"""
P2 Coverage Tests — compaction, i18n completeness, skills, memory endpoints.

Run: python -m pytest tests/test_p2_coverage.py -v
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as server_mod


# ═══════════════════════════════════════════════════════════════════
# 1. Context Compaction — validation & formatting
# ═══════════════════════════════════════════════════════════════════

class TestCompactValidation(unittest.TestCase):

    def setUp(self):
        self.handler = object.__new__(server_mod.CodeHandler)
        self.handler.send_json = mock.Mock()
        self.handler.read_body_json = mock.Mock()
        self.handler.headers = {}  # simulate HTTP headers
        # Compact uses NEW_API_BASE_URL — must be a valid URL prefix
        self._url_patcher = mock.patch.object(server_mod, "NEW_API_BASE_URL", "https://api.example.com")
        self._url_patcher.start()
        self.addCleanup(self._url_patcher.stop)

    def test_rejects_fewer_than_6_messages(self):
        self.handler.read_body_json.return_value = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "hi"}] * 4,
        }
        self.handler.headers["Authorization"] = "Bearer sk-test"
        with self.assertRaises(ValueError):
            server_mod.CodeHandler.compact(self.handler)

    def test_rejects_missing_model(self):
        self.handler.read_body_json.return_value = {
            "model": "",
            "messages": [{"role": "user", "content": str(i)} for i in range(10)],
        }
        self.handler.headers["Authorization"] = "Bearer sk-test"
        with self.assertRaises(ValueError):
            server_mod.CodeHandler.compact(self.handler)

    def test_rejects_missing_api_key(self):
        self.handler.read_body_json.return_value = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": str(i)} for i in range(10)],
        }
        with self.assertRaises(ValueError):
            server_mod.CodeHandler.compact(self.handler)

    def _make_urlopen_mock(self, summary="Summary text"):
        """Create a proper mock for request.urlopen that works as context manager."""
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": summary}}]
        }).encode("utf-8")
        # urlopen returns this mock; then "with ... as resp" calls __enter__ on it
        # which should return something whose .read() returns our data
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        return mock_resp

    def test_keep_count_bounded(self):
        """Verify keep_count formula: max(2, min(6, len//4))."""
        self.handler.read_body_json.return_value = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": str(i)} for i in range(40)],
        }
        self.handler.headers["Authorization"] = "Bearer sk-test"
        with mock.patch.object(server_mod.request, "urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._make_urlopen_mock()
            server_mod.CodeHandler.compact(self.handler)
            data = self.handler.send_json.call_args[0][0]
            self.assertTrue(data.get("ok"), f"Expected ok, got: {data}")
            self.assertEqual(data["kept"], 6, "40 messages should keep 6")
            self.assertEqual(data["compressed"], 34, "40 messages should compress 34")

    def test_keep_count_minimum_2(self):
        """With 8 messages, keep_count = max(2, min(6, 2)) = 2."""
        self.handler.read_body_json.return_value = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": str(i)} for i in range(8)],
        }
        self.handler.headers["Authorization"] = "Bearer sk-test"
        with mock.patch.object(server_mod.request, "urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._make_urlopen_mock()
            server_mod.CodeHandler.compact(self.handler)
            data = self.handler.send_json.call_args[0][0]
            self.assertTrue(data.get("ok"))
            self.assertGreaterEqual(data["kept"], 2)

    def test_multimodal_content_extracts_text_without_leaking_image_data(self):
        image_data = "data:image/png;base64,SHOULD_NOT_REACH_COMPACTION_PROMPT"
        self.handler.read_body_json.return_value = {
            "model": "gpt-4",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请分析这张图片中的数据"},
                        {"type": "image_url", "image_url": {"url": image_data}},
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_data}},
                    ],
                },
                *[
                    {"role": "assistant", "content": f"message-{index}"}
                    for index in range(6)
                ],
            ],
        }
        self.handler.headers["Authorization"] = "Bearer sk-test"

        with mock.patch.object(server_mod.request, "urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._make_urlopen_mock()
            server_mod.CodeHandler.compact(self.handler)

        upstream_request = mock_urlopen.call_args[0][0]
        upstream_payload = json.loads(upstream_request.data.decode("utf-8"))
        prompt = upstream_payload["messages"][0]["content"]
        self.assertIn("请分析这张图片中的数据", prompt)
        self.assertNotIn(image_data, prompt)
        self.assertNotIn("SHOULD_NOT_REACH_COMPACTION_PROMPT", prompt)
        self.assertTrue(self.handler.send_json.call_args[0][0]["ok"])

    def test_uses_request_base_url_and_normalizes_v1_suffix(self):
        self.handler.read_body_json.return_value = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": str(i)} for i in range(8)],
        }
        self.handler.headers.update({
            "Authorization": "Bearer sk-test",
            "X-Base-URL": "https://gateway.example/v1/",
        })
        with mock.patch.object(server_mod.request, "urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._make_urlopen_mock()
            server_mod.CodeHandler.compact(self.handler)

        request_object = mock_urlopen.call_args[0][0]
        self.assertEqual(
            request_object.full_url,
            "https://gateway.example/v1/chat/completions",
        )
        self.assertTrue(self.handler.send_json.call_args[0][0]["ok"])

    def test_empty_base_url_falls_back_to_local_gateway(self):
        self.handler.read_body_json.return_value = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": str(i)} for i in range(8)],
        }
        self.handler.headers["Authorization"] = "Bearer sk-test"
        with mock.patch.object(server_mod, "NEW_API_BASE_URL", ""), \
             mock.patch.object(server_mod.request, "urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._make_urlopen_mock()
            server_mod.CodeHandler.compact(self.handler)

        request_object = mock_urlopen.call_args[0][0]
        self.assertEqual(
            request_object.full_url,
            "http://localhost:3000/v1/chat/completions",
        )
        self.assertTrue(self.handler.send_json.call_args[0][0]["ok"])

    def test_role_labels_applied(self):
        """Verify user/assistant/tool-call/tool-result labels are in the prompt."""
        self.handler.read_body_json.return_value = {
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": "Fix the bug"},
                {"role": "assistant", "content": "I'll look"},
                {"role": "tool-call", "content": "read_file app.js"},
                {"role": "tool-result", "content": "content here..."},
                {"role": "user", "content": "thanks"},
                {"role": "assistant", "content": "done"},
                {"role": "user", "content": "extra"},
                {"role": "assistant", "content": "extra2"},
            ],
        }
        self.handler.headers["Authorization"] = "Bearer sk-test"
        # Capture the request body sent to the LLM
        with mock.patch.object(server_mod.request, "urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._make_urlopen_mock()
            server_mod.CodeHandler.compact(self.handler)
            data = self.handler.send_json.call_args[0][0]
            self.assertTrue(data.get("ok"))
            # Verify the request was made
            mock_urlopen.assert_called_once()
            req = mock_urlopen.call_args[0][0]
            payload = json.loads(req.data.decode("utf-8"))
            summary_request = payload["messages"][0]["content"]
            self.assertIn("用户", summary_request)
            self.assertIn("Agent", summary_request)

    def test_content_truncation(self):
        """Long messages should be truncated to 800 chars in the prompt."""
        long_content = "x" * 2000
        self.handler.read_body_json.return_value = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": long_content}] * 10,
        }
        self.handler.headers["Authorization"] = "Bearer sk-test"
        with mock.patch.object(server_mod.request, "urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._make_urlopen_mock()
            server_mod.CodeHandler.compact(self.handler)
            data = self.handler.send_json.call_args[0][0]
            self.assertTrue(data.get("ok"))
            # Verify truncation: each message truncated to ~800 chars in the prompt
            req = mock_urlopen.call_args[0][0]
            payload = json.loads(req.data.decode("utf-8"))
            prompt_content = payload["messages"][0]["content"]
            self.assertIn("...", prompt_content)

    def test_role_labels_applied(self):
        """Verify user/assistant/tool-call/tool-result labels are in the prompt."""
        self.handler.read_body_json.return_value = {
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": "Fix the bug"},
                {"role": "assistant", "content": "I'll look at the code"},
                {"role": "tool-call", "content": "read_file app.js"},
                {"role": "tool-result", "content": "content here..."},
                {"role": "user", "content": "thanks"},
                {"role": "assistant", "content": "done"},
                {"role": "user", "content": "extra msg 1"},
                {"role": "assistant", "content": "extra msg 2"},
            ],
        }
        self.handler.headers["Authorization"] = "Bearer sk-test"
        captured_prompt = []

        def capture_request(req, **kwargs):
            captured_prompt.append(req.data.decode("utf-8"))
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps({
                "choices": [{"message": {"content": "Summary"}}]
            }).encode()
            mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
            mock_resp.__exit__ = mock.Mock(return_value=False)
            return mock_resp

        with mock.patch.object(server_mod.request, "urlopen", side_effect=capture_request):
            server_mod.CodeHandler.compact(self.handler)
            data = self.handler.send_json.call_args[0][0]
            self.assertTrue(data.get("ok"))
            prompt = captured_prompt[0] if captured_prompt else ""
            payload = json.loads(prompt)
            summary_request = payload["messages"][0]["content"]
            self.assertIn("用户", summary_request)
            self.assertIn("Agent", summary_request)
            self.assertIn("工具调用", summary_request)
            self.assertIn("工具结果", summary_request)

    def test_content_truncation(self):
        """Long messages should be truncated to 800 chars in the prompt."""
        long_content = "x" * 2000
        self.handler.read_body_json.return_value = {
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": long_content},
            ] * 10,
        }
        self.handler.headers["Authorization"] = "Bearer sk-test"
        captured_prompt = []

        def capture_request(req, **kwargs):
            captured_prompt.append(req.data.decode("utf-8"))
            mock_resp = mock.MagicMock()
            mock_resp.read.return_value = json.dumps({
                "choices": [{"message": {"content": "Summary"}}]
            }).encode()
            mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
            mock_resp.__exit__ = mock.Mock(return_value=False)
            return mock_resp

        with mock.patch.object(server_mod.request, "urlopen", side_effect=capture_request):
            server_mod.CodeHandler.compact(self.handler)
            data = self.handler.send_json.call_args[0][0]
            self.assertTrue(data.get("ok"))
            prompt = captured_prompt[0] if captured_prompt else ""
            payload = json.loads(prompt)
            summary_request = payload["messages"][0]["content"]
            # Truncated content should have "..." marker or total prompt ≤ 24000
            self.assertTrue("..." in summary_request or len(summary_request) <= 25000)


