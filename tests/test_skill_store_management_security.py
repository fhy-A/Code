"""Exact schemas, identities, filesystem limits, and fail-closed cleanup."""
import copy
import json
import os

import pytest

from code_runtime import data_dir_owner
from code_runtime import skill_revisions as revisions
from code_runtime import skill_store as legacy
from code_runtime import skill_store_management as management
from code_runtime import skill_store_v2 as metadata
from tests.test_skill_store import _snapshot
from tests.test_skill_store_management import apply, convert, installation, managed, package_request


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(schema="code-skill-install-registry/v3"),
    lambda r: r.update(generation=True),
    lambda r: r.update(generation=2**53 - 1),
    lambda r: r["installations"][0].update(retainedRevisionIds=[]),
    lambda r: r["installations"][0].update(kind=[]),
    lambda r: r["installations"][0].update(enabled=1),
    lambda r: r["installations"][0].update(extra="unknown"),
    lambda r: r["bindings"].append(copy.deepcopy(r["bindings"][0])),
    lambda r: r["bindings"][0].update(selectedInstallationId="si1_" + "f" * 32),
    lambda r: r["operationReceipts"][-1].update(kind=[]),
    lambda r: r["operationReceipts"][-1]["result"].update(revisionId="sha256:" + "f" * 64),
])
def test_exact_registry_rejects_unknown_tampered_or_oversized_identity(managed, mutate):
    manager, _, _ = managed
    convert(manager)
    registry = manager.store.read_registry()
    mutate(registry)
    registry["registryHash"] = legacy._registry_hash(registry)
    with pytest.raises(legacy.SkillStoreError):
        legacy.normalize_registry(registry)


@pytest.mark.parametrize("change", [
    {"kind": "unknown"}, {"kind": []}, {"conflict": []},
    {"routingAlias": "../outside"}, {"routingAlias": "ALPHA/other"},
    {"revisionId": "sha256:" + "A" * 64}, {"extra": True},
])
def test_request_rejection_is_zero_write(managed, change):
    manager, _, tmp_path = managed
    convert(manager)
    request, package = package_request(tmp_path / "new", "import-local", "new", "safe")
    request.update(change)
    before = _snapshot(manager.store.root)
    with pytest.raises((legacy.SkillStoreError, revisions.SkillRevisionError)):
        apply(manager, "request", request, package=package)
    assert _snapshot(manager.store.root) == before


def test_current_registry_requires_complete_verified_journal_lineage(managed):
    manager, _, _ = managed
    convert(manager)
    journal_paths = list((manager.store.root / "transactions").glob("op2_*.json"))
    assert len(journal_paths) == 1
    journal_paths[0].unlink()
    with pytest.raises(legacy.SkillStoreError) as caught:
        legacy.SkillStoreReader(manager.store.data_root).read_registry()
    assert caught.value.code == "management_lineage_invalid"


def test_unknown_object_is_not_eligible_and_never_deleted(managed):
    manager, _, _ = managed
    convert(manager)
    unknown = manager.store._object_path("sha256:" + "f" * 64)
    unknown.mkdir(parents=True)
    marker = unknown / "private.txt"
    marker.write_text("unrecognized material", encoding="utf-8")
    with pytest.raises(legacy.SkillStoreError) as caught:
        manager.recover()
    assert caught.value.code == "store_object_unknown"
    assert marker.read_text(encoding="utf-8") == "unrecognized material"


def test_known_name_but_unknown_temp_bytes_are_not_deleted(managed):
    manager, _, _ = managed
    receipt = convert(manager)
    unknown = manager.store.root / f".registry.json.{receipt['operationId']}.{'f' * 32}.tmp"
    unknown.write_text('{"unrelated":"retain"}', encoding="utf-8")
    with pytest.raises(legacy.SkillStoreError) as caught:
        manager.recover()
    assert caught.value.code == "store_temp_unknown"
    assert unknown.read_text(encoding="utf-8") == '{"unrelated":"retain"}'


def test_captured_package_and_manifest_cannot_disagree(managed):
    manager, _, tmp_path = managed
    convert(manager)
    request, package = package_request(tmp_path / "new", "import-local", "new", "original")
    captured = management.capture_package(package)
    changed = management.CapturedPackage(captured.manifest, (("SKILL.md", b"changed"),))
    before = _snapshot(manager.store.root)
    with pytest.raises(legacy.SkillStoreError) as caught:
        apply(manager, "import", request, package=changed)
    assert caught.value.code == "management_package_invalid"
    assert _snapshot(manager.store.root) == before


@pytest.mark.parametrize("extra", [
    {"dependencies.json": '{"schemaVersion":99,"skill":"new","capabilities":{}}'},
    {"evidence.json": '{"schemaVersion":99,"requirements":[]}'},
    {"code-resources.json": '{"schemaVersion":99,"skill":"new","resources":[]}'},
    {"code-resources.json": json.dumps({"schemaVersion": 1, "skill": "new", "resources": [{
        "id": "escape", "path": "../outside.py", "sha256": "f" * 64, "kind": "python",
        "protocol": "code-test/v1", "modelVisible": True, "arguments": [],
    }]})},
])
def test_invalid_contracts_and_resource_escape_are_not_installed(managed, extra):
    manager, _, tmp_path = managed
    convert(manager)
    request, package = package_request(tmp_path / "new", "import-local", "new", "body")
    for name, text in extra.items():
        (package / name).write_text(text, encoding="utf-8")
    request["revisionId"] = revisions.build_skill_revision(package)["revisionId"]
    before = _snapshot(manager.store.root)
    with pytest.raises(legacy.SkillStoreError):
        apply(manager, "import", request, package=package)
    assert _snapshot(manager.store.root) == before


