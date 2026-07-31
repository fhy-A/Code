(function initializeCodeAgentCompaction(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before compaction");

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

  agent.compaction = Object.freeze({
    getModelContextLimit,
    getModelContextMessages,
    isCompactSummaryMessage,
  });
})(window);