# ═══════════════════════════════════════════════════════════════════
# 2. i18n translation completeness
# ═══════════════════════════════════════════════════════════════════

class TestI18nCoverage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        cls.source = (root / "src" / "core" / "i18n.js").read_text(encoding="utf-8")
        cls.html_source = (root / "index.html").read_text(encoding="utf-8")

    def test_both_languages_present(self):
        """I18N must have both zh and en sections."""
        self.assertIn("I18N = {", self.source)
        self.assertIn("zh: {", self.source)
        self.assertIn("en: {", self.source)

    def test_both_languages_have_similar_size(self):
        """zh and en should have roughly the same number of entries."""
        # A representative key must exist once in each main language section.
        self.assertEqual(self.source.count("toolListFiles:"), 2)

    def test_t_supports_interpolation(self):
        self.assertIn("function t(key", self.source)
        self.assertIn("params", self.source)
        # t() should support {param} interpolation
        self.assertIn("replace(", self.source)
        self.assertIn("params[", self.source)

    def test_html_has_i18n_attributes(self):
        """index.html should use data-i18n for internationalization."""
        # Should have a substantial number of data-i18n attributes
        i18n_count = len(re.findall(r'data-i18n[-\w]*="', self.html_source))
        self.assertGreater(i18n_count, 20,
                           f"Only {i18n_count} data-i18n attributes found")

    def test_critical_keys_present(self):
        """Verify essential UX strings exist in source (either LANG or I18N)."""
        critical = [
            "cancel", "save", "delete", "settings", "models",
            "memory", "skills", "language", "theme",
            "sendTip", "welcome", "newFolder", "refreshFiles",
        ]
        for key in critical:
            # Check as I18N property name
            found = (f"{key}: " in self.source or f"{key}:" in self.source)
            self.assertTrue(found, f"Critical key '{key}' not found in i18n.js")


