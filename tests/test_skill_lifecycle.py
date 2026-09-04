import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

import server as server_mod
from code_runtime import skill_lifecycle
from code_runtime.skill_activation import SKILL_PROMPT_MARKER


def _sha(label):
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _capture(name="alpha", *, role_index=0, evidence=True, dependency=True, resources=True):
    return {
        "name": name,
        "contentHash": _sha(f"skill:{name}"),
        "sourceIdentity": {
            "kind": "installed",
            "directory": name,
            "descriptorId": "sd1_" + hashlib.sha256(name.encode("utf-8")).hexdigest(),
        },
        "evidence": (
            {
                "schemaVersion": 1,
                "requirements": [{
                    "id": f"check-{role_index}",
                    "type": "tool_execution",
                    "tool": "read_file",
                    "minCount": 1,
                }],
            }
            if evidence else None
        ),
        "evidenceIdentity": (
            {"state": "ready", "contentHash": _sha(f"evidence:{name}")}
            if evidence else {"state": "missing"}
        ),
        "dependencyIdentity": (
            {
                "state": "ready",
                "manifestHash": _sha(f"dependency:{name}"),
                "capabilities": ["inspect"],
            }
            if dependency else {"state": "missing", "capabilities": []}
        ),
        "resourceIdentity": (
            {"state": "ready", "contractHash": _sha(f"resources:{name}")}
            if resources else {"state": "missing"}
        ),
    }


_DELETE = object()

def _variant(source, path, value):
    result = copy.deepcopy(source)
    parent = result
    for component in path[:-1]:
        parent = parent[component]
    key = path[-1]
    if value is _DELETE:
        del parent[key]
    else:
        parent[key] = value
    return result

def _write_skill(root, name="alpha", *, sidecars=True, tool="read_file"):
    skill_dir = Path(root) / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join([
            "---",
            f"name: {name}",
            "description: Lifecycle contract test Skill",
            f"allowed-tools: {tool}",
            "---",
            "",
            "SERVER_CAPTURED_LIFECYCLE_SKILL",
        ]),
        encoding="utf-8",
    )
    if sidecars:
        (skill_dir / "evidence.json").write_text(json.dumps({
            "schemaVersion": 1,
            "requirements": [{
                "id": "inspect-source",
                "type": "tool_execution",
                "tool": tool,
                "minCount": 1,
            }],
        }), encoding="utf-8")
        (skill_dir / "dependencies.json").write_text(json.dumps({
            "schemaVersion": 1,
            "skill": name,
            "capabilities": {
                "inspect": {"required": [], "optional": []},
            },
        }), encoding="utf-8")
        (skill_dir / "code-resources.json").write_text(json.dumps({
            "schemaVersion": 1,
            "skill": name,
            "resources": [],
        }), encoding="utf-8")
    return skill_dir


def _messages(user="Use alpha for this task"):
    return [
        {
            "role": "system",
            "content": f"base\n\n{SKILL_PROMPT_MARKER}\n\npermission",
        },
        {"role": "user", "content": user},
    ]


def _build_lifecycle(activation):
    captures = activation.get("captures") if isinstance(activation, dict) else []
    observers = []
    for capture in captures if isinstance(captures, list) else []:
        if not isinstance(capture, dict):
            observers.append({})
            continue
        active = {"name": capture.get("name"), "contentHash": capture.get("contentHash")}
        if capture.get("evidence") is None:
            observers.append({"activeSkill": active, "contractState": "missing"})
        else:
            observers.append({"activeSkill": active, "contractState": "valid",
                              "contract": capture.get("evidence")})
    return skill_lifecycle.build_skill_lifecycle(activation, evidence_observers=observers)


