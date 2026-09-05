"""Pure immutable Skill lifecycle/v2 contracts; no AgentRun integration."""
from __future__ import annotations

import json
from pathlib import PurePosixPath
import re
import unicodedata

from . import skill_dependencies

LIFECYCLE_SCHEMA_VERSION = 2
ACTIVATION_SCHEMA_VERSION = 2
ACCESS_SCHEMA_VERSION = 3
LIFECYCLE_MODE = "immutable-v1"
MAX_SELECTED_SKILLS = 2
MAX_RESOURCE_BINDINGS = 64
MAX_EVIDENCE_CONTRACT_BYTES = 64 * 1024
MAX_DEPENDENCY_CONTRACT_BYTES = 128 * 1024
MAX_RESOURCE_CONTRACT_BYTES = 128 * 1024
MAX_LIFECYCLE_BYTES = 256 * 1024

_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ROOT_ID = re.compile(r"dr1_[0-9a-f]{32}\Z")
_INSTALL_ID = re.compile(r"si1_[0-9a-f]{32}\Z")
_SKILL_ID = re.compile(r"(?:local\.skill/[0-9a-f]{32}|code\.bundle/[a-z0-9][a-z0-9._-]{0,127})\Z")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")
_RESOURCE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_PROTOCOL = re.compile(r"[a-z0-9][a-z0-9._/-]{0,127}\Z")
_RESOURCE_KIND = {"python", "python-library"}


class SkillLifecycleV2Error(ValueError):
    def __init__(self, code, message="Immutable Skill lifecycle is invalid"):
        self.code = str(code)
        super().__init__(message)


def _fail(code):
    raise SkillLifecycleV2Error(code)


def _exact(value, fields, code="skill_lifecycle_v2_invalid"):
    if not isinstance(value, dict) or set(value) != set(fields):
        _fail(code)


def _clone(value, limit):
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise SkillLifecycleV2Error("skill_lifecycle_v2_json_invalid") from exc
    if len(raw) > limit:
        _fail("skill_lifecycle_v2_size_limit")
    return json.loads(raw)


def _hash(value, code="skill_lifecycle_v2_hash_invalid"):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        _fail(code)
    return value


def _relative(value, *, allow_skill=False):
    if not isinstance(value, str):
        _fail("skill_lifecycle_v2_path_invalid")
    raw = value.replace("\\", "/")
    path = PurePosixPath(raw)
    if (not raw or not path.parts or raw != path.as_posix() or raw.startswith("/") or len(raw.encode()) > 1024 or path.is_absolute()
            or not allow_skill and raw.casefold() == "skill.md"
            or any(part in {"", ".", ".."} or part.startswith(".") or ":" in part
                   or part.rstrip(" .") != part for part in path.parts)):
        _fail("skill_lifecycle_v2_path_invalid")
    return path.as_posix()


def normalize_evidence_contract(value):
    if not isinstance(value, dict) or type(value.get("schemaVersion")) is not int or value.get("schemaVersion") not in {1, 2}:
        _fail("skill_lifecycle_v2_evidence_invalid")
    version = value["schemaVersion"]
    allowed = {"schemaVersion", "requirements", "enforcement"}
    if set(value) - allowed or not {"schemaVersion", "requirements"} <= set(value) or version == 2 and set(value) != allowed:
        _fail("skill_lifecycle_v2_evidence_invalid")
    requirements = value.get("requirements")
    if not isinstance(requirements, list) or not 1 <= len(requirements) <= 20:
        _fail("skill_lifecycle_v2_evidence_invalid")
    normalized, seen = [], set()
    for source in requirements:
        kind = source.get("type") if isinstance(source, dict) else None
        fields = {"id", "type", "tool", "minCount"} | ({"artifactKind"} if kind == "artifact" else set())
        _exact(source, fields, "skill_lifecycle_v2_evidence_invalid")
        if (not _TOKEN.fullmatch(str(source.get("id") or "")) or source["id"] in seen
                or not _TOKEN.fullmatch(str(source.get("tool") or ""))
                or kind not in {"tool_execution", "artifact"}
                or type(source.get("minCount")) is not int or not 1 <= source["minCount"] <= 100
                or kind == "artifact" and (source.get("artifactKind") != "file" or source["tool"] != "write_file")):
            _fail("skill_lifecycle_v2_evidence_invalid")
        seen.add(source["id"])
        normalized.append({key: source[key] for key in ("id", "type", "tool", "minCount", "artifactKind") if key in source})
    result = {"schemaVersion": version, "requirements": normalized}
    if "enforcement" in value:
        policy = value["enforcement"]
        if not isinstance(policy, dict) or type(policy.get("schemaVersion")) is not int:
            _fail("skill_lifecycle_v2_evidence_invalid")
        if version == 1:
            _exact(policy, {"schemaVersion", "mode"}, "skill_lifecycle_v2_evidence_invalid")
            if policy != {"schemaVersion": 1, "mode": "explicit_only"}:
                _fail("skill_lifecycle_v2_evidence_invalid")
        else:
            _exact(policy, {"schemaVersion", "mode", "activationKinds"}, "skill_lifecycle_v2_evidence_invalid")
            kinds = policy.get("activationKinds")
            if (policy.get("schemaVersion") != 2 or policy.get("mode") != "owner_completion_once"
                    or not isinstance(kinds, list) or not kinds or kinds != sorted(set(kinds))
                    or any(item not in {"automatic", "explicit"} for item in kinds)):
                _fail("skill_lifecycle_v2_evidence_invalid")
        result["enforcement"] = policy
    return _clone(result, MAX_EVIDENCE_CONTRACT_BYTES)


