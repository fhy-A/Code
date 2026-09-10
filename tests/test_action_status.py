"""Display metadata must not become execution identity or native replay edits.

Run only with CODE_DATA_DIR set to an isolated profile before importing server.
"""
import ast
import copy
import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest
import server as s
from tests.test_reasoning_capabilities import runtime
from tests.test_reasoning_protocol import upstream, create_run, deep_frames, claude_frames
from tests.test_skill_model_loading import loading_env, make_run as make_loading_run, call as loading_call


def normalize(name, args, run=None, call_id="call_fixture"):
    run = run if run is not None else {"id": "fixture", "tools": [s._agent_registry_tool_definition(name)]}
    return s._normalize_agent_tool_calls(run, [{"id": call_id, "function": {
        "name": name, "arguments": json.dumps(args, ensure_ascii=False),
    }}], 1)[0]


@pytest.mark.parametrize("name", [name for name in s.SERVER_TOOL_REGISTRY if name != "request_user_input"])
@pytest.mark.parametrize("value", ["Checking inputs", "Different purpose", "", None, {}, [1], 2, "a\nb", "x" * 81])
def test_display_never_changes_execution_contract(name, value):
    args = {"command": "Get-Location"} if name == "run_command" else {}
    plain = normalize(name, args)
    shown = normalize(name, {**args, "_actionStatus": value})
    for key in ["arguments", "fingerprint", "parseError", "validationErrors", "argumentAliases"]:
        assert shown[key] == plain[key], (name, key)
    assert s._agent_execution_arguments_text(shown) == s._agent_execution_arguments_text(plain)
    assert json.loads(shown["function"]["arguments"])["_actionStatus"] == value
    if name == "run_command":
        run = {"id": "fixture"}
        assert s._agent_command_authorization_request(run, plain)["authorizationId"] == s._agent_command_authorization_request(run, shown)["authorizationId"]
        assert normalize(name, {"command": "Get-Date", "_actionStatus": value})["fingerprint"] != plain["fingerprint"]


def test_old_frozen_schema_and_no_field_follow_baseline_exactly():
    source = subprocess.check_output(["git", "show", "9df515c:server.py"]).decode("utf-8")
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "_normalize_agent_tool_calls")
    namespace = dict(vars(s))
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<baseline>", "exec"), namespace)
    run = {"id": "old", "tools": [copy.deepcopy(s._SERVER_TOOL_DEFINITIONS["read_file"])]}
    calls = [{"id": "call_fixture", "function": {"name": "read_file", "arguments": json.dumps(args)}} for args in [
        {"path": "one"}, {"file_path": "alias"}, {"path": "one", "_actionStatus": "old unknown field"},
    ]]
    assert s._normalize_agent_tool_calls(run, calls, 1) == namespace["_normalize_agent_tool_calls"](run, calls, 1)
    assert "_actionStatus" not in s._agent_registry_tool_definition("request_user_input")["function"]["parameters"]["properties"]
    assert "_actionStatus" not in s._SERVER_TOOL_DEFINITIONS["read_file"]["function"]["parameters"]["properties"]


