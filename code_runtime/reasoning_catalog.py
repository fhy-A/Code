"""Reviewed, bundled capability metadata; never executable provider configuration.

Models.dev (MIT), commit a63e41371cc203eb1b9fe8065e4d190df71d2cfe,
reviewed 2026-09-09. Only exact IDs below are admitted. Official overrides
remain explicit; directory assertions do not attest any gateway connection.
"""
SOURCE_COMMIT = "a63e41371cc203eb1b9fe8065e4d190df71d2cfe"
SOURCE_ROOT = f"https://github.com/anomalyco/models.dev/tree/{SOURCE_COMMIT}/providers"
REVIEWED_AT = "2026-09-09"
UPSTREAM_LICENSE = """MIT License
Copyright (c) 2025 models.dev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
MODELS = {}


def _add(ids, provider, adapter, values, source, **extra):
    for model in ids:
        MODELS[model] = dict(provider=provider, adapter=adapter, efforts=values,
                             source=source, **extra)


_add(("gpt-5.4", "gpt-5.5", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna",
      "gpt-5.4-mini", "gpt-5.4-mini-2026-03-17", "o3", "o3-2025-04-16",
      "o4-mini", "o4-mini-2025-04-16"), "openai", "openai-chat-native-v1",
     ("low", "medium", "high"), "https://developers.openai.com/api/docs/guides/reasoning")
_add(("deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-vision-exp"),
     "deepseek", "deepseek-chat-v4-v1", ("low", "high", "max"),
     "https://api-docs.deepseek.com/guides/thinking_mode/", replay="deepseek")
MODELS["deepseek-v4-pro"]["override"] = {
    "directoryEfforts": ("high", "max"), "field": "efforts",
    "reason": "Official exact-model contract also supports low", "reviewedAt": REVIEWED_AT,
}
_add(("claude-opus-4-6", "claude-sonnet-4-6"), "anthropic", "claude-adaptive-4.6-v1",
     ("low", "medium", "high"), "https://platform.claude.com/docs/en/build-with-claude/effort",
     replay="claude", thinking="adaptive")
_add(("claude-opus-4-7", "claude-opus-4-8"), "anthropic", "claude-adaptive-opus-4.7-4.8-v1",
     ("low", "medium", "high"), "https://platform.claude.com/docs/en/build-with-claude/thinking",
     replay="claude", thinking="adaptive", sampling=False)
_add(("claude-opus-5", "claude-sonnet-5"), "anthropic", "claude-adaptive-5-v1",
     ("low", "medium", "high"), "https://platform.claude.com/docs/en/build-with-claude/thinking",
     replay="claude", thinking="adaptive", sampling=False)
_add(("claude-sonnet-4-5", "claude-sonnet-4-5-20250929"), "anthropic", "claude-sonnet-4.5-budget-v1",
     (1024, 2048, 4096), "https://platform.claude.com/docs/en/build-with-claude/extended-thinking",
     replay="claude", thinking="enabled", answerReserve=1024)
PROFILES = frozenset(m["adapter"] for m in MODELS.values())
for model in ("o4-mini", "o4-mini-2025-04-16"):
    MODELS[model]["source"] = SOURCE_ROOT + "/openai/models/o4-mini.toml"
