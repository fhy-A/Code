import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server as server_mod
from code_runtime.skill_dependencies import load_skill_manifest
from code_runtime.skill_resources import (
    SkillResourceError,
    audit_bundled_skill_resources,
    resolve_skill_resources,
)


ROOT = Path(__file__).resolve().parents[1]


def _sha256(payload):
    return hashlib.sha256(bytes(payload).replace(b"\r\n", b"\n")).hexdigest()


def _snapshot(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _write_skill(root, name, *, body="Skill body\n", dependencies=None, resources=None, custom=False):
    skill_dir = Path(root) / name
    skill_dir.mkdir(parents=True)
    skill_text = f"---\nname: {name}\ndescription: test\n---\n{body}"
    dependency_text = dependencies or json.dumps({
        "schemaVersion": 1,
        "skill": name,
        "capabilities": {"run": {"required": []}},
    }) + "\n"
    (skill_dir / "SKILL.md").write_text(skill_text, encoding="utf-8")
    (skill_dir / "dependencies.json").write_text(dependency_text, encoding="utf-8")
    resources = dict(resources or {"scripts/run.py": b"print('ready')\n"})
    for relative, payload in resources.items():
        target = skill_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    payload = {
        "schemaVersion": 1,
        "skill": name,
        "resources": [{
            "id": "run-helper",
            "path": "scripts/run.py",
            "sha256": _sha256(resources["scripts/run.py"]),
            "kind": "python",
            "protocol": "code-test-resource/v1",
            "modelVisible": True,
            "arguments": ["<input>"],
        }],
    }
    if not custom:
        payload["compatibleInstalled"] = {
            "skillMdSha256": [_sha256(skill_text.encode("utf-8"))],
            "dependenciesSha256": [_sha256(dependency_text.encode("utf-8"))],
        }
    (skill_dir / "code-resources.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return skill_dir


class TestRelocatableSkillResourceContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="Code relocatable Skill resources ")
        self.root = Path(self.temporary.name)
        self.bundled = self.root / "app bundle" / "data" / "skills"
        self.installed = self.root / "active profile with spaces" / "skills"
        self.bundled.mkdir(parents=True)
        self.installed.mkdir(parents=True)

    def tearDown(self):
        self.temporary.cleanup()

    def test_relocated_active_skill_root_returns_only_current_installed_path(self):
        bundled_skill = _write_skill(self.bundled, "demo")
        installed_skill = _write_skill(self.installed, "demo")
        before = resolve_skill_resources("demo", self.installed, self.bundled)
        self.assertEqual(before["source"], "installed")
        self.assertEqual(Path(before["resources"][0]["path"]), installed_skill / "scripts" / "run.py")

        old_root = self.installed
        moved_root = self.root / "relocated .code root" / "skills"
        moved_root.parent.mkdir(parents=True)
        shutil.move(str(old_root), str(moved_root))
        after = resolve_skill_resources("demo", moved_root, self.bundled)

        current_path = Path(after["resources"][0]["path"])
        self.assertEqual(after["source"], "installed")
        self.assertTrue(current_path.is_relative_to(moved_root))
        self.assertFalse(str(current_path).startswith(str(old_root)))
        self.assertEqual(bundled_skill.name, "demo")

    def test_custom_contract_resolves_inside_active_folder_without_writes(self):
        custom_skill = _write_skill(self.installed, "custom-tools", custom=True)
        before = _snapshot(custom_skill)

        resolved = resolve_skill_resources("custom-tools", self.installed, self.bundled)

        self.assertEqual(resolved["source"], "custom")
        self.assertEqual(
            Path(resolved["resources"][0]["path"]),
            custom_skill / "scripts" / "run.py",
        )
        self.assertIn("do not search", resolved["instructions"].lower())
        self.assertEqual(_snapshot(custom_skill), before)

    def test_relocated_custom_contract_uses_only_its_moved_active_path(self):
        custom_skill = _write_skill(self.installed, "custom-tools", custom=True)
        old_root = self.installed
        moved_root = self.root / "relocated custom profile with spaces" / "skills"
        moved_root.parent.mkdir(parents=True)
        shutil.move(str(old_root), str(moved_root))

        resolved = resolve_skill_resources("custom-tools", moved_root, self.bundled)
        actual = Path(resolved["resources"][0]["path"])

        self.assertEqual(resolved["source"], "custom")
        self.assertTrue(actual.is_relative_to(moved_root))
        self.assertFalse(str(actual).startswith(str(old_root)))
        self.assertEqual(actual.name, custom_skill.joinpath("scripts", "run.py").name)

    def test_default_same_root_custom_contract_projects_own_resources_and_dependencies(self):
        app_root = self.root / "Code Dev with spaces"
        shared_skills = app_root / "data" / "skills"
        custom_skill = _write_skill(
            shared_skills,
            "custom-tools",
            custom=True,
            resources={"scripts/run.py": b"print('same root custom')\n"},
        )
        before = _snapshot(custom_skill)
        with (
            mock.patch.object(server_mod, "APP_DIR", app_root),
            mock.patch.object(server_mod, "DATA_DIR", app_root / "data"),
            mock.patch.object(server_mod, "SKILLS_DIR", shared_skills),
        ):
            details = server_mod.read_skill("custom-tools")
            projected = server_mod.execute_use_skill_tool({"name": "custom-tools"})

        self.assertEqual(details["dependencyManifestSource"], "local")
        self.assertTrue(projected["ok"])
        self.assertEqual(projected["runtimeResources"]["source"], "custom")
        self.assertEqual(
            Path(projected["runtimeResources"]["resources"][0]["path"]),
            custom_skill / "scripts" / "run.py",
        )
        self.assertEqual(projected["dependencies"]["manifestSource"], "local")
        self.assertEqual(_snapshot(custom_skill), before)

    def test_custom_skill_without_contract_receives_no_paths_and_stable_guidance(self):
        skill = self.installed / "custom-no-contract"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\nname: custom-no-contract\ndescription: test\n---\nNo helpers published.\n",
            encoding="utf-8",
        )

        resolved = resolve_skill_resources("custom-no-contract", self.installed, self.bundled)

        self.assertEqual(resolved["source"], "custom-no-resources")
        self.assertEqual(resolved["resources"], [])
        self.assertIn("do not search", resolved["instructions"].lower())

    def test_default_same_root_custom_missing_and_tampered_contracts_fail_closed(self):
        shared_skills = self.root / "Code Dev with spaces" / "data" / "skills"
        custom_skill = _write_skill(shared_skills, "custom-tools", custom=True)
        helper = custom_skill / "scripts" / "run.py"

        helper.unlink()
        with self.assertRaises(SkillResourceError) as missing:
            resolve_skill_resources("custom-tools", shared_skills, shared_skills)
        self.assertEqual(missing.exception.error_code, "custom_resource_missing")

        helper.write_text("print('tampered')\n", encoding="utf-8")
        with self.assertRaises(SkillResourceError) as tampered:
            resolve_skill_resources("custom-tools", shared_skills, shared_skills)
        self.assertEqual(tampered.exception.error_code, "custom_resource_hash_mismatch")

    def test_same_name_custom_contract_never_inherits_bundled_resource(self):
        bundled_skill = _write_skill(self.bundled, "demo")
        custom_skill = _write_skill(
            self.installed,
            "demo",
            body="This is a user authored custom Skill.\n",
            custom=True,
            resources={"scripts/run.py": b"print('custom')\n"},
        )

        resolved = resolve_skill_resources("demo", self.installed, self.bundled)

        actual = Path(resolved["resources"][0]["path"])
        self.assertEqual(resolved["source"], "custom")
        self.assertTrue(actual.is_relative_to(custom_skill))
        self.assertFalse(actual.is_relative_to(bundled_skill))
        dependency_manifest = load_skill_manifest(custom_skill, self.bundled)
        self.assertEqual(dependency_manifest["source"], "local")

    def test_custom_contract_missing_tampered_traversal_and_reparse_fail_closed(self):
        skill = _write_skill(self.installed, "custom-tools", custom=True)
        helper = skill / "scripts" / "run.py"
        helper.unlink()
        with self.assertRaises(SkillResourceError) as missing:
            resolve_skill_resources("custom-tools", self.installed, self.bundled)
        self.assertEqual(missing.exception.error_code, "custom_resource_missing")

        helper.write_text("print('tampered')\n", encoding="utf-8")
        with self.assertRaises(SkillResourceError) as tampered:
            resolve_skill_resources("custom-tools", self.installed, self.bundled)
        self.assertEqual(tampered.exception.error_code, "custom_resource_hash_mismatch")

        manifest_path = skill / "code-resources.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["resources"][0]["path"] = "../escape.py"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(SkillResourceError) as traversal:
            resolve_skill_resources("custom-tools", self.installed, self.bundled)
        self.assertEqual(traversal.exception.error_code, "custom_resource_contract_invalid")

        malformed = self.installed / "custom-malformed"
        malformed.mkdir()
        (malformed / "SKILL.md").write_text(
            "---\nname: custom-malformed\ndescription: test\n---\nMalformed contract.\n",
            encoding="utf-8",
        )
        (malformed / "code-resources.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(SkillResourceError) as malformed_contract:
            resolve_skill_resources("custom-malformed", self.installed, self.bundled)
        self.assertEqual(malformed_contract.exception.error_code, "custom_resource_contract_invalid")

        _write_skill(self.installed, "custom-safe", custom=True)
        with mock.patch(
            "code_runtime.skill_resources._is_link_or_reparse",
            side_effect=lambda path: Path(path).name == "run.py",
        ):
            with self.assertRaises(SkillResourceError) as reparse:
                resolve_skill_resources("custom-safe", self.installed, self.bundled)
        self.assertEqual(reparse.exception.error_code, "custom_resource_path_unsafe")


class TestBundledSkillResourceAudit(unittest.TestCase):
    def test_audit_detects_declared_missing_helper_and_ignores_prose_examples(self):
        with tempfile.TemporaryDirectory(prefix="Code bundled resource audit ") as temp:
            bundled = Path(temp) / "data" / "skills"
            prose = bundled / "prose-only"
            prose.mkdir(parents=True)
            (prose / "SKILL.md").write_text(
                "Example only: `python scripts/not-a-contract.py`\n"
                "```bash\npython scripts/also-not-a-contract.py\n```\n",
                encoding="utf-8",
            )
            broken = _write_skill(bundled, "declared-helper")
            (broken / "scripts" / "run.py").unlink()

            audit = audit_bundled_skill_resources(bundled)

        self.assertFalse(audit["ok"])
        self.assertEqual(audit["contracts"], ["declared-helper"])
        self.assertEqual(audit["findings"], [{
            "skill": "declared-helper",
            "resource": "run-helper",
            "errorCode": "bundled_resource_missing",
        }])
        source = (ROOT / "code_runtime" / "skill_resources.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"(?i)(Path\.home|USERPROFILE|os\.walk|rglob\()")

    def test_audit_reports_reparse_entry_without_descending_into_it(self):
        with tempfile.TemporaryDirectory(prefix="Code bundled resource reparse ") as temp:
            bundled = Path(temp) / "data" / "skills"
            unsafe = bundled / "unsafe"
            unsafe.mkdir(parents=True)
            (unsafe / "SKILL.md").write_text("not read", encoding="utf-8")
            with mock.patch(
                "code_runtime.skill_resources._is_link_or_reparse",
                side_effect=lambda path: Path(path).name == "unsafe",
            ):
                audit = audit_bundled_skill_resources(bundled)
        self.assertFalse(audit["ok"])
        self.assertEqual(audit["checkedSkills"], [])
        self.assertEqual(audit["findings"], [{
            "skill": "unsafe",
            "errorCode": "resource_path_unsafe",
        }])


if __name__ == "__main__":
    unittest.main()
