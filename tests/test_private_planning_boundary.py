import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

APPROVED_PUBLIC_DIRECTIONS = (
    "完善项目级文件预览与多标签工作区",
    "持续优化桌面端界面一致性与窄屏体验",
    "提升会话导入、用量统计与兼容性",
    "完善跨平台安装、依赖检测、更新与公开文档",
)


def read_public(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def public_todo_boundary_violations(source: str) -> set[str]:
    violations = set()
    sections = list(re.finditer(
        r"(?ms)^## 近期方向\s*$\n(?P<body>.*?)(?=^## |\Z)",
        source,
    ))
    if len(sections) != 1:
        violations.add("directions")
    else:
        directions = tuple(
            match.group(1).strip()
            for line in sections[0].group("body").splitlines()
            if (match := re.fullmatch(r"\s*-\s+(.+?)\s*", line))
        )
        if directions != APPROVED_PUBLIC_DIRECTIONS:
            violations.add("directions")
    if re.search(r"(?:CODE|WB)-\d{3}", source):
        violations.add("task_id")
    if any(term in source for term in ("渠道", "供应商", "安全缺口")):
        violations.add("sensitive_detail")
    if re.search(
        r"(?<!\d)(?:19|20)\d{2}(?:-\d{1,2}-\d{1,2}|/\d{1,2}/\d{1,2}|年\d{1,2}月\d{1,2}日)(?!\d)",
        source,
    ):
        violations.add("date")
    return violations


class PrivatePlanningBoundaryTests(unittest.TestCase):
    def test_public_todo_is_sanitized_non_executable_short_term_summary(self):
        source = read_public("TODO.md")
        self.assertIn("<!-- workbar-public-short-term-summary/v1 -->", source)
        self.assertIn("公开、脱敏、非执行事实源", source)
        for item in APPROVED_PUBLIC_DIRECTIONS:
            self.assertEqual(source.count(item), 1, item)
        self.assertEqual(set(), public_todo_boundary_violations(source))
        self.assertIn("顺序不代表优先级", source)
        self.assertIn("不构成排期或发布承诺", source)
        self.assertIn("不得据此自动选择或启动任务", source)
        self.assertIn("仅在用户明确批准后人工更新", source)
        self.assertIn("不得从私有 TODO 自动同步", source)
        for forbidden in (
            "最后已分配编号",
            "当前进行",
            "可直接启动",
            "外部等待",
            "下一动作",
            "完成定义",
            "依赖：",
            "related:",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("../workbar-private/TODO.md", source)

    def test_public_todo_adversarial_samples_are_rejected(self):
        source = read_public("TODO.md")
        fourth = f"- {APPROVED_PUBLIC_DIRECTIONS[-1]}"
        samples = {
            "fifth direction": (
                source.replace(fourth, f"{fourth}\n- 增加第五个公开方向", 1),
                "directions",
            ),
            "embedded CODE id": (
                source.replace("高层短期方向", "高层短期方向（内部CODE-054）", 1),
                "task_id",
            ),
            "embedded WB id": (
                source.replace("高层短期方向", "高层短期方向（内部WB-014）", 1),
                "task_id",
            ),
            "channel detail": (
                source.replace("高层短期方向", "高层短期方向及渠道", 1),
                "sensitive_detail",
            ),
            "vendor detail": (
                source.replace("高层短期方向", "高层短期方向及供应商", 1),
                "sensitive_detail",
            ),
            "security gap": (
                source.replace("高层短期方向", "高层短期方向及安全缺口", 1),
                "sensitive_detail",
            ),
            "specific date": (
                source.replace("高层短期方向", "2026-09-15 前的高层短期方向", 1),
                "date",
            ),
        }
        for label, (candidate, expected_violation) in samples.items():
            with self.subTest(label=label):
                self.assertIn(
                    expected_violation,
                    public_todo_boundary_violations(candidate),
                )

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
            self.assertIn("公开、脱敏、非执行", source, path)
            self.assertIn("不得据此自动选择或启动任务", source, path)
            self.assertIn("仅在用户明确批准后人工更新", source, path)
            self.assertIn("不得从私有 TODO 自动同步", source, path)
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
        for path in (
            "README.md",
            "docs/development-log/README.md",
            "docs/release-guide.md",
            "docs/approval-relay-protocol.md",
        ):
            source = read_public(path)
            self.assertIn("公开", source, path)
            self.assertIn("摘要", source, path)
            self.assertIn("不得据此自动选择或启动任务", source, path)
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
        self.assertIn("不得重建", sources)
        self.assertIn("公开摘要", sources)


if __name__ == "__main__":
    unittest.main()
