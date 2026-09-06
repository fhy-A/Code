import http.client
from http.server import ThreadingHTTPServer
import json
import threading
import time
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import server as server_mod
from code_runtime import skill_activation
from code_runtime.skill_activation import (
    DELEGATION_BEGIN_MARKER,
    DELEGATION_END_MARKER,
    SKILL_PROMPT_MARKER,
    SkillActivationError,
    normalize_activation_request,
    prepare_skill_activation,
)


def _write_skill(
    root,
    name,
    *,
    declared_name=None,
    description="Test Skill",
    keywords="",
    allowed_tools="",
    legacy_tools="",
    body="Follow the selected instructions.",
    evidence=None,
):
    directory = Path(root) / name
    directory.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"name: {declared_name or name}", f"description: {description}"]
    if keywords:
        lines.append(f"keywords: {keywords}")
    if allowed_tools:
        lines.append(f"allowed-tools: {allowed_tools}")
    if legacy_tools:
        lines.append(f"tools: {legacy_tools}")
    lines.extend(["---", "", body])
    (directory / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")
    if evidence is not None:
        (directory / "evidence.json").write_text(
            json.dumps(evidence), encoding="utf-8",
        )
    return directory


def _messages(*, task=True):
    parts = ["base"]
    if task:
        parts.append(
            f"{DELEGATION_BEGIN_MARKER}\ndelegation rules\n{DELEGATION_END_MARKER}"
        )
    parts.extend([SKILL_PROMPT_MARKER, "permission"])
    return [
        {"role": "system", "content": "\n\n".join(parts)},
        {"role": "user", "content": "Use alpha for this task"},
    ]


def _estimate(text):
    return server_mod._agent_estimate_text_tokens(text)


class TestCanonicalSkillActivation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="code_skill_activation_")
        self.root = Path(self.temp.name)
        self.installed = self.root / "installed"
        self.bundled = self.root / "bundled"
        self.installed.mkdir()
        self.bundled.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def _prepare(self, *, explicit="alpha", disabled=None, tools=None, tokens=100_000):
        initial_tools = tools or ["read_file", "write_file", "task"]
        return prepare_skill_activation(
            messages=_messages(task="task" in initial_tools),
            user_message="Use alpha for this task",
            request={
                "schemaVersion": 1,
                "explicitSkill": explicit,
                "disabledNames": disabled or [],
            },
            installed_skills_dir=self.installed,
            bundled_skills_dir=self.bundled,
            initial_tool_names=initial_tools,
            available_input_tokens=tokens,
            estimate_tokens=_estimate,
        )

    def test_intent_is_strict_and_explicit_unavailable_fails_closed(self):
        with self.assertRaisesRegex(SkillActivationError, "invalid"):
            normalize_activation_request({
                "schemaVersion": 1,
                "explicitSkill": "alpha",
                "disabledNames": [],
                "owner": "client-value",
            })
        with self.assertRaises(SkillActivationError):
            normalize_activation_request({
                "schemaVersion": 1.0,
                "explicitSkill": "alpha",
                "disabledNames": [],
            })
        _write_skill(self.installed, "alpha")
        with self.assertRaisesRegex(SkillActivationError, "unavailable") as raised:
            self._prepare(disabled=["alpha"])
        self.assertEqual(raised.exception.code, "activation_explicit_skill_unavailable")

    def test_explicit_body_and_evidence_are_captured_and_tools_only_narrow(self):
        evidence = {
            "schemaVersion": 1,
            "requirements": [{
                "id": "inspect-source",
                "type": "tool_execution",
                "tool": "read_file",
                "minCount": 1,
            }],
        }
        _write_skill(
            self.installed,
            "alpha",
            allowed_tools="read_file",
            body="ALPHA_SELECTED_BODY",
            evidence=evidence,
        )
        _write_skill(
            self.installed,
            "unused",
            keywords="unused",
            body="UNSELECTED_BODY_MUST_NOT_APPEAR",
        )
        result = self._prepare()
        self.assertEqual(result["activeSkillNames"], ["alpha"])
        self.assertEqual(result["toolNames"], ["read_file"])
        self.assertNotIn("delegation rules", result["messages"][0]["content"])
        self.assertIn("ALPHA_SELECTED_BODY", result["messages"][0]["content"])
        self.assertNotIn("UNSELECTED_BODY_MUST_NOT_APPEAR", result["messages"][0]["content"])
        self.assertEqual(result["captures"][0]["evidence"], evidence)
        self.assertNotIn(SKILL_PROMPT_MARKER, result["messages"][0]["content"])

    def test_automatic_no_match_disabled_and_reference_tie_load_no_bodies(self):
        for name in ("alpha", "beta", "gamma"):
            _write_skill(
                self.installed,
                name,
                keywords="shared-keyword",
                body=f"PRIVATE_{name.upper()}_BODY",
            )
        tied = prepare_skill_activation(
            messages=_messages(task=False),
            user_message="shared-keyword",
            request={"schemaVersion": 1, "explicitSkill": "", "disabledNames": []},
            installed_skills_dir=self.installed,
            bundled_skills_dir=self.bundled,
            initial_tool_names=["read_file"],
            available_input_tokens=100_000,
            estimate_tokens=_estimate,
        )
        self.assertEqual(tied["activeSkillNames"], [])
        self.assertEqual(tied["captures"], [])
        self.assertEqual(len(tied["references"]), 2)
        self.assertTrue(all("BODY" not in str(item) for item in tied["references"]))
        self.assertNotIn("PRIVATE_", tied["messages"][0]["content"])
        self.assertNotIn(SKILL_PROMPT_MARKER, tied["messages"][0]["content"])

        disabled = prepare_skill_activation(
            messages=_messages(task=False),
            user_message="alpha",
            request={"schemaVersion": 1, "explicitSkill": "", "disabledNames": ["alpha"]},
            installed_skills_dir=self.installed,
            bundled_skills_dir=self.bundled,
            initial_tool_names=["read_file"],
            available_input_tokens=100_000,
            estimate_tokens=_estimate,
        )
        self.assertEqual(disabled["activeSkillNames"], [])
        self.assertEqual(disabled["toolNames"], ["read_file"])

    def test_automatic_owner_modifier_order_and_task_policy(self):
        _write_skill(self.installed, "pdf", body="PDF_OWNER")
        _write_skill(self.installed, "document-design", body="DESIGN_MODIFIER")
        result = prepare_skill_activation(
            messages=_messages(),
            user_message="请美化并编辑 report.pdf",
            request={"schemaVersion": 1, "explicitSkill": "", "disabledNames": []},
            installed_skills_dir=self.installed,
            bundled_skills_dir=self.bundled,
            initial_tool_names=["read_file", "task"],
            available_input_tokens=100_000,
            estimate_tokens=_estimate,
        )
        self.assertEqual(result["activeSkillNames"], ["pdf", "document-design"])
        self.assertLess(
            result["messages"][0]["content"].index("PDF_OWNER"),
            result["messages"][0]["content"].index("DESIGN_MODIFIER"),
        )
        self.assertNotIn("task", result["toolNames"])
        self.assertNotIn("delegation rules", result["messages"][0]["content"])

        _write_skill(
            self.installed, "delegate", keywords="delegate", legacy_tools="read_file",
        )
        delegated = prepare_skill_activation(
            messages=_messages(),
            user_message="请用子 agent delegate 完成",
            request={"schemaVersion": 1, "explicitSkill": "", "disabledNames": []},
            installed_skills_dir=self.installed,
            bundled_skills_dir=self.bundled,
            initial_tool_names=["read_file", "task"],
            available_input_tokens=100_000,
            estimate_tokens=_estimate,
        )
        self.assertEqual(delegated["activeSkillNames"], ["delegate"])
        self.assertIn("task", delegated["toolNames"])
        self.assertIn("delegation rules", delegated["messages"][0]["content"])
        self.assertNotIn(DELEGATION_BEGIN_MARKER, delegated["messages"][0]["content"])

    def test_name_conflict_and_damaged_explicit_owner_fail_closed(self):
        _write_skill(self.installed, "one", declared_name="alpha")
        _write_skill(self.installed, "two", declared_name="alpha")
        with self.assertRaises(SkillActivationError) as raised:
            self._prepare()
        self.assertEqual(raised.exception.code, "activation_explicit_skill_unavailable")

        for child in self.installed.iterdir():
            for path in child.iterdir():
                path.unlink()
            child.rmdir()
        _write_skill(
            self.installed,
            "alpha",
            body="x" * (skill_activation.MAX_BODY_BYTES + 1),
        )
        with self.assertRaises(SkillActivationError) as raised:
            self._prepare()
        self.assertEqual(raised.exception.code, "activation_body_too_large")

    def test_selected_bytes_changing_after_resolution_are_rejected(self):
        skill_dir = _write_skill(self.installed, "alpha", body="ORIGINAL")
        real_resolve = skill_activation.resolve_skill_shadow

        def mutate_after_resolve(*args, **kwargs):
            resolution = real_resolve(*args, **kwargs)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: alpha\ndescription: Test Skill\n---\n\nCHANGED",
                encoding="utf-8",
            )
            return resolution

        with mock.patch.object(
            skill_activation, "resolve_skill_shadow", side_effect=mutate_after_resolve,
        ):
            with self.assertRaises(SkillActivationError) as raised:
                self._prepare()
        self.assertEqual(raised.exception.code, "activation_skill_changed")

    def test_selected_bytes_changing_during_dependency_capture_are_rejected(self):
        skill_dir = _write_skill(self.installed, "alpha", body="ORIGINAL")
        real_resolve = skill_activation.resolve_skill_manifest

        def mutate_during_dependencies(*args, **kwargs):
            manifest = real_resolve(*args, **kwargs)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: alpha\ndescription: Test Skill\n---\n\nCHANGED",
                encoding="utf-8",
            )
            return manifest

        with mock.patch.object(
            skill_activation,
            "resolve_skill_manifest",
            side_effect=mutate_during_dependencies,
        ):
            with self.assertRaises(SkillActivationError) as raised:
                self._prepare()
        self.assertEqual(raised.exception.code, "activation_skill_changed")

    def test_optional_modifier_failure_excludes_modifier_but_keeps_owner(self):
        _write_skill(self.installed, "pdf", body="PDF_OWNER")
        _write_skill(
            self.installed,
            "document-design",
            body="x" * (skill_activation.MAX_BODY_BYTES + 1),
        )
        result = prepare_skill_activation(
            messages=_messages(),
            user_message="请美化并编辑 report.pdf",
            request={"schemaVersion": 1, "explicitSkill": "", "disabledNames": []},
            installed_skills_dir=self.installed,
            bundled_skills_dir=self.bundled,
            initial_tool_names=["read_file", "task"],
            available_input_tokens=100_000,
            estimate_tokens=_estimate,
        )
        self.assertEqual(result["activeSkillNames"], ["pdf"])
        self.assertEqual(result["exclusions"], [{
            "name": "document-design",
            "reasonCode": "activation_body_too_large",
        }])
        self.assertIn("PDF_OWNER", result["messages"][0]["content"])

    def test_owner_budget_and_prompt_marker_fail_closed(self):
        _write_skill(self.installed, "alpha", body="token " * 800)
        with self.assertRaises(SkillActivationError) as raised:
            self._prepare(tokens=1_024)
        self.assertEqual(raised.exception.code, "activation_instruction_too_large")
        messages = _messages(task=False)
        messages[0]["content"] = "base without marker"
        with self.assertRaises(SkillActivationError) as raised:
            prepare_skill_activation(
                messages=messages,
                user_message="alpha",
                request={"schemaVersion": 1, "explicitSkill": "alpha", "disabledNames": []},
                installed_skills_dir=self.installed,
                bundled_skills_dir=self.bundled,
                initial_tool_names=[],
                available_input_tokens=100_000,
                estimate_tokens=_estimate,
            )
        self.assertEqual(raised.exception.code, "activation_prompt_marker_invalid")

        messages = _messages(task=False)
        messages.append({
            "role": "user",
            "content": [{"type": "text", "text": SKILL_PROMPT_MARKER}],
        })
        with self.assertRaises(SkillActivationError) as raised:
            prepare_skill_activation(
                messages=messages,
                user_message="alpha",
                request={"schemaVersion": 1, "explicitSkill": "alpha", "disabledNames": []},
                installed_skills_dir=self.installed,
                bundled_skills_dir=self.bundled,
                initial_tool_names=[],
                available_input_tokens=100_000,
                estimate_tokens=_estimate,
            )
        self.assertEqual(raised.exception.code, "activation_prompt_marker_invalid")

    def test_missing_installed_registry_root_fails_instead_of_becoming_no_match(self):
        missing = self.root / "missing"
        with self.assertRaises(SkillActivationError) as raised:
            prepare_skill_activation(
                messages=_messages(task=False),
                user_message="no match",
                request={"schemaVersion": 1, "explicitSkill": "", "disabledNames": []},
                installed_skills_dir=missing,
                bundled_skills_dir=self.bundled,
                initial_tool_names=[],
                available_input_tokens=100_000,
                estimate_tokens=_estimate,
            )
        self.assertEqual(raised.exception.code, "activation_registry_unavailable")

    def test_registry_entry_budget_stops_before_building_snapshot(self):
        for index in range(skill_activation.MAX_REGISTRY_ENTRIES + 1):
            (self.installed / f"skill-{index}").mkdir()
        with mock.patch.object(skill_activation, "build_skill_registry_snapshot") as build:
            with self.assertRaises(SkillActivationError) as raised:
                prepare_skill_activation(
                    messages=_messages(task=False),
                    user_message="no match",
                    request={"schemaVersion": 1, "explicitSkill": "", "disabledNames": []},
                    installed_skills_dir=self.installed,
                    bundled_skills_dir=self.bundled,
                    initial_tool_names=[],
                    available_input_tokens=100_000,
                    estimate_tokens=_estimate,
                )
        self.assertEqual(raised.exception.code, "activation_registry_too_large")
        build.assert_not_called()


