import ast
import json
import unittest
import warnings
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "server.py"
INVENTORY_PATH = ROOT / "docs" / "harness" / "h0-1-fact-inventory.json"
FRONTEND_PATHS = (
    ROOT / "agent-runtime.js",
    ROOT / "app.js",
    ROOT / "src" / "core" / "state.js",
    ROOT / "src" / "ui" / "messages.js",
)


class HarnessFactInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server_source = SERVER_PATH.read_text(encoding="utf-8")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            cls.server_tree = ast.parse(cls.server_source)
        cls.inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        cls.frontend_source = "\n".join(
            path.read_text(encoding="utf-8") for path in FRONTEND_PATHS
        )

    @classmethod
    def assigned_literal(cls, name):
        for node in cls.server_tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return ast.literal_eval(node.value)
        raise AssertionError(f"missing server assignment: {name}")

    def test_agent_run_status_inventory_matches_server_constants(self):
        produced = set()
        for name in (
            "_AGENT_RUN_ACTIVE",
            "_AGENT_RUN_WAITING",
            "_AGENT_RUN_TERMINAL",
        ):
            produced.update(self.assigned_literal(name))
        listed = {
            item["name"] for item in self.inventory["agentRun"]["statuses"]
        }
        self.assertEqual(produced, listed)

    def test_agent_event_inventory_matches_all_constant_producers(self):
        produced = set(self.assigned_literal("_AGENT_RUN_TERMINAL"))
        for node in ast.walk(self.server_tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in {
                "_append_agent_event",
                "_append_agent_event_locked",
            } or len(node.args) < 2:
                continue
            event_type = node.args[1]
            if isinstance(event_type, ast.Constant) and isinstance(event_type.value, str):
                produced.add(event_type.value)
        listed = {
            item["type"] for item in self.inventory["agentRun"]["events"]
        }
        self.assertEqual(produced, listed)
        self.assertEqual(24, len(listed))

    def test_agent_run_record_version_matches_inventory(self):
        record_version = None
        for node in self.server_tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name != "_agent_run_record":
                continue
            returned = next(
                (item.value for item in node.body if isinstance(item, ast.Return)),
                None,
            )
            if not isinstance(returned, ast.Dict):
                continue
            for key, value in zip(returned.keys, returned.values):
                if isinstance(key, ast.Constant) and key.value == "version":
                    record_version = ast.literal_eval(value)
                    break
        self.assertEqual(self.inventory["agentRun"]["recordVersion"], record_version)

    def test_named_frontend_consumers_exist(self):
        consumers = {
            consumer
            for event in self.inventory["agentRun"]["events"]
            for consumer in event["frontendConsumers"]
        }
        for consumer in sorted(consumers):
            with self.subTest(consumer=consumer):
                self.assertIn(consumer, self.frontend_source)

    def test_trace_catalog_covers_h0_1_scope(self):
        trace_ids = {
            item["id"] for item in self.inventory["sanitizedTraceCandidates"]
        }
        required = {
            "plain-text-final",
            "single-read-tool",
            "multi-tool-stage",
            "questionnaire-submit",
            "edit-authorization-accept",
            "auto-compaction-success",
            "cancel-during-model",
            "refresh-before-first-response",
        }
        self.assertGreaterEqual(len(trace_ids), 10)
        self.assertTrue(required.issubset(trace_ids))


if __name__ == "__main__":
    unittest.main()
