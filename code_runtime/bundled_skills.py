"""Fail-safe bundled Skill upgrade sync and persistent deletion intent."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path


STATE_SCHEMA = "code-bundled-skills/v1"
STATE_FILENAME = "bundled-skills-state.json"
WORK_DIRNAME = ".bundled-skill-work"
MAX_STATE_BYTES = 64 * 1024
_SAFE_SKILL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_WORK_ITEM = re.compile(
    r"^(?P<kind>copy|delete)-(?P<name>[A-Za-z0-9][A-Za-z0-9_-]{0,63})-"
    r"(?P<nonce>[0-9a-f]{32})$",
)


class BundledSkillStateError(ValueError):
    """Raised when bundled Skill state or a delete transaction is unsafe."""


def bundled_skill_state_path(installed_skills_dir):
    return Path(installed_skills_dir).parent / STATE_FILENAME


def bundled_skill_work_root(installed_skills_dir):
    return Path(installed_skills_dir).parent / WORK_DIRNAME


def _empty_state():
    return {"schema": STATE_SCHEMA, "tombstones": []}


def _normalize_state(payload):
    if not isinstance(payload, dict) or payload.get("schema") != STATE_SCHEMA:
        raise BundledSkillStateError("bundled Skill state schema is invalid")
    tombstones = payload.get("tombstones")
    if not isinstance(tombstones, list):
        raise BundledSkillStateError("bundled Skill tombstones must be an array")
    normalized = []
    for item in tombstones:
        name = str(item or "")
        if not _SAFE_SKILL_NAME.fullmatch(name) or name in normalized:
            raise BundledSkillStateError("bundled Skill tombstone is invalid")
        normalized.append(name)
    return {"schema": STATE_SCHEMA, "tombstones": sorted(normalized)}


def load_bundled_skill_state(installed_skills_dir):
    path = bundled_skill_state_path(installed_skills_dir)
    if path.is_symlink():
        raise BundledSkillStateError("bundled Skill state path is not a regular file")
    if not path.exists():
        return _empty_state()
    try:
        if not path.is_file():
            raise BundledSkillStateError("bundled Skill state path is not a regular file")
        if path.stat().st_size > MAX_STATE_BYTES:
            raise BundledSkillStateError("bundled Skill state is too large")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except BundledSkillStateError:
        raise
    except Exception as exc:
        raise BundledSkillStateError(f"bundled Skill state is unreadable: {exc}") from exc
    return _normalize_state(payload)


def _atomic_write_state(installed_skills_dir, state):
    path = bundled_skill_state_path(installed_skills_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_state(state)
    payload = (
        json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        temp_path = None
    except Exception as exc:
        raise BundledSkillStateError(f"bundled Skill state write failed: {exc}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _cleanup_partial_directory(path):
    path = Path(path)
    if not path.exists():
        return True
    try:
        shutil.rmtree(path)
    except OSError:
        try:
            shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass
    return not path.exists()


def _ensure_work_root(installed_skills_dir):
    work_root = bundled_skill_work_root(installed_skills_dir)
    if work_root.is_symlink():
        raise BundledSkillStateError("bundled Skill work root is not a regular directory")
    work_root.mkdir(parents=True, exist_ok=True)
    if not work_root.is_dir():
        raise BundledSkillStateError("bundled Skill work root is not a directory")
    return work_root


def _reconcile_work_root(installed_skills_dir, state):
    installed_skills_dir = Path(installed_skills_dir)
    work_root = _ensure_work_root(installed_skills_dir)
    tombstones = set(state["tombstones"])
    errors = []
    for item in sorted(work_root.iterdir(), key=lambda path: path.name.lower()):
        match = _WORK_ITEM.fullmatch(item.name)
        if not match or not item.is_dir() or item.is_symlink():
            errors.append({"stage": "work_reconcile", "error": f"unrecognized work item: {item.name}"})
            continue
        kind = match.group("kind")
        name = match.group("name")
        destination = installed_skills_dir / name
        if kind == "copy" or name in tombstones:
            if not _cleanup_partial_directory(item):
                errors.append({"skill": name, "stage": "cleanup", "error": "work item cleanup failed"})
            continue
        if destination.exists():
            errors.append({
                "skill": name,
                "stage": "delete_recovery",
                "error": "destination already exists; quarantine preserved",
            })
            continue
        try:
            os.rename(item, destination)
        except OSError as exc:
            errors.append({"skill": name, "stage": "delete_recovery", "error": str(exc)})
    return work_root, errors


def sync_missing_bundled_skills(bundled_skills_dir, installed_skills_dir):
    """Copy only missing, non-tombstoned bundled Skill directories."""
    bundled_skills_dir = Path(bundled_skills_dir)
    installed_skills_dir = Path(installed_skills_dir)
    result = {
        "ok": True,
        "status": "ready",
        "copied": [],
        "existing": [],
        "tombstoned": [],
        "errors": [],
    }
    if not bundled_skills_dir.is_dir():
        result["status"] = "source_missing"
        return result
    installed_skills_dir.mkdir(parents=True, exist_ok=True)
    try:
        state = load_bundled_skill_state(installed_skills_dir)
    except BundledSkillStateError as exc:
        result.update({"ok": False, "status": "state_invalid"})
        result["errors"].append({"stage": "state", "error": str(exc)})
        return result

    try:
        work_root, reconcile_errors = _reconcile_work_root(installed_skills_dir, state)
    except BundledSkillStateError as exc:
        result.update({"ok": False, "status": "work_invalid"})
        result["errors"].append({"stage": "work", "error": str(exc)})
        return result
    if reconcile_errors:
        result["ok"] = False
        result["status"] = "partial"
        result["errors"].extend(reconcile_errors)

    tombstones = set(state["tombstones"])
    sources = sorted(
        (
            path for path in bundled_skills_dir.iterdir()
            if path.is_dir() and _SAFE_SKILL_NAME.fullmatch(path.name)
        ),
        key=lambda path: path.name.lower(),
    )
    for source in sources:
        name = source.name
        destination = installed_skills_dir / name
        if destination.exists():
            result["existing"].append(name)
            continue
        if name in tombstones:
            result["tombstoned"].append(name)
            continue
        temp_dir = work_root / f"copy-{name}-{uuid.uuid4().hex}"
        temp_dir.mkdir()
        try:
            shutil.copytree(source, temp_dir, dirs_exist_ok=True)
            if destination.exists():
                result["existing"].append(name)
                continue
            os.rename(temp_dir, destination)
            temp_dir = None
            result["copied"].append(name)
        except Exception as exc:
            result["ok"] = False
            result["status"] = "partial"
            result["errors"].append({"skill": name, "stage": "copy", "error": str(exc)})
        finally:
            if temp_dir is not None and not _cleanup_partial_directory(temp_dir):
                result["ok"] = False
                result["status"] = "partial"
                result["errors"].append({
                    "skill": name,
                    "stage": "cleanup",
                    "error": "partial directory cleanup failed",
                })
    return result


def delete_installed_skill(name, bundled_skills_dir, installed_skills_dir):
    """Delete one installed Skill, persisting intent for bundled names."""
    name = str(name or "")
    if not _SAFE_SKILL_NAME.fullmatch(name):
        raise BundledSkillStateError("invalid skill name")
    bundled_skills_dir = Path(bundled_skills_dir)
    installed_skills_dir = Path(installed_skills_dir)
    skill_dir = installed_skills_dir / name
    if not skill_dir.is_dir():
        raise BundledSkillStateError("skill not found")
    if not (bundled_skills_dir / name).is_dir():
        shutil.rmtree(skill_dir)
        return {"ok": True}

    previous_state = load_bundled_skill_state(installed_skills_dir)
    work_root = _ensure_work_root(installed_skills_dir)
    next_state = {
        "schema": STATE_SCHEMA,
        "tombstones": sorted({*previous_state["tombstones"], name}),
    }
    backup = work_root / f"delete-{name}-{uuid.uuid4().hex}"
    try:
        os.rename(skill_dir, backup)
    except OSError as exc:
        raise BundledSkillStateError(f"bundled Skill delete staging failed: {exc}") from exc

    try:
        _atomic_write_state(installed_skills_dir, next_state)
    except Exception as exc:
        try:
            os.rename(backup, skill_dir)
        except OSError as rollback_exc:
            raise BundledSkillStateError(
                f"bundled Skill state failed and directory rollback failed: {rollback_exc}",
            ) from exc
        raise BundledSkillStateError(str(exc)) from exc

    try:
        shutil.rmtree(backup)
    except OSError:
        # The deletion intent is already durable and the original directory is
        # no longer visible. Keep any partial quarantine outside skills/ so a
        # later startup can retry exact-path cleanup without restoring damage.
        pass
    return {"ok": True}
