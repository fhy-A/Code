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
REQUIRED_RESOURCE_CONTRACTS = frozenset({"pptx", "xlsx"})

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
    "custom_resource_contract_missing": "The custom Skill did not publish a trusted local resource contract.",
    "custom_resource_contract_invalid": "The custom Skill local resource contract is invalid.",
    "custom_resource_missing": "A declared custom Skill resource is missing.",
    "custom_resource_hash_mismatch": "A declared custom Skill resource failed integrity verification.",
    "custom_resource_path_unsafe": "A declared custom Skill resource path is not a regular, contained file.",
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
    if _is_link_or_reparse(root) or not root.is_dir():
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


def _normalized_hash_list(value, field, error_code="resource_contract_invalid"):
    if not isinstance(value, list) or not value:
        raise SkillResourceError(error_code)
    normalized = []
    for item in value:
        item = str(item or "").lower()
        if not _SHA256.fullmatch(item) or item in normalized:
            raise SkillResourceError(error_code)
        normalized.append(item)
    return tuple(normalized)


def _normalized_relative_path(value, error_code="resource_contract_invalid"):
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
        raise SkillResourceError(error_code)
    return path


def _load_resource_contract(skill_name, skill_dir, *, custom=False):
    """Read one bounded resource contract without discovering filesystem paths.

    Bundled contracts certify known Code copies and can provide a read-only
    compatibility fallback.  Custom contracts deliberately omit that identity
    list: their helpers live with the active custom Skill and never inherit a
    bundled fallback, even when names collide.
    """
    skill_dir = Path(skill_dir)
    missing_code = "custom_resource_contract_missing" if custom else "resource_contract_missing"
    invalid_code = "custom_resource_contract_invalid" if custom else "resource_contract_invalid"
    manifest_path = skill_dir / RESOURCE_MANIFEST_NAME
    if not os.path.lexists(manifest_path):
        if not custom and skill_name in REQUIRED_RESOURCE_CONTRACTS:
            raise SkillResourceError(missing_code)
        return None
    manifest_relative = PurePosixPath(RESOURCE_MANIFEST_NAME)
    try:
        manifest_path = _contained_regular_file(
            skill_dir,
            manifest_relative,
            missing_code=missing_code,
        )
    except SkillResourceError as exc:
        if custom:
            raise SkillResourceError(invalid_code) from exc
        raise
    try:
        if manifest_path.stat().st_size > MAX_RESOURCE_MANIFEST_BYTES:
            raise SkillResourceError(invalid_code)
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except SkillResourceError:
        raise
    except Exception:
        raise SkillResourceError(invalid_code)
    if (
        not isinstance(payload, dict)
        or payload.get("schemaVersion") != RESOURCE_SCHEMA_VERSION
        or payload.get("skill") != skill_name
    ):
        raise SkillResourceError(invalid_code)
    if custom:
        if "compatibleInstalled" in payload:
            raise SkillResourceError(invalid_code)
        skill_hashes = ()
        dependency_hashes = ()
    else:
        compatible = payload.get("compatibleInstalled")
        if not isinstance(compatible, dict):
            raise SkillResourceError(invalid_code)
        skill_hashes = _normalized_hash_list(
            compatible.get("skillMdSha256"), "skillMdSha256", invalid_code,
        )
        dependency_hashes = _normalized_hash_list(
            compatible.get("dependenciesSha256"), "dependenciesSha256", invalid_code,
        )
    raw_resources = payload.get("resources")
    if not isinstance(raw_resources, list) or not raw_resources:
        raise SkillResourceError(invalid_code)
    resources = []
    seen_ids = set()
    seen_paths = set()
    visible_count = 0
    for raw in raw_resources:
        if not isinstance(raw, dict):
            raise SkillResourceError(invalid_code)
        resource_id = str(raw.get("id") or "")
        relative = _normalized_relative_path(raw.get("path"), invalid_code)
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
            raise SkillResourceError(invalid_code)
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
        raise SkillResourceError(invalid_code)
    return {
        "skillHashes": skill_hashes,
        "dependencyHashes": dependency_hashes,
        "resources": resources,
        "custom": custom,
    }


def _validate_installed_identity(skill_name, installed_skills_dir, contract):
    installed_skills_dir = Path(installed_skills_dir)
    if _is_link_or_reparse(installed_skills_dir) or not installed_skills_dir.is_dir():
        raise SkillResourceError("resource_path_unsafe")
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


def _active_skill_dir(skill_name, installed_skills_dir):
    """Return the active Skill folder only when it is a contained regular tree."""
    installed_skills_dir = Path(installed_skills_dir)
    if _is_link_or_reparse(installed_skills_dir) or not installed_skills_dir.is_dir():
        raise SkillResourceError("resource_path_unsafe")
    skill_dir = installed_skills_dir / skill_name
    if _is_link_or_reparse(skill_dir) or not skill_dir.is_dir():
        raise SkillResourceError("skill_not_installed")
    _contained_regular_file(
        skill_dir,
        PurePosixPath("SKILL.md"),
        missing_code="skill_not_installed",
    )
    return skill_dir


