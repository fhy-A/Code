import importlib.util
import re
import unittest
from pathlib import Path

import server as server_mod
from skill_dependencies import load_skill_manifest


SKILLS_ROOT = Path(server_mod.SKILLS_DIR)
WORKFLOW_SKILLS = {
    "brainstorming",
    "dispatching-parallel-agents",
    "executing-plans",
    "receiving-code-review",
    "requesting-code-review",
    "subagent-driven-development",
    "test-driven-development",
    "writing-plans",
}
DEPENDENCY_SKILLS = {
    "document-design",
    "docx",
    "hyperframes",
    "image-generation",
    "mcp-builder",
    "office-files",
    "pdf",
    "ppt-master",
    "pptx",
    "web-artifacts-builder",
    "xlsx",
}


def load_skill_validator():
    path = SKILLS_ROOT / "skill-creator" / "scripts" / "quick_validate.py"
    spec = importlib.util.spec_from_file_location("code_skill_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_skill


class TestBuiltInSkillRouting(unittest.TestCase):
    def skill_names_for(self, prompt):
        return [skill["name"] for skill in server_mod.match_skills(prompt)]

    def test_description_words_do_not_trigger_automatic_loading(self):
        self.assertEqual(
            self.skill_names_for("解释一下 Python 装饰器的工作原理"),
            [],
        )

    def test_representative_prompts_route_to_one_specific_skill(self):
        cases = {
            "帮我审查 server.py 的改动，找出潜在 bug": ["code-review"],
            "为 parser.py 补充 pytest 单元测试并运行": ["python-testing"],
            "读取 docs/report.pdf 并提取前三页内容": ["office-files", "pdf"],
            "生成一份正式的 Word 项目周报": ["document-design"],
            "用 matplotlib 画一张月度销量折线图": ["image-generation"],
            "重新设计欢迎页的布局和视觉样式": ["design-aesthetics"],
            "根据截图分析按钮为什么错位，只需要诊断": ["design-aesthetics"],
            "这条代码审查意见建议删除兼容层，帮我判断是否合理": ["receiving-code-review"],
            "有没有适合做 React 性能优化的 Skill": ["find-skills"],
        }
        for prompt, expected in cases.items():
            with self.subTest(prompt=prompt):
                self.assertEqual(self.skill_names_for(prompt), expected)

    def test_action_requests_do_not_load_review_or_chart_skills(self):
        prompts = (
            "server.py 有个 bug，帮我直接修复",
            "修复上传接口的路径遍历漏洞",
            "生成一张未来城市的 AI 海报",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertEqual(self.skill_names_for(prompt), [])


class TestBuiltInSkillMetadata(unittest.TestCase):
    def test_declared_tools_are_available_in_code(self):
        available = set(server_mod.SERVER_TOOL_REGISTRY)
        for skill in server_mod.list_skills(brief=True):
            with self.subTest(skill=skill["name"]):
                self.assertLessEqual(set(skill.get("tools") or []), available)

    def test_skill_name_matches_directory(self):
        for skill in server_mod.list_skills(brief=True):
            with self.subTest(skill=skill["name"]):
                self.assertEqual(skill["name"], skill["dir"])

    def test_workflow_skills_declare_the_code_tools_they_may_use(self):
        skills = {skill["name"]: skill for skill in server_mod.list_skills(brief=True)}
        for name in WORKFLOW_SKILLS:
            with self.subTest(skill=name):
                self.assertTrue(skills[name].get("tools"))

    def test_workflow_skills_do_not_reference_uninstalled_superpowers(self):
        for name in WORKFLOW_SKILLS:
            text = (SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8-sig")
            with self.subTest(skill=name):
                self.assertNotIn("superpowers:", text.lower())

    def test_relative_markdown_links_resolve_inside_the_skill(self):
        for skill_md in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
            text = skill_md.read_text(encoding="utf-8-sig")
            text_without_fences = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text_without_fences):
                if "://" in target or target.startswith("#"):
                    continue
                relative = target.split("#", 1)[0]
                with self.subTest(skill=skill_md.parent.name, target=target):
                    self.assertTrue((skill_md.parent / relative).is_file())

    def test_skill_instructions_stay_below_500_lines(self):
        for skill_md in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
            line_count = len(skill_md.read_text(encoding="utf-8-sig").splitlines())
            with self.subTest(skill=skill_md.parent.name):
                self.assertLess(line_count, 500)

    def test_every_bundled_skill_passes_the_packaging_validator(self):
        validate_skill = load_skill_validator()
        for skill_dir in sorted(path for path in SKILLS_ROOT.iterdir() if path.is_dir()):
            valid, message = validate_skill(skill_dir)
            with self.subTest(skill=skill_dir.name, message=message):
                self.assertTrue(valid, message)

    def test_dependency_skills_have_valid_machine_readable_manifests(self):
        declared = set()
        for skill_dir in sorted(path for path in SKILLS_ROOT.iterdir() if path.is_dir()):
            manifest = load_skill_manifest(skill_dir)
            if manifest:
                declared.add(skill_dir.name)
        self.assertEqual(declared, DEPENDENCY_SKILLS)

    def test_use_skill_requires_a_separate_tool_round(self):
        description = server_mod.SERVER_TOOL_REGISTRY["use_skill"]["definition"]["function"]["description"]
        self.assertIn("alone", description.lower())
        self.assertIn("wait", description.lower())

    def test_brainstorming_has_a_bounded_default_exploration_budget(self):
        text = (SKILLS_ROOT / "brainstorming" / "SKILL.md").read_text(encoding="utf-8-sig")
        self.assertIn("默认探索预算", text)
        self.assertIn("最多进行 3 次搜索或文件枚举、4 次定向读取", text)
        self.assertIn("不要用多个近义查询反复搜索同一实现", text)
        self.assertIn("待验证", text)
        self.assertIn("最终回答检查", text)
        self.assertIn("没有基准测试支撑的性能排序", text)


if __name__ == "__main__":
    unittest.main()
