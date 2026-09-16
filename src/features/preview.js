(function registerPreviewFeature(global) {
  "use strict";

  const MIN_CHAT_WORKSPACE_WIDTH = 520;
  const MIN_PREVIEW_WIDTH = 250;
  const DEFAULT_PREVIEW_WIDTH = 420;

  const Code = global.Code;
  if (!Code?.features) throw new Error("Code namespace must load before preview feature");

  function parseDelimitedText(text = "", delimiter = ",", maxRows = 10001) {
    const rows = [];
    let row = [];
    let field = "";
    let quoted = false;
    let limited = false;

    for (let index = 0; index < text.length; index += 1) {
      const char = text[index];
      if (quoted) {
        if (char === '"' && text[index + 1] === '"') {
          field += '"';
          index += 1;
        } else if (char === '"') {
          quoted = false;
        } else {
          field += char;
        }
        continue;
      }
      if (char === '"' && field.length === 0) {
        quoted = true;
      } else if (char === delimiter) {
        row.push(field);
        field = "";
      } else if (char === "\n" || char === "\r") {
        if (char === "\r" && text[index + 1] === "\n") index += 1;
        row.push(field);
        rows.push(row);
        row = [];
        field = "";
        if (rows.length >= maxRows) {
          limited = index < text.length - 1;
          break;
        }
      } else {
        field += char;
      }
    }
    if (!limited && (field.length || row.length)) {
      row.push(field);
      rows.push(row);
    }
    while (rows.length && rows[rows.length - 1].every((cell) => cell === "")) rows.pop();
    return { rows, limited };
  }

  function previewRawUrl(path = "", version = "") {
    const query = `/api/file?path=${encodeURIComponent(path || "")}&raw=1`;
    return version ? `${query}&v=${encodeURIComponent(version)}` : query;
  }

  function createPreviewFeature(options = {}) {
    const state = options.state || {};
    const els = options.elements || {};
    const t = options.t || ((key) => key);
    const escapeHtml = options.escapeHtml || ((value) => String(value ?? ""));
    const apiJson = options.apiJson;
    const renderMarkdown = options.renderMarkdown;
    const resolveSyntaxPatterns = options.resolveSyntaxPatterns || (() => null);
    const highlightSyntax = options.highlightSyntax || ((line) => escapeHtml(line));
    const languageFromPath = options.languageFromPath || (() => "text");
    const formatSize = options.formatSize || ((value) => String(value || 0));
    const copyText = options.copyText || (async () => false);
    const showCopyFeedback = options.showCopyFeedback || (() => {});
    const showToast = options.showToast || (() => {});
    const documentRef = options.document || global.document;
    const storage = options.storage || global.localStorage;

    if (typeof apiJson !== "function") throw new Error("preview feature requires apiJson");
    if (typeof renderMarkdown !== "function") throw new Error("preview feature requires renderMarkdown");

    let pollTimer = null;
    let dragState = null;
    let resizeFrame = 0;
    let pendingWidth = null;
    let bound = false;
    const STORE_KEY = "code-preview-workspaces-v1";
    const clone = (value) => JSON.parse(JSON.stringify(value));
    const uid = () => (global.crypto || globalThis.crypto).randomUUID().replaceAll("-", "");
    let scope = null;
    let workspace = null;
    let epoch = 0;
    let requestSeq = 0;
    let openIntentSeq = 0;
    let orderBase = 0;
    let gesture = null;
    let draftId;
    let restoring = null;
    let restoreTarget = null;
    let lastData = null;
    let rendererSeq = 0;
    const contentCache = new Map();
    const CACHE_ENTRIES = 8;
    const CACHE_BYTES = 8 * 1024 * 1024;
    let cacheBytes = 0;
    function dropCached(key) {
      const item = contentCache.get(key);
      if (item) { cacheBytes -= item.bytes; contentCache.delete(key); }
    }
    function clearCached() { contentCache.clear(); cacheBytes = 0; }
    function cachePreview(data) {
      dropCached(data.fileKey);
      const serialized = JSON.stringify(data);
      const bytes = Math.max(serialized.length * 2, new TextEncoder().encode(serialized).length);
      if (bytes > CACHE_BYTES) return;
      contentCache.set(data.fileKey, { data: Object.freeze({ ...data }), bytes });
      cacheBytes += bytes;
      while (contentCache.size > CACHE_ENTRIES || cacheBytes > CACHE_BYTES) dropCached(contentCache.keys().next().value);
    }
    function cachedPreview(key) {
      const item = contentCache.get(key);
      if (!item) return null;
      contentCache.delete(key); contentCache.set(key, item);
      return item.data;
    }
    let warned = new Set();
    const memory = new Map();
    const invalidRecords = new Set();
    const closedFiles = new Map();
    try { draftId = global.sessionStorage.getItem("code-preview-draft") || uid(); }
    catch (_) { draftId = uid(); }
    const tabsElement = documentRef.getElementById?.("previewTabs");
    const keyOf = (ctx) => `${ctx.dataSourceId}:${ctx.sessionId || "draft"}:${ctx.sessionInstanceId}`;
    const activeTab = () => workspace?.tabs.find((tab) => tab.id === workspace.active);
    const emptyWorkspace = () => ({ tabs: [], active: null, mru: [], reuse: null, paneOpen: false });
    function warn(key, onceKey = key) {
      if (!warned.has(onceKey)) { warned.add(onceKey); showToast(t(key), "warning"); }
    }
    function readStore() {
      const raw = storage?.getItem(STORE_KEY);
      if (raw == null) return { version: 1, records: {}, migrated: false };
      const value = JSON.parse(raw);
      if (value?.version !== 1 || !value.records || typeof value.records !== "object"
        || Array.isArray(value.records) || Object.keys(value.records).length > 50
        || new TextEncoder().encode(raw).length > 1048576) throw new Error("store");
      return value;
    }
    function validWorkspace(value) {
      const object = (item) => item !== null && typeof item === "object" && !Array.isArray(item);
      const text = (item, max) => typeof item === "string" && item.length > 0 && item.length <= max && !item.includes("\0");
      const number = (item, min = 0, max = 1e9) => typeof item === "number" && Number.isFinite(item) && item >= min && item <= max;
      const integer = (item) => number(item) && Number.isSafeInteger(item);
      if (!object(value) || !Array.isArray(value.tabs) || value.tabs.length > 20
        || typeof value.paneOpen !== "boolean" || !Array.isArray(value.mru) || value.mru.length > 20) return false;
      if (!value.tabs.every((tab) => object(tab) && typeof tab.id === "string" && /^[a-f0-9]{32}$/.test(tab.id)
        && typeof tab.fileKey === "string" && /^[a-f0-9]{64}$/.test(tab.fileKey)
        && text(tab.path, 32768) && text(tab.locator, 32768)
        && (tab.name === undefined || text(tab.name, 4096))
        && (tab.mode == null || ["source", "rendered", "table"].includes(tab.mode))
        && (tab.scroll === undefined || number(tab.scroll))
        && (tab.scale == null || number(tab.scale, 0.1, 5))
        && (tab.page === undefined || integer(tab.page))
        && (tab.order === undefined || integer(tab.order))
        && (tab.innerScroll === undefined || (object(tab.innerScroll) && number(tab.innerScroll.top) && number(tab.innerScroll.left))))) return false;
      const ids = new Set(value.tabs.map((tab) => tab.id));
      const orders = value.tabs.map((tab, index) => tab.order ?? index + 1);
      return ids.size === value.tabs.length && new Set(value.tabs.map((tab) => tab.fileKey)).size === value.tabs.length
        && new Set(orders).size === orders.length
        && (value.orderCounter === undefined || (integer(value.orderCounter) && value.orderCounter >= Math.max(0, ...orders)))
        && (value.tabs.length ? ids.has(value.active) : value.active === null)
        && (value.reuse === null || ids.has(value.reuse))
        && value.mru.every((id) => ids.has(id)) && new Set(value.mru).size === value.mru.length;
    }
    function saveView() {
      const tab = activeTab();
      if (!tab || !state.previewPath) return;
      tab.scroll = Math.max(0, els.filePreview.scrollTop || 0);
      tab.mode = state.previewMode;
      tab.scale = state.previewImageScale;
      tab.page = state.previewTable?.page || 0;
      const inner = els.filePreview.querySelector(".preview-table-scroll, .image-preview-viewport");
      if (inner) tab.innerScroll = { top: inner.scrollTop, left: inner.scrollLeft };
    }
    function restoreView(tab, line) {
      if (!line) els.filePreview.scrollTop = tab.scroll || 0;
      if (state.previewKind === "delimited" && state.previewMode === "table" && state.previewTable) {
        state.previewTable.page = Math.max(0, Number(tab.page) || 0);
        renderDelimitedTablePage();
      }
      const inner = els.filePreview.querySelector(".preview-table-scroll, .image-preview-viewport");
      if (inner && tab.innerScroll) {
        inner.scrollTop = tab.innerScroll.top || 0;
        inner.scrollLeft = tab.innerScroll.left || 0;
      }
    }
    function persist({ migrated = false } = {}) {
      if (!scope || !workspace) return false;
      memory.set(keyOf(scope), clone(workspace));
      try {
        if (invalidRecords.has(keyOf(scope))) throw new Error("invalid existing record");
        if (!scope.sessionId) {
          const raw = global.sessionStorage.getItem(`code-preview-draft:${keyOf(scope)}`);
          if (raw !== null) {
            try { if (new TextEncoder().encode(raw).length > 1048576 || !validWorkspace(JSON.parse(raw))) throw new Error("invalid draft"); }
            catch (error) { invalidRecords.add(keyOf(scope)); memory.delete(keyOf(scope)); throw error; }
          }
          const encodedDraft = JSON.stringify(workspace);
          if (new TextEncoder().encode(encodedDraft).length > 1048576) throw new Error("draft capacity");
          global.sessionStorage.setItem("code-preview-draft", draftId);
          global.sessionStorage.setItem(`code-preview-draft:${keyOf(scope)}`, encodedDraft);
          if (!migrated) return true;
        }
        const store = readStore();
        const key = keyOf(scope);
        if (invalidRecords.has(key)) throw new Error("invalid existing record");
        if (Object.hasOwn(store.records, key) && !validWorkspace(store.records[key])) {
          invalidRecords.add(key); memory.delete(key); throw new Error("invalid existing record");
        }
        if (scope.sessionId) {
          if (!Object.hasOwn(store.records, key) && Object.keys(store.records).length >= 50) throw new Error("capacity");
          store.records[key] = clone(workspace);
        }
        if (migrated) store.migrated = true;
        const encoded = JSON.stringify(store);
        if (new TextEncoder().encode(encoded).length > 1048576) throw new Error("capacity");
        storage.setItem(STORE_KEY, encoded);
        return true;
      } catch (_) { warn("previewStateUnsaved"); return false; }
    }
    function clearRenderer(empty = true) {
      releaseDrag(false);
      stopAutoRefresh();
      rendererSeq += 1;
      requestSeq += 1;
      state.previewPath = "";
      state.previewTreePath = "";
      state.previewContent = "";
      state.previewTable = null;
      state.previewKind = "";
      lastData = null;
      state._previewMtime = "";
      markActiveFile();
      els.filePreview.onclick = null;
      if (empty) renderNotice(t("noFileOpen"), t("selectFileToPreview"));
      else { els.filePreview.innerHTML = ""; renderModeActions([]); }
    }
    function renderLoading(tab) {
      els.previewTitle.textContent = tab.name || tab.path.split(/[\\/]/).pop();
      els.previewMeta.textContent = t("previewLoading");
      els.previewLanguage.textContent = "";
      els.filePreview.className = "file-preview loading";
      els.filePreview.innerHTML = `<div class="preview-notice" role="status"><span>${escapeHtml(t("previewLoading"))}</span></div>`;
      els.refreshPreview.disabled = true;
      els.copyPreview.disabled = true;
    }
    function beginNavigation() {
      saveView();
      persist();
      const token = { epoch: ++epoch, draft: scope && !scope.sessionId ? clone(workspace) : null,
        sourceId: scope?.dataSourceId };
      gesture = null;
      closedFiles.clear();
      clearCached();
      scope = null;
      workspace = null;
      restoring = null;
      restoreTarget = null;
      clearRenderer();
      els.workbench.classList.remove("preview-open");
      if (els.fileTree) { els.fileTree.inert = true; els.fileTree.setAttribute("aria-busy", "true"); }
      renderTabs();
      return token;
    }
    function renderTabs() {
      if (!tabsElement) return;
      const focusedTab = tabsElement.contains(documentRef.activeElement) ? documentRef.activeElement?.dataset?.previewTab : null;
      tabsElement.replaceChildren();
      for (const tab of workspace?.tabs || []) {
        const item = documentRef.createElement("div");
        item.className = `preview-tab${tab.id === workspace.active ? " active" : ""}`;
        const button = documentRef.createElement("button");
        button.type = "button";
        button.dataset.previewTab = tab.id;
        button.textContent = tab.name || tab.path.split(/[\\/]/).pop();
        button.title = tab.path;
        button.setAttribute("role", "tab");
        button.setAttribute("aria-selected", String(tab.id === workspace.active));
        button.tabIndex = tab.id === workspace.active ? 0 : -1;
        button.addEventListener("click", () => { gesture = null; activate(tab.id); });
        button.addEventListener("keydown", (event) => {
          if (event.key === "Delete") { event.preventDefault(); closeTab(tab.id); return; }
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          const list = workspace.tabs;
          let index = list.indexOf(tab);
          index = event.key === "Home" ? 0 : event.key === "End" ? list.length - 1
            : (index + (event.key === "ArrowRight" ? 1 : -1) + list.length) % list.length;
          activate(list[index].id);
          tabsElement.querySelector('[aria-selected="true"]')?.focus();
        });
        const closeButton = documentRef.createElement("button");
        closeButton.type = "button";
        closeButton.className = "preview-tab-close";
        closeButton.textContent = "×";
        closeButton.setAttribute("aria-label", t("previewCloseTab", { name: tab.name || tab.path }));
        closeButton.addEventListener("click", () => closeTab(tab.id));
        item.append(button, closeButton);
        tabsElement.appendChild(item);
      }
      if (focusedTab) [...tabsElement.querySelectorAll("[data-preview-tab]")].find((button) => button.dataset.previewTab === focusedTab)?.focus({ preventScroll: true });
      tabsElement.querySelector('[aria-selected="true"]')?.closest(".preview-tab")?.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
    function fileUrl(path, tab = null, raw = false) {
      const query = new URLSearchParams({ ...scope, path });
      if (tab) query.set("fileKey", tab.fileKey);
      if (raw) { query.set("raw", "1"); query.set("v", state._previewMtime || ""); }
      return `/api/preview/file?${query}`;
    }
    function current(token, tab) {
      return token.epoch === epoch && token.seq === requestSeq && scope
        && token.scopeKey === keyOf(scope) && activeTab() === tab && workspace.paneOpen;
    }
    async function readActive({ line, refresh = false } = {}) {
      const tab = activeTab();
      if (!scope || !tab || !workspace.paneOpen) return;
      stopAutoRefresh();
      const token = { epoch, seq: ++requestSeq, scopeKey: keyOf(scope) };
      try {
        const data = await apiJson(fileUrl(tab.locator, tab));
        if (!current(token, tab)) return;
        if (data.fileKey !== tab.fileKey || data.canonicalAbsolutePath !== tab.path) throw new Error("preview_file_changed");
        cachePreview(data);
        if (!refresh || data.contentRevision !== state._previewMtime) {
          saveView();
          state.previewMode = tab.mode;
          renderData(data, { line, scheduleRefresh: false });
          restoreView(tab, line);
          if (state.previewKind === "image") applyImageScale(tab.scale ?? null);
        }
        startAutoRefresh();
      } catch (_) {
        if (!current(token, tab)) return;
        clearCached();
        clearRenderer(false);
        renderNotice(t("previewUnavailable"), tab.path);
        els.refreshPreview.disabled = false;
      }
    }
    function activate(id, options = {}) {
      if (!workspace) return;
      saveView();
      clearRenderer(false);
      workspace.active = id;
      workspace.mru = [id, ...workspace.mru.filter((value) => value !== id)];
      workspace.paneOpen = true;
      els.workbench.classList.add("preview-open");
      renderTabs();
      persist();
      const tab = activeTab();
      const cached = cachedPreview(tab.fileKey);
      if (cached) { state.previewMode = tab.mode; renderData(cached, { ...options, scheduleRefresh: false }); restoreView(tab, options.line); }
      else renderLoading(tab);
      return readActive({ ...options, refresh: Boolean(cached) });
    }
    function closeTab(id) {
      if (!workspace) return;
      gesture = null;
      saveView();
      const wasActive = workspace.active === id;
      const closing = workspace.tabs.find((tab) => tab.id === id);
      if (closing) { closedFiles.set(closing.fileKey, ++openIntentSeq); dropCached(closing.fileKey); }
      workspace.tabs = workspace.tabs.filter((tab) => tab.id !== id);
      workspace.mru = workspace.mru.filter((value) => value !== id);
      if (workspace.reuse === id) workspace.reuse = null;
      if (wasActive) {
        const next = workspace.mru.find((value) => workspace.tabs.some((tab) => tab.id === value)) || workspace.tabs[0]?.id;
        if (next) activate(next);
        else { workspace.active = null; close(); }
      }
      renderTabs();
      persist();
      if (wasActive && workspace.active) tabsElement?.querySelector('[aria-selected="true"]')?.focus({ preventScroll: true });
    }
    async function restore(creationToken = null) {
      const target = state.sessionId || `draft:${draftId}`;
      if (!creationToken && restoring && restoreTarget === target) return restoring;
      const token = beginNavigation();
      const sessionId = state.sessionId || "";
      const promise = (async () => {
        try {
          const ctx = await apiJson("/api/preview/context", { method: "POST",
            body: JSON.stringify({ sessionId, draftId: sessionId ? "" : draftId }) });
          if (token.epoch !== epoch || (state.sessionId || "") !== sessionId) return false;
          scope = ctx;
          if (els.fileTree) { els.fileTree.inert = false; els.fileTree.removeAttribute("aria-busy"); }
          let saved = memory.get(keyOf(ctx));
          let hasSaved = memory.has(keyOf(ctx));
          try {
            const store = readStore();
            if (!hasSaved && sessionId && Object.hasOwn(store.records, keyOf(ctx))) {
              saved = store.records[keyOf(ctx)]; hasSaved = true;
            } else if (!hasSaved && !sessionId) {
              const raw = global.sessionStorage.getItem(`code-preview-draft:${keyOf(ctx)}`);
              if (raw !== null) {
                if (new TextEncoder().encode(raw).length > 1048576) throw new Error("draft capacity");
                hasSaved = true; saved = JSON.parse(raw);
              }
            }
            const previousPrefix = `${ctx.dataSourceId}:${sessionId}:`;
            if (sessionId && !hasSaved && Object.entries(store.records).some(([key, record]) => key.startsWith(previousPrefix)
                && key !== keyOf(ctx) && /^[a-f0-9]{32}$/.test(key.slice(previousPrefix.length))
                && validWorkspace(record) && record.tabs.length)) {
              warn("previewTabsUnavailable", `previewTabsUnavailable:${keyOf(ctx)}`);
            }
          } catch (_) {
            if (!sessionId) invalidRecords.add(keyOf(ctx));
            warn("previewStateUnsaved");
          }
          if (hasSaved && !validWorkspace(saved)) { invalidRecords.add(keyOf(ctx)); warn("previewStateUnsaved"); saved = null; }
          workspace = saved ? clone(saved) : emptyWorkspace();
          workspace.tabs.forEach((tab, index) => { if (!Number.isFinite(tab.order)) tab.order = index + 1; });
          workspace.orderCounter = Math.max(0, ...workspace.tabs.map((tab) => tab.order));
          if (creationToken?.draft && creationToken.epoch === token.epoch - 1
              && creationToken.sourceId === ctx.dataSourceId && !workspace.tabs.length) {
            workspace = clone(creationToken.draft);
          }
          orderBase = workspace.orderCounter || 0;
          renderTabs();
          if (workspace.paneOpen && activeTab()) await activate(workspace.active);
          if (token.epoch !== epoch) return false;
          try {
            if (global.navigator?.locks) await global.navigator.locks.request("code-preview-legacy-migration", async () => {
              if (token.epoch !== epoch || invalidRecords.has(keyOf(scope))) return;
              const store = readStore();
              if (store.migrated || workspace.tabs.length || (store.migrationOwner && store.migrationOwner !== keyOf(scope))) return;
              if (storage.getItem("code-preview-open") !== "1") return;
              const path = storage.getItem("code-preview-path");
              if (!path) return;
              store.migrationOwner = keyOf(scope);
              storage.setItem(STORE_KEY, JSON.stringify(store));
              if (await loadFile(path, undefined, { ready: true }) && token.epoch === epoch) persist({ migrated: true });
            });
          } catch (_) { warn("previewStateUnsaved"); }
          return true;
        } catch (error) {
          if (token.epoch === epoch) {
            scope = null;
            workspace = null;
            clearRenderer();
            renderTabs();
            if (els.fileTree) { els.fileTree.inert = false; els.fileTree.removeAttribute("aria-busy"); }
            warn(error?.data?.errorCode === "preview_source_unavailable" ? "previewSourceUnavailable" : "previewUnavailable");
          }
          return false;
        }
      })();
      restoring = promise;
      restoreTarget = target;
      const settled = () => { if (restoring === promise) { restoring = null; restoreTarget = null; } };
      void promise.then(settled, settled);
      return promise;
    }
    function newDraft() {
      draftId = uid();
      return restore();
    }
    function contextWillChange() { return scope ? beginNavigation() : null; }
    function contextDidChange(token) { if (token?.epoch === epoch) return restore(); }

    function applyPreviewWidth(width = state.previewWidth, persist = true) {
      const measuredWorkbenchWidth = Number(els.workbench?.getBoundingClientRect?.().width);
      const availableWorkbenchWidth = Number.isFinite(measuredWorkbenchWidth)
        && measuredWorkbenchWidth > 0
        ? measuredWorkbenchWidth
        : (Number(global.innerWidth) || 1280);
      const previewLimit = Math.max(
        MIN_PREVIEW_WIDTH,
        availableWorkbenchWidth - MIN_CHAT_WORKSPACE_WIDTH,
      );
      const requestedWidth = Number(width) || DEFAULT_PREVIEW_WIDTH;
      const next = Math.min(Math.max(requestedWidth, MIN_PREVIEW_WIDTH), previewLimit);
      state.previewWidth = next;
      documentRef?.documentElement?.style?.setProperty("--preview-width", `${next}px`);
      if (persist) { try { storage?.setItem("code-preview-width", String(next)); } catch (_) { warn("previewStateUnsaved"); } }
      return next;
    }

    function renderModeActions(actions = []) {
      if (!els.previewModeActions) return;
      els.previewModeActions.replaceChildren();
      actions.forEach((action) => {
        const button = documentRef.createElement("button");
        button.type = "button";
        button.className = `preview-mode-btn${action.active ? " active" : ""}${action.iconOnly ? " icon-only" : ""}`;
        button.textContent = action.label;
        button.title = action.title || action.label;
        button.setAttribute("aria-label", action.title || action.label);
        if (action.disabled) button.disabled = true;
        button.addEventListener("click", () => { action.onClick(); saveView(); persist(); });
        els.previewModeActions.appendChild(button);
      });
    }

    function renderNotice(title, body = "") {
      els.filePreview.className = "file-preview empty";
      els.previewTitle.textContent = title;
      els.previewMeta.textContent = body || "";
      els.previewLanguage.textContent = "";
      renderModeActions([]);
      els.refreshPreview.disabled = true;
      els.copyPreview.disabled = true;
      els.filePreview.innerHTML = `
        <div class="preview-notice">
          <strong>${escapeHtml(title)}</strong>
          ${body ? `<span>${escapeHtml(body)}</span>` : ""}
        </div>
      `;
    }

    function renderCodePreview(content = "") {
      const normalized = content.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
      const lines = normalized.length ? normalized.split("\n") : [""];
      const lang = languageFromPath(state.previewPath || "");
      const doHighlight = normalized.length <= 350000 && lines.length <= 8000
        ? resolveSyntaxPatterns(lang)
        : null;

      els.filePreview.className = "file-preview code-preview";
      els.filePreview.innerHTML = lines.map((line, index) => {
        const highlighted = doHighlight ? highlightSyntax(line, lang) : escapeHtml(line);
        return `
          <div class="code-line" data-line="${index + 1}">
            <span class="line-no">${index + 1}</span>
            <span class="line-code">${highlighted || " "}</span>
          </div>
        `;
      }).join("");
      els.filePreview.onclick = (event) => {
        const line = event.target.closest(".code-line");
        if (!line || !els.filePreview.contains(line)) return;
        els.filePreview.querySelector(".code-line.active-line")?.classList.remove("active-line");
        line.classList.add("active-line");
        copyText(`${state.previewPath}:${line.dataset.line}`);
      };
    }

    function sanitizeHtml(html = "") {
      const documentNode = new global.DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
      documentNode.querySelectorAll("script, style, iframe, object, embed, form, input, button, textarea, select").forEach((node) => node.remove());
      documentNode.querySelectorAll("*").forEach((node) => {
        [...node.attributes].forEach((attribute) => {
          const name = attribute.name.toLowerCase();
          const value = attribute.value.trim().toLowerCase();
          if (name.startsWith("on") || ((name === "href" || name === "src") && value.startsWith("javascript:"))) {
            node.removeAttribute(attribute.name);
          }
        });
      });
      return documentNode.body.firstElementChild?.innerHTML || "";
    }

    function renderMarkdownPreview(content = "", mode = state.previewMode) {
      state.previewMode = mode === "source" ? "source" : "rendered";
      renderModeActions([
        { label: t("previewRendered"), active: state.previewMode === "rendered", onClick: () => renderMarkdownPreview(content, "rendered") },
        { label: t("previewSource"), active: state.previewMode === "source", onClick: () => renderMarkdownPreview(content, "source") },
      ]);
      if (state.previewMode === "source") {
        renderCodePreview(content);
        return;
      }
      els.filePreview.onclick = null;
      els.filePreview.className = "file-preview markdown-preview";
      els.filePreview.innerHTML = `<article class="preview-markdown-body">${sanitizeHtml(renderMarkdown(content))}</article>`;
    }

    function renderDelimitedTablePage() {
      const tableState = state.previewTable;
      if (!tableState) return;
      const rows = tableState.rows;
      if (!rows.length) {
        els.filePreview.innerHTML = `<div class="preview-notice"><span>${escapeHtml(t("previewNoRows"))}</span></div>`;
        return;
      }
      const headers = rows[0];
      const dataRows = rows.slice(1);
      const totalPages = Math.max(1, Math.ceil(dataRows.length / tableState.pageSize));
      tableState.page = Math.min(Math.max(0, tableState.page), totalPages - 1);
      const start = tableState.page * tableState.pageSize;
      const visibleRows = dataRows.slice(start, start + tableState.pageSize);
      const columnCount = Math.max(1, ...rows.map((row) => row.length));
      const visibleColumnCount = Math.min(columnCount, 60);
      const normalizedHeaders = Array.from({ length: visibleColumnCount }, (_, index) => headers[index] || `#${index + 1}`);
      const headHtml = normalizedHeaders.map((header) => `<th>${escapeHtml(header)}</th>`).join("");
      const bodyHtml = visibleRows.map((row, rowIndex) => {
        const cells = Array.from({ length: visibleColumnCount }, (_, columnIndex) => `<td>${escapeHtml(row[columnIndex] || "")}</td>`).join("");
        return `<tr><th class="table-row-number">${start + rowIndex + 2}</th>${cells}</tr>`;
      }).join("");
      const limitNotice = tableState.limited ? `<span class="table-limit-notice">${escapeHtml(t("previewTableLimited", { count: rows.length }))}</span>` : "";
      els.filePreview.innerHTML = `
        <div class="preview-table-scroll">
          <table class="preview-data-table"><thead><tr><th class="table-row-number">#</th>${headHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>
        </div>
        <footer class="preview-table-footer">
          <span>${escapeHtml(t("previewRows", { count: dataRows.length }))} · ${escapeHtml(t("previewColumns", { count: columnCount }))}</span>
          ${limitNotice}
          <div class="preview-table-pager">
            <button type="button" class="mini-btn" data-table-page="previous" ${tableState.page === 0 ? "disabled" : ""} title="${escapeHtml(t("previewPreviousPage"))}">‹</button>
            <span>${escapeHtml(t("previewPageOf", { page: tableState.page + 1, total: totalPages }))}</span>
            <button type="button" class="mini-btn" data-table-page="next" ${tableState.page >= totalPages - 1 ? "disabled" : ""} title="${escapeHtml(t("previewNextPage"))}">›</button>
          </div>
        </footer>`;
      els.filePreview.querySelector('[data-table-page="previous"]')?.addEventListener("click", () => {
        tableState.page -= 1;
        renderDelimitedTablePage();
        saveView(); persist();
      });
      els.filePreview.querySelector('[data-table-page="next"]')?.addEventListener("click", () => {
        tableState.page += 1;
        renderDelimitedTablePage();
        saveView(); persist();
      });
    }

    function renderDelimitedPreview(content = "", delimiter = ",", mode = state.previewMode) {
      state.previewMode = mode === "source" ? "source" : "table";
      renderModeActions([
        { label: t("previewTable"), active: state.previewMode === "table", onClick: () => renderDelimitedPreview(content, delimiter, "table") },
        { label: t("previewSource"), active: state.previewMode === "source", onClick: () => renderDelimitedPreview(content, delimiter, "source") },
      ]);
      if (state.previewMode === "source") {
        renderCodePreview(content);
        return;
      }
      if (!state.previewTable || state.previewTable.content !== content || state.previewTable.delimiter !== delimiter) {
        const parsed = parseDelimitedText(content, delimiter);
        state.previewTable = { content, delimiter, rows: parsed.rows, limited: parsed.limited, page: 0, pageSize: 100 };
      }
      els.filePreview.onclick = null;
      els.filePreview.className = "file-preview table-preview";
      renderDelimitedTablePage();
    }

    function currentImageFitScale() {
      const viewport = els.filePreview.querySelector(".image-preview-viewport");
      const image = viewport?.querySelector("img");
      if (!viewport || !image?.naturalWidth || !image?.naturalHeight) return 1;
      return Math.min((viewport.clientWidth - 32) / image.naturalWidth, (viewport.clientHeight - 32) / image.naturalHeight, 1);
    }

    function applyImageScale(scale = null) {
      const viewport = els.filePreview.querySelector(".image-preview-viewport");
      const image = viewport?.querySelector("img");
      if (!viewport || !image) return;
      state.previewImageScale = scale === null ? null : Math.min(5, Math.max(0.1, scale));
      viewport.classList.toggle("fit", state.previewImageScale === null);
      if (state.previewImageScale === null) {
        image.style.width = "";
        image.style.height = "";
      } else {
        image.style.width = `${Math.round(image.naturalWidth * state.previewImageScale)}px`;
        image.style.height = `${Math.round(image.naturalHeight * state.previewImageScale)}px`;
      }
      renderImageActions();
    }

    function renderImageActions() {
      const displayScale = state.previewImageScale === null ? currentImageFitScale() : state.previewImageScale;
      renderModeActions([
        { label: "−", iconOnly: true, title: t("previewZoomOut"), onClick: () => applyImageScale(displayScale / 1.25) },
        { label: state.previewImageScale === null ? t("previewFit") : `${Math.round(displayScale * 100)}%`, active: state.previewImageScale === null, title: t("previewFit"), onClick: () => applyImageScale(null) },
        { label: "+", iconOnly: true, title: t("previewZoomIn"), onClick: () => applyImageScale(displayScale * 1.25) },
        { label: "1:1", title: t("previewActualSize"), active: state.previewImageScale === 1, onClick: () => applyImageScale(1) },
      ]);
    }

    function renderImagePreview(path = state.previewPath) {
      state.previewImageScale = activeTab()?.scale ?? null;
      els.filePreview.onclick = null;
      els.filePreview.className = "file-preview image-preview";
      els.filePreview.innerHTML = `<div class="image-preview-viewport fit"><img src="${escapeHtml(fileUrl(activeTab()?.locator || path, activeTab(), true))}" alt="${escapeHtml(path.split(/[\\/]/).pop() || "preview")}" draggable="false" /></div>`;
      const viewport = els.filePreview.querySelector(".image-preview-viewport");
      const image = viewport.querySelector("img");
      const imageEpoch = epoch, imageSeq = rendererSeq;
      const imageCurrent = () => imageEpoch === epoch && imageSeq === rendererSeq && image.isConnected;
      els.previewMeta.textContent = formatMeta(lastData || {}, t("previewLoading"));
      image.addEventListener("load", () => {
        if (imageCurrent()) { applyImageScale(state.previewImageScale); els.previewMeta.textContent = formatMeta(lastData || {}); }
      }, { once: true });
      image.addEventListener("error", () => {
        if (imageCurrent()) { clearCached(); renderNotice(t("loadFailed"), t("imageReadFailed")); }
      }, { once: true });
      let imageDrag = null;
      viewport.addEventListener("pointerdown", (event) => {
        if (event.button !== 0 || state.previewImageScale === null) return;
        imageDrag = { x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop };
        viewport.classList.add("dragging");
        viewport.setPointerCapture(event.pointerId);
      });
      viewport.addEventListener("pointermove", (event) => {
        if (!imageDrag) return;
        viewport.scrollLeft = imageDrag.left - (event.clientX - imageDrag.x);
        viewport.scrollTop = imageDrag.top - (event.clientY - imageDrag.y);
      });
      const endImageDrag = () => { imageDrag = null; viewport.classList.remove("dragging"); };
      viewport.addEventListener("pointerup", endImageDrag);
      viewport.addEventListener("pointercancel", endImageDrag);
      renderImageActions();
    }

    function renderPdfPreview(path = state.previewPath) {
      els.filePreview.onclick = null;
      els.filePreview.className = "file-preview pdf-preview";
      renderModeActions([]);
      els.filePreview.innerHTML = `<iframe class="preview-pdf-frame" src="${escapeHtml(fileUrl(activeTab()?.locator || path, activeTab(), true))}#view=FitH&toolbar=1&navpanes=0" title="${escapeHtml(path.split(/[\\/]/).pop() || t("previewPdf"))}"></iframe>`;
      const frame = els.filePreview.querySelector("iframe");
      const frameEpoch = epoch, frameSeq = rendererSeq;
      els.previewMeta.textContent = formatMeta(lastData || {}, t("previewLoading"));
      frame.addEventListener("load", () => {
        if (frameEpoch === epoch && frameSeq === rendererSeq && frame.isConnected) els.previewMeta.textContent = formatMeta(lastData || {});
      }, { once: true });
    }

    function markActiveFile() {
      (documentRef.querySelectorAll?.(".file-item") || []).forEach((button) => {
        const selected = button.dataset.path === state.previewPath || button.dataset.path === lastData?.path;
        button.classList.toggle("active", selected);
        button.closest?.(".file-item-row")?.classList.toggle("active", selected);
      });
    }

    function formatMeta(data, suffix = "") {
      const parts = [data.path || state.previewPath || "", formatSize(data.size || 0)];
      const encoding = String(data.encoding || "").toLowerCase();
      if (encoding && encoding !== "utf-8" && encoding !== "utf-8-sig") parts.push(encoding);
      if (data.truncated) parts.push(t("fmtTruncatedContent"));
      if (suffix) parts.push(suffix);
      return parts.filter(Boolean).join(" \u00b7 ");
    }

    function stopAutoRefresh() {
      if (pollTimer !== null) global.clearTimeout(pollTimer);
      pollTimer = null;
    }

    function startAutoRefresh() {
      stopAutoRefresh();
      if (scope && workspace?.paneOpen && activeTab()) {
        pollTimer = global.setTimeout(() => readActive({ refresh: true }), 3000);
      }
    }

    function scrollPreviewToLine(line) {
      const target = els.filePreview.querySelector(`.code-line[data-line="${line}"]`);
      if (!target) return;
      els.filePreview.querySelector(".code-line.active-line")?.classList.remove("active-line");
      target.classList.add("active-line");
      target.scrollIntoView({ block: "center", behavior: "smooth" });
    }

    async function loadFile(path, mtime, options = {}) {
      void mtime;
      const suppliedIntent = options.intent;
      const intentSeq = suppliedIntent?.seq ?? (options.ready ? openIntentSeq : ++openIntentSeq);
      if (!scope && !options.ready) {
        const expectedEpoch = epoch + (restoring ? 0 : 1);
        if (restoring) await restoring;
        else await restore();
        if (epoch !== expectedEpoch) return false;
      }
      if (!scope || !workspace) return false;
      if (!options.newTab && options.gesture !== "double" && intentSeq !== openIntentSeq) return false;
      if (suppliedIntent && (suppliedIntent.epoch !== epoch || suppliedIntent.scopeKey !== keyOf(scope))) return false;
      const ownEpoch = epoch;
      const context = scope;
      let ownSeq = suppliedIntent?.requestSeq ?? ++requestSeq;
      const requestedOrder = suppliedIntent?.order ?? orderBase + intentSeq;
      workspace.orderCounter = Math.max(workspace.orderCounter || 0, requestedOrder);
      saveView();
      if (options.gesture === "double") {
        if (gesture?.path === path && gesture.epoch === epoch) workspace = clone(gesture.before);
        gesture = null;
        options = { ...options, newTab: true };
      } else if (options.gesture === "single") {
        gesture = { path, epoch, before: clone(workspace) };
      } else gesture = null;
      workspace.orderCounter = Math.max(workspace.orderCounter || 0, requestedOrder);
      const beforeGesture = gesture;
      stopAutoRefresh();
      if (ownSeq === requestSeq) {
        clearRenderer(false);
        ownSeq = requestSeq;
        workspace.paneOpen = true;
        els.workbench.classList.add("preview-open");
        renderLoading({ path });
      }
      try {
        const data = await apiJson(fileUrl(path));
        if (ownEpoch !== epoch || context !== scope || (!options.newTab && ownSeq !== requestSeq)) return false;
        if (!data.fileKey || !data.canonicalAbsolutePath) throw new Error("identity");
        if ((closedFiles.get(data.fileKey) || 0) > intentSeq) return false;
        const foreground = ownSeq === requestSeq;
        let tab = workspace.tabs.find((item) => item.fileKey === data.fileKey);
        if (!tab) {
          const slot = !options.newTab && workspace.tabs.find((item) => item.id === workspace.reuse);
          if (!slot && workspace.tabs.length >= 20) {
            warn("previewTabLimit");
            if (foreground && activeTab()) await activate(workspace.active);
            return false;
          }
          tab = { id: slot?.id || uid(), path: data.canonicalAbsolutePath,
            locator: data.locator, fileKey: data.fileKey, name: data.name,
            scroll: 0, mode: null, scale: null, order: slot?.order ?? requestedOrder };
          if (slot) workspace.tabs.splice(workspace.tabs.indexOf(slot), 1, tab);
          else workspace.tabs.push(tab);
          if (!options.newTab) workspace.reuse = tab.id;
        }
        if (options.newTab) tab.order = Math.min(tab.order, requestedOrder);
        workspace.tabs.sort((left, right) => left.order - right.order);
        cachePreview(data);
        if (!foreground) {
          if (!workspace.active) workspace.active = tab.id;
          renderTabs(); persist(); return true;
        }
        if (beforeGesture && gesture === beforeGesture) gesture.committed = true;
        clearRenderer(false);
        workspace.active = tab.id;
        workspace.mru = [tab.id, ...workspace.mru.filter((id) => id !== tab.id)];
        workspace.paneOpen = true;
        els.workbench.classList.add("preview-open");
        state.previewMode = tab.mode;
        renderData(data, options);
        restoreView(tab, options.line);
        renderTabs();
        persist();
        return true;
      } catch (_) {
        if (ownEpoch === epoch && ownSeq === requestSeq) {
          clearCached();
          clearRenderer(false);
          renderNotice(t("previewUnavailable"), path);
          showToast(t("previewUnavailable"), "warning");
        }
        return false;
      }
    }

    function renderData(data, options = {}) {
      rendererSeq += 1;
      lastData = data;
      const previousPath = state.previewPath;
      applyPreviewWidth(state.previewWidth, false);
      state.previewPath = data.canonicalAbsolutePath;
      state.previewTreePath = data.path;
      if (previousPath !== state.previewPath) {
        state.previewTable = null;
        state.previewImageScale = null;
      }
      state._previewMtime = data.contentRevision || "";
      const language = languageFromPath(state.previewPath);
      markActiveFile();
      els.previewTitle.textContent = data.name || "File";
      els.previewMeta.textContent = formatMeta(data);
      els.previewLanguage.textContent = language;
      els.refreshPreview.disabled = false;
      const ext = (data.name || "").split(".").pop()?.toLowerCase();

      if (ext && /^(png|jpg|jpeg|gif|webp|svg|bmp|ico)$/i.test(ext)) {
        state.previewKind = "image";
        state.previewContent = "";
        els.previewLanguage.textContent = ext;
        renderImagePreview(state.previewPath);
        els.copyPreview.disabled = true;
        if (options.scheduleRefresh !== false) startAutoRefresh();
        return;
      }
      if (ext === "pdf") {
        state.previewKind = "pdf";
        state.previewContent = "";
        els.previewLanguage.textContent = "pdf";
        renderPdfPreview(state.previewPath);
        els.copyPreview.disabled = true;
        if (options.scheduleRefresh !== false) startAutoRefresh();
        return;
      }
      if (data.binary) {
        state.previewContent = "";
        renderNotice(t("binaryFile"), t("previewUnsupported"));
        els.copyPreview.disabled = true;
        return;
      }

      state.previewContent = data.content || "";
      if (state.previewContent) {
        if (ext === "md" || ext === "markdown" || ext === "mdown") {
          state.previewKind = "markdown";
          if (!state.previewMode) state.previewMode = "rendered";
          renderMarkdownPreview(state.previewContent, state.previewMode);
        } else if (ext === "csv" || ext === "tsv") {
          state.previewKind = "delimited";
          if (!state.previewMode) state.previewMode = "table";
          renderDelimitedPreview(state.previewContent, ext === "tsv" ? "\t" : ",", state.previewMode);
        } else {
          state.previewKind = "text";
          state.previewMode = "source";
          renderModeActions([]);
          renderCodePreview(state.previewContent);
        }
      } else {
        renderNotice(t("emptyFile"), t("noTextContent"));
      }
      els.copyPreview.disabled = false;
      if (options.line && Number.isInteger(options.line) && options.line > 0) {
        scrollPreviewToLine(options.line);
      }
      if (options.scheduleRefresh !== false) startAutoRefresh();
    }

    function close() {
      gesture = null;
      saveView();
      if (workspace) workspace.paneOpen = false;
      persist();
      clearRenderer();
      els.workbench.classList.remove("preview-open");
      els.togglePreview?.focus?.({ preventScroll: true });
    }

    async function toggle() {
      if (workspace?.paneOpen) { close(); return; }
      if (!scope) await restore();
      if (!workspace) return;
      workspace.paneOpen = true;
      els.workbench.classList.add("preview-open");
      applyPreviewWidth(state.previewWidth, true);
      if (activeTab()) await activate(workspace.active);
      persist();
    }

    function releaseDrag(commit = false) {
      const previous = dragState;
      const width = pendingWidth;
      if (!previous && !resizeFrame && width === null) return;
      dragState = null;
      pendingWidth = null;
      if (resizeFrame) {
        global.cancelAnimationFrame(resizeFrame);
        resizeFrame = 0;
      }
      if (previous && els.previewResizer.hasPointerCapture?.(previous.pointerId)) {
        try { els.previewResizer.releasePointerCapture(previous.pointerId); } catch (_) { /* Already released by the browser. */ }
      }
      documentRef.body?.classList.remove("resizing-preview");
      documentRef?.documentElement?.style?.removeProperty?.("--drag-message-list-width");
      documentRef?.documentElement?.style?.removeProperty?.("--drag-preview-content-width");
      if (commit && previous) applyPreviewWidth(width ?? state.previewWidth, true);
    }
    function finishDrag(event) {
      if (!dragState || (event?.pointerId !== undefined && event.pointerId !== dragState.pointerId)) return;
      releaseDrag(true);
    }

    function bind() {
      if (bound) return;
      bound = true;
      els.refreshPreview.addEventListener("click", () => {
        gesture = null;
        readActive();
      });
      els.copyPreview.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopImmediatePropagation();
        const ok = await copyText(state.previewContent || "");
        showCopyFeedback(els.copyPreview, ok);
      }, true);
      els.togglePreview.addEventListener("click", toggle);
      els.closePreview?.addEventListener("click", close);
      els.previewResizer.addEventListener("pointerdown", (event) => {
        if (!els.workbench.classList.contains("preview-open")) return;
        event.preventDefault();
        releaseDrag(false);
        dragState = { startX: event.clientX, startWidth: state.previewWidth, pointerId: event.pointerId };
        const messageListWidth = els.messageList?.getBoundingClientRect?.().width || 0;
        const previewContentWidth = els.filePreview?.getBoundingClientRect?.().width || 0;
        if (messageListWidth) {
          documentRef?.documentElement?.style?.setProperty(
            "--drag-message-list-width",
            `${messageListWidth}px`,
          );
        }
        if (previewContentWidth) {
          documentRef?.documentElement?.style?.setProperty(
            "--drag-preview-content-width",
            `${previewContentWidth}px`,
          );
        }
        els.previewResizer.setPointerCapture(event.pointerId);
        documentRef.body.classList.add("resizing-preview");
      });
      els.previewResizer.addEventListener("pointermove", (event) => {
        if (!dragState || (event.pointerId !== undefined && event.pointerId !== dragState.pointerId)) return;
        pendingWidth = dragState.startWidth - (event.clientX - dragState.startX);
        if (resizeFrame) return;
        const scheduledDrag = dragState;
        resizeFrame = global.requestAnimationFrame(() => {
          if (dragState !== scheduledDrag) return;
          applyPreviewWidth(pendingWidth, false);
          resizeFrame = 0;
        });
      });
      els.previewResizer.addEventListener("pointerup", finishDrag);
      els.previewResizer.addEventListener("pointercancel", () => releaseDrag(false));
      global.addEventListener("resize", () => applyPreviewWidth(state.previewWidth));
      global.addEventListener("pagehide", () => { saveView(); persist(); stopAutoRefresh(); releaseDrag(false); clearCached(); });
      els.filePreview?.addEventListener?.("scroll", () => { saveView(); persist(); }, { passive: true });
    }

    return Object.freeze({
      applyPreviewWidth,
      beginNavigation,
      newDraft,
      contextWillChange,
      contextDidChange,
      closeTab,
      bind,
      close,
      loadFile,
      renderCodePreview,
      renderDelimitedPreview,
      renderImagePreview,
      renderMarkdownPreview,
      renderPdfPreview,
      restore,
      ensureRestored: () => scope ? Promise.resolve(true) : restoring || restore(),
      captureOpenIntent: () => { stopAutoRefresh(); const seq = ++openIntentSeq; return { epoch, seq, requestSeq: ++requestSeq,
        scopeKey: scope ? keyOf(scope) : null,
        order: workspace ? orderBase + seq : null }; },
      finishOpenProbe: (token) => { if (token.epoch === epoch && token.seq === openIntentSeq) startAutoRefresh(); },
      isOpenIntentCurrent: (token, explicit = false) => token.epoch === epoch && Boolean(scope)
        && token.scopeKey === keyOf(scope) && (explicit || token.seq === openIntentSeq),
      refreshLanguage: () => {
        saveView();
        renderTabs();
        if (lastData && state.previewPath) { renderData(lastData, { scheduleRefresh: false }); restoreView(activeTab()); }
        else renderNotice(t("noFileOpen"), t("selectFileToPreview"));
      },
      stopAutoRefresh,
      toggle,
    });
  }

  Code.features.preview = Object.freeze({
    createPreviewFeature,
    parseDelimitedText,
    previewRawUrl,
  });
})(window);
