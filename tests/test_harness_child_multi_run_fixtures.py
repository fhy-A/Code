"""Strict synthetic fixture contracts for H3-2B2 Child AgentRun replay."""

import hashlib
import json
import re
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from code_runtime.agent_protocol import normalize_agent_event


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "harness"
SCHEMA_PATH = FIXTURE_DIR / "multi-run-trace-suite-v2.schema.json"
SUITE_PATH = FIXTURE_DIR / "child-agent-multi-run-trace-suite.json"
EXPECTED_FIXTURE_SUITE_HASH = "0ab4fb75adfd3a0818db55f1e57b02fa5aabdcf9b6c156fd8827dfb98e7255da"


def canonical_hash(value):
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class HarnessChildMultiRunFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
        cls.scenario = cls.suite["scenarios"][0]
        cls.validator = Draft202012Validator(
            cls.schema,
            format_checker=FormatChecker(),
        )

    def schema_errors(self, suite):
        return sorted(
            self.validator.iter_errors(suite),
            key=lambda error: list(error.path),
        )

    def test_v2_schema_is_strict_versioned_and_accepts_the_child_suite(self):
        Draft202012Validator.check_schema(self.schema)
        self.assertEqual(self.schema_errors(self.suite), [])
        self.assertEqual(self.schema["properties"]["multiRunFixtureVersion"]["const"], 2)
        self.assertEqual(self.suite["multiRunFixtureVersion"], 2)
        self.assertFalse(self.schema["additionalProperties"])
        self.assertFalse(self.schema["$defs"]["scenario"]["additionalProperties"])

        mutated = json.loads(json.dumps(self.suite))
        mutated["scenarios"][0]["unexpectedLifecycleState"] = {}
        paths = [list(error.path) for error in self.validator.iter_errors(mutated)]
        self.assertIn(["scenarios", 0], paths)

    def test_root_and_child_role_branches_reject_cross_role_identity_fields(self):
        cases = (
            ("P1", "clientRequestId", ""),
            ("P1", "parentToolCallId", "T0"),
            ("P1", "agentDepth", 1),
            ("C1", "clientRequestId", "synthetic-child-request"),
            ("C1", "parentAgentRunId", ""),
            ("C1", "parentToolCallId", ""),
            ("C1", "agentDepth", 0),
        )
        for run_key, field, value in cases:
            with self.subTest(run=run_key, field=field):
                mutated = json.loads(json.dumps(self.suite))
                mutated["scenarios"][0]["identities"]["agentRuns"][run_key][field] = value
                self.assertTrue(self.schema_errors(mutated))

    def test_v2_counts_name_and_raw_hash_are_frozen_separately(self):
        self.assertEqual(len(self.suite["scenarios"]), 1)
        self.assertEqual(
            self.scenario["name"],
            "child-agent-out-of-order-terminal-parent-results",
        )
        self.assertEqual(len(self.scenario["runs"]), 3)
        self.assertEqual(
            sum(len(run["events"]) for run in self.scenario["runs"].values()),
            21,
        )
        self.assertEqual(len(self.scenario["schedule"]), 21)
        self.assertEqual(
            sum(entry["kind"] == "fact-marker" for entry in self.scenario["schedule"]),
            0,
        )
        self.assertEqual(len(self.scenario["checkpoints"]), 6)
        self.assertEqual(canonical_hash(self.suite), EXPECTED_FIXTURE_SUITE_HASH)

    def test_every_raw_event_satisfies_the_strict_production_protocol(self):
        for run_key, run in self.scenario["runs"].items():
            for event in run["events"]:
                with self.subTest(run=run_key, seq=event["seq"], type=event["type"]):
                    normalized = normalize_agent_event(
                        {"protocolVersion": 1, **event},
                        strict=True,
                    )
                    self.assertEqual(normalized["event"]["seq"], event["seq"])
                    self.assertEqual(normalized["event"]["type"], event["type"])
                    self.assertEqual(normalized["diagnostics"], [])

    def test_parent_child_identity_and_raw_event_mappings_close_four_ways(self):
        identities = self.scenario["identities"]["agentRuns"]
        parent = identities["P1"]
        child_keys = ["C1", "C2"]
        child_by_tool = {
            identities[key]["parentToolCallId"]: identities[key]["agentRunId"]
            for key in child_keys
        }

        self.assertEqual(parent["parentAgentRunId"], "")
        self.assertEqual(parent["parentToolCallId"], "")
        self.assertEqual(parent["agentDepth"], 0)
        for child_key in child_keys:
            child = identities[child_key]
            with self.subTest(child=child_key):
                self.assertEqual(child["parentAgentRunId"], parent["agentRunId"])
                self.assertEqual(child["agentDepth"], 1)
                self.assertEqual(child["clientRequestId"], "")

        parent_events = self.scenario["runs"]["P1"]["events"]
        first_model = next(
            event for event in parent_events
            if event["type"] == "model_completed" and event["data"]["round"] == 1
        )
        declared = [call["id"] for call in first_model["data"]["toolCalls"]]
        created = [
            (event["data"]["toolCallId"], event["data"]["childAgentRunId"])
            for event in parent_events if event["type"] == "child_agent_created"
        ]
        completed = [
            (
                event["data"]["toolCallId"],
                event["data"]["result"]["childAgentRunId"],
            )
            for event in parent_events if event["type"] == "tool_completed"
        ]

        self.assertEqual(declared, ["T1", "T2"])
        self.assertEqual(set(declared), set(child_by_tool))
        self.assertEqual(created, [(tool_id, child_by_tool[tool_id]) for tool_id in declared])
        self.assertEqual(completed, [(tool_id, child_by_tool[tool_id]) for tool_id in declared])

    def test_fixed_schedule_separates_child_terminal_and_parent_result_orders(self):
        runs = self.scenario["runs"]
        schedule = self.scenario["schedule"]
        child_keys = {
            key for key, identity in self.scenario["identities"]["agentRuns"].items()
            if identity["role"] == "child"
        }
        child_terminal = []
        parent_results = []
        child_terminal_steps = []
        parent_result_steps = []
        for entry in schedule:
            event = runs[entry["runKey"]]["events"][entry["eventSeq"] - 1]
            if entry["runKey"] in child_keys and event["type"] == "completed":
                child_terminal.append(entry["runKey"])
                child_terminal_steps.append(entry["step"])
            if entry["runKey"] == "P1" and event["type"] == "tool_completed":
                parent_results.append(event["data"]["toolCallId"])
                parent_result_steps.append(entry["step"])

        self.assertEqual(child_terminal, ["C2", "C1"])
        self.assertEqual(parent_results, ["T1", "T2"])
        self.assertLess(max(child_terminal_steps), min(parent_result_steps))

    def test_parent_has_one_post_child_final_answer_and_one_terminal(self):
        parent_events = self.scenario["runs"]["P1"]["events"]
        final_models = [
            event for event in parent_events
            if event["type"] == "model_completed"
            and event["data"]["round"] == 2
            and event["data"]["content"]
            and event["data"]["toolCalls"] == []
        ]
        parent_terminals = [
            event for event in parent_events
            if event["type"] in {"completed", "failed", "cancelled"}
        ]
        self.assertEqual(len(final_models), 1)
        self.assertEqual([event["type"] for event in parent_terminals], ["completed"])
        self.assertGreater(final_models[0]["seq"], 9)

    def test_v2_suite_contains_only_synthetic_sanitized_content(self):
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
