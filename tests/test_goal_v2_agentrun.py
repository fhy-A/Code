from __future__ import annotations

import io
import json
import threading
from pathlib import Path

import pytest
from PIL import Image

from code_runtime import image_runtime
import server as server_mod


SESSION_ID = "session-v2-agent-main"


@pytest.fixture()
def isolated_server(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(server_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(server_mod, "SESSIONS_DIR", sessions)
    with server_mod._agent_run_lock:
        before = dict(server_mod._agent_runs)
        server_mod._agent_runs.clear()
    yield tmp_path
    with server_mod._agent_run_lock:
        server_mod._agent_runs.clear()
        server_mod._agent_runs.update(before)


def _persist_session(session_id: str, messages: list[dict]) -> None:
    server_mod.write_json(server_mod.session_path(session_id), {
        "id": session_id,
        "title": "Goal v2 AgentRun test",
        "createdAt": server_mod.now_iso(),
        "updatedAt": server_mod.now_iso(),
        "messageCount": len(messages),
    })
    server_mod.write_jsonl(server_mod.messages_path(session_id), messages)


def _origin_message(client_request_id: str, message_id: str = "message-goal-origin") -> dict:
    return {
        "id": message_id,
        "role": "user",
        "content": "Implement a durable multi-stage feature with verification",
        "meta": {
            "goalOrigin": {
                "messageId": message_id,
                "clientRequestId": client_request_id,
            },
        },
    }


def _payload(content: str = "Implement a durable multi-stage feature") -> dict:
    return {
        "model": "fake-model",
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": content},
        ],
    }


def _create_run(
    client_request_id: str,
    *,
    session_id: str = SESSION_ID,
    permission_profile: str = "read",
    run_kind: str = "foreground",
    parent_run_id: str = "",
    agent_depth: int = 0,
    image_route=None,
):
    return server_mod._create_agent_run(
        session_id,
        _payload(),
        "http://127.0.0.1:1",
        [],
        ["list_files", "run_command", "write_file", "task", "generate_image"],
        8,
        permission_profile,
        parent_run_id=parent_run_id,
        agent_depth=agent_depth,
        start_worker=False,
        client_request_id=client_request_id,
        run_kind=run_kind,
        image_route=image_route,
    )


def _model_runtime_stub(run_id: str) -> dict:
    return {
        "id": run_id,
        "condition": threading.Condition(threading.RLock()),
        "context_failure_attribution": None,
    }


def _tool_names(run) -> set[str]:
    return {
        str((definition.get("function") or {}).get("name") or "")
        for definition in run.get("tools") or []
    }


def _call(run, name: str, arguments: dict, call_id: str) -> dict:
    normalized = server_mod._normalize_agent_tool_calls(run, [{
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }], len(run.get("rounds") or []) + 1)
    run["messages"].append({
        "role": "assistant",
        "content": "",
        "tool_calls": server_mod._agent_assistant_tool_calls(normalized),
    })
    run["pending_tool_calls"] = normalized
    run["status"] = "tools"
    assert server_mod._execute_agent_pending_tools(run) is True
    return run["tool_executions"][call_id]["result"]


def _plan() -> list[dict]:
    return [
        {
            "id": f"step-{index}",
            "description": f"Complete product stage {index}",
            "acceptanceCriteria": [{
                "id": f"criterion-{index}",
                "kind": "machine",
                "description": f"Stage {index} has deterministic evidence",
            }],
        }
        for index in range(1, 4)
    ]


def test_goal_revise_plan_uses_provider_portable_non_empty_object_schema():
    parameters = server_mod._SERVER_TOOL_DEFINITIONS["goal_revise_plan"]["function"]["parameters"]

    assert parameters["type"] == "object"
    assert parameters["minProperties"] == 1
    assert "anyOf" not in parameters


def _active_goal_run(
    client_request_id: str = "foreground-continuation-root",
    *,
    session_id: str = SESSION_ID,
    image_route=None,
):
    origin = _origin_message(client_request_id, f"origin-{client_request_id}")
    _persist_session(session_id, [origin])
    run = _create_run(
        client_request_id,
        session_id=session_id,
        permission_profile="bypass",
        image_route=image_route,
    )
    _call(run, "goal_create", {"objective": "Finish a long durable Goal"}, "continuation-create")
    _call(run, "goal_set_plan", {"steps": _plan()}, "continuation-plan")
    _call(run, "goal_start_step", {"stepId": "step-1"}, "continuation-start")
    run["status"] = "model"
    return run


def _advance_goal_to_acceptance(run) -> dict:
    _call(run, "goal_create", {"objective": "Complete a durable accepted Goal"}, "call-create")
    _call(run, "goal_set_plan", {"steps": _plan()}, "call-plan")
    for index in range(1, 3):
        _call(
            run,
            "goal_start_step",
            {"stepId": f"step-{index}"},
            f"call-start-{index}",
        )
        _call(
            run,
            "goal_complete_step",
            {
                "stepId": f"step-{index}",
                "evidence": [{
                    "criterionId": f"criterion-{index}",
                    "kind": "machine",
                    "summary": f"Stage {index} verification passed",
                }],
            },
            f"call-complete-{index}",
        )
    _call(run, "goal_start_step", {"stepId": "step-3"}, "call-start-3")
    runtime = server_mod.goal_v2_runtime()
    current = runtime.read(SESSION_ID).state
    completed = runtime.service.append(
        SESSION_ID,
        current.goal["goalId"],
        "step_completed",
        {
            "stepId": "step-3",
            "sourceRunId": run["id"],
            "evidence": [{
                "id": "legacy-evidence-3",
                "criterionId": "criterion-3",
                "kind": "machine",
                "summary": "Legacy stage 3 verification passed",
                "sourceRunId": run["id"],
                "sourceToolCallId": "legacy-complete-3",
                "recordedAt": server_mod.now_iso(),
            }],
        },
        expected_revision=current.revision,
        idempotency_key="legacy-step-complete-3",
        actor="foreground-agent",
    )
    return runtime.ready_for_acceptance(
        SESSION_ID,
        completed["goal"]["goalId"],
        summary="Legacy ready record",
        source_run_id=run["id"],
        expected_revision=completed["revision"],
        idempotency_key="legacy-ready",
    )


def test_foreground_identity_binding_adds_internal_goal_tools_for_all_profiles(isolated_server):
    goal_tools = set(server_mod._AGENT_GOAL_DEFAULT_TOOL_NAMES)
    for profile in ("read", "plan", "accept", "bypass"):
        request_id = f"foreground-{profile}"
        _persist_session(SESSION_ID, [_origin_message(request_id, f"message-{profile}")])
        run = _create_run(request_id, permission_profile=profile)
        assert run["run_kind"] == "foreground"
        assert run["origin_message_id"] == f"message-{profile}"
        assert run["goal_operations_enabled"] is True
        assert goal_tools <= _tool_names(run)
        assert "goal_ready_for_acceptance" not in _tool_names(run)
        assert "goal_complete" not in _tool_names(run)
        if profile == "read":
            assert "run_command" not in _tool_names(run)
            assert "write_file" not in _tool_names(run)
            assert "task" not in _tool_names(run)
        if profile == "plan":
            assert "task" in _tool_names(run)
            assert "run_command" not in _tool_names(run)
            assert "write_file" not in _tool_names(run)
        if profile in {"accept", "bypass"}:
            assert {"run_command", "write_file"} <= _tool_names(run)


@pytest.mark.parametrize(
    ("run_kind", "parent_run_id", "agent_depth"),
    [
        ("background", "", 0),
        ("internal", "", 0),
        ("foreground", "a" * 32, 1),
    ],
)
def test_background_internal_and_child_runs_cannot_receive_goal_tools(
    isolated_server, run_kind, parent_run_id, agent_depth,
):
    request_id = f"request-{run_kind}-{agent_depth}"
    _persist_session(SESSION_ID, [_origin_message(request_id)])
    run = _create_run(
        request_id,
        run_kind=run_kind,
        parent_run_id=parent_run_id,
        agent_depth=agent_depth,
    )
    assert not (set(server_mod._AGENT_GOAL_TOOL_NAMES) & _tool_names(run))
    assert run["goal_operations_enabled"] is False


def test_missing_ambiguous_or_forged_message_identity_fails_closed(isolated_server):
    _persist_session(SESSION_ID, [{"role": "user", "content": "legacy"}])
    missing = _create_run("foreground-missing")
    assert missing["goal_operations_enabled"] is False

    forged = _origin_message("foreground-forged")
    forged["meta"]["goalOrigin"]["messageId"] = "different-message"
    _persist_session(SESSION_ID, [forged])
    run = _create_run("foreground-forged")
    assert run["goal_operations_enabled"] is False

    duplicate = _origin_message("foreground-duplicate")
    _persist_session(SESSION_ID, [duplicate, dict(duplicate)])
    ambiguous = _create_run("foreground-duplicate")
    assert ambiguous["goal_operations_enabled"] is False

    for forged_field in (
        "sessionId", "originMessageId", "clientRequestId", "ownerRunId",
        "permissionProfile",
    ):
        errors = server_mod._registered_tool_argument_errors(
            "goal_create",
            {"objective": "valid objective", forged_field: "forged-value"},
        )
        assert any(item["reason"] == "additional_property" for item in errors)

    for forged_field in (
        "sessionId", "goalId", "revision", "originMessageId",
        "clientRequestId", "ownerRunId",
    ):
        errors = server_mod._registered_tool_argument_errors(
            "goal_complete",
            {"summary": "User accepted", forged_field: "forged-value"},
        )
        assert any(item["reason"] == "additional_property" for item in errors)


def test_explicit_goal_uses_the_persisted_origin_and_same_foreground_run_identity(
    isolated_server,
):
    request_id = "foreground-explicit-v2"
    message_id = "message-explicit-v2"
    _persist_session(SESSION_ID, [_origin_message(request_id, message_id)])
    body = {
        "operation": "explicit_create",
        "objective": "Deliver one explicit durable Goal",
        "expectedRevision": 0,
        "idempotencyKey": f"explicit-{request_id}",
        "messageId": message_id,
        "clientRequestId": request_id,
        "permissionProfile": "accept",
    }

    created = server_mod.control_goal_v2(SESSION_ID, body)
    goal = created["goal"]
    expected_run_id = server_mod._agent_run_id_for_client_request(
        SESSION_ID, request_id,
    )
    assert goal["sourceKind"] == "explicit"
    assert goal["originMessageId"] == message_id
    assert goal["ownerRunId"] == expected_run_id
    assert goal["lifecycle"] == "draft"
    stored = server_mod.read_jsonl(server_mod.messages_path(SESSION_ID))
    marker = stored[0]["meta"]["goalOrigin"]
    assert marker == {
        "messageId": message_id,
        "clientRequestId": request_id,
        "goalId": goal["goalId"],
        "sourceKind": "explicit",
        "confirmedRevision": 1,
        "confirmed": True,
    }

    run = _create_run(request_id, permission_profile="accept")
    assert run["id"] == expected_run_id
    assert run["origin_message_id"] == message_id
    assert run["goal_operations_enabled"] is True
    replay = server_mod.control_goal_v2(SESSION_ID, body)
    assert replay["noOp"] is True
    assert replay["reused"] is True
    assert server_mod.goal_v2_runtime().read(SESSION_ID).state.revision == 1


def test_goal_origin_marker_is_server_confirmed_and_browser_spoofs_fail_closed(
    isolated_server,
):
    request_id = "foreground-origin-marker"
    message_id = "message-origin-marker"
    forged = _origin_message(request_id, message_id)
    forged["meta"]["goalOrigin"].update({
        "goalId": "goal-forged",
        "sourceKind": "explicit",
        "confirmedRevision": 999,
        "confirmed": True,
    })

    sanitized = server_mod._merge_goal_v2_origin_metadata(
        SESSION_ID, [forged], existing_messages=[],
    )
    marker = sanitized[0]["meta"]["goalOrigin"]
    assert marker == {
        "messageId": message_id,
        "clientRequestId": request_id,
    }

    _persist_session(SESSION_ID, sanitized)
    result = server_mod.control_goal_v2(SESSION_ID, {
        "operation": "explicit_create",
        "objective": "Confirm the marker from the v2 event",
        "expectedRevision": 0,
        "idempotencyKey": f"explicit-{request_id}",
        "messageId": message_id,
        "clientRequestId": request_id,
        "permissionProfile": "read",
    })
    confirmed = server_mod._merge_goal_v2_origin_metadata(
        SESSION_ID,
        sanitized,
        projection=result,
        existing_messages=sanitized,
    )[0]["meta"]["goalOrigin"]
    assert confirmed["confirmed"] is True
    assert confirmed["goalId"] == result["goal"]["goalId"]
    assert confirmed["sourceKind"] == "explicit"


def test_autonomous_run_creates_plans_and_advances_goal_without_permission_change(isolated_server):
    request_id = "foreground-autonomous-main"
    _persist_session(SESSION_ID, [_origin_message(request_id)])
    run = _create_run(request_id, permission_profile="read")

    created = _call(run, "goal_create", {"objective": "Ship a durable multi-stage feature"}, "call-create")
    planned = _call(run, "goal_set_plan", {"steps": _plan()}, "call-plan")
    started = _call(run, "goal_start_step", {"stepId": "step-1"}, "call-start-1")
    completed = _call(run, "goal_complete_step", {
        "stepId": "step-1",
        "evidence": [{
            "criterionId": "criterion-1",
            "kind": "machine",
            "summary": "Targeted test passed",
        }],
    }, "call-complete-1")
    gated = _call(run, "goal_raise_gate", {
        "gateType": "waiting_user",
        "summary": "A product decision is required",
    }, "call-gate")
    cleared = _call(run, "goal_clear_gate", {}, "call-clear-gate")

    assert created["goal"]["originMessageId"] == "message-goal-origin"
    assert created["goal"]["ownerRunId"] == run["id"]
    assert created["goal"]["permissionProfile"] == "read"
    assert planned["goal"]["steps"][0]["status"] == "pending"
    assert started["goal"]["steps"][0]["status"] == "in_progress"
    evidence = completed["goal"]["steps"][0]["evidence"][0]
    assert evidence["sourceRunId"] == run["id"]
    assert evidence["sourceToolCallId"] == "call-complete-1"
    assert gated["goal"]["gate"]["type"] == "waiting_user"
    assert cleared["goal"]["gate"] is None
    assert run["permission_profile"] == "read"
    assert "run_command" not in _tool_names(run)
    goal_events = [event for event in run["events"] if (
        event.get("type") in {"tool_started", "tool_completed"}
        and str(event.get("data", {}).get("name") or "").startswith("goal_")
    )]
    assert goal_events
    assert all("internal" not in event.get("data", {}) for event in goal_events)
    assert server_mod._agent_snapshot(run)["toolExecutions"] == []


def test_foreground_worker_runs_autonomous_goal_sequence_and_simple_run_stays_goal_free(
    isolated_server, monkeypatch,
):
    request_id = "foreground-worker-autonomous"
    _persist_session(SESSION_ID, [_origin_message(request_id)])
    run = _create_run(request_id, permission_profile="accept")
    model_payloads = []
    model_results = iter([
        {
            "content": "",
            "toolCalls": [{
                "id": "worker-create",
                "type": "function",
                "function": {
                    "name": "goal_create",
                    "arguments": json.dumps({"objective": "Autonomous worker Goal"}),
                },
            }],
            "finishReason": "tool_calls",
        },
        {
            "content": "",
            "toolCalls": [{
                "id": "worker-plan",
                "type": "function",
                "function": {
                    "name": "goal_set_plan",
                    "arguments": json.dumps({"steps": _plan()}),
                },
            }],
            "finishReason": "tool_calls",
        },
        {
            "content": "",
            "toolCalls": [{
                "id": "worker-start",
                "type": "function",
                "function": {
                    "name": "goal_start_step",
                    "arguments": json.dumps({"stepId": "step-1"}),
                },
            }],
            "finishReason": "tool_calls",
        },
        {
            "content": "",
            "toolCalls": [{
                "id": "worker-complete",
                "type": "function",
                "function": {
                    "name": "goal_complete_step",
                    "arguments": json.dumps({
                        "stepId": "step-1",
                        "evidence": [{
                            "criterionId": "criterion-1",
                            "kind": "machine",
                            "summary": "Worker verification passed",
                        }],
                    }),
                },
            }],
            "finishReason": "tool_calls",
        },
        {
            "content": "Goal work is underway and the first stage is complete.",
            "toolCalls": [],
            "finishReason": "stop",
        },
    ])

    def create_model_run(session_id, payload, base_url, keys, **_kwargs):
        model_payloads.append(payload)
        return _model_runtime_stub(f"model-{len(model_payloads)}")

    def wait_for_model(_run, _model_run, **_kwargs):
        result = next(model_results)
        return {
            "status": "completed",
            "result": {
                "reasoning": "",
                "usage": {},
                **result,
            },
        }

    monkeypatch.setattr(server_mod, "_create_model_runtime_run", create_model_run)
    monkeypatch.setattr(server_mod, "_agent_wait_for_model", wait_for_model)
    server_mod._agent_run_worker(run)

    assert run["status"] == "completed"
    state = server_mod.goal_v2_runtime().read(SESSION_ID).state
    assert state.goal["sourceKind"] == "autonomous"
    assert state.goal["steps"][0]["status"] == "completed"
    assert len(model_payloads) == 5
    first_tool_names = {
        definition["function"]["name"]
        for definition in model_payloads[0].get("tools", [])
    }
    assert set(server_mod._AGENT_GOAL_DEFAULT_TOOL_NAMES) <= first_tool_names
    assert "goal_ready_for_acceptance" not in first_tool_names
    assert "goal_complete" not in first_tool_names
    assert server_mod._agent_snapshot(run)["toolExecutions"] == []
    protocol_shadow = server_mod._agent_protocol_shadow_snapshot(run)
    assert protocol_shadow["contractErrors"] == 0
    assert protocol_shadow["diagnosticCounts"] == {}

    simple_session = "session-v2-agent-simple-worker"
    simple_request = "foreground-worker-simple"
    _persist_session(simple_session, [_origin_message(simple_request, "simple-origin")])
    simple = _create_run(simple_request, session_id=simple_session)
    monkeypatch.setattr(
        server_mod,
        "_agent_wait_for_model",
        lambda _run, _model_run, **_kwargs: {
            "status": "completed",
            "result": {
                "content": "The simple answer is 4.",
                "reasoning": "",
                "toolCalls": [],
                "finishReason": "stop",
                "usage": {},
            },
        },
    )
    server_mod._agent_run_worker(simple)
    assert simple["status"] == "completed"
    assert server_mod.goal_v2_runtime().read(simple_session).state.goal is None


def test_legacy_ready_goal_worker_can_use_compatibility_completion(
    isolated_server, monkeypatch,
):
    setup_request = "foreground-acceptance-setup"
    setup_origin = _origin_message(setup_request, "message-acceptance-setup")
    _persist_session(SESSION_ID, [setup_origin])
    setup_run = _create_run(setup_request)
    _advance_goal_to_acceptance(setup_run)

    acceptance_request = "foreground-user-acceptance"
    acceptance_origin = _origin_message(acceptance_request, "message-user-acceptance")
    acceptance_origin["content"] = "The Goal looks good; I explicitly accept it."
    _persist_session(SESSION_ID, [setup_origin, acceptance_origin])
    run = _create_run(acceptance_request)
    model_payloads = []
    model_results = iter([
        {
            "content": "",
            "toolCalls": [{
                "id": "worker-goal-accept",
                "type": "function",
                "function": {
                    "name": "goal_complete",
                    "arguments": json.dumps({
                        "summary": "The user explicitly accepted the Goal",
                    }),
                },
            }],
            "finishReason": "tool_calls",
        },
        {
            "content": "The persisted completion receipt succeeded; the Goal is complete.",
            "toolCalls": [],
            "finishReason": "stop",
        },
    ])

    monkeypatch.setattr(
        server_mod,
        "_create_model_runtime_run",
        lambda _session_id, payload, _base_url, _keys, **_kwargs: (
            model_payloads.append(payload)
            or _model_runtime_stub(f"model-{len(model_payloads)}")
        ),
    )
    monkeypatch.setattr(
        server_mod,
        "_agent_wait_for_model",
        lambda _run, _model_run, **_kwargs: {
            "status": "completed",
            "result": {"reasoning": "", "usage": {}, **next(model_results)},
        },
    )
    server_mod._agent_run_worker(run)

    assert run["status"] == "completed"
    assert server_mod.goal_v2_runtime().read(SESSION_ID).state.goal["lifecycle"] == "completed"
    assert len(model_payloads) == 2
    assert "goal_complete" in {
        item["function"]["name"] for item in model_payloads[0]["tools"]
    }
    receipt = next(
        message for message in model_payloads[1]["messages"]
        if message.get("role") == "tool"
        and message.get("tool_call_id") == "worker-goal-accept"
    )
    receipt_payload = json.loads(receipt["content"])
    assert receipt_payload["ok"] is True
    assert receipt_payload["action"] == "goal_complete"
    assert receipt_payload["goal"]["lifecycle"] == "completed"


def test_user_acceptance_step_stays_in_progress_until_gate_is_cleared(
    isolated_server,
):
    request_id = "foreground-user-gated-final-step"
    _persist_session(SESSION_ID, [_origin_message(request_id)])
    run = _create_run(request_id)
    plan = _plan()
    plan[-1]["acceptanceCriteria"][0]["kind"] = "user"
    _call(run, "goal_create", {"objective": "User-gated Goal"}, "create")
    _call(run, "goal_set_plan", {"steps": plan}, "plan")
    for index in (1, 2):
        _call(run, "goal_start_step", {"stepId": f"step-{index}"}, f"start-{index}")
        _call(run, "goal_complete_step", {
            "stepId": f"step-{index}",
            "evidence": [{
                "criterionId": f"criterion-{index}",
                "kind": "machine",
                "summary": "Machine acceptance passed",
            }],
        }, f"complete-{index}")
    _call(run, "goal_start_step", {"stepId": "step-3"}, "start-3")
    _call(run, "goal_raise_gate", {
        "gateType": "waiting_user",
        "summary": "The final product check needs the user's judgment",
    }, "gate-user")

    blocked = _call(run, "goal_complete_step", {
        "stepId": "step-3",
        "evidence": [{
            "criterionId": "criterion-3",
            "kind": "user",
            "summary": "User has not actually accepted yet",
        }],
    }, "complete-before-user")
    assert blocked["ok"] is False
    assert "gated Goal step" in blocked["error"]
    current = server_mod.goal_v2_runtime().read(SESSION_ID).state
    assert current.goal["lifecycle"] == "active"
    assert current.goal["steps"][-1]["status"] == "in_progress"

    _call(run, "goal_clear_gate", {}, "clear-user-gate")
    wrong_kind = _call(run, "goal_complete_step", {
        "stepId": "step-3",
        "evidence": [{
            "criterionId": "criterion-3",
            "kind": "machine",
            "summary": "Machine evidence cannot replace user acceptance",
        }],
    }, "complete-wrong-kind")
    assert wrong_kind["ok"] is False
    assert "evidence kind" in wrong_kind["error"]

    completed = _call(run, "goal_complete_step", {
        "stepId": "step-3",
        "evidence": [{
            "criterionId": "criterion-3",
            "kind": "user",
            "summary": "The user accepted the concrete final step",
        }],
    }, "complete-after-user")
    assert completed["ok"] is True
    assert completed["goal"]["lifecycle"] == "completed"
    assert completed["goal"]["steps"][-1]["status"] == "completed"


def test_same_goal_reuses_and_different_goal_fails_closed(isolated_server):
    first_request = "foreground-same-objective-a"
    _persist_session(SESSION_ID, [_origin_message(first_request, "message-a")])
    first = _create_run(first_request)
    _call(first, "goal_create", {"objective": "One durable objective"}, "call-create-a")

    second_request = "foreground-same-objective-b"
    _persist_session(SESSION_ID, [_origin_message(second_request, "message-b")])
    second = _create_run(second_request)
    reused = _call(second, "goal_create", {"objective": " One durable objective "}, "call-create-b")
    assert reused["noOp"] is True
    assert reused["reused"] is True

    third_request = "foreground-different-objective"
    _persist_session(SESSION_ID, [_origin_message(third_request, "message-c")])
    third = _create_run(third_request)
    conflict = _call(third, "goal_create", {"objective": "Different objective"}, "call-create-c")
    assert conflict["ok"] is False
    assert "different nonterminal Goal" in conflict["error"]
    assert server_mod.goal_v2_runtime().read(SESSION_ID).state.revision == 1


def test_prepared_goal_operation_is_restart_safe_and_exactly_once(isolated_server):
    request_id = "foreground-restart-safe"
    _persist_session(SESSION_ID, [_origin_message(request_id)])
    run = _create_run(request_id)
    _call(run, "goal_create", {"objective": "Restart-safe Goal"}, "call-create")

    call = server_mod._normalize_agent_tool_calls(run, [{
        "id": "call-plan-restart",
        "type": "function",
        "function": {
            "name": "goal_set_plan",
            "arguments": json.dumps({"steps": _plan()}),
        },
    }], 2)[0]
    execution = {
        "name": "goal_set_plan",
        "arguments": call["function"]["arguments"],
        "fingerprint": call["fingerprint"],
        "status": "running",
        "result": None,
        "startedAt": server_mod.now_iso(),
    }
    run["tool_executions"][call["id"]] = execution
    first = server_mod._execute_agent_goal_operation(run, call, execution)
    assert first["revision"] == 2

    record = server_mod._agent_run_record(run)
    assert record["runKind"] == "foreground"
    assert "originMessageId" not in record
    assert "goalOperationsEnabled" not in record
    rebuilt = server_mod._agent_run_from_record(record)
    assert rebuilt["goal_operations_enabled"] is True
    assert rebuilt["origin_message_id"] == "message-goal-origin"
    rebuilt_execution = rebuilt["tool_executions"][call["id"]]
    replay = server_mod._execute_agent_goal_operation(rebuilt, call, rebuilt_execution)
    assert replay["noOp"] is True
    assert replay["revision"] == 2
    assert server_mod.goal_v2_runtime().read(SESSION_ID).state.revision == 2


def test_final_step_completes_goal_once_and_allows_a_new_goal(isolated_server):
    setup_request_id = "foreground-goal-work"
    setup_origin = _origin_message(setup_request_id, "message-goal-work")
    _persist_session(SESSION_ID, [setup_origin])
    setup_run = _create_run(setup_request_id, permission_profile="accept")
    _call(setup_run, "goal_create", {"objective": "Complete directly"}, "create-direct")
    _call(setup_run, "goal_set_plan", {"steps": _plan()}, "plan-direct")
    for index in range(1, 4):
        _call(
            setup_run, "goal_start_step", {"stepId": f"step-{index}"},
            f"start-direct-{index}",
        )
        completed = _call(setup_run, "goal_complete_step", {
            "stepId": f"step-{index}",
            "evidence": [{
                "criterionId": f"criterion-{index}",
                "kind": "machine",
                "summary": f"Stage {index} passed",
            }],
        }, f"complete-direct-{index}")
    assert completed["ok"] is True
    assert completed["goal"]["lifecycle"] == "completed"
    assert completed["revision"] == 8
    assert all(step["status"] == "completed" for step in completed["goal"]["steps"])
    event_types = [
        json.loads(line)["type"]
        for line in server_mod.goal_v2_runtime().service.events_path(SESSION_ID).read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert event_types[-1] == "goal_completed"
    assert "goal_ready_for_acceptance" not in event_types

    # Replaying the prepared mutation after rebuilding the AgentRun consults
    # the persisted idempotency fact and cannot append a second completion.
    call = server_mod._normalize_agent_tool_calls(setup_run, [{
        "id": "complete-direct-3",
        "type": "function",
        "function": {
            "name": "goal_complete_step",
            "arguments": json.dumps({
                "stepId": "step-3",
                "evidence": [{
                    "criterionId": "criterion-3",
                    "kind": "machine",
                    "summary": "Stage 3 passed",
                }],
            }),
        },
    }], 20)[0]
    rebuilt = server_mod._agent_run_from_record(
        server_mod._agent_run_record(setup_run)
    )
    replay = server_mod._execute_agent_goal_operation(
        rebuilt,
        call,
        rebuilt["tool_executions"]["complete-direct-3"],
    )
    assert replay["noOp"] is True
    assert replay["revision"] == 8
    assert server_mod.goal_v2_runtime().read(SESSION_ID).state.revision == 8

    next_request_id = "foreground-after-accepted-goal"
    _persist_session(SESSION_ID, [
        _origin_message(next_request_id, "message-next-goal"),
    ])
    next_run = _create_run(next_request_id)
    next_goal = _call(
        next_run,
        "goal_create",
        {"objective": "Start a distinct Goal after acceptance"},
        "call-next-goal",
    )
    assert next_goal["ok"] is True
    assert next_goal["goal"]["lifecycle"] == "draft"
    assert next_goal["goal"]["goalId"] != completed["goal"]["goalId"]
    assert next_goal["revision"] == 9


def test_successful_final_step_derives_one_no_tool_complete_response_round(
    isolated_server,
):
    request_id = "foreground-goal-final-response"
    _persist_session(SESSION_ID, [_origin_message(request_id)])
    run = _create_run(request_id)
    _call(run, "goal_create", {"objective": "Produce one complete Goal result"}, "create")
    _call(run, "goal_set_plan", {"steps": _plan()}, "plan")
    for index in range(1, 3):
        _call(run, "goal_start_step", {"stepId": f"step-{index}"}, f"start-{index}")
        _call(run, "goal_complete_step", {
            "stepId": f"step-{index}",
            "evidence": [{
                "criterionId": f"criterion-{index}",
                "kind": "machine",
                "summary": f"Stage {index} evidence passed",
            }],
        }, f"complete-{index}")
    _call(run, "goal_start_step", {"stepId": "step-3"}, "start-3")

    call = {
        "id": "complete-final",
        "type": "function",
        "function": {
            "name": "goal_complete_step",
            "arguments": json.dumps({
                "stepId": "step-3",
                "evidence": [{
                    "criterionId": "criterion-3",
                    "kind": "machine",
                    "summary": "Final stage evidence passed",
                }],
            }),
        },
    }
    run["messages"].append({
        "role": "assistant",
        "content": "Final evidence is verified; persisting the last step now.",
        "tool_calls": [call],
    })
    run["pending_tool_calls"] = server_mod._normalize_agent_tool_calls(
        run, [call], len(run.get("rounds") or []) + 1,
    )
    run["status"] = "tools"
    assert server_mod._execute_agent_pending_tools(run) is True
    assert run["tool_executions"]["complete-final"]["result"]["goal"]["lifecycle"] == "completed"
    assert server_mod._agent_goal_final_response_pending(run) is True

    payload, force_final = server_mod._agent_model_payload(run)
    assert force_final is False
    assert "tools" not in payload
    assert "tool_choice" not in payload
    assert payload["messages"][-1] == {
        "role": "system",
        "content": server_mod._AGENT_GOAL_FINAL_RESPONSE_INSTRUCTION,
    }
    assert "one complete, self-contained user-facing final answer" in payload["messages"][-1]["content"]
    assert "Do not say that the summary is above" in payload["messages"][-1]["content"]
    assert any(
        message.get("role") == "assistant"
        and message.get("content") == "Final evidence is verified; persisting the last step now."
        for message in payload["messages"]
    )

    failed = {
        "goal_operations_enabled": True,
        "pending_tool_calls": [],
        "messages": [{"role": "assistant", "tool_calls": [call]}],
        "tool_executions": {
            "complete-final": {
                "status": "completed",
                "result": {"ok": False, "action": "goal_complete_step"},
            },
        },
    }
    assert server_mod._agent_goal_final_response_pending(failed) is False


def test_final_step_completion_rejects_gate_and_stale_operations(isolated_server):
    request_id = "foreground-invalid-acceptance"
    _persist_session(SESSION_ID, [_origin_message(request_id, "message-invalid-acceptance")])
    run = _create_run(request_id)
    _call(run, "goal_create", {"objective": "Do not accept early"}, "call-create")
    _call(run, "goal_set_plan", {"steps": _plan()}, "call-plan")
    for index in range(1, 3):
        _call(run, "goal_start_step", {"stepId": f"step-{index}"}, f"start-{index}")
        _call(run, "goal_complete_step", {
            "stepId": f"step-{index}",
            "evidence": [{
                "criterionId": f"criterion-{index}",
                "kind": "machine",
                "summary": "Evidence passed",
            }],
        }, f"complete-{index}")
    _call(run, "goal_start_step", {"stepId": "step-3"}, "start-3")

    pending = server_mod._normalize_agent_tool_calls(run, [{
        "id": "stale-final-step",
        "type": "function",
        "function": {
            "name": "goal_complete_step",
            "arguments": json.dumps({
                "stepId": "step-3",
                "evidence": [{
                    "criterionId": "criterion-3",
                    "kind": "machine",
                    "summary": "Final evidence passed",
                }],
            }),
        },
    }], 20)[0]
    execution = {
        "name": "goal_complete_step",
        "arguments": pending["function"]["arguments"],
        "fingerprint": pending["fingerprint"],
        "status": "running",
        "result": None,
        "startedAt": server_mod.now_iso(),
    }
    server_mod._agent_goal_prepare_operation(run, pending, execution)
    state = server_mod.goal_v2_runtime().read(SESSION_ID).state
    server_mod.goal_v2_runtime().pause(
        SESSION_ID,
        state.goal["goalId"],
        reason="A later user message paused the Goal",
        source_run_id=run["id"],
        expected_revision=state.revision,
        idempotency_key="pause-before-stale-accept",
    )
    with pytest.raises(server_mod.GoalV2ConflictError, match="stale Goal v2 revision"):
        server_mod._execute_agent_goal_operation(run, pending, execution)
    read = server_mod.goal_v2_runtime().read(SESSION_ID).state
    assert read.goal["lifecycle"] == "paused"
    assert read.goal["steps"][-1]["status"] == "in_progress"
    assert read.revision == 8


def test_simple_foreground_run_that_does_not_call_goal_tools_writes_no_goal(isolated_server):
    request_id = "foreground-simple"
    _persist_session(SESSION_ID, [_origin_message(request_id)])
    run = _create_run(request_id)

    assert run["goal_operations_enabled"] is True
    assert server_mod.goal_v2_runtime().read(SESSION_ID).state.revision == 0
    assert not (Path(isolated_server) / "goals-v2").exists()


def test_goal_soft_handoff_admits_one_durable_successor_and_redacts_reasoning(
    isolated_server, monkeypatch,
):
    run = _active_goal_run()
    run["rounds"] = [{
        "round": index,
        "runtimeRunId": f"runtime-{index}",
        "content": "public progress" if index == 40 else "",
        "reasoning": f"private chain {index}",
        "toolCalls": [],
        "usage": {"total_tokens": 1},
    } for index in range(1, 41)]
    run["events"].append(server_mod._build_agent_event(
        run["next_seq"],
        "model_completed",
        {"round": 40, "content": "public progress", "reasoning": "private chain"},
        server_mod.now_iso(),
    ))
    run["next_seq"] += 1
    started = []
    monkeypatch.setattr(server_mod, "_start_agent_worker", lambda child: started.append(child["id"]))

    assert server_mod._handoff_agent_goal_run(
        run, reason="soft_round_limit", hard_limit=False,
    ) is True
    continuation = run["result"]["continuation"]
    successor = server_mod._get_agent_run(continuation["agentRunId"])

    assert run["status"] == "completed"
    assert started == [successor["id"]]
    assert successor["permission_profile"] == run["permission_profile"]
    assert successor["base_url"] == run["base_url"]
    assert successor["continuation"]["parentRunId"] == run["id"]
    assert successor["origin_message_id"] == run["origin_message_id"]
    assert successor["goal_operations_enabled"] is True
    assert len(successor["messages"]) == 2
    assert [item["role"] for item in successor["messages"]] == ["system", "user"]
    serialized_checkpoint = json.dumps(successor["messages"], ensure_ascii=False)
    assert "public progress" in serialized_checkpoint
    assert "private chain" not in serialized_checkpoint
    assert "tool_calls" not in serialized_checkpoint

    durable = server_mod.read_json(server_mod._agent_run_path(run["id"]), {})
    assert all(item.get("reasoning") == "" for item in durable["rounds"])
    assert all(
        (event.get("data") or {}).get("reasoning", "") == ""
        for event in durable["events"]
        if event.get("type") == "model_completed"
    )
    assert "private chain" not in json.dumps(server_mod._agent_snapshot(run), ensure_ascii=False)

    with server_mod._agent_run_lock:
        server_mod._agent_runs.pop(successor["id"], None)
    recovered = server_mod._get_agent_run(successor["id"])
    assert recovered["status"] == "waiting_credentials"
    assert recovered["resume_status"] == "model"
    assert recovered["origin_message_id"] == run["origin_message_id"]
    assert recovered["goal_operations_enabled"] is True


def test_goal_continuation_checkpoint_is_bounded_valid_json(isolated_server):
    run = _active_goal_run("foreground-bounded-checkpoint")
    run["rounds"] = [
        {
            "round": index,
            "content": f"public-{index}-" + ("a" * 6000),
            "reasoning": "private chain must never be projected",
        }
        for index in range(1, 13)
    ]
    for index in range(24):
        run["tool_executions"][f"read-{index}"] = {
            "name": "read_file",
            "arguments": "p" * 6000,
            "status": "completed",
            "outcome": "succeeded",
            "result": {"content": "r" * 6000},
        }
    projection = server_mod.goal_v2_runtime().read(SESSION_ID).projection()

    serialized = server_mod._agent_continuation_public_checkpoint(run, projection)
    checkpoint = json.loads(serialized)

    assert len(serialized) <= server_mod._AGENT_GOAL_CHECKPOINT_MAX_CHARS
    assert checkpoint["kind"] == "goal_agent_continuation_v1"
    assert checkpoint["goalRevision"] == projection["revision"]
    assert checkpoint["truncated"] is True
    assert "private chain" not in serialized


def test_goal_handoff_is_duplicate_safe_and_starts_one_successor(
    isolated_server, monkeypatch,
):
    run = _active_goal_run("foreground-handoff-duplicate")
    run["rounds"] = [{"round": index, "content": "", "reasoning": ""}
                     for index in range(1, 41)]
    started = []

    def start_once(child):
        with child["condition"]:
            if child.get("worker") is None:
                child["worker"] = object()
                started.append(child["id"])
            return child["worker"]

    monkeypatch.setattr(server_mod, "_start_agent_worker", start_once)

    assert server_mod._handoff_agent_goal_run(run, reason="soft_round_limit") is True
    first = dict(run["result"]["continuation"])
    assert server_mod._handoff_agent_goal_run(run, reason="soft_round_limit") is True
    second = dict(run["result"]["continuation"])

    assert first == second
    assert started == [first["agentRunId"]]
    assert len([
        item for item in server_mod._agent_runs.values()
        if str((item.get("continuation") or {}).get("parentRunId") or "") == run["id"]
    ]) == 1


def test_worker_crosses_round_40_with_read_tool_without_fixed_handoff(
    isolated_server, monkeypatch,
):
    run = _active_goal_run("foreground-worker-soft-boundary")
    run["max_rounds"] = 50
    run["rounds"] = [{"round": index, "content": "", "reasoning": ""}
                     for index in range(1, 40)]
    model_payloads = []
    model_results = iter([
        {
            "content": "",
            "reasoning": "private",
            "toolCalls": [{
                "id": "boundary-read",
                "type": "function",
                "function": {
                    "name": "list_files",
                    "arguments": json.dumps({"path": "."}),
                },
            }],
            "finishReason": "tool_calls",
            "usage": {},
        },
        {
            "content": "continued beyond the former Goal round boundary",
            "reasoning": "",
            "toolCalls": [],
            "finishReason": "stop",
            "usage": {},
        },
    ])
    monkeypatch.setattr(
        server_mod,
        "_create_model_runtime_run",
        lambda _session_id, payload, _base_url, _keys, **_kwargs: (
            model_payloads.append(payload)
            or _model_runtime_stub(f"boundary-model-{len(model_payloads)}")
        ),
    )
    monkeypatch.setattr(
        server_mod,
        "_agent_wait_for_model",
        lambda _run, _model_run, **_kwargs: {
            "status": "completed",
            "result": next(model_results),
        },
    )

    server_mod._agent_run_worker(run)

    assert len(model_payloads) == 2
    assert len(run["rounds"]) == 41
    assert run["tool_executions"]["boundary-read"]["status"] == "completed"
    assert run["status"] == "completed"
    assert run["result"]["content"] == "continued beyond the former Goal round boundary"
    assert "continuation" not in run["result"]


def test_goal_hard_limit_keeps_auditable_failure_while_successor_continues(
    isolated_server, monkeypatch,
):
    run = _active_goal_run("foreground-hard-limit")
    run["rounds"] = [{"round": index, "content": "", "reasoning": "secret"}
                     for index in range(1, 51)]
    monkeypatch.setattr(server_mod, "_start_agent_worker", lambda _child: None)

    assert server_mod._handoff_agent_goal_run(
        run, reason="hard_round_limit", hard_limit=True,
    ) is True
    assert run["status"] == "failed"
    assert run["error_code"] == "goal_run_hard_limit"
    assert run["result"]["continuation"]["agentRunId"]
    assert server_mod.goal_v2_runtime().read(SESSION_ID).state.goal["lifecycle"] == "active"


def test_goal_round_50_continues_without_fixed_failure_when_gated(
    isolated_server, monkeypatch,
):
    run = _active_goal_run("foreground-worker-hard-boundary")
    state = server_mod.goal_v2_runtime().read(SESSION_ID).state
    server_mod.goal_v2_runtime().raise_gate(
        SESSION_ID,
        state.goal["goalId"],
        "waiting_user",
        "A user decision arrived at the hard boundary",
        source_run_id=run["id"],
        expected_revision=state.revision,
        idempotency_key="hard-boundary-gate",
    )
    run["max_rounds"] = 50
    run["rounds"] = [{"round": index, "content": "", "reasoning": ""}
                     for index in range(1, 50)]
    model_results = iter([
        {
            "content": "",
            "reasoning": "private",
            "toolCalls": [{
                "id": "hard-boundary-read",
                "type": "function",
                "function": {
                    "name": "list_files",
                    "arguments": json.dumps({"path": "."}),
                },
            }],
            "finishReason": "tool_calls",
            "usage": {},
        },
        {
            "content": "continued beyond the former hard boundary",
            "reasoning": "",
            "toolCalls": [],
            "finishReason": "stop",
            "usage": {},
        },
    ])
    monkeypatch.setattr(
        server_mod,
        "_create_model_runtime_run",
        lambda _session_id, _payload, _base_url, _keys, **_kwargs: _model_runtime_stub(
            f"boundary-model-{len(run['rounds']) + 1}"
        ),
    )
    monkeypatch.setattr(
        server_mod,
        "_agent_wait_for_model",
        lambda _run, _model_run, **_kwargs: {
            "status": "completed",
            "result": next(model_results),
        },
    )

    server_mod._agent_run_worker(run)

    assert len(run["rounds"]) == 51
    assert run["status"] == "completed"
    assert run["error_code"] == ""
    assert run["tool_executions"]["hard-boundary-read"]["status"] == "completed"
    assert "continuation" not in run["result"]
    assert server_mod.goal_v2_runtime().read(SESSION_ID).state.goal["gate"]["type"] == "waiting_user"


def test_repeated_terminal_error_pauses_after_one_successor(
    isolated_server, monkeypatch,
):
    run = _active_goal_run("foreground-repeated-terminal-error")
    monkeypatch.setattr(server_mod, "_start_agent_worker", lambda _child: None)

    assert server_mod._handoff_agent_goal_run(
        run,
        reason="transient_model_failure",
        terminal_error="upstream timed out",
        terminal_error_code="upstream_timeout",
    ) is True
    successor = server_mod._get_agent_run(run["result"]["continuation"]["agentRunId"])
    assert successor["status"] == "model"

    assert server_mod._handoff_agent_goal_run(
        successor,
        reason="transient_model_failure",
        terminal_error="upstream timed out",
        terminal_error_code="upstream_timeout",
    ) is True
    goal = server_mod.goal_v2_runtime().read(SESSION_ID).state.goal
    assert successor["status"] == "completed"
    assert successor["result"]["continuationPaused"] is True
    assert goal["gate"]["type"] == "waiting_user"


def test_two_stalled_goal_runs_raise_one_user_gate_instead_of_looping(
    isolated_server, monkeypatch,
):
    run = _active_goal_run("foreground-stall-root")
    current_revision = server_mod.goal_v2_runtime().read(SESSION_ID).state.revision
    run["continuation"] = {
        "goalId": server_mod.goal_v2_runtime().read(SESSION_ID).state.goal["goalId"],
        "originMessageId": run["origin_message_id"],
        "rootRunId": run["id"],
        "rootClientRequestId": run["client_request_id"],
        "index": 1,
        "baselineGoalRevision": current_revision,
        "stalledHandoffs": 1,
    }
    run["rounds"] = [{"round": index, "content": "", "reasoning": ""}
                     for index in range(1, 41)]
    monkeypatch.setattr(server_mod, "_start_agent_worker", lambda _child: None)

    assert server_mod._handoff_agent_goal_run(
        run, reason="soft_round_limit", hard_limit=False,
    ) is True
    state = server_mod.goal_v2_runtime().read(SESSION_ID).state
    assert run["status"] == "completed"
    assert run["result"]["continuationPaused"] is True
    assert "continuation" not in run["result"]
    assert state.goal["gate"]["type"] == "waiting_user"
    assert state.goal["steps"][0]["status"] == "in_progress"


def test_continuation_does_not_replay_an_identical_successful_side_effect(
    isolated_server, monkeypatch,
):
    run = _active_goal_run("foreground-no-replay")
    run["continuation"] = {
        "goalId": server_mod.goal_v2_runtime().read(SESSION_ID).state.goal["goalId"],
        "originMessageId": run["origin_message_id"],
        "protectedEffectFingerprints": [],
    }
    calls = server_mod._normalize_agent_tool_calls(run, [{
        "id": "write-once",
        "type": "function",
        "function": {
            "name": "write_file",
            "arguments": json.dumps({"path": "once.txt", "content": "once"}),
        },
    }], 1)
    fingerprint = calls[0]["fingerprint"]
    run["continuation"]["protectedEffectFingerprints"] = [fingerprint]
    run["pending_tool_calls"] = calls
    run["status"] = "tools"
    execute = monkeypatch.spy(server_mod, "tool_write_file") if hasattr(monkeypatch, "spy") else None

    assert server_mod._execute_agent_pending_tools(run) is True
    result = run["tool_executions"]["write-once"]["result"]
    assert result["notReplayed"] is True
    assert not (Path(isolated_server).parent / "project" / "once.txt").exists()
    if execute is not None:
        execute.assert_not_called()


def test_goal_successor_protects_successful_image_generation_without_false_positive(
    isolated_server, monkeypatch,
):
    root = Path(isolated_server)
    registry = image_runtime.ImageRouteRegistry(root / "image-routes.json")
    catalog = registry.refresh([{
        "connectionId": "goal-image",
        "name": "Goal image",
        "baseUrl": "https://goal-image.invalid/v1",
        "key": "GOAL_IMAGE_SECRET",
        "models": [{"id": "goal-image-v1", "supportsEdit": False}],
    }])
    route = registry.resolve(
        catalog["routes"][0]["routeRef"],
        catalog["catalogRevision"],
        "goal-image-v1",
    )
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), (30, 60, 90)).save(buffer, format="PNG")
    generated = image_runtime.validate_image_bytes(buffer.getvalue())

    class ImageClient:
        def __init__(self):
            self.calls = []

        def generate(self, resolved, normalized, operation_id, **_kwargs):
            self.calls.append({
                "routeRef": resolved.route_ref,
                "prompt": normalized["prompt"],
                "operationId": operation_id,
            })
            return [generated]

    client = ImageClient()
    assets = image_runtime.GeneratedAssetRepository(root / "generated-assets")
    monkeypatch.setattr(server_mod, "_image_route_registry", registry)
    monkeypatch.setattr(server_mod, "_generated_asset_repository", assets)
    monkeypatch.setattr(server_mod, "_image_upstream_client", client)

    run = _active_goal_run(
        "foreground-image-continuation",
        image_route=route,
    )
    arguments = {
        "prompt": "render durable goal evidence",
        "size": "auto",
        "quality": "standard",
        "count": 1,
        "outputFormat": "png",
    }
    first = _call(run, "generate_image", arguments, "image-original")
    assert first["ok"] is True
    assert len(client.calls) == 1
    fingerprint = run["tool_executions"]["image-original"]["fingerprint"]

    monkeypatch.setattr(server_mod, "_start_agent_worker", lambda _child: None)
    run["status"] = "model"
    assert server_mod._handoff_agent_goal_run(run, reason="soft_round_limit") is True
    successor = server_mod._get_agent_run(run["result"]["continuation"]["agentRunId"])
    assert fingerprint in successor["continuation"]["protectedEffectFingerprints"]
    assert successor["image_route"]["routeRef"] == route.route_ref

    repeated = _call(successor, "generate_image", arguments, "image-repeated")
    assert repeated["notReplayed"] is True
    assert len(client.calls) == 1

    distinct = _call(
        successor,
        "generate_image",
        {**arguments, "prompt": "render distinct goal evidence"},
        "image-distinct",
    )
    assert distinct["ok"] is True
    assert len(client.calls) == 2
