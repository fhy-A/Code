import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import skill_dependencies as dependencies


def _manifest(skill="demo"):
    return {
        "schemaVersion": 1,
        "skill": skill,
        "capabilities": {
            "create": {
                "required": [
                    {"type": "python", "name": "demo-python", "importName": "demo_python"},
                    {"type": "node", "name": "demo-node", "version": "1.2.3"},
                ],
                "optional": [
                    {"type": "command", "name": "demo-cli"},
                ],
            },
            "inspect": {
                "required": [
                    {
                        "type": "command",
                        "name": "demo-cli",
                        "installHint": "Windows PowerShell: winget install --id Demo.Cli --exact",
                    },
                ],
            },
        },
    }


class TestDependencyManifest(unittest.TestCase):
    def test_normalizes_capabilities_and_requirements(self):
        manifest = dependencies.normalize_manifest(_manifest(), expected_skill="demo")
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["skill"], "demo")
        self.assertEqual([item["id"] for item in manifest["capabilities"]], ["create", "inspect"])
        self.assertEqual(manifest["capabilities"][0]["required"][0]["id"], "python:demo-python")
        self.assertTrue(manifest["capabilities"][0]["optional"][0]["optional"])
        self.assertEqual(
            manifest["capabilities"][1]["required"][0]["installHint"],
            "Windows PowerShell: winget install --id Demo.Cli --exact",
        )

    def test_rejects_dependency_names_that_can_escape_managed_runtimes(self):
        for dep_type, name in (("node", "../outside"), ("python", "../../outside"), ("command", "bin/tool")):
            payload = _manifest()
            payload["capabilities"]["create"]["required"] = [{"type": dep_type, "name": name}]
            with self.subTest(dep_type=dep_type), self.assertRaisesRegex(
                dependencies.DependencyManifestError, "invalid dependency name"
            ):
                dependencies.normalize_manifest(payload, expected_skill="demo")


