import json
import base64
import io
import inspect
import hashlib
import unittest
from pathlib import Path
from unittest import mock

import launcher
import server


ROOT = Path(__file__).resolve().parent.parent


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class TestImageVisionBridge(unittest.TestCase):
    @staticmethod
    def _image_bytes(image_format):
        from PIL import Image

        image = Image.new("RGBA", (16, 16), (30, 120, 210, 180))
        if image_format in {"JPEG", "BMP"}:
            image = image.convert("RGB")
        output = io.BytesIO()
        image.save(output, format=image_format)
        return output.getvalue()

    def test_image_limit_is_separate_from_text_limit(self):
        self.assertGreater(server.MAX_TOOL_IMAGE_BYTES, server.MAX_TOOL_READ_BYTES)

    def test_server_agent_injects_tool_images_as_image_url(self):
        result = {
            "ok": True,
            "action": "read_file",
            "path": "assets/example.png",
            "binary": True,
            "visual": True,
            "mime": "image/png",
            "base64": "aW1hZ2U=",
        }
        marker = server._agent_tool_vision_marker(result, "call-image")
        run = {
            "messages": [{
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call-image",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }],
            }, {
                "role": "tool",
                "tool_call_id": "call-image",
                "name": "read_file",
                "content": "image loaded",
            }, marker],
            "tool_executions": {
                "call-image": {"status": "completed", "result": result},
            },
        }

        messages = server._agent_model_messages(run)

        self.assertEqual(marker["_agentToolVisionCallId"], "call-image")
        self.assertEqual([message["role"] for message in messages], ["assistant", "tool", "user"])
        self.assertEqual(messages[2]["content"][1]["type"], "image_url")
        self.assertEqual(
            messages[2]["content"][1]["image_url"]["url"],
            "data:image/png;base64,aW1hZ2U=",
        )

    def test_durable_vision_marker_does_not_duplicate_base64(self):
        result = {
            "ok": True,
            "action": "read_file",
            "path": "assets/example.png",
            "binary": True,
            "visual": True,
            "mime": "image/png",
            "base64": "aW1hZ2U=",
        }
        marker = server._agent_tool_vision_marker(result, "call-image")
        self.assertNotIn("aW1hZ2U=", json.dumps(marker))

    def test_parallel_visual_history_is_projected_as_one_complete_tool_block(self):
        def visual_result(encoded):
            return {
                "ok": True,
                "action": "read_file",
                "path": "assets/example.png",
                "binary": True,
                "visual": True,
                "mime": "image/png",
                "base64": encoded,
            }

        calls = [{
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": "{}"},
        } for call_id, name in (("call-a", "read_file"), ("call-b", "glob_files"))]
        result_a = visual_result("YQ==")
        result_b = visual_result("Yg==")
        messages = [
            {"role": "assistant", "content": "", "tool_calls": calls},
            {"role": "tool", "tool_call_id": "call-a", "name": "read_file", "content": "A"},
            server._agent_tool_vision_marker(result_a, "call-a"),
            {"role": "tool", "tool_call_id": "call-b", "name": "read_file", "content": "B"},
            server._agent_tool_vision_marker(result_b, "call-b"),
        ]
        before = json.dumps(messages, ensure_ascii=False)
        run = {
            "messages": messages,
            "tool_executions": {
                "call-a": {"status": "completed", "result": result_a},
                "call-b": {"status": "completed", "result": result_b},
            },
        }

        projected = server._agent_model_messages(run)

        self.assertEqual(json.dumps(messages, ensure_ascii=False), before)
        self.assertEqual(
            [message["role"] for message in projected],
            ["assistant", "tool", "tool", "user", "user"],
        )
        self.assertEqual(
            [projected[1]["tool_call_id"], projected[2]["tool_call_id"]],
            ["call-a", "call-b"],
        )
        self.assertTrue(projected[3]["content"][1]["image_url"]["url"].endswith("YQ=="))
        self.assertTrue(projected[4]["content"][1]["image_url"]["url"].endswith("Yg=="))

    def test_new_parallel_visual_writes_defer_markers_until_receipts_are_complete(self):
        calls = [{
            "id": call_id,
            "type": "function",
            "function": {"name": "read_file", "arguments": "{}"},
        } for call_id in ("call-a", "call-b")]
        visual = {
            "ok": True,
            "action": "read_file",
            "path": "assets/example.png",
            "binary": True,
            "visual": True,
            "mime": "image/png",
            "base64": "YQ==",
        }
        failed = {"ok": False, "action": "glob_files", "error": "missing"}
        run = {
            "messages": [{"role": "assistant", "content": "", "tool_calls": calls}],
            "pending_tool_calls": [{"id": "call-b"}],
            "tool_executions": {
                "call-a": {"status": "completed", "result": visual},
                "call-b": {"status": "completed", "result": failed},
            },
        }

        server._append_agent_tool_message_locked(run, "call-a", "read_file", visual)
        self.assertFalse(server._flush_agent_tool_vision_markers_locked(run))
        self.assertEqual([message["role"] for message in run["messages"]], ["assistant", "tool"])

        server._append_agent_tool_message_locked(run, "call-b", "glob_files", failed)
        run["pending_tool_calls"] = []
        self.assertTrue(server._flush_agent_tool_vision_markers_locked(run))
        self.assertEqual(
            [message["role"] for message in run["messages"]],
            ["assistant", "tool", "tool", "user"],
        )
        self.assertEqual(run["messages"][-1]["_agentToolVisionCallId"], "call-a")

    def test_protocol_recovery_uses_completed_execution_and_never_replays_unknown(self):
        calls = [{
            "id": call_id,
            "type": "function",
            "function": {"name": "read_file", "arguments": "{}"},
        } for call_id in ("call-a", "call-b", "call-c")]
        messages = [
            {"role": "assistant", "content": "", "tool_calls": calls},
            {"role": "tool", "tool_call_id": "call-a", "name": "read_file", "content": "A"},
        ]
        executions = {
            "call-b": {
                "status": "completed",
                "name": "read_file",
                "result": {"ok": True, "action": "read_file", "content": "B"},
            },
        }

        projected = server._agent_canonicalize_tool_protocol_messages(messages, executions)

        self.assertEqual([message["role"] for message in projected], ["assistant", "tool", "tool", "tool"])
        self.assertEqual(
            [message["tool_call_id"] for message in projected[1:]],
            ["call-a", "call-b", "call-c"],
        )
        self.assertTrue(json.loads(projected[2]["content"])["ok"])
        unknown = json.loads(projected[3]["content"])
        self.assertTrue(unknown["unknownState"])
        self.assertTrue(unknown["notReplayed"])

        identical_duplicate = messages + [dict(messages[1])]
        deduplicated = server._agent_canonicalize_tool_protocol_messages(
            identical_duplicate, executions,
        )
        self.assertEqual(sum(message.get("role") == "tool" for message in deduplicated), 3)

        conflicting = messages + [{
            "role": "tool",
            "tool_call_id": "call-a",
            "name": "read_file",
            "content": "different",
        }]
        with self.assertRaises(server.AgentToolProtocolError):
            server._agent_canonicalize_tool_protocol_messages(conflicting, executions)

        duplicate_call_ids = [{
            "id": "call-a",
            "type": "function",
            "function": {"name": "read_file", "arguments": "{}"},
        }, {
            "id": "call-a",
            "type": "function",
            "function": {"name": "glob_files", "arguments": "{}"},
        }]
        with self.assertRaises(server.AgentToolProtocolError):
            server._agent_canonicalize_tool_protocol_messages([{
                "role": "assistant",
                "content": "",
                "tool_calls": duplicate_call_ids,
            }])

        with self.assertRaises(server.AgentToolProtocolError):
            server._agent_canonicalize_tool_protocol_messages([{
                "role": "tool",
                "tool_call_id": "orphan-call",
                "name": "read_file",
                "content": "preserved evidence",
            }])

    def test_model_image_projection_accepts_or_converts_supported_matrix(self):
        for image_format, expected_mime, converted in (
            ("PNG", "image/png", False),
            ("JPEG", "image/jpeg", False),
            ("WEBP", "image/webp", False),
            ("BMP", "image/png", True),
            ("GIF", "image/png", True),
            ("ICO", "image/png", True),
            ("TIFF", "image/png", True),
        ):
            with self.subTest(image_format=image_format):
                result = server._normalize_model_image_bytes(
                    self._image_bytes(image_format),
                    "image/x-icon",
                )
                self.assertTrue(result["ok"], result.get("error"))
                self.assertEqual(result["mime"], expected_mime)
                self.assertEqual(result["converted"], converted)

    def test_model_payload_projection_repairs_mime_without_mutating_history(self):
        encoded = base64.b64encode(self._image_bytes("ICO")).decode("ascii")
        payload = {
            "model": "gpt-test",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "inspect"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/x-icon;base64,{encoded}"},
                    },
                ],
            }],
        }
        before = json.dumps(payload, ensure_ascii=False)

        projected = server._project_model_payload_images(payload)

        self.assertEqual(json.dumps(payload, ensure_ascii=False), before)
        image_url = projected["messages"][0]["content"][1]["image_url"]["url"]
        self.assertTrue(image_url.startswith("data:image/png;base64,"))

    def test_model_payload_projection_omits_invalid_data_image_non_destructively(self):
        payload = {
            "messages": [{
                "role": "user",
                "content": [{
                    "type": "image_url",
                    "image_url": {"url": "data:image/x-icon;base64,not-valid"},
                }],
            }],
        }

        projected = server._project_model_payload_images(payload)

        self.assertEqual(
            payload["messages"][0]["content"][0]["image_url"]["url"],
            "data:image/x-icon;base64,not-valid",
        )
        self.assertEqual(projected["messages"][0]["content"][0]["type"], "text")
        self.assertIn("original conversation history is unchanged", projected["messages"][0]["content"][0]["text"])

    def test_all_upstream_chat_paths_apply_model_image_projection(self):
        self.assertIn(
            "_project_model_payload_images(run[\"payload\"])",
            inspect.getsource(server._model_runtime_worker),
        )
        self.assertIn(
            "_project_model_payload_images(parsed_body)",
            inspect.getsource(server.CodeHandler.proxy),
        )


