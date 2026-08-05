"""H3-2C2 contracts for production loading of minimum legacy AgentRun records."""

import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, FormatChecker

import server as server_mod


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "harness"
SCHEMA_PATH = FIXTURE_DIR / "legacy-agent-run-recovery-suite.schema.json"
MANIFEST_PATH = FIXTURE_DIR / "legacy-agent-run-recovery-suite.json"
EXPECTED_MANIFEST_HASH = "9acdf241c211ccff9528f30a17ad03ce7ddeae16c263f5de4494fdd61c6bddeb"
EXPECTED_SOURCE_HASHES = {
    "agent-run-v1": "a2bed1af692366f4af3f21f1b41bba7f09cccac4456da57e93e193a0c5345598",
    "agent-run-v2": "890db5b3840b5bd2ffb2d0f4ac5f1cc0611865debf981a87fa29f3a32fd8cc66",
    "agent-run-v3": "f5e0279652b4aea71abf2f1447a87578b7201caff3519bba43f70bc77df7470a",
    "agent-run-v4": "96d60cdcebb6d49668e869d9b854bba67c53fc1ae0b3c551218b11554ffe13a0",
}
EXPECTED_MISSING_FIELDS = {
    "agent-run-v1": [
        "cwd", "workspaceRoots", "clientRequestId", "parentAgentRunId",
        "parentToolCallId", "agentDepth", "permissionProfile", "errorCode",
        "nonActionCount", "forceFinalRound", "forceFinalReason", "contextLimit",
        "contextRecoveryRound", "toolBudgets", "compactions", "pendingInput",
        "pendingAuthorization", "pendingSteers", "steerReceipts",
    ],
    "agent-run-v2": [
        "clientRequestId", "parentAgentRunId", "parentToolCallId", "agentDepth",
        "nonActionCount", "forceFinalRound", "forceFinalReason", "contextLimit",
        "contextRecoveryRound", "compactions", "pendingSteers", "steerReceipts",
    ],
    "agent-run-v3": [
        "parentAgentRunId", "parentToolCallId", "agentDepth", "nonActionCount",
        "forceFinalRound", "forceFinalReason", "pendingSteers", "steerReceipts",
    ],
    "agent-run-v4": [
        "parentAgentRunId", "parentToolCallId", "agentDepth", "nonActionCount",
        "forceFinalRound", "forceFinalReason",
    ],
}


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


def first_difference(actual, expected, path):
    if type(actual) is not type(expected):
        return path, expected, actual
    if isinstance(expected, dict):
        for key in expected:
            child_path = f"{path}.{key}"
            if key not in actual:
                return child_path, expected[key], "<missing>"
            difference = first_difference(actual[key], expected[key], child_path)
            if difference:
                return difference
        for key in actual:
            if key not in expected:
                return f"{path}.{key}", "<absent>", actual[key]
        return None
    if isinstance(expected, list):
        for index, expected_item in enumerate(expected):
            child_path = f"{path}[{index}]"
            if index >= len(actual):
                return child_path, expected_item, "<missing>"
            difference = first_difference(actual[index], expected_item, child_path)
            if difference:
                return difference
        if len(actual) > len(expected):
            return f"{path}[{len(expected)}]", "<absent>", actual[len(expected)]
        return None
    if actual != expected:
        return path, expected, actual
    return None


def require_match(actual, expected, path):
    difference = first_difference(actual, expected, path)
    if difference:
        raise EvidenceContractError(*difference)


def loader_fields(run):
    return {
        "status": run["status"],
        "resume_status": run["resume_status"],
        "client_request_id": run["client_request_id"],
        "parent_agent_run_id": run["parent_agent_run_id"],
        "parent_tool_call_id": run["parent_tool_call_id"],
        "agent_depth": run["agent_depth"],
        "permission_profile": run["permission_profile"],
        "error_code": run["error_code"],
        "non_action_count": run["non_action_count"],
        "force_final_round": run["force_final_round"],
        "force_final_reason": run["force_final_reason"],
        "context_limit": run["context_limit"],
        "context_recovery_round": run["context_recovery_round"],
        "pending_steers": deepcopy(run["pending_steers"]),
        "pending_input_present": run["pending_input"] is not None,
        "steer_receipt_count": len(run["steer_receipts"]),
        "compaction_count": len(run["compactions"]),
        "next_seq": run["next_seq"],
        "max_rounds": run["max_rounds"],
    }


