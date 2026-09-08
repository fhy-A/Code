"""Offline exact-model contracts and real local HTTP/durable replay boundaries."""
import ast
import copy
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import pytest
from code_runtime import reasoning_capabilities as rc, protocol_replay as pr
from code_runtime.model_route_registry import ModelRouteRegistry
from tests.test_reasoning_capabilities import runtime
from tests.test_skill_model_loading import loading_env, make_run


def native_url(model):
    return {"openai": "https://api.openai.com", "deepseek": "https://api.deepseek.com", "anthropic": "https://api.anthropic.com"}[rc.MODELS[model]["provider"]]


def compile_model(model, intent, url=None, route="mr1_fixture", contract=None, budget=8192):
    url = url or native_url(model)
    cap = rc.projection(model, route, url, contract=contract)
    selection = dict(schemaVersion=2, modelId=model, routeRef=route, intent=intent, capabilityRevision=cap["capabilityRevision"])
    wire, snapshot = rc.compile_request(dict(model=model, max_tokens=budget, temperature=.2, top_p=.9), selection,
                                       model_id=model, route_ref=route, base_url=url, contract=contract)
    return wire, snapshot, selection


@pytest.mark.parametrize("model", rc.MODELS)
@pytest.mark.parametrize("intent", rc.INTENTS)
def test_every_exact_model_four_tiers(model, intent):
    wire, snap, _ = compile_model(model, intent)
    profile = rc.MODELS[model]
    assert rc.restore_snapshot(snap, model_id=model, route_ref="mr1_fixture") == snap
    if intent == "default":
        assert not rc.MANAGED_FIELDS.intersection(wire)
    elif profile["provider"] == "deepseek":
        assert wire["reasoning_effort"] == {"low": "low", "medium": "high", "high": "max"}[intent]
        assert wire["thinking"] == {"type": "enabled"}
    elif profile["provider"] == "anthropic":
        assert wire["thinking"]["type"] == profile["thinking"]
        if profile["thinking"] == "enabled":
            assert wire["thinking"]["budget_tokens"] == {"low": 1024, "medium": 2048, "high": 4096}[intent]
        else:
            assert wire["output_config"]["effort"] == intent
    else:
        assert wire["reasoning_effort"] == intent
    assert wire.get("max_tokens", wire.get("max_completion_tokens")) == 8192
    assert snap["schemaVersion"] == (3 if profile.get("replay") else 2)


@pytest.mark.parametrize("intent,budget", [("low", 2047), ("medium", 3071), ("high", 5119)])
def test_sonnet_budget_never_expands(intent, budget):
    with pytest.raises(rc.ReasoningError, match="budget_insufficient"):
        compile_model("claude-sonnet-4-5", intent, budget=budget)
    wire, _, _ = compile_model("claude-sonnet-4-5", intent, budget=budget + 1)
    assert wire["max_tokens"] == budget + 1


def register(registry, url, model):
    catalog = registry.refresh([{"connectionId": "workbar_fixture", "source": "workbar", "key": "synthetic-only",
                                 "baseUrl": url}], lambda _: [model])
    route = catalog["routes"][0]
    raw = registry._catalog["routes"][0]
    contract = {k: raw[k] for k in ("connectionId", "baseUrlId", "modelId")}
    contract.update(upstreamModelId=model, adapterProfile=rc.MODELS[model]["adapter"], revision="fixture-v1",
                    officialEvidence=rc.MODELS[model]["source"], adapterEvidence="local-http-test",
                    routeEvidence="", routeVerified=False, expiresAt="2099-01-01T00:00:00Z")
    registry.register_reasoning_contract(route["routeRef"], contract)
    return route, contract