@pytest.mark.parametrize("model", ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-vision-exp", "claude-opus-4-6", "claude-opus-4-7", "claude-sonnet-4-5"])
@pytest.mark.parametrize("value", ["Checking files to locate the entry point", {"invalid": "presentation"}])
def test_actual_native_roundtrip_restore_and_next_user(runtime, upstream, model, value):
    fixture, _ = runtime
    handler, _ = upstream
    make_frames = deep_frames if model.startswith("deepseek") else claude_frames
    frames = make_frames("", True)
    args = {"path": ".", "_actionStatus": value}
    if model.startswith("deepseek"):
        frames[0]["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"] = json.dumps(args)
    else:
        parts = [frame for frame in frames if isinstance(frame, dict) and frame.get("delta", {}).get("type") == "input_json_delta"]
        parts[0]["delta"]["partial_json"] = json.dumps(args)
        parts[1]["delta"]["partial_json"] = ""
    handler.scripts = [frames, make_frames("done"), make_frames("next done")]
    run = create_run(runtime, upstream, model)
    original = s.execute_registered_tool
    seen = []
    def execute(name, payload, **kwargs):
        seen.append(copy.deepcopy(payload))
        return original(name, payload, **kwargs)
    with mock.patch.object(s, "execute_registered_tool", side_effect=execute):
        s._start_agent_worker(run)
        fixture._wait_terminal(run); fixture._wait_worker_idle(run)
    assert run["status"] == "completed", run.get("error")
    assert seen == [{"path": "."}]
    assert len(handler.calls) == 2
    record = s._agent_run_record(run)
    restored = s._agent_run_from_record(record)
    assert restored["protocol_replay"] == run["protocol_replay"]
    assert all("_actionStatus" not in execution["arguments"] for execution in restored["tool_executions"].values())
    for event in s._agent_snapshot(run)["events"]:
        if event["type"] in {"tool_started", "tool_completed"}:
            assert "_actionStatus" not in json.dumps(event["data"])
    wire = handler.calls[1][1]
    assistant = next(message for message in wire["messages"] if message["role"] == "assistant")
    replay_args = json.loads(assistant["tool_calls"][0]["function"]["arguments"]) if model.startswith("deepseek") else next(block["input"] for block in assistant["content"] if block["type"] == "tool_use")
    assert replay_args == args
    next_run = create_run(runtime, upstream, model, messages=copy.deepcopy(run["messages"]) + [{"role": "user", "content": "next"}])
    s._start_agent_worker(next_run)
    fixture._wait_terminal(next_run); fixture._wait_worker_idle(next_run)
    assert next_run["status"] == "completed", next_run.get("error")
    assert not next_run["tool_executions"] and len(handler.calls) == 3


def make_run(runtime, names, profile="bypass"):
    fixture, _ = runtime
    return s._create_agent_run("action-status-fixture", {"model": "test", "messages": [{"role": "user", "content": "inspect"}]},
        fixture.base_url, ["synthetic"], names, permission_profile=profile, cwd=str(fixture.data_dir), start_worker=False)


def test_command_execution_restore_reuse_cancel_and_real_argument_change(runtime):
    run = make_run(runtime, ["run_command"])
    def stage(args):
        call = normalize("run_command", args, run)
        run["pending_tool_calls"] = [call]; run["status"] = "tools"
        return call
    stage({"command": "synthetic command", "_actionStatus": "Inspecting the result"})
    with mock.patch.object(s, "execute_run_command_tool", return_value={"ok": True, "stdout": "fixture", "exitCode": 0}) as execute:
        assert s._execute_agent_pending_tools(run)
        assert execute.call_args.args[0] == {"command": "synthetic command"}
        stage({"command": "synthetic command", "_actionStatus": "Different label"})
        assert s._execute_agent_pending_tools(run)
        assert execute.call_count == 1
    stored = s._agent_run_record(run)
    restored = s._agent_run_from_record(stored)
    restored["pending_tool_calls"] = [normalize("run_command", {"command": "synthetic command", "_actionStatus": "Again"}, restored)]
    restored["status"] = "tools"
    with mock.patch.object(s, "execute_run_command_tool") as execute:
        assert s._execute_agent_pending_tools(restored)
        execute.assert_not_called()
    stage({"command": "changed command", "_actionStatus": "Again"})
    with pytest.raises(ValueError, match="reused with different arguments"):
        s._execute_agent_pending_tools(run)
    run["pending_tool_calls"] = [normalize("run_command", {"command": "queued", "_actionStatus": "Queued label"}, run, "queued")]
    with run["condition"]:
        s._close_agent_tools_for_cancel_locked(run)
    assert json.loads(run["tool_executions"]["queued"]["arguments"]) == {"command": "queued"}


def test_failed_count_and_authorization_ignore_display(runtime):
    run = make_run(runtime, ["run_command"], "accept")
    call = normalize("run_command", {"command": "echo fixture", "_actionStatus": {"invalid": True}}, run)
    run["pending_tool_calls"] = [call]; run["status"] = "tools"
    with mock.patch.object(s, "execute_run_command_tool") as execute:
        assert not s._execute_agent_pending_tools(run)
        execute.assert_not_called()
    assert run["status"] == "waiting_authorization"
    assert "_actionStatus" not in json.dumps(run["pending_authorization"])
    assert json.loads(run["tool_executions"][call["id"]]["arguments"]) == {"command": "echo fixture"}
    failure = {"ok": False, "error": "fixture failure"}
    run["tool_executions"] = {"prior": {"fingerprint": call["fingerprint"], "status": "completed", "result": failure,
        "failureSignature": s._agent_tool_failure_signature(failure)}}
    changed_label = normalize("run_command", {"command": "echo fixture", "_actionStatus": "New label"}, run)
    assert s._agent_identical_tool_failure_count(run, call["fingerprint"]) == s._agent_identical_tool_failure_count(run, changed_label["fingerprint"])


def test_common_guidance_is_once_request_only_and_absent_for_old_tools(runtime):
    run = make_run(runtime, ["read_file", "list_files", "run_command"])
    before = copy.deepcopy(run["messages"])
    for _ in range(2):
        payload, _ = s._agent_model_payload(run)
        assert sum(message.get("content", "").startswith("[Optional action status]\n") for message in payload["messages"]) == 1
        assert json.dumps(payload).count("Never add a call just to send") == 1
    assert run["messages"] == before
    run["tools"] = [copy.deepcopy(s._SERVER_TOOL_DEFINITIONS["read_file"])]
    old_payload, _ = s._agent_model_payload(run)
    assert not any(message.get("content", "").startswith("[Optional action status]\n") for message in old_payload["messages"])


def test_immutable_skill_load_and_execution_records_use_only_clean_parameters(loading_env):
    run = make_loading_run(loading_env)
    loaded = loading_call(run, "use_skill", {"name": "ledger", "role": "owner", "_actionStatus": {"bad": True}}, "load")
    assert loaded["result"]["bodyLoaded"] is True
    assert json.loads(loaded["arguments"]) == {"name": "ledger", "role": "owner"}
    read = loading_call(run, "read_file", {"path": "input.txt", "_actionStatus": "Checking input format"}, "read")
    assert read["result"]["ok"] is True
    assert "_actionStatus" not in json.dumps(read)
    restored = s._agent_run_from_record(s._agent_run_record(run), immutable_skill_reader=loading_env[-1])
    assert restored["skill_loading"] == run["skill_loading"]
    assert restored["tool_executions"] == run["tool_executions"]


def test_actual_image_asset_operation_uses_clean_arguments_and_duplicate_identity():
    from tests.test_image_agent_runtime import TestImageAgentRuntime
    fixture = TestImageAgentRuntime("runTest")
    fixture.setUp()
    try:
        run = fixture._run()
        args = {"prompt": "a small blue square", "count": 1}
        first = fixture._queue(run, arguments={**args, "_actionStatus": "Rendering the illustration"})
        plain = normalize("generate_image", args, run)
        assert first["fingerprint"] == plain["fingerprint"]
        assert s._agent_image_effective_fingerprint(first) == s._agent_image_effective_fingerprint(plain)
        assert s._execute_agent_pending_tools(run)
        record = run["tool_executions"][first["id"]]
        assert record["result"]["ok"] is True
        assert "_actionStatus" not in record["arguments"]
        before = copy.deepcopy(record)
        fixture._queue(run, arguments={**args, "_actionStatus": "Another rendering label"})
        assert s._execute_agent_pending_tools(run)
        assert run["tool_executions"][first["id"]] == before
    finally:
        fixture.tearDown()
