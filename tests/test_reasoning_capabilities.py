"""Offline contracts for exact reasoning compilation and frozen run recovery."""
import copy
import ast
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest

from code_runtime import reasoning_capabilities as rc
from code_runtime.model_route_registry import ModelRouteRegistry
from tests.test_skill_model_loading import loading_env, make_run


def selection(model="gpt-5.5", intent="high", route_ref="mr1_fixture", base_url="https://api.openai.com"):
    cap = rc.projection(model, route_ref, base_url)
    return {"schemaVersion": 2, "intent": intent, "modelId": model,
            "routeRef": route_ref, "capabilityRevision": cap["capabilityRevision"]}


@pytest.mark.parametrize("model", ["gpt-5.4", "gpt-5.5", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"])
@pytest.mark.parametrize("intent", rc.INTENTS)
def test_exact_native_wire(model, intent):
    payload = {"model": model, "temperature": 0.2, "max_tokens": 8192,
               "seed": 42, "messages": [{"role": "user", "content": "fixture"}]}
    original = copy.deepcopy(payload)
    result, snapshot = rc.compile_request(payload, selection(model, intent),
        model_id=model, route_ref="mr1_fixture", base_url="https://api.openai.com")
    assert result.get("reasoning_effort") == (None if intent == "default" else intent)
    assert result["max_completion_tokens"] == 8192 and "max_tokens" not in result
    assert ("temperature" in result) == (intent == "default" or model != "gpt-5.4")
    assert result["seed"] == 42 and payload == original
    assert "reasoningSelection" not in result and "reasoningSnapshot" not in result
    assert snapshot["routeVerified"] is False


@pytest.mark.parametrize("url", ["https://proxy.invalid", "http://api.openai.com", "https://api.openai.com.evil.invalid",
    "https://api.openai.com/other", "https://user@api.openai.com", "https://api.openai.com?x=1", "https://api.openai.com:444"])
def test_unknown_transport_never_inherits_model_capability(url):
    cap = rc.projection("gpt-5.5", "mr1_fixture", url)
    assert cap["intents"] == ["default"] and cap["candidate"]
    with pytest.raises(rc.ReasoningError):
        rc.compile_request({"model": "gpt-5.5"}, selection(base_url=url),
            model_id="gpt-5.5", route_ref="mr1_fixture", base_url=url)


@pytest.mark.parametrize("model", ["alias-gpt-5.5", "gpt-5.5-high", "claude-opus-4-6", "o3-unknown", "o4-mini-unknown"])
def test_unconfirmed_models_default_only(model):
    cap = rc.projection(model, "mr1_fixture", "https://api.openai.com")
    assert cap["intents"] == ["default"]
    wire, _ = rc.compile_request({"model": model, "temperature": 0.2}, selection(model, "default"),
        model_id=model, route_ref="mr1_fixture", base_url="https://api.openai.com")
    assert wire == {"model": model, "temperature": 0.2}


def test_astra_protocol_and_stale_wrong_target_and_conflict():
    assert rc.projection("gpt-6-astra")["intents"] == []
    for changed in [{"schemaVersion": 3}, {"intent": "off"}, {"routeRef": "mr1_other"},
                    {"modelId": "gpt-5.4"}, {"capabilityRevision": "stale"}, {"profileId": "trust-me"}]:
        with pytest.raises(rc.ReasoningError):
            rc.compile_request({"model": "gpt-5.5"}, {**selection(), **changed},
                model_id="gpt-5.5", route_ref="mr1_fixture", base_url="https://api.openai.com")
    for field in rc.MANAGED_FIELDS:
        with pytest.raises(rc.ReasoningError, match="conflict"):
            rc.compile_request({"model": "gpt-5.5", field: "legacy"}, selection(intent="default"),
                model_id="gpt-5.5", route_ref="mr1_fixture", base_url="https://api.openai.com")


def test_registry_projection_changes_with_route_binding_not_name(tmp_path):
    registry = ModelRouteRegistry(tmp_path / "routes.json")
    base = {"connectionId": "manual_synthetic", "source": "manual", "key": "fixture-only", "baseUrl": "https://proxy.invalid"}
    first = registry.refresh([base], lambda _: ["gpt-5.5"])["routes"][0]
    second = registry.refresh([{**base, "baseUrl": "https://api.openai.com"}], lambda _: ["gpt-5.5"])["routes"][0]
    assert first["routeRef"] == second["routeRef"]
    assert first["reasoning"]["intents"] == list(rc.INTENTS)
    assert first["reasoning"]["routeVerified"] is False
    assert second["reasoning"]["intents"] == list(rc.INTENTS)
    assert first["reasoning"]["capabilityRevision"] != second["reasoning"]["capabilityRevision"]
    persisted = json.loads((tmp_path / "routes.json").read_text())
    assert "reasoning" not in persisted["routes"][0]
    restarted = ModelRouteRegistry(tmp_path / "routes.json")
    assert restarted.snapshot()["routes"][0]["reasoning"]["intents"] == ["default"]


def test_feature_disable_blocks_new_admission_but_not_frozen_snapshot(monkeypatch):
    _, snapshot = rc.compile_request({"model": "gpt-5.5"}, selection(),
        model_id="gpt-5.5", route_ref="mr1_fixture", base_url="https://api.openai.com")
    monkeypatch.setenv("CODE_REASONING_V2_ENABLED", "0")
    assert rc.projection("gpt-5.5")["intents"] == []
    assert rc.restore_snapshot(snapshot, model_id="gpt-5.5", route_ref="mr1_fixture") == snapshot


@pytest.fixture
def runtime():
    from tests import test_agent_runtime as harness
    fixture = harness.TestDurableAgentRuntime("runTest")
    fixture.setUpClass()
    fixture.setUp()
    stack = []
    try:
        for name in ("_SKILL_IMMUTABLE_ADMISSION_ENABLED", "_SKILL_MODEL_LOADING_ENABLED", "_SKILL_ACTIVATION_ENABLED"):
            patch = mock.patch.object(harness.server_mod, name, False)
            patch.start(); stack.append(patch)
        yield fixture, harness
    finally:
        fixture.tearDown()
        for patch in reversed(stack): patch.stop()
        fixture.tearDownClass()


def create(runtime, intent="high", client_id="reasoning-fixture"):
    fixture, harness = runtime
    server = harness.server_mod
    registry = ModelRouteRegistry(fixture.data_dir / "reasoning-routes.json")
    native = rc.transport_profile
    # This is an explicit synthetic transport fixture, never a production route declaration.
    transport = mock.patch.object(rc, "transport_profile", side_effect=lambda url: "openai-chat-native-v1" if url == fixture.base_url else native(url))
    transport.start(); fixture.addCleanup(transport.stop)
    cap = registry.refresh([{"connectionId": "manual_synthetic", "source": "manual", "key": "fixture-only", "baseUrl": fixture.base_url}], lambda _: ["gpt-5.5"])
    route = cap["routes"][0]
    metadata = selection(intent=intent, route_ref=route["routeRef"], base_url=fixture.base_url)
    with mock.patch.object(server, "_model_route_registry", registry):
        run = server._create_agent_run("", {"model": "gpt-5.5", "temperature": 0.2, "max_tokens": 4096,
            "messages": [{"role": "user", "content": "fixture final response"}]}, fixture.base_url,
            ["fixture-only"], [], start_worker=False, client_request_id=client_id,
            route_ref=route["routeRef"], catalog_revision=cap["catalogRevision"], reasoning_selection=metadata)
    return run, metadata, registry, transport


def test_admission_freezes_fields_and_idempotent_retry_does_not_recompile(runtime):
    fixture, harness = runtime; server = harness.server_mod
    run, metadata, registry, transport = create(runtime)
    try:
        record = server._agent_run_record(run)
        assert record["reasoningSnapshot"]["intent"] == "high"
        assert record["request"]["reasoning_effort"] == "high"
        with mock.patch.object(rc, "compile_request", side_effect=AssertionError("must not recompile")):
            restored = server._agent_run_from_record(record)
            assert restored["request"] == run["request"]
            duplicate = server._create_agent_run("", {"model": "gpt-5.5", "messages": [{"role": "user", "content": "duplicate"}]},
                fixture.base_url, ["fixture-only"], [], start_worker=False,
                client_request_id="reasoning-fixture", reasoning_selection={**metadata, "intent": "low"})
            assert duplicate is run
        assert harness._AgentUpstream.calls == 0
    finally: transport.stop()


@pytest.mark.parametrize("failure", [{"http_error": 400, "message": "reasoning_effort unsupported"},
    {"partial_then_disconnect": True, "content": "partial fixture"}])
def test_runtime_parameter_failure_and_started_stream_never_replay(runtime, failure):
    fixture, harness = runtime; server = harness.server_mod
    run, _, _, transport = create(runtime)
    try:
        harness._AgentUpstream.scripted_rounds = [failure]
        server._start_agent_worker(run)
        if failure.get("partial_then_disconnect"):
            fixture._wait_status(run, "waiting_recovery")
        else:
            fixture._wait_terminal(run)
        fixture._wait_worker_idle(run)
        assert harness._AgentUpstream.calls == 1
        wire = harness._AgentUpstream.payloads[0]
        assert wire["reasoning_effort"] == "high" and "reasoningSelection" not in wire
        assert run["request"]["reasoning_effort"] == "high"
        assert not run.get("pending_tool_calls")
    finally: transport.stop()


def test_old_record_versions_and_previous_reader_preserve_compiled_request(runtime):
    fixture, harness = runtime; server = harness.server_mod
    run, _, _, transport = create(runtime)
    try:
        record = server._agent_run_record(run)
        previous = subprocess.run(["git", "show", "54686d3:server.py"],
            cwd=server.APP_DIR, capture_output=True, text=True, encoding="utf-8", check=True).stdout
        function = next(n for n in ast.parse(previous).body
            if isinstance(n, ast.FunctionDef) and n.name == "_agent_run_from_record")
        namespace = dict(vars(server))
        exec(compile(ast.Module(body=[function], type_ignores=[]), "baseline-reader", "exec"), namespace)
        old_reader = namespace["_agent_run_from_record"]
        for version in range(1, 6):
            fixture_record = copy.deepcopy(record)
            fixture_record["version"] = version
            if version < 5: fixture_record.pop("skillLifecycle", None)
            restored = server._agent_run_from_record(fixture_record)
            assert restored["request"] == run["request"]
            assert restored["reasoning_snapshot"]["intent"] == "high"
            assert old_reader(fixture_record)["request"] == run["request"]
            fixture_record.pop("reasoningSnapshot")
            assert server._agent_run_from_record(fixture_record)["reasoning_snapshot"] is None
    finally: transport.stop()


def test_delegated_child_inherits_frozen_request_without_catalog_recompile(runtime):
    fixture, harness = runtime; server = harness.server_mod
    run, _, _, transport = create(runtime)
    try:
        with mock.patch.object(rc, "compile_request", side_effect=AssertionError("recompiled")), \
             mock.patch.object(server, "_start_agent_worker"):
            child, _ = server._ensure_agent_delegation_child(run,
                {"id": "reasoning-child", "arguments": {"prompt": "synthetic task"}}, {})
        assert child["request"]["reasoning_effort"] == "high"
        assert child["reasoning_snapshot"] == run["reasoning_snapshot"]
        assert child["reasoning_snapshot"] is not run["reasoning_snapshot"]
        assert harness._AgentUpstream.calls == 0
    finally: transport.stop()


def test_concurrent_duplicate_admission_compiles_once(runtime):
    fixture, harness = runtime; server = harness.server_mod
    _, metadata, registry, transport = create(runtime)
    def admit(_):
        return server._create_agent_run("", {"model": "gpt-5.5", "messages": [{"role": "user", "content": "concurrent fixture"}]},
            fixture.base_url, ["fixture-only"], [], start_worker=False,
            client_request_id="concurrent-reasoning-fixture", route_ref=metadata["routeRef"],
            catalog_revision=registry.snapshot()["catalogRevision"], reasoning_selection=metadata)
    try:
        with mock.patch.object(server, "_model_route_registry", registry), \
             mock.patch.object(rc, "compile_request", wraps=rc.compile_request) as compiler, \
             ThreadPoolExecutor(max_workers=2) as workers:
            runs = list(workers.map(admit, range(2)))
        assert runs[0] is runs[1] and compiler.call_count == 1
        assert harness._AgentUpstream.calls == 0
    finally: transport.stop()


def test_goal_successor_inherits_frozen_reasoning(runtime):
    fixture, harness = runtime; server = harness.server_mod
    run, _, _, transport = create(runtime)
    try:
        with mock.patch.object(server, "_agent_goal_continuation_state", return_value={"goal": {"goalId": "synthetic-goal"}, "revision": 1}), \
             mock.patch.object(server, "_start_agent_worker"), \
             mock.patch.object(rc, "compile_request", side_effect=AssertionError("recompiled")):
            assert server._handoff_agent_goal_run(run, reason="soft_round_limit")
        child = server._get_agent_run(run["result"]["continuation"]["agentRunId"])
        assert child["reasoning_snapshot"] == run["reasoning_snapshot"]
        assert child["request"] == run["request"]
        assert harness._AgentUpstream.calls == 0
    finally: transport.stop()


def test_frozen_reasoning_recovery_does_not_repeat_completed_tool(runtime):
    fixture, harness = runtime; server = harness.server_mod
    original = server.write_json
    _, snapshot = rc.compile_request({"model": "gpt-5.5"}, selection(route_ref=""),
        model_id="gpt-5.5", route_ref="", base_url="https://api.openai.com")
    def write_record(path, record, *args, **kwargs):
        if isinstance(record, dict) and record.get("sessionId") == "restart-session":
            record["request"].update(model="gpt-5.5", reasoning_effort="high")
            record["routeRef"] = ""
            record["reasoningSnapshot"] = copy.deepcopy(snapshot)
        return original(path, record, *args, **kwargs)
    with mock.patch.object(server, "write_json", side_effect=write_record), \
         mock.patch.object(rc, "compile_request", side_effect=AssertionError("recompiled")):
        fixture.test_restart_recovery_reuses_completed_tool_execution()
    assert harness._AgentUpstream.payloads[0]["reasoning_effort"] == "high"


@pytest.mark.parametrize("version", [6, 7])
def test_immutable_record_versions_preserve_reasoning(loading_env, version):
    import server
    run = make_run(loading_env)
    wire, snapshot = rc.compile_request(run["request"],
        selection("deterministic-fixture", "default", "", run["base_url"]),
        model_id="deterministic-fixture", route_ref="", base_url=run["base_url"])
    run["request"] = wire
    run["reasoning_snapshot"] = snapshot
    record = server._agent_run_record(run)
    assert record["version"] == 7
    record["version"] = version
    if version == 6: record.pop("skillLoading")
    restored = server._agent_run_from_record(record, immutable_skill_reader=loading_env[-1])
    assert restored["request"] == wire
    assert restored["reasoning_snapshot"] == snapshot
    record.pop("reasoningSnapshot")
    assert server._agent_run_from_record(record, immutable_skill_reader=loading_env[-1])["reasoning_snapshot"] is None
