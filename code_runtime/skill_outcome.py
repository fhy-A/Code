"""Pure, non-authoritative Skill outcome shadow projection."""

from __future__ import annotations

import hashlib
import re

from .skill_lifecycle import MAX_SELECTED_SKILLS


SCHEMA_VERSION = 1
MODE = "shadow"
MAX_ACTUAL_CLAIMS = 16

_SAFE_NAME_RE = re.compile(r"[A-Za-z0-9_.-]{1,128}")
_SAFE_TOKEN_RE = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_SAFE_CALL_REF_RE = re.compile(r"[A-Za-z0-9_.:-]{1,200}")
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}")


def _run_outcome(status):
    value = str(status or "")
    return value if value in {"completed", "failed", "cancelled"} else "active"


def _safe_call_reference(value):
    raw = str(value or "")
    if _SAFE_CALL_REF_RE.fullmatch(raw):
        return raw
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
    return f"call-sha256:{digest}"


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


def _contract_requirements(evidence):
    if not isinstance(evidence, dict) or evidence.get("state") != "ready":
        return None
    contract = evidence.get("contract")
    if (
        not isinstance(contract, dict)
        or type(contract.get("schemaVersion")) is not int
        or contract.get("schemaVersion") != 1
    ):
        return None
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


def _new_requirement(requirement, skill_index, requirement_index):
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
        "public": public,
    }


def _append_claim(requirement, call_ref, outcome, claim_state, *, reason=""):
    public = requirement["public"]
    counter = {
        ("accepted", "succeeded"): "acceptedSucceeded",
        ("accepted", "failed"): "acceptedFailed",
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
    if reason:
        claim["reason"] = reason
    public["actual"].append(claim)


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
    for key, execution in tool_executions.items():
        grouped.setdefault(_safe_call_reference(key), []).append(execution)
    duplicate_refs = sum(len(group) > 1 for group in grouped.values())
    unique = [
        (call_ref, group[0])
        for call_ref, group in grouped.items()
        if len(group) == 1
    ]
    unique.sort(key=lambda item: item[0])
    return unique, duplicate_refs, 0


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


def project_skill_outcome(lifecycle, tool_executions, run_status):
    """Derive bounded shadow evidence without mutating or authorizing a run."""
    run_outcome = _run_outcome(run_status)
    try:
        selected = lifecycle["activation"]["selected"]
        if not isinstance(selected, list) or len(selected) > MAX_SELECTED_SKILLS:
            return _invalid_projection(run_outcome)
        skills = []
        claims = []
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
            for requirement_index, requirement in enumerate(requirements or []):
                claim = _new_requirement(requirement, skill_index, requirement_index)
                claims.append(claim)
                skill["requirements"].append(claim["public"])
            skills.append(skill)

        executions, duplicate_refs, ignored = _execution_groups(tool_executions)
        for call_ref, execution in executions:
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
                    and outcome == "succeeded"
                    and not _artifact_file_qualified(execution)
                ):
                    _append_claim(
                        claim, call_ref, outcome, "rejected",
                        reason="artifact_structure_invalid",
                    )
                    continue
                candidates.append(claim)
            if len(candidates) == 1:
                _append_claim(candidates[0], call_ref, outcome, "accepted")
            elif len(candidates) > 1:
                reason = (
                    "cross_skill"
                    if len({claim["skillIndex"] for claim in candidates}) > 1
                    else "same_skill_multiple_requirements"
                )
                for claim in candidates:
                    _append_claim(
                        claim, call_ref, outcome, "ambiguous", reason=reason,
                    )

        summary = _empty_summary()
        summary["selectedSkills"] = len(skills)
        summary["duplicateCallReferences"] = duplicate_refs
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
