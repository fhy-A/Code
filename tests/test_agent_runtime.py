"""Durable server-owned Agent run regression tests.

Run: python -m pytest tests/test_agent_runtime.py -v
"""

import hashlib
import json
import tempfile
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import requests

import server as server_mod
from agent_protocol import normalize_agent_event


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


class _AgentUpstream(BaseHTTPRequestHandler):
    calls = 0
    payloads = []
    authorizations = []
    slow_started = threading.Event()
    release_slow = threading.Event()
    parallel_lock = threading.Lock()
    parallel_three_started = threading.Event()
    release_parallel = threading.Event()
    parallel_active = 0
    parallel_max_active = 0
    parallel_prompts_started = []
    scripted_lock = threading.Lock()
    scripted_rounds = []

    def log_message(self, *_args):
        return

    def do_POST(self):
        type(self).calls += 1
        type(self).authorizations.append(self.headers.get("Authorization", ""))
        length = int(self.headers.get("Content-Length", "0") or "0")
        payload = json.loads(self.rfile.read(length) or b"{}")
        type(self).payloads.append(payload)
        with type(self).scripted_lock:
            scripted_frames = (
                type(self).scripted_rounds.pop(0)
                if type(self).scripted_rounds
                else None
            )
        if isinstance(scripted_frames, dict) and scripted_frames.get("partial_then_disconnect"):
            self.send_response(int(scripted_frames.get("http_status") or 200))
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.end_headers()
            frame = {
                "choices": [{
                    "delta": {
                        "content": str(scripted_frames.get("content") or ""),
                        "reasoning_content": str(scripted_frames.get("reasoning") or ""),
                    },
                    "finish_reason": None,
                }],
            }
            self.wfile.write(("data: " + json.dumps(frame) + "\n\n").encode("utf-8"))
            self.wfile.flush()
            self.close_connection = True
            return
        if isinstance(scripted_frames, dict) and scripted_frames.get("first_response_timeout"):
            self.send_response(int(scripted_frames.get("http_status") or 200))
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.end_headers()
            deadline = time.monotonic() + max(
                float(scripted_frames["first_response_timeout"]) * 4,
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
        if isinstance(scripted_frames, dict) and scripted_frames.get("http_error"):
            status = int(scripted_frames.get("http_error") or 400)
            error_payload = {
                "message": str(scripted_frames.get("message") or "upstream error"),
            }
            for field in (
                "code", "type", "max_context_tokens", "maximum_context_tokens",
                "context_window", "context_length",
            ):
                if field in scripted_frames:
                    error_payload[field] = scripted_frames[field]
            body = json.dumps({
                "error": error_payload,
            }).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            return
        messages = payload.get("messages") or []
        parallel_child_prompt = next((
            str(message.get("content") or "")
            for message in messages
            if message.get("role") == "user"
            and str(message.get("content") or "").startswith("parallel child ")
        ), "")
        if parallel_child_prompt:
            with type(self).parallel_lock:
                type(self).parallel_active += 1
                type(self).parallel_max_active = max(
                    type(self).parallel_max_active,
                    type(self).parallel_active,
                )
                type(self).parallel_prompts_started.append(parallel_child_prompt)
                if type(self).parallel_active >= 3:
                    type(self).parallel_three_started.set()
            type(self).release_parallel.wait(timeout=5)
            with type(self).parallel_lock:
                type(self).parallel_active -= 1
        if any(
            message.get("role") == "user" and message.get("content") == "slow request"
            for message in messages
        ):
            type(self).slow_started.set()
            type(self).release_slow.wait(timeout=3)
        if any(
            message.get("role") == "user"
            and message.get("content") == "never produce a first response"
            for message in messages
        ):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.end_headers()
            deadline = time.monotonic() + 0.6
            while time.monotonic() < deadline:
                try:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                except OSError:
                    return
                time.sleep(0.01)
            return
        tool_result_count = sum(message.get("role") == "tool" for message in messages)
        repeat_id = any(
            message.get("role") == "user" and message.get("content") == "repeat tool id"
            for message in messages
        )
        asks_user = any(
            message.get("role") == "user"
            and message.get("content") in {"ask for target", "ask for URL"}
            for message in messages
        )
        asks_user_for_text = any(
            message.get("role") == "user" and message.get("content") == "ask for URL"
            for message in messages
        )
        proposes_edit = any(
            message.get("role") == "user" and message.get("content") == "propose edit"
            for message in messages
        )
        uses_network_and_skills = any(
            message.get("role") == "user"
            and message.get("content") == "inspect skill and network"
            for message in messages
        )
        runs_command = any(
            message.get("role") == "user"
            and message.get("content") in {
                "run approved command",
                "run slow command",
                "install dependency in bypass",
                "install system dependency in bypass",
            }
            for message in messages
        )
        installs_dependency = any(
            message.get("role") == "user" and message.get("content") == "install dependency in bypass"
            for message in messages
        )
        installs_system_dependency = any(
            message.get("role") == "user"
            and message.get("content") == "install system dependency in bypass"
            for message in messages
        )
        runs_slow_command = any(
            message.get("role") == "user" and message.get("content") == "run slow command"
            for message in messages
        )
        saves_memory = any(
            message.get("role") == "user" and message.get("content") == "remember convention"
            for message in messages
        )
        writes_file = any(
            message.get("role") == "user" and message.get("content") == "write project file"
            for message in messages
        )
        deletes_file = any(
            message.get("role") == "user" and message.get("content") == "delete project file"
            for message in messages
        )
        delegation_prompt_map = {
            "delegate inspection": "inspect child file",
            "delegate write child": "write project file",
            "delegate slow child": "slow request",
        }
        delegated_prompts = [next((
            prompt
            for message_text, prompt in delegation_prompt_map.items()
            if any(
                message.get("role") == "user" and message.get("content") == message_text
                for message in messages
            )
        ), "")]
        if any(
            message.get("role") == "user"
            and message.get("content") == "delegate parallel children"
            for message in messages
        ):
            delegated_prompts = [f"parallel child {index}" for index in range(1, 5)]
        delegated_prompts = [prompt for prompt in delegated_prompts if prompt]
        should_call_tool = tool_result_count == 0 or (repeat_id and tool_result_count < 2)
        if scripted_frames is not None:
            frames = scripted_frames
        elif delegated_prompts and tool_result_count == 0:
            frames = [
                {"choices": [{
                    "delta": {"tool_calls": [
                        {
                            "index": index,
                            "id": f"agent-task-{index + 1}",
                            "type": "function",
                            "function": {
                                "name": "task",
                                "arguments": json.dumps({"prompt": prompt}),
                            },
                        }
                        for index, prompt in enumerate(delegated_prompts)
                    ]},
                    "finish_reason": "tool_calls",
                }]},
                {"choices": [], "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 3,
                    "total_tokens": 8,
                }},
            ]
        elif delegated_prompts:
            frames = [
                {"choices": [{
                    "delta": {"content": "delegation task complete"},
                    "finish_reason": "stop",
                }]},
                {"choices": [], "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 3,
                    "total_tokens": 10,
                }},
            ]
        elif writes_file and tool_result_count == 0:
            frames = [{
                "choices": [{
                    "delta": {"tool_calls": [{
                        "index": 0,
                        "id": "agent-write-1",
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": json.dumps({
                                "path": "generated.txt",
                                "content": "written by AgentRun\n",
                            }),
                        },
                    }]},
                    "finish_reason": "tool_calls",
                }],
            }]
        elif writes_file:
            frames = [
                {"choices": [{
                    "delta": {"content": "write task complete"},
                    "finish_reason": "stop",
                }]},
                {"choices": [], "usage": {
                    "prompt_tokens": 8,
                    "completion_tokens": 3,
                    "total_tokens": 11,
                }},
            ]
        elif deletes_file and tool_result_count == 0:
            frames = [{
                "choices": [{
                    "delta": {"tool_calls": [{
                        "index": 0,
                        "id": "agent-delete-1",
                        "type": "function",
                        "function": {
                            "name": "delete_file",
                            "arguments": json.dumps({"path": "obsolete.txt"}),
                        },
                    }]},
                    "finish_reason": "tool_calls",
                }],
            }]
        elif deletes_file:
            frames = [
                {"choices": [{
                    "delta": {"content": "delete task complete"},
                    "finish_reason": "stop",
                }]},
                {"choices": [], "usage": {
                    "prompt_tokens": 8,
                    "completion_tokens": 3,
                    "total_tokens": 11,
                }},
            ]
        elif saves_memory and tool_result_count == 0:
            frames = [{
                "choices": [{
                    "delta": {"tool_calls": [{
                        "index": 0,
                        "id": "agent-memory-1",
                        "type": "function",
                        "function": {
                            "name": "save_memory",
                            "arguments": json.dumps({
                                "name": "runtime-convention",
                                "description": "Runtime convention",
                                "body": "AgentRun owns durable memory writes.",
                            }),
                        },
                    }]},
                    "finish_reason": "tool_calls",
                }],
            }]
        elif saves_memory:
            frames = [
                {
                    "choices": [{
                        "delta": {"content": "memory task complete"},
                        "finish_reason": "stop",
                    }],
                },
                {"choices": [], "usage": {
                    "prompt_tokens": 8,
                    "completion_tokens": 3,
                    "total_tokens": 11,
                }},
            ]
        elif runs_command and tool_result_count == 0:
            command = (
                'python -c "import time; print(\'command-started\', flush=True); time.sleep(20)"'
                if runs_slow_command
                else (
                    "winget install Pandoc.Pandoc"
                    if installs_system_dependency
                    else (
                        "python -m pip install code-test-never-install"
                        if installs_dependency
                        else 'python -c "print(\'agent-command\')"'
                    )
                )
            )
            frames = [{
                "choices": [{
                    "delta": {"tool_calls": [{
                        "index": 0,
                        "id": "agent-command-1",
                        "type": "function",
                        "function": {
                            "name": "run_command",
                            "arguments": json.dumps({
                                "command": command,
                                "description": "Agent runtime command",
                            }),
                        },
                    }]},
                    "finish_reason": "tool_calls",
                }],
            }]
        elif runs_command:
            frames = [
                {
                    "choices": [{
                        "delta": {"content": "command task complete"},
                        "finish_reason": "stop",
                    }],
                },
                {"choices": [], "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 3,
                    "total_tokens": 13,
                }},
            ]
        elif uses_network_and_skills and tool_result_count == 0:
            calls = [
                ("agent-skill-1", "use_skill", {"name": "runtime-skill"}),
                (
                    "agent-skill-resource-1",
                    "read_skill_resource",
                    {"skill": "runtime-skill", "file": "references/guide.md"},
                ),
                ("agent-web-1", "web_fetch", {"url": "https://example.com/docs"}),
            ]
            frames = [{
                "choices": [{
                    "delta": {
                        "tool_calls": [
                            {
                                "index": index,
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(arguments),
                                },
                            }
                            for index, (call_id, name, arguments) in enumerate(calls)
                        ],
                    },
                    "finish_reason": "tool_calls",
                }],
            }]
        elif uses_network_and_skills:
            frames = [
                {
                    "choices": [{
                        "delta": {"content": "network and skill task complete"},
                        "finish_reason": "stop",
                    }],
                },
                {"choices": [], "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                }},
            ]
        elif proposes_edit and tool_result_count == 0:
            frames = [{
                "choices": [{
                    "delta": {"tool_calls": [{
                        "index": 0,
                        "id": "agent-edit-1",
                        "type": "function",
                        "function": {
                            "name": "propose_edit",
                            "arguments": json.dumps({
                                "path": "README.md",
                                "oldText": "Durable Agent",
                                "newText": "Authorized Agent",
                            }),
                        },
                    }]},
                    "finish_reason": "tool_calls",
                }],
            }]
        elif proposes_edit:
            frames = [
                {"choices": [{"delta": {"content": "edit task complete"}, "finish_reason": "stop"}]},
                {"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12}},
            ]
        elif asks_user and tool_result_count == 0:
            arguments = {
                "title": "Choose a target",
                "reason": "The target cannot be inferred from the project.",
                "questions": ([{
                    "id": "url",
                    "prompt": "Which URL should be analyzed?",
                    "type": "single",
                    "required": True,
                    "allowOther": True,
                    "options": [
                        {
                            "value": "discover",
                            "label": "Find a source",
                            "description": "Recommended because no URL was supplied.",
                            "recommended": True,
                        },
                        {
                            "value": "provided",
                            "label": "Use a supplied URL",
                            "description": "Choose this when the exact source is known.",
                            "recommended": False,
                        },
                    ],
                }] if asks_user_for_text else [{
                    "id": "target",
                    "prompt": "Which target should be analyzed?",
                    "type": "single",
                    "required": True,
                    "allowOther": True,
                    "options": [
                        {
                            "value": "api", "label": "API",
                            "description": "Recommended because the request concerns the API.",
                            "recommended": True,
                        },
                        {
                            "value": "ui", "label": "UI",
                            "description": "Choose this for the interface.",
                            "recommended": False,
                        },
                    ],
                }]),
            }
            frames = [{
                "choices": [{
                    "delta": {"tool_calls": [{
                        "index": 0,
                        "id": "agent-question-1",
                        "type": "function",
                        "function": {
                            "name": "request_user_input",
                            "arguments": json.dumps(arguments),
                        },
                    }]},
                    "finish_reason": "tool_calls",
                }],
            }]
        elif asks_user:
            frames = [
                {"choices": [{"delta": {"content": "questionnaire task complete"}, "finish_reason": "stop"}]},
                {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}},
            ]
        elif parallel_child_prompt:
            frames = [
                {"choices": [{
                    "delta": {"content": f"completed {parallel_child_prompt}"},
                    "finish_reason": "stop",
                }]},
                {"choices": [], "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 1,
                    "total_tokens": 4,
                }},
            ]
        elif not should_call_tool:
            frames = [
                {"choices": [{"delta": {"content": "read-only task complete"}, "finish_reason": "stop"}]},
                {"choices": [], "usage": {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11}},
            ]
        else:
            frames = [
                {
                    "choices": [{
                        "delta": {
                            "reasoning_content": "reading project file",
                            "tool_calls": [{
                                "index": 0,
                                "id": "agent-call-1",
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
                {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9}},
            ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.end_headers()
        for frame in frames:
            self.wfile.write(("data: " + json.dumps(frame) + "\n\n").encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class TestDurableAgentRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), _AgentUpstream)
        cls.thread = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.upstream.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.upstream.shutdown()
        cls.upstream.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="code_agent_runtime_")
        self.data_dir = Path(self.temp_dir.name) / "data"
        self.project_dir = Path(self.temp_dir.name) / "project"
        self.data_dir.mkdir()
        self.project_dir.mkdir()
        (self.project_dir / "README.md").write_text("# Durable Agent\n", encoding="utf-8")
        self.config_path = self.data_dir / "config.json"
        self.config_path.write_text(json.dumps({
            "projectRoot": str(self.project_dir),
            "newApiBaseUrl": self.base_url,
        }), encoding="utf-8")
        self.patchers = [
            mock.patch.object(server_mod, "DATA_DIR", self.data_dir),
            mock.patch.object(server_mod, "SESSIONS_DIR", self.data_dir / "sessions"),
            mock.patch.object(server_mod, "CONFIG_PATH", self.config_path),
            mock.patch.object(server_mod, "FILE_BACKUP_DIR", self.data_dir / "file-backups"),
            mock.patch.object(server_mod, "SKILLS_DIR", self.data_dir / "skills"),
            mock.patch.object(server_mod, "MEMORY_DIR", self.data_dir / "memory"),
            mock.patch.object(server_mod, "_MODEL_ROUTE_REGISTRY_ENABLED", False),
        ]
        for patcher in self.patchers:
            patcher.start()
        with server_mod._agent_run_lock:
            server_mod._agent_runs.clear()
        with server_mod._model_runtime_lock:
            server_mod._model_runtime_runs.clear()
        with server_mod.context_window._catalog_lock:
            server_mod.context_window._catalog.clear()
        _AgentUpstream.calls = 0
        _AgentUpstream.payloads = []
        _AgentUpstream.authorizations = []
        _AgentUpstream.slow_started.clear()
        _AgentUpstream.release_slow.clear()
        _AgentUpstream.parallel_three_started.clear()
        _AgentUpstream.release_parallel.clear()
        with _AgentUpstream.parallel_lock:
            _AgentUpstream.parallel_active = 0
            _AgentUpstream.parallel_max_active = 0
            _AgentUpstream.parallel_prompts_started = []
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = []

    def tearDown(self):
        _AgentUpstream.release_slow.set()
        _AgentUpstream.release_parallel.set()
        with server_mod._agent_run_lock:
            runs = list(server_mod._agent_runs.values())
        deadline = time.time() + 2
        while any(run.get("worker") is not None for run in runs) and time.time() < deadline:
            time.sleep(0.01)
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def _wait_terminal(self, run, timeout=5):
        deadline = time.time() + timeout
        with run["condition"]:
            while run["status"] not in server_mod._AGENT_RUN_TERMINAL and time.time() < deadline:
                run["condition"].wait(timeout=0.05)
        self.assertIn(run["status"], server_mod._AGENT_RUN_TERMINAL)

    def _wait_status(self, run, expected, timeout=5):
        deadline = time.time() + timeout
        with run["condition"]:
            while run["status"] != expected and time.time() < deadline:
                run["condition"].wait(timeout=0.05)
        self.assertEqual(run["status"], expected)

    def _wait_worker_idle(self, run, timeout=2):
        deadline = time.time() + timeout
        while run.get("worker") is not None and time.time() < deadline:
            time.sleep(0.01)
        self.assertIsNone(run.get("worker"))

    def _assert_expected_subset(self, actual, expected, path):
        if isinstance(expected, dict):
            self.assertIsInstance(actual, dict, path)
            for key, value in expected.items():
                self.assertIn(key, actual, f"{path}.{key}")
                self._assert_expected_subset(actual[key], value, f"{path}.{key}")
            return
        if isinstance(expected, list):
            self.assertIsInstance(actual, list, path)
            self.assertEqual(len(actual), len(expected), path)
            for index, value in enumerate(expected):
                self._assert_expected_subset(actual[index], value, f"{path}[{index}]")
            return
        self.assertEqual(actual, expected, path)

    def _assert_agent_events_match_evidence_fixture(self, run, fixture):
        actual_events = run["events"]
        expected_events = fixture["events"]
        facts = fixture["sourceFacts"]
        self.assertEqual(
            [event["type"] for event in actual_events],
            facts["agentEventTypes"],
            "$.sourceFacts.agentEventTypes",
        )
        self.assertEqual(len(actual_events), len(expected_events), "$.events")

        expected_runtime_ids = [
            event["data"]["runtimeRunId"]
            for event in expected_events
            if event["type"] == "model_started"
        ]
        actual_runtime_ids = [
            event["data"]["runtimeRunId"]
            for event in actual_events
            if event["type"] == "model_started"
        ]
        self.assertEqual(len(actual_runtime_ids), len(expected_runtime_ids), "$.events.runtimeRunId")
        runtime_ids = dict(zip(expected_runtime_ids, actual_runtime_ids))

        def replace_runtime_ids(value):
            if isinstance(value, dict):
                return {key: replace_runtime_ids(item) for key, item in value.items()}
            if isinstance(value, list):
                return [replace_runtime_ids(item) for item in value]
            return runtime_ids.get(value, value)

        for index, (actual, expected) in enumerate(zip(actual_events, expected_events)):
            normalized = normalize_agent_event(actual, strict=True)
            self.assertEqual(normalized["diagnostics"], [], f"$.events[{index}]")
            self.assertEqual(actual["seq"], expected["seq"], f"$.events[{index}].seq")
            self.assertEqual(actual["type"], expected["type"], f"$.events[{index}].type")
            self._assert_expected_subset(
                actual["data"],
                replace_runtime_ids(expected["data"]),
                f"$.events[{index}].data",
            )
        return actual_runtime_ids

    def test_h3_2c1_agent_failures_and_runtime_snapshots_consume_same_case_data(self):
        fixtures = [
            fixture for fixture in _load_h3_2c1_evidence_fixtures()
            if fixture["sourceFacts"]["caseKind"] in {
                "http-failure",
                "first-response-timeout",
            }
        ]
        agent_projection_by_status = {}
        for index, fixture in enumerate(fixtures):
            with self.subTest(fixture=fixture["name"]):
                facts = fixture["sourceFacts"]
                runtime_input = facts["runtimeInput"]
                scripted = (
                    {
                        "http_error": runtime_input["httpStatus"],
                        "message": runtime_input["httpMessage"],
                    }
                    if facts["caseKind"] == "http-failure"
                    else {
                        "first_response_timeout": runtime_input["timeoutSeconds"],
                        "http_status": runtime_input["httpStatus"],
                    }
                )
                with _AgentUpstream.scripted_lock:
                    _AgentUpstream.scripted_rounds = [scripted]
                timeout_patch = (
                    mock.patch.object(
                        server_mod,
                        "_MODEL_RUNTIME_FIRST_RESPONSE_TIMEOUT",
                        runtime_input["timeoutSeconds"],
                    )
                    if facts["caseKind"] == "first-response-timeout"
                    else mock.patch.object(
                        server_mod,
                        "_MODEL_RUNTIME_FIRST_RESPONSE_TIMEOUT",
                        server_mod._MODEL_RUNTIME_FIRST_RESPONSE_TIMEOUT,
                    )
                )
                with timeout_patch, mock.patch.object(
                    server_mod,
                    "_AGENT_EVENT_PROTOCOL_V1_ENABLED",
                    True,
                ):
                    run = server_mod._create_agent_run(
                        f"h3-2c1-agent-failure-{index}",
                        {
                            "model": "test-model",
                            "messages": [{
                                "role": "user",
                                "content": runtime_input["userContent"],
                            }],
                        },
                        self.base_url,
                        ["synthetic-agent-key"],
                        allowed_tools=[],
                        max_rounds=3,
                    )
                    self._wait_terminal(run)

                snapshot = server_mod._agent_snapshot(run, 0)
                self.assertEqual(snapshot["status"], "failed")
                self.assertEqual(
                    snapshot["errorCode"],
                    facts["agentRunErrorCode"],
                    f"$.fixtures[{index}].sourceFacts.agentRunErrorCode",
                )
                runtime_ids = self._assert_agent_events_match_evidence_fixture(run, fixture)
                self.assertEqual(len(runtime_ids), 1)
                runtime_run = server_mod._get_model_runtime_run(runtime_ids[0])
                self.assertIsNotNone(runtime_run)
                runtime_snapshot = server_mod._runtime_snapshot(runtime_run, 0)
                self.assertEqual(
                    runtime_snapshot["upstreamStatus"],
                    facts["upstreamStatus"],
                    f"$.fixtures[{index}].sourceFacts.upstreamStatus",
                )
                self.assertEqual(
                    runtime_snapshot["errorCode"],
                    facts["runtimeErrorCode"],
                    f"$.fixtures[{index}].sourceFacts.runtimeErrorCode",
                )
                self.assertEqual(
                    runtime_snapshot["transient"],
                    facts["runtimeTransient"],
                    f"$.fixtures[{index}].sourceFacts.runtimeTransient",
                )
                if facts["upstreamStatus"] in {429, 502}:
                    agent_projection_by_status[facts["upstreamStatus"]] = (
                        snapshot["status"],
                        snapshot["errorCode"],
                        [event["type"] for event in run["events"]],
                    )

        self.assertEqual(agent_projection_by_status[429], agent_projection_by_status[502])

    def test_h3_2c1_non_action_agent_events_match_current_production_order(self):
        fixtures = [
            fixture for fixture in _load_h3_2c1_evidence_fixtures()
            if fixture["sourceFacts"]["caseKind"] == "non-action"
        ]
        for index, fixture in enumerate(fixtures):
            with self.subTest(fixture=fixture["name"]):
                runtime_input = fixture["sourceFacts"]["runtimeInput"]
                if runtime_input["responseMode"] == "empty-then-content":
                    first_delta = {}
                else:
                    first_delta = {"reasoning_content": runtime_input["reasoning"]}
                with _AgentUpstream.scripted_lock:
                    _AgentUpstream.scripted_rounds = [
                        [{"choices": [{"delta": first_delta, "finish_reason": "stop"}]}],
                        [{"choices": [{
                            "delta": {"content": runtime_input["finalContent"]},
                            "finish_reason": "stop",
                        }]}],
                    ]
                with mock.patch.object(
                    server_mod,
                    "_AGENT_EVENT_PROTOCOL_V1_ENABLED",
                    True,
                ):
                    run = server_mod._create_agent_run(
                        f"h3-2c1-agent-non-action-{index}",
                        {
                            "model": "test-model",
                            "messages": [{
                                "role": "user",
                                "content": runtime_input["userContent"],
                            }],
                        },
                        self.base_url,
                        ["synthetic-agent-key"],
                        allowed_tools=[],
                        max_rounds=3,
                    )
                    self._wait_terminal(run)
                snapshot = server_mod._agent_snapshot(run, 0)
                runtime_ids = self._assert_agent_events_match_evidence_fixture(run, fixture)

                self.assertEqual(snapshot["status"], "completed")
                self.assertEqual(snapshot["result"]["content"], runtime_input["finalContent"])
                self.assertEqual([item["outcome"] for item in run["rounds"]], [
                    fixture["events"][2]["data"]["outcome"],
                    "completed",
                ])
                self.assertNotIn("model_pending", [event["type"] for event in run["events"]])
                self.assertEqual(len(runtime_ids), 2)
                for runtime_id in runtime_ids:
                    runtime_snapshot = server_mod._runtime_snapshot(
                        server_mod._get_model_runtime_run(runtime_id),
                        0,
                    )
                    self.assertEqual(runtime_snapshot["status"], "completed")
                    self.assertEqual(
                        runtime_snapshot["upstreamStatus"],
                        fixture["sourceFacts"]["upstreamStatus"],
                        "$.sourceFacts.upstreamStatus",
                    )
                    self.assertEqual(
                        runtime_snapshot["errorCode"],
                        fixture["sourceFacts"]["runtimeErrorCode"],
                        "$.sourceFacts.runtimeErrorCode",
                    )
                    self.assertEqual(
                        runtime_snapshot["transient"],
                        fixture["sourceFacts"]["runtimeTransient"],
                        "$.sourceFacts.runtimeTransient",
                    )

    def test_h3_2c1_pre_event_fallback_reaches_agent_only_for_representative_502(self):
        fixture = next(
            fixture for fixture in _load_h3_2c1_evidence_fixtures()
            if fixture["sourceFacts"]["fallback"]["tested"]
        )
        facts = fixture["sourceFacts"]
        fallback = facts["fallback"]
        self.assertEqual(facts["upstreamStatus"], 502)
        self.assertEqual(fallback["scope"], "representative-status-only")
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                {
                    "http_error": fallback["firstAttemptStatus"],
                    "message": facts["runtimeInput"]["httpMessage"],
                },
                [{"choices": [{
                    "delta": {"content": "Synthetic fallback completed."},
                    "finish_reason": "stop",
                }]}],
            ]
        with mock.patch.object(
            server_mod,
            "_AGENT_EVENT_PROTOCOL_V1_ENABLED",
            True,
        ):
            run = server_mod._create_agent_run(
                "h3-2c1-agent-fallback",
                {
                    "model": "test-model",
                    "messages": [{
                        "role": "user",
                        "content": facts["runtimeInput"]["userContent"],
                    }],
                },
                self.base_url,
                ["synthetic-primary-key", "synthetic-secondary-key"],
                allowed_tools=[],
                max_rounds=3,
            )
            self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)

        self.assertEqual(_AgentUpstream.calls, fallback["expectedCalls"])
        self.assertEqual(len(_AgentUpstream.authorizations), fallback["keyCount"])
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "Synthetic fallback completed.")
        self.assertEqual(
            [event["type"] for event in run["events"]],
            ["created", "model_started", "model_completed", "completed"],
        )
        self.assertNotIn("failed", [event["type"] for event in run["events"]])
        runtime_id = next(
            event["data"]["runtimeRunId"]
            for event in run["events"] if event["type"] == "model_started"
        )
        runtime_snapshot = server_mod._runtime_snapshot(
            server_mod._get_model_runtime_run(runtime_id),
            0,
        )
        self.assertEqual(runtime_snapshot["status"], fallback["expectedRuntimeStatus"])
        self.assertEqual(runtime_snapshot["errorCode"], "")
        self.assertNotIn(facts["upstreamMessage"], json.dumps(runtime_snapshot, ensure_ascii=False))

    def test_agent_context_limit_and_multilingual_request_estimate(self):
        self.assertEqual(
            server_mod._agent_requested_max_tokens({
                "max_tokens": 1024,
                "max_completion_tokens": 16000,
            }),
            16000,
        )
        self.assertEqual(server_mod._agent_model_context_limit("gpt-5.6"), 1_000_000)
        self.assertEqual(server_mod._agent_model_context_limit("claude-4.5"), 200_000)
        self.assertEqual(server_mod._agent_model_context_limit("unknown-model"), 128_000)
        self.assertEqual(
            server_mod._normalize_agent_context_limit(None, "gemini-2.5-pro"),
            1_000_000,
        )
        with self.assertRaisesRegex(ValueError, "contextLimit"):
            server_mod._normalize_agent_context_limit("large", "test-model", strict=True)
        with self.assertRaisesRegex(ValueError, "contextLimit"):
            server_mod._normalize_agent_context_limit({}, "test-model", strict=True)

        ascii_tokens = server_mod._agent_estimate_text_tokens("a" * 40)
        chinese_tokens = server_mod._agent_estimate_text_tokens("上下文压缩测试" * 5)
        self.assertEqual(ascii_tokens, 10)
        self.assertEqual(chinese_tokens, 35)

        base = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "x" * 3200}],
        }
        with_tools = dict(base, tools=[{
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "y" * 1200,
                "parameters": {"type": "object"},
            },
        }])
        self.assertFalse(server_mod._agent_should_auto_compact(base, 1024))
        self.assertTrue(server_mod._agent_should_auto_compact(with_tools, 1024))

    def test_agent_compaction_plan_keeps_active_task_and_latest_complete_tool_group(self):
        messages = [
            {"role": "system", "content": "system rules"},
            {"role": "user", "content": "old task"},
            {"role": "assistant", "content": "old result"},
            {
                "role": "user",
                "content": server_mod._AGENT_CONTEXT_SUMMARY_PREFIX + "\nolder summary",
            },
            {"role": "user", "content": "current task must remain exact"},
            {"role": "assistant", "content": "intermediate explanation"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call-latest",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }],
            },
            {
                "role": "tool",
                "tool_call_id": "call-latest",
                "name": "read_file",
                "content": "latest tool result",
            },
        ]

        plan = server_mod._agent_compaction_plan(messages)

        self.assertIsNotNone(plan)
        self.assertEqual(plan["latestUserIndex"], 4)
        self.assertEqual(plan["toolBlockIndices"], [6, 7])
        self.assertEqual(
            [message.get("content") for message in plan["retainedMessages"]],
            ["system rules", "current task must remain exact", "", "latest tool result"],
        )
        self.assertIn("intermediate explanation", [
            message.get("content") for message in plan["compactedMessages"]
        ])
        self.assertIn("older summary", json.dumps(plan["compactedMessages"]))

    def test_agent_compaction_plan_refuses_unshrinkable_current_task(self):
        self.assertIsNone(server_mod._agent_compaction_plan([
            {"role": "system", "content": "system rules"},
            {"role": "user", "content": "one very large current task"},
        ]))

    def test_legacy_agent_record_restores_context_defaults(self):
        run = server_mod._create_agent_run(
            "legacy-context-session",
            {
                "model": "gpt-5.6",
                "messages": [{"role": "user", "content": "legacy task"}],
            },
            self.base_url,
            [],
            start_worker=False,
        )
        record = server_mod._agent_run_record(run)
        record["version"] = 2
        for field in (
            "contextLimit", "contextWindowTokens", "contextBudgetTokens",
            "contextWindowSource", "contextWindowHard", "availableInputTokens",
            "compressionTriggerTokens", "budgetClamped", "budgetAboveEstimate",
        ):
            record.pop(field, None)
        record.pop("contextRecoveryRound")
        record.pop("compactions")

        restored = server_mod._agent_run_from_record(record)

        self.assertEqual(restored["context_limit"], 1_000_000)
        self.assertEqual(restored["context_recovery_round"], 0)
        self.assertEqual(restored["compactions"], [])

    def test_server_context_resolution_is_authoritative_and_rejects_no_input_room(self):
        server_mod.context_window.normalize_catalog(self.base_url, [{
            "id": "hard-model",
            "contextWindowTokens": 200000,
        }])
        run = server_mod._create_agent_run(
            "hard-context-session",
            {
                "model": "hard-model",
                "max_tokens": 16000,
                "messages": [{"role": "user", "content": "hard limit"}],
            },
            self.base_url,
            [],
            context_limit=1000000,
            context_budget_tokens=1000000,
            start_worker=False,
        )
        self.assertEqual(run["context_limit"], 200000)
        self.assertEqual(run["context_window_tokens"], 200000)
        self.assertEqual(run["context_window_source"], "metadata")
        self.assertTrue(run["context_window_hard"])
        self.assertTrue(run["budget_clamped"])
        self.assertEqual(run["available_input_tokens"], 174000)
        restored = server_mod._agent_run_from_record(server_mod._agent_run_record(run))
        for field in (
            "context_limit", "context_window_tokens", "context_budget_tokens",
            "context_window_source", "context_window_hard", "available_input_tokens",
            "compression_trigger_tokens", "budget_clamped", "budget_above_estimate",
        ):
            self.assertEqual(restored[field], run[field])

        official = server_mod._create_agent_run(
            "official-context-session",
            {
                "model": "gpt-5.4-mini",
                "max_tokens": 200000,
                "messages": [{"role": "user", "content": "official estimate"}],
            },
            self.base_url,
            [],
            context_limit=1000000,
            context_budget_tokens=1000000,
            start_worker=False,
        )
        self.assertEqual(official["context_limit"], 1000000)
        self.assertEqual(official["context_window_tokens"], 400000)
        self.assertEqual(official["context_window_source"], "official")
        self.assertFalse(official["context_window_hard"])
        self.assertTrue(official["budget_above_estimate"])
        official_record = server_mod._agent_run_record(official)
        official_restored = server_mod._agent_run_from_record(official_record)
        self.assertEqual(official_restored["context_window_source"], "official")
        self.assertEqual(official_restored["context_window_tokens"], 400000)

        self.assertEqual(
            server_mod._normalize_session_context_resolution({
                "contextLimit": 400000,
                "contextWindowTokens": 400000,
                "contextWindowSource": "official",
            })["contextWindowSource"],
            "official",
        )
        self.assertEqual(
            server_mod._normalize_session_context_resolution({
                "contextLimit": 400000,
                "contextWindowTokens": 400000,
                "contextWindowSource": "stale_official",
            })["contextWindowSource"],
            "stale_official",
        )

        with self.assertRaisesRegex(ValueError, "leave at least 1024 input tokens"):
            server_mod._create_agent_run(
                "small-context-session",
                {
                    "model": "unknown-model",
                    "max_tokens": 2048,
                    "messages": [{"role": "user", "content": "too small"}],
                },
                self.base_url,
                [],
                context_limit=4096,
                context_budget_tokens=4096,
                start_worker=False,
            )

    def test_internal_child_snapshot_strictly_inherits_parent_context(self):
        parent = server_mod._create_agent_run(
            "inherited-context-session",
            {
                "model": "custom-model",
                "max_tokens": 16000,
                "messages": [{"role": "user", "content": "parent"}],
            },
            self.base_url,
            [],
            context_limit=400000,
            context_budget_tokens=400000,
            start_worker=False,
        )
        self.assertEqual(parent["context_limit"], 400000)
        self.assertTrue(parent["budget_above_estimate"])
        parent["calibration_cap_tokens"] = 400000
        parent["calibration_evidence_kind"] = "heuristic"
        parent["calibration_expires_at"] = "2030-01-08T00:00:00Z"
        parent["calibration_applied"] = True

        server_mod.context_window.normalize_catalog(self.base_url, [{
            "id": "custom-model",
            "contextWindowTokens": 128000,
        }])
        child = server_mod._create_agent_run(
            "inherited-context-session",
            {
                "model": "custom-model",
                "max_tokens": 16000,
                "messages": [{"role": "user", "content": "child"}],
            },
            self.base_url,
            [],
            parent_run_id=parent["id"],
            agent_depth=1,
            inherited_context=server_mod._agent_frozen_context_resolution(parent),
            start_worker=False,
        )
        for field in (
            "context_limit", "context_window_tokens", "context_budget_tokens",
            "context_window_source", "context_window_hard", "available_input_tokens",
            "compression_trigger_tokens", "budget_clamped", "budget_above_estimate",
            "calibration_cap_tokens", "calibration_evidence_kind",
            "calibration_expires_at", "calibration_applied",
        ):
            self.assertEqual(child[field], parent[field])

    def test_same_second_newer_calibrated_run_wins_session_and_stale_client_merge(self):
        session_id = "same-second-calibration-session"
        session_file = server_mod.session_path(session_id)
        session_file.parent.mkdir(parents=True, exist_ok=True)
        server_mod.write_json(session_file, {
            "id": session_id,
            "title": "Same second calibration",
            "stats": {},
        })
        with server_mod._agent_created_at_lock:
            previous_created_microsecond = server_mod._agent_last_created_microsecond
            server_mod._agent_last_created_microsecond = 0
        try:
            with mock.patch.object(server_mod.time, "time_ns", return_value=1_787_287_200_000_000_000):
                first = server_mod._create_agent_run(
                    session_id,
                    {
                        "model": "test-model",
                        "messages": [{"role": "user", "content": "first"}],
                    },
                    self.base_url,
                    [],
                    run_kind="foreground",
                    start_worker=False,
                )
                second = server_mod._create_agent_run(
                    session_id,
                    {
                        "model": "test-model",
                        "messages": [{"role": "user", "content": "second"}],
                    },
                    self.base_url,
                    [],
                    run_kind="foreground",
                    start_worker=False,
                )
        finally:
            with server_mod._agent_created_at_lock:
                server_mod._agent_last_created_microsecond = max(
                    server_mod._agent_last_created_microsecond,
                    previous_created_microsecond,
                )
        self.assertLess(first["created_at"], second["created_at"])
        self.assertNotEqual(first["created_at"], second["created_at"])

        first_fact = {
            **first,
            "id": "z-first-run",
            "status": "completed",
        }
        second_fact = {
            **second,
            "id": "a-second-run",
            "status": "completed",
            "context_limit": 64_000,
            "available_input_tokens": 53_504,
            "compression_trigger_tokens": 53_504,
            "calibration_cap_tokens": 64_000,
            "calibration_evidence_kind": "explicit_max",
            "calibration_expires_at": "2030-02-01T00:00:00Z",
            "calibration_applied": True,
        }
        self.assertTrue(server_mod._persist_agent_session_context_resolution(first_fact))
        self.assertTrue(server_mod._persist_agent_session_context_resolution(second_fact))
        authoritative = server_mod.read_json(session_file, {})["stats"]["contextResolution"]
        self.assertEqual(authoritative["sourceAgentRunId"], "a-second-run")
        self.assertEqual(authoritative["contextLimit"], 64_000)
        self.assertTrue(authoritative["calibrationApplied"])

        stale_client = server_mod._session_context_resolution_from_run(first_fact)
        stale_client.pop("sourceAgentRunId", None)
        stale_client.pop("sourceRunCreatedAt", None)
        merged = server_mod._merge_session_stats(
            {"contextResolution": authoritative},
            {"contextResolution": stale_client},
        )
        self.assertEqual(merged["contextResolution"], authoritative)

    def test_completed_foreground_context_persists_idempotently_and_monotonically(self):
        session_id = "context-resolution-session"
        session_file = server_mod.session_path(session_id)
        session_file.parent.mkdir(parents=True, exist_ok=True)
        server_mod.write_json(session_file, {
            "id": session_id,
            "title": "Context resolution",
            "stats": {"input": 1},
        })
        run = server_mod._create_agent_run(
            session_id,
            {
                "model": "custom-model",
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": "persist context"}],
            },
            self.base_url,
            [],
            context_limit=400000,
            context_budget_tokens=400000,
            run_kind="foreground",
            start_worker=False,
        )
        self.assertTrue(server_mod._finish_agent_run(run, "completed"))
        saved = server_mod.read_json(session_file, {})
        resolution = saved["stats"]["contextResolution"]
        self.assertEqual(resolution["contextLimit"], 400000)
        self.assertEqual(resolution["contextWindowTokens"], 128000)
        self.assertEqual(resolution["contextBudgetTokens"], 400000)
        self.assertEqual(resolution["contextWindowSource"], "unknown")
        self.assertTrue(resolution["budgetAboveEstimate"])
        self.assertEqual(resolution["sourceAgentRunId"], run["id"])
        self.assertEqual(resolution["sourceRunCreatedAt"], run["created_at"])
        record = server_mod._agent_run_record(run)
        self.assertEqual(record["runKind"], "foreground")
        self.assertEqual(server_mod._agent_run_from_record(record)["run_kind"], "foreground")

        self.assertFalse(server_mod._persist_agent_session_context_resolution(run))
        older = {
            **run,
            "id": "older-context-run",
            "created_at": "2000-01-01T00:00:00+00:00",
            "context_limit": 64000,
            "context_budget_tokens": 64000,
        }
        self.assertFalse(server_mod._persist_agent_session_context_resolution(older))
        self.assertEqual(
            server_mod.read_json(session_file, {})["stats"]["contextResolution"],
            resolution,
        )

        newer = {
            **run,
            "id": "newer-context-run",
            "created_at": "9999-01-01T00:00:00+00:00",
            "context_limit": 200000,
            "context_budget_tokens": 200000,
            "available_input_tokens": 185904,
            "compression_trigger_tokens": 180000,
            "calibration_cap_tokens": 200000,
            "calibration_evidence_kind": "explicit_max",
            "calibration_expires_at": "2030-02-01T00:00:00Z",
            "calibration_applied": True,
        }
        self.assertTrue(server_mod._persist_agent_session_context_resolution(newer))
        newest = server_mod.read_json(session_file, {})["stats"]["contextResolution"]
        self.assertEqual(newest["sourceAgentRunId"], "newer-context-run")
        self.assertEqual(newest["contextLimit"], 200000)
        self.assertEqual(newest["calibrationCapTokens"], 200000)
        self.assertEqual(newest["calibrationEvidenceKind"], "explicit_max")
        self.assertTrue(newest["calibrationApplied"])
        merged = server_mod._merge_session_stats(
            {"input": 1, "contextResolution": newest},
            {"input": 2},
        )
        self.assertEqual(merged["input"], 2)
        self.assertEqual(merged["contextResolution"], newest)
        self.assertNotIn(
            "contextResolution",
            server_mod._merge_session_stats({"input": 1}, {"input": 2}),
        )
        untrusted = server_mod._merge_session_stats({}, {
            "contextResolution": {
                **newest,
                "sourceAgentRunId": "forged-run",
                "sourceRunCreatedAt": "9999-12-31T23:59:59+00:00",
            },
        })["contextResolution"]
        self.assertNotIn("sourceAgentRunId", untrusted)
        self.assertNotIn("sourceRunCreatedAt", untrusted)

        child = {**newer, "id": "child-context-run", "run_kind": "child"}
        self.assertFalse(server_mod._persist_agent_session_context_resolution(child))

    def test_agent_protocol_shadow_flag_defaults_and_override(self):
        self.assertTrue(server_mod._resolve_agent_protocol_shadow_enabled(
            {},
            instance_mode="dev",
        ))
        self.assertFalse(server_mod._resolve_agent_protocol_shadow_enabled(
            {},
            instance_mode="release",
        ))
        for value in ("0", "false", "NO", "off"):
            with self.subTest(value=value):
                self.assertFalse(server_mod._resolve_agent_protocol_shadow_enabled(
                    {"CODE_AGENT_PROTOCOL_SHADOW": value},
                    instance_mode="dev",
                ))
        for value in ("1", "true", "YES", "on"):
            with self.subTest(value=value):
                self.assertTrue(server_mod._resolve_agent_protocol_shadow_enabled(
                    {"CODE_AGENT_PROTOCOL_SHADOW": value},
                    instance_mode="release",
                ))
        self.assertFalse(server_mod._resolve_agent_protocol_shadow_enabled(
            {"CODE_AGENT_PROTOCOL_SHADOW": "unexpected"},
            instance_mode="release",
        ))
        self.assertTrue(server_mod._resolve_agent_protocol_shadow_enabled(
            {"CODE_AGENT_PROTOCOL_SHADOW": "unexpected"},
            instance_mode="dev",
        ))

    def test_agent_event_protocol_v1_flag_defaults_and_override(self):
        self.assertTrue(server_mod._resolve_agent_event_protocol_v1_enabled(
            {},
            instance_mode="dev",
        ))
        self.assertFalse(server_mod._resolve_agent_event_protocol_v1_enabled(
            {},
            instance_mode="release",
        ))
        for value in ("0", "false", "NO", "off"):
            with self.subTest(value=value):
                self.assertFalse(server_mod._resolve_agent_event_protocol_v1_enabled(
                    {"CODE_AGENT_EVENT_PROTOCOL_V1": value},
                    instance_mode="dev",
                ))
        for value in ("1", "true", "YES", "on"):
            with self.subTest(value=value):
                self.assertTrue(server_mod._resolve_agent_event_protocol_v1_enabled(
                    {"CODE_AGENT_EVENT_PROTOCOL_V1": value},
                    instance_mode="release",
                ))
        self.assertFalse(server_mod._resolve_agent_event_protocol_v1_enabled(
            {"CODE_AGENT_EVENT_PROTOCOL_V1": "unexpected"},
            instance_mode="release",
        ))
        self.assertTrue(server_mod._resolve_agent_event_protocol_v1_enabled(
            {"CODE_AGENT_EVENT_PROTOCOL_V1": "unexpected"},
            instance_mode="dev",
        ))

    def test_agent_projection_shadow_flag_defaults_and_override(self):
        self.assertTrue(server_mod._resolve_agent_projection_shadow_enabled(
            {},
            instance_mode="dev",
        ))
        self.assertFalse(server_mod._resolve_agent_projection_shadow_enabled(
            {},
            instance_mode="release",
        ))
        for value in ("0", "false", "NO", "off"):
            with self.subTest(value=value):
                self.assertFalse(server_mod._resolve_agent_projection_shadow_enabled(
                    {"CODE_AGENT_PROJECTION_SHADOW": value},
                    instance_mode="dev",
                ))
        for value in ("1", "true", "YES", "on"):
            with self.subTest(value=value):
                self.assertTrue(server_mod._resolve_agent_projection_shadow_enabled(
                    {"CODE_AGENT_PROJECTION_SHADOW": value},
                    instance_mode="release",
                ))
        self.assertFalse(server_mod._resolve_agent_projection_shadow_enabled(
            {"CODE_AGENT_PROJECTION_SHADOW": "unexpected"},
            instance_mode="release",
        ))
        self.assertTrue(server_mod._resolve_agent_projection_shadow_enabled(
            {"CODE_AGENT_PROJECTION_SHADOW": "unexpected"},
            instance_mode="dev",
        ))

    def test_agent_event_protocol_v1_writes_one_explicit_envelope(self):
        with (
            mock.patch.object(server_mod, "_AGENT_EVENT_PROTOCOL_V1_ENABLED", True),
            mock.patch.object(server_mod, "_AGENT_PROTOCOL_SHADOW_ENABLED", True),
        ):
            run = server_mod._create_agent_run(
                "protocol-v1-session",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "inspect"}],
                },
                self.base_url,
                [],
                start_worker=False,
            )
            server_mod._set_agent_status(run, "tools")
            server_mod._append_agent_event(run, "tool_started", {
                "toolCallId": "protocol-call",
                "name": "read_file",
                "arguments": "{}",
            })
            server_mod._finish_agent_run(run, "completed")
            shadow = server_mod._agent_protocol_shadow_snapshot(run)

        self.assertTrue(run["events"])
        for event in run["events"]:
            self.assertEqual(event["protocolVersion"], 1)
            self.assertEqual(
                set(event),
                {"protocolVersion", "seq", "type", "data", "createdAt"},
            )
            normalized = server_mod.agent_protocol.normalize_agent_event(
                event,
                strict=True,
            )
            self.assertEqual(normalized["sourceProtocolVersion"], 1)
        self.assertNotIn(
            "legacy_unversioned_event",
            shadow["diagnosticCounts"],
        )
        persisted = json.loads(
            server_mod._agent_run_path(run["id"]).read_text(encoding="utf-8")
        )
        self.assertTrue(all(
            event.get("protocolVersion") == 1
            for event in persisted["events"]
        ))
        public = server_mod._agent_snapshot(run, 0)
        self.assertTrue(all(
            event.get("protocolVersion") == 1
            for event in public["events"]
        ))

    def test_agent_event_protocol_v1_uses_real_utc_and_legacy_preserves_local_time(self):
        local_value = "2030-01-01T20:00:00+08:00"
        with mock.patch.object(server_mod, "_AGENT_EVENT_PROTOCOL_V1_ENABLED", True):
            self.assertEqual(
                server_mod._agent_event_created_at(local_value),
                "2030-01-01T12:00:00Z",
            )
            event = server_mod._build_agent_event(
                1,
                "completed",
                {},
                local_value,
            )
            normalized = server_mod.agent_protocol.normalize_agent_event(
                event,
                strict=True,
            )
            self.assertEqual(normalized["event"]["createdAt"], "2030-01-01T12:00:00Z")

            run = server_mod._create_agent_run(
                "protocol-v1-time-session",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "inspect time"}],
                },
                self.base_url,
                [],
                start_worker=False,
            )
            with mock.patch.object(server_mod, "now_iso", return_value=local_value):
                appended = server_mod._append_agent_event(
                    run,
                    "model_pending",
                    {"round": 1},
                )
            self.assertEqual(appended["createdAt"], "2030-01-01T12:00:00Z")
            self.assertEqual(run["updated_at"], local_value)

        legacy_value = "2030-01-01T20:00:00"
        with mock.patch.object(server_mod, "_AGENT_EVENT_PROTOCOL_V1_ENABLED", False):
            self.assertEqual(
                server_mod._agent_event_created_at(legacy_value),
                legacy_value,
            )

    def test_agent_event_protocol_v1_supports_mixed_history_and_rollback(self):
        with mock.patch.object(server_mod, "_AGENT_EVENT_PROTOCOL_V1_ENABLED", False):
            run = server_mod._create_agent_run(
                "protocol-mixed-session",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "continue"}],
                },
                self.base_url,
                [],
                start_worker=False,
            )
            legacy_record = server_mod._agent_run_record(run)

        self.assertNotIn("protocolVersion", legacy_record["events"][0])
        with mock.patch.object(server_mod, "_AGENT_EVENT_PROTOCOL_V1_ENABLED", True):
            restored = server_mod._agent_run_from_record(legacy_record)
            server_mod._set_agent_status(restored, "model")
            server_mod._append_agent_event(
                restored,
                "resumed",
                {"status": "model"},
            )

        self.assertNotIn("protocolVersion", restored["events"][0])
        self.assertEqual(restored["events"][1]["protocolVersion"], 1)
        source_versions = [
            server_mod.agent_protocol.normalize_agent_event(event)[
                "sourceProtocolVersion"
            ]
            for event in restored["events"]
        ]
        self.assertEqual(source_versions, [0, 1])

        with mock.patch.object(server_mod, "_AGENT_EVENT_PROTOCOL_V1_ENABLED", False):
            rollback_event = server_mod._build_agent_event(
                3,
                "model_pending",
                {"round": 2},
                "2030-01-01T00:00:00Z",
            )
        self.assertEqual(
            set(rollback_event),
            {"seq", "type", "data", "createdAt"},
        )

    def test_agent_protocol_shadow_observes_without_changing_public_or_durable_data(self):
        with (
            mock.patch.object(server_mod, "_AGENT_PROTOCOL_SHADOW_ENABLED", True),
            mock.patch.object(server_mod, "_AGENT_EVENT_PROTOCOL_V1_ENABLED", False),
        ):
            run = server_mod._create_agent_run(
                "shadow-shape-session",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "inspect"}],
                },
                self.base_url,
                [],
                start_worker=False,
            )
            server_mod._set_agent_status(run, "tools")
            event = server_mod._append_agent_event(run, "tool_started", {
                "toolCallId": "shadow-call",
                "name": "read_file",
                "arguments": "{}",
            })
            shadow = server_mod._agent_protocol_shadow_snapshot(run)

        self.assertEqual(
            set(event),
            {"seq", "type", "data", "createdAt"},
        )
        self.assertEqual(shadow["eventsObserved"], 2)
        self.assertEqual(shadow["eventsAccepted"], 2)
        self.assertEqual(shadow["transitionsObserved"], 1)
        self.assertEqual(shadow["lastRunStatus"], "tools")
        self.assertEqual(shadow["contractErrors"], 0)
        self.assertEqual(shadow["diagnosticCounts"]["legacy_unversioned_event"], 2)

        durable = server_mod._agent_run_record(run)
        public = server_mod._agent_snapshot(run, 0)
        persisted = json.loads(
            server_mod._agent_run_path(run["id"]).read_text(encoding="utf-8")
        )
        for representation in (durable, public, persisted):
            encoded = json.dumps(representation, ensure_ascii=False)
            self.assertNotIn("protocol_shadow", encoded)
            self.assertNotIn("protocolShadow", encoded)
            self.assertNotIn("diagnosticCounts", encoded)

    def test_agent_protocol_shadow_diagnoses_credential_like_tool_text_without_sequence_gap(self):
        fixture_text = "source example sk-fixture123456 remains ordinary tool output"
        with (
            mock.patch.object(server_mod, "_AGENT_PROTOCOL_SHADOW_ENABLED", True),
            mock.patch.object(server_mod, "_AGENT_EVENT_PROTOCOL_V1_ENABLED", True),
        ):
            run = server_mod._create_agent_run(
                "shadow-credential-diagnostic-session",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "inspect source"}],
                },
                self.base_url,
                [],
                start_worker=False,
            )
            server_mod._set_agent_status(run, "tools")
            server_mod._append_agent_event(run, "tool_started", {
                "toolCallId": "shadow-source-call",
                "name": "search_files",
                "arguments": "{}",
            })
            completed = server_mod._append_agent_event(run, "tool_completed", {
                "toolCallId": "shadow-source-call",
                "name": "search_files",
                "result": {"content": fixture_text},
                "outcome": "success",
            })
            server_mod._set_agent_status(run, "model")
            server_mod._append_agent_event(run, "model_pending", {"round": 2})
            shadow = server_mod._agent_protocol_shadow_snapshot(run)

        self.assertEqual(completed["data"]["result"]["content"], fixture_text)
        self.assertEqual(shadow["eventsObserved"], 4)
        self.assertEqual(shadow["eventsAccepted"], 4)
        self.assertEqual(shadow["contractErrors"], 0)
        self.assertEqual(shadow["diagnosticCounts"]["credential_like_text"], 1)
        self.assertNotIn("event_sequence_gap", shadow["diagnosticCounts"])
        encoded_shadow = json.dumps(shadow, ensure_ascii=False)
        self.assertNotIn("sk-fixture123456", encoded_shadow)
        self.assertIn(
            fixture_text,
            json.dumps(server_mod._agent_run_record(run), ensure_ascii=False),
        )

    def test_agent_protocol_shadow_is_fail_open_and_diagnostics_are_bounded(self):
        with mock.patch.object(server_mod, "_AGENT_PROTOCOL_SHADOW_ENABLED", True):
            run = server_mod._create_agent_run(
                "shadow-fail-open-session",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "continue"}],
                },
                self.base_url,
                [],
                start_worker=False,
            )
            with mock.patch.object(
                server_mod.agent_protocol,
                "normalize_agent_event",
                side_effect=RuntimeError("sensitive fixture detail"),
            ):
                event = server_mod._append_agent_event(
                    run,
                    "model_pending",
                    {"round": 1},
                )

            shadow_state = run["protocol_shadow"]
            for index in range(
                server_mod._AGENT_PROTOCOL_SHADOW_DIAGNOSTIC_LIMIT + 6
            ):
                server_mod._record_agent_protocol_shadow_diagnostic(
                    shadow_state,
                    {
                        "code": f"fixture_{index}",
                        "message": "sk-sensitive-value-must-not-be-retained",
                        "path": "data.secret",
                    },
                    source="test-source",
                    event_type="future-sensitive-event",
                    seq=index + 10,
                )
            shadow = server_mod._agent_protocol_shadow_snapshot(run)

        self.assertIsNotNone(event)
        self.assertEqual(run["events"][-1]["type"], "model_pending")
        self.assertEqual(shadow["contractErrors"], 1)
        self.assertLessEqual(
            len(shadow["diagnostics"]),
            server_mod._AGENT_PROTOCOL_SHADOW_DIAGNOSTIC_LIMIT,
        )
        self.assertGreater(shadow["diagnosticsDropped"], 0)
        self.assertLessEqual(
            len(shadow["diagnosticCounts"]),
            server_mod._AGENT_PROTOCOL_SHADOW_DIAGNOSTIC_LIMIT,
        )
        encoded = json.dumps(shadow, ensure_ascii=False)
        self.assertNotIn("sensitive fixture detail", encoded)
        self.assertNotIn("sk-sensitive-value", encoded)
        self.assertNotIn("data.secret", encoded)
        self.assertTrue(all(
            set(item) == {"code", "severity", "source", "eventType", "seq"}
            for item in shadow["diagnostics"]
        ))

    def test_agent_protocol_shadow_can_be_disabled_without_changing_events(self):
        with mock.patch.object(server_mod, "_AGENT_PROTOCOL_SHADOW_ENABLED", False):
            run = server_mod._create_agent_run(
                "shadow-disabled-session",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "continue"}],
                },
                self.base_url,
                [],
                start_worker=False,
            )
            event = server_mod._append_agent_event(
                run,
                "model_pending",
                {"round": 1},
            )
            shadow = server_mod._agent_protocol_shadow_snapshot(run)

        self.assertIsNone(run["protocol_shadow"])
        self.assertFalse(shadow["enabled"])
        self.assertEqual(shadow["eventsObserved"], 0)
        self.assertEqual(event["seq"], 2)

    def test_agent_protocol_shadow_restores_at_persisted_cursor(self):
        with mock.patch.object(server_mod, "_AGENT_PROTOCOL_SHADOW_ENABLED", True):
            run = server_mod._create_agent_run(
                "shadow-restore-session",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "continue"}],
                },
                self.base_url,
                [],
                start_worker=False,
            )
            record = server_mod._agent_run_record(run)
            restored = server_mod._agent_run_from_record(record)
            self.assertEqual(restored["status"], "waiting_credentials")
            server_mod._set_agent_status(restored, "model")
            server_mod._append_agent_event(
                restored,
                "resumed",
                {"status": "model"},
            )
            shadow = server_mod._agent_protocol_shadow_snapshot(restored)

        self.assertEqual(shadow["eventsObserved"], 1)
        self.assertEqual(shadow["eventsAccepted"], 1)
        self.assertEqual(shadow["transitionsObserved"], 1)
        self.assertEqual(shadow["lastRunStatus"], "model")
        self.assertNotIn("event_sequence_gap", shadow["diagnosticCounts"])
        self.assertNotIn("out_of_order_event", shadow["diagnosticCounts"])

    def test_agent_protocol_shadow_observes_complete_terminal_chain(self):
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [[
                {
                    "choices": [{
                        "delta": {"content": "shadow validation complete"},
                        "finish_reason": "stop",
                    }],
                },
                {
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 3,
                        "completion_tokens": 4,
                        "total_tokens": 7,
                    },
                },
            ]]
        with mock.patch.object(server_mod, "_AGENT_PROTOCOL_SHADOW_ENABLED", True):
            run = server_mod._create_agent_run(
                "shadow-terminal-session",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "complete"}],
                },
                self.base_url,
                ["shadow-runtime-key"],
                allowed_tools=[],
            )
            self._wait_terminal(run)
            shadow = server_mod._agent_protocol_shadow_snapshot(run)

        self.assertEqual(run["status"], "completed")
        self.assertEqual(shadow["eventsObserved"], len(run["events"]))
        self.assertEqual(shadow["eventsAccepted"], len(run["events"]))
        self.assertEqual(shadow["lastRunStatus"], "completed")
        self.assertEqual(shadow["contractErrors"], 0)
        for unexpected in (
            "event_sequence_gap",
            "out_of_order_event",
            "missing_payload_fields",
            "illegal_state_transition",
            "unknown_event_type",
        ):
            self.assertNotIn(unexpected, shadow["diagnosticCounts"])

    def test_agent_protocol_shadow_accepts_all_h0_trace_events(self):
        suite_path = (
            Path(__file__).parent
            / "fixtures"
            / "harness"
            / "trace-suite.json"
        )
        suite = json.loads(suite_path.read_text(encoding="utf-8"))
        with mock.patch.object(server_mod, "_AGENT_PROTOCOL_SHADOW_ENABLED", True):
            for fixture in suite["fixtures"]:
                with self.subTest(fixture=fixture["name"]):
                    run = {
                        "condition": threading.Condition(threading.RLock()),
                        "status": "model",
                        "protocol_shadow": server_mod._new_agent_protocol_shadow(
                            "model",
                            0,
                        ),
                    }
                    for event in fixture["events"]:
                        server_mod._agent_protocol_shadow_observe(
                            run,
                            event,
                            source="append",
                        )
                    shadow = server_mod._agent_protocol_shadow_snapshot(run)
                    self.assertEqual(
                        shadow["eventsObserved"],
                        len(fixture["events"]),
                    )
                    self.assertEqual(
                        shadow["eventsAccepted"],
                        len(fixture["events"]),
                    )
                    self.assertEqual(shadow["contractErrors"], 0)
                    self.assertNotIn(
                        "event_sequence_gap",
                        shadow["diagnosticCounts"],
                    )
                    self.assertNotIn(
                        "out_of_order_event",
                        shadow["diagnosticCounts"],
                    )

    def test_agent_protocol_shadow_bounds_sequence_fingerprints(self):
        with mock.patch.object(server_mod, "_AGENT_PROTOCOL_SHADOW_ENABLED", True):
            run = {
                "condition": threading.Condition(threading.RLock()),
                "status": "model",
                "protocol_shadow": server_mod._new_agent_protocol_shadow(
                    "model",
                    0,
                ),
            }
            event_count = server_mod._AGENT_PROTOCOL_SHADOW_FINGERPRINT_LIMIT + 12
            for seq in range(1, event_count + 1):
                server_mod._agent_protocol_shadow_observe(
                    run,
                    {
                        "seq": seq,
                        "type": "model_pending",
                        "data": {"round": seq},
                        "createdAt": "2030-01-01T00:00:00Z",
                    },
                    source="append",
                )
            shadow = server_mod._agent_protocol_shadow_snapshot(run)

        self.assertEqual(shadow["eventsAccepted"], event_count)
        self.assertEqual(
            len(run["protocol_shadow"]["validator"].fingerprints),
            server_mod._AGENT_PROTOCOL_SHADOW_FINGERPRINT_LIMIT,
        )
        self.assertNotIn(1, run["protocol_shadow"]["validator"].fingerprints)
        self.assertIn(event_count, run["protocol_shadow"]["validator"].fingerprints)

    def test_agent_auto_compacts_after_tool_result_and_continues_same_run(self):
        (self.project_dir / "large.txt").write_text("x" * 12000, encoding="utf-8")
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                [
                    {"choices": [{
                        "delta": {"tool_calls": [{
                            "index": 0,
                            "id": "compact-read-1",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"path": "large.txt"}),
                            },
                        }]},
                        "finish_reason": "tool_calls",
                    }]},
                    {"choices": [], "usage": {
                        "prompt_tokens": 5,
                        "completion_tokens": 4,
                        "total_tokens": 9,
                    }},
                ],
                [
                    {"choices": [{
                        "delta": {"content": "Older investigation was summarized."},
                        "finish_reason": "stop",
                    }]},
                    {"choices": [], "usage": {
                        "prompt_tokens": 4,
                        "completion_tokens": 2,
                        "total_tokens": 6,
                    }},
                ],
                [
                    {"choices": [{
                        "delta": {"content": "task continued after compaction"},
                        "finish_reason": "stop",
                    }]},
                    {"choices": [], "usage": {
                        "prompt_tokens": 5,
                        "completion_tokens": 2,
                        "total_tokens": 7,
                    }},
                ],
            ]
        run = server_mod._create_agent_run(
            "session-auto-compact",
            {
                "model": "test-model",
                "max_tokens": 1024,
                "messages": [
                    {"role": "system", "content": "system rules"},
                    {"role": "user", "content": "older investigation"},
                    {"role": "assistant", "content": "older checkpoint"},
                    {"role": "user", "content": "inspect the large file and continue"},
                ],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["read_file"]],
            },
            self.base_url,
            ["agent-secret-key", "agent-secondary-key"],
            allowed_tools=["read_file"],
            context_budget_tokens=8192,
            start_worker=False,
        )
        initial_payload, _ = server_mod._agent_model_payload(run)
        self.assertFalse(server_mod._agent_should_auto_compact(
            initial_payload,
            run["context_limit"],
            run["compression_trigger_tokens"],
        ))

        server_mod._start_agent_worker(run)
        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)

        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "task continued after compaction")
        self.assertEqual(snapshot["round"], 2)
        self.assertEqual(snapshot["usage"]["total_tokens"], 22)
        self.assertEqual(_AgentUpstream.calls, 3)
        self.assertEqual(len(snapshot["compactions"]), 1)
        self.assertEqual(snapshot["compactions"][0]["reason"], "threshold")
        self.assertTrue(any(
            str(message.get("content") or "").startswith(
                server_mod._AGENT_CONTEXT_SUMMARY_PREFIX,
            )
            for message in run["messages"]
        ))
        self.assertTrue(any(
            message.get("role") == "tool"
            and message.get("tool_call_id") == "compact-read-1"
            for message in run["messages"]
        ))
        event_types = [event["type"] for event in snapshot["events"]]
        self.assertLess(
            event_types.index("tool_completed"),
            event_types.index("context_compaction_started"),
        )
        self.assertLess(
            event_types.index("context_compaction_started"),
            event_types.index("context_compaction_completed"),
        )
        with server_mod._agent_run_lock:
            server_mod._agent_runs.pop(run["id"], None)
        restored = server_mod._get_agent_run(run["id"])
        self.assertEqual(len(restored["compactions"]), 1)
        self.assertTrue(any(
            event["type"] == "context_compaction_completed"
            for event in restored["events"]
        ))

    def test_agent_recovers_once_from_upstream_context_error(self):
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                {
                    "http_error": 400,
                    "message": "maximum context length exceeded for this model",
                },
                [
                    {"choices": [{
                        "delta": {"content": "Recovered history summary."},
                        "finish_reason": "stop",
                    }]},
                    {"choices": [], "usage": {
                        "prompt_tokens": 4,
                        "completion_tokens": 2,
                        "total_tokens": 6,
                    }},
                ],
                [
                    {"choices": [{
                        "delta": {"content": "recovered after context overflow"},
                        "finish_reason": "stop",
                    }]},
                    {"choices": [], "usage": {
                        "prompt_tokens": 5,
                        "completion_tokens": 2,
                        "total_tokens": 7,
                    }},
                ],
            ]
        run = server_mod._create_agent_run(
            "session-context-recovery",
            {
                "model": "test-model",
                "messages": [
                    {"role": "system", "content": "system rules"},
                    {"role": "user", "content": "old task"},
                    {"role": "assistant", "content": "old result"},
                    {"role": "user", "content": "current task"},
                ],
            },
            self.base_url,
            ["agent-secret-key"],
            context_limit=128000,
        )

        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)

        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "recovered after context overflow")
        self.assertEqual(snapshot["round"], 1)
        self.assertEqual(snapshot["usage"]["total_tokens"], 13)
        self.assertEqual(run["context_recovery_round"], 1)
        self.assertEqual(_AgentUpstream.calls, 3)
        self.assertEqual(
            _AgentUpstream.authorizations,
            ["Bearer agent-secret-key"] * 3,
        )
        self.assertEqual(len(snapshot["compactions"]), 1)
        self.assertEqual(
            snapshot["compactions"][0]["reason"],
            "context_window_exceeded",
        )
        attribution = run["context_failure_attribution"]
        self.assertEqual(attribution["upstreamStatus"], 400)
        self.assertEqual(attribution["evidenceKind"], "heuristic")
        self.assertIsNone(attribution["explicitMaximumTokens"])
        self.assertEqual(
            attribution["keyFingerprint"],
            server_mod.context_calibration.key_fingerprint("agent-secret-key"),
        )
        self.assertNotIn("contextFailureAttribution", snapshot)
        record = server_mod._agent_run_record(run)
        self.assertEqual(record["contextFailureAttribution"], attribution)
        self.assertNotIn("agent-secret-key", json.dumps(record, ensure_ascii=False))
        restored = server_mod._agent_run_from_record(record)
        self.assertEqual(restored["context_failure_attribution"], attribution)
        self.assertEqual(snapshot["contextLimit"], 64_000)
        self.assertEqual(snapshot["calibrationCapTokens"], 64_000)
        self.assertEqual(snapshot["calibrationEvidenceKind"], "heuristic")
        self.assertTrue(snapshot["calibrationApplied"])
        self.assertFalse(run.get("pending_context_calibration"))
        stored = server_mod._context_calibration_store().resolve(
            attribution["scopeId"]
        )
        self.assertEqual(stored["capTokens"], 64_000)
        self.assertEqual(stored["evidenceKind"], "heuristic")

    def test_agent_context_recovery_is_bounded_to_one_attempt_per_round(self):
        context_error = {
            "http_error": 400,
            "message": "maximum context length exceeded for this model",
        }
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                context_error,
                [{
                    "choices": [{
                        "delta": {"content": "One recovery summary."},
                        "finish_reason": "stop",
                    }],
                }],
                context_error,
            ]
        run = server_mod._create_agent_run(
            "session-context-recovery-bounded",
            {
                "model": "test-model",
                "messages": [
                    {"role": "user", "content": "old task"},
                    {"role": "assistant", "content": "old result"},
                    {"role": "user", "content": "current task"},
                ],
            },
            self.base_url,
            ["agent-secret-key"],
            context_budget_tokens=128000,
        )

        self._wait_status(run, "waiting_recovery")
        snapshot = server_mod._agent_snapshot(run, 0)

        self.assertEqual(snapshot["status"], "waiting_recovery")
        self.assertEqual(snapshot["errorCode"], "context_recovery_required")
        self.assertEqual(snapshot["recoveryState"]["kind"], "context_compaction_failed")
        self.assertEqual(_AgentUpstream.calls, 3)
        self.assertEqual(len(snapshot["compactions"]), 1)
        self.assertEqual(snapshot["contextLimit"], 128_000)
        self.assertIsNone(snapshot["calibrationCapTokens"])
        self.assertFalse(snapshot["calibrationApplied"])
        self.assertFalse(run.get("pending_context_calibration"))
        self.assertFalse((self.data_dir / "context-calibrations.json").exists())

    def test_explicit_context_calibration_commits_before_accepting_model_result(self):
        context_error = {
            "http_error": 400,
            "code": "context_length_exceeded",
            "max_context_tokens": 200_000,
            "message": (
                "maximum context length is 200000 tokens; "
                "requested 420000 tokens"
            ),
        }
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                context_error,
                [{"choices": [{
                    "delta": {"content": "Explicit recovery summary."},
                    "finish_reason": "stop",
                }]}],
                [{"choices": [{
                    "delta": {"content": "explicit recovery complete"},
                    "finish_reason": "stop",
                }]}],
            ]
        run = server_mod._create_agent_run(
            "session-explicit-calibration",
            {
                "model": "gpt-5.6",
                "messages": [
                    {"role": "user", "content": "old task"},
                    {"role": "assistant", "content": "old result"},
                    {"role": "user", "content": "current task"},
                ],
            },
            self.base_url,
            ["explicit-key-a", "explicit-key-b"],
            context_limit=1_000_000,
        )
        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)

        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["contextLimit"], 200_000)
        self.assertEqual(snapshot["calibrationCapTokens"], 200_000)
        self.assertEqual(snapshot["calibrationEvidenceKind"], "explicit_max")
        self.assertTrue(snapshot["calibrationApplied"])
        self.assertTrue(snapshot["calibrationExpiresAt"])
        self.assertEqual(_AgentUpstream.calls, 3)
        self.assertEqual(_AgentUpstream.authorizations, ["Bearer explicit-key-a"] * 3)

        same_scope = server_mod._create_agent_run(
            "session-explicit-next",
            {
                "model": "gpt-5.6",
                "messages": [{"role": "user", "content": "next task"}],
            },
            self.base_url,
            ["explicit-key-a", "explicit-key-b"],
            start_worker=False,
        )
        other_key = server_mod._create_agent_run(
            "session-explicit-other-key",
            {
                "model": "gpt-5.6",
                "messages": [{"role": "user", "content": "other key task"}],
            },
            self.base_url,
            ["explicit-key-b"],
            start_worker=False,
        )
        self.assertEqual(same_scope["context_limit"], 200_000)
        self.assertTrue(same_scope["calibration_applied"])
        self.assertEqual(other_key["context_limit"], 1_050_000)
        self.assertFalse(other_key["calibration_applied"])

    def test_calibration_store_failure_discards_tool_result_and_executes_nothing(self):
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                {
                    "http_error": 400,
                    "code": "context_length_exceeded",
                    "max_context_tokens": 64_000,
                    "message": "maximum context length is 64000 tokens",
                },
                [{"choices": [{
                    "delta": {"content": "Store failure recovery summary."},
                    "finish_reason": "stop",
                }]}],
                [{"choices": [{
                    "delta": {"tool_calls": [{
                        "index": 0,
                        "id": "store-failure-read",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path":"README.md"}',
                        },
                    }]},
                    "finish_reason": "tool_calls",
                }]}],
            ]
        with mock.patch.object(
            server_mod.context_calibration.ContextCalibrationStore,
            "record_success",
            side_effect=server_mod.context_calibration.CalibrationStorageUnavailable(
                "storage_unavailable"
            ),
        ):
            run = server_mod._create_agent_run(
                "session-calibration-store-failure",
                {
                    "model": "gpt-5.6",
                    "messages": [
                        {"role": "user", "content": "old task"},
                        {"role": "assistant", "content": "old result"},
                        {"role": "user", "content": "current task"},
                    ],
                },
                self.base_url,
                ["store-failure-key", "unused-key"],
                allowed_tools=["read_file"],
                context_limit=400_000,
            )
            self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["errorCode"], "calibration_storage_unavailable")
        self.assertEqual(snapshot["toolExecutions"], [])
        self.assertEqual(snapshot["round"], 0)
        self.assertEqual(_AgentUpstream.authorizations, ["Bearer store-failure-key"] * 3)
        self.assertFalse((self.data_dir / "context-calibrations.json").exists())

    def test_pending_recovery_requires_the_same_key_after_credentials_restore(self):
        run = server_mod._create_agent_run(
            "session-pending-calibration-key",
            {
                "model": "test-model",
                "messages": [
                    {"role": "user", "content": "old task"},
                    {"role": "assistant", "content": "old result"},
                    {"role": "user", "content": "current task"},
                ],
            },
            self.base_url,
            ["pending-key-a"],
            start_worker=False,
        )
        scope = server_mod.context_calibration.calibration_scope(
            self.base_url, "pending-key-a", "test-model",
        )
        run["context_failure_attribution"] = (
            server_mod.context_calibration.context_failure_attribution(
                scope,
                400,
                server_mod.context_calibration.classify_context_failure(
                    400,
                    code="context_length_exceeded",
                    message="context length exceeded",
                ),
            )
        )
        pending = server_mod._agent_prepare_context_calibration(run, 1)
        self.assertIsNotNone(pending)
        record = server_mod._agent_run_record(run)
        run = server_mod._agent_run_from_record(record)
        self.assertEqual(run["status"], "waiting_credentials")
        self.assertEqual(run["pending_context_calibration"], pending)
        with server_mod._agent_run_lock:
            server_mod._agent_runs[run["id"]] = run

        server_mod._resume_agent_run(run, ["pending-key-b"], self.base_url)
        self._wait_status(run, "waiting_credentials")
        self.assertEqual(_AgentUpstream.calls, 0)
        self.assertIsNotNone(run["pending_context_calibration"])
        self.assertEqual(run["context_limit"], 64_000)

    def test_cancelled_pending_calibration_rolls_back_without_store_write(self):
        run = server_mod._create_agent_run(
            "session-cancelled-calibration",
            {
                "model": "test-model",
                "messages": [
                    {"role": "user", "content": "old task"},
                    {"role": "assistant", "content": "old result"},
                    {"role": "user", "content": "current task"},
                ],
            },
            self.base_url,
            ["cancel-calibration-key"],
            start_worker=False,
        )
        scope = server_mod.context_calibration.calibration_scope(
            self.base_url, "cancel-calibration-key", "test-model",
        )
        run["context_failure_attribution"] = (
            server_mod.context_calibration.context_failure_attribution(
                scope,
                400,
                server_mod.context_calibration.classify_context_failure(
                    400,
                    code="context_length_exceeded",
                    message="context length exceeded",
                ),
            )
        )
        self.assertIsNotNone(server_mod._agent_prepare_context_calibration(run, 1))
        self.assertEqual(run["context_limit"], 64_000)
        run["cancel_event"].set()
        server_mod._start_agent_worker(run)
        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "cancelled")
        self.assertEqual(snapshot["contextLimit"], 128_000)
        self.assertFalse(snapshot["calibrationApplied"])
        self.assertFalse(run.get("pending_context_calibration"))
        self.assertFalse((self.data_dir / "context-calibrations.json").exists())
        self.assertEqual(_AgentUpstream.calls, 0)

    def test_client_request_id_reuses_same_agent_run_after_memory_reset(self):
        payload = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "durable background task"}],
        }
        first = server_mod._create_agent_run(
            "background-session",
            payload,
            self.base_url,
            ["secret-key"],
            start_worker=False,
            client_request_id="background-123",
        )
        first_id = first["id"]
        self.assertEqual(first["client_request_id"], "background-123")
        self.assertTrue(server_mod._agent_run_path(first_id).is_file())

        with server_mod._agent_run_lock:
            server_mod._agent_runs.clear()
        replay = server_mod._create_agent_run(
            "background-session",
            payload,
            self.base_url,
            ["replacement-key"],
            start_worker=False,
            client_request_id="background-123",
        )
        self.assertEqual(replay["id"], first_id)
        self.assertEqual(replay["client_request_id"], "background-123")
        self.assertEqual(len(list(server_mod._agent_runs_dir().glob("*.json"))), 1)
        self.assertNotIn("secret-key", json.dumps(server_mod._agent_run_record(replay)))
        self.assertNotIn("replacement-key", json.dumps(server_mod._agent_run_record(replay)))

    def test_client_request_id_rejects_unsafe_values(self):
        with self.assertRaisesRegex(ValueError, "clientRequestId"):
            server_mod._create_agent_run(
                "background-session",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "invalid id"}],
                },
                self.base_url,
                [],
                start_worker=False,
                client_request_id="../not-safe",
            )

    def test_agent_continues_without_browser_polling_and_executes_read_only_loop(self):
        run = server_mod._create_agent_run(
            "session-agent",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "inspect the project"}],
                "tools": [
                    server_mod._SERVER_TOOL_DEFINITIONS["read_file"],
                    {"type": "function", "function": {"name": "write_file", "parameters": {}}},
                ],
            },
            self.base_url,
            ["agent-secret-key"],
            allowed_tools=["read_file", "write_file"],
        )

        # Do not read a snapshot until the worker has reached a terminal state.
        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)

        self.assertEqual(run["status"], "completed")
        self.assertEqual(_AgentUpstream.calls, 2)
        self.assertEqual(snapshot["allowedTools"], ["read_file"])
        self.assertEqual(snapshot["round"], 2)
        self.assertEqual(snapshot["result"]["content"], "read-only task complete")
        self.assertEqual(snapshot["usage"]["total_tokens"], 20)
        self.assertEqual(len(snapshot["toolExecutions"]), 1)
        self.assertEqual(snapshot["toolExecutions"][0]["name"], "read_file")
        self.assertEqual(snapshot["toolExecutions"][0]["status"], "completed")
        self.assertIn("Durable Agent", json.dumps(snapshot["toolExecutions"][0]["result"]))
        self.assertEqual(run["keys"], [])
        self.assertEqual(
            [item["function"]["name"] for item in _AgentUpstream.payloads[0]["tools"]],
            ["read_file"],
        )
        event_types = [event["type"] for event in snapshot["events"]]
        for expected in (
            "created", "model_started", "model_completed", "tool_started",
            "tool_completed", "completed",
        ):
            self.assertIn(expected, event_types)

        persisted = server_mod._agent_run_path(run["id"]).read_text(encoding="utf-8")
        self.assertNotIn("agent-secret-key", persisted)
        self.assertNotIn("agent-secret-key", json.dumps(snapshot))
        self.assertEqual(_AgentUpstream.authorizations, ["Bearer agent-secret-key"] * 2)

    def test_agent_stops_when_first_meaningful_model_response_times_out(self):
        with mock.patch.object(
            server_mod,
            "_MODEL_RUNTIME_FIRST_RESPONSE_TIMEOUT",
            0.12,
        ):
            started = time.monotonic()
            run = server_mod._create_agent_run(
                "session-first-response-timeout",
                {
                    "model": "test-model",
                    "messages": [{
                        "role": "user",
                        "content": "never produce a first response",
                    }],
                },
                self.base_url,
                ["agent-secret-key"],
            )
            self._wait_terminal(run)
            elapsed = time.monotonic() - started

        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["errorCode"], "model_response_timeout")
        self.assertIn("0.12 seconds", snapshot["error"])
        self.assertLess(elapsed, 0.5)
        self.assertEqual(_AgentUpstream.calls, 1)
        self.assertEqual(run["active_runtime_id"], "")

    def test_midrun_stream_failure_survives_restart_and_reuses_completed_tool(self):
        private_reasoning = "private recovery reasoning must not persist"
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                [{
                    "choices": [{
                        "delta": {"tool_calls": [{
                            "index": 0,
                            "id": "recovery-read-1",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"path": "README.md"}),
                            },
                        }]},
                        "finish_reason": "tool_calls",
                    }],
                }],
                {
                    "partial_then_disconnect": True,
                    "content": "partial response after completed tool",
                    "reasoning": private_reasoning,
                },
                [{
                    "choices": [{
                        "delta": {"content": "recovered on the same AgentRun"},
                        "finish_reason": "stop",
                    }],
                }],
            ]

        original_execute = server_mod.execute_registered_tool
        with mock.patch.object(
            server_mod,
            "execute_registered_tool",
            wraps=original_execute,
        ) as execute_mock:
            run = server_mod._create_agent_run(
                "session-midrun-stream-recovery",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "read then recover"}],
                    "tools": [server_mod._SERVER_TOOL_DEFINITIONS["read_file"]],
                },
                self.base_url,
                ["recovery-key"],
                allowed_tools=["read_file"],
            )
            self._wait_status(run, "waiting_recovery")
            self._wait_worker_idle(run)

            self.assertEqual(execute_mock.call_count, 1)
            self.assertEqual(_AgentUpstream.calls, 2)
            snapshot = server_mod._agent_snapshot(run, 0)
            self.assertEqual(snapshot["errorCode"], "agent_recovery_required")
            self.assertEqual(snapshot["recoveryState"]["kind"], "model_interrupted")
            self.assertNotIn("modelCheckpoint", snapshot)
            record = server_mod._agent_run_record(run)
            self.assertEqual(
                record["modelCheckpoint"]["content"],
                "partial response after completed tool",
            )
            self.assertTrue(record["modelCheckpoint"]["hasReasoning"])
            self.assertNotIn(private_reasoning, json.dumps(record, ensure_ascii=False))
            runtime_ids = [
                event["data"]["runtimeRunId"]
                for event in run["events"]
                if event["type"] == "model_started"
            ]
            self.assertEqual(len(runtime_ids), 2)
            self.assertIsNotNone(
                server_mod._model_runtime_runs[runtime_ids[0]]["first_response_timeout"],
            )
            self.assertIsNone(
                server_mod._model_runtime_runs[runtime_ids[1]]["first_response_timeout"],
            )

            run_id = run["id"]
            with server_mod._agent_run_lock:
                server_mod._agent_runs.pop(run_id, None)
            restored = server_mod._get_agent_run(run_id)
            self.assertEqual(restored["id"], run_id)
            self.assertEqual(restored["status"], "waiting_recovery")
            server_mod._resume_agent_run(
                restored,
                ["recovery-key"],
                self.base_url,
            )
            self._wait_terminal(restored)

            self.assertEqual(execute_mock.call_count, 1)

        self.assertEqual(restored["status"], "completed")
        self.assertEqual(restored["result"]["content"], "recovered on the same AgentRun")
        self.assertEqual(_AgentUpstream.calls, 3)
        self.assertIsNone(restored.get("model_checkpoint"))
        self.assertIsNone(restored.get("recovery_state"))
        self.assertEqual(
            sum(message.get("role") == "user" for message in restored["messages"]),
            1,
        )
        self.assertEqual(
            sum(message.get("role") == "tool" for message in restored["messages"]),
            1,
        )
        recovery_payload = _AgentUpstream.payloads[-1]
        recovery_messages = recovery_payload["messages"]
        self.assertEqual(
            sum(message.get("role") == "user" for message in recovery_messages),
            1,
        )
        self.assertTrue(any(
            message.get("role") == "system"
            and "partial response after completed tool" in str(message.get("content") or "")
            for message in recovery_messages
        ))
        self.assertNotIn(private_reasoning, json.dumps(recovery_payload, ensure_ascii=False))

    def test_agent_normalizes_read_file_alias_before_execution_and_history(self):
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                [{
                    "choices": [{
                        "delta": {"tool_calls": [{
                            "index": 0,
                            "id": "alias-read-1",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({
                                    "file_path": "README.md",
                                }),
                            },
                        }]},
                        "finish_reason": "tool_calls",
                    }],
                }],
                [{
                    "choices": [{
                        "delta": {"content": "README starts with Durable Agent."},
                        "finish_reason": "stop",
                    }],
                }],
            ]

        run = server_mod._create_agent_run(
            "session-read-alias",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "read README"}],
            },
            self.base_url,
            ["alias-key"],
            allowed_tools=["read_file"],
            max_rounds=3,
        )
        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)

        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(len(snapshot["toolExecutions"]), 1)
        execution = snapshot["toolExecutions"][0]
        self.assertEqual(execution["outcome"], "succeeded")
        self.assertEqual(json.loads(execution["arguments"]), {
            "path": "README.md",
        })
        self.assertEqual(execution["argumentAliases"], [{
            "from": "file_path",
            "to": "path",
        }])
        self.assertTrue(execution["result"]["ok"])
        started_event = next(
            event for event in snapshot["events"]
            if event["type"] == "tool_started"
        )
        self.assertEqual(json.loads(started_event["data"]["arguments"]), {
            "path": "README.md",
        })
        self.assertEqual(started_event["data"]["argumentAliases"], [{
            "from": "file_path",
            "to": "path",
        }])
        completed_event = next(
            event for event in snapshot["events"]
            if event["type"] == "tool_completed"
        )
        self.assertEqual(completed_event["data"]["outcome"], "succeeded")
        self.assertEqual(completed_event["data"]["argumentAliases"], [{
            "from": "file_path",
            "to": "path",
        }])
        assistant_tool_call = next(
            message for message in run["messages"]
            if message.get("role") == "assistant" and message.get("tool_calls")
        )
        self.assertEqual(
            json.loads(
                assistant_tool_call["tool_calls"][0]["function"]["arguments"]
            ),
            {"path": "README.md"},
        )

    def test_agent_rejects_invalid_tool_arguments_without_calling_executor(self):
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                [{
                    "choices": [{
                        "delta": {"tool_calls": [{
                            "index": 0,
                            "id": "invalid-read-1",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({
                                    "unexpected": "README.md",
                                }),
                            },
                        }]},
                        "finish_reason": "tool_calls",
                    }],
                }],
                [{
                    "choices": [{
                        "delta": {
                            "content": "The tool arguments were invalid."
                        },
                        "finish_reason": "stop",
                    }],
                }],
            ]

        with mock.patch.object(
            server_mod,
            "execute_registered_tool",
            wraps=server_mod.execute_registered_tool,
        ) as execute_mock:
            run = server_mod._create_agent_run(
                "session-invalid-tool-arguments",
                {
                    "model": "test-model",
                    "messages": [{
                        "role": "user",
                        "content": "send invalid read arguments",
                    }],
                },
                self.base_url,
                ["invalid-argument-key"],
                allowed_tools=["read_file"],
                max_rounds=3,
            )
            self._wait_terminal(run)

        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(execute_mock.call_count, 0)
        execution = snapshot["toolExecutions"][0]
        self.assertEqual(execution["status"], "completed")
        self.assertEqual(execution["outcome"], "failed")
        self.assertEqual(
            execution["result"]["errorCode"], "invalid_tool_arguments",
        )
        completed_event = next(
            event for event in snapshot["events"]
            if event["type"] == "tool_completed"
        )
        self.assertEqual(completed_event["data"]["outcome"], "failed")
        self.assertEqual(
            {(item["field"], item["reason"])
             for item in execution["result"]["fieldErrors"]},
            {
                ("path", "required"),
                ("unexpected", "additional_property"),
            },
        )

    def test_agent_blocks_fourth_identical_failure_and_forces_one_final_round(self):
        tool_rounds = []
        for index in range(1, 5):
            tool_rounds.append([{
                "choices": [{
                    "delta": {"tool_calls": [{
                        "index": 0,
                        "id": f"repeat-failure-{index}",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"path": "missing.txt"}),
                        },
                    }]},
                    "finish_reason": "tool_calls",
                }],
            }])
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = tool_rounds + [[{
                "choices": [{
                    "delta": {
                        "content": "I could not verify the missing file."
                    },
                    "finish_reason": "stop",
                }],
            }]]

        failing_executor = mock.Mock(
            side_effect=ValueError("synthetic file failure"),
        )
        with mock.patch.dict(
            server_mod.SERVER_TOOL_REGISTRY["read_file"],
            {"execute": failing_executor},
        ):
            run = server_mod._create_agent_run(
                "session-identical-tool-failure",
                {
                    "model": "test-model",
                    "messages": [{
                        "role": "user",
                        "content": "repeat the same failing read",
                    }],
                },
                self.base_url,
                ["repeat-failure-key"],
                allowed_tools=["read_file"],
                max_rounds=6,
            )
            self._wait_terminal(run)

        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(failing_executor.call_count, 3)
        self.assertEqual(_AgentUpstream.calls, 5)
        self.assertEqual(len(snapshot["toolExecutions"]), 4)
        self.assertTrue(
            snapshot["toolExecutions"][-1]["result"]["retryBlocked"],
        )
        self.assertEqual(
            snapshot["toolExecutions"][-1]["result"]["errorCode"],
            "repeated_tool_failure",
        )
        self.assertEqual(
            [event["type"] for event in snapshot["events"]].count(
                "tool_retry_blocked"
            ),
            1,
        )
        self.assertNotIn("tools", _AgentUpstream.payloads[-1])
        self.assertTrue(any(
            message.get("role") == "system"
            and "identical tool call was blocked" in str(
                message.get("content") or ""
            )
            for message in _AgentUpstream.payloads[-1]["messages"]
        ))
        self.assertFalse(snapshot["forceFinalRound"])
        with server_mod._agent_run_lock:
            server_mod._agent_runs.pop(run["id"], None)
        restored = server_mod._get_agent_run(run["id"])
        self.assertTrue(all(
            execution.get("outcome") == "failed"
            for execution in restored["tool_executions"].values()
        ))

    def test_agent_rejects_forced_final_tool_call_without_executing_it(self):
        tool_rounds = []
        for index in range(1, 5):
            tool_rounds.append([{
                "choices": [{
                    "delta": {"tool_calls": [{
                        "index": 0,
                        "id": f"forced-final-failure-{index}",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"path": "missing.txt"}),
                        },
                    }]},
                    "finish_reason": "tool_calls",
                }],
            }])
        unusable_tool_call_id = "forced-final-unusable-tool-call"
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = tool_rounds + [[{
                "choices": [{
                    "delta": {"tool_calls": [{
                        "index": 0,
                        "id": unusable_tool_call_id,
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"path": "missing.txt"}),
                        },
                    }]},
                    "finish_reason": "tool_calls",
                }],
            }]]

        failing_executor = mock.Mock(
            side_effect=ValueError("synthetic file failure"),
        )
        with mock.patch.dict(
            server_mod.SERVER_TOOL_REGISTRY["read_file"],
            {"execute": failing_executor},
        ):
            run = server_mod._create_agent_run(
                "session-forced-final-unusable-tool",
                {
                    "model": "test-model",
                    "messages": [{
                        "role": "user",
                        "content": "return an unusable tool call in the forced final round",
                    }],
                },
                self.base_url,
                ["forced-final-unusable-key"],
                allowed_tools=["read_file"],
                max_rounds=6,
            )
            self._wait_terminal(run)

        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["errorCode"], "repeated_tool_failure")
        self.assertEqual(failing_executor.call_count, 3)
        self.assertEqual(_AgentUpstream.calls, 5)
        self.assertNotIn("tools", _AgentUpstream.payloads[-1])
        self.assertNotIn("tool_choice", _AgentUpstream.payloads[-1])
        self.assertTrue(any(
            message.get("role") == "system"
            and "identical tool call was blocked" in str(
                message.get("content") or ""
            )
            for message in _AgentUpstream.payloads[-1]["messages"]
        ))
        self.assertFalse(snapshot["forceFinalRound"])
        self.assertEqual(snapshot["pendingToolCalls"], [])
        self.assertEqual(len(snapshot["toolExecutions"]), 4)
        self.assertNotIn(
            unusable_tool_call_id,
            {execution["toolCallId"] for execution in snapshot["toolExecutions"]},
        )
        event_types = [event["type"] for event in snapshot["events"]]
        self.assertEqual(event_types.count("model_completed"), 5)
        self.assertEqual(event_types.count("tool_started"), 4)
        self.assertEqual(event_types.count("tool_completed"), 4)
        self.assertEqual(event_types.count("tool_retry_blocked"), 1)
        self.assertEqual(event_types[-2:], ["model_completed", "failed"])
        final_model_event = [
            event for event in snapshot["events"]
            if event["type"] == "model_completed"
        ][-1]
        self.assertEqual(
            final_model_event["data"]["toolCalls"][0]["id"],
            unusable_tool_call_id,
        )
        self.assertFalse(any(
            event.get("data", {}).get("toolCallId") == unusable_tool_call_id
            for event in snapshot["events"]
            if event["type"] in {
                "tool_started", "tool_completed", "tool_retry_blocked",
            }
        ))

    def test_agent_allows_changed_arguments_after_three_identical_failures(self):
        scripted_rounds = []
        for index in range(1, 4):
            scripted_rounds.append([{
                "choices": [{
                    "delta": {"tool_calls": [{
                        "index": 0,
                        "id": f"missing-read-{index}",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"path": "missing.txt"}),
                        },
                    }]},
                    "finish_reason": "tool_calls",
                }],
            }])
        scripted_rounds.extend([
            [{
                "choices": [{
                    "delta": {"tool_calls": [{
                        "index": 0,
                        "id": "corrected-read-4",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"path": "README.md"}),
                        },
                    }]},
                    "finish_reason": "tool_calls",
                }],
            }],
            [{
                "choices": [{
                    "delta": {"content": "The corrected read succeeded."},
                    "finish_reason": "stop",
                }],
            }],
        ])
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = scripted_rounds

        def selective_read(payload):
            if payload.get("path") == "missing.txt":
                raise ValueError("synthetic file failure")
            return {
                "ok": True,
                "action": "read_file",
                "path": payload["path"],
                "content": "# Durable Agent",
            }

        with mock.patch.dict(
            server_mod.SERVER_TOOL_REGISTRY["read_file"],
            {"execute": mock.Mock(side_effect=selective_read)},
        ):
            run = server_mod._create_agent_run(
                "session-changed-tool-arguments",
                {
                    "model": "test-model",
                    "messages": [{
                        "role": "user",
                        "content": "correct a repeated failing read",
                    }],
                },
                self.base_url,
                ["changed-argument-key"],
                allowed_tools=["read_file"],
                max_rounds=6,
            )
            self._wait_terminal(run)

        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(len(snapshot["toolExecutions"]), 4)
        self.assertEqual(
            [item["outcome"] for item in snapshot["toolExecutions"]],
            ["failed", "failed", "failed", "succeeded"],
        )
        self.assertTrue(
            snapshot["toolExecutions"][2]["result"]["retryLimitReached"],
        )
        self.assertFalse(snapshot["forceFinalRound"])
        self.assertNotIn(
            "tool_retry_blocked",
            [event["type"] for event in snapshot["events"]],
        )

    def test_identical_failure_guard_requires_the_same_error_streak(self):
        fingerprint = "same-tool-and-arguments"
        run = {"tool_executions": {}}
        for index, error in enumerate(("first error", "second error", "first error")):
            result = {
                "ok": False,
                "action": "read_file",
                "error": error,
            }
            run["tool_executions"][str(index)] = {
                "fingerprint": fingerprint,
                "status": "completed",
                "outcome": "failed",
                "failureSignature": server_mod._agent_tool_failure_signature(
                    result
                ),
                "result": result,
            }
        self.assertEqual(
            server_mod._agent_identical_tool_failure_count(run, fingerprint),
            1,
        )

        success = {"ok": True, "action": "read_file"}
        run["tool_executions"]["success"] = {
            "fingerprint": fingerprint,
            "status": "completed",
            "outcome": "succeeded",
            "result": success,
        }
        self.assertEqual(
            server_mod._agent_identical_tool_failure_count(run, fingerprint),
            0,
        )

    def test_agent_enforces_and_persists_grouped_tool_budgets(self):
        run = server_mod._create_agent_run(
            "session-budget",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "bounded exploration"}],
            },
            self.base_url,
            ["agent-secret-key"],
            allowed_tools=["read_file", "search_files", "glob_files"],
            start_worker=False,
            tool_budgets=[
                {
                    "name": "discovery",
                    "tools": ["search_files", "glob_files", "missing_tool"],
                    "limit": 3,
                    "exhaustedMessage": "synthesize now",
                },
                {"name": "reading", "tools": ["read_file"], "limit": 1},
            ],
        )
        self.assertEqual(run["tool_budgets"][0]["tools"], ["search_files", "glob_files"])
        run["messages"].append({"role": "assistant", "content": "", "tool_calls": []})
        run["pending_tool_calls"] = server_mod._normalize_agent_tool_calls(
            run,
            [
                {"index": 0, "id": "budget-read-1", "function": {"name": "read_file", "arguments": {"path": "README.md"}}},
                {"index": 1, "id": "budget-read-2", "function": {"name": "read_file", "arguments": {"path": "README.md"}}},
            ],
            1,
        )
        run["status"] = "tools"
        self.assertTrue(server_mod._execute_agent_pending_tools(run))
        self.assertIn("Durable Agent", run["tool_executions"]["budget-read-1"]["result"]["content"])
        blocked = run["tool_executions"]["budget-read-2"]["result"]
        self.assertFalse(blocked["ok"])
        self.assertIn("tool budget reading is exhausted", blocked["error"])
        self.assertNotIn(
            "read_file",
            [item["function"]["name"] for item in server_mod._agent_model_tools(run)],
        )

        record = server_mod._agent_run_record(run)
        restored = server_mod._agent_run_from_record(record)
        self.assertEqual(restored["tool_budgets"], run["tool_budgets"])
        self.assertEqual(
            server_mod._agent_snapshot(restored, 0)["toolBudgetUsage"]["reading"],
            2,
        )

    def test_agent_caps_the_entire_tool_message_sent_back_to_the_model(self):
        result = {
            "ok": True,
            "action": "search_files",
            "count": 100,
            "results": [
                {"path": f"file-{index}.py", "matches": ["x" * 5000]}
                for index in range(20)
            ],
        }
        content = server_mod._agent_tool_message_content(result)
        self.assertLessEqual(len(content), server_mod._AGENT_TOOL_MESSAGE_LIMIT)
        compact = json.loads(content)
        self.assertTrue(compact["truncatedForModel"])
        self.assertEqual(compact["action"], "search_files")
        self.assertEqual(compact["count"], 100)
        self.assertGreater(compact["originalCharacters"], server_mod._AGENT_TOOL_MESSAGE_LIMIT)
        self.assertIn("file-0.py", compact["preview"])

    def test_task_tool_requires_plan_accept_or_bypass_permission(self):
        payload = {"tools": [server_mod._SERVER_TOOL_DEFINITIONS["task"]]}
        self.assertEqual(
            server_mod._agent_selected_tools(payload, ["task"], "read"),
            [],
        )
        for profile in ("plan", "accept", "bypass"):
            with self.subTest(profile=profile):
                selected = server_mod._agent_selected_tools(payload, ["task"], profile)
                self.assertEqual(
                    [item["function"]["name"] for item in selected],
                    ["task"],
                )

    def test_plan_delegation_runs_persistent_child_and_merges_usage_once(self):
        run = server_mod._create_agent_run(
            "delegation-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "delegate inspection"}],
                "tools": [
                    server_mod._SERVER_TOOL_DEFINITIONS["task"],
                    server_mod._SERVER_TOOL_DEFINITIONS["read_file"],
                    server_mod._SERVER_TOOL_DEFINITIONS["request_user_input"],
                ],
            },
            self.base_url,
            ["delegation-secret-key"],
            allowed_tools=["task", "read_file", "request_user_input"],
            permission_profile="plan",
        )

        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)
        task_execution = next(
            item for item in snapshot["toolExecutions"] if item["name"] == "task"
        )
        child_id = task_execution["childAgentRunId"]
        child = server_mod._get_agent_run(child_id)
        child_snapshot = server_mod._agent_snapshot(child, 0)

        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "delegation task complete")
        self.assertEqual(snapshot["usage"]["total_tokens"], 38)
        self.assertEqual(task_execution["status"], "completed")
        self.assertEqual(task_execution["result"]["status"], "completed")
        self.assertEqual(task_execution["result"]["result"], "read-only task complete")
        self.assertEqual(child_snapshot["parentAgentRunId"], run["id"])
        self.assertEqual(child_snapshot["parentToolCallId"], "agent-task-1")
        self.assertEqual(child_snapshot["agentDepth"], 1)
        self.assertEqual(child_snapshot["allowedTools"], ["read_file"])
        self.assertEqual(child_snapshot["status"], "completed")
        self.assertEqual(child_snapshot["usage"]["total_tokens"], 20)
        self.assertEqual(_AgentUpstream.calls, 4)
        self.assertTrue(run["tool_executions"]["agent-task-1"]["childUsageMerged"])
        parent_record = server_mod._agent_run_path(run["id"]).read_text(encoding="utf-8")
        child_record = server_mod._agent_run_path(child_id).read_text(encoding="utf-8")
        self.assertNotIn("delegation-secret-key", parent_record)
        self.assertNotIn("delegation-secret-key", child_record)

    def test_same_turn_delegations_use_bounded_concurrency_and_ordered_results(self):
        run = server_mod._create_agent_run(
            "parallel-delegation-session",
            {
                "model": "test-model",
                "messages": [{
                    "role": "user",
                    "content": "delegate parallel children",
                }],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["task"]],
            },
            self.base_url,
            ["parallel-delegation-key"],
            allowed_tools=["task"],
            permission_profile="plan",
        )

        self.assertTrue(_AgentUpstream.parallel_three_started.wait(timeout=3))
        with _AgentUpstream.parallel_lock:
            self.assertEqual(_AgentUpstream.parallel_max_active, 3)
            self.assertEqual(
                set(_AgentUpstream.parallel_prompts_started),
                {"parallel child 1", "parallel child 2", "parallel child 3"},
            )
        started_executions = list(run.get("tool_executions", {}).values())
        self.assertEqual(len(started_executions), 3)
        self.assertTrue(all(item.get("childAgentRunId") for item in started_executions))

        _AgentUpstream.release_parallel.set()
        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)
        task_executions = [
            item for item in snapshot["toolExecutions"] if item["name"] == "task"
        ]
        expected_call_ids = [f"agent-task-{index}" for index in range(1, 5)]
        expected_results = [f"completed parallel child {index}" for index in range(1, 5)]

        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["usage"]["total_tokens"], 34)
        self.assertEqual(
            [item["toolCallId"] for item in task_executions],
            expected_call_ids,
        )
        self.assertEqual(
            [item["result"]["result"] for item in task_executions],
            expected_results,
        )
        self.assertEqual(
            [
                message["tool_call_id"]
                for message in run["messages"]
                if message.get("role") == "tool" and message.get("name") == "task"
            ],
            expected_call_ids,
        )
        with _AgentUpstream.parallel_lock:
            self.assertEqual(_AgentUpstream.parallel_max_active, 3)
            self.assertEqual(
                set(_AgentUpstream.parallel_prompts_started),
                {f"parallel child {index}" for index in range(1, 5)},
            )
        self.assertEqual(_AgentUpstream.calls, 6)

    def test_accept_delegation_proxies_child_file_authorization(self):
        target = self.project_dir / "generated.txt"
        run = server_mod._create_agent_run(
            "delegated-write-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "delegate write child"}],
                "tools": [
                    server_mod._SERVER_TOOL_DEFINITIONS["task"],
                    server_mod._SERVER_TOOL_DEFINITIONS["write_file"],
                ],
            },
            self.base_url,
            ["delegated-write-key"],
            allowed_tools=["task", "write_file"],
            permission_profile="accept",
        )

        self._wait_status(run, "waiting_authorization")
        self._wait_worker_idle(run)
        waiting = server_mod._agent_snapshot(run, 0)
        pending = waiting["pendingAuthorization"]
        child = server_mod._get_agent_run(pending["childAgentRunId"])
        self.assertEqual(pending["action"], "write_file")
        self.assertEqual(pending["path"], "generated.txt")
        self.assertEqual(child["status"], "waiting_authorization")
        self.assertFalse(target.exists())

        forwarded = server_mod._submit_agent_authorization(
            run, pending["authorizationId"], "approved",
        )
        self.assertEqual(forwarded["action"], "task_authorization")
        self.assertEqual(run["status"], "waiting_credentials")
        self.assertEqual(child["status"], "waiting_credentials")
        self.assertFalse(target.exists())

        server_mod._resume_agent_run(run, ["delegated-resume-key"])
        self._wait_terminal(run)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(child["status"], "completed")
        self.assertEqual(target.read_text(encoding="utf-8"), "written by AgentRun\n")
        persisted = (
            server_mod._agent_run_path(run["id"]).read_text(encoding="utf-8")
            + server_mod._agent_run_path(child["id"]).read_text(encoding="utf-8")
        )
        self.assertNotIn("delegated-write-key", persisted)
        self.assertNotIn("delegated-resume-key", persisted)

    def test_cancelling_parent_cancels_active_delegated_child(self):
        run = server_mod._create_agent_run(
            "delegated-cancel-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "delegate slow child"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["task"]],
            },
            self.base_url,
            ["delegated-cancel-key"],
            allowed_tools=["task"],
            permission_profile="plan",
        )

        self.assertTrue(_AgentUpstream.slow_started.wait(timeout=3))
        deadline = time.time() + 2
        child_id = ""
        while not child_id and time.time() < deadline:
            execution = run.get("tool_executions", {}).get("agent-task-1") or {}
            child_id = str(execution.get("childAgentRunId") or "")
            time.sleep(0.01)
        self.assertTrue(child_id)
        child = server_mod._get_agent_run(child_id)

        server_mod._cancel_agent_run(run["id"])
        _AgentUpstream.release_slow.set()
        self._wait_terminal(run)
        self._wait_terminal(child)
        self.assertEqual(run["status"], "cancelled")
        self.assertEqual(child["status"], "cancelled")
        self.assertEqual(run["keys"], [])
        self.assertEqual(child["keys"], [])

    def test_child_system_prompt_uses_chinese_control_without_parent_context_inheritance(self):
        prompt = server_mod._agent_child_system_prompt()

        for expected in (
            "专注的编程子 Agent",
            "只完成被委派的任务",
            "绝不能提升权限",
            "不能再次委派其他 Agent",
            "不能发起交互问卷",
            "使用委派任务本身的语言回复",
            "重要文件和验证",
        ):
            self.assertIn(expected, prompt)
        for forbidden in (
            "You are a focused child coding agent",
            "=== 项目上下文",
            "=== 长期记忆",
            "=== 已激活 Skill",
        ):
            self.assertNotIn(forbidden, prompt)

    def test_agent_record_roundtrip_preserves_system_prompt_bytes(self):
        system_prompt = (
            "安全首段\n\n"
            "当前时间：2026年08月15日星期六 01:02"
            "（Asia/Shanghai UTC+08:00）\n\n权限末段"
        )
        run = server_mod._create_agent_run(
            "system-prompt-roundtrip-session",
            {
                "model": "test-model",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "inspect without starting"},
                ],
            },
            self.base_url,
            [],
            start_worker=False,
        )

        record = server_mod._agent_run_record(run)
        restored = server_mod._agent_run_from_record(record)

        self.assertEqual(record["version"], 5)
        self.assertEqual(record["messages"][0], {"role": "system", "content": system_prompt})
        self.assertEqual(restored["messages"][0], record["messages"][0])
        payload, _ = server_mod._agent_model_payload(restored)
        self.assertEqual(payload["messages"][0]["content"], system_prompt)

    def test_v4_and_v5_records_project_interleaved_visual_tools_without_rewriting(self):
        seed = server_mod._create_agent_run(
            "tool-protocol-version-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "inspect without starting"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["read_file"]],
            },
            self.base_url,
            [],
            allowed_tools=["read_file"],
            start_worker=False,
        )
        calls = [{
            "id": call_id,
            "type": "function",
            "function": {"name": "read_file", "arguments": "{}"},
        } for call_id in ("call-a", "call-b")]
        result_a = {
            "ok": True, "action": "read_file", "path": "a.png",
            "binary": True, "visual": True, "mime": "image/png", "base64": "YQ==",
        }
        result_b = {
            "ok": True, "action": "read_file", "path": "b.png",
            "binary": True, "visual": True, "mime": "image/png", "base64": "Yg==",
        }
        broken = [
            {"role": "assistant", "content": "", "tool_calls": calls},
            {"role": "tool", "tool_call_id": "call-a", "name": "read_file", "content": "A"},
            server_mod._agent_tool_vision_marker(result_a, "call-a"),
            {"role": "tool", "tool_call_id": "call-b", "name": "read_file", "content": "B"},
            server_mod._agent_tool_vision_marker(result_b, "call-b"),
        ]
        base_record = server_mod._agent_run_record(seed)
        base_record["status"] = "failed"
        base_record["messages"] = broken
        base_record["toolExecutions"] = {
            "call-a": {"status": "completed", "name": "read_file", "result": result_a},
            "call-b": {"status": "completed", "name": "read_file", "result": result_b},
        }

        for version in (4, 5):
            with self.subTest(version=version):
                record = json.loads(json.dumps(base_record))
                record["version"] = version
                before = json.dumps(record["messages"], ensure_ascii=False)
                restored = server_mod._agent_run_from_record(record)
                payload, _ = server_mod._agent_model_payload(restored)
                self.assertEqual(json.dumps(record["messages"], ensure_ascii=False), before)
                self.assertEqual(
                    [message["role"] for message in payload["messages"]],
                    ["assistant", "tool", "tool", "user", "user"],
                )
                self.assertEqual(
                    [payload["messages"][1]["tool_call_id"], payload["messages"][2]["tool_call_id"]],
                    ["call-a", "call-b"],
                )

    def test_conflicting_tool_history_fails_locally_without_upstream_or_replay(self):
        run = server_mod._create_agent_run(
            "tool-protocol-conflict-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "seed"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["read_file"]],
            },
            self.base_url,
            [],
            allowed_tools=["read_file"],
            start_worker=False,
        )
        call = {
            "id": "call-conflict",
            "type": "function",
            "function": {"name": "read_file", "arguments": "{}"},
        }
        run["messages"] = [
            {"role": "assistant", "content": "", "tool_calls": [call]},
            {"role": "tool", "tool_call_id": "call-conflict", "content": "first"},
            {"role": "tool", "tool_call_id": "call-conflict", "content": "second"},
        ]
        run["status"] = "model"
        run["keys"] = ["must-not-be-used"]

        server_mod._start_agent_worker(run)
        self._wait_terminal(run)

        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error_code"], "tool_protocol_error")
        self.assertEqual(_AgentUpstream.calls, 0)
        self.assertEqual(run["tool_executions"], {})

    def test_orphan_tool_history_fails_locally_without_upstream_or_replay(self):
        run = server_mod._create_agent_run(
            "tool-protocol-orphan-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "seed"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["read_file"]],
            },
            self.base_url,
            [],
            allowed_tools=["read_file"],
            start_worker=False,
        )
        run["messages"] = [{
            "role": "tool",
            "tool_call_id": "orphan-call",
            "name": "read_file",
            "content": "preserved evidence",
        }]
        run["status"] = "model"
        run["keys"] = ["must-not-be-used"]

        server_mod._start_agent_worker(run)
        self._wait_terminal(run)

        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error_code"], "tool_protocol_error")
        self.assertEqual(_AgentUpstream.calls, 0)
        self.assertEqual(run["tool_executions"], {})

    def test_restart_reuses_completed_child_without_second_child_request(self):
        parent = server_mod._create_agent_run(
            "delegated-restart-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "delegate inspection"}],
                "tools": [
                    server_mod._SERVER_TOOL_DEFINITIONS["task"],
                    server_mod._SERVER_TOOL_DEFINITIONS["read_file"],
                ],
            },
            self.base_url,
            ["restart-parent-key"],
            allowed_tools=["task", "read_file"],
            permission_profile="plan",
            start_worker=False,
        )
        child = server_mod._create_agent_run(
            "delegated-restart-session",
            {
                "model": "test-model",
                "messages": [
                    {"role": "system", "content": server_mod._agent_child_system_prompt()},
                    {"role": "user", "content": "inspect child file"},
                ],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["read_file"]],
            },
            self.base_url,
            ["restart-child-key"],
            allowed_tools=["read_file"],
            permission_profile="plan",
            parent_run_id=parent["id"],
            parent_tool_call_id="agent-task-1",
            agent_depth=1,
        )
        self._wait_terminal(child)
        calls_after_child = _AgentUpstream.calls
        arguments = json.dumps({"prompt": "inspect child file"}, separators=(",", ":"))
        fingerprint = hashlib.sha256(f"task\0{arguments}".encode()).hexdigest()
        call = {
            "index": 0,
            "id": "agent-task-1",
            "type": "function",
            "function": {"name": "task", "arguments": arguments},
            "arguments": {"prompt": "inspect child file"},
            "parseError": "",
            "fingerprint": fingerprint,
        }
        timestamp = server_mod.now_iso()
        with parent["condition"]:
            parent["messages"].append({
                "role": "assistant",
                "content": "",
                "tool_calls": server_mod._agent_assistant_tool_calls([call]),
            })
            parent["rounds"].append({
                "round": 1,
                "toolCalls": server_mod._agent_assistant_tool_calls([call]),
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            })
            parent["usage"] = {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}
            parent["pending_tool_calls"] = [call]
            parent["tool_executions"] = {
                "agent-task-1": {
                    "name": "task",
                    "arguments": arguments,
                    "fingerprint": fingerprint,
                    "status": "waiting_child",
                    "result": None,
                    "error": "",
                    "startedAt": timestamp,
                    "completedAt": "",
                    "childAgentRunId": child["id"],
                    "prompt": "inspect child file",
                },
            }
            parent["status"] = "tools"
            parent["updated_at"] = timestamp
        server_mod._persist_agent_run(parent)
        with server_mod._agent_run_lock:
            server_mod._agent_runs.pop(parent["id"], None)
            server_mod._agent_runs.pop(child["id"], None)

        loaded = server_mod._get_agent_run(parent["id"])
        self.assertEqual(loaded["status"], "waiting_credentials")
        server_mod._resume_agent_run(
            loaded,
            ["restart-resume-key"],
            self.base_url,
        )
        self._wait_terminal(loaded)

        self.assertEqual(loaded["status"], "completed")
        self.assertEqual(_AgentUpstream.calls, calls_after_child + 1)
        self.assertEqual(loaded["usage"]["total_tokens"], 38)
        execution = loaded["tool_executions"]["agent-task-1"]
        self.assertEqual(execution["childAgentRunId"], child["id"])
        self.assertTrue(execution["childUsageMerged"])

    def test_command_tool_requires_accept_or_bypass_permission(self):
        payload = {"tools": [server_mod._SERVER_TOOL_DEFINITIONS["run_command"]]}
        self.assertEqual(
            server_mod._agent_selected_tools(payload, ["run_command"], "read"),
            [],
        )
        self.assertEqual(
            server_mod._agent_selected_tools(payload, ["run_command"], "plan"),
            [],
        )
        for profile in ("accept", "bypass"):
            with self.subTest(profile=profile):
                selected = server_mod._agent_selected_tools(
                    payload, ["run_command"], profile,
                )
                self.assertEqual(
                    [item["function"]["name"] for item in selected],
                    ["run_command"],
                )

    def test_memory_tool_requires_accept_or_bypass_permission(self):
        payload = {"tools": [server_mod._SERVER_TOOL_DEFINITIONS["save_memory"]]}
        for profile in ("read", "plan"):
            with self.subTest(profile=profile):
                self.assertEqual(
                    server_mod._agent_selected_tools(payload, ["save_memory"], profile),
                    [],
                )
        for profile in ("accept", "bypass"):
            with self.subTest(profile=profile):
                selected = server_mod._agent_selected_tools(
                    payload, ["save_memory"], profile,
                )
                self.assertEqual(
                    [item["function"]["name"] for item in selected],
                    ["save_memory"],
                )

    def test_agent_saves_memory_without_browser_relay_or_authorization_pause(self):
        run = server_mod._create_agent_run(
            "memory-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "remember convention"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["save_memory"]],
            },
            self.base_url,
            ["memory-secret-key"],
            allowed_tools=["save_memory"],
            permission_profile="accept",
        )
        self._wait_terminal(run)

        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "memory task complete")
        self.assertIsNone(snapshot["pendingAuthorization"])
        self.assertEqual(len(snapshot["toolExecutions"]), 1)
        result = snapshot["toolExecutions"][0]["result"]
        self.assertEqual(result["action"], "save_memory")
        self.assertFalse(result["replayed"])
        memory_path = self.data_dir / "memory" / "runtime-convention.md"
        self.assertIn(
            "AgentRun owns durable memory writes.",
            memory_path.read_text(encoding="utf-8"),
        )
        persisted = server_mod._agent_run_path(run["id"]).read_text(encoding="utf-8")
        self.assertNotIn("memory-secret-key", persisted)

    def test_file_mutation_tools_require_accept_or_bypass_permission(self):
        payload = {"tools": [
            server_mod._SERVER_TOOL_DEFINITIONS["write_file"],
            server_mod._SERVER_TOOL_DEFINITIONS["delete_file"],
        ]}
        for profile in ("read", "plan"):
            with self.subTest(profile=profile):
                self.assertEqual(
                    server_mod._agent_selected_tools(
                        payload, ["write_file", "delete_file"], profile,
                    ),
                    [],
                )
        for profile in ("accept", "bypass"):
            with self.subTest(profile=profile):
                selected = server_mod._agent_selected_tools(
                    payload, ["write_file", "delete_file"], profile,
                )
                self.assertEqual(
                    [item["function"]["name"] for item in selected],
                    ["write_file", "delete_file"],
                )

    def test_accept_write_waits_for_authorization_then_executes_after_resume(self):
        target = self.project_dir / "generated.txt"
        run = server_mod._create_agent_run(
            "write-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "write project file"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["write_file"]],
            },
            self.base_url,
            ["write-before-approval-key"],
            allowed_tools=["write_file"],
            permission_profile="accept",
        )
        self._wait_status(run, "waiting_authorization")
        self._wait_worker_idle(run)
        pending = server_mod._agent_snapshot(run, 0)["pendingAuthorization"]
        self.assertEqual(pending["action"], "write_file")
        self.assertEqual(pending["path"], "generated.txt")
        self.assertIn("written by AgentRun", pending["diff"])
        self.assertFalse(target.exists())

        approved = server_mod._submit_agent_authorization(
            run, pending["authorizationId"], "approved",
        )
        self.assertTrue(approved["authorized"])
        self.assertFalse(approved["executed"])
        self.assertEqual(run["status"], "waiting_credentials")
        self.assertFalse(target.exists())

        server_mod._resume_agent_run(run, ["write-after-approval-key"])
        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "write task complete")
        self.assertEqual(target.read_text(encoding="utf-8"), "written by AgentRun\n")
        result = snapshot["toolExecutions"][0]["result"]
        self.assertEqual(result["action"], "write_file")
        self.assertFalse(result["replayed"])
        persisted = server_mod._agent_run_path(run["id"]).read_text(encoding="utf-8")
        self.assertNotIn("write-before-approval-key", persisted)
        self.assertNotIn("write-after-approval-key", persisted)

    def test_rejected_delete_never_changes_project(self):
        target = self.project_dir / "obsolete.txt"
        target.write_text("keep me", encoding="utf-8")
        run = server_mod._create_agent_run(
            "delete-reject-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "delete project file"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["delete_file"]],
            },
            self.base_url,
            ["delete-reject-key"],
            allowed_tools=["delete_file"],
            permission_profile="accept",
        )
        self._wait_status(run, "waiting_authorization")
        self._wait_worker_idle(run)
        pending = server_mod._agent_snapshot(run, 0)["pendingAuthorization"]
        self.assertEqual(pending["action"], "delete_file")
        rejected = server_mod._submit_agent_authorization(
            run, pending["authorizationId"], "rejected",
        )
        self.assertTrue(rejected["rejected"])
        self.assertTrue(target.is_file())

        server_mod._resume_agent_run(run, ["delete-reject-resume-key"])
        self._wait_terminal(run)
        self.assertTrue(target.is_file())
        result = server_mod._agent_snapshot(run, 0)["toolExecutions"][0]["result"]
        self.assertTrue(result["rejected"])

    def test_agent_executes_network_and_skill_tools_without_browser_polling(self):
        skill_dir = self.data_dir / "skills" / "runtime-skill"
        reference_dir = skill_dir / "references"
        reference_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: runtime-skill\ndescription: Runtime test\n"
            "tools: read_file\n---\n\nFollow runtime guidance.\n",
            encoding="utf-8",
        )
        (reference_dir / "guide.md").write_text("Runtime reference", encoding="utf-8")
        web_result = {
            "ok": True,
            "action": "web_fetch",
            "url": "https://example.com/docs",
            "status": 200,
            "content": "Public documentation",
        }

        with mock.patch.dict(
            server_mod.SERVER_TOOL_REGISTRY["web_fetch"],
            {"execute": lambda _payload: dict(web_result)},
        ):
            run = server_mod._create_agent_run(
                "network-skill-session",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "inspect skill and network"}],
                    "tools": [
                        server_mod._SERVER_TOOL_DEFINITIONS["use_skill"],
                        server_mod._SERVER_TOOL_DEFINITIONS["read_skill_resource"],
                        server_mod._SERVER_TOOL_DEFINITIONS["web_fetch"],
                    ],
                },
                self.base_url,
                ["network-skill-key"],
                allowed_tools=["use_skill", "read_skill_resource", "web_fetch"],
            )
            # The worker owns all three calls; no browser snapshot or tool relay
            # is needed before it reaches the final model response.
            self._wait_terminal(run)

        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "network and skill task complete")
        self.assertEqual(
            snapshot["allowedTools"],
            ["use_skill", "read_skill_resource", "web_fetch"],
        )
        executions = {item["name"]: item for item in snapshot["toolExecutions"]}
        self.assertEqual(set(executions), {"use_skill", "read_skill_resource", "web_fetch"})
        self.assertIn("runtime guidance", json.dumps(executions["use_skill"]["result"]))
        self.assertIn("Runtime reference", json.dumps(executions["read_skill_resource"]["result"]))
        self.assertEqual(executions["web_fetch"]["result"], web_result)
        persisted = server_mod._agent_run_path(run["id"]).read_text(encoding="utf-8")
        self.assertNotIn("network-skill-key", persisted)
        self.assertNotIn("network-skill-key", json.dumps(snapshot))

    def test_accept_command_waits_for_authorization_then_executes_once(self):
        run = server_mod._create_agent_run(
            "command-accept-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "run approved command"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["run_command"]],
            },
            self.base_url,
            ["command-before-approval-key"],
            allowed_tools=["run_command"],
            permission_profile="accept",
        )
        self._wait_status(run, "waiting_authorization")
        self._wait_worker_idle(run)
        pending = server_mod._agent_snapshot(run, 0)["pendingAuthorization"]
        self.assertEqual(pending["action"], "run_command")
        self.assertIn("agent-command", pending["command"])
        execution = run["tool_executions"]["agent-command-1"]
        self.assertEqual(execution["status"], "waiting_authorization")

        decision = server_mod._submit_agent_authorization(
            run, pending["authorizationId"], "approved",
        )
        self.assertTrue(decision["authorized"])
        self.assertFalse(decision["executed"])
        self.assertEqual(run["status"], "waiting_credentials")
        self.assertEqual(execution["status"], "authorized")

        server_mod._resume_agent_run(run, ["command-after-approval-key"])
        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "command task complete")
        command_execution = snapshot["toolExecutions"][0]
        self.assertEqual(command_execution["status"], "completed")
        self.assertTrue(command_execution["result"]["ok"])
        self.assertIn("agent-command", command_execution["result"]["stdout"])
        self.assertEqual(
            [event["type"] for event in snapshot["events"]].count("command_started"),
            1,
        )
        persisted = server_mod._agent_run_path(run["id"]).read_text(encoding="utf-8")
        self.assertNotIn("command-before-approval-key", persisted)
        self.assertNotIn("command-after-approval-key", persisted)

    def test_failed_command_reports_nonzero_result_once_and_run_can_complete(self):
        command = (
            'node -e "console.error(\'h2-3-intentional-failure\'); '
            'process.exit(7)"'
        )
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                [{
                    "choices": [{
                        "delta": {"tool_calls": [{
                            "index": 0,
                            "id": "agent-command-failure-1",
                            "type": "function",
                            "function": {
                                "name": "run_command",
                                "arguments": json.dumps({
                                    "command": command,
                                    "description": "Intentional AgentRun failure",
                                }),
                            },
                        }]},
                        "finish_reason": "tool_calls",
                    }],
                }],
                [{
                    "choices": [{
                        "delta": {"content": "command failed once with exit code 7"},
                        "finish_reason": "stop",
                    }],
                }],
            ]

        run = server_mod._create_agent_run(
            "command-failure-session",
            {
                "model": "test-model",
                "messages": [{
                    "role": "user",
                    "content": "run one intentionally failing command",
                }],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["run_command"]],
            },
            self.base_url,
            ["command-failure-key"],
            allowed_tools=["run_command"],
            permission_profile="bypass",
        )
        self._wait_terminal(run)

        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(
            snapshot["result"]["content"],
            "command failed once with exit code 7",
        )
        self.assertEqual(_AgentUpstream.calls, 2)
        self.assertEqual(snapshot["pendingToolCalls"], [])
        execution = snapshot["toolExecutions"][0]
        self.assertEqual(execution["toolCallId"], "agent-command-failure-1")
        self.assertEqual(execution["status"], "completed")
        self.assertEqual(execution["outcome"], "failed")
        self.assertFalse(execution["result"]["ok"])
        self.assertEqual(execution["result"]["exitCode"], 7)
        self.assertIn("h2-3-intentional-failure", execution["result"]["stderr"])
        event_types = [event["type"] for event in snapshot["events"]]
        self.assertEqual(event_types.count("command_started"), 1)
        completed = [
            event for event in snapshot["events"]
            if event["type"] == "tool_completed"
        ]
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["data"]["outcome"], "failed")
        self.assertEqual(completed[0]["data"]["result"]["exitCode"], 7)
        tool_messages = [
            message for message in _AgentUpstream.payloads[-1]["messages"]
            if message.get("role") == "tool"
        ]
        self.assertEqual(len(tool_messages), 1)
        tool_result = json.loads(tool_messages[0]["content"])
        self.assertFalse(tool_result["ok"])
        self.assertEqual(tool_result["exitCode"], 7)
        self.assertIn("h2-3-intentional-failure", tool_result["stderr"])

    def test_rejected_command_becomes_tool_result_without_execution(self):
        run = server_mod._create_agent_run(
            "command-reject-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "run approved command"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["run_command"]],
            },
            self.base_url,
            ["command-reject-key"],
            allowed_tools=["run_command"],
            permission_profile="accept",
        )
        self._wait_status(run, "waiting_authorization")
        self._wait_worker_idle(run)
        pending = server_mod._agent_snapshot(run, 0)["pendingAuthorization"]
        with mock.patch.object(server_mod.subprocess, "Popen") as popen_mock:
            result = server_mod._submit_agent_authorization(
                run, pending["authorizationId"], "rejected",
            )
            popen_mock.assert_not_called()
        self.assertTrue(result["rejected"])
        self.assertEqual(run["status"], "waiting_credentials")
        server_mod._resume_agent_run(run, ["command-reject-resume-key"])
        self._wait_terminal(run)
        execution = server_mod._agent_snapshot(run, 0)["toolExecutions"][0]
        self.assertEqual(execution["status"], "completed")
        self.assertTrue(execution["result"]["rejected"])

    def test_bypass_command_persists_output_and_cancel_stops_process(self):
        run = server_mod._create_agent_run(
            "command-cancel-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "run slow command"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["run_command"]],
            },
            self.base_url,
            ["command-cancel-key"],
            allowed_tools=["run_command"],
            permission_profile="bypass",
        )
        deadline = time.time() + 8
        process = None
        while time.time() < deadline:
            execution = run["tool_executions"].get("agent-command-1") or {}
            process = run.get("active_process")
            if execution.get("status") == "running" and "command-started" in execution.get("stdout", ""):
                break
            time.sleep(0.05)
        self.assertIsNotNone(process)
        self.assertIsNone(process.poll())
        persisted_running = server_mod._agent_run_path(run["id"]).read_text(encoding="utf-8")
        self.assertIn("command-started", persisted_running)

        server_mod._cancel_agent_run(run["id"])
        self._wait_terminal(run)
        self._wait_worker_idle(run)
        self.assertIsNotNone(process.poll())
        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "cancelled")
        execution = snapshot["toolExecutions"][0]
        self.assertEqual(execution["status"], "cancelled")
        self.assertTrue(execution["result"]["cancelled"])
        self.assertIn("command-started", execution["stdout"])
        event_types = [event["type"] for event in snapshot["events"]]
        self.assertEqual(event_types[-2:], ["tool_completed", "cancelled"])
        self.assertEqual(event_types.count("tool_completed"), 1)
        completed_event = snapshot["events"][-2]
        self.assertEqual(completed_event["data"]["toolCallId"], "agent-command-1")
        self.assertEqual(completed_event["data"]["name"], "run_command")
        self.assertEqual(completed_event["data"]["outcome"], "failed")
        self.assertTrue(completed_event["data"]["result"]["cancelled"])
        self.assertIn("command-started", completed_event["data"]["result"]["stdout"])

    def test_cancel_closes_every_tool_in_one_model_round_without_starting_the_second(self):
        command_started = threading.Event()
        command_calls = []

        def fake_command_executor(
            body,
            *,
            cancel_event=None,
            output_callback=None,
            process_callback=None,
        ):
            command_calls.append(dict(body or {}))
            if callable(output_callback):
                output_callback("stdout", "multi-cancel-started\n")
            command_started.set()
            self.assertIsNotNone(cancel_event)
            self.assertTrue(cancel_event.wait(timeout=2))
            return {
                "ok": False,
                "action": "run_command",
                "command": str((body or {}).get("command") or ""),
                "cwd": str(self.project_dir),
                "exitCode": None,
                "stdout": "multi-cancel-started\n",
                "stderr": "",
                "cancelled": True,
                "error": "Command cancelled.",
            }

        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [[{
                "choices": [{
                    "delta": {"tool_calls": [
                        {
                            "index": 0,
                            "id": "multi-cancel-command",
                            "type": "function",
                            "function": {
                                "name": "run_command",
                                "arguments": json.dumps({
                                    "command": "node -e \"setTimeout(() => {}, 20000)\"",
                                    "description": "cancel the active command",
                                }),
                            },
                        },
                        {
                            "index": 1,
                            "id": "multi-cancel-read",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"path": "README.md"}),
                            },
                        },
                    ]},
                    "finish_reason": "tool_calls",
                }],
            }]]

        with (
            mock.patch.object(server_mod, "_AGENT_PROTOCOL_SHADOW_ENABLED", True),
            mock.patch.object(server_mod, "_AGENT_EVENT_PROTOCOL_V1_ENABLED", True),
            mock.patch.object(
                server_mod,
                "execute_run_command_tool",
                side_effect=fake_command_executor,
            ),
            mock.patch.object(
                server_mod,
                "execute_registered_tool",
                wraps=server_mod.execute_registered_tool,
            ) as registered_tool,
        ):
            run = server_mod._create_agent_run(
                "multi-tool-cancel-session",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "cancel two tools"}],
                    "tools": [
                        server_mod._SERVER_TOOL_DEFINITIONS["run_command"],
                        server_mod._SERVER_TOOL_DEFINITIONS["read_file"],
                    ],
                },
                self.base_url,
                ["multi-cancel-key"],
                allowed_tools=["run_command", "read_file"],
                permission_profile="bypass",
            )
            self.assertTrue(command_started.wait(timeout=5))

            barrier = threading.Barrier(3)
            cancel_results = []

            def cancel_run():
                barrier.wait()
                cancel_results.append(server_mod._cancel_agent_run(run["id"]))

            cancel_threads = [
                threading.Thread(target=cancel_run),
                threading.Thread(target=cancel_run),
            ]
            for thread in cancel_threads:
                thread.start()
            barrier.wait()
            for thread in cancel_threads:
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())

            self._wait_terminal(run)
            self._wait_worker_idle(run)
            event_count = len(run["events"])
            self.assertIs(server_mod._cancel_agent_run(run["id"]), run)
            self.assertEqual(len(run["events"]), event_count)
            self.assertEqual(cancel_results, [run, run])
            self.assertEqual(len(command_calls), 1)
            registered_tool.assert_not_called()

            snapshot = server_mod._agent_snapshot(run, 0)
            self.assertEqual(snapshot["status"], "cancelled")
            self.assertEqual(snapshot["pendingToolCalls"], [])
            self.assertIsNone(snapshot["pendingInput"])
            self.assertIsNone(snapshot["pendingAuthorization"])
            executions = {
                item["toolCallId"]: item for item in snapshot["toolExecutions"]
            }
            self.assertEqual(set(executions), {
                "multi-cancel-command", "multi-cancel-read",
            })
            active = executions["multi-cancel-command"]
            waiting = executions["multi-cancel-read"]
            self.assertEqual((active["status"], active["outcome"]), ("cancelled", "failed"))
            self.assertTrue(active["result"]["cancelled"])
            self.assertNotIn("cancelledBeforeStart", active["result"])
            self.assertEqual((waiting["status"], waiting["outcome"]), ("cancelled", "failed"))
            self.assertTrue(waiting["result"]["cancelled"])
            self.assertTrue(waiting["result"]["cancelledBeforeStart"])
            self.assertEqual(waiting["startedAt"], "")

            events = snapshot["events"]
            completed = [event for event in events if event["type"] == "tool_completed"]
            self.assertEqual(
                [event["data"]["toolCallId"] for event in completed],
                ["multi-cancel-command", "multi-cancel-read"],
            )
            self.assertEqual(len(completed), 2)
            self.assertEqual(events[-1]["type"], "cancelled")
            self.assertLess(events.index(completed[-1]), len(events) - 1)
            self.assertEqual([
                event["data"]["toolCallId"]
                for event in events if event["type"] == "tool_started"
            ], ["multi-cancel-command"])
            self.assertEqual([
                event["data"]["toolCallId"]
                for event in events if event["type"] == "command_started"
            ], ["multi-cancel-command"])
            shadow = server_mod._agent_protocol_shadow_snapshot(run)
            self.assertEqual(shadow["diagnosticCounts"], {})
            self.assertEqual(shadow["contractErrors"], 0)

        with server_mod._agent_run_lock:
            server_mod._agent_runs.pop(run["id"], None)
        restored = server_mod._get_agent_run(run["id"])
        restored_snapshot = server_mod._agent_snapshot(restored, 0)
        self.assertEqual(restored_snapshot["status"], "cancelled")
        self.assertEqual(restored_snapshot["pendingToolCalls"], [])
        self.assertIsNone(restored_snapshot["pendingInput"])
        self.assertIsNone(restored_snapshot["pendingAuthorization"])
        non_terminal_tool_statuses = {
            "running",
            "waiting_authorization",
            "waiting_user_input",
            "authorized",
            "applying_edit",
            "applying_file_mutation",
            "queued_child",
            "waiting_child",
            "waiting_child_authorization",
        }
        self.assertFalse(
            non_terminal_tool_statuses & {
                item["status"] for item in restored_snapshot["toolExecutions"]
            },
        )

    def test_bypass_dependency_install_still_waits_for_user_authorization(self):
        run = server_mod._create_agent_run(
            "dependency-install-bypass-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "install dependency in bypass"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["run_command"]],
            },
            self.base_url,
            ["dependency-install-key"],
            allowed_tools=["run_command"],
            permission_profile="bypass",
        )
        self._wait_status(run, "waiting_authorization")
        self._wait_worker_idle(run)
        snapshot = server_mod._agent_snapshot(run, 0)
        pending = snapshot["pendingAuthorization"]
        self.assertIn("pip install", pending["command"])
        execution = run["tool_executions"]["agent-command-1"]
        self.assertTrue(execution["dependencyInstall"])
        with mock.patch.object(server_mod.subprocess, "Popen") as popen_mock:
            rejected = server_mod._submit_agent_authorization(
                run, pending["authorizationId"], "rejected",
            )
            popen_mock.assert_not_called()
        self.assertTrue(rejected["rejected"])

    def test_bypass_system_dependency_install_is_blocked_without_execution(self):
        with mock.patch.object(server_mod.subprocess, "Popen") as popen_mock:
            run = server_mod._create_agent_run(
                "system-dependency-install-bypass-session",
                {
                    "model": "test-model",
                    "messages": [{
                        "role": "user",
                        "content": "install system dependency in bypass",
                    }],
                    "tools": [server_mod._SERVER_TOOL_DEFINITIONS["run_command"]],
                },
                self.base_url,
                ["dependency-install-key"],
                allowed_tools=["run_command"],
                permission_profile="bypass",
            )
            self._wait_terminal(run)
            self._wait_worker_idle(run)

        popen_mock.assert_not_called()
        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "completed")
        execution = run["tool_executions"]["agent-command-1"]
        self.assertEqual(execution["dependencyInstallKind"], "system")
        self.assertIn("outside Code", execution["error"])
        self.assertIsNone(snapshot["pendingAuthorization"])

    def test_restart_marks_running_command_unknown_and_never_replays_it(self):
        run_id = uuid.uuid4().hex
        arguments = json.dumps({
            "command": 'python -c "print(\'must-not-run-again\')"',
            "description": "Non-replayable command",
        }, separators=(",", ":"))
        fingerprint = hashlib.sha256(f"run_command\0{arguments}".encode()).hexdigest()
        timestamp = server_mod.now_iso()
        record = {
            "version": 1,
            "id": run_id,
            "sessionId": "command-restart-session",
            "status": "tools",
            "resumeStatus": "",
            "permissionProfile": "bypass",
            "error": "",
            "baseUrl": self.base_url,
            "request": {"model": "test-model", "tool_choice": "auto"},
            "messages": [
                {"role": "user", "content": "run approved command"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "agent-command-1",
                        "type": "function",
                        "function": {"name": "run_command", "arguments": arguments},
                    }],
                },
            ],
            "tools": [server_mod._SERVER_TOOL_DEFINITIONS["run_command"]],
            "rounds": [{"round": 1, "toolCalls": [], "usage": {"total_tokens": 5}}],
            "pendingToolCalls": [{
                "index": 0,
                "id": "agent-command-1",
                "type": "function",
                "function": {"name": "run_command", "arguments": arguments},
                "arguments": json.loads(arguments),
                "parseError": "",
                "fingerprint": fingerprint,
            }],
            "toolExecutions": {
                "agent-command-1": {
                    "name": "run_command",
                    "arguments": arguments,
                    "fingerprint": fingerprint,
                    "status": "running",
                    "command": "must-not-run-again",
                    "cwd": str(self.project_dir),
                    "stdout": "partial output\n",
                    "stderr": "",
                    "startedAt": timestamp,
                    "completedAt": "",
                },
            },
            "usage": {"total_tokens": 5},
            "result": {},
            "events": [],
            "nextSeq": 1,
            "maxRounds": 4,
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }
        server_mod.write_json(server_mod._agent_run_path(run_id), record)

        loaded = server_mod._get_agent_run(run_id)
        self.assertEqual(loaded["status"], "waiting_credentials")
        interrupted = loaded["tool_executions"]["agent-command-1"]
        self.assertEqual(interrupted["status"], "completed")
        self.assertTrue(interrupted["result"]["unknownState"])
        self.assertTrue(interrupted["result"]["notReplayed"])
        with mock.patch.object(server_mod.subprocess, "Popen") as popen_mock:
            server_mod._resume_agent_run(loaded, ["command-restart-key"])
            self._wait_terminal(loaded)
            popen_mock.assert_not_called()
        snapshot = server_mod._agent_snapshot(loaded, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "command task complete")
        self.assertTrue(snapshot["toolExecutions"][0]["result"]["notReplayed"])

    def test_restart_replays_running_memory_write_without_rewriting_file(self):
        payload = {
            "name": "runtime-convention",
            "description": "Runtime convention",
            "body": "AgentRun owns durable memory writes.",
        }
        first = server_mod.execute_registered_tool("save_memory", payload)
        self.assertFalse(first["replayed"])
        memory_path = self.data_dir / "memory" / "runtime-convention.md"
        before = memory_path.read_bytes()
        before_mtime = memory_path.stat().st_mtime_ns

        run_id = uuid.uuid4().hex
        arguments = json.dumps(payload, separators=(",", ":"))
        fingerprint = hashlib.sha256(f"save_memory\0{arguments}".encode()).hexdigest()
        timestamp = server_mod.now_iso()
        record = {
            "version": 1,
            "id": run_id,
            "sessionId": "memory-restart-session",
            "status": "tools",
            "resumeStatus": "",
            "permissionProfile": "accept",
            "error": "",
            "baseUrl": self.base_url,
            "request": {"model": "test-model", "tool_choice": "auto"},
            "messages": [
                {"role": "user", "content": "remember convention"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "agent-memory-1",
                        "type": "function",
                        "function": {"name": "save_memory", "arguments": arguments},
                    }],
                },
            ],
            "tools": [server_mod._SERVER_TOOL_DEFINITIONS["save_memory"]],
            "rounds": [{"round": 1, "toolCalls": [], "usage": {"total_tokens": 5}}],
            "pendingToolCalls": [{
                "index": 0,
                "id": "agent-memory-1",
                "type": "function",
                "function": {"name": "save_memory", "arguments": arguments},
                "arguments": payload,
                "parseError": "",
                "fingerprint": fingerprint,
            }],
            "toolExecutions": {
                "agent-memory-1": {
                    "name": "save_memory",
                    "arguments": arguments,
                    "fingerprint": fingerprint,
                    "status": "running",
                    "result": None,
                    "error": "",
                    "startedAt": timestamp,
                    "completedAt": "",
                },
            },
            "usage": {"total_tokens": 5},
            "result": {},
            "events": [],
            "nextSeq": 1,
            "maxRounds": 4,
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }
        server_mod.write_json(server_mod._agent_run_path(run_id), record)

        loaded = server_mod._get_agent_run(run_id)
        self.assertEqual(loaded["status"], "waiting_credentials")
        original_execute = server_mod.execute_registered_tool
        with mock.patch.object(
            server_mod, "execute_registered_tool", wraps=original_execute,
        ) as execute_mock:
            server_mod._resume_agent_run(loaded, ["memory-restart-key"])
            self._wait_terminal(loaded)
            self.assertEqual(execute_mock.call_count, 1)

        snapshot = server_mod._agent_snapshot(loaded, 0)
        self.assertEqual(snapshot["status"], "completed")
        result = snapshot["toolExecutions"][0]["result"]
        self.assertTrue(result["replayed"])
        self.assertEqual(memory_path.read_bytes(), before)
        self.assertEqual(memory_path.stat().st_mtime_ns, before_mtime)
        self.assertTrue(any(
            event["type"] == "tool_completed" and event["data"].get("replayed")
            for event in snapshot["events"]
        ))
        persisted = server_mod._agent_run_path(run_id).read_text(encoding="utf-8")
        self.assertNotIn("memory-restart-key", persisted)

    def test_restart_replays_delete_from_receipt_without_second_effect(self):
        target = self.project_dir / "obsolete.txt"
        target.write_text("delete once", encoding="utf-8")
        payload = {"path": "obsolete.txt"}
        operation_id = "agent-delete-crash-operation"
        first = server_mod.execute_registered_tool(
            "delete_file", {**payload, "_operationId": operation_id},
        )
        self.assertFalse(first["replayed"])
        self.assertFalse(target.exists())
        backup_path = Path(first["backupPath"])
        backup_mtime = backup_path.stat().st_mtime_ns

        run_id = uuid.uuid4().hex
        arguments = json.dumps(payload, separators=(",", ":"))
        fingerprint = hashlib.sha256(f"delete_file\0{arguments}".encode()).hexdigest()
        timestamp = server_mod.now_iso()
        record = {
            "version": 1,
            "id": run_id,
            "sessionId": "delete-restart-session",
            "status": "tools",
            "resumeStatus": "",
            "permissionProfile": "bypass",
            "error": "",
            "baseUrl": self.base_url,
            "request": {"model": "test-model", "tool_choice": "auto"},
            "messages": [
                {"role": "user", "content": "delete project file"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "agent-delete-1",
                        "type": "function",
                        "function": {"name": "delete_file", "arguments": arguments},
                    }],
                },
            ],
            "tools": [server_mod._SERVER_TOOL_DEFINITIONS["delete_file"]],
            "rounds": [{"round": 1, "toolCalls": [], "usage": {"total_tokens": 5}}],
            "pendingToolCalls": [{
                "index": 0,
                "id": "agent-delete-1",
                "type": "function",
                "function": {"name": "delete_file", "arguments": arguments},
                "arguments": payload,
                "parseError": "",
                "fingerprint": fingerprint,
            }],
            "toolExecutions": {
                "agent-delete-1": {
                    "name": "delete_file",
                    "arguments": arguments,
                    "fingerprint": fingerprint,
                    "status": "applying_file_mutation",
                    "operationId": operation_id,
                    "result": None,
                    "error": "",
                    "startedAt": timestamp,
                    "completedAt": "",
                },
            },
            "usage": {"total_tokens": 5},
            "result": {},
            "events": [],
            "nextSeq": 1,
            "maxRounds": 4,
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }
        server_mod.write_json(server_mod._agent_run_path(run_id), record)

        loaded = server_mod._get_agent_run(run_id)
        self.assertEqual(loaded["status"], "waiting_credentials")
        server_mod._resume_agent_run(loaded, ["delete-restart-key"])
        self._wait_terminal(loaded)

        snapshot = server_mod._agent_snapshot(loaded, 0)
        self.assertEqual(snapshot["status"], "completed")
        result = snapshot["toolExecutions"][0]["result"]
        self.assertTrue(result["replayed"])
        self.assertFalse(target.exists())
        self.assertEqual(backup_path.stat().st_mtime_ns, backup_mtime)
        self.assertTrue(any(
            event["type"] == "tool_completed" and event["data"].get("replayed")
            for event in snapshot["events"]
        ))
        persisted = server_mod._agent_run_path(run_id).read_text(encoding="utf-8")
        self.assertNotIn("delete-restart-key", persisted)

    def test_agent_questionnaire_waits_durably_and_continues_after_valid_answer(self):
        run = server_mod._create_agent_run(
            "question-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "ask for target"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["request_user_input"]],
            },
            self.base_url,
            ["question-secret-key"],
            allowed_tools=["request_user_input"],
        )
        self._wait_status(run, "waiting_user_input")
        self._wait_worker_idle(run)

        waiting = server_mod._agent_snapshot(run, 0)
        self.assertEqual(waiting["pendingInput"]["requestId"], "user-input-agent-question-1")
        self.assertEqual(waiting["pendingInput"]["questions"][0]["id"], "target")
        self.assertEqual(waiting["toolExecutions"][0]["status"], "waiting_user_input")
        self.assertEqual(run["keys"], [])
        persisted = server_mod._agent_run_path(run["id"]).read_text(encoding="utf-8")
        self.assertIn('"status": "waiting_user_input"', persisted)
        self.assertNotIn("question-secret-key", persisted)

        with self.assertRaisesRegex(ValueError, "invalid choice"):
            server_mod._submit_agent_input(run, [{
                "id": "target",
                "status": "resolved",
                "values": ["invalid"],
            }])
        self.assertEqual(run["status"], "waiting_user_input")

        result = server_mod._submit_agent_input(run, [{
            "id": "target",
            "status": "resolved",
            "values": ["api"],
        }])
        self.assertEqual(result["answers"][0]["answer"], "API")
        self.assertEqual(run["status"], "waiting_credentials")
        server_mod._resume_agent_run(run, ["question-resume-key"])
        self._wait_terminal(run)

        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "questionnaire task complete")
        self.assertIsNone(snapshot["pendingInput"])
        self.assertEqual(snapshot["toolExecutions"][0]["status"], "completed")
        self.assertTrue(any(
            message.get("role") == "tool"
            and message.get("tool_call_id") == "agent-question-1"
            and '"api"' in message.get("content", "")
            for message in run["messages"]
        ))
        event_types = [event["type"] for event in snapshot["events"]]
        for expected in (
            "user_input_required", "user_input_submitted", "tool_completed",
            "waiting_credentials", "resumed", "completed",
        ):
            self.assertIn(expected, event_types)

    def test_goal_cancel_tool_is_internal_bounded_and_persists_terminal_identity(self):
        session_id = "session-agent-goal-cancel-draft"
        client_request_id = "foreground-goal-cancel-draft"
        message_id = "message-goal-cancel-draft"
        server_mod.write_json(server_mod.session_path(session_id), {
            "id": session_id,
            "title": "Cancel draft Goal",
            "createdAt": server_mod.now_iso(),
            "updatedAt": server_mod.now_iso(),
            "messageCount": 1,
        })
        server_mod.write_jsonl(server_mod.messages_path(session_id), [{
            "id": message_id,
            "role": "user",
            "content": "Create a durable draft Goal",
            "meta": {"goalOrigin": {
                "messageId": message_id,
                "clientRequestId": client_request_id,
            }},
        }])
        run = server_mod._create_agent_run(
            session_id,
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "Cancel the current Goal"}],
            },
            self.base_url,
            [],
            allowed_tools=[],
            permission_profile="read",
            start_worker=False,
            client_request_id=client_request_id,
            run_kind="foreground",
        )

        tool_names = {
            str((definition.get("function") or {}).get("name") or "")
            for definition in run["tools"]
        }
        self.assertIn("goal_cancel", tool_names)
        self.assertIn("goal_cancel", server_mod._AGENT_GOAL_DEFAULT_TOOL_NAMES)
        definition = server_mod._SERVER_TOOL_DEFINITIONS["goal_cancel"]["function"]
        self.assertEqual(definition["parameters"]["required"], ["reason"])
        self.assertEqual(definition["parameters"]["properties"]["reason"]["maxLength"], 2000)
        self.assertTrue(server_mod._agent_tool_spec("goal_cancel")["internal"])

        def call(name, arguments, call_id):
            normalized = server_mod._normalize_agent_tool_calls(run, [{
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }], len(run.get("rounds") or []) + 1)
            run["pending_tool_calls"] = normalized
            run["status"] = "tools"
            self.assertTrue(server_mod._execute_agent_pending_tools(run))
            return run["tool_executions"][call_id]

        created = call(
            "goal_create", {"objective": "A cancellable draft Goal"}, "goal-create-draft",
        )["result"]
        self.assertEqual(created["goal"]["lifecycle"], "draft")
        cancelled_execution = call(
            "goal_cancel", {"reason": "  User explicitly abandoned this Goal.  "},
            "goal-cancel-draft",
        )
        cancelled = cancelled_execution["result"]
        self.assertEqual(cancelled["action"], "goal_cancel")
        self.assertEqual(cancelled["goal"]["lifecycle"], "cancelled")
        self.assertEqual(cancelled["goal"]["ownerRunId"], run["id"])

        runtime = server_mod.goal_v2_runtime()
        persisted = server_mod.GoalV2Runtime(self.data_dir).read(session_id).state
        self.assertEqual(persisted.goal["lifecycle"], "cancelled")
        events = server_mod.read_jsonl(runtime.service.events_path(session_id))
        terminal = events[-1]
        self.assertEqual(terminal["type"], "goal_cancelled")
        self.assertEqual(terminal["actor"], "foreground-agent")
        self.assertEqual(terminal["payload"]["sourceRunId"], run["id"])
        self.assertEqual(terminal["payload"]["reason"], "User explicitly abandoned this Goal.")

        prepared = cancelled_execution["goalOperation"]
        replay = runtime.cancel_goal(
            session_id,
            persisted.goal["goalId"],
            reason=prepared["arguments"]["reason"],
            source_run_id=run["id"],
            expected_revision=prepared["expectedRevision"],
            idempotency_key=prepared["idempotencyKey"],
        )
        self.assertTrue(replay["accepted"])
        self.assertTrue(replay["noOp"])
        self.assertEqual(replay["revision"], persisted.revision)
        late_plan = [{
            "id": f"late-{index}",
            "description": f"Forbidden late stage {index}",
            "acceptanceCriteria": [{
                "id": f"late-criterion-{index}",
                "kind": "machine",
                "description": "Must never be appended after cancellation",
            }],
        } for index in range(1, 4)]
        with self.assertRaises(server_mod.GoalV2ConflictError):
            runtime.set_plan(
                session_id,
                persisted.goal["goalId"],
                late_plan,
                source_run_id=run["id"],
                expected_revision=persisted.revision,
                idempotency_key="late-plan-after-cancel",
            )
        with self.assertRaises(server_mod.GoalV2ConflictError):
            runtime.start_step(
                session_id,
                persisted.goal["goalId"],
                "late-1",
                source_run_id=run["id"],
                expected_revision=persisted.revision,
                idempotency_key="late-step-after-cancel",
            )

    def test_goal_cancel_rejects_empty_reason_and_cancels_active_gated_goal(self):
        session_id = "session-agent-goal-cancel-active"
        client_request_id = "foreground-goal-cancel-active"
        message_id = "message-goal-cancel-active"
        server_mod.write_json(server_mod.session_path(session_id), {
            "id": session_id,
            "title": "Cancel gated Goal",
            "createdAt": server_mod.now_iso(),
            "updatedAt": server_mod.now_iso(),
            "messageCount": 1,
        })
        server_mod.write_jsonl(server_mod.messages_path(session_id), [{
            "id": message_id,
            "role": "user",
            "content": "Create an active Goal",
            "meta": {"goalOrigin": {
                "messageId": message_id,
                "clientRequestId": client_request_id,
            }},
        }])
        run = server_mod._create_agent_run(
            session_id,
            {"model": "test-model", "messages": [{"role": "user", "content": "cancel"}]},
            self.base_url,
            [],
            allowed_tools=[],
            permission_profile="read",
            start_worker=False,
            client_request_id=client_request_id,
            run_kind="foreground",
        )

        def call(name, arguments, call_id):
            normalized = server_mod._normalize_agent_tool_calls(run, [{
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }], len(run.get("rounds") or []) + 1)
            run["pending_tool_calls"] = normalized
            run["status"] = "tools"
            self.assertTrue(server_mod._execute_agent_pending_tools(run))
            return run["tool_executions"][call_id]

        call("goal_create", {"objective": "Active gated Goal"}, "active-create")
        plan = [{
            "id": f"step-{index}",
            "description": f"Stage {index}",
            "acceptanceCriteria": [{
                "id": f"criterion-{index}",
                "kind": "machine",
                "description": f"Stage {index} verified",
            }],
        } for index in range(1, 4)]
        runtime = server_mod.goal_v2_runtime()
        created_state = runtime.read(session_id).state
        planned = runtime.set_plan(
            session_id,
            created_state.goal["goalId"],
            plan,
            source_run_id=run["id"],
            expected_revision=created_state.revision,
            idempotency_key="active-plan",
        )
        started = runtime.start_step(
            session_id,
            planned["goal"]["goalId"],
            "step-1",
            source_run_id=run["id"],
            expected_revision=planned["revision"],
            idempotency_key="active-start",
        )
        gated = runtime.raise_gate(
            session_id,
            started["goal"]["goalId"],
            "waiting_user",
            "Waiting for a decision",
            source_run_id=run["id"],
            expected_revision=started["revision"],
            idempotency_key="active-gate",
        )
        self.assertEqual(gated["goal"]["lifecycle"], "active")
        self.assertEqual(gated["goal"]["gate"]["type"], "waiting_user")
        failed = call("goal_cancel", {"reason": "   "}, "active-cancel-empty")
        self.assertEqual(failed["status"], "completed")
        self.assertFalse(failed["result"]["ok"])
        self.assertIn("requires a reason", failed["result"]["error"])
        self.assertEqual(
            server_mod.goal_v2_runtime().read(session_id).state.goal["lifecycle"],
            "active",
        )
        cancelled = call(
            "goal_cancel", {"reason": "User confirmed cancellation"}, "active-cancel",
        )["result"]
        self.assertEqual(cancelled["goal"]["lifecycle"], "cancelled")
        self.assertEqual(cancelled["goal"]["gate"]["type"], "waiting_user")

    def test_legacy_text_question_accepts_nonempty_text_without_prompt_parsing(self):
        pending = {
            "requestId": "legacy-text-request",
            "title": "Legacy question",
            "questions": [{
                "id": "url",
                "prompt": "Which URL should be analyzed?",
                "type": "text",
                "required": True,
                "allowOther": False,
                "options": [],
            }],
        }
        result = server_mod._normalize_agent_input_result(
            pending,
            [{
                "id": "url",
                "status": "resolved",
                "text": "你帮我找",
            }],
        )
        self.assertEqual(result["answers"][0]["text"], "你帮我找")
        self.assertEqual(result["answers"][0]["answer"], "你帮我找")

    def test_new_questionnaire_format_requires_custom_input_and_one_recommendation(self):
        definition = server_mod._SERVER_TOOL_DEFINITIONS["request_user_input"]["function"]
        questions_schema = definition["parameters"]["properties"]["questions"]
        question_schema = definition["parameters"]["properties"]["questions"]["items"]
        self.assertEqual(questions_schema["minItems"], 1)
        self.assertEqual(questions_schema["maxItems"], 5)
        self.assertIn("normally use no more than three", definition["description"])
        self.assertIn("four or five only", definition["description"])
        self.assertEqual(question_schema["properties"]["type"]["enum"], ["single", "multiple"])
        self.assertEqual(question_schema["properties"]["options"]["minItems"], 2)
        self.assertEqual(question_schema["properties"]["options"]["maxItems"], 3)
        self.assertIn("allowOther", question_schema["required"])
        self.assertIn("recommended", question_schema["properties"]["options"]["items"]["required"])

        valid = {
            "id": "valid-call",
            "arguments": {
                "questions": [{
                    "id": "target",
                    "prompt": "Choose a target",
                    "type": "single",
                    "allowOther": True,
                    "options": [
                        {
                            "value": "api", "label": "API",
                            "description": "Recommended for this request.",
                            "recommended": True,
                        },
                        {
                            "value": "ui", "label": "UI",
                            "description": "Use for interface work.",
                            "recommended": False,
                        },
                    ],
                }],
            },
        }
        normalized = server_mod._normalize_agent_input_request(valid)
        self.assertTrue(normalized["questions"][0]["allowOther"])
        self.assertEqual(
            [item["recommended"] for item in normalized["questions"][0]["options"]],
            [True, False],
        )

        for question_count in (1, 3, 5):
            with self.subTest(question_count=question_count):
                questions = [
                    {
                        **valid["arguments"]["questions"][0],
                        "id": f"target-{index}",
                        "prompt": f"Choose target {index}",
                    }
                    for index in range(question_count)
                ]
                accepted = server_mod._normalize_agent_input_request({
                    "id": f"valid-{question_count}",
                    "arguments": {"questions": questions},
                })
                self.assertEqual(len(accepted["questions"]), question_count)

        six_questions = [
            {
                **valid["arguments"]["questions"][0],
                "id": f"too-many-{index}",
                "prompt": f"Too many {index}",
            }
            for index in range(6)
        ]
        with self.assertRaisesRegex(ValueError, "requires 1 to 5 questions"):
            server_mod._normalize_agent_input_request({
                "id": "six-question-call",
                "arguments": {"questions": six_questions},
            })

        invalid_cases = {
            "text type": {"type": "text"},
            "custom input disabled": {"allowOther": False},
            "one choice": {"options": [valid["arguments"]["questions"][0]["options"][0]]},
            "no recommendation": {"options": [
                {**item, "recommended": False}
                for item in valid["arguments"]["questions"][0]["options"]
            ]},
            "two recommendations": {"options": [
                {**item, "recommended": True}
                for item in valid["arguments"]["questions"][0]["options"]
            ]},
            "empty recommendation reason": {"options": [
                {**valid["arguments"]["questions"][0]["options"][0], "description": ""},
                valid["arguments"]["questions"][0]["options"][1],
            ]},
        }
        for label, delta in invalid_cases.items():
            with self.subTest(label=label):
                question = {**valid["arguments"]["questions"][0], **delta}
                with self.assertRaises(ValueError):
                    server_mod._normalize_agent_input_request({
                        "id": "invalid-call", "arguments": {"questions": [question]},
                    })

    def test_invalid_new_questionnaire_is_repairable_in_the_same_agent_run(self):
        def tool_round(call_id, arguments):
            return [{
                "choices": [{
                    "delta": {"tool_calls": [{
                        "index": 0,
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": "request_user_input",
                            "arguments": json.dumps(arguments),
                        },
                    }]},
                    "finish_reason": "tool_calls",
                }],
            }]

        valid_question = {
            "id": "target",
            "prompt": "Choose a target",
            "type": "single",
            "required": True,
            "allowOther": True,
            "options": [
                {
                    "value": "api", "label": "API",
                    "description": "Recommended for the current request.",
                    "recommended": True,
                },
                {
                    "value": "ui", "label": "UI",
                    "description": "Use for interface work.",
                    "recommended": False,
                },
            ],
        }
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                tool_round("invalid-questionnaire", {
                    "questions": [{
                        "id": "target",
                        "prompt": "Choose a target",
                        "type": "text",
                        "allowOther": False,
                    }],
                }),
                tool_round("repaired-questionnaire", {"questions": [valid_question]}),
                [{"choices": [{
                    "delta": {"content": "repaired questionnaire complete"},
                    "finish_reason": "stop",
                }]}],
            ]

        run = server_mod._create_agent_run(
            "questionnaire-format-repair",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "ask after repairing format"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["request_user_input"]],
            },
            self.base_url,
            ["questionnaire-repair-key"],
            allowed_tools=["request_user_input"],
            max_rounds=4,
        )
        self._wait_status(run, "waiting_user_input")
        self._wait_worker_idle(run)
        waiting = server_mod._agent_snapshot(run, 0)
        executions = {item["toolCallId"]: item for item in waiting["toolExecutions"]}
        self.assertFalse(executions["invalid-questionnaire"]["result"]["ok"])
        self.assertEqual(executions["invalid-questionnaire"]["status"], "completed")
        self.assertEqual(executions["repaired-questionnaire"]["status"], "waiting_user_input")
        self.assertEqual(waiting["status"], "waiting_user_input")

        server_mod._submit_agent_input(run, [{
            "id": "target",
            "status": "resolved",
            "values": [],
            "other": "custom target",
        }])
        server_mod._resume_agent_run(run, ["questionnaire-repair-resume-key"])
        self._wait_terminal(run)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["result"]["content"], "repaired questionnaire complete")

    def test_active_agent_steer_is_durable_idempotent_and_consumed_once(self):
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                [{
                    "choices": [{
                        "delta": {"content": "stale candidate"},
                        "finish_reason": "stop",
                    }],
                }],
                [{
                    "choices": [{
                        "delta": {"content": "guided result"},
                        "finish_reason": "stop",
                    }],
                }],
            ]

        run = server_mod._create_agent_run(
            "steer-active-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "slow request"}],
            },
            self.base_url,
            ["steer-secret-key"],
        )
        self.assertTrue(_AgentUpstream.slow_started.wait(timeout=2))
        receipt = server_mod._submit_agent_steer(
            run,
            {"role": "user", "content": "use the new priority"},
            "steer-client-1",
        )
        duplicate = server_mod._submit_agent_steer(
            run,
            {"role": "user", "content": "use the new priority"},
            "steer-client-1",
        )
        self.assertFalse(receipt["duplicate"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(receipt["steerId"], duplicate["steerId"])
        with self.assertRaisesRegex(ValueError, "different steer message"):
            server_mod._submit_agent_steer(
                run,
                "different content",
                "steer-client-1",
            )

        _AgentUpstream.release_slow.set()
        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "guided result")
        self.assertEqual(snapshot["pendingSteerCount"], 0)
        self.assertEqual(snapshot["steerReceipts"][0]["status"], "consumed")
        self.assertEqual(_AgentUpstream.calls, 2)
        self.assertEqual(
            sum(
                message.get("role") == "user"
                and message.get("content") == "use the new priority"
                for message in run["messages"]
            ),
            1,
        )
        self.assertTrue(any(
            message.get("role") == "user"
            and message.get("content") == "use the new priority"
            for message in _AgentUpstream.payloads[1]["messages"]
        ))
        event_types = [event["type"] for event in snapshot["events"]]
        self.assertEqual(event_types.count("steer_submitted"), 1)
        self.assertEqual(event_types.count("steer_consumed"), 1)
        self.assertLess(
            event_types.index("steer_submitted"),
            event_types.index("steer_consumed"),
        )
        persisted = json.loads(
            server_mod._agent_run_path(run["id"]).read_text(encoding="utf-8")
        )
        self.assertEqual(persisted["version"], 5)
        self.assertEqual(persisted["pendingSteers"], [])
        self.assertNotIn("steer-secret-key", json.dumps(persisted))

    def test_pending_agent_steer_survives_restart_and_resume(self):
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [[{
                "choices": [{
                    "delta": {"content": "restored guided result"},
                    "finish_reason": "stop",
                }],
            }]]
        run = server_mod._create_agent_run(
            "steer-restart-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "original task"}],
            },
            self.base_url,
            [],
            start_worker=False,
        )
        server_mod._submit_agent_steer(
            run,
            "restored steer",
            "steer-restart-client",
        )
        with server_mod._agent_run_lock:
            server_mod._agent_runs.pop(run["id"], None)

        restored = server_mod._get_agent_run(run["id"])
        self.assertEqual(restored["status"], "waiting_credentials")
        self.assertEqual(len(restored["pending_steers"]), 1)
        server_mod._resume_agent_run(
            restored,
            ["steer-resume-key"],
            self.base_url,
        )
        self._wait_terminal(restored)
        self.assertEqual(restored["result"]["content"], "restored guided result")
        self.assertEqual(restored["pending_steers"], [])
        self.assertEqual(restored["steer_receipts"][0]["status"], "consumed")
        self.assertEqual(
            [message.get("content") for message in restored["messages"]].count(
                "restored steer"
            ),
            1,
        )

    def test_terminal_agent_rejects_new_steer(self):
        run = server_mod._create_agent_run(
            "steer-terminal-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "terminal task"}],
            },
            self.base_url,
            ["terminal-steer-key"],
        )
        self._wait_terminal(run)
        with self.assertRaisesRegex(
            server_mod.AgentRunConflictError,
            "cannot be steered",
        ):
            server_mod._submit_agent_steer(
                run,
                "too late",
                "terminal-steer-client",
            )

    def test_accept_profile_waits_for_durable_edit_authorization(self):
        target = self.project_dir / "README.md"
        run = server_mod._create_agent_run(
            "edit-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "propose edit"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["propose_edit"]],
            },
            self.base_url,
            ["edit-secret-key"],
            allowed_tools=["propose_edit"],
            permission_profile="accept",
        )
        self._wait_status(run, "waiting_authorization")
        self._wait_worker_idle(run)

        waiting = server_mod._agent_snapshot(run, 0)
        pending = waiting["pendingAuthorization"]
        self.assertEqual(waiting["permissionProfile"], "accept")
        self.assertEqual(pending["toolCallId"], "agent-edit-1")
        self.assertEqual(pending["path"], "README.md")
        self.assertIn("Authorized Agent", pending["diff"])
        self.assertNotIn("newContent", pending)
        self.assertEqual(target.read_text(encoding="utf-8"), "# Durable Agent\n")
        self.assertEqual(run["keys"], [])
        persisted = server_mod._agent_run_path(run["id"]).read_text(encoding="utf-8")
        self.assertIn('"status": "waiting_authorization"', persisted)
        self.assertNotIn("edit-secret-key", persisted)

        result = server_mod._submit_agent_authorization(
            run, pending["authorizationId"], "approved",
        )
        self.assertTrue(result["applied"])
        self.assertFalse(result["replayed"])
        self.assertEqual(target.read_text(encoding="utf-8"), "# Authorized Agent\n")
        self.assertEqual(run["status"], "waiting_credentials")
        self.assertEqual(len(list((self.data_dir / "file-backups").glob("*.bak"))), 1)

        server_mod._resume_agent_run(run, ["edit-resume-key"])
        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "edit task complete")
        self.assertIsNone(snapshot["pendingAuthorization"])
        event_types = [event["type"] for event in snapshot["events"]]
        for expected in (
            "authorization_required", "authorization_submitted",
            "tool_completed", "waiting_credentials", "resumed", "completed",
        ):
            self.assertIn(expected, event_types)

    def test_plan_profile_returns_edit_proposal_without_writing(self):
        target = self.project_dir / "README.md"
        run = server_mod._create_agent_run(
            "edit-plan-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "propose edit"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["propose_edit"]],
            },
            self.base_url,
            ["edit-plan-key"],
            allowed_tools=["propose_edit"],
            permission_profile="plan",
        )
        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["toolExecutions"][0]["status"], "completed")
        self.assertTrue(snapshot["toolExecutions"][0]["result"]["proposalOnly"])
        self.assertEqual(target.read_text(encoding="utf-8"), "# Durable Agent\n")
        self.assertFalse((self.data_dir / "file-backups").exists())

    def test_rejected_edit_authorization_keeps_file_unchanged(self):
        target = self.project_dir / "README.md"
        run = server_mod._create_agent_run(
            "edit-reject-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "propose edit"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["propose_edit"]],
            },
            self.base_url,
            ["edit-reject-key"],
            allowed_tools=["propose_edit"],
            permission_profile="accept",
        )
        self._wait_status(run, "waiting_authorization")
        self._wait_worker_idle(run)
        pending = server_mod._agent_snapshot(run, 0)["pendingAuthorization"]
        with server_mod._agent_run_lock:
            server_mod._agent_runs.pop(run["id"], None)
        loaded = server_mod._get_agent_run(run["id"])
        self.assertEqual(loaded["status"], "waiting_authorization")
        self.assertEqual(
            server_mod._agent_snapshot(loaded, 0)["pendingAuthorization"]["authorizationId"],
            pending["authorizationId"],
        )
        result = server_mod._submit_agent_authorization(
            loaded, pending["authorizationId"], "rejected",
        )
        self.assertTrue(result["rejected"])
        self.assertFalse(result["applied"])
        self.assertEqual(target.read_text(encoding="utf-8"), "# Durable Agent\n")
        self.assertFalse((self.data_dir / "file-backups").exists())

    def test_edit_proposal_apply_is_idempotent_after_written_content(self):
        proposal = server_mod.execute_propose_edit_tool({
            "path": "README.md",
            "oldText": "Durable Agent",
            "newText": "Authorized Agent",
        })
        first = server_mod.execute_apply_edit_proposal(proposal)
        second = server_mod.execute_apply_edit_proposal(proposal)
        self.assertTrue(first["applied"])
        self.assertFalse(first["replayed"])
        self.assertTrue(second["applied"])
        self.assertTrue(second["replayed"])
        self.assertEqual(len(list((self.data_dir / "file-backups").glob("*.bak"))), 1)

    def test_approved_stale_edit_returns_conflict_without_overwriting(self):
        target = self.project_dir / "README.md"
        run = server_mod._create_agent_run(
            "edit-conflict-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "propose edit"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["propose_edit"]],
            },
            self.base_url,
            ["edit-conflict-key"],
            allowed_tools=["propose_edit"],
            permission_profile="accept",
        )
        self._wait_status(run, "waiting_authorization")
        self._wait_worker_idle(run)
        pending = server_mod._agent_snapshot(run, 0)["pendingAuthorization"]
        target.write_text("# Changed elsewhere\n", encoding="utf-8")
        result = server_mod._submit_agent_authorization(
            run, pending["authorizationId"], "approved",
        )
        self.assertFalse(result["ok"])
        self.assertTrue(result["conflict"])
        self.assertFalse(result["applied"])
        self.assertEqual(target.read_text(encoding="utf-8"), "# Changed elsewhere\n")
        self.assertFalse((self.data_dir / "file-backups").exists())

    def test_restart_after_write_replays_approved_edit_without_second_backup(self):
        run = server_mod._create_agent_run(
            "edit-replay-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "propose edit"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["propose_edit"]],
            },
            self.base_url,
            ["edit-replay-key"],
            allowed_tools=["propose_edit"],
            permission_profile="accept",
        )
        self._wait_status(run, "waiting_authorization")
        self._wait_worker_idle(run)
        pending = server_mod._agent_snapshot(run, 0)["pendingAuthorization"]
        first = server_mod.execute_apply_edit_proposal(run["pending_authorization"]["proposal"])
        self.assertFalse(first["replayed"])
        with server_mod._agent_run_lock:
            server_mod._agent_runs.pop(run["id"], None)
        loaded = server_mod._get_agent_run(run["id"])
        second = server_mod._submit_agent_authorization(
            loaded, pending["authorizationId"], "approved",
        )
        self.assertTrue(second["replayed"])
        self.assertEqual(len(list((self.data_dir / "file-backups").glob("*.bak"))), 1)

    def test_bypass_restart_reuses_persisted_proposal_after_write(self):
        run = server_mod._create_agent_run(
            "edit-bypass-replay-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "propose edit"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["propose_edit"]],
            },
            self.base_url,
            ["edit-bypass-key"],
            allowed_tools=["propose_edit"],
            permission_profile="accept",
        )
        self._wait_status(run, "waiting_authorization")
        self._wait_worker_idle(run)
        proposal = run["pending_authorization"]["proposal"]
        first = server_mod.execute_apply_edit_proposal(proposal)
        self.assertFalse(first["replayed"])
        execution = run["tool_executions"]["agent-edit-1"]
        execution["status"] = "applying_edit"
        execution["proposal"] = proposal
        run["permission_profile"] = "bypass"
        run["pending_authorization"] = None
        run["status"] = "tools"
        server_mod._persist_agent_run(run)
        with server_mod._agent_run_lock:
            server_mod._agent_runs.pop(run["id"], None)

        loaded = server_mod._get_agent_run(run["id"])
        self.assertEqual(loaded["status"], "waiting_credentials")
        with mock.patch.object(server_mod, "execute_registered_tool") as execute_mock:
            server_mod._resume_agent_run(loaded, ["edit-bypass-resume-key"])
            self._wait_status(loaded, "waiting_recovery")
            execute_mock.assert_not_called()
            server_mod._resume_agent_run(
                loaded,
                ["edit-bypass-resume-key"],
                self.base_url,
            )
            self._wait_terminal(loaded)
            execute_mock.assert_not_called()
        result = loaded["tool_executions"]["agent-edit-1"]["result"]
        self.assertTrue(result["replayed"])
        self.assertEqual(loaded["result"]["content"], "edit task complete")
        self.assertEqual(len(list((self.data_dir / "file-backups").glob("*.bak"))), 1)

    def test_restart_recovery_reuses_completed_tool_execution(self):
        run_id = uuid.uuid4().hex
        arguments = '{"path":"README.md"}'
        fingerprint = hashlib.sha256(f"read_file\0{arguments}".encode()).hexdigest()
        timestamp = server_mod.now_iso()
        tool_result = {
            "ok": True,
            "action": "read_file",
            "path": "README.md",
            "content": "# Durable Agent\n",
            "size": 16,
            "truncated": False,
            "lineRange": None,
        }
        record = {
            "version": 1,
            "id": run_id,
            "sessionId": "restart-session",
            "status": "tools",
            "resumeStatus": "",
            "error": "",
            "baseUrl": self.base_url,
            "request": {"model": "test-model", "tool_choice": "auto"},
            "messages": [
                {"role": "user", "content": "inspect after restart"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "agent-call-1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": arguments},
                    }],
                },
            ],
            "tools": [server_mod._SERVER_TOOL_DEFINITIONS["read_file"]],
            "rounds": [{"round": 1, "toolCalls": [], "usage": {"total_tokens": 9}}],
            "pendingToolCalls": [{
                "index": 0,
                "id": "agent-call-1",
                "type": "function",
                "function": {"name": "read_file", "arguments": arguments},
                "arguments": {"path": "README.md"},
                "parseError": "",
                "fingerprint": fingerprint,
            }],
            "toolExecutions": {
                "agent-call-1": {
                    "name": "read_file",
                    "arguments": arguments,
                    "fingerprint": fingerprint,
                    "status": "completed",
                    "result": tool_result,
                    "error": "",
                    "startedAt": timestamp,
                    "completedAt": timestamp,
                },
            },
            "usage": {"total_tokens": 9},
            "result": {},
            "events": [],
            "nextSeq": 1,
            "maxRounds": 4,
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }
        server_mod.write_json(server_mod._agent_run_path(run_id), record)

        loaded = server_mod._get_agent_run(run_id)
        self.assertEqual(loaded["status"], "waiting_credentials")
        with mock.patch.object(server_mod, "execute_registered_tool") as execute_mock:
            server_mod._resume_agent_run(loaded, ["restart-secret-key"])
            self._wait_terminal(loaded)
            execute_mock.assert_not_called()

        snapshot = server_mod._agent_snapshot(loaded, 0)
        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "read-only task complete")
        self.assertEqual(_AgentUpstream.calls, 1)
        self.assertTrue(any(
            message.get("role") == "tool" and message.get("tool_call_id") == "agent-call-1"
            for message in loaded["messages"]
        ))
        persisted = server_mod._agent_run_path(run_id).read_text(encoding="utf-8")
        self.assertNotIn("restart-secret-key", persisted)

    def test_restart_preserves_pending_questionnaire_before_credentials_resume(self):
        run = server_mod._create_agent_run(
            "question-restart-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "ask for target"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["request_user_input"]],
            },
            self.base_url,
            ["question-before-restart-key"],
            allowed_tools=["request_user_input"],
        )
        self._wait_status(run, "waiting_user_input")
        self._wait_worker_idle(run)
        run_id = run["id"]
        with server_mod._agent_run_lock:
            server_mod._agent_runs.pop(run_id, None)

        loaded = server_mod._get_agent_run(run_id)
        self.assertEqual(loaded["status"], "waiting_user_input")
        self.assertEqual(loaded["pending_input"]["toolCallId"], "agent-question-1")
        self.assertEqual(loaded["keys"], [])

        server_mod._submit_agent_input(loaded, [{
            "id": "target",
            "status": "resolved",
            "values": ["ui"],
        }])
        self.assertEqual(loaded["status"], "waiting_credentials")
        server_mod._resume_agent_run(
            loaded,
            ["question-after-restart-key"],
            self.base_url,
        )
        self._wait_terminal(loaded)
        self.assertEqual(loaded["result"]["content"], "questionnaire task complete")
        self.assertEqual(_AgentUpstream.calls, 2)

    def test_repeated_tool_call_id_reuses_execution_but_keeps_protocol_pair(self):
        original_execute = server_mod.execute_registered_tool
        with mock.patch.object(
            server_mod,
            "execute_registered_tool",
            wraps=original_execute,
        ) as execute_mock:
            run = server_mod._create_agent_run(
                "repeat-call-session",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "repeat tool id"}],
                    "tools": [server_mod._SERVER_TOOL_DEFINITIONS["read_file"]],
                },
                self.base_url,
                ["repeat-secret-key"],
                allowed_tools=["read_file"],
                max_rounds=4,
            )
            self._wait_terminal(run)

        self.assertEqual(run["status"], "completed")
        self.assertEqual(_AgentUpstream.calls, 3)
        self.assertEqual(execute_mock.call_count, 1)
        self.assertEqual(
            sum(message.get("role") == "tool" for message in run["messages"]),
            2,
        )
        replay_events = [
            event for event in run["events"]
            if event["type"] == "tool_completed" and event["data"].get("replayed")
        ]
        self.assertEqual(len(replay_events), 1)

    def test_legacy_model_round_limit_is_read_but_not_enforced(self):
        run = server_mod._create_agent_run(
            "round-limit-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "repeat tool id"}],
                "tools": [server_mod._SERVER_TOOL_DEFINITIONS["read_file"]],
            },
            self.base_url,
            ["round-limit-secret-key"],
            allowed_tools=["read_file"],
            max_rounds=2,
        )
        self._wait_terminal(run)

        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["result"]["content"], "read-only task complete")
        self.assertEqual(_AgentUpstream.calls, 3)
        self.assertEqual(run["keys"], [])

    def test_worker_continues_after_legacy_fiftieth_round_without_goal_handoff(self):
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [[{
                "choices": [{
                    "delta": {"content": "continued after legacy round fifty"},
                    "finish_reason": "stop",
                }],
            }]]
        run = server_mod._create_agent_run(
            "legacy-round-fifty-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "continue"}],
            },
            self.base_url,
            ["round-fifty-key"],
            allowed_tools=[],
            max_rounds=50,
            start_worker=False,
        )
        run["rounds"] = [{
            "round": index,
            "content": "prior progress",
            "reasoning": "",
            "toolCalls": [],
            "finishReason": "stop",
            "usage": {},
            "completedAt": "2030-01-01T00:00:00Z",
            "outcome": "completed",
        } for index in range(1, 51)]

        server_mod._start_agent_worker(run)
        self._wait_terminal(run)

        self.assertEqual(run["status"], "completed")
        self.assertEqual(len(run["rounds"]), 51)
        self.assertEqual(run["result"]["content"], "continued after legacy round fifty")
        self.assertFalse(run.get("continuation"))

    def test_empty_compaction_summary_retries_once_then_persists_backoff(self):
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                [{"choices": [{"delta": {}, "finish_reason": "stop"}]}],
                [{"choices": [{"delta": {}, "finish_reason": "stop"}]}],
            ]
        run = server_mod._create_agent_run(
            "empty-compaction-backoff-session",
            {
                "model": "test-model",
                "messages": [
                    {"role": "system", "content": "system rules"},
                    {"role": "user", "content": "old task"},
                    {"role": "assistant", "content": "old result"},
                    {"role": "user", "content": "current task"},
                ],
            },
            self.base_url,
            ["compaction-key"],
            allowed_tools=[],
            start_worker=False,
        )
        original_messages = json.loads(json.dumps(run["messages"]))

        failed = server_mod._run_agent_auto_compaction(
            run, "threshold", before_estimate=10000,
        )
        repeated = server_mod._run_agent_auto_compaction(
            run, "threshold", before_estimate=10000,
        )

        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["errorCode"], "empty_compaction_summary")
        self.assertEqual(failed["attempts"], 2)
        self.assertEqual(repeated["status"], "skipped")
        self.assertEqual(repeated["reason"], "compaction_backoff")
        self.assertEqual(_AgentUpstream.calls, 2)
        self.assertEqual(run["messages"], original_messages)
        self.assertEqual(run["compaction_recovery"]["lastErrorCode"], "empty_compaction_summary")
        self.assertTrue(run["compaction_recovery"]["nextRetryAt"])
        record = server_mod._agent_run_record(run)
        restored = server_mod._agent_run_from_record(record)
        repeated_after_restart = server_mod._run_agent_auto_compaction(
            restored, "threshold", before_estimate=10000,
        )
        self.assertEqual(repeated_after_restart["status"], "skipped")
        self.assertEqual(repeated_after_restart["reason"], "compaction_backoff")
        self.assertEqual(restored["messages"], original_messages)
        self.assertEqual(_AgentUpstream.calls, 2)

    def test_nonshrinking_compaction_keeps_original_history_atomically(self):
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [[{
                "choices": [{
                    "delta": {"content": "A valid but non-shrinking final summary."},
                    "finish_reason": "stop",
                }],
            }]]
        run = server_mod._create_agent_run(
            "nonshrinking-compaction-session",
            {
                "model": "test-model",
                "messages": [
                    {"role": "system", "content": "system rules"},
                    {"role": "user", "content": "old task"},
                    {"role": "assistant", "content": "old result"},
                    {"role": "user", "content": "current task"},
                ],
            },
            self.base_url,
            ["compaction-key"],
            allowed_tools=[],
            start_worker=False,
        )
        original_messages = json.loads(json.dumps(run["messages"]))

        failed = server_mod._run_agent_auto_compaction(
            run, "threshold", before_estimate=1,
        )

        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["errorCode"], "compaction_not_smaller")
        self.assertEqual(run["messages"], original_messages)
        self.assertEqual(run["compactions"], [])
        self.assertEqual(_AgentUpstream.calls, 1)
        compaction_payload = _AgentUpstream.payloads[0]
        self.assertNotIn("tools", compaction_payload)
        self.assertIn("Return only the final summary", compaction_payload["messages"][0]["content"])

    def test_credentials_inside_payload_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "credentials"):
            server_mod._create_agent_run(
                "session-agent",
                {
                    "model": "test-model",
                    "apiKey": "must-not-persist",
                    "messages": [{"role": "user", "content": "hi"}],
                },
                self.base_url,
                [],
            )
        with self.assertRaisesRegex(ValueError, "credentials"):
            server_mod._create_agent_run(
                "session-agent",
                {
                    "model": "test-model",
                    "extra_body": {"authorization": "Bearer must-not-persist"},
                    "messages": [{"role": "user", "content": "hi"}],
                },
                self.base_url,
                [],
            )
        with self.assertRaisesRegex(ValueError, "credentials"):
            server_mod._create_agent_run(
                "session-agent",
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "hi"}],
                },
                "https://secret@example.com/v1",
                [],
            )

    def test_http_create_poll_and_idempotent_cancel(self):
        server_mod.ThreadingHTTPServer.daemon_threads = True
        http_server = server_mod.ThreadingHTTPServer(
            ("127.0.0.1", 0), server_mod.CodeHandler,
        )
        thread = threading.Thread(target=http_server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{http_server.server_address[1]}"
        try:
            response = requests.post(
                base + "/api/agent/runs",
                json={
                    "sessionId": "http-agent",
                    "payload": {
                        "model": "test-model",
                        "messages": [{"role": "user", "content": "inspect through HTTP"}],
                        "tools": [server_mod._SERVER_TOOL_DEFINITIONS["read_file"]],
                    },
                    "allowedTools": ["read_file"],
                    "baseUrl": self.base_url,
                    "keys": ["http-secret-key"],
                },
                timeout=5,
            )
            self.assertEqual(response.status_code, 201)
            run_id = response.json()["agentRunId"]

            deadline = time.time() + 5
            snapshot = {}
            while time.time() < deadline:
                poll = requests.get(
                    f"{base}/api/agent/runs/{run_id}?cursor=0&wait=1",
                    timeout=3,
                )
                self.assertEqual(poll.status_code, 200)
                snapshot = poll.json()
                if snapshot.get("status") in server_mod._AGENT_RUN_TERMINAL:
                    break
            self.assertEqual(snapshot.get("status"), "completed")
            self.assertEqual(snapshot.get("result", {}).get("content"), "read-only task complete")
            self.assertNotIn("http-secret-key", json.dumps(snapshot))

            cancel = requests.delete(f"{base}/api/agent/runs/{run_id}", timeout=3)
            self.assertEqual(cancel.status_code, 200)
            self.assertEqual(cancel.json()["status"], "completed")
        finally:
            http_server.shutdown()
            http_server.server_close()
            thread.join(timeout=2)

    def test_http_questionnaire_submit_endpoint_resumes_same_agent_run(self):
        server_mod.ThreadingHTTPServer.daemon_threads = True
        http_server = server_mod.ThreadingHTTPServer(
            ("127.0.0.1", 0), server_mod.CodeHandler,
        )
        thread = threading.Thread(target=http_server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{http_server.server_address[1]}"
        try:
            created = requests.post(
                base + "/api/agent/runs",
                json={
                    "sessionId": "http-question-agent",
                    "payload": {
                        "model": "test-model",
                        "messages": [{"role": "user", "content": "ask for target"}],
                        "tools": [server_mod._SERVER_TOOL_DEFINITIONS["request_user_input"]],
                    },
                    "allowedTools": ["request_user_input"],
                    "baseUrl": self.base_url,
                    "keys": ["http-question-key"],
                },
                timeout=5,
            )
            self.assertEqual(created.status_code, 201)
            run_id = created.json()["agentRunId"]

            deadline = time.time() + 5
            snapshot = {}
            while time.time() < deadline:
                snapshot = requests.get(
                    f"{base}/api/agent/runs/{run_id}?cursor=0&wait=1",
                    timeout=3,
                ).json()
                if snapshot.get("status") == "waiting_user_input":
                    break
            self.assertEqual(snapshot.get("status"), "waiting_user_input")
            self.assertEqual(snapshot.get("pendingInput", {}).get("toolCallId"), "agent-question-1")

            submitted = requests.post(
                f"{base}/api/agent/runs/{run_id}/input",
                json={"answers": [{
                    "id": "target",
                    "status": "resolved",
                    "values": ["ui"],
                }]},
                timeout=3,
            )
            self.assertEqual(submitted.status_code, 200)
            self.assertEqual(submitted.json()["status"], "waiting_credentials")

            resumed = requests.post(
                f"{base}/api/agent/runs/{run_id}/resume",
                json={"keys": ["http-question-resume-key"], "baseUrl": self.base_url},
                timeout=3,
            )
            self.assertEqual(resumed.status_code, 200)
            deadline = time.time() + 5
            while time.time() < deadline:
                snapshot = requests.get(
                    f"{base}/api/agent/runs/{run_id}?cursor=0&wait=1",
                    timeout=3,
                ).json()
                if snapshot.get("status") in server_mod._AGENT_RUN_TERMINAL:
                    break
            self.assertEqual(snapshot.get("status"), "completed")
            self.assertEqual(snapshot.get("result", {}).get("content"), "questionnaire task complete")
        finally:
            http_server.shutdown()
            http_server.server_close()
            thread.join(timeout=2)

    def test_http_questionnaire_rejection_is_structured_and_has_no_side_effects(self):
        server_mod.ThreadingHTTPServer.daemon_threads = True
        http_server = server_mod.ThreadingHTTPServer(
            ("127.0.0.1", 0), server_mod.CodeHandler,
        )
        thread = threading.Thread(target=http_server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{http_server.server_address[1]}"
        try:
            created = requests.post(
                base + "/api/agent/runs",
                json={
                    "sessionId": "http-question-terminal",
                    "payload": {
                        "model": "test-model",
                        "messages": [{"role": "user", "content": "ask for target"}],
                        "tools": [server_mod._SERVER_TOOL_DEFINITIONS["request_user_input"]],
                    },
                    "allowedTools": ["request_user_input"],
                    "baseUrl": self.base_url,
                    "keys": ["http-question-terminal-key"],
                },
                timeout=5,
            )
            self.assertEqual(created.status_code, 201)
            run_id = created.json()["agentRunId"]
            deadline = time.time() + 5
            snapshot = {}
            while time.time() < deadline:
                snapshot = requests.get(
                    f"{base}/api/agent/runs/{run_id}?cursor=0&wait=1",
                    timeout=3,
                ).json()
                if snapshot.get("status") == "waiting_user_input":
                    break
            self.assertEqual(snapshot.get("status"), "waiting_user_input")
            request_id = snapshot["pendingInput"]["requestId"]
            answers = [{"id": "target", "status": "resolved", "values": ["ui"]}]

            before_mismatch = server_mod._agent_snapshot(
                server_mod._get_agent_run(run_id), 0,
            )
            mismatch = requests.post(
                f"{base}/api/agent/runs/{run_id}/input",
                json={"requestId": "stale-request", "answers": answers},
                timeout=3,
            )
            self.assertEqual(mismatch.status_code, 409)
            self.assertEqual(mismatch.json()["errorCode"], "agent_run_input_mismatch")
            self.assertEqual(mismatch.json()["agentRunStatus"], "waiting_user_input")
            self.assertEqual(mismatch.json()["pendingInputRequestId"], request_id)
            self.assertEqual(
                server_mod._agent_snapshot(server_mod._get_agent_run(run_id), 0),
                before_mismatch,
            )

            cancelled = requests.delete(f"{base}/api/agent/runs/{run_id}", timeout=3)
            self.assertEqual(cancelled.status_code, 200)
            self.assertEqual(cancelled.json()["status"], "cancelled")
            run_path = server_mod._agent_run_path(run_id)
            before_rejected = run_path.read_bytes()
            terminal_snapshot = server_mod._agent_snapshot(
                server_mod._get_agent_run(run_id), 0,
            )
            rejected = requests.post(
                f"{base}/api/agent/runs/{run_id}/input",
                json={"requestId": request_id, "answers": answers},
                timeout=3,
            )
            self.assertEqual(rejected.status_code, 409)
            self.assertEqual(rejected.json()["errorCode"], "agent_run_input_inactive")
            self.assertEqual(rejected.json()["agentRunStatus"], "cancelled")
            self.assertFalse(rejected.json()["retryable"])
            self.assertEqual(run_path.read_bytes(), before_rejected)
            self.assertEqual(
                server_mod._agent_snapshot(server_mod._get_agent_run(run_id), 0),
                terminal_snapshot,
            )

            missing = requests.post(
                f"{base}/api/agent/runs/missing-questionnaire/input",
                json={"requestId": request_id, "answers": answers},
                timeout=3,
            )
            self.assertEqual(missing.status_code, 404)
            self.assertEqual(missing.json()["errorCode"], "agent_run_not_found")
            self.assertEqual(missing.json()["agentRunStatus"], "not_found")
        finally:
            http_server.shutdown()
            http_server.server_close()
            thread.join(timeout=2)

    def test_http_steer_endpoint_uses_same_agent_run_and_returns_conflict_after_terminal(self):
        server_mod.ThreadingHTTPServer.daemon_threads = True
        http_server = server_mod.ThreadingHTTPServer(
            ("127.0.0.1", 0), server_mod.CodeHandler,
        )
        thread = threading.Thread(target=http_server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{http_server.server_address[1]}"
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                [{
                    "choices": [{
                        "delta": {"content": "first candidate"},
                        "finish_reason": "stop",
                    }],
                }],
                [{
                    "choices": [{
                        "delta": {"content": "HTTP guided result"},
                        "finish_reason": "stop",
                    }],
                }],
            ]
        try:
            created = requests.post(
                base + "/api/agent/runs",
                json={
                    "sessionId": "http-steer-agent",
                    "payload": {
                        "model": "test-model",
                        "messages": [{"role": "user", "content": "slow request"}],
                    },
                    "baseUrl": self.base_url,
                    "keys": ["http-steer-key"],
                },
                timeout=5,
            )
            self.assertEqual(created.status_code, 201)
            run_id = created.json()["agentRunId"]
            self.assertTrue(_AgentUpstream.slow_started.wait(timeout=2))

            steered = requests.post(
                f"{base}/api/agent/runs/{run_id}/steer",
                json={
                    "clientRequestId": "http-steer-client",
                    "message": {"role": "user", "content": "HTTP steer"},
                },
                timeout=3,
            )
            self.assertEqual(steered.status_code, 200)
            self.assertEqual(steered.json()["agentRunId"], run_id)
            self.assertEqual(steered.json()["result"]["status"], "pending")
            _AgentUpstream.release_slow.set()

            deadline = time.time() + 5
            snapshot = {}
            while time.time() < deadline:
                snapshot = requests.get(
                    f"{base}/api/agent/runs/{run_id}?cursor=0&wait=1",
                    timeout=3,
                ).json()
                if snapshot.get("status") in server_mod._AGENT_RUN_TERMINAL:
                    break
            self.assertEqual(snapshot.get("status"), "completed")
            self.assertEqual(snapshot.get("result", {}).get("content"), "HTTP guided result")

            rejected = requests.post(
                f"{base}/api/agent/runs/{run_id}/steer",
                json={
                    "clientRequestId": "http-steer-late",
                    "message": "too late",
                },
                timeout=3,
            )
            self.assertEqual(rejected.status_code, 409)
            self.assertEqual(rejected.json()["errorCode"], "agent_run_not_active")
        finally:
            _AgentUpstream.release_slow.set()
            http_server.shutdown()
            http_server.server_close()
            thread.join(timeout=2)

    def test_http_edit_authorization_endpoint_submits_durable_decision(self):
        server_mod.ThreadingHTTPServer.daemon_threads = True
        http_server = server_mod.ThreadingHTTPServer(
            ("127.0.0.1", 0), server_mod.CodeHandler,
        )
        thread = threading.Thread(target=http_server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{http_server.server_address[1]}"
        try:
            created = requests.post(
                base + "/api/agent/runs",
                json={
                    "sessionId": "http-edit-agent",
                    "payload": {
                        "model": "test-model",
                        "messages": [{"role": "user", "content": "propose edit"}],
                        "tools": [server_mod._SERVER_TOOL_DEFINITIONS["propose_edit"]],
                    },
                    "allowedTools": ["propose_edit"],
                    "permissionProfile": "accept",
                    "baseUrl": self.base_url,
                    "keys": ["http-edit-key"],
                },
                timeout=5,
            )
            self.assertEqual(created.status_code, 201)
            run_id = created.json()["agentRunId"]
            deadline = time.time() + 5
            snapshot = {}
            while time.time() < deadline:
                snapshot = requests.get(
                    f"{base}/api/agent/runs/{run_id}?cursor=0&wait=1",
                    timeout=3,
                ).json()
                if snapshot.get("status") == "waiting_authorization":
                    break
            pending = snapshot.get("pendingAuthorization") or {}
            self.assertEqual(snapshot.get("status"), "waiting_authorization")

            submitted = requests.post(
                f"{base}/api/agent/runs/{run_id}/authorization",
                json={
                    "authorizationId": pending.get("authorizationId"),
                    "decision": "rejected",
                },
                timeout=3,
            )
            self.assertEqual(submitted.status_code, 200)
            self.assertEqual(submitted.json()["status"], "waiting_credentials")
            self.assertTrue(submitted.json()["result"]["rejected"])
            self.assertEqual(
                (self.project_dir / "README.md").read_text(encoding="utf-8"),
                "# Durable Agent\n",
            )
        finally:
            http_server.shutdown()
            http_server.server_close()
            thread.join(timeout=2)

    def test_cancel_stops_active_model_round_and_clears_credentials(self):
        run = server_mod._create_agent_run(
            "cancel-session",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "slow request"}],
            },
            self.base_url,
            ["cancel-secret-key"],
            allowed_tools=[],
        )
        self.assertTrue(_AgentUpstream.slow_started.wait(timeout=2))
        self.assertTrue(server_mod._cancel_agent_run(run["id"]))
        _AgentUpstream.release_slow.set()
        self._wait_terminal(run)

        self.assertEqual(run["status"], "cancelled")
        self.assertEqual(run["keys"], [])
        time.sleep(0.05)
        event_types = [event["type"] for event in run["events"]]
        self.assertEqual(event_types[-1], "cancelled")
        persisted = server_mod._agent_run_path(run["id"]).read_text(encoding="utf-8")
        self.assertNotIn("cancel-secret-key", persisted)

    def test_content_filter_stops_immediately_without_empty_response_retry(self):
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [[
                {"choices": [{
                    "delta": {},
                    "finish_reason": "content_filter",
                }]},
                {"choices": [], "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 0,
                    "total_tokens": 7,
                }},
            ]]
        run = server_mod._create_agent_run(
            "session-content-filtered",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "complete the task"}],
            },
            self.base_url,
            ["filter-key"],
            allowed_tools=[],
            max_rounds=3,
        )

        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)

        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["errorCode"], "content_filtered")
        self.assertEqual(snapshot["error"], "finish_reason=content_filter")
        self.assertEqual(snapshot["nonActionCount"], 0)
        self.assertEqual(_AgentUpstream.calls, 1)
        self.assertEqual(
            [item["outcome"] for item in run["rounds"]],
            ["content_filtered"],
        )
        self.assertNotIn(
            "model_recovery",
            [event["type"] for event in run["events"]],
        )

    def test_empty_model_round_recovers_once_and_completes(self):
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                [
                    {"choices": [{"delta": {}, "finish_reason": "stop"}]},
                    {"choices": [], "usage": {
                        "prompt_tokens": 3, "completion_tokens": 0, "total_tokens": 3,
                    }},
                ],
                [
                    {"choices": [{
                        "delta": {"content": "Recovered with a complete answer."},
                        "finish_reason": "stop",
                    }]},
                    {"choices": [], "usage": {
                        "prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10,
                    }},
                ],
            ]
        run = server_mod._create_agent_run(
            "session-empty-recovery",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "complete the task"}],
            },
            self.base_url,
            ["recovery-key"],
            allowed_tools=[],
            max_rounds=3,
        )

        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)

        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["result"]["content"], "Recovered with a complete answer.")
        self.assertEqual(snapshot["nonActionCount"], 0)
        self.assertEqual(_AgentUpstream.calls, 2)
        self.assertEqual([item["outcome"] for item in run["rounds"]], ["empty", "completed"])
        recovery = next(event for event in run["events"] if event["type"] == "model_recovery")
        self.assertEqual(recovery["data"]["reason"], "empty")
        self.assertEqual(recovery["data"]["attempt"], 1)
        self.assertTrue(any(
            message.get("role") == "user"
            and str(message.get("content") or "").startswith("[System recovery]")
            for message in _AgentUpstream.payloads[1]["messages"]
        ))
        self.assertNotIn("user_input_required", [event["type"] for event in run["events"]])

    def test_reasoning_only_then_promise_uses_shared_budget_and_persists_failure(self):
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                [
                    {"choices": [{
                        "delta": {"reasoning_content": "I should inspect the repository."},
                        "finish_reason": "stop",
                    }]},
                    {"choices": [], "usage": {
                        "prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7,
                    }},
                ],
                [
                    {"choices": [{
                        "delta": {"content": "Okay, I'll inspect the repository now."},
                        "finish_reason": "stop",
                    }]},
                    {"choices": [], "usage": {
                        "prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10,
                    }},
                ],
            ]
        run = server_mod._create_agent_run(
            "session-shared-recovery",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "inspect the repository"}],
            },
            self.base_url,
            ["recovery-key"],
            allowed_tools=[],
            max_rounds=3,
        )

        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)

        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["errorCode"], "empty_response")
        self.assertEqual(snapshot["nonActionCount"], 2)
        self.assertEqual([item["outcome"] for item in run["rounds"]], ["reasoning_only", "promise"])
        self.assertEqual(
            [event["type"] for event in run["events"]].count("model_recovery"),
            1,
        )

        with server_mod._agent_run_lock:
            server_mod._agent_runs.pop(run["id"], None)
        restored = server_mod._get_agent_run(run["id"])
        restored_snapshot = server_mod._agent_snapshot(restored, 0)
        self.assertEqual(restored_snapshot["errorCode"], "empty_response")
        self.assertEqual(restored_snapshot["nonActionCount"], 2)

    def test_tool_action_resets_prior_promise_recovery_debt(self):
        with _AgentUpstream.scripted_lock:
            _AgentUpstream.scripted_rounds = [
                [
                    {"choices": [{
                        "delta": {"content": "好的，我先检查一下。"},
                        "finish_reason": "stop",
                    }]},
                ],
                [
                    {"choices": [{
                        "delta": {"tool_calls": [{
                            "index": 0,
                            "id": "recovery-read-1",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"path": "README.md"}),
                            },
                        }]},
                        "finish_reason": "tool_calls",
                    }]},
                ],
                [
                    {"choices": [{
                        "delta": {"content": "检查完成：README 内容正常。"},
                        "finish_reason": "stop",
                    }]},
                ],
            ]
        run = server_mod._create_agent_run(
            "session-promise-action",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "inspect README"}],
            },
            self.base_url,
            ["recovery-key"],
            allowed_tools=["read_file"],
            max_rounds=4,
        )

        self._wait_terminal(run)
        snapshot = server_mod._agent_snapshot(run, 0)

        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["nonActionCount"], 0)
        self.assertEqual(
            [item["outcome"] for item in run["rounds"]],
            ["promise", "tool_calls", "completed"],
        )
        self.assertEqual(len(snapshot["toolExecutions"]), 1)
        self.assertEqual(snapshot["toolExecutions"][0]["name"], "read_file")
        self.assertIn("README 内容正常", snapshot["result"]["content"])

    def test_legacy_reasoning_only_pending_input_enters_automatic_recovery(self):
        run = server_mod._create_agent_run(
            "session-legacy-empty",
            {
                "model": "test-model",
                "messages": [{"role": "user", "content": "continue legacy task"}],
            },
            self.base_url,
            ["legacy-key"],
            allowed_tools=[],
            start_worker=False,
        )
        run["pending_input"] = {
            "type": "empty_response",
            "reasoning": "legacy reasoning",
            "requestId": uuid.uuid4().hex,
        }
        run["status"] = "waiting_user_input"
        server_mod._persist_agent_run(run)

        result = server_mod._submit_agent_input(run, {})

        self.assertTrue(result["ok"])
        self.assertEqual(run["status"], "waiting_credentials")
        self.assertEqual(run["resume_status"], "model")
        self.assertEqual(run["non_action_count"], 1)
        self.assertIsNone(run["pending_input"])
        self.assertTrue(str(run["messages"][-1]["content"]).startswith("[System recovery]"))
        recovery = next(event for event in run["events"] if event["type"] == "model_recovery")
        self.assertTrue(recovery["data"]["legacyPendingInput"])


