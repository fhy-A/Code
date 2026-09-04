"""Read-only Skill descriptors, registry snapshots, and shadow resolution.

This module is deliberately isolated from the production Skill activation path.
It never mutates Skill packages and its resolver returns diagnostics only; callers
must not use the result to construct prompts, permissions, AgentRuns, dependency
bindings, resource receipts, or evidence gates.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Iterable

import yaml
from yaml.constructor import ConstructorError
from yaml.resolver import BaseResolver
from yaml.tokens import AliasToken, AnchorToken

from code_runtime.bundled_skills import (
    BundledSkillStateError,
    load_bundled_skill_state,
)


DESCRIPTOR_SCHEMA = "code-skill-descriptor/v1"
REGISTRY_SCHEMA = "code-skill-registry-snapshot/v1"
RESOLUTION_SCHEMA = "code-skill-shadow-resolution/v2"
COMPARISON_SCHEMA = "code-skill-shadow-comparison/v1"

MAX_SKILL_BYTES = 512 * 1024
MAX_SIDECAR_BYTES = 256 * 1024
MAX_YAML_ITEMS = 4096
MAX_YAML_DEPTH = 24
MAX_MESSAGE_CHARS = 20_000

SIDECARS = (
    ("dependencies", "dependencies.json"),
    ("resources", "code-resources.json"),
    ("evidence", "evidence.json"),
)
STANDARD_FRONTMATTER_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}
CODE_LEGACY_FRONTMATTER_FIELDS = {
    # Code v0 adapters. They remain observable metadata and never grant
    # permission-profile capabilities.
    "keywords",
    "tools",
    "version",
}
KNOWN_FRONTMATTER_FIELDS = STANDARD_FRONTMATTER_FIELDS | CODE_LEGACY_FRONTMATTER_FIELDS
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SAFE_DIRECTORY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
STANDARD_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

EXPLICIT_ONLY_SKILLS = frozenset({
    "dispatching-parallel-agents",
    "subagent-driven-development",
    "executing-plans",
    "writing-plans",
})
OFFICE_SPECIALISTS = frozenset({"docx", "pdf", "pptx", "xlsx"})
OFFICE_ROUTE_NAMES = OFFICE_SPECIALISTS | {"office-files"}


class SkillRegistryError(ValueError):
    """Stable parser or registry failure without exposing local paths."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code)


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects ambiguous duplicate mapping keys."""


def _construct_unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "frontmatter keys must be strings",
                key_node.start_mark,
            )
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate frontmatter key: {key}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_hash(value) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _diagnostic(code: str, severity: str = "error", **fields) -> dict:
    result = {"code": str(code), "severity": str(severity)}
    for key in sorted(fields):
        value = fields[key]
        if value not in (None, "", [], {}):
            result[key] = value
    return result


def _sort_diagnostics(items: Iterable[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda item: (
            str(item.get("code") or ""),
            str(item.get("severity") or ""),
            json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        ),
    )


def _normalize_yaml_value(value, *, depth=0, counter=None):
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > MAX_YAML_ITEMS or depth > MAX_YAML_DEPTH:
        raise SkillRegistryError("frontmatter_too_complex", "Skill frontmatter is too complex")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SkillRegistryError("frontmatter_value_invalid", "Skill frontmatter contains a non-finite number")
        return value
    if isinstance(value, list):
        return [
            _normalize_yaml_value(item, depth=depth + 1, counter=counter)
            for item in value
        ]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise SkillRegistryError("frontmatter_key_invalid", "Skill frontmatter keys must be strings")
        normalized = {}
        for key in sorted(value):
            normalized[key] = _normalize_yaml_value(
                value[key], depth=depth + 1, counter=counter,
            )
        return normalized
    raise SkillRegistryError(
        "frontmatter_value_unsupported",
        f"Unsupported Skill frontmatter value: {type(value).__name__}",
    )


def _normalize_terms(value, *, kind: str) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        values = re.split(r"[,\n]", value)
    elif isinstance(value, list):
        values = value
    else:
        raise SkillRegistryError(
            f"{kind}_invalid",
            f"Skill {kind} must be a string or list",
        )
    normalized = []
    for item in values:
        if not isinstance(item, str):
            raise SkillRegistryError(
                f"{kind}_invalid",
                f"Skill {kind} entries must be strings",
            )
        text = item.strip()
        if not text or text in normalized:
            continue
        if len(text) > 240:
            raise SkillRegistryError(f"{kind}_invalid", f"Skill {kind} entry is too long")
        if kind == "allowed_tools" and any(ord(character) < 0x20 for character in text):
            raise SkillRegistryError("allowed_tools_invalid", "Skill allowed-tools entry is invalid")
        normalized.append(text)
        if len(normalized) > 128:
            raise SkillRegistryError(f"{kind}_invalid", f"Skill {kind} has too many entries")
    return normalized


def _normalize_allowed_tools(value) -> tuple[str, list[str], str, bool]:
    """Preserve official tokens while recognizing Code's legacy shapes."""
    if value in (None, ""):
        return "", [], "none", value is None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return "", [], "standard-space-string", False
        if "," in raw:
            tokens = _normalize_terms(raw, kind="allowed_tools")
            return raw, tokens, "legacy-comma-string", False
        tokens = raw.split()
        source = "standard-space-string"
        standard = True
    elif isinstance(value, list):
        raw = ""
        tokens = _normalize_terms(value, kind="allowed_tools")
        source = "legacy-yaml-list"
        standard = False
    else:
        raise SkillRegistryError(
            "allowed_tools_invalid",
            "Skill allowed-tools must be a string or legacy list",
        )
    if not tokens or len(tokens) > 128:
        raise SkillRegistryError("allowed_tools_invalid", "Skill allowed-tools is invalid")
    for token in tokens:
        if len(token) > 240 or any(ord(character) < 0x21 for character in token):
            raise SkillRegistryError("allowed_tools_invalid", "Skill allowed-tools token is invalid")
    return raw, tokens, source, standard


