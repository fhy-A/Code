from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.js").read_text(encoding="utf-8")
GOAL_SOURCE = (ROOT / "src/features/goal.js").read_text(encoding="utf-8")
MESSAGES_SOURCE = (ROOT / "src/ui/messages.js").read_text(encoding="utf-8")
STYLE_SOURCE = (ROOT / "styles.css").read_text(encoding="utf-8")
INDEX_SOURCE = (ROOT / "index.html").read_text(encoding="utf-8")
I18N_SOURCE = (ROOT / "src/core/i18n.js").read_text(encoding="utf-8")
SERVER_SOURCE = (ROOT / "server.py").read_text(encoding="utf-8")


def test_explicit_goal_runs_after_origin_persistence_and_before_foreground_run():
    start = APP_SOURCE.index("async function sendMessage(")
    end = APP_SOURCE.index("function getSelectedModel()", start)
    source = APP_SOURCE[start:end]
    save_boundary = source.index("await saveSessionState(sessionId, ctx.messages, ctx.stats")
    assert save_boundary < source.index(
        "await goalFeature.prepareExplicitGoal"
    )
    assert 'persistMessages: explicitGoalAction?.kind === "create"' in source[
        save_boundary:source.index("await goalFeature.prepareExplicitGoal")
    ]
    assert source.index("await goalFeature.prepareExplicitGoal") < source.index(
        "claimActiveRunContext(ctx)"
    )
    assert source.index("claimActiveRunContext(ctx)") < source.index(
        "await executeRunContext(ctx)"
    )
    assert "permissionProfile: ctx.permissionProfile" in source
    assert "goal-workflow" not in APP_SOURCE
    assert "goal-workflow" not in GOAL_SOURCE
    assert "planner_" not in SERVER_SOURCE
    assert "goal_service().read" not in SERVER_SOURCE
    assert 'route.endswith("/goal")' not in SERVER_SOURCE


def test_goal_message_marker_is_fail_closed_and_not_keyword_derived():
    marker_start = MESSAGES_SOURCE.index("const goalOrigin = msg.meta?.goalOrigin")
    marker_end = MESSAGES_SOURCE.index("const traceClass", marker_start)
    marker_source = MESSAGES_SOURCE[marker_start:marker_end]
    assert "goalOrigin?.confirmed === true" in marker_source
    assert 'String(goalOrigin.messageId || "") === String(msg.id || "")' in marker_source
    assert 'String(goalOrigin.sourceKind || "") === "explicit"' in marker_source
    assert "autonomous" not in marker_source
    assert "goalOrigin.goalId" in marker_source
    assert "/goal" not in marker_source
    assert "goal-message-marker" in STYLE_SOURCE
    assert ".msg.user:has(.goal-message-marker) .msg-meta" in STYLE_SOURCE


