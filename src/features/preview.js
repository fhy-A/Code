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
    let review = null;
    let reviewMode = false;
    let reviewRequestsPaused = true;
    const blankSessions = new Map();
    const TREE_NODES = 2000, TREE_BYTES = 2 * 1024 * 1024, TREE_CONCURRENCY = 2, TREE_QUEUE = 16;
    const treeQueue = [];
    let treeRequests = 0;
    let blankState = null, activeBlankId = null;
    const REVIEW_TAB = "review";
    const REVIEW_OPEN_LIMIT = 8;
    const REVIEW_BYTES = 1024 * 1024;
    const REVIEW_LINES = 10000;
    let viewMru = [];
    let revealTabId = null;
    const touchView = id => { revealTabId = id; viewMru = [id, ...viewMru.filter(value => value !== id)].slice(0, 21); };
    function syncReviewModes() { renderTabs(); }
    function stopReviewRequests() {
      reviewRequestsPaused = true;
      review?.summaryRequest?.abort();
      review?.pending?.controller.abort();
    }
    function saveReviewView() {
      if (!reviewMode || !review || els.filePreview.dataset.reviewView !== review.id) return;
      review.scroll = els.filePreview.scrollTop || 0;
      for (const node of els.filePreview.querySelectorAll("[data-review-entry]")) {
        const entry = review.entries.get(node.dataset.reviewEntry), body = node.querySelector(".review-detail");
        if (entry && body) entry.left = (body.querySelector('.diff-lines') || body).scrollLeft;
      }
    }
    function reviewStats(operations, incomplete = false) {
      const known = operations.filter(op => Number.isSafeInteger(op.lineStats?.additions) && op.lineStats.additions >= 0
        && Number.isSafeInteger(op.lineStats?.deletions) && op.lineStats.deletions >= 0);
      if (!known.length) return escapeHtml(t("reviewStatsUnknown"));
      const total = known.reduce((sum, op) => ({add: sum.add + op.lineStats.additions, del: sum.del + op.lineStats.deletions}), {add: 0, del: 0});
      return `<span class="review-additions">+${total.add}</span><span class="review-deletions">−${total.del}</span>${known.length !== operations.length || incomplete ? '<sup>*</sup>' : ''}`;
    }
    function reviewBody(entry) {
      if (entry.limited) return escapeHtml(t("reviewDisplayLimit"));
      if (entry.error) return escapeHtml(t("reviewUnavailableHint"));
      const detail = entry.detail;
      if (!detail) return escapeHtml(t("previewLoading"));
      if (detail.bodyState === "diff") return options.renderDiff(detail.diff, {expanded: true, compact: true});
      const reason = detail.kind === "delete" && ["binary", "encoding", "limit", "unreadable", "changed", "unverifiable"].includes(detail.bodyReason)
        ? `reviewDelete_${detail.bodyReason}` : detail.bodyState === "not-retained" ? "reviewBodyMissing" : detail.bodyState === "limit" ? "reviewBodyLimit" : "reviewNoLineDiff";
      return escapeHtml(t(reason));
    }
    function renderReview() {
      if (!reviewMode || !review) return;
      const focusedKey = documentRef.activeElement?.closest?.('[data-review-entry]')?.dataset.reviewEntry;
      const focusedAction = documentRef.activeElement?.dataset?.reviewAction;
      saveReviewView();
      syncReviewModes();
      els.refreshPreview.disabled = true;
      els.copyPreview.disabled = true;
      renderModeActions([]);
      els.filePreview.className = "file-preview recorded-review";
      els.filePreview.dataset.reviewView = review.id;
      const summary = review.summary;
      const scopeHint = `${t("reviewRecordedOnly")} ${t("reviewExpandBudgetHint", {count: REVIEW_OPEN_LIMIT})} ${t("reviewPartialStatsHint")}`;
      const operations = summary?.operations || [];
      const root = String(summary?.originRoot || "").replaceAll("\\", "/").replace(/\/$/, "");
      const displayPath = path => {
        const value = String(path || "").replaceAll("\\", "/"), windows = /^[a-z]:/i.test(root) || root.startsWith("//");
        const inside = (windows ? value.toLowerCase() : value).startsWith((windows ? root.toLowerCase() : root) + "/");
        return root && inside ? value.slice(root.length + 1) : value;
      };
      const actionIcon = action => `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true">${action === 'copy' ? '<rect x="5" y="5" width="8" height="9" rx="1"/><path d="M3 11H2V2h8v1"/>' : action === 'open' ? '<path d="M9 2h5v5M14 2 7 9M6 3H2v11h11v-4"/>' : `<path d="${action === 'collapse' ? 'm4 6 4 4 4-4' : 'm6 4 4 4-4 4'}"/>`}</svg>`;
      els.filePreview.innerHTML = `<div class="review-task-heading"><strong>${escapeHtml(t("reviewCardTitle"))}</strong>${summary ? `<span class="review-task-total" aria-describedby="reviewScopeHint" title="${escapeHtml(`${t("reviewOperationTotalsHint")} ${t("reviewPartialStatsHint")}`)}">${reviewStats(operations.filter(op => op.entityKind === "file"), summary.coverage?.complete === false)}</span>` : ''}</div>
        ${!summary ? `<div class="preview-notice" role="status">${escapeHtml(t(review.error ? "reviewUnavailableHint" : "previewLoading"))}</div>` : `<span id="reviewScopeHint" class="sr-only">${escapeHtml(scopeHint)}</span>${!summary.coverage.complete ? `<p class="review-coverage">${escapeHtml(t("reviewIncompleteHint"))}</p>` : ''}
        ${operations.slice(0, 512).map(op => {
          const entry = review.entries.get(op.operationKey), path = displayPath(op.path), slash = path.lastIndexOf('/');
          const kind = `${t(`reviewKind_${op.kind}`)}${op.entityKind === 'directory' ? ` · ${t('reviewDirectory')}` : ''}`;
          const extension = path.slice(slash + 1).split('.').at(-1).toLowerCase();
          const badge = ['js', 'ts', 'css', 'html', 'py', 'json', 'md', 'go'].includes(extension) ? `<span class="review-file-badge" data-extension="${extension}">${escapeHtml(extension.toUpperCase())}</span>` : (options.renderFileIcon?.(op.path) || actionIcon('open'));
          const button = (action, label, icon) => `<button type="button" class="review-row-action" data-review-action="${action}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}"${action === 'toggle' ? ` aria-expanded="${Boolean(entry)}"` : ''}>${actionIcon(icon)}</button>`;
          return `<section class="review-operation-section" data-review-entry="${escapeHtml(op.operationKey)}"><div class="review-operation-row" data-review-row="${escapeHtml(op.operationKey)}"><span class="review-file-icon" title="${escapeHtml(kind)}" role="img" aria-label="${escapeHtml(kind)}">${badge}</span><button type="button" class="review-operation" data-review-operation="${escapeHtml(op.operationKey)}" aria-expanded="${Boolean(entry)}" title="${escapeHtml(op.path)}"><span class="review-operation-parent">${escapeHtml(path.slice(0, slash + 1))}</span><strong class="review-operation-name">${escapeHtml(path.slice(slash + 1))}</strong></button><span class="review-operation-stats">${reviewStats([op])}</span><span class="review-row-actions">${button('copy', t('copyPath'), 'copy')}${button('toggle', t(entry ? 'collapseEditDiff' : 'expandEditDiff'), entry ? 'collapse' : 'expand')}${op.entityKind === 'file' ? button('open', t('previewOpenNewTab'), 'open') : ''}</span></div>${entry ? `<div class="review-detail"${!entry.detail ? ' role="status"' : ''}>${reviewBody(entry)}</div>` : ''}</section>`;
        }).join('')}${!operations.length ? `<p>${escapeHtml(t("reviewNoRecords"))}</p>` : ''}`}`;
      els.filePreview.onclick = event => {
        const row = event.target.closest?.('[data-review-row]');
        if (!row) return;
        const action = event.target.closest?.('[data-review-action]')?.dataset.reviewAction || 'toggle';
        if (action === 'toggle') void selectReviewOperation(row.dataset.reviewRow, {toggle: true});
        else void reviewFileAction(row.dataset.reviewRow, action);
      };
      els.filePreview.onchange = null;
      els.filePreview.scrollTop = review.scroll || 0;
      for (const node of els.filePreview.querySelectorAll("[data-review-entry]")) {
        const body = node.querySelector(".review-detail"), entry = review.entries.get(node.dataset.reviewEntry);
        if (body && entry) (body.querySelector('.diff-lines') || body).scrollLeft = entry.left || 0;
        if (node.dataset.reviewEntry === focusedKey) node.querySelector(focusedAction ? `[data-review-action="${focusedAction}"]` : '[data-review-operation]')?.focus({preventScroll: true});
      }
    }
    async function reviewFileAction(key, action) {
      if (!reviewMode || !review?.summary) return;
      const current = review, summary = current.summary, revision = summary.revision, ownScope = scope, ownEpoch = epoch;
      const operation = summary.operations.find(item => item.operationKey === key), path = operation?.path;
      if (!path || !options.isAbsoluteFilePath?.(path)) return;
      const isCurrent = () => review === current && current.summary === summary && summary.revision === revision
        && scope === ownScope && epoch === ownEpoch && state.sessionId === ownScope.sessionId && workspace?.paneOpen
        && summary.operations.find(item => item.operationKey === key) === operation && operation.path === path;
      if (action === 'copy') {
        let copied = false;
        try { copied = await copyText(path); } catch (_) { /* Existing copy failure feedback. */ }
        if (isCurrent() && reviewMode) showToast(t(copied ? 'pathCopied' : 'copyFailed'), copied ? 'success' : 'warning');
      } else if (action === 'open' && operation.entityKind === 'file') {
        await loadFile(path, undefined, {newTab: true, isCurrent});
      }
    }
    function reviewUrl(id, suffix = "", revision = null) {
      const query = new URLSearchParams({ dataSourceId: scope.dataSourceId, sessionId: scope.sessionId, sessionInstanceId: scope.sessionInstanceId });
      if (revision) query.set("revision", revision);
      return `/api/agent/runs/${encodeURIComponent(id)}/file-changes${suffix}?${query}`;
    }
    async function readReviewSummary(id, {signal} = {}) {
      const currentScope = scope;
      if (!currentScope?.sessionId || !/^[a-f0-9]{32}$/.test(id || "")) throw new Error("review_unavailable");
      const summary = await apiJson(reviewUrl(id), {signal});
      if (scope !== currentScope || summary.rootRunId !== id || summary.sessionId !== currentScope.sessionId
          || summary.dataSourceId !== currentScope.dataSourceId || summary.sessionInstanceId !== currentScope.sessionInstanceId) throw new Error("review_changed");
      return summary;
    }
    function pumpReview() {
      const current = review;
      if (!reviewMode || reviewRequestsPaused || !current?.summary || current.pending || !workspace?.paneOpen) return current?.pending?.promise;
      const waiting = [...current.entries].filter(([, entry]) => !entry.detail && !entry.error && !entry.limited);
      const pair = waiting.find(([, entry]) => entry.priority) || waiting[0];
      if (!pair) return;
      const [key, entry] = pair, ownEpoch = epoch;
      const pending = {key, controller: new AbortController()};
      current.pending = pending;
      pending.promise = (async () => {
        try {
          const detail = await apiJson(reviewUrl(current.id, `/${encodeURIComponent(key)}`, current.summary.revision), {signal: pending.controller.signal});
          if (pending.controller.signal.aborted || review !== current || epoch !== ownEpoch || !reviewMode || current.entries.get(key) !== entry) return;
          const serialized = JSON.stringify(detail), bytes = Math.max(serialized.length * 2, new TextEncoder().encode(serialized).length);
          const lines = detail.bodyState === "diff" ? String(detail.diff || "").split("\n").length : 0;
          const retained = [...current.entries.values()].reduce((sum, item) => ({bytes: sum.bytes + (item.bytes || 0), lines: sum.lines + (item.lines || 0)}), {bytes: 0, lines: 0});
          if (entry.priority) {
            for (const [otherKey, other] of current.entries) {
              if (retained.bytes + bytes <= REVIEW_BYTES && retained.lines + lines <= REVIEW_LINES) break;
              if (otherKey === key) continue;
              retained.bytes -= other.bytes || 0; retained.lines -= other.lines || 0;
              current.entries.delete(otherKey);
              if (!entry.notified) { showToast(t("reviewFocusedCollapsed"), "warning"); entry.notified = true; }
            }
          }
          if (retained.bytes + bytes > REVIEW_BYTES || retained.lines + lines > REVIEW_LINES) entry.limited = true;
          else Object.assign(entry, {detail, bytes, lines, priority: false});
        } catch (_) {
          if (!pending.controller.signal.aborted && review === current && epoch === ownEpoch && current.entries.get(key) === entry) entry.error = true;
        } finally {
          if (current.pending === pending) current.pending = null;
          if (review === current && reviewMode && !reviewRequestsPaused && epoch === ownEpoch) { renderReview(); void pumpReview(); }
        }
      })();
      return pending.promise;
    }
    async function openReview(id, {fileKey, resume = false} = {}) {
      if (!/^[a-f0-9]{32}$/.test(id || "")) return false;
      const intent = ++openIntentSeq, sessionId = state.sessionId;
      const initialization = scope ? null : (restoring || restore());
      const navigation = epoch;
      if (initialization) await initialization;
      if (intent !== openIntentSeq || sessionId !== state.sessionId || scope?.sessionId !== sessionId || !scope?.sessionId || navigation !== epoch) return false;
      saveView(); clearRenderer(false);
      leaveBlank();
      reviewMode = true;
      reviewRequestsPaused = false;
      if (review?.id !== id) review = {id, summary: null, entries: new Map(), scroll: 0};
      const current = review, ownEpoch = epoch;
      workspace.paneOpen = true;
      touchView(REVIEW_TAB);
      els.workbench.classList.add("preview-open");
      // Rendering a cached review is synchronous; switching tabs does not refetch.
      renderReview();
      els.filePreview.scrollTop = current.scroll || 0;
      if (!current.summary) {
        current.error = false;
        const controller = new AbortController(); current.summaryRequest = controller;
        try {
          const summary = await readReviewSummary(id, {signal: controller.signal});
          if (controller.signal.aborted || review !== current || epoch !== ownEpoch || !reviewMode) return false;
          if (!Array.isArray(summary.operations) || summary.operations.length > 512) throw new Error("review_limit");
          current.summary = summary;
        } catch (_) {
          if (controller.signal.aborted || review !== current || epoch !== ownEpoch || !reviewMode) return false;
          current.error = true;
        } finally { if (current.summaryRequest === controller) current.summaryRequest = null; }
        renderReview();
        const selected = fileKey ? current.summary?.operations.filter(op => op.fileKey === fileKey).at(-1) : current.summary?.operations[0];
        if (selected) await selectReviewOperation(selected.operationKey, {scroll: Boolean(fileKey)});
      } else if (fileKey) {
        const selected = current.summary.operations.filter(op => op.fileKey === fileKey).at(-1);
        if (selected) await selectReviewOperation(selected.operationKey, {scroll: true});
      } else void pumpReview();
      return true;
    }
    async function selectReviewOperation(key, {toggle = false, scroll = false} = {}) {
      if (!reviewMode || !review?.summary?.operations.some(item => item.operationKey === key)) return;
      reviewRequestsPaused = false;
      saveReviewView();
      if (toggle && review.entries.has(key)) {
        review.entries.delete(key);
        if (review.pending?.key === key) review.pending.controller.abort();
      } else {
        if (!review.entries.has(key)) {
          if (review.entries.size >= REVIEW_OPEN_LIMIT) {
            if (!scroll) { showToast(t("reviewDisplayLimit"), "warning"); return; }
            review.entries.delete(review.entries.keys().next().value);
            showToast(t("reviewFocusedCollapsed"), "warning");
          }
          review.entries.set(key, {});
        }
        if (scroll) {
          const entry = review.entries.get(key);
          Object.assign(entry, {priority: !entry.detail, limited: false, error: false});
          if (review.pending && review.pending.key !== key) review.pending.controller.abort();
        }
      }
      renderReview();
      if (scroll) [...els.filePreview.querySelectorAll("[data-review-entry]")].find(node => node.dataset.reviewEntry === key)?.scrollIntoView({block: "start"});
      return pumpReview();
    }
    function closeReview() {
      const wasActive = reviewMode;
      stopReviewRequests(); review = null; viewMru = viewMru.filter(id => id !== REVIEW_TAB);
      if (wasActive) {
        reviewMode = false;
        const nextView = viewMru.find(id => blankState?.tabs.some(tab => tab.id === id) || workspace?.tabs.some(tab => tab.id === id));
        if (blankState?.tabs.some(tab => tab.id === nextView)) void activateBlank(nextView);
        else if (activeTab()) void activate(nextView || workspace.active);
        else close();
      }
      renderTabs();
      if (wasActive) tabsElement?.querySelector('[aria-selected="true"]')?.focus({preventScroll: true});
    }
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
    const tabListToggle = documentRef.getElementById?.("previewTabListToggle");
    const tabListMenu = documentRef.getElementById?.("previewTabListMenu");
    const newTabButton = documentRef.getElementById?.("previewNewTab");
    let tabMenuState = null, tabResizeObserver = null;
    const keyOf = (ctx) => `${ctx.dataSourceId}:${ctx.sessionId || "draft"}:${ctx.sessionInstanceId}`;
    const activeTab = () => workspace?.tabs.find((tab) => tab.id === workspace.active);
    const activeBlank = () => blankState?.tabs.find(tab => tab.id === activeBlankId);
    const activeViewId = () => activeBlankId || (reviewMode ? REVIEW_TAB : workspace?.active);
    const slotCount = () => (workspace?.tabs.length || 0) + (blankState?.tabs.length || 0);
    const emptyWorkspace = () => ({ tabs: [], active: null, mru: [], reuse: null, paneOpen: false });
    function warn(key, onceKey = key) {
      if (!warned.has(onceKey)) { warned.add(onceKey); showToast(t(key), "warning"); }
    }
    function validatePickerData(data, path, query) {
      if (data.dataSourceId !== scope.dataSourceId || data.sessionId !== scope.sessionId || data.sessionInstanceId !== scope.sessionInstanceId
          || data.contextRevision !== scope.contextRevision || data.root !== scope.root || data.path !== path || data.query !== query
          || !Array.isArray(data.items) || data.items.length > 200
          || data.items.some(item => !["file", "dir"].includes(item.type) || typeof item.name !== "string" || item.name.length > 4096
            || typeof item.path !== "string" || item.path.length > 4096 || !options.isAbsoluteFilePath?.(item.absolutePath)
            || item.absolutePath.length > 32768 || (item.type === "file" && !/^[a-f0-9]{64}$/.test(item.fileKey || "")))) throw new Error("picker_identity");
    }
    function treeFits(tab, path, replacement) {
      let nodes = 0, bytes = 0;
      const count = node => { nodes += 1 + (node.items?.length || 0); bytes += 256 + node.path.length * 2 + (node.bytes || 0); };
      for (const record of blankSessions.values()) for (const item of record.tabs) {
        for (const node of item.tree?.values() || []) count(item === tab && node.path === path ? replacement : node);
        if (item === tab && !item.tree.has(path)) count(replacement);
      }
      return nodes <= TREE_NODES && bytes <= TREE_BYTES;
    }
    function treeVisible(tab, path) {
      if (!path) return true;
      const parts = path.split('/');
      for (let i = 0; i < parts.length; i++) if (!tab.tree.get(parts.slice(0, i).join('/'))?.expanded) return false;
      return true;
    }
    function stopTreeRequests(tab, path = null) {
      if (!tab?.tree) return;
      for (const node of tab.tree.values()) {
        if (path !== null && node.path !== path && !node.path.startsWith(path ? `${path}/` : '')) continue;
        if (node.job) { global.clearTimeout(node.job.timeout); node.job.controller.abort(); }
        node.job = null; node.loading = false;
      }
      for (let i = treeQueue.length - 1; i >= 0; i--) if (treeQueue[i].node.job !== treeQueue[i]) treeQueue.splice(i, 1);
    }
    function pumpTree() {
      while (treeRequests < TREE_CONCURRENCY && treeQueue.length) {
        const job = treeQueue.shift();
        if (!job.current()) continue;
        treeRequests += 1;
        void job.run().finally(() => { treeRequests -= 1; pumpTree(); });
      }
    }
    function loadTreeNode(tab, node) {
      if (node.job || !node.expanded || !treeVisible(tab, node.path)) return;
      if (treeQueue.length >= TREE_QUEUE) { node.error = "previewTreeQueueLimit"; renderBlank(); return; }
      const controller = new AbortController(), ownScope = scope, ownEpoch = epoch;
      const job = {tab, node, controller, current: () => scope === ownScope && epoch === ownEpoch && activeBlank() === tab
        && workspace?.paneOpen && !tab.query.trim() && node.job === job && node.expanded && treeVisible(tab, node.path)};
      node.job = job; node.loading = true; node.error = "";
      job.run = async () => {
        try {
          const data = await apiJson(`/api/preview/files?${new URLSearchParams({...ownScope, path: node.path, q: ""})}`, {signal: controller.signal});
          if (!job.current() || controller.signal.aborted) return;
          validatePickerData(data, node.path, "");
          const encoded = JSON.stringify(data.items), bytes = Math.max(encoded.length * 2, new TextEncoder().encode(encoded).length);
          const next = {...node, items: data.items, bytes, limited: data.limited === true};
          if (!treeFits(tab, node.path, next)) { node.error = "previewTreeLimit"; return; }
          node.items = next.items; node.bytes = bytes; node.limited = next.limited;
        } catch (_) {
          if (job.current() && !controller.signal.aborted) node.error = "previewPickerFailed";
        } finally {
          global.clearTimeout(job.timeout);
          if (job.current()) { node.job = null; node.loading = false; renderBlank(); }
        }
      };
      job.timeout = global.setTimeout(() => {
        if (!job.current()) return;
        node.error = 'previewPickerFailed'; node.job = null; node.loading = false; controller.abort();
        const queued = treeQueue.indexOf(job); if (queued >= 0) treeQueue.splice(queued, 1);
        renderBlank();
      }, 5000);
      treeQueue.push(job); pumpTree();
    }
    function resumeTree(tab) {
      if (!tab.tree.has('')) {
        const root = {path: '', expanded: true, items: null};
        if (!treeFits(tab, '', root)) { tab.error = 'previewTreeLimit'; return; }
        tab.tree.set('', root);
      }
      for (const node of tab.tree.values()) if (node.expanded && treeVisible(tab, node.path) && node.items === null && !node.error) loadTreeNode(tab, node);
    }
    function toggleTreeNode(tab, entry) {
      let node = tab.tree.get(entry.path);
      if (!node) {
        node = {path: entry.path, expanded: false, items: null};
        if (!treeFits(tab, entry.path, node)) { tab.error = 'previewTreeLimit'; renderBlank(); return; }
        tab.tree.set(entry.path, node);
      }
      node.expanded = !node.expanded; tab.error = '';
      if (node.expanded) loadTreeNode(tab, node);
      else {
        stopTreeRequests(tab, node.path);
        node.items = null; node.bytes = 0; node.error = ''; node.limited = false;
        for (const path of tab.tree.keys()) if (path !== node.path && path.startsWith(node.path ? `${node.path}/` : '')) tab.tree.delete(path);
      }
      renderBlank();
    }
    function saveBlankScroll(tab) {
      if (tab && els.filePreview.dataset.blankView === tab.id) {
        const scroller = els.filePreview.querySelector('.preview-picker-results') || els.filePreview;
        tab.scrolls[els.filePreview.dataset.pickerMode || 'tree'] = Math.max(0, scroller.scrollTop || 0);
      }
    }
    function stopBlankSearch(tab = activeBlank()) {
      if (!tab) return;
      stopTreeRequests(tab);
      global.clearTimeout(tab.timer); tab.timer = null;
      tab.controller?.abort(); tab.openController?.abort();
      tab.controller = null; tab.openController = null;
      tab.loading = false; tab.opening = false; tab.entries = [];
    }
    function leaveBlank() {
      stopBlankSearch();
      if (blankState) blankState.active = null;
      activeBlankId = null;
    }
    function restoreBlankState() {
      blankState = blankSessions.get(keyOf(scope)) || null;
      if (blankState && blankState.context !== `${scope.serverInstanceId}:${scope.contextRevision}`) {
        blankSessions.delete(keyOf(scope)); blankState = null;
      }
      activeBlankId = blankState?.active || null;
      viewMru = (blankState?.mru || workspace.mru || []).filter(id => workspace.tabs.some(tab => tab.id === id) || blankState?.tabs.some(tab => tab.id === id));
    }
    async function createBlank() {
      const expectedSession = state.sessionId;
      const expectedEpoch = epoch + (!scope && !restoring ? 1 : 0);
      if (!scope) await (restoring || restore());
      if (!scope || !workspace || epoch !== expectedEpoch || state.sessionId !== expectedSession) return false;
      if (slotCount() >= 20) { showToast(t("previewTabLimit"), "warning"); return false; }
      if (!blankState) {
        if (blankSessions.size >= 50) { showToast(t("previewBlankMemoryLimit"), "warning"); return false; }
        blankState = {context: `${scope.serverInstanceId}:${scope.contextRevision}`, tabs: [], active: null, mru: []};
        blankSessions.set(keyOf(scope), blankState);
      }
      const order = Math.max((workspace.orderCounter || 0) + 1, orderBase + ++openIntentSeq);
      workspace.orderCounter = order;
      const tab = {id: uid(), order, query: "", tree: new Map(), scrolls: {tree: 0, search: 0}, entries: [], error: "", loading: false};
      blankState.tabs.push(tab);
      await activateBlank(tab.id, true);
      return true;
    }
    async function activateBlank(id, focus = false) {
      const tab = blankState?.tabs.find(item => item.id === id);
      if (!scope || !workspace || !tab) return false;
      saveView(); clearRenderer(false); reviewMode = false;
      activeBlankId = id; blankState.active = id;
      workspace.paneOpen = true; els.workbench.classList.add("preview-open");
      touchView(id); applyPreviewWidth(state.previewWidth, false); renderBlank({focus}); renderTabs(); persist();
      return searchBlank(tab);
    }
    function closeBlank(id) {
      const tab = blankState?.tabs.find(item => item.id === id);
      if (!tab) return;
      const wasActive = activeBlankId === id;
      stopBlankSearch(tab); blankState.tabs = blankState.tabs.filter(item => item !== tab);
      viewMru = viewMru.filter(value => value !== id);
      if (wasActive) { activeBlankId = null; blankState.active = null; }
      if (!blankState.tabs.length) { blankSessions.delete(keyOf(scope)); blankState = null; }
      if (wasActive) {
        const next = viewMru.find(value => tabDescriptions().some(item => item.id === value)) || tabDescriptions()[0]?.id;
        if (next) void activateView(next); else close();
      }
      renderTabs(); persist();
      if (wasActive && workspace?.paneOpen) tabsElement?.querySelector('[aria-selected="true"]')?.focus({preventScroll: true});
    }
    async function searchBlank(tab = activeBlank()) {
      if (!tab || tab !== activeBlank() || !scope || !workspace?.paneOpen) return;
      stopBlankSearch(tab); tab.error = "";
      if (!tab.query.trim()) { resumeTree(tab); renderBlank(); return; }
      tab.loading = true;
      const controller = new AbortController(), ownScope = scope, ownEpoch = epoch;
      tab.controller = controller;
      const requestedPath = "", requestedQuery = tab.query.trim();
      const current = () => scope === ownScope && epoch === ownEpoch && activeBlank() === tab && workspace?.paneOpen && tab.controller === controller;
      let timedOut = false;
      const timeout = global.setTimeout(() => { timedOut = true; controller.abort(); }, 5000);
      renderBlank();
      try {
        const query = new URLSearchParams({...scope, path: requestedPath, q: requestedQuery});
        const data = await apiJson(`/api/preview/files?${query}`, {signal: controller.signal});
        if (!current() || controller.signal.aborted) return;
        validatePickerData(data, requestedPath, requestedQuery);
        tab.entries = data.items; tab.limited = data.limited === true;
      } catch (_) {
        if (current() && (!controller.signal.aborted || timedOut)) tab.error = "previewPickerFailed";
      } finally {
        global.clearTimeout(timeout);
        if (current()) { tab.controller = null; tab.loading = false; renderBlank(); }
      }
    }
    function renderBlank({focus = false, reset = false} = {}) {
      const tab = activeBlank();
      if (!tab) return;
      saveBlankScroll(tab);
      const oldInput = els.filePreview.querySelector('[data-picker-query]');
      const hadFocus = oldInput && documentRef.activeElement === oldInput, selection = oldInput?.selectionStart;
      const focusedPath = documentRef.activeElement?.dataset?.pickerPath;
      const focusedRetry = documentRef.activeElement?.dataset?.pickerRetryPath;
      els.refreshPreview.disabled = true; els.copyPreview.disabled = true; renderModeActions([]); setPreviewStatus();
      if (reset || els.filePreview.dataset.blankView !== tab.id || !oldInput) {
        els.filePreview.className = "file-preview preview-picker"; els.filePreview.dataset.blankView = tab.id;
        els.filePreview.innerHTML = `<div class="preview-picker-heading"><h2>${escapeHtml(t("previewNewTab"))}</h2><p>${escapeHtml(t("previewPickerHint"))}</p></div><input data-picker-query type="search" maxlength="128" autocomplete="off" spellcheck="false" aria-label="${escapeHtml(t("previewPickerSearch"))}" placeholder="${escapeHtml(t("previewPickerSearch"))}"><div class="preview-picker-status" role="status"></div><div class="preview-picker-results"></div>`;
      }
      const searching = Boolean(tab.query.trim()), mode = searching ? 'search' : 'tree';
      els.filePreview.dataset.pickerMode = mode;
      const input = els.filePreview.querySelector('[data-picker-query]');
      if (input.value !== tab.query) input.value = tab.query;
      const rows = [], rootName = scope.root.replace(/[\\/]$/, '').split(/[\\/]/).pop() || scope.root;
      const addTree = (entry, depth) => {
        const node = tab.tree.get(entry.path);
        rows.push({entry, depth, node});
        if (node?.expanded) for (const child of node.items || []) addTree(child, depth + 1);
      };
      if (searching) tab.entries.forEach(entry => rows.push({entry, depth: 0}));
      else addTree({path: '', name: rootName, absolutePath: scope.root, type: 'dir'}, 0);
      const status = els.filePreview.querySelector('.preview-picker-status');
      status.innerHTML = tab.loading || tab.opening ? `${escapeHtml(t("previewLoading"))}<button type="button" data-picker-action="cancel">${escapeHtml(t("previewPickerCancel"))}</button>`
        : tab.error ? `${escapeHtml(t(tab.error))}<button type="button" data-picker-action="retry">${escapeHtml(t("previewPickerRetry"))}</button>`
        : searching && tab.limited ? escapeHtml(t("previewPickerLimited")) : '';
      const results = els.filePreview.querySelector('.preview-picker-results');
      results.classList?.toggle('preview-picker-tree', !searching);
      if (searching) results.removeAttribute?.('role'); else results.setAttribute?.('role', 'tree');
      results.innerHTML = rows.map(({entry, depth, node}, index) => {
        const directory = entry.type === 'dir', expanded = directory && node?.expanded;
        const treeAttrs = searching ? '' : ` role="treeitem" aria-level="${depth + 1}"${directory ? ` aria-expanded="${Boolean(expanded)}" aria-busy="${Boolean(node?.loading)}"${node?.loading ? ` aria-label="${escapeHtml(entry.name + ' · ' + t('previewLoading'))}"` : ''}` : ''} tabindex="${entry.path === (tab.treeFocus || '') ? 0 : -1}" data-picker-path="${escapeHtml(entry.path)}" style="padding-left:${7 + Math.min(depth, 12) * 14}px"`;
        const indicator = expanded ? '▾' : '▸';
        const row = `<button type="button" class="preview-picker-item" data-picker-index="${index}"${treeAttrs}${tab.opening ? ' disabled' : ''} title="${escapeHtml(entry.absolutePath)}"><span aria-hidden="true"${directory ? ' class="preview-tree-toggle"' : ''}>${directory ? indicator : (options.renderFileIcon?.(entry.absolutePath) || '·')}</span><span><strong>${escapeHtml(entry.name)}</strong>${searching ? `<small>${escapeHtml(entry.path)}</small>` : ''}</span></button>`;
        const message = expanded && !node.loading && (node.error || (node.limited ? 'previewPickerLimited' : node.items?.length === 0 ? 'previewPickerEmpty' : ''));
        return row + (message ? `<div class="preview-tree-status" role="status">${escapeHtml(t(message))}${node.error || node.limited ? `<button type="button" data-picker-retry-path="${escapeHtml(entry.path)}">${escapeHtml(t('previewPickerRetry'))}</button>` : ''}</div>` : '');
      }).join('') || (!tab.loading && !tab.opening && !tab.error ? `<p>${escapeHtml(t("previewPickerEmpty"))}</p>` : '');
      const focusRow = (path, reveal = false) => {
        const button = [...els.filePreview.querySelectorAll('[data-picker-path]')].find(row => row.dataset.pickerPath === path);
        if (button) { tab.treeFocus = path; button.tabIndex = 0; button.focus({preventScroll: true}); if (reveal) button.scrollIntoView({block: 'nearest'}); }
      };
      els.filePreview.onfocusin = event => {
        const row = event.target.closest?.('[data-picker-path]');
        if (!row) return;
        tab.treeFocus = row.dataset.pickerPath;
        for (const button of els.filePreview.querySelectorAll('[data-picker-path]')) button.tabIndex = button === row ? 0 : -1;
      };
      input.oninput = () => {
        if (activeBlank() !== tab) return;
        saveBlankScroll(tab); stopBlankSearch(tab); tab.query = input.value; tab.error = ''; tab.limited = false; renderBlank();
        if (!tab.query.trim()) void searchBlank(tab);
        else tab.timer = global.setTimeout(() => { tab.timer = null; void searchBlank(tab); }, 250);
      };
      const cancel = () => { stopBlankSearch(tab); tab.error = 'previewPickerCancelled'; renderBlank({focus: true}); };
      input.onkeydown = event => {
        if (event.key === 'Enter') { event.preventDefault(); void searchBlank(tab); }
        if (event.key === 'ArrowDown') { event.preventDefault(); els.filePreview.querySelector('[data-picker-index]')?.focus(); }
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); cancel(); }
      };
      els.filePreview.onkeydown = event => {
        const row = event.target.closest?.('[data-picker-index]'), item = row && rows[Number(row.dataset.pickerIndex)];
        if (!item || !['ArrowDown', 'ArrowUp', 'ArrowRight', 'ArrowLeft', 'Home', 'End', 'Escape'].includes(event.key)) return;
        event.preventDefault();
        if (event.key === 'Escape') { event.stopPropagation(); cancel(); return; }
        if (!searching && ['ArrowRight', 'ArrowLeft'].includes(event.key)) {
          if (event.key === 'ArrowRight') {
            if (item.entry.type === 'dir' && !item.node?.expanded) toggleTreeNode(tab, item.entry);
            else if (item.node?.items?.length) focusRow(item.node.items[0].path, true);
          } else if (item.node?.expanded) toggleTreeNode(tab, item.entry);
          else focusRow(item.entry.path.split('/').slice(0, -1).join('/'), true);
          return;
        }
        const buttons = [...els.filePreview.querySelectorAll('[data-picker-index]')], index = buttons.indexOf(row);
        const next = buttons[event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : Math.max(0, Math.min(buttons.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)))];
        next?.focus(); if (!searching && next) tab.treeFocus = next.dataset.pickerPath;
      };
      els.filePreview.onclick = event => {
        if (activeBlank() !== tab) return;
        const action = event.target.closest?.('[data-picker-action]')?.dataset.pickerAction;
        if (action) {
          if (action === 'cancel') cancel();
          else {
            if (!searching && tab.error === 'previewPickerOpenFailed') {
              const parent = tab.tree.get(tab.fileParent || '');
              if (parent) { parent.items = null; parent.bytes = 0; parent.error = ''; }
            }
            void searchBlank(tab);
          }
          return;
        }
        const retry = event.target.closest?.('[data-picker-retry-path]');
        if (retry) { const node = tab.tree.get(retry.dataset.pickerRetryPath); if (node) { loadTreeNode(tab, node); renderBlank(); } return; }
        const row = event.target.closest?.('[data-picker-index]'), item = row && rows[Number(row.dataset.pickerIndex)];
        if (!item || tab.opening) return;
        if (item.entry.type === 'dir') { tab.treeFocus = item.entry.path; toggleTreeNode(tab, item.entry); }
        else {
          tab.fileParent = item.entry.path.split('/').slice(0, -1).join('/');
          void loadFile(item.entry.absolutePath, undefined, {newTab: true, blankTarget: tab, expectedFileKey: item.entry.fileKey});
        }
      };
      if (focus || hadFocus) { input.focus({preventScroll: true}); if (selection != null) input.setSelectionRange?.(selection, selection); }
      else if (!searching && (focusedPath ?? focusedRetry) !== undefined) focusRow(focusedPath ?? focusedRetry);
      results.scrollTop = tab.scrolls[mode];
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
      if (activeBlankId) { saveBlankScroll(activeBlank()); return; }
      if (reviewMode) { saveReviewView(); return; }
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
      stopBlankSearch();
      if (els.filePreview.dataset) delete els.filePreview.dataset.blankView;
      els.filePreview.onkeydown = null;
      els.filePreview.onfocusin = null;
      stopReviewRequests();
      if (els.filePreview.dataset) delete els.filePreview.dataset.reviewView;
      setPreviewStatus();
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
      els.filePreview.onchange = null;
      if (empty) renderNotice(t("noFileOpen"), t("selectFileToPreview"));
      else { els.filePreview.innerHTML = ""; renderModeActions([]); }
    }
    function setPreviewStatus(text = "") {
      const status = documentRef.getElementById?.("previewStatus");
      if (status) { status.textContent = text; status.hidden = !text; }
    }
    function renderLoading(tab) {
      if (els.previewTitle) els.previewTitle.textContent = tab.name || tab.path.split(/[\\/]/).pop();
      if (els.previewMeta) els.previewMeta.textContent = t("previewLoading");
      if (els.previewLanguage) els.previewLanguage.textContent = "";
      els.filePreview.className = "file-preview loading";
      els.filePreview.innerHTML = `<div class="preview-notice" role="status"><span>${escapeHtml(t("previewLoading"))}</span></div>`;
      els.refreshPreview.disabled = true;
      els.copyPreview.disabled = true;
    }
    function beginNavigation() {
      closeTabMenu(false); revealTabId = null;
      saveView();
      if (blankState) blankState.mru = [...viewMru];
      stopBlankSearch(); blankState = null; activeBlankId = null;
      persist();
      const token = { epoch: ++epoch, draft: scope && !scope.sessionId ? clone(workspace) : null,
        sourceId: scope?.dataSourceId };
      gesture = null;
      closedFiles.clear();
      clearCached();
      stopReviewRequests();
      review = null; reviewMode = false; viewMru = []; syncReviewModes();
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
    function tabDescriptions() {
      const files = workspace?.tabs || [], blanks = blankState?.tabs || [];
      const list = [...files, ...blanks.map((tab, index) => ({id: tab.id, order: tab.order, isBlank: true,
        name: blanks.length > 1 ? t("previewNewTabNumber", {number: index + 1}) : t("previewNewTab")}))].sort((a, b) => a.order - b.order);
      if (review) list.push({id: REVIEW_TAB, name: t("reviewInspect")});
      const nameOf = tab => tab.name || tab.path.split(/[\\/]/).pop();
      return list.map(tab => {
        const isReview = tab.id === REVIEW_TAB;
        const name = nameOf(tab);
        let parent = "";
        const sameNames = !isReview && !tab.isBlank ? files.filter(item => nameOf(item) === name) : [];
        if (sameNames.length > 1) {
          const parents = value => value.path.replaceAll("\\", "/").split("/").slice(0, -1);
          const parts = parents(tab);
          let depth = 1;
          while (depth < parts.length && sameNames.some(item => item !== tab
            && parents(item).slice(-depth).join("/") === parts.slice(-depth).join("/"))) depth += 1;
          parent = parts.slice(-depth).join("/") || "/";
        }
        return {...tab, name, parent, label: name + (parent ? ` · ${parent}` : ""), isReview};
      });
    }
    function activateView(id) {
      if (id === REVIEW_TAB) { if (review) return openReview(review.id, {resume: true}); }
      else if (blankState?.tabs.some(tab => tab.id === id)) return activateBlank(id);
      else if (workspace?.tabs.some(tab => tab.id === id)) return activate(id);
    }
    const closeView = id => id === REVIEW_TAB ? closeReview() : blankState?.tabs.some(tab => tab.id === id) ? closeBlank(id) : closeTab(id);
    function closeTabMenu(returnFocus = false) {
      if (!tabMenuState) return;
      tabMenuState = null;
      tabListMenu.hidden = true;
      tabListMenu.replaceChildren();
      tabListToggle.setAttribute("aria-expanded", "false");
      if (returnFocus) (tabListToggle.hidden ? tabsElement.querySelector('[aria-selected="true"]') : tabListToggle)?.focus({preventScroll: true});
    }
    function syncTabMenu() {
      const token = tabMenuState;
      if (!token) return;
      const list = tabDescriptions();
      if (scope !== token.scope || epoch !== token.epoch || !workspace?.paneOpen || (state.sessionId || "") !== (scope?.sessionId || "")) { closeTabMenu(false); return; }
      if ((token.review && token.review !== review) || token.ids.some(id => !list.some(tab => tab.id === id))) { closeTabMenu(tabListMenu.contains(documentRef.activeElement)); return; }
      token.review = review;
      const signature = JSON.stringify(list.map(tab => [tab.id, tab.name, tab.path, tab.parent]));
      const active = activeViewId();
      if (signature !== token.signature) {
        const focused = tabListMenu.contains(documentRef.activeElement) ? documentRef.activeElement.dataset.previewMenuTab : null;
        const top = tabListMenu.scrollTop;
        tabListMenu.replaceChildren();
        for (const tab of list) {
          const button = documentRef.createElement("button");
          button.type = "button"; button.dataset.previewMenuTab = tab.id;
          button.setAttribute("role", "menuitemradio");
          button.title = tab.path || tab.name;
          button.setAttribute("aria-label", tab.path || tab.name);
          button.innerHTML = `<span class="preview-menu-check" aria-hidden="true">✓</span><span class="preview-menu-description"><strong>${escapeHtml(tab.name)}</strong>${tab.path ? `<span>${escapeHtml(tab.path)}</span>` : ''}</span>`;
          button.addEventListener("click", () => {
            const target = tabDescriptions().find(item => item.id === tab.id);
            if (tabMenuState !== token || scope !== token.scope || epoch !== token.epoch || (state.sessionId || "") !== (scope?.sessionId || "")
                || !workspace?.paneOpen || !target || target.path !== tab.path || (tab.isReview && review !== token.review)) { closeTabMenu(false); return; }
            closeTabMenu(false); gesture = null; void activateView(tab.id);
            tabsElement.querySelector('[aria-selected="true"]')?.focus({preventScroll: true});
          });
          tabListMenu.appendChild(button);
        }
        token.ids = list.map(tab => tab.id); token.signature = signature;
        if (focused) [...tabListMenu.children].find(button => button.dataset.previewMenuTab === focused)?.focus({preventScroll: true});
        tabListMenu.scrollTop = top;
      }
      for (const button of tabListMenu.children) {
        const selected = button.dataset.previewMenuTab === active;
        button.setAttribute("aria-checked", String(selected)); button.tabIndex = selected ? 0 : -1;
      }
    }
    function openTabMenu(position = "active") {
      if (!tabListToggle || tabListToggle.hidden || !scope || !workspace?.paneOpen) return;
      tabMenuState = {scope, epoch, review, ids: [], signature: ""};
      tabListMenu.hidden = false; tabListToggle.setAttribute("aria-expanded", "true"); syncTabMenu();
      if (!tabMenuState) return;
      const buttons = [...tabListMenu.children];
      (position === "first" ? buttons[0] : position === "last" ? buttons.at(-1) : buttons.find(button => button.getAttribute("aria-checked") === "true") || buttons[0])?.focus({preventScroll: true});
      revealMenuItem(documentRef.activeElement);
    }
    function revealMenuItem(button) {
      if (!button || !tabListMenu.contains(button)) return;
      const bounds = tabListMenu.getBoundingClientRect(), box = button.getBoundingClientRect();
      if (box.top < bounds.top) tabListMenu.scrollTop += box.top - bounds.top;
      else if (box.bottom > bounds.bottom) tabListMenu.scrollTop += box.bottom - bounds.bottom;
    }
    function syncTabOverflow() {
      if (!tabsElement || !tabListToggle) return;
      // Measure once with the trigger absent so its own width cannot perpetuate overflow.
      const left = tabsElement.scrollLeft;
      tabListToggle.hidden = true;
      const overflow = tabsElement.scrollWidth > tabsElement.clientWidth + 1;
      tabListToggle.hidden = !overflow;
      tabsElement.scrollLeft = left;
      if (!overflow && tabMenuState) closeTabMenu(tabListMenu.contains(documentRef.activeElement));
    }
    function revealTab(id) {
      const item = [...tabsElement.children].find(node => node.querySelector('[data-preview-tab]')?.dataset.previewTab === id);
      if (!item) return;
      const bounds = tabsElement.getBoundingClientRect(), box = item.getBoundingClientRect();
      if (box.left < bounds.left) tabsElement.scrollLeft += box.left - bounds.left;
      else if (box.right > bounds.right) tabsElement.scrollLeft += box.right - bounds.right;
    }
    function renderTabs() {
      if (!tabsElement) return;
      const focusedItem = tabsElement.contains(documentRef.activeElement) ? documentRef.activeElement.closest('.preview-tab') : null;
      const focusedTab = focusedItem?.querySelector('[data-preview-tab]')?.dataset.previewTab;
      const focusedClose = documentRef.activeElement?.classList?.contains('preview-tab-close');
      const left = tabsElement.scrollLeft;
      tabsElement.replaceChildren();
      const list = tabDescriptions(), active = activeViewId();
      for (const tab of list) {
        const {isReview, isBlank, label, name, parent} = tab;
        const extensionMatch = !isReview && !isBlank && name.match(/\.(?:d\.(?:ts|mts|cts)|tar\.(?:gz|bz2|xz|zst)|[^.]+)$/i);
        const extension = extensionMatch && extensionMatch.index > 0 ? extensionMatch[0] : "", stem = name.slice(0, name.length - extension.length);
        const item = documentRef.createElement("div");
        item.className = `preview-tab${isReview ? ' is-review' : ''}${tab.id === active ? " active" : ""}`;
        if (!isReview) item.style.minWidth = `${Math.min(192, Math.max(112, 76 + extension.length * 7 + (parent ? 32 : 0)))}px`;
        const button = documentRef.createElement("button");
        button.type = "button";
        button.dataset.previewTab = tab.id;
        button.innerHTML = `${!isReview && !isBlank && options.renderFileIcon ? `<span class="preview-tab-icon" aria-hidden="true">${options.renderFileIcon(tab.path)}</span>` : ''}<span class="preview-tab-name"><span class="preview-tab-basename"><span class="preview-tab-stem">${escapeHtml(stem)}</span>${extension ? `<span class="preview-tab-extension">${escapeHtml(extension)}</span>` : ''}</span>${parent ? `<span class="preview-tab-parent"> · ${escapeHtml(parent)}</span>` : ''}</span>`;
        button.title = isReview ? t("reviewInspect") : isBlank ? name : tab.path;
        button.setAttribute("aria-label", button.title);
        button.setAttribute("role", "tab");
        button.setAttribute("aria-selected", String(tab.id === active));
        button.tabIndex = tab.id === active ? 0 : -1;
        button.addEventListener("click", () => { gesture = null; void activateView(tab.id); });
        button.addEventListener("keydown", (event) => {
          if (event.key === "Delete") { event.preventDefault(); closeView(tab.id); return; }
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          let index = list.indexOf(tab);
          index = event.key === "Home" ? 0 : event.key === "End" ? list.length - 1
            : (index + (event.key === "ArrowRight" ? 1 : -1) + list.length) % list.length;
          void activateView(list[index].id);
          tabsElement.querySelector('[aria-selected="true"]')?.focus({preventScroll: true});
        });
        const closeButton = documentRef.createElement("button");
        closeButton.type = "button";
        closeButton.className = "preview-tab-close";
        closeButton.textContent = "×";
        closeButton.setAttribute("aria-label", t("previewCloseTab", { name: label }));
        closeButton.addEventListener("click", () => closeView(tab.id));
        item.append(button, closeButton);
        tabsElement.appendChild(item);
      }
      syncTabOverflow(); tabsElement.scrollLeft = left;
      if (focusedTab) {
        const button = [...tabsElement.querySelectorAll("[data-preview-tab]")].find(node => node.dataset.previewTab === focusedTab);
        (focusedClose ? button?.parentElement.querySelector('.preview-tab-close') : button)?.focus({preventScroll: true});
      }
      if (revealTabId) { revealTab(revealTabId); revealTabId = null; }
      syncTabMenu();
    }
    function fileUrl(path, tab = null, raw = false) {
      const query = new URLSearchParams({ ...scope, path });
      if (tab) query.set("fileKey", tab.fileKey);
      if (raw) { query.set("raw", "1"); query.set("v", state._previewMtime || ""); }
      return `/api/preview/file?${query}`;
    }
    function current(token, tab) {
      return !activeBlankId && !reviewMode && token.epoch === epoch && token.seq === requestSeq && scope
        && token.scopeKey === keyOf(scope) && activeTab() === tab && workspace.paneOpen;
    }
    async function readActive({ line, refresh = false } = {}) {
      const tab = activeTab();
      if (!scope || !tab || !workspace.paneOpen || activeBlankId || reviewMode) return;
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
      leaveBlank();
      reviewMode = false; syncReviewModes();
      clearRenderer(false);
      workspace.active = id;
      touchView(id);
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
      const wasActive = !reviewMode && !activeBlankId && workspace.active === id;
      viewMru = viewMru.filter(value => value !== id);
      const closing = workspace.tabs.find((tab) => tab.id === id);
      if (closing) { closedFiles.set(closing.fileKey, ++openIntentSeq); dropCached(closing.fileKey); }
      workspace.tabs = workspace.tabs.filter((tab) => tab.id !== id);
      workspace.mru = workspace.mru.filter((value) => value !== id);
      if (workspace.reuse === id) workspace.reuse = null;
      if (wasActive) {
        const nextView = viewMru.find(value => value === REVIEW_TAB ? Boolean(review) : workspace.tabs.some(tab => tab.id === value) || blankState?.tabs.some(tab => tab.id === value));
        const next = workspace.mru.find((value) => workspace.tabs.some((tab) => tab.id === value)) || workspace.tabs[0]?.id;
        if (nextView === REVIEW_TAB) { clearRenderer(false); workspace.active = next || null; void openReview(review.id, {resume: true}); }
        else if (blankState?.tabs.some(tab => tab.id === nextView)) { workspace.active = next || null; void activateBlank(nextView); }
        else if (next) activate(next);
        else if (blankState?.tabs.length) { workspace.active = null; void activateBlank(blankState.tabs[0].id); }
        else if (review) { workspace.active = null; void openReview(review.id, {resume: true}); }
        else { workspace.active = null; close(); }
      } else if (workspace.active === id) {
        workspace.active = workspace.mru.find(value => workspace.tabs.some(tab => tab.id === value)) || workspace.tabs[0]?.id || null;
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
          restoreBlankState();
          renderTabs();
          if (workspace.paneOpen && activeBlank()) await activateBlank(activeBlankId);
          else if (workspace.paneOpen && activeTab()) await activate(workspace.active);
          else if (workspace.paneOpen) await createBlank();
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
      setPreviewStatus();
      els.filePreview.className = "file-preview empty";
      if (els.previewTitle) els.previewTitle.textContent = title;
      if (els.previewMeta) els.previewMeta.textContent = body || "";
      if (els.previewLanguage) els.previewLanguage.textContent = "";
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
      els.filePreview.onchange = null;
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
      els.filePreview.onchange = null;
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
      els.filePreview.onchange = null;
      els.filePreview.className = "file-preview image-preview";
      els.filePreview.innerHTML = `<div class="image-preview-viewport fit"><img src="${escapeHtml(fileUrl(activeTab()?.locator || path, activeTab(), true))}" alt="${escapeHtml(path.split(/[\\/]/).pop() || "preview")}" draggable="false" /></div>`;
      const viewport = els.filePreview.querySelector(".image-preview-viewport");
      const image = viewport.querySelector("img");
      const imageEpoch = epoch, imageSeq = rendererSeq;
      const imageCurrent = () => imageEpoch === epoch && imageSeq === rendererSeq && image.isConnected;
      if (els.previewMeta) els.previewMeta.textContent = formatMeta(lastData || {}, t("previewLoading"));
      setPreviewStatus(t("previewLoading"));
      image.addEventListener("load", () => {
        if (imageCurrent()) { applyImageScale(state.previewImageScale); if (els.previewMeta) els.previewMeta.textContent = formatMeta(lastData || {}); setPreviewStatus(); }
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
      els.filePreview.onchange = null;
      els.filePreview.className = "file-preview pdf-preview";
      renderModeActions([]);
      els.filePreview.innerHTML = `<iframe class="preview-pdf-frame" src="${escapeHtml(fileUrl(activeTab()?.locator || path, activeTab(), true))}#view=FitH&toolbar=1&navpanes=0" title="${escapeHtml(path.split(/[\\/]/).pop() || t("previewPdf"))}"></iframe>`;
      const frame = els.filePreview.querySelector("iframe");
      const frameEpoch = epoch, frameSeq = rendererSeq;
      if (els.previewMeta) els.previewMeta.textContent = formatMeta(lastData || {}, t("previewLoading"));
      setPreviewStatus(t("previewLoading"));
      frame.addEventListener("load", () => {
        if (frameEpoch === epoch && frameSeq === rendererSeq && frame.isConnected) { if (els.previewMeta) els.previewMeta.textContent = formatMeta(lastData || {}); setPreviewStatus(); }
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
        if (!reviewMode && !activeBlankId && scope && workspace?.paneOpen && activeTab()) {
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
      const blankTarget = options.blankTarget, priorBlank = activeBlank();
      if (blankTarget) {
        const expectedScope = scope, expectedEpoch = epoch, controller = new AbortController();
        if (activeBlank() !== blankTarget) return false;
        stopBlankSearch(blankTarget); blankTarget.openController = controller;
        options = {...options, isCurrent: () => activeBlank() === blankTarget && scope === expectedScope && epoch === expectedEpoch
          && workspace?.paneOpen && blankTarget.openController === controller && !controller.signal.aborted};
        blankTarget.opening = true; blankTarget.error = "";
      }
      if (options.isCurrent && !options.isCurrent()) return false;
      const suppliedIntent = options.intent;
      const intentSeq = suppliedIntent?.seq ?? (options.ready ? openIntentSeq : ++openIntentSeq);
      if (!scope && !options.ready) {
        const expectedEpoch = epoch + (restoring ? 0 : 1);
        if (restoring) await restoring;
        else await restore();
        if (epoch !== expectedEpoch) return false;
      }
      if (!scope || !workspace || (options.isCurrent && !options.isCurrent())) return false;
      if (!options.newTab && options.gesture !== "double" && intentSeq !== openIntentSeq) return false;
      if (suppliedIntent && (suppliedIntent.epoch !== epoch || suppliedIntent.scopeKey !== keyOf(scope))) return false;
      const ownEpoch = epoch;
      const context = scope;
      let ownSeq = suppliedIntent?.requestSeq ?? ++requestSeq;
      const requestedOrder = blankTarget?.order ?? suppliedIntent?.order ?? orderBase + intentSeq;
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
        if (blankTarget) renderBlank();
        else {
          leaveBlank(); reviewMode = false; syncReviewModes();
          clearRenderer(false); ownSeq = requestSeq;
          workspace.paneOpen = true; els.workbench.classList.add("preview-open");
          renderLoading({ path });
        }
      }
      try {
        const data = await apiJson(fileUrl(path, options.expectedFileKey ? {fileKey: options.expectedFileKey} : null), blankTarget ? {signal: blankTarget.openController.signal} : undefined);
        if (ownEpoch !== epoch || context !== scope || ((!options.newTab || blankTarget) && ownSeq !== requestSeq) || (options.isCurrent && !options.isCurrent())) return false;
        if (!data.fileKey || !data.canonicalAbsolutePath) throw new Error("identity");
        if (options.expectedFileKey && data.fileKey !== options.expectedFileKey) throw new Error("identity");
        if ((closedFiles.get(data.fileKey) || 0) > intentSeq) return false;
        const foreground = ownSeq === requestSeq;
        let tab = workspace.tabs.find((item) => item.fileKey === data.fileKey);
        if (!tab) {
          const slot = !options.newTab && workspace.tabs.find((item) => item.id === workspace.reuse);
          if (!slot && !blankTarget && slotCount() >= 20) {
            warn("previewTabLimit");
            if (foreground && activeTab()) await activate(workspace.active);
            else if (foreground && priorBlank && blankState?.tabs.includes(priorBlank)) await activateBlank(priorBlank.id);
            return false;
          }
          tab = { id: blankTarget?.id || slot?.id || uid(), path: data.canonicalAbsolutePath,
            locator: data.locator, fileKey: data.fileKey, name: data.name,
            scroll: 0, mode: null, scale: null, order: slot?.order ?? requestedOrder };
          if (slot) workspace.tabs.splice(workspace.tabs.indexOf(slot), 1, tab);
          else workspace.tabs.push(tab);
          if (!options.newTab) workspace.reuse = tab.id;
        }
        if (options.newTab) tab.order = Math.min(tab.order, requestedOrder);
        if (blankTarget) {
          blankState.tabs = blankState.tabs.filter(item => item !== blankTarget);
          blankState.active = null; activeBlankId = null;
          viewMru = viewMru.filter(id => id !== blankTarget.id);
          if (!blankState.tabs.length) { blankSessions.delete(keyOf(scope)); blankState = null; }
        }
        workspace.tabs.sort((left, right) => left.order - right.order);
        cachePreview(data);
        if (!foreground) {
          if (!workspace.active) workspace.active = tab.id;
          renderTabs(); persist(); return true;
        }
        if (beforeGesture && gesture === beforeGesture) gesture.committed = true;
        clearRenderer(false);
        workspace.active = tab.id;
        touchView(tab.id);
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
        if (ownEpoch === epoch && ownSeq === requestSeq && (!options.isCurrent || options.isCurrent())) {
          if (blankTarget) {
            blankTarget.opening = false; blankTarget.openController = null; blankTarget.error = "previewPickerOpenFailed";
            renderBlank({focus: true}); return false;
          }
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
      if (els.previewTitle) els.previewTitle.textContent = data.name || "File";
      if (els.previewMeta) els.previewMeta.textContent = formatMeta(data);
      if (els.previewLanguage) els.previewLanguage.textContent = language;
      els.refreshPreview.disabled = false;
      setPreviewStatus(data.truncated ? t("fmtTruncatedContent") : "");
      const ext = (data.name || "").split(".").pop()?.toLowerCase();

      if (ext && /^(png|jpg|jpeg|gif|webp|svg|bmp|ico)$/i.test(ext)) {
        state.previewKind = "image";
        state.previewContent = "";
        if (els.previewLanguage) els.previewLanguage.textContent = ext;
        renderImagePreview(state.previewPath);
        els.copyPreview.disabled = true;
        if (options.scheduleRefresh !== false) startAutoRefresh();
        return;
      }
      if (ext === "pdf") {
        state.previewKind = "pdf";
        state.previewContent = "";
        if (els.previewLanguage) els.previewLanguage.textContent = "pdf";
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
      closeTabMenu(false);
      openIntentSeq += 1;
      gesture = null;
      saveView();
      if (workspace) workspace.paneOpen = false;
      persist();
      reviewMode = false; syncReviewModes();
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
      if (activeBlank()) await activateBlank(activeBlankId, true);
      else if (activeTab()) await activate(workspace.active);
      else if (blankState?.tabs.length) await activateBlank(blankState.tabs[0].id, true);
      else await createBlank();
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
      newTabButton?.addEventListener("click", () => { void createBlank(); });
      tabListToggle?.addEventListener("click", () => tabMenuState ? closeTabMenu(true) : openTabMenu());
      tabListToggle?.addEventListener("keydown", event => {
        if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); openTabMenu(event.key === "ArrowDown" ? "first" : "last"); }
      });
      tabListMenu?.addEventListener("keydown", event => {
        if (event.key === "Escape") { event.preventDefault(); closeTabMenu(true); return; }
        if (event.key === "Tab") { closeTabMenu(true); return; }
        if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const buttons = [...tabListMenu.children], current = buttons.indexOf(documentRef.activeElement);
        const index = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (current + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
        buttons[index]?.focus({preventScroll: true}); revealMenuItem(buttons[index]);
      });
      documentRef.addEventListener?.("pointerdown", event => {
        if (tabMenuState && !tabListMenu.contains(event.target) && !tabListToggle.contains(event.target)) closeTabMenu(false);
      });
      tabsElement?.addEventListener("wheel", event => {
        if (event.ctrlKey || tabsElement.scrollWidth <= tabsElement.clientWidth + 1) return;
        event.preventDefault(); tabsElement.scrollLeft += event.deltaX || event.deltaY;
      }, {passive: false});
      if (tabsElement && global.ResizeObserver) { tabResizeObserver = new global.ResizeObserver(syncTabOverflow); tabResizeObserver.observe(tabsElement); }
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
      global.addEventListener("resize", () => { applyPreviewWidth(state.previewWidth); syncTabOverflow(); });
      global.addEventListener("pagehide", () => { closeTabMenu(false); tabResizeObserver?.disconnect(); saveView(); persist(); stopBlankSearch(); stopAutoRefresh(); stopReviewRequests(); releaseDrag(false); clearCached(); });
      global.addEventListener("pageshow", () => { if (tabsElement) tabResizeObserver?.observe(tabsElement); syncTabOverflow(); });
      els.filePreview?.addEventListener?.("scroll", () => { saveView(); persist(); }, { passive: true });
    }

    return Object.freeze({
      openReview,
      readReviewSummary,
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
        if (activeBlankId) { renderTabs(); renderBlank({reset: true}); return; }
        if (reviewMode) { renderReview(); return; }
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
