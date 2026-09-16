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

  // Presentation only. Never use this projection as an edit/apply payload.
  function compactUnifiedDiff(text = "") {
    let source = String(text).replace(/\r\n/g, "\n");
    const fence = source.match(/^```(?:diff)?[^\S\n]*\n([\s\S]*?)\n```[^\S\n]*$/i);
    if (fence) source = fence[1];
    const lines = source.split("\n");
    if (lines.at(-1) === "") lines.pop();
    const fail = () => ({ok: false, source});
    // Bound parser work independently of the review controller's retained-body cap.
    if (source.length > 1048576 || lines.length > 20000) return fail();
    let i = 0, path = "", previousEnd = [1, 1];
    while (i < lines.length && /^(diff --git |index |new file mode |deleted file mode |old mode |new mode |similarity index |rename from |rename to )/.test(lines[i])) i++;
    if (lines[i]?.startsWith("--- ")) {
      if (!lines[i + 1]?.startsWith("+++ ")) return fail();
      path = lines[i + 1].slice(4).split("\t")[0]; i += 2;
    }
    const selected = [];
    while (i < lines.length) {
      const match = lines[i++].match(/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:.*)?$/);
      if (!match) return fail();
      const [oldStart, oldCount, newStart, newCount] = [Number(match[1]), Number(match[2] ?? 1), Number(match[3]), Number(match[4] ?? 1)];
      if (![oldStart, oldCount, newStart, newCount, oldStart + oldCount, newStart + newCount].every(Number.isSafeInteger)
          || (oldCount && !oldStart) || (newCount && !newStart)) return fail();
      let oldLine = oldStart + (oldCount ? 0 : 1), newLine = newStart + (newCount ? 0 : 1), oldUsed = 0, newUsed = 0;
      if (oldLine < previousEnd[0] || newLine < previousEnd[1]) return fail();
      const rows = [];
      while (oldUsed < oldCount || newUsed < newCount || lines[i] === "\\ No newline at end of file") {
        const line = lines[i++];
        if (line === "\\ No newline at end of file") {
          if (!rows.length || rows.at(-1).noNewline) return fail();
          rows.at(-1).noNewline = true; continue;
        }
        if (typeof line !== "string" || !/^[ +\-]/.test(line)) return fail();
        const kind = line[0] === "+" ? "add" : line[0] === "-" ? "remove" : "context";
        const row = {kind, text: line.slice(1), before: [oldLine, newLine], oldLine: kind === "add" ? null : oldLine, newLine: kind === "remove" ? null : newLine};
        if (kind !== "add") { oldLine++; oldUsed++; }
        if (kind !== "remove") { newLine++; newUsed++; }
        if (oldUsed > oldCount || newUsed > newCount) return fail();
        row.after = [oldLine, newLine]; rows.push(row);
      }
      const keep = new Set();
      rows.forEach((row, index) => {
        if (row.kind !== "context") for (let j = Math.max(0, index - 1); j <= Math.min(rows.length - 1, index + 1); j++) keep.add(j);
      });
      rows.forEach((row, index) => { if (keep.has(index)) selected.push(row); });
      previousEnd = [oldLine, newLine];
    }
    const rows = [], gap = (before, after) => {
      const oldGap = after[0] - before[0], newGap = after[1] - before[1];
      if (oldGap || newGap) rows.push({kind: "gap", count: oldGap === newGap && oldGap >= 0 ? oldGap : null});
    };
    let cursor = [1, 1];
    for (const row of selected) { gap(cursor, row.before); rows.push(row); cursor = row.after; }
    if (selected.length) gap(cursor, previousEnd);
    return {ok: true, rows, path, source};
  }

  function isEditSuggestionMessage(msg) {
    if (!msg || msg.role !== "tool-result") return false;
    const meta = msg.meta || {};
    const action = meta.action || meta.tool?.action || "";
    if (action === "delete_file") return false;
    // Old snapshots may contain a synthetic pendingEditId for a failed call.
    // Filter that projection at display time without rewriting saved history.
    const failed = meta.result?.ok === false || meta.outcome === "failed";
    if (meta.serverManaged && failed && !meta.authorizationId
        && !meta.result?.proposalId && !meta.applied && !meta.result?.applied
        && !(meta.path && /(^|\n)(--- |\+\+\+ |@@ )/.test(normalizeDiffText(msg.content)))) return false;
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
      if (renderOptions.compact) {
        const parsed = compactUnifiedDiff(text);
        let html, count;
        if (!parsed.ok) {
          count = parsed.source.split("\n").length;
          html = `<p class="compact-diff-warning">${escapeHtml(t("compactDiffFallback"))}</p><pre class="compact-diff-raw">${escapeHtml(parsed.source)}</pre>`;
        } else {
          count = parsed.rows.length;
          const lang = parsed.path.split(".").pop().toLowerCase();
          html = parsed.rows.map(row => {
            if (row.kind === "gap") return `<div class="compact-diff-gap" data-omitted-lines="${row.count ?? 'unknown'}">${escapeHtml(row.count === null ? t("compactDiffGapUnknown") : t("compactDiffGap", {count: row.count}))}</div>`;
            const marker = row.kind === "add" ? "+" : row.kind === "remove" ? "−" : " ";
            return `<span class="diff-line diff-${row.kind}" data-old-line="${row.oldLine ?? ''}" data-new-line="${row.newLine ?? ''}"><span class="diff-gutter">${marker}</span><span class="diff-num">${row.newLine ?? row.oldLine}</span><span class="diff-code">${lang ? highlightSyntax(row.text, lang) : escapeHtml(row.text)}</span>${row.noNewline ? `<span class="compact-diff-no-newline" title="${escapeHtml(t("compactDiffNoNewline"))}" aria-label="${escapeHtml(t("compactDiffNoNewline"))}">↵</span>` : ''}</span>`;
          }).join("") || `<p class="compact-diff-empty">${escapeHtml(t("reviewNoLineDiff"))}</p>`;
        }
        const isLong = count > 40, expanded = isLong && renderOptions.expanded === true;
        const label = expanded ? t("collapseDiff") : t("expandDiff", {count});
        return `<div class="diff-block compact-diff${isLong ? (expanded ? ' is-expanded' : ' is-collapsed') : ''}" data-diff-line-count="${count}"><div class="diff-lines">${html}</div>${isLong ? `<button class="diff-expand-btn" type="button" aria-expanded="${expanded}">${escapeHtml(label)}</button>` : ''}</div>`;
      }
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
      if (!isEditSuggestionMessage(msg) || !pendingId || action === "delete_file" || !content) return "";

      const pendingEdits = getPendingEdits() || {};
      const authorizationRequests = getAuthorizationRequests() || [];
      const permissionProfile = getPermissionProfile();
      const editState = pendingEdits[editInstanceId] || {};
      const applied = !!(meta.applied || editState.applied || meta.result?.applied === true);
      const resultFailed = meta.result?.ok === false || meta.outcome === "failed";
      const rejected = Boolean(meta.result?.rejected || meta.authorizationDecision === "rejected"
        || (!resultFailed && (meta.rejected || editState.rejected || editState.resolved && !editState.applied)));
      const failed = resultFailed && !applied && !rejected;
      const serverExecuting = Boolean(meta.serverManaged && meta.authorizationDecision === "approved" && !applied && !rejected && !failed);
      const isPending = authorizationRequests.some((item) => item.status === "pending" && item.editId === editInstanceId);
      // Server-managed edits that were approved: treat as applied (model handles retries).
      const autoApplied = Boolean(meta.serverManaged && meta.authorizationDecision === "approved" && !applied && !rejected && !failed);
      const queued = !failed && (isPending || Boolean(meta.serverManaged && !serverExecuting && !applied && !rejected && !autoApplied));
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
        body = renderDiff(content, { expanded: diffFullyExpanded, compact: true });
      } else if (isWriteFile) {
        const lines = content.split("\n");
        const lineCount = lines.length;
        const isLong = lineCount > 40;
        const lineHtml = `<pre class="compact-diff-raw">${escapeHtml(content)}</pre>`;
        const expandLabel = diffFullyExpanded ? t("collapseDiff") : t("expandDiff", { count: lineCount });
        body = `<div class="code-block write-file-preview${isLong ? (diffFullyExpanded ? " is-expanded" : " is-collapsed") : ""}" data-diff-line-count="${lineCount}"><div class="diff-lines">${lineHtml}</div>${isLong ? `<button class="diff-expand-btn" type="button" aria-expanded="${diffFullyExpanded}">${escapeHtml(expandLabel)}</button>` : ""}</div>`;
      } else {
        body = `<div class="tool-edit-markdown">${renderMarkdown(content)}</div>`;
      }
      const stats = isDiff ? getDiffStats(diffText) : { additions: 0, removals: 0 };
      const canReject = permissionProfile !== "bypass";
      const effectiveApplied = applied || autoApplied;
      const status = effectiveApplied ? t("appliedLabel") : (rejected ? t("rejectedLabel") : (failed ? t("toolProcessFailed") : (proposalOnly ? t("proposalOnly") : (serverExecuting ? t("processingLabel") : (queued ? t("waitingApproval") : t("pendingConfirmation"))))));
      const statusClass = effectiveApplied ? "is-applied" : (rejected || failed ? "is-rejected" : "is-review");
      const disclosureKey = diffExpanded ? "collapseEditDiff" : "expandEditDiff";
      const disclosureLabel = t(disclosureKey);
      const safeEditInstanceId = String(editInstanceId).replace(/[^A-Za-z0-9_-]/g, "-");
      const diffContentId = `edit-diff-${safeEditInstanceId}-${index}`;

      let actions = "";
      if (!applied && !rejected && !failed && !queued && !proposalOnly && !meta.serverManaged) {
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
    compactUnifiedDiff,
    createEditDiffDisclosureState,
    createDiffFeature,
    getDiffStats,
    getEditSuggestionInstanceId,
    isEditSuggestionMessage,
    normalizeDiffText,
  });
})(window);