def _standard_format_reasons(
    meta: dict,
    *,
    directory: str,
    name: str,
    description: str,
    metadata,
    allowed_tools_standard: bool,
) -> list[str]:
    reasons = []
    if (
        len(name) > 64
        or not STANDARD_NAME_RE.fullmatch(name)
    ):
        reasons.append("standard_name_invalid")
    if name != directory:
        reasons.append("standard_name_directory_mismatch")
    if not 1 <= len(description) <= 1024:
        reasons.append("standard_description_invalid")
    if "license" in meta and (
        not isinstance(meta.get("license"), str)
        or not str(meta.get("license") or "").strip()
    ):
        reasons.append("standard_license_invalid")
    if "compatibility" in meta and (
        not isinstance(meta.get("compatibility"), str)
        or not 1 <= len(str(meta.get("compatibility") or "")) <= 500
    ):
        reasons.append("standard_compatibility_invalid")
    if "metadata" in meta and (
        not isinstance(metadata, dict)
        or any(not isinstance(value, str) for value in metadata.values())
    ):
        reasons.append("standard_metadata_invalid")
    if "allowed-tools" in meta and not allowed_tools_standard:
        reasons.append("standard_allowed_tools_invalid")
    if set(meta) & CODE_LEGACY_FRONTMATTER_FIELDS:
        reasons.append("code_legacy_top_level_fields")
    if set(meta) - KNOWN_FRONTMATTER_FIELDS:
        reasons.append("standard_unknown_top_level_fields")
    return sorted(set(reasons))


def parse_skill_document(text: str) -> dict:
    """Parse one SKILL.md using real, safe YAML without Memory semantics."""
    if not isinstance(text, str):
        raise SkillRegistryError("skill_text_invalid", "Skill document must be text")
    document = text.lstrip("\ufeff")
    if len(document.encode("utf-8")) > MAX_SKILL_BYTES:
        raise SkillRegistryError("skill_too_large", "Skill document is too large")
    lines = document.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise SkillRegistryError("frontmatter_missing", "Skill frontmatter is missing")
    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() in {"---", "..."}:
            closing = index
            break
    if closing is None:
        raise SkillRegistryError("frontmatter_unterminated", "Skill frontmatter is unterminated")
    raw_yaml = "".join(lines[1:closing])
    try:
        for token in yaml.scan(raw_yaml, Loader=yaml.SafeLoader):
            if isinstance(token, (AliasToken, AnchorToken)):
                raise SkillRegistryError(
                    "frontmatter_alias_unsupported",
                    "Skill frontmatter anchors and aliases are not supported",
                )
        raw_meta = yaml.load(raw_yaml, Loader=_UniqueKeySafeLoader)
    except SkillRegistryError:
        raise
    except yaml.YAMLError as exc:
        raise SkillRegistryError("frontmatter_yaml_invalid", "Skill frontmatter YAML is invalid") from exc
    if raw_meta is None:
        raw_meta = {}
    if not isinstance(raw_meta, dict):
        raise SkillRegistryError("frontmatter_not_mapping", "Skill frontmatter must be a mapping")
    meta = _normalize_yaml_value(raw_meta)
    body = "".join(lines[closing + 1:]).strip()
    return {"meta": meta, "body": body}


def _is_link_or_reparse(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(metadata.st_mode):
        return True
    attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400) or 0x400)
    return bool(attributes & reparse_flag)


def _read_skill_bytes(path: Path) -> bytes:
    if _is_link_or_reparse(path):
        raise SkillRegistryError("skill_file_unsafe", "Skill document is not a regular file")
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode):
        raise SkillRegistryError("skill_file_unsafe", "Skill document is not a regular file")
    if metadata.st_size > MAX_SKILL_BYTES:
        raise SkillRegistryError("skill_too_large", "Skill document is too large")
    return path.read_bytes()


