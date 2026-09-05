"""Explicit, profile-owned management; no real profiles or external sources."""
import copy
from pathlib import Path

import pytest

from code_runtime import data_dir_owner
from code_runtime import skill_revisions as revisions
from code_runtime import skill_store as legacy
from code_runtime import skill_store_management as management
from code_runtime import skill_store_v2 as metadata
from tests.test_skill_store import _fixture, _snapshot, _write_skill


@pytest.fixture
def managed(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    _write_skill(data / "skills", "custom")
    store = legacy.SkillStore(data, bundle, write_enabled=True)
    before = store.bootstrap(catalog)
    with data_dir_owner.acquire_data_dir_owner(data) as owner:
        manager = management.SkillStoreManager(store, owner=owner)
        yield manager, before, tmp_path


def apply(manager, key, request, *, package=None, base=None):
    base = base or manager.store.read_registry()
    return manager.apply(
        key, request, base_generation=base["generation"],
        base_registry_hash=base["registryHash"], package=package,
    )


def convert(manager):
    return apply(manager, "convert", {"kind": "convert-v2"})


def installation(manager, name):
    return next(item for item in manager.store.read_registry()["installations"]
                if item["displayName"] == name)


def package_request(tmp_path, kind, name, body, *, iid=None, conflict="reject"):
    path = _write_skill(tmp_path, name, body=body)
    request = {"kind": kind, "routingAlias": name,
               "revisionId": revisions.build_skill_revision(path)["revisionId"],
               "conflict": conflict}
    if iid is not None:
        request["installationId"] = iid
    return request, path


def test_conversion_preserves_v1_bytes_identity_and_history(managed):
    manager, before, _ = managed
    data = manager.store.data_root
    objects_before = _snapshot(manager.store.root / "objects")
    legacy_before = _snapshot(data / "skills")
    journal_before = _snapshot(manager.store.root / "transactions")
    receipt = convert(manager)
    after = manager.store.read_registry()
    assert after["schema"] == metadata.REGISTRY_SCHEMA
    assert after["generation"] == before["generation"] + 1
    assert after["dataRootId"] == before["dataRootId"]
    assert after["sourceObservations"] == before["sourceObservations"]
    assert after["bundledTombstones"] == before["bundledTombstones"]
    assert _snapshot(data / "skills") == legacy_before
    assert _snapshot(manager.store.root / "objects") == objects_before
    for name, payload in journal_before.items():
        assert _snapshot(manager.store.root / "transactions")[name] == payload
    for old in before["installations"]:
        new = next(item for item in after["installations"]
                   if item["installationId"] == old["installationId"])
        assert {key: new[key] for key in old} == old
        assert new["retainedRevisionIds"] == [old["revisionId"]]
    assert before["operationReceipts"][0] in after["operationReceipts"]
    assert receipt == apply(manager, "convert", {"kind": "convert-v2"}, base=before)


def test_a_b_c_retry_before_cas_and_identical_new_action(managed):
    manager, _, tmp_path = managed
    convert(manager)
    initial = manager.store.read_registry()
    custom = installation(manager, "custom")
    requests, receipts = [], []
    for letter in "ABC":
        request, package = package_request(
            tmp_path / letter, "edit-local", "custom", letter,
            iid=custom["installationId"],
        )
        requests.append(request)
        receipts.append(apply(manager, letter, request, package=package))
    after_c = manager.store.read_registry()
    assert apply(manager, "A", requests[0], base=initial) == receipts[0]
    assert manager.store.read_registry() == after_c
    with pytest.raises(legacy.SkillStoreError) as caught:
        apply(manager, "A", requests[1], base=initial)
    assert caught.value.code == "management_operation_key_conflict"
    with pytest.raises(legacy.SkillStoreError) as caught:
        apply(manager, "another", requests[0], base=initial)
    assert caught.value.code == "registry_cas_conflict"
    same_package = tmp_path / "C" / "custom"
    fresh = apply(manager, "C-again", requests[-1], package=same_package)
    assert fresh["appliedGeneration"] == after_c["generation"] + 1
    assert fresh["operationId"] != receipts[-1]["operationId"]
    item = installation(manager, "custom")
    assert item["skillId"] == custom["skillId"]
    assert item["installationId"] == custom["installationId"]
    assert len(item["retainedRevisionIds"]) == 4
    reader = legacy.SkillStoreReader(manager.store.data_root)
    for revision_id in item["retainedRevisionIds"]:
        assert reader.read_pinned(initial["dataRootId"], revision_id)["revisionId"] == revision_id


def test_fork_rename_toggle_uninstall_restore_and_rollback(managed):
    manager, _, tmp_path = managed
    convert(manager)
    bundle = installation(manager, "alpha")
    original_object = _snapshot(manager.store._object_path(bundle["revisionId"]))
    request, package = package_request(tmp_path / "fork", "fork-bundled", "alpha",
                                       "fork", iid=bundle["installationId"])
    with pytest.raises(legacy.SkillStoreError) as caught:
        apply(manager, "fork-rejected", request, package=package)
    assert caught.value.code == "management_alias_conflict"
    request["conflict"] = "select-new"
    receipt = apply(manager, "fork", request, package=package)
    iid = receipt["result"]["installationId"]
    first_revision = request["revisionId"]
    request, package = package_request(tmp_path / "rename", "edit-local", "renamed",
                                       "edited", iid=iid)
    apply(manager, "rename", request, package=package)
    reader = legacy.SkillStoreReader(manager.store.data_root)
    with pytest.raises(legacy.SkillStoreError) as caught:
        reader.read_active("alpha")
    assert caught.value.code == "store_binding_unavailable"
    assert reader.read_active("renamed")["installation"]["installationId"] == iid
    for kind, extra in (("set-enabled", {"enabled": False}), ("uninstall", {})):
        apply(manager, kind, {"kind": kind, "installationId": iid, **extra})
        with pytest.raises(legacy.SkillStoreError) as caught:
            reader.read_active("renamed")
        assert caught.value.code == "store_binding_unavailable"
        assert reader.read_pinned(manager.store.read_registry()["dataRootId"], first_revision)
    apply(manager, "restore", {"kind": "restore", "installationId": iid})
    assert installation(manager, "renamed")["enabled"] is False
    apply(manager, "enable", {"kind": "set-enabled", "installationId": iid, "enabled": True})
    generation = manager.store.read_registry()["generation"]
    apply(manager, "rollback", {"kind": "rollback", "installationId": iid,
                               "revisionId": first_revision, "routingAlias": "alpha",
                               "conflict": "select-new"})
    assert manager.store.read_registry()["generation"] == generation + 1
    assert reader.read_active("alpha")["installation"]["revisionId"] == first_revision
    assert _snapshot(manager.store._object_path(bundle["revisionId"])) == original_object
    assert next(item for item in manager.store.read_registry()["installations"]
                if item["installationId"] == bundle["installationId"])["revisionId"] == bundle["revisionId"]


def test_no_implicit_conversion_or_unowned_write(managed):
    manager, before, tmp_path = managed
    request, package = package_request(tmp_path / "new", "create-local", "new", "new")
    snapshot = _snapshot(manager.store.root)
    with pytest.raises(legacy.SkillStoreError) as caught:
        apply(manager, "new", request, package=package)
    assert caught.value.code == "management_conversion_required"
    assert _snapshot(manager.store.root) == snapshot
    with pytest.raises(legacy.SkillStoreError) as caught:
        management.SkillStoreManager(manager.store, owner=None)
    assert caught.value.code == "management_owner_required"
    assert manager.store.read_registry() == before


def test_selected_local_does_not_fall_back_to_bundle(managed):
    manager, _, tmp_path = managed
    convert(manager)
    bundle = installation(manager, "alpha")
    request, package = package_request(tmp_path / "fork", "fork-bundled", "alpha", "fork",
                                       iid=bundle["installationId"], conflict="select-new")
    iid = apply(manager, "fork", request, package=package)["result"]["installationId"]
    for key, request in (
        ("disable", {"kind": "set-enabled", "installationId": iid, "enabled": False}),
        ("uninstall", {"kind": "uninstall", "installationId": iid}),
        ("restore", {"kind": "restore", "installationId": iid}),
    ):
        apply(manager, key, request)
        binding = next(b for b in manager.store.read_registry()["bindings"] if b["routingAlias"] == "alpha")
        assert binding["selectedInstallationId"] == iid
        assert binding["activeCandidate"] is None
        with pytest.raises(legacy.SkillStoreError) as caught:
            legacy.SkillStoreReader(manager.store.data_root).read_active("alpha")
        assert caught.value.code == "store_binding_unavailable"
    apply(manager, "choose-bundle", {"kind": "select-candidate", "routingAlias": "alpha",
                                     "installationId": bundle["installationId"]})
    assert legacy.SkillStoreReader(manager.store.data_root).read_active("alpha")["installation"]["skillId"] == bundle["skillId"]


@pytest.mark.parametrize("kind", ["create-local", "import-local"])
def test_local_creation_and_offline_catalog_update(managed, kind):
    manager, _, tmp_path = managed
    convert(manager)
    request, package = package_request(tmp_path / "new", kind, "new", "local package")
    receipt = apply(manager, "new", request, package=management.capture_package(package))
    assert installation(manager, "new")["installationId"] == receipt["result"]["installationId"]
    alpha = installation(manager, "alpha")
    request, package = package_request(tmp_path / "catalog", "update-bundled", "alpha", "offline upgrade",
                                       iid=alpha["installationId"])
    request["catalog"] = revisions.build_bundled_catalog(package.parent, {"alpha": alpha["skillId"]})
    apply(manager, "upgrade", request, package=package)
    updated = next(item for item in manager.store.read_registry()["installations"]
                   if item["installationId"] == alpha["installationId"])
    assert updated["kind"] == "bundled"
    assert updated["skillId"] == alpha["skillId"]
    assert updated["retainedRevisionIds"] == sorted([alpha["revisionId"], request["revisionId"]])


def test_profile_enablement_and_explicit_preference_reduction(managed):
    manager, _, _ = managed
    convert(manager)
    before = manager.store.read_registry()
    with pytest.raises(legacy.SkillStoreError) as caught:
        apply(manager, "prefs", {"kind": "migrate-preferences", "disabledNames": ["alpha"], "confirmed": False})
    assert caught.value.code == "management_confirmation_required"
    assert manager.store.read_registry() == before
    apply(manager, "prefs", {"kind": "migrate-preferences", "disabledNames": ["alpha"], "confirmed": True})
    assert not installation(manager, "alpha")["enabled"]
    apply(manager, "prefs-empty", {"kind": "migrate-preferences", "disabledNames": [], "confirmed": True})
    assert not installation(manager, "alpha")["enabled"]
    assert installation(manager, "custom")["enabled"]
    # Independent readers of this profile see the same disabled selection.
    for _ in range(2):
        with pytest.raises(legacy.SkillStoreError) as caught:
            legacy.SkillStoreReader(manager.store.data_root).read_active("alpha")
        assert caught.value.code == "store_binding_unavailable"


def test_case_only_rename_preserves_local_identity(managed):
    manager, _, tmp_path = managed
    convert(manager)
    old = installation(manager, "custom")
    request, package = package_request(tmp_path / "case", "edit-local", "CUSTOM", "case rename",
                                       iid=old["installationId"])
    apply(manager, "case", request, package=package)
    updated = installation(manager, "CUSTOM")
    assert updated["skillId"] == old["skillId"]
    assert updated["installationId"] == old["installationId"]
    assert legacy.SkillStoreReader(manager.store.data_root).read_active("custom")["installation"]["installationId"] == old["installationId"]
