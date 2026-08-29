import hashlib
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
PPTX_BASELINE_DIGEST = "244147f3830a24502c2b6e9f1efe4006f9974929fb1d3c529e7dc0aca39b6e9c"


def directory_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(root).as_posix(),
    ):
        relative = path.relative_to(root).as_posix()
        data = path.read_bytes()
        digest.update(f"{relative}\t{len(data)}\t{hashlib.sha256(data).hexdigest()}\n".encode())
    return digest.hexdigest()


class TestPptMasterStaticSkill(unittest.TestCase):
    def test_fixed_vendor_slice_passes_static_validation(self):
        result = validate_vendor_package(SKILL_DIR)
        self.assertTrue(result["ok"])
        self.assertEqual(result["commit"], COMMIT)
        self.assertEqual(result["tree"], TREE)
        self.assertEqual(result["executableEntrypoints"], 0)
        self.assertLess(result["fileCount"], 1_000)
        self.assertLess(result["totalBytes"], 15 * 1024 * 1024)

    def test_wrapper_is_flat_explicit_and_static_only(self):
        skills = {item["name"]: item for item in server_mod.list_skills()}
        skill = skills["ppt-master"]
        self.assertEqual(skill["dir"], "ppt-master")
        self.assertEqual(skill["keywords"], [])
        self.assertNotIn("run_command", skill["tools"])
        self.assertNotIn("write_file", skill["tools"])
        self.assertIn("STATIC_ONLY_DO_NOT_EXECUTE", skill["body"])
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
        self.assertIn("STATIC_ONLY_DO_NOT_EXECUTE", projected["body"])
        self.assertEqual(projected["dependencies"]["status"], "unavailable")

    def test_dependency_gate_is_stably_unavailable(self):
        status = server_mod.get_single_skill_dependency_status(
            "ppt-master", "offline-core"
        )
        self.assertEqual(status["status"], "unavailable")
        self.assertEqual(len(status["capabilities"]), 1)
        capability = status["capabilities"][0]
        self.assertEqual(capability["id"], "offline-core")
        self.assertEqual(capability["status"], "unavailable")
        missing = {item["name"] for item in capability["required"] if not item["available"]}
        self.assertEqual(missing, {"skia-pathops", "uharfbuzz"})

    def test_default_pptx_bytes_and_matching_stay_unchanged(self):
        self.assertEqual(directory_digest(PPTX_DIR), PPTX_BASELINE_DIGEST)
        self.assertEqual(len(list(PPTX_DIR.rglob("*"))), 2)

    def test_build_exe_recursively_packages_the_static_skill(self):
        source = (ROOT / "build_exe.py").read_text(encoding="utf-8")
        self.assertIn("APP_DIR / 'data' / 'skills'", source)
        manifest = json.loads((SKILL_DIR / "vendor-manifest.json").read_text(encoding="utf-8"))
        packaged = {
            path.relative_to(ROOT / "data" / "skills").as_posix()
            for path in SKILL_DIR.rglob("*")
            if path.is_file()
        }
        self.assertIn("ppt-master/SKILL.md", packaged)
        self.assertIn("ppt-master/vendor-manifest.json", packaged)
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
