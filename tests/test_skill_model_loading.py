"""Real append-only loading contracts in fresh, owned synthetic data roots."""
import copy
import json
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import pytest

import server as server_mod
from code_runtime import data_dir_owner, skill_loading, skill_revisions, skill_store, skill_store_management, skill_outcome
from code_runtime.skill_activation import SKILL_PROMPT_MARKER, DELEGATION_BEGIN_MARKER, DELEGATION_END_MARKER

TOOLS = ["use_skill", "read_file", "write_file", "read_skill_resource", "check_skill_dependencies", "run_command"]


@pytest.fixture
def loading_env(tmp_path, monkeypatch, request):
    data, bundle, workspace = tmp_path / "data", tmp_path / "bundle", tmp_path / "workspace"
    data.mkdir(); bundle.mkdir(); workspace.mkdir()
    (data / "skills").mkdir()
    identities = {}
    options = getattr(request, "param", {})
    entries = {"ledger": "Summarize transaction data using the packaged rules",
               "refine": "Improve the wording of an existing report", "other": "Another independent execution task"}
    entries.update({name: "Explicit workflow fixture" for name in options if name not in entries})
    for name, description in entries.items():
        package = bundle / name
        package.mkdir()
        spec = options.get(name, {})
        document = f"---\nname: {name}\ndescription: {description}\nkeywords: definitely-not-a-router\nallowed-tools: {', '.join(spec.get('tools', TOOLS))}\n---\n\nPinned instructions for {name}.\n" + spec.get("body", "")
        if spec.get("preference"):
            document = document.replace("allowed-tools:", "tools:")
        (package / "SKILL.md").write_text(document, encoding="utf-8")
        (package / "rules.txt").write_text("Use exact decimal arithmetic.\n", encoding="utf-8")
        if spec.get("evidence"):
            (package / "evidence.json").write_text(json.dumps(spec["evidence"]), encoding="utf-8")
        shutil.copytree(package, data / "skills" / name)
        identities[name] = "code.bundle/" + name
    store = skill_store.SkillStore(data, bundle, write_enabled=True)
    store.bootstrap(skill_revisions.build_bundled_catalog(bundle, identities))
    reader = skill_store.SkillStoreReader(data)
    monkeypatch.setattr(server_mod, "DATA_DIR", data)
    monkeypatch.setattr(server_mod, "SKILLS_DIR", tmp_path / "forbidden-mutable-root")
    monkeypatch.setattr(server_mod, "_MODEL_ROUTE_REGISTRY_ENABLED", False)
    monkeypatch.setattr(server_mod, "_SKILL_MODEL_LOADING_ENABLED", True)
    monkeypatch.setattr(server_mod, "_SKILL_COMPLETION_ENFORCEMENT_ENABLED", False)
    with server_mod._agent_run_lock:
        server_mod._agent_runs.clear()
    (workspace / "input.txt").write_text("sample", encoding="utf-8")
    yield data, bundle, workspace, reader
    with server_mod._agent_run_lock:
        server_mod._agent_runs.clear()


def make_run(env, *, explicit="", permission="bypass", message="Process ledger.csv", tools=None, disabled_names=None):
    _data, _bundle, workspace, reader = env
    delegation = f"\n\n{DELEGATION_BEGIN_MARKER}\nDelegate work when authorized.\n{DELEGATION_END_MARKER}" if "task" in (tools or []) else ""
    return server_mod._create_agent_run(
        "", {"model": "deterministic-fixture", "messages": [
            {"role": "system", "content": f"base\n\n{SKILL_PROMPT_MARKER}\n\npermissions{delegation}"},
            {"role": "user", "content": message},
        ]}, "http://127.0.0.1:9", [], {"schemaVersion": 1, "names": tools or TOOLS},
        8, permission, start_worker=False, run_kind="foreground", cwd=str(workspace),
        skill_activation_request={"schemaVersion": 2, "explicitSkill": explicit, "disabledNames": disabled_names or []},
        _immutable_skill_reader=reader,
    )


def call(run, name, arguments, call_id="call-1"):
    prepared = server_mod._normalize_agent_tool_calls(run, [{
        "id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)},
    }], 1)[0]
    run["pending_tool_calls"] = [prepared]
    run["status"] = "tools"
    server_mod._execute_agent_pending_tools(run)
    return run["tool_executions"][call_id]


