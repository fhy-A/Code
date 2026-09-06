"""Local HTTP and new-admission compatibility for managed Skills."""
import json
import threading
from unittest import mock

import pytest
import requests

import server
from code_runtime import skill_management_api as api
from tests.test_skill_management_api import service, _convert, _item, _preview, _commit


@pytest.fixture
def http(service, monkeypatch):
    monkeypatch.setattr(server, "DATA_DIR", service.data_root)
    monkeypatch.setattr(server, "SKILLS_DIR", service.data_root / "skills")
    monkeypatch.setattr(server, "SESSIONS_DIR", service.data_root / "sessions")
    monkeypatch.setattr(server, "CONFIG_PATH", service.data_root / "config.json")
    monkeypatch.setattr(server, "_skill_management_service", lambda: service)
    monkeypatch.setattr(server, "_MODEL_ROUTE_REGISTRY_ENABLED", False)
    monkeypatch.setattr(server, "_SKILL_IMMUTABLE_ADMISSION_ENABLED", True)
    host = server.ThreadingHTTPServer(("127.0.0.1", 0), server.CodeHandler)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    client = requests.Session()
    client.trust_env = False
    base = "http://127.0.0.1:" + str(host.server_port)
    try:
        yield lambda method, path, **kwargs: client.request(method, base + path, timeout=5, **kwargs)
    finally:
        client.close()
        host.shutdown()
        host.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()
        with server._agent_run_index_builds_lock:
            workers = [worker for path, worker in server._agent_run_index_builds.items()
                       if str(service.data_root) in path]
        for worker in workers:
            worker.join(timeout=2)
            assert not worker.is_alive()


def test_http_explicit_conversion_receipt_and_exact_read(http, service):
    state = http("GET", "/api/skill-management/v1").json()
    assert state["mode"] == "immutable-v1"
    preview = http("POST", "/api/skill-management/v1/preview", json={
        "protocol": api.PROTOCOL, "base": state["registry"], "kind": "convert-v2",
    })
    assert preview.status_code == 200
    body = preview.json()
    response = http("POST", "/api/skill-management/v1/operations", json={
        "protocol": api.PROTOCOL, "base": body["base"], "request": body["request"],
        "operationKey": "http-convert", "confirmed": True,
    })
    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert http("GET", "/api/skill-management/v1/receipts/http-convert", params={"dataRootId": state["registry"]["dataRootId"]}).json()["receipt"] == receipt
    item = _item(service, "alpha")
    path = "/api/skill-management/v1/installations/" + item["installationId"]
    identity = {"revision": item["revisionId"], "dataRootId": state["registry"]["dataRootId"]}
    assert http("GET", path, params={"revision": item["revisionId"]}).status_code == 400
    assert http("GET", path, params={**identity, "revision": [item["revisionId"], item["revisionId"]]}).status_code == 400
    result = http("GET", path, params=identity)
    assert result.status_code == 200
    assert result.json()["revisionId"] == item["revisionId"]
    result = http("GET", path + "/files", params={**identity, "path": "nested/text.txt"})
    assert result.json()["content"] == "a\n"


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/skills?brief=1"), ("GET", "/api/skills/alpha"),
    ("GET", "/api/skills/alpha/file?path=nested/text.txt"),
    ("GET", "/api/skills/dependencies"),
    ("POST", "/api/skills"), ("DELETE", "/api/skills?name=alpha"),
    ("POST", "/api/skills/dependencies/plan"),
    ("POST", "/api/skills/dependencies/operations"),
    ("POST", "/api/tools/use_skill"),
    ("POST", "/api/tools/check_skill_dependencies"),
    ("POST", "/api/tools/read_skill_resource"),
])
def test_legacy_http_is_explicitly_refused_before_mutable_helpers(http, method, path):
    with mock.patch.object(server, "read_skill", side_effect=AssertionError("legacy read")), \
            mock.patch.object(server, "create_skill", side_effect=AssertionError("legacy write")):
        response = http(method, path, json={"name": "alpha"})
    assert response.status_code == 409
    assert response.json()["errorCode"] == "management_client_upgrade_required"


def test_http_rejects_non_json_cross_origin_and_unknown_protocol(http, service):
    path = "/api/skill-management/v1/preview"
    payload = {"protocol": api.PROTOCOL, "base": service.snapshot()["registry"], "kind": "convert-v2"}
    non_json = http("POST", path, data="{}")
    assert non_json.status_code == 400
    assert non_json.headers.get("Connection") == "close"
    cross_origin = http("POST", path, json=payload, headers={"Origin": "https://other.invalid"})
    assert cross_origin.status_code == 403
    assert cross_origin.headers.get("Connection") == "close"
    unknown = http("POST", path, json={**payload, "protocol": "future"})
    assert unknown.status_code == 400
    assert unknown.json()["errorCode"] == "management_protocol_required"


def test_off_heartbeat_does_not_advertise_mutable_activation(http, service, monkeypatch):
    monkeypatch.setattr(server, "_SKILL_IMMUTABLE_ADMISSION_ENABLED", False)
    monkeypatch.setattr(server, "_SKILL_ACTIVATION_ENABLED", True)
    service.admission_enabled = False
    result = http("GET", "/api/browser-heartbeat").json()
    assert result["skillManagementMode"] == "immutable"
    assert "skillActivationProtocol" not in result