def test_goal_completion_marker_is_explicit_only_and_formats_trusted_duration():
    script = r'''
global.window = global;
global.Code = {ui: {}};
require("./src/ui/messages.js");
const feature = Code.ui.messages.createMessagesFeature({
  escapeHtml: (value) => String(value ?? ""),
  renderMarkdown: (value) => String(value),
  renderAssistantContent: (value) => String(value),
  getMessageText: (message) => String(message?.content || ""),
  getSelectedModel: () => "model",
  t: (key, params = {}) => key === "goalCompletionMarker"
    ? `ACHIEVED ${params.duration}`
    : key,
});
const render = (marker, overrides = {}) => {
  const {meta: overrideMeta = {}, ...messageOverrides} = overrides;
  return feature.renderFinalAssistantProjection({
    role: "assistant",
    content: "Final public answer",
    _time: "2026-08-15T01:02:05Z",
    ...messageOverrides,
    meta: {
      agentRunId: "run-complete",
      _agentRunTerminal: true,
      _usage: {input: 3, output: 1, cache: 0},
      goalCompletion: marker,
      ...overrideMeta,
    },
  }, 0);
};
const marker = {
  goalId: "goal-explicit",
  sourceKind: "explicit",
  sourceRunId: "run-complete",
  createdAt: "2026-08-15T01:00:00Z",
  completedAt: "2026-08-15T01:02:05Z",
  confirmed: true,
};
process.stdout.write(JSON.stringify({
  explicit: render(marker),
  noUsage: render(marker, {meta: {_usage: null}}),
  seconds: render({...marker, completedAt: "2026-08-15T01:00:59.999Z"}),
  hours: render({...marker, completedAt: "2026-08-15T02:02:03Z"}),
  usageOnly: render(null),
  controlsOnly: render(null, {meta: {_usage: null}}),
  autonomous: render({...marker, sourceKind: "autonomous"}),
  mismatchedRun: render({...marker, sourceRunId: "run-other"}),
  missingTerminal: render(marker, {meta: {_agentRunTerminal: false}}),
  invalidTime: render({...marker, completedAt: "invalid"}),
}));
'''
    completed = subprocess.run(
        ["node", "-"], cwd=ROOT, input=script, text=True,
        encoding="utf-8", capture_output=True, check=True,
    )
    data = json.loads(completed.stdout)
    assert "ACHIEVED 2m 5s" in data["explicit"]
    assert data["explicit"].index('class="response-info"') < data["explicit"].index(
        'class="goal-completion-marker"'
    )
    assert data["explicit"].count('class="msg-footer"') == 1
    assert data["explicit"].count('class="msg-footer-status"') == 1
    assert data["explicit"].index('class="goal-completion-marker"') < data["explicit"].index(
        'class="msg-copy-btn"'
    )
    assert data["explicit"].index('class="msg-copy-btn"') < data["explicit"].index(
        'class="msg-time"'
    )
    assert "ACHIEVED 2m 5s" in data["noUsage"]
    assert 'class="response-info"' not in data["noUsage"]
    assert data["noUsage"].count('class="msg-footer"') == 1
    assert data["noUsage"].index('class="goal-completion-marker"') < data["noUsage"].index(
        'class="msg-copy-btn"'
    )
    assert "ACHIEVED 59s" in data["seconds"]
    assert "ACHIEVED 1h 2m 3s" in data["hours"]
    assert data["usageOnly"].index('class="response-info"') < data["usageOnly"].index(
        'class="msg-copy-btn"'
    )
    assert 'class="goal-completion-marker"' not in data["usageOnly"]
    assert 'class="response-info"' not in data["controlsOnly"]
    assert 'class="goal-completion-marker"' not in data["controlsOnly"]
    assert data["controlsOnly"].index('class="msg-copy-btn"') < data["controlsOnly"].index(
        'class="msg-time"'
    )
    assert "goal-explicit" not in data["explicit"]
    assert "goal-completion-marker" not in data["autonomous"]
    assert "goal-completion-marker" not in data["mismatchedRun"]
    assert "goal-completion-marker" not in data["missingTerminal"]
    assert "goal-completion-marker" not in data["invalidTime"]
    assert 'goalCompletionMarker: "已在 {duration} 内达成目标"' in I18N_SOURCE
    assert 'goalCompletionMarker: "Goal achieved in {duration}"' in I18N_SOURCE
    assert ".goal-completion-marker" in STYLE_SOURCE
    assert ".msg-footer-status" in STYLE_SOURCE
    assert "justify-content: flex-start" in STYLE_SOURCE
    assert ".msg-footer-status { display: inline-flex; flex: 0 1 auto" in STYLE_SOURCE
    assert "flex-wrap: wrap; gap: 0" in STYLE_SOURCE
    assert ".msg-footer-status > .goal-completion-marker:not(:first-child)" in STYLE_SOURCE
    assert ".msg-footer-hover { display: inline-flex; align-items: center; gap: 0; max-width: 0; margin-left: 0" in STYLE_SOURCE
    assert ".msg.assistant:focus-within .msg-footer-hover" in STYLE_SOURCE
    assert "@media (hover: none), (pointer: coarse)" in STYLE_SOURCE
    assert ".msg-copy-btn:focus-visible" in STYLE_SOURCE