def test_catalog_has_real_descriptions_without_semantic_preselection(loading_env):
    with mock.patch("code_runtime.skill_registry.resolve_skill_shadow", side_effect=AssertionError("semantic router called")):
        run = make_run(loading_env)
    assert run["active_skill_names"] == []
    assert "Summarize transaction data" in run["messages"][0]["content"]
    assert "Pinned instructions for ledger" not in run["messages"][0]["content"]
    assert {item["name"] for item in run["skill_loading"]["catalog"]} == {"ledger", "refine", "other"}
    assert server_mod._agent_run_record(run)["version"] == 7


def test_default_loading_preserves_browser_disabled_selection(loading_env, monkeypatch):
    monkeypatch.setattr(server_mod, "_SKILL_MODEL_LOADING_ENABLED", server_mod._resolve_skill_model_loading_enabled({}))
    before = loading_env[-1].read_registry()
    run = make_run(loading_env, disabled_names=["ledger"])
    assert {item["name"] for item in run["skill_loading"]["catalog"]} == {"refine", "other"}
    assert run["active_skill_names"] == []
    assert loading_env[-1].read_registry() == before
    result = call(run, "use_skill", {"name": "ledger", "role": "owner"})
    assert result["result"]["errorCode"] == "skill_loading_not_available_in_catalog"
    assert not run["skill_loading"]["loads"]


def test_mid_task_first_load_and_modifier_keep_old_execution_unattributed(loading_env):
    run = make_run(loading_env)
    earlier = copy.deepcopy(call(run, "read_file", {"path": "input.txt"}, "before-load"))
    result = call(run, "use_skill", {"name": "ledger", "role": "owner"}, "load-owner")
    assert result["result"]["bodyLoaded"] is True
    assert run["active_skill_names"] == ["ledger"]
    assert "Pinned instructions for ledger" in run["messages"][0]["content"]
    assert run["tool_executions"]["before-load"] == earlier
    assert earlier["skillLoadCount"] == 0 and earlier["skillExecutionContext"]["skills"] == []
    modifier = call(run, "use_skill", {"name": "refine", "role": "modifier"}, "load-modifier")
    assert modifier["result"]["ok"] is True
    assert run["active_skill_names"] == ["ledger", "refine"]
    record = server_mod._agent_run_record(run)
    restored = server_mod._agent_run_from_record(record, immutable_skill_reader=loading_env[-1])
    assert restored["tool_executions"]["before-load"] == earlier
    assert restored["skill_loading"] == run["skill_loading"]


@pytest.mark.parametrize("arguments,code", [
    ({"name": "ledger"}, "skill_loading_arguments_invalid"),
    ({"name": "refine", "role": "modifier"}, "skill_loading_owner_required"),
    ({"name": "missing", "role": "owner"}, "skill_loading_not_available_in_catalog"),
])
def test_invalid_load_has_no_partial_activation(loading_env, arguments, code):
    run = make_run(loading_env)
    before = copy.deepcopy(run["skill_loading"])
    execution = call(run, "use_skill", arguments)
    assert execution["result"]["errorCode"] == code
    assert run["skill_loading"] == before and not run["active_skill_names"]


def test_second_owner_limit_and_duplicate_receipt(loading_env):
    run = make_run(loading_env)
    first = call(run, "use_skill", {"name": "ledger", "role": "owner"}, "first")["result"]
    duplicate = call(run, "use_skill", {"name": "ledger", "role": "owner"}, "repeat")["result"]
    assert duplicate["newlyLoaded"] is False and duplicate["loadReceiptId"] == first["loadReceiptId"]
    failed = call(run, "use_skill", {"name": "other", "role": "owner"}, "second-owner")
    assert failed["result"]["errorCode"] == "skill_loading_second_owner_rejected"
    call(run, "use_skill", {"name": "refine", "role": "modifier"}, "modifier")
    limited = call(run, "use_skill", {"name": "other", "role": "modifier"}, "third")
    assert limited["result"]["errorCode"] == "skill_loading_limit_reached"
    assert len(run["skill_loading"]["loads"]) == 2


def test_explicit_load_is_real_once_and_remains_exclusive(loading_env):
    run = make_run(loading_env, explicit="ledger")
    before_messages = copy.deepcopy(run["messages"][1:])
    assert server_mod._ensure_explicit_skill_load(run)
    assert server_mod._ensure_explicit_skill_load(run)
    assert run["messages"][1:] == before_messages  # no forged model request
    operations = [item for item in run["tool_executions"].values() if item.get("skillLoadOrigin") == "explicit"]
    assert len(operations) == 1 and operations[0]["result"]["loadOrigin"] == "explicit"
    failed = call(run, "use_skill", {"name": "refine", "role": "modifier"}, "other")
    assert failed["result"]["errorCode"] == "skill_loading_explicit_exclusive"


