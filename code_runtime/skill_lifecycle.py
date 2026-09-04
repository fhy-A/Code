"""Versioned, credential-free Skill lifecycle records for AgentRun v5."""

from __future__ import annotations

import json
from pathlib import PurePosixPath
import re

from code_runtime.skill_registry import SAFE_DIRECTORY_RE, SAFE_NAME_RE

LIFECYCLE_SCHEMA_VERSION = 1
ACTIVATION_SCHEMA_VERSION = 1
ACCESS_SCHEMA_VERSION = 2
LEGACY_ACCESS_SCHEMA_VERSION = 1
LIFECYCLE_MODE = "canonical-v1"
MAX_SELECTED_SKILLS = 2
MAX_CAPABILITIES = 64
MAX_RESOURCE_BINDINGS = 64
MAX_EVIDENCE_CONTRACT_BYTES = 64 * 1024
MAX_LIFECYCLE_BYTES = 256 * 1024
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}")
_DESCRIPTOR_ID_RE = re.compile(r"sd1_[0-9a-f]{64}")
_CAPABILITY_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_RESOURCE_SOURCE = {"custom", "installed", "bundled-fallback"}


class SkillLifecycleError(ValueError):
    """Stable fail-closed error for canonical Skill lifecycle records."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code)


def _invalid(message: str):
    raise SkillLifecycleError("skill_lifecycle_invalid", message)

def _require_exact_keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        _invalid(f"{label} is invalid")

def _require_version(value, expected, code, label):
    if isinstance(value, bool) or not isinstance(value, int) or value != expected:
        raise SkillLifecycleError(code, f"{label} is unsupported")


def _json_clone(value, *, limit=MAX_LIFECYCLE_BYTES):
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(raw) > limit:
            _invalid("Skill lifecycle is too large")
        return json.loads(raw.decode("utf-8"))
    except (TypeError, ValueError, UnicodeError) as exc:
        if isinstance(exc, SkillLifecycleError):
            raise
        raise SkillLifecycleError(
            "skill_lifecycle_invalid", "Skill lifecycle is not JSON-safe",
        ) from exc


def _normalize_hash(value, label):
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        _invalid(f"{label} is invalid")
    return value


def _normalize_source(value):
    _require_exact_keys(value, {"kind", "directory", "descriptorId"}, "Skill source")
    directory = value.get("directory")
    descriptor_id = value.get("descriptorId")
    if value.get("kind") != "installed":
        _invalid("Skill source kind is invalid")
    if not isinstance(directory, str) or not SAFE_DIRECTORY_RE.fullmatch(directory):
        _invalid("Skill source directory is invalid")
    if not isinstance(descriptor_id, str) or not _DESCRIPTOR_ID_RE.fullmatch(descriptor_id):
        _invalid("Skill descriptor identity is invalid")
    return {"kind": "installed", "directory": directory, "descriptorId": descriptor_id}


def _normalize_evidence(value):
    if not isinstance(value, dict):
        _invalid("Skill evidence identity is invalid")
    state = value.get("state")
    if state == "missing":
        _require_exact_keys(value, {"state"}, "Missing Skill evidence")
        return {"state": "missing"}
    if state == "invalid":
        _require_exact_keys(
            value, {"state", "contentHash"}, "Invalid Skill evidence",
        )
        return {"state": "invalid", "contentHash": _normalize_hash(
            value.get("contentHash"), "Skill evidence hash",
        )}
    if state != "ready":
        _invalid("Skill evidence state is invalid")
    _require_exact_keys(
        value, {"state", "contentHash", "contract"}, "Ready Skill evidence",
    )
    contract = value.get("contract")
    if not isinstance(contract, dict):
        _invalid("Skill evidence contract is invalid")
    contract = _json_clone(contract, limit=MAX_EVIDENCE_CONTRACT_BYTES)
    return {"state": "ready", "contentHash": _normalize_hash(
        value.get("contentHash"), "Skill evidence hash",
    ), "contract": contract}


def _normalize_dependency(value):
    if not isinstance(value, dict):
        _invalid("Skill dependency identity is invalid")
    state = value.get("state")
    if state == "missing":
        _require_exact_keys(
            value, {"state", "capabilities"}, "Missing Skill dependency",
        )
    elif state == "ready":
        _require_exact_keys(
            value,
            {"state", "manifestHash", "capabilities"},
            "Ready Skill dependency",
        )
    else:
        _invalid("Skill dependency state is invalid")
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, list) or len(capabilities) > MAX_CAPABILITIES:
        _invalid("Skill dependency capabilities are invalid")
    normalized = []
    for capability in capabilities:
        if (
            not isinstance(capability, str)
            or not _CAPABILITY_RE.fullmatch(capability)
            or capability in normalized
        ):
            _invalid("Skill dependency capability is invalid")
        normalized.append(capability)
    if normalized != sorted(normalized):
        _invalid("Skill dependency capabilities are not canonical")
    result = {"state": state, "capabilities": normalized}
    if state == "ready":
        result["manifestHash"] = _normalize_hash(
            value.get("manifestHash"), "Skill dependency manifest hash",
        )
    elif normalized:
        _invalid("Missing Skill dependency cannot declare capabilities")
    return result


def _normalize_resources(value):
    if not isinstance(value, dict):
        _invalid("Skill resource identity is invalid")
    state = value.get("state")
    if state == "missing":
        _require_exact_keys(value, {"state"}, "Missing Skill resources")
        return {"state": "missing"}
    if state != "ready":
        _invalid("Skill resource state is invalid")
    keys = set(value)
    if keys not in ({"state", "contractHash"}, {"state", "contractHash", "source"}):
        _invalid("Ready Skill resources is invalid")
    result = {"state": "ready", "contractHash": _normalize_hash(
        value.get("contractHash"), "Skill resource contract hash",
    )}
    if "source" in value:
        if value.get("source") not in _RESOURCE_SOURCE:
            _invalid("Skill resource source is invalid")
        result["source"] = value["source"]
    return result


def normalize_text_resource_path(value) -> str:
    if not isinstance(value, str):
        raise SkillLifecycleError(
            "skill_lifecycle_reference_invalid", "Skill reference is invalid",
        )
    raw = value.replace("\\", "/")
    path = PurePosixPath(raw)
    if (
        not raw
        or raw.startswith("/")
        or len(raw.encode("utf-8")) > 1024
        or path.is_absolute()
        or raw.casefold() == "skill.md"
        or any(
            part in {"", ".", ".."} or part.casefold() == "__pycache__"
            or part.startswith(".")
            or ":" in part
            or part.rstrip(" .") != part
            for part in path.parts
        )
    ):
        raise SkillLifecycleError(
            "skill_lifecycle_reference_invalid", "Skill reference is invalid",
        )
    return path.as_posix()


def _normalize_resource_bindings(value, selected_names):
    if not isinstance(value, list) or len(value) > MAX_RESOURCE_BINDINGS:
        _invalid("Skill access bindings are invalid")
    bindings = []
    keys = set()
    for item in value:
        _require_exact_keys(
            item, {"kind", "skill", "file", "contentHash"}, "Skill access binding",
        )
        skill = item.get("skill")
        if item.get("kind") != "text" or skill not in selected_names:
            _invalid("Skill access binding identity is invalid")
        binding = {
            "kind": "text",
            "skill": skill,
            "file": normalize_text_resource_path(item.get("file")),
            "contentHash": _normalize_hash(
                item.get("contentHash"), "Skill access binding content hash",
            ),
        }
        key = (skill, binding["file"].casefold())
        if key in keys:
            _invalid("Skill access bindings are duplicated")
        keys.add(key)
        bindings.append(binding)
    if bindings != sorted(bindings, key=lambda item: (item["skill"], item["file"].casefold())):
        _invalid("Skill access bindings are not canonical")
    return bindings


def _normalize_selected(value, index):
    _require_exact_keys(
        value,
        {
            "name", "role", "source", "skillContentHash",
            "evidence", "dependency", "resources",
        },
        "Selected Skill",
    )
    name = value.get("name")
    if not isinstance(name, str) or not SAFE_NAME_RE.fullmatch(name):
        _invalid("Selected Skill name is invalid")
    expected_role = "owner" if index == 0 else "modifier"
    if value.get("role") != expected_role:
        _invalid("Selected Skill role is invalid")
    return {
        "name": name,
        "role": expected_role,
        "source": _normalize_source(value.get("source")),
        "skillContentHash": _normalize_hash(
            value.get("skillContentHash"), "Selected Skill content hash",
        ),
        "evidence": _normalize_evidence(value.get("evidence")),
        "dependency": _normalize_dependency(value.get("dependency")),
        "resources": _normalize_resources(value.get("resources")),
    }


def normalize_skill_lifecycle(value) -> dict:
    """Validate and deep-copy canonical ``skillLifecycle/v1`` data."""
    _require_exact_keys(
        value, {"schemaVersion", "mode", "activation", "access"}, "Skill lifecycle",
    )
    _require_version(
        value.get("schemaVersion"),
        LIFECYCLE_SCHEMA_VERSION,
        "skill_lifecycle_version_unsupported",
        "Skill lifecycle version",
    )
    if value.get("mode") != LIFECYCLE_MODE:
        _invalid("Skill lifecycle mode is invalid")

    activation = value.get("activation")
    _require_exact_keys(
        activation,
        {"schemaVersion", "intentKind", "outcome", "selected"},
        "Skill activation lifecycle",
    )
    _require_version(
        activation.get("schemaVersion"),
        ACTIVATION_SCHEMA_VERSION,
        "skill_lifecycle_activation_version_unsupported",
        "Skill activation lifecycle version",
    )
    intent_kind = activation.get("intentKind")
    outcome = activation.get("outcome")
    selected_source = activation.get("selected")
    if intent_kind not in {"explicit", "automatic"}:
        _invalid("Skill activation intent kind is invalid")
    if outcome not in {"activated", "none"}:
        _invalid("Skill activation outcome is invalid")
    if not isinstance(selected_source, list) or len(selected_source) > MAX_SELECTED_SKILLS:
        _invalid("Selected Skill set is invalid")
    selected = [_normalize_selected(item, index) for index, item in enumerate(selected_source)]
    names = [item["name"] for item in selected]
    if len(names) != len(set(names)):
        _invalid("Selected Skill names are duplicated")
    if outcome == "none" and selected:
        _invalid("Empty Skill activation cannot select Skills")
    if outcome == "activated" and not selected:
        _invalid("Activated Skill lifecycle must select a Skill")
    if intent_kind == "explicit" and (outcome != "activated" or len(selected) != 1):
        _invalid("Explicit Skill activation must select exactly one owner")

    access = value.get("access")
    _require_exact_keys(
        access, {"schemaVersion", "resourceBindings"}, "Skill access lifecycle",
    )
    access_version = access.get("schemaVersion")
    if isinstance(access_version, bool):
        _require_version(access_version, ACCESS_SCHEMA_VERSION,
                         "skill_lifecycle_access_version_unsupported",
                         "Skill access lifecycle version")
    if access_version == LEGACY_ACCESS_SCHEMA_VERSION:
        if access.get("resourceBindings") != []:
            _invalid("Legacy Skill access bindings must be empty")
        bindings = []
    elif access_version == ACCESS_SCHEMA_VERSION:
        bindings = _normalize_resource_bindings(access.get("resourceBindings"), set(names))
    else:
        _require_version(
            access_version,
            ACCESS_SCHEMA_VERSION,
            "skill_lifecycle_access_version_unsupported",
            "Skill access lifecycle version",
        )

    return _json_clone({
        "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
        "mode": LIFECYCLE_MODE,
        "activation": {
            "schemaVersion": ACTIVATION_SCHEMA_VERSION,
            "intentKind": intent_kind,
            "outcome": outcome,
            "selected": selected,
        },
        "access": {"schemaVersion": access_version, "resourceBindings": bindings},
    })


def build_skill_lifecycle(activation, *, evidence_observers) -> dict:
    """Build lifecycle v1 only from the server's canonical activation capture."""
    if not isinstance(activation, dict) or not isinstance(activation.get("explicit"), bool):
        _invalid("Canonical Skill activation is invalid")
    captures = activation.get("captures")
    if not isinstance(captures, list) or len(captures) > MAX_SELECTED_SKILLS:
        _invalid("Canonical Skill activation captures are invalid")
    if (
        not isinstance(evidence_observers, list)
        or len(evidence_observers) != len(captures)
    ):
        _invalid("Canonical Skill evidence projection is invalid")
    selected = []
    for index, (capture, observer) in enumerate(zip(captures, evidence_observers)):
        if not isinstance(capture, dict) or not isinstance(observer, dict):
            _invalid("Canonical Skill capture is invalid")
        evidence_identity = capture.get("evidenceIdentity")
        if not isinstance(evidence_identity, dict):
            _invalid("Canonical Skill evidence identity is invalid")
        active = observer.get("activeSkill")
        if not isinstance(active, dict) or (
            active.get("name") != capture.get("name")
            or active.get("contentHash") != capture.get("contentHash")
        ):
            _invalid("Canonical Skill evidence projection identity is invalid")
        observer_state = observer.get("contractState")
        if observer_state == "valid" and evidence_identity.get("state") == "ready":
            evidence_record = {
                **evidence_identity,
                "contract": observer.get("contract"),
            }
        elif observer_state == "invalid" and evidence_identity.get("state") == "ready":
            evidence_record = {
                "state": "invalid",
                "contentHash": evidence_identity.get("contentHash"),
            }
        elif observer_state == "missing" and evidence_identity.get("state") == "missing":
            evidence_record = {"state": "missing"}
        else:
            _invalid("Canonical Skill evidence projection conflicts with its capture")
        resource_identity = capture.get("resourceIdentity")
        if (resource_identity or {}).get("state") == "ready" and "source" not in resource_identity:
            _invalid("Canonical Skill resource identity is incomplete")
        selected.append({
            "name": capture.get("name"),
            "role": "owner" if index == 0 else "modifier",
            "source": capture.get("sourceIdentity"),
            "skillContentHash": capture.get("contentHash"),
            "evidence": evidence_record,
            "dependency": capture.get("dependencyIdentity"),
            "resources": resource_identity,
        })
    return normalize_skill_lifecycle({
        "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
        "mode": LIFECYCLE_MODE,
        "activation": {
            "schemaVersion": ACTIVATION_SCHEMA_VERSION,
            "intentKind": "explicit" if activation["explicit"] else "automatic",
            "outcome": "activated" if selected else "none",
            "selected": selected,
        },
        "access": {"schemaVersion": ACCESS_SCHEMA_VERSION, "resourceBindings": []},
    })


