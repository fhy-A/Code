"""Trusted executable resources bundled with Code Skills.

This module is a clean-room Code implementation.  It resolves only resources
declared by the current Code bundle and never searches parent directories,
user profiles, or the wider filesystem.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath

from .bundled_skills import BundledSkillStateError, load_bundled_skill_state


RESOURCE_MANIFEST_NAME = "code-resources.json"
RESOURCE_SCHEMA_VERSION = 1
MAX_RESOURCE_MANIFEST_BYTES = 128 * 1024
MAX_EXECUTABLE_RESOURCE_BYTES = 2 * 1024 * 1024
REQUIRED_RESOURCE_CONTRACTS = frozenset({"xlsx"})

_SAFE_SKILL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SAFE_RESOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SAFE_PROTOCOL = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RESOURCE_KINDS = {"python", "python-library"}

_PUBLIC_ERRORS = {
    "resource_contract_missing": "The installed Skill's trusted resource contract is unavailable.",
    "resource_contract_invalid": "The installed Skill's trusted resource contract is invalid.",
    "skill_state_invalid": "The bundled Skill deletion state is invalid; resource access is blocked.",
    "skill_tombstoned": "The bundled Skill was removed by the user; its resources remain disabled.",
    "skill_not_installed": "The Skill is not installed.",
    "installed_skill_identity_unknown": "The installed Skill differs from supported Code copies; trusted executable resources were not attached.",
    "installed_resource_conflict": "An installed resource conflicts with the Code-owned copy and was preserved unchanged.",
    "bundled_resource_missing": "A required Code-owned Skill resource is missing from this installation.",
    "bundled_resource_hash_mismatch": "A required Code-owned Skill resource failed integrity verification.",
    "resource_path_unsafe": "A Skill resource path is not a regular, contained file.",
}


class SkillResourceError(ValueError):
    """Stable, public-safe failure while resolving a trusted Skill resource."""

    def __init__(self, error_code):
        self.error_code = str(error_code or "resource_contract_invalid")
        super().__init__(_PUBLIC_ERRORS.get(self.error_code, _PUBLIC_ERRORS["resource_contract_invalid"]))


def _sha256_file(path):
    # Git may materialize these text resources with CRLF on Windows.  The
    # contract hashes canonical LF bytes so checkout policy cannot invalidate
    # an otherwise identical Code-owned script or installed Skill identity.
    payload = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(payload).hexdigest()


def _is_link_or_reparse(path):
    """Reject symlinks and Windows reparse points without resolving them."""
    try:
        metadata = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(metadata.st_mode):
        return True
    attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400) or 0x400)
    return bool(attributes & reparse_flag)


def _contained_regular_file(root, relative_path, *, missing_code, mismatch_code=""):
    root = Path(root)
    if not root.is_dir() or _is_link_or_reparse(root):
        raise SkillResourceError("resource_path_unsafe")
    candidate = root.joinpath(*relative_path.parts)
    current = root
    for part in relative_path.parts:
        current = current / part
        if _is_link_or_reparse(current):
            raise SkillResourceError("resource_path_unsafe")
    if not candidate.is_file():
        raise SkillResourceError(missing_code)
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError):
        raise SkillResourceError("resource_path_unsafe")
    try:
        if candidate.stat().st_size > MAX_EXECUTABLE_RESOURCE_BYTES:
            raise SkillResourceError(mismatch_code or "resource_path_unsafe")
    except OSError:
        raise SkillResourceError("resource_path_unsafe")
    return candidate


def _normalized_hash_list(value, field):
    if not isinstance(value, list) or not value:
        raise SkillResourceError("resource_contract_invalid")
    normalized = []
    for item in value:
        item = str(item or "").lower()
        if not _SHA256.fullmatch(item) or item in normalized:
            raise SkillResourceError("resource_contract_invalid")
        normalized.append(item)
    return tuple(normalized)


def _normalized_relative_path(value):
    raw = str(value or "").replace("\\", "/")
    path = PurePosixPath(raw)
    if (
        not raw
        or raw.startswith("/")
        or path.is_absolute()
        or any(
            part in {"", ".", "..", "__pycache__"}
            or part.startswith(".")
            or ":" in part
            for part in path.parts
        )
    ):
        raise SkillResourceError("resource_contract_invalid")
    return path


def _load_resource_contract(skill_name, bundled_skill_dir):
    bundled_skill_dir = Path(bundled_skill_dir)
    manifest_path = bundled_skill_dir / RESOURCE_MANIFEST_NAME
    if not manifest_path.exists():
        if skill_name in REQUIRED_RESOURCE_CONTRACTS:
            raise SkillResourceError("resource_contract_missing")
        return None
    manifest_relative = PurePosixPath(RESOURCE_MANIFEST_NAME)
    manifest_path = _contained_regular_file(
        bundled_skill_dir,
        manifest_relative,
        missing_code="resource_contract_missing",
    )
    try:
        if manifest_path.stat().st_size > MAX_RESOURCE_MANIFEST_BYTES:
            raise SkillResourceError("resource_contract_invalid")
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except SkillResourceError:
        raise
    except Exception:
        raise SkillResourceError("resource_contract_invalid")
    if (
        not isinstance(payload, dict)
        or payload.get("schemaVersion") != RESOURCE_SCHEMA_VERSION
        or payload.get("skill") != skill_name
    ):
        raise SkillResourceError("resource_contract_invalid")
    compatible = payload.get("compatibleInstalled")
    if not isinstance(compatible, dict):
        raise SkillResourceError("resource_contract_invalid")
    skill_hashes = _normalized_hash_list(compatible.get("skillMdSha256"), "skillMdSha256")
    dependency_hashes = _normalized_hash_list(
        compatible.get("dependenciesSha256"), "dependenciesSha256",
    )
    raw_resources = payload.get("resources")
    if not isinstance(raw_resources, list) or not raw_resources:
        raise SkillResourceError("resource_contract_invalid")
    resources = []
    seen_ids = set()
    seen_paths = set()
    visible_count = 0
    for raw in raw_resources:
        if not isinstance(raw, dict):
            raise SkillResourceError("resource_contract_invalid")
        resource_id = str(raw.get("id") or "")
        relative = _normalized_relative_path(raw.get("path"))
        sha256 = str(raw.get("sha256") or "").lower()
        kind = str(raw.get("kind") or "")
        protocol = str(raw.get("protocol") or "")
        visible = raw.get("modelVisible") is True
        arguments = raw.get("arguments")
        if (
            not _SAFE_RESOURCE_ID.fullmatch(resource_id)
            or resource_id in seen_ids
            or relative.as_posix() in seen_paths
            or not _SHA256.fullmatch(sha256)
            or kind not in _RESOURCE_KINDS
            or not _SAFE_PROTOCOL.fullmatch(protocol)
            or not isinstance(arguments, list)
            or len(arguments) > 16
            or any(not isinstance(item, str) or len(item) > 256 for item in arguments)
        ):
            raise SkillResourceError("resource_contract_invalid")
        seen_ids.add(resource_id)
        seen_paths.add(relative.as_posix())
        visible_count += int(visible)
        resources.append({
            "id": resource_id,
            "relative": relative,
            "sha256": sha256,
            "kind": kind,
            "protocol": protocol,
            "modelVisible": visible,
            "arguments": list(arguments),
        })
    if visible_count < 1:
        raise SkillResourceError("resource_contract_invalid")
    return {
        "skillHashes": skill_hashes,
        "dependencyHashes": dependency_hashes,
        "resources": resources,
    }


def _validate_installed_identity(skill_name, installed_skills_dir, contract):
    installed_skills_dir = Path(installed_skills_dir)
    try:
        state = load_bundled_skill_state(installed_skills_dir)
    except BundledSkillStateError:
        raise SkillResourceError("skill_state_invalid")
    if skill_name in set(state.get("tombstones") or []):
        raise SkillResourceError("skill_tombstoned")
    installed_skill_dir = installed_skills_dir / skill_name
    if not installed_skill_dir.is_dir():
        raise SkillResourceError("skill_not_installed")
    skill_md = _contained_regular_file(
        installed_skill_dir,
        PurePosixPath("SKILL.md"),
        missing_code="installed_skill_identity_unknown",
    )
    dependencies = _contained_regular_file(
        installed_skill_dir,
        PurePosixPath("dependencies.json"),
        missing_code="installed_skill_identity_unknown",
    )
    if (
        _sha256_file(skill_md) not in contract["skillHashes"]
        or _sha256_file(dependencies) not in contract["dependencyHashes"]
    ):
        raise SkillResourceError("installed_skill_identity_unknown")
    return installed_skill_dir


def preferred_bundled_dependency_manifest(skill_dir, bundled_skills_dir):
    """Return the current bundled manifest for a verified legacy installation.

    This is a read-only compatibility adapter: the installed manifest remains
    byte-for-byte untouched, while dependency checks can use the current Code
    capability contract.  Skills without a resource contract keep legacy
    local-first behavior.
    """
    skill_dir = Path(skill_dir)
    skill_name = skill_dir.name
    bundled_skill_dir = Path(bundled_skills_dir) / skill_name
    contract = _load_resource_contract(skill_name, bundled_skill_dir)
    if contract is None:
        return None
    installed_skill_dir = _validate_installed_identity(
        skill_name,
        skill_dir.parent,
        contract,
    )
    bundled_skill_md = _contained_regular_file(
        bundled_skill_dir,
        PurePosixPath("SKILL.md"),
        missing_code="resource_contract_invalid",
    )
    bundled_dependencies = _contained_regular_file(
        bundled_skill_dir,
        PurePosixPath("dependencies.json"),
        missing_code="resource_contract_invalid",
    )
    if (
        _sha256_file(bundled_skill_md) not in contract["skillHashes"]
        or _sha256_file(bundled_dependencies) not in contract["dependencyHashes"]
    ):
        raise SkillResourceError("resource_contract_invalid")
    installed_dependencies = installed_skill_dir / "dependencies.json"
    if _sha256_file(installed_dependencies) == _sha256_file(bundled_dependencies):
        return None
    return bundled_dependencies


def resolve_skill_resources(skill_name, installed_skills_dir, bundled_skills_dir):
    """Resolve model-visible Code-owned resources for one installed Skill.

    Existing installations are never changed.  A complete exact installed
    resource set is used in place; otherwise the current verified bundle is a
    read-only fallback.  Any conflicting installed file fails closed.
    """
    skill_name = str(skill_name or "")
    if not _SAFE_SKILL_NAME.fullmatch(skill_name):
        raise SkillResourceError("resource_contract_invalid")
    bundled_skill_dir = Path(bundled_skills_dir) / skill_name
    contract = _load_resource_contract(skill_name, bundled_skill_dir)
    if contract is None:
        return None
    installed_skill_dir = _validate_installed_identity(
        skill_name,
        installed_skills_dir,
        contract,
    )

    bundled_manifest_path = _contained_regular_file(
        bundled_skill_dir,
        PurePosixPath(RESOURCE_MANIFEST_NAME),
        missing_code="resource_contract_missing",
    )
    installed_manifest_path = installed_skill_dir / RESOURCE_MANIFEST_NAME
    if os.path.lexists(installed_manifest_path):
        try:
            safe_installed_manifest = _contained_regular_file(
                installed_skill_dir,
                PurePosixPath(RESOURCE_MANIFEST_NAME),
                missing_code="installed_resource_conflict",
            )
        except SkillResourceError:
            raise SkillResourceError("installed_resource_conflict")
        if _sha256_file(safe_installed_manifest) != _sha256_file(bundled_manifest_path):
            raise SkillResourceError("installed_resource_conflict")

    bundled_paths = {}
    for resource in contract["resources"]:
        path = _contained_regular_file(
            bundled_skill_dir,
            resource["relative"],
            missing_code="bundled_resource_missing",
            mismatch_code="bundled_resource_hash_mismatch",
        )
        if _sha256_file(path) != resource["sha256"]:
            raise SkillResourceError("bundled_resource_hash_mismatch")
        bundled_paths[resource["id"]] = path

    installed_paths = {}
    installed_missing = False
    for resource in contract["resources"]:
        path = installed_skill_dir.joinpath(*resource["relative"].parts)
        if not os.path.lexists(path):
            installed_missing = True
            continue
        try:
            safe_path = _contained_regular_file(
                installed_skill_dir,
                resource["relative"],
                missing_code="installed_resource_conflict",
            )
        except SkillResourceError:
            raise SkillResourceError("installed_resource_conflict")
        if _sha256_file(safe_path) != resource["sha256"]:
            raise SkillResourceError("installed_resource_conflict")
        installed_paths[resource["id"]] = safe_path

    use_installed = not installed_missing and len(installed_paths) == len(contract["resources"])
    source_paths = installed_paths if use_installed else bundled_paths
    public_resources = []
    for resource in contract["resources"]:
        if not resource["modelVisible"]:
            continue
        public_resources.append({
            "id": resource["id"],
            "kind": resource["kind"],
            "protocol": resource["protocol"],
            "path": str(source_paths[resource["id"]].resolve(strict=True)),
            "sha256": resource["sha256"],
            "arguments": list(resource["arguments"]),
        })
    return {
        "schemaVersion": RESOURCE_SCHEMA_VERSION,
        "source": "installed" if use_installed else "bundled-fallback",
        "resources": public_resources,
        "instructions": (
            "Use only the exact resource path returned here with the Python runtime selected by "
            "check_skill_dependencies. Do not search parent folders, adjacent repositories, the "
            "user profile, or disk roots, and do not copy the resource into the project."
        ),
    }
