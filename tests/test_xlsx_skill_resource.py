import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import server as server_mod
from code_runtime import bundled_skills
from code_runtime.skill_dependencies import inspect_skill_directory, load_skill_manifest
from code_runtime.skill_resources import (
    SkillResourceError,
    resolve_skill_resources,
)


ROOT = Path(__file__).resolve().parents[1]
XLSX_DIR = ROOT / "data" / "skills" / "xlsx"
RECALC_PATH = XLSX_DIR / "scripts" / "recalc.py"
SOFFICE_HELPER_PATH = XLSX_DIR / "scripts" / "office" / "soffice.py"
RESOURCE_MANIFEST_PATH = XLSX_DIR / "code-resources.json"


def _sha256(path):
    payload = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(payload).hexdigest()


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_skill(root, *, skill_text, dependency_text, include_resources=True):
    skill_dir = Path(root) / "xlsx"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_text, encoding="utf-8")
    (skill_dir / "dependencies.json").write_text(dependency_text, encoding="utf-8")
    resource_payloads = {
        "scripts/recalc.py": b"print('recalc')\n",
        "scripts/office/soffice.py": b"def locate(): return 'soffice'\n",
    }
    if include_resources:
        for relative, payload in resource_payloads.items():
            target = skill_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
    return skill_dir, resource_payloads


