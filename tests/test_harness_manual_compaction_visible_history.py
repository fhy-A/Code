"""H3-2D2 exact app.js source-slice manual compaction evidence."""

import hashlib
import html
import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, FormatChecker

import server as server_mod


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "harness"
SCHEMA_PATH = FIXTURE_DIR / "manual-compaction-visible-history-evidence.schema.json"
FIXTURE_PATH = FIXTURE_DIR / "manual-compaction-visible-history-evidence.json"
APP_PATH = ROOT / "app.js"

EXPECTED_FIXTURE_SHA256 = "f1a5ae6abcd16759c9a788349b91cd5887735859c23111d9df965003896b0fe5"
EXPECTED_SLICE_SHA256 = "75508cb263c790549546faa08adf3941d0964693b6d73e659c29fe3d38174710"
EXPECTED_PROFILE = {
    "id": "h3-2d2-manual-compaction-visible-history",
    "version": 1,
    "scope": "exact-app-source-slice-success-chain",
}
EXPECTED_SOURCE_MESSAGE_IDS = [
    "msg-user-0",
    "msg-assistant-0",
    "msg-user-1",
    "msg-assistant-tool-plan-1",
    "msg-tool-call-1",
    "msg-tool-result-1",
    "msg-assistant-tool-final-1",
    "msg-user-2",
    "msg-assistant-2",
    "msg-user-3",
    "msg-assistant-3",
    "msg-user-4",
    "msg-assistant-4",
]
EXPECTED_VISIBLE_SENTINELS = [
    "VISIBLE_USER_0",
    "VISIBLE_ASSISTANT_0",
    "VISIBLE_USER_1",
    "VISIBLE_ASSISTANT_TOOL_PLAN_1",
    "VISIBLE_TOOL_RESULT_1",
    "VISIBLE_ASSISTANT_TOOL_FINAL_1",
    "VISIBLE_USER_2",
    "VISIBLE_ASSISTANT_2",
    "VISIBLE_USER_3",
    "VISIBLE_ASSISTANT_3",
    "VISIBLE_USER_4",
    "VISIBLE_ASSISTANT_4",
]