def _read_sidecar_summary(path: Path, expected_name: str) -> tuple[dict, list[dict]]:
    if _is_link_or_reparse(path):
        return {"state": "invalid"}, [
            _diagnostic("sidecar_unsafe", sidecar=path.name)
        ]
    if not path.exists():
        return {"state": "missing"}, []
    try:
        metadata = os.lstat(path)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_SIDECAR_BYTES:
            raise SkillRegistryError("sidecar_invalid", "Skill sidecar is not a bounded regular file")
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError) as exc:
        return {"state": "unreadable", "errorType": type(exc).__name__}, [
            _diagnostic("sidecar_unreadable", sidecar=path.name, errorType=type(exc).__name__)
        ]
    except (json.JSONDecodeError, SkillRegistryError) as exc:
        return {"state": "invalid", "errorType": type(exc).__name__}, [
            _diagnostic("sidecar_invalid", sidecar=path.name, errorType=type(exc).__name__)
        ]
    if not isinstance(payload, dict):
        return {"state": "invalid", "contentHash": _sha256_bytes(raw)}, [
            _diagnostic("sidecar_invalid", sidecar=path.name)
        ]
    declared_skill = payload.get("skill")
    summary = {
        "state": "ready",
        "contentHash": _sha256_bytes(raw),
    }
    schema = payload.get("schema", payload.get("schemaVersion"))
    if isinstance(schema, (str, int)) and not isinstance(schema, bool):
        summary["schema"] = schema
    diagnostics = []
    if declared_skill not in (None, ""):
        summary["skill"] = str(declared_skill)[:128]
        if str(declared_skill) != expected_name:
            summary["state"] = "invalid"
            diagnostics.append(_diagnostic(
                "sidecar_skill_mismatch",
                sidecar=path.name,
            ))
    return summary, diagnostics


def _empty_descriptor(source_kind: str, directory: str) -> dict:
    source = {
        "kind": source_kind,
        "directory": directory,
        "sourceId": f"{source_kind}:{directory}",
    }
    return {
        "schema": DESCRIPTOR_SCHEMA,
        "descriptorId": "",
        "identity": {
            "source": source["sourceId"],
            "name": directory,
            "version": "",
            "contentHash": "",
        },
        "source": source,
        "provenance": {"kind": "unresolved"},
        "name": directory,
        "version": "",
        "description": "",
        "license": None,
        "compatibility": None,
        "metadata": {},
        "format": {
            "classification": "invalid",
            "standardCompliant": False,
            "legacyCompatible": False,
            "reasonCodes": [],
        },
        "allowedToolsRaw": "",
        "allowedToolTokens": [],
        "allowedTools": [],
        "toolPolicy": {"mode": "none", "source": "none"},
        "routingKeywords": [],
        "legacyAdapters": {},
        "unknownFields": [],
        "contentHash": "",
        "bodyHash": "",
        "bodyLoaded": False,
        "sidecars": {},
        "health": "invalid",
        "executableCandidate": False,
        "diagnostics": [],
    }


def _finalize_descriptor(descriptor: dict) -> None:
    descriptor["diagnostics"] = _sort_diagnostics(descriptor.get("diagnostics") or [])
    error_codes = {
        item["code"] for item in descriptor["diagnostics"]
        if item.get("severity") == "error"
    }
    if "legacy_ambiguous" in error_codes:
        health = "legacy-ambiguous"
    elif "source_name_conflict" in error_codes or "active_name_conflict" in error_codes:
        health = "conflict"
    elif "skill_unreadable" in error_codes:
        health = "unreadable"
    elif "skill_directory_unsafe" in error_codes or "skill_file_unsafe" in error_codes:
        health = "unsafe"
    elif descriptor.get("provenance", {}).get("kind") == "tombstoned":
        health = "tombstoned"
    elif descriptor.get("provenance", {}).get("kind") == "bundled-not-installed":
        health = "missing"
    elif error_codes:
        health = "invalid"
    elif descriptor.get("source", {}).get("kind") == "bundled":
        health = "reference-only"
    else:
        health = "ready"
    descriptor["health"] = health
    descriptor["executableCandidate"] = bool(
        descriptor.get("source", {}).get("kind") == "installed"
        and health == "ready"
        and descriptor.get("bodyLoaded")
    )
    identity = {
        "source": descriptor["source"]["sourceId"],
        "name": descriptor.get("name") or descriptor["source"]["directory"],
        "version": descriptor.get("version") or "",
        "contentHash": descriptor.get("contentHash") or "",
    }
    descriptor["identity"] = identity
    descriptor["descriptorId"] = "sd1_" + _canonical_hash(identity).split(":", 1)[1]


