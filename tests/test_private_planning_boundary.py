import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_public(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class PrivatePlanningBoundaryTests(unittest.TestCase):
    def test_public_todo_is_marker_only_compatibility_stub(self):
        source = read_public("TODO.md")
        self.assertIn("<!-- workbar-private-plan-stub/v1 -->", source)
        self.assertIsNone(re.search(r"(?m)^### (?:CODE|WB)-\d{3}\b", source))
        for forbidden in ("最后已分配编号", "当前进行", "可直接启动", "外部等待"):
            self.assertNotIn(forbidden, source)
        self.assertIn("../workbar-private/TODO.md", source)
        self.assertIn("用户显式", source)
        self.assertIn("不得", source)

    def test_public_handoff_is_marker_only_compatibility_stub(self):
        source = read_public("docs/development-handoff.md")
        self.assertIn("<!-- workbar-private-handoff-stub/v1 -->", source)
        self.assertNotIn("状态：`active`", source)
        self.assertIsNone(re.search(r"(?m)^- 任务 ID：", source))
        self.assertIn("../../workbar-private/development-handoff.md", source)
        self.assertIn("用户显式", source)

    def test_code_collaboration_rules_point_to_private_fact_sources(self):
        for path in ("AGENTS.md", "CLAUDE.md"):
            source = read_public(path)
            self.assertIn("../workbar-private/TODO.md", source, path)
            self.assertIn("../workbar-private/development-handoff.md", source, path)
            self.assertIn("私有", source, path)
            self.assertIn("缺失", source, path)
            self.assertIn("用户显式", source, path)
            for legacy in (
                "未完成项目事项以 `TODO.md` 为准",
                "未完成事项统一写入本目录的 `TODO.md`",
                "将剩余事项写入 `TODO.md`",
                "创建或更新 `docs/development-handoff.md`",
            ):
                self.assertNotIn(legacy, source, f"{path}: {legacy}")

    def test_public_guidance_keeps_completed_facts_public_and_plans_private(self):
        expected_private_refs = {
            "README.md": "../workbar-private/TODO.md",
            "docs/development-log/README.md": "../../../workbar-private/TODO.md",
            "docs/development-handoff-template.md": "../../workbar-private/development-handoff.md",
            "docs/release-guide.md": "../../workbar-private/TODO.md",
            "docs/approval-relay-protocol.md": "../../workbar-private/TODO.md",
        }
        for path, private_ref in expected_private_refs.items():
            source = read_public(path)
            self.assertIn(private_ref, source, path)
            self.assertIn("私有", source, path)
        log_rules = read_public("docs/development-log/README.md")
        self.assertIn("完成事实", log_rules)
        self.assertNotIn("未完成事项写入项目根目录 `TODO.md`", log_rules)

    def test_public_boundary_never_requires_private_directory_to_exist(self):
        sources = "\n".join(read_public(path) for path in (
            "TODO.md",
            "docs/development-handoff.md",
            "AGENTS.md",
            "CLAUDE.md",
            "README.md",
        ))
        self.assertIn("私有事实源缺失", sources)
        self.assertIn("用户显式", sources)
        self.assertIn("不得创建", sources)
        self.assertIn("公开 stub", sources)


if __name__ == "__main__":
    unittest.main()