def _same_regular_skills_root(installed_skills_dir, bundled_skills_dir):
    """Tell whether a source/dev active root is physically the bundled root."""
    installed_skills_dir = Path(installed_skills_dir)
    bundled_skills_dir = Path(bundled_skills_dir)
    if (
        _is_link_or_reparse(installed_skills_dir)
        or _is_link_or_reparse(bundled_skills_dir)
        or not installed_skills_dir.is_dir()
        or not bundled_skills_dir.is_dir()
    ):
        return False
    try:
        return os.path.samefile(installed_skills_dir, bundled_skills_dir)
    except OSError:
        return False


def _same_root_custom_contract(skill_name, installed_skills_dir, bundled_skills_dir):
    """Load an explicit custom contract only from a shared source/dev root.

    Code-owned resource Skills reserve their identity manifests.  A missing or
    malformed identity contract for one of those names remains a bundled
    integrity failure, never an inferred custom Skill.
    """
    if (
        skill_name in REQUIRED_RESOURCE_CONTRACTS
        or not _same_regular_skills_root(installed_skills_dir, bundled_skills_dir)
    ):
        return None
    installed_skill_dir = _active_skill_dir(skill_name, installed_skills_dir)
    if not os.path.lexists(installed_skill_dir / RESOURCE_MANIFEST_NAME):
        return None
    return _load_resource_contract(skill_name, installed_skill_dir, custom=True)


def _public_runtime_resources(contract, source, source_paths):
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
        "source": source,
        "resources": public_resources,
        "instructions": (
            "Use only the exact resource path returned here with the runtime selected by "
            "check_skill_dependencies. Do not search parent folders, adjacent repositories, the "
            "user profile, or disk roots, and do not copy the resource into the project."
        ),
    }


def _resolve_custom_resources(skill_name, installed_skills_dir):
    """Resolve explicit user-authored helpers from the active Skill folder only."""
    installed_skill_dir = _active_skill_dir(skill_name, installed_skills_dir)
    contract = _load_resource_contract(skill_name, installed_skill_dir, custom=True)
    if contract is None:
        return None
    source_paths = {}
    for resource in contract["resources"]:
        try:
            path = _contained_regular_file(
                installed_skill_dir,
                resource["relative"],
                missing_code="custom_resource_missing",
                mismatch_code="custom_resource_hash_mismatch",
            )
        except SkillResourceError as exc:
            if exc.error_code == "resource_path_unsafe":
                raise SkillResourceError("custom_resource_path_unsafe") from exc
            raise
        if _sha256_file(path) != resource["sha256"]:
            raise SkillResourceError("custom_resource_hash_mismatch")
        source_paths[resource["id"]] = path
    return _public_runtime_resources(contract, "custom", source_paths)


def _no_custom_resource_guidance():
    """Return a stable fail-closed result when a custom Skill has no contract."""
    return {
        "schemaVersion": RESOURCE_SCHEMA_VERSION,
        "source": "custom-no-resources",
        "resources": [],
        "instructions": (
            "No trusted local helper resources were published for this custom Skill. Do not "
            "search for or infer helper paths from parent folders, adjacent repositories, the "
            "user profile, or disk roots. Report a missing resource contract if a helper is required."
        ),
    }


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
    try:
        contract = _load_resource_contract(skill_name, bundled_skill_dir)
    except SkillResourceError as exc:
        if exc.error_code == "resource_contract_invalid":
            custom_contract = _same_root_custom_contract(
                skill_name,
                skill_dir.parent,
                bundled_skills_dir,
            )
            if custom_contract is not None:
                return None
        raise
    if contract is None:
        return None
    try:
        installed_skill_dir = _validate_installed_identity(
            skill_name,
            skill_dir.parent,
            contract,
        )
    except SkillResourceError as exc:
        if _same_regular_skills_root(skill_dir.parent, bundled_skills_dir):
            raise
        # A same-name custom Skill with its own explicit resource contract is
        # not a legacy bundled copy.  Keep its local dependency manifest and
        # let resolve_skill_resources validate the custom resource contract;
        # never project the bundled dependency fallback into that Skill.
        if (
            exc.error_code in {"installed_skill_identity_unknown", "skill_tombstoned"}
            and os.path.lexists(skill_dir / RESOURCE_MANIFEST_NAME)
        ):
            return None
        raise
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


def _resolve_bundled_resources(skill_name, installed_skills_dir, bundled_skills_dir, contract):
    """Resolve a verified bundled Skill with its legacy read-only fallback."""
    bundled_skill_dir = Path(bundled_skills_dir) / skill_name
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
        except SkillResourceError as exc:
            raise SkillResourceError("installed_resource_conflict") from exc
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
        except SkillResourceError as exc:
            raise SkillResourceError("installed_resource_conflict") from exc
        if _sha256_file(safe_path) != resource["sha256"]:
            raise SkillResourceError("installed_resource_conflict")
        installed_paths[resource["id"]] = safe_path

    use_installed = not installed_missing and len(installed_paths) == len(contract["resources"])
    return _public_runtime_resources(
        contract,
        "installed" if use_installed else "bundled-fallback",
        installed_paths if use_installed else bundled_paths,
    )