def _build_descriptor(skill_dir: Path, source_kind: str) -> dict:
    directory = skill_dir.name
    descriptor = _empty_descriptor(source_kind, directory)
    if not SAFE_DIRECTORY_RE.fullmatch(directory):
        descriptor["diagnostics"].append(_diagnostic("skill_directory_name_invalid"))
    if _is_link_or_reparse(skill_dir):
        descriptor["diagnostics"].append(_diagnostic("skill_directory_unsafe"))
        _finalize_descriptor(descriptor)
        return descriptor
    skill_path = skill_dir / "SKILL.md"
    if _is_link_or_reparse(skill_path):
        descriptor["diagnostics"].append(_diagnostic("skill_file_unsafe"))
        _finalize_descriptor(descriptor)
        return descriptor
    if not skill_path.exists():
        descriptor["diagnostics"].append(_diagnostic("skill_document_missing"))
        _finalize_descriptor(descriptor)
        return descriptor
    try:
        raw = _read_skill_bytes(skill_path)
        descriptor["contentHash"] = _sha256_bytes(raw)
        parsed = parse_skill_document(raw.decode("utf-8-sig"))
    except SkillRegistryError as exc:
        descriptor["diagnostics"].append(_diagnostic(exc.code))
        _finalize_descriptor(descriptor)
        return descriptor
    except (OSError, UnicodeError) as exc:
        descriptor["diagnostics"].append(_diagnostic(
            "skill_unreadable", errorType=type(exc).__name__,
        ))
        _finalize_descriptor(descriptor)
        return descriptor

    meta = parsed["meta"]
    body = parsed["body"]
    name = meta.get("name")
    description = meta.get("description")
    field_invalid = False
    if not isinstance(name, str) or not SAFE_NAME_RE.fullmatch(name.strip()):
        descriptor["diagnostics"].append(_diagnostic("skill_name_invalid"))
        field_invalid = True
    else:
        descriptor["name"] = name.strip()
    if not isinstance(description, str) or not description.strip():
        descriptor["diagnostics"].append(_diagnostic("skill_description_invalid"))
        description_text = ""
        field_invalid = True
    else:
        description_text = description.strip()
        descriptor["description"] = " ".join(description_text.split())[:4000]
    if descriptor["name"] != directory:
        descriptor["diagnostics"].append(_diagnostic(
            "skill_directory_name_mismatch", "warning",
        ))

    descriptor["license"] = meta.get("license")
    descriptor["compatibility"] = meta.get("compatibility")
    raw_metadata = meta.get("metadata")
    metadata = {} if raw_metadata is None else raw_metadata
    if not isinstance(metadata, dict):
        descriptor["diagnostics"].append(_diagnostic("skill_metadata_invalid"))
        metadata = {}
        field_invalid = True
    descriptor["metadata"] = metadata

    metadata_version = metadata.get("version")
    top_level_version = meta.get("version")
    version = metadata_version if isinstance(metadata_version, str) else top_level_version
    if version not in (None, ""):
        if isinstance(version, (str, int, float)) and not isinstance(version, bool):
            descriptor["version"] = str(version).strip()[:128]
        else:
            descriptor["diagnostics"].append(_diagnostic("skill_version_invalid"))
            field_invalid = True

    allowed_tools_standard = True
    try:
        allowed_raw = ""
        allowed_tokens = []
        allowed_source = "none"
        if "allowed-tools" in meta:
            (
                allowed_raw,
                allowed_tokens,
                allowed_shape,
                allowed_tools_standard,
            ) = _normalize_allowed_tools(meta.get("allowed-tools"))
            allowed_source = (
                "allowed-tools" if allowed_tools_standard
                else f"legacy-allowed-tools-{allowed_shape.removeprefix('legacy-')}"
            )
        elif "tools" in meta:
            allowed_tokens = _normalize_terms(meta.get("tools"), kind="allowed_tools")
            allowed_source = "legacy-tools"
        elif "tools" in metadata:
            allowed_tokens = _normalize_terms(metadata.get("tools"), kind="allowed_tools")
            allowed_source = "legacy-metadata-tools"
        descriptor["allowedToolsRaw"] = allowed_raw
        descriptor["allowedToolTokens"] = allowed_tokens
        descriptor["allowedTools"] = allowed_tokens
        descriptor["toolPolicy"] = {
            "mode": (
                "narrow-only" if allowed_source.startswith(("allowed-tools", "legacy-allowed-tools"))
                else "preference-only" if allowed_source.startswith("legacy")
                else "none"
            ),
            "source": allowed_source,
        }
        keyword_source = None
        if "keywords" in meta:
            keywords = _normalize_terms(meta.get("keywords"), kind="keywords")
            keyword_source = "legacy-keywords"
        elif "keywords" in metadata:
            keywords = _normalize_terms(metadata.get("keywords"), kind="keywords")
            keyword_source = "legacy-metadata-keywords"
        else:
            keywords = []
        descriptor["routingKeywords"] = keywords
        descriptor["legacyAdapters"] = {
            **({"allowedTools": allowed_source} if allowed_source.startswith("legacy-allowed-tools") else {}),
            **({"tools": allowed_source} if allowed_source in {"legacy-tools", "legacy-metadata-tools"} else {}),
            **({"keywords": keyword_source} if keyword_source else {}),
            **({"version": "legacy-top-level-version"} if "version" in meta else {}),
            **({"metadata": "legacy-nested-values"} if any(
                not isinstance(value, str) for value in metadata.values()
            ) else {}),
        }
    except SkillRegistryError as exc:
        descriptor["diagnostics"].append(_diagnostic(exc.code))
        field_invalid = True

    unknown = sorted(set(meta) - KNOWN_FRONTMATTER_FIELDS)
    descriptor["unknownFields"] = unknown
    if unknown:
        descriptor["diagnostics"].append(_diagnostic(
            "frontmatter_unknown_fields", "info", fields=unknown,
        ))
    format_reasons = _standard_format_reasons(
        meta,
        directory=directory,
        name=name.strip() if isinstance(name, str) else "",
        description=description_text,
        metadata={} if raw_metadata is None else raw_metadata,
        allowed_tools_standard=allowed_tools_standard,
    )
    descriptor["format"] = {
        "classification": (
            "invalid" if field_invalid
            else "code-legacy" if format_reasons
            else "agent-skills-standard"
        ),
        "standardCompliant": not field_invalid and not format_reasons,
        "legacyCompatible": not field_invalid,
        "reasonCodes": format_reasons,
    }
    descriptor["diagnostics"].extend(
        _diagnostic(code, "warning") for code in format_reasons
    )
    descriptor["bodyLoaded"] = bool(body)
    descriptor["bodyHash"] = _sha256_bytes(body.encode("utf-8")) if body else ""
    if not body:
        descriptor["diagnostics"].append(_diagnostic("skill_body_missing"))

    sidecars = {}
    for key, filename in SIDECARS:
        summary, diagnostics = _read_sidecar_summary(skill_dir / filename, descriptor["name"])
        sidecars[key] = summary
        descriptor["diagnostics"].extend(diagnostics)
    descriptor["sidecars"] = sidecars
    _finalize_descriptor(descriptor)
    return descriptor


