(function initializeCodeAgentTools(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before tools");
  if (!agent.modelRequest) throw new Error("Code model request must load before tools");

  const { buildNativeToolCallMessage } = agent.modelRequest;

  function parseJsonLoose(text = "{}") {
    if (typeof text === "object" && text !== null) return text;
    try {
      return JSON.parse(text || "{}");
    } catch (_) {
      return {};
    }
  }

  function normalizeNativeToolCall(call) {
    const name = call?.function?.name || call?.name || "";
    const args = parseJsonLoose(call?.function?.arguments || call?.arguments || "{}");
    return {
      ...args,
      action: name,
      _native: true,
      _toolCallId: call?.id || `call_${Date.now()}_${Math.random().toString(16).slice(2)}`,
    };
  }

  function normalizeToolCallList(map) {
    return [...map.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([, call]) => buildNativeToolCallMessage(call))
      .filter((call) => call.function.name);
  }

  agent.tools = Object.freeze({
    normalizeNativeToolCall,
    normalizeToolCallList,
    parseJsonLoose,
  });
})(window);