def snapshot_fields(snapshot):
    return {
        "status": snapshot["status"],
        "clientRequestId": snapshot["clientRequestId"],
        "parentAgentRunId": snapshot["parentAgentRunId"],
        "parentToolCallId": snapshot["parentToolCallId"],
        "agentDepth": snapshot["agentDepth"],
        "permissionProfile": snapshot["permissionProfile"],
        "errorCode": snapshot["errorCode"],
        "nonActionCount": snapshot["nonActionCount"],
        "forceFinalRound": snapshot["forceFinalRound"],
        "contextLimit": snapshot["contextLimit"],
        "round": snapshot["round"],
        "pendingSteerCount": snapshot["pendingSteerCount"],
        "pendingInputPresent": snapshot["pendingInput"] is not None,
        "steerReceiptCount": len(snapshot["steerReceipts"]),
        "compactionCount": len(snapshot["compactions"]),
        "nextCursor": snapshot["nextCursor"],
    }


def persisted_fields(record):
    return {
        "version": record["version"],
        "status": record["status"],
        "resumeStatus": record["resumeStatus"],
        "clientRequestId": record["clientRequestId"],
        "parentAgentRunId": record["parentAgentRunId"],
        "parentToolCallId": record["parentToolCallId"],
        "agentDepth": record["agentDepth"],
        "permissionProfile": record["permissionProfile"],
        "errorCode": record["errorCode"],
        "nonActionCount": record["nonActionCount"],
        "forceFinalRound": record["forceFinalRound"],
        "forceFinalReason": record["forceFinalReason"],
        "contextLimit": record["contextLimit"],
        "contextRecoveryRound": record["contextRecoveryRound"],
        "pendingSteers": deepcopy(record["pendingSteers"]),
        "pendingInputPresent": record["pendingInput"] is not None,
        "steerReceiptCount": len(record["steerReceipts"]),
        "compactionCount": len(record["compactions"]),
        "nextSeq": record["nextSeq"],
    }


def load_source_fixture(case):
    path = FIXTURE_DIR / case["sourceFixture"]
    return path, json.loads(path.read_text(encoding="utf-8"))


def collect_memory_evidence(manifest, case):
    _path, fixture = load_source_fixture(case)
    fixture_before = deepcopy(fixture)
    record = fixture["record"]
    workspace_function = server_mod._agent_run_workspace
    with tempfile.TemporaryDirectory(prefix="h3_2c2_loader_") as temp_name:
        temp_root = Path(temp_name)
        config_path = temp_root / "config.json"
        sessions_dir = temp_root / "sessions"
        projects_path = temp_root / "projects.json"
        workspace_dir = temp_root / "workspace"
        sessions_dir.mkdir()
        workspace_dir.mkdir()
        server_mod.write_json(config_path, {"projectRoot": str(workspace_dir)})
        with (
            mock.patch.object(server_mod, "CONFIG_PATH", config_path),
            mock.patch.object(server_mod, "SESSIONS_DIR", sessions_dir),
            mock.patch.object(server_mod, "PROJECTS_PATH", projects_path),
            mock.patch.object(
                server_mod,
                "_agent_run_workspace",
                wraps=workspace_function,
            ) as workspace_mock,
        ):
            run = server_mod._agent_run_from_record(record)
    if fixture != fixture_before:
        raise EvidenceContractError("$.sourceFixture", fixture_before, fixture)
    roots_argument = workspace_mock.call_args.args[2]
    expected_roots_argument = None if record["version"] == 1 else record["workspaceRoots"]
    if roots_argument != expected_roots_argument:
        raise EvidenceContractError(
            "$.workspaceRootsInput",
            expected_roots_argument,
            roots_argument,
        )
    snapshot = server_mod._agent_snapshot(run)
    persisted = server_mod._agent_run_record(run)
    return {
        "sourceCanonicalSha256": canonical_hash(fixture),
        "sourceRecordVersion": record["version"],
        "missingFields": [
            field for field in manifest["persistedV4Fields"]
            if field not in record
        ],
        "expected": {
            "loader": {"fields": loader_fields(run)},
            "snapshot": {"fields": snapshot_fields(snapshot)},
            "persisted": {"fields": persisted_fields(persisted)},
        },
        "persistedFieldNames": list(persisted),
    }