def _dependency(value, skill):
    if not isinstance(value, dict) or value.get("state") not in {"missing", "ready"}:
        _fail("skill_lifecycle_v2_dependency_invalid")
    if value["state"] == "missing":
        _exact(value, {"state", "capabilities"}, "skill_lifecycle_v2_dependency_invalid")
        if value["capabilities"] != []:
            _fail("skill_lifecycle_v2_dependency_invalid")
        return {"state": "missing", "capabilities": []}
    _exact(value, {"state", "manifestHash", "capabilities", "manifest"}, "skill_lifecycle_v2_dependency_invalid")
    manifest = _clone(value["manifest"], MAX_DEPENDENCY_CONTRACT_BYTES)
    try:
        raw_capabilities = {
            item["id"]: {"required": item["required"], "optional": item["optional"]}
            for item in manifest["capabilities"]
        }
        normalized = skill_dependencies.normalize_manifest(
            {"schemaVersion": manifest["schemaVersion"], "skill": manifest["skill"],
             "capabilities": raw_capabilities},
            expected_skill=skill,
        )
    except (KeyError, TypeError, skill_dependencies.DependencyManifestError) as exc:
        raise SkillLifecycleV2Error("skill_lifecycle_v2_dependency_invalid") from exc
    for capability in normalized["capabilities"]:
        for requirement in capability["required"] + capability["optional"]:
            requirement.pop("installHint", None)
    if manifest != normalized:
        _fail("skill_lifecycle_v2_dependency_invalid")
    capabilities = [item["id"] for item in normalized["capabilities"]]
    if value["capabilities"] != sorted(set(capabilities)):
        _fail("skill_lifecycle_v2_dependency_invalid")
    return {"state": "ready", "manifestHash": _hash(value["manifestHash"]), "capabilities": value["capabilities"], "manifest": normalized}


def normalize_resource_contract(value, *, expected_skill):
    _exact(value, {"schemaVersion", "skill", "resources"}, "skill_lifecycle_v2_resources_invalid")
    if type(value.get("schemaVersion")) is not int or value.get("schemaVersion") != 1 or value.get("skill") != expected_skill:
        _fail("skill_lifecycle_v2_resources_invalid")
    resources, ids, paths = [], set(), set()
    for source in value.get("resources") if isinstance(value.get("resources"), list) else ():
        _exact(source, {"id", "path", "sha256", "kind", "protocol", "modelVisible", "arguments"}, "skill_lifecycle_v2_resources_invalid")
        path = _relative(source["path"], allow_skill=True)
        arguments = source["arguments"]
        if (not all(isinstance(source[key], str) for key in ("id", "sha256", "kind", "protocol"))
                or not _RESOURCE_ID.fullmatch(source["id"]) or source["id"] in ids or path.casefold() in paths
                or not re.fullmatch(r"[0-9a-f]{64}", source["sha256"])
                or source["kind"] not in _RESOURCE_KIND or not _PROTOCOL.fullmatch(source["protocol"])
                or type(source["modelVisible"]) is not bool or not isinstance(arguments, list) or len(arguments) > 16
                or any(not isinstance(item, str) or len(item) > 256 or item.startswith(("/", "\\\\"))
                       or re.match(r"^[A-Za-z]:[\\/]", item) for item in arguments)):
            _fail("skill_lifecycle_v2_resources_invalid")
        ids.add(source["id"]); paths.add(path.casefold())
        resources.append({**source, "path": path, "arguments": list(arguments)})
    if not resources or not any(item["modelVisible"] for item in resources):
        _fail("skill_lifecycle_v2_resources_invalid")
    return _clone({"schemaVersion": 1, "skill": expected_skill, "resources": resources}, MAX_RESOURCE_CONTRACT_BYTES)


