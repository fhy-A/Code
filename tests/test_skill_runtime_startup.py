"""Immutable Skill startup ownership, bootstrap, and rollback contracts."""

from pathlib import Path
import shutil

import pytest

from code_runtime import data_dir_owner
from code_runtime import skill_revisions
from code_runtime import skill_runtime_startup
from code_runtime import skill_store
from code_runtime import skill_store_management
from tests.test_skill_store_management import apply as apply_management, package_request


def _write_skill(root, name="alpha", body="use alpha"):
    target = Path(root) / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} fixture\ntools: read_file\n---\n\n{body}\n",
        encoding="utf-8",
        newline="\n",
    )
    return target


def _fixture(tmp_path, *, shared=False):
    data = tmp_path / "profile"
    bundle = data / "skills" if shared else tmp_path / "bundle"
    installed = data / "skills"
    _write_skill(bundle)
    if not shared:
        shutil.copytree(bundle / "alpha", installed / "alpha")
    catalog = skill_revisions.build_bundled_catalog(
        bundle, {"alpha": "code.bundle/alpha"},
    )
    (bundle / skill_revisions.CATALOG_FILENAME).write_text(
        skill_revisions.render_bundled_catalog(catalog),
        encoding="utf-8",
        newline="\n",
    )
    return data, bundle, catalog


def _tree(root):
    root = Path(root)
    if not root.exists():
        return []
    return [
        (path.relative_to(root).as_posix(), "dir" if path.is_dir() else path.read_bytes())
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
    ]


class _CrashOnce:
    def __init__(self, point):
        self.point = point
        self.seen = False

    def __call__(self, point):
        if point == self.point and not self.seen:
            self.seen = True
            raise skill_store.SkillStoreInterruption(point)


