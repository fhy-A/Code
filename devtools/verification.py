"""Shared, read-only verification profiles for local development and releases."""

from __future__ import annotations

from dataclasses import dataclass
import codecs
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable, Iterable, TextIO


ROOT = Path(__file__).resolve().parent.parent
NPM = "npm.cmd" if os.name == "nt" else "npm"
DOCTOR_SCHEMA = "code-development-doctor/v1"
DOCTOR_NODE_SCHEMA = "code-development-doctor-node/v1"
DOCTOR_NODE_PROBE = ROOT / "scripts" / "development-doctor.cjs"
DOCTOR_COMMAND_TIMEOUT = 10
DOCTOR_NODE_TIMEOUT = 30
DOCTOR_PYTHON_MODULES = (
    ("pytest", "pytest"),
    ("requests", "requests"),
    ("yaml", "PyYAML"),
    ("jsonschema", "jsonschema"),
)
DOCTOR_NODE_CHECK_IDS = (
    "esbuild_transform",
    "playwright_package",
    "chromium_launch",
)
H4_PYTHON_PROBE = """\
import importlib.util
import json
import platform
import sys

names = ("pytest", "requests", "yaml", "jsonschema")
print(json.dumps({
    "executable": sys.executable,
    "version": platform.python_version(),
    "modules": {
        name: importlib.util.find_spec(name) is not None
        for name in names
    },
}, sort_keys=True, separators=(",", ":")))
"""


@dataclass(frozen=True)
class CheckSpec:
    """One deterministic verification command."""

    check_id: str
    label: str
    command: tuple[str, ...]
    timeout: int


@dataclass(frozen=True)
class DoctorCheckResult:
    """One environment capability result emitted by the doctor."""

    check_id: str
    status: str
    reason: str
    detail: dict[str, object]


CHECKS: dict[str, CheckSpec] = {
    "frontend_build": CheckSpec(
        "frontend_build",
        "构建前端 bundle",
        ("node", str(ROOT / "scripts" / "build-frontend.mjs")),
        120,
    ),
    "frontend_freshness": CheckSpec(
        "frontend_freshness",
        "核对前端 bundle freshness",
        ("node", str(ROOT / "scripts" / "build-frontend.mjs"), "--check"),
        120,
    ),
    "frontend_bundle_syntax": CheckSpec(
        "frontend_bundle_syntax",
        "检查前端 bundle 语法",
        ("node", "--check", str(ROOT / "dist" / "frontend" / "code.bundle.js")),
        120,
    ),
    "pytest_ui": CheckSpec(
        "pytest_ui",
        "运行前端模块与 P0 稳定性测试",
        (
            sys.executable,
            "-m",
            "pytest",
            "tests/test_frontend_modules.py",
            "tests/test_p0_stability.py",
            "-q",
        ),
        180,
    ),
    "pytest_full": CheckSpec(
        "pytest_full",
        "运行完整 pytest",
        (sys.executable, "-m", "pytest", "tests", "-q", "--durations=30"),
        1500,
    ),
    "harness_replay": CheckSpec(
        "harness_replay",
        "运行 Harness replay 发布门禁",
        (NPM, "run", "verify:harness-replay"),
        30,
    ),
    "h4": CheckSpec(
        "h4",
        "运行 H4 真实运行时验收",
        (NPM, "run", "test:h4:e2e"),
        600,
    ),
    "git_diff_check": CheckSpec(
        "git_diff_check",
        "检查 Git diff 空白错误",
        ("git", "diff", "--check"),
        300,
    ),
    "syntax_app": CheckSpec(
        "syntax_app",
        "检查 app.js 语法",
        ("node", "--check", str(ROOT / "app.js")),
        300,
    ),
    "syntax_agent_runtime": CheckSpec(
        "syntax_agent_runtime",
        "检查 agent-runtime.js 语法",
        ("node", "--check", str(ROOT / "agent-runtime.js")),
        300,
    ),
    "syntax_server": CheckSpec(
        "syntax_server",
        "检查 server.py 语法",
        (sys.executable, "-m", "py_compile", str(ROOT / "server.py")),
        300,
    ),
    "syntax_launcher": CheckSpec(
        "syntax_launcher",
        "检查 launcher.py 语法",
        (sys.executable, "-m", "py_compile", str(ROOT / "launcher.py")),
        300,
    ),
    "syntax_build_exe": CheckSpec(
        "syntax_build_exe",
        "检查 build_exe.py 语法",
        (sys.executable, "-m", "py_compile", str(ROOT / "build_exe.py")),
        300,
    ),
}

