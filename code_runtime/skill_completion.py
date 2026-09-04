"""Pure contracts for default-off Skill owner completion enforcement."""

from __future__ import annotations

import copy
import hashlib
import json
import re

from . import skill_outcome


PLAN_VERSION = 1
CONTRACT_VERSION = skill_outcome.COMPLETION_CONTRACT_VERSION
ENFORCEMENT_MODE = skill_outcome.COMPLETION_ENFORCEMENT_MODE
MAX_REPAIR_CALLS = 8

_PHASES = {"armed", "continuing", "finalizing", "passed", "failed"}
_SAFE_NAME_RE = re.compile(r"[A-Za-z0-9_.-]{1,128}")
_SAFE_CALL_RE = re.compile(r"[A-Za-z0-9_.:-]{1,200}")
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}")
_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}")
_CONTINUATION_RE = re.compile(r"sce1_[0-9a-f]{64}")
_EXPLICIT_TARGET_FIELDS = {
    "use_skill": "name",
    "check_skill_dependencies": "name",
    "read_skill_resource": "skill",
}


class SkillCompletionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _error(code, message):
    raise SkillCompletionError(code, message)


def _budget_capacity(tool, budgets):
    limits = [
        int(item.get("limit") or 0)
        for item in budgets or []
        if isinstance(item, dict) and tool in (item.get("tools") or [])
    ]
    return min(limits) if limits else MAX_REPAIR_CALLS


def build_plan(lifecycle, tool_specs, tool_budgets, *, enabled):
    if not enabled:
        return None
    try:
        activation = lifecycle["activation"]
        selected = activation["selected"]
        owner = selected[0]
        evidence = owner["evidence"]
    except (IndexError, KeyError, TypeError):
        return None
    raw_contract = evidence.get("contract") if isinstance(evidence, dict) else None
    if not isinstance(raw_contract, dict) or raw_contract.get("schemaVersion") != CONTRACT_VERSION:
        return None
    contract = skill_outcome.normalize_completion_contract(raw_contract)
    if contract is None:
        _error("skill_completion_contract_invalid", "Skill completion contract is invalid")
    enforcement = contract["enforcement"]
    activation_kind = str(activation.get("intentKind") or "")
    if activation_kind not in enforcement["activationKinds"]:
        return None
    if (
        owner.get("role") != "owner" or evidence.get("state") != "ready"
        or not _SAFE_NAME_RE.fullmatch(str(owner.get("name") or ""))
        or not _HASH_RE.fullmatch(str(owner.get("skillContentHash") or ""))
        or not _HASH_RE.fullmatch(str(evidence.get("contentHash") or ""))
    ):
        _error("skill_completion_contract_unenforceable", "Skill completion owner identity is invalid")
    requirements = contract["requirements"]
    all_tools = [
        item.get("tool")
        for skill in selected if isinstance(skill, dict)
        for item in (((skill.get("evidence") or {}).get("contract") or {}).get("requirements") or [])
        if isinstance(item, dict)
    ]
    owner_tools = [item["tool"] for item in requirements]
    if len(owner_tools) != len(set(owner_tools)) or any(
        all_tools.count(tool) != 1 for tool in owner_tools
    ):
        _error("skill_completion_contract_unenforceable", "Skill completion tools are ambiguous")
    if sum(item["minCount"] for item in requirements) > MAX_REPAIR_CALLS:
        _error("skill_completion_contract_unenforceable", "Skill completion call budget is too large")
    for requirement in requirements:
        spec = (tool_specs or {}).get(requirement["tool"])
        if not spec or not spec.get("effect") or spec.get("effect") in {"interaction", "goal_metadata"}:
            _error("skill_completion_contract_unenforceable", "Skill completion tool is not enforceable")
        if spec.get("effect") != "read" and requirement["minCount"] != 1:
            _error("skill_completion_contract_unenforceable", "Side-effect evidence must have minCount 1")
        if _budget_capacity(requirement["tool"], tool_budgets) < requirement["minCount"]:
            _error("skill_completion_contract_unenforceable", "Skill completion tool budget is insufficient")
    if "run_command" in owner_tools:
        runtime_skills = [
            item.get("name") for item in selected
            if (item.get("dependency") or {}).get("capabilities")
        ]
        if runtime_skills not in ([], [owner["name"]]):
            _error("skill_completion_contract_unenforceable", "Skill command runtime identity is ambiguous")
    return {
        "version": PLAN_VERSION,
        "policy": {
            "mode": ENFORCEMENT_MODE,
            "activationKind": activation_kind,
            "activationKinds": enforcement["activationKinds"],
            "owner": {
                "name": owner["name"], "role": "owner",
                "skillContentHash": owner["skillContentHash"],
                "evidenceContentHash": evidence["contentHash"],
            },
        },
        "phase": "armed",
        "triggerRound": 0,
        "continuationId": "",
        "allowedCalls": [],
        "toolBatchCallIds": [],
    }


