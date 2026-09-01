import base64
import hashlib
import io
import json
from pathlib import Path
import shutil
import socket
import tempfile
import threading
import unittest
from unittest import mock

from PIL import Image

from code_runtime import image_runtime
from code_runtime.image_runtime import (
    GeneratedAssetRepository,
    ImageRouteRegistry,
    ImageRuntimeError,
    ImageUpstreamClient,
    PublicImageDownloader,
    ResolvedImageRoute,
    normalize_generate_request,
    validate_image_bytes,
)


def image_bytes(fmt="PNG", size=(4, 3), color=(20, 40, 60)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, body=b"", *, status=200, headers=None):
        self._body = io.BytesIO(body)
        self.status = status
        self.headers = headers or {}
        self.closed = False

    def read(self, size=-1):
        return self._body.read(size)

    def getheader(self, name):
        return self.headers.get(name)

    def close(self):
        self.closed = True


class ImageRouteRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "image-routes.json"
        self.registry = ImageRouteRegistry(self.path)
        self.secret = "IMAGE_SECRET_SENTINEL"
        self.private_url = "https://private-provider.invalid/v1"

    def tearDown(self):
        self.temp.cleanup()

    def connection(self, **overrides):
        record = {
            "connectionId": "image-alpha",
            "name": "Image Alpha",
            "baseUrl": self.private_url,
            "key": self.secret,
            "enabled": True,
            "models": [
                {"id": "image-model", "supportsEdit": True},
                "generate-only",
            ],
        }
        record.update(overrides)
        return record

    def test_catalog_is_secret_free_and_runtime_credentials_are_not_restartable(self):
        snapshot = self.registry.refresh([self.connection()])
        self.assertTrue(snapshot["ok"])
        self.assertEqual(len(snapshot["routes"]), 2)
        route = next(item for item in snapshot["routes"] if item["modelId"] == "image-model")
        self.assertRegex(route["routeRef"], r"^ir1_[a-f0-9]{64}$")
        self.assertEqual(
            set(route),
            {
                "routeRef", "connectionId", "label", "modelId",
                "supportsGeneration", "enabled",
                "credentialsAvailable",
            },
        )
        durable = self.path.read_text(encoding="utf-8")
        self.assertNotIn(self.secret, durable)
        self.assertNotIn(self.private_url, durable)

        resolved = self.registry.resolve(
            route["routeRef"], snapshot["catalogRevision"], "image-model",
        )
        self.assertEqual(resolved.key, self.secret)
        self.assertEqual(resolved.base_url, self.private_url)

        restarted = ImageRouteRegistry(self.path)
        restarted_snapshot = restarted.snapshot()
        self.assertFalse(next(
            item for item in restarted_snapshot["routes"]
            if item["routeRef"] == route["routeRef"]
        )["credentialsAvailable"])
        with self.assertRaises(ImageRuntimeError) as captured:
            restarted.resolve(route["routeRef"], snapshot["catalogRevision"], "image-model")
        self.assertEqual(captured.exception.code, "image_route_credentials_unavailable")

        rebound = restarted.refresh([self.connection()])
        self.assertEqual(rebound["catalogRevision"], snapshot["catalogRevision"])
        self.assertEqual(
            restarted.resolve(route["routeRef"], rebound["catalogRevision"], "image-model").key,
            self.secret,
        )
        rotated = restarted.refresh([self.connection(
            key="ROTATED_SECRET_SENTINEL",
            baseUrl="https://rotated-provider.invalid/v1",
        )])
        rotated_route = next(
            item for item in rotated["routes"] if item["modelId"] == "image-model"
        )
        self.assertEqual(rotated["catalogRevision"], rebound["catalogRevision"])
        self.assertEqual(rotated_route["routeRef"], route["routeRef"])
        rebound_runtime = restarted.resolve(
            route["routeRef"], rotated["catalogRevision"], "image-model",
        )
        self.assertEqual(rebound_runtime.key, "ROTATED_SECRET_SENTINEL")
        self.assertEqual(rebound_runtime.base_url, "https://rotated-provider.invalid/v1")
        durable_after_rotation = self.path.read_text(encoding="utf-8")
        self.assertNotIn("ROTATED_SECRET_SENTINEL", durable_after_rotation)
        self.assertNotIn("rotated-provider.invalid", durable_after_rotation)

    def test_legacy_durable_edit_capability_is_read_without_migration(self):
        initial = self.registry.refresh([self.connection(models=[{
            "id": "image-model",
            "supportsEdit": False,
        }])])
        legacy = json.loads(self.path.read_text(encoding="utf-8"))
        legacy["routes"][0]["supportsEdit"] = False
        self.path.write_text(
            json.dumps(legacy, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        before_load = self.path.read_bytes()

        restarted = ImageRouteRegistry(self.path)
        snapshot = restarted.snapshot()
        self.assertEqual(self.path.read_bytes(), before_load)
        self.assertNotIn("supportsEdit", snapshot["routes"][0])

        rebound = restarted.refresh([self.connection(models=[{
            "id": "image-model",
            "supportsEdit": True,
        }])])
        self.assertEqual(rebound["catalogRevision"], initial["catalogRevision"])
        self.assertEqual(rebound["routes"][0]["routeRef"], initial["routes"][0]["routeRef"])
        self.assertTrue(restarted.resolve(
            rebound["routes"][0]["routeRef"],
            rebound["catalogRevision"],
            "image-model",
        ).supports_edit)

    def test_stale_disabled_missing_and_invalid_connections_fail_closed(self):
        initial = self.registry.refresh([self.connection()])
        route = initial["routes"][0]
        changed = self.registry.refresh([
            self.connection(models=["image-model", "new-model"]),
        ])
        self.assertGreater(changed["catalogRevision"], initial["catalogRevision"])
        with self.assertRaises(ImageRuntimeError) as captured:
            self.registry.resolve(route["routeRef"], initial["catalogRevision"], route["modelId"])
        self.assertEqual(captured.exception.code, "image_route_stale")

        disabled = self.registry.refresh([self.connection(enabled=False)])
        disabled_route = next(item for item in disabled["routes"] if item["modelId"] == "image-model")
        with self.assertRaises(ImageRuntimeError) as captured:
            self.registry.resolve(
                disabled_route["routeRef"], disabled["catalogRevision"], "image-model",
            )
        self.assertEqual(captured.exception.code, "image_route_disabled")

        retained = self.registry.refresh([self.connection(key="")])
        self.assertEqual(retained["failedConnections"], 1)
        self.assertNotIn(self.secret, json.dumps(retained))
        with self.assertRaises(ImageRuntimeError) as captured:
            self.registry.resolve(
                disabled_route["routeRef"], retained["catalogRevision"], "image-model",
            )
        self.assertIn(captured.exception.code, {
            "image_route_disabled", "image_route_credentials_unavailable",
        })

        invalid = ImageRouteRegistry(Path(self.temp.name) / "invalid.json")
        result = invalid.refresh([self.connection(baseUrl="file:///private")])
        self.assertEqual(result["failures"][0]["code"], "image_route_invalid")


class ImageValidationTests(unittest.TestCase):
    def test_request_limits_and_reference_identity(self):
        normalized = normalize_generate_request({
            "prompt": "draw a safe fixture",
            "count": 4,
            "size": "1024x1536",
            "quality": "high",
            "outputFormat": "webp",
            "reference": {"type": "generated_asset", "id": "ga1_fixture"},
        })
        self.assertEqual(normalized["count"], 4)
        self.assertEqual(normalized["reference"]["type"], "generated_asset")
        for payload, code in (
            ({"prompt": ""}, "image_prompt_invalid"),
            ({"prompt": "x", "count": 5}, "image_count_invalid"),
            ({"prompt": "x", "size": "999x999"}, "image_size_invalid"),
            ({"prompt": "x", "quality": "ultra-secret"}, "image_quality_invalid"),
            ({"prompt": "x", "outputFormat": "gif"}, "image_format_invalid"),
            ({"prompt": "x", "reference": {"type": "url", "id": "https://x"}}, "image_reference_invalid"),
        ):
            with self.subTest(code=code), self.assertRaises(ImageRuntimeError) as captured:
                normalize_generate_request(payload)
            self.assertEqual(captured.exception.code, code)

    def test_signature_mime_pixels_and_damage_are_checked(self):
        png = image_bytes("PNG")
        valid = validate_image_bytes(png, "image/png")
        self.assertEqual((valid.width, valid.height), (4, 3))
        self.assertEqual(valid.mime_type, "image/png")
        with self.assertRaises(ImageRuntimeError) as captured:
            validate_image_bytes(png, "image/jpeg")
        self.assertEqual(captured.exception.code, "image_response_mime_mismatch")
        with mock.patch.object(image_runtime, "MAX_IMAGE_PIXELS", 5):
            with self.assertRaises(ImageRuntimeError) as captured:
                validate_image_bytes(png)
        self.assertEqual(captured.exception.code, "image_response_pixels_invalid")
        with self.assertRaises(ImageRuntimeError) as captured:
            validate_image_bytes(png[:20])
        self.assertIn(captured.exception.code, {
            "image_response_corrupt", "image_response_mime_mismatch",
        })
        with self.assertRaises(ImageRuntimeError) as captured:
            validate_image_bytes(b"not-an-image")
        self.assertEqual(captured.exception.code, "image_response_invalid")


class ImageUpstreamClientTests(unittest.TestCase):
    def setUp(self):
        self.route = ResolvedImageRoute(
            route_ref="ir1_" + "a" * 64,
            catalog_revision=3,
            connection_id="image-alpha",
            label="Image Alpha",
            model_id="image-model",
            supports_generation=True,
            supports_edit=True,
            base_url="https://provider.invalid/v1",
            key="SECRET_SENTINEL",
        )
        self.normalized = normalize_generate_request({
            "prompt": "draw fixture", "count": 1, "size": "auto",
            "quality": "auto", "outputFormat": "png",
        })

    def test_generation_uses_json_b64_and_idempotency_key(self):
        captured = {}
        png = image_bytes("PNG")

        def urlopen(req, timeout):
            captured.update({"request": req, "timeout": timeout})
            payload = json.dumps({"data": [{
                "b64_json": base64.b64encode(png).decode("ascii"),
                "url": "https://must-not-be-used.invalid/private",
            }]}).encode("utf-8")
            return FakeResponse(payload, headers={"Content-Length": str(len(payload))})

        result = ImageUpstreamClient(urlopen=urlopen).generate(
            self.route, self.normalized, "operation-1",
        )
        request_body = json.loads(captured["request"].data.decode("utf-8"))
        self.assertTrue(captured["request"].full_url.endswith("/v1/images/generations"))
        self.assertEqual(request_body["response_format"], "b64_json")
        self.assertEqual(request_body["n"], 1)
        self.assertNotIn("size", request_body)
        self.assertNotIn("quality", request_body)
        self.assertEqual(captured["request"].get_header("Idempotency-key"), "operation-1")
        self.assertEqual(result[0].mime_type, "image/png")

    def test_direct_multi_image_upstream_request_is_rejected_before_dispatch(self):
        dispatched = []
        normalized = normalize_generate_request({
            "prompt": "runtime must split this batch",
            "count": 4,
        })

        client = ImageUpstreamClient(
            urlopen=lambda *_args, **_kwargs: dispatched.append(True),
        )
        for reference in (None, validate_image_bytes(image_bytes("PNG"))):
            with self.subTest(reference=reference is not None), self.assertRaises(ImageRuntimeError) as captured:
                client.generate(
                    self.route,
                    normalized,
                    "operation-must-not-dispatch",
                    reference_image=reference,
                )
            self.assertEqual(captured.exception.code, "image_batch_required")
        self.assertEqual(dispatched, [])

    def test_default_and_max_timeout_allow_simulated_66_second_completion(self):
        self.assertEqual(image_runtime.IMAGE_TIMEOUT_SECONDS, 180)
        png = image_bytes("PNG")
        payload = json.dumps({"data": [{
            "b64_json": base64.b64encode(png).decode("ascii"),
        }]}).encode("utf-8")

        for label, timeout_kwargs in (
            ("default", {}),
            ("maximum", {"timeout": 999}),
        ):
            with self.subTest(timeout=label):
                now = {"value": 0.0}
                observed = []

                def clock():
                    return now["value"]

                def urlopen(req, timeout):
                    observed.append(timeout)
                    now["value"] = 66.0
                    return FakeResponse(payload)

                result = ImageUpstreamClient(
                    urlopen=urlopen,
                    clock=clock,
                ).generate(
                    self.route,
                    self.normalized,
                    f"operation-66-seconds-{label}",
                    **timeout_kwargs,
                )
                self.assertEqual(observed, [180])
                self.assertEqual(result[0].mime_type, "image/png")

    def test_response_read_and_url_fallback_share_total_deadline(self):
        png = validate_image_bytes(image_bytes("PNG"))
        encoded_payload = json.dumps({"data": [{
            "b64_json": base64.b64encode(png.data).decode("ascii"),
        }]}).encode("utf-8")
        now = {"value": 0.0}
        response_socket = mock.Mock()
        response = FakeResponse(encoded_payload)
        response.fp = mock.Mock()
        response.fp.raw = mock.Mock()
        response.fp.raw._sock = response_socket

        def clock():
            return now["value"]

        def response_after_40_seconds(req, timeout):
            self.assertEqual(timeout, 180)
            now["value"] = 40.0
            return response

        result = ImageUpstreamClient(
            urlopen=response_after_40_seconds,
            clock=clock,
        ).generate(
            self.route,
            self.normalized,
            "operation-response-read-budget",
        )
        response_socket.settimeout.assert_any_call(140.0)
        self.assertEqual(result[0].sha256, png.sha256)

        now["value"] = 0.0
        slow_socket = mock.Mock()

        class SlowResponse(FakeResponse):
            def __init__(self):
                super().__init__(encoded_payload)
                self.fp = mock.Mock()
                self.fp.raw = mock.Mock()
                self.fp.raw._sock = slow_socket

            def read(self, size=-1):
                now["value"] = 181.0
                return super().read(size)

        def response_finishes_after_deadline(req, timeout):
            self.assertEqual(timeout, 180)
            return SlowResponse()

        with self.assertRaises(ImageRuntimeError) as captured:
            ImageUpstreamClient(
                urlopen=response_finishes_after_deadline,
                clock=clock,
            ).generate(
                self.route,
                self.normalized,
                "operation-response-read-timeout",
            )
        self.assertEqual(captured.exception.code, "image_upstream_timeout")
        self.assertTrue(captured.exception.outcome_unknown)
        self.assertTrue(captured.exception.public_payload()["notReplayed"])
        slow_socket.settimeout.assert_called_once_with(180.0)

        for finished_at, expected_code in (
            (179.0, ""),
            (181.0, "image_upstream_timeout"),
        ):
            with self.subTest(url_fallback_finished_at=finished_at):
                now = {"value": 0.0}
                downloader = mock.Mock()

                def urlopen(req, timeout):
                    self.assertEqual(timeout, 180)
                    now["value"] = 66.0
                    return FakeResponse(json.dumps({"data": [{
                        "url": "https://public.invalid/generated.png",
                    }]}).encode("utf-8"))

                def download(url, *, timeout):
                    self.assertEqual(timeout, 114.0)
                    now["value"] = finished_at
                    return png

                downloader.fetch.side_effect = download
                client = ImageUpstreamClient(
                    urlopen=urlopen,
                    downloader=downloader,
                    clock=lambda: now["value"],
                )
                if expected_code:
                    with self.assertRaises(ImageRuntimeError) as captured:
                        client.generate(
                            self.route,
                            self.normalized,
                            f"operation-url-deadline-{finished_at}",
                        )
                    self.assertEqual(captured.exception.code, expected_code)
                    self.assertTrue(captured.exception.outcome_unknown)
                    self.assertTrue(captured.exception.public_payload()["notReplayed"])
                else:
                    result = client.generate(
                        self.route,
                        self.normalized,
                        f"operation-url-deadline-{finished_at}",
                    )
                    self.assertEqual(result[0].sha256, png.sha256)
                downloader.fetch.assert_called_once()

    def test_edit_uses_single_multipart_reference(self):
        captured = {}
        output = image_bytes("WEBP")
        reference = validate_image_bytes(image_bytes("JPEG"))

        def urlopen(req, timeout):
            captured["request"] = req
            payload = json.dumps({"data": [{
                "b64_json": base64.b64encode(output).decode("ascii"),
            }]}).encode("utf-8")
            return FakeResponse(payload)

        normalized = {**self.normalized, "reference": {"type": "attachment", "id": "attachments/ref.jpg"}, "outputFormat": "webp"}
        result = ImageUpstreamClient(urlopen=urlopen).generate(
            self.route, normalized, "operation-edit", reference_image=reference,
        )
        req = captured["request"]
        self.assertTrue(req.full_url.endswith("/v1/images/edits"))
        self.assertIn("multipart/form-data", req.get_header("Content-type"))
        self.assertEqual(req.data.count(b'name="image"'), 1)
        self.assertNotIn(b'name="size"', req.data)
        self.assertNotIn(b'name="quality"', req.data)
        self.assertNotIn(b"SECRET_SENTINEL", req.data)
        self.assertEqual(result[0].mime_type, "image/webp")

    def test_edit_ignores_legacy_capability_values(self):
        reference = validate_image_bytes(image_bytes("JPEG"))
        output = image_bytes("WEBP")
        normalized = {
            **self.normalized,
            "reference": {"type": "attachment", "id": "attachments/ref.jpg"},
            "outputFormat": "webp",
        }

        for label, model in (
            ("false", {"id": "image-model", "supportsEdit": False}),
            ("missing", {"id": "image-model"}),
            ("true", {"id": "image-model", "supportsEdit": True}),
        ):
            with self.subTest(legacy_capability=label), tempfile.TemporaryDirectory() as root:
                registry = ImageRouteRegistry(Path(root) / "routes.json")
                catalog = registry.refresh([{
                    "connectionId": "legacy-image",
                    "name": "Legacy image",
                    "baseUrl": "https://provider.invalid/v1",
                    "key": "SECRET_SENTINEL",
                    "models": [model],
                }])
                route = registry.resolve(
                    catalog["routes"][0]["routeRef"],
                    catalog["catalogRevision"],
                    "image-model",
                )
                requests = []

                def urlopen(req, timeout):
                    requests.append(req)
                    payload = json.dumps({"data": [{
                        "b64_json": base64.b64encode(output).decode("ascii"),
                    }]}).encode("utf-8")
                    return FakeResponse(payload)

                result = ImageUpstreamClient(urlopen=urlopen).generate(
                    route,
                    normalized,
                    f"operation-edit-{label}",
                    reference_image=reference,
                )
                self.assertEqual(len(requests), 1)
                self.assertTrue(requests[0].full_url.endswith("/v1/images/edits"))
                self.assertEqual(result[0].mime_type, "image/webp")

    def test_unimplemented_edit_endpoint_is_stable_and_not_replayed(self):
        reference = validate_image_bytes(image_bytes("JPEG"))
        normalized = {
            **self.normalized,
            "reference": {"type": "attachment", "id": "attachments/ref.jpg"},
        }

        for status in (404, 405, 501):
            calls = []

            def unsupported(req, timeout, status=status):
                calls.append(req)
                raise image_runtime.error.HTTPError(
                    req.full_url,
                    status,
                    "UNSUPPORTED_EDIT_SECRET_SENTINEL",
                    {},
                    None,
                )

            with self.subTest(status=status), self.assertRaises(ImageRuntimeError) as captured:
                ImageUpstreamClient(urlopen=unsupported).generate(
                    self.route,
                    normalized,
                    f"operation-unsupported-{status}",
                    reference_image=reference,
                )
            payload = captured.exception.public_payload()
            self.assertEqual(captured.exception.code, "image_edit_unsupported")
            self.assertFalse(captured.exception.retryable)
            self.assertTrue(captured.exception.outcome_unknown)
            self.assertTrue(payload["notReplayed"])
            self.assertNotIn("SECRET_SENTINEL", json.dumps(payload))
            self.assertEqual(len(calls), 1)

    def test_generation_and_edit_reject_paid_format_or_size_mismatch(self):
        png = image_bytes("PNG")

        def returns_png(req, timeout):
            payload = json.dumps({"data": [{
                "b64_json": base64.b64encode(png).decode("ascii"),
            }]}).encode("utf-8")
            return FakeResponse(payload)

        client = ImageUpstreamClient(urlopen=returns_png)
        for normalized, code in (
            ({**self.normalized, "outputFormat": "webp"}, "image_response_format_mismatch"),
            ({**self.normalized, "size": "512x512"}, "image_response_size_mismatch"),
        ):
            with self.subTest(code=code), self.assertRaises(ImageRuntimeError) as captured:
                client.generate(self.route, normalized, f"operation-{code}")
            self.assertEqual(captured.exception.code, code)
            self.assertTrue(captured.exception.outcome_unknown)
            self.assertTrue(captured.exception.public_payload()["notReplayed"])

        reference = validate_image_bytes(image_bytes("JPEG"))
        edit_request = {
            **self.normalized,
            "reference": {"type": "attachment", "id": "attachments/ref.jpg"},
            "outputFormat": "webp",
        }
        with self.assertRaises(ImageRuntimeError) as captured:
            client.generate(
                self.route,
                edit_request,
                "operation-edit-format-mismatch",
                reference_image=reference,
            )
        self.assertEqual(captured.exception.code, "image_response_format_mismatch")
        self.assertTrue(captured.exception.outcome_unknown)

    def test_jpeg_mapping_and_exact_fixed_size_are_accepted(self):
        cases = [
            ("JPEG", (4, 3), {**self.normalized, "outputFormat": "jpeg"}, "image/jpeg"),
            ("PNG", (512, 512), {**self.normalized, "size": "512x512"}, "image/png"),
        ]
        for image_format, size, normalized, expected_mime in cases:
            payload_bytes = image_bytes(image_format, size=size)

            def returns_expected(req, timeout, payload_bytes=payload_bytes):
                payload = json.dumps({"data": [{
                    "b64_json": base64.b64encode(payload_bytes).decode("ascii"),
                }]}).encode("utf-8")
                return FakeResponse(payload)

            with self.subTest(image_format=image_format, size=size):
                result = ImageUpstreamClient(urlopen=returns_expected).generate(
                    self.route,
                    normalized,
                    f"operation-{image_format.lower()}-{size[0]}x{size[1]}",
                )
            self.assertEqual(result[0].mime_type, expected_mime)
            self.assertEqual((result[0].width, result[0].height), size)

    def test_url_response_is_consumed_server_side_and_errors_are_secret_free(self):
        png = validate_image_bytes(image_bytes("PNG"))
        downloader = mock.Mock()
        downloader.fetch.return_value = png

        def urlopen(req, timeout):
            return FakeResponse(json.dumps({"data": [{
                "url": "https://public.invalid/image.png?secret=URL_SECRET",
            }]}).encode("utf-8"))

        result = ImageUpstreamClient(urlopen=urlopen, downloader=downloader).generate(
            self.route, self.normalized, "operation-url",
        )
        self.assertEqual(result[0].sha256, png.sha256)
        downloader.fetch.assert_called_once()

        for normalized, code in (
            ({**self.normalized, "outputFormat": "webp"}, "image_response_format_mismatch"),
            ({**self.normalized, "size": "512x512"}, "image_response_size_mismatch"),
        ):
            with self.subTest(url_contract=code), self.assertRaises(ImageRuntimeError) as captured:
                ImageUpstreamClient(urlopen=urlopen, downloader=downloader).generate(
                    self.route, normalized, f"operation-url-{code}",
                )
            self.assertEqual(captured.exception.code, code)
            self.assertTrue(captured.exception.outcome_unknown)
            self.assertTrue(captured.exception.public_payload()["notReplayed"])

        def failed(req, timeout):
            raise image_runtime.error.HTTPError(req.full_url, 403, "forbidden SECRET", {}, None)

        with self.assertRaises(ImageRuntimeError) as captured:
            ImageUpstreamClient(urlopen=failed).generate(
                self.route, self.normalized, "operation-failed",
            )
        payload = json.dumps(captured.exception.public_payload())
        self.assertEqual(captured.exception.code, "image_credentials_rejected")
        self.assertNotIn("SECRET", payload)
        self.assertNotIn("provider.invalid", payload)

        downloader.fetch.side_effect = ImageRuntimeError(
            "image_download_failed", "Generated image download failed.", retryable=True,
        )
        with self.assertRaises(ImageRuntimeError) as captured:
            ImageUpstreamClient(urlopen=urlopen, downloader=downloader).generate(
                self.route, self.normalized, "operation-url-download-failed",
            )
        self.assertEqual(captured.exception.code, "image_download_failed")
        self.assertTrue(captured.exception.outcome_unknown)
        self.assertTrue(captured.exception.public_payload()["notReplayed"])

    def test_timeout_and_network_failure_are_outcome_unknown(self):
        for failure, code in (
            (TimeoutError("SECRET timeout"), "image_upstream_timeout"),
            (image_runtime.error.URLError("SECRET network"), "image_upstream_network_error"),
        ):
            def urlopen(req, timeout, failure=failure):
                raise failure
            with self.subTest(code=code), self.assertRaises(ImageRuntimeError) as captured:
                ImageUpstreamClient(urlopen=urlopen).generate(
                    self.route, self.normalized, "operation-unknown",
                )
            self.assertEqual(captured.exception.code, code)
            self.assertTrue(captured.exception.outcome_unknown)
            public_payload = captured.exception.public_payload()
            self.assertNotIn("SECRET", json.dumps(public_payload))
            if code == "image_upstream_timeout":
                message = str(public_payload.get("error") or "").lower()
                self.assertIn("delivery", message)
                self.assertIn("result", message)
                self.assertNotIn("dispatch", message)
                self.assertNotIn("submitted", message)
                self.assertNotIn("received", message)
                self.assertTrue(public_payload["outcomeUnknown"])
                self.assertTrue(public_payload["notReplayed"])
        http_timeout = ImageUpstreamClient._http_error(504).public_payload()
        self.assertEqual(http_timeout["errorCode"], "image_upstream_timeout")
        self.assertIn("delivery", http_timeout["error"].lower())
        self.assertIn("result", http_timeout["error"].lower())
        self.assertNotIn("dispatch", http_timeout["error"].lower())
        self.assertTrue(http_timeout["outcomeUnknown"])
        self.assertTrue(http_timeout["notReplayed"])

    def test_cancel_before_dispatch_is_safe_and_after_response_is_outcome_unknown(self):
        cancelled = threading.Event()
        cancelled.set()
        opener = mock.Mock()
        with self.assertRaises(ImageRuntimeError) as captured:
            ImageUpstreamClient(urlopen=opener).generate(
                self.route,
                self.normalized,
                "operation-cancel-before",
                cancel_event=cancelled,
            )
        self.assertEqual(captured.exception.code, "image_cancelled")
        self.assertFalse(captured.exception.outcome_unknown)
        opener.assert_not_called()

        cancelled.clear()
        png = image_bytes("PNG")

        def completes_after_cancel(req, timeout):
            cancelled.set()
            payload = json.dumps({"data": [{
                "b64_json": base64.b64encode(png).decode("ascii"),
            }]}).encode("utf-8")
            return FakeResponse(payload)

        with self.assertRaises(ImageRuntimeError) as captured:
            ImageUpstreamClient(urlopen=completes_after_cancel).generate(
                self.route,
                self.normalized,
                "operation-cancel-after",
                cancel_event=cancelled,
            )
        self.assertEqual(captured.exception.code, "image_cancelled")
        self.assertTrue(captured.exception.outcome_unknown)

    def test_response_processing_shares_one_total_timeout_budget(self):
        png = image_bytes("PNG")

        def immediate(req, timeout):
            payload = json.dumps({"data": [{
                "b64_json": base64.b64encode(png).decode("ascii"),
            }]}).encode("utf-8")
            return FakeResponse(payload)

        clock = mock.Mock(side_effect=[0.0, 2.0])
        with self.assertRaises(ImageRuntimeError) as captured:
            ImageUpstreamClient(urlopen=immediate, clock=clock).generate(
                self.route,
                self.normalized,
                "operation-total-timeout",
                timeout=1,
            )
        self.assertEqual(captured.exception.code, "image_upstream_timeout")
        self.assertTrue(captured.exception.outcome_unknown)


class PublicDownloaderTests(unittest.TestCase):
    class Connection:
        def __init__(self, responses):
            self.responses = responses
            self.sock = None
            self.headers = {}

        def putrequest(self, method, target, **kwargs):
            self.target = target

        def putheader(self, name, value):
            self.headers[name] = value

        def endheaders(self):
            pass

        def getresponse(self):
            return self.responses.pop(0)

        def close(self):
            pass

    @staticmethod
    def public_resolver(host, port, *args):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port))]

    def test_private_dns_and_redirect_downgrade_are_blocked(self):
        def private_resolver(host, port, *args):
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", port))]

        downloader = PublicImageDownloader(resolver=private_resolver)
        with self.assertRaises(ImageRuntimeError) as captured:
            downloader.fetch("https://example.com/image.png")
        self.assertEqual(captured.exception.code, "image_download_ssrf_blocked")

        responses = [FakeResponse(status=302, headers={"Location": "http://example.com/image.png"})]
        connection = self.Connection(responses)
        downloader = PublicImageDownloader(
            resolver=self.public_resolver,
            connection_factory=lambda **kwargs: connection,
        )
        with self.assertRaises(ImageRuntimeError) as captured:
            downloader.fetch("https://example.com/start")
        self.assertEqual(captured.exception.code, "image_download_redirect_blocked")

    def test_public_image_is_bounded_and_validated(self):
        png = image_bytes("PNG")
        response = FakeResponse(
            png,
            headers={"Content-Type": "image/png", "Content-Length": str(len(png))},
        )
        connection = self.Connection([response])
        downloader = PublicImageDownloader(
            resolver=self.public_resolver,
            connection_factory=lambda **kwargs: connection,
        )
        result = downloader.fetch("https://example.com/image.png")
        self.assertEqual(result.mime_type, "image/png")
        self.assertEqual(connection.headers["Host"], "example.com")

        missing_mime = self.Connection([
            FakeResponse(png, headers={"Content-Length": str(len(png))}),
        ])
        downloader = PublicImageDownloader(
            resolver=self.public_resolver,
            connection_factory=lambda **kwargs: missing_mime,
        )
        with self.assertRaises(ImageRuntimeError) as captured:
            downloader.fetch("https://example.com/image.png")
        self.assertEqual(captured.exception.code, "image_response_mime_invalid")


class GeneratedAssetRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "generated-assets"
        self.repository = GeneratedAssetRepository(self.root)
        self.images = [validate_image_bytes(image_bytes("PNG"))]

    def tearDown(self):
        self.temp.cleanup()

    def test_assets_are_opaque_owned_restartable_and_exactly_once(self):
        result = self.repository.save_operation(
            "operation-1", "session-a", "run-a", "call-a", self.images,
            created_at="2026-08-28T00:00:00Z",
        )
        asset = result["assets"][0]
        self.assertRegex(asset["assetId"], r"^ga1_[A-Za-z0-9_-]{32,96}$")
        self.assertEqual(asset["url"], f"/api/sessions/session-a/generated-assets/{asset['assetId']}")
        durable = "".join(path.read_text(encoding="utf-8") for path in self.root.rglob("*.json"))
        self.assertNotIn(str(self.root.resolve()), durable)
        self.assertNotIn("SECRET", durable)

        restarted = GeneratedAssetRepository(self.root)
        replay = restarted.find_operation_result(
            "operation-1", "session-a", "run-a", "call-a", 1,
        )
        self.assertTrue(replay["replayed"])
        data, meta = restarted.read("session-a", asset["assetId"])
        self.assertEqual(hashlib.sha256(data).hexdigest(), meta["sha256"])
        with self.assertRaises(ImageRuntimeError) as captured:
            restarted.read("session-b", asset["assetId"])
        self.assertEqual(captured.exception.code, "generated_asset_forbidden")

        with self.assertRaises(ImageRuntimeError) as captured:
            restarted.find_operation_result(
                "operation-1", "session-a", "run-a", "call-a", 2,
            )
        self.assertEqual(captured.exception.code, "image_operation_partial")
        self.assertTrue(captured.exception.outcome_unknown)
        self.assertTrue(restarted.read("session-a", asset["assetId"])[0])

    def test_session_cleanup_never_removes_other_session_assets(self):
        first = self.repository.save_operation(
            "operation-a", "session-a", "run-a", "call-a", self.images,
            created_at="2026-08-28T00:00:00Z",
        )
        second = self.repository.save_operation(
            "operation-b", "session-b", "run-b", "call-b", self.images,
            created_at="2026-08-28T00:00:00Z",
        )
        self.assertEqual(self.repository.delete_session_assets("session-a"), 1)
        with self.assertRaises(ImageRuntimeError):
            self.repository.read("session-a", first["assets"][0]["assetId"])
        self.assertTrue(self.repository.read("session-b", second["assets"][0]["assetId"])[0])
        self.assertEqual(self.repository.delete_session_assets("session-a"), 0)

    def test_session_cleanup_restores_all_assets_after_partial_filesystem_failure(self):
        first = self.repository.save_operation(
            "operation-a", "session-a", "run-a", "call-a", self.images,
            created_at="2026-08-28T00:00:00Z",
        )
        second = self.repository.save_operation(
            "operation-b", "session-a", "run-b", "call-b", self.images,
            created_at="2026-08-28T00:00:00Z",
        )
        original_rmtree = shutil.rmtree
        calls = 0

        def fail_second_delete(path, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise PermissionError(13, "Permission denied", "generated-asset")
            return original_rmtree(path, *args, **kwargs)

        with mock.patch("code_runtime.image_runtime.shutil.rmtree", side_effect=fail_second_delete):
            with self.assertRaises(ImageRuntimeError) as captured:
                self.repository.delete_session_assets("session-a")

        self.assertEqual(captured.exception.code, "generated_asset_cleanup_failed")
        self.assertTrue(self.repository.read("session-a", first["assets"][0]["assetId"])[0])
        self.assertTrue(self.repository.read("session-a", second["assets"][0]["assetId"])[0])


if __name__ == "__main__":
    unittest.main()
