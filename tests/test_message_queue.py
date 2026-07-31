import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
APP_SOURCE = (ROOT / "app.js").read_text(encoding="utf-8")
SESSIONS_SOURCE = (ROOT / "src" / "features" / "sessions.js").read_text(encoding="utf-8")
MESSAGES_SOURCE = (ROOT / "src" / "ui" / "messages.js").read_text(encoding="utf-8")
I18N_SOURCE = (ROOT / "src" / "core" / "i18n.js").read_text(encoding="utf-8")
SUBAGENTS_SOURCE = (ROOT / "src" / "agent" / "subagents.js").read_text(encoding="utf-8")
COMPACTION_SOURCE = (ROOT / "src" / "agent" / "compaction.js").read_text(encoding="utf-8")


class TestRunningMessageQueue(unittest.TestCase):
    def test_ordinary_running_message_uses_fifo_queue(self):
        submit_start = APP_SOURCE.index('els.chatForm.addEventListener("submit"')
        submit_end = APP_SOURCE.index('els.newChat.addEventListener', submit_start)
        submit = APP_SOURCE[submit_start:submit_end]
        self.assertIn("enqueueSessionMessage(sessionId, taskText, imgs)", submit)
        self.assertIn("if (parallelTask !== null)", submit)
        self.assertIn("dispatchBackgroundSubAgent(sessionId, taskText, imgs)", submit)

    def test_parallel_intent_requires_explicit_command(self):
        self.assertIn("function parseParallelCommand(text)", SUBAGENTS_SOURCE)
        self.assertIn(r"/^\/parallel(?:\s+([\s\S]*))?$/i", SUBAGENTS_SOURCE)
        self.assertNotIn("function parseParallelCommand(text)", APP_SOURCE)
        self.assertIn("} = window.Code.agent.subagents;", APP_SOURCE)
        self.assertIn('{ name: "parallel", descriptionKey: "cmdParallelDesc" }', (
            ROOT / "src" / "features" / "skills-memory.js"
        ).read_text(encoding="utf-8"))
        self.assertIn("cmdParallelDesc", I18N_SOURCE)

    def test_queue_snapshots_execution_configuration_at_submission(self):
        enqueue_start = APP_SOURCE.index("async function enqueueSessionMessage(")
        enqueue_end = APP_SOURCE.index("async function cancelQueuedSessionMessage", enqueue_start)
        enqueue = APP_SOURCE[enqueue_start:enqueue_end]
        for expected in (
            "const model = getSelectedModel()",
            "const permissionProfile = getPermissionProfile()",
            'const toolPreset = els.toolPreset.value || "default"',
            "const thinkingLevel = getThinkingLevel()",
            "const temperature = Number(els.temperature.value",
            "const maxTokens = getEffectiveMaxTokens(model)",
            "permissionProfile,",
            "toolPreset,",
            "thinkingLevel,",
        ):
            self.assertIn(expected, enqueue)

    def test_pending_queue_messages_are_detached_from_model_context(self):
        self.assertIn("meta: {", APP_SOURCE)
        self.assertIn("queuedDispatch: { id, status: \"pending\", queuedAt }", APP_SOURCE)
        self.assertIn("detachedFromMain: true", APP_SOURCE)
        self.assertIn(".filter((message) => !shouldDetach(message))", COMPACTION_SOURCE)
        self.assertIn(
            "getModelContextMessages(streamMessages, isDetachedFromMainContext)",
            APP_SOURCE,
        )

    def test_queue_uses_stable_client_request_id_for_server_idempotency(self):
        self.assertIn("clientRequestId: id", APP_SOURCE)
        self.assertIn("clientRequestId: item.clientRequestId || item.id", APP_SOURCE)
        self.assertIn("clientRequestId: ctx.clientRequestId || \"\"", APP_SOURCE)
        self.assertIn("ctx.clientRequestId = String(runState.clientRequestId", APP_SOURCE)

    def test_success_atomically_removes_active_queue_item(self):
        clear_start = APP_SOURCE.index("async function clearRunCheckpoint(ctx)")
        clear_end = APP_SOURCE.index("function resetRenderCache", clear_start)
        clear = APP_SOURCE[clear_start:clear_end]
        self.assertIn('const queueItemId = String(ctx.queueItemId || "")', clear)
        self.assertIn(".filter((item) => item.id !== queueItemId)", clear)
        self.assertIn('queuedUserMessage.meta.queuedDispatch.status = "completed"', clear)
        self.assertIn("messages: serialized", clear)
        self.assertIn("runState: clearedRunState", clear)

    def test_pending_message_can_be_canceled_without_touching_active_run(self):
        cancel_start = APP_SOURCE.index("async function cancelQueuedSessionMessage")
        cancel_end = APP_SOURCE.index("function finishQueuedSessionMessage", cancel_start)
        cancel = APP_SOURCE[cancel_start:cancel_end]
        self.assertIn('item.status !== "pending"', cancel)
        self.assertIn("candidate.id !== queueItemId", cancel)
        self.assertIn("markQueuedMessageCanceled(messages, queueItemId, canceledAt)", cancel)
        self.assertIn("state._sessionRuns[sessionId]?._activeCtx?.messages", cancel)
        self.assertIn("markQueuedMessageCanceled(activeMessages, queueItemId, canceledAt)", cancel)
        self.assertNotIn("cancelSessionRun", cancel)
        self.assertNotIn("background", cancel.lower())

    def test_canceled_queue_message_is_retained_but_excluded_from_context(self):
        marker_start = APP_SOURCE.index("function markQueuedMessageCanceled")
        marker_end = APP_SOURCE.index("function updateQueuedMessageItem", marker_start)
        marker = APP_SOURCE[marker_start:marker_end]
        self.assertIn('queuedDispatch.status = "canceled"', marker)
        self.assertIn("message.meta.detachedFromMain = true", marker)
        self.assertIn("queuedMessageCanceled", I18N_SOURCE)
        self.assertIn('queued-message-status canceled', MESSAGES_SOURCE)

    def test_queue_restores_after_foreground_recovery(self):
        init_start = APP_SOURCE.index("async function init()")
        init = APP_SOURCE[init_start:]
        self.assertIn("sessionStartup.startRecovery();", init)
        startup_start = SESSIONS_SOURCE.index("function createSessionStartup(")
        coordination_start = SESSIONS_SOURCE.index("function startRecovery()", startup_start)
        coordination = SESSIONS_SOURCE[coordination_start:]
        self.assertIn("recovery.resumePersistedRuns()", coordination)
        self.assertIn(".then(() => recovery.resumePersistedQueuedMessages())", coordination)
        resume_start = APP_SOURCE.index("async function resumePersistedQueuedMessages()")
        resume_end = APP_SOURCE.index("function getBackgroundJob", resume_start)
        resume = APP_SOURCE[resume_start:resume_end]
        self.assertIn('item.status !== "running"', resume)
        self.assertIn('status: "pending"', resume)
        self.assertIn("await pumpQueuedSessionMessages(summary.id)", resume)

    def test_fifo_pump_selects_first_pending_item_and_auto_advances(self):
        pump_start = APP_SOURCE.index("async function pumpQueuedSessionMessages(")
        pump_end = APP_SOURCE.index("async function resumePersistedQueuedMessages", pump_start)
        pump = APP_SOURCE[pump_start:pump_end]
        self.assertIn('.find((candidate) => candidate.status === "pending")', pump)
        self.assertIn("state._queuedMessagePumps.has(sessionId)", pump)
        self.assertIn("if (!item.model || !getBestKey(item.model)) return false", pump)
        self.assertIn("queueMicrotask", pump)

    def test_queue_projection_has_status_and_cancel_action(self):
        self.assertIn("queued-message-status pending", MESSAGES_SOURCE)
        self.assertIn("queued-message-cancel", MESSAGES_SOURCE)
        self.assertIn("queuedTailMessages.push", MESSAGES_SOURCE)
        self.assertIn("queuedMessagePending", I18N_SOURCE)
        self.assertIn("cancelQueuedMessage", I18N_SOURCE)


if __name__ == "__main__":
    unittest.main()
