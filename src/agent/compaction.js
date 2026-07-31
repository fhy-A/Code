(function initializeCodeAgentCompaction(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before compaction");

  const RECENT_CONTEXT_ROUND_COUNT = 3;
  const MIN_COMPACTION_API_MESSAGES = 6;

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

  function getModelContextLimit(model) {
    const normalized = String(model || "").toLowerCase().replace(/_/g, "-");
    const claudeVersion = normalized.match(/claude.*?(\d+)[.-](\d+)/);
    if (claudeVersion) {
      const major = Number(claudeVersion[1]);
      const minor = Number(claudeVersion[2]);
      if (major >= 5 || (major === 4 && minor >= 6)) return 1000000;
      return 200000;
    }
    if (/claude|opus|sonnet|haiku/i.test(normalized)) return 200000;
    if (/gpt-4\.1|gpt-5[.-][2-9]/i.test(normalized)) return 1000000;
    if (/gpt|o1|o3|o4|openai/i.test(normalized)) return 128000;
    if (/deepseek.*v4/i.test(normalized)) return 1000000;
    if (/deepseek/i.test(normalized)) return 128000;
    if (/gemini/i.test(normalized)) return 1000000;
    return 128000;
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
    getModelContextLimit,
    getModelContextMessages,
    isCompactSummaryMessage,
    serverKeepCount,
  });
})(window);