class TestTiffAttachmentPreviewPolicy(unittest.TestCase):
    @staticmethod
    def _tiff_bytes(size=(17, 11), mode="RGB"):
        from PIL import Image

        image = Image.new(mode, size, 1 if mode == "1" else (25, 90, 180))
        output = io.BytesIO()
        options = {"compression": "group4"} if mode == "1" else {}
        image.save(output, format="TIFF", **options)
        return output.getvalue()

    def test_tiff_preview_is_decodable_png_without_mutating_source(self):
        from PIL import Image

        source = self._tiff_bytes()
        before_hash = hashlib.sha256(source).hexdigest()

        preview = server._derive_tiff_preview_png(source, "image/tiff")

        self.assertEqual(hashlib.sha256(source).hexdigest(), before_hash)
        self.assertTrue(preview.startswith(bytes.fromhex("89504e470d0a1a0a")))
        with Image.open(io.BytesIO(preview)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (17, 11))

        wide_source = self._tiff_bytes((4096, 2))
        wide_preview = server._derive_tiff_preview_png(wide_source, "image/tiff")
        with Image.open(io.BytesIO(wide_preview)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertLessEqual(max(image.size), server.MODEL_INPUT_IMAGE_MAX_DIMENSION)

    def test_inline_preview_rejects_bad_base64_signature_size_pixels_and_damage(self):
        png = TestImageVisionBridge._image_bytes("PNG")
        cases = (
            (lambda: server._decode_tiff_preview_base64("%%%", "image/tiff"), "base64"),
            (
                lambda: server._decode_tiff_preview_base64(
                    base64.b64encode(png).decode("ascii"),
                    "image/tiff",
                ),
                "must be TIFF",
            ),
            (
                lambda: server._decode_tiff_preview_base64(
                    base64.b64encode(b"II*\x00broken").decode("ascii"),
                    "image/tiff",
                ),
                "conversion failed",
            ),
            (
                lambda: server._decode_tiff_preview_base64(
                    "A" * ((((server.MAX_ATTACHMENT_BYTES + 2) // 3) * 4) + 1),
                    "image/tiff",
                ),
                "size limit",
            ),
        )
        for operation, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ValueError, expected):
                    operation()

        oversized_pixels = self._tiff_bytes((5001, 5000), mode="1")
        self.assertLess(len(oversized_pixels), server.MAX_ATTACHMENT_BYTES)
        with self.assertRaisesRegex(ValueError, "dimensions exceed limit"):
            server._derive_tiff_preview_png(oversized_pixels, "image/tiff")

    def test_preview_failure_does_not_change_model_tiff_projection(self):
        source = self._tiff_bytes()
        data_url = f"data:image/tiff;base64,{base64.b64encode(source).decode('ascii')}"
        expected = server._project_model_image_url(data_url)

        with self.assertRaises(ValueError):
            server._derive_tiff_preview_png(b"II*\x00broken", "image/tiff")

        self.assertEqual(server._project_model_image_url(data_url), expected)
        self.assertTrue(expected.startswith("data:image/png;base64,"))


class TestExistingBrowserRefresh(unittest.TestCase):
    def test_launcher_detects_connected_browser(self):
        with mock.patch("urllib.request.urlopen", return_value=_Response({"hasBrowser": True})):
            self.assertTrue(launcher.has_existing_browser())

    def test_launcher_handles_unavailable_old_server(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertFalse(launcher.has_existing_browser())

    def test_formal_updater_can_force_existing_page_reuse(self):
        with mock.patch.object(launcher, "has_existing_browser", return_value=False):
            self.assertTrue(launcher.should_reuse_browser(argv=["Code.exe", "--reuse-browser"]))
            self.assertFalse(launcher.should_reuse_browser(argv=["Code.exe"]))

    def test_launcher_does_not_terminate_existing_processes(self):
        source = (ROOT / "launcher.py").read_text(encoding="utf-8")
        self.assertNotIn("def kill_existing", source)
        self.assertNotIn("taskkill", source)
        self.assertNotIn("Win32_Process", source)

    def test_frontend_refreshes_when_server_instance_changes(self):
        source = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("data.serverInstanceId !== browserServerInstanceId", source)
        self.assertIn("location.reload()", source)
        self.assertIn("applyInstanceIdentity(browserInstanceMode)", source)
        self.assertIn('_instanceProductName = isDev ? "Code Dev" : "Code"', source)
        self.assertIn('document.getElementById("productName")', source)
        self.assertIn('id="productName">Code</span>', (ROOT / "index.html").read_text(encoding="utf-8"))
        self.assertIn(
            "${_instanceProductName} · ${title}",
            source,
        )

if __name__ == "__main__":
    unittest.main()
