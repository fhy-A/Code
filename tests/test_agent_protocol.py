"""H1-1 contract tests for canonical Agent events and state invariants."""

import json
import unittest
from pathlib import Path

import agent_protocol


ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = ROOT / "docs" / "harness" / "h0-1-fact-inventory.json"
TRACE_SUITE_PATH = ROOT / "tests" / "fixtures" / "harness" / "trace-suite.json"


def _field_value(field):
    if field in {
        "round",
        "attempt",
        "maxAttempts",
        "maxRounds",
        "contextLimit",
        "contextWindowTokens",
        "contextBudgetTokens",
        "availableInputTokens",
        "compressionTriggerTokens",
        "estimatedTokensBefore",
        "estimatedTokensAfter",
        "threshold",
        "compactedMessageCount",
        "retainedMessageCount",
        "failureCount",
        "count",
        "pendingCount",
    }:
        return 1
    if field in {"allowedTools", "toolBudgets", "workspaceRoots", "toolCalls", "argumentAliases", "questions", "steerIds"}:
        return []
    if field in {"usage", "result"}:
        return {}
    if field in {
        "replayed", "forcedFinal", "legacyPendingInput",
        "contextWindowHard", "budgetClamped", "budgetAboveEstimate",
    }:
        return False
    return f"fixture-{field}"


def _strict_event(event_type, seq=1):
    spec = agent_protocol.AGENT_EVENT_SPECS[event_type]
    return {
        "protocolVersion": 1,
        "seq": seq,
        "type": event_type,
        "data": {
            field: _field_value(field)
            for field in spec["requiredPayloadFields"]
        },
        "createdAt": "2030-01-01T00:00:00Z",
    }


