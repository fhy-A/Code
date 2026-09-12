"""Crash/IO boundaries using only synthetic temporary profiles."""
import copy
import json
from unittest import mock

import pytest

from code_runtime import data_dir_owner
from code_runtime import skill_store as legacy
from code_runtime import skill_store_management as management
from code_runtime import skill_store_v2 as metadata
from tests.test_skill_store import _CrashOnce, _fixture, _snapshot
from tests.test_skill_store_management import apply, convert, installation, managed, package_request


FAULTS = [
    "after-journal-prepared-temp", "after-journal-prepared-publish", "after-staging-file",
    "after-management-capture", "after-journal-captured-temp", "after-journal-captured-publish",
    "after-object-publish", "after-journal-objects-published-temp", "after-journal-objects-published-publish",
    "after-managed-registry-temp", "after-managed-registry-publish",
    "after-journal-registry-published-temp", "after-journal-registry-published-publish",
    "after-journal-committed-temp", "after-journal-committed-publish",
    "after-management-receipt", "after-management-cleanup",
]


@pytest.mark.parametrize("point", FAULTS)
@pytest.mark.parametrize("error_type", [legacy.SkillStoreInterruption, OSError])
def test_each_durable_boundary_replays_once(managed, point, error_type):
    manager, _, tmp_path = managed
    convert(manager)
    base = manager.store.read_registry()
    custom = installation(manager, "custom")
    request, package = package_request(tmp_path / "next", "edit-local", "custom", "next bytes",
                                       iid=custom["installationId"])
    reached = []

    def crash(value):
        if value == point and not reached:
            reached.append(value)
            raise error_type("injected durable-boundary interruption")

    manager.store.fault_injector = crash
    with pytest.raises(error_type):
        apply(manager, "next", request, package=package, base=base)
    assert reached == [point]
    manager.store.fault_injector = None
    actual = manager.store._load_registry()
    assert actual["generation"] in {base["generation"], base["generation"] + 1}
    receipt = apply(manager, "next", request, package=package, base=base)
    assert receipt["appliedGeneration"] == base["generation"] + 1
    final = manager.store.read_registry()
    assert final["generation"] == receipt["appliedGeneration"]
    assert apply(manager, "next", request, base=base) == receipt
    assert not list((manager.store.root / "staging").iterdir())
    assert not list(manager.store.root.rglob("*.tmp"))
    assert len(manager.store._journals()) == 3


@pytest.mark.parametrize("point", ["after-journal-prepared-publish", "after-staging-file"])
def test_early_source_drift_preserves_frozen_request(managed, point):
    manager, _, tmp_path = managed
    convert(manager)
    base = manager.store.read_registry()
    request, package = package_request(tmp_path / "next", "edit-local", "custom", "original capture",
                                       iid=installation(manager, "custom")["installationId"])
    captured = management.capture_package(package)
    manager.store.fault_injector = _CrashOnce(point)
    with pytest.raises(legacy.SkillStoreInterruption):
        apply(manager, "edit", request, package=package)
    manager.store.fault_injector = None
    (package / "SKILL.md").write_text("different source", encoding="utf-8")
    before = _snapshot(manager.store.root)
    with pytest.raises(legacy.SkillStoreError) as caught:
        manager.recover()
    assert caught.value.code == "management_capture_required"
    with pytest.raises(legacy.SkillStoreError) as caught:
        apply(manager, "edit", request, package=package, base=base)
    assert caught.value.code == "management_source_changed"
    assert _snapshot(manager.store.root) == before
    assert apply(manager, "edit", request, package=captured, base=base)["appliedGeneration"] == base["generation"] + 1


@pytest.mark.parametrize("point", ["after-management-capture", "after-object-publish", "after-managed-registry-publish"])
def test_late_recovery_never_reads_mutable_sources(managed, point):
    manager, _, tmp_path = managed
    convert(manager)
    request, package = package_request(tmp_path / "next", "edit-local", "custom", "captured forever",
                                       iid=installation(manager, "custom")["installationId"])
    manager.store.fault_injector = _CrashOnce(point)
    with pytest.raises(legacy.SkillStoreInterruption):
        apply(manager, "edit", request, package=package)
    manager.store.fault_injector = None
    (package / "SKILL.md").write_text("changed", encoding="utf-8")
    with mock.patch.object(management, "capture_package", side_effect=AssertionError("source IO forbidden")):
        receipt = manager.recover()
    assert receipt["requestHash"] == legacy._digest(legacy._canonical(request))
    assert installation(manager, "custom")["revisionId"] == request["revisionId"]


@pytest.mark.parametrize("point", ["after-journal-prepared-publish", "after-staging-file", "after-object-publish"])
def test_abort_only_cleans_owned_staging_never_published_history(managed, point):
    manager, _, tmp_path = managed
    convert(manager)
    base = manager.store.read_registry()
    objects = _snapshot(manager.store.root / "objects")
    request, package = package_request(tmp_path / "next", "edit-local", "custom", "aborted bytes",
                                       iid=installation(manager, "custom")["installationId"])
    manager.store.fault_injector = _CrashOnce(point)
    with pytest.raises(legacy.SkillStoreInterruption):
        apply(manager, "abort", request, package=package)
    manager.store.fault_injector = None
    result = manager.abort("abort")
    assert result["state"] == "aborted"
    assert manager.abort("abort") == result
    assert manager.store.read_registry() == base
    for name, payload in objects.items():
        assert _snapshot(manager.store.root / "objects")[name] == payload
    if point == "after-object-publish":
        assert manager.store._object_path(request["revisionId"]).exists()
    with pytest.raises(legacy.SkillStoreError) as caught:
        apply(manager, "abort", request, base=base)
    assert caught.value.code == "management_operation_aborted"
    apply(manager, "new-operation", request, package=package)
    assert manager.store.read_registry()["generation"] == base["generation"] + 1


