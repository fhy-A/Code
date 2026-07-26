(function registerPanelsUi(global) {
  "use strict";

  const Code = global.Code;
  if (!Code?.ui) throw new Error("Code namespace must load before panels UI");

  function countSessionMessages(messages = []) {
    const visible = Array.isArray(messages) ? messages.filter(Boolean) : [];
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
    return String(value || "").slice(0, 16).replace("T", " ") || "-";
  }

  function calculateSessionStats(options = {}) {
    const messages = Array.isArray(options.messages) ? options.messages.filter(Boolean) : [];
    const usageStats = options.stats || {};
    const counts = countSessionMessages(messages);
    const input = usageStats.input;
    const output = usageStats.output;
    const cache = usageStats.cache || 0;
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
    const ctxLimit = getContextLimit(options.model || "");
    const contextPct = Math.min(100, (contextTokens / ctxLimit) * 100);
    return {
      counts,
      input,
      output,
      cache,
      cacheWrite,
      cacheWriteReported,
      contextTokens,
      ctxLimit,
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
    const getSelectedModel = options.getSelectedModel || (() => "");
    const getMessageText = options.getMessageText || ((msg) => String(msg?.content || ""));
    const getSystemPrompt = options.getSystemPrompt || (() => "");
    const getDocument = options.getDocument || (() => global.document);
    const copyText = options.copyText || (async () => false);
    const onRenderBranchTree = options.onRenderBranchTree || (() => {});
    const onRenderToolLog = options.onRenderToolLog || (() => {});
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
      });
    }

    function closeTopPanels() {
      elements.statsPanel?.classList.remove("open");
      elements.toolLogPanel?.classList.remove("open");
      elements.branchPanel?.classList.remove("open");
      elements.usageStrip?.classList.remove("active");
      elements.toolLogToggle?.classList.remove("active");
      elements.toggleBranches?.classList.remove("active");
      onBranchPanelOpenChanged(false);
    }

    function updateStatsPanel() {
      const stats = calcStats();
      elements.statInput.textContent = formatCompact(stats.input);
      elements.statOutput.textContent = formatCompact(stats.output);
      elements.statCache.textContent = formatCompact(stats.cache);
      elements.statContext.textContent = `${stats.contextPct.toFixed(0)}%`;
      elements.usageStrip.title = t("usageStripTitle")
        .replace("{current}", formatCompact(stats.contextTokens || 0))
        .replace("{limit}", formatCompact(stats.ctxLimit || 200000));

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
      elements.sessionFile.textContent = sessionFilePath(session);
      elements.sessionFile.title = `ID: ${getSessionId() || "-"}`;
      elements.msgUser.textContent = stats.counts.user;
      elements.msgAssistant.textContent = stats.counts.assistant;
      elements.msgTools.textContent = (stats.counts.toolCalls || 0) + (stats.counts.toolResults || 0);
      elements.msgTotal.textContent = stats.counts.total;
      elements.tokenInput.textContent = formatNumber(stats.input);
      elements.tokenOutput.textContent = formatNumber(stats.output);
      elements.tokenCache.textContent = formatNumber(stats.cache);
      if (elements.tokenCacheWriteRow) {
        elements.tokenCacheWriteRow.hidden = !stats.cacheWriteReported;
      }
      if (elements.tokenCacheWrite) {
        elements.tokenCacheWrite.textContent = formatNumber(stats.cacheWrite);
      }
      elements.tokenTotal.textContent = formatNumber((stats.input || 0) + (stats.output || 0));
      elements.tokenContext.textContent = `${stats.contextPct.toFixed(0)}%（${formatCompact(stats.contextTokens || 0)} / ${formatCompact(stats.ctxLimit || 200000)}）`;
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

    function toggleToolLogPanel() {
      const open = !elements.toolLogPanel.classList.contains("open");
      closeTopPanels();
      onRenderToolLog();
      elements.toolLogPanel.classList.toggle("open", open);
      elements.toolLogToggle.classList.toggle("active", open);
    }

    function toggleStatsPanel() {
      const open = !elements.statsPanel.classList.contains("open");
      closeTopPanels();
      elements.statsPanel.classList.toggle("open", open);
      elements.usageStrip.classList.toggle("active", open);
    }

    function dismissPanelsForTarget(target) {
      if (!target?.closest?.("#toolLogPanel") && !target?.closest?.("#toolLogToggle")) {
        elements.toolLogPanel?.classList.remove("open");
        elements.toolLogToggle?.classList.remove("active");
      }
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
      elements.toolLogToggle?.addEventListener("click", toggleToolLogPanel);
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
      toggleToolLogPanel,
      updateStatsPanel,
    });
  }

  Code.ui.panels = Object.freeze({
    calculateSessionStats,
    countSessionMessages,
    createPanelsFeature,
    formatSessionTimestamp,
    resolveSessionFilePath,
  });
})(window);
