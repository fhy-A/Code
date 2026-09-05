"""AgentRun v6 immutable Skill runtime and recovery integration."""
import copy
import json
from pathlib import Path
import shutil
from unittest import mock

import pytest

import server as server_mod
from code_runtime import skill_revisions
from code_runtime import skill_runtime_v2
from code_runtime import skill_store
from code_runtime.skill_activation import SKILL_PROMPT_MARKER
from tests import test_skill_admission as admission_fixture


def _runtime_fixture(tmp_path):
    data, bundle, _registry = admission_fixture._fixture(tmp_path)
    shutil.rmtree(data / skill_store.STORE_DIRECTORY)
    for root in (data / "skills", bundle):
        path = root / "xlsx" / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "allowed-tools: read_file, write_file",
            "allowed-tools: read_file, write_file, run_command, use_skill, check_skill_dependencies, read_skill_resource, task",
        )
        path.write_text(text, encoding="utf-8", newline="\n")
    catalog = skill_revisions.build_bundled_catalog(bundle, {
        "document-design": "code.bundle/document-design",
        "xlsx": "code.bundle/xlsx",
    })
    skill_store.SkillStore(data, bundle, write_enabled=True).bootstrap(catalog)
    return data, bundle, skill_store.SkillStoreReader(data)


@pytest.fixture
def runtime_env(tmp_path, monkeypatch):
    data, bundle, reader = _runtime_fixture(tmp_path)
    monkeypatch.setattr(server_mod, "DATA_DIR", data)
    monkeypatch.setattr(server_mod, "SKILLS_DIR", tmp_path / "mutable-must-not-be-read")
    monkeypatch.setattr(server_mod, "_SKILL_ACTIVATION_ENABLED", False)
    monkeypatch.setattr(server_mod, "_MODEL_ROUTE_REGISTRY_ENABLED", False)
    with server_mod._agent_run_lock:
        server_mod._agent_runs.clear()
    yield data, bundle, reader
    with server_mod._agent_run_lock:
        server_mod._agent_runs.clear()


def _run(reader, *, message="xlsx", explicit="xlsx", permission="read", tools=None, request_id=""):
    names = tools or [
        "read_file", "write_file", "run_command", "use_skill",
        "check_skill_dependencies", "read_skill_resource",
    ]
    return server_mod._create_agent_run(
        "",
        {
            "model": "test-model",
            "messages": [
                {"role": "system", "content": f"base\n\n{SKILL_PROMPT_MARKER}\n\npermission"},
                {"role": "user", "content": message},
            ],
        },
        "http://127.0.0.1:9",
        [],
        {"schemaVersion": 1, "names": names},
        4,
        permission,
        start_worker=False,
        client_request_id=request_id,
        run_kind="foreground",
        skill_activation_request={
            "schemaVersion": 1, "explicitSkill": explicit, "disabledNames": [],
        },
        _immutable_skill_reader=reader,
    )


def _call(run, name, arguments, call_id="call-1"):
    call = server_mod._normalize_agent_tool_calls(run, [{
        "index": 0,
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }], 1)[0]
    run["pending_tool_calls"] = [call]
    run["status"] = "tools"
    server_mod._execute_agent_pending_tools(run)
    return run["tool_executions"].get(call_id), call


def test_v6_writer_no_match_and_terminal_reader_free(runtime_env):
    _data, _bundle, reader = runtime_env
    run = _run(reader, message="hello world", explicit="")
    record = server_mod._agent_run_record(run)
    assert record["version"] == 6
    assert record["skillLifecycle"]["schemaVersion"] == 2
    assert record["skillLifecycle"]["activation"]["outcome"] == "none"
    assert record["activeSkillNames"] == []
    assert record["activeSkillDependencies"] == {"version": 2, "skills": []}
    assert record["skillEvidence"] == {"version": 2, "skills": []}
    assert record["skillRuntimeBindings"] == {"version": 2, "bindings": []}
    assert record["skillOutcome"]["version"] == 3

    unavailable = server_mod._agent_run_from_record(copy.deepcopy(record))
    assert unavailable["status"] == "waiting_recovery"
    assert unavailable["skill_recovery"]["dataRootId"] == record["skillLifecycle"]["activation"]["registry"]["dataRootId"]

    run["status"] = "completed"
    run["result"] = {"content": "done"}
    terminal_record = server_mod._agent_run_record(run)
    restored = server_mod._agent_run_from_record(terminal_record)
    assert restored["status"] == "completed"
    assert restored["skill_recovery"] is None