def test_commit_cannot_abort_or_rewind(managed):
    manager, _, _ = managed
    manager.store.fault_injector = _CrashOnce("after-managed-registry-publish")
    with pytest.raises(legacy.SkillStoreInterruption):
        convert(manager)
    manager.store.fault_injector = None
    before = manager.store._load_registry()
    with pytest.raises(legacy.SkillStoreError) as caught:
        manager.abort("convert")
    assert caught.value.code == "management_already_committed"
    manager.recover()
    assert manager.store.read_registry() == before


@pytest.mark.parametrize("action", ["recover", "abort"])
def test_short_disk_write_needs_the_original_captured_prefix(managed, action):
    manager, _, tmp_path = managed
    convert(manager)
    request, package = package_request(tmp_path / "new", "edit-local", "custom", "bounded capture",
                                       iid=installation(manager, "custom")["installationId"])
    manager.store.fault_injector = _CrashOnce("after-staging-file")
    with pytest.raises(legacy.SkillStoreInterruption):
        apply(manager, "short-write", request, package=package)
    manager.store.fault_injector = None
    journal = next(j for j in manager.store._journals() if j["phase"] == "prepared")
    partial = manager.store._object_path(request["revisionId"], staging=journal["operationId"]) / "content" / "SKILL.md"
    partial.write_bytes(partial.read_bytes()[:7])
    before = _snapshot(manager.store.root)
    with pytest.raises(legacy.SkillStoreError):
        manager.abort("short-write")
    assert _snapshot(manager.store.root) == before
    if action == "abort":
        assert manager.abort("short-write", package=package)["state"] == "aborted"
    else:
        manager.recover(package=package)
        assert installation(manager, "custom")["revisionId"] == request["revisionId"]
    assert not list((manager.store.root / "staging").iterdir())


def test_late_missing_or_corrupt_capture_never_reloads_source(managed):
    manager, _, tmp_path = managed
    convert(manager)
    base = manager.store.read_registry()
    request, package = package_request(tmp_path / "new", "edit-local", "custom", "late capture",
                                       iid=installation(manager, "custom")["installationId"])
    manager.store.fault_injector = _CrashOnce("after-journal-captured-publish")
    with pytest.raises(legacy.SkillStoreInterruption):
        apply(manager, "late", request, package=package)
    manager.store.fault_injector = None
    journal = next(j for j in manager.store._journals() if j["phase"] == "captured")
    path = manager.store._object_path(request["revisionId"], staging=journal["operationId"]) / "manifest.json"
    path.unlink()
    before = _snapshot(manager.store.root)
    with mock.patch.object(management, "capture_package", side_effect=AssertionError("late source reload")):
        with pytest.raises(legacy.SkillStoreError):
            manager.recover(package=package)
    assert _snapshot(manager.store.root) == before
    assert manager.store._load_registry() == base


def test_unknown_staging_and_objects_are_preserved(managed):
    manager, _, tmp_path = managed
    convert(manager)
    request, package = package_request(tmp_path / "next", "edit-local", "custom", "new",
                                       iid=installation(manager, "custom")["installationId"])
    manager.store.fault_injector = _CrashOnce("after-staging-file")
    with pytest.raises(legacy.SkillStoreInterruption):
        apply(manager, "edit", request, package=package)
    manager.store.fault_injector = None
    journal = next(item for item in manager.store._journals() if item["phase"] == "prepared")
    # staging is addressed through the store: its directory name is the short form
    unknown = manager.store._staging_directory(journal["operationId"]) / "user-file.txt"
    unknown.write_text("must survive", encoding="utf-8")
    with pytest.raises(legacy.SkillStoreError) as caught:
        manager.abort("edit")
    assert caught.value.code == "staging_unknown"
    assert unknown.read_text(encoding="utf-8") == "must survive"


@pytest.mark.parametrize("point", ["after-journal-copying-publish", "after-journal-staged-verified-publish"])
def test_explicit_conversion_closes_v1_first(tmp_path, point):
    data, bundle, catalog = _fixture(tmp_path)
    store = legacy.SkillStore(data, bundle, write_enabled=True, fault_injector=_CrashOnce(point))
    with pytest.raises(legacy.SkillStoreInterruption):
        store.bootstrap(catalog)
    v1 = store._journals()[0]["targetRegistry"]
    legacy_before = _snapshot(data / "skills")
    store.fault_injector = None
    with data_dir_owner.acquire_data_dir_owner(data) as owner:
        manager = management.SkillStoreManager(store, owner=owner)
        loader = mock.Mock(return_value=catalog)
        receipt = manager.apply("convert", {"kind": "convert-v2"}, base_generation=v1["generation"],
                                base_registry_hash=v1["registryHash"], catalog_loader=loader)
        assert receipt["appliedGeneration"] == 1
        assert store._journals()[0]["phase"] == "committed"
        if "staged-verified" in point:
            loader.assert_not_called()
        else:
            assert loader.called
        assert _snapshot(data / "skills") == legacy_before
