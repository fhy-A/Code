"""Skill dependency runtime binding contracts for durable AgentRun commands."""

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import server as server_mod


class TestSkillRuntimeBinding(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="code_skill_binding_")
        self.root = Path(self.temporary.name)
        self.data_dir = self.root / "data"
        self.project_dir = self.root / "project"
        self.skills_dir = self.data_dir / "skills"
        self.data_dir.mkdir()
        self.project_dir.mkdir()
        self.skills_dir.mkdir()
        self.config_path = self.data_dir / "config.json"
        self.config_path.write_text(json.dumps({
            "projectRoot": str(self.project_dir),
        }), encoding="utf-8")
        self.patchers = [
            mock.patch.object(server_mod, "DATA_DIR", self.data_dir),
            mock.patch.object(server_mod, "SKILLS_DIR", self.skills_dir),
            mock.patch.object(server_mod, "CONFIG_PATH", self.config_path),
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

    def _create_skill(self, name, capabilities):
        return server_mod.create_skill(
            name=name,
            description=f"{name} dependency runtime",
            body_text="Use the checked capability and then run its command.",
            tools="check_skill_dependencies,run_command",
            dependencies=capabilities,
        )

    def _create_run(self, names, *, permission="bypass"):
        return server_mod._create_agent_run(
            "",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "use the active skill"}],
                "tools": [
                    server_mod._SERVER_TOOL_DEFINITIONS["check_skill_dependencies"],
                    server_mod._SERVER_TOOL_DEFINITIONS["use_skill"],
                    server_mod._SERVER_TOOL_DEFINITIONS["run_command"],
                ],
            },
            "http://127.0.0.1:9",
            [],
            allowed_tools=["check_skill_dependencies", "use_skill", "run_command"],
            permission_profile=permission,
            active_skill_names=list(names),
            active_skill_name=names[0] if len(names) == 1 else "",
            start_worker=False,
        )

    def _managed_paths(self, suffix=""):
        python_root = self.data_dir / "runtime" / "python"
        scripts = python_root / "Scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        python = scripts / f"python{suffix}.exe"
        python.write_bytes(b"synthetic managed python")
        node_modules = self.data_dir / "runtime" / "node" / "node_modules"
        (node_modules / ".bin").mkdir(parents=True, exist_ok=True)
        return python, node_modules

    def _status(self, skill, capability, python=None, node=None, *, capabilities=None):
        capability_ids = list(capabilities or [capability])
        runtime = {}
        requirements = []
        if python is not None:
            runtime["python"] = {"source": "managed", "executable": str(python)}
            requirements.append({
                "id": "python:demo", "type": "python", "name": "demo",
                "available": True, "source": "managed",
            })
        if node is not None:
            runtime["node"] = {"source": "managed", "nodePath": str(node)}
            requirements.append({
                "id": "node:demo", "type": "node", "name": "demo",
                "available": True, "source": "managed",
            })
        return {
            "name": skill,
            "status": "ready",
            "manifestSource": "local",
            "detectedFrom": [],
            "capabilities": [
                {
                    "id": item,
                    "status": "ready",
                    "required": requirements if item == capability else [],
                    "optional": [],
                    "missingOptional": 0,
                }
                for item in capability_ids
            ],
            "installGuidance": {
                "needed": False,
                "selectionRequired": len(capability_ids) > 1 and not capability,
                "selectedCapability": capability,
                "availableCapabilities": capability_ids,
                "requiredMissing": [],
                "optionalMissing": [],
                "steps": [],
                "runtime": runtime,
                "instructions": "ready",
            },
        }

    def _bind(self, run, skill, capability, status):
        result = {
            "ok": True,
            "action": "check_skill_dependencies",
            "skill": skill,
            **status,
        }
        return server_mod._agent_bind_skill_runtime_from_result(
            run,
            "check_skill_dependencies",
            {"name": skill, "capability": capability},
            result,
        )

    def _command_call(self, run, command="python --version"):
        return server_mod._normalize_agent_tool_calls(run, [{
            "index": 0,
            "id": "skill-runtime-command",
            "type": "function",
            "function": {
                "name": "run_command",
                "arguments": json.dumps({"command": command}),
            },
        }], 1)[0]

    def _tool_call(self, run, name, arguments, call_id):
        return server_mod._normalize_agent_tool_calls(run, [{
            "index": 0,
            "id": call_id,
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(arguments),
            },
        }], 1)[0]

    def test_ready_single_capability_check_binds_managed_python_and_node(self):
        self._create_skill("runtime-skill", {
            "runtime": {
                "required": [
                    {"type": "python", "name": "demo"},
                    {"type": "node", "name": "demo"},
                ],
                "optional": [],
            },
        })
        run = self._create_run(["runtime-skill"])
        python, node_modules = self._managed_paths()
        status = self._status("runtime-skill", "runtime", python, node_modules)

        self.assertTrue(self._bind(run, "runtime-skill", "runtime", status))
        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=status,
        ):
            prepared = server_mod._agent_prepare_skill_runtime_environment(run)

        self.assertTrue(prepared["ok"])
        self.assertEqual(prepared["environment"]["VIRTUAL_ENV"], str(python.parents[1]))
        path_entries = prepared["environment"]["PATH"].split(os.pathsep)
        self.assertEqual(path_entries[:2], [str(python.parents[1]), str(python.parent)])
        self.assertEqual(prepared["environment"]["NODE_PATH"].split(os.pathsep)[0], str(node_modules))
        self.assertEqual(path_entries[2], str(node_modules / ".bin"))
        self.assertTrue(prepared["summary"]["managedPythonApplied"])
        self.assertTrue(prepared["summary"]["managedNodeApplied"])
        self.assertNotIn("environment", prepared["summary"])

    def test_agent_check_tool_establishes_and_persists_secret_free_binding(self):
        self._create_skill("checked-skill", {
            "runtime": {
                "required": [{"type": "python", "name": "demo"}],
                "optional": [],
            },
        })
        run = self._create_run(["checked-skill"])
        python, _ = self._managed_paths()
        status = self._status("checked-skill", "runtime", python)
        call = self._tool_call(
            run,
            "check_skill_dependencies",
            {"name": "checked-skill", "capability": "runtime"},
            "checked-skill-call",
        )
        run["pending_tool_calls"] = [call]
        run["status"] = "tools"

        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=status,
        ):
            server_mod._execute_agent_pending_tools(run)

        execution = run["tool_executions"][call["id"]]
        self.assertTrue(execution["result"]["runtimeBinding"]["established"])
        self.assertIn("checked-skill", run["skill_runtime_bindings"])
        record = server_mod._agent_run_record(run)
        self.assertEqual(record["activeSkillNames"], ["checked-skill"])
        self.assertEqual(record["skillRuntimeBindings"]["version"], 1)
        public = server_mod._agent_snapshot(run, 0)["skillRuntimeBindings"]
        self.assertEqual(public, [{
            "skill": "checked-skill",
            "capability": "runtime",
            "managedPython": True,
            "managedNode": False,
        }])
        self.assertNotIn(str(python), json.dumps(public))

    def test_production_chain_check_restart_authorize_resume_and_stale_gate(self):
        self._create_skill("chain-skill", {
            "runtime": {
                "required": [
                    {"type": "python", "name": "demo"},
                    {"type": "node", "name": "demo"},
                ],
                "optional": [],
            },
        })
        run = self._create_run(["chain-skill"], permission="accept")
        python, node_modules = self._managed_paths()
        status = self._status("chain-skill", "runtime", python, node_modules)
        check_call = self._tool_call(
            run,
            "check_skill_dependencies",
            {"name": "chain-skill", "capability": "runtime"},
            "chain-check",
        )
        run["pending_tool_calls"] = [check_call]
        run["status"] = "tools"
        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=status,
        ):
            server_mod._execute_agent_pending_tools(run)

        persisted = server_mod._agent_run_record(run)
        self.assertEqual(
            persisted["skillRuntimeBindings"]["bindings"][0]["capability"],
            "runtime",
        )
        restored = server_mod._agent_run_from_record(persisted)
        stale_restore = server_mod._agent_run_from_record(persisted)
        command = self._command_call(restored, "python --version")
        restored["pending_tool_calls"] = [command]
        restored["status"] = "tools"
        parent_environment = dict(os.environ)

        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=status,
        ), mock.patch.object(server_mod.subprocess, "Popen") as popen:
            server_mod._execute_agent_pending_tools(restored)
        popen.assert_not_called()
        self.assertEqual(restored["status"], "waiting_authorization")
        pending = restored["pending_authorization"]
        server_mod._submit_agent_authorization(
            restored, pending["authorizationId"], "approved",
        )
        self.assertEqual(restored["status"], "waiting_credentials")

        captured = {}

        def execute(arguments, **kwargs):
            captured["arguments"] = dict(arguments)
            captured.update(kwargs)
            return {
                "ok": True,
                "action": "run_command",
                "command": arguments["command"],
                "cwd": str(self.project_dir),
                "exitCode": 0,
                "stdout": "managed runtime applied",
                "stderr": "",
                "cancelled": False,
                "timedOut": False,
                "error": None,
            }

        def resume_worker(target):
            server_mod._execute_agent_pending_tools(target)
            return None

        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=status,
        ) as recheck, mock.patch.object(
            server_mod, "execute_run_command_tool", side_effect=execute,
        ), mock.patch.object(
            server_mod, "_start_agent_worker", side_effect=resume_worker,
        ):
            server_mod._resume_agent_run(restored, [])

        self.assertEqual(recheck.call_count, 1)
        environment = captured["process_environment"]
        self.assertEqual(environment["VIRTUAL_ENV"], str(python.parents[1]))
        self.assertEqual(environment["NODE_PATH"].split(os.pathsep)[0], str(node_modules))
        path_entries = environment["PATH"].split(os.pathsep)
        self.assertEqual(path_entries[:3], [
            str(python.parents[1]),
            str(python.parent),
            str(node_modules / ".bin"),
        ])
        self.assertEqual(captured["runtime_summary"], {
            "version": 1,
            "skills": [{"skill": "chain-skill", "capability": "runtime"}],
            "managedPythonApplied": True,
            "managedNodeApplied": True,
        })
        self.assertEqual(dict(os.environ), parent_environment)
        self.assertEqual(
            restored["tool_executions"][command["id"]]["result"]["stdout"],
            "managed runtime applied",
        )

        stale_command = self._command_call(stale_restore, "python --version")
        stale_restore["pending_tool_calls"] = [stale_command]
        stale_restore["status"] = "tools"
        python.unlink()
        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=status,
        ), mock.patch.object(server_mod.subprocess, "Popen") as stale_popen:
            server_mod._execute_agent_pending_tools(stale_restore)
        stale_popen.assert_not_called()
        stale_result = stale_restore["tool_executions"][stale_command["id"]]["result"]
        self.assertEqual(stale_result["errorCode"], "skill_dependency_runtime_stale")
        self.assertEqual(stale_result["reason"], "managed_runtime_path_unsafe")
        self.assertEqual(stale_restore["skill_runtime_bindings"], {})

    def test_use_skill_binds_only_one_explicit_ready_capability(self):
        self._create_skill("single-use", {
            "runtime": {
                "required": [{"type": "python", "name": "demo"}],
                "optional": [],
            },
        })
        run = self._create_run(["single-use"])
        python, _ = self._managed_paths()
        status = self._status("single-use", "runtime", python)
        call = self._tool_call(run, "use_skill", {"name": "single-use"}, "single-use-call")
        run["pending_tool_calls"] = [call]
        run["status"] = "tools"
        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=status,
        ):
            server_mod._execute_agent_pending_tools(run)
        self.assertEqual(run["skill_runtime_bindings"]["single-use"]["capability"], "runtime")

        self._create_skill("multi-use", {
            "create": {
                "required": [{"type": "python", "name": "demo"}],
                "optional": [],
            },
            "inspect": {
                "required": [{"type": "node", "name": "demo"}],
                "optional": [],
            },
        })
        multi_run = self._create_run(["multi-use"])
        multi = self._status("multi-use", "", capabilities=["create", "inspect"])
        multi_call = self._tool_call(
            multi_run, "use_skill", {"name": "multi-use"}, "multi-use-call",
        )
        multi_run["pending_tool_calls"] = [multi_call]
        multi_run["status"] = "tools"
        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=multi,
        ):
            server_mod._execute_agent_pending_tools(multi_run)
        self.assertEqual(multi_run["skill_runtime_bindings"], {})

    def test_unchecked_dependent_skill_blocks_before_authorization_and_popen(self):
        self._create_skill("unchecked-skill", {
            "runtime": {
                "required": [{"type": "python", "name": "demo"}],
                "optional": [],
            },
        })
        run = self._create_run(["unchecked-skill"], permission="accept")
        run["pending_tool_calls"] = [self._command_call(run)]
        run["status"] = "tools"

        with mock.patch.object(server_mod.subprocess, "Popen") as popen:
            server_mod._execute_agent_pending_tools(run)

        popen.assert_not_called()
        execution = run["tool_executions"]["skill-runtime-command"]
        self.assertEqual(execution["result"]["errorCode"], "skill_dependency_check_required")
        self.assertFalse(execution["result"]["retryable"])
        self.assertIsNone(run.get("pending_authorization"))

    def test_missing_dependency_managed_install_authorizes_then_resumes_without_runtime(self):
        self._create_skill("install-skill", {
            "runtime": {
                "required": [{"type": "python", "name": "demo"}],
                "optional": [],
            },
        })
        command = "python -m pip install code-test-never-install"
        for permission in ("accept", "bypass"):
            with self.subTest(permission=permission):
                run = self._create_run(["install-skill"], permission=permission)
                call = self._command_call(run, command)
                run["pending_tool_calls"] = [call]
                run["status"] = "tools"

                with mock.patch.object(server_mod.subprocess, "Popen") as popen:
                    server_mod._execute_agent_pending_tools(run)
                popen.assert_not_called()
                self.assertEqual(run["status"], "waiting_authorization")
                execution = run["tool_executions"][call["id"]]
                self.assertTrue(execution["dependencyInstall"])
                self.assertEqual(execution["dependencyInstallKind"], "managed")
                self.assertIsNone(execution["result"])
                self.assertEqual(run["skill_runtime_bindings"], {})

                pending = run["pending_authorization"]
                server_mod._submit_agent_authorization(
                    run, pending["authorizationId"], "approved",
                )
                captured = {}

                def execute(arguments, **kwargs):
                    captured["arguments"] = dict(arguments)
                    captured["kwargs"] = dict(kwargs)
                    return {
                        "ok": True,
                        "action": "run_command",
                        "command": arguments["command"],
                        "cwd": str(self.project_dir),
                        "exitCode": 0,
                        "stdout": "managed install completed",
                        "stderr": "",
                        "cancelled": False,
                        "timedOut": False,
                        "error": None,
                    }

                def resume_worker(target):
                    server_mod._execute_agent_pending_tools(target)
                    return None

                with mock.patch.object(
                    server_mod, "execute_run_command_tool", side_effect=execute,
                ) as command_executor, mock.patch.object(
                    server_mod, "_start_agent_worker", side_effect=resume_worker,
                ):
                    server_mod._resume_agent_run(run, [])

                command_executor.assert_called_once()
                self.assertEqual(captured["arguments"]["command"], command)
                self.assertNotIn("process_environment", captured["kwargs"])
                self.assertNotIn("runtime_summary", captured["kwargs"])
                self.assertEqual(run["skill_runtime_bindings"], {})
                self.assertEqual(
                    run["tool_executions"][call["id"]]["result"]["stdout"],
                    "managed install completed",
                )

    def test_missing_dependency_system_and_environment_installs_never_execute(self):
        self._create_skill("blocked-install-skill", {
            "runtime": {
                "required": [{"type": "python", "name": "demo"}],
                "optional": [],
            },
        })
        cases = (
            ("system", "winget install Pandoc.Pandoc"),
            (
                "environment",
                '$p = "$env:APPDATA\\npm\\pdftoppm.cmd"; '
                'Set-Content -Path $p -Value "@echo off"',
            ),
        )
        for expected_kind, command in cases:
            with self.subTest(kind=expected_kind):
                run = self._create_run(["blocked-install-skill"])
                call = self._command_call(run, command)
                run["pending_tool_calls"] = [call]
                run["status"] = "tools"
                with mock.patch.object(server_mod.subprocess, "Popen") as popen:
                    server_mod._execute_agent_pending_tools(run)
                popen.assert_not_called()
                execution = run["tool_executions"][call["id"]]
                self.assertEqual(execution["dependencyInstallKind"], expected_kind)
                self.assertIn("outside Code", execution["error"])
                self.assertIsNone(run.get("pending_authorization"))
                self.assertEqual(run["skill_runtime_bindings"], {})

    def test_multi_capability_without_explicit_selection_never_binds(self):
        self._create_skill("multi-capability", {
            "create": {
                "required": [{"type": "python", "name": "demo"}],
                "optional": [],
            },
            "inspect": {
                "required": [{"type": "node", "name": "demo"}],
                "optional": [],
            },
        })
        run = self._create_run(["multi-capability"])
        result = {
            "ok": True,
            "action": "check_skill_dependencies",
            "skill": "multi-capability",
            **self._status(
                "multi-capability", "", capabilities=["create", "inspect"],
            ),
        }

        bound = server_mod._agent_bind_skill_runtime_from_result(
            run,
            "check_skill_dependencies",
            {"name": "multi-capability"},
            result,
        )

        self.assertFalse(bound)
        self.assertEqual(run["skill_runtime_bindings"], {})

    def test_multiple_active_skills_require_every_binding_and_reject_conflict(self):
        capabilities = {
            "runtime": {
                "required": [{"type": "python", "name": "demo"}],
                "optional": [],
            },
        }
        self._create_skill("skill-one", capabilities)
        self._create_skill("skill-two", capabilities)
        run = self._create_run(["skill-one", "skill-two"])
        python, _ = self._managed_paths()
        first = self._status("skill-one", "runtime", python)
        second = self._status("skill-two", "runtime", python)
        self.assertTrue(self._bind(run, "skill-one", "runtime", first))

        missing = server_mod._agent_prepare_skill_runtime_environment(run)
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["errorCode"], "skill_dependency_check_required")
        self.assertEqual(missing["pendingSkills"][0]["skill"], "skill-two")

        self.assertTrue(self._bind(run, "skill-two", "runtime", second))
        with mock.patch.object(
            server_mod,
            "get_single_skill_dependency_status",
            side_effect=lambda name, capability="": first if name == "skill-one" else second,
        ):
            merged = server_mod._agent_prepare_skill_runtime_environment(run)
        self.assertTrue(merged["ok"])
        self.assertEqual(merged["summary"]["skills"], [
            {"skill": "skill-one", "capability": "runtime"},
            {"skill": "skill-two", "capability": "runtime"},
        ])

        python_alt, _ = self._managed_paths("-alt")
        second_alt = self._status("skill-two", "runtime", python_alt)
        self.assertTrue(self._bind(run, "skill-two", "runtime", second_alt))
        with mock.patch.object(
            server_mod,
            "get_single_skill_dependency_status",
            side_effect=lambda name, capability="": first if name == "skill-one" else second_alt,
        ):
            conflict = server_mod._agent_prepare_skill_runtime_environment(run)
        self.assertFalse(conflict["ok"])
        self.assertEqual(conflict["errorCode"], "skill_dependency_runtime_stale")
        self.assertEqual(conflict["reason"], "managed_runtime_conflict")

    def test_accept_waits_without_launch_and_resume_rechecks_before_execution(self):
        self._create_skill("accept-skill", {
            "runtime": {
                "required": [{"type": "python", "name": "demo"}],
                "optional": [],
            },
        })
        run = self._create_run(["accept-skill"], permission="accept")
        python, _ = self._managed_paths()
        status = self._status("accept-skill", "runtime", python)
        self.assertTrue(self._bind(run, "accept-skill", "runtime", status))
        call = self._command_call(run)
        run["pending_tool_calls"] = [call]
        run["status"] = "tools"

        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=status,
        ) as recheck, mock.patch.object(server_mod.subprocess, "Popen") as popen:
            server_mod._execute_agent_pending_tools(run)
        popen.assert_not_called()
        self.assertEqual(run["status"], "waiting_authorization")
        self.assertEqual(recheck.call_count, 1)

        execution = run["tool_executions"][call["id"]]
        execution["status"] = "authorized"
        execution["authorizationDecision"] = "approved"
        run["pending_authorization"] = None
        run["status"] = "tools"
        captured = {}

        def execute(arguments, **kwargs):
            captured.update(kwargs)
            return {
                "ok": True, "action": "run_command", "command": arguments["command"],
                "cwd": str(self.project_dir), "exitCode": 0, "stdout": "ready",
                "stderr": "", "cancelled": False, "timedOut": False, "error": None,
            }

        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=status,
        ) as resume_recheck, mock.patch.object(
            server_mod, "execute_run_command_tool", side_effect=execute,
        ):
            server_mod._execute_agent_pending_tools(run)

        self.assertEqual(resume_recheck.call_count, 1)
        self.assertEqual(captured["process_environment"]["VIRTUAL_ENV"], str(python.parents[1]))
        self.assertTrue(captured["runtime_summary"]["managedPythonApplied"])

    def test_uninstall_path_manifest_change_and_restart_all_fail_closed(self):
        self._create_skill("restart-skill", {
            "runtime": {
                "required": [{"type": "python", "name": "demo"}],
                "optional": [],
            },
        })
        run = self._create_run(["restart-skill"])
        python, _ = self._managed_paths()
        status = self._status("restart-skill", "runtime", python)
        self.assertTrue(self._bind(run, "restart-skill", "runtime", status))
        record = server_mod._agent_run_record(run)
        restored = server_mod._agent_run_from_record(record)
        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=status,
        ):
            self.assertTrue(server_mod._agent_prepare_skill_runtime_environment(restored)["ok"])

        python.unlink()
        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=status,
        ):
            missing = server_mod._agent_prepare_skill_runtime_environment(restored)
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["errorCode"], "skill_dependency_runtime_stale")
        self.assertEqual(restored["skill_runtime_bindings"], {})

        python, _ = self._managed_paths()
        self.assertTrue(self._bind(run, "restart-skill", "runtime", status))
        manifest = self.skills_dir / "restart-skill" / "dependencies.json"
        source = json.loads(manifest.read_text(encoding="utf-8"))
        source["capabilities"]["runtime"]["optional"] = [
            {"type": "command", "name": "git"},
        ]
        manifest.write_text(json.dumps(source), encoding="utf-8")
        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=status,
        ):
            changed = server_mod._agent_prepare_skill_runtime_environment(run)
        self.assertFalse(changed["ok"])
        self.assertEqual(changed["reason"], "skill_manifest_changed")

        self.assertTrue(self._bind(restored, "restart-skill", "runtime", status))
        not_ready = json.loads(json.dumps(status))
        not_ready["status"] = "unavailable"
        not_ready["capabilities"][0]["status"] = "unavailable"
        not_ready["installGuidance"]["needed"] = True
        not_ready["installGuidance"]["requiredMissing"] = [{"id": "python:demo"}]
        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=not_ready,
        ):
            unavailable = server_mod._agent_prepare_skill_runtime_environment(restored)
        self.assertFalse(unavailable["ok"])
        self.assertEqual(unavailable["errorCode"], "skill_dependency_runtime_stale")

        tampered = json.loads(json.dumps(record))
        tampered["skillRuntimeBindings"]["bindings"][0]["checkedStatus"] = "partial"
        restored_tampered = server_mod._agent_run_from_record(tampered)
        self.assertEqual(restored_tampered["skill_runtime_bindings"], {})
        rejected = server_mod._agent_prepare_skill_runtime_environment(restored_tampered)
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["errorCode"], "skill_dependency_check_required")

    def test_legacy_no_skill_and_dependency_free_runs_keep_empty_environment(self):
        no_skill = self._create_run([])
        prepared = server_mod._agent_prepare_skill_runtime_environment(no_skill)
        self.assertTrue(prepared["ok"])
        self.assertIsNone(prepared["environment"])

        self._create_skill("dependency-free", {})
        dependency_free = self._create_run(["dependency-free"])
        prepared = server_mod._agent_prepare_skill_runtime_environment(dependency_free)
        self.assertTrue(prepared["ok"])
        self.assertIsNone(prepared["environment"])

        legacy = server_mod._agent_run_record(dependency_free)
        legacy.pop("activeSkillNames", None)
        legacy.pop("activeSkillDependencies", None)
        legacy.pop("skillRuntimeBindings", None)
        restored = server_mod._agent_run_from_record(legacy)
        self.assertEqual(restored["active_skill_names"], [])
        self.assertEqual(restored["skill_runtime_bindings"], {})
        self.assertTrue(server_mod._agent_prepare_skill_runtime_environment(restored)["ok"])

    def test_process_environment_does_not_mutate_parent_and_rejects_unsafe_paths(self):
        self._create_skill("safe-skill", {
            "runtime": {
                "required": [{"type": "python", "name": "demo"}],
                "optional": [],
            },
        })
        run = self._create_run(["safe-skill"])
        python, _ = self._managed_paths()
        status = self._status("safe-skill", "runtime", python)
        self.assertTrue(self._bind(run, "safe-skill", "runtime", status))
        parent_environment = dict(os.environ)
        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=status,
        ):
            prepared = server_mod._agent_prepare_skill_runtime_environment(run)
        self.assertTrue(prepared["ok"])
        self.assertEqual(dict(os.environ), parent_environment)

        outside = self.root / "outside-python.exe"
        outside.write_bytes(b"outside")
        outside_status = self._status("safe-skill", "runtime", outside)
        self.assertTrue(self._bind(run, "safe-skill", "runtime", outside_status))
        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=outside_status,
        ):
            escaped = server_mod._agent_prepare_skill_runtime_environment(run)
        self.assertFalse(escaped["ok"])
        self.assertEqual(escaped["reason"], "managed_runtime_path_unsafe")

        self.assertTrue(self._bind(run, "safe-skill", "runtime", status))
        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=status,
        ), mock.patch.object(
            server_mod, "_path_stat_is_reparse", side_effect=lambda info: info.st_mode == python.lstat().st_mode,
        ):
            reparse = server_mod._agent_prepare_skill_runtime_environment(run)
        self.assertFalse(reparse["ok"])
        self.assertEqual(reparse["reason"], "managed_runtime_path_unsafe")

        system_status = self._status("safe-skill", "runtime")
        system_status["installGuidance"]["runtime"] = {
            "python": {"source": "system", "executable": str(outside)},
            "node": {"source": "app", "nodePath": str(outside.parent)},
        }
        self.assertTrue(self._bind(run, "safe-skill", "runtime", system_status))
        with mock.patch.object(
            server_mod, "get_single_skill_dependency_status", return_value=system_status,
        ):
            nonmanaged = server_mod._agent_prepare_skill_runtime_environment(run)
        self.assertTrue(nonmanaged["ok"])
        self.assertIsNone(nonmanaged["environment"])
        self.assertFalse(nonmanaged["summary"]["managedPythonApplied"])
        self.assertFalse(nonmanaged["summary"]["managedNodeApplied"])

    def test_run_command_uses_only_supplied_process_environment_and_public_summary(self):
        environment = dict(os.environ)
        environment["SKILL_RUNTIME_TEST"] = "process-only"
        summary = {
            "version": 1,
            "skills": [{"skill": "safe-skill", "capability": "runtime"}],
            "managedPythonApplied": True,
            "managedNodeApplied": False,
        }
        process = mock.Mock()
        process.stdout = mock.Mock()
        process.stderr = mock.Mock()
        process.stdout.fileno.return_value = -1
        process.stderr.fileno.return_value = -1
        process.poll.return_value = 0
        process.wait.return_value = 0

        with mock.patch.object(
            server_mod, "resolve_project_path", return_value=(self.project_dir, ""),
        ), mock.patch.object(
            server_mod.subprocess, "Popen", return_value=process,
        ) as popen, mock.patch.object(
            server_mod.threading, "Thread",
        ):
            result = server_mod.execute_run_command_tool(
                {"command": "python --version"},
                process_environment=environment,
                runtime_summary=summary,
            )

        self.assertIs(popen.call_args.kwargs["env"], environment)
        self.assertEqual(result["skillRuntime"], summary)
        self.assertNotIn("environment", result)
        self.assertNotIn("SKILL_RUNTIME_TEST", json.dumps(result))
        self.assertNotIn("SKILL_RUNTIME_TEST", os.environ)


if __name__ == "__main__":
    unittest.main()