def _component(value, skill, kind):
    if kind == "dependency":
        return _dependency(value, skill)
    states = {"missing", "invalid", "ready"} if kind == "evidence" else {"missing", "ready"}
    if not isinstance(value, dict) or value.get("state") not in states:
        _fail(f"skill_lifecycle_v2_{kind}_invalid")
    if value["state"] == "missing":
        _exact(value, {"state"}, f"skill_lifecycle_v2_{kind}_invalid")
        return {"state": "missing"}
    if value["state"] == "invalid":
        _exact(value, {"state", "contentHash"}, f"skill_lifecycle_v2_{kind}_invalid")
        return {"state": "invalid", "contentHash": _hash(value["contentHash"])}
    hash_key = "contentHash" if kind == "evidence" else "contractHash"
    _exact(value, {"state", hash_key, "contract"}, f"skill_lifecycle_v2_{kind}_invalid")
    contract = normalize_evidence_contract(value["contract"]) if kind == "evidence" else normalize_resource_contract(value["contract"], expected_skill=skill)
    return {"state": "ready", hash_key: _hash(value[hash_key]), "contract": contract}


def normalize_skill_lifecycle(value):
    _exact(value, {"schemaVersion", "mode", "activation", "access"})
    if type(value.get("schemaVersion")) is not int or value.get("schemaVersion") != 2 or value.get("mode") != LIFECYCLE_MODE:
        _fail("skill_lifecycle_v2_version_unsupported")
    activation = value["activation"]
    _exact(activation, {"schemaVersion", "intentKind", "outcome", "registry", "selected"})
    if type(activation.get("schemaVersion")) is not int or activation.get("schemaVersion") != 2 or activation.get("intentKind") not in {"explicit", "automatic"} or activation.get("outcome") not in {"activated", "none"}:
        _fail("skill_lifecycle_v2_activation_invalid")
    registry = activation["registry"]
    _exact(registry, {"schema", "dataRootId", "generation", "registryHash"})
    if (registry.get("schema") != "code-skill-install-registry/v1" or not _ROOT_ID.fullmatch(str(registry.get("dataRootId")))
            or type(registry.get("generation")) is not int or not 0 <= registry["generation"] <= 2**53 - 1):
        _fail("skill_lifecycle_v2_registry_invalid")
    registry = {**registry, "registryHash": _hash(registry.get("registryHash"))}
    source = activation["selected"]
    if not isinstance(source, list) or len(source) > MAX_SELECTED_SKILLS:
        _fail("skill_lifecycle_v2_selected_invalid")
    selected, names, aliases, installations, skill_ids = [], set(), set(), set(), set()
    fields = {"name", "routingAlias", "displayName", "role", "skillId", "installationId", "revisionId", "skillContentHash", "evidence", "dependency", "resources"}
    for index, item in enumerate(source):
        _exact(item, fields, "skill_lifecycle_v2_selected_invalid")
        name, alias, display = item.get("name"), item.get("routingAlias"), item.get("displayName")
        identity = (item.get("installationId"), item.get("revisionId"))
        if (not isinstance(name, str) or not isinstance(alias, str) or not _NAME.fullmatch(name) or not _NAME.fullmatch(alias)
                or name.casefold() in names or alias.casefold() in aliases
                or item.get("role") != ("owner" if index == 0 else "modifier") or not _SKILL_ID.fullmatch(str(item.get("skillId")))
                or not _INSTALL_ID.fullmatch(str(identity[0])) or identity[0] in installations or item.get("skillId") in skill_ids
                or not _HASH.fullmatch(str(identity[1]))
                or not isinstance(display, str) or not display or unicodedata.normalize("NFC", display) != display
                or len(display.encode()) > 256 or any(ord(char) < 0x20 for char in display)):
            _fail("skill_lifecycle_v2_selected_invalid")
        names.add(name.casefold()); aliases.add(alias.casefold()); installations.add(identity[0]); skill_ids.add(item["skillId"])
        selected.append({**{key: item[key] for key in fields - {"evidence", "dependency", "resources", "skillContentHash"}},
                         "skillContentHash": _hash(item["skillContentHash"]),
                         "evidence": _component(item["evidence"], name, "evidence"),
                         "dependency": _component(item["dependency"], name, "dependency"),
                         "resources": _component(item["resources"], name, "resources")})
    if (activation["outcome"] == "none") != (not selected) or activation["intentKind"] == "explicit" and len(selected) != 1:
        _fail("skill_lifecycle_v2_activation_invalid")
    access = value["access"]
    _exact(access, {"schemaVersion", "resourceBindings"})
    if type(access.get("schemaVersion")) is not int or access.get("schemaVersion") != 3 or not isinstance(access.get("resourceBindings"), list) or len(access["resourceBindings"]) > MAX_RESOURCE_BINDINGS:
        _fail("skill_lifecycle_v2_access_invalid")
    allowed = {(item["installationId"], item["revisionId"]) for item in selected}
    bindings, keys = [], set()
    for source_binding in access["resourceBindings"]:
        _exact(source_binding, {"kind", "installationId", "revisionId", "file", "contentHash"}, "skill_lifecycle_v2_access_invalid")
        identity = (source_binding.get("installationId"), source_binding.get("revisionId"))
        file = _relative(source_binding.get("file"))
        key = (identity[0], file.casefold())
        if source_binding.get("kind") != "text" or identity not in allowed or key in keys:
            _fail("skill_lifecycle_v2_access_invalid")
        keys.add(key)
        bindings.append({**source_binding, "file": file, "contentHash": _hash(source_binding.get("contentHash"))})
    if bindings != sorted(bindings, key=lambda item: (item["installationId"], item["file"].casefold())):
        _fail("skill_lifecycle_v2_access_invalid")
    return _clone({"schemaVersion": 2, "mode": LIFECYCLE_MODE,
                   "activation": {**activation, "registry": registry, "selected": selected},
                   "access": {"schemaVersion": 3, "resourceBindings": bindings}}, MAX_LIFECYCLE_BYTES)


