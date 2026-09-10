"""File discovery coverage uses synthetic files and injected I/O failures only."""
import ast
import contextlib
import inspect
import json
import os
import subprocess
import threading
from pathlib import Path
from unittest import mock

import pytest
import server as s


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(s, "_effective_agent_project_root", lambda: tmp_path)
    return tmp_path


CASES = [("list_files", {}), ("glob_files", {"pattern": "**/*.txt"}), ("search_files", {"query": "NEEDLE"})]


@contextlib.contextmanager
def deny_directory(target):
    original_iterdir, original_scandir = Path.iterdir, os.scandir
    def items(path):
        if path == target:
            raise PermissionError(13, "fixture secret must not be exposed", str(target))
        return original_iterdir(path)
    def scan(path):
        if Path(path) == target:
            raise PermissionError(13, "fixture secret must not be exposed", str(target))
        return original_scandir(path)
    with mock.patch.object(Path, "iterdir", items), mock.patch.object(os, "scandir", scan):
        yield


def invoke(tool, payload):
    result = s.execute_registered_tool(tool, payload)
    coverage = result["coverage"]
    assert len(json.dumps(coverage, ensure_ascii=False).encode()) <= 4096
    assert len(coverage["samples"]) <= 10
    for sample in coverage["samples"]:
        assert len(sample["path"].encode()) <= 240
        assert not Path(sample["path"]).is_absolute()
    assert "fixture secret" not in json.dumps(result)
    return result


@pytest.mark.parametrize("tool,payload", CASES)
def test_empty_root_denial_and_missing_path_are_distinct(project, tool, payload):
    result = invoke(tool, payload)
    assert result["ok"] and result["count"] == 0 and result["coverage"]["status"] == "complete"
    with deny_directory(project):
        result = invoke(tool, payload)
    assert not result["ok"] and result["coverage"]["status"] == "failed"
    assert result["error"] == "Target is not accessible for this operation."
    with pytest.raises(ValueError, match="不存在"):
        invoke(tool, {**payload, "path": "missing"})


@pytest.mark.parametrize("tool,payload", CASES)
def test_child_denial_preserves_valid_results(project, tool, payload):
    locked = project / "locked"
    locked.mkdir()
    (locked / "hidden.txt").write_text("NEEDLE")
    (project / "visible.txt").write_text("NEEDLE")
    with deny_directory(locked):
        result = invoke(tool, {**payload, **({"maxDepth": 3} if tool == "list_files" else {})})
    assert result["ok"] and result["coverage"]["status"] == "partial"
    assert result["coverage"]["reasons"] == {"directory_unavailable": 1}
    entries = result.get("items", result.get("results"))
    assert any(item["path"] == "visible.txt" for item in entries)
    assert not any("hidden.txt" in item["path"] for item in entries)
    assert not s._agent_tool_failure_signature(result)


@pytest.mark.parametrize("explicit,name_hit", [(False, False), (True, False), (True, True)])
def test_unreadable_file_distinguishes_name_hit_and_explicit_target(project, explicit, name_hit):
    target = project / "private.txt"
    target.write_text("NEEDLE")
    with mock.patch.object(Path, "read_bytes", side_effect=PermissionError("fixture secret")):
        result = invoke("search_files", {"query": "private" if name_hit else "NEEDLE", **({"path": target.name} if explicit else {})})
    failed = explicit and not name_hit
    assert result["ok"] is not failed
    assert result["coverage"]["status"] == ("failed" if failed else "partial")
    assert result["count"] == int(name_hit)
    if name_hit:
        assert result["results"][0]["nameMatch"] and result["results"][0]["matches"] == []


@pytest.mark.parametrize("denied", [False, True])
def test_glob_root_fallback_keeps_scope_and_initial_failure(project, denied):
    sub = project / "sub"
    sub.mkdir()
    (project / "outside.txt").write_text("NEEDLE")
    with deny_directory(sub) if denied else contextlib.nullcontext():
        result = invoke("glob_files", {"path": "sub", "pattern": "*.txt"})
    assert result["ok"] and result["results"][0]["path"] == "outside.txt"
    assert result["coverage"]["status"] == ("partial" if denied else "complete")
    assert result["coverage"]["scope"] == {"requestedPath": "sub", "rootFallback": True, "fallbackPath": "."}


