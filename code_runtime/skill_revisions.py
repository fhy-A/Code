"""Read-only, content-addressed identity for complete Code Skill packages."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import unicodedata
from .bundled_skills import (
    BundledSkillStateError,
    STATE_FILENAME as LEGACY_STATE_FILENAME,
    load_bundled_skill_state,
)
REVISION_SCHEMA = "code-skill-revision/v1"
CATALOG_SCHEMA = "code-skill-bundled-catalog/v1"
MIGRATION_SCHEMA = "code-skill-migration-shadow/v1"
CATALOG_FILENAME = "catalog.json"
MAX_SKILLS = 256
MAX_FILES = 4096
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_DEPTH = 24
MAX_PATH_BYTES = 1024
MAX_CATALOG_BYTES = 256 * 1024
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_DIRECTORY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_SKILL_ID_RE = re.compile(r"code\.bundle/[a-z0-9][a-z0-9._-]{0,127}\Z")
_TRANSIENT_DIRECTORY = "__pycache__"
class SkillRevisionError(ValueError):
    """Stable fail-closed error for revision, catalog, and shadow planning."""

    def __init__(self, code, message="Skill revision identity is invalid"):
        self.code = str(code)
        super().__init__(message)
def _fail(code, message="Skill revision identity is invalid"):
    raise SkillRevisionError(code, message)
def _canonical_json(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
def _digest(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()
def _path_kind(path):
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unreadable"
    attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
    reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400) or 0x400)
    if stat.S_ISLNK(metadata.st_mode) or attributes & reparse:
        return "unsafe"
    if stat.S_ISDIR(metadata.st_mode):
        return "directory"
    if stat.S_ISREG(metadata.st_mode):
        return "file"
    return "special"
def _normalize_directory(value):
    if (
        not isinstance(value, str) or not _DIRECTORY_RE.fullmatch(value)
        or value.rstrip(" .") != value
    ):
        _fail("revision_path_invalid")
    return value
def _normalize_relative(value):
    if not isinstance(value, str) or "\\" in value:
        _fail("revision_path_invalid")
    path = PurePosixPath(value)
    if len(path.parts) > MAX_DEPTH:
        _fail("revision_depth_exceeded")
    if (
        not value or value.startswith("/") or path.is_absolute()
        or path.as_posix() != value
        or len(value.encode("utf-8")) > MAX_PATH_BYTES
        or unicodedata.normalize("NFC", value) != value
        or any(
            part in {"", ".", ".."} or ":" in part
            or part.rstrip(" .") != part
            or any(ord(character) < 0x20 for character in part)
            for part in path.parts
        )
    ):
        _fail("revision_path_invalid")
    return value
def _path_alias(value):
    return unicodedata.normalize("NFC", value).casefold()
def _stat_identity(metadata):
    return (
        int(metadata.st_mode), int(metadata.st_size),
        int(getattr(metadata, "st_mtime_ns", 0) or 0),
        int(getattr(metadata, "st_dev", 0) or 0),
        int(getattr(metadata, "st_ino", 0) or 0),
    )
def _read_file_bytes(path):
    return Path(path).read_bytes()
def _stable_file(path):
    try:
        before = os.lstat(path)
        if _path_kind(path) != "file":
            _fail("revision_path_unsafe")
        if before.st_size > MAX_FILE_BYTES:
            _fail("revision_file_size_exceeded")
        first = _read_file_bytes(path)
        middle = os.lstat(path)
        second = _read_file_bytes(path)
        after = os.lstat(path)
    except SkillRevisionError:
        raise
    except OSError as exc:
        raise SkillRevisionError("revision_file_unreadable") from exc
    if (
        _stat_identity(before) != _stat_identity(middle)
        or _stat_identity(middle) != _stat_identity(after)
        or len(first) != before.st_size or first != second
        or _path_kind(path) != "file"
    ):
        _fail("revision_changed_during_read")
    return first
def _canonical_content(raw):
    if b"\0" not in raw:
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            pass
        else:
            return "utf8-lf", raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return "binary", raw
def _walk_package_files(root):
    root = Path(root)
    if _path_kind(root) != "directory":
        _fail("revision_root_unsafe")
    pending = [root]
    files = []
    aliases = set()
    entry_count = 0
    while pending:
        current = pending.pop()
        try:
            children = sorted(current.iterdir(), key=lambda item: (item.name.casefold(), item.name))
        except OSError as exc:
            raise SkillRevisionError("revision_root_unreadable") from exc
        for child in children:
            entry_count += 1
            if entry_count > MAX_FILES:
                _fail("revision_file_count_exceeded")
            kind = _path_kind(child)
            try:
                relative = child.relative_to(root).as_posix()
            except ValueError as exc:
                raise SkillRevisionError("revision_path_invalid") from exc
            _normalize_relative(relative)
            alias = _path_alias(relative)
            if alias in aliases:
                _fail("revision_path_collision")
            aliases.add(alias)
            if kind == "unsafe":
                _fail("revision_path_unsafe")
            if kind == "directory":
                if child.name != _TRANSIENT_DIRECTORY:
                    pending.append(child)
                continue
            if kind == "file" and child.suffix.casefold() == ".pyc":
                continue
            if kind != "file":
                _fail("revision_path_special" if kind == "special" else "revision_file_unreadable")
            files.append((relative, child))
            if len(files) > MAX_FILES:
                _fail("revision_file_count_exceeded")
    return sorted(files, key=lambda item: item[0])
def normalize_revision_manifest(value):
    if not isinstance(value, dict) or value.get("schema") != REVISION_SCHEMA:
        _fail("revision_manifest_invalid")
    if set(value) not in (
        {"schema", "files"},
        {"schema", "revisionId", "files", "summary"},
    ):
        _fail("revision_manifest_invalid")
    sources = value.get("files")
    if not isinstance(sources, list) or not 1 <= len(sources) <= MAX_FILES:
        _fail("revision_manifest_invalid")
    files = []
    aliases = set()
    total = 0
    for source in sources:
        if not isinstance(source, dict) or set(source) != {
            "path", "size", "digest", "contentMode",
        }:
            _fail("revision_manifest_invalid")
        path = _normalize_relative(source.get("path"))
        alias = _path_alias(path)
        if alias in aliases:
            _fail("revision_path_collision")
        aliases.add(alias)
        size = source.get("size")
        digest = source.get("digest")
        mode = source.get("contentMode")
        if (
            isinstance(size, bool) or not isinstance(size, int)
            or not 0 <= size <= MAX_FILE_BYTES
            or not isinstance(digest, str) or not _HASH_RE.fullmatch(digest)
            or mode not in {"utf8-lf", "binary"}
        ):
            _fail("revision_manifest_invalid")
        total += size
        if total > MAX_TOTAL_BYTES:
            _fail("revision_total_size_exceeded")
        files.append({"path": path, "size": size, "digest": digest, "contentMode": mode})
    files.sort(key=lambda item: item["path"])
    if "SKILL.md" not in {item["path"] for item in files}:
        _fail("revision_skill_document_missing")
    payload = {"schema": REVISION_SCHEMA, "files": files}
    revision_id = _digest(_canonical_json(payload))
    normalized = {
        "schema": REVISION_SCHEMA,
        "revisionId": revision_id,
        "files": files,
        "summary": {"fileCount": len(files), "totalSize": total},
    }
    if "revisionId" in value and value.get("revisionId") != revision_id:
        _fail("revision_id_mismatch")
    if "summary" in value and value.get("summary") != normalized["summary"]:
        _fail("revision_manifest_invalid")
    return normalized
def _read_skill_revision_once(skill_dir):
    files = []
    contents = {}
    raw_total = 0
    paths = _walk_package_files(skill_dir)
    if "SKILL.md" not in {relative for relative, _path in paths}:
        _fail("revision_skill_document_missing")
    for relative, path in paths:
        raw = _stable_file(path)
        raw_total += len(raw)
        if raw_total > MAX_TOTAL_BYTES:
            _fail("revision_total_size_exceeded")
        mode, canonical = _canonical_content(raw)
        contents[relative] = canonical
        files.append({
            "path": relative,
            "size": len(canonical),
            "digest": _digest(canonical),
            "contentMode": mode,
        })
    return normalize_revision_manifest({"schema": REVISION_SCHEMA, "files": files}), contents
def read_skill_revision(skill_dir):
    """Return one stable revision manifest and its independent canonical bytes."""
    first, contents = _read_skill_revision_once(skill_dir)
    second, repeated = _read_skill_revision_once(skill_dir)
    if first != second or contents != repeated:
        _fail("revision_changed_during_read")
    return first, contents
def build_skill_revision(skill_dir):
    return read_skill_revision(skill_dir)[0]
def normalize_bundled_catalog(value):
    if not isinstance(value, dict) or set(value) != {"schema", "skills"} or value.get("schema") != CATALOG_SCHEMA:
        _fail("catalog_invalid")
    sources = value.get("skills")
    if not isinstance(sources, list) or not 1 <= len(sources) <= MAX_SKILLS:
        _fail("catalog_invalid")
    skills = []
    ids = set()
    directories = set()
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"skillId", "directory", "revisionId"}:
            _fail("catalog_invalid")
        skill_id = source.get("skillId")
        directory = source.get("directory")
        revision_id = source.get("revisionId")
        if not isinstance(skill_id, str) or not _SKILL_ID_RE.fullmatch(skill_id):
            _fail("catalog_skill_id_invalid")
        directory = _normalize_directory(directory)
        if not isinstance(revision_id, str) or not _HASH_RE.fullmatch(revision_id):
            _fail("catalog_revision_invalid")
        directory_key = directory.casefold()
        if directory_key in directories:
            _fail("catalog_directory_duplicate")
        if skill_id in ids:
            _fail("catalog_skill_id_duplicate")
        directories.add(directory_key)
        ids.add(skill_id)
        skills.append({"skillId": skill_id, "directory": directory, "revisionId": revision_id})
    canonical = sorted(skills, key=lambda item: (item["directory"].casefold(), item["directory"]))
    if skills != canonical:
        _fail("catalog_not_canonical")
    return {"schema": CATALOG_SCHEMA, "skills": canonical}
def _bundled_directories(root):
    root = Path(root)
    if _path_kind(root) != "directory":
        _fail("catalog_root_unsafe")
    directories = []
    try:
        children = sorted(root.iterdir(), key=lambda item: (item.name.casefold(), item.name))
    except OSError as exc:
        raise SkillRevisionError("catalog_root_unreadable") from exc
    for child in children:
        kind = _path_kind(child)
        if kind == "file" and child.name == CATALOG_FILENAME:
            continue
        if kind == "unsafe":
            _fail("catalog_path_unsafe")
        if kind != "directory":
            _fail("catalog_root_entry_invalid")
        directories.append(_normalize_directory(child.name))
        if len(directories) > MAX_SKILLS:
            _fail("catalog_skill_count_exceeded")
    return directories
def build_bundled_catalog(bundled_root, assignments):
    if not isinstance(assignments, dict):
        _fail("catalog_assignment_invalid")
    directories = _bundled_directories(bundled_root)
    assigned = set(assignments)
    current = set(directories)
    if assigned - current:
        _fail("catalog_coverage_changed")
    if current - assigned:
        _fail("catalog_assignment_required")
    skills = [
        {
            "skillId": assignments[directory],
            "directory": directory,
            "revisionId": build_skill_revision(Path(bundled_root) / directory)["revisionId"],
        }
        for directory in directories
    ]
    return normalize_bundled_catalog({"schema": CATALOG_SCHEMA, "skills": skills})
def render_bundled_catalog(value):
    return _canonical_json(normalize_bundled_catalog(value)).decode("utf-8") + "\n"


def load_bundled_catalog(path):
    path = Path(path)
    if _path_kind(path) != "file":
        _fail("catalog_file_unsafe")
    try:
        raw = _stable_file(path)
        if len(raw) > MAX_CATALOG_BYTES:
            _fail("catalog_too_large")
        payload = json.loads(raw.decode("utf-8"))
    except SkillRevisionError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SkillRevisionError("catalog_unreadable") from exc
    return normalize_bundled_catalog(payload)
def _catalog_hash(catalog):
    return _digest(_canonical_json(normalize_bundled_catalog(catalog)))


def validate_bundled_catalog(bundled_root, catalog):
    catalog = normalize_bundled_catalog(catalog)
    assignments = {item["directory"]: item["skillId"] for item in catalog["skills"]}
    try:
        rebuilt = build_bundled_catalog(bundled_root, assignments)
    except SkillRevisionError as exc:
        if exc.code in {"catalog_assignment_required", "catalog_coverage_changed"}:
            raise SkillRevisionError("catalog_coverage_changed") from exc
        raise
    if rebuilt != catalog:
        _fail("catalog_stale")
    return {"ok": True, "skillCount": len(catalog["skills"]), "catalogHash": _catalog_hash(catalog)}
def _installed_observations(root):
    root = Path(root)
    kind = _path_kind(root)
    if kind == "missing":
        return "missing", {}
    if kind != "directory":
        return "unsafe", {}
    observations = {}
    aliases = {}
    try:
        children = sorted(root.iterdir(), key=lambda item: (item.name.casefold(), item.name))
    except OSError:
        return "unreadable", {}
    for child in children:
        child_kind = _path_kind(child)
        if child_kind == "file":
            continue
        try:
            directory = _normalize_directory(child.name)
        except SkillRevisionError:
            directory = "~invalid-" + hashlib.sha256(child.name.encode("utf-8", errors="replace")).hexdigest()[:16]
            observations[directory] = {"state": "invalid", "errorCode": "revision_path_invalid"}
            continue
        alias = directory.casefold()
        if alias in aliases:
            observations[aliases[alias]] = {"state": "invalid", "errorCode": "revision_path_collision"}
            observations[directory] = {"state": "invalid", "errorCode": "revision_path_collision"}
            continue
        aliases[alias] = directory
        if len(observations) >= MAX_SKILLS:
            _fail("migration_entry_count_exceeded")
        if child_kind != "directory":
            observations[directory] = {
                "state": "invalid",
                "errorCode": {"unsafe": "revision_path_unsafe", "unreadable": "revision_file_unreadable"}.get(child_kind, "revision_path_special"),
            }
            continue
        try:
            revision = build_skill_revision(child)
            observations[directory] = {"state": "ready", "revisionId": revision["revisionId"]}
        except SkillRevisionError as exc:
            observations[directory] = {"state": "invalid", "errorCode": exc.code}
    return "ready", observations
def _legacy_tombstones(installed_root):
    state_path = Path(installed_root).parent / LEGACY_STATE_FILENAME
    kind = _path_kind(state_path)
    if kind == "missing":
        return set()
    if kind != "file":
        _fail("legacy_state_invalid")
    try:
        before = _stable_file(state_path)
        state = load_bundled_skill_state(installed_root)
        if before != _stable_file(state_path) or len(state["tombstones"]) > MAX_SKILLS:
            _fail("legacy_state_invalid")
    except BundledSkillStateError as exc:
        raise SkillRevisionError("legacy_state_invalid") from exc
    return set(state["tombstones"])
def plan_legacy_migration(installed_root, bundled_root, catalog):
    catalog = normalize_bundled_catalog(catalog)
    freshness = validate_bundled_catalog(bundled_root, catalog)
    installed_root = Path(installed_root)
    bundled_root = Path(bundled_root)
    root_state, installed = _installed_observations(installed_root)
    tombstones = _legacy_tombstones(installed_root)
    repeated_state, repeated_installed = _installed_observations(installed_root)
    if (root_state, installed) != (repeated_state, repeated_installed):
        _fail("migration_source_changed")
    shared = False
    if root_state == "ready":
        try:
            shared = os.path.samefile(installed_root, bundled_root)
        except OSError:
            shared = False
    bundled = {item["directory"]: item for item in catalog["skills"]}
    entries = []
    for directory in sorted(set(bundled) | set(installed), key=lambda value: (value.casefold(), value)):
        expected = bundled.get(directory)
        observed = installed.get(directory, {"state": "missing"})
        bundled_state = "tombstoned" if directory in tombstones else "available"
        if root_state in {"unsafe", "unreadable"}:
            classification = "invalid"
        elif shared and observed.get("state") == "ready":
            classification = "shared-development"
        elif observed.get("state") == "invalid":
            classification = "invalid"
        elif expected is None:
            classification = "local-custom"
        elif observed.get("state") == "missing":
            classification = "tombstoned-bundled" if bundled_state == "tombstoned" else "bundled-missing"
        elif observed.get("revisionId") != expected["revisionId"]:
            classification = "same-name-modified"
        elif bundled_state == "tombstoned":
            classification = "tombstone-conflict"
        else:
            classification = "exact-bundled"
        entry = {
            "directory": directory,
            "classification": classification,
            "installed": observed,
        }
        if expected:
            entry.update({
                "skillId": expected["skillId"],
                "bundledRevisionId": expected["revisionId"],
                "bundledState": bundled_state,
            })
        entries.append(entry)
    root_mode = "shared-development" if shared else "separate-installed-and-bundled"
    plan = {
        "schema": MIGRATION_SCHEMA,
        "mode": "read-only",
        "catalogHash": freshness["catalogHash"],
        "rootMode": root_mode,
        "installedRootState": root_state,
        "unmatchedTombstones": sorted(tombstones - set(bundled)),
        "entries": entries,
        "summary": {
            key: sum(item["classification"] == key for item in entries)
            for key in sorted({item["classification"] for item in entries})
        },
    }
    if validate_bundled_catalog(bundled_root, catalog) != freshness:
        _fail("migration_source_changed")
    plan["planHash"] = _digest(_canonical_json(plan))
    return plan