def _initialize(runtime, owner, data, bundle, enabled, sync=None):
    return runtime.initialize(
        owner=owner,
        data_root=data,
        bundled_root=bundle,
        admission_enabled=enabled,
        legacy_sync_result=sync,
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_startup_never_implicitly_converts_a_committed_v1_store(tmp_path, enabled):
    data, bundle, catalog = _fixture(tmp_path)
    store = skill_store.SkillStore(data, bundle, write_enabled=True)
    original = store.bootstrap(catalog)
    before = _tree(data)
    with data_dir_owner.acquire_data_dir_owner(data) as owner:
        runtime = skill_runtime_startup.ImmutableSkillStartupRuntime(
            catalog_loader=lambda *_: pytest.fail("committed startup must not read catalog"),
        )
        assert _initialize(runtime, owner, data, bundle, enabled)["status"] == "ready"
        assert runtime.recovery_reader().read_registry() == original
        assert _tree(data) == before


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("point", [
    "after-journal-prepared-publish", "after-managed-registry-publish", "after-journal-committed-publish",
])
def test_startup_recovers_explicit_v2_conversion_without_sources(tmp_path, enabled, point):
    data, bundle, catalog = _fixture(tmp_path)
    store = skill_store.SkillStore(data, bundle, write_enabled=True)
    original = store.bootstrap(catalog)
    with data_dir_owner.acquire_data_dir_owner(data) as owner:
        manager = skill_store_management.SkillStoreManager(store, owner=owner)
        store.fault_injector = _CrashOnce(point)
        with pytest.raises(skill_store.SkillStoreInterruption):
            apply_management(manager, "convert", {"kind": "convert-v2"})
        runtime = skill_runtime_startup.ImmutableSkillStartupRuntime(
            catalog_loader=lambda *_: pytest.fail("v2 recovery must not read catalog"),
        )
        assert _initialize(runtime, owner, data, bundle, enabled, {"ok": False})["status"] == "ready"
        reader = runtime.recovery_reader()
        managed = reader.read_registry()
        assert managed["schema"] == "code-skill-install-registry/v2"
        assert managed["dataRootId"] == original["dataRootId"]
        assert managed["generation"] == original["generation"] + 1
        assert (runtime.admission_reader() is reader) is enabled


@pytest.mark.parametrize("enabled", [False, True])
def test_startup_late_v2_update_is_captured_only(tmp_path, enabled):
    data, bundle, catalog = _fixture(tmp_path)
    store = skill_store.SkillStore(data, bundle, write_enabled=True)
    original = store.bootstrap(catalog)
    with data_dir_owner.acquire_data_dir_owner(data) as owner:
        manager = skill_store_management.SkillStoreManager(store, owner=owner)
        apply_management(manager, "convert", {"kind": "convert-v2"})
        item = original["installations"][0]
        request, package = package_request(tmp_path / "new", "update-bundled", "alpha", "next",
                                           iid=item["installationId"])
        request["catalog"] = skill_revisions.build_bundled_catalog(package.parent, {"alpha": item["skillId"]})
        store.fault_injector = _CrashOnce("after-journal-captured-publish")
        with pytest.raises(skill_store.SkillStoreInterruption):
            apply_management(manager, "update", request, package=package)
        (package / "SKILL.md").write_text("source now differs", encoding="utf-8")
        runtime = skill_runtime_startup.ImmutableSkillStartupRuntime(
            catalog_loader=lambda *_: pytest.fail("late update must not read catalog"),
        )
        assert _initialize(runtime, owner, data, bundle, enabled)["status"] == "ready"
        reader = runtime.recovery_reader()
        assert reader.read_active("alpha")["installation"]["revisionId"] == request["revisionId"]
        assert reader.read_pinned(original["dataRootId"], item["revisionId"])


@pytest.mark.parametrize("enabled", [False, True])
def test_startup_early_v2_update_requires_explicit_capture(tmp_path, enabled):
    data, bundle, catalog = _fixture(tmp_path)
    store = skill_store.SkillStore(data, bundle, write_enabled=True)
    original = store.bootstrap(catalog)
    with data_dir_owner.acquire_data_dir_owner(data) as owner:
        manager = skill_store_management.SkillStoreManager(store, owner=owner)
        apply_management(manager, "convert", {"kind": "convert-v2"})
        item = original["installations"][0]
        request, package = package_request(tmp_path / "new", "fork-bundled", "local-alpha", "fork",
                                           iid=item["installationId"])
        store.fault_injector = _CrashOnce("after-journal-prepared-publish")
        with pytest.raises(skill_store.SkillStoreInterruption):
            apply_management(manager, "fork", request, package=package)
        before = _tree(data)
        runtime = skill_runtime_startup.ImmutableSkillStartupRuntime(
            catalog_loader=lambda *_: pytest.fail("v2 recovery must not discover source"),
        )
        if enabled:
            with pytest.raises(skill_runtime_startup.ImmutableSkillStartupError) as caught:
                _initialize(runtime, owner, data, bundle, enabled)
            assert caught.value.code == "management_capture_required"
        else:
            assert _initialize(runtime, owner, data, bundle, enabled)["errorCode"] == "management_capture_required"
        assert runtime.recovery_reader() is None
        assert _tree(data) == before


def test_absent_flag_off_is_zero_write_and_has_no_reader(tmp_path):
    data, bundle, _catalog = _fixture(tmp_path)
    before = _tree(data)
    owner = data_dir_owner.acquire_data_dir_owner(data)
    try:
        runtime = skill_runtime_startup.ImmutableSkillStartupRuntime()
        state = _initialize(runtime, owner, data, bundle, False)
        assert state == {
            "status": "disabled", "admissionEnabled": False,
            "readerReady": False, "errorCode": "",
        }
        assert runtime.recovery_reader() is None
        assert runtime.admission_reader() is None
        assert _tree(data) == before
    finally:
        owner.release()


def test_absent_flag_on_bootstraps_once_and_shared_source_stays_blocked(tmp_path):
    data, bundle, _catalog = _fixture(tmp_path)
    owner = data_dir_owner.acquire_data_dir_owner(data)
    try:
        runtime = skill_runtime_startup.ImmutableSkillStartupRuntime()
        state = _initialize(runtime, owner, data, bundle, True, {"ok": True})
        assert state["status"] == "ready"
        assert state["readerReady"] is True
        assert runtime.admission_reader() is runtime.recovery_reader()
        registry = runtime.recovery_reader().read_registry()
        assert registry["bindings"][0]["state"] == "ready"
        runtime._store_factory = lambda *_args, **_kwargs: pytest.fail(
            "successful duplicate initialization performed store IO"
        )
        assert _initialize(runtime, owner, data, bundle, True, {"ok": False}) == state
    finally:
        owner.release()

    shared_data, shared_bundle, _catalog = _fixture(tmp_path / "shared", shared=True)
    shared_owner = data_dir_owner.acquire_data_dir_owner(shared_data)
    try:
        shared = skill_runtime_startup.ImmutableSkillStartupRuntime()
        _initialize(shared, shared_owner, shared_data, shared_bundle, True)
        binding = shared.recovery_reader().read_registry()["bindings"][0]
        assert binding["state"] == "blocked"
        assert binding["reasonCode"] == "shared-development-unconfirmed"
        assert binding["activeCandidate"] is None
    finally:
        shared_owner.release()


def test_committed_flag_off_uses_reader_without_catalog_source_or_sync(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    skill_store.SkillStore(data, bundle, write_enabled=True).bootstrap(catalog)
    expected = skill_store.SkillStoreReader(data).read_registry()
    shutil.rmtree(data / "skills")
    shutil.rmtree(bundle)
    owner = data_dir_owner.acquire_data_dir_owner(data)
    try:
        runtime = skill_runtime_startup.ImmutableSkillStartupRuntime()
        state = _initialize(runtime, owner, data, bundle, False, {"ok": False})
        assert state["status"] == "ready"
        assert state["admissionEnabled"] is False
        assert runtime.admission_reader() is None
        assert runtime.recovery_reader().read_registry() == expected
    finally:
        owner.release()


def test_failed_legacy_sync_blocks_only_first_enabled_bootstrap(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    owner = data_dir_owner.acquire_data_dir_owner(data)
    try:
        runtime = skill_runtime_startup.ImmutableSkillStartupRuntime()
        with pytest.raises(skill_runtime_startup.ImmutableSkillStartupError) as raised:
            _initialize(runtime, owner, data, bundle, True, {"ok": False})
        assert raised.value.code == "skill_runtime_legacy_sync_failed"
        assert not (data / skill_store.STORE_DIRECTORY).exists()
    finally:
        owner.release()

    skill_store.SkillStore(data, bundle, write_enabled=True).bootstrap(catalog)
    owner = data_dir_owner.acquire_data_dir_owner(data)
    try:
        committed = skill_runtime_startup.ImmutableSkillStartupRuntime()
        assert _initialize(committed, owner, data, bundle, True, {"ok": False})["status"] == "ready"
    finally:
        owner.release()


def test_probe_prefers_valid_nonterminal_journal_over_published_registry(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    crashing = skill_store.SkillStore(
        data, bundle, write_enabled=True,
        fault_injector=_CrashOnce("after-registry-publish"),
    )
    with pytest.raises(skill_store.SkillStoreInterruption):
        crashing.bootstrap(catalog)
    state = skill_store.SkillStore(data, bundle).inspect_startup_state()
    assert state["state"] == "recoverable"
    assert state["phase"] == "objects-published"


def test_probe_rejects_multiple_journals_root_mismatch_and_unknown_objects(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    crashing = skill_store.SkillStore(
        data, bundle, write_enabled=True,
        fault_injector=_CrashOnce("after-journal-prepared-publish"),
    )
    with pytest.raises(skill_store.SkillStoreInterruption):
        crashing.bootstrap(catalog)
    store = skill_store.SkillStore(data, bundle)
    journal = store._journals()[0]
    store._journals = lambda: [journal, {**journal, "phase": "committed"}]
    with pytest.raises(skill_store.SkillStoreError) as multiple:
        store.inspect_startup_state()
    assert multiple.value.code == "store_transaction_conflict"
    store._journals = lambda: [
        {**journal, "phase": "committed"},
        {**journal, "phase": "committed"},
    ]
    with pytest.raises(skill_store.SkillStoreError) as committed_multiple:
        store.inspect_startup_state()
    assert committed_multiple.value.code == "store_transaction_conflict"

    root_path = data / skill_store.STORE_DIRECTORY / "root.json"
    root_path.write_bytes(skill_store._canonical({
        "schema": skill_store.ROOT_SCHEMA,
        "dataRootId": "dr1_" + "f" * 32,
    }) + b"\n")
    with pytest.raises(skill_store.SkillStoreError) as mismatch:
        skill_store.SkillStore(data, bundle).inspect_startup_state()
    assert mismatch.value.code == "root_mismatch"
    root_path.unlink()

    unknown = (
        data / skill_store.STORE_DIRECTORY / "objects" / "sha256" / "ff"
        / ("f" * 64)
    )
    unknown.mkdir(parents=True)
    with pytest.raises(skill_store.SkillStoreError) as objects:
        skill_store.SkillStore(data, bundle).inspect_startup_state()
    assert objects.value.code == "store_object_unknown"


def test_probe_rejects_unknown_staged_revision_before_recovery(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    crashing = skill_store.SkillStore(
        data, bundle, write_enabled=True,
        fault_injector=_CrashOnce("after-journal-prepared-publish"),
    )
    with pytest.raises(skill_store.SkillStoreInterruption):
        crashing.bootstrap(catalog)
    journal = skill_store.SkillStore(data, bundle)._journals()[0]
    unknown = (
        data / skill_store.STORE_DIRECTORY / "staging" / journal["operationId"]
        / "objects" / "sha256" / "ff" / ("f" * 64)
    )
    unknown.mkdir(parents=True)
    with pytest.raises(skill_store.SkillStoreError) as staged:
        skill_store.SkillStore(data, bundle).inspect_startup_state()
    assert staged.value.code == "staging_unknown"


def test_probe_requires_one_committed_journal_matching_registry(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    skill_store.SkillStore(data, bundle, write_enabled=True).bootstrap(catalog)
    store = skill_store.SkillStore(data, bundle)
    journal = store._journals()[0]
    store._journals = lambda: []
    with pytest.raises(skill_store.SkillStoreError) as missing:
        store.inspect_startup_state()
    assert missing.value.code == "bootstrap_store_incomplete"

    store._journals = lambda: [{
        **journal,
        "targetRegistry": {**journal["targetRegistry"], "generation": 1},
    }]
    with pytest.raises(skill_store.SkillStoreError) as mismatch:
        store.inspect_startup_state()
    assert mismatch.value.code == "registry_cas_conflict"


def test_late_recovery_is_journal_first_when_catalog_is_unavailable(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    custom = _write_skill(data / "skills", "custom", "captured")
    crashing = skill_store.SkillStore(
        data, bundle, write_enabled=True,
        fault_injector=_CrashOnce("after-journal-staged-verified-publish"),
    )
    with pytest.raises(skill_store.SkillStoreInterruption):
        crashing.bootstrap(catalog)
    (custom / "SKILL.md").write_text("changed", encoding="utf-8")
    (bundle / skill_revisions.CATALOG_FILENAME).unlink()
    owner = data_dir_owner.acquire_data_dir_owner(data)
    try:
        unavailable = skill_runtime_startup.ImmutableSkillStartupRuntime()
        state = _initialize(unavailable, owner, data, bundle, False)
        assert state["status"] == "unavailable"
        assert state["errorCode"] == "bootstrap_already_committed_conflict"
        assert unavailable.recovery_reader() is None
    finally:
        owner.release()
    journal = next((data / skill_store.STORE_DIRECTORY / "transactions").glob("*.json"))
    assert '"phase":"committed"' in journal.read_text(encoding="utf-8")

    owner = data_dir_owner.acquire_data_dir_owner(data)
    try:
        restarted = skill_runtime_startup.ImmutableSkillStartupRuntime()
        assert _initialize(restarted, owner, data, bundle, False)["status"] == "ready"
        assert restarted.recovery_reader() is not None
    finally:
        owner.release()


def test_early_recovery_conflict_is_preserved_with_admission_off_or_on(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    custom = _write_skill(data / "skills", "custom", "prepared")
    crashing = skill_store.SkillStore(
        data, bundle, write_enabled=True,
        fault_injector=_CrashOnce("after-journal-prepared-publish"),
    )
    with pytest.raises(skill_store.SkillStoreInterruption):
        crashing.bootstrap(catalog)
    journal = next((data / skill_store.STORE_DIRECTORY / "transactions").glob("*.json"))
    before = journal.read_bytes()
    (custom / "SKILL.md").write_text("changed too early", encoding="utf-8")

    owner = data_dir_owner.acquire_data_dir_owner(data)
    try:
        disabled = skill_runtime_startup.ImmutableSkillStartupRuntime()
        state = _initialize(disabled, owner, data, bundle, False)
        assert state["status"] == "unavailable"
        assert state["errorCode"] == "bootstrap_recovery_source_conflict"
        assert journal.read_bytes() == before
    finally:
        owner.release()

    owner = data_dir_owner.acquire_data_dir_owner(data)
    try:
        enabled = skill_runtime_startup.ImmutableSkillStartupRuntime()
        with pytest.raises(skill_runtime_startup.ImmutableSkillStartupError) as raised:
            _initialize(enabled, owner, data, bundle, True)
        assert raised.value.code == "bootstrap_recovery_source_conflict"
        assert journal.read_bytes() == before
    finally:
        owner.release()


def test_invalid_store_is_nonfatal_only_when_new_admission_is_off(tmp_path):
    data, bundle, _catalog = _fixture(tmp_path)
    store_root = data / skill_store.STORE_DIRECTORY
    store_root.mkdir()
    (store_root / "unknown").write_text("keep", encoding="utf-8")
    before = _tree(store_root)
    owner = data_dir_owner.acquire_data_dir_owner(data)
    try:
        runtime = skill_runtime_startup.ImmutableSkillStartupRuntime()
        state = _initialize(runtime, owner, data, bundle, False)
        assert state["status"] == "unavailable"
        assert state["errorCode"] == "store_layout_unknown"
        assert _tree(store_root) == before
    finally:
        owner.release()

    owner = data_dir_owner.acquire_data_dir_owner(data)
    try:
        enabled = skill_runtime_startup.ImmutableSkillStartupRuntime()
        with pytest.raises(skill_runtime_startup.ImmutableSkillStartupError) as raised:
            _initialize(enabled, owner, data, bundle, True)
        assert raised.value.code == "store_layout_unknown"
        enabled._store_factory = lambda *_args, **_kwargs: pytest.fail(
            "failed duplicate initialization performed store IO"
        )
        with pytest.raises(skill_runtime_startup.ImmutableSkillStartupError) as repeated:
            _initialize(enabled, owner, data, bundle, True)
        assert repeated.value.code == "store_layout_unknown"
        assert _tree(store_root) == before
    finally:
        owner.release()


def test_owner_identity_and_hot_reinitialization_are_rejected(tmp_path):
    data, bundle, _catalog = _fixture(tmp_path)
    owner = data_dir_owner.acquire_data_dir_owner(data)
    other_data, other_bundle, _catalog = _fixture(tmp_path / "other")
    try:
        runtime = skill_runtime_startup.ImmutableSkillStartupRuntime()
        with pytest.raises(skill_runtime_startup.ImmutableSkillStartupError) as mismatch:
            _initialize(runtime, owner, other_data, other_bundle, False)
        assert mismatch.value.code == "skill_runtime_owner_mismatch"
    finally:
        owner.release()

    owner = data_dir_owner.acquire_data_dir_owner(data)
    try:
        runtime = skill_runtime_startup.ImmutableSkillStartupRuntime()
        _initialize(runtime, owner, data, bundle, False)
        with pytest.raises(skill_runtime_startup.ImmutableSkillStartupError) as conflict:
            _initialize(runtime, owner, data, bundle, True)
        assert conflict.value.code == "skill_runtime_startup_reinitialize_conflict"
    finally:
        owner.release()

    released = data_dir_owner.acquire_data_dir_owner(data)
    released.release()
    with pytest.raises(skill_runtime_startup.ImmutableSkillStartupError) as inactive:
        _initialize(skill_runtime_startup.ImmutableSkillStartupRuntime(), released, data, bundle, False)
    assert inactive.value.code == "skill_runtime_owner_required"


@pytest.mark.parametrize("value,expected", [
    (None, True), ("", True), ("  ", True),
    ("1", True), ("true", True), (" YES ", True), ("on", True),
    ("0", False), ("false", False), (" OFF ", False), ("no", False),
    ("unexpected", False),
])
def test_server_new_skill_defaults_preserve_explicit_opt_out(value, expected):
    import server

    for key, resolve in (
        ("CODE_SKILL_IMMUTABLE_ADMISSION_V1", server._resolve_skill_immutable_admission_enabled),
        ("CODE_SKILL_MODEL_LOADING_V1", server._resolve_skill_model_loading_enabled),
    ):
        assert resolve({} if value is None else {key: value}) is expected
    # The two new defaults do not opt in to either independent legacy flag.
    env = {"CODE_SKILL_IMMUTABLE_ADMISSION_V1": value,
           "CODE_SKILL_MODEL_LOADING_V1": value}
    assert server._resolve_skill_completion_enforcement_enabled(env) is False
    assert server._resolve_skill_activation_enabled(env) is False


def test_startup_io_failure_is_stable_and_not_retried(tmp_path):
    data, bundle, _catalog = _fixture(tmp_path)
    calls = 0

    def fail_store(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise OSError("private path must not escape")

    owner = data_dir_owner.acquire_data_dir_owner(data)
    try:
        runtime = skill_runtime_startup.ImmutableSkillStartupRuntime(
            store_factory=fail_store,
        )
        for _attempt in range(2):
            with pytest.raises(skill_runtime_startup.ImmutableSkillStartupError) as raised:
                _initialize(runtime, owner, data, bundle, True)
            assert raised.value.code == "skill_runtime_startup_io_failed"
        assert calls == 1
    finally:
        owner.release()
