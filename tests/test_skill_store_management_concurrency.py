"""Bounded in-process and real cross-process registry publication."""
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from pathlib import Path
import threading
import time

import pytest

from code_runtime import data_dir_owner
from code_runtime import skill_store as legacy
from code_runtime import skill_store_management as management
from tests.test_skill_store import _CrashOnce
from tests.test_skill_store_management import apply, convert, installation, managed, package_request


def test_same_key_has_one_transaction_across_threads(managed):
    manager, _, tmp_path = managed
    convert(manager)
    base = manager.store.read_registry()
    request, path = package_request(tmp_path / "edit", "edit-local", "custom", "next",
                                    iid=installation(manager, "custom")["installationId"])
    package = management.capture_package(path)
    barrier = threading.Barrier(4)

    def write(_):
        barrier.wait(timeout=5)
        return apply(manager, "same", request, package=package, base=base)

    with ThreadPoolExecutor(max_workers=4) as workers:
        receipts = list(workers.map(write, range(4)))
    assert all(receipt == receipts[0] for receipt in receipts)
    assert manager.store.read_registry()["generation"] == base["generation"] + 1
    assert len(manager.store._journals()) == 3


def test_distinct_keys_with_same_base_conflict_not_double_apply(managed):
    manager, _, tmp_path = managed
    convert(manager)
    base = manager.store.read_registry()
    request, path = package_request(tmp_path / "edit", "edit-local", "custom", "next",
                                    iid=installation(manager, "custom")["installationId"])
    package = management.capture_package(path)
    barrier = threading.Barrier(3)

    def write(index):
        barrier.wait(timeout=5)
        try:
            return apply(manager, f"operation-{index}", request, package=package, base=base)
        except legacy.SkillStoreError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=3) as workers:
        results = list(workers.map(write, range(3)))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert results.count("registry_cas_conflict") == 2
    assert manager.store.read_registry()["generation"] == base["generation"] + 1


def test_reader_wait_on_thread_writer_is_bounded(managed):
    manager, _, _ = managed
    convert(manager)
    reader = legacy.SkillStoreReader(manager.store.data_root, lock_timeout=0.05)
    with ThreadPoolExecutor(max_workers=1) as worker:
        with manager.store._mutation_lock():
            started = time.monotonic()
            future = worker.submit(reader.read_registry)
            with pytest.raises(legacy.SkillStoreError) as caught:
                future.result(timeout=2)
            assert caught.value.code == "store_busy"
            assert time.monotonic() - started < 1.5
    assert reader.read_registry()["schema"].endswith("/v2")


def test_one_active_transaction_and_snapshot_conflict(managed):
    manager, _, tmp_path = managed
    convert(manager)
    reader = legacy.SkillStoreReader(manager.store.data_root)
    snapshot = reader.begin_admission()
    old = snapshot.capture_active("custom")
    base = manager.store.read_registry()
    request, package = package_request(tmp_path / "edit", "edit-local", "custom", "next",
                                       iid=installation(manager, "custom")["installationId"])
    manager.store.fault_injector = _CrashOnce("after-object-publish")
    with pytest.raises(legacy.SkillStoreInterruption):
        apply(manager, "first", request, package=package, base=base)
    manager.store.fault_injector = None
    # Published but uncommitted new objects are eligible only through this journal.
    assert reader.read_registry() == base
    with pytest.raises(legacy.SkillStoreError) as caught:
        apply(manager, "second", request, package=package, base=base)
    assert caught.value.code == "store_transaction_conflict"
    manager.recover()
    assert snapshot.capture_active("custom")["object"] == old["object"]
    with pytest.raises(legacy.SkillStoreError) as caught:
        snapshot.finish()
    assert caught.value.code == "registry_changed"


def _child_edit(data, bundle, request, package, base, ready, proceed):
    def hold(point):
        if point == "after-object-publish":
            ready.set()
            if not proceed.wait(timeout=12):
                raise RuntimeError("test parent did not release publication gate")

    with data_dir_owner.acquire_data_dir_owner(Path(data)) as owner:
        store = legacy.SkillStore(Path(data), Path(bundle), write_enabled=True, fault_injector=hold)
        manager = management.SkillStoreManager(store, owner=owner)
        apply(manager, "process-edit", request, package=Path(package), base=base)


def test_process_writer_and_reader_observe_complete_snapshots(managed):
    manager, _, tmp_path = managed
    convert(manager)
    base = manager.store.read_registry()
    custom = installation(manager, "custom")
    request, package = package_request(tmp_path / "edit", "edit-local", "custom", "process-owned next",
                                       iid=custom["installationId"])
    manager.owner.release()
    context = multiprocessing.get_context("spawn")
    ready, proceed = context.Event(), context.Event()
    process = context.Process(target=_child_edit, args=(
        str(manager.store.data_root), str(manager.store.bundled_root), request, str(package), base, ready, proceed,
    ))
    reader = legacy.SkillStoreReader(manager.store.data_root, lock_timeout=0.05)
    assert reader.read_registry() == base
    process.start()
    try:
        assert ready.wait(timeout=10), "child did not reach the publication gate"
        with pytest.raises(legacy.SkillStoreError) as caught:
            reader.read_registry()
        assert caught.value.code == "store_busy"
    finally:
        proceed.set()
        process.join(timeout=15)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
    assert not process.is_alive()
    assert process.exitcode == 0
    after = reader.read_registry()
    assert after["generation"] == base["generation"] + 1
    assert reader.read_active("custom")["installation"]["revisionId"] == request["revisionId"]
    assert reader.read_pinned(base["dataRootId"], custom["revisionId"])