def collect_disk_evidence(case):
    _path, fixture = load_source_fixture(case)
    fixture_before = deepcopy(fixture)
    source_record = fixture["record"]
    with tempfile.TemporaryDirectory(prefix="h3_2c2_agent_run_") as temp_name:
        data_dir = Path(temp_name) / "data"
        config_path = data_dir / "config.json"
        sessions_dir = data_dir / "sessions"
        projects_path = data_dir / "projects.json"
        workspace_dir = Path(temp_name) / "workspace"
        data_dir.mkdir()
        sessions_dir.mkdir()
        workspace_dir.mkdir()
        server_mod.write_json(config_path, {"projectRoot": str(workspace_dir)})
        with (
            mock.patch.object(server_mod, "DATA_DIR", data_dir),
            mock.patch.object(server_mod, "CONFIG_PATH", config_path),
            mock.patch.object(server_mod, "SESSIONS_DIR", sessions_dir),
            mock.patch.object(server_mod, "PROJECTS_PATH", projects_path),
            mock.patch.object(server_mod, "_agent_run_worker") as worker_mock,
            mock.patch.object(server_mod.threading, "Thread") as thread_mock,
            mock.patch.object(server_mod, "_create_model_runtime_run") as model_mock,
            mock.patch.object(server_mod, "_execute_agent_pending_tools") as pending_tools_mock,
            mock.patch.object(server_mod, "execute_registered_tool") as tool_mock,
            mock.patch.object(server_mod.request, "urlopen") as urlopen_mock,
            mock.patch.object(server_mod.request, "urlretrieve") as urlretrieve_mock,
        ):
            with server_mod._agent_run_lock:
                server_mod._agent_runs.clear()
            run_path = server_mod._agent_run_path(source_record["id"])
            if data_dir.resolve() not in run_path.resolve().parents:
                raise AssertionError(f"AgentRun path escaped temporary DATA_DIR: {run_path}")
            server_mod.write_json(run_path, deepcopy(source_record))

            first = server_mod._get_agent_run(source_record["id"])
            cached = server_mod._get_agent_run(source_record["id"])
            first_snapshot = server_mod._agent_snapshot(first)
            source_event_count = len(source_record.get("events") or [])
            restart_events = [
                {
                    "type": event["type"],
                    "reason": str((event.get("data") or {}).get("reason") or ""),
                    "resumeStatus": str((event.get("data") or {}).get("resumeStatus") or ""),
                }
                for event in first["events"][source_event_count:]
            ]

            first_persisted_record = server_mod._agent_run_record(first)
            server_mod._persist_agent_run(first)
            normalized_record = server_mod.read_json(run_path, None)
            if normalized_record != first_persisted_record:
                raise EvidenceContractError(
                    "$.expected.disk.persistedRecordStable",
                    first_persisted_record,
                    normalized_record,
                )
            with server_mod._agent_run_lock:
                server_mod._agent_runs.clear()
            second = server_mod._get_agent_run(source_record["id"])
            second_cached = server_mod._get_agent_run(source_record["id"])
            second_snapshot = server_mod._agent_snapshot(second)

            side_effect_mocks = (
                worker_mock,
                thread_mock,
                model_mock,
                pending_tools_mock,
                tool_mock,
                urlopen_mock,
                urlretrieve_mock,
            )
            for side_effect_mock in side_effect_mocks:
                if side_effect_mock.call_count:
                    raise AssertionError(
                        f"unexpected worker/model/tool/network side effect: {side_effect_mock}"
                    )
            if fixture != fixture_before:
                raise EvidenceContractError("$.sourceFixture", fixture_before, fixture)
            if cached is not first or second_cached is not second:
                raise EvidenceContractError("$.expected.disk.cacheHitSameObject", True, False)
            if second is first:
                raise AssertionError("second recovery reused the pre-restart in-memory object")

            evidence = {
                "firstLoadStatus": first["status"],
                "firstLoadEventTypes": [event["type"] for event in first["events"]],
                "firstLoadNextSeq": first["next_seq"],
                "firstLoadNextCursor": first_snapshot["nextCursor"],
                "restartEvents": restart_events,
                "cacheHitSameObject": cached is first and second_cached is second,
                "persistedVersion": normalized_record["version"],
                "secondLoadStatus": second["status"],
                "secondLoadEventTypes": [event["type"] for event in second["events"]],
                "secondLoadNextSeq": second["next_seq"],
                "secondLoadNextCursor": second_snapshot["nextCursor"],
                "publicSnapshotStable": second_snapshot == first_snapshot,
                "persistedRecordStable": (
                    server_mod._agent_run_record(second) == normalized_record
                ),
            }
            with server_mod._agent_run_lock:
                server_mod._agent_runs.clear()
            return evidence


