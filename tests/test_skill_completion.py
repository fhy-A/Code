import copy
import hashlib
import unittest

from code_runtime import skill_completion, skill_outcome


def _sha(value):
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def _requirement(requirement_id="inspect", tool="read_file", minimum=1):
    return {
        "id": requirement_id,
        "type": "tool_execution",
        "tool": tool,
        "minCount": minimum,
    }


def _contract(requirements=None, kinds=None):
    return {
        "schemaVersion": 2,
        "requirements": requirements or [_requirement()],
        "enforcement": {
            "schemaVersion": 2,
            "mode": "owner_completion_once",
            "activationKinds": kinds or ["automatic", "explicit"],
        },
    }


def _skill(name="alpha", role="owner", requirements=None, *, capabilities=None):
    return {
        "name": name,
        "role": role,
        "skillContentHash": _sha(f"skill:{name}"),
        "evidence": {
            "state": "ready",
            "contentHash": _sha(f"evidence:{name}"),
            "contract": _contract(requirements),
        },
        "dependency": {
            "state": "ready" if capabilities else "missing",
            "capabilities": list(capabilities or []),
            **({"manifestHash": _sha(f"dependency:{name}")} if capabilities else {}),
        },
    }


def _lifecycle(owner=None, *modifiers, kind="explicit"):
    return {
        "activation": {
            "intentKind": kind,
            "selected": [owner or _skill(), *modifiers],
        },
    }


_SPECS = {
    "read_file": {"effect": "read", "idempotent": True},
    "use_skill": {"effect": "read", "idempotent": True},
    "write_file": {"effect": "file_mutation", "idempotent": True},
    "run_command": {"effect": "command", "idempotent": False},
    "request_user_input": {"effect": "interaction", "idempotent": True},
    "goal_complete_step": {"effect": "goal_metadata", "idempotent": True},
}


def _plan(lifecycle=None, specs=None, budgets=None):
    return skill_completion.build_plan(
        lifecycle or _lifecycle(), specs or _SPECS, budgets or [], enabled=True,
    )


def _execution(tool="read_file", outcome="succeeded", *, arguments=None, suffix="a"):
    return {
        "name": tool,
        "arguments": arguments or {},
        "status": "completed",
        "outcome": outcome,
        "fingerprint": hashlib.sha256(f"{tool}:{suffix}".encode()).hexdigest(),
        "result": {"ok": outcome == "succeeded"},
    }


def _outcome(lifecycle, executions=None):
    return skill_outcome.project_skill_outcome(
        lifecycle, executions or {}, "run-completion-test", "model",
    )


def _call(tool="read_file", call_id="repair-a", *, arguments=None, suffix="a"):
    return {
        "id": call_id,
        "function": {"name": tool, "arguments": "{}"},
        "arguments": arguments or {},
        "parseError": "",
        "validationErrors": [],
        "fingerprint": hashlib.sha256(f"{tool}:{suffix}".encode()).hexdigest(),
    }


