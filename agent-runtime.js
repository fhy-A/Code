(function attachAgentRuntime(global) {
  "use strict";

  const POLL_DELAYS = [500, 1000, 2000, 4000, 8000];

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
            for (const event of events) {
              const seq = Number(event?.seq || 0);
              if (seq <= cursor) continue;
              cursor = seq;
              controller.enqueue(encodeSse(String(event?.data ?? "")));
            }

            if (snapshot.status === "completed") {
              controller.close();
              return;
            }
            if (snapshot.status === "failed" || snapshot.status === "cancelled") {
              const detail = JSON.stringify({
                message: snapshot.error || `Runtime ${snapshot.status}`,
                code: `runtime_${snapshot.status}`,
                status: snapshot.upstreamStatus || 0,
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
