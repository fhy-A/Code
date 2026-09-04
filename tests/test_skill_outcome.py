import hashlib
import json
import unittest

from code_runtime import skill_outcome


def _sha(value):
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _requirement(requirement_id, tool="read_file", *, kind="tool_execution", minimum=1):
    result = {
        "id": requirement_id,
        "type": kind,
        "tool": tool,
        "minCount": minimum,
    }
    if kind == "artifact":
        result["artifactKind"] = "file"
    return result


def _selected(name, index, requirements=None, *, evidence_state="ready"):
    evidence = {"state": evidence_state}
    if evidence_state == "ready":
        evidence.update({
            "contentHash": _sha(f"evidence:{name}"),
            "contract": {
                "schemaVersion": 1,
                "requirements": requirements or [_requirement(f"inspect-{name}")],
            },
        })
    elif evidence_state == "invalid":
        evidence["contentHash"] = _sha(f"evidence:{name}")
    return {
        "name": name,
        "role": "owner" if index == 0 else "modifier",
        "skillContentHash": _sha(f"skill:{name}"),
        "evidence": evidence,
    }


def _lifecycle(*skills):
    return {"activation": {"selected": list(skills)}}


def _execution(tool="read_file", *, outcome="succeeded", result=None):
    return {
        "name": tool,
        "status": "completed",
        "outcome": outcome,
        "result": result if result is not None else {"ok": outcome == "succeeded"},
    }


