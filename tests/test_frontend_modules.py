"""Regression guards for the transitional frontend module split."""

import json
import os
import posixpath
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
APP_SOURCE = (ROOT / "app.js").read_text(encoding="utf-8")
SERVER_SOURCE = (ROOT / "server.py").read_text(encoding="utf-8")
RUNTIME_SOURCE = (ROOT / "agent-runtime.js").read_text(encoding="utf-8")
STATE_SOURCE = (ROOT / "src" / "core" / "state.js").read_text(encoding="utf-8")
I18N_SOURCE = (ROOT / "src" / "core" / "i18n.js").read_text(encoding="utf-8")
PLATFORM_SOURCE = (ROOT / "src" / "core" / "platform.js").read_text(encoding="utf-8")
API_CLIENT_SOURCE = (ROOT / "src" / "services" / "api-client.js").read_text(encoding="utf-8")
PERSISTENCE_SOURCE = (ROOT / "src" / "services" / "persistence.js").read_text(encoding="utf-8")
SESSIONS_SOURCE = (ROOT / "src" / "features" / "sessions.js").read_text(encoding="utf-8")
SETTINGS_SOURCE = (ROOT / "src" / "features" / "settings.js").read_text(encoding="utf-8")
ONBOARDING_TASKS_SOURCE = (ROOT / "src" / "features" / "onboarding-tasks.js").read_text(encoding="utf-8")
DIFF_SOURCE = (ROOT / "src" / "ui" / "diff.js").read_text(encoding="utf-8")
MARKDOWN_SOURCE = (ROOT / "src" / "ui" / "markdown.js").read_text(encoding="utf-8")
MESSAGES_SOURCE = (ROOT / "src" / "ui" / "messages.js").read_text(encoding="utf-8")
TIMELINE_SOURCE = (ROOT / "src" / "ui" / "timeline.js").read_text(encoding="utf-8")
PANELS_SOURCE = (ROOT / "src" / "ui" / "panels.js").read_text(encoding="utf-8")
PREVIEW_SOURCE = (ROOT / "src" / "features" / "preview.js").read_text(encoding="utf-8")
FILES_SOURCE = (ROOT / "src" / "features" / "files.js").read_text(encoding="utf-8")
IMAGE_ATTACHMENTS_SOURCE = (ROOT / "src" / "features" / "image-attachments.js").read_text(encoding="utf-8")
SKILLS_MEMORY_SOURCE = (ROOT / "src" / "features" / "skills-memory.js").read_text(encoding="utf-8")
GOAL_SOURCE = (ROOT / "src" / "features" / "goal.js").read_text(encoding="utf-8")
SESSION_IMPORT_SOURCE = (ROOT / "src" / "features" / "session-import.js").read_text(encoding="utf-8")
BRANCHES_SOURCE = (ROOT / "src" / "features" / "branches.js").read_text(encoding="utf-8")
MODEL_REQUEST_SOURCE = (ROOT / "src" / "agent" / "model-request.js").read_text(encoding="utf-8")
SYSTEM_PROMPT_SOURCE = (ROOT / "src" / "agent" / "system-prompt.js").read_text(encoding="utf-8")
TOOLS_SOURCE = (ROOT / "src" / "agent" / "tools.js").read_text(encoding="utf-8")
PERMISSIONS_SOURCE = (ROOT / "src" / "agent" / "permissions.js").read_text(encoding="utf-8")
QUESTIONNAIRE_SOURCE = (ROOT / "src" / "agent" / "questionnaire.js").read_text(encoding="utf-8")
SUBAGENTS_SOURCE = (ROOT / "src" / "agent" / "subagents.js").read_text(encoding="utf-8")
COMPACTION_SOURCE = (ROOT / "src" / "agent" / "compaction.js").read_text(encoding="utf-8")
MODEL_STREAM_SOURCE = (ROOT / "src" / "agent" / "model-stream.js").read_text(encoding="utf-8")
SHADOW_SOURCE = (ROOT / "src" / "agent" / "run-projection-shadow.js").read_text(encoding="utf-8")
INDEX_SOURCE = (ROOT / "index.html").read_text(encoding="utf-8")
BUILD_SOURCE = (ROOT / "build_exe.py").read_text(encoding="utf-8")
FRONTEND_ENTRY_SOURCE = (ROOT / "src" / "frontend-entry.js").read_text(encoding="utf-8")
FRONTEND_BUILD_SOURCE = (ROOT / "scripts" / "build-frontend.mjs").read_text(encoding="utf-8")
H4_SMOKE_SOURCE = (ROOT / "tests" / "e2e" / "h4" / "smoke.spec.cjs").read_text(encoding="utf-8")
PACKAGE_JSON = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
CURRENT_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
CURRENT_SPEC_SOURCE = (ROOT / f"Code-v{CURRENT_VERSION}.spec").read_text(encoding="utf-8")
STYLE_SOURCE = (ROOT / "styles.css").read_text(encoding="utf-8")
LOGO_SOURCE = (ROOT / "assets" / "code-logo.svg").read_text(encoding="utf-8")
LOGO_EXPORT_SOURCE = (ROOT / "design" / "logo-concepts" / "export_selected_logo.py").read_text(encoding="utf-8")


class TestFrontendCoreModules(unittest.TestCase):
    def test_same_parent_detached_result_keeps_main_result_in_its_original_slot(self):
        ordering_start = APP_SOURCE.index(
            "function placeMainResultByCompletionOrder(messages, mainMessage, taskStartedAt)"
        )
        ordering_end = APP_SOURCE.index("function stopLiveTimer()", ordering_start)
        ordering_source = APP_SOURCE[ordering_start:ordering_end]
        script = f"""
eval({json.dumps(ordering_source)});
const main = {{role: "assistant", content: "main-final", meta: {{}}}};
const detachedUser = {{
  role: "user",
  content: "parallel-user",
  meta: {{
    detachedFromMain: true,
    backgroundDispatch: {{id: "job-1", parentTaskStartedAt: 500}},
  }},
}};
const detachedResult = {{
  role: "assistant",
  content: "parallel-error",
  meta: {{
    kind: "background-subagent",
    jobId: "job-1",
    detachedFromMain: true,
    parentTaskStartedAt: 500,
  }},
}};
const detachedMessages = [main, detachedUser, detachedResult];
const detachedChanged = placeMainResultByCompletionOrder(detachedMessages, main, 500);

const orphanMain = {{role: "assistant", content: "orphan-main", meta: {{}}}};
const orphanDetached = {{
  role: "assistant",
  content: "orphan-detached",
  meta: {{
    kind: "background-subagent",
    jobId: "orphan-job",
    detachedFromMain: true,
    parentTaskStartedAt: 500,
  }},
}};
const orphanMessages = [orphanMain, orphanDetached];
const orphanChanged = placeMainResultByCompletionOrder(orphanMessages, orphanMain, 500);

const legacyMain = {{role: "assistant", content: "legacy-main", meta: {{}}}};
const legacyBackground = {{
  role: "assistant",
  content: "legacy-background",
  meta: {{kind: "background-subagent", parentTaskStartedAt: 500}},
}};
const legacyMessages = [legacyMain, legacyBackground];
const legacyChanged = placeMainResultByCompletionOrder(legacyMessages, legacyMain, 500);

const queueMain = {{role: "assistant", content: "queue-main", meta: {{}}}};
const queuedUser = {{role: "user", content: "queued", meta: {{queuedDispatch: {{id: "q-1"}}}}}};
const queueMessages = [queueMain, queuedUser];
const queueChanged = placeMainResultByCompletionOrder(queueMessages, queueMain, 500);

process.stdout.write(JSON.stringify({{
  detachedChanged,
  detachedOrder: detachedMessages.map((message) => message.content),
  detachedIdentityStable: detachedMessages[0] === main
    && detachedMessages[1] === detachedUser
    && detachedMessages[2] === detachedResult,
  orphanChanged,
  orphanOrder: orphanMessages.map((message) => message.content),
  legacyChanged,
  legacyOrder: legacyMessages.map((message) => message.content),
  queueChanged,
  queueOrder: queueMessages.map((message) => message.content),
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(json.loads(completed.stdout), {
            "detachedChanged": False,
            "detachedOrder": ["main-final", "parallel-user", "parallel-error"],
            "detachedIdentityStable": True,
            "orphanChanged": False,
            "orphanOrder": ["orphan-main", "orphan-detached"],
            "legacyChanged": True,
            "legacyOrder": ["legacy-background", "legacy-main"],
            "queueChanged": False,
            "queueOrder": ["queue-main", "queued"],
        })

    def test_send_preconditions_are_localized_and_check_model_before_key(self):
        queue_start = APP_SOURCE.index("async function enqueueSessionMessage(")
        queue_end = APP_SOURCE.index("async function cancelQueuedSessionMessage(", queue_start)
        queue_source = APP_SOURCE[queue_start:queue_end]
        send_start = APP_SOURCE.index("async function sendMessage(")
        send_end = APP_SOURCE.index("function getSelectedModel()", send_start)
        send_source = APP_SOURCE[send_start:send_end]
        script = f"""
let selectedModel = "";
let selectedKey = "";
const keyLookups = [];
const translations = {{
  createSessionFirst: "create-session-first",
  selectModelFirst: "select-model-first",
  configureKeyFirst: "configure-key-first",
}};
function t(key) {{ return translations[key] || key; }}
function getSelectedModel() {{ return selectedModel; }}
function getBestKey(model) {{ keyLookups.push(model); return selectedKey; }}
eval({json.dumps(queue_source)});
eval({json.dumps(send_source)});
async function errorMessage(callback) {{
  try {{ await callback(); return ""; }}
  catch (error) {{ return error.message; }}
}}
(async () => {{
  const queueNoModel = await errorMessage(() => enqueueSessionMessage("session-1", "queued"));
  const sendNoModel = await errorMessage(() => sendMessage("sent"));
  const lookupsBeforeModel = keyLookups.length;
  selectedModel = "gpt-test";
  const queueNoKey = await errorMessage(() => enqueueSessionMessage("session-1", "queued"));
  const sendNoKey = await errorMessage(() => sendMessage("sent"));
  process.stdout.write(JSON.stringify({{
    queueNoModel,
    sendNoModel,
    queueNoKey,
    sendNoKey,
    lookupsBeforeModel,
    keyLookups,
  }}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(json.loads(completed.stdout), {
            "queueNoModel": "select-model-first",
            "sendNoModel": "select-model-first",
            "queueNoKey": "configure-key-first",
            "sendNoKey": "configure-key-first",
            "lookupsBeforeModel": 0,
            "keyLookups": ["gpt-test", "gpt-test"],
        })
        self.assertIn('selectModelFirst: "请先刷新并选择模型"', I18N_SOURCE)
        self.assertIn('selectModelFirst: "Refresh and select a model first"', I18N_SOURCE)
        self.assertIn('configureKeyFirst: "请先在“模型”设置中添加 API Key"', I18N_SOURCE)
        self.assertIn('configureKeyFirst: "Add an API Key in Models first"', I18N_SOURCE)
        self.assertNotIn("Please enter a New API sub key in Models first.", APP_SOURCE)
        self.assertNotIn("Please refresh and select a model first.", APP_SOURCE)

    def test_active_model_runtime_recovery_uses_snapshot_authority_and_one_owner(self):
        ownership_start = APP_SOURCE.index("const activeAgentRuntimeProjectionOwners")
        ownership_end = APP_SOURCE.index("function rebindRecoveredRuntimeAssistant", ownership_start)
        ownership_source = APP_SOURCE[ownership_start:ownership_end]
        project_start = APP_SOURCE.index("async function projectAgentModelStarted")
        recovery_start = APP_SOURCE.index("async function recoverActiveAgentRuntimeProjection")
        project_source = APP_SOURCE[project_start:recovery_start]
        recovery_end = APP_SOURCE.index("function projectAgentModelCompleted", recovery_start)
        recovery_source = APP_SOURCE[recovery_start:recovery_end]
        script = f"""
{ownership_source}
const attachmentCalls = [];
async function attachAgentRuntimeProjection(ctx, event, options) {{
  attachmentCalls.push({{
    agentRunId: ctx.agentRunId,
    runtimeRunId: event?.data?.runtimeRunId || "",
    recovered: options?.recovered === true,
  }});
}}
function findAgentAssistantByRuntime(ctx, runtimeRunId) {{
  return (ctx.messages || []).find((message) => message?.meta?.agentRuntimeRunId === runtimeRunId);
}}
function agentEventMeta(ctx, event, type) {{
  return {{agentRunId: ctx.agentRunId, agentEventType: type, agentEventSeq: event.seq}};
}}
{project_source}
{recovery_source}
(async () => {{
  let releaseShared;
  let sharedConsumerCalls = 0;
  const sharedGate = new Promise((resolve) => {{ releaseShared = resolve; }});
  const ownerCtx = {{agentRunId: "agent-owner", sessionId: "session-owner"}};
  const first = consumeAgentRuntimeProjection(ownerCtx, "runtime-shared", async () => {{
    sharedConsumerCalls += 1;
    await sharedGate;
    return "shared-result";
  }});
  const second = consumeAgentRuntimeProjection(ownerCtx, "runtime-shared", async () => {{
    sharedConsumerCalls += 1;
    return "duplicate-result";
  }});
  await Promise.resolve();
  releaseShared();
  const sharedResults = await Promise.all([first, second]);
  const settledResult = await consumeAgentRuntimeProjection(ownerCtx, "runtime-shared", async () => {{
    sharedConsumerCalls += 1;
    return "late-duplicate-result";
  }});

  const missingCtx = {{
    agentRunId: "agent-missing",
    sessionId: "session-missing",
    agentEventCursor: 4,
    runtimeRunId: "persisted-clue",
    run: {{runtimeRunId: "persisted-clue"}},
  }};
  const missing = await recoverActiveAgentRuntimeProjection(missingCtx, {{
    activeRuntimeRunId: "",
    events: [],
  }});

  const pendingCtx = {{
    agentRunId: "agent-pending",
    sessionId: "session-pending",
    agentEventCursor: 4,
    runtimeRunId: "stale-runtime",
    run: {{runtimeRunId: "stale-runtime"}},
    messages: [],
  }};
  const pending = await recoverActiveAgentRuntimeProjection(pendingCtx, {{
    activeRuntimeRunId: "runtime-authoritative-pending",
    events: [{{seq: 5, type: "model_started", data: {{runtimeRunId: "runtime-authoritative-pending"}}}}],
  }});

  const recoveredCtx = {{
    agentRunId: "agent-recovered",
    sessionId: "session-recovered",
    agentEventCursor: 9,
    runtimeRunId: "stale-runtime",
    run: {{runtimeRunId: "stale-runtime"}},
    messages: [],
  }};
  const recovered = await recoverActiveAgentRuntimeProjection(recoveredCtx, {{
    activeRuntimeRunId: "runtime-authoritative",
    events: [],
  }});
  const recoveredAssistant = {{
    role: "assistant",
    streaming: true,
    meta: {{agentRunId: "agent-recovered", agentRuntimeRunId: "runtime-authoritative"}},
  }};
  recoveredCtx.messages.push(recoveredAssistant);
  await projectAgentModelStarted(recoveredCtx, {{
    seq: 10,
    type: "model_started",
    data: {{runtimeRunId: "runtime-authoritative", round: 3}},
  }});

  process.stdout.write(JSON.stringify({{
    samePromise: first === second,
    sharedConsumerCalls,
    sharedResults,
    settledResult,
    missing,
    missingRuntimeRunId: missingCtx.runtimeRunId,
    missingRunRuntimeRunId: missingCtx.run.runtimeRunId,
    pending,
    pendingRuntimeRunId: pendingCtx.runtimeRunId,
    pendingRunRuntimeRunId: pendingCtx.run.runtimeRunId,
    recovered,
    recoveredRuntimeRunId: recoveredCtx.runtimeRunId,
    recoveredRunRuntimeRunId: recoveredCtx.run.runtimeRunId,
    recoveredModelRound: recoveredCtx.run.modelRound,
    recoveredAssistantMeta: recoveredAssistant.meta,
    attachmentCalls,
  }}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["samePromise"])
        self.assertEqual(data["sharedConsumerCalls"], 1)
        self.assertEqual(data["sharedResults"], ["shared-result", "shared-result"])
        self.assertEqual(data["settledResult"], "shared-result")
        self.assertEqual(data["missing"]["status"], "no-active-runtime")
        self.assertEqual(data["missingRuntimeRunId"], "persisted-clue")
        self.assertEqual(data["missingRunRuntimeRunId"], "persisted-clue")
        self.assertEqual(data["pending"]["status"], "pending-model-start")
        self.assertEqual(data["pendingRuntimeRunId"], "runtime-authoritative-pending")
        self.assertEqual(data["pendingRunRuntimeRunId"], "runtime-authoritative-pending")
        self.assertEqual(data["recovered"]["status"], "reattached")
        self.assertEqual(data["recoveredRuntimeRunId"], "runtime-authoritative")
        self.assertEqual(data["recoveredRunRuntimeRunId"], "runtime-authoritative")
        self.assertEqual(data["recoveredModelRound"], 3)
        self.assertEqual(data["recoveredAssistantMeta"]["agentEventType"], "model_started")
        self.assertEqual(data["recoveredAssistantMeta"]["agentEventSeq"], 10)
        self.assertEqual(data["attachmentCalls"], [{
            "agentRunId": "agent-recovered",
            "runtimeRunId": "runtime-authoritative",
            "recovered": True,
        }])

        loop_start = APP_SOURCE.index("async function runServerAgentLoop")
        loop_end = APP_SOURCE.index("async function executeRunContext", loop_start)
        loop_source = APP_SOURCE[loop_start:loop_end]
        get_index = loop_source.index("let snapshot = await agentRuntime.getAgentRun")
        recover_index = loop_source.index("await recoverActiveAgentRuntimeProjection(ctx, snapshot)")
        watch_index = loop_source.index("snapshot = await agentRuntime.watchAgentRun")
        self.assertLess(get_index, recover_index)
        self.assertLess(recover_index, watch_index)
        attachment_start = APP_SOURCE.index("async function attachAgentRuntimeProjection")
        attachment_end = APP_SOURCE.index("async function projectAgentModelStarted", attachment_start)
        attachment_source = APP_SOURCE[attachment_start:attachment_end]
        self.assertNotIn('ctx.runtimeRunId = ""', attachment_source)
        self.assertNotIn('ctx.run.runtimeRunId = ""', attachment_source)
        self.assertNotIn("createRun(", attachment_source)
        self.assertIn("const streamPromise = _callModelOnceAttempt", attachment_source)

    def test_runtime_assistant_is_revived_only_for_authoritative_active_owner(self):
        internal_start = APP_SOURCE.index("function internalCompactionRuntimeIds")
        internal_end = APP_SOURCE.index("function releaseAttachedImagePreview", internal_start)
        internal_source = APP_SOURCE[internal_start:internal_end]
        attachment_start = APP_SOURCE.index("function rebindRecoveredRuntimeAssistant")
        attachment_end = APP_SOURCE.index("async function projectAgentModelStarted", attachment_start)
        attachment_source = APP_SOURCE[attachment_start:attachment_end]
        script = f"""
const state = {{sessionId: "session-active"}};
const streamCalls = [];
function findAgentAssistantByRuntime(ctx, runtimeRunId) {{
  return ctx.messages.find((message) => (
    message?.role === "assistant"
    && message?.meta?.agentRunId === ctx.agentRunId
    && message?.meta?.agentRuntimeRunId === runtimeRunId
  ));
}}
function agentEventMeta(ctx, event, type) {{
  return {{agentRunId: ctx.agentRunId, agentEventType: type, agentEventSeq: Number(event?.seq || 0)}};
}}
function getSelectedModel() {{ return "model-fallback"; }}
function setSessionMessages() {{}}
function renderSessionMessages() {{}}
function syncActiveRunBanner() {{}}
function persistRunCheckpoint() {{ return Promise.resolve(); }}
async function _callModelOnceAttempt(index, nativeTools, ctx) {{
  streamCalls.push({{index, nativeTools, agentRunId: ctx.agentRunId, runtimeRunId: ctx.runtimeRunId}});
}}
{internal_source}
{attachment_source}
function makeContext(activeRuntimeRunId) {{
  const assistant = {{
    role: "assistant",
    content: "persisted partial",
    streaming: false,
    meta: {{agentRunId: "agent-1", agentRuntimeRunId: "runtime-1"}},
  }};
  return {{
    assistant,
    ctx: {{
      agentRunId: "agent-1",
      sessionId: "session-active",
      runtimeRunId: "runtime-1",
      _activeRuntimeRunId: activeRuntimeRunId,
      model: "model-1",
      messages: [assistant],
      run: {{runtimeRunId: "runtime-1"}},
    }},
  }};
}}
(async () => {{
  const active = makeContext("runtime-1");
  await attachAgentRuntimeProjection(active.ctx, {{data: {{runtimeRunId: "runtime-1"}}}}, {{recovered: true}});
  const nonActive = makeContext("runtime-other");
  await attachAgentRuntimeProjection(nonActive.ctx, {{data: {{runtimeRunId: "runtime-1"}}}}, {{recovered: true}});
  const terminal = makeContext("");
  await attachAgentRuntimeProjection(terminal.ctx, {{data: {{runtimeRunId: "runtime-1"}}}}, {{recovered: true}});
  const ordinaryReplay = makeContext("runtime-1");
  await attachAgentRuntimeProjection(ordinaryReplay.ctx, {{data: {{runtimeRunId: "runtime-1"}}}});
  process.stdout.write(JSON.stringify({{
    active: {{
      streaming: active.assistant.streaming,
      projection: active.assistant._streamProjection,
      count: active.ctx.messages.length,
    }},
    nonActive: {{streaming: nonActive.assistant.streaming, count: nonActive.ctx.messages.length}},
    terminal: {{streaming: terminal.assistant.streaming, count: terminal.ctx.messages.length}},
    ordinaryReplay: {{streaming: ordinaryReplay.assistant.streaming, count: ordinaryReplay.ctx.messages.length}},
    streamCalls,
  }}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["active"], {
            "streaming": True,
            "projection": "answer",
            "count": 1,
        })
        self.assertEqual(data["nonActive"], {"streaming": False, "count": 1})
        self.assertEqual(data["terminal"], {"streaming": False, "count": 1})
        self.assertEqual(data["ordinaryReplay"], {"streaming": False, "count": 1})
        self.assertEqual(data["streamCalls"], [{
            "index": 0,
            "nativeTools": True,
            "agentRunId": "agent-1",
            "runtimeRunId": "runtime-1",
        }])

    def test_first_model_delta_persists_one_metadata_only_checkpoint(self):
        helper_start = APP_SOURCE.index("function markModelResponseStarted")
        helper_end = APP_SOURCE.index("function getRecoveryCountdownSeconds", helper_start)
        helper_source = APP_SOURCE[helper_start:helper_end]
        script = f"""
const state = {{sessionId: "other-session"}};
const checkpoints = [];
const saves = [];
function syncActiveRunBanner() {{}}
function makeRunCheckpoint(ctx, status, phase, extra) {{
  return {{status, phase, ...extra, fromRun: ctx.run.hasFirstModelResponseStarted}};
}}
function setSessionRunState(sessionId, checkpoint) {{
  checkpoints.push({{sessionId, checkpoint}});
}}
async function saveSessionState(sessionId, messages, stats, title, options) {{
  saves.push({{sessionId, messages, stats, title, options}});
}}
{helper_source}
(async () => {{
  const messages = [{{role: "assistant", content: "partial", streaming: true}}];
  const run = {{
    hasFirstModelResponseStarted: false,
    modelResponseStarted: false,
    modelWaitStartedAt: 123,
    modelRecovery: {{attempt: 1}},
    runtimeRunId: "runtime-authoritative",
  }};
  const ctx = {{
    sessionId: "session-1",
    runtimeRunId: "runtime-authoritative",
    messages,
    stats: {{input: 1}},
    run,
  }};
  recordModelResponseStarted(ctx, run, "session-1");
  recordModelResponseStarted(ctx, run, "session-1");
  await Promise.resolve();
  process.stdout.write(JSON.stringify({{
    run,
    checkpointCount: checkpoints.length,
    checkpoints,
    saveCount: saves.length,
    persistMessages: saves[0]?.options?.persistMessages,
    sameMessages: saves[0]?.messages === messages,
  }}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["run"]["hasFirstModelResponseStarted"])
        self.assertTrue(data["run"]["modelResponseStarted"])
        self.assertIsNone(data["run"]["modelWaitStartedAt"])
        self.assertIsNone(data["run"]["modelRecovery"])
        self.assertEqual(data["checkpointCount"], 1)
        self.assertEqual(data["saveCount"], 1)
        self.assertFalse(data["persistMessages"])
        self.assertTrue(data["sameMessages"])
        checkpoint = data["checkpoints"][0]["checkpoint"]
        self.assertTrue(checkpoint["hasFirstModelResponseStarted"])
        self.assertTrue(checkpoint["fromRun"])
        self.assertEqual(checkpoint["runtimeRunId"], "runtime-authoritative")

    def test_existing_runtime_404_never_creates_a_replacement_run(self):
        script = f"""
global.window = {{Code: {{agent: {{}}}}}};
const source = {json.dumps(RUNTIME_SOURCE)};
const calls = [];
global.fetch = async (url, options = {{}}) => {{
  calls.push({{url: String(url), method: String(options.method || "GET")}});
  return new Response(JSON.stringify({{error: "runtime missing"}}), {{
    status: 404,
    headers: {{"Content-Type": "application/json"}},
  }});
}};
eval(source);
(async () => {{
  let errorStatus = 0;
  let errorMessage = "";
  try {{
    const response = await window.Code.agent.runtime.openSseResponse({{
      runId: "runtime-expired",
      sessionId: "session-1",
      payload: {{model: "should-not-be-used"}},
      keys: ["should-not-be-used"],
    }});
    await response.body.getReader().read();
  }} catch (error) {{
    errorStatus = Number(error?.status || 0);
    errorMessage = error?.message || String(error);
  }}
  process.stdout.write(JSON.stringify({{calls, errorStatus, errorMessage}}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["errorStatus"], 404)
        self.assertEqual(data["calls"], [{
            "url": "/api/runtime/runs/runtime-expired?cursor=0&wait=0",
            "method": "GET",
        }])
        self.assertNotEqual(data["calls"][0]["url"], "/api/runtime/runs")

    def test_existing_runtime_replay_restores_body_across_repeated_attachments(self):
        script = f"""
global.window = {{Code: {{agent: {{}}}}}};
const source = {json.dumps(RUNTIME_SOURCE)};
const calls = [];
let requestCount = 0;
const catchUpResult = {{
  reasoning: "思考一。",
  content: "第一段。\\n\\n第二段。\\n\\n",
  toolCalls: [{{
    index: 0,
    id: "call-1",
    type: "function",
    function: {{name: "read_file", arguments: "{{\\\"path\\\":\\\"VERSION\\\"}}"}},
  }}],
  usage: {{}},
}};
const frames = [
  {{seq: 5, data: JSON.stringify({{choices: [{{delta: {{content: "第三段。"}}, finish_reason: "stop"}}]}})}},
  {{seq: 6, data: "[DONE]"}},
];
global.fetch = async (url, options = {{}}) => {{
  calls.push({{url: String(url), method: String(options.method || "GET")}});
  requestCount += 1;
  if (requestCount % 2 === 1) {{
    return new Response(JSON.stringify({{
      status: "running",
      events: [
        {{seq: 1, data: "ignored-history-1"}},
        {{seq: 2, data: "ignored-history-2"}},
        {{seq: 3, data: "ignored-history-3"}},
        {{seq: 4, data: "ignored-history-4"}},
      ],
      nextCursor: 4,
      result: catchUpResult,
    }}), {{status: 200, headers: {{"Content-Type": "application/json"}}}});
  }}
  return new Response(JSON.stringify({{
    status: "completed",
    events: frames,
    nextCursor: 6,
    result: {{...catchUpResult, content: `${{catchUpResult.content}}第三段。`}},
  }}), {{status: 200, headers: {{"Content-Type": "application/json"}}}});
}};
eval(source);
async function attach() {{
  const response = await window.Code.agent.runtime.openSseResponse({{
    runId: "runtime-replay",
    sessionId: "session-1",
  }});
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let raw = "";
  while (true) {{
    const packet = await reader.read();
    if (packet.done) break;
    raw += decoder.decode(packet.value);
  }}
  const payloads = raw.split(/\\r?\\n/)
    .filter((line) => line.startsWith("data: "))
    .map((line) => line.slice(6));
  const jsonFrames = payloads.filter((item) => item !== "[DONE]").map(JSON.parse);
  return {{
    content: jsonFrames.map((frame) => frame.choices?.[0]?.delta?.content || "").join(""),
    reasoning: jsonFrames.map((frame) => frame.choices?.[0]?.delta?.reasoning_content || "").join(""),
    toolNames: jsonFrames.flatMap((frame) => frame.choices?.[0]?.delta?.tool_calls || [])
      .map((call) => call.function?.name || ""),
    doneCount: payloads.filter((item) => item === "[DONE]").length,
  }};
}}
(async () => {{
  const first = await attach();
  const second = await attach();
  process.stdout.write(JSON.stringify({{first, second, calls}}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        expected = {
            "content": "第一段。\n\n第二段。\n\n第三段。",
            "reasoning": "思考一。",
            "toolNames": ["read_file"],
            "doneCount": 1,
        }
        self.assertEqual(data["first"], expected)
        self.assertEqual(data["second"], expected)
        self.assertEqual(len(data["calls"]), 4)
        self.assertEqual(data["calls"], [
            {
                "url": "/api/runtime/runs/runtime-replay?cursor=0&wait=0",
                "method": "GET",
            },
            {
                "url": "/api/runtime/runs/runtime-replay?cursor=4&wait=25",
                "method": "GET",
            },
        ] * 2)

    def test_existing_runtime_terminal_snapshots_converge_without_create(self):
        script = f"""
global.window = {{Code: {{agent: {{}}}}}};
const source = {json.dumps(RUNTIME_SOURCE)};
const calls = [];
const snapshots = {{
  completed: {{
    status: "completed",
    events: [{{seq: 1, data: "ignored-history"}}],
    nextCursor: 1,
    result: {{content: "complete-body", reasoning: "", toolCalls: [], usage: {{}}}},
  }},
  failed: {{
    status: "failed",
    events: [{{seq: 1, data: "ignored-history"}}],
    nextCursor: 1,
    result: {{content: "failed-partial", reasoning: "", toolCalls: [], usage: {{}}}},
    errorCode: "upstream_error",
    error: "bounded failure",
    transient: true,
  }},
  cancelled: {{
    status: "cancelled",
    events: [{{seq: 1, data: "ignored-history"}}],
    nextCursor: 1,
    result: {{content: "cancelled-partial", reasoning: "", toolCalls: [], usage: {{}}}},
    errorCode: "runtime_cancelled",
    transient: false,
  }},
}};
global.fetch = async (url, options = {{}}) => {{
  calls.push({{url: String(url), method: String(options.method || "GET")}});
  const runId = String(url).split("/").pop().split("?")[0];
  return new Response(JSON.stringify(snapshots[runId]), {{
    status: 200,
    headers: {{"Content-Type": "application/json"}},
  }});
}};
eval(source);
async function attach(runId) {{
  const response = await window.Code.agent.runtime.openSseResponse({{runId}});
  const reader = response.body.getReader();
  let text = "";
  while (true) {{
    const packet = await reader.read();
    if (packet.done) break;
    text += new TextDecoder().decode(packet.value);
  }}
  const frames = text.split(/\\r?\\n/)
    .filter((line) => line.startsWith("data: "))
    .map((line) => line.slice(6));
  return {{
    body: frames.filter((item) => item.startsWith("{{"))
      .map((item) => JSON.parse(item).choices?.[0]?.delta?.content || "")
      .join(""),
    done: frames.filter((item) => item === "[DONE]").length,
    errors: frames.filter((item) => item.startsWith("[ERROR]")).map((item) => JSON.parse(item.slice(7))),
  }};
}}
(async () => {{
  const completed = await attach("completed");
  const failed = await attach("failed");
  const cancelled = await attach("cancelled");
  process.stdout.write(JSON.stringify({{completed, failed, cancelled, calls}}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["completed"], {
            "body": "complete-body",
            "done": 1,
            "errors": [],
        })
        self.assertEqual(data["failed"]["body"], "failed-partial")
        self.assertEqual(data["failed"]["done"], 0)
        self.assertEqual(data["failed"]["errors"][0]["code"], "upstream_error")
        self.assertEqual(data["cancelled"]["body"], "cancelled-partial")
        self.assertEqual(data["cancelled"]["done"], 0)
        self.assertEqual(data["cancelled"]["errors"][0]["code"], "runtime_cancelled")
        self.assertTrue(all(call["method"] == "GET" for call in data["calls"]))
        self.assertTrue(all("cursor=0&wait=0" in call["url"] for call in data["calls"]))
        self.assertNotIn({"url": "/api/runtime/runs", "method": "POST"}, data["calls"])

    def test_replayed_model_completion_reuses_one_assistant(self):
        projection_start = APP_SOURCE.index("function projectAgentModelCompleted")
        projection_end = APP_SOURCE.index("function findAgentCompactionProjection", projection_start)
        projection_source = APP_SOURCE[projection_start:projection_end]
        script = f"""
function findAgentAssistantByRuntime(ctx, runtimeRunId) {{
  return ctx.messages.find((message) => message?.meta?.agentRuntimeRunId === runtimeRunId);
}}
function splitThoughtContent(text) {{
  return {{thought: "restored thought", content: String(text).replace(/^.*?\\n/, "")}};
}}
function toolProgressSummary() {{ return ""; }}
function agentEventMeta(ctx, event, type) {{
  return {{agentRunId: ctx.agentRunId, agentEventType: type, agentEventSeq: event.seq}};
}}
function markModelResponseStarted(run) {{ run.hasFirstModelResponseStarted = true; }}
function cloneUsageStats(usage) {{ return {{...usage}}; }}
function setSessionLastUsage() {{}}
function updateUsage() {{}}
{projection_source}
const assistant = {{
  role: "assistant",
  content: "partial body",
  thought: "partial thought",
  streaming: true,
  meta: {{agentRunId: "agent-1", agentRuntimeRunId: "runtime-1"}},
}};
const ctx = {{
  agentRunId: "agent-1",
  sessionId: "session-1",
  model: "model-1",
  messages: [assistant],
  run: {{}},
  runtimeRunId: "runtime-1",
}};
const event = {{
  seq: 12,
  createdAt: "2026-08-04T00:00:00Z",
  data: {{
    runtimeRunId: "runtime-1",
    reasoning: "final thought",
    content: "final body",
    usage: {{input: 10, output: 20}},
    toolCalls: [],
  }},
}};
projectAgentModelCompleted(ctx, event);
projectAgentModelCompleted(ctx, event);
process.stdout.write(JSON.stringify({{
  messageCount: ctx.messages.length,
  sameAssistant: ctx.messages[0] === assistant,
  streaming: assistant.streaming,
  content: assistant.content,
  eventType: assistant.meta.agentEventType,
  eventSeq: assistant.meta.agentEventSeq,
  runtimeRunId: assistant.meta.agentRuntimeRunId,
  ctxRuntimeRunId: ctx.runtimeRunId,
  runRuntimeRunId: ctx.run.runtimeRunId,
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["messageCount"], 1)
        self.assertTrue(data["sameAssistant"])
        self.assertFalse(data["streaming"])
        self.assertEqual(data["content"], "final body")
        self.assertEqual(data["eventType"], "model_completed")
        self.assertEqual(data["eventSeq"], 12)
        self.assertEqual(data["runtimeRunId"], "runtime-1")
        self.assertEqual(data["ctxRuntimeRunId"], "")
        self.assertEqual(data["runRuntimeRunId"], "")

    def test_session_title_fallbacks_use_current_language(self):
        save_state_start = APP_SOURCE.index("async function saveSessionState(")
        save_state_end = APP_SOURCE.index("async function saveCurrentSession()", save_state_start)
        save_state_source = APP_SOURCE[save_state_start:save_state_end]
        save_current_start = save_state_end
        save_current_end = APP_SOURCE.index("async function loadConfig()", save_current_start)
        save_current_source = APP_SOURCE[save_current_start:save_current_end]
        send_start = APP_SOURCE.index("async function sendMessage(")
        send_end = APP_SOURCE.index("function getSelectedModel()", send_start)
        send_source = APP_SOURCE[send_start:send_end]
        self.assertIn('|| t("untitledSession")', save_state_source)
        self.assertIn('createSession(t("sessionTitleDefault"))', save_current_source)
        self.assertIn('userText.slice(0, 24) || t("sessionTitleDefault")', send_source)
        self.assertNotIn('createSession("New session")', APP_SOURCE)

    def test_concurrent_full_session_writes_share_the_per_session_save_chain(self):
        clear_start = APP_SOURCE.index("async function clearRunCheckpoint(")
        clear_end = APP_SOURCE.index("function resetRenderCache()", clear_start)
        clear_source = APP_SOURCE[clear_start:clear_end]
        cache_start = APP_SOURCE.index("function cacheActiveSessionState()")
        cache_end = APP_SOURCE.index("function isSessionStreaming(", cache_start)
        cache_source = APP_SOURCE[cache_start:cache_end]
        current_start = APP_SOURCE.index("async function saveCurrentSession()")
        current_end = APP_SOURCE.index("async function loadConfig()", current_start)
        current_source = APP_SOURCE[current_start:current_end]

        for source in (clear_source, cache_source, current_source):
            self.assertIn("saveSessionState(", source)
            self.assertNotIn("apiJson(`/api/sessions/", source)
        for source in (clear_source, cache_source, current_source):
            self.assertIn("{ persistMessages: true }", source)

        persistence_source = (ROOT / "src" / "services" / "persistence.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("const previous = saveChains[sessionId] || Promise.resolve();", persistence_source)
        self.assertIn("saveChains[sessionId] = savePromise;", persistence_source)

    def test_successful_message_persistence_syncs_authoritative_activity_once(self):
        sync_start = APP_SOURCE.index("function syncPersistedSessionActivity(")
        sync_end = APP_SOURCE.index("async function saveSessionState(", sync_start)
        sync_source = APP_SOURCE[sync_start:sync_end]
        save_end = APP_SOURCE.index("async function saveCurrentSession()", sync_end)
        save_source = APP_SOURCE[sync_end:save_end]
        self.assertLess(
            save_source.index("const savedSession = await persistSessionPayload"),
            save_source.index("syncPersistedSessionActivity(sessionId, savedSession, options)"),
        )
        self.assertNotIn("refreshSessions", save_source)
        script = f"""
const state = {{
  sessionId: "active",
  sessionUpdated: "2026-08-23T01:00:00Z",
  sessions: [
    {{id: "active", lastMessageTime: "2026-08-23T01:00:00Z"}},
    {{id: "background", lastMessageTime: "2026-08-23T02:00:00Z"}},
  ],
}};
let renders = 0;
let panelUpdates = 0;
function renderSessions() {{ renders += 1; }}
function updateStatsPanel() {{ panelUpdates += 1; }}
{sync_source}
const activeChanged = syncPersistedSessionActivity(
  "active",
  {{lastMessageTime: "2026-08-23T03:00:00Z"}},
  {{persistMessages: true}},
);
const repeated = syncPersistedSessionActivity(
  "active",
  {{lastMessageTime: "2026-08-23T03:00:00Z"}},
  {{persistMessages: true}},
);
const metadataOnly = syncPersistedSessionActivity(
  "active",
  {{lastMessageTime: "2026-08-23T04:00:00Z"}},
  {{persistMessages: false}},
);
const invalid = syncPersistedSessionActivity(
  "active",
  {{lastMessageTime: "2026-08-23T05:00:00"}},
  {{persistMessages: true}},
);
const backgroundChanged = syncPersistedSessionActivity(
  "background",
  {{lastMessageTime: "2026-08-23T06:00:00+00:00"}},
  {{persistMessages: true}},
);
process.stdout.write(JSON.stringify({{
  activeChanged,
  repeated,
  metadataOnly,
  invalid,
  backgroundChanged,
  renders,
  panelUpdates,
  sessionUpdated: state.sessionUpdated,
  sessions: state.sessions,
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["activeChanged"])
        self.assertFalse(data["repeated"])
        self.assertFalse(data["metadataOnly"])
        self.assertFalse(data["invalid"])
        self.assertTrue(data["backgroundChanged"])
        self.assertEqual(data["renders"], 2)
        self.assertEqual(data["panelUpdates"], 1)
        self.assertEqual(data["sessionUpdated"], "2026-08-23T03:00:00Z")
        self.assertEqual(data["sessions"], [
            {"id": "active", "lastMessageTime": "2026-08-23T03:00:00Z"},
            {"id": "background", "lastMessageTime": "2026-08-23T06:00:00+00:00"},
        ])

    def test_manual_compaction_operation_locks_cover_preparation_and_release_in_finally(self):
        compact_start = APP_SOURCE.index("async function compactConversation()")
        compact_end = APP_SOURCE.index("function hideCompactConfirm()", compact_start)
        compact_source = APP_SOURCE[compact_start:compact_end]
        do_compact_start = compact_source.index("const doCompact = async () => {")
        try_index = compact_source.index("try {", do_compact_start)
        register_index = compact_source.index("operations.set(targetSessionId", try_index)
        render_index = compact_source.index(
            "renderManualCompactionTarget(targetSessionId)", register_index
        )
        persist_index = compact_source.index(
            "await persistManualCompactionTerminal(targetSessionId", render_index
        )
        finally_index = compact_source.index("} finally {", persist_index)
        delete_index = compact_source.index(
            "operations.delete(targetSessionId)", finally_index
        )
        self.assertLess(try_index, register_index)
        self.assertLess(register_index, render_index)
        self.assertLess(render_index, persist_index)
        self.assertLess(persist_index, finally_index)
        self.assertLess(finally_index, delete_index)
        self.assertIn("if (operationRegistered)", compact_source[finally_index:delete_index])

        retry_start = APP_SOURCE.index("async function retryManualCompactionPersistence(")
        retry_end = APP_SOURCE.index("function projectOptimisticFirstMessage(", retry_start)
        retry_source = APP_SOURCE[retry_start:retry_end]
        retry_try = retry_source.index("try {")
        retry_register = retry_source.index("operations.set(sessionId", retry_try)
        fingerprint_index = retry_source.index(
            "manualCompactionSaveFingerprint(sessionId)", retry_register
        )
        title_index = retry_source.index(
            "manualCompactionTargetTitle(sessionId)", fingerprint_index
        )
        save_index = retry_source.index("await saveSessionState(", title_index)
        retry_finally = retry_source.index("} finally {", save_index)
        retry_delete = retry_source.index("operations.delete(sessionId)", retry_finally)
        self.assertLess(retry_try, retry_register)
        self.assertLess(retry_register, fingerprint_index)
        self.assertLess(fingerprint_index, title_index)
        self.assertLess(title_index, save_index)
        self.assertLess(save_index, retry_finally)
        self.assertLess(retry_finally, retry_delete)
        self.assertIn(
            "if (operations && operationRegistered)",
            retry_source[retry_finally:retry_delete],
        )

    def test_import_boundary_survives_compaction_and_stays_out_of_exports(self):
        self.assertIn("if (message.meta?.skipApi) return null;", MODEL_REQUEST_SOURCE)
        self.assertIn(
            'message.role === "tool-call"',
            MODEL_REQUEST_SOURCE,
        )
        self.assertIn(
            "&& !message.meta?.skipApi",
            MODEL_REQUEST_SOURCE,
        )
        compact_start = APP_SOURCE.index("async function compactConversation()")
        compact_end = APP_SOURCE.index("function hideCompactConfirm()", compact_start)
        compact_source = APP_SOURCE[compact_start:compact_end]
        self.assertIn(
            'message?.meta?.kind === "import-boundary"',
            COMPACTION_SOURCE,
        )
        self.assertIn("const modelContextMessages = getModelContextMessages(", compact_source)
        self.assertIn("buildManualCompactionPlan(modelContextMessages, {", compact_source)
        self.assertIn("messages: requestMessages", compact_source)
        self.assertIn(
            "const completedMessages = [",
            compact_source,
        )
        self.assertIn("...messagesBeforeCompaction,", compact_source)
        self.assertIn("commitManualCompactionTarget(targetSessionId", compact_source)
        self.assertIn(
            "await persistManualCompactionTerminal(targetSessionId, completedMarker)",
            compact_source,
        )
        retry_end = APP_SOURCE.index("function projectOptimisticFirstMessage(", compact_start)
        retry_source = APP_SOURCE[compact_start:retry_end]
        self.assertIn("{ persistMessages: true }", retry_source)

        export_start = APP_SOURCE.index("function exportMarkdown()")
        export_end = APP_SOURCE.index("let sidebarDragState", export_start)
        export_source = APP_SOURCE[export_start:export_end]
        self.assertIn(
            ".filter((msg) => !msg?.meta?._system && !msg?.meta?.skipExport)",
            export_source,
        )

    def test_goal_v2_ui_slash_routing_avoids_legacy_popup_control(self):
        handler_start = APP_SOURCE.index("function handleUiSlashCommand(text)")
        handler_end = APP_SOURCE.index("function clearCurrentSession()", handler_start)
        handler_source = APP_SOURCE[handler_start:handler_end]
        script = f"""
let compactCalls = 0;
const goalFeature = {{handleSlash: () => false}};
function compactConversation() {{ compactCalls += 1; return Promise.resolve(); }}
function exportMarkdown() {{}}
function clearCurrentSession() {{}}
function createBranch() {{}}
eval({json.dumps(handler_source)});
process.stdout.write(JSON.stringify({{
  handled: handleUiSlashCommand("/compact"),
  unknown: handleUiSlashCommand("/unknown"),
  compactCalls,
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(json.loads(completed.stdout), {
            "handled": True,
            "unknown": False,
            "compactCalls": 1,
        })
        self.assertIn("goalFeature?.handleSlash(text)", handler_source)
        self.assertNotIn("goalControlFeature", APP_SOURCE)
        self.assertNotIn("createGoalControlFeature({", APP_SOURCE)

        compact_start = APP_SOURCE.index("async function compactConversation()")
        compact_end = APP_SOURCE.index("function hideCompactConfirm()", compact_start)
        compact_source = APP_SOURCE[compact_start:compact_end]
        self.assertNotIn("els.compactBtn", compact_source)
        self.assertNotIn("There are too few messages to compact.", compact_source)
        for key in (
            "compactWaitForActiveTask",
            "compactTooFewMessages",
            "compactSetupRequired",
        ):
            self.assertIn(f't("{key}")', compact_source)
        self.assertIn('confirmBtn.textContent = t("compacting")', compact_source)
        self.assertIn('confirmBtn.textContent = t("confirmCompact")', compact_source)
        for handler in ("onConfirm", "onCancel", "onModalClick"):
            self.assertIn(f'addEventListener("click", {handler})', compact_source)
            self.assertIn(f'removeEventListener("click", {handler})', compact_source)

    def test_slash_suggestions_group_commands_before_skills(self):
        script = f"""
global.window = {{Code: {{features: {{}}}}}};
eval({json.dumps(SKILLS_MEMORY_SOURCE)});
const translate = (key) => ({{
  cmdCompactDesc: "compact-desc",
  cmdGoalDesc: "goal-desc",
  cmdRememberDesc: "remember-desc",
  cmdExportDesc: "export-desc",
  cmdClearDesc: "clear-desc",
  cmdBranchDesc: "branch-desc",
  cmdParallelDesc: "parallel-desc",
  cmdHelpDesc: "help-desc",
  slashCommandsLabel: "Commands",
  slashSkillsLabel: "Skills",
}}[key] || key);
const groups = window.Code.features.skillsMemory.getSlashSuggestionGroups(
  [
    {{name: "alpha", description: "Alpha skill"}},
    {{name: "compact-skill", description: "Skill with a similar name"}},
    {{name: "disabled", description: "Disabled skill"}},
  ],
  new Set(["disabled"]),
  "",
  translate,
);
process.stdout.write(JSON.stringify(groups));
"""
        completed = subprocess.run(
            ["node", "-"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            input=script,
            check=True,
        )
        groups = json.loads(completed.stdout)
        self.assertEqual([group["key"] for group in groups], ["commands", "skills"])
        self.assertEqual(groups[0]["label"], "Commands")
        self.assertEqual(
            [item["name"] for item in groups[0]["items"]],
            ["goal", "compact", "remember", "export", "clear", "branch", "parallel", "help"],
        )
        self.assertEqual(
            [item["description"] for item in groups[0]["items"]],
            [
                "goal-desc",
                "compact-desc",
                "remember-desc",
                "export-desc",
                "clear-desc",
                "branch-desc",
                "parallel-desc",
                "help-desc",
            ],
        )
        self.assertEqual(
            [item["name"] for item in groups[1]["items"]],
            ["alpha", "compact-skill"],
        )
        self.assertIn('class="slash-section-label"', SKILLS_MEMORY_SOURCE)
        self.assertIn(".slash-section + .slash-section", STYLE_SOURCE)
        self.assertIn('slashCommandsLabel: "命令", slashSkillsLabel: "Skills"', I18N_SOURCE)
        self.assertIn('slashCommandsLabel: "Commands", slashSkillsLabel: "Skills"', I18N_SOURCE)
        self.assertIn(
            'cmdParallelDesc: "主任务运行时，启动共享当前项目的后台子 Agent"',
            I18N_SOURCE,
        )
        self.assertIn(
            'cmdParallelDesc: "Start a background Subagent that shares the current project"',
            I18N_SOURCE,
        )

    def test_goal_v2_replaces_draft_dialogs_with_compact_event_projection(self):
        self.assertIn('const { createGoalFeature } = window.Code.features.goal;', APP_SOURCE)
        self.assertIn("goalFeature = createGoalFeature({", APP_SOURCE)
        self.assertNotIn("goalControlFeature", APP_SOURCE)
        self.assertNotIn("createGoalControlFeature({", APP_SOURCE)
        self.assertIn('route.endswith("/goal-v2/control")', SERVER_SOURCE)
        self.assertNotIn('route.endswith("/goal/control")', SERVER_SOURCE)
        self.assertNotIn("window.confirm", GOAL_SOURCE)
        self.assertNotIn("window.alert", GOAL_SOURCE)
        self.assertNotIn("step.acceptanceCriteria", GOAL_SOURCE)
        self.assertNotIn("criterion.kind", GOAL_SOURCE)
        self.assertNotIn("criterion.description", GOAL_SOURCE)
        self.assertNotIn("goal-progress-criteria", GOAL_SOURCE)
        self.assertNotIn("goal-progress-criterion-kind", GOAL_SOURCE)
        self.assertNotIn(".goal-progress-criteria", STYLE_SOURCE)
        self.assertNotIn(".goal-progress-criterion-kind", STYLE_SOURCE)
        for key in (
            "goalStep_pending",
            "goalStep_in_progress",
            "goalStep_completed",
            "goalCriterion_machine",
            "goalCriterion_agent",
            "goalCriterion_user",
        ):
            self.assertEqual(I18N_SOURCE.count(f"{key}:"), 2)
        self.assertIn("inProgressIndexes.length === 1", GOAL_SOURCE)
        self.assertEqual(GOAL_SOURCE.count("current: progress"), 2)
        self.assertIn(
            'goalProgressAriaLabel: "Goal：{objective}，{phase}，进度 {current}/{total}"',
            I18N_SOURCE,
        )
        self.assertIn(
            'goalProgressAriaLabel: "Goal: {objective}, {phase}, progress {current}/{total}"',
            I18N_SOURCE,
        )
        self.assertEqual(
            I18N_SOURCE.count('goalProgressCount: "{current}/{total}"'),
            2,
        )
        self.assertNotIn('goalProgressCount: "{completed}/{total}"', I18N_SOURCE)

    def test_goal_projection_is_hidden_during_session_transition_and_restored_on_failure(self):
        script = f"""
const window = {{Code: {{features: {{}}}}}};
global.window = window;
eval({json.dumps(GOAL_SOURCE)});

function node() {{
  return {{
    hidden: true,
    textContent: "",
    innerHTML: "",
    className: "",
    dataset: {{}},
    attributes: {{}},
    classList: {{toggle() {{}}, add() {{}}, remove() {{}}}},
    setAttribute(name, value) {{ this.attributes[name] = String(value); }},
    addEventListener() {{}},
    removeEventListener() {{}},
    contains() {{ return false; }},
    matches() {{ return false; }},
    focus() {{}},
  }};
}}
const elements = {{
  goalProgress: node(),
  goalProgressSummary: node(),
  goalProgressObjective: node(),
  goalProgressPhase: node(),
  goalProgressCount: node(),
  goalProgressDetails: node(),
}};
const documentRef = {{
  activeElement: null,
  addEventListener() {{}},
  removeEventListener() {{}},
}};
const pending = [];
const apiJson = (url) => new Promise((resolve, reject) => pending.push({{url, resolve, reject}}));
const projection = (objective) => ({{
  data: {{
    exists: true,
    health: "healthy",
    revision: 1,
    goal: {{goalId: objective, lifecycle: "active", sourceKind: "model", objective, steps: []}},
  }},
}});
const feature = window.Code.features.goal.createGoalFeature({{
  apiJson,
  t: (key) => key,
  getSessionId: () => "",
  getMessages: () => [],
  elements,
  document: documentRef,
}});
const flush = () => new Promise((resolve) => setImmediate(resolve));

(async () => {{
  feature.setSession("source");
  pending.shift().resolve(projection("source goal"));
  await flush();
  const initiallyVisible = !elements.goalProgress.hidden && elements.goalProgressObjective.textContent === "source goal";

  const lateRefresh = feature.refresh("source");
  const lateRequest = pending.shift();
  const token = feature.beginSessionTransition("target");
  const hiddenImmediately = elements.goalProgress.hidden
    && elements.goalProgressObjective.textContent === ""
    && feature.getCached() === null;
  lateRequest.resolve(projection("late source goal"));
  await lateRefresh;
  feature.setSession("source");
  const lateSourceDiscarded = elements.goalProgress.hidden && pending.length === 0;

  feature.setSession("target");
  const targetRequest = pending.shift();
  const hiddenUntilTargetGoal = elements.goalProgress.hidden;
  targetRequest.resolve(projection("target goal"));
  await flush();
  const targetVisible = !elements.goalProgress.hidden && elements.goalProgressObjective.textContent === "target goal";

  const failedToken = feature.beginSessionTransition("failed");
  const wrongTokenRejected = feature.cancelSessionTransition("target", token) === false
    && elements.goalProgress.hidden;
  const restored = feature.cancelSessionTransition("target", failedToken) === true
    && !elements.goalProgress.hidden
    && elements.goalProgressObjective.textContent === "target goal";
  process.stdout.write(JSON.stringify({{
    initiallyVisible,
    hiddenImmediately,
    lateSourceDiscarded,
    hiddenUntilTargetGoal,
    targetVisible,
    wrongTokenRejected,
    restored,
  }}));
}})().catch((error) => {{ console.error(error); process.exitCode = 1; }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "initiallyVisible": True,
                "hiddenImmediately": True,
                "lateSourceDiscarded": True,
                "hiddenUntilTargetGoal": True,
                "targetVisible": True,
                "wrongTokenRejected": True,
                "restored": True,
            },
        )

    def test_goal_create_reuses_the_same_waiting_draft_without_a_second_write(self):
        script = r"""
global.window = {Code: {features: {}}};
require("./src/features/skills-memory.js");
const {createGoalControlFeature} = window.Code.features.skillsMemory;
const calls = [];
const confirms = [];
const toasts = [];
let projection = {
  revision: 1,
  goal: {
    goalId: "goal-existing",
    lifecycle: "awaiting_confirmation",
    objective: "做一个不修改项目文件的演示目标",
    steps: [
      {status: "pending", description: "确认范围", acceptanceCriteria: [{kind: "user", description: "用户确认"}]},
      {status: "pending", description: "安全执行", acceptanceCriteria: [{kind: "agent", description: "不写项目"}]},
      {status: "pending", description: "验收结果", acceptanceCriteria: [{kind: "user", description: "用户验收"}]},
    ],
  },
};
const feature = createGoalControlFeature({
  t: (key, params) => params?.error ? `${key}:${params.error}` : key,
  apiJson: async (_url, request = {}) => {
    const body = request.body ? JSON.parse(request.body) : null;
    calls.push(body?.operation || "query");
    if (!body) return {data: projection};
    if (body.operation !== "confirm_draft") throw new Error(`unexpected ${body.operation}`);
    projection = {...projection, revision: 2, goal: {...projection.goal, lifecycle: "active"}};
    return {data: projection};
  },
  getSessionId: () => "session-existing",
  getPermissionProfile: () => "accept",
  getLanguage: () => "zh",
  confirm: (message) => { confirms.push(message); return true; },
  showToast: (message, kind) => toasts.push({message, kind}),
});
(async () => {
  await feature.execute({kind: "create", objective: projection.goal.objective});
  projection = {
    ...projection,
    revision: 3,
    goal: {...projection.goal, lifecycle: "awaiting_confirmation", objective: "另一个目标"},
  };
  const beforeDifferent = calls.length;
  await feature.execute({kind: "create", objective: "不同目标"});
  process.stdout.write(JSON.stringify({calls, confirms, toasts, beforeDifferent}));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            input=script,
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["calls"][:2], ["query", "confirm_draft"])
        self.assertNotIn("create_draft", data["calls"])
        self.assertIn("[user] 用户确认", data["confirms"][0])
        self.assertEqual(data["calls"][data["beforeDifferent"]:], ["query"])
        self.assertTrue(
            any("goalDraftAlreadyExists" in item["message"] for item in data["toasts"])
        )
        self.assertIn("const isBlankWelcome = state.messages.length === 0 && !state.sessionId", APP_SOURCE)

    def test_settings_shell_is_responsive_and_navigation_is_grouped(self):
        for key in (
            "settingsGroupAgent",
            "settingsGroupAppearance",
            "settingsGroupApplication",
        ):
            self.assertIn(f'data-i18n="{key}"', INDEX_SOURCE)

        self.assertEqual(INDEX_SOURCE.count('class="settings-nav-group"'), 3)
        self.assertIn("width: min(1150px, calc(100vw - 48px))", STYLE_SOURCE)
        self.assertIn("height: min(830px, calc(100vh - 48px))", STYLE_SOURCE)
        self.assertIn(".settings-page-card > header { flex: 0 0 auto; }", STYLE_SOURCE)
        self.assertIn(".settings-nav-group + .settings-nav-group", STYLE_SOURCE)

        layout_start = STYLE_SOURCE.index(".settings-layout {")
        layout_end = STYLE_SOURCE.index(".settings-nav {", layout_start)
        layout = STYLE_SOURCE[layout_start:layout_end]
        self.assertIn("flex: 1 1 auto", layout)
        self.assertIn("min-height: 0", layout)
        self.assertNotIn("height: 750px", layout)

    def test_language_switch_is_global_sidebar_control(self):
        self.assertNotIn('data-panel="language"', INDEX_SOURCE)
        self.assertIn('id="settingsLanguageSwitch"', INDEX_SOURCE)
        self.assertEqual(INDEX_SOURCE.count("data-settings-lang="), 2)
        self.assertIn("function updateLanguageControls()", SETTINGS_SOURCE)
        self.assertIn('byId("settingsLanguageSwitch")?.addEventListener("click"', SETTINGS_SOURCE)
        self.assertIn('const activePanel = documentRef.querySelector(".settings-nav-item.active")?.dataset.panel', SETTINGS_SOURCE)
        self.assertIn("function refreshActiveSettingsLanguage(panel)", SETTINGS_SOURCE)
        self.assertIn("refreshActiveSettingsLanguage(activePanel);", SETTINGS_SOURCE)
        self.assertIn('const balance = byId("accountBalanceValue")', SETTINGS_SOURCE)
        self.assertIn('data-i18n="accountLoggedIn"', SETTINGS_SOURCE)
        self.assertIn('class="account-connection-dot"', SETTINGS_SOURCE)
        self.assertIn(".account-connection-dot {", STYLE_SOURCE)
        self.assertNotIn(".account-connection span {", STYLE_SOURCE)
        self.assertIn("refreshSkillsMemorySettingsLanguage(panel);", SETTINGS_SOURCE)
        self.assertIn("renderThemePanel(detail);", SETTINGS_SOURCE)
        self.assertNotIn('if (activePanel === "skills") switchSettingsPanel("skills")', SETTINGS_SOURCE)
        self.assertNotIn("function renderLanguagePanel(", SETTINGS_SOURCE)
        self.assertIn(".settings-language-options", STYLE_SOURCE)
        self.assertIn('data-i18n-title="getFromWorkbar"', SETTINGS_SOURCE)
        self.assertIn('<span data-i18n="getFromWorkbar">', SETTINGS_SOURCE)
        for marker in (
            'data-i18n="models"',
            'data-i18n="apiKeys"',
            'data-i18n="availableModels"',
            'data-i18n="systemPromptHint"',
            'data-i18n="updateReadyHint"',
        ):
            self.assertIn(marker, SETTINGS_SOURCE)
        self.assertIn("function refreshSettingsLanguage(panel)", SKILLS_MEMORY_SOURCE)
        self.assertIn('label.textContent = t("editingMemory", { name: state._editingMemory })', SKILLS_MEMORY_SOURCE)
        self.assertIn("refreshSettingsLanguage: refreshSkillsMemorySettingsLanguage", APP_SOURCE)
        self.assertIn("refreshSkillsMemorySettingsLanguage,", APP_SOURCE)

    def test_account_page_refreshes_lazily_and_uses_safe_summary_fields(self):
        self.assertIn('data-panel="account" data-i18n="platformAccount">workbar 账号</button>', INDEX_SOURCE)
        self.assertIn("async function refreshPlatformAccount(container, auth)", SETTINGS_SOURCE)
        self.assertIn("if (refresh) refreshPlatformAccount(container, auth);", SETTINGS_SOURCE)
        self.assertIn("function formatAccountQuota(value, display = {})", SETTINGS_SOURCE)
        self.assertIn('platformAccount: "workbar 账号"', I18N_SOURCE)
        self.assertIn('platformAccount: "workbar account"', I18N_SOURCE)
        for field in (
            "accountBalance",
            "accountUsedQuota",
            "accountRequests",
            "accountEmail",
            "accountGroup",
        ):
            self.assertEqual(I18N_SOURCE.count(f"{field}:"), 2)

    def test_workbar_gate_keeps_api_key_phrase_on_its_own_line(self):
        for key in ("connectWorkbarDescPrimary", "connectWorkbarDescSecondary"):
            self.assertEqual(I18N_SOURCE.count(f"{key}:"), 2)
        self.assertNotIn("connectWorkbarDesc:", I18N_SOURCE)
        self.assertIn('class="${expired || unavailable ? "" : "platform-auth-description"}"', SETTINGS_SOURCE)
        self.assertIn('t("connectWorkbarDescPrimary")', SETTINGS_SOURCE)
        self.assertIn('t("connectWorkbarDescSecondary")', SETTINGS_SOURCE)
        self.assertIn(".platform-auth-description span { display: block; }", STYLE_SOURCE)

    def test_explicit_onboarding_tasks_replace_the_removed_legacy_overlay(self):
        self.assertNotIn('id="onboardingOverlay"', INDEX_SOURCE)
        self.assertNotIn(".onboarding-overlay", STYLE_SOURCE)
        self.assertNotIn("function shouldShowOnboarding(", SETTINGS_SOURCE)
        self.assertNotIn("function showOnboarding(", SETTINGS_SOURCE)
        self.assertNotIn("shouldShowOnboarding", APP_SOURCE)
        self.assertNotIn("showOnboarding", APP_SOURCE)
        self.assertNotRegex(I18N_SOURCE, r"\bobo(?:Welcome|Feat|Start|Step)")
        self.assertIn('localStorage.removeItem("code-onboarding")', APP_SOURCE)
        self.assertIn('localStorage.removeItem("agent-lite-onboarding")', APP_SOURCE)
        self.assertIn('const ONBOARDING_STORAGE_KEY = "code-onboarding-tasks-v1"', ONBOARDING_TASKS_SOURCE)
        self.assertNotIn('"code-onboarding"', ONBOARDING_TASKS_SOURCE)
        self.assertNotIn('"agent-lite-onboarding"', ONBOARDING_TASKS_SOURCE)
        self.assertIn('id="composerStack"', INDEX_SOURCE)
        self.assertIn('id="onboardingTasks"', INDEX_SOURCE)
        self.assertIn('data-panel="onboarding"', INDEX_SOURCE)
        self.assertIn('import "./features/onboarding-tasks.js";', FRONTEND_ENTRY_SOURCE)

        stack_start = INDEX_SOURCE.index('<div id="composerStack"')
        tool_preset_start = INDEX_SOURCE.index('<select id="toolPreset"', stack_start)
        stack_source = INDEX_SOURCE[stack_start:tool_preset_start]
        form_start = stack_source.index('<form id="chatForm"')
        form_end = stack_source.index("</form>", form_start) + len("</form>")
        form_source = stack_source[form_start:form_end]
        self.assertEqual(form_source.count("<div"), form_source.count("</div>"))
        self.assertRegex(
            stack_source,
            r'(?s)<form id="chatForm".*?</form>\s*'
            r'<section id="onboardingTasks"[^>]*></section>\s*</div>\s*$',
        )

    def test_onboarding_state_is_ordered_minimal_and_fail_closed(self):
        script = f"""
global.window = {{Code: {{features: {{}}}}}};
eval({json.dumps(ONBOARDING_TASKS_SOURCE)});
const {{createOnboardingStateMachine}} = window.Code.features.onboardingTasks;

class MemoryStorage {{
  constructor(initial = {{}}) {{ this.values = new Map(Object.entries(initial)); this.writes = 0; }}
  getItem(key) {{ return this.values.has(key) ? this.values.get(key) : null; }}
  setItem(key, value) {{ this.writes += 1; this.values.set(key, String(value)); }}
}}
function finish(machine, taskId, success = true, claim = true) {{
  const intentId = machine.beginIntent(taskId);
  if (!intentId) return {{intentId, result: false}};
  if (claim && machine.claimIntent(taskId) !== intentId) throw new Error(`claim failed for ${{taskId}}`);
  return {{intentId, result: machine.resolveIntent(intentId, success)}};
}}

function migrateLegacy(completedTaskIds, completed = false, collapsed = false) {{
  const storage = new MemoryStorage({{
    "code-onboarding-tasks-v1": JSON.stringify({{
      version: 1,
      completedTaskIds,
      collapsed,
      completed,
    }}),
  }});
  const machine = createOnboardingStateMachine({{storage}});
  return {{
    state: machine.initialize({{hasExistingSessions: false}}),
    stored: JSON.parse(storage.getItem("code-onboarding-tasks-v1")),
  }};
}}

const storage = new MemoryStorage();
const machine = createOnboardingStateMachine({{storage, nonceFactory: (() => {{ let n = 0; return () => `n-${{++n}}`; }})()}});
const initial = machine.initialize({{hasExistingSessions: false}});
const passive = machine.snapshot();
const outOfOrder = machine.beginIntent("key");
const failed = finish(machine, "workbar", false);
const afterFailure = machine.snapshot();
const workbar = finish(machine, "workbar");
const afterWorkbar = machine.snapshot();
const unclaimedKey = machine.beginIntent("key");
const serializedWhilePending = storage.getItem("code-onboarding-tasks-v1");

const restored = createOnboardingStateMachine({{storage, nonceFactory: () => "restored"}});
const restoredState = restored.initialize({{hasExistingSessions: false}});
const restoredPending = restored.pendingIntent();
for (const taskId of ["key", "first-task"]) {{
  const result = finish(restored, taskId);
  if (!result.result) throw new Error(`completion failed for ${{taskId}}`);
}}
const completeState = restored.snapshot();
const completedRaw = storage.getItem("code-onboarding-tasks-v1");
const completedKeys = Object.keys(JSON.parse(completedRaw)).sort();
restored.reopen();
const resetAfterReopen = restored.snapshot();

const migratedLegacy = [
  migrateLegacy([]),
  migrateLegacy(["workbar"]),
  migrateLegacy(["workbar", "key"], false, true),
  migrateLegacy(["workbar", "key", "model"]),
  migrateLegacy(["workbar", "key", "model", "first-task"], true),
];

const oldStorage = new MemoryStorage();
const oldUser = createOnboardingStateMachine({{storage: oldStorage}});
const oldUserState = oldUser.initialize({{hasExistingSessions: true}});
const oldUserDefaultExempt = oldUser.isDefaultExempt();
const oldUserStored = oldStorage.getItem("code-onboarding-tasks-v1");
oldUser.reopen();
const oldUserReopened = oldUser.snapshot();
const oldUserReopenedStored = oldStorage.getItem("code-onboarding-tasks-v1");

const corruptStorage = new MemoryStorage({{"code-onboarding-tasks-v1": "{{broken"}});
const corrupt = createOnboardingStateMachine({{storage: corruptStorage}});
const corruptState = corrupt.initialize({{hasExistingSessions: false}});
const unknownStorage = new MemoryStorage({{
  "code-onboarding-tasks-v1": JSON.stringify({{version: 99, completedTaskIds: ["workbar", "key", "first-task"], completed: true}}),
}});
const unknown = createOnboardingStateMachine({{storage: unknownStorage}});
const unknownState = unknown.initialize({{hasExistingSessions: false}});

let storageErrors = 0;
const failingStorage = {{getItem() {{ return null; }}, setItem() {{ throw new Error("denied"); }}}};
const failing = createOnboardingStateMachine({{storage: failingStorage, onStorageError: () => storageErrors++}});
failing.initialize({{hasExistingSessions: false}});
const failedWriteIntent = failing.beginIntent("workbar");
const failedWriteResult = failing.resolveIntent(failedWriteIntent, true);
const failedWriteState = failing.snapshot();

const firstTaskStorage = new MemoryStorage({{
  "code-onboarding-tasks-v1": JSON.stringify({{
    version: 2,
    completedTaskIds: ["workbar", "key"],
    completed: false,
  }}),
}});
const firstTask = createOnboardingStateMachine({{storage: firstTaskStorage, nonceFactory: () => "first"}});
firstTask.initialize({{hasExistingSessions: false}});
const fillOnlyState = firstTask.snapshot();
const cancelledFirstTaskIntent = firstTask.beginIntent("first-task");
const cancelResult = firstTask.cancelIntent(cancelledFirstTaskIntent);
const afterCancelState = firstTask.snapshot();
const failedDispatchIntent = firstTask.beginIntent("first-task");
const failedDispatchClaim = firstTask.claimIntent("first-task");
const failedDispatchResult = firstTask.resolveIntent(failedDispatchIntent, false);
const afterFailedDispatchState = firstTask.snapshot();

process.stdout.write(JSON.stringify({{
  initial,
  passive,
  outOfOrder,
  failed,
  afterFailure,
  workbar,
  afterWorkbar,
  unclaimedKey: Boolean(unclaimedKey),
  serializedWhilePending,
  restoredState,
  restoredPending,
  completeState,
  completedKeys,
  completedRaw,
  resetAfterReopen,
  migratedLegacy,
  oldUserState,
  oldUserDefaultExempt,
  oldUserStored,
  oldUserReopened,
  oldUserReopenedStored,
  corruptState,
  unknownState,
  failedWriteResult,
  failedWriteState,
  storageErrors,
  fillOnlyState,
  cancelResult,
  afterCancelState,
  failedDispatchClaim,
  failedDispatchIntent,
  failedDispatchResult,
  afterFailedDispatchState,
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        result = json.loads(completed.stdout)
        fresh = {
            "version": 2,
            "completedTaskIds": [],
            "completed": False,
        }
        self.assertEqual(result["initial"], fresh)
        self.assertEqual(result["passive"], fresh)
        self.assertIsNone(result["outOfOrder"])
        self.assertFalse(result["failed"]["result"])
        self.assertEqual(result["afterFailure"], fresh)
        self.assertTrue(result["workbar"]["result"])
        self.assertEqual(result["afterWorkbar"]["completedTaskIds"], ["workbar"])
        self.assertTrue(result["unclaimedKey"])
        serialized_pending = json.loads(result["serializedWhilePending"])
        self.assertEqual(
            sorted(serialized_pending),
            ["completed", "completedTaskIds", "version"],
        )
        self.assertEqual(serialized_pending["completedTaskIds"], ["workbar"])
        self.assertEqual(result["restoredState"]["completedTaskIds"], ["workbar"])
        self.assertIsNone(result["restoredPending"])
        self.assertEqual(result["completeState"]["completedTaskIds"], ["workbar", "key", "first-task"])
        self.assertTrue(result["completeState"]["completed"])
        self.assertEqual(result["completedKeys"], ["completed", "completedTaskIds", "version"])
        self.assertNotRegex(result["completedRaw"], r"(?i)(api.?key|token|account|message|secret)")
        self.assertEqual(result["resetAfterReopen"], fresh)
        self.assertEqual(result["migratedLegacy"], [
            {"state": fresh, "stored": fresh},
            {"state": {**fresh, "completedTaskIds": ["workbar"]}, "stored": {**fresh, "completedTaskIds": ["workbar"]}},
            {"state": {**fresh, "completedTaskIds": ["workbar", "key"]}, "stored": {**fresh, "completedTaskIds": ["workbar", "key"]}},
            {"state": {**fresh, "completedTaskIds": ["workbar", "key"]}, "stored": {**fresh, "completedTaskIds": ["workbar", "key"]}},
            {
                "state": {"version": 2, "completedTaskIds": ["workbar", "key", "first-task"], "completed": True},
                "stored": {"version": 2, "completedTaskIds": ["workbar", "key", "first-task"], "completed": True},
            },
        ])
        self.assertFalse(result["oldUserState"]["completed"])
        self.assertTrue(result["oldUserDefaultExempt"])
        self.assertIsNone(result["oldUserStored"])
        self.assertEqual(result["oldUserReopened"], fresh)
        self.assertIsNotNone(result["oldUserReopenedStored"])
        self.assertEqual(result["corruptState"], fresh)
        self.assertEqual(result["unknownState"], fresh)
        self.assertFalse(result["failedWriteResult"])
        self.assertEqual(result["failedWriteState"], fresh)
        self.assertGreaterEqual(result["storageErrors"], 2)
        first_task_pending = {**fresh, "completedTaskIds": ["workbar", "key"]}
        self.assertEqual(result["fillOnlyState"], first_task_pending)
        self.assertTrue(result["cancelResult"])
        self.assertEqual(result["afterCancelState"], first_task_pending)
        self.assertEqual(result["failedDispatchClaim"], result["failedDispatchIntent"])
        self.assertFalse(result["failedDispatchResult"])
        self.assertEqual(result["afterFailedDispatchState"], first_task_pending)

    def test_onboarding_completion_is_one_shot_and_out_of_composer_flow(self):
        script = f"""
global.window = {{Code: {{features: {{}}}}}};
eval({json.dumps(ONBOARDING_TASKS_SOURCE)});
const {{createOnboardingTasksFeature}} = window.Code.features.onboardingTasks;

function makeClassList() {{
  const values = new Set();
  return {{
    toggle(name, force) {{
      const enabled = force === undefined ? !values.has(name) : Boolean(force);
      if (enabled) values.add(name); else values.delete(name);
      return enabled;
    }},
    contains(name) {{ return values.has(name); }},
  }};
}}
function attach(parent, child, before = null) {{
  if (child.parentElement) {{
    const index = child.parentElement.children.indexOf(child);
    if (index >= 0) child.parentElement.children.splice(index, 1);
  }}
  const targetIndex = before ? parent.children.indexOf(before) : -1;
  if (targetIndex >= 0) parent.children.splice(targetIndex, 0, child);
  else parent.children.push(child);
  child.parentElement = parent;
}}
function makeTree() {{
  const host = {{name: "chatPane", children: [], appendChild(child) {{ attach(this, child); }}}};
  const stack = {{
    name: "composerStack",
    children: [],
    parentElement: host,
    appendChild(child) {{ attach(this, child); }},
    insertBefore(child, before) {{ attach(this, child, before); }},
    closest(selector) {{ return selector === ".chat-pane" ? host : null; }},
  }};
  host.children.push(stack);
  const listeners = {{}};
  const root = {{
    parentElement: stack,
    nextSibling: null,
    classList: makeClassList(),
    dataset: {{}},
    innerHTML: "",
    addEventListener(type, callback) {{ listeners[type] = callback; }},
  }};
  stack.children.push(root);
  return {{host, stack, root, listeners}};
}}
class MemoryStorage {{
  constructor(value) {{ this.value = value; }}
  getItem() {{ return this.value; }}
  setItem(key, value) {{ this.value = String(value); }}
}}
const firstTaskRaw = JSON.stringify({{
  version: 2,
  completedTaskIds: ["workbar", "key"],
  completed: false,
}});
let scheduled = null;
let scheduleCount = 0;
window.setTimeout = (callback, delay) => {{ scheduled = {{callback, delay}}; scheduleCount += 1; return scheduleCount; }};
window.clearTimeout = () => {{ scheduled = null; }};
window.requestAnimationFrame = () => 0;
const tree = makeTree();
const feature = createOnboardingTasksFeature({{
  root: tree.root,
  storage: new MemoryStorage(firstTaskRaw),
  t: (key) => ({{
    onboardingCompleteTitle: "您已准备好使用 Code",
    onboardingCompleteDescription: "新手任务已全部完成",
  }}[key] || key),
  actions: {{"first-task": async () => ({{pending: true, ready: true}})}},
}});
feature.bind();
feature.initialize({{hasExistingSessions: false, isWelcomeVisible: true}});
tree.listeners.click({{target: {{closest(selector) {{
  if (selector === "[data-onboarding-example]") return null;
  if (selector === "[data-onboarding-task-action]") return {{dataset: {{onboardingTaskAction: "first-task"}}}};
  return null;
}}}}}});

setImmediate(() => {{
  const intentId = feature.claimFirstTaskIntent();
  const completed = feature.completeIntent(intentId);
  const live = {{
    completed,
    parentIsHost: tree.root.parentElement === tree.host,
    stackChildren: tree.stack.children.length,
    celebrating: tree.root.classList.contains("is-celebrating"),
    hidden: tree.root.classList.contains("hidden"),
    copyVisible: tree.root.innerHTML.includes("您已准备好使用 Code")
      && tree.root.innerHTML.includes("新手任务已全部完成"),
    roleStatus: tree.root.innerHTML.includes('role="status"'),
    delay: scheduled?.delay,
    scheduleCount,
  }};
  scheduled.callback();
  const afterTimer = {{
    parentIsInline: tree.root.parentElement === tree.stack,
    celebrating: tree.root.classList.contains("is-celebrating"),
    hidden: tree.root.classList.contains("hidden"),
    completionPresent: tree.root.innerHTML.includes("data-onboarding-complete"),
  }};
  feature.initialize({{hasExistingSessions: false, isWelcomeVisible: true}});
  const afterReload = {{
    scheduleCount,
    celebrating: tree.root.classList.contains("is-celebrating"),
    hidden: tree.root.classList.contains("hidden"),
    completionPresent: tree.root.innerHTML.includes("data-onboarding-complete"),
  }};
  const migratedTree = makeTree();
  const migratedFeature = createOnboardingTasksFeature({{
    root: migratedTree.root,
    storage: new MemoryStorage(JSON.stringify({{
      version: 1,
      completedTaskIds: ["workbar", "key", "model", "first-task"],
      completed: true,
      collapsed: false,
    }})),
  }});
  migratedFeature.initialize({{hasExistingSessions: false, isWelcomeVisible: true}});
  const afterMigration = {{
    scheduleCount,
    parentIsInline: migratedTree.root.parentElement === migratedTree.stack,
    celebrating: migratedTree.root.classList.contains("is-celebrating"),
    hidden: migratedTree.root.classList.contains("hidden"),
    completionPresent: migratedTree.root.innerHTML.includes("data-onboarding-complete"),
  }};
  process.stdout.write(JSON.stringify({{live, afterTimer, afterReload, afterMigration}}));
}});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["live"], {
            "completed": True,
            "parentIsHost": True,
            "stackChildren": 0,
            "celebrating": True,
            "hidden": False,
            "copyVisible": True,
            "roleStatus": True,
            "delay": 2400,
            "scheduleCount": 1,
        })
        self.assertEqual(result["afterTimer"], {
            "parentIsInline": True,
            "celebrating": False,
            "hidden": True,
            "completionPresent": False,
        })
        self.assertEqual(result["afterReload"], {
            "scheduleCount": 1,
            "celebrating": False,
            "hidden": True,
            "completionPresent": False,
        })
        self.assertEqual(result["afterMigration"], {
            "scheduleCount": 1,
            "parentIsInline": True,
            "celebrating": False,
            "hidden": True,
            "completionPresent": False,
        })

    def test_onboarding_actions_use_explicit_real_success_boundaries(self):
        self.assertIn("isWelcomeVisible: state.messages.length === 0 && !state.sessionId", APP_SOURCE)
        self.assertIn("onboardingTasksFeature?.setWelcomeVisible(isBlankWelcome)", APP_SOURCE)
        self.assertIn('verifyPlatformConnection({ updateGate: true })', APP_SOURCE)
        self.assertIn('onboardingTasksFeature?.isPending("key")', APP_SOURCE)
        self.assertIn('onboardingTasksFeature?.confirmFirstTaskModel()', APP_SOURCE)
        self.assertIn('onboardingTasksFeature?.claimFirstTaskIntent()', APP_SOURCE)
        self.assertIn("onAgentRunCreated({ agentRunId: ctx.agentRunId, sessionId: ctx.sessionId })", APP_SOURCE)
        self.assertLess(
            APP_SOURCE.index('ctx.agentRunId = String(created.agentRunId || "")'),
            APP_SOURCE.index("onAgentRunCreated({ agentRunId: ctx.agentRunId, sessionId: ctx.sessionId })"),
        )
        self.assertIn("if (!result?.ok || !Array.isArray(result.models) || result.models.length === 0) return false", APP_SOURCE)
        self.assertIn("const currentTaskId = machine.currentTaskId()", ONBOARDING_TASKS_SOURCE)
        self.assertIn("if (normalized !== currentTaskId()) return null", ONBOARDING_TASKS_SOURCE)
        self.assertIn("const showTasks = welcomeVisible && !defaultExempt && !state.completed", ONBOARDING_TASKS_SOURCE)
        self.assertIn("if (pending && !pending.claimed)", ONBOARDING_TASKS_SOURCE)
        self.assertIn("intent = null", ONBOARDING_TASKS_SOURCE)
        self.assertNotIn("pendingIntent:", ONBOARDING_TASKS_SOURCE.split("function persist(candidate)", 1)[0])
        self.assertNotIn("setCollapsed", ONBOARDING_TASKS_SOURCE)
        self.assertNotIn("onboardingLater", ONBOARDING_TASKS_SOURCE)
        self.assertNotIn("onboardingRestore", ONBOARDING_TASKS_SOURCE)
        self.assertIn('fetchFn("/api/code/auth/validate"', SETTINGS_SOURCE)
        self.assertIn("verifyPlatformConnection,", SETTINGS_SOURCE)
        self.assertIn("beginNewConversation(projectIdForNewConversation())", APP_SOURCE)
        self.assertIn('data-onboarding-example="${index}"', ONBOARDING_TASKS_SOURCE)
        self.assertIn('els.prompt.dispatchEvent(new Event("input", { bubbles: true }))', APP_SOURCE)
        self.assertIn('permissionProfile: getStoredValue("code-permission-profile") || "accept"', STATE_SOURCE)
        self.assertIn('setThinkingLevel(localStorage.getItem("code-thinking") || "auto")', APP_SOURCE)
        self.assertIn('const savedPerm = localStorage.getItem("code-permission-profile") || "accept"', APP_SOURCE)

        for key in (
            "onboardingTitle",
            "onboardingWorkbarTitle",
            "onboardingKeyTitle",
            "onboardingFirstTaskTitle",
            "onboardingExamplesTitle",
            "onboardingExampleProjectStructure",
            "onboardingExampleAnalyzeProblems",
            "onboardingExampleSmallChange",
            "onboardingCompleteTitle",
            "onboardingSettingsAction",
        ):
            self.assertEqual(I18N_SOURCE.count(f"{key}:"), 2)
        for copy in (
            "请介绍 Code 能做什么，并推荐几个适合第一次尝试的任务。",
            "请先询问我想整理的内容和网页地址，再联网读取并整理关键结论与来源。",
            "请通过问卷了解我想制作的 HTML 小项目，再创建 Goal，生成并验证一个可直接打开的单文件 HTML。",
            "您已准备好使用 Code",
            "新手任务已全部完成",
            "Please introduce what Code can do and recommend a few tasks that are good for a first try.",
            "First ask what content and web address I want to organize, then access the web to read it and summarize the key conclusions and sources.",
            "Use a questionnaire to understand the small HTML project I want to make, then create a Goal and generate and verify a single-file HTML page that I can open directly.",
            "You're ready to use Code",
            "You've completed all getting-started tasks",
        ):
            self.assertIn(copy, I18N_SOURCE)
        self.assertIn("const composerRoot = els.composerStack || els.chatForm", APP_SOURCE)
        self.assertIn("composerResizeObserver.observe(composerRoot)", APP_SOURCE)
        self.assertIn(".chat-pane.empty-chat .composer-stack {", STYLE_SOURCE)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", STYLE_SOURCE)
        shrink_rule = re.search(
            r"\.composer-stack > \.composer,\s*"
            r"\.composer-stack > \.onboarding-tasks\s*\{([^}]*)\}",
            STYLE_SOURCE,
        )
        self.assertIsNotNone(shrink_rule)
        self.assertIn("box-sizing: border-box;", shrink_rule.group(1))
        self.assertIn("min-width: 0;", shrink_rule.group(1))
        self.assertIn("max-width: 100%;", shrink_rule.group(1))
        self.assertIn(".composer-stack > .onboarding-tasks { width: 100%; }", STYLE_SOURCE)
        self.assertIn("width: var(--conversation-content-width);", STYLE_SOURCE)
        self.assertIn(".onboarding-example-list", STYLE_SOURCE)
        self.assertIn("box-shadow: none;", STYLE_SOURCE)
        self.assertNotIn(".onboarding-restore", STYLE_SOURCE)
        self.assertNotIn(".onboarding-later", STYLE_SOURCE)
        self.assertIn("const celebrationHost = options.celebrationHost", ONBOARDING_TASKS_SOURCE)
        self.assertIn("mountCelebrationRoot();", ONBOARDING_TASKS_SOURCE)
        self.assertIn('root.classList.toggle("is-celebrating", celebrating)', ONBOARDING_TASKS_SOURCE)
        self.assertIn("pointer-events: none;", STYLE_SOURCE)
        self.assertIn("@keyframes onboardingCelebrationHalo", STYLE_SOURCE)
        self.assertIn("@media (prefers-reduced-motion: reduce)", STYLE_SOURCE)
        self.assertIn(".onboarding-celebration { animation: onboardingCelebrationFade .18s ease-out both; }", STYLE_SOURCE)
        celebration_start = STYLE_SOURCE.index("@keyframes onboardingCelebrationIn {")
        celebration_end = STYLE_SOURCE.index("@keyframes onboardingCelebrationHalo", celebration_start)
        celebration_keyframes = STYLE_SOURCE[celebration_start:celebration_end]
        self.assertIn("transform: scale(.96);", celebration_keyframes)
        self.assertIn("transform: scale(1);", celebration_keyframes)
        self.assertNotIn("translate", celebration_keyframes)

    def test_composer_controls_do_not_implicitly_submit_prompt(self):
        form_start = INDEX_SOURCE.index('<form id="chatForm"')
        form_end = INDEX_SOURCE.index("</form>", form_start)
        buttons = re.findall(r"<button\b[^>]*>", INDEX_SOURCE[form_start:form_end])
        self.assertTrue(buttons)
        for button in buttons:
            if 'id="sendBtn"' in button:
                self.assertIn('type="submit"', button)
            else:
                self.assertIn('type="button"', button)

    def test_agent_runtime_client_exposes_durable_run_protocol(self):
        for expected in (
            "createAgentRun",
            "getAgentRun",
            "resumeAgentRun",
            "submitAgentInput",
            "submitAgentAuthorization",
            "normalizeAgentEvent",
            "watchAgentRun",
            "cancelAgentRun",
            '"waiting_authorization",',
            "await onEvent?.(normalized.event, snapshot",
        ):
            self.assertIn(expected, RUNTIME_SOURCE)
        self.assertIn('clientRequestId = ""', RUNTIME_SOURCE)
        self.assertIn("clientRequestId,", RUNTIME_SOURCE)
        self.assertIn("agent.runtime = runtime", RUNTIME_SOURCE)
        self.assertNotIn("global." + "AgentRuntime", RUNTIME_SOURCE)
        self.assertNotIn("window." + "AgentRuntime", APP_SOURCE)
        self.assertIn("const agentRuntime = window.Code.agent.runtime;", APP_SOURCE)

    def test_agent_runtime_questionnaire_error_contract_is_machine_readable(self):
        script = f"""
global.window = {{Code: {{agent: {{}}}}}};
const requests = [];
global.fetch = async (url, options = {{}}) => {{
  requests.push({{url, body: JSON.parse(options.body || "{{}}")}});
  if (requests.length === 1) return {{
    ok: false,
    status: 409,
    async json() {{ return {{
      error: "opaque server message",
      errorCode: "agent_run_input_inactive",
      agentRunId: "run-1",
      agentRunStatus: "cancelled",
      pendingInputRequestId: "request-1",
      retryable: false,
    }}; }},
  }};
  return {{ok: true, status: 200, async json() {{ return {{ok: true}}; }}}};
}};
eval({json.dumps(RUNTIME_SOURCE)});
(async () => {{
  let rejected = null;
  try {{
    await window.Code.agent.runtime.submitAgentInput("run-1", {{
      requestId: "request-1",
      answers: [{{id: "url", status: "resolved", text: "你帮我找"}}],
    }});
  }} catch (error) {{
    rejected = {{
      httpStatus: error.status,
      errorCode: error.errorCode,
      agentRunId: error.agentRunId,
      agentRunStatus: error.agentRunStatus,
      pendingInputRequestId: error.pendingInputRequestId,
      retryable: error.retryable,
    }};
  }}
  await window.Code.agent.runtime.submitAgentInput("run-1", {{answers: []}});
  process.stdout.write(JSON.stringify({{requests, rejected}}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["requests"][0]["body"], {
            "answers": [{"id": "url", "status": "resolved", "text": "你帮我找"}],
            "requestId": "request-1",
        })
        self.assertEqual(data["requests"][1]["body"], {"answers": []})
        self.assertEqual(data["rejected"], {
            "httpStatus": 409,
            "errorCode": "agent_run_input_inactive",
            "agentRunId": "run-1",
            "agentRunStatus": "cancelled",
            "pendingInputRequestId": "request-1",
            "retryable": False,
        })

    def test_agent_runtime_registers_only_inside_code_namespace(self):
        script = f"""
const source = {json.dumps(RUNTIME_SOURCE)};
global.window = {{}};
let missingNamespaceError = "";
try {{ eval(source); }} catch (error) {{ missingNamespaceError = error.message; }}
global.window = {{Code: {{agent: {{}}}}}};
eval(source);
process.stdout.write(JSON.stringify({{
  missingNamespaceError,
  registered: typeof window.Code.agent.runtime?.watchAgentRun === "function",
  hasTopLevelRuntime: Object.prototype.hasOwnProperty.call(window, "AgentRuntime"),
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(
            data["missingNamespaceError"],
            "Code agent namespace must load before agent runtime",
        )
        self.assertTrue(data["registered"])
        self.assertFalse(data["hasTopLevelRuntime"])

    def test_agent_runtime_watcher_projects_events_sequentially_and_resumes_cursor(self):
        script = f"""
global.window = {{Code: {{agent: {{}}}}}};
const source = {json.dumps(RUNTIME_SOURCE)};
const urls = [];
const snapshots = [
  {{status: "running", events: [
    {{seq: 1, type: "created"}},
    {{protocolVersion: 1, seq: 2, type: "model_started", data: {{}}}},
    {{protocolVersion: 3, seq: 3, type: "future_event", data: {{future: true}}}},
    {{protocolVersion: 1, seq: 4, type: "", data: {{}}}},
  ]}},
  {{status: "completed", events: [{{seq: 5, type: "completed"}}], result: {{content: "ok"}}}},
];
global.fetch = async (url) => {{
  urls.push(String(url));
  return new Response(JSON.stringify(snapshots.shift()), {{
    status: 200,
    headers: {{"Content-Type": "application/json"}},
  }});
}};
eval(source);
const order = [];
const versions = [];
(async () => {{
  const result = await window.Code.agent.runtime.watchAgentRun({{
    agentRunId: "agent-1",
    onEvent: async (event) => {{
      order.push(`start-${{event.seq}}`);
      versions.push([event.seq, event.protocolVersion, event.type]);
      await new Promise((resolve) => setTimeout(resolve, 1));
      order.push(`end-${{event.seq}}`);
    }},
  }});
  process.stdout.write(JSON.stringify({{urls, order, versions, cursor: result.nextCursor, status: result.status}}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertIn("cursor=0", data["urls"][0])
        self.assertIn("cursor=4", data["urls"][1])
        self.assertEqual(
            data["order"],
            [
                "start-1", "end-1",
                "start-2", "end-2",
                "start-3", "end-3",
                "start-5", "end-5",
            ],
        )
        self.assertEqual(
            data["versions"],
            [
                [1, 1, "created"],
                [2, 1, "model_started"],
                [3, 1, "future_event"],
                [5, 1, "completed"],
            ],
        )
        self.assertEqual(data["cursor"], 5)
        self.assertEqual(data["status"], "completed")

    def test_agent_runtime_normalizes_legacy_v1_future_and_malformed_events(self):
        script = f"""
global.window = {{Code: {{agent: {{}}}}}};
const source = {json.dumps(RUNTIME_SOURCE)};
eval(source);
const normalize = window.Code.agent.runtime.normalizeAgentEvent;
const events = [
  {{seq: 1, type: "created", data: {{model: "fixture"}}, createdAt: "2030-01-01T00:00:00Z"}},
  {{protocolVersion: 1, seq: 2, type: "completed", data: {{}}, createdAt: "2030-01-01T00:00:01Z", ignored: true}},
  {{protocolVersion: 4, seq: 3, type: "future_event", data: {{future: true}}, createdAt: "2030-01-01T00:00:02Z"}},
  {{protocolVersion: 1, seq: 4, type: "tool_started", data: ["invalid"], createdAt: "2030-01-01T00:00:03Z"}},
  {{protocolVersion: 1, seq: 5, type: "", data: {{}}, createdAt: "2030-01-01T00:00:04Z"}},
];
process.stdout.write(JSON.stringify(events.map((event) => normalize(event))));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        legacy, current, future, invalid_data, invalid_type = json.loads(
            completed.stdout
        )
        self.assertEqual(legacy["sourceProtocolVersion"], 0)
        self.assertEqual(legacy["event"]["protocolVersion"], 1)
        self.assertIn("legacy_unversioned_event", legacy["diagnostics"])
        self.assertEqual(current["sourceProtocolVersion"], 1)
        self.assertNotIn("ignored", current["event"])
        self.assertEqual(future["sourceProtocolVersion"], 4)
        self.assertEqual(future["event"]["type"], "future_event")
        self.assertIn("future_protocol_version", future["diagnostics"])
        self.assertEqual(invalid_data["event"]["data"], {})
        self.assertIn("invalid_event_data", invalid_data["diagnostics"])
        self.assertIsNone(invalid_type["event"])
        self.assertEqual(invalid_type["seq"], 5)
        self.assertIn("invalid_event_type", invalid_type["diagnostics"])

    def test_agent_runtime_smooths_large_text_delta_without_changing_content(self):
        script = f"""
global.window = {{Code: {{agent: {{}}}}}};
const source = {json.dumps(RUNTIME_SOURCE)};
const original = "x".repeat(145);
let fetchCount = 0;
global.fetch = async (url) => {{
  fetchCount += 1;
  if (String(url) === "/api/runtime/runs") {{
    return new Response(JSON.stringify({{runId: "runtime-1"}}), {{
      status: 201,
      headers: {{"Content-Type": "application/json"}},
    }});
  }}
  const frame = {{
    choices: [{{delta: {{content: original}}, finish_reason: "stop"}}],
    usage: {{completion_tokens: 40}},
  }};
  return new Response(JSON.stringify({{
    status: "completed",
    events: [
      {{seq: 1, data: JSON.stringify(frame)}},
      {{seq: 2, data: "[DONE]"}},
    ],
  }}), {{
    status: 200,
    headers: {{"Content-Type": "application/json"}},
  }});
}};
eval(source);
(async () => {{
  const response = await window.Code.agent.runtime.openSseResponse({{
    sessionId: "session-1",
    payload: {{model: "claude-test", messages: [{{role: "user", content: "hi"}}]}},
    keys: ["key"],
  }});
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const dataFrames = [];
  while (true) {{
    const packet = await reader.read();
    if (packet.done) break;
    const text = decoder.decode(packet.value);
    for (const line of text.split(/\\r?\\n/)) {{
      if (line.startsWith("data: ")) dataFrames.push(line.slice(6));
    }}
  }}
  const jsonFrames = dataFrames.filter((item) => item !== "[DONE]").map(JSON.parse);
  const contentParts = jsonFrames.map((item) => item.choices[0].delta.content);
  process.stdout.write(JSON.stringify({{
    fetchCount,
    frameCount: jsonFrames.length,
    maxChunk: Math.max(...contentParts.map((item) => Array.from(item).length)),
    content: contentParts.join(""),
    finishReasons: jsonFrames.map((item) => item.choices[0].finish_reason || ""),
    usageFrames: jsonFrames.filter((item) => item.usage).length,
    doneCount: dataFrames.filter((item) => item === "[DONE]").length,
  }}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["fetchCount"], 2)
        self.assertGreater(data["frameCount"], 1)
        self.assertLessEqual(data["maxChunk"], 48)
        self.assertEqual(data["content"], "x" * 145)
        self.assertEqual(data["finishReasons"][-1], "stop")
        self.assertEqual(data["finishReasons"][:-1], [""] * (data["frameCount"] - 1))
        self.assertEqual(data["usageFrames"], 1)
        self.assertEqual(data["doneCount"], 1)

    def test_agent_runtime_catchup_seed_does_not_reanimate_historical_backlog(self):
        script = f"""
global.window = {{Code: {{agent: {{}}}}}};
const source = {json.dumps(RUNTIME_SOURCE)};
const progress = [];
global.fetch = async () => {{
  const events = Array.from({{length: 120}}, (_, index) => ({{
    seq: index + 1,
    data: JSON.stringify({{choices: [{{delta: {{content: "x"}}}}]}}),
  }}));
  events.push({{seq: 121, data: "[DONE]"}});
  return new Response(JSON.stringify({{
    status: "completed",
    events,
    nextCursor: 121,
    result: {{
      content: "x".repeat(120),
      reasoning: "",
      toolCalls: [],
      finishReason: "stop",
      usage: {{prompt_tokens: 8, completion_tokens: 4, total_tokens: 12}},
    }},
  }}), {{status: 200, headers: {{"Content-Type": "application/json"}}}});
}};
eval(source);
(async () => {{
  const startedAt = Date.now();
  const response = await window.Code.agent.runtime.openSseResponse({{
    runId: "runtime-existing",
    onStreamProgress: (sample) => progress.push(sample),
  }});
  const reader = response.body.getReader();
  let text = "";
  while (true) {{
    const packet = await reader.read();
    if (packet.done) break;
    text += new TextDecoder().decode(packet.value);
  }}
  process.stdout.write(JSON.stringify({{
    elapsedMs: Date.now() - startedAt,
    phases: progress.map((item) => item.phase),
    firstBatchEventCount: progress.find((item) => item.phase === "first-delta")?.pendingEventCount || 0,
    frameCount: (text.match(/data: /g) || []).length,
    content: text.split(/\\r?\\n/)
      .filter((line) => line.startsWith("data: {{"))
      .map((line) => JSON.parse(line.slice(6)).choices?.[0]?.delta?.content || "")
      .join(""),
    diagnostic: window.Code.agent.runtime.streamDiagnostics.snapshot(),
  }}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["phases"], ["poll-started", "first-delta", "completed"])
        self.assertEqual(data["firstBatchEventCount"], 0)
        self.assertEqual(data["frameCount"], 2)
        self.assertEqual(data["content"], "x" * 120)
        self.assertEqual(data["diagnostic"]["status"], "completed")
        self.assertEqual(data["diagnostic"]["runtimeRunId"], "runtime-existing")
        self.assertEqual(data["diagnostic"]["firstBatchEventCount"], 0)
        self.assertTrue(data["diagnostic"]["catchUpSeeded"])
        self.assertEqual(data["diagnostic"]["catchUpCursor"], 121)
        self.assertEqual(data["diagnostic"]["batchCount"], 0)
        self.assertEqual(data["diagnostic"]["eventCount"], 0)
        self.assertEqual(data["diagnostic"]["maxBatchEventCount"], 0)
        self.assertEqual(data["diagnostic"]["contentFrameCount"], 1)
        self.assertEqual(data["diagnostic"]["contentChars"], 120)
        self.assertEqual(data["diagnostic"]["reasoningFrameCount"], 0)
        self.assertEqual(data["diagnostic"]["reasoningChars"], 0)
        self.assertGreaterEqual(
            data["diagnostic"]["firstContentAt"],
            data["diagnostic"]["firstDeltaAt"],
        )
        self.assertGreaterEqual(
            data["diagnostic"]["lastContentAt"],
            data["diagnostic"]["firstContentAt"],
        )
        self.assertGreaterEqual(
            data["diagnostic"]["firstDeltaAt"],
            data["diagnostic"]["pollStartedAt"],
        )

    def test_agent_runtime_sends_background_idempotency_key(self):
        script = f"""
global.window = {{Code: {{agent: {{}}}}}};
const source = {json.dumps(RUNTIME_SOURCE)};
let captured = null;
global.fetch = async (url, options) => {{
  captured = {{url: String(url), body: JSON.parse(options.body)}};
  return new Response(JSON.stringify({{agentRunId: "agent-1", status: "model"}}), {{
    status: 201,
    headers: {{"Content-Type": "application/json"}},
  }});
}};
eval(source);
(async () => {{
  await window.Code.agent.runtime.createAgentRun({{
    sessionId: "session-1",
    clientRequestId: "background-123",
    payload: {{model: "test-model", messages: [{{role: "user", content: "hi"}}]}},
    keys: [],
    toolBudgets: [{{name: "reading", tools: ["read_file"], limit: 4}}],
    contextLimit: 128000,
  }});
  process.stdout.write(JSON.stringify(captured));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["url"], "/api/agent/runs")
        self.assertEqual(data["body"]["clientRequestId"], "background-123")
        self.assertEqual(data["body"]["toolBudgets"][0]["limit"], 4)
        self.assertEqual(data["body"]["contextLimit"], 128000)

    def test_server_agent_questionnaire_uses_durable_submit_and_reload_path(self):
        self.assertIn('name: "request_user_input"', TOOLS_SOURCE)
        self.assertIn("const skillAllowedToolNames = applySkillTaskPolicy(", APP_SOURCE)
        self.assertIn("const serverTools = getNativeTools(ctx.toolPreset, skillAllowedToolNames)", APP_SOURCE)
        self.assertIn('if (snapshot.status === "waiting_user_input")', APP_SOURCE)
        self.assertIn("await requestServerAgentInput(ctx, snapshot.pendingInput)", APP_SOURCE)
        self.assertIn("agentRuntime.submitAgentInput(request.agentRunId", APP_SOURCE)
        self.assertIn('status: nextStatus', APP_SOURCE)
        self.assertIn('const nextStatus = resolver ? "running" : "resuming"', APP_SOURCE)
        self.assertIn('agentRunId: String(tool._agentRunId || "")', APP_SOURCE)
        self.assertIn("userInputRequest: serializeUserInputRequest(request)", APP_SOURCE)

    def test_server_agent_loop_state_matrix_and_side_effects_stay_in_app(self):
        loop_start = APP_SOURCE.index("async function runServerAgentLoop(ctx)")
        loop_end = APP_SOURCE.index("async function executeRunContext(ctx)", loop_start)
        loop_source = APP_SOURCE[loop_start:loop_end]

        ordered_steps = (
            "let snapshot = await agentRuntime.getAgentRun",
            'if (snapshot.status === "waiting_credentials") {',
            "await agentRuntime.resumeAgentRun",
            "snapshot = await agentRuntime.watchAgentRun",
            "ctx.agentEventCursor = Number(",
            'if (snapshot.status === "waiting_credentials") continue;',
            'if (snapshot.status === "waiting_user_input") {',
            "await requestServerAgentInput(ctx, snapshot.pendingInput)",
            'if (snapshot.status === "waiting_authorization") {',
            "await requestServerAgentAuthorization(ctx, snapshot.pendingAuthorization)",
            'if (snapshot.status === "completed") {',
            'if (snapshot.status === "cancelled") {',
            'throw new DOMException("Aborted", "AbortError");',
            "const err = new Error(snapshot.error || `Server Agent ${snapshot.status}`)",
        )
        positions = [loop_source.index(step) for step in ordered_steps]
        self.assertEqual(positions, sorted(positions))
        cancelled_start = loop_source.index('if (snapshot.status === "cancelled") {')
        cancelled_end = loop_source.index("const err = new Error", cancelled_start)
        cancelled = loop_source[cancelled_start:cancelled_end]
        self.assertIn("clearObservedAgentRun(ctx);", cancelled)
        self.assertLess(
            cancelled.index("clearObservedAgentRun(ctx);"),
            cancelled.index('throw new DOMException("Aborted", "AbortError");'),
        )

        for expected in (
            "await buildModelRequestPayload(ctx, true, serverTools)",
            "await agentRuntime.createAgentRun",
            "await persistRunCheckpoint(ctx, \"running\", \"model\"",
            "onEvent: (event, observedSnapshot) => projectAgentEvent(ctx, event, observedSnapshot)",
            "onSnapshot: (observedSnapshot) => observeAgentProjectionSnapshot(ctx, observedSnapshot)",
            "ctx.run.recovery = {",
            "ctx.run.agentEventCursor = ctx.agentEventCursor",
            "clearObservedAgentRun(ctx)",
            "err.status = snapshot.status",
            "err.errorCode = snapshot.errorCode || \"\"",
            'if (err.errorCode === "model_access_denied")',
            "await refreshModels()",
        ):
            self.assertIn(expected, loop_source)

        self.assertFalse((ROOT / "src" / "agent" / "agent-loop.js").exists())
        self.assertNotIn("./src/agent/agent-loop.js", INDEX_SOURCE)

    def test_goal_continuation_switches_agent_runs_without_exposing_reasoning_or_rolling_back(self):
        loop_start = APP_SOURCE.index("async function runServerAgentLoop(ctx)")
        loop_end = APP_SOURCE.index("async function executeRunContext(ctx)", loop_start)
        loop_source = APP_SOURCE[loop_start:loop_end]
        send_start = APP_SOURCE.index("async function sendMessage(userText, options = {})")
        send_end = APP_SOURCE.index("function getSelectedModel()", send_start)
        send_source = APP_SOURCE[send_start:send_end]
        stream_start = APP_SOURCE.index("async function _callModelOnceAttempt(")
        stream_end = APP_SOURCE.index("function _safeMd", stream_start)
        stream_source = APP_SOURCE[stream_start:stream_end]
        completed_start = APP_SOURCE.index("function projectAgentModelCompleted")
        completed_end = APP_SOURCE.index("function findAgentCompactionProjection", completed_start)
        completed_source = APP_SOURCE[completed_start:completed_end]

        for expected in (
            "const continuation = snapshot?.result?.continuation",
            "ctx.agentRunId = String(continuation.agentRunId)",
            "ctx.agentEventCursor = 0",
            "continuationIndex: Number(continuation.index || 0)",
            "continue;",
        ):
            self.assertIn(expected, loop_source)
        self.assertLess(
            loop_source.index("const continuation = snapshot?.result?.continuation"),
            loop_source.index('if (snapshot.status === "completed") {'),
        )
        self.assertIn("snapshot.goalOperationsEnabled", loop_source)
        self.assertIn("err.preservePublicProcess", loop_source)
        self.assertIn("!loopError?.preservePublicProcess", send_source)
        self.assertIn("const serverOwnedProjection = isServerOwnedRun(ctx)", stream_source)
        self.assertIn("const visibleFinalText = serverOwnedProjection", stream_source)
        self.assertIn("const visibleTurnText = serverOwnedProjection", stream_source)
        self.assertIn("? String(turnEvent.rawContent || \"\")", stream_source)
        self.assertIn('const projectedContent = { thought: "", content:', completed_source)
        self.assertNotIn("data.reasoning", completed_source)

    def test_projection_shadow_is_feature_gated_and_observes_all_run_boundaries(self):
        background_start = APP_SOURCE.index("async function runBackgroundSubAgentJob(job)")
        background_end = APP_SOURCE.index("function pumpBackgroundDispatcher()", background_start)
        background = APP_SOURCE[background_start:background_end]
        foreground_start = APP_SOURCE.index("async function runServerAgentLoop(ctx)")
        foreground_end = APP_SOURCE.index("async function executeRunContext(ctx)", foreground_start)
        foreground = APP_SOURCE[foreground_start:foreground_end]

        self.assertIn("let _agentProjectionShadowEnabled = false", APP_SOURCE)
        self.assertIn("setAgentProjectionShadowEnabled(data.agentProjectionShadow === true)", APP_SOURCE)
        self.assertIn("if (!_agentProjectionShadowEnabled", APP_SOURCE)
        self.assertIn("onEvent: (event) => observeAgentProjectionEvent(subCtx, event)", background)
        self.assertIn(
            "onSnapshot: (observedSnapshot) => observeAgentProjectionSnapshot(subCtx, observedSnapshot)",
            background,
        )
        self.assertIn("archiveAgentProjectionShadow(subCtx)", background)
        self.assertIn(
            "onEvent: (event, observedSnapshot) => projectAgentEvent(ctx, event, observedSnapshot)",
            foreground,
        )
        self.assertIn(
            "onSnapshot: (observedSnapshot) => observeAgentProjectionSnapshot(ctx, observedSnapshot)",
            foreground,
        )
        self.assertIn("beginAgentProjectionEvent(ctx, projectionEvent, projectionReferenceTime)", APP_SOURCE)
        self.assertIn("completeAgentProjectionEvent(ctx, projectionEvent, projectionReferenceTime)", APP_SOURCE)
        self.assertIn("archiveAgentProjectionShadow(ctx)", APP_SOURCE)
        self.assertIn("_agentProjectionShadowSummaries: []", STATE_SOURCE)
        self.assertIn("projectionShadowDiagnostics = Object.freeze", APP_SOURCE)
        self.assertIn("snapshot: snapshotAgentProjectionShadowDiagnostics", APP_SOURCE)
        self.assertIn(
            "_agentProjectionShadowEnabled ? state._agentProjectionShadowSummaries : []",
            APP_SOURCE,
        )
        self.assertIn("createProjectionShadowReport", SHADOW_SOURCE)
        self.assertIn("DEFAULT_MAX_SUMMARIES", SHADOW_SOURCE)

    def test_agent_questionnaire_normalizes_and_serializes_without_side_effects(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/questionnaire.js");

const questionnaire = window.Code.agent.questionnaire;
const source = [
  {
    prompt: "  Pick a target  ",
    type: "unknown",
    required: false,
    allowOther: 1,
    options: [
      {},
      {value: "api"},
      {label: "Second"},
      {value: "four"},
      {value: "five"},
      {value: "six"},
      {value: "seven"},
      {value: "eight"},
      {value: "ignored"},
    ],
  },
  {id: "details", prompt: " Explain ", type: "text", options: [{value: "ignored"}]},
  {prompt: "   ", type: "text"},
  {prompt: "sliced out", type: "text"},
];
const sourceBefore = JSON.stringify(source);
const questions = questionnaire.normalizeUserInputQuestions(source);
const request = {
  id: "request-1",
  questions,
  nested: {value: 1},
  abortSignal: {aborted: false},
  abortHandler: "handler",
  _finishing: true,
};
const serialized = questionnaire.serializeUserInputRequest(request);
serialized.nested.value = 2;

process.stdout.write(JSON.stringify({
  frozen: Object.isFrozen(questionnaire),
  sourceUnchanged: JSON.stringify(source) === sourceBefore,
  questions,
  serialized,
  requestNestedValue: request.nested.value,
  nullRequest: questionnaire.serializeUserInputRequest(null),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["frozen"])
        self.assertTrue(data["sourceUnchanged"])
        self.assertEqual(len(data["questions"]), 2)
        first, second = data["questions"]
        self.assertEqual(first["id"], "question_1")
        self.assertEqual(first["prompt"], "Pick a target")
        self.assertEqual(first["type"], "single")
        self.assertFalse(first["required"])
        self.assertTrue(first["allowOther"])
        self.assertEqual(len(first["options"]), 8)
        self.assertEqual(first["options"][:3], [
            {"value": "option_1", "label": "1", "description": ""},
            {"value": "api", "label": "api", "description": ""},
            {"value": "option_3", "label": "Second", "description": ""},
        ])
        self.assertEqual(first["status"], "pending")
        self.assertEqual(first["selected"], [])
        self.assertEqual(first["text"], "")
        self.assertEqual(first["other"], "")
        self.assertIsNone(first["answer"])
        self.assertEqual(second["id"], "details")
        self.assertEqual(second["prompt"], "Explain")
        self.assertEqual(second["type"], "text")
        self.assertEqual(second["options"], [])
        self.assertNotIn("abortSignal", data["serialized"])
        self.assertNotIn("abortHandler", data["serialized"])
        self.assertNotIn("_finishing", data["serialized"])
        self.assertEqual(data["serialized"]["nested"]["value"], 2)
        self.assertEqual(data["requestNestedValue"], 1)
        self.assertIsNone(data["nullRequest"])

        for function_name in ("normalizeUserInputQuestions", "serializeUserInputRequest"):
            self.assertIn(f"function {function_name}(", QUESTIONNAIRE_SOURCE)
            self.assertNotIn(f"function {function_name}(", APP_SOURCE)
        self.assertIn("} = window.Code.agent.questionnaire;", APP_SOURCE)
        self.assertIn("normalizeUserInputQuestions(tool.questions)", APP_SOURCE)

    def test_agent_questionnaire_builds_stable_localized_results(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/questionnaire.js");

const questionnaire = window.Code.agent.questionnaire;
const request = {
  id: "request-2",
  title: "Choose",
  questions: [
    {id: "text", prompt: "Text", type: "text", status: "resolved", text: "  hello  ", other: ""},
    {
      id: "choice",
      prompt: "Choice",
      type: "multiple",
      status: "resolved",
      selected: ["api", "unknown"],
      options: [{value: "api", label: "API"}],
      other: "  custom  ",
    },
    {
      id: "skip",
      prompt: "Skip",
      type: "single",
      status: "canceled",
      selected: [],
      options: [{value: "later", label: "Later"}],
      other: "  later  ",
    },
    {id: "empty", prompt: "Empty", type: "text", status: "resolved", text: "   ", other: ""},
    {
      id: "skip-empty",
      prompt: "Skip empty",
      type: "single",
      status: "canceled",
      selected: [],
      options: [{value: "later", label: "Later"}],
      other: "",
    },
  ],
};
const requestBefore = JSON.stringify(request);
const result = questionnaire.buildUserInputResult(request, "Skipped");
const payload = JSON.parse(JSON.stringify(result));
const selectedValues = [...result.answers[1].values];
result.answers[1].values.push("mutated");

process.stdout.write(JSON.stringify({
  answerTexts: result.answers.map((answer) => answer.answer),
  otherValues: result.answers.map((answer) => answer.other),
  selectedValues,
  requestUnchanged: JSON.stringify(request) === requestBefore,
  sourceSelected: request.questions[1].selected,
  summary: result.summary,
  resultHeader: {
    ok: result.ok,
    action: result.action,
    requestId: result.requestId,
    title: result.title,
  },
  ownProperties: result.answers.map((answer) => ({
    values: Object.prototype.hasOwnProperty.call(answer, "values"),
    text: Object.prototype.hasOwnProperty.call(answer, "text"),
  })),
  payloadKeys: payload.answers.map((answer) => Object.keys(answer)),
  nullAnswer: questionnaire.userInputAnswerText(null, "Skipped"),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["resultHeader"], {
            "ok": True,
            "action": "request_user_input",
            "requestId": "request-2",
            "title": "Choose",
        })
        self.assertEqual(data["answerTexts"], [
            "hello",
            "API、unknown、  custom  ",
            "Skipped：  later  ",
            "",
            "Skipped",
        ])
        self.assertEqual(data["otherValues"], ["", "custom", "later", "", ""])
        self.assertEqual(data["selectedValues"], ["api", "unknown"])
        self.assertTrue(data["requestUnchanged"])
        self.assertEqual(data["sourceSelected"], ["api", "unknown"])
        self.assertEqual(
            data["summary"],
            "Text：hello\nChoice：API、unknown、  custom  \n"
            "Skip：Skipped：  later  \nEmpty：Skipped\nSkip empty：Skipped",
        )
        self.assertTrue(all(item == {"values": True, "text": True} for item in data["ownProperties"]))
        self.assertNotIn("values", data["payloadKeys"][0])
        self.assertIn("text", data["payloadKeys"][0])
        self.assertIn("values", data["payloadKeys"][1])
        self.assertNotIn("text", data["payloadKeys"][1])
        self.assertEqual(data["nullAnswer"], "")

        self.assertIn("function userInputAnswerText(", QUESTIONNAIRE_SOURCE)
        self.assertIn("function buildUserInputResult(", QUESTIONNAIRE_SOURCE)
        self.assertNotIn("function userInputAnswerText(", APP_SOURCE)
        self.assertIn("buildUserInputResult: buildUserInputResultData", APP_SOURCE)
        self.assertIn('return buildUserInputResultData(request, t("questionCanceled"));', APP_SOURCE)
        self.assertNotIn("const answers = request.questions.map", APP_SOURCE)

    def test_questionnaire_side_effects_and_legacy_reload_stay_in_app(self):
        start = APP_SOURCE.index("function normalizeUserInputRequest(")
        end = APP_SOURCE.index("async function resumePersistedRuns()", start)
        source = APP_SOURCE[start:end]

        for expected in (
            "function getUserInputRequest(",
            "function restoreUserInputRequest(",
            "function classifyAgentUserInputState(",
            "async function invalidateServerUserInputRequest(",
            "async function reconcilePersistedUserInputRequest(",
            "if (current?.id === savedRequest.id) return current;",
            "const restored = JSON.parse(JSON.stringify(savedRequest));",
            "async function requestUserInput(",
            "if (ctx?.isSubAgent)",
            "async function finishServerAgentUserInputRequest(",
            "agentRuntime.submitAgentInput(request.agentRunId",
            "if (request.agentRunId) return finishServerAgentUserInputRequest(request);",
            'role: "tool-result"',
            "resumedFromUserInput: true",
            "resumePersistedSessionRun(summary).catch",
            "function renderUserInputPanel(",
            "async function persistUserInputProgress(",
            "async function resolveUserInputQuestion(",
            "function bindUserInputPanel(",
        ):
            self.assertIn(expected, source)

        self.assertEqual(APP_SOURCE.count("requestUserInput("), 2)
        self.assertIn("await requestServerAgentInput(ctx, snapshot.pendingInput)", APP_SOURCE)
        self.assertIn("_agentRunId: ctx.agentRunId", APP_SOURCE)
        self.assertIn("await reconcilePersistedUserInputRequest(", APP_SOURCE)
        self.assertIn("requestId: request.id", APP_SOURCE)
        self.assertNotIn("Agent run is not waiting for user input", APP_SOURCE)

        navigation_start = SESSIONS_SOURCE.index("function createSessionNavigation(")
        navigation_end = SESSIONS_SOURCE.index("function createSessionStartup(", navigation_start)
        navigation_source = SESSIONS_SOURCE[navigation_start:navigation_end]
        set_run_state = navigation_source.index(
            "setSessionRunState(session.id, session.runState || getSessionRunState(session.id));"
        )
        reconcile_request = navigation_source.index(
            "await recovery.reconcilePersistedUserInputRequest("
        )
        restore_authorization = navigation_source.index(
            "recovery.restoreAuthorizationRequest(session.id, session.runState?.authorizationRequest);"
        )
        render_messages = navigation_source.index("view.renderMessages();", restore_authorization)
        self.assertLess(set_run_state, reconcile_request)
        self.assertLess(reconcile_request, restore_authorization)
        self.assertLess(restore_authorization, render_messages)
        navigation_wiring_start = APP_SOURCE.index("const sessionNavigation = createSessionNavigation({")
        navigation_wiring_end = APP_SOURCE.index("const {", navigation_wiring_start)
        self.assertIn(
            "reconcilePersistedUserInputRequest,",
            APP_SOURCE[navigation_wiring_start:navigation_wiring_end],
        )

        terminal_start = source.index("function terminalQuestionnaireRunState(")
        invalidate_start = source.index("async function invalidateServerUserInputRequest(")
        invalidate_end = source.index("async function reconcilePersistedUserInputRequest(", invalidate_start)
        terminal_source = source[terminal_start:invalidate_start]
        invalidate_source = source[invalidate_start:invalidate_end]
        self.assertIn("userInputRequest: null", terminal_source)
        self.assertIn("{ persistMessages: false }", invalidate_source)
        self.assertNotIn("appendUserInputSummary", invalidate_source)
        self.assertNotIn("resumePersistedSessionRun", invalidate_source)
        self.assertNotIn('role: "tool-result"', invalidate_source)

        for key in (
            "questionnaireRunEnded",
            "questionnaireStatusUnavailable",
            "questionnaireRetry",
        ):
            self.assertEqual(I18N_SOURCE.count(f"{key}:"), 2)

        for forbidden in (
            "state.",
            "agentRuntime",
            "saveSessionState",
            "renderUserInputPanel",
            ".innerHTML",
            "addEventListener",
            "_notify(",
            "resumePersistedSessionRun",
        ):
            self.assertNotIn(forbidden, QUESTIONNAIRE_SOURCE)

    def test_questionnaire_reconciliation_is_authoritative_and_retryable(self):
        start = APP_SOURCE.index("const AUTHORITATIVE_AGENT_INPUT_ERROR_CODES")
        end = APP_SOURCE.index("function buildUserInputResult(", start)
        source = APP_SOURCE[start:end]
        script = f"""
{source}
const request = {{id: "request-1", agentRunId: "run-1"}};
const retryRequest = {{...request}};
setUserInputReconcileRetry(retryRequest, true);
process.stdout.write(JSON.stringify({{
  matched: classifyAgentUserInputState(request, {{
    status: "waiting_user_input",
    pendingInput: {{requestId: "request-1"}},
  }}),
  completed: classifyAgentUserInputState(request, {{status: "completed"}}),
  cancelled: classifyAgentUserInputState(request, {{status: "cancelled"}}),
  mismatched: classifyAgentUserInputState(request, {{
    status: "waiting_user_input",
    pendingInput: {{requestId: "request-2"}},
  }}),
  notFound: classifyAgentUserInputState(request, null, {{status: 404}}),
  transient: classifyAgentUserInputState(request, null, {{status: 503}}),
  invalidSnapshot: classifyAgentUserInputState(request, {{}}),
  inactive: classifyAgentUserInputState(request, null, {{
    status: 409,
    errorCode: "agent_run_input_inactive",
    agentRunStatus: "failed",
  }}),
  retrySerialized: JSON.stringify(retryRequest),
  completedState: terminalQuestionnaireRunState({{
    status: "waiting-user-input",
    userInputRequest: {{id: "request-1"}},
    backgroundRuns: [{{id: "background-1"}}],
  }}, "completed"),
  cancelledState: terminalQuestionnaireRunState({{
    status: "waiting-user-input",
    userInputRequest: {{id: "request-1"}},
    agentRunId: "run-1",
  }}, "cancelled"),
  failedState: terminalQuestionnaireRunState({{
    status: "waiting-user-input",
    userInputRequest: {{id: "request-1"}},
  }}, "failed"),
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["matched"]["action"], "keep")
        self.assertEqual(data["completed"], {
            "action": "clear", "status": "completed", "reason": "terminal", "pendingRequestId": "",
        })
        self.assertEqual(data["cancelled"]["action"], "clear")
        self.assertEqual(data["mismatched"], {
            "action": "clear", "status": "waiting_user_input", "reason": "request_mismatch",
            "pendingRequestId": "request-2",
        })
        self.assertEqual(data["notFound"]["action"], "clear")
        self.assertEqual(data["transient"]["action"], "retry")
        self.assertEqual(data["invalidSnapshot"]["action"], "retry")
        self.assertEqual(data["inactive"]["status"], "failed")
        self.assertNotIn("_reconcileRetry", data["retrySerialized"])
        self.assertEqual(data["completedState"], {"backgroundRuns": [{"id": "background-1"}]})
        self.assertEqual(data["cancelledState"]["status"], "paused")
        self.assertIsNone(data["cancelledState"]["userInputRequest"])
        self.assertEqual(data["failedState"]["status"], "failed")
        self.assertIsNone(data["failedState"]["userInputRequest"])

    def test_subagent_context_and_background_prompt_are_pure_module_behaviors(self):
        script = f"""
global.window = {{}};
eval({json.dumps((ROOT / "src" / "core" / "namespace.js").read_text(encoding="utf-8"))});
eval({json.dumps(SUBAGENTS_SOURCE)});
const subagents = window.Code.agent.subagents;
const sourceTools = [
  {{type: "function", function: {{name: "read_file"}}}},
  {{type: "function", function: {{name: "task"}}}},
  {{type: "function", function: {{name: "request_user_input"}}}},
];
const parent = {{
  model: "test-model",
  cwd: "C:/project",
  primaryRoot: "C:/workspace",
  messages: [{{role: "user", content: "parent history"}}],
  stats: {{input: 9, output: 8, cache: 7}},
  _agentProjectionShadow: {{id: "parent-shadow"}},
  _agentProjectionLegacyObservation: {{id: "parent-legacy"}},
  _agentProjectionShadowArchived: true,
}};
const rawPrompt = "  inspect   project  ";
const context = subagents.createSubAgentContext({{
  parentContext: parent,
  taskPrompt: rawPrompt,
  securityLayer: "SECURITY",
  authorizationId: "sub-fixed",
  tools: sourceTools,
}});
const longTask = "x".repeat(151);
process.stdout.write(JSON.stringify({{
  exports: Object.keys(subagents).sort(),
  context: {{
    model: context.model,
    isSubAgent: context.isSubAgent,
    authorizationId: context.authorizationId,
    authorizationLabel: context.authorizationLabel,
    tools: context.tools.map((tool) => tool.function.name),
    messages: context.messages,
    stats: context.stats,
    taskUsage: context.taskUsage,
    ownsProjectionShadow: Object.prototype.hasOwnProperty.call(context, "_agentProjectionShadow"),
    ownsLegacyProjection: Object.prototype.hasOwnProperty.call(context, "_agentProjectionLegacyObservation"),
    ownsProjectionArchiveFlag: Object.prototype.hasOwnProperty.call(context, "_agentProjectionShadowArchived"),
  }},
  parentMessages: parent.messages,
  parentStats: parent.stats,
  parentProjectionShadow: parent._agentProjectionShadow,
  parentLegacyProjection: parent._agentProjectionLegacyObservation,
  parentProjectionArchiveFlag: parent._agentProjectionShadowArchived,
  sourceTools: sourceTools.map((tool) => tool.function.name),
  background: subagents.buildBackgroundTaskPrompt(longTask, "new request"),
  standalone: subagents.buildBackgroundTaskPrompt("", "new request"),
  parsed: [
    subagents.parseParallelCommand("/parallel do work"),
    subagents.parseParallelCommand("/PARALLEL  multi\\nline  "),
    subagents.parseParallelCommand("/parallel"),
    subagents.parseParallelCommand("ordinary text"),
  ],
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)

        self.assertEqual(
            data["exports"],
            [
                "BACKGROUND_JOB_TIMEOUT_MS",
                "backgroundJobElapsedMs",
                "buildBackgroundJobCheckpoint",
                "buildBackgroundResultMessage",
                "buildBackgroundTaskPrompt",
                "buildRestoredBackgroundJobData",
                "buildSubAgentSystemPrompt",
                "createSubAgentContext",
                "hasBackgroundResult",
                "mergeBackgroundUsageStats",
                "parseParallelCommand",
            ],
        )
        self.assertEqual(data["context"]["model"], "test-model")
        self.assertTrue(data["context"]["isSubAgent"])
        self.assertEqual(data["context"]["authorizationId"], "sub-fixed")
        self.assertEqual(data["context"]["authorizationLabel"], "inspect project")
        self.assertEqual(data["context"]["tools"], ["read_file"])
        self.assertEqual(data["context"]["messages"][1]["content"], "  inspect   project  ")
        self.assertIn("SECURITY", data["context"]["messages"][0]["content"])
        self.assertIn("当前工作目录：C:/project", data["context"]["messages"][0]["content"])
        self.assertIn("主文件夹：C:/workspace", data["context"]["messages"][0]["content"])
        self.assertIn("禁止再次委派子 Agent", data["context"]["messages"][0]["content"])
        self.assertIn("使用委派任务本身的语言回复", data["context"]["messages"][0]["content"])
        self.assertIn("[DECISION_POINT]", data["context"]["messages"][0]["content"])
        self.assertEqual(data["context"]["stats"], {"input": 0, "output": 0, "cache": 0})
        self.assertEqual(data["context"]["taskUsage"], {"input": 0, "output": 0, "cache": 0})
        self.assertFalse(data["context"]["ownsProjectionShadow"])
        self.assertFalse(data["context"]["ownsLegacyProjection"])
        self.assertFalse(data["context"]["ownsProjectionArchiveFlag"])
        self.assertEqual(data["parentMessages"], [{"role": "user", "content": "parent history"}])
        self.assertEqual(data["parentStats"], {"input": 9, "output": 8, "cache": 7})
        self.assertEqual(data["parentProjectionShadow"], {"id": "parent-shadow"})
        self.assertEqual(data["parentLegacyProjection"], {"id": "parent-legacy"})
        self.assertTrue(data["parentProjectionArchiveFlag"])
        self.assertEqual(data["sourceTools"], ["read_file", "task", "request_user_input"])
        self.assertIn(f"主 Agent 正在处理：{'x' * 150}", data["background"])
        self.assertNotIn("x" * 151, data["background"])
        self.assertIn("[新请求] new request", data["background"])
        self.assertEqual(data["standalone"], "new request")
        self.assertEqual(data["parsed"], ["do work", "multi\nline", "", None])

        for function_name in (
            "buildBackgroundTaskPrompt",
            "buildSubAgentSystemPrompt",
            "createSubAgentContext",
            "parseParallelCommand",
        ):
            self.assertIn(f"function {function_name}(", SUBAGENTS_SOURCE)
        self.assertNotIn("function createSubAgentContext(", APP_SOURCE)
        self.assertNotIn("function buildBackgroundTaskPrompt(", APP_SOURCE)
        self.assertNotIn("function parseParallelCommand(", APP_SOURCE)
        self.assertIn("} = window.Code.agent.subagents;", APP_SOURCE)
        self.assertIn("return createSubAgentContext({", APP_SOURCE)
        self.assertIn("buildBackgroundTaskPrompt(currentTask, userText)", APP_SOURCE)
        self.assertLess(
            FRONTEND_ENTRY_SOURCE.index('import "./agent/questionnaire.js"'),
            FRONTEND_ENTRY_SOURCE.index('import "./agent/subagents.js"'),
        )
        self.assertLess(
            FRONTEND_ENTRY_SOURCE.index('import "./agent/subagents.js"'),
            FRONTEND_ENTRY_SOURCE.index('import "./agent/model-stream.js"'),
        )
        for forbidden in (
            "state.",
            "agentRuntime",
            "saveSessionState",
            "Date.now",
            "fetch(",
            "document.",
            "renderSessionMessages",
            "setBackgroundRunCheckpoint",
            "new Promise",
            "AbortController",
            "appendSessionMessages",
            "requestServerAgentAuthorization",
            "pumpBackgroundDispatcher",
            "dispatchBackgroundSubAgent",
            "restoreBackgroundJobsForSession",
        ):
            self.assertNotIn(forbidden, SUBAGENTS_SOURCE)

    def test_background_checkpoint_timing_and_usage_are_pure_module_behaviors(self):
        script = f"""
global.window = {{}};
eval({json.dumps((ROOT / "src" / "core" / "namespace.js").read_text(encoding="utf-8"))});
eval({json.dumps(SUBAGENTS_SOURCE)});
const subagents = window.Code.agent.subagents;
const parentRoots = ["C:/workspace", "D:/shared"];
const job = {{
  id: "job-1",
  clientRequestId: "request-1",
  status: "running",
  agentRunId: 42,
  cursor: "3",
  userText: "inspect",
  taskPrompt: "",
  model: "test-model",
  permissionProfile: "plan",
  toolPreset: "full",
  thinkingLevel: "high",
  temperature: "0",
  maxTokens: "4096",
  parentCtx: {{cwd: "C:/project", primaryRoot: "C:/workspace", rootPaths: parentRoots}},
  parentTaskStartedAt: "500",
  queuedAt: "1000",
  startedAt: "1200",
  deadlineAt: "9000",
  abortController: {{hidden: true}},
  completion: "hidden",
}};
const checkpoint = subagents.buildBackgroundJobCheckpoint(job, 7000);
const checkpointRoots = [...checkpoint.rootPaths];
checkpoint.rootPaths.push("E:/mutated");
const legacy = subagents.buildBackgroundJobCheckpoint({{
  id: "legacy-job",
  status: "pending",
  userText: "legacy task",
  parentCtx: {{cwd: "C:/legacy", primaryRoot: "", rootPaths: ["C:/legacy"]}},
}}, 10000);
const currentStats = {{input: 1, output: "2", cache: 3, cost: 0.5, cacheWrite: 4, extra: "keep"}};
const childStats = {{input: "5", output: 6, cache: "7", cost: "1.5", cacheWrite: "2"}};
const merged = subagents.mergeBackgroundUsageStats(currentStats, childStats);
const withoutCacheWrite = subagents.mergeBackgroundUsageStats(currentStats, {{input: 2}});
process.stdout.write(JSON.stringify({{
  timeout: subagents.BACKGROUND_JOB_TIMEOUT_MS,
  checkpoint,
  checkpointRoots,
  parentRoots,
  legacy,
  merged,
  withoutCacheWrite,
  currentStats,
  childStats,
  elapsed: [
    subagents.backgroundJobElapsedMs({{queuedAt: 1000, startedAt: 2000}}, 5500),
    subagents.backgroundJobElapsedMs({{startedAt: 2000}}, 5500),
    subagents.backgroundJobElapsedMs({{queuedAt: 6000}}, 5500),
    subagents.backgroundJobElapsedMs(null, 5500),
  ],
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)

        self.assertEqual(data["timeout"], 600000)
        self.assertEqual(data["checkpointRoots"], ["C:/workspace", "D:/shared"])
        self.assertEqual(data["parentRoots"], ["C:/workspace", "D:/shared"])
        self.assertEqual(data["checkpoint"]["agentRunId"], "42")
        self.assertEqual(data["checkpoint"]["cursor"], 3)
        self.assertEqual(data["checkpoint"]["taskPrompt"], "inspect")
        self.assertEqual(data["checkpoint"]["temperature"], 0)
        self.assertEqual(data["checkpoint"]["maxTokens"], 4096)
        self.assertEqual(data["checkpoint"]["cwd"], "C:/project")
        self.assertEqual(data["checkpoint"]["primaryRoot"], "C:/workspace")
        self.assertEqual(data["checkpoint"]["queuedAt"], 1000)
        self.assertEqual(data["checkpoint"]["deadlineAt"], 9000)
        self.assertNotIn("abortController", data["checkpoint"])
        self.assertNotIn("completion", data["checkpoint"])

        self.assertEqual(data["legacy"]["clientRequestId"], "legacy-job")
        self.assertEqual(data["legacy"]["taskPrompt"], "legacy task")
        self.assertEqual(data["legacy"]["permissionProfile"], "read")
        self.assertEqual(data["legacy"]["toolPreset"], "default")
        self.assertEqual(data["legacy"]["thinkingLevel"], "auto")
        self.assertEqual(data["legacy"]["temperature"], 0.2)
        self.assertEqual(data["legacy"]["cwd"], "C:/legacy")
        self.assertEqual(data["legacy"]["rootPaths"], ["C:/legacy"])
        self.assertEqual(data["legacy"]["queuedAt"], 10000)
        self.assertEqual(data["legacy"]["deadlineAt"], 610000)

        self.assertEqual(data["merged"], {
            "input": 6,
            "output": 8,
            "cache": 10,
            "cost": 2,
            "cacheWrite": 6,
            "extra": "keep",
        })
        self.assertEqual(data["withoutCacheWrite"]["cacheWrite"], 4)
        self.assertEqual(data["currentStats"], {
            "input": 1,
            "output": "2",
            "cache": 3,
            "cost": 0.5,
            "cacheWrite": 4,
            "extra": "keep",
        })
        self.assertEqual(data["childStats"]["cacheWrite"], "2")
        self.assertEqual(data["elapsed"], [4500, 3500, 0, 0])

        for function_name in (
            "buildBackgroundJobCheckpoint",
            "mergeBackgroundUsageStats",
            "backgroundJobElapsedMs",
        ):
            self.assertIn(f"function {function_name}(", SUBAGENTS_SOURCE)
            self.assertNotIn(f"function {function_name}(", APP_SOURCE)
        self.assertNotIn("const BACKGROUND_JOB_TIMEOUT_MS", APP_SOURCE)
        self.assertIn("buildBackgroundJobCheckpoint(job, Date.now())", APP_SOURCE)
        self.assertIn("Object.assign(stats, mergeBackgroundUsageStats(stats, childStats));", APP_SOURCE)
        self.assertIn("formatElapsedMs(backgroundJobElapsedMs(job, finishedAt))", APP_SOURCE)

    def test_background_restore_job_data_is_pure_and_backward_compatible(self):
        script = f"""
global.window = {{}};
eval({json.dumps((ROOT / "src" / "core" / "namespace.js").read_text(encoding="utf-8"))});
eval({json.dumps(SUBAGENTS_SOURCE)});
const subagents = window.Code.agent.subagents;
const sourceRoots = ["C:/workspace", "D:/shared"];
const checkpoint = {{
  id: 77,
  clientRequestId: 88,
  status: "waiting-authorization",
  agentRunId: 99,
  cursor: "3",
  userText: "saved request",
  taskPrompt: "saved task",
  model: "saved-model",
  permissionProfile: "plan",
  toolPreset: "full",
  thinkingLevel: "high",
  temperature: "0",
  maxTokens: "2048",
  cwd: "C:/project",
  primaryRoot: "C:/workspace",
  rootPaths: sourceRoots,
  parentTaskStartedAt: "500",
  queuedAt: "1000",
  startedAt: "1200",
  deadlineAt: "9000",
  futureField: {{version: 2}},
}};
const restored = subagents.buildRestoredBackgroundJobData(checkpoint, {{
  sessionId: "session-1",
  fallbackUserText: "message fallback",
  fallbackModel: "selected-model",
  fallbackQueuedAt: 7000,
  fallbackDeadlineAt: 607000,
}});
const restoredRoots = [...restored.rootPaths];
restored.rootPaths.push("E:/mutated");
const legacyCheckpoint = {{
  id: "legacy-job",
  status: "running",
  agentRunId: "run-1",
  cursor: "4",
  futureField: "keep",
}};
const legacy = subagents.buildRestoredBackgroundJobData(legacyCheckpoint, {{
  sessionId: "legacy-session",
  fallbackUserText: "message text",
  fallbackModel: "fallback-model",
  fallbackQueuedAt: 3000,
  fallbackDeadlineAt: 603000,
}});
process.stdout.write(JSON.stringify({{
  restored,
  restoredRoots,
  checkpoint,
  sourceRoots,
  legacy,
  legacyCheckpoint,
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)

        restored = data["restored"]
        self.assertEqual(restored["id"], "77")
        self.assertEqual(restored["clientRequestId"], "88")
        self.assertEqual(restored["sessionId"], "session-1")
        self.assertEqual(restored["status"], "pending")
        self.assertTrue(restored["restored"])
        self.assertEqual(restored["agentRunId"], "99")
        self.assertEqual(restored["cursor"], 3)
        self.assertEqual(restored["userText"], "saved request")
        self.assertEqual(restored["taskPrompt"], "saved task")
        self.assertEqual(restored["model"], "saved-model")
        self.assertEqual(restored["temperature"], 0)
        self.assertEqual(restored["maxTokens"], 2048)
        self.assertEqual(restored["queuedAt"], 1000)
        self.assertEqual(restored["startedAt"], 1200)
        self.assertEqual(restored["deadlineAt"], 9000)
        self.assertEqual(restored["futureField"], {"version": 2})
        self.assertEqual(data["restoredRoots"], ["C:/workspace", "D:/shared"])
        self.assertEqual(data["sourceRoots"], ["C:/workspace", "D:/shared"])
        self.assertEqual(data["checkpoint"]["status"], "waiting-authorization")
        self.assertEqual(data["checkpoint"]["id"], 77)

        legacy = data["legacy"]
        self.assertEqual(legacy["id"], "legacy-job")
        self.assertEqual(legacy["clientRequestId"], "legacy-job")
        self.assertEqual(legacy["sessionId"], "legacy-session")
        self.assertEqual(legacy["status"], "pending")
        self.assertTrue(legacy["restored"])
        self.assertEqual(legacy["agentRunId"], "run-1")
        self.assertEqual(legacy["cursor"], 4)
        self.assertEqual(legacy["userText"], "message text")
        self.assertEqual(legacy["taskPrompt"], "message text")
        self.assertEqual(legacy["model"], "fallback-model")
        self.assertEqual(legacy["permissionProfile"], "read")
        self.assertEqual(legacy["toolPreset"], "default")
        self.assertEqual(legacy["thinkingLevel"], "auto")
        self.assertEqual(legacy["temperature"], 0.2)
        self.assertEqual(legacy["queuedAt"], 3000)
        self.assertEqual(legacy["deadlineAt"], 603000)
        self.assertEqual(legacy["futureField"], "keep")
        self.assertEqual(data["legacyCheckpoint"]["status"], "running")
        for runtime_field in ("parentCtx", "userMessage", "completion", "resolve"):
            self.assertNotIn(runtime_field, legacy)

        self.assertIn("function buildRestoredBackgroundJobData(", SUBAGENTS_SOURCE)
        self.assertNotIn("function buildRestoredBackgroundJobData(", APP_SOURCE)
        self.assertIn("buildRestoredBackgroundJobData(checkpoint, {", APP_SOURCE)
        self.assertIn("...restoredJobData,", APP_SOURCE)

    def test_background_result_projection_and_deduplication_are_pure(self):
        script = f"""
global.window = {{}};
require("./src/core/namespace.js");
require("./src/services/persistence.js");
require("./src/ui/messages.js");
require("./src/agent/subagents.js");
const subagents = window.Code.agent.subagents;
const persistence = window.Code.services.persistence;
const messagesFeature = window.Code.ui.messages.createMessagesFeature({{
  escapeHtml: (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;"),
  formatCompact: (value) => String(value),
  renderMarkdown: (value) => String(value),
  t: (key) => key,
  getMessageText: (message) => String(message?.content || ""),
  getBackgroundJob: () => null,
  getMessages: () => [],
  getSessionId: () => "session-background-result",
  getSelectedModel: () => "test-model",
  renderNetworkRecoveryStatus: () => "",
  renderAssistantContent: (value) => String(value),
  renderBranchFlow: () => "",
  isEditSuggestionMessage: () => false,
  renderEditSuggestion: () => "",
}});
const job = {{id: "job-1", agentRunId: "run-1", parentTaskStartedAt: "500"}};
const usage = {{input: 3, output: 4, cache: 5}};
const success = subagents.buildBackgroundResultMessage(job, {{
  content: "completed",
  error: false,
  model: "test-model",
  timestamp: "2026-08-01T00:00:00.000Z",
  responseTime: " 2.5s ",
  usage,
  includeUsage: true,
}});
const failure = subagents.buildBackgroundResultMessage(job, {{
  content: "failed",
  error: true,
  model: "test-model",
  timestamp: "2026-08-01T00:00:01.000Z",
  responseTime: " 3s ",
}});
const durableSuccess = persistence.serializeSessionMessages(
  [success],
  {{includeModel: true, includeTime: true}},
)[0];
const durableFailure = persistence.serializeSessionMessages(
  [failure],
  {{includeModel: true, includeTime: true}},
)[0];
const restoredSuccess = JSON.parse(JSON.stringify(durableSuccess));
const restoredFailure = JSON.parse(JSON.stringify(durableFailure));
const savedAgain = persistence.serializeSessionMessages(
  [restoredSuccess, restoredFailure],
  {{includeModel: true, includeTime: true}},
);
const detachedUser = {{
  role: "user",
  content: "parallel task",
  meta: {{detachedFromMain: true, backgroundDispatch: {{id: "job-1", status: "completed"}}}},
}};
const successProjection = messagesFeature.projectMessages(
  [detachedUser, restoredSuccess],
  {{hasActiveRun: false}},
);
const repeatedSuccessProjection = messagesFeature.projectMessages(
  [detachedUser, savedAgain[0]],
  {{hasActiveRun: false}},
);
const failureProjection = messagesFeature.projectMessages(
  [detachedUser, restoredFailure],
  {{hasActiveRun: false}},
);
const messages = [
  {{role: "user", meta: {{kind: "background-subagent", jobId: 7}}}},
  {{role: "assistant", meta: {{kind: "other", jobId: 7}}}},
  {{role: "assistant", meta: {{kind: "background-subagent", jobId: 7}}}},
];
process.stdout.write(JSON.stringify({{
  success,
  failure,
  durableSuccess,
  durableFailure,
  savedAgain,
  successProjection,
  repeatedSuccessProjection,
  failureProjection,
  sameUsage: success.meta._usage === usage,
  foundNumber: subagents.hasBackgroundResult(messages, 7),
  foundString: subagents.hasBackgroundResult(messages, "7"),
  foundMissing: subagents.hasBackgroundResult(null, 7),
  job,
  usage,
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)

        self.assertEqual(data["success"], {
            "role": "assistant",
            "content": "completed",
            "meta": {
                "kind": "background-subagent",
                "jobId": "job-1",
                "agentRunId": "run-1",
                "error": False,
                "detachedFromMain": True,
                "parentTaskStartedAt": 500,
                "_responseTime": "2.5s",
                "_usage": {"input": 3, "output": 4, "cache": 5},
                "_usageScope": "task",
            },
            "_model": "test-model",
            "_time": "2026-08-01T00:00:00.000Z",
            "_responseTime": "2.5s",
        })
        self.assertEqual(data["failure"], {
            "role": "assistant",
            "content": "failed",
            "meta": {
                "kind": "background-subagent",
                "jobId": "job-1",
                "agentRunId": "run-1",
                "error": True,
                "detachedFromMain": True,
                "parentTaskStartedAt": 500,
                "_responseTime": "3s",
            },
            "_model": "test-model",
            "_time": "2026-08-01T00:00:01.000Z",
            "_responseTime": "3s",
        })
        self.assertTrue(data["sameUsage"])
        for message, elapsed in (
            (data["success"], "2.5s"),
            (data["failure"], "3s"),
        ):
            self.assertEqual(message["_responseTime"], elapsed)
            self.assertEqual(message["meta"]["_responseTime"], elapsed)
        for message, elapsed in (
            (data["durableSuccess"], "2.5s"),
            (data["durableFailure"], "3s"),
            (data["savedAgain"][0], "2.5s"),
            (data["savedAgain"][1], "3s"),
        ):
            self.assertNotIn("_responseTime", message)
            self.assertEqual(message["meta"]["_responseTime"], elapsed)
        self.assertEqual(data["successProjection"].count('class="run-time"'), 1)
        self.assertEqual(data["successProjection"].count("2.5s"), 1)
        self.assertEqual(data["repeatedSuccessProjection"], data["successProjection"])
        self.assertEqual(data["failureProjection"].count('class="run-time"'), 1)
        self.assertEqual(data["failureProjection"].count("3s"), 1)
        self.assertTrue(data["foundNumber"])
        self.assertFalse(data["foundString"])
        self.assertFalse(data["foundMissing"])
        self.assertEqual(data["job"], {
            "id": "job-1",
            "agentRunId": "run-1",
            "parentTaskStartedAt": "500",
        })
        self.assertEqual(data["usage"], {"input": 3, "output": 4, "cache": 5})

        for function_name in ("buildBackgroundResultMessage", "hasBackgroundResult"):
            self.assertIn(f"function {function_name}(", SUBAGENTS_SOURCE)
            self.assertNotIn(f"function {function_name}(", APP_SOURCE)
        self.assertGreaterEqual(APP_SOURCE.count("hasBackgroundResult("), 3)
        self.assertEqual(APP_SOURCE.count("buildBackgroundResultMessage(job, {"), 2)

    def test_primary_error_recovery_elapsed_survives_serialization_without_footer_duplicate(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/services/persistence.js");
require("./src/ui/messages.js");
const persistence = window.Code.services.persistence;
const messagesFeature = window.Code.ui.messages.createMessagesFeature({
  escapeHtml: (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;"),
  formatCompact: (value) => String(value),
  renderMarkdown: (value) => String(value),
  t: (key) => key,
  getMessageText: (message) => String(message?.content || ""),
  getBackgroundJob: () => null,
  getMessages: () => [],
  getSessionId: () => "session-primary-failure",
  getSelectedModel: () => "test-model",
  renderNetworkRecoveryStatus: () => "",
  renderAssistantContent: (value) => String(value),
  renderBranchFlow: () => "",
  isEditSuggestionMessage: () => false,
  renderEditSuggestion: () => "",
});
const source = [
  {role: "user", content: "primary task"},
  {
    role: "assistant",
    content: "bounded failure",
    _responseTime: "7s",
    _model: "test-model",
    _time: "2026-08-08T00:00:00.000Z",
    meta: {
      kind: "error-recovery",
      _model: "test-model",
      _responseTime: "7s",
      _usage: {input: 3, output: 1, cache: 0},
      _usageScope: "task",
    },
  },
];
const durable = persistence.serializeSessionMessages(
  source,
  {includeModel: true, includeTime: true},
);
const restored = JSON.parse(JSON.stringify(durable));
const savedAgain = persistence.serializeSessionMessages(
  restored,
  {includeModel: true, includeTime: true},
);
const html = messagesFeature.projectMessages(restored, {hasActiveRun: false});
const repeatedHtml = messagesFeature.projectMessages(
  JSON.parse(JSON.stringify(savedAgain)),
  {hasActiveRun: false},
);
process.stdout.write(JSON.stringify({durable, restored, savedAgain, html, repeatedHtml}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)

        for message in (
            data["durable"][1],
            data["restored"][1],
            data["savedAgain"][1],
        ):
            self.assertNotIn("_responseTime", message)
            self.assertEqual(message["meta"]["kind"], "error-recovery")
            self.assertEqual(message["meta"]["_responseTime"], "7s")
            self.assertEqual(message["meta"]["_usage"], {"input": 3, "output": 1, "cache": 0})

        for html in (data["html"], data["repeatedHtml"]):
            self.assertEqual(html.count("data-completed-run-status"), 1)
            self.assertEqual(html.count('class="completed-run-timer"'), 1)
            self.assertEqual(html.count("7s"), 1)
            self.assertEqual(html.count('class="run-time"'), 0)
            self.assertEqual(html.count('class="response-info"'), 1)
        self.assertEqual(data["repeatedHtml"], data["html"])

    def test_compaction_context_policy_is_pure_and_backward_compatible(self):
        script = f"""
global.window = {{}};
eval({json.dumps((ROOT / "src" / "core" / "namespace.js").read_text(encoding="utf-8"))});
eval({json.dumps(COMPACTION_SOURCE)});
const compaction = window.Code.agent.compaction;
compaction.setModelContextCatalog([
  {{id:"claude-4.5-sonnet",contextWindowTokens:200000}},
  {{id:"claude_4.6_opus",contextWindowTokens:1000000}},
  {{id:"claude-5.0-sonnet",contextWindowTokens:1000000}},
  {{id:"gpt-4.1",contextWindowTokens:1047576,contextWindowSource:"official"}},
  {{id:"gpt-5.2-codex",contextWindowTokens:400000,contextWindowSource:"official"}},
  {{id:"gpt-5.1-codex",contextWindowTokens:400000,contextWindowSource:"official"}},
  {{id:"deepseek-v4",contextWindowTokens:1000000}},
  {{id:"deepseek-v3",contextWindowTokens:128000}},
  {{id:"gemini-2.5-pro",contextWindowTokens:1048576,contextWindowSource:"official"}},
]);
const messages = [
  {{role: "user", content: "old"}},
  {{role: "assistant", content: "summary-1", meta: {{kind: "compact-summary"}}}},
  {{role: "assistant", content: "detached", meta: {{detachedFromMain: true}}}},
  {{role: "user", content: "middle"}},
  {{role: "assistant", content: "summary-2", meta: {{kind: "compact-summary"}}}},
  {{role: "user", content: "latest"}},
];
const before = JSON.stringify(messages);
const selected = compaction.getModelContextMessages(
  messages,
  (message) => Boolean(message?.meta?.detachedFromMain),
);
const noSummary = compaction.getModelContextMessages([
  {{role: "user", content: "visible"}},
  {{role: "assistant", content: "hidden", meta: {{detachedFromMain: true}}}},
], (message) => Boolean(message?.meta?.detachedFromMain));
process.stdout.write(JSON.stringify({{
  selected: selected.map((message) => message.content),
  noSummary: noSummary.map((message) => message.content),
  unchanged: JSON.stringify(messages) === before,
  summary: compaction.isCompactSummaryMessage(messages[4]),
  limits: Object.fromEntries([
    "claude-4.5-sonnet",
    "claude_4.6_opus",
    "claude-5.0-sonnet",
    "gpt-4.1",
    "gpt-5.2-codex",
    "gpt-5.1-codex",
    "deepseek-v4",
    "deepseek-v3",
    "gemini-2.5-pro",
    "unknown",
  ].map((model) => [model, compaction.getModelContextLimit(model)])),
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["selected"], ["summary-2", "latest"])
        self.assertEqual(data["noSummary"], ["visible"])
        self.assertTrue(data["unchanged"])
        self.assertTrue(data["summary"])
        self.assertEqual(data["limits"], {
            "claude-4.5-sonnet": 200000,
            "claude_4.6_opus": 1000000,
            "claude-5.0-sonnet": 1000000,
            "gpt-4.1": 1047576,
            "gpt-5.2-codex": 400000,
            "gpt-5.1-codex": 400000,
            "deepseek-v4": 1000000,
            "deepseek-v3": 128000,
            "gemini-2.5-pro": 1048576,
            "unknown": 128000,
        })

    def test_context_budget_single_input_normalization_and_safety(self):
        script = f"""
global.window = {{}};
eval({json.dumps((ROOT / "src" / "core" / "namespace.js").read_text(encoding="utf-8"))});
eval({json.dumps(COMPACTION_SOURCE)});
const c = window.Code.agent.compaction;
c.setModelContextCatalog([{{id:"hard-model",contextWindowTokens:200000,contextWindowSource:"metadata",contextWindowHard:true}}]);
c.setContextBudgetTokens(400000);
const hard = c.getModelContextResolution("hard-model", 16000);
const estimated = c.getModelContextResolution("unknown-model", 16000);
c.setModelContextCatalog([
  {{id:"mixed-estimated",contextWindowTokens:1000000,contextWindowSource:"metadata",contextWindowHard:true}},
  {{id:"mixed-estimated",contextWindowTokens:128000,contextWindowSource:"unknown",contextWindowHard:false}},
  {{id:"mixed-hard",contextWindowTokens:200000,contextWindowSource:"metadata",contextWindowHard:true}},
  {{id:"mixed-hard",contextWindowTokens:1000000,contextWindowSource:"family",contextWindowHard:false}},
  {{id:"official-model",contextWindowTokens:400000,contextWindowSource:"official",contextWindowHard:false,maxOutputTokens:128000}},
  {{id:"stale-model",contextWindowTokens:500000,contextWindowSource:"stale_official",contextWindowHard:false}},
]);
const mixedEstimated = c.getModelContextResolution("mixed-estimated", 16000);
const mixedHard = c.getModelContextResolution("mixed-hard", 16000);
const official = c.getModelContextResolution("official-model", 200000);
const stale = c.getModelContextResolution("stale-model", 16000);
c.setContextBudgetTokens(4096);
const insufficient = c.getModelContextResolution("unknown-model", 2048);
process.stdout.write(JSON.stringify({{hard, estimated, mixedEstimated, mixedHard, official, stale, insufficient}}));
"""
        completed = subprocess.run(
            ["node", "-e", script], cwd=ROOT, check=True,
            capture_output=True, text=True, encoding="utf-8",
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["hard"]["contextLimit"], 200000)
        self.assertTrue(data["hard"]["budgetClamped"])
        self.assertEqual(data["estimated"]["contextLimit"], 400000)
        self.assertTrue(data["estimated"]["budgetAboveEstimate"])
        self.assertEqual(data["estimated"]["contextWindowSource"], "unknown")
        self.assertEqual(data["mixedEstimated"]["contextLimit"], 400000)
        self.assertTrue(data["mixedEstimated"]["contextWindowHard"])
        self.assertEqual(data["mixedHard"]["contextLimit"], 200000)
        self.assertTrue(data["mixedHard"]["contextWindowHard"])
        self.assertEqual(data["official"]["contextWindowSource"], "official")
        self.assertEqual(data["official"]["contextLimit"], 400000)
        self.assertEqual(data["official"]["maxOutputTokens"], 128000)
        self.assertFalse(data["official"]["contextWindowHard"])
        self.assertFalse(data["official"]["budgetClamped"])
        self.assertEqual(data["stale"]["contextWindowSource"], "stale_official")
        self.assertTrue(data["insufficient"]["inputBudgetInsufficient"])
        helper_start = APP_SOURCE.index("function parseContextBudgetInput(")
        helper_end = APP_SOURCE.index("function renderContextBudgetStatus(", helper_start)
        helper_source = APP_SOURCE[helper_start:helper_end]
        parser_script = f"""
eval({json.dumps(helper_source)});
const cases = {{
  blank: resolveContextBudgetInput("", {{contextWindowTokens:128000,maxTokens:4096}}),
  legacyAuto: resolveContextBudgetInput("auto", {{contextWindowTokens:128000,maxTokens:4096}}),
  legacyNumber: resolveContextBudgetInput("400000", {{contextWindowTokens:128000,maxTokens:4096}}),
  suffixK: resolveContextBudgetInput("128K", {{contextWindowTokens:128000,maxTokens:4096,reportFormatAdjustment:true}}),
  suffixM: resolveContextBudgetInput("1m", {{contextWindowTokens:128000,maxTokens:4096}}),
  low: resolveContextBudgetInput("1", {{contextWindowTokens:128000,maxTokens:4096}}),
  high: resolveContextBudgetInput("3M", {{contextWindowTokens:128000,maxTokens:4096}}),
  hard: resolveContextBudgetInput("400k", {{contextWindowTokens:200000,contextWindowHard:true,maxTokens:4096}}),
  estimated: resolveContextBudgetInput("400k", {{contextWindowTokens:128000,maxTokens:4096}}),
  impossible: resolveContextBudgetInput("", {{contextWindowTokens:4096,contextWindowHard:true,maxTokens:16384}}),
  invalid: resolveContextBudgetInput("12.5k", {{contextWindowTokens:128000,maxTokens:4096,autoLabel:"Auto"}}),
  negative: resolveContextBudgetInput("-1", {{contextWindowTokens:128000,maxTokens:4096}}),
  unit: resolveContextBudgetInput("12g", {{contextWindowTokens:128000,maxTokens:4096}}),
  text: resolveContextBudgetInput("hello", {{contextWindowTokens:128000,maxTokens:4096}}),
  oldBinary: resolveContextBudgetInput("65536", {{contextWindowTokens:128000,maxTokens:4096}}),
}};
process.stdout.write(JSON.stringify(cases));
"""
        parser_completed = subprocess.run(
            ["node", "-e", parser_script], cwd=ROOT, check=True,
            capture_output=True, text=True, encoding="utf-8",
        )
        cases = json.loads(parser_completed.stdout)
        self.assertEqual(cases["blank"]["storageValue"], "auto")
        self.assertEqual(cases["blank"]["displayValue"], "")
        self.assertEqual(cases["legacyAuto"]["storageValue"], "auto")
        self.assertEqual(cases["legacyNumber"]["displayValue"], "400k")
        self.assertEqual(cases["legacyNumber"]["storageValue"], "400000")
        self.assertEqual(cases["suffixK"]["tokens"], 128000)
        self.assertEqual(cases["suffixM"]["tokens"], 1000000)
        self.assertEqual(cases["low"]["tokens"], 9216)
        self.assertEqual(cases["high"]["tokens"], 2000000)
        self.assertEqual(cases["hard"]["tokens"], 200000)
        self.assertEqual(cases["hard"]["statusKey"], "contextBudgetAdjusted")
        self.assertTrue(cases["estimated"]["aboveEstimate"])
        self.assertEqual(cases["estimated"]["statusKey"], "contextBudgetEstimateWarning")
        self.assertTrue(cases["impossible"]["insufficient"])
        for invalid in ("invalid", "negative", "unit", "text"):
            self.assertFalse(cases[invalid]["valid"])
            self.assertIsNone(cases[invalid]["storageValue"])
            self.assertEqual(cases[invalid]["statusKey"], "contextBudgetInvalidFormat")
        self.assertEqual(cases["oldBinary"]["displayValue"], "65536")
        wrapper_end = APP_SOURCE.index("function saveLocalSettings(", helper_start)
        wrapper_source = APP_SOURCE[helper_start:wrapper_end]
        wrapper_script = f"""
const CONTEXT_BUDGET_KEY = "code-context-budget";
const values = new Map([[CONTEXT_BUDGET_KEY, "400000"]]);
const writes = [];
const localStorage = {{
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => {{ values.set(key, String(value)); writes.push([key, String(value)]); }},
}};
const els = {{contextBudget: {{value: "12g"}}, contextBudgetStatus: {{textContent:"", hidden:true, dataset:{{}}}}}};
const document = {{getElementById: () => null}};
const getSelectedModel = () => "unknown-model";
const getEffectiveMaxTokens = () => 4096;
const getModelContextResolution = () => ({{contextWindowTokens:128000,contextWindowHard:false}});
let selectedBudget = null;
const setContextBudgetTokens = (value) => {{ selectedBudget = value; }};
const t = (key) => key === "contextBudgetInvalidFormat" ? "Invalid format" : key;
eval({json.dumps(wrapper_source + '''
const numericResult = normalizeContextBudgetSetting({reportFormatAdjustment:true});
globalThis.__invalidFallback = {
  numeric: {
    result: numericResult,
    value: els.contextBudget.value,
    stored: values.get(CONTEXT_BUDGET_KEY),
    writes: [...writes],
    selectedBudget,
    status: {...els.contextBudgetStatus, dataset: {...els.contextBudgetStatus.dataset}},
  },
};
values.set(CONTEXT_BUDGET_KEY, "auto");
writes.length = 0;
els.contextBudget.value = "-7";
selectedBudget = null;
const autoResult = normalizeContextBudgetSetting({reportFormatAdjustment:true});
globalThis.__invalidFallback.auto = {
  result: autoResult,
  value: els.contextBudget.value,
  stored: values.get(CONTEXT_BUDGET_KEY),
  writes: [...writes],
  selectedBudget,
};
''')});
process.stdout.write(JSON.stringify(globalThis.__invalidFallback));
"""
        wrapper_completed = subprocess.run(
            ["node", "-e", wrapper_script], cwd=ROOT, check=True,
            capture_output=True, text=True, encoding="utf-8",
        )
        fallback = json.loads(wrapper_completed.stdout)
        self.assertFalse(fallback["numeric"]["result"]["valid"])
        self.assertEqual(fallback["numeric"]["value"], "400k")
        self.assertEqual(fallback["numeric"]["stored"], "400000")
        self.assertEqual(fallback["numeric"]["writes"], [])
        self.assertEqual(fallback["numeric"]["selectedBudget"], 400000)
        self.assertEqual(fallback["numeric"]["status"]["textContent"], "Invalid format")
        self.assertFalse(fallback["numeric"]["status"]["hidden"])
        self.assertFalse(fallback["auto"]["result"]["valid"])
        self.assertEqual(fallback["auto"]["value"], "")
        self.assertEqual(fallback["auto"]["stored"], "auto")
        self.assertEqual(fallback["auto"]["writes"], [])
        self.assertEqual(fallback["auto"]["selectedBudget"], "auto")
        self.assertIn('id="contextBudget" type="text"', INDEX_SOURCE)
        self.assertNotIn('id="contextBudgetCustom"', INDEX_SOURCE)
        self.assertIn("context-settings-primary", INDEX_SOURCE)
        self.assertIn("context-budget-field", INDEX_SOURCE)
        self.assertIn("@media (max-width: 560px)", STYLE_SOURCE)
        self.assertIn("settingsMaxTokens.value = els.maxTokens.value", SETTINGS_SOURCE)
        self.assertIn('localStorage.setItem("code-max-tokens", els.maxTokens.value)', APP_SOURCE)
        self.assertIn('const savedMax = localStorage.getItem("code-max-tokens") || "auto"', APP_SOURCE)
        self.assertIn("els.maxTokens.value = savedMax", APP_SOURCE)
        self.assertIn('temperature: "温度", maxTokens: "最大输出"', I18N_SOURCE)
        self.assertIn('temperature: "Temperature", maxTokens: "Max Tokens"', I18N_SOURCE)
        self.assertIn("contextBudgetPlaceholder", I18N_SOURCE)
        self.assertIn("contextBudgetInvalidFormat", I18N_SOURCE)
        self.assertIn("contextBudgetEstimateWarning", I18N_SOURCE)
        self.assertIn("contextBudgetInsufficient", I18N_SOURCE)
        self.assertIn("rememberFrozenSessionContextResolution(ctx.sessionId, frozen)", APP_SOURCE)
        self.assertIn("getSessionStats(sessionId)?.contextResolution", APP_SOURCE)
        self.assertIn("if (!ctx.isDetachedBackground && Number(snapshot?.contextLimit) > 0)", APP_SOURCE)
        self.assertIn("inputBudgetInsufficient: Boolean(item.inputBudgetInsufficient)", APP_SOURCE)
        self.assertIn("contextWindowTokens: Number(job.contextWindowTokens || 0)", APP_SOURCE)

    def test_session_context_resolution_restores_but_frontend_does_not_persist_it(self):
        helper_start = APP_SOURCE.index("const frozenContextResolutionBySession = new Map();")
        helper_end = APP_SOURCE.index("const {\n  classifyModelRequestFailure", helper_start)
        helper_source = APP_SOURCE[helper_start:helper_end]
        script = f"""
const stats = new Map([
  ["session-new", {{contextResolution: {{
    contextLimit: 400000,
    contextWindowTokens: 128000,
    contextBudgetTokens: 400000,
    contextWindowSource: "unknown",
    budgetAboveEstimate: true,
    calibrationCapTokens: 200000,
    calibrationEvidenceKind: "explicit_max",
    calibrationExpiresAt: "2030-02-01T00:00:00Z",
    calibrationApplied: true,
  }}}}],
  ["session-official", {{contextResolution: {{
    contextLimit: 400000,
    contextWindowTokens: 400000,
    contextBudgetTokens: null,
    contextWindowSource: "official",
  }}}}],
  ["session-stale", {{contextResolution: {{
    contextLimit: 500000,
    contextWindowTokens: 500000,
    contextBudgetTokens: null,
    contextWindowSource: "stale_official",
  }}}}],
]);
const getSessionStats = (sessionId) => stats.get(sessionId) || {{}};
const setSessionStats = (sessionId, value) => stats.set(sessionId, value);
eval({json.dumps(helper_source + '''
globalThis.__contextResult = {
  restored: getFrozenSessionContextResolution("session-new"),
  official: getFrozenSessionContextResolution("session-official"),
  stale: getFrozenSessionContextResolution("session-stale"),
  missing: getFrozenSessionContextResolution("session-old"),
  remembered: rememberFrozenSessionContextResolution("session-new", {
    contextLimit: 200000,
    contextWindowTokens: 200000,
    contextBudgetTokens: 200000,
    contextWindowSource: "metadata",
    contextWindowHard: true,
  }),
  persistedAfterRemember: getSessionStats("session-new").contextResolution,
};
''')});
process.stdout.write(JSON.stringify(globalThis.__contextResult));
"""
        completed = subprocess.run(
            ["node", "-e", script], cwd=ROOT, check=True,
            capture_output=True, text=True, encoding="utf-8",
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["restored"]["contextLimit"], 400000)
        self.assertEqual(data["restored"]["contextWindowSource"], "unknown")
        self.assertEqual(data["restored"]["calibrationCapTokens"], 200000)
        self.assertEqual(data["restored"]["calibrationEvidenceKind"], "explicit_max")
        self.assertTrue(data["restored"]["calibrationApplied"])
        self.assertEqual(data["official"]["contextWindowSource"], "official")
        self.assertEqual(data["stale"]["contextWindowSource"], "stale_official")
        self.assertIsNone(data["missing"])
        self.assertEqual(data["remembered"]["contextLimit"], 200000)
        self.assertEqual(data["persistedAfterRemember"]["contextLimit"], 400000)
        self.assertNotIn("stats.contextResolution =", APP_SOURCE)
        self.assertIn("contextCalibrationAdjusted", I18N_SOURCE)
        self.assertIn("code-context-calibration-notice:", APP_SOURCE)
        self.assertIn('sessionStorage.getItem(noticeKey) === "1"', APP_SOURCE)
        self.assertIn("calibrationCapTokens: snapshot.calibrationCapTokens", APP_SOURCE)

        for function_name in (
            "getModelContextLimit",
            "getModelContextMessages",
            "isCompactSummaryMessage",
        ):
            self.assertIn(f"function {function_name}(", COMPACTION_SOURCE)
            self.assertNotIn(f"function {function_name}(", APP_SOURCE)
        self.assertIn("} = window.Code.agent.compaction;", APP_SOURCE)
        self.assertIn(
            "getModelContextMessages(streamMessages, isDetachedFromMainContext)",
            APP_SOURCE,
        )
        for forbidden in (
            "state.",
            "document.",
            "localStorage",
            "apiJson",
            "saveSessionState",
            "fetch(",
        ):
            self.assertNotIn(forbidden, COMPACTION_SOURCE)

    def test_manual_compaction_plan_keeps_three_complete_context_rounds(self):
        script = f"""
global.window = {{}};
eval({json.dumps((ROOT / "src" / "core" / "namespace.js").read_text(encoding="utf-8"))});
eval({json.dumps(MODEL_REQUEST_SOURCE)});
eval({json.dumps(COMPACTION_SOURCE)});
const request = window.Code.agent.modelRequest;
const compaction = window.Code.agent.compaction;
const messages = [
  {{role: "system", content: "import boundary", meta: {{kind: "import-boundary"}}}},
  {{role: "assistant", content: "old summary", meta: {{kind: "compact-summary"}}}},
  {{role: "user", content: "u0"}},
  {{role: "assistant", content: "a0"}},
  {{role: "tool-result", content: "archived trace", meta: {{skipApi: true}}}},
  {{role: "user", content: "u1"}},
  {{role: "assistant", content: "a1"}},
  {{role: "user", content: "u2"}},
  {{role: "assistant", content: "a2"}},
  {{role: "tool-call", content: "read_file", meta: {{toolCallId: "call-2"}}}},
  {{role: "tool-result", content: "file contents", meta: {{toolCallId: "call-2"}}}},
  {{role: "assistant", content: "a2 final"}},
  {{role: "user", content: "u3"}},
  {{role: "assistant", content: "a3"}},
  {{role: "user", content: "queued", meta: {{detachedFromMain: true}}}},
  {{role: "assistant", content: "background", meta: {{detachedFromMain: true}}}},
  {{role: "user", content: "u4"}},
  {{role: "assistant", content: "a4"}},
];
const before = JSON.stringify(messages);
const plan = compaction.buildManualCompactionPlan(messages, {{
  mapMessageForApi: request.mapMessageForApi,
  getMessageText: (message) => String(message?.content || ""),
  isDetachedMessage: (message) => Boolean(message?.meta?.detachedFromMain),
}});
const activeContext = compaction.getModelContextMessages(
  messages,
  (message) => Boolean(message?.meta?.detachedFromMain),
);
const repeatPlan = compaction.buildManualCompactionPlan(activeContext, {{
  mapMessageForApi: request.mapMessageForApi,
  getMessageText: (message) => String(message?.content || ""),
  isDetachedMessage: (message) => Boolean(message?.meta?.detachedFromMain),
}});
const shortPlan = compaction.buildManualCompactionPlan([
  {{role: "user", content: "s0"}},
  {{role: "assistant", content: "r0"}},
  {{role: "user", content: "s1"}},
  {{role: "assistant", content: "r1"}},
  {{role: "user", content: "s2"}},
  {{role: "assistant", content: "r2"}},
], {{mapMessageForApi: request.mapMessageForApi}});
const summaryMessage = compaction.createCompactSummaryMessage(
  {{summary: "  stable summary  ", compressed: 99}},
  {{compressed: plan.compressCount, estimatedSaved: 123, createdAt: "2026-08-01T00:00:00.000Z"}},
);
const serverSummaryCount = plan.requestMessages.length
  - compaction.serverKeepCount(plan.requestMessages.length);
process.stdout.write(JSON.stringify({{
  canCompact: plan.canCompact,
  compressCount: plan.compressCount,
  keepCount: plan.keepCount,
  kept: plan.keptMessages.map((message) => message.content),
  removed: plan.removedMessages.map((message) => message.content),
  request: plan.requestMessages.map((message) => message.content),
  requestKeepCount: plan.requestKeepCount,
  serverSummaryCount,
  activeContext: activeContext.map((message) => message.content),
  repeatCanCompact: repeatPlan.canCompact,
  repeatRemoved: repeatPlan.removedMessages.map((message) => message.content),
  repeatKept: repeatPlan.keptMessages.map((message) => message.content),
  repeatRequest: repeatPlan.requestMessages.map((message) => message.content),
  shortCanCompact: shortPlan.canCompact,
  shortKept: shortPlan.keptMessages.map((message) => message.content),
  summaryMessage,
  unchanged: JSON.stringify(messages) === before,
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["canCompact"])
        self.assertEqual(data["compressCount"], 5)
        self.assertEqual(data["keepCount"], 10)
        self.assertEqual(data["kept"], [
            "u2", "a2", "read_file", "file contents", "a2 final",
            "u3", "a3", "queued", "background", "u4", "a4",
        ])
        self.assertEqual(data["removed"], [
            "old summary", "u0", "a0", "archived trace", "u1", "a1",
        ])
        self.assertEqual(data["request"], [
            "import boundary", "old summary", "u0", "a0", "u1", "a1", "u4", "a4",
        ])
        self.assertEqual(data["requestKeepCount"], 2)
        self.assertEqual(data["serverSummaryCount"], 6)
        self.assertEqual(data["activeContext"], [
            "old summary", "u0", "a0", "archived trace", "u1", "a1",
            "u2", "a2", "read_file", "file contents", "a2 final",
            "u3", "a3", "u4", "a4",
        ])
        self.assertTrue(data["repeatCanCompact"])
        self.assertEqual(data["repeatRemoved"], [
            "old summary", "u0", "a0", "archived trace", "u1", "a1",
        ])
        self.assertEqual(data["repeatKept"], [
            "u2", "a2", "read_file", "file contents", "a2 final",
            "u3", "a3", "u4", "a4",
        ])
        self.assertEqual(data["repeatRequest"], [
            "old summary", "u0", "a0", "u1", "a1", "u4", "a4",
        ])
        self.assertFalse(data["shortCanCompact"])
        self.assertEqual(data["shortKept"], ["s0", "r0", "s1", "r1", "s2", "r2"])
        self.assertEqual(data["summaryMessage"], {
            "role": "assistant",
            "content": "上下文压缩摘要（5 条消息）\n\nstable summary",
            "meta": {
                "kind": "compact-summary",
                "compressed": 5,
                "estimatedSaved": 123,
            },
            "_time": "2026-08-01T00:00:00.000Z",
        })
        self.assertTrue(data["unchanged"])

        for function_name in (
            "buildManualCompactionPlan",
            "createCompactSummaryMessage",
            "findCompleteContextStart",
            "getModelContextMessages",
            "resolveRequestKeepCount",
            "serverKeepCount",
        ):
            self.assertIn(f"function {function_name}(", COMPACTION_SOURCE)
        self.assertNotIn("function createCompactSummaryMessage(", APP_SOURCE)
        self.assertIn("recentRoundCount: RECENT_CONTEXT_ROUND_COUNT", APP_SOURCE)
        self.assertIn("createdAt: new Date().toISOString()", APP_SOURCE)
        self.assertNotIn("new Date(", COMPACTION_SOURCE)

    def test_server_agent_authorization_uses_durable_card_and_reload_path(self):
        for expected in (
            "requestServerAgentAuthorization(ctx, snapshot.pendingAuthorization)",
            "agentRuntime.submitAgentAuthorization(item.agentRunId",
            'status: "waiting-authorization"',
            "authorizationRequest: serializeAuthorizationRequest(request)",
            "restoreAuthorizationRequest(session.id, session.runState?.authorizationRequest)",
            "ensureServerAuthorizationProjection(ctx, pendingAuthorization)",
            "resumePersistedSessionRun(summary).catch",
        ):
            self.assertIn(expected, APP_SOURCE)

        request_start = APP_SOURCE.index("async function requestServerAgentAuthorization(")
        request_end = APP_SOURCE.index("async function runServerAgentLoop(", request_start)
        request_source = APP_SOURCE[request_start:request_end]
        request_foreground_start = request_source.index(
            "  } else {", request_source.index("if (ctx.isDetachedBackground)")
        )
        request_foreground_end = request_source.index(
            "  state.authorizationPanelCollapsed", request_foreground_start
        )
        request_foreground = request_source[request_foreground_start:request_foreground_end]
        request_projection_index = request_source.index(
            "const editId = ensureServerAuthorizationProjection(ctx, pendingAuthorization)"
        )
        request_run_state_index = request_source.index(
            "setSessionRunState(ctx.sessionId, nextState)", request_foreground_start
        )
        request_save_index = request_source.index(
            "await saveSessionState(", request_run_state_index
        )
        self.assertEqual(
            [request_projection_index, request_run_state_index, request_save_index],
            sorted([request_projection_index, request_run_state_index, request_save_index]),
        )
        self.assertIn("authorizationRequest: serializeAuthorizationRequest(request)", request_foreground)
        self.assertIn("{ persistMessages: true }", request_foreground)

        finish_start = APP_SOURCE.index("async function finishServerAgentAuthorizationRequest(")
        finish_end = APP_SOURCE.index("function resolveAuthorization(", finish_start)
        finish_source = APP_SOURCE[finish_start:finish_end]
        finish_foreground_start = finish_source.index(
            "  } else {", finish_source.index("if (item.detachedBackground)")
        )
        finish_foreground_end = finish_source.index(
            "  if (item.sessionId === state.sessionId)", finish_foreground_start
        )
        finish_foreground = finish_source[finish_foreground_start:finish_foreground_end]
        submit_index = finish_source.index("await agentRuntime.submitAgentAuthorization(")
        decision_projection_index = finish_source.index(
            "markServerAuthorizationProjection(item, result, approved)"
        )
        clear_request_index = finish_source.index(
            "state.authorizationRequests = state.authorizationRequests.filter"
        )
        run_state_clear_index = finish_source.index(
            "authorizationRequest: null", finish_foreground_start
        )
        set_state_index = finish_source.index(
            "setSessionRunState(item.sessionId, nextState)", finish_foreground_start
        )
        save_index = finish_source.index("await saveSessionState(", set_state_index)
        resolver_index = finish_source.index("  if (resolver) {", save_index)
        resume_index = finish_source.index("resumePersistedSessionRun(summary)", resolver_index)
        ordered = [
            submit_index,
            decision_projection_index,
            clear_request_index,
            run_state_clear_index,
            set_state_index,
            save_index,
            resolver_index,
            resume_index,
        ]
        self.assertEqual(ordered, sorted(ordered))
        self.assertIn("{ persistMessages: true }", finish_foreground)
        self.assertIn(
            "Boolean(meta.serverManaged && !serverExecuting && !applied && !rejected",
            DIFF_SOURCE,
        )
        self.assertIn("executionOwner: executionOwnerForPermissionProfile(permissionProfile)", APP_SOURCE)
        self.assertIn(
            'return SERVER_EXECUTION_PROFILES.includes(permissionProfile) ? "server-agent" : "browser"',
            PERMISSIONS_SOURCE,
        )
        self.assertIn("action: authorizationAction", APP_SOURCE)
        self.assertIn("pendingAuthorization.path || pendingAuthorization.command", APP_SOURCE)

    def test_server_authorization_edit_target_identity_survives_file_card_enhancement(self):
        render_start = DIFF_SOURCE.index("function renderEditSuggestionProjection(")
        render_end = DIFF_SOURCE.index("return Object.freeze({", render_start)
        render_source = DIFF_SOURCE[render_start:render_end]
        card_start = APP_SOURCE.index("function maybeRenderFileCard(")
        card_end = APP_SOURCE.index("function _toolActionLabel(", card_start)
        card_source = APP_SOURCE[card_start:card_end]

        self.assertIn(
            'class="tool-edit-target clickable-path" type="button" data-path="${escapeHtml(target)}"',
            render_source,
        )
        self.assertIn('card.className = "path-file-card";', card_source)
        self.assertIn("card.title = p;", card_source)
        self.assertIn('name.textContent = el.textContent || "";', card_source)
        self.assertIn("el.replaceWith(card);", card_source)
        self.assertLess(card_source.index("card.title = p;"), card_source.index("el.replaceWith(card);"))

        self.assertIn(
            'const EDIT_AUTHORIZATION_PATH_IDENTITY = Object.freeze({',
            H4_SMOKE_SOURCE,
        )
        self.assertIn(
            'selector: ".tool-edit-target[data-path], .path-file-card[title]",',
            H4_SMOKE_SOURCE,
        )
        self.assertIn(
            "projection = await editSuggestionPathProjection(page, "
            "EDIT_AUTHORIZATION_CONTRACT.path);",
            H4_SMOKE_SOURCE,
        )
        self.assertIn(
            "pathMatches: suggestionPath(suggestion) === facts.path,",
            H4_SMOKE_SOURCE,
        )
        self.assertGreaterEqual(
            H4_SMOKE_SOURCE.count("await exactEditSuggestionForPath("),
            2,
        )
        self.assertNotIn('querySelector(".tool-edit-target', H4_SMOKE_SOURCE)
        self.assertNotIn('locator(".tool-edit-target', H4_SMOKE_SOURCE)
        self.assertEqual(H4_SMOKE_SOURCE.count(".tool-edit-target"), 2)
        self.assertEqual(H4_SMOKE_SOURCE.count(".path-file-card"), 2)

    def test_server_agent_uses_profile_tools_and_projects_all_authorized_actions(self):
        for expected in (
            "const profileAllowedToolNames = getAllowedToolNamesForProfile(",
            "allowedTools: serverToolNames",
            "toolBudgets: skillToolBudgets",
            '["propose_edit", "apply_edit", "write_file", "delete_file"]',
            'const authorizationAction = String(pendingAuthorization.action || "propose_edit")',
            'command: String(pendingAuthorization.command || "")',
            "projectServerEditToolCompleted(ctx, event, callMessage, result)",
            "const decisionResult = result?.childResult || result || {}",
            'const delegatedEditCompletion = toolAction === "task" && Boolean(projection)',
        ):
            self.assertIn(expected, APP_SOURCE)
        self.assertIn(
            'toolPreset === "full" && ["accept", "bypass"].includes(permissionProfile)',
            PERMISSIONS_SOURCE,
        )
        self.assertNotIn("SERVER_AGENT_SAFE_TOOLS", APP_SOURCE)

    def test_agent_runtime_submits_authorization_id_and_decision(self):
        script = f"""
global.window = {{Code: {{agent: {{}}}}}};
const source = {json.dumps(RUNTIME_SOURCE)};
let captured = null;
global.fetch = async (url, options) => {{
  captured = {{url: String(url), method: options.method, body: JSON.parse(options.body)}};
  return new Response(JSON.stringify({{status: "waiting_credentials", result: {{applied: true}}}}), {{
    status: 200,
    headers: {{"Content-Type": "application/json"}},
  }});
}};
eval(source);
(async () => {{
  const result = await window.Code.agent.runtime.submitAgentAuthorization("agent/a", {{
    authorizationId: "authorization-1",
    decision: "approved",
  }});
  process.stdout.write(JSON.stringify({{captured, result}}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["captured"]["url"], "/api/agent/runs/agent%2Fa/authorization")
        self.assertEqual(data["captured"]["method"], "POST")
        self.assertEqual(data["captured"]["body"], {
            "authorizationId": "authorization-1",
            "decision": "approved",
        })
        self.assertTrue(data["result"]["result"]["applied"])

    def test_agent_runtime_steers_same_run_with_idempotency_key(self):
        script = f"""
global.window = {{Code: {{agent: {{}}}}}};
const source = {json.dumps(RUNTIME_SOURCE)};
let captured = null;
global.fetch = async (url, options) => {{
  captured = {{url: String(url), method: options.method, body: JSON.parse(options.body)}};
  return new Response(JSON.stringify({{status: "model", result: {{status: "pending"}}}}), {{
    status: 200,
    headers: {{"Content-Type": "application/json"}},
  }});
}};
eval(source);
(async () => {{
  const result = await window.Code.agent.runtime.steerAgentRun("agent/a", {{
    clientRequestId: "steer-client-1",
    message: {{role: "user", content: "new priority"}},
  }});
  process.stdout.write(JSON.stringify({{captured, result}}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["captured"]["url"], "/api/agent/runs/agent%2Fa/steer")
        self.assertEqual(data["captured"]["method"], "POST")
        self.assertEqual(data["captured"]["body"], {
            "message": {"role": "user", "content": "new priority"},
            "clientRequestId": "steer-client-1",
        })
        self.assertEqual(data["result"]["result"]["status"], "pending")

    def test_followup_steer_freezes_target_run_across_session_save_cleanup(self):
        helper_start = APP_SOURCE.index("async function submitSessionSteer(")
        helper_end = APP_SOURCE.index("async function steerSessionMessage(", helper_start)
        helper_source = APP_SOURCE[helper_start:helper_end]
        script = f"""
let capturedRunId = "";
let saveCount = 0;
const agentRuntime = {{
  async steerAgentRun(agentRunId) {{
    capturedRunId = String(agentRunId);
    return {{result: {{steerId: "steer-1"}}}};
  }},
}};
const renderSessionMessages = () => {{}};
const messageScrollController = null;
let ctx = {{
  agentRunId: "run-at-click",
  sessionId: "session-1",
  messages: [],
  stats: {{}},
  run: {{abortController: new AbortController()}},
}};
const userMessage = {{
  meta: {{steerDispatch: {{
    agentRunId: "run-at-click",
    clientRequestId: "followup-1",
    status: "submitting",
  }}}},
  content: "next task",
}};
ctx.messages.push(userMessage);
// Reproduce bundle cleanup during steerSessionMessage's pre-submit save.
ctx.agentRunId = "";
const saveSessionState = async () => {{
  saveCount += 1;
}};
eval({json.dumps(helper_source)});
(async () => {{
  const result = await submitSessionSteer(ctx, userMessage, {{createReadingAnchor: false}});
  process.stdout.write(JSON.stringify({{
    capturedRunId,
    saveCount,
    result,
    dispatch: userMessage.meta.steerDispatch,
  }}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script], cwd=ROOT, check=True,
            capture_output=True, text=True, encoding="utf-8",
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["capturedRunId"], "run-at-click")
        self.assertEqual(data["saveCount"], 1)
        self.assertEqual(data["dispatch"]["agentRunId"], "run-at-click")
        self.assertEqual(data["dispatch"]["status"], "accepted")
        self.assertEqual(data["dispatch"]["steerId"], "steer-1")

    def test_read_only_permission_is_user_visible(self):
        self.assertIn('data-value="read"', INDEX_SOURCE)
        self.assertIn('data-i18n="permRead"', INDEX_SOURCE)
        self.assertIn('permRead: "只读分析"', I18N_SOURCE)
        self.assertIn('permRead: "Read only"', I18N_SOURCE)

    def test_partial_think_blocks_never_leak_into_visible_content(self):
        parser_start = APP_SOURCE.index("function splitThoughtContent")
        parser_end = APP_SOURCE.index("function bindCopyButtons", parser_start)
        parser_source = APP_SOURCE[parser_start:parser_end]
        cases = (
            "<thi",
            "visible<t",
            "prefix <think>hidden reasoning",
            "<think>hidden</think>answer",
            "<THINK>hidden</THINK>done",
            "plain answer",
        )
        script = (
            parser_source
            + f"\nconst cases = {json.dumps(cases)};"
            + "\nprocess.stdout.write(JSON.stringify(cases.map(splitThoughtContent)));"
        )
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            [
                {"thought": "", "content": ""},
                {"thought": "", "content": "visible"},
                {"thought": "hidden reasoning", "content": "prefix"},
                {"thought": "hidden", "content": "answer"},
                {"thought": "hidden", "content": "done"},
                {"thought": "", "content": "plain answer"},
            ],
        )

    def test_system_prompt_segment_table_preserves_legacy_bytes_and_task_snapshot(self):
        security_match = re.search(
            r"const SYSTEM_SECURITY_LAYER = `([\s\S]*?)`\.trim\(\);",
            APP_SOURCE,
        )
        delegation_match = re.search(
            r"const SUBAGENT_DELEGATION_RULES = `([\s\S]*?)`;",
            APP_SOURCE,
        )
        self.assertIsNotNone(security_match)
        self.assertIsNotNone(delegation_match)
        security_layer = security_match.group(1).strip()
        delegation_rules = delegation_match.group(1)
        self.assertIn("通过 workbar 连接模型服务。", security_layer)
        self.assertIn("解释模型连接方式时，统一称为 workbar", security_layer)
        self.assertIn("不展开、猜测或披露其底层网关实现", security_layer)
        self.assertNotIn("API 中转站", security_layer)
        self.assertNotIn("New API", security_layer)
        script = r"""
const crypto = require("crypto");
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/system-prompt.js");
const prompt = window.Code.agent.systemPrompt;
(async () => {
const securityLayer = __SECURITY_LAYER__;
const delegationRules = __DELEGATION_RULES__;
const environment = prompt.formatSystemPromptEnvironment({
  capturedAt: new Date(2026, 7, 15, 1, 2),
  timeZoneName: "Asia/Shanghai",
  utcOffsetMinutes: 480,
  cwd: "C:/work/main",
  appVersion: "0.6.2",
});
const values = {
  securityLayer,
  behaviorInstruction: "CUSTOM BEHAVIOR",
  environmentInstruction: environment.instruction,
  projectFoldersInstruction: "当前项目主文件夹：C:/work/main\n项目源文件夹（均可搜索、读取和编辑）：\n- C:/work/main\n- C:/work/shared",
  externalFilesInstruction: "提示：项目外部文件可以直接读，系统自动处理权限。@图片路径 用 read_file 读取即可获得视觉输入。回复中可用 ![描述](路径) 嵌入本地图片（png/jpg/gif/webp/svg）。",
  delegationInstruction: delegationRules,
  responseLanguageInstruction: "## Response Language\nThe user is writing in English. Reply in English unless the user explicitly asks for another language.",
  projectContextInstruction: "=== 项目上下文（仅本项目，来自 AGENTS.md） ===\nPROJECT CONTEXT",
  memoryInstruction: '=== 长期记忆（跨会话保留） ===\n以下信息已融入当前上下文，直接使用，不要提及"长期记忆"或"根据记忆"。\nMEMORY CONTEXT',
  skillInstruction: "=== 已激活 Skill: fixture-skill（正文已加载，不要再次调用 use_skill） ===\nSKILL BODY",
  permissionInstruction: "PERMISSION INSTRUCTION",
};
const snapshot = prompt.createSystemPromptSnapshot(values, environment);
const normalizedLegacy = snapshot.prompt.replace(
  "（Asia/Shanghai UTC+08:00）",
  "（北京时间）",
);
const hash = (value) => crypto.createHash("sha256").update(value, "utf8").digest("hex");

const owner = {sessionId: "session-1"};
let factoryCalls = 0;
const factory = async () => {
  factoryCalls += 1;
  await Promise.resolve();
  return snapshot;
};
const [cachedA, cachedB] = await Promise.all([
  prompt.getOrCreateSystemPromptSnapshot(owner, factory),
  prompt.getOrCreateSystemPromptSnapshot(owner, factory),
]);

const nextEnvironment = prompt.formatSystemPromptEnvironment({
  capturedAt: new Date(2026, 7, 16, 3, 4),
  timeZoneName: "Europe/Paris",
  utcOffsetMinutes: 120,
  cwd: "D:/next",
  appVersion: "0.6.3",
});
const nextValues = {
  ...values,
  behaviorInstruction: "NEXT BEHAVIOR",
  environmentInstruction: nextEnvironment.instruction,
  projectFoldersInstruction: "NEXT ROOTS",
  projectContextInstruction: "NEXT PROJECT",
  memoryInstruction: "NEXT MEMORY",
  skillInstruction: "NEXT SKILL",
};
const sameTask = await prompt.getOrCreateSystemPromptSnapshot(
  owner,
  async () => prompt.createSystemPromptSnapshot(nextValues, nextEnvironment),
);
const nextTask = await prompt.getOrCreateSystemPromptSnapshot(
  {sessionId: "session-2"},
  async () => prompt.createSystemPromptSnapshot(nextValues, nextEnvironment),
);

const retryOwner = {};
let failureCount = 0;
try {
  await prompt.getOrCreateSystemPromptSnapshot(retryOwner, async () => {
    failureCount += 1;
    throw new Error("fixture failure");
  });
} catch (error) {
  if (error.message !== "fixture failure") throw error;
}
const recovered = await prompt.getOrCreateSystemPromptSnapshot(retryOwner, async () => {
  failureCount += 1;
  return snapshot;
});
const minimalNames = prompt.buildSystemPromptSegments({
  securityLayer: "security",
  behaviorInstruction: "behavior",
  environmentInstruction: "environment",
  externalFilesInstruction: "external",
  permissionInstruction: "permission",
}).map((segment) => segment.name);

process.stdout.write(JSON.stringify({
  definitions: prompt.SYSTEM_PROMPT_SEGMENTS,
  names: snapshot.segmentNames,
  normalizedLegacyHash: hash(normalizedLegacy),
  newHash: hash(snapshot.prompt),
  environment,
  cachedIdentity: cachedA === cachedB && cachedA === sameTask,
  factoryCalls,
  hiddenFromSerialization: !JSON.stringify(owner).includes("CUSTOM BEHAVIOR"),
  frozen: Object.isFrozen(snapshot) && Object.isFrozen(snapshot.segmentNames),
  sameTaskPrompt: sameTask.prompt,
  nextTaskPrompt: nextTask.prompt,
  failureCount,
  recovered: recovered === snapshot,
  minimalNames,
}));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        script = script.replace(
            "__SECURITY_LAYER__",
            json.dumps(security_layer, ensure_ascii=False),
        ).replace(
            "__DELEGATION_RULES__",
            json.dumps(delegation_rules, ensure_ascii=False),
        )
        completed = subprocess.run(
            ["node", "--input-type=commonjs", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(
            data["names"],
            [
                "security",
                "behavior",
                "environment",
                "project-folders",
                "external-files",
                "delegation",
                "response-language",
                "project-context",
                "memory",
                "skill",
                "permission",
            ],
        )
        self.assertEqual(data["definitions"][0]["refresh"], "static")
        self.assertEqual(data["definitions"][-1]["name"], "permission")
        self.assertEqual(
            data["normalizedLegacyHash"],
            "496090a3e5625836c49adb16de4bedde935ddcdfe77a6dfa03c2e40e12377d46",
        )
        self.assertEqual(
            data["newHash"],
            "740ee2b019b3a641963b0d0311a9f0500d233c1d7a458e53d08f542e71b824f5",
        )
        self.assertEqual(data["environment"]["timeZone"], "Asia/Shanghai UTC+08:00")
        self.assertIn("（Asia/Shanghai UTC+08:00）", data["environment"]["instruction"])
        self.assertTrue(data["cachedIdentity"])
        self.assertEqual(data["factoryCalls"], 1)
        self.assertTrue(data["hiddenFromSerialization"])
        self.assertTrue(data["frozen"])
        self.assertIn("CUSTOM BEHAVIOR", data["sameTaskPrompt"])
        self.assertNotIn("NEXT BEHAVIOR", data["sameTaskPrompt"])
        for expected in (
            "NEXT BEHAVIOR",
            "D:/next",
            "v0.6.3",
            "NEXT ROOTS",
            "NEXT PROJECT",
            "NEXT MEMORY",
            "NEXT SKILL",
        ):
            self.assertIn(expected, data["nextTaskPrompt"])
        self.assertEqual(data["failureCount"], 2)
        self.assertTrue(data["recovered"])
        self.assertEqual(
            data["minimalNames"],
            ["security", "behavior", "environment", "external-files", "permission"],
        )

    def test_system_prompt_snapshot_wiring_keeps_retry_and_dynamic_sources_scoped(self):
        composer_source = SYSTEM_PROMPT_SOURCE
        prompt_start = APP_SOURCE.index("async function buildSystemPromptSnapshot(")
        prompt_end = APP_SOURCE.index("async function loadProjectContext()", prompt_start)
        prompt_source = APP_SOURCE[prompt_start:prompt_end]
        request_start = APP_SOURCE.index("async function buildModelRequestPayload(")
        request_end = APP_SOURCE.index("async function _callModelOnceAttempt(", request_start)
        request_source = APP_SOURCE[request_start:request_end]
        retry_start = APP_SOURCE.index("// If the request had images and the error suggests")
        retry_end = APP_SOURCE.index("// Annotate the assistant response", retry_start)
        retry_source = APP_SOURCE[retry_start:retry_end]

        for expected in (
            "createSystemPromptSnapshotData({",
            "formatSystemPromptEnvironment({",
            "resolveLocalTimeZoneName()",
            "options.appVersion ?? state.appVersion",
            "options.memoryContext ?? state.memoryContext",
            "options.projectContext ?? state.projectContext",
            "ensureSkillBody(",
            "getMatchedSkillPrompts(",
            "getPermissionInstruction(permissionProfile)",
            "allowedToolNames.has(\"task\")",
            "userLang !== \"Chinese\"",
        ):
            self.assertIn(expected, prompt_source)
        self.assertIn("getOrCreateSystemPromptSnapshot(", prompt_source)
        self.assertIn("await getTaskSystemPrompt(ctx, systemPromptOptions)", request_source)
        self.assertIn("ctx.agentRunId = \"\"", retry_source)
        self.assertNotIn("_systemPromptSnapshot", retry_source)
        self.assertIn("} = window.Code.agent.systemPrompt;", APP_SOURCE)
        self.assertNotIn("const systemPromptComposer =", APP_SOURCE)
        self.assertLess(
            FRONTEND_ENTRY_SOURCE.index('import "./agent/system-prompt.js";'),
            FRONTEND_ENTRY_SOURCE.index('import "../app.js";'),
        )
        for forbidden in ("state.", "els.", "ensureSkillBody", "getMatchedSkillPrompts"):
            self.assertNotIn(forbidden, composer_source)
        self.assertIn("enumerable: false", composer_source)
        self.assertIn("agent.systemPrompt = Object.freeze({", composer_source)

    def test_core_module_files_exist(self):
        for relative_path in (
            "src/core/namespace.js",
            "src/core/state.js",
            "src/core/icons.js",
            "src/core/utils.js",
            "src/core/i18n.js",
            "src/core/platform.js",
            "src/core/theme-engine.js",
            "src/services/notifications.js",
            "src/services/api-client.js",
            "src/services/persistence.js",
            "src/features/sessions.js",
            "src/features/branches.js",
            "src/ui/diff.js",
            "src/ui/markdown.js",
            "src/ui/timeline.js",
            "src/ui/messages.js",
            "src/ui/run-view-model.js",
            "src/ui/panels.js",
            "src/features/settings.js",
            "src/features/onboarding-tasks.js",
            "src/features/preview.js",
            "src/features/files.js",
            "src/features/image-attachments.js",
            "src/features/skills-memory.js",
            "src/features/goal.js",
            "src/features/session-import.js",
            "src/agent/system-prompt.js",
            "src/agent/model-request.js",
            "src/agent/tools.js",
            "src/agent/permissions.js",
            "src/agent/questionnaire.js",
            "src/agent/subagents.js",
            "src/agent/compaction.js",
            "src/agent/model-stream.js",
            "src/agent/run-reducer.js",
            "src/agent/run-projection-shadow.js",
            "src/frontend-entry.js",
        ):
            self.assertTrue((ROOT / relative_path).is_file(), relative_path)

    def test_default_entry_uses_bundle_with_generated_classic_fallback(self):
        entry_imports = re.findall(
            r'^import "([^\"]+)";$',
            FRONTEND_ENTRY_SOURCE,
            flags=re.MULTILINE,
        )
        classic_scripts = [
            "./" + posixpath.normpath(posixpath.join("src", item))
            for item in entry_imports
        ]

        self.assertEqual(len(classic_scripts), len(set(classic_scripts)))
        self.assertEqual(len(classic_scripts), 40)
        self.assertIn("./src/features/onboarding-tasks.js", classic_scripts)
        self.assertIn("./src/features/image-overlay.js", classic_scripts)
        self.assertIn("./src/features/link-context-menu.js", classic_scripts)
        self.assertLess(
            classic_scripts.index("./src/agent/system-prompt.js"),
            classic_scripts.index("./app.js"),
        )
        self.assertEqual(classic_scripts[-2:], ["./agent-runtime.js", "./app.js"])
        self.assertIn('data-frontend-runtime="bundle"', INDEX_SOURCE)
        self.assertEqual(INDEX_SOURCE.count('/dist/frontend/code.bundle.js'), 1)
        self.assertEqual(INDEX_SOURCE.count('/dist/frontend/index.classic.html'), 1)
        self.assertNotIn("window.__codeUseClassicFrontend", INDEX_SOURCE)
        self.assertNotIn("frontendBundleLoaded", FRONTEND_ENTRY_SOURCE)
        self.assertNotRegex(INDEX_SOURCE, r"\sonerror=")
        self.assertIn('bundleScript.addEventListener("error"', INDEX_SOURCE)
        self.assertIn('bundleScript.addEventListener("load"', INDEX_SOURCE)
        self.assertIn(
            'document.documentElement.setAttribute("data-code-frontend-ready", "true")',
            FRONTEND_ENTRY_SOURCE,
        )
        self.assertNotRegex(
            INDEX_SOURCE,
            r'<script src="\./(?:src/[^\"]+|agent-runtime\.js|app\.js)"></script>',
        )

    def test_default_bundle_bootstrap_falls_back_without_global_bridge(self):
        runtime_match = re.search(
            r'<!-- code-frontend-runtime:start -->\s*<script>([\s\S]*?)</script>\s*<!-- code-frontend-runtime:end -->',
            INDEX_SOURCE,
        )
        self.assertIsNotNone(runtime_match)
        bootstrap_source = runtime_match.group(1)
        script = f"""
const vm = require("vm");
const bootstrapSource = {json.dumps(bootstrap_source)};

function runScenario(eventType, ready) {{
  const attributes = new Map();
  if (ready) attributes.set("data-code-frontend-ready", "true");
  const listeners = {{}};
  const replacements = [];
  let appended = null;
  const bundleScript = {{
    src: "",
    async: true,
    addEventListener(type, handler, options) {{
      listeners[type] = {{handler, options}};
    }},
  }};
  const document = {{
    documentElement: {{
      getAttribute(name) {{ return attributes.get(name) || null; }},
    }},
    createElement(tagName) {{
      if (tagName !== "script") throw new Error(`unexpected element: ${{tagName}}`);
      return bundleScript;
    }},
    body: {{
      appendChild(node) {{ appended = node; return node; }},
    }},
  }};
  const window = {{
    location: {{
      href: "http://127.0.0.1:3011/?phase2-first-send=1",
      replace(value) {{ replacements.push(String(value)); }},
    }},
  }};
  vm.runInNewContext(bootstrapSource, {{window, document, URL}});
  if (eventType) listeners[eventType].handler();
  return {{
    appended: appended === bundleScript,
    src: bundleScript.src,
    async: bundleScript.async,
    errorOnce: listeners.error.options.once === true,
    loadOnce: listeners.load.options.once === true,
    replacements,
  }};
}}

process.stdout.write(JSON.stringify({{
  error: runScenario("error", false),
  initFailure: runScenario("load", false),
  ready: runScenario("load", true),
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        for scenario in data.values():
            self.assertTrue(scenario["appended"])
            self.assertEqual(scenario["src"], "/dist/frontend/code.bundle.js")
            self.assertFalse(scenario["async"])
            self.assertTrue(scenario["errorOnce"])
            self.assertTrue(scenario["loadOnce"])
        self.assertEqual(len(data["error"]["replacements"]), 1)
        self.assertIn("fallback=bundle-load", data["error"]["replacements"][0])
        self.assertEqual(len(data["initFailure"]["replacements"]), 1)
        self.assertIn("fallback=bundle-init", data["initFailure"]["replacements"][0])
        self.assertEqual(data["ready"]["replacements"], [])

    def test_frontend_bundle_build_is_deterministic_and_guarded(self):
        def combined_output(process):
            return (process.stdout or "") + (process.stderr or "")

        self.assertEqual(PACKAGE_JSON["devDependencies"]["esbuild"], "0.28.1")
        self.assertIn('"build:frontend"', (ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertIn('"verify:frontend"', (ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertIn('entryPoints: ["src/frontend-entry.js"]', FRONTEND_BUILD_SOURCE)
        self.assertIn("Expected 40 frontend entry imports", FRONTEND_BUILD_SOURCE)
        self.assertIn('format: "iife"', FRONTEND_BUILD_SOURCE)
        self.assertIn('treeShaking: false', FRONTEND_BUILD_SOURCE)
        self.assertIn('const statePath = path.join(outputDir, "code.bundle.state.json")', FRONTEND_BUILD_SOURCE)
        self.assertIn('if (checkOnly)', FRONTEND_BUILD_SOURCE)
        self.assertIn('sourceFingerprint', FRONTEND_BUILD_SOURCE)
        self.assertIn('Frontend build output hash mismatch', FRONTEND_BUILD_SOURCE)
        self.assertIn('/dist/frontend/code.bundle.js', INDEX_SOURCE)
        self.assertIn('/dist/frontend/index.classic.html', INDEX_SOURCE)
        self.assertIn("FRONTEND_BUNDLE", BUILD_SOURCE)
        self.assertIn("FRONTEND_CLASSIC_FALLBACK", BUILD_SOURCE)
        self.assertIn("build_frontend_assets()", BUILD_SOURCE)
        self.assertNotIn("code.bundle.js.map", BUILD_SOURCE)
        self.assertNotIn("code.bundle.meta.json", BUILD_SOURCE)

        self.assertIn("dist\\\\frontend\\\\code.bundle.js", CURRENT_SPEC_SOURCE)
        self.assertIn("dist\\\\frontend\\\\index.classic.html", CURRENT_SPEC_SOURCE)
        self.assertIn("src', 'src'", CURRENT_SPEC_SOURCE)
        self.assertNotIn("code.bundle.js.map", CURRENT_SPEC_SOURCE)
        self.assertNotIn("code.bundle.meta.json", CURRENT_SPEC_SOURCE)
        self.assertNotIn("code.bundle.state.json", CURRENT_SPEC_SOURCE)

        entry_imports = re.findall(
            r'^import "([^\"]+)";$',
            FRONTEND_ENTRY_SOURCE,
            flags=re.MULTILINE,
        )
        expected_fallback_scripts = [
            "/" + posixpath.normpath(posixpath.join("src", item))
            for item in entry_imports
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first"
            second = Path(temp_dir) / "second"
            bundles = []
            normalized_previews = []
            fallbacks = []
            source_fingerprints = []
            for output_dir in (first, second):
                result = subprocess.run(
                    [
                        "node",
                        "scripts/build-frontend.mjs",
                        "--outdir",
                        str(output_dir),
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, combined_output(result))
                bundle = output_dir / "code.bundle.js"
                source_map = output_dir / "code.bundle.js.map"
                metadata = output_dir / "code.bundle.meta.json"
                state = output_dir / "code.bundle.state.json"
                preview = output_dir / "index.html"
                fallback = output_dir / "index.classic.html"
                self.assertTrue(bundle.is_file())
                self.assertTrue(source_map.is_file())
                self.assertTrue(metadata.is_file())
                self.assertTrue(state.is_file())
                self.assertTrue(preview.is_file())
                self.assertTrue(fallback.is_file())
                bundles.append(bundle.read_bytes())
                preview_source = preview.read_text(encoding="utf-8")
                fallback_source = fallback.read_text(encoding="utf-8")
                fallbacks.append(fallback_source)
                state_data = json.loads(state.read_text(encoding="utf-8"))
                source_fingerprints.append(state_data["sourceFingerprint"])

                self.assertIn('data-frontend-runtime="bundle"', preview_source)
                self.assertIn('href="/styles.css"', preview_source)
                self.assertIn('href="/code-icon.ico', preview_source)
                resolved_output_dir = output_dir.resolve()
                resolved_root = ROOT.resolve()
                if resolved_output_dir.is_relative_to(resolved_root):
                    relative_output_dir = resolved_output_dir.relative_to(resolved_root).as_posix()
                    expected_bundle_url = f"/{relative_output_dir}/code.bundle.js"
                else:
                    expected_bundle_url = "./code.bundle.js"
                bundle_assignment = f'bundleScript.src = "{expected_bundle_url}";'
                fallback_assignment = (
                    'const fallback = new URL("./index.classic.html", window.location.href);'
                )
                replacement_count = preview_source.count(bundle_assignment)
                self.assertEqual(replacement_count, 1)
                self.assertEqual(preview_source.count(fallback_assignment), 1)
                self.assertNotRegex(
                    preview_source,
                    r'<script src="\./(?:src/[^\"]+|agent-runtime\.js|app\.js)"></script>',
                )
                self.assertLess(
                    preview_source.index('id="importModal"'),
                    preview_source.index(fallback_assignment),
                )
                self.assertLess(
                    preview_source.index(fallback_assignment),
                    preview_source.index(bundle_assignment),
                )
                normalized_bundle_assignment = (
                    'bundleScript.src = "__DETERMINISTIC_BUNDLE_URL__";'
                )
                normalized_preview = preview_source.replace(
                    bundle_assignment,
                    normalized_bundle_assignment,
                    1,
                )
                self.assertEqual(
                    normalized_preview.count(normalized_bundle_assignment),
                    replacement_count,
                )
                self.assertNotIn(bundle_assignment, normalized_preview)
                normalized_previews.append(normalized_preview)
                self.assertIn("https://cdn.jsdelivr.net/npm/katex", preview_source)
                self.assertIn("https://cdn.jsdelivr.net/npm/marked", preview_source)
                self.assertIn('data-frontend-runtime="classic-fallback"', fallback_source)
                self.assertIn('href="/styles.css"', fallback_source)
                self.assertIn('href="/code-icon.ico', fallback_source)
                self.assertNotIn("code.bundle.js", fallback_source)
                fallback_scripts = re.findall(
                    r'<script src="(/(?:src/[^"]+|agent-runtime\.js|app\.js))"></script>',
                    fallback_source,
                )
                self.assertEqual(fallback_scripts, expected_fallback_scripts)
                self.assertEqual(fallback_scripts[-2:], ["/agent-runtime.js", "/app.js"])

                self.assertEqual(state_data["schemaVersion"], 1)
                self.assertEqual(state_data["esbuildVersion"], "0.28.1")
                self.assertRegex(state_data["sourceFingerprint"], r"^[0-9a-f]{64}$")
                for expected in (
                    "src/frontend-entry.js",
                    "index.html",
                    "package-lock.json",
                    "scripts/build-frontend.mjs",
                ):
                    self.assertIn(expected, state_data["inputs"])
                self.assertEqual(
                    set(state_data["outputs"]),
                    {
                        "code.bundle.js",
                        "code.bundle.js.map",
                        "code.bundle.meta.json",
                        "index.html",
                        "index.classic.html",
                    },
                )

                freshness = subprocess.run(
                    [
                        "node",
                        "scripts/build-frontend.mjs",
                        "--check",
                        "--outdir",
                        str(output_dir),
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=False,
                )
                self.assertEqual(
                    freshness.returncode,
                    0,
                    combined_output(freshness),
                )

                syntax = subprocess.run(
                    ["node", "--check", str(bundle)],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=False,
                )
                self.assertEqual(syntax.returncode, 0, combined_output(syntax))

                inputs = json.loads(metadata.read_text(encoding="utf-8"))["inputs"]
                for expected in (
                    "src/frontend-entry.js",
                    "src/core/namespace.js",
                    "src/agent/system-prompt.js",
                    "agent-runtime.js",
                    "app.js",
                ):
                    self.assertIn(expected, inputs)

            self.assertEqual(bundles[0], bundles[1])
            self.assertEqual(normalized_previews[0], normalized_previews[1])
            self.assertEqual(fallbacks[0], fallbacks[1])
            self.assertEqual(source_fingerprints[0], source_fingerprints[1])

            first_bundle = first / "code.bundle.js"
            original_bundle = first_bundle.read_bytes()
            first_bundle.write_bytes(original_bundle + b"\n// tampered\n")
            tampered = subprocess.run(
                ["node", "scripts/build-frontend.mjs", "--check", "--outdir", str(first)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            self.assertNotEqual(tampered.returncode, 0)
            self.assertIn("Frontend build output hash mismatch", combined_output(tampered))
            first_bundle.write_bytes(original_bundle)

            first_state = first / "code.bundle.state.json"
            original_state = first_state.read_text(encoding="utf-8")
            stale_state = json.loads(original_state)
            stale_state["sourceFingerprint"] = "0" * 64
            first_state.write_text(json.dumps(stale_state), encoding="utf-8")
            stale = subprocess.run(
                ["node", "scripts/build-frontend.mjs", "--check", "--outdir", str(first)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("source fingerprint changed", combined_output(stale))
            first_state.write_text(original_state, encoding="utf-8")

            first_fallback = first / "index.classic.html"
            first_fallback.unlink()
            missing = subprocess.run(
                ["node", "scripts/build-frontend.mjs", "--check", "--outdir", str(first)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("Frontend build output is missing", combined_output(missing))

    def test_namespace_defines_supported_buckets(self):
        source = (ROOT / "src/core/namespace.js").read_text(encoding="utf-8")
        for bucket in ("core", "services", "features", "agent", "ui"):
            self.assertIn(f'Code.{bucket} = Code.{bucket} || {{}}', source)

    def test_model_request_builds_stable_message_sequences(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/model-request.js");

const request = window.Code.agent.modelRequest;
const messages = [
  {
    role: "assistant",
    content: "checking",
    meta: {
      toolCalls: [
        {
          id: "call-1",
          type: "function",
          function: {name: "read_file", arguments: "{\"path\":\"A.md\"}"},
        },
        {
          id: "call-2",
          type: "function",
          function: {name: "read_file", arguments: "{\"path\":\"B.md\"}"},
        },
      ],
    },
  },
  {role: "tool-call", meta: {toolCallId: "call-1"}},
  {
    role: "tool-result",
    content: "A result",
    meta: {toolCallId: "call-1"},
  },
  {
    role: "user",
    content: [
      {type: "text", text: "next"},
      {type: "image_url", image_url: {url: "data:image/png;base64,x"}},
    ],
  },
  {
    role: "tool-result",
    content: "orphan",
    meta: {toolCallId: "missing"},
  },
  {role: "assistant", content: "pending", streaming: true},
  {role: "system", content: "hidden", meta: {skipApi: true}},
];
const before = JSON.stringify(messages);
const nativeMessages = request.buildModelRequestMessages(messages, true);
const fallbackMessages = request.buildModelRequestMessages(messages, false);
const textOnlyMessages = request.projectMessagesWithoutImages(messages);
const pureImageRetry = request.projectMessagesWithoutImages([{
  role: "user",
  content: [{type: "image_url", image_url: {url: "data:image/png;base64,AAAA"}}],
}]);
const generatedToolCall = request.buildNativeToolCallMessage({
  name: "search_files",
  arguments: "{\"query\":\"todo\"}",
});

process.stdout.write(JSON.stringify({
  frozen: Object.isFrozen(request),
  inputUnchanged: JSON.stringify(messages) === before,
  nativeMessages,
  fallbackMessages,
  hasImages: request.hasImageContent(messages),
  textOnlyMessages,
  pureImageRetry,
  generatedToolCall,
  invalid: request.mapMessageForApi(null),
  system: request.mapMessageForApi({role: "system", content: "rules"}),
  skipped: request.mapMessageForApi({
    role: "user",
    content: "private",
    meta: {skipApi: true},
  }),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["frozen"])
        self.assertTrue(data["inputUnchanged"])
        self.assertTrue(data["hasImages"])
        self.assertIsNone(data["invalid"])
        self.assertIsNone(data["skipped"])
        self.assertEqual(data["system"], {"role": "system", "content": "rules"})
        self.assertTrue(data["generatedToolCall"]["id"].startswith("call_"))
        self.assertEqual(data["generatedToolCall"]["type"], "function")
        self.assertEqual(
            data["generatedToolCall"]["function"],
            {"name": "search_files", "arguments": '{"query":"todo"}'},
        )

        native_messages = data["nativeMessages"]
        self.assertEqual(len(native_messages), 4)
        self.assertEqual(
            [call["id"] for call in native_messages[0]["tool_calls"]],
            ["call-1"],
        )
        self.assertEqual(
            native_messages[1],
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "content": "A result",
            },
        )
        self.assertEqual(native_messages[2]["content"][1]["type"], "image_url")
        self.assertEqual(
            native_messages[3],
            {"role": "user", "content": "[Tool result]\norphan"},
        )
        self.assertEqual(
            data["textOnlyMessages"][3]["content"],
            [{"type": "text", "text": "next"}],
        )
        self.assertIn(
            "text-only compatibility retry",
            data["pureImageRetry"][0]["content"][0]["text"],
        )
        self.assertNotIn("lastUser.content = textOnly", APP_SOURCE)
        self.assertIn("ctx._omitImagesForModelRequest = true", APP_SOURCE)

        fallback_messages = data["fallbackMessages"]
        self.assertEqual(len(fallback_messages), 4)
        self.assertNotIn("tool_calls", fallback_messages[0])
        self.assertEqual(
            fallback_messages[1],
            {"role": "user", "content": "【工具结果】\nA result"},
        )
        self.assertEqual(
            fallback_messages[3],
            {"role": "user", "content": "【工具结果】\norphan"},
        )

    def test_model_request_canonicalizes_tool_result_before_same_run_steer(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/model-request.js");

const request = window.Code.agent.modelRequest;
const messages = [
  {role: "user", content: "original"},
  {role: "assistant", content: "checking", meta: {
    agentRunId: "run-1",
    toolCalls: [{id: "call-1", type: "function", function: {
      name: "run_command",
      arguments: '{"command":"git status --short"}',
    }}],
  }},
  {role: "tool-call", meta: {agentRunId: "run-1", toolCallId: "call-1"}},
  {role: "user", content: "steer", meta: {steerDispatch: {
    agentRunId: "run-1",
    status: "accepted",
  }}},
  {role: "tool-result", content: "clean", meta: {
    agentRunId: "run-1",
    toolCallId: "call-1",
  }},
  {role: "assistant", content: "more", meta: {
    agentRunId: "run-1",
    toolCalls: [{id: "call-2", type: "function", function: {
      name: "read_file",
      arguments: '{"path":"VERSION"}',
    }}],
  }},
  {role: "tool-call", meta: {agentRunId: "run-1", toolCallId: "call-2"}},
  {role: "user", content: "second steer", meta: {steerDispatch: {
    agentRunId: "run-1",
    status: "accepted",
  }}},
  {role: "tool-result", content: "0.5.32", meta: {
    agentRunId: "run-1",
    toolCallId: "call-2",
  }},
  {role: "assistant", content: "done", meta: {agentRunId: "run-1"}},
];
const before = JSON.stringify(messages);
const canonical = request.canonicalizeSteerToolResultOrder(messages);
const nativeMessages = request.buildModelRequestMessages(messages, true);
process.stdout.write(JSON.stringify({
  inputUnchanged: JSON.stringify(messages) === before,
  canonicalRoles: canonical.map((message) => message.role),
  canonicalContent: canonical.map((message) => message.content || ""),
  nativeMessages,
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["inputUnchanged"])
        self.assertEqual(
            data["canonicalRoles"],
            [
                "user", "assistant", "tool-call", "tool-result", "user",
                "assistant", "tool-call", "tool-result", "user", "assistant",
            ],
        )
        self.assertEqual(data["canonicalContent"][3:5], ["clean", "steer"])
        self.assertEqual(
            [message["role"] for message in data["nativeMessages"]],
            ["user", "assistant", "tool", "user", "assistant", "tool", "user", "assistant"],
        )
        self.assertEqual(
            data["nativeMessages"][1]["tool_calls"][0]["id"],
            "call-1",
        )
        self.assertEqual(data["nativeMessages"][2]["tool_call_id"], "call-1")
        self.assertEqual(data["nativeMessages"][3]["content"], "steer")
        self.assertEqual(data["nativeMessages"][5]["tool_call_id"], "call-2")
        self.assertEqual(data["nativeMessages"][6]["content"], "second steer")

    def test_model_request_assembles_payload_fields_and_reasoning_controls(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/model-request.js");

const {assembleModelRequestPayload} = window.Code.agent.modelRequest;
const tool = {
  type: "function",
  function: {name: "read_file", parameters: {type: "object"}},
};
const input = {
  model: "claude-sonnet",
  tools: [tool],
  modelMessages: [{role: "user", content: "hello"}],
  systemPrompt: "rules",
  includeSystemPrompt: true,
  temperature: 0.3,
  maxTokens: 1234,
  thinkingLevel: "high",
};
const before = JSON.stringify(input);
const assemble = (model, thinkingLevel, extra = {}) => assembleModelRequestPayload({
  model,
  thinkingLevel,
  modelMessages: [{role: "user", content: "hello"}],
  temperature: 0.2,
  maxTokens: 2048,
  ...extra,
});

process.stdout.write(JSON.stringify({
  inputUnchanged: JSON.stringify(input) === before,
  base: assembleModelRequestPayload(input),
  subAgent: assemble("plain-model", "off", {
    systemPrompt: "must-not-appear",
    includeSystemPrompt: false,
  }),
  claude: {
    off: assemble("claude-3-7-sonnet", "off"),
    auto: assemble("claude-3-7-sonnet", "auto"),
    high: assemble("claude-3-7-sonnet", "high"),
    max: assemble("claude-3-7-sonnet", "max"),
  },
  openai: {
    off: assemble("o3", "off"),
    auto: assemble("o3", "auto"),
    high: assemble("o3", "high"),
    max: assemble("o3", "max"),
  },
  gemini: {
    off: assemble("gemini-3-pro", "off"),
    auto: assemble("nano-banana-pro", "auto"),
    high: assemble("gemini-3-pro", "high"),
    max: assemble("nano-banana-pro", "max"),
  },
  other: assemble("gpt-4.1", "max"),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["inputUnchanged"])

        base = data["base"]
        self.assertEqual(
            {key: base[key] for key in (
                "model", "stream", "stream_options", "temperature", "max_tokens",
            )},
            {
                "model": "claude-sonnet",
                "stream": True,
                "stream_options": {"include_usage": True},
                "temperature": 0.3,
                "max_tokens": 1234,
            },
        )
        self.assertEqual(base["messages"], [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "hello"},
        ])
        self.assertEqual(base["tools"], [{
            "type": "function",
            "function": {"name": "read_file", "parameters": {"type": "object"}},
        }])
        self.assertEqual(base["tool_choice"], "auto")
        self.assertEqual(base["thinking"], {"type": "enabled", "budget_tokens": 8000})

        sub_agent = data["subAgent"]
        self.assertEqual(sub_agent["messages"], [{"role": "user", "content": "hello"}])
        self.assertNotIn("tools", sub_agent)
        self.assertNotIn("tool_choice", sub_agent)

        self.assertEqual(data["claude"]["off"]["thinking"], {"type": "disabled"})
        self.assertEqual(data["claude"]["auto"]["thinking"]["budget_tokens"], 4000)
        self.assertEqual(data["claude"]["high"]["thinking"]["budget_tokens"], 8000)
        self.assertEqual(data["claude"]["max"]["thinking"]["budget_tokens"], 16000)

        self.assertNotIn("reasoning_effort", data["openai"]["off"])
        self.assertEqual(data["openai"]["auto"]["reasoning_effort"], "low")
        self.assertEqual(data["openai"]["high"]["reasoning_effort"], "medium")
        self.assertEqual(data["openai"]["max"]["reasoning_effort"], "high")

        self.assertNotIn("reasoning_effort", data["gemini"]["off"])
        self.assertNotIn("reasoning_effort", data["gemini"]["auto"])
        self.assertEqual(data["gemini"]["high"]["reasoning_effort"], "high")
        self.assertEqual(data["gemini"]["max"]["reasoning_effort"], "high")
        self.assertNotIn("reasoning_effort", data["other"])
        self.assertNotIn("thinking", data["other"])

    def test_model_request_payload_keeps_async_preparation_and_runtime_in_app(self):
        start = APP_SOURCE.index("async function buildModelRequestPayload(")
        end = APP_SOURCE.index("async function _callModelOnceAttempt(", start)
        adapter_source = APP_SOURCE[start:end]
        runtime_source = APP_SOURCE[end:]
        app_imports = APP_SOURCE[:start]

        self.assertIn("await loadProjectContextForRoot(", adapter_source)
        self.assertIn("await getTaskSystemPrompt(ctx, systemPromptOptions)", adapter_source)
        self.assertIn("await getSystemPrompt(systemPromptOptions)", adapter_source)
        self.assertIn("assembleModelRequestPayload({", adapter_source)
        self.assertNotIn("buildModelRequestMessages,", app_imports)
        self.assertNotIn("function isTransientModelError", APP_SOURCE)
        self.assertNotIn("loadProjectContextForRoot", MODEL_REQUEST_SOURCE)
        self.assertNotIn("getSystemPrompt(", MODEL_REQUEST_SOURCE)
        self.assertNotIn("fetch(", MODEL_REQUEST_SOURCE)
        self.assertNotIn("AbortController", MODEL_REQUEST_SOURCE)
        self.assertIn("agentRuntime.openSseResponse({", runtime_source)
        self.assertIn('fetch("/proxy/chat", {', runtime_source)

    def test_agent_tools_normalize_native_calls_without_mutating_inputs(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/model-request.js");
require("./src/agent/tools.js");

const tools = window.Code.agent.tools;
const objectArgs = {path: "A.md", action: "wrong"};
const nativeCall = {
  id: "call-1",
  type: "function",
  function: {name: "read_file", arguments: objectArgs},
};
const before = JSON.stringify(nativeCall);
const normalized = tools.normalizeNativeToolCall(nativeCall);
const generated = tools.normalizeNativeToolCall({
  name: "search_files",
  arguments: "{\"query\":\"todo\"}",
});
const callsByIndex = new Map([
  [3, {id: "call-empty", function: {name: "", arguments: "{}"}}],
  [2, {id: "call-2", function: {name: "read_file", arguments: "{}"}}],
  [1, {id: "call-1", function: {name: "list_files", arguments: "{}"}}],
]);
const callsBefore = JSON.stringify([...callsByIndex.entries()]);
const normalizedList = tools.normalizeToolCallList(callsByIndex);

process.stdout.write(JSON.stringify({
  frozen: Object.isFrozen(tools),
  inputUnchanged: JSON.stringify(nativeCall) === before,
  mapUnchanged: JSON.stringify([...callsByIndex.entries()]) === callsBefore,
  sameObject: tools.parseJsonLoose(objectArgs) === objectArgs,
  invalid: tools.parseJsonLoose("{broken"),
  empty: tools.parseJsonLoose(""),
  normalized,
  generated,
  normalizedList,
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["frozen"])
        self.assertTrue(data["inputUnchanged"])
        self.assertTrue(data["mapUnchanged"])
        self.assertTrue(data["sameObject"])
        self.assertEqual(data["invalid"], {})
        self.assertEqual(data["empty"], {})
        self.assertEqual(
            data["normalized"],
            {
                "path": "A.md",
                "action": "read_file",
                "_native": True,
                "_toolCallId": "call-1",
            },
        )
        self.assertEqual(data["generated"]["action"], "search_files")
        self.assertEqual(data["generated"]["query"], "todo")
        self.assertTrue(data["generated"]["_toolCallId"].startswith("call_"))
        self.assertEqual(
            [call["function"]["name"] for call in data["normalizedList"]],
            ["list_files", "read_file"],
        )
        self.assertEqual(
            [call["id"] for call in data["normalizedList"]],
            ["call-1", "call-2"],
        )
        self.assertIn(
            "const { buildNativeToolCallMessage } = agent.modelRequest;",
            TOOLS_SOURCE,
        )
        self.assertIn(
            "} = window.Code.agent.tools;",
            APP_SOURCE[:APP_SOURCE.index("function upgradeStaticIcons")],
        )
        self.assertNotIn("function parseJsonLoose", APP_SOURCE)
        self.assertNotIn("function normalizeNativeToolCall", APP_SOURCE)
        self.assertNotIn("function normalizeToolCallList", APP_SOURCE)

    def test_agent_tools_exports_stable_native_tool_schema(self):
        script = r"""
const crypto = require("crypto");
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/model-request.js");
require("./src/agent/tools.js");

const definitions = window.Code.agent.tools.nativeTools;
const before = JSON.stringify(definitions);
const selected = definitions.filter((tool) => ["request_user_input", "read_file"].includes(tool.function.name));
const byName = Object.fromEntries(definitions.map((tool) => [tool.function.name, tool]));

process.stdout.write(JSON.stringify({
  names: definitions.map((tool) => tool.function.name),
  hash: crypto.createHash("sha256").update(before).digest("hex"),
  unchanged: JSON.stringify(definitions) === before,
  selectedNames: selected.map((tool) => tool.function.name),
  selectionIsNewArray: selected !== definitions,
  questionnaireOptionLimit:
    byName.request_user_input.function.parameters.properties.questions.items.properties.options.maxItems,
  runCommandProperties: Object.keys(byName.run_command.function.parameters.properties),
  saveMemoryRequired: byName.save_memory.function.parameters.required,
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(
            data["names"],
            [
                "request_user_input",
                "list_files",
                "read_file",
                "search_files",
                "glob_files",
                "propose_edit",
                "run_command",
                "task",
                "use_skill",
                "check_skill_dependencies",
                "read_skill_resource",
                "write_file",
                "delete_file",
                "web_fetch",
                "save_memory",
            ],
        )
        self.assertEqual(
            data["hash"],
            "65c3320c6550f0b2391c9d77e84760e8e901881a88a717e6fc0bea74b97373df",
        )
        self.assertTrue(data["unchanged"])
        self.assertTrue(data["selectionIsNewArray"])
        self.assertEqual(data["selectedNames"], ["request_user_input", "read_file"])
        self.assertIsNone(data.get("questionnaireOptionLimit"))
        self.assertEqual(data["runCommandProperties"], ["command"])
        self.assertEqual(
            data["saveMemoryRequired"],
            ["name", "description", "body"],
        )
        self.assertIn("const nativeTools = [", TOOLS_SOURCE)
        self.assertIn(
            "nativeTools,",
            APP_SOURCE[:APP_SOURCE.index("function upgradeStaticIcons")],
        )
        self.assertNotIn("const nativeTools = [", APP_SOURCE)

    def test_agent_permissions_select_stable_profile_tools_without_shared_mutation(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/permissions.js");

const permissions = window.Code.agent.permissions;
const profiles = Object.fromEntries(
  ["read", "plan", "accept", "bypass"].map((profile) => [
    profile,
    [...permissions.getAllowedToolNamesForProfile(profile)],
  ]),
);
const firstRead = permissions.getAllowedToolNamesForProfile("read");
firstRead.add("run_command");
const secondRead = permissions.getAllowedToolNamesForProfile("read");

process.stdout.write(JSON.stringify({
  frozen: Object.isFrozen(permissions),
  profiles,
  unknown: [...permissions.getAllowedToolNamesForProfile("unknown")],
  planFull: [...permissions.getAllowedToolNamesForProfile("plan", "full")],
  readIsolated: !secondRead.has("run_command"),
  owners: Object.fromEntries(
    ["read", "plan", "accept", "bypass", "unknown"].map((profile) => [
      profile,
      permissions.executionOwnerForPermissionProfile(profile),
    ]),
  ),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["frozen"])
        self.assertTrue(data["readIsolated"])
        self.assertEqual(
            data["profiles"]["read"],
            [
                "request_user_input",
                "list_files",
                "read_file",
                "search_files",
                "glob_files",
                "check_skill_dependencies",
            ],
        )
        self.assertEqual(
            data["profiles"]["plan"],
            [
                "request_user_input",
                "list_files",
                "read_file",
                "search_files",
                "glob_files",
                "web_fetch",
                "propose_edit",
                "task",
                "use_skill",
                "check_skill_dependencies",
                "read_skill_resource",
            ],
        )
        self.assertEqual(
            data["profiles"]["accept"],
            [
                "request_user_input",
                "list_files",
                "read_file",
                "search_files",
                "glob_files",
                "web_fetch",
                "propose_edit",
                "run_command",
                "task",
                "use_skill",
                "check_skill_dependencies",
                "write_file",
                "delete_file",
                "save_memory",
                "read_skill_resource",
            ],
        )
        self.assertEqual(data["profiles"]["accept"], data["profiles"]["bypass"])
        self.assertEqual(data["unknown"], data["profiles"]["accept"])
        self.assertNotIn("run_command", data["planFull"])
        self.assertEqual(
            data["owners"],
            {
                "read": "server-agent",
                "plan": "server-agent",
                "accept": "server-agent",
                "bypass": "server-agent",
                "unknown": "browser",
            },
        )
        self.assertIn(
            "} = window.Code.agent.permissions;",
            APP_SOURCE[:APP_SOURCE.index("function upgradeStaticIcons")],
        )
        self.assertNotIn("const toolPolicy =", APP_SOURCE)
        self.assertNotIn("function executionOwnerForPermissionProfile", APP_SOURCE)
        self.assertNotIn("function getAllowedToolNamesForProfile", APP_SOURCE)

    def test_auto_permission_risk_gate_is_versioned_cancel_safe_and_coalesces_confirmation(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/permissions.js");

const permissions = window.Code.agent.permissions;
class Storage {
  constructor(values = {}) { this.values = new Map(Object.entries(values)); }
  getItem(key) { return this.values.has(key) ? this.values.get(key) : null; }
  setItem(key, value) { this.values.set(key, String(value)); }
  removeItem(key) { this.values.delete(key); }
}

(async () => {
  const storage = new Storage({"code-permission-profile": "accept"});
  let profile = "accept";
  const decisions = [false, true, true];
  const reasons = [];
  const committed = [];
  const gate = permissions.createAutoPermissionRiskGate({
    storage,
    getProfile: () => profile,
    onProfileCommitted: (value) => { profile = value; committed.push(value); },
    requestConfirmation: async ({reason}) => { reasons.push(reason); return decisions.shift(); },
  });

  const selectionCancelled = await gate.requestProfileTransition("bypass");
  const afterCancel = {
    profile,
    stored: storage.getItem("code-permission-profile"),
    ack: storage.getItem(permissions.AUTO_PERMISSION_ACK_KEY),
  };
  const selectionConfirmed = await gate.requestProfileTransition("bypass");
  const afterConfirm = {
    profile,
    stored: storage.getItem("code-permission-profile"),
    ack: storage.getItem(permissions.AUTO_PERMISSION_ACK_KEY),
    acknowledged: gate.isAutoAcknowledged(),
  };
  const switchedAway = await gate.requestProfileTransition("plan");
  const afterSwitchAway = {
    profile,
    ack: storage.getItem(permissions.AUTO_PERMISSION_ACK_KEY),
  };
  const reentered = await gate.requestProfileTransition("bypass");

  const legacyStorage = new Storage({"code-permission-profile": "bypass"});
  let legacyProfile = "bypass";
  let legacyResolve;
  let legacyConfirmations = 0;
  const legacyGate = permissions.createAutoPermissionRiskGate({
    storage: legacyStorage,
    getProfile: () => legacyProfile,
    onProfileCommitted: (value) => { legacyProfile = value; },
    requestConfirmation: () => {
      legacyConfirmations += 1;
      return new Promise((resolve) => { legacyResolve = resolve; });
    },
  });
  const firstPending = legacyGate.ensureDispatchConfirmed();
  const secondPending = legacyGate.ensureDispatchConfirmed();
  await Promise.resolve();
  legacyResolve(true);
  const legacyResults = await Promise.all([firstPending, secondPending]);

  const cancelStorage = new Storage({"code-permission-profile": "bypass"});
  let cancelProfile = "bypass";
  const cancelGate = permissions.createAutoPermissionRiskGate({
    storage: cancelStorage,
    getProfile: () => cancelProfile,
    onProfileCommitted: (value) => { cancelProfile = value; },
    requestConfirmation: async () => false,
  });
  const legacyCancelled = await cancelGate.ensureDispatchConfirmed();

  process.stdout.write(JSON.stringify({
    constants: {
      key: permissions.AUTO_PERMISSION_ACK_KEY,
      version: permissions.AUTO_PERMISSION_ACK_VERSION,
    },
    selectionCancelled,
    afterCancel,
    selectionConfirmed,
    afterConfirm,
    switchedAway,
    afterSwitchAway,
    reentered,
    reasons,
    committed,
    legacy: {
      neededBefore: true,
      results: legacyResults,
      confirmations: legacyConfirmations,
      profile: legacyProfile,
      ack: legacyStorage.getItem(permissions.AUTO_PERMISSION_ACK_KEY),
      neededAfter: legacyGate.requiresDispatchConfirmation(),
    },
    legacyCancel: {
      result: legacyCancelled,
      profile: cancelProfile,
      stored: cancelStorage.getItem("code-permission-profile"),
      ack: cancelStorage.getItem(permissions.AUTO_PERMISSION_ACK_KEY),
    },
  }));
})().catch((error) => { console.error(error); process.exitCode = 1; });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["constants"], {"key": "code-auto-permission-risk-ack", "version": "v1"})
        self.assertFalse(data["selectionCancelled"])
        self.assertEqual(data["afterCancel"], {"profile": "accept", "stored": "accept", "ack": None})
        self.assertTrue(data["selectionConfirmed"])
        self.assertEqual(
            data["afterConfirm"],
            {"profile": "bypass", "stored": "bypass", "ack": "v1", "acknowledged": True},
        )
        self.assertTrue(data["switchedAway"])
        self.assertEqual(data["afterSwitchAway"], {"profile": "plan", "ack": None})
        self.assertTrue(data["reentered"])
        self.assertEqual(data["reasons"], ["selection", "selection", "selection"])
        self.assertEqual(data["committed"], ["bypass", "plan", "bypass"])
        self.assertEqual(
            data["legacy"],
            {
                "neededBefore": True,
                "results": [True, True],
                "confirmations": 1,
                "profile": "bypass",
                "ack": "v1",
                "neededAfter": False,
            },
        )
        self.assertEqual(
            data["legacyCancel"],
            {"result": False, "profile": "accept", "stored": "accept", "ack": None},
        )

    def test_auto_permission_dialog_gates_dispatch_before_side_effects_and_is_accessible(self):
        self.assertIn('id="autoPermissionConfirmModal"', INDEX_SOURCE)
        self.assertIn('role="alertdialog"', INDEX_SOURCE)
        self.assertIn('aria-labelledby="autoPermissionRiskTitle"', INDEX_SOURCE)
        self.assertIn('aria-describedby="autoPermissionRiskDescription"', INDEX_SOURCE)
        self.assertIn('id="cancelAutoPermissionConfirm"', INDEX_SOURCE)
        self.assertIn('id="confirmAutoPermission"', INDEX_SOURCE)
        self.assertIn(".auto-permission-risk-card {", STYLE_SOURCE)
        self.assertIn(".auto-permission-risk-heading {", STYLE_SOURCE)
        self.assertIn(".auto-permission-capabilities {", STYLE_SOURCE)
        self.assertIn(".auto-permission-capability + .auto-permission-capability {", STYLE_SOURCE)
        self.assertIn(".auto-permission-risk-limits {", STYLE_SOURCE)
        self.assertIn(".danger-btn.auto-permission-enable-btn {", STYLE_SOURCE)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", STYLE_SOURCE)
        self.assertEqual(INDEX_SOURCE.count('class="auto-permission-capability"'), 3)
        self.assertEqual(INDEX_SOURCE.count('class="auto-permission-capability-icon"'), 3)
        self.assertIn('class="auto-permission-warning-icon" aria-hidden="true"', INDEX_SOURCE)
        self.assertNotIn("auto-permission-risk-list", INDEX_SOURCE)
        self.assertNotIn("auto-permission-risk-repeat", INDEX_SOURCE)

        selection_start = APP_SOURCE.index('els.permPillDropdown.addEventListener("click"')
        selection_end = APP_SOURCE.index('document.addEventListener("click"', selection_start)
        selection_source = APP_SOURCE[selection_start:selection_end]
        self.assertIn("await autoPermissionGate.requestProfileTransition(val);", selection_source)
        self.assertNotIn('localStorage.setItem("code-permission-profile", val)', selection_source)
        self.assertNotIn("setPermLevel(val)", selection_source)

        submit_start = APP_SOURCE.index('els.chatForm.addEventListener("submit"')
        submit_end = APP_SOURCE.index('els.newChat.addEventListener("click"', submit_start)
        submit_source = APP_SOURCE[submit_start:submit_end]
        local_command_index = submit_source.index("handleUiSlashCommand(text)")
        gate_index = submit_source.index("autoPermissionGate.requiresDispatchConfirmation()")
        clear_index = submit_source.index('els.prompt.value = "";', gate_index)
        self.assertLess(local_command_index, gate_index)
        self.assertLess(gate_index, clear_index)
        for side_effect in (
            "dispatchBackgroundSubAgent(sessionId, taskText, imgs)",
            "dispatch(sessionId, taskText, imgs)",
            "await sendMessage(text, {",
        ):
            self.assertLess(gate_index, submit_source.index(side_effect))
        self.assertIn("if (autoPermissionDispatchConfirmationPending) return;", submit_source)
        self.assertIn("confirmed = await autoPermissionGate.ensureDispatchConfirmed();", submit_source)
        self.assertLess(gate_index, submit_source.index("consumeFollowUpBehaviorOverride()"))

        dialog_start = APP_SOURCE.index("function showAutoPermissionRiskConfirm(")
        dialog_end = APP_SOURCE.index("const autoPermissionGate =", dialog_start)
        dialog_source = APP_SOURCE[dialog_start:dialog_end]
        self.assertIn('document.addEventListener("keydown", onKeyDown, true);', dialog_source)
        self.assertIn('document.addEventListener("focusin", onFocusIn, true);', dialog_source)
        self.assertIn('document.removeEventListener("focusin", onFocusIn, true);', dialog_source)
        self.assertIn("settled || modal.contains(event.target)", dialog_source)
        self.assertIn('event.key === "Escape"', dialog_source)
        self.assertIn('event.key !== "Tab"', dialog_source)
        self.assertIn("const focusDefaultIfVisible = () => {", dialog_source)
        self.assertIn('style.visibility !== "visible"', dialog_source)
        self.assertIn('modal.addEventListener("transitionend", onInitialFocusTransition);', dialog_source)
        self.assertIn('modal.addEventListener("transitioncancel", onInitialFocusTransition);', dialog_source)
        self.assertIn('event.target !== modal || !["opacity", "visibility"].includes(event.propertyName)', dialog_source)
        self.assertIn("initialFocusTimer = setTimeout(() => {", dialog_source)
        self.assertIn("clearTimeout(initialFocusTimer);", dialog_source)
        self.assertIn("transitionBudgetMs() + 32", dialog_source)
        self.assertIn("cancelButton.focus({ preventScroll: true });", dialog_source)
        transition_listener_index = dialog_source.index(
            'modal.addEventListener("transitionend", onInitialFocusTransition);'
        )
        show_index = dialog_source.index('modal.classList.remove("hidden");')
        focus_attempt_index = dialog_source.index("if (focusDefaultIfVisible())", show_index)
        fallback_index = dialog_source.index("initialFocusTimer = setTimeout", focus_attempt_index)
        self.assertLess(transition_listener_index, show_index)
        self.assertLess(show_index, focus_attempt_index)
        self.assertLess(focus_attempt_index, fallback_index)
        finish_index = dialog_source.index("const finish = (confirmed) => {")
        finish_cleanup_index = dialog_source.index("clearInitialFocusScheduling();", finish_index)
        focus_restore_index = dialog_source.index("previousFocus.focus();", finish_index)
        self.assertLess(finish_cleanup_index, focus_restore_index)
        self.assertNotIn("requestAnimationFrame", dialog_source)
        self.assertNotIn("queueMicrotask", dialog_source)
        self.assertNotIn('event.key === "Enter"', dialog_source)
        self.assertIn("await expect(cancelPermissionConfirm).toBeFocused();", H4_SMOKE_SOURCE)
        self.assertIn("Active element at focus timeout:", H4_SMOKE_SOURCE)
        auto_h4_start = H4_SMOKE_SOURCE.index("async function exerciseAutoPermissionRiskGate(")
        auto_h4_end = H4_SMOKE_SOURCE.index('\ntest("', auto_h4_start)
        auto_h4_source = H4_SMOKE_SOURCE[auto_h4_start:auto_h4_end]
        bring_to_front_index = auto_h4_source.index("await page.bringToFront();")
        page_focus_index = auto_h4_source.index("document.hasFocus()")
        first_selection_index = auto_h4_source.index('await selectPermission("bypass");')
        self.assertLess(bring_to_front_index, page_focus_index)
        self.assertLess(page_focus_index, first_selection_index)
        self.assertIn("documentHasFocus: document.hasFocus()", auto_h4_source)

        for key in (
            "autoPermissionRiskTitle",
            "autoPermissionRiskLead",
            "autoPermissionFilesTitle",
            "autoPermissionFilesDescription",
            "autoPermissionCommandsTitle",
            "autoPermissionCommandsDescription",
            "autoPermissionNetworkTitle",
            "autoPermissionNetworkDescription",
            "autoPermissionRiskLimits",
            "autoPermissionKeepCurrent",
            "autoPermissionEnable",
            "autoPermissionSaveFailed",
        ):
            self.assertIn(f'{key}: "', I18N_SOURCE)
        for removed_key in ("autoPermissionRiskDifference", "autoPermissionRiskRepeat"):
            self.assertNotIn(removed_key, INDEX_SOURCE)
            self.assertNotIn(removed_key, I18N_SOURCE)

        fallback_copy = (
            "Code 将不再逐项等待您的确认，自动执行当前任务允许的文件、命令和工具操作。仅在您信任当前任务和工作区时启用。",
            "读取、创建、修改或删除项目文件",
            "运行命令、使用 Skills，并启动子任务",
            "获取网页内容或调用已启用的联网能力",
            "服务端安全限制仍然有效：越界路径、危险或系统级命令、破坏性 Git、工具预算和参数校验仍会被拦截。",
        )
        for copy in fallback_copy:
            self.assertIn(copy, INDEX_SOURCE)

        translated_copy = (
            'autoPermissionRiskTitle: "Enable Auto mode?"',
            'autoPermissionRiskLead: "Code will stop asking for approval for each action and automatically perform file, command, and tool operations allowed for the current task. Enable it only when you trust the current task and workspace."',
            'autoPermissionFilesTitle: "Files and edits"',
            'autoPermissionFilesDescription: "Read, create, modify, or delete project files"',
            'autoPermissionCommandsTitle: "Commands and tools"',
            'autoPermissionCommandsDescription: "Run commands, use Skills, and start subtasks"',
            'autoPermissionNetworkTitle: "Network access"',
            'autoPermissionNetworkDescription: "Fetch web content or use enabled network capabilities"',
            'autoPermissionRiskLimits: "Server-enforced safety limits still apply: out-of-scope paths, dangerous or system-level commands, destructive Git operations, tool budgets, and argument validation remain blocked."',
            'autoPermissionKeepCurrent: "Cancel"',
            'autoPermissionEnable: "Enable Auto mode"',
        )
        for copy in translated_copy:
            self.assertIn(copy, I18N_SOURCE)
        self.assertNotIn("完全访问权限", INDEX_SOURCE)
        self.assertNotIn("Full access", I18N_SOURCE)

    def test_auto_permission_dialog_initial_focus_is_deferred_and_cancel_safe(self):
        dialog_start = APP_SOURCE.index("function showAutoPermissionRiskConfirm(")
        dialog_end = APP_SOURCE.index("const autoPermissionGate =", dialog_start)
        dialog_source = APP_SOURCE[dialog_start:dialog_end].strip()
        script = f"""
const showAutoPermissionRiskConfirm = eval("(" + {json.dumps(dialog_source)} + ")");

function fakeElement(name) {{
  const listeners = new Map();
  return {{
    name,
    isConnected: true,
    dataset: {{}},
    attributes: new Map(),
    focusCalls: [],
    computedVisibility: "visible",
    transitionDuration: "0s",
    transitionDelay: "0s",
    classList: {{
      values: new Set(["hidden"]),
      add(value) {{ this.values.add(value); }},
      remove(value) {{ this.values.delete(value); }},
      contains(value) {{ return this.values.has(value); }},
    }},
    addEventListener(type, listener) {{ listeners.set(type, listener); }},
    removeEventListener(type, listener) {{
      if (listeners.get(type) === listener) listeners.delete(type);
    }},
    dispatch(type, event = {{}}) {{ listeners.get(type)?.({{ target: this, ...event }}); }},
    listenerCount(type) {{ return listeners.has(type) ? 1 : 0; }},
    setAttribute(key, value) {{ this.attributes.set(key, value); }},
    contains() {{ return false; }},
    focus(options) {{
      this.focusCalls.push(options || null);
      document.activeElement = this;
      document.dispatch("focusin", {{ target: this }});
    }},
  }};
}}

const documentListeners = new Map();
let focusinAdds = 0;
const previousFocus = fakeElement("previous");
const document = {{
  activeElement: previousFocus,
  addEventListener(type, listener) {{
    if (!documentListeners.has(type)) documentListeners.set(type, new Set());
    documentListeners.get(type).add(listener);
    if (type === "focusin") focusinAdds += 1;
  }},
  removeEventListener(type, listener) {{
    documentListeners.get(type)?.delete(listener);
  }},
  dispatch(type, event) {{
    for (const listener of [...(documentListeners.get(type) || [])]) listener(event);
  }},
  listenerCount(type) {{ return documentListeners.get(type)?.size || 0; }},
}};
const modal = fakeElement("modal");
const closeButton = fakeElement("close");
const cancelButton = fakeElement("cancel");
const confirmButton = fakeElement("confirm");
const outsideButton = fakeElement("outside");
modal.contains = (node) => [modal, closeButton, cancelButton, confirmButton].includes(node);
const els = {{
  autoPermissionConfirmModal: modal,
  closeAutoPermissionConfirm: closeButton,
  cancelAutoPermissionConfirm: cancelButton,
  confirmAutoPermission: confirmButton,
  permPillDropdown: fakeElement("dropdown"),
  permPillBtn: fakeElement("pill"),
}};

function getComputedStyle(element) {{
  return {{
    display: "grid",
    visibility: element.computedVisibility,
    transitionDuration: element.transitionDuration,
    transitionDelay: element.transitionDelay,
  }};
}}

let nextTimerId = 0;
const timers = new Map();
const cancelledTimers = [];
function setTimeout(callback, delay) {{
  const id = ++nextTimerId;
  timers.set(id, {{ callback, delay }});
  return id;
}}
function clearTimeout(id) {{
  cancelledTimers.push(id);
  timers.delete(id);
}}

(async () => {{
  modal.computedVisibility = "visible";
  modal.transitionDuration = "0s";
  let immediateSettled = false;
  const immediatePromise = showAutoPermissionRiskConfirm({{ reason: "selection" }});
  immediatePromise.then(() => {{ immediateSettled = true; }});
  await Promise.resolve();
  const immediateState = {{
    active: document.activeElement.name,
    settled: immediateSettled,
    scheduledTimers: nextTimerId,
    pendingTimers: timers.size,
    focusinListeners: document.listenerCount("focusin"),
    transitionListeners: modal.listenerCount("transitionend"),
  }};
  cancelButton.dispatch("click");
  const immediateResult = await immediatePromise;

  cancelButton.focusCalls = [];
  modal.computedVisibility = "hidden";
  modal.transitionDuration = "0.2s, 0.2s";
  modal.transitionDelay = "0s";
  const transitionPromise = showAutoPermissionRiskConfirm({{ reason: "selection" }});
  const beforeTransition = {{
    active: document.activeElement.name,
    pendingTimer: timers.has(1),
    timerDelay: timers.get(1)?.delay,
    cancelFocusCalls: [...cancelButton.focusCalls],
    focusinListeners: document.listenerCount("focusin"),
    transitionListeners: modal.listenerCount("transitionend"),
  }};
  modal.computedVisibility = "visible";
  modal.dispatch("transitionend", {{ propertyName: "visibility" }});
  outsideButton.focus();
  const afterTransition = {{
    active: document.activeElement.name,
    cancelFocusCalls: [...cancelButton.focusCalls],
    timerCancelled: cancelledTimers.includes(1),
    transitionListeners: modal.listenerCount("transitionend"),
  }};
  document.dispatch("keydown", {{
    key: "Escape",
    preventDefault() {{}},
    stopPropagation() {{}},
  }});
  const transitionResult = await transitionPromise;

  cancelButton.focusCalls = [];
  modal.computedVisibility = "hidden";
  const fallbackPromise = showAutoPermissionRiskConfirm({{ reason: "legacy-dispatch" }});
  const beforeFallback = {{
    active: document.activeElement.name,
    pendingTimer: timers.has(2),
    timerDelay: timers.get(2)?.delay,
    focusinListeners: document.listenerCount("focusin"),
  }};
  modal.computedVisibility = "visible";
  const fallbackCallback = timers.get(2).callback;
  timers.delete(2);
  fallbackCallback();
  const afterFallback = {{
    cancelFocusCalls: [...cancelButton.focusCalls],
    active: document.activeElement.name,
    transitionListeners: modal.listenerCount("transitionend"),
  }};
  document.dispatch("keydown", {{
    key: "Escape",
    preventDefault() {{}},
    stopPropagation() {{}},
  }});
  const fallbackResult = await fallbackPromise;

  cancelButton.focusCalls = [];
  modal.computedVisibility = "hidden";
  const cancelledPromise = showAutoPermissionRiskConfirm({{ reason: "selection" }});
  const cancelledCallback = timers.get(3).callback;
  cancelButton.dispatch("click");
  const cancelledResult = await cancelledPromise;
  modal.computedVisibility = "visible";
  modal.dispatch("transitionend", {{ propertyName: "visibility" }});
  cancelledCallback();
  const afterEarlyCancel = {{
    result: cancelledResult,
    cancelledTimers: [...cancelledTimers],
    cancelFocusCalls: [...cancelButton.focusCalls],
    active: document.activeElement.name,
    focusinListeners: document.listenerCount("focusin"),
    transitionListeners: modal.listenerCount("transitionend"),
  }};

  process.stdout.write(JSON.stringify({{
    immediateState,
    immediateResult,
    beforeTransition,
    afterTransition,
    transitionResult,
    beforeFallback,
    afterFallback,
    fallbackResult,
    afterEarlyCancel,
    previousFocusCalls: previousFocus.focusCalls.length,
    active: document.activeElement.name,
    focusinAdds,
    focusinListenersAfterFinish: document.listenerCount("focusin"),
  }}));
}})().catch((error) => {{ console.error(error); process.exitCode = 1; }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(
            data["immediateState"],
            {
                "active": "cancel",
                "settled": False,
                "scheduledTimers": 0,
                "pendingTimers": 0,
                "focusinListeners": 1,
                "transitionListeners": 0,
            },
        )
        self.assertFalse(data["immediateResult"])
        self.assertEqual(
            data["beforeTransition"],
            {
                "active": "previous",
                "pendingTimer": True,
                "timerDelay": 232,
                "cancelFocusCalls": [],
                "focusinListeners": 1,
                "transitionListeners": 1,
            },
        )
        self.assertEqual(
            data["afterTransition"],
            {
                "active": "cancel",
                "cancelFocusCalls": [
                    {"preventScroll": True},
                    {"preventScroll": True},
                ],
                "timerCancelled": True,
                "transitionListeners": 0,
            },
        )
        self.assertFalse(data["transitionResult"])
        self.assertEqual(
            data["beforeFallback"],
            {
                "active": "previous",
                "pendingTimer": True,
                "timerDelay": 232,
                "focusinListeners": 1,
            },
        )
        self.assertEqual(
            data["afterFallback"],
            {
                "cancelFocusCalls": [{"preventScroll": True}],
                "active": "cancel",
                "transitionListeners": 0,
            },
        )
        self.assertFalse(data["fallbackResult"])
        self.assertEqual(
            data["afterEarlyCancel"],
            {
                "result": False,
                "cancelledTimers": [1, 3],
                "cancelFocusCalls": [],
                "active": "previous",
                "focusinListeners": 0,
                "transitionListeners": 0,
            },
        )
        self.assertEqual(data["previousFocusCalls"], 4)
        self.assertEqual(data["active"], "previous")
        self.assertEqual(data["focusinAdds"], 4)
        self.assertEqual(data["focusinListenersAfterFinish"], 0)

    def test_auto_permission_goal_create_is_gated_while_goal_status_stays_local(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/features/goal.js");
const classify = window.Code.features.goal.classifyGoalInput;
process.stdout.write(JSON.stringify({
  query: classify("/goal status"),
  localizedQuery: classify("/goal 状态"),
  create: classify("/goal implement the next step"),
  ordinary: classify("please continue"),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "query": {"kind": "query"},
                "localizedQuery": {"kind": "query"},
                "create": {"kind": "create", "objective": "implement the next step"},
                "ordinary": None,
            },
        )
        self.assertIn('if (!action || action.kind === "create") return false;', GOAL_SOURCE)

        submit_start = APP_SOURCE.index('els.chatForm.addEventListener("submit"')
        submit_end = APP_SOURCE.index('els.newChat.addEventListener("click"', submit_start)
        submit_source = APP_SOURCE[submit_start:submit_end]
        local_goal_index = submit_source.index("handleUiSlashCommand(text)")
        gate_index = submit_source.index("autoPermissionGate.requiresDispatchConfirmation()")
        send_index = submit_source.index("await sendMessage(text, {")
        self.assertLess(local_goal_index, gate_index)
        self.assertLess(gate_index, send_index)

        send_start = APP_SOURCE.index("async function sendMessage(")
        send_end = APP_SOURCE.index("function getSelectedModel()", send_start)
        send_source = APP_SOURCE[send_start:send_end]
        classify_index = send_source.index("goalFeature?.classifyGoalInput(userText)")
        prepare_index = send_source.index("await goalFeature.prepareExplicitGoal({")
        run_index = send_source.index("if (!claimActiveRunContext(ctx))")
        self.assertLess(classify_index, prepare_index)
        self.assertLess(prepare_index, run_index)

    def test_agent_permissions_transform_authorization_data_without_side_effects(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/permissions.js");

const permissions = window.Code.agent.permissions;
const request = {
  id: "authorization-1",
  sessionId: "alpha",
  sourceKey: "main",
  sourceLabel: "Main",
  status: "pending",
  selected: true,
  tool: {action: "write_file", path: "README.md", metadata: {attempt: 1}},
  resolve: () => {},
  abortSignal: {aborted: false},
  abortHandler: () => {},
  submitDecision: () => {},
  _finishing: true,
  error: "temporary",
};
const serialized = permissions.serializeAuthorizationRequest(request);
request.tool.path = "changed.md";
request.tool.metadata.attempt = 2;

const items = [
  {id: "sub-1", sessionId: "alpha", status: "pending", sourceKey: "sub", sourceLabel: "Sub"},
  {id: "main-1", sessionId: "alpha", status: "pending", sourceKey: "main", sourceLabel: "Main"},
  {id: "sub-2", sessionId: "alpha", status: "pending", sourceKey: "sub", sourceLabel: "Sub"},
  {id: "done", sessionId: "alpha", status: "approved", sourceKey: "main", sourceLabel: "Main"},
  {id: "other", sessionId: "beta", status: "pending", sourceKey: "main", sourceLabel: "Main"},
];
const pending = permissions.filterPendingAuthorizations(items, "alpha");
const groups = permissions.groupAuthorizations(pending);

process.stdout.write(JSON.stringify({
  instructions: Object.fromEntries(
    ["read", "plan", "accept", "bypass"].map((profile) => [
      profile,
      permissions.getPermissionInstruction(profile),
    ]),
  ),
  unknownInstruction: permissions.getPermissionInstruction("unknown") ?? null,
  nullSerialization: permissions.serializeAuthorizationRequest(null),
  serialized,
  requestPath: request.tool.path,
  pendingIds: pending.map((item) => item.id),
  pendingKeepsReferences: pending[0] === items[0] && pending[1] === items[1],
  groupKeys: groups.map((group) => group.key),
  groupLabels: groups.map((group) => group.label),
  groupedIds: groups.map((group) => group.items.map((item) => item.id)),
  groupsKeepReferences: groups[0].items[0] === items[0] && groups[0].items[1] === items[2],
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(
            data["instructions"],
            {
                "read": "权限策略：只读分析。只能列出、读取和搜索项目文件；遇到无法从上下文或文件中确认的关键决策时可以向用户提问。不能写入、删除、运行命令、访问网络或启动子 Agent。",
                "plan": "权限策略：计划模式。可读取、搜索、生成修改方案，但不能运行命令或直接写入文件。",
                "accept": "权限策略：接受编辑模式。可执行命令和写入文件，但操作前需用户确认。",
                "bypass": "权限策略：自动模式。当前允许的操作会自动执行，不再逐项请求授权；危险命令、越界路径、破坏性 Git、系统级操作及其他服务端安全限制仍然生效。",
            },
        )
        self.assertIsNone(data["unknownInstruction"])
        self.assertIsNone(data["nullSerialization"])
        self.assertEqual(
            data["serialized"],
            {
                "id": "authorization-1",
                "sessionId": "alpha",
                "sourceKey": "main",
                "sourceLabel": "Main",
                "status": "pending",
                "selected": True,
                "tool": {"action": "write_file", "path": "README.md", "metadata": {"attempt": 1}},
            },
        )
        self.assertEqual(data["requestPath"], "changed.md")
        self.assertEqual(data["pendingIds"], ["sub-1", "main-1", "sub-2"])
        self.assertTrue(data["pendingKeepsReferences"])
        self.assertEqual(data["groupKeys"], ["sub", "main"])
        self.assertEqual(data["groupLabels"], ["Sub", "Main"])
        self.assertEqual(data["groupedIds"], [["sub-1", "sub-2"], ["main-1"]])
        self.assertTrue(data["groupsKeepReferences"])
        for function_name in (
            "getPermissionInstruction",
            "serializeAuthorizationRequest",
            "filterPendingAuthorizations",
            "groupAuthorizations",
        ):
            self.assertIn(f"function {function_name}(", PERMISSIONS_SOURCE)
            self.assertNotIn(f"function {function_name}(", APP_SOURCE)
        self.assertNotIn("const permissionInstructions =", APP_SOURCE)

    def test_model_stream_protocol_parses_deltas_tools_and_failures(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/model-stream.js");

const protocol = window.Code.agent.modelStream;
const toolCalls = new Map();
protocol.mergeToolCallDelta(toolCalls, {
  index: 0,
  id: "call-1",
  type: "function",
  function: {name: "read_file", arguments: "{\"path\":"},
});
protocol.mergeToolCallDelta(toolCalls, {
  index: 0,
  function: {arguments: "\"README.md\"}"},
});

const requestError = protocol.createModelRequestError("broken", {
  status: 503,
  code: "upstream_error",
  transient: true,
});
const turn = protocol.createModelTurnAccumulator();
const firstTurnEvent = turn.consume({
  choices: [{
    delta: {
      reasoning_content: "plan",
      content: "answer",
      tool_calls: [{
        index: 0,
        id: "call-2",
        type: "function",
        function: {name: "read_file", arguments: "{\"path\":"},
      }],
    },
  }],
});
const secondTurnEvent = turn.consume({
  choices: [{
    delta: {
      tool_calls: [{
        index: 0,
        function: {arguments: "\"TODO.md\"}"},
      }],
    },
  }],
  usage: {completion_tokens: 3},
});
const doneTurnEvent = turn.consume("[DONE]");
const failedTurn = protocol.createModelTurnAccumulator();
const failedTurnEvent = failedTurn.consume(
  '[ERROR]{"message":"runtime failed","status":502,"code":"upstream","transient":false}',
);
const completeToolTurn = protocol.createModelTurnAccumulator();
const completeToolEvent = completeToolTurn.consume({
  choices: [{
    message: {
      tool_calls: [{
        id: "call-complete",
        type: "function",
        function: {name: "read_file", arguments: "{\"path\":\"VERSION\"}"},
      }],
    },
  }],
});
const result = {
  frozen: Object.isFrozen(protocol),
  ignored: protocol.parseSseLine("event: message"),
  invalid: protocol.parseSseLine("data: {broken"),
  done: protocol.parseSseLine("data: [DONE]"),
  errorFrame: protocol.parseSseLine(
    'data: [ERROR]{"message":"runtime failed","status":502}',
  ),
  parsed: protocol.parseSseLine('data: {"choices":[{"delta":{"content":"ok"}}]}'),
  openai: protocol.extractStreamDelta({
    choices: [{delta: {reasoning_content: "think", content: ["a", {text: "b"}]}}],
  }),
  anthropicThinking: protocol.extractStreamDelta({
    type: "content_block_delta",
    delta: {type: "thinking_delta", thinking: "reason"},
  }),
  anthropicText: protocol.extractStreamDelta({
    type: "content_block_delta",
    delta: {type: "text_delta", text: "answer"},
  }),
  responsesText: protocol.extractStreamDelta({
    type: "response.output_text.delta",
    delta: "response",
  }),
  responsesReasoning: protocol.extractStreamDelta({
    type: "response.reasoning_text.delta",
    delta: "response reason",
  }),
  toolCall: toolCalls.get(0),
  accessDenied: protocol.classifyModelRequestFailure(
    403, "", "Not authorized to access model",
  ),
  transient: protocol.classifyModelRequestFailure(503, "", "upstream failed"),
  permanent: protocol.classifyModelRequestFailure(400, "bad_request", "invalid"),
  requestError: {
    message: requestError.message,
    status: requestError.status,
    code: requestError.code,
    transient: requestError.transient,
    modelRequest: requestError.modelRequest,
  },
  retryWithoutTools: protocol.shouldRetryWithoutNativeTools(
    "function calling is not supported",
  ),
  keepTools: protocol.shouldRetryWithoutNativeTools("upstream timeout"),
  turn: {
    frozen: Object.isFrozen(turn),
    first: firstTurnEvent,
    second: secondTurnEvent,
    done: doneTurnEvent,
    toolCall: turn.getToolCallMap().get(0),
  },
  failedTurn: {
    event: {
      kind: failedTurnEvent.kind,
      rawThought: failedTurnEvent.rawThought,
      rawContent: failedTurnEvent.rawContent,
      completed: failedTurnEvent.completed,
    },
    error: {
      message: failedTurnEvent.error.message,
      status: failedTurnEvent.error.status,
      code: failedTurnEvent.error.code,
      transient: failedTurnEvent.error.transient,
      modelRequest: failedTurnEvent.error.modelRequest,
    },
  },
  completeToolTurn: {
    event: completeToolEvent,
    toolCall: completeToolTurn.getToolCallMap().get(0),
  },
};
process.stdout.write(JSON.stringify(result));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["frozen"])
        self.assertIsNone(data["ignored"])
        self.assertIsNone(data["invalid"])
        self.assertEqual(data["done"], "[DONE]")
        self.assertEqual(
            data["errorFrame"],
            '[ERROR]{"message":"runtime failed","status":502}',
        )
        self.assertEqual(
            data["parsed"]["choices"][0]["delta"]["content"],
            "ok",
        )
        self.assertEqual(data["openai"]["reasoning"], "think")
        self.assertEqual(data["openai"]["text"], "ab")
        self.assertEqual(data["anthropicThinking"]["reasoning"], "reason")
        self.assertEqual(data["anthropicText"]["text"], "answer")
        self.assertEqual(data["responsesText"]["text"], "response")
        self.assertEqual(data["responsesReasoning"]["reasoning"], "response reason")
        self.assertEqual(
            data["toolCall"],
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": '{"path":"README.md"}',
                },
            },
        )
        self.assertEqual(
            data["accessDenied"],
            {"code": "model_access_denied", "transient": False},
        )
        self.assertEqual(data["transient"], {"code": "", "transient": True})
        self.assertEqual(
            data["permanent"],
            {"code": "bad_request", "transient": False},
        )
        self.assertEqual(
            data["requestError"],
            {
                "message": "broken",
                "status": 503,
                "code": "upstream_error",
                "transient": True,
                "modelRequest": True,
            },
        )
        self.assertTrue(data["retryWithoutTools"])
        self.assertFalse(data["keepTools"])
        self.assertTrue(data["turn"]["frozen"])
        self.assertEqual(data["turn"]["first"]["kind"], "delta")
        self.assertEqual(data["turn"]["first"]["reasoning"], "plan")
        self.assertEqual(data["turn"]["first"]["text"], "answer")
        self.assertTrue(data["turn"]["first"]["receivedToolCallDelta"])
        self.assertEqual(data["turn"]["first"]["combinedText"], "<think>plan</think>\nanswer")
        self.assertEqual(data["turn"]["second"]["usage"], {"completion_tokens": 3})
        self.assertEqual(data["turn"]["done"]["kind"], "done")
        self.assertTrue(data["turn"]["done"]["completed"])
        self.assertEqual(
            data["turn"]["toolCall"],
            {
                "id": "call-2",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": '{"path":"TODO.md"}',
                },
            },
        )
        self.assertEqual(
            data["failedTurn"]["event"],
            {
                "kind": "error",
                "rawThought": "",
                "rawContent": "",
                "completed": False,
            },
        )
        self.assertEqual(
            data["failedTurn"]["error"],
            {
                "message": "runtime failed",
                "status": 502,
                "code": "upstream",
                "transient": False,
                "modelRequest": True,
            },
        )
        self.assertTrue(data["completeToolTurn"]["event"]["receivedToolCallDelta"])
        self.assertEqual(
            data["completeToolTurn"]["toolCall"],
            {
                "id": "call-complete",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": '{"path":"VERSION"}',
                },
            },
        )

    def test_model_sse_data_reader_handles_arbitrary_bytes_and_tail_frames(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/agent/model-stream.js");

const protocol = window.Code.agent.modelStream;
const encoder = new TextEncoder();

function byteStream(text) {
  const bytes = encoder.encode(text);
  return new ReadableStream({
    start(controller) {
      for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
      controller.close();
    },
  });
}

function batchStream(text) {
  const bytes = encoder.encode(text);
  return new ReadableStream({
    start(controller) {
      controller.enqueue(bytes);
      controller.close();
    },
  });
}

async function collect(body) {
  const reader = protocol.createSseDataReader(body);
  const frames = [];
  while (true) {
    const packet = await reader.read();
    if (packet.done) return frames;
    frames.push(packet.value);
  }
}

(async () => {
  const frozenReader = protocol.createSseDataReader(batchStream("data: [DONE]\n\n"));
  const arbitraryBytes = await collect(byteStream([
    ": keepalive\r\n\r\n",
    'data: {"choices":[{"delta":{"content":"你"}}]}\r\n\r\n',
    'data: {"usage":{"completion_tokens":1}}\n\n',
    "data: [DONE]",
  ].join("")));
  const batched = await collect(batchStream([
    'data: {"choices":[{"delta":{"content":"a"}}]}\n\n',
    'data: {"choices":[{"delta":{"content":"b"}}]}\n\n',
    "data: [DONE]\n\n",
  ].join("")));
  const errorTail = await collect(batchStream(
    'data: [ERROR]{"message":"tail failed","status":502}',
  ));
  const toolTail = await collect(batchStream(
    'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"read_file","arguments":"{}"}}]}}]}',
  ));
  const incomplete = await collect(batchStream(
    'data: {"choices":[{"delta":{"content":"partial"}}]}',
  ));

  let readerError = null;
  const brokenReader = protocol.createSseDataReader(new ReadableStream({
    start(controller) {
      controller.error(new Error("reader broken"));
    },
  }));
  try {
    await brokenReader.read();
  } catch (error) {
    readerError = error.message;
  }

  process.stdout.write(JSON.stringify({
    readerFrozen: Object.isFrozen(frozenReader),
    arbitraryBytes,
    batched,
    errorTail,
    toolTail,
    incomplete,
    readerError,
  }));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["readerFrozen"])
        self.assertEqual(
            data["arbitraryBytes"],
            [
                {"choices": [{"delta": {"content": "你"}}]},
                {"usage": {"completion_tokens": 1}},
                "[DONE]",
            ],
        )
        self.assertEqual(
            [
                frame.get("choices", [{}])[0].get("delta", {}).get("content")
                for frame in data["batched"][:-1]
            ],
            ["a", "b"],
        )
        self.assertEqual(data["batched"][-1], "[DONE]")
        self.assertEqual(
            data["errorTail"],
            ['[ERROR]{"message":"tail failed","status":502}'],
        )
        self.assertEqual(
            data["toolTail"][0]["choices"][0]["delta"]["tool_calls"][0]["function"],
            {"name": "read_file", "arguments": "{}"},
        )
        self.assertEqual(
            data["incomplete"],
            [{"choices": [{"delta": {"content": "partial"}}]}],
        )
        self.assertEqual(data["readerError"], "reader broken")

    def test_state_module_isolates_session_domains_and_checkpoints(self):
        state_path = ROOT / "src" / "core" / "state.js"
        self.assertTrue(state_path.is_file())
        self.assertIn("const state = createAppState(localStorage);", APP_SOURCE)
        self.assertIn("} = createSessionStateAccessors(state);", APP_SOURCE)
        self.assertNotIn("function ensureSessionRun(", APP_SOURCE)
        self.assertNotIn("function getSessionMessages(", APP_SOURCE)
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/core/state.js");

const values = new Map([
  ["code-permission-profile", "plan"],
  ["code-preview-width", "512"],
  ["code-session-height", "240"],
  ["code-sidebar-width", "300"],
  ["code-disabled-skills", JSON.stringify(["alpha", "beta"])],
  ["code-lang", "en"],
]);
const storage = {
  getItem(key) {
    return values.has(key) ? values.get(key) : null;
  },
};
const {createAppState, createSessionStateAccessors} = window.Code.core.state;
const state = createAppState(storage);
const sessions = createSessionStateAccessors(state);

state.sessions = [{id: "alpha"}, {id: "beta"}];
state.sessionId = "alpha";
const alphaMessages = [{role: "user", content: "alpha"}];
const betaMessages = [{role: "user", content: "beta"}];
sessions.setSessionMessages("alpha", alphaMessages);
sessions.setSessionMessages("beta", betaMessages);
sessions.setSessionStats("alpha", {input: 1, output: 2, cache: 3, cost: 4});
sessions.setSessionStats("beta", {input: 5, output: 6, cache: 7, cost: 8});
sessions.setSessionLastUsage("alpha", {total_tokens: 11});
sessions.setSessionLastUsage("beta", {total_tokens: 22});

const alphaRun = sessions.ensureSessionRun("alpha");
const betaRun = sessions.ensureSessionRun("beta");
sessions.setSessionRunState("alpha", {status: "running"});
sessions.setBackgroundRunCheckpoint("alpha", {id: "bg-1", status: "running"});
sessions.setQueuedMessageCheckpoints("alpha", [{id: "queue-1", status: "queued"}]);
sessions.removeBackgroundRunCheckpoint("alpha", "bg-1");

process.stdout.write(JSON.stringify({
  defaults: {
    permissionProfile: state.permissionProfile,
    previewWidth: state.previewWidth,
    sidebarSessionHeight: state.sidebarSessionHeight,
    sidebarWidth: state.sidebarWidth,
    disabledSkills: [...state.disabledSkills],
    lang: state.lang,
  },
  activeMessageIdentity: state.messages === alphaMessages,
  backgroundMessages: sessions.getSessionMessages("beta"),
  activeStats: state.stats,
  backgroundStats: sessions.getSessionStats("beta"),
  activeUsage: state.lastUsage,
  backgroundUsage: sessions.getSessionLastUsage("beta"),
  independentRuns: alphaRun !== betaRun && alphaRun.sessionId === "alpha" && betaRun.sessionId === "beta",
  mirroredRunState: state.sessions[0].runState === sessions.getSessionRunState("alpha"),
  backgroundRuns: sessions.getBackgroundRunCheckpoints("alpha"),
  queuedMessages: sessions.getQueuedMessageCheckpoints("alpha"),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "defaults": {
                    "permissionProfile": "plan",
                    "previewWidth": 512,
                    "sidebarSessionHeight": 240,
                    "sidebarWidth": 300,
                    "disabledSkills": ["alpha", "beta"],
                    "lang": "en",
                },
                "activeMessageIdentity": True,
                "backgroundMessages": [{"role": "user", "content": "beta"}],
                "activeStats": {"input": 1, "output": 2, "cache": 3, "cost": 4},
                "backgroundStats": {"input": 5, "output": 6, "cache": 7, "cost": 8},
                "activeUsage": {"total_tokens": 11},
                "backgroundUsage": {"total_tokens": 22},
                "independentRuns": True,
                "mirroredRunState": True,
                "backgroundRuns": [],
                "queuedMessages": [{"id": "queue-1", "status": "queued"}],
            },
        )

    def test_run_timing_helpers_exclude_offline_time_and_support_old_checkpoints(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/core/state.js");

const {
  activeRunElapsedMs,
  createAppState,
  createSessionStateAccessors,
  persistedRunElapsedMs,
} = window.Code.core.state;
const state = createAppState({getItem: () => null});
const run = createSessionStateAccessors(state).ensureSessionRun("timer");

process.stdout.write(JSON.stringify({
  defaultTimerFields: [run.taskElapsedBaseMs, run.taskElapsedResumedAt],
  explicitCheckpoint: persistedRunElapsedMs({
    elapsedMs: 15000,
    startedAt: "2026-08-02T00:27:00.000Z",
    updatedAt: "2026-08-02T00:27:15.000Z",
  }, Date.parse("2026-08-02T16:15:00.000Z")),
  legacyCheckpoint: persistedRunElapsedMs({
    startedAt: "2026-08-02T00:27:00.000Z",
    updatedAt: "2026-08-02T00:27:15.000Z",
  }, Date.parse("2026-08-02T16:15:00.000Z")),
  futureCheckpoint: persistedRunElapsedMs({
    startedAt: "2026-08-02T16:15:00.000Z",
    updatedAt: "2026-08-02T16:16:00.000Z",
  }, Date.parse("2026-08-02T16:15:30.000Z")),
  malformedCheckpoint: persistedRunElapsedMs({startedAt: "bad", updatedAt: "worse"}, 100000),
  normalActiveRun: activeRunElapsedMs({
    taskStartTime: 10000,
    taskElapsedBaseMs: null,
    taskElapsedResumedAt: null,
  }, 16000),
  resumedActiveRun: activeRunElapsedMs({
    taskStartTime: 1000,
    taskElapsedBaseMs: 15000,
    taskElapsedResumedAt: 100000,
  }, 103000),
  futureResumeAnchor: activeRunElapsedMs({
    taskStartTime: 1000,
    taskElapsedBaseMs: 15000,
    taskElapsedResumedAt: 104000,
  }, 103000),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "defaultTimerFields": [None, None],
                "explicitCheckpoint": 15000,
                "legacyCheckpoint": 15000,
                "futureCheckpoint": 0,
                "malformedCheckpoint": 0,
                "normalActiveRun": 6000,
                "resumedActiveRun": 18000,
                "futureResumeAnchor": 15000,
            },
        )

    def test_persistence_module_preserves_payload_profiles_and_serializes_saves(self):
        persistence_path = ROOT / "src" / "services" / "persistence.js"
        self.assertTrue(persistence_path.is_file())
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/services/persistence.js");

const {
  serializeSessionMessages,
  buildSessionSavePayload,
  createSessionPersistence,
} = window.Code.services.persistence;

const sourceMessage = {
  role: "assistant",
  content: "done",
  thought: "checked",
  meta: {kind: "answer"},
  _images: ["image.png"],
  _model: "gpt-test",
  _time: "2026-07-31T06:30:00Z",
};
const baseMessages = serializeSessionMessages([sourceMessage]);
const modelMessages = serializeSessionMessages(
  [sourceMessage],
  {includeModel: true},
);
const durableMessages = serializeSessionMessages(
  [sourceMessage],
  {includeModel: true, includeTime: true},
);
const metadataPayload = buildSessionSavePayload({
  title: "Metadata",
  stats: {input: 1},
  lastUsage: {total_tokens: 2},
  runState: {status: "running"},
});
const durablePayload = buildSessionSavePayload({
  title: "Durable",
  stats: {input: 3},
  lastUsage: {total_tokens: 4},
  runState: {status: "completed"},
  messages: [sourceMessage],
  persistMessages: true,
});

const starts = [];
const releases = [];
const saveChains = {};
const requestJson = (url, options) => {
  const payload = JSON.parse(options.body);
  starts.push({url, title: payload.title});
  return new Promise((resolve) => {
    releases.push(() => resolve({id: url.split("/").pop(), title: payload.title}));
  });
};
const persistence = createSessionPersistence({requestJson, saveChains});
const first = persistence.saveSession("alpha", {title: "first"});
const second = persistence.saveSession("alpha", {title: "second"});
const parallel = persistence.saveSession("beta", {title: "parallel"});

setImmediate(async () => {
  const startsBeforeRelease = starts.slice();
  releases.splice(0).forEach((release) => release());
  await new Promise((resolve) => setImmediate(resolve));
  releases.splice(0).forEach((release) => release());
  const results = await Promise.all([first, second, parallel]);
  process.stdout.write(JSON.stringify({
    baseMessages,
    modelMessages,
    durableMessages,
    metadataPayload,
    durablePayload,
    sourceUnchanged: sourceMessage._model === "gpt-test"
      && sourceMessage._time === "2026-07-31T06:30:00Z",
    startsBeforeRelease,
    starts,
    results,
    saveChains,
  }));
});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(
            result["baseMessages"],
            [{
                "role": "assistant",
                "content": "done",
                "thought": "checked",
                "meta": {"kind": "answer"},
                "_images": ["image.png"],
            }],
        )
        self.assertEqual(result["modelMessages"][0]["_model"], "gpt-test")
        self.assertNotIn("_time", result["modelMessages"][0])
        self.assertEqual(result["durableMessages"][0]["_model"], "gpt-test")
        self.assertEqual(
            result["durableMessages"][0]["_time"],
            "2026-07-31T06:30:00Z",
        )
        self.assertNotIn("messages", result["metadataPayload"])
        self.assertEqual(
            result["durablePayload"]["messages"],
            result["durableMessages"],
        )
        self.assertTrue(result["sourceUnchanged"])
        self.assertEqual(
            [item["title"] for item in result["startsBeforeRelease"]],
            ["first", "parallel"],
        )
        self.assertEqual(
            [item["title"] for item in result["starts"]],
            ["first", "parallel", "second"],
        )
        self.assertEqual(
            [item["title"] for item in result["results"]],
            ["first", "second", "parallel"],
        )
        self.assertEqual(result["saveChains"], {})

    def test_sessions_module_owns_crud_requests_and_loaded_data_normalization(self):
        self.assertTrue((ROOT / "src" / "features" / "sessions.js").is_file())
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/features/sessions.js");

const {
  normalizeSessionMessages,
  collectPendingEdits,
  createSessionsFeature,
} = window.Code.features.sessions;
const requests = [];
const requestJson = async (url, options = {}) => {
  const request = {
    url,
    method: options.method || "GET",
    body: options.body ? JSON.parse(options.body) : null,
  };
  requests.push(request);
  if (url === "/api/sessions" && request.method === "GET") {
    return {data: [{id: "alpha"}, {id: "beta"}]};
  }
  return {id: url.split("/").pop(), ...request};
};
const sessions = createSessionsFeature({requestJson});

(async () => {
  const listed = await sessions.listSessions();
  await sessions.getSession("alpha / beta");
  await sessions.createSession({title: "Created", projectId: "project-1"});
  await sessions.updateSession("alpha", {title: "Renamed", stats: {input: 2}});
  await sessions.deleteSession("beta");

  const sourceMessages = [
    {role: "assistant", content: "answer", _images: ["image.png"]},
    {
      role: "tool-result",
      content: "edit",
      meta: {
        pendingEditId: "edit-1",
        path: "app.js",
        newContent: "updated",
        applied: true,
        serverManaged: true,
        mtime: 42,
      },
    },
    {role: "tool-result", content: "ignored", meta: {}},
  ];
  const normalized = normalizeSessionMessages(sourceMessages);
  const pendingEdits = collectPendingEdits(normalized);
  let missingIdError = "";
  try {
    await sessions.getSession(" ");
  } catch (error) {
    missingIdError = error.message;
  }

  process.stdout.write(JSON.stringify({
    listed,
    requests,
    normalized,
    pendingEdits,
    sourceIdentityPreserved: normalized[0] !== sourceMessages[0]
      && sourceMessages[0]._images[0] === "image.png",
    missingIdError,
  }));
})();
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["listed"], [{"id": "alpha"}, {"id": "beta"}])
        self.assertEqual(
            result["requests"],
            [
                {"url": "/api/sessions", "method": "GET", "body": None},
                {
                    "url": "/api/sessions/alpha%20%2F%20beta",
                    "method": "GET",
                    "body": None,
                },
                {
                    "url": "/api/sessions",
                    "method": "POST",
                    "body": {"title": "Created", "projectId": "project-1"},
                },
                {
                    "url": "/api/sessions/alpha",
                    "method": "PUT",
                    "body": {"title": "Renamed", "stats": {"input": 2}},
                },
                {
                    "url": "/api/sessions/beta",
                    "method": "DELETE",
                    "body": None,
                },
            ],
        )
        self.assertTrue(result["sourceIdentityPreserved"])
        self.assertEqual(
            result["pendingEdits"],
            {
                "edit-1": {
                    "path": "app.js",
                    "newContent": "updated",
                    "applied": True,
                    "rejected": False,
                    "resolved": True,
                    "serverManaged": True,
                    "mtime": 42,
                },
            },
        )
        self.assertEqual(result["missingIdError"], "Session id is required")

        self.assertIn("createSessionsFeature({ requestJson: apiJson })", APP_SOURCE)
        refresh_start = APP_SOURCE.index("async function refreshSessions()")
        refresh_end = APP_SOURCE.index("function scheduleDeferredSessionRefresh(", refresh_start)
        rename_start = APP_SOURCE.index("async function renameSession(")
        delete_start = APP_SOURCE.index("async function deleteSession(", rename_start)
        pinned_start = APP_SOURCE.index("function getPinnedSessions()", delete_start)
        self.assertIn(
            "state.sessions = await listSessionRecords();",
            APP_SOURCE[refresh_start:refresh_end],
        )
        self.assertIn(
            "await updateSessionRecord(sessionId",
            APP_SOURCE[rename_start:delete_start],
        )
        self.assertIn(
            "await deleteSessionRecord(sessionId);",
            APP_SOURCE[delete_start:pinned_start],
        )
        navigation_start = SESSIONS_SOURCE.index("function createSessionNavigation(")
        self.assertIn(
            "const session = await data.createSession(body);",
            SESSIONS_SOURCE[navigation_start:],
        )
        self.assertIn(
            "session = await data.getSession(sessionId);",
            SESSIONS_SOURCE[navigation_start:],
        )
        self.assertIn(
            "state.messages = cached || normalizeSessionMessages(session.messages || []);",
            SESSIONS_SOURCE[navigation_start:],
        )
        self.assertIn(
            "state.pendingEdits = collectPendingEdits(state.messages);",
            SESSIONS_SOURCE[navigation_start:],
        )
        self.assertNotIn("async function createSession(", APP_SOURCE)
        self.assertNotIn("async function loadSession(", APP_SOURCE)

    def test_session_navigation_preserves_new_create_and_switch_state(self):
        self.assertLess(
            APP_SOURCE.index("const panelsFeature = createPanelsFeature({"),
            APP_SOURCE.index("const sessionNavigation = createSessionNavigation({"),
        )
        self.assertLess(
            APP_SOURCE.index("updateStatsPanel,", APP_SOURCE.index("const {", APP_SOURCE.index("const panelsFeature"))),
            APP_SOURCE.index("const sessionNavigation = createSessionNavigation({"),
        )
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/features/sessions.js");

const values = new Map([
  ["code-foreground-view", "session"],
  ["code-last-session", "alpha"],
]);
const storage = {
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: (key) => values.delete(key),
};
const alphaMessages = [{role: "user", content: "alpha"}];
const state = {
  sessionId: "alpha",
  sessions: [
    {id: "alpha", projectId: "p1", cwd: "C:/One", title: "Alpha"},
    {id: "beta", projectId: "p2", cwd: "C:/Beta", title: "Beta"},
  ],
  projectsMap: {
    p1: {id: "p1", path: "C:/One"},
    p2: {id: "p2", path: "C:/Two"},
  },
  pendingProjectId: null,
  messages: alphaMessages,
  stats: {input: 1, output: 2, cache: 3},
  pendingEdits: {},
  _sessionMsgs: {alpha: alphaMessages},
  _sessionStats: {alpha: {input: 1, output: 2, cache: 3}},
  _sessionLastUsage: {},
  _sessionRunStates: {},
  _foregroundNavigationSeq: 0,
  _sessionLoadSeq: 0,
  branchPanelOpen: true,
  _keepBranchOpen: false,
};
const events = [];
const elements = {
  sessionTitle: {value: "Alpha"},
  branchPanel: {classList: {remove: (name) => events.push(["branch-remove", name])}},
  toggleBranches: {classList: {remove: (name) => events.push(["toggle-remove", name])}},
};
const stateAccessors = {
  getSessionRunState: (sessionId) => state._sessionRunStates[sessionId] || {},
  setSessionRunState: (sessionId, runState) => {
    state._sessionRunStates[sessionId] = {...(runState || {})};
  },
  setSessionMessages: (sessionId, messages) => {
    state._sessionMsgs[sessionId] = messages;
    if (sessionId === state.sessionId) state.messages = messages;
  },
  setSessionStats: (sessionId, stats) => {
    state._sessionStats[sessionId] = stats;
    if (sessionId === state.sessionId) state.stats = stats;
  },
  setSessionLastUsage: (sessionId, usage) => {
    if (usage) state._sessionLastUsage[sessionId] = usage;
    else delete state._sessionLastUsage[sessionId];
    if (sessionId === state.sessionId) state.lastUsage = usage || null;
  },
};
const data = {
  createSession: async (body) => {
    events.push(["create", body]);
    return {
      id: "created",
      title: body.title,
      projectId: body.projectId,
      cwd: body.cwd,
      createdAt: "2026-07-31T07:00:00Z",
      updatedAt: "2026-07-31T07:00:01Z",
      messages: [],
      stats: {input: 0, output: 0, cache: 0},
      runState: {},
      lastUsage: null,
    };
  },
  getSession: async (sessionId) => {
    events.push(["get", sessionId]);
    return {
      id: "beta",
      title: "Beta loaded",
      projectId: "p2",
      cwd: "C:/Beta",
      createdAt: "2026-07-30T01:00:00Z",
      updatedAt: "2026-07-31T07:00:02Z",
      messages: [{
        role: "tool-result",
        content: "edit",
        meta: {
          pendingEditId: "edit-beta",
          path: "beta.js",
          newContent: "next",
          rejected: true,
        },
      }],
      stats: {input: 7, output: 8, cache: 9, cost: 1},
      lastUsage: {total_tokens: 24},
      runState: {
        status: "waiting-user-input",
        userInputRequest: {id: "question-beta", status: "pending"},
        authorizationRequest: {id: "authorization-beta", status: "pending"},
      },
    };
  },
};
let currentRoot = "C:/One";
const project = {
  getCurrentProject: () => state.projectsMap.p1,
  getById: (projectId) => state.projectsMap[projectId],
  getPrimaryPath: (projectRecord) => projectRecord?.path || "",
  getCurrentRoot: () => currentRoot,
  pathsEqual: (left, right) => String(left).toLowerCase() === String(right).toLowerCase(),
  saveRoot: async (path) => {
    currentRoot = path;
    events.push(["save-root", path]);
  },
};
const view = {
  cacheActiveSessionState: () => {
    events.push(["cache", state.sessionId]);
    if (!state.sessionId) return;
    state._sessionMsgs[state.sessionId] = state.messages;
    state._sessionStats[state.sessionId] = state.stats;
  },
  resetRenderCache: () => events.push(["reset-render"]),
  renderMessages: () => events.push(["render-messages", state.sessionId]),
  renderSessions: () => events.push(["render-sessions", state.sessionId]),
  updateGroupBadge: (session) => events.push(["group", session.id || ""]),
  updateStatsPanel: () => events.push(["stats"]),
  updateSendButtonState: () => events.push(["send"]),
  syncActiveStreamingState: () => events.push(["stream", state.sessionId]),
  scheduleMessagesScrollToBottom: (sessionId) => events.push(["scroll", sessionId]),
  refreshSessions: async () => events.push(["refresh"]),
  showToast: (message, kind) => events.push(["toast", message, kind]),
};
const recovery = {
  reconcilePersistedUserInputRequest: async (sessionId, request) => {
    events.push(["user-input-start", sessionId, request?.id || ""]);
    await Promise.resolve();
    stateAccessors.setSessionRunState(sessionId, {
      ...stateAccessors.getSessionRunState(sessionId),
      status: "paused",
      userInputRequest: null,
    });
    events.push(["user-input-finish", sessionId, stateAccessors.getSessionRunState(sessionId).status]);
  },
  restoreAuthorizationRequest: (sessionId, request) => events.push(["authorization", sessionId, request?.id || ""]),
};
const branch = {
  syncMetadata: (summaries, session) => {
    const summary = summaries.find((item) => item.id === session.id);
    if (summary) Object.assign(summary, session);
    return summary || null;
  },
};
const navigation = window.Code.features.sessions.createSessionNavigation({
  state,
  elements,
  storage,
  data,
  stateAccessors,
  project,
  branch,
  recovery,
  view,
  t: (key) => key === "untitledSession" ? "Untitled" : "New session",
});

(async () => {
  navigation.beginNewConversation("p2");
  const afterBegin = {
    sessionId: state.sessionId,
    pendingProjectId: state.pendingProjectId,
    title: elements.sessionTitle.value,
    foregroundView: values.get("code-foreground-view"),
    lastSession: values.get("code-last-session") || null,
  };

  const optimisticMessages = [{role: "user", content: "optimistic"}];
  await navigation.createSession("Created", {
    initialMessages: optimisticMessages,
    deferSidebarRefresh: true,
  });
  const afterCreate = {
    sessionId: state.sessionId,
    pendingProjectId: state.pendingProjectId,
    title: elements.sessionTitle.value,
    messages: state.messages,
    deferredRefreshId: state._deferredSessionRefreshId,
    foregroundView: values.get("code-foreground-view"),
    lastSession: values.get("code-last-session"),
  };

  state._lastSwitchTime = 0;
  await navigation.loadSession("beta");
  const afterLoad = {
    sessionId: state.sessionId,
    pendingProjectId: state.pendingProjectId,
    title: elements.sessionTitle.value,
    messages: state.messages,
    pendingEdits: state.pendingEdits,
    stats: state.stats,
    lastUsage: state.lastUsage,
    branchPanelOpen: state.branchPanelOpen,
    runState: state._sessionRunStates.beta,
    foregroundView: values.get("code-foreground-view"),
    lastSession: values.get("code-last-session"),
  };

  process.stdout.write(JSON.stringify({afterBegin, afterCreate, afterLoad, events}));
})();
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(
            result["afterBegin"],
            {
                "sessionId": None,
                "pendingProjectId": "p2",
                "title": "",
                "foregroundView": "welcome",
                "lastSession": None,
            },
        )
        self.assertEqual(result["afterCreate"]["sessionId"], "created")
        self.assertEqual(result["afterCreate"]["pendingProjectId"], "p2")
        self.assertEqual(result["afterCreate"]["title"], "Created")
        self.assertEqual(
            result["afterCreate"]["messages"],
            [{"role": "user", "content": "optimistic"}],
        )
        self.assertEqual(result["afterCreate"]["deferredRefreshId"], "created")
        self.assertEqual(result["afterCreate"]["foregroundView"], "session")
        self.assertEqual(result["afterCreate"]["lastSession"], "created")

        self.assertEqual(result["afterLoad"]["sessionId"], "beta")
        self.assertEqual(result["afterLoad"]["pendingProjectId"], "p2")
        self.assertEqual(result["afterLoad"]["title"], "Beta loaded")
        self.assertEqual(result["afterLoad"]["stats"], {"input": 7, "output": 8, "cache": 9, "cost": 1})
        self.assertEqual(result["afterLoad"]["lastUsage"], {"total_tokens": 24})
        self.assertFalse(result["afterLoad"]["branchPanelOpen"])
        self.assertEqual(
            result["afterLoad"]["runState"],
            {
                "status": "paused",
                "userInputRequest": None,
                "authorizationRequest": {"id": "authorization-beta", "status": "pending"},
            },
        )
        self.assertEqual(result["afterLoad"]["foregroundView"], "session")
        self.assertEqual(result["afterLoad"]["lastSession"], "beta")
        self.assertEqual(
            result["afterLoad"]["pendingEdits"],
            {
                "edit-beta": {
                    "path": "beta.js",
                    "newContent": "next",
                    "applied": False,
                    "rejected": True,
                    "resolved": True,
                    "serverManaged": False,
                    "mtime": 0,
                },
            },
        )
        self.assertIn(["create", {"title": "Created", "projectId": "p2", "cwd": "C:/Two"}], result["events"])
        self.assertIn(["get", "beta"], result["events"])
        self.assertIn(["user-input-start", "beta", "question-beta"], result["events"])
        self.assertIn(["user-input-finish", "beta", "paused"], result["events"])
        self.assertIn(["authorization", "beta", "authorization-beta"], result["events"])
        self.assertIn(["scroll", "beta"], result["events"])
        self.assertLess(
            result["events"].index(["user-input-start", "beta", "question-beta"]),
            result["events"].index(["user-input-finish", "beta", "paused"]),
        )
        self.assertLess(
            result["events"].index(["user-input-finish", "beta", "paused"]),
            result["events"].index(["authorization", "beta", "authorization-beta"]),
        )
        self.assertLess(
            result["events"].index(["authorization", "beta", "authorization-beta"]),
            result["events"].index(["render-messages", "beta"]),
        )

    def test_session_navigation_only_isolates_goal_for_an_accepted_switch_and_restores_on_failure(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/features/sessions.js");

const state = {
  sessionId: "source",
  sessions: [{id: "source", title: "Source"}, {id: "target", title: "Target"}],
  messages: [], stats: {}, pendingEdits: {}, pendingProjectId: null,
  _sessionMsgs: {source: []}, _sessionStats: {}, _sessionLastUsage: {},
  _sessionRunStates: {}, _foregroundNavigationSeq: 0, _sessionLoadSeq: 0,
  branchPanelOpen: false, _keepBranchOpen: false,
};
const elements = {
  sessionTitle: {value: "Source"},
  branchPanel: {classList: {remove() {}}},
  toggleBranches: {classList: {remove() {}}},
};
const storage = {setItem() {}, removeItem() {}};
const stateAccessors = {
  getSessionRunState: (id) => state._sessionRunStates[id] || {},
  setSessionRunState: (id, value) => { state._sessionRunStates[id] = {...(value || {})}; },
  setSessionMessages: (id, value) => { state._sessionMsgs[id] = value; },
  setSessionStats: (id, value) => { state._sessionStats[id] = value; },
  setSessionLastUsage() {},
};
const requests = [];
const data = {
  createSession: async () => ({}),
  getSession: (id) => new Promise((resolve, reject) => requests.push({id, resolve, reject})),
};
const project = {
  getCurrentProject: () => null, getById: () => null, getPrimaryPath: () => "",
  getCurrentRoot: () => "", pathsEqual: () => true, saveRoot: async () => {},
};
const branch = {
  syncMetadata: (summaries, session) => {
    const found = summaries.find((item) => item.id === session.id);
    if (found) Object.assign(found, session);
    return found || null;
  },
};
const events = [];
let transitionCount = 0;
const view = {
  beginSessionTransition(id) {
    const token = `transition-${++transitionCount}`;
    events.push(["begin", id, token]);
    return token;
  },
  cancelSessionTransition(id, token) { events.push(["cancel", id, token]); return true; },
  cacheActiveSessionState() { events.push(["cache", state.sessionId]); },
  resetRenderCache() {}, renderMessages() { events.push(["render", state.sessionId]); },
  renderSessions() {}, updateGroupBadge() {}, updateStatsPanel() {}, updateSendButtonState() {},
  syncActiveStreamingState() {}, scheduleMessagesScrollToBottom() {}, refreshSessions: async () => {},
  showToast() {},
};
const navigation = window.Code.features.sessions.createSessionNavigation({
  state, elements, storage, data, stateAccessors, project, branch,
  recovery: {reconcilePersistedUserInputRequest: async () => {}, restoreAuthorizationRequest() {}},
  view, t: () => "Untitled",
});

(async () => {
  state._lastSwitchTime = Date.now();
  await navigation.loadSession("target");
  const debounced = {events: events.slice(), requests: requests.length};

  state._lastSwitchTime = 0;
  await navigation.loadSession("source");
  const sameSession = {events: events.slice(), requests: requests.length};

  state._lastSwitchTime = 0;
  const failedLoad = navigation.loadSession("target").catch((error) => error.message);
  const acceptedBeforeRead = events.slice();
  requests.shift().reject(new Error("target unavailable"));
  const failure = await failedLoad;

  const successfulLoad = navigation.loadSession("target", {userInitiated: false});
  requests.shift().resolve({
    id: "target", title: "Target", messages: [], stats: {}, runState: {},
    createdAt: "2026-08-24T00:00:00Z", updatedAt: "2026-08-24T00:00:01Z",
  });
  await successfulLoad;

  process.stdout.write(JSON.stringify({
    debounced,
    sameSession,
    acceptedBeforeRead,
    failure,
    finalSessionId: state.sessionId,
    events,
  }));
})().catch((error) => { console.error(error); process.exitCode = 1; });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["debounced"], {"events": [], "requests": 0})
        self.assertEqual(result["sameSession"]["requests"], 0)
        self.assertFalse(any(event[0] == "begin" for event in result["sameSession"]["events"]))
        self.assertEqual(
            result["acceptedBeforeRead"][-2:],
            [["begin", "target", "transition-1"], ["cache", "source"]],
        )
        self.assertEqual(result["failure"], "target unavailable")
        self.assertIn(["cancel", "source", "transition-1"], result["events"])
        self.assertEqual(result["finalSessionId"], "target")
        self.assertIn(["begin", "target", "transition-2"], result["events"])
        self.assertIn(["render", "target"], result["events"])

    def test_session_startup_restores_foreground_and_orders_recovery(self):
        self.assertIn("createSessionStartup,", APP_SOURCE)
        self.assertIn("const sessionStartup = createSessionStartup({", APP_SOURCE)
        init_start = APP_SOURCE.index("async function init()")
        platform_sync = APP_SOURCE.index(
            "const platformSync = await platformSyncPromise;",
            init_start,
        )
        auth_check = APP_SOURCE.index("if (platformSync?.authExpired)", platform_sync)
        recovery_call = APP_SOURCE.index("sessionStartup.startRecovery();", auth_check)
        model_refresh = APP_SOURCE.index("await refreshModels();", recovery_call)
        self.assertLess(platform_sync, auth_check)
        self.assertLess(auth_check, recovery_call)
        self.assertLess(recovery_call, model_refresh)
        self.assertEqual(APP_SOURCE.count("sessionStartup.startRecovery();"), 1)
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/features/sessions.js");

const values = new Map([
  ["code-foreground-view", "session"],
  ["code-last-session", "alpha"],
]);
const storage = {
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: (key) => values.delete(key),
};
const state = {
  sessions: [{id: "alpha"}, {id: "running", runState: {status: "running"}}],
};
const events = [];
const errors = [];
const navigation = {
  loadSession: async (sessionId) => events.push(["load", sessionId]),
  rememberWelcomeForeground: () => {
    events.push(["welcome"]);
    values.set("code-foreground-view", "welcome");
    values.delete("code-last-session");
  },
};
const recovery = {
  resumePersistedRuns: async () => {
    events.push(["runs-start"]);
    await Promise.resolve();
    events.push(["runs-finish"]);
  },
  resumePersistedQueuedMessages: async () => events.push(["queued"]),
  resumePersistedBackgroundRuns: async () => events.push(["background"]),
};
const startup = window.Code.features.sessions.createSessionStartup({
  state,
  storage,
  navigation,
  recovery,
  logger: {error: (...args) => errors.push(args.map(String))},
});

(async () => {
  const restored = await startup.restoreForegroundSession();
  const tasks = startup.startRecovery();
  const afterStart = events.slice();
  await Promise.all([tasks.foreground, tasks.background]);
  const afterRecovery = events.slice();

  values.set("code-foreground-view", "welcome");
  values.set("code-last-session", "alpha");
  const welcomeResult = await startup.restoreForegroundSession();

  const failingStartup = window.Code.features.sessions.createSessionStartup({
    state,
    storage,
    navigation,
    recovery: {
      resumePersistedRuns: async () => { throw new Error("runs failed"); },
      resumePersistedQueuedMessages: async () => events.push(["unexpected-queued"]),
      resumePersistedBackgroundRuns: async () => { throw new Error("background failed"); },
    },
    logger: {error: (...args) => errors.push(args.map((value) => value?.message || String(value)))},
  });
  const failedTasks = failingStartup.startRecovery();
  await Promise.all([failedTasks.foreground, failedTasks.background]);

  process.stdout.write(JSON.stringify({
    restored,
    afterStart,
    afterRecovery,
    welcomeResult,
    foregroundView: values.get("code-foreground-view"),
    lastSession: values.get("code-last-session") || null,
    errors,
  }));
})();
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["restored"], "alpha")
        self.assertEqual(
            result["afterStart"],
            [["load", "alpha"], ["runs-start"], ["background"]],
        )
        self.assertEqual(
            result["afterRecovery"],
            [["load", "alpha"], ["runs-start"], ["background"], ["runs-finish"], ["queued"]],
        )
        self.assertIsNone(result["welcomeResult"])
        self.assertEqual(result["foregroundView"], "welcome")
        self.assertIsNone(result["lastSession"])
        self.assertEqual(len(result["errors"]), 2)
        self.assertFalse(any(event[0] == "unexpected-queued" for event in result["afterRecovery"]))

        startup_start = SESSIONS_SOURCE.index("function createSessionStartup(")
        restore_start = SESSIONS_SOURCE.index("async function restoreForegroundSession()", startup_start)
        recovery_start = SESSIONS_SOURCE.index("function startRecovery()", restore_start)
        startup_end = SESSIONS_SOURCE.index("features.sessions = Object.freeze", recovery_start)
        self.assertIn('storage.getItem("code-foreground-view")', SESSIONS_SOURCE[restore_start:recovery_start])
        self.assertIn(
            "await navigation.loadSession(lastId, { userInitiated: false });",
            SESSIONS_SOURCE[restore_start:recovery_start],
        )
        self.assertIn(
            ".then(() => recovery.resumePersistedQueuedMessages())",
            SESSIONS_SOURCE[recovery_start:startup_end],
        )
        self.assertIn(
            "const background = recovery.resumePersistedBackgroundRuns()",
            SESSIONS_SOURCE[recovery_start:startup_end],
        )

    def test_internal_restore_does_not_consume_user_switch_debounce(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/features/sessions.js");

let now = 1_000;
Date.now = () => now;
const values = new Map([
  ["code-foreground-view", "session"],
  ["code-last-session", "alpha"],
]);
const storage = {
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: (key) => values.delete(key),
};
const records = Object.fromEntries(["alpha", "beta", "gamma"].map((id) => [id, {
  id,
  title: id.toUpperCase(),
  messages: [],
  stats: {input: 0, output: 0, cache: 0},
  runState: {},
  lastUsage: null,
}]));
const state = {
  sessionId: null,
  sessions: Object.values(records).map((record) => ({...record})),
  projectsMap: {},
  pendingProjectId: null,
  messages: [],
  stats: {},
  pendingEdits: {},
  _sessionMsgs: {},
  _sessionStats: {},
  _sessionLastUsage: {},
  _sessionRunStates: {},
  _foregroundNavigationSeq: 0,
  _sessionLoadSeq: 0,
  branchPanelOpen: false,
  _keepBranchOpen: false,
};
const getCalls = [];
const data = {
  createSession: async () => records.alpha,
  getSession: async (sessionId) => {
    getCalls.push(sessionId);
    return {...records[sessionId]};
  },
};
const stateAccessors = {
  getSessionRunState: (sessionId) => state._sessionRunStates[sessionId] || {},
  setSessionRunState: (sessionId, value) => { state._sessionRunStates[sessionId] = value || {}; },
  setSessionMessages: (sessionId, value) => { state._sessionMsgs[sessionId] = value; },
  setSessionStats: (sessionId, value) => { state._sessionStats[sessionId] = value; },
  setSessionLastUsage: (sessionId, value) => { state._sessionLastUsage[sessionId] = value; },
};
const project = {
  getCurrentProject: () => null,
  getById: () => null,
  getPrimaryPath: () => "",
  getCurrentRoot: () => "",
  pathsEqual: () => true,
  saveRoot: async () => {},
};
const view = {
  cacheActiveSessionState: () => {},
  resetRenderCache: () => {},
  renderMessages: () => {},
  renderSessions: () => {},
  updateGroupBadge: () => {},
  updateStatsPanel: () => {},
  updateSendButtonState: () => {},
  syncActiveStreamingState: () => {},
  scheduleMessagesScrollToBottom: () => {},
  refreshSessions: async () => {},
  showToast: () => {},
};
const navigation = window.Code.features.sessions.createSessionNavigation({
  state,
  elements: {
    sessionTitle: {value: ""},
    branchPanel: {classList: {remove: () => {}}},
    toggleBranches: {classList: {remove: () => {}}},
  },
  storage,
  data,
  stateAccessors,
  project,
  branch: {
    syncMetadata: (summaries, session) => summaries.find((item) => item.id === session.id),
  },
  recovery: {
    reconcilePersistedUserInputRequest: async () => {},
    restoreAuthorizationRequest: () => {},
  },
  view,
  t: () => "Untitled",
});
const startup = window.Code.features.sessions.createSessionStartup({
  state,
  storage,
  navigation,
  recovery: {
    resumePersistedRuns: async () => {},
    resumePersistedQueuedMessages: async () => {},
    resumePersistedBackgroundRuns: async () => {},
  },
});

(async () => {
  await startup.restoreForegroundSession();
  const afterRestore = {
    sessionId: state.sessionId,
    lastSwitchTime: state._lastSwitchTime || null,
    getCalls: getCalls.slice(),
  };

  await navigation.loadSession("beta");
  const afterImmediateUserSwitch = {
    sessionId: state.sessionId,
    lastSwitchTime: state._lastSwitchTime,
    getCalls: getCalls.slice(),
  };

  await navigation.loadSession("gamma");
  const afterRapidUserSwitch = {
    sessionId: state.sessionId,
    getCalls: getCalls.slice(),
  };

  now = 1_300;
  await navigation.loadSession("gamma");
  const afterDebounceWindow = {
    sessionId: state.sessionId,
    lastSwitchTime: state._lastSwitchTime,
    getCalls: getCalls.slice(),
  };

  process.stdout.write(JSON.stringify({
    afterRestore,
    afterImmediateUserSwitch,
    afterRapidUserSwitch,
    afterDebounceWindow,
  }));
})();
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(
            result["afterRestore"],
            {"sessionId": "alpha", "lastSwitchTime": None, "getCalls": ["alpha"]},
        )
        self.assertEqual(
            result["afterImmediateUserSwitch"],
            {"sessionId": "beta", "lastSwitchTime": 1000, "getCalls": ["alpha", "beta"]},
        )
        self.assertEqual(
            result["afterRapidUserSwitch"],
            {"sessionId": "beta", "getCalls": ["alpha", "beta"]},
        )
        self.assertEqual(
            result["afterDebounceWindow"],
            {
                "sessionId": "gamma",
                "lastSwitchTime": 1300,
                "getCalls": ["alpha", "beta", "gamma"],
            },
        )

    def test_branches_feature_preserves_tree_creation_and_switching(self):
        self.assertIn("const { createBranchesFeature } = window.Code.features.branches;", APP_SOURCE)
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/features/branches.js");

const events = [];
const stats = new Map([["parent", {input: 12, output: 3, cache: 4, cost: 0.5}]]);
const usage = new Map([["parent", {total_tokens: 19}]]);
const state = {
  sessionId: "child",
  sessions: [
    {id: "parent", title: "Parent <root>", _branches: [], _branchDepth: 0},
    {id: "child", title: "Child", _parentId: "parent", _branches: [], _branchDepth: 1},
  ],
  isStreaming: false,
  branchPanelOpen: true,
  _keepBranchOpen: false,
};
let branchHtml = "";
let createHandler = null;
const elements = {
  branchTree: {
    get innerHTML() { return branchHtml; },
    set innerHTML(value) { branchHtml = value; },
    querySelectorAll: () => [],
  },
  createBranchBtn: {
    addEventListener: (name, handler) => {
      events.push(["bind", name]);
      createHandler = handler;
    },
  },
};
const requestJson = async (url, options) => {
  events.push(["request", url, options.method, JSON.parse(options.body)]);
  return {id: "branch-new", title: "Branch: Child", stats: {}, lastUsage: null};
};
const feature = window.Code.features.branches.createBranchesFeature({
  state,
  elements,
  requestJson,
  stateAccessors: {
    getSessionStats: (sessionId) => stats.get(sessionId) || {},
    getSessionLastUsage: (sessionId) => usage.get(sessionId) || null,
    setSessionStats: (sessionId, value) => {
      stats.set(sessionId, value);
      events.push(["stats", sessionId, value]);
    },
    setSessionLastUsage: (sessionId, value) => {
      usage.set(sessionId, value);
      events.push(["usage", sessionId, value]);
    },
  },
  session: {
    refreshSessions: async () => events.push(["refresh"]),
    loadSession: async (sessionId) => {
      events.push(["load", sessionId]);
      state.sessionId = sessionId;
    },
    deleteSession: async (sessionId) => events.push(["delete", sessionId]),
  },
  view: {
    showToast: (message, kind) => events.push(["toast", message, kind]),
  },
  t: (key, params = {}) => ({
    untitledSession: "Untitled",
    noBranches: "No branches",
    delete: "Delete",
    branchTitleTemplate: `Branch: ${params.title || ""}`,
    createSessionFirst: "Create session first",
    stopBeforeBranch: "Stop first",
    branchFailed: "Branch failed",
  }[key] || key),
  escapeHtml: (value) => String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;"),
});

(async () => {
  const tree = feature.buildBranchTree("child");
  feature.renderBranchTree();
  const rendered = branchHtml;

  state.sessionId = "parent";
  await feature.createBranch();
  const afterCreate = {
    stats: stats.get("branch-new"),
    usage: usage.get("branch-new"),
    keepOpen: state._keepBranchOpen,
    sessionId: state.sessionId,
  };

  await feature.switchToBranch("child");
  feature.bind();

  state.sessionId = null;
  await feature.createBranch();
  state.sessionId = "parent";
  state.isStreaming = true;
  await feature.createBranch();

  process.stdout.write(JSON.stringify({
    tree,
    rendered,
    afterCreate,
    events,
    hasCreateHandler: typeof createHandler === "function",
  }));
})();
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["tree"]["id"], "parent")
        self.assertEqual(result["tree"]["children"][0]["id"], "child")
        self.assertTrue(result["tree"]["children"][0]["isActive"])
        self.assertIn("Parent &lt;root&gt;", result["rendered"])
        self.assertIn("branch-node active", result["rendered"])
        self.assertEqual(result["afterCreate"]["stats"], {"input": 12, "output": 3, "cache": 4, "cost": 0.5})
        self.assertEqual(result["afterCreate"]["usage"], {"total_tokens": 19})
        self.assertTrue(result["afterCreate"]["keepOpen"])
        self.assertEqual(result["afterCreate"]["sessionId"], "branch-new")
        self.assertIn(
            [
                "request",
                "/api/sessions/parent/branch",
                "POST",
                {"title": "Branch: Parent <root>"},
            ],
            result["events"],
        )
        self.assertIn(["refresh"], result["events"])
        self.assertIn(["load", "branch-new"], result["events"])
        self.assertIn(["load", "child"], result["events"])
        self.assertIn(["toast", "Create session first", "warning"], result["events"])
        self.assertIn(["toast", "Stop first", "warning"], result["events"])
        self.assertIn(["bind", "click"], result["events"])
        self.assertTrue(result["hasCreateHandler"])

        self.assertIn("const response = await requestJson(", BRANCHES_SOURCE)
        self.assertIn("item._parentId === record.id", BRANCHES_SOURCE)
        self.assertIn("void session.deleteSession(sessionId);", BRANCHES_SOURCE)
        self.assertIn("await session.refreshSessions();", BRANCHES_SOURCE)
        self.assertIn("await session.loadSession(response.id);", BRANCHES_SOURCE)
        self.assertNotIn("function buildBranchTree(", APP_SOURCE)
        self.assertNotIn("async function createBranch(", APP_SOURCE)
        self.assertNotIn("async function switchToBranch(", APP_SOURCE)

    def test_platform_core_normalizes_and_parses_key_config(self):
        self.assertIn('const WORKBAR_URL = "https://workbar.ai"', PLATFORM_SOURCE)
        script = r"""
const values = new Map([
  ["code-key-config", JSON.stringify([
    {name: "legacy", key: "sk-legacy", enabled: false},
    {name: "remote", key: "sk-remote", enabled: true, source: "platform"},
  ])],
]);
const storage = {
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
};
global.window = {localStorage: storage};
require("./src/core/namespace.js");
require("./src/core/platform.js");
const platform = window.Code.core.platform;
const loaded = platform.loadKeyConfig(storage);
const parsed = platform.parseKeyText([
  "primary: sk-primary",
  "secondary sk-secondary",
  "sk-plain",
  "duplicate: sk-primary",
  "remote: sk-remote",
].join("\n"), loaded);
const saved = platform.saveKeyConfig(parsed.entries, storage);
const synced = platform.mergeSyncedKeys(loaded, [
  {id: 1, name: "remote-renamed", status: 2},
  {id: 2, name: "manual-from-platform", status: 1},
  {id: 3, name: "new-platform", status: 1},
  {id: 4, name: "masked", status: 1},
], {1: "remote", 2: "legacy", 3: "new-full", 4: "sk-***mask"});
process.stdout.write(JSON.stringify({
  url: platform.WORKBAR_URL,
  loaded,
  parsed,
  saved,
  synced,
  formatted: platform.formatSyncedKeyLine("team:\nprimary", "raw-value"),
  masked: platform.maskSyncedKey("raw-value"),
  serialized: platform.serializeKeyEntries(saved),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["url"], "https://workbar.ai")
        self.assertEqual(data["loaded"][0]["source"], "manual")
        self.assertFalse(data["loaded"][0]["enabled"])
        self.assertEqual(data["loaded"][1]["source"], "platform")
        self.assertEqual(data["parsed"]["duplicates"], ["duplicate"])
        self.assertEqual([entry["key"] for entry in data["saved"]], [
            "sk-primary", "sk-secondary", "sk-plain", "sk-remote",
        ])
        self.assertEqual(data["saved"][-1]["source"], "platform")
        self.assertIn("primary: sk-primary", data["serialized"])
        self.assertEqual(data["synced"]["imported"], 1)
        self.assertEqual(data["synced"]["updated"], 1)
        synced = {entry["key"]: entry for entry in data["synced"]["entries"]}
        self.assertEqual(synced["sk-legacy"]["name"], "legacy")
        self.assertEqual(synced["sk-legacy"]["source"], "manual")
        self.assertEqual(synced["sk-legacy"]["platformTokenId"], "2")
        self.assertEqual(synced["sk-remote"]["name"], "remote-renamed")
        self.assertFalse(synced["sk-remote"]["enabled"])
        self.assertEqual(synced["sk-remote"]["platformTokenId"], "1")
        self.assertEqual(synced["sk-new-full"]["source"], "platform")
        self.assertEqual(synced["sk-new-full"]["platformTokenId"], "3")
        self.assertEqual(data["formatted"], "team primary: sk-raw-value")
        self.assertTrue(data["masked"].startswith("sk-•"))
        self.assertTrue(data["masked"].endswith("alue"))
        self.assertNotIn("raw-value", data["masked"])

    def test_platform_key_exclusions_store_only_account_and_token_ids(self):
        script = r"""
const values = new Map();
const storage = {
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
};
global.window = {localStorage: storage};
require("./src/core/namespace.js");
require("./src/core/platform.js");
const platform = window.Code.core.platform;
platform.excludePlatformToken("7", 12, storage);
platform.excludePlatformToken("7", "13", storage);
platform.excludePlatformToken("7", 12, storage);
platform.excludePlatformToken("8", 22, storage);
const rejected = platform.excludePlatformToken("7", "not-a-token-id", storage);
const exclusions = platform.loadPlatformKeyExclusions("7", storage);
const merged = platform.mergeSyncedKeys([
  {name: "manual", key: "sk-manual", enabled: true, source: "manual"},
], [
  {id: 12, name: "removed", status: 1},
  {id: 14, name: "manual-match", status: 1},
  {id: 15, name: "new", status: 1},
], {12: "removed", 14: "manual", 15: "new"}, {excludedTokenIds: exclusions});
process.stdout.write(JSON.stringify({
  rejected,
  exclusions: [...exclusions],
  otherAccount: [...platform.loadPlatformKeyExclusions("8", storage)],
  rawState: values.get(platform.KEY_SYNC_EXCLUSIONS_STORAGE_KEY),
  merged,
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertFalse(data["rejected"])
        self.assertEqual(data["exclusions"], ["12", "13"])
        self.assertEqual(data["otherAccount"], ["22"])
        raw_state = json.loads(data["rawState"])
        self.assertEqual(raw_state, {
            "version": 1,
            "accounts": {"7": ["12", "13"], "8": ["22"]},
        })
        self.assertNotIn("sk-", data["rawState"])
        self.assertNotIn("key", data["rawState"].lower())
        self.assertNotIn("name", data["rawState"].lower())
        merged = {entry["key"]: entry for entry in data["merged"]["entries"]}
        self.assertNotIn("sk-removed", merged)
        self.assertEqual(merged["sk-manual"]["source"], "manual")
        self.assertEqual(merged["sk-manual"]["platformTokenId"], "14")
        self.assertEqual(merged["sk-new"]["platformTokenId"], "15")
        self.assertEqual(data["merged"]["imported"], 1)

    def test_key_config_save_removes_legacy_sensitive_copy(self):
        script = r"""
const values = new Map([
  ["code-key", "legacy-sensitive-copy"],
  ["agent-lite-key", "older-sensitive-copy"],
  ["agent-lite-key-config", "old-structured-sensitive-copy"],
]);
const removed = [];
const storage = {
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: (key) => { removed.push(key); values.delete(key); },
};
global.window = {localStorage: storage};
require("./src/core/namespace.js");
require("./src/core/platform.js");
const platform = window.Code.core.platform;
platform.saveKeyConfig([
  {name: "manual", key: "sk-manual", enabled: true, source: "manual"},
], storage);
process.stdout.write(JSON.stringify({
  removed,
  legacyExists: platform.LEGACY_KEY_STORAGE_KEYS.some((key) => values.has(key)),
  structuredExists: values.has("code-key-config"),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["removed"], [
            "code-key",
            "agent-lite-key",
            "agent-lite-key-config",
        ])
        self.assertFalse(data["legacyExists"])
        self.assertTrue(data["structuredExists"])

    def test_legacy_key_migration_is_one_time_and_cannot_restore_deleted_keys(self):
        script = r"""
function makeStorage(initial) {
  const values = new Map(initial);
  return {
    values,
    getItem: (key) => values.has(key) ? values.get(key) : null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
}
global.window = {localStorage: makeStorage([])};
require("./src/core/namespace.js");
require("./src/core/platform.js");
const platform = window.Code.core.platform;

const deletedStorage = makeStorage([
  [platform.KEY_CONFIG_STORAGE_KEY, "[]"],
  ["agent-lite-key", "stale-text-value"],
  ["agent-lite-key-config", JSON.stringify([{name: "stale", key: "stale-structured-value"}])],
]);
const keptDeleted = platform.migrateLegacyKeyConfig(deletedStorage);

const firstUpgradeStorage = makeStorage([
  ["agent-lite-key-config", JSON.stringify([{name: "old", key: "old-structured-value"}])],
]);
const firstMigration = platform.migrateLegacyKeyConfig(firstUpgradeStorage);
platform.saveKeyConfig([], firstUpgradeStorage);
const afterDeleteAndRestart = platform.migrateLegacyKeyConfig(firstUpgradeStorage);

process.stdout.write(JSON.stringify({
  keptDeletedCount: keptDeleted.length,
  deletedLegacyRemaining: platform.LEGACY_KEY_STORAGE_KEYS.filter((key) => deletedStorage.values.has(key)),
  firstMigrationCount: firstMigration.length,
  afterDeleteAndRestartCount: afterDeleteAndRestart.length,
  upgradeLegacyRemaining: platform.LEGACY_KEY_STORAGE_KEYS.filter((key) => firstUpgradeStorage.values.has(key)),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["keptDeletedCount"], 0)
        self.assertEqual(data["deletedLegacyRemaining"], [])
        self.assertEqual(data["firstMigrationCount"], 1)
        self.assertEqual(data["afterDeleteAndRestartCount"], 0)
        self.assertEqual(data["upgradeLegacyRemaining"], [])

        migration_start = APP_SOURCE.index("const keyMap = [")
        migration_end = APP_SOURCE.index("];", migration_start)
        generic_key_map = APP_SOURCE[migration_start:migration_end]
        self.assertNotIn('"key"', generic_key_map)
        self.assertNotIn('"key-config"', generic_key_map)
        self.assertNotIn('"platform-auth"', generic_key_map)
        self.assertIn("migrateLegacyKeyConfig(localStorage);", APP_SOURCE)
        self.assertNotIn('parseKeyText(localStorage.getItem("code-key")', APP_SOURCE)

    def test_modules_export_through_code_core(self):
        icons = (ROOT / "src/core/icons.js").read_text(encoding="utf-8")
        utils = (ROOT / "src/core/utils.js").read_text(encoding="utf-8")
        i18n = (ROOT / "src/core/i18n.js").read_text(encoding="utf-8")
        self.assertIn("core.icons = Object.freeze", icons)
        self.assertIn("core.utils = Object.freeze", utils)
        self.assertIn("core.i18n = Object.freeze", i18n)
        for name in (
            "escapeHtml",
            "formatCompact",
            "formatNumber",
            "formatElapsed",
            "estimateTokens",
        ):
            self.assertIn(name, utils)

    def test_i18n_runtime_translates_interpolates_switches_and_keeps_keys_in_sync(self):
        script = """
global.window = {Code: {core: {}}};
require("./src/core/i18n.js");
let language = "zh";
const persisted = [];
const changed = [];
const runtime = window.Code.core.i18n.createI18nRuntime({
  getLanguage: () => language,
  setLanguage: (nextLanguage) => { language = nextLanguage; },
  persistLanguage: (nextLanguage) => persisted.push(nextLanguage),
  onLanguageChanged: (nextLanguage) => changed.push(nextLanguage),
});
const zh = runtime.t("editingMemory", {name: "demo"});
const zhDeleteSession = runtime.t("deleteSessionConfirmMessage", {name: "示例"});
runtime.setLang("en");
const en = runtime.t("editingMemory", {name: "demo"});
const enDeleteSession = runtime.t("deleteSessionConfirmMessage", {name: "Example"});
const {LANG, I18N} = window.Code.core.i18n;
const missingKeys = {
  i18nEn: Object.keys(I18N.zh).filter((key) => !(key in I18N.en)),
  i18nZh: Object.keys(I18N.en).filter((key) => !(key in I18N.zh)),
  langEn: Object.keys(LANG.zh).filter((key) => !(key in LANG.en)),
  langZh: Object.keys(LANG.en).filter((key) => !(key in LANG.zh)),
};
process.stdout.write(JSON.stringify({zh, zhDeleteSession, en, enDeleteSession, persisted, changed, missingKeys}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "zh": "编辑中：demo",
                "zhDeleteSession": "删除会话「示例」？此操作不可恢复。",
                "en": "Editing: demo",
                "enDeleteSession": 'Delete session "Example"? This action cannot be undone.',
                "persisted": ["en"],
                "changed": ["en"],
                "missingKeys": {
                    "i18nEn": [],
                    "i18nZh": [],
                    "langEn": [],
                    "langZh": [],
                },
            },
        )

    def test_notifications_export_through_code_services(self):
        source = (ROOT / "src/services/notifications.js").read_text(encoding="utf-8")
        self.assertIn("services.notifications = Object.freeze", source)
        self.assertIn("showToast", source)
        self.assertIn("notify", source)
        script = """
const scheduled = [];
const children = [];
global.window = {
  Code: {services: {}},
  document: {
    getElementById: () => ({appendChild: (child) => children.push(child)}),
    createElement: () => ({style: {}, remove: () => {}}),
  },
  setTimeout: (_callback, delay) => scheduled.push(delay),
};
require("./src/services/notifications.js");
const {showToast} = window.Code.services.notifications;
showToast("default");
showToast("long", "info", {duration: 7000});
showToast("bounded", "info", {duration: 99999});
process.stdout.write(JSON.stringify({scheduled, childCount: children.length}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            {"scheduled": [3000, 7000, 15000], "childCount": 3},
        )

    def test_api_client_exports_and_preserves_json_request_behavior(self):
        self.assertIn("services.apiClient = Object.freeze", API_CLIENT_SOURCE)
        script = """
global.window = {Code: {services: {}}};
const calls = [];
const responses = [
  {ok: true, status: 200, statusText: "OK", json: async () => ({value: 42})},
  {ok: false, status: 400, statusText: "Bad Request", json: async () => ({error: "broken"})},
  {ok: false, status: 502, statusText: "Bad Gateway", json: async () => { throw new Error("invalid json"); }},
  {ok: true, status: 204, statusText: "No Content", json: async () => { throw new Error("empty"); }},
];
window.fetch = async (url, options) => {
  calls.push({url, options});
  return responses.shift();
};
require("./src/services/api-client.js");
const {apiJson} = window.Code.services.apiClient;
(async () => {
  const success = await apiJson("/success", {
    method: "POST",
    headers: {"X-Trace": "trace-1"},
    body: JSON.stringify({hello: "world"}),
  });
  let serverError = "";
  let serverErrorStatus = 0;
  let serverErrorData = null;
  let invalidError = "";
  try { await apiJson("/server-error"); } catch (error) {
    serverError = error.message;
    serverErrorStatus = error.status;
    serverErrorData = error.data;
  }
  try { await apiJson("/invalid-error"); } catch (error) { invalidError = error.message; }
  const emptySuccess = await apiJson("/empty-success");
  process.stdout.write(JSON.stringify({success, serverError, serverErrorStatus, serverErrorData, invalidError, emptySuccess, calls}));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["success"], {"value": 42})
        self.assertEqual(data["serverError"], "broken")
        self.assertEqual(data["serverErrorStatus"], 400)
        self.assertEqual(data["serverErrorData"], {"error": "broken"})
        self.assertEqual(data["invalidError"], "HTTP 502: Bad Gateway")
        self.assertEqual(data["emptySuccess"], {})
        self.assertEqual(data["calls"][0]["url"], "/success")
        self.assertEqual(data["calls"][0]["options"]["method"], "POST")
        self.assertEqual(
            data["calls"][0]["options"]["headers"],
            {"Content-Type": "application/json", "X-Trace": "trace-1"},
        )

    def test_files_feature_exports_sorting_paths_and_attachment_flow(self):
        self.assertIn("features.files = Object.freeze", FILES_SOURCE)
        script = """
global.window = {
  Code: {features: {}},
  btoa: (binary) => Buffer.from(binary, "binary").toString("base64"),
};
require("./src/features/files.js");
const {shortPath, sortFileItems, formatFileTimestamp, FILE_TIME_WIDE_SIDEBAR_MIN, createFilesFeature} = window.Code.features.files;
const items = [
  {name: "z-dir", path: "z-dir", type: "dir", updatedAt: "2026-01-01"},
  {name: "b.ts", path: "b.ts", type: "file", updatedAt: "2026-01-03"},
  {name: "a.js", path: "a.js", type: "file", updatedAt: "2026-01-02"},
  {name: "a-dir", path: "a-dir", type: "dir", updatedAt: "2026-01-04"},
];
const calls = [];
const inserted = [];
const density = [];
const elements = {
  filePicker: {value: "old", clicked: false, click() { this.clicked = true; }},
  attachFile: {disabled: false},
  fileTree: {classList: {toggle: (name, enabled) => density.push({name, enabled})}},
};
const feature = createFilesFeature({
  state: {},
  elements,
  t: (key) => key,
  escapeHtml: (value) => String(value),
  apiJson: async (url, options) => {
    calls.push({url, options});
    return {path: "attachments/demo.txt"};
  },
  insertPromptText: (value) => inserted.push(value),
});
(async () => {
  feature.pickProjectFile();
  await feature.resolvePickedFile({
    name: "demo.txt",
    arrayBuffer: async () => Uint8Array.from([104, 105]).buffer,
  });
  feature.setFileTimeDensity(319);
  feature.setFileTimeDensity(320);
  const now = new Date(2026, 6, 19, 15, 0);
  process.stdout.write(JSON.stringify({
    short: shortPath("C:/Users/Admin/project"),
    defaultOrder: sortFileItems(items).map((item) => item.path),
    typeOrder: sortFileItems(items, "type", true).map((item) => item.path),
    timeOrder: sortFileItems(items, "time", true).map((item) => item.path),
    pickerCleared: elements.filePicker.value,
    pickerClicked: elements.filePicker.clicked,
    attachDisabled: elements.attachFile.disabled,
    inserted,
    calls,
    density,
    densityBoundary: FILE_TIME_WIDE_SIDEBAR_MIN,
    todayTime: formatFileTimestamp(new Date(2026, 6, 19, 8, 7), now),
    sameYearTime: formatFileTimestamp(new Date(2026, 0, 2, 3, 4), now),
    oldTime: formatFileTimestamp(new Date(2025, 11, 31, 23, 59), now),
    invalidTime: formatFileTimestamp("invalid", now),
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["short"], "~\\Admin\\project")
        self.assertEqual(data["defaultOrder"], ["a-dir", "z-dir", "a.js", "b.ts"])
        self.assertEqual(data["typeOrder"], ["a-dir", "z-dir", "a.js", "b.ts"])
        self.assertEqual(data["timeOrder"], ["a-dir", "b.ts", "a.js", "z-dir"])
        self.assertEqual(data["pickerCleared"], "")
        self.assertTrue(data["pickerClicked"])
        self.assertFalse(data["attachDisabled"])
        self.assertEqual(data["inserted"], ["attachments/demo.txt"])
        self.assertEqual(data["densityBoundary"], 320)
        self.assertEqual(data["density"], [
            {"name": "file-time-wide", "enabled": False},
            {"name": "file-time-wide", "enabled": True},
        ])
        self.assertEqual(data["todayTime"], {
            "compact": "08:07",
            "full": "2026/07/19 08:07",
        })
        self.assertEqual(data["sameYearTime"], {
            "compact": "01/02 03:04",
            "full": "2026/01/02 03:04",
        })
        self.assertEqual(data["oldTime"], {
            "compact": "2025/12/31",
            "full": "2025/12/31 23:59",
        })
        self.assertEqual(data["invalidTime"], {"compact": "", "full": ""})
        self.assertIn('class="file-time"', FILES_SOURCE)
        self.assertIn('class="file-time-compact"', FILES_SOURCE)
        self.assertIn('class="file-time-full"', FILES_SOURCE)
        self.assertIn(".file-tree.file-time-wide .file-time-full", STYLE_SOURCE)
        self.assertIn(".file-item-row:hover .file-time", STYLE_SOURCE)
        self.assertEqual(data["calls"][0]["url"], "/api/attachments")
        self.assertEqual(data["calls"][0]["options"]["method"], "POST")
        self.assertEqual(
            json.loads(data["calls"][0]["options"]["body"]),
            {"name": "demo.txt", "contentBase64": "aGk="},
        )

    def test_silent_file_tree_refresh_coalesces_latest_wins_and_preserves_view_state(self):
        script = r"""
global.window = {
  Code: {features: {}},
  setTimeout,
  clearTimeout,
};
require("./src/features/files.js");
const {createSilentFileTreeRefreshController} = window.Code.features.files;

const timers = [];
const requests = [];
const pending = [];
const applied = [];
let view = {root: "C:/demo", dir: "src", search: "needle", previewPath: "src/a.js", scrollTop: 41};
const controller = createSilentFileTreeRefreshController({
  captureView: () => view ? {...view} : null,
  requestItems: (captured) => {
    requests.push({...captured});
    return new Promise((resolve, reject) => pending.push({resolve, reject, captured}));
  },
  applyItems: (data, captured) => applied.push({data, captured}),
  isViewCurrent: (captured, data) => Boolean(
    view
    && view.root === captured.root
    && view.dir === captured.dir
    && data.root === captured.root
    && data.path === captured.dir
  ),
  setTimeout: (callback) => { timers.push(callback); return timers.length; },
  clearTimeout: () => {},
  delayMs: 0,
});

(async () => {
  const scheduledFirst = controller.schedule({turnId: "run-1", root: "c:\\demo\\"});
  const duplicateFirst = controller.schedule({turnId: "run-1", root: "C:/demo"});
  const scheduledSecond = controller.schedule({turnId: "run-2", root: "C:/demo"});
  timers.shift()();
  await Promise.resolve();
  pending[0].resolve({root: "C:/demo", path: "src", items: [{name: "old.js"}]});
  await Promise.resolve();
  await Promise.resolve();
  const afterCoalesced = controller.snapshot();

  controller.schedule({turnId: "run-3", root: "C:/demo"});
  timers.shift()();
  await Promise.resolve();
  controller.schedule({turnId: "run-4", root: "C:/demo"});
  timers.shift()();
  await Promise.resolve();
  pending[2].resolve({root: "C:/demo", path: "src", items: [{name: "latest.js"}]});
  await Promise.resolve();
  await Promise.resolve();
  pending[1].resolve({root: "C:/demo", path: "src", items: [{name: "stale.js"}]});
  await Promise.resolve();
  await Promise.resolve();

  controller.schedule({turnId: "run-5", root: "C:/demo"});
  timers.shift()();
  await Promise.resolve();
  pending[3].reject(new Error("offline"));
  await Promise.resolve();
  await Promise.resolve();
  const afterFailure = controller.snapshot();

  const otherProject = controller.schedule({turnId: "run-other", root: "C:/other"});
  view = null;
  const noProject = controller.schedule({turnId: "run-6", root: "C:/demo"});
  process.stdout.write(JSON.stringify({
    scheduledFirst,
    duplicateFirst,
    scheduledSecond,
    requests,
    applied,
    afterCoalesced,
    afterFailure,
    otherProject,
    noProject,
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["scheduledFirst"])
        self.assertFalse(data["duplicateFirst"])
        self.assertTrue(data["scheduledSecond"])
        self.assertEqual(len(data["requests"]), 4)
        self.assertEqual(data["requests"][0]["search"], "needle")
        self.assertEqual(data["requests"][0]["previewPath"], "src/a.js")
        self.assertEqual(data["requests"][0]["scrollTop"], 41)
        self.assertEqual(len(data["applied"]), 2)
        self.assertEqual(data["applied"][0]["data"]["items"], [{"name": "old.js"}])
        self.assertEqual(data["applied"][1]["data"]["items"], [{"name": "latest.js"}])
        self.assertEqual(data["afterCoalesced"]["requestCount"], 1)
        self.assertEqual(data["afterCoalesced"]["applyCount"], 1)
        self.assertEqual(data["afterFailure"]["requestCount"], 4)
        self.assertEqual(data["afterFailure"]["applyCount"], 2)
        self.assertFalse(data["otherProject"])
        self.assertFalse(data["noProject"])

    def test_file_feature_silent_refresh_keeps_search_selection_scroll_and_handles_empty_tree(self):
        script = r"""
global.window = {Code: {features: {}}, setTimeout, clearTimeout};
require("./src/features/files.js");
const {createFilesFeature} = window.Code.features.files;
const callbacks = [];
const fileTree = {
  innerHTML: "",
  scrollTop: 63,
  classList: {toggle() {}},
  querySelectorAll: () => [],
};
const state = {
  currentDir: "src",
  _fileRoot: "C:/demo",
  _fileItems: [{name: "old.js", path: "src/old.js", type: "file"}],
  previewPath: "src/keep.js",
};
const elements = {
  fileTree,
  projectRoot: {value: "C:/demo"},
  fileSearch: {value: "keep"},
  filePathBar: {style: {}, innerHTML: "", querySelectorAll: () => [], scrollWidth: 0, clientWidth: 100},
  cwdPathText: {textContent: "~\\demo"},
  goUp: {disabled: false},
  newFolderBtn: {disabled: false},
  refreshFiles: {disabled: false},
};
let nextItems = [];
const calls = [];
const feature = createFilesFeature({
  state,
  elements,
  t: (key) => key,
  escapeHtml: (value) => String(value),
  apiJson: async (url) => { calls.push(url); return {root: "C:/demo", path: "src", items: nextItems}; },
  setTimeout: (callback) => { callbacks.push(callback); return callbacks.length; },
  clearTimeout: () => {},
  silentRefreshDelayMs: 0,
});
(async () => {
  const scheduled = feature.scheduleSilentRefresh({turnId: "run-empty", root: "C:/demo"});
  callbacks.shift()();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  const empty = {
    items: state._fileItems,
    dir: state.currentDir,
    search: elements.fileSearch.value,
    previewPath: state.previewPath,
    scrollTop: fileTree.scrollTop,
    snapshot: feature.snapshotSilentRefresh(),
  };
  nextItems = [{name: "keep.js", path: "src/keep.js", type: "file"}];
  feature.scheduleSilentRefresh({turnId: "run-new", root: "C:/demo"});
  callbacks.shift()();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  process.stdout.write(JSON.stringify({scheduled, calls, empty, final: {
    items: state._fileItems,
    dir: state.currentDir,
    search: elements.fileSearch.value,
    previewPath: state.previewPath,
    scrollTop: fileTree.scrollTop,
    snapshot: feature.snapshotSilentRefresh(),
  }}));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["scheduled"])
        self.assertEqual(data["calls"], ["/api/files?path=src", "/api/files?path=src"])
        self.assertEqual(data["empty"]["items"], [])
        self.assertEqual(data["empty"]["dir"], "src")
        self.assertEqual(data["empty"]["search"], "keep")
        self.assertEqual(data["empty"]["previewPath"], "src/keep.js")
        self.assertEqual(data["empty"]["scrollTop"], 63)
        self.assertEqual(data["final"]["items"], [{"name": "keep.js", "path": "src/keep.js", "type": "file"}])
        self.assertEqual(data["final"]["dir"], "src")
        self.assertEqual(data["final"]["search"], "keep")
        self.assertEqual(data["final"]["previewPath"], "src/keep.js")
        self.assertEqual(data["final"]["scrollTop"], 63)
        self.assertEqual(data["final"]["snapshot"]["requestCount"], 2)
        self.assertEqual(data["final"]["snapshot"]["applyCount"], 2)

    def test_silent_file_tree_refresh_is_wired_only_to_real_terminal_boundaries(self):
        self.assertIn("function scheduleTerminalFileTreeRefresh(ctx, terminalStatus)", APP_SOURCE)
        self.assertIn('if (!["completed", "failed", "cancelled"].includes', APP_SOURCE)
        self.assertIn("backgroundJobId: job.id", APP_SOURCE)
        self.assertIn("job.status === \"completed\" ? \"completed\" : \"failed\"", APP_SOURCE)
        self.assertIn("recoveryError ? (recoveryError?.name === \"AbortError\" ? \"cancelled\" : \"failed\") : \"completed\"", APP_SOURCE)
        self.assertIn("loopError ? (loopError?.name === \"AbortError\" ? \"cancelled\" : \"failed\") : \"completed\"", APP_SOURCE)
        terminal_schedule = APP_SOURCE.index("scheduleTerminalFileTreeRefresh(\n    ctx,", APP_SOURCE.index("async function sendMessage"))
        final_save = APP_SOURCE.index("await saveSessionState(sessionId, ctx.messages, ctx.stats);", terminal_schedule)
        self.assertLess(terminal_schedule, final_save)
        self.assertNotIn("scheduleTerminalFileTreeRefresh", APP_SOURCE[APP_SOURCE.index("async function enqueueSessionMessage"):APP_SOURCE.index("async function submitSessionSteer")])
        self.assertNotIn("scheduleTerminalFileTreeRefresh", APP_SOURCE[APP_SOURCE.index("async function finishServerAgentUserInputRequest"):APP_SOURCE.index("function renderUserInputQuestion")])
        self.assertNotIn("scheduleTerminalFileTreeRefresh", APP_SOURCE[APP_SOURCE.index("async function requestServerAgentAuthorization"):APP_SOURCE.index("async function runServerAgentLoop")])
        self.assertIn("scheduleSilentRefresh: silentRefresh.schedule", FILES_SOURCE)
        self.assertIn("silentRefresh.invalidate();", FILES_SOURCE)

    def test_file_context_menu_distinguishes_explorer_from_default_open(self):
        self.assertIn('if (action === "reveal") body.reveal = true;', FILES_SOURCE)
        self.assertIn('if (action === "explore") body.explorer = true;', FILES_SOURCE)
        self.assertIn('if (action === "terminal") body.terminal = true;', FILES_SOURCE)
        self.assertIn('void requestOpenFile(apiJson, showToast, t, body);', FILES_SOURCE)
        self.assertNotIn('fetchImpl("/api/open-file"', FILES_SOURCE)
        self.assertIn('apiJson("/api/open-file"', APP_SOURCE)
        self.assertIn('body: JSON.stringify({ path: fp, reveal: true })', APP_SOURCE)
        self.assertNotIn('body: JSON.stringify({ path: fp, explorer: true })', APP_SOURCE)

    def test_file_context_open_response_is_silent_on_success_and_sanitizes_failures(self):
        script = r"""
global.window = {Code: {features: {}}};
require('./src/features/files.js');
const {requestOpenFile} = window.Code.features.files;
const calls = [];
const toasts = [];
const t = (key) => `translated:${key}`;
const showToast = (message, kind) => toasts.push([message, kind]);
const responder = (result, error) => async (url, options) => {
  calls.push([url, options.method, JSON.parse(options.body)]);
  if (error) throw error;
  return result;
};
(async () => {
  const success = await requestOpenFile(
    responder({ok: true, degraded: false}), showToast, t, {path: 'ok.txt', reveal: true},
  );
  const afterSuccess = toasts.slice();
  const degraded = await requestOpenFile(
    responder({ok: true, degraded: true, degradedReasons: ['foreground_not_granted']}),
    showToast, t, {path: 'folder', explorer: true},
  );
  const httpFailure = await requestOpenFile(
    responder(null, new Error('HTTP 400: sensitive server detail')),
    showToast, t, {path: 'bad.txt'},
  );
  const networkFailure = await requestOpenFile(
    responder(null, new Error('network contains internal endpoint')),
    showToast, t, {path: 'offline.txt'},
  );
  const invalidJsonProjection = await requestOpenFile(
    responder({}), showToast, t, {path: 'invalid.txt'},
  );
  const incompleteSuccess = await requestOpenFile(
    responder({ok: true}), showToast, t, {path: 'incomplete.txt'},
  );
  process.stdout.write(JSON.stringify({
    success, afterSuccess, degraded, httpFailure, networkFailure,
    invalidJsonProjection, incompleteSuccess, calls, toasts,
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["success"], {"ok": True, "degraded": False})
        self.assertEqual(data["afterSuccess"], [])
        self.assertTrue(data["degraded"]["degraded"])
        self.assertIsNone(data["httpFailure"])
        self.assertIsNone(data["networkFailure"])
        self.assertIsNone(data["invalidJsonProjection"])
        self.assertIsNone(data["incompleteSuccess"])
        self.assertEqual(data["toasts"], [
            ["translated:openDegraded", "warning"],
            ["translated:openFailed", "error"],
            ["translated:openFailed", "error"],
            ["translated:openFailed", "error"],
            ["translated:openFailed", "error"],
        ])
        self.assertEqual(data["calls"][0], [
            "/api/open-file", "POST", {"path": "ok.txt", "reveal": True},
        ])
        self.assertNotIn("sensitive", json.dumps(data["toasts"]))
        self.assertNotIn("internal endpoint", json.dumps(data["toasts"]))
        self.assertIn('openDegraded: "已打开位置，但未能完成选择或置前"', I18N_SOURCE)
        self.assertIn(
            'openDegraded: "Location opened, but selection or foreground activation was not completed"',
            I18N_SOURCE,
        )
        self.assertIn("successfulOpenSilent: true", H4_SMOKE_SOURCE)
        self.assertIn("degradedWarningVisible: true", H4_SMOKE_SOURCE)


    def test_file_tree_recursive_search_and_keyboard_navigation(self):
        self.assertIn('runStreamingSearch', FILES_SOURCE)
        self.assertIn('buildSearchLevels', FILES_SOURCE)
        self.assertIn('handleFileTreeKeydown', FILES_SOURCE)
        self.assertIn('tabindex="${index === 0 ? 0 : -1}"', FILES_SOURCE)
        script = r"""
global.window = {Code: {features: {}}, setTimeout, clearTimeout};
require('./src/features/files.js');
const {createFilesFeature} = window.Code.features.files;
const listeners = {};
const globCalls = [];
const buttons = [];
const fileTree = {
  innerHTML: '',
  scrollTop: 0,
  classList: {toggle() {}},
  addEventListener: (name, fn) => { listeners[name] = fn; },
  querySelectorAll: () => buttons,
  querySelector: () => null,
  insertAdjacentHTML: () => {},
};
const state = {
  currentDir: 'src',
  _fileRoot: 'C:/demo',
  _fileItems: [{name: 'a.js', path: 'src/a.js', type: 'file'}, {name: 'b.ts', path: 'src/b.ts', type: 'file'}],
  previewPath: '',
};
const elements = {
  fileTree,
  projectRoot: {value: 'C:/demo'},
  fileSearch: {value: '', addEventListener: (name, fn) => { listeners['search-' + name] = fn; }},
  filePathBar: {style: {}, innerHTML: '', querySelectorAll: () => [], scrollWidth: 0, clientWidth: 100},
  cwdPathText: {textContent: ''},
  goUp: {disabled: false, addEventListener: () => {}},
  newFolderBtn: {disabled: false, addEventListener: () => {}},
  refreshFiles: {disabled: false, addEventListener: () => {}},
  fileSortBtn: {addEventListener: () => {}},
};
const timers = [];
const documentRoot = {
  body: {appendChild: () => {}},
  getElementById: () => ({textContent: '', addEventListener: () => {}}),
  addEventListener: () => {},
  querySelector: () => null,
  activeElement: null,
};
const feature = createFilesFeature({
  state,
  elements,
  t: (key) => key,
  escapeHtml: (value) => String(value),
  openFile: (path) => { globCalls.push('open:' + path); },
  apiJson: async (url, options) => {
    if (url === '/api/tools/glob_files') {
      const body = JSON.parse(options.body);
      globCalls.push('glob:' + body.path + ':' + body.pattern);
      if (body.path === 'C:/demo/src') {
        return {ok: true, results: [{path: 'src/deep/config.json', type: 'file'}, {path: 'src/config', type: 'dir'}], truncated: true};
      }
      return {ok: true, results: [{path: 'src/deep/config.json', type: 'file'}], truncated: false};
    }
    return {root: 'C:/demo', path: 'src', items: state._fileItems};
  },
  setTimeout: (fn, ms) => { timers.push({fn, ms}); return timers.length; },
  clearTimeout: () => {},
  storage: {getItem: () => null, setItem: () => {}},
  documentRoot,
});
(async () => {
  feature.bind();
  feature.loadFiles();
  await Promise.resolve(); await Promise.resolve();
  const rendered = fileTree.innerHTML;
  const tabIndex0 = rendered.includes('tabindex="0"');
  const tabIndexNeg = rendered.includes('tabindex="-1"');
  const ariaSelected = rendered.includes('aria-selected="false"');
  // 搜索防抖：输入 'config' → 250ms 后调 glob_files（pattern 包装为 *config*）
  elements.fileSearch.value = 'config';
  listeners['search-input']();
  const searchingShown = fileTree.innerHTML.includes('searching');
  const debounced = timers.length;
  const timer = timers[timers.length - 1];
  await timer.fn();
  // 过期取消：再输入 'cfg' 触发新搜索，旧响应（已返回）仍被丢弃
  const globBeforeStale = globCalls.length;
  listeners['search-input']();
  await timers[timers.length - 1].fn();
  // 键盘导航：构造按钮 mock（渲染后 querySelectorAll 返回）
  const btnA = {dataset: {path: 'src/a.js', type: 'file'}, setAttribute: () => {}, classList: {toggle: () => {}}, addEventListener: () => {}, focus: () => { documentRoot.activeElement = btnA; globCalls.push('focus:a'); }, click: () => { globCalls.push('click:a'); }};
  const btnB = {dataset: {path: 'src/b.ts', type: 'file'}, setAttribute: () => {}, classList: {toggle: () => {}}, addEventListener: () => {}, focus: () => { globCalls.push('focus:b'); }, click: () => { globCalls.push('click:b'); }};
  buttons.length = 0; buttons.push(btnA, btnB);
  listeners['keydown']({key: 'ArrowDown', preventDefault: () => {}});
  listeners['keydown']({key: 'Enter', preventDefault: () => {}});
  // Esc 退出搜索
  elements.fileSearch.value = 'config';
  listeners['keydown']({key: 'Escape', preventDefault: () => {}});
  process.stdout.write(JSON.stringify({
    tabIndex0, tabIndexNeg, ariaSelected,
    searchingShown,
    debounced: debounced > 0,
    globCalls,
    globBeforeStale,
    searchCleared: elements.fileSearch.value,
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["tabIndex0"])
        self.assertTrue(data["tabIndexNeg"])
        self.assertTrue(data["ariaSelected"])
        self.assertTrue(data["searchingShown"])
        self.assertTrue(data["debounced"])
        self.assertIn('glob:C:/demo/src:*config*', data["globCalls"])
        self.assertIn('glob:C:/demo:*config*', data["globCalls"])
        self.assertIn('focus:a', data["globCalls"])
        self.assertIn('click:a', data["globCalls"])
        self.assertEqual(data["searchCleared"], "")
    def test_file_tree_streaming_search_order_dedupe_limit_cancel_cache(self):
        self.assertIn('runStreamingSearch', FILES_SOURCE)
        self.assertIn('buildSearchLevels', FILES_SOURCE)
        self.assertIn('SEARCH_LIMIT', FILES_SOURCE)
        script = r"""
global.window = {Code: {features: {}}, setTimeout, clearTimeout};
require('./src/features/files.js');
const {createFilesFeature} = window.Code.features.files;
const listeners = {};
const globCalls = [];
const buttons = [];
const fileTree = {
  innerHTML: '',
  scrollTop: 0,
  classList: {toggle() {}},
  addEventListener: (name, fn) => { listeners[name] = fn; },
  querySelectorAll: () => buttons,
  querySelector: () => null,
  insertAdjacentHTML: (pos, html) => { fileTree.innerHTML += html; },
};
const state = {
  currentDir: 'src/deep',
  _fileRoot: 'C:/demo',
  _fileItems: [],
  previewPath: '',
};
const elements = {
  fileTree,
  projectRoot: {value: 'C:/demo'},
  fileSearch: {value: '', addEventListener: (name, fn) => { listeners['search-' + name] = fn; }},
  filePathBar: {style: {}, innerHTML: '', querySelectorAll: () => [], scrollWidth: 0, clientWidth: 100},
  cwdPathText: {textContent: ''},
  goUp: {disabled: false, addEventListener: () => {}},
  newFolderBtn: {disabled: false, addEventListener: () => {}},
  refreshFiles: {disabled: false, addEventListener: () => {}},
  fileSortBtn: {addEventListener: () => {}},
};
const timers = [];
const documentRoot = {
  body: {appendChild: () => {}},
  getElementById: () => ({textContent: '', addEventListener: () => {}}),
  addEventListener: () => {},
  querySelector: () => null,
  activeElement: null,
};
const snapshots = [];
const bigResults = Array.from({length: 501}, (_, i) => ({path: 'bulk/' + i + '.txt', type: 'file'}));
const feature = createFilesFeature({
  state,
  elements,
  t: (key, params) => params ? key + JSON.stringify(params) : key,
  escapeHtml: (value) => String(value),
  openFile: () => {},
  apiJson: async (url, options) => {
    if (url === '/api/tools/glob_files') {
      const body = JSON.parse(options.body);
      globCalls.push('glob:' + body.path + ':' + body.pattern);
      snapshots.push(fileTree.innerHTML);
      const pattern = body.pattern;
      if (pattern === '*xy*') return {ok: true, results: [{path: 'src/deep/xy.txt', type: 'file'}]};
      if (pattern === '*fallback*') return {ok: true, results: [{path: 'outside/x.txt', type: 'file'}, {path: 'src/deep/x.json', type: 'file'}]};
      if (pattern === '*empty*') return {ok: true, results: [], truncated: false};
      if (pattern === '*big*') return {ok: true, results: bigResults, truncated: true};
      if (body.path === 'C:/demo/src/deep') return {ok: true, results: [{path: 'src/deep/x.json', type: 'file'}]};
      if (body.path === 'C:/demo/src') return {ok: true, results: [{path: 'src/a.js', type: 'file'}, {path: 'src/deep/x.json', type: 'file'}]};
      return {ok: true, results: [{path: 'config', type: 'dir'}], truncated: false};
    }
    return {root: 'C:/demo', path: 'src/deep', items: []};
  },
  setTimeout: (fn, ms) => { timers.push({fn, ms}); return timers.length; },
  clearTimeout: () => {},
  storage: {getItem: () => null, setItem: () => {}},
  documentRoot,
});
(async () => {
  feature.bind();
  feature.loadFiles();
  await Promise.resolve(); await Promise.resolve();
  const out = {};
  // A: 层级顺序（当前目录→父→根）+ 按 path 去重 + 进度行
  elements.fileSearch.value = 'cfg';
  listeners['search-input']();
  await timers[timers.length - 1].fn();
  await Promise.resolve(); await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const htmlA = fileTree.innerHTML;
  out.order = globCalls.filter((c) => c.includes('*cfg*'));
  out.dedupeCount = htmlA.split('data-path="src/deep/x.json" data-type="file"').length - 1;
  out.hasAjs = htmlA.includes('data-path="src/a.js"');
  out.hasConfigDir = htmlA.includes('data-path="config"');
  out.progressShown = snapshots.some((s) => s.includes('search-status-line') && s.includes('searchProgress'));
  out.progressHasY3 = snapshots.some((s) => s.includes('searchProgress') && s.includes('"y":3'));
  out.progressLevels = snapshots.filter((s) => s.includes('searchProgress')).map((s) => { const m = s.match(/"x":(\d+)/); return m ? Number(m[1]) : null; });
  out.noProgressWhenDone = !htmlA.includes('search-status-line');
  out.countLine = htmlA.includes('searchResultCount') && htmlA.includes('"n":3');
  // B: 全局 500 上限（当前层即达上限，不再请求根层）
  elements.fileSearch.value = 'big';
  listeners['search-input']();
  await timers[timers.length - 1].fn();
  await Promise.resolve(); await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const htmlB = fileTree.innerHTML;
  out.limitHit = htmlB.includes('searchResultCountLimited') && htmlB.includes('"n":500');
  out.bigRequests = globCalls.filter((c) => c.includes('*big*'));
  out.bigRows = htmlB.split('file-item-row').length - 1;
  // C: 新输入取消进行中队列（旧流结果不渲染）
  elements.fileSearch.value = 'cfg';
  listeners['search-input']();
  const cancelTimer = timers[timers.length - 1];
  cancelTimer.fn(); // start stream without awaiting
  elements.fileSearch.value = 'xy';
  listeners['search-input']();
  await timers[timers.length - 1].fn();
  await Promise.resolve(); await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const htmlC = fileTree.innerHTML;
  out.cancelledHasXy = htmlC.includes('data-path="src/deep/xy.txt"');
  out.cancelledNoCfg = !htmlC.includes('data-path="src/deep/x.json"') && !htmlC.includes('data-path="src/a.js"');
  // D: 目录粒度缓存（3s TTL 内同 dir|pattern 不再发请求）
  const xyBefore = globCalls.filter((c) => c.includes('*xy*')).length;
  elements.fileSearch.value = 'xy';
  listeners['search-input']();
  await timers[timers.length - 1].fn();
  await Promise.resolve(); await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const xyAfter = globCalls.filter((c) => c.includes('*xy*')).length;
  out.cacheHit = xyAfter === xyBefore && xyAfter === 3;
  // E: 服务端回退检测（子树无匹配时 glob_files 回扫项目根，前端停止队列）
  const fallbackBefore = globCalls.filter((c) => c.includes('*fallback*')).length;
  elements.fileSearch.value = 'fallback';
  listeners['search-input']();
  await timers[timers.length - 1].fn();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const htmlE = fileTree.innerHTML;
  out.fallbackRequests = globCalls.filter((c) => c.includes('*fallback*')).length - fallbackBefore;
  out.fallbackStopped = !htmlE.includes('search-status-line');
  out.fallbackHasOutside = htmlE.includes('data-path="outside/x.txt"');
  out.fallbackMergedLocal = htmlE.includes('data-path="src/deep/x.json"');
  // F: 单层场景（当前目录=项目根）进度文案区分（用新词避开缓存）
  state.currentDir = '';
  elements.fileSearch.value = 'cfg2';
  listeners['search-input']();
  await timers[timers.length - 1].fn();
  await new Promise((resolve) => setTimeout(resolve, 0));
  out.singleLevelText = snapshots.some((s) => s.includes('searchProgressSingle'));
  // G: 空态（无结果）保持「无匹配文件」，不显示总数行
  state.currentDir = 'src/deep';
  elements.fileSearch.value = 'empty';
  listeners['search-input']();
  await timers[timers.length - 1].fn();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const htmlG = fileTree.innerHTML;
  out.emptyState = htmlG.includes('noMatchingFiles') && !htmlG.includes('searchResultCount');
  process.stdout.write(JSON.stringify(out));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["order"], [
            "glob:C:/demo/src/deep:*cfg*",
            "glob:C:/demo/src:*cfg*",
            "glob:C:/demo:*cfg*",
        ])
        self.assertEqual(data["dedupeCount"], 1)
        self.assertTrue(data["hasAjs"])
        self.assertTrue(data["hasConfigDir"])
        self.assertTrue(data["progressShown"])
        self.assertTrue(data["progressHasY3"])
        self.assertIn(1, data["progressLevels"])
        self.assertIn(2, data["progressLevels"])
        self.assertTrue(data["singleLevelText"])
        self.assertTrue(data["noProgressWhenDone"])
        self.assertTrue(data["countLine"])
        self.assertTrue(data["limitHit"])
        self.assertEqual(data["bigRequests"], ["glob:C:/demo/src/deep:*big*"])
        self.assertEqual(data["bigRows"], 500)
        self.assertTrue(data["cancelledHasXy"])
        self.assertTrue(data["cancelledNoCfg"])
        self.assertTrue(data["cacheHit"])
        self.assertTrue(data["emptyState"])
        self.assertEqual(data["fallbackRequests"], 1)
        self.assertTrue(data["fallbackStopped"])
        self.assertTrue(data["fallbackHasOutside"])
        self.assertTrue(data["fallbackMergedLocal"])
    def test_file_tree_search_field_keydown_handlers(self):
        self.assertIn('handleSearchFieldKeydown', FILES_SOURCE)
        self.assertIn('clearSearchAndRestore', FILES_SOURCE)
        script = r"""
global.window = {Code: {features: {}}, setTimeout, clearTimeout};
require('./src/features/files.js');
const {createFilesFeature} = window.Code.features.files;
const listeners = {};
const fileCalls = [];
const buttons = [];
let firstQuery = null;
const fileTree = {
  innerHTML: '',
  scrollTop: 0,
  classList: {toggle() {}},
  addEventListener: (name, fn) => { listeners[name] = fn; },
  querySelectorAll: () => buttons,
  querySelector: () => firstQuery,
  insertAdjacentHTML: () => {},
};
const state = {
  currentDir: 'src',
  _fileRoot: 'C:/demo',
  _fileItems: [{name: 'a.js', path: 'src/a.js', type: 'file'}],
  previewPath: '',
};
const elements = {
  fileTree,
  projectRoot: {value: 'C:/demo'},
  fileSearch: {value: '', addEventListener: (name, fn) => { listeners['search-' + name] = fn; }},
  filePathBar: {style: {}, innerHTML: '', querySelectorAll: () => [], scrollWidth: 0, clientWidth: 100},
  cwdPathText: {textContent: ''},
  goUp: {disabled: false, addEventListener: () => {}},
  newFolderBtn: {disabled: false, addEventListener: () => {}},
  refreshFiles: {disabled: false, addEventListener: () => {}},
  fileSortBtn: {addEventListener: () => {}},
};
const timers = [];
const documentRoot = {
  body: {appendChild: () => {}},
  getElementById: () => ({textContent: '', addEventListener: () => {}}),
  addEventListener: () => {},
  querySelector: () => null,
  activeElement: null,
};
const feature = createFilesFeature({
  state,
  elements,
  t: (key) => key,
  escapeHtml: (value) => String(value),
  openFile: () => {},
  apiJson: async (url, options) => {
    if (url === '/api/tools/glob_files') {
      const body = JSON.parse(options.body);
      fileCalls.push('glob:' + body.path);
      return {ok: true, results: [{path: 'src/zz.json', type: 'file'}]};
    }
    fileCalls.push('files:' + url);
    return {root: 'C:/demo', path: 'src', items: state._fileItems};
  },
  setTimeout: (fn, ms) => { timers.push({fn, ms}); return timers.length; },
  clearTimeout: () => {},
  storage: {getItem: () => null, setItem: () => {}},
  documentRoot,
});
(async () => {
  feature.bind();
  feature.loadFiles();
  await Promise.resolve(); await Promise.resolve();
  const out = {};
  let preventDefaulted = false;
  // 1) 搜索框焦点 Esc：清空搜索词并恢复列表
  elements.fileSearch.value = 'cfg';
  listeners['search-keydown']({key: 'Escape', preventDefault: () => { preventDefaulted = true; }});
  out.escCleared = elements.fileSearch.value === '';
  out.escPrevented = preventDefaulted;
  // 2) 搜索框焦点 Alt+↑：上一级目录（loadFiles 请求父路径）
  preventDefaulted = false;
  listeners['search-keydown']({altKey: true, key: 'ArrowUp', preventDefault: () => { preventDefaulted = true; }});
  await Promise.resolve(); await Promise.resolve();
  out.goUpRequested = fileCalls.some((c) => c === 'files:/api/files?path=');
  out.goUpPrevented = preventDefaulted;
  // 3) 搜索框焦点 Backspace：不拦截（不 preventDefault、不上级）
  const callsBefore = fileCalls.length;
  preventDefaulted = false;
  listeners['search-keydown']({key: 'Backspace', preventDefault: () => { preventDefaulted = true; }});
  out.backspaceNotPrevented = !preventDefaulted;
  out.backspaceNoGoUp = fileCalls.length === callsBefore;
  // 4) 搜索进行中按 Esc：取消 in-flight 流，旧响应不覆盖列表
  elements.fileSearch.value = 'cfg';
  listeners['search-input']();
  const cancelTimer = timers[timers.length - 1];
  cancelTimer.fn(); // start stream without awaiting
  elements.fileSearch.value = 'cfg';
  listeners['search-keydown']({key: 'Escape', preventDefault: () => {}});
  await new Promise((resolve) => setTimeout(resolve, 0));
  const html = fileTree.innerHTML;
  out.escCancelledStream = !html.includes('src/zz.json') && !html.includes('searchProgress');
  // 5) 进入目录（loadFiles）后自动聚焦列表首项（roving tabindex + aria-selected）
  const focusLog = [];
  const btnFirst = {dataset: {path: 'src/a.js', type: 'file'}, setAttribute: (n, v) => { btnFirst.aria = btnFirst.aria || {}; btnFirst.aria[n] = v; }, classList: {toggle: () => {}}, addEventListener: () => {}, focus: () => { focusLog.push('focus-first'); }};
  firstQuery = btnFirst;
  buttons.length = 0; buttons.push(btnFirst);
  await feature.loadFiles();
  await Promise.resolve(); await Promise.resolve();
  out.autoFocus = focusLog.includes('focus-first') && btnFirst.aria && btnFirst.aria['aria-selected'] === 'true';
  // 6) 搜索框 Ctrl+↑ 备用上一级（与 Alt+↑ 并存）
  const goUpCalls = () => fileCalls.filter((c) => c === 'files:/api/files?path=').length;
  const before6 = goUpCalls();
  preventDefaulted = false;
  listeners['search-keydown']({ctrlKey: true, key: 'ArrowUp', preventDefault: () => { preventDefaulted = true; }});
  await Promise.resolve(); await Promise.resolve();
  out.ctrlGoUp = preventDefaulted && goUpCalls() === before6 + 1;
  // 7) 列表焦点 Ctrl+↑ 备用上一级（Backspace 语义保持）
  const before7 = goUpCalls();
  preventDefaulted = false;
  listeners['keydown']({ctrlKey: true, key: 'ArrowUp', preventDefault: () => { preventDefaulted = true; }});
  await Promise.resolve(); await Promise.resolve();
  out.listCtrlGoUp = preventDefaulted && goUpCalls() === before7 + 1;
  process.stdout.write(JSON.stringify(out));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["escCleared"])
        self.assertTrue(data["escPrevented"])
        self.assertTrue(data["goUpRequested"])
        self.assertTrue(data["goUpPrevented"])
        self.assertTrue(data["backspaceNotPrevented"])
        self.assertTrue(data["backspaceNoGoUp"])
        self.assertTrue(data["escCancelledStream"])
        self.assertTrue(data["autoFocus"])
        self.assertTrue(data["ctrlGoUp"])
        self.assertTrue(data["listCtrlGoUp"])



    def test_answer_render_path_alias_bare_url_and_image_preview(self):
        # 执行级：pathAlias 规则 + 裸 URL 域名别名（marked 用最小 mock）
        script = r"""
global.window = {Code: {ui: {}}, katex: undefined};
require('./src/core/namespace.js');
require('./src/ui/markdown.js');
require('./src/features/link-context-menu.js');
const md = window.Code.ui.markdown;
const out = {};
out.relStays = md.pathAlias('src/a.js', 'C:/demo');
out.insideRoot = md.pathAlias('C:\\demo\\src\\deep\\b.ts', 'C:\\demo');
out.insideRootSlash = md.pathAlias('C:/demo/x.png', 'C:/demo');
out.outsideRoot = md.pathAlias('C:\\Users\\Admin\\Desktop\\photo.jpg', 'C:\\demo');
out.unixAbs = md.pathAlias('/Users/me/a.txt', 'C:/demo');
out.empty = md.pathAlias('', 'C:/demo');
out.absDrive = md.isAbsolutePath('C:/Users/a.txt');
out.absFwd = md.isAbsolutePath('/C:/Users/a.txt');
out.absUnc = md.isAbsolutePath('//server/share/a.txt');
out.absPosix = md.isAbsolutePath('/Users/me/a.txt');
out.notAbs = md.isAbsolutePath('src/a.js');
out.aliasFwdDrive = md.pathAlias('/C:/demo/src/a.js', 'C:/demo');
out.aliasFwdOutside = md.pathAlias('/C:/Users/x/photo.jpg', 'C:/demo');
out.aliasUncOutside = md.pathAlias('//server/share/x.png', 'C:/demo');
out.refParenLine = md.parseLineRef('run.go (line 91)');
out.refParen = md.parseLineRef('run.go(91)');
out.refFullParen = md.parseLineRef('run.go（91）');
out.refColon = md.parseLineRef('server.py:123');
out.refColonSlash = md.parseLineRef('a/b/c.txt:12');
out.refNone = md.parseLineRef('src/a.js');
out.refNotPath = md.parseLineRef('time:10');
out.refBad = md.parseLineRef('x(abc)');
out.clsImage = md.classifyLocalPath('a.png');
out.clsDerived = md.classifyLocalPath('x.tif');
out.clsText = md.classifyLocalPath('server.py');
out.clsTextMd = md.classifyLocalPath('doc.md');
out.clsBinaryZip = md.classifyLocalPath('a.zip');
out.clsBinaryPdf = md.classifyLocalPath('b.pdf');
out.clsBinaryExe = md.classifyLocalPath('c.exe');
out.clsBinaryMedia = md.classifyLocalPath('d.mp4');
out.clsUnknown = md.classifyLocalPath('noext');
out.candDeepseek = md.faviconHostCandidates('chat.deepseek.com').join(',');
out.candAliyun = md.faviconHostCandidates('chat.aliyun.com').join(',');
out.candDoubao = md.faviconHostCandidates('www.doubao.com').join(',');
out.candWww = md.faviconHostCandidates('www.github.com').join(',');
out.candCompound = md.faviconHostCandidates('b.baidu.com.cn').join(',');
out.candMulti = md.faviconHostCandidates('a.b.deepseek.com').join(',');
out.candBare = md.faviconHostCandidates('deepseek.com').join(',');
out.candEmpty = md.faviconHostCandidates('').length;



out.isImg = md.isImagePath('a.PNG');
out.isImgJpeg = md.isImagePath('x.jpeg');
out.notImg = md.isImagePath('a.txt');
out.notImgNoExt = md.isImagePath('src/deep');
// marked 最小 mock：解析常用语法走各 renderer
const holder = {};
const markedMock = {
  Renderer: function () {},
  setOptions: (opts) => { holder.renderer = opts.renderer; },
  parse: (src) => {
    const r = holder.renderer;
    let out = String(src);
    out = out.replace(/^(#{1,6})\s+(.+)$/gm, (m, hashes, text) =>
      r.heading({ depth: hashes.length, text, tokens: [{ type: 'text', text }] }));
    out = out.replace(/^>\s*\[!(\w+)\]\s*\n((?:^>.*\n?)*)/gm, (m, type, rest) => {
      const bodyText = rest.replace(/^>\s?/gm, '').trim();
      const bodyTokens = [{ type: 'paragraph', text: bodyText, tokens: [{ type: 'text', text: bodyText }] }];
      return r.blockquote({ text: '[!' + type + ']', tokens: [{ type: 'paragraph', text: '[!' + type + ']' }, ...bodyTokens] });
    });
    out = out.replace(/^>(.*)(?:\n|$)/gm, (m, content) => r.blockquote({ text: content.trim(), tokens: [{ type: 'paragraph', text: content.trim(), tokens: [{ type: 'text', text: content.trim() }] }] }));
    out = out.replace(/^\|(.+)\|\n\|[-| :]+\|\n((?:\|.+\|\n?)*)$/gm, (m, headerRow, bodyRows) => {
      const cells = (row) => { const parts = row.split('|').map((c) => c.trim()); if (parts[0] === '') parts.shift(); if (parts.length && parts[parts.length - 1] === '') parts.pop(); return parts.map((c) => ({ tokens: [{ type: 'text', text: c }] })); };
      return r.table({ header: cells(headerRow), rows: bodyRows.trim().split('\n').map(cells) });
    });
    out = out.replace(/```(\w*)\n([\s\S]*?)```/g, (m, lang, text) => r.code({ text, lang }));
    out = out.replace(/`([^`]+)`/g, (m, text) => r.codespan({ text }));
    out = out.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (m, alt, href) => r.image({ href, text: alt, title: null }));
    out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, text, hrefAndTitle) => {
      const tm = hrefAndTitle.match(/^(\S+)\s+["'](.+?)["']$/);
      return r.link({ href: tm ? tm[1] : hrefAndTitle, text, tokens: [{ type: 'text', text }], title: tm ? tm[2] : null });
    });
    return out;
  },
};
const feature = md.createMarkdownFeature({ marked: markedMock, escapeHtml: (v) => String(v), random: () => 'x' });
const bare = feature.renderMarkdownLite('[https://wallhaven.cc/x](https://wallhaven.cc/x)');
out.bareLink = bare.includes('>wallhaven.cc<') && bare.includes('href="https://wallhaven.cc/x"');
out.bareNoNativeTitle = !bare.includes('title="https://wallhaven.cc/x"');
const titled = feature.renderMarkdownLite('[site](https://example.com/a "作者标题")');
out.explicitTitleKept = titled.includes('title="作者标题"');
out.bareExt = bare.includes('class="ext-link"') && bare.includes('link-ext-icon') && bare.includes('data-favicon') && !bare.includes('↗');
const labeled = feature.renderMarkdownLite('[wallhaven 主页](https://wallhaven.cc/x)');
out.labeledStays = labeled.includes('>wallhaven 主页<');
const rel = feature.renderMarkdownLite('[src/a.js](src/a.js)');
out.relLinkTextStays = rel.includes('>src/a.js<');
// 1-7 格式化点
const admonition = feature.renderMarkdownLite('> [!WARNING]\n> 内容很重要');
out.admonitionWarning = admonition.includes('admonition-warning') && admonition.includes('data-admonition="warning"') && admonition.includes('内容很重要');
const quote = feature.renderMarkdownLite('> 普通引用');
out.plainQuote = quote.includes('<blockquote>') && !quote.includes('admonition');
const table = feature.renderMarkdownLite('| 名称 | 值 |\n|---|---|\n| a | 1 |');
out.tableWrap = table.includes('table-wrap') && table.includes('<th>名称</th>') && table.includes('<td>1</td>');
const codeBlock = feature.renderMarkdownLite('```js\nconst x = 1;\n```');
out.langLabelJs = codeBlock.includes('lang-label') && codeBlock.includes('JavaScript');
const extLink = feature.renderMarkdownLite('[site](https://example.com/a)');
out.extIcon = extLink.includes('class="ext-link"') && extLink.includes('link-ext-icon') && extLink.includes('data-favicon') && !extLink.includes('↗') && extLink.includes('<svg');
out.glyphInline = extLink.includes('link-ext-icon" data-favicon="" aria-hidden="true"><svg');
out.extLeft = extLink.indexOf('link-ext-icon') < extLink.indexOf('>site<');
const heading = feature.renderMarkdownLite('## 我的标题');
out.headingAnchor = heading.includes('<h2 id="我的标题">');
const headingDup = feature.renderMarkdownLite('## A\n## A');
out.headingDup = headingDup.includes('id="a-2"');
const imgInline = feature.renderMarkdownLite('![alt](/api/file?path=x.png)');
out.imgSlot = imgInline.includes('msg-inline-img-slot') && imgInline.includes('data-img-src=') && imgInline.includes('data-message-image-preview');
const refHtml = feature.renderMarkdownLite('`server.py:123`');
const codeRef = feature.renderMarkdownLite('```js\n// see server.py:123\nconst x = 1;\n```');
out.refRendered = refHtml.includes('data-line="123"') && refHtml.includes('data-path="server.py"');
out.codeBlockRef = codeRef.includes('data-line="123"') && codeRef.includes('clickable-path code-ref');
// R009 菜单模块执行级
const lcm = window.Code.features.linkContextMenu;
const menuLog = [];
const fakeDoc = {
  querySelectorAll: () => [],
  createElement: () => ({ style: {}, innerHTML: '', querySelectorAll: () => [], addEventListener: () => {}, appendChild: () => {}, remove: () => {} }),
  body: { appendChild: () => {} },
  addEventListener: () => {},
  removeEventListener: () => {},
};
window.document = fakeDoc;
const menuT = (k) => ({ openInPreview: '打开', openDefaultApp: '用默认程序打开', revealInFolder: '在文件夹中显示', copyPath: '复制路径', copyFileName: '复制文件名', openInNewTab: '在新标签页打开', copyLink: '复制链接' })[k] || k;
const created = [];
fakeDoc.createElement = () => { const el = { style: {}, innerHTML: '', querySelectorAll: () => [], addEventListener: () => {}, appendChild: () => {}, remove: () => { created.push('removed'); } }; created.push(el); return el; };
const menuCalls = [];
lcm.showLinkContextMenu({
  x: 10, y: 10, kind: 'path',
  pathOptions: { kind: 'text', path: 'C:/p/a.py', filename: 'a.py', previewable: true },
  t: menuT, copyText: (v) => menuCalls.push('copy:' + v),
  callbacks: { open: () => menuCalls.push('open'), system: () => menuCalls.push('system'), reveal: () => menuCalls.push('reveal') },
});
const pathMenu = created[created.length - 1];
out.menuPathHtml = pathMenu.innerHTML.includes('a.py') && pathMenu.innerHTML.includes('data-action="open"') && pathMenu.innerHTML.includes('data-action="system"') && pathMenu.innerHTML.includes('data-action="reveal"') && pathMenu.innerHTML.includes('data-action="copy-path"') && pathMenu.innerHTML.includes('data-action="copy-name"');
created.length = 0; menuCalls.length = 0;
lcm.showLinkContextMenu({
  x: 10, y: 10, kind: 'path',
  pathOptions: { kind: 'binary', path: 'C:/p/b.zip', filename: 'b.zip', previewable: false },
  t: menuT, copyText: (v) => menuCalls.push('copy:' + v),
  callbacks: { open: () => menuCalls.push('open'), system: () => menuCalls.push('system'), reveal: () => menuCalls.push('reveal') },
});
const binMenu = created[created.length - 1];
out.menuBinaryHtml = binMenu.innerHTML.includes('data-action="system"') && binMenu.innerHTML.includes('data-action="copy-path"') && binMenu.innerHTML.includes('data-action="copy-name"') && !binMenu.innerHTML.includes('data-action="open"') && !binMenu.innerHTML.includes('data-action="reveal"');
created.length = 0; menuCalls.length = 0;
lcm.showLinkContextMenu({
  x: 10, y: 10, kind: 'link',
  linkOptions: { url: 'https://example.com/a' },
  t: menuT, copyText: (v) => menuCalls.push('copy:' + v),
  callbacks: { openTab: (u) => menuCalls.push('tab:' + u) },
});
const linkMenu = created[created.length - 1];
out.menuLinkHtml = linkMenu.innerHTML.includes('data-action="open-tab"') && linkMenu.innerHTML.includes('data-action="copy-link"');




process.stdout.write(JSON.stringify(out));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["relStays"], "src/a.js")
        self.assertEqual(data["insideRoot"], "src/deep/b.ts")
        self.assertEqual(data["insideRootSlash"], "x.png")
        self.assertEqual(data["outsideRoot"], "photo.jpg")
        self.assertEqual(data["unixAbs"], "a.txt")
        self.assertEqual(data["empty"], "")
        self.assertTrue(data["absDrive"])
        self.assertTrue(data["absFwd"])
        self.assertTrue(data["absUnc"])
        self.assertTrue(data["absPosix"])
        self.assertFalse(data["notAbs"])
        self.assertEqual(data["aliasFwdDrive"], "src/a.js")
        self.assertEqual(data["aliasFwdOutside"], "photo.jpg")
        self.assertEqual(data["aliasUncOutside"], "x.png")
        self.assertEqual(data["refParenLine"], {"path": "run.go", "line": 91})
        self.assertEqual(data["refParen"], {"path": "run.go", "line": 91})
        self.assertEqual(data["refFullParen"], {"path": "run.go", "line": 91})
        self.assertEqual(data["refColon"], {"path": "server.py", "line": 123})
        self.assertEqual(data["refColonSlash"], {"path": "a/b/c.txt", "line": 12})
        self.assertIsNone(data["refNone"])
        self.assertIsNone(data["refNotPath"])
        self.assertIsNone(data["refBad"])
        self.assertEqual(data["clsImage"], "image")
        self.assertEqual(data["clsDerived"], "derived")
        self.assertEqual(data["clsText"], "text")
        self.assertEqual(data["clsTextMd"], "text")
        self.assertEqual(data["clsBinaryZip"], "binary")
        self.assertEqual(data["clsBinaryPdf"], "binary")
        self.assertEqual(data["clsBinaryExe"], "binary")
        self.assertEqual(data["clsBinaryMedia"], "binary")
        self.assertEqual(data["clsUnknown"], "text")
        self.assertEqual(data["candDeepseek"], "chat.deepseek.com,deepseek.com")
        self.assertEqual(data["candAliyun"], "chat.aliyun.com,aliyun.com")
        self.assertEqual(data["candDoubao"], "www.doubao.com,doubao.com")
        self.assertEqual(data["candWww"], "www.github.com,github.com")
        self.assertEqual(data["candCompound"], "b.baidu.com.cn,baidu.com.cn")
        self.assertEqual(data["candMulti"], "a.b.deepseek.com,b.deepseek.com,deepseek.com")
        self.assertEqual(data["candBare"], "deepseek.com")
        self.assertEqual(data["candEmpty"], 0)
        # R016 源码级
        self.assertIn('faviconHostCandidates', MARKDOWN_SOURCE)
        self.assertIn('COMPOUND_SUFFIXES', MARKDOWN_SOURCE)
        self.assertIn('com.cn', MARKDOWN_SOURCE)

        # R008 源码级：矩阵路由
        self.assertIn('openReferencedPath', APP_SOURCE)
        self.assertIn('classifyLocalPath', APP_SOURCE)
        self.assertIn('kind === "binary"', APP_SOURCE)
        self.assertIn('/api/open-file', APP_SOURCE)
        self.assertIn('350000', PREVIEW_SOURCE)
        self.assertIn('8000', PREVIEW_SOURCE)

        self.assertTrue(data["refRendered"])
        self.assertTrue(data["codeBlockRef"])
        self.assertTrue(data["menuPathHtml"])
        self.assertTrue(data["menuBinaryHtml"])
        self.assertTrue(data["menuLinkHtml"])
        # R009 源码级
        self.assertIn('bindLinkContextMenus', APP_SOURCE)
        self.assertIn('link-context-menu.js', FRONTEND_ENTRY_SOURCE)
        self.assertIn('showLinkContextMenu', LINK_MENU_SOURCE) if 'LINK_MENU_SOURCE' in dir() else None
        self.assertIn('openInNewTab', I18N_SOURCE)
        self.assertIn('copyFileName', I18N_SOURCE)

        # R005/R007 源码级
        self.assertIn('scrollPreviewToLine', PREVIEW_SOURCE)
        self.assertIn('options.line', PREVIEW_SOURCE)
        self.assertIn('parseLineRef', MARKDOWN_SOURCE)
        self.assertIn('loadFile(fp, undefined, line && line > 0 ? { line } : {})', APP_SOURCE)
        self.assertIn('sb-path-tooltip', STYLE_SOURCE)

        self.assertTrue(data["isImg"])
        self.assertTrue(data["isImgJpeg"])
        self.assertFalse(data["notImg"])
        self.assertFalse(data["notImgNoExt"])
        self.assertTrue(data["bareLink"])
        self.assertTrue(data["bareNoNativeTitle"])
        self.assertTrue(data["explicitTitleKept"])
        # R015 源码级
        self.assertNotIn('if (!token.title) title = ` title="', MARKDOWN_SOURCE)
        self.assertIn('custom sb-path-tooltip', MARKDOWN_SOURCE)

        self.assertTrue(data["bareExt"])
        self.assertTrue(data["labeledStays"])
        self.assertTrue(data["relLinkTextStays"])
        self.assertTrue(data["admonitionWarning"])
        self.assertTrue(data["plainQuote"])
        self.assertTrue(data["tableWrap"])
        self.assertTrue(data["langLabelJs"])
        self.assertTrue(data["extIcon"])
        self.assertTrue(data["extLeft"])
        self.assertTrue(data["glyphInline"])
        # R014 / CODE-036 phase 2: only the same-origin proxy reaches favicon sources.
        self.assertIn('/api/favicon?scheme=${encodeURIComponent(scheme)}&host=${encodeURIComponent(host)}', APP_SOURCE)
        self.assertNotIn('icons.duckduckgo.com/ip3/', APP_SOURCE)
        self.assertNotIn('www.google.com/s2/favicons', APP_SOURCE)
        self.assertNotIn('api.faviconkit.com/', APP_SOURCE)
        self.assertIn('naturalWidth <= 1', APP_SOURCE)

        self.assertIn('_faviconCache', APP_SOURCE)
        self.assertIn('{ failed: true }', APP_SOURCE)
        self.assertNotIn('slot.hidden = true', APP_SOURCE)
        self.assertIn('width:20px;height:20px', STYLE_SOURCE)
        self.assertIn('width:16px;height:16px;border-radius:5px', STYLE_SOURCE)
        self.assertIn('sb-favicon-in', STYLE_SOURCE)
        self.assertIn('#fff 88%', STYLE_SOURCE)
        self.assertNotIn('filter:brightness', STYLE_SOURCE)

        # R010 源码级：favicon 左置 / 无箭头残留 / 防编造 / 主题 / 阴影
        self.assertIn('</span>${inner}</a>', MARKDOWN_SOURCE)
        self.assertNotIn('↗', MARKDOWN_SOURCE)
        self.assertIn('禁止编造不存在的路径', APP_SOURCE)
        self.assertIn('html[data-theme-mode="dark"]', STYLE_SOURCE)
        self.assertIn('html[data-theme-mode="light"]', STYLE_SOURCE)
        self.assertIn('#fff 88%', STYLE_SOURCE)
        self.assertIn('border-radius:4px', STYLE_SOURCE)
        self.assertIn('border:1px solid var(--line)', STYLE_SOURCE)
        self.assertNotIn('.ext-favicon{filter:', STYLE_SOURCE)
        self.assertNotIn('brightness(1.25)', STYLE_SOURCE)
        self.assertNotIn('background:color-mix(in srgb,var(--panel-3)', STYLE_SOURCE)

        self.assertNotIn('prefers-color-scheme', STYLE_SOURCE)
        self.assertIn('#fff 88%', STYLE_SOURCE)
        self.assertIn('FILE_ICON_SVG', APP_SOURCE)
        self.assertIn('classifyLocalPath?.(p)', APP_SOURCE)
        self.assertIn('icon.innerHTML = FILE_ICON_SVG', APP_SOURCE)
        self.assertNotIn('icon.textContent = "📄"', APP_SOURCE)
        self.assertIn('--muted', STYLE_SOURCE)

        self.assertIn('box-shadow:0 1px 4px rgba(0,0,0,.12)', STYLE_SOURCE)
        self.assertIn('data-loaded', APP_SOURCE)
        self.assertIn('[data-loaded]{background:none;min-width:0;min-height:0;animation:none}', STYLE_SOURCE)


        self.assertTrue(data["headingAnchor"])
        self.assertTrue(data["headingDup"])
        self.assertTrue(data["imgSlot"])
        # 源码级：1-7 在 markdown.js / app.js / styles / i18n
        self.assertIn('data-admonition="', MARKDOWN_SOURCE)
        self.assertIn('admonition-title', MARKDOWN_SOURCE)
        self.assertIn('table-wrap', MARKDOWN_SOURCE)
        self.assertIn('langLabel(lang)', MARKDOWN_SOURCE)
        self.assertIn('link-ext-icon', MARKDOWN_SOURCE)
        self.assertIn('data-favicon', MARKDOWN_SOURCE)
        self.assertNotIn('↗', MARKDOWN_SOURCE)
        self.assertIn('bindExtLinkFavicons', APP_SOURCE)
        self.assertIn('/api/favicon?', APP_SOURCE)
        self.assertIn('.ext-favicon', STYLE_SOURCE)

        self.assertIn('slugify(token.text)', MARKDOWN_SOURCE)
        self.assertIn('msg-inline-img-slot', MARKDOWN_SOURCE)
        self.assertIn('bindAdmonitions', APP_SOURCE)
        self.assertIn('bindMessageImages', APP_SOURCE)
        self.assertIn('msg-img-fallback', APP_SOURCE)
        self.assertIn('path-file-card', APP_SOURCE)
        self.assertIn('isOutOfRootPath', APP_SOURCE)
        self.assertIn('copyFailed', I18N_SOURCE)
        self.assertIn('admonitionWarning: "警告"', I18N_SOURCE)
        self.assertIn('admonitionCaution: "Caution"', I18N_SOURCE)
        self.assertIn('.admonition-warning', STYLE_SOURCE)
        self.assertIn('.table-wrap', STYLE_SOURCE)
        self.assertIn('sb-img-shimmer', STYLE_SOURCE)
        self.assertIn('## 回答格式', APP_SOURCE)
        self.assertIn('提及文件或图片路径时用行内代码包裹', APP_SOURCE)
        self.assertIn('[!NOTE]/[!TIP]/[!IMPORTANT]/[!WARNING]/[!CAUTION]', APP_SOURCE)
        self.assertIn('标准 Markdown。', APP_SOURCE)


        # 源码级：app.js 别名/预览绑定 + markdown 域名逻辑
        self.assertIn("markdownApi.pathAlias(p, projectRoot)", APP_SOURCE)
        self.assertIn("maybeRenderFileCard(el, p, projectRoot)", APP_SOURCE)
        self.assertIn("return; // out of root", APP_SOURCE)
        self.assertIn("path-image-card", APP_SOURCE)
        self.assertIn("path-image-thumb", APP_SOURCE)
        self.assertIn("probe.onerror = () => { /* degrade: keep the text alias */ }", APP_SOURCE)
        self.assertIn("pathAlias,", MARKDOWN_SOURCE)
        self.assertIn("isImagePath,", MARKDOWN_SOURCE)

    def test_external_favicon_binding_uses_same_origin_and_keeps_glyph_on_failure(self):
        start = APP_SOURCE.index("const _faviconCache = new Map();")
        end = APP_SOURCE.index("// Right-click menus for links in final answers", start)
        source = APP_SOURCE[start:end] + "\nglobalThis.__bindFavicons = bindExtLinkFavicons;"
        script = f"""
const vm = require("vm");
const source = {json.dumps(source)};
const created = [];
let activeSlots = [];
function slotFor(href) {{
  return {{
    dataset: {{}},
    children: [{{kind: "glyph"}}],
    closest(selector) {{
      if (selector !== "a.ext-link") throw new Error("unexpected selector");
      return {{getAttribute(name) {{ return name === "href" ? href : null; }}}};
    }},
    replaceChildren(node) {{ this.children = [node]; }},
  }};
}}
const document = {{
  querySelectorAll(selector) {{
    if (selector !== "a.ext-link .link-ext-icon") throw new Error("unexpected query");
    return activeSlots;
  }},
  createElement(tag) {{
    if (tag !== "img") throw new Error("unexpected element");
    const handlers = {{}};
    const image = {{
      naturalWidth: 16,
      naturalHeight: 16,
      addEventListener(type, handler) {{ handlers[type] = handler; }},
      get handlers() {{ return handlers; }},
      set src(value) {{ this._src = String(value); created.push(this); }},
      get src() {{ return this._src; }},
    }};
    return image;
  }},
}};
const sandbox = {{document, URL, encodeURIComponent, window: {{Code: {{ui: {{}}}}}}}};
vm.runInNewContext(source, sandbox);

const successSlot = slotFor("https://例子.测试/path?q=1");
activeSlots = [successSlot];
sandbox.__bindFavicons();
const successImage = created.at(-1);
successImage.handlers.load();

const failureSlot = slotFor("http://missing.example/path");
activeSlots = [failureSlot];
sandbox.__bindFavicons();
const failureImage = created.at(-1);
failureImage.handlers.error();
const createdBeforeNegativeCache = created.length;
const repeatedFailureSlot = slotFor("http://missing.example/other");
activeSlots = [repeatedFailureSlot];
sandbox.__bindFavicons();

process.stdout.write(JSON.stringify({{
  successSrc: successImage.src,
  successReplaced: successSlot.children[0] === successImage,
  failureKeptGlyph: failureSlot.children[0].kind === "glyph",
  negativeCacheSkipped: created.length === createdBeforeNegativeCache,
  repeatedFailureKeptGlyph: repeatedFailureSlot.children[0].kind === "glyph",
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(
            data["successSrc"],
            "/api/favicon?scheme=https&host=xn--fsqu00a.xn--0zwm56d",
        )
        self.assertTrue(data["successReplaced"])
        self.assertTrue(data["failureKeptGlyph"])
        self.assertTrue(data["negativeCacheSkipped"])
        self.assertTrue(data["repeatedFailureKeptGlyph"])

    def test_image_overlay_gallery_model_and_app_integration(self):
        # 执行级：纯导航模型（首尾禁用策略、索引、空数组/越界降级）
        script = r"""
global.window = {Code: {features: {}}};
require('./src/features/image-overlay.js');
const {createImageOverlayModel, normalizeSources} = window.Code.features.imageOverlay;
const out = {};
const m = createImageOverlayModel(['a.png', 'b.png', 'c.png'], 0);
out.count = m.count;
out.startCurrent = m.current();
out.canPrevStart = m.canPrev();
out.next1 = m.next();
out.indexAfterNext = m.index;
out.next2 = m.next();
out.canNextEnd = m.canNext();
out.nextAtEnd = m.next();
out.currentAtEnd = m.current();
out.prev = m.prev();
out.clampedStart = createImageOverlayModel(['x', 'y'], 99).index;
out.negStart = createImageOverlayModel(['x', 'y'], -3).index;
out.emptyCount = createImageOverlayModel([], 0).count;
out.emptyCurrent = createImageOverlayModel([], 0).current();
out.singleCount = createImageOverlayModel(['only.png'], 0).count;
out.filtered = normalizeSources(['a', '', null, 'b', 0]).length;
process.stdout.write(JSON.stringify(out));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["startCurrent"], "a.png")
        self.assertFalse(data["canPrevStart"])
        self.assertEqual(data["next1"], "b.png")
        self.assertEqual(data["indexAfterNext"], 1)
        self.assertEqual(data["next2"], "c.png")
        self.assertFalse(data["canNextEnd"])
        self.assertEqual(data["nextAtEnd"], "c.png")
        self.assertEqual(data["currentAtEnd"], "c.png")
        self.assertEqual(data["prev"], "b.png")
        self.assertEqual(data["clampedStart"], 1)
        self.assertEqual(data["negStart"], 0)
        self.assertEqual(data["emptyCount"], 0)
        self.assertEqual(data["emptyCurrent"], "")
        self.assertEqual(data["singleCount"], 1)
        self.assertEqual(data["filtered"], 2)
        # 源码级：app.js 多图渲染与键盘/点击绑定
        self.assertIn("overlay-prev", APP_SOURCE)
        self.assertIn("overlay-next", APP_SOURCE)
        self.assertIn("overlay-index", APP_SOURCE)
        self.assertIn('event.key === "ArrowLeft"', APP_SOURCE)
        self.assertIn('event.key === "ArrowRight"', APP_SOURCE)
        self.assertIn("createModel(options?.sources, options?.index)", APP_SOURCE)
        self.assertIn("data-composer-image-preview data-index=", APP_SOURCE)
        self.assertIn("state.attachedImages.map((img) => imagePreviewSource(img)).filter(Boolean)", APP_SOURCE)
        self.assertIn("parseInt(image.dataset.index, 10)", APP_SOURCE)
        self.assertIn("prevImage", I18N_SOURCE)
        self.assertIn("nextImage", I18N_SOURCE)
        self.assertIn('imagePreviewTitle: "查看原图"', I18N_SOURCE)
        self.assertIn('imagePreviewTitle: "View original"', I18N_SOURCE)
        self.assertIn('t("imagePreviewTitle")', APP_SOURCE)
        self.assertNotIn('title="Image preview"', APP_SOURCE)
        self.assertIn("overlay-nav-btn", STYLE_SOURCE)

    def test_image_attachment_mime_facts_cover_input_matrix(self):
        script = r"""
global.window = {};
require("./src/core/namespace.js");
require("./src/features/image-attachments.js");
const images = window.Code.features.imageAttachments;
const bytes = {
  png: [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a],
  jpeg: [0xff, 0xd8, 0xff],
  webp: [...Buffer.from("RIFF"), 0, 0, 0, 0, ...Buffer.from("WEBP")],
  gif: [...Buffer.from("GIF89a")],
  bmp: [0x42, 0x4d],
  ico: [0x00, 0x00, 0x01, 0x00],
  tiffLe: [0x49, 0x49, 0x2a, 0x00],
  tiffBe: [0x4d, 0x4d, 0x00, 0x2a],
};
process.stdout.write(JSON.stringify({
  sniffed: Object.fromEntries(Object.entries(bytes).map(([key, value]) => [
    key,
    images.sniffImageMime(Uint8Array.from(value)),
  ])),
  aliases: [
    images.normalizeImageMime("image/jpg"),
    images.normalizeImageMime("image/vnd.microsoft.icon"),
    images.normalizeImageMime("image/x-tiff"),
  ],
  fileFacts: [
    images.imageMimeForFile({name: "wrong.ico", type: "image/x-icon"}, Uint8Array.from(bytes.png)),
    images.imageMimeForFile({name: "photo.tiff", type: ""}),
    images.isImageFileCandidate({name: "photo.tiff", type: ""}),
    images.isImageFileCandidate({name: "notes.txt", type: "text/plain"}),
  ],
  outputs: ["image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp", "image/x-icon", "image/tiff"]
    .map((mime) => images.modelImageOutputMime(mime)),
  deferred: ["image/png", "image/gif", "image/tiff", "image/svg+xml"]
    .map((mime) => images.canDeferImageConversion(mime)),
  parsed: images.parseImageDataUrl("data:image/png;base64,QUJD"),
  rejectedDataUrl: images.parseImageDataUrl("data:image/png,not-base64"),
  storageNames: [
    images.storageNameForImage("code-icon.ico", "image/png"),
    images.storageNameForImage("photo.jpeg", "image/jpeg"),
    images.storageNameForImage("capture", "image/webp"),
  ],
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["sniffed"], {
            "png": "image/png",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
            "gif": "image/gif",
            "bmp": "image/bmp",
            "ico": "image/x-icon",
            "tiffLe": "image/tiff",
            "tiffBe": "image/tiff",
        })
        self.assertEqual(data["aliases"], ["image/jpeg", "image/x-icon", "image/tiff"])
        self.assertEqual(data["fileFacts"], ["image/png", "image/tiff", True, False])
        self.assertEqual(data["outputs"], [
            "image/png", "image/jpeg", "image/webp",
            "image/png", "image/png", "image/png", "image/png",
        ])
        self.assertEqual(data["deferred"], [True, True, True, False])
        self.assertEqual(data["parsed"], {"mime": "image/png", "base64": "QUJD"})
        self.assertIsNone(data["rejectedDataUrl"])
        self.assertEqual(data["storageNames"], ["code-icon.png", "photo.jpeg", "capture.webp"])

    def test_composer_image_pipeline_uses_actual_encoding_and_waits_before_send(self):
        compression = APP_SOURCE[
            APP_SOURCE.index("async function compressImage("):
            APP_SOURCE.index("async function handleImagePaste(")
        ]
        self.assertIn("const sourceMime = imageMimeForFile(file, bytes)", compression)
        self.assertIn("canvas.toDataURL(modelImageOutputMime(sourceMime), quality)", compression)
        self.assertIn("const encoded = parseImageDataUrl(", compression)
        self.assertIn("img.onerror = () => finishWithOriginal()", compression)
        self.assertIn("setTimeout(() => finishWithOriginal(), IMAGE_DECODE_TIMEOUT_MS)", compression)
        self.assertNotIn('file.type === "image/png" ? "image/jpeg" : file.type', compression)
        self.assertIn("addImage(displayName, image.base64, image.mime", compression)
        self.assertIn("name: img.storageName || img.name || \"image.png\"", APP_SOURCE)
        self.assertIn("await handleImageFile(imageFileFromBytes(bytes, name, mime)", APP_SOURCE)

        submit = APP_SOURCE[
            APP_SOURCE.index('els.chatForm.addEventListener("submit"'):
            APP_SOURCE.index("els.newChat.addEventListener", APP_SOURCE.index('els.chatForm.addEventListener("submit"'))
        ]
        self.assertLess(
            submit.index("await waitForPendingImageAttachments()"),
            submit.index("const hasImages = state.attachedImages.length > 0"),
        )
        self.assertLess(
            submit.index("await resolveAtImages()"),
            submit.index("const hasImages = state.attachedImages.length > 0"),
        )
        for key in (
            "imageAttachmentTooLarge",
            "imageAttachmentUnsupported",
            "imageAttachmentFailed",
        ):
            self.assertEqual(I18N_SOURCE.count(f"{key}:"), 2)

    def test_tiff_browser_preview_is_derived_without_entering_persistence(self):
        script = r"""
global.window = {
  fetch: null,
  URL: {},
};
require("./src/core/namespace.js");
require("./src/features/image-attachments.js");
const images = window.Code.features.imageAttachments;
const calls = [];
const fetchImpl = async (url, options) => {
  calls.push({url, options});
  return {
    ok: true,
    blob: async () => new Blob([Buffer.from("png-preview")], {type: "image/png"}),
  };
};
const urlApi = {createObjectURL: (blob) => `blob:tiff-${blob.size}`};
const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((onResolve, onReject) => {
    resolve = onResolve;
    reject = onReject;
  });
  return {promise, reject, resolve};
};
(async () => {
  const previewUrl = await images.requestDerivedBrowserPreview({
    name: "sample.tiff",
    mime: "image/tiff",
    base64: "TU0AKg==",
  }, {fetchImpl, urlApi});
  const storedPreviewUrl = await images.requestDerivedBrowserPreview({
    name: "stored.tiff",
    mime: "image/x-tiff",
    path: "attachments/stored.tiff",
  }, {fetchImpl, urlApi});

  const cacheRequests = [];
  const pendingRequests = [];
  const revoked = [];
  const settled = [];
  const cache = images.createDerivedBrowserPreviewCache({
    requestPreview: (image) => {
      cacheRequests.push({...image});
      const request = deferred();
      pendingRequests.push(request);
      return request.promise;
    },
    urlApi: {revokeObjectURL: (url) => revoked.push(url)},
    onSettled: (entry) => settled.push({key: entry.key, status: entry.status}),
  });
  const first = {mime: "image/tiff", path: "attachments/a.tiff", name: "a.tiff"};
  const firstAlias = {mime: "image/x-tiff", path: "attachments/a.tiff", name: "alias.tiff"};
  const firstBefore = JSON.stringify(first);
  const firstPromise = cache.ensure(first);
  const aliasPromise = cache.ensure(firstAlias);
  await Promise.resolve();
  const pendingEvidence = {
    samePromise: firstPromise === aliasPromise,
    status: cache.status(first),
    source: cache.source(first),
    requestCount: cacheRequests.length,
    sameKey: images.derivedBrowserPreviewCacheKey(first)
      === images.derivedBrowserPreviewCacheKey(firstAlias),
  };
  pendingRequests[0].resolve("blob:ready-a");
  const readyValues = await Promise.all([firstPromise, aliasPromise]);
  const readyRepeat = await cache.ensure(firstAlias);
  const readyEvidence = {
    status: cache.status(firstAlias),
    source: cache.source(firstAlias),
    values: readyValues,
    repeat: readyRepeat,
    requestCount: cacheRequests.length,
    inputUnchanged: JSON.stringify(first) === firstBefore,
  };

  const failed = {mime: "image/tiff", path: "attachments/b.tiff"};
  const failedPromise = cache.ensure(failed);
  await Promise.resolve();
  pendingRequests[1].reject(new Error("synthetic preview failure"));
  const failedValue = await failedPromise;
  const failedRepeat = await cache.ensure(failed);
  const failedEvidence = {
    status: cache.status(failed),
    source: cache.source(failed),
    values: [failedValue, failedRepeat],
    requestCount: cacheRequests.length,
  };

  const other = {mime: "image/tiff", path: "attachments/c.tiff"};
  const otherPromise = cache.ensure(other);
  await Promise.resolve();
  pendingRequests[2].resolve("blob:ready-c");
  await otherPromise;

  const late = {mime: "image/tiff", path: "attachments/late.tiff"};
  const latePromise = cache.ensure(late);
  await Promise.resolve();
  const beforeClear = {
    requestCount: cacheRequests.length,
    firstStatus: cache.status(first),
    failedStatus: cache.status(failed),
    otherStatus: cache.status(other),
    lateStatus: cache.status(late),
  };
  cache.clear();
  cache.clear();
  pendingRequests[3].resolve("blob:late-after-clear");
  await latePromise;

  const createDisposalCache = () => {
    const requests = [];
    const pending = [];
    const revokedUrls = [];
    const settledEntries = [];
    const instance = images.createDerivedBrowserPreviewCache({
      requestPreview: (image) => {
        requests.push({...image});
        const request = deferred();
        pending.push(request);
        return request.promise;
      },
      urlApi: {revokeObjectURL: (url) => revokedUrls.push(url)},
      onSettled: (entry) => settledEntries.push({key: entry.key, status: entry.status}),
    });
    return {instance, pending, requests, revokedUrls, settledEntries};
  };
  const disposeTarget = {mime: "image/tiff", path: "attachments/dispose.tiff"};

  const failedDisposal = createDisposalCache();
  const failedDisposalPromise = failedDisposal.instance.ensure(disposeTarget);
  await Promise.resolve();
  failedDisposal.pending[0].reject(new Error("synthetic disposed failure"));
  await failedDisposalPromise;
  const failedBeforeDispose = {
    requestCount: failedDisposal.requests.length,
    status: failedDisposal.instance.status(disposeTarget),
  };
  failedDisposal.instance.dispose();
  failedDisposal.instance.dispose();
  const failedAfterDisposeValue = await failedDisposal.instance.ensure(disposeTarget);

  const pendingDisposal = createDisposalCache();
  const pendingDisposalPromise = pendingDisposal.instance.ensure(disposeTarget);
  await Promise.resolve();
  pendingDisposal.instance.dispose();
  pendingDisposal.instance.dispose();
  pendingDisposal.pending[0].resolve("blob:pending-after-dispose");
  const pendingAfterDisposeValue = await pendingDisposalPromise;
  const pendingRepeatValue = await pendingDisposal.instance.ensure(disposeTarget);

  const readyDisposal = createDisposalCache();
  const readyDisposalPromise = readyDisposal.instance.ensure(disposeTarget);
  await Promise.resolve();
  readyDisposal.pending[0].resolve("blob:ready-before-dispose");
  await readyDisposalPromise;
  const readyBeforeDispose = readyDisposal.instance.source(disposeTarget);
  readyDisposal.instance.dispose();
  readyDisposal.instance.dispose();
  const readyAfterDisposeValue = await readyDisposal.instance.ensure(disposeTarget);

  const freshPageCache = createDisposalCache();
  const freshPagePromise = freshPageCache.instance.ensure(disposeTarget);
  await Promise.resolve();
  freshPageCache.pending[0].resolve("blob:fresh-page");
  const freshPageValue = await freshPagePromise;
  process.stdout.write(JSON.stringify({
    derived: ["image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp", "image/x-icon", "image/tiff"]
      .map((mime) => images.requiresDerivedBrowserPreview(mime)),
    previewUrl,
    storedPreviewUrl,
    requests: calls.map((call) => ({
      url: call.url,
      method: call.options.method,
      body: call.options.body ? JSON.parse(call.options.body) : null,
    })),
    cache: {
      pendingEvidence,
      readyEvidence,
      failedEvidence,
      beforeClear,
      requestPaths: cacheRequests.map((image) => image.path),
      revoked,
      settled,
      clearedStatuses: [cache.status(first), cache.status(failed), cache.status(other), cache.status(late)],
    },
    disposal: {
      failed: {
        before: failedBeforeDispose,
        afterValue: failedAfterDisposeValue,
        requestCount: failedDisposal.requests.length,
        source: failedDisposal.instance.source(disposeTarget),
        status: failedDisposal.instance.status(disposeTarget),
        revoked: failedDisposal.revokedUrls,
        settled: failedDisposal.settledEntries,
      },
      pending: {
        values: [pendingAfterDisposeValue, pendingRepeatValue],
        requestCount: pendingDisposal.requests.length,
        source: pendingDisposal.instance.source(disposeTarget),
        status: pendingDisposal.instance.status(disposeTarget),
        revoked: pendingDisposal.revokedUrls,
        settled: pendingDisposal.settledEntries,
      },
      ready: {
        beforeSource: readyBeforeDispose,
        afterValue: readyAfterDisposeValue,
        requestCount: readyDisposal.requests.length,
        source: readyDisposal.instance.source(disposeTarget),
        status: readyDisposal.instance.status(disposeTarget),
        revoked: readyDisposal.revokedUrls,
        settled: readyDisposal.settledEntries,
      },
      freshPage: {
        value: freshPageValue,
        requestCount: freshPageCache.requests.length,
        source: freshPageCache.instance.source(disposeTarget),
        status: freshPageCache.instance.status(disposeTarget),
      },
    },
    sources: {
      composerTiff: images.imagePreviewSource({mime: "image/tiff", _previewUrl: previewUrl, base64: "ORIGINAL"}),
      pendingTiffWithoutPreview: images.imagePreviewSource({mime: "image/tiff", base64: "ORIGINAL"}),
      storedTiff: images.imagePreviewSource({path: "attachments/sample.tiff", mime: "image/tiff"}),
      storedPng: images.imagePreviewSource({path: "attachments/sample.png", mime: "image/png"}),
      inlineGif: images.imagePreviewSource({mime: "image/gif", base64: "R0lG"}),
    },
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["derived"], [False, False, False, False, False, False, True])
        self.assertTrue(data["previewUrl"].startswith("blob:tiff-"))
        self.assertTrue(data["storedPreviewUrl"].startswith("blob:tiff-"))
        self.assertEqual(data["requests"], [
            {
                "url": "/api/attachments/preview",
                "method": "POST",
                "body": {"mime": "image/tiff", "contentBase64": "TU0AKg=="},
            },
            {
                "url": "/api/attachments/preview?path=attachments%2Fstored.tiff",
                "method": "GET",
                "body": None,
            },
        ])
        self.assertEqual(data["cache"]["pendingEvidence"], {
            "samePromise": True,
            "status": "pending",
            "source": "",
            "requestCount": 1,
            "sameKey": True,
        })
        self.assertEqual(data["cache"]["readyEvidence"], {
            "status": "ready",
            "source": "blob:ready-a",
            "values": ["blob:ready-a", "blob:ready-a"],
            "repeat": "blob:ready-a",
            "requestCount": 1,
            "inputUnchanged": True,
        })
        self.assertEqual(data["cache"]["failedEvidence"], {
            "status": "failed",
            "source": "",
            "values": ["", ""],
            "requestCount": 2,
        })
        self.assertEqual(data["cache"]["beforeClear"], {
            "requestCount": 4,
            "firstStatus": "ready",
            "failedStatus": "failed",
            "otherStatus": "ready",
            "lateStatus": "pending",
        })
        self.assertEqual(data["cache"]["requestPaths"], [
            "attachments/a.tiff",
            "attachments/b.tiff",
            "attachments/c.tiff",
            "attachments/late.tiff",
        ])
        self.assertEqual(data["cache"]["revoked"], [
            "blob:ready-a",
            "blob:ready-c",
            "blob:late-after-clear",
        ])
        self.assertEqual(data["cache"]["settled"], [
            {"key": "image/tiff\u0000attachments/a.tiff", "status": "ready"},
            {"key": "image/tiff\u0000attachments/b.tiff", "status": "failed"},
            {"key": "image/tiff\u0000attachments/c.tiff", "status": "ready"},
        ])
        self.assertEqual(data["cache"]["clearedStatuses"], ["", "", "", ""])
        self.assertEqual(data["disposal"]["failed"], {
            "before": {"requestCount": 1, "status": "failed"},
            "afterValue": "",
            "requestCount": 1,
            "source": "",
            "status": "",
            "revoked": [],
            "settled": [{
                "key": "image/tiff\u0000attachments/dispose.tiff",
                "status": "failed",
            }],
        })
        self.assertEqual(data["disposal"]["pending"], {
            "values": ["", ""],
            "requestCount": 1,
            "source": "",
            "status": "",
            "revoked": ["blob:pending-after-dispose"],
            "settled": [],
        })
        self.assertEqual(data["disposal"]["ready"], {
            "beforeSource": "blob:ready-before-dispose",
            "afterValue": "",
            "requestCount": 1,
            "source": "",
            "status": "",
            "revoked": ["blob:ready-before-dispose"],
            "settled": [{
                "key": "image/tiff\u0000attachments/dispose.tiff",
                "status": "ready",
            }],
        })
        self.assertEqual(data["disposal"]["freshPage"], {
            "value": "blob:fresh-page",
            "requestCount": 1,
            "source": "blob:fresh-page",
            "status": "ready",
        })
        self.assertEqual(data["sources"]["composerTiff"], data["previewUrl"])
        self.assertEqual(data["sources"]["pendingTiffWithoutPreview"], "")
        self.assertEqual(
            data["sources"]["storedTiff"],
            "/api/attachments/preview?path=attachments%2Fsample.tiff",
        )
        self.assertEqual(
            data["sources"]["storedPng"],
            "/api/file?path=attachments%2Fsample.png&raw=1",
        )
        self.assertEqual(data["sources"]["inlineGif"], "data:image/gif;base64,R0lG")

        compression = APP_SOURCE[
            APP_SOURCE.index("async function compressImage("):
            APP_SOURCE.index("async function handleImagePaste(")
        ]
        self.assertIn("if (requiresDerivedBrowserPreview(sourceMime)) return original", compression)
        self.assertIn("previewUrl = await requestDerivedBrowserPreview(image)", compression)
        self.assertIn("previewFailed = true", compression)
        self.assertIn("data-composer-image-fallback", APP_SOURCE)
        upload = APP_SOURCE[
            APP_SOURCE.index("async function uploadImagesForStorage("):
            APP_SOURCE.index("function addImage(")
        ]
        self.assertNotIn("refs.push(img)", upload)
        self.assertNotIn("_previewUrl", PERSISTENCE_SOURCE)
        self.assertNotIn("_previewFailed", PERSISTENCE_SOURCE)
        self.assertIn("const persistedTiffPreviewCache = createDerivedBrowserPreviewCache", APP_SOURCE)
        self.assertIn("persistedTiffPreviewCache.dispose();", APP_SOURCE)
        self.assertNotIn("persistedTiffPreviewCache", PERSISTENCE_SOURCE)

    def test_skills_memory_feature_ranks_and_loads_context_without_app_globals(self):
        self.assertIn("features.skillsMemory = Object.freeze", SKILLS_MEMORY_SOURCE)
        script = """
global.window = {Code: {features: {}}};
require("./src/features/skills-memory.js");
const {applySkillTaskPolicy, createSkillsMemoryFeature, getSkillToolBudgets, rankMatchedSkills} = window.Code.features.skillsMemory;
const skills = [
  {name: "python-tests", description: "Python testing", keywords: ["python+pytest"]},
  {name: "review", description: "Review changes", keywords: []},
  {name: "general", description: "python help", keywords: []},
  {name: "writing-plans", description: "python pytest plan", keywords: ["python+pytest"]},
  {name: "disabled", description: "python pytest", keywords: ["python+pytest"]},
];
const ranked = rankMatchedSkills(skills, new Set(["disabled"]), "Review this Python pytest project");
const descriptionOnly = rankMatchedSkills(
  [{name: "python-testing", description: "Python testing", keywords: []}],
  new Set(),
  "Explain Python decorators",
);
const skillTaskPolicy = applySkillTaskPolicy(
  new Set(["read_file", "task"]),
  [{name: "brainstorming", keywords: ["brainstorm"], tools: ["read_file"]}],
  new Set(),
  "brainstorm options",
  "brainstorming",
);
const explicitDelegationPolicy = applySkillTaskPolicy(
  new Set(["read_file", "task"]),
  [{name: "brainstorming", keywords: ["brainstorm"], tools: ["read_file"]}],
  new Set(),
  "brainstorm with parallel subagents",
  "brainstorming",
);
const brainstormingBudgets = getSkillToolBudgets(
  [{name: "brainstorming", keywords: ["brainstorm"], tools: ["read_file"]}],
  new Set(),
  "brainstorm options",
  "brainstorming",
);
const deepAuditBudgets = getSkillToolBudgets(
  [{name: "brainstorming", keywords: ["brainstorm"], tools: ["read_file"]}],
  new Set(),
  "run a deep audit",
  "brainstorming",
);
const calls = [];
const state = {skills: [], disabledSkills: new Set()};
const feature = createSkillsMemoryFeature({
  state,
  elements: {},
  apiJson: async (url) => {
    calls.push(url);
    if (url === "/api/skills?brief=1") return {data: [{name: "demo", body: null, keywords: ["demo"], tools: ["read_file"]}]};
    if (url === "/api/skills/demo") return {body: "Demo instructions", path: "skills/demo", resources: {}};
    if (url === "/api/memory-context") return {found: true, count: 2, content: "memory"};
    throw new Error(`unexpected request: ${url}`);
  },
  document: {getElementById: () => null},
  storage: {setItem: () => {}},
});
(async () => {
  const loadedSkills = await feature.loadSkills();
  const loadedSkill = await feature.ensureSkillBody(loadedSkills[0]);
  const matchedPrompt = await feature.getMatchedSkillPrompts("run the demo workflow");
  const memory = await feature.loadMemoryContext();
  process.stdout.write(JSON.stringify({
    ranked: ranked.map((skill) => skill.name),
    descriptionOnly: descriptionOnly.map((skill) => skill.name),
    skillTaskPolicy: [...skillTaskPolicy],
    explicitDelegationPolicy: [...explicitDelegationPolicy],
    brainstormingBudgets,
    deepAuditBudgets,
    loadedSkill,
    matchedPrompt,
    memory,
    calls,
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["ranked"], ["python-tests"])
        self.assertEqual(data["descriptionOnly"], [])
        self.assertEqual(data["skillTaskPolicy"], ["read_file"])
        self.assertEqual(data["explicitDelegationPolicy"], ["read_file", "task"])
        self.assertEqual(data["brainstormingBudgets"][0]["limit"], 3)
        self.assertEqual(data["brainstormingBudgets"][1]["limit"], 4)
        self.assertIn("不得加入未实测的耗时", data["brainstormingBudgets"][0]["exhaustedMessage"])
        self.assertEqual(data["deepAuditBudgets"], [])
        self.assertEqual(data["loadedSkill"]["body"], "Demo instructions")
        self.assertIn("[Skill: demo]", data["matchedPrompt"])
        self.assertIn("Preferred tools: read_file", data["matchedPrompt"])
        self.assertIn("does not expand the current mode's permissions", data["matchedPrompt"])
        self.assertIn("Do not call task unless it is listed", data["matchedPrompt"])
        self.assertIn("正文已加载，不要再次调用 use_skill", APP_SOURCE)
        self.assertEqual(data["memory"], {"found": True, "count": 2, "content": "memory"})
        self.assertEqual(
            data["calls"],
            ["/api/skills?brief=1", "/api/skills/demo", "/api/memory-context"],
        )

    def test_settings_feature_owns_theme_update_auth_and_key_storage(self):
        self.assertIn("features.settings = Object.freeze", SETTINGS_SOURCE)
        script = """
const values = new Map([["code-key-config", JSON.stringify([{name: "primary", key: "sk-1", enabled: true}])]]);
const storage = {
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: (key) => values.delete(key),
};
const bodyClasses = new Set();
const replaced = [];
global.window = {
  localStorage: storage,
  URLSearchParams,
  location: {search: "?code_token=token-1&user_id=user-1&username=Alice", href: "http://127.0.0.1:3010/", replace: () => {}},
  history: {replaceState: (...args) => replaced.push(args)},
  matchMedia: () => ({matches: false, addEventListener: () => {}}),
  setTimeout,
  setInterval,
  clearInterval,
};
require("./src/core/namespace.js");
require("./src/core/platform.js");
require("./src/features/settings.js");
const {createSettingsFeature, loadKeyConfig} = window.Code.features.settings;
const calls = [];
const toasts = [];
const state = {};
const documentStub = {
  body: {classList: {toggle: (name, active) => active ? bodyClasses.add(name) : bodyClasses.delete(name)}},
  getElementById: () => null,
  querySelectorAll: () => [],
};
const feature = createSettingsFeature({
  state,
  elements: {},
  t: (key, args) => args?.name ? `${key}:${args.name}` : key,
  apiJson: async (url) => {
    calls.push(url);
    await new Promise((resolve) => setTimeout(resolve, 1));
    return {updateAvailable: true, remoteVersion: "0.6.0"};
  },
  showToast: (...args) => toasts.push(args),
  document: documentStub,
  storage,
});
(async () => {
  feature.applyTheme("dark");
  const [first, second] = await Promise.all([
    feature.checkForUpdates(),
    feature.checkForUpdates(),
  ]);
  const callbackHandled = await feature.checkCodeCallback();
  process.stdout.write(JSON.stringify({
    bodyClasses: [...bodyClasses],
    theme: values.get("code-theme"),
    keys: loadKeyConfig(storage),
    calls,
    first,
    second,
    updateInfo: state.updateInfo,
    callbackHandled,
    auth: JSON.parse(values.get("code-platform-auth")),
    replaced,
    toasts,
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["bodyClasses"], ["theme-dark"])
        self.assertEqual(data["theme"], "dark")
        self.assertEqual(data["keys"], [{"name": "primary", "key": "sk-1", "enabled": True, "source": "manual"}])
        self.assertEqual(data["calls"], ["/api/check-update"])
        self.assertEqual(data["first"], data["second"])
        self.assertEqual(data["updateInfo"]["remoteVersion"], "0.6.0")
        self.assertTrue(data["callbackHandled"])
        self.assertEqual(data["auth"], {"token": "token-1", "userId": "user-1", "username": "Alice"})
        self.assertEqual(data["replaced"], [[None, "", "/"]])
        self.assertEqual(data["toasts"], [["loggedInAs:Alice", "warning"]])

    def test_workbar_login_callback_follows_current_code_origin(self):
        self.assertNotIn('encodeURIComponent("http://127.0.0.1:3010/")', SETTINGS_SOURCE)
        self.assertIn("global.open(buildPlatformLoginUrl(), \"_blank\")", SETTINGS_SOURCE)
        script = """
global.window = {
  Code: {core: {}, features: {}},
  URL,
  location: {href: "http://127.0.0.1:3010/"},
};
require("./src/core/namespace.js");
require("./src/core/platform.js");
require("./src/features/settings.js");
const {buildPlatformLoginUrl} = window.Code.features.settings;
const hrefs = [
  "http://127.0.0.1:3010/",
  "http://127.0.0.1:3011/settings?panel=account#login",
  "http://localhost:45123/dev/",
];
process.stdout.write(JSON.stringify(hrefs.map((href) => buildPlatformLoginUrl({href}))));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        urls = json.loads(completed.stdout)
        self.assertEqual(
            urls,
            [
                "https://workbar.ai/code/connect?callback=http%3A%2F%2F127.0.0.1%3A3010%2F",
                "https://workbar.ai/code/connect?callback=http%3A%2F%2F127.0.0.1%3A3011%2F",
                "https://workbar.ai/code/connect?callback=http%3A%2F%2Flocalhost%3A45123%2F",
            ],
        )

    def test_settings_feature_validates_callback_and_skips_duplicate_startup_validation(self):
        script = r"""
const values = new Map([["code-platform-auth", JSON.stringify({token: "access-1", userId: "7", username: "old"})]]);
const storage = {
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: (key) => values.delete(key),
};
const nodes = new Map();
const documentStub = {
  body: {appendChild: (node) => nodes.set(node.id, node)},
  createElement: () => {
    let id = "";
    return {
      innerHTML: "",
      className: "",
      set id(value) { id = value; },
      get id() { return id; },
      remove: () => nodes.delete(id),
    };
  },
  getElementById: (id) => nodes.get(id) || null,
  querySelectorAll: () => [],
  addEventListener: () => {},
};
let mode = "valid";
const calls = [];
const fetchStub = async (url, options) => {
  calls.push({url, body: JSON.parse(options.body)});
  if (mode === "expired") return {status: 401, ok: false, json: async () => ({})};
  return {status: 200, ok: true, json: async () => ({valid: true, account: {userId: "7", username: "alice"}})};
};
global.window = {
  localStorage: storage,
  URLSearchParams,
  location: {search: "?code_token=callback-token&user_id=7&username=alice", reload: () => {}},
  history: {replaceState: () => {}},
  matchMedia: () => ({matches: false, addEventListener: () => {}}),
  addEventListener: () => {},
  open: () => {},
  setTimeout,
  setInterval,
  clearInterval,
};
require("./src/core/namespace.js");
require("./src/core/platform.js");
require("./src/features/settings.js");
const feature = window.Code.features.settings.createSettingsFeature({
  elements: {},
  t: (key) => key,
  apiJson: async () => ({}),
  document: documentStub,
  storage,
  fetch: fetchStub,
});
(async () => {
  const valid = await feature.initializePlatformAuth();
  const refreshedAuth = JSON.parse(values.get("code-platform-auth"));
  const gateAfterValid = nodes.has("platformAuthGate");
  window.location.search = "";
  mode = "expired";
  const cached = await feature.initializePlatformAuth();
  const cachedGate = nodes.has("platformAuthGate");
  process.stdout.write(JSON.stringify({valid, cached, refreshedAuth, gateAfterValid, cachedGate, authExists: values.has("code-platform-auth"), calls}));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["valid"])
        self.assertTrue(data["cached"])
        self.assertEqual(data["refreshedAuth"]["username"], "alice")
        self.assertFalse(data["gateAfterValid"])
        self.assertFalse(data["cachedGate"])
        self.assertTrue(data["authExists"])
        self.assertEqual(data["calls"], [{
            "url": "/api/code/auth/validate",
            "body": {"token": "callback-token", "userId": "7"},
        }])

    def test_settings_silent_sync_turns_unauthorized_cached_auth_into_expired_gate(self):
        script = r"""
const values = new Map([["code-platform-auth", JSON.stringify({token: "expired", userId: "7"})]]);
const storage = {
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: (key) => values.delete(key),
};
const nodes = new Map();
const documentStub = {
  body: {appendChild: (node) => nodes.set(node.id, node)},
  createElement: () => {
    let id = "";
    return {
      innerHTML: "",
      className: "",
      set id(value) { id = value; },
      get id() { return id; },
      remove: () => nodes.delete(id),
    };
  },
  getElementById: (id) => nodes.get(id) || null,
  querySelectorAll: () => [],
};
global.window = {
  localStorage: storage,
  URLSearchParams,
  location: {search: "", reload: () => {}},
  history: {replaceState: () => {}},
  matchMedia: () => ({matches: false, addEventListener: () => {}}),
  addEventListener: () => {},
  open: () => {},
  setTimeout,
  setInterval,
  clearInterval,
};
require("./src/core/namespace.js");
require("./src/core/platform.js");
require("./src/features/settings.js");
const feature = window.Code.features.settings.createSettingsFeature({
  elements: {apiKey: {value: ""}},
  t: (key) => key,
  apiJson: async () => ({}),
  document: documentStub,
  storage,
  fetch: async () => ({status: 401, ok: false, json: async () => ({})}),
});
(async () => {
  const initialized = await feature.initializePlatformAuth();
  const result = await feature.syncPlatformKeysSilently();
  process.stdout.write(JSON.stringify({
    initialized,
    result,
    authExists: values.has("code-platform-auth"),
    gate: nodes.get("platformAuthGate")?.innerHTML || "",
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["initialized"])
        self.assertTrue(data["result"]["authExpired"])
        self.assertFalse(data["authExists"])
        self.assertIn("workbarSessionExpired", data["gate"])

    def test_settings_sync_displays_structured_workbar_failure(self):
        script = r"""
const values = new Map([["code-platform-auth", JSON.stringify({token: "access-1", userId: "7"})]]);
const storage = {
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: (key) => values.delete(key),
};
const toasts = [];
const translations = {
  syncFailed: "同步失败：{message}",
  syncStageListTokens: "获取令牌列表",
  syncStageReadKeys: "读取完整 Key",
  syncStageUnknown: "同步 workbar Key",
  syncPositionPage: "（第 {index} 页）",
  syncPositionBatch: "（第 {index} 批）",
  syncFailureHttp: "{stage}{position}时 workbar 返回 {status}",
  syncFailureTimeout: "{stage}{position}超时",
  syncFailureNetwork: "{stage}{position}网络连接失败",
  syncFailureInvalidResponse: "{stage}{position}收到无效响应",
  syncFailureUnknown: "{stage}{position}失败（HTTP {status}）",
};
const t = (key, args = {}) => Object.entries(args).reduce(
  (text, [name, value]) => text.replaceAll(`{${name}}`, value),
  translations[key] || key,
);
global.window = {
  localStorage: storage,
  URL,
  URLSearchParams,
  location: {href: "http://127.0.0.1:3011/", search: ""},
  history: {replaceState: () => {}},
  matchMedia: () => ({matches: false, addEventListener: () => {}}),
  setTimeout,
  setInterval,
  clearInterval,
};
require("./src/core/namespace.js");
require("./src/core/platform.js");
require("./src/features/settings.js");
const feature = window.Code.features.settings.createSettingsFeature({
  elements: {apiKey: {value: ""}},
  t,
  apiJson: async () => ({}),
  document: {getElementById: () => null, querySelectorAll: () => []},
  storage,
  fetch: async () => ({
    status: 502,
    ok: false,
    json: async () => ({
      error: "workbar_sync_failed",
      stage: "read_keys",
      kind: "http",
      upstreamStatus: 504,
      batch: 2,
    }),
  }),
  showToast: (...args) => toasts.push(args),
});
(async () => {
  const result = await feature.syncKeysFromPlatform();
  process.stdout.write(JSON.stringify({result, toasts}));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        message = "读取完整 Key（第 2 批）时 workbar 返回 504"
        self.assertEqual(data["result"], {"ok": False, "error": message})
        self.assertEqual(data["toasts"], [[f"同步失败：{message}", "error"]])
        self.assertIn('syncFailureTimeout: "{stage}{position}超时"', I18N_SOURCE)
        self.assertIn('syncFailureTimeout: "{stage}{position} timed out"', I18N_SOURCE)

    def test_settings_sync_distinguishes_empty_unreadable_and_all_added_results(self):
        script = r"""
const values = new Map([
  ["code-platform-auth", JSON.stringify({token: "access-1", userId: "7"})],
  ["code-key-config", JSON.stringify([
    {name: "local", key: "sk-existing", enabled: true, source: "manual"},
  ])],
]);
const storage = {
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: (key) => values.delete(key),
};
const toasts = [];
let mode = "empty";
let appendedHtml = "";
const actionButton = {textContent: "", addEventListener: () => {}};
const documentStub = {
  body: {appendChild: (node) => { appendedHtml = node.innerHTML; }},
  createElement: () => ({
    id: "",
    className: "",
    innerHTML: "",
    remove: () => {},
    addEventListener: () => {},
    querySelector: (selector) => selector === ".key-sync-close" || selector === "#keySyncCopyAll" ? actionButton : null,
    querySelectorAll: () => [],
  }),
  getElementById: () => null,
  querySelectorAll: () => [],
};
global.window = {
  localStorage: storage,
  URLSearchParams,
  location: {search: "", reload: () => {}},
  history: {replaceState: () => {}},
  matchMedia: () => ({matches: false, addEventListener: () => {}}),
  addEventListener: () => {},
  open: () => {},
  setTimeout,
  setInterval,
  clearInterval,
};
require("./src/core/namespace.js");
require("./src/core/platform.js");
require("./src/features/settings.js");
const feature = window.Code.features.settings.createSettingsFeature({
  elements: {apiKey: {value: "local: sk-existing"}},
  t: (key, args) => args?.count == null ? key : `${key}:${args.count}`,
  apiJson: async () => ({}),
  document: documentStub,
  storage,
  navigator: {clipboard: {writeText: async () => {}}},
  fetch: async () => {
    if (mode === "empty") return {status: 200, ok: true, json: async () => ({tokens: [], keys: {}})};
    if (mode === "unreadable") return {
      status: 200,
      ok: true,
      json: async () => ({tokens: [{id: 1}, {id: 2}], keys: {}}),
    };
    return {
      status: 200,
      ok: true,
      json: async () => ({tokens: [{id: 1, name: "existing", status: 1}], keys: {1: "sk-existing"}}),
    };
  },
  showToast: (...args) => toasts.push(args),
});
(async () => {
  const before = values.get("code-key-config");
  const empty = await feature.syncKeysFromPlatform();
  mode = "unreadable";
  const unreadable = await feature.syncKeysFromPlatform();
  mode = "all-added";
  const allAdded = await feature.syncKeysFromPlatform();
  process.stdout.write(JSON.stringify({
    empty,
    unreadable,
    allAdded,
    toasts,
    appendedHtml,
    localConfigPreserved: before === values.get("code-key-config"),
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["empty"]["status"], "no-platform-tokens")
        self.assertEqual(data["empty"]["preservedLocalCount"], 1)
        self.assertEqual(data["unreadable"]["status"], "keys-unreadable")
        self.assertEqual(data["unreadable"]["unreadableKeyCount"], 2)
        self.assertEqual(data["unreadable"]["preservedLocalCount"], 1)
        self.assertEqual(data["allAdded"]["status"], "all-added")
        self.assertEqual(data["allAdded"]["presented"], 1)
        self.assertTrue(data["localConfigPreserved"])
        self.assertEqual(data["toasts"], [
            ["noPlatformTokens", "warning"],
            ["platformKeysUnreadable:2", "warning"],
        ])
        self.assertIn("allKeysAdded", data["appendedHtml"])
        self.assertIn('noPlatformTokens: "workbar 账号暂无 Key，本地 Key 不受影响"', I18N_SOURCE)
        self.assertIn('noPlatformTokens: "No Keys in this workbar account. Local Keys are unchanged."', I18N_SOURCE)
        self.assertIn('allKeysAdded: "当前 Code 已添加全部 Key"', I18N_SOURCE)
        self.assertIn('allKeysAdded: "All Keys are added to this Code instance"', I18N_SOURCE)

    def test_settings_silent_sync_merges_without_touching_manual_keys_or_ui(self):
        script = r"""
const values = new Map([
  ["code-platform-auth", JSON.stringify({token: "access-1", userId: "7", username: "alice"})],
  ["code-platform-key-exclusions", JSON.stringify({version: 1, accounts: {"7": ["3"]}})],
  ["code-key-config", JSON.stringify([
    {name: "manual", key: "sk-manual", enabled: false, source: "manual"},
    {name: "old", key: "sk-old", enabled: true, source: "platform"},
  ])],
]);
const storage = {
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: (key) => values.delete(key),
};
const apiKey = {value: ""};
const calls = [];
const toasts = [];
let settingsSaved = 0;
global.window = {
  localStorage: storage,
  URLSearchParams,
  location: {search: "", reload: () => {}},
  history: {replaceState: () => {}},
  matchMedia: () => ({matches: false, addEventListener: () => {}}),
  addEventListener: () => {},
  open: () => {},
  setTimeout,
  setInterval,
  clearInterval,
};
require("./src/core/namespace.js");
require("./src/core/platform.js");
require("./src/features/settings.js");
const feature = window.Code.features.settings.createSettingsFeature({
  elements: {apiKey},
  t: (key) => key,
  apiJson: async () => ({}),
  document: {getElementById: () => null, querySelectorAll: () => []},
  storage,
  fetch: async (url, options) => {
    calls.push({url, body: JSON.parse(options.body)});
    return {
      status: 200,
      ok: true,
      json: async () => ({
        tokens: [
          {id: 1, name: "old-renamed", status: 2},
          {id: 2, name: "new", status: 1},
          {id: 3, name: "removed", status: 1},
        ],
        keys: {1: "sk-old", 2: "sk-new", 3: "sk-removed"},
      }),
    };
  },
  saveLocalSettings: () => { settingsSaved += 1; },
  showToast: (...args) => toasts.push(args),
});
(async () => {
  const result = await feature.syncPlatformKeysSilently();
  process.stdout.write(JSON.stringify({
    result,
    config: JSON.parse(values.get("code-key-config")),
    apiKey: apiKey.value,
    calls,
    toasts,
    settingsSaved,
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        config = {entry["key"]: entry for entry in data["config"]}
        self.assertTrue(data["result"]["ok"])
        self.assertEqual(data["result"]["status"], "synced")
        self.assertEqual(data["result"]["imported"], 1)
        self.assertEqual(config["sk-manual"], {
            "name": "manual", "key": "sk-manual", "enabled": False, "source": "manual",
        })
        self.assertEqual(config["sk-old"]["name"], "old-renamed")
        self.assertFalse(config["sk-old"]["enabled"])
        self.assertEqual(config["sk-old"]["platformTokenId"], "1")
        self.assertEqual(config["sk-new"]["source"], "platform")
        self.assertEqual(config["sk-new"]["platformTokenId"], "2")
        self.assertNotIn("sk-removed", config)
        self.assertIn("manual: sk-manual", data["apiKey"])
        self.assertEqual(data["calls"], [{
            "url": "/api/code/sync-keys",
            "body": {"token": "access-1", "userId": "7"},
        }])
        self.assertEqual(data["toasts"], [])
        self.assertEqual(data["settingsSaved"], 1)
        self.assertIn("const platformSyncPromise = syncPlatformKeysSilently();", APP_SOURCE)
        self.assertNotIn("await syncPlatformKeysSilently()", APP_SOURCE)

    def test_settings_interactive_sync_masks_html_and_copies_colon_formatted_keys(self):
        script = r"""
const values = new Map([
  ["code-platform-auth", JSON.stringify({token: "access-1", userId: "7"})],
  ["code-platform-key-exclusions", JSON.stringify({version: 1, accounts: {"7": ["2"]}})],
  ["code-key-config", JSON.stringify([
    {name: "existing", key: "sk-existing-secret", enabled: true, source: "manual"},
  ])],
]);
const storage = {
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: (key) => values.delete(key),
};
const writes = [];
const toasts = [];
const copyHandlers = [];
let copyAllHandler = null;
let appended = null;
const closeButton = {addEventListener: () => {}};
const copyAllButton = {
  textContent: "",
  addEventListener: (type, handler) => { if (type === "click") copyAllHandler = handler; },
};
const copyButtons = [0, 1].map((index) => ({
  dataset: {copyIndex: String(index)},
  textContent: "",
  addEventListener: (type, handler) => { if (type === "click") copyHandlers[index] = handler; },
}));
const overlay = {
  id: "",
  className: "",
  innerHTML: "",
  remove: () => {},
  addEventListener: () => {},
  querySelector: (selector) => selector === ".key-sync-close" ? closeButton
    : selector === "#keySyncCopyAll" ? copyAllButton : null,
  querySelectorAll: (selector) => selector === ".key-copy-one" ? copyButtons : [],
};
const documentStub = {
  body: {appendChild: (node) => { appended = node; }},
  createElement: () => overlay,
  getElementById: () => null,
  querySelectorAll: () => [],
};
global.window = {
  localStorage: storage,
  URLSearchParams,
  location: {search: "", reload: () => {}},
  history: {replaceState: () => {}},
  matchMedia: () => ({matches: false, addEventListener: () => {}}),
  addEventListener: () => {},
  open: () => {},
  setTimeout: (handler) => { handler(); return 1; },
  setInterval,
  clearInterval,
};
require("./src/core/namespace.js");
require("./src/core/platform.js");
require("./src/features/settings.js");
const feature = window.Code.features.settings.createSettingsFeature({
  elements: {apiKey: {value: "existing: sk-existing-secret"}},
  t: (key, args) => args?.count == null ? key : `${key}:${args.count}`,
  apiJson: async () => ({}),
  document: documentStub,
  storage,
  navigator: {clipboard: {writeText: async (text) => { writes.push(text); }}},
  fetch: async () => ({
    status: 200,
    ok: true,
    json: async () => ({
      tokens: [
        {id: 1, name: "existing", status: 1},
        {id: 2, name: "new:key\nname", status: 1},
        {id: 3, name: "disabled", status: 2},
        {id: 4, name: "unreadable", status: 1},
      ],
      keys: {1: "existing-secret", 2: "sk-new-secret", 3: "sk-disabled-secret"},
    }),
  }),
  showToast: (...args) => toasts.push(args),
});
(async () => {
  const result = await feature.syncKeysFromPlatform();
  copyHandlers[0]();
  copyAllHandler();
  await Promise.resolve();
  await Promise.resolve();
  process.stdout.write(JSON.stringify({
    result,
    html: appended.innerHTML,
    writes,
    toasts,
    copyButtonCount: (appended.innerHTML.match(/key-copy-one/g) || []).length,
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["result"]["presented"], 3)
        self.assertEqual(data["result"]["status"], "partial")
        self.assertEqual(data["result"]["tokenCount"], 4)
        self.assertEqual(data["result"]["unreadableKeyCount"], 1)
        self.assertEqual(data["copyButtonCount"], 2)
        self.assertIn("alreadyAdded", data["html"])
        self.assertIn("removedFromCode", data["html"])
        self.assertIn("removedKeyCount:1", data["html"])
        self.assertIn("removedKeysHint", data["html"])
        self.assertIn("disabledStatus", data["html"])
        self.assertIn("disabledKeyCount:1", data["html"])
        self.assertIn("unreadableKeyCount:1", data["html"])
        self.assertIn('class="modal-card key-sync-card"', data["html"])
        self.assertIn('class="key-sync-name" title="existing"', data["html"])
        self.assertIn("key-sync-disabled", data["html"])
        self.assertIn("sk-••••••••cret", data["html"])
        self.assertNotIn("sk-existing-secret", data["html"])
        self.assertNotIn("sk-new-secret", data["html"])
        self.assertNotIn("sk-disabled-secret", data["html"])
        self.assertEqual(data["writes"], [
            "existing: sk-existing-secret",
            "existing: sk-existing-secret\nnew key name: sk-new-secret",
        ])
        self.assertEqual(data["toasts"], [])

    def test_settings_key_cards_and_model_detection_keep_existing_controls(self):
        for expected in (
            'class="key-main"',
            'class="key-act-btn key-eye"',
            'class="toggle-switch key-enable"',
            'class="key-act-btn key-trash"',
            'data-source="${entry.source === "platform" ? "platform" : "manual"}" data-platform-token-id="${escapeHtml(entry.platformTokenId || "")}"',
            "platform.excludePlatformToken(auth.userId, platformTokenId, storage);",
            'class="key-workbar-btn"',
            't("getFromWorkbar")',
            'id="settingsModelCount"',
            'class="model-refresh-btn"',
            'refreshSettingsModelList',
            'await refreshModels()',
            "onKeyConfigChanged(saved)",
            "hasCatalogState",
        ):
            self.assertIn(expected, SETTINGS_SOURCE)
        for expected in (
            ".key-row.disabled .key-main",
            ".model-count-badge",
            ".model-refresh-btn.is-loading svg",
            ".model-provider-group + .model-provider-group",
            ".model-list-empty",
            ".model-list-state.is-loading::before",
            ".model-list-state.is-warning",
            ".model-list-state.is-error",
        ):
            self.assertIn(expected, STYLE_SOURCE)
        self.assertIn('getFromWorkbar: "从 workbar 获取"', I18N_SOURCE)

    def test_model_catalog_cache_restores_and_refreshes_atomically(self):
        catalog_start = APP_SOURCE.index('const MODEL_CATALOG_CACHE_KEY =')
        catalog_end = APP_SOURCE.index("function appendSystemError", catalog_start)
        catalog_source = APP_SOURCE[catalog_start:catalog_end]
        script = f"""
const values = new Map([
  ["code-model", "old-model"],
  ["code-model-catalog-cache-v1", JSON.stringify({{
    version: 1,
    baseUrl: "https://workbar.ai",
    models: ["old-model"],
    savedAt: 1,
  }})],
]);
const localStorage = {{
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: (key) => values.delete(key),
}};
const state = {{
  modelKeyMap: {{}},
  modelKeysMap: {{}},
  modelCatalogModels: ["old-model"],
  modelCatalogStatusKey: "",
  modelCatalogSource: "cache",
}};
const settingsList = {{innerHTML: ""}};
const settingsCount = {{textContent: ""}};
const document = {{
  getElementById: (id) => id === "settingsModelList" ? settingsList : id === "settingsModelCount" ? settingsCount : null,
}};
const els = {{
  baseUrl: {{value: "https://workbar.ai"}},
  modelPillDropdown: {{innerHTML: ""}},
  modelListBox: {{innerHTML: ""}},
  refreshModelsBtn: {{disabled: false}},
}};
const toasts = [];
let selectedModel = "old-model";
let fetchMode = "success";
const t = (key) => key;
const escapeHtml = (value) => String(value);
const showToast = (...args) => toasts.push(args);
const getSelectedModel = () => selectedModel;
const setSelectedModel = (value) => {{ selectedModel = value; }};
const getApiKeys = () => ["sk-one", "sk-two"];
const setModelContextCatalog = (entries) => {{ state.contextEntries = entries; }};
let fetchCalls = 0;
async function fetch() {{
  if (fetchMode === "failure") throw new Error("offline");
  fetchCalls += 1;
  const data = fetchMode === "empty"
    ? []
    : fetchCalls === 1
      ? [
          {{id: "models/gpt-b", contextWindowTokens: 500000, contextWindowSource: "stale_official", contextWindowHard: false, maxOutputTokens: 128000, officialProvider: "xai", officialCatalogRevision: "test"}},
          {{id: "gpt-a", contextWindowTokens: 400000, contextWindowSource: "official", contextWindowHard: false}},
          {{id: "imagen-3"}},
        ]
      : [
          {{id: "models/gpt-b", contextWindowTokens: 1000000, contextWindowSource: "family", contextWindowHard: false}},
          {{id: "gpt-a", contextWindowTokens: 1000000, contextWindowSource: "metadata", contextWindowHard: true}},
        ];
  return {{ok: true, json: async () => ({{data}})}};
}}
eval({json.dumps(catalog_source)});
(async () => {{
  const firstPromise = refreshModels();
  const duringStatus = state.modelCatalogStatusKey;
  const first = await firstPromise;
  const firstMapKey = state.modelKeyMap["gpt-a"];
  const cacheTextAfterSuccess = values.get("code-model-catalog-cache-v1");
  const cacheAfterSuccess = JSON.parse(cacheTextAfterSuccess);

  selectedModel = "gpt-b";
  values.set("code-model", "gpt-b");
  state.modelCatalogModels = [];
  const restored = restoreCachedModelCatalog();
  const restoreStatus = state.modelCatalogStatusKey;

  fetchMode = "failure";
  const failed = await refreshModels();
  const failureStatus = state.modelCatalogStatusKey;
  const failureSelection = selectedModel;
  const cacheAfterFailure = values.has("code-model-catalog-cache-v1");

  fetchMode = "empty";
  const empty = await refreshModels();
  const emptyStatus = state.modelCatalogStatusKey;
  const emptySelection = selectedModel;
  const emptyCacheExists = values.has("code-model-catalog-cache-v1");
  markModelCatalogStale([{{key: "sk-two", enabled: true}}]);
  const enabledKeyStatus = state.modelCatalogStatusKey;
  markModelCatalogStale([{{key: "sk-two", enabled: false}}]);
  const disabledKeyStatus = state.modelCatalogStatusKey;
  process.stdout.write(JSON.stringify({{
    duringStatus,
    first,
    firstMapKey,
    cacheAfterSuccess,
    cacheContainsSecret: cacheTextAfterSuccess.includes("sk-one"),
    restored,
    restoreStatus,
    failed,
    failureStatus,
    failureSelection,
    cacheAfterFailure,
    empty,
    emptyStatus,
    emptySelection,
    emptyCacheExists,
    settingsCount: settingsCount.textContent,
    enabledKeyStatus,
    disabledKeyStatus,
    toasts,
  }}));
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["duringStatus"], "detectingModels")
        self.assertEqual(data["first"], {"ok": True, "models": ["gpt-a", "gpt-b"]})
        self.assertEqual(data["firstMapKey"], "sk-one")
        self.assertEqual(data["cacheAfterSuccess"]["version"], 2)
        self.assertEqual(data["cacheAfterSuccess"]["models"], ["gpt-a", "gpt-b"])
        self.assertEqual(
            [entry["id"] for entry in data["cacheAfterSuccess"]["entries"]],
            ["gpt-a", "gpt-b"],
        )
        self.assertEqual(
            data["cacheAfterSuccess"]["entries"][0]["contextWindowSource"],
            "metadata",
        )
        self.assertEqual(
            data["cacheAfterSuccess"]["entries"][0]["contextWindowTokens"],
            1000000,
        )
        self.assertTrue(data["cacheAfterSuccess"]["entries"][0]["contextWindowHard"])
        self.assertEqual(
            data["cacheAfterSuccess"]["entries"][1]["contextWindowSource"],
            "stale_official",
        )
        self.assertEqual(
            data["cacheAfterSuccess"]["entries"][1]["contextWindowTokens"],
            500000,
        )
        self.assertEqual(
            data["cacheAfterSuccess"]["entries"][1]["maxOutputTokens"],
            128000,
        )
        self.assertNotIn("key", data["cacheAfterSuccess"])
        self.assertFalse(data["cacheContainsSecret"])
        self.assertEqual(data["restored"], ["gpt-a", "gpt-b"])
        self.assertEqual(data["restoreStatus"], "detectingModels")
        self.assertEqual(data["failed"]["reason"], "request-failed")
        self.assertEqual(data["failed"]["models"], ["gpt-a", "gpt-b"])
        self.assertEqual(data["failureStatus"], "modelCatalogRefreshFailedCached")
        self.assertEqual(data["failureSelection"], "gpt-b")
        self.assertTrue(data["cacheAfterFailure"])
        self.assertEqual(data["empty"], {"ok": True, "models": []})
        self.assertEqual(data["emptyStatus"], "noModelsFound")
        self.assertEqual(data["emptySelection"], "")
        self.assertFalse(data["emptyCacheExists"])
        self.assertEqual(data["settingsCount"], "0")
        self.assertEqual(data["enabledKeyStatus"], "modelCatalogNeedsRefresh")
        self.assertEqual(data["disabledKeyStatus"], "enterApiKey")

    def test_key_persistence_is_isolated_from_general_settings_and_syncs_across_tabs(self):
        save_start = APP_SOURCE.index("function saveLocalSettings(")
        save_end = APP_SOURCE.index("function handleUiSlashCommand(", save_start)
        general_save = APP_SOURCE[save_start:save_end]
        self.assertNotIn("saveKeyConfig", general_save)
        self.assertNotIn('setItem("code-key"', general_save)
        self.assertNotIn("function saveApiKeySettings()", APP_SOURCE)
        self.assertNotIn('els.apiKey.addEventListener("change"', APP_SOURCE)
        self.assertIn('LEGACY_KEY_STORAGE_KEYS.forEach((key) => storage?.removeItem?.(key));', PLATFORM_SOURCE)
        self.assertIn('event.key !== platform.KEY_CONFIG_STORAGE_KEY', SETTINGS_SOURCE)
        self.assertIn('if (event.key === "code-platform-auth")', SETTINGS_SOURCE)
        self.assertNotIn('event.key === "code-platform-auth" && event.newValue', SETTINGS_SOURCE)
        get_keys_start = APP_SOURCE.index("function getApiKeys()")
        get_keys_end = APP_SOURCE.index("function detectLanguage(", get_keys_start)
        get_keys_source = APP_SOURCE[get_keys_start:get_keys_end]
        self.assertIn("loadKeyConfig()", get_keys_source)
        self.assertNotIn("els.apiKey", get_keys_source)
        self.assertIn('id="apiKey"', INDEX_SOURCE)
        self.assertIn('autocomplete="off" hidden aria-hidden="true" tabindex="-1"', INDEX_SOURCE)

        script = r"""
const values = new Map([["code-key-config", JSON.stringify([
  {name: "old", key: "sk-old", enabled: true, source: "manual"},
])]]);
const storage = {
  getItem: (key) => values.has(key) ? values.get(key) : null,
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: (key) => values.delete(key),
};
let storageHandler = null;
let pageShowHandler = null;
let reloads = 0;
const keyList = {innerHTML: "", querySelectorAll: () => []};
const documentStub = {
  getElementById: (id) => id === "settingsKeyList" ? keyList : null,
  querySelectorAll: () => [],
  addEventListener: () => {},
};
global.window = {
  localStorage: storage,
  location: {search: "", reload: () => { reloads += 1; }},
  history: {replaceState: () => {}},
  matchMedia: () => ({matches: false, addEventListener: () => {}}),
  addEventListener: (type, handler) => {
    if (type === "storage") storageHandler = handler;
    if (type === "pageshow") pageShowHandler = handler;
  },
  setTimeout,
  setInterval,
  clearInterval,
};
require("./src/core/namespace.js");
require("./src/core/platform.js");
require("./src/features/settings.js");
const apiKey = {value: "old: sk-old"};
const feature = window.Code.features.settings.createSettingsFeature({
  elements: {apiKey},
  t: (key) => key,
  apiJson: async () => ({}),
  document: documentStub,
  storage,
});
feature.bind();
values.set("code-key-config", "[]");
apiKey.value = "restored-by-browser: sk-stale";
pageShowHandler();
const staleBrowserValueCleared = apiKey.value === "" && !keyList.innerHTML.includes("sk-stale");
values.set("code-key-config", JSON.stringify([
  {name: "replacement", key: "sk-replacement", enabled: true, source: "manual"},
]));
storageHandler({key: "code-key-config"});
const keyUpdated = apiKey.value === "replacement: sk-replacement";
const editorUpdated = keyList.innerHTML.includes("replacement");
storageHandler({key: "code-platform-auth", newValue: null});
process.stdout.write(JSON.stringify({staleBrowserValueCleared, keyUpdated, editorUpdated, reloads}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["staleBrowserValueCleared"])
        self.assertTrue(data["keyUpdated"])
        self.assertTrue(data["editorUpdated"])
        self.assertEqual(data["reloads"], 1)
        self.assertIn('syncKeysTitle: "从 workbar 获取 API Key"', I18N_SOURCE)
        self.assertIn('syncKeysTitle: "Get API Keys from workbar"', I18N_SOURCE)
        self.assertIn('allKeysAdded: "当前 Code 已添加全部 Key"', I18N_SOURCE)
        self.assertIn('detectAvailableModels: "重新检测可用模型"', I18N_SOURCE)
        self.assertIn(".key-sync-note.is-complete::before", STYLE_SOURCE)
        self.assertIn(".key-sync-card { width: min(720px, calc(100vw - 32px));", STYLE_SOURCE)
        self.assertIn("grid-template-columns: minmax(160px, 1.35fr) minmax(150px, 0.8fr) minmax(132px, auto);", STYLE_SOURCE)
        self.assertNotIn('class="key-connect-btn"', SETTINGS_SOURCE)
        self.assertNotIn('class="key-enable-label"', SETTINGS_SOURCE)

    def test_settings_panels_avoid_duplicate_refresh_and_preserve_async_state(self):
        switch_start = SETTINGS_SOURCE.index("function switchSettingsPanel(panel)")
        switch_end = SETTINGS_SOURCE.index("function openSettingsPage", switch_start)
        switch_source = SETTINGS_SOURCE[switch_start:switch_end]
        models_start = switch_source.index('case "models":')
        models_end = switch_source.index('case "account":', models_start)
        self.assertNotIn("refreshSettingsModelList()", switch_source[models_start:models_end])
        self.assertIn('addEventListener("click", refreshSettingsModelList)', SETTINGS_SOURCE)

        self.assertIn("let settingsSelectedSkillName = null", SKILLS_MEMORY_SOURCE)
        self.assertIn("function renderSettingsSkillsSidebar(preferredName = settingsSelectedSkillName)", SKILLS_MEMORY_SOURCE)
        self.assertIn("settingsSelectedSkillName = item.dataset.skillName", SKILLS_MEMORY_SOURCE)
        self.assertIn("renderSettingsSkillsSidebar(skill.name)", SKILLS_MEMORY_SOURCE)
        self.assertNotIn('sidebar.querySelector(".skill-list-item")?.classList.add("active")', SKILLS_MEMORY_SOURCE)

        memory_start = SKILLS_MEMORY_SOURCE.index("function renderMemoryPanel(container)")
        memory_end = SKILLS_MEMORY_SOURCE.index("function renderSkillsInSettings", memory_start)
        memory_source = SKILLS_MEMORY_SOURCE[memory_start:memory_end]
        self.assertNotIn("setTimeout(() => refreshSettingsMemoryList()", memory_source)
        self.assertIn("refreshSettingsMemoryList();", memory_source)
        self.assertIn('class="settings-memory-state is-loading"', memory_source)
        self.assertIn('id="settingsMemoryRetry"', memory_source)
        self.assertIn("requestId !== settingsMemoryRequestId", memory_source)
        self.assertIn(".settings-memory-state", STYLE_SOURCE)
        self.assertIn('loadingMemories: "正在加载记忆…"', I18N_SOURCE)
        self.assertIn('loadingMemories: "Loading memories…"', I18N_SOURCE)

    def test_skill_dependency_preflight_is_lazy_cached_and_visible_in_settings(self):
        render_start = SKILLS_MEMORY_SOURCE.index("function renderSkillsInSettings(container)")
        sidebar_start = SKILLS_MEMORY_SOURCE.index("function renderSettingsSkillsSidebar", render_start)
        render_source = SKILLS_MEMORY_SOURCE[render_start:sidebar_start]
        load_start = render_source.index("async function loadSkillDependencyStatus")
        load_source = render_source[load_start:]

        self.assertIn('id="settingsSkillDependencyOverview"', render_source)
        self.assertIn('id="settingsSkillDependencyRefresh"', render_source)
        self.assertIn('apiJson("/api/skills/dependencies")', load_source)
        self.assertIn("if (skillDependencySnapshot && !force) return skillDependencySnapshot", load_source)
        self.assertIn("if (!skillDependencySnapshot && !skillDependencyLoading) loadSkillDependencyStatus()", render_source)
        self.assertNotIn("/api/skills/dependencies", SKILLS_MEMORY_SOURCE[:render_start])

        detail_start = SKILLS_MEMORY_SOURCE.index("async function showSkillDetailInSettings", sidebar_start)
        detail_end = SKILLS_MEMORY_SOURCE.index("function bind()", detail_start)
        detail_source = SKILLS_MEMORY_SOURCE[detail_start:detail_end]
        self.assertIn("renderSkillDependencySection(skill.name)", detail_source)
        self.assertIn("skill-dependency-sidebar-status", SKILLS_MEMORY_SOURCE)

        for key in (
            "skillDependencyTitle",
            "skillDependencyCheck",
            "skillDependencyChecking",
            "skillDependencySummary",
            "skillDependencyProbeFailed",
            "skillDependencyReady",
            "skillDependencyPartial",
            "skillDependencyUnavailable",
        ):
            self.assertEqual(I18N_SOURCE.count(f"{key}:"), 2)

        for selector in (
            ".skill-dependency-overview",
            ".skill-dependency-sidebar-status",
            ".skill-dependency-card",
            ".skill-capability-row",
            ".skill-dependency-chip.is-missing.is-optional",
        ):
            self.assertIn(selector, STYLE_SOURCE)

    def test_skill_dependency_settings_operations_are_scoped_recoverable_and_localized(self):
        operation_start = SKILLS_MEMORY_SOURCE.index("function recalculateSkillDependencySummary")
        bind_start = SKILLS_MEMORY_SOURCE.index("function bindSkillDependencyInteractions", operation_start)
        operation_source = SKILLS_MEMORY_SOURCE[operation_start:bind_start]
        self.assertIn('apiJson("/api/skills/dependencies/plan"', operation_source)
        self.assertIn('apiJson("/api/skills/dependencies/operations"', operation_source)
        self.assertIn("fingerprint: preview.plan.fingerprint", operation_source)
        self.assertIn('method: "DELETE"', operation_source)
        self.assertIn("pollSkillDependencyOperation(operation.id)", operation_source)
        self.assertIn("operation.result.dependency", operation_source)
        self.assertIn("refreshSingleSkillDependencyStatus(operation.skill)", operation_source)
        self.assertIn("function recheckAndDismissSkillDependencyOperation", operation_source)
        self.assertIn("if (operation.dismissed) forgetDependencyOperation(operationId)", operation_source)
        self.assertIn('data-dependency-operation-recheck="${escapeHtml(operation.id)}"', SKILLS_MEMORY_SOURCE)
        self.assertNotIn("run_command", operation_source)

        self.assertIn("function renderDependencySystemHints(required)", SKILLS_MEMORY_SOURCE)
        self.assertIn("item.installHint || t(\"skillDependencySystemHintFallback\")", SKILLS_MEMORY_SOURCE)
        self.assertIn('data-dependency-action="install"', SKILLS_MEMORY_SOURCE)
        self.assertIn('data-dependency-action="repair"', SKILLS_MEMORY_SOURCE)
        self.assertIn('data-dependency-action="uninstall"', SKILLS_MEMORY_SOURCE)
        self.assertIn("loadSkillDependencyOperations();", SKILLS_MEMORY_SOURCE)
        self.assertIn("let skillDependencyOperationByKey = new Map()", SKILLS_MEMORY_SOURCE)
        self.assertIn("const managedRequirements = [...required, ...optional]", SKILLS_MEMORY_SOURCE)
        self.assertIn("const missingRequiredManaged = required", SKILLS_MEMORY_SOURCE)
        self.assertIn("const missingOptionalManaged = optional", SKILLS_MEMORY_SOURCE)
        self.assertIn('? "skillDependencyInstallOptional"', SKILLS_MEMORY_SOURCE)
        self.assertIn("const allRequiredManaged = capabilities.flatMap", SKILLS_MEMORY_SOURCE)
        self.assertIn('data-dependency-install-all', SKILLS_MEMORY_SOURCE)
        self.assertIn('openSkillDependencyPlan(skillName, "*", "install")', SKILLS_MEMORY_SOURCE)
        self.assertIn("settingsSelectedSkillName", operation_source)
        self.assertIn("renderSettingsSkillsSidebar(settingsSelectedSkillName)", operation_source)

        for key in (
            "skillDependencyInstall",
            "skillDependencyInstallOptional",
            "skillDependencyRepair",
            "skillDependencyUninstall",
            "skillDependencyPlanTitle",
            "skillDependencyAuthorizationManagedOnly",
            "skillDependencyOperationRunning",
            "skillDependencyOperationCompleted",
            "skillDependencyOperationCancelled",
            "skillDependencyRetryOperation",
            "skillDependencySystemHintTitle",
            "skillDependencySharedPreserved",
            "skillDependencyInstallAll",
            "skillDependencyAllManagedReady",
            "skillDependencyAllCapabilities",
            "skillDependencySystemExcluded",
        ):
            self.assertEqual(I18N_SOURCE.count(f"{key}:"), 2)

        for selector in (
            ".skill-dependency-capability-actions",
            ".skill-dependency-system-hints",
            ".skill-dependency-operation-plan",
            ".skill-dependency-operation-state",
            ".skill-dependency-progress",
            ".skill-dependency-operation-actions",
        ):
            self.assertIn(selector, STYLE_SOURCE)

    def test_skill_editor_can_save_validated_dependency_manifests(self):
        self.assertIn('id="skillDependencyEditor"', INDEX_SOURCE)
        self.assertIn('id="skillEditDependencies"', INDEX_SOURCE)
        self.assertIn('id="skillDependencyTemplate"', INDEX_SOURCE)
        self.assertIn('id="skillDependencyEditorNotice"', INDEX_SOURCE)
        self.assertIn("class=\"modal-card skill-editor-card\"", INDEX_SOURCE)
        self.assertIn("skill.dependencyCapabilities = full.dependencyCapabilities || {}", SKILLS_MEMORY_SOURCE)
        self.assertIn("JSON.stringify(dependencies, null, 2)", SKILLS_MEMORY_SOURCE)
        self.assertIn("dependencies = JSON.parse(dependencyText)", SKILLS_MEMORY_SOURCE)
        self.assertIn('originalName: editingSkillName || ""', SKILLS_MEMORY_SOURCE)
        self.assertIn("payload.dependencies = dependencies", SKILLS_MEMORY_SOURCE)
        self.assertIn('["detected", "bundled"].includes(editingSkillDependencySource)', SKILLS_MEMORY_SOURCE)
        self.assertNotIn(
            'apiJson(`/api/skills?name=${encodeURIComponent(editingSkillName)}`, { method: "DELETE" })',
            SKILLS_MEMORY_SOURCE,
        )
        self.assertIn("skillDependencySnapshot = null", SKILLS_MEMORY_SOURCE)
        self.assertIn("loadSkillDependencyStatus({ force: true })", SKILLS_MEMORY_SOURCE)
        for key in (
            "skillDependencyEditorTitle",
            "skillDependencyEditorHint",
            "skillDependencyEditorPlaceholder",
            "skillDependencyTemplate",
            "skillDependencyJsonInvalid",
            "skillDependencyManifestInvalid",
            "skillDependencyDetected",
            "skillDependencyDetectedEditorNotice",
        ):
            self.assertEqual(I18N_SOURCE.count(f"{key}:"), 2)
        for selector in (
            ".skill-editor-card",
            ".skill-dependency-editor",
            ".skill-dependency-json",
            ".skill-dependency-editor-error",
            ".skill-dependency-editor-notice",
            ".skill-dependency-source",
        ):
            self.assertIn(selector, STYLE_SOURCE)

    def test_skill_dependencies_gate_first_use_and_are_available_as_a_read_tool(self):
        self.assertIn('name: "check_skill_dependencies"', TOOLS_SOURCE)
        self.assertIn('"check_skill_dependencies"', PERMISSIONS_SOURCE)
        self.assertIn("before first use of this Skill", SKILLS_MEMORY_SOURCE)
        self.assertIn('capability: { type: "string"', TOOLS_SOURCE)
        self.assertIn("Choose only the capability needed by the current task", SKILLS_MEMORY_SOURCE)
        self.assertIn("Re-run check_skill_dependencies for the same selected capability", SKILLS_MEMORY_SOURCE)
        self.assertIn("System-command dependencies must be installed by the user outside Code", SKILLS_MEMORY_SOURCE)
        self.assertIn("Present supplied installHints verbatim", SKILLS_MEMORY_SOURCE)
        self.assertIn("never execute them, modify PATH, or create global command wrappers", SKILLS_MEMORY_SOURCE)
        self.assertEqual(I18N_SOURCE.count("toolCheckSkillDependencies:"), 2)

    def test_theme_picker_separates_mode_from_the_resolved_variant_list(self):
        start = SETTINGS_SOURCE.index("function renderThemePanel(container)")
        end = SETTINGS_SOURCE.index("function renderAccountPanel", start)
        source = SETTINGS_SOURCE[start:end]

        self.assertIn('class="tp-mode-switch"', source)
        self.assertIn('class="tp-mode-btn ${prefs.mode === mode ? "active" : ""}"', source)
        self.assertEqual(source.count('class="tp-variants"'), 1)
        self.assertNotIn('class="tp-mode-row"', source)
        self.assertNotIn('name="tp-mode"', source)
        self.assertIn('const resolvedMode = prefs.mode === "system"', source)
        self.assertIn('const visibleModes = prefs.mode === "system" ? ["light", "dark"] : [resolvedMode]', source)
        self.assertIn('data-tp-variant-mode="${mode}"', source)
        self.assertIn('applyTheme(prefs.mode, variantMode === "light"', source)

        for selector in (
            ".tp-mode-switch",
            ".tp-mode-btn.active",
            ".tp-variant-group + .tp-variant-group",
            ".tp-row--sel .tp-check",
        ):
            self.assertIn(selector, STYLE_SOURCE)
        for expected in (
            'themeMode: "外观模式"',
            'themeSchemes: "主题方案"',
            'themeMode: "Appearance mode"',
            'themeSchemes: "Theme schemes"',
        ):
            self.assertIn(expected, I18N_SOURCE)

    def test_markdown_ui_uses_one_source_preserving_render_pipeline(self):
        self.assertIn("Code.ui.markdown = Object.freeze", MARKDOWN_SOURCE)
        script = r"""
global.window = {
  Code: {ui: {}},
  katex: {
    renderToString: (math, options) => {
      if (math === "bad") throw new Error("invalid math");
      return `<katex data-display="${options.displayMode}">${math}</katex>`;
    },
  },
};
class Renderer {}
let configured = null;
let parsedSource = null;
const marked = {
  Renderer,
  setOptions: (options) => { configured = options; },
  parse: (source) => { parsedSource = source; return `<parsed>${source}</parsed>`; },
};
require("./src/ui/markdown.js");
const {createMarkdownFeature, resolveSyntaxPatterns} = window.Code.ui.markdown;
const feature = createMarkdownFeature({
  marked,
  random: () => 0.5,
  escapeHtml: (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;"),
  renderDiff: (text) => `<diff>${text}</diff>`,
});
feature.renderer.parser = {parseInline: (tokens) => tokens.map((token) => token.text).join("")};
const markdownInput = "Heading\n===\n\n---\n\nMath $x+1$, bad $bad$, and `$HOME`.\n\n```js\nconst price = '$5';\n````\n\nAfter $y+2$.";
process.stdout.write(JSON.stringify({
  javascript: feature.highlightSyntax('const value = "<x>"; // note', "javascript"),
  json: feature.highlightSyntax('{"name":"demo","ok":true,"count":2}', "json"),
  ansi: feature.renderAnsi('\u001b[1;31m<error>\u001b[0m'),
  code: feature.renderer.code({text: "const value = 1;", lang: "js"}),
  terminal: feature.renderer.code({text: '\u001b[32mok\u001b[0m', lang: "terminal"}),
  diff: feature.renderer.code({text: "+line", lang: "diff"}),
  pathCode: feature.renderer.codespan({text: "C:/work/a.py"}),
  plainCode: feature.renderer.codespan({text: "value"}),
  link: feature.renderer.link({href: "/docs", text: "docs", tokens: [{text: "docs"}]}),
  localImage: feature.renderer.image({href: "assets/demo.png", text: "local", title: null}),
  remoteImage: feature.renderer.image({href: "https://example.test/demo.png", text: "remote", title: null}),
  rendered: feature.renderMarkdownLite(markdownInput),
  parsedSource,
  aliasResolved: Array.isArray(resolveSyntaxPatterns("ts")),
  breaks: configured.breaks,
  gfm: configured.gfm,
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertIn('<span class="syn-kw">const</span>', data["javascript"])
        self.assertIn('&lt;x&gt;', data["javascript"])
        self.assertNotIn('-kw&quot;&gt;', data["javascript"])
        self.assertIn('<span class="syn-key">&quot;name&quot;</span>', data["json"])
        self.assertIn('<span class="syn-kw">true</span>', data["json"])
        self.assertEqual(
            data["ansi"],
            '<span class="ansi-1"><span class="ansi-31">&lt;error&gt;</span></span>',
        )
        self.assertIn('class="copy-code"', data["code"])
        self.assertIn('class="line-no">1</span>', data["code"])
        self.assertIn('class="ansi-block"', data["terminal"])
        self.assertEqual(data["diff"], "<diff>+line</diff>")
        self.assertIn('class="clickable-path"', data["pathCode"])
        self.assertEqual(data["plainCode"], "<code>value</code>")
        self.assertIn('target="_blank" rel="noopener"', data["link"])
        self.assertIn('/api/file?path=assets%2Fdemo.png&amp;raw=1', data["localImage"])
        self.assertIn('class="msg-inline-img"', data["localImage"])
        self.assertIn('class="msg-inline-img-slot"', data["localImage"])
        self.assertIn('src="https://example.test/demo.png"', data["remoteImage"])
        self.assertIn("Heading\n===", data["parsedSource"])
        self.assertIn("\n---\n", data["parsedSource"])
        self.assertNotIn("\\===", data["parsedSource"])
        self.assertNotIn("$x+1$", data["parsedSource"])
        self.assertNotIn("$y+2$", data["parsedSource"])
        self.assertIn("`$HOME`", data["parsedSource"])
        self.assertIn("const price = '$5';", data["parsedSource"])
        self.assertIn('class="math-inline"', data["rendered"])
        self.assertIn('<katex data-display="false">x+1</katex>', data["rendered"])
        self.assertIn('<katex data-display="false">y+2</katex>', data["rendered"])
        self.assertIn("$bad$", data["rendered"])
        self.assertTrue(data["aliasResolved"])
        self.assertTrue(data["breaks"])
        self.assertTrue(data["gfm"])

    def test_structured_markdown_preserves_task_list_and_table_semantics(self):
        script = r"""
global.window = {Code: {ui: {}}};
class Renderer {}
let configured = null;
const marked = {
  Renderer,
  setOptions(options) { configured = options; },
  parse: () => "",
};
require("./src/ui/markdown.js");
const feature = window.Code.ui.markdown.createMarkdownFeature({
  marked,
  escapeHtml: (value) => String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;"),
});
const renderer = feature.renderer;
const parser = {
  parseInline(tokens) {
    return (tokens || []).map((token) => {
      if (token.type === "checkbox") return renderer.checkbox.call(renderer, token);
      return String(token.text || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }).join("");
  },
  parse(tokens) {
    return (tokens || []).map((token) => {
      if (token.type === "checkbox") return renderer.checkbox.call(renderer, token);
      if (token.type === "list") return renderer.list.call(renderer, token);
      if (token.type === "paragraph" || token.type === "text") {
        return parser.parseInline(token.tokens || [token]);
      }
      return "";
    }).join("");
  },
};
renderer.parser = parser;
const taskList = renderer.list.call(renderer, {
  ordered: false,
  start: "",
  items: [
    {
      task: true,
      checked: true,
      tokens: [
        {type: "checkbox", checked: true},
        {type: "text", text: "已完成", tokens: [{type: "text", text: "已完成"}]},
      ],
    },
    {
      task: true,
      checked: false,
      tokens: [
        {
          type: "paragraph",
          text: "待处理长文本",
          tokens: [
            {type: "checkbox", checked: false},
            {type: "text", text: "待处理长文本"},
          ],
        },
        {
          type: "list",
          ordered: true,
          start: 3,
          items: [{task: false, tokens: [{type: "text", text: "嵌套项目", tokens: [{type: "text", text: "嵌套项目"}]}]}],
        },
      ],
    },
  ],
});
const ordinaryList = renderer.list.call(renderer, {
  ordered: true,
  start: 4,
  items: [{task: false, tokens: [{type: "text", text: "普通项目", tokens: [{type: "text", text: "普通项目"}]}]}],
});
const table = renderer.table.call(renderer, {
  header: [
    {align: "left", tokens: [{type: "text", text: "左 & 列"}]},
    {align: "center", tokens: [{type: "text", text: "中列"}]},
    {align: "right", tokens: [{type: "text", text: "右列"}]},
  ],
  rows: [[
    {align: "left", tokens: [{type: "text", text: "A < B"}]},
    {align: "center", tokens: [{type: "text", text: "中"}]},
    {align: "right", tokens: [{type: "text", text: "42"}]},
  ]],
});
process.stdout.write(JSON.stringify({
  taskList,
  ordinaryList,
  table,
  gfm: configured.gfm,
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        task_list = data["taskList"]
        self.assertIn('class="md-list md-list-unordered task-list"', task_list)
        self.assertEqual(task_list.count('class="task-list-item"'), 2)
        self.assertEqual(task_list.count('class="task-list-checkbox"'), 2)
        self.assertEqual(task_list.count('type="checkbox" disabled checked'), 1)
        self.assertEqual(task_list.count('type="checkbox" disabled aria-labelledby='), 1)
        self.assertIn('data-task-state="checked"', task_list)
        self.assertIn('data-task-state="unchecked"', task_list)
        self.assertIn('aria-labelledby="md-task-content-1"', task_list)
        self.assertIn('aria-labelledby="md-task-content-2"', task_list)
        self.assertIn('class="md-list md-list-ordered" start="3"', task_list)
        self.assertEqual(task_list.count("已完成"), 1)
        self.assertEqual(task_list.count("待处理长文本"), 1)
        self.assertIn('class="md-list md-list-ordered" start="4"', data["ordinaryList"])
        self.assertNotIn("task-list-item", data["ordinaryList"])
        self.assertIn('align="left" data-align="left" class="md-align-left"', data["table"])
        self.assertIn('align="center" data-align="center" class="md-align-center"', data["table"])
        self.assertIn('align="right" data-align="right" class="md-align-right"', data["table"])
        self.assertIn("左 &amp; 列", data["table"])
        self.assertIn("A &lt; B", data["table"])
        self.assertIn('class="table-scroll" tabindex="-1"', data["table"])
        self.assertIn('class="table-overflow-hint" aria-hidden="true">↔', data["table"])
        self.assertTrue(data["gfm"])

        self.assertIn(".md-list .md-list", STYLE_SOURCE)
        self.assertIn("pointer-events:none", STYLE_SOURCE)
        self.assertIn('.table-wrap[data-overflow="true"] .table-overflow-hint', STYLE_SOURCE)
        self.assertIn("overscroll-behavior-inline:contain", STYLE_SOURCE)
        self.assertIn("th.md-align-center", STYLE_SOURCE)
        self.assertIn("td.md-align-right", STYLE_SOURCE)

    def test_structured_table_binding_only_focuses_real_overflow(self):
        start = APP_SOURCE.index("let _structuredTableFrame = 0;")
        end = APP_SOURCE.index("// Inline images degrade", start)
        source = APP_SOURCE[start:end]
        script = f"""
const source = {json.dumps(source)};
const narrowScroll = {{scrollWidth: 240, clientWidth: 240, tabIndex: 99}};
const wideScroll = {{scrollWidth: 640, clientWidth: 320, tabIndex: 99}};
const narrowWrap = {{dataset: {{}}, querySelector: () => narrowScroll}};
const wideWrap = {{dataset: {{}}, querySelector: () => wideScroll}};
let resizeBindings = 0;
let frames = 0;
global.document = {{querySelectorAll: (selector) => selector === ".table-wrap" ? [narrowWrap, wideWrap] : []}};
global.window = {{
  requestAnimationFrame(callback) {{ frames += 1; callback(); return frames; }},
  addEventListener(type) {{ if (type === "resize") resizeBindings += 1; }},
}};
eval(source);
bindStructuredMarkdownTables();
bindStructuredMarkdownTables();
process.stdout.write(JSON.stringify({{
  narrowOverflow: narrowWrap.dataset.overflow,
  narrowTabIndex: narrowScroll.tabIndex,
  wideOverflow: wideWrap.dataset.overflow,
  wideTabIndex: wideScroll.tabIndex,
  resizeBindings,
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["narrowOverflow"], "false")
        self.assertEqual(data["narrowTabIndex"], -1)
        self.assertEqual(data["wideOverflow"], "true")
        self.assertEqual(data["wideTabIndex"], 0)
        self.assertEqual(data["resizeBindings"], 1)

    def test_plain_file_cards_are_lightweight_without_changing_image_cards(self):
        file_card = re.search(r"\.path-file-card\{([^}]+)\}", STYLE_SOURCE)
        image_card = re.search(r"\.path-image-card\{([^}]+)\}", STYLE_SOURCE)
        self.assertIsNotNone(file_card)
        self.assertIsNotNone(image_card)
        file_style = file_card.group(1)
        image_style = image_card.group(1)

        for expected in (
            "display:inline-flex",
            "align-items:center",
            "gap:4px",
            "background:transparent",
            "border:0",
            "border-radius:0",
            "padding:0 1px 0 0",
            "vertical-align:baseline",
            "cursor:pointer",
        ):
            self.assertIn(expected, file_style)
        for removed in (
            "background:var(--panel)",
            "border:1px solid var(--line)",
            "border-radius:8px",
            "padding:3px 10px 3px 6px",
        ):
            self.assertNotIn(removed, file_style)

        for preserved in (
            "background:var(--panel)",
            "border:1px solid var(--line)",
            "border-radius:8px",
            "padding:4px 10px 4px 4px",
            "vertical-align:middle",
        ):
            self.assertIn(preserved, image_style)
        self.assertIn('card.className = "path-file-card";', APP_SOURCE)
        self.assertIn('card.className = "path-image-card";', APP_SOURCE)
        self.assertIn("card.addEventListener(\"click\"", APP_SOURCE)
        self.assertIn("openReferencedPath(p, projectRoot);", APP_SOURCE)
        self.assertIn("showLinkContextMenu", APP_SOURCE)

    def test_markdown_cjk_bare_url_boundaries_preserve_markdown_regions(self):
        script = r"""
global.window = {Code: {ui: {}}};
require("./src/ui/markdown.js");
const markdown = window.Code.ui.markdown;
const project = markdown.projectCjkBareUrlBoundaries;
const original = "推荐 https://yuanbao.tencent.com）（再看 https://xinghuo.xfyun.cn、最后 https://mistral.ai。";
const query = "查询 https://example.com/a?q=hello&lang=zh#part，编码 https://example.com/%E4%B8%AD%E6%96%87。";
const consecutive = "https://a.example、https://b.example；https://c.example：https://d.example！https://e.example…";
const explicit = "[说明 https://label.example。](https://target.example/中文?q=1)";
const image = "![图 https://alt.example。](https://images.example/中文.png)";
const angle = "<https://angle.example/中文>";
const inlineCode = "`https://code.example。`";
const fencedCode = "```text\nhttps://fence.example。\n```";
const rawHtml = '<a href="https://html.example/中文">链接</a>';
const plainAscii = "https://ascii.example/a?q=hello#part next";
const unicodeHanPath = "https://example.com/中文";
const unicodeHangulPath = "https://example.com/한글";
const unicodeKanaPath = "https://example.com/かな";
const unpunctuatedHanText = "https://example.com后续正文";

let configured = null;
class Renderer {}
const marked = {
  Renderer,
  setOptions(options) { configured = options; },
  parse(source) {
    return String(source).replace(/<(https?:\/\/[^<>\s]+)>/gi, (_raw, href) => configured.renderer.link.call({
      parser: {parseInline: (tokens) => tokens.map((token) => token.text).join("")},
    }, {href, text: href, tokens: [{type: "text", text: href}], title: null}));
  },
};
const feature = markdown.createMarkdownFeature({
  marked,
  escapeHtml: (value) => String(value)
    .replaceAll("&", "&amp;")
    .replaceAll('<', "&lt;")
    .replaceAll('>', "&gt;")
    .replaceAll('"', "&quot;"),
});
const rendered = feature.renderMarkdownLite(original);
process.stdout.write(JSON.stringify({
  original: project(original),
  query: project(query),
  consecutive: project(consecutive),
  explicit: project(explicit),
  image: project(image),
  angle: project(angle),
  inlineCode: project(inlineCode),
  fencedCode: project(fencedCode),
  rawHtml: project(rawHtml),
  plainAscii: project(plainAscii),
  unicodeHanPath: project(unicodeHanPath),
  unicodeHangulPath: project(unicodeHangulPath),
  unicodeKanaPath: project(unicodeKanaPath),
  unpunctuatedHanText: project(unpunctuatedHanText),
  rendered,
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(
            data["original"],
            "推荐 <https://yuanbao.tencent.com>）（再看 "
            "<https://xinghuo.xfyun.cn>、最后 <https://mistral.ai>。",
        )
        self.assertEqual(
            data["query"],
            "查询 <https://example.com/a?q=hello&lang=zh#part>，编码 "
            "<https://example.com/%E4%B8%AD%E6%96%87>。",
        )
        self.assertEqual(
            data["consecutive"],
            "<https://a.example>、<https://b.example>；"
            "<https://c.example>：<https://d.example>！<https://e.example>…",
        )
        self.assertEqual(
            data["explicit"],
            "[说明 https://label.example。](https://target.example/中文?q=1)",
        )
        self.assertEqual(
            data["image"],
            "![图 https://alt.example。](https://images.example/中文.png)",
        )
        self.assertEqual(data["angle"], "<https://angle.example/中文>")
        self.assertEqual(data["inlineCode"], "`https://code.example。`")
        self.assertEqual(data["fencedCode"], "```text\nhttps://fence.example。\n```")
        self.assertEqual(data["rawHtml"], '<a href="https://html.example/中文">链接</a>')
        self.assertEqual(data["plainAscii"], "https://ascii.example/a?q=hello#part next")
        self.assertEqual(data["unicodeHanPath"], "https://example.com/中文")
        self.assertEqual(data["unicodeHangulPath"], "https://example.com/한글")
        self.assertEqual(data["unicodeKanaPath"], "https://example.com/かな")
        self.assertEqual(data["unpunctuatedHanText"], "https://example.com后续正文")
        self.assertEqual(data["rendered"].count('class="ext-link"'), 3)
        for href in (
            "https://yuanbao.tencent.com",
            "https://xinghuo.xfyun.cn",
            "https://mistral.ai",
        ):
            self.assertIn(f'href="{href}"', data["rendered"])
        self.assertIn('target="_blank" rel="noopener"', data["rendered"])
        self.assertNotIn("%EF%BC", data["rendered"])

    def test_diff_ui_owns_normalization_stats_rendering_and_edit_cards(self):
        self.assertIn("Code.ui.diff = Object.freeze", DIFF_SOURCE)
        script = r"""
global.window = {Code: {ui: {}}};
require("./src/ui/diff.js");
const {createDiffFeature, isEditSuggestionMessage} = window.Code.ui.diff;
const escapeHtml = (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
let pendingEdits = {};
let authorizationRequests = [];
let permissionProfile = "accept";
const feature = createDiffFeature({
  escapeHtml,
  highlightSyntax: (value, lang) => `<hl data-lang="${lang}">${escapeHtml(value)}</hl>`,
  renderMarkdown: (value) => `<md>${escapeHtml(value)}</md>`,
  renderCopyButton: (value) => `<copy>${escapeHtml(value)}</copy>`,
  t: (key) => key,
  getMessageText: (msg) => String(msg.content || ""),
  getPendingEdits: () => pendingEdits,
  getAuthorizationRequests: () => authorizationRequests,
  getPermissionProfile: () => permissionProfile,
});
const raw = `Preamble that must be removed
\`\`\`diff
--- a/src/demo.js
+++ b/src/demo.js
@@ -1,2 +1,2 @@
-const oldValue = "<old>";
+const newValue = "<new>";
 context
\`\`\`
Trailing prose`;
const normalized = feature.normalizeDiffText(raw);
const stats = feature.getDiffStats(raw);
const rendered = feature.renderDiff(raw);
const longDiff = [
  "--- a/src/long.js",
  "+++ b/src/long.js",
  "@@ -1,41 +1,41 @@",
  ...Array.from({length: 41}, (_, index) => ` line-${index + 1}`),
].join("\n");
const message = {
  role: "tool-result",
  content: raw,
  meta: {pendingEditId: "edit-1", action: "propose_edit", path: "src/<demo>.js"},
};
const pendingCard = feature.renderEditSuggestionProjection(message, 7);
authorizationRequests = [{status: "pending", editId: "edit-1"}];
const queuedCard = feature.renderEditSuggestionProjection(message, 7);
authorizationRequests = [];
pendingEdits = {"edit-1": {applied: true}};
const appliedCard = feature.renderEditSuggestionProjection(message, 7);
const noChangesCard = feature.renderEditSuggestionProjection({
  role: "tool-result",
  content: "(no changes)",
  meta: {pendingEditId: "edit-2", action: "propose_edit"},
}, 8);
process.stdout.write(JSON.stringify({
  normalized,
  stats,
  rendered,
  longRendered: feature.renderDiff(longDiff),
  pendingCard,
  queuedCard,
  appliedCard,
  noChangesCard,
  isEdit: isEditSuggestionMessage(message),
  isNotEdit: isEditSuggestionMessage({role: "assistant", meta: {pendingEditId: "edit-1"}}),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["normalized"].startswith("--- a/src/demo.js"))
        self.assertNotIn("Preamble", data["normalized"])
        self.assertNotIn("Trailing prose", data["normalized"])
        self.assertEqual(data["stats"], {"additions": 1, "removals": 1, "lineCount": 6})
        self.assertIn('class="diff-line diff-header"', data["rendered"])
        self.assertIn('class="diff-line diff-hunk"', data["rendered"])
        self.assertIn('class="diff-line diff-remove"', data["rendered"])
        self.assertIn('class="diff-line diff-add"', data["rendered"])
        self.assertIn('data-lang="js"', data["rendered"])
        self.assertIn("&lt;new&gt;", data["rendered"])
        self.assertNotIn("<new>", data["rendered"])
        self.assertIn("is-collapsed", data["longRendered"])
        self.assertIn("expandDiff", data["longRendered"])
        self.assertIn("src/&lt;demo&gt;.js", data["pendingCard"])
        self.assertIn('class="diff-stat diff-stat-add">+1', data["pendingCard"])
        self.assertIn('class="diff-stat diff-stat-remove">−1', data["pendingCard"])
        self.assertIn('class="apply-edit-btn"', data["pendingCard"])
        self.assertIn('class="reject-edit-btn"', data["pendingCard"])
        self.assertIn("pendingConfirmation", data["pendingCard"])
        self.assertIn("waitingApproval", data["queuedCard"])
        self.assertNotIn('class="apply-edit-btn"', data["queuedCard"])
        self.assertIn("is-applied", data["appliedCard"])
        self.assertIn("appliedLabel", data["appliedCard"])
        self.assertNotIn('class="apply-edit-btn"', data["appliedCard"])
        self.assertEqual(data["noChangesCard"], "")
        self.assertTrue(data["isEdit"])
        self.assertFalse(data["isNotEdit"])

    def test_edit_diff_disclosure_is_transient_independent_and_accessible(self):
        script = r"""
global.window = {Code: {ui: {}}};
require("./src/ui/diff.js");
const {createDiffFeature, createEditDiffDisclosureState} = window.Code.ui.diff;
const escapeHtml = (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
const disclosure = createEditDiffDisclosureState();
disclosure.setSession("session-a");
let pendingEdits = {};
let authorizationRequests = [];
const feature = createDiffFeature({
  escapeHtml,
  highlightSyntax: (value) => escapeHtml(value),
  renderMarkdown: (value) => `<md>${escapeHtml(value)}</md>`,
  renderCopyButton: () => "<copy></copy>",
  t: (key, vars = {}) => vars.count == null ? key : `${key}:${vars.count}`,
  getMessageText: (msg) => String(msg.content || ""),
  getPendingEdits: () => pendingEdits,
  getAuthorizationRequests: () => authorizationRequests,
  getPermissionProfile: () => "accept",
  isEditDiffExpanded: (editId) => disclosure.isExpanded(editId),
  isEditDiffFullyExpanded: (editId) => disclosure.isFullyExpanded(editId),
});
const shortDiff = [
  "--- a/demo.txt",
  "+++ b/demo.txt",
  "@@ -1 +1 @@",
  "-old",
  "+new",
].join("\n");
const edit = (id, overrides = {}) => ({
  role: "tool-result",
  content: shortDiff,
  meta: {pendingEditId: id, action: "propose_edit", path: `${id}.txt`, ...overrides},
});
const defaultCard = feature.renderEditSuggestionProjection(edit("edit-1"), 4);
disclosure.setExpanded("edit-1", true);
const expandedCard = feature.renderEditSuggestionProjection(edit("edit-1"), 4);
authorizationRequests = [{status: "pending", editId: "edit-1"}];
const waitingCard = feature.renderEditSuggestionProjection(edit("edit-1"), 4);
authorizationRequests = [];
pendingEdits = {"edit-1": {applied: true}};
const appliedCard = feature.renderEditSuggestionProjection(edit("edit-1", {applied: true}), 4);
pendingEdits = {};
const rejectedCard = feature.renderEditSuggestionProjection(edit("edit-1", {rejected: true}), 4);
const failedCard = feature.renderEditSuggestionProjection(edit("edit-1", {outcome: "failed"}), 4);
const independentCard = feature.renderEditSuggestionProjection(edit("edit-2"), 5);
const writeCard = feature.renderEditSuggestionProjection({
  role: "tool-result",
  content: "first\nsecond",
  meta: {pendingEditId: "edit-write", action: "write_file", path: "created.txt"},
}, 6);
const markdownCard = feature.renderEditSuggestionProjection({
  role: "tool-result",
  content: "Plain edit explanation without a Diff body.",
  meta: {pendingEditId: "edit-markdown", action: "propose_edit", path: "plain.txt"},
}, 7);
const longDiff = [
  "--- a/long.txt",
  "+++ b/long.txt",
  "@@ -1,41 +1,41 @@",
  ...Array.from({length: 41}, (_, index) => ` line-${index + 1}`),
].join("\n");
disclosure.setExpanded("edit-long", true);
const boundedLongCard = feature.renderEditSuggestionProjection({
  role: "tool-result",
  content: longDiff,
  meta: {pendingEditId: "edit-long", action: "propose_edit", path: "long.txt"},
}, 7);
disclosure.setFullyExpanded("edit-long", true);
const fullLongCard = feature.renderEditSuggestionProjection({
  role: "tool-result",
  content: longDiff,
  meta: {pendingEditId: "edit-long", action: "propose_edit", path: "long.txt"},
}, 7);
const sameSessionKept = disclosure.setSession("session-a");
const beforeSwitch = disclosure.snapshot();
const switched = disclosure.setSession("session-b");
const afterSwitch = disclosure.snapshot();
process.stdout.write(JSON.stringify({
  defaultCard,
  expandedCard,
  waitingCard,
  appliedCard,
  rejectedCard,
  failedCard,
  independentCard,
  writeCard,
  markdownCard,
  boundedLongCard,
  fullLongCard,
  sameSessionKept,
  beforeSwitch,
  switched,
  afterSwitch,
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertIn("data-edit-diff-toggle", data["defaultCard"])
        self.assertIn('aria-expanded="false"', data["defaultCard"])
        self.assertIn("data-edit-diff-body hidden", data["defaultCard"])
        self.assertIn('class="apply-edit-btn"', data["defaultCard"])
        self.assertIn('class="reject-edit-btn"', data["defaultCard"])
        self.assertIn('aria-controls="edit-diff-edit-1-4"', data["defaultCard"])
        self.assertIn('aria-expanded="true"', data["expandedCard"])
        self.assertNotIn("data-edit-diff-body hidden", data["expandedCard"])
        self.assertIn('aria-expanded="true"', data["waitingCard"])
        self.assertIn('aria-expanded="true"', data["appliedCard"])
        self.assertIn('aria-expanded="true"', data["rejectedCard"])
        self.assertIn('aria-expanded="true"', data["failedCard"])
        self.assertIn("is-rejected", data["rejectedCard"])
        self.assertIn('aria-expanded="false"', data["independentCard"])
        self.assertIn("data-edit-diff-body hidden", data["independentCard"])
        self.assertIn('aria-expanded="false"', data["writeCard"])
        self.assertIn("write-file-preview", data["writeCard"])
        self.assertNotIn("data-edit-diff-toggle", data["markdownCard"])
        self.assertNotIn("data-edit-diff-body", data["markdownCard"])
        self.assertIn("tool-edit-markdown", data["markdownCard"])
        self.assertIn('class="code-block diff-block is-collapsed"', data["boundedLongCard"])
        self.assertIn("expandDiff:44", data["boundedLongCard"])
        self.assertIn('class="code-block diff-block is-expanded"', data["fullLongCard"])
        self.assertIn("collapseDiff", data["fullLongCard"])
        self.assertFalse(data["sameSessionKept"])
        self.assertEqual(data["beforeSwitch"], {
            "sessionId": "session-a",
            "expanded": ["edit-1", "edit-long"],
            "fullyExpanded": ["edit-long"],
        })
        self.assertTrue(data["switched"])
        self.assertEqual(data["afterSwitch"], {
            "sessionId": "session-b",
            "expanded": [],
            "fullyExpanded": [],
        })

        self.assertIn("editDiffDisclosureState.setSession(state.sessionId);", APP_SOURCE)
        self.assertIn("editDiffDisclosureState.setExpanded(id, nextExpanded);", APP_SOURCE)
        self.assertIn("editDiffDisclosureState.setFullyExpanded(editId, expanded);", APP_SOURCE)
        self.assertGreaterEqual(
            APP_SOURCE.count("messageScrollController?.onContentChanged(state.sessionId);"),
            5,
        )
        self.assertIn(".tool-edit-diff[hidden]", STYLE_SOURCE)
        self.assertIn(".edit-diff-toggle:focus-visible", STYLE_SOURCE)
        self.assertIn('expandEditDiff: "查看 Diff"', I18N_SOURCE)
        self.assertIn('collapseEditDiff: "Collapse Diff"', I18N_SOURCE)

    def test_server_edit_instance_identity_separates_repeated_proposals(self):
        script = r"""
global.window = {Code: {ui: {}}};
require("./src/ui/diff.js");
const {
  createDiffFeature,
  createEditDiffDisclosureState,
  getEditSuggestionInstanceId,
} = window.Code.ui.diff;
const sharedPendingId = "server-edit-shared-proposal";
const metaA = {
  pendingEditId: sharedPendingId,
  serverManaged: true,
  authorizationId: "authorization-a",
  agentRunId: "run-a",
  toolCallId: "call-shared",
};
const metaB = {
  pendingEditId: sharedPendingId,
  serverManaged: true,
  authorizationId: "authorization-b",
  agentRunId: "run-b",
  toolCallId: "call-shared",
};
const instanceA = getEditSuggestionInstanceId(metaA);
const instanceB = getEditSuggestionInstanceId(metaB);
const disclosure = createEditDiffDisclosureState();
disclosure.setSession("session-repeated");
disclosure.setExpanded(instanceA, true);
let pendingEdits = {
  [instanceA]: {rejected: true, resolved: true},
};
let authorizationRequests = [{status: "pending", editId: instanceB}];
const escapeHtml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");
const feature = createDiffFeature({
  escapeHtml,
  t: (key) => key,
  getMessageText: (message) => String(message.content || ""),
  getPendingEdits: () => pendingEdits,
  getAuthorizationRequests: () => authorizationRequests,
  getPermissionProfile: () => "accept",
  isEditDiffExpanded: (editId) => disclosure.isExpanded(editId),
  isEditDiffFullyExpanded: (editId) => disclosure.isFullyExpanded(editId),
});
const diff = [
  "--- a/same.txt",
  "+++ b/same.txt",
  "@@ -1 +1 @@",
  "-old",
  "+new",
].join("\n");
const render = (meta, index) => feature.renderEditSuggestionProjection({
  role: "tool-result",
  content: diff,
  meta: {action: "propose_edit", path: "same.txt", ...meta},
}, index);
const rejectedA = render(metaA, 4);
const waitingB = render(metaB, 9);
disclosure.setExpanded(instanceB, true);
authorizationRequests = [];
pendingEdits = {
  ...pendingEdits,
  [instanceB]: {applied: true, resolved: true},
};
const appliedB = render({...metaB, applied: true}, 9);
process.stdout.write(JSON.stringify({
  instanceA,
  instanceB,
  sameInstanceA: getEditSuggestionInstanceId({...metaA}) === instanceA,
  historicalFallback: getEditSuggestionInstanceId({
    pendingEditId: sharedPendingId,
    serverManaged: true,
    agentRunId: "old-run",
    toolCallId: "old-call",
  }),
  finalFallback: getEditSuggestionInstanceId({
    pendingEditId: sharedPendingId,
    serverManaged: true,
  }),
  localIdentity: getEditSuggestionInstanceId({
    pendingEditId: "local-edit",
    serverManaged: false,
    authorizationId: "ignored-authorization",
  }),
  rejectedA,
  waitingB,
  appliedB,
  disclosure: disclosure.snapshot(),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["instanceA"], "server-edit-authorization-authorization-a")
        self.assertEqual(data["instanceB"], "server-edit-authorization-authorization-b")
        self.assertNotEqual(data["instanceA"], data["instanceB"])
        self.assertTrue(data["sameInstanceA"])
        self.assertEqual(
            data["historicalFallback"],
            "server-edit-call-old-run-old-call",
        )
        self.assertEqual(data["finalFallback"], "server-edit-shared-proposal")
        self.assertEqual(data["localIdentity"], "local-edit")
        self.assertIn('data-edit-id="server-edit-authorization-authorization-a"', data["rejectedA"])
        self.assertIn('aria-expanded="true"', data["rejectedA"])
        self.assertIn("is-rejected", data["rejectedA"])
        self.assertIn('data-edit-id="server-edit-authorization-authorization-b"', data["waitingB"])
        self.assertIn('aria-expanded="false"', data["waitingB"])
        self.assertIn("waitingApproval", data["waitingB"])
        self.assertNotIn("is-rejected", data["waitingB"])
        self.assertIn('aria-expanded="true"', data["appliedB"])
        self.assertIn("is-applied", data["appliedB"])
        self.assertEqual(
            data["disclosure"]["expanded"],
            [
                "server-edit-authorization-authorization-a",
                "server-edit-authorization-authorization-b",
            ],
        )

        self.assertIn("getEditSuggestionInstanceId(projection.meta) || pendingEditId", APP_SOURCE)
        self.assertIn("message.meta?.agentRunId === ctx.agentRunId", APP_SOURCE)
        self.assertIn("projection.meta.authorizationId = authorizationId;", APP_SOURCE)
        self.assertIn("restored.editId = getEditSuggestionInstanceId({", APP_SOURCE)
        self.assertIn("serverManaged: restored.serverAgent === true", APP_SOURCE)
        self.assertEqual(
            APP_SOURCE.count("getEditSuggestionInstanceId(projection.meta) || pendingEditId"),
            2,
        )

    def test_authorization_view_reveals_edit_diff_without_mutating_authorization(self):
        helper_start = APP_SOURCE.index("let authorizationViewHighlightTimer")
        helper_end = APP_SOURCE.index("function bindCopyButtons", helper_start)
        helper_source = APP_SOURCE[helper_start:helper_end]
        script = f"""
const vm = require("node:vm");
const label = {{dataset: {{}}, textContent: ""}};
const attrs = new Map([
  ["aria-controls", "edit-diff-edit-1-4"],
  ["aria-expanded", "false"],
]);
const button = {{
  dataset: {{editId: "edit-1"}},
  title: "",
  getAttribute(name) {{ return attrs.get(name) || ""; }},
  setAttribute(name, value) {{ attrs.set(name, String(value)); }},
  querySelector(selector) {{ return selector === "[data-edit-diff-label]" ? label : null; }},
}};
const body = {{hidden: true}};
const classes = new Set();
let scrollOptions = null;
const target = {{
  querySelector(selector) {{ return selector === ".edit-diff-toggle" ? button : null; }},
  scrollIntoView(options) {{ scrollOptions = options; }},
  classList: {{
    add(value) {{ classes.add(value); }},
    remove(value) {{ classes.delete(value); }},
    contains(value) {{ return classes.has(value); }},
  }},
}};
let targetPresent = false;
const messages = {{
  querySelector() {{ return targetPresent ? target : null; }},
  querySelectorAll() {{ return classes.has("is-authorization-view-target") ? [target] : []; }},
}};
const stateCalls = [];
let layoutCalls = 0;
let timerSequence = 0;
const timers = new Map();
const context = {{
  String,
  Boolean,
  CSS: {{escape: (value) => String(value)}},
  els: {{messages}},
  document: {{getElementById: (id) => id === "edit-diff-edit-1-4" ? body : null}},
  editDiffDisclosureState: {{
    setExpanded(editId, expanded) {{ stateCalls.push([editId, expanded]); }},
  }},
  messageScrollController: {{onContentChanged() {{ layoutCalls += 1; }}}},
  state: {{sessionId: "session-a"}},
  t: (key) => `label:${{key}}`,
  setTimeout(callback, delay) {{
    timerSequence += 1;
    timers.set(timerSequence, {{callback, delay}});
    return timerSequence;
  }},
  clearTimeout(timerId) {{ timers.delete(timerId); }},
}};
vm.createContext(context);
vm.runInContext({json.dumps(helper_source)}, context);
const missing = context.revealAuthorizationEdit("missing");
const missingSnapshot = {{stateCalls: stateCalls.length, layoutCalls, timers: timers.size}};
targetPresent = true;
const revealed = context.revealAuthorizationEdit("edit-1");
const revealTimer = timers.get(timerSequence);
const revealedSnapshot = {{
  stateCalls: [...stateCalls],
  layoutCalls,
  bodyHidden: body.hidden,
  ariaExpanded: attrs.get("aria-expanded"),
  ariaLabel: attrs.get("aria-label"),
  labelKey: label.dataset.i18n,
  labelText: label.textContent,
  scrollOptions,
  highlighted: classes.has("is-authorization-view-target"),
  timerDelay: revealTimer?.delay || 0,
}};
revealTimer.callback();
const highlightedAfterTimer = classes.has("is-authorization-view-target");
context.setRenderedEditDiffExpanded("edit-1", false);
process.stdout.write(JSON.stringify({{
  missing,
  missingSnapshot,
  revealed,
  revealedSnapshot,
  highlightedAfterTimer,
  collapsed: {{
    stateCalls,
    layoutCalls,
    bodyHidden: body.hidden,
    ariaExpanded: attrs.get("aria-expanded"),
    ariaLabel: attrs.get("aria-label"),
    labelKey: label.dataset.i18n,
    labelText: label.textContent,
  }},
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertFalse(data["missing"])
        self.assertEqual(data["missingSnapshot"], {
            "stateCalls": 0,
            "layoutCalls": 0,
            "timers": 0,
        })
        self.assertTrue(data["revealed"])
        self.assertEqual(data["revealedSnapshot"], {
            "stateCalls": [["edit-1", True]],
            "layoutCalls": 0,
            "bodyHidden": False,
            "ariaExpanded": "true",
            "ariaLabel": "label:collapseEditDiff",
            "labelKey": "collapseEditDiff",
            "labelText": "label:collapseEditDiff",
            "scrollOptions": {"behavior": "smooth", "block": "center"},
            "highlighted": True,
            "timerDelay": 1400,
        })
        self.assertFalse(data["highlightedAfterTimer"])
        self.assertEqual(data["collapsed"], {
            "stateCalls": [["edit-1", True], ["edit-1", False]],
            "layoutCalls": 1,
            "bodyHidden": True,
            "ariaExpanded": "false",
            "ariaLabel": "label:expandEditDiff",
            "labelKey": "expandEditDiff",
            "labelText": "label:expandEditDiff",
        })
        self.assertIn("revealAuthorizationEdit(viewButton.dataset.authView);", APP_SOURCE)
        self.assertIn("return;", APP_SOURCE[
            APP_SOURCE.index('const viewButton = event.target.closest("[data-auth-view]");'):
            APP_SOURCE.index("function toolProgressSummary", helper_end)
        ])
        for forbidden in (
            "authorizationRequests",
            "resolveAuthorization",
            "renderAuthorizationPanel",
            ".selected",
        ):
            self.assertNotIn(forbidden, helper_source)
        self.assertIn(
            ".edit-suggestion.is-authorization-view-target .tool-edit-card",
            STYLE_SOURCE,
        )
        self.assertIn(
            ".edit-suggestion.is-authorization-view-target .tool-edit-head",
            STYLE_SOURCE,
        )
        self.assertIn("color-mix(in srgb, var(--accent) 26%, transparent)", STYLE_SOURCE)

    def test_messages_ui_owns_grouping_projection_and_response_status(self):
        self.assertIn("Code.ui.messages = Object.freeze", MESSAGES_SOURCE)
        for obsolete in (
            "function renderUserProjection(",
            "function renderThinkingProjection(",
            "function renderFinalAssistantProjection(",
            "function renderCompletedRunStatus(",
            "function renderBackgroundReplyReference(",
            "const TOOL_DISPLAY =",
            "function _isToolError(",
            "function _toolStatusLabel(",
            "function _toolStatusClass(",
            "function _toolTarget(",
            "function _toolResultSummary(",
            "function renderToolMessage(",
            "function renderToolSection(",
        ):
            self.assertNotIn(obsolete, APP_SOURCE)
        self.assertIn("function _toolActionLabel(action)", APP_SOURCE)
        self.assertIn("getToolActionLabel: _toolActionLabel", APP_SOURCE)
        self.assertNotIn("window.copyMessageText", APP_SOURCE)
        self.assertIn("bindMessageInteractions(els.messageList)", APP_SOURCE)
        script = r"""
global.window = {Code: {ui: {}}};
require("./src/ui/messages.js");
const {createMessagesFeature} = window.Code.ui.messages;
const escapeHtml = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
let messages = [];
const feature = createMessagesFeature({
  escapeHtml,
  formatCompact: (value) => String(value),
  renderMarkdown: (value) => `<md>${escapeHtml(value)}</md>`,
  t: (key, vars = {}) => vars.count == null ? key : `${key}:${vars.count}`,
  getMessageText: (msg) => String(msg?.content || ""),
  getBackgroundJob: (id) => id === "job-1" ? {status: "running"} : null,
  getMessages: () => messages,
  getSessionId: () => "session-1",
  getSelectedModel: () => "model-1",
  renderNetworkRecoveryStatus: () => "<recovery></recovery>",
  renderAssistantContent: (value) => `<answer>${escapeHtml(value)}</answer>`,
  renderBranchFlow: (title) => `<branch>${escapeHtml(title)}</branch>`,
  isEditSuggestionMessage: (msg) => Boolean(msg?.meta?.edit),
  renderEditSuggestion: (_msg, index) => `<edit data-index="${index}"></edit>`,
  getToolActionLabel: (action) => `label:${action}`,
});
messages = [
  {role: "user", content: "run <task>", meta: {backgroundDispatch: {id: "job-1"}}},
  {role: "assistant", content: "inspect **project**", thought: "secret reasoning", meta: {toolCalls: [{id: "call-1", function: {name: "read_file", arguments: '{"path":"README.md"}'}}]}},
  {role: "tool-call", content: "hidden tool", meta: {action: "read_file", toolCallId: "call-1", tool: {action: "read_file", path: "README.md"}}},
  {role: "tool-result", content: "legacy failure text", meta: {action: "read_file", toolCallId: "call-1", outcome: "failed", result: {ok: false, errorCode: "invalid_tool_arguments", error: "missing path"}}},
  {role: "assistant", content: "inspect **project**", meta: {toolCalls: [{id: "call-2", function: {name: "read_file", arguments: '{"path":"README.md"}'}}]}},
  {role: "tool-call", content: "hidden tool again", meta: {action: "read_file", toolCallId: "call-2", tool: {action: "read_file", path: "README.md"}}},
  {role: "tool-result", content: "legacy failure text", meta: {action: "read_file", toolCallId: "call-2", outcome: "failed", result: {ok: false, errorCode: "invalid_tool_arguments", error: "missing path"}}},
  {role: "assistant", content: "done", _model: "model-1", meta: {_usage: {input: 12, output: 3}}, _responseTime: "4s"},
  {role: "assistant", content: "background done", meta: {kind: "background-subagent", jobId: "job-1", _usage: {input: 2}}},
  {role: "tool-result", content: "diff", meta: {edit: true}},
  {role: "assistant", content: "hidden internal", meta: {_system: true}},
];
const html = feature.projectMessages(messages, {
  hasActiveRun: true,
  branchMarker: {messageCount: 1, parentTitle: "Parent"},
});
const completedHtml = feature.projectMessages(messages, {
  hasActiveRun: false,
});
const simpleCompletedHtml = feature.projectMessages([
  {role: "user", content: "simple"},
  {role: "assistant", content: "simple answer", _responseTime: "1s"},
], {hasActiveRun: false});
const compactSummaryHtml = feature.projectMessages([
  {role: "user", content: "visible old task"},
  {role: "assistant", content: "visible old answer", _responseTime: "1s"},
  {role: "assistant", content: "hidden compact summary", meta: {kind: "compact-summary", compressed: 12}},
  {role: "user", content: "recent task"},
  {role: "assistant", content: "recent answer", _responseTime: "1s"},
], {hasActiveRun: false});
const activeTraceMessages = [
  {role: "user", content: "active trace"},
  {role: "assistant", content: "checkpoint", meta: {toolCalls: [
    {id: "active-1", function: {name: "run_command", arguments: '{"command":"git status --short"}'}},
  ]}},
  {role: "tool-call", meta: {action: "run_command", toolCallId: "active-1", tool: {action: "run_command", command: "git status --short"}}},
  {role: "tool-result", content: "clean", meta: {action: "run_command", toolCallId: "active-1", outcome: "succeeded"}},
  {role: "assistant", content: "first final chunk", streaming: true, _streamProjection: "answer"},
];
const activeAnswerHtml = feature.projectMessages(activeTraceMessages, {
  hasActiveRun: true,
});
const collapsedActiveAnswerHtml = feature.projectMessages(activeTraceMessages, {
  hasActiveRun: true,
  collapsedExecutionTraces: new Set(["0"]),
});
const activeThinkingHtml = feature.projectMessages([
  {role: "user", content: "active thinking"},
  {role: "assistant", content: "checkpoint", meta: {toolCalls: [
    {id: "thinking-1", function: {name: "read_file", arguments: '{"path":"README.md"}'}},
  ]}},
  {role: "tool-call", meta: {action: "read_file", toolCallId: "thinking-1", tool: {action: "read_file", path: "README.md"}}},
  {role: "tool-result", content: "contents", meta: {action: "read_file", toolCallId: "thinking-1", outcome: "succeeded"}},
  {role: "assistant", content: "next checkpoint", streaming: true, _streamProjection: "thinking"},
], {hasActiveRun: true});
const emptyRecoveryHtml = feature.projectMessages([
  {role: "user", content: "empty recovery"},
  {role: "assistant", content: "", meta: {toolCalls: [
    {id: "empty-1", function: {name: "run_command", arguments: '{"command":"git status --short"}'}},
  ]}},
  {role: "tool-call", meta: {action: "run_command", toolCallId: "empty-1", tool: {action: "run_command", command: "git status --short"}}},
  {role: "tool-result", content: "clean", meta: {action: "run_command", toolCallId: "empty-1", outcome: "succeeded"}},
  {role: "assistant", content: " ", streaming: true, _streamProjection: "pending"},
], {hasActiveRun: true});
const operationalHtml = feature.projectMessages([
  {role: "user", content: "inspect"},
  {role: "assistant", content: "正在读取 README.md…\n正在执行 git status --short…", meta: {toolCalls: [
    {id: "notice-1", function: {name: "read_file", arguments: '{"path":"README.md"}'}},
  ]}},
  {role: "tool-call", meta: {action: "read_file", toolCallId: "notice-1", tool: {action: "read_file", path: "README.md"}}},
  {role: "tool-result", content: "file contents", meta: {action: "read_file", toolCallId: "notice-1", outcome: "succeeded"}},
  {role: "assistant", content: "meaningful checkpoint", meta: {toolCalls: [
    {id: "notice-2", function: {name: "run_command", arguments: '{"command":"git status --short"}'}},
  ]}},
  {role: "tool-call", meta: {action: "run_command", toolCallId: "notice-2", tool: {action: "run_command", command: "git status --short"}}},
  {role: "tool-result", content: "clean", meta: {action: "run_command", toolCallId: "notice-2", outcome: "succeeded"}},
  {role: "assistant", content: "done", _responseTime: "2s"},
], {hasActiveRun: false});
const groupedStageHtml = feature.projectMessages([
  {role: "user", content: "inspect"},
  {role: "assistant", content: "正在读取 README.md…", meta: {toolCalls: [
    {id: "group-1", function: {name: "read_file", arguments: '{"path":"README.md"}'}},
  ]}},
  {role: "tool-call", meta: {action: "read_file", toolCallId: "group-1", tool: {action: "read_file", path: "README.md"}}},
  {role: "tool-result", content: "file contents", meta: {action: "read_file", toolCallId: "group-1", outcome: "succeeded"}},
  {role: "assistant", content: "正在执行 git status --short…", meta: {toolCalls: [
    {id: "group-2", function: {name: "run_command", arguments: '{"command":"git status --short"}'}},
  ]}},
  {role: "tool-call", meta: {action: "run_command", toolCallId: "group-2", tool: {action: "run_command", command: "git status --short"}}},
  {role: "tool-result", content: "clean", meta: {action: "run_command", toolCallId: "group-2", outcome: "succeeded"}},
  {role: "assistant", content: "done", _responseTime: "2s"},
], {hasActiveRun: false});
const activeCompletedTailMessages = [
  {role: "user", content: "active tool stage"},
  {role: "assistant", content: "", meta: {toolCalls: [
    {id: "active-tail-1", function: {name: "read_file", arguments: '{"path":"README.md"}'}},
    {id: "active-tail-2", function: {name: "run_command", arguments: '{"command":"git status --short"}'}},
  ]}},
  {role: "tool-call", meta: {action: "read_file", toolCallId: "active-tail-1", tool: {action: "read_file", path: "README.md"}}},
  {role: "tool-result", content: "contents", meta: {action: "read_file", toolCallId: "active-tail-1", outcome: "succeeded"}},
  {role: "tool-call", meta: {action: "run_command", toolCallId: "active-tail-2", tool: {action: "run_command", command: "git status --short"}}},
  {role: "tool-result", content: "clean", meta: {action: "run_command", toolCallId: "active-tail-2", outcome: "succeeded"}},
];
const activeCompletedTailHtml = feature.projectMessages(activeCompletedTailMessages, {hasActiveRun: true});
const expandedActiveTailHtml = feature.projectMessages(activeCompletedTailMessages, {
  hasActiveRun: true,
  expandedToolProcesses: new Set(["0:1"]),
});
const completedCollapsedTailHtml = feature.projectMessages(activeCompletedTailMessages, {
  hasActiveRun: false,
  expandedToolProcesses: new Set(["0:1"]),
});
const activeSeparatedStagesHtml = feature.projectMessages([
  {role: "user", content: "active separated stages"},
  {role: "assistant", content: "", meta: {toolCalls: [
    {id: "separated-1", function: {name: "read_file", arguments: '{"path":"README.md"}'}},
    {id: "separated-1b", function: {name: "run_command", arguments: '{"command":"git status --short"}'}},
  ]}},
  {role: "tool-call", meta: {action: "read_file", toolCallId: "separated-1", tool: {action: "read_file", path: "README.md"}}},
  {role: "tool-result", content: "contents", meta: {action: "read_file", toolCallId: "separated-1", outcome: "succeeded"}},
  {role: "tool-call", meta: {action: "run_command", toolCallId: "separated-1b", tool: {action: "run_command", command: "git status --short"}}},
  {role: "tool-result", content: "clean", meta: {action: "run_command", toolCallId: "separated-1b", outcome: "succeeded"}},
  {role: "assistant", content: "checkpoint between stages", meta: {toolCalls: [
    {id: "separated-2", function: {name: "run_command", arguments: '{"command":"git status --short"}'}},
  ]}},
  {role: "tool-call", meta: {action: "run_command", toolCallId: "separated-2", tool: {action: "run_command", command: "git status --short"}}},
  {role: "tool-result", content: "clean", meta: {action: "run_command", toolCallId: "separated-2", outcome: "succeeded"}},
], {hasActiveRun: true});
const activeToolGapMessages = [
  {role: "user", content: "active multi-round tool stage"},
  {role: "assistant", content: "", meta: {toolCalls: [
    {id: "gap-1", function: {name: "read_file", arguments: '{"path":"README.md"}'}},
  ]}},
  {role: "tool-call", meta: {action: "read_file", toolCallId: "gap-1", tool: {action: "read_file", path: "README.md"}}},
  {role: "tool-result", content: "contents", meta: {action: "read_file", toolCallId: "gap-1", outcome: "succeeded"}},
  {role: "assistant", content: "reviewing the first result"},
];
const activeToolGapHtml = feature.projectMessages(activeToolGapMessages, {
  hasActiveRun: true,
  expandedToolProcesses: new Set(["session-1:gap-1"]),
  expandedToolItems: new Set(["session-1:gap-1:gap-1"]),
});
const activeFailedToolGapMessages = [
  {role: "user", content: "active failed tool stage"},
  {role: "assistant", content: "", meta: {toolCalls: [
    {id: "failed-gap-1", function: {name: "read_file", arguments: '{"path":"missing.txt"}'}},
  ]}},
  {role: "tool-call", meta: {action: "read_file", toolCallId: "failed-gap-1", tool: {action: "read_file", path: "missing.txt"}}},
  {role: "tool-result", content: "missing", meta: {action: "read_file", toolCallId: "failed-gap-1", outcome: "failed", result: {ok: false, error: "missing"}}},
  {role: "assistant", content: "trying a safe alternative"},
];
const activeFailedToolGapHtml = feature.projectMessages(activeFailedToolGapMessages, {
  hasActiveRun: true,
  expandedToolProcesses: new Set(["session-1:failed-gap-1"]),
  expandedToolItems: new Set(["session-1:failed-gap-1:failed-gap-1"]),
});
const activeFailedThenRetryHtml = feature.projectMessages([
  {role: "user", content: "retry after a failed tool"},
  {role: "assistant", content: "", meta: {toolCalls: [
    {id: "failed-gap-1", function: {name: "read_file", arguments: '{"path":"missing.txt"}'}},
  ]}},
  {role: "tool-call", meta: {action: "read_file", toolCallId: "failed-gap-1", tool: {action: "read_file", path: "missing.txt"}}},
  {role: "tool-result", content: "missing", meta: {action: "read_file", toolCallId: "failed-gap-1", outcome: "failed", result: {ok: false, error: "missing"}}},
  {role: "assistant", content: "", meta: {toolCalls: [
    {id: "failed-gap-2", function: {name: "read_file", arguments: '{"path":"README.md"}'}},
  ]}},
  {role: "tool-call", meta: {action: "read_file", toolCallId: "failed-gap-2", tool: {action: "read_file", path: "README.md"}}},
], {
  hasActiveRun: true,
  expandedToolProcesses: new Set(["session-1:failed-gap-1"]),
  expandedToolItems: new Set([
    "session-1:failed-gap-1:failed-gap-1",
    "session-1:failed-gap-1:failed-gap-2",
  ]),
});
const activeQuestionnaireWaitingHtml = feature.projectMessages([
  {role: "user", content: "ask before continuing"},
  {role: "assistant", content: "", meta: {toolCalls: [
    {id: "questionnaire-gap-1", function: {name: "request_user_input", arguments: '{"questions":[]}' }},
  ]}},
  {role: "tool-call", meta: {
    action: "request_user_input",
    toolCallId: "questionnaire-gap-1",
    tool: {action: "request_user_input"},
  }},
], {
  hasActiveRun: true,
  expandedToolProcesses: new Set(["session-1:questionnaire-gap-1"]),
  expandedToolItems: new Set(["session-1:questionnaire-gap-1:questionnaire-gap-1"]),
});
const activeAuthorizationWaitingHtml = feature.projectMessages([
  {role: "user", content: "authorize before continuing"},
  {role: "assistant", content: "", meta: {toolCalls: [
    {id: "authorization-gap-1", function: {name: "propose_edit", arguments: '{"path":"src/a.js"}' }},
  ]}},
  {role: "tool-call", meta: {
    action: "propose_edit",
    toolCallId: "authorization-gap-1",
    tool: {action: "propose_edit", path: "src/a.js"},
  }},
], {
  hasActiveRun: true,
  expandedToolProcesses: new Set(["session-1:authorization-gap-1"]),
  expandedToolItems: new Set(["session-1:authorization-gap-1:authorization-gap-1"]),
});
const autoCompactionHtml = feature.projectMessages([
  {role: "user", content: "continue a long task"},
  {role: "assistant", content: "checkpoint", meta: {toolCalls: [
    {id: "compact-tool-1", function: {name: "read_file", arguments: '{"path":"README.md"}'}},
  ]}},
  {role: "tool-call", meta: {action: "read_file", toolCallId: "compact-tool-1", tool: {action: "read_file", path: "README.md"}}},
  {role: "tool-result", content: "contents", meta: {action: "read_file", toolCallId: "compact-tool-1", outcome: "succeeded"}},
  {role: "assistant", content: "", meta: {kind: "auto-context-compaction", status: "completed"}},
  {role: "assistant", content: "final after compaction", _responseTime: "3s"},
], {hasActiveRun: false});
const manualCompactionRunningHtml = feature.projectMessages([
  {role: "user", content: "manual compact task"},
  {role: "assistant", content: "manual compact answer", _responseTime: "2s"},
  {role: "assistant", content: "", meta: {kind: "manual-context-compaction", status: "running", skipApi: true}},
], {hasActiveRun: false});
const manualCompactionCompletedHtml = feature.projectMessages([
  {role: "user", content: "manual compact task"},
  {role: "assistant", content: "manual compact answer", _responseTime: "2s"},
  {role: "assistant", content: "", meta: {kind: "manual-context-compaction", status: "completed", skipApi: true}},
], {hasActiveRun: false});
const manualCompactionFailedHtml = feature.projectMessages([
  {role: "user", content: "manual compact task"},
  {role: "assistant", content: "manual compact answer", _responseTime: "2s"},
  {role: "assistant", content: "", meta: {kind: "manual-context-compaction", status: "failed", skipApi: true}},
], {hasActiveRun: false});
const manualCompactionFailedPersistenceHtml = feature.projectMessages([
  {role: "user", content: "manual compact task"},
  {role: "assistant", content: "", meta: {
    kind: "manual-context-compaction",
    status: "failed",
    errorStage: "compact_request",
    errorCode: "compact_request_failed",
    persistenceStatus: "failed",
    persistenceErrorCode: "session_save_failed",
    compactionId: "d3d3d3d3-2222-4333-8444-555555555555",
    skipApi: true,
  }},
], {hasActiveRun: false});
const runningStage = feature.renderToolProcessProjection([
  {msg: {role: "assistant", meta: {toolCalls: [
    {id: "running-1", function: {name: "read_file", arguments: '{"path":"README.md"}'}},
    {id: "running-2", function: {name: "run_command", arguments: '{"command":"git status --short"}'}},
  ]}}, index: 1},
  {msg: {role: "tool-call", meta: {action: "read_file", toolCallId: "running-1", tool: {action: "read_file", path: "README.md"}}}, index: 2},
  {msg: {role: "tool-result", content: "file contents", meta: {action: "read_file", toolCallId: "running-1", outcome: "succeeded"}}, index: 3},
  {msg: {role: "tool-call", meta: {action: "run_command", toolCallId: "running-2", tool: {action: "run_command", command: "git status --short"}}}, index: 4},
], 9);
const completedCommands = feature.renderToolProcessProjection([
  {msg: {role: "assistant", meta: {toolCalls: [
    {id: "command-1", function: {name: "run_command", arguments: '{"command":"node --check app.js"}'}},
    {id: "command-2", function: {name: "run_command", arguments: '{"command":"git status --short"}'}},
  ]}}, index: 1},
  {msg: {role: "tool-call", meta: {action: "run_command", toolCallId: "command-1", tool: {action: "run_command", command: "node --check app.js"}}}, index: 2},
  {msg: {role: "tool-result", content: "ok", meta: {action: "run_command", toolCallId: "command-1", outcome: "succeeded"}}, index: 3},
  {msg: {role: "tool-call", meta: {action: "run_command", toolCallId: "command-2", tool: {action: "run_command", command: "git status --short"}}}, index: 4},
  {msg: {role: "tool-result", content: "clean", meta: {action: "run_command", toolCallId: "command-2", outcome: "succeeded"}}, index: 5},
], 10);
const completedEdits = feature.renderToolProcessProjection([
  {msg: {role: "assistant", meta: {toolCalls: [
    {id: "edit-1", function: {name: "write_file", arguments: '{"path":"src/a.js","content":"a"}'}},
    {id: "edit-2", function: {name: "propose_edit", arguments: '{"path":"src/b.js"}'}},
  ]}}, index: 1},
  {msg: {role: "tool-call", meta: {action: "write_file", toolCallId: "edit-1", tool: {action: "write_file", path: "src/a.js"}}}, index: 2},
  {msg: {role: "tool-result", content: "saved", meta: {action: "write_file", toolCallId: "edit-1", outcome: "succeeded"}}, index: 3},
  {msg: {role: "tool-call", meta: {action: "propose_edit", toolCallId: "edit-2", tool: {action: "propose_edit", path: "src/b.js"}}}, index: 4},
  {msg: {role: "tool-result", content: "applied", meta: {action: "propose_edit", toolCallId: "edit-2", outcome: "succeeded"}}, index: 5},
], 11);
const cancelledCommand = feature.renderToolProcessProjection([
  {msg: {role: "assistant", meta: {toolCalls: [
    {id: "cancelled-1", function: {name: "run_command", arguments: '{"command":"node slow.js"}'}},
    {id: "cancelled-2", function: {name: "read_file", arguments: '{"path":"README.md"}'}},
  ]}}, index: 1},
  {msg: {role: "tool-call", meta: {action: "run_command", toolCallId: "cancelled-1", tool: {action: "run_command", command: "node slow.js"}}}, index: 2},
  {msg: {role: "tool-result", content: "Command cancelled.", meta: {action: "run_command", toolCallId: "cancelled-1", outcome: "failed", result: {ok: false, cancelled: true, error: "Command cancelled."}}}, index: 3},
  {msg: {role: "tool-result", content: "Tool call cancelled before execution.", meta: {action: "read_file", toolCallId: "cancelled-2", outcome: "failed", result: {ok: false, cancelled: true, cancelledBeforeStart: true, error: "Tool call cancelled before execution."}}}, index: 4},
], 12);
const streaming = feature.renderFinalAssistantProjection({
  role: "assistant",
  content: "streaming answer",
  streaming: true,
  _streamProjection: "answer",
}, 9);
const pending = feature.renderFinalAssistantProjection({
  role: "assistant",
  content: "unclassified first frame",
  streaming: true,
  _streamProjection: "pending",
}, 10);
const commentary = feature.renderFinalAssistantProjection({
  role: "assistant",
  content: "stable checkpoint",
  streaming: true,
  _streamProjection: "thinking",
}, 11);
const englishOperational = feature.renderFinalAssistantProjection({
  role: "assistant",
  content: "Reading README.md...",
  streaming: true,
  _streamProjection: "thinking",
}, 12);
const usageOnly = feature.renderCompletedRunStatus("model-1", "", {input: 8});
const claudeUsage = feature.normalizeResponseUsage({
  input_tokens: 12,
  output_tokens: 4,
  cache_read_input_tokens: 100,
  cache_creation_input_tokens: 3,
});
const openAIUsage = feature.normalizeResponseUsage({
  prompt_tokens: 100,
  completion_tokens: 4,
  prompt_tokens_details: {cached_tokens: 80},
});
const cacheStatus = feature.renderCompletedRunStatus("model-1", "", {
  input: 115,
  output: 4,
  cache: 100,
  cacheWrite: 3,
});
process.stdout.write(JSON.stringify({
  html,
  completedHtml,
  simpleCompletedHtml,
  compactSummaryHtml,
  activeAnswerHtml,
  collapsedActiveAnswerHtml,
  activeThinkingHtml,
  emptyRecoveryHtml,
  operationalHtml,
  groupedStageHtml,
  activeCompletedTailHtml,
  expandedActiveTailHtml,
  completedCollapsedTailHtml,
  activeSeparatedStagesHtml,
  activeToolGapHtml,
  activeFailedToolGapHtml,
  activeFailedThenRetryHtml,
  activeQuestionnaireWaitingHtml,
  activeAuthorizationWaitingHtml,
  autoCompactionHtml,
  manualCompactionRunningHtml,
  manualCompactionCompletedHtml,
  manualCompactionFailedHtml,
  manualCompactionFailedPersistenceHtml,
  runningStage,
  completedCommands,
  completedEdits,
  cancelledCommand,
  streaming,
  pending,
  commentary,
  englishOperational,
  usageOnly,
  claudeUsage,
  openAIUsage,
  cacheStatus,
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        html = data["html"]
        completed_html = data["completedHtml"]
        self.assertLess(html.index("run &lt;task&gt;"), html.index("data-active-run-anchor"))
        self.assertLess(html.index("data-active-run-anchor"), html.index("<branch>Parent</branch>"))
        first_commentary = html.index("<answer>inspect **project**</answer>")
        first_process = html.index("tool-process", first_commentary)
        second_commentary = html.index("<answer>inspect **project**</answer>", first_commentary + 1)
        second_process = html.index("tool-process", second_commentary)
        self.assertLess(html.index("<branch>Parent</branch>"), first_commentary)
        self.assertLess(first_commentary, first_process)
        self.assertLess(first_process, second_commentary)
        self.assertLess(second_commentary, second_process)
        self.assertLess(second_process, html.index("<answer>done</answer>"))
        self.assertLess(html.index("<answer>done</answer>"), html.index("background-reply-reference"))
        self.assertLess(html.index("background-reply-reference"), html.index("<edit data-index=\"9\">"))
        self.assertIn("backgroundRunning", html)
        self.assertIn("inspect **project**", html)
        self.assertIn("label:read_file", html)
        self.assertIn("README.md", html)
        self.assertIn("missing path", html)
        self.assertEqual(html.count('class="tool-process-item failed"'), 2)
        self.assertGreaterEqual(html.count("<details"), 2)
        self.assertNotIn("<details open", html)
        self.assertNotIn("toolProcessRepeated:2", html)
        self.assertNotIn("toolProcessTitle", html)
        self.assertIn("toolProcessArguments", html)
        self.assertIn("toolProcessResult", html)
        self.assertNotIn("secret reasoning", html)
        self.assertIn("background done", html)
        self.assertNotIn("<compact", data["compactSummaryHtml"])
        self.assertNotIn("hidden compact summary", data["compactSummaryHtml"])
        self.assertIn("visible old task", data["compactSummaryHtml"])
        self.assertIn("visible old answer", data["compactSummaryHtml"])
        self.assertIn("recent answer", data["compactSummaryHtml"])
        self.assertNotIn("hidden tool", html)
        self.assertNotIn("<md>inspect", html)
        self.assertNotIn("hidden internal", html)
        self.assertIn('data-stream-session="session-1"', data["streaming"])
        self.assertIn('data-stream-kind="answer"', data["streaming"])
        self.assertIn("<recovery></recovery>", data["streaming"])
        self.assertIn('data-stream-kind="pending"', data["pending"])
        self.assertNotIn("unclassified first frame", data["pending"])
        self.assertIn('data-stream-kind="thinking"', data["commentary"])
        self.assertIn("stable checkpoint", data["commentary"])
        self.assertNotIn('class="role', data["commentary"])
        self.assertNotIn("msg-footer", data["commentary"])
        self.assertIn('data-completed-run-status', completed_html)
        self.assertIn('class="completed-run-label">completedElapsedLabel</span>', completed_html)
        self.assertEqual(completed_html.count("4s"), 1)
        self.assertLess(completed_html.index("run &lt;task&gt;"), completed_html.index("data-completed-run-status"))
        self.assertIn('class="execution-trace completed"', completed_html)
        self.assertIn('data-execution-trace="0"', completed_html)
        self.assertNotIn('class="execution-trace completed is-expanded"', completed_html)
        trace_start = completed_html.index('class="execution-trace completed"')
        trace_body = completed_html.index('class="execution-trace-body"', trace_start)
        first_trace_commentary = completed_html.index("<answer>inspect **project**</answer>")
        first_trace_tools = completed_html.index("data-tool-process-block", first_trace_commentary)
        final_answer = completed_html.index("<answer>done</answer>")
        trace_end = completed_html.rfind("</section>", trace_body, final_answer)
        self.assertLess(completed_html.index("data-completed-run-status"), trace_body)
        self.assertLess(trace_body, first_trace_commentary)
        self.assertLess(first_trace_commentary, first_trace_tools)
        self.assertLess(first_trace_tools, trace_end)
        self.assertLess(trace_end, final_answer)
        auto_compaction_html = data["autoCompactionHtml"]
        auto_trace_body = auto_compaction_html.index('class="execution-trace-body"')
        auto_marker = auto_compaction_html.index("data-context-compaction")
        auto_final = auto_compaction_html.index("final after compaction")
        auto_trace_end = auto_compaction_html.rfind("</section>", auto_trace_body, auto_final)
        self.assertLess(auto_trace_body, auto_marker)
        self.assertLess(auto_marker, auto_trace_end)
        self.assertLess(auto_trace_end, auto_final)
        self.assertIn("autoCompactedContext", auto_compaction_html)
        manual_running_html = data["manualCompactionRunningHtml"]
        manual_completed_html = data["manualCompactionCompletedHtml"]
        manual_failed_html = data["manualCompactionFailedHtml"]
        manual_failed_persistence_html = data["manualCompactionFailedPersistenceHtml"]
        self.assertNotIn("execution-trace", manual_running_html)
        self.assertIn('class="context-compaction-row msg running"', manual_running_html)
        self.assertIn('data-context-compaction-mode="manual"', manual_running_html)
        self.assertIn("manualCompactingContext", manual_running_html)
        self.assertLess(manual_running_html.index("manual compact answer"), manual_running_html.index("data-context-compaction"))
        self.assertIn('class="context-compaction-row msg completed"', manual_completed_html)
        self.assertIn("manualCompactedContext", manual_completed_html)
        self.assertIn('class="context-compaction-row msg failed"', manual_failed_html)
        self.assertIn("manualCompactContextFailed", manual_failed_html)
        self.assertIn(
            'class="context-compaction-row msg failed warning"',
            manual_failed_persistence_html,
        )
        self.assertIn(
            "manualCompactFailurePersistenceFailed",
            manual_failed_persistence_html,
        )
        self.assertIn("data-manual-compaction-retry", manual_failed_persistence_html)
        self.assertNotIn("manualCompactedContext", manual_failed_persistence_html)
        self.assertNotIn(
            ">manualCompactPersistenceFailed<",
            manual_failed_persistence_html,
        )
        self.assertNotIn("execution-trace", data["simpleCompletedHtml"])
        self.assertIn("data-completed-run-status", data["simpleCompletedHtml"])
        active_answer_html = data["activeAnswerHtml"]
        self.assertIn('class="execution-trace active is-expanded"', active_answer_html)
        self.assertIn('data-execution-trace="0"', active_answer_html)
        self.assertIn('class="execution-trace active is-expanded"', active_answer_html)
        active_trace_start = active_answer_html.index('class="execution-trace active is-expanded"')
        active_summary = active_answer_html.index('class="execution-trace-summary"', active_trace_start)
        active_anchor = active_answer_html.index("data-active-run-anchor", active_summary)
        active_body = active_answer_html.index('class="execution-trace-body"', active_anchor)
        active_commentary = active_answer_html.index("checkpoint", active_body)
        active_tools = active_answer_html.index("data-tool-process-block", active_commentary)
        active_final = active_answer_html.index("first final chunk")
        active_trace_end = active_answer_html.rfind("</section>", active_tools, active_final)
        self.assertLess(active_summary, active_anchor)
        self.assertLess(active_anchor, active_body)
        self.assertLess(active_body, active_commentary)
        self.assertLess(active_commentary, active_tools)
        self.assertLess(active_tools, active_trace_end)
        self.assertLess(active_trace_end, active_final)
        self.assertIn('class="execution-trace active"', data["collapsedActiveAnswerHtml"])
        self.assertNotIn(
            'class="execution-trace active is-expanded"',
            data["collapsedActiveAnswerHtml"],
        )
        self.assertIn(
            'class="execution-trace active is-expanded"',
            data["activeThinkingHtml"],
        )
        self.assertLess(
            data["activeThinkingHtml"].index("data-active-run-anchor"),
            data["activeThinkingHtml"].index("checkpoint"),
        )
        self.assertIn("next checkpoint", data["activeThinkingHtml"])
        self.assertIn(
            'class="execution-trace active is-expanded"',
            data["emptyRecoveryHtml"],
        )
        self.assertLess(
            data["emptyRecoveryHtml"].index("data-active-run-anchor"),
            data["emptyRecoveryHtml"].index("data-tool-process-block"),
        )
        pending_tail_summary = data["emptyRecoveryHtml"].split('<div class="tool-process-stage-body">', 1)[0]
        self.assertIn('class="tool-process-stage running single-tool"', pending_tail_summary)
        self.assertNotIn("tool-active", pending_tail_summary)
        self.assertIn(
            "<strong>label:run_command</strong><code>git status --short</code>",
            pending_tail_summary,
        )
        self.assertNotIn("toolProcessRanCommand", pending_tail_summary)
        answer_stage_summary = data["activeAnswerHtml"].split('<div class="tool-process-stage-body">', 1)[0]
        self.assertIn(
            "<strong>label:run_command</strong><code>git status --short</code>",
            answer_stage_summary,
        )
        self.assertNotIn("toolProcessRanCommand", answer_stage_summary)
        self.assertNotIn("正在读取 README.md", data["operationalHtml"])
        self.assertNotIn("正在执行 git status --short", data["operationalHtml"])
        self.assertIn("meaningful checkpoint", data["operationalHtml"])
        self.assertIn("label:read_file", data["operationalHtml"])
        self.assertIn("label:run_command", data["operationalHtml"])
        self.assertEqual(data["operationalHtml"].count("data-tool-process-block"), 2)
        first_operational_group = data["operationalHtml"].index("data-tool-process-block")
        checkpoint_index = data["operationalHtml"].index("meaningful checkpoint")
        second_operational_group = data["operationalHtml"].index("data-tool-process-block", first_operational_group + 1)
        self.assertLess(first_operational_group, checkpoint_index)
        self.assertLess(checkpoint_index, second_operational_group)
        self.assertEqual(data["groupedStageHtml"].count("data-tool-process-block"), 1)
        self.assertEqual(data["groupedStageHtml"].count('class="tool-process-item succeeded"'), 2)
        self.assertIn('class="tool-process-stage succeeded"', data["groupedStageHtml"])
        grouped_stage_summary = data["groupedStageHtml"].split('<div class="tool-process-stage-body">', 1)[0]
        self.assertIn(
            "<strong>toolProcessInspectedFile · toolProcessRanCommand</strong>",
            grouped_stage_summary,
        )
        self.assertNotIn("tool-process-indicator", grouped_stage_summary)
        self.assertNotIn("<code>", grouped_stage_summary)
        self.assertNotIn("<details open", data["groupedStageHtml"])
        active_tail_summary = data["activeCompletedTailHtml"].split('<div class="tool-process-stage-body">', 1)[0]
        self.assertIn('class="tool-process-stage running"', active_tail_summary)
        self.assertNotIn("tool-active", active_tail_summary)
        self.assertIn(
            "<strong>label:run_command</strong><code>git status --short</code>",
            active_tail_summary,
        )
        self.assertNotIn("toolProcessInspectedFile", active_tail_summary)
        self.assertNotIn("toolProcessRanCommand", active_tail_summary)
        self.assertIn('data-tool-process-key="0:1"', data["activeCompletedTailHtml"])
        self.assertNotRegex(
            data["activeCompletedTailHtml"],
            r'<details class="tool-process-stage running"[^>]+ open>',
        )
        self.assertRegex(
            data["expandedActiveTailHtml"],
            r'<details class="tool-process-stage running"[^>]+ open>',
        )
        self.assertNotRegex(
            data["completedCollapsedTailHtml"],
            r'<details class="tool-process-stage succeeded"[^>]+ open>',
        )
        separated_html = data["activeSeparatedStagesHtml"]
        self.assertEqual(separated_html.count("data-tool-process-block"), 2)
        separated_first = separated_html.split("data-tool-process-block", 2)[1]
        separated_second = separated_html.split("data-tool-process-block", 2)[2]
        self.assertIn('class="tool-process-stage succeeded"', separated_first)
        self.assertNotIn("single-tool", separated_first.split('<div class="tool-process-stage-body">', 1)[0])
        self.assertIn(
            "<strong>toolProcessInspectedFile · toolProcessRanCommand</strong>",
            separated_first,
        )
        self.assertIn('class="tool-process-stage running single-tool"', separated_second)
        self.assertNotIn("tool-active", separated_second.split('<div class="tool-process-stage-body">', 1)[0])
        self.assertIn(
            "<strong>label:run_command</strong><code>git status --short</code>",
            separated_second,
        )
        for gap_html in (data["activeToolGapHtml"], data["activeFailedToolGapHtml"]):
            gap_summary = gap_html.split('<div class="tool-process-stage-body">', 1)[0]
            self.assertIn('class="tool-process-stage running single-tool"', gap_summary)
            self.assertNotIn("tool-active", gap_summary)
            self.assertRegex(
                gap_html,
                r'<details class="tool-process-stage running single-tool"[^>]+ open>',
            )
            self.assertRegex(
                gap_html,
                r'<details class="tool-process-item (?:succeeded|failed)"[^>]+ open>',
            )
        failed_then_retry_html = data["activeFailedThenRetryHtml"]
        self.assertEqual(failed_then_retry_html.count("data-tool-process-block"), 1)
        self.assertEqual(failed_then_retry_html.count('class="tool-process-stage running tool-active"'), 1)
        self.assertIn('data-tool-process-id="session-1:failed-gap-1"', failed_then_retry_html)
        self.assertNotIn('data-tool-process-id="session-1:failed-gap-2"', failed_then_retry_html)
        self.assertEqual(failed_then_retry_html.count('class="tool-process-item '), 2)
        self.assertRegex(
            failed_then_retry_html,
            r'<details class="tool-process-item failed"[^>]+ open>',
        )
        self.assertRegex(
            failed_then_retry_html,
            r'<details class="tool-process-item running"[^>]+ open>',
        )
        for waiting_html in (
            data["activeQuestionnaireWaitingHtml"],
            data["activeAuthorizationWaitingHtml"],
        ):
            self.assertIn('class="tool-process-stage running tool-active single-tool"', waiting_html)
            self.assertRegex(
                waiting_html,
                r'<details class="tool-process-stage running tool-active single-tool"[^>]+ open>',
            )
            self.assertRegex(
                waiting_html,
                r'<details class="tool-process-item running"[^>]+ open>',
            )
        self.assertIn('data-current-action="run_command"', data["runningStage"])
        self.assertIn('class="tool-process-stage running tool-active"', data["runningStage"])
        running_stage_summary = data["runningStage"].split('<div class="tool-process-stage-body">', 1)[0]
        self.assertIn(
            "<strong>label:run_command</strong><code>git status --short</code>",
            running_stage_summary,
        )
        self.assertNotIn("tool-process-indicator", running_stage_summary)
        self.assertIn("tool-process-indicator", data["runningStage"].split('<div class="tool-process-stage-body">', 1)[1])
        self.assertEqual(data["runningStage"].count("toolProcessRunning"), 1)
        completed_commands_summary = data["completedCommands"].split('<div class="tool-process-stage-body">', 1)[0]
        self.assertIn("<strong>toolProcessRanCommands</strong>", completed_commands_summary)
        self.assertNotIn("<code>", completed_commands_summary)
        completed_edits_summary = data["completedEdits"].split('<div class="tool-process-stage-body">', 1)[0]
        self.assertIn("<strong>toolProcessEditedFiles</strong>", completed_edits_summary)
        self.assertNotIn("<code>", completed_edits_summary)
        self.assertIn('class="tool-process-stage cancelled"', data["cancelledCommand"])
        self.assertIn('class="tool-process-item cancelled"', data["cancelledCommand"])
        self.assertEqual(data["cancelledCommand"].count('class="tool-process-item cancelled"'), 2)
        self.assertIn("toolProcessCancelled", data["cancelledCommand"])
        self.assertNotIn("toolProcessRunning", data["cancelledCommand"])
        for expected in (
            'toolProcessRanCommand: "运行了命令"',
            'toolProcessRanCommands: "运行了多个命令"',
            'toolProcessEditedFile: "编辑了文件"',
            'toolProcessEditedFiles: "编辑了多个文件"',
            'toolProcessInspectedFile: "查看了文件"',
            'toolProcessInspectedFiles: "查看了多个文件"',
            'toolProcessDeletedFile: "删除了文件"',
            'toolProcessDeletedFiles: "删除了多个文件"',
            'toolProcessUsedTool: "使用了工具"',
            'toolProcessUsedTools: "使用了多个工具"',
            'toolProcessRanCommand: "Ran a command"',
            'toolProcessEditedFiles: "Edited multiple files"',
        ):
            self.assertIn(expected, I18N_SOURCE)
        self.assertNotIn("Reading README.md", data["englishOperational"])
        self.assertNotIn("0s", data["usageOnly"])
        self.assertEqual(data["claudeUsage"], {
            "input": 115,
            "output": 4,
            "cache": 100,
            "cacheWrite": 3,
            "hasCacheReported": True,
        })
        self.assertEqual(data["openAIUsage"], {
            "input": 100,
            "output": 4,
            "cache": 80,
            "hasCacheReported": True,
        })
        self.assertIn('data-usage-kind="input"', data["cacheStatus"])
        self.assertIn('data-usage-kind="cache-read"', data["cacheStatus"])
        self.assertIn('data-usage-kind="cache-write"', data["cacheStatus"])
        self.assertIn('title="statCacheWriteTitle"', data["cacheStatus"])

    def test_primary_turn_owns_completed_elapsed_while_detached_footer_remains(self):
        script = r"""
global.window = {Code: {ui: {}}};
require("./src/ui/messages.js");
const {createMessagesFeature} = window.Code.ui.messages;
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");
let language = "zh";
const translations = {
  zh: {
    completedElapsedLabel: "用时",
    processedLabel: "已处理",
    taskElapsedTitle: "任务总耗时",
  },
  en: {
    completedElapsedLabel: "Worked for",
    processedLabel: "Worked for",
    taskElapsedTitle: "Total task time",
  },
};
const feature = createMessagesFeature({
  escapeHtml,
  formatCompact: (value) => String(value),
  renderMarkdown: (value) => `<md>${escapeHtml(value)}</md>`,
  t: (key) => translations[language]?.[key] || key,
  getMessageText: (msg) => String(msg?.content || ""),
  getBackgroundJob: () => null,
  getMessages: () => [],
  getSessionId: () => "session-completed-owner",
  getSelectedModel: () => "model-1",
  renderNetworkRecoveryStatus: () => "",
  renderAssistantContent: (value) => `<answer>${escapeHtml(value)}</answer>`,
  renderBranchFlow: () => "",
  isEditSuggestionMessage: () => false,
  renderEditSuggestion: () => "",
  getToolActionLabel: (action) => `label:${action}`,
});
const usage = {_usage: {input: 12, output: 4}};
const detachedUser = {
  role: "user",
  content: "/parallel inspect independently",
  meta: {
    detachedFromMain: true,
    backgroundDispatch: {id: "parallel-1", status: "completed"},
  },
};
const detachedAssistant = {
  role: "assistant",
  content: "parallel result",
  _responseTime: "2s",
  meta: {
    detachedFromMain: true,
    kind: "background-subagent",
    jobId: "parallel-1",
  },
};
const mainFinal = {
  role: "assistant",
  content: "main final",
  _responseTime: "9s",
  meta: usage,
};
const parallelFirstMessages = [
  {role: "user", content: "main task"},
  detachedUser,
  detachedAssistant,
  mainFinal,
];
const mainFirstMessages = [
  {role: "user", content: "main task"},
  detachedUser,
  mainFinal,
  detachedAssistant,
];
const toolMessages = [
  {role: "user", content: "main tool task"},
  {role: "assistant", content: "inspect", meta: {toolCalls: [
    {id: "call-1", function: {name: "read_file", arguments: '{"path":"README.md"}'}},
  ]}},
  {role: "tool-call", meta: {
    action: "read_file",
    toolCallId: "call-1",
    tool: {action: "read_file", path: "README.md"},
  }},
  detachedUser,
  detachedAssistant,
  {role: "tool-result", content: "contents", meta: {
    action: "read_file",
    toolCallId: "call-1",
    outcome: "succeeded",
  }},
  {role: "assistant", content: "tool final", _responseTime: "8s", meta: usage},
];
const queuedMessages = [
  {role: "user", content: "main task"},
  {role: "assistant", content: "main final", _responseTime: "5s", meta: usage},
  {role: "user", content: "queued next", meta: {
    queuedDispatch: {id: "queue-1", status: "completed"},
  }},
  {role: "assistant", content: "queued final", _responseTime: "6s", meta: usage},
];
const parallelFirst = feature.projectMessages(parallelFirstMessages, {hasActiveRun: false});
const mainFirst = feature.projectMessages(mainFirstMessages, {hasActiveRun: false});
const tool = feature.projectMessages(toolMessages, {hasActiveRun: false});
const toolExpanded = feature.projectMessages(toolMessages, {
  hasActiveRun: false,
  expandedExecutionTraces: new Set(["0"]),
});
const queued = feature.projectMessages(queuedMessages, {hasActiveRun: false});
const refreshed = feature.projectMessages(parallelFirstMessages, {hasActiveRun: false});
const zh = refreshed;
language = "en";
const en = feature.projectMessages(parallelFirstMessages, {hasActiveRun: false});
process.stdout.write(JSON.stringify({
  parallelFirst,
  mainFirst,
  tool,
  toolExpanded,
  queued,
  refreshed,
  refreshStable: refreshed === parallelFirst,
  zh,
  en,
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)

        def article(html, message_index):
            marker = f'data-msg-index="{message_index}"'
            marker_index = html.index(marker)
            start = html.rfind("<article", 0, marker_index)
            end = html.index("</article>", marker_index) + len("</article>")
            return html[start:end]

        parallel_first = data["parallelFirst"]
        self.assertEqual(parallel_first.count("data-completed-run-status"), 1)
        self.assertEqual(parallel_first.count("9s"), 1)
        self.assertEqual(parallel_first.count("2s"), 1)
        self.assertEqual(parallel_first.count('class="run-time"'), 1)
        main_footer = article(parallel_first, 3)
        detached_footer = article(parallel_first, 2)
        self.assertIn('class="response-info"', main_footer)
        self.assertIn('data-usage-kind="input"', main_footer)
        self.assertIn('data-usage-kind="output"', main_footer)
        self.assertNotIn('class="run-time"', main_footer)
        self.assertIn('class="run-time"', detached_footer)
        self.assertIn("2s", detached_footer)
        self.assertNotIn("data-completed-run-status", article(parallel_first, 1))

        main_first = data["mainFirst"]
        self.assertEqual(main_first.count("data-completed-run-status"), 1)
        self.assertEqual(main_first.count("9s"), 1)
        self.assertEqual(main_first.count("2s"), 1)
        self.assertNotIn('class="run-time"', article(main_first, 2))
        self.assertIn('class="run-time"', article(main_first, 3))

        tool = data["tool"]
        self.assertEqual(tool.count("data-completed-run-status"), 1)
        self.assertEqual(tool.count("data-tool-process-block"), 1)
        self.assertEqual(tool.count('class="tool-process-item succeeded"'), 1)
        self.assertEqual(tool.count('data-tool-process-key="0:1"'), 1)
        self.assertEqual(tool.count("execution-trace-persistent"), 2)
        self.assertEqual(tool.count('class="run-time"'), 1)
        self.assertNotIn('class="run-time"', article(tool, 6))
        trace_start = tool.index('class="execution-trace completed"')
        main_final = tool.index("tool final")
        trace_end = tool.rfind("</section>", trace_start, main_final)
        self.assertLess(trace_start, tool.index("data-tool-process-block", trace_start))
        self.assertLess(tool.index("parallel result", trace_start), trace_end)
        self.assertLess(trace_end, main_final)
        self.assertEqual(data["toolExpanded"].count("data-tool-process-block"), 1)
        self.assertEqual(
            data["toolExpanded"].count('class="execution-trace completed is-expanded"'),
            1,
        )

        queued = data["queued"]
        self.assertEqual(queued.count("data-completed-run-status"), 2)
        self.assertEqual(queued.count("用时"), 2)
        self.assertEqual(queued.count('class="run-time"'), 0)
        self.assertEqual(queued.count("5s"), 1)
        self.assertEqual(queued.count("6s"), 1)
        self.assertTrue(data["refreshStable"])
        self.assertEqual(data["refreshed"].count("data-completed-run-status"), 1)

        self.assertIn('class="completed-run-label">用时</span>', data["zh"])
        self.assertNotIn('class="completed-run-label">已处理</span>', data["zh"])
        self.assertIn('class="completed-run-label">Worked for</span>', data["en"])
        self.assertNotIn('class="completed-run-label">用时</span>', data["en"])
        self.assertIn('processedLabel: "已处理"', I18N_SOURCE)
        self.assertIn('completedElapsedLabel: "用时"', I18N_SOURCE)
        self.assertIn('completedElapsedLabel: "Worked for"', I18N_SOURCE)

    def test_messages_ui_binds_copy_and_image_events_without_inline_globals(self):
        self.assertNotIn('onclick="copyMessageText', MESSAGES_SOURCE)
        self.assertNotIn('onclick="showImageOverlay', MESSAGES_SOURCE)
        self.assertNotIn('onload="', MESSAGES_SOURCE)
        self.assertNotIn('onclick="showImageOverlay', MARKDOWN_SOURCE)
        self.assertNotIn('onclick="showImageOverlay', APP_SOURCE)
        self.assertIn("data-composer-image-preview", APP_SOURCE)
        image_thumbs_source = APP_SOURCE.split("function renderImageThumbs()", 1)[1].split(
            "async function handleImageFile", 1
        )[0]
        self.assertIn(
            'container.querySelectorAll("[data-composer-image-preview]")',
            image_thumbs_source,
        )
        model_attempt_source = APP_SOURCE.split("async function _callModelOnceAttempt", 1)[1].split(
            "function _safeMd", 1
        )[0]
        self.assertNotIn("data-composer-image-preview", model_attempt_source)

        sent_image_rule_start = STYLE_SOURCE.index(".msg-img-clickable {")
        sent_image_rule_end = STYLE_SOURCE.index("}", sent_image_rule_start)
        sent_image_rule = STYLE_SOURCE[sent_image_rule_start:sent_image_rule_end]
        self.assertIn("width: auto", sent_image_rule)
        self.assertIn("height: 120px", sent_image_rule)
        self.assertIn("max-width: 100%", sent_image_rule)
        self.assertIn("object-fit: contain", sent_image_rule)
        image_group_rule_start = STYLE_SOURCE.index(".msg-image-group {")
        image_group_rule_end = STYLE_SOURCE.index("}", image_group_rule_start)
        image_group_rule = STYLE_SOURCE[image_group_rule_start:image_group_rule_end]
        self.assertIn("display: flex", image_group_rule)
        self.assertIn("flex-wrap: wrap", image_group_rule)
        self.assertIn("justify-content: flex-end", image_group_rule)
        self.assertIn("gap: 8px", image_group_rule)

        script = r"""
const writes = [];
const previewed = [];
const loaded = [];
const timers = [];
global.setTimeout = (handler) => { timers.push(handler); return timers.length; };
global.window = {
  Code: {features: {}, ui: {}},
  navigator: {clipboard: {writeText: async (value) => { writes.push(value); }}},
};
require("./src/ui/messages.js");
require("./src/features/image-attachments.js");
const {createMessagesFeature} = window.Code.ui.messages;
const {imagePreviewSource} = window.Code.features.imageAttachments;
const handlers = {};
const root = {
  addEventListener(type, handler, options) {
    handlers[type] = handlers[type] || [];
    handlers[type].push({handler, options});
  },
  contains: () => true,
};
const classes = new Set();
const copyButton = {
  dataset: {copyText: "copy me"},
  innerHTML: "copy",
  title: "",
  classList: {
    add: (...names) => names.forEach((name) => classes.add(name)),
    remove: (...names) => names.forEach((name) => classes.delete(name)),
  },
  setAttribute(name, value) { this[name] = value; },
  closest(selector) { return selector === ".msg-copy-btn" ? this : null; },
};
const previewImage = {
  currentSrc: "current-preview.png",
  src: "fallback-preview.png",
  closest(selector) { return selector === "[data-message-image-preview]" ? this : null; },
};
const loadingImage = {
  closest(selector) { return selector === "[data-message-scroll-on-load]" ? this : null; },
};
const fallbackCard = {hidden: true};
const failedPreviewImage = {
  hidden: false,
  parentElement: {querySelector: () => fallbackCard},
  closest(selector) { return selector === "[data-message-image-preview]" ? this : null; },
};
const feature = createMessagesFeature({
  escapeHtml: (value) => String(value ?? ""),
  t: (key) => key,
  getImagePreviewSource: imagePreviewSource,
  onImagePreview: (src) => previewed.push(src),
  onImageLoad: (image) => loaded.push(image),
});
const firstBound = feature.bindInteractions(root);
const secondBound = feature.bindInteractions(root);

(async () => {
  handlers.click[0].handler({target: copyButton});
  await Promise.resolve();
  await Promise.resolve();
  handlers.click[0].handler({target: previewImage});
  handlers.load[0].handler({target: loadingImage});
  handlers.error[0].handler({target: failedPreviewImage});
  const copyHtml = feature.renderCopyButton("copy me");
  const userHtml = feature.renderUserProjection({
    role: "user",
    content: "",
    _images: [{path: "C:/tmp/demo.png", name: "demo"}],
  }, 1);
  const batchHtml = feature.renderUserProjection({
    role: "user",
    content: "describe these images",
    _images: [
      {path: "C:/tmp/one.png", name: "one"},
      {path: "C:/tmp/two.png", name: "two"},
      {path: "C:/tmp/three.png", name: "three"},
    ],
  }, 2);
  const tiffHtml = feature.renderUserProjection({
    role: "user",
    content: "tiff",
    _images: [{path: "attachments/demo.tiff", name: "demo.tiff", mime: "image/tiff"}],
  }, 3, {});
  process.stdout.write(JSON.stringify({
    firstBound,
    secondBound,
    clickHandlers: handlers.click.length,
    loadHandlers: handlers.load.length,
    errorHandlers: handlers.error.length,
    loadUsesCapture: handlers.load[0].options === true,
    writes,
    previewed,
    loadedCount: loaded.length,
    failedPreviewHidden: failedPreviewImage.hidden,
    fallbackVisible: fallbackCard.hidden === false,
    copied: classes.has("copied"),
    copyHtml,
    userHtml,
    batchHtml,
    tiffHtml,
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["firstBound"])
        self.assertFalse(data["secondBound"])
        self.assertEqual(data["clickHandlers"], 1)
        self.assertEqual(data["loadHandlers"], 1)
        self.assertEqual(data["errorHandlers"], 1)
        self.assertTrue(data["loadUsesCapture"])
        self.assertEqual(data["writes"], ["copy me"])
        self.assertEqual(data["previewed"], ["current-preview.png"])
        self.assertEqual(data["loadedCount"], 1)
        self.assertTrue(data["failedPreviewHidden"])
        self.assertTrue(data["fallbackVisible"])
        self.assertTrue(data["copied"])
        self.assertIn('class="msg-copy-btn"', data["copyHtml"])
        self.assertNotIn("onclick=", data["copyHtml"])
        self.assertIn("data-message-image-preview", data["userHtml"])
        self.assertIn("data-message-scroll-on-load", data["userHtml"])
        self.assertNotIn("onclick=", data["userHtml"])
        self.assertNotIn("onload=", data["userHtml"])
        self.assertNotIn("data-message-image-fallback", data["userHtml"])
        self.assertEqual(data["batchHtml"].count('class="msg user msg-image-batch"'), 1)
        self.assertEqual(data["batchHtml"].count("data-message-image-preview"), 3)
        self.assertEqual(data["batchHtml"].count('class="bubble bubble-img msg-image-group"'), 1)
        self.assertNotIn("data-message-image-fallback", data["batchHtml"])
        self.assertIn("data-message-image-fallback", data["tiffHtml"])
        self.assertIn("/api/attachments/preview?path=attachments%2Fdemo.tiff", data["tiffHtml"])
        self.assertLess(
            data["batchHtml"].index("msg-image-group"),
            data["batchHtml"].index("describe these images"),
        )

    def test_messages_ui_localizes_request_user_input_process(self):
        self.assertIn('request_user_input:"toolRequestUserInput"', APP_SOURCE)
        self.assertIn('case "request_user_input": return t("progressUserInput");', APP_SOURCE)
        self.assertIn('/^→\\s*request_user_input$/.test(line)', MESSAGES_SOURCE)
        self.assertIn('if (action === "request_user_input") return "questionnaire";', MESSAGES_SOURCE)

        script = r"""
global.window = {Code: {ui: {}}};
require("./src/ui/messages.js");
const {createMessagesFeature} = window.Code.ui.messages;
const feature = createMessagesFeature({
  escapeHtml: (value) => String(value ?? ""),
  renderMarkdown: (value) => String(value ?? ""),
  renderAssistantContent: (value) => `<answer>${String(value ?? "")}</answer>`,
  getMessageText: (msg) => String(msg?.content || ""),
  getToolActionLabel: (action) => `label:${action}`,
  t: (key) => key,
});
const messages = [
  {role: "user", content: "ask"},
  {role: "assistant", content: "→ request_user_input", meta: {toolCalls: [
    {id: "question-1", function: {name: "request_user_input", arguments: '{"questions":[{"id":"preview","question":"预览正常吗？"}]}' }},
  ]}},
  {role: "tool-call", meta: {action: "request_user_input", toolCallId: "question-1", tool: {
    action: "request_user_input",
    questions: [{id: "preview", question: "预览正常吗？"}],
  }}},
  {role: "tool-result", content: '{"answers":{"preview":"正常"}}', meta: {
    action: "request_user_input",
    toolCallId: "question-1",
    outcome: "succeeded",
  }},
  {role: "assistant", content: "done", _responseTime: "1s"},
];
const html = feature.projectMessages(messages, {hasActiveRun: false});
const multiple = feature.renderToolProcessProjection([
  {msg: {role: "assistant", meta: {toolCalls: [
    {id: "question-2", function: {name: "request_user_input", arguments: '{"questions":[{"id":"a","question":"A?"}]}' }},
    {id: "question-3", function: {name: "request_user_input", arguments: '{"questions":[{"id":"b","question":"B?"}]}' }},
  ]}}, index: 1},
  {msg: {role: "tool-call", meta: {action: "request_user_input", toolCallId: "question-2", tool: {action: "request_user_input"}}}, index: 2},
  {msg: {role: "tool-result", content: "a", meta: {action: "request_user_input", toolCallId: "question-2", outcome: "succeeded"}}, index: 3},
  {msg: {role: "tool-call", meta: {action: "request_user_input", toolCallId: "question-3", tool: {action: "request_user_input"}}}, index: 4},
  {msg: {role: "tool-result", content: "b", meta: {action: "request_user_input", toolCallId: "question-3", outcome: "succeeded"}}, index: 5},
], 2);
process.stdout.write(JSON.stringify({
  html,
  multiple,
  legacyNotice: feature.isOperationalToolNotice("→ request_user_input"),
  chineseNotice: feature.isOperationalToolNotice("正在等待用户输入…"),
  englishNotice: feature.isOperationalToolNotice("Waiting for user input…"),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["legacyNotice"])
        self.assertTrue(data["chineseNotice"])
        self.assertTrue(data["englishNotice"])
        self.assertNotIn("→ request_user_input", data["html"])
        self.assertEqual(data["html"].count("data-tool-process-block"), 1)
        self.assertIn('class="tool-process-stage succeeded single-tool"', data["html"])
        self.assertNotIn("<strong>toolProcessAskedUser</strong>", data["html"])
        self.assertIn("<strong>label:request_user_input</strong>", data["html"])
        self.assertIn("<strong>toolProcessAskedUserMultiple</strong>", data["multiple"])
        for expected in (
            'toolRequestUserInput: "询问用户"',
            'toolProcessAskedUser: "询问了用户"',
            'toolProcessAskedUserMultiple: "多次询问了用户"',
            'progressUserInput: "正在等待用户输入…"',
            'toolRequestUserInput: "Ask user"',
            'toolProcessAskedUser: "Asked the user"',
            'toolProcessAskedUserMultiple: "Asked the user multiple times"',
            'progressUserInput: "Waiting for user input…"',
        ):
            self.assertIn(expected, I18N_SOURCE)

    def test_messages_ui_defers_pending_fifo_rows_below_active_output(self):
        script = r"""
global.window = {Code: {ui: {}}};
require("./src/ui/messages.js");
const feature = window.Code.ui.messages.createMessagesFeature({
  escapeHtml: (value) => String(value ?? ""),
  renderMarkdown: (value) => String(value ?? ""),
  t: (key) => key,
  getMessageText: (msg) => String(msg?.content || ""),
  getSelectedModel: () => "model-1",
  renderAssistantContent: (value) => `<answer>${value}</answer>`,
});
const messages = [
  {role: "user", content: "active request"},
  {role: "user", content: "queued first", meta: {queuedDispatch: {id: "q-1", status: "pending"}, detachedFromMain: true}},
  {role: "user", content: "canceled second", meta: {queuedDispatch: {id: "q-2", status: "canceled"}, detachedFromMain: true}},
  {role: "assistant", content: "active output"},
  {role: "user", content: "queued third", meta: {queuedDispatch: {id: "q-3", status: "pending"}, detachedFromMain: true}},
];
process.stdout.write(feature.projectMessages(messages, {hasActiveRun: true}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        html = completed.stdout
        self.assertLess(html.index("active request"), html.index("active output"))
        self.assertLess(html.index("active output"), html.index("queued first"))
        self.assertLess(html.index("queued first"), html.index("canceled second"))
        self.assertLess(html.index("canceled second"), html.index("queued third"))
        self.assertEqual(html.count("queued-message-cancel"), 0)
        self.assertEqual(html.count("queuedMessagePending"), 0)
        self.assertEqual(html.count("queuedMessageCanceled"), 0)

    def test_timeline_ui_owns_markers_nodes_and_click_navigation(self):
        self.assertIn("Code.ui.timeline = Object.freeze", TIMELINE_SOURCE)
        for obsolete in (
            "function getCompactSummaryStats(",
            "function renderCompactSummaryProjection(",
            "function getBranchFlowMarker(",
            "function renderBranchFlowProjection(",
            "function renderTimeline(",
        ):
            self.assertNotIn(obsolete, APP_SOURCE)
        script = r"""
global.window = {Code: {ui: {}}};
require("./src/ui/timeline.js");
const {createTimelineFeature, DEFAULT_MIN_TIMELINE_WIDTH, TIMELINE_MARKER_PITCH, TIMELINE_MAX_VIEWPORT_RATIO, syncSessionBranchMetadata} = window.Code.ui.timeline;
const escapeHtml = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
let messages = [
  {role: "user", content: "first task"},
  {role: "assistant", content: "tool planning", meta: {toolCalls: [{id: "call-1"}]}},
  {role: "assistant", content: "## First paragraph\n\n### Second paragraph\n\n\n**Third paragraph**\n- Fourth paragraph"},
  {role: "user", content: "second task " + "x".repeat(90)},
  {role: "assistant", content: "partial", streaming: true},
  {role: "assistant", content: "[final response](https://example.com) with `code`"},
];
const sessions = [
  {id: "parent", title: "Parent <one>", _branches: ["child"]},
  {id: "child", _parentId: "parent", _branchMsgCount: null},
];
const loadedBranch = {id: "child", _parentId: "parent", _branchDepth: 1, _branches: [], _branchMsgCount: 3.8};
const visible = new Set();
const clickListeners = [];
const markerStates = new Map();
const makeMarker = (index) => {
  const state = {active: false, visible: false, ariaCurrent: null, classes: new Set(), listeners: {}};
  const marker = {
    dataset: {index},
    classList: {
      toggle: (name, enabled) => {
        if (enabled) state.classes.add(name);
        else state.classes.delete(name);
        if (name === "is-active") state.active = enabled;
        if (name === "is-visible") state.visible = enabled;
      },
    },
    setAttribute: (name, value) => {
      if (name === "aria-current") state.ariaCurrent = value;
    },
    removeAttribute: (name) => {
      if (name === "aria-current") state.ariaCurrent = null;
    },
    addEventListener: (type, callback) => {
      if (type === "click") clickListeners.push(callback);
      state.listeners[type] = callback;
    },
  };
  markerStates.set(index, state);
  return marker;
};
let markers = [];
let timelineHtmlValue = "";
let wheelListener = null;
const timelineAttributes = new Map();
const timeline = {
  clientHeight: 534,
  get innerHTML() {
    return timelineHtmlValue;
  },
  set innerHTML(value) {
    timelineHtmlValue = value;
    clickListeners.length = 0;
    markerStates.clear();
    markers = Array.from(value.matchAll(/data-index="(\d+)"/g), (match) => makeMarker(match[1]));
  },
  classList: {
    add: (name) => visible.add(name),
    remove: (name) => visible.delete(name),
    toggle: (name, enabled) => {
      if (enabled) visible.add(name);
      else visible.delete(name);
    },
  },
  setAttribute: (name, value) => timelineAttributes.set(name, value),
  removeAttribute: (name) => timelineAttributes.delete(name),
  querySelectorAll: (selector) => selector === ".tl-marker" ? markers : [],
  addEventListener: (type, callback) => {
    if (type === "wheel") wheelListener = callback;
  },
  removeEventListener: () => {},
};
let scrolled = null;
let scrollListener = null;
let resizeCallback = null;
let viewportHeight = 720;
class FakeResizeObserver {
  constructor(callback) {
    resizeCallback = callback;
  }
  observe() {}
  disconnect() {}
}
const messageContainer = {
  scrollTop: 0,
  clientHeight: 400,
  clientWidth: 800,
  addEventListener: (type, callback) => {
    if (type === "scroll") scrollListener = callback;
  },
  removeEventListener: () => {},
  querySelector: (selector) => {
    const index = selector.match(/"(\d+)"/)?.[1] || "0";
    const target = {
      offsetTop: index === "3" ? 500 : Number(index) * 100,
      offsetParent: messageContainer,
      scrollIntoView: (options) => { scrolled = {selector, options}; },
    };
    return target;
  },
};
const t = (key, params = {}) => `${key}:${Object.values(params).join("|")}`;
const feature = createTimelineFeature({
  escapeHtml,
  formatCompact: (value) => `${value}t`,
  t,
  getMessageText: (msg) => String(msg?.content || ""),
  getMessages: () => messages,
  getSessions: () => sessions,
  getSessionId: () => "child",
  getTimelineElement: () => timeline,
  getMessageContainer: () => messageContainer,
  requestAnimationFrame: (callback) => callback(),
  ResizeObserver: FakeResizeObserver,
  getViewportHeight: () => viewportHeight,
});
const syncedBranch = syncSessionBranchMetadata(sessions, loadedBranch);
const branchMarker = feature.getBranchFlowMarker();
const branch = feature.renderBranchFlowProjection(branchMarker.parentTitle);
const nodes = feature.projectTimelineNodes(messages);
feature.renderTimeline();
const timelineHtml = timeline.innerHTML;
const wasVisible = visible.has("visible");
const initialActive = markerStates.get("0").active;
const initialVisible = markerStates.get("0").visible;
messageContainer.scrollTop = 450;
scrollListener();
const activeAfterScroll = markerStates.get("3").active;
const activeAria = markerStates.get("3").ariaCurrent;
const firstVisibleAfterScroll = markerStates.get("0").visible;
const secondVisibleAfterScroll = markerStates.get("3").visible;
clickListeners[1]();
messageContainer.clientWidth = 500;
resizeCallback();
const hiddenWhenNarrow = visible.has("is-space-constrained");
const narrowAriaHidden = timelineAttributes.get("aria-hidden");
messageContainer.clientWidth = 700;
resizeCallback();
const restoredWhenWide = !visible.has("is-space-constrained");
const restoredAriaHidden = timelineAttributes.has("aria-hidden");
messages = Array.from({length: 70}, (_, index) => ({role: "user", content: `task ${index}`}));
messageContainer.scrollTop = 450;
feature.renderTimeline();
const longMarkerCount = markers.length;
const longWindowStart = timeline.innerHTML.match(/data-window-start="(\d+)"/)?.[1];
const longFirstIndex = markers[0].dataset.index;
markerStates.get("4").listeners.mouseenter();
const hoverCascade = {
  main: markerStates.get("4").classes.has("is-hover-main"),
  upperNear1: markerStates.get("3").classes.has("is-hover-near-1"),
  lowerNear1: markerStates.get("5").classes.has("is-hover-near-1"),
  upperNear2: markerStates.get("2").classes.has("is-hover-near-2"),
  lowerNear2: markerStates.get("6").classes.has("is-hover-near-2"),
  outside: markerStates.get("1").classes.has("is-hover-near-2"),
};
markerStates.get("4").listeners.mouseleave();
const hoverCascadeCleared = !Array.from(markerStates.values())
  .some((state) => Array.from(state.classes).some((name) => name.startsWith("is-hover-")));
let wheelPrevented = 0;
let wheelStopped = 0;
const wheelEvent = {
  deltaY: 100,
  preventDefault: () => { wheelPrevented += 1; },
  stopPropagation: () => { wheelStopped += 1; },
};
wheelListener(wheelEvent);
const afterWheelStart = timeline.innerHTML.match(/data-window-start="(\d+)"/)?.[1];
const afterWheelFirstIndex = markers[0].dataset.index;
for (let index = 0; index < 10; index += 1) wheelListener(wheelEvent);
const endWindowStart = timeline.innerHTML.match(/data-window-start="(\d+)"/)?.[1];
wheelListener(wheelEvent);
const boundaryWindowStart = timeline.innerHTML.match(/data-window-start="(\d+)"/)?.[1];
timeline.clientHeight = 214;
viewportHeight = 400;
resizeCallback();
const smallViewportMarkerCount = markers.length;
timeline.clientHeight = 534;
viewportHeight = 720;
resizeCallback();
const restoredViewportMarkerCount = markers.length;
messages = [{role: "user", content: "only one"}];
feature.renderTimeline();
process.stdout.write(JSON.stringify({
  defaultMinTimelineWidth: DEFAULT_MIN_TIMELINE_WIDTH,
  timelineMarkerPitch: TIMELINE_MARKER_PITCH,
  timelineMaxViewportRatio: TIMELINE_MAX_VIEWPORT_RATIO,
  syncedBranch,
  branchMarker,
  branch,
  nodes,
  timelineHtml,
  wasVisible,
  initialActive,
  initialVisible,
  activeAfterScroll,
  activeAria,
  firstVisibleAfterScroll,
  secondVisibleAfterScroll,
  scrolled,
  hiddenWhenNarrow,
  narrowAriaHidden,
  restoredWhenWide,
  restoredAriaHidden,
  longMarkerCount,
  longWindowStart,
  longFirstIndex,
  hoverCascade,
  hoverCascadeCleared,
  afterWheelStart,
  afterWheelFirstIndex,
  endWindowStart,
  boundaryWindowStart,
  smallViewportMarkerCount,
  restoredViewportMarkerCount,
  wheelPrevented,
  wheelStopped,
  clearedHtml: timeline.innerHTML,
  visibleAfterClear: visible.has("visible"),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["defaultMinTimelineWidth"], 560)
        self.assertEqual(data["timelineMarkerPitch"], 9)
        self.assertEqual(data["timelineMaxViewportRatio"], 0.7)
        self.assertNotIn("function getCompactSummaryStats(", TIMELINE_SOURCE)
        self.assertNotIn("function renderCompactSummaryProjection(", TIMELINE_SOURCE)
        self.assertEqual(data["syncedBranch"]["_branchMsgCount"], 3.8)
        self.assertEqual(data["branchMarker"], {"messageCount": 3, "parentTitle": "Parent <one>"})
        self.assertIn("Parent &lt;one&gt;", data["branch"])
        self.assertEqual([node["index"] for node in data["nodes"]], [0, 3])
        self.assertTrue(data["nodes"][1]["label"].endswith("…"))
        self.assertEqual(
            data["nodes"][0]["assistantPreview"],
            "First paragraph\nSecond paragraph\nThird paragraph…",
        )
        self.assertEqual(data["nodes"][1]["assistantPreview"], "final response with code")
        self.assertIn('data-index="0"', data["timelineHtml"])
        self.assertIn('data-index="3"', data["timelineHtml"])
        self.assertIn('class="tl-marker is-edge-start"', data["timelineHtml"])
        self.assertIn('class="tl-line"', data["timelineHtml"])
        self.assertIn('role="list"', data["timelineHtml"])
        self.assertIn("--timeline-visible-count:2", data["timelineHtml"])
        self.assertIn("timelineJumpTo:first task", data["timelineHtml"])
        self.assertIn('class="tl-bubble-title">first task</strong>', data["timelineHtml"])
        self.assertIn('class="tl-bubble-answer">First paragraph', data["timelineHtml"])
        self.assertIn("Second paragraph", data["timelineHtml"])
        self.assertIn("Third paragraph…", data["timelineHtml"])
        self.assertNotIn("## First paragraph", data["timelineHtml"])
        self.assertNotIn("### Second paragraph", data["timelineHtml"])
        self.assertNotIn("**Third paragraph**", data["timelineHtml"])
        self.assertNotIn("https://example.com", data["timelineHtml"])
        self.assertNotIn("`code`", data["timelineHtml"])
        self.assertIn('aria-describedby="timeline-preview-0"', data["timelineHtml"])
        self.assertNotIn("tl-dot", data["timelineHtml"])
        self.assertTrue(data["wasVisible"])
        self.assertTrue(data["initialActive"])
        self.assertTrue(data["initialVisible"])
        self.assertTrue(data["activeAfterScroll"])
        self.assertEqual(data["activeAria"], "location")
        self.assertTrue(data["firstVisibleAfterScroll"])
        self.assertTrue(data["secondVisibleAfterScroll"])
        self.assertEqual(data["scrolled"]["selector"], '[data-msg-index="3"]')
        self.assertEqual(data["scrolled"]["options"], {"behavior": "smooth", "block": "start"})
        self.assertTrue(data["hiddenWhenNarrow"])
        self.assertEqual(data["narrowAriaHidden"], "true")
        self.assertTrue(data["restoredWhenWide"])
        self.assertFalse(data["restoredAriaHidden"])
        self.assertEqual(data["longMarkerCount"], 56)
        self.assertEqual(data["longWindowStart"], "0")
        self.assertEqual(data["longFirstIndex"], "0")
        self.assertEqual(
            data["hoverCascade"],
            {
                "main": True,
                "upperNear1": True,
                "lowerNear1": True,
                "upperNear2": True,
                "lowerNear2": True,
                "outside": False,
            },
        )

        self.assertTrue(data["hoverCascadeCleared"])
        self.assertEqual(data["afterWheelStart"], "3")
        self.assertEqual(data["afterWheelFirstIndex"], "3")
        self.assertEqual(data["endWindowStart"], "14")
        self.assertEqual(data["boundaryWindowStart"], "14")
        self.assertEqual(data["smallViewportMarkerCount"], 24)
        self.assertEqual(data["restoredViewportMarkerCount"], 56)
        self.assertGreaterEqual(data["wheelPrevented"], 1)
        self.assertEqual(data["wheelPrevented"], data["wheelStopped"])
        self.assertEqual(data["clearedHtml"], "")
        self.assertFalse(data["visibleAfterClear"])
        self.assertIn('id="chatTimeline" role="navigation"', INDEX_SOURCE)
        self.assertIn('data-i18n-aria-label="timelineNavigation"', INDEX_SOURCE)
        for key in (
            "timelineNavigation",
            "timelineJumpTo",
            "timelineUntitled",
            "timelineNoFinalAnswer",
        ):
            self.assertEqual(I18N_SOURCE.count(f"{key}:"), 2, key)
        self.assertIn(".tl-marker.is-visible .tl-line", STYLE_SOURCE)
        self.assertIn(".tl-marker.is-active .tl-line", STYLE_SOURCE)
        self.assertIn(".tl-marker:hover .tl-line", STYLE_SOURCE)
        self.assertIn("width: 19px", STYLE_SOURCE)
        self.assertIn("left: 9px", STYLE_SOURCE)
        self.assertIn(".chat-timeline.visible.is-space-constrained", STYLE_SOURCE)
        self.assertIn("max-height: min(70vh, 100%)", STYLE_SOURCE)
        self.assertIn("grid-template-rows: repeat(var(--timeline-visible-count)", STYLE_SOURCE)
        self.assertIn("row-gap: 2px", STYLE_SOURCE)
        self.assertIn("-webkit-line-clamp: 3", STYLE_SOURCE)
        self.assertIn("white-space: pre-line", STYLE_SOURCE)
        self.assertNotIn(".tl-dot {", STYLE_SOURCE)

    def test_delete_session_confirmation_uses_i18n_and_localized_fallback(self):
        delete_start = APP_SOURCE.index("async function deleteSession(")
        delete_end = APP_SOURCE.index("function getPinnedSessions()", delete_start)
        delete_source = APP_SOURCE[delete_start:delete_end]

        self.assertIn('session?.title || t("untitledSession")', delete_source)
        self.assertIn(
            't("deleteSessionConfirmMessage", { name: title })',
            delete_source,
        )
        self.assertIn('deleteSessionConfirmMessage: "删除会话「{name}」？此操作不可恢复。"', I18N_SOURCE)
        self.assertIn(
            'deleteSessionConfirmMessage: "Delete session \\"{name}\\"? This action cannot be undone."',
            I18N_SOURCE,
        )
        self.assertNotIn("Untitled session", delete_source)
        self.assertNotIn("This action cannot be undone.`", delete_source)

    def test_remaining_visible_status_strings_use_i18n(self):
        self.assertIn('showToast(t("notEnoughToExtract"))', APP_SOURCE)
        self.assertIn('content: t("scanningConversation")', APP_SOURCE)
        self.assertIn('showToast(t("restarting"), "success")', SETTINGS_SOURCE)
        self.assertNotIn("Not enough conversation content to extract memories", APP_SOURCE)
        self.assertNotIn("Scanning conversation...", APP_SOURCE)
        self.assertNotIn("Code is restarting...", SETTINGS_SOURCE)
        self.assertEqual(I18N_SOURCE.count("scanningConversation:"), 2)

    def test_panels_ui_owns_session_stats_fields_and_top_panel_interactions(self):
        self.assertIn("Code.ui.panels = Object.freeze", PANELS_SOURCE)
        for removed_id in (
            "toolLogToggle",
            "toolLogPanel",
            "toolLogSummary",
            "toolLogList",
        ):
            self.assertNotIn(removed_id, INDEX_SOURCE)
            self.assertNotIn(removed_id, APP_SOURCE)
        self.assertNotIn("function getToolLogDetail(", APP_SOURCE)
        self.assertNotIn("function renderToolLog(", APP_SOURCE)
        self.assertNotIn("toggleToolLogPanel", PANELS_SOURCE)
        self.assertNotIn("onRenderToolLog", PANELS_SOURCE)
        self.assertNotIn(".tool-log-", STYLE_SOURCE)
        for removed_key in (
            "toolLog:",
            "toolLogEmpty:",
            "toolLogHint:",
            "toolActions:",
            "toolCalls:",
            "toolResults:",
            "toolFailures:",
            "fmtToolLogSep:",
            'toolLogToggle: "toolLog"',
        ):
            self.assertNotIn(removed_key, I18N_SOURCE)
        self.assertIn('id="statsPanel"', INDEX_SOURCE)
        self.assertIn('id="branchPanel"', INDEX_SOURCE)
        self.assertIn('id="toggleBranches"', INDEX_SOURCE)
        self.assertIn('id="togglePreview"', INDEX_SOURCE)
        self.assertIn("elements.msgTools.textContent", PANELS_SOURCE)
        self.assertIn('tools: "工具"', I18N_SOURCE)
        self.assertIn('tools: "Tools"', I18N_SOURCE)
        for obsolete in (
            "function closeTopPanels(",
            "function sessionFilePath(",
            "function calcStats(",
            "function updateStatsPanel(",
        ):
            self.assertNotIn(obsolete, APP_SOURCE)
        script = r"""
global.window = {Code: {ui: {}}, setTimeout: (callback) => callback()};
require("./src/ui/panels.js");
const {
  calculateSessionStats,
  createPanelsFeature,
  formatSessionTimestamp,
  formatSessionSource,
  resolveSessionFilePath,
} = window.Code.ui.panels;
const makeElement = (id) => {
  const classes = new Set();
  const listeners = {};
  const attrs = {};
  return {
    id,
    textContent: "",
    title: "",
    classes,
    listeners,
    attrs,
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
      toggle: (name, force) => {
        const next = force === undefined ? !classes.has(name) : Boolean(force);
        if (next) classes.add(name); else classes.delete(name);
        return next;
      },
    },
    addEventListener: (type, callback) => { listeners[type] = callback; },
    setAttribute: (name, value) => { attrs[name] = String(value); },
  };
};
const elementNames = [
  "statsPanel", "branchPanel", "usageStrip",
  "toggleBranches", "copySessionPath", "statInput", "statOutput", "statCache",
  "statContext", "ctxRingFill", "sessionCreated", "sessionUpdated", "sessionSource", "sessionFile",
  "msgUser", "msgAssistant", "msgTools", "msgTotal", "tokenInput", "tokenOutput",
  "tokenCache", "tokenCacheWriteRow", "tokenCacheWrite", "tokenTotal", "tokenContext",
];
const elements = Object.fromEntries(elementNames.map((name) => [name, makeElement(name)]));
const documentListeners = {};
const document = {addEventListener: (type, callback) => { documentListeners[type] = callback; }};
let branchOpen = false;
let branchRenders = 0;
let systemPromptReads = 0;
let usageStats = {input: 120, output: 30, cache: 10, cacheWrite: 5};
const messages = [
  {role: "user", content: "one"},
  {role: "assistant", content: "two"},
  {role: "assistant", content: "", meta: {kind: "auto-context-compaction", skipExport: true}},
  {role: "tool-call", content: "three"},
  {role: "tool-result", content: "four", streaming: true},
];
const feature = createPanelsFeature({
  elements,
  t: (key) => key === "usageStripTitle" ? "ctx {current}/{limit}" : key,
  formatCompact: (value) => `${value}c`,
  formatNumber: (value) => `${value}n`,
  estimateTokens: (value) => String(value).length,
  getMessages: () => messages,
  getStats: () => usageStats,
  getSessionId: () => "session-1",
  getSession: () => ({
    id: "session-1",
    createdAt: "2026-07-19T10:11:12Z",
    updatedAt: "2026-07-19T12:13:14Z",
    source: "claude-code",
    _sessionMessageFilePath: "C:/data/session-1.jsonl",
  }),
  getSessionLastUsage: () => ({prompt_tokens: 600}),
  getContextMessages: (items) => items,
  getContextLimit: () => 1000,
  getSelectedModel: () => "model-1",
  getMessageText: (msg) => msg.content,
  getSystemPrompt: () => { systemPromptReads += 1; return "system"; },
  getDocument: () => document,
  copyText: async () => true,
  onRenderBranchTree: () => { branchRenders += 1; },
  onBranchPanelOpenChanged: (open) => { branchOpen = open; },
});
feature.bind();
feature.bind();
const stats = feature.updateStatsPanel();
const cacheWriteText = elements.tokenCacheWrite.textContent;
const cacheWriteHidden = elements.tokenCacheWriteRow.hidden;
usageStats = {input: 120, output: 30, cache: 10};
const statsWithoutCacheWrite = feature.updateStatsPanel();
const cacheWriteHiddenWhenMissing = elements.tokenCacheWriteRow.hidden;
const systemPromptReadsWithLastUsage = systemPromptReads;
feature.toggleStatsPanel();
const statsWasOpen = elements.statsPanel.classes.has("open") && elements.usageStrip.classes.has("active");
feature.toggleBranchPanel();
const branchWasOpen = branchOpen && elements.branchPanel.classes.has("open") && !elements.statsPanel.classes.has("open");
feature.dismissPanelsForTarget({closest: () => null});
const allClosed = !elements.statsPanel.classes.has("open")
  && !elements.branchPanel.classes.has("open")
  && !branchOpen;
const fallback = calculateSessionStats({
  messages,
  stats: {input: 2, output: 1},
  getContextMessages: (items) => items,
  estimateTokens: (value) => String(value).length,
  getMessageText: (msg) => msg.content,
  getSystemPrompt: () => "sys",
  model: "fallback",
  getContextLimit: () => 100,
});
process.stdout.write(JSON.stringify({
  stats,
  fields: {
    statInput: elements.statInput.textContent,
    statContext: elements.statContext.textContent,
    sessionCreated: elements.sessionCreated.textContent,
    sessionUpdated: elements.sessionUpdated.textContent,
    sessionSource: elements.sessionSource.textContent,
    sessionSourceKey: elements.sessionSource.attrs["data-i18n"],
    sessionFile: elements.sessionFile.textContent,
    sessionFileTitle: elements.sessionFile.title,
    msgTotal: elements.msgTotal.textContent,
    msgTools: elements.msgTools.textContent,
    tokenTotal: elements.tokenTotal.textContent,
    tokenCacheWrite: cacheWriteText,
    cacheWriteHidden,
    cacheWriteHiddenWhenMissing,
    tokenContext: elements.tokenContext.textContent,
    usageTitle: elements.usageStrip.title,
    ringStroke: elements.ctxRingFill.attrs.stroke,
  },
  systemPromptReadsWithLastUsage,
  statsWasOpen,
  branchWasOpen,
  allClosed,
  branchRenders,
  fallback,
  statsWithoutCacheWrite,
  absolutePath: resolveSessionFilePath({id: "s1"}, {sessionId: "s1", absolutePath: "D:/sessions/s1.jsonl"}),
  fallbackPath: resolveSessionFilePath({id: "s2"}),
  codexSource: formatSessionSource({source: "codex"}, (key) => `t:${key}`),
  codeSource: formatSessionSource({}, (key) => `t:${key}`),
  registeredDocumentClick: Boolean(documentListeners.click),
  shanghaiAware: formatSessionTimestamp("2026-08-22T05:37:00Z"),
  legacyNaive: formatSessionTimestamp("2026-08-22T13:37:00"),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "TZ": "Asia/Shanghai"},
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["stats"]["counts"], {
            "user": 1,
            "assistant": 1,
            "toolCalls": 1,
            "toolResults": 1,
            "total": 4,
        })
        self.assertEqual(data["stats"]["contextTokens"], 600)
        self.assertEqual(data["stats"]["contextPct"], 60)
        self.assertEqual(data["fields"], {
            "statInput": "120c",
            "statContext": "60%",
            "sessionCreated": "2026-07-19 18:11",
            "sessionUpdated": "2026-07-19 20:13",
            "sessionSource": "sessionSourceClaude",
            "sessionSourceKey": "sessionSourceClaude",
            "sessionFile": "C:/data/session-1.jsonl",
            "sessionFileTitle": "ID: session-1",
            "msgTotal": 4,
            "msgTools": 2,
            "tokenTotal": "150n",
            "tokenCacheWrite": "5n",
            "cacheWriteHidden": False,
            "cacheWriteHiddenWhenMissing": True,
            "tokenContext": "60% · 1000c",
            "usageTitle": "viewSessionInfo",
            "ringStroke": "var(--muted)",
        })
        self.assertEqual(data["systemPromptReadsWithLastUsage"], 0)
        self.assertTrue(data["statsWasOpen"])
        self.assertTrue(data["branchWasOpen"])
        self.assertTrue(data["allClosed"])
        self.assertEqual(data["branchRenders"], 1)
        self.assertEqual(data["fallback"]["contextTokens"], 14)
        self.assertFalse(data["fallback"]["cacheWriteReported"])
        self.assertFalse(data["statsWithoutCacheWrite"]["cacheWriteReported"])
        self.assertEqual(data["absolutePath"], "D:/sessions/s1.jsonl")
        self.assertEqual(data["fallbackPath"], "code/data/sessions/s2.jsonl")
        self.assertEqual(data["codexSource"], "t:sessionSourceCodex")
        self.assertEqual(data["codeSource"], "t:sessionSourceCode")
        self.assertTrue(data["registeredDocumentClick"])
        self.assertEqual(data["shanghaiAware"], "2026-08-22 13:37")
        self.assertEqual(data["legacyNaive"], "2026-08-22 13:37")


    def test_cache_hit_rate_normalization_and_rendering(self):
        self.assertIn("hasCacheReported", MESSAGES_SOURCE)
        self.assertIn("cacheHit", PANELS_SOURCE)
        self.assertIn('id="statCacheHit"', INDEX_SOURCE)
        script = r"""
global.window = {Code: {ui: {}}, setTimeout: (callback) => callback()};
require("./src/ui/messages.js");
require("./src/ui/panels.js");
const { normalizeResponseUsage } = window.Code.ui.messages;
const { calculateSessionStats } = window.Code.ui.panels;
const withCache = normalizeResponseUsage({
  prompt_tokens: 100,
  completion_tokens: 4,
  prompt_tokens_details: {cached_tokens: 80},
});
const withoutCache = normalizeResponseUsage({prompt_tokens: 100, completion_tokens: 4});
const statsBase = {
  getContextMessages: (x) => x,
  estimateTokens: () => 0,
  getMessageText: () => "",
  getSystemPrompt: () => "",
  getContextLimit: () => 100,
};
const hit = calculateSessionStats({
  messages: [],
  stats: {input: 100, output: 4, cache: 80, cacheReported: true},
  ...statsBase,
});
const hitClamped = calculateSessionStats({
  messages: [],
  stats: {input: 50, output: 4, cache: 80, cacheReported: true},
  ...statsBase,
});
const noReport = calculateSessionStats({
  messages: [],
  stats: {input: 100, output: 4, cache: 0},
  ...statsBase,
});
const persistedInferred = calculateSessionStats({
  messages: [],
  stats: {input: 100, output: 4, cache: 80},
  ...statsBase,
});
process.stdout.write(JSON.stringify({
  withCache: {cache: withCache.cache, hasCacheReported: withCache.hasCacheReported},
  withoutCache: {cache: withoutCache.cache, hasCacheReported: withoutCache.hasCacheReported},
  hit: hit.cacheHit,
  hitClamped: hitClamped.cacheHit,
  noReport: noReport.cacheHit,
  persistedInferred: persistedInferred.cacheHit,
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["withCache"], {"cache": 80, "hasCacheReported": True})
        self.assertEqual(data["withoutCache"], {"cache": 0, "hasCacheReported": False})
        self.assertEqual(data["hit"], 0.8)
        self.assertEqual(data["hitClamped"], 1.0)
        self.assertIsNone(data["noReport"])
        self.assertEqual(data["persistedInferred"], 0.8)

    def test_preview_feature_exports_parsing_urls_and_width_rules(self):
        self.assertIn("features.preview = Object.freeze", PREVIEW_SOURCE)
        script = """
global.window = {Code: {features: {}}, innerWidth: 1000};
require("./src/features/preview.js");
const {createPreviewFeature, parseDelimitedText, previewRawUrl} = window.Code.features.preview;
const styles = [];
const storage = [];
const feature = createPreviewFeature({
  state: {previewWidth: 420},
  elements: {},
  apiJson: async () => ({}),
  renderMarkdown: (value) => value,
  document: {documentElement: {style: {setProperty: (...args) => styles.push(args)}}},
  storage: {setItem: (...args) => storage.push(args)},
});
const parsed = parseDelimitedText('name,note\\nAlice,"hello, world"\\nBob,"two\\nlines"\\n');
const limited = parseDelimitedText("a\\nb\\nc\\n", ",", 2);
const wide = feature.applyPreviewWidth(600, false);
const narrow = feature.applyPreviewWidth(100, true);
process.stdout.write(JSON.stringify({
  parsed,
  limited,
  wide,
  narrow,
  styles,
  storage,
  raw: previewRawUrl("folder/a b.pdf", "version 1"),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(
            data["parsed"]["rows"],
            [["name", "note"], ["Alice", "hello, world"], ["Bob", "two\nlines"]],
        )
        self.assertFalse(data["parsed"]["limited"])
        self.assertEqual(data["limited"]["rows"], [["a"], ["b"]])
        self.assertTrue(data["limited"]["limited"])
        self.assertEqual(data["wide"], 480)
        self.assertEqual(data["narrow"], 250)
        self.assertEqual(data["styles"][-1], ["--preview-width", "250px"])
        self.assertEqual(data["storage"], [["code-preview-width", "250"]])
        self.assertEqual(
            data["raw"],
            "/api/file?path=folder%2Fa%20b.pdf&raw=1&v=version%201",
        )

    def test_large_text_preview_stays_internal_without_system_open(self):
        self.assertNotIn('/api/open-file', PREVIEW_SOURCE)
        script = """
global.window = {
  Code: {features: {}},
  innerWidth: 1280,
  setInterval,
  clearInterval,
  addEventListener: () => {},
};
require("./src/features/preview.js");
const {createPreviewFeature} = window.Code.features.preview;
const requests = [];
const responses = [
  {
    ok: true,
    path: "large-characters.txt",
    name: "large-characters.txt",
    content: `H4_CHAR_START\\n${"x".repeat(350001)}`,
    size: 1200000,
    truncated: true,
    binary: false,
    updatedAt: "2026-08-24T05:00:00Z",
  },
  {
    ok: true,
    path: "large-lines.txt",
    name: "large-lines.txt",
    content: Array.from({length: 8001}, (_, index) => `line-${index}`).join("\\n"),
    size: 1200000,
    truncated: true,
    binary: false,
    updatedAt: "2026-08-24T05:00:01Z",
  },
];
const classes = new Set();
const filePreview = {
  className: "",
  innerHTML: "",
  onclick: null,
  querySelector: () => null,
};
const elements = {
  workbench: {classList: {
    add: (name) => classes.add(name),
    contains: (name) => classes.has(name),
  }},
  previewTitle: {textContent: ""},
  previewMeta: {textContent: ""},
  previewLanguage: {textContent: ""},
  refreshPreview: {disabled: true},
  copyPreview: {disabled: true},
  previewModeActions: {replaceChildren: () => {}, appendChild: () => {}},
  filePreview,
};
const storage = [];
const feature = createPreviewFeature({
  state: {previewWidth: 420},
  elements,
  apiJson: async (url, options = {}) => {
    requests.push({url, method: options.method || "GET"});
    if (!url.startsWith("/api/file?path=")) throw new Error(`unexpected request: ${url}`);
    return responses.shift();
  },
  renderMarkdown: (value) => value,
  resolveSyntaxPatterns: () => null,
  document: {
    querySelectorAll: () => [],
    documentElement: {style: {setProperty: () => {}}},
  },
  storage: {
    setItem: (...args) => storage.push(args),
    removeItem: () => {},
  },
  t: (key) => key === "fmtTruncatedContent" ? "TRUNCATED" : key,
  escapeHtml: (value) => String(value ?? ""),
  languageFromPath: () => "text",
  formatSize: (value) => `${value} B`,
});
(async () => {
  await feature.loadFile("large-characters.txt");
  const characters = {
    className: filePreview.className,
    startVisible: filePreview.innerHTML.includes("H4_CHAR_START"),
    truncatedMeta: elements.previewMeta.textContent.includes("TRUNCATED"),
    copyEnabled: elements.copyPreview.disabled === false,
  };
  await feature.loadFile("large-lines.txt");
  const lines = {
    className: filePreview.className,
    count: (filePreview.innerHTML.match(/class="code-line"/g) || []).length,
    truncatedMeta: elements.previewMeta.textContent.includes("TRUNCATED"),
    copyEnabled: elements.copyPreview.disabled === false,
  };
  feature.stopAutoRefresh();
  process.stdout.write(JSON.stringify({characters, lines, requests, storage}));
})().catch((error) => { console.error(error); process.exitCode = 1; });
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(
            data["characters"],
            {
                "className": "file-preview code-preview",
                "startVisible": True,
                "truncatedMeta": True,
                "copyEnabled": True,
            },
        )
        self.assertEqual(data["lines"]["className"], "file-preview code-preview")
        self.assertEqual(data["lines"]["count"], 8001)
        self.assertTrue(data["lines"]["truncatedMeta"])
        self.assertTrue(data["lines"]["copyEnabled"])
        self.assertEqual(
            data["requests"],
            [
                {"url": "/api/file?path=large-characters.txt", "method": "GET"},
                {"url": "/api/file?path=large-lines.txt", "method": "GET"},
            ],
        )
        self.assertIn(["code-preview-open", "1"], data["storage"])
        self.assertIn(["code-preview-path", "large-lines.txt"], data["storage"])

    def test_sidebar_resizers_coalesce_layout_updates_and_defer_persistence(self):
        script = """
const frames = [];
const windowListeners = {};
global.window = {
  Code: {features: {}},
  innerWidth: 1000,
  addEventListener: (type, callback) => { windowListeners[type] = callback; },
  requestAnimationFrame: (callback) => {
    frames.push(callback);
    return frames.length;
  },
  cancelAnimationFrame: () => {},
};
require("./src/features/preview.js");
const {createPreviewFeature} = window.Code.features.preview;
const handlers = {};
const makeEventElement = (name) => ({
  addEventListener: (type, callback) => { handlers[`${name}:${type}`] = callback; },
});
const workbenchClasses = new Set(["preview-open"]);
const bodyClasses = new Set();
const styleWrites = [];
const styleRemovals = [];
const storageWrites = [];
const previewResizer = {
  ...makeEventElement("resizer"),
  setPointerCapture: () => {},
  hasPointerCapture: () => true,
  releasePointerCapture: () => {},
};
const elements = {
  refreshPreview: makeEventElement("refresh"),
  copyPreview: makeEventElement("copy"),
  togglePreview: makeEventElement("toggle"),
  previewResizer,
  workbench: {classList: {contains: (name) => workbenchClasses.has(name)}},
  messageList: {getBoundingClientRect: () => ({width: 640})},
  filePreview: {getBoundingClientRect: () => ({width: 420})},
};
const documentRef = {
  documentElement: {
    style: {
      setProperty: (...args) => styleWrites.push(args),
      removeProperty: (name) => styleRemovals.push(name),
    },
  },
  body: {
    classList: {
      add: (name) => bodyClasses.add(name),
      remove: (name) => bodyClasses.delete(name),
    },
  },
};
const feature = createPreviewFeature({
  state: {previewWidth: 420},
  elements,
  apiJson: async () => ({}),
  renderMarkdown: (value) => value,
  document: documentRef,
  storage: {
    setItem: (...args) => storageWrites.push(args),
    removeItem: () => {},
  },
});
feature.bind();
handlers["resizer:pointerdown"]({clientX: 600, pointerId: 7, preventDefault: () => {}});
handlers["resizer:pointermove"]({clientX: 570});
handlers["resizer:pointermove"]({clientX: 540});
const framesBeforeFlush = frames.length;
const writesBeforeFlush = styleWrites.slice();
const storageBeforeFlush = storageWrites.slice();
frames.shift()();
const writesAfterFlush = styleWrites.slice();
const storageAfterFlush = storageWrites.slice();
handlers["resizer:pointerup"]({pointerId: 7});
process.stdout.write(JSON.stringify({
  framesBeforeFlush,
  writesBeforeFlush,
  storageBeforeFlush,
  writesAfterFlush,
  storageAfterFlush,
  storageWrites,
  styleRemovals,
  resizingAfterFinish: bodyClasses.has("resizing-preview"),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["framesBeforeFlush"], 1)
        self.assertEqual(
            data["writesBeforeFlush"],
            [
                ["--drag-message-list-width", "640px"],
                ["--drag-preview-content-width", "420px"],
            ],
        )
        self.assertEqual(data["storageBeforeFlush"], [])
        self.assertEqual(data["writesAfterFlush"][-1], ["--preview-width", "480px"])
        self.assertEqual(data["storageAfterFlush"], [])
        self.assertEqual(data["storageWrites"], [["code-preview-width", "480"]])
        self.assertEqual(
            data["styleRemovals"],
            ["--drag-message-list-width", "--drag-preview-content-width"],
        )
        self.assertFalse(data["resizingAfterFinish"])

        self.assertIn("function applySidebarWidth(width = state.sidebarWidth, persist = true)", APP_SOURCE)
        self.assertIn("applySidebarWidth(pendingSidebarWidth, false)", APP_SOURCE)
        self.assertIn("applySidebarWidth(pendingSidebarWidth ?? state.sidebarWidth, true)", APP_SOURCE)
        self.assertIn('removeProperty("--drag-message-list-width")', APP_SOURCE)
        self.assertIn(".resizing-sidebar-main :where(.message-list)", STYLE_SOURCE)
        self.assertIn(".resizing-preview .file-preview", STYLE_SOURCE)
        self.assertIn("contain: layout paint", STYLE_SOURCE)
        self.assertIn(".workbench.preview-open {\n    grid-template-columns: minmax(0, 1fr) 0;", STYLE_SOURCE)

    def test_app_uses_extracted_modules_without_duplicate_definitions(self):
        self.assertIn("const { uiIcon } = window.Code.core.icons", APP_SOURCE)
        self.assertIn("} = window.Code.core.utils", APP_SOURCE)
        self.assertIn("const { createI18nRuntime } = window.Code.core.i18n", APP_SOURCE)
        self.assertIn("const { t, setLang, applyI18n } = createI18nRuntime", APP_SOURCE)
        self.assertIn("const { apiJson } = window.Code.services.apiClient", APP_SOURCE)
        self.assertIn("createDiffFeature,", APP_SOURCE)
        self.assertIn("createEditDiffDisclosureState,", APP_SOURCE)
        self.assertIn("getEditSuggestionInstanceId,", APP_SOURCE)
        self.assertIn("} = window.Code.ui.diff;", APP_SOURCE)
        self.assertIn("const diffFeature = createDiffFeature", APP_SOURCE)
        self.assertIn("const { createPreviewFeature } = window.Code.features.preview", APP_SOURCE)
        self.assertIn("const previewFeature = createPreviewFeature", APP_SOURCE)
        self.assertIn("const { createFilesFeature, shortPath } = window.Code.features.files", APP_SOURCE)
        self.assertIn("const filesFeature = createFilesFeature", APP_SOURCE)
        self.assertIn("getSkillToolBudgets,", APP_SOURCE)
        self.assertIn("const skillsMemoryFeature = createSkillsMemoryFeature", APP_SOURCE)
        self.assertIn("createSettingsFeature,", APP_SOURCE)
        self.assertIn("loadFollowUpBehavior,", APP_SOURCE)
        self.assertIn("} = window.Code.features.settings", APP_SOURCE)
        self.assertIn("const settingsFeature = createSettingsFeature", APP_SOURCE)
        self.assertIn("createMarkdownFeature,", APP_SOURCE)
        self.assertIn("const markdownFeature = createMarkdownFeature", APP_SOURCE)
        self.assertIn(
            "const { showToast, notify: _notify } = window.Code.services.notifications",
            APP_SOURCE,
        )
        for legacy_definition in (
            "const UI_ICON_PATHS",
            "function uiIcon(",
            "function escapeHtml(",
            "function formatCompact(",
            "function formatNumber(",
            "function formatElapsed(",
            "function estimateTokens(",
            "function normalizeDiffText(",
            "function getDiffStats(",
            "function renderDiff(",
            "function isEditSuggestionMessage(",
            "function renderEditSuggestionProjection(",
            "const LANG =",
            "const I18N =",
            "function t(key",
            "function setLang(",
            "function applyI18n(",
            "async function apiJson(",
            "function applyPreviewWidth(",
            "function renderPreviewNotice(",
            "function renderCodePreview(",
            "function renderPreviewModeActions(",
            "function sanitizePreviewHtml(",
            "function renderMarkdownPreview(",
            "function parseDelimitedText(",
            "function renderDelimitedTablePage(",
            "function renderDelimitedPreview(",
            "function currentImageFitScale(",
            "function applyImagePreviewScale(",
            "function renderImagePreviewActions(",
            "function renderImagePreview(",
            "function renderPdfPreview(",
            "function markActiveFile(",
            "function formatPreviewMeta(",
            "async function loadFile(",
            "function startPreviewAutoRefresh(",
            "function shortPath(",
            "function arrayBufferToBase64(",
            "async function uploadAttachment(",
            "async function pickProjectFile(",
            "async function resolvePickedFile(",
            "function showFileContextMenu(",
            "function renderFileTree(",
            "async function loadFiles(",
            "function goUpDir(",
            "function toggleCwdDropdown(",
            "function renderRecentFolders(",
            "function addRecentFolder(",
            "async function loadSkills(",
            "async function ensureSkillBody(",
            "async function getMatchedSkillPrompts(",
            "function showSkillsPanel(",
            "function renderSkillsList(",
            "async function showSkillDetail(",
            "function openSkillEditor(",
            "function closeSkillEditor(",
            "async function saveSkillEdit(",
            "function toggleSkill(",
            "async function deleteSkillConfirm(",
            "function showSlashSuggestions(",
            "async function loadMemoryContext(",
            "function updateMemoryContextIndicator(",
            "async function showMemoryPanel(",
            "function hideMemoryPanel(",
            "async function renderMemoryList(",
            "async function editMemory(",
            "async function deleteMemory(",
            "async function saveMemorySubmit(",
            "function renderMemoryPanel(",
            "function clearMemoryForm(",
            "async function refreshSettingsMemoryList(",
            "function renderSkillsInSettings(",
            "function renderSettingsSkillsSidebar(",
            "async function showSkillDetailInSettings(",
            "function loadKeyConfig(",
            "function saveKeyConfig(",
            "function parseKeyLines(",
            "function serializeKeys(",
            "function renderKeyEditor(",
            "function bindKeyEditorEvents(",
            "function showInlineKeyDeleteConfirm(",
            "function applyTheme(",
            "function updateThemeButtons(",
            "function showSettings(",
            "function openSettingsPage(",
            "function switchSettingsPanel(",
            "function renderModelsPanel(",
            "function renderSystemPanel(",
            "function renderLanguagePanel(",
            "function renderThemePanel(",
            "function renderAccountPanel(",
            "function isUpdateNoticeUnread(",
            "function markUpdateNoticeSeen(",
            "function setUpdateNotice(",
            "async function checkForUpdates(",
            "function renderUpdatePanel(",
            "function getPlatformUrl(",
            "function getPlatformAuth(",
            "function savePlatformAuth(",
            "function clearPlatformAuth(",
            "async function checkCodeCallback(",
            "async function syncKeysFromPlatform(",
            "function showKeySyncModal(",
            "const SYNTAX_PATTERNS =",
            "function _resolveSyntaxPatterns(",
            "function highlightSyntax(",
            "function renderAnsi(",
            "function renderMarkdownLite(",
            "function setupMarked(",
            "function showToast(",
            "function _notify(",
        ):
            self.assertNotIn(legacy_definition, APP_SOURCE)

        # Preserve the current duplicate formatSize behavior until its own cleanup.
        self.assertEqual(APP_SOURCE.count("function formatSize("), 2)
        self.assertNotIn('onclick="cwdPickFolderAction()"', INDEX_SOURCE)
        self.assertNotIn('onclick="cwdUseHomeFolder()"', INDEX_SOURCE)

    def test_packaged_exe_includes_runtime_and_module_tree(self):
        self.assertIn("APP_DIR / 'agent-runtime.js'", BUILD_SOURCE)
        self.assertIn("APP_DIR / 'src'", BUILD_SOURCE)
        self.assertIn("f\"{APP_DIR / 'src'}{';'}src\"", BUILD_SOURCE)
        self.assertIn("f\"{FRONTEND_BUNDLE}{';'}dist/frontend\"", BUILD_SOURCE)
        self.assertIn("f\"{FRONTEND_CLASSIC_FALLBACK}{';'}dist/frontend\"", BUILD_SOURCE)
        self.assertIn("APP_DIR / 'code-icon.png'", BUILD_SOURCE)
        self.assertIn("APP_DIR / 'assets'", BUILD_SOURCE)
        self.assertNotIn("code.bundle.js.map", BUILD_SOURCE)
        self.assertNotIn("code.bundle.meta.json", BUILD_SOURCE)

    def test_code_brand_mark_and_minimal_welcome_stay_in_sync(self):
        upper_path = "M80 13A40 40 0 0 1 80 93"
        lower_path = "M80 147A40 40 0 0 1 80 67"
        for source in (INDEX_SOURCE, APP_SOURCE, LOGO_SOURCE):
            self.assertIn(upper_path, source)
            self.assertIn(lower_path, source)
            self.assertIn('stroke="currentColor"', source)
            self.assertNotIn("#2563EB", source)
            self.assertNotIn("#BFDBFE", source)
        self.assertIn(".logo-svg {", STYLE_SOURCE)
        self.assertIn("--brand-mark: #000000;", STYLE_SOURCE)
        self.assertIn("--brand-mark: #ffffff;", STYLE_SOURCE)
        self.assertIn("color: var(--brand-mark);", STYLE_SOURCE)
        self.assertIn("draw.rounded_rectangle", LOGO_EXPORT_SOURCE)
        self.assertIn(
            'draw_mark(draw, "#FFFFFF", SCALE, optical_small_size=True)',
            LOGO_EXPORT_SOURCE,
        )
        self.assertIn('render_transparent_mark("#000000")', LOGO_EXPORT_SOURCE)
        self.assertIn('render_transparent_mark("#FFFFFF")', LOGO_EXPORT_SOURCE)
        self.assertTrue((ROOT / "code-icon.ico").is_file())
        self.assertTrue((ROOT / "code-icon.png").is_file())
        self.assertTrue((ROOT / "assets" / "code-icon.png").is_file())
        self.assertTrue((ROOT / "assets" / "code-logo-black.svg").is_file())
        self.assertTrue((ROOT / "assets" / "code-logo-white.svg").is_file())
        self.assertTrue((ROOT / "assets" / "code-logo-black.png").is_file())
        self.assertTrue((ROOT / "assets" / "code-logo-white.png").is_file())
        self.assertTrue((ROOT / "assets" / "code-wordmark.svg").is_file())
        self.assertIn("function renderCodeWordmark", APP_SOURCE)
        self.assertIn('viewBox="0 0 130 54"', APP_SOURCE)

        welcome_start = APP_SOURCE.index('<div class="welcome-screen">')
        welcome_end = APP_SOURCE.index("clearTimeline();", welcome_start)
        welcome = APP_SOURCE[welcome_start:welcome_end]
        self.assertIn('class="welcome-wordmark welcome-brand-lockup"', welcome)
        self.assertIn('class="welcome-command-line"', welcome)
        self.assertIn('class="welcome-product"', welcome)
        self.assertIn('renderCodeWordmark("welcome-typed-brand")', welcome)
        self.assertIn('class="welcome-travel-caret"', welcome)
        self.assertNotIn('<div class="welcome-product">Code</div>', welcome)
        self.assertNotIn('class="welcome-mark-stage"', welcome)
        self.assertIn('t("welcomeHeadline")', welcome)
        self.assertNotIn('class="welcome-actions"', welcome)
        self.assertNotIn("data-welcome-prompt=", welcome)
        self.assertNotIn("function bindWelcomeActions()", APP_SOURCE)
        self.assertNotIn(".welcome-actions {", STYLE_SOURCE)
        self.assertIn("function playWelcomeMotion(root)", APP_SOURCE)
        self.assertIn('window.matchMedia("(prefers-reduced-motion: reduce)")', APP_SOURCE)
        self.assertIn("const promptRect = els.prompt.getBoundingClientRect();", APP_SOURCE)
        self.assertIn("background: var(--text);", STYLE_SOURCE)
        self.assertIn("@keyframes welcomeCaretType", STYLE_SOURCE)
        self.assertIn("width: min(680px, calc(100% - 48px));", STYLE_SOURCE)
        self.assertIn("welcomeMotion.sloganAnimation = slogan.animate", APP_SOURCE)
        self.assertIn('delay: approachDuration,', APP_SOURCE)
        self.assertIn('duration: revealDuration,', APP_SOURCE)
        self.assertIn('easing: "linear",', APP_SOURCE)
        self.assertIn("const sharedStartTime = document.timeline?.currentTime;", APP_SOURCE)
        self.assertIn(
            "welcomeMotion.travelAnimation.startTime = sharedStartTime;",
            APP_SOURCE,
        )
        self.assertIn(
            "welcomeMotion.sloganAnimation.startTime = sharedStartTime;",
            APP_SOURCE,
        )
        self.assertIn("const approachDuration = 335;", APP_SOURCE)
        self.assertIn("const revealDuration = 780;", APP_SOURCE)
        self.assertIn(
            "const revealTravelDuration = approachDuration + revealDuration;",
            APP_SOURCE,
        )
        self.assertNotIn("const finalDistance = Math.hypot(", APP_SOURCE)
        self.assertIn("const WELCOME_HANDOFF_VARIANTS = [", APP_SOURCE)
        self.assertIn('{ id: "return", weight: 30 }', APP_SOURCE)
        self.assertIn('{ id: "wrap", weight: 30 }', APP_SOURCE)
        self.assertIn('{ id: "relay", weight: 20 }', APP_SOURCE)
        self.assertIn('{ id: "packet", weight: 15 }', APP_SOURCE)
        self.assertIn('{ id: "jump", weight: 5 }', APP_SOURCE)
        self.assertIn("function selectWelcomeHandoffVariant()", APP_SOURCE)
        self.assertIn('sessionStorage.getItem("code.welcomeHandoff")', APP_SOURCE)
        self.assertIn('sessionStorage.setItem("code.welcomeHandoff", selected.id)', APP_SOURCE)
        self.assertIn("function playSelectedWelcomeHandoff(root, context)", APP_SOURCE)
        finish_start = APP_SOURCE.index("function finishWelcomeMotion(")
        finish_end = APP_SOURCE.index("function welcomeBezierPoint", finish_start)
        finish_block = APP_SOURCE[finish_start:finish_end]
        self.assertIn("if (focusPrompt && !els.prompt.disabled) {", finish_block)
        self.assertNotIn("const canMoveFocus", finish_block)
        handoff_finish_start = APP_SOURCE.index("function finishWelcomeHandoff(")
        handoff_finish_end = APP_SOURCE.index("function playWelcomeHardReturn", handoff_finish_start)
        handoff_finish_block = APP_SOURCE[handoff_finish_start:handoff_finish_end]
        self.assertIn("if (!els.prompt.disabled) {", handoff_finish_block)
        self.assertNotIn("const canMoveFocus", handoff_finish_block)
        self.assertIn(
            "scheduleWelcomeMotion(() => finishWelcomeMotion(root, { focusPrompt: true }), 320);",
            handoff_finish_block,
        )
        self.assertIn(
            "scheduleWelcomeMotion(() => playSelectedWelcomeHandoff(root, context), 150);",
            APP_SOURCE,
        )
        self.assertLess(
            APP_SOURCE.index("welcomeMotion.travelAnimation.finished"),
            APP_SOURCE.index("playSelectedWelcomeHandoff(root, context), 150"),
        )
        self.assertIn(".welcome-handoff-trace,", STYLE_SOURCE)
        self.assertIn(".welcome-handoff-beam {", STYLE_SOURCE)
        self.assertIn(".welcome-handoff-signal {", STYLE_SOURCE)
        self.assertIn(".welcome-handoff-mark {", STYLE_SOURCE)
        self.assertIn("@keyframes welcomeComposerLanding", STYLE_SOURCE)
        self.assertNotIn("animation: welcomeRevealSlogan", STYLE_SOURCE)
        self.assertNotIn("@keyframes welcomeRevealSlogan", STYLE_SOURCE)

    def test_user_message_meta_reserves_the_standard_followup_gap(self):
        message_list_start = STYLE_SOURCE.index(".message-list {")
        message_list_end = STYLE_SOURCE.index("}", message_list_start)
        message_list_rule = STYLE_SOURCE[message_list_start:message_list_end]
        self.assertIn("--message-stack-gap: 26px", message_list_rule)
        self.assertIn("--user-message-meta-height: 26px", message_list_rule)
        self.assertIn("--user-message-meta-offset: 2px", message_list_rule)

        user_start = STYLE_SOURCE.index(".msg.user {")
        user_end = STYLE_SOURCE.index("}", user_start)
        user_rule = STYLE_SOURCE[user_start:user_end]
        self.assertIn("var(--message-stack-gap)", user_rule)
        self.assertIn("var(--user-message-meta-height)", user_rule)
        self.assertIn("var(--user-message-meta-offset)", user_rule)

        meta_start = STYLE_SOURCE.index(".msg-meta {")
        meta_end = STYLE_SOURCE.index("}", meta_start)
        meta_rule = STYLE_SOURCE[meta_start:meta_end]
        self.assertIn("height: var(--user-message-meta-height)", meta_rule)
        self.assertIn("margin-top: var(--user-message-meta-offset)", meta_rule)

        modern_message_start = STYLE_SOURCE.rindex(".msg {")
        modern_message_end = STYLE_SOURCE.index("}", modern_message_start)
        modern_message_rule = STYLE_SOURCE[modern_message_start:modern_message_end]
        self.assertIn("margin-bottom: var(--message-stack-gap)", modern_message_rule)

    def test_user_message_time_is_an_escaped_nonshrinking_element(self):
        script = r"""
global.window = {Code: {ui: {}}};
const NativeDate = Date;
global.Date = class extends NativeDate {
  constructor(...args) {
    super(...(args.length ? args : ["2026-08-23T13:00:00+08:00"]));
  }
  static now() { return new NativeDate("2026-08-23T13:00:00+08:00").getTime(); }
};
require("./src/ui/messages.js");
const {createMessagesFeature} = window.Code.ui.messages;
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");
const feature = createMessagesFeature({
  escapeHtml,
  formatCompact: (value) => String(value),
  renderMarkdown: (value) => `<md>${escapeHtml(value)}</md>`,
  t: (key) => key === "yesterday" ? "<昨天>" : key,
  getMessageText: (message) => String(message?.content || ""),
  getBackgroundJob: (id) => id === "job-1" ? {status: "running"} : null,
  getMessages: () => [],
  getSessionId: () => "session-time",
  getSelectedModel: () => "model-1",
  renderAssistantContent: (value) => `<answer>${escapeHtml(value)}</answer>`,
  renderBranchFlow: () => "",
  isEditSuggestionMessage: () => false,
  renderEditSuggestion: () => "",
  getToolActionLabel: (action) => action,
});
const html = feature.projectMessages([{
  id: "message-1",
  role: "user",
  content: "你好",
  _time: "2026-08-22T12:56:00+08:00",
  meta: {
    backgroundDispatch: {id: "job-1"},
    goalOrigin: {
      confirmed: true,
      messageId: "message-1",
      goalId: "goal-1",
      sourceKind: "explicit",
    },
  },
}], {hasActiveRun: false});
process.stdout.write(html);
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "TZ": "Asia/Shanghai"},
            check=True,
        )
        html = completed.stdout
        time_markup = (
            '<time class="msg-time user-message-time" '
            'datetime="2026-08-22T12:56:00+08:00">&lt;昨天&gt; 12:56</time>'
        )
        self.assertIn(time_markup, html)
        self.assertEqual(html.count('class="msg-time user-message-time"'), 1)
        self.assertLess(html.index("goal-message-marker"), html.index("background-dispatch-status"))
        self.assertLess(html.index("background-dispatch-status"), html.index(time_markup))
        self.assertLess(html.index(time_markup), html.index("msg-copy-btn"))
        self.assertIn(
            'time ? `<span class="msg-time">${time}</span>` : ""',
            MESSAGES_SOURCE,
        )

        time_start = STYLE_SOURCE.index(".user-message-time {")
        time_end = STYLE_SOURCE.index("}", time_start)
        time_rule = STYLE_SOURCE[time_start:time_end]
        self.assertIn("display: inline-flex", time_rule)
        self.assertIn("flex: 0 0 auto", time_rule)
        self.assertIn("white-space: nowrap", time_rule)

    def test_same_run_steer_stays_inside_one_execution_trace_without_merging_tool_stages(self):
        script = r"""
global.window = {Code: {ui: {}}};
require("./src/ui/messages.js");
const {createMessagesFeature} = window.Code.ui.messages;
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");
const feature = createMessagesFeature({
  escapeHtml,
  formatCompact: (value) => String(value),
  renderMarkdown: (value) => `<md>${escapeHtml(value)}</md>`,
  t: (key) => key,
  getMessageText: (msg) => String(msg?.content || ""),
  getBackgroundJob: () => null,
  getMessages: () => [],
  getSessionId: () => "session-steer",
  getSelectedModel: () => "model-1",
  renderNetworkRecoveryStatus: () => "",
  renderAssistantContent: (value) => `<answer>${escapeHtml(value)}</answer>`,
  renderBranchFlow: () => "",
  isEditSuggestionMessage: () => false,
  renderEditSuggestion: () => "",
  getToolActionLabel: (action) => `label:${action}`,
});
const messages = [
  {role: "user", content: "original"},
  {role: "assistant", content: "first checkpoint", meta: {
    agentRunId: "run-1",
    toolCalls: [{id: "call-1", function: {
      name: "run_command",
      arguments: '{"command":"git status --short"}',
    }}],
  }},
  {role: "tool-call", meta: {
    agentRunId: "run-1",
    action: "run_command",
    toolCallId: "call-1",
    tool: {action: "run_command", command: "git status --short"},
  }},
  {role: "user", content: "steer instruction", meta: {steerDispatch: {
    agentRunId: "run-1",
    status: "accepted",
  }}},
  {role: "tool-result", content: "clean", meta: {
    agentRunId: "run-1",
    action: "run_command",
    toolCallId: "call-1",
    outcome: "succeeded",
  }},
  {role: "assistant", content: "second checkpoint", meta: {
    agentRunId: "run-1",
    toolCalls: [{id: "call-2", function: {
      name: "read_file",
      arguments: '{"path":"VERSION"}',
    }}],
  }},
  {role: "tool-call", meta: {
    agentRunId: "run-1",
    action: "read_file",
    toolCallId: "call-2",
    tool: {action: "read_file", path: "VERSION"},
  }},
  {role: "user", content: "second steer", meta: {steerDispatch: {
    agentRunId: "run-1",
    status: "accepted",
  }}},
  {role: "tool-result", content: "0.5.32", meta: {
    agentRunId: "run-1",
    action: "read_file",
    toolCallId: "call-2",
    outcome: "succeeded",
  }},
  {role: "assistant", content: "final answer", _responseTime: "44s", meta: {
    agentRunId: "run-1",
  }},
];
process.stdout.write(JSON.stringify({
  completed: feature.projectMessages(messages, {hasActiveRun: false}),
  expanded: feature.projectMessages(messages, {
    hasActiveRun: false,
    expandedExecutionTraces: new Set(["0"]),
  }),
  active: feature.projectMessages(messages.slice(0, 5), {hasActiveRun: true}),
  duplicateCallIds: feature.projectMessages([
    {role: "user", content: "two runs"},
    {role: "assistant", content: "first", meta: {agentRunId: "run-a", toolCalls: [
      {id: "shared-call", function: {name: "read_file", arguments: '{"path":"a.txt"}'}},
    ]}},
    {role: "tool-call", meta: {agentRunId: "run-a", action: "read_file", toolCallId: "shared-call"}},
    {role: "tool-result", content: "A", meta: {agentRunId: "run-a", action: "read_file", toolCallId: "shared-call", outcome: "succeeded"}},
    {role: "assistant", content: "second", meta: {agentRunId: "run-b", toolCalls: [
      {id: "shared-call", function: {name: "read_file", arguments: '{"path":"b.txt"}'}},
    ]}},
    {role: "tool-call", meta: {agentRunId: "run-b", action: "read_file", toolCallId: "shared-call"}},
    {role: "tool-result", content: "B failed", meta: {agentRunId: "run-b", action: "read_file", toolCallId: "shared-call", outcome: "failed", result: {ok: false, error: "B failed"}}},
    {role: "assistant", content: "done"},
  ], {hasActiveRun: false}),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        html = data["completed"]
        self.assertEqual(html.count('class="execution-trace completed"'), 1)
        self.assertEqual(html.count("data-completed-run-status"), 1)
        self.assertEqual(html.count("data-tool-process-block"), 2)
        self.assertEqual(html.count('class="tool-process-stage succeeded single-tool"'), 2)
        trace_body = html.index('class="execution-trace-body"')
        first_checkpoint = html.index("first checkpoint", trace_body)
        first_tools = html.index("data-tool-process-block", first_checkpoint)
        steer = html.index("steer instruction", first_tools)
        second_checkpoint = html.index("second checkpoint", steer)
        second_tools = html.index("data-tool-process-block", second_checkpoint)
        second_steer = html.index("second steer", second_tools)
        final_answer = html.index("final answer", second_steer)
        trace_end = html.rfind("</section>", second_tools, final_answer)
        self.assertLess(trace_body, first_checkpoint)
        self.assertLess(first_checkpoint, first_tools)
        self.assertLess(first_tools, steer)
        self.assertLess(steer, second_checkpoint)
        self.assertLess(second_checkpoint, second_tools)
        self.assertLess(second_tools, second_steer)
        self.assertLess(second_steer, trace_end)
        self.assertLess(trace_end, final_answer)
        self.assertEqual(html.count("<answer>final answer</answer>"), 1)
        self.assertEqual(html.count("execution-trace-persistent"), 2)
        self.assertIn(
            ".execution-trace:not(.is-expanded) > .execution-trace-body > :not(.execution-trace-persistent)",
            STYLE_SOURCE,
        )
        first_stage = html[first_tools:steer]
        self.assertIn('class="tool-process-stage succeeded single-tool"', first_stage)
        self.assertNotIn('class="tool-process-stage running"', first_stage)

        expanded_html = data["expanded"]
        self.assertEqual(
            expanded_html.count('class="execution-trace completed is-expanded"'),
            1,
        )
        expanded_first_tools = expanded_html.index("data-tool-process-block")
        expanded_steer = expanded_html.index("steer instruction", expanded_first_tools)
        expanded_second_tools = expanded_html.index("data-tool-process-block", expanded_steer)
        expanded_second_steer = expanded_html.index("second steer", expanded_second_tools)
        expanded_final = expanded_html.index("final answer", expanded_second_steer)
        self.assertLess(expanded_first_tools, expanded_steer)
        self.assertLess(expanded_steer, expanded_second_tools)
        self.assertLess(expanded_second_tools, expanded_second_steer)
        self.assertLess(expanded_second_steer, expanded_final)

        active_html = data["active"]
        self.assertIn('class="execution-trace active is-expanded"', active_html)
        active_trace_body = active_html.index('class="execution-trace-body"')
        self.assertLess(active_html.index("data-active-run-anchor"), active_trace_body)
        self.assertLess(active_trace_body, active_html.index("first checkpoint"))
        self.assertLess(active_html.index("data-tool-process-block"), active_html.index("steer instruction"))

        duplicate_html = data["duplicateCallIds"]
        self.assertEqual(duplicate_html.count('data-tool-call-id="shared-call"'), 2)
        self.assertEqual(duplicate_html.count('data-agent-run-id="run-a"'), 1)
        self.assertEqual(duplicate_html.count('data-agent-run-id="run-b"'), 1)
        self.assertEqual(duplicate_html.count('class="tool-process-item succeeded"'), 1)
        self.assertEqual(duplicate_html.count('class="tool-process-item failed"'), 1)

    def test_tool_round_projection_is_structured_compact_and_reasoning_safe(self):
        render_start = MESSAGES_SOURCE.index("function projectMessages(")
        assistant_start = MESSAGES_SOURCE.index('if (msg.role === "assistant") {', render_start)
        assistant_end = MESSAGES_SOURCE.index('if (msg.role === "user") {', assistant_start)
        assistant_block = MESSAGES_SOURCE[assistant_start:assistant_end]

        self.assertIn(
            'const streamingProcessRound = msg.streaming',
            assistant_block,
        )
        self.assertIn('["pending", "thinking"].includes(msg._streamProjection)', assistant_block)
        self.assertIn("if (visibleAssistantToolCalls(msg).length) {", assistant_block)
        self.assertIn(
            "if (isInternalGoalOnlyAssistant(msg) && !isPublicProcessCommentary(msg)) continue;",
            assistant_block,
        )
        self.assertIn("if (isPublicProcessCommentary(msg)) {", assistant_block)
        self.assertIn("const hasMeaningfulToolCommentary = Boolean(", assistant_block)
        self.assertIn("if (hasMeaningfulToolCommentary) {", assistant_block)
        self.assertIn("rows.push(renderFinalAssistantProjection(msg, index, assistantOptions))", assistant_block)
        self.assertIn('content: ""', assistant_block)
        self.assertIn("pendingProcess.push", assistant_block)
        self.assertLess(
            assistant_block.index("rows.push(renderFinalAssistantProjection(msg, index, assistantOptions))"),
            assistant_block.index("pendingProcess.push"),
        )
        self.assertIn("if (streamingProcessRound) {", assistant_block)
        self.assertLess(
            assistant_block.index("if (streamingProcessRound) {"),
            assistant_block.rindex("rows.push(renderFinalAssistantProjection(msg, index, assistantOptions))"),
        )
        projection_start = MESSAGES_SOURCE.index("function renderToolProcessProjection")
        projection_end = MESSAGES_SOURCE.index("function renderAssistantResponseInfo", projection_start)
        projection = MESSAGES_SOURCE[projection_start:projection_end]
        self.assertIn("calls.map(getProcessCallView)", projection)
        self.assertIn('class="tool-process-item ${escapeHtml(call.outcome)}"', projection)
        self.assertIn('escapeHtml(t("toolProcessArguments"))', projection)
        self.assertIn('escapeHtml(t("toolProcessResult"))', projection)
        self.assertNotIn('escapeHtml(t("toolProcessModelNote"))', projection)
        self.assertNotIn("collapseRepeatedProcessCalls(calls)", projection)
        self.assertNotIn("msg.thought", projection)
        self.assertNotIn("renderMarkdown(", projection)
        self.assertIn(".tool-process-item {", STYLE_SOURCE)
        self.assertIn(".tool-process-item.failed", STYLE_SOURCE)
        self.assertIn(".tool-process-stage:not([open]) > .tool-process-stage-body", STYLE_SOURCE)
        self.assertIn(".tool-process-stage[open] > summary .tool-process-stage-chevron", STYLE_SOURCE)
        self.assertIn("max-height: min(320px, 42vh)", STYLE_SOURCE)
        self.assertIn(".agent-commentary {", STYLE_SOURCE)
        self.assertIn(".completed-run-status.msg {", STYLE_SOURCE)
        self.assertNotIn(".active-run-line::after", STYLE_SOURCE)
        self.assertNotIn(".completed-run-line::after", STYLE_SOURCE)
        role_style_start = STYLE_SOURCE.rindex(".role {")
        role_style_end = STYLE_SOURCE.index("}", role_style_start)
        role_style = STYLE_SOURCE[role_style_start:role_style_end]
        self.assertIn("font-size: 12px", role_style)
        self.assertIn("line-height: 1.4", role_style)
        self.assertIn("letter-spacing: .015em", role_style)
        self.assertIn('.msg.assistant > .role:not(.is-empty)::after', STYLE_SOURCE)
        role_rule_start = STYLE_SOURCE.index('.msg.assistant > .role:not(.is-empty)::after')
        role_rule_end = STYLE_SOURCE.index("}", role_rule_start)
        role_rule = STYLE_SOURCE[role_rule_start:role_rule_end]
        self.assertIn("min-width: 24px", role_rule)
        self.assertIn("flex: 1 1 auto", role_rule)
        self.assertNotIn("\n  width: 24px;", role_rule)
        process_style_start = STYLE_SOURCE.index(".tool-process {")
        process_style_end = STYLE_SOURCE.index("}", process_style_start)
        self.assertIn("margin-bottom: 12px", STYLE_SOURCE[process_style_start:process_style_end])

        tool_projection_start = APP_SOURCE.index("function projectAgentToolCompleted")
        tool_projection_end = APP_SOURCE.index("async function projectAgentEvent", tool_projection_start)
        tool_projection = APP_SOURCE[tool_projection_start:tool_projection_end]
        self.assertIn("outcome:", tool_projection)
        self.assertIn("result,", tool_projection)
        self.assertIn("argumentAliases:", tool_projection)

    def test_running_tool_group_shimmer_is_scoped_motion_safe_and_layout_neutral(self):
        task_running_selector = ".tool-process-stage.running > .tool-process-stage-summary {"
        group_heading_selector = (
            ".tool-process-stage.tool-active > .tool-process-stage-summary\n"
            "  .tool-process-stage-heading {"
        )
        reduced_heading_selector = (
            "  .tool-process-stage.tool-active > .tool-process-stage-summary\n"
            "    .tool-process-stage-heading {"
        )
        reduced_code_selector = (
            "  .tool-process-stage.tool-active > .tool-process-stage-summary\n"
            "    .tool-process-stage-heading > code {"
        )
        self.assertNotIn(task_running_selector, STYLE_SOURCE)
        self.assertEqual(STYLE_SOURCE.count(group_heading_selector), 1)
        self.assertEqual(STYLE_SOURCE.count(reduced_heading_selector), 1)
        self.assertEqual(STYLE_SOURCE.count(reduced_code_selector), 1)

        rule_start = STYLE_SOURCE.index(group_heading_selector)
        rule_end = STYLE_SOURCE.index("}", rule_start)
        rule = STYLE_SOURCE[rule_start:rule_end]
        self.assertIn("background-color: currentColor", rule)
        self.assertIn("background-image: linear-gradient(", rule)
        self.assertIn("color-mix(in srgb, var(--accent) 78%, var(--text))", rule)
        self.assertEqual(rule.count("color-mix(in srgb, var(--accent) 30%, transparent)"), 2)
        self.assertIn("background-repeat: no-repeat", rule)
        self.assertIn("background-size: 36% 100%", rule)
        self.assertIn("background-position: -58% 0", rule)
        self.assertIn("background-clip: text", rule)
        self.assertIn("-webkit-background-clip: text", rule)
        self.assertIn("-webkit-text-fill-color: transparent", rule)
        self.assertIn("animation: tool-process-stage-text-shimmer 5.2s ease-in-out infinite", rule)
        self.assertNotRegex(
            rule,
            r"(?m)^\s*(?:color|opacity|width|height|padding|border(?:-[\w-]+)?|transform|pointer-events)\s*:",
        )
        self.assertNotIn("mask", rule)
        self.assertNotIn("::before", rule)
        self.assertNotIn("::after", rule)

        keyframes_start = STYLE_SOURCE.index("@keyframes tool-process-stage-text-shimmer {")
        reduced_start = STYLE_SOURCE.index("@media (prefers-reduced-motion: reduce)", keyframes_start)
        keyframes = STYLE_SOURCE[keyframes_start:reduced_start]
        self.assertIn("0%,\n  12%", keyframes)
        self.assertIn("background-position: -58% 0", keyframes)
        self.assertIn("40%,\n  100%", keyframes)
        self.assertIn("background-position: 158% 0", keyframes)
        self.assertAlmostEqual(5.2 * 0.12, 0.6, delta=0.03)
        self.assertAlmostEqual(5.2 * (0.40 - 0.12), 1.46, delta=0.03)
        self.assertAlmostEqual(5.2 * (1 - 0.40), 3.12, delta=0.03)
        self.assertNotRegex(keyframes, r"(?m)^\s*(?:color|opacity|transform)\s*:")

        reduced_rule_start = STYLE_SOURCE.index(reduced_heading_selector, reduced_start)
        reduced_rule_end = STYLE_SOURCE.index("}", reduced_rule_start)
        reduced_rule = STYLE_SOURCE[reduced_rule_start:reduced_rule_end]
        self.assertIn("animation: none", reduced_rule)
        self.assertIn("color: color-mix(in srgb, var(--accent) 46%, var(--text))", reduced_rule)
        self.assertIn("background: none", reduced_rule)
        self.assertIn("-webkit-text-fill-color: currentColor", reduced_rule)
        self.assertNotRegex(
            reduced_rule,
            r"(?m)^\s*(?:opacity|width|height|padding|border(?:-[\w-]+)?|transform|pointer-events)\s*:",
        )

        reduced_code_start = STYLE_SOURCE.index(reduced_code_selector, reduced_rule_end)
        reduced_code_end = STYLE_SOURCE.index("}", reduced_code_start)
        reduced_code_rule = STYLE_SOURCE[reduced_code_start:reduced_code_end]
        self.assertIn("color: color-mix(in srgb, var(--accent) 34%, var(--muted))", reduced_code_rule)
        self.assertIn("-webkit-text-fill-color: currentColor", reduced_code_rule)
        self.assertNotRegex(
            reduced_code_rule,
            r"(?m)^\s*(?:animation|opacity|width|height|padding|border(?:-[\w-]+)?|transform|pointer-events)\s*:",
        )

        self.assertNotIn(".tool-process-stage-heading > strong,", STYLE_SOURCE)
        self.assertIn("const toolIsActive = detectedOutcome", MESSAGES_SOURCE)
        self.assertIn('toolIsActive ? "tool-active" : ""', MESSAGES_SOURCE)
        self.assertIn("const open = (", MESSAGES_SOURCE)
        self.assertIn("const itemOpen = options.allowExpanded", MESSAGES_SOURCE)
        self.assertNotIn("const itemOpen = singleToolStage ||", MESSAGES_SOURCE)
        self.assertNotIn(".tool-process-stage.single-tool .tool-process-item > summary", STYLE_SOURCE)

        self.assertNotIn(".tool-process-item.running > .tool-process-stage-summary", STYLE_SOURCE)
        self.assertNotIn(".edit-suggestion.running > .tool-process-stage-summary", STYLE_SOURCE)

    def test_tool_fold_controls_block_primary_selection_without_disabling_body_copy(self):
        for selector in (
            ".execution-trace-summary {",
            ".tool-process-stage > summary {",
            ".tool-process-item > summary {",
        ):
            rule_start = STYLE_SOURCE.index(selector)
            rule_end = STYLE_SOURCE.index("}", rule_start)
            rule = STYLE_SOURCE[rule_start:rule_end]
            self.assertIn("-webkit-user-select: none", rule)
            self.assertIn("user-select: none", rule)
        self.assertIn(
            ".execution-trace-summary:focus-visible:not(.is-pointer-focus)",
            STYLE_SOURCE,
        )
        self.assertIn(
            ".tool-process-stage > summary:focus-visible:not(.is-pointer-focus)",
            STYLE_SOURCE,
        )
        self.assertIn(
            ".tool-process-item > summary:focus-visible:not(.is-pointer-focus)",
            STYLE_SOURCE,
        )
        self.assertIn(
            ".execution-trace-summary.is-pointer-focus:focus {\n  outline: none;",
            STYLE_SOURCE,
        )
        self.assertIn(
            ".tool-process-stage > summary.is-pointer-focus:focus,\n"
            ".tool-process-item > summary.is-pointer-focus:focus {\n"
            "  outline: none;",
            STYLE_SOURCE,
        )
        sync_start = MESSAGES_SOURCE.index("function syncProjectedElement(")
        sync_end = MESSAGES_SOURCE.index("function reconcileToolProcessItem(", sync_start)
        sync_projection = MESSAGES_SOURCE[sync_start:sync_end]
        self.assertIn(
            'current.classList?.contains?.("is-pointer-focus") === true',
            sync_projection,
        )
        self.assertIn(
            'current.classList?.add?.("is-pointer-focus")',
            sync_projection,
        )

        script = r"""
global.window = global;
window.Code = {ui: {}};
require("./src/ui/messages.js");
const {createMessagesFeature} = window.Code.ui.messages;
const handlers = {};
const root = {
  addEventListener(type, handler, options) {
    handlers[type] = handlers[type] || [];
    handlers[type].push({handler, options});
  },
  contains: () => true,
};
const feature = createMessagesFeature({
  escapeHtml: (value) => String(value ?? ""),
  t: (key) => key,
});
feature.bindInteractions(root);

const FOLD_SELECTOR = "[data-execution-trace-toggle], .tool-process-stage > summary, .tool-process-item > summary";
const INTERACTIVE_SELECTOR = "a, button, input, textarea, select, [contenteditable='true']";
const focusOptions = [];
const attributes = {};
let expanded = true;
let syntheticClicks = 0;
let documentFocused = true;
const pendingFocusCleanups = [];
global.queueMicrotask = (callback) => pendingFocusCleanups.push(callback);
const flushFocusCleanups = () => {
  while (pendingFocusCleanups.length) pendingFocusCleanups.shift()();
};
const ownerDocument = {
  activeElement: null,
  body: null,
  documentElement: null,
  hasFocus: () => documentFocused,
};
ownerDocument.body = {ownerDocument};
ownerDocument.documentElement = {ownerDocument};
const sameDocumentTarget = {ownerDocument};
const controlClasses = new Set();
const trace = {
  classList: {toggle() { expanded = !expanded; return expanded; }},
};
const control = {
  ownerDocument,
  classList: {
    add(value) { controlClasses.add(value); },
    remove(value) { controlClasses.delete(value); },
    contains(value) { return controlClasses.has(value); },
  },
  contains(node) { return node === this.link; },
  focus(options) {
    ownerDocument.activeElement = this;
    focusOptions.push(options || null);
  },
  setAttribute(name, value) { attributes[name] = value; },
  click() {
    syntheticClicks += 1;
    handlers.click[0].handler({target: this});
  },
  closest(selector) {
    if (selector === FOLD_SELECTOR) return this;
    if (selector === "[data-execution-trace-toggle]") return this;
    if (selector === "[data-execution-trace]") return trace;
    return null;
  },
};
const link = {
  closest(selector) {
    if (selector === FOLD_SELECTOR) return control;
    if (selector === INTERACTIVE_SELECTOR) return this;
    return null;
  },
};
control.link = link;
const body = {closest: () => null};

const runMouseDown = (target, button) => {
  let prevented = 0;
  handlers.mousedown[0].handler({
    target,
    button,
    preventDefault() { prevented += 1; },
  });
  return prevented;
};
const primaryPrevented = runMouseDown(control, 0);
const pointerMarked = control.classList.contains("is-pointer-focus");
const secondaryPrevented = runMouseDown(control, 2);
const nestedLinkPrevented = runMouseDown(link, 0);
const bodyPrevented = runMouseDown(body, 0);
handlers.keydown[0].handler({
  target: control,
  key: "Tab",
  preventDefault() { throw new Error("Tab must retain native navigation"); },
});
const keyboardClearedPointerMark = !control.classList.contains("is-pointer-focus");
runMouseDown(control, 0);
documentFocused = false;
handlers.focusout[0].handler({target: control, relatedTarget: null});
flushFocusCleanups();
const pageBlurPreservedPointerMark = control.classList.contains("is-pointer-focus");
documentFocused = true;
const pageRestorePreservedPointerMark = control.classList.contains("is-pointer-focus");
ownerDocument.activeElement = ownerDocument.body;
handlers.focusout[0].handler({target: control, relatedTarget: null});
flushFocusCleanups();
const transientBodyFocusPreservedPointerMark = control.classList.contains("is-pointer-focus");
ownerDocument.activeElement = sameDocumentTarget;
handlers.focusout[0].handler({target: control, relatedTarget: sameDocumentTarget});
flushFocusCleanups();
const sameDocumentFocusClearedPointerMark = !control.classList.contains("is-pointer-focus");
runMouseDown(control, 0);
ownerDocument.activeElement = sameDocumentTarget;
handlers.focusout[0].handler({target: control, relatedTarget: null});
flushFocusCleanups();
const activeElementFocusClearedPointerMark = !control.classList.contains("is-pointer-focus");
runMouseDown(control, 0);
let keyboardPrevented = 0;
handlers.keydown[0].handler({
  target: control,
  key: "Enter",
  preventDefault() { keyboardPrevented += 1; },
});
handlers.keydown[0].handler({
  target: control,
  key: " ",
  preventDefault() { keyboardPrevented += 1; },
});

process.stdout.write(JSON.stringify({
  mouseDownHandlers: handlers.mousedown.length,
  primaryPrevented,
  secondaryPrevented,
  nestedLinkPrevented,
  bodyPrevented,
  focusOptions,
  pointerMarked,
  keyboardClearedPointerMark,
  pageBlurPreservedPointerMark,
  pageRestorePreservedPointerMark,
  transientBodyFocusPreservedPointerMark,
  sameDocumentFocusClearedPointerMark,
  activeElementFocusClearedPointerMark,
  keyboardPrevented,
  syntheticClicks,
  expanded,
  ariaExpanded: attributes["aria-expanded"],
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(json.loads(completed.stdout), {
            "mouseDownHandlers": 1,
            "primaryPrevented": 1,
            "secondaryPrevented": 0,
            "nestedLinkPrevented": 0,
            "bodyPrevented": 0,
            "focusOptions": [
                {"preventScroll": True},
                {"preventScroll": True},
                {"preventScroll": True},
                {"preventScroll": True},
            ],
            "pointerMarked": True,
            "keyboardClearedPointerMark": True,
            "pageBlurPreservedPointerMark": True,
            "pageRestorePreservedPointerMark": True,
            "transientBodyFocusPreservedPointerMark": True,
            "sameDocumentFocusClearedPointerMark": True,
            "activeElementFocusClearedPointerMark": True,
            "keyboardPrevented": 2,
            "syntheticClicks": 2,
            "expanded": True,
            "ariaExpanded": "true",
        })

    def test_tool_process_reconciliation_keeps_group_and_item_identity(self):
        projection_start = MESSAGES_SOURCE.index("function renderToolProcessProjection")
        projection_end = MESSAGES_SOURCE.index("function renderAssistantResponseInfo", projection_start)
        projection = MESSAGES_SOURCE[projection_start:projection_end]
        self.assertIn('data-tool-process-id="${escapeHtml(processId)}"', projection)
        self.assertIn('data-tool-call-id="${escapeHtml(toolCallId)}"', projection)
        self.assertIn('data-tool-process-item-key="${escapeHtml(itemKey)}"', projection)
        self.assertIn("options.allowExpanded", projection)
        self.assertIn("expandedToolItems.has(itemKey)", projection)

        reconcile_start = MESSAGES_SOURCE.index("function reconcileToolProcessNodes(")
        reconcile_end = MESSAGES_SOURCE.index("function createMessagesFeature", reconcile_start)
        reconcile = MESSAGES_SOURCE[reconcile_start:reconcile_end]
        self.assertIn("currentStages = new Map()", reconcile)
        self.assertIn("currentItems = new Map()", reconcile)
        self.assertIn("reconcileToolProcessItem(currentItem, projectedItem)", reconcile)
        self.assertIn("projectedItem.replaceWith?.(currentItem)", reconcile)
        self.assertIn("projectedArticle.replaceWith?.(currentArticle)", reconcile)
        self.assertNotIn("setTimeout", reconcile)
        self.assertNotIn("opacity", reconcile)

        flush_start = MESSAGES_SOURCE.index("const flushProcess = (options = {}) =>")
        flush_end = MESSAGES_SOURCE.index("const openCompletedExecutionTrace", flush_start)
        flush_process = MESSAGES_SOURCE[flush_start:flush_end]
        self.assertIn("const activeForegroundStage = hasActiveRun", flush_process)
        self.assertIn("currentUserIndex === activeUserIndex", flush_process)
        self.assertIn(
            "pendingProcess.every(({ msg }) => !isDetachedProjectionMessage(msg))",
            flush_process,
        )
        self.assertIn(
            "activeStage: Boolean(options.activeStage) || activeForegroundStage",
            flush_process,
        )
        self.assertNotIn("setTimeout", flush_process)

        script = r"""
global.window = global;
window.Code = {ui: {}};
require("./src/ui/messages.js");
const {reconcileToolProcessNodes} = window.Code.ui.messages;

class Element {
  constructor(tagName, attrs = {}) {
    this.tagName = tagName.toUpperCase();
    this.attrs = {...attrs};
    this.attributeChanges = [];
    this.childNodes = [];
    this.parentElement = null;
  }
  get dataset() {
    const output = {};
    for (const [name, value] of Object.entries(this.attrs)) {
      if (!name.startsWith("data-")) continue;
      const key = name.slice(5).replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase());
      output[key] = value;
    }
    return output;
  }
  get className() { return this.attrs.class || ""; }
  getAttributeNames() { return Object.keys(this.attrs); }
  getAttribute(name) { return Object.hasOwn(this.attrs, name) ? this.attrs[name] : null; }
  setAttribute(name, value) {
    const next = String(value);
    if (this.attrs[name] !== next) this.attributeChanges.push({name, action: "set", value: next});
    this.attrs[name] = next;
  }
  removeAttribute(name) {
    if (Object.hasOwn(this.attrs, name)) this.attributeChanges.push({name, action: "remove"});
    delete this.attrs[name];
  }
  append(...nodes) {
    for (const node of nodes) {
      if (node.parentElement) node.parentElement.childNodes = node.parentElement.childNodes.filter((item) => item !== node);
      node.parentElement = this;
      this.childNodes.push(node);
    }
  }
  replaceChildren(...nodes) {
    for (const child of this.childNodes) child.parentElement = null;
    this.childNodes = [];
    this.append(...nodes);
  }
  replaceWith(node) {
    const parent = this.parentElement;
    if (!parent) return;
    const index = parent.childNodes.indexOf(this);
    if (node.parentElement) node.parentElement.childNodes = node.parentElement.childNodes.filter((item) => item !== node);
    parent.childNodes[index] = node;
    node.parentElement = parent;
    this.parentElement = null;
  }
  matches(selector) {
    const first = selector.split(" ").at(-1);
    const tag = first.match(/^[a-z]+/i)?.[0] || "";
    if (tag && this.tagName !== tag.toUpperCase()) return false;
    for (const className of [...first.matchAll(/\.([a-z0-9_-]+)/gi)].map((match) => match[1])) {
      if (!this.className.split(/\s+/).includes(className)) return false;
    }
    for (const attribute of [...first.matchAll(/\[([^\]=]+)(?:="([^"]*)")?\]/g)]) {
      if (!Object.hasOwn(this.attrs, attribute[1])) return false;
      if (attribute[2] != null && this.attrs[attribute[1]] !== attribute[2]) return false;
    }
    return true;
  }
  descendants() { return this.childNodes.flatMap((child) => [child, ...child.descendants()]); }
  querySelectorAll(selector) {
    const normalized = selector.replace(/^:scope\s*>\s*/, "");
    const direct = selector.startsWith(":scope");
    return (direct ? this.childNodes : this.descendants()).filter((node) => node.matches(normalized));
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) {
    let node = this;
    while (node) {
      if (node.matches(selector)) return node;
      node = node.parentElement;
    }
    return null;
  }
}

const el = (tag, attrs, ...children) => {
  const node = new Element(tag, attrs);
  node.append(...children);
  return node;
};
const toolItem = (id, outcome, marker, open = false) => el("details", {
  class: `tool-process-item ${outcome}`,
  "data-tool-call-id": id,
  "data-tool-process-item-key": `session-1:call-1:${id}`,
  ...(open ? {open: ""} : {}),
}, el("summary", {"data-marker": `${marker}-summary`}), el("div", {class: "tool-process-body", "data-marker": marker}));
const group = (outcome, marker, items, open = false) => {
  const stage = el("details", {
    class: `tool-process-stage ${outcome}`,
    "data-tool-process-id": "session-1:call-1",
    "data-tool-process-key": "0:1",
    ...(open ? {open: ""} : {}),
  }, el("summary", {class: "tool-process-stage-summary", "data-marker": `${marker}-summary`}),
     el("div", {class: "tool-process-stage-body", "data-marker": marker},
       el("div", {class: "tool-process-list"}, ...items)));
  return el("article", {class: "msg assistant tool-process"}, stage);
};
const trace = (state, marker, article, expanded = true) => el("section", {
  class: `execution-trace ${state}${expanded ? " is-expanded" : ""}`,
  "data-execution-trace": "0",
}, el("div", {
  class: "execution-trace-summary",
  "aria-expanded": String(expanded),
  "data-marker": `${marker}-summary`,
}), el("div", {class: "execution-trace-body", "data-marker": marker}, article));
const currentItem1 = toolItem("call-1", "running", "old-1", true);
const currentItem2 = toolItem("call-2", "running", "old-2", true);
const currentArticle = group("running", "old-group", [currentItem1, currentItem2], true);
const currentTrace = trace("active", "old-trace", currentArticle, true);
const currentRoot = el("div", {}, currentTrace);
const projectedItem1 = toolItem("call-1", "succeeded", "new-1", true);
const projectedItem2 = toolItem("call-2", "failed", "new-2", true);
const projectedArticle = group("failed", "new-group", [projectedItem1, projectedItem2], true);
const projectedTrace = trace("active", "new-trace", projectedArticle, true);
const projectedRoot = el("div", {}, projectedTrace);
const result = reconcileToolProcessNodes(currentRoot, projectedRoot);
const nextTrace = projectedRoot.querySelector("section.execution-trace[data-execution-trace]");
const nextArticle = projectedRoot.querySelector("article.tool-process");
const nextStage = nextArticle.querySelector("details.tool-process-stage[data-tool-process-id]");
const nextItems = nextStage.querySelectorAll("details.tool-process-item[data-tool-call-id]");

const sequenceItem1 = toolItem("call-1", "running", "sequence-start-1", true);
const sequenceArticle = group("running", "sequence-start", [sequenceItem1], true);
const sequenceRoot = el("div", {}, sequenceArticle);
const sequenceStage = sequenceArticle.querySelector("details.tool-process-stage[data-tool-process-id]");
const sequenceTimeline = [];
let sequenceItem2 = null;
const reconcileSequence = (projectedArticleValue, label) => {
  const projectedRootValue = el("div", {}, projectedArticleValue);
  reconcileToolProcessNodes(sequenceRoot, projectedRootValue);
  sequenceRoot.replaceChildren(...projectedRootValue.childNodes);
  const stage = sequenceRoot.querySelector("details.tool-process-stage[data-tool-process-id]");
  const items = stage.querySelectorAll("details.tool-process-item[data-tool-call-id]");
  if (items.length > 1 && !sequenceItem2) sequenceItem2 = items[1];
  sequenceTimeline.push({
    label,
    sameStage: stage === sequenceStage,
    sameItem1: items[0] === sequenceItem1,
    sameItem2: items.length < 2 || items[1] === sequenceItem2,
    stageOpen: Object.hasOwn(stage.attrs, "open"),
    itemOpen: items.map((item) => Object.hasOwn(item.attrs, "open")),
    itemClasses: items.map((item) => item.className),
  });
};
reconcileSequence(group("running", "gap-after-tool-1", [
  toolItem("call-1", "succeeded", "gap-1", true),
], true), "tool1-completed-model-gap");
reconcileSequence(group("running", "tool-2-started", [
  toolItem("call-1", "succeeded", "tool2-start-1", true),
  toolItem("call-2", "running", "tool2-start-2", false),
], true), "tool2-started");
reconcileSequence(group("running", "gap-after-tool-2", [
  toolItem("call-1", "succeeded", "gap-2-1", true),
  toolItem("call-2", "succeeded", "gap-2-2", false),
], true), "tool2-completed-model-gap");
reconcileSequence(group("succeeded", "terminal", [
  toolItem("call-1", "succeeded", "terminal-1", false),
  toolItem("call-2", "succeeded", "terminal-2", false),
], false), "terminal");
process.stdout.write(JSON.stringify({
  result,
  sameTrace: nextTrace === currentTrace,
  sameArticle: nextArticle === currentArticle,
  sameStage: nextStage === currentArticle.querySelector("details.tool-process-stage[data-tool-process-id]"),
  sameItems: nextItems[0] === currentItem1 && nextItems[1] === currentItem2,
  stageClass: nextStage.className,
  stageOpen: Object.hasOwn(nextStage.attrs, "open"),
  itemClasses: nextItems.map((item) => item.className),
  itemOpen: nextItems.map((item) => Object.hasOwn(item.attrs, "open")),
  stageMarker: nextStage.querySelector(":scope > summary").getAttribute("data-marker"),
  itemMarkers: nextItems.map((item) => item.querySelector(":scope > .tool-process-body").getAttribute("data-marker")),
  traceClass: nextTrace.className,
  traceMarker: nextTrace.querySelector(":scope > .execution-trace-summary").getAttribute("data-marker"),
  sequenceTimeline,
  stageOpenMutations: sequenceStage.attributeChanges.filter((change) => change.name === "open"),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(json.loads(completed.stdout), {
            "result": {"traces": 1, "groups": 1, "items": 2},
            "sameTrace": True,
            "sameArticle": True,
            "sameStage": True,
            "sameItems": True,
            "stageClass": "tool-process-stage failed",
            "stageOpen": True,
            "itemClasses": ["tool-process-item succeeded", "tool-process-item failed"],
            "itemOpen": [True, True],
            "stageMarker": "new-group-summary",
            "itemMarkers": ["new-1", "new-2"],
            "traceClass": "execution-trace active is-expanded",
            "traceMarker": "new-trace-summary",
            "sequenceTimeline": [
                {
                    "label": "tool1-completed-model-gap",
                    "sameStage": True,
                    "sameItem1": True,
                    "sameItem2": True,
                    "stageOpen": True,
                    "itemOpen": [True],
                    "itemClasses": ["tool-process-item succeeded"],
                },
                {
                    "label": "tool2-started",
                    "sameStage": True,
                    "sameItem1": True,
                    "sameItem2": True,
                    "stageOpen": True,
                    "itemOpen": [True, False],
                    "itemClasses": ["tool-process-item succeeded", "tool-process-item running"],
                },
                {
                    "label": "tool2-completed-model-gap",
                    "sameStage": True,
                    "sameItem1": True,
                    "sameItem2": True,
                    "stageOpen": True,
                    "itemOpen": [True, False],
                    "itemClasses": ["tool-process-item succeeded", "tool-process-item succeeded"],
                },
                {
                    "label": "terminal",
                    "sameStage": True,
                    "sameItem1": True,
                    "sameItem2": True,
                    "stageOpen": False,
                    "itemOpen": [False, False],
                    "itemClasses": ["tool-process-item succeeded", "tool-process-item succeeded"],
                },
            ],
            "stageOpenMutations": [{"name": "open", "action": "remove"}],
        })

    def test_streaming_projection_switches_kind_without_leaking_raw_reasoning(self):
        projection_start = MESSAGES_SOURCE.index("function renderFinalAssistantProjection")
        projection_end = MESSAGES_SOURCE.index("function projectMessages", projection_start)
        projection = MESSAGES_SOURCE[projection_start:projection_end]

        self.assertIn('data-stream-session="${escapeHtml(getSessionId() || "")}"', projection)
        self.assertIn('msg._streamProjection === "thinking"', projection)
        self.assertIn('data-stream-kind="${streamKind}"', projection)
        self.assertIn('streamKind === "pending" ? " is-pending" : ""', projection)
        self.assertIn('data-stream-role', projection)
        self.assertIn('streaming-answer-role${showModel ? "" : " is-empty"}', projection)
        self.assertIn('streamKind !== "pending"', projection)
        self.assertIn("&& hasVisibleContent", projection)
        self.assertIn('streamKind === "thinking" && isOperationalToolNotice(content)', projection)
        self.assertNotIn('data-stream-part="thought"', projection)
        self.assertNotIn("msg.thought", projection)
        patch_start = APP_SOURCE.index("function patchStreamingAssistantMessage")
        patch_end = APP_SOURCE.index("function scheduleStreamingAssistantPatch", patch_start)
        patch = APP_SOURCE[patch_start:patch_end]
        self.assertIn('if (streamKind === "pending")', patch)
        self.assertIn("scheduleStreamingAnswerProjection(sessionId, index)", patch)
        self.assertIn('msg._streamProjection === "pending" && visibleContent', patch)
        self.assertLess(
            patch.index("scheduleStreamingAnswerProjection(sessionId, index)"),
            patch.index("const article = els.messages.querySelector"),
        )
        self.assertIn('data-stream-part="answer"', patch)
        self.assertIn("renderMarkdownLite(visibleContent)", patch)
        self.assertIn('streamKind === "pending" || !visibleContent', patch)
        self.assertNotIn("preservedNodes", APP_SOURCE)
        self.assertNotIn("appendChild(preservedNode)", APP_SOURCE)

        self.assertIn('_streamProjection: "pending"', APP_SOURCE)
        self.assertIn("const STREAM_PROJECTION_GRACE_MS = 180", APP_SOURCE)

        render_start = APP_SOURCE.index("function renderMessages()")
        render_end = APP_SOURCE.index("function isProcessMessage", render_start)
        render = APP_SOURCE[render_start:render_end]
        self.assertIn("projectedMessageList.innerHTML = html", render)
        self.assertIn("reconcileToolProcessNodes(els.messageList, projectedMessageList)", render)
        self.assertNotIn("els.messageList.innerHTML = html", render)
        self.assertNotIn("els.messages.innerHTML = html", render)
        self.assertIn("pruneStaleStreamingNodes(state.sessionId)", render)

    def test_auto_context_compaction_is_rendered_inside_execution_trace(self):
        self.assertIn('kind: "auto-context-compaction"', APP_SOURCE)
        self.assertIn("function renderAutoContextCompaction(msg, index)", MESSAGES_SOURCE)
        self.assertIn('msg.meta?.kind === "auto-context-compaction"', MESSAGES_SOURCE)
        self.assertIn('data-context-compaction', MESSAGES_SOURCE)
        self.assertIn('t(labelKey)', MESSAGES_SOURCE)
        self.assertIn(".context-compaction-row {", STYLE_SOURCE)
        self.assertIn(".context-compaction-row.running", STYLE_SOURCE)
        for key in (
            "autoCompactingContext",
            "autoCompactedContext",
            "autoCompactContextFailed",
        ):
            self.assertIn(key, I18N_SOURCE)
        helper_start = APP_SOURCE.index("function internalCompactionRuntimeIds")
        helper_end = APP_SOURCE.index("function releaseAttachedImagePreview", helper_start)
        helper_source = APP_SOURCE[helper_start:helper_end]
        script = f"""
eval({json.dumps(helper_source)});
const ctx = {{messages: [
  {{role:"user",content:"task"}},
  {{role:"assistant",content:"CONTEXT CHECKPOINT",streaming:false,meta:{{agentRuntimeRunId:"runtime-compact"}}}},
  {{role:"assistant",content:"",meta:{{kind:"auto-context-compaction",compactionId:"compact-1"}}}},
  {{role:"assistant",content:"PUBLIC FINAL",meta:{{agentRuntimeRunId:"runtime-final"}}}},
]}};
const detected = snapshotActiveCompactionRuntimeId({{
  activeRuntimeRunId:"runtime-compact",
  events:[{{type:"context_compaction_started",data:{{compactionId:"compact-1"}}}}],
}});
const closedBatch = snapshotActiveCompactionRuntimeId({{
  activeRuntimeRunId:"runtime-final",
  events:[
    {{type:"context_compaction_started",data:{{compactionId:"compact-1"}}}},
    {{type:"context_compaction_completed",data:{{compactionId:"compact-1",runtimeRunId:"runtime-compact"}}}},
  ],
}});
const marked = markInternalCompactionRuntime(ctx, detected);
const afterMark = ctx.messages.map((message) => ({{content:message.content,kind:message.meta?.kind||""}}));
const active = internalCompactionRuntimeIds(ctx).has("runtime-compact");
clearInternalCompactionRuntime(ctx, "runtime-compact");
process.stdout.write(JSON.stringify({{detected,closedBatch,marked,afterMark,active,cleared:internalCompactionRuntimeIds(ctx).size}}));
"""
        completed = subprocess.run(
            ["node", "-e", script], cwd=ROOT, check=True,
            capture_output=True, text=True, encoding="utf-8",
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["detected"], "runtime-compact")
        self.assertEqual(data["closedBatch"], "")
        self.assertEqual(data["marked"], "runtime-compact")
        self.assertTrue(data["active"])
        self.assertEqual(data["cleared"], 0)
        self.assertNotIn("CONTEXT CHECKPOINT", [item["content"] for item in data["afterMark"]])
        self.assertIn("PUBLIC FINAL", [item["content"] for item in data["afterMark"]])
        self.assertIn("auto-context-compaction", [item["kind"] for item in data["afterMark"]])
        self.assertIn("skipExport: true", APP_SOURCE)
        self.assertIn("internalCompactionRuntimeRunId", APP_SOURCE)
        self.assertIn("snapshotActiveCompactionRuntimeId(snapshot)", APP_SOURCE)
        self.assertIn("removeInternalCompactionRuntimeProjection(ctx, runtimeRunId)", APP_SOURCE)
        export_start = APP_SOURCE.index("function exportMarkdown()")
        export_end = APP_SOURCE.index("let sidebarDragState", export_start)
        self.assertIn("!msg?.meta?.skipExport", APP_SOURCE[export_start:export_end])

    def test_tool_round_finalization_is_atomic(self):
        helper_start = APP_SOURCE.index("function finalizeStreamingAssistantMessage")
        helper_end = APP_SOURCE.index("function updateUsage", helper_start)
        helper = APP_SOURCE[helper_start:helper_end]
        self.assertIn(
            "updateAssistantMessage(index, rawContent, false, sessionId, targetMessages, true)",
            helper,
        )
        self.assertIn("const visibleToolCalls =", helper)
        self.assertLess(
            helper.index("current.meta.toolCalls = visibleToolCalls"),
            helper.index("renderSessionMessages"),
        )
        self.assertIn("!isInternalGoalToolName(call?.function?.name)", helper)

    def test_agent_run_usage_internal_goal_tools_and_visible_tool_activity_are_projected_once(self):
        script = r"""
global.window = global;
global.Code = {ui: {}};
require("./src/ui/messages.js");
const feature = Code.ui.messages.createMessagesFeature({
  escapeHtml: (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;"),
  formatCompact: (value) => String(value),
  renderMarkdown: (value) => String(value),
  renderAssistantContent: (value) => String(value),
  getMessageText: (message) => String(message?.content || ""),
  getSessionId: () => "session-goal-projection",
  getSelectedModel: () => "test-model",
  getToolActionLabel: (name) => String(name),
  t: (key) => key,
});
const runMeta = {agentRunId: "run-1", agentClientRequestId: "request-1"};
const completed = [
  {role: "user", content: "goal task"},
  {
    role: "assistant",
    content: "INTERNAL GOAL COMMENTARY",
    meta: {
      ...runMeta,
      publicProcessCommentary: true,
      toolCalls: [{id: "goal-1", function: {name: "goal_create", arguments: "{}"}}],
      _usage: {input: 10, output: 1, cache: 2},
    },
  },
  {role: "tool-call", content: "INTERNAL CALL", meta: {...runMeta, action: "goal_create", toolCallId: "goal-1"}},
  {role: "tool-result", content: "INTERNAL RESULT", meta: {...runMeta, action: "goal_create", toolCallId: "goal-1", outcome: "succeeded", result: {ok: true}}},
  {
    role: "assistant",
    content: "checking source",
    meta: {
      ...runMeta,
      toolCalls: [{id: "read-1", function: {name: "read_file", arguments: '{"path":"app.js"}'}}],
      _usage: {input: 20, output: 2, cache: 3},
    },
  },
  {role: "tool-call", content: "", meta: {...runMeta, action: "read_file", toolCallId: "read-1", tool: {action: "read_file", path: "app.js"}}},
  {role: "tool-result", content: "source", meta: {...runMeta, action: "read_file", toolCallId: "read-1", outcome: "succeeded", result: {ok: true, path: "app.js"}}},
  {role: "assistant", content: "FINAL ANSWER", meta: {...runMeta, _usage: {input: 30, output: 3, cache: 4}}},
];
const completedHtml = feature.projectMessages(completed, {hasActiveRun: true});
const restoredProcess = [
  {role: "user", content: "restored Goal process"},
  {
    role: "assistant",
    content: "RESTORED PUBLIC GOAL PROCESS",
    meta: {
      ...runMeta,
      publicProcessCommentary: true,
      toolCalls: [{id: "goal-restored", function: {name: "goal_complete_step", arguments: "{}"}}],
    },
  },
  {role: "tool-call", content: "HIDDEN GOAL CALL", meta: {...runMeta, action: "goal_complete_step", toolCallId: "goal-restored"}},
  {role: "tool-result", content: "HIDDEN GOAL RESULT", meta: {...runMeta, action: "goal_complete_step", toolCallId: "goal-restored", outcome: "succeeded"}},
  {role: "assistant", content: "RESTORED FINAL", _responseTime: "4s", meta: {...runMeta}},
];
const restoredHtml = feature.projectMessages(restoredProcess, {hasActiveRun: false});
const restoredRefreshHtml = feature.projectMessages(
  JSON.parse(JSON.stringify(restoredProcess)),
  {hasActiveRun: false},
);
const streamingProcess = [
  {role: "user", content: "live Goal process"},
  {
    role: "assistant",
    content: "LIVE PUBLIC GOAL PROCESS",
    streaming: true,
    _streamProjection: "thinking",
    meta: {...runMeta},
  },
];
const streamingProcessHtml = feature.projectMessages(streamingProcess, {hasActiveRun: true});
const taskScoped = [
  {role: "user", content: "task scoped"},
  {role: "assistant", content: "round", meta: {agentRunId: "run-2", _usage: {input: 7, output: 1, cache: 0}}},
  {role: "assistant", content: "TASK FINAL", meta: {agentRunId: "run-2", _usage: {input: 99, output: 8, cache: 6}, _usageScope: "task"}},
];
const taskHtml = feature.projectMessages(taskScoped, {hasActiveRun: false});
const pending = [
  {role: "user", content: "pending tool"},
  {role: "assistant", content: "reading", meta: {agentRunId: "run-3", toolCalls: [{id: "read-2", function: {name: "read_file", arguments: "{}"}}]}},
];
const pendingHtml = feature.projectMessages(pending, {hasActiveRun: true});
const handoff = [
  {role: "user", content: "long Goal", id: "origin-4"},
  {
    role: "assistant",
    content: "PUBLIC HANDOFF CHECKPOINT",
    meta: {
      agentRunId: "run-4",
      agentClientRequestId: "request-4",
      agentUsageGroupId: "origin-4",
      toolCalls: [{id: "read-4", function: {name: "read_file", arguments: '{"path":"server.py"}'}}],
      _usage: {input: 44, output: 4, cache: 0},
      _usageScope: "task",
      _usageGroupTerminal: false,
    },
  },
  {role: "tool-call", content: "", meta: {agentRunId: "run-4", action: "read_file", toolCallId: "read-4"}},
  {role: "tool-result", content: "source", meta: {agentRunId: "run-4", action: "read_file", toolCallId: "read-4", outcome: "succeeded", result: {ok: true}}},
  {
    role: "assistant",
    content: "Reading fixture.txt…",
    meta: {
      agentRunId: "run-4",
      agentClientRequestId: "request-4",
      agentUsageGroupId: "origin-4",
      toolCalls: [{id: "read-5", function: {name: "read_file", arguments: '{"path":"fixture.txt"}'}}],
    },
  },
  {role: "tool-call", content: "", meta: {agentRunId: "run-4", action: "read_file", toolCallId: "read-5"}},
  {role: "tool-result", content: "source", meta: {agentRunId: "run-4", action: "read_file", toolCallId: "read-5", outcome: "succeeded", result: {ok: true}}},
];
const handoffHtml = feature.projectMessages(handoff, {hasActiveRun: false});
const completedHandoff = [
  ...handoff,
  {
    role: "assistant",
    content: "SUCCESSOR FINAL",
    meta: {
      agentRunId: "run-5",
      agentClientRequestId: "request-5",
      agentUsageGroupId: "origin-4",
      _usage: {input: 6, output: 2, cache: 1},
      _usageScope: "task",
      _usageGroupTerminal: true,
    },
  },
];
const completedHandoffHtml = feature.projectMessages(completedHandoff, {hasActiveRun: false});
const threeRuns = [
  {role: "user", content: "three runs", id: "origin-6"},
  {role: "assistant", content: "run a old", meta: {agentRunId: "run-a", agentUsageGroupId: "origin-6", _usage: {input: 9, output: 1, cache: 1}, _usageScope: "task", _usageGroupTerminal: false}},
  {role: "assistant", content: "run a refreshed", meta: {agentRunId: "run-a", agentUsageGroupId: "origin-6", _usage: {input: 10, output: 2, cache: 2}, _usageScope: "task", _usageGroupTerminal: false}},
  {role: "assistant", content: "run b", meta: {agentRunId: "run-b", agentUsageGroupId: "origin-6", _usage: {input: 20, output: 3, cache: 4}, _usageScope: "task", _usageGroupTerminal: false}},
  {role: "assistant", content: "run c final", meta: {agentRunId: "run-c", agentUsageGroupId: "origin-6", _usage: {input: 30, output: 5, cache: 6}, _usageScope: "task", _usageGroupTerminal: true}},
];
const threeRunsHtml = feature.projectMessages(threeRuns, {hasActiveRun: false});
const threeRunsRefreshHtml = feature.projectMessages(JSON.parse(JSON.stringify(threeRuns)), {hasActiveRun: false});
const separateTurns = [
  {role: "user", content: "first", id: "origin-7"},
  {role: "assistant", content: "first final", meta: {agentRunId: "run-7", agentUsageGroupId: "origin-7", _usage: {input: 7, output: 1}, _usageScope: "task", _usageGroupTerminal: true}},
  {role: "user", content: "second", id: "origin-8"},
  {role: "assistant", content: "second final", meta: {agentRunId: "run-8", agentUsageGroupId: "origin-8", _usage: {input: 8, output: 2}, _usageScope: "task", _usageGroupTerminal: true}},
];
const separateTurnsHtml = feature.projectMessages(separateTurns, {hasActiveRun: false});
process.stdout.write(JSON.stringify({
  completedHtml,
  restoredHtml,
  restoredRefreshHtml,
  streamingProcessHtml,
  taskHtml,
  pendingHtml,
  handoffHtml,
  completedHandoffHtml,
  threeRunsHtml,
  threeRunsRefreshHtml,
  separateTurnsHtml,
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        completed_html = data["completedHtml"]
        self.assertEqual(completed_html.count('class="response-info"'), 1)
        self.assertIn('data-usage-kind="input"', completed_html)
        self.assertIn(">60</span>", completed_html)
        self.assertIn(">6</span>", completed_html)
        self.assertIn("INTERNAL GOAL COMMENTARY", completed_html)
        self.assertIn('class="msg assistant agent-commentary', completed_html)
        self.assertNotIn("INTERNAL CALL", completed_html)
        self.assertNotIn("INTERNAL RESULT", completed_html)
        self.assertNotIn("goal_create", completed_html)
        self.assertEqual(completed_html.count('data-tool-call-id="read-1"'), 1)
        self.assertIn('class="tool-process-stage running single-tool"', completed_html)
        self.assertNotIn('class="tool-process-stage running tool-active', completed_html)
        self.assertIn("RESTORED PUBLIC GOAL PROCESS", data["restoredHtml"])
        self.assertIn("RESTORED FINAL", data["restoredHtml"])
        self.assertIn('class="execution-trace completed"', data["restoredHtml"])
        self.assertNotIn('class="execution-trace completed is-expanded"', data["restoredHtml"])
        self.assertNotIn("goal_complete_step", data["restoredHtml"])
        self.assertNotIn("HIDDEN GOAL CALL", data["restoredHtml"])
        self.assertNotIn("HIDDEN GOAL RESULT", data["restoredHtml"])
        self.assertEqual(data["restoredHtml"], data["restoredRefreshHtml"])
        self.assertIn("LIVE PUBLIC GOAL PROCESS", data["streamingProcessHtml"])
        self.assertIn('class="execution-trace active is-expanded"', data["streamingProcessHtml"])
        self.assertIn('data-stream-kind="thinking"', data["streamingProcessHtml"])
        self.assertEqual(data["taskHtml"].count('class="response-info"'), 1)
        self.assertIn(">99</span>", data["taskHtml"])
        self.assertNotIn(">106</span>", data["taskHtml"])
        self.assertIn('class="tool-process-stage running tool-active single-tool"', data["pendingHtml"])
        self.assertIn("PUBLIC HANDOFF CHECKPOINT", data["handoffHtml"])
        self.assertEqual(data["handoffHtml"].count('class="response-info"'), 0)
        self.assertEqual(data["handoffHtml"].count('data-tool-call-id="read-4"'), 1)
        self.assertEqual(data["completedHandoffHtml"].count('class="response-info"'), 1)
        self.assertIn(">50</span>", data["completedHandoffHtml"])
        self.assertIn(">6</span>", data["completedHandoffHtml"])
        self.assertIn(">1</span>", data["completedHandoffHtml"])
        self.assertEqual(data["threeRunsHtml"].count('class="response-info"'), 1)
        self.assertIn(">60</span>", data["threeRunsHtml"])
        self.assertIn(">10</span>", data["threeRunsHtml"])
        self.assertIn(">12</span>", data["threeRunsHtml"])
        self.assertEqual(data["threeRunsHtml"], data["threeRunsRefreshHtml"])
        self.assertEqual(data["separateTurnsHtml"].count('class="response-info"'), 2)
        self.assertIn(">7</span>", data["separateTurnsHtml"])
        self.assertIn(">8</span>", data["separateTurnsHtml"])

        attach_start = APP_SOURCE.index("function attachCompletedAgentUsage")
        attach_end = APP_SOURCE.index("function findLastAssistantMessage", attach_start)
        attach_source = APP_SOURCE[attach_start:attach_end]
        self.assertIn("snapshot?.usage || ctx.taskUsage", attach_source)
        self.assertIn("attachTaskUsageToAssistant(", attach_source)
        self.assertIn("_agentRunTerminal: true", attach_source)
        self.assertIn("_usageGroupTerminal: options.groupTerminal !== false", APP_SOURCE)
        self.assertIn("attachCompletedAgentUsage(ctx, snapshot, { groupTerminal: false })", APP_SOURCE)
        self.assertIn("ctx.agentUsageGroupId = foregroundOriginMessageId", APP_SOURCE)
        sync_start = APP_SOURCE.index("function syncTrustedGoalMessageMetadata")
        sync_end = APP_SOURCE.index("async function saveSessionState", sync_start)
        sync_source = APP_SOURCE[sync_start:sync_end]
        self.assertIn('origin.sourceKind === "explicit"', sync_source)
        self.assertIn('completion.sourceKind === "explicit"', sync_source)
        self.assertIn("meta._agentRunTerminal === true", sync_source)
        self.assertIn("delete message.meta.goalCompletion", sync_source)
        self.assertIn(
            "syncTrustedGoalMessageMetadata(messages, savedSession?.messages)",
            APP_SOURCE,
        )
        model_start = APP_SOURCE.index("function projectAgentModelCompleted")
        model_end = APP_SOURCE.index("function findAgentCompactionProjection", model_start)
        model_source = APP_SOURCE[model_start:model_end]
        self.assertIn(
            "const publicProcessCommentary = data.internalOnlyToolCalls === true || toolCalls.length > 0",
            model_source,
        )
        self.assertIn("publicProcessCommentary: true", model_source)
        self.assertNotIn("ctx.messages.splice(index, 1)", model_source)
        self.assertNotIn("assistant.meta._usage =", model_source)

        stream_start = APP_SOURCE.index("const reader = createSseDataReader(res.body)")
        stream_end = APP_SOURCE.index("function _safeMd", stream_start)
        stream = APP_SOURCE[stream_start:stream_end]
        self.assertIn("const turnEvent = turnAccumulator.consume(data)", stream)
        self.assertNotIn("new TextDecoder()", stream)
        self.assertNotIn("buffer +=", stream)
        self.assertIn(
            'markStreamingAssistantProjection(assistantIndex, "thinking"',
            stream,
        )
        self.assertIn("const serverOwnedProjection = isServerOwnedRun(ctx)", stream)
        self.assertIn(
            "{ publicProcessCommentary: serverOwnedProjection && toolCalls.length > 0 }",
            stream,
        )
        self.assertIn("visibleFinalText || toolProgressSummary(visibleToolCalls)", stream)
        self.assertNotIn("visibleFinalText || toolProgressSummary(toolCalls)", stream)
        self.assertIn("serverOwnedProjection ? turnEvent.text", stream)
        self.assertNotIn("deferServerOwnedProjection", stream)
        self.assertNotIn("serverOwnedProjectionVisible", stream)
        self.assertNotIn("internalGoalOnly", stream)
        self.assertEqual(stream.count("finalizeStreamingAssistantMessage("), 1)

        tool_completion_start = APP_SOURCE.index("function projectAgentToolCompleted")
        tool_completion_end = APP_SOURCE.index("async function projectAgentEvent", tool_completion_start)
        tool_completion = APP_SOURCE[tool_completion_start:tool_completion_end]
        self.assertGreaterEqual(
            tool_completion.count('String(msg?.meta?.agentRunId || "") === String(ctx.agentRunId || "")')
            + tool_completion.count('String(message?.meta?.agentRunId || "") === String(ctx.agentRunId || "")'),
            2,
        )

    def test_active_run_banner_uses_one_stable_task_status(self):
        helper_start = APP_SOURCE.index("function ensureActiveRunBannerStructure")
        helper_end = APP_SOURCE.index("function cloneUsageStats", helper_start)
        helper = APP_SOURCE[helper_start:helper_end]
        self.assertEqual(helper.count("banner.innerHTML ="), 1)
        self.assertIn("nodes.label.textContent = getActiveRunLabel(sessionId)", helper)
        self.assertIn("nodes.timer.textContent = getRunTimerDisplay(sessionId)", helper)
        self.assertIn('nodes.timer.title = t("taskElapsedTitle")', helper)
        self.assertIn("data-task-elapsed", helper)
        self.assertNotIn("run-model", helper)
        self.assertNotIn("data-active-run-phase", helper)
        self.assertNotIn("function setTaskPhase", APP_SOURCE)
        self.assertNotIn("_taskPhase", APP_SOURCE)
        self.assertNotIn("executingTool", APP_SOURCE)
        label_start = APP_SOURCE.index("function getActiveRunLabel")
        label_end = APP_SOURCE.index("function markModelResponseStarted", label_start)
        label_helper = APP_SOURCE[label_start:label_end]
        self.assertIn(
            'if (run?.hasFirstModelResponseStarted) return t("processedLabel");',
            label_helper,
        )
        self.assertNotIn("run.modelRound", label_helper)
        self.assertNotIn('"waitingForModelContinuation"', label_helper)
        self.assertNotIn('"modelContinuationDelayed"', label_helper)
        self.assertNotIn('"processingLabel"', label_helper)
        self.assertTrue(label_helper.rstrip().endswith('return t("waitingForModelResponse");\n}'))

        response_start = APP_SOURCE.index("function markModelResponseStarted")
        response_end = APP_SOURCE.index("function getRecoveryCountdownSeconds", response_start)
        response_helper = APP_SOURCE[response_start:response_end]
        self.assertIn("run.hasFirstModelResponseStarted = true;", response_helper)
        self.assertLess(
            response_helper.index("run.hasFirstModelResponseStarted = true;"),
            response_helper.index("if (run.modelResponseStarted) return firstResponseStarted;"),
        )

        self.assertIn("hasFirstModelResponseStarted: false", STATE_SOURCE)
        self.assertIn(
            "hasFirstModelResponseStarted: Boolean(ctx.run?.hasFirstModelResponseStarted)",
            APP_SOURCE,
        )
        self.assertIn("function hasRecoveredModelResponse", APP_SOURCE)
        self.assertIn("ctx.run.hasFirstModelResponseStarted = Boolean(", APP_SOURCE)
        self.assertIn("runState.hasFirstModelResponseStarted", APP_SOURCE)
        self.assertIn("hasRecoveredModelResponse(messages, runState)", APP_SOURCE)
        send_start = APP_SOURCE.index("async function sendMessage")
        send_end = APP_SOURCE.index("function getSelectedModel", send_start)
        self.assertIn("run.hasFirstModelResponseStarted = false;", APP_SOURCE[send_start:send_end])

        timer_start = APP_SOURCE.index("function startLiveTimer()")
        timer_end = APP_SOURCE.index("function finalizeRunTiming", timer_start)
        timer_helper = APP_SOURCE[timer_start:timer_end]
        self.assertNotIn("getActiveRunLabel", timer_helper)
        self.assertNotIn("data-active-run-label", timer_helper)
        self.assertIn('taskElapsedTitle: "任务总耗时"', I18N_SOURCE)
        self.assertIn('taskElapsedTitle: "Total task time"', I18N_SOURCE)
        self.assertIn("modelRound: Number(extra.modelRound", APP_SOURCE)
        self.assertIn("ctx.run.modelRound = Number(runState.modelRound || 0)", APP_SOURCE)

    def test_persisted_run_presentation_hydrates_before_network_recovery(self):
        helper_start = APP_SOURCE.index("const PERSISTED_ACTIVE_RUN_STATUSES")
        helper_end = APP_SOURCE.index("function syncActiveStreamingState", helper_start)
        helper = APP_SOURCE[helper_start:helper_end]
        script = f"""
global.window = {{Code: {{core: {{}}}}}};
require("./src/core/state.js");
const {{activeRunElapsedMs, persistedRunElapsedMs}} = window.Code.core.state;
const stored = new Map();
global.sessionStorage = {{
  getItem: (key) => stored.has(key) ? stored.get(key) : null,
  setItem: (key, value) => stored.set(key, String(value)),
  removeItem: (key) => stored.delete(key),
}};
const runs = new Map();
function ensureSessionRun(sessionId) {{ return runs.get(sessionId) || null; }}
function hasRecoveredModelResponse(messages, runState) {{
  return messages.some((message) => message?.meta?.agentRunId === runState?.agentRunId);
}}
{helper}
const resumedAt = Date.parse("2026-08-02T16:16:00Z");
sessionStorage.setItem(activeRunTimerStorageKey("session-1"), JSON.stringify({{
  version: 1,
  agentRunId: "agent-1",
  elapsedMs: 17000,
  savedAt: resumedAt - 1000,
}}));
const active = {{isStreaming: false}};
runs.set("session-1", active);
const hydrated = hydratePersistedRunPresentation("session-1", active, {{
  status: "running",
  executionOwner: "server-agent",
  agentRunId: "agent-1",
  agentEventCursor: 7,
  elapsedMs: 15000,
  startedAt: "2026-08-02T16:15:00Z",
  hasFirstModelResponseStarted: true,
  modelRound: 2,
  model: "test-model",
}}, [], resumedAt);
const initialElapsed = activeRunElapsedMs(active, resumedAt);
const continuedElapsed = activeRunElapsedMs(active, resumedAt + 5000);
persistActiveRunTimerCheckpoint("session-1", resumedAt + 5000);
const repeated = {{isStreaming: false}};
runs.set("session-1", repeated);
const repeatedHydrated = hydratePersistedRunPresentation("session-1", repeated, {{
  status: "running",
  executionOwner: "server-agent",
  agentRunId: "agent-1",
  elapsedMs: 15000,
  startedAt: "2026-08-02T16:15:00Z",
}}, [], resumedAt + 6000);
const repeatedElapsed = activeRunElapsedMs(repeated, resumedAt + 6000);

const inferred = {{isStreaming: false}};
runs.set("session-2", inferred);
hydratePersistedRunPresentation("session-2", inferred, {{
  status: "waiting-network",
  executionOwner: "server-agent",
  agentRunId: "agent-2",
  elapsedMs: 4000,
}}, [{{meta: {{agentRunId: "agent-2"}}}}], resumedAt);

sessionStorage.setItem(activeRunTimerStorageKey("session-stale"), JSON.stringify({{
  version: 1,
  agentRunId: "agent-stale",
  elapsedMs: 50000,
  savedAt: resumedAt - 31000,
}}));
const stale = {{isStreaming: false}};
runs.set("session-stale", stale);
hydratePersistedRunPresentation("session-stale", stale, {{
  status: "running",
  executionOwner: "server-agent",
  agentRunId: "agent-stale",
  elapsedMs: 9000,
}}, [], resumedAt);

sessionStorage.setItem(activeRunTimerStorageKey("session-mismatch"), JSON.stringify({{
  version: 1,
  agentRunId: "other-agent",
  elapsedMs: 80000,
  savedAt: resumedAt - 500,
}}));
const mismatch = {{isStreaming: false}};
runs.set("session-mismatch", mismatch);
hydratePersistedRunPresentation("session-mismatch", mismatch, {{
  status: "running",
  executionOwner: "server-agent",
  agentRunId: "expected-agent",
  elapsedMs: 7000,
}}, [], resumedAt);

const completed = {{isStreaming: false}};
runs.set("session-3", completed);
const completedHydrated = hydratePersistedRunPresentation("session-3", completed, {{
  status: "completed",
  executionOwner: "server-agent",
  agentRunId: "agent-3",
  elapsedMs: 9000,
}}, [], resumedAt);
const legacy = {{isStreaming: false}};
runs.set("session-4", legacy);
const legacyHydrated = hydratePersistedRunPresentation("session-4", legacy, {{
  status: "running",
  executionOwner: "browser",
  agentRunId: "agent-4",
}}, [], resumedAt);
clearActiveRunTimerCheckpoint("session-1");
const checkpointCleared = sessionStorage.getItem(activeRunTimerStorageKey("session-1")) === null;
process.stdout.write(JSON.stringify({{
  hydrated,
  active,
  initialElapsed,
  continuedElapsed,
  repeatedHydrated,
  repeatedElapsed,
  inferred,
  staleElapsed: activeRunElapsedMs(stale, resumedAt),
  mismatchElapsed: activeRunElapsedMs(mismatch, resumedAt),
  completedHydrated,
  completed,
  legacyHydrated,
  legacy,
  checkpointCleared,
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["hydrated"])
        self.assertTrue(data["active"]["isStreaming"])
        self.assertEqual(data["active"]["agentRunId"], "agent-1")
        self.assertEqual(data["active"]["agentEventCursor"], 7)
        self.assertEqual(data["active"]["modelRound"], 2)
        self.assertEqual(data["active"]["model"], "test-model")
        self.assertTrue(data["active"]["hasFirstModelResponseStarted"])
        self.assertEqual(data["initialElapsed"], 18000)
        self.assertEqual(data["continuedElapsed"], 23000)
        self.assertTrue(data["repeatedHydrated"])
        self.assertEqual(data["repeatedElapsed"], 24000)
        self.assertTrue(data["inferred"]["isStreaming"])
        self.assertTrue(data["inferred"]["hasFirstModelResponseStarted"])
        self.assertEqual(data["staleElapsed"], 9000)
        self.assertEqual(data["mismatchElapsed"], 7000)
        self.assertFalse(data["completedHydrated"])
        self.assertFalse(data["completed"]["isStreaming"])
        self.assertFalse(data["legacyHydrated"])
        self.assertFalse(data["legacy"]["isStreaming"])
        self.assertTrue(data["checkpointCleared"])

        sync_start = APP_SOURCE.index("function syncActiveStreamingState")
        sync_end = APP_SOURCE.index("let composerResizeObserver", sync_start)
        sync_helper = APP_SOURCE[sync_start:sync_end]
        self.assertIn("hydratePersistedRunPresentation(", sync_helper)
        self.assertLess(
            sync_helper.index("hydratePersistedRunPresentation("),
            sync_helper.index("state.isStreaming = Boolean(run?.isStreaming)"),
        )
        timer_start = APP_SOURCE.index("function startLiveTimer()")
        timer_end = APP_SOURCE.index("function finalizeRunTiming", timer_start)
        self.assertIn(
            "persistActiveRunTimerCheckpoint(state.sessionId)",
            APP_SOURCE[timer_start:timer_end],
        )
        recovery_start = APP_SOURCE.index("async function resumePersistedSessionRun")
        recovery_end = APP_SOURCE.index("function normalizeUserInputRequest", recovery_start)
        recovery = APP_SOURCE[recovery_start:recovery_end]
        self.assertIn("const presentationElapsedMs = activeRunElapsedMs", recovery)
        self.assertIn("ctx.run.taskElapsedBaseMs = Math.max(", recovery)
        self.assertIn("persistActiveRunTimerCheckpoint(sid);", APP_SOURCE)
        self.assertIn("clearActiveRunTimerCheckpoint(sessionId);", APP_SOURCE)

    def test_first_send_projects_user_before_session_creation(self):
        helper_start = APP_SOURCE.index("function projectOptimisticFirstMessage")
        helper_end = APP_SOURCE.index("async function sendMessage", helper_start)
        helper = APP_SOURCE[helper_start:helper_end]
        self.assertIn("state.messages.push(message);", helper)
        self.assertIn("renderMessages();", helper)
        self.assertIn("return message;", helper)

        send_start = APP_SOURCE.index("async function sendMessage")
        send_end = APP_SOURCE.index("function getSelectedModel", send_start)
        send = APP_SOURCE[send_start:send_end]
        projection_index = send.index("projectOptimisticFirstMessage(")
        create_index = send.index("await createSession(")
        self.assertLess(projection_index, create_index)
        self.assertIn("initialMessages: state.messages", send)
        self.assertIn("deferSidebarRefresh: true", send)
        self.assertIn("reconcileOptimisticFirstMessage(", send)
        self.assertIn("if (!existingMessage && !optimisticMessage)", send)
        self.assertLess(
            send.index("setStreaming(true, sessionId);"),
            send.index("scheduleDeferredSessionRefresh(sessionId);"),
        )

    def test_optimistic_first_message_reuses_one_message_object(self):
        helper_start = APP_SOURCE.index("function projectOptimisticFirstMessage")
        helper_end = APP_SOURCE.index("async function sendMessage", helper_start)
        helper = APP_SOURCE[helper_start:helper_end]
        script = f"""
const state = {{ messages: [] }};
let renderCount = 0;
function resetRenderCache() {{}}
function renderMessages() {{ renderCount += 1; }}
{helper}
const message = projectOptimisticFirstMessage(
  "hello",
  "test-model",
  Date.parse("2026-07-31T04:00:00Z"),
  [{{ mime: "image/png", base64: "AAAA" }}],
);
const projectedContentIsMultimodal = Array.isArray(message.content)
  && message.content.length === 2;
const sameObject = state.messages[0] === message;
reconcileOptimisticFirstMessage(
  message,
  "hello",
  ["attachments/image.png"],
  "test-model",
);
process.stdout.write(JSON.stringify({{
  projectedContentIsMultimodal,
  sameObject,
  messageCount: state.messages.length,
  renderCount,
  content: message.content,
  images: message._images,
  pending: Boolean(message.meta?.pendingSessionCreation),
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["projectedContentIsMultimodal"])
        self.assertTrue(data["sameObject"])
        self.assertEqual(data["messageCount"], 1)
        self.assertEqual(data["renderCount"], 1)
        self.assertEqual(data["content"], "hello")
        self.assertEqual(data["images"], ["attachments/image.png"])
        self.assertFalse(data["pending"])

    def test_deferred_first_send_sidebar_refresh_preserves_active_run(self):
        navigation_start = SESSIONS_SOURCE.index("function createSessionNavigation(")
        create_start = SESSIONS_SOURCE.index("async function createSession(", navigation_start)
        create_end = SESSIONS_SOURCE.index("async function loadSession(", create_start)
        create = SESSIONS_SOURCE[create_start:create_end]
        self.assertIn("const initialMessages = Array.isArray(options.initialMessages)", create)
        self.assertIn("state.messages = initialMessages || session.messages || [];", create)
        self.assertIn("if (options.deferSidebarRefresh !== true)", create)
        self.assertIn("state._deferredSessionRefreshId = session.id;", create)
        self.assertLess(
            create.index("view.renderMessages();"),
            create.index("if (session.cwd) await project.saveRoot"),
        )

        refresh_start = APP_SOURCE.index("async function refreshSessions()")
        refresh_end = APP_SOURCE.index("function scheduleDeferredSessionRefresh(", refresh_start)
        refresh = APP_SOURCE[refresh_start:refresh_end]
        self.assertIn("if (!isSessionStreaming(session.id))", refresh)
        self.assertIn("setSessionRunState(session.id, session.runState || {});", refresh)

    def test_active_run_banner_uses_stable_anchor_above_thought_process(self):
        wrapper = """<div id="messages" class="messages">
            <div id="messageList" class="message-list"></div>
            <div id="activeRunBanner" class="active-run-banner hidden"></div>
          </div>"""
        self.assertIn(wrapper, INDEX_SOURCE)
        self.assertLess(INDEX_SOURCE.index('id="activeRunBanner"'), INDEX_SOURCE.index('id="chatForm"'))

        message_list_start = STYLE_SOURCE.index(".message-list {")
        message_list_end = STYLE_SOURCE.index("}", message_list_start)
        message_list_rule = STYLE_SOURCE[message_list_start:message_list_end]
        self.assertIn("display: block", message_list_rule)
        self.assertIn("width: 100%", message_list_rule)
        self.assertNotIn("display: contents", message_list_rule)

        render_start = APP_SOURCE.index("function renderMessages()")
        render_end = APP_SOURCE.index("function isProcessMessage", render_start)
        render = APP_SOURCE[render_start:render_end]
        project_start = MESSAGES_SOURCE.index("function projectMessages(")
        user_start = MESSAGES_SOURCE.index('if (msg.role === "user") {', project_start)
        user_end = MESSAGES_SOURCE.index("continue;", user_start)
        user_projection = MESSAGES_SOURCE[user_start:user_end]
        self.assertLess(
            user_projection.index("rows.push(renderUserProjection(msg, index))"),
            user_projection.index("insertActiveRunAnchor()"),
        )
        self.assertIn('data-active-run-anchor', MESSAGES_SOURCE)
        self.assertIn("const expandedExecutionTraces = new Set(", render)
        self.assertIn('.execution-trace.completed.is-expanded[data-execution-trace]', render)
        self.assertIn("const collapsedExecutionTraces = hasActiveRun", render)
        self.assertIn(
            '.execution-trace.active:not(.is-expanded)[data-execution-trace]',
            render,
        )
        self.assertIn("const expandedToolProcesses = hasActiveRun", render)
        self.assertIn('details.tool-process-stage[open][data-tool-process-id]', render)
        self.assertIn("const expandedToolItems = hasActiveRun", render)
        self.assertIn('details.tool-process-item[open][data-tool-process-item-key]', render)
        self.assertIn("const html = projectMessages(msgs, {", render)
        self.assertIn("expandedExecutionTraces,", render)
        self.assertIn("collapsedExecutionTraces,", render)
        self.assertIn("expandedToolProcesses,", render)
        self.assertIn("reconcileToolProcessNodes(els.messageList, projectedMessageList);", render)
        self.assertIn(
            "els.messageList.replaceChildren(...Array.from(projectedMessageList.childNodes));",
            render,
        )
        self.assertEqual(render.count("messageScrollController?.onContentChanged(state.sessionId);"), 3)
        reconcile_index = render.index("reconcileToolProcessNodes(els.messageList, projectedMessageList);")
        replace_index = render.index("els.messageList.replaceChildren")
        scroll_index = render.index("messageScrollController?.onContentChanged(state.sessionId);", replace_index)
        self.assertLess(reconcile_index, replace_index)
        self.assertLess(replace_index, scroll_index)
        self.assertNotIn(
            "messageScrollController?.onContentChanged(state.sessionId);",
            render[reconcile_index:replace_index],
        )
        self.assertLess(render.index("parkActiveRunBanner();\n  const projectedMessageList"), replace_index)
        mounted_index = render.index("mountActiveRunBanner();", replace_index)
        self.assertLess(mounted_index, render.index("syncActiveRunBanner(state.sessionId);", mounted_index))
        empty_session_guard = "if (isBlankWelcome)"
        self.assertIn(empty_session_guard, render)
        self.assertNotIn(
            "syncActiveRunBanner(state.sessionId);",
            render[:render.index(empty_session_guard)],
        )

        helper_start = APP_SOURCE.index("function parkActiveRunBanner")
        helper_end = APP_SOURCE.index("function syncActiveRunBanner", helper_start)
        helper = APP_SOURCE[helper_start:helper_end]
        self.assertIn("els.messages.appendChild(banner)", helper)
        self.assertIn("anchor.appendChild(banner)", helper)

        timer_start = APP_SOURCE.index("function startLiveTimer()")
        timer_end = APP_SOURCE.index("function finalizeRunTiming", timer_start)
        self.assertNotIn("syncActiveRunBanner", APP_SOURCE[timer_start:timer_end])

        banner_start = STYLE_SOURCE.index(".active-run-banner {")
        banner_end = STYLE_SOURCE.index(".active-run-banner.visible", banner_start)
        banner = STYLE_SOURCE[banner_start:banner_end]
        self.assertIn("position: static", banner)
        self.assertIn("width: 100%", banner)
        self.assertNotIn("bottom:", banner)
        self.assertIn(".messages > .active-run-banner", STYLE_SOURCE)
        self.assertNotIn("transform:", banner)

        line_start = STYLE_SOURCE.index(".active-run-line {")
        line_end = STYLE_SOURCE.index(".active-run-indicator", line_start)
        line = STYLE_SOURCE[line_start:line_end]
        self.assertIn("display: inline-flex", line)
        self.assertNotIn("background:", line)
        self.assertNotIn("border:", line)
        self.assertNotIn("border-radius:", line)

        indicator_start = STYLE_SOURCE.index(".active-run-indicator {")
        indicator_end = STYLE_SOURCE.index(".active-run-label", indicator_start)
        indicator = STYLE_SOURCE[indicator_start:indicator_end]
        self.assertNotIn("animation:", indicator)
        self.assertNotIn("var(--accent)", indicator)

        timer_style_start = STYLE_SOURCE.index(".streaming-timer {")
        timer_style_end = STYLE_SOURCE.index(".network-reconnect-status", timer_style_start)
        timer_style = STYLE_SOURCE[timer_style_start:timer_style_end]
        self.assertIn("color: inherit", timer_style)
        self.assertNotIn("var(--accent)", timer_style)
        self.assertNotIn("font-weight: 700", timer_style)

        timer_start = APP_SOURCE.index("function startLiveTimer()")
        timer_end = APP_SOURCE.index("function finalizeRunTiming", timer_start)
        self.assertIn("}, 1000);", APP_SOURCE[timer_start:timer_end])

        self.assertIn("--composer-safe-bottom", STYLE_SOURCE)
        self.assertIn("function syncComposerSafeArea()", APP_SOURCE)
        self.assertIn("new ResizeObserver(syncComposerSafeArea)", APP_SOURCE)

    def test_error_recovery_rolls_back_to_healthy_snapshot(self):
        """After a model API error, messages are rolled back to pre-run state."""
        self.assertIn("const snapshotIndex = ctx.messages.length", APP_SOURCE)
        self.assertIn("if (!isAbort)", APP_SOURCE)
        self.assertIn("ctx.messages.length = snapshotIndex", APP_SOURCE)
        self.assertIn('delete msg.streaming', APP_SOURCE)
        self.assertIn("delete msg._streamProjection", APP_SOURCE)
        self.assertIn('kind: "error-recovery"', APP_SOURCE)
        self.assertIn("errorRecoveryHint", APP_SOURCE)
        self.assertIn("errorRecoveryHint", I18N_SOURCE)
        self.assertIn("loopError._codeErrorRendered = true", APP_SOURCE)
        self.assertIn(
            'if (!err?._codeErrorRendered) appendSystemError(errMsg)',
            APP_SOURCE,
        )

    def test_error_recovery_preserves_user_message_on_rollback(self):
        """Rollback restores user message content and keeps it at snapshot-1."""
        self.assertIn("userMsg.content = originalUserContent", APP_SOURCE)
        self.assertIn("const originalUserContent = messageContent", APP_SOURCE)
        self.assertIn('userMsg.role === "user"', APP_SOURCE)

    # ── error_code frontend display ──

    def test_error_code_meta_has_all_codes(self):
        """All runtime error codes have entries in _errorCodeMeta."""
        codes = ["upstream_error", "model_response_timeout", "config_error",
                 "model_access_denied", "permission_denied",
                 "tool_error", "user_cancelled", "empty_response",
                 "content_filtered", "internal_error"]
        for code in codes:
            self.assertIn(code + ":", APP_SOURCE.replace(" ", ""),
                         f"Missing error code meta entry: {code}")

    def test_error_code_info_function_exists(self):
        self.assertIn("function _errorCodeInfo(code)", APP_SOURCE)

    def test_format_agent_error_function_exists(self):
        self.assertIn("function _formatAgentError(err)", APP_SOURCE)
        self.assertIn("err.errorCode", APP_SOURCE)
        self.assertIn("_errorCodeInfo", APP_SOURCE)

    def test_format_agent_error_uses_i18n(self):
        """_formatAgentError uses t() for label and suggestion keys."""
        self.assertIn("t(\"errLabel\"", APP_SOURCE.replace(" ", ""))
        self.assertIn("t(\"errSug\"", APP_SOURCE.replace(" ", ""))
        self.assertIn("t(\"errAgentFailed\")", APP_SOURCE.replace(" ", ""))
        self.assertIn("\\u{1f4a1}", APP_SOURCE)

    def test_agent_snapshot_includes_error_code_propagation(self):
        """Agent failure throws error with errorCode attached."""
        self.assertIn("err.errorCode = snapshot.errorCode", APP_SOURCE)
        self.assertIn('err.status = snapshot.status', APP_SOURCE)

    def test_agent_catch_block_uses_format_agent_error(self):
        """The catch block uses _formatAgentError instead of hardcoded text."""
        self.assertIn("_formatAgentError(err)", APP_SOURCE)

    def test_retry_distinction(self):
        """Transient errors suggest retry; permanent errors don't."""
        self.assertIn("retry: true", APP_SOURCE)
        self.assertIn("retry: false", APP_SOURCE)

    def test_i18n_keys_for_all_error_codes(self):
        """Every error code has both label and suggestion i18n keys."""
        self.assertIn("errLabelUpstreamError", I18N_SOURCE)
        self.assertIn("errSugUpstreamError", I18N_SOURCE)
        self.assertIn("errLabelModelResponseTimeout", I18N_SOURCE)
        self.assertIn("errSugModelResponseTimeout", I18N_SOURCE)
        self.assertIn("errLabelEmptyResponse", I18N_SOURCE)
        self.assertIn("errSugEmptyResponse", I18N_SOURCE)
        self.assertIn("errLabelContentFiltered", I18N_SOURCE)
        self.assertIn("errSugContentFiltered", I18N_SOURCE)
        self.assertIn("errAgentFailed", I18N_SOURCE)

    def test_i18n_keys_have_both_languages(self):
        """Error i18n keys exist in both Chinese and English."""
        self.assertIn("上游异常", I18N_SOURCE)
        self.assertIn("Upstream error", I18N_SOURCE)
        self.assertIn("模型未产出回复", I18N_SOURCE)
        self.assertIn("No response generated", I18N_SOURCE)
        self.assertIn("响应被内容策略拦截", I18N_SOURCE)
        self.assertIn("Response blocked by content policy", I18N_SOURCE)

    # ── Session import UI ──

    def test_import_button_in_html(self):
        """Import button exists in the toolbar and modal."""
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="importSessions"', html)

    def test_import_modal_in_html(self):
        """Import modal with source tabs and list exists."""
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="importModal"', html)
        self.assertIn('id="importList"', html)
        self.assertIn('id="importStatus"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('id="importDoBtn"', html)
        self.assertIn('id="importProgress"', html)
        self.assertIn('id="importProgressTrack"', html)
        self.assertIn('role="progressbar"', html)
        self.assertIn('id="importCancelBtn"', html)
        self.assertIn('id="importRetryBtn"', html)
        self.assertIn('id="importFailures"', html)
        self.assertIn('import-source-tab', html)
        self.assertIn('class="modal-panel import-dialog"', html)
        self.assertIn('role="dialog"', html)
        self.assertIn('aria-modal="true"', html)
        self.assertIn('id="importRefreshBtn"', html)
        self.assertIn('data-import-filter="importable"', html)
        self.assertIn('data-import-filter="all"', html)
        self.assertIn('id="importSelectionSummary"', html)
        self.assertIn('id="importDismissBtn"', html)
        self.assertIn(
            "从本机 Claude Code 或 Codex 导入历史会话",
            html,
        )
        self.assertIn(
            'importDialogSubtitle: "从本机 Claude Code 或 Codex 导入历史会话"',
            I18N_SOURCE,
        )
        self.assertIn(
            'importDialogSubtitle: "Import local Claude Code or Codex session history"',
            I18N_SOURCE,
        )

    def test_import_functions_in_app_js(self):
        """Import functions are defined in app.js."""
        self.assertIn("function openImportModal", APP_SOURCE)
        self.assertIn("function loadImportSessions", APP_SOURCE)
        self.assertIn("function renderImportList", APP_SOURCE)
        self.assertIn("function renderImportBatchState", APP_SOURCE)
        self.assertIn("function cancelImportBatch", APP_SOURCE)
        self.assertIn("function retryFailedImports", APP_SOURCE)
        self.assertIn("function doImport", APP_SOURCE)

    def test_import_els_references(self):
        """Import DOM element references exist."""
        self.assertIn("importSessions:", APP_SOURCE)
        self.assertIn("importModal:", APP_SOURCE)
        self.assertIn("importList:", APP_SOURCE)
        self.assertIn("importDoBtn:", APP_SOURCE)
        self.assertIn("importProgress:", APP_SOURCE)
        self.assertIn("importCancelBtn:", APP_SOURCE)
        self.assertIn("importRetryBtn:", APP_SOURCE)
        self.assertIn("importFailures:", APP_SOURCE)

    def test_import_source_switching(self):
        """Source tab switching updates _importSource."""
        self.assertIn("_importSource", APP_SOURCE)
        self.assertIn('dataset.source', APP_SOURCE)

    def test_import_i18n_keys(self):
        """Import i18n keys exist in both languages."""
        for key in (
            "importSessions",
            "sessionTransferActions",
            "importSessionsTip",
            "exportBtnTip",
            "importDialogSubtitle",
            "closeImport",
            "importSourceTabsLabel",
            "importSourceCount",
            "importRefresh",
            "importRefreshTip",
            "importRefreshing",
            "importSearchLabel",
            "importSearchPlaceholder",
            "importSelectAll",
            "importSelectVisible",
            "importFilterLabel",
            "importFilterImportable",
            "importFilterAll",
            "importVisibleSummary",
            "importSelectedCount",
            "importToCode",
            "importLoading",
            "importLoadFailed",
            "importNoMatching",
            "importStatusImported",
            "importStatusContinued",
            "importStatusUpdateAvailable",
            "importStatusUpdateConflict",
            "importStatusUpdateConflictHint",
            "importResultSnapshot",
            "importResultFailed",
            "importCancel",
            "importStopping",
            "importProgress",
            "importRetryProgress",
            "importFinalizing",
            "importResultCancelled",
            "importBadgeLifecycleHint",
            "importBadgeHiddenToast",
            "sourceBadgeCodexTitle",
            "sourceBadgeClaudeTitle",
            "importRetryResultPrefix",
            "importRetryFailed",
            "importFailureDetails",
            "importFailureRetryable",
            "importFailureNeedsFix",
            "importErrorSourceChanged",
            "importErrorSourceIncomplete",
            "importErrorSourceMissing",
            "importErrorPermissionDenied",
            "importErrorInvalidJsonl",
            "importErrorNetwork",
        ):
            self.assertEqual(I18N_SOURCE.count(f"{key}:"), 2, key)

    def test_import_modal_css_exists(self):
        """Import modal styles are defined."""
        self.assertIn("import-source-tab", STYLE_SOURCE)
        self.assertIn(".import-session-row", STYLE_SOURCE)
        self.assertIn(".import-session-state", STYLE_SOURCE)
        self.assertIn(".import-result", STYLE_SOURCE)
        self.assertIn(".import-progress", STYLE_SOURCE)
        self.assertIn(".import-progress-bar", STYLE_SOURCE)
        self.assertIn(".import-result-actions", STYLE_SOURCE)
        self.assertIn(".import-badge-hint", STYLE_SOURCE)
        self.assertIn(".import-failure-item", STYLE_SOURCE)
        self.assertIn(".import-search-field", STYLE_SOURCE)
        self.assertIn(".import-filter-tabs", STYLE_SOURCE)
        self.assertIn(".import-dialog-footer", STYLE_SOURCE)
        self.assertIn(".modal-panel.import-dialog", STYLE_SOURCE)
        self.assertIn("@media (max-width: 640px)", STYLE_SOURCE)
        self.assertIn('id="importBadgeHint"', INDEX_SOURCE)
        refresh_css = re.search(
            r"\.import-refresh-btn\s*\{(?P<body>.*?)\}",
            STYLE_SOURCE,
            re.S,
        )
        self.assertIsNotNone(refresh_css)
        self.assertIn("display: inline-flex", refresh_css.group("body"))
        self.assertIn("align-items: center", refresh_css.group("body"))
        self.assertIn("justify-content: center", refresh_css.group("body"))
        search_input_css = re.search(
            r"\.import-search-field input\s*\{(?P<body>.*?)\}",
            STYLE_SOURCE,
            re.S,
        )
        self.assertIsNotNone(search_input_css)
        self.assertIn("box-shadow: none", search_input_css.group("body"))
        primary_css_blocks = re.findall(
            r"\.import-dialog-actions \.primary-btn\s*\{(?P<body>.*?)\}",
            STYLE_SOURCE,
            re.S,
        )
        self.assertTrue(primary_css_blocks)
        primary_css = "\n".join(primary_css_blocks)
        self.assertIn("background: var(--accent)", primary_css)
        self.assertIn("color: var(--bg)", primary_css)
        feedback_css = re.search(
            r"\.import-feedback\s*\{(?P<body>.*?)\}",
            STYLE_SOURCE,
            re.S,
        )
        self.assertIsNotNone(feedback_css)
        self.assertIn("flex: 0 0 auto", feedback_css.group("body"))
        self.assertIn("max-height: 170px", feedback_css.group("body"))
        self.assertIn("overflow-y: auto", feedback_css.group("body"))
        result_css = re.search(
            r"\.import-result\s*\{(?P<body>.*?)\}",
            STYLE_SOURCE,
            re.S,
        )
        self.assertIsNotNone(result_css)
        for expected in (
            "min-height: 0",
            "padding: 8px 10px",
            "border: 1px solid var(--line)",
            "background: var(--panel)",
            "line-height: 1.45",
        ):
            self.assertIn(expected, result_css.group("body"))
        self.assertIn(".import-result:empty", STYLE_SOURCE)
        self.assertIn(".import-failures:empty", STYLE_SOURCE)
        footer_css = re.search(
            r"\.import-dialog-footer\s*\{(?P<body>.*?)\}",
            STYLE_SOURCE,
            re.S,
        )
        self.assertIsNotNone(footer_css)
        self.assertIn("flex: 0 0 auto", footer_css.group("body"))

    def test_session_transfer_toolbar_uses_distinct_accessible_icons(self):
        toolbar_start = INDEX_SOURCE.index('class="session-transfer-actions"')
        toolbar_end = INDEX_SOURCE.index('id="usageStrip"', toolbar_start)
        toolbar_source = INDEX_SOURCE[toolbar_start:toolbar_end]
        self.assertIn('id="importSessions"', toolbar_source)
        self.assertIn('class="tool-btn transfer-icon-btn import-entry-btn"', toolbar_source)
        self.assertIn('id="exportChat"', toolbar_source)
        self.assertIn('class="tool-btn transfer-icon-btn export-entry-btn"', toolbar_source)
        self.assertIn('data-i18n-aria-label="importSessionsTip"', toolbar_source)
        self.assertIn('data-i18n-aria-label="exportBtnTip"', toolbar_source)
        self.assertIn(
            'title="从本机 Claude Code 或 Codex 导入历史会话"',
            toolbar_source,
        )
        self.assertIn(
            'importSessionsTip: "从本机 Claude Code 或 Codex 导入历史会话"',
            I18N_SOURCE,
        )
        self.assertIn(
            'importSessionsTip: "Import local Claude Code or Codex session history"',
            I18N_SOURCE,
        )
        self.assertEqual(toolbar_source.count('width="18" height="18"'), 2)
        self.assertNotIn("export-icon-btn", toolbar_source)
        transfer_actions_css = re.search(
            r"\.session-transfer-actions\s*\{(?P<body>.*?)\}",
            STYLE_SOURCE,
            re.S,
        )
        self.assertIsNotNone(transfer_actions_css)
        self.assertNotIn("border-right", transfer_actions_css.group("body"))
        self.assertNotRegex(
            STYLE_SOURCE,
            r"\.usage-strip\s*\{[^}]*border-left",
        )

    def test_import_source_badge_explains_and_follows_snapshot_lifecycle(self):
        badge_start = APP_SOURCE.index("function renderSessionSourceBadge(")
        badge_end = APP_SOURCE.index("function renderPinIcon(", badge_start)
        badge_source = APP_SOURCE[badge_start:badge_end]
        sync_start = APP_SOURCE.index("function syncSessionSourceBadgeState(")
        sync_end = APP_SOURCE.index("async function saveSessionState(", sync_start)
        sync_source = APP_SOURCE[sync_start:sync_end]
        render_start = APP_SOURCE.index("function renderImportBatchState(")
        render_end = APP_SOURCE.index("function cancelImportBatch(", render_start)
        render_source = APP_SOURCE[render_start:render_end]

        self.assertIn("session?.sourceBadgeVisible !== true", badge_source)
        self.assertIn('t("sourceBadgeCodexTitle")', badge_source)
        self.assertIn('t("sourceBadgeClaudeTitle")', badge_source)
        self.assertIn("SOURCE_BADGE_NOTICE_KEY", sync_source)
        self.assertIn(
            'showToast(t("importBadgeHiddenToast"), "info", { duration: 7000 })',
            sync_source,
        )
        self.assertIn("renderSessions();", sync_source)
        self.assertIn('t("importBadgeLifecycleHint")', render_source)
        self.assertIn("counts.snapshot", render_source)

    def test_source_badge_transition_hides_once_and_notifies_once(self):
        sync_start = APP_SOURCE.index("const SOURCE_BADGE_NOTICE_KEY")
        sync_end = APP_SOURCE.index("async function saveSessionState(", sync_start)
        sync_source = APP_SOURCE[sync_start:sync_end]
        script = f"""
const vm = require("vm");
const stored = new Map();
const renders = [];
const toasts = [];
const context = {{
  state: {{
    sessionId: "session-1",
    sessions: [
      {{id: "session-1", source: "codex", sourceBadgeVisible: true}},
      {{id: "session-2", source: "claude-code", sourceBadgeVisible: true}},
    ],
  }},
  localStorage: {{
    getItem: (key) => stored.get(key) || null,
    setItem: (key, value) => stored.set(key, String(value)),
  }},
  renderSessions: () => renders.push("render"),
  showToast: (...args) => toasts.push(args),
  t: (key) => key,
}};
vm.runInNewContext({json.dumps(sync_source)}, context);
context.syncSessionSourceBadgeState(
  "session-1",
  {{source: "codex", sourceBadgeVisible: false}},
  {{notify: true}},
);
context.state.sessionId = "session-2";
context.syncSessionSourceBadgeState(
  "session-2",
  {{source: "claude-code", sourceBadgeVisible: false}},
  {{notify: true}},
);
context.syncSessionSourceBadgeState(
  "session-2",
  {{source: "claude-code", sourceBadgeVisible: false}},
  {{notify: true}},
);
process.stdout.write(JSON.stringify({{
  sessions: context.state.sessions,
  renders,
  toasts,
  stored: Array.from(stored.entries()),
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertFalse(data["sessions"][0]["sourceBadgeVisible"])
        self.assertFalse(data["sessions"][1]["sourceBadgeVisible"])
        self.assertEqual(data["renders"], ["render", "render"])
        self.assertEqual(
            data["toasts"],
            [["importBadgeHiddenToast", "info", {"duration": 7000}]],
        )
        self.assertEqual(
            data["stored"],
            [["code-source-badge-lifecycle-notice-v1", "1"]],
        )

    def test_import_picker_disables_already_imported_sessions(self):
        """Only safe, actionable rows can be selected for import."""
        render_start = APP_SOURCE.index("function renderImportList()")
        render_end = APP_SOURCE.index("function importResultText", render_start)
        render_source = APP_SOURCE[render_start:render_end]
        self.assertIn("var canImport = importSessionCanImport(s);", render_source)
        self.assertIn("var sessionKey = importSessionKey(s);", render_source)
        self.assertIn('cb.dataset.importable = canImport ? "true" : "false";', render_source)
        self.assertIn("cb.dataset.sessionKey = sessionKey;", render_source)
        self.assertIn("cb.disabled = !canImport || _importBusy;", render_source)
        self.assertIn('"update-conflict": "importStatusUpdateConflict"', render_source)
        self.assertIn('className = "import-session-state"', render_source)
        self.assertIn("_importSelectedKeys.add(c.dataset.sessionKey)", APP_SOURCE)
        self.assertIn("_importSelectedKeys.delete(c.dataset.sessionKey)", APP_SOURCE)

    def test_import_search_and_filters_use_cached_sessions_locally(self):
        helper_start = APP_SOURCE.index("function importSessionKey(")
        helper_end = APP_SOURCE.index("function _bindImportEvents(", helper_start)
        helper_source = APP_SOURCE[helper_start:helper_end]
        script = f"""
const vm = require("vm");
const search = {{value: "alpha"}};
const context = {{
  _importSource: "codex",
  _importFilter: "importable",
  _importSessions: [
    {{id: "one", sourceId: "alpha-1", title: "Alpha task", canImport: true}},
    {{id: "two", sourceId: "beta-2", title: "Beta task", canImport: false}},
    {{id: "three", sourceId: "gamma-3", title: "Gamma alpha", canImport: false}},
    {{id: "four", sourceId: "delta-4", title: "Delta task", canImport: true}},
  ],
  document: {{
    getElementById: (id) => id === "importSearch" ? search : null,
    querySelectorAll: () => [],
  }},
  t: (key, params) => `${{key}}:${{params?.count ?? ""}}`,
}};
vm.runInNewContext({json.dumps(helper_source)}, context);
const searched = context.filteredImportSessions().map((item) => item.id);
search.value = "";
const importable = context.filteredImportSessions().map((item) => item.id);
context._importFilter = "all";
const all = context.filteredImportSessions().map((item) => item.id);
process.stdout.write(JSON.stringify({{
  searched,
  importable,
  all,
  key: context.importSessionKey(context._importSessions[0]),
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "searched": ["one"],
                "importable": ["one", "four"],
                "all": ["one", "two", "three", "four"],
                "key": "codex:alpha-1",
            },
        )
        self.assertIn("if (!force && Array.isArray(cached))", APP_SOURCE)
        search_handler_start = APP_SOURCE.index(
            'if (search) search.addEventListener("input"',
        )
        search_handler_end = APP_SOURCE.index(
            'modal.addEventListener("click", function (event)',
            search_handler_start,
        )
        search_handler = APP_SOURCE[search_handler_start:search_handler_end]
        self.assertIn("renderImportList();", search_handler)
        self.assertNotIn("loadImportSessions", search_handler)

    def test_import_completion_refreshes_without_reloading_page(self):
        """Import actions stay visible and refresh the sidebar and picker in place."""
        import_start = APP_SOURCE.index("async function runImportBatch(")
        import_end = APP_SOURCE.index(
            "if (els.importSessions)",
            import_start,
        )
        import_source = APP_SOURCE[import_start:import_end]
        self.assertIn("_importBatchRunner.run", import_source)
        self.assertIn("source: importSource", import_source)
        self.assertIn("items: selectedSessions", import_source)
        self.assertIn("setImportBusy(true);", import_source)
        self.assertIn("setImportBusy(false);", import_source)
        self.assertIn("delete _importCache[importSource];", import_source)
        self.assertIn("await refreshSessions();", import_source)
        self.assertIn("await loadImportSessions(true);", import_source)
        self.assertIn("renderImportBatchState();", import_source)
        self.assertNotIn("location.reload()", import_source)
        self.assertNotIn("closeImportModal()", import_source)

    def test_import_batch_cancel_retry_and_error_details_are_wired(self):
        import_start = APP_SOURCE.index("function importFailureMessage(")
        import_end = APP_SOURCE.index("if (els.importSessions)", import_start)
        import_source = APP_SOURCE[import_start:import_end]
        self.assertIn("_importBatchRunner.cancel()", import_source)
        self.assertIn(".filter(function (failure) { return failure.retryable; })", import_source)
        self.assertIn('mode: mode || "import"', import_source)
        self.assertIn("importFailureMessage(failure)", import_source)
        self.assertIn("failure.errorCode", import_source)
        self.assertIn("failure.retryable", import_source)
        self.assertIn("_importFinalizing = true;", import_source)
        self.assertIn("_importFinalizing = false;", import_source)

    def test_import_batch_runner_stops_after_current_item_and_classifies_failures(self):
        script = r"""
global.window = {setTimeout};
require("./src/core/namespace.js");
require("./src/features/session-import.js");
const {createImportBatchRunner} = window.Code.features.sessionImport;

(async () => {
  const calls = [];
  const resolvers = [];
  const progress = [];
  const cancelRunner = createImportBatchRunner({
    importOne: (source, item) => {
      calls.push({source, id: item.id});
      return new Promise((resolve) => resolvers.push(resolve));
    },
    onProgress: (snapshot) => progress.push({
      phase: snapshot.phase,
      processed: snapshot.processed,
      cancelRequested: snapshot.cancelRequested,
    }),
    yieldControl: async () => {},
  });
  const pending = cancelRunner.run({
    source: "codex",
    items: [{id: "one"}, {id: "two"}, {id: "three"}],
  });
  const cancelAccepted = cancelRunner.cancel();
  resolvers[0]({action: "created"});
  const cancelled = await pending;

  const failureRunner = createImportBatchRunner({
    importOne: async (source, item) => {
      if (item.id === "retry") {
        const error = new Error("changed");
        error.errorCode = "import_source_changed";
        error.retryable = true;
        throw error;
      }
      if (item.id === "broken") {
        const error = new Error("invalid");
        error.errorCode = "import_source_invalid_jsonl";
        error.retryable = false;
        throw error;
      }
      return {action: "updated"};
    },
    yieldControl: async () => {},
  });
  const classified = await failureRunner.run({
    source: "claude-code",
    mode: "retry",
    items: [{id: "ok"}, {id: "retry"}, {id: "broken"}],
  });
  process.stdout.write(JSON.stringify({
    calls,
    cancelAccepted,
    cancelled,
    progress,
    classified,
  }));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["cancelAccepted"])
        self.assertEqual(data["calls"], [{"source": "codex", "id": "one"}])
        self.assertEqual(data["cancelled"]["processed"], 1)
        self.assertEqual(data["cancelled"]["cancelled"], 2)
        self.assertEqual(data["cancelled"]["counts"]["created"], 1)
        self.assertTrue(data["cancelled"]["cancelRequested"])
        self.assertEqual(data["progress"][-1]["phase"], "cancelled")
        self.assertEqual(data["classified"]["mode"], "retry")
        self.assertEqual(data["classified"]["counts"]["updated"], 1)
        self.assertEqual(data["classified"]["counts"]["failed"], 2)
        self.assertEqual(
            [failure["errorCode"] for failure in data["classified"]["failures"]],
            ["import_source_changed", "import_source_invalid_jsonl"],
        )
        self.assertEqual(
            [failure["retryable"] for failure in data["classified"]["failures"]],
            [True, False],
        )

    def test_import_picker_revalidates_preloaded_source_state(self):
        """Opening or switching sources never trusts stale preload metadata."""
        open_start = APP_SOURCE.index("async function openImportModal()")
        open_end = APP_SOURCE.index("function updateGroupBadge", open_start)
        open_source = APP_SOURCE[open_start:open_end]
        bind_start = APP_SOURCE.index("function _bindImportEvents()")
        bind_end = APP_SOURCE.index("async function openImportModal()", bind_start)
        bind_source = APP_SOURCE[bind_start:bind_end]
        self.assertIn("_importSessions = _importCache[_importSource] || [];", open_source)
        self.assertIn("await loadImportSessions(true);", open_source)
        self.assertIn("_importSessions = _importCache[_importSource] || [];", bind_source)
        self.assertIn("loadImportSessions(true);", bind_source)


class TestSessionStatusSlot(unittest.TestCase):
    def test_background_streaming_messages_refresh_only_the_existing_status_slot(self):
        projection_start = APP_SOURCE.index("function markSessionUnread(")
        projection_end = APP_SOURCE.index("const PERSISTED_ACTIVE_RUN_STATUSES", projection_start)
        projection_source = APP_SOURCE[projection_start:projection_end]
        script = r"""
const background = {id: "background", _unread: false, _seenCount: 0};
const active = {id: "active", _unread: false, _seenCount: 0};
const state = {
  sessionId: "active",
  sessions: [active, background],
  branchPanelOpen: false,
};
let backgroundStreaming = true;
const counts = {statusRefresh: 0, fullSessions: 0, activeMessages: 0, branches: 0};
const getSessionMessages = (sessionId) => (
  sessionId === "background" ? [{}, {}] : [{}, {}, {}]
);
const isSessionStreaming = (sessionId) => sessionId === "background" && backgroundStreaming;
const refreshSessionStatusSlot = (sessionId) => {
  if (sessionId === "background") counts.statusRefresh += 1;
};
const renderSessions = () => { counts.fullSessions += 1; };
const renderMessages = () => { counts.activeMessages += 1; };
const renderBranchTree = () => { counts.branches += 1; };
eval(__PROJECTION_SOURCE__);

renderSessionMessages("background");
const streaming = {
  unread: background._unread,
  seenCount: background._seenCount,
  ...counts,
};

backgroundStreaming = false;
renderSessionMessages("background");
const terminal = {
  unread: background._unread,
  seenCount: background._seenCount,
  ...counts,
};

renderSessionMessages("active");
const foreground = {
  activeSeenCount: active._seenCount,
  ...counts,
};
process.stdout.write(JSON.stringify({streaming, terminal, foreground}));
""".replace("__PROJECTION_SOURCE__", json.dumps(projection_source))
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(
            data["streaming"],
            {
                "unread": True,
                "seenCount": 2,
                "statusRefresh": 1,
                "fullSessions": 0,
                "activeMessages": 0,
                "branches": 0,
            },
        )
        self.assertEqual(
            data["terminal"],
            {
                "unread": True,
                "seenCount": 2,
                "statusRefresh": 1,
                "fullSessions": 1,
                "activeMessages": 0,
                "branches": 0,
            },
        )
        self.assertEqual(
            data["foreground"],
            {
                "activeSeenCount": 3,
                "statusRefresh": 1,
                "fullSessions": 1,
                "activeMessages": 1,
                "branches": 0,
            },
        )

    def test_same_status_kind_patches_slot_and_indicator_in_place(self):
        status_start = APP_SOURCE.index("function resolveSessionStatusSlot(")
        status_end = APP_SOURCE.index("const sessionStatusTicker", status_start)
        status_source = APP_SOURCE[status_start:status_end]
        script = f"""
const state = {{sessionId: "session-1", sessions: [{{id: "session-1"}}]}};
let nextStatus = {{kind: "running", text: "", label: "running-one"}};
let slots = [];
const els = {{sessionList: {{querySelectorAll() {{ return slots; }}}}}};
const getSessionRunState = () => ({{}});
const getUserInputRequest = () => null;
const pendingAuthorizations = () => [];
const isSessionStreaming = () => nextStatus.kind === "running";
const t = (key) => key;
const resolveSessionStatus = () => ({{...nextStatus}});
const escapeHtml = (value) => String(value);
function makeIndicator() {{
  return {{attrs: {{}}, setAttribute(name, value) {{ this.attrs[name] = value; }}}};
}}
function makeSlot(kind, indicator = null) {{
  return {{
    dataset: {{sessionId: "session-1", sessionStatus: kind}},
    attrs: {{}},
    indicator,
    replacementCount: 0,
    replacementHtml: "",
    _text: kind === "idle" ? "old" : "",
    querySelector(selector) {{
      return selector === ":scope > .session-status-indicator" ? this.indicator : null;
    }},
    setAttribute(name, value) {{ this.attrs[name] = String(value); }},
    removeAttribute(name) {{ delete this.attrs[name]; }},
    get textContent() {{ return this._text; }},
    set textContent(value) {{ this._text = String(value); }},
    set outerHTML(value) {{ this.replacementCount += 1; this.replacementHtml = String(value); }},
  }};
}}
eval({json.dumps(status_source)});

const runningIndicator = makeIndicator();
const runningSlot = makeSlot("running", runningIndicator);
slots = [runningSlot];
const firstRunningRefresh = refreshSessionStatusSlot("session-1");
nextStatus = {{kind: "running", text: "", label: "running-two"}};
const secondRunningRefresh = refreshSessionStatusSlot("session-1");
const runningProjection = {{
  firstRunningRefresh,
  secondRunningRefresh,
  sameSlot: slots[0] === runningSlot,
  sameIndicator: runningSlot.indicator === runningIndicator,
  replacements: runningSlot.replacementCount,
  role: runningSlot.attrs.role,
  title: runningSlot.attrs.title,
  ariaLabel: runningSlot.attrs["aria-label"],
  indicatorAriaHidden: runningIndicator.attrs["aria-hidden"],
}};

nextStatus = {{kind: "unread", text: "", label: "new-message"}};
const transitioned = refreshSessionStatusSlot("session-1");
const transitionProjection = {{
  transitioned,
  replacements: runningSlot.replacementCount,
  unreadMarkup: runningSlot.replacementHtml.includes('data-session-status="unread"'),
  indicatorMarkup: runningSlot.replacementHtml.includes('class="session-status-indicator"'),
}};

const idleSlot = makeSlot("idle");
slots = [idleSlot];
nextStatus = {{kind: "idle", text: "1m", label: "1m"}};
const firstIdleRefresh = refreshSessionStatusSlot("session-1");
nextStatus = {{kind: "idle", text: "2m", label: "2m"}};
const secondIdleRefresh = refreshSessionStatusSlot("session-1");
const idleProjection = {{
  firstIdleRefresh,
  secondIdleRefresh,
  sameSlot: slots[0] === idleSlot,
  replacements: idleSlot.replacementCount,
  text: idleSlot.textContent,
  ariaLabel: idleSlot.attrs["aria-label"],
  rolePresent: Object.hasOwn(idleSlot.attrs, "role"),
  titlePresent: Object.hasOwn(idleSlot.attrs, "title"),
}};
process.stdout.write(JSON.stringify({{runningProjection, transitionProjection, idleProjection}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(
            data["runningProjection"],
            {
                "firstRunningRefresh": True,
                "secondRunningRefresh": True,
                "sameSlot": True,
                "sameIndicator": True,
                "replacements": 0,
                "role": "img",
                "title": "running-two",
                "ariaLabel": "running-two",
                "indicatorAriaHidden": "true",
            },
        )
        self.assertEqual(
            data["transitionProjection"],
            {
                "transitioned": True,
                "replacements": 1,
                "unreadMarkup": True,
                "indicatorMarkup": True,
            },
        )
        self.assertEqual(
            data["idleProjection"],
            {
                "firstIdleRefresh": True,
                "secondIdleRefresh": True,
                "sameSlot": True,
                "replacements": 0,
                "text": "2m",
                "ariaLabel": "2m",
                "rolePresent": False,
                "titlePresent": False,
            },
        )

    def test_relative_time_boundaries_fallbacks_and_status_priority(self):
        script = f"""
const window = {{Code: {{features: {{}}}}}};
global.window = window;
eval({json.dumps(SESSIONS_SOURCE)});
const sessions = window.Code.features.sessions;
const now = Date.parse("2026-08-24T12:00:00Z");
const translate = (language) => (key, params = {{}}) => {{
  if (key === "sessionRelativeNow") return language === "zh" ? "刚刚" : "now";
  const unit = {{
    sessionRelativeMinutes: language === "zh" ? "分钟" : "m",
    sessionRelativeHours: language === "zh" ? "小时" : "h",
    sessionRelativeDays: language === "zh" ? "天" : "d",
  }}[key];
  return `${{params.count}}${{unit}}`;
}};
const zh = translate("zh");
const en = translate("en");
const sample = (value, formatter = zh) => sessions.formatSessionRelativeTime(
  value,
  formatter,
  now,
);
process.stdout.write(JSON.stringify({{
  zh: [
    sample({{lastMessageTime: "2026-08-24T12:00:00Z"}}),
    sample({{lastMessageTime: "2026-08-24T12:05:00Z"}}),
    sample({{lastMessageTime: "2026-08-24T11:59:01Z"}}),
    sample({{lastMessageTime: "2026-08-24T11:59:00Z"}}),
    sample({{lastMessageTime: "2026-08-24T11:00:01Z"}}),
    sample({{lastMessageTime: "2026-08-24T11:00:00Z"}}),
    sample({{lastMessageTime: "2026-08-23T13:00:00Z"}}),
    sample({{lastMessageTime: "2026-08-23T12:00:00Z"}}),
  ],
  en: sample({{lastMessageTime: "2026-08-24T10:00:00Z"}}, en),
  fallback: sample({{
    lastMessageTime: "invalid",
    updatedAt: "2026-08-24T11:58:00Z",
    createdAt: "2026-08-20T00:00:00Z",
  }}),
  awareFallback: sample({{
    lastMessageTime: "2026-08-24T11:00:00",
    updatedAt: "invalid",
    createdAt: "2026-08-24T11:57:00+00:00",
  }}),
  missing: sample({{}}),
  running: sessions.resolveSessionStatus(
    {{_unread: true}},
    {{streaming: true, runningLabel: "running", unreadLabel: "unread", translate: zh, now}},
  ),
  unread: sessions.resolveSessionStatus(
    {{_unread: true, lastMessageTime: "2026-08-24T11:00:00Z"}},
    {{streaming: false, runningLabel: "running", unreadLabel: "unread", translate: zh, now}},
  ),
  idle: sessions.resolveSessionStatus(
    {{lastMessageTime: "2026-08-24T11:00:00Z"}},
    {{streaming: false, runningLabel: "running", unreadLabel: "unread", translate: zh, now}},
  ),
  inactiveQuestion: sessions.resolveSessionStatus(
    {{_unread: true}},
    {{active: false, waitingUserInput: true, waitingAuthorization: true, streaming: true,
      waitingUserInputLabel: "answer", waitingAuthorizationLabel: "confirm",
      runningLabel: "running", unreadLabel: "unread", translate: zh, now}},
  ),
  inactiveAuthorization: sessions.resolveSessionStatus(
    {{_unread: true}},
    {{active: false, waitingAuthorization: true, streaming: true,
      waitingAuthorizationLabel: "confirm", runningLabel: "running",
      unreadLabel: "unread", translate: zh, now}},
  ),
  activeWaitingRunning: sessions.resolveSessionStatus(
    {{_unread: true}},
    {{active: true, waitingUserInput: true, waitingAuthorization: true, streaming: true,
      waitingUserInputLabel: "answer", waitingAuthorizationLabel: "confirm",
      runningLabel: "running", unreadLabel: "unread", translate: zh, now}},
  ),
  activeWaitingUnread: sessions.resolveSessionStatus(
    {{_unread: true}},
    {{active: true, waitingUserInput: true, waitingAuthorization: true, streaming: false,
      waitingUserInputLabel: "answer", waitingAuthorizationLabel: "confirm",
      runningLabel: "running", unreadLabel: "unread", translate: zh, now}},
  ),
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(
            data["zh"],
            ["刚刚", "刚刚", "刚刚", "1分钟", "59分钟", "1小时", "23小时", "1天"],
        )
        self.assertEqual(data["en"], "2h")
        self.assertEqual(data["fallback"], "2分钟")
        self.assertEqual(data["awareFallback"], "3分钟")
        self.assertEqual(data["missing"], "")
        self.assertEqual(data["running"], {"kind": "running", "text": "", "label": "running"})
        self.assertEqual(data["unread"], {"kind": "unread", "text": "", "label": "unread"})
        self.assertEqual(data["idle"], {"kind": "idle", "text": "1小时", "label": "1小时"})
        self.assertEqual(
            data["inactiveQuestion"],
            {"kind": "waiting-user-input", "text": "", "label": "answer"},
        )
        self.assertEqual(
            data["inactiveAuthorization"],
            {"kind": "waiting-authorization", "text": "", "label": "confirm"},
        )
        self.assertEqual(
            data["activeWaitingRunning"],
            {"kind": "running", "text": "", "label": "running"},
        )
        self.assertEqual(
            data["activeWaitingUnread"],
            {"kind": "unread", "text": "", "label": "unread"},
        )

    def test_ticker_updates_only_idle_slots_once_per_minute_without_reordering(self):
        script = f"""
const window = {{Code: {{features: {{}}}}}};
global.window = window;
eval({json.dumps(SESSIONS_SOURCE)});
const sessionsFeature = window.Code.features.sessions;
let now = Date.parse("2026-08-24T12:00:59Z");
const sessionItems = [
  {{id: "older", lastMessageTime: "2026-08-24T11:59:59Z"}},
  {{id: "newer", lastMessageTime: "2026-08-24T12:00:30Z"}},
];
const idleSlot = {{
  dataset: {{sessionId: "older", sessionStatus: "idle"}},
  textContent: "1m",
  attrs: {{}},
  setAttribute(name, value) {{ this.attrs[name] = value; }},
  removeAttribute(name) {{ delete this.attrs[name]; }},
}};
const runningSlot = {{
  dataset: {{sessionId: "newer", sessionStatus: "running"}},
  textContent: "RUNNING",
}};
const selectors = [];
const root = {{
  querySelectorAll(selector) {{
    selectors.push(selector);
    return selector.includes('data-session-status="idle"') ? [idleSlot] : [idleSlot, runningSlot];
  }},
}};
let scheduled = 0;
let cancelled = 0;
let intervalMs = 0;
let callback = null;
const ticker = sessionsFeature.createSessionStatusTicker({{
  getRoot: () => root,
  getSessions: () => sessionItems,
  translate: (key, params = {{}}) => key === "sessionRelativeNow" ? "now" : `${{params.count}}m`,
  now: () => now,
  setInterval(fn, ms) {{ scheduled += 1; callback = fn; intervalMs = ms; return 17; }},
  clearInterval(id) {{ if (id === 17) cancelled += 1; }},
}});
const beforeOrder = sessionItems.map((item) => item.id);
const firstTimer = ticker.start();
const secondTimer = ticker.start();
now += 60_000;
const changes = callback();
const firstStop = ticker.stop();
const secondStop = ticker.stop();
process.stdout.write(JSON.stringify({{
  beforeOrder,
  afterOrder: sessionItems.map((item) => item.id),
  firstTimer,
  secondTimer,
  scheduled,
  cancelled,
  intervalMs,
  changes,
  idleText: idleSlot.textContent,
  idleAria: idleSlot.attrs["aria-label"],
  runningText: runningSlot.textContent,
  selectors,
  firstStop,
  secondStop,
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["beforeOrder"], ["older", "newer"])
        self.assertEqual(data["afterOrder"], ["older", "newer"])
        self.assertEqual(data["firstTimer"], 17)
        self.assertEqual(data["secondTimer"], 17)
        self.assertEqual(data["scheduled"], 1)
        self.assertEqual(data["cancelled"], 1)
        self.assertEqual(data["intervalMs"], 60_000)
        self.assertEqual(data["changes"], 1)
        self.assertEqual(data["idleText"], "2m")
        self.assertEqual(data["idleAria"], "2m")
        self.assertEqual(data["runningText"], "RUNNING")
        self.assertEqual(len(data["selectors"]), 1)
        self.assertIn('data-session-status="idle"', data["selectors"][0])
        self.assertTrue(data["firstStop"])
        self.assertFalse(data["secondStop"])

    def test_markup_i18n_and_css_keep_one_fixed_accessible_status_slot(self):
        render_start = APP_SOURCE.index("function renderSessionStatusSlot(")
        render_end = APP_SOURCE.index("function renderProjectSessionRow(", render_start)
        render_source = APP_SOURCE[render_start:render_end]
        row_end = APP_SOURCE.index("function renderProjectSection(", render_end)
        row_source = APP_SOURCE[render_end:row_end]
        ticker_start = SESSIONS_SOURCE.index("function createSessionStatusTicker(")
        ticker_end = SESSIONS_SOURCE.index("function createSessionsFeature(", ticker_start)
        ticker_source = SESSIONS_SOURCE[ticker_start:ticker_end]
        running_start = STYLE_SOURCE.index(
            ".session-status-slot.is-running .session-status-indicator {"
        )
        running_end = STYLE_SOURCE.index("}", running_start)
        running_source = STYLE_SOURCE[running_start:running_end]

        self.assertIn('data-session-status="idle"', render_source)
        self.assertIn('role="img" title="', render_source)
        self.assertIn('aria-label="', render_source)
        self.assertIn("renderSessionStatusSlot(session)", row_source)
        self.assertNotIn("if (!active)", row_source)
        self.assertNotIn("renderSessions", ticker_source)
        self.assertNotIn("fetch(", ticker_source)
        self.assertNotIn("apiJson", ticker_source)
        for running_contract in (
            "width: 11px;",
            "height: 11px;",
            "border: 2px solid var(--accent);",
            "border-right-color: transparent;",
            "animation: session-status-spin 1.4s linear infinite;",
        ):
            self.assertIn(running_contract, running_source)
        self.assertNotIn("session-status-spin .8s", running_source)
        for key in (
            "sessionRelativeNow",
            "sessionRelativeMinutes",
            "sessionRelativeHours",
            "sessionRelativeDays",
            "sessionWaitingAnswer",
            "sessionWaitingConfirmation",
        ):
            self.assertEqual(I18N_SOURCE.count(key + ":"), 2)
        for css_contract in (
            ".session-main .session-status-slot",
            "flex: 0 0 46px;",
            "white-space: nowrap;",
            ".session-status-slot.is-running .session-status-indicator",
            ".session-status-slot.is-unread .session-status-indicator",
            ".session-status-slot.is-waiting-user-input .session-status-indicator",
            ".session-status-slot.is-waiting-authorization .session-status-indicator",
            'content: "?";',
            'content: "!";',
            "background: var(--accent);",
            "@keyframes session-status-spin",
            "@media (prefers-reduced-motion: reduce)",
            "animation: none;",
        ):
            self.assertIn(css_contract, STYLE_SOURCE)
        self.assertIn("position: absolute;", STYLE_SOURCE[STYLE_SOURCE.index(".session-more-wrap"):])


class TestSidebarProjectArchitecture(unittest.TestCase):
    """Regression guards for the Codex-style project/session sidebar."""

    def test_project_css_classes_exist(self):
        """The sidebar has one project level and direct session children."""
        for cls_name in (
            "project-toolbar",
            "project-block",
            "project-header",
            "project-arrow",
            "project-name",
            "project-pin-indicator",
            "project-children",
            "project-empty-sessions",
            "project-sessions-toggle",
            "project-header-action",
            "session-source-badge",
        ):
            self.assertIn(
                "." + cls_name, STYLE_SOURCE,
                f"CSS class .{cls_name} missing from styles.css"
            )
        self.assertNotIn(".project-group-label", STYLE_SOURCE)
        self.assertNotIn(".project-group-children", STYLE_SOURCE)
        self.assertNotIn(".project-count", STYLE_SOURCE)

    def test_collapsed_css_exists(self):
        """Projects retain independent collapse state without source groups."""
        self.assertIn("project-children.collapsed", STYLE_SOURCE)
        self.assertIn("code-collapsed-projects", APP_SOURCE)
        self.assertNotIn("code-collapsed-groups", APP_SOURCE)

    def test_project_toolbar_replaces_independent_filter(self):
        """There is one project context model, not a second project filter."""
        self.assertIn('id="projectToolbar"', INDEX_SOURCE)
        self.assertIn('id="projectCreateBtn"', INDEX_SOURCE)
        self.assertNotIn('id="projectSelect"', INDEX_SOURCE)
        self.assertNotIn('id="projectFilter"', INDEX_SOURCE)

    def test_project_api_referenced_in_app_js(self):
        """Project API endpoint is referenced in app.js."""
        self.assertIn("/api/projects", APP_SOURCE)

    def test_agent_run_and_prompt_capture_the_session_workspace(self):
        self.assertIn("cwd: ctx.cwd ||", APP_SOURCE)
        self.assertIn("cwd: subCtx.cwd ||", APP_SOURCE)
        self.assertIn("cwd,", RUNTIME_SOURCE)
        self.assertIn("primaryRoot: projectPrimaryPath(project) || cwd", APP_SOURCE)
        self.assertIn("loadProjectContextForRoot(", APP_SOURCE)
        self.assertIn("projectContext: ctx?.projectContext", APP_SOURCE)

    def test_render_sessions_has_no_source_group_projection(self):
        """Source remains metadata and is never projected as a second tree level."""
        render_start = APP_SOURCE.index("function renderSessions()")
        render_end = APP_SOURCE.index("function openProjectContextMenu", render_start)
        render_source = APP_SOURCE[render_start:render_end]
        self.assertIn("sessionsByProject", render_source)
        self.assertNotIn("buildGroupMap", render_source)
        self.assertNotIn("session.group", render_source)
        self.assertIn("renderSessionSourceBadge", APP_SOURCE)

    def test_refreshProjects_function_exists(self):
        """Projects use canonical labels with compatibility fallback."""
        self.assertIn("async function refreshProjects", APP_SOURCE)
        self.assertIn("project?.label || project?.name", APP_SOURCE)

    def test_project_actions_are_keyboard_and_touch_reachable(self):
        self.assertIn("function attachProjectSessionListeners", APP_SOURCE)
        self.assertIn("project-more-btn", APP_SOURCE)
        self.assertIn("project-new-session", APP_SOURCE)
        self.assertIn("@media (hover: none), (max-width: 700px)", STYLE_SOURCE)

    def test_pinned_state_uses_a_shared_outline_pin_icon(self):
        self.assertIn("function renderPinIcon()", APP_SOURCE)
        self.assertIn('class="pin-icon"', APP_SOURCE)
        self.assertIn(".pin-icon", STYLE_SOURCE)
        self.assertNotIn("&#9733;", APP_SOURCE)

    def test_project_menu_contains_edit_and_pin_only(self):
        menu_start = APP_SOURCE.index("function openProjectContextMenu")
        menu_end = APP_SOURCE.index("function attachProjectSessionListeners", menu_start)
        menu_source = APP_SOURCE[menu_start:menu_end]
        self.assertIn('data-action="edit"', menu_source)
        self.assertIn('data-action="pin"', menu_source)
        self.assertNotIn('data-action="rename"', menu_source)
        self.assertNotIn('data-action="delete"', menu_source)
        self.assertIn("code-pinned-projects", APP_SOURCE)

    def test_project_editor_owns_rename_multi_folder_edit_and_delete(self):
        for element_id in (
            "projectEditModal",
            "projectEditName",
            "projectSourceFolderList",
            "addProjectFolder",
            "deleteProjectFromEdit",
            "saveProjectEdit",
            "projectDeleteConfirmModal",
            "confirmProjectDelete",
        ):
            self.assertIn(f'id="{element_id}"', INDEX_SOURCE)
        self.assertIn("/api/projects/", APP_SOURCE)
        self.assertIn('"/update"', APP_SOURCE)
        self.assertIn("/api/pick-folder", APP_SOURCE)
        self.assertIn("editingProjectRootPaths", APP_SOURCE)
        self.assertIn("rootPaths: editingProjectRootPaths", APP_SOURCE)
        self.assertIn('data-project-folder-action="primary"', APP_SOURCE)
        self.assertIn("project-edit-card", STYLE_SOURCE)
        self.assertIn("project-delete-confirm-card", STYLE_SOURCE)

    def test_add_folder_uses_a_conventional_folder_plus_icon(self):
        self.assertIn(
            "M3.5 7A2 2 0 0 1 5.5 5h3.75L11 7h7.5a2 2 0 0 1 2 2v8",
            INDEX_SOURCE,
        )
        self.assertIn("M15.5 11.5v5M13 14h5", INDEX_SOURCE)

    def test_sidebar_does_not_render_session_counts(self):
        render_start = APP_SOURCE.index("function renderProjectSection")
        render_end = APP_SOURCE.index("function renderSessions()", render_start)
        render_source = APP_SOURCE[render_start:render_end]
        self.assertNotIn("project-count", render_source)
        self.assertNotIn('t("showAllSessions", { count:', render_source)
        self.assertEqual(I18N_SOURCE.count('showAllSessions: "显示全部"'), 1)
        self.assertEqual(I18N_SOURCE.count('showAllSessions: "Show all"'), 1)

    def test_unassigned_sessions_have_concise_explanatory_copy(self):
        self.assertEqual(I18N_SOURCE.count('otherSessions: "无项目会话"'), 1)
        self.assertEqual(I18N_SOURCE.count('otherSessions: "No-project sessions"'), 1)
        self.assertEqual(I18N_SOURCE.count("unassignedSessionsHint:"), 2)
        self.assertIn('t("unassignedSessionsHint")', APP_SOURCE)

    def test_session_info_shows_project_not_group(self):
        self.assertIn('data-i18n="sessionProject"', INDEX_SOURCE)
        self.assertIn("projectDisplayName(project)", APP_SOURCE)

    def test_i18n_keys_exist(self):
        """Dynamic project controls switch language immediately."""
        for key in (
            "projectsLabel",
            "otherSessions",
            "noProject",
            "newSessionInProject",
            "projectActions",
            "noProjectSessions",
            "showAllSessions",
            "collapseSessions",
            "sessionProject",
            "editProject",
            "sourceFolder",
            "sourceFolders",
            "addSourceFolder",
            "primaryFolder",
            "makePrimary",
            "removeSourceFolder",
            "sourceFolderAlreadyAdded",
            "sessionDetachedFromProject",
            "changeSourceFolder",
            "deleteProject",
            "removeProjectTitle",
            "removeProjectDescription",
        ):
            self.assertEqual(I18N_SOURCE.count(key + ":"), 2)

    def test_project_preview_limits_recent_sessions_and_keeps_active_visible(self):
        helper_start = APP_SOURCE.index("const PROJECT_SESSION_PREVIEW_LIMIT")
        helper_end = APP_SOURCE.index("async function refreshProjects", helper_start)
        helper_source = APP_SOURCE[helper_start:helper_end]
        script = f"""
{helper_source}
const sessions = [
  {{ id: "s1", updatedAt: "2026-07-26T12:00:00" }},
  {{ id: "s2", updatedAt: "2026-07-26T11:00:00" }},
  {{ id: "s3", updatedAt: "2026-07-26T10:00:00" }},
  {{ id: "s4", updatedAt: "2026-07-26T09:00:00" }},
  {{ id: "s5", updatedAt: "2026-07-26T08:00:00" }},
];
const limited = selectProjectSessionPreview(sessions, ["s4"], "s5", false);
const expanded = selectProjectSessionPreview(sessions, ["s4"], "s5", true);
process.stdout.write(JSON.stringify({{
  limited: limited.items.map((item) => item.id),
  hiddenCount: limited.hiddenCount,
  expanded: expanded.items.map((item) => item.id),
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertEqual(data["limited"], ["s4", "s1", "s2", "s5"])
        self.assertEqual(data["hiddenCount"], 1)
        self.assertEqual(data["expanded"], ["s4", "s1", "s2", "s3", "s5"])

    def test_project_session_order_uses_conversation_time_after_pins(self):
        helper_start = APP_SOURCE.index("const PROJECT_SESSION_PREVIEW_LIMIT")
        helper_end = APP_SOURCE.index("async function refreshProjects", helper_start)
        helper_source = APP_SOURCE[helper_start:helper_end]
        script = f"""
{helper_source}
const sessions = [
  {{ id: "pinned-old", updatedAt: "2026-08-23T15:00:00Z", lastMessageTime: "2026-08-20T10:00:00Z" }},
  {{ id: "tie-alpha", updatedAt: "2026-08-20T11:00:00Z", lastMessageTime: "2026-08-20T13:00:00Z" }},
  {{ id: "tie-beta", updatedAt: "2026-08-20T09:00:00Z", lastMessageTime: "2026-08-20T13:00:00Z" }},
  {{ id: "fallback", updatedAt: "2026-08-20T12:00:00Z", lastMessageTime: "invalid" }},
  {{ id: "naive", updatedAt: "2026-08-20T12:30:00Z", lastMessageTime: "2026-08-24T13:00:00" }},
];
process.stdout.write(JSON.stringify(orderProjectSessions(sessions, ["pinned-old"]).map((item) => item.id)));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            ["pinned-old", "tie-alpha", "tie-beta", "naive", "fallback"],
        )

    def test_pinned_projects_sort_before_unpinned_projects(self):
        helper_start = APP_SOURCE.index("const PROJECT_SESSION_PREVIEW_LIMIT")
        helper_end = APP_SOURCE.index("async function refreshProjects", helper_start)
        helper_source = APP_SOURCE[helper_start:helper_end]
        script = f"""
{helper_source}
const projects = [
  {{ id: "a", label: "Alpha", path: "C:/Alpha" }},
  {{ id: "b", label: "Beta", path: "C:/Beta" }},
  {{ id: "c", label: "Charlie", path: "C:/Charlie" }},
];
process.stdout.write(JSON.stringify(orderProjects(projects, ["c"]).map((item) => item.id)));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(json.loads(completed.stdout), ["c", "a", "b"])

    def test_preview_expansion_is_persisted_per_project(self):
        self.assertIn("code-expanded-project-sessions", APP_SOURCE)
        self.assertIn("PROJECT_SESSION_PREVIEW_LIMIT = 3", APP_SOURCE)

    def test_new_session_inherits_project_without_filter_dropdown(self):
        navigation_start = SESSIONS_SOURCE.index("function createSessionNavigation(")
        create_start = SESSIONS_SOURCE.index("async function createSession(", navigation_start)
        create_end = SESSIONS_SOURCE.index("async function loadSession(", create_start)
        create_source = SESSIONS_SOURCE[create_start:create_end]
        self.assertIn("state.pendingProjectId", create_source)
        self.assertIn("body.projectId = projectId", create_source)
        self.assertNotIn("projectSelect", create_source)

    def test_session_restore_waits_for_sidebar_refresh(self):
        init_start = APP_SOURCE.index("async function init()")
        init_end = APP_SOURCE.index("await sessionStartup.restoreForegroundSession();", init_start)
        self.assertIn("await refreshSessions();", APP_SOURCE[init_start:init_end])


class ComposerThemeAndFileDragTests(unittest.TestCase):
    def test_composer_surfaces_follow_the_active_theme(self):
        for declaration in (
            "--composer-surface: color-mix(in srgb, var(--bg) 94%, var(--text) 6%);",
            "--composer-surface-hover: color-mix(in srgb, var(--bg) 92%, var(--text) 8%);",
            "--composer-surface-disabled: color-mix(in srgb, var(--bg) 97%, var(--text) 3%);",
            "--composer-surface-drag: color-mix(in srgb, var(--composer-surface) 88%, var(--accent) 12%);",
        ):
            self.assertIn(declaration, STYLE_SOURCE)

        self.assertIn(".composer:not(.drag-active):not(:focus-within):not(:has(textarea:disabled)):hover", STYLE_SOURCE)
        self.assertIn(".chat-pane.empty-chat .composer:focus-within", STYLE_SOURCE)
        self.assertIn(".chat-pane.empty-chat .composer:has(textarea:disabled)", STYLE_SOURCE)
        self.assertIn(".chat-pane.empty-chat .composer.drag-active", STYLE_SOURCE)
        self.assertIn("background: var(--composer-surface-drag);", STYLE_SOURCE)

        thumbs_start = STYLE_SOURCE.index(".image-thumbs {")
        thumbs_end = STYLE_SOURCE.index("}", thumbs_start)
        self.assertIn("background: transparent;", STYLE_SOURCE[thumbs_start:thumbs_end])
        bar_start = STYLE_SOURCE.index(".composer-bar {", STYLE_SOURCE.index("/* Main canvas"))
        bar_end = STYLE_SOURCE.index("}", bar_start)
        self.assertIn("background: transparent;", STYLE_SOURCE[bar_start:bar_end])

    def test_composer_text_states_keep_theme_readability(self):
        placeholder_start = STYLE_SOURCE.index(".composer textarea::placeholder")
        placeholder_end = STYLE_SOURCE.index("}", placeholder_start)
        placeholder_source = STYLE_SOURCE[placeholder_start:placeholder_end]
        self.assertIn("color: var(--muted);", placeholder_source)
        self.assertIn("opacity: 1;", placeholder_source)
        self.assertIn("caret-color: var(--accent);", STYLE_SOURCE)
        self.assertIn(".composer textarea:disabled", STYLE_SOURCE)
        self.assertIn("-webkit-text-fill-color: var(--muted);", STYLE_SOURCE)

    def test_composer_file_drag_state_is_form_scoped_and_depth_stable(self):
        drag_start = APP_SOURCE.index("let composerFileDragDepth = 0;")
        drag_end = APP_SOURCE.index('els.prompt.addEventListener("input"', drag_start)
        drag_source = APP_SOURCE[drag_start:drag_end]

        self.assertIn('types.includes("Files")', drag_source)
        self.assertIn('classList.toggle("drag-active", Boolean(active))', drag_source)
        self.assertIn("composerFileDragDepth += 1;", drag_source)
        self.assertIn("if (composerFileDragDepth === 0) return;", drag_source)
        self.assertIn("Math.max(0, composerFileDragDepth - 1)", drag_source)
        for event_name in ("dragenter", "dragover", "dragleave", "drop"):
            self.assertEqual(
                drag_source.count(f'els.chatForm.addEventListener("{event_name}"'),
                1,
            )

        self.assertNotIn('els.prompt.addEventListener("drop"', APP_SOURCE)
        self.assertNotIn('els.prompt.addEventListener("dragover"', APP_SOURCE)
        drop_start = drag_source.index('els.chatForm.addEventListener("drop"')
        drop_source = drag_source[drop_start:]
        self.assertLess(
            drop_source.index("clearComposerDragActive();"),
            drop_source.index("handleImageDrop(e);"),
        )

    def test_file_drag_feedback_preserves_existing_image_candidate_semantics(self):
        handler_start = APP_SOURCE.index("function handleImageDrop(e)")
        handler_end = APP_SOURCE.index("function updateAssistantMessage", handler_start)
        handler_source = APP_SOURCE[handler_start:handler_end]
        self.assertIn("if (isImageFileCandidate(file))", handler_source)
        self.assertIn("queueImageFile(file);", handler_source)


class LongTextDisplayTests(unittest.TestCase):
    def test_long_text_display_uses_real_overflow_and_page_local_state(self):
        script = r"""
global.window = global;
global.Code = {ui: {}};
global.innerHeight = 400;
const windowListeners = new Map();
global.addEventListener = (type, handler) => windowListeners.set(type, handler);
global.removeEventListener = (type, handler) => {
  if (windowListeners.get(type) === handler) windowListeners.delete(type);
};
require("./src/ui/messages.js");
const {createLongTextDisplayController} = window.Code.ui.messages;

function classList(initial = []) {
  const values = new Set(initial);
  return {
    add: (...names) => names.forEach((name) => values.add(name)),
    remove: (...names) => names.forEach((name) => values.delete(name)),
    toggle(name, force) {
      const next = force === undefined ? !values.has(name) : Boolean(force);
      if (next) values.add(name); else values.delete(name);
      return next;
    },
    contains: (name) => values.has(name),
    values: () => [...values],
  };
}

function eventTarget(extra = {}) {
  const listeners = new Map();
  return Object.assign({
    hidden: false,
    dataset: {},
    attributes: {},
    classList: classList(),
    addEventListener(type, handler) { listeners.set(type, handler); },
    removeEventListener(type, handler) {
      if (listeners.get(type) === handler) listeners.delete(type);
    },
    emit(type, event = {}) { listeners.get(type)?.(event); },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    listenerTypes: () => [...listeners.keys()],
  }, extra);
}

function messageFixture(key, scrollHeight, collapsedHeight) {
  const button = eventTarget({dataset: {userMessageToggle: key}});
  button.closest = (selector) => selector === "[data-user-message-toggle]" ? button : null;
  const wrapper = {
    dataset: {userMessageText: key},
    classList: classList(["is-collapsed"]),
    scrollHeight,
    get clientHeight() {
      return this.classList.contains("is-collapsed") ? Math.min(scrollHeight, collapsedHeight) : scrollHeight;
    },
    parentElement: {querySelector: () => button},
  };
  return {wrapper, button};
}

const longMessage = messageFixture("7", 260, 140);
const shortMessage = messageFixture("8", 100, 140);
const root = eventTarget({
  contains: () => true,
  querySelectorAll: (selector) => selector === "[data-user-message-text]"
    ? [longMessage.wrapper, shortMessage.wrapper]
    : [],
});
const style = {
  height: "",
  removeProperty(name) { if (name === "height") this.height = ""; },
};
let focusCount = 0;
const textarea = eventTarget({
  value: "FULL DRAFT CONTENT",
  scrollHeight: 600,
  scrollTop: 17,
  selectionStart: 5,
  selectionEnd: 11,
  selectionDirection: "forward",
  style,
  focus(options) { focusCount += 1; this.focusOptions = options; },
  setSelectionRange(start, end, direction) {
    this.selectionStart = start;
    this.selectionEnd = end;
    this.selectionDirection = direction;
  },
});
const composerToggle = eventTarget();
let layoutChanges = 0;
const controller = createLongTextDisplayController({
  root,
  textarea,
  composerToggle,
  sessionId: "session-a",
  getLabel: (key) => `label:${key}`,
  getComputedStyle: () => ({
    lineHeight: "20",
    paddingTop: "10",
    paddingBottom: "10",
    getPropertyValue: (name) => name === "--composer-compact-max-height" ? "120px" : "",
  }),
  getViewportHeight: () => 400,
  onLayoutChange: () => { layoutChanges += 1; },
});

const firstConnect = controller.connect();
const initial = {
  composerHidden: composerToggle.hidden,
  longHidden: longMessage.button.hidden,
  shortHidden: shortMessage.button.hidden,
  longExpanded: longMessage.button.attributes["aria-expanded"],
};
let prevented = false;
composerToggle.emit("mousedown", {preventDefault: () => { prevented = true; }});
composerToggle.emit("click");
const composerExpanded = {
  value: textarea.value,
  height: textarea.style.height,
  selection: [textarea.selectionStart, textarea.selectionEnd, textarea.selectionDirection],
  scrollTop: textarea.scrollTop,
  focused: focusCount,
  preventScroll: textarea.focusOptions?.preventScroll,
  prevented,
  expanded: controller.snapshot().composerExpanded,
};
composerToggle.emit("mousedown", {preventDefault() {}});
composerToggle.emit("click");
const composerCollapsed = {
  value: textarea.value,
  height: textarea.style.height,
  expanded: controller.snapshot().composerExpanded,
  focused: focusCount,
};

root.emit("click", {target: longMessage.button});
const expandedMessage = {
  expanded: longMessage.wrapper.classList.contains("is-expanded"),
  aria: longMessage.button.attributes["aria-expanded"],
  state: controller.snapshot().expandedUserMessages,
};
controller.syncUserMessages("session-a");
const redrawPreserved = longMessage.wrapper.classList.contains("is-expanded");
controller.setSession("session-b");
controller.syncUserMessages("session-b");
const sessionReset = {
  collapsed: longMessage.wrapper.classList.contains("is-collapsed"),
  aria: longMessage.button.attributes["aria-expanded"],
  state: controller.snapshot().expandedUserMessages,
};

textarea.scrollHeight = 100;
textarea.emit("input");
const compactDraft = {
  hidden: composerToggle.hidden,
  expanded: controller.snapshot().composerExpanded,
};
controller.disconnect();

process.stdout.write(JSON.stringify({
  firstConnect,
  initial,
  composerExpanded,
  composerCollapsed,
  expandedMessage,
  redrawPreserved,
  sessionReset,
  compactDraft,
  layoutChanges,
  rootListeners: root.listenerTypes(),
  textareaListeners: textarea.listenerTypes(),
  toggleListeners: composerToggle.listenerTypes(),
  windowListeners: [...windowListeners.keys()],
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["firstConnect"])
        self.assertEqual(data["initial"], {
            "composerHidden": False,
            "longHidden": False,
            "shortHidden": True,
            "longExpanded": "false",
        })
        self.assertEqual(data["composerExpanded"]["value"], "FULL DRAFT CONTENT")
        self.assertEqual(data["composerExpanded"]["height"], "180px")
        self.assertEqual(data["composerExpanded"]["selection"], [5, 11, "forward"])
        self.assertEqual(data["composerExpanded"]["scrollTop"], 17)
        self.assertTrue(data["composerExpanded"]["preventScroll"])
        self.assertTrue(data["composerExpanded"]["prevented"])
        self.assertTrue(data["composerExpanded"]["expanded"])
        self.assertEqual(data["composerCollapsed"], {
            "value": "FULL DRAFT CONTENT",
            "height": "",
            "expanded": False,
            "focused": 2,
        })
        self.assertEqual(data["expandedMessage"], {
            "expanded": True,
            "aria": "true",
            "state": ["7"],
        })
        self.assertTrue(data["redrawPreserved"])
        self.assertEqual(data["sessionReset"], {
            "collapsed": True,
            "aria": "false",
            "state": [],
        })
        self.assertEqual(data["compactDraft"], {"hidden": True, "expanded": False})
        self.assertEqual(data["layoutChanges"], 3)
        self.assertEqual(data["rootListeners"], [])
        self.assertEqual(data["textareaListeners"], [])
        self.assertEqual(data["toggleListeners"], [])
        self.assertEqual(data["windowListeners"], [])

    def test_user_projection_keeps_full_markdown_copy_and_attachments(self):
        script = r"""
global.window = global;
global.Code = {ui: {}};
require("./src/ui/messages.js");
const {createMessagesFeature} = window.Code.ui.messages;
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll('"', "&quot;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;");
const feature = createMessagesFeature({
  escapeHtml,
  renderMarkdown: (value) => `<md>${escapeHtml(value)}</md>`,
  t: (key) => key,
});
const full = "Line one\n\n```js\nconst full = true;\n```\nFinal line";
const plain = feature.renderUserProjection({role: "user", content: full}, 4);
const withImage = feature.renderUserProjection({
  role: "user",
  content: [{type: "text", text: full}, {type: "image", source: "ignored"}],
  _images: [{path: "attachments/full.png", name: "full.png", mime: "image/png"}],
}, 5);
const imageOnly = feature.renderUserProjection({
  role: "user",
  content: "",
  _images: [{path: "attachments/only.png", name: "only.png", mime: "image/png"}],
}, 6);
process.stdout.write(JSON.stringify({full, plain, withImage, imageOnly}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        data = json.loads(completed.stdout)
        escaped_full = data["full"].replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
        for html in (data["plain"], data["withImage"]):
            self.assertIn(escaped_full, html)
            self.assertIn("data-user-message-text", html)
            self.assertIn("data-user-message-toggle", html)
            self.assertIn(f'data-copy-text="{escaped_full}"', html)
            self.assertIn('aria-expanded="false"', html)
            self.assertIn('data-i18n-aria-label="expandUserMessage"', html)
        self.assertIn("attachments%2Ffull.png", data["withImage"])
        self.assertLess(
            data["withImage"].index("attachments%2Ffull.png"),
            data["withImage"].index("data-user-message-text"),
        )
        self.assertIn("attachments%2Fonly.png", data["imageOnly"])
        self.assertNotIn("data-user-message-text", data["imageOnly"])
        self.assertNotIn("data-user-message-toggle", data["imageOnly"])

    def test_long_text_contract_preserves_full_dispatch_data_and_accessibility(self):
        controller_start = MESSAGES_SOURCE.index("function createLongTextDisplayController")
        controller_end = MESSAGES_SOURCE.index("function tokenCount", controller_start)
        controller_source = MESSAGES_SOURCE[controller_start:controller_end]
        self.assertNotIn("textarea.value =", controller_source)
        self.assertNotIn(".slice(", controller_source)
        self.assertIn("textarea.selectionStart", controller_source)
        self.assertIn("textarea.setSelectionRange", controller_source)
        self.assertIn("expandedUserMessages.clear();", controller_source)
        self.assertIn("onLayoutChange();", controller_source)

        submit_start = APP_SOURCE.index('els.chatForm.addEventListener("submit"')
        submit_end = APP_SOURCE.index('els.newChat.addEventListener("click"', submit_start)
        submit_source = APP_SOURCE[submit_start:submit_end]
        self.assertIn("let text = els.prompt.value.trim();", submit_source)
        self.assertIn("const taskText = parallelTask !== null ? parallelTask : text;", submit_source)
        self.assertIn("dispatch(sessionId, taskText, imgs)", submit_source)
        self.assertIn("dispatchBackgroundSubAgent(sessionId, taskText, imgs)", submit_source)
        self.assertIn("await sendMessage(text, {", submit_source)

        for key in (
            "expandComposerInput",
            "collapseComposerInput",
            "expandUserMessage",
            "collapseUserMessage",
        ):
            self.assertIn(f'{key}: "', I18N_SOURCE)
        self.assertIn('aria-controls="prompt"', INDEX_SOURCE)
        self.assertIn('data-i18n-aria-label="expandComposerInput"', INDEX_SOURCE)
        self.assertIn("max-height: min(45vh, 420px);", STYLE_SOURCE)
        self.assertIn("--composer-compact-max-height: 154px;", STYLE_SOURCE)
        self.assertIn("--user-message-collapsed-lines: 8;", STYLE_SOURCE)
        self.assertIn("--user-message-collapsed-lines: 6;", STYLE_SOURCE)
        self.assertIn("--user-message-collapsed-height: 14.08em;", STYLE_SOURCE)
        self.assertIn("--user-message-collapsed-height: 10.56em;", STYLE_SOURCE)
        self.assertIn(".user-message-text.is-overflowing.is-collapsed::after", STYLE_SOURCE)
        self.assertNotIn("transition: max-height", STYLE_SOURCE)


class MessageScrollControllerTests(unittest.TestCase):
    def test_reading_anchor_consumes_space_and_releases_on_downward_intent(self):
        script = r"""
global.window = global;
global.Code = { ui: {} };
global.getSelection = () => ({ isCollapsed: true });
require("./src/ui/messages.js");

function classList() {
  const values = new Set();
  return {
    toggle(name, force) {
      const next = force === undefined ? !values.has(name) : Boolean(force);
      if (next) values.add(name); else values.delete(name);
      return next;
    },
    contains(name) { return values.has(name); },
  };
}

function eventTarget(extra = {}) {
  const listeners = new Map();
  return Object.assign({
    classList: classList(),
    dataset: {},
    attributes: {},
    tabIndex: -1,
    addEventListener(type, callback, options) { listeners.set(type, { callback, options }); },
    removeEventListener(type, callback) {
      if (listeners.get(type)?.callback === callback) listeners.delete(type);
    },
    emit(type, event = {}) { listeners.get(type)?.callback({ target: this, ...event }); },
    setAttribute(name, value) { this.attributes[name] = String(value); },
  }, extra);
}

let rawScrollTop = 200;
let reserve = 0;
let realHeight = 600;
const scrollWrites = [];
const container = eventTarget({ clientHeight: 400 });
Object.defineProperties(container, {
  scrollTop: {
    configurable: true,
    get() { return rawScrollTop; },
    set(value) { rawScrollTop = Number(value); scrollWrites.push(rawScrollTop); },
  },
  scrollHeight: {
    configurable: true,
    get() { return realHeight + reserve; },
  },
});
const content = eventTarget({
  style: { setProperty(_name, value) { reserve = Number.parseInt(value, 10) || 0; } },
});
const button = eventTarget();
const frames = new Map();
let nextFrame = 1;
function requestFrame(callback) { const id = nextFrame++; frames.set(id, callback); return id; }
function cancelFrame(id) { frames.delete(id); }
function flushFrames() {
  const callbacks = [...frames.values()];
  frames.clear();
  callbacks.forEach((callback) => callback());
}
const controller = Code.ui.messages.createMessageScrollController({
  container,
  content,
  button,
  requestAnimationFrame: requestFrame,
  cancelAnimationFrame: cancelFrame,
  ResizeObserver: null,
  isCompactViewport: () => false,
  findAnchorElement: (index) => index === 4 ? { offsetTop: 500 } : null,
  measureAnchorTop: (element) => element.offsetTop,
  applyAnchorReserve(value) { reserve = Number(value || 0); },
});
controller.setSession("s1");
controller.connect();

const began = controller.beginReadingAnchor("s1", 4);
const initial = controller.snapshot();
flushFrames();
const afterInitialFrame = controller.snapshot();

realHeight += 100;
controller.onContentChanged("s1");
flushFrames();
const afterGrowth = controller.snapshot();

container.emit("wheel", { deltaX: 0, deltaY: -24, ctrlKey: false });
rawScrollTop -= 24;
container.emit("scroll");
const afterUp = controller.snapshot();
const reserveAfterUp = reserve;

realHeight -= 40;
controller.onContentChanged("s1");
const afterShrink = controller.snapshot();
const reserveAfterShrink = reserve;

realHeight += 220;
controller.onContentChanged("s1");
flushFrames();
const afterExhaustion = controller.snapshot();

realHeight -= 220;
controller.onContentChanged("s1");
flushFrames();
const afterExhaustionShrink = controller.snapshot();

container.emit("wheel", { deltaX: 0, deltaY: 20, ctrlKey: false });
const afterDownIntent = controller.snapshot();
const reserveAfterDownIntent = reserve;

button.emit("click");
flushFrames();
const afterJump = controller.snapshot();
const realBottomAfterJump = rawScrollTop;

controller.beginReadingAnchor("s1", 4);
flushFrames();
container.emit("scroll");
rawScrollTop -= 20;
container.emit("scroll");
const beforeDirectDown = controller.snapshot();
rawScrollTop += 8;
container.emit("scroll");
const afterDirectDown = controller.snapshot();

controller.beginReadingAnchor("s1", 4);
controller.forceToLatest("s1");
flushFrames();
const afterForce = controller.snapshot();

controller.beginReadingAnchor("s1", 4);
controller.setSession("s2");
const afterSession = controller.snapshot();

const compactController = Code.ui.messages.createMessageScrollController({
  container,
  content,
  button,
  requestAnimationFrame: requestFrame,
  cancelAnimationFrame: cancelFrame,
  ResizeObserver: null,
  isCompactViewport: () => true,
  findAnchorElement: () => ({ offsetTop: 500 }),
  measureAnchorTop: (element) => element.offsetTop,
  applyAnchorReserve(value) { reserve = Number(value || 0); },
});
compactController.setSession("mobile");
const compactBegan = compactController.beginReadingAnchor("mobile", 1);
const compact = compactController.snapshot();

let layoutRawTop = 468;
let layoutReserve = 268;
let layoutRealHeight = 600;
let layoutAnchorTop = 500;
const layoutContainer = eventTarget({ clientHeight: 400 });
Object.defineProperties(layoutContainer, {
  scrollTop: {
    configurable: true,
    get() { return layoutRawTop; },
    set(value) { layoutRawTop = Number(value); },
  },
  scrollHeight: {
    configurable: true,
    get() { return layoutRealHeight + layoutReserve; },
  },
});
const layoutController = Code.ui.messages.createMessageScrollController({
  container: layoutContainer,
  content,
  button,
  requestAnimationFrame: requestFrame,
  cancelAnimationFrame: cancelFrame,
  ResizeObserver: null,
  isCompactViewport: () => false,
  findAnchorElement: () => ({ offsetTop: layoutAnchorTop }),
  measureAnchorTop: (element) => element.offsetTop,
  applyAnchorReserve(value) { layoutReserve = Number(value || 0); },
});
layoutController.setSession("layout");
layoutController.connect();
layoutController.beginReadingAnchor("layout", 2);
flushFrames();
layoutController.onContentChanged("layout");
frames.clear();
layoutContainer.emit("wheel", { deltaX: 0, deltaY: -20, ctrlKey: false });
const layoutAfterIntent = layoutController.snapshot();
layoutRawTop -= 20;
layoutContainer.emit("scroll");
const layoutAfterUp = layoutController.snapshot();
layoutAnchorTop += 50;
layoutRealHeight += 50;
layoutRawTop += 50;
layoutController.onContentChanged("layout");
layoutContainer.emit("scroll");
const layoutAfterProgrammaticShift = layoutController.snapshot();
layoutRawTop -= 10;
layoutContainer.emit("scroll");
const layoutAfterUserUp = layoutController.snapshot();

let visibleRawTop = 468;
let visibleReserve = 268;
const visibleRealHeight = 600;
const visibleContainer = eventTarget({ clientHeight: 400 });
Object.defineProperties(visibleContainer, {
  scrollTop: {
    configurable: true,
    get() { return visibleRawTop; },
    set(value) { visibleRawTop = Number(value); },
  },
  scrollHeight: {
    configurable: true,
    get() { return visibleRealHeight + visibleReserve; },
  },
});
const visibleButton = eventTarget();
const visibilityController = Code.ui.messages.createMessageScrollController({
  container: visibleContainer,
  content,
  button: visibleButton,
  requestAnimationFrame: requestFrame,
  cancelAnimationFrame: cancelFrame,
  ResizeObserver: null,
  isCompactViewport: () => false,
  findAnchorElement: () => ({ offsetTop: 500 }),
  measureAnchorTop: (element) => element.offsetTop,
  applyAnchorReserve(value) { visibleReserve = Number(value || 0); },
});
visibilityController.setSession("visibility");
visibilityController.connect();
visibilityController.beginReadingAnchor("visibility", 3);
flushFrames();
visibleContainer.emit("scroll");
const visibilityInitial = visibilityController.snapshot();
visibleContainer.emit("wheel", { deltaX: 0, deltaY: -20, ctrlKey: false });
visibleRawTop -= 20;
visibleContainer.emit("scroll");
const visibilityAfter20 = visibilityController.snapshot();
visibleRawTop -= 40;
visibleContainer.emit("scroll");
const visibilityAfter60 = visibilityController.snapshot();
visibleContainer.emit("wheel", { deltaX: 0, deltaY: 12, ctrlKey: false });
const visibilityAfterBlankRelease = visibilityController.snapshot();

visibilityController.beginReadingAnchor("visibility", 3);
flushFrames();
visibleContainer.emit("scroll");
visibleRawTop = 41;
visibleContainer.emit("scroll");
const visibilityAt159 = visibilityController.snapshot();
visibleRawTop = 40;
visibleContainer.emit("scroll");
const visibilityAt160 = visibilityController.snapshot();
visibleRawTop = 200;
visibleContainer.emit("scroll");
const visibilityReturned = visibilityController.snapshot();

process.stdout.write(JSON.stringify({
  afterDirectDown,
  afterDownIntent,
  afterExhaustion,
  afterExhaustionShrink,
  afterForce,
  afterGrowth,
  afterInitialFrame,
  afterJump,
  afterSession,
  afterShrink,
  afterUp,
  began,
  beforeDirectDown,
  compact,
  compactBegan,
  initial,
  layoutAfterProgrammaticShift,
  layoutAfterIntent,
  layoutAfterUp,
  layoutAfterUserUp,
  realBottomAfterJump,
  reserveAfterDownIntent,
  reserveAfterShrink,
  reserveAfterUp,
  scrollWrites,
  visibilityAfter20,
  visibilityAfter60,
  visibilityAfterBlankRelease,
  visibilityAt159,
  visibilityAt160,
  visibilityInitial,
  visibilityReturned,
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["began"])
        self.assertEqual(data["initial"]["readingAnchor"]["messageIndex"], 4)
        self.assertEqual(data["initial"]["readingAnchor"]["remainingReserve"], 268)
        self.assertEqual(data["afterInitialFrame"]["readingAnchor"]["remainingReserve"], 268)
        self.assertEqual(data["afterGrowth"]["readingAnchor"]["remainingReserve"], 168)
        self.assertEqual(data["afterGrowth"]["realContentDistance"], 0)
        self.assertFalse(data["afterGrowth"]["visible"])
        self.assertFalse(data["afterUp"]["following"])
        self.assertEqual(data["reserveAfterUp"], 144)
        self.assertEqual(data["afterUp"]["readingAnchor"]["userConsumedReserve"], 24)
        self.assertLessEqual(data["reserveAfterShrink"], data["reserveAfterUp"])
        self.assertEqual(data["afterShrink"]["readingAnchor"]["remainingReserve"], 144)
        self.assertEqual(data["afterExhaustion"]["readingAnchor"]["remainingReserve"], 0)
        self.assertEqual(data["afterExhaustionShrink"]["readingAnchor"]["remainingReserve"], 0)
        self.assertIsNone(data["afterDownIntent"]["readingAnchor"])
        self.assertEqual(data["reserveAfterDownIntent"], 0)
        self.assertIsNone(data["afterJump"]["readingAnchor"])
        self.assertEqual(data["realBottomAfterJump"], 260)
        self.assertIsNotNone(data["beforeDirectDown"]["readingAnchor"])
        self.assertFalse(data["beforeDirectDown"]["following"])
        self.assertEqual(data["beforeDirectDown"]["readingAnchor"]["userConsumedReserve"], 20)
        self.assertIsNone(data["afterDirectDown"]["readingAnchor"])
        self.assertIsNone(data["afterForce"]["readingAnchor"])
        self.assertIsNone(data["afterSession"]["readingAnchor"])
        self.assertTrue(data["compactBegan"])
        self.assertEqual(data["compact"]["readingAnchor"]["targetScrollTop"], 480)
        self.assertFalse(data["layoutAfterIntent"]["following"])
        self.assertTrue(data["layoutAfterIntent"]["awaitingUserScroll"])
        self.assertLess(data["layoutAfterUp"]["readingAnchor"]["remainingReserve"], 268)
        consumed_after_up = data["layoutAfterUp"]["readingAnchor"]["userConsumedReserve"]
        self.assertGreater(consumed_after_up, 0)
        self.assertEqual(
            data["layoutAfterProgrammaticShift"]["readingAnchor"]["remainingReserve"],
            data["layoutAfterUp"]["readingAnchor"]["remainingReserve"],
        )
        self.assertEqual(
            data["layoutAfterProgrammaticShift"]["readingAnchor"]["userConsumedReserve"],
            consumed_after_up,
        )
        self.assertEqual(
            data["layoutAfterUserUp"]["readingAnchor"]["remainingReserve"],
            data["layoutAfterProgrammaticShift"]["readingAnchor"]["remainingReserve"] - 10,
        )
        self.assertEqual(
            data["layoutAfterUserUp"]["readingAnchor"]["userConsumedReserve"],
            consumed_after_up + 10,
        )
        self.assertEqual(data["visibilityInitial"]["realContentDistance"], 0)
        self.assertFalse(data["visibilityInitial"]["visible"])
        self.assertEqual(data["visibilityAfter20"]["realContentDistance"], 0)
        self.assertEqual(data["visibilityAfter20"]["distance"], 20)
        self.assertFalse(data["visibilityAfter20"]["visible"])
        self.assertEqual(data["visibilityAfter60"]["realContentDistance"], 0)
        self.assertEqual(data["visibilityAfter60"]["distance"], 60)
        self.assertFalse(data["visibilityAfter60"]["visible"])
        self.assertIsNone(data["visibilityAfterBlankRelease"]["readingAnchor"])
        self.assertEqual(data["visibilityAfterBlankRelease"]["realContentDistance"], 0)
        self.assertFalse(data["visibilityAfterBlankRelease"]["visible"])
        self.assertEqual(data["visibilityAt159"]["realContentDistance"], 159)
        self.assertFalse(data["visibilityAt159"]["visible"])
        self.assertEqual(data["visibilityAt160"]["realContentDistance"], 160)
        self.assertTrue(data["visibilityAt160"]["visible"])
        self.assertEqual(data["visibilityReturned"]["realContentDistance"], 0)
        self.assertFalse(data["visibilityReturned"]["visible"])

    def test_reading_anchor_wiring_and_css_contract(self):
        controller_start = MESSAGES_SOURCE.index("function createMessageScrollController(options = {})")
        controller_end = MESSAGES_SOURCE.index("function createLongTextDisplayController", controller_start)
        controller_source = MESSAGES_SOURCE[controller_start:controller_end]
        for expected in (
            "function beginReadingAnchor(ownerSessionId, messageIndex)",
            "function reconcileReadingAnchor(initialize = false)",
            "function captureAnchorLayoutAdjustment()",
            "function consumeAnchorReserveForUpwardScroll(distance)",
            "function releaseReadingAnchorForDownwardIntent()",
            "function realContentDistanceToBottom()",
            "Math.min(currentReserve, requiredReserve)",
            "content?.style?.setProperty?.(\"--message-reading-anchor-space\", next)",
            "if (deltaY < 0) relinquishFollowingForUpwardIntent()",
            "else if (deltaY > 0) releaseReadingAnchorForDownwardIntent()",
        ):
            self.assertIn(expected, controller_source)
        anchor_start = controller_source.index("function reconcileReadingAnchor(initialize = false)")
        anchor_end = controller_source.index("function updateButton()", anchor_start)
        anchor_source = controller_source[anchor_start:anchor_end]
        self.assertNotIn("setTimeout", anchor_source)
        self.assertNotIn("preventDefault", controller_source)

        self.assertIn("--message-reading-anchor-space: 0px;", STYLE_SOURCE)
        self.assertIn(".message-list.has-reading-anchor-space", STYLE_SOURCE)
        self.assertIn("padding-bottom: var(--message-reading-anchor-space);", STYLE_SOURCE)
        self.assertIn("overflow-anchor: none;", STYLE_SOURCE)

        self.assertIn(
            "messageScrollController?.beginReadingAnchor(sessionId, snapshotIndex - 1);",
            APP_SOURCE,
        )
        self.assertIn(
            "messageScrollController?.beginReadingAnchor(\n      ctx.sessionId,\n      ctx.messages.indexOf(userMessage),",
            APP_SOURCE,
        )
        self.assertIn(
            "await submitSessionSteer(ctx, message, { createReadingAnchor: false });",
            APP_SOURCE,
        )
        queue_source = APP_SOURCE[
            APP_SOURCE.index("async function enqueueSessionMessage("):
            APP_SOURCE.index("async function submitSessionSteer(")
        ]
        parallel_source = APP_SOURCE[
            APP_SOURCE.index("async function dispatchBackgroundSubAgent("):
            APP_SOURCE.index("async function restoreBackgroundJobsForSession(")
        ]
        self.assertNotIn("beginReadingAnchor", queue_source)
        self.assertNotIn("beginReadingAnchor", parallel_source)

        send_source = APP_SOURCE[
            APP_SOURCE.index("async function sendMessage("):
            APP_SOURCE.index("function getSelectedModel()")
        ]
        self.assertLess(
            send_source.index("renderSessionMessages(sessionId);"),
            send_source.index("messageScrollController?.beginReadingAnchor(sessionId, snapshotIndex - 1);"),
        )
        self.assertLess(
            send_source.index("messageScrollController?.beginReadingAnchor(sessionId, snapshotIndex - 1);"),
            send_source.index("setStreaming(true, sessionId);"),
        )
        self.assertIn("if (options.createReadingAnchor !== false && ctx.sessionId === state.sessionId)", APP_SOURCE)
        self.assertIn("if (Number(error?.status || 0) === 409)", APP_SOURCE)

    def test_scroll_controller_preserves_position_and_coalesces_following_updates(self):
        script = r"""
global.window = global;
global.Code = { ui: {} };
require("./src/ui/messages.js");

function classList() {
  const values = new Set();
  return {
    toggle(name, force) {
      const next = force === undefined ? !values.has(name) : Boolean(force);
      if (next) values.add(name); else values.delete(name);
      return next;
    },
    contains(name) { return values.has(name); },
  };
}

function eventTarget(extra = {}) {
  const listeners = new Map();
  return Object.assign({
    classList: classList(),
    dataset: {},
    attributes: {},
    tabIndex: -1,
    addEventListener(type, callback, options) { listeners.set(type, { callback, options }); },
    removeEventListener(type, callback) {
      if (listeners.get(type)?.callback === callback) listeners.delete(type);
    },
    emit(type, event = {}) {
      listeners.get(type)?.callback({ target: this, ...event });
    },
    listenerCount(type) { return listeners.has(type) ? 1 : 0; },
    listenerOptions(type) { return listeners.get(type)?.options; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
  }, extra);
}

let nextFrame = 1;
const frames = new Map();
const requestFrame = (callback) => {
  const id = nextFrame++;
  frames.set(id, callback);
  return id;
};
const cancelFrame = (id) => frames.delete(id);
const flushFrames = () => {
  const callbacks = Array.from(frames.values());
  frames.clear();
  callbacks.forEach((callback) => callback());
};

const resizeObservers = [];
class FakeResizeObserver {
  constructor(callback) { this.callback = callback; resizeObservers.push(this); }
  observe() {}
  disconnect() {}
}

const container = eventTarget({ scrollHeight: 1000, clientHeight: 400, scrollTop: 600 });
const button = eventTarget();
const focusCalls = [];
let expandedSelection = false;
global.getSelection = () => ({ isCollapsed: !expandedSelection });
const focusTarget = { focus(options) { focusCalls.push(options); } };
const controller = Code.ui.messages.createMessageScrollController({
  container,
  content: {},
  button,
  focusTarget,
  requestAnimationFrame: requestFrame,
  cancelAnimationFrame: cancelFrame,
  ResizeObserver: FakeResizeObserver,
  getLabel: (key) => `label:${key}`,
});

controller.setSession("s1");
controller.connect();
const passiveIntentListeners = ["wheel", "touchstart", "touchmove", "touchend", "touchcancel"]
  .every((type) => container.listenerOptions(type)?.passive === true);
controller.onContentChanged("s1");
const pendingBeforeWheel = controller.snapshot();
container.emit("wheel", { deltaX: 0, deltaY: -24, ctrlKey: false });
const wheelIntent = controller.snapshot();
const wheelIntentTop = container.scrollTop;
flushFrames();
const wheelTopAfterFlush = container.scrollTop;
container.scrollTop = 576;
container.emit("scroll");
const handedOff = controller.snapshot();
const smallAwayFrames = frames.size;
container.scrollHeight = 1120;
controller.onContentChanged("s1");
const afterSmallGrowth = controller.snapshot();
const afterSmallGrowthTop = container.scrollTop;
const afterSmallGrowthFrames = frames.size;
container.scrollTop = 550;
container.emit("scroll");
const revealed = controller.snapshot();
container.scrollTop = 700;
container.emit("scroll");
const visibleNearBottom = controller.snapshot();
container.scrollTop = 550;
container.emit("scroll");
container.scrollHeight = 1200;
const preservedTop = container.scrollTop;
controller.onContentChanged("s1");
const afterGrowth = controller.snapshot();
const afterGrowthTop = container.scrollTop;
controller.setRunning(true, "s1");
const runningClass = button.classList.contains("is-running");
const runningLabel = button.attributes["aria-label"];
controller.setRunning(false, "other-session");
const isolatedRunning = controller.snapshot().running;
controller.setSuppressed(true);
const suppressedVisible = button.classList.contains("visible");
controller.setSuppressed(false);
const restoredVisible = button.classList.contains("visible");

container.scrollTop = 799;
container.emit("scroll");
flushFrames();
container.scrollHeight = 1400;
controller.onContentChanged("s1");
controller.onContentChanged("s1");
const coalescedFrames = frames.size;
flushFrames();
const followedTop = container.scrollTop;

container.scrollTop = 700;
container.emit("scroll");
button.emit("click");
const clickedTop = container.scrollTop;
const focusPreventedScroll = focusCalls[0]?.preventScroll === true;

controller.setRunning(true, "s1");
controller.setSession("s2");
const reset = controller.snapshot();
controller.setRunning(true, "s1");
const foreignSessionIgnored = controller.snapshot().running;
container.scrollHeight = 1600;
resizeObservers[0].callback();
resizeObservers[0].callback();
const resizeFrames = frames.size;
flushFrames();
const resizedTop = container.scrollTop;

controller.forceToLatest("s2");
flushFrames();
controller.onContentChanged("s2");
const pendingBeforeIgnoredInputs = controller.snapshot();
container.emit("wheel", { deltaX: 0, deltaY: 20, ctrlKey: false });
const afterDownwardWheel = controller.snapshot();
container.emit("wheel", { deltaX: 30, deltaY: -20, ctrlKey: false });
const afterHorizontalWheel = controller.snapshot();
container.emit("wheel", { deltaX: 0, deltaY: -20, ctrlKey: true });
const afterCtrlWheel = controller.snapshot();
container.emit("click");
const afterOrdinaryClick = controller.snapshot();
container.emit("touchstart", { touches: [{ clientY: 100 }] });
container.emit("touchend", { touches: [] });
const afterTouchTap = controller.snapshot();
container.emit("touchstart", { touches: [{ clientY: 100 }] });
container.emit("touchmove", { touches: [{ clientY: 102 }] });
container.emit("touchend", { touches: [] });
const afterTouchJitter = controller.snapshot();
expandedSelection = true;
container.emit("touchstart", { touches: [{ clientY: 100 }] });
container.emit("touchmove", { touches: [{ clientY: 112 }] });
expandedSelection = false;
const afterSelectionMove = controller.snapshot();

container.emit("touchstart", { touches: [{ clientY: 100 }] });
container.emit("touchmove", { touches: [{ clientY: 104 }] });
const touchIntent = controller.snapshot();
const touchIntentTop = container.scrollTop;
flushFrames();
const touchTopAfterFlush = container.scrollTop;
container.scrollHeight = 1800;
controller.onContentChanged("s2");
const touchAfterGrowth = controller.snapshot();
const touchTopAfterGrowth = container.scrollTop;
controller.disconnect();
const afterDisconnect = controller.snapshot();
const listenersAfterDisconnect = [
  "scroll", "wheel", "touchstart", "touchmove", "touchend", "touchcancel",
].reduce((total, type) => total + container.listenerCount(type), 0)
  + button.listenerCount("click");

process.stdout.write(JSON.stringify({
  passiveIntentListeners,
  pendingBeforeWheel,
  wheelIntent,
  wheelIntentTop,
  wheelTopAfterFlush,
  handedOff,
  smallAwayFrames,
  afterSmallGrowth,
  afterSmallGrowthTop,
  afterSmallGrowthFrames,
  revealed,
  visibleNearBottom,
  preservedTop,
  afterGrowth,
  afterGrowthTop,
  runningClass,
  runningLabel,
  isolatedRunning,
  suppressedVisible,
  restoredVisible,
  coalescedFrames,
  followedTop,
  clickedTop,
  focusPreventedScroll,
  reset,
  foreignSessionIgnored,
  resizeFrames,
  resizedTop,
  pendingBeforeIgnoredInputs,
  afterDownwardWheel,
  afterHorizontalWheel,
  afterCtrlWheel,
  afterOrdinaryClick,
  afterTouchTap,
  afterTouchJitter,
  afterSelectionMove,
  touchIntent,
  touchIntentTop,
  touchTopAfterFlush,
  touchAfterGrowth,
  touchTopAfterGrowth,
  afterDisconnect,
  listenersAfterDisconnect,
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)
        self.assertTrue(data["passiveIntentListeners"])
        self.assertTrue(data["pendingBeforeWheel"]["following"])
        self.assertTrue(data["pendingBeforeWheel"]["framePending"])
        self.assertFalse(data["wheelIntent"]["following"])
        self.assertTrue(data["wheelIntent"]["awaitingUserScroll"])
        self.assertFalse(data["wheelIntent"]["framePending"])
        self.assertEqual(data["wheelIntentTop"], 600)
        self.assertEqual(data["wheelTopAfterFlush"], 600)
        self.assertFalse(data["handedOff"]["following"])
        self.assertFalse(data["handedOff"]["awaitingUserScroll"])
        self.assertFalse(data["handedOff"]["visible"])
        self.assertEqual(data["handedOff"]["distance"], 24)
        self.assertEqual(data["smallAwayFrames"], 0)
        self.assertFalse(data["afterSmallGrowth"]["following"])
        self.assertFalse(data["afterSmallGrowth"]["visible"])
        self.assertEqual(data["afterSmallGrowth"]["distance"], 144)
        self.assertEqual(data["afterSmallGrowthTop"], 576)
        self.assertEqual(data["afterSmallGrowthFrames"], 0)
        self.assertTrue(data["revealed"]["visible"])
        self.assertFalse(data["revealed"]["following"])
        self.assertEqual(data["revealed"]["distance"], 170)
        self.assertFalse(data["visibleNearBottom"]["following"])
        self.assertTrue(data["visibleNearBottom"]["visible"])
        self.assertEqual(data["visibleNearBottom"]["distance"], 20)
        self.assertEqual(data["preservedTop"], 550)
        self.assertEqual(data["afterGrowth"]["distance"], 250)
        self.assertEqual(data["afterGrowthTop"], 550)
        self.assertTrue(data["runningClass"])
        self.assertEqual(data["runningLabel"], "label:scrollToLatestRunning")
        self.assertTrue(data["isolatedRunning"])
        self.assertFalse(data["suppressedVisible"])
        self.assertTrue(data["restoredVisible"])
        self.assertEqual(data["coalescedFrames"], 1)
        self.assertEqual(data["followedTop"], 1000)
        self.assertEqual(data["clickedTop"], 1000)
        self.assertTrue(data["focusPreventedScroll"])
        self.assertEqual(data["reset"]["sessionId"], "s2")
        self.assertTrue(data["reset"]["following"])
        self.assertFalse(data["reset"]["visible"])
        self.assertFalse(data["reset"]["running"])
        self.assertFalse(data["foreignSessionIgnored"])
        self.assertEqual(data["resizeFrames"], 1)
        self.assertEqual(data["resizedTop"], 1200)
        for key in (
            "pendingBeforeIgnoredInputs",
            "afterDownwardWheel",
            "afterHorizontalWheel",
            "afterCtrlWheel",
            "afterOrdinaryClick",
            "afterTouchTap",
            "afterTouchJitter",
            "afterSelectionMove",
        ):
            self.assertTrue(data[key]["following"], key)
            self.assertFalse(data[key]["awaitingUserScroll"], key)
            self.assertTrue(data[key]["framePending"], key)
        self.assertFalse(data["touchIntent"]["following"])
        self.assertTrue(data["touchIntent"]["awaitingUserScroll"])
        self.assertFalse(data["touchIntent"]["framePending"])
        self.assertEqual(data["touchIntentTop"], 1200)
        self.assertEqual(data["touchTopAfterFlush"], 1200)
        self.assertTrue(data["touchAfterGrowth"]["awaitingUserScroll"])
        self.assertEqual(data["touchTopAfterGrowth"], 1200)
        self.assertFalse(data["afterDisconnect"]["awaitingUserScroll"])
        self.assertEqual(data["listenersAfterDisconnect"], 0)

    def test_scroll_controller_guards_short_overflow_until_real_scroll(self):
        script = r"""
global.window = global;
global.Code = { ui: {} };
global.getSelection = () => ({ isCollapsed: true });
require("./src/ui/messages.js");

function classList() {
  const values = new Set();
  return {
    toggle(name, force) {
      const next = force === undefined ? !values.has(name) : Boolean(force);
      if (next) values.add(name); else values.delete(name);
      return next;
    },
    contains(name) { return values.has(name); },
  };
}

function eventTarget(extra = {}) {
  const listeners = new Map();
  return Object.assign({
    classList: classList(),
    dataset: {},
    attributes: {},
    tabIndex: -1,
    addEventListener(type, callback, options) { listeners.set(type, { callback, options }); },
    removeEventListener(type, callback) {
      if (listeners.get(type)?.callback === callback) listeners.delete(type);
    },
    emit(type, event = {}) {
      listeners.get(type)?.callback({ target: this, ...event });
    },
    listenerCount(type) { return listeners.has(type) ? 1 : 0; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
  }, extra);
}

function createHarness(overflow) {
  let rawScrollTop = overflow;
  const scrollWrites = [];
  const container = eventTarget({
    clientHeight: 400,
    scrollHeight: 400 + overflow,
  });
  Object.defineProperty(container, "scrollTop", {
    configurable: true,
    get() { return rawScrollTop; },
    set(value) {
      rawScrollTop = Number(value);
      scrollWrites.push(rawScrollTop);
    },
  });
  const button = eventTarget();
  const frames = new Map();
  let nextFrame = 1;
  let resizeCallback = null;
  class FakeResizeObserver {
    constructor(callback) { resizeCallback = callback; }
    observe() {}
    disconnect() {}
  }
  const controller = Code.ui.messages.createMessageScrollController({
    container,
    content: {},
    button,
    requestAnimationFrame(callback) {
      const id = nextFrame++;
      frames.set(id, callback);
      return id;
    },
    cancelAnimationFrame(id) { frames.delete(id); },
    ResizeObserver: FakeResizeObserver,
  });
  controller.setSession("s1");
  controller.connect();
  return {
    button,
    container,
    controller,
    frames,
    resize() { resizeCallback?.(); },
    scrollWrites,
    setBrowserScrollTop(value) { rawScrollTop = Number(value); },
  };
}

function guardedScenario(overflow, intent, running) {
  const harness = createHarness(overflow);
  const { container, controller, frames, scrollWrites } = harness;
  controller.setRunning(running, "s1");
  controller.onContentChanged("s1");
  const pending = controller.snapshot();
  if (intent === "touch") {
    container.emit("touchstart", { touches: [{ clientY: 100 }] });
    container.emit("touchmove", { touches: [{ clientY: 104 }] });
  } else {
    container.emit("wheel", { deltaX: 0, deltaY: -24, ctrlKey: false });
  }
  const afterIntent = controller.snapshot();
  let afterTouchEnd = null;
  let afterTouchCancel = null;
  if (intent === "touch") {
    container.emit("touchend", { touches: [] });
    afterTouchEnd = controller.snapshot();
    container.emit("touchcancel", { touches: [] });
    afterTouchCancel = controller.snapshot();
  }

  const movement = overflow >= 600 ? 200 : Math.min(20, overflow);
  const intendedTop = overflow - movement;
  harness.setBrowserScrollTop(intendedTop);
  scrollWrites.length = 0;
  container.scrollHeight += 7;
  controller.onContentChanged("s1");
  controller.onContentChanged("s1");
  harness.resize();
  harness.resize();
  const beforeRealScroll = controller.snapshot();
  const topBeforeRealScroll = container.scrollTop;
  const writesBeforeRealScroll = scrollWrites.slice();

  container.emit("scroll");
  const afterRealScroll = controller.snapshot();
  const capturedTop = container.scrollTop;
  container.scrollHeight += 11;
  controller.onContentChanged("s1");
  harness.resize();
  const afterLaterChanges = controller.snapshot();
  const topAfterLaterChanges = container.scrollTop;
  return {
    afterIntent,
    afterLaterChanges,
    afterRealScroll,
    afterTouchCancel,
    afterTouchEnd,
    beforeRealScroll,
    capturedTop,
    framesAfterIntent: frames.size,
    intent,
    intendedTop,
    overflow,
    pending,
    running,
    topAfterLaterChanges,
    topBeforeRealScroll,
    writesBeforeRealScroll,
  };
}

function toleranceScenario(distance) {
  const harness = createHarness(30);
  harness.setBrowserScrollTop(30 - distance);
  harness.container.emit("scroll");
  return { distance, snapshot: harness.controller.snapshot() };
}

function insufficientOverflowScenario(overflow, intent) {
  const harness = createHarness(overflow);
  harness.controller.onContentChanged("s1");
  if (intent === "touch") {
    harness.container.emit("touchstart", { touches: [{ clientY: 100 }] });
    harness.container.emit("touchmove", { touches: [{ clientY: 104 }] });
  } else {
    harness.container.emit("wheel", { deltaX: 0, deltaY: -24, ctrlKey: false });
  }
  return { overflow, intent, snapshot: harness.controller.snapshot() };
}

function cleanupScenarios() {
  const clickHarness = createHarness(600);
  clickHarness.controller.onContentChanged("s1");
  clickHarness.container.emit("wheel", { deltaX: 0, deltaY: -24, ctrlKey: false });
  const awaitingBeforeClick = clickHarness.controller.snapshot();
  clickHarness.button.emit("click");
  const afterClick = clickHarness.controller.snapshot();

  clickHarness.container.emit("wheel", { deltaX: 0, deltaY: -24, ctrlKey: false });
  const awaitingBeforeSession = clickHarness.controller.snapshot();
  clickHarness.controller.setSession("s2");
  const afterSession = clickHarness.controller.snapshot();

  clickHarness.controller.onContentChanged("s2");
  clickHarness.container.emit("wheel", { deltaX: 0, deltaY: -24, ctrlKey: false });
  const awaitingBeforeDisconnect = clickHarness.controller.snapshot();
  clickHarness.controller.disconnect();
  const afterDisconnect = clickHarness.controller.snapshot();

  const directScrollHarness = createHarness(600);
  directScrollHarness.setBrowserScrollTop(500);
  directScrollHarness.container.emit("scroll");
  const directScroll = directScrollHarness.controller.snapshot();
  directScrollHarness.container.scrollHeight += 20;
  directScrollHarness.controller.onContentChanged("s1");
  directScrollHarness.resize();
  const directScrollTopAfterChanges = directScrollHarness.container.scrollTop;

  return {
    afterClick,
    afterDisconnect,
    afterSession,
    awaitingBeforeClick,
    awaitingBeforeDisconnect,
    awaitingBeforeSession,
    directScroll,
    directScrollTopAfterChanges,
  };
}

const guarded = [];
for (const overflow of [10, 30, 80, 150, 600]) {
  guarded.push(guardedScenario(overflow, "wheel", true));
  guarded.push(guardedScenario(overflow, "touch", false));
}
const insufficient = [];
for (const overflow of [0, 1, 2]) {
  insufficient.push(insufficientOverflowScenario(overflow, "wheel"));
  insufficient.push(insufficientOverflowScenario(overflow, "touch"));
}
process.stdout.write(JSON.stringify({
  cleanup: cleanupScenarios(),
  guarded,
  insufficient,
  tolerance: [1, 2, 3].map(toleranceScenario),
}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(completed.stdout)

        self.assertEqual(len(data["guarded"]), 10)
        for scenario in data["guarded"]:
            label = f'{scenario["intent"]}:{scenario["overflow"]}'
            self.assertTrue(scenario["pending"]["following"], label)
            self.assertTrue(scenario["pending"]["framePending"], label)
            self.assertFalse(scenario["afterIntent"]["following"], label)
            self.assertTrue(scenario["afterIntent"]["awaitingUserScroll"], label)
            self.assertFalse(scenario["afterIntent"]["framePending"], label)
            self.assertEqual(scenario["framesAfterIntent"], 0, label)
            if scenario["intent"] == "touch":
                self.assertTrue(scenario["afterTouchEnd"]["awaitingUserScroll"], label)
                self.assertTrue(scenario["afterTouchCancel"]["awaitingUserScroll"], label)
            self.assertTrue(scenario["beforeRealScroll"]["awaitingUserScroll"], label)
            self.assertEqual(scenario["writesBeforeRealScroll"], [], label)
            self.assertEqual(scenario["topBeforeRealScroll"], scenario["intendedTop"], label)
            self.assertFalse(scenario["afterRealScroll"]["awaitingUserScroll"], label)
            self.assertFalse(scenario["afterRealScroll"]["following"], label)
            self.assertEqual(scenario["capturedTop"], scenario["intendedTop"], label)
            self.assertEqual(scenario["topAfterLaterChanges"], scenario["intendedTop"], label)
            self.assertFalse(scenario["afterLaterChanges"]["awaitingUserScroll"], label)
            self.assertEqual(
                scenario["afterRealScroll"]["visible"],
                scenario["overflow"] >= 600,
                label,
            )

        for scenario in data["insufficient"]:
            label = f'{scenario["intent"]}:{scenario["overflow"]}'
            self.assertTrue(scenario["snapshot"]["following"], label)
            self.assertFalse(scenario["snapshot"]["awaitingUserScroll"], label)
            self.assertTrue(scenario["snapshot"]["framePending"], label)

        tolerance = {item["distance"]: item["snapshot"] for item in data["tolerance"]}
        self.assertTrue(tolerance[1]["following"])
        self.assertTrue(tolerance[2]["following"])
        self.assertFalse(tolerance[3]["following"])
        for snapshot in tolerance.values():
            self.assertFalse(snapshot["awaitingUserScroll"])

        cleanup = data["cleanup"]
        for key in (
            "awaitingBeforeClick",
            "awaitingBeforeSession",
            "awaitingBeforeDisconnect",
        ):
            self.assertTrue(cleanup[key]["awaitingUserScroll"], key)
        for key in ("afterClick", "afterSession", "afterDisconnect"):
            self.assertFalse(cleanup[key]["awaitingUserScroll"], key)
        self.assertTrue(cleanup["afterClick"]["following"])
        self.assertTrue(cleanup["afterSession"]["following"])
        self.assertFalse(cleanup["directScroll"]["following"])
        self.assertFalse(cleanup["directScroll"]["awaitingUserScroll"])
        self.assertEqual(cleanup["directScrollTopAfterChanges"], 500)

    def test_scroll_to_latest_dom_theme_accessibility_and_app_wiring(self):
        for expected in (
            'id="scrollToBottomBtn"',
            'data-i18n-title="scrollToLatest"',
            'data-i18n-aria-label="scrollToLatest"',
            'class="scroll-to-bottom-idle-icon"',
            'class="scroll-to-bottom-running-icon"',
        ):
            self.assertIn(expected, INDEX_SOURCE)

        for expected in (
            'scrollToLatest: "回到最新消息"',
            'scrollToLatestRunning: "任务运行中，回到最新消息"',
            'scrollToLatest: "Jump to latest message"',
            'scrollToLatestRunning: "Task running, jump to latest message"',
        ):
            self.assertIn(expected, I18N_SOURCE)

        for expected in (
            "--scroll-jump-surface: color-mix(",
            ".scroll-to-bottom-btn.visible",
            ".scroll-to-bottom-btn.is-running .scroll-to-bottom-running-icon",
            ".scroll-to-bottom-btn:focus-visible",
            "@keyframes scroll-jump-progress",
            "@media (prefers-reduced-motion: reduce)",
            ".chat-pane.empty-chat .scroll-to-bottom-btn",
        ):
            self.assertIn(expected, STYLE_SOURCE)

        running_start = STYLE_SOURCE.index(".scroll-to-bottom-running-icon {")
        running_end = STYLE_SOURCE.index("}", running_start)
        running_source = STYLE_SOURCE[running_start:running_end]
        for expected in (
            "display: none;",
            "align-items: center;",
            "justify-content: center;",
            "gap: 3.5px;",
        ):
            self.assertIn(expected, running_source)
        dot_start = STYLE_SOURCE.index(".scroll-to-bottom-running-icon > span {")
        dot_end = STYLE_SOURCE.index("}", dot_start)
        self.assertIn("position: static;", STYLE_SOURCE[dot_start:dot_end])
        for index, delay in ((1, "-.24s"), (2, "-.12s"), (3, "0s")):
            selector = f".scroll-to-bottom-running-icon > span:nth-child({index}) {{"
            state_start = STYLE_SOURCE.index(selector)
            state_end = STYLE_SOURCE.index("}", state_start)
            state_source = STYLE_SOURCE[state_start:state_end]
            self.assertIn(f"animation-delay: {delay};", state_source)
            self.assertNotRegex(state_source, r"\b(?:bottom|left|right)\s*:")
        active_start = STYLE_SOURCE.index(
            ".scroll-to-bottom-btn.is-running .scroll-to-bottom-running-icon {"
        )
        active_end = STYLE_SOURCE.index("}", active_start)
        self.assertIn("display: flex;", STYLE_SOURCE[active_start:active_end])
        button_start = STYLE_SOURCE.index(".scroll-to-bottom-btn {")
        button_end = STYLE_SOURCE.index("}", button_start)
        button_source = STYLE_SOURCE[button_start:button_end]
        self.assertIn("width: 40px;", button_source)
        self.assertIn("height: 40px;", button_source)
        reduced_start = STYLE_SOURCE.index(
            "@media (prefers-reduced-motion: reduce)", active_end
        )
        reduced_end = STYLE_SOURCE.index("}\n}", reduced_start) + 3
        reduced_source = STYLE_SOURCE[reduced_start:reduced_end]
        self.assertIn("animation: none;", reduced_source)
        self.assertIn("transform: none;", reduced_source)

        for expected in (
            "createMessageScrollController",
            "messageScrollController?.forceToLatest(sessionId)",
            "messageScrollController?.onContentChanged(sessionId)",
            "messageScrollController?.onViewportChanged(state.sessionId)",
            "messageScrollController?.setSuppressed(true)",
            "messageScrollController?.setSuppressed(false)",
            "messageScrollController?.setRunning(active, sessionId)",
        ):
            self.assertIn(expected, APP_SOURCE)
        self.assertNotIn("els.messages.scrollTop = els.messages.scrollHeight", APP_SOURCE)
        self.assertNotIn("state._followOutput", APP_SOURCE)

        self.assertIn("function createMessageScrollController(options = {})", MESSAGES_SOURCE)
        self.assertIn("const bottomTolerance = Number(options.bottomTolerance ?? 2)", MESSAGES_SOURCE)
        self.assertNotIn("followThreshold", MESSAGES_SOURCE)
        self.assertIn("const revealThreshold = Number(options.revealThreshold ?? 160)", MESSAGES_SOURCE)
        self.assertIn('focusTarget.focus({ preventScroll: true })', MESSAGES_SOURCE)
        self.assertIn('root.addEventListener("toggle"', MESSAGES_SOURCE)
        controller_start = MESSAGES_SOURCE.index("function createMessageScrollController(options = {})")
        controller_end = MESSAGES_SOURCE.index("function createLongTextDisplayController", controller_start)
        controller_source = MESSAGES_SOURCE[controller_start:controller_end]
        for expected in (
            "function relinquishFollowingForUpwardIntent()",
            "let awaitingUserScroll = false",
            "maxScrollTop() <= bottomTolerance",
            'container.addEventListener("wheel", onWheelIntent, passiveListenerOptions)',
            'container.addEventListener("touchstart", onTouchStart, passiveListenerOptions)',
            'container.addEventListener("touchmove", onTouchMove, passiveListenerOptions)',
            'container?.removeEventListener?.("wheel", onWheelIntent, passiveListenerOptions)',
            'container?.removeEventListener?.("touchmove", onTouchMove, passiveListenerOptions)',
        ):
            self.assertIn(expected, controller_source)
        self.assertNotIn("preventDefault", controller_source)


if __name__ == "__main__":
    unittest.main()
