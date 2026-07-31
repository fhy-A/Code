"""Regression guards for the transitional frontend module split."""

import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
APP_SOURCE = (ROOT / "app.js").read_text(encoding="utf-8")
RUNTIME_SOURCE = (ROOT / "agent-runtime.js").read_text(encoding="utf-8")
STATE_SOURCE = (ROOT / "src" / "core" / "state.js").read_text(encoding="utf-8")
I18N_SOURCE = (ROOT / "src" / "core" / "i18n.js").read_text(encoding="utf-8")
PLATFORM_SOURCE = (ROOT / "src" / "core" / "platform.js").read_text(encoding="utf-8")
API_CLIENT_SOURCE = (ROOT / "src" / "services" / "api-client.js").read_text(encoding="utf-8")
SESSIONS_SOURCE = (ROOT / "src" / "features" / "sessions.js").read_text(encoding="utf-8")
SETTINGS_SOURCE = (ROOT / "src" / "features" / "settings.js").read_text(encoding="utf-8")
DIFF_SOURCE = (ROOT / "src" / "ui" / "diff.js").read_text(encoding="utf-8")
MARKDOWN_SOURCE = (ROOT / "src" / "ui" / "markdown.js").read_text(encoding="utf-8")
MESSAGES_SOURCE = (ROOT / "src" / "ui" / "messages.js").read_text(encoding="utf-8")
TIMELINE_SOURCE = (ROOT / "src" / "ui" / "timeline.js").read_text(encoding="utf-8")
PANELS_SOURCE = (ROOT / "src" / "ui" / "panels.js").read_text(encoding="utf-8")
PREVIEW_SOURCE = (ROOT / "src" / "features" / "preview.js").read_text(encoding="utf-8")
FILES_SOURCE = (ROOT / "src" / "features" / "files.js").read_text(encoding="utf-8")
SKILLS_MEMORY_SOURCE = (ROOT / "src" / "features" / "skills-memory.js").read_text(encoding="utf-8")
SESSION_IMPORT_SOURCE = (ROOT / "src" / "features" / "session-import.js").read_text(encoding="utf-8")
BRANCHES_SOURCE = (ROOT / "src" / "features" / "branches.js").read_text(encoding="utf-8")
INDEX_SOURCE = (ROOT / "index.html").read_text(encoding="utf-8")
BUILD_SOURCE = (ROOT / "build_exe.py").read_text(encoding="utf-8")
STYLE_SOURCE = (ROOT / "styles.css").read_text(encoding="utf-8")
LOGO_SOURCE = (ROOT / "assets" / "code-logo.svg").read_text(encoding="utf-8")
LOGO_EXPORT_SOURCE = (ROOT / "design" / "logo-concepts" / "export_selected_logo.py").read_text(encoding="utf-8")


