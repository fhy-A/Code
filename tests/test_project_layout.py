"""Deterministic contracts for the repository's top-level module layout."""

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GOAL_V1_MODULES = ("goal_control", "goal_protocol", "goal_store")


def first_party_runtime_sources():
    sources = list(ROOT.glob("*.py"))
    for relative in ("code_runtime", "devtools", "scripts"):
        source_root = ROOT / relative
        if source_root.is_dir():
            sources.extend(source_root.rglob("*.py"))
    return sorted(set(sources))


class TestProjectLayout(unittest.TestCase):
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
