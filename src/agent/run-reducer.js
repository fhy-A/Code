(function attachRunReducer(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before run reducer");

  const RUN_PROJECTION_SCHEMA_VERSION = 1;
  const RUN_STATUSES = Object.freeze([
    "model",
    "tools",
    "waiting_credentials",
    "waiting_user_input",
    "waiting_authorization",
    "completed",
    "failed",
    "cancelled",
  ]);
  const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);
  const KNOWN_EVENT_TYPES = Object.freeze([
    "created",
    "resumed",
    "waiting_credentials",
    "model_pending",
    "model_started",
    "model_completed",
    "model_recovery",
    "tool_started",
    "command_started",
    "tool_completed",
    "tool_retry_blocked",
    "authorization_required",
    "authorization_submitted",
    "user_input_required",
    "user_input_submitted",
    "child_agent_created",
    "context_compaction_started",
    "context_compaction_completed",
    "context_compaction_failed",
    "completed",
    "failed",
    "cancelled",
  ]);
  const KNOWN_EVENT_TYPE_SET = new Set(KNOWN_EVENT_TYPES);

  const EVENT_CATEGORIES = Object.freeze({
    created: "run",
    resumed: "run",
    waiting_credentials: "run",
    model_pending: "model",
    model_started: "model",
    model_completed: "model",
    model_recovery: "model",
    tool_started: "tool",
    command_started: "tool",
    tool_completed: "tool",
    tool_retry_blocked: "tool",
    authorization_required: "authorization",
    authorization_submitted: "authorization",
    user_input_required: "user-input",
    user_input_submitted: "user-input",
    child_agent_created: "tool",
    context_compaction_started: "compaction",
    context_compaction_completed: "compaction",
    context_compaction_failed: "compaction",
    completed: "terminal",
    failed: "terminal",
    cancelled: "terminal",
  });

  const EVENT_STATES = Object.freeze({
    created: "created",
    resumed: "resumed",
    waiting_credentials: "waiting",
    model_pending: "pending",
    model_started: "running",
    model_completed: "completed",
    model_recovery: "recovery",
    tool_started: "running",
    command_started: "running",
    tool_completed: "completed",
    tool_retry_blocked: "blocked",
    authorization_required: "waiting",
    authorization_submitted: "submitted",
    user_input_required: "waiting",
    user_input_submitted: "submitted",
    child_agent_created: "created",
    context_compaction_started: "running",
    context_compaction_completed: "completed",
    context_compaction_failed: "failed",
    completed: "completed",
    failed: "failed",
    cancelled: "cancelled",
  });

  function stringValue(value) {
    return String(value == null ? "" : value);
  }

  function positiveInteger(value, fallback = 0) {
    const number = Number(value);
    return Number.isInteger(number) && number > 0 ? number : fallback;
  }

  function nonNegativeNumber(value, fallback = null) {
    if (value === "" || value == null) return fallback;
    const number = Number(value);
    return Number.isFinite(number) && number >= 0 ? number : fallback;
  }

  function normalizeStatus(value, fallback = "model") {
    const status = stringValue(value);
    return RUN_STATUSES.includes(status) ? status : fallback;
  }

  function phaseForStatus(status) {
    if (TERMINAL_STATUSES.has(status)) return "terminal";
    if (status.startsWith("waiting_")) return status;
    return status === "tools" ? "tools" : "model";
  }

  function normalizeTool(source, fallbackId = "") {
    const toolCallId = stringValue(
      source?.toolCallId || source?.id || fallbackId,
    );
    return {
      toolCallId,
      name: stringValue(source?.name || source?.action),
      status: stringValue(source?.status || "running"),
      outcome: stringValue(source?.outcome),
      startedAt: stringValue(source?.startedAt),
      completedAt: stringValue(source?.completedAt),
    };
  }

  function normalizePending(snapshot, status) {
    if (status === "waiting_authorization" && snapshot?.pendingAuthorization) {
      const source = snapshot.pendingAuthorization;
      return {
        kind: "authorization",
        id: stringValue(source.authorizationId),
        toolCallId: stringValue(source.toolCallId),
        action: stringValue(source.action),
      };
    }
    if (status === "waiting_user_input" && snapshot?.pendingInput) {
      const source = snapshot.pendingInput;
      return {
        kind: "user-input",
        id: stringValue(source.requestId),
        toolCallId: stringValue(source.toolCallId),
        action: stringValue(source.type),
      };
    }
    if (status === "waiting_credentials") {
      return {
        kind: "credentials",
        id: "",
        toolCallId: "",
        action: stringValue(snapshot?.resumeStatus),
      };
    }
    return null;
  }

  function createRunProjectionState(snapshot = {}) {
    const status = normalizeStatus(snapshot.status, "model");
    const tools = {};
    const toolOrder = [];
    const sourceTools = Array.isArray(snapshot.toolExecutions)
      ? snapshot.toolExecutions
      : Object.values(snapshot.toolExecutions || {});
    for (let index = 0; index < sourceTools.length; index += 1) {
      const tool = normalizeTool(sourceTools[index], `snapshot-tool-${index + 1}`);
      if (!tool.toolCallId || tools[tool.toolCallId]) continue;
      tools[tool.toolCallId] = tool;
      toolOrder.push(tool.toolCallId);
    }
    const startedAt = stringValue(snapshot.createdAt || snapshot.startedAt);
    const updatedAt = stringValue(snapshot.updatedAt || startedAt);
    return {
      schemaVersion: RUN_PROJECTION_SCHEMA_VERSION,
      status,
      phase: phaseForStatus(status),
      cursor: Math.max(0, Number(snapshot.eventCursor ?? snapshot.nextCursor ?? 0) || 0),
      modelRoundCount: Math.max(0, Number(snapshot.round ?? snapshot.modelRoundCount ?? 0) || 0),
      models: {},
      modelOrder: [],
      tools,
      toolOrder,
      pending: normalizePending(snapshot, status),
      compactions: {},
      compactionOrder: [],
      timing: {
        startedAt,
        updatedAt,
        completedAt: TERMINAL_STATUSES.has(status) ? updatedAt : "",
        elapsedMs: nonNegativeNumber(snapshot.elapsedMs),
        elapsedObservedAt: stringValue(snapshot.elapsedObservedAt || updatedAt),
      },
      timeline: [],
      diagnostics: [],
    };
  }

  function cloneState(state) {
    return {
      ...state,
      models: Object.fromEntries(Object.entries(state.models || {}).map(
        ([key, value]) => [key, { ...value }],
      )),
      modelOrder: [...(state.modelOrder || [])],
      tools: Object.fromEntries(Object.entries(state.tools || {}).map(
        ([key, value]) => [key, { ...value }],
      )),
      toolOrder: [...(state.toolOrder || [])],
      pending: state.pending ? { ...state.pending } : null,
      compactions: Object.fromEntries(Object.entries(state.compactions || {}).map(
        ([key, value]) => [key, { ...value }],
      )),
      compactionOrder: [...(state.compactionOrder || [])],
      timing: { ...(state.timing || {}) },
      timeline: (state.timeline || []).map((item) => ({ ...item })),
      diagnostics: [...(state.diagnostics || [])],
    };
  }

  function eventReference(eventType, data) {
    if (eventType.startsWith("model_")) {
      return stringValue(data.runtimeRunId || data.round);
    }
    if (eventType.startsWith("tool_") || eventType === "command_started" || eventType === "child_agent_created") {
      return stringValue(data.toolCallId);
    }
    if (eventType.startsWith("authorization_")) return stringValue(data.authorizationId);
    if (eventType.startsWith("user_input_")) return stringValue(data.requestId);
    if (eventType.startsWith("context_compaction_")) return stringValue(data.compactionId);
    return "";
  }

  function eventRoundKey(data, state) {
    const round = positiveInteger(data.round, state.modelRoundCount + 1);
    const runtimeRunId = stringValue(data.runtimeRunId);
    return {
      round,
      key: runtimeRunId ? `runtime:${runtimeRunId}` : `round:${round}`,
      runtimeRunId,
    };
  }

  function upsertModel(next, data, status, createdAt) {
    const identity = eventRoundKey(data, next);
    let key = identity.key;
    if (!next.models[key] && identity.runtimeRunId) {
      const byRound = `round:${identity.round}`;
      if (next.models[byRound]) key = byRound;
    }
    const resolvedRound = positiveInteger(
      data.round,
      positiveInteger(next.models[key]?.round, identity.round),
    );
    if (!next.models[key]) next.modelOrder.push(key);
    next.models[key] = {
      ...(next.models[key] || {}),
      round: resolvedRound,
      runtimeRunId: identity.runtimeRunId || next.models[key]?.runtimeRunId || "",
      status,
      outcome: stringValue(data.outcome || next.models[key]?.outcome),
      startedAt: status === "running"
        ? (next.models[key]?.startedAt || createdAt)
        : stringValue(next.models[key]?.startedAt),
      completedAt: status === "completed" ? createdAt : stringValue(next.models[key]?.completedAt),
    };
    next.modelRoundCount = Math.max(next.modelRoundCount, resolvedRound);
  }

  function upsertTool(next, data, status, createdAt) {
    const toolCallId = stringValue(data.toolCallId);
    if (!toolCallId) return;
    if (!next.tools[toolCallId]) next.toolOrder.push(toolCallId);
    next.tools[toolCallId] = {
      ...(next.tools[toolCallId] || {}),
      toolCallId,
      name: stringValue(data.name || next.tools[toolCallId]?.name),
      status,
      outcome: stringValue(data.outcome || next.tools[toolCallId]?.outcome),
      startedAt: status === "running"
        ? (next.tools[toolCallId]?.startedAt || createdAt)
        : stringValue(next.tools[toolCallId]?.startedAt),
      completedAt: status === "completed" ? createdAt : stringValue(next.tools[toolCallId]?.completedAt),
    };
  }

  function upsertCompaction(next, data, status, createdAt) {
    const compactionId = stringValue(data.compactionId);
    if (!compactionId) return;
    if (!next.compactions[compactionId]) next.compactionOrder.push(compactionId);
    next.compactions[compactionId] = {
      ...(next.compactions[compactionId] || {}),
      compactionId,
      status,
      reason: stringValue(data.reason || next.compactions[compactionId]?.reason),
      startedAt: status === "running"
        ? (next.compactions[compactionId]?.startedAt || createdAt)
        : stringValue(next.compactions[compactionId]?.startedAt),
      completedAt: status !== "running" ? createdAt : "",
    };
  }

  function clearPending(next, kind, id) {
    if (!next.pending || next.pending.kind !== kind) return;
    if (id && next.pending.id && id !== next.pending.id) return;
    next.pending = null;
  }

  function reduceRunProjectionEvent(state, event) {
    if (!state || state.schemaVersion !== RUN_PROJECTION_SCHEMA_VERSION) {
      throw new TypeError("Run projection state must use schema version 1");
    }
    if (!event || typeof event !== "object" || Array.isArray(event)) {
      throw new TypeError("Run projection event must be a normalized event object");
    }
    const seq = positiveInteger(event.seq);
    const eventType = stringValue(event.type).trim();
    if (!seq || !eventType) {
      throw new TypeError("Run projection event requires a positive seq and type");
    }
    if (seq <= state.cursor) return state;

    const next = cloneState(state);
    if (seq > state.cursor + 1) next.diagnostics.push("event_sequence_gap");
    if (!KNOWN_EVENT_TYPE_SET.has(eventType)) next.diagnostics.push("unknown_event_type");

    const data = event.data && typeof event.data === "object" && !Array.isArray(event.data)
      ? event.data
      : {};
    const createdAt = stringValue(event.createdAt);
    const wasTerminal = TERMINAL_STATUSES.has(state.status);
    next.cursor = seq;
    if (!next.timing.startedAt && createdAt) next.timing.startedAt = createdAt;
    if (createdAt) next.timing.updatedAt = createdAt;
    next.timeline.push({
      seq,
      type: eventType,
      category: EVENT_CATEGORIES[eventType] || "unknown",
      status: EVENT_STATES[eventType] || "observed",
      refId: eventReference(eventType, data),
      createdAt,
    });

    if (wasTerminal && eventType !== state.status) {
      next.diagnostics.push("illegal_terminal_transition");
      next.phase = "terminal";
      return next;
    }

    if (eventType === "resumed") {
      next.status = normalizeStatus(data.status, next.status);
      next.pending = null;
    } else if (eventType === "waiting_credentials") {
      next.status = "waiting_credentials";
      next.pending = {
        kind: "credentials",
        id: "",
        toolCallId: "",
        action: stringValue(data.resumeStatus),
      };
    } else if (["model_pending", "model_started", "model_recovery"].includes(eventType)) {
      next.status = "model";
      if (eventType !== "model_pending") {
        upsertModel(next, data, eventType === "model_started" ? "running" : "recovery", createdAt);
      }
    } else if (eventType === "model_completed") {
      upsertModel(next, data, "completed", createdAt);
      next.status = Array.isArray(data.toolCalls) && data.toolCalls.length ? "tools" : "model";
    } else if (["tool_started", "command_started", "child_agent_created"].includes(eventType)) {
      next.status = "tools";
      upsertTool(next, data, "running", createdAt);
    } else if (eventType === "tool_completed") {
      next.status = "tools";
      upsertTool(next, data, "completed", createdAt);
    } else if (eventType === "tool_retry_blocked") {
      next.status = "tools";
      upsertTool(next, data, "blocked", createdAt);
    } else if (eventType === "authorization_required") {
      next.status = "waiting_authorization";
      next.pending = {
        kind: "authorization",
        id: stringValue(data.authorizationId),
        toolCallId: stringValue(data.toolCallId),
        action: stringValue(data.action),
      };
    } else if (eventType === "authorization_submitted") {
      next.status = "tools";
      clearPending(next, "authorization", stringValue(data.authorizationId));
    } else if (eventType === "user_input_required") {
      next.status = "waiting_user_input";
      next.pending = {
        kind: "user-input",
        id: stringValue(data.requestId),
        toolCallId: stringValue(data.toolCallId),
        action: stringValue(data.type),
      };
    } else if (eventType === "user_input_submitted") {
      next.status = "tools";
      clearPending(next, "user-input", stringValue(data.requestId));
    } else if (eventType.startsWith("context_compaction_")) {
      const status = eventType.endsWith("_started")
        ? "running"
        : (eventType.endsWith("_failed") ? "failed" : "completed");
      upsertCompaction(next, data, status, createdAt);
    } else if (TERMINAL_STATUSES.has(eventType)) {
      next.status = eventType;
      next.pending = null;
      next.timing.completedAt = createdAt || next.timing.updatedAt;
    }
    next.phase = phaseForStatus(next.status);
    return next;
  }

  function applyRunProjectionSnapshot(state, snapshot = {}) {
    if (!state || state.schemaVersion !== RUN_PROJECTION_SCHEMA_VERSION) {
      throw new TypeError("Run projection state must use schema version 1");
    }
    const next = cloneState(state);
    next.status = normalizeStatus(snapshot.status, next.status);
    next.phase = phaseForStatus(next.status);
    next.modelRoundCount = Math.max(
      next.modelRoundCount,
      Math.max(0, Number(snapshot.round ?? snapshot.modelRoundCount ?? 0) || 0),
    );
    const snapshotState = createRunProjectionState(snapshot);
    for (const toolCallId of snapshotState.toolOrder) {
      if (!next.tools[toolCallId]) next.toolOrder.push(toolCallId);
      next.tools[toolCallId] = {
        ...(next.tools[toolCallId] || {}),
        ...snapshotState.tools[toolCallId],
      };
    }
    next.pending = snapshotState.pending;
    const elapsedMs = nonNegativeNumber(snapshot.elapsedMs);
    if (elapsedMs != null) {
      next.timing.elapsedMs = elapsedMs;
      next.timing.elapsedObservedAt = stringValue(snapshot.elapsedObservedAt || snapshot.updatedAt);
    }
    if (snapshot.createdAt || snapshot.startedAt) {
      next.timing.startedAt = stringValue(snapshot.createdAt || snapshot.startedAt);
    }
    if (snapshot.updatedAt) next.timing.updatedAt = stringValue(snapshot.updatedAt);
    if (TERMINAL_STATUSES.has(next.status)) {
      next.timing.completedAt = stringValue(snapshot.completedAt || snapshot.updatedAt || next.timing.completedAt);
    }
    return next;
  }

  function reduceRunProjectionInput(state, input) {
    if (input?.kind === "event") return reduceRunProjectionEvent(state, input.event);
    if (input?.kind === "snapshot") return applyRunProjectionSnapshot(state, input.snapshot);
    throw new TypeError("Run projection input kind must be event or snapshot");
  }

  function reduceRunProjectionInputs(initialState, inputs = []) {
    return inputs.reduce(reduceRunProjectionInput, initialState);
  }

  agent.runReducer = Object.freeze({
    RUN_PROJECTION_SCHEMA_VERSION,
    RUN_STATUSES,
    KNOWN_EVENT_TYPES,
    EVENT_CATEGORIES,
    createRunProjectionState,
    reduceRunProjectionEvent,
    applyRunProjectionSnapshot,
    reduceRunProjectionInput,
    reduceRunProjectionInputs,
  });
})(window);