class TestFrontendCoreModules(unittest.TestCase):
    def test_import_boundary_survives_compaction_and_stays_out_of_exports(self):
        self.assertIn("if (msg.meta?.skipApi) return null;", APP_SOURCE)
        self.assertIn(
            'msg.role === "tool-call" && msg.meta?.toolCallId && !msg.meta?.skipApi',
            APP_SOURCE,
        )
        compact_start = APP_SOURCE.index("async function compactConversation()")
        compact_end = APP_SOURCE.index("function hideCompactConfirm()", compact_start)
        compact_source = APP_SOURCE[compact_start:compact_end]
        self.assertIn(
            'msg?.meta?.kind === "import-boundary"',
            compact_source,
        )
        self.assertIn(
            ".map((msg) => mapMessageForApi(msg, false))",
            compact_source,
        )
        self.assertIn(".filter(Boolean)", compact_source)
        self.assertIn(
            "state.messages = [...durableSystemMessages, summaryMsg, ...kept]",
            compact_source,
        )

        export_start = APP_SOURCE.index("function exportMarkdown()")
        export_end = APP_SOURCE.index("let sidebarDragState", export_start)
        export_source = APP_SOURCE[export_start:export_end]
        self.assertIn(
            ".filter((msg) => !msg?.meta?._system && !msg?.meta?.skipExport)",
            export_source,
        )

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

    def test_legacy_onboarding_is_removed_from_startup(self):
        self.assertNotIn('id="onboardingOverlay"', INDEX_SOURCE)
        self.assertNotIn(".onboarding-overlay", STYLE_SOURCE)
        self.assertNotIn("function shouldShowOnboarding(", SETTINGS_SOURCE)
        self.assertNotIn("function showOnboarding(", SETTINGS_SOURCE)
        self.assertNotIn("shouldShowOnboarding", APP_SOURCE)
        self.assertNotIn("showOnboarding", APP_SOURCE)
        self.assertNotRegex(I18N_SOURCE, r"\bobo(?:Welcome|Feat|Start|Step)")
        self.assertIn('localStorage.removeItem("code-onboarding")', APP_SOURCE)
        self.assertIn('localStorage.removeItem("agent-lite-onboarding")', APP_SOURCE)

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
            "watchAgentRun",
            "cancelAgentRun",
            '"waiting_authorization",',
            "await onEvent?.(event, snapshot)",
        ):
            self.assertIn(expected, RUNTIME_SOURCE)
        self.assertIn('clientRequestId = ""', RUNTIME_SOURCE)
        self.assertIn("clientRequestId,", RUNTIME_SOURCE)

    def test_agent_runtime_watcher_projects_events_sequentially_and_resumes_cursor(self):
        script = f"""
global.window = {{}};
const source = {json.dumps(RUNTIME_SOURCE)};
const urls = [];
const snapshots = [
  {{status: "running", events: [{{seq: 1, type: "created"}}, {{seq: 2, type: "model_started"}}]}},
  {{status: "completed", events: [{{seq: 3, type: "completed"}}], result: {{content: "ok"}}}},
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
(async () => {{
  const result = await window.AgentRuntime.watchAgentRun({{
    agentRunId: "agent-1",
    onEvent: async (event) => {{
      order.push(`start-${{event.seq}}`);
      await new Promise((resolve) => setTimeout(resolve, 1));
      order.push(`end-${{event.seq}}`);
    }},
  }});
  process.stdout.write(JSON.stringify({{urls, order, cursor: result.nextCursor, status: result.status}}));
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
        self.assertIn("cursor=2", data["urls"][1])
        self.assertEqual(
            data["order"],
            ["start-1", "end-1", "start-2", "end-2", "start-3", "end-3"],
        )
        self.assertEqual(data["cursor"], 3)
        self.assertEqual(data["status"], "completed")

    def test_agent_runtime_smooths_large_text_delta_without_changing_content(self):
        script = f"""