def _enumerate_descriptors(root: Path, source_kind: str) -> tuple[list[dict], list[dict]]:
    root = Path(root)
    if not root.exists():
        return [], [_diagnostic(f"{source_kind}_root_missing")]
    if _is_link_or_reparse(root) or not root.is_dir():
        return [], [_diagnostic(f"{source_kind}_root_unsafe")]
    try:
        entries = sorted(root.iterdir(), key=lambda item: (item.name.casefold(), item.name))
    except OSError as exc:
        return [], [_diagnostic(
            f"{source_kind}_root_unreadable", errorType=type(exc).__name__,
        )]
    descriptors = []
    for entry in entries:
        try:
            if entry.is_dir() or _is_link_or_reparse(entry):
                descriptors.append(_build_descriptor(entry, source_kind))
        except OSError as exc:
            descriptor = _empty_descriptor(source_kind, entry.name)
            descriptor["diagnostics"].append(_diagnostic(
                "skill_unreadable", errorType=type(exc).__name__,
            ))
            _finalize_descriptor(descriptor)
            descriptors.append(descriptor)
    return descriptors, []


def _add_descriptor_diagnostic(descriptor: dict, code: str, severity="error", **fields) -> None:
    descriptor["diagnostics"] = [
        *(descriptor.get("diagnostics") or []),
        _diagnostic(code, severity, **fields),
    ]
    _finalize_descriptor(descriptor)


