"""Regression coverage for single-owner foreground AgentRun observation."""

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
APP_SOURCE = (ROOT / "app.js").read_text(encoding="utf-8")


class TestForegroundRunOwnership(unittest.TestCase):

    def test_identity_safe_claim_and_release(self):
        start = APP_SOURCE.index("function claimActiveRunContext(ctx)")
        end = APP_SOURCE.index("function _formatAgentError", start)
        helpers = APP_SOURCE[start:end]
        script = f"""
{helpers}
const run = {{}};
const first = {{ run, name: "first" }};
const second = {{ run, name: "second" }};
const result = {{
  firstClaim: claimActiveRunContext(first),
  secondClaimWhileOwned: claimActiveRunContext(second),
  firstOwns: ownsActiveRunContext(first),
  secondOwns: ownsActiveRunContext(second),
  secondReleaseWhileOwned: releaseActiveRunContext(second),
  ownerAfterForeignRelease: run._activeCtx?.name || "",
  firstRelease: releaseActiveRunContext(first),
  secondClaimAfterRelease: claimActiveRunContext(second),
  ownerAfterSecondClaim: run._activeCtx?.name || "",
}};
console.log(JSON.stringify(result));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout), {
            "firstClaim": True,
            "secondClaimWhileOwned": False,
            "firstOwns": True,
            "secondOwns": False,
            "secondReleaseWhileOwned": False,
            "ownerAfterForeignRelease": "first",
            "firstRelease": True,
            "secondClaimAfterRelease": True,
            "ownerAfterSecondClaim": "second",
        })

    def test_recovery_does_not_overwrite_or_clear_another_owner(self):
        builder_start = APP_SOURCE.index("function buildRecoveredRunContext")
        builder_end = APP_SOURCE.index("const LEGACY_BROWSER_RUN_ERROR", builder_start)
        builder = APP_SOURCE[builder_start:builder_end]
        self.assertNotIn("ctx.run._activeCtx = ctx", builder)

        recovery_start = APP_SOURCE.index("async function resumePersistedSessionRun(summary)")
        recovery_end = APP_SOURCE.index("function normalizeUserInputRequest", recovery_start)
        recovery = APP_SOURCE[recovery_start:recovery_end]
        self.assertIn("if (!claimActiveRunContext(ctx)) return;", recovery)
        self.assertGreaterEqual(recovery.count("publishTerminalRunOwnership(ctx);"), 2)
        self.assertLess(
            recovery.index("if (!claimActiveRunContext(ctx)) return;"),
            recovery.index("setStreaming(true, summary.id);"),
        )

    def test_all_active_context_mutations_use_identity_safe_helpers(self):
        self.assertEqual(APP_SOURCE.count("run._activeCtx = ctx"), 1)
        self.assertEqual(APP_SOURCE.count("ctx.run._activeCtx = null"), 1)
        self.assertNotIn("if (run) run._activeCtx = null", APP_SOURCE)

        loop_start = APP_SOURCE.index("async function runServerAgentLoop(ctx)")
        loop_end = APP_SOURCE.index("async function executeRunContext(ctx)", loop_start)
        loop = APP_SOURCE[loop_start:loop_end]
        self.assertIn("if (!claimActiveRunContext(ctx))", loop)
        self.assertNotIn("ctx.run._activeCtx = ctx", loop)

    def test_normal_and_continue_cleanup_are_owner_guarded(self):
        continue_start = APP_SOURCE.index("async function continueAgentRun()")
        continue_end = APP_SOURCE.index("async function renameSession", continue_start)
        continued = APP_SOURCE[continue_start:continue_end]
        self.assertIn("if (!claimActiveRunContext(ctx)) return;", continued)
        self.assertGreaterEqual(continued.count("publishTerminalRunOwnership(ctx);"), 2)

        send_start = APP_SOURCE.index("async function sendMessage(userText, options = {})")
        send_end = APP_SOURCE.index("function getSelectedModel()", send_start)
        send = APP_SOURCE[send_start:send_end]
        self.assertIn("if (!claimActiveRunContext(ctx))", send)
        self.assertIn("publishTerminalRunOwnership(ctx);", send)

    def test_terminal_publication_releases_only_the_current_owner(self):
        identity_start = APP_SOURCE.index("function claimActiveRunContext(ctx)")
        identity_end = APP_SOURCE.index("function _formatAgentError", identity_start)
        identity_helpers = APP_SOURCE[identity_start:identity_end]
        publish_start = APP_SOURCE.index("function publishTerminalRunOwnership(ctx)")
        publish_end = APP_SOURCE.index("function refreshSessionStatusSlot", publish_start)
        publish_helper = APP_SOURCE[publish_start:publish_end]
        script = f"""
{identity_helpers}
{publish_helper}
const calls = [];
function setStreaming(active, sessionId) {{ calls.push([active, sessionId]); }}
const run = {{}};
const owner = {{run, sessionId: "session-owner"}};
const foreign = {{run, sessionId: "session-foreign"}};
claimActiveRunContext(owner);
const foreignPublished = publishTerminalRunOwnership(foreign);
const ownerBefore = run._activeCtx === owner;
const ownerPublished = publishTerminalRunOwnership(owner);
const ownerAfter = run._activeCtx || null;
const replayPublished = publishTerminalRunOwnership(owner);
console.log(JSON.stringify({{
  foreignPublished,
  ownerBefore,
  ownerPublished,
  ownerAfter,
  replayPublished,
  calls,
}}));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout), {
            "foreignPublished": False,
            "ownerBefore": True,
            "ownerPublished": True,
            "ownerAfter": None,
            "replayPublished": False,
            "calls": [[False, "session-owner"]],
        })


if __name__ == "__main__":
    unittest.main()
