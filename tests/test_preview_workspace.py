"""Preview identity, lifecycle and bound read contracts (isolated DATA_DIR only)."""
import concurrent.futures
import hashlib
import io
import json
import os
from pathlib import Path
from unittest import mock

import pytest

if not os.environ.get("CODE_DATA_DIR"):
    pytest.skip("Preview lifecycle cases require disposable CODE_DATA_DIR before server import", allow_module_level=True)

import server
from code_runtime import preview_identity as identity


@pytest.fixture
def preview(tmp_path, monkeypatch):
    data, root = tmp_path / "data", tmp_path / "root"
    root.mkdir()
    for key, value in {"DATA_DIR": data, "SESSIONS_DIR": data / "sessions",
                       "ATTACHMENTS_DIR": data / "attachments", "CONFIG_PATH": data / "config.json"}.items():
        monkeypatch.setattr(server, key, value)
    monkeypatch.setattr(server, "_effective_agent_project_root", lambda: str(root))
    sid = "abc123abc123abcd"
    server.write_json(server.session_path(sid), {"id": sid, "revision": 7, "createdAt": "2026-09-16T00:00:00",
                                               "title": "keep", "custom": {"untouched": True}})
    return data, root, sid


def context(sid):
    return server._preview_context({"sessionId": sid}, initialize=True)


def file_response(ctx, path, **extra):
    binding = {**ctx, **extra}
    binding["_validatedRoot"] = server._validate_preview_context(binding)["root"]
    result = []
    handler = object.__new__(server.CodeHandler)
    handler.send_json = lambda payload, *args: result.append(payload)
    handler.get_file(str(path), preview_binding=binding)
    return result[0]


def test_concurrent_initialization_preserves_metadata_and_cas(preview):
    _, _, sid = preview
    before = server.read_json(server.session_path(sid), {})
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: context(sid), range(16)))
    assert len({r["sessionInstanceId"] for r in results}) == 1
    assert len({r["dataSourceId"] for r in results}) == 1
    after = server.read_json(server.session_path(sid), {})
    assert {k: v for k, v in after.items() if k != "previewIdentity"} == before
    assert sum(r["identityInitialized"] for r in results) == 1


def test_identity_lost_or_same_id_recreated_does_not_reuse(preview):
    _, _, sid = preview
    old = context(sid)
    path = server.session_path(sid)
    value = server.read_json(path, {})
    value.pop("previewIdentity")
    server.write_json(path, value)
    with pytest.raises(identity.PreviewConflict):
        server._validate_preview_context(old)
    renewed = context(sid)
    assert renewed["sessionInstanceId"] != old["sessionInstanceId"]
    path.unlink()
    with pytest.raises(identity.PreviewConflict):
        server._validate_preview_context(renewed)
    server.write_json(path, value)
    assert context(sid)["sessionInstanceId"] != renewed["sessionInstanceId"]


@pytest.mark.parametrize("payload", [b"{", b'{"schema":"future"}', b"[]", b"x" * 5000])
def test_corrupt_source_is_never_reset(preview, payload):
    data, _, sid = preview
    context(sid)
    source = data / "preview-workspace/source.json"
    source.write_bytes(payload)
    with pytest.raises(identity.PreviewConflict):
        context(sid)
    assert source.read_bytes() == payload


def test_source_move_and_server_restart(preview, monkeypatch):
    data, _, sid = preview
    first = context(sid)
    monkeypatch.setattr(server, "_server_instance_id", "next-process")
    assert context(sid)["dataSourceId"] == first["dataSourceId"]
    with pytest.raises(identity.PreviewConflict):
        server._validate_preview_context(first)
    copied = data.parent / "copied"
    source = copied / "preview-workspace/source.json"
    source.parent.mkdir(parents=True)
    source.write_bytes((data / "preview-workspace/source.json").read_bytes())
    with pytest.raises(identity.PreviewConflict):
        identity.source_identity(copied, server.write_json, initialize=True)