class TestSkillLifecycleContract(unittest.TestCase):
    def test_builds_canonical_activation_and_projects_compatibility(self):
        activation = {
            "explicit": False,
            "captures": [_capture("alpha"), _capture("reviewer", role_index=1)],
        }

        lifecycle = _build_lifecycle(activation)
        projection = skill_lifecycle.project_skill_lifecycle(lifecycle)

        self.assertEqual(lifecycle["schemaVersion"], 1)
        self.assertEqual(lifecycle["mode"], "canonical-v1")
        self.assertEqual(lifecycle["activation"]["intentKind"], "automatic")
        self.assertEqual(lifecycle["activation"]["outcome"], "activated")
        self.assertEqual(
            [item["role"] for item in lifecycle["activation"]["selected"]],
            ["owner", "modifier"],
        )
        self.assertEqual(projection["activeSkillNames"], ["alpha", "reviewer"])
        self.assertEqual(
            projection["dependencies"],
            {"alpha": ["inspect"], "reviewer": ["inspect"]},
        )
        self.assertFalse(projection["explicit"])
        self.assertEqual(projection["captures"][0]["evidence"], activation["captures"][0]["evidence"])
        self.assertEqual(lifecycle["access"], {"schemaVersion": 1, "resourceBindings": []})
        with self.assertRaises(skill_lifecycle.SkillLifecycleError):
            skill_lifecycle.build_skill_lifecycle(activation, evidence_observers=[])

    def test_canonical_none_and_legacy_adapter_are_distinct(self):
        lifecycle = _build_lifecycle({"explicit": False, "captures": []})
        self.assertEqual(lifecycle["activation"]["outcome"], "none")
        self.assertEqual(skill_lifecycle.project_skill_lifecycle(lifecycle)["activeSkillNames"], [])

        legacy = skill_lifecycle.adapt_legacy_skill_lifecycle(
            ["alpha"],
            {"alpha": ["inspect"]},
            {
                "version": 1,
                "skills": [{
                    "activeSkill": {"name": "alpha", "contentHash": _sha("legacy")},
                }],
            },
        )
        self.assertEqual(legacy["mode"], "legacy")
        self.assertEqual(legacy["activation"]["selected"][0]["role"], "unknown")
        self.assertEqual(legacy["activation"]["selected"][0]["skillContentHash"], _sha("legacy"))
        self.assertNotIn("source", legacy["activation"]["selected"][0])

    def test_normalization_is_a_deep_copy_and_rejects_unknown_versions(self):
        source = _build_lifecycle({
            "explicit": True,
            "captures": [_capture("alpha")],
        })
        normalized = skill_lifecycle.normalize_skill_lifecycle(source)
        normalized["activation"]["selected"][0]["name"] = "changed"
        self.assertEqual(source["activation"]["selected"][0]["name"], "alpha")

        invalid = json.loads(json.dumps(source))
        invalid["schemaVersion"] = 2
        with self.assertRaises(skill_lifecycle.SkillLifecycleError):
            skill_lifecycle.normalize_skill_lifecycle(invalid)

    def test_rejects_unknown_child_versions_with_stable_codes(self):
        source = _build_lifecycle({
            "explicit": True,
            "captures": [_capture("alpha")],
        })
        cases = [
            (
                "outer",
                ("schemaVersion",),
                2,
                "skill_lifecycle_version_unsupported",
            ),
            (
                "activation",
                ("activation", "schemaVersion"),
                2,
                "skill_lifecycle_activation_version_unsupported",
            ),
            (
                "access",
                ("access", "schemaVersion"),
                2,
                "skill_lifecycle_access_version_unsupported",
            ),
        ]
        for label, path, value, expected_code in cases:
            with self.subTest(label=label):
                with self.assertRaises(skill_lifecycle.SkillLifecycleError) as raised:
                    skill_lifecycle.normalize_skill_lifecycle(
                        _variant(source, path, value)
                    )
                self.assertEqual(raised.exception.code, expected_code)

    def test_rejects_malformed_partial_and_noncanonical_envelopes(self):
        source = _build_lifecycle({
            "explicit": True,
            "captures": [_capture("alpha")],
        })
        selected = ("activation", "selected", 0)
        cases = [
            ("top missing", ("mode",), _DELETE),
            ("top extra", ("clientIntent",), "forbidden"),
            ("mode", ("mode",), "legacy"),
            ("bool version", ("schemaVersion",), True),
            ("activation missing", ("activation", "outcome"), _DELETE),
            ("activation extra", ("activation", "rawIntent"), "forbidden"),
            ("intent", ("activation", "intentKind"), "legacy"),
            ("outcome", ("activation", "outcome"), "unknown"),
            ("selected type", ("activation", "selected"), {}),
            ("selected extra", selected + ("body",), "forbidden"),
            ("name", selected + ("name",), "bad/name"),
            ("role", selected + ("role",), "modifier"),
            ("source missing", selected + ("source", "descriptorId"), _DELETE),
            ("source extra", selected + ("source", "absolutePath"), "C:/secret"),
            ("source kind", selected + ("source", "kind"), "bundled"),
            ("source directory", selected + ("source", "directory"), "../alpha"),
            ("descriptor", selected + ("source", "descriptorId"), "sd1_short"),
            ("skill hash", selected + ("skillContentHash",), "sha256:nope"),
            ("evidence state", selected + ("evidence", "state"), "invalid"),
            ("evidence hash", selected + ("evidence", "contentHash"), "bad"),
            ("evidence missing contract", selected + ("evidence", "contract"), _DELETE),
            ("dependency state", selected + ("dependency", "state"), "invalid"),
            ("dependency hash", selected + ("dependency", "manifestHash"), "bad"),
            (
                "dependency unsorted",
                selected + ("dependency", "capabilities"),
                ["second", "first"],
            ),
            (
                "dependency duplicate",
                selected + ("dependency", "capabilities"),
                ["inspect", "inspect"],
            ),
            (
                "dependency invalid capability",
                selected + ("dependency", "capabilities"),
                ["Inspect"],
            ),
            ("resources state", selected + ("resources", "state"), "invalid"),
            ("resources hash", selected + ("resources", "contractHash"), "bad"),
            ("access extra", ("access", "diagnostics"), []),
            ("access binding premature", ("access", "resourceBindings"), [{}]),
        ]
        for label, path, value in cases:
            with self.subTest(label=label):
                with self.assertRaises(skill_lifecycle.SkillLifecycleError) as raised:
                    skill_lifecycle.normalize_skill_lifecycle(
                        _variant(source, path, value)
                    )
                self.assertEqual(
                    raised.exception.code,
                    (
                        "skill_lifecycle_version_unsupported"
                        if label == "bool version"
                        else "skill_lifecycle_invalid"
                    ),
                )

    def test_rejects_outcome_role_and_cardinality_conflicts(self):
        explicit = _build_lifecycle({"explicit": True, "captures": [_capture("alpha")]})
        automatic = _build_lifecycle({
            "explicit": False,
            "captures": [_capture("alpha"), _capture("reviewer", role_index=1)],
        })
        none = _build_lifecycle({"explicit": False, "captures": []})
        cases = [
            ("explicit none", _variant(explicit, ("activation", "outcome"), "none")),
            ("explicit two", _variant(
                explicit, ("activation", "selected"), automatic["activation"]["selected"],
            )),
            ("activated empty", _variant(none, ("activation", "outcome"), "activated")),
            ("none selected", _variant(automatic, ("activation", "outcome"), "none")),
            ("duplicate names", _variant(
                automatic, ("activation", "selected", 1, "name"), "alpha",
            )),
            ("second owner", _variant(
                automatic, ("activation", "selected", 1, "role"), "owner",
            )),
            (
                "too many",
                _variant(
                    automatic,
                    ("activation", "selected"),
                    [
                        automatic["activation"]["selected"][0],
                        automatic["activation"]["selected"][1],
                        automatic["activation"]["selected"][1],
                    ],
                ),
            ),
        ]
        for label, value in cases:
            with self.subTest(label=label):
                with self.assertRaises(skill_lifecycle.SkillLifecycleError):
                    skill_lifecycle.normalize_skill_lifecycle(value)

    def test_missing_sidecars_have_exact_minimal_shapes(self):
        lifecycle = _build_lifecycle({
            "explicit": True,
            "captures": [_capture(
                "alpha", evidence=False, dependency=False, resources=False,
            )],
        })
        selected = lifecycle["activation"]["selected"][0]
        self.assertEqual(selected["evidence"], {"state": "missing"})
        self.assertEqual(
            selected["dependency"],
            {"state": "missing", "capabilities": []},
        )
        self.assertEqual(selected["resources"], {"state": "missing"})
        projection = skill_lifecycle.project_skill_lifecycle(lifecycle)
        self.assertIsNone(projection["captures"][0]["evidence"])
        self.assertEqual(projection["dependencies"], {"alpha": []})

    def test_record_contains_no_prompt_body_path_registry_or_diagnostics(self):
        capture = _capture("alpha")
        capture.update({
            "body": "SECRET_INSTRUCTION_BODY",
            "descriptor": {
                "absolutePath": "C:/private/alpha/SKILL.md",
                "diagnostics": [{"code": "private"}],
                "registry": [{"name": "other"}],
            },
            "references": [{"name": "other"}],
            "disabledNames": ["other"],
        })
        lifecycle = _build_lifecycle({
            "explicit": True,
            "captures": [capture],
            "rawIntent": "use alpha with secret text",
        })
        serialized = json.dumps(lifecycle, ensure_ascii=False, sort_keys=True)
        for forbidden in (
            "SECRET_INSTRUCTION_BODY",
            "C:/private",
            "absolutePath",
            "diagnostics",
            "registry",
            "references",
            "disabledNames",
            "rawIntent",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

    def test_rejects_non_json_and_oversized_evidence_contracts(self):
        source = _build_lifecycle({
            "explicit": True,
            "captures": [_capture("alpha")],
        })
        non_json = _variant(
            source,
            ("activation", "selected", 0, "evidence", "contract"),
            {"schemaVersion": 1, "requirements": set()},
        )
        with self.assertRaises(skill_lifecycle.SkillLifecycleError):
            skill_lifecycle.normalize_skill_lifecycle(non_json)
        oversized = _variant(
            source,
            ("activation", "selected", 0, "evidence", "contract"),
            {"schemaVersion": 1, "requirements": [], "padding": "x" * (64 * 1024)},
        )
        with self.assertRaises(skill_lifecycle.SkillLifecycleError):
            skill_lifecycle.normalize_skill_lifecycle(oversized)


class TestSkillLifecycleAgentRunIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="code_skill_lifecycle_run_")
        self.root = Path(self.temp.name)
        self.data_dir = self.root / "data"
        self.skills_dir = self.data_dir / "skills"
        self.skills_dir.mkdir(parents=True)
        self.skill_dir = _write_skill(self.skills_dir)
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
        self.temp.cleanup()

    def _create(
        self,
        request_id="lifecycle-run",
        *,
        explicit_skill="alpha",
        disabled_names=None,
        start_worker=False,
        allowed_names=None,
        user_message="Use alpha for this task",
        permission_profile="read",
    ):
        return server_mod._create_agent_run(
            "",
            {
                "model": "test-model",
                "messages": _messages(user_message),
            },
            "http://127.0.0.1:1",
            [],
            {
                "schemaVersion": 1,
                "names": ["read_file"] if allowed_names is None else allowed_names,
            },
            4,
            permission_profile,
            start_worker=start_worker,
            client_request_id=request_id,
            cwd=str(self.root),
            run_kind="foreground",
            skill_activation_request={
                "schemaVersion": 1,
                "explicitSkill": explicit_skill,
                "disabledNames": list(disabled_names or []),
            },
        )

    @staticmethod
    def _terminal_record(run):
        with run["condition"]:
            run["status"] = "completed"
            run["resume_status"] = ""
        return server_mod._agent_run_record(run)

    def test_v5_record_contains_canonical_lifecycle_and_compatibility_projections(self):
        run = self._create()
        record = self._terminal_record(run)
        lifecycle = record["skillLifecycle"]
        selected = lifecycle["activation"]["selected"][0]

        self.assertEqual(record["version"], 5)
        self.assertEqual(lifecycle["schemaVersion"], 1)
        self.assertEqual(lifecycle["mode"], "canonical-v1")
        self.assertEqual(lifecycle["activation"]["intentKind"], "explicit")
        self.assertEqual(lifecycle["activation"]["outcome"], "activated")
        self.assertEqual(selected["name"], "alpha")
        self.assertEqual(selected["role"], "owner")
        self.assertEqual(selected["source"]["kind"], "installed")
        self.assertEqual(selected["source"]["directory"], "alpha")
        self.assertRegex(selected["source"]["descriptorId"], r"^sd1_[0-9a-f]{64}$")
        self.assertEqual(selected["evidence"]["state"], "ready")
        self.assertEqual(selected["dependency"]["state"], "ready")
        self.assertEqual(selected["dependency"]["capabilities"], ["inspect"])
        self.assertEqual(selected["resources"]["state"], "ready")
        self.assertEqual(lifecycle["access"]["resourceBindings"], [])

        projection = skill_lifecycle.project_skill_lifecycle(lifecycle)
        self.assertEqual(record["activeSkillNames"], projection["activeSkillNames"])
        self.assertEqual(
            record["activeSkillDependencies"],
            {"version": 1, "skills": [{"skill": "alpha", "capabilities": ["inspect"]}]},
        )
        restored_observers = server_mod._restore_skill_evidence_observers(
            record["skillEvidence"], run["tools"],
        )
        expected_observers = server_mod._freeze_captured_skill_evidence_observers(
            projection, run["tools"],
        )
        self.assertEqual(restored_observers, expected_observers)

        serialized = json.dumps(lifecycle, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotIn("SERVER_CAPTURED_LIFECYCLE_SKILL", serialized)
        self.assertNotIn("absolutePath", serialized)
        self.assertNotIn("diagnostics", serialized)
        self.assertNotIn("disabledNames", serialized)

        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["activeSkillNames"], ["alpha"])
        self.assertNotIn("skillLifecycle", snapshot)

    def test_roundtrip_uses_lifecycle_without_skill_or_registry_reread(self):
        original = self._create("roundtrip")
        record = self._terminal_record(original)
        with mock.patch.object(
            server_mod,
            "prepare_skill_activation",
            side_effect=AssertionError("restore must not activate Skills"),
        ), mock.patch.object(
            server_mod,
            "read_skill",
            side_effect=AssertionError("restore must not read Skills"),
        ), mock.patch.object(
            server_mod,
            "_agent_registry_tool_definition",
            return_value=None,
        ):
            restored = server_mod._agent_run_from_record(copy.deepcopy(record))
            persisted_again = server_mod._agent_run_record(restored)

        self.assertEqual(restored["skill_lifecycle"], record["skillLifecycle"])
        self.assertEqual(restored["_skill_lifecycle_view"], record["skillLifecycle"])
        self.assertEqual(restored["active_skill_names"], ["alpha"])
        self.assertEqual(restored["active_skill_dependencies"], {"alpha": ["inspect"]})
        self.assertEqual(persisted_again["skillLifecycle"], record["skillLifecycle"])
        self.assertEqual(persisted_again["activeSkillNames"], record["activeSkillNames"])
        self.assertEqual(
            persisted_again["activeSkillDependencies"],
            record["activeSkillDependencies"],
        )
        self.assertEqual(persisted_again["skillEvidence"], record["skillEvidence"])

    def test_restart_loader_restores_lifecycle_and_does_not_reread_skill(self):
        original = self._create("restart-loader")
        lifecycle = copy.deepcopy(original["skill_lifecycle"])
        run_path = server_mod._agent_run_path(original["id"])
        self.assertTrue(run_path.is_file())
        with server_mod._agent_run_lock:
            server_mod._agent_runs.clear()
        with mock.patch.object(
            server_mod,
            "prepare_skill_activation",
            side_effect=AssertionError("restart must not activate Skills"),
        ), mock.patch.object(
            server_mod,
            "read_skill",
            side_effect=AssertionError("restart must not read Skills"),
        ):
            restored = server_mod._get_agent_run(original["id"])

        self.assertIsNotNone(restored)
        self.assertEqual(restored["skill_lifecycle"], lifecycle)
        self.assertEqual(restored["active_skill_names"], ["alpha"])
        self.assertEqual(restored["status"], "waiting_credentials")
        durable = server_mod.read_json(run_path, None)
        self.assertEqual(durable["skillLifecycle"], lifecycle)
        self.assertEqual(durable["activeSkillNames"], ["alpha"])

    def test_restart_recovery_mutation_does_not_create_false_projection_conflict(self):
        _write_skill(self.skills_dir, tool="run_command")
        run = self._create(
            "running-command-recovery",
            allowed_names=["run_command"],
            permission_profile="accept",
        )
        run["tool_executions"] = {
            "call-running": {
                "name": "run_command",
                "arguments": {"command": "never-executed"},
                "command": "never-executed",
                "status": "running",
                "stdout": "",
                "stderr": "",
            },
        }
        record = server_mod._agent_run_record(run)
        self.assertEqual(record["skillEvidence"]["status"], "partial")
        restored = server_mod._agent_run_from_record(record)
        execution = restored["tool_executions"]["call-running"]
        self.assertEqual(execution["status"], "completed")
        self.assertEqual(execution["outcome"], "failed")
        self.assertTrue(execution["result"]["interrupted"])
        self.assertTrue(execution["result"]["notReplayed"])
        self.assertEqual(restored["skill_lifecycle"], record["skillLifecycle"])

    def test_automatic_no_match_persists_lifecycle_without_compatibility_noise(self):
        run = self._create(
            "automatic-none",
            explicit_skill="",
            disabled_names=["alpha"],
            user_message="No matching capability is requested",
        )
        record = self._terminal_record(run)
        lifecycle = record["skillLifecycle"]
        self.assertEqual(lifecycle["activation"], {
            "schemaVersion": 1,
            "intentKind": "automatic",
            "outcome": "none",
            "selected": [],
        })
        for key in ("activeSkillNames", "activeSkillDependencies", "skillEvidence"):
            self.assertNotIn(key, record)
        restored = server_mod._agent_run_from_record(record)
        self.assertEqual(restored["active_skill_names"], [])
        self.assertEqual(restored["active_skill_dependencies"], {})
        self.assertEqual(restored["skill_evidence_observers"], [])
        self.assertEqual(
            server_mod._agent_run_record(restored)["skillLifecycle"],
            lifecycle,
        )

    def test_projection_conflicts_and_missing_compatibility_fail_closed(self):
        record = self._terminal_record(self._create("projection-conflicts"))
        mutations = [
            (
                "name changed",
                ("activeSkillNames", 0),
                "other",
            ),
            (
                "name missing",
                ("activeSkillNames",),
                _DELETE,
            ),
            (
                "dependency changed",
                ("activeSkillDependencies", "skills", 0, "capabilities"),
                [],
            ),
            (
                "dependency missing",
                ("activeSkillDependencies",),
                _DELETE,
            ),
            (
                "evidence identity changed",
                ("skillEvidence", "skills", 0, "activeSkill", "contentHash"),
                _sha("tampered"),
            ),
            (
                "evidence status changed",
                ("skillEvidence", "status"),
                "satisfied",
            ),
            (
                "evidence missing",
                ("skillEvidence",),
                _DELETE,
            ),
        ]
        for label, path, value in mutations:
            with self.subTest(label=label):
                with self.assertRaises(skill_lifecycle.SkillLifecycleError) as raised:
                    server_mod._agent_run_from_record(
                        _variant(record, path, value)
                    )
                self.assertEqual(
                    raised.exception.code,
                    "skill_lifecycle_projection_conflict",
                )

    def test_in_memory_projection_conflicts_cannot_be_persisted(self):
        cases = [
            ("names", "active_skill_names", ["other"]),
            ("dependencies", "active_skill_dependencies", {"alpha": []}),
            ("evidence", "skill_evidence_observers", []),
        ]
        for index, (label, key, value) in enumerate(cases):
            with self.subTest(label=label):
                run = self._create(f"memory-conflict-{index}")
                run[key] = value
                with self.assertRaises(skill_lifecycle.SkillLifecycleError) as raised:
                    server_mod._agent_run_record(run)
                self.assertEqual(
                    raised.exception.code,
                    "skill_lifecycle_projection_conflict",
                )

    def test_unknown_malformed_or_wrong_outer_lifecycle_fails_closed(self):
        record = self._terminal_record(self._create("malformed-lifecycle"))
        cases = [
            (
                "unknown lifecycle version",
                _variant(record, ("skillLifecycle", "schemaVersion"), 2),
                "skill_lifecycle_version_unsupported",
            ),
            (
                "malformed ready evidence",
                _variant(record, ("skillLifecycle", "activation", "selected", 0,
                                  "evidence", "contract"),
                         {"schemaVersion": 1, "requirements": []}),
                "skill_lifecycle_invalid",
            ),
            (
                "null lifecycle",
                _variant(record, ("skillLifecycle",), None),
                "skill_lifecycle_invalid",
            ),
            (
                "wrong outer version",
                _variant(record, ("version",), 4),
                "skill_lifecycle_outer_version_unsupported",
            ),
            (
                "wrong run scope",
                _variant(record, ("runKind",), "child"),
                "skill_lifecycle_scope_invalid",
            ),
        ]
        for label, value, expected_code in cases:
            with self.subTest(label=label):
                with self.assertRaises(skill_lifecycle.SkillLifecycleError) as raised:
                    server_mod._agent_run_from_record(value)
                self.assertEqual(raised.exception.code, expected_code)

    def test_old_v1_through_v5_records_use_read_only_adapter_without_writeback(self):
        source = self._terminal_record(self._create("legacy-fixtures"))
        del source["skillLifecycle"]
        for version in range(1, 6):
            with self.subTest(version=version):
                record = copy.deepcopy(source)
                record["version"] = version
                before = json.dumps(record, ensure_ascii=False, sort_keys=True)
                restored = server_mod._agent_run_from_record(record)
                after = json.dumps(record, ensure_ascii=False, sort_keys=True)
                self.assertEqual(after, before)
                self.assertIsNone(restored["skill_lifecycle"])
                self.assertEqual(restored["_skill_lifecycle_view"]["mode"], "legacy")
                selected = restored["_skill_lifecycle_view"]["activation"]["selected"]
                self.assertEqual(selected[0]["name"], "alpha")
                self.assertEqual(selected[0]["role"], "unknown")
                self.assertEqual(
                    selected[0]["skillContentHash"],
                    source["skillEvidence"]["skills"][0]["activeSkill"]["contentHash"],
                )
                rewritten = server_mod._agent_run_record(restored)
                self.assertNotIn("skillLifecycle", rewritten)
                self.assertEqual(rewritten["activeSkillNames"], ["alpha"])

    def test_sidecar_changes_after_registry_capture_fail_closed(self):
        from code_runtime import skill_activation

        real_shadow = skill_activation.resolve_skill_shadow
        real_manifest = skill_activation.resolve_skill_manifest

        def mutate_evidence(*args, **kwargs):
            resolution = real_shadow(*args, **kwargs)
            (self.skill_dir / "evidence.json").write_text(
                json.dumps({"schemaVersion": 1, "requirements": []}),
                encoding="utf-8",
            )
            return resolution

        with mock.patch.object(
            skill_activation, "resolve_skill_shadow", side_effect=mutate_evidence,
        ):
            with self.assertRaises(server_mod.SkillActivationError) as raised:
                self._create("evidence-drift")
        self.assertEqual(raised.exception.code, "activation_skill_changed")

        _write_skill(self.skills_dir)

        def mutate_dependencies(*args, **kwargs):
            manifest = real_manifest(*args, **kwargs)
            (self.skill_dir / "dependencies.json").write_text(
                json.dumps({"schemaVersion": 1, "skill": "alpha", "capabilities": {}}),
                encoding="utf-8",
            )
            return manifest

        with mock.patch.object(
            skill_activation,
            "resolve_skill_manifest",
            side_effect=mutate_dependencies,
        ):
            with self.assertRaises(server_mod.SkillActivationError) as raised:
                self._create("dependency-drift")
        self.assertEqual(raised.exception.code, "activation_skill_changed")

        _write_skill(self.skills_dir)

        def mutate_resources(*args, **kwargs):
            manifest = real_manifest(*args, **kwargs)
            (self.skill_dir / "code-resources.json").write_text(
                json.dumps({"schemaVersion": 1, "skill": "alpha", "resources": ["changed"]}),
                encoding="utf-8",
            )
            return manifest

        with mock.patch.object(
            skill_activation,
            "resolve_skill_manifest",
            side_effect=mutate_resources,
        ):
            with self.assertRaises(server_mod.SkillActivationError) as raised:
                self._create("resource-drift")
        self.assertEqual(raised.exception.code, "activation_skill_changed")


if __name__ == "__main__":
    unittest.main()