def test_both_glob_scopes_unavailable_fail(project):
    sub = project / "sub"
    sub.mkdir()
    with deny_directory(sub), deny_directory(project):
        result = invoke("glob_files", {"path": "sub", "pattern": "*.txt"})
    assert result["ok"] is False and result["coverage"]["status"] == "failed"
    assert result["coverage"]["scope"]["rootFallback"] is True


@pytest.mark.parametrize("tool,payload", [CASES[1], CASES[2], ("search_files", {"query": "NEEDLE", "glob": "*.txt"})])
def test_walk_failure_keeps_earlier_results_and_does_not_blame_glob(project, tool, payload):
    (project / "hit.txt").write_text("NEEDLE")
    def interrupted(*args, **kwargs):
        yield str(project), [], ["hit.txt"]
        raise PermissionError("fixture secret")
    with mock.patch.object(os, "walk", interrupted):
        result = invoke(tool, payload)
    assert result["ok"] and result["count"] == 1
    assert result["coverage"]["status"] == "partial"
    assert result["coverage"]["reasons"]["traversal_interrupted"] == 1


def test_size_binary_and_explicit_filters_are_not_permission_failures(project):
    (project / "large.txt").write_bytes(b"x" * (s.MAX_SEARCH_FILE_BYTES + 1))
    (project / "binary.bin").write_bytes(b"\0NEEDLE")
    (project / "source.py").write_text("NEEDLE")
    (project / "node_modules").mkdir()
    (project / "node_modules" / "ignored.txt").write_text("NEEDLE")
    large = invoke("search_files", {"path": "large.txt", "query": "NEEDLE"})
    assert large["ok"] and large["coverage"]["status"] == "partial"
    assert large["coverage"]["reasons"] == {"size_limit": 1}
    binary = invoke("search_files", {"path": "binary.bin", "query": "NEEDLE"})
    assert binary["coverage"]["status"] == "complete"
    assert binary["coverage"]["reasons"] == {"binary_excluded": 1}
    for extra in [{"type": "md"}, {"glob": "*.md"}]:
        filtered = invoke("search_files", {"query": "NEEDLE", **extra})
        assert filtered["count"] == 0 and filtered["coverage"]["status"] == "complete"
    assert invoke("glob_files", {"pattern": "**/ignored.txt"})["count"] == 0
    name = invoke("search_files", {"query": "large"})
    assert name["count"] == 1 and name["results"][0]["matches"] == []


def test_declared_exclusions_do_not_create_metadata_warnings(project):
    excluded = project / "node_modules"
    excluded.mkdir()
    wrong_type = project / "excluded.bin"
    wrong_type.touch()
    original = Path.stat
    def stat(path, *args, **kwargs):
        if path in {excluded, wrong_type} and inspect.currentframe().f_back.f_code.co_name == "is_kind":
            raise PermissionError("fixture secret")
        return original(path, *args, **kwargs)
    with mock.patch.object(Path, "stat", stat):
        # The regular .bin entry is included by list, so only probe the skipped
        # directory there; extension exclusion belongs to search.
        with mock.patch.object(Path, "iterdir", return_value=iter([excluded])):
            listing = invoke("list_files", {})
        search = invoke("search_files", {"query": "NEEDLE", "type": "txt"})
    assert listing["coverage"]["status"] == search["coverage"]["status"] == "complete"
    assert not listing["coverage"]["reasons"] and not search["coverage"]["reasons"]


@pytest.mark.parametrize("tool,payload", CASES)
def test_result_limits_remain_unchanged_and_report_possible_omission(project, tool, payload):
    for index in range(201):
        (project / f"hit-{index:03}.txt").write_text("NEEDLE")
    result = invoke(tool, payload)
    assert result["count"] == (100 if tool == "search_files" else 200)
    assert result["truncated"] and result["coverage"]["status"] == "partial"
    assert result["coverage"]["reasons"]["result_limit"] == 1