def build_skill_registry_snapshot(installed_skills_dir, bundled_skills_dir) -> dict:
    """Build a deterministic, read-only registry snapshot from two source roots."""
    installed_root = Path(installed_skills_dir)
    bundled_root = Path(bundled_skills_dir)
    try:
        same_root = installed_root.resolve() == bundled_root.resolve()
    except OSError:
        same_root = False

    bundled, bundled_diagnostics = (
        ([], []) if same_root else _enumerate_descriptors(bundled_root, "bundled")
    )
    installed, installed_diagnostics = _enumerate_descriptors(installed_root, "installed")
    registry_diagnostics = [*bundled_diagnostics, *installed_diagnostics]

    tombstones = []
    if not same_root:
        try:
            tombstones = list(load_bundled_skill_state(installed_root).get("tombstones") or [])
        except BundledSkillStateError as exc:
            registry_diagnostics.append(_diagnostic(
                "bundled_state_invalid", errorType=type(exc).__name__,
            ))

    bundled_by_directory = {
        item["source"]["directory"]: item
        for item in bundled
    }
    for descriptor in bundled:
        if descriptor.get("name") in tombstones or descriptor["source"]["directory"] in tombstones:
            descriptor["provenance"] = {"kind": "tombstoned"}
        else:
            descriptor["provenance"] = {"kind": "bundled-reference"}
        _finalize_descriptor(descriptor)

    for descriptor in installed:
        if same_root:
            # Development uses one physical root for installed and bundled
            # Skills. Record that observable fact without guessing whether a
            # particular directory originated from a shipped copy or a local
            # authoring action.
            descriptor["provenance"] = {"kind": "shared-development"}
            _finalize_descriptor(descriptor)
            continue
        reference = bundled_by_directory.get(descriptor["source"]["directory"])
        if reference is None:
            descriptor["provenance"] = {"kind": "custom"}
            _finalize_descriptor(descriptor)
            continue
        if (
            descriptor.get("contentHash")
            and descriptor.get("contentHash") == reference.get("contentHash")
            and descriptor.get("name") == reference.get("name")
        ):
            descriptor["provenance"] = {
                "kind": "bundled-current",
                "referenceDescriptorId": reference["descriptorId"],
            }
            _finalize_descriptor(descriptor)
        else:
            descriptor["provenance"] = {
                "kind": "legacy-ambiguous",
                "referenceDescriptorId": reference["descriptorId"],
            }
            _add_descriptor_diagnostic(descriptor, "legacy_ambiguous")

    installed_directories = {
        item["source"]["directory"] for item in installed
    }
    for descriptor in bundled:
        if (
            descriptor.get("provenance", {}).get("kind") == "bundled-reference"
            and descriptor["source"]["directory"] not in installed_directories
        ):
            descriptor["provenance"] = {"kind": "bundled-not-installed"}
            _finalize_descriptor(descriptor)

    active_by_name = {}
    bundled_by_name = {}
    for descriptor in installed:
        active_by_name.setdefault(descriptor.get("name") or "", []).append(descriptor)
    for descriptor in bundled:
        bundled_by_name.setdefault(descriptor.get("name") or "", []).append(descriptor)

    for name, group in active_by_name.items():
        if not name:
            continue
        if len(group) > 1:
            for descriptor in group:
                _add_descriptor_diagnostic(descriptor, "active_name_conflict")
        for descriptor in group:
            references = bundled_by_name.get(name) or []
            if not references:
                continue
            exact_lineage = any(
                descriptor.get("contentHash")
                and descriptor.get("contentHash") == reference.get("contentHash")
                and descriptor["source"]["directory"] == reference["source"]["directory"]
                for reference in references
            )
            if not exact_lineage and descriptor.get("provenance", {}).get("kind") != "legacy-ambiguous":
                _add_descriptor_diagnostic(descriptor, "source_name_conflict")

    descriptors = sorted(
        [*installed, *bundled],
        key=lambda item: (
            0 if item["source"]["kind"] == "installed" else 1,
            str(item.get("name") or "").casefold(),
            item["source"]["directory"].casefold(),
            item["descriptorId"],
        ),
    )
    counts = {}
    for descriptor in descriptors:
        health = descriptor["health"]
        counts[health] = counts.get(health, 0) + 1
    snapshot = {
        "schema": REGISTRY_SCHEMA,
        "version": 1,
        "rootMode": "shared-development" if same_root else "separate-installed-and-bundled",
        "descriptors": descriptors,
        "diagnostics": _sort_diagnostics(registry_diagnostics),
        "summary": {
            "total": len(descriptors),
            "executable": sum(bool(item.get("executableCandidate")) for item in descriptors),
            "byHealth": {key: counts[key] for key in sorted(counts)},
        },
    }
    snapshot["health"] = "degraded" if (
        snapshot["diagnostics"]
        or any(item["health"] in {"conflict", "invalid", "legacy-ambiguous", "missing", "unsafe", "unreadable"} for item in descriptors)
    ) else "ready"
    snapshot["registryHash"] = _canonical_hash(snapshot)
    return snapshot


def project_skill_tools(descriptor: dict, permission_tool_names: Iterable[str]) -> dict:
    """Project descriptor tool intent without ever expanding the caller profile."""
    permitted = []
    for name in permission_tool_names or []:
        normalized = str(name or "").strip()
        if normalized and normalized not in permitted:
            permitted.append(normalized)
    declared = {
        str(name or "").strip()
        for name in descriptor.get("allowedTools") or []
        if str(name or "").strip()
    }
    policy = descriptor.get("toolPolicy") or {}
    mode = str(policy.get("mode") or "none")
    if mode == "narrow-only":
        allowed = [name for name in permitted if name in declared]
    else:
        allowed = list(permitted)
    return {
        "mode": mode,
        "allowed": allowed,
        "preferred": [name for name in permitted if name in declared],
    }


