"""Read-only bounded picker and existing identity-fenced file selection."""
import os
import subprocess
from pathlib import Path
from unittest import mock
from urllib.parse import urlencode

import pytest

from code_runtime import preview_picker as picker
from code_runtime.preview_identity import PreviewConflict, digest, path_identity


def test_empty_query_is_immediate_metadata_only(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested/hidden.txt").write_text("secret")
    (tmp_path / "one.txt").write_text("body must not be read")
    with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("body")), mock.patch.object(Path, "read_text", side_effect=AssertionError("body")):
        result = picker.list_entries(tmp_path)
    assert result["scannedDirectories"] == 1
    assert [x["name"] for x in result["items"]] == ["nested", "one.txt"]
    assert result["items"][1]["fileKey"] == digest(path_identity(tmp_path / "one.txt"))
    assert not result["limited"]


def test_search_matches_basename_not_content_or_parent(tmp_path):
    (tmp_path / "needle-parent").mkdir()
    (tmp_path / "needle-parent/unrelated.txt").write_text("needle")
    (tmp_path / "needle-parent/NEEDLE.txt").write_text("other")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored/needle.txt").touch()
    result = picker.list_entries(tmp_path, query="needle", skip_names={"ignored"})
    assert [x["path"] for x in result["items"]] == ["needle-parent/NEEDLE.txt"]
    assert result["scannedDirectories"] == 2
    assert picker.list_entries(tmp_path, "needle-parent")["scannedDirectories"] == 1


@pytest.mark.parametrize("value", ["../escape", "a/../b", "/absolute", "C:/absolute", "C:relative", "\\\\server\\share", "a\0b", "x" * 4097])
def test_rejects_escape_and_invalid_paths(tmp_path, value):
    with pytest.raises(PreviewConflict):
        picker.list_entries(tmp_path, value)
    assert not list(tmp_path.iterdir())


def test_links_are_not_followed(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir(); outside.mkdir(); (outside / "needle.txt").write_text("outside")
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink unavailable")
    result = picker.list_entries(root, query="needle")
    assert result["items"] == [] and "links" in result["reasons"]
    with pytest.raises(PreviewConflict):
        picker.list_entries(root, "link")


@pytest.mark.skipif(os.name != "nt", reason="Windows junction boundary")
def test_windows_junction_is_not_followed(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir(); outside.mkdir(); (outside / "needle.txt").write_text("outside")
    link = root / "junction"
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                    f"New-Item -ItemType Junction -Path {quote(link)} -Target {quote(outside)} | Out-Null"], check=True)
    try:
        result = picker.list_entries(root, query="needle")
        assert result["items"] == [] and "links" in result["reasons"]
        with pytest.raises(PreviewConflict):
            picker.list_entries(root, "junction")
    finally:
        os.rmdir(link)  # Only the fixture junction entry; never recurse through it.
    assert (outside / "needle.txt").read_text() == "outside"


@pytest.mark.parametrize("constant,limit,reason", [("MAX_RESULTS", 2, "results"), ("MAX_ENTRIES", 2, "entries"), ("MAX_BYTES", 1, "bytes")])
def test_output_and_scan_bounds(tmp_path, monkeypatch, constant, limit, reason):
    for i in range(4):
        (tmp_path / f"file{i}.txt").touch()
    monkeypatch.setattr(picker, constant, limit)
    result = picker.list_entries(tmp_path)
    assert result["limited"] and reason in result["reasons"]
    assert len(result["items"]) <= 2 and result["scannedEntries"] <= 4


def test_directory_depth_and_time_bounds(tmp_path, monkeypatch):
    (tmp_path / "a/b/c").mkdir(parents=True)
    (tmp_path / "a/b/c/needle").touch()
    monkeypatch.setattr(picker, "MAX_DEPTH", 1)
    result = picker.list_entries(tmp_path, query="needle")
    assert result["scannedDirectories"] == 2 and "depth" in result["reasons"]
    monkeypatch.setattr(picker, "MAX_DIRECTORIES", 1)
    assert "directories" in picker.list_entries(tmp_path, query="needle")["reasons"]
    ticks = iter([0, 1])
    result = picker.list_entries(tmp_path, clock=lambda: next(ticks))
    assert result["scannedDirectories"] == 0 and result["reasons"] == ["time"]


@pytest.mark.skipif(not os.environ.get("CODE_DATA_DIR"), reason="disposable CODE_DATA_DIR required")
def test_bound_route_checks_before_and_after_scan_and_never_recovers(tmp_path, monkeypatch):
    import server
    root, data = tmp_path / "root", tmp_path / "data"
    root.mkdir(); (root / "a.txt").write_text("body")
    for key, value in {"DATA_DIR": data, "SESSIONS_DIR": data / "sessions", "ATTACHMENTS_DIR": data / "attachments", "CONFIG_PATH": data / "config.json"}.items():
        monkeypatch.setattr(server, key, value)
    monkeypatch.setattr(server, "_effective_agent_project_root", lambda: str(root))
    sid = "abc123abc123abcd"
    server.write_json(server.session_path(sid), {"id": sid, "revision": 1})
    ctx = server._preview_context({"sessionId": sid}, initialize=True)
    def get(binding):
        handler = object.__new__(server.CodeHandler)
        handler.path = "/api/preview/files?" + urlencode(binding)
        handler._handle_skill_management = lambda *args: False
        handler._guard_legacy_skill_http = lambda *args: False
        output = []
        handler.send_json = lambda payload, status=200: output.append((status, payload))
        handler.do_GET()
        return output[0]
    with mock.patch.object(server, "_recover_session_archive_transaction", side_effect=AssertionError("recovery")):
        status, result = get(ctx)
        assert status == 200 and result["root"] == ctx["root"]
        assert result["items"][0]["name"] == "a.txt"
        other = root / "b.txt"
        other.write_text("must not read")
        handler = object.__new__(server.CodeHandler)
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("body before identity")):
            with pytest.raises(PreviewConflict):
                handler.get_file(str(other), preview_binding={**ctx, "_validatedRoot": ctx["root"], "fileKey": result["items"][0]["fileKey"]})
        for field in ("dataSourceId", "sessionInstanceId", "serverInstanceId", "contextRevision"):
            with mock.patch.object(picker, "list_entries", side_effect=AssertionError("must reject before scan")):
                assert get({**ctx, field: "wrong"})[0] == 409
        original = picker.list_entries
        def change_root(*args, **kwargs):
            payload = original(*args, **kwargs)
            monkeypatch.setattr(server, "_effective_agent_project_root", lambda: str(root / "other"))
            return payload
        with mock.patch.object(picker, "list_entries", side_effect=change_root):
            assert get(ctx)[0] == 409


@pytest.mark.skipif(not os.environ.get("CODE_DATA_DIR"), reason="disposable CODE_DATA_DIR required")
def test_access_log_omits_picker_query(capsys):
    import server
    handler = object.__new__(server.CodeHandler)
    handler.path = "/api/preview/files?q=PRIVATE_SEARCH&path=PRIVATE_DIRECTORY"
    handler.command, handler.request_version = "GET", "HTTP/1.1"
    handler.address_string = lambda: "fixture"
    handler.log_request(200)
    output = capsys.readouterr().out
    assert "/api/preview/files" in output and "PRIVATE" not in output