class TestSkillCompletionContract(unittest.TestCase):
    def assert_code(self, expected, callback):
        with self.assertRaises(skill_completion.SkillCompletionError) as raised:
            callback()
        self.assertEqual(raised.exception.code, expected)

    def test_shared_v2_contract_normalizer_is_exact_and_keeps_v1_separate(self):
        normalized = skill_outcome.normalize_completion_contract(_contract())
        self.assertEqual(normalized, _contract())
        self.assertIsNone(skill_outcome.normalize_completion_contract({
            "schemaVersion": 1,
            "requirements": [_requirement()],
        }))

        variants = []
        for path, value in (
            (("extra",), True),
            (("schemaVersion",), True),
            (("enforcement", "schemaVersion"), 1),
            (("enforcement", "mode"), "explicit_only"),
            (("enforcement", "activationKinds"), []),
            (("enforcement", "activationKinds"), ["explicit", "automatic"]),
            (("enforcement", "activationKinds"), ["explicit", "explicit"]),
            (("requirements", 0, "extra"), True),
            (("requirements", 0, "minCount"), True),
        ):
            changed = copy.deepcopy(_contract())
            target = changed
            for component in path[:-1]:
                target = target[component]
            target[path[-1]] = value
            variants.append(changed)
        duplicate = _contract([_requirement(), _requirement()])
        variants.append(duplicate)
        for value in variants:
            with self.subTest(value=value):
                self.assertIsNone(skill_outcome.normalize_completion_contract(value))

    def test_admission_is_default_off_activation_scoped_and_fail_closed(self):
        lifecycle = _lifecycle()
        self.assertIsNone(skill_completion.build_plan(
            lifecycle, _SPECS, [], enabled=False,
        ))
        explicit_only = copy.deepcopy(lifecycle)
        explicit_only["activation"]["intentKind"] = "automatic"
        explicit_only["activation"]["selected"][0]["evidence"]["contract"][
            "enforcement"
        ]["activationKinds"] = ["explicit"]
        self.assertIsNone(skill_completion.build_plan(
            explicit_only, _SPECS, [], enabled=True,
        ))
        plan = _plan(lifecycle)
        self.assertEqual(plan["phase"], "armed")
        self.assertEqual(plan["policy"]["owner"]["name"], "alpha")

        cases = {
            "unknown tool": (_lifecycle(_skill(requirements=[_requirement(tool="unknown")])), _SPECS, []),
            "empty effect": (lifecycle, {"read_file": {"effect": "", "idempotent": True}}, []),
            "interaction": (_lifecycle(_skill(requirements=[_requirement(tool="request_user_input")])), _SPECS, []),
            "goal metadata": (_lifecycle(_skill(requirements=[_requirement(tool="goal_complete_step")])), _SPECS, []),
            "side effect count": (_lifecycle(_skill(requirements=[_requirement(tool="write_file", minimum=2)])), _SPECS, []),
            "sum over eight": (_lifecycle(_skill(requirements=[_requirement(minimum=9)])), _SPECS, []),
            "budget too small": (lifecycle, _SPECS, [{"tools": ["read_file"], "limit": 0}]),
        }
        for label, arguments in cases.items():
            with self.subTest(label=label):
                self.assert_code(
                    "skill_completion_contract_unenforceable",
                    lambda arguments=arguments: skill_completion.build_plan(
                        *arguments, enabled=True,
                    ),
                )

    def test_admission_rejects_duplicate_modifier_and_foreign_command_identity(self):
        duplicate_owner = _skill(requirements=[
            _requirement("a"), _requirement("b"),
        ])
        overlap_modifier = _skill(
            "beta", "modifier", [_requirement("beta-inspect")],
        )
        foreign_runtime = _skill(
            "beta", "modifier", [_requirement("beta-read")], capabilities=["inspect"],
        )
        command_owner = _skill(requirements=[_requirement(tool="run_command")])
        for lifecycle in (
            _lifecycle(duplicate_owner),
            _lifecycle(_skill(), overlap_modifier),
            _lifecycle(command_owner, foreign_runtime),
        ):
            with self.subTest(lifecycle=lifecycle):
                self.assert_code(
                    "skill_completion_contract_unenforceable",
                    lambda lifecycle=lifecycle: _plan(lifecycle),
                )

    def test_outcome_classifies_only_missing_and_failed_reads_as_recoverable(self):
        lifecycle = _lifecycle()
        plan = _plan(lifecycle)
        missing = skill_completion.evaluate(plan, _outcome(lifecycle), _SPECS)
        self.assertEqual(missing["status"], "recoverable")
        self.assertEqual(missing["allowedCalls"], [{
            "requirementId": "inspect", "tool": "read_file", "maxCalls": 1,
        }])

        succeeded = skill_completion.evaluate(
            plan, _outcome(lifecycle, {"read-ok": _execution()}), _SPECS,
        )
        self.assertEqual(succeeded["status"], "satisfied")
        failed_read = skill_completion.evaluate(
            plan,
            _outcome(lifecycle, {"read-failed": _execution(outcome="failed")}),
            _SPECS,
        )
        self.assertEqual(failed_read["status"], "recoverable")
        self.assertEqual(failed_read["gaps"][0]["class"], "failed_read")

        write_lifecycle = _lifecycle(
            _skill(requirements=[_requirement(tool="write_file")]),
        )
        failed_write = skill_completion.evaluate(
            _plan(write_lifecycle),
            _outcome(write_lifecycle, {
                "write-failed": _execution("write_file", "failed"),
            }),
            _SPECS,
        )
        self.assertEqual(failed_write["status"], "fatal")
        self.assertEqual(failed_write["gaps"][0]["class"], "failed_side_effect")

        duplicate_refs = _outcome(lifecycle, {7: _execution(), "7": _execution(suffix="b")})
        duplicate_result = skill_completion.evaluate(plan, duplicate_refs, _SPECS)
        self.assertEqual(duplicate_result["status"], "fatal")
        self.assertEqual(duplicate_result["gaps"][0]["class"], "duplicate_reference")

    def test_continuation_state_is_deterministic_and_forbidden_phases_fail(self):
        lifecycle = _lifecycle()
        plan = _plan(lifecycle)
        evaluation = skill_completion.evaluate(plan, _outcome(lifecycle), _SPECS)
        first = skill_completion.begin_continuation(
            plan, evaluation, "run-a", 3, "candidate",
        )
        repeated = skill_completion.begin_continuation(
            plan, evaluation, "run-a", 3, "candidate",
        )
        self.assertEqual(first, repeated)
        self.assertRegex(first["continuationId"], r"^sce1_[0-9a-f]{64}$")
        self.assertEqual(
            skill_completion.normalize_plan(first, lifecycle, _SPECS, []), first,
        )

        invalid = []
        dirty_armed = copy.deepcopy(plan)
        dirty_armed["triggerRound"] = 1
        invalid.append(dirty_armed)
        incomplete = copy.deepcopy(plan)
        incomplete["phase"] = "continuing"
        invalid.append(incomplete)
        finalizing_without_batch = copy.deepcopy(first)
        finalizing_without_batch["phase"] = "finalizing"
        invalid.append(finalizing_without_batch)
        widened_calls = copy.deepcopy(first)
        widened_calls["allowedCalls"][0]["maxCalls"] = 2
        invalid.append(widened_calls)
        oversized_batch = copy.deepcopy(first)
        oversized_batch["toolBatchCallIds"] = [f"repair-{index}" for index in range(9)]
        invalid.append(oversized_batch)
        extra = copy.deepcopy(first)
        extra["modelRoundsUsed"] = 1
        invalid.append(extra)
        changed_policy = copy.deepcopy(first)
        changed_policy["policy"]["owner"]["name"] = "beta"
        invalid.append(changed_policy)
        for value in invalid:
            with self.subTest(value=value):
                self.assert_code(
                    "skill_completion_state_invalid",
                    lambda value=value: skill_completion.normalize_plan(
                        value, lifecycle, _SPECS, [],
                    ),
                )

    def test_repair_batch_is_one_shot_bounded_and_targeted(self):
        lifecycle = _lifecycle()
        plan = _plan(lifecycle)
        evaluation = skill_completion.evaluate(plan, _outcome(lifecycle), _SPECS)
        continuing = skill_completion.begin_continuation(
            plan, evaluation, "run-a", 1, "candidate",
        )
        call = _call()
        self.assertEqual(
            skill_completion.validate_repair_batch(
                continuing, [call], _SPECS, {},
            ),
            ["repair-a"],
        )
        batched = skill_completion.advance(continuing, "continuing", ["repair-a"])
        self.assert_code(
            "skill_completion_repair_batch_invalid",
            lambda: skill_completion.validate_repair_batch(
                batched, [_call(call_id="repair-b")], _SPECS, {},
            ),
        )

        targeted_lifecycle = _lifecycle(
            _skill(requirements=[_requirement(tool="use_skill")]),
        )
        targeted = skill_completion.begin_continuation(
            _plan(targeted_lifecycle),
            skill_completion.evaluate(
                _plan(targeted_lifecycle), _outcome(targeted_lifecycle), _SPECS,
            ),
            "run-target", 1, "candidate",
        )
        self.assertEqual(skill_completion.validate_repair_batch(
            targeted, [_call("use_skill", arguments={"name": "alpha"})], _SPECS, {},
        ), ["repair-a"])
        self.assert_code(
            "skill_completion_repair_batch_invalid",
            lambda: skill_completion.validate_repair_batch(
                targeted,
                [_call("use_skill", arguments={"name": "beta"})],
                _SPECS,
                {},
            ),
        )

        write_lifecycle = _lifecycle(
            _skill(requirements=[_requirement(tool="write_file")]),
        )
        write_plan = _plan(write_lifecycle)
        write_continuing = skill_completion.begin_continuation(
            write_plan,
            skill_completion.evaluate(write_plan, _outcome(write_lifecycle), _SPECS),
            "run-write", 1, "candidate",
        )
        self.assert_code(
            "skill_completion_repair_batch_invalid",
            lambda: skill_completion.validate_repair_batch(
                write_continuing,
                [_call("write_file")],
                _SPECS,
                {"prior-write": _execution("write_file", "failed")},
            ),
        )


if __name__ == "__main__":
    unittest.main()
