import json
import base64
import io
import inspect
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
            "messages": [marker],
            "tool_executions": {"call-image": {"result": result}},
        }

        messages = server._agent_model_messages(run)

        self.assertEqual(marker["_agentToolVisionCallId"], "call-image")
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"][1]["type"], "image_url")
        self.assertEqual(
            messages[0]["content"][1]["image_url"]["url"],
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

    def test_packaged_process_query_supports_versioned_executables(self):
        process_list = mock.Mock(stdout="101\n202\n", returncode=0)
        stopped = mock.Mock(returncode=0)
        with mock.patch.object(launcher.os, "getpid", return_value=101), \
             mock.patch.object(launcher.os, "getppid", return_value=100), \
             mock.patch.object(launcher.subprocess, "run", side_effect=[process_list, stopped]) as run:
            self.assertEqual(launcher.kill_existing(), 1)
        query = run.call_args_list[0].args[0][-1]
        self.assertIn("Code(?:-v[0-9.]+)?", query)
        self.assertEqual(run.call_args_list[1].args[0], ["taskkill", "/PID", "202", "/T", "/F"])

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
