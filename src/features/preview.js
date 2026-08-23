(function registerPreviewFeature(global) {
  "use strict";

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

    function applyPreviewWidth(width = state.previewWidth, persist = true) {
      const viewportLimit = Math.max(320, (global.innerWidth || 1280) - 520);
      const next = Math.min(Math.max(Number(width) || 420, 250), viewportLimit);
      state.previewWidth = next;
      documentRef?.documentElement?.style?.setProperty("--preview-width", `${next}px`);
      if (persist) storage?.setItem("code-preview-width", String(next));
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
        button.addEventListener("click", action.onClick);
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
      });
      els.filePreview.querySelector('[data-table-page="next"]')?.addEventListener("click", () => {
        tableState.page += 1;
        renderDelimitedTablePage();
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
      state.previewImageScale = null;
      els.filePreview.onclick = null;
      els.filePreview.className = "file-preview image-preview";
      els.filePreview.innerHTML = `<div class="image-preview-viewport fit"><img src="${previewRawUrl(path, state._previewMtime || "")}" alt="${escapeHtml(path.split(/[\\/]/).pop() || "preview")}" draggable="false" /></div>`;
      const viewport = els.filePreview.querySelector(".image-preview-viewport");
      const image = viewport.querySelector("img");
      image.addEventListener("load", renderImageActions, { once: true });
      image.addEventListener("error", () => renderNotice(t("loadFailed"), t("imageReadFailed")), { once: true });
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
      els.filePreview.innerHTML = `<iframe class="preview-pdf-frame" src="${previewRawUrl(path, state._previewMtime || "")}#view=FitH&toolbar=1&navpanes=0" title="${escapeHtml(path.split(/[\\/]/).pop() || t("previewPdf"))}"></iframe>`;
    }

    function markActiveFile() {
      documentRef.querySelectorAll(".file-item").forEach((button) => {
        button.classList.toggle("active", button.dataset.path === state.previewPath);
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
      if (pollTimer !== null) global.clearInterval(pollTimer);
      pollTimer = null;
    }

    function startAutoRefresh() {
      stopAutoRefresh();
      pollTimer = global.setInterval(async () => {
        if (!state.previewPath || !els.workbench.classList.contains("preview-open")) return;
        try {
          const data = await apiJson(`/api/file?path=${encodeURIComponent(state.previewPath)}`);
          if (!data.updatedAt || data.updatedAt === state._previewMtime) return;
          state._previewMtime = data.updatedAt;
          els.previewMeta.textContent = formatMeta(data, t("autoUpdated"));
          if (state.previewKind === "image") {
            renderImagePreview(state.previewPath);
          } else if (state.previewKind === "pdf") {
            renderPdfPreview(state.previewPath);
          } else if (!data.binary) {
            state.previewContent = data.content || "";
            if (state.previewKind === "markdown") {
              renderMarkdownPreview(state.previewContent, state.previewMode);
            } else if (state.previewKind === "delimited") {
              const ext = state.previewPath.split(".").pop()?.toLowerCase();
              state.previewTable = null;
              renderDelimitedPreview(state.previewContent, ext === "tsv" ? "\t" : ",", state.previewMode);
            } else {
              renderCodePreview(state.previewContent);
            }
          }
        } catch (_) { /* file may have been deleted or renamed */ }
      }, 3000);
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
      const data = await apiJson(`/api/file?path=${encodeURIComponent(path)}`);
      const previousPath = state.previewPath;
      els.workbench.classList.add("preview-open");
      storage?.setItem("code-preview-open", "1");
      storage?.setItem("code-preview-path", path);
      state.previewPath = data.path || path;
      if (previousPath !== state.previewPath) {
        state.previewTable = null;
        state.previewImageScale = null;
      }
      state._previewMtime = data.updatedAt || "";
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
        startAutoRefresh();
        return;
      }
      if (ext === "pdf") {
        state.previewKind = "pdf";
        state.previewContent = "";
        els.previewLanguage.textContent = "pdf";
        renderPdfPreview(state.previewPath);
        els.copyPreview.disabled = true;
        startAutoRefresh();
        return;
      }
      if (data.binary) {
        state.previewContent = "";
        renderNotice(t("binaryFile"), t("previewUnsupported"));
        els.copyPreview.disabled = true;
        return;
      }

      state.previewContent = data.content || "";
      // Oversized text files open externally instead of an internal preview
      // (routing matrix 5: over the preview character/line limits).
      if (state.previewContent && (
        state.previewContent.length > 350000
        || state.previewContent.split("\n").length > 8000
      )) {
        try {
          await apiJson("/api/open-file", {
            method: "POST",
            body: JSON.stringify({ path: state.previewPath }),
          });
        } catch (_) { /* keep the preview pane untouched */ }
        return;
      }
      if (state.previewContent) {
        if (ext === "md" || ext === "markdown" || ext === "mdown") {
          state.previewKind = "markdown";
          if (previousPath !== state.previewPath) state.previewMode = "rendered";
          renderMarkdownPreview(state.previewContent, state.previewMode);
        } else if (ext === "csv" || ext === "tsv") {
          state.previewKind = "delimited";
          if (previousPath !== state.previewPath) state.previewMode = "table";
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
      startAutoRefresh();
    }

    function close() {
      stopAutoRefresh();
      els.workbench.classList.remove("preview-open");
      state.previewPath = "";
      state.previewContent = "";
      storage?.removeItem("code-preview-open");
      storage?.removeItem("code-preview-path");
    }

    function toggle() {
      const opening = !els.workbench.classList.contains("preview-open");
      if (opening) {
        els.workbench.classList.add("preview-open");
      } else {
        close();
      }
    }

    function finishDrag(event) {
      if (!dragState) return;
      if (event?.pointerId !== undefined && els.previewResizer.hasPointerCapture(event.pointerId)) {
        els.previewResizer.releasePointerCapture(event.pointerId);
      }
      if (resizeFrame) {
        global.cancelAnimationFrame(resizeFrame);
        resizeFrame = 0;
      }
      applyPreviewWidth(pendingWidth ?? state.previewWidth, true);
      pendingWidth = null;
      dragState = null;
      documentRef.body.classList.remove("resizing-preview");
      documentRef?.documentElement?.style?.removeProperty?.("--drag-message-list-width");
      documentRef?.documentElement?.style?.removeProperty?.("--drag-preview-content-width");
    }

    function bind() {
      if (bound) return;
      bound = true;
      els.refreshPreview.addEventListener("click", () => {
        if (!state.previewPath) return;
        loadFile(state.previewPath).catch((error) => showToast(error.message, "error"));
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
        dragState = { startX: event.clientX, startWidth: state.previewWidth };
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
        if (!dragState) return;
        pendingWidth = dragState.startWidth - (event.clientX - dragState.startX);
        if (resizeFrame) return;
        resizeFrame = global.requestAnimationFrame(() => {
          applyPreviewWidth(pendingWidth, false);
          resizeFrame = 0;
        });
      });
      els.previewResizer.addEventListener("pointerup", finishDrag);
      els.previewResizer.addEventListener("pointercancel", finishDrag);
      global.addEventListener("resize", () => applyPreviewWidth(state.previewWidth));
    }

    async function restore() {
      if (storage?.getItem("code-preview-open") !== "1") return false;
      const savedPath = storage.getItem("code-preview-path");
      if (!savedPath) return false;
      try {
        await loadFile(savedPath);
        return true;
      } catch (_) {
        storage.removeItem("code-preview-open");
        storage.removeItem("code-preview-path");
        return false;
      }
    }

    return Object.freeze({
      applyPreviewWidth,
      bind,
      close,
      loadFile,
      renderCodePreview,
      renderDelimitedPreview,
      renderImagePreview,
      renderMarkdownPreview,
      renderPdfPreview,
      restore,
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