def test_v6_no_match_client_request_is_idempotent(runtime_env):
    _data, _bundle, reader = runtime_env
    first = _run(reader, message="hello world", explicit="", request_id="immutable-no-match")
    second = _run(reader, message="hello world", explicit="", request_id="immutable-no-match")
    assert second is first
    assert server_mod._agent_run_record(second)["version"] == 6


def test_v6_exact_consumers_never_call_mutable_paths(runtime_env):
    _data, _bundle, reader = runtime_env
    run = _run(reader)
    forbidden = (
        mock.patch.object(server_mod, "read_skill", side_effect=AssertionError("mutable read_skill")),
        mock.patch.object(server_mod, "resolve_skill_manifest", side_effect=AssertionError("mutable manifest")),
        mock.patch.object(server_mod, "resolve_skill_resources_with_identity", side_effect=AssertionError("mutable resources")),
    )
    for patcher in forbidden:
        patcher.start()
    try:
        with mock.patch.object(reader, "read_registry", side_effect=AssertionError("active pointer")):
            snapshot = server_mod._agent_lifecycle_skill_snapshot(run, "xlsx")
            assert snapshot["immutable"] is True
            assert snapshot["runtimeResources"]["source"] == "immutable"
            status = server_mod._agent_lifecycle_dependency_status(snapshot, "create")
            assert status["installGuidance"]["selectedCapability"] == "create"
            use_execution, _ = _call(run, "use_skill", {"name": "xlsx"}, "use-1")
            assert use_execution["result"]["ok"] is True
            assert use_execution["result"]["runtimeResources"]["source"] == "immutable"
            assert run["skill_runtime_bindings"]["xlsx"]["version"] == 2
            execution, _ = _call(
                run, "read_skill_resource", {"skill": "xlsx", "file": "private.txt"},
                "resource-1",
            )
            result = execution["result"]
            assert result["ok"] is True
            assert "secret-value" in result["content"]
            assert execution["skillExecutionContext"]["skills"][0]["resource"]["contentHash"]
            binding = run["skill_lifecycle"]["access"]["resourceBindings"][0]
            assert binding["kind"] == "text"
            assert binding["installationId"] == snapshot["selected"]["installationId"]
            assert binding["revisionId"] == snapshot["selected"]["revisionId"]
    finally:
        for patcher in reversed(forbidden):
            patcher.stop()


def test_execution_context_is_durable_before_command_and_completed_reuses(runtime_env, tmp_path):
    data, _bundle, reader = runtime_env
    run = _run(reader, permission="bypass")
    check, _ = _call(
        run, "check_skill_dependencies", {"name": "xlsx", "capability": "create"},
        "check-1",
    )
    assert check["result"]["ok"] is True
    assert run["skill_runtime_bindings"]["xlsx"]["version"] == 2
    with mock.patch.object(server_mod, "read_skill", side_effect=AssertionError("mutable")), mock.patch.object(
        server_mod, "resolve_skill_manifest", side_effect=AssertionError("mutable"),
    ), mock.patch.object(
        server_mod, "resolve_skill_resources_with_identity", side_effect=AssertionError("mutable"),
    ):
        assert server_mod._agent_prepare_skill_runtime_environment(run)["ok"] is True
    resource_path = server_mod._agent_lifecycle_skill_snapshot(run, "xlsx")["runtimeResources"]["resources"][0]["path"]

    observations = []

    def execute(arguments, **_options):
        durable = server_mod._agent_run_record(run)["toolExecutions"]["command-1"]
        observations.append(copy.deepcopy(durable))
        return {
            "ok": True, "action": "run_command", "command": arguments["command"],
            "cwd": str(run["cwd"]), "exitCode": 0, "stdout": "ok", "stderr": "",
        }

    with mock.patch.object(server_mod, "execute_run_command_tool", side_effect=execute) as invoked:
        execution, call = _call(
            run, "run_command", {"command": f'python "{resource_path}" out.xlsx', "description": "probe"},
            "command-1",
        )
        assert execution["result"]["ok"] is True
        assert observations[0]["skillExecutionContext"]["version"] == 1
        assert observations[0]["skillExecutionContext"]["dataRootId"] == run["skill_lifecycle"]["activation"]["registry"]["dataRootId"]
        assert observations[0]["status"] == "running"
        original_arguments = execution["arguments"]
        run["pending_tool_calls"] = [call]
        run["status"] = "tools"
        server_mod._execute_agent_pending_tools(run)
        assert invoked.call_count == 1
        moved = tmp_path / "completed-move"
        moved.mkdir()
        shutil.copytree(data / skill_store.STORE_DIRECTORY, moved / skill_store.STORE_DIRECTORY)
        run["_immutable_skill_reader"] = skill_store.SkillStoreReader(moved)
        run["pending_tool_calls"] = [call]
        run["status"] = "tools"
        server_mod._execute_agent_pending_tools(run)
        assert invoked.call_count == 1
        assert execution["arguments"] == original_arguments
    public = server_mod._agent_snapshot(run)
    public_skill_fields = json.dumps({
        "evidence": public["skillEvidence"],
        "bindings": public["skillRuntimeBindings"],
    })
    assert "installationId" not in public_skill_fields
    assert "revisionId" not in public_skill_fields


