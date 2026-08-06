"""Isolated loopback host for H4 browser tests.

The Code side uses the production CodeHandler unchanged. This process only
provides a deterministic loopback upstream, test-side instrumentation, and a
stdin control channel for readiness, metrics, release, and graceful shutdown.
"""

from __future__ import annotations

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
from urllib import parse


MODEL_ID = "h4-e2e-model"
PLAIN_USER = "H4_PLAIN_USER"
PLAIN_FINAL = "H4_PLAIN_FINAL"
TOOL_USER = "H4_TOOL_USER"
TOOL_STAGE = "H4_TOOL_STAGE"
TOOL_FINAL = "H4_TOOL_FINAL"
CLASSIC_USER = "H4_CLASSIC_USER"
CLASSIC_FINAL = "H4_CLASSIC_FINAL"
TOOL_CALL_ID = "h4-read-call-1"
READ_PATH = "fixture.txt"


class MetricState:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data = {
            "fakeRequests": [],
            "chatRequests": [],
            "toolExecutions": [],
            "productionToolDelegations": 0,
            "unsafeToolRequests": 0,
            "modelGateWaits": 0,
        }

    def append(self, key: str, value: dict) -> None:
        with self._lock:
            self._data[key].append(value)

    def increment(self, key: str) -> None:
        with self._lock:
            self._data[key] += 1

    def snapshot(self) -> dict:
        with self._lock:
            return deepcopy(self._data)


METRICS = MetricState()
MODEL_GATE = threading.Event()