def test_exact_cap_and_per_file_cap_need_no_extra_scan(project):
    for index in range(100):
        (project / f"hit-{index}.txt").write_text("NEEDLE")
    result = invoke("search_files", {"query": "NEEDLE"})
    assert result["count"] == 100 and result["truncated"]
    assert result["coverage"]["reasons"] == {"result_limit": 1}
    (project / "lines.txt").write_text("NEEDLE\n" * 11)
    result = invoke("search_files", {"query": "NEEDLE", "path": "lines.txt"})
    assert len(result["results"][0]["matches"]) == 10 and not result["truncated"]
    assert result["coverage"]["reasons"] == {"per_file_limit": 1}


def test_candidate_limit_does_not_scan_later_directory_or_change_batch_limit(project):
    for index in range(5001):
        (project / f"file-{index}.txt").touch()
    def walk(*args, **kwargs):
        yield str(project), [], [f"file-{index}.txt" for index in range(5001)]
        raise AssertionError("must not ask for another directory after candidate cap")
    with mock.patch.object(os, "walk", walk):
        for extra in [{}, {"glob": "*.txt"}]:
            result = invoke("search_files", {"query": "NEEDLE", **extra})
            assert result["count"] == 0 and not result["truncated"]
            assert result["coverage"]["reasons"] == {"candidate_limit": 1}


@pytest.mark.parametrize("tool,payload", CASES[:2])
def test_all_unknown_sizes_are_marked_beyond_sample_cap(project, tool, payload):
    for index in range(25):
        (project / f"item-{index:02}.txt").write_text("not empty")
    original = Path.stat
    def stat(path, *args, **kwargs):
        if path.parent == project and inspect.currentframe().f_back.f_code.co_name == "size":
            raise PermissionError("fixture secret")
        return original(path, *args, **kwargs)
    with mock.patch.object(Path, "stat", stat):
        result = invoke(tool, payload)
    entries = result.get("items", result.get("results"))
    assert len(entries) == 25
    assert all(item["size"] == 0 and item["sizeAvailable"] is False for item in entries)
    assert len(result["coverage"]["samples"]) == 10 and result["coverage"]["samplesTruncated"]
    assert result["coverage"]["reasons"]["metadata_unavailable"] == 25


def test_summary_utf8_json_limits_and_no_raw_error_or_absolute_paths(project):
    collector = s._FileCoverage(project, project / ("🙂" * 200))
    for index in range(1000):
        collector.note("file_unreadable", project / (str(index) + "\u0001" * 240 + "🙂" * 200))
    result = collector.finish({"ok": True, "action": "search_files", "count": 1, "results": []})
    coverage = result["coverage"]
    assert len(json.dumps(coverage, ensure_ascii=False).encode()) <= 4096
    assert len(coverage["samples"]) <= 10 and coverage["samplesTruncated"]
    assert coverage["reasons"]["file_unreadable"] == 1000
    assert str(project) not in json.dumps(coverage, ensure_ascii=False)
    assert all(len(item["path"].encode()) <= 240 for item in coverage["samples"])
    assert len(coverage["scope"]["requestedPath"].encode()) <= 240


@pytest.mark.parametrize("action", ["list_files", "glob_files", "search_files", "read_file"])
def test_model_compaction_preserves_only_discovery_coverage_header(project, action):
    collector = s._FileCoverage(project, project)
    collector.note("metadata_unavailable", project / "unknown.txt")
    collector.root_fallback = True
    result = collector.finish({"ok": True, "action": action, "count": 1, "results": [{"text": "🙂\\\n" * 20000}]})
    model = s._agent_tool_message_content(result)
    assert len(model) <= s._AGENT_TOOL_MESSAGE_LIMIT
    compact = json.loads(model)
    assert compact["truncatedForModel"]
    if action != "read_file":
        assert compact["coverage"] == {"status": "partial", "reasons": {"metadata_unavailable": 1}, "rootFallback": True}
        assert len(json.dumps(compact["coverage"]).encode()) < 1024
    else:
        assert "coverage" not in compact


