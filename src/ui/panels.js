(function registerPanelsUi(global) {
  "use strict";

  const Code = global.Code;
  if (!Code?.ui) throw new Error("Code namespace must load before panels UI");

  function countSessionMessages(messages = []) {
    const visible = Array.isArray(messages) ? messages.filter((message) => (
      Boolean(message) && message.meta?.kind !== "auto-context-compaction"
    )) : [];
    const counts = {
      user: visible.filter((msg) => msg.role === "user").length,
      assistant: visible.filter((msg) => msg.role === "assistant").length,
      toolCalls: visible.filter((msg) => msg.role === "tool-call").length,
      toolResults: visible.filter((msg) => msg.role === "tool-result").length,
    };
    counts.total = counts.user + counts.assistant + counts.toolCalls + counts.toolResults;
    return counts;
  }

  function resolveSessionFilePath(session = {}, options = {}) {
    const sessionId = options.sessionId || session?.id || "";
    if (!sessionId) return "-";
    const absolutePath = String(options.absolutePath || "");
    if (absolutePath.endsWith(`${sessionId}.jsonl`)) return absolutePath;
    return `code/data/sessions/${sessionId}.jsonl`;
  }

  function formatSessionTimestamp(value) {
    const raw = String(value || "").trim();
    if (!raw) return "-";
    if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(raw)) {
      return raw.slice(0, 16).replace("T", " ") || "-";
    }
    const parsed = new Date(raw);
    if (!Number.isFinite(parsed.getTime())) return "-";
    const pad = (part) => String(part).padStart(2, "0");
    return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}`
      + ` ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`;
  }

  function sessionSourceI18nKey(session = {}) {
    const source = String(session?.source || "code").toLowerCase();
    if (source === "codex") return "sessionSourceCodex";
    if (source === "claude-code") return "sessionSourceClaude";
    return "sessionSourceCode";
  }

  function formatSessionSource(session = {}, t = (key) => key) {
    return t(sessionSourceI18nKey(session));
  }

  function calculateSessionStats(options = {}) {
    const messages = Array.isArray(options.messages) ? options.messages.filter(Boolean) : [];
    const usageStats = options.stats || {};
    const counts = countSessionMessages(messages);
    const input = usageStats.input;
    const output = usageStats.output;
    const cache = usageStats.cache || 0;
    // Server-persisted stats only carry {input, output, cache, cost}, so a
    // positive cache total is treated as evidence the upstream reported it;
    // the explicit flag covers live sessions where zero cache was reported.
    const cacheReported = Boolean(usageStats.cacheReported) || Number(usageStats.cache) > 0;
    const cacheWriteReported = Object.prototype.hasOwnProperty.call(
      usageStats,
      "cacheWrite",
    );
    const cacheWrite = cacheWriteReported ? Number(usageStats.cacheWrite || 0) : 0;
    const lastUsage = options.lastUsage || null;
    let contextTokens;
    const reportedContextTokens = lastUsage?.prompt_tokens ?? lastUsage?.input;
    if (reportedContextTokens != null) {
      contextTokens = Number(reportedContextTokens) || 0;
    } else {
      const getContextMessages = options.getContextMessages || ((items) => items);
      const estimateTokens = options.estimateTokens || (() => 0);
      const getMessageText = options.getMessageText || ((msg) => String(msg?.content || ""));
      const contextMessages = getContextMessages(messages) || [];
      contextTokens = contextMessages
        .filter((msg) => !msg.streaming)
        .reduce((sum, msg) => sum + estimateTokens(getMessageText(msg)), 0)
        + estimateTokens(
          options.getSystemPrompt
            ? options.getSystemPrompt({ briefSkills: true })
            : options.systemPrompt || "",
        );
    }

    const getContextLimit = options.getContextLimit || (() => 128000);
    const getContextResolution = options.getContextResolution || null;
    const resolution = options.getContextResolution?.(options.model || "") || null;
    const ctxLimit = Number(resolution?.contextLimit || getContextLimit(options.model || ""));
    const contextPct = Math.min(100, (contextTokens / ctxLimit) * 100);
    const cacheHit =
      cacheReported && Number(input) > 0
        ? Math.min(1, Number(cache) / Number(input))
        : null;
    return {
      counts,
      input,
      output,
      cache,
      cacheHit,
      cacheReported,
      cacheWrite,
      cacheWriteReported,
      contextTokens,
      ctxLimit,
      contextWindowTokens: Number(resolution?.contextWindowTokens || ctxLimit),
      contextBudgetTokens: resolution?.contextBudgetTokens ?? null,
      contextWindowSource: String(resolution?.contextWindowSource || "unknown"),
      budgetClamped: Boolean(resolution?.budgetClamped),
      budgetAboveEstimate: Boolean(resolution?.budgetAboveEstimate),
      contextPct,
    };
  }

  function createPanelsFeature(options = {}) {
    const elements = options.elements || {};
    const t = options.t || ((key) => key);
    const formatCompact = options.formatCompact || ((value) => String(value ?? 0));
    const formatNumber = options.formatNumber || ((value) => String(value ?? 0));
    const estimateTokens = options.estimateTokens || (() => 0);
    const getMessages = options.getMessages || (() => []);
    const getStats = options.getStats || (() => ({}));
    const getSessionId = options.getSessionId || (() => "");
    const getSession = options.getSession || (() => ({}));
    const getSessionLastUsage = options.getSessionLastUsage || (() => null);
    const getContextMessages = options.getContextMessages || ((messages) => messages);
    const getContextLimit = options.getContextLimit || (() => 128000);
    const getContextResolution = options.getContextResolution || null;
    const getSelectedModel = options.getSelectedModel || (() => "");
    const getMessageText = options.getMessageText || ((msg) => String(msg?.content || ""));
    const getSystemPrompt = options.getSystemPrompt || (() => "");
    const getDocument = options.getDocument || (() => global.document);
    const copyText = options.copyText || (async () => false);
    const onRenderBranchTree = options.onRenderBranchTree || (() => {});
    const onBranchPanelOpenChanged = options.onBranchPanelOpenChanged || (() => {});
    let bound = false;

    function sessionFilePath(session = getSession()) {
      return resolveSessionFilePath(session, {
        sessionId: getSessionId(),
        absolutePath: session?._sessionMessageFilePath,
      });
    }

    function calcStats(
      messages = getMessages(),
      stats = getStats(),
      sessionId = getSessionId(),
      modelOverride = "",
    ) {
      return calculateSessionStats({
        messages,
        stats,
        lastUsage: getSessionLastUsage(sessionId),
        getContextMessages,
        estimateTokens,
        getMessageText,
        getSystemPrompt,
        model: modelOverride || getSelectedModel() || "",
        getContextLimit,
        getContextResolution,
      });
    }

    function closeTopPanels() {
      elements.statsPanel?.classList.remove("open");
      elements.branchPanel?.classList.remove("open");
      elements.usageStrip?.classList.remove("active");
      elements.toggleBranches?.classList.remove("active");
      onBranchPanelOpenChanged(false);
    }

    function updateStatsPanel() {
      const stats = calcStats();
      elements.statInput.textContent = formatCompact(stats.input);
      elements.statOutput.textContent = formatCompact(stats.output);
      elements.statCache.textContent = formatCompact(stats.cache);
      if (elements.statCacheHit) {
        const hit = stats.cacheHit;
        elements.statCacheHit.hidden = hit === null || hit === undefined;
        elements.statCacheHit.textContent = hit === null || hit === undefined
          ? ""
          : `${(hit * 100).toFixed(0)}%`;
        elements.statCacheHit.title = t("statCacheHitTitle");
      }
      const contextPercent = `${stats.contextPct.toFixed(0)}%`;
      const contextSummary = `${contextPercent} · ${formatCompact(stats.ctxLimit || 128000)}`;
      elements.statContext.textContent = contextPercent;
      elements.usageStrip.title = t("viewSessionInfo");

      const ring = elements.ctxRingFill;
      if (ring) {
        const pct = Math.min(stats.contextPct, 100) / 100;
        const circumference = 2 * Math.PI * 5;
        ring.setAttribute("stroke-dasharray", `${pct * circumference} ${circumference}`);
        ring.setAttribute(
          "stroke",
          stats.contextPct >= 95
            ? "var(--red)"
            : stats.contextPct >= 80
              ? "var(--yellow)"
              : "var(--muted)",
        );
      }

      elements.usageStrip.classList.remove("warn", "danger");
      elements.statContext.classList.remove("warn", "danger");
      if (stats.contextPct >= 80) {
        elements.usageStrip.classList.add("danger");
        elements.statContext.classList.add("danger");
      } else if (stats.contextPct >= 60) {
        elements.usageStrip.classList.add("warn");
        elements.statContext.classList.add("warn");
      }

      const session = getSession() || {};
      elements.sessionCreated.textContent = formatSessionTimestamp(session.createdAt);
      elements.sessionUpdated.textContent = formatSessionTimestamp(session.updatedAt);
      if (elements.sessionSource) {
        elements.sessionSource.setAttribute?.(
          "data-i18n",
          sessionSourceI18nKey(session),
        );
        elements.sessionSource.textContent = formatSessionSource(session, t);
      }
      elements.sessionFile.textContent = sessionFilePath(session);
      elements.sessionFile.title = `ID: ${getSessionId() || "-"}`;
      elements.msgUser.textContent = stats.counts.user;
      elements.msgAssistant.textContent = stats.counts.assistant;
      elements.msgTools.textContent = (stats.counts.toolCalls || 0) + (stats.counts.toolResults || 0);
      elements.msgTotal.textContent = stats.counts.total;
      elements.tokenInput.textContent = formatNumber(stats.input);
      elements.tokenOutput.textContent = formatNumber(stats.output);
      elements.tokenCache.textContent = formatNumber(stats.cache);
      if (elements.tokenCacheHit) {
        elements.tokenCacheHit.textContent = stats.cacheHit === null || stats.cacheHit === undefined
          ? "—"
          : `${(stats.cacheHit * 100).toFixed(0)}%`;
      }
      if (elements.tokenCacheWriteRow) {
        elements.tokenCacheWriteRow.hidden = !stats.cacheWriteReported;
      }
      if (elements.tokenCacheWrite) {
        elements.tokenCacheWrite.textContent = formatNumber(stats.cacheWrite);
      }
      elements.tokenTotal.textContent = formatNumber((stats.input || 0) + (stats.output || 0));
      elements.tokenContext.textContent = contextSummary;
      return stats;
    }

    function toggleBranchPanel() {
      const open = !elements.branchPanel.classList.contains("open");
      closeTopPanels();
      elements.branchPanel.classList.toggle("open", open);
      elements.toggleBranches.classList.toggle("active", open);
      onBranchPanelOpenChanged(open);
      if (open) onRenderBranchTree();
    }

    function toggleStatsPanel() {
      const open = !elements.statsPanel.classList.contains("open");
      closeTopPanels();
      elements.statsPanel.classList.toggle("open", open);
      elements.usageStrip.classList.toggle("active", open);
    }

    function dismissPanelsForTarget(target) {
      if (!target?.closest?.("#statsPanel") && !target?.closest?.("#usageStrip")) {
        elements.statsPanel?.classList.remove("open");
        elements.usageStrip?.classList.remove("active");
      }
      if (!target?.closest?.("#branchPanel") && !target?.closest?.("#toggleBranches")) {
        elements.branchPanel?.classList.remove("open");
        elements.toggleBranches?.classList.remove("active");
        onBranchPanelOpenChanged(false);
      }
    }

    async function copySessionPath() {
      const ok = await copyText(sessionFilePath());
      elements.copySessionPath.textContent = ok ? t("copiedBtn") : t("failedBtn");
      global.setTimeout(() => {
        elements.copySessionPath.textContent = t("copyBtn");
      }, 1200);
    }

    function bind() {
      if (bound) return;
      bound = true;
      elements.toggleBranches?.addEventListener("click", toggleBranchPanel);
      elements.usageStrip?.addEventListener("click", toggleStatsPanel);
      elements.copySessionPath?.addEventListener("click", copySessionPath);
      getDocument()?.addEventListener("click", (event) => dismissPanelsForTarget(event.target));
    }

    return Object.freeze({
      bind,
      calcStats,
      closeTopPanels,
      copySessionPath,
      dismissPanelsForTarget,
      sessionFilePath,
      toggleBranchPanel,
      toggleStatsPanel,
      updateStatsPanel,
    });
  }

  Code.ui.panels = Object.freeze({
    calculateSessionStats,
    countSessionMessages,
    createPanelsFeature,
    formatSessionSource,
    formatSessionTimestamp,
    resolveSessionFilePath,
    sessionSourceI18nKey,
  });
})(window);
