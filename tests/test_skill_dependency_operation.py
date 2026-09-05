"""Synthetic marker/containment contracts, including a real offline pip chain."""
import copy
import json
import os
import shutil
from pathlib import Path
import sys
import threading
import zipfile
from unittest import mock

import pytest

import server
from code_runtime import data_dir_owner, skill_dependency_operation as operation
from code_runtime import skill_management_api, skill_revisions, skill_store
from tests.test_skill_admission import _write_skill
from tests.test_skill_runtime_v2_agentrun import _run, _call


TARGET = {"dataRootId": "dr1_" + "a" * 32, "installationId": "si1_" + "b" * 32,
          "revisionId": "sha256:" + "c" * 64, "manifestHash": "sha256:" + "d" * 64, "capability": "create"}


def test_marker_requires_exit_then_exact_binding_and_never_replays(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    state = operation.DependencyOperation(root)
    assert state.read() is None
    assert list(root.iterdir()) == []
    with data_dir_owner.acquire_data_dir_owner(root) as owner:
        marker = state.begin(TARGET, "requester", {"steps": []}, owner)
        with pytest.raises(operation.DependencyOperationError, match="unknown"):
            operation.DependencyOperation(root).begin(TARGET, "new", {}, owner)
        state.exited(marker["operationId"], {"ok": False, "writerExited": False}, owner)
        assert state.read()["state"] == "running"
        with pytest.raises(operation.DependencyOperationError, match="not_settleable"):
            state.settle(TARGET, {"ready": True}, owner)
        state.exited(marker["operationId"], {"ok": False, "writerExited": True}, owner)
        with pytest.raises(operation.DependencyOperationError, match="target_conflict"):
            state.begin({**TARGET, "capability": "other"}, "new", {}, owner)
        state.settle(TARGET, {"target": TARGET, "runtime": {}, "checkedAt": "2026-09-05T00:00:00Z"}, owner)
        state.assert_available()
        assert state.read()["state"] == "settled"
    with pytest.raises(operation.DependencyOperationError, match="owner_required"):
        state.begin(TARGET, "new", {}, owner)


def test_corrupt_marker_or_interrupted_write_is_not_empty(tmp_path):
    state = operation.DependencyOperation(tmp_path)
    state.path.write_text('{"schema":"future"}')
    with pytest.raises(operation.DependencyOperationError, match="invalid"):
        state.read()
    (tmp_path / (operation.MARKER + ".tmp-evidence")).write_text("partial")
    with pytest.raises(operation.DependencyOperationError, match="interrupted"):
        state.read()


@pytest.mark.parametrize("state_name,result,binding", [
    ("exited", {}, {}),
    ("exited", {"ok": False, "writerExited": False}, {}),
    ("exited", {"ok": False, "writerExited": 1}, {}),
    ("running", {"ok": False, "writerExited": True}, {}),
    ("exited", {"ok": True, "writerExited": True}, {"ready": True}),
    ("settled", {"ok": True, "writerExited": False},
     {"target": TARGET, "runtime": {}, "checkedAt": "2026-09-05T00:00:00Z"}),
])
def test_resealed_marker_cannot_replace_writer_exit_proof(tmp_path, state_name, result, binding):
    state = operation.DependencyOperation(tmp_path)
    with data_dir_owner.acquire_data_dir_owner(tmp_path) as owner:
        value = state.begin(TARGET, "synthetic", {}, owner)
        value.update(state=state_name, result=result, binding=binding)
        # A valid checksum does not excuse inconsistent persisted state.
        state._write(value, owner)
        with pytest.raises(operation.DependencyOperationError, match="invalid"):
            state.read()
        with pytest.raises(operation.DependencyOperationError, match="invalid"):
            state.assert_available()


@pytest.mark.skipif(os.name != "nt", reason="Windows containment contract")
def test_containment_real_exit_and_cancel(tmp_path):
    target = tmp_path / "created"
    plan = {"actionable": True, "steps": [{"_argv": [sys.executable, "-c",
        "from pathlib import Path; Path(" + repr(str(target)) + ").write_text('ok')"]}]}
    result = operation.execute_contained(plan)
    assert result["ok"] is True and result["writerExited"] is True
    assert target.read_text() == "ok"
    cancel = threading.Event()
    cancel.set()
    result = operation.execute_contained({"actionable": True, "steps": [
        {"_argv": [sys.executable, "-c", "import time; time.sleep(20)"]},
    ]}, cancel_event=cancel)
    assert result["ok"] is False and result["writerExited"] is True


@pytest.fixture
def managed_env(tmp_path, monkeypatch):
    data, bundle = tmp_path / "profile", tmp_path / "bundle"
    data.mkdir()
    bundle.mkdir()
    manifest = {"schemaVersion": 1, "skill": "demo", "capabilities": {
        "create": {"required": [{"type": "python", "name": "r076-demo", "importName": "r076_demo", "version": "1.0"}],
                   "optional": [{"type": "python", "name": "never-install-optional-r076"}]},
        "other": {"required": [{"type": "python", "name": "never-install-other-r076"}]},
    }}
    _write_skill(bundle, "demo", allowed="run_command, use_skill, check_skill_dependencies, read_file",
                 extra={"dependencies.json": json.dumps(manifest)})
    shutil.copytree(bundle, data / "skills")
    catalog = skill_revisions.build_bundled_catalog(bundle, {"demo": "code.bundle/demo"})
    skill_store.SkillStore(data, bundle, write_enabled=True).bootstrap(catalog)
    reader = skill_store.SkillStoreReader(data)
    monkeypatch.setattr(server, "DATA_DIR", data)
    monkeypatch.setattr(server, "_MODEL_ROUTE_REGISTRY_ENABLED", False)
    monkeypatch.setattr(server, "_SKILL_IMMUTABLE_ADMISSION_ENABLED", True)
    monkeypatch.setattr(server, "_agent_runs", {})
    monkeypatch.setattr(server, "_managed_dependency_plans", server.OrderedDict())
    with data_dir_owner.acquire_data_dir_owner(data) as owner:
        service = skill_management_api.SkillManagementService(data, bundle, owner=owner,
            admission_enabled=True, catalog_loader=lambda: catalog)
        monkeypatch.setattr(server, "_skill_management_service", lambda: service)
        yield data, bundle, reader, service


def test_plan_forgery_cross_run_off_and_optional_are_closed(managed_env):
    _, _, reader, service = managed_env
    run = _run(reader, explicit="demo", permission="bypass")
    execution, _ = _call(run, "check_skill_dependencies", {"name": "demo", "capability": "create"}, "check")
    plan = execution["result"]["dependencyPlan"]
    assert [item["name"] for item in plan["requirements"]] == ["r076-demo"]
    assert plan["target"]["revisionId"] == run["skill_lifecycle"]["activation"]["selected"][0]["revisionId"]
    other = _run(reader, explicit="demo", permission="bypass")
    result, _ = _call(other, "run_command", plan["toolArguments"], "foreign")
    assert result["result"]["errorCode"] == "dependency_plan_unavailable"
    result, _ = _call(run, "run_command", {**plan["toolArguments"], "command": "echo forged"}, "forged")
    assert result["result"]["errorCode"] == "dependency_plan_command_forbidden"
    service.admission_enabled = False
    result, _ = _call(run, "check_skill_dependencies", {"name": "demo", "capability": "create"}, "off")
    assert result["result"]["dependencyPlanError"] == "management_read_only"


@pytest.mark.parametrize("permission", ["accept", "read"])
def test_non_bypass_retains_authorization(managed_env, permission):
    _, _, reader, _ = managed_env
    run = _run(reader, explicit="demo", permission=permission)
    checked, _ = _call(run, "check_skill_dependencies", {"name": "demo", "capability": "create"}, "check")
    execution, _ = _call(run, "run_command", checked["result"]["dependencyPlan"]["toolArguments"], "install")
    if permission == "accept":
        assert run["status"] == "waiting_authorization"
        assert execution["status"] == "waiting_authorization"
        assert run["pending_authorization"]["command"]
        original_pending = copy.deepcopy(run["pending_authorization"])
        run["permission_profile"] = "bypass"
        with mock.patch.object(server, "_managed_dependency_execute") as execute:
            assert server._execute_agent_pending_tools(run) is False
        execute.assert_not_called()
        assert run["pending_authorization"] == original_pending
    else:
        assert execution["result"]["ok"] is False
        assert run["pending_authorization"] is None
    assert server._managed_dependency_state().read() is None


def test_shared_runtime_bidirectional_gate_and_plain_chat(managed_env):
    data, _, reader, service = managed_env
    run = _run(reader, explicit="demo", permission="bypass", request_id="original")
    checked, _ = _call(run, "check_skill_dependencies", {"name": "demo", "capability": "create"}, "check")
    plan = checked["result"]["dependencyPlan"]
    other = _run(reader, explicit="demo", permission="bypass")
    result, _ = _call(run, "run_command", plan["toolArguments"], "busy")
    assert result["result"]["errorCode"] == "dependency_runtime_in_use"
    assert server._managed_dependency_state().read() is None
    other["status"] = "completed"
    entry = server._managed_dependency_entry(plan["reference"], run)
    server._managed_dependency_state().begin(plan["target"], run["id"], entry["plan"], service.owner)
    with pytest.raises(server.SkillActivationError, match="unsettled"):
        _run(reader, explicit="demo", permission="bypass")
    assert _run(reader, explicit="demo", request_id="original") is run
    plain = server._create_agent_run("", {"model": "test", "messages": [{"role": "user", "content": "hello"}]},
        "http://127.0.0.1:9", [], ["read_file"], start_worker=False)
    assert plain["active_skill_names"] == []
    assert operation.DependencyOperation(data).read()["state"] == "running"
    with pytest.raises(operation.DependencyOperationError, match="unknown"):
        server._managed_dependency_plan("demo", "create", "repair", run)


def test_unknown_writer_and_mark_failure_do_not_replay_or_execute(managed_env):
    data, _, reader, _ = managed_env
    run = _run(reader, explicit="demo", permission="bypass")
    checked, _ = _call(run, "check_skill_dependencies", {"name": "demo", "capability": "create"}, "check")
    plan = checked["result"]["dependencyPlan"]
    with mock.patch.object(operation.DependencyOperation, "_write", side_effect=OSError("disk unavailable")), \
            mock.patch.object(operation, "execute_contained") as execute:
        failed, _ = _call(run, "run_command", plan["toolArguments"], "mark-failed")
    assert failed["result"]["ok"] is False
    execute.assert_not_called()
    with mock.patch.object(operation, "execute_contained", return_value={"ok": False, "writerExited": False}), \
            mock.patch.object(server, "_agent_bind_skill_runtime_durably") as bind:
        failed, _ = _call(run, "run_command", plan["toolArguments"], "unknown")
    bind.assert_not_called()
    assert failed["result"]["ok"] is False
    assert operation.DependencyOperation(data).read()["state"] == "running"
    with pytest.raises(operation.DependencyOperationError, match="unsettled"):
        operation.DependencyOperation(data).assert_available()


def test_concurrent_operations_have_one_marker_owner(tmp_path):
    state = operation.DependencyOperation(tmp_path)
    results = []
    with data_dir_owner.acquire_data_dir_owner(tmp_path) as owner:
        def begin():
            try:
                results.append(state.begin(TARGET, "one", {}, owner)["operationId"])
            except operation.DependencyOperationError as exc:
                results.append(exc.code)
        workers = [threading.Thread(target=begin) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5)
            assert not worker.is_alive()
    assert results.count("dependency_writer_unknown") == 1
    assert len(set(results)) == 2


@pytest.mark.skipif(os.name != "nt", reason="Windows containment contract")
def test_descendant_exit_is_not_inferred_from_installer_pid(tmp_path):
    child_script = "import time; time.sleep(20)"
    parent_script = "import subprocess,sys; subprocess.Popen([sys.executable,'-c'," + repr(child_script) + "], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)"
    result = operation.execute_contained({"actionable": True, "steps": [
        {"_argv": [sys.executable, "-c", parent_script]},
    ]})
    assert result == {"ok": False, "errorCode": "dependency_descendant_outlived_installer", "writerExited": True}


@pytest.mark.skipif(os.name != "nt", reason="Windows packaged-source containment")
def test_packaged_worker_source_closure_is_runnable(tmp_path, monkeypatch):
    source = Path(operation.__file__).parent
    destination = tmp_path / "dependency-worker" / "code_runtime"
    destination.mkdir(parents=True)
    for filename in ("__init__.py", "skill_dependency_operation.py", "skill_dependencies.py", "skill_resources.py", "bundled_skills.py"):
        shutil.copyfile(source / filename, destination / filename)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    argv = operation.worker_command(sys.executable)
    assert str(destination) in argv[2]
    result = operation.execute_contained({"actionable": True, "steps": [
        {"_argv": [sys.executable, "-c", "print('packaged-source')"]},
    ]}, worker_argv=argv)
    assert result["ok"] is True and result["writerExited"] is True


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.skipif(os.name != "nt", reason="Windows writer exit")
def test_cancel_and_timeout_after_effect_do_not_claim_rollback(tmp_path, cancel):
    marker = tmp_path / "effect"
    event = threading.Event()
    script = "from pathlib import Path; import time; Path(" + repr(str(marker)) + ").write_text('changed'); time.sleep(20)"
    plan = {"actionable": True, "steps": [{"_argv": [sys.executable, "-c", script]}]}
    results = []
    worker = threading.Thread(target=lambda: results.append(operation.execute_contained(
        plan, cancel_event=event, timeout_seconds=5 if cancel else 1)))
    worker.start()
    try:
        import time
        deadline = time.monotonic() + 5
        while not marker.exists() and worker.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.read_text() == "changed"
    finally:
        if cancel:
            event.set()
        worker.join(timeout=10)
        assert not worker.is_alive()
    assert results[0]["ok"] is False and results[0]["writerExited"] is True
    assert results[0]["cancelled" if cancel else "timedOut"] is True
    assert marker.read_text() == "changed"


@pytest.mark.skipif(os.name != "nt", reason="Windows containment contract")
@pytest.mark.parametrize("interrupt_binding", [False, True])
def test_offline_real_install_recheck_bind_continue(managed_env, tmp_path, monkeypatch, interrupt_binding):
    data, _, reader, _ = managed_env
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    with zipfile.ZipFile(wheels / "r076_demo-1.0-py3-none-any.whl", "w") as wheel:
        wheel.writestr("r076_demo/__init__.py", "VALUE = 76\n")
        wheel.writestr("r076_demo-1.0.dist-info/METADATA", "Metadata-Version: 2.1\nName: r076-demo\nVersion: 1.0\n")
        wheel.writestr("r076_demo-1.0.dist-info/WHEEL", "Wheel-Version: 1.0\nGenerator: synthetic\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        wheel.writestr("r076_demo-1.0.dist-info/RECORD", "")
    monkeypatch.setenv("PIP_NO_INDEX", "1")
    monkeypatch.setenv("PIP_FIND_LINKS", str(wheels))
    monkeypatch.setenv("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    monkeypatch.setenv("PIP_CONFIG_FILE", os.devnull)
    monkeypatch.setenv("PIP_CACHE_DIR", str(tmp_path / "pip-cache"))
    run = _run(reader, explicit="demo", permission="bypass")
    checked, _ = _call(run, "check_skill_dependencies", {"name": "demo", "capability": "create"}, "check")
    plan = checked["result"]["dependencyPlan"]
    original_persist = server._persist_agent_run
    interrupted = []
    def persist(value):
        if interrupt_binding and value.get("skill_runtime_bindings") and not interrupted:
            interrupted.append(True)
            raise OSError("synthetic binding write failure")
        return original_persist(value)
    with mock.patch.object(server, "_persist_agent_run", side_effect=persist):
        execution, _ = _call(run, "run_command", plan["toolArguments"], "install")
    if interrupt_binding:
        assert execution["result"]["errorCode"] == "skill_dependency_binding_persist_failed"
        assert not run["skill_runtime_bindings"]
        assert operation.DependencyOperation(data).read()["state"] == "exited"
        with mock.patch.object(operation, "execute_contained") as not_reinstalled:
            rechecked, _ = _call(run, "check_skill_dependencies", {"name": "demo", "capability": "create"}, "settle")
        assert rechecked["result"]["ok"] is True, rechecked["result"]
        not_reinstalled.assert_not_called()
    else:
        assert execution["result"]["ok"] is True, execution["result"]
        assert execution["result"]["settled"] is True
    assert execution["result"]["writerExited"] is True
    assert run["pending_authorization"] is None
    assert run["skill_runtime_bindings"]["demo"]["capability"] == "create"
    persisted = json.loads(server._agent_run_path(run["id"]).read_text(encoding="utf-8"))
    assert persisted["version"] == 6
    assert operation.DependencyOperation(data).read()["state"] == "settled"
    with pytest.raises(operation.DependencyOperationError, match="unavailable"):
        server._managed_dependency_entry(plan["reference"], run)
    # Real next tool uses the exact managed interpreter selected by the binding.
    executable = run["skill_runtime_bindings"]["demo"]["runtime"]["python"]["executable"]
    result, _ = _call(run, "run_command", {"command": "& '" + executable + "' -c 'import r076_demo; print(r076_demo.VALUE)'"}, "continue")
    assert result["result"]["ok"] is True, result["result"]
    assert "76" in result["result"]["stdout"]
    restored = server._agent_run_from_record(server._agent_run_record(run), immutable_skill_reader=reader)
    assert restored["skill_runtime_bindings"] == run["skill_runtime_bindings"]
