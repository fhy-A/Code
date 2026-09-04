"""Pure, non-authoritative Skill outcome shadow projection."""

from __future__ import annotations

import hashlib
import json
import re

from .skill_lifecycle import MAX_SELECTED_SKILLS


SCHEMA_VERSION = 2
RECEIPT_VERSION = 1
MODE = "shadow"
MAX_ACTUAL_CLAIMS = 16
COMPLETION_CONTRACT_VERSION = 2
COMPLETION_ENFORCEMENT_VERSION = 2
COMPLETION_ENFORCEMENT_MODE = "owner_completion_once"

_SAFE_NAME_RE = re.compile(r"[A-Za-z0-9_.-]{1,128}")
_SAFE_TOKEN_RE = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_SAFE_CALL_REF_RE = re.compile(r"[A-Za-z0-9_.:-]{1,200}")
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}")
_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}")
_EXPLICIT_TARGET_FIELDS = {
    "use_skill": "name",
    "check_skill_dependencies": "name",
    "read_skill_resource": "skill",
}


def _run_outcome(status):
    value = str(status or "")
    return value if value in {"completed", "failed", "cancelled"} else "active"


def _safe_call_reference(value):
    raw = str(value or "")
    if _SAFE_CALL_REF_RE.fullmatch(raw):
        return raw, True
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
    return f"call-sha256:{digest}", False


def _empty_summary():
    return {
        "selectedSkills": 0,
        "validContracts": 0,
        "missingContracts": 0,
        "invalidContracts": 0,
        "requirements": 0,
        "satisfiedRequirements": 0,
        "acceptedSucceeded": 0,
        "acceptedFailed": 0,
        "ambiguousClaims": 0,
        "rejectedClaims": 0,
        "duplicateCallReferences": 0,
        "unsafeCallReferences": 0,
        "invalidExecutionFingerprints": 0,
        "invalidRunIdentities": 0,
        "ignoredExecutions": 0,
    }


def _invalid_projection(run_outcome):
    summary = _empty_summary()
    summary["invalidContracts"] = 1
    return {
        "version": SCHEMA_VERSION,
        "mode": MODE,
        "runOutcome": run_outcome,
        "aggregateState": (
            run_outcome if run_outcome in {"failed", "cancelled"}
            else "invalid_contract"
        ),
        "skills": [],
        "summary": summary,
    }


def _normalize_requirement(source):
    if not isinstance(source, dict):
        return None
    requirement_id = source.get("id")
    requirement_type = source.get("type")
    tool = source.get("tool")
    minimum = source.get("minCount")
    if (
        not isinstance(requirement_id, str)
        or not _SAFE_TOKEN_RE.fullmatch(requirement_id)
        or requirement_type not in {"tool_execution", "artifact"}
        or not isinstance(tool, str)
        or not _SAFE_TOKEN_RE.fullmatch(tool)
        or isinstance(minimum, bool)
        or not isinstance(minimum, int)
        or not 1 <= minimum <= 100
    ):
        return None
    expected = {"id", "type", "tool", "minCount"}
    item = {
        "id": requirement_id,
        "type": requirement_type,
        "tool": tool,
        "minCount": minimum,
    }
    if requirement_type == "artifact":
        expected.add("artifactKind")
        if source.get("artifactKind") != "file" or tool != "write_file":
            return None
        item["artifactKind"] = "file"
    if set(source) != expected:
        return None
    return item


def normalize_completion_enforcement(value):
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion", "mode", "activationKinds",
    }:
        return None
    version = value.get("schemaVersion")
    kinds = value.get("activationKinds")
    if (
        isinstance(version, bool) or version != COMPLETION_ENFORCEMENT_VERSION
        or value.get("mode") != COMPLETION_ENFORCEMENT_MODE
        or not isinstance(kinds, list) or not kinds
        or kinds != sorted(set(kinds))
        or any(kind not in {"automatic", "explicit"} for kind in kinds)
    ):
        return None
    return {
        "schemaVersion": COMPLETION_ENFORCEMENT_VERSION,
        "mode": COMPLETION_ENFORCEMENT_MODE,
        "activationKinds": list(kinds),
    }


def normalize_completion_contract(value):
    version = value.get("schemaVersion") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or set(value) != {"schemaVersion", "requirements", "enforcement"}
        or isinstance(version, bool) or version != COMPLETION_CONTRACT_VERSION
    ):
        return None
    sources = value.get("requirements")
    if not isinstance(sources, list) or not sources or len(sources) > 20:
        return None
    requirements = [_normalize_requirement(item) for item in sources]
    ids = [item.get("id") for item in requirements if isinstance(item, dict)]
    enforcement = normalize_completion_enforcement(value.get("enforcement"))
    if None in requirements or len(ids) != len(set(ids)) or enforcement is None:
        return None
    return {
        "schemaVersion": COMPLETION_CONTRACT_VERSION,
        "requirements": requirements,
        "enforcement": enforcement,
    }


