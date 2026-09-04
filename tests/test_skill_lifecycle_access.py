"""Active-only access continuity for canonical Skill lifecycle records."""

import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest import mock

import server as server_mod
from code_runtime import skill_lifecycle
from code_runtime.skill_activation import SKILL_PROMPT_MARKER


def _sha(label):
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


_DELETE = object()


def _variant(source, path, value):
    result = copy.deepcopy(source)
    parent = result
    for component in path[:-1]:
        parent = parent[component]
    if value is _DELETE:
        del parent[path[-1]]
    else:
        parent[path[-1]] = value
    return result


def _lifecycle():
    return skill_lifecycle.normalize_skill_lifecycle({
        "schemaVersion": 1,
        "mode": "canonical-v1",
        "activation": {
            "schemaVersion": 1,
            "intentKind": "explicit",
            "outcome": "activated",
            "selected": [{
                "name": "alpha",
                "role": "owner",
                "source": {
                    "kind": "installed",
                    "directory": "alpha-dir",
                    "descriptorId": "sd1_" + hashlib.sha256(b"alpha").hexdigest(),
                },
                "skillContentHash": _sha("skill"),
                "evidence": {"state": "missing"},
                "dependency": {"state": "missing", "capabilities": []},
                "resources": {"state": "missing"},
            }],
        },
        "access": {"schemaVersion": 2, "resourceBindings": []},
    })


class TestSkillLifecycleAccessContract(unittest.TestCase):
    def test_text_binding_is_canonical_idempotent_and_change_rejecting(self):
        lifecycle = _lifecycle()

        bound = skill_lifecycle.bind_text_resource(
            lifecycle, "alpha", "references/guide.md", _sha("guide-v1"),
        )
        repeated = skill_lifecycle.bind_text_resource(
            bound, "alpha", "references/guide.md", _sha("guide-v1"),
        )
        alias = skill_lifecycle.bind_text_resource(
            bound, "alpha", "REFERENCES/GUIDE.MD", _sha("guide-v1"),
        )

        self.assertEqual(bound, repeated)
        self.assertEqual(bound, alias)
        self.assertEqual(bound["access"], {
            "schemaVersion": 2,
            "resourceBindings": [{
                "kind": "text",
                "skill": "alpha",
                "file": "references/guide.md",
                "contentHash": _sha("guide-v1"),
            }],
        })
        with self.assertRaises(skill_lifecycle.SkillLifecycleError) as raised:
            skill_lifecycle.bind_text_resource(
                copy.deepcopy(bound), "alpha", "references/guide.md", _sha("guide-v2"),
            )
        self.assertEqual(raised.exception.code, "skill_lifecycle_reference_changed")
        with self.assertRaises(skill_lifecycle.SkillLifecycleError) as alias_changed:
            skill_lifecycle.bind_text_resource(
                bound, "alpha", "REFERENCES/GUIDE.MD", _sha("guide-v2"),
            )
        self.assertEqual(
            alias_changed.exception.code, "skill_lifecycle_reference_changed",
        )

    def test_access_v1_empty_record_remains_readable_and_upgrades_on_bind(self):
        lifecycle = _lifecycle()
        lifecycle["access"] = {"schemaVersion": 1, "resourceBindings": []}

        normalized = skill_lifecycle.normalize_skill_lifecycle(lifecycle)
        upgraded = skill_lifecycle.bind_text_resource(
            normalized, "alpha", "notes.txt", _sha("notes"),
        )

        self.assertEqual(normalized["access"]["schemaVersion"], 1)
        self.assertEqual(upgraded["access"]["schemaVersion"], 2)

    def test_bindings_are_bounded_unique_and_deterministically_sorted(self):
        lifecycle = _lifecycle()
        for index in reversed(range(skill_lifecycle.MAX_RESOURCE_BINDINGS)):
            lifecycle = skill_lifecycle.bind_text_resource(
                lifecycle, "alpha", f"references/{index:02d}.txt", _sha(str(index)),
            )
        files = [item["file"] for item in lifecycle["access"]["resourceBindings"]]
        self.assertEqual(files, sorted(files))
        self.assertEqual(len(files), skill_lifecycle.MAX_RESOURCE_BINDINGS)

        repeated = skill_lifecycle.bind_text_resource(
            lifecycle, "alpha", "references/00.txt", _sha("0"),
        )
        self.assertEqual(repeated, lifecycle)
        with self.assertRaises(skill_lifecycle.SkillLifecycleError) as raised:
            skill_lifecycle.bind_text_resource(
                lifecycle, "alpha", "references/overflow.txt", _sha("overflow"),
            )
        self.assertEqual(raised.exception.code, "skill_lifecycle_reference_limit")

        duplicated = copy.deepcopy(lifecycle)
        duplicated["access"]["resourceBindings"].append(copy.deepcopy(
            duplicated["access"]["resourceBindings"][0]
        ))
        with self.assertRaises(skill_lifecycle.SkillLifecycleError):
            skill_lifecycle.normalize_skill_lifecycle(duplicated)

    def test_reference_paths_and_active_identity_fail_closed(self):
        invalid_paths = (
            "", "/absolute.txt", "../escape.txt", "refs/../escape.txt",
            ".hidden", "refs/.hidden", "refs/__pycache__/x.py", "refs/__PYCACHE__/x.py",
            "C:/drive.txt",
            "SKILL.md", "skill.MD", "guide.md.", "guide.md ", {"not": "text"},
        )
        for value in invalid_paths:
            with self.subTest(value=value):
                with self.assertRaises(skill_lifecycle.SkillLifecycleError) as raised:
                    skill_lifecycle.normalize_text_resource_path(value)
                self.assertEqual(raised.exception.code, "skill_lifecycle_reference_invalid")
        self.assertEqual(
            skill_lifecycle.normalize_text_resource_path("references\\guide.md"),
            "references/guide.md",
        )
        with self.assertRaises(skill_lifecycle.SkillLifecycleError) as raised:
            skill_lifecycle.bind_text_resource(
                _lifecycle(), "beta", "references/guide.md", _sha("guide"),
            )
        self.assertEqual(raised.exception.code, "skill_lifecycle_skill_not_active")

    def test_legacy_resource_identity_and_empty_access_are_read_only_compatible(self):
        lifecycle = _lifecycle()
        lifecycle["activation"]["selected"][0]["resources"] = {
            "state": "ready", "contractHash": _sha("legacy-resources"),
        }
        lifecycle["access"] = {"schemaVersion": 1, "resourceBindings": []}

        normalized = skill_lifecycle.normalize_skill_lifecycle(lifecycle)

        self.assertNotIn("source", normalized["activation"]["selected"][0]["resources"])
        self.assertEqual(normalized["access"]["schemaVersion"], 1)
        malformed = copy.deepcopy(normalized)
        malformed["access"]["schemaVersion"] = True
        with self.assertRaises(skill_lifecycle.SkillLifecycleError) as raised:
            skill_lifecycle.normalize_skill_lifecycle(malformed)
        self.assertEqual(
            raised.exception.code, "skill_lifecycle_access_version_unsupported",
        )


