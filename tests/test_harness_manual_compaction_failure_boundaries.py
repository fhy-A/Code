import hashlib
import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

import server


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "harness"
FIXTURE_PATH = FIXTURE_DIR / "manual-compaction-failure-boundaries-evidence.json"
SCHEMA_PATH = FIXTURE_DIR / "manual-compaction-failure-boundaries-evidence.schema.json"
D2_FIXTURE_PATH = FIXTURE_DIR / "manual-compaction-visible-history-evidence.json"

CASE_IDS = [
    "compact-throws",
    "compact-ok-false",
    "summary-build-throws",
    "archive-fails",
    "first-save-fails-retry-succeeds",
    "both-saves-fail",
    "apply-fails",
    "repeat-confirm",
    "switch-before-confirm",
    "switch-during-compact",
    "target-changes-during-compact",
    "switch-during-save-retry",
    "state-appended-before-retry",
    "save-response-lost-after-server-write",
    "target-changes-during-retry",
    "second-compaction-blocked-pending",
    "explicit-retry-succeeds",
    "failed-marker-persistence-retry-succeeds",
    "operation-lock-render-throws",
]

RAW_SECRET_MARKERS = [
    "SECRET_D3_KEY",
    "SECRET_VENDOR_RESPONSE",
    "C:\\private\\session",
    "/private/session",
]


def canonical_hash(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_node(script, payload):
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=True,
    )
    return json.loads(completed.stdout)


