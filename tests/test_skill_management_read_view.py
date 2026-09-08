"""Request-local management projections; synthetic stores, no runtime writes."""
import copy
import shutil
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest

from code_runtime import data_dir_owner, skill_revisions, skill_store, skill_store_management
from code_runtime import skill_management_api as api
from tests.test_skill_management_api import service, _convert, _item, _preview, _commit
from tests.test_skill_store import _snapshot, _write_skill, _CrashOnce
from tests.test_skill_store_management import apply


@pytest.fixture(scope="module")
def selected_31_skill_template(tmp_path_factory):
    """Build the real generation-32 history once; tests only mutate copies."""
    root = tmp_path_factory.mktemp("selected-31-skill-template")
    data, bundle = root / "profile", root / "bundle"
    data.mkdir()
    for index in range(31):
        _write_skill(bundle, f"skill-{index:02}", extra={
            f"resources/reference-{number}.txt": "synthetic reference\n" * 20 for number in range(6)
        })
    catalog = skill_revisions.build_bundled_catalog(bundle, {
        f"skill-{index:02}": f"code.bundle/skill-{index:02}" for index in range(31)
    })
    store = skill_store.SkillStore(data, bundle, write_enabled=True)
    store.bootstrap(catalog)
    with data_dir_owner.acquire_data_dir_owner(data) as owner:
        manager = skill_store_management.SkillStoreManager(store, owner=owner)
        apply(manager, "convert", {"kind": "convert-v2"})
        for item in store.read_registry()["installations"]:
            apply(manager, item["displayName"], {"kind": "select-candidate",
                  "installationId": item["installationId"], "routingAlias": item["displayName"]})
        assert store.read_registry()["generation"] == 32
    before = _snapshot(root)
    yield root
    assert _snapshot(root) == before


def _copy_31_skill_template(source, destination):
    data, bundle = destination / "profile", destination / "bundle"
    shutil.copytree(source / "profile", data)
    shutil.copytree(source / "bundle", bundle)
    assert _snapshot(data) == _snapshot(source / "profile")
    assert _snapshot(bundle) == _snapshot(source / "bundle")
    return data, bundle


def test_31_skill_toggle_snapshot_and_integrity(tmp_path, selected_31_skill_template):
    """Exercise both real write directions; historical warmups live in performance/."""
    data, bundle = _copy_31_skill_template(selected_31_skill_template, tmp_path)
    assert sum(path.is_file() for path in bundle.rglob("*")) == 217
    store = skill_store.SkillStore(data, bundle, write_enabled=True)
    with data_dir_owner.acquire_data_dir_owner(data) as owner:
        target = store.read_registry()["installations"][0]
        service = api.SkillManagementService(data, bundle, owner=owner,
            admission_enabled=True, server_instance_id="synthetic")
        for desired in (False, True):
            generation = store.read_registry()["generation"]
            snapshot = service.snapshot()
            assert snapshot["mode"] == "managed-v2" and snapshot["registry"]["generation"] == generation
            assert len(snapshot["installations"]) == 31
            preview = service.preview({"protocol": api.PROTOCOL,
                "base": snapshot["registry"], "kind": "set-enabled", "installationId": target["installationId"], "enabled": desired})
            result = service.apply({"protocol": api.PROTOCOL,
                "base": preview["base"], "request": preview["request"], "operationKey": f"toggle-from-{generation}", "confirmed": True})
            refreshed = service.snapshot()  # Independent re-read validates the write response.
            assert result["snapshot"] == refreshed
            assert result["snapshot"]["registry"]["generation"] == generation + 1
            item = next(item for item in refreshed["installations"] if item["installationId"] == target["installationId"])
            assert item["enabled"] is desired


@pytest.mark.parametrize("converted", [False, True])
def test_read_only_view_compatibility_and_no_cross_request_cache(service, converted):
    if converted:
        _convert(service)
    service.admission_enabled = False
    before = _snapshot(service.data_root)
    snapshot = service.snapshot()
    assert snapshot["mode"] == ("managed-v2" if converted else "immutable-v1")
    assert not snapshot["capabilities"]["write"]
    assert all(item["description"] == "test" for item in snapshot["installations"])
    item = snapshot["installations"][0]
    detail = service.detail(item["installationId"], item["revisionId"])
    assert detail["description"] == item["description"]
    assert _snapshot(service.data_root) == before
    path = service.store._object_path(item["revisionId"]) / "content" / "SKILL.md"
    path.write_bytes(path.read_bytes() + b"tampered")
    broken = _snapshot(service.data_root)
    failed = service.snapshot()
    assert failed["mode"] == "unavailable"
    assert failed["installations"] == [] and failed["registry"] is None
    with pytest.raises(api.SkillManagementError, match="object_corrupt"):
        service.detail(item["installationId"], item["revisionId"])
    assert _snapshot(service.data_root) == broken


