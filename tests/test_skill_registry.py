import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import server as server_mod
from code_runtime import skill_registry
from code_runtime.skill_registry import (
    SkillRegistryError,
    build_skill_registry_snapshot,
    compare_observed_and_shadow,
    parse_skill_document,
    project_skill_tools,
    resolve_skill_shadow,
)


def _write_skill(
    root,
    directory,
    *,
    name=None,
    description="Test Skill",
    keywords="",
    tools="read_file",
    body="Do the task safely.",
    extra_frontmatter="",
):
    skill_dir = Path(root) / directory
    skill_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"name: {name or directory}",
        f"description: {description}",
    ]
    if keywords:
        lines.append(f"keywords: {keywords}")
    if tools:
        lines.append(f"tools: {tools}")
    if extra_frontmatter:
        lines.extend(extra_frontmatter.strip().splitlines())
    lines.extend(["---", "", body])
    (skill_dir / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")
    return skill_dir


def _descriptor(snapshot, name, source="installed", directory=None):
    matches = [
        item for item in snapshot["descriptors"]
        if item["name"] == name
        and item["source"]["kind"] == source
        and (directory is None or item["source"]["directory"] == directory)
    ]
    if len(matches) != 1:
        raise AssertionError((name, source, directory, matches))
    return matches[0]


def _bundled_frontend_skills():
    """Build the exact metadata/body shape consumed by the existing JS path."""
    skills = []
    for item in server_mod.list_skills(brief=True):
        text = (
            Path(server_mod.SKILLS_DIR) / item["dir"] / "SKILL.md"
        ).read_text(encoding="utf-8-sig")
        _meta, body = server_mod.parse_memory_frontmatter(text)
        skills.append({
            **item,
            "body": body.strip(),
            "dependencyCapabilities": {},
        })
    return skills


def _frontend_skill_observations(skills, cases):
    script = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
global.window = {Code: {features: {}}};
require("./src/features/skills-memory.js");
const {createSkillsMemoryFeature, rankMatchedSkills} = window.Code.features.skillsMemory;

function namesFromInstruction(instruction) {
  const explicit = String(instruction).match(/已激活 Skill: ([^（]+)（/);
  if (explicit) return [explicit[1]];
  return [...String(instruction).matchAll(/\[Skill: ([^\]]+)\]/g)].map((match) => match[1]);
}

