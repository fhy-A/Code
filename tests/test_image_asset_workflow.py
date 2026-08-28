import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import image_runtime
import server as server_mod


def _png(width=5, height=3, color=(32, 96, 160)):
    output = io.BytesIO()
    Image.new("RGB", (width, height), color).save(output, format="PNG")
    return output.getvalue()


class _FakeImageClient:
    def __init__(self):
        self.calls = []
        self.image = image_runtime.validate_image_bytes(_png())

    def generate(
        self, route, normalized_request, operation_id, *,
        reference_image=None, cancel_event=None,
    ):
        self.calls.append({
            "operationId": operation_id,
            "request": dict(normalized_request),
            "reference": reference_image,
        })
        return [self.image]


class TestImageAssetWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="code_image_asset_workflow_")
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.project = self.root / "project"
        self.sessions = self.data / "sessions"
        self.attachments = self.data / "attachments"
        self.backups = self.data / "file-backups"
        self.data.mkdir()
        self.project.mkdir()
        self.sessions.mkdir()
        self.attachments.mkdir()
        self.config = self.data / "config.json"
        self.config.write_text(
            json.dumps({"projectRoot": str(self.project)}), encoding="utf-8",
        )

        self.registry = image_runtime.ImageRouteRegistry(
            self.data / "isolated-image-route-registry.json",
        )
        self.registry.refresh([{
            "connectionId": "image-workflow",
            "name": "Image workflow",
            "baseUrl": "https://images.invalid/v1",
            "key": "IMAGE_WORKFLOW_SECRET_SENTINEL",
            "models": [{"id": "image-workflow-v1"}],
        }])
        snapshot = self.registry.snapshot()
        self.route = self.registry.resolve(
            snapshot["routes"][0]["routeRef"],
            snapshot["catalogRevision"],
            "image-workflow-v1",
        )
        self.assets = image_runtime.GeneratedAssetRepository(
            self.data / "isolated-generated-assets",
        )
        self.client = _FakeImageClient()
        self.patchers = [
            mock.patch.object(server_mod, "DATA_DIR", self.data),
            mock.patch.object(server_mod, "SESSIONS_DIR", self.sessions),
            mock.patch.object(server_mod, "ATTACHMENTS_DIR", self.attachments),
            mock.patch.object(server_mod, "FILE_BACKUP_DIR", self.backups),
            mock.patch.object(server_mod, "CONFIG_PATH", self.config),
            mock.patch.object(server_mod, "_MODEL_ROUTE_REGISTRY_ENABLED", False),
            mock.patch.object(server_mod, "_image_route_registry", self.registry),
            mock.patch.object(server_mod, "_generated_asset_repository", self.assets),
            mock.patch.object(server_mod, "_image_upstream_client", self.client),
        ]
        for patcher in self.patchers:
            patcher.start()
        with server_mod._agent_run_lock:
            server_mod._agent_runs.clear()

    def tearDown(self):
        with server_mod._agent_run_lock:
            server_mod._agent_runs.clear()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp.cleanup()

    def _session(self, session_id):
        server_mod.write_json(server_mod.session_path(session_id), {
            "id": session_id,
            "title": "Image asset workflow",
            "createdAt": server_mod.now_iso(),
            "updatedAt": server_mod.now_iso(),
            "messageCount": 0,
            "cwd": str(self.project),
        })
        server_mod.write_jsonl(server_mod.messages_path(session_id), [])
        return session_id

    def _run(self, session_id, content, *, permission="bypass"):
        self._session(session_id)
        return server_mod._create_agent_run(
            session_id,
            {"model": "chat-model", "messages": [{"role": "user", "content": content}]},
            "https://chat.invalid/v1",
            [],
            allowed_tools=["generate_image", "manage_generated_image"],
            permission_profile=permission,
            start_worker=False,
            cwd=str(self.project),
            workspace_roots=[str(self.project)],
            image_route=self.route,
        )

    @staticmethod
    def _queue(run, name, arguments, call_id="asset-workflow-call"):
        normalized = server_mod._normalize_agent_tool_calls(run, [{
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }], 1)
        run["messages"].append({
            "role": "assistant",
            "content": "",
            "tool_calls": server_mod._agent_assistant_tool_calls(normalized),
        })
        run["pending_tool_calls"] = normalized
        run["status"] = "tools"
        return normalized[0]

    def _asset(self, session_id, *, operation_id="seed-operation"):
        result = self.assets.save_operation(
            operation_id,
            session_id,
            "seed-run",
            "seed-call",
            [image_runtime.validate_image_bytes(_png())],
            created_at=server_mod.now_iso(),
        )
        return result["assets"][0]

    def test_count_intent_reads_only_current_string_or_multimodal_user_text(self):
        cases = [
            ([{"role": "user", "content": "请生成 4 张图片"}], 4),
            ([{"role": "user", "content": [
                {"type": "text", "text": "把参考图做成两个版本"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
            ]}], 2),
            ([{"role": "user", "content": "生成一张 4K 图片，尺寸 1024x1024"}], 1),
            ([
                {"role": "user", "content": "以前做三张"},
                {"role": "assistant", "content": "好的"},
                {"role": "user", "content": "这次只编辑当前图片"},
            ], 1),
            ([{"role": "user", "content": "给我多个版本"}], None),
        ]
        for messages, expected in cases:
            with self.subTest(messages=messages):
                self.assertEqual(
                    server_mod._agent_explicit_image_count(messages), expected,
                )

    def test_count_greater_than_one_requires_current_explicit_intent_before_authorization(self):
        run = self._run(
            "count-not-explicit", "请把这张图编辑成 4K", permission="accept",
        )
        call = self._queue(run, "generate_image", {
            "prompt": "edit the supplied composition",
            "count": 2,
        })

        self.assertTrue(server_mod._execute_agent_pending_tools(run))

        result = run["tool_executions"][call["id"]]["result"]
        self.assertEqual(result["errorCode"], "image_count_not_explicit")
        self.assertIsNone(run.get("pending_authorization"))
        self.assertEqual(self.client.calls, [])

    def test_explicit_multimodal_two_versions_allows_one_batch(self):
        run = self._run("count-explicit", [
            {"type": "text", "text": "请基于这张图明确生成 2 个版本"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ])
        call = self._queue(run, "generate_image", {
            "prompt": "two controlled variants",
            "count": 2,
        })

        self.assertTrue(server_mod._execute_agent_pending_tools(run))

        result = run["tool_executions"][call["id"]]["result"]
        self.assertTrue(result["ok"])
        self.assertEqual(result["requested"], 2)
        self.assertEqual(len(self.client.calls), 2)

    def test_complex_run_generates_then_edits_once_per_stage_across_restart(self):
        run = self._run(
            "staged-image-run",
            "先生成一张主图，再基于生成结果编辑成蓝色版本",
            permission="accept",
        )
        first_arguments = {"prompt": "create the initial composition", "count": 1}
        first = self._queue(
            run, "generate_image", first_arguments, call_id="stage-generate",
        )
        self.assertFalse(server_mod._execute_agent_pending_tools(run))
        first_auth = server_mod._agent_public_pending_authorization(run)
        server_mod._submit_agent_authorization(
            run, first_auth["authorizationId"], "approved",
        )
        run["status"] = "tools"
        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        first_result = run["tool_executions"][first["id"]]["result"]
        first_asset = first_result["assets"][0]
        self.assertEqual(len(self.client.calls), 1)

        restored = server_mod._agent_run_from_record(server_mod._agent_run_record(run))
        self.assertEqual(len(self.client.calls), 1)
        restored["status"] = "tools"
        second = self._queue(restored, "generate_image", {
            "prompt": "edit the initial composition into a blue version",
            "reference": {"type": "generated_asset", "id": first_asset["assetId"]},
            "count": 1,
        }, call_id="stage-edit")
        self.assertFalse(server_mod._execute_agent_pending_tools(restored))
        second_auth = server_mod._agent_public_pending_authorization(restored)
        self.assertNotEqual(first_auth["authorizationId"], second_auth["authorizationId"])
        server_mod._submit_agent_authorization(
            restored, second_auth["authorizationId"], "approved",
        )
        restored["status"] = "tools"
        self.assertTrue(server_mod._execute_agent_pending_tools(restored))

        second_result = restored["tool_executions"][second["id"]]["result"]
        self.assertEqual(len(self.client.calls), 2)
        self.assertEqual(self.client.calls[1]["reference"].sha256, first_asset["sha256"])
        self.assertNotEqual(
            first_asset["assetId"], second_result["assets"][0]["assetId"],
        )
        self.assertEqual(
            len([event for event in restored["events"] if event["type"] == "authorization_required"]),
            2,
        )

        duplicate = self._queue(
            restored, "generate_image", first_arguments, call_id="stage-generate-duplicate",
        )
        self.assertTrue(server_mod._execute_agent_pending_tools(restored))
        duplicate_result = restored["tool_executions"][duplicate["id"]]["result"]
        self.assertEqual(duplicate_result["errorCode"], "image_stage_already_completed")
        self.assertTrue(duplicate_result["notReplayed"])
        self.assertEqual(len(self.client.calls), 2)
        self.assertIsNone(restored.get("pending_authorization"))

        server_mod._agent_run_from_record(server_mod._agent_run_record(restored))
        self.assertEqual(len(self.client.calls), 2)

    def test_same_session_later_agent_run_reuses_generated_asset_without_export(self):
        first = self._run("same-session-reference", "先生成一张图片")
        call = self._queue(first, "generate_image", {
            "prompt": "create a reusable source", "count": 1,
        }, call_id="same-session-generate")
        self.assertTrue(server_mod._execute_agent_pending_tools(first))
        source = first["tool_executions"][call["id"]]["result"]["assets"][0]

        second = server_mod._create_agent_run(
            first["session_id"],
            {"model": "chat-model", "messages": [{
                "role": "user", "content": "编辑刚才生成的那一张图片",
            }]},
            "https://chat.invalid/v1",
            [],
            allowed_tools=["generate_image", "manage_generated_image"],
            permission_profile="bypass",
            start_worker=False,
            cwd=str(self.project),
            workspace_roots=[str(self.project)],
            image_route=self.route,
        )
        edit = self._queue(second, "generate_image", {
            "prompt": "edit the reusable source once",
            "reference": {"type": "generated_asset", "id": source["assetId"]},
            "count": 1,
        }, call_id="same-session-edit")
        self.assertTrue(server_mod._execute_agent_pending_tools(second))

        self.assertTrue(second["tool_executions"][edit["id"]]["result"]["ok"])
        self.assertEqual(self.client.calls[-1]["reference"].sha256, source["sha256"])
        self.assertFalse((self.project / "output" / "generated-images").exists())

    def test_export_requires_one_authorization_and_replays_without_duplicate_write(self):
        run = self._run("export-asset", "请把生成图片转存为 hero.png", permission="accept")
        asset = self._asset(run["session_id"])
        call = self._queue(run, "manage_generated_image", {
            "operation": "export",
            "assetId": asset["assetId"],
            "name": "hero.png",
        })

        self.assertFalse(server_mod._execute_agent_pending_tools(run))
        pending = server_mod._agent_public_pending_authorization(run)
        self.assertEqual(pending["action"], "manage_generated_image")
        self.assertEqual(pending["path"], "output/generated-images/hero.png")
        self.assertFalse((self.project / pending["path"]).exists())

        server_mod._submit_agent_authorization(
            run, pending["authorizationId"], "approved",
        )
        run["status"] = "tools"
        self.assertTrue(server_mod._execute_agent_pending_tools(run))

        result = run["tool_executions"][call["id"]]["result"]
        target = self.project / result["path"]
        self.assertEqual(target.read_bytes(), _png())
        self.assertEqual(result["absolutePath"], str(target.resolve()))
        self.assertEqual(result["sha256"], asset["sha256"])
        self.assertNotIn("generated-assets", json.dumps(result))

        with self.assertRaises(ValueError):
            server_mod._submit_agent_authorization(
                run, pending["authorizationId"], "approved",
            )

        first_mtime = target.stat().st_mtime_ns
        replay = server_mod.execute_manage_generated_image_tool({
            "operation": "export",
            "assetId": asset["assetId"],
            "name": "hero.png",
            "_operationId": run["tool_executions"][call["id"]]["operationId"],
            "_sessionId": run["session_id"],
            "_agentRunId": run["id"],
            "_toolCallId": call["id"],
            "_projectRoot": str(self.project),
        })
        self.assertTrue(replay["replayed"])
        self.assertEqual(target.stat().st_mtime_ns, first_mtime)

    def test_export_default_name_is_deterministic_and_same_hash_is_idempotent(self):
        run = self._run("default-export", "请转存生成图片")
        asset = self._asset(run["session_id"])
        base = {
            "operation": "export", "assetId": asset["assetId"],
            "_sessionId": run["session_id"], "_agentRunId": run["id"],
            "_projectRoot": str(self.project),
        }

        first = server_mod.execute_manage_generated_image_tool({
            **base, "_operationId": "default-export-one", "_toolCallId": "one",
        })
        second = server_mod.execute_manage_generated_image_tool({
            **base, "_operationId": "default-export-two", "_toolCallId": "two",
        })

        self.assertEqual(first["path"], second["path"])
        self.assertEqual(
            first["path"], f"output/generated-images/image-{asset['sha256'][:16]}.png",
        )
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])

    def test_export_conflict_cross_session_and_corrupt_source_fail_closed(self):
        owner = self._run("asset-owner", "生成一张图")
        asset = self._asset(owner["session_id"])
        target_dir = self.project / "output" / "generated-images"
        target_dir.mkdir(parents=True)
        (target_dir / "conflict.png").write_bytes(_png(color=(200, 10, 10)))

        for session_id, name, expected in (
            (owner["session_id"], "conflict.png", "image_asset_target_conflict"),
            ("other-session", "owned.png", "generated_asset_forbidden"),
        ):
            if session_id != owner["session_id"]:
                run = self._run(session_id, "转存图片")
            else:
                run = owner
            call = self._queue(run, "manage_generated_image", {
                "operation": "export", "assetId": asset["assetId"], "name": name,
            }, call_id=f"export-{session_id}")
            self.assertTrue(server_mod._execute_agent_pending_tools(run))
            self.assertEqual(
                run["tool_executions"][call["id"]]["result"]["errorCode"], expected,
            )

        data, meta = self.assets.read(owner["session_id"], asset["assetId"])
        asset_dir = self.assets._asset_dir(asset["assetId"])
        (asset_dir / meta["fileName"]).write_bytes(data + b"corrupt")
        corrupt = self._run(owner["session_id"], "转存损坏图片")
        call = self._queue(corrupt, "manage_generated_image", {
            "operation": "export", "assetId": asset["assetId"], "name": "corrupt.png",
        }, call_id="export-corrupt")
        self.assertTrue(server_mod._execute_agent_pending_tools(corrupt))
        self.assertEqual(
            corrupt["tool_executions"][call["id"]]["result"]["errorCode"],
            "generated_asset_corrupt",
        )
        self.assertFalse((target_dir / "corrupt.png").exists())

    def test_rename_is_atomic_conflict_safe_and_restart_idempotent(self):
        run = self._run("rename-asset", "把导出的图片改名")
        asset = self._asset(run["session_id"])
        exported = server_mod.execute_manage_generated_image_tool({
            "operation": "export", "assetId": asset["assetId"], "name": "before.png",
            "_operationId": "export-before", "_sessionId": run["session_id"],
            "_agentRunId": run["id"], "_toolCallId": "export-before",
            "_projectRoot": str(self.project),
        })
        payload = {
            "operation": "rename", "path": exported["path"], "name": "after.png",
            "_operationId": "rename-once", "_sessionId": run["session_id"],
            "_agentRunId": run["id"], "_toolCallId": "rename-call",
            "_projectRoot": str(self.project),
        }

        first = server_mod.execute_manage_generated_image_tool(payload)
        replay = server_mod.execute_manage_generated_image_tool(payload)

        self.assertFalse((self.project / exported["path"]).exists())
        self.assertTrue((self.project / first["path"]).is_file())
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["sha256"], first["sha256"])

    def test_applying_file_mutation_restart_reuses_export_receipt_and_target(self):
        run = self._run("export-restart", "请转存生成图片")
        asset = self._asset(run["session_id"])
        call = self._queue(run, "manage_generated_image", {
            "operation": "export", "assetId": asset["assetId"], "name": "restart.png",
        }, call_id="export-restart-call")
        operation_id = "restart-operation"
        run["tool_executions"][call["id"]] = {
            "name": "manage_generated_image",
            "arguments": call["function"]["arguments"],
            "fingerprint": call["fingerprint"],
            "status": "applying_file_mutation",
            "operationId": operation_id,
            "result": None,
            "error": "",
        }
        first = server_mod.execute_manage_generated_image_tool({
            **call["arguments"],
            "_operationId": operation_id,
            "_sessionId": run["session_id"],
            "_agentRunId": run["id"],
            "_toolCallId": call["id"],
            "_projectRoot": str(self.project),
        })
        target = self.project / first["path"]
        before = target.stat().st_mtime_ns

        restored = server_mod._agent_run_from_record(server_mod._agent_run_record(run))
        restored["status"] = "tools"
        self.assertTrue(server_mod._execute_agent_pending_tools(restored))

        result = restored["tool_executions"][call["id"]]["result"]
        self.assertTrue(result["replayed"])
        self.assertEqual(target.stat().st_mtime_ns, before)

    def test_path_traversal_absolute_names_and_symlinked_output_fail_closed(self):
        run = self._run("asset-path-guard", "请转存图片")
        asset = self._asset(run["session_id"])
        for index, arguments in enumerate((
            {"operation": "export", "assetId": asset["assetId"], "name": "../escape.png"},
            {"operation": "export", "assetId": asset["assetId"], "name": "C:\\escape.png"},
            {"operation": "rename", "path": "C:\\outside.png", "name": "safe.png"},
            {"operation": "rename", "path": "output/generated-images/../escape.png", "name": "safe.png"},
        )):
            call = self._queue(
                run, "manage_generated_image", arguments,
                call_id=f"path-guard-{index}",
            )
            self.assertTrue(server_mod._execute_agent_pending_tools(run))
            result = run["tool_executions"][call["id"]]["result"]
            self.assertIn(result["errorCode"], {
                "image_asset_name_invalid", "image_asset_path_invalid",
            })
        self.assertFalse((self.project.parent / "escape.png").exists())

        path_type = type(self.project)
        original_is_symlink = path_type.is_symlink

        def fake_is_symlink(path):
            return path.name == "generated-images" or original_is_symlink(path)

        with mock.patch.object(path_type, "is_symlink", fake_is_symlink):
            with self.assertRaises(image_runtime.ImageRuntimeError) as raised:
                server_mod.execute_manage_generated_image_tool({
                    "operation": "export", "assetId": asset["assetId"], "name": "safe.png",
                    "_operationId": "symlink-guard", "_sessionId": run["session_id"],
                    "_agentRunId": run["id"], "_toolCallId": "symlink-guard",
                    "_projectRoot": str(self.project),
                })
        self.assertEqual(raised.exception.code, "image_asset_symlink_forbidden")

    def test_rename_unlink_failure_rolls_back_new_target(self):
        run = self._run("rename-rollback", "重命名导出图片")
        asset = self._asset(run["session_id"])
        exported = server_mod.execute_manage_generated_image_tool({
            "operation": "export", "assetId": asset["assetId"], "name": "source.png",
            "_operationId": "rollback-export", "_sessionId": run["session_id"],
            "_agentRunId": run["id"], "_toolCallId": "rollback-export",
            "_projectRoot": str(self.project),
        })
        source = self.project / exported["path"]
        target = source.with_name("target.png")
        path_type = type(source)
        original_unlink = path_type.unlink

        def fail_source_unlink(path, *args, **kwargs):
            if path == source:
                raise PermissionError("locked")
            return original_unlink(path, *args, **kwargs)

        with mock.patch.object(path_type, "unlink", fail_source_unlink):
            with self.assertRaises(image_runtime.ImageRuntimeError) as raised:
                server_mod.execute_manage_generated_image_tool({
                    "operation": "rename", "path": exported["path"], "name": "target.png",
                    "_operationId": "rollback-rename", "_sessionId": run["session_id"],
                    "_agentRunId": run["id"], "_toolCallId": "rollback-rename",
                    "_projectRoot": str(self.project),
                })
        self.assertEqual(raised.exception.code, "image_asset_write_failed")
        self.assertTrue(source.is_file())
        self.assertFalse(target.exists())

    def test_workspace_image_reference_is_strict_and_cross_session(self):
        first = self._run("workspace-source", "生成并转存图片")
        asset = self._asset(first["session_id"])
        exported = server_mod.execute_manage_generated_image_tool({
            "operation": "export", "assetId": asset["assetId"], "name": "reference.png",
            "_operationId": "export-reference", "_sessionId": first["session_id"],
            "_agentRunId": first["id"], "_toolCallId": "export-reference",
            "_projectRoot": str(self.project),
        })
        self.assets.delete_session_assets(first["session_id"])
        second = self._run("workspace-edit", "请编辑 output/generated-images/reference.png")
        call = self._queue(second, "generate_image", {
            "prompt": "edit the controlled workspace image",
            "reference": {"type": "workspace_image", "id": exported["path"]},
            "count": 1,
        }, call_id="workspace-reference")

        self.assertTrue(server_mod._execute_agent_pending_tools(second))

        self.assertTrue(second["tool_executions"][call["id"]]["result"]["ok"])
        self.assertEqual(self.client.calls[-1]["reference"].data, _png())

        outside = self.project / "outside.png"
        outside.write_bytes(_png())
        blocked = self._run("workspace-blocked", "请编辑 outside.png")
        call = self._queue(blocked, "generate_image", {
            "prompt": "must be rejected",
            "reference": {"type": "workspace_image", "id": "outside.png"},
            "count": 1,
        }, call_id="workspace-outside")
        self.assertTrue(server_mod._execute_agent_pending_tools(blocked))
        self.assertEqual(
            blocked["tool_executions"][call["id"]]["result"]["errorCode"],
            "image_workspace_reference_invalid",
        )

    def test_session_cleanup_does_not_remove_exported_workspace_copy(self):
        run = self._run("export-survives-delete", "转存图片")
        asset = self._asset(run["session_id"])
        exported = server_mod.execute_manage_generated_image_tool({
            "operation": "export", "assetId": asset["assetId"], "name": "survives.png",
            "_operationId": "export-survives", "_sessionId": run["session_id"],
            "_agentRunId": run["id"], "_toolCallId": "export-survives",
            "_projectRoot": str(self.project),
        })

        self.assets.delete_session_assets(run["session_id"])

        self.assertTrue((self.project / exported["path"]).is_file())
        with self.assertRaises(image_runtime.ImageRuntimeError):
            self.assets.read(run["session_id"], asset["assetId"])


if __name__ == "__main__":
    unittest.main()