ORCHESTRATION_SCRIPT = r"""
const fs = require("fs");
const vm = require("vm");
const cryptoModule = require("crypto");
const input = JSON.parse(fs.readFileSync(0, "utf8"));

global.window = {localStorage: {getItem: () => null}};
require("./src/core/namespace.js");
require("./src/core/state.js");
require("./src/services/persistence.js");
require("./src/agent/model-request.js");
require("./src/agent/compaction.js");
require("./src/ui/messages.js");

const stateModule = window.Code.core.state;
const persistence = window.Code.services.persistence;
const modelRequest = window.Code.agent.modelRequest;
const compaction = window.Code.agent.compaction;
const messagesUi = window.Code.ui.messages;
const scenario = input.scenario;
const dispatchIdentity = {
  routeRef: "route-h3-2d3-synthetic",
  catalogRevision: 23,
};
const targetSessionId = "session-h3-2d3-target";
const secondarySessionId = "session-h3-2d3-secondary";
const originalStats = {input: 41, output: 17, cache: 3};
const originalUsage = {input: 41, output: 17};
const sourceMessages = structuredClone(input.sourceMessages);
const secondaryMessages = [{
  role: "user",
  content: "SECONDARY_SESSION_SENTINEL",
  meta: {evidenceMessageId: "secondary-message"},
}];

const state = stateModule.createAppState(window.localStorage);
state.sessions = [
  {id: targetSessionId, title: "Synthetic D3 target"},
  {id: secondarySessionId, title: "Synthetic D3 secondary"},
];
state.sessionId = targetSessionId;
state.messages = structuredClone(sourceMessages);
state.stats = structuredClone(originalStats);
state.lastUsage = structuredClone(originalUsage);
const accessors = stateModule.createSessionStateAccessors(state);
accessors.setSessionMessages(targetSessionId, state.messages);
accessors.setSessionStats(targetSessionId, state.stats);
accessors.setSessionLastUsage(targetSessionId, state.lastUsage);
accessors.setSessionRunState(targetSessionId, {});
state._sessionMsgs[secondarySessionId] = structuredClone(secondaryMessages);
state._sessionStats[secondarySessionId] = {input: 0, output: 0, cache: 0};
state._sessionRunStates[secondarySessionId] = {};

class MinimalElement {
  constructor(id) {
    this.id = id;
    this.innerHTML = "";
    this.textContent = "";
    this.value = "";
    this.disabled = false;
    this.dataset = {};
    this._handlers = new Map();
    this._classes = new Set(["hidden"]);
    this.classList = {
      add: (name) => this._classes.add(name),
      remove: (name) => this._classes.delete(name),
      contains: (name) => this._classes.has(name),
    };
  }
  addEventListener(type, handler) {
    if (!this._handlers.has(type)) this._handlers.set(type, new Set());
    this._handlers.get(type).add(handler);
  }
  removeEventListener(type, handler) {
    this._handlers.get(type)?.delete(handler);
  }
  handlerCount(type) { return this._handlers.get(type)?.size || 0; }
  dispatch(type, event = null) {
    [...(this._handlers.get(type) || [])].forEach((handler) => handler(event || {target: this}));
  }
}

const elements = new Map([
  ["compactConfirmBody", new MinimalElement("compactConfirmBody")],
  ["compactConfirmModal", new MinimalElement("compactConfirmModal")],
  ["confirmCompact", new MinimalElement("confirmCompact")],
  ["cancelCompact", new MinimalElement("cancelCompact")],
  ["cancelCompactX", new MinimalElement("cancelCompactX")],
]);
const document = {getElementById: (id) => elements.get(id)};
const confirmBtn = elements.get("confirmCompact");
const cancelBtn = elements.get("cancelCompact");
const cancelX = elements.get("cancelCompactX");
const modal = elements.get("compactConfirmModal");
const els = {
  baseUrl: {value: "http://synthetic.invalid"},
  sessionTitle: {value: "Synthetic D3 target"},
};

const switchLog = [];
function switchSession(sessionId) {
  const previous = state.sessionId;
  state._sessionMsgs[previous] = state.messages;
  state._sessionStats[previous] = state.stats;
  if (state.lastUsage) state._sessionLastUsage[previous] = state.lastUsage;
  else delete state._sessionLastUsage[previous];
  state.sessionId = sessionId;
  state.messages = state._sessionMsgs[sessionId] || [];
  state.stats = state._sessionStats[sessionId] || {input: 0, output: 0, cache: 0};
  state.lastUsage = state._sessionLastUsage[sessionId] || null;
  els.sessionTitle.value = state.sessions.find((item) => item.id === sessionId)?.title || "";
  switchLog.push({from: previous, to: sessionId});
}

function appendTargetMessage(content) {
  const messages = [...accessors.getSessionMessages(targetSessionId), {
    role: "user",
    content,
    meta: {evidenceMessageId: content.toLowerCase()},
  }];
  accessors.setSessionMessages(targetSessionId, messages);
}

const appSource = fs.readFileSync("app.js", "utf8");
const startMarker = "async function compactConversation()";
const endMarker = "function projectOptimisticFirstMessage(";
const startIndex = appSource.indexOf(startMarker);
const endIndex = appSource.indexOf(endMarker, startIndex);
if (startIndex < 0 || endIndex <= startIndex) throw new Error("invalid D3 source slice");
const sliceSource = appSource.slice(startIndex, endIndex);

const NativeDate = Date;
const fixedEpoch = NativeDate.parse("2026-08-06T12:00:00.000Z");
class FixedDate extends NativeDate {
  constructor(...args) { super(...(args.length ? args : [fixedEpoch])); }
  static now() { return fixedEpoch; }
}

const callTrace = [];
const apiCalls = [];
const dispatchCalls = [];
const saveCalls = [];
const renderCalls = [];
const toastCalls = [];
const safeLogs = [];
const unhandledRejections = [];
let saveNumber = 0;
let explicitRetryPhase = false;
let applyFailureArmed = scenario === "apply-fails";
let renderFailureArmed = scenario === "operation-lock-render-throws";
let summaryFactoryCalls = 0;
const onUnhandledRejection = (reason) => {
  unhandledRejections.push(String(reason?.message || reason || "unknown"));
};
process.on("unhandledRejection", onUnhandledRejection);

const apiJson = async (path, options = {}) => {
  const body = typeof options.body === "string" ? JSON.parse(options.body) : options.body;
  if (path === "/api/compact") {
    callTrace.push("compact");
    apiCalls.push({
      path,
      method: options.method,
      messageCount: body?.messages?.length || 0,
      routeRef: options.headers?.["X-Model-Route-Ref"] || null,
      catalogRevision: options.headers?.["X-Model-Route-Revision"] || null,
      authorizationPresent: Boolean(options.headers?.Authorization),
    });
    if ([
      "compact-throws",
      "failed-marker-persistence-retry-succeeds",
    ].includes(scenario)) {
      throw new Error("SECRET_D3_KEY SECRET_VENDOR_RESPONSE C:\\private\\session");
    }
    if (scenario === "compact-ok-false") {
      return {ok: false, error: "SECRET_VENDOR_RESPONSE"};
    }
    if (scenario === "switch-during-compact") switchSession(secondarySessionId);
    if (scenario === "target-changes-during-compact") {
      appendTargetMessage("TARGET_CHANGED_DURING_COMPACT");
    }
    return {ok: true, summary: "SYNTHETIC_D3_SUMMARY"};
  }
  if (path.endsWith("/archive")) {
    callTrace.push("archive");
    apiCalls.push({
      path,
      method: options.method,
      messageCount: body?.messages?.length || 0,
    });
    if (scenario === "archive-fails") {
      throw new Error("SECRET_VENDOR_RESPONSE /private/session");
    }
    return {ok: true, path: "synthetic-archive"};
  }
  throw new Error("unexpected apiJson path");
};

const saveSessionState = async (sessionId, messages, stats, title, options = {}) => {
  saveNumber += 1;
  const resolvedTitle = title
    || (sessionId === state.sessionId ? els.sessionTitle.value.trim() : "")
    || state.sessions.find((item) => item.id === sessionId)?.title
    || "Untitled";
  const payload = persistence.buildSessionSavePayload({
    title: resolvedTitle,
    stats,
    lastUsage: accessors.getSessionLastUsage(sessionId),
    runState: accessors.getSessionRunState(sessionId),
    messages,
    persistMessages: options.persistMessages === true,
  });
  callTrace.push(`save:${saveNumber}`);
  saveCalls.push({sessionId, title: resolvedTitle, payload: structuredClone(payload)});

  const firstSaveFails = [
    "first-save-fails-retry-succeeds",
    "both-saves-fail",
    "switch-during-save-retry",
    "state-appended-before-retry",
    "save-response-lost-after-server-write",
    "target-changes-during-retry",
    "second-compaction-blocked-pending",
    "explicit-retry-succeeds",
    "failed-marker-persistence-retry-succeeds",
  ].includes(scenario) && saveNumber === 1;
  const secondSaveFails = [
    "both-saves-fail",
    "second-compaction-blocked-pending",
    "explicit-retry-succeeds",
    "failed-marker-persistence-retry-succeeds",
  ].includes(scenario) && saveNumber === 2 && !explicitRetryPhase;

  if (scenario === "switch-during-save-retry" && saveNumber === 1) {
    switchSession(secondarySessionId);
  }
  if (scenario === "state-appended-before-retry" && saveNumber === 1) {
    appendTargetMessage("APPENDED_BEFORE_RETRY");
    state.sessions.find((item) => item.id === targetSessionId).title = "Updated D3 target title";
    if (state.sessionId === targetSessionId) els.sessionTitle.value = "Updated D3 target title";
  }
  if (scenario === "target-changes-during-retry" && saveNumber === 2) {
    appendTargetMessage("APPENDED_DURING_RETRY");
  }
  if (firstSaveFails || secondSaveFails) {
    throw new Error("SECRET_VENDOR_RESPONSE C:\\private\\session");
  }
  return {ok: true};
};

const setSessionStats = (sessionId, stats) => {
  if (
    applyFailureArmed
    && sessionId === targetSessionId
    && Number(stats?.input || 0) === 0
    && Number(stats?.output || 0) === 0
  ) {
    applyFailureArmed = false;
    throw new Error("SECRET_VENDOR_RESPONSE");
  }
  accessors.setSessionStats(sessionId, stats);
};

const summaryFactory = (result, options) => {
  summaryFactoryCalls += 1;
  if (scenario === "summary-build-throws") {
    throw new Error("SECRET_VENDOR_RESPONSE");
  }
  return compaction.createCompactSummaryMessage(result, options);
};

const renderSessionMessages = (sessionId) => {
  renderCalls.push({sessionId, activeSessionId: state.sessionId});
  if (renderFailureArmed) {
    renderFailureArmed = false;
    throw new Error("SECRET_VENDOR_RESPONSE /private/session");
  }
};

const context = vm.createContext({
  apiJson,
  buildManualCompactionPlan: compaction.buildManualCompactionPlan,
  buildSessionSavePayload: persistence.buildSessionSavePayload,
  console: {warn: (message, details) => safeLogs.push({message, details})},
  createCompactSummaryMessage: summaryFactory,
  crypto: {randomUUID: () => "d3d3d3d3-2222-4333-8444-555555555555"},
  Date: FixedDate,
  document,
  els,
  encodeURIComponent,
  formatCompact: (value) => String(value),
  getModelDispatchCredentials: async (model) => {
    dispatchCalls.push(model);
    return {
      baseUrl: els.baseUrl.value,
      keys: [],
      ...dispatchIdentity,
    };
  },
  getModelContextMessages: compaction.getModelContextMessages,
  getMsgText: (message) => Array.isArray(message?.content)
    ? String(message.content.find((part) => part?.type === "text")?.text || "")
    : String(message?.content || ""),
  getSelectedModel: () => "synthetic-model",
  getSessionLastUsage: accessors.getSessionLastUsage,
  getSessionMessages: accessors.getSessionMessages,
  getSessionRunState: accessors.getSessionRunState,
  getSessionStats: accessors.getSessionStats,
  isDetachedFromMainContext: () => false,
  isSessionStreaming: () => false,
  mapMessageForApi: modelRequest.mapMessageForApi,
  RECENT_CONTEXT_ROUND_COUNT: compaction.RECENT_CONTEXT_ROUND_COUNT,
  renderSessionMessages,
  resetRenderCache: () => {},
  saveSessionState,
  serializeSessionMessages: persistence.serializeSessionMessages,
  setSessionLastUsage: accessors.setSessionLastUsage,
  setSessionMessages: accessors.setSessionMessages,
  setSessionStats,
  setStreaming: () => {},
  showToast: (...args) => toastCalls.push(args),
  state,
  String,
  t: (key) => key,
  updateStatsPanel: () => {},
});
const compiled = new vm.Script(
  `${sliceSource}\nthis.__compactConversation = compactConversation; this.__retryManualCompactionPersistence = retryManualCompactionPersistence; this.__manualCompactionOperations = manualCompactionOperations;`,
  {filename: "app.js#manual-compaction-d3-exact-slice"},
);
compiled.runInContext(context);

async function settle() {
  for (let index = 0; index < 80; index += 1) {
    await new Promise((resolve) => setImmediate(resolve));
    if (
      confirmBtn.disabled === false
      && context.__manualCompactionOperations().size === 0
      && !state._manualCompactionConfirmSessionId
    ) return;
  }
  throw new Error("manual compaction did not settle");
}

(async () => {
  await context.__compactConversation();
  if (scenario === "switch-before-confirm") switchSession(secondarySessionId);
  const handlersBefore = {
    confirm: confirmBtn.handlerCount("click"),
    cancel: cancelBtn.handlerCount("click") + cancelX.handlerCount("click"),
    modal: modal.handlerCount("click"),
  };
  confirmBtn.dispatch("click");
  await settle();

  const beforeRepeat = {api: apiCalls.length, save: saveCalls.length};
  confirmBtn.dispatch("click");
  await new Promise((resolve) => setImmediate(resolve));
  const repeatDelta = {
    api: apiCalls.length - beforeRepeat.api,
    save: saveCalls.length - beforeRepeat.save,
  };

  let secondCompactionDelta = null;
  if (scenario === "second-compaction-blocked-pending") {
    const before = {api: apiCalls.length, save: saveCalls.length};
    await context.__compactConversation();
    secondCompactionDelta = {
      api: apiCalls.length - before.api,
      save: saveCalls.length - before.save,
      confirmHandlers: confirmBtn.handlerCount("click"),
    };
  }

  let explicitRetryDelta = null;
  let pendingRetryHtml = null;
  const feature = messagesUi.createMessagesFeature({
    escapeHtml: (value) => String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;"),
    renderMarkdown: (value) => String(value || ""),
    t: (key) => key,
    getMessageText: (message) => String(message?.content || ""),
  });
  const projectTargetHtml = () => {
    const nativeProjectionDate = global.Date;
    global.Date = FixedDate;
    try {
      return feature.projectMessages(
        accessors.getSessionMessages(targetSessionId),
        {hasActiveRun: false},
      );
    } finally {
      global.Date = nativeProjectionDate;
    }
  };
  if ([
    "explicit-retry-succeeds",
    "failed-marker-persistence-retry-succeeds",
  ].includes(scenario)) {
    pendingRetryHtml = projectTargetHtml();
    appendTargetMessage("APPENDED_BEFORE_EXPLICIT_RETRY");
    state.sessions.find((item) => item.id === targetSessionId).title = "Explicit retry current title";
    if (state.sessionId === targetSessionId) els.sessionTitle.value = "Explicit retry current title";
    const pendingMarker = accessors.getSessionMessages(targetSessionId).find((message) => (
      message?.meta?.kind === "manual-context-compaction"
      && message.meta.persistenceStatus === "failed"
    ));
    const before = {
      compact: callTrace.filter((item) => item === "compact").length,
      archive: callTrace.filter((item) => item === "archive").length,
      summary: summaryFactoryCalls,
      save: saveCalls.length,
    };
    explicitRetryPhase = true;
    await context.__retryManualCompactionPersistence(
      targetSessionId,
      pendingMarker.meta.compactionId,
    );
    explicitRetryDelta = {
      compact: callTrace.filter((item) => item === "compact").length - before.compact,
      archive: callTrace.filter((item) => item === "archive").length - before.archive,
      summary: summaryFactoryCalls - before.summary,
      save: saveCalls.length - before.save,
    };
  }

  let lockRecovery = null;
  if (scenario === "operation-lock-render-throws") {
    const before = {api: apiCalls.length, save: saveCalls.length};
    await context.__compactConversation();
    lockRecovery = {
      operationCount: context.__manualCompactionOperations().size,
      confirmHandlersBeforeCancel: confirmBtn.handlerCount("click"),
      apiDelta: apiCalls.length - before.api,
      saveDelta: saveCalls.length - before.save,
    };
    cancelBtn.dispatch("click");
    lockRecovery.handlersAfterCancel = {
      confirm: confirmBtn.handlerCount("click"),
      cancel: cancelBtn.handlerCount("click") + cancelX.handlerCount("click"),
      modal: modal.handlerCount("click"),
    };
  }

  const targetMessages = accessors.getSessionMessages(targetSessionId);
  const html = projectTargetHtml();
  await new Promise((resolve) => setImmediate(resolve));
  process.removeListener("unhandledRejection", onUnhandledRejection);
  process.stdout.write(JSON.stringify({
    scenario,
    slice: {
      sha256: cryptoModule.createHash("sha256").update(sliceSource, "utf8").digest("hex"),
      characterLength: sliceSource.length,
    },
    targetSessionId,
    secondarySessionId,
    activeSessionId: state.sessionId,
    targetMessages: structuredClone(targetMessages),
    targetStats: structuredClone(accessors.getSessionStats(targetSessionId)),
    targetLastUsage: structuredClone(accessors.getSessionLastUsage(targetSessionId)),
    targetTitle: state.sessions.find((item) => item.id === targetSessionId)?.title,
    activeMessages: structuredClone(state.messages),
    secondaryMessages: structuredClone(accessors.getSessionMessages(secondarySessionId)),
    callTrace,
    apiCalls,
    dispatchCalls,
    dispatchIdentity,
    saveCalls,
    renderCalls,
    toastCalls,
    safeLogs,
    switchLog,
    handlersBefore,
    handlersAfter: {
      confirm: confirmBtn.handlerCount("click"),
      cancel: cancelBtn.handlerCount("click") + cancelX.handlerCount("click"),
      modal: modal.handlerCount("click"),
    },
    repeatDelta,
    secondCompactionDelta,
    explicitRetryDelta,
    pendingRetryHtml,
    lockRecovery,
    summaryFactoryCalls,
    unhandledRejections,
    html,
  }));
})().catch((error) => {
  process.stderr.write(error.stack || String(error));
  process.exitCode = 1;
});
"""


