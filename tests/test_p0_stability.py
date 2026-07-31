"""P0 stability regression tests.

Run: python -m pytest tests/test_p0_stability.py -v
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server as server_mod


ROOT = Path(__file__).resolve().parent.parent
APP_SOURCE = (ROOT / "app.js").read_text(encoding="utf-8")
RUNTIME_SOURCE = (ROOT / "agent-runtime.js").read_text(encoding="utf-8")
MODEL_STREAM_SOURCE = (ROOT / "src" / "agent" / "model-stream.js").read_text(encoding="utf-8")
PERSISTENCE_SOURCE = (ROOT / "src" / "services" / "persistence.js").read_text(encoding="utf-8")
SESSIONS_SOURCE = (ROOT / "src" / "features" / "sessions.js").read_text(encoding="utf-8")
MESSAGES_SOURCE = (ROOT / "src" / "ui" / "messages.js").read_text(encoding="utf-8")
TIMELINE_SOURCE = (ROOT / "src" / "ui" / "timeline.js").read_text(encoding="utf-8")
I18N_SOURCE = (ROOT / "src" / "core" / "i18n.js").read_text(encoding="utf-8")


class TestFrontendNetworkRecovery(unittest.TestCase):
    def test_request_timeout_does_not_abort_whole_agent_run(self):
        self.assertIn("function createRequestSignal(userSignal, timeoutMs)", APP_SOURCE)
        self.assertIn("timedOut = true", APP_SOURCE)
        self.assertIn("controller.abort();", APP_SOURCE)
        self.assertIn("timedOut: () => timedOut", APP_SOURCE)
        self.assertNotIn("setTimeout(() => run.abortController.abort(), FETCH_TIMEOUT_MS)", APP_SOURCE)

    def test_runtime_poll_uses_bounded_backoff(self):
        self.assertIn(
            "const POLL_DELAYS = [500, 1000, 2000, 4000, 8000]",
            RUNTIME_SOURCE,
        )
        self.assertIn(
            "POLL_DELAYS[Math.min(failures, POLL_DELAYS.length - 1)]",
            RUNTIME_SOURCE,
        )
        self.assertIn("await sleep(delay, signal)", RUNTIME_SOURCE)

    def test_incomplete_sse_is_not_treated_as_success(self):
        self.assertIn("const reader = createSseDataReader(res.body)", APP_SOURCE)
        self.assertIn("if (done) break", APP_SOURCE)
        self.assertIn('code: "stream_interrupted"', APP_SOURCE)
        self.assertIn("Stream interrupted before completion", APP_SOURCE)

    def test_runtime_poll_reconnect_is_visible_in_active_answer(self):
        for expected in (
            "onReconnect",
            "onReconnected",
            "nextRetryAt: Date.now() + delay",
        ):
            self.assertIn(expected, RUNTIME_SOURCE)
        for expected in (
            "networkReconnectStatus",
            'source: "runtime-poll"',
            "network-reconnect-countdown",
        ):
            self.assertIn(expected, APP_SOURCE)
        self.assertIn("renderNetworkRecoveryStatus(getSessionId())", MESSAGES_SOURCE)

    def test_model_access_denial_is_not_retried_and_refreshes_capabilities(self):
        self.assertIn(
            'return { code: "model_access_denied", transient: false }',
            MODEL_STREAM_SOURCE,
        )
        self.assertNotIn('Retry once if New API transient "no access" error', APP_SOURCE)
        self.assertIn("state.modelKeysMap[model]", APP_SOURCE)
        self.assertIn('if (err.errorCode === "model_access_denied")', APP_SOURCE)
        self.assertIn("await refreshModels()", APP_SOURCE)
        self.assertIn("snapshot.errorCode || `runtime_${snapshot.status}`", RUNTIME_SOURCE)
        self.assertIn("snapshot.transient", RUNTIME_SOURCE)

    def test_large_text_sse_chunks_receive_bounded_visual_smoothing(self):
        for expected in (
            "SSE_VISUAL_CHUNK_CHARS = 48",
            "SSE_VISUAL_MAX_CHUNKS = 12",
            "SSE_BATCH_MAX_PAUSES = 8",
            "expandSseDataForProjection",
            "Array.from(String(text || \"\"))",
        ):
            self.assertIn(expected, RUNTIME_SOURCE)
        self.assertIn("if (delta.tool_calls || delta.function_call) return [value]", RUNTIME_SOURCE)
        self.assertIn("if (!isLast) delete projectedFrame.usage", RUNTIME_SOURCE)

    def test_model_wait_escalates_only_before_first_response(self):
        for expected in (
            "MODEL_RESPONSE_WAIT_NOTICE_MS = 25000",
            "MODEL_RESPONSE_SLOW_NOTICE_MS = 60000",
            '"waitingForModelResponse"',
            '"modelResponseDelayed"',
            'return t("modelResponseSlow")',
            'if (run?.hasFirstModelResponseStarted) return t("processedLabel")',
            "run.hasFirstModelResponseStarted = true",
            "run.modelWaitStartedAt = Date.now()",
            "run.modelResponseStarted = false",
            "markModelResponseStarted(run, sessionId)",
            "function projectAgentModelRecovery(ctx, event)",
            'eventType === "model_recovery"',
            'return t("modelRecovery"',
        ):
            self.assertIn(expected, APP_SOURCE)
        self.assertIn('nodes.label.textContent = getActiveRunLabel(sessionId)', APP_SOURCE)
        self.assertNotIn('document.querySelectorAll("[data-active-run-label]")', APP_SOURCE)
        self.assertIn("已提交模型，正在等待响应", I18N_SOURCE)
        self.assertIn("工具处理完成，正在等待模型继续", I18N_SOURCE)
        self.assertIn("任务总耗时", I18N_SOURCE)
        self.assertIn("模型未给出有效结果，正在自动续行", I18N_SOURCE)
        self.assertNotIn('"(empty response)"', APP_SOURCE)


class TestFrontendRefreshRecovery(unittest.TestCase):
    def test_completed_session_restore_scrolls_after_layout(self):
        self.assertIn("function scheduleMessagesScrollToBottom(sessionId = state.sessionId)", APP_SOURCE)
        self.assertIn("if (state.sessionId !== sessionId) return", APP_SOURCE)
        self.assertIn("els.messages.scrollTop = els.messages.scrollHeight", APP_SOURCE)

        navigation_start = SESSIONS_SOURCE.index("function createSessionNavigation(")
        load_start = SESSIONS_SOURCE.index("async function loadSession(sessionId)", navigation_start)
        load_end = SESSIONS_SOURCE.index("return Object.freeze({", load_start)
        load_session = SESSIONS_SOURCE[load_start:load_end]
        self.assertEqual(load_session.count("scheduleMessagesScrollToBottom("), 2)

        timeline = TIMELINE_SOURCE[
            TIMELINE_SOURCE.index("function renderTimeline()"):
            TIMELINE_SOURCE.index("return Object.freeze", TIMELINE_SOURCE.index("function renderTimeline()"))
        ]
        self.assertNotIn("scrollTop", timeline)

    def test_recovery_is_locked_per_session(self):
        self.assertIn("async function withSessionRecoveryLock(sessionId, worker)", APP_SOURCE)
        self.assertIn("navigator.locks?.request", APP_SOURCE)
        self.assertIn("code-run-recovery-lease", APP_SOURCE)

    def test_recovery_reuses_server_runtime_stream_and_guards_side_effects(self):
        self.assertIn("function prepareMessagesForRunRecovery(messages, runState)", APP_SOURCE)
        self.assertIn('runState?.phase === "model"', APP_SOURCE)
        self.assertIn("Boolean(runState?.runtimeRunId)", APP_SOURCE)
        self.assertIn("if (hasRuntimeRun || hasServerAgent) return cleaned", APP_SOURCE)
        self.assertIn("ctx._reuseRuntimeAssistant = Boolean(ctx.runtimeRunId)", APP_SOURCE)
        self.assertIn("Before repeating any write, command, network request", APP_SOURCE)
        self.assertIn('meta: { _system: true, kind: "run-recovery" }', APP_SOURCE)

    def test_recovery_restores_saved_execution_settings(self):
        for expected in (
            "ctx.model = runState.model || ctx.model",
            "ctx.temperature = Number(runState.temperature",
            "ctx.toolPreset = runState.toolPreset",
            "ctx.permissionProfile = runState.permissionProfile",
            "ctx.thinkingLevel = runState.thinkingLevel",
        ):
            self.assertIn(expected, APP_SOURCE)

    def test_init_starts_recovery_after_models_are_loaded(self):
        models_pos = APP_SOURCE.index("await refreshModels();")
        recovery_pos = APP_SOURCE.index("sessionStartup.startRecovery();", models_pos)
        self.assertGreater(recovery_pos, models_pos)
        startup_start = SESSIONS_SOURCE.index("function createSessionStartup(")
        coordination_start = SESSIONS_SOURCE.index("function startRecovery()", startup_start)
        coordination = SESSIONS_SOURCE[coordination_start:]
        runs_pos = coordination.index("recovery.resumePersistedRuns()")
        queue_resume_pos = coordination.index("recovery.resumePersistedQueuedMessages()")
        background_pos = coordination.index("recovery.resumePersistedBackgroundRuns()")
        self.assertGreater(queue_resume_pos, runs_pos)
        self.assertGreater(background_pos, runs_pos)

    def test_init_restores_saved_model_before_platform_sync_and_validates_availability(self):
        restore = 'setSelectedModel(localStorage.getItem("code-model") || "");'
        restore_pos = APP_SOURCE.index(restore)
        sync_pos = APP_SOURCE.index("const platformSyncPromise = syncPlatformKeysSilently();")
        self.assertLess(restore_pos, sync_pos)

        refresh_start = APP_SOURCE.index("async function refreshModels()")
        refresh_end = APP_SOURCE.index("function appendSystemError", refresh_start)
        refresh_source = APP_SOURCE[refresh_start:refresh_end]
        self.assertIn('if (savedModel && models.includes(savedModel))', refresh_source)
        self.assertIn('setSelectedModel("");', refresh_source)
        self.assertIn('localStorage.removeItem("code-model");', refresh_source)

    def test_server_agent_checkpoint_survives_reload(self):
        for expected in (
            'executionOwner: String(',
            'agentRunId: String(',
            'agentEventCursor: Number(',
            'runState: getSessionRunState(sid)',
            'runState: { ...getSessionRunState(prevId) }',
            'persistMessages: ctx.executionOwner === "server-agent"',
            'ctx.executionOwner = runState.executionOwner',
            'ctx.agentRunId = String(runState.agentRunId',
            'await executeRunContext(ctx)',
        ):
            self.assertIn(expected, APP_SOURCE)
        self.assertIn("if (options.persistMessages === true)", PERSISTENCE_SOURCE)

    def test_all_permission_profiles_have_single_server_execution_owner(self):
        self.assertIn('read: new Set(["request_user_input", "list_files", "read_file", "search_files", "glob_files", "check_skill_dependencies"])', APP_SOURCE)
        self.assertIn('return ["read", "plan", "accept", "bypass"].includes(permissionProfile) ? "server-agent" : "browser"', APP_SOURCE)
        self.assertIn("executionOwner: executionOwnerForPermissionProfile(permissionProfile)", APP_SOURCE)
        self.assertIn("ctx.executionOwner = runState.executionOwner || executionOwnerForPermissionProfile(ctx.permissionProfile)", APP_SOURCE)
        self.assertIn('if (!isServerOwnedRun(ctx)) throw new Error(LEGACY_BROWSER_RUN_ERROR)', APP_SOURCE)
        self.assertIn('return runServerAgentLoop(ctx)', APP_SOURCE)
        self.assertIn('await _callModelOnceAttempt(assistantIndex, true, ctx)', APP_SOURCE)
        server_projection = APP_SOURCE[
            APP_SOURCE.index("async function projectAgentModelStarted"):
            APP_SOURCE.index("function projectAgentModelCompleted")
        ]
        self.assertNotIn("callModelOnce(", server_projection)

    def test_legacy_browser_checkpoint_fails_explicitly_without_replay(self):
        recovery_start = APP_SOURCE.index("async function resumePersistedSessionRun(summary)")
        recovery_end = APP_SOURCE.index("async function resumePersistedRuns()", recovery_start)
        recovery = APP_SOURCE[recovery_start:recovery_end]
        legacy_branch_start = recovery.index('if (latestRunState.executionOwner !== "server-agent")')
        legacy_branch_end = recovery.index("const ctx = buildRecoveredRunContext", legacy_branch_start)
        legacy_branch = recovery[legacy_branch_start:legacy_branch_end]

        self.assertIn("finalizeLegacyBrowserRunMessages(session.messages)", legacy_branch)
        self.assertIn('status: "failed"', legacy_branch)
        self.assertIn('phase: "legacy-browser-retired"', legacy_branch)
        self.assertIn("lastError: LEGACY_BROWSER_RUN_ERROR", legacy_branch)
        self.assertIn("await saveSessionState", legacy_branch)
        self.assertIn("{ persistMessages: true }", legacy_branch)
        self.assertIn("return;", legacy_branch)
        self.assertNotIn("executeRunContext", legacy_branch)
        self.assertIn('kind: "legacy-browser-run-retired"', APP_SOURCE)

    def test_continue_action_cannot_reenter_legacy_browser_loop(self):
        continue_start = APP_SOURCE.index("async function continueAgentRun()")
        continue_end = APP_SOURCE.index("async function renameSession", continue_start)
        continue_action = APP_SOURCE[continue_start:continue_end]
        self.assertIn("await executeRunContext(ctx)", continue_action)
        self.assertNotIn("runAgentLoop(ctx)", continue_action)
        self.assertNotIn("async function runAgentLoop(", APP_SOURCE)
        self.assertNotIn("async function executeToolWithDelegation(", APP_SOURCE)

    def test_refresh_restores_original_task_timer_before_streaming(self):
        recovery_start = APP_SOURCE.index("async function resumePersistedSessionRun(summary)")
        recovery_end = APP_SOURCE.index("async function resumePersistedRuns()", recovery_start)
        recovery = APP_SOURCE[recovery_start:recovery_end]
        parse_index = recovery.index("const originalStartedAt = Date.parse")
        task_index = recovery.index("ctx.run.taskStartTime = originalStartedAt")
        streaming_index = recovery.index("setStreaming(true, summary.id)")

        self.assertLess(parse_index, task_index)
        self.assertLess(task_index, streaming_index)
        self.assertIn("ctx.taskStartedAt = originalStartedAt", recovery)
        self.assertIn("ctx.run.responseStartTime = originalStartedAt", recovery)

    def test_server_agent_cancellation_covers_parent_and_child_runs(self):
        cancel_start = APP_SOURCE.index("function cancelSessionRun(run)")
        cancel_end = APP_SOURCE.index("function backgroundActiveForSession", cancel_start)
        cancel = APP_SOURCE[cancel_start:cancel_end]
        self.assertIn("cancelAgentRun(agentRunId)", cancel)
        self.assertIn("cancelRun(runtimeRunId)", cancel)

    def test_durable_model_projection_always_has_completion_time(self):
        projection_start = APP_SOURCE.index("function projectAgentModelCompleted")
        projection_end = APP_SOURCE.index("function projectAgentToolStarted", projection_start)
        projection = APP_SOURCE[projection_start:projection_end]
        self.assertIn("const projectedContent = splitThoughtContent(combined)", projection)
        self.assertIn("data.completedAt || event?.createdAt", projection)
        self.assertIn("_time: completedAt", projection)
        self.assertIn("assistant._time = assistant._time || completedAt", projection)

    def test_completed_elapsed_is_persisted_before_checkpoint_clear(self):
        clear_start = APP_SOURCE.index("async function clearRunCheckpoint(ctx)")
        clear_end = APP_SOURCE.index("function isCompactSummaryMessage", clear_start)
        clear_checkpoint = APP_SOURCE[clear_start:clear_end]
        finalize_index = clear_checkpoint.index("finalizeRunTiming(ctx.sessionId)")
        serialize_index = clear_checkpoint.index("const serialized = serializeSessionMessages")

        self.assertLess(finalize_index, serialize_index)
        self.assertIn("meta: message.meta || {}", PERSISTENCE_SOURCE)

        timing_start = APP_SOURCE.index("function finalizeRunTiming(sessionId)")
        timing_end = APP_SOURCE.index("function placeMainResultByCompletionOrder", timing_start)
        timing = APP_SOURCE[timing_start:timing_end]
        self.assertIn("lastMsg._responseTime = display", timing)
        self.assertIn("_responseTime: display", timing)

    def test_missing_historical_elapsed_does_not_render_fake_zero_seconds(self):
        status_start = MESSAGES_SOURCE.index("function renderCompletedRunStatus")
        status_end = MESSAGES_SOURCE.index("function renderUserProjection", status_start)
        status = MESSAGES_SOURCE[status_start:status_end]
        response_start = MESSAGES_SOURCE.index("function renderAssistantResponseInfo")
        response_end = MESSAGES_SOURCE.index("function renderBackgroundReplyReference", response_start)
        response = MESSAGES_SOURCE[response_start:response_end]

        self.assertIn("const elapsedHtml = elapsed", status)
        self.assertIn("usageHtml && elapsedHtml", status)
        self.assertNotIn('elapsed || "0s"', response)
        self.assertIn("renderCompletedRunStatus", response)


class TestServerRunStatePersistence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.sessions_dir = Path(self.temp_dir.name)
        self.patch_sessions = mock.patch.object(server_mod, "SESSIONS_DIR", self.sessions_dir)
        self.patch_sessions.start()
        self.addCleanup(self.patch_sessions.stop)

    def make_handler(self, body):
        handler = object.__new__(server_mod.CodeHandler)
        handler.read_body_json = mock.Mock(return_value=body)
        handler.send_json = mock.Mock()
        return handler

    def test_create_summary_and_save_preserve_run_state(self):
        running = {
            "status": "waiting-network",
            "phase": "model",
            "model": "deepseek-v4-pro",
            "recoveryCount": 2,
        }
        create_handler = self.make_handler({"title": "P0", "runState": running})
        server_mod.CodeHandler.create_session(create_handler)
        created = create_handler.send_json.call_args.args[0]

        stored = json.loads(server_mod.session_path(created["id"]).read_text(encoding="utf-8"))
        self.assertEqual(stored["runState"], running)
        self.assertEqual(server_mod.session_summary(stored)["runState"], running)

        save_handler = self.make_handler({
            "title": "P0",
            "messages": [{"role": "user", "content": "continue"}],
            "stats": {"input": 3},
            "runState": {"status": "resuming", "phase": "tools"},
        })
        server_mod.CodeHandler.save_session(save_handler, created["id"])
        saved = save_handler.send_json.call_args.args[0]
        self.assertEqual(saved["runState"]["status"], "resuming")
        self.assertEqual(saved["runState"]["phase"], "tools")

    def test_ordinary_save_does_not_erase_existing_checkpoint(self):
        session_id = "stabletest01"
        server_mod.write_json(server_mod.session_path(session_id), {
            "id": session_id,
            "title": "checkpoint",
            "messages": [],
            "runState": {"status": "running", "phase": "tools"},
        })
        handler = self.make_handler({"title": "checkpoint", "messages": []})
        server_mod.CodeHandler.save_session(handler, session_id)
        saved = handler.send_json.call_args.args[0]
        self.assertEqual(saved["runState"], {"status": "running", "phase": "tools"})

    def test_session_save_persists_last_usage(self):
        initial_usage = {
            "prompt_tokens": 1250,
            "completion_tokens": 80,
            "total_tokens": 1330,
        }
        create_handler = self.make_handler({"title": "usage", "lastUsage": initial_usage})
        server_mod.CodeHandler.create_session(create_handler)
        created = create_handler.send_json.call_args.args[0]
        self.assertEqual(created["lastUsage"], initial_usage)

        updated_usage = {
            "prompt_tokens": 2400,
            "completion_tokens": 120,
            "total_tokens": 2520,
        }
        save_handler = self.make_handler({
            "title": "usage",
            "messages": [{"role": "assistant", "content": "done"}],
            "lastUsage": updated_usage,
        })
        server_mod.CodeHandler.save_session(save_handler, created["id"])

        stored = json.loads(
            server_mod.session_path(created["id"]).read_text(encoding="utf-8")
        )
        self.assertEqual(stored["lastUsage"], updated_usage)


if __name__ == "__main__":
    unittest.main()
