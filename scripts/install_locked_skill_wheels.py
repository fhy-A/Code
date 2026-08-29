#!/usr/bin/env python3
"""Install or roll back the audited PPT Master wheels in Code's managed venv.

The helper deliberately exposes no package, command, index, target-directory,
or resolver controls.  Candidate wheels must match the repository lock and a
fresh report from ``audit_locked_python_wheels.py``.  Execution is delegated to
the existing managed dependency plan executor and never invokes a shell.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import skill_dependencies  # noqa: E402  (repository root is intentionally pinned first)


DATA_ROOT = REPOSITORY_ROOT / "data"
RUNTIME_ROOT = DATA_ROOT / "runtime"
PYTHON_ROOT = RUNTIME_ROOT / "python"
MANAGED_PYTHON = PYTHON_ROOT / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
LOCK_PATH = DATA_ROOT / "skills" / "ppt-master" / "dependency-lock.json"


class LockedInstallError(RuntimeError):
    """Raised when the immutable install contract is not satisfied."""


def _canonical_name(value: str) -> str:
    import re

    return re.sub(r"[-_.]+", "-", str(value or "").strip()).lower()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_reparse(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(__import__("stat"), "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _safe_wheel_root(value: str) -> Path:
    root = Path(value).resolve(strict=True)
    temp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "").resolve(strict=True)
    try:
        root.relative_to(temp)
    except ValueError as exc:
        raise LockedInstallError("wheel root is outside the system TEMP directory") from exc
    if root == temp or root.is_symlink() or _is_reparse(root):
        raise LockedInstallError("wheel root must be a non-reparse child of system TEMP")
    return root


def _distribution_snapshot() -> dict:
    if not MANAGED_PYTHON.is_file():
        raise LockedInstallError("Code managed Python runtime is missing")
    program = r'''
import importlib.metadata as metadata
import json
import pathlib
import sys

rows = []
for dist in metadata.distributions():
    name = dist.metadata.get("Name") or ""
    record = pathlib.Path(dist._path) / "RECORD"
    rows.append({
        "name": name,
        "version": dist.version,
        "recordSha256": __import__("hashlib").sha256(record.read_bytes()).hexdigest()
            if record.is_file() else "",
    })
print(json.dumps({
    "prefix": sys.prefix,
    "basePrefix": sys.base_prefix,
    "distributions": sorted(rows, key=lambda item: item["name"].lower()),
}, sort_keys=True))
'''
    completed = subprocess.run(
        [str(MANAGED_PYTHON), "-I", "-c", program],
        cwd=str(RUNTIME_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode:
        raise LockedInstallError(f"managed runtime snapshot failed: {completed.stderr[:500]}")
    snapshot = json.loads(completed.stdout)
    if Path(snapshot["prefix"]).resolve() != PYTHON_ROOT.resolve():
        raise LockedInstallError("managed Python reported an unexpected sys.prefix")
    return snapshot


def _snapshot_map(snapshot: dict) -> dict[str, dict]:
    return {
        _canonical_name(item.get("name")): item
        for item in snapshot.get("distributions", [])
        if item.get("name")
    }


def _load_lock() -> dict:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if lock.get("skill") != "ppt-master" or lock.get("capability") != "offline-core":
        raise LockedInstallError("dependency lock identity is invalid")
    expected = {
        (_canonical_name(item.get("project")), str(item.get("version")))
        for item in lock.get("wheels", [])
    }
    if expected != {("skia-pathops", "0.9.2"), ("uharfbuzz", "0.50.0")}:
        raise LockedInstallError("dependency lock must contain exactly the admitted packages")
    return lock


def _load_install_contract(lock: dict, wheel_root: Path) -> list[Path]:
    audit_path = wheel_root / "wheel-audit.json"
    if not audit_path.is_file() or audit_path.is_symlink() or _is_reparse(audit_path):
        raise LockedInstallError("fresh wheel audit report is missing or unsafe")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audited = {
        (_canonical_name(item.get("project")), str(item.get("version"))): item
        for item in audit.get("wheels", [])
    }
    wheels: list[Path] = []
    for expected in lock.get("wheels", []):
        key = (_canonical_name(expected.get("project")), str(expected.get("version")))
        actual = audited.get(key)
        if not actual:
            raise LockedInstallError(f"wheel audit does not contain {key[0]}=={key[1]}")
        for field in ("filename", "url", "size", "sha256", "wheelTags"):
            if actual.get(field) != expected.get(field):
                raise LockedInstallError(f"wheel audit differs from lock: {key[0]} {field}")
        if actual.get("metadata", {}).get("license") != expected.get("license"):
            raise LockedInstallError(f"wheel license differs from lock: {key[0]}")
        if actual.get("metadata", {}).get("requiresDist") != expected.get("requiresDist"):
            raise LockedInstallError(f"wheel dependencies differ from lock: {key[0]}")
        if actual.get("nativeImports", {}).get("unexplainedImports"):
            raise LockedInstallError(f"wheel has unexplained native imports: {key[0]}")
        wheel = (wheel_root / expected["filename"]).resolve(strict=True)
        try:
            wheel.relative_to(wheel_root)
        except ValueError as exc:
            raise LockedInstallError("wheel path escapes the audited root") from exc
        if wheel.is_symlink() or _is_reparse(wheel):
            raise LockedInstallError("wheel file is a symlink or reparse point")
        if wheel.stat().st_size != expected["size"] or _sha256(wheel) != expected["sha256"]:
            raise LockedInstallError(f"wheel bytes differ from lock: {wheel.name}")
        wheels.append(wheel)
    if len(wheels) != 2:
        raise LockedInstallError("lock must contain exactly two wheels")
    return wheels


def _plan(action: str, lock: dict, wheels: list[Path]) -> dict:
    projects = [item["project"] for item in lock["wheels"]]
    if action == "install":
        argv = [
            str(MANAGED_PYTHON), "-I", "-m", "pip", "install",
            "--disable-pip-version-check", "--no-index", "--no-deps",
            "--only-binary=:all:", "--no-compile", *map(str, wheels),
        ]
        summary = "managed python -m pip install --no-index --no-deps " + " ".join(
            path.name for path in wheels
        )
    else:
        argv = [str(MANAGED_PYTHON), "-I", "-m", "pip", "uninstall", "--yes", *projects]
        summary = "managed python -m pip uninstall --yes " + " ".join(projects)
    plan = {
        "schemaVersion": 1,
        "skill": lock["skill"],
        "capability": lock["capability"],
        "action": action,
        "actionable": True,
        "noChanges": False,
        "blockedReasons": [],
        "requirements": [],
        "systemRequirements": [],
        "locations": {"python": str(PYTHON_ROOT)},
        "authorization": {
            "scope": "managed_runtime",
            "root": str(RUNTIME_ROOT),
            "systemPackageManagers": False,
            "pathChanges": False,
            "globalWrappers": False,
        },
        "steps": [{
            "id": f"{action}-locked-python-wheels",
            "type": "python",
            "purpose": f"{action}_locked_wheels",
            "target": str(PYTHON_ROOT),
            "displayCommand": summary,
            "_argv": argv,
            "_cwd": str(RUNTIME_ROOT),
            "_ensureDirectories": [str(RUNTIME_ROOT)],
        }],
        "commandSummaries": [summary],
    }
    public = skill_dependencies.public_dependency_operation_plan(plan)
    canonical = json.dumps(public, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    plan["fingerprint"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return plan


def _execute(plan: dict) -> dict:
    return skill_dependencies.execute_dependency_operation_plan(plan, timeout_seconds=300)


def _verify_transition(before: dict, after: dict, lock: dict, action: str) -> dict:
    before_map, after_map = _snapshot_map(before), _snapshot_map(after)
    targets = {_canonical_name(item["project"]): item for item in lock["wheels"]}
    changed = sorted(
        name for name in set(before_map) | set(after_map)
        if before_map.get(name) != after_map.get(name)
    )
    if set(changed) != set(targets):
        raise LockedInstallError(f"managed distributions changed outside lock: {changed}")
    for name, expected in targets.items():
        if action == "install":
            if before_map.get(name):
                raise LockedInstallError(f"target was already installed before admission: {name}")
            if after_map.get(name, {}).get("version") != expected["version"]:
                raise LockedInstallError(f"installed version mismatch: {name}")
        elif after_map.get(name):
            raise LockedInstallError(f"rollback left target installed: {name}")
    return {"changedDistributions": changed, "beforeCount": len(before_map), "afterCount": len(after_map)}


def _execute_with_verified_recovery(plan: dict, lock: dict, wheels: list[Path], before: dict) -> dict:
    result = _execute(plan)
    if result.get("ok"):
        return result
    cleanup = _execute(_plan("rollback", lock, wheels))
    if not cleanup.get("ok"):
        raise LockedInstallError("locked install failed and automatic rollback failed")
    restored = _distribution_snapshot()
    if restored != before:
        raise LockedInstallError(
            "locked install failed and automatic rollback did not restore the exact pre-install baseline"
        )
    raise LockedInstallError("locked install failed; exact pre-install baseline was restored")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "rollback"))
    parser.add_argument("--wheel-root")
    args = parser.parse_args()
    lock = _load_lock()
    if args.action == "install":
        if not args.wheel_root:
            raise LockedInstallError("install requires --wheel-root with freshly audited wheels")
        wheel_root = _safe_wheel_root(args.wheel_root)
        wheels = _load_install_contract(lock, wheel_root)
    else:
        wheels = []
    before = _distribution_snapshot()
    before_map = _snapshot_map(before)
    targets = {_canonical_name(item["project"]) for item in lock["wheels"]}
    if args.action == "install" and any(name in before_map for name in targets):
        raise LockedInstallError("locked target is already installed; use rollback first")
    if args.action == "rollback" and any(
        before_map.get(_canonical_name(item["project"]), {}).get("version") != item["version"]
        for item in lock["wheels"]
    ):
        raise LockedInstallError("rollback target is absent or differs from the lock")

    plan = _plan(args.action, lock, wheels)
    if args.action == "install":
        result = _execute_with_verified_recovery(plan, lock, wheels, before)
    else:
        result = _execute(plan)
        if not result.get("ok"):
            raise LockedInstallError("locked rollback operation failed")
    after = _distribution_snapshot()
    transition = _verify_transition(before, after, lock, args.action)
    print(json.dumps({
        "ok": True,
        "action": args.action,
        "plan": skill_dependencies.public_dependency_operation_plan(plan),
        "operation": result,
        "transition": transition,
        "managedRuntime": str(PYTHON_ROOT.relative_to(REPOSITORY_ROOT)).replace("\\", "/"),
    }, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError, LockedInstallError) as exc:
        print(f"locked wheel operation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