SYNTAX_CHECK_IDS = (
    "syntax_app",
    "syntax_agent_runtime",
    "syntax_server",
    "syntax_launcher",
    "syntax_build_exe",
)

# Standalone profiles are deliberately read-only with respect to tracked source,
# version metadata, Git refs and remotes.  The official release workflow opts in
# to frontend_build through get_release_check_ids(); it remains the same logical
# release definition, with the existing dry-run/skip-tests policies applied.
RELEASE_READ_ONLY_CHECK_IDS = (
    "git_diff_check",
    *SYNTAX_CHECK_IDS,
    "frontend_freshness",
    "frontend_bundle_syntax",
    "harness_replay",
    "pytest_full",
)

PROFILE_CHECK_IDS: dict[str, tuple[str, ...]] = {
    "quick": ("git_diff_check", *SYNTAX_CHECK_IDS),
    "ui": (
        "frontend_freshness",
        "frontend_bundle_syntax",
        "pytest_ui",
        "git_diff_check",
        "syntax_app",
    ),
    "runtime": (
        "frontend_freshness",
        "frontend_bundle_syntax",
        "pytest_full",
        "harness_replay",
        "h4",
        "git_diff_check",
        *SYNTAX_CHECK_IDS,
    ),
    "release": RELEASE_READ_ONLY_CHECK_IDS,
}


def get_profile_check_ids(profile: str) -> tuple[str, ...]:
    """Return the ordered checks for a standalone verification profile."""

    try:
        return PROFILE_CHECK_IDS[profile]
    except KeyError as exc:
        raise ValueError(f"unknown verification profile: {profile}") from exc


def get_release_check_ids(*, dry_run: bool, skip_tests: bool) -> tuple[str, ...]:
    """Return the exact ordered quality gates used by release.py.

    This preserves the historical release gate mapping:
    - formal release runs cheap source checks before build/replay/full pytest;
    - dry-run does not build, run pytest/replay, or inspect the working diff;
    - the legacy --skip-tests subset remains defined, but non-dry-run CLI reuse
      is accepted only through a current sealed prepared credential.
    """

    checks = list(RELEASE_READ_ONLY_CHECK_IDS)
    checks.insert(checks.index("frontend_freshness"), "frontend_build")
    excluded = set()
    if dry_run:
        excluded.add("frontend_build")
    if dry_run or skip_tests:
        excluded.update(("pytest_full", "harness_replay", "git_diff_check"))
    return tuple(check_id for check_id in checks if check_id not in excluded)


def get_release_definition_manifest() -> dict[str, object]:
    """Return the canonical full-release gate definition for credential binding."""

    root_text = str(ROOT)
    checks = []
    for check_id in get_release_check_ids(dry_run=False, skip_tests=False):
        spec = CHECKS[check_id]
        command = tuple(
            str(part).replace(root_text, "<ROOT>")
            for part in spec.command
        )
        checks.append(
            {
                "id": spec.check_id,
                "label": spec.label,
                "command": command,
                "timeout": spec.timeout,
            }
        )
    return {
        "schema": "code-release-verification/v1",
        "checks": checks,
    }


