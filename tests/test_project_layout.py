"""Deterministic contracts for the repository's top-level module layout."""

import ast
import importlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GOAL_V1_MODULES = ("goal_control", "goal_protocol", "goal_store")
RUNTIME_MODULES = (
    "agent_protocol",
    "bundled_skills",
    "context_calibration",
    "context_window",
    "data_dir_owner",
    "goal_runtime",
    "goal_v2_protocol",
    "goal_v2_store",
    "image_runtime",
    "model_route_registry",
    "official_model_capabilities",
    "ppt_master_runtime",
    "skill_dependencies",
    "skill_resources",
    "windows_explorer",
)
DEVTOOL_MODULES = ("release_state", "verification")


def first_party_runtime_sources():
    sources = list(ROOT.glob("*.py"))
    for relative in ("code_runtime", "devtools", "scripts"):
        source_root = ROOT / relative
        if source_root.is_dir():
            sources.extend(source_root.rglob("*.py"))
    return sorted(set(sources))


class TestProjectLayout(unittest.TestCase):
    def test_development_support_modules_live_only_in_devtools(self):
        devtools_root = ROOT / "devtools"
        self.assertEqual(
            sorted(path.name for path in devtools_root.iterdir() if path.is_file()),
            ["__init__.py", *(f"{name}.py" for name in DEVTOOL_MODULES)],
        )
        for module_name in DEVTOOL_MODULES:
            self.assertFalse((ROOT / f"{module_name}.py").exists())
            module = importlib.import_module(f"devtools.{module_name}")
            self.assertEqual(Path(module.__file__).resolve().parent, devtools_root.resolve())

        package_source = (devtools_root / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("import *", package_source)
        self.assertEqual(importlib.import_module("devtools.verification").ROOT, ROOT)
        self.assertIn("from devtools.release_state import", (ROOT / "release.py").read_text(encoding="utf-8"))
        self.assertIn("from devtools.verification import", (ROOT / "release.py").read_text(encoding="utf-8"))
        self.assertIn("from devtools.verification import", (ROOT / "verify.py").read_text(encoding="utf-8"))

    def test_backend_runtime_modules_live_only_in_code_runtime(self):
        runtime_root = ROOT / "code_runtime"
        self.assertEqual(
            sorted(path.name for path in runtime_root.iterdir() if path.is_file()),
            ["__init__.py", *(f"{name}.py" for name in RUNTIME_MODULES)],
        )
        for module_name in RUNTIME_MODULES:
            self.assertFalse((ROOT / f"{module_name}.py").exists())
            module = importlib.import_module(f"code_runtime.{module_name}")
            self.assertEqual(Path(module.__file__).resolve().parent, runtime_root.resolve())

        package_source = (runtime_root / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("import *", package_source)
        self.assertEqual(importlib.import_module("code_runtime.ppt_master_runtime").APP_ROOT, ROOT)
        self.assertIn("from code_runtime", (ROOT / "server.py").read_text(encoding="utf-8"))
        self.assertIn("from code_runtime", (ROOT / "launcher.py").read_text(encoding="utf-8"))
        self.assertIn(
            "from code_runtime import skill_dependencies",
            (ROOT / "scripts" / "install_locked_skill_wheels.py").read_text(encoding="utf-8"),
        )

    def test_goal_v1_root_modules_are_absent_and_have_no_runtime_consumer(self):
        for module_name in GOAL_V1_MODULES:
            self.assertFalse((ROOT / f"{module_name}.py").exists())

        forbidden_dynamic_import = re.compile(
            r"(?:import_module|__import__|spec_from_file_location)\s*\([^\n]*(?:goal_control|goal_protocol|goal_store)"
        )
        for path in first_party_runtime_sources():
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            imported_modules = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_modules.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_modules.add(node.module)
            self.assertTrue(
                imported_modules.isdisjoint(GOAL_V1_MODULES),
                f"{path.relative_to(ROOT)} imports Goal v1: "
                f"{sorted(imported_modules.intersection(GOAL_V1_MODULES))}",
            )
            self.assertIsNone(
                forbidden_dynamic_import.search(source),
                f"{path.relative_to(ROOT)} dynamically imports Goal v1",
            )

        self.assertIn("data/goals/", (ROOT / ".gitignore").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