def test_proxy_requires_exact_reviewed_binding_and_survives_reload(tmp_path):
    registry = ModelRouteRegistry(tmp_path / "routes.json")
    route, contract = register(registry, "https://proxy.invalid", "deepseek-v4-pro")
    assert registry.snapshot()["routes"][0]["reasoning"]["intents"] == list(rc.INTENTS)
    reloaded = ModelRouteRegistry(registry.path)
    reloaded.bind_runtime_base_urls([{"connectionId": "workbar_fixture", "baseUrl": "https://proxy.invalid"}])
    assert reloaded.snapshot()["routes"][0]["reasoning"]["intents"] == list(rc.INTENTS)
    assert not reloaded.snapshot()["routes"][0]["reasoning"]["routeVerified"]
    for field, value in [("baseUrlId", "other"), ("connectionId", "other"), ("modelId", "other"), ("headers", {})]:
        with pytest.raises(ValueError):
            registry.register_reasoning_contract(route["routeRef"], {**contract, field: value})
    registry.register_reasoning_contract(route["routeRef"], {**contract, "expiresAt": "2020-01-01T00:00:00Z"})
    assert registry.snapshot()["routes"][0]["reasoning"]["intents"] == ["default"]


def claude_frames(content="complete", tool=False):
    blocks = [
        {"type": "thinking", "thinking": "", "signature": ""},
        {"type": "redacted_thinking", "data": "opaque-redacted"},
        {"type": "text", "text": content},
    ]
    if tool:
        blocks.append({"type": "tool_use", "id": "call_fixture", "name": "list_files", "input": {}})
    frames = [{"type": "message_start", "message": {"usage": {"input_tokens": 7, "output_tokens": 0}}}]
    for i, block in enumerate(blocks):
        frames.append({"type": "content_block_start", "index": i, "content_block": block})
        if i == 0:
            frames += [{"type": "content_block_delta", "index": i, "delta": {"type": "thinking_delta", "thinking": "private thinking"}},
                       {"type": "content_block_delta", "index": i, "delta": {"type": "signature_delta", "signature": "sig-"}},
                       {"type": "content_block_delta", "index": i, "delta": {"type": "signature_delta", "signature": "opaque"}}]
        if block["type"] == "tool_use":
            frames += [{"type": "content_block_delta", "index": i, "delta": {"type": "input_json_delta", "partial_json": '{"path":'}},
                       {"type": "content_block_delta", "index": i, "delta": {"type": "input_json_delta", "partial_json": '"."}'}}]
        frames.append({"type": "content_block_stop", "index": i})
    frames += [{"type": "message_delta", "delta": {"stop_reason": "tool_use" if tool else "end_turn"}, "usage": {"output_tokens": 9}},
               {"type": "message_stop"}]
    return frames


def deep_frames(content="complete", tool=False):
    delta = {"reasoning_content": "private thinking", "content": content}
    if tool:
        delta["tool_calls"] = [{"index": 0, "id": "call_fixture", "type": "function",
                                "function": {"name": "list_files", "arguments": '{"path":"."}'}}]
    return [{"choices": [{"delta": delta, "finish_reason": "tool_calls" if tool else "stop"}]}, "[DONE]"]


@pytest.fixture
def upstream():
    class Handler(BaseHTTPRequestHandler):
        scripts, calls = [], []
        protocol_errors = []
        def log_message(self, *_):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.calls.append((self.path, body))
            if str(body.get("model", "")).startswith("deepseek") and body.get("tools"):
                missing = [index for index, message in enumerate(body.get("messages", []))
                           if message.get("role") == "assistant" and not isinstance(message.get("reasoning_content"), str)]
                if missing:
                    self.protocol_errors.append(missing)
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error":{"message":"missing reasoning_content in assistant history"}}')
                    return
            script = self.scripts.pop(0) if self.scripts else []
            if isinstance(script, int):
                self.send_response(script)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for frame in script:
                data = frame if isinstance(frame, str) else json.dumps(frame)
                self.wfile.write(("data: " + data + "\n\n").encode())
                self.wfile.flush()
    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield Handler, f"http://127.0.0.1:{http.server_port}"
    finally:
        http.shutdown()
        http.server_close()
        thread.join(3)
        assert not thread.is_alive()