def test_compact_composer_projection_replaces_the_large_planner_board():
    assert 'id="goalProgress"' in INDEX_SOURCE
    assert 'id="goalProgressSummary"' in INDEX_SOURCE
    assert 'aria-controls="goalProgressDetails"' in INDEX_SOURCE
    assert ".goal-progress.hidden" in STYLE_SOURCE
    assert ".goal-progress-details" in STYLE_SOURCE
    assert "bottom: calc(100% + 8px)" in STYLE_SOURCE
    assert ".goal-progress-summary:focus-visible" in STYLE_SOURCE
    assert "goal-status-board" not in STYLE_SOURCE
    assert "goal-board-" not in STYLE_SOURCE
    assert "goalStatusBoard" not in GOAL_SOURCE
    assert "window.confirm" not in GOAL_SOURCE
    assert "window.alert" not in GOAL_SOURCE
    assert "goalProgressAriaLabel" in I18N_SOURCE
    assert 'goalStep_pending: "未开始"' in I18N_SOURCE
    assert 'goalStep_in_progress: "进行中"' in I18N_SOURCE
    assert 'goalStep_completed: "已完成"' in I18N_SOURCE
    assert 'const TERMINAL_LIFECYCLES = new Set(["completed", "cancelled"]);' in GOAL_SOURCE
    assert '!TERMINAL_LIFECYCLES.has(String(goal.lifecycle || ""))' in GOAL_SOURCE
    assert '"goal_complete"' in APP_SOURCE
    assert '"goal_complete"' in MESSAGES_SOURCE
    assert "完成最后一个步骤会在同一次 goal_complete_step 回执中直接完成 Goal" in APP_SOURCE
    assert "调用最后一个 goal_complete_step 时，不要同时输出面向用户的完整最终总结" in APP_SOURCE
    assert "成功回执后的既有无工具终态轮才是唯一完整答复" in APP_SOURCE
    assert "先保留该步骤为 in_progress 并记录 waiting_user gate" in APP_SOURCE


