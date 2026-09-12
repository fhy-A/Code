import tempfile
import unittest
from pathlib import Path
from unittest import mock

import server as server_mod


# Hermetic fixtures: the Skill frontmatter parser is line-based, so a YAML block
# written under "metadata:" arrives as the string "" (json.loads("") raises) and
# not as a parsed mapping.  That is exactly the shape that used to degrade into
# the literal capability name "None".
YAML_BLOCK_METADATA_SKILL = """---
name: demo-yaml
description: yaml block metadata without a JSON toolCapability
metadata:
  keywords: demo
  tools: read_file
---

Body.
"""

JSON_TOOL_CAPABILITY_SKILL = """---
name: demo-json
description: explicit JSON metadata declaring a tool capability
metadata: {"toolCapability": "offline-core"}
tools: read_file
---

Body.
"""


class TestSkillFrontmatterCapability(unittest.TestCase):
    def _write_skill(self, root, name, text):
        skill_dir = Path(root) / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
        return skill_dir

    def test_yaml_block_metadata_parses_to_an_empty_metadata_string(self):
        meta, _ = server_mod.parse_memory_frontmatter(YAML_BLOCK_METADATA_SKILL)
        self.assertEqual(meta["metadata"], "")

    def test_missing_tool_capability_is_not_a_literal_None_capability(self):
        with tempfile.TemporaryDirectory() as temp:
            skill_dir = self._write_skill(temp, "demo-yaml", YAML_BLOCK_METADATA_SKILL)
            meta, _ = server_mod.parse_memory_frontmatter(YAML_BLOCK_METADATA_SKILL)
            with mock.patch.object(server_mod, "inspect_skill_directory") as inspect:
                tools = server_mod._skill_frontmatter_tools(meta, skill_dir)
            inspect.assert_not_called()
            self.assertEqual(tools, ["read_file"])

    def test_brief_skill_list_keeps_tools_without_probing_dependencies(self):
        with tempfile.TemporaryDirectory() as temp:
            self._write_skill(temp, "demo-yaml", YAML_BLOCK_METADATA_SKILL)
            with (
                mock.patch.object(server_mod, "SKILLS_DIR", Path(temp)),
                mock.patch.object(server_mod, "inspect_skill_directory") as inspect,
            ):
                skills = server_mod.list_skills(brief=True)
            inspect.assert_not_called()
            self.assertEqual([item["name"] for item in skills], ["demo-yaml"])
            self.assertEqual(skills[0]["tools"], ["read_file"])

    def test_declared_tool_capability_still_runs_the_dependency_probe(self):
        with tempfile.TemporaryDirectory() as temp:
            skill_dir = self._write_skill(temp, "demo-json", JSON_TOOL_CAPABILITY_SKILL)
            meta, _ = server_mod.parse_memory_frontmatter(JSON_TOOL_CAPABILITY_SKILL)
            self.assertEqual(meta["metadata"], '{"toolCapability": "offline-core"}')
            with mock.patch.object(
                server_mod, "inspect_skill_directory", return_value={"status": "ready"}
            ) as inspect:
                tools = server_mod._skill_frontmatter_tools(meta, skill_dir)
            inspect.assert_called_once()
            self.assertEqual(inspect.call_args.kwargs["capability_id"], "offline-core")
            self.assertEqual(tools, ["read_file"])

    def test_unready_dependency_probe_still_hides_declared_tools(self):
        with tempfile.TemporaryDirectory() as temp:
            skill_dir = self._write_skill(temp, "demo-json", JSON_TOOL_CAPABILITY_SKILL)
            meta, _ = server_mod.parse_memory_frontmatter(JSON_TOOL_CAPABILITY_SKILL)
            with mock.patch.object(
                server_mod, "inspect_skill_directory", return_value={"status": "unavailable"}
            ):
                tools = server_mod._skill_frontmatter_tools(meta, skill_dir)
            self.assertEqual(tools, [])


if __name__ == "__main__":
    unittest.main()