class TestCanonicalSkillAgentAccess(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="code_skill_access_")
        self.root = Path(self.temporary.name)
        self.data_dir = self.root / "data"
        self.skills_dir = self.data_dir / "skills"
        self.skills_dir.mkdir(parents=True)
        self.skill_dir = self._write_skill("alpha")
        self.patchers = [
            mock.patch.object(server_mod, "DATA_DIR", self.data_dir),
            mock.patch.object(server_mod, "SKILLS_DIR", self.skills_dir),
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
        self.temporary.cleanup()

    def _write_skill(self, name):
        skill_dir = self.skills_dir / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "\n".join([
                "---",
                f"name: {name}",
                "description: Canonical access test",
                "allowed-tools: use_skill, check_skill_dependencies, read_skill_resource, run_command",
                "---",
                "",
                "Use references/guide.md and the trusted helper when required.",
            ]),
            encoding="utf-8",
        )
        (skill_dir / "dependencies.json").write_text(json.dumps({
            "schemaVersion": 1,
            "skill": name,
            "capabilities": {"inspect": {"required": [], "optional": []}},
        }), encoding="utf-8")
        helper = skill_dir / "scripts" / "run.py"
        helper.parent.mkdir()
        helper.write_text("print('trusted helper')\n", encoding="utf-8")
        helper_hash = hashlib.sha256(
            helper.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        (skill_dir / "code-resources.json").write_text(json.dumps({
            "schemaVersion": 1,
            "skill": name,
            "resources": [{
                "id": "run-helper",
                "path": "scripts/run.py",
                "sha256": helper_hash,
                "kind": "python",
                "protocol": "skill-access-test/v1",
                "modelVisible": True,
                "arguments": ["<input>"],
            }],
        }), encoding="utf-8")
        references = skill_dir / "references"
        references.mkdir()
        (references / "guide.md").write_text("Pinned guide v1\n", encoding="utf-8")
        return skill_dir

    def _create_run(
        self, request_id="skill-access", *, explicit_skill="alpha", disabled_names=(),
        permission="read",
    ):
        return server_mod._create_agent_run(
            "",
            {
                "model": "test-model",
                "messages": [
                    {
                        "role": "system",
                        "content": f"base\n\n{SKILL_PROMPT_MARKER}\n\npermission",
                    },
                    {"role": "user", "content": "Use alpha for this task"},
                ],
            },
            "http://127.0.0.1:9",
            [],
            {
                "schemaVersion": 1,
                "names": [
                    "use_skill", "check_skill_dependencies", "read_skill_resource",
                    "run_command",
                ],
            },
            4,
            permission,
            start_worker=False,
            client_request_id=request_id,
            cwd=str(self.root),
            run_kind="foreground",
            skill_activation_request={
                "schemaVersion": 1,
                "explicitSkill": explicit_skill,
                "disabledNames": list(disabled_names),
            },
        )

    def _create_legacy_run(self, request_id="legacy-access", *, run_kind="foreground"):
        return server_mod._create_agent_run(
            "",
            {"model": "test-model", "messages": [{"role": "user", "content": "use alpha"}]},
            "http://127.0.0.1:9",
            [],
            ["use_skill", "check_skill_dependencies", "read_skill_resource"],
            4,
            "read",
            active_skill_names=["alpha"],
            active_skill_name="alpha",
            start_worker=False,
            client_request_id=request_id,
            cwd=str(self.root),
            run_kind=run_kind,
        )

    @staticmethod
    def _call(run, name, arguments, call_id):
        call = server_mod._normalize_agent_tool_calls(run, [{
            "index": 0,
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }], 1)[0]
        run["pending_tool_calls"] = [call]
        run["status"] = "tools"
        server_mod._execute_agent_pending_tools(run)
        return run["tool_executions"][call_id]["result"]

    @staticmethod
    def _ready_status(run, name, capability, runtime=None):
        snapshot = server_mod._agent_lifecycle_skill_snapshot(run, name)
        status = server_mod._agent_lifecycle_dependency_status(snapshot, capability)
        status["installGuidance"]["runtime"] = copy.deepcopy(runtime or {})
        return status

    def _managed_runtime(self, suffix):
        scripts = self.data_dir / "runtime" / "python" / "Scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        python = scripts / f"python-{suffix}.exe"
        python.write_bytes(b"synthetic managed python")
        node = self.data_dir / "runtime" / "node" / "node_modules"
        (node / ".bin").mkdir(parents=True, exist_ok=True)
        return {
            "python": {"source": "managed", "executable": str(python)},
            "node": {"source": "managed", "nodePath": str(node)},
        }

    def test_nonactive_skill_rejects_before_registry_or_skill_io(self):
        cases = (
            ("use_skill", {"name": "beta"}),
            ("check_skill_dependencies", {"name": "beta", "capability": "inspect"}),
            ("read_skill_resource", {"skill": "beta", "file": "/escape.txt"}),
        )
        for index, (action, arguments) in enumerate(cases):
            with self.subTest(action=action):
                run = self._create_run(f"nonactive-{index}")
                blockers = [
                    mock.patch.object(server_mod, "read_skill", side_effect=AssertionError("read")),
                    mock.patch.object(server_mod, "list_skills", side_effect=AssertionError("list")),
                    mock.patch.object(
                        server_mod, "resolve_skill_manifest", side_effect=AssertionError("manifest"),
                    ),
                    mock.patch.object(
                        server_mod, "resolve_skill_resources_with_identity",
                        side_effect=AssertionError("resources"),
                    ),
                    mock.patch.object(
                        server_mod, "_agent_runtime_path_safe", side_effect=AssertionError("path"),
                    ),
                ]
                for blocker in blockers:
                    blocker.start()
                try:
                    result = self._call(
                        run, action, arguments, f"nonactive-call-{index}",
                    )
                finally:
                    for blocker in reversed(blockers):
                        blocker.stop()
                self.assertFalse(result["ok"])
                self.assertEqual(result["errorCode"], "skill_lifecycle_skill_not_active")
                self.assertNotIn("Available", json.dumps(result))

        no_match = self._create_run(
            "no-match", explicit_skill="", disabled_names=("alpha",),
        )
        with mock.patch.object(
            server_mod, "resolve_skill_manifest", side_effect=AssertionError("manifest"),
        ), mock.patch.object(
            server_mod, "_agent_runtime_path_safe", side_effect=AssertionError("path"),
        ):
            rejected = self._call(
                no_match, "use_skill", {"name": "alpha"}, "no-match-call",
            )
        self.assertEqual(rejected["errorCode"], "skill_lifecycle_skill_not_active")

    def test_active_use_skill_returns_resources_and_dependencies_without_body(self):
        run = self._create_run("active-use")

        with mock.patch.object(
            server_mod, "read_skill", side_effect=AssertionError("must use frozen path"),
        ), mock.patch.object(
            server_mod, "list_skills", side_effect=AssertionError("must not enumerate"),
        ):
            result = self._call(run, "use_skill", {"name": "alpha"}, "active-use-call")

        self.assertTrue(result["ok"])
        self.assertTrue(result["alreadyActive"])
        self.assertEqual(set(result), {
            "ok", "action", "name", "alreadyActive", "runtimeResources", "dependencies",
            "runtimeBinding",
        })
        self.assertTrue(result["runtimeBinding"]["established"])
        self.assertEqual(result["runtimeResources"]["source"], "custom")
        self.assertEqual(
            result["dependencies"]["installGuidance"]["selectedCapability"],
            "inspect",
        )

    def test_canonical_dependency_check_binds_only_explicit_ready_capability(self):
        run = self._create_run("dependency-bind")
        result = self._call(
            run, "check_skill_dependencies",
            {"name": "alpha", "capability": "inspect"},
            "binding-call",
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["runtimeBinding"]["established"])
        self.assertEqual(
            run["skill_runtime_bindings"]["alpha"]["capability"], "inspect",
        )
        self.assertIn("skillRuntimeBindings", server_mod._agent_run_record(run))

    def test_command_preflight_uses_canonical_binding_without_name_discovery(self):
        run = self._create_run("preflight")
        checked = self._call(
            run, "check_skill_dependencies",
            {"name": "alpha", "capability": "inspect"},
            "preflight-check",
        )
        self.assertTrue(checked["ok"])
        self.assertTrue(checked["runtimeBinding"]["established"])
        with run["condition"]:
            run["status"] = "waiting_credentials"
            run["resume_status"] = "model"
        restored = server_mod._agent_run_from_record(
            server_mod._agent_run_record(run)
        )

        with mock.patch.object(
            server_mod, "read_skill", side_effect=AssertionError("must use frozen path"),
        ), mock.patch.object(
            server_mod, "list_skills", side_effect=AssertionError("must not enumerate"),
        ):
            prepared = server_mod._agent_prepare_skill_runtime_environment(restored)

        self.assertTrue(prepared["ok"])

    def test_multi_capability_selection_and_declared_replacement_rules(self):
        skill = self._write_skill("multi-bind")
        (skill / "dependencies.json").write_text(json.dumps({
            "schemaVersion": 1,
            "skill": "multi-bind",
            "capabilities": {
                "inspect": {"required": [], "optional": []},
                "render": {"required": [], "optional": []},
            },
        }), encoding="utf-8")
        run = self._create_run("multi-bind", explicit_skill="multi-bind")

        used = self._call(
            run, "use_skill", {"name": "multi-bind"}, "multi-use",
        )
        omitted = self._call(
            run, "check_skill_dependencies", {"name": "multi-bind"}, "multi-omitted",
        )
        self.assertNotIn("runtimeBinding", used)
        self.assertNotIn("runtimeBinding", omitted)
        self.assertEqual(run["skill_runtime_bindings"], {})

        first = self._call(
            run,
            "check_skill_dependencies",
            {"name": "multi-bind", "capability": "inspect"},
            "multi-inspect",
        )
        second = self._call(
            run,
            "check_skill_dependencies",
            {"name": "multi-bind", "capability": "render"},
            "multi-render",
        )
        invalid = self._call(
            run,
            "check_skill_dependencies",
            {"name": "multi-bind", "capability": "other"},
            "multi-invalid",
        )
        self.assertTrue(first["runtimeBinding"]["established"])
        self.assertTrue(second["runtimeBinding"]["established"])
        self.assertNotIn("runtimeBinding", invalid)
        self.assertEqual(
            run["skill_runtime_bindings"]["multi-bind"]["capability"], "render",
        )

    def test_nonready_dependency_result_cannot_create_or_replace_binding(self):
        run = self._create_run("not-ready-bind")
        ready = self._ready_status(run, "alpha", "inspect")
        unavailable = copy.deepcopy(ready)
        unavailable["status"] = "unavailable"
        unavailable["capabilities"][0]["status"] = "unavailable"
        unavailable["installGuidance"]["requiredMissing"] = [{"type": "python"}]
        with mock.patch.object(
            server_mod, "_agent_lifecycle_dependency_status", return_value=unavailable,
        ):
            result = self._call(
                run,
                "check_skill_dependencies",
                {"name": "alpha", "capability": "inspect"},
                "not-ready-call",
            )
        self.assertNotIn("runtimeBinding", result)
        self.assertEqual(run["skill_runtime_bindings"], {})

    def test_post_result_snapshot_io_failure_never_creates_binding(self):
        run = self._create_run("binding-snapshot-failure")
        status = self._ready_status(run, "alpha", "inspect")
        result = {
            "ok": True,
            "action": "check_skill_dependencies",
            "skill": "alpha",
            **status,
        }
        with mock.patch.object(
            server_mod, "_agent_lifecycle_skill_snapshot",
            side_effect=OSError("injected snapshot failure"),
        ):
            bound = server_mod._agent_bind_skill_runtime_from_result(
                run,
                "check_skill_dependencies",
                {"name": "alpha", "capability": "inspect"},
                result,
            )
        self.assertFalse(bound)
        self.assertEqual(run["skill_runtime_bindings"], {})

    def test_canonical_restore_rejects_every_binding_identity_conflict(self):
        run = self._create_run("restore-binding")
        self._call(
            run,
            "check_skill_dependencies",
            {"name": "alpha", "capability": "inspect"},
            "restore-binding-call",
        )
        with run["condition"]:
            run["status"] = "waiting_credentials"
            run["resume_status"] = "model"
        record = server_mod._agent_run_record(run)
        restored = server_mod._agent_run_from_record(copy.deepcopy(record))
        self.assertEqual(restored["skill_runtime_bindings"], run["skill_runtime_bindings"])

        binding_path = ("skillRuntimeBindings", "bindings", 0)
        mutations = (
            ("top bool version", ("skillRuntimeBindings", "version"), True),
            ("binding bool version", binding_path + ("version",), True),
            ("name", binding_path + ("skill",), "beta"),
            ("content", binding_path + ("skillContentHash",), _sha("wrong-content")),
            ("manifest", binding_path + ("manifestHash",), _sha("wrong-manifest")),
            ("capability", binding_path + ("capability",), "other"),
            ("malformed", binding_path + ("checkedAt",), _DELETE),
            ("extra", binding_path + ("unexpected",), True),
        )
        for label, path, value in mutations:
            with self.subTest(label=label):
                with self.assertRaises(skill_lifecycle.SkillLifecycleError) as raised:
                    server_mod._agent_run_from_record(_variant(record, path, value))
                self.assertEqual(
                    raised.exception.code, "skill_lifecycle_runtime_binding_conflict",
                )
        duplicate = copy.deepcopy(record)
        duplicate["skillRuntimeBindings"]["bindings"].append(copy.deepcopy(
            duplicate["skillRuntimeBindings"]["bindings"][0]
        ))
        with self.assertRaises(skill_lifecycle.SkillLifecycleError):
            server_mod._agent_run_from_record(duplicate)

        legacy = copy.deepcopy(record)
        legacy.pop("skillLifecycle")
        del legacy["skillRuntimeBindings"]["bindings"][0]["checkedAt"]
        legacy_binding = server_mod._agent_run_from_record(legacy)[
            "skill_runtime_bindings"
        ]["alpha"]
        self.assertEqual(legacy_binding["checkedAt"], "")

    def test_in_memory_binding_conflict_blocks_record_and_public_projection(self):
        run = self._create_run("memory-binding-conflict")
        self._call(
            run,
            "check_skill_dependencies",
            {"name": "alpha", "capability": "inspect"},
            "memory-binding-call",
        )
        valid = copy.deepcopy(run["skill_runtime_bindings"]["alpha"])
        for label, field, value in (
            ("manifest", "manifestHash", _sha("conflict")),
            ("bool version", "version", True),
        ):
            with self.subTest(label=label):
                source = copy.deepcopy(valid)
                source[field] = value
                run["skill_runtime_bindings"] = {"alpha": source}
                for project in (
                    lambda: server_mod._agent_run_record(run),
                    lambda: server_mod._agent_snapshot(run, 0),
                ):
                    with self.assertRaises(skill_lifecycle.SkillLifecycleError) as raised:
                        project()
                    self.assertEqual(
                        raised.exception.code,
                        "skill_lifecycle_runtime_binding_conflict",
                    )

    def test_runtime_binding_persists_before_tool_result_is_exposed(self):
        run = self._create_run("binding-persist-order")
        original_persist = server_mod._persist_agent_run
        observations = []

        def observe(target):
            binding_present = "alpha" in target["skill_runtime_bindings"]
            execution = (target.get("tool_executions") or {}).get("binding-order-call") or {}
            observations.append((binding_present, execution.get("result") is None))
            return original_persist(target)

        with mock.patch.object(server_mod, "_persist_agent_run", side_effect=observe):
            result = self._call(
                run,
                "check_skill_dependencies",
                {"name": "alpha", "capability": "inspect"},
                "binding-order-call",
            )
        self.assertTrue(result["runtimeBinding"]["established"])
        self.assertIn((True, True), observations)

    def test_replacement_persist_failure_clears_target_and_retry_reauthorizes(self):
        skill = self._write_skill("atomic-bind")
        (skill / "dependencies.json").write_text(json.dumps({
            "schemaVersion": 1,
            "skill": "atomic-bind",
            "capabilities": {
                "inspect": {"required": [], "optional": []},
                "render": {"required": [], "optional": []},
            },
        }), encoding="utf-8")
        run = self._create_run(
            "atomic-bind", explicit_skill="atomic-bind", permission="bypass",
        )
        self._call(
            run,
            "check_skill_dependencies",
            {"name": "atomic-bind", "capability": "inspect"},
            "atomic-initial",
        )
        self.assertEqual(
            run["skill_runtime_bindings"]["atomic-bind"]["capability"], "inspect",
        )
        original_persist = server_mod._persist_agent_run
        failed = False
        retry_persisted = False

        def inject(target):
            nonlocal failed, retry_persisted
            binding = target["skill_runtime_bindings"].get("atomic-bind") or {}
            if binding.get("capability") == "render":
                if not failed:
                    failed = True
                    raise OSError("injected replacement binding persist failure")
                retry_persisted = True
            return original_persist(target)

        with mock.patch.object(server_mod, "_persist_agent_run", side_effect=inject):
            rejected = self._call(
                run,
                "check_skill_dependencies",
                {"name": "atomic-bind", "capability": "render"},
                "atomic-replace-fail",
            )
            self.assertEqual(
                rejected["errorCode"], "skill_dependency_binding_persist_failed",
            )
            self.assertNotIn("runtimeBinding", rejected)
            self.assertNotIn("atomic-bind", run["skill_runtime_bindings"])
            with mock.patch.object(
                server_mod, "execute_run_command_tool",
                side_effect=AssertionError("command must remain blocked"),
            ) as execute:
                blocked = self._call(
                    run,
                    "run_command",
                    {"command": "python --version"},
                    "atomic-command-blocked",
                )
            execute.assert_not_called()
            self.assertEqual(blocked["errorCode"], "skill_dependency_check_required")
            retried = self._call(
                run,
                "check_skill_dependencies",
                {"name": "atomic-bind", "capability": "render"},
                "atomic-retry",
            )

        self.assertTrue(retried["runtimeBinding"]["established"])
        self.assertTrue(retry_persisted)
        self.assertEqual(
            run["skill_runtime_bindings"]["atomic-bind"]["capability"], "render",
        )

    def test_command_never_executes_and_durably_clears_each_frozen_identity_drift(self):
        kinds = (
            "skill", "dependency", "resource-content", "resource-contract",
            "resource-source", "directory", "descriptor",
        )
        for index, kind in enumerate(kinds):
            with self.subTest(kind=kind):
                name = f"binding-drift-{index}"
                skill = self._write_skill(name)
                run = self._create_run(
                    f"binding-drift-{index}", explicit_skill=name, permission="bypass",
                )
                checked = self._call(
                    run,
                    "check_skill_dependencies",
                    {"name": name, "capability": "inspect"},
                    f"binding-drift-check-{index}",
                )
                self.assertTrue(checked["runtimeBinding"]["established"])
                selected = run["skill_lifecycle"]["activation"]["selected"][0]
                if kind == "skill":
                    (skill / "SKILL.md").write_text(
                        f"---\nname: {name}\ndescription: changed\n---\nChanged.\n",
                        encoding="utf-8",
                    )
                elif kind == "dependency":
                    (skill / "dependencies.json").write_text(json.dumps({
                        "schemaVersion": 1,
                        "skill": name,
                        "capabilities": {
                            "inspect": {"required": [{"type": "python", "name": "changed"}]},
                        },
                    }), encoding="utf-8")
                elif kind == "resource-content":
                    (skill / "scripts" / "run.py").write_text(
                        "print('changed')\n", encoding="utf-8",
                    )
                elif kind == "resource-contract":
                    path = skill / "code-resources.json"
                    contract = json.loads(path.read_text(encoding="utf-8"))
                    contract["resources"][0]["protocol"] = "skill-access-test/v2"
                    path.write_text(json.dumps(contract), encoding="utf-8")
                elif kind == "resource-source":
                    selected["resources"]["source"] = "installed"
                elif kind == "directory":
                    shutil.copytree(skill, self.skills_dir / f"alternate-{index}")
                    selected["source"]["directory"] = f"alternate-{index}"
                else:
                    selected["source"]["descriptorId"] = "sd1_" + "0" * 64
                run["_skill_lifecycle_view"] = run["skill_lifecycle"]
                with mock.patch.object(
                    server_mod, "execute_run_command_tool",
                    side_effect=AssertionError("stale command must not execute"),
                ) as execute:
                    blocked = self._call(
                        run,
                        "run_command",
                        {"command": "python --version"},
                        f"binding-drift-command-{index}",
                    )
                execute.assert_not_called()
                self.assertEqual(blocked["errorCode"], "skill_dependency_runtime_stale")
                self.assertNotIn(name, run["skill_runtime_bindings"])
                durable = server_mod.read_json(server_mod._agent_run_path(run["id"]), None)
                self.assertNotIn("skillRuntimeBindings", durable)

    def test_managed_runtime_and_python_node_path_drift_never_execute(self):
        for index, kind in enumerate(("runtime", "python-path", "node-path")):
            with self.subTest(kind=kind):
                name = f"managed-drift-{index}"
                self._write_skill(name)
                run = self._create_run(
                    f"managed-drift-{index}", explicit_skill=name, permission="bypass",
                )
                runtime = self._managed_runtime(str(index))
                ready = self._ready_status(run, name, "inspect", runtime)
                with mock.patch.object(
                    server_mod, "_agent_lifecycle_dependency_status", return_value=ready,
                ):
                    checked = self._call(
                        run,
                        "check_skill_dependencies",
                        {"name": name, "capability": "inspect"},
                        f"managed-check-{index}",
                    )
                self.assertTrue(checked["runtimeBinding"]["established"])
                current = ready
                if kind == "runtime":
                    changed_runtime = self._managed_runtime(f"changed-{index}")
                    current = self._ready_status(run, name, "inspect", changed_runtime)
                elif kind == "python-path":
                    Path(runtime["python"]["executable"]).unlink()
                else:
                    shutil.rmtree(runtime["node"]["nodePath"])
                with mock.patch.object(
                    server_mod, "_agent_lifecycle_dependency_status", return_value=current,
                ), mock.patch.object(
                    server_mod, "execute_run_command_tool",
                    side_effect=AssertionError("drifted runtime must not execute"),
                ) as execute:
                    blocked = self._call(
                        run,
                        "run_command",
                        {"command": "python --version"},
                        f"managed-command-{index}",
                    )
                execute.assert_not_called()
                self.assertEqual(blocked["errorCode"], "skill_dependency_runtime_stale")
                self.assertNotIn(name, run["skill_runtime_bindings"])

    def test_skill_dependency_and_executable_resource_drift_fail_closed(self):
        cases = (
            (
                "skill",
                lambda: (self.skill_dir / "SKILL.md").write_text(
                    "---\nname: alpha\ndescription: changed\n---\nChanged body.\n",
                    encoding="utf-8",
                ),
                "skill_lifecycle_identity_changed",
            ),
            (
                "dependency",
                lambda: (self.skill_dir / "dependencies.json").write_text(json.dumps({
                    "schemaVersion": 1,
                    "skill": "alpha",
                    "capabilities": {
                        "inspect": {"required": [{"type": "python", "name": "changed"}]},
                    },
                }), encoding="utf-8"),
                "skill_lifecycle_dependency_changed",
            ),
            (
                "resource",
                lambda: (self.skill_dir / "scripts" / "run.py").write_text(
                    "print('changed helper')\n", encoding="utf-8",
                ),
                "skill_lifecycle_resource_changed",
            ),
        )
        for index, (label, mutate, expected) in enumerate(cases):
            with self.subTest(kind=label):
                if index:
                    self.skill_dir = self._write_skill(f"alpha-{index}")
                    run = self._create_run(
                        f"drift-{index}", explicit_skill=f"alpha-{index}",
                    )
                    arguments = {"name": f"alpha-{index}"}
                else:
                    run = self._create_run("drift-0")
                    arguments = {"name": "alpha"}
                mutate()
                result = self._call(run, "use_skill", arguments, f"drift-call-{index}")
                self.assertFalse(result["ok"])
                self.assertEqual(result["errorCode"], expected)

    def test_same_name_alternate_directory_and_descriptor_are_not_authority(self):
        for field in ("descriptor", "directory"):
            with self.subTest(field=field):
                run = self._create_run(f"identity-{field}")
                selected = run["skill_lifecycle"]["activation"]["selected"][0]
                if field == "directory":
                    shutil.copytree(self.skill_dir, self.skills_dir / "alternate")
                    selected["source"]["directory"] = "alternate"
                else:
                    selected["source"]["descriptorId"] = "sd1_" + "0" * 64
                run["_skill_lifecycle_view"] = run["skill_lifecycle"]
                with mock.patch.object(
                    server_mod, "list_skills", side_effect=AssertionError("must not enumerate"),
                ):
                    result = self._call(
                        run, "use_skill", {"name": "alpha"}, f"identity-call-{field}",
                    )
                self.assertEqual(result["errorCode"], "skill_lifecycle_identity_changed")

    def test_resource_contract_and_source_drift_fail_closed(self):
        run = self._create_run("contract-drift")
        contract_path = self.skill_dir / "code-resources.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["resources"][0]["protocol"] = "skill-access-test/v2"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        changed = self._call(
            run, "use_skill", {"name": "alpha"}, "contract-drift-call",
        )
        self.assertEqual(changed["errorCode"], "skill_lifecycle_resource_changed")

        self.skill_dir = self._write_skill("alpha-source")
        source_run = self._create_run(
            "source-drift", explicit_skill="alpha-source",
        )
        selected = source_run["skill_lifecycle"]["activation"]["selected"][0]
        self.assertEqual(selected["resources"]["source"], "custom")
        selected["resources"]["source"] = "installed"
        source_run["_skill_lifecycle_view"] = source_run["skill_lifecycle"]
        source_changed = self._call(
            source_run,
            "use_skill",
            {"name": "alpha-source"},
            "source-drift-call",
        )
        self.assertEqual(
            source_changed["errorCode"], "skill_lifecycle_resource_changed",
        )

    def test_first_read_persists_hash_and_later_content_change_is_rejected(self):
        run = self._create_run("first-read")
        guide = self.skill_dir / "references" / "guide.md"
        expected_hash = "sha256:" + hashlib.sha256(guide.read_bytes()).hexdigest()

        first = self._call(
            run,
            "read_skill_resource",
            {"skill": "alpha", "file": "references/guide.md"},
            "first-read-call",
        )
        record = server_mod.read_json(server_mod._agent_run_path(run["id"]), None)
        binding = record["skillLifecycle"]["access"]["resourceBindings"][0]
        self.assertTrue(first["ok"])
        self.assertEqual(first["content"].strip(), "Pinned guide v1")
        self.assertEqual(binding["skill"], "alpha")
        self.assertEqual(binding["file"], "references/guide.md")
        self.assertEqual(binding["contentHash"], expected_hash)

        guide.write_text(
            "Pinned guide v2\n", encoding="utf-8",
        )
        changed = self._call(
            run,
            "read_skill_resource",
            {"skill": "alpha", "file": "references/guide.md"},
            "changed-read-call",
        )
        self.assertFalse(changed["ok"])
        self.assertEqual(changed["errorCode"], "skill_lifecycle_reference_changed")
        self.assertNotIn("content", changed)

    def test_repeat_restart_and_concurrent_first_reads_keep_one_binding(self):
        run = self._create_run("repeat-read")
        arguments = {"skill": "alpha", "file": "references/guide.md"}
        first = self._call(run, "read_skill_resource", arguments, "repeat-first")
        repeated = self._call(run, "read_skill_resource", arguments, "repeat-second")
        self.assertEqual(first["content"], repeated["content"])
        self.assertEqual(
            len(run["skill_lifecycle"]["access"]["resourceBindings"]), 1,
        )

        with run["condition"]:
            run["status"] = "waiting_credentials"
            run["resume_status"] = "model"
        record = server_mod._agent_run_record(run)
        with mock.patch.object(
            server_mod, "read_skill", side_effect=AssertionError("restore must not enumerate"),
        ):
            restored = server_mod._agent_run_from_record(copy.deepcopy(record))
        after_restart = self._call(
            restored, "read_skill_resource", arguments, "restart-read",
        )
        self.assertEqual(after_restart["content"], first["content"])
        self.assertEqual(
            restored["skill_lifecycle"]["access"]["resourceBindings"],
            record["skillLifecycle"]["access"]["resourceBindings"],
        )

        concurrent = self._create_run("concurrent-read")
        results = []
        threads = [threading.Thread(
            target=lambda: results.append(server_mod._execute_agent_skill_lifecycle_tool(
                concurrent, "read_skill_resource", arguments,
            )),
        ) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertEqual(len(results), 6)
        self.assertTrue(all(item["ok"] for item in results))
        self.assertEqual(
            len(concurrent["skill_lifecycle"]["access"]["resourceBindings"]), 1,
        )

    def test_first_read_binding_is_persisted_before_tool_result_is_exposed(self):
        run = self._create_run("persist-order")
        original_persist = server_mod._persist_agent_run
        observations = []

        def observe(target):
            binding_present = bool(
                target["skill_lifecycle"]["access"]["resourceBindings"]
            )
            execution = (target.get("tool_executions") or {}).get("persist-order-call") or {}
            observations.append((binding_present, execution.get("result") is None))
            return original_persist(target)

        with mock.patch.object(server_mod, "_persist_agent_run", side_effect=observe):
            result = self._call(
                run,
                "read_skill_resource",
                {"skill": "alpha", "file": "references/guide.md"},
                "persist-order-call",
            )

        self.assertTrue(result["ok"])
        self.assertIn((True, True), observations)

    def test_persist_failure_rolls_back_binding_and_retry_persists_before_content(self):
        run = self._create_run("persist-retry")
        original_persist = server_mod._persist_agent_run
        failed = False
        successful_binding_persists = 0

        def inject(target):
            nonlocal failed, successful_binding_persists
            has_binding = bool(target["skill_lifecycle"]["access"]["resourceBindings"])
            pending_result = all(
                execution.get("result") is None
                for execution in (target.get("tool_executions") or {}).values()
                if execution.get("status") == "running"
            )
            if has_binding and pending_result:
                if not failed:
                    failed = True
                    raise OSError("injected lifecycle persist failure")
                successful_binding_persists += 1
            return original_persist(target)

        arguments = {"skill": "alpha", "file": "references/guide.md"}
        with mock.patch.object(server_mod, "_persist_agent_run", side_effect=inject):
            first = self._call(run, "read_skill_resource", arguments, "persist-fail-call")
            self.assertFalse(first["ok"])
            self.assertEqual(first["errorCode"], "skill_lifecycle_persist_failed")
            self.assertNotIn("content", first)
            self.assertEqual(
                run["skill_lifecycle"]["access"]["resourceBindings"], [],
            )
            second = self._call(run, "read_skill_resource", arguments, "persist-retry-call")

        self.assertTrue(second["ok"])
        self.assertGreaterEqual(successful_binding_persists, 1)
        durable = server_mod.read_json(server_mod._agent_run_path(run["id"]), None)
        self.assertEqual(
            len(durable["skillLifecycle"]["access"]["resourceBindings"]), 1,
        )

    def test_v1_empty_access_record_upgrades_after_restart_read(self):
        run = self._create_run("v1-access")
        with run["condition"]:
            run["status"] = "waiting_credentials"
            run["resume_status"] = "model"
        record = server_mod._agent_run_record(run)
        record["skillLifecycle"]["access"] = {
            "schemaVersion": 1, "resourceBindings": [],
        }

        restored = server_mod._agent_run_from_record(record)
        result = self._call(
            restored,
            "read_skill_resource",
            {"skill": "alpha", "file": "references/guide.md"},
            "v1-upgrade-call",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(restored["skill_lifecycle"]["access"]["schemaVersion"], 2)
        self.assertEqual(
            len(restored["skill_lifecycle"]["access"]["resourceBindings"]), 1,
        )

    def test_persisted_case_alias_duplicate_fails_closed_on_restore(self):
        run = self._create_run("case-alias-record")
        self._call(
            run,
            "read_skill_resource",
            {"skill": "alpha", "file": "references/guide.md"},
            "case-alias-read",
        )
        with run["condition"]:
            run["status"] = "waiting_credentials"
            run["resume_status"] = "model"
        record = server_mod._agent_run_record(run)
        duplicate = copy.deepcopy(
            record["skillLifecycle"]["access"]["resourceBindings"][0]
        )
        duplicate["file"] = "REFERENCES/GUIDE.MD"
        record["skillLifecycle"]["access"]["resourceBindings"].append(duplicate)

        with self.assertRaises(skill_lifecycle.SkillLifecycleError) as raised:
            server_mod._agent_run_from_record(record)

        self.assertEqual(raised.exception.code, "skill_lifecycle_invalid")

    def test_direct_legacy_background_and_child_skill_tools_keep_old_behavior(self):
        direct = server_mod.execute_use_skill_tool({"name": "alpha"})
        self.assertTrue(direct["ok"])
        self.assertIn("body", direct)
        self.assertIn("runtimeResources", direct)

        for run_kind in ("foreground", "background", "child"):
            with self.subTest(run_kind=run_kind):
                run = self._create_legacy_run(f"legacy-{run_kind}", run_kind=run_kind)
                result = self._call(
                    run, "use_skill", {"name": "alpha"}, f"legacy-call-{run_kind}",
                )
                self.assertIsNone(run["skill_lifecycle"])
                self.assertIn("body", result)
                self.assertEqual(
                    run["skill_runtime_bindings"]["alpha"]["capability"], "inspect",
                )


if __name__ == "__main__":
    unittest.main()