def summarize_case(output):
    messages = output["targetMessages"]
    summaries = [
        message for message in messages
        if message.get("meta", {}).get("kind") == "compact-summary"
    ]
    markers = [
        message for message in messages
        if message.get("meta", {}).get("kind") == "manual-context-compaction"
    ]
    marker_meta = markers[-1].get("meta", {}) if markers else {}
    persisted_marker = {
        key: marker_meta.get(key)
        for key in (
            "status",
            "errorStage",
            "errorCode",
            "archiveStatus",
            "archiveErrorCode",
            "persistenceStatus",
            "persistenceErrorCode",
            "compactionId",
        )
        if marker_meta.get(key) is not None
    }
    output_text = json.dumps(output, ensure_ascii=False, sort_keys=True)
    raw_error_leak = any(secret in output_text for secret in RAW_SECRET_MARKERS)
    result = {
        "id": output["scenario"],
        "callTrace": output["callTrace"],
        "dispatchCalls": output["dispatchCalls"],
        "compactRouteHeaders": [
            {
                "routeRef": call["routeRef"],
                "catalogRevision": call["catalogRevision"],
                "authorizationPresent": call["authorizationPresent"],
            }
            for call in output["apiCalls"]
            if call["path"] == "/api/compact"
        ],
        "counts": {
            "messages": len(messages),
            "summaries": len(summaries),
            "markers": len(markers),
            "compact": sum(item == "compact" for item in output["callTrace"]),
            "archive": sum(item == "archive" for item in output["callTrace"]),
            "summaryFactory": output["summaryFactoryCalls"],
            "save": len(output["saveCalls"]),
        },
        "marker": persisted_marker,
        "messagesHash": canonical_hash(messages),
        "stats": output["targetStats"],
        "lastUsage": output["targetLastUsage"],
        "activeSessionId": output["activeSessionId"],
        "targetTitle": output["targetTitle"],
        "saveMessageCounts": [len(call["payload"].get("messages", [])) for call in output["saveCalls"]],
        "saveTitles": [call["title"] for call in output["saveCalls"]],
        "savePayloadHashes": [canonical_hash(call["payload"]) for call in output["saveCalls"]],
        "secondaryMessagesHash": canonical_hash(output["secondaryMessages"]),
        "activeMessagesHash": canonical_hash(output["activeMessages"]),
        "renderTargets": output["renderCalls"],
        "toastKeys": [call[0] for call in output["toastCalls"] if call],
        "handlersAfter": output["handlersAfter"],
        "repeatDelta": output["repeatDelta"],
        "secondCompactionDelta": output["secondCompactionDelta"],
        "explicitRetryDelta": output["explicitRetryDelta"],
        "pendingUiHash": (
            hashlib.sha256(output["pendingRetryHtml"].encode("utf-8")).hexdigest()
            if output["pendingRetryHtml"] is not None else None
        ),
        "lockRecovery": output["lockRecovery"],
        "unhandledRejectionCount": len(output["unhandledRejections"]),
        "uiHash": hashlib.sha256(output["html"].encode("utf-8")).hexdigest(),
        "rawErrorLeak": raw_error_leak,
    }
    result["scenarioHash"] = canonical_hash(result)
    return result