def test_bound_reads_hashes_aliases_and_root_aba(preview, monkeypatch):
    _, root, sid = preview
    (root / "a.txt").write_bytes(b"A\r\n")
    ctx = context(sid)
    result = file_response(ctx, "a.txt")
    assert result["canonicalAbsolutePath"] == str((root / "a.txt").resolve())
    assert result["contentRevision"] == hashlib.sha256(b"A\r\n").hexdigest()
    assert file_response(ctx, root / "a.txt")["fileKey"] == result["fileKey"]
    other = root.parent / "other"
    other.mkdir()
    (other / "a.txt").write_text("WRONG")
    # The validated root is immutable throughout resolution even if the live
    # root changes twice; the final validation cannot detect ABA on its own.
    binding = {**ctx, "_validatedRoot": ctx["root"]}
    live = {"root": str(other)}
    monkeypatch.setattr(server, "_effective_agent_project_root", lambda: live["root"])
    original_resolver = identity.resolve_read_path
    def resolve_during_aba(value, frozen_root, home):
        result = original_resolver(value, frozen_root, home)
        live["root"] = str(root)
        return result
    monkeypatch.setattr(identity, "resolve_read_path", resolve_during_aba)
    handler = object.__new__(server.CodeHandler)
    output = []
    handler.send_json = lambda payload: output.append(payload)
    handler.get_file("a.txt", preview_binding=binding)
    assert output[0]["content"] == "A\r\n"
    monkeypatch.setattr(server, "_effective_agent_project_root", lambda: str(other))
    with pytest.raises(identity.PreviewConflict):
        file_response(ctx, "a.txt")


def test_file_replacement_and_symlink_redirect(preview):
    _, root, sid = preview
    target = root / "a.txt"
    target.write_text("first")
    ctx = context(sid)
    original = file_response(ctx, target)
    replacement = root / "next"
    replacement.write_text("second")
    os.replace(replacement, target)
    result = file_response(ctx, target, fileKey=original["fileKey"])
    assert result["content"] == "second"
    assert result["contentRevision"] != original["contentRevision"]
    with pytest.raises(identity.PreviewConflict):
        file_response(ctx, target, fileKey="0" * 64)


def test_read_fallback_does_not_create_output(preview):
    _, root, _ = preview
    outside = root.parent / "outside" / "missing.txt"
    result_root, target = identity.resolve_read_path(str(outside), root, root / "home")
    assert result_root == root
    assert target == root / "output/missing.txt"
    assert not (root / "output").exists()


def test_raw_uses_same_scope_and_file_binding(preview):
    _, root, sid = preview
    target = root / "image.png"
    target.write_bytes(b"\x89PNG\r\nfixture")
    ctx = context(sid)
    facts = file_response(ctx, target)
    binding = {**ctx, "fileKey": facts["fileKey"], "_validatedRoot": ctx["root"]}
    handler = object.__new__(server.CodeHandler)
    handler.send_response = mock.Mock()
    handler.send_header = mock.Mock()
    handler.end_headers = mock.Mock()
    handler.wfile = io.BytesIO()
    handler.get_file(str(target), raw=True, preview_binding=binding)
    assert handler.wfile.getvalue() == target.read_bytes()
    handler.send_response.assert_called_once_with(200)
    handler.send_response.reset_mock()
    with pytest.raises(identity.PreviewConflict):
        handler.get_file(str(target), raw=True, preview_binding={**binding, "sessionInstanceId": "f" * 32})
    handler.send_response.assert_not_called()


def test_preview_never_recovers_lifecycle_transactions(preview):
    _, root, sid = preview
    (root / "a").write_text("A")
    ctx = context(sid)
    with mock.patch.object(server, "_recover_session_archive_transaction", side_effect=AssertionError("unexpected mutation")):
        assert file_response(ctx, root / "a")["content"] == "A"
        journal = server._session_archive_journal_path(sid)
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text("pending transaction")
        with pytest.raises(identity.PreviewConflict):
            file_response(ctx, root / "a")
        with pytest.raises(identity.PreviewConflict):
            context(sid)


def test_missing_or_unknown_session_identity_is_not_guessed(preview):
    _, _, sid = preview
    path = server.session_path(sid)
    value = server.read_json(path, {})
    value["previewIdentity"] = {"version": 2, "id": "f" * 32}
    server.write_json(path, value)
    with pytest.raises(identity.PreviewConflict):
        context(sid)
    assert server.read_json(path, {}) == value


