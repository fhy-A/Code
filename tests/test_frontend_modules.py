"""Regression guards for the transitional frontend module split."""

import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
APP_SOURCE = (ROOT / "app.js").read_text(encoding="utf-8")
RUNTIME_SOURCE = (ROOT / "agent-runtime.js").read_text(encoding="utf-8")
I18N_SOURCE = (ROOT / "src" / "core" / "i18n.js").read_text(encoding="utf-8")
PLATFORM_SOURCE = (ROOT / "src" / "core" / "platform.js").read_text(encoding="utf-8")
API_CLIENT_SOURCE = (ROOT / "src" / "services" / "api-client.js").read_text(encoding="utf-8")
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
            "src/core/icons.js",
            "src/core/utils.js",
            "src/core/i18n.js",
            "src/core/platform.js",
            "src/services/notifications.js",
            "src/services/api-client.js",
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
            "./src/core/platform.js",
            "./src/core/icons.js",
            "./src/core/utils.js",
            "./src/core/i18n.js",
            "./src/services/notifications.js",
            "./src/services/api-client.js",
            "./src/ui/diff.js",
            "./src/ui/markdown.js",
            "./src/ui/timeline.js",
            "./src/ui/messages.js",
            "./src/ui/panels.js",
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
  t: (key) => key,
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
});
messages = [
  {role: "user", content: "run <task>", meta: {backgroundDispatch: {id: "job-1"}}},
  {role: "assistant", content: "inspect project", meta: {toolCalls: [{id: "call-1"}]}},
  {role: "tool-call", content: "hidden tool"},
  {role: "assistant", content: "done", _model: "model-1", meta: {_usage: {input: 12, output: 3}}, _responseTime: "4s"},
  {role: "assistant", content: "background done", meta: {kind: "background-subagent", jobId: "job-1", _usage: {input: 2}}},
  {role: "tool-result", content: "diff", meta: {edit: true}},
  {role: "assistant", content: "hidden internal", meta: {_system: true}},
];
const html = feature.projectMessages(messages, {
  hasActiveRun: true,
  branchMarker: {messageCount: 1, parentTitle: "Parent"},
});
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
  streaming,
  pending,
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
        self.assertLess(html.index("run &lt;task&gt;"), html.index("data-active-run-anchor"))
        self.assertLess(html.index("data-active-run-anchor"), html.index("<branch>Parent</branch>"))
        self.assertLess(html.index("<branch>Parent</branch>"), html.index("thinking-process"))
        self.assertLess(html.index("thinking-process"), html.index("<answer>done</answer>"))
        self.assertLess(html.index("<answer>done</answer>"), html.index("background-reply-reference"))
        self.assertLess(html.index("background-reply-reference"), html.index("<edit data-index=\"5\">"))
        self.assertIn("backgroundRunning", html)
        self.assertIn("inspect project", html)
        self.assertIn("background done", html)
        self.assertNotIn("hidden tool", html)
        self.assertNotIn("hidden internal", html)
        self.assertIn('data-stream-session="session-1"', data["streaming"])
        self.assertIn('data-stream-kind="answer"', data["streaming"])
        self.assertIn("<recovery></recovery>", data["streaming"])
        self.assertIn('data-stream-kind="pending"', data["pending"])
        self.assertNotIn("unclassified first frame", data["pending"])
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
const {createTimelineFeature, getCompactSummaryStats, syncSessionBranchMetadata} = window.Code.ui.timeline;
const escapeHtml = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
let messages = [
  {role: "user", content: "first task"},
  {role: "assistant", content: "answer"},
  {role: "user", content: "hidden", meta: {_system: true}},
  {role: "user", content: "second task " + "x".repeat(90)},
];
const sessions = [
  {id: "parent", title: "Parent <one>", _branches: ["child"]},
  {id: "child", _parentId: "parent", _branchMsgCount: null},
];
const loadedBranch = {id: "child", _parentId: "parent", _branchDepth: 1, _branches: [], _branchMsgCount: 3.8};
const visible = new Set();
const listeners = [];
const dots = [
  {dataset: {index: "0"}, addEventListener: (_type, callback) => listeners.push(callback)},
  {dataset: {index: "3"}, addEventListener: (_type, callback) => listeners.push(callback)},
];
const timeline = {
  innerHTML: "",
  classList: {
    add: (name) => visible.add(name),
    remove: (name) => visible.delete(name),
  },
  querySelectorAll: () => dots,
};
let scrolled = null;
const messageContainer = {
  querySelector: (selector) => ({scrollIntoView: (options) => { scrolled = {selector, options}; }}),
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
listeners[1]();
messages = [{role: "user", content: "only one"}];
feature.renderTimeline();
process.stdout.write(JSON.stringify({
  metaStats,
  legacyStats,
  compact,
  syncedBranch,
  branchMarker,
  branch,
  nodes,
  timelineHtml,
  wasVisible,
  scrolled,
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
        self.assertEqual(data["metaStats"], {"compressed": 5, "estimatedSaved": 9000})
        self.assertEqual(data["legacyStats"], {"compressed": 4, "estimatedSaved": 1500})
        self.assertIn('class="msg branch-indicator compact-indicator"', data["compact"])
        self.assertIn("compactMarkerMessages:5", data["compact"])
        self.assertIn("compactMarkerSaved:9000t", data["compact"])
        self.assertEqual(data["syncedBranch"]["_branchMsgCount"], 3.8)
        self.assertEqual(data["branchMarker"], {"messageCount": 3, "parentTitle": "Parent <one>"})
        self.assertIn("Parent &lt;one&gt;", data["branch"])
        self.assertEqual([node["index"] for node in data["nodes"]], [0, 3])
        self.assertTrue(data["nodes"][1]["label"].endswith("..."))
        self.assertIn('data-index="0"', data["timelineHtml"])
        self.assertIn('data-index="3"', data["timelineHtml"])
        self.assertTrue(data["wasVisible"])
        self.assertEqual(data["scrolled"]["selector"], '[data-msg-index="3"]')
        self.assertEqual(data["scrolled"]["options"], {"behavior": "smooth", "block": "start"})
        self.assertEqual(data["clearedHtml"], "")
        self.assertFalse(data["visibleAfterClear"])

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

    def test_thought_projection_only_collects_tool_round_summaries(self):
        render_start = MESSAGES_SOURCE.index("function projectMessages(")
        assistant_start = MESSAGES_SOURCE.index('if (msg.role === "assistant") {', render_start)
        assistant_end = MESSAGES_SOURCE.index('if (msg.role === "user") {', assistant_start)
        assistant_block = MESSAGES_SOURCE[assistant_start:assistant_end]

        self.assertIn(
            'const streamingToolRound = msg.streaming && msg._streamProjection === "thinking"',
            assistant_block,
        )
        self.assertIn(
            "if (msg.meta?.toolCalls?.length || streamingToolRound) {",
            assistant_block,
        )
        self.assertIn("pendingThoughts.push", assistant_block)
        self.assertLess(
            assistant_block.index("if (msg.meta?.toolCalls?.length || streamingToolRound) {"),
            assistant_block.index("pendingThoughts.push"),
        )
        projection_start = MESSAGES_SOURCE.index("function renderThinkingProjection")
        projection_end = MESSAGES_SOURCE.index("function renderAssistantResponseInfo", projection_start)
        projection = MESSAGES_SOURCE[projection_start:projection_end]
        self.assertIn('data-stream-kind="thinking"', projection)
        self.assertIn('data-stream-part="summary"', projection)
        self.assertNotIn('t("thoughtProcess")', projection)
        self.assertNotIn(".thinking-process .role", STYLE_SOURCE)
        self.assertIn("const hasVisibleSummary = summaries.some", projection)
        self.assertIn('if (!hasVisibleSummary) return ""', projection)
        self.assertNotIn('thinking-process.is-empty', STYLE_SOURCE)
        self.assertNotIn("MAX_LEN", projection)
        self.assertNotIn("truncate", projection)
        thought_style_start = STYLE_SOURCE.index(".thinking-summary-list {")
        thought_style_end = STYLE_SOURCE.index("}", thought_style_start)
        thought_style = STYLE_SOURCE[thought_style_start:thought_style_end]
        self.assertIn("color: var(--text)", thought_style)
        self.assertIn("font-size: 14.5px", thought_style)
        self.assertIn("line-height: 1.76", thought_style)
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
        self.assertIn(".thinking-summary-item + .thinking-summary-item", STYLE_SOURCE)
        spacing_start = STYLE_SOURCE.index(".thinking-summary-item + .thinking-summary-item")
        spacing_end = STYLE_SOURCE.index("}", spacing_start)
        self.assertIn("margin-top: .65em", STYLE_SOURCE[spacing_start:spacing_end])
        thought_spacing_start = STYLE_SOURCE.rindex(".thinking-process {")
        thought_spacing_end = STYLE_SOURCE.index("}", thought_spacing_start)
        self.assertIn("margin-bottom: 20px", STYLE_SOURCE[thought_spacing_start:thought_spacing_end])

    def test_streaming_projection_switches_kind_without_leaking_raw_reasoning(self):
        projection_start = MESSAGES_SOURCE.index("function renderFinalAssistantProjection")
        projection_end = MESSAGES_SOURCE.index("function projectMessages", projection_start)
        projection = MESSAGES_SOURCE[projection_start:projection_end]

        self.assertIn('data-stream-session="${escapeHtml(getSessionId() || "")}"', projection)
        self.assertIn('const streamKind = msg._streamProjection === "answer" ? "answer" : "pending"', projection)
        self.assertIn('data-stream-kind="${streamKind}"', projection)
        self.assertIn('streamKind === "pending" ? " is-pending" : ""', projection)
        self.assertIn('data-stream-role', projection)
        self.assertIn('streaming-answer-role${showModel ? "" : " is-empty"}', projection)
        self.assertNotIn('data-stream-part="thought"', projection)
        self.assertNotIn("msg.thought", projection)
        patch_start = APP_SOURCE.index("function patchStreamingAssistantMessage")
        patch_end = APP_SOURCE.index("function scheduleStreamingAssistantPatch", patch_start)
        patch = APP_SOURCE[patch_start:patch_end]
        self.assertIn('streamKind === "thinking"', patch)
        self.assertIn('if (streamKind === "pending")', patch)
        self.assertIn("scheduleStreamingAnswerProjection(sessionId, index)", patch)
        self.assertIn('streamKind !== "answer" || !visibleContent', patch)
        self.assertIn('data-stream-part="summary"', patch)
        self.assertIn('msg._streamProjection === "thinking" && visibleContent', patch)
        self.assertIn("renderSessionMessages(sessionId)", patch)
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
        self.assertIn('nodes.label.textContent = t("processingLabel")', helper)
        self.assertIn("nodes.timer.textContent = getRunTimerDisplay(sessionId)", helper)
        self.assertNotIn("run-model", helper)
        self.assertNotIn("data-active-run-phase", helper)
        self.assertNotIn("function setTaskPhase", APP_SOURCE)
        self.assertNotIn("_taskPhase", APP_SOURCE)
        self.assertNotIn("executingTool", APP_SOURCE)

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
        self.assertIn("projectMessages(msgs, { hasActiveRun, branchMarker })", render)
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

    def test_error_recovery_preserves_user_message_on_rollback(self):
        """Rollback restores user message content and keeps it at snapshot-1."""
        self.assertIn("userMsg.content = originalUserContent", APP_SOURCE)
        self.assertIn("const originalUserContent = messageContent", APP_SOURCE)
        self.assertIn('userMsg.role === "user"', APP_SOURCE)

    # ── error_code frontend display ──

    def test_error_code_meta_has_all_codes(self):
        """All 7 error codes have entries in _errorCodeMeta."""
        codes = ["upstream_error", "config_error", "permission_denied",
                 "tool_error", "user_cancelled", "empty_response", "internal_error"]
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
        self.assertIn("errLabelEmptyResponse", I18N_SOURCE)
        self.assertIn("errSugEmptyResponse", I18N_SOURCE)
        self.assertIn("errAgentFailed", I18N_SOURCE)

    def test_i18n_keys_have_both_languages(self):
        """Error i18n keys exist in both Chinese and English."""
        self.assertIn("上游异常", I18N_SOURCE)
        self.assertIn("Upstream error", I18N_SOURCE)
        self.assertIn("模型未产出回复", I18N_SOURCE)
        self.assertIn("No response generated", I18N_SOURCE)

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
        create_start = APP_SOURCE.index("async function createSession(")
        create_end = APP_SOURCE.index("async function loadSession(", create_start)
        create_source = APP_SOURCE[create_start:create_end]
        self.assertIn("state.pendingProjectId", create_source)
        self.assertIn("body.projectId = projectId", create_source)
        self.assertNotIn("projectSelect", create_source)

    def test_session_restore_waits_for_sidebar_refresh(self):
        init_start = APP_SOURCE.index("async function init()")
        init_end = APP_SOURCE.index("const foregroundView", init_start)
        self.assertIn("await refreshSessions();", APP_SOURCE[init_start:init_end])


if __name__ == "__main__":
    unittest.main()