def test_context_persist_failure_rolls_back_without_dispatch(runtime_env):
    _data, _bundle, reader = runtime_env
    run = _run(reader, permission="bypass")
    call = server_mod._normalize_agent_tool_calls(run, [{
        "index": 0, "id": "write-1", "type": "function",
        "function": {"name": "write_file", "arguments": json.dumps({"path": "x.txt", "content": "x"})},
    }], 1)[0]
    run["pending_tool_calls"] = [call]
    run["status"] = "tools"
    with mock.patch.object(server_mod, "_persist_agent_run", side_effect=OSError("disk full")), mock.patch.object(
        server_mod, "execute_registered_tool",
    ) as dispatched:
        with pytest.raises(OSError, match="disk full"):
            server_mod._execute_agent_pending_tools(run)
    assert "write-1" not in run["tool_executions"]
    dispatched.assert_not_called()


def test_invalid_v6_tool_arguments_get_empty_exact_context(runtime_env):
    _data, _bundle, reader = runtime_env
    run = _run(reader)
    call = server_mod._normalize_agent_tool_calls(run, [{
        "index": 0, "id": "invalid-resource", "type": "function",
        "function": {"name": "read_skill_resource", "arguments": "{broken"},
    }], 1)[0]
    run["pending_tool_calls"] = [call]
    run["status"] = "tools"
    server_mod._execute_agent_pending_tools(run)
    execution = run["tool_executions"]["invalid-resource"]
    assert execution["result"]["ok"] is False
    assert execution["skillExecutionContext"]["skills"] == []


