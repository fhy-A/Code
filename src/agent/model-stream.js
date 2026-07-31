(function initializeCodeModelStream(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before model stream");

  function parseSseLine(line) {
    if (!line.startsWith("data:")) return null;

    const payload = line.slice(5).trim();
    if (!payload || payload === "[DONE]" || payload.startsWith("[ERROR]")) {
      return payload || null;
    }

    try {
      return JSON.parse(payload);
    } catch (_) {
      return null;
    }
  }

  function streamDeltaText(value) {
    if (typeof value === "string") return value;
    if (!Array.isArray(value)) return "";
    return value.map((part) => {
      if (typeof part === "string") return part;
      return part?.text || part?.content || part?.value || "";
    }).join("");
  }

  function extractStreamDelta(data) {
    const choice = data?.choices?.[0] || {};
    const delta = choice.delta || {};
    let reasoning = streamDeltaText(
      delta.reasoning_content ?? delta.reasoning ?? delta.thinking,
    );
    let text = streamDeltaText(delta.content ?? choice.message?.content);

    if (data?.type === "content_block_delta") {
      if (data.delta?.type === "thinking_delta") {
        reasoning += streamDeltaText(data.delta.thinking);
      }
      if (data.delta?.type === "text_delta") {
        text += streamDeltaText(data.delta.text);
      }
    }
    if (data?.type === "response.output_text.delta") {
      text += streamDeltaText(data.delta);
    }
    if (data?.type === "response.reasoning_text.delta") {
      reasoning += streamDeltaText(data.delta);
    }

    return { reasoning, text, delta, choice };
  }

  function mergeToolCallDelta(map, part) {
    const index = Number.isInteger(part.index) ? part.index : map.size;
    const existing = map.get(index) || {
      id: "",
      type: "function",
      function: { name: "", arguments: "" },
    };
    if (part.id) existing.id = part.id;
    if (part.type) existing.type = part.type;
    if (part.function?.name) existing.function.name = part.function.name;
    if (part.function?.arguments) {
      existing.function.arguments += part.function.arguments;
    }
    map.set(index, existing);
  }

  function combinedTurnText(rawThought, rawContent) {
    return rawThought ? `<think>${rawThought}</think>\n${rawContent}` : rawContent;
  }

  function createModelTurnAccumulator() {
    let rawThought = "";
    let rawContent = "";
    let completed = false;
    const toolCallsByIndex = new Map();

    function snapshot() {
      return {
        rawThought,
        rawContent,
        combinedText: combinedTurnText(rawThought, rawContent),
        completed,
      };
    }

    function consume(data) {
      if (typeof data === "string" && data.startsWith("[ERROR]")) {
        const rawError = data.slice(7).trim();
        let detail = {};
        try {
          detail = JSON.parse(rawError);
        } catch (_) {
          detail = {};
        }
        return {
          kind: "error",
          error: createModelRequestError(
            detail.message || rawError || "Stream interrupted",
            {
              status: Number(detail.status || 0),
              code: detail.code || "stream_error",
              transient: detail.transient !== false,
            },
          ),
          ...snapshot(),
        };
      }

      if (data === "[DONE]") {
        completed = true;
        return { kind: "done", ...snapshot() };
      }

      const { reasoning, text, delta, choice } = extractStreamDelta(data);
      let receivedToolCallDelta = false;

      if (Array.isArray(delta.tool_calls)) {
        delta.tool_calls.forEach((part) => mergeToolCallDelta(toolCallsByIndex, part));
        receivedToolCallDelta = delta.tool_calls.length > 0;
      }

      if (Array.isArray(choice.message?.tool_calls)) {
        choice.message.tool_calls.forEach((part, index) => (
          mergeToolCallDelta(toolCallsByIndex, { ...part, index })
        ));
        receivedToolCallDelta = receivedToolCallDelta
          || choice.message.tool_calls.length > 0;
      }

      if (reasoning) rawThought += reasoning;
      if (text) rawContent += text;

      return {
        kind: "delta",
        reasoning,
        text,
        usage: data?.usage,
        receivedToolCallDelta,
        ...snapshot(),
      };
    }

    return Object.freeze({
      consume,
      snapshot,
      getToolCallMap: () => toolCallsByIndex,
    });
  }

  function createModelRequestError(message, details = {}) {
    const error = new Error(String(message || "Model request failed"));
    error.status = Number(details.status || 0);
    error.code = String(details.code || "");
    error.transient = Boolean(details.transient);
    error.modelRequest = true;
    return error;
  }

  function isModelAccessDenied(status = 0, code = "", message = "") {
    const text = `${code || ""} ${message || ""}`.toLowerCase();
    return String(code || "") === "model_access_denied"
      || /no access to model|not authorized to access model|unauthorized model|无权访问模型|无权访问任何模型/.test(text);
  }

  function classifyModelRequestFailure(status = 0, code = "", message = "") {
    const numericStatus = Number(status || 0);
    if (isModelAccessDenied(numericStatus, code, message)) {
      return { code: "model_access_denied", transient: false };
    }
    const transient = [408, 425, 429, 500, 502, 503, 504].includes(numericStatus)
      || /upstream error|do request failed|timed out|timeout|network|fetch failed|connection/i.test(message);
    return { code: String(code || ""), transient };
  }

  function shouldRetryWithoutNativeTools(errorText = "") {
    return /(tool_choice|tools? (?:are )?not supported|unsupported (?:tool|function)|function calling (?:is )?not supported|unknown field.*tools|invalid.*tool_calls?)/i.test(errorText);
  }

  agent.modelStream = Object.freeze({
    parseSseLine,
    streamDeltaText,
    extractStreamDelta,
    mergeToolCallDelta,
    createModelTurnAccumulator,
    createModelRequestError,
    isModelAccessDenied,
    classifyModelRequestFailure,
    shouldRetryWithoutNativeTools,
  });
})(window);
