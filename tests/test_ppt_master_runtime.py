import hashlib
import json
import os
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import ppt_master_runtime as runtime
import server as server_mod


SAMPLE_MARKDOWN = """# 离线运行试点
结构化输入生成原生可编辑对象

## 安全边界保持明确
- 仅接受 UTF-8 Markdown 或 TXT
- 输出固定在当前 AgentRun
- 不访问网络、Key 或用户目录

## 原生对象保持可编辑
| 对象 | 验收状态 |
|---|---|
| 文本与形状 | 通过 |
| 表格与图表 | 通过 |

## 试点阶段稳步闭合
```chart
阶段,完成率
供应链,100
运行时,100
验证,100
```
"""


class TestPptMasterRuntime(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "project"
        self.project.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def payload(self, *, run_id="ppt-run-1", operation="a" * 64, markdown=SAMPLE_MARKDOWN):
        return {
            "markdown": markdown,
            "_operationId": operation,
            "_projectRoot": str(self.project),
            "_agentRunId": run_id,
            "_toolCallId": "ppt-call-1",
            "_cancelEvent": threading.Event(),
        }

    def test_actual_worker_generates_editable_native_objects_and_replays_receipt(self):
        first = runtime.execute_ppt_master_tool(self.payload())
        self.assertTrue(first["ok"])
        self.assertFalse(first["replayed"])
        self.assertEqual(first["slideCount"], 4)
        self.assertGreater(first["shapeCount"], 10)
        self.assertEqual(first["tableCount"], 1)
        self.assertEqual(first["chartCount"], 1)
        self.assertTrue(first["editable"])
        self.assertTrue(first["offline"])
        deck = self.project / first["path"]
        self.assertTrue(deck.is_file())
        before = deck.read_bytes()
        with zipfile.ZipFile(deck) as archive:
            chart_xml = b"".join(
                archive.read(name)
                for name in archive.namelist()
                if name.startswith("ppt/charts/chart") and name.endswith(".xml")
            )
        self.assertNotRegex(chart_xml, rb'<c:(?:axId|crossAx) val="-')

        replay = runtime.execute_ppt_master_tool(self.payload())
        self.assertTrue(replay["ok"])
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["sha256"], first["sha256"])
        self.assertEqual(deck.read_bytes(), before)
        self.assertFalse((self.project / "output/ppt-master/.staging/ppt-run-1").exists())
        self.assertFalse((self.project / "%SystemDrive%").exists())

    def test_inline_and_project_file_inputs_fail_closed(self):
        normalized = runtime._normalize_markdown({"markdown": "# 标题"}, self.project)
        self.assertEqual(normalized[:2], ("# 标题", "inline"))
        source = self.project / "brief.md"
        source.write_text("# 项目简报", encoding="utf-8")
        normalized = runtime._normalize_markdown({"sourcePath": "brief.md"}, self.project)
        self.assertEqual(normalized[:2], ("# 项目简报", "project_file"))

        invalid = (
            {},
            {"markdown": "# A", "sourcePath": "brief.md"},
            {"markdown": "see https://example.com"},
            {"markdown": '<img src="https://example.com/a.png">'},
            {"sourcePath": str(source)},
            {"sourcePath": "../brief.md"},
            {"sourcePath": "brief.pdf"},
        )
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(runtime.PptMasterRuntimeError):
                runtime._normalize_markdown(payload, self.project)

        source.write_bytes(b"x" * (runtime.MAX_INPUT_BYTES + 1))
        with self.assertRaises(runtime.PptMasterRuntimeError) as raised:
            runtime._normalize_markdown({"sourcePath": "brief.md"}, self.project)
        self.assertEqual(raised.exception.code, "ppt_master_source_too_large")

    def test_reparse_source_is_blocked_without_reading_it(self):
        source = self.project / "brief.txt"
        source.write_text("protected", encoding="utf-8")
        original = runtime._is_reparse
        with mock.patch.object(
            runtime,
            "_is_reparse",
            side_effect=lambda path: path == source or original(path),
        ):
            with self.assertRaises(runtime.PptMasterRuntimeError) as raised:
                runtime._normalize_markdown({"sourcePath": "brief.txt"}, self.project)
        self.assertEqual(raised.exception.code, "ppt_master_reparse_blocked")

    def test_existing_public_output_is_never_overwritten(self):
        occupied = self.project / "output/ppt-master/ppt-run-occupied"
        occupied.mkdir(parents=True)
        sentinel = occupied / "sentinel.bin"
        sentinel.write_bytes(b"keep")
        with self.assertRaises(runtime.PptMasterRuntimeError) as raised:
            runtime.execute_ppt_master_tool(self.payload(run_id="ppt-run-occupied"))
        self.assertEqual(raised.exception.code, "ppt_master_output_exists")
        self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_restart_with_prepared_only_is_not_replayed_or_regenerated(self):
        run_id, operation = "ppt-run-unknown", "b" * 64
        staging = self.project / f"output/ppt-master/.staging/{run_id}"
        staging.mkdir(parents=True)
        input_sha = hashlib.sha256(SAMPLE_MARKDOWN.encode("utf-8")).hexdigest()
        (staging / "prepared.json").write_text(
            json.dumps({"operationId": operation, "inputSha256": input_sha}),
            encoding="utf-8",
        )
        with mock.patch.object(runtime, "_validate_runtime_contract", return_value={
            "receipt": {"packages": []},
            "vendor": {"manifestDigest": "x"},
        }), mock.patch.object(runtime.subprocess, "Popen") as popen:
            with self.assertRaises(runtime.PptMasterRuntimeError) as raised:
                runtime.execute_ppt_master_tool(self.payload(run_id=run_id, operation=operation))
        self.assertEqual(raised.exception.code, "ppt_master_previous_outcome_unknown")
        self.assertTrue(raised.exception.outcome_unknown)
        popen.assert_not_called()
        self.assertFalse(staging.exists())

    def test_cancel_and_timeout_kill_worker_and_remove_staging(self):
        fake = Path(self.temporary.name) / "slow_worker.py"
        fake.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
        contract = {
            "receipt": {"packages": []},
            "vendor": {"manifestDigest": "x"},
        }
        for mode in ("cancel", "timeout"):
            run_id = f"ppt-{mode}"
            payload = self.payload(run_id=run_id, operation=("c" if mode == "cancel" else "d") * 64)
            if mode == "cancel":
                payload["_cancelEvent"].set()
            with self.subTest(mode=mode), mock.patch.object(
                runtime, "_validate_runtime_contract", return_value=contract
            ), mock.patch.object(runtime, "MANAGED_PYTHON", Path(sys.executable)), mock.patch.object(
                runtime, "WORKER_PATH", fake
            ), mock.patch.object(runtime, "TIMEOUT_SECONDS", 0.05):
                with self.assertRaises(runtime.PptMasterRuntimeError) as raised:
                    runtime.execute_ppt_master_tool(payload)
            self.assertEqual(raised.exception.cancelled, mode == "cancel")
            self.assertEqual(raised.exception.timed_out, mode == "timeout")
            self.assertFalse((self.project / f"output/ppt-master/{run_id}").exists())
            self.assertFalse((self.project / f"output/ppt-master/.staging/{run_id}").exists())

    def test_tool_schema_exposes_no_command_module_or_output_path(self):
        definition = server_mod._SERVER_TOOL_DEFINITIONS["create_ppt_master_deck"]
        properties = definition["function"]["parameters"]["properties"]
        self.assertEqual(set(properties), {"markdown", "sourcePath"})
        errors = server_mod._registered_tool_argument_errors(
            "create_ppt_master_deck",
            {"markdown": "# A", "outputPath": "outside.pptx", "module": "anything"},
        )
        self.assertTrue(errors)
        payload = {"tools": [definition]}
        for profile in ("read", "plan"):
            self.assertEqual(
                server_mod._agent_selected_tools(payload, ["create_ppt_master_deck"], profile),
                [],
            )
        for profile in ("accept", "bypass"):
            selected = server_mod._agent_selected_tools(
                payload, ["create_ppt_master_deck"], profile,
            )
            self.assertEqual(selected[0]["function"]["name"], "create_ppt_master_deck")


if __name__ == "__main__":
    unittest.main()