def build_skill_lifecycle(admission):
    if not isinstance(admission, dict) or not {"intentKind", "registry", "captures"} <= set(admission):
        _fail("skill_lifecycle_v2_admission_invalid")
    captures = admission.get("captures")
    if not isinstance(captures, list) or len(captures) > MAX_SELECTED_SKILLS:
        _fail("skill_lifecycle_v2_admission_invalid")
    selected = []
    capture_fields = ("name", "routingAlias", "displayName", "skillId", "installationId",
                      "revisionId", "skillContentHash", "evidence", "dependency", "resources")
    for index, capture in enumerate(captures):
        if not isinstance(capture, dict) or not set(capture_fields) <= set(capture):
            _fail("skill_lifecycle_v2_admission_invalid")
        selected.append({key: capture[key] for key in capture_fields}
                        | {"role": "owner" if index == 0 else "modifier"})
    return normalize_skill_lifecycle({"schemaVersion": 2, "mode": LIFECYCLE_MODE,
        "activation": {"schemaVersion": 2, "intentKind": admission.get("intentKind"),
                       "outcome": "activated" if selected else "none", "registry": admission.get("registry"), "selected": selected},
        "access": {"schemaVersion": 3, "resourceBindings": []}})


def project_skill_lifecycle(value):
    lifecycle = normalize_skill_lifecycle(value)
    selected = lifecycle["activation"]["selected"]
    return {"activeSkillNames": [item["name"] for item in selected],
            "dependencies": {item["name"]: item["dependency"].get("capabilities", []) for item in selected},
            "captures": [{"name": item["name"], "contentHash": item["skillContentHash"],
                          "evidenceState": item["evidence"]["state"],
                          "evidence": item["evidence"].get("contract") if item["evidence"]["state"] == "ready" else {} if item["evidence"]["state"] == "invalid" else None}
                         for item in selected],
            "explicit": lifecycle["activation"]["intentKind"] == "explicit"}


def require_active_skill(value, name):
    lifecycle = normalize_skill_lifecycle(value)
    requested = str(name or "").strip()
    for selected in lifecycle["activation"]["selected"]:
        if selected["name"] == requested:
            return _clone(selected, MAX_LIFECYCLE_BYTES)
    _fail("skill_lifecycle_v2_skill_not_active")


def normalize_text_resource_path(value):
    return _relative(value)


def bind_text_resource(value, installation_id, revision_id, file, content_hash):
    lifecycle = normalize_skill_lifecycle(value)
    bindings = list(lifecycle["access"]["resourceBindings"])
    candidate = {"kind": "text", "installationId": installation_id, "revisionId": revision_id,
                 "file": _relative(file), "contentHash": _hash(content_hash)}
    for current in bindings:
        if current["installationId"] == installation_id and current["file"].casefold() == candidate["file"].casefold():
            if current != candidate:
                _fail("skill_lifecycle_v2_access_conflict")
            return lifecycle
    bindings.append(candidate)
    lifecycle["access"]["resourceBindings"] = sorted(bindings, key=lambda item: (item["installationId"], item["file"].casefold()))
    return normalize_skill_lifecycle(lifecycle)
