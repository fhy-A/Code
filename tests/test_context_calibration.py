"""Strict D-lite context classification and calibration-store tests."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import context_calibration as calibration


UTC = dt.timezone.utc


class StrictContextFailureTests(unittest.TestCase):
    def test_candidate_prefers_explicit_then_uses_deterministic_ladder(self):
        explicit = calibration.calibration_candidate(
            400_000,
            explicit_maximum=200_000,
            max_tokens=8_000,
        )
        self.assertEqual(explicit["capTokens"], 200_000)
        self.assertEqual(explicit["evidenceKind"], "explicit_max")
        self.assertEqual(explicit["compressionTriggerTokens"], 180_000)

        heuristic = calibration.calibration_candidate(
            400_000,
            explicit_maximum=400_000,
            max_tokens=8_000,
        )
        self.assertEqual(heuristic["capTokens"], 256_000)
        self.assertEqual(heuristic["evidenceKind"], "heuristic")
        self.assertIsNone(calibration.calibration_candidate(
            16_000,
            max_tokens=12_000,
        ))

        scope_id = "a" * 64
        first = calibration.calibration_observation_id(
            scope_id, "run-1", 2, 128_000, "heuristic",
        )
        second = calibration.calibration_observation_id(
            scope_id, "run-1", 2, 128_000, "heuristic",
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
    def test_structured_and_adjacent_explicit_maximum(self):
        structured = calibration.classify_context_failure(
            400,
            payload={
                "error": {
                    "code": "context_length_exceeded",
                    "max_context_tokens": 128_000,
                    "request_id": 20260821,
                },
            },
            message="request rejected",
        )
        self.assertEqual(structured, {
            "matched": True,
            "errorCode": "context_window_exceeded",
            "evidenceKind": "explicit_max",
            "explicitMaximumTokens": 128_000,
            "numericConflict": False,
        })

        message = calibration.classify_context_failure(
            413,
            message=(
                "This model's maximum context length is 200,000 tokens. "
                "Your messages resulted in 240000 tokens; request id 20260821."
            ),
        )
        self.assertTrue(message["matched"])
        self.assertEqual(message["explicitMaximumTokens"], 200_000)
        self.assertEqual(message["evidenceKind"], "explicit_max")

    def test_conflicts_and_unrelated_numbers_never_become_explicit(self):
        conflict = calibration.classify_context_failure(
            400,
            payload={
                "error": {
                    "code": "context_length_exceeded",
                    "max_context_tokens": 128_000,
                },
            },
            message="maximum context length is 200000 tokens; requested 220000",
        )
        self.assertTrue(conflict["matched"])
        self.assertTrue(conflict["numericConflict"])
        self.assertIsNone(conflict["explicitMaximumTokens"])
        self.assertEqual(conflict["evidenceKind"], "heuristic")

        unrelated = calibration.classify_context_failure(
            422,
            code="context_window_exceeded",
            message="request 20260821 has 150000 requested tokens",
        )
        self.assertTrue(unrelated["matched"])
        self.assertIsNone(unrelated["explicitMaximumTokens"])

    def test_non_context_and_disallowed_statuses_do_not_learn(self):
        cases = [
            (429, "context_length_exceeded", "maximum context length is 128000 tokens"),
            (502, "context_length_exceeded", "maximum context length is 128000 tokens"),
            (400, "rate_limit", "too many requests"),
            (400, "content_filter", "content blocked by policy"),
            (404, "model_not_found", "context window metadata unavailable"),
            (400, "bad_request", "context window metadata unavailable"),
            (400, "bad_request", "request has too many tokens"),
        ]
        for status, code, message in cases:
            with self.subTest(status=status, code=code):
                self.assertFalse(calibration.classify_context_failure(
                    status, code=code, message=message,
                )["matched"])

    def test_scope_is_stable_and_contains_no_raw_credentials_or_url(self):
        scope = calibration.calibration_scope(
            "HTTPS://Example.COM:443/v1/", "secret-key-value", "models/Test_Model",
        )
        equivalent = calibration.calibration_scope(
            "https://example.com/v1", "secret-key-value", "test_model",
        )
        self.assertEqual(scope, equivalent)
        encoded = json.dumps(scope, sort_keys=True)
        self.assertNotIn("secret-key-value", encoded)
        self.assertNotIn("example.com", encoded)
        self.assertEqual(len(scope["scopeId"]), 64)
        self.assertEqual(len(scope["keyFingerprint"]), 64)


class ContextCalibrationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp.name) / "数据-校准"
        self.now = dt.datetime(2030, 1, 1, tzinfo=UTC)
        self.store = calibration.ContextCalibrationStore(
            self.data_dir,
            clock=lambda: self.now,
        )
        self.scope = calibration.calibration_scope(
            "https://gateway.example/v1", "test-key-a", "test-model",
        )

    def tearDown(self):
        self.temp.cleanup()

    def _observation_id(self, label):
        return calibration._sha256("test-observation/v1\0" + label)

    def test_record_resolve_ttl_minimum_reset_and_no_secret_leak(self):
        self.assertEqual(self.store.resolve(self.scope["scopeId"])["storageStatus"], "missing")
        self.store.record_success(
            self.scope,
            cap_tokens=200_000,
            evidence_kind="explicit_max",
            observation_id=self._observation_id("explicit"),
            now=self.now,
        )
        self.store.record_success(
            self.scope,
            cap_tokens=128_000,
            evidence_kind="heuristic",
            observation_id=self._observation_id("heuristic"),
            now=self.now,
        )
        active = self.store.resolve(self.scope["scopeId"], now=self.now)
        self.assertEqual(active["capTokens"], 128_000)
        self.assertEqual(active["evidenceKind"], "heuristic")
        self.assertEqual(
            active["expiresAt"],
            calibration.calibration_expiry("heuristic", self.now),
        )
        self.assertEqual(active["observationCount"], 2)
        payload = self.store.path.read_text(encoding="utf-8")
        self.assertEqual(json.loads(payload)["schema"], calibration.SCHEMA)
        self.assertNotIn("test-key-a", payload)
        self.assertNotIn("gateway.example", payload)

        after_heuristic = self.store.resolve(
            self.scope["scopeId"], now=self.now + dt.timedelta(days=8),
        )
        self.assertEqual(after_heuristic["capTokens"], 200_000)
        after_all = self.store.resolve(
            self.scope["scopeId"], now=self.now + dt.timedelta(days=31),
        )
        self.assertIsNone(after_all["capTokens"])
        self.assertTrue(self.store.reset(self.scope["scopeId"], now=self.now))
        self.assertFalse(self.store.reset(self.scope["scopeId"], now=self.now))

    def test_idempotency_conflict_and_bounded_observations(self):
        observation_id = self._observation_id("same")
        first = self.store.record_success(
            self.scope,
            cap_tokens=128_000,
            evidence_kind="explicit_max",
            observation_id=observation_id,
            now=self.now,
        )
        retry = self.store.record_success(
            self.scope,
            cap_tokens=128_000,
            evidence_kind="explicit_max",
            observation_id=observation_id,
            now=self.now + dt.timedelta(seconds=10),
        )
        self.assertEqual(first, retry)
        with self.assertRaises(calibration.CalibrationStorageUnavailable):
            self.store.record_success(
                self.scope,
                cap_tokens=64_000,
                evidence_kind="explicit_max",
                observation_id=observation_id,
                now=self.now,
            )
        for index in range(12):
            self.store.record_success(
                self.scope,
                cap_tokens=32_000 + index * 1_000,
                evidence_kind="explicit_max",
                observation_id=self._observation_id(f"bounded-{index}"),
                now=self.now + dt.timedelta(seconds=index + 1),
            )
        document = self.store.read().document
        observations = document["scopes"][self.scope["scopeId"]]["observations"]
        self.assertEqual(len(observations), calibration.MAX_OBSERVATIONS_PER_SCOPE)
        self.assertEqual(min(item["capTokens"] for item in observations), 32_000)

    def test_corruption_disables_reads_and_refuses_mutation_without_overwrite(self):
        self.data_dir.mkdir(parents=True)
        original = (
            b'{"schema":"unknown-calibration/v9","revision":0,'
            b'"updatedAt":"2030-01-01T00:00:00Z","scopes":{}}'
        )
        self.store.path.write_bytes(original)
        read_result = self.store.read()
        self.assertEqual(read_result.storage_status, "corrupted")
        self.assertFalse(read_result.available)
        self.assertEqual(
            self.store.resolve(self.scope["scopeId"])["storageStatus"],
            "corrupted",
        )
        with self.assertRaisesRegex(calibration.CalibrationStorageUnavailable, "storage_unavailable"):
            self.store.record_success(
                self.scope,
                cap_tokens=128_000,
                evidence_kind="explicit_max",
                observation_id=self._observation_id("corrupt"),
                now=self.now,
            )
        with self.assertRaisesRegex(calibration.CalibrationStorageUnavailable, "storage_unavailable"):
            self.store.reset(self.scope["scopeId"], now=self.now)
        self.assertEqual(self.store.path.read_bytes(), original)

    def test_interrupted_replace_preserves_previous_document_and_cleans_temp(self):
        self.store.record_success(
            self.scope,
            cap_tokens=128_000,
            evidence_kind="explicit_max",
            observation_id=self._observation_id("before"),
            now=self.now,
        )
        before = self.store.path.read_bytes()
        with mock.patch.object(calibration.os, "replace", side_effect=OSError("synthetic replace failure")):
            with self.assertRaisesRegex(
                calibration.CalibrationStorageUnavailable,
                "storage_unavailable",
            ):
                self.store.record_success(
                    self.scope,
                    cap_tokens=64_000,
                    evidence_kind="explicit_max",
                    observation_id=self._observation_id("after"),
                    now=self.now + dt.timedelta(seconds=1),
                )
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(list(self.data_dir.glob("*.tmp")), [])

    def test_two_real_processes_merge_under_one_lock(self):
        script = r'''\
import datetime as dt
import sys
from pathlib import Path
import context_calibration as c

data_dir = Path(sys.argv[1])
cap = int(sys.argv[2])
label = sys.argv[3]
scope = c.calibration_scope("https://gateway.example/v1", "process-key", "process-model")
store = c.ContextCalibrationStore(data_dir)
store.record_success(
    scope,
    cap_tokens=cap,
    evidence_kind="explicit_max",
    observation_id=c._sha256("process-observation/v1\\0" + label),
)
'''
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", script, str(self.data_dir), str(cap), label],
                cwd=Path(__file__).resolve().parents[1],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for cap, label in ((200_000, "one"), (64_000, "two"))
        ]
        errors = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            if process.returncode != 0:
                errors.append((process.returncode, stdout, stderr))
        self.assertEqual(errors, [])
        scope = calibration.calibration_scope(
            "https://gateway.example/v1", "process-key", "process-model",
        )
        resolved = calibration.ContextCalibrationStore(self.data_dir).resolve(scope["scopeId"])
        self.assertEqual(resolved["capTokens"], 64_000)
        self.assertEqual(resolved["observationCount"], 2)


if __name__ == "__main__":
    unittest.main()