def resolve_skill_resources(skill_name, installed_skills_dir, bundled_skills_dir):
    """Resolve one active Skill's explicit helper contract without path discovery.

    A known bundled identity retains compatibility/tombstone semantics.  An
    active custom Skill may instead opt in through its own complete manifest;
    that path is never mixed with, or repaired from, a bundled Skill of the
    same name.  An uncontracted custom Skill keeps existing no-resource
    behavior rather than receiving guessed helper paths.
    """
    skill_name = str(skill_name or "")
    if not _SAFE_SKILL_NAME.fullmatch(skill_name):
        raise SkillResourceError("resource_contract_invalid")
    bundled_skill_dir = Path(bundled_skills_dir) / skill_name
    installed_skill_dir = _active_skill_dir(skill_name, installed_skills_dir)
    installed_manifest_exists = os.path.lexists(installed_skill_dir / RESOURCE_MANIFEST_NAME)
    try:
        bundled_contract = _load_resource_contract(skill_name, bundled_skill_dir)
    except SkillResourceError as exc:
        if exc.error_code == "resource_contract_invalid":
            custom_contract = _same_root_custom_contract(
                skill_name,
                installed_skills_dir,
                bundled_skills_dir,
            )
            if custom_contract is not None:
                return _resolve_custom_resources(skill_name, installed_skills_dir)
        raise
    if bundled_contract is None:
        if installed_manifest_exists:
            return _resolve_custom_resources(skill_name, installed_skills_dir)
        if not bundled_skill_dir.is_dir():
            return _no_custom_resource_guidance()
        return None
    try:
        return _resolve_bundled_resources(
            skill_name,
            installed_skills_dir,
            bundled_skills_dir,
            bundled_contract,
        )
    except SkillResourceError as exc:
        if exc.error_code not in {"installed_skill_identity_unknown", "skill_tombstoned"}:
            raise
        if _same_regular_skills_root(installed_skills_dir, bundled_skills_dir):
            raise
        if not installed_manifest_exists:
            raise
        return _resolve_custom_resources(skill_name, installed_skills_dir)


def audit_bundled_skill_resources(bundled_skills_dir):
    """Audit only explicit bundled resource contracts under one Code bundle.

    The audit intentionally ignores prose, Markdown examples, and user Skill
    folders.  A runnable local helper is a `code-resources.json` entry, so a
    missing declared file is actionable while a documentation example is not.
    """
    bundled_skills_dir = Path(bundled_skills_dir)
    result = {
        "schemaVersion": RESOURCE_SCHEMA_VERSION,
        "checkedSkills": [],
        "contracts": [],
        "findings": [],
    }
    if _is_link_or_reparse(bundled_skills_dir) or not bundled_skills_dir.is_dir():
        result["findings"].append({"skill": "", "errorCode": "resource_path_unsafe"})
        result["ok"] = False
        return result
    try:
        entries = tuple(sorted(bundled_skills_dir.iterdir(), key=lambda path: path.name.casefold()))
    except OSError:
        result["findings"].append({"skill": "", "errorCode": "resource_path_unsafe"})
        result["ok"] = False
        return result
    for skill_dir in entries:
        skill_name = skill_dir.name
        if not _SAFE_SKILL_NAME.fullmatch(skill_name):
            continue
        if _is_link_or_reparse(skill_dir):
            result["findings"].append({"skill": skill_name, "errorCode": "resource_path_unsafe"})
            continue
        if not skill_dir.is_dir():
            continue
        result["checkedSkills"].append(skill_name)
        has_contract = os.path.lexists(skill_dir / RESOURCE_MANIFEST_NAME)
        if not has_contract and skill_name not in REQUIRED_RESOURCE_CONTRACTS:
            continue
        try:
            contract = _load_resource_contract(skill_name, skill_dir)
        except SkillResourceError as exc:
            result["findings"].append({"skill": skill_name, "errorCode": exc.error_code})
            continue
        if contract is None:
            continue
        result["contracts"].append(skill_name)
        for resource in contract["resources"]:
            try:
                path = _contained_regular_file(
                    skill_dir,
                    resource["relative"],
                    missing_code="bundled_resource_missing",
                    mismatch_code="bundled_resource_hash_mismatch",
                )
                if _sha256_file(path) != resource["sha256"]:
                    raise SkillResourceError("bundled_resource_hash_mismatch")
            except SkillResourceError as exc:
                result["findings"].append({
                    "skill": skill_name,
                    "resource": resource["id"],
                    "errorCode": exc.error_code,
                })
    result["ok"] = not result["findings"]
    return result