def test_source_write_failure_does_not_initialize_session(preview):
    _, _, sid = preview
    with mock.patch.object(server, "write_json", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            context(sid)
    assert "previewIdentity" not in server.read_json(server.session_path(sid), {})


def test_creation_branch_save_archive_restore_and_delete_preserve_ownership():
    from test_session_persistence import TestSessionArchiveLifecycle
    fixture = TestSessionArchiveLifecycle()
    fixture.setUp()
    try:
        created = fixture.create_session()
        sid = created["id"]
        initial = identity.identity_id(created["previewIdentity"])
        handler = fixture.make_handler({"title": "renamed", "previewIdentity": identity.new_identity()})
        handler.save_session(sid)
        assert identity.identity_id(server.read_json(server.session_path(sid), {})["previewIdentity"]) == initial
        branch = fixture.make_handler({"previewIdentity": created["previewIdentity"]})
        branch.branch_session(sid)
        child = branch.send_json.call_args.args[0]
        assert identity.identity_id(child["previewIdentity"]) != initial
        ctx = context(sid)
        fixture.archive(sid)
        with pytest.raises((identity.PreviewConflict, server.SessionLifecycleConflictError)):
            server._validate_preview_context(ctx)
        fixture.unarchive(sid)
        assert context(sid)["sessionInstanceId"] == initial
        deletion = fixture.make_handler()
        deletion.delete_session(sid)
        with pytest.raises(identity.PreviewConflict):
            server._validate_preview_context(ctx)
    finally:
        fixture.doCleanups()


def test_concurrent_initialization_and_save_keeps_identity(preview):
    _, _, sid = preview
    def save(_):
        handler = object.__new__(server.CodeHandler)
        handler.read_body_json = lambda: {"title": "updated", "previewIdentity": identity.new_identity()}
        handler.send_json = mock.Mock()
        handler.save_session(sid)
        return context(sid)["sessionInstanceId"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        ids = list(pool.map(save, range(12)))
    assert len(set(ids)) == 1


def test_symlink_alias_and_bound_redirect(preview):
    _, root, sid = preview
    (root / "a").write_text("A")
    (root / "b").write_text("B")
    alias = root / "link"
    try:
        alias.symlink_to(root / "a")
    except OSError as exc:
        pytest.skip(f"symlink capability unavailable: {exc.winerror if hasattr(exc, 'winerror') else exc.errno}")
    ctx = context(sid)
    first = file_response(ctx, alias)
    assert first["fileKey"] == file_response(ctx, root / "a")["fileKey"]
    alias.unlink()
    alias.symlink_to(root / "b")
    with pytest.raises(identity.PreviewConflict):
        file_response(ctx, alias, fileKey=first["fileKey"])


def test_import_refresh_keeps_identity_and_divergent_snapshot_gets_new_identity(preview):
    from test_server import TestCodexImport
    _, root, _ = preview
    source = root / "foreign.jsonl"
    make_source = TestCodexImport()._make_codex_jsonl
    messages = [("user", "initial"), ("assistant", "reply")]
    source.write_text(make_source(messages), encoding="utf-8")
    first = server.import_codex_session(str(source))
    identity_id = identity.identity_id(first["previewIdentity"])
    assert server.import_codex_session(str(source))["previewIdentity"]["id"] == identity_id
    messages.append(("user", "source update"))
    source.write_text(make_source(messages), encoding="utf-8")
    updated = server.import_codex_session(str(source))
    assert updated["id"] == first["id"]
    assert updated["previewIdentity"]["id"] == identity_id
    local_messages = server.messages_path(first["id"])
    server.write_jsonl(local_messages, server.read_jsonl(local_messages) + [{"role": "user", "content": "local continuation"}])
    messages.append(("assistant", "later source reply"))
    source.write_text(make_source(messages), encoding="utf-8")
    snapshot = server.import_codex_session(str(source))
    assert snapshot["id"] != first["id"]
    assert snapshot["previewIdentity"]["id"] != identity_id
