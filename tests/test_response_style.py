"""Offline reply-style transport/continuity evidence; import under isolated CODE_DATA_DIR."""
import copy
import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest
from code_runtime import reasoning_capabilities as rc, protocol_replay as pr
from tests.test_reasoning_capabilities import runtime
from tests.test_reasoning_protocol import upstream, create_run, deep_frames, claude_frames, compile_model


@pytest.fixture(scope="module")
def styles():
    script = """
const fs=require('fs'),vm=require('vm');const s={Code:{agent:{}}};s.window=s;vm.createContext(s);
vm.runInContext(fs.readFileSync('src/agent/system-prompt.js','utf8'),s);
const p=s.Code.agent.systemPrompt;
console.log(JSON.stringify(p.RESPONSE_DETAILS.flatMap(detail=>p.RESPONSE_TONES.map(tone=>p.createResponseStyleSnapshot({detail,tone})))));
"""
    return json.loads(subprocess.check_output(["node", "-e", script], cwd=Path(__file__).parents[1], text=True))


@pytest.mark.parametrize("model", list(rc.MODELS))
def test_nine_styles_leave_each_exact_model_sampling_and_tools_unchanged(styles, model):
    wire, snapshot, selection = compile_model(model, "high")
    for style in styles:
        payload = dict(model=model, max_tokens=8192, temperature=.2, top_p=.9,
                       messages=[{"role": "system", "content": style["instruction"]}, {"role": "user", "content": "fixture"}])
        changed, other = rc.compile_request(payload, selection, model_id=model, route_ref=selection["routeRef"],
            base_url={"openai":"https://api.openai.com", "deepseek":"https://api.deepseek.com", "anthropic":"https://api.anthropic.com"}[rc.MODELS[model]["provider"]])
        assert {k:v for k,v in changed.items() if k != "messages"} == wire
        assert other == snapshot
        assert changed["messages"] == payload["messages"]


@pytest.mark.parametrize("model", ["deepseek-v4-pro", "claude-opus-4-6", "claude-sonnet-4-5"])
@pytest.mark.parametrize("style_index", [0, 8])
def test_native_tool_round_restart_child_goal_and_changed_style_scope(styles, runtime, upstream, model, style_index):
    fixture, harness = runtime
    server = harness.server_mod
    handler, _ = upstream
    frames = deep_frames if model.startswith("deepseek") else claude_frames
    handler.scripts = [frames("checking", True), frames("done")]
    instruction = "Existing safety and engineering contract."
    if styles[style_index]["instruction"]:
        instruction += "\n\n" + styles[style_index]["instruction"]
    run = create_run(runtime, upstream, model, messages=[{"role":"system", "content":instruction}, {"role":"user", "content":"list then finish"}])
    server._start_agent_worker(run)
    fixture._wait_terminal(run); fixture._wait_worker_idle(run)
    assert run["status"] == "completed", run.get("error")
    assert len(handler.calls) == 2 and len(run["tool_executions"]) == 1
    for _, payload in handler.calls:
        text=json.dumps(payload, ensure_ascii=False)
        assert text.count("[Reply preferences]") == (1 if style_index else 0)
        assert "Existing safety and engineering contract." in text
    record=server._agent_run_record(run)
    with mock.patch.object(rc,"compile_request",side_effect=AssertionError("Recompiled frozen request")):
        restored=server._agent_run_from_record(record)
        assert restored["request"] == run["request"]
        payload,_=server._agent_model_payload(restored)
    assert json.dumps(payload).count("[Reply preferences]") == (1 if style_index else 0)
    assert server._agent_compaction_payload(run,{"compactedMessages":[]})["messages"][0]["content"].startswith("You are creating a context checkpoint")
    with mock.patch.object(server,"_start_agent_worker"), mock.patch.object(rc,"compile_request",side_effect=AssertionError("recompile")):
        child,_=server._ensure_agent_delegation_child(run,{"id":"style-child", "arguments":{"prompt":"inspect"}}, {})
        assert "[Reply preferences]" not in child["messages"][0]["content"]
        assert child["request"] == run["request"]
        with mock.patch.object(server,"_agent_goal_continuation_state",return_value={"goal":{"goalId":"style-goal"},"revision":1}):
            assert server._handoff_agent_goal_run(run,reason="soft_round_limit")
        successor=server._get_agent_run(run["result"]["continuation"]["agentRunId"])
        assert successor["messages"][0]["content"] == instruction
    changed=copy.deepcopy(restored["messages"])
    changed[0]["content"] += "\nA new task has a different reply preference."
    following=create_run(runtime,upstream,model,messages=changed)
    next_payload,_=server._agent_model_payload(following)
    wire=pr.messages_request(next_payload) if model.startswith("claude") else next_payload
    assert "private thinking" not in json.dumps(wire) and "sig-opaque" not in json.dumps(wire)
    assert not handler.protocol_errors
