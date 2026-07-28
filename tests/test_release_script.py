import inspect
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import release


class TestReleaseNotesAutomation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.releases_dir = Path(self._tmp.name)
        self._releases_patch = mock.patch.object(
            release,
            "RELEASES_DIR",
            self.releases_dir,
        )
        self._releases_patch.start()

    def tearDown(self):
        self._releases_patch.stop()
        self._tmp.cleanup()

    def test_new_release_uses_chinese_template_and_is_blocked(self):
        release_file = release.generate_release_notes(
            "0.5.31",
            "ABC123",
            1024 * 1024,
        )
        content = release_file.read_text(encoding="utf-8")

        self.assertIn("## 打包信息", content)
        self.assertIn("## 下载与校验", content)
        self.assertIn(release.RELEASE_NOTES_PLACEHOLDER, content)
        self.assertIn("Code-v0.5.31.exe", content)
        self.assertIn("ABC123", content)
        self.assertTrue(
            release.validate_release_notes(release_file, "0.5.31"),
        )
        with self.assertRaises(SystemExit):
            release.require_release_notes_ready(release_file, "0.5.31")

    def test_preserves_legacy_body_and_refreshes_generated_metadata(self):
        release_file = self.releases_dir / "v0.5.31.md"
        release_file.write_text(
            """# Code v0.5.30 Release Notes

Date: 2026-07-27

## 更新重点

- 修复发布说明被覆盖的问题。

## Packaging

- stale metadata

## Download / verification

`Code-v0.5.30.exe` / `OLD_SHA`
""",
            encoding="utf-8",
        )

        generated = release.generate_release_notes(
            "0.5.31",
            "NEW_SHA",
            2 * 1024 * 1024,
        )
        content = generated.read_text(encoding="utf-8")

        self.assertIn("## 更新重点", content)
        self.assertIn("修复发布说明被覆盖的问题", content)
        self.assertIn("Code-v0.5.31.exe", content)
        self.assertIn("NEW_SHA", content)
        self.assertIn("2.00 MiB", content)
        self.assertNotIn("stale metadata", content)
        self.assertNotIn("Code-v0.5.30.exe", content)
        self.assertNotIn("OLD_SHA", content)
        self.assertEqual(
            release.validate_release_notes(generated, "0.5.31"),
            [],
        )

    def test_preserves_prepared_body_only_file(self):
        release_file = self.releases_dir / "v0.5.31.md"
        release_file.write_text(
            """## 主要改动

- 自动发布会保留这段预先写好的中文正文。
""",
            encoding="utf-8",
        )

        generated = release.generate_release_notes(
            "0.5.31",
            "READY_SHA",
            4096,
        )
        content = generated.read_text(encoding="utf-8")

        self.assertIn("自动发布会保留这段预先写好的中文正文", content)
        self.assertEqual(content.count("## 主要改动"), 1)
        self.assertEqual(
            release.validate_release_notes(generated, "0.5.31"),
            [],
        )

        regenerated = release.generate_release_notes(
            "0.5.31",
            "REFRESHED_SHA",
            8192,
        )
        refreshed_content = regenerated.read_text(encoding="utf-8")
        self.assertEqual(refreshed_content.count("## 主要改动"), 1)
        self.assertIn("自动发布会保留这段预先写好的中文正文", refreshed_content)
        self.assertIn("REFRESHED_SHA", refreshed_content)
        self.assertNotIn("READY_SHA", refreshed_content)

    def test_placeholder_variants_are_rejected(self):
        variants = (
            "内容待补充",
            "TBD",
            "[TODO] write notes",
            "DRY_RUN_SHA256",
            "适用于 vX.Y.Z",
        )
        for index, placeholder in enumerate(variants):
            with self.subTest(placeholder=placeholder):
                release_file = self.releases_dir / f"v0.5.{40 + index}.md"
                version = f"0.5.{40 + index}"
                release_file.write_text(
                    release._render_release_notes(
                        version,
                        f"## 主要改动\n\n- {placeholder}",
                        "VALID_SHA",
                        1024,
                        "2026-07-28",
                    ),
                    encoding="utf-8",
                )
                self.assertTrue(
                    release.validate_release_notes(release_file, version),
                )

    def test_release_notes_gate_runs_before_git_commit_and_tag(self):
        source = inspect.getsource(release.main)
        self.assertLess(
            source.index("require_release_notes_ready"),
            source.index("git_commit_and_tag"),
        )
        self.assertIn("if initial_errors and args.yes", source)


if __name__ == "__main__":
    unittest.main()
