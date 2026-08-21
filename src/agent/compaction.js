(function initializeCodeAgentCompaction(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before compaction");

  const RECENT_CONTEXT_ROUND_COUNT = 3;
  const MIN_COMPACTION_API_MESSAGES = 6;
  const UNKNOWN_CONTEXT_LIMIT = 128000;
  const CONTEXT_BUDGET_KEY = "code-context-budget";
  const modelCapabilities = new Map();
  let selectedContextBudget = null;

  function capabilityPriority(capability) {
    if (capability?.contextWindowHard) return 100;
    return {
      official: 40,
      stale_official: 39,
      family: 20,
      unknown: 10,
    }[String(capability?.contextWindowSource || "")] || 0;
  }

  function isCompactSummaryMessage(message) {
    return message?.meta?.kind === "compact-summary";
  }

  function getModelContextMessages(messages, isDetachedMessage = null) {
    const shouldDetach = typeof isDetachedMessage === "function"
      ? isDetachedMessage
      : () => false;
    const visible = (Array.isArray(messages) ? messages : [])
      .filter((message) => !shouldDetach(message));
    let latestSummaryIndex = -1;
    visible.forEach((message, index) => {
      if (isCompactSummaryMessage(message)) latestSummaryIndex = index;
    });
    return latestSummaryIndex >= 0 ? visible.slice(latestSummaryIndex) : visible;
  }

  function setModelContextCatalog(entries) {
    modelCapabilities.clear();
    for (const entry of Array.isArray(entries) ? entries : []) {
      const id = String(entry?.id || "").trim().replace(/^models\//, "");
      const tokens = Number(entry?.contextWindowTokens);
      if (!id || !Number.isInteger(tokens) || tokens < 1024 || tokens > 2000000) continue;
      const previous = modelCapabilities.get(id.toLowerCase());
      const source = ["metadata", "official", "stale_official", "family", "unknown"].includes(entry.contextWindowSource)
        ? entry.contextWindowSource
        : "unknown";
      let normalized = {
        contextWindowTokens: tokens,
        contextWindowSource: source,
        contextWindowHard: Boolean(entry.contextWindowHard),
        maxOutputTokens: entry.maxOutputTokens != null
          && Number.isInteger(Number(entry.maxOutputTokens))
          && Number(entry.maxOutputTokens) >= 1024
          && Number(entry.maxOutputTokens) <= 2000000
          ? Number(entry.maxOutputTokens)
          : null,
        officialProvider: String(entry.officialProvider || ""),
        officialCatalogRevision: String(entry.officialCatalogRevision || ""),
      };
      if (previous) {
        const previousPriority = capabilityPriority(previous);
        const normalizedPriority = capabilityPriority(normalized);
        if (previousPriority !== normalizedPriority) {
          normalized = normalizedPriority > previousPriority ? normalized : previous;
        } else if (previous.contextWindowTokens <= normalized.contextWindowTokens) {
          normalized = previous;
        }
      }
      modelCapabilities.set(id.toLowerCase(), normalized);
    }
  }

  function setContextBudgetTokens(value) {
    const tokens = Number(value);
    selectedContextBudget = value == null || value === "auto"
      ? null
      : (Number.isInteger(tokens) && tokens >= 1024 && tokens <= 2000000 ? tokens : null);
    return selectedContextBudget;
  }

  function getContextBudgetTokens() { return selectedContextBudget; }

  function getModelContextResolution(model, maxTokens = 4096) {
    const capability = modelCapabilities.get(String(model || "").toLowerCase()) || {
      contextWindowTokens: UNKNOWN_CONTEXT_LIMIT,
      contextWindowSource: "unknown",
      contextWindowHard: false,
    };
    const budget = getContextBudgetTokens();
    let contextLimit = budget == null ? capability.contextWindowTokens : budget;
    const budgetClamped = capability.contextWindowHard && contextLimit > capability.contextWindowTokens;
    const budgetAboveEstimate = !capability.contextWindowHard && contextLimit > capability.contextWindowTokens;
    if (budgetClamped) contextLimit = capability.contextWindowTokens;
    const safetyMarginTokens = Math.max(4096, Math.floor(contextLimit * 0.05));
    const rawAvailableInputTokens = contextLimit - Number(maxTokens || 0) - safetyMarginTokens;
    const availableInputTokens = Math.max(1024, rawAvailableInputTokens);
    return {
      ...capability,
      contextBudgetTokens: budget,
      contextLimit,
      safetyMarginTokens,
      availableInputTokens,
      compressionTriggerTokens: Math.min(Math.floor(contextLimit * 0.9), availableInputTokens),
      inputBudgetInsufficient: rawAvailableInputTokens < 1024,
      budgetClamped,
      budgetAboveEstimate,
    };
  }

  function getModelContextLimit(model) {
    return getModelContextResolution(model).contextLimit;
  }

  function serverKeepCount(messageCount) {
    return Math.max(2, Math.min(6, Math.floor(Math.max(0, messageCount) / 4)));
  }

  function resolveRequestKeepCount(prefixCount) {
    let keepCount = 2;
    for (let attempt = 0; attempt < 6; attempt += 1) {
      const nextKeepCount = serverKeepCount(prefixCount + keepCount);
      if (nextKeepCount === keepCount) return keepCount;
      keepCount = nextKeepCount;
    }
    return keepCount;
  }

  function createMappedEntries(messages, mapMessageForApi) {
    if (typeof mapMessageForApi !== "function") return [];
    const entries = [];
    (Array.isArray(messages) ? messages : []).forEach((message, sourceIndex) => {
      const apiMessage = mapMessageForApi(message, false);
      if (apiMessage) entries.push({ sourceIndex, apiMessage });
    });
    return entries;
  }

  function findCompleteContextStart(
    messages,
    mappedEntries,
    isDetachedMessage,
    recentRoundCount,
  ) {
    const sourceMessages = Array.isArray(messages) ? messages : [];
    const mappedIndices = new Set(mappedEntries.map((entry) => entry.sourceIndex));
    const shouldDetach = typeof isDetachedMessage === "function"
      ? isDetachedMessage
      : () => false;
    const userRoundStarts = [];
    sourceMessages.forEach((message, index) => {
      if (
        message?.role === "user"
        && mappedIndices.has(index)
        && !shouldDetach(message)
      ) {
        userRoundStarts.push(index);
      }
    });

    if (userRoundStarts.length < recentRoundCount) return 0;
    const latestRoundsStart = userRoundStarts[userRoundStarts.length - recentRoundCount];
    const minimumTailEntry = mappedEntries[
      Math.max(0, mappedEntries.length - MIN_COMPACTION_API_MESSAGES)
    ];
    if (!minimumTailEntry) return latestRoundsStart;

    let containingRoundStart = 0;
    for (const roundStart of userRoundStarts) {
      if (roundStart > minimumTailEntry.sourceIndex) break;
      containingRoundStart = roundStart;
    }
    return Math.min(latestRoundsStart, containingRoundStart);
  }

  function buildManualCompactionPlan(messages, options = {}) {
    const sourceMessages = Array.isArray(messages) ? messages : [];
    const mapMessageForApi = options.mapMessageForApi;
    const getMessageText = typeof options.getMessageText === "function"
      ? options.getMessageText
      : (message) => String(message?.content || "");
    const requestedRoundCount = Number(options.recentRoundCount);
    const recentRoundCount = Number.isFinite(requestedRoundCount)
      ? Math.max(1, Math.floor(requestedRoundCount))
      : RECENT_CONTEXT_ROUND_COUNT;
    const durableSystemMessages = sourceMessages.filter(
      (message) => message?.meta?.kind === "import-boundary",
    );
    const compactableMessages = sourceMessages.filter(
      (message) => message?.meta?.kind !== "import-boundary",
    );
    const compactableEntries = createMappedEntries(compactableMessages, mapMessageForApi);
    const keepStartIndex = findCompleteContextStart(
      compactableMessages,
      compactableEntries,
      options.isDetachedMessage,
      recentRoundCount,
    );
    const removedMessages = compactableMessages.slice(0, keepStartIndex);
    const keptMessages = compactableMessages.slice(keepStartIndex);
    const removedEntries = createMappedEntries(removedMessages, mapMessageForApi);
    const keptEntries = createMappedEntries(keptMessages, mapMessageForApi);
    const durableEntries = createMappedEntries(durableSystemMessages, mapMessageForApi);
    const summaryPrefixMessages = [
      ...durableEntries.map((entry) => entry.apiMessage),
      ...removedEntries.map((entry) => entry.apiMessage),
    ];
    const requestKeepCount = Math.min(
      keptEntries.length,
      resolveRequestKeepCount(summaryPrefixMessages.length),
    );
    const requestTail = requestKeepCount > 0
      ? keptEntries.slice(-requestKeepCount).map((entry) => entry.apiMessage)
      : [];
    const requestMessages = [...summaryPrefixMessages, ...requestTail];
    const totalChars = removedEntries.reduce(
      (sum, entry) => sum + getMessageText(entry.apiMessage).length,
      0,
    );
    const estimatedTokens = Math.ceil(totalChars / 3.2);
    const estimatedSaved = Math.ceil(estimatedTokens * 0.7);
    const canCompact = (
      compactableEntries.length >= MIN_COMPACTION_API_MESSAGES
      && removedEntries.length > 0
      && requestMessages.length >= MIN_COMPACTION_API_MESSAGES
      && serverKeepCount(requestMessages.length) === requestKeepCount
    );

    return {
      canCompact,
      compactableApiMessages: compactableEntries.map((entry) => entry.apiMessage),
      compactableMessages,
      compressCount: removedEntries.length,
      durableSystemMessages,
      estimatedSaved,
      estimatedTokens,
      keepCount: keptEntries.length,
      keptMessages,
      recentRoundCount,
      removedMessages,
      requestKeepCount,
      requestMessages,
    };
  }

  function createCompactSummaryMessage(result, options = {}) {
    const compressed = Math.max(
      0,
      Number(options.compressed ?? result?.compressed) || 0,
    );
    const defaultEstimatedSaved = Math.ceil(compressed * 3000 * 0.7);
    const estimatedSaved = Math.max(
      0,
      Number(options.estimatedSaved ?? defaultEstimatedSaved) || 0,
    );
    const summary = String(result?.summary || "").trim();
    return {
      role: "assistant",
      content: `上下文压缩摘要（${compressed} 条消息）\n\n${summary}`,
      meta: {
        kind: "compact-summary",
        compressed,
        estimatedSaved,
      },
      _time: String(options.createdAt || ""),
    };
  }

  agent.compaction = Object.freeze({
    RECENT_CONTEXT_ROUND_COUNT,
    buildManualCompactionPlan,
    createCompactSummaryMessage,
    CONTEXT_BUDGET_KEY,
    getContextBudgetTokens,
    getModelContextLimit,
    getModelContextResolution,
    getModelContextMessages,
    isCompactSummaryMessage,
    serverKeepCount,
    setContextBudgetTokens,
    setModelContextCatalog,
  });
})(window);
