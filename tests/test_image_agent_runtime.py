"""AgentRun and route integration coverage for the independent image runtime."""

import base64
import io
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import requests
from PIL import Image

import image_runtime
import server as server_mod


def _png(width=3, height=2, color=(25, 80, 140)):
    output = io.BytesIO()
    Image.new("RGB", (width, height), color).save(output, format="PNG")
    return output.getvalue()


class _FakeImageClient:
    def __init__(self, image):
        self.image = image_runtime.validate_image_bytes(image)
        self.calls = []

    def generate(self, route, normalized_request, operation_id, *, reference_image=None, cancel_event=None):
        self.calls.append({
            "routeRef": route.route_ref,
            "modelId": route.model_id,
            "baseUrl": route.base_url,
            "key": route.key,
            "operationId": operation_id,
            "request": dict(normalized_request),
            "reference": reference_image,
        })
        return [self.image for _ in range(normalized_request["count"])]


class TestImageAgentRuntime(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="code_image_agent_")
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.project = self.root / "project"
        self.sessions = self.data / "sessions"
        self.attachments = self.data / "attachments"
        self.data.mkdir()
        self.project.mkdir()
        self.sessions.mkdir()
        self.attachments.mkdir()
        self.config = self.data / "config.json"
        self.config.write_text(json.dumps({"projectRoot": str(self.project)}), encoding="utf-8")

        self.registry_path = self.data / "image-route-registry.json"
        self.registry = image_runtime.ImageRouteRegistry(self.registry_path)
        self.registry.refresh([{
            "connectionId": "image-qa",
            "name": "Image QA",
            "baseUrl": "https://images.example/v1",
            "key": "IMAGE_SECRET_SENTINEL",
            "models": [{"id": "image-model-v1", "supportsEdit": True}],
        }])
        snapshot = self.registry.snapshot()
        self.route = self.registry.resolve(
            snapshot["routes"][0]["routeRef"],
            snapshot["catalogRevision"],
            "image-model-v1",
        )
        self.assets = image_runtime.GeneratedAssetRepository(self.data / "generated-assets")
        self.client = _FakeImageClient(_png())
        self.patchers = [
            mock.patch.object(server_mod, "DATA_DIR", self.data),
            mock.patch.object(server_mod, "SESSIONS_DIR", self.sessions),
            mock.patch.object(server_mod, "ATTACHMENTS_DIR", self.attachments),
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

    def _session(self, session_id="image-session"):
        server_mod.write_json(server_mod.session_path(session_id), {
            "id": session_id,
            "title": "Image runtime test",
            "createdAt": server_mod.now_iso(),
            "updatedAt": server_mod.now_iso(),
            "messageCount": 0,
        })
        server_mod.write_jsonl(server_mod.messages_path(session_id), [])
        return session_id

    def _run(
        self, permission="bypass", session_id="image-session", route=None,
        content="make one image",
    ):
        self._session(session_id)
        return server_mod._create_agent_run(
            session_id,
            {"model": "chat-model", "messages": [{"role": "user", "content": content}]},
            "https://chat.example/v1",
            [],
            allowed_tools=["generate_image"],
            permission_profile=permission,
            start_worker=False,
            image_route=self.route if route is None else route,
        )

    def _queue(self, run, call_id="image-call", arguments=None):
        arguments = arguments or {
            "prompt": "a small blue square",
            "size": "1024x1024",
            "quality": "standard",
            "count": 1,
            "outputFormat": "png",
        }
        raw = {
            "id": call_id,
            "type": "function",
            "function": {"name": "generate_image", "arguments": json.dumps(arguments)},
        }
        normalized = server_mod._normalize_agent_tool_calls(run, [raw], 1)
        run["messages"].append({
            "role": "assistant",
            "content": "",
            "tool_calls": server_mod._agent_assistant_tool_calls(normalized),
        })
        run["pending_tool_calls"] = normalized
        run["status"] = "tools"
        return run["pending_tool_calls"][0]

    def _prepared_batch_execution(self, run, call, count):
        batch_id = server_mod._agent_image_batch_id(run, call)
        return {
            "name": "generate_image",
            "arguments": call["function"]["arguments"],
            "fingerprint": call["fingerprint"],
            "status": "running",
            "operationId": batch_id,
            "dispatchState": "prepared",
            "imageBatch": {
                "schema": "image-batch/v1",
                "batchId": batch_id,
                "requested": count,
                "maxConcurrency": 2,
                "admissionStopped": False,
                "items": [
                    {
                        "index": index,
                        "operationId": server_mod._agent_image_batch_operation_id(
                            batch_id, index,
                        ),
                        "dispatchState": "prepared",
                        "result": None,
                    }
                    for index in range(count)
                ],
            },
            "result": None,
            "error": "",
        }

    def test_image_tool_requires_frozen_route_and_is_secret_free(self):
        session_id = self._session("no-image-route")
        run = server_mod._create_agent_run(
            session_id,
            {"model": "chat-model", "messages": [{"role": "user", "content": "ordinary chat"}]},
            "https://chat.example/v1",
            [],
            allowed_tools=["generate_image", "read_file"],
            permission_profile="bypass",
            start_worker=False,
        )
        self.assertNotIn("generate_image", {
            item["function"]["name"] for item in run["tools"]
        })

        for permission in ("read", "plan"):
            isolated = self._run(permission=permission, session_id=f"image-{permission}")
            self.assertNotIn("generate_image", {
                item["function"]["name"] for item in isolated["tools"]
            })

        routed = self._run()
        record = server_mod._agent_run_record(routed)
        snapshot = server_mod._agent_snapshot(routed, 0)
        self.assertEqual(record["imageRoute"]["routeRef"], self.route.route_ref)
        self.assertEqual(snapshot["imageRoute"]["modelId"], "image-model-v1")
        serialized = json.dumps({"record": record, "snapshot": snapshot})
        self.assertNotIn("IMAGE_SECRET_SENTINEL", serialized)
        self.assertNotIn("images.example", serialized)

        legacy = dict(record)
        legacy.pop("imageRoute", None)
        restored = server_mod._agent_run_from_record(legacy)
        self.assertIsNone(restored["image_route"])
        self.assertNotIn("generate_image", {
            item["function"]["name"] for item in server_mod._agent_model_tools(restored)
        })

        child = server_mod._create_agent_run(
            routed["session_id"],
            {"model": "chat-model", "messages": [{"role": "user", "content": "child"}]},
            "https://chat.example/v1",
            [],
            allowed_tools=["generate_image"],
            permission_profile="bypass",
            parent_run_id=routed["id"],
            agent_depth=1,
            start_worker=False,
        )
        self.assertNotIn("generate_image", {
            item["function"]["name"] for item in child["tools"]
        })

        routed["status"] = "waiting_credentials"
        different = image_runtime.ResolvedImageRoute(
            route_ref="ir1_" + "b" * 64,
            catalog_revision=self.route.catalog_revision,
            connection_id="other-image",
            label="Other image",
            model_id=self.route.model_id,
            supports_generation=True,
            supports_edit=False,
            base_url="https://other.invalid/v1",
            key="OTHER_SECRET",
        )
        with self.assertRaises(image_runtime.ImageRuntimeError) as captured:
            server_mod._resume_agent_run(routed, [], image_route=different)
        self.assertEqual(captured.exception.code, "image_route_model_mismatch")
        run["status"] = "waiting_credentials"
        with self.assertRaises(image_runtime.ImageRuntimeError):
            server_mod._resume_agent_run(run, [], image_route=self.route)

    def test_bypass_generation_persists_assets_and_never_repeats_upstream(self):
        run = self._run()
        call = self._queue(run)
        self.assertEqual(
            set((call.get("arguments") or {})),
            {"prompt", "count"},
        )
        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(self.client.calls[0]["request"]["size"], "auto")
        self.assertEqual(self.client.calls[0]["request"]["quality"], "auto")
        self.assertEqual(self.client.calls[0]["request"]["outputFormat"], "png")
        execution = run["tool_executions"][call["id"]]
        self.assertEqual(execution["dispatchState"], "assets_persisted")
        result = execution["result"]
        self.assertTrue(result["ok"])
        self.assertNotIn("path", json.dumps(result).lower())
        self.assertNotIn("images.example", json.dumps(result))
        asset = result["assets"][0]
        stored, meta = self.assets.read(run["session_id"], asset["assetId"])
        self.assertEqual(stored, _png())
        self.assertEqual(meta["toolCallId"], call["id"])
        self.assertEqual((meta["width"], meta["height"]), (3, 2))

    def test_count_four_uses_four_single_image_children_with_two_way_concurrency(self):
        run = self._run(session_id="image-batch-four", content="make four images")
        call = self._queue(run, call_id="image-batch-call", arguments={
            "prompt": "four ordered variants",
            "count": 4,
        })
        lock = threading.Lock()
        release_first = threading.Event()
        release_third = threading.Event()
        third_started = threading.Event()
        active = 0
        peak = 0
        calls = []

        def generate(_route, normalized, operation_id, **_kwargs):
            nonlocal active, peak
            with lock:
                index = len(calls)
                calls.append({
                    "index": index,
                    "operationId": operation_id,
                    "count": normalized["count"],
                })
                active += 1
                peak = max(peak, active)
                if index == 2:
                    third_started.set()
            try:
                if index == 0:
                    self.assertTrue(release_first.wait(5))
                elif index == 2:
                    self.assertTrue(release_third.wait(5))
                return [image_runtime.validate_image_bytes(_png(index + 2, 2))]
            finally:
                with lock:
                    active -= 1

        errors = []
        self.client.generate = mock.Mock(side_effect=generate)

        def execute():
            try:
                server_mod._execute_agent_pending_tools(run)
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        worker = threading.Thread(target=execute)
        worker.start()
        try:
            self.assertTrue(third_started.wait(5))
            release_first.set()
            release_third.set()
            worker.join(timeout=5)
        except Exception as exc:  # pragma: no cover - preserves worker cleanup
            errors.append(exc)
            release_first.set()
            release_third.set()
            worker.join(timeout=5)
            raise

        self.assertEqual(errors, [])
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(calls), 4)
        self.assertEqual([entry["count"] for entry in calls], [1, 1, 1, 1])
        self.assertEqual(len({entry["operationId"] for entry in calls}), 4)
        self.assertEqual(peak, 2)
        result = run["tool_executions"][call["id"]]["result"]
        self.assertEqual(result["requested"], 4)
        self.assertEqual(result["succeeded"], 4)
        self.assertEqual(result["failed"], 0)
        self.assertFalse(result["partial"])
        self.assertEqual([asset["batchIndex"] for asset in result["assets"]], [0, 1, 2, 3])
        self.assertEqual([asset["width"] for asset in result["assets"]], [2, 3, 4, 5])

    def test_batch_partial_success_keeps_order_and_does_not_refill_failed_items(self):
        run = self._run(session_id="image-batch-partial", content="make four images")
        call = self._queue(run, call_id="image-batch-partial-call", arguments={
            "prompt": "four variants with one ordinary failure",
            "count": 4,
        })
        lock = threading.Lock()
        calls = []

        def generate(_route, normalized, operation_id, **_kwargs):
            with lock:
                index = len(calls)
                calls.append({"index": index, "operationId": operation_id})
            self.assertEqual(normalized["count"], 1)
            if index == 1:
                raise image_runtime.ImageRuntimeError(
                    "image_upstream_http_error",
                    "Image service rejected the request.",
                    retryable=False,
                    http_status=502,
                )
            return [image_runtime.validate_image_bytes(_png(index + 2, 2))]

        self.client.generate = mock.Mock(side_effect=generate)
        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        self.assertEqual(len(calls), 4)
        result = run["tool_executions"][call["id"]]["result"]
        self.assertTrue(result["ok"])
        self.assertTrue(result["partial"])
        self.assertEqual(
            (result["requested"], result["succeeded"], result["failed"]),
            (4, 3, 1),
        )
        self.assertEqual([asset["batchIndex"] for asset in result["assets"]], [0, 2, 3])
        self.assertEqual(result["items"][1], {
            "index": 1,
            "status": "failed",
            "errorCode": "image_upstream_http_error",
            "retryable": False,
        })

    def test_batch_unknown_stops_undispatched_items_without_retry(self):
        run = self._run(session_id="image-batch-unknown", content="make four images")
        call = self._queue(run, call_id="image-batch-unknown-call", arguments={
            "prompt": "stop after unknown paid outcome",
            "count": 4,
        })
        lock = threading.Lock()
        first_returned = threading.Event()
        calls = []

        def generate(_route, normalized, operation_id, **_kwargs):
            with lock:
                index = len(calls)
                calls.append({"index": index, "operationId": operation_id})
            self.assertEqual(normalized["count"], 1)
            if index == 0:
                first_returned.set()
                raise image_runtime.ImageRuntimeError(
                    "image_upstream_timeout",
                    "Delivery and result are unknown.",
                    retryable=True,
                    http_status=504,
                    outcome_unknown=True,
                )
            self.assertTrue(first_returned.wait(5))
            return [image_runtime.validate_image_bytes(_png(3, 2))]

        self.client.generate = mock.Mock(side_effect=generate)
        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        self.assertEqual(len(calls), 2)
        result = run["tool_executions"][call["id"]]["result"]
        self.assertTrue(result["ok"])
        self.assertTrue(result["partial"])
        self.assertTrue(result["outcomeUnknown"])
        self.assertTrue(result["notReplayed"])
        self.assertEqual(
            (result["requested"], result["succeeded"], result["failed"]),
            (4, 1, 3),
        )
        self.assertEqual(
            [item["status"] for item in result["items"]],
            ["failed", "assets_persisted", "not_dispatched", "not_dispatched"],
        )
        self.assertTrue(result["items"][2]["notDispatched"])
        self.assertTrue(result["items"][3]["notDispatched"])

    def test_batch_cancel_stops_new_admission_but_keeps_inflight_successes(self):
        run = self._run(session_id="image-batch-cancel", content="make four images")
        call = self._queue(run, call_id="image-batch-cancel-call", arguments={
            "prompt": "cancel remaining variants",
            "count": 4,
        })
        lock = threading.Lock()
        two_started = threading.Event()
        release = threading.Event()
        calls = []

        def generate(_route, normalized, operation_id, **_kwargs):
            with lock:
                index = len(calls)
                calls.append({"index": index, "operationId": operation_id})
                if len(calls) == 2:
                    two_started.set()
            self.assertTrue(release.wait(5))
            return [image_runtime.validate_image_bytes(_png(index + 2, 2))]

        self.client.generate = mock.Mock(side_effect=generate)
        errors = []

        def execute():
            try:
                server_mod._execute_agent_pending_tools(run)
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        worker = threading.Thread(target=execute)
        worker.start()
        self.assertTrue(two_started.wait(5))
        run["cancel_event"].set()
        release.set()
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(calls), 2)
        result = run["tool_executions"][call["id"]]["result"]
        self.assertTrue(result["partial"])
        self.assertEqual((result["succeeded"], result["failed"]), (2, 2))
        self.assertEqual(
            [item["status"] for item in result["items"]],
            ["assets_persisted", "assets_persisted", "cancelled", "cancelled"],
        )

    def test_restart_reuses_completed_child_and_never_replays_unknown_batch_item(self):
        run = self._run(session_id="image-batch-restart")
        call = self._queue(run, call_id="image-batch-restart-call", arguments={
            "prompt": "recover mixed batch",
            "count": 4,
        })
        batch_id = server_mod._agent_image_batch_id(run, call)
        operation_ids = [
            server_mod._agent_image_batch_operation_id(batch_id, index)
            for index in range(4)
        ]
        completed = self.assets.save_operation(
            operation_ids[0],
            run["session_id"],
            run["id"],
            call["id"],
            [image_runtime.validate_image_bytes(_png(2, 2))],
            created_at=server_mod.now_iso(),
            batch_id=batch_id,
            batch_index=0,
        )
        run["tool_executions"][call["id"]] = {
            "name": "generate_image",
            "arguments": call["function"]["arguments"],
            "fingerprint": call["fingerprint"],
            "status": "running",
            "operationId": batch_id,
            "dispatchState": "dispatched",
            "imageBatch": {
                "schema": "image-batch/v1",
                "batchId": batch_id,
                "requested": 4,
                "maxConcurrency": 2,
                "items": [
                    {
                        "index": 0,
                        "operationId": operation_ids[0],
                        "dispatchState": "assets_persisted",
                        "result": completed,
                    },
                    {
                        "index": 1,
                        "operationId": operation_ids[1],
                        "dispatchState": "dispatched",
                        "result": None,
                    },
                    {
                        "index": 2,
                        "operationId": operation_ids[2],
                        "dispatchState": "prepared",
                        "result": None,
                    },
                    {
                        "index": 3,
                        "operationId": operation_ids[3],
                        "dispatchState": "prepared",
                        "result": None,
                    },
                ],
            },
            "result": None,
            "error": "",
        }

        restored = server_mod._agent_run_from_record(server_mod._agent_run_record(run))
        execution = restored["tool_executions"][call["id"]]
        self.assertEqual(execution["status"], "completed")
        result = execution["result"]
        self.assertTrue(result["partial"])
        self.assertEqual((result["succeeded"], result["failed"]), (1, 3))
        self.assertEqual(
            [item["status"] for item in result["items"]],
            ["assets_persisted", "failed", "not_dispatched", "not_dispatched"],
        )
        self.assertTrue(result["outcomeUnknown"])
        self.assertEqual(len(self.client.calls), 0)

        restored["status"] = "tools"
        retry = self._queue(restored, call_id="image-batch-retry-blocked", arguments={
            "prompt": "a changed prompt must still be blocked",
            "count": 1,
        })
        self.assertTrue(server_mod._execute_agent_pending_tools(restored))
        self.assertEqual(
            restored["tool_executions"][retry["id"]]["result"]["errorCode"],
            "image_retry_blocked",
        )
        self.assertEqual(len(self.client.calls), 0)

    def test_restart_continues_only_prepared_batch_children(self):
        run = self._run(session_id="image-batch-prepared-restart")
        call = self._queue(run, call_id="image-batch-prepared-call", arguments={
            "prompt": "resume prepared children",
            "count": 3,
        })
        batch_id = server_mod._agent_image_batch_id(run, call)
        operation_ids = [
            server_mod._agent_image_batch_operation_id(batch_id, index)
            for index in range(3)
        ]
        completed = self.assets.save_operation(
            operation_ids[0],
            run["session_id"],
            run["id"],
            call["id"],
            [image_runtime.validate_image_bytes(_png(2, 2))],
            created_at=server_mod.now_iso(),
            batch_id=batch_id,
            batch_index=0,
        )
        run["tool_executions"][call["id"]] = {
            "name": "generate_image",
            "arguments": call["function"]["arguments"],
            "fingerprint": call["fingerprint"],
            "status": "running",
            "operationId": batch_id,
            "dispatchState": "prepared",
            "imageBatch": {
                "schema": "image-batch/v1",
                "batchId": batch_id,
                "requested": 3,
                "maxConcurrency": 2,
                "items": [
                    {
                        "index": 0,
                        "operationId": operation_ids[0],
                        "dispatchState": "assets_persisted",
                        "result": completed,
                    },
                    *[
                        {
                            "index": index,
                            "operationId": operation_ids[index],
                            "dispatchState": "prepared",
                            "result": None,
                        }
                        for index in (1, 2)
                    ],
                ],
            },
            "result": None,
            "error": "",
        }

        restored = server_mod._agent_run_from_record(server_mod._agent_run_record(run))
        execution = restored["tool_executions"][call["id"]]
        self.assertEqual(execution["status"], "running")
        self.assertEqual(execution["dispatchState"], "prepared")
        restored["status"] = "tools"
        self.assertTrue(server_mod._execute_agent_pending_tools(restored))
        self.assertEqual(len(self.client.calls), 2)
        self.assertEqual(
            [entry["operationId"] for entry in self.client.calls],
            operation_ids[1:],
        )
        result = execution["result"]
        self.assertEqual((result["requested"], result["succeeded"], result["failed"]), (3, 3, 0))
        self.assertEqual([asset["batchIndex"] for asset in result["assets"]], [0, 1, 2])

    def test_restart_fails_closed_when_persisted_batch_asset_is_missing(self):
        run = self._run(session_id="image-batch-missing-asset")
        call = self._queue(run, call_id="image-batch-missing-call", arguments={
            "prompt": "recover a missing persisted asset",
            "count": 2,
        })
        execution = self._prepared_batch_execution(run, call, 2)
        batch = execution["imageBatch"]
        missing_asset_id = "ga1_" + "a" * 43
        batch["items"][0].update({
            "dispatchState": "assets_persisted",
            "result": {
                "ok": True,
                "action": "generate_image",
                "count": 1,
                "assets": [{
                    "assetId": missing_asset_id,
                    "url": (
                        f"/api/sessions/{run['session_id']}/generated-assets/"
                        f"{missing_asset_id}"
                    ),
                    "mimeType": "image/png",
                    "width": 2,
                    "height": 2,
                    "byteLength": len(_png(2, 2)),
                    "sha256": "a" * 64,
                    "batchId": batch["batchId"],
                    "batchIndex": 0,
                }],
            },
        })
        run["tool_executions"][call["id"]] = execution

        restored = server_mod._agent_run_from_record(server_mod._agent_run_record(run))
        recovered = restored["tool_executions"][call["id"]]
        result = recovered["result"]
        self.assertEqual(recovered["status"], "completed")
        self.assertEqual(result["items"][0]["errorCode"], "generated_asset_not_found")
        self.assertTrue(result["items"][0]["notReplayed"])
        self.assertNotIn("outcomeUnknown", result["items"][0])
        self.assertEqual(result["items"][1]["status"], "not_dispatched")
        self.assertEqual(result["assets"], [])
        restored["status"] = "tools"
        self.assertTrue(server_mod._execute_agent_pending_tools(restored))
        self.assertEqual(len(self.client.calls), 0)

    def test_restart_replaces_completed_batch_stale_success_when_asset_is_missing(self):
        run = self._run(session_id="image-batch-completed-missing")
        call = self._queue(run, call_id="image-batch-completed-missing-call", arguments={
            "prompt": "do not project a nonexistent completed asset",
            "count": 2,
        })
        execution = self._prepared_batch_execution(run, call, 2)
        batch = execution["imageBatch"]
        persisted = self.assets.save_operation(
            batch["items"][0]["operationId"],
            run["session_id"],
            run["id"],
            call["id"],
            [image_runtime.validate_image_bytes(_png(2, 2))],
            created_at=server_mod.now_iso(),
            batch_id=batch["batchId"],
            batch_index=0,
        )
        missing_asset_id = "ga1_" + "b" * 43
        missing = {
            "ok": True,
            "action": "generate_image",
            "count": 1,
            "assets": [{
                "assetId": missing_asset_id,
                "url": (
                    f"/api/sessions/{run['session_id']}/generated-assets/"
                    f"{missing_asset_id}"
                ),
                "mimeType": "image/png",
                "width": 2,
                "height": 2,
                "byteLength": len(_png(2, 2)),
                "sha256": "b" * 64,
                "batchId": batch["batchId"],
                "batchIndex": 1,
            }],
        }
        batch["items"][0].update({
            "dispatchState": "assets_persisted",
            "result": persisted,
        })
        batch["items"][1].update({
            "dispatchState": "assets_persisted",
            "result": missing,
        })
        execution.update({
            "status": "completed",
            "dispatchState": "assets_persisted",
            "result": server_mod._agent_image_batch_result(batch),
            "outcome": "succeeded",
        })
        run["tool_executions"][call["id"]] = execution

        restored = server_mod._agent_run_from_record(server_mod._agent_run_record(run))
        recovered = restored["tool_executions"][call["id"]]
        result = recovered["result"]
        self.assertEqual(recovered["status"], "completed")
        self.assertTrue(result["partial"])
        self.assertEqual((result["succeeded"], result["failed"]), (1, 1))
        self.assertEqual(result["assets"], persisted["assets"])
        self.assertEqual(result["items"][1]["errorCode"], "generated_asset_not_found")
        self.assertTrue(result["items"][1]["notReplayed"])
        self.assertNotIn(missing_asset_id, json.dumps(server_mod._agent_snapshot(restored, 0)))
        self.assertEqual(len(self.client.calls), 0)

    def test_restart_fails_closed_for_corrupt_partial_or_unavailable_batch_asset(self):
        for failure_kind in ("corrupt", "partial", "unavailable"):
            with self.subTest(failure_kind=failure_kind):
                run = self._run(session_id=f"image-batch-{failure_kind}-asset")
                call = self._queue(
                    run,
                    call_id=f"image-batch-{failure_kind}-call",
                    arguments={"prompt": "recover durable evidence", "count": 2},
                )
                execution = self._prepared_batch_execution(run, call, 2)
                batch = execution["imageBatch"]
                persisted = self.assets.save_operation(
                    batch["items"][0]["operationId"],
                    run["session_id"],
                    run["id"],
                    call["id"],
                    [image_runtime.validate_image_bytes(_png(2, 2))],
                    created_at=server_mod.now_iso(),
                    batch_id=batch["batchId"],
                    batch_index=0,
                )
                batch["items"][0].update({
                    "dispatchState": "assets_persisted",
                    "result": persisted,
                })
                run["tool_executions"][call["id"]] = execution
                if failure_kind == "corrupt":
                    asset_id = persisted["assets"][0]["assetId"]
                    (self.data / "generated-assets" / asset_id / "content.png").write_bytes(
                        b"corrupt-image-evidence"
                    )
                    restore_context = mock.patch.object(
                        server_mod, "_generated_asset_repository", self.assets,
                    )
                elif failure_kind == "partial":
                    restore_context = mock.patch.object(
                        self.assets,
                        "find_operation_result",
                        side_effect=image_runtime.ImageRuntimeError(
                            "image_operation_partial",
                            "A prior image operation left partial durable assets.",
                            outcome_unknown=True,
                        ),
                    )
                else:
                    restore_context = mock.patch.object(
                        self.assets,
                        "find_operation_result",
                        side_effect=image_runtime.ImageRuntimeError(
                            "generated_asset_store_unavailable",
                            "Generated asset storage is unavailable.",
                            retryable=True,
                            http_status=503,
                        ),
                    )
                with restore_context:
                    restored = server_mod._agent_run_from_record(
                        server_mod._agent_run_record(run)
                    )
                result = restored["tool_executions"][call["id"]]["result"]
                expected = {
                    "corrupt": "generated_asset_corrupt",
                    "partial": "image_operation_partial",
                    "unavailable": "generated_asset_store_unavailable",
                }[failure_kind]
                self.assertEqual(result["items"][0]["errorCode"], expected)
                self.assertTrue(result["items"][0]["notReplayed"])
                self.assertNotIn("outcomeUnknown", result["items"][0])
                self.assertEqual(result["items"][1]["status"], "not_dispatched")
                self.assertEqual(len(self.client.calls), 0)

    def test_execute_rejects_corrupt_batch_state_before_upstream(self):
        run = self._run(session_id="invalid-batch-execution")
        call = self._queue(run, call_id="invalid-batch-execution-call", arguments={
            "prompt": "reject a corrupt prepared batch",
            "count": 2,
        })
        execution = self._prepared_batch_execution(run, call, 2)
        execution["imageBatch"]["items"][0]["operationId"] = (
            "IMAGE_BATCH_EXECUTION_SECRET_SENTINEL"
        )
        run["tool_executions"][call["id"]] = execution

        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        result = run["tool_executions"][call["id"]]["result"]
        self.assertEqual(result["errorCode"], "image_batch_state_invalid")
        self.assertTrue(result["outcomeUnknown"])
        self.assertTrue(result["notReplayed"])
        self.assertNotIn("imageBatch", run["tool_executions"][call["id"]])
        self.assertNotIn(
            "IMAGE_BATCH_EXECUTION_SECRET_SENTINEL",
            json.dumps(server_mod._agent_snapshot(run, 0)),
        )
        self.assertEqual(len(self.client.calls), 0)

    def test_corrupt_batch_identity_and_structure_are_bounded_and_never_replayed(self):
        sentinel = "IMAGE_BATCH_INVALID_SECRET_SENTINEL"
        mutations = {
            "batch_id": lambda batch: batch.update({"batchId": sentinel}),
            "requested": lambda batch: batch.update({"requested": sentinel}),
            "max_concurrency": lambda batch: batch.update({"maxConcurrency": 4}),
            "non_bool_admission": lambda batch: batch.update({
                "admissionStopped": sentinel,
            }),
            "duplicate_index": lambda batch: batch["items"][1].update({"index": 0}),
            "missing_index": lambda batch: batch["items"].pop(),
            "out_of_order_index": lambda batch: batch["items"].reverse(),
            "wrong_operation": lambda batch: batch["items"][0].update({
                "operationId": sentinel,
            }),
            "duplicate_operation": lambda batch: batch["items"][1].update({
                "operationId": batch["items"][0]["operationId"],
            }),
            "empty_operation": lambda batch: batch["items"][0].update({
                "operationId": "",
            }),
            "unsupported_state": lambda batch: batch["items"][0].update({
                "dispatchState": sentinel,
            }),
            "malformed_result": lambda batch: batch["items"][0].update({
                "dispatchState": "failed",
                "result": {
                    "ok": False,
                    "action": "generate_image",
                    "errorCode": "image_upstream_http_error",
                    "retryable": False,
                    "unexpected": sentinel,
                },
            }),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                run = self._run(session_id=f"invalid-batch-{name}")
                call = self._queue(
                    run,
                    call_id=f"invalid-batch-{name}-call",
                    arguments={"prompt": "validate persisted batch", "count": 2},
                )
                execution = self._prepared_batch_execution(run, call, 2)
                mutate(execution["imageBatch"])
                run["tool_executions"][call["id"]] = execution
                raw_snapshot = server_mod._agent_snapshot(run, 0)
                raw_public = next(
                    item for item in raw_snapshot["toolExecutions"]
                    if item["toolCallId"] == call["id"]
                )
                self.assertEqual(
                    raw_public["result"]["errorCode"],
                    "image_batch_state_invalid",
                )
                self.assertNotIn(sentinel, json.dumps(raw_snapshot))
                record = server_mod._agent_run_record(run)
                restored = server_mod._agent_run_from_record(record)
                recovered = restored["tool_executions"][call["id"]]
                self.assertEqual(recovered["status"], "completed")
                self.assertEqual(
                    recovered["result"]["errorCode"],
                    "image_batch_state_invalid",
                )
                self.assertTrue(recovered["result"]["outcomeUnknown"])
                self.assertTrue(recovered["result"]["notReplayed"])
                snapshot = server_mod._agent_snapshot(restored, 0)
                self.assertNotIn(sentinel, json.dumps(snapshot))
                restored["status"] = "tools"
                self.assertTrue(server_mod._execute_agent_pending_tools(restored))
                self.assertEqual(len(self.client.calls), 0)

    def test_legacy_completed_multi_image_operation_reuses_two_assets(self):
        run = self._run(session_id="legacy-completed-multi")
        call = self._queue(run, call_id="legacy-completed-multi-call", arguments={
            "prompt": "legacy completed pair",
            "count": 2,
        })
        operation_id = "legacy-completed-multi-operation"
        expected = self.assets.save_operation(
            operation_id,
            run["session_id"],
            run["id"],
            call["id"],
            [
                image_runtime.validate_image_bytes(_png(2, 2)),
                image_runtime.validate_image_bytes(_png(3, 2)),
            ],
            created_at=server_mod.now_iso(),
        )
        run["tool_executions"][call["id"]] = {
            "name": "generate_image",
            "arguments": call["function"]["arguments"],
            "fingerprint": call["fingerprint"],
            "status": "completed",
            "operationId": operation_id,
            "dispatchState": "assets_persisted",
            "result": expected,
            "error": "",
        }
        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        self.assertEqual(run["tool_executions"][call["id"]]["result"], expected)
        restored = server_mod._agent_run_from_record(server_mod._agent_run_record(run))
        restored["status"] = "tools"
        self.assertTrue(server_mod._execute_agent_pending_tools(restored))
        self.assertEqual(restored["tool_executions"][call["id"]]["result"], expected)
        self.assertEqual(len(expected["assets"]), 2)
        self.assertNotIn("imageBatch", restored["tool_executions"][call["id"]])
        self.assertEqual(len(self.client.calls), 0)

    def test_reference_edit_batch_reuses_one_explicit_reference_for_each_child(self):
        run = self._run(
            session_id="image-batch-reference-edit",
            content="make two edits of the explicit reference",
        )
        attachment = self.attachments / "reference.png"
        attachment.write_bytes(_png(4, 5))
        server_mod.write_jsonl(server_mod.messages_path(run["session_id"]), [{
            "role": "user",
            "content": "explicit reference",
            "_images": [{
                "path": "attachments/reference.png",
                "name": "reference.png",
                "mime": "image/png",
            }],
        }])
        call = self._queue(run, call_id="image-batch-reference-call", arguments={
            "prompt": "two edits of the explicit reference",
            "reference": {"type": "attachment", "id": "attachments/reference.png"},
            "count": 2,
        })

        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        self.assertEqual(len(self.client.calls), 2)
        self.assertEqual([entry["request"]["count"] for entry in self.client.calls], [1, 1])
        self.assertEqual(len({entry["operationId"] for entry in self.client.calls}), 2)
        references = [entry["reference"] for entry in self.client.calls]
        self.assertTrue(all(reference is not None for reference in references))
        self.assertEqual({reference.sha256 for reference in references}, {
            image_runtime.validate_image_bytes(_png(4, 5)).sha256,
        })

    def test_batch_cancel_between_admissions_does_not_dispatch_next_child(self):
        run = self._run(
            session_id="image-batch-cancel-between-admissions",
            content="make three images",
        )
        call = self._queue(run, call_id="image-batch-cancel-between-call", arguments={
            "prompt": "cancel after the first durable admission",
            "count": 3,
        })
        original_persist = server_mod._persist_agent_run
        cancellation_observed = threading.Event()

        def persist_then_cancel(candidate_run):
            original_persist(candidate_run)
            execution = candidate_run.get("tool_executions", {}).get(call["id"], {})
            batch = execution.get("imageBatch") or {}
            items = batch.get("items") or []
            if (
                not cancellation_observed.is_set()
                and items
                and items[0].get("dispatchState") == "dispatched"
            ):
                cancellation_observed.set()
                candidate_run["cancel_event"].set()

        with mock.patch.object(
            server_mod,
            "_persist_agent_run",
            side_effect=persist_then_cancel,
        ):
            server_mod._execute_agent_pending_tools(run)

        self.assertTrue(cancellation_observed.is_set())
        self.assertEqual(len(self.client.calls), 1)
        batch = run["tool_executions"][call["id"]]["imageBatch"]
        self.assertEqual(
            [item["dispatchState"] for item in batch["items"]],
            ["assets_persisted", "cancelled", "cancelled"],
        )

    def test_legacy_multi_image_dispatched_record_is_unknown_and_not_split(self):
        run = self._run(session_id="legacy-multi-image-dispatched")
        call = self._queue(run, call_id="legacy-multi-call", arguments={
            "prompt": "legacy two image request",
            "count": 2,
        })
        run["tool_executions"][call["id"]] = {
            "name": "generate_image",
            "arguments": call["function"]["arguments"],
            "fingerprint": call["fingerprint"],
            "status": "running",
            "operationId": "legacy-multi-operation",
            "dispatchState": "dispatched",
            "result": None,
            "error": "",
        }

        restored = server_mod._agent_run_from_record(server_mod._agent_run_record(run))
        execution = restored["tool_executions"][call["id"]]
        self.assertEqual(execution["status"], "completed")
        self.assertEqual(execution["result"]["errorCode"], "image_outcome_unknown")
        self.assertTrue(execution["result"]["notReplayed"])
        self.assertNotIn("imageBatch", execution)
        self.assertEqual(len(self.client.calls), 0)

    def test_batch_total_size_limit_fails_paid_item_before_asset_save(self):
        run = self._run(session_id="image-batch-total-size", content="make two images")
        call = self._queue(run, call_id="image-batch-total-size-call", arguments={
            "prompt": "batch total size limit",
            "count": 2,
        })
        payload = image_runtime.validate_image_bytes(_png(2, 2))
        self.client.generate = mock.Mock(return_value=[payload])
        with mock.patch.object(server_mod, "MAX_IMAGE_TOTAL_BYTES", payload.byte_length):
            self.assertTrue(server_mod._execute_agent_pending_tools(run))
        result = run["tool_executions"][call["id"]]["result"]
        self.assertTrue(result["partial"])
        self.assertEqual((result["succeeded"], result["failed"]), (1, 1))
        self.assertEqual(result["items"][1]["errorCode"], "image_response_too_large")
        self.assertEqual(len(self.assets.snapshot_session_assets(run["session_id"])), 1)

    def test_simulated_66_second_completion_persists_one_idempotent_asset(self):
        now = {"value": 0.0}
        requests = []
        payload = json.dumps({"data": [{
            "b64_json": base64.b64encode(_png()).decode("ascii"),
        }]}).encode("utf-8")

        class Response:
            status = 200
            headers = {"Content-Length": str(len(payload))}

            def __init__(self):
                self.body = io.BytesIO(payload)

            def read(self, size=-1):
                return self.body.read(size)

            def close(self):
                pass

        def urlopen(req, timeout):
            requests.append({
                "timeout": timeout,
                "idempotencyKey": req.get_header("Idempotency-key"),
            })
            now["value"] = 66.0
            return Response()

        client = image_runtime.ImageUpstreamClient(
            urlopen=urlopen,
            clock=lambda: now["value"],
        )
        run = self._run(permission="bypass", session_id="image-66-second-success")
        call = self._queue(run, call_id="slow-image-success")
        with mock.patch.object(server_mod, "_image_upstream_client", client):
            self.assertTrue(server_mod._execute_agent_pending_tools(run))

        execution = run["tool_executions"][call["id"]]
        self.assertEqual(execution["dispatchState"], "assets_persisted")
        self.assertEqual(requests, [{
            "timeout": 180,
            "idempotencyKey": execution["operationId"],
        }])
        asset = execution["result"]["assets"][0]
        stored, meta = self.assets.read(run["session_id"], asset["assetId"])
        self.assertEqual(stored, _png())
        self.assertEqual((meta["width"], meta["height"]), (3, 2))
        self.assertEqual(meta["operationId"], execution["operationId"])

    def test_accept_gate_redacts_prompt_and_reject_is_terminal_for_tool(self):
        run = self._run(permission="accept", content="make two images")
        call = self._queue(run, arguments={
            "prompt": "PROMPT_SECRET_SENTINEL",
            "count": 2,
            "size": "1024x1024",
            "quality": "hd",
            "outputFormat": "webp",
        })
        self.assertFalse(server_mod._execute_agent_pending_tools(run))
        self.assertEqual(run["status"], "waiting_authorization")
        public = server_mod._agent_public_pending_authorization(run)
        self.assertEqual(public["action"], "generate_image")
        self.assertEqual(public["modelId"], "image-model-v1")
        self.assertEqual(public["count"], 2)
        self.assertEqual(public["size"], "auto")
        self.assertEqual(public["quality"], "auto")
        self.assertEqual(public["outputFormat"], "png")
        self.assertEqual(public["maxIndependentRequests"], 2)
        self.assertNotIn("PROMPT_SECRET_SENTINEL", json.dumps(public))
        server_mod._submit_agent_authorization(run, public["authorizationId"], "rejected")
        self.assertEqual(len(self.client.calls), 0)
        result = run["tool_executions"][call["id"]]["result"]
        self.assertEqual(result["errorCode"], "image_generation_rejected")
        self.assertNotIn(call["id"], [item["id"] for item in run["pending_tool_calls"]])

    def test_tool_arguments_cannot_override_route_credentials_or_headers(self):
        run = self._run()
        call = self._queue(run, arguments={
            "prompt": "attempt route override",
            "baseUrl": "https://attacker.invalid",
            "key": "ATTACKER_SECRET",
            "headers": {"Authorization": "Bearer ATTACKER_SECRET"},
        })
        self.assertTrue(call["validationErrors"])
        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        result = run["tool_executions"][call["id"]]["result"]
        self.assertFalse(result["ok"])
        self.assertEqual(result["errorCode"], "invalid_tool_arguments")
        self.assertEqual(len(self.client.calls), 0)
        serialized = json.dumps(server_mod._agent_run_record(run))
        self.assertNotIn("ATTACKER_SECRET", serialized)
        self.assertNotIn("attacker.invalid", serialized)

        malformed = server_mod._normalize_agent_tool_calls(run, [{
            "id": "malformed-image-call",
            "type": "function",
            "function": {
                "name": "generate_image",
                "arguments": '{"key":"MALFORMED_SECRET"',
            },
        }], 2)[0]
        self.assertEqual(malformed["function"]["arguments"], "{}")
        self.assertNotIn("MALFORMED_SECRET", json.dumps(malformed))

    def test_model_surface_omits_execution_controls_and_legacy_values_share_fingerprint(self):
        run = self._run()
        definition = next(
            item for item in server_mod._agent_model_tools(run)
            if item["function"]["name"] == "generate_image"
        )
        properties = definition["function"]["parameters"]["properties"]
        self.assertNotIn("size", properties)
        self.assertNotIn("quality", properties)
        self.assertNotIn("outputFormat", properties)

        raw_calls = []
        for index, controls in enumerate((
            {"size": "1024x1024", "quality": "hd", "outputFormat": "webp"},
            {"size": "999x999", "quality": "provider-ultra", "outputFormat": "gif"},
        )):
            raw_calls.append({
                "id": f"legacy-image-{index}",
                "type": "function",
                "function": {
                    "name": "generate_image",
                    "arguments": json.dumps({
                        "prompt": "same effective image request",
                        "count": 1,
                        **controls,
                    }),
                },
            })
        normalized = server_mod._normalize_agent_tool_calls(run, raw_calls, 1)
        self.assertEqual(normalized[0]["fingerprint"], normalized[1]["fingerprint"])
        self.assertEqual(normalized[0]["arguments"], {
            "prompt": "same effective image request",
            "count": 1,
        })

    def test_dispatched_nonretryable_failure_blocks_changed_retry_before_authorization_after_restart(self):
        run = self._run(permission="accept", session_id="image-retry-fuse")
        first = self._queue(run, call_id="paid-failure", arguments={
            "prompt": "first paid attempt",
            "size": "1024x1024",
            "quality": "hd",
            "count": 1,
            "outputFormat": "png",
        })
        self.assertFalse(server_mod._execute_agent_pending_tools(run))
        pending = server_mod._agent_public_pending_authorization(run)
        server_mod._submit_agent_authorization(run, pending["authorizationId"], "approved")
        upstream = mock.Mock(side_effect=image_runtime.ImageRuntimeError(
            "image_upstream_http_error",
            "Image service rejected the request.",
            retryable=False,
            http_status=400,
        ))
        self.client.generate = upstream
        run["status"] = "tools"
        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        self.assertEqual(upstream.call_count, 1)
        first_result = run["tool_executions"][first["id"]]["result"]
        self.assertFalse(first_result["retryable"])
        self.assertEqual(run["tool_executions"][first["id"]]["dispatchState"], "dispatched")

        server_mod._persist_agent_run(run)
        with server_mod._agent_run_lock:
            server_mod._agent_runs.pop(run["id"], None)
        restored = server_mod._get_agent_run(run["id"])
        self.assertIsNotNone(restored)
        second = self._queue(restored, call_id="changed-retry", arguments={
            "prompt": "changed prompt must not spend again",
            "size": "auto",
            "quality": "standard",
            "count": 1,
            "outputFormat": "jpeg",
        })
        authorization_events_before = len([
            event for event in restored["events"]
            if event["type"] == "authorization_required"
        ])
        self.assertTrue(server_mod._execute_agent_pending_tools(restored))
        blocked = restored["tool_executions"][second["id"]]["result"]
        self.assertEqual(blocked["errorCode"], "image_retry_blocked")
        self.assertTrue(blocked["retryBlocked"])
        self.assertTrue(blocked["notReplayed"])
        self.assertFalse(blocked["retryable"])
        self.assertEqual(upstream.call_count, 1)
        self.assertIsNone(restored.get("pending_authorization"))
        self.assertEqual(len([
            event for event in restored["events"]
            if event["type"] == "authorization_required"
        ]), authorization_events_before)

        fresh = self._run(permission="bypass", session_id="image-retry-fresh-run")
        self._queue(fresh, call_id="fresh-run-attempt", arguments={
            "prompt": "new user message may try once",
            "quality": "hd",
        })
        self.assertTrue(server_mod._execute_agent_pending_tools(fresh))
        self.assertEqual(upstream.call_count, 2)

    def test_outcome_unknown_failure_blocks_changed_bypass_retry(self):
        run = self._run(permission="bypass", session_id="image-unknown-fuse")
        first = self._queue(run, call_id="unknown-paid-failure")
        upstream = mock.Mock(side_effect=image_runtime.ImageRuntimeError(
            "image_response_format_mismatch",
            "Generated image format did not match the requested output format.",
            retryable=True,
            outcome_unknown=True,
        ))
        self.client.generate = upstream
        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        self.assertTrue(run["tool_executions"][first["id"]]["result"]["outcomeUnknown"])
        self._queue(run, call_id="unknown-changed-retry", arguments={
            "prompt": "do not retry an uncertain paid request",
            "count": 1,
        })
        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        blocked = run["tool_executions"]["unknown-changed-retry"]["result"]
        self.assertEqual(blocked["errorCode"], "image_retry_blocked")
        self.assertEqual(upstream.call_count, 1)

    def test_timeout_persists_one_operation_and_blocks_second_paid_dispatch(self):
        run = self._run(permission="bypass", session_id="image-timeout-fuse")
        first = self._queue(run, call_id="timed-out-paid-request")
        upstream = mock.Mock(side_effect=image_runtime.ImageRuntimeError(
            "image_upstream_timeout",
            "Timed out while contacting the image service; delivery and the result are unknown.",
            retryable=True,
            http_status=504,
            outcome_unknown=True,
        ))
        self.client.generate = upstream

        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        first_execution = run["tool_executions"][first["id"]]
        first_result = first_execution["result"]
        operation_id = first_execution["operationId"]
        self.assertTrue(operation_id)
        self.assertEqual(first_execution["dispatchState"], "dispatched")
        self.assertEqual(first_result["errorCode"], "image_upstream_timeout")
        self.assertTrue(first_result["outcomeUnknown"])
        self.assertTrue(first_result["notReplayed"])
        self.assertEqual(upstream.call_count, 1)
        self.assertEqual(upstream.call_args.args[2], operation_id)

        server_mod._persist_agent_run(run)
        with server_mod._agent_run_lock:
            server_mod._agent_runs.pop(run["id"], None)
        restored = server_mod._get_agent_run(run["id"])
        self.assertIsNotNone(restored)
        second = self._queue(restored, call_id="changed-after-timeout", arguments={
            "prompt": "a different paid image request must be blocked",
            "count": 1,
        })
        self.assertTrue(server_mod._execute_agent_pending_tools(restored))
        blocked_execution = restored["tool_executions"][second["id"]]
        self.assertEqual(blocked_execution["result"]["errorCode"], "image_retry_blocked")
        self.assertTrue(blocked_execution["result"]["notReplayed"])
        self.assertNotIn("operationId", blocked_execution)
        operation_ids = [
            execution.get("operationId")
            for execution in restored["tool_executions"].values()
            if execution.get("operationId")
        ]
        self.assertEqual(operation_ids, [operation_id])
        self.assertEqual(upstream.call_count, 1)
        self.assertFalse(any(
            event["type"] == "authorization_required"
            for event in restored["events"]
        ))

    def test_unexpected_upstream_diagnostics_are_redacted_after_dispatch(self):
        run = self._run()
        call = self._queue(run)
        self.client.generate = mock.Mock(
            side_effect=RuntimeError("IMAGE_SECRET_SENTINEL https://images.example/v1"),
        )
        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        result = run["tool_executions"][call["id"]]["result"]
        self.assertEqual(result["errorCode"], "image_runtime_failed")
        self.assertTrue(result["outcomeUnknown"])
        serialized = json.dumps({
            "result": result,
            "record": server_mod._agent_run_record(run),
            "snapshot": server_mod._agent_snapshot(run, 0),
        })
        self.assertNotIn("IMAGE_SECRET_SENTINEL", serialized)
        self.assertNotIn("images.example", serialized)

    def test_paid_output_contract_failure_never_persists_an_asset(self):
        run = self._run()
        call = self._queue(run)
        self.client.generate = mock.Mock(side_effect=image_runtime.ImageRuntimeError(
            "image_response_format_mismatch",
            "Generated image format did not match the requested output format.",
            outcome_unknown=True,
        ))
        with mock.patch.object(self.assets, "save_operation", wraps=self.assets.save_operation) as save:
            self.assertTrue(server_mod._execute_agent_pending_tools(run))
        save.assert_not_called()
        result = run["tool_executions"][call["id"]]["result"]
        self.assertEqual(result["errorCode"], "image_response_format_mismatch")
        self.assertTrue(result["outcomeUnknown"])
        self.assertTrue(result["notReplayed"])
        self.assertFalse((self.data / "generated-assets").exists())

    def test_session_delete_during_paid_dispatch_never_leaves_a_late_asset(self):
        run = self._run(session_id="delete-during-image")
        call = self._queue(run)
        upstream_entered = threading.Event()
        release_upstream = threading.Event()
        errors = []
        validated = image_runtime.validate_image_bytes(_png())

        def blocked_generate(*_args, **_kwargs):
            upstream_entered.set()
            if not release_upstream.wait(5):
                raise AssertionError("image upstream release was not signalled")
            return [validated]

        self.client.generate = mock.Mock(side_effect=blocked_generate)

        def execute():
            try:
                server_mod._execute_agent_pending_tools(run)
            except Exception as exc:  # pragma: no cover - assertion reports details
                errors.append(exc)

        worker = threading.Thread(target=execute)
        worker.start()
        self.assertTrue(upstream_entered.wait(5))

        handler = object.__new__(server_mod.CodeHandler)
        handler.send_json = mock.Mock()
        server_mod.CodeHandler.delete_session(handler, run["session_id"])
        self.assertEqual(handler.send_json.call_args.args[0], {"ok": True})
        release_upstream.set()
        worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        result = run["tool_executions"][call["id"]]["result"]
        self.assertEqual(result["errorCode"], "image_session_deleted")
        self.assertTrue(result["outcomeUnknown"])
        self.assertTrue(result["notReplayed"])
        self.assertEqual(self.client.generate.call_count, 1)
        self.assertEqual(self.assets.snapshot_session_assets(run["session_id"]), [])
        self.assertFalse(server_mod.session_path(run["session_id"]).exists())

    def test_accept_approval_and_missing_runtime_credentials_resume_from_prepared(self):
        run = self._run(permission="accept")
        call = self._queue(run)
        self.assertFalse(server_mod._execute_agent_pending_tools(run))
        pending = server_mod._agent_public_pending_authorization(run)
        server_mod._submit_agent_authorization(run, pending["authorizationId"], "approved")

        restarted_registry = image_runtime.ImageRouteRegistry(self.registry_path)
        with mock.patch.object(server_mod, "_image_route_registry", restarted_registry):
            run["status"] = "tools"
            self.assertFalse(server_mod._execute_agent_pending_tools(run))
        execution = run["tool_executions"][call["id"]]
        self.assertEqual(run["status"], "waiting_credentials")
        self.assertEqual(execution["dispatchState"], "prepared")
        self.assertEqual(len(self.client.calls), 0)

        rebound = restarted_registry.refresh([{
            "connectionId": "image-qa",
            "name": "Image QA",
            "baseUrl": "https://rotated-images.example/v1",
            "key": "ROTATED_IMAGE_SECRET_SENTINEL",
            "models": [{"id": "image-model-v1", "supportsEdit": True}],
        }])
        self.assertEqual(rebound["catalogRevision"], self.route.catalog_revision)
        self.assertEqual(rebound["routes"][0]["routeRef"], self.route.route_ref)
        with mock.patch.object(server_mod, "_image_route_registry", restarted_registry):
            run["status"] = "tools"
            self.assertTrue(server_mod._execute_agent_pending_tools(run))
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(self.client.calls[0]["key"], "ROTATED_IMAGE_SECRET_SENTINEL")
        self.assertEqual(
            self.client.calls[0]["baseUrl"], "https://rotated-images.example/v1",
        )
        self.assertTrue(execution["result"]["ok"])

    def test_restart_marks_dispatched_without_assets_unknown_and_never_calls_upstream(self):
        run = self._run()
        call = self._queue(run)
        run["tool_executions"][call["id"]] = {
            "name": "generate_image",
            "arguments": call["function"]["arguments"],
            "fingerprint": call["fingerprint"],
            "status": "running",
            "operationId": "unknown-operation",
            "dispatchState": "dispatched",
            "result": None,
            "error": "",
        }
        restored = server_mod._agent_run_from_record(server_mod._agent_run_record(run))
        result = restored["tool_executions"][call["id"]]["result"]
        self.assertEqual(result["errorCode"], "image_outcome_unknown")
        self.assertTrue(result["notReplayed"])
        self.assertTrue(result["outcomeUnknown"])
        self.assertEqual(len(self.client.calls), 0)

        before = server_mod._agent_cancel_tool_result(
            {"dispatchState": "prepared"}, "generate_image", cancelled_before_start=True,
        )
        self.assertTrue(before["cancelledBeforeStart"])
        self.assertNotIn("outcomeUnknown", before)
        after = server_mod._agent_cancel_tool_result(
            {"dispatchState": "dispatched"}, "generate_image",
        )
        self.assertEqual(after["errorCode"], "image_outcome_unknown")
        self.assertTrue(after["notReplayed"])

    def test_restart_recovers_assets_after_dispatch_without_another_upstream_call(self):
        run = self._run()
        call = self._queue(run)
        operation_id = "durable-operation"
        expected = self.assets.save_operation(
            operation_id,
            run["session_id"],
            run["id"],
            call["id"],
            [image_runtime.validate_image_bytes(_png())],
            created_at=server_mod.now_iso(),
        )
        run["tool_executions"][call["id"]] = {
            "name": "generate_image",
            "arguments": call["function"]["arguments"],
            "fingerprint": call["fingerprint"],
            "status": "running",
            "operationId": operation_id,
            "dispatchState": "dispatched",
            "result": None,
            "error": "",
        }
        restored = server_mod._agent_run_from_record(server_mod._agent_run_record(run))
        execution = restored["tool_executions"][call["id"]]
        self.assertEqual(execution["status"], "completed")
        self.assertEqual(execution["result"], {**expected, "replayed": True})
        self.assertTrue(execution["result"]["replayed"])
        restored["status"] = "tools"
        self.assertTrue(server_mod._execute_agent_pending_tools(restored))
        completed = [
            event for event in restored["events"]
            if event["type"] == "tool_completed" and event["data"].get("toolCallId") == call["id"]
        ]
        self.assertEqual(len(completed), 1)
        self.assertEqual(len(self.client.calls), 0)

    def test_edit_reference_requires_persisted_current_session_attachment(self):
        run = self._run()
        attachment = self.attachments / "reference.png"
        attachment.write_bytes(_png(4, 5))
        server_mod.write_jsonl(server_mod.messages_path(run["session_id"]), [{
            "role": "user",
            "content": "reference",
            "_images": [{"path": "attachments/reference.png", "name": "reference.png", "mime": "image/png"}],
        }])
        self._queue(run, arguments={
            "prompt": "edit the owned image",
            "reference": {"type": "attachment", "id": "attachments/reference.png"},
            "count": 1,
            "outputFormat": "png",
        })
        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        self.assertEqual(self.client.calls[0]["reference"].width, 4)

        other = self._run(session_id="other-session")
        call = self._queue(other, arguments={
            "prompt": "must not read another session attachment",
            "reference": {"type": "attachment", "id": "attachments/reference.png"},
            "count": 1,
            "outputFormat": "png",
        })
        self.assertTrue(server_mod._execute_agent_pending_tools(other))
        result = other["tool_executions"][call["id"]]["result"]
        self.assertEqual(result["errorCode"], "image_reference_forbidden")
        self.assertEqual(len(self.client.calls), 1)

    def test_legacy_false_edit_capability_does_not_block_owned_reference(self):
        legacy_route = image_runtime.ResolvedImageRoute(
            route_ref=self.route.route_ref,
            catalog_revision=self.route.catalog_revision,
            connection_id=self.route.connection_id,
            label=self.route.label,
            model_id=self.route.model_id,
            supports_generation=True,
            supports_edit=False,
            base_url=self.route.base_url,
            key=self.route.key,
        )
        run = self._run(session_id="legacy-edit-capability", route=legacy_route)
        attachment = self.attachments / "legacy-reference.png"
        attachment.write_bytes(_png(4, 5))
        server_mod.write_jsonl(server_mod.messages_path(run["session_id"]), [{
            "role": "user",
            "content": "reference",
            "_images": [{
                "path": "attachments/legacy-reference.png",
                "name": "legacy-reference.png",
                "mime": "image/png",
            }],
        }])
        call = self._queue(run, arguments={
            "prompt": "edit the legacy owned image",
            "reference": {"type": "attachment", "id": "attachments/legacy-reference.png"},
            "count": 1,
            "outputFormat": "png",
        })
        with mock.patch.object(self.registry, "resolve", return_value=legacy_route):
            self.assertTrue(server_mod._execute_agent_pending_tools(run))
        result = run["tool_executions"][call["id"]]["result"]
        self.assertTrue(result["ok"])
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(self.client.calls[0]["reference"].width, 4)

    def test_route_and_asset_http_apis_are_secret_free_and_session_scoped(self):
        run = self._run()
        call = self._queue(run)
        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        asset_id = run["tool_executions"][call["id"]]["result"]["assets"][0]["assetId"]

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.CodeHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            refreshed = requests.post(f"{base}/api/image-routes/refresh", json={
                "connections": [{
                    "connectionId": "image-qa",
                    "name": "Image QA",
                    "baseUrl": "https://images.example/v1",
                    "key": "IMAGE_SECRET_SENTINEL",
                    "models": [{"id": "image-model-v1", "supportsEdit": True}],
                }],
            }, timeout=3)
            self.assertEqual(refreshed.status_code, 200)
            self.assertNotIn("IMAGE_SECRET_SENTINEL", refreshed.text)
            self.assertNotIn("images.example", refreshed.text)
            catalog = requests.get(f"{base}/api/image-routes", timeout=3)
            self.assertEqual(catalog.status_code, 200)
            self.assertNotIn("IMAGE_SECRET_SENTINEL", catalog.text)
            self.assertNotIn("images.example", catalog.text)

            route = catalog.json()["routes"][0]
            admitted = {"id": "a" * 32, "status": "model", "client_request_id": ""}
            with mock.patch.object(server_mod, "_create_agent_run", return_value=admitted) as create:
                created = requests.post(f"{base}/api/agent/runs", json={
                    "sessionId": run["session_id"],
                    "payload": {
                        "model": "chat-model",
                        "messages": [{"role": "user", "content": "image"}],
                    },
                    "allowedTools": ["generate_image"],
                    "permissionProfile": "bypass",
                    "imageRouteRef": route["routeRef"],
                    "imageCatalogRevision": catalog.json()["catalogRevision"],
                    "imageModelId": route["modelId"],
                }, timeout=3)
            self.assertEqual(created.status_code, 201)
            bound = create.call_args.kwargs["image_route"]
            self.assertEqual(bound.route_ref, route["routeRef"])
            self.assertEqual(bound.key, "IMAGE_SECRET_SENTINEL")
            self.assertNotIn("IMAGE_SECRET_SENTINEL", created.text)

            incomplete = requests.post(f"{base}/api/agent/runs", json={
                "sessionId": run["session_id"],
                "payload": {
                    "model": "chat-model",
                    "messages": [{"role": "user", "content": "image"}],
                },
                "imageRouteRef": route["routeRef"],
            }, timeout=3)
            self.assertEqual(incomplete.status_code, 400)
            self.assertEqual(incomplete.json()["errorCode"], "image_route_invalid")

            owned = requests.get(
                f"{base}/api/sessions/{run['session_id']}/generated-assets/{asset_id}", timeout=3,
            )
            self.assertEqual(owned.status_code, 200)
            self.assertEqual(owned.headers["Content-Type"], "image/png")
            self.assertEqual(owned.content, _png())

            forbidden = requests.get(
                f"{base}/api/sessions/other-session/generated-assets/{asset_id}", timeout=3,
            )
            self.assertEqual(forbidden.status_code, 403)
            self.assertNotIn("generated-assets", forbidden.text)

            deleted = requests.delete(f"{base}/api/sessions/{run['session_id']}", timeout=3)
            self.assertEqual(deleted.status_code, 200)
            with self.assertRaises(image_runtime.ImageRuntimeError):
                self.assets.read(run["session_id"], asset_id)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)

    def test_agent_run_create_can_rebind_empty_runtime_catalog_once_with_same_request_id(self):
        session_id = self._session("image-rebind-session")
        frozen_route = {
            "routeRef": self.route.route_ref,
            "catalogRevision": self.route.catalog_revision,
            "modelId": self.route.model_id,
        }
        runtime_registry = image_runtime.ImageRouteRegistry(self.registry_path)
        with runtime_registry._lock:
            runtime_registry._catalog["routes"] = []
            runtime_registry._credentials = {}
            runtime_registry._base_urls = {}

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.CodeHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        create_payload = {
            "sessionId": session_id,
            "clientRequestId": "stable-image-rebind-request",
            "payload": {
                "model": "chat-model",
                "messages": [{"role": "user", "content": "one image request"}],
            },
            "baseUrl": "http://127.0.0.1:9/v1",
            "keys": ["CHAT_SECRET_SENTINEL"],
            "allowedTools": ["generate_image"],
            "permissionProfile": "bypass",
            "imageRouteRef": frozen_route["routeRef"],
            "imageCatalogRevision": frozen_route["catalogRevision"],
            "imageModelId": frozen_route["modelId"],
        }
        try:
            with (
                mock.patch.object(server_mod, "_image_route_registry", runtime_registry),
                mock.patch.object(server_mod, "_start_agent_worker") as start_worker,
            ):
                failed = requests.post(
                    f"{base}/api/agent/runs", json=create_payload, timeout=3,
                )
                self.assertEqual(failed.status_code, 503)
                self.assertEqual(failed.json()["errorCode"], "image_route_catalog_unavailable")
                self.assertEqual(server_mod._agent_runs, {})
                start_worker.assert_not_called()

                refreshed = requests.post(f"{base}/api/image-routes/refresh", json={
                    "connections": [{
                        "connectionId": "image-qa",
                        "name": "Image QA",
                        "baseUrl": "https://rotated-images.example/v1",
                        "key": "ROTATED_IMAGE_SECRET_SENTINEL",
                        "models": [{"id": "image-model-v1"}],
                    }],
                }, timeout=3)
                self.assertEqual(refreshed.status_code, 200)
                rebound = refreshed.json()
                self.assertEqual(rebound["routes"][0]["routeRef"], frozen_route["routeRef"])
                self.assertGreater(
                    rebound["catalogRevision"], frozen_route["catalogRevision"],
                )

                retried_payload = {
                    **create_payload,
                    "imageCatalogRevision": rebound["catalogRevision"],
                }
                created = requests.post(
                    f"{base}/api/agent/runs", json=retried_payload, timeout=3,
                )
                self.assertEqual(created.status_code, 201)
                run_id = created.json()["agentRunId"]
                self.assertTrue(run_id)
                self.assertEqual(len(server_mod._agent_runs), 1)
                self.assertEqual(
                    server_mod._agent_runs[run_id]["client_request_id"],
                    "stable-image-rebind-request",
                )
                self.assertEqual(
                    server_mod._agent_runs[run_id]["image_route"]["catalogRevision"],
                    rebound["catalogRevision"],
                )

                with ThreadPoolExecutor(max_workers=2) as pool:
                    repeats = list(pool.map(
                        lambda _: requests.post(
                            f"{base}/api/agent/runs", json=retried_payload, timeout=3,
                        ),
                        range(2),
                    ))
                self.assertEqual([item.status_code for item in repeats], [201, 201])
                self.assertEqual(
                    [item.json()["agentRunId"] for item in repeats],
                    [run_id, run_id],
                )
                self.assertEqual(len(server_mod._agent_runs), 1)
                start_worker.assert_called_once()
                serialized = json.dumps({
                    "failed": failed.json(),
                    "catalog": rebound,
                    "created": created.json(),
                })
                for secret in (
                    "CHAT_SECRET_SENTINEL",
                    "ROTATED_IMAGE_SECRET_SENTINEL",
                    "rotated-images.example",
                ):
                    self.assertNotIn(secret, serialized)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