@pytest.mark.parametrize("drift", ["root", "generation"])
def test_response_rechecks_identity_after_content(service, drift):
    _convert(service)
    item = _item(service, "local")
    reader_store = service.reader._store
    original = reader_store._load_root if drift == "root" else reader_store._load_registry
    armed = False

    def changed(*args, **kwargs):
        value = original(*args, **kwargs)
        if armed:
            value = copy.deepcopy(value)
            if drift == "root":
                value["dataRootId"] = "dr1_" + "a" * 32
            else:
                value["generation"] += 1
        return value

    read = service.reader._read_pinned_from_root

    def read_then_drift(*args, **kwargs):
        nonlocal armed
        result = read(*args, **kwargs)
        armed = True
        return result

    before = _snapshot(service.data_root)
    with mock.patch.object(reader_store, "_load_root" if drift == "root" else "_load_registry", side_effect=changed), \
            mock.patch.object(service.reader, "_read_pinned_from_root", side_effect=read_then_drift):
        with pytest.raises(api.SkillManagementError, match="registry_changed"):
            service.detail(item["installationId"], item["revisionId"])
    assert _snapshot(service.data_root) == before


def test_interrupted_transaction_stays_unavailable_without_recovery(service):
    _convert(service)
    item = _item(service, "local")
    preview = _preview(service, "set-enabled", installationId=item["installationId"], enabled=False)
    service.store.fault_injector = _CrashOnce("after-journal-prepared-publish")
    with pytest.raises(RuntimeError):
        _commit(service, preview, "pending")
    service.store.fault_injector = None
    before = _snapshot(service.data_root)
    assert service.snapshot()["mode"] == "unavailable"
    with pytest.raises(api.SkillManagementError, match="store_busy"):
        service.detail(item["installationId"], item["revisionId"])
    assert _snapshot(service.data_root) == before


def test_lineage_and_registry_must_be_the_same_generation(service):
    _convert(service)
    inspect = service.reader._store.inspect_startup_state
    def stale_state():
        state = inspect()
        state["generation"] -= 1
        return state
    before = _snapshot(service.data_root)
    with mock.patch.object(service.reader._store, "inspect_startup_state", side_effect=stale_state):
        result = service.snapshot()
        assert result["mode"] == "unavailable" and result["errorCode"] == "registry_changed"
        assert not result["installations"]
    assert _snapshot(service.data_root) == before


def test_detail_verifies_target_only_but_snapshot_rejects_any_returned_corruption(service):
    _convert(service)
    local, bundled = _item(service, "local"), _item(service, "alpha")
    with pytest.raises(api.SkillManagementError, match="management_identity_required"):
        service.detail(local["installationId"], data_root_id="dr1_" + "f" * 32)
    with pytest.raises(api.SkillManagementError, match="management_revision_not_retained"):
        service.detail(local["installationId"], bundled["revisionId"])
    path = service.store._object_path(bundled["revisionId"]) / "content" / "nested" / "text.txt"
    path.write_bytes(b"changed unrelated resource")
    before = _snapshot(service.data_root)
    assert service.detail(local["installationId"])["name"] == "local"
    assert service.snapshot()["mode"] == "unavailable"
    with pytest.raises(skill_store.SkillStoreError) as error:
        service.reader.read_registry()  # Runtime reader still checks the entire retained store.
    assert error.value.code == "object_corrupt"
    assert _snapshot(service.data_root) == before


def test_31_skill_first_reads_counts_and_parallel_integrity(tmp_path, selected_31_skill_template):
    data, bundle = _copy_31_skill_template(selected_31_skill_template, tmp_path)
    store = skill_store.SkillStore(data, bundle, write_enabled=True)
    with data_dir_owner.acquire_data_dir_owner(data) as owner:
        manager = skill_store_management.SkillStoreManager(store, owner=owner)
        registry = store.read_registry()
        target = registry["installations"][0]
        for enabled in (False, True):
            apply(manager, str(enabled), {"kind": "set-enabled", "installationId": target["installationId"], "enabled": enabled})
        before = _snapshot(data)

        def new_service():
            return api.SkillManagementService(data, bundle, owner=owner, admission_enabled=True)

        current = new_service()
        with mock.patch.object(current.reader._store, "_verify_object", wraps=current.reader._store._verify_object) as verify, \
                mock.patch.object(current.reader._store, "inspect_startup_state", wraps=current.reader._store.inspect_startup_state) as inspect:
            snapshot = current.snapshot()
            assert snapshot["mode"] == "managed-v2" and snapshot["registry"]["generation"] == 34
            assert len(snapshot["installations"]) == 31
            assert all(item["description"] == "test" for item in snapshot["installations"])
            assert verify.call_count == 62 and inspect.call_count == 1
        current = new_service()  # A fresh service; no warmed application cache.
        with mock.patch.object(current.reader._store, "_verify_object", wraps=current.reader._store._verify_object) as verify, \
                mock.patch.object(current.reader._store, "inspect_startup_state", wraps=current.reader._store.inspect_startup_state) as inspect:
            detail = current.detail(target["installationId"])
            assert detail["description"] == "test"
            assert verify.call_count == 2 and inspect.call_count == 1
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(new_service().snapshot),
                       pool.submit(new_service().detail, target["installationId"])]
            results = [future.result(timeout=30) for future in futures]
        assert results[0]["mode"] == "managed-v2" and results[1]["description"] == "test"
        assert _snapshot(data) == before
