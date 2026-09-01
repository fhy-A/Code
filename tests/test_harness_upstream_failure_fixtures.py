"""Strict H3-2C1 fixture and production-evidence contracts."""

import hashlib
import json
import re
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

import server as server_mod
from code_runtime.agent_protocol import normalize_agent_event


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "harness"
SCHEMA_PATH = FIXTURE_DIR / "upstream-failure-recovery-trace-suite.schema.json"
SUITE_PATH = FIXTURE_DIR / "upstream-failure-recovery-trace-suite.json"
EXPECTED_FIXTURE_SUITE_HASH = "3278b2cfed32b5d06d8c0e0b4c07f84b065b3c0f41803d13bbbe211c8879a6c1"


def canonical_hash(value):
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class EvidenceContractError(AssertionError):
    def __init__(self, path, expected, actual):
        super().__init__(f"{path}: expected {expected!r}, got {actual!r}")
        self.path = path
        self.expected = expected
        self.actual = actual


def require_equal(actual, expected, path):
    if actual != expected:
        raise EvidenceContractError(path, expected, actual)


def assert_source_contract(fixture):
    """Make sourceFacts executable against production classification and raw events."""
    facts = fixture["sourceFacts"]
    runtime_input = facts["runtimeInput"]
    events = fixture["events"]
    event_types = [event["type"] for event in events]
    require_equal(
        facts["agentEventTypes"],
        event_types,
        "$.sourceFacts.agentEventTypes",
    )

    if facts["caseKind"] == "http-failure":
        require_equal(
            facts["upstreamStatus"],
            runtime_input["httpStatus"],
            "$.sourceFacts.upstreamStatus",
        )
        require_equal(
            facts["upstreamMessage"],
            runtime_input["httpMessage"],
            "$.sourceFacts.upstreamMessage",
        )
        error_code, transient = server_mod._classify_runtime_failure(
            facts["upstreamStatus"],
            facts["upstreamMessage"],
        )
        require_equal(
            facts["runtimeErrorCode"],
            error_code,
            "$.sourceFacts.runtimeErrorCode",
        )
        require_equal(
            facts["runtimeTransient"],
            transient,
            "$.sourceFacts.runtimeTransient",
        )
        require_equal(
            facts["agentRunErrorCode"],
            error_code,
            "$.sourceFacts.agentRunErrorCode",
        )
        require_equal(events[-1]["data"]["errorCode"], error_code, "$.events[2].data.errorCode")
        require_equal(events[-1]["data"]["error"], facts["upstreamMessage"], "$.events[2].data.error")
        require_equal(event_types, ["created", "model_started", "failed"], "$.events")
        return

    if facts["caseKind"] == "first-response-timeout":
        require_equal(
            facts["upstreamStatus"],
            runtime_input["httpStatus"],
            "$.sourceFacts.upstreamStatus",
        )
        require_equal(
            facts["runtimeErrorCode"],
            "model_response_timeout",
            "$.sourceFacts.runtimeErrorCode",
        )
        require_equal(facts["runtimeTransient"], True, "$.sourceFacts.runtimeTransient")
        require_equal(
            facts["agentRunErrorCode"],
            "model_response_timeout",
            "$.sourceFacts.agentRunErrorCode",
        )
        require_equal(
            events[-1]["data"]["errorCode"],
            "model_response_timeout",
            "$.events[2].data.errorCode",
        )
        require_equal(event_types, ["created", "model_started", "failed"], "$.events")
        return

    require_equal(facts["upstreamStatus"], 0, "$.sourceFacts.upstreamStatus")
    require_equal(runtime_input["httpStatus"], 200, "$.sourceFacts.runtimeInput.httpStatus")
    require_equal(facts["runtimeErrorCode"], "", "$.sourceFacts.runtimeErrorCode")
    require_equal(facts["runtimeTransient"], False, "$.sourceFacts.runtimeTransient")
    require_equal(facts["agentRunErrorCode"], "", "$.sourceFacts.agentRunErrorCode")
    first_outcome = (
        "empty" if runtime_input["responseMode"] == "empty-then-content"
        else "reasoning_only"
    )
    require_equal(
        event_types,
        [
            "created",
            "model_started",
            "model_completed",
            "model_recovery",
            "model_started",
            "model_completed",
            "completed",
        ],
        "$.events",
    )
    require_equal(events[2]["data"]["outcome"], first_outcome, "$.events[2].data.outcome")
    require_equal(events[3]["data"]["reason"], first_outcome, "$.events[3].data.reason")
    require_equal(events[5]["data"]["outcome"], "completed", "$.events[5].data.outcome")
    require_equal(events[5]["data"]["content"], runtime_input["finalContent"], "$.events[5].data.content")


class HarnessUpstreamFailureFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(
            cls.schema,
            format_checker=FormatChecker(),
        )

    def schema_errors(self, suite):
        return sorted(self.validator.iter_errors(suite), key=lambda error: list(error.path))

    def test_schema_and_evidence_profile_are_strict_versioned_and_accepted(self):
        Draft202012Validator.check_schema(self.schema)
        self.assertEqual(self.schema_errors(self.suite), [])
        self.assertFalse(self.schema["additionalProperties"])
        self.assertFalse(self.schema["$defs"]["sourceFacts"]["additionalProperties"])
        self.assertEqual(self.suite["fixtureVersion"], 1)
        self.assertEqual(self.suite["evidenceProfile"], {
            "id": "h3-2c1-upstream-failure-non-action",
            "version": 1,
            "replayPayload": "single-run-fixture-v1",
            "productionEvidence": "model-runtime-agent-run-integration-v1",
        })

        cases = (
            (("evidenceProfile", "version"), 2, ["evidenceProfile", "version"]),
            (("evidenceProfile", "replayPayload"), "generic-fixture-v1", ["evidenceProfile", "replayPayload"]),
            (("fixtures", 0, "sourceFacts", "unexpected"), True, ["fixtures", 0, "sourceFacts"]),
        )
        for keys, value, expected_path in cases:
            with self.subTest(keys=keys):
                mutated = deepcopy(self.suite)
                target = mutated
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value
                self.assertIn(
                    expected_path,
                    [list(error.path) for error in self.schema_errors(mutated)],
                )

    def test_counts_names_and_raw_hash_are_frozen_as_an_independent_suite(self):
        self.assertEqual(len(self.suite["fixtures"]), 6)
        self.assertEqual(sum(len(item["events"]) for item in self.suite["fixtures"]), 26)
        self.assertEqual(sum(len(item["checkpoints"]) for item in self.suite["fixtures"]), 16)
        self.assertEqual(sum(len(item["recoveryPoints"]) for item in self.suite["fixtures"]), 0)
        self.assertEqual(
            [item["name"] for item in self.suite["fixtures"]],
            [
                "upstream-401-config-terminal",
                "upstream-429-transient-terminal",
                "upstream-502-transient-terminal",
                "model-first-response-timeout-terminal",
                "model-empty-output-recovery-current",
                "model-reasoning-only-recovery-current",
            ],
        )
        self.assertEqual(canonical_hash(self.suite), EXPECTED_FIXTURE_SUITE_HASH)

    def test_every_raw_event_satisfies_the_strict_production_protocol(self):
        for fixture in self.suite["fixtures"]:
            for event in fixture["events"]:
                with self.subTest(fixture=fixture["name"], seq=event["seq"]):
                    normalized = normalize_agent_event(
                        {"protocolVersion": 1, **event},
                        strict=True,
                    )
                    self.assertEqual(normalized["diagnostics"], [])
                    self.assertEqual(normalized["event"]["type"], event["type"])

    def test_source_facts_execute_against_production_classification_and_raw_events(self):
        for fixture in self.suite["fixtures"]:
            with self.subTest(fixture=fixture["name"]):
                assert_source_contract(fixture)

        self.assertEqual(
            server_mod._classify_runtime_failure(
                401,
                "Synthetic token has no access to model synthetic-model.",
            ),
            ("model_access_denied", False),
        )

    def test_source_fact_mutations_fail_at_frozen_contract_paths(self):
        by_name = {item["name"]: item for item in self.suite["fixtures"]}
        cases = (
            ("upstream-401-config-terminal", "upstreamStatus", 429, "$.sourceFacts.upstreamStatus"),
            ("upstream-429-transient-terminal", "runtimeErrorCode", "config_error", "$.sourceFacts.runtimeErrorCode"),
            ("upstream-502-transient-terminal", "runtimeTransient", False, "$.sourceFacts.runtimeTransient"),
            ("model-first-response-timeout-terminal", "agentRunErrorCode", "upstream_error", "$.sourceFacts.agentRunErrorCode"),
        )
        for name, field, value, expected_path in cases:
            with self.subTest(name=name, field=field):
                mutated = deepcopy(by_name[name])
                mutated["sourceFacts"][field] = value
                with self.assertRaises(EvidenceContractError) as raised:
                    assert_source_contract(mutated)
                self.assertEqual(raised.exception.path, expected_path)

        mutated = deepcopy(by_name["model-empty-output-recovery-current"])
        mutated["events"][3], mutated["events"][4] = mutated["events"][4], mutated["events"][3]
        with self.assertRaises(EvidenceContractError) as raised:
            assert_source_contract(mutated)
        self.assertEqual(raised.exception.path, "$.sourceFacts.agentEventTypes")

        mutated = deepcopy(by_name["upstream-502-transient-terminal"])
        mutated["events"][2]["data"]["errorCode"] = "config_error"
        with self.assertRaises(EvidenceContractError) as raised:
            assert_source_contract(mutated)
        self.assertEqual(raised.exception.path, "$.events[2].data.errorCode")

    def test_fallback_profile_is_explicitly_limited_to_one_representative_status(self):
        tested = [
            item for item in self.suite["fixtures"]
            if item["sourceFacts"]["fallback"]["tested"]
        ]
        self.assertEqual([item["name"] for item in tested], ["upstream-502-transient-terminal"])
        self.assertEqual(tested[0]["sourceFacts"]["fallback"], {
            "tested": True,
            "firstAttemptStatus": 502,
            "keyCount": 2,
            "expectedCalls": 2,
            "expectedRuntimeStatus": "completed",
            "scope": "representative-status-only",
        })

    def test_non_action_cases_freeze_current_order_without_model_pending(self):
        fixtures = [
            item for item in self.suite["fixtures"]
            if item["sourceFacts"]["caseKind"] == "non-action"
        ]
        for fixture in fixtures:
            with self.subTest(fixture=fixture["name"]):
                event_types = [event["type"] for event in fixture["events"]]
                self.assertNotIn("model_pending", event_types)
                self.assertEqual(
                    [event["data"]["outcome"] for event in fixture["events"] if event["type"] == "model_completed"],
                    [fixture["events"][2]["data"]["outcome"], "completed"],
                )

    def test_suite_is_synthetic_and_contains_no_live_credentials_or_locations(self):
        serialized = json.dumps(self.suite, ensure_ascii=False)
        for forbidden in (
            r"(?i)authorization\s*:",
            r"(?i)bearer\s+",
            r"(?i)cookie\s*:",
            r"(?i)sk-[a-z0-9]",
            r"(?i)api[_ -]?key",
            r"[A-Za-z]:\\",
            r"https?://",
        ):
            with self.subTest(pattern=forbidden):
                self.assertIsNone(re.search(forbidden, serialized))
        self.assertIn("Synthetic", serialized)


if __name__ == "__main__":
    unittest.main()