def _write_resource_manifest(
    skill_dir,
    resource_payloads,
    *,
    skill_hashes,
    dependency_hashes,
    overrides=None,
):
    resources = [
        {
            "id": "recalculate",
            "path": "scripts/recalc.py",
            "sha256": hashlib.sha256(resource_payloads["scripts/recalc.py"]).hexdigest(),
            "kind": "python",
            "protocol": "code-xlsx-recalc/v1",
            "modelVisible": True,
            "arguments": ["<workbook.xlsx>", "[timeout_seconds]", "[--force]"],
        },
        {
            "id": "soffice-helper",
            "path": "scripts/office/soffice.py",
            "sha256": hashlib.sha256(resource_payloads["scripts/office/soffice.py"]).hexdigest(),
            "kind": "python-library",
            "protocol": "code-xlsx-soffice/v1",
            "modelVisible": False,
            "arguments": [],
        },
    ]
    payload = {
        "schemaVersion": 1,
        "skill": "xlsx",
        "compatibleInstalled": {
            "skillMdSha256": list(skill_hashes),
            "dependenciesSha256": list(dependency_hashes),
        },
        "resources": resources,
    }
    payload.update(overrides or {})
    (Path(skill_dir) / "code-resources.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


class TestTrustedSkillResourceResolution(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="code xlsx resources ")
        self.root = Path(self.temp.name)
        self.bundled = self.root / "app bundle" / "data" / "skills"
        self.installed = self.root / "installed profile" / "skills"
        self.bundled.mkdir(parents=True)
        self.installed.mkdir(parents=True)
        self.skill_v2 = "---\nname: xlsx\ndescription: test\n---\nBundled v2\n"
        self.skill_v1 = "---\nname: xlsx\ndescription: test\n---\nBundled v1\n"
        self.dependencies = json.dumps({
            "schemaVersion": 1,
            "skill": "xlsx",
            "capabilities": {"run": {"required": []}},
        }) + "\n"
        self.bundled_skill, self.payloads = _write_skill(
            self.bundled,
            skill_text=self.skill_v2,
            dependency_text=self.dependencies,
        )
        self.allowed_skill_hashes = [
            hashlib.sha256(self.skill_v1.encode("utf-8")).hexdigest(),
            _sha256(self.bundled_skill / "SKILL.md"),
        ]
        self.allowed_dependency_hashes = [_sha256(self.bundled_skill / "dependencies.json")]
        _write_resource_manifest(
            self.bundled_skill,
            self.payloads,
            skill_hashes=self.allowed_skill_hashes,
            dependency_hashes=self.allowed_dependency_hashes,
        )

    def tearDown(self):
        self.temp.cleanup()

    def _install(self, *, legacy=False, resources=True):
        skill, _ = _write_skill(
            self.installed,
            skill_text=self.skill_v1 if legacy else self.skill_v2,
            dependency_text=self.dependencies,
            include_resources=resources,
        )
        return skill

    def test_new_install_uses_exact_installed_resource_inside_path_with_spaces(self):
        installed_skill = self._install()
        resolved = resolve_skill_resources("xlsx", self.installed, self.bundled)

        self.assertEqual(resolved["schemaVersion"], 1)
        self.assertEqual(resolved["source"], "installed")
        self.assertIn("do not search", resolved["instructions"].lower())
        self.assertEqual(len(resolved["resources"]), 1)
        item = resolved["resources"][0]
        self.assertEqual(item["id"], "recalculate")
        self.assertEqual(item["protocol"], "code-xlsx-recalc/v1")
        self.assertEqual(Path(item["path"]), installed_skill / "scripts" / "recalc.py")
        self.assertIn(" ", item["path"])

    def test_legacy_install_missing_resources_uses_bundled_fallback_without_writes(self):
        installed_skill = self._install(legacy=True, resources=False)
        before = sorted(path.relative_to(installed_skill).as_posix() for path in installed_skill.rglob("*"))

        resolved = resolve_skill_resources("xlsx", self.installed, self.bundled)
        after = sorted(path.relative_to(installed_skill).as_posix() for path in installed_skill.rglob("*"))

        self.assertEqual(resolved["source"], "bundled-fallback")
        self.assertEqual(Path(resolved["resources"][0]["path"]), self.bundled_skill / "scripts" / "recalc.py")
        self.assertEqual(before, after)

    def test_legacy_dependency_manifest_uses_current_bundled_capabilities_without_rewrite(self):
        installed_skill = self._install(legacy=True, resources=False)
        legacy_dependencies = json.dumps({
            "schemaVersion": 1,
            "skill": "xlsx",
            "capabilities": {"legacy": {"required": []}},
        }) + "\n"
        (installed_skill / "dependencies.json").write_text(legacy_dependencies, encoding="utf-8")
        dependency_hashes = [
            self.allowed_dependency_hashes[0],
            _sha256(installed_skill / "dependencies.json"),
        ]
        _write_resource_manifest(
            self.bundled_skill,
            self.payloads,
            skill_hashes=self.allowed_skill_hashes,
            dependency_hashes=dependency_hashes,
        )
        before = (installed_skill / "dependencies.json").read_bytes()

        manifest = load_skill_manifest(installed_skill, self.bundled)

        self.assertEqual(manifest["source"], "bundled-compatible")
        self.assertEqual([item["id"] for item in manifest["capabilities"]], ["run"])
        self.assertEqual((installed_skill / "dependencies.json").read_bytes(), before)

    def test_custom_identity_and_same_name_resource_conflict_fail_closed(self):
        installed_skill = self._install(legacy=True, resources=False)
        (installed_skill / "SKILL.md").write_text("custom xlsx", encoding="utf-8")
        with self.assertRaises(SkillResourceError) as custom:
            resolve_skill_resources("xlsx", self.installed, self.bundled)
        self.assertEqual(custom.exception.error_code, "installed_skill_identity_unknown")

        shutil.rmtree(installed_skill)
        installed_skill = self._install(legacy=True, resources=True)
        (installed_skill / "scripts" / "recalc.py").write_text("custom resource", encoding="utf-8")
        with self.assertRaises(SkillResourceError) as conflict:
            resolve_skill_resources("xlsx", self.installed, self.bundled)
        self.assertEqual(conflict.exception.error_code, "installed_resource_conflict")
        self.assertEqual((installed_skill / "scripts" / "recalc.py").read_text(), "custom resource")

    def test_tombstone_never_projects_or_restores_bundled_resource(self):
        self._install(legacy=True, resources=False)
        bundled_skills.bundled_skill_state_path(self.installed).write_text(
            json.dumps({"schema": bundled_skills.STATE_SCHEMA, "tombstones": ["xlsx"]}),
            encoding="utf-8",
        )
        with self.assertRaises(SkillResourceError) as caught:
            resolve_skill_resources("xlsx", self.installed, self.bundled)
        self.assertEqual(caught.exception.error_code, "skill_tombstoned")

    def test_missing_tampered_traversal_and_reparse_resources_are_rejected(self):
        self._install(legacy=True, resources=False)
        recalc = self.bundled_skill / "scripts" / "recalc.py"
        recalc.unlink()
        with self.assertRaises(SkillResourceError) as missing:
            resolve_skill_resources("xlsx", self.installed, self.bundled)
        self.assertEqual(missing.exception.error_code, "bundled_resource_missing")

        recalc.write_bytes(self.payloads["scripts/recalc.py"] + b"tampered")
        with self.assertRaises(SkillResourceError) as tampered:
            resolve_skill_resources("xlsx", self.installed, self.bundled)
        self.assertEqual(tampered.exception.error_code, "bundled_resource_hash_mismatch")

        recalc.write_bytes(self.payloads["scripts/recalc.py"])
        manifest = json.loads((self.bundled_skill / "code-resources.json").read_text())
        manifest["resources"][0]["path"] = "../escape.py"
        (self.bundled_skill / "code-resources.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(SkillResourceError) as traversal:
            resolve_skill_resources("xlsx", self.installed, self.bundled)
        self.assertEqual(traversal.exception.error_code, "resource_contract_invalid")

        _write_resource_manifest(
            self.bundled_skill,
            self.payloads,
            skill_hashes=self.allowed_skill_hashes,
            dependency_hashes=self.allowed_dependency_hashes,
        )
        with mock.patch(
            "code_runtime.skill_resources._is_link_or_reparse",
            side_effect=lambda path: Path(path).name == "recalc.py",
        ):
            with self.assertRaises(SkillResourceError) as reparse:
                resolve_skill_resources("xlsx", self.installed, self.bundled)
        self.assertEqual(reparse.exception.error_code, "resource_path_unsafe")

    def test_use_skill_projects_resources_and_reports_stable_failure(self):
        self._install()
        app_dir = self.root / "app bundle"
        with (
            mock.patch.object(server_mod, "APP_DIR", app_dir),
            mock.patch.object(server_mod, "SKILLS_DIR", self.installed),
        ):
            projected = server_mod.execute_use_skill_tool({"name": "xlsx"})
            self.assertTrue(projected["ok"])
            self.assertEqual(projected["runtimeResources"]["source"], "installed")
            self.assertNotIn(str(self.root.parent), projected.get("error", ""))

            (self.installed / "xlsx" / "scripts" / "recalc.py").write_text("conflict", encoding="utf-8")
            failed = server_mod.execute_use_skill_tool({"name": "xlsx"})
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["errorCode"], "installed_resource_conflict")
        self.assertFalse(failed["retryable"])
        self.assertNotIn(str(self.root), failed["error"])


class TestXlsxResourceContract(unittest.TestCase):
    def test_repository_contract_has_verified_resources_and_packaging(self):
        manifest = json.loads(RESOURCE_MANIFEST_PATH.read_text(encoding="utf-8"))
        by_id = {item["id"]: item for item in manifest["resources"]}
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["skill"], "xlsx")
        self.assertEqual(by_id["recalculate"]["sha256"], _sha256(RECALC_PATH))
        self.assertEqual(by_id["soffice-helper"]["sha256"], _sha256(SOFFICE_HELPER_PATH))
        resolved = resolve_skill_resources("xlsx", ROOT / "data" / "skills", ROOT / "data" / "skills")
        self.assertEqual(resolved["source"], "installed")
        self.assertEqual(Path(resolved["resources"][0]["path"]), RECALC_PATH)

        skill_text = (XLSX_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("runtimeResources", skill_text)
        self.assertIn("create-edit-formulas", skill_text)
        self.assertNotRegex(skill_text, r"(?i)(USERPROFILE|HOME|rglob|recurse)")
        for source_path in (
            ROOT / "code_runtime" / "skill_resources.py",
            RECALC_PATH,
            SOFFICE_HELPER_PATH,
        ):
            source = source_path.read_text(encoding="utf-8")
            self.assertNotRegex(source, r"(?i)(Path\.home|USERPROFILE|os\.walk|rglob\()")
        build_source = (ROOT / "build_exe.py").read_text(encoding="utf-8")
        self.assertIn("APP_DIR / 'data' / 'skills'", build_source)

    def test_formula_capability_requires_openpyxl_and_soffice_without_blocking_plain_edit(self):
        manifest = json.loads((XLSX_DIR / "dependencies.json").read_text(encoding="utf-8"))
        capabilities = manifest["capabilities"]
        formula_required = {
            f"{item['type']}:{item['name']}"
            for item in capabilities["create-edit-formulas"]["required"]
        }
        plain_required = {
            f"{item['type']}:{item['name']}"
            for item in capabilities["create-edit"]["required"]
        }
        inspect_required = {
            f"{item['type']}:{item['name']}"
            for item in capabilities["inspect"]["required"]
        }
        self.assertEqual(formula_required, {"python:openpyxl", "command:soffice"})
        soffice_requirement = next(
            item
            for item in capabilities["create-edit-formulas"]["required"]
            if item["type"] == "command"
        )
        self.assertEqual(soffice_requirement["executableKind"], "libreoffice")
        self.assertTrue(all(
            item.get("executableKind") == "libreoffice"
            for capability in capabilities.values()
            for item in capability.get("required", [])
            if item.get("type") == "command" and item.get("name") == "soffice"
        ))
        self.assertEqual(plain_required, {"python:openpyxl"})
        self.assertNotIn("command:soffice", inspect_required)

        with mock.patch("code_runtime.skill_dependencies._system_libreoffice_path", return_value=""):
            status = inspect_skill_directory(
                XLSX_DIR,
                bundled_skills_dir=ROOT / "data" / "skills",
                app_dir=ROOT,
                data_dir=ROOT / "data",
                capability_id="create-edit-formulas",
            )
        selected = next(item for item in status["capabilities"] if item["id"] == "create-edit-formulas")
        self.assertEqual(selected["status"], "unavailable")
        self.assertEqual(
            [item["id"] for item in status["installGuidance"]["requiredMissing"]],
            ["command:soffice"],
        )
        self.assertIn("installed by the user outside Code", status["installGuidance"]["instructions"])

    def test_windows_soffice_probe_prefers_real_libreoffice_over_path_wrapper(self):
        from code_runtime import skill_dependencies

        with tempfile.TemporaryDirectory(prefix="Code LibreOffice ") as temp:
            program_files = Path(temp)
            program = program_files / "LibreOffice" / "program"
            program.mkdir(parents=True)
            executable = program / "soffice.exe"
            executable.write_bytes(b"MZ")
            (program / "soffice.bin").write_bytes(b"bin")
            (program / "fundamental.ini").write_text("[Bootstrap]", encoding="utf-8")
            with (
                mock.patch.object(skill_dependencies.sys, "platform", "win32"),
                mock.patch.dict(skill_dependencies.os.environ, {"ProgramFiles": str(program_files)}, clear=False),
                mock.patch.object(skill_dependencies.shutil, "which", return_value=r"C:\fake\soffice.cmd"),
            ):
                generic = skill_dependencies._system_command_path("soffice")
                inspected = skill_dependencies._probe_commands([{
                    "id": "command:soffice",
                    "name": "soffice",
                    "executableKind": "libreoffice",
                }], Path(temp) / "data")
                found = inspected["command:soffice"]["executable"]
        self.assertEqual(generic, r"C:\fake\soffice.cmd")
        self.assertEqual(found, str(executable.resolve()))


class TestXlsxRecalcResource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scripts_dir = str(RECALC_PATH.parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        cls.recalc = _load_module("code_xlsx_recalc", RECALC_PATH)
        cls.office = _load_module("code_xlsx_soffice", SOFFICE_HELPER_PATH)

    def _workbook(self, path, *, formula="=SUM(1,2)", error_literal=None):
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Formula Sheet"
        sheet["A1"] = formula
        if error_literal:
            sheet["A2"] = error_literal
            sheet["A2"].data_type = "e"
        workbook.save(path)

    def test_success_and_errors_found_contracts_replace_only_after_staging(self):
        with tempfile.TemporaryDirectory(prefix="Code XLSX results ") as temp:
            root = Path(temp)
            clean = root / "clean workbook.xlsx"
            broken = root / "broken workbook.xlsx"
            self._workbook(clean)
            self._workbook(broken, error_literal="#DIV/0!")

            def fake_recalculate(source, destination, **_kwargs):
                shutil.copy2(source, destination)

            with mock.patch.object(self.recalc, "recalculate_with_libreoffice", side_effect=fake_recalculate):
                clean_result = self.recalc.recalculate_workbook(clean, timeout_seconds=12)
                broken_result = self.recalc.recalculate_workbook(broken, timeout_seconds=12)

        self.assertEqual(clean_result["status"], "success")
        self.assertEqual(clean_result["total_formulas"], 1)
        self.assertEqual(clean_result["total_errors"], 0)
        self.assertEqual(broken_result["status"], "errors_found")
        self.assertEqual(broken_result["total_formulas"], 1)
        self.assertEqual(broken_result["total_errors"], 1)
        self.assertEqual(broken_result["error_summary"]["#DIV/0!"]["locations"], ["Formula Sheet!A2"])

    def test_external_links_fail_closed_unless_force_is_explicit(self):
        with tempfile.TemporaryDirectory(prefix="Code XLSX external ") as temp:
            workbook = Path(temp) / "external.xlsx"
            network_formula = Path(temp) / "network formula.xlsx"
            self._workbook(workbook)
            self._workbook(network_formula, formula='=WEBSERVICE("https://example.invalid/value")')
            with zipfile.ZipFile(workbook, "a") as archive:
                archive.writestr("xl/externalLinks/externalLink1.xml", "<externalLink/>")

            with self.assertRaises(self.recalc.RecalcError) as blocked:
                self.recalc.recalculate_workbook(workbook, timeout_seconds=10)
            self.assertEqual(blocked.exception.error_code, "external_links_detected")
            with self.assertRaises(self.recalc.RecalcError) as formula_blocked:
                self.recalc.recalculate_workbook(network_formula, timeout_seconds=10)
            self.assertEqual(formula_blocked.exception.error_code, "external_links_detected")
            with mock.patch.object(
                self.recalc,
                "recalculate_with_libreoffice",
                side_effect=lambda source, destination, **_kwargs: shutil.copy2(source, destination),
            ) as recalculated:
                result = self.recalc.recalculate_workbook(workbook, timeout_seconds=10, force=True)
        self.assertEqual(result["status"], "success")
        recalculated.assert_called_once()

    def test_cli_errors_are_json_and_timeout_is_bounded(self):
        stdout = []
        with mock.patch.object(self.recalc, "_write_json", side_effect=stdout.append):
            exit_code = self.recalc.main(["missing.xlsx", "9999"])
        self.assertNotEqual(exit_code, 0)
        self.assertEqual(stdout[0]["schema"], "code-xlsx-recalc/v1")
        self.assertEqual(stdout[0]["errorCode"], "invalid_timeout")
        self.assertNotIn(str(Path.home()), stdout[0]["error"])

    def test_publish_failure_preserves_original_and_removes_same_directory_temp(self):
        with tempfile.TemporaryDirectory(prefix="Code XLSX publish failure ") as temp:
            workbook = Path(temp) / "original.xlsx"
            self._workbook(workbook)
            original = workbook.read_bytes()
            with (
                mock.patch.object(
                    self.recalc,
                    "recalculate_with_libreoffice",
                    side_effect=lambda source, destination, **_kwargs: shutil.copy2(source, destination),
                ),
                mock.patch.object(self.recalc.os, "replace", side_effect=OSError("synthetic")),
            ):
                with self.assertRaises(self.recalc.RecalcError) as failed:
                    self.recalc.recalculate_workbook(workbook, timeout_seconds=10)
            preserved = workbook.read_bytes()
            leftovers = list(workbook.parent.glob(f".{workbook.name}.*.recalc.tmp"))
        self.assertEqual(failed.exception.error_code, "replace_failed")
        self.assertEqual(preserved, original)
        self.assertEqual(leftovers, [])

    def test_soffice_command_uses_argument_array_and_honors_cancel(self):
        class CompletedProcess:
            returncode = 0
            pid = 4242

            def __init__(self, output):
                self.output = output

            def poll(self):
                return self.returncode

            def communicate(self, timeout=None):
                self.output.parent.mkdir(parents=True, exist_ok=True)
                self.output.write_bytes(b"xlsx")
                return "converted", ""

        with tempfile.TemporaryDirectory(prefix="Code XLSX command ") as temp:
            root = Path(temp)
            source = root / "input & $(safe).xlsx"
            source.write_bytes(b"xlsx")
            out_dir = root / "out path"
            profile = root / "profile path"
            executable = root / "LibreOffice" / "program" / "soffice.exe"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"MZ")
            (executable.parent / "soffice.bin").write_bytes(b"bin")
            (executable.parent / "fundamental.ini").write_text("[Bootstrap]", encoding="utf-8")
            process_holder = {}

            def popen(argv, **kwargs):
                process_holder["argv"] = argv
                process_holder["kwargs"] = kwargs
                return CompletedProcess(out_dir / source.name)

            with mock.patch.object(self.office.subprocess, "Popen", side_effect=popen):
                output = self.office.run_soffice_conversion(
                    source,
                    out_dir,
                    profile,
                    timeout_seconds=10,
                    executable=executable,
                )
            self.assertEqual(output, out_dir / source.name)
            self.assertIsInstance(process_holder["argv"], list)
            self.assertIn(str(source), process_holder["argv"])
            self.assertNotIn("shell", process_holder["kwargs"])

            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(self.office.SofficeError) as cancelled:
                self.office.run_soffice_conversion(
                    source,
                    out_dir,
                    profile,
                    timeout_seconds=10,
                    executable=executable,
                    cancel_event=cancel,
                )
        self.assertEqual(cancelled.exception.error_code, "cancelled")

    def test_soffice_process_timeout_terminates_the_tree(self):
        class HangingProcess:
            returncode = None
            pid = 4243

            def poll(self):
                return None

            def communicate(self, timeout=None):
                raise subprocess.TimeoutExpired(["soffice"], timeout)

        with tempfile.TemporaryDirectory(prefix="Code XLSX timeout ") as temp:
            root = Path(temp)
            source = root / "timeout.xlsx"
            source.write_bytes(b"xlsx")
            executable = root / "LibreOffice" / "program" / "soffice.exe"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"MZ")
            (executable.parent / "soffice.bin").write_bytes(b"bin")
            (executable.parent / "fundamental.ini").write_text("[Bootstrap]", encoding="utf-8")
            process = HangingProcess()
            with (
                mock.patch.object(self.office.subprocess, "Popen", return_value=process),
                mock.patch.object(self.office.time, "monotonic", side_effect=[0.0, 11.0]),
                mock.patch.object(self.office, "_terminate_process_tree") as terminate,
            ):
                with self.assertRaises(self.office.SofficeError) as timed_out:
                    self.office.run_soffice_conversion(
                        source,
                        root / "out",
                        root / "profile",
                        timeout_seconds=10,
                        executable=executable,
                    )
        self.assertEqual(timed_out.exception.error_code, "timeout")
        terminate.assert_called_once_with(process)


if __name__ == "__main__":
    unittest.main()