def snapshot(run):
    return {key: copy.deepcopy(run[key]) for key in (
        "skill_loading", "skill_lifecycle", "active_skill_names", "active_skill_dependencies", "tools",
        "tool_budgets", "skill_completion_enforcement",
    )} | {"system": run["messages"][0]["content"]}


@pytest.mark.parametrize("explicit", ["", "ledger", "missing"])
def test_off_restores_exact_v7_without_migrating_older_runs(loading_env, monkeypatch, explicit):
    run = make_run(loading_env, explicit=explicit)
    assert server_mod._ensure_explicit_skill_load(run) is (explicit != "missing")
    monkeypatch.setattr(server_mod, "_SKILL_MODEL_LOADING_ENABLED", False)
    monkeypatch.setattr(server_mod, "_SKILL_IMMUTABLE_ADMISSION_ENABLED", False)
    record = server_mod._agent_run_record(run)
    restored = server_mod._agent_run_from_record(record, immutable_skill_reader=loading_env[-1])
    assert snapshot(restored) == snapshot(run)
    assert server_mod._agent_run_record(restored)["version"] == 7
    with pytest.raises(server_mod.SkillActivationError, match="disabled"):
        make_run(loading_env)
    from tests.test_skill_runtime_v2_agentrun import _run
    older = _run(loading_env[-1], explicit="ledger")
    assert server_mod._agent_run_record(older)["version"] == 6
    failed = call(older, "use_skill", {"name": "ledger", "role": "owner"}, "old-new-argument")
    assert failed["result"]["errorCode"] == "skill_loading_protocol_required"
    assert server_mod._agent_run_record(older)["version"] == 6


def test_mixed_batch_rejects_sibling_write_without_running_it(loading_env):
    run = make_run(loading_env)
    raw = [{"id": key, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
           for key, name, args in (("write", "write_file", {"path": "must-not-exist", "content": "no"}),
                                  ("load", "use_skill", {"name": "ledger", "role": "owner"}))]
    run["pending_tool_calls"] = server_mod._normalize_agent_tool_calls(run, raw, 1)
    run["status"] = "tools"
    server_mod._execute_agent_pending_tools(run)
    assert not (loading_env[2] / "must-not-exist").exists()
    assert not run["active_skill_names"]
    assert all(item["result"]["ok"] is False for item in run["tool_executions"].values())


@pytest.mark.parametrize("field", ["pending_authorization", "pending_input", "pending_skill_evidence", "active_process"])
def test_pending_boundaries_cannot_be_replaced_by_loading(loading_env, field):
    run = make_run(loading_env)
    before = snapshot(run)
    run["pending_tool_calls"] = [{"id": "load"}]
    sentinel = {"unchanged": True}
    run[field] = sentinel
    with pytest.raises(skill_loading.SkillLoadingError, match="standalone"):
        server_mod._execute_agent_skill_load(run, {"name": "ledger", "role": "owner"}, "load")
    assert run[field] is sentinel and snapshot(run) == before


def test_concurrent_same_call_returns_one_original_receipt(loading_env):
    run = make_run(loading_env)
    run["pending_tool_calls"] = [{"id": "load"}]
    execution = {"name": "use_skill", "arguments": '{"name":"ledger","role":"owner"}', "status": "prepared",
                 "skillLoadCount": 0, "skillExecutionContext": {"version": 1, "dataRootId": run["skill_loading"]["registry"]["dataRootId"], "skills": []}}
    run["tool_executions"]["load"] = execution
    gate = threading.Barrier(2)
    def load():
        gate.wait(timeout=5)
        return server_mod._execute_agent_skill_load(run, {"name": "ledger", "role": "owner"}, "load", execution=execution)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: load(), range(2)))
    assert results[0] == results[1] and results[0]["newlyLoaded"] is True
    assert len(run["skill_loading"]["loads"]) == 1
    assert server_mod.read_json(server_mod._agent_run_path(run["id"]), None)["skillLoading"] == run["skill_loading"]


