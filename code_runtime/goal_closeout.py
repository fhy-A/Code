"""Bounded model projection and optional Run-local closeout metadata.

Goal events/reducer remain authoritative. This module does not evaluate whether
model-supplied evidence is objectively true and never writes a Goal event.
"""
from __future__ import annotations

import copy
import json


PROJECTION_LIMIT = 24000
CHECK_ROUNDS = 2  # one bounded episode: up to two metadata turns, then one final
CONTINUE_ROUNDS = 8  # a smaller cap inside the existing Run/tool budgets
CHECK_TOOLS = frozenset({"goal_read", "goal_complete_step", "goal_complete", "goal_raise_gate",
                         "goal_clear_gate", "goal_cancel"})
PHASES = {"open", "checking", "resumed", "stopping", "stopped"}
RELATIONS = {"unknown", "related", "status", "unrelated"}


def normalize(value, run_id, rounds=None):
    if value is None:
        return None  # old Runs do not require a migration
    required = {"version", "runId", "goalId", "revision", "relation", "reason",
                "sourceCallId", "inputKey", "phase", "checkRound", "trigger", "gateRevision"}
    optional = {"inputRound", "gateDisposition"}
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - optional:
        raise ValueError("goal_closeout_state_invalid")
    if type(value["version"]) is not int or value["version"] != 1 or value["runId"] != run_id:
        raise ValueError("goal_closeout_state_invalid")
    for key in ("revision", "checkRound", "gateRevision"):
        if type(value[key]) is not int or value[key] < 0:
            raise ValueError("goal_closeout_state_invalid")
    for key in ("runId", "goalId", "reason", "sourceCallId", "inputKey", "trigger"):
        if not isinstance(value[key], str) or len(value[key]) > 2000:
            raise ValueError("goal_closeout_state_invalid")
    if (not value["goalId"] or value["relation"] not in RELATIONS
            or value["phase"] not in PHASES
            or (value["phase"] != "open" and not value["trigger"])
            or (value["relation"] != "unknown" and not value["reason"])):
        raise ValueError("goal_closeout_state_invalid")
    if value["phase"] == "open" and (value["checkRound"] or value["trigger"] or value["gateRevision"]):
        raise ValueError("goal_closeout_state_invalid")
    if rounds is not None and value["checkRound"] > rounds:
        raise ValueError("goal_closeout_state_invalid")
    input_round = value.get("inputRound")
    if input_round is not None and (type(input_round) is not int or input_round < 0
                                    or (rounds is not None and input_round > rounds)):
        raise ValueError("goal_closeout_state_invalid")
    disposition = value.get("gateDisposition")
    if disposition is not None and (
        not isinstance(disposition, dict) or set(disposition) != {"revision", "inputKey", "sourceCallId"}
        or type(disposition["revision"]) is not int or disposition["revision"] < 0
        or any(not isinstance(disposition[k], str) or not disposition[k] or len(disposition[k]) > 2000
               for k in ("inputKey", "sourceCallId"))
    ):
        raise ValueError("goal_closeout_state_invalid")
    return copy.deepcopy(value)


def create(run_id, projection, input_key):
    return {"version": 1, "runId": run_id, "goalId": projection["goal"]["goalId"],
            "revision": projection["revision"], "relation": "unknown", "reason": "",
            "sourceCallId": "", "inputKey": input_key, "phase": "open",
            "checkRound": 0, "trigger": "", "gateRevision": 0,
            "inputRound": None, "gateDisposition": None}


