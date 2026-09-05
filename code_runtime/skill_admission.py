"""Revision-backed immutable Skill admission with only injected readers."""
from __future__ import annotations

import hashlib
import json

from . import skill_activation as activation
from . import skill_dependencies
from . import skill_lifecycle_v2 as lifecycle_v2
from . import skill_registry as registry_api
from . import skill_resources


class SkillAdmissionError(ValueError):
    def __init__(self, code, message="Immutable Skill admission failed"):
        self.code = str(code)
        super().__init__(message)


def _fail(code):
    raise SkillAdmissionError(code)


def _files(selection):
    return {item["path"]: item for item in selection["object"]["files"]}


def _json_sidecar(selection, filename, maximum):
    item = _files(selection).get(filename)
    if item is None:
        return None
    raw = item["content"]
    if len(raw) > maximum:
        _fail("immutable_sidecar_too_large")
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SkillAdmissionError("immutable_sidecar_invalid") from exc
    if not isinstance(value, dict):
        _fail("immutable_sidecar_invalid")
    return item, value


def _descriptor(selection):
    alias = selection["routingAlias"]
    descriptor = registry_api._empty_descriptor("installed", alias)
    skill = _files(selection).get("SKILL.md")
    body = ""
    try:
        if skill is None or len(skill["content"]) > registry_api.MAX_SKILL_BYTES:
            _fail("immutable_skill_invalid")
        descriptor["contentHash"] = skill["digest"]
        parsed = registry_api.parse_skill_document(skill["content"].decode("utf-8-sig"))
        meta, body = parsed["meta"], parsed["body"]
        name, description = meta.get("name"), meta.get("description")
        if not isinstance(name, str) or not registry_api.SAFE_NAME_RE.fullmatch(name.strip()):
            _fail("immutable_skill_invalid")
        if not isinstance(description, str) or not description.strip():
            _fail("immutable_skill_invalid")
        descriptor["name"] = name.strip()
        descriptor["description"] = " ".join(description.strip().split())[:4000]
        metadata = {} if meta.get("metadata") is None else meta.get("metadata")
        if not isinstance(metadata, dict):
            _fail("immutable_skill_invalid")
        version = metadata.get("version") if isinstance(metadata.get("version"), str) else meta.get("version")
        if version not in (None, ""):
            if isinstance(version, bool) or not isinstance(version, (str, int, float)):
                _fail("immutable_skill_invalid")
            descriptor["version"] = str(version).strip()[:128]
        allowed, source = [], "none"
        if "allowed-tools" in meta:
            _, allowed, shape, standard = registry_api._normalize_allowed_tools(meta.get("allowed-tools"))
            source = "allowed-tools" if standard else f"legacy-allowed-tools-{shape.removeprefix('legacy-')}"
        elif "tools" in meta:
            allowed, source = registry_api._normalize_terms(meta.get("tools"), kind="allowed_tools"), "legacy-tools"
        elif "tools" in metadata:
            allowed, source = registry_api._normalize_terms(metadata.get("tools"), kind="allowed_tools"), "legacy-metadata-tools"
        descriptor["allowedTools"] = allowed
        descriptor["toolPolicy"] = {"mode": "narrow-only" if source.startswith(("allowed-tools", "legacy-allowed-tools")) else "preference-only" if source.startswith("legacy") else "none", "source": source}
        keywords = meta.get("keywords", metadata.get("keywords"))
        descriptor["routingKeywords"] = registry_api._normalize_terms(keywords, kind="keywords") if keywords is not None else []
        descriptor["bodyLoaded"] = bool(body)
        descriptor["bodyHash"] = registry_api._sha256_bytes(body.encode()) if body else ""
        if not body:
            _fail("immutable_skill_invalid")
        sidecars = {}
        for key, filename in registry_api.SIDECARS:
            captured = _json_sidecar(selection, filename, registry_api.MAX_SIDECAR_BYTES)
            if captured is None:
                sidecars[key] = {"state": "missing"}
                continue
            item, payload = captured
            state = "ready" if payload.get("skill") in (None, "", descriptor["name"]) else "invalid"
            sidecars[key] = {"state": state, "contentHash": item["digest"]}
            if state != "ready":
                _fail("immutable_sidecar_invalid")
        descriptor["sidecars"] = sidecars
    except (UnicodeError, registry_api.SkillRegistryError, SkillAdmissionError) as exc:
        descriptor["diagnostics"].append(registry_api._diagnostic(getattr(exc, "code", "immutable_skill_invalid")))
    registry_api._finalize_descriptor(descriptor)
    return descriptor, body