(async () => {
  const observations = [];
  for (const testCase of input.cases) {
    const available = (testCase.skills || input.skills).map((skill) => ({...skill}));
    const disabled = new Set(testCase.disabled || []);
    const ranked = rankMatchedSkills(available, disabled, testCase.prompt);
    const state = {skills: available, disabledSkills: disabled};
    const feature = createSkillsMemoryFeature({
      state,
      elements: {},
      apiJson: async () => { throw new Error("preloaded Skill fixture fetched unexpectedly"); },
      document: {getElementById: () => null},
      storage: {setItem: () => {}},
    });
    const snapshot = await feature.getSkillPromptSnapshot(
      testCase.prompt,
      testCase.explicitSkill || "",
      {skills: available, disabledSkills: disabled},
    );
    observations.push({
      rankedNames: ranked.map((skill) => skill.name),
      activeSkillNames: [...snapshot.activeSkillNames],
      promptNames: namesFromInstruction(snapshot.instruction),
      activeBodyLengths: snapshot.activeSkillNames.map((name) => (
        available.find((skill) => skill.name === name)?.body?.length || 0
      )),
    });
  }
  process.stdout.write(JSON.stringify(observations));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=Path(server_mod.APP_DIR),
        input=json.dumps({"skills": skills, "cases": cases}, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(completed.stdout)


class TestSkillDocumentParser(unittest.TestCase):
    def test_real_yaml_parses_code_legacy_shapes_without_calling_them_standard(self):
        parsed = parse_skill_document("""---
name: report-skill
description: >
  Build a checked
  report.
license: Apache-2.0
compatibility:
  os: [windows, linux]
allowed-tools:
  - read_file
  - run_command
metadata:
  keywords:
    - report+audit
    - 报告+审计
  owner:
    team: documents
version: 2
future-field:
  enabled: true
---

Follow the workflow.
""")

        self.assertEqual(parsed["meta"]["name"], "report-skill")
        self.assertEqual(parsed["meta"]["description"], "Build a checked report.\n")
        self.assertEqual(parsed["meta"]["allowed-tools"], ["read_file", "run_command"])
        self.assertEqual(parsed["meta"]["metadata"]["owner"]["team"], "documents")
        self.assertEqual(parsed["body"], "Follow the workflow.")

    def test_duplicate_keys_and_aliases_fail_closed(self):
        cases = (
            "---\nname: one\nname: two\ndescription: test\n---\nBody\n",
            "---\nname: &name demo\ndescription: *name\n---\nBody\n",
        )
        for text in cases:
            with self.subTest(text=text):
                with self.assertRaises(SkillRegistryError):
                    parse_skill_document(text)

    def test_memory_style_text_without_yaml_envelope_is_not_guessed(self):
        with self.assertRaisesRegex(SkillRegistryError, "frontmatter"):
            parse_skill_document("name: demo\ndescription: test\n\nBody")

    def test_tool_policy_can_only_narrow_or_express_legacy_preference(self):
        narrow_descriptor = {
            "allowedTools": ["read_file", "unavailable_tool"],
            "toolPolicy": {"mode": "narrow-only"},
        }
        legacy_descriptor = {
            "allowedTools": ["read_file", "unavailable_tool"],
            "toolPolicy": {"mode": "preference-only"},
        }
        permission_profile = ["read_file", "write_file"]

        narrowed = project_skill_tools(narrow_descriptor, permission_profile)
        preferred = project_skill_tools(legacy_descriptor, permission_profile)

        self.assertEqual(narrowed["allowed"], ["read_file"])
        self.assertEqual(narrowed["preferred"], ["read_file"])
        self.assertEqual(preferred["allowed"], permission_profile)
        self.assertEqual(preferred["preferred"], ["read_file"])
        self.assertNotIn("unavailable_tool", narrowed["allowed"])
        self.assertNotIn("unavailable_tool", preferred["allowed"])


class TestSkillRegistrySnapshot(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.installed = self.root / "profile" / "skills"
        self.bundled = self.root / "app" / "data" / "skills"
        self.installed.mkdir(parents=True)
        self.bundled.mkdir(parents=True)

    def tearDown(self):
        self.temporary.cleanup()

    def test_official_agent_skills_frontmatter_is_standard(self):
        _write_skill(
            self.installed,
            "official-skill",
            tools="",
            extra_frontmatter="""license: Apache-2.0
compatibility: Requires git and access to the local workspace
metadata:
  author: example-org
  version: "1.2"
allowed-tools: Bash(git:*) Bash(jq:*) Read""",
        )
        _write_skill(
            self.installed,
            "official-workbar-tool",
            tools="",
            extra_frontmatter="allowed-tools: read_file Bash(git:*)",
        )

        snapshot = build_skill_registry_snapshot(self.installed, self.installed)
        descriptor = _descriptor(snapshot, "official-skill")
        workbar_descriptor = _descriptor(snapshot, "official-workbar-tool")

        self.assertEqual(descriptor["format"], {
            "classification": "agent-skills-standard",
            "standardCompliant": True,
            "legacyCompatible": True,
            "reasonCodes": [],
        })
        self.assertEqual(descriptor["version"], "1.2")
        self.assertEqual(
            descriptor["allowedToolsRaw"],
            "Bash(git:*) Bash(jq:*) Read",
        )
        self.assertEqual(
            descriptor["allowedToolTokens"],
            ["Bash(git:*)", "Bash(jq:*)", "Read"],
        )
        projection = project_skill_tools(
            descriptor,
            ["read_file", "run_command"],
        )
        self.assertEqual(projection["allowed"], [])
        self.assertEqual(projection["preferred"], [])
        workbar_projection = project_skill_tools(
            workbar_descriptor,
            ["read_file", "run_command"],
        )
        self.assertEqual(workbar_projection["allowed"], ["read_file"])
        self.assertNotIn("Bash(git:*)", workbar_projection["allowed"])

    def test_code_legacy_yaml_shapes_remain_observable_but_not_standard(self):
        _write_skill(
            self.installed,
            "legacy-shapes",
            tools="",
            extra_frontmatter="""compatibility:
  os: [windows, linux]
allowed-tools:
  - read_file
  - run_command
metadata:
  owner:
    team: documents
version: 2
future-field:
  enabled: true""",
        )
        _write_skill(
            self.installed,
            "legacy-comma-tools",
            tools="",
            extra_frontmatter="allowed-tools: read_file, run_command",
        )

        snapshot = build_skill_registry_snapshot(self.installed, self.installed)
        descriptor = _descriptor(snapshot, "legacy-shapes")
        comma_descriptor = _descriptor(snapshot, "legacy-comma-tools")

        self.assertEqual(descriptor["health"], "ready")
        self.assertTrue(descriptor["executableCandidate"])
        self.assertEqual(descriptor["format"]["classification"], "code-legacy")
        self.assertFalse(descriptor["format"]["standardCompliant"])
        self.assertTrue(descriptor["format"]["legacyCompatible"])
        self.assertEqual(descriptor["allowedToolTokens"], ["read_file", "run_command"])
        self.assertEqual(descriptor["version"], "2")
        self.assertEqual(set(descriptor["format"]["reasonCodes"]), {
            "code_legacy_top_level_fields",
            "standard_allowed_tools_invalid",
            "standard_compatibility_invalid",
            "standard_metadata_invalid",
            "standard_unknown_top_level_fields",
        })
        self.assertEqual(comma_descriptor["format"]["classification"], "code-legacy")
        self.assertEqual(
            comma_descriptor["allowedToolTokens"],
            ["read_file", "run_command"],
        )
        self.assertEqual(
            comma_descriptor["legacyAdapters"]["allowedTools"],
            "legacy-allowed-tools-comma-string",
        )

    def test_official_name_description_and_compatibility_boundaries(self):
        names = {
            "name64": "a" * 64,
            "name65": "b" * 65,
            "consecutive": "bad--name",
            "description1024": "description-1024",
            "description1025": "description-1025",
            "compatibility500": "compatibility-500",
            "compatibility501": "compatibility-501",
        }
        _write_skill(self.installed, names["name64"], tools="")
        _write_skill(self.installed, names["name65"], tools="")
        _write_skill(self.installed, names["consecutive"], tools="")
        _write_skill(
            self.installed,
            names["description1024"],
            tools="",
            description="d" * 1024,
        )
        _write_skill(
            self.installed,
            names["description1025"],
            tools="",
            description="d" * 1025,
        )
        _write_skill(
            self.installed,
            names["compatibility500"],
            tools="",
            extra_frontmatter=f"compatibility: {'c' * 500}",
        )
        _write_skill(
            self.installed,
            names["compatibility501"],
            tools="",
            extra_frontmatter=f"compatibility: {'c' * 501}",
        )

        snapshot = build_skill_registry_snapshot(self.installed, self.installed)
        formats = {
            key: _descriptor(snapshot, value)["format"]
            for key, value in names.items()
        }

        self.assertEqual(formats["name64"]["classification"], "agent-skills-standard")
        self.assertEqual(formats["description1024"]["classification"], "agent-skills-standard")
        self.assertEqual(formats["compatibility500"]["classification"], "agent-skills-standard")
        self.assertEqual(formats["name65"]["classification"], "code-legacy")
        self.assertIn("standard_name_invalid", formats["name65"]["reasonCodes"])
        self.assertEqual(formats["consecutive"]["classification"], "code-legacy")
        self.assertIn("standard_name_invalid", formats["consecutive"]["reasonCodes"])
        self.assertEqual(formats["description1025"]["classification"], "code-legacy")
        self.assertIn(
            "standard_description_invalid",
            formats["description1025"]["reasonCodes"],
        )
        self.assertEqual(formats["compatibility501"]["classification"], "code-legacy")
        self.assertIn(
            "standard_compatibility_invalid",
            formats["compatibility501"]["reasonCodes"],
        )

    def test_snapshot_is_deterministic_and_preserves_distinct_sources(self):
        for name in ("zeta", "alpha"):
            bundled = _write_skill(self.bundled, name, keywords=f"{name}+task")
            shutil.copytree(bundled, self.installed / name)

        first = build_skill_registry_snapshot(self.installed, self.bundled)
        second = build_skill_registry_snapshot(self.installed, self.bundled)
        relocated_installed = self.root / "relocated" / "profile" / "skills"
        relocated_bundled = self.root / "relocated" / "app" / "data" / "skills"
        shutil.copytree(self.installed, relocated_installed)
        shutil.copytree(self.bundled, relocated_bundled)
        relocated = build_skill_registry_snapshot(relocated_installed, relocated_bundled)

        self.assertEqual(first, second)
        self.assertEqual(first, relocated)
        self.assertEqual(first["registryHash"], second["registryHash"])
        self.assertNotIn(str(self.root), json.dumps(first))
        self.assertEqual(first["summary"]["executable"], 2)
        alpha = [item for item in first["descriptors"] if item["name"] == "alpha"]
        self.assertEqual({item["source"]["kind"] for item in alpha}, {"installed", "bundled"})
        self.assertEqual(len({item["descriptorId"] for item in alpha}), 2)
        self.assertEqual(_descriptor(first, "alpha")["provenance"]["kind"], "bundled-current")
        self.assertEqual(_descriptor(first, "alpha", "bundled")["health"], "reference-only")

    def test_custom_legacy_ambiguous_and_name_conflict_are_not_merged(self):
        bundled_xlsx = _write_skill(self.bundled, "xlsx", body="Bundled body")
        (bundled_xlsx / "dependencies.json").write_text(json.dumps({
            "schemaVersion": 1,
            "skill": "xlsx",
            "capabilities": [],
        }), encoding="utf-8")
        (bundled_xlsx / "code-resources.json").write_text(json.dumps({
            "schemaVersion": 1,
            "skill": "xlsx",
            "resources": [],
        }), encoding="utf-8")
        _write_skill(self.installed, "xlsx", body="Unknown older or custom body")
        _write_skill(
            self.installed,
            "custom-xlsx",
            name="xlsx",
            body="Custom body with the same public name",
        )
        _write_skill(self.installed, "local-only", body="Local body")

        snapshot = build_skill_registry_snapshot(self.installed, self.bundled)
        legacy = _descriptor(snapshot, "xlsx", directory="xlsx")
        conflict = _descriptor(snapshot, "xlsx", directory="custom-xlsx")
        custom = _descriptor(snapshot, "local-only")

        self.assertEqual(legacy["health"], "legacy-ambiguous")
        self.assertFalse(legacy["executableCandidate"])
        self.assertEqual(legacy["sidecars"]["dependencies"]["state"], "missing")
        self.assertEqual(legacy["sidecars"]["resources"]["state"], "missing")
        bundled_reference = _descriptor(snapshot, "xlsx", "bundled")
        self.assertEqual(bundled_reference["sidecars"]["dependencies"]["state"], "ready")
        self.assertEqual(bundled_reference["sidecars"]["resources"]["state"], "ready")
        self.assertEqual(conflict["health"], "conflict")
        self.assertFalse(conflict["executableCandidate"])
        self.assertEqual(conflict["format"]["classification"], "code-legacy")
        self.assertIn(
            "standard_name_directory_mismatch",
            conflict["format"]["reasonCodes"],
        )
        self.assertEqual(custom["provenance"]["kind"], "custom")
        self.assertTrue(custom["executableCandidate"])

    def test_invalid_unreadable_and_empty_skills_have_stable_diagnostics(self):
        invalid = self.installed / "invalid"
        invalid.mkdir()
        (invalid / "SKILL.md").write_text(
            "---\nname: [broken\ndescription: test\n---\nBody\n",
            encoding="utf-8",
        )
        _write_skill(self.installed, "empty", body="")
        _write_skill(self.installed, "blocked")
        real_reader = skill_registry._read_skill_bytes

        def read_or_fail(path):
            if path.parent.name == "blocked":
                raise PermissionError("blocked for test")
            return real_reader(path)

        with mock.patch.object(skill_registry, "_read_skill_bytes", side_effect=read_or_fail):
            snapshot = build_skill_registry_snapshot(self.installed, self.installed)

        self.assertEqual(_descriptor(snapshot, "invalid")["health"], "invalid")
        self.assertEqual(_descriptor(snapshot, "empty")["health"], "invalid")
        self.assertEqual(_descriptor(snapshot, "blocked")["health"], "unreadable")
        self.assertEqual(
            _descriptor(snapshot, "invalid")["format"]["classification"],
            "invalid",
        )
        self.assertTrue(all(
            not item["executableCandidate"]
            for item in snapshot["descriptors"]
        ))

    def test_sidecars_are_summarized_without_mutation(self):
        skill = _write_skill(
            self.installed,
            "report",
            extra_frontmatter="""allowed-tools:
  - read_file
metadata:
  keywords: [report+audit]
future-field: retained-by-author
license: MIT
compatibility: windows""",
        )
        sidecars = {
            "dependencies.json": {"schemaVersion": 1, "skill": "report", "capabilities": []},
            "code-resources.json": {"schemaVersion": 1, "skill": "report", "resources": []},
            "evidence.json": {"schemaVersion": 1, "requirements": []},
        }
        for filename, payload in sidecars.items():
            (skill / filename).write_text(json.dumps(payload), encoding="utf-8")
        before = {
            path.name: path.read_bytes()
            for path in skill.iterdir()
            if path.is_file()
        }

        snapshot = build_skill_registry_snapshot(self.installed, self.installed)
        after = {
            path.name: path.read_bytes()
            for path in skill.iterdir()
            if path.is_file()
        }
        descriptor = _descriptor(snapshot, "report")

        self.assertEqual(before, after)
        self.assertEqual(descriptor["allowedTools"], ["read_file"])
        self.assertEqual(descriptor["routingKeywords"], ["report+audit"])
        self.assertEqual(descriptor["unknownFields"], ["future-field"])
        self.assertEqual(
            {key: value["state"] for key, value in descriptor["sidecars"].items()},
            {"dependencies": "ready", "resources": "ready", "evidence": "ready"},
        )

    def test_invalid_sidecar_and_tombstone_fail_closed(self):
        broken = _write_skill(self.installed, "broken-sidecar")
        (broken / "dependencies.json").write_text("[]", encoding="utf-8")
        _write_skill(self.bundled, "deleted")
        _write_skill(self.bundled, "not-installed")
        state_path = self.installed.parent / "bundled-skills-state.json"
        state_path.write_text(json.dumps({
            "schema": "code-bundled-skills/v1",
            "tombstones": ["deleted"],
        }), encoding="utf-8")

        snapshot = build_skill_registry_snapshot(self.installed, self.bundled)

        self.assertEqual(_descriptor(snapshot, "broken-sidecar")["health"], "invalid")
        self.assertEqual(_descriptor(snapshot, "deleted", "bundled")["health"], "tombstoned")
        self.assertEqual(_descriptor(snapshot, "not-installed", "bundled")["health"], "missing")
        self.assertEqual(
            _descriptor(snapshot, "not-installed", "bundled")["provenance"]["kind"],
            "bundled-not-installed",
        )

    def test_development_and_separate_frozen_roots_share_parser_semantics(self):
        bundled = _write_skill(
            self.bundled,
            "portable",
            extra_frontmatter="""allowed-tools: [read_file, run_command]
metadata:
  keywords: [portable+task]
compatibility: windows""",
        )
        shutil.copytree(bundled, self.installed / "portable")

        development = build_skill_registry_snapshot(self.bundled, self.bundled)
        frozen = build_skill_registry_snapshot(self.installed, self.bundled)
        dev_descriptor = _descriptor(development, "portable")
        frozen_descriptor = _descriptor(frozen, "portable")
        self.assertEqual(dev_descriptor["provenance"]["kind"], "shared-development")
        self.assertEqual(frozen_descriptor["provenance"]["kind"], "bundled-current")
        comparable = (
            "name",
            "description",
            "license",
            "compatibility",
            "metadata",
            "allowedTools",
            "routingKeywords",
            "contentHash",
            "bodyHash",
        )
        self.assertEqual(
            {key: dev_descriptor[key] for key in comparable},
            {key: frozen_descriptor[key] for key in comparable},
        )


class TestSkillShadowResolver(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.skills = Path(self.temporary.name) / "skills"
        self.skills.mkdir()
        _write_skill(self.skills, "xlsx", keywords="公式, 电子表格")
        _write_skill(self.skills, "pdf", keywords="读取+pdf, 提取+pdf")
        _write_skill(self.skills, "office-files", keywords="读取+xlsx, 读取+pdf")
        _write_skill(self.skills, "document-design", keywords="文档+美化, 生成+xlsx")
        _write_skill(self.skills, "alpha", keywords="影子+路由")
        _write_skill(self.skills, "beta", keywords="影子+路由")
        self.snapshot = build_skill_registry_snapshot(self.skills, self.skills)

    def tearDown(self):
        self.temporary.cleanup()

    def test_explicit_skill_is_exact_owner(self):
        result = resolve_skill_shadow(
            self.snapshot,
            "普通说明",
            explicit_skill="xlsx",
        )
        self.assertEqual(result["owner"]["name"], "xlsx")
        self.assertEqual(result["owner"]["reasonCode"], "explicit_skill")
        self.assertEqual(result["modifiers"], [])

    def test_math_formula_explanation_does_not_select_xlsx(self):
        result = resolve_skill_shadow(self.snapshot, "解释一下数学公式的推导")
        self.assertIsNone(result["owner"])
        self.assertEqual(result["modifiers"], [])
        self.assertEqual(result["references"], [])

    def test_workbook_formula_task_has_one_owner_without_aggregate_competition(self):
        result = resolve_skill_shadow(
            self.snapshot,
            "读取这个 xlsx 做公式审计，检查有没有错误",
        )
        self.assertEqual(result["owner"]["name"], "xlsx")
        self.assertEqual(result["owner"]["role"], "owner")
        self.assertEqual([item["name"] for item in result["references"]], ["office-files"])
        self.assertNotIn("office-files", [result["owner"]["name"]])

    def test_document_design_is_modifier_for_xlsx_owner(self):
        result = resolve_skill_shadow(
            self.snapshot,
            "创建一个排版精美且含公式和图表的 Excel 工作簿",
        )
        self.assertEqual(result["owner"]["name"], "xlsx")
        self.assertEqual(
            [(item["name"], item["role"]) for item in result["modifiers"]],
            [("document-design", "modifier")],
        )

    def test_pdf_source_wins_over_output_table_hint(self):
        result = resolve_skill_shadow(
            self.snapshot,
            "读取 report.pdf 里的表格并提取出来保存为 csv",
        )
        self.assertEqual(result["owner"]["name"], "pdf")
        self.assertEqual([item["name"] for item in result["references"]], ["office-files"])

    def test_disabled_and_ambiguous_candidates_do_not_become_owner(self):
        disabled = resolve_skill_shadow(
            self.snapshot,
            "创建 Excel 工作簿",
            disabled_names={"xlsx"},
        )
        ambiguous = resolve_skill_shadow(self.snapshot, "请做影子路由")

        self.assertIsNone(disabled["owner"])
        self.assertIn("skill_disabled", {item["reasonCode"] for item in disabled["excluded"]})
        self.assertIsNone(ambiguous["owner"])
        self.assertEqual(
            {item["name"] for item in ambiguous["references"]},
            {"alpha", "beta"},
        )
        self.assertIn(
            "legacy_match_ambiguous",
            {item["code"] for item in ambiguous["diagnostics"]},
        )

    def test_legacy_ambiguous_descriptor_is_not_executable(self):
        separate_root = Path(self.temporary.name) / "separate"
        installed = separate_root / "profile" / "skills"
        bundled = separate_root / "app" / "skills"
        installed.mkdir(parents=True)
        bundled.mkdir(parents=True)
        _write_skill(bundled, "xlsx", body="Current bundled")
        _write_skill(installed, "xlsx", body="Unknown legacy")
        snapshot = build_skill_registry_snapshot(installed, bundled)

        result = resolve_skill_shadow(snapshot, "创建 Excel 工作簿")

        self.assertIsNone(result["owner"])
        self.assertIn(
            "descriptor_legacy-ambiguous",
            {item["reasonCode"] for item in result["excluded"]},
        )
        self.assertIn(
            "execution_owner_unavailable",
            {item["code"] for item in result["diagnostics"]},
        )

    def test_comparison_counts_extra_and_missing_exactly(self):
        resolution = resolve_skill_shadow(
            self.snapshot,
            "创建一个排版精美的 Excel 工作簿",
        )
        report = compare_observed_and_shadow(["document-design"], resolution)
        self.assertEqual(report["shadowExecutionNames"], ["xlsx", "document-design"])
        self.assertEqual(report["added"], ["xlsx"])
        self.assertEqual(report["removed"], [])
        self.assertTrue(report["changed"])


class TestSkillShadowServerIsolation(unittest.TestCase):
    def test_shadow_flag_is_explicit_opt_in(self):
        self.assertFalse(server_mod._resolve_skill_registry_shadow_enabled({}))
        self.assertFalse(server_mod._resolve_skill_registry_shadow_enabled({
            "CODE_SKILL_REGISTRY_SHADOW": "invalid",
        }))
        self.assertTrue(server_mod._resolve_skill_registry_shadow_enabled({
            "CODE_SKILL_REGISTRY_SHADOW": "true",
        }))

    def test_production_matcher_does_not_call_shadow_pipeline(self):
        skills = [{
            "name": "demo",
            "description": "",
            "keywords": ["demo+task"],
            "tools": [],
        }]
        with (
            mock.patch.object(server_mod, "list_skills", return_value=skills),
            mock.patch.object(
                server_mod,
                "build_skill_registry_snapshot",
                side_effect=AssertionError("shadow pipeline entered"),
            ) as shadow_builder,
        ):
            result = server_mod.match_skills("demo task")
        self.assertEqual([item["name"] for item in result], ["demo"])
        shadow_builder.assert_not_called()

    def test_disabled_endpoint_preserves_existing_not_found_behavior(self):
        handler = object.__new__(server_mod.CodeHandler)
        handler.path = "/api/skills/shadow-resolution"
        handler.send_json = mock.Mock()
        handler.send_error = mock.Mock()
        handler.read_body_json = mock.Mock()
        with (
            mock.patch.object(server_mod, "_SKILL_REGISTRY_SHADOW_ENABLED", False),
            mock.patch.object(server_mod, "get_skill_registry_shadow_audit") as shadow_audit,
        ):
            handler.do_POST()
        handler.read_body_json.assert_not_called()
        shadow_audit.assert_not_called()
        handler.send_json.assert_not_called()
        handler.send_error.assert_called_once_with(404)

    def test_enabled_endpoint_is_read_only_audit(self):
        handler = object.__new__(server_mod.CodeHandler)
        handler.path = "/api/skills/shadow-resolution"
        handler.send_json = mock.Mock()
        handler.send_error = mock.Mock()
        handler.read_body_json = mock.Mock(return_value={
            "message": "demo",
            "explicitSkill": "xlsx",
            "disabled": [],
        })
        payload = {"schema": "code-skill-shadow-audit/v1", "mode": "diagnostic-only"}
        with (
            mock.patch.object(server_mod, "_SKILL_REGISTRY_SHADOW_ENABLED", True),
            mock.patch.object(server_mod, "get_skill_registry_shadow_audit", return_value=payload) as audit,
        ):
            handler.do_POST()
        audit.assert_called_once_with("demo", explicit_skill="xlsx", disabled_names=[])
        handler.send_json.assert_called_once_with(payload)
        handler.send_error.assert_not_called()

    def test_audit_requires_external_frontend_production_observation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skills"
            root.mkdir()
            _write_skill(root, "xlsx", keywords="公式")
            with mock.patch.object(server_mod, "SKILLS_DIR", root):
                before = [item["name"] for item in server_mod.match_skills("解释数学公式推导")]
                with mock.patch.object(
                    server_mod,
                    "match_skills",
                    side_effect=AssertionError("server matcher is not a production baseline"),
                ) as server_matcher:
                    audit = server_mod.get_skill_registry_shadow_audit(
                        "解释数学公式推导",
                        installed_skills_dir=root,
                        bundled_skills_dir=root,
                    )
                server_matcher.assert_not_called()
                after = [item["name"] for item in server_mod.match_skills("解释数学公式推导")]

        self.assertEqual(before, ["xlsx"])
        self.assertEqual(after, before)
        self.assertEqual(audit["productionObservation"], {
            "available": False,
            "reasonCode": "frontend_observation_required",
        })
        self.assertIsNone(audit["shadow"]["owner"])
        self.assertFalse(audit["shadowApplied"])
        self.assertFalse(audit["productionBehaviorChanged"])


class TestBundledSkillShadowEvaluationCorpus(unittest.TestCase):
    """Use the shipped JS matcher/snapshot as the production baseline."""

    CASES = (
        {
            "prompt": "读取这个 xlsx 做公式审计，检查有没有错误",
            "production": ["office-files", "xlsx"],
            "owner": "xlsx",
            "modifiers": [],
            "references": ["office-files"],
            "added": [],
            "removed": ["office-files"],
        },
        {
            "prompt": "解释一下数学公式的推导",
            "production": ["xlsx"],
            "owner": None,
            "modifiers": [],
            "references": [],
            "added": [],
            "removed": ["xlsx"],
        },
        {
            "prompt": "创建一个排版精美且含公式和图表的 Excel 工作簿",
            "production": ["xlsx"],
            "owner": "xlsx",
            "modifiers": ["document-design"],
            "references": [],
            "added": ["document-design"],
            "removed": [],
        },
        {
            "prompt": "读取 report.pdf 里的表格并提取出来保存为 csv",
            "production": ["office-files", "pdf"],
            "owner": "pdf",
            "modifiers": [],
            "references": ["office-files"],
            "added": [],
            "removed": ["office-files"],
        },
        {
            "prompt": "生成一份正式的 Word 项目周报",
            "production": ["document-design"],
            "owner": "docx",
            "modifiers": [],
            "references": [],
            "added": ["docx"],
            "removed": ["document-design"],
        },
        {
            "prompt": "用这个模板生成一份季度汇报 PPT，要图表",
            "production": ["document-design", "pptx"],
            "owner": "pptx",
            "modifiers": ["document-design"],
            "references": [],
            "added": [],
            "removed": [],
        },
        {
            "prompt": "帮我审查 server.py 的改动，找出潜在 bug",
            "production": ["code-review"],
            "owner": "code-review",
            "modifiers": [],
            "references": [],
            "added": [],
            "removed": [],
        },
    )

    def test_bundled_corpus_has_exact_production_and_shadow_deltas(self):
        snapshot = build_skill_registry_snapshot(
            server_mod.SKILLS_DIR,
            server_mod.APP_DIR / "data" / "skills",
        )
        self.assertEqual(
            {item["format"]["classification"] for item in snapshot["descriptors"]},
            {"code-legacy"},
        )
        observations = _frontend_skill_observations(
            _bundled_frontend_skills(),
            [{"prompt": case["prompt"]} for case in self.CASES],
        )
        for case, production in zip(self.CASES, observations):
            with self.subTest(prompt=case["prompt"]):
                production_names = production["activeSkillNames"]
                shadow = resolve_skill_shadow(snapshot, case["prompt"])
                comparison = compare_observed_and_shadow(production_names, shadow)

                self.assertEqual(production_names, case["production"])
                self.assertEqual(production["promptNames"], production_names)
                self.assertEqual(
                    (shadow["owner"] or {}).get("name"),
                    case["owner"],
                )
                self.assertEqual(
                    [item["name"] for item in shadow["modifiers"]],
                    case["modifiers"],
                )
                self.assertEqual(
                    [item["name"] for item in shadow["references"]],
                    case["references"],
                )
                self.assertEqual(comparison["added"], case["added"])
                self.assertEqual(comparison["removed"], case["removed"])

    def test_frontend_baseline_locks_explicit_disabled_cap_and_body_order(self):
        skills = [
            {"name": "writing-plans", "body": "PLAN", "keywords": ["shared+match"], "tools": []},
            {"name": "auto-a", "body": "AAAA", "keywords": ["shared+match"], "tools": []},
            {"name": "auto-b", "body": "B", "keywords": ["shared+match"], "tools": []},
            {"name": "auto-c", "body": "CC", "keywords": ["shared+match"], "tools": []},
            {"name": "auto-d", "body": "DDD", "keywords": ["shared+match"], "tools": []},
            {"name": "auto-disabled", "body": "X", "keywords": ["shared+match"], "tools": []},
        ]
        cases = [
            {"prompt": "please shared match", "disabled": ["auto-disabled"]},
            {"prompt": "writing-plans"},
            {"prompt": "anything", "explicitSkill": "writing-plans"},
            {"prompt": "please shared match", "disabled": ["auto-a", "auto-disabled"]},
        ]

        observations = _frontend_skill_observations(skills, cases)

        self.assertEqual(observations[0]["rankedNames"], ["auto-a", "auto-b", "auto-c"])
        self.assertEqual(observations[0]["activeSkillNames"], ["auto-b", "auto-c", "auto-a"])
        self.assertEqual(observations[0]["activeBodyLengths"], [1, 2, 4])
        self.assertEqual(observations[0]["promptNames"], observations[0]["activeSkillNames"])
        self.assertEqual(observations[1]["activeSkillNames"], [])
        self.assertEqual(observations[2]["activeSkillNames"], ["writing-plans"])
        self.assertEqual(observations[2]["promptNames"], ["writing-plans"])
        self.assertEqual(observations[3]["rankedNames"], ["auto-b", "auto-c", "auto-d"])
        self.assertEqual(observations[3]["activeSkillNames"], ["auto-b", "auto-c", "auto-d"])


if __name__ == "__main__":
    unittest.main()