ACTION_PATTERNS = (
    ("audit", 100, re.compile(r"审计|校验|验证|核对|检查|audit|validate|verify", re.I)),
    ("create", 90, re.compile(r"创建|生成|制作|新建|create|generate|build", re.I)),
    ("edit", 80, re.compile(r"编辑|修改|更新|调整|修复|edit|modify|update|fix", re.I)),
    ("read", 70, re.compile(r"读取|提取|分析|总结|打开|read|extract|analy[sz]e|summari[sz]e", re.I)),
)
FORMAT_HINTS = {
    "xlsx": (
        (100, re.compile(r"\.(?:xlsx|xlsm|xls|csv|tsv)\b", re.I)),
        (90, re.compile(r"\b(?:xlsx|xlsm|excel|spreadsheet|workbook|csv|tsv)\b", re.I)),
        (90, re.compile(r"工作簿|电子表格")),
        (35, re.compile(r"表格")),
    ),
    "docx": (
        (100, re.compile(r"\.(?:docx|dotx)\b", re.I)),
        (90, re.compile(r"\b(?:docx|word)\b", re.I)),
        (80, re.compile(r"Word\s*文档|文字文档", re.I)),
    ),
    "pptx": (
        (100, re.compile(r"\.(?:pptx|potx)\b", re.I)),
        (90, re.compile(r"\b(?:pptx|powerpoint|ppt|deck)\b", re.I)),
        (85, re.compile(r"演示文稿|幻灯片")),
    ),
    "pdf": (
        (100, re.compile(r"\.pdf\b", re.I)),
        (90, re.compile(r"\bpdf\b", re.I)),
        (85, re.compile(r"PDF\s*文件", re.I)),
    ),
}
DESIGN_INTENT_RE = re.compile(
    r"美化|排版|配色|视觉|样式|风格|精美|专业设计|图表|design|polish|theme|layout|style",
    re.I,
)
OUTPUT_HINT_RE = re.compile(r"(?:存|保存|导出|转换|转|输出)\s*(?:为|成|到)?\s*$", re.I)


def _action_candidates(message: str, explicit_action: str = "") -> list[dict]:
    allowed = {item[0] for item in ACTION_PATTERNS} | {"general"}
    normalized = str(explicit_action or "").strip().lower()
    if normalized:
        if normalized not in allowed:
            raise SkillRegistryError("shadow_action_invalid", "Shadow action is invalid")
        return [{"id": normalized, "score": 1000, "reasonCode": "explicit_action"}]
    candidates = []
    for action, score, pattern in ACTION_PATTERNS:
        if pattern.search(message):
            candidates.append({"id": action, "score": score, "reasonCode": f"inferred_{action}"})
    if not candidates:
        candidates.append({"id": "general", "score": 0, "reasonCode": "no_action_signal"})
    return sorted(candidates, key=lambda item: (-item["score"], item["id"]))


def _format_candidates(message: str) -> list[dict]:
    candidates = []
    for name, hints in FORMAT_HINTS.items():
        best = 0
        for score, pattern in hints:
            for match in pattern.finditer(message):
                adjusted = score
                prefix = message[max(0, match.start() - 12):match.start()]
                if OUTPUT_HINT_RE.search(prefix):
                    adjusted -= 25
                best = max(best, adjusted)
        if best:
            candidates.append({"name": name, "score": best, "reasonCode": f"format_{name}"})
    return sorted(candidates, key=lambda item: (-item["score"], item["name"]))


def _candidate(descriptor: dict, role: str, reason: str, score: int) -> dict:
    return {
        "descriptorId": descriptor["descriptorId"],
        "name": descriptor["name"],
        "source": descriptor["source"]["sourceId"],
        "role": role,
        "reasonCode": reason,
        "score": int(score),
    }


def _legacy_match_score(descriptor: dict, message_lower: str) -> int:
    keyword_scores = []
    for keyword in descriptor.get("routingKeywords") or []:
        parts = [part.strip().lower() for part in str(keyword).split("+") if part.strip()]
        if parts and all(part in message_lower for part in parts):
            keyword_scores.append(300 + sum(len(part) for part in parts))
    if keyword_scores:
        return max(keyword_scores)
    name = str(descriptor.get("name") or "").lower()
    if len(name) >= 2 and name in message_lower:
        return 200 + len(name)
    return 0


