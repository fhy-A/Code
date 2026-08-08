"""P0 stability regression tests.

Run: python -m pytest tests/test_p0_stability.py -v
"""

import io
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
PERMISSIONS_SOURCE = (ROOT / "src" / "agent" / "permissions.js").read_text(encoding="utf-8")
PERSISTENCE_SOURCE = (ROOT / "src" / "services" / "persistence.js").read_text(encoding="utf-8")
SESSIONS_SOURCE = (ROOT / "src" / "features" / "sessions.js").read_text(encoding="utf-8")
MESSAGES_SOURCE = (ROOT / "src" / "ui" / "messages.js").read_text(encoding="utf-8")
TIMELINE_SOURCE = (ROOT / "src" / "ui" / "timeline.js").read_text(encoding="utf-8")
I18N_SOURCE = (ROOT / "src" / "core" / "i18n.js").read_text(encoding="utf-8")


class _ProxyStreamingResponse:
    status = 200
    headers = {"Content-Type": "text/event-stream; charset=utf-8"}

    def __init__(self, lines=(), error=None):
        self._lines = iter(lines)
        self._error = error

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def readline(self):
        if self._error is not None:
            error, self._error = self._error, None
            raise error
        return next(self._lines, b"")


class TestStreamingProxyFrames(unittest.TestCase):
    def _run_proxy(self, response):
        body = json.dumps({"stream": True}).encode("utf-8")
        handler = object.__new__(server_mod.CodeHandler)
        handler.headers = {
            "Content-Length": str(len(body)),
            "X-Base-URL": "http://upstream.test",
        }
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        handler.send_response = mock.Mock()
        handler.send_header = mock.Mock()
        handler.end_headers = mock.Mock()

        with mock.patch.object(server_mod.request, "urlopen", return_value=response):
            handler.proxy("POST", "/v1/chat/completions")

        handler.send_response.assert_called_once_with(200)
        return handler.wfile.getvalue()

    def test_streaming_proxy_passes_upstream_frames_verbatim(self):
        output = self._run_proxy(_ProxyStreamingResponse(lines=[
            b'data: {"choices":[]}\n\n',
            b"data: [DONE]\n\n",
        ]))
        self.assertEqual(
            output,
            b'data: {"choices":[]}\n\ndata: [DONE]\n\n',
        )

    def test_streaming_proxy_terminates_error_frame_after_headers(self):
        output = self._run_proxy(_ProxyStreamingResponse(
            error=RuntimeError("upstream broke"),
        ))
        self.assertEqual(output, b"data: [ERROR] upstream broke\n\n")


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
            "SSE_BACKLOG_FRAMES_PER_PAINT = 48",
            "expandSseDataForProjection",
            "Array.from(String(text || \"\"))",
        ):
            self.assertIn(expected, RUNTIME_SOURCE)
        self.assertIn("if (delta.tool_calls || delta.function_call) return [value]", RUNTIME_SOURCE)
        self.assertIn("if (!isLast) delete projectedFrame.usage", RUNTIME_SOURCE)

    def test_server_owned_model_attaches_before_checkpoint_persistence(self):
        start = APP_SOURCE.index("async function attachAgentRuntimeProjection")
        end = APP_SOURCE.index("function projectAgentModelCompleted", start)
        projection = APP_SOURCE[start:end]
        attach = projection.index("const streamPromise = _callModelOnceAttempt")
        checkpoint = projection.index("persistRunCheckpoint(ctx, \"running\", \"model\"")
        self.assertLess(attach, checkpoint)
        self.assertNotIn("await persistRunCheckpoint", projection[:attach])

        attempt_start = APP_SOURCE.index("async function _callModelOnceAttempt")
        attempt_end = APP_SOURCE.index("function _safeMd", attempt_start)
        attempt = APP_SOURCE[attempt_start:attempt_end]
        self.assertIn("useRuntimeBridge && attachedRuntimeRunId", attempt)
        self.assertIn("payload: {}", attempt)
        self.assertIn('"poll-started": "pollStartedAt"', attempt)
        self.assertIn('"first-delta": "firstDeltaAt"', attempt)
        self.assertIn("streamDiagnostics", RUNTIME_SOURCE)
        self.assertIn("latestStreamDiagnostic", RUNTIME_SOURCE)

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
            "function projectAgentContextCompaction(ctx, event, status)",
            'eventType === "model_recovery"',
            'eventType === "context_compaction_started"',
            'eventType === "context_compaction_completed"',
            'eventType === "context_compaction_failed"',
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

    def test_init_starts_recovery_before_model_catalog_refresh(self):
        init_pos = APP_SOURCE.index("async function init()")
        platform_sync_pos = APP_SOURCE.index(
            "const platformSync = await platformSyncPromise;",
            init_pos,
        )
        auth_check_pos = APP_SOURCE.index("if (platformSync?.authExpired)", platform_sync_pos)
        recovery_pos = APP_SOURCE.index("sessionStartup.startRecovery();", auth_check_pos)
        models_pos = APP_SOURCE.index("await refreshModels();", recovery_pos)
        self.assertLess(platform_sync_pos, auth_check_pos)
        self.assertLess(auth_check_pos, recovery_pos)
        self.assertLess(recovery_pos, models_pos)
        self.assertEqual(APP_SOURCE.count("sessionStartup.startRecovery();"), 1)
        startup_start = SESSIONS_SOURCE.index("function createSessionStartup(")
        coordination_start = SESSIONS_SOURCE.index("function startRecovery()", startup_start)
        coordination = SESSIONS_SOURCE[coordination_start:]
        runs_pos = coordination.index("recovery.resumePersistedRuns()")
        queue_resume_pos = coordination.index("recovery.resumePersistedQueuedMessages()")
        background_pos = coordination.index("recovery.resumePersistedBackgroundRuns()")
        self.assertGreater(queue_resume_pos, runs_pos)
        self.assertGreater(background_pos, runs_pos)

    def test_init_restores_saved_model_before_platform_sync_and_validates_availability(self):
        cache_restore = "const cachedModelCatalog = hasEnabledKey ? restoreCachedModelCatalog() : [];"
        restore = 'setSelectedModel(localStorage.getItem("code-model") || "");'
        cache_pos = APP_SOURCE.index(cache_restore)
        restore_pos = APP_SOURCE.index(restore)
        sync_pos = APP_SOURCE.index("const platformSyncPromise = syncPlatformKeysSilently();")
        self.assertLess(cache_pos, restore_pos)
        self.assertLess(restore_pos, sync_pos)

        refresh_start = APP_SOURCE.index("async function refreshModels()")
        refresh_end = APP_SOURCE.index("function appendSystemError", refresh_start)
        refresh_source = APP_SOURCE[refresh_start:refresh_end]
        self.assertIn("if (successCount === 0)", refresh_source)
        self.assertIn('"modelCatalogRefreshFailedCached"', refresh_source)
        self.assertIn('writeModelCatalogCache(models, baseUrl)', refresh_source)
        self.assertIn('if (savedModel && models.includes(savedModel))', refresh_source)
        self.assertIn('setSelectedModel("");', refresh_source)
        self.assertIn('localStorage.removeItem("code-model");', refresh_source)

        best_key_start = APP_SOURCE.index("function getBestKey(model)")
        best_key_end = APP_SOURCE.index("function getFallbackKeys(model)", best_key_start)
        best_key_source = APP_SOURCE[best_key_start:best_key_end]
        self.assertIn("mappedKey && keys.includes(mappedKey)", best_key_source)

    def test_server_agent_checkpoint_survives_reload(self):
        for expected in (
            'executionOwner: String(',
            'agentRunId: String(',
            'agentEventCursor: Number(',
            'runState: getSessionRunState(sid)',
            'persistMessages: ctx.executionOwner === "server-agent"',
            'ctx.executionOwner = runState.executionOwner',
            'ctx.agentRunId = String(runState.agentRunId',
            'await executeRunContext(ctx)',
        ):
            self.assertIn(expected, APP_SOURCE)
        cache_start = APP_SOURCE.index("function cacheActiveSessionState()")
        cache_end = APP_SOURCE.index("function isSessionStreaming(", cache_start)
        cache_source = APP_SOURCE[cache_start:cache_end]
        self.assertIn(
            """saveSessionState(
      prevId,
      msgs,
      state.stats,
      els.sessionTitle.value.trim() || "Untitled",
      { persistMessages: true },
    )""",
            cache_source,
        )
        self.assertNotIn("apiJson(`/api/sessions/", cache_source)

        save_start = APP_SOURCE.index("async function saveSessionState(")
        save_end = APP_SOURCE.index("async function saveCurrentSession()", save_start)
        save_source = APP_SOURCE[save_start:save_end]
        self.assertIn("const payload = buildSessionSavePayload({", save_source)
        self.assertIn("runState: getSessionRunState(sessionId)", save_source)
        self.assertIn("messages,", save_source)

        payload_start = PERSISTENCE_SOURCE.index("function buildSessionSavePayload(")
        payload_end = PERSISTENCE_SOURCE.index("function createSessionPersistence(", payload_start)
        payload_source = PERSISTENCE_SOURCE[payload_start:payload_end]
        self.assertIn("runState: { ...(options.runState || {}) }", payload_source)
        self.assertIn("payload.messages = serializeSessionMessages(", payload_source)
        self.assertIn("options.messages,", payload_source)
        self.assertIn("if (options.persistMessages === true)", PERSISTENCE_SOURCE)

    def test_all_permission_profiles_have_single_server_execution_owner(self):
        self.assertIn('read: Object.freeze([', PERMISSIONS_SOURCE)
        self.assertIn('"check_skill_dependencies"', PERMISSIONS_SOURCE)
        self.assertIn(
            'return SERVER_EXECUTION_PROFILES.includes(permissionProfile) ? "server-agent" : "browser"',
            PERMISSIONS_SOURCE,
        )
        self.assertIn("executionOwner: executionOwnerForPermissionProfile(permissionProfile)", APP_SOURCE)
        self.assertIn("ctx.executionOwner = runState.executionOwner || executionOwnerForPermissionProfile(ctx.permissionProfile)", APP_SOURCE)
        self.assertIn('if (!isServerOwnedRun(ctx)) throw new Error(LEGACY_BROWSER_RUN_ERROR)', APP_SOURCE)
        self.assertIn('return runServerAgentLoop(ctx)', APP_SOURCE)
        self.assertIn('const streamPromise = _callModelOnceAttempt(assistantIndex, true, ctx)', APP_SOURCE)
        self.assertIn('await streamPromise', APP_SOURCE)
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

    def test_refresh_restores_monotonic_elapsed_timer_with_short_lived_bridge(self):
        recovery_start = APP_SOURCE.index("async function resumePersistedSessionRun(summary)")
        recovery_end = APP_SOURCE.index("async function resumePersistedRuns()", recovery_start)
        recovery = APP_SOURCE[recovery_start:recovery_end]
        presentation_index = recovery.index(
            "const presentationElapsedMs = activeRunElapsedMs"
        )
        elapsed_index = recovery.index("ctx.run.taskElapsedBaseMs = Math.max(")
        resume_index = recovery.index("ctx.run.taskElapsedResumedAt = resumedAt")
        streaming_index = recovery.index("setStreaming(true, summary.id)")

        self.assertLess(presentation_index, elapsed_index)
        self.assertLess(elapsed_index, streaming_index)
        self.assertLess(resume_index, streaming_index)
        self.assertIn("persistedRunElapsedMs(latestRunState, resumedAt)", recovery)
        self.assertIn("ctx.taskStartedAt = taskStartedAt", recovery)
        self.assertIn("ctx.run.taskStartTime = taskStartedAt", recovery)
        self.assertIn("ctx.run.responseStartTime = resumedAt", recovery)
        self.assertNotIn("ctx.run.responseStartTime = originalStartedAt", recovery)
        self.assertIn("elapsedMs: activeRunElapsedMs(timingRun, checkpointNow)", APP_SOURCE)
        self.assertIn("const ACTIVE_RUN_TIMER_MAX_AGE_MS = 30000", APP_SOURCE)
        self.assertIn("checkpoint.elapsedMs + Math.max(0, now - checkpoint.savedAt)", APP_SOURCE)
        self.assertIn("persistActiveRunTimerCheckpoint(sid);", APP_SOURCE)
        self.assertIn("clearActiveRunTimerCheckpoint(sessionId);", APP_SOURCE)

    def test_server_agent_cancellation_covers_parent_and_child_runs(self):
        cancel_start = APP_SOURCE.index("function cancelSessionRun(run)")
        cancel_end = APP_SOURCE.index("function backgroundActiveForSession", cancel_start)
        cancel = APP_SOURCE[cancel_start:cancel_end]
        self.assertIn("cancelAgentRun?.(agentRunId)", cancel)
        self.assertIn("cancelRun(runtimeRunId)", cancel)
        self.assertIn("if (!run || run.cancelRequested) return;", cancel)
        self.assertNotIn('run.agentRunId = ""', cancel)
        server_cancel_start = cancel.index("if (agentRunId) {")
        legacy_cancel_start = cancel.index("const runtimeRunId", server_cancel_start)
        server_cancel = cancel[server_cancel_start:legacy_cancel_start]
        self.assertIn("run.cancelRequested = true;", server_cancel)
        self.assertTrue(server_cancel.rstrip().endswith("return;\n  }"))
        self.assertNotIn("run.abortController.abort()", server_cancel)

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
        clear_end = APP_SOURCE.index("function resetRenderCache", clear_start)
        clear_checkpoint = APP_SOURCE[clear_start:clear_end]
        finalize_index = clear_checkpoint.index("finalizeRunTiming(ctx.sessionId)")
        save_index = clear_checkpoint.index("await saveSessionState(")

        self.assertLess(finalize_index, save_index)
        self.assertIn(
            """await saveSessionState(
      ctx.sessionId,
      msgs,
      ctx.stats || getSessionStats(ctx.sessionId),
      sessionTitle || "Untitled",
      { persistMessages: true },
    )""",
            clear_checkpoint,
        )

        save_start = APP_SOURCE.index("async function saveSessionState(")
        save_end = APP_SOURCE.index("async function saveCurrentSession()", save_start)
        save_source = APP_SOURCE[save_start:save_end]
        self.assertIn("const payload = buildSessionSavePayload({", save_source)
        self.assertIn("messages,", save_source)
        self.assertIn("persistMessages: options.persistMessages === true", save_source)

        serialize_start = PERSISTENCE_SOURCE.index("function serializeSessionMessages(")
        serialize_end = PERSISTENCE_SOURCE.index("function buildSessionSavePayload(", serialize_start)
        serialize_source = PERSISTENCE_SOURCE[serialize_start:serialize_end]
        for expected in (
            "role: message.role",
            'content: message.content || ""',
            'thought: message.thought || ""',
            "meta: message.meta || {}",
            "_images: message._images || undefined",
        ):
            self.assertIn(expected, serialize_source)
        payload_start = serialize_end
        payload_end = PERSISTENCE_SOURCE.index("function createSessionPersistence(", payload_start)
        payload_source = PERSISTENCE_SOURCE[payload_start:payload_end]
        self.assertIn("payload.messages = serializeSessionMessages(", payload_source)
        self.assertIn("options.messages,", payload_source)

        timing_start = APP_SOURCE.index("function finalizeRunTiming(sessionId")
        timing_end = APP_SOURCE.index("function placeMainResultByCompletionOrder", timing_start)
        timing = APP_SOURCE[timing_start:timing_end]
        self.assertIn("lastMsg._responseTime = display", timing)
        self.assertIn("_responseTime: display", timing)

    def test_failed_elapsed_is_finalized_after_checkpoint_capture_before_message_persistence(self):
        persist_start = APP_SOURCE.index("async function persistRunCheckpoint(")
        persist_end = APP_SOURCE.index("async function clearRunCheckpoint(ctx)", persist_start)
        persist_source = APP_SOURCE[persist_start:persist_end]
        checkpoint_index = persist_source.index(
            "const checkpoint = makeRunCheckpoint(ctx, status, phase, extra)"
        )
        run_state_index = persist_source.index(
            "setSessionRunState(ctx.sessionId, checkpoint)"
        )
        finalize_index = persist_source.index(
            "finalizeRunTiming(ctx.sessionId, options.finalizeTimingTarget)"
        )
        save_index = persist_source.index("await saveSessionState(")

        self.assertEqual(
            [checkpoint_index, run_state_index, finalize_index, save_index],
            sorted([checkpoint_index, run_state_index, finalize_index, save_index]),
        )
        self.assertIn("if (options.finalizeTimingTarget)", persist_source)
        self.assertIn(
            "persistMessages: ctx.executionOwner === \"server-agent\"",
            persist_source,
        )

        failure_start = APP_SOURCE.index("  if (loopError) {")
        failure_end = APP_SOURCE.index("  } else {\n    await clearRunCheckpoint", failure_start)
        failure_source = APP_SOURCE[failure_start:failure_end]
        self.assertIn("let errorRecoveryAssistant = null", failure_source)
        self.assertIn("errorRecoveryAssistant = {", failure_source)
        self.assertIn("ctx.messages.push(errorRecoveryAssistant)", failure_source)
        self.assertIn(
            "finalizeTimingTarget: errorRecoveryAssistant",
            failure_source,
        )
        self.assertLess(
            failure_source.index("const status = isAbort ? \"paused\" : \"failed\""),
            failure_source.index("errorRecoveryAssistant = {"),
        )
        self.assertLess(
            failure_source.index("errorRecoveryAssistant = {"),
            failure_source.index("await persistRunCheckpoint(ctx, status"),
        )
        self.assertLess(
            failure_source.index("await persistRunCheckpoint(ctx, status"),
            APP_SOURCE.index("if (ownsActiveRunContext(ctx)) setStreaming(false", failure_start)
            - failure_start,
        )

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