def test_goal_feature_projects_v2_and_posts_explicit_create_with_latest_identity():
    script = r'''
global.window = {Code: {features: {}}, crypto: {randomUUID: () => "uuid"}};
require("./src/features/goal.js");
const {classifyGoalInput, createGoalFeature} = window.Code.features.goal;

function classList() {
  const values = new Set(["hidden"]);
  return {
    values,
    add(value) { values.add(value); },
    remove(value) { values.delete(value); },
    toggle(value, force) {
      if (force === undefined ? !values.has(value) : force) values.add(value);
      else values.delete(value);
    },
  };
}
function element() {
  const listeners = {};
  return {
    classList: classList(), dataset: {}, hidden: true, textContent: "", innerHTML: "",
    attrs: {}, listeners,
    setAttribute(name, value) { this.attrs[name] = String(value); },
    addEventListener(type, listener) { (listeners[type] ||= []).push(listener); },
    emit(type, event = {}) { for (const listener of listeners[type] || []) listener({preventDefault() {}, ...event}); },
    contains(target) { return target === this; }, matches() { return false; }, focus() {},
  };
}
const elements = {
  goalProgress: element(), goalProgressSummary: element(), goalProgressObjective: element(),
  goalProgressPhase: element(), goalProgressCount: element(), goalProgressDetails: element(),
};
const messages = [{
  id: "message-explicit", role: "user", content: "/goal Ship durable v2",
  meta: {goalOrigin: {messageId: "message-explicit", clientRequestId: "request-explicit"}},
}];
const empty = {protocolVersion: 2, sessionId: "session-a", revision: 0, health: "healthy", writable: true, exists: false, goal: null};
const goal = {
  goalId: "goal-v2", originMessageId: "message-explicit", clientRequestId: "request-explicit",
  sourceKind: "explicit", lifecycle: "active", objective: "Ship durable v2", currentStepId: "step-2",
  steps: [
    {id: "step-1", status: "completed", description: "Inspect", acceptanceCriteria: [{kind: "machine", description: "Inspection passes"}]},
    {id: "step-2", status: "in_progress", description: "Implement", acceptanceCriteria: [{kind: "agent", description: "Implementation remains bounded"}]},
    {id: "step-3", status: "pending", description: "Review", acceptanceCriteria: [{kind: "user", description: "User accepts"}]},
  ],
};
const active = {...empty, revision: 4, exists: true, goal};
const calls = [];
let projection = empty;
let renders = 0;
const feature = createGoalFeature({
  elements,
  document: {activeElement: null},
  getSessionId: () => "session-a",
  getMessages: () => messages,
  renderMessages: () => { renders += 1; },
  t: (key, params = {}) => {
    if (key === "goalProgressCount") return `${params.current}/${params.total}`;
    if (key === "goalProgressAriaLabel") return `${params.current}/${params.total}`;
    return key;
  },
  escapeHtml: (value) => String(value),
  apiJson: async (url, options = {}) => {
    const body = options.body ? JSON.parse(options.body) : null;
    calls.push({url, body});
    if (body) { projection = active; return {data: active}; }
    return {data: projection};
  },
});
const settle = () => new Promise((resolve) => setTimeout(resolve, 5));
(async () => {
  feature.setSession("session-a");
  await settle();
  const created = await feature.prepareExplicitGoal({
    sessionId: "session-a", objective: "Ship durable v2", messageId: "message-explicit",
    clientRequestId: "request-explicit", permissionProfile: "accept",
  });
  elements.goalProgressSummary.emit("click");
  const opened = !elements.goalProgressDetails.hidden;
  elements.goalProgress.emit("keydown", {key: "Escape"});
  const activeView = {
    hidden: elements.goalProgress.hidden,
    objective: elements.goalProgressObjective.textContent,
    phase: elements.goalProgressPhase.textContent,
    count: elements.goalProgressCount.textContent,
    ariaLabel: elements.goalProgressSummary.attrs["aria-label"],
    details: elements.goalProgressDetails.innerHTML,
  };
  const makeSteps = (statuses) => statuses.map((status, index) => ({
    id: `matrix-step-${index + 1}`,
    status,
    description: `Matrix step ${index + 1}`,
    acceptanceCriteria: [{kind: "machine", description: `Matrix evidence ${index + 1}`}],
  }));
  const progressCases = [];
  for (const item of [
    {name: "not-started", statuses: ["pending", "pending", "pending", "pending"], currentStepId: null},
    {name: "first-running", statuses: ["in_progress", "pending", "pending", "pending"], currentStepId: "matrix-step-1"},
    {name: "second-running", statuses: ["completed", "in_progress", "pending", "pending"], currentStepId: "matrix-step-2"},
    {name: "waiting-third", statuses: ["completed", "completed", "in_progress", "pending"], currentStepId: "matrix-step-3", gate: {type: "waiting_user"}},
    {name: "between-steps", statuses: ["completed", "completed", "pending", "pending"], currentStepId: null},
    {name: "single-running", statuses: ["in_progress"], currentStepId: "matrix-step-1"},
    {name: "long-running", statuses: ["completed", "completed", "completed", "completed", "completed", "completed", "in_progress", "pending"], currentStepId: "matrix-step-7"},
  ]) {
    projection = {
      ...active,
      goal: {...goal, currentStepId: item.currentStepId, gate: item.gate || null, steps: makeSteps(item.statuses)},
    };
    await feature.refresh("session-a", {quiet: true});
    progressCases.push({
      name: item.name,
      count: elements.goalProgressCount.textContent,
      ariaLabel: elements.goalProgressSummary.attrs["aria-label"],
      hidden: elements.goalProgress.hidden,
    });
  }
  projection = {
    ...active,
    revision: 10,
    goal: {
      ...goal,
      lifecycle: "completed",
      currentStepId: null,
      steps: goal.steps.map((step) => ({...step, status: "completed"})),
    },
  };
  await feature.refresh("session-a", {quiet: true});
  process.stdout.write(JSON.stringify({
    classifications: {
      query: classifyGoalInput("/goal"), create: classifyGoalInput("/goal Ship durable v2"),
      mention: classifyGoalInput("please discuss /goal without creating one"),
    },
    createdRevision: created.revision,
    control: calls.find((call) => call.body),
    ...activeView,
    progressCases,
    hiddenAfterCompleted: elements.goalProgress.hidden,
    opened, closedWithEscape: elements.goalProgressDetails.hidden,
    sourceCriteria: goal.steps.map((step) => step.acceptanceCriteria),
    marker: messages[0].meta.goalOrigin,
    renders,
  }));
})().catch((error) => { console.error(error); process.exit(1); });
'''
    completed = subprocess.run(
        ["node", "-"], cwd=ROOT, input=script, text=True,
        encoding="utf-8", capture_output=True, check=True,
    )
    data = json.loads(completed.stdout)
    assert data["classifications"]["query"]["kind"] == "query"
    assert data["classifications"]["create"] == {
        "kind": "create", "objective": "Ship durable v2",
    }
    assert data["classifications"]["mention"] is None
    assert data["createdRevision"] == 4
    assert data["control"]["url"].endswith("/goal-v2/control")
    assert data["control"]["body"] == {
        "operation": "explicit_create",
        "objective": "Ship durable v2",
        "expectedRevision": 0,
        "idempotencyKey": "explicit-request-explicit",
        "messageId": "message-explicit",
        "clientRequestId": "request-explicit",
        "permissionProfile": "accept",
    }
    assert data["hidden"] is False
    assert data["objective"] == "Ship durable v2"
    assert data["phase"] == "goalProgressActive"
    assert data["count"] == "2/3"
    assert data["ariaLabel"] == "2/3"
    assert data["progressCases"] == [
        {"name": "not-started", "count": "0/4", "ariaLabel": "0/4", "hidden": False},
        {"name": "first-running", "count": "1/4", "ariaLabel": "1/4", "hidden": False},
        {"name": "second-running", "count": "2/4", "ariaLabel": "2/4", "hidden": False},
        {"name": "waiting-third", "count": "3/4", "ariaLabel": "3/4", "hidden": False},
        {"name": "between-steps", "count": "2/4", "ariaLabel": "2/4", "hidden": False},
        {"name": "single-running", "count": "1/1", "ariaLabel": "1/1", "hidden": False},
        {"name": "long-running", "count": "7/8", "ariaLabel": "7/8", "hidden": False},
    ]
    assert "is-in_progress is-current" in data["details"]
    assert "Inspect" in data["details"]
    assert "Implement" in data["details"]
    assert "Review" in data["details"]
    assert "goalStep_completed" in data["details"]
    assert "goalStep_in_progress" in data["details"]
    assert "goalStep_pending" in data["details"]
    assert "Inspection passes" not in data["details"]
    assert "Implementation remains bounded" not in data["details"]
    assert "User accepts" not in data["details"]
    assert "goal-progress-criteria" not in data["details"]
    assert "goal-progress-criterion-kind" not in data["details"]
    assert data["sourceCriteria"] == [
        [{"kind": "machine", "description": "Inspection passes"}],
        [{"kind": "agent", "description": "Implementation remains bounded"}],
        [{"kind": "user", "description": "User accepts"}],
    ]
    assert data["opened"] is True
    assert data["closedWithEscape"] is True
    assert data["marker"]["confirmed"] is True
    assert data["marker"]["goalId"] == "goal-v2"
    assert data["renders"] == 2
    assert data["hiddenAfterCompleted"] is True