@pytest.mark.parametrize("failure", ["before", "after", "uncertain"])
def test_atomic_persist_failure_and_restart_never_create_half_load(loading_env, monkeypatch, failure):
    run = make_run(loading_env)
    before = snapshot(run)
    original_persist, original_read = server_mod._persist_agent_run, server_mod.read_json
    hit = []
    def persist(value):
        if value["skill_loading"]["loads"] and not hit:
            hit.append(True)
            if failure != "before":
                original_persist(value)
            raise OSError("injected atomic write boundary")
        return original_persist(value)
    def read(path, default=None):
        if failure == "uncertain" and hit and Path(path) == server_mod._agent_run_path(run["id"]):
            raise OSError("readback unavailable")
        return original_read(path, default)
    with monkeypatch.context() as patch:
        patch.setattr(server_mod, "_persist_agent_run", persist)
        patch.setattr(server_mod, "read_json", read)
        if failure == "uncertain":
            with pytest.raises(skill_loading.SkillLoadingError, match="uncertain"):
                call(run, "use_skill", {"name": "ledger", "role": "owner"})
            with pytest.raises(skill_loading.SkillLoadingError, match="uncertain"):
                server_mod._resume_agent_run(run, [])
        else:
            execution = call(run, "use_skill", {"name": "ledger", "role": "owner"})
            assert execution["result"]["ok"] is (failure == "after")
    if failure == "before":
        assert snapshot(run) == before
    record = original_read(server_mod._agent_run_path(run["id"]), None)
    restored = server_mod._agent_run_from_record(record, immutable_skill_reader=loading_env[-1])
    assert bool(restored["active_skill_names"]) is (failure != "before")
    assert len(restored["skill_loading"]["loads"]) == (failure != "before")
    if failure == "uncertain":
        with pytest.raises(skill_loading.SkillLoadingError, match="uncertain"):
            original_persist(run)
        assert restored["tool_executions"]["call-1"]["result"]["bodyLoaded"] is True


@pytest.mark.parametrize("loading_env", [{"ledger": {"tools": ["use_skill", "read_file"]},
                                          "refine": {"tools": ["use_skill", "write_file"]}}], indirect=True)
def test_late_loading_only_intersects_permissions_and_rejects_removed_tool(loading_env):
    run = make_run(loading_env)
    call(run, "use_skill", {"name": "ledger", "role": "owner"}, "owner")
    assert skill_loading.effective_tools(run["skill_loading"]) == ["use_skill", "read_file"]
    call(run, "use_skill", {"name": "refine", "role": "modifier"}, "modifier")
    assert skill_loading.effective_tools(run["skill_loading"]) == ["use_skill"]
    result = call(run, "write_file", {"path": "forbidden", "content": "x"}, "write")
    assert result["result"]["ok"] is False
    assert not (loading_env[2] / "forbidden").exists()


def test_catalog_change_fails_new_load_but_pinned_body_and_retry_survive(loading_env):
    from tests.test_skill_store_management import apply
    data, bundle, _workspace, reader = loading_env
    run = make_run(loading_env)
    call(run, "use_skill", {"name": "ledger", "role": "owner"}, "owner")
    before = snapshot(run)
    with data_dir_owner.acquire_data_dir_owner(data) as owner:
        manager = skill_store_management.SkillStoreManager(skill_store.SkillStore(data, bundle, write_enabled=True), owner=owner)
        apply(manager, "convert", {"kind": "convert-v2"})
        iid = run["skill_loading"]["loads"][0]["capture"]["installationId"]
        apply(manager, "disable", {"kind": "set-enabled", "installationId": iid, "enabled": False})
    retry = call(run, "use_skill", {"name": "ledger", "role": "owner"}, "retry")
    assert retry["result"]["ok"] is True and retry["result"]["newlyLoaded"] is False
    refused = call(run, "use_skill", {"name": "refine", "role": "modifier"}, "modifier")
    assert refused["result"]["errorCode"] == "skill_loading_catalog_changed"
    restored = server_mod._agent_run_from_record(server_mod._agent_run_record(run), immutable_skill_reader=reader)
    assert snapshot(restored) == before


def test_budget_rejection_preserves_previous_body_tools_and_receipts(loading_env, monkeypatch):
    run = make_run(loading_env)
    before = snapshot(run)
    monkeypatch.setattr(server_mod, "_agent_estimate_text_tokens", lambda _: 10**9)
    failed = call(run, "use_skill", {"name": "ledger", "role": "owner"})
    assert failed["result"]["errorCode"] == "skill_loading_budget_exceeded"
    assert snapshot(run) == before


