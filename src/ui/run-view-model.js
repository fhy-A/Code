(function attachRunViewModel(global) {
  "use strict";

  const Code = global.Code;
  const ui = Code && Code.ui;
  const reducer = Code && Code.agent && Code.agent.runReducer;
  if (!ui || !reducer) {
    throw new Error("Code run reducer must load before run View Model");
  }

  const RUN_VIEW_MODEL_SCHEMA_VERSION = 1;
  const RUN_PROJECTION_COMPARISON_FIELDS = Object.freeze([
    "status",
    "terminalStatus",
    "modelRoundCount",
    "toolCount",
    "pendingKind",
    "elapsedMs",
    "timeline",
  ]);
  const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

  function parseTimestamp(value) {
    if (!value) return null;
    const parsed = Date.parse(String(value));
    return Number.isFinite(parsed) ? parsed : null;
  }

  function normalizedReferenceTime(value) {
    if (value == null || value === "") return null;
    if (typeof value === "number") return Number.isFinite(value) ? value : null;
    return parseTimestamp(value);
  }

  function resolveElapsedMs(state, referenceTime = null) {
    const timing = state.timing || {};
    const explicitElapsed = Number(timing.elapsedMs);
    const hasExplicitElapsed = timing.elapsedMs != null
      && Number.isFinite(explicitElapsed)
      && explicitElapsed >= 0;
    const observedAt = parseTimestamp(timing.elapsedObservedAt);
    const completedAt = parseTimestamp(timing.completedAt);
    const updatedAt = parseTimestamp(timing.updatedAt);
    const suppliedReference = normalizedReferenceTime(referenceTime);
    const terminal = TERMINAL_STATUSES.has(state.status);
    const reference = terminal
      ? (completedAt ?? updatedAt)
      : suppliedReference;

    if (hasExplicitElapsed) {
      const delta = observedAt != null && reference != null
        ? Math.max(0, reference - observedAt)
        : 0;
      return Math.floor(explicitElapsed + delta);
    }

    const startedAt = parseTimestamp(timing.startedAt);
    const fallbackReference = reference ?? updatedAt;
    if (startedAt == null || fallbackReference == null) return 0;
    return Math.floor(Math.max(0, fallbackReference - startedAt));
  }

  function projectRunViewModel(state, { referenceTime = null } = {}) {
    if (!state || state.schemaVersion !== reducer.RUN_PROJECTION_SCHEMA_VERSION) {
      throw new TypeError("Run View Model requires projection schema version 1");
    }
    const terminalStatus = TERMINAL_STATUSES.has(state.status) ? state.status : "";
    const tools = (state.toolOrder || []).map((toolCallId) => ({
      ...(state.tools[toolCallId] || {}),
    }));
    const modelRounds = (state.modelOrder || []).map((key) => ({
      ...(state.models[key] || {}),
    }));
    const compactions = (state.compactionOrder || []).map((compactionId) => ({
      ...(state.compactions[compactionId] || {}),
    }));
    return {
      schemaVersion: RUN_VIEW_MODEL_SCHEMA_VERSION,
      cursor: Number(state.cursor || 0),
      status: state.status,
      phase: state.phase,
      terminalStatus,
      modelRoundCount: Number(state.modelRoundCount || 0),
      modelRounds,
      toolCount: tools.length,
      tools,
      pendingKind: state.pending?.kind || "",
      pending: state.pending ? { ...state.pending } : null,
      elapsedMs: resolveElapsedMs(state, referenceTime),
      timing: { ...(state.timing || {}) },
      timeline: (state.timeline || []).map((item) => ({ ...item })),
      compactions,
      diagnostics: [...(state.diagnostics || [])],
    };
  }

  function createRunProjectionComparison(viewModel) {
    if (!viewModel || viewModel.schemaVersion !== RUN_VIEW_MODEL_SCHEMA_VERSION) {
      throw new TypeError("Projection comparison requires Run View Model version 1");
    }
    return {
      status: viewModel.status,
      terminalStatus: viewModel.terminalStatus,
      modelRoundCount: viewModel.modelRoundCount,
      toolCount: viewModel.toolCount,
      pendingKind: viewModel.pendingKind,
      elapsedMs: viewModel.elapsedMs,
      timeline: viewModel.timeline.map((item) => ({
        seq: item.seq,
        type: item.type,
        category: item.category,
        status: item.status,
        refId: item.refId,
      })),
    };
  }

  ui.runViewModel = Object.freeze({
    RUN_VIEW_MODEL_SCHEMA_VERSION,
    RUN_PROJECTION_COMPARISON_FIELDS,
    resolveElapsedMs,
    projectRunViewModel,
    createRunProjectionComparison,
  });
})(window);
