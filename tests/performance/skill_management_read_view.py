"""Manual synthetic performance comparisons; excluded by default filename discovery.

Run: python -B -m pytest tests/performance/skill_management_read_view.py -q -s
The optional CODE_SKILL_BENCH_FIXTURE must be an isolated synthetic preparation.
"""
import json
import os
from pathlib import Path
import time
from contextlib import ExitStack, contextmanager
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from code_runtime import data_dir_owner, skill_revisions, skill_store, skill_store_management
from code_runtime import skill_management_api as api
from tests.test_skill_store import _snapshot
from tests.test_skill_store_management import apply
from tests.test_skill_management_read_view import (
    selected_31_skill_template, _copy_31_skill_template,
)


def test_31_skill_toggle_segments_and_integrity_counts(tmp_path, request):
    """Comparable measurements, with correctness independent of elapsed time."""
    prepared = os.environ.get("CODE_SKILL_BENCH_FIXTURE")
    source = Path(prepared) if prepared else request.getfixturevalue("selected_31_skill_template")
    data, bundle = _copy_31_skill_template(source, tmp_path)
    store = skill_store.SkillStore(data, bundle, write_enabled=True)
    with data_dir_owner.acquire_data_dir_owner(data) as owner:
        if not prepared:
            manager = skill_store_management.SkillStoreManager(store, owner=owner)
            target = store.read_registry()["installations"][0]
            for index in range(5):
                apply(manager, f"toggle-{index}", {"kind": "set-enabled", "installationId": target["installationId"], "enabled": bool(index % 2)})
        registry = store.read_registry()
        target = registry["installations"][0]
        generation, desired = registry["generation"], not target["enabled"]
        report = {"fixture": {"skills": 31, "files": 217, "generation": generation,
                  "registryHash": registry["registryHash"], "clonedSyntheticState": bool(prepared)}, "segments": {}}
        counts, durations = {}, {}

        def measure(name, action):
            counts.clear(); durations.clear()
            start = time.perf_counter()
            result = action()
            report["segments"][name] = {"ms": round((time.perf_counter() - start) * 1000, 2),
                "checks": dict(counts), "inclusiveMs": {key: round(value * 1000, 2) for key, value in durations.items()}}
            return result

        def instrument(container, name):
            original = getattr(container, name)
            def counted(*args, **kwargs):
                key = name
                if name == "_load_registry":
                    key += ":objects" if kwargs.get("verify_objects", True) else ":metadata"
                elif name == "_stable_file":
                    key += ":content" if "/content/" in str(args[0]).replace("\\", "/") else ":metadata"
                counts[key] = counts.get(key, 0) + 1
                start = time.perf_counter()
                try:
                    return original(*args, **kwargs)
                finally:
                    durations[key] = durations.get(key, 0) + time.perf_counter() - start
            return mock.patch.object(container, name, counted)

        original_lock = skill_store.SkillStore._store_lock
        @contextmanager
        def timed_lock(store, *, write):
            key = "lockWait:write" if write else "lockWait:read"
            start = time.perf_counter()
            with original_lock(store, write=write):
                counts[key] = counts.get(key, 0) + 1
                durations[key] = durations.get(key, 0) + time.perf_counter() - start
                yield

        service = api.SkillManagementService(data, bundle, owner=owner, admission_enabled=True, server_instance_id="synthetic")
        with ExitStack() as stack:
            for name in ("_verify_object", "_load_registry", "_load_json", "_journals", "_inspect_layout", "inspect_startup_state"):
                stack.enter_context(instrument(skill_store.SkillStore, name))
            stack.enter_context(instrument(skill_revisions, "_stable_file"))
            stack.enter_context(mock.patch.object(skill_store.SkillStore, "_store_lock", timed_lock))
            for name in ("normalize_registry", "normalize_journal"):
                stack.enter_context(instrument(skill_store_management.metadata, name))
            stack.enter_context(instrument(skill_store_management, "inspect_managed_state"))
            snapshot = measure("list", service.snapshot)
            assert snapshot["mode"] == "managed-v2" and snapshot["registry"]["generation"] == generation
            assert len(snapshot["installations"]) == 31
            preview = measure("preview", lambda: service.preview({"protocol": api.PROTOCOL,
                "base": snapshot["registry"], "kind": "set-enabled", "installationId": target["installationId"], "enabled": desired}))
            result = measure("applyWithSnapshot", lambda: service.apply({"protocol": api.PROTOCOL,
                "base": preview["base"], "request": preview["request"], "operationKey": f"measured-toggle-from-{generation}", "confirmed": True}))
            refreshed = measure("redundantList", service.snapshot)
        assert result["snapshot"] == refreshed
        assert result["snapshot"]["registry"]["generation"] == generation + 1
        item = next(item for item in refreshed["installations"] if item["installationId"] == target["installationId"])
        assert item["enabled"] is desired
        (tmp_path / "toggle-performance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (tmp_path / "toggle-response.json").write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
        print("R103_TOGGLE_PERFORMANCE " + json.dumps(report))


def test_31_skill_first_reads_counts_and_serial_parallel_timing(tmp_path, selected_31_skill_template):
    data, bundle = _copy_31_skill_template(selected_31_skill_template, tmp_path)
    store = skill_store.SkillStore(data, bundle, write_enabled=True)
    with data_dir_owner.acquire_data_dir_owner(data) as owner:
        manager = skill_store_management.SkillStoreManager(store, owner=owner)
        registry = store.read_registry()
        target = registry["installations"][0]
        for enabled in (False, True):
            apply(manager, str(enabled), {"kind": "set-enabled", "installationId": target["installationId"], "enabled": enabled})
        before = _snapshot(data)
        report = {"fixture": "31 synthetic Skills, 217 files, generation 34", "timingsMs": {}}

        def new_service():
            return api.SkillManagementService(data, bundle, owner=owner, admission_enabled=True)

        def measure(name, action):
            start = time.perf_counter()
            result = action()
            report["timingsMs"][name] = round((time.perf_counter() - start) * 1000, 2)
            return result

        old = new_service()
        def old_snapshot():
            old._registry()
            old.store.inspect_startup_state()
        def old_detail():
            old._registry()  # Former HTTP root precheck.
            registry = old._registry()
            old._object(registry, target["installationId"], target["revisionId"])
            old._registry()
        with mock.patch.object(old.reader._store, "_verify_object", wraps=old.reader._store._verify_object) as verify:
            measure("oldSnapshotWithoutDescriptions", old_snapshot)
            report["oldSnapshotObjectChecks"] = verify.call_count
            assert verify.call_count == 31
            verify.reset_mock()
            measure("oldDetail", old_detail)
            report["oldDetailObjectChecks"] = verify.call_count
            assert verify.call_count == 95
        current = new_service()
        with mock.patch.object(current.reader._store, "_verify_object", wraps=current.reader._store._verify_object) as verify, \
                mock.patch.object(current.reader._store, "inspect_startup_state", wraps=current.reader._store.inspect_startup_state) as inspect:
            snapshot = measure("newSnapshotWithDescriptions", current.snapshot)
            assert snapshot["mode"] == "managed-v2" and snapshot["registry"]["generation"] == 34
            assert len(snapshot["installations"]) == 31
            assert all(item["description"] == "test" for item in snapshot["installations"])
            assert verify.call_count == 62 and inspect.call_count == 1
            report["snapshotObjectChecks"] = verify.call_count
        current = new_service()  # A fresh service; no warmed application cache.
        with mock.patch.object(current.reader._store, "_verify_object", wraps=current.reader._store._verify_object) as verify, \
                mock.patch.object(current.reader._store, "inspect_startup_state", wraps=current.reader._store.inspect_startup_state) as inspect:
            detail = measure("newDetail", lambda: current.detail(target["installationId"]))
            assert detail["description"] == "test"
            assert verify.call_count == 2 and inspect.call_count == 1
            report["detailObjectChecks"] = verify.call_count
        def parallel():
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(new_service().snapshot),
                           pool.submit(new_service().detail, target["installationId"])]
                return [future.result(timeout=30) for future in futures]
        results = measure("newSnapshotAndDetailParallel", parallel)
        assert results[0]["mode"] == "managed-v2" and results[1]["description"] == "test"
        assert _snapshot(data) == before
        print("R099_READ_PERFORMANCE " + json.dumps(report))