class TestDependencyDiscovery(unittest.TestCase):
    def test_discovers_python_requirements_and_static_imports(self):
        with tempfile.TemporaryDirectory() as temp:
            skill_dir = Path(temp) / "copied-python"
            scripts = skill_dir / "scripts"
            scripts.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("# Copied Skill", encoding="utf-8")
            (skill_dir / "requirements.txt").write_text(
                "requests>=2.28\nPillow~=10.0\n",
                encoding="utf-8",
            )
            (skill_dir / "requirements-dev.txt").write_text("pytest==9.1.1\n", encoding="utf-8")
            (skill_dir / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
            helpers = scripts / "office" / "helpers"
            helpers.mkdir(parents=True)
            (helpers / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
            (scripts / "run.py").write_text(
                "import json\nimport requests\nimport yaml\nfrom PIL import Image\nimport helper\nfrom helpers import VALUE\n",
                encoding="utf-8",
            )

            manifest = dependencies.discover_skill_manifest(skill_dir)

        self.assertEqual(manifest["source"], "detected")
        self.assertIn("requirements.txt", manifest["detectedFrom"])
        self.assertIn("Python imports", manifest["detectedFrom"])
        capability = next(item for item in manifest["capabilities"] if item["id"] == "python-runtime")
        required = {item["name"]: item for item in capability["required"]}
        optional = {item["name"]: item for item in capability["optional"]}
        self.assertEqual(required["requests"]["minimumVersion"], "2.28")
        self.assertEqual(required["Pillow"]["minimumVersion"], "10.0")
        self.assertEqual(required["PyYAML"]["importName"], "yaml")
        self.assertEqual(optional["pytest"]["version"], "9.1.1")
        self.assertNotIn("json", required)
        self.assertNotIn("helper", required)
        self.assertNotIn("helpers", required)

    def test_discovers_package_json_and_javascript_imports(self):
        with tempfile.TemporaryDirectory() as temp:
            skill_dir = Path(temp) / "copied-node"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Copied Skill", encoding="utf-8")
            (skill_dir / "package.json").write_text(json.dumps({
                "dependencies": {"lodash": "^4.17.0"},
                "optionalDependencies": {"sharp": "0.33.0"},
            }), encoding="utf-8")
            (skill_dir / "index.js").write_text(
                "import chalk from 'chalk';\nimport fs from 'node:fs';\nconst helper = require('./helper');\n",
                encoding="utf-8",
            )
            (skill_dir / "widget.tsx").write_text(
                "import React from 'react';\nimport localWidget from './widget';\n",
                encoding="utf-8",
            )

            manifest = dependencies.discover_skill_manifest(skill_dir)

        capability = next(item for item in manifest["capabilities"] if item["id"] == "node-runtime")
        required = {item["name"]: item for item in capability["required"]}
        optional = {item["name"]: item for item in capability["optional"]}
        self.assertEqual(required["lodash"]["minimumVersion"], "4.17.0")
        self.assertIn("chalk", required)
        self.assertIn("react", required)
        self.assertEqual(optional["sharp"]["version"], "0.33.0")
        self.assertNotIn("fs", required)

    def test_discovers_explicit_install_commands_from_copied_skill_markdown(self):
        with tempfile.TemporaryDirectory() as temp:
            skill_dir = Path(temp) / "documented-installer"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                """# Documented installer

## Installation

`python -m pip install requests>=2.31 PyYAML`

```bash
npm install @scope/tool@1.2.0 sharp
```

This paragraph discusses dependencies but does not declare another package.
""",
                encoding="utf-8",
            )

            manifest = dependencies.discover_skill_manifest(skill_dir)

        self.assertEqual(manifest["source"], "detected")
        self.assertIn("SKILL.md install commands", manifest["detectedFrom"])
        capabilities = {item["id"]: item for item in manifest["capabilities"]}
        python_required = {item["name"]: item for item in capabilities["python-runtime"]["required"]}
        node_required = {item["name"]: item for item in capabilities["node-runtime"]["required"]}
        self.assertEqual(python_required["requests"]["minimumVersion"], "2.31")
        self.assertEqual(python_required["PyYAML"]["importName"], "yaml")
        self.assertEqual(node_required["@scope/tool"]["version"], "1.2.0")
        self.assertIn("sharp", node_required)

    def test_plain_markdown_dependency_discussion_is_not_auto_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            skill_dir = Path(temp) / "workflow-only"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "# Workflow\n\nReview the project's dependencies and installation plan.\n",
                encoding="utf-8",
            )

            manifest = dependencies.discover_skill_manifest(skill_dir)

        self.assertIsNone(manifest)

    def test_explicit_manifest_remains_the_highest_priority(self):
        with tempfile.TemporaryDirectory() as temp:
            skill_dir = Path(temp) / "explicit"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Explicit Skill", encoding="utf-8")
            (skill_dir / "requirements.txt").write_text("requests\n", encoding="utf-8")
            (skill_dir / "dependencies.json").write_text(json.dumps({
                "schemaVersion": 1,
                "skill": "explicit",
                "capabilities": {
                    "default": {"required": [{"type": "command", "name": "git"}]},
                },
            }), encoding="utf-8")

            manifest = dependencies.resolve_skill_manifest(skill_dir)

        self.assertEqual(manifest["source"], "local")
        requirement = manifest["capabilities"][0]["required"][0]
        self.assertEqual(requirement["id"], "command:git")

    def test_builds_managed_install_and_user_cooperation_guidance(self):
        inspection = {
            "capabilities": [{
                "id": "runtime",
                "required": [
                    {"id": "python:requests", "type": "python", "name": "requests", "minimumVersion": "2.28", "available": False},
                    {
                        "id": "command:pdftoppm",
                        "type": "command",
                        "name": "pdftoppm",
                        "available": False,
                        "installHint": "Windows PowerShell: winget install --id Poppler.Exact --exact",
                    },
                ],
                "optional": [],
            }],
        }
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            dependencies,
            "_managed_python",
            return_value=(r"C:\Python\python.exe", "system"),
        ):
            guidance = dependencies.build_install_guidance(inspection, data_dir=temp)

        self.assertTrue(guidance["needed"])
        self.assertEqual(guidance["runtime"]["python"]["source"], "system")
        self.assertEqual(guidance["runtime"]["python"]["executable"], r"C:\Python\python.exe")
        python_step = next(item for item in guidance["steps"] if item["type"] == "python")
        command_step = next(item for item in guidance["steps"] if item["type"] == "command")
        self.assertEqual(len(python_step["commands"]), 2)
        self.assertIn("venv", python_step["commands"][0]["command"])
        self.assertIn("requests>=2.28", python_step["commands"][1]["command"])
        self.assertEqual(command_step["strategy"], "user_cooperation")
        self.assertEqual(command_step["commands"], [])
        self.assertEqual(command_step["installHints"], [{
            "requirement": "command:pdftoppm",
            "text": "Windows PowerShell: winget install --id Poppler.Exact --exact",
        }])

    def test_ready_managed_dependency_keeps_runtime_execution_context(self):
        inspection = {
            "capabilities": [{
                "id": "runtime",
                "required": [{
                    "id": "python:demo",
                    "type": "python",
                    "name": "demo",
                    "available": True,
                    "source": "managed",
                }],
                "optional": [],
            }],
        }
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            dependencies,
            "_managed_python",
            return_value=(str(Path(temp) / "runtime" / "python" / "python.exe"), "managed"),
        ):
            guidance = dependencies.build_install_guidance(inspection, data_dir=temp)

        self.assertFalse(guidance["needed"])
        self.assertEqual(guidance["runtime"]["python"]["source"], "managed")
        self.assertTrue(guidance["runtime"]["python"]["executable"].endswith("python.exe"))

    def test_multi_capability_report_requires_one_explicit_selection(self):
        inspection = {
            "capabilities": [
                {
                    "id": "create",
                    "required": [{
                        "id": "node:docx",
                        "type": "node",
                        "name": "docx",
                        "available": True,
                    }],
                    "optional": [],
                },
                {
                    "id": "read",
                    "required": [{
                        "id": "command:pandoc",
                        "type": "command",
                        "name": "pandoc",
                        "available": False,
                    }],
                    "optional": [],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            report = dependencies.build_install_guidance(inspection, data_dir=temp)
            create = dependencies.build_install_guidance(
                inspection,
                data_dir=temp,
                capability_id="create",
            )
            read = dependencies.build_install_guidance(
                inspection,
                data_dir=temp,
                capability_id="read",
            )

        self.assertTrue(report["selectionRequired"])
        self.assertFalse(report["needed"])
        self.assertEqual(report["availableCapabilities"], ["create", "read"])
        self.assertEqual(report["steps"], [])
        self.assertFalse(create["selectionRequired"])
        self.assertFalse(create["needed"])
        self.assertEqual(create["selectedCapability"], "create")
        self.assertTrue(read["needed"])
        self.assertEqual(read["selectedCapability"], "read")
        self.assertEqual(read["requiredMissing"][0]["id"], "command:pandoc")
        self.assertEqual(read["steps"][0]["strategy"], "user_cooperation")

    def test_rejects_unknown_dependency_capability(self):
        inspection = {
            "capabilities": [{"id": "create", "required": [], "optional": []}],
        }
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(
            dependencies.DependencyManifestError
        ):
            dependencies.build_install_guidance(
                inspection,
                data_dir=temp,
                capability_id="render",
            )

    def test_rejects_wrong_schema_skill_and_dependency_type(self):
        cases = []
        wrong_schema = _manifest()
        wrong_schema["schemaVersion"] = 2
        cases.append(wrong_schema)
        wrong_skill = _manifest("other")
        cases.append(wrong_skill)
        wrong_type = _manifest()
        wrong_type["capabilities"]["create"]["required"][0]["type"] = "installer"
        cases.append(wrong_type)
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(dependencies.DependencyManifestError):
                dependencies.normalize_manifest(payload, expected_skill="demo")

    def test_bundled_manifest_is_fallback_for_existing_user_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            local = root / "local" / "demo"
            bundled = root / "bundled" / "demo"
            local.mkdir(parents=True)
            bundled.mkdir(parents=True)
            (local / "SKILL.md").write_text("# existing user copy", encoding="utf-8")
            (bundled / "dependencies.json").write_text(json.dumps(_manifest()), encoding="utf-8")

            manifest = dependencies.load_skill_manifest(local, root / "bundled")

        self.assertEqual(manifest["source"], "bundled")
        self.assertEqual(manifest["skill"], "demo")


class TestDependencyInspection(unittest.TestCase):
    @staticmethod
    def _command_manifest(requirements):
        return dependencies.normalize_manifest({
            "schemaVersion": 1,
            "skill": "system-tools",
            "capabilities": {
                "run": {"required": requirements},
            },
        }, expected_skill="system-tools")

    @staticmethod
    def _missing_command_results(*names):
        return {
            f"command:{name}": {
                "installed": False,
                "available": False,
                "detectedVersion": "",
                "source": "",
                "executable": "",
                "reason": "not_installed",
            }
            for name in names
        }

    def test_windows_missing_bash_and_qpdf_receive_trusted_default_hints(self):
        manifest = self._command_manifest([
            {"type": "command", "name": "bash"},
            {"type": "command", "name": "qpdf"},
            {"type": "command", "name": "renderer"},
        ])
        identity_before = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        with (
            mock.patch.object(dependencies.sys, "platform", "win32"),
            mock.patch.object(
                dependencies,
                "_probe_commands",
                return_value=self._missing_command_results("bash", "qpdf", "renderer"),
            ),
            tempfile.TemporaryDirectory() as temp,
        ):
            result = dependencies.inspect_manifest(manifest, app_dir=temp, data_dir=temp)
            guidance = dependencies.build_install_guidance(result, data_dir=temp)

        required = {
            item["name"]: item
            for item in result["capabilities"][0]["required"]
        }
        self.assertEqual(
            required["bash"]["installHint"],
            "winget install --id Git.Git --exact --source winget",
        )
        self.assertEqual(
            required["qpdf"]["installHint"],
            "winget install --id QPDF.QPDF --exact --source winget",
        )
        self.assertNotIn("installHint", required["renderer"])
        command_step = next(step for step in guidance["steps"] if step["type"] == "command")
        self.assertEqual(command_step["commands"], [])
        self.assertEqual(command_step["installHints"], [
            {
                "requirement": "command:bash",
                "text": "winget install --id Git.Git --exact --source winget",
            },
            {
                "requirement": "command:qpdf",
                "text": "winget install --id QPDF.QPDF --exact --source winget",
            },
        ])
        self.assertEqual(json.dumps(manifest, ensure_ascii=False, sort_keys=True), identity_before)

    def test_manifest_install_hint_precedes_windows_default(self):
        manifest = self._command_manifest([{
            "type": "command",
            "name": "bash",
            "installHint": "Use the approved enterprise Git package",
        }])
        with (
            mock.patch.object(dependencies.sys, "platform", "win32"),
            mock.patch.object(
                dependencies,
                "_probe_commands",
                return_value=self._missing_command_results("bash"),
            ),
        ):
            result = dependencies.inspect_manifest(manifest, app_dir=".", data_dir=".")

        requirement = result["capabilities"][0]["required"][0]
        self.assertEqual(requirement["installHint"], "Use the approved enterprise Git package")

    def test_non_windows_does_not_derive_windows_install_hints(self):
        manifest = self._command_manifest([
            {"type": "command", "name": "bash"},
            {"type": "command", "name": "qpdf"},
        ])
        with (
            mock.patch.object(dependencies.sys, "platform", "linux"),
            mock.patch.object(
                dependencies,
                "_probe_commands",
                return_value=self._missing_command_results("bash", "qpdf"),
            ),
        ):
            result = dependencies.inspect_manifest(manifest, app_dir=".", data_dir=".")

        for requirement in result["capabilities"][0]["required"]:
            self.assertNotIn("installHint", requirement)

    def test_reports_partial_status_and_optional_gaps(self):
        manifest = dependencies.normalize_manifest(_manifest(), expected_skill="demo")
        manifest["source"] = "local"
        with (
            mock.patch.object(dependencies, "_probe_python", return_value={
                "python:demo-python": {
                    "installed": True, "available": True, "detectedVersion": "1.0", "source": "system", "reason": "",
                }
            }),
            mock.patch.object(dependencies, "_probe_node", return_value={
                "node:demo-node": {
                    "installed": True, "available": True, "detectedVersion": "1.2.3", "source": "managed", "reason": "",
                }
            }),
            mock.patch.object(dependencies, "_probe_commands", return_value={
                "command:demo-cli": {
                    "installed": False, "available": False, "detectedVersion": "", "source": "", "reason": "not_installed",
                }
            }),
        ):
            result = dependencies.inspect_manifest(manifest, app_dir=".", data_dir=".")

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["capabilities"][0]["status"], "ready")
        self.assertEqual(result["capabilities"][0]["missingOptional"], 1)
        self.assertEqual(result["capabilities"][1]["status"], "unavailable")

    def test_managed_node_package_precedes_app_copy_and_checks_version(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            managed = root / "data" / "runtime" / "node" / "node_modules" / "demo-node"
            app_copy = root / "app" / "node_modules" / "demo-node"
            managed.mkdir(parents=True)
            app_copy.mkdir(parents=True)
            (managed / "package.json").write_text('{"version":"1.2.3"}', encoding="utf-8")
            (app_copy / "package.json").write_text('{"version":"9.9.9"}', encoding="utf-8")
            requirement = dependencies._normalize_requirement({
                "type": "node", "name": "demo-node", "version": "1.2.3",
            })

            result = dependencies._probe_node([requirement], root / "app", root / "data")

        self.assertTrue(result["node:demo-node"]["available"])
        self.assertEqual(result["node:demo-node"]["detectedVersion"], "1.2.3")
        self.assertEqual(result["node:demo-node"]["source"], "managed")

    def test_windows_command_probe_finds_standard_install_locations(self):
        requirements = [
            dependencies._normalize_requirement({"type": "command", "name": "tesseract"}),
            dependencies._normalize_requirement({"type": "command", "name": "qpdf"}),
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tesseract = root / "Tesseract-OCR" / "tesseract.exe"
            qpdf = root / "qpdf 12.3.2" / "bin" / "qpdf.exe"
            tesseract.parent.mkdir(parents=True)
            qpdf.parent.mkdir(parents=True)
            tesseract.write_text("", encoding="utf-8")
            qpdf.write_text("", encoding="utf-8")
            with (
                mock.patch.object(dependencies.sys, "platform", "win32"),
                mock.patch.object(dependencies.shutil, "which", return_value=None),
                mock.patch.object(dependencies, "_windows_registered_path", return_value=""),
                mock.patch.dict(dependencies.os.environ, {
                    "ProgramFiles": str(root),
                    "ProgramFiles(x86)": "",
                    "LOCALAPPDATA": str(root / "local"),
                }),
            ):
                result = dependencies._probe_commands(requirements, root / "data")

        self.assertTrue(result["command:tesseract"]["available"])
        self.assertEqual(Path(result["command:tesseract"]["executable"]), tesseract)
        self.assertTrue(result["command:qpdf"]["available"])
        self.assertEqual(Path(result["command:qpdf"]["executable"]), qpdf)

    def test_bash_probe_finds_standard_git_for_windows_roots(self):
        locations = (
            ("ProgramFiles", Path("Git") / "bin" / "bash.exe"),
            ("ProgramFiles", Path("Git") / "usr" / "bin" / "bash.exe"),
            ("ProgramFiles(x86)", Path("Git") / "bin" / "bash.exe"),
            ("ProgramFiles(x86)", Path("Git") / "usr" / "bin" / "bash.exe"),
            ("LOCALAPPDATA", Path("Programs") / "Git" / "bin" / "bash.exe"),
            ("LOCALAPPDATA", Path("Programs") / "Git" / "usr" / "bin" / "bash.exe"),
        )
        for root_name, relative in locations:
            with self.subTest(root=root_name, relative=str(relative)), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                environment = {
                    "ProgramFiles": str(root / "machine"),
                    "ProgramFiles(x86)": str(root / "machine-x86"),
                    "LOCALAPPDATA": str(root / "user"),
                }
                candidate = Path(environment[root_name]) / relative
                candidate.parent.mkdir(parents=True)
                candidate.write_text("", encoding="utf-8")
                with (
                    mock.patch.object(dependencies.sys, "platform", "win32"),
                    mock.patch.object(dependencies.shutil, "which", return_value=None),
                    mock.patch.object(dependencies, "_windows_registered_path", return_value=""),
                    mock.patch.dict(dependencies.os.environ, environment, clear=False),
                ):
                    executable = dependencies._system_command_path("bash")

                self.assertEqual(Path(executable), candidate)

    def test_bash_probe_derives_git_root_from_fresh_registered_git(self):
        calls = []
        with tempfile.TemporaryDirectory() as temp:
            git_root = Path(temp) / "Custom Git"
            git_executable = git_root / "cmd" / "git.exe"
            bash_executable = git_root / "usr" / "bin" / "bash.exe"
            git_executable.parent.mkdir(parents=True)
            bash_executable.parent.mkdir(parents=True)
            git_executable.write_text("", encoding="utf-8")
            bash_executable.write_text("", encoding="utf-8")

            def which(name, path=None):
                calls.append((name, path))
                if name == "git" and path == "fresh-registered-path":
                    return str(git_executable)
                return None

            with (
                mock.patch.object(dependencies.sys, "platform", "win32"),
                mock.patch.object(dependencies.shutil, "which", side_effect=which),
                mock.patch.object(
                    dependencies,
                    "_windows_registered_path",
                    return_value="fresh-registered-path",
                ),
                mock.patch.dict(dependencies.os.environ, {
                    "ProgramFiles": str(Path(temp) / "empty-machine"),
                    "ProgramFiles(x86)": str(Path(temp) / "empty-x86"),
                    "LOCALAPPDATA": str(Path(temp) / "empty-user"),
                }, clear=False),
            ):
                executable = dependencies._system_command_path("bash")

        self.assertEqual(Path(executable), bash_executable)
        self.assertIn(("git", "fresh-registered-path"), calls)

    def test_bash_probe_rechecks_fresh_state_without_system_side_effects(self):
        manifest = self._command_manifest([{"type": "command", "name": "bash"}])
        identity_before = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        state = {"installed": False}
        registered_calls = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            git_root = root / "New Git"
            git_executable = git_root / "cmd" / "git.exe"
            bash_executable = git_root / "bin" / "bash.exe"

            def registered_path():
                registered_calls.append(state["installed"])
                return "fresh-registered-path" if state["installed"] else ""

            def which(name, path=None):
                if name == "git" and path == "fresh-registered-path" and state["installed"]:
                    return str(git_executable)
                return None

            environment = {
                "PATH": "original-process-path",
                "ProgramFiles": str(root / "empty-machine"),
                "ProgramFiles(x86)": str(root / "empty-x86"),
                "LOCALAPPDATA": str(root / "empty-user"),
            }
            with (
                mock.patch.object(dependencies.sys, "platform", "win32"),
                mock.patch.object(dependencies.shutil, "which", side_effect=which),
                mock.patch.object(dependencies, "_windows_registered_path", side_effect=registered_path),
                mock.patch.object(dependencies.subprocess, "run") as run_command,
                mock.patch.dict(dependencies.os.environ, environment, clear=False),
            ):
                first = dependencies.inspect_manifest(manifest, app_dir=root, data_dir=root / "data")
                git_executable.parent.mkdir(parents=True)
                bash_executable.parent.mkdir(parents=True)
                git_executable.write_text("", encoding="utf-8")
                bash_executable.write_text("", encoding="utf-8")
                state["installed"] = True
                second = dependencies.inspect_manifest(manifest, app_dir=root, data_dir=root / "data")
                process_path_after = dependencies.os.environ["PATH"]

        first_requirement = first["capabilities"][0]["required"][0]
        second_requirement = second["capabilities"][0]["required"][0]
        self.assertFalse(first_requirement["available"])
        self.assertEqual(
            first_requirement["installHint"],
            "winget install --id Git.Git --exact --source winget",
        )
        self.assertTrue(second_requirement["available"])
        self.assertEqual(Path(second_requirement["executable"]), bash_executable)
        self.assertEqual(registered_calls, [False, True])
        self.assertEqual(process_path_after, "original-process-path")
        run_command.assert_not_called()
        self.assertEqual(json.dumps(manifest, ensure_ascii=False, sort_keys=True), identity_before)

    def test_command_probe_reads_fresh_registered_path_without_mutating_process_path(self):
        calls = []

        def which(name, path=None):
            calls.append((name, path))
            return r"C:\FreshTool\demo.exe" if path == "fresh-registered-path" else None

        with (
            mock.patch.object(dependencies.shutil, "which", side_effect=which),
            mock.patch.object(dependencies, "_windows_registered_path", return_value="fresh-registered-path"),
        ):
            executable = dependencies._system_command_path("demo")

        self.assertEqual(executable, r"C:\FreshTool\demo.exe")
        self.assertEqual(calls, [("demo", None), ("demo", "fresh-registered-path")])

    def test_invalid_manifest_is_reported_without_hiding_valid_skills(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            skills = root / "skills"
            valid = skills / "demo"
            invalid = skills / "broken"
            valid.mkdir(parents=True)
            invalid.mkdir(parents=True)
            for directory in (valid, invalid):
                (directory / "SKILL.md").write_text("# skill", encoding="utf-8")
            (valid / "dependencies.json").write_text(json.dumps(_manifest()), encoding="utf-8")
            (invalid / "dependencies.json").write_text("{bad json", encoding="utf-8")
            ready = {
                "name": "demo", "status": "ready", "manifestSource": "local", "capabilities": [],
            }
            with mock.patch.object(dependencies, "inspect_manifest", return_value=ready):
                result = dependencies.inspect_skill_dependencies(
                    skills,
                    bundled_skills_dir=root / "bundled",
                    app_dir=root,
                    data_dir=root / "data",
                )

        self.assertEqual(result["summary"], {"declared": 1, "ready": 1, "partial": 0, "unavailable": 0})
        self.assertEqual(result["skills"], [ready])
        self.assertEqual(result["errors"][0]["name"], "broken")


class TestDependencyOperations(unittest.TestCase):
    def _runtime_tools(self, root):
        host_python = root / "host-python.exe"
        npm = root / "npm.cmd"
        host_python.write_text("", encoding="utf-8")
        npm.write_text("", encoding="utf-8")

        def which(name):
            if name in {"python", "python3"}:
                return str(host_python)
            if name in {"npm", "npm.cmd"}:
                return str(npm)
            return None

        return host_python, npm, which

    def test_install_plan_targets_only_managed_python_and_node_runtimes(self):
        inspection = {
            "name": "demo",
            "capabilities": [{
                "id": "create",
                "required": [
                    {
                        "id": "python:requests", "type": "python", "name": "requests",
                        "minimumVersion": "2.28", "available": False, "installed": False,
                        "source": "", "reason": "not_installed",
                    },
                    {
                        "id": "node:docx", "type": "node", "name": "docx",
                        "version": "9.5.0", "available": False, "installed": False,
                        "source": "", "reason": "not_installed",
                    },
                    {
                        "id": "command:pandoc", "type": "command", "name": "pandoc",
                        "available": False, "installed": False, "source": "",
                        "installHint": "Windows PowerShell: winget install --id JohnMacFarlane.Pandoc --exact",
                    },
                ],
                "optional": [],
            }],
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, which = self._runtime_tools(root)
            with mock.patch.object(dependencies.shutil, "which", side_effect=which):
                plan = dependencies.build_dependency_operation_plan(
                    inspection,
                    data_dir=root / "data",
                    capability_id="create",
                    action="install",
                )

        self.assertTrue(plan["actionable"])
        self.assertEqual([step["id"] for step in plan["steps"]], [
            "create-python-runtime", "install-python-packages", "prepare-node-runtime", "install-node-packages",
        ])
        external_steps = [step for step in plan["steps"] if "_argv" in step]
        self.assertTrue(all(isinstance(step["_argv"], list) for step in external_steps))
        self.assertFalse(any("winget" in part for step in external_steps for part in step["_argv"]))
        self.assertEqual(plan["systemRequirements"][0]["installHint"], inspection["capabilities"][0]["required"][2]["installHint"])
        self.assertIn(str(Path(temp) / "data" / "runtime"), plan["authorization"]["root"])
        public = dependencies.public_dependency_operation_plan(plan)
        self.assertTrue(public["fingerprint"])
        self.assertTrue(all("_argv" not in step for step in public["steps"]))
        self.assertFalse(public["authorization"]["systemPackageManagers"])
        self.assertFalse(public["authorization"]["pathChanges"])
        self.assertFalse(public["authorization"]["globalWrappers"])

    def test_windows_venv_path_recovers_after_runtime_creation(self):
        inspection = {
            "name": "demo",
            "capabilities": [{
                "id": "inspect",
                "required": [{
                    "id": "python:markitdown",
                    "type": "python",
                    "name": "markitdown",
                    "available": False,
                    "installed": False,
                    "source": "system",
                    "reason": "not_installed",
                }],
                "optional": [],
            }],
        }
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(dependencies.sys, "platform", "win32"):
            data_dir = Path(temp) / "data"
            scripts_python = data_dir / "runtime" / "python" / "Scripts" / "python.exe"
            scripts_python.parent.mkdir(parents=True)
            scripts_python.write_text("", encoding="utf-8")
            plan = dependencies.build_dependency_operation_plan(
                inspection,
                data_dir=data_dir,
                capability_id="inspect",
                action="install",
            )
            self.assertEqual(dependencies._managed_python_path(data_dir), scripts_python)
            self.assertEqual([step["id"] for step in plan["steps"]], ["install-python-packages"])
            self.assertEqual(Path(plan["steps"][0]["_argv"][0]), scripts_python)

    def test_settings_operations_include_optional_managed_dependencies(self):
        inspection = {
            "name": "demo",
            "capabilities": [{
                "id": "create",
                "required": [{
                    "id": "node:required-package", "type": "node", "name": "required-package",
                    "available": True, "source": "managed",
                }],
                "optional": [{
                    "id": "node:optional-package", "type": "node", "name": "optional-package",
                    "available": False, "source": "", "reason": "not_installed",
                }],
            }],
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, which = self._runtime_tools(root)
            with mock.patch.object(dependencies.shutil, "which", side_effect=which):
                install = dependencies.build_dependency_operation_plan(
                    inspection, data_dir=root / "data", capability_id="create", action="install",
                )
                repair = dependencies.build_dependency_operation_plan(
                    inspection, data_dir=root / "data", capability_id="create", action="repair",
                )
                uninstall = dependencies.build_dependency_operation_plan(
                    inspection, data_dir=root / "data", capability_id="create", action="uninstall",
                )

        install_step = next(step for step in install["steps"] if step["id"] == "install-node-packages")
        repair_step = next(step for step in repair["steps"] if step["id"] == "repair-node-packages")
        self.assertIn("optional-package", install_step["_argv"])
        self.assertIn("required-package", repair_step["_argv"])
        self.assertIn("optional-package", repair_step["_argv"])
        self.assertEqual(uninstall["steps"][0]["_packageNames"], ["required-package"])
        operations = {item["id"]: item for item in install["requirements"]}
        self.assertTrue(operations["node:optional-package"]["optional"])

    def test_install_all_only_includes_missing_required_managed_dependencies(self):
        inspection = {
            "name": "demo",
            "capabilities": [
                {
                    "id": "create",
                    "required": [{
                        "id": "node:already-ready", "type": "node", "name": "already-ready",
                        "available": True, "source": "managed",
                    }],
                    "optional": [{
                        "id": "node:optional-package", "type": "node", "name": "optional-package",
                        "available": False, "source": "", "reason": "not_installed",
                    }],
                },
                {
                    "id": "inspect",
                    "required": [{
                        "id": "python:missing-python", "type": "python", "name": "missing-python",
                        "available": False, "source": "system", "reason": "not_installed",
                    }],
                    "optional": [],
                },
                {
                    "id": "render",
                    "required": [{
                        "id": "command:renderer", "type": "command", "name": "renderer",
                        "available": False, "source": "", "reason": "not_installed",
                        "installHint": "Install Renderer outside Code",
                    }],
                    "optional": [],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, which = self._runtime_tools(root)
            with mock.patch.object(dependencies.shutil, "which", side_effect=which):
                plan = dependencies.build_dependency_operation_plan(
                    inspection, data_dir=root / "data", capability_id="*", action="install",
                )

        operations = {item["id"]: item["operation"] for item in plan["requirements"]}
        self.assertEqual(plan["capabilities"], ["create", "inspect", "render"])
        self.assertEqual(operations["node:already-ready"], "satisfied")
        self.assertEqual(operations["python:missing-python"], "install")
        self.assertNotIn("node:optional-package", operations)
        self.assertEqual(plan["systemRequirements"][0]["operation"], "user_install")
        self.assertFalse(any(
            "already-ready" in part or "optional-package" in part or "renderer" in part
            for step in plan["steps"] for part in step.get("_argv", [])
        ))
        python_step = next(step for step in plan["steps"] if step["id"] == "install-python-packages")
        self.assertIn("missing-python", python_step["_argv"])
        with self.assertRaisesRegex(dependencies.DependencyManifestError, "only support install"):
            dependencies.build_dependency_operation_plan(
                inspection, data_dir=root / "data", capability_id="*", action="repair",
            )

    def test_repair_reinstalls_all_required_managed_packages(self):
        inspection = {
            "name": "demo",
            "capabilities": [{
                "id": "runtime",
                "required": [
                    {"id": "python:demo", "type": "python", "name": "demo", "available": True, "source": "system"},
                    {"id": "node:demo-node", "type": "node", "name": "demo-node", "available": True, "source": "app"},
                ],
                "optional": [],
            }],
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            managed_python = dependencies._managed_python_path(root / "data")
            managed_python.parent.mkdir(parents=True)
            managed_python.write_text("", encoding="utf-8")
            _, _, which = self._runtime_tools(root)
            with mock.patch.object(dependencies.shutil, "which", side_effect=which):
                plan = dependencies.build_dependency_operation_plan(
                    inspection,
                    data_dir=root / "data",
                    capability_id="runtime",
                    action="repair",
                )

        python_step = next(step for step in plan["steps"] if step["type"] == "python")
        node_step = next(step for step in plan["steps"] if step["id"] == "repair-node-packages")
        self.assertIn("--force-reinstall", python_step["_argv"])
        self.assertIn("--force", node_step["_argv"])
        self.assertNotIn("create-python-runtime", [step["id"] for step in plan["steps"]])
        self.assertTrue(all(item["operation"] == "repair" for item in plan["requirements"]))

    def test_uninstall_preserves_shared_and_non_managed_dependencies(self):
        inspection = {
            "name": "demo",
            "capabilities": [{
                "id": "runtime",
                "required": [
                    {"id": "python:shared", "type": "python", "name": "shared", "available": True, "source": "managed"},
                    {"id": "node:exclusive", "type": "node", "name": "exclusive", "available": True, "source": "managed"},
                    {"id": "node:external", "type": "node", "name": "external", "available": True, "source": "app"},
                ],
                "optional": [],
            }],
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, _, which = self._runtime_tools(root)
            with mock.patch.object(dependencies.shutil, "which", side_effect=which):
                plan = dependencies.build_dependency_operation_plan(
                    inspection,
                    data_dir=root / "data",
                    capability_id="runtime",
                    action="uninstall",
                    shared_requirement_ids={"python:shared"},
                )

        operations = {item["id"]: item["operation"] for item in plan["requirements"]}
        self.assertEqual(operations["python:shared"], "preserve_shared")
        self.assertEqual(operations["node:external"], "preserve_external")
        self.assertEqual(operations["node:exclusive"], "uninstall")
        self.assertEqual(len(plan["steps"]), 1)
        self.assertEqual(plan["steps"][0]["id"], "uninstall-node-packages")
        self.assertEqual(plan["steps"][0]["_operation"], "remove_node_packages")
        self.assertEqual(plan["steps"][0]["_packageNames"], ["exclusive"])
        self.assertNotIn("_argv", plan["steps"][0])

    def test_python_operations_use_distribution_name(self):
        inspection = {
            "name": "demo",
            "capabilities": [{
                "id": "runtime",
                "required": [{
                    "id": "python:demo_import",
                    "type": "python",
                    "name": "demo_import",
                    "importName": "demo_import",
                    "distribution": "demo-distribution",
                    "available": True,
                    "source": "managed",
                }],
                "optional": [],
            }],
        }
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp) / "data"
            managed_python = dependencies._managed_python_path(data_dir)
            managed_python.parent.mkdir(parents=True)
            managed_python.write_text("", encoding="utf-8")
            plan = dependencies.build_dependency_operation_plan(
                inspection,
                data_dir=data_dir,
                capability_id="runtime",
                action="uninstall",
            )

        self.assertEqual(plan["steps"][0]["_argv"][-1], "demo-distribution")

    def test_node_uninstall_precisely_removes_target_and_its_bins(self):
        with tempfile.TemporaryDirectory() as temp:
            node_root = Path(temp) / "runtime" / "node"
            node_modules = node_root / "node_modules"
            target = node_modules / "target-package"
            unrelated = node_modules / "unrelated-package"
            bin_root = node_modules / ".bin"
            target.mkdir(parents=True)
            unrelated.mkdir()
            bin_root.mkdir()
            (target / "package.json").write_text(json.dumps({
                "name": "target-package", "version": "1.0.0", "bin": {"target-cli": "cli.js"},
            }), encoding="utf-8")
            (unrelated / "package.json").write_text(json.dumps({
                "name": "unrelated-package", "version": "2.0.0",
            }), encoding="utf-8")
            for suffix in ("", ".cmd", ".ps1"):
                (bin_root / f"target-cli{suffix}").write_text("shim", encoding="utf-8")
            (bin_root / "unrelated-cli.cmd").write_text("keep", encoding="utf-8")
            (node_modules / ".package-lock.json").write_text("{}", encoding="utf-8")
            plan = {
                "actionable": True,
                "steps": [{
                    "id": "uninstall-node-packages",
                    "purpose": "uninstall_packages",
                    "displayCommand": "remove managed Node packages: target-package",
                    "_operation": "remove_node_packages",
                    "_nodeRoot": str(node_root),
                    "_packageNames": ["target-package"],
                }],
            }

            result = dependencies.execute_dependency_operation_plan(plan, timeout_seconds=10)
            runtime_manifest = json.loads((node_root / "package.json").read_text(encoding="utf-8"))

            self.assertTrue(result["ok"])
            self.assertFalse(target.exists())
            self.assertTrue(unrelated.is_dir())
            self.assertTrue((bin_root / "unrelated-cli.cmd").is_file())
            self.assertTrue(all(not (bin_root / f"target-cli{suffix}").exists() for suffix in ("", ".cmd", ".ps1")))
            self.assertFalse((node_modules / ".package-lock.json").exists())
            self.assertEqual(runtime_manifest["dependencies"], {"unrelated-package": "2.0.0"})

    def test_executor_runs_argument_arrays_and_reports_step_progress(self):
        progress = []
        with tempfile.TemporaryDirectory() as temp:
            plan = {
                "actionable": True,
                "steps": [{
                    "id": "safe-step",
                    "type": "python",
                    "purpose": "install_packages",
                    "displayCommand": "python validation",
                    "_argv": [sys.executable, "-c", "print('ok')"],
                    "_cwd": temp,
                }],
            }
            result = dependencies.execute_dependency_operation_plan(
                plan,
                progress_callback=progress.append,
                timeout_seconds=10,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["completedSteps"], 1)
        self.assertEqual(progress[0]["phase"], "install_packages")
        self.assertEqual(progress[-1]["phase"], "step_completed")
        self.assertNotIn("_argv", progress[0]["step"])


if __name__ == "__main__":
    unittest.main()