ORCHESTRATION_SCRIPT = r"""
const fs = require("fs");
const vm = require("vm");
const crypto = require("crypto");
const input = JSON.parse(fs.readFileSync(0, "utf8"));

let forbiddenFetchCalls = 0;
global.fetch = () => {
  forbiddenFetchCalls += 1;
  throw new Error("network access is forbidden in H3-2D2");
};
global.window = {
  localStorage: {getItem: () => null},
};
require("./src/core/namespace.js");
require("./src/core/state.js");
require("./src/services/persistence.js");
require("./src/agent/model-request.js");
require("./src/agent/compaction.js");

const stateModule = window.Code.core.state;
const persistence = window.Code.services.persistence;
const modelRequest = window.Code.agent.modelRequest;
const compaction = window.Code.agent.compaction;
const sourceMessages = structuredClone(input.sourceMessages);
const sourceBefore = structuredClone(sourceMessages);
const state = stateModule.createAppState(window.localStorage);
state.sessionId = input.fixedInputs.sessionId;
state.messages = structuredClone(sourceMessages);
state.stats = {input: 41, output: 17, cache: 3};
state.lastUsage = {input: 41, output: 17};
state.sessions = [{id: input.fixedInputs.sessionId, title: "Synthetic manual compaction evidence"}];
const stateAccessors = stateModule.createSessionStateAccessors(state);
stateAccessors.setSessionMessages(state.sessionId, state.messages);
stateAccessors.setSessionStats(state.sessionId, state.stats);
stateAccessors.setSessionLastUsage(state.sessionId, state.lastUsage);

const appSource = fs.readFileSync("app.js", "utf8");
const startMarker = input.sourceSlice.startMarker;
const endMarker = input.sourceSlice.endMarker;
const requiredFunction = input.sourceSlice.requiredFunction;
const markerCount = (source, marker) => source.split(marker).length - 1;
const startMarkerCount = markerCount(appSource, startMarker);
const endMarkerCount = markerCount(appSource, endMarker);
if (startMarkerCount !== 1 || endMarkerCount !== 1) {
  throw new Error(`source slice boundaries must be unique: ${startMarkerCount}/${endMarkerCount}`);
}
const startIndex = appSource.indexOf(startMarker);
const endIndex = appSource.indexOf(endMarker, startIndex);
if (startIndex < 0 || endIndex <= startIndex) throw new Error("invalid source slice boundaries");
const sliceSource = appSource.slice(startIndex, endIndex);
const sliceSha256 = crypto.createHash("sha256").update(sliceSource, "utf8").digest("hex");
const containsHideCompactConfirm = sliceSource.includes(requiredFunction);
if (!containsHideCompactConfirm) throw new Error("source slice omits hideCompactConfirm");

class MinimalElement {
  constructor(id) {
    this.id = id;
    this.innerHTML = "";
    this.textContent = "";
    this.disabled = false;
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
  handlerCount(type) {
    return this._handlers.get(type)?.size || 0;
  }
  dispatch(type, event = null) {
    const handlers = [...(this._handlers.get(type) || [])];
    const actualEvent = event || {target: this};
    handlers.forEach((handler) => handler(actualEvent));
  }
}

const elements = new Map([
  ["compactConfirmBody", new MinimalElement("compactConfirmBody")],
  ["compactConfirmModal", new MinimalElement("compactConfirmModal")],
  ["confirmCompact", new MinimalElement("confirmCompact")],
  ["cancelCompact", new MinimalElement("cancelCompact")],
  ["cancelCompactX", new MinimalElement("cancelCompactX")],
]);
const document = {
  getElementById: (id) => {
    if (!elements.has(id)) throw new Error(`unexpected DOM lookup: ${id}`);
    return elements.get(id);
  },
};
const confirmBtn = elements.get("confirmCompact");
const cancelBtn = elements.get("cancelCompact");
const cancelX = elements.get("cancelCompactX");
const modal = elements.get("compactConfirmModal");
const els = {
  baseUrl: {value: input.fixedInputs.baseUrl},
  sessionTitle: {value: "Synthetic manual compaction evidence"},
};

const NativeDate = Date;
const fixedEpoch = NativeDate.parse(input.fixedInputs.now);
class FixedDate extends NativeDate {
  constructor(...args) {
    super(...(args.length ? args : [fixedEpoch]));
  }
  static now() {
    return fixedEpoch;
  }
}

const getMessageText = (message) => {
  const content = message?.content;
  if (!content) return "";
  if (Array.isArray(content)) {
    return content.find((part) => part?.type === "text")?.text || "";
  }
  return String(content);
};
const isDetachedFromMainContext = (message) => Boolean(
  message?.meta?.detachedFromMain
  || message?.meta?.kind === "background-subagent-notify"
);

const activeContext = compaction.getModelContextMessages(
  sourceMessages,
  isDetachedFromMainContext,
);
const plan = compaction.buildManualCompactionPlan(activeContext, {
  mapMessageForApi: modelRequest.mapMessageForApi,
  getMessageText,
  isDetachedMessage: isDetachedFromMainContext,
  recentRoundCount: compaction.RECENT_CONTEXT_ROUND_COUNT,
});

const apiCalls = [];
const dispatchCalls = [];
const saveCalls = [];
const renderCalls = [];
const setStreamingCalls = [];
const toastCalls = [];
let resolveSave;
const saveCompleted = new Promise((resolve) => { resolveSave = resolve; });
const apiJson = async (path, options = {}) => {
  const body = typeof options.body === "string" ? JSON.parse(options.body) : options.body;
  apiCalls.push({
    path,
    method: options.method || "GET",
    headers: structuredClone(options.headers || {}),
    body: structuredClone(body),
  });
  if (path === "/api/compact") {
    return {ok: true, summary: input.fixedInputs.summary};
  }
  if (path.endsWith("/archive")) {
    return {ok: true, path: "captured-by-h3-2d2"};
  }
  throw new Error(`unexpected apiJson path: ${path}`);
};
const saveSessionState = async (sessionId, messages, stats, title, options) => {
  saveCalls.push({
    sessionId,
    messages: structuredClone(messages),
    stats: structuredClone(stats),
    title: title ?? null,
    options: structuredClone(options || {}),
  });
  resolveSave();
  return {ok: true};
};

const context = vm.createContext({
  apiJson,
  buildManualCompactionPlan: compaction.buildManualCompactionPlan,
  buildSessionSavePayload: persistence.buildSessionSavePayload,
  createCompactSummaryMessage: compaction.createCompactSummaryMessage,
  Date: FixedDate,
  document,
  els,
  encodeURIComponent,
  formatCompact: (value) => String(value),
  getModelDispatchCredentials: async (model) => {
    dispatchCalls.push(model);
    return {
      baseUrl: input.fixedInputs.baseUrl,
      keys: [],
      routeRef: input.fixedInputs.routeRef,
      catalogRevision: input.fixedInputs.catalogRevision,
    };
  },
  getSessionLastUsage: stateAccessors.getSessionLastUsage,
  getSessionMessages: stateAccessors.getSessionMessages,
  getSessionRunState: stateAccessors.getSessionRunState,
  getSessionStats: stateAccessors.getSessionStats,
  getModelContextMessages: compaction.getModelContextMessages,
  getMsgText: getMessageText,
  getSelectedModel: () => input.fixedInputs.model,
  isDetachedFromMainContext,
  isSessionStreaming: () => false,
  mapMessageForApi: modelRequest.mapMessageForApi,
  RECENT_CONTEXT_ROUND_COUNT: compaction.RECENT_CONTEXT_ROUND_COUNT,
  renderSessionMessages: (sessionId) => renderCalls.push({
    sessionId,
    messageCount: stateAccessors.getSessionMessages(sessionId).length,
  }),
  resetRenderCache: () => {},
  saveSessionState,
  serializeSessionMessages: persistence.serializeSessionMessages,
  setSessionLastUsage: stateAccessors.setSessionLastUsage,
  setSessionMessages: stateAccessors.setSessionMessages,
  setSessionStats: stateAccessors.setSessionStats,
  setStreaming: (active, sessionId) => setStreamingCalls.push({active, sessionId}),
  showToast: (...args) => toastCalls.push(args),
  state,
  String,
  t: (key) => key,
  updateStatsPanel: () => {},
});
const compiled = new vm.Script(
  `${sliceSource}\nthis.__compactConversation = compactConversation;`,
  {filename: "app.js#compactConversation-exact-slice"},
);
compiled.runInContext(context);
if (typeof context.__compactConversation !== "function") {
  throw new Error("compiled slice did not expose compactConversation");
}

(async () => {
  await context.__compactConversation();
  const handlersBefore = {
    confirm: confirmBtn.handlerCount("click"),
    cancel: cancelBtn.handlerCount("click") + cancelX.handlerCount("click"),
    modal: modal.handlerCount("click"),
  };
  confirmBtn.dispatch("click");
  await saveCompleted;
  await Promise.resolve();
  await Promise.resolve();

  const handlersAfter = {
    confirm: confirmBtn.handlerCount("click"),
    cancel: cancelBtn.handlerCount("click") + cancelX.handlerCount("click"),
    modal: modal.handlerCount("click"),
  };
  const beforeRepeat = {
    compact: apiCalls.filter((call) => call.path === "/api/compact").length,
    archive: apiCalls.filter((call) => call.path.endsWith("/archive")).length,
    save: saveCalls.length,
  };
  confirmBtn.dispatch("click");
  await Promise.resolve();
  await Promise.resolve();
  const afterRepeat = {
    compact: apiCalls.filter((call) => call.path === "/api/compact").length,
    archive: apiCalls.filter((call) => call.path.endsWith("/archive")).length,
    save: saveCalls.length,
  };

  const saveCall = saveCalls[0];
  const serializedFinal = persistence.serializeSessionMessages(
    saveCall.messages,
    {includeModel: true, includeTime: true},
  );
  const savePayload = persistence.buildSessionSavePayload({
    title: "Synthetic manual compaction evidence",
    stats: saveCall.stats,
    lastUsage: null,
    runState: {},
    messages: saveCall.messages,
    persistMessages: true,
  });
  process.stdout.write(JSON.stringify({
    slice: {
      startMarkerCount,
      endMarkerCount,
      containsHideCompactConfirm,
      characterLength: sliceSource.length,
      sha256: sliceSha256,
      compiledInVm: true,
    },
    sourceBefore,
    sourceInputUnchanged: JSON.stringify(sourceMessages) === JSON.stringify(sourceBefore),
    plan: {
      activeContext,
      canCompact: plan.canCompact,
      compressCount: plan.compressCount,
      keepCount: plan.keepCount,
      removedMessages: plan.removedMessages,
      keptMessages: plan.keptMessages,
      requestMessages: plan.requestMessages,
    },
    apiCalls,
    dispatchCalls,
    saveCalls,
    finalState: {
      messages: structuredClone(state.messages),
      stats: structuredClone(state.stats),
      lastUsage: state.lastUsage,
    },
    execution: {
      handlersBefore,
      handlersAfter,
      repeatDelta: {
        compact: afterRepeat.compact - beforeRepeat.compact,
        archive: afterRepeat.archive - beforeRepeat.archive,
        save: afterRepeat.save - beforeRepeat.save,
      },
      renderCalls,
      setStreamingCalls,
      toastCalls,
      modalHidden: modal.classList.contains("hidden"),
    },
    persistence: {
      serializedFinal,
      repeatedSerializedFinal: persistence.serializeSessionMessages(
        saveCall.messages,
        {includeModel: true, includeTime: true},
      ),
      savePayload,
    },
    forbiddenFetchCalls,
  }));
})().catch((error) => {
  process.stderr.write(error.stack || String(error));
  process.exitCode = 1;
});
"""