def test_goal_details_pinned_popover_dismisses_outside_without_blocking_actions():
    script = r'''
global.window = {Code: {features: {}}};
require("./src/features/goal.js");
const {createGoalFeature} = window.Code.features.goal;

const documentListeners = {};
const documentRef = {
  activeElement: null,
  addEventListener(type, listener, capture = false) {
    (documentListeners[type] ||= []).push({listener, capture});
  },
  removeEventListener(type, listener, capture = false) {
    documentListeners[type] = (documentListeners[type] || []).filter((item) => (
      item.listener !== listener || item.capture !== capture
    ));
  },
  emit(type, event = {}) {
    const payload = {
      target: null,
      relatedTarget: null,
      defaultPrevented: false,
      propagationStopped: false,
      preventDefault() { this.defaultPrevented = true; },
      stopPropagation() { this.propagationStopped = true; },
      ...event,
    };
    for (const item of [...(documentListeners[type] || [])]) item.listener(payload);
    return payload;
  },
};

function classList() {
  const values = new Set(["hidden"]);
  return {
    add(value) { values.add(value); },
    remove(value) { values.delete(value); },
    toggle(value, force) {
      if (force === undefined ? !values.has(value) : force) values.add(value);
      else values.delete(value);
    },
  };
}

function element(parentNode = null) {
  const listeners = {};
  return {
    parentNode, classList: classList(), dataset: {}, hidden: true, hovered: false,
    textContent: "", innerHTML: "", attrs: {}, listeners, focusCount: 0,
    setAttribute(name, value) { this.attrs[name] = String(value); },
    addEventListener(type, listener) { (listeners[type] ||= []).push(listener); },
    removeEventListener(type, listener) {
      listeners[type] = (listeners[type] || []).filter((item) => item !== listener);
    },
    emit(type, event = {}) {
      const payload = {
        target: this,
        relatedTarget: null,
        defaultPrevented: false,
        preventDefault() { this.defaultPrevented = true; },
        ...event,
      };
      for (const listener of [...(listeners[type] || [])]) listener(payload);
      return payload;
    },
    contains(target) {
      for (let node = target; node; node = node.parentNode) {
        if (node === this) return true;
      }
      return false;
    },
    matches(selector) { return selector === ":hover" && this.hovered; },
    focus() { documentRef.activeElement = this; this.focusCount += 1; },
  };
}

const root = element();
const summary = element(root);
const details = element(root);
const elements = {
  goalProgress: root,
  goalProgressSummary: summary,
  goalProgressObjective: element(summary),
  goalProgressPhase: element(summary),
  goalProgressCount: element(summary),
  goalProgressDetails: details,
};
const empty = {
  protocolVersion: 2, sessionId: "session-b", revision: 0,
  health: "healthy", writable: true, exists: false, goal: null,
};
const active = {
  ...empty, sessionId: "session-a", revision: 3, exists: true,
  goal: {
    goalId: "goal-v2", lifecycle: "active", objective: "Dismiss Goal details",
    currentStepId: "step-1", steps: [
      {id: "step-1", status: "in_progress", description: "Verify dismissal"},
      {id: "step-2", status: "pending", description: "Keep board state"},
      {id: "step-3", status: "pending", description: "Finish"},
    ],
  },
};
const feature = createGoalFeature({
  elements,
  document: documentRef,
  getSessionId: () => "session-a",
  t: (key, params = {}) => key === "goalProgressCount"
    ? `${params.current}/${params.total}`
    : key,
  escapeHtml: (value) => String(value),
  apiJson: async (url) => ({data: url.includes("session-a") ? active : empty}),
});
const settle = () => new Promise((resolve) => setTimeout(resolve, 5));

(async () => {
  feature.setSession("session-a");
  await settle();

  summary.emit("click");
  const opened = !details.hidden;
  const detailScrollbar = element(details);
  documentRef.emit("pointerdown", {target: details});
  root.emit("focusout", {relatedTarget: null});
  documentRef.emit("click", {target: detailScrollbar});
  const insideStayedOpen = !details.hidden;

  const outside = element();
  const outsidePointer = documentRef.emit("pointerdown", {target: outside});
  const outsideClick = documentRef.emit("click", {target: outside});
  let outsideActionCount = 0;
  if (!outsidePointer.defaultPrevented && !outsidePointer.propagationStopped) outsideActionCount += 1;
  if (!outsideClick.defaultPrevented && !outsideClick.propagationStopped) outsideActionCount += 1;
  const outsideClosed = details.hidden;

  summary.emit("click");
  feature.render(active);
  const rerenderRetained = !details.hidden;
  root.emit("focusout", {relatedTarget: outside});
  const focusLeaveClosed = details.hidden;

  root.emit("pointerenter");
  const hoverOpened = !details.hidden;
  root.emit("pointerleave");
  const hoverLeaveClosed = details.hidden;

  summary.emit("click");
  const escapeEvent = root.emit("keydown", {key: "Escape"});
  const escapeClosed = details.hidden;
  const escapeFocusedSummary = documentRef.activeElement === summary && summary.focusCount === 1;

  summary.emit("click");
  feature.setSession("session-b");
  const sessionSwitchClosed = details.hidden;
  await settle();

  feature.setSession("session-a");
  await settle();
  summary.emit("click");
  feature.render({
    ...active,
    goal: {...active.goal, lifecycle: "completed", currentStepId: null},
  });
  const completedClosed = details.hidden && root.hidden;

  feature.render(active);
  summary.emit("click");
  feature.render(active);
  const listenerCountsBeforeDestroy = {
    pointerdown: (documentListeners.pointerdown || []).length,
    pointerup: (documentListeners.pointerup || []).length,
    pointercancel: (documentListeners.pointercancel || []).length,
    click: (documentListeners.click || []).length,
  };
  feature.destroy();
  const listenerCountsAfterDestroy = {
    pointerdown: (documentListeners.pointerdown || []).length,
    pointerup: (documentListeners.pointerup || []).length,
    pointercancel: (documentListeners.pointercancel || []).length,
    click: (documentListeners.click || []).length,
  };

  process.stdout.write(JSON.stringify({
    opened, insideStayedOpen, outsideClosed, outsideActionCount,
    pointerPrevented: outsidePointer.defaultPrevented,
    clickPrevented: outsideClick.defaultPrevented,
    rerenderRetained, focusLeaveClosed, hoverOpened, hoverLeaveClosed,
    escapeClosed, escapeFocusedSummary, escapePrevented: escapeEvent.defaultPrevented,
    sessionSwitchClosed, completedClosed,
    listenerCountsBeforeDestroy, listenerCountsAfterDestroy,
  }));
})().catch((error) => { console.error(error); process.exit(1); });
'''
    completed = subprocess.run(
        ["node", "-"], cwd=ROOT, input=script, text=True,
        encoding="utf-8", capture_output=True, check=True,
    )
    data = json.loads(completed.stdout)
    assert data == {
        "opened": True,
        "insideStayedOpen": True,
        "outsideClosed": True,
        "outsideActionCount": 2,
        "pointerPrevented": False,
        "clickPrevented": False,
        "rerenderRetained": True,
        "focusLeaveClosed": True,
        "hoverOpened": True,
        "hoverLeaveClosed": True,
        "escapeClosed": True,
        "escapeFocusedSummary": True,
        "escapePrevented": True,
        "sessionSwitchClosed": True,
        "completedClosed": True,
        "listenerCountsBeforeDestroy": {
            "pointerdown": 1, "pointerup": 1, "pointercancel": 1, "click": 1,
        },
        "listenerCountsAfterDestroy": {
            "pointerdown": 0, "pointerup": 0, "pointercancel": 0, "click": 0,
        },
    }


def test_goal_feature_session_switch_is_latest_wins_and_hides_empty_projection():
    assert "sequence !== requestSequence" in GOAL_SOURCE
    assert "normalized !== currentSessionId" in GOAL_SOURCE
    assert 'root.hidden = !visible' in GOAL_SOURCE
    assert 'root.setAttribute("aria-hidden", String(!visible))' in GOAL_SOURCE
    assert "detailsPinned = false" in GOAL_SOURCE
    assert 'event.key !== "Escape"' in GOAL_SOURCE
