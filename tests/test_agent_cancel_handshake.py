"""Regression coverage for durable foreground AgentRun cancellation."""

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
APP_SOURCE = (ROOT / "app.js").read_text(encoding="utf-8")
STATE_SOURCE = (ROOT / "src" / "core" / "state.js").read_text(encoding="utf-8")
I18N_SOURCE = (ROOT / "src" / "core" / "i18n.js").read_text(encoding="utf-8")


class TestAgentCancelHandshake(unittest.TestCase):

    def _run_cancel_scenario(self, body):
        start = APP_SOURCE.index("function clearObservedAgentRun(ctx)")
        end = APP_SOURCE.index("function backgroundActiveForSession", start)
        helpers = APP_SOURCE[start:end]
        script = f"""
let agentRuntime;
const toasts = [];
function t(key) {{ return key; }}
function showToast(message, type) {{ toasts.push([message, type]); }}
{helpers}
{body}
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return json.loads(completed.stdout)

    def _run_pause_finalizer_scenario(self, body):
        start = APP_SOURCE.index("function finalizeRunTiming(sessionId")
        end = APP_SOURCE.index("function placeMainResultByCompletionOrder", start)
        helpers = APP_SOURCE[start:end]
        script = f"""
const state = {{ sessionId: "session-1" }};
const sessions = new Map();
const runs = new Map();
function t(key) {{ return key === "outputPaused" ? "[Output paused]" : key; }}
function ensureSessionRun(id) {{ return runs.get(id); }}
function getSessionMessages(id) {{ return sessions.get(id) || []; }}
function setSessionMessages(id, messages) {{ sessions.set(id, messages); }}
function isDetachedFromMainContext() {{ return false; }}
function activeRunElapsedMs() {{ return 15000; }}
function formatElapsedMs() {{ return "15s"; }}
function getSelectedModel() {{ return "test-model"; }}
function placeMainResultByCompletionOrder() {{}}
{helpers}
{body}
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return json.loads(completed.stdout)

    def test_server_cancel_keeps_observer_alive_and_deduplicates_clicks(self):
        result = self._run_cancel_scenario(r"""
const calls = [];
let resolveCancellation;
agentRuntime = {
  cancelAgentRun(id) {
    calls.push(["agent", id]);
    return new Promise((resolve) => { resolveCancellation = resolve; });
  },
  cancelRun(id) {
    calls.push(["runtime", id]);
    return Promise.resolve();
  },
};
const ctx = { agentRunId: "agent-1", agentEventCursor: 2 };
const run = {
  agentRunId: "agent-1",
  agentEventCursor: 2,
  runtimeRunId: "runtime-1",
  cancelRequested: false,
  _activeCtx: ctx,
  abortController: { abort() { calls.push(["abort"]); } },
};
ctx.run = run;
cancelSessionRun(run);
cancelSessionRun(run);
resolveCancellation({ ok: true });
setImmediate(() => process.stdout.write(JSON.stringify({
  calls,
  agentRunId: run.agentRunId,
  ctxAgentRunId: ctx.agentRunId,
  cursor: run.agentEventCursor,
  cancelRequested: run.cancelRequested,
})));
""")
        self.assertEqual(result, {
            "calls": [["agent", "agent-1"]],
            "agentRunId": "agent-1",
            "ctxAgentRunId": "agent-1",
            "cursor": 2,
            "cancelRequested": True,
        })

    def test_terminal_observation_clears_agent_references(self):
        result = self._run_cancel_scenario(r"""
agentRuntime = {};
const ctx = { agentRunId: "agent-1", agentEventCursor: 3 };
const run = {
  agentRunId: "agent-1",
  agentEventCursor: 3,
  cancelRequested: true,
};
ctx.run = run;
clearObservedAgentRun(ctx);
process.stdout.write(JSON.stringify({
  ctxAgentRunId: ctx.agentRunId,
  ctxCursor: ctx.agentEventCursor,
  runAgentRunId: run.agentRunId,
  runCursor: run.agentEventCursor,
  cancelRequested: run.cancelRequested,
}));
""")
        self.assertEqual(result, {
            "ctxAgentRunId": "",
            "ctxCursor": 0,
            "runAgentRunId": "",
            "runCursor": 0,
            "cancelRequested": False,
        })

    def test_cancel_failure_reenables_retry_without_aborting_observer(self):
        result = self._run_cancel_scenario(r"""
const calls = [];
console.error = () => {};
agentRuntime = {
  cancelAgentRun(id) {
    calls.push(["agent", id]);
    return Promise.reject(new Error("offline"));
  },
};
const run = {
  agentRunId: "agent-1",
  cancelRequested: false,
  abortController: { abort() { calls.push(["abort"]); } },
};
cancelSessionRun(run);
setImmediate(() => process.stdout.write(JSON.stringify({
  calls,
  agentRunId: run.agentRunId,
  cancelRequested: run.cancelRequested,
  toasts,
})));
""")
        self.assertEqual(result, {
            "calls": [["agent", "agent-1"]],
            "agentRunId": "agent-1",
            "cancelRequested": False,
            "toasts": [["cancelRunFailed", "error"]],
        })

    def test_legacy_runtime_cancel_still_aborts_local_stream(self):
        result = self._run_cancel_scenario(r"""
const calls = [];
agentRuntime = {
  cancelRun(id) {
    calls.push(["runtime", id]);
    return Promise.resolve();
  },
};
const run = {
  agentRunId: "",
  runtimeRunId: "runtime-1",
  cancelRequested: false,
  abortController: { abort() { calls.push(["abort"]); } },
};
cancelSessionRun(run);
process.stdout.write(JSON.stringify({
  calls,
  runtimeRunId: run.runtimeRunId,
}));
""")
        self.assertEqual(result, {
            "calls": [["runtime", "runtime-1"], ["abort"]],
            "runtimeRunId": "",
        })

    def test_session_run_state_declares_cancel_request_flag(self):
        self.assertIn("cancelRequested: false", STATE_SOURCE)
        self.assertIn('outputPaused: "[已暂停输出]"', I18N_SOURCE)
        self.assertIn('outputPaused: "[Output paused]"', I18N_SOURCE)
        self.assertIn('cancelRunFailed: "停止任务失败，请重试"', I18N_SOURCE)
        self.assertIn('cancelRunFailed: "Could not stop the task. Try again."', I18N_SOURCE)

    def test_model_pause_without_output_creates_timed_marker(self):
        result = self._run_pause_finalizer_scenario(r"""
const messages = [{ role: "user", content: "hello" }];
const run = { taskStartTime: Date.now() - 15000, responseStartTime: Date.now() - 10000 };
sessions.set("session-1", messages);
runs.set("session-1", run);
const ctx = { sessionId: "session-1", messages, run, model: "test-model" };
const target = finalizePausedRun(ctx);
process.stdout.write(JSON.stringify({ messages, target, run }));
""")
        self.assertEqual(len(result["messages"]), 2)
        self.assertEqual(result["target"]["content"], "[Output paused]")
        self.assertEqual(result["target"]["_responseTime"], "15s")
        self.assertEqual(result["target"]["meta"]["_responseTime"], "15s")
        self.assertTrue(result["target"]["meta"]["runPaused"])
        self.assertIsNone(result["run"]["taskStartTime"])

    def test_model_pause_preserves_partial_output_without_usage(self):
        result = self._run_pause_finalizer_scenario(r"""
const assistant = {
  role: "assistant",
  content: "partial answer",
  thought: "partial thought",
  streaming: true,
  _streamProjection: "answer",
  meta: { _usage: { input: 10, output: 3 }, _usageScope: "task" },
};
const messages = [{ role: "user", content: "hello" }, assistant];
const run = { taskStartTime: Date.now() - 15000 };
sessions.set("session-1", messages);
runs.set("session-1", run);
const ctx = { sessionId: "session-1", messages, run };
finalizePausedRun(ctx);
finalizePausedRun(ctx);
process.stdout.write(JSON.stringify({ messages, assistant }));
""")
        self.assertEqual(result["assistant"]["content"], "partial answer\n\n[Output paused]")
        self.assertEqual(result["assistant"]["content"].count("[Output paused]"), 1)
        self.assertFalse(result["assistant"]["streaming"])
        self.assertNotIn("_streamProjection", result["assistant"])
        self.assertNotIn("_usage", result["assistant"]["meta"])
        self.assertNotIn("_usageScope", result["assistant"]["meta"])
        self.assertEqual(result["assistant"]["_responseTime"], "15s")

    def test_abort_uses_shared_terminal_publication_and_still_finalizes_pause(self):
        send_start = APP_SOURCE.index("async function sendMessage(userText")
        send_end = APP_SOURCE.index("function getSelectedModel()", send_start)
        send_source = APP_SOURCE[send_start:send_end]
        abort_start = send_source.index("if (loopError) {")
        publish_position = send_source.index("publishTerminalRunOwnership(ctx);")
        pause_position = send_source.index("if (isAbort) finalizePausedRun(ctx);", abort_start)
        self.assertLess(publish_position, abort_start)
        self.assertLess(abort_start, pause_position)

        continue_start = APP_SOURCE.index("async function continueAgentRun()")
        continue_end = APP_SOURCE.index("async function renameSession", continue_start)
        continue_source = APP_SOURCE[continue_start:continue_end]
        self.assertLess(
            continue_source.index("finalizePausedRun(ctx);"),
            continue_source.index("publishTerminalRunOwnership(ctx);"),
        )

    def test_cancelled_child_runtime_keeps_partial_projection_for_pause_finalizer(self):
        start = APP_SOURCE.index("async function attachAgentRuntimeProjection(ctx, event")
        end = APP_SOURCE.index("function projectAgentModelCompleted(ctx, event)", start)
        projection = APP_SOURCE[start:end]
        cancelled = 'ctx.run?.cancelRequested || error?.code === "runtime_cancelled"'
        discard = "if (projectedIndex >= 0) ctx.messages.splice(projectedIndex, 1);"

        self.assertIn(cancelled, projection)
        self.assertNotIn(discard, projection)
        cancellation_start = projection.index(cancelled)
        cancellation_end = projection.index(
            "// The parent AgentRun owns this child Runtime ID.",
            cancellation_start,
        )
        self.assertIn("return;", projection[cancellation_start:cancellation_end])

    def test_tool_completion_pairs_agent_run_and_tool_call_identity(self):
        start = APP_SOURCE.index("function projectAgentToolCompleted(ctx, event)")
        end = APP_SOURCE.index("async function projectAgentEvent", start)
        projection = APP_SOURCE[start:end]
        script = f"""
function isInternalGoalToolName() {{ return false; }}
function findAgentProjectionMessage() {{ return null; }}
function normalizeNativeToolCall(call) {{
  return {{action: call.function.name, _toolCallId: call.id, _native: true}};
}}
function formatToolCall() {{ return ""; }}
function projectAgentToolStarted(ctx, event) {{
  ctx.messages.push({{
    role: "tool-call",
    meta: {{
      agentRunId: ctx.agentRunId,
      toolCallId: event.data.toolCallId,
      action: event.data.name,
    }},
  }});
}}
let selectedCall = null;
function projectServerEditToolCompleted(_ctx, _event, callMessage) {{
  selectedCall = callMessage;
  return false;
}}
function formatToolResult(result) {{ return JSON.stringify(result); }}
function agentEventMeta(ctx, event, eventType) {{
  return {{agentRunId: ctx.agentRunId, agentEventType: eventType, agentEventSeq: event.seq}};
}}
{projection}
const runACall = {{role: "tool-call", meta: {{agentRunId: "run-a", toolCallId: "shared", action: "read_file"}}}};
const runBCall = {{role: "tool-call", meta: {{agentRunId: "run-b", toolCallId: "shared", action: "read_file"}}}};
const ctx = {{agentRunId: "run-b", messages: [runACall, runBCall]}};
projectAgentToolCompleted(ctx, {{
  seq: 9,
  data: {{
    toolCallId: "shared",
    name: "read_file",
    result: {{ok: true, path: "README.md"}},
    outcome: "succeeded",
  }},
}});
process.stdout.write(JSON.stringify({{
  runAType: runACall.meta.agentEventType || "",
  runBType: runBCall.meta.agentEventType || "",
  selectedRunId: selectedCall?.meta?.agentRunId || "",
  result: ctx.messages.at(-1),
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
        result = json.loads(completed.stdout)
        self.assertEqual(result["runAType"], "")
        self.assertEqual(result["runBType"], "")
        self.assertEqual(result["selectedRunId"], "run-b")
        self.assertEqual(result["result"]["meta"]["agentRunId"], "run-b")
        self.assertEqual(result["result"]["meta"]["toolCallId"], "shared")
        self.assertEqual(result["result"]["meta"]["outcome"], "succeeded")

    def test_stream_cleanup_keeps_active_context_message_array_identity(self):
        helper_start = APP_SOURCE.index("function removeKeyFallbackMessages(messages)")
        helper_end = APP_SOURCE.index("async function waitForModelRetry", helper_start)
        helper = APP_SOURCE[helper_start:helper_end]
        script = f"""
{helper}
const assistant = {{ role: "assistant", content: "partial" }};
const messages = [
  {{ role: "assistant", content: "retry", meta: {{ kind: "key-fallback" }} }},
  assistant,
];
const result = removeKeyFallbackMessages(messages);
process.stdout.write(JSON.stringify({{
  sameArray: result === messages,
  length: messages.length,
  keepsAssistant: messages[0] === assistant,
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
        self.assertEqual(json.loads(completed.stdout), {
            "sameArray": True,
            "length": 1,
            "keepsAssistant": True,
        })

        attempt_start = APP_SOURCE.index("async function _callModelOnceAttempt")
        attempt_end = APP_SOURCE.index("function _safeMd", attempt_start)
        attempt = APP_SOURCE[attempt_start:attempt_end]
        self.assertEqual(attempt.count("removeKeyFallbackMessages(_streamMsgs);"), 2)
        self.assertNotIn("_streamMsgs = _streamMsgs.filter", attempt)

    def test_server_loop_clears_only_after_terminal_snapshot(self):
        start = APP_SOURCE.index("async function runServerAgentLoop(ctx)")
        end = APP_SOURCE.index("async function executeRunContext(ctx)", start)
        loop = APP_SOURCE[start:end]
        snapshot_position = loop.index("snapshot = await agentRuntime.watchAgentRun")
        cancelled_position = loop.index('if (snapshot.status === "cancelled") {')
        clear_position = loop.index("clearObservedAgentRun(ctx);", cancelled_position)
        abort_position = loop.index('throw new DOMException("Aborted", "AbortError");', cancelled_position)
        self.assertLess(snapshot_position, cancelled_position)
        self.assertLess(cancelled_position, clear_position)
        self.assertLess(clear_position, abort_position)


if __name__ == "__main__":
    unittest.main()