PROJECTION_SCRIPT = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
let forbiddenFetchCalls = 0;
global.fetch = () => {
  forbiddenFetchCalls += 1;
  throw new Error("network access is forbidden in H3-2D2 projection");
};
const NativeDate = Date;
const fixedEpoch = NativeDate.parse(input.fixedInputs.now);
class FixedDate extends NativeDate {
  constructor(...args) {
    super(...(args.length ? args : [fixedEpoch]));
  }
  static now() {
    return fixedEpoch;
  }
}
global.Date = FixedDate;
global.window = {Code: {agent: {}, ui: {}}};
require("./src/agent/model-request.js");
require("./src/agent/compaction.js");
require("./src/ui/messages.js");

const messages = structuredClone(input.messages);
const before = JSON.stringify(messages);
const modelRequest = window.Code.agent.modelRequest;
const compaction = window.Code.agent.compaction;
const contextMessages = compaction.getModelContextMessages(
  messages,
  (message) => Boolean(
    message?.meta?.detachedFromMain
    || message?.meta?.kind === "background-subagent-notify"
  ),
);
const apiMessages = contextMessages
  .map((message) => modelRequest.mapMessageForApi(message))
  .filter(Boolean);

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");
const feature = window.Code.ui.messages.createMessagesFeature({
  escapeHtml,
  renderMarkdown: (value) => `<span>${escapeHtml(value)}</span>`,
  t: (key) => key === "manualCompactedContext"
    ? input.fixedInputs.markerSentinel
    : `I18N_${key}`,
  getMessageText: (message) => {
    const content = message?.content;
    if (Array.isArray(content)) {
      return content.find((part) => part?.type === "text")?.text || "";
    }
    return String(content || "");
  },
  getSelectedModel: () => input.fixedInputs.model,
  getToolActionLabel: (action) => `ACTION_${action}`,
});
const html = feature.projectMessages(messages, {hasActiveRun: false});
const repeatedHtml = feature.projectMessages(messages, {hasActiveRun: false});
process.stdout.write(JSON.stringify({
  contextMessages,
  apiMessages,
  html,
  repeatedHtml,
  sourceUnchanged: before === JSON.stringify(messages),
  forbiddenFetchCalls,
}));
"""


class EvidenceContractError(AssertionError):
    def __init__(self, path, expected=None, actual=None):
        self.path = path
        self.expected = expected
        self.actual = actual
        super().__init__(f"{path}: expected {expected!r}, got {actual!r}")


class VisibleTextParser(HTMLParser):
    VOID_ELEMENTS = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        is_hidden = self.hidden_depth > 0 or any(
            name.lower() == "hidden" for name, _value in attrs
        )
        if is_hidden and tag.lower() not in self.VOID_ELEMENTS:
            self.hidden_depth += 1

    def handle_endtag(self, _tag):
        if self.hidden_depth > 0:
            self.hidden_depth -= 1

    def handle_data(self, data):
        if self.hidden_depth > 0:
            return
        normalized = " ".join(data.split())
        if normalized:
            self.parts.append(normalized)


class ArchiveHandlerAdapter:
    def __init__(self, body):
        self.body = deepcopy(body)
        self.responses = []

    def read_body_json(self):
        return deepcopy(self.body)

    def send_json(self, payload, status=200):
        self.responses.append({"status": status, "payload": deepcopy(payload)})


def canonical_hash(value):
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def text_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def load_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def message_ids(messages):
    return [message.get("meta", {}).get("evidenceMessageId") for message in messages]


def first_difference(actual, expected, path):
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise EvidenceContractError(path, expected, actual)
        for key in expected:
            if key not in actual:
                raise EvidenceContractError(f"{path}.{key}", expected[key], None)
            first_difference(actual[key], expected[key], f"{path}.{key}")
        return
    if isinstance(expected, list):
        if not isinstance(actual, list):
            raise EvidenceContractError(path, expected, actual)
        common = min(len(actual), len(expected))
        for index in range(common):
            first_difference(actual[index], expected[index], f"{path}[{index}]")
        if len(actual) != len(expected):
            raise EvidenceContractError(f"{path}[{common}]", len(expected), len(actual))
        return
    if actual != expected:
        raise EvidenceContractError(path, expected, actual)


def require_match(actual, expected, path):
    first_difference(actual, expected, path)


def validate_profile_source_and_slice(fixture):
    require_match(fixture["evidenceProfile"], EXPECTED_PROFILE, "$.evidenceProfile")
    if fixture["schemaVersion"] != 1:
        raise EvidenceContractError("$.schemaVersion", 1, fixture["schemaVersion"])
    source_slice = fixture["sourceSlice"]
    if source_slice["sha256"] != EXPECTED_SLICE_SHA256:
        raise EvidenceContractError(
            "$.sourceSlice.sha256",
            EXPECTED_SLICE_SHA256,
            source_slice["sha256"],
        )
    messages = fixture["sourceMessages"]
    if len(messages) != len(EXPECTED_SOURCE_MESSAGE_IDS):
        raise EvidenceContractError(
            f"$.sourceMessages[{min(len(messages), len(EXPECTED_SOURCE_MESSAGE_IDS))}]",
            len(EXPECTED_SOURCE_MESSAGE_IDS),
            len(messages),
        )
    actual_ids = message_ids(messages)
    require_match(actual_ids, EXPECTED_SOURCE_MESSAGE_IDS, "$.sourceMessages")
    if len(set(actual_ids)) != len(actual_ids):
        raise EvidenceContractError("$.sourceMessages", "unique evidenceMessageId", actual_ids)
    for index, message in enumerate(messages):
        if "id" in message:
            raise EvidenceContractError(f"$.sourceMessages[{index}].id", None, message["id"])
    source_expected = fixture["expected"]["source"]
    require_match(
        source_expected["messageIds"],
        EXPECTED_SOURCE_MESSAGE_IDS,
        "$.expected.source.messageIds",
    )
    require_match(
        source_expected["visibleSentinels"],
        EXPECTED_VISIBLE_SENTINELS,
        "$.expected.source.visibleSentinels",
    )
    actual_hashes = [canonical_hash(message) for message in messages]
    require_match(
        actual_hashes,
        source_expected["messageCanonicalHashes"],
        "$.expected.source.messageCanonicalHashes",
    )
    if canonical_hash(messages) != source_expected["historyCanonicalHash"]:
        raise EvidenceContractError(
            "$.expected.source.historyCanonicalHash",
            source_expected["historyCanonicalHash"],
            canonical_hash(messages),
        )


def ensure_inside(path, root, contract_path):
    resolved = Path(path).resolve()
    resolved_root = Path(root).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise EvidenceContractError(contract_path, str(resolved_root), str(resolved))
    return resolved


def collect_visible_text(rendered_html):
    parser = VisibleTextParser()
    parser.feed(rendered_html)
    parser.close()
    return "\n".join(parser.parts)


def collect_evidence(fixture):
    validate_profile_source_and_slice(fixture)
    source_messages = deepcopy(fixture["sourceMessages"])
    orchestration = run_node(
        ORCHESTRATION_SCRIPT,
        {
            "sourceSlice": fixture["sourceSlice"],
            "fixedInputs": fixture["fixedInputs"],
            "sourceMessages": source_messages,
        },
    )
    if not orchestration["sourceInputUnchanged"]:
        raise EvidenceContractError("$.expected.source.historyCanonicalHash", "unchanged", "mutated")
    if orchestration["slice"]["sha256"] != EXPECTED_SLICE_SHA256:
        raise EvidenceContractError(
            "$.sourceSlice.sha256",
            EXPECTED_SLICE_SHA256,
            orchestration["slice"]["sha256"],
        )

    compact_calls = [
        call for call in orchestration["apiCalls"]
        if call["path"] == "/api/compact"
    ]
    archive_calls = [
        call for call in orchestration["apiCalls"]
        if call["path"].endswith("/archive")
    ]
    save_calls = orchestration["saveCalls"]
    if len(compact_calls) != 1:
        raise EvidenceContractError("$.expected.execution.compactCalls", 1, len(compact_calls))
    if len(archive_calls) != 1:
        raise EvidenceContractError("$.expected.execution.archiveCalls", 1, len(archive_calls))
    if len(save_calls) != 1:
        raise EvidenceContractError("$.expected.execution.saveCalls", 1, len(save_calls))
    compact_call = compact_calls[0]
    archive_call = archive_calls[0]
    archive_messages = archive_call["body"].get("messages") or []
    if archive_messages != source_messages:
        raise EvidenceContractError(
            "$.expected.archive.payloadMessageHash",
            canonical_hash(source_messages),
            canonical_hash(archive_messages),
        )
    if any(message.get("meta", {}).get("kind") == "manual-context-compaction" for message in archive_messages):
        raise EvidenceContractError("$.expected.archive.payloadMessageHash", "no running marker", "marker found")

    final_messages = orchestration["finalState"]["messages"]
    if final_messages[:len(source_messages)] != source_messages:
        raise EvidenceContractError(
            "$.expected.completed.sourcePrefixHash",
            canonical_hash(source_messages),
            canonical_hash(final_messages[:len(source_messages)]),
        )
    summaries = [
        message for message in final_messages
        if message.get("meta", {}).get("kind") == "compact-summary"
    ]
    markers = [
        message for message in final_messages
        if message.get("meta", {}).get("kind") == "manual-context-compaction"
    ]
    if len(summaries) != 1:
        raise EvidenceContractError("$.expected.completed.summaryCount", 1, len(summaries))
    if len(markers) != 1:
        raise EvidenceContractError("$.expected.completed.markerCount", 1, len(markers))
    if final_messages[-2:] != [summaries[0], markers[0]]:
        raise EvidenceContractError("$.expected.completed.finalMessagesHash", "summary then marker", final_messages[-2:])

    serialized_final = orchestration["persistence"]["serializedFinal"]
    repeated_serialized = orchestration["persistence"]["repeatedSerializedFinal"]
    if serialized_final != repeated_serialized:
        raise EvidenceContractError("$.expected.save.serializedHash", "stable", "changed")
    save_payload = orchestration["persistence"]["savePayload"]
    if save_payload.get("messages") != serialized_final:
        raise EvidenceContractError("$.expected.save.payloadHash", "serialized messages", save_payload)

    fixed = fixture["fixedInputs"]
    real_sessions = (ROOT / "data" / "sessions").resolve()
    with tempfile.TemporaryDirectory(prefix="h3_2d2_manual_compaction_") as temp_name:
        temp_root = Path(temp_name).resolve()
        sessions_root = (temp_root / "sessions").resolve()
        sessions_root.mkdir(parents=True, exist_ok=True)
        if sessions_root == real_sessions or sessions_root.is_relative_to(real_sessions):
            raise EvidenceContractError("$.expected.archive.pathsInsideTemp", temp_root, sessions_root)
        ensure_inside(sessions_root, temp_root, "$.expected.archive.pathsInsideTemp")

        response_adapter = ArchiveHandlerAdapter(archive_call["body"])
        save_path = temp_root / "save" / "final.jsonl"
        side_effect_patchers = (
            mock.patch.object(server_mod, "DATA_DIR", temp_root),
            mock.patch.object(server_mod, "SESSIONS_DIR", sessions_root),
            mock.patch.object(server_mod, "now_iso", return_value=fixed["now"]),
            mock.patch.object(server_mod, "_agent_run_worker"),
            mock.patch.object(server_mod, "_create_model_runtime_run"),
            mock.patch.object(server_mod, "_execute_agent_pending_tools"),
            mock.patch.object(server_mod, "execute_registered_tool"),
            mock.patch.object(server_mod.request, "urlopen"),
            mock.patch.object(server_mod.request, "urlretrieve"),
            mock.patch.object(server_mod.webbrowser, "open"),
            mock.patch.object(server_mod.threading, "Thread"),
        )
        with side_effect_patchers[0] as _data_patch, side_effect_patchers[1] as _sessions_patch, side_effect_patchers[2] as _now_mock, side_effect_patchers[3] as worker_mock, side_effect_patchers[4] as model_mock, side_effect_patchers[5] as pending_tools_mock, side_effect_patchers[6] as tool_mock, side_effect_patchers[7] as urlopen_mock, side_effect_patchers[8] as urlretrieve_mock, side_effect_patchers[9] as browser_mock, side_effect_patchers[10] as thread_mock:
            pre_compaction_jsonl = ensure_inside(
                server_mod.messages_path(fixed["sessionId"]),
                temp_root,
                "$.expected.archive.pathsInsideTemp",
            )
            server_mod.write_jsonl(pre_compaction_jsonl, source_messages)
            server_mod.CodeHandler.archive_session(response_adapter, fixed["sessionId"])
            if len(response_adapter.responses) != 1:
                raise EvidenceContractError("$.expected.archive.responseOk", 1, len(response_adapter.responses))
            response = response_adapter.responses[0]
            archive_json_path = ensure_inside(
                response["payload"].get("path", ""),
                temp_root,
                "$.expected.archive.pathsInsideTemp",
            )
            archive_jsonl_path = ensure_inside(
                archive_json_path.with_suffix(".jsonl"),
                temp_root,
                "$.expected.archive.pathsInsideTemp",
            )
            archive_record = server_mod.read_json(archive_json_path, {})
            copied_jsonl = server_mod.read_jsonl(archive_jsonl_path)
            if archive_record.get("messages") != source_messages:
                raise EvidenceContractError(
                    "$.expected.archive.recordHash",
                    canonical_hash(source_messages),
                    canonical_hash(archive_record.get("messages")),
                )
            if copied_jsonl != source_messages:
                raise EvidenceContractError(
                    "$.expected.archive.copiedJsonlHash",
                    canonical_hash(source_messages),
                    canonical_hash(copied_jsonl),
                )

            save_path.parent.mkdir(parents=True, exist_ok=True)
            server_mod.write_jsonl(save_path, save_payload["messages"])
            round_trip = server_mod.read_jsonl(save_path)
            if round_trip[:len(source_messages)] != serialized_final[:len(source_messages)]:
                raise EvidenceContractError(
                    "$.expected.save.originalPrefixHash",
                    canonical_hash(serialized_final[:len(source_messages)]),
                    canonical_hash(round_trip[:len(source_messages)]),
                )

            temp_files = sorted(
                str(path.relative_to(temp_root)).replace("\\", "/")
                for path in temp_root.rglob("*")
                if path.is_file()
            )
            for path in temp_root.rglob("*"):
                if path.is_file():
                    ensure_inside(path, temp_root, "$.expected.archive.pathsInsideTemp")
            python_side_effects = {
                "browserCalls": browser_mock.call_count,
                "modelCalls": model_mock.call_count,
                "networkCalls": urlopen_mock.call_count + urlretrieve_mock.call_count,
                "threadStarts": thread_mock.call_count,
                "toolCalls": pending_tools_mock.call_count + tool_mock.call_count,
                "workerStarts": worker_mock.call_count,
            }

        projection = run_node(
            PROJECTION_SCRIPT,
            {"messages": round_trip, "fixedInputs": fixed},
        )
        if not projection["sourceUnchanged"]:
            raise EvidenceContractError("$.expected.model.contextHash", "unchanged", "mutated")
        if projection["html"] != projection["repeatedHtml"]:
            raise EvidenceContractError("$.expected.ui.htmlHash", "stable", "changed")
        side_effects = {
            **python_side_effects,
            "networkCalls": (
                python_side_effects["networkCalls"]
                + orchestration["forbiddenFetchCalls"]
                + projection["forbiddenFetchCalls"]
            ),
        }

    visible_text = collect_visible_text(projection["html"])
    sentinel_occurrences = []
    for sentinel in EXPECTED_VISIBLE_SENTINELS:
        start = 0
        while True:
            index = visible_text.find(sentinel, start)
            if index < 0:
                break
            sentinel_occurrences.append((index, sentinel))
            start = index + len(sentinel)
    actual_sentinel_sequence = [
        sentinel for _index, sentinel in sorted(sentinel_occurrences)
    ]
    marker_sentinel = fixed["markerSentinel"]
    summary_sentinel = fixed["summary"]
    marker_count = visible_text.count(marker_sentinel)
    summary_count = visible_text.count(summary_sentinel)

    context_messages = projection["contextMessages"]
    context_source_ids = [
        message.get("meta", {}).get("evidenceMessageId")
        for message in context_messages
        if message.get("meta", {}).get("evidenceMessageId")
    ]
    context_kinds = [
        message.get("meta", {}).get("kind")
        for message in context_messages
    ]
    api_messages = projection["apiMessages"]
    api_payload_text = json.dumps(api_messages, ensure_ascii=False, sort_keys=True)

    plan = orchestration["plan"]
    execution = orchestration["execution"]
    evidence = {
        "counts": {
            "sourceMessages": len(source_messages),
            "visibleSourceSentinels": len(EXPECTED_VISIBLE_SENTINELS),
            "finalMessages": len(final_messages),
            "summaryMessages": len(summaries),
            "markerMessages": len(markers),
        },
        "source": {
            "messageIds": message_ids(source_messages),
            "messageCanonicalHashes": [canonical_hash(message) for message in source_messages],
            "historyCanonicalHash": canonical_hash(source_messages),
            "visibleSentinels": EXPECTED_VISIBLE_SENTINELS,
        },
        "slice": orchestration["slice"],
        "plan": {
            "activeContextMessageIds": message_ids(plan["activeContext"]),
            "canCompact": plan["canCompact"],
            "compressCount": plan["compressCount"],
            "keepCount": plan["keepCount"],
            "removedMessageIds": message_ids(plan["removedMessages"]),
            "keptMessageIds": message_ids(plan["keptMessages"]),
            "requestMessageCount": len(plan["requestMessages"]),
            "requestApiMessageHashes": [canonical_hash(message) for message in plan["requestMessages"]],
            "requestApiPayloadHash": canonical_hash(plan["requestMessages"]),
        },
        "execution": {
            "compactCalls": len(compact_calls),
            "archiveCalls": len(archive_calls),
            "saveCalls": len(save_calls),
            "renderCalls": len(execution["renderCalls"]),
            "setStreamingCalls": len(execution["setStreamingCalls"]),
            "toastCalls": len(execution["toastCalls"]),
            "confirmHandlersBeforeClick": execution["handlersBefore"]["confirm"],
            "cancelHandlersBeforeClick": execution["handlersBefore"]["cancel"],
            "modalHandlersBeforeClick": execution["handlersBefore"]["modal"],
            "confirmHandlersAfterCleanup": execution["handlersAfter"]["confirm"],
            "cancelHandlersAfterCleanup": execution["handlersAfter"]["cancel"],
            "modalHandlersAfterCleanup": execution["handlersAfter"]["modal"],
            "repeatClickAddedCompactCalls": execution["repeatDelta"]["compact"],
            "repeatClickAddedArchiveCalls": execution["repeatDelta"]["archive"],
            "repeatClickAddedSaveCalls": execution["repeatDelta"]["save"],
            "fixedMarkerTime": markers[0]["_time"],
            "savePersistMessages": save_calls[0]["options"].get("persistMessages") is True,
        },
        "dispatch": {
            "requestedModels": orchestration["dispatchCalls"],
            "routeRef": compact_call["headers"].get("X-Model-Route-Ref"),
            "catalogRevision": compact_call["headers"].get("X-Model-Route-Revision"),
            "baseUrl": compact_call["headers"].get("X-Base-URL"),
            "authorizationPresent": "Authorization" in compact_call["headers"],
        },
        "archive": {
            "requestPath": archive_call["path"],
            "requestMethod": archive_call["method"],
            "payloadHash": canonical_hash(archive_call["body"]),
            "payloadMessageHash": canonical_hash(archive_messages),
            "recordHash": canonical_hash(archive_record),
            "copiedJsonlHash": canonical_hash(copied_jsonl),
            "responseOk": response["status"] == 200 and response["payload"].get("ok") is True,
            "pathsInsideTemp": True,
            "relativeFiles": temp_files,
        },
        "completed": {
            "finalMessagesHash": canonical_hash(final_messages),
            "sourcePrefixHash": canonical_hash(final_messages[:len(source_messages)]),
            "summaryHash": canonical_hash(summaries[0]),
            "markerHash": canonical_hash(markers[0]),
            "summaryCount": len(summaries),
            "markerCount": len(markers),
            "markerStatus": markers[0].get("meta", {}).get("status"),
            "markerSkipApi": markers[0].get("meta", {}).get("skipApi") is True,
            "stats": orchestration["finalState"]["stats"],
        },
        "save": {
            "serializedHash": canonical_hash(serialized_final),
            "payloadHash": canonical_hash(save_payload),
            "roundTripHash": canonical_hash(round_trip),
            "roundTripMessageIds": message_ids(round_trip),
            "originalPrefixHash": canonical_hash(round_trip[:len(source_messages)]),
            "relativeFile": "save/final.jsonl",
        },
        "model": {
            "contextLength": len(context_messages),
            "contextSourceMessageIds": context_source_ids,
            "contextKinds": context_kinds,
            "contextHash": canonical_hash(context_messages),
            "apiMessageHashes": [canonical_hash(message) for message in api_messages],
            "apiPayloadHash": canonical_hash(api_messages),
            "evidenceIdsAbsentFromApiPayload": (
                "evidenceMessageId" not in api_payload_text
                and all(source_id not in api_payload_text for source_id in EXPECTED_SOURCE_MESSAGE_IDS)
            ),
        },
        "ui": {
            "htmlHash": text_hash(projection["html"]),
            "visibleTextHash": text_hash(visible_text),
            "visibleSentinels": actual_sentinel_sequence,
            "markerSentinel": marker_sentinel,
            "summarySentinel": summary_sentinel,
            "markerCount": marker_count,
            "summaryCount": summary_count,
        },
        "sideEffects": side_effects,
    }
    evidence["replayHash"] = canonical_hash(evidence)
    return evidence


class TestHarnessManualCompactionVisibleHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.fixture = load_fixture()
        cls.validator = Draft202012Validator(
            cls.schema,
            format_checker=FormatChecker(),
        )

    def test_visible_text_parser_ignores_hidden_subtrees(self):
        rendered_html = (
            '<div>visible before<button type="button" hidden>hidden label'
            "<span>nested hidden label</span></button>"
            '<span>visible after</span><template hidden="">'
            "<p>hidden template content</p></template></div>"
        )
        self.assertEqual(
            collect_visible_text(rendered_html),
            "visible before\nvisible after",
        )

    def test_fixture_schema_profile_source_slice_and_hash(self):
        errors = sorted(
            self.validator.iter_errors(self.fixture),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest(),
            EXPECTED_FIXTURE_SHA256,
        )
        validate_profile_source_and_slice(self.fixture)

    def test_success_chain_matches_frozen_evidence_without_skips(self):
        evidence = collect_evidence(self.fixture)
        require_match(evidence, self.fixture["expected"], "$.expected")

    def test_deterministic_replay_freezes_all_layer_hashes(self):
        first = collect_evidence(self.fixture)
        second = collect_evidence(self.fixture)
        self.assertEqual(first, second)
        self.assertEqual(first["replayHash"], self.fixture["expected"]["replayHash"])

    def test_source_history_and_profile_mutations_freeze_paths(self):
        mutations = []

        profile = deepcopy(self.fixture)
        profile["evidenceProfile"]["version"] = 2
        mutations.append((profile, "$.evidenceProfile.version"))

        slice_hash = deepcopy(self.fixture)
        slice_hash["sourceSlice"]["sha256"] = "f" * 64
        mutations.append((slice_hash, "$.sourceSlice.sha256"))

        missing = deepcopy(self.fixture)
        missing["sourceMessages"].pop()
        mutations.append((missing, "$.sourceMessages[12]"))

        reordered = deepcopy(self.fixture)
        reordered["sourceMessages"][0], reordered["sourceMessages"][1] = (
            reordered["sourceMessages"][1],
            reordered["sourceMessages"][0],
        )
        mutations.append((reordered, "$.sourceMessages[0]"))

        for mutated, expected_path in mutations:
            with self.subTest(path=expected_path):
                with self.assertRaises(EvidenceContractError) as caught:
                    validate_profile_source_and_slice(mutated)
                self.assertEqual(caught.exception.path, expected_path)

    def test_plan_prefix_summary_marker_archive_save_and_model_mutations_freeze_paths(self):
        evidence = collect_evidence(self.fixture)
        mutations = [
            ("plan", "removedMessageIds", 0, "wrong-plan-id"),
            ("completed", "sourcePrefixHash", None, "f" * 64),
            ("completed", "summaryCount", None, 2),
            ("completed", "markerStatus", None, "running"),
            ("archive", "payloadHash", None, "f" * 64),
            ("save", "roundTripHash", None, "f" * 64),
            ("model", "contextSourceMessageIds", 0, "msg-user-0"),
        ]
        for section, field, index, value in mutations:
            actual = deepcopy(evidence)
            if index is None:
                actual[section][field] = value
                expected_path = f"$.expected.{section}.{field}"
            else:
                if field == "contextSourceMessageIds":
                    actual[section][field].append(value)
                else:
                    actual[section][field][index] = value
                expected_path = f"$.expected.{section}.{field}[{index}]"
            with self.subTest(path=expected_path):
                with self.assertRaises(EvidenceContractError) as caught:
                    require_match(actual, self.fixture["expected"], "$.expected")
                self.assertEqual(caught.exception.path, expected_path)

    def test_ui_and_one_shot_mutations_freeze_paths(self):
        evidence = collect_evidence(self.fixture)
        mutations = []

        missing = deepcopy(evidence)
        missing["ui"]["visibleSentinels"].pop(3)
        mutations.append((missing, "$.expected.ui.visibleSentinels[3]"))

        duplicate = deepcopy(evidence)
        duplicate["ui"]["visibleSentinels"].insert(3, duplicate["ui"]["visibleSentinels"][3])
        mutations.append((duplicate, "$.expected.ui.visibleSentinels[4]"))

        reordered = deepcopy(evidence)
        reordered["ui"]["visibleSentinels"][0], reordered["ui"]["visibleSentinels"][1] = (
            reordered["ui"]["visibleSentinels"][1],
            reordered["ui"]["visibleSentinels"][0],
        )
        mutations.append((reordered, "$.expected.ui.visibleSentinels[0]"))

        repeat = deepcopy(evidence)
        repeat["execution"]["repeatClickAddedSaveCalls"] = 1
        mutations.append((repeat, "$.expected.execution.repeatClickAddedSaveCalls"))

        for actual, expected_path in mutations:
            with self.subTest(path=expected_path):
                with self.assertRaises(EvidenceContractError) as caught:
                    require_match(actual, self.fixture["expected"], "$.expected")
                self.assertEqual(caught.exception.path, expected_path)

    def test_schema_rejects_profile_drift_missing_extra_and_top_level_message_id(self):
        mutations = []

        profile = deepcopy(self.fixture)
        profile["evidenceProfile"]["scope"] = "public-module-import"
        mutations.append((profile, ("evidenceProfile", "scope")))

        missing = deepcopy(self.fixture)
        missing["sourceMessages"].pop()
        mutations.append((missing, ("sourceMessages",)))

        extra = deepcopy(self.fixture)
        extra["unexpected"] = True
        mutations.append((extra, ()))

        top_level_id = deepcopy(self.fixture)
        top_level_id["sourceMessages"][0]["id"] = "forbidden-top-level-id"
        mutations.append((top_level_id, ("sourceMessages", 0)))

        for mutated, expected_path in mutations:
            with self.subTest(path=expected_path):
                paths = {
                    tuple(error.absolute_path)
                    for error in self.validator.iter_errors(mutated)
                }
                self.assertIn(expected_path, paths)


if __name__ == "__main__":
    unittest.main()