global.window = {{}};
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
  const response = await window.AgentRuntime.openSseResponse({{
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

    def test_agent_runtime_sends_background_idempotency_key(self):
        script = f"""
global.window = {{}};
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
  await window.AgentRuntime.createAgentRun({{
    sessionId: "session-1",
    clientRequestId: "background-123",
    payload: {{model: "test-model", messages: [{{role: "user", content: "hi"}}]}},
    keys: [],
    toolBudgets: [{{name: "reading", tools: ["read_file"], limit: 4}}],
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

    def test_server_agent_questionnaire_uses_durable_submit_and_reload_path(self):
        self.assertIn('name: "request_user_input"', APP_SOURCE)
        self.assertIn("const skillAllowedToolNames = applySkillTaskPolicy(", APP_SOURCE)
        self.assertIn("const serverTools = getNativeTools(ctx.toolPreset, skillAllowedToolNames)", APP_SOURCE)
        self.assertIn('if (snapshot.status === "waiting_user_input")', APP_SOURCE)
        self.assertIn("await requestServerAgentInput(ctx, snapshot.pendingInput)", APP_SOURCE)
        self.assertIn("window.AgentRuntime.submitAgentInput(request.agentRunId", APP_SOURCE)
        self.assertIn('status: nextStatus', APP_SOURCE)
        self.assertIn('const nextStatus = resolver ? "running" : "resuming"', APP_SOURCE)
        self.assertIn('agentRunId: String(tool._agentRunId || "")', APP_SOURCE)
        self.assertIn("userInputRequest: serializeUserInputRequest(request)", APP_SOURCE)

    def test_server_agent_authorization_uses_durable_card_and_reload_path(self):
        for expected in (
            "requestServerAgentAuthorization(ctx, snapshot.pendingAuthorization)",
            "window.AgentRuntime.submitAgentAuthorization(item.agentRunId",
            'status: "waiting-authorization"',
            "authorizationRequest: serializeAuthorizationRequest(request)",
            "restoreAuthorizationRequest(session.id, session.runState?.authorizationRequest)",
            "ensureServerAuthorizationProjection(ctx, pendingAuthorization)",
            "resumePersistedSessionRun(summary).catch",
        ):
            self.assertIn(expected, APP_SOURCE)
        self.assertIn(
            "Boolean(meta.serverManaged && !serverExecuting && !applied && !rejected",
            DIFF_SOURCE,
        )
        self.assertIn("executionOwner: executionOwnerForPermissionProfile(permissionProfile)", APP_SOURCE)
        self.assertIn('return ["read", "plan", "accept", "bypass"].includes(permissionProfile) ? "server-agent" : "browser"', APP_SOURCE)
        self.assertIn("action: authorizationAction", APP_SOURCE)
        self.assertIn("pendingAuthorization.path || pendingAuthorization.command", APP_SOURCE)

    def test_server_agent_uses_profile_tools_and_projects_all_authorized_actions(self):
        for expected in (
            "const profileAllowedToolNames = getAllowedToolNamesForProfile(",
            "allowedTools: serverToolNames",
            "toolBudgets: skillToolBudgets",
            'toolPreset === "full" && ["accept", "bypass"].includes(permissionProfile)',
            '["propose_edit", "apply_edit", "write_file", "delete_file"]',
            'const authorizationAction = String(pendingAuthorization.action || "propose_edit")',
            'command: String(pendingAuthorization.command || "")',
            "projectServerEditToolCompleted(ctx, event, callMessage, result)",
            "const decisionResult = result?.childResult || result || {}",
            'const delegatedEditCompletion = toolAction === "task" && Boolean(projection)',
        ):
            self.assertIn(expected, APP_SOURCE)
        self.assertNotIn("SERVER_AGENT_SAFE_TOOLS", APP_SOURCE)

    def test_agent_runtime_submits_authorization_id_and_decision(self):
        script = f"""
global.window = {{}};
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
  const result = await window.AgentRuntime.submitAgentAuthorization("agent/a", {{
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

    def test_core_module_files_exist(self):
        for relative_path in (
            "src/core/namespace.js",
            "src/core/state.js",
            "src/core/icons.js",
            "src/core/utils.js",
            "src/core/i18n.js",
            "src/core/platform.js",
            "src/services/notifications.js",
            "src/services/api-client.js",
            "src/services/persistence.js",
            "src/features/sessions.js",
            "src/features/branches.js",
            "src/ui/diff.js",
            "src/ui/markdown.js",
            "src/ui/timeline.js",
            "src/ui/messages.js",
            "src/ui/panels.js",
            "src/features/settings.js",
            "src/features/preview.js",
            "src/features/files.js",
            "src/features/skills-memory.js",
            "src/features/session-import.js",
        ):
            self.assertTrue((ROOT / relative_path).is_file(), relative_path)

    def test_scripts_load_before_runtime_and_app(self):
        scripts = (
            "./src/core/namespace.js",
            "./src/core/state.js",
            "./src/core/platform.js",
            "./src/core/icons.js",
            "./src/core/utils.js",
            "./src/core/i18n.js",
            "./src/services/notifications.js",
            "./src/services/api-client.js",
            "./src/services/persistence.js",
            "./src/ui/diff.js",
            "./src/ui/markdown.js",
            "./src/ui/timeline.js",
            "./src/ui/messages.js",
            "./src/ui/panels.js",
            "./src/features/sessions.js",
            "./src/features/branches.js",
            "./src/features/settings.js",
            "./src/features/skills-memory.js",
            "./src/features/preview.js",
            "./src/features/files.js",
            "./src/features/session-import.js",
            "./agent-runtime.js",
            "./app.js",
        )
        positions = [INDEX_SOURCE.index(f'src="{script}"') for script in scripts]
        self.assertEqual(positions, sorted(positions))

    def test_namespace_defines_supported_buckets(self):
        source = (ROOT / "src/core/namespace.js").read_text(encoding="utf-8")
        for bucket in ("core", "services", "features", "agent", "ui"):
            self.assertIn(f'Code.{bucket} = Code.{bucket} || {{}}', source)

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
            "const session = await data.getSession(sessionId);",
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
  restoreUserInputRequest: (sessionId, request) => events.push(["user-input", sessionId, request?.id || ""]),
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
        self.assertIn(["user-input", "beta", "question-beta"], result["events"])
        self.assertIn(["authorization", "beta", "authorization-beta"], result["events"])
        self.assertIn(["scroll", "beta"], result["events"])

    def test_session_startup_restores_foreground_and_orders_recovery(self):
        self.assertIn("createSessionStartup,", APP_SOURCE)
        self.assertIn("const sessionStartup = createSessionStartup({", APP_SOURCE)
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
        self.assertIn("await navigation.loadSession(lastId);", SESSIONS_SOURCE[restore_start:recovery_start])
        self.assertIn(
            ".then(() => recovery.resumePersistedQueuedMessages())",
            SESSIONS_SOURCE[recovery_start:startup_end],
        )
        self.assertIn(
            "const background = recovery.resumePersistedBackgroundRuns()",
            SESSIONS_SOURCE[recovery_start:startup_end],
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
runtime.setLang("en");
const en = runtime.t("editingMemory", {name: "demo"});
const {LANG, I18N} = window.Code.core.i18n;
const missingKeys = {
  i18nEn: Object.keys(I18N.zh).filter((key) => !(key in I18N.en)),
  i18nZh: Object.keys(I18N.en).filter((key) => !(key in I18N.zh)),
  langEn: Object.keys(LANG.zh).filter((key) => !(key in LANG.en)),
  langZh: Object.keys(LANG.en).filter((key) => !(key in LANG.zh)),
};
process.stdout.write(JSON.stringify({zh, en, persisted, changed, missingKeys}));
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
                "en": "Editing: demo",
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
  let invalidError = "";
  try { await apiJson("/server-error"); } catch (error) { serverError = error.message; }
  try { await apiJson("/invalid-error"); } catch (error) { invalidError = error.message; }
  const emptySuccess = await apiJson("/empty-success");
  process.stdout.write(JSON.stringify({success, serverError, invalidError, emptySuccess, calls}));
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
        self.assertEqual(data["copyButtonCount"], 2)
        self.assertIn("alreadyAdded", data["html"])
        self.assertIn("removedFromCode", data["html"])
        self.assertIn("removedKeyCount:1", data["html"])
        self.assertIn("removedKeysHint", data["html"])
        self.assertIn("disabledStatus", data["html"])
        self.assertIn("disabledKeyCount:1", data["html"])
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
        ):
            self.assertIn(expected, SETTINGS_SOURCE)
        for expected in (
            ".key-row.disabled .key-main",
            ".model-count-badge",
            ".model-refresh-btn.is-loading svg",
            ".model-provider-group + .model-provider-group",
            ".model-list-empty",
        ):
            self.assertIn(expected, STYLE_SOURCE)
        self.assertIn('getFromWorkbar: "从 workbar 获取"', I18N_SOURCE)

    def test_key_persistence_is_isolated_from_general_settings_and_syncs_across_tabs(self):
        save_start = APP_SOURCE.index("function saveLocalSettings()")
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
        self.assertIn('syncKeysTitle: "选择 workbar API Key"', I18N_SOURCE)
        self.assertIn('allKeysAdded: "已启用的 API Key 均已在本地列表中"', I18N_SOURCE)
        self.assertIn('detectAvailableModels: "重新检测可用模型"', I18N_SOURCE)
        self.assertIn(".key-sync-note.is-complete::before", STYLE_SOURCE)
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
        self.assertIn('name: "check_skill_dependencies"', APP_SOURCE)
        self.assertIn('"check_skill_dependencies"', APP_SOURCE[APP_SOURCE.index("const toolPolicy"):])
        self.assertIn("before first use of this Skill", SKILLS_MEMORY_SOURCE)
        self.assertIn('capability: { type: "string"', APP_SOURCE)
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
        self.assertIn('/api/file?path=assets%2Fdemo.png&raw=1', data["localImage"])
        self.assertIn('class="msg-inline-img"', data["localImage"])
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
        self.assertIn("展开全部 44 行", data["longRendered"])
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

    def test_messages_ui_owns_grouping_projection_and_response_status(self):
        self.assertIn("Code.ui.messages = Object.freeze", MESSAGES_SOURCE)
        for obsolete in (
            "function renderUserProjection(",
            "function renderThinkingProjection(",
            "function renderFinalAssistantProjection(",
            "function renderCompletedRunStatus(",
            "function renderBackgroundReplyReference(",
        ):
            self.assertNotIn(obsolete, APP_SOURCE)
        self.assertIn("window.copyMessageText = copyMessageText", APP_SOURCE)
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
  renderCompactSummary: (_msg, index) => `<compact data-index="${index}"></compact>`,
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
const expandedActiveAnswerHtml = feature.projectMessages(activeTraceMessages, {
  hasActiveRun: true,
  expandedExecutionTraces: new Set(["0"]),
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
  activeAnswerHtml,
  expandedActiveAnswerHtml,
  activeThinkingHtml,
  emptyRecoveryHtml,
  operationalHtml,
  groupedStageHtml,
  runningStage,
  completedCommands,
  completedEdits,
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
        self.assertIn('class="completed-run-label">processedLabel</span>', completed_html)
        self.assertEqual(completed_html.count("4s"), 1)
        self.assertLess(completed_html.index("run &lt;task&gt;"), completed_html.index("data-completed-run-status"))
        self.assertIn('class="execution-trace completed"', completed_html)
        self.assertIn('data-execution-trace="0"', completed_html)
        self.assertNotIn('class="execution-trace completed" open', completed_html)
        trace_start = completed_html.index('class="execution-trace completed"')
        trace_body = completed_html.index('class="execution-trace-body"', trace_start)
        first_trace_commentary = completed_html.index("<answer>inspect **project**</answer>")
        first_trace_tools = completed_html.index("data-tool-process-block", first_trace_commentary)
        final_answer = completed_html.index("<answer>done</answer>")
        trace_end = completed_html.rfind("</details>", trace_body, final_answer)
        self.assertLess(completed_html.index("data-completed-run-status"), trace_body)
        self.assertLess(trace_body, first_trace_commentary)
        self.assertLess(first_trace_commentary, first_trace_tools)
        self.assertLess(first_trace_tools, trace_end)
        self.assertLess(trace_end, final_answer)
        self.assertNotIn("execution-trace", data["simpleCompletedHtml"])
        self.assertIn("data-completed-run-status", data["simpleCompletedHtml"])
        active_answer_html = data["activeAnswerHtml"]
        self.assertIn('class="execution-trace active"', active_answer_html)
        self.assertIn('data-execution-trace="0"', active_answer_html)
        self.assertNotIn(
            '<details class="execution-trace active" data-execution-trace="0" open',
            active_answer_html,
        )
        active_trace_start = active_answer_html.index('class="execution-trace active"')
        active_summary = active_answer_html.index('class="execution-trace-summary"', active_trace_start)
        active_anchor = active_answer_html.index("data-active-run-anchor", active_summary)
        active_body = active_answer_html.index('class="execution-trace-body"', active_anchor)
        active_commentary = active_answer_html.index("checkpoint", active_body)
        active_tools = active_answer_html.index("data-tool-process-block", active_commentary)
        active_final = active_answer_html.index("first final chunk")
        active_trace_end = active_answer_html.rfind("</details>", active_tools, active_final)
        self.assertLess(active_summary, active_anchor)
        self.assertLess(active_anchor, active_body)
        self.assertLess(active_body, active_commentary)
        self.assertLess(active_commentary, active_tools)
        self.assertLess(active_tools, active_trace_end)
        self.assertLess(active_trace_end, active_final)
        self.assertIn(
            '<details class="execution-trace active" data-execution-trace="0" open',
            data["expandedActiveAnswerHtml"],
        )
        self.assertNotIn("execution-trace", data["activeThinkingHtml"])
        self.assertLess(
            data["activeThinkingHtml"].index("data-active-run-anchor"),
            data["activeThinkingHtml"].index("checkpoint"),
        )
        self.assertIn("next checkpoint", data["activeThinkingHtml"])
        self.assertNotIn("execution-trace", data["emptyRecoveryHtml"])
        self.assertLess(
            data["emptyRecoveryHtml"].index("data-active-run-anchor"),
            data["emptyRecoveryHtml"].index("data-tool-process-block"),
        )
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
        self.assertIn('data-current-action="run_command"', data["runningStage"])
        self.assertIn('class="tool-process-stage running"', data["runningStage"])
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
        })
        self.assertEqual(data["openAIUsage"], {
            "input": 100,
            "output": 4,
            "cache": 80,
        })
        self.assertIn('data-usage-kind="input"', data["cacheStatus"])
        self.assertIn('data-usage-kind="cache-read"', data["cacheStatus"])
        self.assertIn('data-usage-kind="cache-write"', data["cacheStatus"])
        self.assertIn('title="statCacheWriteTitle"', data["cacheStatus"])

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
        self.assertEqual(html.count("queued-message-cancel"), 2)
        self.assertEqual(html.count("queuedMessagePending"), 2)
        self.assertEqual(html.count("queuedMessageCanceled"), 1)

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
const {createTimelineFeature, DEFAULT_MIN_TIMELINE_WIDTH, TIMELINE_MARKER_PITCH, TIMELINE_MAX_VIEWPORT_RATIO, getCompactSummaryStats, syncSessionBranchMetadata} = window.Code.ui.timeline;
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
const metaStats = feature.getCompactSummaryStats({meta: {compressed: 5, estimatedSaved: 9000}});
const legacyStats = getCompactSummaryStats({content: "自动压缩 4 条，节省 ~1.5k"});
const compact = feature.renderCompactSummaryProjection({meta: {compressed: 5, estimatedSaved: 9000}}, 7);
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
  metaStats,
  legacyStats,
  compact,
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
        self.assertEqual(data["metaStats"], {"compressed": 5, "estimatedSaved": 9000})
        self.assertEqual(data["legacyStats"], {"compressed": 4, "estimatedSaved": 1500})
        self.assertIn('class="msg branch-indicator compact-indicator"', data["compact"])
        self.assertIn("compactMarkerMessages:5", data["compact"])
        self.assertIn("compactMarkerSaved:9000t", data["compact"])
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

    def test_panels_ui_owns_session_stats_fields_and_top_panel_interactions(self):
        self.assertIn("Code.ui.panels = Object.freeze", PANELS_SOURCE)
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
  "statsPanel", "toolLogPanel", "branchPanel", "usageStrip", "toolLogToggle",
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
let toolRenders = 0;
let systemPromptReads = 0;
let usageStats = {input: 120, output: 30, cache: 10, cacheWrite: 5};
const messages = [
  {role: "user", content: "one"},
  {role: "assistant", content: "two"},
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
  onRenderToolLog: () => { toolRenders += 1; },
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
feature.toggleToolLogPanel();
const toolWasOpen = elements.toolLogPanel.classes.has("open") && !elements.statsPanel.classes.has("open");
feature.toggleBranchPanel();
const branchWasOpen = branchOpen && elements.branchPanel.classes.has("open") && !elements.toolLogPanel.classes.has("open");
feature.dismissPanelsForTarget({closest: () => null});
const allClosed = !elements.statsPanel.classes.has("open")
  && !elements.toolLogPanel.classes.has("open")
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
  toolWasOpen,
  branchWasOpen,
  allClosed,
  branchRenders,
  toolRenders,
  fallback,
  statsWithoutCacheWrite,
  absolutePath: resolveSessionFilePath({id: "s1"}, {sessionId: "s1", absolutePath: "D:/sessions/s1.jsonl"}),
  fallbackPath: resolveSessionFilePath({id: "s2"}),
  codexSource: formatSessionSource({source: "codex"}, (key) => `t:${key}`),
  codeSource: formatSessionSource({}, (key) => `t:${key}`),
  registeredDocumentClick: Boolean(documentListeners.click),
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
            "sessionCreated": "2026-07-19 10:11",
            "sessionUpdated": "2026-07-19 12:13",
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
            "tokenContext": "60%（600c / 1000c）",
            "usageTitle": "ctx 600c/1000c",
            "ringStroke": "var(--muted)",
        })
        self.assertEqual(data["systemPromptReadsWithLastUsage"], 0)
        self.assertTrue(data["statsWasOpen"])
        self.assertTrue(data["toolWasOpen"])
        self.assertTrue(data["branchWasOpen"])
        self.assertTrue(data["allClosed"])
        self.assertEqual(data["branchRenders"], 1)
        self.assertEqual(data["toolRenders"], 1)
        self.assertEqual(data["fallback"]["contextTokens"], 14)
        self.assertFalse(data["fallback"]["cacheWriteReported"])
        self.assertFalse(data["statsWithoutCacheWrite"]["cacheWriteReported"])
        self.assertEqual(data["absolutePath"], "D:/sessions/s1.jsonl")
        self.assertEqual(data["fallbackPath"], "code/data/sessions/s2.jsonl")
        self.assertEqual(data["codexSource"], "t:sessionSourceCodex")
        self.assertEqual(data["codeSource"], "t:sessionSourceCode")
        self.assertTrue(data["registeredDocumentClick"])

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
        self.assertIn("const { createDiffFeature } = window.Code.ui.diff", APP_SOURCE)
        self.assertIn("const diffFeature = createDiffFeature", APP_SOURCE)
        self.assertIn("const { createPreviewFeature } = window.Code.features.preview", APP_SOURCE)
        self.assertIn("const previewFeature = createPreviewFeature", APP_SOURCE)
        self.assertIn("const { createFilesFeature, shortPath } = window.Code.features.files", APP_SOURCE)
        self.assertIn("const filesFeature = createFilesFeature", APP_SOURCE)
        self.assertIn("getSkillToolBudgets,", APP_SOURCE)
        self.assertIn("const skillsMemoryFeature = createSkillsMemoryFeature", APP_SOURCE)
        self.assertIn("const { createSettingsFeature } = window.Code.features.settings", APP_SOURCE)
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
        self.assertIn("APP_DIR / 'code-icon.png'", BUILD_SOURCE)
        self.assertIn("APP_DIR / 'assets'", BUILD_SOURCE)

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

    def test_tool_round_projection_is_structured_compact_and_reasoning_safe(self):
        render_start = MESSAGES_SOURCE.index("function projectMessages(")
        assistant_start = MESSAGES_SOURCE.index('if (msg.role === "assistant") {', render_start)
        assistant_end = MESSAGES_SOURCE.index('if (msg.role === "user") {', assistant_start)
        assistant_block = MESSAGES_SOURCE[assistant_start:assistant_end]

        self.assertIn(
            'const streamingToolRound = msg.streaming && msg._streamProjection === "thinking"',
            assistant_block,
        )
        self.assertIn(
            "if (msg.meta?.toolCalls?.length) {",
            assistant_block,
        )
        self.assertIn("const hasMeaningfulToolCommentary = Boolean(", assistant_block)
        self.assertIn("if (hasMeaningfulToolCommentary) {", assistant_block)
        self.assertIn("rows.push(renderFinalAssistantProjection(msg, index, assistantOptions))", assistant_block)
        self.assertIn('content: ""', assistant_block)
        self.assertIn("pendingProcess.push", assistant_block)
        self.assertLess(
            assistant_block.index("rows.push(renderFinalAssistantProjection(msg, index, assistantOptions))"),
            assistant_block.index("pendingProcess.push"),
        )
        self.assertIn("if (streamingToolRound) {", assistant_block)
        self.assertLess(
            assistant_block.index("if (streamingToolRound) {"),
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
        self.assertIn("els.messageList.innerHTML = html", render)
        self.assertNotIn("els.messages.innerHTML = html", render)
        self.assertIn("pruneStaleStreamingNodes(state.sessionId)", render)

    def test_tool_round_finalization_is_atomic(self):
        helper_start = APP_SOURCE.index("function finalizeStreamingAssistantMessage")
        helper_end = APP_SOURCE.index("function parseSseLine", helper_start)
        helper = APP_SOURCE[helper_start:helper_end]
        self.assertIn(
            "updateAssistantMessage(index, rawContent, false, sessionId, targetMessages, true)",
            helper,
        )
        self.assertLess(helper.index("current.meta.toolCalls = toolCalls"), helper.index("renderSessionMessages"))

        stream_start = APP_SOURCE.index("const toolCallsByIndex = new Map()")
        stream_end = APP_SOURCE.index("function _safeMd", stream_start)
        stream = APP_SOURCE[stream_start:stream_end]
        self.assertIn(
            'markStreamingAssistantProjection(assistantIndex, "thinking"',
            stream,
        )
        self.assertGreaterEqual(stream.count("finalizeStreamingAssistantMessage("), 2)

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
            response_helper.index("if (run.modelResponseStarted) return;"),
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
        self.assertIn('details.execution-trace[open][data-execution-trace]', render)
        self.assertIn("const html = projectMessages(msgs, {", render)
        self.assertIn("expandedExecutionTraces,", render)
        self.assertLess(render.index("parkActiveRunBanner();\n  els.messageList.innerHTML = html"), render.index("mountActiveRunBanner();", render.index("els.messageList.innerHTML = html")))
        mounted_index = render.index("mountActiveRunBanner();", render.index("els.messageList.innerHTML = html"))
        self.assertLess(mounted_index, render.index("syncActiveRunBanner(state.sessionId);", mounted_index))
        self.assertNotIn("syncActiveRunBanner(state.sessionId);", render[:render.index("if (state.messages.length === 0)")])

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


if __name__ == "__main__":
    unittest.main()
