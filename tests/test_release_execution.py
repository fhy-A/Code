"""Isolated release execution and sealed routing; never use real remotes."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from unittest import mock
from contextlib import ExitStack

import pytest

import release
from devtools import verification


def invoke(tmp_path, source, **kwargs):
    return verification.run_logged_command(
        [sys.executable, "-u", "-c", source], cwd=tmp_path, timeout=kwargs.pop("timeout", 10),
        log_dir=tmp_path / "logs", stream=kwargs.pop("stream", io.StringIO()), **kwargs,
    )


def assert_exited(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x100000, False, pid)
        if handle:
            try:
                assert api.WaitForSingleObject(handle, 2000) == 0
            finally:
                api.CloseHandle(handle)
    else:
        # A reaped-or-zombie child no longer executes or writes.
        status = Path(f"/proc/{pid}/stat")
        if status.exists():
            assert status.read_text().split(") ", 1)[1].startswith("Z")


def test_full_stdout_stderr_unicode_and_nonzero_are_preserved(tmp_path):
    result = invoke(tmp_path, "import sys; print('中文' * 5000); print('error-tail', file=sys.stderr); sys.exit(7)")
    assert result.returncode == 7
    assert result.stdout == "中文" * 5000 + "\n"
    assert result.stderr == "error-tail\n"
    assert (tmp_path / "logs/stdout.log").read_text(encoding="utf-8") == result.stdout
    assert (tmp_path / "logs/stderr.log").read_text(encoding="utf-8") == result.stderr
    assert json.loads((tmp_path / "logs/result.json").read_text())["exitCode"] == 7


CHILD_SOURCE = """
import subprocess, sys, time
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
print('CHILD=' + str(child.pid), flush=True)
print('partial-stderr', file=sys.stderr, flush=True)
print('READY', flush=True)
time.sleep(30)
"""


@pytest.mark.parametrize("cancel", [False, True])
def test_timeout_or_live_cancellation_retains_output_and_closes_only_owned_tree(tmp_path, cancel):
    event = threading.Event()
    class Observer(io.StringIO):
        def write(self, text):
            result = super().write(text)
            if cancel and "READY" in text:
                event.set()  # Requires live output while the command is asleep.
            return result
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        with pytest.raises(KeyboardInterrupt if cancel else subprocess.TimeoutExpired) as caught:
            invoke(tmp_path, CHILD_SOURCE, timeout=2, cancel_event=event, stream=Observer())
        stdout = (tmp_path / "logs/stdout.log").read_text(encoding="utf-8")
        stderr = (tmp_path / "logs/stderr.log").read_text(encoding="utf-8")
        assert "READY" in stdout and "partial-stderr" in stderr
        child_pid = int(next(line for line in stdout.splitlines() if line.startswith("CHILD=")).split("=")[1])
        assert_exited(child_pid)
        assert unrelated.poll() is None
        summary = json.loads((tmp_path / "logs/result.json").read_text())
        assert summary["status"] == ("cancelled" if cancel else "timeout")
        assert summary["exitCode"] == (130 if cancel else 124)
        if not cancel:
            assert caught.value.stdout == stdout and caught.value.stderr == stderr
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)


def test_spawn_failure_stays_nonzero_and_preserves_diagnostic(tmp_path):
    result = verification.run_logged_command(
        [str(tmp_path / "missing-command")], cwd=tmp_path, timeout=10,
        log_dir=tmp_path / "logs", stream=io.StringIO(),
    )
    assert result.returncode != 0
    assert "FileNotFoundError" in result.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows Job attachment boundary")
def test_containment_failure_never_releases_requested_command(tmp_path):
    from code_runtime.skill_dependency_operation import _WindowsJob
    with mock.patch.object(_WindowsJob, "attach", side_effect=OSError("synthetic attach failure")):
        with pytest.raises(OSError, match="synthetic attach failure"):
            invoke(tmp_path, "from pathlib import Path; Path('unexpected').write_text('bad')")
    assert not (tmp_path / "unexpected").exists()
    summary = json.loads((tmp_path / "logs/result.json").read_text())
    assert summary["status"] == "failed" and "attach failure" in summary["error"]


def test_success_also_closes_leftover_owned_children(tmp_path):
    result = invoke(tmp_path, CHILD_SOURCE.replace("time.sleep(30)\n", "", 1))
    assert result.returncode == 0
    child_pid = int(next(line for line in result.stdout.splitlines() if line.startswith("CHILD=")).split("=")[1])
    assert_exited(child_pid)


def test_console_encoding_fallback_does_not_change_utf8_logs(tmp_path):
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="ascii")
    result = invoke(tmp_path, "print('中文')", stream=stream)
    assert result.stdout == "中文\n"
    stream.flush()
    assert b"\\u4e2d" in raw.getvalue()
    assert (tmp_path / "logs/stdout.log").read_text(encoding="utf-8") == "中文\n"


def test_quiet_identity_calls_do_not_enter_streaming_logs():
    result = subprocess.CompletedProcess(["identity"], 0, "private-identity", "")
    with mock.patch.object(release.subprocess, "run", return_value=result), \
            mock.patch.object(release, "run_logged_command") as logged:
        assert release.run_quiet(["identity"]) is result
    logged.assert_not_called()


def test_fast_failure_reports_unrun_checks_without_launching_expensive_work(capsys):
    with mock.patch.object(release, "run", return_value=(2, "syntax failed", "")) as command, \
            mock.patch.object(release, "run_tests") as full, \
            mock.patch.object(release, "run_harness_replay_gate") as replay:
        with pytest.raises(SystemExit):
            release.run_release_quality_checks(dry_run=False, skip_tests=False)
    assert command.call_count == 1
    full.assert_not_called()
    replay.assert_not_called()
    output = capsys.readouterr().out
    assert "CHECK_FAILED id=git_diff_check" in output
    assert "NOT_RUN syntax_app" in output and "pytest_full" in output


def test_manifest_is_only_reordered_with_unchanged_commands_and_timeouts():
    historical = ("frontend_build", "frontend_freshness", "frontend_bundle_syntax", "pytest_full",
                  "harness_replay", "git_diff_check", *verification.SYNTAX_CHECK_IDS)
    current = verification.get_release_check_ids(dry_run=False, skip_tests=False)
    assert set(current) == set(historical) and len(current) == len(set(current))
    before = verification.get_release_definition_fingerprint()
    with mock.patch.object(verification, "get_release_check_ids", return_value=historical):
        assert verification.get_release_definition_fingerprint() != before
    assert verification.CHECKS["pytest_full"].timeout == 1500


@pytest.mark.parametrize("body", ["", "# 更新\n", release.RELEASE_NOTES_PLACEHOLDER])
def test_bad_notes_fail_before_environment_remote_or_metadata(tmp_path, body):
    (tmp_path / "v1.2.3.md").write_text(body, encoding="utf-8")
    with mock.patch.object(release, "RELEASES_DIR", tmp_path), \
            mock.patch.object(release.shutil, "which") as which:
        with pytest.raises(SystemExit):
            release.require_prepare_inputs("1.2.3")
    which.assert_not_called()


def test_body_only_notes_remain_supported_and_missing_build_tool_fails_early(tmp_path):
    (tmp_path / "v1.2.3.md").write_text("## 改动\n\n- 已完成发布流程优化。", encoding="utf-8")
    with mock.patch.object(release, "RELEASES_DIR", tmp_path), \
            mock.patch.object(release.shutil, "which", return_value="existing-tool"), \
            mock.patch.object(release.importlib.util, "find_spec", return_value=object()):
        release.require_prepare_inputs("1.2.3")
    with mock.patch.object(release, "RELEASES_DIR", tmp_path), \
            mock.patch.object(release.shutil, "which", return_value=None):
        with pytest.raises(SystemExit):
            release.require_prepare_inputs("1.2.3")


@pytest.mark.parametrize("state", [None, "prepared", "publishing", "published"])
def test_full_routes_once_through_existing_sealed_actions(tmp_path, state):
    credential = tmp_path / "credential.json"
    if state:
        credential.write_text("synthetic existence")
    with mock.patch.object(release, "_credential_path", return_value=credential), \
            mock.patch.object(release, "_load_prepared_credential", return_value=(credential, {"state": state})), \
            mock.patch.object(release, "prepare_release") as prepare, \
            mock.patch.object(release, "publish_prepared") as publish, \
            mock.patch.object(release, "resume_release") as resume:
        release.full_release("1.2.3", auto_yes=True)
    assert prepare.call_count == (1 if state is None else 0)
    assert publish.call_count == (1 if state in {None, "prepared"} else 0)
    assert resume.call_count == (1 if state in {"publishing", "published"} else 0)


def test_stale_or_unknown_credential_never_falls_back_to_fresh_prepare(tmp_path):
    credential = tmp_path / "credential.json"
    credential.write_text("stale")
    for bad in (SystemExit("stale"), {"state": "unknown"}):
        with mock.patch.object(release, "_credential_path", return_value=credential), \
                mock.patch.object(release, "_load_prepared_credential", **(
                    {"side_effect": bad} if isinstance(bad, BaseException) else {"return_value": (credential, bad)})), \
                mock.patch.object(release, "prepare_release") as prepare, \
                mock.patch.object(release, "publish_prepared") as publish:
            with pytest.raises(SystemExit):
                release.full_release("1.2.3", auto_yes=True)
        prepare.assert_not_called()
        publish.assert_not_called()


def test_full_interactive_cancellation_has_no_prepare_or_publish(tmp_path):
    with mock.patch.object(release, "_credential_path", return_value=tmp_path / "absent"), \
            mock.patch.object(release, "run", return_value=(0, "", "")), \
            mock.patch.object(release, "get_current_version", return_value="1.2.2"), \
            mock.patch.object(release, "ask", return_value=False), \
            mock.patch.object(release, "prepare_release") as prepare, \
            mock.patch.object(release, "publish_prepared") as publish:
        release.full_release("1.2.3")
    prepare.assert_not_called()
    publish.assert_not_called()


def test_full_yes_still_rejects_bad_notes_before_remote_or_expensive_steps(tmp_path):
    version = tmp_path / "VERSION"
    version.write_text("1.2.2\n")
    (tmp_path / "v1.2.3.md").write_text("# 更新\n", encoding="utf-8")
    with mock.patch.object(release, "VERSION_FILE", version), \
            mock.patch.object(release, "RELEASES_DIR", tmp_path), \
            mock.patch.object(release, "_credential_path", return_value=tmp_path / "absent.json"), \
            mock.patch.object(release, "_git_branch", return_value="master"), \
            mock.patch.object(release, "_ensure_cached_empty"), \
            mock.patch.object(release, "_git_head", return_value="synthetic-head"), \
            mock.patch.object(release, "remote_read_only_preflight") as remote, \
            mock.patch.object(release, "run_release_quality_checks") as quality, \
            mock.patch.object(release, "publish_prepared") as publish:
        with pytest.raises(SystemExit):
            release.full_release("1.2.3", auto_yes=True)
    remote.assert_not_called()
    quality.assert_not_called()
    publish.assert_not_called()
    assert version.read_text() == "1.2.2\n"


def test_default_cli_dispatches_full_with_confirmation_mode():
    for flags, auto_yes in (([], False), (["--yes"], True)):
        with mock.patch.object(release.sys, "argv", ["release.py", "1.2.3", "--no-proxy", *flags]), \
                mock.patch.object(release, "full_release") as full:
            release.main()
        full.assert_called_once_with("1.2.3", auto_yes=auto_yes)


@pytest.mark.skipif(os.name != "nt", reason="Windows batch command used by npm")
def test_windows_batch_command_keeps_output_and_exit_code(tmp_path):
    command = tmp_path / "build check.cmd"
    command.write_text("@echo off\necho batch-output\nexit /b 3\n", encoding="ascii")
    result = verification.run_logged_command([str(command)], cwd=tmp_path, timeout=10,
                                             log_dir=tmp_path / "logs", stream=io.StringIO())
    assert result.returncode == 3 and "batch-output" in result.stdout


@pytest.mark.parametrize("drift", [None, "head", "branch", "tag", "release", "asset"])
def test_published_state_is_read_only_even_when_remote_objects_are_missing(tmp_path, drift):
    credential = {"state": "published", "version": "1.2.3", "tag": "v1.2.3",
                  "publication": {"commit": "published-head"}, "releaseFiles": [],
                  "baseline": {"outsideTrackedSha256": "clean"},
                  "environment": {"repository": "synthetic/repo"}}
    readers = {"_validate_static_credential": None, "_git_branch": "master", "_ensure_cached_empty": None,
               "_git_head": "different" if drift == "head" else "published-head",
               "_verify_release_commit": None, "_tracked_state_digest": "clean",
               "_local_tag_commit": "published-head",
               "_read_remote_branch": "different" if drift == "branch" else "published-head",
               "_read_remote_tag": None if drift == "tag" else "published-head",
               "_read_remote_release": None if drift == "release" else {"tagName": "v1.2.3"},
               "_audit_release_metadata": None, "_audit_release_asset": None}
    with ExitStack() as stack:
        for name, value in readers.items():
            stack.enter_context(mock.patch.object(release, name, **(
                {"side_effect": SystemExit("asset drift")} if name == "_audit_release_asset" and drift == "asset"
                else {"return_value": value})))
        writes = [stack.enter_context(mock.patch.object(release, name)) for name in
                  ("run", "save_credential", "_ensure_release_commit", "_ensure_local_tag",
                   "_ensure_remote_branch", "_ensure_remote_tag", "_ensure_github_release", "_ensure_release_asset")]
        if drift:
            with pytest.raises(SystemExit):
                release._continue_publication(tmp_path / "credential.json", credential)
        else:
            assert release._continue_publication(tmp_path / "credential.json", credential) is credential
        for write in writes:
            write.assert_not_called()