def test_text_access_persist_failure_returns_no_sensitive_content(runtime_env):
    _data, _bundle, reader = runtime_env
    run = _run(reader)
    original = server_mod._persist_agent_run
    calls = 0

    def persist(target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("access persist failed")
        return original(target)

    with mock.patch.object(server_mod, "_persist_agent_run", side_effect=persist):
        execution, _ = _call(
            run, "read_skill_resource", {"skill": "xlsx", "file": "private.txt"},
            "resource-fail",
        )
    assert execution["result"]["ok"] is False
    assert execution["result"]["errorCode"] == "skill_lifecycle_persist_failed"
    assert "content" not in execution["result"]
    assert run["skill_lifecycle"]["access"]["resourceBindings"] == []


def test_text_resource_limit_rejects_before_binding_or_content(runtime_env):
    data, bundle, _reader = runtime_env
    shutil.rmtree(data / skill_store.STORE_DIRECTORY)
    oversized = "x" * (server_mod.MAX_TOOL_READ_BYTES + 1)
    for root in (data / "skills", bundle):
        (root / "xlsx" / "large.txt").write_text(oversized, encoding="utf-8")
    catalog = skill_revisions.build_bundled_catalog(bundle, {
        "document-design": "code.bundle/document-design",
        "xlsx": "code.bundle/xlsx",
    })
    skill_store.SkillStore(data, bundle, write_enabled=True).bootstrap(catalog)
    run = _run(skill_store.SkillStoreReader(data))
    execution, _ = _call(
        run, "read_skill_resource", {"skill": "xlsx", "file": "large.txt"},
        "large-resource",
    )
    assert execution["result"]["ok"] is False
    assert execution["result"]["errorCode"] == "skill_revision_resource_too_large"
    assert "content" not in execution["result"]
    assert run["skill_lifecycle"]["access"]["resourceBindings"] == []


def test_runtime_binding_persist_failure_rolls_back_and_hides_paths(runtime_env):
    _data, _bundle, reader = runtime_env
    run = _run(reader)
    original = server_mod._persist_agent_run
    calls = 0

    def persist(target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("binding persist failed")
        return original(target)

    with mock.patch.object(server_mod, "_persist_agent_run", side_effect=persist):
        execution, _ = _call(run, "use_skill", {"name": "xlsx"}, "use-fail")
    assert execution["result"]["ok"] is False
    assert execution["result"]["errorCode"] == "skill_dependency_binding_persist_failed"
    assert "runtimeResources" not in execution["result"]
    assert run["skill_runtime_bindings"] == {}


def test_runtime_preflight_rejects_unpersisted_new_executor(runtime_env):
    data, _bundle, reader = runtime_env
    run = _run(reader)
    execution, _ = _call(
        run, "check_skill_dependencies", {"name": "xlsx", "capability": "create"},
        "check-runtime",
    )
    assert execution["result"]["ok"] is True
    fake = data / "runtime" / "python" / "Scripts" / "python.exe"
    fake.parent.mkdir(parents=True, exist_ok=True)
    fake.write_bytes(b"fake")
    run["skill_runtime_bindings"]["xlsx"]["runtime"] = {
        "python": {"source": "managed", "executable": str(fake)},
    }
    result = server_mod._agent_prepare_skill_runtime_environment(run)
    assert result["ok"] is False
    assert result["errorCode"] == "skill_dependency_runtime_stale"
    assert run["skill_runtime_bindings"] == {}


def test_skill_recovery_round_trip_preserves_authorization_gate(runtime_env):
    _data, _bundle, reader = runtime_env
    run = _run(reader, permission="accept")
    execution, _call_value = _call(
        run, "write_file", {"path": "book.xlsx", "content": "x"}, "write-1",
    )
    assert execution["status"] == "waiting_authorization"
    assert run["status"] == "waiting_authorization"
    pending = copy.deepcopy(run["pending_authorization"])
    record = server_mod._agent_run_record(run)

    unavailable = server_mod._agent_run_from_record(copy.deepcopy(record))
    assert unavailable["status"] == "waiting_recovery"
    assert unavailable["skill_recovery"]["priorState"]["status"] == "waiting_authorization"
    with pytest.raises(ValueError, match="exact immutable Skill revision"):
        server_mod._resume_agent_run(unavailable, [])
    recovery_record = server_mod._agent_run_record(unavailable)
    assert recovery_record["skillRecovery"]["pendingGate"]["kind"] == "authorization"
    repeated = server_mod._agent_run_from_record(copy.deepcopy(recovery_record))
    assert server_mod._agent_run_record(repeated)["skillRecovery"] == recovery_record["skillRecovery"]

    restored = server_mod._agent_run_from_record(
        copy.deepcopy(recovery_record), immutable_skill_reader=reader,
    )
    assert restored["status"] == "waiting_authorization"
    assert restored["skill_recovery"] is None
    assert {key: value for key, value in restored["pending_authorization"].items() if key != "submitting"} == {
        key: value for key, value in pending.items() if key != "submitting"
    }
    assert restored["tool_executions"]["write-1"]["status"] == "waiting_authorization"


@pytest.mark.parametrize("failure", ["missing", "corrupt"])
def test_fixed_object_failure_waits_and_recovers_same_revision(runtime_env, tmp_path, failure):
    data, _bundle, reader = runtime_env
    run = _run(reader)
    record = server_mod._agent_run_record(run)
    revision = record["skillLifecycle"]["activation"]["selected"][0]["revisionId"]
    digest = revision.removeprefix("sha256:")
    object_path = data / skill_store.STORE_DIRECTORY / "objects" / "sha256" / digest[:2] / digest
    backup = tmp_path / "saved-object"
    if failure == "missing":
        shutil.move(str(object_path), str(backup))
    else:
        skill_path = object_path / "content" / "SKILL.md"
        backup.write_bytes(skill_path.read_bytes())
        skill_path.write_bytes(backup.read_bytes() + b"corrupt")
    unavailable = server_mod._agent_run_from_record(
        copy.deepcopy(record), immutable_skill_reader=reader,
    )
    assert unavailable["status"] == "waiting_recovery"
    assert unavailable["skill_recovery"]["errorCode"] == "skill_revision_unavailable"
    recovery_record = server_mod._agent_run_record(unavailable)
    if failure == "missing":
        shutil.move(str(backup), str(object_path))
    else:
        (object_path / "content" / "SKILL.md").write_bytes(backup.read_bytes())
    restored = server_mod._agent_run_from_record(
        recovery_record, immutable_skill_reader=reader,
    )
    assert restored["status"] == "waiting_credentials"
    assert restored["skill_recovery"] is None


def test_get_run_persists_and_clears_skill_recovery_idempotently(runtime_env, tmp_path):
    data, _bundle, reader = runtime_env
    run = _run(reader, request_id="recovery-get-run")
    run_id = run["id"]
    record = server_mod._agent_run_record(run)
    revision = record["skillLifecycle"]["activation"]["selected"][0]["revisionId"]
    digest = revision.removeprefix("sha256:")
    object_path = data / skill_store.STORE_DIRECTORY / "objects" / "sha256" / digest[:2] / digest
    backup = tmp_path / "get-run-object"
    shutil.move(str(object_path), str(backup))
    with server_mod._agent_run_lock:
        server_mod._agent_runs.clear()
    unavailable = server_mod._get_agent_run(run_id)
    assert unavailable["status"] == "waiting_recovery"
    assert "skillRecovery" in server_mod.read_json(server_mod._agent_run_path(run_id), {})
    shutil.move(str(backup), str(object_path))
    restored = server_mod._get_agent_run(run_id, immutable_skill_reader=reader)
    assert restored["status"] == "waiting_credentials"
    assert restored["skill_recovery"] is None
    assert "skillRecovery" not in server_mod.read_json(server_mod._agent_run_path(run_id), {})


@pytest.mark.parametrize("waiting", [
    "waiting_user_input", "waiting_skill_evidence", "waiting_credentials",
])
def test_skill_recovery_restores_each_prior_waiting_state(runtime_env, waiting):
    _data, _bundle, reader = runtime_env
    run = _run(reader)
    run["status"] = waiting
    run["resume_status"] = "model" if waiting == "waiting_credentials" else ""
    run["pending_input"] = None
    run["pending_authorization"] = None
    run["pending_skill_evidence"] = None
    if waiting == "waiting_user_input":
        run["pending_input"] = {"version": 1, "requestId": "input-1", "questions": []}
    elif waiting == "waiting_skill_evidence":
        owner = run["skill_lifecycle"]["activation"]["selected"][0]
        run["pending_skill_evidence"] = {
            "version": 2,
            "gateId": "skill-evidence-" + "a" * 40,
            "authority": skill_runtime_v2.authority_from_selected(owner, evidence=True),
            "candidateResult": {"content": "candidate", "finishReason": "stop", "usage": {}},
            "evidenceStatus": "partial",
            "missing": [{
                "id": "write", "tool": "write_file", "minCount": 1,
                "succeededCount": 0, "failedCount": 0,
            }],
            "createdAt": "2026-09-05T00:00:00Z",
        }
    record = server_mod._agent_run_record(run)
    unavailable = server_mod._agent_run_from_record(copy.deepcopy(record))
    recovery_record = server_mod._agent_run_record(unavailable)
    restored = server_mod._agent_run_from_record(
        recovery_record, immutable_skill_reader=reader,
    )
    assert restored["status"] == waiting
    assert restored["skill_recovery"] is None
    if waiting == "waiting_user_input":
        assert restored["pending_input"] == run["pending_input"]
    elif waiting == "waiting_skill_evidence":
        assert restored["pending_skill_evidence"] == run["pending_skill_evidence"]


@pytest.mark.parametrize("path_style", ["native", "slashes", "casefold"])
def test_prepared_command_with_old_resource_path_is_not_rewritten(runtime_env, tmp_path, path_style):
    data, _bundle, reader = runtime_env
    run = _run(reader, permission="accept")
    _call(run, "check_skill_dependencies", {"name": "xlsx", "capability": "create"}, "check-1")
    resource_path = server_mod._agent_lifecycle_skill_snapshot(run, "xlsx")["runtimeResources"]["resources"][0]["path"]
    command_path = {
        "native": resource_path,
        "slashes": resource_path.replace("\\", "/"),
        "casefold": resource_path.swapcase(),
    }[path_style]
    execution, call = _call(
        run, "run_command", {"command": f'python "{command_path}" out.xlsx', "description": "run pinned"},
        "command-1",
    )
    assert execution["status"] == "waiting_authorization"
    old_arguments = execution["arguments"]
    old_fingerprint = execution["fingerprint"]
    old_messages = copy.deepcopy(run["messages"])
    moved = tmp_path / "moved-profile"
    moved.mkdir()
    shutil.copytree(data / skill_store.STORE_DIRECTORY, moved / skill_store.STORE_DIRECTORY)
    run["_immutable_skill_reader"] = skill_store.SkillStoreReader(moved)
    with pytest.raises(skill_runtime_v2.ImmutableSkillRuntimeError) as raised:
        server_mod._agent_immutable_execution_identity(run, call, execution)
    assert raised.value.code == "skill_runtime_path_rebind_required"
    assert server_mod._execute_agent_pending_tools(run) is True
    assert execution["status"] == "completed"
    assert execution["result"]["errorCode"] == "skill_runtime_path_rebind_required"
    assert execution["result"]["notReplayed"] is True
    assert run["pending_authorization"] is None
    assert execution["arguments"] == old_arguments
    assert execution["fingerprint"] == old_fingerprint
    assert run["messages"][:len(old_messages)] == old_messages


def test_stale_skill_path_close_persist_failure_rolls_back_without_dispatch(runtime_env, tmp_path):
    data, _bundle, reader = runtime_env
    run = _run(reader, permission="accept")
    _call(run, "check_skill_dependencies", {"name": "xlsx", "capability": "create"}, "check-1")
    resource_path = server_mod._agent_lifecycle_skill_snapshot(run, "xlsx")["runtimeResources"]["resources"][0]["path"]
    execution, _call_value = _call(
        run, "run_command", {"command": f'python "{resource_path}" out.xlsx', "description": "run pinned"},
        "command-1",
    )
    assert execution["status"] == "waiting_authorization"
    moved = tmp_path / "persist-failure-move"
    moved.mkdir()
    shutil.copytree(data / skill_store.STORE_DIRECTORY, moved / skill_store.STORE_DIRECTORY)
    run["_immutable_skill_reader"] = skill_store.SkillStoreReader(moved)
    before = {
        "execution": copy.deepcopy(execution),
        "pendingToolCalls": copy.deepcopy(run["pending_tool_calls"]),
        "pendingAuthorization": copy.deepcopy(run["pending_authorization"]),
        "status": run["status"],
        "resumeStatus": run["resume_status"],
        "messages": copy.deepcopy(run["messages"]),
        "events": copy.deepcopy(run["events"]),
        "nextSeq": run["next_seq"],
    }
    with mock.patch.object(server_mod, "_persist_agent_run", side_effect=OSError("close persist failed")), mock.patch.object(
        server_mod, "execute_registered_tool",
    ) as dispatched:
        with pytest.raises(OSError, match="close persist failed"):
            server_mod._execute_agent_pending_tools(run)
    assert run["tool_executions"]["command-1"] == before["execution"]
    assert run["pending_tool_calls"] == before["pendingToolCalls"]
    assert run["pending_authorization"] == before["pendingAuthorization"]
    assert run["status"] == before["status"]
    assert run["resume_status"] == before["resumeStatus"]
    assert run["messages"] == before["messages"]
    assert run["events"] == before["events"]
    assert run["next_seq"] == before["nextSeq"]
    dispatched.assert_not_called()


def test_v6_context_tamper_rejected_and_missing_version_legacy_still_loads(runtime_env):
    _data, _bundle, reader = runtime_env
    run = _run(reader, permission="accept")
    _execution, _ = _call(
        run, "write_file", {"path": "book.xlsx", "content": "x"}, "write-1",
    )
    record = server_mod._agent_run_record(run)
    record["toolExecutions"]["write-1"]["skillExecutionContext"]["dataRootId"] = "dr1_" + "f" * 32
    with pytest.raises(server_mod.skill_lifecycle.SkillLifecycleError) as raised:
        server_mod._agent_run_from_record(record, immutable_skill_reader=reader)
    assert raised.value.code == "skill_execution_context_conflict"

    legacy = server_mod._create_agent_run(
        "", {"model": "test-model", "messages": [{"role": "user", "content": "plain"}]},
        "http://127.0.0.1:9", [], ["read_file"], 2, "read",
        start_worker=False, run_kind="internal",
    )
    legacy_record = server_mod._agent_run_record(legacy)
    assert legacy_record["version"] == 5
    legacy_record.pop("version")
    restored = server_mod._agent_run_from_record(legacy_record)
    assert restored["skill_lifecycle"] is None
    legacy["status"] = "waiting_user_input"
    legacy["pending_input"] = {"version": 1, "requestId": "legacy-input"}
    pending_record = server_mod._agent_run_record(legacy)
    pending_restored = server_mod._agent_run_from_record(pending_record)
    assert pending_restored["status"] == "waiting_user_input"
    assert pending_restored["pending_input"] == legacy["pending_input"]


def test_v6_unknown_nonreplayable_dispatch_is_closed_on_restart(runtime_env):
    _data, _bundle, reader = runtime_env
    run = _run(reader)
    context = skill_runtime_v2.build_execution_context(
        reader, run["skill_lifecycle"], "save_memory", {"content": "fact"},
        bindings={},
    )
    run["tool_executions"]["memory-1"] = {
        "name": "save_memory", "arguments": json.dumps({"content": "fact"}),
        "argumentAliases": [], "fingerprint": "b" * 64,
        "status": "dispatching", "outcome": "", "result": None,
        "error": "", "startedAt": "2026-09-05T00:00:00Z", "completedAt": "",
        "nonReplayable": True, "skillExecutionContext": context,
    }
    record = server_mod._agent_run_record(run)
    restored = server_mod._agent_run_from_record(
        record, immutable_skill_reader=reader,
    )
    execution = restored["tool_executions"]["memory-1"]
    assert execution["status"] == "completed"
    assert execution["result"]["unknownState"] is True
    assert execution["result"]["notReplayed"] is True


def test_completion_reconcile_and_dispatch_helper_keep_separate_boundaries(runtime_env):
    _data, _bundle, reader = runtime_env
    run = _run(reader)
    run["rounds"] = [{
        "round": 1, "outcome": "completed", "content": "candidate",
        "finishReason": "stop", "toolCalls": [],
    }]
    run["messages"].append({"role": "assistant", "content": "candidate"})
    plan = {"phase": "armed", "triggerRound": 0, "toolBatchCallIds": []}
    with mock.patch.object(
        server_mod, "_agent_skill_completion_evaluate",
        return_value=(plan, {"status": "recoverable"}),
    ), mock.patch.object(
        server_mod, "_agent_skill_completion_candidate", return_value="candidate-called",
    ) as candidate:
        assert server_mod._agent_skill_completion_reconcile(run) == "candidate-called"
    candidate.assert_called_once()

    execution = {
        "status": "prepared",
        "skillExecutionContext": {"version": 1},
    }
    with mock.patch.object(server_mod, "_persist_agent_run") as persisted:
        server_mod._agent_mark_immutable_nonreplayable_dispatch(run, execution)
    assert execution["status"] == "dispatching"
    assert execution["nonReplayable"] is True
    persisted.assert_called_once_with(run)


def test_v6_completion_repair_loop_and_terminal_projection_tamper(runtime_env, monkeypatch):
    data, bundle, _reader = runtime_env
    shutil.rmtree(data / skill_store.STORE_DIRECTORY)
    evidence = {
        "schemaVersion": 2,
        "requirements": [{
            "id": "write", "type": "artifact", "tool": "write_file",
            "minCount": 1, "artifactKind": "file",
        }],
        "enforcement": {
            "schemaVersion": 2, "mode": "owner_completion_once",
            "activationKinds": ["explicit"],
        },
    }
    for root in (data / "skills", bundle):
        (root / "xlsx" / "evidence.json").write_text(
            json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8", newline="\n",
        )
    catalog = skill_revisions.build_bundled_catalog(bundle, {
        "document-design": "code.bundle/document-design",
        "xlsx": "code.bundle/xlsx",
    })
    skill_store.SkillStore(data, bundle, write_enabled=True).bootstrap(catalog)
    reader = skill_store.SkillStoreReader(data)
    monkeypatch.setattr(server_mod, "_SKILL_COMPLETION_ENFORCEMENT_ENABLED", True)
    run = _run(reader, permission="bypass")
    assert run["skill_completion_enforcement"]["version"] == 2

    first_candidate = {"content": "draft", "finishReason": "stop", "usage": {}}
    run["rounds"].append({
        "round": 1, "outcome": "completed", "content": "draft",
        "finishReason": "stop", "toolCalls": [],
    })
    run["messages"].append({"role": "assistant", "content": "draft"})
    assert server_mod._agent_skill_completion_candidate(run, first_candidate) == "continue"
    assert run["skill_completion_enforcement"]["phase"] == "continuing"

    repair = server_mod._normalize_agent_tool_calls(run, [{
        "index": 0, "id": "repair-write", "type": "function",
        "function": {"name": "write_file", "arguments": json.dumps({
            "path": "artifact.txt", "content": "done",
        })},
    }], 2)[0]
    assert server_mod._agent_skill_completion_tool_batch(run, [repair]) == "continue"
    with mock.patch.object(server_mod, "execute_registered_tool", return_value={
        "ok": True, "action": "write_file", "path": "artifact.txt",
    }):
        assert server_mod._execute_agent_pending_tools(run) is True
    assert server_mod._agent_skill_completion_after_tools(run) == "continue"
    assert run["skill_completion_enforcement"]["phase"] == "finalizing"
    finalizing_record = server_mod._agent_run_record(run)
    finalizing_restore = server_mod._agent_run_from_record(
        copy.deepcopy(finalizing_record), immutable_skill_reader=reader,
    )
    assert finalizing_restore["skill_completion_enforcement"]["phase"] == "finalizing"
    assert finalizing_restore["tool_executions"]["repair-write"]["status"] == "completed"
    assert finalizing_restore["status"] == "waiting_credentials"
    assert finalizing_restore["resume_status"] == "tools"
    with mock.patch.object(server_mod, "_start_agent_worker"):
        server_mod._resume_agent_run(finalizing_restore, ["test-key"])
    assert finalizing_restore["status"] == "tools"
    finalizing_restore["status"] = "model"

    final_candidate = {"content": "final", "finishReason": "stop", "usage": {}}
    finalizing_restore["rounds"].append({
        "round": 2, "outcome": "completed", "content": "final",
        "finishReason": "stop", "toolCalls": [],
    })
    finalizing_restore["messages"].append({"role": "assistant", "content": "final"})
    with mock.patch.object(server_mod, "_persist_agent_session_context_resolution", return_value=False):
        assert server_mod._agent_skill_completion_candidate(finalizing_restore, final_candidate) == "done"
    assert finalizing_restore["status"] == "completed"
    assert finalizing_restore["skill_completion_enforcement"]["phase"] == "passed"
    record = server_mod._agent_run_record(finalizing_restore)
    assert record["skillOutcome"]["aggregateState"] == "satisfied"
    assert record["skillCompletionEnforcement"]["version"] == 2
    assert server_mod._agent_run_from_record(copy.deepcopy(record))["status"] == "completed"

    tampered = copy.deepcopy(record)
    tampered["skillOutcome"]["aggregateState"] = "observing"
    with pytest.raises(server_mod.skill_lifecycle.SkillLifecycleError) as raised:
        server_mod._agent_run_from_record(tampered)
    assert raised.value.code == "skill_lifecycle_projection_conflict"


def test_v6_goal_handoff_pauses_once_and_never_creates_successor(runtime_env):
    _data, _bundle, reader = runtime_env
    run = _run(reader)
    run["session_id"] = "session-v2"
    projection = {
        "revision": 7,
        "goal": {"goalId": "goal-v2", "gate": None},
    }
    goal_runtime = mock.Mock()

    def finish(target, status):
        target["status"] = status
        return True

    with mock.patch.object(server_mod, "_agent_goal_continuation_state", return_value=projection), mock.patch.object(
        server_mod, "goal_v2_runtime", return_value=goal_runtime,
    ), mock.patch.object(
        server_mod, "_session_archive_stop_fence_active", return_value=False,
    ), mock.patch.object(
        server_mod, "_finish_agent_run", side_effect=finish,
    ), mock.patch.object(server_mod, "_create_agent_run") as create_successor:
        assert server_mod._handoff_agent_goal_run(run, reason="soft_round_limit") is True
        assert server_mod._handoff_agent_goal_run(run, reason="soft_round_limit") is True
    create_successor.assert_not_called()
    goal_runtime.raise_gate.assert_called_once()
    assert run["result"]["continuationReasonCode"] == "skill_goal_continuation_unsupported"


def test_v6_child_strips_all_skill_authority_tools(runtime_env):
    _data, _bundle, reader = runtime_env
    run = _run(reader)
    run["tools"].append(server_mod._agent_registry_tool_definition("task"))
    call = {"id": "task-1", "arguments": {"prompt": "inspect only"}}
    execution = {}
    captured = {}

    def create(*args, **kwargs):
        captured["allowed"] = list(args[4])
        captured["definitions"] = [
            item["function"]["name"] for item in args[1]["tools"]
        ]
        return {"id": "child-1"}

    with mock.patch.object(server_mod, "_create_agent_run", side_effect=create), mock.patch.object(
        server_mod, "_start_agent_worker",
    ), mock.patch.object(server_mod, "_append_agent_event"):
        child, _prompt = server_mod._ensure_agent_delegation_child(run, call, execution)
    assert child["id"] == "child-1"
    for name in ("use_skill", "check_skill_dependencies", "read_skill_resource"):
        assert name not in captured["allowed"]
        assert name not in captured["definitions"]
    assert "read_file" in captured["allowed"]