def _message_text(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return str(content or "")


def _scenario_for(payload: dict) -> tuple[str, bool]:
    messages = payload.get("messages") or []
    user_text = ""
    has_tool_result = False
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") == "user":
            user_text = _message_text(message)
        if message.get("role") == "tool" or message.get("tool_call_id") == TOOL_CALL_ID:
            has_tool_result = True
    if TOOL_USER in user_text:
        return ("tool-final" if has_tool_result else "tool-call", has_tool_result)
    if CLASSIC_USER in user_text:
        return "classic-text", has_tool_result
    return "plain-text", has_tool_result


def _chunk(delta: dict, finish_reason=None, usage=None) -> dict:
    frame = {
        "id": "h4-chat",
        "object": "chat.completion.chunk",
        "created": 1_700_000_000,
        "model": MODEL_ID,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    if usage is not None:
        frame["usage"] = usage
    return frame


def _sse_payload(frames: list[dict]) -> bytes:
    lines = [f"data: {json.dumps(frame, separators=(',', ':'))}\n\n" for frame in frames]
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


class FakeUpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args) -> None:
        return

    def _read_json(self) -> dict:
        size = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(size) if size else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _record(self, kind: str) -> None:
        route = parse.urlparse(self.path).path
        METRICS.append("fakeRequests", {
            "method": self.command,
            "path": route,
            "kind": kind,
            "authorizationPresent": bool(self.headers.get("Authorization")),
        })

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        route = parse.urlparse(self.path).path
        if route == "/v1/models":
            self._record("models")
            self._send_json({"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]})
            return
        if route == "/api/token/":
            self._record("platform-sync")
            self._send_json({"data": {"items": [], "total": 0}})
            return
        if route == "/api/user/self":
            self._record("platform-auth")
            self._send_json({"data": {"id": 7, "username": "h4-user"}})
            return
        self._record("unexpected")
        self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        route = parse.urlparse(self.path).path
        if route == "/api/token/batch/keys":
            self._read_json()
            self._record("platform-sync")
            self._send_json({"data": {"keys": {}}})
            return
        if route != "/v1/chat/completions":
            self._record("unexpected")
            self._send_json({"error": "not found"}, 404)
            return

        payload = self._read_json()
        if payload.get("stream") is not True:
            self._record("unexpected-nonstream-chat")
            METRICS.append("chatRequests", {"scenario": "unexpected-nonstream", "stream": False})
            self._send_json({
                "choices": [{"message": {"role": "assistant", "content": "H4_TITLE"}}],
            })
            return

        scenario, has_tool_result = _scenario_for(payload)
        self._record("agent-chat")
        METRICS.append("chatRequests", {
            "scenario": scenario,
            "stream": True,
            "hasToolResult": has_tool_result,
        })
        current_chat_count = len(METRICS.snapshot()["chatRequests"])
        if current_chat_count == 1:
            METRICS.increment("modelGateWaits")
            if not MODEL_GATE.wait(timeout=10):
                self._send_json({"error": "model gate timeout"}, 504)
                return

        if scenario == "tool-call":
            frames = [
                _chunk({"role": "assistant", "content": TOOL_STAGE}),
                _chunk({
                    "tool_calls": [{
                        "index": 0,
                        "id": TOOL_CALL_ID,
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"path": READ_PATH}, separators=(",", ":")),
                        },
                    }],
                }),
                _chunk({}, "tool_calls", {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14}),
            ]
        else:
            final_text = {
                "plain-text": PLAIN_FINAL,
                "classic-text": CLASSIC_FINAL,
                "tool-final": TOOL_FINAL,
            }[scenario]
            frames = [
                _chunk({"role": "assistant", "content": final_text}),
                _chunk({}, "stop", {"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18}),
            ]

        data = _sse_payload(frames)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()


def _json_line(payload: dict) -> None:
    print(json.dumps(payload, separators=(",", ":")), flush=True)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: isolated_host.py <temporary-root>")
    root = Path(sys.argv[1]).resolve()
    data_dir = (root / "data").resolve()
    project_dir = (root / "project").resolve()
    artifacts_dir = (root / "artifacts").resolve()
    for candidate in (data_dir, project_dir, artifacts_dir):
        if root not in candidate.parents:
            raise RuntimeError("temporary path escaped the owned root")
        candidate.mkdir(parents=True, exist_ok=True)

    fake_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstreamHandler)
    fake_server.daemon_threads = True
    fake_port = fake_server.server_address[1]
    fake_url = f"http://127.0.0.1:{fake_port}"
    fake_thread = threading.Thread(target=fake_server.serve_forever, daemon=True)
    fake_thread.start()

    os.environ["CODE_DATA_DIR"] = str(data_dir)
    os.environ["CODE_PORT"] = "0"
    os.environ["CODE_INSTANCE_MODE"] = "release"
    os.environ["CODE_AGENT_PROTOCOL_SHADOW"] = "0"
    os.environ["CODE_AGENT_PROJECTION_SHADOW"] = "0"
    os.environ["CODE_AGENT_EVENT_PROTOCOL_V1"] = "1"
    os.environ["NEW_API_BASE_URL"] = fake_url
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"

    repo_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo_root))
    import server as code_server

    code_server.WORKBAR_URL = fake_url
    code_server.CODEX_SESSIONS_DIR = root / "home" / ".codex" / "sessions"
    code_server.CLAUDE_PROJECTS_DIR = root / "home" / ".claude" / "projects"
    code_server._read_remote_version = lambda: (None, None)
    code_server.write_json(code_server.CONFIG_PATH, {
        "projectRoot": str(project_dir),
        "newApiBaseUrl": fake_url,
    })

    original_execute_registered_tool = code_server.execute_registered_tool

    def counted_execute_registered_tool(action, payload, *, _arguments_validated=False):
        if action != "read_file":
            METRICS.increment("unsafeToolRequests")
            raise ValueError("H4 tool action is outside the read-only fixture contract")
        requested = str((payload or {}).get("path") or "")
        if requested != READ_PATH:
            METRICS.increment("unsafeToolRequests")
            raise ValueError("H4 read_file request escaped the fixed synthetic fixture")
        METRICS.append("toolExecutions", {
            "action": "read_file",
            "path": READ_PATH,
        })
        METRICS.increment("productionToolDelegations")
        return original_execute_registered_tool(
            action,
            payload,
            _arguments_validated=_arguments_validated,
        )

    def probe_tool_boundary():
        before = METRICS.snapshot()
        rejected_action = False
        rejected_path = False
        try:
            counted_execute_registered_tool("list_files", {"path": ""})
        except ValueError:
            rejected_action = True
        try:
            counted_execute_registered_tool("read_file", {"path": "../outside.txt"})
        except ValueError:
            rejected_path = True
        allowed_result = counted_execute_registered_tool("read_file", {"path": READ_PATH})
        after = METRICS.snapshot()
        return {
            "rejectedAction": rejected_action,
            "rejectedPath": rejected_path,
            "allowedRead": bool(allowed_result.get("ok")),
            "unsafeDelta": after["unsafeToolRequests"] - before["unsafeToolRequests"],
            "delegationDelta": (
                after["productionToolDelegations"]
                - before["productionToolDelegations"]
            ),
            "toolExecutionDelta": (
                len(after["toolExecutions"])
                - len(before["toolExecutions"])
            ),
        }

    code_server.execute_registered_tool = counted_execute_registered_tool
    code_server.ThreadingHTTPServer.daemon_threads = True
    code_server._migrate_sessions_to_hierarchy()
    code_server._migrate_codex_project_sessions_support()
    code_server._migrate_project_root_paths()
    code_httpd = code_server.ThreadingHTTPServer(("127.0.0.1", 0), code_server.CodeHandler)
    code_httpd.daemon_threads = True
    code_port = code_httpd.server_address[1]
    code_thread = threading.Thread(target=code_httpd.serve_forever, daemon=True)
    code_thread.start()

    fixture_bytes = (project_dir / READ_PATH).read_bytes()
    sensitive_environment_names = sorted(
        name
        for name in os.environ
        if re.search(r"(?:KEY|TOKEN|SECRET|PASSWORD|COOKIE|AUTH)", name, re.IGNORECASE)
    )
    _json_line({
        "type": "ready",
        "codeUrl": f"http://127.0.0.1:{code_port}",
        "fakeUrl": fake_url,
        "codePort": code_port,
        "fakePort": fake_port,
        "fixtureSha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "environment": {
            "parentSentinelPresent": "H4_PARENT_SECRET_SENTINEL" in os.environ,
            "sensitiveNames": sensitive_environment_names,
            "homeIsIsolated": Path.home().resolve() == (root / "home").resolve(),
        },
    })

    try:
        for raw_line in sys.stdin:
            try:
                command = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            request_id = command.get("id")
            operation = command.get("command")
            if operation == "release-model":
                MODEL_GATE.set()
                _json_line({"type": "response", "id": request_id, "ok": True})
                continue
            if operation == "metrics":
                _json_line({
                    "type": "response",
                    "id": request_id,
                    "ok": True,
                    "metrics": METRICS.snapshot(),
                })
                continue
            if operation == "probe-tool-boundary":
                _json_line({
                    "type": "response",
                    "id": request_id,
                    "ok": True,
                    "contract": probe_tool_boundary(),
                })
                continue
            if operation == "shutdown":
                _json_line({"type": "response", "id": request_id, "ok": True})
                break
            _json_line({"type": "response", "id": request_id, "ok": False})
    finally:
        MODEL_GATE.set()
        code_httpd.shutdown()
        fake_server.shutdown()
        code_httpd.server_close()
        fake_server.server_close()
        code_thread.join(timeout=3)
        fake_thread.join(timeout=3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