def collect_suite(fixture):
    d2_fixture = json.loads(D2_FIXTURE_PATH.read_text(encoding="utf-8"))
    results = {}
    raw_outputs = {}
    slice_evidence = None
    dispatch_identity = None
    for case in fixture["cases"]:
        output = run_node(ORCHESTRATION_SCRIPT, {
            "scenario": case["id"],
            "sourceMessages": d2_fixture["sourceMessages"],
        })
        raw_outputs[case["id"]] = output
        results[case["id"]] = summarize_case(output)
        slice_evidence = output["slice"]
        if dispatch_identity is None:
            dispatch_identity = output["dispatchIdentity"]
        elif output["dispatchIdentity"] != dispatch_identity:
            raise AssertionError("dispatch identity changed across scenarios")
    evidence = {
        "evidenceProfile": fixture["evidenceProfile"],
        "cases": fixture["cases"],
        "sourceFixtureSha256": file_hash(D2_FIXTURE_PATH),
        "slice": slice_evidence,
        "dispatchIdentity": dispatch_identity,
        "results": results,
    }
    evidence["suiteHash"] = canonical_hash(evidence)
    return evidence, raw_outputs


def first_difference(expected, actual, path="$"):
    if type(expected) is not type(actual):
        return path
    if isinstance(expected, dict):
        expected_keys = list(expected)
        actual_keys = list(actual)
        if expected_keys != actual_keys:
            for key in expected_keys:
                if key not in actual:
                    return f"{path}.{key}"
            for key in actual_keys:
                if key not in expected:
                    return f"{path}.{key}"
            return path
        for key in expected_keys:
            difference = first_difference(expected[key], actual[key], f"{path}.{key}")
            if difference:
                return difference
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path}[{min(len(expected), len(actual))}]"
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            difference = first_difference(expected_item, actual_item, f"{path}[{index}]")
            if difference:
                return difference
        return None
    return None if expected == actual else path


