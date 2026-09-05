import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from code_runtime import skill_revisions as revisions
from code_runtime import skill_store


def _write_skill(root, name, body="body", extra=None, newline="\n"):
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_bytes(
        newline.join(("---", f"name: {name}", "description: test", "---", "", body)).encode()
    )
    for relative, value in (extra or {}).items():
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else value.encode())
    return directory


def _fixture(tmp_path, *, installed=True):
    data = tmp_path / "profile"
    bundle = tmp_path / "bundle"
    data.mkdir(parents=True); bundle.mkdir(parents=True)
    bundled = _write_skill(bundle, "alpha", extra={"nested/text.txt": "a\r\n"})
    if installed:
        (data / "skills").mkdir()
        shutil.copytree(bundled, data / "skills" / "alpha")
    catalog = revisions.build_bundled_catalog(bundle, {"alpha": "code.bundle/alpha"})
    return data, bundle, catalog


def _snapshot(root):
    if not root.exists():
        return None
    return {
        path.relative_to(root).as_posix(): ("dir" if path.is_dir() else path.read_bytes())
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if not path.is_symlink()
    }


def _store(data, bundle, fault=None, timeout=5):
    return skill_store.SkillStore(
        data, bundle, write_enabled=True, fault_injector=fault, lock_timeout=timeout,
    )


def _by_alias(registry):
    return {item["routingAlias"]: item for item in registry["bindings"]}


def _reseal(registry):
    registry["operationReceipts"][0]["resultStateHash"] = skill_store._state_hash(registry)
    registry["registryHash"] = skill_store._registry_hash(registry)
    return registry