def test_old_new_mixed_results_keep_failure_count_and_public_json_compatibility(project):
    success = {"ok": True, "action": "search_files", "count": 0, "results": []}
    partial = {**success, "coverage": {"status": "partial"}}
    failure = {"ok": False, "action": "search_files", "error": "Target is not accessible for this operation."}
    run = {"tool_executions": {}}
    for index, result in enumerate([success, partial, failure, {**failure, "coverage": {"status": "failed", "samples": []}}, failure]):
        execution = {"name": "search_files", "fingerprint": "same-call"}
        s._set_agent_execution_result(execution, result)
        run["tool_executions"][str(index)] = execution
        assert s._agent_public_tool_executions(run)[-1]["result"] == result
        assert s._agent_identical_tool_failure_count(run, "same-call") == max(0, index - 1)
    assert json.loads(json.dumps(run)) == run
    assert "coverage" not in run["tool_executions"]["0"]["result"]


def test_normal_matching_sorting_filters_and_truncated_match_baseline(project):
    # Execute only the pure tool/receipt functions from the approved baseline,
    # using the same isolated root and dependencies; no old server is started.
    baseline = subprocess.check_output(["git", "show", "4654ad4:server.py"], text=True, encoding="utf-8")
    names = {"execute_list_files_tool", "execute_glob_files_tool", "execute_search_files_tool", "_resolve_search_candidates", "_matches_glob_path", "_agent_tool_message_content"}
    tree = ast.parse(baseline)
    old = dict(vars(s))
    exec(compile(ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[]), "baseline-file-tools", "exec"), old)
    (project / "src").mkdir()
    (project / "src" / "a.py").write_text("NEEDLE\nplain")
    (project / "B.txt").write_text("NEEDLE")
    for tool, payload in CASES + [("list_files", {"maxDepth": 3}), ("search_files", {"query": "NEE.*", "regex": True, "glob": "**/*.py"}), ("glob_files", {"pattern": "**/*.py", "path": "src"})]:
        result = invoke(tool, payload)
        result.pop("coverage")
        assert result == old["execute_" + tool + "_tool"](payload)
    for action in ["read_file", "web_fetch", "search_files"]:
        legacy = {"ok": True, "action": action, "results": [{"text": "🙂\\\n" * 20000}]}
        assert s._agent_tool_message_content(legacy) == old["_agent_tool_message_content"](legacy)
    other_tool = {"ok": True, "action": "read_file", "coverage": {"status": "partial"}, "content": "x" * 20000}
    assert s._agent_tool_message_content(other_tool) == old["_agent_tool_message_content"](other_tool)


def test_http_coverage_results_and_existing_parameter_errors(project):
    import requests
    host = s.ThreadingHTTPServer(("127.0.0.1", 0), s.CodeHandler)
    worker = threading.Thread(target=host.serve_forever, daemon=True)
    worker.start()
    try:
        for tool, payload in CASES:
            url = f"http://127.0.0.1:{host.server_port}/api/tools/{tool}"
            complete = requests.post(url, json=payload, timeout=10)
            with deny_directory(project):
                denied = requests.post(url, json=payload, timeout=10)
            # Transport stays unchanged; the registered tool carries failure.
            assert complete.status_code == denied.status_code == 200
            assert complete.json()["coverage"]["status"] == "complete"
            assert denied.json()["coverage"]["status"] == "failed" and not denied.json()["ok"]
        bad = requests.post(f"http://127.0.0.1:{host.server_port}/api/tools/search_files", json={"query": "[", "regex": True}, timeout=10)
        assert bad.status_code == 400 and "正则表达式无效" in bad.json()["error"]
    finally:
        host.shutdown()
        host.server_close()
        worker.join(timeout=2)
        assert not worker.is_alive()
