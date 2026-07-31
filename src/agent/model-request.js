(function initializeCodeModelRequest(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before model request");

  function getMessageText(message) {
    const content = message?.content;
    if (!content) return "";
    if (Array.isArray(content)) {
      return content.find((part) => part?.type === "text")?.text || "";
    }
    return String(content);
  }

  function buildNativeToolCallMessage(toolCall) {
    return {
      id: toolCall?.id || `call_${Date.now()}`,
      type: toolCall?.type || "function",
      function: {
        name: toolCall?.function?.name || toolCall?.name || "",
        arguments: toolCall?.function?.arguments || toolCall?.arguments || "{}",
      },
    };
  }

  function mapMessageForApi(message, includeNativeTools = true) {
    if (!message || typeof message !== "object") return null;
    if (message.meta?.skipApi) return null;

    if (message.role === "system") {
      return { role: "system", content: getMessageText(message) };
    }

    if (message.role === "assistant") {
      const toolCalls = includeNativeTools ? (message.meta?.toolCalls || []) : [];
      if (toolCalls.length > 0) {
        return {
          role: "assistant",
          content: getMessageText(message),
          tool_calls: toolCalls.map(buildNativeToolCallMessage),
        };
      }
      return { role: "assistant", content: getMessageText(message) };
    }

    if (message.role === "tool-call") return null;

    if (message.role === "tool-result") {
      if (includeNativeTools && message.meta?.toolCallId) {
        return {
          role: "tool",
          tool_call_id: message.meta.toolCallId,
          content: getMessageText(message),
        };
      }
      return { role: "user", content: `【工具结果】\n${getMessageText(message)}` };
    }

    if (message.role === "user") {
      const content = message.content || "";
      return { role: "user", content };
    }

    return { role: "user", content: getMessageText(message) };
  }

  function buildModelRequestMessages(messages, includeNativeTools = true) {
    const result = [];
    let pendingToolCallIds = new Set();
    let lastAssistantWithCallsIndex = -1;

    for (const message of Array.isArray(messages) ? messages : []) {
      if (!message || message.streaming) continue;

      const mapped = mapMessageForApi(message, includeNativeTools);
      if (!mapped) {
        if (
          message.role === "tool-call"
          && message.meta?.toolCallId
          && !message.meta?.skipApi
        ) {
          pendingToolCallIds.add(message.meta.toolCallId);
        }
        continue;
      }

      if (mapped.role === "tool") {
        if (pendingToolCallIds.has(mapped.tool_call_id)) {
          pendingToolCallIds.delete(mapped.tool_call_id);
        } else {
          result.push({
            role: "user",
            content: `[Tool result]\n${mapped.content || ""}`,
          });
          continue;
        }
      }

      if (
        lastAssistantWithCallsIndex >= 0
        && pendingToolCallIds.size > 0
        && mapped.role !== "tool"
      ) {
        const previous = result[lastAssistantWithCallsIndex];
        if (previous?.tool_calls) {
          previous.tool_calls = previous.tool_calls.filter(
            (toolCall) => !pendingToolCallIds.has(toolCall.id),
          );
          if (previous.tool_calls.length === 0) delete previous.tool_calls;
        }
        lastAssistantWithCallsIndex = -1;
        pendingToolCallIds.clear();
      }

      result.push(mapped);
      if (mapped.role === "assistant" && mapped.tool_calls?.length > 0) {
        lastAssistantWithCallsIndex = result.length - 1;
        pendingToolCallIds = new Set(mapped.tool_calls.map((toolCall) => toolCall.id));
      } else if (mapped.role === "assistant") {
        lastAssistantWithCallsIndex = -1;
        pendingToolCallIds.clear();
      }
    }

    if (lastAssistantWithCallsIndex >= 0 && pendingToolCallIds.size > 0) {
      const previous = result[lastAssistantWithCallsIndex];
      if (previous?.tool_calls) {
        previous.tool_calls = previous.tool_calls.filter(
          (toolCall) => !pendingToolCallIds.has(toolCall.id),
        );
        if (previous.tool_calls.length === 0) delete previous.tool_calls;
      }
    }

    return result;
  }

  function assembleModelRequestPayload({
    model = "",
    tools = [],
    modelMessages = [],
    systemPrompt = "",
    includeSystemPrompt = true,
    temperature = 0.2,
    maxTokens = 0,
    thinkingLevel = "auto",
  } = {}) {
    const requestTools = Array.isArray(tools) ? tools : [];
    const payload = {
      model,
      stream: true,
      stream_options: { include_usage: true },
      temperature,
      max_tokens: maxTokens,
      messages: [
        ...(includeSystemPrompt ? [{ role: "system", content: systemPrompt }] : []),
        ...buildModelRequestMessages(modelMessages, requestTools.length > 0),
      ],
    };

    if (requestTools.length > 0) {
      payload.tools = requestTools;
      payload.tool_choice = "auto";
    }

    const thinkingMode = thinkingLevel || "auto";
    if (/claude|opus|sonnet|haiku/i.test(model)) {
      if (thinkingMode === "off") {
        payload.thinking = { type: "disabled" };
      } else {
        const budgets = { auto: 4000, high: 8000, max: 16000 };
        payload.thinking = {
          type: "enabled",
          budget_tokens: budgets[thinkingMode] || 4000,
        };
      }
    } else if (/o1|o3|o4/i.test(model)) {
      if (thinkingMode !== "off") {
        payload.reasoning_effort = thinkingMode === "max"
          ? "high"
          : thinkingMode === "high" ? "medium" : "low";
      }
    } else if (/gemini|nano-banana/i.test(model)) {
      const efforts = { high: "high", max: "high" };
      if (efforts[thinkingMode]) {
        payload.reasoning_effort = efforts[thinkingMode];
      }
    }

    return payload;
  }

  agent.modelRequest = Object.freeze({
    assembleModelRequestPayload,
    buildModelRequestMessages,
    buildNativeToolCallMessage,
    mapMessageForApi,
  });
})(window);
