import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "workspace_owner_lease.py"
sys.path.insert(0, str(SCRIPT.parent))

import workspace_owner_lease as owner_lease


def git(cwd, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def init_repo(path):
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "config", "user.name", "Lease Test")
    git(path, "config", "user.email", "lease@example.invalid")
    (path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    git(path, "add", "tracked.txt")
    git(path, "commit", "-q", "-m", "initial")


def git_dir(repo):
    return Path(git(repo, "rev-parse", "--absolute-git-dir").stdout.strip())


def holder(runtime="codex", approval="approval-a", developer="developer-a"):
    return [
        "--runtime",
        runtime,
        "--approval-id",
        approval,
        "--developer-id",
        developer,
    ]


def acquire_args(
    runtime="codex",
    approval="approval-a",
    developer="developer-a",
    stage="stage-a",
    relay="relay-a",
    ttl=owner_lease.DEFAULT_TTL_SECONDS,
):
    return [
        *holder(runtime, approval, developer),
        "--stage",
        stage,
        "--relay-id",
        relay,
        "--ttl-seconds",
        str(ttl),
    ]


class OwnerLeaseCliTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "共享工作区"
        init_repo(self.repo)

    def tearDown(self):
        self.temporary.cleanup()

    def run_cli(self, action, *args, repo=None, json_output=True, env=None):
        command = [
            sys.executable,
            str(SCRIPT),
            action,
            "--repo",
            str(repo or self.repo),
        ]
        if json_output:
            command.append("--json")
        command.extend(args)
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
            env=env,
        )

    def json_result(self, result):
        self.assertTrue(result.stdout.strip(), result.stderr)
        return json.loads(result.stdout)

    def state_path(self, repo=None):
        return git_dir(repo or self.repo) / owner_lease.STATE_NAME

    def history_path(self, repo=None):
        return git_dir(repo or self.repo) / owner_lease.HISTORY_NAME

    def expire_lease(self, seconds_past=10, repo=None):
        path = self.state_path(repo)
        lease = json.loads(path.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc)
        expires = now - timedelta(seconds=seconds_past)
        renewed = expires - timedelta(seconds=lease["ttlSeconds"])
        lease["acquiredAt"] = owner_lease._format_utc(renewed)
        lease["renewedAt"] = owner_lease._format_utc(renewed)
        lease["expiresAt"] = owner_lease._format_utc(expires)
        path.write_text(
            json.dumps(lease, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return lease

    def owner_snapshot(self, repo=None):
        snapshot = {}
        for path in git_dir(repo or self.repo).glob("workbar-owner-lease*"):
            content = path.read_bytes()
            snapshot[path.name] = (
                len(content),
                path.stat().st_mtime_ns,
                hashlib.sha256(content).hexdigest(),
            )
        return snapshot

    def test_two_real_subprocesses_compete_atomically(self):
        command_a = [
            sys.executable,
            str(SCRIPT),
            "acquire",
            "--repo",
            str(self.repo),
            "--json",
            *acquire_args(developer="developer-a"),
        ]
        command_b = [
            sys.executable,
            str(SCRIPT),
            "acquire",
            "--repo",
            str(self.repo),
            "--json",
            *acquire_args(developer="developer-b"),
        ]
        process_a = subprocess.Popen(
            command_a,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        process_b = subprocess.Popen(
            command_b,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        output_a, error_a = process_a.communicate(timeout=30)
        output_b, error_b = process_b.communicate(timeout=30)

        self.assertEqual(sorted((process_a.returncode, process_b.returncode)), [0, 3])
        payloads = (json.loads(output_a), json.loads(output_b))
        winner = next(payload for payload in payloads if payload["ok"])
        loser = next(payload for payload in payloads if not payload["ok"])
        self.assertEqual(winner["action"], "acquired")
        self.assertEqual(loser["status"], "conflict")
        self.assertEqual(error_a + error_b, "")
        state = json.loads(self.state_path().read_text(encoding="utf-8"))
        self.assertEqual(state["leaseId"], winner["lease"]["leaseId"])

    def test_same_holder_is_idempotent_and_can_renew(self):
        first = self.run_cli("acquire", *acquire_args())
        self.assertEqual(first.returncode, 0)
        first_payload = self.json_result(first)

        repeated = self.run_cli(
            "acquire",
            *acquire_args(stage="stage-b", relay="relay-b", ttl=120),
        )
        self.assertEqual(repeated.returncode, 0)
        repeated_payload = self.json_result(repeated)
        self.assertEqual(repeated_payload["action"], "renewed")
        self.assertEqual(repeated_payload["lease"]["leaseId"], first_payload["lease"]["leaseId"])
        self.assertEqual(repeated_payload["lease"]["stage"], "stage-b")

        renewed = self.run_cli(
            "renew",
            *holder(),
            "--lease-id",
            first_payload["lease"]["leaseId"],
            "--stage",
            "stage-c",
            "--relay-id",
            "relay-c",
            "--ttl-seconds",
            "180",
        )
        self.assertEqual(renewed.returncode, 0)
        renewed_payload = self.json_result(renewed)
        self.assertEqual(renewed_payload["lease"]["ttlSeconds"], 180)
        self.assertEqual(renewed_payload["lease"]["baseHead"], first_payload["lease"]["baseHead"])

    def test_other_holder_and_wrong_release_are_rejected(self):
        acquired = self.json_result(self.run_cli("acquire", *acquire_args()))
        lease_id = acquired["lease"]["leaseId"]

        other = self.run_cli("acquire", *acquire_args(developer="developer-b"))
        self.assertEqual(other.returncode, owner_lease.EXIT_CONFLICT)
        self.assertEqual(self.json_result(other)["status"], "conflict")

        wrong_release = self.run_cli(
            "release",
            *holder(developer="developer-b"),
            "--lease-id",
            lease_id,
        )
        self.assertEqual(wrong_release.returncode, owner_lease.EXIT_CONFLICT)
        self.assertTrue(self.state_path().exists())

        released = self.run_cli("release", *holder(), "--lease-id", lease_id)
        self.assertEqual(released.returncode, 0)
        self.assertFalse(self.state_path().exists())

    def test_status_is_read_only_and_outputs_stable_text_and_json(self):
        before = self.owner_snapshot()
        plain = self.run_cli("status", json_output=False)
        self.assertEqual(plain.returncode, 0)
        self.assertEqual(plain.stdout.strip(), "STATUS status=none")
        self.assertEqual(self.owner_snapshot(), before)

        acquired = self.json_result(self.run_cli("acquire", *acquire_args()))
        before_active_status = self.owner_snapshot()
        active = self.run_cli("status")
        self.assertEqual(active.returncode, 0)
        active_payload = self.json_result(active)
        self.assertEqual(active_payload["status"], "active")
        self.assertEqual(active_payload["lease"]["leaseId"], acquired["lease"]["leaseId"])
        self.assertEqual(self.owner_snapshot(), before_active_status)

    def test_ttl_bounds_and_schema_exclude_paths_or_business_data(self):
        for ttl in (owner_lease.MIN_TTL_SECONDS - 1, owner_lease.MAX_TTL_SECONDS + 1):
            with self.subTest(ttl=ttl):
                result = self.run_cli("acquire", *acquire_args(ttl=ttl))
                self.assertEqual(result.returncode, owner_lease.EXIT_USAGE)
                self.assertEqual(self.json_result(result)["status"], "invalid_arguments")
        self.assertFalse(self.state_path().exists())

        acquired = self.json_result(self.run_cli("acquire", *acquire_args()))
        lease = acquired["lease"]
        self.assertEqual(set(lease), owner_lease._LEASE_KEYS)
        self.assertEqual(lease["schema"], owner_lease.SCHEMA)
        self.assertEqual(lease["ttlSeconds"], owner_lease.DEFAULT_TTL_SECONDS)
        serialized = json.dumps(lease, ensure_ascii=False)
        self.assertNotIn(str(self.repo), serialized)
        self.assertNotIn("token", serialized.lower())
        self.assertNotIn("credential", serialized.lower())

    def test_fresh_acquire_rejects_preexisting_cached_and_nonrepo_is_code_five(self):
        (self.repo / "tracked.txt").write_text("cached before acquire\n", encoding="utf-8")
        git(self.repo, "add", "tracked.txt")
        cached = self.run_cli("acquire", *acquire_args())
        self.assertEqual(cached.returncode, owner_lease.EXIT_RECOVERY_REQUIRED)
        self.assertEqual(self.json_result(cached)["status"], "recovery_required")
        self.assertFalse(self.state_path().exists())

        not_repo = Path(self.temporary.name) / "不是仓库"
        not_repo.mkdir()
        environment = self.run_cli(
            "status",
            repo=not_repo,
            env={
                **os.environ,
                "GIT_CEILING_DIRECTORIES": str(Path(self.temporary.name).resolve()),
            },
        )
        self.assertEqual(environment.returncode, owner_lease.EXIT_ENVIRONMENT)
        self.assertEqual(self.json_result(environment)["status"], "environment_error")

    def test_expired_acquire_is_refused_and_clock_grace_prevents_double_owner(self):
        acquired = self.json_result(self.run_cli("acquire", *acquire_args()))

        self.expire_lease(seconds_past=2)
        within_grace = self.run_cli("acquire", *acquire_args(developer="developer-b"))
        self.assertEqual(within_grace.returncode, owner_lease.EXIT_CONFLICT)
        status_payload = self.json_result(self.run_cli("status"))
        self.assertEqual(status_payload["status"], "active")
        self.assertTrue(status_payload["withinClockSkewGrace"])

        expired = self.expire_lease(seconds_past=10)
        refused = self.run_cli("acquire", *acquire_args(developer="developer-b"))
        self.assertEqual(refused.returncode, owner_lease.EXIT_RECOVERY_REQUIRED)
        self.assertEqual(self.json_result(refused)["status"], "recovery_required")
        self.assertEqual(expired["leaseId"], acquired["lease"]["leaseId"])
        self.assertEqual(self.json_result(self.run_cli("status"))["status"], "expired")

    def test_reclaim_audits_head_cached_and_expected_lease(self):
        acquired = self.json_result(self.run_cli("acquire", *acquire_args()))
        expired = self.expire_lease()

        wrong_id = self.run_cli(
            "reclaim",
            *acquire_args(developer="developer-b"),
            "--expected-lease-id",
            str(uuid_for_test()),
        )
        self.assertEqual(wrong_id.returncode, owner_lease.EXIT_CONFLICT)

        reclaimed = self.run_cli(
            "reclaim",
            *acquire_args(runtime="dsh", developer="developer-dsh", relay="relay-dsh"),
            "--expected-lease-id",
            expired["leaseId"],
        )
        self.assertEqual(reclaimed.returncode, 0)
        payload = self.json_result(reclaimed)
        self.assertEqual(payload["action"], "reclaimed")
        self.assertEqual(payload["previousLeaseId"], acquired["lease"]["leaseId"])
        self.assertEqual(payload["lease"]["runtime"], "dsh")
        history = json.loads(self.history_path().read_text(encoding="utf-8"))
        self.assertEqual(history["schema"], owner_lease.HISTORY_SCHEMA)
        self.assertEqual(history["entries"][0]["leaseId"], expired["leaseId"])
        self.assertEqual(git(self.repo, "status", "--short").stdout, "")

    def test_reclaim_fails_closed_for_head_or_cached_drift(self):
        acquired = self.json_result(self.run_cli("acquire", *acquire_args()))
        self.expire_lease()
        (self.repo / "tracked.txt").write_text("new commit\n", encoding="utf-8")
        git(self.repo, "add", "tracked.txt")
        git(self.repo, "commit", "-q", "-m", "head drift")
        head_drift = self.run_cli(
            "reclaim",
            *acquire_args(developer="developer-b"),
            "--expected-lease-id",
            acquired["lease"]["leaseId"],
        )
        self.assertEqual(head_drift.returncode, owner_lease.EXIT_RECOVERY_REQUIRED)

        self.temporary.cleanup()
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "缓存漂移"
        init_repo(self.repo)
        acquired = self.json_result(self.run_cli("acquire", *acquire_args()))
        self.expire_lease()
        (self.repo / "tracked.txt").write_text("cached\n", encoding="utf-8")
        git(self.repo, "add", "tracked.txt")
        cached_drift = self.run_cli(
            "reclaim",
            *acquire_args(developer="developer-b"),
            "--expected-lease-id",
            acquired["lease"]["leaseId"],
        )
        self.assertEqual(cached_drift.returncode, owner_lease.EXIT_RECOVERY_REQUIRED)

    def test_damage_and_interrupted_initialization_require_user_review(self):
        self.json_result(self.run_cli("acquire", *acquire_args()))
        self.state_path().write_text("{broken", encoding="utf-8")
        damaged_status = self.run_cli("status")
        self.assertEqual(damaged_status.returncode, owner_lease.EXIT_RECOVERY_REQUIRED)
        damaged_reclaim = self.run_cli(
            "reclaim",
            *acquire_args(developer="developer-b"),
            "--expected-lease-id",
            str(uuid_for_test()),
        )
        self.assertEqual(damaged_reclaim.returncode, owner_lease.EXIT_RECOVERY_REQUIRED)

        self.temporary.cleanup()
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "初始化中断"
        init_repo(self.repo)
        incomplete = git_dir(self.repo) / f"{owner_lease.STATE_NAME}.tmp-interrupted"
        incomplete.write_text("partial", encoding="utf-8")
        acquire = self.run_cli("acquire", *acquire_args())
        reclaim = self.run_cli(
            "reclaim",
            *acquire_args(developer="developer-b"),
            "--expected-lease-id",
            str(uuid_for_test()),
        )
        self.assertEqual(acquire.returncode, owner_lease.EXIT_RECOVERY_REQUIRED)
        self.assertEqual(reclaim.returncode, owner_lease.EXIT_RECOVERY_REQUIRED)

    def test_history_is_bounded(self):
        payload = self.json_result(self.run_cli("acquire", *acquire_args()))
        for index in range(owner_lease.HISTORY_LIMIT + 3):
            expired = self.expire_lease()
            runtime = "dsh" if index % 2 else "codex"
            payload = self.json_result(
                self.run_cli(
                    "reclaim",
                    *acquire_args(
                        runtime=runtime,
                        approval=f"approval-{index}",
                        developer=f"developer-{index}",
                        stage=f"stage-{index}",
                        relay=f"relay-{index}",
                    ),
                    "--expected-lease-id",
                    expired["leaseId"],
                ),
            )
        history = json.loads(self.history_path().read_text(encoding="utf-8"))
        self.assertEqual(len(history["entries"]), owner_lease.HISTORY_LIMIT)
        self.assertEqual(history["entries"][-1]["leaseId"], expired["leaseId"])
        self.assertEqual(payload["status"], "active")

    def test_regular_and_linked_worktree_git_dirs_never_pollute_status(self):
        acquired = self.json_result(self.run_cli("acquire", *acquire_args()))
        self.assertEqual(git(self.repo, "status", "--short").stdout, "")
        main_git_dir = git_dir(self.repo)
        self.assertTrue((main_git_dir / owner_lease.STATE_NAME).exists())
        self.run_cli("release", *holder(), "--lease-id", acquired["lease"]["leaseId"])

        linked = Path(self.temporary.name) / "链接工作树"
        git(self.repo, "worktree", "add", "-q", "-b", "lease-linked-test", str(linked))
        linked_payload = self.json_result(
            self.run_cli("acquire", *acquire_args(developer="linked-developer"), repo=linked),
        )
        linked_git_dir = git_dir(linked)
        self.assertNotEqual(linked_git_dir, main_git_dir)
        self.assertTrue((linked_git_dir / owner_lease.STATE_NAME).exists())
        self.assertFalse((main_git_dir / owner_lease.STATE_NAME).exists())
        self.assertEqual(git(linked, "status", "--short").stdout, "")
        released = self.run_cli(
            "release",
            *holder(developer="linked-developer"),
            "--lease-id",
            linked_payload["lease"]["leaseId"],
            repo=linked,
        )
        self.assertEqual(released.returncode, 0)


def uuid_for_test():
    return "00000000-0000-4000-8000-000000000000"


if __name__ == "__main__":
    unittest.main()