def _contract_requirements(evidence):
    if not isinstance(evidence, dict) or evidence.get("state") != "ready":
        return None
    contract = evidence.get("contract")
    version = contract.get("schemaVersion") if isinstance(contract, dict) else None
    if (
        not isinstance(contract, dict)
        or type(version) is not int
        or version not in {1, COMPLETION_CONTRACT_VERSION}
    ):
        return None
    if version == COMPLETION_CONTRACT_VERSION:
        normalized = normalize_completion_contract(contract)
        return normalized["requirements"] if normalized else None
    sources = contract.get("requirements")
    if not isinstance(sources, list) or not sources or len(sources) > 20:
        return None
    requirements = []
    seen = set()
    for source in sources:
        requirement = _normalize_requirement(source)
        if requirement is None or requirement["id"] in seen:
            return None
        seen.add(requirement["id"])
        requirements.append(requirement)
    return requirements


def _new_requirement(requirement, skill_index, requirement_index, skill_identity):
    public = {
        **requirement,
        "actual": [],
        "actualTruncated": 0,
        "acceptedSucceeded": 0,
        "acceptedFailed": 0,
        "ambiguous": 0,
        "rejected": 0,
        "missingCount": requirement["minCount"],
        "gap": True,
    }
    return {
        "skillIndex": skill_index,
        "requirementIndex": requirement_index,
        "type": requirement["type"],
        "tool": requirement["tool"],
        "qualification": (
            "artifact_file" if requirement["type"] == "artifact"
            else "tool_execution"
        ),
        "skill": skill_identity,
        "public": public,
    }


def _append_diagnostic(requirement, call_ref, outcome, claim_state, reason):
    public = requirement["public"]
    counter = {
        ("ambiguous", "succeeded"): "ambiguous",
        ("ambiguous", "failed"): "ambiguous",
        ("rejected", "succeeded"): "rejected",
        ("rejected", "failed"): "rejected",
    }[(claim_state, outcome)]
    public[counter] += 1
    if len(public["actual"]) >= MAX_ACTUAL_CLAIMS:
        public["actualTruncated"] += 1
        return
    claim = {
        "callRef": call_ref,
        "outcome": outcome,
        "claimState": claim_state,
    }
    claim["reason"] = reason
    public["actual"].append(claim)


def _append_receipt(requirement, run_id, call_ref, fingerprint, outcome, source):
    public = requirement["public"]
    public[
        "acceptedSucceeded" if outcome == "succeeded" else "acceptedFailed"
    ] += 1
    if len(public["actual"]) >= MAX_ACTUAL_CLAIMS:
        public["actualTruncated"] += 1
        return
    skill = requirement["skill"]
    evidence_hash = str(skill.get("evidenceContentHash") or "")
    digest = hashlib.sha256("\0".join((
        run_id,
        skill["name"],
        skill["role"],
        skill["skillContentHash"],
        evidence_hash,
        public["id"],
        public["tool"],
        requirement["qualification"],
        call_ref,
        fingerprint,
        outcome,
        source,
    )).encode("utf-8", errors="replace")).hexdigest()
    public["actual"].append({
        "version": RECEIPT_VERSION,
        "receiptId": f"sr1_{digest}",
        "skill": dict(skill),
        "requirementId": public["id"],
        "tool": public["tool"],
        "callRef": call_ref,
        "executionFingerprint": fingerprint,
        "outcome": outcome,
        "qualification": requirement["qualification"],
        "source": source,
        "claimState": "accepted",
    })


def _artifact_file_qualified(execution):
    result = execution.get("result") if isinstance(execution, dict) else None
    return bool(
        isinstance(result, dict)
        and result.get("ok") is not False
        and result.get("action") == "write_file"
        and str(result.get("path") or "").strip()
    )


def _completed_execution(execution):
    if not isinstance(execution, dict) or execution.get("status") != "completed":
        return None
    name = execution.get("name")
    if not isinstance(name, str) or not _SAFE_TOKEN_RE.fullmatch(name):
        return None
    outcome = execution.get("outcome")
    if outcome not in {"succeeded", "failed"}:
        if outcome not in {None, ""} or not isinstance(execution.get("result"), dict):
            return None
        outcome = "failed" if execution["result"].get("ok") is False else "succeeded"
    return name, outcome


def _execution_groups(tool_executions):
    if not isinstance(tool_executions, dict):
        return [], 0, 1
    grouped = {}
    safety = {}
    for key, execution in tool_executions.items():
        call_ref, safe = _safe_call_reference(key)
        grouped.setdefault(call_ref, []).append(execution)
        safety[call_ref] = safety.get(call_ref, True) and safe
    duplicate_refs = sum(len(group) > 1 for group in grouped.values())
    unique = [
        (call_ref, safety[call_ref], group[0])
        for call_ref, group in grouped.items()
        if len(group) == 1
    ]
    unique.sort(key=lambda item: item[0])
    return unique, duplicate_refs, 0


