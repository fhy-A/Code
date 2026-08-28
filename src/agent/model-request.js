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

  const GENERATED_ASSET_ID_PATTERN = /^ga1_[A-Za-z0-9_-]{32,96}$/;
  const GENERATED_ASSET_MIME_TYPES = new Set([
    "image/jpeg",
    "image/png",
    "image/webp",
  ]);
  const GENERATED_ASSET_MAX_BYTES = 20 * 1024 * 1024;
  const GENERATED_ASSET_MAX_PIXELS = 40_000_000;

  function boundedInteger(value, minimum, maximum) {
    return Number.isInteger(value) && value >= minimum && value <= maximum
      ? value
      : null;
  }

  function projectAuthoritativeGeneratedAsset(asset) {
    if (!asset || typeof asset !== "object" || Array.isArray(asset)) return null;
    const assetId = String(asset.assetId || "");
    const mimeType = String(asset.mimeType || "").toLowerCase();
    const width = boundedInteger(asset.width, 1, GENERATED_ASSET_MAX_PIXELS);
    const height = boundedInteger(asset.height, 1, GENERATED_ASSET_MAX_PIXELS);
    const byteLength = boundedInteger(asset.byteLength, 1, GENERATED_ASSET_MAX_BYTES);
    if (
      !GENERATED_ASSET_ID_PATTERN.test(assetId)
      || !GENERATED_ASSET_MIME_TYPES.has(mimeType)
      || width === null
      || height === null
      || width * height > GENERATED_ASSET_MAX_PIXELS
      || byteLength === null
    ) {
      return null;
    }
    return { assetId, mimeType, width, height, byteLength };
  }

  function projectGeneratedImageHistoryResult(result) {
    if (!result || typeof result !== "object" || Array.isArray(result)) return null;
    if (result.action && result.action !== "generate_image") return null;

    if (result.ok === true) {
      if (!Array.isArray(result.assets) || result.assets.length < 1 || result.assets.length > 4) {
        return null;
      }
      const assets = result.assets.map(projectAuthoritativeGeneratedAsset);
      if (assets.some((asset) => !asset)) return null;

      const count = result.count === undefined
        ? assets.length
        : boundedInteger(result.count, 1, 4);
      const requested = result.requested === undefined
        ? assets.length
        : boundedInteger(result.requested, 1, 4);
      const succeeded = result.succeeded === undefined
        ? assets.length
        : boundedInteger(result.succeeded, 1, 4);
      const failed = result.failed === undefined
        ? requested - succeeded
        : boundedInteger(result.failed, 0, 4);
      if (
        count === null
        || requested === null
        || succeeded === null
        || failed === null
        || count !== assets.length
        || succeeded !== assets.length
        || succeeded + failed !== requested
      ) {
        return null;
      }
      const partial = succeeded > 0 && failed > 0;
      if (result.partial !== undefined && result.partial !== partial) return null;
      return {
        action: "generate_image",
        authoritativeGeneratedAssets: true,
        ok: true,
        count,
        requested,
        succeeded,
        failed,
        partial,
        assets,
        ...(result.outcomeUnknown === true ? { outcomeUnknown: true } : {}),
        ...(result.notReplayed === true ? { notReplayed: true } : {}),
      };
    }

    if (result.ok !== false) return null;
    const projection = {
      action: "generate_image",
      authoritativeGeneratedAssets: true,
      ok: false,
    };
    const errorCode = String(result.errorCode || "");
    if (/^[a-z][a-z0-9_]{0,63}$/.test(errorCode)) projection.errorCode = errorCode;
    const countKeys = ["requested", "succeeded", "failed"];
    for (const key of countKeys) {
      if (result[key] === undefined) continue;
      const value = boundedInteger(result[key], 0, 4);
      if (value === null) return null;
      projection[key] = value;
    }
    if (
      projection.requested !== undefined
      && projection.succeeded !== undefined
      && projection.failed !== undefined
      && (
        projection.succeeded !== 0
        || projection.succeeded + projection.failed !== projection.requested
      )
    ) {
      return null;
    }
    if (typeof result.partial === "boolean") projection.partial = result.partial;
    if (typeof result.retryable === "boolean") projection.retryable = result.retryable;
    if (result.outcomeUnknown === true) projection.outcomeUnknown = true;
    if (result.notReplayed === true) projection.notReplayed = true;
    return projection;
  }

  function getModelToolResultText(message) {
    const fallback = getMessageText(message);
    if (message?.meta?.action !== "generate_image") return fallback;
    const projection = projectGeneratedImageHistoryResult(message.meta?.result);
    return projection ? JSON.stringify(projection) : fallback;
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
      const content = getModelToolResultText(message);
      if (includeNativeTools && message.meta?.toolCallId) {
        return {
          role: "tool",
          tool_call_id: message.meta.toolCallId,
          content,
        };
      }
      return { role: "user", content: `【工具结果】\n${content}` };
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
      content: getModelToolResultText(message),
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