def normalize_plan(value, lifecycle, tool_specs, tool_budgets):
    expected = build_plan(lifecycle, tool_specs, tool_budgets, enabled=True)
    fields = {
        "version", "policy", "phase", "triggerRound", "continuationId",
        "allowedCalls", "toolBatchCallIds",
    }
    if expected is None or not isinstance(value, dict) or set(value) != fields:
        _error("skill_completion_state_invalid", "Skill completion state is invalid")
    if any(value.get(key) != expected[key] for key in ("version", "policy")):
        _error("skill_completion_state_invalid", "Skill completion policy identity changed")
    phase = value.get("phase")
    trigger = value.get("triggerRound")
    continuation_id = value.get("continuationId")
    if (
        phase not in _PHASES or isinstance(trigger, bool)
        or not isinstance(trigger, int) or trigger < 0
        or (continuation_id and not _CONTINUATION_RE.fullmatch(str(continuation_id)))
    ):
        _error("skill_completion_state_invalid", "Skill completion state values are invalid")
    requirement_map = {
        item["id"]: item for item in skill_outcome.normalize_completion_contract(
            lifecycle["activation"]["selected"][0]["evidence"]["contract"]
        )["requirements"]
    }
    allowed = value.get("allowedCalls")
    call_ids = value.get("toolBatchCallIds")
    if not isinstance(allowed, list) or not isinstance(call_ids, list):
        _error("skill_completion_state_invalid", "Skill completion state lists are invalid")
    seen = set()
    for item in allowed:
        requirement = requirement_map.get(item.get("requirementId")) if isinstance(item, dict) else None
        maximum = item.get("maxCalls") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict) or set(item) != {"requirementId", "tool", "maxCalls"}
            or not requirement or requirement["tool"] != item.get("tool")
            or item["requirementId"] in seen or isinstance(maximum, bool)
            or not isinstance(maximum, int) or not 1 <= maximum <= requirement["minCount"]
        ):
            _error("skill_completion_state_invalid", "Skill completion allowed call is invalid")
        seen.add(item["requirementId"])
    if (
        len(call_ids) != len(set(call_ids)) or len(call_ids) > MAX_REPAIR_CALLS
        or any(not isinstance(item, str) or not _SAFE_CALL_RE.fullmatch(item) for item in call_ids)
    ):
        _error("skill_completion_state_invalid", "Skill completion tool call ids are invalid")
    active = (trigger, continuation_id, allowed)
    if phase == "armed" and (any(active) or call_ids):
        _error("skill_completion_state_invalid", "Armed Skill completion state is dirty")
    if phase in {"continuing", "finalizing"} and (
        trigger < 1 or not all(active[1:]) or (phase == "finalizing" and not call_ids)
    ):
        _error("skill_completion_state_invalid", "Active Skill completion state is incomplete")
    return copy.deepcopy(value)


def validate_runtime_state(plan, round_count, executions):
    phase = plan["phase"]
    if phase in {"continuing", "finalizing"} and not (
        plan["triggerRound"] <= round_count
        <= plan["triggerRound"] + (2 if phase == "finalizing" else 1)
    ):
        _error("skill_completion_state_invalid", "Skill completion round state is invalid")
    if phase == "finalizing" and any(
        (executions or {}).get(item, {}).get("status") != "completed"
        for item in plan["toolBatchCallIds"]
    ):
        _error("skill_completion_state_invalid", "Skill completion batch state is invalid")
    return plan


