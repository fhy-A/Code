import builtins
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "session_file_size.py"
sys.path.insert(0, str(SCRIPT.parent))
import session_file_size as session_size


TASK = "01a08005-31d6-7f22-af20-f68fa1fe0464"


def make_session(home, size=0, store="sessions", task=TASK):
    path = home / store / "2026" / "09" / "08" / f"rollout-2026-09-08T15-56-59-{task}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Synthetic file lengths exercise actual stat sizes without any session content.
    with path.open("wb") as handle:
        handle.truncate(size)
    return path


@pytest.mark.parametrize("size,level", [
    (0, "normal"),
    (100 * session_size.MIB - 1, "normal"),
    (100 * session_size.MIB, "observe"),
    (100 * session_size.MIB + 1, "observe"),
    (300 * session_size.MIB - 1, "observe"),
    (300 * session_size.MIB, "recommend_rotation"),
    (300 * session_size.MIB + 1, "recommend_rotation"),
    (500 * session_size.MIB - 1, "recommend_rotation"),
    (500 * session_size.MIB, "strongly_recommend_rotation"),
    (500 * session_size.MIB + 1, "strongly_recommend_rotation"),
])
def test_real_stat_boundaries(tmp_path, size, level):
    path = make_session(tmp_path, size)
    try:
        result = session_size.inspect_session(TASK, tmp_path)
        assert result["status"] == "ok"
        assert result["level"] == level
        assert result["sizeBytes"] == size
        assert result["path"] == str(path)
        assert result["modifiedAt"] and result["matchCount"] == 1
    finally:
        path.unlink()


@pytest.mark.parametrize("store", ["sessions", "archived_sessions"])
def test_exact_id_and_store(tmp_path, store):
    path = make_session(tmp_path, 13, store=store)
    # Similar UUID, appended suffix and other extensions are not candidates.
    make_session(tmp_path, 999, store=store, task=TASK[:-1] + "5")
    path.with_name(path.stem + "-extra.jsonl").write_bytes(b"unrelated")
    path.with_suffix(".jsonl.bak").write_bytes(b"unrelated")
    result = session_size.inspect_session(TASK.upper(), tmp_path)
    assert result["status"] == "ok" and result["sizeBytes"] == 13
    assert result["matchCount"] == 1


@pytest.mark.parametrize("kind", ["empty_home", "missing_home", "other_task", "prefix"])
def test_no_match_is_unknown(tmp_path, kind):
    home = tmp_path / "missing" if kind == "missing_home" else tmp_path
    task = TASK
    if kind == "other_task":
        make_session(home, task=TASK[:-1] + "5")
    if kind == "prefix":
        make_session(home)
        task = TASK[:8]
    result = session_size.inspect_session(task, home)
    assert result["status"] == result["level"] == "unknown"
    assert result["sizeBytes"] is None and result["path"] is None


@pytest.mark.parametrize("second_store", ["sessions", "archived_sessions"])
def test_duplicate_never_picks_newest_or_smallest(tmp_path, second_store):
    make_session(tmp_path, 1)
    other = tmp_path / second_store / f"rollout-other-{TASK}.jsonl"
    other.parent.mkdir(exist_ok=True)
    other.write_bytes(b"duplicate")
    result = session_size.inspect_session(TASK, tmp_path)
    assert result["status"] == "unknown"
    assert result["reason"] == "multiple_matches" and result["matchCount"] == 2
    assert result["sizeBytes"] is None


def test_partial_directory_failure_is_unknown(tmp_path):
    make_session(tmp_path, 1)
    archived = tmp_path / "archived_sessions"
    archived.mkdir()
    original = os.scandir

    def denied(path):
        if Path(path) == archived:
            raise PermissionError("synthetic denial")
        return original(path)

    with patch.object(session_size.os, "scandir", side_effect=denied):
        result = session_size.inspect_session(TASK, tmp_path)
    assert result["status"] == "unknown" and result["sizeBytes"] is None
    assert result["reason"] == "metadata_unavailable"


@pytest.mark.parametrize("error", [PermissionError, FileNotFoundError])
def test_candidate_stat_failure_is_unknown(tmp_path, error):
    path = make_session(tmp_path, 1)
    original = Path.lstat

    def unavailable(candidate):
        if candidate == path:
            raise error("synthetic failure")
        return original(candidate)

    with patch.object(Path, "lstat", unavailable):
        result = session_size.inspect_session(TASK, tmp_path)
    assert result["status"] == "unknown" and result["sizeBytes"] is None


def test_reparse_root_is_unknown_without_following_it(tmp_path):
    make_session(tmp_path, 1)
    metadata = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
    with patch.object(Path, "lstat", return_value=metadata), \
         patch.object(os, "scandir", side_effect=AssertionError("must not follow junction")):
        result = session_size.inspect_session(TASK, tmp_path)
    assert result["reason"] == "unsafe_search_root"


def test_non_directory_store_is_unknown(tmp_path):
    make_session(tmp_path, 1)
    (tmp_path / "archived_sessions").write_bytes(b"not a directory")
    result = session_size.inspect_session(TASK, tmp_path)
    assert result["status"] == "unknown" and result["reason"] == "unsafe_search_root"


def test_no_content_reads_writes_or_persistent_state(tmp_path):
    path = make_session(tmp_path)
    path.write_bytes(b"SYNTHETIC SECRET: this content must never be opened by the checker")
    before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in tmp_path.rglob("*")}
    content = path.read_bytes()
    with patch.object(builtins, "open", side_effect=AssertionError("content open")), \
         patch.object(Path, "open", side_effect=AssertionError("path content open")), \
         patch.object(os, "open", side_effect=AssertionError("low-level file open")):
        first = session_size.inspect_session(TASK, tmp_path)
        second = session_size.inspect_session(TASK, tmp_path)
    assert first["status"] == second["status"] == "ok"
    assert "SYNTHETIC SECRET" not in json.dumps(first)
    after = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in tmp_path.rglob("*")}
    assert before == after and path.read_bytes() == content


@pytest.mark.parametrize("present,exit_code", [(True, 0), (False, 2)])
def test_cli_json_exit_codes_and_environment_default(tmp_path, present, exit_code):
    if present:
        make_session(tmp_path, 23)
    env = dict(os.environ, CODEX_HOME=str(tmp_path))
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), TASK, "--json"],
        env=env, text=True, encoding="utf-8", capture_output=True, timeout=10,
    )
    payload = json.loads(result.stdout)
    assert result.returncode == exit_code, result.stderr
    assert payload["status"] == ("ok" if present else "unknown")
    assert payload["sizeBytes"] == (23 if present else None)