def resolve_skill_shadow(
    registry_snapshot: dict,
    user_message: str,
    *,
    explicit_skill: str = "",
    disabled_names: Iterable[str] = (),
    action: str = "",
) -> dict:
    """Return a diagnostic-only owner/modifier/reference resolution."""
    if not isinstance(registry_snapshot, dict) or registry_snapshot.get("schema") != REGISTRY_SCHEMA:
        raise SkillRegistryError("registry_snapshot_invalid", "Skill registry snapshot is invalid")
    message = str(user_message or "")
    if len(message) > MAX_MESSAGE_CHARS:
        raise SkillRegistryError("shadow_message_too_large", "Shadow message is too large")
    message_lower = message.lower()
    explicit = str(explicit_skill or "").strip()
    if explicit and not SAFE_NAME_RE.fullmatch(explicit):
        raise SkillRegistryError("explicit_skill_invalid", "Explicit Skill name is invalid")
    disabled = {
        str(name or "").strip()
        for name in disabled_names or []
        if isinstance(name, str) and SAFE_NAME_RE.fullmatch(str(name).strip())
    }
    descriptors = list(registry_snapshot.get("descriptors") or [])
    active = [item for item in descriptors if item.get("source", {}).get("kind") == "installed"]
    eligible = [
        item for item in active
        if item.get("executableCandidate") and item.get("name") not in disabled
    ]
    by_name = {}
    for descriptor in eligible:
        by_name.setdefault(descriptor["name"], []).append(descriptor)

    exclusions = []
    for descriptor in active:
        if descriptor.get("name") in disabled:
            exclusions.append({
                "descriptorId": descriptor["descriptorId"],
                "name": descriptor["name"],
                "source": descriptor["source"]["sourceId"],
                "reasonCode": "skill_disabled",
            })
        elif not descriptor.get("executableCandidate"):
            exclusions.append({
                "descriptorId": descriptor["descriptorId"],
                "name": descriptor["name"],
                "source": descriptor["source"]["sourceId"],
                "reasonCode": f"descriptor_{descriptor.get('health') or 'invalid'}",
            })

    action_candidates = _action_candidates(message, action)
    selected_action = action_candidates[0]
    owner = None
    modifiers = []
    references = []
    diagnostics = []

    if explicit:
        matches = by_name.get(explicit) or []
        if len(matches) == 1:
            owner = _candidate(matches[0], "owner", "explicit_skill", 1000)
        else:
            diagnostics.append(_diagnostic(
                "explicit_skill_unavailable", "warning", skill=explicit,
            ))
    else:
        formats = _format_candidates(message)
        if formats:
            best_score = formats[0]["score"]
            best_formats = [item for item in formats if item["score"] == best_score]
            if len(best_formats) > 1:
                diagnostics.append(_diagnostic(
                    "execution_domain_ambiguous", "warning",
                    domains=[item["name"] for item in best_formats],
                ))
                for item in best_formats:
                    matches = by_name.get(item["name"]) or []
                    if len(matches) == 1:
                        references.append(_candidate(
                            matches[0], "reference", "ambiguous_execution_domain", item["score"],
                        ))
            else:
                domain = best_formats[0]
                matches = by_name.get(domain["name"]) or []
                if len(matches) == 1:
                    owner = _candidate(
                        matches[0], "owner", "specialist_format_owner", domain["score"],
                    )
                else:
                    diagnostics.append(_diagnostic(
                        "execution_owner_unavailable", "warning", domain=domain["name"],
                    ))
                if selected_action["id"] in {"audit", "read"}:
                    aggregate = by_name.get("office-files") or []
                    if len(aggregate) == 1:
                        references.append(_candidate(
                            aggregate[0], "reference", "office_read_reference", 40,
                        ))
                if DESIGN_INTENT_RE.search(message):
                    design = by_name.get("document-design") or []
                    if len(design) == 1:
                        modifiers.append(_candidate(
                            design[0], "modifier", "document_design_modifier", 60,
                        ))
        else:
            scored = []
            for descriptor in eligible:
                name = descriptor.get("name") or ""
                if name in EXPLICIT_ONLY_SKILLS or name in OFFICE_ROUTE_NAMES:
                    continue
                score = _legacy_match_score(descriptor, message_lower)
                if score:
                    scored.append((score, descriptor))
            if scored:
                best_score = max(score for score, _ in scored)
                best = [descriptor for score, descriptor in scored if score == best_score]
                if len(best) == 1:
                    owner = _candidate(best[0], "owner", "legacy_adapter_unique_best", best_score)
                else:
                    diagnostics.append(_diagnostic(
                        "legacy_match_ambiguous", "warning",
                        skills=sorted(item["name"] for item in best),
                    ))
                    references.extend(
                        _candidate(item, "reference", "legacy_match_tie", best_score)
                        for item in sorted(best, key=lambda value: value["descriptorId"])
                    )

    result = {
        "schema": RESOLUTION_SCHEMA,
        "registryHash": registry_snapshot.get("registryHash") or "",
        "input": {
            "messageHash": _sha256_bytes(message.encode("utf-8")),
            "messageLength": len(message),
            "explicitSkill": explicit,
        },
        "action": selected_action,
        "actionCandidates": action_candidates,
        "owner": owner,
        "modifiers": sorted(modifiers, key=lambda item: (-item["score"], item["descriptorId"])),
        "references": sorted(references, key=lambda item: (-item["score"], item["descriptorId"])),
        "excluded": sorted(exclusions, key=lambda item: (item["name"], item["descriptorId"])),
        "diagnostics": _sort_diagnostics(diagnostics),
    }
    result["resolutionHash"] = _canonical_hash(result)
    return result


def compare_observed_and_shadow(observed_names: Iterable[str], shadow_resolution: dict) -> dict:
    """Compare an externally observed resolver result with the shadow output."""
    observed = []
    for name in observed_names or []:
        normalized = str(name or "").strip()
        if normalized and normalized not in observed:
            observed.append(normalized)
    owner = shadow_resolution.get("owner") or {}
    shadow = []
    if owner.get("name"):
        shadow.append(owner["name"])
    for candidate in shadow_resolution.get("modifiers") or []:
        name = str(candidate.get("name") or "")
        if name and name not in shadow:
            shadow.append(name)
    report = {
        "schema": COMPARISON_SCHEMA,
        "observedNames": observed,
        "shadowExecutionNames": shadow,
        "added": sorted(set(shadow) - set(observed)),
        "removed": sorted(set(observed) - set(shadow)),
        "changed": observed != shadow,
    }
    report["comparisonHash"] = _canonical_hash(report)
    return report