def require_active_skill(value, name) -> dict:
    lifecycle = normalize_skill_lifecycle(value)
    requested = str(name or "").strip()
    for selected in lifecycle["activation"]["selected"]:
        if selected["name"] == requested:
            return _json_clone(selected)
    raise SkillLifecycleError(
        "skill_lifecycle_skill_not_active", "Requested Skill is not active",
    )


def bind_text_resource(value, skill, file, content_hash) -> dict:
    lifecycle = normalize_skill_lifecycle(value)
    selected = require_active_skill(lifecycle, skill)
    normalized_file = normalize_text_resource_path(file)
    normalized_hash = _normalize_hash(content_hash, "Skill reference content hash")
    bindings = list(lifecycle["access"]["resourceBindings"])
    for binding in bindings:
        if binding["skill"] == selected["name"] and binding["file"].casefold() == normalized_file.casefold():
            if binding["contentHash"] != normalized_hash:
                raise SkillLifecycleError(
                    "skill_lifecycle_reference_changed", "Skill reference changed",
                )
            return lifecycle
    if len(bindings) >= MAX_RESOURCE_BINDINGS:
        raise SkillLifecycleError(
            "skill_lifecycle_reference_limit", "Skill reference limit is reached",
        )
    bindings.append({
        "kind": "text",
        "skill": selected["name"],
        "file": normalized_file,
        "contentHash": normalized_hash,
    })
    lifecycle["access"] = {
        "schemaVersion": ACCESS_SCHEMA_VERSION,
        "resourceBindings": sorted(bindings, key=lambda item: (item["skill"], item["file"].casefold())),
    }
    return normalize_skill_lifecycle(lifecycle)


