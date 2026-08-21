"""Server-owned model runtime regression tests.

Run: python -m pytest tests/test_model_runtime.py -v
"""

import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import server as server_mod


_H3_2C1_SUITE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "harness"
    / "upstream-failure-recovery-trace-suite.json"
)


def _load_h3_2c1_evidence_fixtures():
    suite = json.loads(_H3_2C1_SUITE_PATH.read_text(encoding="utf-8"))
    if suite.get("evidenceProfile") != {
        "id": "h3-2c1-upstream-failure-non-action",
        "version": 1,
        "replayPayload": "single-run-fixture-v1",
        "productionEvidence": "model-runtime-agent-run-integration-v1",
    }:
        raise AssertionError("unexpected H3-2C1 evidence profile")
    return suite["fixtures"]


class _StreamingUpstream(BaseHTTPRequestHandler):
    calls = 0
    authorizations = []
    evidence_case = None
    evidence_fallback_active = False

    def log_message(self, *_args):
        return

    def do_POST(self):
        type(self).calls += 1
        type(self).authorizations.append(self.headers.get("Authorization", ""))
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        user_content = (payload.get("messages") or [{}])[-1].get("content")
        evidence_case = type(self).evidence_case
        if evidence_case:
            facts = evidence_case["sourceFacts"]
            runtime_input = facts["runtimeInput"]
            if user_content == runtime_input["userContent"]:
                mode = runtime_input["responseMode"]
                fallback_succeeded = (
                    type(self).evidence_fallback_active
                    and facts["fallback"]["tested"]
                    and type(self).calls > 1
                )
                if mode == "http-error" and not fallback_succeeded:
                    body = json.dumps({
                        "error": {"message": runtime_input["httpMessage"]},
                    }).encode("utf-8")
                    self.send_response(runtime_input["httpStatus"])
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if mode == "first-response-timeout":
                    self.send_response(runtime_input["httpStatus"])
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.end_headers()
                    deadline = time.monotonic() + max(
                        float(runtime_input["timeoutSeconds"]) * 4,
                        0.3,
                    )
                    while time.monotonic() < deadline:
                        try:
                            self.wfile.write(b": synthetic keepalive\n\n")
                            self.wfile.flush()
                        except OSError:
                            return
                        time.sleep(0.01)
                    return
        if user_content == "always 502":
            body = json.dumps({
                "error": {
                    "message": "Upstream service temporarily unavailable",
                    "code": "upstream_error",
                },
            }).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        authorization = self.headers.get("Authorization", "")
        if (
            user_content == "key scoped context error"
            and authorization == "Bearer context-primary-key"
        ):
            body = json.dumps({
                "error": {
                    "message": (
                        "credential context-primary-key: maximum context length is 128000 tokens; "
                        "requested 150000 tokens; request id 20260821"
                    ),
                    "code": "context_length_exceeded",
                    "max_context_tokens": 128000,
                },
            }).encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if (
            user_content == "key scoped non-context error"
            and authorization == "Bearer fallback-primary-key"
        ):
            body = json.dumps({
                "error": {
                    "message": "Upstream service temporarily unavailable",
                    "code": "upstream_error",
                },
            }).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if user_content == "deny model":
            body = json.dumps({
                "error": {
                    "message": "该令牌无权访问模型 deepseek-v4-pro",
                    "code": "new_api_error",
                },
            }, ensure_ascii=False).encode("utf-8")
            self.send_response(403)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.end_headers()
        if user_content in {"keepalive only", "usage only"}:
            deadline = time.monotonic() + 0.6
            while time.monotonic() < deadline:
                try:
                    if user_content == "keepalive only":
                        self.wfile.write(b": keepalive\n\n")
                    else:
                        usage_frame = {
                            "choices": [],
                            "usage": {"prompt_tokens": 1, "total_tokens": 1},
                        }
                        self.wfile.write(
                            (
                                "data: "
                                + json.dumps(usage_frame)
                                + "\n\n"
                            ).encode("utf-8")
                        )
                    self.wfile.flush()
                except OSError:
                    return
                time.sleep(0.01)
            return
        if user_content == "content then pause":
            frame = {"choices": [{"delta": {"content": "started"}}]}
            self.wfile.write(
                ("data: " + json.dumps(frame) + "\n\n").encode("utf-8")
            )
            self.wfile.flush()
            time.sleep(0.2)
            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except OSError:
                pass
            return
        if user_content == "call a tool":
            frames = [
                {
                    "choices": [{
                        "delta": {
                            "reasoning_content": "checking files",
                            "tool_calls": [{
                                "index": 0,
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "read_", "arguments": "{\"pa"},
                            }],
                        },
                    }],
                },
                {
                    "choices": [{
                        "delta": {
                            "tool_calls": [{
                                "index": 0,
                                "function": {"name": "file", "arguments": "th\":\"README.md\"}"},
                            }],
                        },
                        "finish_reason": "tool_calls",
                    }],
                },
                {
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 7,
                        "completion_tokens": 4,
                        "total_tokens": 11,
                    },
                },
            ]
        else:
            frames = [
                {"choices": [{"delta": {"reasoning_content": "checking"}}]},
                {"choices": [{"delta": {"content": "hello"}, "finish_reason": "stop"}]},
                {
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 3,
                        "completion_tokens": 2,
                        "total_tokens": 5,
                    },
                },
            ]
        for frame in frames:
            self.wfile.write(
                ("data: " + json.dumps(frame, ensure_ascii=False) + "\n\n").encode("utf-8")
            )
            self.wfile.flush()
            time.sleep(0.01)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class TestModelRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _StreamingUpstream.calls = 0
        _StreamingUpstream.authorizations = []
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), _StreamingUpstream)
        cls.thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.upstream.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.upstream.shutdown()
        cls.upstream.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        _StreamingUpstream.calls = 0
        _StreamingUpstream.authorizations = []
        _StreamingUpstream.evidence_case = None
        _StreamingUpstream.evidence_fallback_active = False
        with server_mod._model_runtime_lock:
            server_mod._model_runtime_runs.clear()

    def _wait_for_terminal(self, run, timeout=3):
        deadline = time.time() + timeout
        with run["condition"]:
            while run["status"] == "running" and time.time() < deadline:
                run["condition"].wait(timeout=0.05)
        self.assertNotEqual(run["status"], "running")

    def test_same_run_can_be_replayed_without_second_upstream_request(self):
        run = server_mod._create_model_runtime_run(
            "session-a",
            {"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
            self.base_url,
            ["secret-test-key"],
        )
        self._wait_for_terminal(run)

        first_browser = server_mod._runtime_snapshot(run, 0)
        refreshed_browser = server_mod._runtime_snapshot(run, 0)

        self.assertEqual(run["status"], "completed")
        self.assertEqual(_StreamingUpstream.calls, 1)
        self.assertEqual(_StreamingUpstream.authorizations, ["Bearer secret-test-key"])
        self.assertEqual(first_browser["events"], refreshed_browser["events"])
        self.assertEqual(first_browser["events"][-1]["data"], "[DONE]")
        self.assertIn("hello", json.dumps(first_browser, ensure_ascii=False))
        self.assertEqual(first_browser["result"]["content"], "hello")
        self.assertEqual(first_browser["result"]["reasoning"], "checking")
        self.assertEqual(first_browser["result"]["finishReason"], "stop")
        self.assertEqual(first_browser["result"]["usage"]["total_tokens"], 5)

    def test_runtime_aggregates_split_tool_call_without_browser_parser(self):
        run = server_mod._create_model_runtime_run(
            "session-tool",
            {"model": "test-model", "messages": [{"role": "user", "content": "call a tool"}]},
            self.base_url,
            ["secret-test-key"],
        )
        self._wait_for_terminal(run)

        snapshot = server_mod._runtime_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["reasoning"], "checking files")
        self.assertEqual(snapshot["result"]["finishReason"], "tool_calls")
        self.assertEqual(snapshot["result"]["usage"]["total_tokens"], 11)
        self.assertEqual(snapshot["result"]["toolCalls"], [{
            "index": 0,
            "id": "call-1",
            "type": "function",
            "function": {"name": "read_file", "arguments": "{\"path\":\"README.md\"}"},
        }])

    def test_runtime_snapshot_never_exposes_credentials_or_request_payload(self):
        run = server_mod._create_model_runtime_run(
            "session-b",
            {"model": "test-model", "messages": [{"role": "user", "content": "private"}]},
            self.base_url,
            ["secret-test-key"],
        )
        self._wait_for_terminal(run)

        snapshot_text = json.dumps(server_mod._runtime_snapshot(run, 0), ensure_ascii=False)
        self.assertNotIn("secret-test-key", snapshot_text)
        self.assertNotIn("private", snapshot_text)
        self.assertEqual(run["keys"], [])
        self.assertEqual(run["payload"], {})

    def test_failed_upstream_yields_error_status_for_frontend_recovery(self):
        """When the upstream model returns a non-200 status, the agent run
        should become 'failed' so the frontend can trigger rollback."""
        run = server_mod._create_model_runtime_run(
            "session-error",
            {"model": "test-model", "messages": [{"role": "user", "content": "crash"}]},
            "http://127.0.0.1:1",  # unreachable — triggers connection error
            ["test-key"],
        )
        self._wait_for_terminal(run, timeout=8)
        self.assertEqual(run["status"], "failed")
        self.assertIn("error", run)
        self.assertTrue(run["error"], "error should contain failure reason")

    def test_model_access_denial_is_structured_and_not_transient(self):
        run = server_mod._create_model_runtime_run(
            "session-denied",
            {
                "model": "deepseek-v4-pro",
                "messages": [{"role": "user", "content": "deny model"}],
            },
            self.base_url,
            ["restricted-key-a", "restricted-key-b"],
        )
        self._wait_for_terminal(run)

        snapshot = server_mod._runtime_snapshot(run, 0)
        self.assertEqual(_StreamingUpstream.calls, 2)
        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["upstreamStatus"], 403)
        self.assertEqual(snapshot["errorCode"], "model_access_denied")
        self.assertFalse(snapshot["transient"])
        self.assertIn("无权访问模型", snapshot["error"])

    def test_transient_http_failure_is_structured_without_duplicate_retry(self):
        run = server_mod._create_model_runtime_run(
            "session-transient",
            {
                "model": "claude-opus-test",
                "messages": [{"role": "user", "content": "always 502"}],
            },
            self.base_url,
            ["authorized-key"],
        )
        self._wait_for_terminal(run)
        snapshot = server_mod._runtime_snapshot(run, 0)
        self.assertEqual(_StreamingUpstream.calls, 1)
        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["upstreamStatus"], 502)
        self.assertEqual(snapshot["errorCode"], "upstream_error")
        self.assertTrue(snapshot["transient"])
        self.assertEqual(snapshot["error"], "Upstream service temporarily unavailable")

    def test_h3_2c1_http_cases_consume_the_versioned_evidence_profile(self):
        fixtures = [
            fixture for fixture in _load_h3_2c1_evidence_fixtures()
            if fixture["sourceFacts"]["caseKind"] == "http-failure"
        ]
        for index, fixture in enumerate(fixtures):
            with self.subTest(fixture=fixture["name"]):
                facts = fixture["sourceFacts"]
                _StreamingUpstream.calls = 0
                _StreamingUpstream.evidence_case = fixture
                run = server_mod._create_model_runtime_run(
                    f"h3-2c1-runtime-http-{index}",
                    {
                        "model": "test-model",
                        "messages": [{
                            "role": "user",
                            "content": facts["runtimeInput"]["userContent"],
                        }],
                    },
                    self.base_url,
                    ["synthetic-test-key"],
                )
                self._wait_for_terminal(run)
                snapshot = server_mod._runtime_snapshot(run, 0)

                self.assertEqual(
                    snapshot["upstreamStatus"],
                    facts["upstreamStatus"],
                    f"$.fixtures[{index}].sourceFacts.upstreamStatus",
                )
                self.assertEqual(
                    snapshot["errorCode"],
                    facts["runtimeErrorCode"],
                    f"$.fixtures[{index}].sourceFacts.runtimeErrorCode",
                )
                self.assertEqual(
                    snapshot["transient"],
                    facts["runtimeTransient"],
                    f"$.fixtures[{index}].sourceFacts.runtimeTransient",
                )
                self.assertEqual(snapshot["error"], facts["upstreamMessage"])
                self.assertEqual(snapshot["status"], "failed")
                self.assertEqual(_StreamingUpstream.calls, 1)
                self.assertEqual(
                    server_mod._classify_runtime_failure(
                        facts["upstreamStatus"],
                        facts["upstreamMessage"],
                    ),
                    (facts["runtimeErrorCode"], facts["runtimeTransient"]),
                )

        self.assertEqual(
            server_mod._classify_runtime_failure(
                401,
                "Synthetic credential has no access to model synthetic-model.",
            ),
            ("model_access_denied", False),
        )

    def test_h3_2c1_first_response_timeout_consumes_the_same_case_data(self):
        fixture = next(
            item for item in _load_h3_2c1_evidence_fixtures()
            if item["sourceFacts"]["caseKind"] == "first-response-timeout"
        )
        facts = fixture["sourceFacts"]
        runtime_input = facts["runtimeInput"]
        _StreamingUpstream.evidence_case = fixture
        with mock.patch.object(
            server_mod,
            "_MODEL_RUNTIME_FIRST_RESPONSE_TIMEOUT",
            runtime_input["timeoutSeconds"],
        ):
            run = server_mod._create_model_runtime_run(
                "h3-2c1-runtime-timeout",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": runtime_input["userContent"]}],
                },
                self.base_url,
                ["synthetic-test-key"],
            )
            self._wait_for_terminal(run)
        snapshot = server_mod._runtime_snapshot(run, 0)

        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["upstreamStatus"], facts["upstreamStatus"], "$.sourceFacts.upstreamStatus")
        self.assertEqual(snapshot["errorCode"], facts["runtimeErrorCode"], "$.sourceFacts.runtimeErrorCode")
        self.assertEqual(snapshot["transient"], facts["runtimeTransient"], "$.sourceFacts.runtimeTransient")
        self.assertEqual(snapshot["error"], facts["upstreamMessage"])
        self.assertEqual(_StreamingUpstream.calls, 1)

    def test_h3_2c1_pre_event_multi_key_fallback_is_scoped_to_the_502_case(self):
        fixture = next(
            item for item in _load_h3_2c1_evidence_fixtures()
            if item["sourceFacts"]["fallback"]["tested"]
        )
        facts = fixture["sourceFacts"]
        fallback = facts["fallback"]
        self.assertEqual(facts["upstreamStatus"], 502)
        self.assertEqual(fallback["scope"], "representative-status-only")
        _StreamingUpstream.evidence_case = fixture
        _StreamingUpstream.evidence_fallback_active = True
        run = server_mod._create_model_runtime_run(
            "h3-2c1-runtime-fallback",
            {
                "model": "test-model",
                "messages": [{
                    "role": "user",
                    "content": facts["runtimeInput"]["userContent"],
                }],
            },
            self.base_url,
            ["synthetic-primary-key", "synthetic-secondary-key"],
        )
        self._wait_for_terminal(run)
        snapshot = server_mod._runtime_snapshot(run, 0)

        self.assertEqual(snapshot["status"], fallback["expectedRuntimeStatus"])
        self.assertEqual(_StreamingUpstream.calls, fallback["expectedCalls"])
        self.assertEqual(len(_StreamingUpstream.authorizations), fallback["keyCount"])
        self.assertEqual(snapshot["result"]["content"], "hello")
        self.assertEqual(snapshot["errorCode"], "")
        self.assertEqual(snapshot["events"][0]["seq"], 1)
        self.assertNotIn(facts["upstreamMessage"], json.dumps(snapshot, ensure_ascii=False))

    def test_strict_context_error_stops_on_actual_key_and_keeps_attribution_private(self):
        run = server_mod._create_model_runtime_run(
            "context-key-scope",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "key scoped context error"}],
            },
            self.base_url,
            ["context-primary-key", "context-secondary-key"],
        )
        self._wait_for_terminal(run)
        snapshot = server_mod._runtime_snapshot(run, 0)

        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["errorCode"], "context_window_exceeded")
        self.assertEqual(
            snapshot["error"],
            "The upstream rejected the request because it exceeded the model context window",
        )
        self.assertEqual(_StreamingUpstream.calls, 1)
        self.assertEqual(
            _StreamingUpstream.authorizations,
            ["Bearer context-primary-key"],
        )
        attribution = server_mod._runtime_context_failure_attribution(run)
        self.assertEqual(attribution["upstreamStatus"], 400)
        self.assertEqual(attribution["evidenceKind"], "explicit_max")
        self.assertEqual(attribution["explicitMaximumTokens"], 128000)
        self.assertEqual(
            attribution["keyFingerprint"],
            server_mod.context_calibration.key_fingerprint("context-primary-key"),
        )
        public_json = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("context-primary-key", public_json)
        self.assertNotIn("context-secondary-key", public_json)
        self.assertNotIn(attribution["keyFingerprint"], public_json)
        self.assertNotIn("20260821", public_json)
        self.assertNotIn("requested 150000", public_json)

    def test_non_context_failure_still_falls_back_to_second_key(self):
        run = server_mod._create_model_runtime_run(
            "non-context-key-scope",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "key scoped non-context error"}],
            },
            self.base_url,
            ["fallback-primary-key", "fallback-secondary-key"],
        )
        self._wait_for_terminal(run)
        snapshot = server_mod._runtime_snapshot(run, 0)

        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "hello")
        self.assertEqual(_StreamingUpstream.calls, 2)
        self.assertEqual(_StreamingUpstream.authorizations, [
            "Bearer fallback-primary-key",
            "Bearer fallback-secondary-key",
        ])
        self.assertIsNone(server_mod._runtime_context_failure_attribution(run))

    def test_first_response_timeout_ignores_keepalive_and_usage_only_events(self):
        for user_content in ("keepalive only", "usage only"):
            with self.subTest(user_content=user_content):
                with mock.patch.object(
                    server_mod,
                    "_MODEL_RUNTIME_FIRST_RESPONSE_TIMEOUT",
                    0.12,
                ):
                    started = time.monotonic()
                    run = server_mod._create_model_runtime_run(
                        "session-first-response-timeout",
                        {
                            "model": "test-model",
                            "messages": [{"role": "user", "content": user_content}],
                        },
                        self.base_url,
                        ["authorized-key"],
                    )
                    self._wait_for_terminal(run)
                    elapsed = time.monotonic() - started

                snapshot = server_mod._runtime_snapshot(run, 0)
                self.assertEqual(snapshot["status"], "failed")
                self.assertEqual(snapshot["errorCode"], "model_response_timeout")
                self.assertTrue(snapshot["transient"])
                self.assertIn("0.12 seconds", snapshot["error"])
                self.assertLess(elapsed, 0.5)
                self.assertEqual(snapshot["result"]["content"], "")
                self.assertEqual(snapshot["result"]["reasoning"], "")
                self.assertEqual(snapshot["result"]["toolCalls"], [])

    def test_meaningful_content_releases_first_response_deadline(self):
        with mock.patch.object(
            server_mod,
            "_MODEL_RUNTIME_FIRST_RESPONSE_TIMEOUT",
            0.08,
        ):
            started = time.monotonic()
            run = server_mod._create_model_runtime_run(
                "session-content-before-deadline",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "content then pause"}],
                },
                self.base_url,
                ["authorized-key"],
            )
            self._wait_for_terminal(run)
            elapsed = time.monotonic() - started

        snapshot = server_mod._runtime_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "started")
        self.assertGreater(elapsed, 0.15)


if __name__ == "__main__":
    unittest.main()
