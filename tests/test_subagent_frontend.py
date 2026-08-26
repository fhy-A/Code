import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class TestSubAgentFrontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "app.js").read_text(encoding="utf-8")
        cls.state_source = (ROOT / "src" / "core" / "state.js").read_text(encoding="utf-8")
        cls.persistence_source = (ROOT / "src" / "services" / "persistence.js").read_text(encoding="utf-8")
        cls.i18n_source = (ROOT / "src" / "core" / "i18n.js").read_text(encoding="utf-8")
        cls.messages_source = (ROOT / "src" / "ui" / "messages.js").read_text(encoding="utf-8")
        cls.model_request_source = (ROOT / "src" / "agent" / "model-request.js").read_text(encoding="utf-8")
        cls.permissions_source = (ROOT / "src" / "agent" / "permissions.js").read_text(encoding="utf-8")
        cls.subagents_source = (ROOT / "src" / "agent" / "subagents.js").read_text(encoding="utf-8")
        cls.compaction_source = (ROOT / "src" / "agent" / "compaction.js").read_text(encoding="utf-8")

    def test_subagent_system_message_stays_system(self):
        self.assertIn('if (message.role === "system")', self.model_request_source)
        self.assertIn(
            'return { role: "system", content: getMessageText(message) };',
            self.model_request_source,
        )

    def test_background_agent_builds_private_prompt_before_server_dispatch(self):
        self.assertIn('const subCtx = createSubContext(parentCtx, job.taskPrompt);', self.source)
        self.assertIn('function createSubAgentContext(', self.subagents_source)
        self.assertIn('{ role: "system", content: subSystem }', self.subagents_source)
        self.assertIn('{ role: "user", content: taskPrompt }', self.subagents_source)
        self.assertIn(
            'const prepared = await buildModelRequestPayload(subCtx, true, serverTools);',
            self.source,
        )

    def test_subagent_cannot_delegate_again(self):
        self.assertIn(
            'Object.freeze(["task", "request_user_input"])',
            self.subagents_source,
        )
        self.assertIn('禁止再次委派子 Agent', self.subagents_source)

    def test_main_agent_receives_explicit_delegation_rules(self):
        self.assertIn('const SUBAGENT_DELEGATION_RULES = `## 子 Agent 委派规则', self.source)
        self.assertIn('if (allowedToolNames.has("task"))', self.source)
        self.assertIn('parts.push(SUBAGENT_DELEGATION_RULES);', self.source)
        self.assertIn('存在两个及以上互不依赖的工作流', self.source)
        self.assertIn('不要把整个原始任务不加拆分地转交给单个子 Agent', self.source)
        self.assertIn('仅在并行收益明显高于额外成本时委派', self.source)

    def test_legacy_browser_agent_orchestration_is_removed(self):
        for obsolete in (
            'async function runAgentLoop(',
            'async function executeToolWithDelegation(',
            'async function executeToolCall(',
            'async function mapWithConcurrency(',
            'function mergeDelegatedUsage(',
            'function isToolAllowed(',
            'function shouldAskBeforeTool(',
            'function finishLocalAuthorizationRequest(',
            'function requestAuthorization(',
            'messageQueue:',
        ):
            self.assertNotIn(obsolete, self.source)
        resolve_start = self.source.index("function resolveAuthorization(")
        resolve_end = self.source.index("function bindAuthorizationPanel()", resolve_start)
        self.assertNotIn("if (!item.serverAgent)", self.source[resolve_start:resolve_end])

    def test_foreground_and_background_agents_use_durable_server_runs(self):
        self.assertIn('return runServerAgentLoop(ctx);', self.source)
        self.assertIn('async function runBackgroundSubAgentJob(job)', self.source)
        self.assertGreaterEqual(self.source.count('agentRuntime.createAgentRun'), 2)
        self.assertGreaterEqual(self.source.count('agentRuntime.watchAgentRun'), 2)

    def test_plan_mode_can_delegate_without_mutation_tools(self):
        plan_start = self.permissions_source.index("plan: Object.freeze([")
        plan_end = self.permissions_source.index("accept: Object.freeze([", plan_start)
        plan_policy = self.permissions_source[plan_start:plan_end]
        for allowed in ('"propose_edit"', '"task"', '"use_skill"'):
            self.assertIn(allowed, plan_policy)
        for mutation in ('"run_command"', '"write_file"', '"delete_file"'):
            self.assertNotIn(mutation, plan_policy)
        self.assertIn('SUBAGENT_DISABLED_TOOL_NAMES.includes', self.subagents_source)

    def test_authorization_panel_groups_main_and_subagents(self):
        self.assertIn('return { key: "main", label: t("mainAgentLabel") };', self.source)
        self.assertIn('function groupAuthorizations(items)', self.permissions_source)
        self.assertNotIn('function groupAuthorizations(items)', self.source)
        self.assertIn('data-auth-group=', self.source)
        self.assertIn('data-auth-action="approve"', self.source)
        self.assertIn('data-auth-action="reject-all"', self.source)

    def test_parallel_subagent_usage_uses_private_ledgers(self):
        self.assertIn('if (!ctx?.isSubAgent) setSessionStats(sessionId, stats);', self.source)
        self.assertIn('mergeBackgroundUsage(job.sessionId, sub.usage);', self.source)
        self.assertNotIn('mergeBackgroundUsage(sessionId, subCtx.stats);', self.source)

    def test_background_result_keeps_its_own_usage(self):
        self.assertIn('meta._usage = usage', self.subagents_source)
        self.assertIn('meta._usageScope = "task"', self.subagents_source)
        self.assertIn('usage: sub.usage', self.source)
        self.assertIn('includeUsage: true', self.source)

    def test_subagent_module_stops_at_pure_result_projection_boundary(self):
        for function_name in (
            "buildBackgroundResultMessage",
            "hasBackgroundResult",
        ):
            self.assertIn(f"function {function_name}(", self.subagents_source)
            self.assertNotIn(f"function {function_name}(", self.source)
        for runtime_function in (
            "createBackgroundServerContext",
            "runBackgroundSubAgentJob",
            "pumpBackgroundDispatcher",
            "dispatchBackgroundSubAgent",
            "restoreBackgroundJobsForSession",
            "resumePersistedBackgroundRuns",
        ):
            self.assertIn(f"function {runtime_function}(", self.source)
            self.assertNotIn(f"function {runtime_function}(", self.subagents_source)
        for forbidden in (
            "agentRuntime",
            "AbortController",
            "new Promise",
            "appendSessionMessages",
            "saveSessionState",
            "requestServerAgentAuthorization",
        ):
            self.assertNotIn(forbidden, self.subagents_source)

    def test_background_elapsed_time_survives_refresh(self):
        self.assertIn("startedAt: Number(source.startedAt || 0)", self.subagents_source)
        self.assertIn("queuedAt: source.queuedAt || fallbackQueuedAt", self.subagents_source)
        self.assertIn("buildRestoredBackgroundJobData(checkpoint, {", self.source)
        self.assertIn('if (status === "running" && !Number(job.startedAt || 0))', self.source)
        self.assertIn("const submittedAt = Number(job?.queuedAt || job?.startedAt || finishedAt)", self.subagents_source)
        self.assertIn('const normalizedResponseTime = String(responseTime || "").trim()', self.subagents_source)
        self.assertEqual(self.subagents_source.count("_responseTime: normalizedResponseTime"), 2)
        self.assertGreaterEqual(self.source.count("responseTime: backgroundJobElapsed(job)"), 2)

    def test_visible_timing_starts_when_each_message_is_submitted(self):
        self.assertIn("ctx.taskStartedAt = submittedAt", self.source)
        self.assertIn("run.taskStartTime = submittedAt", self.source)
        self.assertGreaterEqual(
            self.source.count("_time: new Date(submittedAt).toISOString()"),
            2,
        )
        self.assertIn("queuedAt: submittedAt", self.source)
        self.assertIn("new Date(Number(ctx.taskStartedAt || Date.now())).toISOString()", self.source)

    def test_main_timing_never_attaches_to_background_result(self):
        self.assertIn(
            'message?.role === "assistant" && !isDetachedFromMainContext(message)',
            self.source,
        )

    def test_background_result_keeps_parent_task_ordering_key(self):
        self.assertIn("parentTaskStartedAt: Number(job.parentTaskStartedAt || 0)", self.source)
        self.assertIn("backgroundDispatch: { id, status: \"pending\", agentRunId: \"\", parentTaskStartedAt }", self.source)

    def test_background_answer_uses_clickable_reply_reference_without_prompt_prefix(self):
        self.assertIn("function renderBackgroundReplyReference(msg)", self.messages_source)
        self.assertIn("data-background-reply-id=", self.messages_source)
        self.assertIn("data-background-message-id=", self.messages_source)
        self.assertIn('target.scrollIntoView({ behavior: "smooth", block: "center" })', self.source)
        self.assertNotIn('`**后台处理**：${job.userText.slice(0, 80)}', self.source)

    def test_main_and_background_results_follow_completion_order(self):
        self.assertIn("function placeMainResultByCompletionOrder(messages, mainMessage, taskStartedAt)", self.source)
        self.assertIn('message.meta?.kind === "background-subagent"', self.source)
        self.assertIn("messages.splice(lastCompletedBackground, 0, mainMessage)", self.source)

    def test_background_dispatch_uses_bounded_scheduler(self):
        self.assertIn('globalLimit: 3', self.state_source)
        self.assertIn('perSessionLimit: 2', self.state_source)
        self.assertIn('function pumpBackgroundDispatcher()', self.source)
        self.assertIn('backgroundActiveForSession(candidate.sessionId) < dispatcher.perSessionLimit', self.source)

    def test_background_dispatch_has_visible_lifecycle_and_timeout(self):
        self.assertIn('backgroundDispatch: { id, status: "pending", agentRunId: "", parentTaskStartedAt }', self.source)
        self.assertIn('updateBackgroundJob(job, "running")', self.source)
        self.assertIn('const BACKGROUND_JOB_TIMEOUT_MS = 10 * 60 * 1000;', self.subagents_source)
        self.assertIn('后台处理中', self.i18n_source)

    def test_background_dispatch_uses_durable_server_agent(self):
        background_start = self.source.index("async function runBackgroundSubAgentJob(job)")
        background_end = self.source.index("function pumpBackgroundDispatcher()", background_start)
        background = self.source[background_start:background_end]
        self.assertIn("agentRuntime.createAgentRun", background)
        self.assertIn("clientRequestId: job.clientRequestId || job.id", background)
        self.assertIn("agentRuntime.watchAgentRun", background)
        self.assertIn("agentRuntime.resumeAgentRun", background)
        self.assertNotIn("runAgentLoop(", background)

    def test_background_run_checkpoint_survives_main_completion_and_reload(self):
        self.assertIn("function getBackgroundRunCheckpoints(sessionId)", self.state_source)
        self.assertIn("backgroundRuns.push({ ...checkpoint })", self.state_source)
        clear_start = self.source.index("async function clearRunCheckpoint(ctx)")
        clear_end = self.source.index("function resetRenderCache", clear_start)
        clear = self.source[clear_start:clear_end]
        self.assertIn(
            """...(backgroundRuns.length ? { backgroundRuns: backgroundRuns.map((item) => ({ ...item })) } : {}),""",
            clear,
        )
        set_run_state_index = clear.index(
            "setSessionRunState(ctx.sessionId, clearedRunState)"
        )
        save_index = clear.index("await saveSessionState(")
        self.assertLess(set_run_state_index, save_index)
        self.assertIn(
            """await saveSessionState(
      ctx.sessionId,
      msgs,
      getSessionStats(ctx.sessionId),
      sessionTitle || "Untitled",
      { persistMessages: true },
    ).catch(() => null)""",
            clear,
        )
        self.assertIn("async function resumePersistedBackgroundRuns()", self.source)
        self.assertIn("restoreBackgroundJobsForSession(summary)", self.source)
        restore_start = self.source.index("async function restoreBackgroundJobsForSession(summary)")
        restore_end = self.source.index("async function resumePersistedBackgroundRuns()", restore_start)
        restore = self.source[restore_start:restore_end]
        self.assertIn("buildRestoredBackgroundJobData(checkpoint, {", restore)
        self.assertIn("const completion = new Promise", restore)
        self.assertIn("state._backgroundDispatcher.jobs.push({", restore)
        self.assertIn("removeBackgroundRunCheckpoint(summary.id, checkpoint.id)", restore)
        self.assertIn("await saveSessionState(", restore)
        self.assertIn("parentCtx: null", restore)
        self.assertIn("userMessage,", restore)
        self.assertIn("completion,", restore)
        self.assertIn("resolve,", restore)

    def test_background_server_agent_cannot_delegate_or_open_questionnaire(self):
        self.assertIn('allowedToolNames.delete("task")', self.source)
        self.assertIn('allowedToolNames.delete("request_user_input")', self.source)
        self.assertIn('if (snapshot.status === "waiting_user_input")', self.source)
        self.assertIn('throw new Error("后台任务不能发起交互问卷")', self.source)

    def test_background_authorization_does_not_replace_main_run_checkpoint(self):
        self.assertIn("detachedBackground: Boolean(ctx.isDetachedBackground)", self.source)
        self.assertIn("if (item.detachedBackground)", self.source)
        self.assertIn("Failed to persist background authorization result", self.source)
        self.assertIn("projection.meta.detachedFromMain = true", self.source)

    def test_background_messages_are_detached_from_main_model_context(self):
        self.assertIn('function isDetachedFromMainContext(msg)', self.source)
        self.assertIn('msg.meta?.detachedFromMain', self.source)
        self.assertIn('function getModelContextMessages(messages, isDetachedMessage = null)', self.compaction_source)
        self.assertIn('.filter((message) => !shouldDetach(message))', self.compaction_source)
        self.assertIn('getModelContextMessages(streamMessages, isDetachedFromMainContext)', self.source)
        self.assertGreaterEqual(self.source.count('detachedFromMain: true'), 3)

    def test_legacy_background_notifications_stay_out_of_model_context(self):
        self.assertIn(
            'msg.meta?.kind === "background-subagent-notify"',
            self.source,
        )

    def test_background_edit_projection_is_detached_from_parent_context(self):
        self.assertIn('if (ctx.isDetachedBackground)', self.source)
        self.assertIn('projection.meta.detachedFromMain = true;', self.source)
        self.assertIn('detachedFromMain: true', self.source)

    def test_background_dispatch_owns_abort_controller(self):
        self.assertIn('abortController: new AbortController()', self.source)
        self.assertIn('if (!ctx?.isSubAgent && sessionId === state.sessionId)', self.source)

    def test_session_saves_are_serialized(self):
        self.assertIn('_sessionSaveChains: {}', self.state_source)
        self.assertIn('const previous = saveChains[sessionId] || Promise.resolve();', self.persistence_source)
        self.assertIn('saveChains[sessionId] = savePromise;', self.persistence_source)

    def test_active_subagent_does_not_block_main_session_updates(self):
        self.assertNotIn('_subAgentDepth', self.source)


if __name__ == "__main__":
    unittest.main()