@pytest.mark.parametrize("tamper", ["body", "receipt", "prefix", "tools", "protocol", "catalog", "policy", "outer", "missing-receipt"])
def test_invalid_loading_records_fail_closed(loading_env, tamper):
    run = make_run(loading_env)
    call(run, "use_skill", {"name": "ledger", "role": "owner"})
    record = server_mod._agent_run_record(run)
    item = record["skillLoading"]["loads"][0]
    if tamper == "body": item["capture"]["body"] += "forged"
    if tamper == "receipt": item["receiptId"] = "sl1_" + "0" * 64
    if tamper == "prefix": record["toolExecutions"]["call-1"]["skillLoadCount"] = 0
    if tamper == "tools": record["tools"] = []
    if tamper == "protocol": record["skillLoading"]["protocol"] = "future"
    if tamper == "catalog": record["skillLoading"]["catalog"][0]["revisionId"] = "unknown"
    if tamper == "policy": item["capture"]["descriptor"]["toolPolicy"]["mode"] = "allow-everything"
    if tamper == "outer": record["version"] = 6
    if tamper == "missing-receipt": record["toolExecutions"] = {}
    with pytest.raises(ValueError):
        server_mod._agent_run_from_record(record, immutable_skill_reader=loading_env[-1])


EVIDENCE = {"schemaVersion": 2, "requirements": [{"id": "read", "type": "tool_execution", "tool": "read_file", "minCount": 1}],
            "enforcement": {"schemaVersion": 2, "mode": "owner_completion_once", "activationKinds": ["automatic", "explicit"]}}


@pytest.mark.parametrize("loading_env", [{"ledger": {"evidence": EVIDENCE}}], indirect=True)
def test_old_tool_results_do_not_satisfy_new_owner_and_modifier_does_not_reset_plan(loading_env, monkeypatch):
    monkeypatch.setattr(server_mod, "_SKILL_COMPLETION_ENFORCEMENT_ENABLED", True)
    run = make_run(loading_env)
    call(run, "read_file", {"path": "input.txt"}, "early")
    call(run, "use_skill", {"name": "ledger", "role": "owner"}, "owner")
    plan = copy.deepcopy(run["skill_completion_enforcement"])
    assert plan["phase"] == "armed"
    outcome = skill_outcome.project_immutable_skill_outcome(run["skill_lifecycle"], run["tool_executions"], run["id"], "active")
    assert outcome["skills"][0]["requirements"][0]["acceptedSucceeded"] == 0
    call(run, "read_file", {"path": "input.txt"}, "late")
    call(run, "use_skill", {"name": "refine", "role": "modifier"}, "modifier")
    outcome = skill_outcome.project_immutable_skill_outcome(run["skill_lifecycle"], run["tool_executions"], run["id"], "active")
    assert outcome["skills"][0]["requirements"][0]["acceptedSucceeded"] == 1
    assert run["skill_completion_enforcement"] == plan
    retained = server_mod._agent_compaction_plan(run["messages"] + [{"role": "assistant", "content": "large " * 1000}])["retainedMessages"]
    assert retained[0] == run["messages"][0]


@pytest.mark.parametrize("loading_env", [{"ledger": {"tools": ["read_file"], "preference": True},
                                          "refine": {"tools": ["task"], "preference": True}}], indirect=True)
@pytest.mark.parametrize("explicit_delegation", [False, True])
def test_task_permission_preserves_legacy_intent_and_never_returns_later(loading_env, explicit_delegation):
    run = make_run(loading_env, tools=TOOLS + ["task"],
                   message="Use parallel agents to prepare a report" if explicit_delegation else "Prepare a report")
    assert run["skill_loading"]["delegationRequested"] is explicit_delegation
    call(run, "use_skill", {"name": "ledger", "role": "owner"}, "owner")
    assert ("task" in skill_loading.effective_tools(run["skill_loading"])) is explicit_delegation
    call(run, "use_skill", {"name": "refine", "role": "modifier"}, "modifier")
    restored = server_mod._agent_run_from_record(server_mod._agent_run_record(run), immutable_skill_reader=loading_env[-1])
    assert ("task" in skill_loading.effective_tools(restored["skill_loading"])) is explicit_delegation


@pytest.mark.parametrize("loading_env", [{"ledger": {"evidence": EVIDENCE},
                                          "refine": {"tools": ["use_skill"]}}], indirect=True)