def _evaluation(status, gaps, allowed=()):
    encoded = json.dumps(gaps, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "status": status,
        "gaps": gaps,
        "allowedCalls": list(allowed),
        "gapDigest": "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }


def evaluate(plan, outcome, tool_specs):
    if not isinstance(outcome, dict) or outcome.get("version") != 2:
        return {"status": "invalid", "gaps": [], "allowedCalls": [], "gapDigest": ""}
    owner_identity = plan["policy"]["owner"]
    owners = [
        item for item in outcome.get("skills") or []
        if isinstance(item, dict) and item.get("role") == "owner"
    ]
    observed = owners[0].get("requirements") if len(owners) == 1 else None
    if (
        len(owners) != 1 or owners[0].get("contractState") != "valid"
        or any(owners[0].get(key) != value for key, value in owner_identity.items())
        or not isinstance(observed, list) or not observed
    ):
        return {"status": "invalid", "gaps": [], "allowedCalls": [], "gapDigest": ""}
    if int((outcome.get("summary") or {}).get("duplicateCallReferences") or 0) > 0:
        return _evaluation("fatal", [{
            "requirementId": "*", "tool": "*", "missingCount": 0,
            "class": "duplicate_reference",
        }])
    gaps, allowed, fatal = [], [], False
    for requirement in observed:
        if not requirement.get("gap"):
            continue
        spec = (tool_specs or {}).get(requirement["tool"]) or {}
        if int(requirement.get("ambiguous") or 0) > 0:
            gap_class, fatal = "ambiguous_existing", True
        elif int(requirement.get("rejected") or 0) > 0:
            gap_class, fatal = "rejected_existing", True
        elif int(requirement.get("acceptedFailed") or 0) > 0:
            if spec.get("effect") == "read" and spec.get("idempotent") is True:
                gap_class = "failed_read"
            else:
                gap_class, fatal = "failed_side_effect", True
        else:
            gap_class = "not_executed"
        gap = {
            "requirementId": requirement["id"], "tool": requirement["tool"],
            "missingCount": int(requirement.get("missingCount") or 0),
            "class": gap_class,
        }
        gaps.append(gap)
        if gap_class in {"not_executed", "failed_read"}:
            allowed.append({
                "requirementId": gap["requirementId"], "tool": gap["tool"],
                "maxCalls": gap["missingCount"],
            })
    if not gaps:
        return _evaluation("satisfied", [])
    return _evaluation("fatal" if fatal else "recoverable", gaps, [] if fatal else allowed)


def begin_continuation(plan, evaluation, run_id, round_number, content):
    if plan.get("phase") != "armed" or evaluation.get("status") != "recoverable":
        _error("skill_completion_state_invalid", "Skill completion cannot start continuation")
    candidate_digest = "sha256:" + hashlib.sha256(
        str(content or "").encode("utf-8", errors="replace")
    ).hexdigest()
    gap_digest = str(evaluation.get("gapDigest") or "")
    digest = hashlib.sha256("\0".join((
        str(run_id or ""), plan["policy"]["owner"]["evidenceContentHash"],
        str(round_number), candidate_digest, gap_digest,
    )).encode("utf-8", errors="replace")).hexdigest()
    updated = copy.deepcopy(plan)
    updated.update({
        "phase": "continuing", "triggerRound": int(round_number),
        "continuationId": f"sce1_{digest}",
        "allowedCalls": copy.deepcopy(evaluation["allowedCalls"]),
    })
    return updated


def validate_repair_batch(plan, calls, tool_specs, executions):
    if plan.get("phase") != "continuing" or plan.get("toolBatchCallIds"):
        _error("skill_completion_repair_batch_invalid", "Skill completion repair batch is unavailable")
    if not isinstance(calls, list) or not calls or len(calls) > MAX_REPAIR_CALLS:
        _error("skill_completion_repair_batch_invalid", "Skill completion repair batch size is invalid")
    limits = {item["tool"]: item["maxCalls"] for item in plan.get("allowedCalls") or []}
    counts, call_ids, fingerprints = {}, [], set()
    owner_name = plan["policy"]["owner"]["name"]
    for call in calls:
        name = str((call.get("function") or {}).get("name") or "")
        call_id = str(call.get("id") or "")
        fingerprint = str(call.get("fingerprint") or "")
        if (
            name not in limits or call.get("parseError") or call.get("validationErrors")
            or not _SAFE_CALL_RE.fullmatch(call_id) or not _FINGERPRINT_RE.fullmatch(fingerprint)
            or call_id in call_ids or call_id in (executions or {}) or fingerprint in fingerprints
        ):
            _error("skill_completion_repair_batch_invalid", "Skill completion repair call is invalid")
        counts[name] = counts.get(name, 0) + 1
        if counts[name] > limits[name]:
            _error("skill_completion_repair_batch_invalid", "Skill completion repair call budget exceeded")
        spec = (tool_specs or {}).get(name) or {}
        if spec.get("effect") != "read" and any(
            isinstance(item, dict) and item.get("name") == name
            for item in (executions or {}).values()
        ):
            _error("skill_completion_repair_batch_invalid", "Skill completion side effect cannot be replayed")
        target = _EXPLICIT_TARGET_FIELDS.get(name)
        if target and (
            not isinstance(call.get("arguments"), dict)
            or str(call["arguments"].get(target) or "").strip() != owner_name
        ):
            _error("skill_completion_repair_batch_invalid", "Skill completion target is invalid")
        call_ids.append(call_id)
        fingerprints.add(fingerprint)
    return call_ids


def advance(plan, phase, call_ids=None):
    if phase not in {"finalizing", "passed", "failed"}:
        if phase != "continuing" or call_ids is None:
            _error("skill_completion_state_invalid", "Skill completion transition is invalid")
    updated = copy.deepcopy(plan)
    updated["phase"] = phase
    if call_ids is not None:
        updated["toolBatchCallIds"] = list(call_ids)
    return updated
