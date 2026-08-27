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

  function hasImageContent(messages) {
    return (Array.isArray(messages) ? messages : []).some((message) => (
      Array.isArray(message?.content)
      && message.content.some((part) => part?.type === "image_url")
    ));
  }

  function projectMessagesWithoutImages(messages) {
    return (Array.isArray(messages) ? messages : []).map((message) => {
      if (!message || typeof message !== "object") return message;
      if (!Array.isArray(message.content)) return { ...message };
      const content = message.content
        .filter((part) => part?.type !== "image_url")
        .map((part) => (part && typeof part === "object" ? { ...part } : part));
      if (content.length === 0) {
        content.push({
          type: "text",
          text: "[Image omitted for a text-only compatibility retry]",
        });
      }
      return { ...message, content };
    });
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

  function createToolProtocolError(message) {
    const error = new Error(String(message || "Tool protocol history is invalid"));
    error.code = "tool_protocol_error";
    error.errorCode = "tool_protocol_error";
    error.transient = false;
    return error;
  }

  function toolResultSignature(message) {
    return JSON.stringify({
      content: getMessageText(message),
      action: String(message?.meta?.action || ""),
    });
  }

  function recoveredToolResultMessage(toolCall) {
    const toolCallId = String(toolCall?.id || "");
    const action = String(toolCall?.function?.name || toolCall?.name || "");
    return {
      role: "tool-result",
      content: JSON.stringify({
        ok: false,
        action,
        errorCode: "missing_tool_result",
        unknownState: true,
        notReplayed: true,
        error: "The historical tool result was unavailable and was not replayed.",
      }),
      meta: {
        action,
        toolCallId,
        native: true,
        protocolRecovery: true,
      },
    };
  }

  function canonicalizeSteerToolResultOrder(messages) {
    const source = Array.isArray(messages) ? messages : [];
    const output = [];
    let index = 0;
    while (index < source.length) {
      const message = source[index];
      const toolCalls = message?.role === "assistant" && Array.isArray(message.meta?.toolCalls)
        ? message.meta.toolCalls.filter((call) => String(call?.id || ""))
        : [];
      if (toolCalls.length === 0) {
        if (
          ["tool-call", "tool-result"].includes(message?.role)
          && String(message.meta?.toolCallId || "")
        ) {
          throw createToolProtocolError(
            "Orphan tool evidence could not be bound to one assistant declaration; no model request was sent",
          );
        }
        output.push(message);
        index += 1;
        continue;
      }

      const callIds = toolCalls.map((call) => String(call.id));
      if (new Set(callIds).size !== callIds.length) {
        throw createToolProtocolError(
          "Assistant declared duplicate tool call IDs; no model request was sent",
        );
      }
      const callIdSet = new Set(callIds);
      let end = index + 1;
      while (end < source.length && source[end]?.role !== "assistant") end += 1;

      const results = new Map(callIds.map((callId) => [callId, []]));
      const consumed = new Set();
      for (let candidateIndex = index + 1; candidateIndex < end; candidateIndex += 1) {
        const candidate = source[candidateIndex];
        const toolCallId = String(candidate?.meta?.toolCallId || "");
        if (candidate?.role === "tool-result" && callIdSet.has(toolCallId)) {
          results.get(toolCallId).push(candidate);
          consumed.add(candidateIndex);
        }
      }

      output.push(message);
      toolCalls.forEach((toolCall) => {
        const toolCallId = String(toolCall.id);
        const matches = results.get(toolCallId) || [];
        if (matches.length > 0) {
          const signatures = new Set(matches.map(toolResultSignature));
          if (signatures.size > 1) {
            throw createToolProtocolError(
              "Conflicting duplicate tool results were found; no model request was sent",
            );
          }
          output.push(matches[0]);
        } else {
          output.push(recoveredToolResultMessage(toolCall));
        }
      });
      for (let candidateIndex = index + 1; candidateIndex < end; candidateIndex += 1) {
        if (consumed.has(candidateIndex)) continue;
        const candidate = source[candidateIndex];
        const candidateToolCallId = String(candidate?.meta?.toolCallId || "");
        if (
          candidateToolCallId
          && (
            candidate?.role === "tool-result"
            || (candidate?.role === "tool-call" && !callIdSet.has(candidateToolCallId))
          )
        ) {
          throw createToolProtocolError(
            "Orphan tool evidence could not be bound to one assistant declaration; no model request was sent",
          );
        }
        output.push(candidate);
      }
      index = end;
    }

    return output;
  }

  function buildModelRequestMessages(messages, includeNativeTools = true) {
    const result = [];
    let pendingToolCallIds = new Set();
    let lastAssistantWithCallsIndex = -1;
    const requestMessages = includeNativeTools
      ? canonicalizeSteerToolResultOrder(messages)
      : (Array.isArray(messages) ? messages : []);

    for (const message of requestMessages) {
      if (!message || message.streaming) continue;

      const mapped = mapMessageForApi(message, includeNativeTools);
      if (!mapped) {
        // Visual tool-call rows never establish API protocol state. Only the
        // originating assistant.meta.toolCalls declaration can do that.
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
    canonicalizeSteerToolResultOrder,
    hasImageContent,
    mapMessageForApi,
    projectMessagesWithoutImages,
  });
})(window);