def test_modifier_cannot_remove_an_existing_completion_obligation(loading_env, monkeypatch):
    monkeypatch.setattr(server_mod, "_SKILL_COMPLETION_ENFORCEMENT_ENABLED", True)
    run = make_run(loading_env)
    call(run, "use_skill", {"name": "ledger", "role": "owner"}, "owner")
    before = snapshot(run)
    result = call(run, "use_skill", {"name": "refine", "role": "modifier"}, "modifier")
    assert result["result"]["ok"] is False
    assert snapshot(run) == before


@pytest.mark.parametrize("loading_env", [{name: {} for name in ("writing-plans", "executing-plans", "dispatching-parallel-agents", "subagent-driven-development")}], indirect=True)
def test_previously_explicit_only_skills_are_normal_model_choices_in_v7(loading_env):
    from code_runtime.skill_registry import EXPLICIT_ONLY_SKILLS
    run = make_run(loading_env)
    assert EXPLICIT_ONLY_SKILLS.issubset(item["name"] for item in run["skill_loading"]["catalog"])
    for index, name in enumerate(sorted(EXPLICIT_ONLY_SKILLS)):
        natural = make_run(loading_env)
        loaded = call(natural, "use_skill", {"name": name, "role": "owner"}, f"load-{index}")
        assert loaded["result"]["bodyLoaded"] is True
        explicit = make_run(loading_env, explicit=name)
        assert server_mod._ensure_explicit_skill_load(explicit)
        assert explicit["active_skill_names"] == [name]


@pytest.mark.parametrize("tool", ["use_skill", "read_file", "run_command", "task"])
def test_cancel_before_execution_has_a_valid_loading_prefix(loading_env, tool):
    run = make_run(loading_env, tools=TOOLS + ["task"])
    args = {"name": "ledger", "role": "owner"} if tool == "use_skill" else {"path": "input.txt"} if tool == "read_file" else {"command": "echo unused"} if tool == "run_command" else {"prompt": "unused"}
    run["pending_tool_calls"] = server_mod._normalize_agent_tool_calls(run, [{"id": "cancel-me", "type": "function", "function": {"name": tool, "arguments": json.dumps(args)}}], 1)
    server_mod._cancel_agent_run(run["id"])
    restored = server_mod._agent_run_from_record(server_mod._agent_run_record(run), immutable_skill_reader=loading_env[-1])
    assert restored["status"] == "cancelled"
    assert restored["tool_executions"]["cancel-me"]["skillLoadCount"] == 0
    assert not restored["active_skill_names"]


def test_mixed_load_and_delegation_cannot_launch_a_child(loading_env):
    run = make_run(loading_env, tools=TOOLS + ["task"], message="Use parallel agents")
    raw = [{"id": key, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
           for key, name, args in (("child", "task", {"prompt": "must not launch"}),
                                  ("load", "use_skill", {"name": "ledger", "role": "owner"}))]
    run["pending_tool_calls"] = server_mod._normalize_agent_tool_calls(run, raw, 1)
    with mock.patch.object(server_mod, "_ensure_agent_delegation_child", side_effect=AssertionError("child launched")) as start:
        server_mod._execute_agent_pending_tools(run)
    start.assert_not_called()
    assert run["tool_executions"]["child"]["result"]["ok"] is False
    restored = server_mod._agent_run_from_record(server_mod._agent_run_record(run), immutable_skill_reader=loading_env[-1])
    assert not restored["active_skill_names"]


def test_protocol_controls_explicit_only_ui_hint_without_changing_legacy_mode():
    script = r'''
global.window = {Code:{features:{}}};
require("./src/features/skills-memory.js");
const list = {innerHTML:"", querySelectorAll:() => []};
let enabled = false;
const feature = window.Code.features.skillsMemory.createSkillsMemoryFeature({
  state:{skills:[{name:"writing-plans", description:"Planning"}], disabledSkills:new Set()},
  apiJson:async () => ({}), isModelSkillLoadingEnabled:() => enabled,
  document:{getElementById:() => list},
});
feature.refreshLoadingProtocol();
const legacy = list.innerHTML;
enabled = true; feature.refreshLoadingProtocol();
const modern = list.innerHTML;
enabled = false; feature.refreshLoadingProtocol();
process.stdout.write(JSON.stringify({legacy, modern, off:list.innerHTML}));
'''
    result = subprocess.run(["node", "-e", script], cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=True)
    data = json.loads(result.stdout)
    assert "skill-explicit-badge" in data["legacy"]
    assert "skill-explicit-badge" not in data["modern"]
    assert "writing-plans" in data["modern"]
    assert data["off"] == data["legacy"]