def get_release_definition_fingerprint() -> str:
    """Return a stable SHA-256 for the exact formal release gate definition."""

    encoded = json.dumps(
        get_release_definition_manifest(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


Executor = Callable[[CheckSpec], subprocess.CompletedProcess[str]]
DoctorExecutor = Callable[[tuple[str, ...], int], subprocess.CompletedProcess[str]]


_COMMAND_GATE = """\
import json, subprocess, sys
request = json.loads(sys.stdin.readline())
raise SystemExit(subprocess.call(request['command'], shell=request['shell']))
"""


def _write_live(stream, text):
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        stream.write(text.encode(encoding, errors="backslashreplace").decode(encoding))
    stream.flush()


def run_logged_command(command, *, cwd, timeout, env=None, label="command",
                       stream=None, log_dir=None, cancel_event=None):
    """Stream diagnostics; use the existing Job owner before releasing a child.

    The tiny stdin gate cannot spawn the requested command until containment
    succeeds. Quiet identity/credential commands deliberately do not use this.
    """
    output = stream if stream is not None else sys.stdout
    directory = Path(log_dir) if log_dir is not None else Path(tempfile.mkdtemp(prefix="code-check-"))
    directory.mkdir(parents=True, exist_ok=True)
    stdout_path, stderr_path = directory / "stdout.log", directory / "stderr.log"
    for path in (stdout_path, stderr_path):
        path.touch(exist_ok=False)
    started = time.monotonic()
    captured = {"stdout": [], "stderr": []}
    pump_errors, threads = [], []
    console_lock = threading.Lock()
    process, job, attached = None, None, False
    status, failure = "failed", None
    environment = dict(os.environ if env is None else env)
    environment.setdefault("PYTHONUNBUFFERED", "1")
    environment["PYTHONIOENCODING"] = "utf-8"
    _write_live(output, f"START {label} timeout={timeout}s logs={directory}\n")

    def pump(pipe, name, path):
        decoder = io.IncrementalNewlineDecoder(codecs.getincrementaldecoder("utf-8")(errors="replace"), translate=True)
        try:
            with path.open("a", encoding="utf-8", newline="", buffering=1) as log:
                while True:
                    chunk = pipe.read1(4096)
                    text = decoder.decode(chunk, final=not chunk)
                    if text:
                        captured[name].append(text)
                        log.write(text)
                        log.flush()
                        with console_lock:
                            _write_live(output, text)
                    if not chunk:
                        break
        except Exception as exc:
            pump_errors.append(exc)
        finally:
            pipe.close()

    try:
        if os.name == "nt":
            from code_runtime.skill_dependency_operation import _WindowsJob
            job = _WindowsJob()
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", _COMMAND_GATE], cwd=str(cwd), env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
        if job is not None:
            job.attach(process)
            attached = True
        for name, path in (("stdout", stdout_path), ("stderr", stderr_path)):
            thread = threading.Thread(target=pump, args=(getattr(process, name), name, path), daemon=True)
            thread.start()
            threads.append(thread)
        payload_command = command if isinstance(command, str) else [os.fspath(part) for part in command]
        process.stdin.write((json.dumps({"command": payload_command, "shell": isinstance(command, str)}) + "\n").encode("utf-8"))
        process.stdin.close()
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                raise KeyboardInterrupt("command cancelled")
            if pump_errors:
                raise OSError("command diagnostic stream failed") from pump_errors[0]
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                process.wait(timeout=min(remaining, 0.1))
            except subprocess.TimeoutExpired:
                pass
        status = "passed" if process.returncode == 0 else "failed"
    except BaseException as exc:
        failure = exc
        status = "timeout" if isinstance(exc, subprocess.TimeoutExpired) else "cancelled" if isinstance(exc, KeyboardInterrupt) else "failed"
    finally:
        # Confirm the existing Job is empty before reporting completion, even
        # when a descendant outlives its leader. No process-name enumeration.
        if job is not None:
            try:
                if attached and not job.empty():
                    job.stop()
                    deadline = time.monotonic() + 5
                    while not job.empty() and time.monotonic() < deadline:
                        time.sleep(0.01)
                    if not job.empty():
                        raise OSError("command process tree exit unconfirmed")
            except Exception as exc:
                failure = failure or exc
                status = "failed"
            finally:
                job.close()
        if process is not None:
            if os.name != "nt":
                import signal
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif not attached and process.poll() is None:
                process.kill()  # Still behind the unopened stdin gate.
            process.wait(timeout=5)
            if process.stdin and not process.stdin.closed:
                try:
                    process.stdin.close()
                except OSError:
                    pass  # The gated child was already stopped during setup.
        for thread in threads:
            thread.join(timeout=5)
        if any(thread.is_alive() for thread in threads) or pump_errors:
            failure = failure or OSError("command diagnostics did not finish")
            status = "failed"
        stdout, stderr = "".join(captured["stdout"]), "".join(captured["stderr"])
        exit_code = 124 if status == "timeout" else 130 if status == "cancelled" else process.returncode if process else 127
        if failure is not None and exit_code == 0:
            exit_code = 127
        summary = {"label": label, "status": status, "exitCode": exit_code,
                   "elapsedSeconds": round(time.monotonic() - started, 3),
                   "stdout": stdout_path.name, "stderr": stderr_path.name}
        if failure is not None:
            summary["error"] = f"{type(failure).__name__}: {failure}"
        (directory / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_live(output, f"\nEND {label} status={status} exit={exit_code} elapsed={summary['elapsedSeconds']}s logs={directory}\n")
    if failure is not None:
        if isinstance(failure, subprocess.TimeoutExpired):
            failure.output, failure.stderr = stdout, stderr
        raise failure
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _default_executor(spec: CheckSpec, *, stream=None) -> subprocess.CompletedProcess[str]:
    return run_logged_command(list(spec.command), cwd=ROOT, timeout=spec.timeout,
                              label=spec.check_id, stream=stream)


def _default_doctor_executor(
    command: tuple[str, ...],
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _write_lines(stream: TextIO, values: Iterable[str]) -> None:
    for value in values:
        if value:
            line = value.rstrip() + "\n"
            try:
                stream.write(line)
            except UnicodeEncodeError:
                encoding = getattr(stream, "encoding", None) or "utf-8"
                safe_line = line.encode(encoding, errors="backslashreplace").decode(encoding)
                stream.write(safe_line)


def _doctor_result(
    check_id: str,
    status: str,
    reason: str,
    **detail: object,
) -> DoctorCheckResult:
    return DoctorCheckResult(check_id, status, reason, detail)


def _default_module_finder(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _parse_json_output(output: str) -> dict[str, object] | None:
    for line in reversed(output.splitlines()):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _command_failure_detail(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    lines = [
        line.strip()
        for line in f"{result.stdout or ''}\n{result.stderr or ''}".splitlines()
        if line.strip()
    ]
    return {
        "exitCode": result.returncode,
        "message": (lines[-1] if lines else "command failed")[:300],
    }


def _normalized_executable(value: str) -> str:
    return os.path.normcase(os.path.realpath(value))


def run_doctor(
    *,
    executor: DoctorExecutor | None = None,
    which: Callable[[str], str | None] | None = None,
    module_finder: Callable[[str], bool] | None = None,
    stream: TextIO | None = None,
    current_executable: str | None = None,
    current_version: str | None = None,
) -> int:
    """Probe development capabilities without changing verification profiles.

    The doctor deliberately aggregates all independent failures. It never
    installs dependencies, contacts the network, or writes tracked outputs.
    """

    output = stream or sys.stdout
    invoke = executor or _default_doctor_executor
    resolve = which or shutil.which
    find_module = module_finder or _default_module_finder
    active_executable = current_executable or sys.executable
    active_version = current_version or platform.python_version()
    results: list[DoctorCheckResult] = [
        _doctor_result(
            "python_current",
            "passed",
            "ready",
            executable=active_executable,
            version=active_version,
        )
    ]

    missing_current = [
        package_name
        for import_name, package_name in DOCTOR_PYTHON_MODULES
        if not find_module(import_name)
    ]
    results.append(
        _doctor_result(
            "python_current_modules",
            "failed" if missing_current else "passed",
            "missing" if missing_current else "ready",
            missing=missing_current,
        )
    )

    h4_command = resolve("python")
    h4_payload: dict[str, object] | None = None
    if not h4_command:
        results.extend(
            (
                _doctor_result("python_h4", "failed", "missing", command="python"),
                _doctor_result("python_identity", "failed", "blocked"),
                _doctor_result("python_h4_modules", "failed", "blocked"),
            )
        )
    else:
        try:
            h4_process = invoke(("python", "-c", H4_PYTHON_PROBE), DOCTOR_COMMAND_TIMEOUT)
        except subprocess.TimeoutExpired:
            results.extend(
                (
                    _doctor_result("python_h4", "failed", "timeout", command=h4_command),
                    _doctor_result("python_identity", "failed", "blocked"),
                    _doctor_result("python_h4_modules", "failed", "blocked"),
                )
            )
        except OSError as exc:
            results.extend(
                (
                    _doctor_result(
                        "python_h4",
                        "failed",
                        "spawn_failed",
                        command=h4_command,
                        error=type(exc).__name__,
                    ),
                    _doctor_result("python_identity", "failed", "blocked"),
                    _doctor_result("python_h4_modules", "failed", "blocked"),
                )
            )
        else:
            h4_payload = _parse_json_output(h4_process.stdout or "")
            if h4_process.returncode != 0 or not h4_payload:
                detail = _command_failure_detail(h4_process)
                results.extend(
                    (
                        _doctor_result("python_h4", "failed", "invalid_output", **detail),
                        _doctor_result("python_identity", "failed", "blocked"),
                        _doctor_result("python_h4_modules", "failed", "blocked"),
                    )
                )
            else:
                h4_executable = str(h4_payload.get("executable") or h4_command)
                h4_version = str(h4_payload.get("version") or "unknown")
                results.append(
                    _doctor_result(
                        "python_h4",
                        "passed",
                        "ready",
                        command=h4_command,
                        executable=h4_executable,
                        version=h4_version,
                    )
                )
                same_interpreter = (
                    _normalized_executable(active_executable)
                    == _normalized_executable(h4_executable)
                )
                results.append(
                    _doctor_result(
                        "python_identity",
                        "passed" if same_interpreter else "warning",
                        "same_interpreter" if same_interpreter else "interpreter_mismatch",
                        current=active_executable,
                        h4=h4_executable,
                    )
                )
                h4_modules = h4_payload.get("modules")
                if not isinstance(h4_modules, dict):
                    results.append(
                        _doctor_result("python_h4_modules", "failed", "invalid_output")
                    )
                else:
                    missing_h4 = [
                        package_name
                        for import_name, package_name in DOCTOR_PYTHON_MODULES
                        if not bool(h4_modules.get(import_name))
                    ]
                    results.append(
                        _doctor_result(
                            "python_h4_modules",
                            "failed" if missing_h4 else "passed",
                            "missing" if missing_h4 else "ready",
                            missing=missing_h4,
                        )
                    )

    node_command = resolve("node")
    if not node_command:
        results.append(_doctor_result("node_runtime", "failed", "missing", command="node"))
    else:
        try:
            node_process = invoke((node_command, "--version"), DOCTOR_COMMAND_TIMEOUT)
        except subprocess.TimeoutExpired:
            results.append(_doctor_result("node_runtime", "failed", "timeout", command=node_command))
        except OSError as exc:
            results.append(
                _doctor_result(
                    "node_runtime",
                    "failed",
                    "spawn_failed",
                    command=node_command,
                    error=type(exc).__name__,
                )
            )
        else:
            if node_process.returncode == 0:
                results.append(
                    _doctor_result(
                        "node_runtime",
                        "passed",
                        "ready",
                        command=node_command,
                        version=(node_process.stdout or "").strip(),
                    )
                )
            else:
                results.append(
                    _doctor_result(
                        "node_runtime",
                        "failed",
                        "command_failed",
                        command=node_command,
                        **_command_failure_detail(node_process),
                    )
                )

    npm_command = resolve(NPM)
    if not npm_command:
        results.append(_doctor_result("npm_runtime", "failed", "missing", command=NPM))
    else:
        try:
            npm_process = invoke((npm_command, "--version"), DOCTOR_COMMAND_TIMEOUT)
        except subprocess.TimeoutExpired:
            results.append(_doctor_result("npm_runtime", "failed", "timeout", command=npm_command))
        except OSError as exc:
            results.append(
                _doctor_result(
                    "npm_runtime",
                    "failed",
                    "spawn_failed",
                    command=npm_command,
                    error=type(exc).__name__,
                )
            )
        else:
            if npm_process.returncode == 0:
                results.append(
                    _doctor_result(
                        "npm_runtime",
                        "passed",
                        "ready",
                        command=npm_command,
                        version=(npm_process.stdout or "").strip(),
                    )
                )
            else:
                results.append(
                    _doctor_result(
                        "npm_runtime",
                        "failed",
                        "command_failed",
                        command=npm_command,
                        **_command_failure_detail(npm_process),
                    )
                )

    if not node_command:
        results.extend(
            _doctor_result(check_id, "failed", "blocked")
            for check_id in DOCTOR_NODE_CHECK_IDS
        )
    else:
        try:
            node_probe = invoke(
                (node_command, str(DOCTOR_NODE_PROBE)),
                DOCTOR_NODE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            results.extend(
                _doctor_result(check_id, "failed", "timeout")
                for check_id in DOCTOR_NODE_CHECK_IDS
            )
        except OSError as exc:
            results.extend(
                _doctor_result(
                    check_id,
                    "failed",
                    "spawn_failed",
                    error=type(exc).__name__,
                )
                for check_id in DOCTOR_NODE_CHECK_IDS
            )
        else:
            node_payload = _parse_json_output(node_probe.stdout or "")
            node_checks = node_payload.get("checks") if node_payload else None
            if (
                not node_payload
                or node_payload.get("schema") != DOCTOR_NODE_SCHEMA
                or not isinstance(node_checks, list)
            ):
                detail = _command_failure_detail(node_probe)
                results.extend(
                    _doctor_result(check_id, "failed", "invalid_output", **detail)
                    for check_id in DOCTOR_NODE_CHECK_IDS
                )
            else:
                checks_by_id = {
                    item.get("id"): item
                    for item in node_checks
                    if isinstance(item, dict)
                }
                node_results = []
                for check_id in DOCTOR_NODE_CHECK_IDS:
                    item = checks_by_id.get(check_id)
                    if not item:
                        node_results.append(
                            _doctor_result(check_id, "failed", "invalid_output")
                        )
                        continue
                    status = str(item.get("status") or "failed")
                    reason = str(item.get("reason") or "invalid_output")
                    detail = item.get("detail")
                    node_results.append(
                        DoctorCheckResult(
                            check_id,
                            status if status in {"passed", "failed"} else "failed",
                            reason,
                            detail if isinstance(detail, dict) else {},
                        )
                    )
                if node_probe.returncode != 0 and not any(
                    result.status == "failed" for result in node_results
                ):
                    node_results[-1] = _doctor_result(
                        "chromium_launch",
                        "failed",
                        "probe_exit",
                        **_command_failure_detail(node_probe),
                    )
                results.extend(node_results)

    _write_lines(output, (f"DOCTOR schema={DOCTOR_SCHEMA}",))
    for result in results:
        detail = json.dumps(
            result.detail,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        _write_lines(
            output,
            (
                f"CHECK id={result.check_id} status={result.status} "
                f"reason={result.reason} detail={detail}",
            ),
        )
    failed = [result.check_id for result in results if result.status == "failed"]
    _write_lines(output, (f"FIRST_FAILURE {failed[0] if failed else 'none'}",))
    exit_code = 1 if failed else 0
    _write_lines(
        output,
        (f"RESULT doctor status={'failed' if failed else 'passed'} exit={exit_code}",),
    )
    return exit_code


def run_profile(
    profile: str,
    *,
    executor: Executor | None = None,
    stream: TextIO | None = None,
) -> int:
    """Execute one profile fail-fast and emit a stable, citable summary."""

    output = stream or sys.stdout
    if profile not in PROFILE_CHECK_IDS:
        available = ",".join(PROFILE_CHECK_IDS)
        output.write(f"VERIFY profile={profile}\n")
        output.write(f"ERROR unknown_profile={profile} available={available}\n")
        output.write(f"FIRST_FAILURE unknown_profile\n")
        output.write(f"RESULT profile={profile} status=failed exit=2\n")
        return 2

    selected = get_profile_check_ids(profile)
    skipped = tuple(check_id for check_id in CHECKS if check_id not in selected)
    output.write(f"VERIFY profile={profile}\n")
    output.write(f"EXECUTE count={len(selected)} items={','.join(selected)}\n")
    output.write(f"SKIP count={len(skipped)} items={','.join(skipped) or '-'}\n")

    invoke = executor or (lambda spec: _default_executor(spec, stream=output))
    for index, check_id in enumerate(selected, start=1):
        spec = CHECKS[check_id]
        output.write(
            f"START index={index}/{len(selected)} id={check_id} timeout={spec.timeout}s\n"
        )
        try:
            result = invoke(spec)
        except subprocess.TimeoutExpired as exc:
            if executor is not None:
                _write_lines(output, (str(exc.stdout or ""), str(exc.stderr or "")))
            output.write(f"FAIL id={check_id} reason=timeout exit=124\n")
            output.write(f"FIRST_FAILURE {check_id}\n")
            output.write(f"RESULT profile={profile} status=failed exit=124\n")
            return 124
        except OSError as exc:
            output.write(f"FAIL id={check_id} reason=spawn_error detail={exc}\n")
            output.write(f"FIRST_FAILURE {check_id}\n")
            output.write(f"RESULT profile={profile} status=failed exit=127\n")
            return 127

        if executor is not None:
            _write_lines(output, (result.stdout or "", result.stderr or ""))
        if result.returncode != 0:
            output.write(f"FAIL id={check_id} reason=command exit={result.returncode}\n")
            output.write(f"FIRST_FAILURE {check_id}\n")
            output.write(
                f"RESULT profile={profile} status=failed exit={result.returncode}\n"
            )
            return result.returncode
        output.write(f"PASS id={check_id}\n")

    output.write("FIRST_FAILURE none\n")
    output.write(f"RESULT profile={profile} status=passed exit=0\n")
    return 0
