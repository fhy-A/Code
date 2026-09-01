import importlib
import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import launcher
import server as server_mod


class TestBundledSkillSync(unittest.TestCase):
    @staticmethod
    def _module():
        return importlib.import_module("bundled_skills")

    @staticmethod
    def _write_skill(root, name, content):
        skill_dir = Path(root) / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        return skill_dir

    def test_launcher_main_uses_shared_bundled_skill_sync(self):
        source = inspect.getsource(launcher._main)
        self.assertIn("sync_bundled_skills_at_startup(base, data_dir)", source)
        self.assertNotIn('for sub in ["memory", "skills"]', source)

    def test_launcher_upgrades_29_to_31_without_touching_existing_or_custom(self):
        legacy_names = [f"legacy-{index:02d}" for index in range(29)]
        bundled_names = [*legacy_names, "ppt-master", "imagegen"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "app"
            bundled = base / "data" / "skills"
            installed = root / "profile" / "skills"
            bundled.mkdir(parents=True)
            installed.mkdir(parents=True)
            for name in bundled_names:
                self._write_skill(bundled, name, f"bundled:{name}")
            for name in legacy_names:
                self._write_skill(installed, name, f"user-preserved:{name}")
            custom = self._write_skill(installed, "my-custom", "custom-bytes")
            with mock.patch.object(
                Path,
                "home",
                side_effect=AssertionError("real HOME must not be read"),
            ):
                result = launcher.sync_bundled_skills_at_startup(base, root / "profile")
            legacy_content = (installed / "legacy-00" / "SKILL.md").read_text()
            custom_content = (custom / "SKILL.md").read_text()
            ppt_content = (installed / "ppt-master" / "SKILL.md").read_text()
            imagegen_content = (installed / "imagegen" / "SKILL.md").read_text()

        self.assertEqual(result["copied"], ["imagegen", "ppt-master"])
        self.assertEqual(legacy_content, "user-preserved:legacy-00")
        self.assertEqual(custom_content, "custom-bytes")
        self.assertEqual(ppt_content, "bundled:ppt-master")
        self.assertEqual(imagegen_content, "bundled:imagegen")

    def test_future_bundled_addition_is_filled_without_overwriting_prior_copy(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundled = root / "bundled"
            installed = root / "data" / "skills"
            bundled.mkdir()
            installed.mkdir(parents=True)
            self._write_skill(bundled, "existing", "bundled-v1")
            first = module.sync_missing_bundled_skills(bundled, installed)
            (installed / "existing" / "SKILL.md").write_text("user-edited", encoding="utf-8")
            self._write_skill(bundled, "future-skill", "bundled-v2")
            second = module.sync_missing_bundled_skills(bundled, installed)
            existing_content = (installed / "existing" / "SKILL.md").read_text()

        self.assertEqual(first["copied"], ["existing"])
        self.assertEqual(second["copied"], ["future-skill"])
        self.assertEqual(existing_content, "user-edited")

    def test_legacy_missing_skill_without_state_is_restored_once(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundled = root / "bundled"
            installed = root / "data" / "skills"
            bundled.mkdir()
            installed.mkdir(parents=True)
            self._write_skill(bundled, "imagegen", "bundled-imagegen")

            first = module.sync_missing_bundled_skills(bundled, installed)
            (installed / "imagegen" / "SKILL.md").write_text("preserve-after-migration", encoding="utf-8")
            second = module.sync_missing_bundled_skills(bundled, installed)
            installed_content = (installed / "imagegen" / "SKILL.md").read_text()

        self.assertEqual(first["copied"], ["imagegen"])
        self.assertEqual(second["copied"], [])
        self.assertEqual(installed_content, "preserve-after-migration")

    def test_bundled_ui_delete_writes_tombstone_and_survives_restart(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app_dir = root / "app"
            bundled = app_dir / "data" / "skills"
            installed = root / "data" / "skills"
            bundled.mkdir(parents=True)
            installed.mkdir(parents=True)
            self._write_skill(bundled, "imagegen", "bundled-imagegen")
            self._write_skill(installed, "imagegen", "installed-imagegen")
            with (
                mock.patch.object(server_mod, "APP_DIR", app_dir),
                mock.patch.object(server_mod, "SKILLS_DIR", installed),
            ):
                result = server_mod.delete_skill("imagegen")

            state = module.load_bundled_skill_state(installed)
            restarted = module.sync_missing_bundled_skills(bundled, installed)
            skill_exists_after_restart = (installed / "imagegen").exists()

        self.assertEqual(result, {"ok": True})
        self.assertEqual(state["tombstones"], ["imagegen"])
        self.assertEqual(restarted["tombstoned"], ["imagegen"])
        self.assertFalse(skill_exists_after_restart)

    def test_corrupt_state_fails_closed_without_copying_or_blocking_startup(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "app"
            bundled = base / "data" / "skills"
            installed = root / "data" / "skills"
            bundled.mkdir(parents=True)
            installed.mkdir(parents=True)
            self._write_skill(bundled, "ppt-master", "bundled-ppt")
            module.bundled_skill_state_path(installed).write_text("{broken", encoding="utf-8")

            direct = module.sync_missing_bundled_skills(bundled, installed)
            launcher_result = launcher.sync_bundled_skills_at_startup(base, root / "data")
            copied_after_corruption = (installed / "ppt-master").exists()

        self.assertFalse(direct["ok"])
        self.assertEqual(direct["status"], "state_invalid")
        self.assertFalse(launcher_result["ok"])
        self.assertFalse(copied_after_corruption)

    def test_copy_failure_cleans_partial_directory_and_continues(self):
        module = self._module()
        original_copytree = module.shutil.copytree
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundled = root / "bundled"
            installed = root / "data" / "skills"
            bundled.mkdir()
            installed.mkdir(parents=True)
            self._write_skill(bundled, "broken", "broken-source")
            self._write_skill(bundled, "healthy", "healthy-source")

            def copytree(source, destination, *args, **kwargs):
                if Path(source).name == "broken":
                    (Path(destination) / "partial.txt").write_text("partial", encoding="utf-8")
                    raise OSError("synthetic copy failure")
                return original_copytree(source, destination, *args, **kwargs)

            with mock.patch.object(module.shutil, "copytree", side_effect=copytree):
                result = module.sync_missing_bundled_skills(bundled, installed)

            leftovers = [path.name for path in installed.iterdir() if path.name.startswith(".")]
            broken_exists = (installed / "broken").exists()
            healthy_exists = (installed / "healthy").is_dir()

        self.assertFalse(result["ok"])
        self.assertEqual(result["copied"], ["healthy"])
        self.assertFalse(broken_exists)
        self.assertTrue(healthy_exists)
        self.assertEqual(leftovers, [])

    def test_state_write_failure_rolls_back_bundled_delete(self):
        module = self._module()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundled = root / "app" / "data" / "skills"
            installed = root / "data" / "skills"
            bundled.mkdir(parents=True)
            installed.mkdir(parents=True)
            self._write_skill(bundled, "ppt-master", "bundled-ppt")
            self._write_skill(installed, "ppt-master", "user-content")
            with mock.patch.object(
                module,
                "_atomic_write_state",
                side_effect=OSError("synthetic state failure"),
            ):
                with self.assertRaises(module.BundledSkillStateError):
                    module.delete_installed_skill("ppt-master", bundled, installed)

            leftovers = [path.name for path in installed.iterdir() if path.name.startswith(".")]
            installed_content = (installed / "ppt-master" / "SKILL.md").read_text()
            state_exists = module.bundled_skill_state_path(installed).exists()

        self.assertEqual(installed_content, "user-content")
        self.assertFalse(state_exists)
        self.assertEqual(leftovers, [])

    def test_delete_cleanup_failure_rolls_back_directory_and_tombstone(self):
        module = self._module()
        original_rmtree = module.shutil.rmtree
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundled = root / "app" / "data" / "skills"
            installed = root / "data" / "skills"
            bundled.mkdir(parents=True)
            installed.mkdir(parents=True)
            self._write_skill(bundled, "imagegen", "bundled-imagegen")
            self._write_skill(installed, "imagegen", "user-content")

            def rmtree(path, *args, **kwargs):
                if Path(path).name.startswith(".imagegen.delete-"):
                    raise OSError("synthetic delete failure")
                return original_rmtree(path, *args, **kwargs)

            with mock.patch.object(module.shutil, "rmtree", side_effect=rmtree):
                with self.assertRaises(module.BundledSkillStateError):
                    module.delete_installed_skill("imagegen", bundled, installed)

            state = module.load_bundled_skill_state(installed)
            leftovers = [path.name for path in installed.iterdir() if path.name.startswith(".")]
            installed_content = (installed / "imagegen" / "SKILL.md").read_text()

        self.assertEqual(installed_content, "user-content")
        self.assertEqual(state["tombstones"], [])
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