def assert_case_contract(case, index, evidence):
    prefix = f"$.cases[{index}]"
    require_match(
        evidence["sourceCanonicalSha256"],
        case["sourceCanonicalSha256"],
        f"{prefix}.sourceCanonicalSha256",
    )
    require_match(
        evidence["sourceRecordVersion"],
        case["sourceRecordVersion"],
        f"{prefix}.sourceRecordVersion",
    )
    require_match(evidence["missingFields"], case["missingFields"], f"{prefix}.missingFields")
    for layer in ("loader", "snapshot", "persisted"):
        require_match(
            evidence["expected"][layer],
            case["expected"][layer],
            f"{prefix}.expected.{layer}",
        )
    if "disk" in evidence["expected"]:
        require_match(
            evidence["expected"]["disk"],
            case["expected"]["disk"],
            f"{prefix}.expected.disk",
        )


class LegacyAgentRunRecoveryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.validator = Draft202012Validator(
            cls.schema,
            format_checker=FormatChecker(),
        )

    def schema_errors(self, manifest):
        return sorted(self.validator.iter_errors(manifest), key=lambda error: list(error.path))

    def test_schema_manifest_and_reference_set_are_strict_and_frozen(self):
        Draft202012Validator.check_schema(self.schema)
        self.assertEqual(self.schema_errors(self.manifest), [])
        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(self.manifest["evidenceProfile"], {
            "id": "h3-2c2-legacy-agent-run-recovery",
            "version": 1,
            "sourceKind": "referenced-compatibility-fixtures",
            "productionEvidence": "agent-run-loader-snapshot-persistence-v1",
        })
        self.assertEqual(len(self.manifest["cases"]), 4)
        self.assertEqual(
            [case["name"] for case in self.manifest["cases"]],
            ["agent-run-v1", "agent-run-v2", "agent-run-v3", "agent-run-v4"],
        )
        self.assertEqual(
            [case["sourceFixture"] for case in self.manifest["cases"]],
            [f"compatibility/agent-run-v{version}.json" for version in range(1, 5)],
        )
        self.assertEqual(canonical_hash(self.manifest), EXPECTED_MANIFEST_HASH)

        mutations = (
            (("manifestVersion",), 2, ["manifestVersion"]),
            (("evidenceProfile", "version"), 2, ["evidenceProfile", "version"]),
            (("cases", 0, "unexpected"), True, ["cases", 0]),
        )
        for keys, value, expected_path in mutations:
            with self.subTest(keys=keys):
                mutated = deepcopy(self.manifest)
                target = mutated
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value
                self.assertIn(
                    expected_path,
                    [list(error.path) for error in self.schema_errors(mutated)],
                )

    def test_explicit_missing_fields_hashes_and_three_layers_match_production(self):
        self.assertEqual(
            [len(case["missingFields"]) for case in self.manifest["cases"]],
            [19, 12, 8, 6],
        )
        for index, case in enumerate(self.manifest["cases"]):
            with self.subTest(case=case["name"]):
                self.assertEqual(case["sourceCanonicalSha256"], EXPECTED_SOURCE_HASHES[case["name"]])
                self.assertEqual(case["missingFields"], EXPECTED_MISSING_FIELDS[case["name"]])
                evidence = collect_memory_evidence(self.manifest, case)
                self.assertEqual(
                    evidence["persistedFieldNames"],
                    self.manifest["persistedV4Fields"],
                )
                self.assertNotIn("resumeStatus", case["expected"]["snapshot"]["fields"])
                self.assertNotIn("forceFinalReason", case["expected"]["snapshot"]["fields"])
                assert_case_contract(case, index, evidence)

    def test_real_temp_disk_recovery_is_idempotent_without_external_side_effects(self):
        for index, case in enumerate(self.manifest["cases"]):
            with self.subTest(case=case["name"]):
                memory_evidence = collect_memory_evidence(self.manifest, case)
                memory_evidence["expected"]["disk"] = collect_disk_evidence(case)
                assert_case_contract(case, index, memory_evidence)

    def test_active_v1_and_terminal_v3_restart_boundaries_are_explicit(self):
        by_name = {case["name"]: case for case in self.manifest["cases"]}
        v1 = collect_disk_evidence(by_name["agent-run-v1"])
        self.assertEqual(v1["restartEvents"], [{
            "type": "waiting_credentials",
            "reason": "server_restarted",
            "resumeStatus": "tools",
        }])
        self.assertEqual(v1["firstLoadEventTypes"], ["waiting_credentials"])
        self.assertEqual(v1["secondLoadEventTypes"], ["waiting_credentials"])
        self.assertTrue(v1["publicSnapshotStable"])

        v3 = collect_disk_evidence(by_name["agent-run-v3"])
        self.assertEqual(v3["restartEvents"], [])
        self.assertEqual(v3["firstLoadEventTypes"], ["completed"])
        self.assertEqual(v3["secondLoadEventTypes"], ["completed"])
        self.assertTrue(v3["publicSnapshotStable"])

    def test_targeted_mutations_report_frozen_first_difference_paths(self):
        evidence = []
        for case in self.manifest["cases"]:
            item = collect_memory_evidence(self.manifest, case)
            item["expected"]["disk"] = collect_disk_evidence(case)
            evidence.append(item)

        mutations = (
            (0, ("missingFields", 0), "version", "$.cases[0].missingFields[0]"),
            (0, ("expected", "loader", "fields", "status"), "completed", "$.cases[0].expected.loader.fields.status"),
            (1, ("expected", "snapshot", "fields", "parentAgentRunId"), "unexpected-parent", "$.cases[1].expected.snapshot.fields.parentAgentRunId"),
            (1, ("expected", "persisted", "fields", "agentDepth"), 1, "$.cases[1].expected.persisted.fields.agentDepth"),
            (1, ("expected", "loader", "fields", "context_limit"), 128000, "$.cases[1].expected.loader.fields.context_limit"),
            (3, ("expected", "snapshot", "fields", "steerReceiptCount"), 0, "$.cases[3].expected.snapshot.fields.steerReceiptCount"),
            (2, ("expected", "persisted", "fields", "version"), 3, "$.cases[2].expected.persisted.fields.version"),
            (0, ("expected", "disk", "restartEvents", 0, "reason"), "unexpected-restart", "$.cases[0].expected.disk.restartEvents[0].reason"),
            (0, ("expected", "disk", "secondLoadNextSeq"), 3, "$.cases[0].expected.disk.secondLoadNextSeq"),
        )
        for case_index, keys, value, expected_path in mutations:
            with self.subTest(keys=keys):
                mutated_case = deepcopy(self.manifest["cases"][case_index])
                target = mutated_case
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value
                with self.assertRaises(EvidenceContractError) as raised:
                    assert_case_contract(mutated_case, case_index, evidence[case_index])
                self.assertEqual(raised.exception.path, expected_path)


if __name__ == "__main__":
    unittest.main()