def create_run(runtime, upstream, model, intent="high", messages=None, session="protocol-session"):
    fixture, harness = runtime
    handler, url = upstream
    server = harness.server_mod
    registry = ModelRouteRegistry(fixture.data_dir / "protocol-routes.json")
    route, contract = register(registry, url, model)
    _, _, selection = compile_model(model, intent, url, route["routeRef"], contract)
    with mock.patch.object(server, "_model_route_registry", registry):
        run = server._create_agent_run(session, {"model": model, "max_tokens": 8192,
            "messages": messages or [{"role": "user", "content": "list then finish"}]}, url, ["synthetic-only"],
            ["list_files"], cwd=str(fixture.data_dir), start_worker=False, reasoning_selection=selection,
            route_ref=route["routeRef"], catalog_revision=registry.snapshot()["catalogRevision"])
    return run


@pytest.mark.parametrize("model", ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-vision-exp", "claude-opus-4-6", "claude-opus-4-7", "claude-sonnet-4-5"])
def test_http_tool_replay_durable_and_next_user(runtime, upstream, model):
    fixture, harness = runtime
    server = harness.server_mod
    handler, _ = upstream
    frames = deep_frames if model.startswith("deepseek") else claude_frames
    handler.scripts = [frames("checking", True), frames("done"), frames("next done")]
    run = create_run(runtime, upstream, model)
    server._start_agent_worker(run)
    fixture._wait_terminal(run)
    fixture._wait_worker_idle(run)
    assert run["status"] == "completed", (run["error"], run.get("error_code"))
    assert len(handler.calls) == 2
    wire = handler.calls[1][1]
    assert handler.calls[0][0] == ("/v1/chat/completions" if model.startswith("deepseek") else "/v1/messages")
    if model.startswith("deepseek"):
        assert next(m for m in wire["messages"] if m["role"] == "assistant")["reasoning_content"] == "private thinking"
    else:
        blocks = next(m for m in wire["messages"] if m["role"] == "assistant")["content"]
        assert blocks[0] == {"type": "thinking", "thinking": "private thinking", "signature": "sig-opaque"}
        assert blocks[1] == {"type": "redacted_thinking", "data": "opaque-redacted"}
        assert any(b["type"] == "tool_result" for m in wire["messages"] for b in m["content"])
    record = server._agent_run_record(run)
    assert len(record["protocolReplay"]["entries"]) == 2
    public = json.dumps(server._agent_snapshot(run))
    assert "sig-opaque" not in public and "opaque-redacted" not in public and "private thinking" not in public
    if not model.startswith("deepseek"):
        model_run = server._get_model_runtime_run(run["rounds"][0]["runtimeRunId"])
        live = server._runtime_snapshot(model_run)
        assert live["result"]["reasoning"] == "private thinking"
        assert "private thinking" in json.dumps(live["events"])
        assert "sig-opaque" not in json.dumps(live) and "opaque-redacted" not in json.dumps(live)
    restored = server._agent_run_from_record(record)
    assert restored["protocol_replay"] == run["protocol_replay"]
    messages = copy.deepcopy(run["messages"]) + [{"role": "user", "content": "continue"}]
    second = create_run(runtime, upstream, model, messages=messages)
    server._start_agent_worker(second)
    fixture._wait_terminal(second)
    fixture._wait_worker_idle(second)
    assert second["status"] == "completed", second["error"]
    assert len(handler.calls) == 3
    final_wire = json.dumps(handler.calls[2][1])
    assert final_wire.count("private thinking") == 2
    assert len(second["tool_executions"]) == 0
    assert not handler.protocol_errors


@pytest.mark.parametrize("model", ["deepseek-v4-pro", "claude-opus-4-6"])
@pytest.mark.parametrize("failure", ["truncate", "400", "missing"])
def test_incomplete_or_rejected_response_never_executes_tool(runtime, upstream, model, failure):
    fixture, harness = runtime
    server = harness.server_mod
    frames = deep_frames("check", True) if model.startswith("deepseek") else claude_frames("check", True)
    if failure == "400":
        frames = 400
    elif failure == "truncate":
        frames = frames[:-1]
    elif model.startswith("deepseek"):
        frames[0]["choices"][0]["delta"].pop("reasoning_content")
    else:
        frames = [f for f in frames if f.get("delta", {}).get("type") != "signature_delta"]
    upstream[0].scripts = [frames]
    run = create_run(runtime, upstream, model)
    server._start_agent_worker(run)
    fixture._wait_status(run, "waiting_recovery" if failure == "truncate" else "failed")
    fixture._wait_worker_idle(run)
    assert len(upstream[0].calls) == 1
    assert not run["tool_executions"] and not run["pending_tool_calls"]


def test_old_binary_guard_and_missing_replay_rejected(runtime, upstream):
    _, harness = runtime
    server = harness.server_mod
    run = create_run(runtime, upstream, "claude-opus-4-6")
    record = server._agent_run_record(run)
    raw = subprocess.run(["git", "show", "82c7358:code_runtime/reasoning_capabilities.py"], cwd=server.APP_DIR,
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    ns = {}
    exec(compile(raw, "old-capabilities", "exec"), ns)
    with pytest.raises(ValueError):
        ns["restore_snapshot"](record["reasoningSnapshot"], model_id=run["request"]["model"], route_ref=run["route_ref"])
    record.pop("protocolReplay")
    with pytest.raises(rc.ReasoningError):
        server._agent_run_from_record(record)


@pytest.mark.parametrize("model", ["deepseek-v4-pro", "claude-opus-4-6"])
def test_restart_after_tool_does_not_execute_it_again(runtime, upstream, model):
    fixture, harness = runtime
    server = harness.server_mod
    frames = deep_frames if model.startswith("deepseek") else claude_frames
    upstream[0].scripts = [frames("checking", True), frames("partial")[:-1], frames("recovered")]
    run = create_run(runtime, upstream, model)
    server._start_agent_worker(run)
    fixture._wait_status(run, "waiting_recovery")
    fixture._wait_worker_idle(run)
    record = server._agent_run_record(run)
    assert record["modelCheckpoint"]["protocolReplayVersion"] == 1
    assert len(run["tool_executions"]) == 1
    original = copy.deepcopy(run["tool_executions"])
    restored = server._agent_run_from_record(record)
    with pytest.raises(rc.ReasoningError, match="target_mismatch"):
        server._resume_agent_run(restored, ["synthetic-only"], "http://127.0.0.1:1", route_ref=run["route_ref"])
    server._resume_agent_run(restored, ["synthetic-only"], upstream[1], route_ref=run["route_ref"])
    fixture._wait_terminal(restored)
    fixture._wait_worker_idle(restored)
    assert restored["status"] == "completed", restored["error"]
    assert restored["tool_executions"] == original
    assert len(upstream[0].calls) == 3
    assert "partial" in json.dumps(upstream[0].calls[2][1])


def test_storage_failure_prevents_tool_execution(runtime, upstream):
    fixture, harness = runtime
    server = harness.server_mod
    upstream[0].scripts = [deep_frames("checking", True)]
    run = create_run(runtime, upstream, "deepseek-v4-pro")
    persist = server._persist_agent_run
    failures = []
    def fail_before_tools(value):
        if value.get("protocol_replay", {}).get("entries") and not failures:
            failures.append(True)
            raise OSError("synthetic persistence failure")
        return persist(value)
    with mock.patch.object(server, "_persist_agent_run", side_effect=fail_before_tools):
        server._start_agent_worker(run)
        fixture._wait_terminal(run)
        fixture._wait_worker_idle(run)
    assert failures and run["status"] == "failed"
    assert not run["tool_executions"]
    assert len(upstream[0].calls) == 1


def test_foreign_prefix_model_and_session_never_replay_native_data(runtime, upstream):
    fixture, harness = runtime
    server = harness.server_mod
    upstream[0].scripts = [claude_frames("done")]
    run = create_run(runtime, upstream, "claude-opus-4-6")
    server._start_agent_worker(run)
    fixture._wait_terminal(run)
    fixture._wait_worker_idle(run)
    for model, session, system in [("claude-opus-4-7", "protocol-session", ""),
                                    ("claude-opus-4-6", "foreign-session", ""),
                                    ("claude-opus-4-6", "protocol-session", "changed prefix")]:
        messages = copy.deepcopy(run["messages"]) + [{"role": "user", "content": "continue"}]
        if system:
            messages.insert(0, {"role": "system", "content": system})
        follow = create_run(runtime, upstream, model, messages=messages, session=session)
        payload, _ = server._agent_model_payload(follow)
        assert "signature" not in json.dumps(pr.messages_request(payload))
        assert "private thinking" not in json.dumps(payload)
        assert "done" in json.dumps(payload)


def test_child_and_goal_inherit_configuration_but_start_new_protocol(runtime, upstream):
    _, harness = runtime
    server = harness.server_mod
    run = create_run(runtime, upstream, "claude-opus-4-6")
    with mock.patch.object(rc, "compile_request", side_effect=AssertionError("recompile")), mock.patch.object(server, "_start_agent_worker"):
        child, _ = server._ensure_agent_delegation_child(run, {"id": "child-fixture", "arguments": {"prompt": "inspect"}}, {})
    assert child["reasoning_snapshot"] == run["reasoning_snapshot"]
    assert child["protocol_replay"] == pr.empty(run["reasoning_snapshot"])
    assert child["request"]["output_config"] == {"effort": "high"}
    with mock.patch.object(server, "_agent_goal_continuation_state", return_value={"goal": {"goalId": "synthetic-goal"}, "revision": 1}), \
         mock.patch.object(server, "_start_agent_worker"), \
         mock.patch.object(rc, "compile_request", side_effect=AssertionError("recompile")):
        assert server._handoff_agent_goal_run(run, reason="soft_round_limit")
    successor = server._get_agent_run(run["result"]["continuation"]["agentRunId"])
    assert successor["reasoning_snapshot"] == run["reasoning_snapshot"]
    assert successor["protocol_replay"] == pr.empty(run["reasoning_snapshot"])


def test_history_mutation_invalidates_all_dependent_signatures(runtime, upstream):
    fixture, harness = runtime
    server = harness.server_mod
    upstream[0].scripts = [claude_frames("checking", True), claude_frames("done")]
    run = create_run(runtime, upstream, "claude-opus-4-6")
    server._start_agent_worker(run)
    fixture._wait_terminal(run)
    fixture._wait_worker_idle(run)
    messages = copy.deepcopy(run["messages"])
    messages[0]["content"] = "modified history"
    changed = create_run(runtime, upstream, "claude-opus-4-6", messages=messages + [{"role": "user", "content": "next"}])
    payload, _ = server._agent_model_payload(changed)
    assert "signature" not in json.dumps(payload)
    assert "private thinking" not in json.dumps(payload)
    assert all("tool_calls" not in m and m["role"] != "tool" for m in payload["messages"])


def test_stream_empty_tool_input_and_signed_redacted_blocks():
    frames = claude_frames("tool", True)
    frames = [f for f in frames if f.get("delta", {}).get("type") != "input_json_delta"]
    response = pr.Response("claude")
    chunks = [response.feed(json.dumps(frame)) for frame in frames]
    message = {"role": "assistant", "content": "tool", "tool_calls": [{"id": "call_fixture", "type": "function", "function": {"name": "list_files", "arguments": "{}"}}]}
    native = response.complete(message)
    assert native[-1]["input"] == {}
    assert native[0]["signature"] == "sig-opaque"
    assert "opaque" not in "".join(chunks)


def test_vision_and_tool_result_native_projection():
    image = "data:image/png;base64,aGVsbG8="
    wire = pr.messages_request({"model": "claude-opus-4-6", "max_tokens": 8192, "messages": [
        {"role": "user", "content": [{"type": "text", "text": "look"}, {"type": "image_url", "image_url": {"url": image}}]},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c", "function": {"name": "inspect", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c", "content": "found"}]})
    assert wire["messages"][0]["content"][1]["source"] == {"type": "base64", "media_type": "image/png", "data": "aGVsbG8="}
    assert wire["messages"][2]["content"] == [{"type": "tool_result", "tool_use_id": "c", "content": "found"}]


@pytest.mark.parametrize("version", [6, 7])
def test_v3_replay_coexists_with_immutable_skill_records(loading_env, version):
    import server
    run = make_run(loading_env)
    wire, snapshot, _ = compile_model("claude-opus-4-6", "high", route=run["route_ref"])
    run["request"] = wire
    run["reasoning_snapshot"] = snapshot
    run["protocol_replay"] = pr.empty(snapshot)
    record = server._agent_run_record(run)
    record["version"] = version
    if version == 6:
        record.pop("skillLoading")
    restored = server._agent_run_from_record(record, immutable_skill_reader=loading_env[-1])
    assert restored["protocol_replay"] == run["protocol_replay"]
    assert restored["reasoning_snapshot"] == snapshot


def test_creation_keeps_full_dependency_gate_under_real_contention(runtime):
    fixture, harness = runtime
    server = harness.server_mod
    gate = server.skill_dependency_operation.GATE
    attempts = {name: threading.Event() for name in ("admit-a", "admit-b")}
    entered, results, failures = [], [], []
    original_options = server._agent_request_options
    class ObservedGate:
        def __enter__(self):
            event = attempts.get(threading.current_thread().name)
            if event:
                event.set()
            gate.acquire()
            return self
        def __exit__(self, *_):
            gate.release()
    def options(payload):
        entered.append(threading.current_thread().name)
        return original_options(payload)
    def admit():
        try:
            results.append(server._create_agent_run("", {"model": "test-model", "messages": [{"role": "user", "content": "fixture"}]},
                                                    fixture.base_url, ["synthetic-only"], [], start_worker=False))
        except BaseException as exc:
            failures.append(exc)
    threads = [threading.Thread(target=admit, name=name) for name in attempts]
    with mock.patch.object(server.skill_dependency_operation, "GATE", ObservedGate()), \
         mock.patch.object(server, "_agent_request_options", side_effect=options):
        try:
            with gate:
                for thread in threads:
                    thread.start()
                for event in attempts.values():
                    assert event.wait(3), "creation did not contend on the real dependency gate"
                assert entered == [], "creation reached admission before holding the dependency gate"
            for thread in threads:
                thread.join(5)
            assert all(not thread.is_alive() for thread in threads)
            assert not failures and len(results) == 2
            assert sorted(entered) == ["admit-a", "admit-b"]
            assert results[0]["id"] != results[1]["id"]
        finally:
            for thread in threads:
                if thread.ident is not None:
                    thread.join(5)


@pytest.mark.parametrize("model", [name for name, profile in rc.MODELS.items() if profile.get("replay")])
def test_v2_never_accepts_a_downgraded_native_replay_profile(model):
    _, snapshot, _ = compile_model(model, "high")
    snapshot["schemaVersion"] = 2
    snapshot.pop("transportIdentity")
    with pytest.raises(rc.ReasoningError, match="snapshot_invalid"):
        rc.restore_snapshot(snapshot, model_id=model, route_ref="mr1_fixture")


def test_record_downgrade_cannot_remove_replay_guard(runtime, upstream):
    _, harness = runtime
    server = harness.server_mod
    run = create_run(runtime, upstream, "deepseek-v4-pro")
    record = server._agent_run_record(run)
    record["reasoningSnapshot"]["schemaVersion"] = 2
    record["reasoningSnapshot"].pop("transportIdentity")
    record.pop("protocolReplay")
    with pytest.raises(rc.ReasoningError, match="snapshot_invalid"):
        server._agent_run_from_record(record)


def test_strict_upstream_really_rejects_missing_assistant_reasoning(upstream):
    from urllib import request, error
    body = {"model": "deepseek-v4-pro", "tools": [{"type": "function", "function": {"name": "list_files"}}],
            "messages": [{"role": "assistant", "content": "legacy response"}]}
    with pytest.raises(error.HTTPError) as rejected:
        request.urlopen(request.Request(upstream[1] + "/v1/chat/completions", data=json.dumps(body).encode(),
                                        headers={"Content-Type": "application/json"}), timeout=3)
    assert rejected.value.code == 400
    rejected.value.close()
    assert upstream[0].protocol_errors == [[0]]


@pytest.mark.parametrize("model", ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-vision-exp"])
@pytest.mark.parametrize("history_kind", ["legacy", "cross_model", "changed_prefix", "compacted"])
def test_strict_deepseek_history_handoff_completes_tools(runtime, upstream, model, history_kind):
    fixture, harness = runtime
    server = harness.server_mod
    handler, _ = upstream
    if history_kind in {"cross_model", "changed_prefix"}:
        source_model = "claude-opus-4-6" if history_kind == "cross_model" else model
        handler.scripts = [claude_frames("prior answer") if history_kind == "cross_model" else deep_frames("prior answer")]
        source = create_run(runtime, upstream, source_model)
        server._start_agent_worker(source)
        fixture._wait_terminal(source)
        fixture._wait_worker_idle(source)
        assert source["status"] == "completed", source["error"]
        messages = copy.deepcopy(source["messages"]) + [{"role": "user", "content": "continue"}]
        if history_kind == "changed_prefix":
            messages.insert(0, {"role": "system", "content": "new system prefix"})
    else:
        messages = [{"role": "user", "content": "older request " * 1000},
                    {"role": "assistant", "content": "prior answer"},
                    {"role": "user", "content": "continue"}]
        if history_kind == "compacted":
            messages.extend([
                {"role": "assistant", "content": "prior tool work", "tool_calls": [{"id": "old_call", "type": "function", "function": {"name": "list_files", "arguments": '{"path":"."}'}}]},
                {"role": "tool", "tool_call_id": "old_call", "content": "old files result"},
            ])
    run = create_run(runtime, upstream, model, messages=messages)
    if history_kind == "compacted":
        handler.scripts = [deep_frames("prior answer summarized")]
        before = server._agent_estimate_request_tokens(server._agent_model_payload(run)[0])
        compacted = server._run_agent_auto_compaction(run, "threshold", before)
        assert compacted["status"] == "completed", compacted
        assert any(m.get("tool_calls") for m in run["messages"]), "fixture must retain the old assistant tool tail"
    before_calls = len(handler.calls)
    handler.scripts = [deep_frames("checking", True), deep_frames("done")]
    server._start_agent_worker(run)
    fixture._wait_terminal(run)
    fixture._wait_worker_idle(run)
    assert run["status"] == "completed", (run["error"], run["error_code"], handler.protocol_errors)
    assert len(handler.calls) - before_calls == 2
    assert not handler.protocol_errors
    first, followup = [body for _, body in handler.calls[-2:]]
    assert first["tools"] and followup["tools"]
    assert all(m["role"] != "assistant" for m in first["messages"])
    assistants = [m for m in followup["messages"] if m["role"] == "assistant"]
    assert len(assistants) == 1 and assistants[0]["reasoning_content"] == "private thinking"
    assert "prior" in json.dumps(first["messages"])
    assert len(run["tool_executions"]) == 1 and "call_fixture" in run["tool_executions"]