def _arguments_object(execution):
    value = execution.get("arguments") if isinstance(execution, dict) else None
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _explicit_skill_target(name, execution):
    field = _EXPLICIT_TARGET_FIELDS.get(name)
    if field is None:
        return None
    arguments = _arguments_object(execution)
    target = arguments.get(field) if isinstance(arguments, dict) else None
    if not isinstance(target, str) or not _SAFE_NAME_RE.fullmatch(target.strip()):
        return "", "explicit_skill_target_malformed"
    return target.strip(), ""


def _runtime_skill_target(name, execution):
    if name != "run_command":
        return None
    result = execution.get("result") if isinstance(execution, dict) else None
    if not isinstance(result, dict) or "skillRuntime" not in result:
        return None
    runtime = result.get("skillRuntime")
    if (
        not isinstance(runtime, dict)
        or isinstance(runtime.get("version"), bool)
        or runtime.get("version") != 1
    ):
        return "", "runtime_skill_identity_malformed"
    skills = runtime.get("skills") if isinstance(runtime, dict) else None
    if not isinstance(skills, list) or not skills:
        return "", "runtime_skill_identity_malformed"
    if len(skills) != 1:
        return "", "runtime_skill_identity_ambiguous"
    if not isinstance(skills[0], dict):
        return "", "runtime_skill_identity_malformed"
    target = skills[0].get("skill")
    if not isinstance(target, str) or not _SAFE_NAME_RE.fullmatch(target.strip()):
        return "", "runtime_skill_identity_malformed"
    return target.strip(), ""


def _select_candidate(candidates, skill_counts, execution, name):
    explicit = _explicit_skill_target(name, execution)
    runtime = _runtime_skill_target(name, execution)
    signal = explicit if explicit is not None else runtime
    source = "explicit_skill_target" if explicit is not None else "runtime_single_skill"
    if signal is not None:
        target, error = signal
        if error:
            return None, "rejected", error
        if skill_counts.get(target, 0) != 1:
            return None, "rejected", f"{source}_inactive"
        narrowed = [item for item in candidates if item["skill"]["name"] == target]
        if len(narrowed) == 1:
            return narrowed[0], "accepted", source
        if len(narrowed) > 1:
            return None, "ambiguous", "same_skill_multiple_requirements"
        return None, "rejected", f"{source}_conflict"
    if len(candidates) == 1:
        return candidates[0], "accepted", "server_unique"
    if len(candidates) > 1:
        reason = (
            "cross_skill"
            if len({item["skillIndex"] for item in candidates}) > 1
            else "same_skill_multiple_requirements"
        )
        return None, "ambiguous", reason
    return None, "ignored", ""


def _skill_state(contract_state, requirements, run_outcome):
    if contract_state != "valid":
        return f"{contract_state}_contract"
    if requirements and all(not item["public"]["gap"] for item in requirements):
        return "satisfied"
    if run_outcome == "completed":
        return "terminal_gaps"
    if run_outcome in {"failed", "cancelled"}:
        return run_outcome
    return "observing"


def _aggregate_state(skills, run_outcome):
    if not skills:
        return "not_applicable"
    if run_outcome in {"failed", "cancelled"}:
        return run_outcome
    states = {item["state"] for item in skills}
    if "invalid_contract" in states:
        return "invalid_contract"
    if "missing_contract" in states:
        return "missing_contract"
    if states == {"satisfied"}:
        return "satisfied"
    if run_outcome == "completed":
        return "terminal_gaps"
    return "observing"