@pytest.mark.parametrize("admission,loading", [(None, None), ("off", None), (None, "off"), ("off", "off")])
def test_default_protocol_and_independent_opt_out(http, service, monkeypatch, admission, loading):
    from code_runtime.skill_runtime_startup import ImmutableSkillStartupRuntime
    from code_runtime.skill_activation import SKILL_PROMPT_MARKER

    admission_on = server._resolve_skill_immutable_admission_enabled(
        {} if admission is None else {"CODE_SKILL_IMMUTABLE_ADMISSION_V1": admission})
    loading_on = server._resolve_skill_model_loading_enabled(
        {} if loading is None else {"CODE_SKILL_MODEL_LOADING_V1": loading})
    monkeypatch.setattr(server, "_SKILL_IMMUTABLE_ADMISSION_ENABLED", admission_on)
    monkeypatch.setattr(server, "_SKILL_MODEL_LOADING_ENABLED", loading_on)
    monkeypatch.setattr(service, "admission_enabled", admission_on)
    runtime = ImmutableSkillStartupRuntime()
    runtime.initialize(owner=service.owner, data_root=service.data_root,
                       bundled_root=service.bundled_root, admission_enabled=admission_on)
    monkeypatch.setattr(server, "_immutable_skill_startup_runtime", runtime)
    before = service.snapshot()["registry"]
    heartbeat = http("GET", "/api/browser-heartbeat").json()
    assert (heartbeat.get("skillActivationProtocol") == "canonical-v1") is admission_on
    assert (heartbeat.get("skillLoadingProtocol") == "model-driven-v1") is (admission_on and loading_on)
    assert runtime.recovery_reader() is not None

    def create(schema):
        return server._create_agent_run("", {"model": "synthetic", "messages": [
            {"role": "system", "content": f"base\n\n{SKILL_PROMPT_MARKER}\n\npermission"},
            {"role": "user", "content": "plain task"},
        ]}, "http://127.0.0.1:9", [], {"schemaVersion": 1, "names": ["use_skill", "read_file"]},
            permission_profile="read", start_worker=False, run_kind="foreground", cwd=str(service.data_root),
            skill_activation_request={"schemaVersion": schema, "explicitSkill": "", "disabledNames": []})

    try:
        for schema in (1, 2):
            expected_error = ("immutable_skill_admission_disabled" if not admission_on else
                              "skill_loading_protocol_required" if loading_on and schema == 1 else
                              "skill_loading_disabled" if not loading_on and schema == 2 else None)
            if expected_error:
                with pytest.raises(server.SkillActivationError) as error:
                    create(schema)
                assert error.value.code == expected_error
            else:
                run = create(schema)
                assert server._agent_run_record(run)["version"] == (7 if schema == 2 else 6)
                assert not run["active_skill_names"]
                if schema == 2:
                    assert run["skill_loading"]["catalog"]
        assert service.snapshot()["registry"] == before
    finally:
        with server._agent_run_lock:
            server._agent_runs.clear()


def test_dependency_ui_uses_exact_server_plan_and_confirmation(http, service, monkeypatch):
    _convert(service)
    dependency = {"schemaVersion": 1, "skill": "ui-demo", "capabilities": {
        "create": {"required": [{"type": "python", "name": "r076-ui-missing-test"}]},
    }}
    _commit(service, _preview(service, "create-local", document="---\nname: ui-demo\ndescription: UI test\n---\nBody\n",
                             dependencyDocument=json.dumps(dependency)), "ui-demo")
    monkeypatch.setattr(server, "_managed_dependency_plans", server.OrderedDict())
    item = _item(service, "ui-demo")
    identity = {"dataRootId": service.snapshot()["registry"]["dataRootId"],
                "installationId": item["installationId"], "revisionId": item["revisionId"]}
    payload = {"protocol": api.PROTOCOL, "identity": identity, "capability": "create"}
    prefix = "/api/skill-management/v1/dependencies"
    assert http("POST", prefix + "/check", json=payload).status_code == 200
    plan = http("POST", prefix + "/plan", json={**payload, "action": "install"}).json()
    assert plan["target"]["installationId"] == item["installationId"]
    assert plan["target"]["revisionId"] == item["revisionId"]
    assert server._managed_dependency_state().read() is None
    with mock.patch.object(server, "_managed_dependency_execute", return_value={"ok": True}) as execute:
        body = {"protocol": api.PROTOCOL, "reference": plan["reference"],
                "fingerprint": plan["fingerprint"], "confirmed": True}
        assert http("POST", prefix + "/execute", json={**body, "fingerprint": "forged"}).status_code == 409
        assert http("POST", prefix + "/execute", json={**body, "confirmed": False}).status_code == 409
        execute.assert_not_called()
        assert http("POST", prefix + "/execute", json=body).json()["ok"] is True
        execute.assert_called_once_with(plan["reference"])
    assert http("POST", prefix + "/check", json={**payload, "identity": {**identity, "revisionId": "sha256:" + "f" * 64}}).status_code == 404


def test_existing_client_request_precedes_new_management_gate(monkeypatch):
    existing = {"id": "original", "status": "waiting_user_input"}
    with mock.patch.object(server, "_get_agent_run", return_value=existing), \
            mock.patch.object(server, "_skill_management_service", side_effect=AssertionError("new admission gate")):
        result = server._create_agent_run("", {"model": "synthetic", "messages": [{"role": "user", "content": "plain"}]},
                                          "http://127.0.0.1:9", [], client_request_id="original-request", start_worker=False)
    assert result is existing
