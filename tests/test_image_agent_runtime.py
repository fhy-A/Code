"""AgentRun and route integration coverage for the independent image runtime."""

import io
import json
import tempfile
import threading
import unittest
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

    def _run(self, permission="bypass", session_id="image-session", route=None):
        self._session(session_id)
        return server_mod._create_agent_run(
            session_id,
            {"model": "chat-model", "messages": [{"role": "user", "content": "make an image"}]},
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
        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        self.assertEqual(len(self.client.calls), 1)
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

    def test_accept_gate_redacts_prompt_and_reject_is_terminal_for_tool(self):
        run = self._run(permission="accept")
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

        restarted_registry.refresh([{
            "connectionId": "image-qa",
            "name": "Image QA",
            "baseUrl": "https://images.example/v1",
            "key": "IMAGE_SECRET_SENTINEL",
            "models": [{"id": "image-model-v1", "supportsEdit": True}],
        }])
        with mock.patch.object(server_mod, "_image_route_registry", restarted_registry):
            run["status"] = "tools"
            self.assertTrue(server_mod._execute_agent_pending_tools(run))
        self.assertEqual(len(self.client.calls), 1)
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


if __name__ == "__main__":
    unittest.main()
