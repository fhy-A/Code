(function attachRunProjectionShadow(global) {
  "use strict";

  const Code = global.Code;
  const agent = Code && Code.agent;
  const reducer = agent && agent.runReducer;
  const view = Code && Code.ui && Code.ui.runViewModel;
  if (!agent || !reducer || !view) {
    throw new Error("Code run projection modules must load before projection shadow");
  }

  const RUN_PROJECTION_SHADOW_SCHEMA_VERSION = 1;
  const DEFAULT_MAX_DIAGNOSTICS = 64;
  const DEFAULT_MAX_SUMMARIES = 32;
  const SAFE_DIAGNOSTIC_CODES = new Set([
    "projection_shadow_error",
    "projection_mismatch",
    "event_observer_error",
    "snapshot_observer_error",
    "comparison_observer_error",
    "reducer_event_sequence_gap",
    "reducer_unknown_event_type",
    "reducer_illegal_terminal_transition",
  ]);
  const SAFE_DIAGNOSTIC_FIELDS = new Set([
    "",
    ...view.RUN_PROJECTION_COMPARISON_FIELDS,
  ]);
  const SAFE_RUN_KINDS = new Set(["foreground", "background"]);
  const LEGACY_EVENT_CATEGORIES = Object.freeze({
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
  const LEGACY_EVENT_STATUSES = Object.freeze({
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
  const LEGACY_TOOL_EVENT_TYPES = new Set([
    "tool_started",
    "command_started",
    "tool_completed",
    "tool_retry_blocked",
    "child_agent_created",
  ]);

  function positiveLimit(value, fallback) {
    const number = Number(value);
    const normalized = Number.isInteger(number) && number > 0 ? number : fallback;
    return Math.min(normalized, fallback);
  }

  function nonNegativeInteger(value) {
    const number = Number(value);
    return Number.isFinite(number) && number >= 0 ? Math.floor(number) : 0;
  }

  function diagnosticCode(value) {
    const code = String(value || "");
    return SAFE_DIAGNOSTIC_CODES.has(code) ? code : "projection_shadow_error";
  }

  function diagnosticField(value) {
    const field = String(value || "");
    return SAFE_DIAGNOSTIC_FIELDS.has(field) ? field : "";
  }

  function projectionStatus(value) {
    const status = String(value || "");
    return reducer.RUN_STATUSES.includes(status) ? status : "";
  }

  function sanitizeDiagnosticCounts(value) {
    const counts = {};
    if (!value || typeof value !== "object" || Array.isArray(value)) return counts;
    for (const [rawCode, rawCount] of Object.entries(value)) {
      const code = diagnosticCode(rawCode);
      counts[code] = nonNegativeInteger(counts[code]) + nonNegativeInteger(rawCount);
    }
    return counts;
  }

  function sanitizeArchivedSummary(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const runKind = String(value.runKind || "");
    return {
      schemaVersion: RUN_PROJECTION_SHADOW_SCHEMA_VERSION,
      cursor: nonNegativeInteger(value.cursor),
      status: projectionStatus(value.status),
      eventsObserved: nonNegativeInteger(value.eventsObserved),
      snapshotsObserved: nonNegativeInteger(value.snapshotsObserved),
      comparisons: nonNegativeInteger(value.comparisons),
      mismatches: nonNegativeInteger(value.mismatches),
      observerErrors: nonNegativeInteger(value.observerErrors),
      diagnosticCounts: sanitizeDiagnosticCounts(value.diagnosticCounts),
      diagnostics: (Array.isArray(value.diagnostics) ? value.diagnostics : [])
        .slice(0, DEFAULT_MAX_DIAGNOSTICS)
        .map((item) => ({
          code: diagnosticCode(item?.code),
          field: diagnosticField(item?.field),
          cursor: nonNegativeInteger(item?.cursor),
          status: projectionStatus(item?.status),
        })),
      diagnosticsDropped: nonNegativeInteger(value.diagnosticsDropped),
      runKind: SAFE_RUN_KINDS.has(runKind) ? runKind : "foreground",
    };
  }

  function createProjectionShadowReport(
    summaries,
    { enabled = false, maxSummaries = DEFAULT_MAX_SUMMARIES } = {},
  ) {
    const active = enabled === true;
    const limit = positiveLimit(maxSummaries, DEFAULT_MAX_SUMMARIES);
    const safeSummaries = active
      ? (Array.isArray(summaries) ? summaries : [])
        .slice(-limit)
        .map(sanitizeArchivedSummary)
        .filter(Boolean)
      : [];
    const totals = {
      eventsObserved: 0,
      snapshotsObserved: 0,
      comparisons: 0,
      mismatches: 0,
      observerErrors: 0,
      diagnosticsDropped: 0,
    };
    const runKindCounts = { foreground: 0, background: 0 };
    const diagnosticCounts = {};
    for (const summary of safeSummaries) {
      runKindCounts[summary.runKind] += 1;
      for (const field of Object.keys(totals)) totals[field] += summary[field];
      for (const [code, count] of Object.entries(summary.diagnosticCounts)) {
        diagnosticCounts[code] = nonNegativeInteger(diagnosticCounts[code]) + count;
      }
    }
    return {
      schemaVersion: RUN_PROJECTION_SHADOW_SCHEMA_VERSION,
      enabled: active,
      summaryLimit: limit,
      summaryCount: safeSummaries.length,
      runKindCounts,
      totals,
      diagnosticCounts,
      summaries: safeSummaries,
    };
  }

  function incrementCount(target, key) {
    target[key] = Number(target[key] || 0) + 1;
  }

  function legacyEventReference(type, data) {
    if (type.startsWith("model_")) return String(data.runtimeRunId || data.round || "");
    if (LEGACY_TOOL_EVENT_TYPES.has(type)) return String(data.toolCallId || "");
    if (type.startsWith("authorization_")) return String(data.authorizationId || "");
    if (type.startsWith("user_input_")) return String(data.requestId || "");
    if (type.startsWith("context_compaction_")) return String(data.compactionId || "");
    return "";
  }

  function projectLegacyTimelineItem(event) {
    const type = String(event?.type || "").trim();
    const data = event?.data && typeof event.data === "object" && !Array.isArray(event.data)
      ? event.data
      : {};
    return {
      seq: Math.max(0, Number(event?.seq || 0)),
      type,
      category: LEGACY_EVENT_CATEGORIES[type] || "unknown",
      status: LEGACY_EVENT_STATUSES[type] || "observed",
      refId: legacyEventReference(type, data),
      createdAt: String(event?.createdAt || ""),
    };
  }

  function createLegacyProjectionObservation({
    cursor = 0,
    toolCallIds = [],
    modelRoundCount = 0,
  } = {}) {
    return {
      cursor: Math.max(0, Number(cursor || 0)),
      toolCallIds: [...new Set(toolCallIds.map((value) => String(value || "")).filter(Boolean))],
      modelRoundCount: Math.max(0, Number(modelRoundCount || 0)),
      timeline: [],
    };
  }

  function observeLegacyProjectionEvent(observation, event) {
    if (!observation || !event || typeof event !== "object" || Array.isArray(event)) return false;
    const item = projectLegacyTimelineItem(event);
    if (!item.seq || !item.type || item.seq <= Number(observation.cursor || 0)) return false;
    const data = event.data && typeof event.data === "object" && !Array.isArray(event.data)
      ? event.data
      : {};
    observation.cursor = item.seq;
    observation.timeline.push(item);
    if (LEGACY_TOOL_EVENT_TYPES.has(item.type)) {
      const toolCallId = String(data.toolCallId || "");
      if (toolCallId && !observation.toolCallIds.includes(toolCallId)) {
        observation.toolCallIds.push(toolCallId);
      }
    }
    if (["model_started", "model_completed"].includes(item.type)) {
      observation.modelRoundCount = Math.max(
        Number(observation.modelRoundCount || 0),
        Number(data.round || 0),
      );
    }
    return true;
  }

  function snapshotLegacyProjectionObservation(observation) {
    return {
      cursor: Math.max(0, Number(observation?.cursor || 0)),
      toolCount: Array.isArray(observation?.toolCallIds) ? observation.toolCallIds.length : 0,
      modelRoundCount: Math.max(0, Number(observation?.modelRoundCount || 0)),
      timeline: comparableTimeline(observation?.timeline),
    };
  }

  function recordDiagnostic(shadow, code, field = "") {
    const safeCode = String(code || "projection_shadow_error");
    const safeField = String(field || "");
    incrementCount(shadow.diagnosticCounts, safeCode);
    if (safeCode === "projection_mismatch") shadow.mismatches += 1;
    if (shadow.diagnostics.length >= shadow.maxDiagnostics) {
      shadow.diagnosticsDropped += 1;
      return;
    }
    shadow.diagnostics.push({
      code: safeCode,
      field: safeField,
      cursor: Number(shadow.projectionState?.cursor || 0),
      status: String(shadow.projectionState?.status || ""),
    });
  }

  function captureReducerDiagnostics(shadow, previousCount) {
    const diagnostics = shadow.projectionState?.diagnostics || [];
    for (const code of diagnostics.slice(previousCount)) {
      recordDiagnostic(shadow, `reducer_${String(code || "diagnostic")}`);
    }
  }

  function createRunProjectionShadow({ initialSnapshot = {}, maxDiagnostics } = {}) {
    return {
      schemaVersion: RUN_PROJECTION_SHADOW_SCHEMA_VERSION,
      maxDiagnostics: positiveLimit(maxDiagnostics, DEFAULT_MAX_DIAGNOSTICS),
      projectionState: reducer.createRunProjectionState(initialSnapshot),
      eventsObserved: 0,
      snapshotsObserved: 0,
      comparisons: 0,
      mismatches: 0,
      observerErrors: 0,
      diagnosticCounts: {},
      diagnostics: [],
      diagnosticsDropped: 0,
    };
  }

  function observeProjectionEvent(shadow, event) {
    if (!shadow || shadow.schemaVersion !== RUN_PROJECTION_SHADOW_SCHEMA_VERSION) return false;
    shadow.eventsObserved += 1;
    const previousDiagnostics = shadow.projectionState?.diagnostics?.length || 0;
    try {
      shadow.projectionState = reducer.reduceRunProjectionEvent(shadow.projectionState, event);
      captureReducerDiagnostics(shadow, previousDiagnostics);
      return true;
    } catch (_) {
      shadow.observerErrors += 1;
      recordDiagnostic(shadow, "event_observer_error");
      return false;
    }
  }

  function observeProjectionSnapshot(shadow, snapshot) {
    if (!shadow || shadow.schemaVersion !== RUN_PROJECTION_SHADOW_SCHEMA_VERSION) return false;
    shadow.snapshotsObserved += 1;
    try {
      shadow.projectionState = reducer.applyRunProjectionSnapshot(
        shadow.projectionState,
        snapshot || {},
      );
      return true;
    } catch (_) {
      shadow.observerErrors += 1;
      recordDiagnostic(shadow, "snapshot_observer_error");
      return false;
    }
  }

  function comparableTimeline(timeline) {
    return (Array.isArray(timeline) ? timeline : []).map((item) => ({
      seq: Number(item?.seq || 0),
      type: String(item?.type || ""),
      category: String(item?.category || "unknown"),
      status: String(item?.status || "observed"),
      refId: String(item?.refId || ""),
    }));
  }

  function normalizeLegacyComparison(facts = {}) {
    return {
      status: String(facts.status || "model"),
      terminalStatus: String(facts.terminalStatus || ""),
      modelRoundCount: Math.max(0, Number(facts.modelRoundCount || 0)),
      toolCount: Math.max(0, Number(facts.toolCount || 0)),
      pendingKind: String(facts.pendingKind || ""),
      elapsedMs: Math.max(0, Number(facts.elapsedMs || 0)),
      timeline: comparableTimeline(facts.timeline),
    };
  }

  function fieldMatches(left, right) {
    if (left === right) return true;
    return JSON.stringify(left) === JSON.stringify(right);
  }

  function compareProjectionShadow(
    shadow,
    legacyFacts,
    { referenceTime = null, fields = view.RUN_PROJECTION_COMPARISON_FIELDS } = {},
  ) {
    if (!shadow || shadow.schemaVersion !== RUN_PROJECTION_SHADOW_SCHEMA_VERSION) return false;
    shadow.comparisons += 1;
    try {
      const projected = view.createRunProjectionComparison(
        view.projectRunViewModel(shadow.projectionState, { referenceTime }),
      );
      const legacy = normalizeLegacyComparison(legacyFacts);
      let equal = true;
      for (const field of fields) {
        if (!view.RUN_PROJECTION_COMPARISON_FIELDS.includes(field)) continue;
        if (fieldMatches(projected[field], legacy[field])) continue;
        equal = false;
        recordDiagnostic(shadow, "projection_mismatch", field);
      }
      return equal;
    } catch (_) {
      shadow.observerErrors += 1;
      recordDiagnostic(shadow, "comparison_observer_error");
      return false;
    }
  }

  function snapshotRunProjectionShadow(shadow) {
    if (!shadow || shadow.schemaVersion !== RUN_PROJECTION_SHADOW_SCHEMA_VERSION) return null;
    return {
      schemaVersion: RUN_PROJECTION_SHADOW_SCHEMA_VERSION,
      cursor: Number(shadow.projectionState?.cursor || 0),
      status: String(shadow.projectionState?.status || ""),
      eventsObserved: shadow.eventsObserved,
      snapshotsObserved: shadow.snapshotsObserved,
      comparisons: shadow.comparisons,
      mismatches: shadow.mismatches,
      observerErrors: shadow.observerErrors,
      diagnosticCounts: { ...shadow.diagnosticCounts },
      diagnostics: shadow.diagnostics.map((item) => ({ ...item })),
      diagnosticsDropped: shadow.diagnosticsDropped,
    };
  }

  agent.runProjectionShadow = Object.freeze({
    RUN_PROJECTION_SHADOW_SCHEMA_VERSION,
    DEFAULT_MAX_DIAGNOSTICS,
    DEFAULT_MAX_SUMMARIES,
    createLegacyProjectionObservation,
    observeLegacyProjectionEvent,
    snapshotLegacyProjectionObservation,
    createRunProjectionShadow,
    observeProjectionEvent,
    observeProjectionSnapshot,
    compareProjectionShadow,
    snapshotRunProjectionShadow,
    createProjectionShadowReport,
  });
})(window);