def project_skill_lifecycle(value) -> dict:
    """Project canonical activation fields used by AgentRun v5 compatibility data."""
    lifecycle = normalize_skill_lifecycle(value)
    activation = lifecycle["activation"]
    selected = activation["selected"]
    return {
        "activeSkillNames": [item["name"] for item in selected],
        "dependencies": {
            item["name"]: list(item["dependency"]["capabilities"])
            for item in selected
        },
        "captures": [
            {
                "name": item["name"],
                "contentHash": item["skillContentHash"],
                "evidenceState": item["evidence"]["state"],
                "evidence": (
                    _json_clone(item["evidence"]["contract"])
                    if item["evidence"]["state"] == "ready"
                    else {} if item["evidence"]["state"] == "invalid" else None
                ),
            }
            for item in selected
        ],
        "explicit": activation["intentKind"] == "explicit",
    }


def adapt_legacy_skill_lifecycle(active_names, dependencies, skill_evidence) -> dict:
    """Return an in-memory, non-persistable view of legacy AgentRun Skill fields."""
    names = []
    for value in active_names or []:
        name = value.strip() if isinstance(value, str) else ""
        if SAFE_NAME_RE.fullmatch(name) and name not in names:
            names.append(name)
    evidence_items = []
    if isinstance(skill_evidence, dict):
        sources = skill_evidence.get("skills")
        evidence_items = sources if isinstance(sources, list) else [skill_evidence]
    content_hashes = {}
    for item in evidence_items:
        active = item.get("activeSkill") if isinstance(item, dict) else None
        name = str((active or {}).get("name") or "")
        content_hash = str((active or {}).get("contentHash") or "")
        if SAFE_NAME_RE.fullmatch(name) and _HASH_RE.fullmatch(content_hash):
            content_hashes[name] = content_hash
    selected = []
    for name in names:
        item = {"name": name, "role": "unknown"}
        if name in content_hashes:
            item["skillContentHash"] = content_hashes[name]
        capabilities = (dependencies or {}).get(name) if isinstance(dependencies, dict) else None
        if isinstance(capabilities, list):
            item["dependencyCapabilities"] = [
                value for value in capabilities if isinstance(value, str)
            ]
        selected.append(item)
    return {
        "schemaVersion": 0,
        "mode": "legacy",
        "activation": {
            "schemaVersion": 0,
            "intentKind": "unknown",
            "outcome": "activated" if selected else "none",
            "selected": selected,
        },
        "access": {"schemaVersion": 0, "resourceBindings": []},
    }
