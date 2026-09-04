import hashlib
import json
import unittest

from code_runtime import skill_outcome


_RUN_ID = "run-skill-outcome"


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


def _execution(
    tool="read_file", *, outcome="succeeded", result=None, arguments=None,
    fingerprint=None,
):
    execution = {
        "name": tool,
        "status": "completed",
        "outcome": outcome,
        "fingerprint": fingerprint or hashlib.sha256(
            f"fixture:{tool}".encode("utf-8")
        ).hexdigest(),
        "result": result if result is not None else {"ok": outcome == "succeeded"},
    }
    if arguments is not None:
        execution["arguments"] = (
            json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
            if isinstance(arguments, dict) else arguments
        )
    return execution


def _project(lifecycle, executions, status, *, run_id=_RUN_ID):
    return skill_outcome.project_skill_outcome(
        lifecycle, executions, run_id, status,
    )


class TestSkillOutcomeProjection(unittest.TestCase):
    def test_observes_partial_then_satisfied_evidence_without_reusing_calls(self):
        lifecycle = _lifecycle(_selected("alpha", 0, [
            _requirement("inspect"),
            _requirement("write", "write_file", kind="artifact"),
        ]))
        initial = _project(lifecycle, {}, "tools")
        self.assertEqual(initial["aggregateState"], "observing")
        self.assertEqual(
            [item["missingCount"] for item in initial["skills"][0]["requirements"]],
            [1, 1],
        )

        executions = {
            "call-read": _execution(),
            "call-write-failed": _execution(
                "write_file", outcome="failed",
                result={"ok": False, "action": "write_file", "path": "failed.txt"},
            ),
        }
        partial = _project(lifecycle, executions, "model")
        inspect, write = partial["skills"][0]["requirements"]
        self.assertEqual((inspect["acceptedSucceeded"], inspect["missingCount"]), (1, 0))
        self.assertEqual((write["acceptedFailed"], write["missingCount"]), (0, 1))
        self.assertEqual(write["rejected"], 1)
        self.assertEqual(partial["aggregateState"], "observing")

        executions["call-write-ready"] = _execution(
            "write_file",
            result={"ok": True, "action": "write_file", "path": "ready.txt"},
        )
        satisfied = _project(lifecycle, executions, "completed")
        self.assertEqual(satisfied["aggregateState"], "satisfied")
        self.assertEqual(satisfied["summary"]["acceptedSucceeded"], 2)
        self.assertEqual(satisfied["summary"]["acceptedFailed"], 0)
        self.assertEqual(satisfied["summary"]["satisfiedRequirements"], 2)

        receipt = inspect["actual"][0]
        self.assertEqual(receipt["version"], 1)
        self.assertEqual(receipt["source"], "server_unique")
        self.assertEqual(receipt["qualification"], "tool_execution")
        self.assertEqual(receipt["skill"]["name"], "alpha")

    def test_same_skill_multi_requirement_claim_is_ambiguous_and_counts_toward_none(self):
        lifecycle = _lifecycle(_selected("alpha", 0, [
            _requirement("inspect-a"),
            _requirement("inspect-b"),
        ]))
        projection = _project(
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
        projection = _project(
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
        projection = _project(
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
        projection = _project(lifecycle, executions, "completed")
        requirement = projection["skills"][0]["requirements"][0]
        self.assertEqual(requirement["acceptedSucceeded"], 1)
        self.assertEqual(requirement["acceptedFailed"], 0)
        self.assertEqual(requirement["rejected"], 2)
        self.assertEqual(
            [item["claimState"] for item in requirement["actual"]],
            ["rejected", "rejected", "accepted"],
        )
        serialized = json.dumps(projection)
        self.assertNotIn("failed-secret.txt", serialized)
        self.assertNotIn("ready-secret.txt", serialized)

    def test_failed_receipt_is_auditable_but_never_satisfies_and_binds_run(self):
        lifecycle = _lifecycle(_selected("alpha", 0))
        execution = _execution(
            outcome="failed",
            arguments={"path": "SECRET_ARGUMENT.txt"},
            result={"ok": False, "error": "SECRET_RESULT"},
        )
        first = _project(lifecycle, {"failed-call": execution}, "completed")
        repeated = _project(lifecycle, {"failed-call": execution}, "completed")
        other_run = _project(
            lifecycle, {"failed-call": execution}, "completed", run_id="other-run",
        )
        requirement = first["skills"][0]["requirements"][0]
        receipt = requirement["actual"][0]

        self.assertEqual(first["version"], 2)
        self.assertEqual((requirement["acceptedFailed"], requirement["missingCount"]), (1, 1))
        self.assertRegex(receipt["receiptId"], r"^sr1_[0-9a-f]{64}$")
        self.assertEqual(receipt["receiptId"], repeated["skills"][0]["requirements"][0]["actual"][0]["receiptId"])
        self.assertNotEqual(receipt["receiptId"], other_run["skills"][0]["requirements"][0]["actual"][0]["receiptId"])
        self.assertEqual(receipt["executionFingerprint"], execution["fingerprint"])
        self.assertNotIn("SECRET", json.dumps(first))

    def test_receipt_id_binds_every_authoritative_identity_component(self):
        lifecycle = _lifecycle(_selected("alpha", 0))
        execution = _execution()

        def receipt_id(source, executions=None, *, run_id=_RUN_ID):
            projection = _project(
                source,
                executions or {"call-a": execution},
                "completed",
                run_id=run_id,
            )
            return projection["skills"][0]["requirements"][0]["actual"][0][
                "receiptId"
            ]

        baseline = receipt_id(lifecycle)
        variants = []
        for path, value in (
            (("role",), "modifier"),
            (("skillContentHash",), _sha("different-skill")),
            (("evidence", "contentHash"), _sha("different-evidence")),
            (("evidence", "contract", "requirements", 0, "id"), "different-id"),
        ):
            changed = json.loads(json.dumps(lifecycle))
            target = changed["activation"]["selected"][0]
            for component in path[:-1]:
                target = target[component]
            target[path[-1]] = value
            variants.append(receipt_id(changed))
        variants.extend((
            receipt_id(lifecycle, {"call-b": execution}),
            receipt_id(lifecycle, {"call-a": _execution(fingerprint="f" * 64)}),
            receipt_id(lifecycle, {"call-a": _execution(outcome="failed")}),
            receipt_id(lifecycle, run_id="different-run"),
        ))
        self.assertTrue(all(item != baseline for item in variants))
        self.assertEqual(len(set(variants)), len(variants))

    def test_each_explicit_skill_target_resolves_cross_skill_candidates(self):
        for tool, field in (
            ("use_skill", "name"),
            ("check_skill_dependencies", "name"),
            ("read_skill_resource", "skill"),
        ):
            with self.subTest(tool=tool):
                lifecycle = _lifecycle(
                    _selected("alpha", 0, [_requirement("alpha-use", tool)]),
                    _selected("beta", 1, [_requirement("beta-use", tool)]),
                )
                projection = _project(lifecycle, {
                    f"{tool}-call": _execution(tool, arguments={field: "beta"}),
                }, "completed")
                alpha = projection["skills"][0]["requirements"][0]
                beta = projection["skills"][1]["requirements"][0]
                self.assertEqual(alpha["acceptedSucceeded"], 0)
                self.assertEqual(beta["acceptedSucceeded"], 1)
                self.assertEqual(beta["actual"][0]["source"], "explicit_skill_target")

    def test_explicit_target_malformed_inactive_and_conflicting_never_fall_back(self):
        lifecycle = _lifecycle(
            _selected("alpha", 0, [_requirement("alpha-read", "read_file")]),
            _selected("beta", 1, [_requirement("beta-use", "use_skill")]),
        )
        cases = (
            ("malformed", "{", "explicit_skill_target_malformed"),
            ("inactive", {"name": "gamma"}, "explicit_skill_target_inactive"),
            ("conflict", {"name": "alpha"}, "explicit_skill_target_conflict"),
        )
        for label, arguments, reason in cases:
            with self.subTest(label=label):
                projection = _project(lifecycle, {
                    f"call-{label}": _execution("use_skill", arguments=arguments),
                }, "completed")
                requirement = projection["skills"][1]["requirements"][0]
                self.assertEqual(requirement["acceptedSucceeded"], 0)
                self.assertEqual(requirement["actual"][0]["reason"], reason)

    def test_runtime_single_skill_resolves_but_bad_runtime_identity_never_falls_back(self):
        lifecycle = _lifecycle(
            _selected("alpha", 0, [_requirement("alpha-run", "run_command")]),
            _selected("beta", 1, [_requirement("beta-run", "run_command")]),
        )
        result = {
            "ok": True,
            "skillRuntime": {
                "version": 1,
                "skills": [{"skill": "beta", "capability": "inspect"}],
                "managedPythonApplied": False,
                "managedNodeApplied": False,
            },
        }
        projection = _project(lifecycle, {
            "runtime-call": _execution("run_command", result=result),
        }, "completed")
        receipt = projection["skills"][1]["requirements"][0]["actual"][0]
        self.assertEqual(receipt["source"], "runtime_single_skill")

        for label, skills, reason in (
            ("ambiguous", [{"skill": "alpha"}, {"skill": "beta"}], "runtime_skill_identity_ambiguous"),
            ("inactive", [{"skill": "gamma"}], "runtime_single_skill_inactive"),
            ("malformed", "not-a-list", "runtime_skill_identity_malformed"),
        ):
            with self.subTest(label=label):
                bad_result = {"ok": True, "skillRuntime": {"version": 1, "skills": skills}}
                bad = _project(lifecycle, {
                    f"runtime-{label}": _execution("run_command", result=bad_result),
                }, "completed")
                requirements = [item["requirements"][0] for item in bad["skills"]]
                self.assertEqual(sum(item["acceptedSucceeded"] for item in requirements), 0)
                self.assertTrue(all(item["actual"][0]["reason"] == reason for item in requirements))

        bad_version_result = {
            "ok": True,
            "skillRuntime": {"version": True, "skills": [{"skill": "beta"}]},
        }
        bad_version = _project(lifecycle, {
            "runtime-version": _execution("run_command", result=bad_version_result),
        }, "completed")
        requirements = [item["requirements"][0] for item in bad_version["skills"]]
        self.assertTrue(all(
            item["actual"][0]["reason"] == "runtime_skill_identity_malformed"
            for item in requirements
        ))

    def test_invalid_fingerprint_and_run_identity_produce_no_receipt(self):
        lifecycle = _lifecycle(_selected("alpha", 0))
        invalid_fingerprint = _project(lifecycle, {
            "bad-fingerprint": _execution(fingerprint="SECRET_FINGERPRINT"),
        }, "completed")
        requirement = invalid_fingerprint["skills"][0]["requirements"][0]
        self.assertEqual(requirement["acceptedSucceeded"], 0)
        self.assertEqual(requirement["actual"][0]["reason"], "execution_fingerprint_invalid")
        self.assertEqual(invalid_fingerprint["summary"]["invalidExecutionFingerprints"], 1)
        self.assertNotIn("SECRET_FINGERPRINT", json.dumps(invalid_fingerprint))

        invalid_run = _project(
            lifecycle, {"bad-run": _execution()}, "completed", run_id="",
        )
        requirement = invalid_run["skills"][0]["requirements"][0]
        self.assertEqual(requirement["actual"][0]["reason"], "run_identity_invalid")
        self.assertEqual(invalid_run["summary"]["invalidRunIdentities"], 1)

    def test_aggregate_distinguishes_terminal_and_contract_states(self):
        ready = _lifecycle(_selected("alpha", 0))
        self.assertEqual(
            _project(ready, {}, "completed")["aggregateState"],
            "terminal_gaps",
        )
        self.assertEqual(
            _project(ready, {}, "failed")["aggregateState"],
            "failed",
        )
        self.assertEqual(
            _project(ready, {}, "cancelled")["aggregateState"],
            "cancelled",
        )
        missing = _lifecycle(_selected("alpha", 0, evidence_state="missing"))
        invalid = _lifecycle(_selected("alpha", 0, evidence_state="invalid"))
        self.assertEqual(
            _project(missing, {}, "model")["aggregateState"],
            "missing_contract",
        )
        self.assertEqual(
            _project(invalid, {}, "model")["aggregateState"],
            "invalid_contract",
        )
        self.assertEqual(
            _project(_lifecycle(), {}, "completed")["aggregateState"],
            "not_applicable",
        )

    def test_projection_is_bounded_deterministic_and_hides_unsafe_call_ids(self):
        lifecycle = _lifecycle(_selected("alpha", 0))
        executions = {
            f"failed-{index:02d}": _execution(outcome="failed")
            for index in range(40)
        }
        executions["SECRET\nCALL"] = _execution(outcome="failed")
        projection = _project(lifecycle, executions, "failed")
        reversed_projection = _project(
            lifecycle, dict(reversed(list(executions.items()))), "failed",
        )
        self.assertEqual(projection, reversed_projection)
        requirement = projection["skills"][0]["requirements"][0]
        self.assertEqual(requirement["acceptedFailed"], 40)
        self.assertEqual(requirement["rejected"], 1)
        self.assertEqual(len(requirement["actual"]), skill_outcome.MAX_ACTUAL_CLAIMS)
        self.assertEqual(requirement["actualTruncated"], 25)
        self.assertEqual(projection["summary"]["unsafeCallReferences"], 1)
        serialized = json.dumps(projection)
        self.assertNotIn("SECRET", serialized)
        self.assertIn("call-sha256:", serialized)

    def test_malformed_input_is_total_and_contains_no_source_payload(self):
        projection = _project(
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
            _project(
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
            _project(
                too_many, {}, "model",
            )["aggregateState"],
            "invalid_contract",
        )

        duplicate = _lifecycle(_selected("alpha", 0), _selected("alpha", 1))
        self.assertEqual(
            _project(duplicate, {"call": _execution()}, "completed")["aggregateState"],
            "invalid_contract",
        )


if __name__ == "__main__":
    unittest.main()
