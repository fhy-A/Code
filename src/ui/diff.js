(function registerDiffUi(global) {
  "use strict";

  const Code = global.Code;
  if (!Code?.ui) throw new Error("Code namespace must load before diff UI");

  function normalizeDiffText(text = "") {
    const source = String(text).replace(/\r\n/g, "\n");
    const fenced = source.match(/```(?:diff)?\s*\n([\s\S]*?)\n?```/i);
    if (fenced) return fenced[1].trimEnd();

    const lines = source.split("\n");
    const firstHeader = lines.findIndex((line) => line.startsWith("--- "));
    const normalized = firstHeader >= 0 ? lines.slice(firstHeader) : lines;
    while (normalized.length && /^```(?:diff)?\s*$/i.test(normalized[0].trim())) normalized.shift();
    while (normalized.length && /^```\s*$/.test(normalized.at(-1).trim())) normalized.pop();
    return normalized.join("\n").trimEnd();
  }

  function getDiffStats(text = "") {
    const lines = normalizeDiffText(text).split("\n");
    return {
      additions: lines.filter((line) => line.startsWith("+") && !line.startsWith("+++")).length,
      removals: lines.filter((line) => line.startsWith("-") && !line.startsWith("---")).length,
      lineCount: lines.length,
    };
  }

  function isEditSuggestionMessage(msg) {
    if (!msg || msg.role !== "tool-result") return false;
    const meta = msg.meta || {};
    const action = meta.action || meta.tool?.action || "";
    if (action === "delete_file") return false;
    return !!meta.pendingEditId && (["propose_edit", "apply_edit", "write_file", "manage_generated_image"].includes(action) || !!meta.newContent);
  }

  function getEditSuggestionInstanceId(meta = {}) {
    const pendingEditId = String(meta.pendingEditId || "");
    if (!meta.serverManaged) return pendingEditId;

    const authorizationId = String(meta.authorizationId || "");
    if (authorizationId) return `server-edit-authorization-${authorizationId}`;

    const agentRunId = String(meta.agentRunId || "");
    const toolCallId = String(meta.toolCallId || "");
    if (agentRunId && toolCallId) return `server-edit-call-${agentRunId}-${toolCallId}`;
    return pendingEditId;
  }

  function createEditDiffDisclosureState() {
    let sessionId = null;
    const expanded = new Set();
    const fullyExpanded = new Set();
    const normalizeId = (value) => String(value || "");

    function setSession(nextSessionId) {
      const next = normalizeId(nextSessionId);
      if (sessionId === next) return false;
      sessionId = next;
      expanded.clear();
      fullyExpanded.clear();
      return true;
    }

    function setExpanded(editId, value) {
      const id = normalizeId(editId);
      if (!id) return false;
      if (value) expanded.add(id);
      else expanded.delete(id);
      return true;
    }

    function setFullyExpanded(editId, value) {
      const id = normalizeId(editId);
      if (!id) return false;
      if (value) fullyExpanded.add(id);
      else fullyExpanded.delete(id);
      return true;
    }

    return Object.freeze({
      isExpanded: (editId) => expanded.has(normalizeId(editId)),
      isFullyExpanded: (editId) => fullyExpanded.has(normalizeId(editId)),
      setExpanded,
      setFullyExpanded,
      setSession,
      snapshot: () => ({
        sessionId: sessionId || "",
        expanded: Array.from(expanded),
        fullyExpanded: Array.from(fullyExpanded),
      }),
    });
  }

  function createDiffFeature(options = {}) {
    const escapeHtml = options.escapeHtml || ((value) => String(value ?? ""));
    const highlightSyntax = options.highlightSyntax || ((value) => escapeHtml(value));
    const renderMarkdown = options.renderMarkdown || ((value) => escapeHtml(value));
    const renderCopyButton = options.renderCopyButton || (() => "");
    const t = options.t || ((key) => key);
    const getMessageText = options.getMessageText || ((msg) => String(msg?.content || ""));
    const getPendingEdits = options.getPendingEdits || (() => ({}));
    const getAuthorizationRequests = options.getAuthorizationRequests || (() => []);
    const getPermissionProfile = options.getPermissionProfile || (() => "accept");
    const isEditDiffExpanded = options.isEditDiffExpanded || (() => false);
    const isEditDiffFullyExpanded = options.isEditDiffFullyExpanded || (() => false);

    function renderDiff(text, renderOptions = {}) {
      const lines = normalizeDiffText(text).split("\n");
      let lang = null;
      for (const line of lines) {
        const match = line.match(/^(---|\+\+\+) [ab]\/(.+)/);
        if (!match) continue;
        const extension = match[2].split(".").pop().toLowerCase();
        if (extension) lang = extension;
        break;
      }

      let oldLine = 0;
      let newLine = 0;
      const gutter = (value) => `<span class="diff-gutter">${value}</span>`;
      const number = (value) => `<span class="diff-num">${value}</span>`;
      const html = lines.map((line) => {
        if (line.startsWith("+++") || line.startsWith("---")) {
          return `<span class="diff-line diff-header">${gutter("")}${number("")}<span class="diff-code">${escapeHtml(line)}</span></span>`;
        }
        if (line.startsWith("@@")) {
          const match = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
          if (match) {
            oldLine = parseInt(match[1], 10) - 1;
            newLine = parseInt(match[2], 10) - 1;
          }
          return `<span class="diff-line diff-hunk">${gutter("")}${number("")}<span class="diff-code">${escapeHtml(line)}</span></span>`;
        }

        let lineNumber = "";
        let className;
        let marker;
        let content;
        if (line.startsWith("+")) {
          newLine += 1;
          lineNumber = newLine;
          className = "diff-add";
          marker = "+";
          content = line.slice(1);
        } else if (line.startsWith("-")) {
          oldLine += 1;
          lineNumber = oldLine;
          className = "diff-remove";
          marker = "-";
          content = line.slice(1);
        } else {
          oldLine += 1;
          newLine += 1;
          lineNumber = newLine;
          className = "diff-context";
          marker = " ";
          content = line.startsWith(" ") ? line.slice(1) : line;
        }
        const highlighted = lang ? highlightSyntax(content, lang) : escapeHtml(content);
        return `<span class="diff-line ${className}">${gutter(marker)}${number(lineNumber)}<span class="diff-code">${highlighted}</span></span>`;
      }).join("");

      const isLong = lines.length > 40;
      const expanded = isLong && renderOptions.expanded === true;
      const expandLabel = expanded ? t("collapseDiff") : t("expandDiff", { count: lines.length });
      return `<div class="code-block diff-block${isLong ? (expanded ? " is-expanded" : " is-collapsed") : ""}"><div class="diff-lines">${html}</div>${isLong ? `<button class="diff-expand-btn" type="button" aria-expanded="${expanded}">${escapeHtml(expandLabel)}</button>` : ""}</div>`;
    }

    function renderEditSuggestionProjection(msg, index) {
      const meta = msg.meta || {};
      const pendingId = meta.pendingEditId;
      const editInstanceId = getEditSuggestionInstanceId(meta) || pendingId;
      const action = meta.action || meta.tool?.action || "propose_edit";
      const target = meta.path || meta.tool?.path || "";
      const content = getMessageText(msg).trim();
      if (!pendingId || action === "delete_file" || !content) return "";

      const pendingEdits = getPendingEdits() || {};
      const authorizationRequests = getAuthorizationRequests() || [];
      const permissionProfile = getPermissionProfile();
      const editState = pendingEdits[editInstanceId] || {};
      const applied = !!(meta.applied || editState.applied);
      const rejected = !!(meta.rejected || editState.rejected || editState.resolved && !editState.applied);
      const serverExecuting = Boolean(meta.serverManaged && meta.authorizationDecision === "approved" && !applied && !rejected);
      const isPending = authorizationRequests.some((item) => item.status === "pending" && item.editId === editInstanceId);
      // Server-managed edits that were approved: treat as applied (model handles retries).
      const autoApplied = Boolean(meta.serverManaged && meta.authorizationDecision === "approved" && !applied && !rejected);
      const queued = isPending || Boolean(meta.serverManaged && !serverExecuting && !applied && !rejected && !autoApplied);
      const proposalOnly = permissionProfile === "plan" || !!meta.proposalOnly;
      const diffText = normalizeDiffText(content);
      if (/^\(no changes\)$/i.test(diffText.trim())) return "";
      const isDiff = /(^|\n)(--- |\+\+\+ |@@ )/.test(diffText);
      const isWriteFile = action === "write_file";
      const hasDiffBody = isDiff || isWriteFile;
      const diffExpanded = hasDiffBody && isEditDiffExpanded(editInstanceId);
      const diffFullyExpanded = hasDiffBody && isEditDiffFullyExpanded(editInstanceId);
      let body;
      if (isDiff) {
        body = renderDiff(diffText, { expanded: diffFullyExpanded });
      } else if (isWriteFile) {
        const ext = (target || "").split(".").pop().toLowerCase() || "";
        const lines = content.split("\n");
        const lineCount = lines.length;
        const isLong = lineCount > 40;
        const lineHtml = lines.map((line, i) => `<span class="diff-line diff-add"><span class="diff-gutter">+</span><span class="diff-num">${i + 1}</span><span class="diff-code">${highlightSyntax(line, ext)}</span></span>`).join("");
        const expandLabel = diffFullyExpanded ? t("collapseDiff") : t("expandDiff", { count: lineCount });
        body = `<div class="code-block write-file-preview${isLong ? (diffFullyExpanded ? " is-expanded" : " is-collapsed") : ""}"><div class="diff-lines">${lineHtml}</div>${isLong ? `<button class="diff-expand-btn" type="button" aria-expanded="${diffFullyExpanded}">${escapeHtml(expandLabel)}</button>` : ""}</div>`;
      } else {
        body = `<div class="tool-edit-markdown">${renderMarkdown(content)}</div>`;
      }
      const stats = isDiff ? getDiffStats(diffText) : { additions: 0, removals: 0 };
      const canReject = permissionProfile !== "bypass";
      const effectiveApplied = applied || autoApplied;
      const status = effectiveApplied ? t("appliedLabel") : (rejected ? t("rejectedLabel") : (proposalOnly ? t("proposalOnly") : (serverExecuting ? t("processingLabel") : (queued ? t("waitingApproval") : t("pendingConfirmation")))));
      const statusClass = effectiveApplied ? "is-applied" : (rejected ? "is-rejected" : "is-review");
      const disclosureKey = diffExpanded ? "collapseEditDiff" : "expandEditDiff";
      const disclosureLabel = t(disclosureKey);
      const safeEditInstanceId = String(editInstanceId).replace(/[^A-Za-z0-9_-]/g, "-");
      const diffContentId = `edit-diff-${safeEditInstanceId}-${index}`;

      let actions = "";
      if (!applied && !rejected && !queued && !proposalOnly && !meta.serverManaged) {
        actions = `
          <div class="apply-edit-bar">
            <button class="apply-edit-btn" type="button" data-edit-id="${escapeHtml(pendingId)}">${t("applyEdit")}</button>
            ${canReject ? `<button class="reject-edit-btn" type="button" data-edit-id="${escapeHtml(pendingId)}">${t("rejectEdit")}</button>` : ""}
          </div>
        `;
      }

      return `
        <article class="msg assistant edit-suggestion" data-msg-index="${index}" data-edit-id="${escapeHtml(editInstanceId)}">
          <div class="tool-edit-card">
            <div class="tool-edit-head">
              <div class="tool-edit-heading">
                ${target ? `<button class="tool-edit-target clickable-path" type="button" data-path="${escapeHtml(target)}" title="${t("openInPreview")}">${escapeHtml(target)}</button>` : `<span class="tool-edit-target">${t("unnamedFile")}</span>`}
                <span class="tool-edit-title">${action === "write_file" ? t("fileWriteProposal") : t("editProposal")}</span>
              </div>
              <div class="tool-edit-summary">
                ${isDiff ? `<span class="diff-stat diff-stat-add">+${stats.additions}</span><span class="diff-stat diff-stat-remove">−${stats.removals}</span>` : (isWriteFile ? `<span class="diff-stat diff-stat-add">+${stats.additions || content.split("\n").length} lines</span>` : "")}
                ${isDiff || isWriteFile ? renderCopyButton(content) : ""}
                <span class="tool-edit-status ${statusClass}">${escapeHtml(status)}</span>
                ${hasDiffBody ? `<button class="edit-diff-toggle" type="button" data-edit-diff-toggle data-edit-id="${escapeHtml(editInstanceId)}" aria-expanded="${diffExpanded}" aria-controls="${escapeHtml(diffContentId)}" aria-label="${escapeHtml(disclosureLabel)}" title="${escapeHtml(disclosureLabel)}" data-i18n-aria-label="${disclosureKey}" data-i18n-title="${disclosureKey}"><span data-edit-diff-label data-i18n="${disclosureKey}">${escapeHtml(disclosureLabel)}</span><span class="edit-diff-toggle-chevron" aria-hidden="true"></span></button>` : ""}
              </div>
            </div>
            <div class="tool-edit-diff"${hasDiffBody ? ` id="${escapeHtml(diffContentId)}" data-edit-diff-body${diffExpanded ? "" : " hidden"}` : ""}>${body}</div>
            ${actions}
          </div>
        </article>
      `;
    }

    return Object.freeze({
      getDiffStats,
      getEditSuggestionInstanceId,
      isEditSuggestionMessage,
      normalizeDiffText,
      renderDiff,
      renderEditSuggestionProjection,
    });
  }

  Code.ui.diff = Object.freeze({
    createEditDiffDisclosureState,
    createDiffFeature,
    getDiffStats,
    getEditSuggestionInstanceId,
    isEditSuggestionMessage,
    normalizeDiffText,
  });
})(window);