def test_store_is_explicit_and_default_off(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    with pytest.raises(ValueError):
        skill_store.SkillStore(None, bundle)
    store = skill_store.SkillStore(data, bundle)
    with pytest.raises(skill_store.SkillStoreError) as caught:
        store.bootstrap(catalog)
    assert caught.value.code == "store_writes_disabled"
    assert not (data / skill_store.STORE_DIRECTORY).exists()


def test_invalid_legacy_state_is_zero_write_preflight(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    state = data / "bundled-skills-state.json"
    state.write_text("{broken", encoding="utf-8")
    before = _snapshot(data)
    with pytest.raises(revisions.SkillRevisionError) as caught:
        _store(data, bundle).bootstrap(catalog)
    assert caught.value.code == "legacy_state_invalid"
    assert _snapshot(data) == before
    assert not (data / skill_store.STORE_DIRECTORY).exists()


def test_invalid_catalog_is_zero_write_preflight(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    catalog["skills"][0]["skillId"] = "invalid"
    before = _snapshot(data)
    with pytest.raises(revisions.SkillRevisionError):
        _store(data, bundle).bootstrap(catalog)
    assert _snapshot(data) == before
    assert not (data / skill_store.STORE_DIRECTORY).exists()


def test_exact_and_custom_bootstrap_preserves_legacy_bytes(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    _write_skill(data / "skills", "custom", body="custom")
    legacy_before = _snapshot(data / "skills")
    registry = _store(data, bundle).bootstrap(catalog)
    assert registry["schema"] == skill_store.REGISTRY_SCHEMA
    assert registry["generation"] == 0
    assert registry["registryHash"].startswith("sha256:")
    bindings = _by_alias(registry)
    assert bindings["alpha"]["state"] == "ready"
    assert bindings["custom"]["state"] == "ready"
    installations = {item["kind"]: item for item in registry["installations"]}
    assert installations["bundled"]["skillId"] == "code.bundle/alpha"
    assert installations["local"]["skillId"].startswith("local.skill/")
    assert _snapshot(data / "skills") == legacy_before
    assert not (data / "bundled-skills-state.json").exists()
    assert _store(data, bundle).read_registry() == registry


def test_stored_text_is_canonical_and_binary_is_raw(tmp_path):
    data, bundle, _catalog = _fixture(tmp_path)
    binary = b"\x00a\r\nb"
    (data / "skills" / "alpha" / "binary.bin").write_bytes(binary)
    shutil.rmtree(bundle / "alpha")
    shutil.copytree(data / "skills" / "alpha", bundle / "alpha")
    catalog = revisions.build_bundled_catalog(bundle, {"alpha": "code.bundle/alpha"})
    registry = _store(data, bundle).bootstrap(catalog)
    revision_id = registry["installations"][0]["revisionId"]
    obj = _store(data, bundle)._object_path(revision_id)
    assert (obj / "content" / "nested" / "text.txt").read_bytes() == b"a\n"
    assert (obj / "content" / "binary.bin").read_bytes() == binary


def test_same_name_modified_and_tombstone_conflicts_are_blocked(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    (data / "skills" / "alpha" / "SKILL.md").write_text("local modification", encoding="utf-8")
    registry = _store(data, bundle).bootstrap(catalog)
    binding = _by_alias(registry)["alpha"]
    assert binding["state"] == "blocked"
    assert binding["reasonCode"] == "same-name-modified"
    assert binding["activeCandidate"] is None
    assert len(binding["candidates"]) == 2

    data2, bundle2, catalog2 = _fixture(tmp_path / "tombstone")
    (data2 / "bundled-skills-state.json").write_text(json.dumps({
        "schema": "code-bundled-skills/v1", "tombstones": ["alpha"],
    }), encoding="utf-8")
    registry2 = _store(data2, bundle2).bootstrap(catalog2)
    assert _by_alias(registry2)["alpha"]["state"] == "blocked"
    assert _by_alias(registry2)["alpha"]["reasonCode"] == "tombstone-conflict"


def test_unmatched_tombstone_does_not_shadow_local_custom(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    _write_skill(data / "skills", "retired", body="unrelated local")
    (data / "bundled-skills-state.json").write_text(json.dumps({
        "schema": "code-bundled-skills/v1", "tombstones": ["retired"],
    }), encoding="utf-8")
    registry = _store(data, bundle).bootstrap(catalog)
    assert _by_alias(registry)["retired"]["state"] == "ready"
    tombstone = next(item for item in registry["bundledTombstones"] if item["legacyName"] == "retired")
    assert tombstone == {
        "legacyName": "retired", "skillId": None,
        "catalogRevisionId": None, "state": "unmatched",
    }


def test_absent_bundled_tombstone_stays_tombstoned(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    shutil.rmtree(data / "skills" / "alpha")
    (data / "bundled-skills-state.json").write_text(json.dumps({
        "schema": "code-bundled-skills/v1", "tombstones": ["alpha"],
    }), encoding="utf-8")
    registry = _store(data, bundle).bootstrap(catalog)
    binding = _by_alias(registry)["alpha"]
    assert binding["state"] == "tombstoned"
    assert binding["activeCandidate"] is None
    assert not registry["installations"]


def test_missing_root_never_becomes_active(tmp_path):
    data, bundle, catalog = _fixture(tmp_path, installed=False)
    registry = _store(data, bundle).bootstrap(catalog)
    binding = _by_alias(registry)["alpha"]
    assert binding["state"] == "blocked"
    assert binding["reasonCode"] == "legacy-root-missing"
    assert binding["activeCandidate"] is None


def test_invalid_skill_entry_is_observed_but_not_imported(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    invalid = data / "skills" / "broken"
    invalid.mkdir()
    (invalid / "not-skill.txt").write_text("opaque", encoding="utf-8")
    registry = _store(data, bundle).bootstrap(catalog)
    binding = _by_alias(registry)["broken"]
    assert binding["state"] == "blocked"
    assert binding["reasonCode"] == "source-invalid"
    assert not binding["candidates"]
    assert all(item["displayName"] != "broken" for item in registry["installations"])


def test_shared_development_never_becomes_active(tmp_path):
    data = tmp_path / "profile"
    bundle = data / "skills"
    data.mkdir(); _write_skill(bundle, "alpha")
    catalog = revisions.build_bundled_catalog(bundle, {"alpha": "code.bundle/alpha"})
    registry = _store(data, bundle).bootstrap(catalog)
    binding = _by_alias(registry)["alpha"]
    assert binding["state"] == "blocked"
    assert binding["reasonCode"] == "shared-development-unconfirmed"


def test_same_request_is_a_post_commit_noop_with_stable_ids(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    _write_skill(data / "skills", "custom")
    store = _store(data, bundle)
    first = store.bootstrap(catalog)
    journal_path = next((data / skill_store.STORE_DIRECTORY / "transactions").glob("*.json"))
    journal_before = journal_path.read_bytes()
    tree_before = _snapshot(data / skill_store.STORE_DIRECTORY)
    second = store.bootstrap(catalog)
    assert second == first
    assert second["generation"] == 0
    assert journal_path.read_bytes() == journal_before
    assert _snapshot(data / skill_store.STORE_DIRECTORY) == tree_before


def test_changed_logical_request_after_commit_fails_closed(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    store = _store(data, bundle)
    first = store.bootstrap(catalog)
    (data / "skills" / "alpha" / "SKILL.md").write_text("changed", encoding="utf-8")
    with pytest.raises(skill_store.SkillStoreError) as caught:
        store.bootstrap(catalog)
    assert caught.value.code == "bootstrap_already_committed_conflict"
    assert store.read_registry() == first


def test_different_catalog_request_cannot_create_second_bootstrap(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    store = _store(data, bundle)
    first = store.bootstrap(catalog)
    alternate = revisions.build_bundled_catalog(bundle, {"alpha": "code.bundle/alternate"})
    with pytest.raises(skill_store.SkillStoreError) as caught:
        store.bootstrap(alternate)
    assert caught.value.code == "bootstrap_already_committed_conflict"
    assert store.read_registry() == first
    assert len(list((data / skill_store.STORE_DIRECTORY / "transactions").glob("*.json"))) == 1


def test_request_hash_is_logical_and_base_is_separate(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    registry = _store(data, bundle).bootstrap(catalog)
    journal = json.loads(next((data / skill_store.STORE_DIRECTORY / "transactions").glob("*.json")).read_text(encoding="utf-8"))
    receipt = registry["operationReceipts"][0]
    assert journal["requestHash"] == receipt["requestHash"]
    assert journal["baseRegistry"] == {"generation": None, "registryHash": None}
    assert receipt["resultStateHash"] == skill_store._state_hash(registry)


class _CrashOnce:
    def __init__(self, point):
        self.point = point
        self.seen = False

    def __call__(self, point):
        if point == self.point and not self.seen:
            self.seen = True
            raise skill_store.SkillStoreInterruption(point)


@pytest.mark.parametrize("point", [
    "after-skeleton",
    "after-journal-prepared-temp",
    "after-journal-prepared-publish",
    "after-root-temp",
    "after-root-publish",
    "after-staging-file",
    "after-journal-staged-verified-publish",
    "after-object-publish",
    "after-registry-temp",
    "after-registry-publish",
    "after-journal-committed-publish",
])
def test_every_crash_boundary_recovers_idempotently(tmp_path, point):
    data, bundle, catalog = _fixture(tmp_path)
    crash = _CrashOnce(point)
    with pytest.raises(skill_store.SkillStoreInterruption):
        _store(data, bundle, crash).bootstrap(catalog)
    registry = _store(data, bundle).bootstrap(catalog)
    assert _store(data, bundle).read_registry() == registry
    assert registry["generation"] == 0
    journals = list((data / skill_store.STORE_DIRECTORY / "transactions").glob("*.json"))
    assert len(journals) == 1
    assert json.loads(journals[0].read_text(encoding="utf-8"))["phase"] == "committed"


def test_ids_recorded_at_prepare_survive_restart(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    _write_skill(data / "skills", "custom")
    crash = _CrashOnce("after-journal-prepared-publish")
    with pytest.raises(skill_store.SkillStoreInterruption):
        _store(data, bundle, crash).bootstrap(catalog)
    journal_path = next((data / skill_store.STORE_DIRECTORY / "transactions").glob("*.json"))
    prepared = json.loads(journal_path.read_text(encoding="utf-8"))
    expected = {(item["installationId"], item["skillId"]) for item in prepared["targetRegistry"]["installations"]}
    completed = _store(data, bundle).bootstrap(catalog)
    assert {(item["installationId"], item["skillId"]) for item in completed["installations"]} == expected


@pytest.mark.parametrize("point,remove_source", [
    ("after-journal-staged-verified-publish", False),
    ("after-object-publish", True),
    ("after-registry-publish", False),
])
def test_late_recovery_uses_captured_objects_not_changed_legacy(tmp_path, point, remove_source):
    data, bundle, catalog = _fixture(tmp_path)
    custom = _write_skill(data / "skills", "custom", body="captured")
    with pytest.raises(skill_store.SkillStoreInterruption):
        _store(data, bundle, _CrashOnce(point)).bootstrap(catalog)
    journal_path = next((data / skill_store.STORE_DIRECTORY / "transactions").glob("*.json"))
    target_registry = json.loads(journal_path.read_text(encoding="utf-8"))["targetRegistry"]
    if remove_source:
        shutil.rmtree(custom)
    else:
        (custom / "SKILL.md").write_text("changed after capture", encoding="utf-8")
    with pytest.raises(skill_store.SkillStoreError) as caught:
        _store(data, bundle).bootstrap(catalog)
    assert caught.value.code == "bootstrap_already_committed_conflict"
    assert _store(data, bundle).read_registry() == target_registry
    assert json.loads(journal_path.read_text(encoding="utf-8"))["phase"] == "committed"
    assert not custom.exists() if remove_source else (custom / "SKILL.md").read_text(encoding="utf-8") == "changed after capture"


@pytest.mark.parametrize("point", ["after-journal-prepared-publish", "after-staging-file"])
def test_early_recovery_blocks_when_source_changed(tmp_path, point):
    data, bundle, catalog = _fixture(tmp_path)
    custom = _write_skill(data / "skills", "custom", body="prepared")
    with pytest.raises(skill_store.SkillStoreInterruption):
        _store(data, bundle, _CrashOnce(point)).bootstrap(catalog)
    journal_path = next((data / skill_store.STORE_DIRECTORY / "transactions").glob("*.json"))
    before = journal_path.read_bytes()
    (custom / "SKILL.md").write_text("changed too early", encoding="utf-8")
    with pytest.raises(skill_store.SkillStoreError) as caught:
        _store(data, bundle).bootstrap(catalog)
    assert caught.value.code == "bootstrap_recovery_source_conflict"
    assert journal_path.read_bytes() == before
    assert not (data / skill_store.STORE_DIRECTORY / "registry.json").exists()


def test_explicit_local_identity_hint_is_durable(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    _write_skill(data / "skills", "custom")
    hint = {"custom": {
        "skillId": "local.skill/" + "1" * 32,
        "installationId": "si1_" + "2" * 32,
    }}
    registry = _store(data, bundle).bootstrap(catalog, identity_hints=hint)
    custom = next(item for item in registry["installations"] if item["kind"] == "local")
    assert custom["skillId"] == hint["custom"]["skillId"]
    assert custom["installationId"] == hint["custom"]["installationId"]
    assert _store(data, bundle).bootstrap(catalog, identity_hints=hint) == registry


def test_same_request_threads_share_one_transaction(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _item: _store(data, bundle).bootstrap(catalog), range(4)))
    assert all(item == results[0] for item in results)
    assert len(list((data / skill_store.STORE_DIRECTORY / "transactions").glob("*.json"))) == 1


def test_same_request_processes_share_one_transaction(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(revisions.render_bundled_catalog(catalog), encoding="utf-8", newline="\n")
    script = (
        "import sys; from code_runtime import skill_revisions as r, skill_store as s; "
        "c=r.load_bundled_catalog(sys.argv[3]); "
        "x=s.SkillStore(sys.argv[1],sys.argv[2],write_enabled=True).bootstrap(c); "
        "print(x['registryHash'])"
    )
    command = [sys.executable, "-c", script, str(data), str(bundle), str(catalog_path)]
    processes = [subprocess.Popen(command, cwd=Path(__file__).parents[1], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    outputs = [process.communicate(timeout=30) for process in processes]
    assert [process.returncode for process in processes] == [0, 0], outputs
    assert outputs[0][0].strip() == outputs[1][0].strip()
    assert len(list((data / skill_store.STORE_DIRECTORY / "transactions").glob("*.json"))) == 1


def test_corrupt_referenced_object_has_no_fallback(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    store = _store(data, bundle)
    registry = store.bootstrap(catalog)
    revision_id = registry["installations"][0]["revisionId"]
    content = store._object_path(revision_id) / "content" / "SKILL.md"
    content.write_bytes(content.read_bytes() + b"tamper")
    with pytest.raises(skill_store.SkillStoreError) as caught:
        store.read_registry()
    assert caught.value.code == "object_corrupt"
    assert (data / "skills" / "alpha" / "SKILL.md").exists()


def test_corrupt_published_object_is_not_overwritten_on_recovery(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    crash = _CrashOnce("after-object-publish")
    with pytest.raises(skill_store.SkillStoreInterruption):
        _store(data, bundle, crash).bootstrap(catalog)
    store = _store(data, bundle)
    journal = json.loads(next((data / skill_store.STORE_DIRECTORY / "transactions").glob("*.json")).read_text(encoding="utf-8"))
    target = store._object_path(journal["objectRevisionIds"][0]) / "content" / "SKILL.md"
    target.write_bytes(target.read_bytes() + b"corrupt")
    corrupted = target.read_bytes()
    with pytest.raises(skill_store.SkillStoreError) as caught:
        store.bootstrap(catalog)
    assert caught.value.code == "object_corrupt"
    assert target.read_bytes() == corrupted


def test_unknown_partial_staging_is_preserved(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    crash = _CrashOnce("after-staging-file")
    with pytest.raises(skill_store.SkillStoreInterruption):
        _store(data, bundle, crash).bootstrap(catalog)
    journal = json.loads(next((data / skill_store.STORE_DIRECTORY / "transactions").glob("*.json")).read_text(encoding="utf-8"))
    unknown = data / skill_store.STORE_DIRECTORY / "staging" / journal["operationId"] / "objects" / "sha256" / journal["objectRevisionIds"][0][7:9] / journal["objectRevisionIds"][0][7:] / "unknown"
    unknown.write_bytes(b"preserve")
    with pytest.raises(skill_store.SkillStoreError) as caught:
        _store(data, bundle).bootstrap(catalog)
    assert caught.value.code == "staging_unknown"
    assert unknown.read_bytes() == b"preserve"


def test_unknown_store_entry_is_preserved_and_blocks(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    store = _store(data, bundle)
    store.bootstrap(catalog)
    unknown = data / skill_store.STORE_DIRECTORY / "unknown.bin"
    unknown.write_bytes(b"keep")
    with pytest.raises(skill_store.SkillStoreError) as caught:
        store.bootstrap(catalog)
    assert caught.value.code == "store_layout_unknown"
    assert unknown.read_bytes() == b"keep"


def test_store_file_lock_has_a_bounded_busy_result(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    script = (
        "import sys; from code_runtime import skill_store as s; "
        "x=s.SkillStore(sys.argv[1],sys.argv[2],write_enabled=True); "
        "c=x._mutation_lock(); c.__enter__(); print('locked',flush=True); sys.stdin.read(1); c.__exit__(None,None,None)"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(data), str(bundle)],
        cwd=Path(__file__).parents[1], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    try:
        assert child.stdout.readline().strip() == "locked"
        with pytest.raises(skill_store.SkillStoreError) as caught:
            _store(data, bundle, timeout=0.05).bootstrap(catalog)
        assert caught.value.code == "store_busy"
    finally:
        child.stdin.write("x"); child.stdin.flush()
        child.communicate(timeout=10)


def test_move_and_clone_preserve_lineage_without_path_identity(tmp_path):
    data, bundle, catalog = _fixture(tmp_path / "source")
    registry = _store(data, bundle).bootstrap(catalog)
    clone = tmp_path / "clone"
    shutil.copytree(data, clone)
    cloned = _store(clone, bundle).read_registry()
    assert cloned["dataRootId"] == registry["dataRootId"]
    assert cloned["registryHash"] == registry["registryHash"]
    moved = tmp_path / "moved"
    shutil.move(data, moved)
    assert _store(moved, bundle).read_registry() == registry
    assert _store(clone, bundle).root != _store(moved, bundle).root


@pytest.mark.parametrize("mutation,code", [
    (lambda value: value.update(extra=True), "registry_invalid"),
    (lambda value: value.update(generation=-1), "registry_generation_invalid"),
    (lambda value: value.update(registryHash="sha256:" + "0" * 64), "registry_hash_mismatch"),
])
def test_registry_schema_corruption_fails_closed(tmp_path, mutation, code):
    data, bundle, catalog = _fixture(tmp_path)
    store = _store(data, bundle)
    store.bootstrap(catalog)
    path = data / skill_store.STORE_DIRECTORY / "registry.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    mutation(value)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(skill_store.SkillStoreError) as caught:
        store.read_registry()
    assert caught.value.code == code


@pytest.mark.parametrize("bad", ["unknown-code", {}, [], "x" * 500])
def test_binding_reason_code_is_closed_and_bounded(tmp_path, bad):
    data, bundle, catalog = _fixture(tmp_path)
    (data / "skills" / "alpha" / "SKILL.md").write_text("modified", encoding="utf-8")
    registry = _store(data, bundle).bootstrap(catalog)
    candidate = copy.deepcopy(registry)
    candidate["bindings"][0]["reasonCode"] = bad
    _reseal(candidate)
    with pytest.raises(skill_store.SkillStoreError) as caught:
        skill_store.normalize_registry(candidate)
    assert caught.value.code == "registry_bindings_invalid"


@pytest.mark.parametrize("state,bad", [
    ("invalid", "unknown-code"),
    ("invalid", {}),
    ("invalid", []),
    ("invalid", "x" * 500),
    ("missing", "source-missing"),
    ("missing", {}),
    ("missing", []),
    ("missing", "x" * 500),
])
def test_observation_error_code_is_closed_and_state_bound(tmp_path, state, bad):
    data, bundle, catalog = _fixture(tmp_path)
    invalid = data / "skills" / "broken"
    invalid.mkdir(); (invalid / "not-skill.txt").write_text("x", encoding="utf-8")
    registry = _store(data, bundle).bootstrap(catalog)
    candidate = copy.deepcopy(registry)
    index = next(i for i, item in enumerate(candidate["sourceObservations"]) if item["state"] == "invalid")
    old = candidate["sourceObservations"][index]
    replacement = skill_store._observation(
        old["sourceKind"], old["locator"]["rootKind"], old["locator"]["directoryToken"],
        state, None, old["catalogHash"], bad,
    )
    candidate["sourceObservations"][index] = replacement
    candidate["sourceObservations"].sort(key=lambda item: item["sourceObservationId"])
    _reseal(candidate)
    with pytest.raises(skill_store.SkillStoreError) as caught:
        skill_store.normalize_registry(candidate)
    assert caught.value.code == "registry_observations_invalid"


def test_missing_observation_accepts_only_null_error(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    invalid = data / "skills" / "broken"
    invalid.mkdir(); (invalid / "not-skill.txt").write_text("x", encoding="utf-8")
    candidate = copy.deepcopy(_store(data, bundle).bootstrap(catalog))
    index = next(i for i, item in enumerate(candidate["sourceObservations"]) if item["state"] == "invalid")
    old = candidate["sourceObservations"][index]
    candidate["sourceObservations"][index] = skill_store._observation(
        old["sourceKind"], old["locator"]["rootKind"], old["locator"]["directoryToken"],
        "missing", None, old["catalogHash"], None,
    )
    candidate["sourceObservations"].sort(key=lambda item: item["sourceObservationId"])
    assert skill_store.normalize_registry(_reseal(candidate)) == candidate


def test_read_only_store_reader_contract_exists():
    assert hasattr(skill_store, "SkillStoreReader")


_EMPTY_LAYOUTS = [
    tuple(name for bit, name in enumerate((
        "registry.lock", "objects/sha256", "transactions", "staging",
    )) if mask & 1 << bit)
    for mask in range(16)
] + [("objects",)]


@pytest.mark.parametrize("layout", _EMPTY_LAYOUTS)
def test_invalid_catalog_preserves_partial_empty_skeleton_byte_for_byte(tmp_path, layout):
    data, bundle, catalog = _fixture(tmp_path)
    root = data / skill_store.STORE_DIRECTORY
    root.mkdir()
    for relative in layout:
        path = root / relative
        if relative == "registry.lock":
            path.write_bytes(b"")
        else:
            path.mkdir(parents=True)
    catalog["skills"][0]["skillId"] = "invalid"
    before = _snapshot(root)
    with pytest.raises(revisions.SkillRevisionError):
        _store(data, bundle).bootstrap(catalog)
    assert _snapshot(root) == before


@pytest.mark.parametrize("layout", _EMPTY_LAYOUTS)
def test_valid_bootstrap_completes_from_any_partial_empty_skeleton(tmp_path, layout):
    data, bundle, catalog = _fixture(tmp_path)
    root = data / skill_store.STORE_DIRECTORY
    root.mkdir()
    for relative in layout:
        path = root / relative
        path.write_bytes(b"") if relative == "registry.lock" else path.mkdir(parents=True)
    assert _by_alias(_store(data, bundle).bootstrap(catalog))["alpha"]["state"] == "ready"


def test_invalid_legacy_state_preserves_crash_lock_byte_for_byte(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    root = data / skill_store.STORE_DIRECTORY
    root.mkdir(); (root / "registry.lock").write_bytes(b"\0")
    (data / "bundled-skills-state.json").write_text("{broken", encoding="utf-8")
    before = _snapshot(root)
    with pytest.raises(revisions.SkillRevisionError):
        _store(data, bundle).bootstrap(catalog)
    assert _snapshot(root) == before


def test_reader_active_and_pinned_reads_are_exact_and_zero_write(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    registry = _store(data, bundle).bootstrap(catalog)
    reader = skill_store.SkillStoreReader(data)
    before = _snapshot(data / skill_store.STORE_DIRECTORY)
    active = reader.read_active("ALPHA")
    assert active["registry"] == {key: registry[key] for key in (
        "schema", "dataRootId", "generation", "registryHash",
    )}
    assert active["routingAlias"] == "alpha"
    assert active["installation"]["revisionId"] == active["object"]["revisionId"]
    assert {item["path"] for item in active["object"]["files"]} == {
        "SKILL.md", "nested/text.txt",
    }
    assert all(not str(data) in value for value in _all_strings(active))
    assert _snapshot(data / skill_store.STORE_DIRECTORY) == before

    (data / "skills" / "alpha" / "SKILL.md").write_text("mutable changed", encoding="utf-8")
    (data / skill_store.STORE_DIRECTORY / "registry.json").write_text("{}\n", encoding="utf-8")
    assert reader.read_pinned(registry["dataRootId"], active["object"]["revisionId"]) == active["object"]
    with pytest.raises(skill_store.SkillStoreError) as caught:
        reader.read_registry()
    assert caught.value.code == "registry_invalid"


def _all_strings(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for key, child in value.items() for item in [key, *_all_strings(child)]]
    if isinstance(value, (list, tuple)):
        return [item for child in value for item in _all_strings(child)]
    return []


def test_reader_rejects_unavailable_and_unknown_bindings(tmp_path):
    data, bundle, catalog = _fixture(tmp_path / "blocked")
    (data / "skills" / "alpha" / "SKILL.md").write_text("modified", encoding="utf-8")
    _store(data, bundle).bootstrap(catalog)
    reader = skill_store.SkillStoreReader(data)
    with pytest.raises(skill_store.SkillStoreError) as caught:
        reader.read_active("alpha")
    assert caught.value.code == "store_binding_unavailable"
    with pytest.raises(skill_store.SkillStoreError) as caught:
        reader.read_active("unknown")
    assert caught.value.code == "store_binding_missing"

    shared = tmp_path / "shared"
    shared.mkdir(); _write_skill(shared / "skills", "alpha")
    shared_catalog = revisions.build_bundled_catalog(shared / "skills", {"alpha": "code.bundle/alpha"})
    _store(shared, shared / "skills").bootstrap(shared_catalog)
    with pytest.raises(skill_store.SkillStoreError) as caught:
        skill_store.SkillStoreReader(shared).read_active("alpha")
    assert caught.value.code == "store_binding_unavailable"

    tomb_data, tomb_bundle, tomb_catalog = _fixture(tmp_path / "tombstone")
    shutil.rmtree(tomb_data / "skills" / "alpha")
    (tomb_data / "bundled-skills-state.json").write_text(json.dumps({
        "schema": "code-bundled-skills/v1", "tombstones": ["alpha"],
    }), encoding="utf-8")
    _store(tomb_data, tomb_bundle).bootstrap(tomb_catalog)
    with pytest.raises(skill_store.SkillStoreError) as caught:
        skill_store.SkillStoreReader(tomb_data).read_active("alpha")
    assert caught.value.code == "store_binding_unavailable"


def test_reader_missing_store_is_zero_write(tmp_path):
    data = tmp_path / "profile"
    data.mkdir()
    before = _snapshot(data)
    with pytest.raises(skill_store.SkillStoreError) as caught:
        skill_store.SkillStoreReader(data).read_registry()
    assert caught.value.code == "store_root_missing"
    assert _snapshot(data) == before


@pytest.mark.parametrize("mutation,code", [
    ("missing", "object_missing"),
    ("corrupt", "object_corrupt"),
    ("extra", "store_object_unknown"),
])
def test_reader_rejects_missing_corrupt_and_extra_objects(tmp_path, mutation, code):
    data, bundle, catalog = _fixture(tmp_path)
    registry = _store(data, bundle).bootstrap(catalog)
    revision_id = registry["installations"][0]["revisionId"]
    obj = _store(data, bundle)._object_path(revision_id)
    if mutation == "missing":
        shutil.rmtree(obj)
    elif mutation == "corrupt":
        (obj / "content" / "SKILL.md").write_bytes(b"tampered")
    else:
        fake = "f" * 64
        shutil.copytree(obj, obj.parents[1] / fake[:2] / fake)
    with pytest.raises(skill_store.SkillStoreError) as caught:
        skill_store.SkillStoreReader(data).read_registry()
    assert caught.value.code == code


def test_pinned_reader_rejects_wrong_root_and_revision(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    registry = _store(data, bundle).bootstrap(catalog)
    reader = skill_store.SkillStoreReader(data)
    revision_id = registry["installations"][0]["revisionId"]
    with pytest.raises(skill_store.SkillStoreError) as caught:
        reader.read_pinned("dr1_" + "f" * 32, revision_id)
    assert caught.value.code == "store_data_root_mismatch"
    with pytest.raises(skill_store.SkillStoreError) as caught:
        reader.read_pinned(registry["dataRootId"], "bad")
    assert caught.value.code == "object_revision_invalid"