def project_skill_outcome(lifecycle, tool_executions, run_id, run_status):
    """Derive bounded shadow evidence without mutating or authorizing a run."""
    run_outcome = _run_outcome(run_status)
    try:
        selected = lifecycle["activation"]["selected"]
        if not isinstance(selected, list) or len(selected) > MAX_SELECTED_SKILLS:
            return _invalid_projection(run_outcome)
        skills = []
        claims = []
        skill_counts = {}
        for skill_index, source in enumerate(selected):
            if not isinstance(source, dict):
                return _invalid_projection(run_outcome)
            name = source.get("name")
            role = source.get("role")
            content_hash = source.get("skillContentHash")
            evidence = source.get("evidence")
            if (
                not isinstance(name, str) or not _SAFE_NAME_RE.fullmatch(name)
                or role not in {"owner", "modifier"}
                or not isinstance(content_hash, str) or not _HASH_RE.fullmatch(content_hash)
                or not isinstance(evidence, dict)
            ):
                return _invalid_projection(run_outcome)
            evidence_state = evidence.get("state")
            requirements = _contract_requirements(evidence)
            if evidence_state == "missing":
                contract_state = "missing"
            elif evidence_state == "invalid" or requirements is None:
                contract_state = "invalid"
            else:
                contract_state = "valid"
            skill = {
                "name": name,
                "role": role,
                "skillContentHash": content_hash,
                "contractState": contract_state,
                "requirements": [],
            }
            if isinstance(evidence.get("contentHash"), str) and _HASH_RE.fullmatch(
                evidence["contentHash"]
            ):
                skill["evidenceContentHash"] = evidence["contentHash"]
            skill_identity = {
                key: skill[key]
                for key in (
                    "name", "role", "skillContentHash", "evidenceContentHash",
                )
                if key in skill
            }
            if name in skill_counts:
                return _invalid_projection(run_outcome)
            skill_counts[name] = 1
            for requirement_index, requirement in enumerate(requirements or []):
                claim = _new_requirement(
                    requirement, skill_index, requirement_index, skill_identity,
                )
                claims.append(claim)
                skill["requirements"].append(claim["public"])
            skills.append(skill)

        executions, duplicate_refs, ignored = _execution_groups(tool_executions)
        unsafe_refs = 0
        invalid_fingerprints = 0
        invalid_run_ids = 0
        for call_ref, safe_call_ref, execution in executions:
            completed = _completed_execution(execution)
            if completed is None:
                ignored += 1
                continue
            name, outcome = completed
            matched = [claim for claim in claims if claim["tool"] == name]
            candidates = []
            for claim in matched:
                if (
                    claim["type"] == "artifact"
                    and not _artifact_file_qualified(execution)
                ):
                    _append_diagnostic(
                        claim, call_ref, outcome, "rejected",
                        "artifact_structure_invalid",
                    )
                    continue
                candidates.append(claim)
            if not candidates:
                ignored += 1
                continue
            if not safe_call_ref:
                unsafe_refs += 1
                for claim in candidates:
                    _append_diagnostic(
                        claim, call_ref, outcome, "rejected", "call_reference_unsafe",
                    )
                continue
            fingerprint = execution.get("fingerprint")
            if not isinstance(fingerprint, str) or not _FINGERPRINT_RE.fullmatch(fingerprint):
                invalid_fingerprints += 1
                for claim in candidates:
                    _append_diagnostic(
                        claim, call_ref, outcome, "rejected",
                        "execution_fingerprint_invalid",
                    )
                continue
            if not isinstance(run_id, str) or not _SAFE_CALL_REF_RE.fullmatch(run_id):
                invalid_run_ids += 1
                for claim in candidates:
                    _append_diagnostic(
                        claim, call_ref, outcome, "rejected", "run_identity_invalid",
                    )
                continue
            accepted, claim_state, reason = _select_candidate(
                candidates, skill_counts, execution, name,
            )
            if accepted is not None:
                _append_receipt(
                    accepted, run_id, call_ref, fingerprint, outcome, reason,
                )
            elif claim_state in {"ambiguous", "rejected"}:
                for claim in candidates:
                    _append_diagnostic(
                        claim, call_ref, outcome, claim_state, reason,
                    )

        summary = _empty_summary()
        summary["selectedSkills"] = len(skills)
        summary["duplicateCallReferences"] = duplicate_refs
        summary["unsafeCallReferences"] = unsafe_refs
        summary["invalidExecutionFingerprints"] = invalid_fingerprints
        summary["invalidRunIdentities"] = invalid_run_ids
        summary["ignoredExecutions"] = ignored
        for skill_index, skill in enumerate(skills):
            contract_state = skill["contractState"]
            summary[f"{contract_state}Contracts"] += 1
            skill_claims = [claim for claim in claims if claim["skillIndex"] == skill_index]
            for claim in skill_claims:
                public = claim["public"]
                public["missingCount"] = max(
                    0, public["minCount"] - public["acceptedSucceeded"],
                )
                public["gap"] = public["missingCount"] > 0
                summary["requirements"] += 1
                summary["satisfiedRequirements"] += int(not public["gap"])
                for key in (
                    "acceptedSucceeded", "acceptedFailed", "ambiguous", "rejected",
                ):
                    target = {
                        "ambiguous": "ambiguousClaims",
                        "rejected": "rejectedClaims",
                    }.get(key, key)
                    summary[target] += public[key]
            skill["state"] = _skill_state(contract_state, skill_claims, run_outcome)
        return {
            "version": SCHEMA_VERSION,
            "mode": MODE,
            "runOutcome": run_outcome,
            "aggregateState": _aggregate_state(skills, run_outcome),
            "skills": skills,
            "summary": summary,
        }
    except (KeyError, TypeError, ValueError):
        return _invalid_projection(run_outcome)