def _evidence(selection, skill_name):
    captured = _json_sidecar(selection, "evidence.json", activation.MAX_EVIDENCE_BYTES)
    if captured is None:
        return {"state": "missing"}
    item, payload = captured
    if payload.get("skill") not in (None, "", skill_name):
        return {"state": "invalid", "contentHash": item["digest"]}
    try:
        contract = lifecycle_v2.normalize_evidence_contract(payload)
    except lifecycle_v2.SkillLifecycleV2Error:
        return {"state": "invalid", "contentHash": item["digest"]}
    return {"state": "ready", "contentHash": item["digest"], "contract": contract}


def _dependency(selection, skill_name):
    captured = _json_sidecar(selection, "dependencies.json", 128 * 1024)
    if captured is None:
        return {"state": "missing", "capabilities": []}
    item, payload = captured
    try:
        manifest = skill_dependencies.normalize_manifest(payload, expected_skill=skill_name)
    except skill_dependencies.DependencyManifestError as exc:
        raise SkillAdmissionError("immutable_dependencies_invalid") from exc
    for capability in manifest["capabilities"]:
        for requirement in capability["required"] + capability["optional"]:
            requirement.pop("installHint", None)
    capabilities = sorted(item["id"] for item in manifest["capabilities"])
    return {"state": "ready", "manifestHash": item["digest"], "capabilities": capabilities, "manifest": manifest}


def _resources(selection, skill_name):
    captured = _json_sidecar(selection, skill_resources.RESOURCE_MANIFEST_NAME, skill_resources.MAX_RESOURCE_MANIFEST_BYTES)
    if captured is None:
        if skill_name in skill_resources.REQUIRED_RESOURCE_CONTRACTS:
            _fail("immutable_resources_invalid")
        return {"state": "missing"}
    item, payload = captured
    if set(payload) - {"schemaVersion", "skill", "compatibleInstalled", "resources"}:
        _fail("immutable_resources_invalid")
    compatible = payload.get("compatibleInstalled")
    if compatible is not None:
        if not isinstance(compatible, dict) or set(compatible) != {"skillMdSha256", "dependenciesSha256"}:
            _fail("immutable_resources_invalid")
        try:
            skill_resources._normalized_hash_list(compatible["skillMdSha256"], "skillMdSha256")
            skill_resources._normalized_hash_list(compatible["dependenciesSha256"], "dependenciesSha256")
        except skill_resources.SkillResourceError as exc:
            raise SkillAdmissionError("immutable_resources_invalid") from exc
    raw_resources = payload.get("resources")
    if not isinstance(raw_resources, list):
        _fail("immutable_resources_invalid")
    fields = ("id", "path", "sha256", "kind", "protocol", "modelVisible", "arguments")
    normalized = {"schemaVersion": payload.get("schemaVersion"), "skill": payload.get("skill"),
                  "resources": [{key: source.get(key) for key in fields} for source in raw_resources if isinstance(source, dict)]}
    if len(normalized["resources"]) != len(raw_resources):
        _fail("immutable_resources_invalid")
    try:
        contract = lifecycle_v2.normalize_resource_contract(normalized, expected_skill=skill_name)
    except lifecycle_v2.SkillLifecycleV2Error as exc:
        raise SkillAdmissionError("immutable_resources_invalid") from exc
    files = _files(selection)
    for resource in contract["resources"]:
        resource_file = files.get(resource["path"])
        if (resource_file is None or len(resource_file["content"]) > skill_resources.MAX_EXECUTABLE_RESOURCE_BYTES
                or resource_file["digest"] != "sha256:" + resource["sha256"]):
            _fail("immutable_resources_invalid")
    return {"state": "ready", "contractHash": item["digest"], "contract": contract}


def _capture(reader, selection, descriptor, body):
    name = descriptor["name"]
    installation = selection["installation"]
    dependency = _dependency(selection, name)
    capture = {
        "name": name,
        "routingAlias": selection["routingAlias"],
        "displayName": installation["displayName"],
        "skillId": installation["skillId"],
        "installationId": installation["installationId"],
        "revisionId": installation["revisionId"],
        "skillContentHash": descriptor["contentHash"],
        "body": body,
        "evidence": _evidence(selection, name),
        "dependency": dependency,
        "dependencyCapabilities": dependency["capabilities"],
        "resources": _resources(selection, name),
        "descriptor": descriptor,
    }
    if reader.read_active(selection["routingAlias"]) != selection:
        _fail("immutable_capture_changed")
    return capture


