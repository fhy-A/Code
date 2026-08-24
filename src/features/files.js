(function initializeCodeFilesFeature(global) {
  "use strict";

  const features = global.Code && global.Code.features;
  if (!features) {
    throw new Error("Code features namespace must load before files");
  }

  function shortPath(path = "") {
    const normalized = String(path).replaceAll("/", "\\");
    const parts = normalized.split("\\").filter(Boolean);
    if (parts.length <= 2) return normalized || "~";
    return `~\\${parts.slice(-2).join("\\")}`;
  }

  function arrayBufferToBase64(buffer, encode = global.btoa) {
    const bytes = new Uint8Array(buffer);
    const chunkSize = 0x8000;
    let binary = "";
    for (let index = 0; index < bytes.length; index += chunkSize) {
      binary += String.fromCharCode.apply(null, bytes.subarray(index, index + chunkSize));
    }
    return encode(binary);
  }

  function sortFileItems(items = [], mode = "default", ascending = true) {
    const sorted = [...items];
    const direction = ascending ? 1 : -1;

    if (mode === "type") {
      sorted.sort((a, b) => {
        if (a.type !== b.type) return (a.type === "dir" ? -1 : 1) * direction;
        const extA = (a.name.split(".").pop() || "").toLowerCase();
        const extB = (b.name.split(".").pop() || "").toLowerCase();
        if (extA !== extB) return extA.localeCompare(extB) * direction;
        return a.name.localeCompare(b.name) * direction;
      });
    } else if (mode === "time") {
      sorted.sort((a, b) => (
        (new Date(b.updatedAt || 0) - new Date(a.updatedAt || 0)) * direction
      ));
    } else {
      sorted.sort((a, b) => {
        if (a.type !== b.type) return (a.type === "dir" ? -1 : 1) * direction;
        return a.name.localeCompare(b.name) * direction;
      });
    }

    return sorted;
  }

  const FILE_TIME_WIDE_SIDEBAR_MIN = 320;
  const SILENT_FILE_REFRESH_DELAY_MS = 32;
  const SILENT_FILE_REFRESH_SEEN_LIMIT = 256;

  function normalizeFileTreeIdentity(value = "") {
    return String(value || "")
      .trim()
      .replace(/\\/g, "/")
      .replace(/\/+$/, "")
      .toLowerCase();
  }

  function createSilentFileTreeRefreshController(options = {}) {
    const captureView = options.captureView;
    const requestItems = options.requestItems;
    const applyItems = options.applyItems;
    const isViewCurrent = options.isViewCurrent;
    const hostSetTimeout = global.setTimeout || globalThis.setTimeout;
    const hostClearTimeout = global.clearTimeout || globalThis.clearTimeout;
    const setTimer = options.setTimeout || hostSetTimeout.bind(globalThis);
    const clearTimer = options.clearTimeout || hostClearTimeout.bind(globalThis);
    const delayMs = Math.max(0, Number(options.delayMs ?? SILENT_FILE_REFRESH_DELAY_MS));
    const seenLimit = Math.max(1, Number(options.seenLimit ?? SILENT_FILE_REFRESH_SEEN_LIMIT));

    if (!captureView || !requestItems || !applyItems || !isViewCurrent) {
      throw new Error("Silent file refresh requires capture, request, apply, and current-view checks");
    }

    let timerId = null;
    let generation = 0;
    let requestCount = 0;
    let applyCount = 0;
    let pendingRoots = new Set();
    const seenTurns = new Set();
    const seenOrder = [];

    function rememberTurn(turnId) {
      if (!turnId || seenTurns.has(turnId)) return false;
      seenTurns.add(turnId);
      seenOrder.push(turnId);
      while (seenOrder.length > seenLimit) {
        seenTurns.delete(seenOrder.shift());
      }
      return true;
    }

    function cancelPendingTimer() {
      if (timerId === null) return;
      clearTimer(timerId);
      timerId = null;
    }

    function invalidate() {
      generation += 1;
      pendingRoots = new Set();
      cancelPendingTimer();
    }

    async function flush() {
      cancelPendingTimer();
      const scheduledRoots = pendingRoots;
      pendingRoots = new Set();
      const view = captureView();
      if (!view) return false;
      const rootIdentity = normalizeFileTreeIdentity(view.root);
      if (scheduledRoots.size && !scheduledRoots.has(rootIdentity)) return false;

      const requestGeneration = generation;
      requestCount += 1;
      let data;
      try {
        data = await requestItems(view);
      } catch (_) {
        return false;
      }
      if (requestGeneration !== generation || !isViewCurrent(view, data)) return false;
      applyItems(data, view);
      applyCount += 1;
      return true;
    }

    function schedule({ turnId = "", root = "" } = {}) {
      const stableTurnId = String(turnId || "").trim();
      if (!rememberTurn(stableTurnId)) return false;
      const view = captureView();
      if (!view) return false;
      const visibleRoot = normalizeFileTreeIdentity(view.root);
      const requestedRoot = normalizeFileTreeIdentity(root);
      if (requestedRoot && requestedRoot !== visibleRoot) return false;

      generation += 1;
      pendingRoots.add(visibleRoot);
      if (timerId === null) {
        timerId = setTimer(() => { void flush(); }, delayMs);
      }
      return true;
    }

    function snapshot() {
      return Object.freeze({
        generation,
        pending: timerId !== null,
        requestCount,
        applyCount,
        seenCount: seenTurns.size,
      });
    }

    return Object.freeze({ schedule, flush, invalidate, snapshot });
  }

  function formatFileTimestamp(value, now = new Date()) {
    const date = value instanceof Date ? value : new Date(value || "");
    const current = now instanceof Date ? now : new Date(now);
    if (Number.isNaN(date.getTime()) || Number.isNaN(current.getTime())) {
      return { compact: "", full: "" };
    }
    const pad = (number) => String(number).padStart(2, "0");
    const year = date.getFullYear();
    const monthDay = `${pad(date.getMonth() + 1)}/${pad(date.getDate())}`;
    const time = `${pad(date.getHours())}:${pad(date.getMinutes())}`;
    const full = `${year}/${monthDay} ${time}`;
    const sameDay = year === current.getFullYear()
      && date.getMonth() === current.getMonth()
      && date.getDate() === current.getDate();
    const compact = sameDay
      ? time
      : year === current.getFullYear()
        ? `${monthDay} ${time}`
        : `${year}/${monthDay}`;
    return { compact, full };
  }

  async function requestOpenFile(apiJson, showToast, t, body) {
    try {
      const data = await apiJson("/api/open-file", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (!data || data.ok !== true || typeof data.degraded !== "boolean") {
        throw new Error("Invalid open-file response");
      }
      if (data.degraded === true) showToast?.(t("openDegraded"), "warning");
      return data;
    } catch (_) {
      showToast?.(t("openFailed"), "error");
      return null;
    }
  }

  function createFilesFeature(options = {}) {
    const state = options.state;
    const elements = options.elements;
    const t = options.t;
    const escapeHtml = options.escapeHtml;
    const apiJson = options.apiJson;
    const showToast = options.showToast;
    const openFile = options.openFile;
    const insertPromptText = options.insertPromptText;
    const saveProjectRoot = options.saveProjectRoot;
    const documentRoot = options.documentRoot || global.document;
    const storage = options.storage || global.localStorage;

    if (!state || !elements || !t || !escapeHtml || !apiJson) {
      throw new Error("Files feature requires state, elements, t, escapeHtml, and apiJson");
    }

    let fileContextMenu = null;
    let bound = false;

    function getRecentFolders() {
      try {
        const value = JSON.parse(storage.getItem("code-recent-folders") || "[]");
        return Array.isArray(value) ? value : [];
      } catch (_) {
        return [];
      }
    }

    function addRecentFolder(path) {
      if (!path) return;
      const filtered = getRecentFolders().filter((item) => item !== path);
      filtered.unshift(path);
      storage.setItem("code-recent-folders", JSON.stringify(filtered.slice(0, 8)));
    }

    function removeRecentFolder(path) {
      if (!path) return;
      storage.setItem(
        "code-recent-folders",
        JSON.stringify(getRecentFolders().filter((item) => item !== path)),
      );
    }

    async function uploadAttachment(file) {
      const contentBase64 = arrayBufferToBase64(await file.arrayBuffer());
      return apiJson("/api/attachments", {
        method: "POST",
        body: JSON.stringify({
          name: file.name,
          contentBase64,
        }),
      });
    }

    function pickProjectFile() {
      if (!elements.filePicker) return;
      elements.filePicker.value = "";
      elements.filePicker.click();
    }

    async function resolvePickedFile(file) {
      if (!file) return;
      if (elements.attachFile) elements.attachFile.disabled = true;
      try {
        const data = await uploadAttachment(file);
        insertPromptText?.(data.path);
      } catch (error) {
        showToast?.(error.message || t("chooseFileFailed"), "error");
      } finally {
        if (elements.attachFile) elements.attachFile.disabled = false;
      }
    }

    function showFileContextMenu(x, y, path, type) {
      if (fileContextMenu) fileContextMenu.remove();
      const menu = documentRoot.createElement("div");
      menu.className = "file-ctx-menu";
      const menuWidth = 180;
      const menuHeight = 130;
      menu.style.left = Math.min(x, global.innerWidth - menuWidth) + "px";
      menu.style.top = Math.min(y, global.innerHeight - menuHeight) + "px";
      const filename = (path || "").split("/").pop() || "";
      if (type === "file") {
        menu.innerHTML = `<div class="file-ctx-name">${escapeHtml(filename)}</div>
          <button data-action="open">${t("openDefaultApp")}</button>
          <button data-action="copy-path">${t("copyPath")}</button>
          <button data-action="reveal">${t("revealInFolder")}</button>`;
      } else {
        menu.innerHTML = `<div class="file-ctx-name">${escapeHtml(filename)}</div>
          <button data-action="explore">${t("openExplorer")}</button>
          <button data-action="copy-path">${t("copyPath")}</button>
          <button data-action="terminal">${t("openTerminal")}</button>`;
      }

      menu.querySelectorAll("button").forEach((button) => {
        button.addEventListener("click", () => {
          const action = button.dataset.action;
          if (action === "copy-path") {
            const root = (elements.projectRoot?.value || "").replace(/[\\/]+$/, "");
            const fullPath = root ? `${root}/${path}`.replace(/\\/g, "/") : path;
            global.navigator.clipboard.writeText(fullPath)
              .then(() => showToast?.(t("pathCopied"), "warning"))
              .catch(() => showToast?.(t("copyFailed"), "error"));
          } else {
            const body = { path };
            if (action === "reveal") body.reveal = true;
            if (action === "explore") body.explorer = true;
            if (action === "terminal") body.terminal = true;
            void requestOpenFile(apiJson, showToast, t, body);
          }
          menu.remove();
        });
      });

      documentRoot.body.appendChild(menu);
      fileContextMenu = menu;
      const close = (event) => {
        if (!menu.contains(event.target)) {
          menu.remove();
          fileContextMenu = null;
          documentRoot.removeEventListener("click", close);
        }
      };
      global.setTimeout(() => documentRoot.addEventListener("click", close), 0);
    }

    function renderFileTree() {
      if (state._noProject) {
        elements.fileTree.innerHTML = `<div class="muted-line" style="padding:12px;">${t("noProjectDir")}</div>`;
        elements.goUp.disabled = true;
        elements.newFolderBtn.disabled = true;
        elements.refreshFiles.disabled = true;
        return;
      }

      elements.goUp.disabled = false;
      elements.newFolderBtn.disabled = false;
      elements.refreshFiles.disabled = false;

      const query = elements.fileSearch.value.trim().toLowerCase();
      const items = state._fileItems || [];
      const filtered = query
        ? items.filter((item) => item.name.toLowerCase().includes(query))
        : items;
      const sortMode = state._fileSortMode || "default";
      const ascending = state._fileSortAsc !== false;

      if (elements.fileSortBtn) {
        const labels = {
          default: t("sortDefault"),
          type: t("sortType"),
          time: t("sortTime"),
        };
        documentRoot.getElementById("fileSortLabel").textContent = labels[sortMode] || t("sortType");
        documentRoot.getElementById("fileSortArrow").textContent = ascending ? "↑" : "↓";
      }

      const sorted = sortFileItems(filtered, sortMode, ascending);
      elements.fileTree.innerHTML = sorted.length
        ? sorted.map((item, index) => {
            const extension = item.type === "dir"
              ? ""
              : ((item.name || "").split(".").pop() || "").toLowerCase().slice(0, 6);
            const extensionClass = extension ? ` ext-${extension}` : "";
            const timestamp = formatFileTimestamp(item.updatedAt);
            const timestampHtml = timestamp.full
              ? `<small class="file-time" title="${escapeHtml(timestamp.full)}" aria-label="${escapeHtml(timestamp.full)}"><span class="file-time-compact" aria-hidden="true">${escapeHtml(timestamp.compact)}</span><span class="file-time-full" aria-hidden="true">${escapeHtml(timestamp.full)}</span></small>`
              : "";
            return `<div class="file-item-row ${item.path === state.previewPath ? "active" : ""}">
              <button class="file-item ${item.type}${extensionClass}" type="button" data-path="${escapeHtml(item.path)}" data-type="${item.type}" tabindex="${index === 0 ? 0 : -1}" role="option" aria-selected="false">
                <span class="file-name" title="${escapeHtml(item.name)}">${item.type === "dir" ? "📁 " : ""}${escapeHtml(item.name)}</span>
                ${timestampHtml}
              </button>
              <button class="file-at-btn" type="button" data-path="${escapeHtml(item.path)}" title="${t("fileAtTitle")}">@</button>
            </div>`;
          }).join("")
        : `<div class="muted-line" style="padding:8px;">${query ? t("noMatchingFiles") : t("emptyDirectory")}</div>`;

      elements.fileTree.querySelectorAll(".file-item").forEach((button) => {
        button.addEventListener("click", () => {
          if (button.dataset.type === "dir") loadFiles(button.dataset.path);
          else openFile?.(button.dataset.path);
        });
        button.addEventListener("contextmenu", (event) => {
          event.preventDefault();
          showFileContextMenu(
            event.clientX,
            event.clientY,
            button.dataset.path,
            button.dataset.type,
          );
        });
      });

      elements.fileTree.querySelectorAll(".file-at-btn").forEach((button) => {
        button.addEventListener("click", (event) => {
          event.stopPropagation();
          insertPromptText?.(`@${button.dataset.path} `);
        });
      });
    }

    function setFileTimeDensity(sidebarWidth) {
      elements.fileTree?.classList.toggle(
        "file-time-wide",
        Number(sidebarWidth) >= FILE_TIME_WIDE_SIDEBAR_MIN,
      );
    }

    function renderPathBar(dir) {
      if (!dir) {
        elements.filePathBar.style.display = "none";
        elements.filePathBar.innerHTML = "";
        return;
      }
      const parts = dir.split("/").filter(Boolean);
      if (!parts.length) {
        elements.filePathBar.style.display = "none";
        elements.filePathBar.innerHTML = "";
        return;
      }

      function buildHtml(partsToShow, collapseIndex) {
        // collapseIndex: first visible index (0 = no collapse), -1 = show all
        let html2 = "";
        if (collapseIndex > 0) {
          // collapsed segments are represented by a single "…" linked to the deepest collapsed path
          const collapsedPath = parts.slice(0, collapseIndex).join("/");
          html2 += `<span class="path-seg" data-path="${escapeHtml(collapsedPath)}">…</span>`;
          html2 += '<span class="path-sep">▸</span>';
        }
        for (let i = Math.max(0, collapseIndex); i < partsToShow.length; i++) {
          if (i > Math.max(0, collapseIndex)) html2 += '<span class="path-sep">▸</span>';
          const pathUpTo = partsToShow.slice(0, i + 1).join("/");
          if (i === partsToShow.length - 1) {
            html2 += `<span class="path-seg current">${escapeHtml(partsToShow[i])}</span>`;
          } else {
            html2 += `<span class="path-seg" data-path="${escapeHtml(pathUpTo)}">${escapeHtml(partsToShow[i])}</span>`;
          }
        }
        return html2;
      }

      // start with all segments visible
      let collapseIndex = 0;
      elements.filePathBar.innerHTML = buildHtml(parts, collapseIndex);
      elements.filePathBar.style.display = "";

      // if overflowing, progressively collapse from the left, keeping at least the last 2 segments
      if (parts.length > 2 && elements.filePathBar.scrollWidth > elements.filePathBar.clientWidth) {
        for (let ci = 1; ci <= parts.length - 2; ci++) {
          elements.filePathBar.innerHTML = buildHtml(parts, ci);
          if (elements.filePathBar.scrollWidth <= elements.filePathBar.clientWidth) {
            collapseIndex = ci;
            break;
          }
          collapseIndex = ci;
        }
      }

      elements.filePathBar.querySelectorAll(".path-seg[data-path]").forEach((seg) => {
        seg.addEventListener("click", () => loadFiles(seg.dataset.path));
      });
    }

    const silentRefresh = createSilentFileTreeRefreshController({
      captureView() {
        if (state._noProject || !elements.fileTree || !elements.projectRoot) return null;
        return {
          root: String(state._fileRoot || elements.projectRoot.value || ""),
          dir: String(state.currentDir || ""),
          search: String(elements.fileSearch?.value || ""),
          previewPath: String(state.previewPath || ""),
          scrollTop: Number(elements.fileTree.scrollTop || 0),
        };
      },
      requestItems(view) {
        return apiJson(`/api/files?path=${encodeURIComponent(view.dir)}`);
      },
      isViewCurrent(view, data) {
        return normalizeFileTreeIdentity(state._fileRoot || elements.projectRoot?.value) === normalizeFileTreeIdentity(view.root)
          && normalizeFileTreeIdentity(state.currentDir) === normalizeFileTreeIdentity(view.dir)
          && normalizeFileTreeIdentity(data?.root) === normalizeFileTreeIdentity(view.root)
          && normalizeFileTreeIdentity(data?.path) === normalizeFileTreeIdentity(view.dir);
      },
      applyItems(data) {
        const preservedScrollTop = Number(elements.fileTree.scrollTop || 0);
        state._fileItems = Array.isArray(data?.items) ? data.items : [];
        renderFileTree();
        elements.fileTree.scrollTop = preservedScrollTop;
      },
      setTimeout: options.setTimeout,
      clearTimeout: options.clearTimeout,
      delayMs: options.silentRefreshDelayMs,
    });

    function focusFirstFileItem() {
      const first = elements.fileTree.querySelector(".file-item");
      if (!first) return;
      const items = [...elements.fileTree.querySelectorAll(".file-item")];
      setFileRowSelected(first, items);
      first.focus();
    }

    async function loadFiles(path = state.currentDir) {
      silentRefresh.invalidate();
      const data = await apiJson(`/api/files?path=${encodeURIComponent(path || "")}`);
      state.currentDir = data.path || "";
      state._fileRoot = data.root || "";
      renderPathBar(state.currentDir);
      elements.cwdPathText.textContent = shortPath(data.root || "");
      elements.fileSearch.value = "";
      state._fileItems = data.items || [];
      elements.goUp.disabled = !state.currentDir;
      renderFileTree();
      // Auto-focus the first list item after switching directories so the
      // keyboard user can navigate immediately without an extra Tab.
      focusFirstFileItem();
    }

    function goUpDir() {
      if (!state.currentDir) return;
      const parts = state.currentDir.split("/").filter(Boolean);
      parts.pop();
      loadFiles(parts.join("/"));
    }
    // ---- Recursive file search (CODE-027) + keyboard navigation (CODE-028) ----
    const searchSetTimeout = options.setTimeout || (global.setTimeout || globalThis.setTimeout).bind(globalThis);
    const searchClearTimeout = options.clearTimeout || (global.clearTimeout || globalThis.clearTimeout).bind(globalThis);
    let searchRequestSeq = 0;
    let searchTimer = null;

    // Streaming progressive search (R007): directory-grained query cache + per-level
    // scan queue that starts at the current file-tree directory and expands upward
    // toward the project root (server glob_files is recursive per path, so each
    // level covers its whole subtree; results are merged by path, deduplicated).
    const SEARCH_CACHE_TTL_MS = 3000;
    const SEARCH_LIMIT = 500;
    const searchCache = new Map();
    let searchStream = null; // { seq, results: Map, scanned, total, limitHit, truncatedAny, done }

    function setFileRowSelected(target, items) {
      items.forEach((el) => {
        const selected = el === target;
        el.setAttribute("aria-selected", selected ? "true" : "false");
        el.classList.toggle("focused", selected);
      });
    }

    function buildSearchLevels(startDir, root) {
      const rootPath = String(root || "").replace(/[\\/]+$/, "");
      const parts = String(startDir || "").split("/").filter(Boolean);
      const levels = [];
      const seen = new Set();
      const push = (level) => {
        if (level && !seen.has(level)) {
          seen.add(level);
          levels.push(level);
        }
      };
      for (let i = parts.length; i >= 0; i--) {
        push([rootPath, ...parts.slice(0, i)].filter(Boolean).join("/"));
      }
      if (!seen.has(rootPath)) push(rootPath);
      return levels;
    }

    function searchProgressText(stream) {
      if (stream.total <= 1) {
        // Single level (current dir is the project root): no level counter.
        return t("searchProgressSingle", { n: stream.results.size });
      }
      return t("searchProgress", {
        n: stream.results.size,
        x: Math.min(stream.scanned + 1, stream.total),
        y: stream.total,
      });
    }

    function restoreSearchFocus() {
      const active = documentRoot.activeElement;
      if (!active || !active.classList || !active.classList.contains("file-item")) return;
      const path = active.dataset && active.dataset.path;
      if (!path) return;
      const items = [...elements.fileTree.querySelectorAll(".file-item")];
      const match = items.find((el) => el.dataset.path === path);
      if (match) {
        setFileRowSelected(match, items);
        match.focus();
      }
    }

    function renderSearchResults() {
      const stream = searchStream;
      const results = stream ? [...stream.results.values()] : [];
      const html = [];
      if (stream && !stream.done) {
        html.push(`<div class="muted-line search-status-line">${escapeHtml(searchProgressText(stream))}</div>`);
      } else if (results.length) {
        const countLine = stream && stream.limitHit
          ? t("searchResultCountLimited", { n: SEARCH_LIMIT })
          : t("searchResultCount", { n: results.length });
        html.push(`<div class="muted-line search-count-line">${escapeHtml(countLine)}</div>`);
      }
      if (results.length) {
        html.push(results.map((item, index) => {
            const base = String(item.path || "").split("/").filter(Boolean).pop() || item.path || "";
            const extension = item.type === "dir"
              ? ""
              : (base.split(".").pop() || "").toLowerCase().slice(0, 6);
            const extensionClass = extension ? ` ext-${extension}` : "";
            return `<div class="file-item-row search-row">
              <button class="file-item ${item.type}${extensionClass}" type="button" data-path="${escapeHtml(item.path)}" data-type="${item.type}" tabindex="${index === 0 ? 0 : -1}" role="option" aria-selected="false">
                <span class="file-name" title="${escapeHtml(item.path)}">${item.type === "dir" ? "📁 " : ""}${escapeHtml(item.path)}</span>
              </button>
              <button class="file-at-btn" type="button" data-path="${escapeHtml(item.path)}" title="${t("fileAtTitle")}">@</button>
            </div>`;
          }).join(""));
      } else if (stream && stream.done) {
        html.push(`<div class="muted-line" style="padding:8px;">${t("noMatchingFiles")}</div>`);
      }
      elements.fileTree.innerHTML = html.join("");
      if (stream?.truncatedAny) {
        elements.fileTree.insertAdjacentHTML("beforeend", `<div class="muted-line search-truncated">${t("searchTruncated")}</div>`);
      }
      bindFileItemActions();
      restoreSearchFocus();
    }

    function bindFileItemActions() {
      elements.fileTree.querySelectorAll(".file-item").forEach((button) => {
        button.addEventListener("click", () => {
          if (button.dataset.type === "dir") loadFiles(button.dataset.path);
          else openFile?.(button.dataset.path);
        });
        button.addEventListener("contextmenu", (event) => {
          event.preventDefault();
          showFileContextMenu(
            event.clientX,
            event.clientY,
            button.dataset.path,
            button.dataset.type,
          );
        });
      });
      elements.fileTree.querySelectorAll(".file-at-btn").forEach((button) => {
        button.addEventListener("click", (event) => {
          event.stopPropagation();
          insertPromptText?.(`@${button.dataset.path} `);
        });
      });
    }

    async function fetchGlobCached(path, pattern) {
      const key = `${path}|${pattern}`;
      const cached = searchCache.get(key);
      const now = Date.now();
      if (cached && now - cached.ts < SEARCH_CACHE_TTL_MS) return cached.data;
      const data = await apiJson("/api/tools/glob_files", {
        method: "POST",
        body: JSON.stringify({ pattern, path }),
      });
      if (data?.ok) searchCache.set(key, { ts: now, data });
      return data;
    }

    async function runStreamingSearch(query) {
      const seq = ++searchRequestSeq;
      const pattern = `*${query}*`;
      const rootPath = String(state._fileRoot || "").replace(/[\\/]+$/, "");
      const levels = buildSearchLevels(state.currentDir || "", rootPath);
      const stream = {
        seq,
        results: new Map(),
        scanned: 0,
        total: levels.length,
        limitHit: false,
        truncatedAny: false,
        done: false,
      };
      searchStream = stream;
      renderSearchResults();
      try {
        for (const dir of levels) {
          if (seq !== searchRequestSeq) return; // cancelled by newer input
          const data = await fetchGlobCached(dir, pattern);
          if (seq !== searchRequestSeq) return; // stale response dropped
          if (data?.ok) {
            const items = Array.isArray(data.results) ? data.results : [];
            // Detect the server fallback: glob_files rescans the whole project
            // root when the requested subtree has no matches. Its response then
            // already covers the whole project, so stop the queue to avoid
            // repeating the full scan on every level.
            const relDir = rootPath ? dir.slice(rootPath.length).replace(/^[\\/]+/, "") : dir;
            const prefix = relDir ? relDir + "/" : "";
            const fellBack = Boolean(prefix) && items.some((item) => !String(item.path || "").startsWith(prefix));
            for (const item of items) {
              if (stream.results.size >= SEARCH_LIMIT) {
                stream.limitHit = true;
                break;
              }
              if (item && item.path && !stream.results.has(item.path)) {
                stream.results.set(item.path, item);
              }
            }
            if (data.truncated) stream.truncatedAny = true;
            if (fellBack) {
              stream.scanned = stream.total;
              break;
            }
          }
          stream.scanned += 1;
          if (stream.limitHit) break;
          renderSearchResults(); // incremental render after each level
        }
        stream.done = true;
        if (seq === searchRequestSeq) renderSearchResults();
      } catch (error) {
        if (seq !== searchRequestSeq) return;
        elements.fileTree.innerHTML = `<div class="muted-line" style="padding:8px;">${escapeHtml(String(error.message || error))}</div>`;
      }
    }

    function onFileSearchInput() {
      if (searchTimer !== null) searchClearTimeout(searchTimer);
      const query = String(elements.fileSearch?.value || "").trim();
      if (!query) {
        searchRequestSeq += 1; // cancel any in-flight search
        searchStream = null;
        renderFileTree();
        return;
      }
      // Show a searching state while the debounce window elapses.
      elements.fileTree.innerHTML = `<div class="muted-line search-status">${t("searching")}</div>`;
      searchTimer = searchSetTimeout(() => {
        const current = String(elements.fileSearch?.value || "").trim();
        if (current) runStreamingSearch(current);
      }, 250);
    }

    function clearSearchAndRestore() {
      if (!elements.fileSearch?.value) return false;
      elements.fileSearch.value = "";
      searchRequestSeq += 1; // cancel any in-flight search
      searchStream = null;
      renderFileTree();
      const first = elements.fileTree.querySelector(".file-item");
      first?.focus();
      return true;
    }

    function isGoUpKey(event) {
      // Alt+ArrowUp may be intercepted by IME/system shortcuts on some
      // setups; Ctrl+ArrowUp is the documented fallback, both stay active.
      return (event.altKey && event.key === "ArrowUp")
        || (event.ctrlKey && event.key === "ArrowUp");
    }

    function handleSearchFieldKeydown(event) {
      // Esc clears the search and restores the current-directory list;
      // Alt/Ctrl+ArrowUp navigates to the parent directory (loadFiles clears
      // the search term as part of restoring the parent listing). Backspace
      // is intentionally not bound here so text editing keeps priority.
      if (isGoUpKey(event)) {
        event.preventDefault();
        goUpDir();
      } else if (event.key === "Escape") {
        event.preventDefault();
        clearSearchAndRestore();
      }
    }

    function handleFileTreeKeydown(event) {
      const items = [...elements.fileTree.querySelectorAll(".file-item")];
      if (!items.length) return;
      const focusedIndex = items.findIndex((el) => el === documentRoot.activeElement);
      if (isGoUpKey(event) || event.key === "Backspace") {
        // Alt/Ctrl+ArrowUp and Backspace navigate to the parent directory;
        // checked before plain ArrowUp so the fallback key is not treated
        // as focus movement.
        event.preventDefault();
        goUpDir();
      } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const start = focusedIndex >= 0 ? focusedIndex : (event.key === "ArrowDown" ? -1 : 0);
        const next = event.key === "ArrowDown"
          ? Math.min(items.length - 1, start + 1)
          : Math.max(0, start - 1);
        const target = items[next] || items[0];
        setFileRowSelected(target, items);
        target.focus();
      } else if (event.key === "Enter" && focusedIndex >= 0) {
        event.preventDefault();
        items[focusedIndex].click();
      } else if (event.key === "Escape") {
        clearSearchAndRestore();
      }
    }


    function renderRecentFolders() {
      const recentContainer = documentRoot.getElementById("cwdRecentFolders");
      const dropdown = documentRoot.getElementById("cwdDropdown");
      const recents = getRecentFolders();
      if (recents.length === 0) {
        recentContainer.innerHTML = "";
        recentContainer.style.display = "none";
        return;
      }

      recentContainer.style.display = "block";
      recentContainer.innerHTML = `<div class="cwd-dropdown-label">${t("recentLabel")}</div>`
        + recents.slice(0, 5).map((path) => (
          `<button class="cwd-dropdown-item cwd-recent-item" data-path="${escapeHtml(path)}">${escapeHtml(shortPath(path))}</button>`
        )).join("");
      recentContainer.querySelectorAll(".cwd-recent-item").forEach((button) => {
        button.addEventListener("click", async () => {
          const path = button.dataset.path;
          dropdown.classList.add("hidden");
          try {
            await saveProjectRoot?.(path);
          } catch (error) {
            const message = String(error.message || error);
            if (/目录不存在|不是文件夹|not exist|not a directory/i.test(message)) {
              removeRecentFolder(path);
              renderRecentFolders();
            }
            showToast?.(message, "error");
          }
        });
      });
    }

    function toggleCwdDropdown() {
      const dropdown = documentRoot.getElementById("cwdDropdown");
      const open = !dropdown.classList.contains("hidden");
      if (open) {
        dropdown.classList.add("hidden");
        return;
      }

      renderRecentFolders();
      const rect = elements.projectRootShort.getBoundingClientRect();
      const spaceBelow = global.innerHeight - rect.bottom;
      dropdown.style.position = "fixed";
      dropdown.style.left = rect.left + "px";
      dropdown.style.right = "auto";
      dropdown.style.width = rect.width + "px";
      dropdown.style.margin = "4px 0 0 0";
      if (spaceBelow < 200) {
        dropdown.style.top = "auto";
        dropdown.style.bottom = (global.innerHeight - rect.top + 4) + "px";
      } else {
        dropdown.style.top = rect.bottom + "px";
        dropdown.style.bottom = "auto";
      }
      dropdown.classList.remove("hidden");
    }

    async function pickFolder() {
      try {
        const data = await apiJson("/api/pick-folder");
        if (!data.cancelled) await saveProjectRoot?.(data.path);
      } catch (error) {
        showToast?.(error.message, "error");
      }
    }

    function openNewFolder() {
      const modal = documentRoot.getElementById("newFolderModal");
      const input = documentRoot.getElementById("newFolderName");
      modal.classList.remove("hidden");
      input.value = "";
      input.focus();
    }

    function hideNewFolder() {
      documentRoot.getElementById("newFolderModal").classList.add("hidden");
    }

    async function createNewFolder() {
      const input = documentRoot.getElementById("newFolderName");
      const name = input.value.trim();
      if (!name) return;
      try {
        await apiJson("/api/mkdir", {
          method: "POST",
          body: JSON.stringify({ name, parent: state.currentDir }),
        });
        hideNewFolder();
        await loadFiles(state.currentDir);
      } catch (error) {
        showToast?.(error.message, "error");
      }
    }

    function bind() {
      if (bound) return;
      bound = true;

      const dropdown = documentRoot.getElementById("cwdDropdown");
      const newFolderModal = documentRoot.getElementById("newFolderModal");
      const newFolderName = documentRoot.getElementById("newFolderName");

      state._fileSortMode = storage.getItem("code-sort-mode") || "default";
      state._fileSortAsc = storage.getItem("code-sort-asc") !== "false";

      elements.attachFile?.addEventListener("click", pickProjectFile);
      elements.filePicker?.addEventListener("change", () => {
        resolvePickedFile(elements.filePicker.files?.[0]);
      });
      elements.projectRootShort?.addEventListener("click", toggleCwdDropdown);
      documentRoot.getElementById("cwdPickFolderBtn")?.addEventListener("click", () => {
        dropdown.classList.add("hidden");
        pickFolder();
      });
      documentRoot.getElementById("cwdHomeBtn")?.addEventListener("click", () => {
        dropdown.classList.add("hidden");
        saveProjectRoot?.("");
      });
      documentRoot.addEventListener("click", (event) => {
        if (!event.target.closest(".cwd-dropdown") && !event.target.closest("#projectRootShort")) {
          dropdown.classList.add("hidden");
        }
      });

      documentRoot.getElementById("closeNewFolder")?.addEventListener("click", hideNewFolder);
      documentRoot.getElementById("cancelNewFolder")?.addEventListener("click", hideNewFolder);
      newFolderModal?.addEventListener("click", (event) => {
        if (event.target === event.currentTarget) hideNewFolder();
      });
      documentRoot.getElementById("confirmNewFolder")?.addEventListener("click", createNewFolder);
      newFolderName?.addEventListener("keydown", (event) => {
        if (event.key === "Enter") createNewFolder();
        if (event.key === "Escape") hideNewFolder();
      });

      elements.refreshFiles?.addEventListener("click", (event) => {
        event.stopPropagation();
        loadFiles().catch((error) => showToast?.(error.message, "error"));
      });
      elements.newFolderBtn?.addEventListener("click", (event) => {
        event.stopPropagation();
        openNewFolder();
      });
      elements.fileSearch?.addEventListener("input", onFileSearchInput);
      elements.fileSearch?.addEventListener("keydown", handleSearchFieldKeydown);
      elements.fileTree?.addEventListener("keydown", handleFileTreeKeydown);
      elements.fileSortBtn?.addEventListener("click", () => {
        state._fileSortAsc = !state._fileSortAsc;
        storage.setItem("code-sort-asc", state._fileSortAsc);
        renderFileTree();
      });
      elements.fileSortBtn?.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        const modes = ["type", "time", "default"];
        const current = state._fileSortMode || "type";
        state._fileSortMode = modes[(modes.indexOf(current) + 1) % modes.length];
        state._fileSortAsc = true;
        storage.setItem("code-sort-mode", state._fileSortMode);
        storage.setItem("code-sort-asc", "true");
        renderFileTree();
      });
      elements.goUp?.addEventListener("click", (event) => {
        event.stopPropagation();
        goUpDir();
      });
    }

    return Object.freeze({
      bind,
      loadFiles,
      scheduleSilentRefresh: silentRefresh.schedule,
      flushSilentRefresh: silentRefresh.flush,
      snapshotSilentRefresh: silentRefresh.snapshot,
      renderFileTree,
      setFileTimeDensity,
      addRecentFolder,
      removeRecentFolder,
      pickProjectFile,
      resolvePickedFile,
    });
  }

  features.files = Object.freeze({
    shortPath,
    arrayBufferToBase64,
    sortFileItems,
    formatFileTimestamp,
    FILE_TIME_WIDE_SIDEBAR_MIN,
    SILENT_FILE_REFRESH_DELAY_MS,
    normalizeFileTreeIdentity,
    createSilentFileTreeRefreshController,
    requestOpenFile,
    createFilesFeature,
  });
})(window);