def test_source_hardlink_is_rejected_before_capture(managed):
    manager, _, tmp_path = managed
    convert(manager)
    request, package = package_request(tmp_path / "new", "import-local", "new", "body")
    os.link(package / "SKILL.md", tmp_path / "hardlinked.md")
    before = _snapshot(manager.store.root)
    with pytest.raises(legacy.SkillStoreError) as caught:
        apply(manager, "import", request, package=package)
    assert caught.value.code == "store_path_unsafe"
    assert _snapshot(manager.store.root) == before


@pytest.mark.parametrize("limit", ["MAX_NEW_OBJECT_BYTES", "MAX_STORE_BYTES", "MAX_TRANSACTIONS", "MAX_RECEIPTS", "MAX_OBJECTS"])
def test_capacity_is_stable_rejection_not_gc(managed, monkeypatch, limit):
    manager, _, tmp_path = managed
    convert(manager)
    base = manager.store.read_registry()
    request, package = package_request(tmp_path / "new", "create-local", "new", "body")
    before = _snapshot(manager.store.root)
    values = {"MAX_NEW_OBJECT_BYTES": 1, "MAX_STORE_BYTES": legacy._safe_tree_bytes(manager.store.root) + 1,
              "MAX_TRANSACTIONS": 2, "MAX_RECEIPTS": 2, "MAX_OBJECTS": len(manager.store._inspect_layout())}
    monkeypatch.setattr(legacy, limit, values[limit])
    with pytest.raises(legacy.SkillStoreError):
        apply(manager, "new", request, package=package, base=base)
    assert _snapshot(manager.store.root) == before


def test_catalog_identity_does_not_override_installation_identity(managed):
    manager, _, tmp_path = managed
    convert(manager)
    alpha = installation(manager, "alpha")
    request, package = package_request(tmp_path / "catalog", "update-bundled", "alpha", "update",
                                       iid=alpha["installationId"])
    request["catalog"] = revisions.build_bundled_catalog(package.parent, {"alpha": "code.bundle/impostor"})
    before = _snapshot(manager.store.root)
    with pytest.raises(legacy.SkillStoreError) as caught:
        apply(manager, "upgrade", request, package=package)
    assert caught.value.code == "management_catalog_identity_mismatch"
    assert _snapshot(manager.store.root) == before


def test_malformed_metadata_shapes_fail_with_bounded_errors(managed):
    manager, _, _ = managed
    convert(manager)
    original = manager.store.read_registry()
    paths = [
        ("sourceObservations", 0, "sourceKind"), ("bundledTombstones",),
        ("installations", 0, "kind"), ("installations", 0, "sourceState"),
        ("installations", 0, "retainedRevisionIds"), ("bindings", 0, "activeCandidate"),
        ("bindings", 0, "selectedInstallationId"), ("bindings", 0, "candidates"),
        ("operationReceipts", -1, "result"), ("operationReceipts", -1, "requestHash"),
    ]
    for path in paths:
        for bad in ([], {}, 42):
            changed = copy.deepcopy(original)
            target = changed
            for key in path[:-1]:
                target = target[key]
            if target[path[-1]] == bad:
                continue  # An unchanged empty tombstone list is valid, not a mutation.
            target[path[-1]] = bad
            changed["registryHash"] = legacy._registry_hash(changed)
            with pytest.raises(legacy.SkillStoreError):
                metadata.normalize_registry(changed)


def test_malformed_captured_manifest_is_a_closed_error(managed):
    manager, _, tmp_path = managed
    convert(manager)
    request, package = package_request(tmp_path / "bad", "import-local", "new", "body")
    captured = management.capture_package(package)
    captured.manifest["files"][0]["contentMode"] = []
    with pytest.raises(legacy.SkillStoreError) as caught:
        apply(manager, "bad", request, package=captured)
    assert caught.value.code == "management_package_invalid"


def test_released_wrong_profile_and_default_off_owners_reject(managed, tmp_path):
    manager, _, _ = managed
    with data_dir_owner.acquire_data_dir_owner(tmp_path / "other") as other:
        with pytest.raises(legacy.SkillStoreError) as caught:
            management.SkillStoreManager(manager.store, owner=other)
        assert caught.value.code == "management_owner_mismatch"
    reader_only = legacy.SkillStore(manager.store.data_root, manager.store.bundled_root)
    with pytest.raises(legacy.SkillStoreError) as caught:
        management.SkillStoreManager(reader_only, owner=manager.owner)
    assert caught.value.code == "store_writes_disabled"
    manager.owner.release()
    before = _snapshot(manager.store.root)
    with pytest.raises(legacy.SkillStoreError) as caught:
        convert(manager)
    assert caught.value.code == "management_owner_required"
    assert _snapshot(manager.store.root) == before