class TestCanonicalAgentRunAdmission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="code_skill_run_")
        self.data_dir = Path(self.temp.name) / "data"
        self.skills_dir = self.data_dir / "skills"
        self.skills_dir.mkdir(parents=True)
        skill_dir = _write_skill(
            self.skills_dir,
            "alpha",
            allowed_tools="read_file",
            body="SERVER_CAPTURED_ALPHA",
            evidence={
                "schemaVersion": 1,
                "requirements": [{
                    "id": "inspect-source",
                    "type": "tool_execution",
                    "tool": "read_file",
                    "minCount": 1,
                }],
            },
        )
        (skill_dir / "dependencies.json").write_text(json.dumps({
            "schemaVersion": 1,
            "skill": "alpha",
            "capabilities": {"inspect": {"required": [], "optional": []}},
        }), encoding="utf-8")
        self.patchers = [
            mock.patch.object(server_mod, "DATA_DIR", self.data_dir),
            mock.patch.object(server_mod, "SKILLS_DIR", self.skills_dir),
            # This class exercises the explicitly selected mutable v5 protocol.
            mock.patch.object(server_mod, "_SKILL_IMMUTABLE_ADMISSION_ENABLED", False),
            mock.patch.object(server_mod, "_SKILL_ACTIVATION_ENABLED", True),
            mock.patch.object(server_mod, "_MODEL_ROUTE_REGISTRY_ENABLED", False),
        ]
        for patcher in self.patchers:
            patcher.start()
        with server_mod._agent_run_lock:
            server_mod._agent_runs.clear()

    def tearDown(self):
        with server_mod._agent_run_lock:
            server_mod._agent_runs.clear()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp.cleanup()

    @staticmethod
    def _context():
        return {
            "contextLimit": 128_000,
            "contextWindowTokens": 128_000,
            "contextBudgetTokens": None,
            "contextWindowSource": "test",
            "contextWindowHard": False,
            "availableInputTokens": 100_000,
            "compressionTriggerTokens": 90_000,
            "budgetClamped": False,
            "budgetAboveEstimate": False,
        }

    def _create(
        self,
        request_id="canonical-request",
        *,
        start_worker=False,
        allowed_tools=None,
        activation_request=None,
    ):
        return server_mod._create_agent_run(
            "",
            {
                "model": "test-model",
                "messages": _messages(task=False),
            },
            "http://127.0.0.1:1",
            [],
            allowed_tools=(
                {"schemaVersion": 1, "names": ["read_file"]}
                if allowed_tools is None else allowed_tools
            ),
            permission_profile="read",
            start_worker=start_worker,
            client_request_id=request_id,
            inherited_context=self._context(),
            run_kind="foreground",
            skill_activation_request=(
                {
                    "schemaVersion": 1,
                    "explicitSkill": "alpha",
                    "disabledNames": [],
                }
                if activation_request is None else activation_request
            ),
        )

    def test_flag_resolver_defaults_off_and_legacy_request_bypasses_canonical(self):
        self.assertFalse(server_mod._resolve_skill_activation_enabled({}))
        self.assertTrue(server_mod._resolve_skill_activation_enabled({
            "CODE_SKILL_ACTIVATION_V1": "true",
        }))
        with mock.patch.object(
            server_mod,
            "prepare_skill_activation",
            side_effect=AssertionError("canonical path must stay unreachable"),
        ):
            run = server_mod._create_agent_run(
                "",
                {"model": "test-model", "messages": [{"role": "user", "content": "legacy"}]},
                "http://127.0.0.1:1",
                [],
                allowed_tools=[],
                permission_profile="read",
                start_worker=False,
                active_skill_name="alpha",
                active_skill_names=["alpha"],
                inherited_context=self._context(),
                run_kind="foreground",
            )
        self.assertEqual(run["messages"], [{"role": "user", "content": "legacy"}])
        self.assertEqual(run["active_skill_names"], ["alpha"])
        legacy_record = server_mod._agent_run_record(run)
        self.assertEqual(legacy_record["version"], 5)
        self.assertNotIn("skillLifecycle", legacy_record)
        self.assertNotIn("skillLifecycle", server_mod._agent_snapshot(run, 0))

    def test_malformed_canonical_envelopes_fail_before_worker(self):
        with mock.patch.object(server_mod, "_start_agent_worker") as start_worker:
            with self.assertRaises(SkillActivationError) as raised:
                self._create("bad-tools", start_worker=True, allowed_tools=[])
            self.assertEqual(raised.exception.code, "activation_tool_envelope_invalid")
            with self.assertRaises(SkillActivationError) as raised:
                self._create("bad-intent", start_worker=True, activation_request={
                    "schemaVersion": 1,
                    "explicitSkill": "alpha",
                    "disabledNames": [],
                    "contentHash": "client-owned",
                })
            self.assertEqual(raised.exception.code, "activation_intent_invalid")
        start_worker.assert_not_called()

    def test_http_capability_and_create_contract_are_additive_and_fail_closed(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.CodeHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        def request(method, path, body=None):
            connection = http.client.HTTPConnection(
                "127.0.0.1", httpd.server_address[1], timeout=5,
            )
            encoded = json.dumps(body).encode("utf-8") if body is not None else None
            connection.request(
                method,
                path,
                body=encoded,
                headers={"Content-Type": "application/json"} if encoded else {},
            )
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            status = response.status
            connection.close()
            return status, payload

        def create_body(request_id, *, canonical=True, malformed_tools=False):
            body = {
                "sessionId": "",
                "clientRequestId": request_id,
                "payload": {
                    "model": "test-model",
                    "messages": _messages(task=False) if canonical else [
                        {"role": "user", "content": "legacy request"},
                    ],
                },
                "baseUrl": "http://127.0.0.1:1",
                "keys": [],
                "allowedTools": [] if malformed_tools or not canonical else {
                    "schemaVersion": 1,
                    "names": [],
                },
                "permissionProfile": "read",
                "runKind": "foreground",
            }
            if canonical:
                body["skillActivationRequest"] = {
                    "schemaVersion": 1,
                    "explicitSkill": "alpha",
                    "disabledNames": [],
                }
                body["skillLifecycle"] = {
                    "schemaVersion": 999,
                    "mode": "client-owned-must-be-ignored",
                }
            return body

        try:
            with mock.patch.object(server_mod, "_SKILL_ACTIVATION_ENABLED", False):
                status, heartbeat = request("GET", "/api/browser-heartbeat")
                self.assertEqual(status, 200)
                self.assertNotIn("skillActivationProtocol", heartbeat)
            status, heartbeat = request("GET", "/api/browser-heartbeat")
            self.assertEqual(status, 200)
            self.assertEqual(heartbeat["skillActivationProtocol"], "canonical-v1")
            with mock.patch.object(server_mod, "_start_agent_worker") as start_worker:
                status, canonical = request(
                    "POST", "/api/agent/runs", create_body("http-canonical"),
                )
                self.assertEqual(status, 201)
                self.assertEqual(canonical["activeSkillNames"], ["alpha"])
                canonical_run = server_mod._get_agent_run(canonical["agentRunId"])
                self.assertEqual(canonical_run["skill_lifecycle"]["schemaVersion"], 1)
                self.assertEqual(canonical_run["skill_lifecycle"]["mode"], "canonical-v1")
                lifecycle_evidence = canonical_run["skill_lifecycle"]["activation"]["selected"][0]["evidence"]
                self.assertEqual(lifecycle_evidence["state"], "invalid")
                self.assertNotIn("contract", lifecycle_evidence)
                invalid_restored = server_mod._agent_run_from_record(
                    server_mod._agent_run_record(canonical_run)
                )
                self.assertEqual(
                    invalid_restored["skill_evidence_observers"][0]["contractState"],
                    "invalid",
                )
                status, legacy = request(
                    "POST", "/api/agent/runs", create_body("http-legacy", canonical=False),
                )
                self.assertEqual(status, 201)
                self.assertNotIn("activeSkillNames", legacy)
                status, malformed = request(
                    "POST",
                    "/api/agent/runs",
                    create_body("http-malformed", malformed_tools=True),
                )
                self.assertEqual(status, 409)
                self.assertEqual(
                    malformed["errorCode"], "activation_tool_envelope_invalid",
                )
                null_intent = create_body("http-null-intent", canonical=False)
                null_intent["skillActivationRequest"] = None
                status, malformed = request(
                    "POST", "/api/agent/runs", null_intent,
                )
                self.assertEqual(status, 409)
                self.assertEqual(malformed["errorCode"], "activation_intent_invalid")
            self.assertEqual(start_worker.call_count, 2)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_canonical_run_remains_v5_and_freezes_authoritative_projection(self):
        with mock.patch.object(
            server_mod, "read_skill", side_effect=AssertionError("legacy read forbidden"),
        ):
            run = self._create()
        self.assertEqual(run["active_skill_names"], ["alpha"])
        self.assertIn("SERVER_CAPTURED_ALPHA", run["messages"][0]["content"])
        self.assertEqual(run["active_skill_dependencies"], {"alpha": ["inspect"]})
        self.assertEqual(run["skill_evidence_observers"][0]["contractState"], "valid")
        self.assertEqual(server_mod._agent_run_record(run)["version"], 5)
        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["activeSkillNames"], ["alpha"])

    def test_same_request_id_runs_activation_once_under_concurrency(self):
        real_prepare = server_mod.prepare_skill_activation
        entered = threading.Event()
        release = threading.Event()
        calls = []
        lifecycle = []
        persisted_lifecycles = []
        real_persist = server_mod._persist_agent_run

        def counted_prepare(**kwargs):
            calls.append(1)
            entered.set()
            release.wait(timeout=2)
            return real_prepare(**kwargs)

        def counted_persist(run):
            lifecycle.append("persist")
            persisted_lifecycles.append(
                server_mod._agent_run_record(run).get("skillLifecycle")
            )
            return real_persist(run)

        def counted_start(run):
            lifecycle.append("worker")
            return object()

        results = []
        errors = []

        def create():
            try:
                results.append(self._create("same-request", start_worker=True))
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        with mock.patch.object(
            server_mod, "prepare_skill_activation", side_effect=counted_prepare,
        ), mock.patch.object(
            server_mod, "_persist_agent_run", side_effect=counted_persist,
        ), mock.patch.object(
            server_mod, "_start_agent_worker", side_effect=counted_start,
        ):
            first = threading.Thread(target=create)
            second = threading.Thread(target=create)
            first.start()
            self.assertTrue(entered.wait(timeout=2))
            second.start()
            time.sleep(0.05)
            release.set()
            first.join(timeout=3)
            second.join(timeout=3)
        self.assertEqual(errors, [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(results), 2)
        self.assertIs(results[0], results[1])
        self.assertEqual(lifecycle, ["persist", "worker"])
        self.assertEqual(len(persisted_lifecycles), 1)
        self.assertEqual(persisted_lifecycles[0]["schemaVersion"], 1)

    def test_persisted_retry_and_reload_do_not_reread_registry_or_skill(self):
        original = self._create("durable-retry")
        original_record = server_mod._agent_run_record(original)
        self.assertEqual(original_record["version"], 5)
        self.assertIn("SERVER_CAPTURED_ALPHA", original_record["messages"][0]["content"])
        with server_mod._agent_run_lock:
            server_mod._agent_runs.clear()
        with mock.patch.object(
            server_mod,
            "prepare_skill_activation",
            side_effect=AssertionError("persisted retry must not resolve Skills"),
        ), mock.patch.object(
            server_mod,
            "read_skill",
            side_effect=AssertionError("persisted retry must not read Skills"),
        ), mock.patch.object(server_mod, "_SKILL_ACTIVATION_ENABLED", False):
            restored = self._create("durable-retry")
        self.assertEqual(restored["id"], original["id"])
        self.assertEqual(restored["messages"], original["messages"])
        self.assertEqual(restored["active_skill_names"], ["alpha"])
        self.assertEqual(restored["skill_lifecycle"], original_record["skillLifecycle"])

    def test_flag_off_rejects_new_canonical_run_without_legacy_fallback(self):
        with mock.patch.object(server_mod, "_SKILL_ACTIVATION_ENABLED", False):
            with mock.patch.object(server_mod, "_freeze_skill_evidence_observers") as legacy, mock.patch.object(
                server_mod, "_start_agent_worker",
            ) as start_worker:
                with self.assertRaises(SkillActivationError) as raised:
                    self._create("flag-off", start_worker=True)
        self.assertEqual(raised.exception.code, "activation_protocol_disabled")
        legacy.assert_not_called()
        start_worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
