import json
import unittest
from pathlib import Path

import server as server_mod
from scripts.validate_ppt_master_vendor import (
    COMMIT,
    TREE,
    validate_vendor_package,
)


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "data" / "skills" / "ppt-master"
PPTX_DIR = ROOT / "data" / "skills" / "pptx"
class TestPptMasterRuntimeSkill(unittest.TestCase):
    def test_fixed_vendor_slice_passes_static_validation(self):
        result = validate_vendor_package(SKILL_DIR)
        self.assertTrue(result["ok"])
        self.assertEqual(result["commit"], COMMIT)
        self.assertEqual(result["tree"], TREE)
        self.assertEqual(result["executableEntrypoints"], 0)
        self.assertLess(result["fileCount"], 1_000)
        self.assertLess(result["totalBytes"], 15 * 1024 * 1024)

    def test_wrapper_is_flat_explicit_and_runtime_gated(self):
        skills = {item["name"]: item for item in server_mod.list_skills()}
        skill = skills["ppt-master"]
        self.assertEqual(skill["dir"], "ppt-master")
        self.assertEqual(skill["keywords"], [])
        self.assertNotIn("run_command", skill["tools"])
        self.assertNotIn("write_file", skill["tools"])
        self.assertEqual(skill["tools"], ["create_ppt_master_deck"])
        self.assertNotIn("STATIC_ONLY_DO_NOT_EXECUTE", skill["body"])
        self.assertIn("/ppt-master", skill["body"])
        self.assertNotIn("${SKILL_DIR}", skill["body"])

        self.assertEqual(
            [item["name"] for item in server_mod.match_skills("创建 ppt")],
            ["pptx"],
        )
        self.assertNotIn(
            "ppt-master",
            [item["name"] for item in server_mod.match_skills("帮我生成一份 PPT 汇报")],
        )
        self.assertEqual(
            [item["name"] for item in server_mod.match_skills("请显式使用 ppt-master")],
            ["ppt-master"],
        )
        projected = server_mod.execute_use_skill_tool({"name": "ppt-master"})
        self.assertTrue(projected["ok"])
        self.assertIn("create_ppt_master_deck", projected["body"])
        self.assertEqual(projected["dependencies"]["status"], "ready")
        self.assertEqual(projected["tools"], ["create_ppt_master_deck"])

    def test_dependency_gate_is_ready_with_exact_locked_versions(self):
        status = server_mod.get_single_skill_dependency_status(
            "ppt-master", "offline-core"
        )
        self.assertEqual(status["status"], "ready")
        self.assertEqual(len(status["capabilities"]), 1)
        capability = status["capabilities"][0]
        self.assertEqual(capability["id"], "offline-core")
        self.assertEqual(capability["status"], "ready")
        versions = {
            item["name"]: item["detectedVersion"]
            for item in capability["required"]
            if item["name"] in {"skia-pathops", "uharfbuzz"}
        }
        self.assertEqual(versions, {"skia-pathops": "0.9.2", "uharfbuzz": "0.50.0"})

    def test_default_pptx_skill_has_only_declared_clean_room_runtime_resources(self):
        packaged = {
            path.relative_to(PPTX_DIR).as_posix()
            for path in PPTX_DIR.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        self.assertEqual(packaged, {
            "SKILL.md",
            "dependencies.json",
            "code-resources.json",
            "scripts/render.py",
            "scripts/office/validate.py",
        })
        manifest = json.loads((PPTX_DIR / "code-resources.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["skill"], "pptx")
        self.assertEqual(
            {item["id"] for item in manifest["resources"]},
            {"validate-deck", "render-pdf"},
        )
        skill_text = (PPTX_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("runtimeResources", skill_text)
        self.assertNotIn("claude-skills", skill_text)
        self.assertNotIn("scripts/", skill_text)

    def test_build_exe_recursively_packages_the_static_skill(self):
        source = (ROOT / "build_exe.py").read_text(encoding="utf-8")
        self.assertIn("APP_DIR / 'data' / 'skills'", source)
        self.assertIn("prepare_bundled_skills_for_packaging", source)
        self.assertIn('ignore_patterns("__pycache__", "*.pyc")', source)
        self.assertIn('f"{PACKAGED_SKILLS_DIR}{\';\'}data/skills"', source)
        manifest = json.loads((SKILL_DIR / "vendor-manifest.json").read_text(encoding="utf-8"))
        packaged = {
            path.relative_to(ROOT / "data" / "skills").as_posix()
            for path in SKILL_DIR.rglob("*")
            if path.is_file()
        }
        self.assertIn("ppt-master/SKILL.md", packaged)
        self.assertIn("ppt-master/vendor-manifest.json", packaged)
        self.assertIn("ppt-master/dependency-lock.json", packaged)
        self.assertIn("ppt-master/dependency-receipt.json", packaged)
        self.assertEqual(
            len([item for item in packaged if item.startswith("ppt-master/vendor/")]),
            manifest["fileCount"],
        )
        banned_fragments = (
            "/brands/", "/decks/", "/icons/", "/sounds/", "/confirm_ui/",
            "/svg_editor/", "/image_backends/", "/tts_backends/",
        )
        self.assertFalse(
            any(fragment in f"/{path.lower()}/" for path in packaged for fragment in banned_fragments)
        )


if __name__ == "__main__":
    unittest.main()