class SaveHandler:
    def __init__(self, payload, lose_response=False):
        self.payload = payload
        self.lose_response = lose_response
        self.response = None

    def read_body_json(self):
        return deepcopy(self.payload)

    def send_json(self, payload, status=200):
        self.response = {"status": status, "payload": deepcopy(payload)}
        if self.lose_response:
            raise ConnectionError("synthetic response lost")


class TestHarnessManualCompactionFailureBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(
            cls.schema,
            format_checker=FormatChecker(),
        )
        cls.evidence, cls.raw_outputs = collect_suite(cls.fixture)

    def test_manifest_schema_profile_and_case_order_are_strict(self):
        self.assertEqual(list(self.validator.iter_errors(self.fixture)), [])
        self.assertEqual([case["id"] for case in self.fixture["cases"]], CASE_IDS)
        self.assertEqual(self.fixture["schemaVersion"], 1)
        self.assertEqual(self.fixture["evidenceProfile"]["version"], 1)
        self.assertEqual(
            self.fixture["evidenceProfile"]["execution"],
            "current-app-js-exact-source-slice",
        )

    def test_failure_and_session_ownership_matrix(self):
        results = self.evidence["results"]
        original_stats = {"input": 41, "output": 17, "cache": 3}
        original_usage = {"input": 41, "output": 17}

        for case_id in CASE_IDS:
            with self.subTest(case=case_id):
                result = results[case_id]
                self.assertEqual(result["counts"]["markers"], 1)
                self.assertFalse(result["rawErrorLeak"])
                self.assertEqual(result["handlersAfter"], {"confirm": 0, "cancel": 0, "modal": 0})
                self.assertEqual(result["repeatDelta"], {"api": 0, "save": 0})
                self.assertEqual(result["unhandledRejectionCount"], 0)

        for case_id, stage, code in (
            ("compact-throws", "compact_request", "compact_request_failed"),
            ("compact-ok-false", "compact_result", "compact_rejected"),
            ("summary-build-throws", "summary_build", "summary_build_failed"),
            ("apply-fails", "state_apply", "state_apply_failed"),
        ):
            result = results[case_id]
            self.assertEqual(result["marker"]["status"], "failed")
            self.assertEqual(result["marker"]["errorStage"], stage)
            self.assertEqual(result["marker"]["errorCode"], code)
            self.assertEqual(result["counts"]["summaries"], 0)
            self.assertEqual(result["stats"], original_stats)
            self.assertEqual(result["lastUsage"], original_usage)

        self.assertEqual(results["compact-throws"]["counts"]["archive"], 0)
        self.assertEqual(results["compact-ok-false"]["counts"]["archive"], 0)
        self.assertEqual(results["summary-build-throws"]["counts"]["archive"], 0)

        archive = results["archive-fails"]
        self.assertEqual(archive["marker"]["status"], "completed")
        self.assertEqual(archive["marker"]["archiveStatus"], "failed")
        self.assertEqual(archive["marker"]["archiveErrorCode"], "archive_failed")
        self.assertEqual(archive["counts"]["summaries"], 1)
        self.assertEqual(archive["counts"]["archive"], 1)
        self.assertIn(
            "manualCompactArchiveWarning",
            self.raw_outputs["archive-fails"]["html"],
        )

        recovered = results["first-save-fails-retry-succeeds"]
        self.assertEqual(recovered["counts"]["save"], 2)
        self.assertEqual(recovered["marker"]["status"], "completed")
        self.assertNotIn("persistenceStatus", recovered["marker"])
        self.assertIn("compactionId", recovered["marker"])

        normal = results["repeat-confirm"]
        self.assertEqual(normal["marker"], {"status": "completed"})

        failed_save = results["both-saves-fail"]
        self.assertEqual(failed_save["counts"]["save"], 2)
        self.assertEqual(failed_save["marker"]["status"], "completed")
        self.assertEqual(failed_save["marker"]["persistenceStatus"], "failed")
        self.assertEqual(failed_save["marker"]["persistenceErrorCode"], "session_save_failed")
        self.assertIn(
            "manualCompactPersistenceFailed",
            self.raw_outputs["both-saves-fail"]["html"],
        )
        self.assertIn(
            "data-manual-compaction-retry",
            self.raw_outputs["both-saves-fail"]["html"],
        )

        target_changed = results["target-changes-during-compact"]
        self.assertEqual(target_changed["marker"]["errorStage"], "target_session")
        self.assertEqual(target_changed["marker"]["errorCode"], "target_session_changed")
        self.assertEqual(target_changed["counts"]["archive"], 0)
        self.assertEqual(target_changed["counts"]["summaries"], 0)
        self.assertIn("TARGET_CHANGED_DURING_COMPACT", json.dumps(
            self.raw_outputs["target-changes-during-compact"]["targetMessages"]
        ))

        for case_id in (
            "switch-before-confirm",
            "switch-during-compact",
            "switch-during-save-retry",
        ):
            result = results[case_id]
            self.assertEqual(result["activeSessionId"], "session-h3-2d3-secondary")
            self.assertEqual(result["marker"]["status"], "completed")
            self.assertEqual(
                self.raw_outputs[case_id]["secondaryMessages"],
                [{
                    "role": "user",
                    "content": "SECONDARY_SESSION_SENTINEL",
                    "meta": {"evidenceMessageId": "secondary-message"},
                }],
            )

        appended = results["state-appended-before-retry"]
        self.assertEqual(appended["counts"]["save"], 2)
        self.assertEqual(appended["saveMessageCounts"][-1], appended["counts"]["messages"])
        self.assertEqual(appended["saveTitles"][-1], "Updated D3 target title")
        self.assertIn("APPENDED_BEFORE_RETRY", json.dumps(
            self.raw_outputs["state-appended-before-retry"]["saveCalls"][-1]["payload"]
        ))

        changed_retry = results["target-changes-during-retry"]
        self.assertEqual(changed_retry["marker"]["persistenceStatus"], "failed")
        self.assertEqual(
            changed_retry["marker"]["persistenceErrorCode"],
            "session_changed_during_save",
        )

        blocked = results["second-compaction-blocked-pending"]
        self.assertEqual(blocked["secondCompactionDelta"], {
            "api": 0,
            "save": 0,
            "confirmHandlers": 0,
        })
        self.assertIn("manualCompactPersistencePending", blocked["toastKeys"])

        explicit = results["explicit-retry-succeeds"]
        self.assertEqual(explicit["explicitRetryDelta"], {
            "compact": 0, "archive": 0, "summary": 0, "save": 1,
        })
        self.assertNotIn("persistenceStatus", explicit["marker"])
        self.assertEqual(explicit["marker"]["status"], "completed")
        self.assertEqual(explicit["saveTitles"][-1], "Explicit retry current title")
        self.assertIn("APPENDED_BEFORE_EXPLICIT_RETRY", json.dumps(
            self.raw_outputs["explicit-retry-succeeds"]["saveCalls"][-1]["payload"]
        ))

        failed_retry = results["failed-marker-persistence-retry-succeeds"]
        failed_retry_raw = self.raw_outputs["failed-marker-persistence-retry-succeeds"]
        self.assertEqual(failed_retry["counts"]["summaries"], 0)
        self.assertEqual(failed_retry["counts"]["markers"], 1)
        self.assertEqual(failed_retry["counts"]["compact"], 1)
        self.assertEqual(failed_retry["counts"]["archive"], 0)
        self.assertEqual(failed_retry["counts"]["summaryFactory"], 0)
        self.assertEqual(failed_retry["counts"]["save"], 3)
        self.assertEqual(failed_retry["marker"]["status"], "failed")
        self.assertEqual(failed_retry["marker"]["errorStage"], "compact_request")
        self.assertEqual(failed_retry["marker"]["errorCode"], "compact_request_failed")
        self.assertNotIn("persistenceStatus", failed_retry["marker"])
        self.assertNotIn("persistenceErrorCode", failed_retry["marker"])
        self.assertEqual(failed_retry["stats"], original_stats)
        self.assertEqual(failed_retry["lastUsage"], original_usage)
        self.assertEqual(failed_retry["explicitRetryDelta"], {
            "compact": 0, "archive": 0, "summary": 0, "save": 1,
        })
        self.assertIn("manualCompactFailurePersistenceFailed", failed_retry_raw["pendingRetryHtml"])
        self.assertIn("data-manual-compaction-retry", failed_retry_raw["pendingRetryHtml"])
        self.assertNotIn("manualCompactedContext", failed_retry_raw["pendingRetryHtml"])
        self.assertIn("manualCompactContextFailed", failed_retry_raw["html"])
        self.assertNotIn("manualCompactedContext", failed_retry_raw["html"])
        self.assertIn("manualCompactFailurePersistenceFailed", failed_retry["toastKeys"])
        source_messages = json.loads(D2_FIXTURE_PATH.read_text(encoding="utf-8"))["sourceMessages"]
        self.assertEqual(
            failed_retry_raw["targetMessages"][:len(source_messages)],
            source_messages,
        )
        self.assertEqual(
            failed_retry_raw["saveCalls"][-1]["payload"]["messages"][-1]["content"],
            "APPENDED_BEFORE_EXPLICIT_RETRY",
        )
        persisted_failed_meta = failed_retry_raw["saveCalls"][-1]["payload"]["messages"][-2]["meta"]
        self.assertEqual(persisted_failed_meta["status"], "failed")
        self.assertEqual(persisted_failed_meta["errorStage"], "compact_request")
        self.assertEqual(persisted_failed_meta["errorCode"], "compact_request_failed")
        self.assertNotIn("persistenceStatus", persisted_failed_meta)
        self.assertNotIn("persistenceErrorCode", persisted_failed_meta)

        lock_failure = results["operation-lock-render-throws"]
        self.assertEqual(lock_failure["marker"]["status"], "failed")
        self.assertEqual(lock_failure["marker"]["errorStage"], "state_apply")
        self.assertEqual(lock_failure["marker"]["errorCode"], "state_apply_failed")
        self.assertEqual(lock_failure["lockRecovery"], {
            "operationCount": 0,
            "confirmHandlersBeforeCancel": 1,
            "apiDelta": 0,
            "saveDelta": 0,
            "handlersAfterCancel": {"confirm": 0, "cancel": 0, "modal": 0},
        })

    def test_response_lost_after_real_server_write_converges_in_temp_storage(self):
        output = self.raw_outputs["save-response-lost-after-server-write"]
        self.assertEqual(len(output["saveCalls"]), 2)
        first_payload = output["saveCalls"][0]["payload"]
        retry_payload = output["saveCalls"][1]["payload"]
        first_request = {**deepcopy(first_payload), "expectedRevision": 0}
        session_id = "session-h3-2d3-response-lost"

        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp).resolve() / "sessions"
            sessions_dir.mkdir(parents=True)
            with patch.object(server, "SESSIONS_DIR", sessions_dir), patch.object(
                server,
                "now_iso",
                return_value="2026-08-06T12:00:00.000Z",
            ):
                meta_path = server.session_path(session_id).resolve()
                self.assertTrue(meta_path.is_relative_to(sessions_dir))
                server.write_json(meta_path, {
                    "id": session_id,
                    "title": "Before response loss",
                    "createdAt": "2026-08-06T12:00:00.000Z",
                })

                first_handler = SaveHandler(first_request, lose_response=True)
                with self.assertRaises(ConnectionError):
                    server.CodeHandler.save_session(first_handler, session_id)
                first_disk = server.read_jsonl(server.messages_path(session_id))
                self.assertEqual(first_disk, first_payload["messages"])
                committed_revision = server.read_json(meta_path, {})["revision"]
                self.assertEqual(committed_revision, 1)

                retry_request = {
                    **deepcopy(retry_payload),
                    "expectedRevision": committed_revision,
                }
                retry_handler = SaveHandler(retry_request)
                server.CodeHandler.save_session(retry_handler, session_id)
                final_path = server.messages_path(session_id).resolve()
                self.assertTrue(final_path.is_relative_to(sessions_dir))
                final_disk = server.read_jsonl(final_path)
                self.assertEqual(final_disk, retry_payload["messages"])
                self.assertEqual(server.read_json(meta_path, {})["revision"], 2)
                self.assertEqual(sum(
                    message.get("meta", {}).get("kind") == "compact-summary"
                    for message in final_disk
                ), 1)
                self.assertEqual(sum(
                    message.get("meta", {}).get("kind") == "manual-context-compaction"
                    for message in final_disk
                ), 1)

    def test_hashes_and_mutation_first_difference_paths_are_frozen(self):
        expected = self.fixture["expected"]
        self.assertEqual(self.evidence["sourceFixtureSha256"], expected["sourceFixtureSha256"])
        self.assertEqual(self.evidence["slice"], expected["slice"])
        self.assertEqual(self.evidence["dispatchIdentity"], expected["dispatchIdentity"])
        actual_hashes = {
            case_id: self.evidence["results"][case_id]["scenarioHash"]
            for case_id in CASE_IDS
        }
        self.assertEqual(actual_hashes, expected["scenarioHashes"])
        self.assertEqual(self.evidence["suiteHash"], expected["suiteHash"])

        baseline = {
            "evidenceProfile": deepcopy(self.fixture["evidenceProfile"]),
            "cases": deepcopy(self.fixture["cases"]),
            "results": deepcopy(self.evidence["results"]),
        }
        mutations = {}

        mutated = deepcopy(baseline)
        mutated["cases"][0], mutated["cases"][1] = mutated["cases"][1], mutated["cases"][0]
        mutations["caseOrder"] = first_difference(baseline, mutated)

        mutated = deepcopy(baseline)
        mutated["results"]["compact-throws"]["marker"]["errorCode"] = "wrong"
        mutations["errorCode"] = first_difference(baseline, mutated)

        mutated = deepcopy(baseline)
        mutated["results"]["both-saves-fail"]["marker"]["persistenceStatus"] = "wrong"
        mutations["persistenceStatus"] = first_difference(baseline, mutated)

        mutated = deepcopy(baseline)
        mutated["results"]["archive-fails"]["callTrace"][1] = "save:wrong"
        mutations["callOrder"] = first_difference(baseline, mutated)

        mutated = deepcopy(baseline)
        mutated["results"]["compact-throws"]["rawErrorLeak"] = True
        mutations["rawErrorLeak"] = first_difference(baseline, mutated)

        mutated = deepcopy(baseline)
        mutated["evidenceProfile"]["scope"] = "wrong"
        mutations["profile"] = first_difference(baseline, mutated)

        mutated = deepcopy(baseline)
        mutated["results"]["failed-marker-persistence-retry-succeeds"]["pendingUiHash"] = "0" * 64
        mutations["failedPersistenceUi"] = first_difference(baseline, mutated)

        mutated = deepcopy(baseline)
        mutated["results"]["operation-lock-render-throws"]["lockRecovery"]["operationCount"] = 1
        mutations["operationLock"] = first_difference(baseline, mutated)

        self.assertEqual(mutations, expected["mutationFirstDifferencePaths"])

    def test_deterministic_replay_has_no_skips(self):
        replay, _ = collect_suite(self.fixture)
        self.assertEqual(replay, self.evidence)
        self.assertEqual(len(self.evidence["results"]), 19)


if __name__ == "__main__":
    unittest.main()