def prepare_immutable_admission(*, reader, messages, user_message, request,
                                initial_tool_names, available_input_tokens, estimate_tokens):
    """Resolve and capture at most owner+modifier from verified object bytes."""
    intent = activation.normalize_activation_request(request)
    registry = reader.read_registry()
    registry_bytes = json.dumps(registry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if len(registry["bindings"]) > activation.MAX_REGISTRY_ENTRIES or len(registry_bytes) > activation.MAX_REGISTRY_METADATA_BYTES:
        _fail("immutable_registry_too_large")
    descriptors, records = [], {}
    for binding in registry["bindings"]:
        if binding["state"] != "ready":
            continue
        selection = reader.read_active(binding["routingAlias"])
        descriptor, body = _descriptor(selection)
        descriptors.append(descriptor)
        records[descriptor["descriptorId"]] = (selection, descriptor, body)
    by_name = {}
    for descriptor in descriptors:
        if descriptor["executableCandidate"]:
            by_name.setdefault(descriptor["name"], []).append(descriptor)
    for group in by_name.values():
        if len(group) > 1:
            for descriptor in group:
                registry_api._add_descriptor_diagnostic(descriptor, "active_name_conflict")
    snapshot = {"schema": registry_api.REGISTRY_SCHEMA, "registryHash": registry["registryHash"], "descriptors": descriptors}
    try:
        resolution = registry_api.resolve_skill_shadow(snapshot, str(user_message or ""),
            explicit_skill=intent["explicitSkill"], disabled_names=intent["disabledNames"])
    except registry_api.SkillRegistryError as exc:
        raise SkillAdmissionError("immutable_resolution_failed") from exc
    owner = resolution.get("owner")
    if intent["explicitSkill"] and not owner:
        _fail("immutable_explicit_skill_unavailable")
    candidates = ([owner] if owner else []) + list(resolution.get("modifiers") or [])
    captures, exclusions = [], []
    token_limit = min(activation.MAX_INSTRUCTION_TOKENS, max(0, int(available_input_tokens or 0) // 4))
    for index, candidate in enumerate(candidates[:activation.MAX_SELECTED_SKILLS]):
        try:
            record = records.get(candidate.get("descriptorId"))
            if record is None:
                _fail("immutable_skill_unavailable")
            capture = _capture(reader, *record)
            if len(capture["body"].encode()) > activation.MAX_BODY_BYTES or estimate_tokens(capture["body"]) > activation.MAX_BODY_TOKENS:
                _fail("immutable_body_too_large")
            proposed = [*captures, capture]
            instruction = activation._instruction(proposed, explicit=bool(intent["explicitSkill"]))
            if len(instruction.encode()) > activation.MAX_INSTRUCTION_BYTES or estimate_tokens(instruction) > token_limit:
                _fail("immutable_instruction_too_large")
            captures = proposed
        except SkillAdmissionError as exc:
            if index == 0:
                raise
            exclusions.append({"name": str(candidate.get("name") or ""), "reasonCode": exc.code})
    tools = list(dict.fromkeys(str(name or "").strip() for name in initial_tool_names or [] if str(name or "").strip()))
    for capture in captures:
        tools = registry_api.project_skill_tools(capture["descriptor"], tools)["allowed"]
    if captures and "task" in tools and not activation._DELEGATION_REQUEST_RE.search(str(user_message or "")) and not any("task" in capture["descriptor"].get("allowedTools", []) for capture in captures):
        tools.remove("task")
    for capture in captures:
        evidence = capture["evidence"]
        if evidence["state"] == "ready" and any(item["tool"] not in tools for item in evidence["contract"]["requirements"]):
            capture["evidence"] = {"state": "invalid", "contentHash": evidence["contentHash"]}
    instruction = activation._instruction(captures, explicit=bool(intent["explicitSkill"]))
    public_captures = []
    for index, capture in enumerate(captures):
        public_captures.append({key: value for key, value in capture.items() if key not in {"descriptor", "dependencyCapabilities"}} | {"role": "owner" if index == 0 else "modifier"})
    if reader.read_registry() != registry:
        _fail("immutable_registry_changed")
    return {"intentKind": "explicit" if intent["explicitSkill"] else "automatic",
            "registry": {key: registry[key] for key in ("schema", "dataRootId", "generation", "registryHash")},
            "captures": public_captures, "activeSkillNames": [item["name"] for item in public_captures],
            "allowedTools": tools, "instruction": instruction, "exclusions": exclusions,
            "resolutionHash": resolution["resolutionHash"]}
