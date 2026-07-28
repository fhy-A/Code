import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dev_server


ROOT = Path(__file__).resolve().parents[1]


class _FakeHttpServer:
    daemon_threads = False
    last_instance = None

    def __init__(self, address, handler):
        self.address = address
        self.handler = handler
        self.socket = mock.Mock()
        self.serve_forever_called = False
        self.server_close_called = False
        type(self).last_instance = self

    def serve_forever(self):
        self.serve_forever_called = True

    def server_close(self):
        self.server_close_called = True


class TestDevServer(unittest.TestCase):
    def test_default_environment_is_isolated_from_packaged_release(self):
        env = {}
        port, data_dir = dev_server.configure_dev_environment(env)

        self.assertEqual(port, 3011)
        self.assertEqual(env["CODE_PORT"], "3011")
        self.assertEqual(data_dir, (ROOT / "data").resolve())
        self.assertEqual(env["CODE_DATA_DIR"], str((ROOT / "data").resolve()))
        self.assertEqual(env["CODE_INSTANCE_MODE"], "dev")
        self.assertTrue(env["CODE_RESTART_ENTRY"].endswith("dev_server.py"))

    def test_environment_supports_explicit_dev_overrides(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "CODE_DEV_PORT": "3911",
                "CODE_DEV_DATA_DIR": temp_dir,
            }
            port, data_dir = dev_server.configure_dev_environment(env)

        self.assertEqual(port, 3911)
        self.assertEqual(env["CODE_PORT"], "3911")
        self.assertEqual(data_dir, Path(temp_dir).resolve())

    def test_invalid_dev_port_is_rejected(self):
        for value in ("not-a-port", "80", "70000"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    dev_server.configure_dev_environment({"CODE_DEV_PORT": value})

    def test_runner_uses_dev_port_migrations_and_tray(self):
        fake_module = mock.Mock()
        fake_module.CodeHandler = object()
        fake_module.load_config.return_value = {"projectRoot": str(ROOT)}

        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.dict(
            os.environ,
            {
                "CODE_DEV_PORT": "3011",
                "CODE_DEV_DATA_DIR": temp_dir,
            },
            clear=False,
        ):
            dev_server.run_dev_server(fake_module, _FakeHttpServer)

        instance = _FakeHttpServer.last_instance
        self.assertEqual(instance.address, ("127.0.0.1", 3011))
        self.assertTrue(instance.serve_forever_called)
        self.assertTrue(instance.server_close_called)
        self.assertEqual(instance.socket.settimeout.call_args.args, (2.0,))
        fake_module._migrate_sessions_to_hierarchy.assert_called_once_with()
        fake_module._migrate_codex_project_sessions_support.assert_called_once_with()
        fake_module._migrate_project_root_paths.assert_called_once_with()
        fake_module.start_tray.assert_called_once_with(3011, instance)

    def test_development_batch_targets_only_port_3011_and_dev_entry(self):
        source = (ROOT / "启动Code开发版.bat").read_text(encoding="utf-8")
        self.assertIn('set "CODE_DEV_PORT=3011"', source)
        self.assertIn("dev_server.py", source)
        self.assertIn("/api/version", source)
        self.assertNotIn(":3010", source)
        self.assertIsNone(
            re.search(r"(^|[\\\\/\\s])server[.]py([\\s\"]|$)", source, re.I),
        )

    def test_packaged_launcher_server_pattern_does_not_match_dev_entry(self):
        managed_server = re.compile(
            r'(^|[\\/\s])server[.]py([\s"]|$)',
            re.IGNORECASE,
        )
        command = rf'pythonw.exe "{ROOT / "dev_server.py"}"'
        self.assertIsNone(managed_server.search(command))


if __name__ == "__main__":
    unittest.main()