def project(projection, *, step_id="", offset=None, text_offset=0):
    """Bounded JSON with stable IDs and explicit character/criterion cursors.

    Reserve space for the Run binding added by the server. Evidence is a bounded
    representative summary, not a second full event store or an acceptance proof.
    """
    if not isinstance(projection, dict) or projection.get("health") != "healthy":
        return {"health": "unavailable", "goal": None, "truncated": False}
    goal = projection.get("goal")
    if not goal:
        return {"health": "healthy", "revision": projection.get("revision", 0), "goal": None}
    if type(text_offset) is not int or not 0 <= text_offset <= 4000:
        raise ValueError("goal_read_text_offset_invalid")
    if offset is not None and (type(offset) is not int or offset < 0):
        raise ValueError("goal_read_offset_invalid")
    clipped = []
    def brief(value, limit, path):
        value = str(value or "")
        if len(value) > limit:
            clipped.append(path)
        return value[:limit]
    objective = str(goal.get("objective") or "")
    objective_start = (offset or 0) if not step_id else 0
    if objective_start > len(objective):
        raise ValueError("goal_read_offset_invalid")
    result = {"health": "healthy", "revision": projection["revision"], "goal": {
        "goalId": goal["goalId"], "lifecycle": goal["lifecycle"],
        "objective": brief(objective[objective_start:], 128 if step_id else 400, "objective"),
        "currentStepId": goal.get("currentStepId"), "gate": None, "steps": [],
    }, "truncated": False, "clippedFields": clipped, "objectiveOffset": objective_start,
        "read": {"tool": "goal_read", "goalId": goal["goalId"],
                 "expectedRevision": projection["revision"], "pageSize": 1}}
    if goal.get("gate"):
        result["goal"]["gate"] = {"type": goal["gate"].get("type"),
            "summary": brief(goal["gate"].get("summary"), 128, "gate.summary")}
    selected = [s for s in goal.get("steps", []) if not step_id or s["id"] == step_id]
    if step_id and not selected:
        raise ValueError("goal_read_unknown_step")
    raw_steps = {s["id"]: s for s in selected}
    for step in selected:
        criteria = step.get("acceptanceCriteria") or []
        start = (offset or 0) if step_id else 0
        if start > len(criteria):
            raise ValueError("goal_read_offset_invalid")
        chosen = criteria[start:start + 1] if step_id else criteria
        text_start = text_offset if step_id else 0
        item = {"id": step["id"], "status": step["status"],
                "description": brief(str(step.get("description") or "")[text_start:],
                                     400 if step_id else 100, step["id"]),
                "criteriaTotal": len(criteria), "offset": start, "descriptionOffset": text_start,
                "acceptanceCriteria": [], "evidence": []}
        for criterion in chosen:
            item["acceptanceCriteria"].append({"id": criterion["id"], "kind": criterion["kind"],
                **({'sourceReference': copy.deepcopy(criterion['sourceReference'])}
                   if criterion.get('sourceReference') else {}),
                "description": brief(str(criterion.get("description") or "")[text_start:],
                                     400 if step_id else 100, criterion["id"]),
                "descriptionOffset": text_start})
        ids = {c["id"] for c in chosen}
        evidence = [e for e in step.get("evidence") or [] if e.get("criterionId") in ids]
        item["evidenceTotal"] = len(evidence)
        for e in evidence[:2 if step_id else 20]:
            item["evidence"].append({**{k: e.get(k) for k in (
                "id", "criterionId", "kind", "sourceRunId", "sourceToolCallId", "artifactDigest")},
                "summary": brief(e.get("summary"), 128, str(e.get("id")))})
        result["goal"]["steps"].append(item)
    result["clippedFieldsOmitted"] = max(0, len(clipped) - 16)
    del clipped[16:]
    def size():
        return len(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    if not step_id:
        ordered = sorted(result["goal"]["steps"], key=lambda s: s["id"] == goal.get("currentStepId"))
        for item in ordered:
            while size() > PROJECTION_LIMIT - 4000 and item["acceptanceCriteria"]:
                removed = item["acceptanceCriteria"].pop()
                item["evidence"] = [e for e in item["evidence"] if e["criterionId"] != removed["id"]]
    # Worst-case Unicode uses up to twelve ASCII JSON characters per code point.
    # Never drop the one paged criterion: shorten text and derive its exact cursor.
    while size() > PROJECTION_LIMIT - 4000:
        result["summaryReducedForBudget"] = True
        result["goal"]["objective"] = result["goal"]["objective"][:len(result["goal"]["objective"]) // 2]
        for item in result["goal"]["steps"]:
            item["description"] = item["description"][:len(item["description"]) // 2]
            for c in item["acceptanceCriteria"]:
                c["description"] = c["description"][:max(1, len(c["description"]) // 2)]
            for e in item["evidence"]:
                e["summary"] = e["summary"][:len(e["summary"]) // 2]
        if size() > PROJECTION_LIMIT - 4000 and not any(
            len(c["description"]) > 1 for s in result["goal"]["steps"] for c in s["acceptanceCriteria"]
        ):
            raise ValueError("goal_projection_limit_exceeded")
    for item in result["goal"]["steps"]:
        raw = raw_steps[item["id"]]
        end = item["offset"] + len(item["acceptanceCriteria"])
        item["nextOffset"] = end if end < item["criteriaTotal"] else None
        item["omittedCriteria"] = item["criteriaTotal"] - len(item["acceptanceCriteria"])
        item["omittedEvidence"] = item["evidenceTotal"] - len(item["evidence"])
        end_text = item["descriptionOffset"] + len(item["description"])
        item["descriptionNextOffset"] = end_text if end_text < len(str(raw.get("description") or "")) else None
        raw_criteria = {c["id"]: c for c in raw.get("acceptanceCriteria") or []}
        for c in item["acceptanceCriteria"]:
            end_text = c["descriptionOffset"] + len(c["description"])
            c["descriptionNextOffset"] = end_text if end_text < len(raw_criteria[c["id"]]["description"]) else None
    objective_end = objective_start + len(result["goal"]["objective"])
    result["objectiveNextOffset"] = (0 if step_id else objective_end) if objective_end < len(objective) else None
    result["truncated"] = bool(clipped or result.get("summaryReducedForBudget")
                               or any(s["omittedCriteria"] or s["omittedEvidence"] for s in result["goal"]["steps"]))
    if size() > PROJECTION_LIMIT - 2000:
        raise ValueError("goal_projection_limit_exceeded")
    return result
