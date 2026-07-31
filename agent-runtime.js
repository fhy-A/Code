(function attachAgentRuntime(global) {
  "use strict";

  const POLL_DELAYS = [500, 1000, 2000, 4000, 8000];
  const SSE_VISUAL_CHUNK_CHARS = 48;
  const SSE_VISUAL_MAX_CHUNKS = 12;
  const SSE_BATCH_MAX_PAUSES = 8;
  const SSE_BATCH_PACE_MS = 16;

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
      for (const event of events) {
        const seq = Number(event?.seq || 0);
        if (seq <= activeCursor) continue;
        // Advance the cursor only after the event projection succeeds. A page
        // reload can then safely replay the same durable event.
        await onEvent?.(event, snapshot);
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
  } = {}) {
    let activeRunId = String(runId || "");
    let cursor = 0;

    const stream = new ReadableStream({
      async start(controller) {
        try {
          if (!activeRunId) {
            const created = await createRun({ sessionId, payload, baseUrl, keys, signal });
            activeRunId = String(created.runId || "");
            if (!activeRunId) throw new Error("Runtime did not return a runId");
            onRunCreated?.(activeRunId);
          }

          let failures = 0;
          while (true) {
            if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
            let snapshot;
            try {
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
              ? Math.max(1, Math.ceil((textFrameCount - 1) / SSE_BATCH_MAX_PAUSES))
              : 0;
            let projectedTextFrames = 0;

            for (const frame of projectionFrames) {
              controller.enqueue(encodeSse(frame.data));
              if (frame.completesEvent) cursor = frame.eventSeq;
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
              controller.close();
              return;
            }
            if (snapshot.status === "failed" || snapshot.status === "cancelled") {
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

  global.AgentRuntime = Object.freeze({
    openSseResponse,
    cancelRun,
    createAgentRun,
    getAgentRun,
    resumeAgentRun,
    submitAgentInput,
    submitAgentAuthorization,
    watchAgentRun,
    cancelAgentRun,
  });
})(window);
