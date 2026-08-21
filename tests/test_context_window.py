import unittest

import context_window


class ContextWindowResolverTest(unittest.TestCase):
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

    def test_multi_key_minimum_preserves_only_the_winning_hardness(self):
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
        self.assertEqual(entries[0]["contextWindowTokens"], 128000)
        self.assertFalse(entries[0]["contextWindowHard"])

    def test_small_budget_is_reported_before_any_upstream_request(self):
        resolved = context_window.resolve(
            "unknown-model", "https://example.test", budget=4096, max_tokens=2048,
        )
        self.assertTrue(resolved["inputBudgetInsufficient"])
        self.assertEqual(resolved["availableInputTokens"], 1024)

    def test_invalid_metadata_and_legacy_hint_only_lower(self):
        entries = context_window.normalize_catalog("https://example.test", [{
            "id": "gpt-5.6", "context_window": "200000", "max_input_tokens": 64000,
        }])
        self.assertEqual(entries[0]["contextWindowSource"], "family")
        resolved = context_window.resolve(
            "gpt-5.6", "https://example.test", budget=2000000, legacy_hint=128000,
        )
        self.assertEqual(resolved["contextLimit"], 128000)


if __name__ == "__main__":
    unittest.main()