class TestSkillOutcomeProjection(unittest.TestCase):
    def test_observes_partial_then_satisfied_evidence_without_reusing_calls(self):
        lifecycle = _lifecycle(_selected("alpha", 0, [
            _requirement("inspect"),
            _requirement("write", "write_file", kind="artifact"),
        ]))
        initial = skill_outcome.project_skill_outcome(lifecycle, {}, "tools")
        self.assertEqual(initial["aggregateState"], "observing")
        self.assertEqual(
            [item["missingCount"] for item in initial["skills"][0]["requirements"]],
            [1, 1],
        )

        executions = {
            "call-read": {
                "name": "read_file",
                "status": "completed",
                "result": {"ok": True},
            },
            "call-write-failed": _execution(
                "write_file", outcome="failed",
                result={"ok": False, "action": "write_file", "path": "failed.txt"},
            ),
        }
        partial = skill_outcome.project_skill_outcome(lifecycle, executions, "model")
        inspect, write = partial["skills"][0]["requirements"]
        self.assertEqual((inspect["acceptedSucceeded"], inspect["missingCount"]), (1, 0))
        self.assertEqual((write["acceptedFailed"], write["missingCount"]), (1, 1))
        self.assertEqual(partial["aggregateState"], "observing")

        executions["call-write-ready"] = _execution(
            "write_file",
            result={"ok": True, "action": "write_file", "path": "ready.txt"},
        )
        satisfied = skill_outcome.project_skill_outcome(lifecycle, executions, "completed")
        self.assertEqual(satisfied["aggregateState"], "satisfied")
        self.assertEqual(satisfied["summary"]["acceptedSucceeded"], 2)
        self.assertEqual(satisfied["summary"]["acceptedFailed"], 1)
        self.assertEqual(satisfied["summary"]["satisfiedRequirements"], 2)

    def test_same_skill_multi_requirement_claim_is_ambiguous_and_counts_toward_none(self):
        lifecycle = _lifecycle(_selected("alpha", 0, [
            _requirement("inspect-a"),
            _requirement("inspect-b"),
        ]))
        projection = skill_outcome.project_skill_outcome(
            lifecycle, {"shared-call": _execution()}, "completed",
        )
        requirements = projection["skills"][0]["requirements"]
        self.assertEqual([item["ambiguous"] for item in requirements], [1, 1])
        self.assertEqual([item["acceptedSucceeded"] for item in requirements], [0, 0])
        self.assertEqual([item["missingCount"] for item in requirements], [1, 1])
        self.assertEqual(
            [item["actual"][0]["claimState"] for item in requirements],
            ["ambiguous", "ambiguous"],
        )
        self.assertEqual(
            [item["actual"][0]["reason"] for item in requirements],
            ["same_skill_multiple_requirements", "same_skill_multiple_requirements"],
        )
        self.assertEqual(projection["aggregateState"], "terminal_gaps")

    def test_cross_skill_claim_is_ambiguous_and_never_uses_skill_order(self):
        lifecycle = _lifecycle(
            _selected("alpha", 0),
            _selected("beta", 1),
        )
        projection = skill_outcome.project_skill_outcome(
            lifecycle, {"shared-call": _execution()}, "model",
        )
        self.assertEqual(
            [item["requirements"][0]["ambiguous"] for item in projection["skills"]],
            [1, 1],
        )
        self.assertEqual(
            [item["requirements"][0]["actual"][0]["reason"] for item in projection["skills"]],
            ["cross_skill", "cross_skill"],
        )
        self.assertEqual(projection["summary"]["acceptedSucceeded"], 0)
        self.assertEqual(projection["summary"]["ambiguousClaims"], 2)

    def test_duplicate_normalized_call_references_are_quarantined(self):
        lifecycle = _lifecycle(_selected("alpha", 0))
        projection = skill_outcome.project_skill_outcome(
            lifecycle,
            {7: _execution(), "7": _execution()},
            "completed",
        )
        requirement = projection["skills"][0]["requirements"][0]
        self.assertEqual(requirement["acceptedSucceeded"], 0)
        self.assertEqual(projection["summary"]["duplicateCallReferences"], 1)
        self.assertEqual(projection["aggregateState"], "terminal_gaps")

    def test_artifact_uses_only_structural_result_and_never_copies_the_path(self):
        lifecycle = _lifecycle(_selected("alpha", 0, [
            _requirement("output", "write_file", kind="artifact"),
        ]))
        executions = {
            "artifact-invalid": _execution(
                "write_file",
                result={"ok": True, "action": "write_file", "path": ""},
            ),
            "artifact-failed": _execution(
                "write_file", outcome="failed",
                result={"ok": False, "action": "write_file", "path": "failed-secret.txt"},
            ),
            "artifact-ready": _execution(
                "write_file",
                result={"ok": True, "action": "write_file", "path": "ready-secret.txt"},
            ),
        }
        projection = skill_outcome.project_skill_outcome(lifecycle, executions, "completed")
        requirement = projection["skills"][0]["requirements"][0]
        self.assertEqual(requirement["acceptedSucceeded"], 1)
        self.assertEqual(requirement["acceptedFailed"], 1)
        self.assertEqual(requirement["rejected"], 1)
        self.assertEqual(
            [item["claimState"] for item in requirement["actual"]],
            ["accepted", "rejected", "accepted"],
        )
        serialized = json.dumps(projection)
        self.assertNotIn("failed-secret.txt", serialized)
        self.assertNotIn("ready-secret.txt", serialized)

    def test_aggregate_distinguishes_terminal_and_contract_states(self):
        ready = _lifecycle(_selected("alpha", 0))
        self.assertEqual(
            skill_outcome.project_skill_outcome(ready, {}, "completed")["aggregateState"],
            "terminal_gaps",
        )
        self.assertEqual(
            skill_outcome.project_skill_outcome(ready, {}, "failed")["aggregateState"],
            "failed",
        )
        self.assertEqual(
            skill_outcome.project_skill_outcome(ready, {}, "cancelled")["aggregateState"],
            "cancelled",
        )
        missing = _lifecycle(_selected("alpha", 0, evidence_state="missing"))
        invalid = _lifecycle(_selected("alpha", 0, evidence_state="invalid"))
        self.assertEqual(
            skill_outcome.project_skill_outcome(missing, {}, "model")["aggregateState"],
            "missing_contract",
        )
        self.assertEqual(
            skill_outcome.project_skill_outcome(invalid, {}, "model")["aggregateState"],
            "invalid_contract",
        )
        self.assertEqual(
            skill_outcome.project_skill_outcome(_lifecycle(), {}, "completed")["aggregateState"],
            "not_applicable",
        )

    def test_projection_is_bounded_deterministic_and_hides_unsafe_call_ids(self):
        lifecycle = _lifecycle(_selected("alpha", 0))
        executions = {
            f"failed-{index:02d}": _execution(outcome="failed")
            for index in range(40)
        }
        executions["SECRET\nCALL"] = _execution(outcome="failed")
        projection = skill_outcome.project_skill_outcome(lifecycle, executions, "failed")
        reversed_projection = skill_outcome.project_skill_outcome(
            lifecycle, dict(reversed(list(executions.items()))), "failed",
        )
        self.assertEqual(projection, reversed_projection)
        requirement = projection["skills"][0]["requirements"][0]
        self.assertEqual(requirement["acceptedFailed"], 41)
        self.assertEqual(len(requirement["actual"]), skill_outcome.MAX_ACTUAL_CLAIMS)
        self.assertEqual(requirement["actualTruncated"], 25)
        serialized = json.dumps(projection)
        self.assertNotIn("SECRET", serialized)
        self.assertIn("call-sha256:", serialized)

    def test_malformed_input_is_total_and_contains_no_source_payload(self):
        projection = skill_outcome.project_skill_outcome(
            {"activation": {"selected": [{"secret": "DO_NOT_COPY"}]}},
            {"call": {"secret": "DO_NOT_COPY"}},
            "model",
        )
        self.assertEqual(projection["aggregateState"], "invalid_contract")
        self.assertNotIn("DO_NOT_COPY", json.dumps(projection))

        boolean_version = _lifecycle(_selected("alpha", 0))
        boolean_version["activation"]["selected"][0]["evidence"]["contract"][
            "schemaVersion"
        ] = True
        self.assertEqual(
            skill_outcome.project_skill_outcome(
                boolean_version, {}, "model",
            )["aggregateState"],
            "invalid_contract",
        )

        too_many = _lifecycle(
            _selected("alpha", 0),
            _selected("beta", 1),
            _selected("gamma", 2),
        )
        self.assertEqual(
            skill_outcome.project_skill_outcome(
                too_many, {}, "model",
            )["aggregateState"],
            "invalid_contract",
        )


if __name__ == "__main__":
    unittest.main()
