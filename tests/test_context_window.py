import copy
import datetime as dt
import json
import unittest
from unittest import mock

import context_window


class ContextWindowResolverTest(unittest.TestCase):
    def test_key_scoped_calibration_caps_final_limit_without_relabeling_capability(self):
        resolved = context_window.resolve(
            "gpt-5.6-sol",
            "https://gateway.example/v1",
            budget=1_000_000,
            max_tokens=16_000,
            calibration={
                "capTokens": 200_000,
                "evidenceKind": "explicit_max",
                "expiresAt": "2030-02-01T00:00:00Z",
            },
        )
        self.assertEqual(resolved["contextWindowTokens"], 1_050_000)
        self.assertEqual(resolved["contextWindowSource"], "official")
        self.assertFalse(resolved["contextWindowHard"])
        self.assertEqual(resolved["contextLimit"], 200_000)
        self.assertEqual(resolved["calibrationCapTokens"], 200_000)
        self.assertEqual(resolved["calibrationEvidenceKind"], "explicit_max")
        self.assertTrue(resolved["calibrationApplied"])
        self.assertEqual(resolved["availableInputTokens"], 174_000)

        lower_budget = context_window.resolve(
            "gpt-5.6-sol",
            "https://gateway.example/v1",
            budget=128_000,
            calibration={
                "capTokens": 200_000,
                "evidenceKind": "heuristic",
                "expiresAt": "2030-01-08T00:00:00Z",
            },
        )
        self.assertEqual(lower_budget["contextLimit"], 128_000)
        self.assertFalse(lower_budget["calibrationApplied"])
    def setUp(self):
        context_window._catalog.clear()

    def test_family_defaults_and_estimated_budget_can_expand(self):
        self.assertEqual(context_window.family_limit("unknown"), 128000)
        self.assertEqual(context_window.family_limit("claude-4.5"), 200000)
        self.assertEqual(context_window.family_limit("gpt-5.6"), 1000000)
        resolved = context_window.resolve(
            "unknown", "https://example.test/v1", budget=400000, max_tokens=16000,
        )
        self.assertEqual(resolved["contextLimit"], 400000)
        self.assertTrue(resolved["budgetAboveEstimate"])
        self.assertEqual(resolved["availableInputTokens"], 364000)
        self.assertEqual(resolved["contextWindowSource"], "unknown")

    def test_desired_maximum_is_preserved_while_runtime_limit_stays_authoritative(self):
        hard_url = "https://hard-context.example/v1"
        context_window.normalize_catalog(hard_url, [{
            "id": "custom-hard-context",
            "context_window": 128_000,
        }])
        hard = context_window.resolve(
            "custom-hard-context",
            hard_url,
            budget=200_000,
            max_tokens=4_096,
        )
        self.assertEqual(hard["contextBudgetTokens"], 200_000)
        self.assertEqual(hard["contextLimit"], 128_000)
        self.assertTrue(hard["budgetClamped"])
        self.assertFalse(hard["budgetAboveEstimate"])

        soft = context_window.resolve(
            "unknown-soft-context",
            "https://soft-context.example/v1",
            budget=200_000,
            max_tokens=4_096,
        )
        self.assertEqual(soft["contextWindowTokens"], 128_000)
        self.assertEqual(soft["contextBudgetTokens"], 200_000)
        self.assertEqual(soft["contextLimit"], 200_000)
        self.assertFalse(soft["budgetClamped"])
        self.assertTrue(soft["budgetAboveEstimate"])

        calibrated = context_window.resolve(
            "unknown-soft-context",
            "https://soft-context.example/v1",
            budget=200_000,
            max_tokens=4_096,
            calibration={
                "capTokens": 96_000,
                "evidenceKind": "explicit_max",
                "expiresAt": "2030-02-01T00:00:00Z",
            },
        )
        self.assertEqual(calibrated["contextBudgetTokens"], 200_000)
        self.assertEqual(calibrated["contextLimit"], 96_000)
        self.assertTrue(calibrated["calibrationApplied"])

        automatic = context_window.resolve(
            "custom-hard-context",
            hard_url,
            budget="auto",
            max_tokens=4_096,
        )
        self.assertIsNone(automatic["contextBudgetTokens"])
        self.assertEqual(automatic["contextLimit"], 128_000)
        self.assertFalse(automatic["budgetClamped"])

    def test_static_official_catalog_has_audited_shape_and_pending_boundary(self):
        data = json.loads(context_window.CATALOG_JSON)
        catalog = context_window.load_official_catalog(data=data)
        entries = catalog["entries"]
        self.assertEqual(catalog["schema"], "code-official-model-capabilities/v1")
        self.assertEqual(catalog["catalogRevision"], "2026-08-21.c1")
        self.assertEqual(len(entries), 37)
        self.assertEqual(
            sum(entry["status"] == "active" for entry in entries),
            31,
        )
        self.assertEqual(
            sum(entry["status"] == "research_pending" for entry in entries),
            6,
        )
        self.assertEqual(
            {entry["provider"] for entry in entries},
            {"openai", "anthropic", "google", "xai", "deepseek", "kimi", "qwen"},
        )
        self.assertTrue(all(entry["sourceUrl"].startswith("https://") for entry in entries))
        self.assertTrue(all(entry["asOf"] == dt.date(2026, 8, 21) for entry in entries))
        self.assertTrue(all(
            entry["contextWindowTokens"] is None
            for entry in entries
            if entry["status"] == "research_pending"
        ))
        self.assertIsNone(context_window.official_resolution("kimi-k2.6"))
        self.assertEqual(
            context_window.resolve("kimi-k2.6", "https://example.test")["contextWindowSource"],
            "unknown",
        )

    def test_official_estimates_correct_family_misses_without_becoming_hard(self):
        normalized = context_window.normalize_catalog("https://example.test", [{
            "id": "gpt-5.4-mini",
        }])[0]
        self.assertEqual(normalized["contextWindowTokens"], 400000)
        self.assertEqual(normalized["contextWindowSource"], "official")
        self.assertFalse(normalized["contextWindowHard"])
        self.assertEqual(normalized["maxOutputTokens"], 128000)
        self.assertEqual(normalized["officialProvider"], "openai")
        self.assertEqual(normalized["officialCatalogRevision"], "2026-08-21.c1")
        context_window._catalog.clear()
        expected = {
            "gpt-5.4-mini": 400000,
            "gpt-5.3-codex": 400000,
            "gpt-5.2-codex": 400000,
            "gpt-5.1-codex": 400000,
            "gpt-5.6-sol": 1050000,
            "claude-sonnet-4-6": 1000000,
            "gemini-3.7-flash": 1048576,
            "grok-4.5": 500000,
            "deepseek-v4-pro": 1000000,
            "kimi-k3": 1000000,
            "qwen3.7-plus": 1000000,
        }
        for model, tokens in expected.items():
            with self.subTest(model=model):
                result = context_window.resolve(model, "https://example.test")
                self.assertEqual(result["contextWindowTokens"], tokens)
                self.assertEqual(result["contextWindowSource"], "official")
                self.assertFalse(result["contextWindowHard"])
        expanded = context_window.resolve(
            "gpt-5.4-mini",
            "https://example.test",
            budget=1000000,
            max_tokens=200000,
        )
        self.assertEqual(expanded["contextLimit"], 1000000)
        self.assertTrue(expanded["budgetAboveEstimate"])
        self.assertEqual(expanded["maxOutputTokens"], 128000)
        self.assertFalse(expanded["budgetClamped"])

    def test_exact_aliases_moving_expiry_stale_and_blacklist(self):
        checked = dt.date(2026, 8, 21)
        canonical = context_window.official_resolution("gpt-5.6-sol")
        self.assertEqual(canonical["contextWindowTokens"], 1_050_000)
        self.assertEqual(canonical["contextWindowSource"], "official")
        self.assertIsNone(context_window.official_resolution("gpt-5.6"))
        current_alias = context_window.resolve("gpt-5.6", "https://example.test")
        self.assertEqual(current_alias["contextWindowTokens"], 1_000_000)
        self.assertEqual(current_alias["contextWindowSource"], "family")
        context_window._catalog.clear()
        self.assertEqual(
            context_window.official_resolution("gpt-5.6", today=checked)[
                "contextWindowTokens"
            ],
            1050000,
        )
        self.assertIsNone(
            context_window.official_resolution(
                "gpt-5.6", today=checked + dt.timedelta(days=8),
            )
        )
        context_window.normalize_catalog("https://example.test", [{"id": "gpt-5.6"}])
        expired_alias_data = json.loads(context_window.CATALOG_JSON)
        expired_alias_data["verifiedAt"] = "2026-08-01"
        for entry in expired_alias_data["entries"]:
            entry["asOf"] = "2026-08-01"
        with mock.patch.object(
            context_window,
            "_official_catalog",
            context_window.load_official_catalog(data=expired_alias_data),
        ):
            expired_alias = context_window.resolve(
                "gpt-5.6", "https://example.test",
            )
        self.assertEqual(expired_alias["contextWindowTokens"], 1000000)
        self.assertEqual(expired_alias["contextWindowSource"], "family")
        context_window._catalog.clear()
        stale = context_window.official_resolution(
            "gpt-5.4-mini", today=checked + dt.timedelta(days=31),
        )
        self.assertEqual(stale["contextWindowTokens"], 400000)
        self.assertEqual(stale["contextWindowSource"], "stale_official")
        stale_data = json.loads(context_window.CATALOG_JSON)
        stale_data["verifiedAt"] = "2026-01-01"
        for entry in stale_data["entries"]:
            entry["asOf"] = "2026-01-01"
        context_window.normalize_catalog("https://example.test", [{
            "id": "gpt-5.4-mini",
        }])
        with mock.patch.object(
            context_window,
            "_official_catalog",
            context_window.load_official_catalog(data=stale_data),
        ):
            stale_resolved = context_window.resolve(
                "gpt-5.4-mini", "https://example.test",
            )
        self.assertEqual(stale_resolved["contextWindowTokens"], 400000)
        self.assertEqual(stale_resolved["contextWindowSource"], "stale_official")
        self.assertEqual(
            context_window.official_resolution("models/gemini-2.5-pro")[
                "contextWindowTokens"
            ],
            1048576,
        )
        for model in (
            "openai/gpt-5.4-mini",
            "vendor:gpt-5.4-mini",
            "claude_4.6_opus",
            "claude-4.5-sonnet",
            "claude-5.0-sonnet",
            "deepseek-v4",
            "grok-latest",
            "grok-code-fast-1",
            "kimi-latest",
            "gpt-5.4-mini-preview",
        ):
            with self.subTest(model=model):
                self.assertIsNone(context_window.official_resolution(model))

    def test_catalog_corruption_and_duplicate_ids_fail_closed(self):
        source = json.loads(context_window.CATALOG_JSON)
        mutations = []
        bad_schema = copy.deepcopy(source)
        bad_schema["schema"] = "future"
        mutations.append(bad_schema)
        bad_url = copy.deepcopy(source)
        bad_url["entries"][0]["sourceUrl"] = "http://example.test/model"
        mutations.append(bad_url)
        wrong_official_host = copy.deepcopy(source)
        wrong_official_host["entries"][0]["sourceUrl"] = "https://example.test/model"
        mutations.append(wrong_official_host)
        bad_range = copy.deepcopy(source)
        bad_range["entries"][0]["contextWindowTokens"] = 3_000_000
        mutations.append(bad_range)
        guessed_pending = copy.deepcopy(source)
        guessed_pending["entries"][27]["contextWindowTokens"] = 262144
        mutations.append(guessed_pending)
        duplicate = copy.deepcopy(source)
        duplicate["entries"][1]["aliases"].append({
            "id": "gpt-5.4-mini", "moving": False,
        })
        mutations.append(duplicate)
        for data in mutations:
            with self.subTest(mutation=mutations.index(data)):
                with self.assertRaises(ValueError):
                    context_window.load_official_catalog(data=data)
        with mock.patch.object(context_window, "_official_catalog", None):
            fallback = context_window.resolve(
                "gpt-5.4-mini", "https://example.test",
            )
        self.assertEqual(fallback["contextWindowTokens"], 1000000)
        self.assertEqual(fallback["contextWindowSource"], "family")

    def test_metadata_aliases_conflict_and_hard_budget_clamp(self):
        entries = context_window.normalize_catalog("https://example.test/v1/", [{
            "id": "models/custom",
            "context_window": 200000,
            "maxContextTokens": 128000,
            "max_output_tokens": 999999,
        }])
        self.assertEqual(entries[0]["contextWindowTokens"], 128000)
        self.assertEqual(entries[0]["metadataStatus"], "conflict")
        resolved = context_window.resolve(
            "custom", "https://EXAMPLE.test:443/v1", budget=1000000,
        )
        self.assertEqual(resolved["contextLimit"], 128000)
        self.assertTrue(resolved["budgetClamped"])

    def test_multi_key_candidates_merge_to_minimum(self):
        context_window.normalize_catalog("https://example.test", [{
            "id": "same-model", "contextWindowTokens": 1000000,
        }])
        entries = context_window.normalize_catalog("https://example.test/", [{
            "id": "same-model", "context_length": 200000,
        }])
        self.assertEqual(entries[0]["contextWindowTokens"], 200000)
        self.assertEqual(
            context_window.resolve("same-model", "https://example.test")["contextLimit"],
            200000,
        )

    def test_multi_key_priority_prefers_live_hard_then_minimum_within_tier(self):
        context_window.normalize_catalog("https://example.test", [{
            "id": "gpt-5.6", "contextWindowTokens": 1000000,
        }])
        entries = context_window.normalize_catalog("https://example.test", [{
            "id": "gpt-5.6",
        }])
        self.assertEqual(entries[0]["contextWindowTokens"], 1000000)
        self.assertTrue(entries[0]["contextWindowHard"])

        context_window._catalog.clear()
        context_window.normalize_catalog("https://example.test", [{
            "id": "gpt-5.6", "contextWindowTokens": 200000,
        }])
        entries = context_window.normalize_catalog("https://example.test", [{
            "id": "gpt-5.6",
        }])
        self.assertEqual(entries[0]["contextWindowTokens"], 200000)
        self.assertTrue(entries[0]["contextWindowHard"])

        context_window._catalog.clear()
        context_window.normalize_catalog("https://example.test", [{
            "id": "custom-model", "contextWindowTokens": 1000000,
        }])
        entries = context_window.normalize_catalog("https://example.test", [{
            "id": "custom-model",
        }])
        self.assertEqual(entries[0]["contextWindowTokens"], 1000000)
        self.assertTrue(entries[0]["contextWindowHard"])

        context_window._catalog.clear()
        context_window.normalize_catalog("https://example.test", [{
            "id": "gpt-5.4-mini",
        }])
        entries = context_window.normalize_catalog("https://example.test", [{
            "id": "gpt-5.4-mini", "contextWindowTokens": 1000000,
        }])
        self.assertEqual(entries[0]["contextWindowTokens"], 1000000)
        self.assertEqual(entries[0]["contextWindowSource"], "metadata")
        self.assertTrue(entries[0]["contextWindowHard"])

    def test_small_budget_is_reported_before_any_upstream_request(self):
        resolved = context_window.resolve(
            "unknown-model", "https://example.test", budget=4096, max_tokens=2048,
        )
        self.assertTrue(resolved["inputBudgetInsufficient"])
        self.assertEqual(resolved["availableInputTokens"], 1024)

    def test_auto_budget_ignores_stale_legacy_hint_and_explicit_controls_win(self):
        entries = context_window.normalize_catalog("https://example.test", [{
            "id": "gpt-5.6-sol", "context_window": "200000", "max_input_tokens": 64000,
        }])
        self.assertEqual(entries[0]["contextWindowSource"], "official")
        automatic = context_window.resolve(
            "deepseek-v4-flash-vision-exp",
            "https://example.test",
            legacy_hint=128000,
        )
        self.assertEqual(automatic["contextWindowTokens"], 1_000_000)
        self.assertEqual(automatic["contextLimit"], 1_000_000)

        explicit = context_window.resolve(
            "deepseek-v4-flash-vision-exp",
            "https://example.test",
            budget=256000,
            legacy_hint=128000,
        )
        self.assertEqual(explicit["contextLimit"], 256000)

        calibrated = context_window.resolve(
            "deepseek-v4-flash-vision-exp",
            "https://example.test",
            legacy_hint=128000,
            calibration={
                "capTokens": 200000,
                "evidenceKind": "explicit_max",
                "expiresAt": "2030-01-01T00:00:00Z",
            },
        )
        self.assertEqual(calibrated["contextLimit"], 200000)
        self.assertTrue(calibrated["calibrationApplied"])


if __name__ == "__main__":
    unittest.main()