class TestAgentEventContract(unittest.TestCase):
    def test_contract_covers_all_h0_1_events_and_payload_fields(self):
        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        inventory_specs = {
            item["type"]: set(item["payloadFields"])
            for item in inventory["agentRun"]["events"]
        }
        self.assertEqual(set(agent_protocol.AGENT_EVENT_SPECS), set(inventory_specs))
        for event_type, expected_fields in inventory_specs.items():
            with self.subTest(event_type=event_type):
                self.assertEqual(
                    set(agent_protocol.AGENT_EVENT_SPECS[event_type]["payloadFields"]),
                    expected_fields,
                )
                normalized = agent_protocol.normalize_agent_event(
                    _strict_event(event_type),
                    strict=True,
                )
                self.assertTrue(normalized["knownType"])
                self.assertEqual(normalized["sourceProtocolVersion"], 1)
                self.assertEqual(normalized["event"]["protocolVersion"], 1)

    def test_unversioned_h0_traces_adapt_without_losing_payloads(self):
        suite = json.loads(TRACE_SUITE_PATH.read_text(encoding="utf-8"))
        for fixture in suite["fixtures"]:
            for event in fixture["events"]:
                with self.subTest(fixture=fixture["name"], seq=event["seq"]):
                    normalized = agent_protocol.normalize_agent_event(event)
                    self.assertEqual(normalized["sourceProtocolVersion"], 0)
                    self.assertTrue(normalized["knownType"])
                    self.assertEqual(normalized["event"]["data"], event["data"])
                    self.assertTrue(any(
                        item["code"] == "legacy_unversioned_event"
                        for item in normalized["diagnostics"]
                    ))

    def test_unknown_event_and_fields_are_forward_compatible(self):
        raw = {
            "protocolVersion": 1,
            "seq": 7,
            "type": "future_fixture_event",
            "data": {"futureField": {"nested": True}},
            "createdAt": "2030-01-01T00:00:00Z",
            "futureEnvelopeField": "ignored",
        }
        normalized = agent_protocol.normalize_agent_event(raw, strict=True)
        self.assertFalse(normalized["knownType"])
        self.assertEqual(normalized["event"]["type"], "future_fixture_event")
        self.assertEqual(normalized["event"]["data"], raw["data"])
        self.assertNotIn("futureEnvelopeField", normalized["event"])
        self.assertEqual(
            {item["code"] for item in normalized["diagnostics"]},
            {"unknown_envelope_fields", "unknown_event_type"},
        )

        known = _strict_event("created")
        known["data"]["futurePayloadField"] = "preserved"
        adapted = agent_protocol.normalize_agent_event(known, strict=True)
        self.assertEqual(adapted["event"]["data"]["futurePayloadField"], "preserved")
        self.assertIn(
            "unknown_payload_fields",
            {item["code"] for item in adapted["diagnostics"]},
        )

    def test_created_context_fields_are_optional_v1_payload(self):
        legacy = _strict_event("created")
        normalized_legacy = agent_protocol.normalize_agent_event(
            legacy,
            strict=True,
        )
        self.assertEqual(normalized_legacy["diagnostics"], [])

        current = _strict_event("created")
        current["data"].update({
            "contextLimit": 400000,
            "contextWindowTokens": 128000,
            "contextBudgetTokens": 400000,
            "contextWindowSource": "unknown",
            "contextWindowHard": False,
            "availableInputTokens": 375904,
            "compressionTriggerTokens": 360000,
            "budgetClamped": False,
            "budgetAboveEstimate": True,
        })
        normalized = agent_protocol.normalize_agent_event(current, strict=True)
        self.assertEqual(normalized["sourceProtocolVersion"], 1)
        self.assertEqual(normalized["diagnostics"], [])
        self.assertEqual(normalized["event"]["data"], current["data"])

    def test_future_protocol_uses_stable_envelope_only_in_compatibility_mode(self):
        raw = _strict_event("completed")
        raw["protocolVersion"] = 2
        normalized = agent_protocol.normalize_agent_event(raw)
        self.assertEqual(normalized["sourceProtocolVersion"], 2)
        self.assertEqual(normalized["event"]["protocolVersion"], 1)
        self.assertIn(
            "future_protocol_version",
            {item["code"] for item in normalized["diagnostics"]},
        )
        with self.assertRaises(agent_protocol.AgentProtocolError):
            agent_protocol.normalize_agent_event(raw, strict=True)

    def test_missing_required_fields_fail_only_in_strict_mode(self):
        raw = _strict_event("tool_started")
        raw["data"].pop("toolCallId")
        compatible = agent_protocol.normalize_agent_event(raw)
        self.assertIn(
            "missing_payload_fields",
            {item["code"] for item in compatible["diagnostics"]},
        )
        with self.assertRaises(agent_protocol.AgentProtocolError):
            agent_protocol.normalize_agent_event(raw, strict=True)

    def test_credentials_are_rejected_recursively(self):
        probes = [
            {"apiKey": "fixture-value"},
            {"nested": {"headers": {"X-Test": "fixture"}}},
            {"message": "Bearer abcdefghijk"},
            {"message": "sk-fixture123456"},
        ]
        for probe in probes:
            raw = _strict_event("completed")
            raw["data"] = probe
            with self.subTest(probe=probe), self.assertRaises(
                agent_protocol.AgentProtocolError
            ):
                agent_protocol.normalize_agent_event(raw)

        allowed = _strict_event("authorization_required")
        normalized = agent_protocol.normalize_agent_event(allowed, strict=True)
        self.assertEqual(
            normalized["event"]["data"]["authorizationId"],
            "fixture-authorizationId",
        )

    def test_credential_diagnostics_preserve_shadow_sequence_without_leaking_values(self):
        raw = _strict_event("tool_completed", 1)
        raw["data"]["result"] = {
            "content": "source example sk-fixture123456 must not enter diagnostics",
        }
        normalized = agent_protocol.normalize_agent_event(
            raw,
            credential_mode="diagnose",
        )
        self.assertEqual(normalized["event"]["data"], raw["data"])
        self.assertEqual(
            {item["code"] for item in normalized["diagnostics"]},
            {"credential_like_text"},
        )
        encoded_diagnostics = json.dumps(
            normalized["diagnostics"],
            ensure_ascii=False,
        )
        self.assertNotIn("sk-fixture123456", encoded_diagnostics)

        validator = agent_protocol.AgentEventSequenceValidator()
        self.assertTrue(validator.observe(normalized)["accepted"])
        second = agent_protocol.normalize_agent_event(
            _strict_event("completed", 2),
            strict=True,
        )
        observed = validator.observe(second, strict=True)
        self.assertTrue(observed["accepted"])
        self.assertEqual(observed["diagnostics"], [])

        sensitive_field = _strict_event("tool_completed", 1)
        sensitive_field["data"]["result"] = {
            "headers": {"X-Test": "fixture"},
        }
        diagnosed_field = agent_protocol.normalize_agent_event(
            sensitive_field,
            credential_mode="diagnose",
        )
        field_diagnostic = next(
            item for item in diagnosed_field["diagnostics"]
            if item["code"] == "credential_bearing_field"
        )
        self.assertEqual(field_diagnostic["severity"], "error")
        self.assertNotIn("fixture", json.dumps(field_diagnostic))

        with self.assertRaises(agent_protocol.AgentProtocolError):
            agent_protocol.normalize_agent_event(
                raw,
                strict=True,
                credential_mode="diagnose",
            )

    def test_sequence_is_monotonic_and_exact_redelivery_is_idempotent(self):
        validator = agent_protocol.AgentEventSequenceValidator()
        first = agent_protocol.normalize_agent_event(_strict_event("created", 1), strict=True)
        accepted = validator.observe(first, strict=True)
        self.assertTrue(accepted["accepted"])
        self.assertFalse(accepted["duplicate"])

        duplicate = validator.observe(first, strict=True)
        self.assertFalse(duplicate["accepted"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(validator.cursor, 1)

        conflict = agent_protocol.normalize_agent_event(_strict_event("completed", 1), strict=True)
        with self.assertRaises(agent_protocol.AgentProtocolError):
            validator.observe(conflict, strict=True)

        gap = agent_protocol.normalize_agent_event(_strict_event("completed", 3), strict=True)
        with self.assertRaises(agent_protocol.AgentProtocolError):
            validator.observe(gap, strict=True)
        compatible_gap = validator.observe(gap)
        self.assertTrue(compatible_gap["accepted"])
        self.assertIn(
            "event_sequence_gap",
            {item["code"] for item in compatible_gap["diagnostics"]},
        )

    def test_run_model_and_tool_transitions_cover_all_declared_states(self):
        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        inventory_states = {item["name"] for item in inventory["agentRun"]["statuses"]}
        self.assertEqual(set(agent_protocol.AGENT_RUN_TRANSITIONS), inventory_states)
        self.assertEqual(
            set(agent_protocol.MODEL_ROUND_TRANSITIONS),
            set(agent_protocol.MODEL_ROUND_STATES),
        )
        self.assertEqual(
            set(agent_protocol.TOOL_EXECUTION_TRANSITIONS),
            set(agent_protocol.TOOL_EXECUTION_STATES),
        )

        for terminal in ("completed", "failed", "cancelled"):
            with self.subTest(terminal=terminal):
                self.assertTrue(
                    agent_protocol.validate_transition(
                        "run", terminal, terminal, strict=True
                    )["valid"]
                )
                invalid = agent_protocol.validate_transition("run", terminal, "model")
                self.assertFalse(invalid["valid"])
                with self.assertRaises(agent_protocol.AgentProtocolError):
                    agent_protocol.validate_transition(
                        "run", terminal, "model", strict=True
                    )

        self.assertFalse(
            agent_protocol.validate_transition(
                "model_round", "failed", "pending"
            )["valid"]
        )
        self.assertFalse(
            agent_protocol.validate_transition(
                "tool_execution", "completed", "running"
            )["valid"]
        )

    def test_contract_summary_is_json_serializable_and_runtime_imports_contract(self):
        summary = agent_protocol.public_contract_summary()
        encoded = json.dumps(summary, ensure_ascii=False, sort_keys=True)
        self.assertIn('"protocolVersion": 1', encoded)
        self.assertEqual(len(summary["eventTypes"]), 24)
        server_source = (ROOT / "server.py").read_text(encoding="utf-8")
        self.assertIn("import agent_protocol", server_source)
        self.assertNotIn("from agent_protocol", server_source)


if __name__ == "__main__":
    unittest.main()