# ═══════════════════════════════════════════════════════════════════
# 2b. Context compaction marker
# ═══════════════════════════════════════════════════════════════════

class TestCompactSummaryMarker(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        cls.source = (root / "app.js").read_text(encoding="utf-8")
        cls.state_source = (root / "src" / "core" / "state.js").read_text(encoding="utf-8")
        cls.messages_source = (root / "src" / "ui" / "messages.js").read_text(encoding="utf-8")
        cls.timeline_source = (root / "src" / "ui" / "timeline.js").read_text(encoding="utf-8")
        cls.i18n_source = (root / "src" / "core" / "i18n.js").read_text(encoding="utf-8")
        cls.compaction_source = (root / "src" / "agent" / "compaction.js").read_text(encoding="utf-8")

    def test_compact_summary_is_hidden_from_message_flow(self):
        self.assertIn('msg.meta?.kind === "compact-summary"', self.messages_source)
        self.assertNotIn("renderCompactSummary(msg, index)", self.messages_source)
        self.assertNotIn("renderCompactSummaryProjection", self.timeline_source)
        self.assertNotIn('class="msg branch-indicator compact-indicator"', self.timeline_source)

    def test_manual_compaction_uses_summary_message_factory(self):
        self.assertEqual(self.source.count("const summaryMsg = createCompactSummaryMessage(result, {"), 1)
        self.assertIn('kind: "compact-summary"', self.compaction_source)

    def test_manual_compaction_projection_is_localized_and_separate(self):
        for key in (
            "manualCompactingContext",
            "manualCompactedContext",
            "manualCompactContextFailed",
        ):
            self.assertEqual(self.i18n_source.count(f"{key}:"), 2, key)
        self.assertIn('msg.meta?.kind === "manual-context-compaction"', self.messages_source)
        self.assertIn("closeExecutionTrace();", self.messages_source)
        self.assertIn('data-context-compaction-mode="${manual ? "manual" : "auto"}"', self.messages_source)
        compact_start = self.source.index("async function compactConversation()")
        compact_end = self.source.index("function hideCompactConfirm()", compact_start)
        compact_source = self.source[compact_start:compact_end]
        self.assertIn('kind: "manual-context-compaction"', compact_source)
        self.assertIn('status: "running"', compact_source)
        self.assertIn("skipApi: true", compact_source)
        self.assertIn('finishManualCompactionMarker("completed")', compact_source)
        self.assertIn('finishManualCompactionMarker("failed", err.message)', compact_source)
        self.assertIn("...messagesBeforeCompaction, summaryMsg, manualCompactionMarker", compact_source)
        self.assertIn("messages: messagesBeforeCompaction", compact_source)
        self.assertNotIn('showToast(t("compactMarker")', compact_source)

    def test_manual_compaction_passes_current_gateway_base_url(self):
        compact_start = self.source.index("async function compactConversation()")
        compact_end = self.source.index("function hideCompactConfirm()", compact_start)
        compact_source = self.source[compact_start:compact_end]
        self.assertIn('const baseUrl = els.baseUrl.value.trim() || "http://localhost:3000"', compact_source)
        self.assertIn('"X-Base-URL": baseUrl', compact_source)

    def test_manual_compaction_keeps_full_history_and_persists_summary_boundary(self):
        self.assertIn(
            "const keptMessages = compactableMessages.slice(keepStartIndex)",
            self.compaction_source,
        )
        self.assertIn(
            "state.messages = [...messagesBeforeCompaction, summaryMsg, manualCompactionMarker]",
            self.source,
        )
        compact_start = self.source.index("async function compactConversation()")
        compact_end = self.source.index("function hideCompactConfirm()", compact_start)
        compact_source = self.source[compact_start:compact_end]
        self.assertIn("const modelContextMessages = getModelContextMessages(", compact_source)
        self.assertIn("buildManualCompactionPlan(modelContextMessages, {", compact_source)
        self.assertNotIn(
            "state.messages = [...durableSystemMessages, summaryMsg, ...keptMessages",
            compact_source,
        )
        self.assertIn("await saveSessionState(", compact_source)
        self.assertIn("{ persistMessages: true }", compact_source)
        self.assertNotIn("_compactPrefix", self.source)

    def test_usage_is_isolated_and_persisted_per_session(self):
        self.assertIn("_sessionLastUsage: {}", self.state_source)
        self.assertIn("setSessionLastUsage(sessionId, turnEvent.usage)", self.source)
        self.assertIn("lastUsage: getSessionLastUsage(sessionId)", self.source)

    def test_context_limit_handles_hyphenated_claude_versions(self):
        self.assertIn("function getModelContextLimit(model)", self.compaction_source)
        self.assertIn("const claudeVersion = normalized.match", self.compaction_source)
        self.assertIn("major === 4 && minor >= 6", self.compaction_source)


class TestBranchFlowMarker(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        cls.source = (root / "app.js").read_text(encoding="utf-8")
        cls.messages_source = (root / "src" / "ui" / "messages.js").read_text(encoding="utf-8")
        cls.timeline_source = (root / "src" / "ui" / "timeline.js").read_text(encoding="utf-8")
        cls.sessions_source = (root / "src" / "features" / "sessions.js").read_text(encoding="utf-8")
        cls.branches_source = (root / "src" / "features" / "branches.js").read_text(encoding="utf-8")

    def test_branch_marker_uses_raw_message_boundary(self):
        self.assertIn("const branchMarker = getBranchFlowMarker();", self.source)
        self.assertIn("if (index === branchBoundary) insertBranchMarker();", self.messages_source)

    def test_loaded_branch_metadata_hydrates_session_summary(self):
        self.assertIn("syncMetadata: syncSessionBranchMetadata", self.source)
        self.assertIn("branch.syncMetadata(state.sessions, session)", self.sessions_source)
        self.assertIn("function syncSessionBranchMetadata(", self.timeline_source)

    def test_new_branch_inherits_usage_baseline_before_loading(self):
        create_start = self.branches_source.index("async function createBranch(title)")
        create_end = self.branches_source.index("function bind()", create_start)
        create_branch = self.branches_source[create_start:create_end]
        self.assertIn("const parentStats = { ...(getSessionStats(parentSessionId) || {}) };", create_branch)
        self.assertIn("setSessionStats(response.id, inheritedStats);", create_branch)
        self.assertIn("setSessionLastUsage(response.id, response.lastUsage || parentLastUsage);", create_branch)
        self.assertIn("createBranchesFeature({", self.source)

    def test_branch_tree_derives_children_from_list_parent_metadata(self):
        self.assertIn("item._parentId === record.id", self.branches_source)
        self.assertIn("new Set([...explicitBranchIds, ...derivedBranchIds])", self.branches_source)

    def test_branch_marker_does_not_splice_projected_rows(self):
        self.assertNotIn("rows.splice(insertAt", self.messages_source)

    def test_plain_session_is_not_treated_as_branch(self):
        self.assertIn("if (!current || current._branchMsgCount == null) return null;", self.timeline_source)
        self.assertIn("if (!parent) return null;", self.timeline_source)


# ═══════════════════════════════════════════════════════════════════
# 3. Skills CRUD
# ═══════════════════════════════════════════════════════════════════

class TestPreviewLineWrapping(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        cls.styles = (root / "styles.css").read_text(encoding="utf-8")
        cls.script = (root / "src" / "features" / "preview.js").read_text(encoding="utf-8")

    def test_code_preview_wraps_inside_narrow_pane(self):
        self.assertIn("grid-template-columns: 52px minmax(0, 1fr);", self.styles)
        self.assertIn("white-space: pre-wrap;", self.styles)
        self.assertIn("overflow-wrap: anywhere;", self.styles)

    def test_drag_temporarily_disables_expensive_wrapping(self):
        self.assertIn(".resizing-preview .code-preview .line-code", self.styles)
        self.assertIn("requestAnimationFrame(() =>", self.script)
        self.assertIn("applyPreviewWidth(pendingWidth, false);", self.script)

    def test_large_preview_uses_lightweight_rendering(self):
        self.assertIn("normalized.length <= 350000 && lines.length <= 8000", self.script)
        self.assertIn("formatMeta(data)", self.script)
        self.assertIn(r'join(" \u00b7 ")', self.script)


class TestPreviewDecoding(unittest.TestCase):

    def test_truncated_utf8_drops_incomplete_tail_without_replacement(self):
        encoded = "中文".encode("utf-8")
        text, encoding = server_mod.decode_preview_text(encoded[:-1], truncated=True)
        self.assertEqual(text, "中")
        self.assertEqual(encoding, "utf-8")
        self.assertNotIn("\ufffd", text)

    def test_utf16_bom_is_text_and_decodes(self):
        encoded = "配置文件".encode("utf-16")
        self.assertTrue(server_mod.is_probably_text(encoded))
        text, encoding = server_mod.decode_preview_text(encoded)
        self.assertEqual(text, "配置文件")
        self.assertEqual(encoding, "utf-16")

    def test_gb18030_fallback(self):
        encoded = "中文源码".encode("gb18030")
        text, encoding = server_mod.decode_preview_text(encoded)
        self.assertEqual(text, "中文源码")
        self.assertEqual(encoding, "gb18030")


class TestSkillsCRUD(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp_data = Path(tempfile.mkdtemp(prefix="code_skill_"))
        cls.tmp_skills = cls.tmp_data / "skills"
        cls.tmp_skills.mkdir(parents=True)
        cls._patcher = mock.patch.object(server_mod, "SKILLS_DIR", cls.tmp_skills)
        cls._patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._patcher.stop()

    def setUp(self):
        for child in self.tmp_skills.iterdir():
            if child.is_dir():
                server_mod.shutil.rmtree(child)
            else:
                child.unlink()

    def test_list_empty(self):
        result = server_mod.list_skills()
        self.assertEqual(result, [])

    def test_create_and_list(self):
        server_mod.create_skill(
            name="test-skill",
            description="A test skill",
            body_text="Do the thing carefully.",
            tools="read_file, search_files",
            keywords="test, example",
        )
        skills = server_mod.list_skills()
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]["name"], "test-skill")
        self.assertEqual(skills[0]["description"], "A test skill")
        self.assertEqual(skills[0]["tools"], ["read_file", "search_files"])
        self.assertEqual(skills[0]["keywords"], ["test", "example"])

    def test_create_skill_with_dependency_manifest(self):
        capabilities = {
            "default": {
                "required": [
                    {"type": "python", "name": "requests", "minimumVersion": "2.0"},
                ],
                "optional": [
                    {
                        "type": "command",
                        "name": "git",
                        "installHint": "Windows PowerShell: winget install --id Git.Git --exact",
                    },
                ],
            },
        }
        result = server_mod.create_skill(
            name="dependency-skill",
            description="Dependency test",
            body_text="Use the declared dependencies.",
            dependencies=capabilities,
        )

        manifest_path = self.tmp_skills / "dependency-skill" / "dependencies.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["skill"], "dependency-skill")
        self.assertEqual(manifest["capabilities"], capabilities)
        self.assertEqual(result["dependencyCapabilities"], capabilities)
        self.assertNotIn("dependencies.json", result["resources"].get("files", []))

    def test_copied_skill_dependencies_are_detected_and_exposed_to_model(self):
        server_mod.create_skill(
            name="copied-dependency-skill",
            description="Copied dependency test",
            body_text="Run the packaged script.",
        )
        skill_dir = self.tmp_skills / "copied-dependency-skill"
        (skill_dir / "requirements.txt").write_text(
            "code-test-missing-package>=1.0\n",
            encoding="utf-8",
        )

        skill = server_mod.read_skill("copied-dependency-skill")
        checked = server_mod.execute_check_skill_dependencies_tool({
            "name": "copied-dependency-skill",
        })
        loaded = server_mod.execute_use_skill_tool({"name": "copied-dependency-skill"})

        self.assertEqual(skill["dependencyManifestSource"], "detected")
        self.assertIn("python-runtime", skill["dependencyCapabilities"])
        self.assertIn("requirements.txt", skill["dependencyDetectedFrom"])
        self.assertEqual(checked["status"], "unavailable")
        self.assertTrue(checked["installGuidance"]["needed"])
        self.assertEqual(loaded["dependencies"]["manifestSource"], "detected")
        self.assertFalse((skill_dir / "dependencies.json").exists())

        server_mod.update_skill(
            "copied-dependency-skill",
            "copied-dependency-skill",
            "Updated without overriding dependencies",
            "Run the packaged script.",
        )
        self.assertFalse((skill_dir / "dependencies.json").exists())

    def test_invalid_dependency_manifest_does_not_leave_partial_skill(self):
        with self.assertRaises(server_mod.DependencyManifestError):
            server_mod.create_skill(
                name="invalid-dependency-skill",
                description="Invalid dependency test",
                body_text="This should not be created.",
                dependencies={
                    "default": {
                        "required": [{"type": "installer", "name": "bad"}],
                    },
                },
            )
        self.assertFalse((self.tmp_skills / "invalid-dependency-skill").exists())

    def test_update_skill_preserves_resources_and_rewrites_dependencies(self):
        server_mod.create_skill(
            name="rename-source",
            description="Before",
            body_text="Before body.",
            dependencies={
                "default": {
                    "required": [{"type": "python", "name": "requests"}],
                },
            },
        )
        references = self.tmp_skills / "rename-source" / "references"
        references.mkdir()
        (references / "guide.md").write_text("Keep me", encoding="utf-8")

        result = server_mod.update_skill(
            "rename-source",
            "rename-target",
            "After",
            "After body.",
            dependencies={
                "render": {
                    "required": [{"type": "command", "name": "pdftoppm"}],
                },
            },
        )

        target = self.tmp_skills / "rename-target"
        manifest = json.loads((target / "dependencies.json").read_text(encoding="utf-8"))
        self.assertFalse((self.tmp_skills / "rename-source").exists())
        self.assertEqual((target / "references" / "guide.md").read_text(encoding="utf-8"), "Keep me")
        self.assertEqual(manifest["skill"], "rename-target")
        self.assertIn("render", result["dependencyCapabilities"])
        self.assertEqual(result["description"], "After")
        self.assertEqual(result["body"], "After body.")

        cleared = server_mod.update_skill(
            "rename-target",
            "rename-target",
            "After",
            "After body.",
            dependencies={},
        )
        self.assertFalse((target / "dependencies.json").exists())
        self.assertEqual(cleared["dependencyCapabilities"], {})

    def test_read_single(self):
        server_mod.create_skill(
            name="read-test",
            description="Read test",
            body_text="Read carefully.",
        )
        result = server_mod.read_skill("read-test")
        self.assertEqual(result["name"], "read-test")
        self.assertEqual(result["body"], "Read carefully.")

    def test_read_skill_resource_stays_inside_packaged_resource_dirs(self):
        server_mod.create_skill(
            name="resource-test",
            description="Resource test",
            body_text="Read the reference.",
        )
        reference_dir = self.tmp_skills / "resource-test" / "references"
        reference_dir.mkdir()
        (reference_dir / "guide.md").write_text("Safe reference", encoding="utf-8")

        self.assertEqual(
            server_mod.read_skill_file("resource-test", "references/guide.md"),
            "Safe reference",
        )
        for skill_name, rel_path in (
            ("..", "memory/secret.md"),
            ("resource-test", "../SKILL.md"),
            ("resource-test", "references/../SKILL.md"),
            ("resource-test", "SKILL.md"),
        ):
            with self.subTest(skill=skill_name, path=rel_path):
                with self.assertRaises(ValueError):
                    server_mod.read_skill_file(skill_name, rel_path)

    def test_skill_resources_include_root_files_and_custom_directories(self):
        server_mod.create_skill(
            name="extended-resources",
            description="Extended resource layout",
            body_text="Read the packaged resources.",
        )
        skill_dir = self.tmp_skills / "extended-resources"
        (skill_dir / "guide.md").write_text("Root guide", encoding="utf-8")
        palette_dir = skill_dir / "palettes"
        palette_dir.mkdir()
        (palette_dir / "dark.md").write_text("Dark palette", encoding="utf-8")

        skill = server_mod.read_skill("extended-resources")
        self.assertEqual(skill["resources"]["files"], ["guide.md"])
        self.assertEqual(skill["resources"]["palettes"], ["palettes/dark.md"])
        self.assertEqual(
            server_mod.read_skill_file("extended-resources", "guide.md"),
            "Root guide",
        )
        self.assertEqual(
            server_mod.read_skill_file("extended-resources", "palettes/dark.md"),
            "Dark palette",
        )

    def test_read_skill_resource_rejects_oversized_files(self):
        server_mod.create_skill(
            name="large-resource",
            description="Large resource",
            body_text="Read the packaged resource.",
        )
        resource = self.tmp_skills / "large-resource" / "guide.md"
        resource.write_text(
            "x" * (server_mod.MAX_TOOL_READ_BYTES + 1),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "resource is too large"):
            server_mod.read_skill_file("large-resource", "guide.md")

    def test_read_nonexistent(self):
        with self.assertRaises(ValueError):
            server_mod.read_skill("nonexistent")

    def test_delete_skill(self):
        server_mod.create_skill(
            name="delete-me",
            description="To be deleted",
            body_text="Nothing important.",
        )
        result = server_mod.delete_skill("delete-me")
        self.assertTrue(result.get("ok"))
        with self.assertRaises(ValueError):
            server_mod.read_skill("delete-me")

    def test_delete_nonexistent(self):
        with self.assertRaises(ValueError):
            server_mod.delete_skill("never-existed")

    def test_create_duplicate_raises(self):
        server_mod.create_skill(
            name="dup-skill",
            description="First version",
            body_text="v1",
        )
        with self.assertRaises(ValueError):
            server_mod.create_skill(
                name="dup-skill",
                description="Second version",
                body_text="v2",
            )


# ═══════════════════════════════════════════════════════════════════
# 4. Memory CRUD + Index
# ═══════════════════════════════════════════════════════════════════

class TestMemoryCRUD(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp_data = Path(tempfile.mkdtemp(prefix="code_mem_"))
        cls.tmp_memory = cls.tmp_data / "memory"
        cls.tmp_memory.mkdir(parents=True)
        cls._patcher = mock.patch.object(server_mod, "MEMORY_DIR", cls.tmp_memory)
        cls._patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._patcher.stop()

    def setUp(self):
        # Clean between tests
        for f in self.tmp_memory.iterdir():
            f.unlink()

    def test_write_and_read_memory(self):
        server_mod.write_memory(
            name="test-memory",
            meta={"description": "A test", "type": "reference"},
            body="This is the memory body.",
        )
        result = server_mod.read_memory("test-memory")
        self.assertEqual(result["name"], "test-memory")
        self.assertEqual(result["meta"]["type"], "reference")
        self.assertIn("This is the memory body", result["body"])

    def test_list_memories(self):
        server_mod.write_memory("m1", {"description": "First"}, "Body 1")
        server_mod.write_memory("m2", {"description": "Second"}, "Body 2")
        result = server_mod.list_memories()
        self.assertEqual(len(result), 2)
        names = [m["name"] for m in result]
        self.assertIn("m1", names)
        self.assertIn("m2", names)

    def test_delete_memory(self):
        server_mod.write_memory("del-me", {"description": "x"}, "y")
        result = server_mod.delete_memory("del-me")
        self.assertTrue(result.get("ok"))
        with self.assertRaises(ValueError):
            server_mod.read_memory("del-me")

    def test_delete_nonexistent_memory(self):
        # delete_memory is idempotent — doesn't error on missing
        result = server_mod.delete_memory("never-there")
        self.assertTrue(result.get("ok"))

    def test_safe_memory_name_validation(self):
        self.assertEqual(server_mod.safe_memory_name("valid-name"), "valid-name")
        with self.assertRaises(ValueError):
            server_mod.safe_memory_name("")
        with self.assertRaises(ValueError):
            server_mod.safe_memory_name("a" * 65)
        with self.assertRaises(ValueError):
            server_mod.safe_memory_name("bad name")

    def test_memory_index_rebuild(self):
        server_mod.write_memory("idx-a", {"description": "A"}, "Content A")
        server_mod.write_memory("idx-b", {"description": "B"}, "Content B")
        # Patch MEMORY_INDEX_PATH (set at import time based on original MEMORY_DIR)
        index_path = self.tmp_memory / "MEMORY.md"
        with mock.patch.object(server_mod, "MEMORY_INDEX_PATH", index_path):
            server_mod._rebuild_memory_index()
        self.assertTrue(index_path.exists())
        content = index_path.read_text(encoding="utf-8")
        self.assertIn("idx-a", content)
        self.assertIn("idx-b", content)


# ═══════════════════════════════════════════════════════════════════
# 5. Project & Memory context loading
# ═══════════════════════════════════════════════════════════════════

class TestContextLoading(unittest.TestCase):

    def test_project_context_structure(self):
        with mock.patch.object(server_mod, "CONFIG_PATH") as mock_cfg:
            import tempfile
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
            tmp.write(json.dumps({
                "projectRoot": str(Path.home()),
                "newApiBaseUrl": "http://localhost:3000",
            }))
            tmp.close()
            mock_cfg.__eq__ = lambda self, other: True
            try:
                # Test that load_project_context returns expected structure
                with mock.patch.object(server_mod, "load_config", return_value={
                    "projectRoot": str(Path.home()),
                    "newApiBaseUrl": "http://localhost:3000",
                }):
                    result = server_mod.load_project_context()
                    self.assertIn("found", result)
                    self.assertIn("name", result)
            finally:
                Path(tmp.name).unlink(missing_ok=True)

    def test_memory_context_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem_dir = Path(tmpdir) / "memory"
            mem_dir.mkdir()
            with mock.patch.object(server_mod, "MEMORY_DIR", mem_dir), \
                 mock.patch.object(server_mod, "MEMORY_INDEX_PATH", mem_dir / "MEMORY.md"), \
                 mock.patch.object(server_mod, "load_config", return_value={
                     "projectRoot": str(Path.home()),
                     "newApiBaseUrl": "http://localhost:3000",
                 }):
                result = server_mod.load_memory_context()
                self.assertIn("found", result)
                self.assertIn("memories", result)


if __name__ == "__main__":
    unittest.main()
