"""Exact-revision runtime contracts for immutable Skill lifecycle/v2."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re

from . import skill_dependencies
from . import skill_lifecycle_v2 as lifecycle_v2


RUNTIME_BINDINGS_VERSION = 2
DEPENDENCIES_VERSION = 2
EVIDENCE_VERSION = 2
EXECUTION_CONTEXT_VERSION = 1
PATH_BINDING_VERSION = 1

_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CAPABILITY = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
_BASE_AUTHORITY_FIELDS = {
    "name", "role", "skillId", "installationId", "revisionId", "skillContentHash",
}


class ImmutableSkillRuntimeError(RuntimeError):
    def __init__(self, code, message="Immutable Skill revision is unavailable", *, temporary=False):
        self.code = str(code)
        self.temporary = bool(temporary)
        super().__init__(message)


def _fail(code, message="Immutable Skill runtime contract is invalid", *, temporary=False):
    raise ImmutableSkillRuntimeError(code, message, temporary=temporary)


def _clone(value):
    try:
        return json.loads(json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ))
    except (TypeError, ValueError) as exc:
        raise ImmutableSkillRuntimeError("skill_runtime_v2_json_invalid") from exc


def is_immutable(lifecycle):
    return isinstance(lifecycle, dict) and lifecycle.get("schemaVersion") == 2


def authority_from_selected(selected, *, evidence=False):
    authority = {key: selected[key] for key in _BASE_AUTHORITY_FIELDS}
    if evidence:
        content_hash = (selected.get("evidence") or {}).get("contentHash")
        if content_hash:
            authority["evidenceContentHash"] = content_hash
    return authority


def _selected_by_authority(lifecycle, authority, *, allow_evidence=False):
    allowed = set(_BASE_AUTHORITY_FIELDS)
    if allow_evidence and "evidenceContentHash" in authority:
        allowed.add("evidenceContentHash")
    if not isinstance(authority, dict) or set(authority) != allowed:
        _fail("skill_runtime_v2_authority_invalid")
    normalized = lifecycle_v2.normalize_skill_lifecycle(lifecycle)
    for selected in normalized["activation"]["selected"]:
        expected = authority_from_selected(selected, evidence=allow_evidence)
        if authority == expected:
            return selected
    _fail("skill_runtime_v2_authority_conflict")


def _reader_snapshot(reader, lifecycle, selected):
    if reader is None or not callable(getattr(reader, "read_runtime", None)):
        _fail("skill_revision_unavailable", temporary=True)
    root_id = lifecycle["activation"]["registry"]["dataRootId"]
    try:
        snapshot = reader.read_runtime(root_id, selected["revisionId"])
    except Exception as exc:
        raise ImmutableSkillRuntimeError(
            "skill_revision_unavailable", temporary=True,
        ) from exc
    if (
        snapshot.get("dataRootId") != root_id
        or snapshot.get("revisionId") != selected["revisionId"]
    ):
        _fail("skill_revision_unavailable", temporary=True)
    files = {item["path"]: item for item in snapshot.get("files") or [] if isinstance(item, dict)}
    skill = files.get("SKILL.md")
    if not skill or skill.get("digest") != selected["skillContentHash"]:
        _fail("skill_revision_unavailable", temporary=True)
    expected_sidecars = (
        ("evidence", "evidence.json", "contentHash"),
        ("dependency", "dependencies.json", "manifestHash"),
        ("resources", "code-resources.json", "contractHash"),
    )
    for component_name, filename, hash_key in expected_sidecars:
        component = selected[component_name]
        item = files.get(filename)
        if component.get("state") == "missing":
            if item is not None:
                _fail("skill_revision_contract_conflict")
            continue
        if component.get("state") in {"ready", "invalid"}:
            if not item or item.get("digest") != component.get(hash_key):
                _fail("skill_revision_unavailable", temporary=True)
        try:
            payload = json.loads(item["content"].decode("utf-8-sig"))
        except (KeyError, UnicodeError, json.JSONDecodeError) as exc:
            if component.get("state") == "invalid" and component_name == "evidence":
                continue
            raise ImmutableSkillRuntimeError("skill_revision_contract_conflict") from exc
        if component.get("state") == "invalid":
            # Admission may deliberately downgrade a structurally valid evidence
            # contract when its required tools were removed by the Skill policy.
            continue
        if component_name == "evidence":
            actual = lifecycle_v2.normalize_evidence_contract(payload)
            if actual != component.get("contract"):
                _fail("skill_revision_contract_conflict")
        elif component_name == "dependency":
            try:
                actual = skill_dependencies.normalize_manifest(
                    payload, expected_skill=selected["name"],
                )
            except skill_dependencies.DependencyManifestError as exc:
                raise ImmutableSkillRuntimeError("skill_revision_contract_conflict") from exc
            for capability in actual["capabilities"]:
                for requirement in capability["required"] + capability["optional"]:
                    requirement.pop("installHint", None)
            if actual != component.get("manifest"):
                _fail("skill_revision_contract_conflict")
        else:
            fields = ("id", "path", "sha256", "kind", "protocol", "modelVisible", "arguments")
            sources = payload.get("resources") if isinstance(payload, dict) else None
            if not isinstance(sources, list) or any(not isinstance(source, dict) for source in sources):
                _fail("skill_revision_contract_conflict")
            normalized_payload = {
                "schemaVersion": payload.get("schemaVersion"),
                "skill": payload.get("skill"),
                "resources": [
                    {key: source.get(key) for key in fields} for source in sources
                ],
            }
            try:
                actual = lifecycle_v2.normalize_resource_contract(
                    normalized_payload, expected_skill=selected["name"],
                )
            except lifecycle_v2.SkillLifecycleV2Error as exc:
                raise ImmutableSkillRuntimeError("skill_revision_contract_conflict") from exc
            if actual != component.get("contract"):
                _fail("skill_revision_contract_conflict")
    return {"selected": selected, "object": snapshot, "files": files}


def verify_lifecycle(reader, lifecycle):
    normalized = lifecycle_v2.normalize_skill_lifecycle(lifecycle)
    if reader is None or not callable(getattr(reader, "verify_root", None)):
        _fail("skill_revision_unavailable", temporary=True)
    try:
        root = reader.verify_root(
            normalized["activation"]["registry"]["dataRootId"]
        )
    except Exception as exc:
        raise ImmutableSkillRuntimeError(
            "skill_revision_unavailable", temporary=True,
        ) from exc
    if root.get("dataRootId") != normalized["activation"]["registry"]["dataRootId"]:
        _fail("skill_revision_unavailable", temporary=True)
    snapshots = {}
    for selected in normalized["activation"]["selected"]:
        snapshots[(selected["installationId"], selected["revisionId"])] = _reader_snapshot(
            reader, normalized, selected,
        )
    for binding in normalized["access"]["resourceBindings"]:
        snapshot = snapshots.get((binding["installationId"], binding["revisionId"]))
        item = (snapshot or {}).get("files", {}).get(binding["file"])
        if item is None or item.get("digest") != binding["contentHash"]:
            _fail("skill_revision_contract_conflict")
    return normalized


def skill_snapshot(reader, lifecycle, name):
    normalized = lifecycle_v2.normalize_skill_lifecycle(lifecycle)
    selected = lifecycle_v2.require_active_skill(normalized, name)
    return _reader_snapshot(reader, normalized, selected)


def build_dependencies(lifecycle):
    normalized = lifecycle_v2.normalize_skill_lifecycle(lifecycle)
    skills = []
    for selected in normalized["activation"]["selected"]:
        dependency = selected["dependency"]
        item = {
            "authority": authority_from_selected(selected),
            "state": dependency["state"],
            "capabilities": list(dependency.get("capabilities") or []),
        }
        if dependency["state"] == "ready":
            item["manifestHash"] = dependency["manifestHash"]
        skills.append(item)
    return {"version": DEPENDENCIES_VERSION, "skills": skills}


def normalize_dependencies(value, lifecycle):
    expected = build_dependencies(lifecycle)
    if value != expected or type(value.get("version")) is not int:
        _fail("skill_runtime_v2_dependencies_conflict")
    return _clone(expected)


def build_evidence(lifecycle):
    normalized = lifecycle_v2.normalize_skill_lifecycle(lifecycle)
    activation_mode = normalized["activation"]["intentKind"]
    skills = []
    for selected in normalized["activation"]["selected"]:
        evidence = selected["evidence"]
        state = evidence["state"]
        item = {
            "authority": authority_from_selected(selected, evidence=True),
            "activationMode": activation_mode,
            "contractState": "valid" if state == "ready" else state,
        }
        if state == "ready":
            item["contract"] = _clone(evidence["contract"])
        else:
            item["diagnosticCode"] = "contract_missing" if state == "missing" else "invalid_contract"
        skills.append(item)
    return {"version": EVIDENCE_VERSION, "skills": skills}


def normalize_evidence(value, lifecycle):
    expected = build_evidence(lifecycle)
    if value != expected or type(value.get("version")) is not int:
        _fail("skill_runtime_v2_evidence_conflict")
    return _clone(expected)


def _normalize_runtime(value):
    if not isinstance(value, dict) or set(value) - {"python", "node"}:
        _fail("skill_runtime_v2_binding_invalid")
    result = {}
    for key, path_key in (("python", "executable"), ("node", "nodePath")):
        source = value.get(key)
        if source is None:
            continue
        if not isinstance(source, dict) or set(source) != {"source", path_key}:
            _fail("skill_runtime_v2_binding_invalid")
        origin, path = source.get("source"), source.get(path_key)
        if origin not in {"managed", "system", "app", "missing", ""} or not isinstance(path, str) or len(path) > 4096:
            _fail("skill_runtime_v2_binding_invalid")
        result[key] = {"source": origin, path_key: path}
    return result


def normalize_runtime_binding(value, lifecycle):
    fields = {
        "version", "authority", "capability", "checkedStatus", "manifestHash",
        "runtime", "checkedAt",
    }
    if not isinstance(value, dict) or set(value) != fields or type(value.get("version")) is not int or value.get("version") != RUNTIME_BINDINGS_VERSION:
        _fail("skill_runtime_v2_binding_invalid")
    selected = _selected_by_authority(lifecycle, value["authority"])
    dependency = selected["dependency"]
    capability = value.get("capability")
    if (
        not isinstance(capability, str) or not _CAPABILITY.fullmatch(capability)
        or value.get("checkedStatus") != "ready"
        or dependency.get("state") != "ready"
        or capability not in dependency.get("capabilities", [])
        or value.get("manifestHash") != dependency.get("manifestHash")
        or not isinstance(value.get("checkedAt"), str) or len(value["checkedAt"]) > 64
    ):
        _fail("skill_runtime_v2_binding_invalid")
    return {
        "version": RUNTIME_BINDINGS_VERSION,
        "authority": authority_from_selected(selected),
        "capability": capability,
        "checkedStatus": "ready",
        "manifestHash": dependency["manifestHash"],
        "runtime": _normalize_runtime(value["runtime"]),
        "checkedAt": value["checkedAt"],
    }


def runtime_bindings_record(bindings, lifecycle):
    normalized_lifecycle = lifecycle_v2.normalize_skill_lifecycle(lifecycle)
    result = []
    for selected in normalized_lifecycle["activation"]["selected"]:
        source = (bindings or {}).get(selected["name"])
        if source is not None:
            result.append(normalize_runtime_binding(source, normalized_lifecycle))
    return {"version": RUNTIME_BINDINGS_VERSION, "bindings": result}


def restore_runtime_bindings(value, lifecycle):
    if not isinstance(value, dict) or set(value) != {"version", "bindings"} or type(value.get("version")) is not int or value.get("version") != RUNTIME_BINDINGS_VERSION:
        _fail("skill_runtime_v2_bindings_conflict")
    sources = value.get("bindings")
    if not isinstance(sources, list) or len(sources) > lifecycle_v2.MAX_SELECTED_SKILLS:
        _fail("skill_runtime_v2_bindings_conflict")
    restored = {}
    for source in sources:
        binding = normalize_runtime_binding(source, lifecycle)
        name = binding["authority"]["name"]
        if name in restored:
            _fail("skill_runtime_v2_bindings_conflict")
        restored[name] = binding
    if runtime_bindings_record(restored, lifecycle) != value:
        _fail("skill_runtime_v2_bindings_conflict")
    return restored


def dependency_status(reader, lifecycle, name, *, app_dir, data_dir, capability=""):
    snapshot = skill_snapshot(reader, lifecycle, name)
    dependency = snapshot["selected"]["dependency"]
    if dependency["state"] == "missing":
        return {
            "name": name, "status": "undeclared", "manifestSource": "",
            "detectedFrom": [], "capabilities": [],
            "installGuidance": {
                "needed": False, "selectionRequired": False,
                "selectedCapability": "", "availableCapabilities": [],
                "requiredMissing": [], "optionalMissing": [], "steps": [],
                "runtime": {}, "instructions": "This Skill declares no external dependencies.",
            },
        }
    inspection = skill_dependencies.inspect_manifest(
        dependency["manifest"], app_dir=app_dir, data_dir=data_dir,
    )
    inspection["installGuidance"] = skill_dependencies.build_install_guidance(
        inspection, data_dir=data_dir, capability_id=capability,
    )
    return inspection


def runtime_resources(reader, lifecycle, name):
    snapshot = skill_snapshot(reader, lifecycle, name)
    selected = snapshot["selected"]
    resources = selected["resources"]
    if resources["state"] != "ready":
        return None
    public = []
    content_root = Path(snapshot["object"]["contentRoot"])
    for resource in resources["contract"]["resources"]:
        item = snapshot["files"].get(resource["path"])
        expected = "sha256:" + resource["sha256"]
        if not item or item.get("digest") != expected:
            _fail("skill_revision_unavailable", temporary=True)
        if resource["modelVisible"]:
            public.append({
                "id": resource["id"], "kind": resource["kind"],
                "protocol": resource["protocol"],
                "path": str((content_root / resource["path"]).resolve(strict=True)),
                "sha256": resource["sha256"],
                "arguments": list(resource["arguments"]),
            })
    return {
        "schemaVersion": 1, "source": "immutable",
        "resources": public,
        "instructions": (
            "Use only the exact resource path returned here with the runtime selected by "
            "check_skill_dependencies. Do not search or copy adjacent files."
        ),
    }


def text_resource(reader, lifecycle, name, file, *, maximum_bytes=None):
    snapshot = skill_snapshot(reader, lifecycle, name)
    relative = lifecycle_v2.normalize_text_resource_path(file)
    item = snapshot["files"].get(relative)
    if item is None:
        _fail("skill_revision_resource_missing")
    if maximum_bytes is not None and len(item.get("content") or b"") > int(maximum_bytes):
        _fail("skill_revision_resource_too_large")
    try:
        content = item["content"].decode("utf-8-sig")
    except UnicodeError as exc:
        raise ImmutableSkillRuntimeError("skill_revision_resource_invalid") from exc
    return relative, item["digest"], content


def _arguments(value):
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _execution_targets(lifecycle, name, arguments, bindings):
    selected = lifecycle["activation"]["selected"]
    explicit_field = {
        "use_skill": "name", "check_skill_dependencies": "name",
        "read_skill_resource": "skill",
    }.get(name)
    if explicit_field:
        target = str(arguments.get(explicit_field) or "").strip()
        return [lifecycle_v2.require_active_skill(lifecycle, target)]
    if name == "run_command":
        bound = set((bindings or {}).keys())
        targets = [item for item in selected if item["name"] in bound]
        if targets:
            return targets
        return [
            item for item in selected
            if any(req.get("tool") == name for req in ((item.get("evidence") or {}).get("contract") or {}).get("requirements", []))
        ]
    return [
        item for item in selected
        if any(req.get("tool") == name for req in ((item.get("evidence") or {}).get("contract") or {}).get("requirements", []))
    ]


def build_execution_context(reader, lifecycle, name, arguments, *, bindings=None):
    normalized = lifecycle_v2.normalize_skill_lifecycle(lifecycle)
    arguments = _arguments(arguments)
    skills = []
    for selected in _execution_targets(normalized, str(name or ""), arguments, bindings):
        snapshot = _reader_snapshot(reader, normalized, selected)
        item = authority_from_selected(selected)
        dependency = selected["dependency"]
        if str(name or "") in {"check_skill_dependencies", "run_command"} and dependency["state"] == "ready":
            capability = str(arguments.get("capability") or "") if name == "check_skill_dependencies" else str(((bindings or {}).get(selected["name"]) or {}).get("capability") or "")
            if capability:
                item.update({"capability": capability, "manifestHash": dependency["manifestHash"]})
        if name == "read_skill_resource":
            relative = lifecycle_v2.normalize_text_resource_path(arguments.get("file"))
            resource = snapshot["files"].get(relative)
            if resource is None:
                _fail("skill_revision_resource_missing")
            item["resource"] = {"file": relative, "contentHash": resource["digest"]}
        skills.append(item)
    return normalize_execution_context({
        "version": EXECUTION_CONTEXT_VERSION,
        "dataRootId": normalized["activation"]["registry"]["dataRootId"],
        "skills": skills,
    }, normalized)


def normalize_execution_context(value, lifecycle):
    normalized = lifecycle_v2.normalize_skill_lifecycle(lifecycle)
    if (
        not isinstance(value, dict) or set(value) != {"version", "dataRootId", "skills"}
        or type(value.get("version")) is not int or value.get("version") != EXECUTION_CONTEXT_VERSION
        or value.get("dataRootId") != normalized["activation"]["registry"]["dataRootId"]
        or not isinstance(value.get("skills"), list)
        or len(value["skills"]) > lifecycle_v2.MAX_SELECTED_SKILLS
    ):
        _fail("skill_execution_context_invalid")
    result, names = [], set()
    for source in value["skills"]:
        if not isinstance(source, dict):
            _fail("skill_execution_context_invalid")
        authority_fields = _BASE_AUTHORITY_FIELDS & set(source)
        if authority_fields != _BASE_AUTHORITY_FIELDS or set(source) - (_BASE_AUTHORITY_FIELDS | {"capability", "manifestHash", "resource"}):
            _fail("skill_execution_context_invalid")
        authority = {key: source[key] for key in _BASE_AUTHORITY_FIELDS}
        selected = _selected_by_authority(normalized, authority)
        if selected["name"] in names:
            _fail("skill_execution_context_invalid")
        names.add(selected["name"])
        item = authority_from_selected(selected)
        has_capability = "capability" in source or "manifestHash" in source
        if has_capability:
            if set(source) & {"capability", "manifestHash"} != {"capability", "manifestHash"}:
                _fail("skill_execution_context_invalid")
            dependency = selected["dependency"]
            if (
                dependency.get("state") != "ready"
                or source.get("manifestHash") != dependency.get("manifestHash")
                or source.get("capability") not in dependency.get("capabilities", [])
            ):
                _fail("skill_execution_context_invalid")
            item.update({"capability": source["capability"], "manifestHash": source["manifestHash"]})
        if "resource" in source:
            resource = source["resource"]
            if not isinstance(resource, dict) or set(resource) != {"file", "contentHash"} or not _HASH.fullmatch(str(resource.get("contentHash") or "")):
                _fail("skill_execution_context_invalid")
            item["resource"] = {
                "file": lifecycle_v2.normalize_text_resource_path(resource.get("file")),
                "contentHash": resource["contentHash"],
            }
        result.append(item)
    order = [item["name"] for item in normalized["activation"]["selected"]]
    if [item["name"] for item in result] != [name for name in order if name in names]:
        _fail("skill_execution_context_invalid")
    return {"version": EXECUTION_CONTEXT_VERSION, "dataRootId": value["dataRootId"], "skills": result}


def verify_execution_context(reader, lifecycle, value):
    normalized_lifecycle = lifecycle_v2.normalize_skill_lifecycle(lifecycle)
    context = normalize_execution_context(value, normalized_lifecycle)
    for source in context["skills"]:
        resource = source.get("resource")
        if resource is None:
            continue
        snapshot = skill_snapshot(reader, normalized_lifecycle, source["name"])
        item = snapshot["files"].get(resource["file"])
        if item is None or item.get("digest") != resource["contentHash"]:
            _fail("skill_execution_context_resource_conflict")
    return context


def build_command_path_binding(reader, lifecycle, context):
    normalized = lifecycle_v2.normalize_skill_lifecycle(lifecycle)
    context = normalize_execution_context(context, normalized)
    resources = []
    for authority in context["skills"]:
        selected = _selected_by_authority(normalized, {key: authority[key] for key in _BASE_AUTHORITY_FIELDS})
        contract = selected["resources"]
        if contract["state"] != "ready":
            continue
        snapshot = _reader_snapshot(reader, normalized, selected)
        content_root = Path(snapshot["object"]["contentRoot"])
        for resource in contract["contract"]["resources"]:
            if not resource["modelVisible"]:
                continue
            file = snapshot["files"].get(resource["path"])
            content_hash = "sha256:" + resource["sha256"]
            if not file or file.get("digest") != content_hash:
                _fail("skill_revision_unavailable", temporary=True)
            resources.append({
                "installationId": selected["installationId"],
                "revisionId": selected["revisionId"],
                "file": resource["path"], "contentHash": content_hash,
                "path": str((content_root / resource["path"]).resolve(strict=True)),
            })
    return {
        "version": PATH_BINDING_VERSION, "dataRootId": context["dataRootId"],
        "resources": resources,
    }


def normalize_command_path_binding(value, lifecycle):
    normalized = lifecycle_v2.normalize_skill_lifecycle(lifecycle)
    if (
        not isinstance(value, dict) or set(value) != {"version", "dataRootId", "resources"}
        or type(value.get("version")) is not int or value.get("version") != PATH_BINDING_VERSION
        or value.get("dataRootId") != normalized["activation"]["registry"]["dataRootId"]
        or not isinstance(value.get("resources"), list) or len(value["resources"]) > 64
    ):
        _fail("skill_runtime_path_binding_invalid")
    seen = set()
    for item in value["resources"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"installationId", "revisionId", "file", "contentHash", "path"}
            or not isinstance(item.get("path"), str) or not item["path"]
            or len(item["path"]) > 4096 or not Path(item["path"]).is_absolute()
            or not _HASH.fullmatch(str(item.get("contentHash") or ""))
        ):
            _fail("skill_runtime_path_binding_invalid")
        lifecycle_v2.normalize_text_resource_path(item.get("file"))
        matches = [selected for selected in normalized["activation"]["selected"] if selected["installationId"] == item.get("installationId") and selected["revisionId"] == item.get("revisionId")]
        if len(matches) != 1:
            _fail("skill_runtime_path_binding_invalid")
        key = (item["installationId"], item["file"].casefold())
        contract = matches[0]["resources"]
        expected = next((
            resource for resource in (contract.get("contract") or {}).get("resources", [])
            if resource.get("path") == item["file"] and resource.get("modelVisible") is True
        ), None)
        if (
            key in seen or contract.get("state") != "ready" or expected is None
            or item["contentHash"] != "sha256:" + expected["sha256"]
        ):
            _fail("skill_runtime_path_binding_invalid")
        seen.add(key)
    return copy.deepcopy(value)
