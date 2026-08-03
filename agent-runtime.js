(function attachAgentRuntime(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before agent runtime");

  const POLL_DELAYS = [500, 1000, 2000, 4000, 8000];
  const SSE_VISUAL_CHUNK_CHARS = 48;
  const SSE_VISUAL_MAX_CHUNKS = 12;
  const SSE_BATCH_MAX_PAUSES = 8;
  const SSE_BACKLOG_FRAMES_PER_PAINT = 48;
  const SSE_BATCH_PACE_MS = 16;
  const AGENT_EVENT_PROTOCOL_VERSION = 1;
  let latestStreamDiagnostic = null;

  const streamDiagnostics = Object.freeze({
    snapshot() {
      return latestStreamDiagnostic ? { ...latestStreamDiagnostic } : null;
    },
  });

  function sleep(ms, signal) {
    return new Promise((resolve, reject) => {
      if (signal?.aborted) {
        reject(new DOMException("Aborted", "AbortError"));
        return;
      }
      const timer = setTimeout(resolve, ms);
      signal?.addEventListener("abort", () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      }, { once: true });
    });
  }

  async function apiJson(url, options = {}) {
    const response = await fetch(url, options);
    let data = null;
    try {
      data = await response.json();
    } catch (_) {
      data = null;
    }
    if (!response.ok) {
      const error = new Error(data?.error || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return data || {};
  }

  function encodeSse(data) {
    return new TextEncoder().encode(`data: ${data}\n\n`);
  }

  function normalizeAgentEvent(rawEvent) {
    const diagnostics = [];
    if (!rawEvent || typeof rawEvent !== "object" || Array.isArray(rawEvent)) {
      return {
        event: null,
        seq: 0,
        sourceProtocolVersion: 0,
        diagnostics: ["invalid_event_envelope"],
      };
    }

    const seq = Number(rawEvent.seq);
    if (!Number.isInteger(seq) || seq <= 0) {
      return {
        event: null,
        seq: 0,
        sourceProtocolVersion: 0,
        diagnostics: ["invalid_event_seq"],
      };
    }

    let sourceProtocolVersion = 0;
    if (rawEvent.protocolVersion == null) {
      diagnostics.push("legacy_unversioned_event");
    } else if (
      Number.isInteger(rawEvent.protocolVersion)
      && rawEvent.protocolVersion >= 1
    ) {
      sourceProtocolVersion = rawEvent.protocolVersion;
      if (sourceProtocolVersion > AGENT_EVENT_PROTOCOL_VERSION) {
        diagnostics.push("future_protocol_version");
      }
    } else {
      diagnostics.push("invalid_protocol_version");
    }

    const eventType = String(rawEvent.type || "").trim();
    if (!eventType) {
      return {
        event: null,
        seq,
        sourceProtocolVersion,
        diagnostics: [...diagnostics, "invalid_event_type"],
      };
    }

    const data = rawEvent.data && typeof rawEvent.data === "object" && !Array.isArray(rawEvent.data)
      ? { ...rawEvent.data }
      : {};
    if (data !== rawEvent.data) diagnostics.push("invalid_event_data");

    return {
      event: {
        protocolVersion: AGENT_EVENT_PROTOCOL_VERSION,
        seq,
        type: eventType,
        data,
        createdAt: String(rawEvent.createdAt || ""),
      },
      seq,
      sourceProtocolVersion,
      diagnostics,
    };
  }

  function splitTextForProjection(text) {
    const codePoints = Array.from(String(text || ""));
    if (codePoints.length <= SSE_VISUAL_CHUNK_CHARS) return [String(text || "")];
    const chunkCount = Math.min(
      SSE_VISUAL_MAX_CHUNKS,
      Math.ceil(codePoints.length / SSE_VISUAL_CHUNK_CHARS),
    );
    const chunkSize = Math.ceil(codePoints.length / chunkCount);
    const chunks = [];
    for (let index = 0; index < codePoints.length; index += chunkSize) {
      chunks.push(codePoints.slice(index, index + chunkSize).join(""));
    }
    return chunks;
  }

  function expandSseDataForProjection(rawData) {
    const value = String(rawData ?? "");
    if (!value || value === "[DONE]" || value.startsWith("[ERROR]")) return [value];
    let frame;
    try {
      frame = JSON.parse(value);
    } catch (_) {
      return [value];
    }
    const choices = Array.isArray(frame?.choices) ? frame.choices : [];
    if (choices.length !== 1 || !choices[0]?.delta || typeof choices[0].delta !== "object") {
      return [value];
    }
    const delta = choices[0].delta;
    if (delta.tool_calls || delta.function_call) return [value];
    const textFields = ["content", "reasoning_content", "reasoning", "thinking", "text"]
      .filter((field) => typeof delta[field] === "string" && delta[field].length > 0);
    if (textFields.length !== 1) return [value];
    const field = textFields[0];
    const chunks = splitTextForProjection(delta[field]);
    if (chunks.length === 1) return [value];

    return chunks.map((chunk, index) => {
      const isFirst = index === 0;
      const isLast = index === chunks.length - 1;
      const projectedDelta = { ...delta, [field]: chunk };
      if (!isFirst) delete projectedDelta.role;
      const projectedChoice = { ...choices[0], delta: projectedDelta };
      if (!isLast) {
        delete projectedChoice.finish_reason;
        delete projectedChoice.finish_details;
      }
      const projectedFrame = {
        ...frame,
        choices: [projectedChoice],
      };
      if (!isLast) delete projectedFrame.usage;
      return JSON.stringify(projectedFrame);
    });
  }

  function isTextProjectionFrame(data) {
    if (!data || data === "[DONE]" || String(data).startsWith("[ERROR]")) return false;
    try {
      const frame = JSON.parse(data);
      const delta = frame?.choices?.[0]?.delta;
      return Boolean(delta && ["content", "reasoning_content", "reasoning", "thinking", "text"]
        .some((field) => typeof delta[field] === "string" && delta[field].length > 0));
    } catch (_) {
      return false;
    }
  }

  function projectionTextStats(data) {
    if (typeof data !== "string" || data === "[DONE]" || data.startsWith("[ERROR]")) {
      return { reasoningChars: 0, contentChars: 0 };
    }
    try {
      const frame = JSON.parse(data);
      const choice = frame?.choices?.[0] || {};
      const delta = choice.delta || {};
      const textLength = (value) => {
        if (typeof value === "string") return value.length;
        if (!Array.isArray(value)) return 0;
        return value.reduce((total, part) => {
          if (typeof part === "string") return total + part.length;
          const text = part?.text || part?.content || part?.value || "";
          return total + (typeof text === "string" ? text.length : 0);
        }, 0);
      };
      let reasoningChars = textLength(
        delta.reasoning_content ?? delta.reasoning ?? delta.thinking,
      );
      let contentChars = textLength(delta.content ?? choice.message?.content);
      if (frame?.type === "content_block_delta") {
        if (frame.delta?.type === "thinking_delta") {
          reasoningChars += textLength(frame.delta.thinking);
        }
        if (frame.delta?.type === "text_delta") {
          contentChars += textLength(frame.delta.text);
        }
      }
      if (frame?.type === "response.output_text.delta") {
        contentChars += textLength(frame.delta);
      }
      if (frame?.type === "response.reasoning_text.delta") {
        reasoningChars += textLength(frame.delta);
      }
      return { reasoningChars, contentChars };
    } catch (_) {
      return { reasoningChars: 0, contentChars: 0 };
    }
  }

  async function createRun({ sessionId, payload, baseUrl, keys, signal }) {
    return apiJson("/api/runtime/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId, payload, baseUrl, keys }),
      signal,
    });
  }

  async function createAgentRun({
    sessionId,
    clientRequestId = "",
    payload,
    baseUrl,
    keys,
    allowedTools,
    toolBudgets,
    maxRounds,
    permissionProfile = "read",
    cwd = "",
    contextLimit,
    signal,
  }) {
    return apiJson("/api/agent/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sessionId,
        clientRequestId,
        payload,
        baseUrl,
        keys,
        allowedTools,
        toolBudgets,
        maxRounds,
        permissionProfile,
        cwd,
        contextLimit,
      }),
      signal,
    });
  }

  async function getAgentRun(agentRunId, { cursor = 0, wait = 0, signal } = {}) {
    return apiJson(
      `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=${Number(cursor) || 0}&wait=${Number(wait) || 0}`,
      { signal },
    );
  }

  async function resumeAgentRun(agentRunId, { keys = [], baseUrl = "", signal } = {}) {
    return apiJson(`/api/agent/runs/${encodeURIComponent(agentRunId)}/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys, baseUrl }),
      signal,
    });
  }

  async function submitAgentInput(agentRunId, { answers = [], signal } = {}) {
    return apiJson(`/api/agent/runs/${encodeURIComponent(agentRunId)}/input`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
      signal,
    });
  }

  async function steerAgentRun(
    agentRunId,
    { message, clientRequestId = "", signal } = {},
  ) {
    return apiJson(`/api/agent/runs/${encodeURIComponent(agentRunId)}/steer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, clientRequestId }),
      signal,
    });
  }

  async function submitAgentAuthorization(
    agentRunId,
    { authorizationId = "", decision = "", signal } = {},
  ) {
    return apiJson(`/api/agent/runs/${encodeURIComponent(agentRunId)}/authorization`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ authorizationId, decision }),
      signal,
    });
  }

  async function watchAgentRun({
    agentRunId,
    cursor = 0,
    signal,
    onEvent,
    onSnapshot,
    onReconnect,
    onReconnected,
  } = {}) {
    let activeCursor = Math.max(0, Number(cursor) || 0);
    let failures = 0;

    while (true) {
      if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
      let snapshot;
      try {
        snapshot = await getAgentRun(agentRunId, { cursor: activeCursor, wait: 25, signal });
        if (failures > 0) onReconnected?.({ attempts: failures });
        failures = 0;
      } catch (error) {
        if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
        if (Number(error?.status) === 404) throw error;
        const delay = POLL_DELAYS[Math.min(failures, POLL_DELAYS.length - 1)];
        failures += 1;
        onReconnect?.({
          attempt: failures,
          delayMs: delay,
          nextRetryAt: Date.now() + delay,
          error,
        });
        await sleep(delay, signal);
        continue;
      }

      const events = Array.isArray(snapshot.events) ? snapshot.events : [];
      for (const rawEvent of events) {
        const normalized = normalizeAgentEvent(rawEvent);
        const seq = normalized.seq;
        if (seq <= activeCursor) continue;
        // Advance the cursor only after the event projection succeeds. A page
        // reload can then safely replay the same durable event.
        if (normalized.event) {
          await onEvent?.(normalized.event, snapshot, {
            sourceProtocolVersion: normalized.sourceProtocolVersion,
            diagnostics: [...normalized.diagnostics],
          });
        }
        activeCursor = seq;
      }
      await onSnapshot?.(snapshot, activeCursor);

      if ([
        "completed",
        "failed",
        "cancelled",
        "waiting_credentials",
        "waiting_user_input",
        "waiting_authorization",
      ].includes(snapshot.status)) {
        return { ...snapshot, nextCursor: activeCursor };
      }
    }
  }

  function openSseResponse({
    runId = "",
    sessionId = "",
    payload = {},
    baseUrl = "",
    keys = [],
    signal,
    onRunCreated,
    onReconnect,
    onReconnected,
    onStreamProgress,
  } = {}) {
    let activeRunId = String(runId || "");
    let cursor = 0;
    let pollStarted = false;
    let firstDeltaObserved = false;
    const streamDiagnostic = {
      schemaVersion: 1,
      runtimeRunId: activeRunId,
      attachedAt: Date.now(),
      pollStartedAt: 0,
      firstDeltaAt: 0,
      firstReasoningAt: 0,
      firstContentAt: 0,
      lastContentAt: 0,
      completedAt: 0,
      firstBatchEventCount: 0,
      batchCount: 0,
      eventCount: 0,
      maxBatchEventCount: 0,
      reasoningFrameCount: 0,
      contentFrameCount: 0,
      reasoningChars: 0,
      contentChars: 0,
      status: "attaching",
    };
    latestStreamDiagnostic = streamDiagnostic;

    function reportStreamProgress(sample) {
      const phase = String(sample?.phase || "");
      const at = Number(sample?.at || Date.now());
      streamDiagnostic.runtimeRunId = activeRunId;
      if (phase === "poll-started") {
        streamDiagnostic.pollStartedAt = at;
        streamDiagnostic.status = "polling";
      } else if (phase === "first-delta") {
        streamDiagnostic.firstDeltaAt = at;
        streamDiagnostic.firstBatchEventCount = Number(sample?.pendingEventCount || 0);
        streamDiagnostic.status = "streaming";
      } else if (phase === "completed") {
        streamDiagnostic.completedAt = at;
        streamDiagnostic.status = "completed";
      }
      onStreamProgress?.(sample);
    }

    const stream = new ReadableStream({
      async start(controller) {
        try {
          if (!activeRunId) {
            const created = await createRun({ sessionId, payload, baseUrl, keys, signal });
            activeRunId = String(created.runId || "");
            if (!activeRunId) throw new Error("Runtime did not return a runId");
            streamDiagnostic.runtimeRunId = activeRunId;
            onRunCreated?.(activeRunId);
          }

          let failures = 0;
          while (true) {
            if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
            let snapshot;
            try {
              if (!pollStarted) {
                pollStarted = true;
                reportStreamProgress({
                  phase: "poll-started",
                  at: Date.now(),
                  cursor,
                });
              }
              snapshot = await apiJson(
                `/api/runtime/runs/${encodeURIComponent(activeRunId)}?cursor=${cursor}&wait=25`,
                { signal },
              );
              if (failures > 0) onReconnected?.({ attempts: failures });
              failures = 0;
            } catch (error) {
              if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
              // A missing run cannot recover by polling forever. Surface it so
              // the normal run-recovery path can decide what to do next.
              if (Number(error?.status) === 404) throw error;
              const delay = POLL_DELAYS[Math.min(failures, POLL_DELAYS.length - 1)];
              failures += 1;
              onReconnect?.({
                attempt: failures,
                delayMs: delay,
                nextRetryAt: Date.now() + delay,
                error,
              });
              await sleep(delay, signal);
              continue;
            }

            const events = Array.isArray(snapshot.events) ? snapshot.events : [];
            const pendingEvents = events.filter((event) => Number(event?.seq || 0) > cursor);
            if (pendingEvents.length > 0) {
              streamDiagnostic.batchCount += 1;
              streamDiagnostic.eventCount += pendingEvents.length;
              streamDiagnostic.maxBatchEventCount = Math.max(
                streamDiagnostic.maxBatchEventCount,
                pendingEvents.length,
              );
            }
            if (!firstDeltaObserved && pendingEvents.length > 0) {
              firstDeltaObserved = true;
              reportStreamProgress({
                phase: "first-delta",
                at: Date.now(),
                cursor,
                pendingEventCount: pendingEvents.length,
              });
            }
            const projectionFrames = pendingEvents.flatMap((event) => (
              expandSseDataForProjection(event?.data).map((data, index, frames) => ({
                data,
                eventSeq: Number(event?.seq || 0),
                completesEvent: index === frames.length - 1,
              }))
            ));
            const textFrameCount = projectionFrames.filter((frame) => (
              isTextProjectionFrame(frame.data)
            )).length;
            const pauseEvery = textFrameCount > 1
              ? Math.min(
                SSE_BACKLOG_FRAMES_PER_PAINT,
                Math.max(1, Math.ceil((textFrameCount - 1) / SSE_BATCH_MAX_PAUSES)),
              )
              : 0;
            let projectedTextFrames = 0;

            for (const frame of projectionFrames) {
              controller.enqueue(encodeSse(frame.data));
              if (frame.completesEvent) cursor = frame.eventSeq;
              const textStats = projectionTextStats(frame.data);
              const observedAt = Date.now();
              if (textStats.reasoningChars > 0) {
                streamDiagnostic.firstReasoningAt ||= observedAt;
                streamDiagnostic.reasoningFrameCount += 1;
                streamDiagnostic.reasoningChars += textStats.reasoningChars;
              }
              if (textStats.contentChars > 0) {
                streamDiagnostic.firstContentAt ||= observedAt;
                streamDiagnostic.lastContentAt = observedAt;
                streamDiagnostic.contentFrameCount += 1;
                streamDiagnostic.contentChars += textStats.contentChars;
              }
              if (!isTextProjectionFrame(frame.data)) continue;
              projectedTextFrames += 1;
              const hasMoreText = projectedTextFrames < textFrameCount;
              if (hasMoreText && pauseEvery && projectedTextFrames % pauseEvery === 0) {
                await sleep(SSE_BATCH_PACE_MS, signal);
              }
            }

            for (const event of pendingEvents) {
              const seq = Number(event?.seq || 0);
              if (seq > cursor) cursor = seq;
            }

            if (snapshot.status === "completed") {
              reportStreamProgress({
                phase: "completed",
                at: Date.now(),
                cursor,
              });
              controller.close();
              return;
            }
            if (snapshot.status === "failed" || snapshot.status === "cancelled") {
              streamDiagnostic.completedAt = Date.now();
              streamDiagnostic.status = snapshot.status;
              const detail = JSON.stringify({
                message: snapshot.error || `Runtime ${snapshot.status}`,
                code: snapshot.errorCode || `runtime_${snapshot.status}`,
                status: snapshot.upstreamStatus || 0,
                transient: typeof snapshot.transient === "boolean"
                  ? snapshot.transient
                  : [408, 425, 429, 500, 502, 503, 504].includes(Number(snapshot.upstreamStatus || 0)),
              });
              controller.enqueue(encodeSse(`[ERROR]${detail}`));
              controller.close();
              return;
            }
          }
        } catch (error) {
          streamDiagnostic.completedAt = Date.now();
          streamDiagnostic.status = signal?.aborted ? "cancelled" : "failed";
          controller.error(error);
        }
      },
    });

    return Promise.resolve(new Response(stream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
    }));
  }

  async function cancelRun(runId) {
    if (!runId) return { ok: true };
    return apiJson(`/api/runtime/runs/${encodeURIComponent(runId)}`, { method: "DELETE" });
  }

  async function cancelAgentRun(agentRunId) {
    if (!agentRunId) return { ok: true };
    return apiJson(`/api/agent/runs/${encodeURIComponent(agentRunId)}`, { method: "DELETE" });
  }

  const runtime = Object.freeze({
    openSseResponse,
    cancelRun,
    createAgentRun,
    getAgentRun,
    resumeAgentRun,
    steerAgentRun,
    submitAgentInput,
    submitAgentAuthorization,
    normalizeAgentEvent,
    watchAgentRun,
    cancelAgentRun,
    streamDiagnostics,
  });
  agent.runtime = runtime;
})(window);
