"""Shared, read-only verification profiles for local development and releases."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Iterable, TextIO


ROOT = Path(__file__).resolve().parent
NPM = "npm.cmd" if os.name == "nt" else "npm"


@dataclass(frozen=True)
class CheckSpec:
    """One deterministic verification command."""

    check_id: str
    label: str
    command: tuple[str, ...]
    timeout: int


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
        (sys.executable, "-m", "pytest", "tests", "-q"),
        180,
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
    "frontend_freshness",
    "frontend_bundle_syntax",
    "pytest_full",
    "harness_replay",
    "git_diff_check",
    *SYNTAX_CHECK_IDS,
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
    - formal release builds the bundle, then runs the complete release profile;
    - dry-run does not build, run pytest/replay, or inspect the working diff;
    - the legacy --skip-tests subset remains defined, but non-dry-run CLI reuse
      is accepted only through a current sealed prepared credential.
    """

    checks = ("frontend_build", *RELEASE_READ_ONLY_CHECK_IDS)
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


def _default_executor(spec: CheckSpec) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(spec.command),
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=spec.timeout,
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

    invoke = executor or _default_executor
    for index, check_id in enumerate(selected, start=1):
        spec = CHECKS[check_id]
        output.write(
            f"START index={index}/{len(selected)} id={check_id} timeout={spec.timeout}s\n"
        )
        try:
            result = invoke(spec)
        except subprocess.TimeoutExpired as exc:
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