class TestEmptyPromiseDetection(unittest.TestCase):
    """Focused false-positive and false-negative coverage for promise text."""

    def test_chinese_promise_detected(self):
        self.assertTrue(server_mod._is_empty_promise("我来检查一下代码"))
        self.assertTrue(server_mod._is_empty_promise("好的，我来检查一下代码"))
        self.assertTrue(server_mod._is_empty_promise("让我看看"))
        self.assertTrue(server_mod._is_empty_promise("我先来确认一下"))
        self.assertTrue(server_mod._is_empty_promise("马上处理"))
        self.assertTrue(server_mod._is_empty_promise("正在读取文件"))

    def test_english_promise_detected(self):
        self.assertTrue(server_mod._is_empty_promise("I'll check the code"))
        self.assertTrue(server_mod._is_empty_promise("Okay, I'll check the code"))
        self.assertTrue(server_mod._is_empty_promise("Let me look into it"))
        self.assertTrue(server_mod._is_empty_promise("I will handle this"))
        self.assertTrue(server_mod._is_empty_promise("First, let me examine"))

    def test_real_answer_not_promise(self):
        self.assertFalse(server_mod._is_empty_promise(
            "这个项目的目录结构如下：\n- src/\n- tests/\n- docs/\n共找到 15 个文件"))
        self.assertFalse(server_mod._is_empty_promise(
            "The bug is caused by a race condition in the save function."))

    def test_chinese_colon_result_not_promise(self):
        self.assertFalse(server_mod._is_empty_promise(
            "我来总结一下：根因是保存阶段存在竞态条件。"))

    def test_english_colon_result_not_promise(self):
        self.assertFalse(server_mod._is_empty_promise(
            "I'll summarize: the save function has a race condition."))

    def test_first_step_instruction_not_promise(self):
        self.assertFalse(server_mod._is_empty_promise(
            "First, update the configuration. Then restart the service."))

    def test_completed_result_marker_not_promise(self):
        self.assertFalse(server_mod._is_empty_promise("已经修复了保存阶段的竞态条件。"))

    def test_multiline_result_not_promise(self):
        self.assertFalse(server_mod._is_empty_promise(
            "我来汇总检查结果：\n- 配置正常\n- 测试通过\n- 无需修改"))

    def test_long_text_not_promise(self):
        long_text = "这个问题的解决方案包括以下步骤。首先，我们需要检查配置文件..." * 10
        self.assertGreater(len(long_text), 240)
        self.assertFalse(server_mod._is_empty_promise(long_text))

    def test_empty_content_not_promise(self):
        self.assertFalse(server_mod._is_empty_promise(""))
        self.assertFalse(server_mod._is_empty_promise("   "))

    def test_non_action_reason_empty(self):
        self.assertEqual(server_mod._agent_non_action_reason("", ""), "empty")

    def test_non_action_reason_reasoning_only(self):
        self.assertEqual(
            server_mod._agent_non_action_reason("", "checking the repository"),
            "reasoning_only",
        )

    def test_non_action_reason_promise(self):
        self.assertEqual(
            server_mod._agent_non_action_reason("Okay, I'll check the repository.", ""),
            "promise",
        )

    def test_non_action_reason_substantive_completion(self):
        self.assertEqual(
            server_mod._agent_non_action_reason("检查完成：配置正常。", "verified"),
            "",
        )


if __name__ == "__main__":
    unittest.main()
