import io
import json
import subprocess
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr
from pathlib import Path
from unittest import mock

import release
import release_state
import verification


def git(cwd, *args):
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.strip()


class TestReleaseCredential(unittest.TestCase):
    def test_credential_path_preserves_unicode_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "中文项目"
            (root / ".git").mkdir(parents=True)
            self.assertEqual(
                release_state.resolve_credential_path(root, "1.2.3"),
                root / ".git" / "code-release" / "v1.2.3.json",
            )

    def test_sealed_credential_rejects_damage_and_tampering(self):
        payload = {
            "schema": release_state.SCHEMA,
            "version": "1.2.3",
            "tag": "v1.2.3",
            "state": "prepared",
            "baseline": {},
            "releaseFiles": [],
            "verification": {},
            "artifact": {},
            "environment": {},
            "publication": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credential.json"
            self.assertEqual(
                release_state.seal_credential(payload),
                release_state.seal_credential(payload),
            )
            sealed = release_state.save_credential(path, payload)
            self.assertEqual(release_state.load_credential(path), sealed)

            damaged = json.loads(path.read_text(encoding="utf-8"))
            damaged["version"] = "9.9.9"
            path.write_text(json.dumps(damaged), encoding="utf-8")
            with self.assertRaises(release_state.CredentialError):
                release_state.load_credential(path)

            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(release_state.CredentialError):
                release_state.load_credential(path)

    def test_record_validation_rejects_unsafe_or_changed_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "safe.txt").write_text("safe", encoding="utf-8")
            records = release_state.record_files(root, ("safe.txt",))
            self.assertEqual(release_state.validate_recorded_files(root, records), [])
            (root / "safe.txt").write_text("changed", encoding="utf-8")
            self.assertTrue(release_state.validate_recorded_files(root, records))
            self.assertTrue(
                release_state.validate_recorded_files(
                    root,
                    ({"path": "../outside", "size": 0, "sha256": "x"},),
                ),
            )


class TestPrepareAtomicFailure(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs" / "releases").mkdir(parents=True)
        (self.root / "VERSION").write_text("1.0.0\n", encoding="utf-8")
        (self.root / "file_version_info.txt").write_text("old-info\n", encoding="utf-8")
        (self.root / "README.md").write_text("old-readme\n", encoding="utf-8")
        (self.root / "Code-v1.0.0.spec").write_text("old-spec\n", encoding="utf-8")
        self.credential_path = self.root / "credential.json"
        self.stack = ExitStack()
        self.stack.enter_context(mock.patch.object(release, "ROOT", self.root))
        self.stack.enter_context(mock.patch.object(release, "VERSION_FILE", self.root / "VERSION"))
        self.stack.enter_context(
            mock.patch.object(release, "VERSION_INFO_FILE", self.root / "file_version_info.txt"),
        )
        self.stack.enter_context(mock.patch.object(release, "README_FILE", self.root / "README.md"))
        self.stack.enter_context(
            mock.patch.object(release, "RELEASES_DIR", self.root / "docs" / "releases"),
        )
        self.stack.enter_context(mock.patch.object(release, "_git_branch", return_value="master"))
        self.stack.enter_context(mock.patch.object(release, "_ensure_cached_empty"))
        self.stack.enter_context(mock.patch.object(release, "_git_head", return_value="base-head"))
        self.stack.enter_context(mock.patch.object(release, "_git_index_tree", return_value="index-tree"))
        self.stack.enter_context(mock.patch.object(release, "_credential_path", return_value=self.credential_path))
        self.stack.enter_context(mock.patch.object(release, "_tracked_state_digest", return_value="outside"))

    def tearDown(self):
        self.stack.close()
        self._tmp.cleanup()

    def test_remote_preflight_happens_before_metadata_and_failure_rolls_back(self):
        events = []

        def preflight(version, head):
            events.append("preflight")
            return {"repository": "owner/repo", "originHead": "origin-head"}

        def update_version(version):
            events.append("metadata")
            release.VERSION_FILE.write_text(version + "\n", encoding="utf-8")

        with mock.patch.object(release, "remote_read_only_preflight", side_effect=preflight), \
                mock.patch.object(release, "update_version_file", side_effect=update_version), \
                mock.patch.object(release, "update_version_info"), \
                mock.patch.object(release, "update_readme"), \
                mock.patch.object(release, "create_spec_file"), \
                mock.patch.object(release, "verify_version_consistency"), \
                mock.patch.object(
                    release,
                    "run_release_quality_checks",
                    side_effect=RuntimeError("synthetic gate failure"),
                ):
            with self.assertRaisesRegex(RuntimeError, "synthetic gate failure"):
                release.prepare_release("1.0.1")

        self.assertEqual(events[:2], ["preflight", "metadata"])
        self.assertEqual((self.root / "VERSION").read_text(encoding="utf-8"), "1.0.0\n")
        self.assertFalse(self.credential_path.exists())

    def test_preflight_failure_leaves_no_valid_credential_or_metadata_delta(self):
        self.credential_path.write_text("stale", encoding="utf-8")
        with mock.patch.object(
            release,
            "remote_read_only_preflight",
            side_effect=SystemExit(1),
        ), mock.patch.object(release, "update_version_file") as update_version:
            with self.assertRaises(SystemExit):
                release.prepare_release("1.0.1")
        update_version.assert_not_called()
        self.assertEqual((self.root / "VERSION").read_text(encoding="utf-8"), "1.0.0\n")
        self.assertFalse(self.credential_path.exists())

    def test_success_creates_bound_prepared_credential_without_publication(self):
        events = []
        target_spec = self.root / "Code-v1.0.1.spec"
        target_notes = self.root / "docs" / "releases" / "v1.0.1.md"
        artifact = self.root / "dist" / "Code-v1.0.1.exe"

        def preflight(version, head):
            events.append("preflight")
            return {"repository": "owner/repo", "originHead": "origin-head"}

        def update_version(version):
            events.append("metadata")
            release.VERSION_FILE.write_text(version + "\n", encoding="utf-8")

        def update_info(version, version_tuple):
            release.VERSION_INFO_FILE.write_text(f"info {version}\n", encoding="utf-8")

        def update_readme(version):
            release.README_FILE.write_text(f"readme {version}\n", encoding="utf-8")

        def create_spec(version, old_version):
            target_spec.write_text(f"spec {version}\n", encoding="utf-8")

        def build(version):
            artifact.parent.mkdir()
            artifact.write_bytes(b"prepared-exe")

        def generate_notes(version, sha256, size):
            target_notes.write_text(
                f"# Code v{version} Release Notes\n\n已验证的发布说明。\n",
                encoding="utf-8",
            )
            return target_notes

        release_paths = release._release_paths("1.0.1")
        with mock.patch.object(release, "remote_read_only_preflight", side_effect=preflight), \
                mock.patch.object(release, "update_version_file", side_effect=update_version), \
                mock.patch.object(release, "update_version_info", side_effect=update_info), \
                mock.patch.object(release, "update_readme", side_effect=update_readme), \
                mock.patch.object(release, "create_spec_file", side_effect=create_spec), \
                mock.patch.object(release, "verify_version_consistency"), \
                mock.patch.object(release, "run_release_quality_checks") as quality, \
                mock.patch.object(release, "build_exe", side_effect=build), \
                mock.patch.object(
                    release,
                    "require_exe_metadata",
                    return_value={
                        "ProductVersion": "1.0.1",
                        "FileVersion": "1.0.1",
                        "OriginalFilename": "Code-v1.0.1.exe",
                    },
                ), mock.patch.object(release, "compute_sha256", return_value="ABC123"), \
                mock.patch.object(release, "generate_release_notes", side_effect=generate_notes), \
                mock.patch.object(release, "require_release_notes_ready"), \
                mock.patch.object(
                    release,
                    "_changed_release_paths",
                    return_value=release_paths,
                ), mock.patch.object(
                    release,
                    "_git_blob_hash",
                    side_effect=lambda path, revision=None: f"blob-{revision or 'current'}-{path}",
                ), mock.patch.object(
                    release,
                    "_environment_fingerprint",
                    return_value={"repository": "owner/repo", "platform": "test"},
                ):
            release.prepare_release("1.0.1")

        quality.assert_called_once_with(dry_run=False, skip_tests=False)
        self.assertEqual(events[:2], ["preflight", "metadata"])
        credential = release_state.load_credential(self.credential_path)
        self.assertEqual(credential["state"], "prepared")
        self.assertEqual(credential["baseline"]["head"], "base-head")
        self.assertEqual(credential["publication"]["lastCompleted"], "prepared")
        self.assertIsNone(credential["publication"]["startedAt"])
        self.assertNotIn("h4", credential["verification"]["checkIds"])
        pytest_manifest = next(
            item
            for item in verification.get_release_definition_manifest()["checks"]
            if item["id"] == "pytest_full"
        )
        self.assertEqual(pytest_manifest["timeout"], 360)
        self.assertEqual(
            credential["verification"]["definitionSha256"],
            release.get_release_definition_fingerprint(),
        )
        self.assertTrue(all(not Path(item["path"]).is_absolute() for item in credential["releaseFiles"]))


class TestCredentialInvalidationMatrix(unittest.TestCase):
    def _credential(self):
        return {
            "version": "1.2.3",
            "releaseFiles": [],
            "verification": {
                "checkIds": list(release.get_release_check_ids(dry_run=False, skip_tests=False)),
                "definitionSha256": release.get_release_definition_fingerprint(),
            },
            "environment": {"repository": "owner/repo", "marker": "expected"},
            "artifact": {
                "path": "dist/Code-v1.2.3.exe",
                "size": 3,
                "sha256": release_state.sha256_bytes(b"exe"),
                "peMetadata": {},
            },
        }

    def test_verification_definition_drift_fails_before_reuse(self):
        credential = self._credential()
        credential["verification"]["definitionSha256"] = "stale"
        with mock.patch.object(release, "_release_paths", return_value=()), \
                mock.patch.object(release, "validate_recorded_files", return_value=[]):
            with self.assertRaises(SystemExit):
                release._validate_static_credential(credential, "1.2.3")

    def test_environment_drift_fails_before_artifact_reuse(self):
        credential = self._credential()
        with mock.patch.object(release, "_release_paths", return_value=()), \
                mock.patch.object(release, "validate_recorded_files", return_value=[]), \
                mock.patch.object(
                    release,
                    "_environment_fingerprint",
                    return_value={"repository": "owner/repo", "marker": "changed"},
                ):
            with self.assertRaises(SystemExit):
                release._validate_static_credential(credential, "1.2.3")

    def test_artifact_tamper_fails_closed(self):
        credential = self._credential()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / credential["artifact"]["path"]
            artifact.parent.mkdir(parents=True)
            artifact.write_bytes(b"bad")
            with mock.patch.object(release, "ROOT", root), \
                    mock.patch.object(release, "_release_paths", return_value=()), \
                    mock.patch.object(release, "validate_recorded_files", return_value=[]), \
                    mock.patch.object(
                        release,
                        "_environment_fingerprint",
                        return_value=credential["environment"],
                    ):
                with self.assertRaises(SystemExit):
                    release._validate_static_credential(credential, "1.2.3")


class TestRemoteReadOnlyPreflight(unittest.TestCase):
    def test_missing_gh_fails_without_git_or_release_mutation(self):
        with mock.patch.object(release, "_gh_is_available", return_value=False), \
                mock.patch.object(release, "run") as mutating_run:
            with self.assertRaises(SystemExit):
                release.remote_read_only_preflight("1.2.3", "base")
        mutating_run.assert_not_called()

    def test_existing_remote_tag_stops_before_release_lookup(self):
        def quiet(cmd, *, cwd=None, timeout=120):
            if cmd[1:3] == ["auth", "status"]:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if cmd[1:3] == ["repo", "view"]:
                return subprocess.CompletedProcess(cmd, 0, "owner/repo\n", "")
            if cmd[0:3] == ["git", "merge-base", "--is-ancestor"]:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if cmd[0:4] == ["git", "rev-parse", "-q", "--verify"]:
                return subprocess.CompletedProcess(cmd, 1, "", "")
            return subprocess.CompletedProcess(cmd, 2, "", "unexpected")

        with mock.patch.object(release, "_gh_is_available", return_value=True), \
                mock.patch.object(release, "run_quiet", side_effect=quiet), \
                mock.patch.object(release, "_read_remote_branch", return_value="origin"), \
                mock.patch.object(release, "_read_remote_tag", return_value="conflict"), \
                mock.patch.object(release, "_read_remote_release") as release_lookup:
            with self.assertRaises(SystemExit):
                release.remote_read_only_preflight("1.2.3", "base")
        release_lookup.assert_not_called()


class FakeGh:
    def __init__(self):
        self.release = None
        self.create_count = 0
        self.upload_count = 0
        self.fail_upload_once = False

    @staticmethod
    def completed(cmd, returncode=0, stdout="", stderr=""):
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)

    def run(self, cmd):
        if cmd[1:3] == ["release", "view"]:
            if self.release is None:
                return self.completed(cmd, 1, stderr="release not found")
            return self.completed(cmd, stdout=json.dumps(self.release, ensure_ascii=False))
        if cmd[1:3] == ["release", "create"]:
            self.create_count += 1
            tag = cmd[3]
            title = cmd[cmd.index("--title") + 1]
            notes = Path(cmd[cmd.index("--notes-file") + 1]).read_text(encoding="utf-8")
            self.release = {
                "tagName": tag,
                "name": title,
                "body": notes,
                "targetCommitish": "master",
                "assets": [],
            }
            return self.completed(cmd, stdout="created")
        if cmd[1:3] == ["release", "upload"]:
            self.upload_count += 1
            if self.fail_upload_once:
                self.fail_upload_once = False
                return self.completed(cmd, 9, stderr="synthetic upload failure")
            artifact = Path(cmd[4])
            self.release["assets"] = [
                {
                    "name": artifact.name,
                    "size": artifact.stat().st_size,
                    "digest": f"sha256:{release_state.sha256_file(artifact)}",
                },
            ]
            return self.completed(cmd, stdout="uploaded")
        return self.completed(cmd, 2, stderr="unexpected fake gh command")


class TestPublishResumeIntegration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.root = base / "repo"
        self.remote = base / "origin.git"
        self.root.mkdir()
        git(self.root, "init", "-b", "master")
        git(self.root, "config", "user.name", "Release Test")
        git(self.root, "config", "user.email", "release-test@example.invalid")
        (self.root / "docs" / "releases").mkdir(parents=True)
        (self.root / "dist").mkdir()
        (self.root / "VERSION").write_text("1.0.0\n", encoding="utf-8")
        (self.root / "file_version_info.txt").write_text("version=1.0.0\n", encoding="utf-8")
        (self.root / "README.md").write_text("download 1.0.0\n", encoding="utf-8")
        (self.root / "Code-v1.0.0.spec").write_text("spec 1.0.0\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "base")
        self.base_head = git(self.root, "rev-parse", "HEAD")
        git(base, "init", "--bare", str(self.remote))
        git(self.root, "remote", "add", "origin", str(self.remote))
        git(self.root, "push", "-u", "origin", "master")

        (self.root / "VERSION").write_text("1.0.1\n", encoding="utf-8")
        (self.root / "file_version_info.txt").write_text("version=1.0.1\n", encoding="utf-8")
        (self.root / "README.md").write_text("download 1.0.1\n", encoding="utf-8")
        (self.root / "Code-v1.0.1.spec").write_text("spec 1.0.1\n", encoding="utf-8")
        (self.root / "docs" / "releases" / "v1.0.1.md").write_text(
            "# Code v1.0.1 Release Notes\n\n已验证的测试发布说明。\n",
            encoding="utf-8",
        )
        (self.root / "dist" / "Code-v1.0.1.exe").write_bytes(b"synthetic-exe")

        self.stack = ExitStack()
        self.stack.enter_context(mock.patch.object(release, "ROOT", self.root))
        self.stack.enter_context(mock.patch.object(release, "VERSION_FILE", self.root / "VERSION"))
        self.stack.enter_context(
            mock.patch.object(release, "VERSION_INFO_FILE", self.root / "file_version_info.txt"),
        )
        self.stack.enter_context(mock.patch.object(release, "README_FILE", self.root / "README.md"))
        self.stack.enter_context(
            mock.patch.object(release, "RELEASES_DIR", self.root / "docs" / "releases"),
        )
        self.stack.enter_context(mock.patch.object(release, "GH_COMMAND", ("fake-gh",)))
        self.fake_gh = FakeGh()

        def quiet(cmd, *, cwd=None, timeout=120):
            if cmd[0] == "fake-gh":
                return self.fake_gh.run(cmd)
            return subprocess.run(
                list(cmd),
                cwd=str(cwd or self.root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )

        self.stack.enter_context(mock.patch.object(release, "run_quiet", side_effect=quiet))
        self.stack.enter_context(mock.patch.object(release, "_validate_static_credential"))
        self.credential_path = self.root / ".git" / "code-release" / "v1.0.1.json"
        self.credential = self._make_credential()
        self.credential = release_state.save_credential(self.credential_path, self.credential)

    def tearDown(self):
        self.stack.close()
        self._tmp.cleanup()

    def _make_credential(self):
        paths = release._release_paths("1.0.1")
        records = release_state.record_files(self.root, paths)
        for record in records:
            record["gitBlob"] = git(
                self.root,
                "hash-object",
                f"--path={record['path']}",
                "--",
                record["path"],
            )
        artifact = self.root / "dist" / "Code-v1.0.1.exe"
        return {
            "schema": release_state.SCHEMA,
            "version": "1.0.1",
            "tag": "v1.0.1",
            "state": "publishing",
            "createdAt": "2026-08-16T00:00:00+00:00",
            "baseline": {
                "head": self.base_head,
                "branch": "master",
                "originHead": self.base_head,
                "indexTree": git(self.root, "write-tree"),
                "outsideTrackedSha256": release._tracked_state_digest(self.base_head, paths),
                "oldVersion": "1.0.0",
            },
            "releaseFiles": records,
            "changedReleaseFiles": list(release._changed_release_paths(self.base_head, paths)),
            "verification": {"definitionSha256": "test", "checkIds": []},
            "artifact": {
                "path": "dist/Code-v1.0.1.exe",
                "size": artifact.stat().st_size,
                "sha256": release_state.sha256_file(artifact),
                "peMetadata": {},
            },
            "environment": {"repository": "owner/repo"},
            "publication": {
                "startedAt": "2026-08-16T00:00:01+00:00",
                "commit": None,
                "lastCompleted": "prepared",
                "completedAt": None,
            },
        }

    def test_publish_and_repeated_resume_are_idempotent(self):
        completed = release._continue_publication(self.credential_path, self.credential)
        self.assertEqual(completed["state"], "published")
        commit = completed["publication"]["commit"]
        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/master"), commit)
        self.assertEqual(git(self.remote, "rev-parse", "refs/tags/v1.0.1"), commit)
        self.assertEqual(self.fake_gh.create_count, 1)
        self.assertEqual(self.fake_gh.upload_count, 1)

        loaded = release_state.load_credential(self.credential_path)
        release._continue_publication(self.credential_path, loaded)
        self.assertEqual(self.fake_gh.create_count, 1)
        self.assertEqual(self.fake_gh.upload_count, 1)

    def test_upload_failure_resumes_without_recreating_release(self):
        self.fake_gh.fail_upload_once = True
        with self.assertRaises(SystemExit):
            release._continue_publication(self.credential_path, self.credential)
        self.assertEqual(self.fake_gh.create_count, 1)
        self.assertEqual(self.fake_gh.upload_count, 1)
        interrupted = release_state.load_credential(self.credential_path)
        self.assertEqual(interrupted["state"], "publishing")
        self.assertEqual(interrupted["publication"]["lastCompleted"], "release")

        completed = release._continue_publication(self.credential_path, interrupted)
        self.assertEqual(completed["state"], "published")
        self.assertEqual(self.fake_gh.create_count, 1)
        self.assertEqual(self.fake_gh.upload_count, 2)

    def test_conflicting_asset_fails_without_upload_or_clobber(self):
        notes = (self.root / "docs" / "releases" / "v1.0.1.md").read_text(encoding="utf-8")
        self.fake_gh.release = {
            "tagName": "v1.0.1",
            "name": "Code v1.0.1",
            "body": notes,
            "targetCommitish": "master",
            "assets": [
                {"name": "Code-v1.0.1.exe", "size": 999, "digest": "sha256:deadbeef"},
            ],
        }
        with self.assertRaises(SystemExit):
            release._continue_publication(self.credential_path, self.credential)
        self.assertEqual(self.fake_gh.upload_count, 0)

    def test_remote_branch_conflict_never_attempts_push(self):
        with mock.patch.object(release, "_read_remote_branch", return_value="different"), \
                mock.patch.object(release, "run") as run_command:
            with self.assertRaises(SystemExit):
                release._ensure_remote_branch(
                    self.credential_path,
                    self.credential,
                    "expected-commit",
                )
        run_command.assert_not_called()

    def test_local_tag_conflict_is_never_deleted_or_recreated(self):
        with mock.patch.object(release, "_local_tag_commit", return_value="different"), \
                mock.patch.object(release, "run") as run_command:
            with self.assertRaises(SystemExit):
                release._ensure_local_tag(
                    self.credential_path,
                    self.credential,
                    "expected-commit",
                )
        run_command.assert_not_called()

    def test_release_body_conflict_stops_before_asset_handling(self):
        info = {
            "tagName": "v1.0.1",
            "name": "Code v1.0.1",
            "body": "different body",
            "assets": [],
        }
        with self.assertRaises(SystemExit):
            release._audit_release_metadata(info, self.credential)


class TestReleaseCliContracts(unittest.TestCase):
    def assert_rejected_before_action(self, argv):
        guarded_names = (
            "parse_version",
            "detect_windows_proxy",
            "prepare_release",
            "publish_prepared",
            "resume_release",
            "remote_read_only_preflight",
            "run",
            "run_quiet",
        )
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(release.sys, "argv", argv))
            guarded = {
                name: stack.enter_context(mock.patch.object(release, name))
                for name in guarded_names
            }
            stderr = io.StringIO()
            stack.enter_context(redirect_stderr(stderr))
            with self.assertRaises(SystemExit) as raised:
                release.main()

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("error:", stderr.getvalue())
        for name, guarded_call in guarded.items():
            with self.subTest(argv=argv, guarded=name):
                guarded_call.assert_not_called()

    def test_version_first_flags_and_compatibility_aliases_dispatch_identically(self):
        cases = (
            (
                "prepare",
                ["release.py", "1.2.3", "--prepare", "--no-proxy"],
                ["release.py", "prepare", "1.2.3", "--no-proxy"],
                "prepare_release",
                mock.call("1.2.3"),
            ),
            (
                "publish-prepared",
                ["release.py", "1.2.3", "--publish-prepared", "--no-proxy"],
                ["release.py", "publish-prepared", "1.2.3", "--no-proxy"],
                "publish_prepared",
                mock.call("1.2.3", auto_yes=False),
            ),
            (
                "resume",
                ["release.py", "1.2.3", "--resume", "--no-proxy"],
                ["release.py", "resume", "1.2.3", "--no-proxy"],
                "resume_release",
                mock.call("1.2.3", auto_yes=False),
            ),
        )
        for action, canonical, alias, expected_name, expected_call in cases:
            for syntax, argv in (("canonical", canonical), ("alias", alias)):
                with self.subTest(action=action, syntax=syntax), ExitStack() as stack:
                    stack.enter_context(mock.patch.object(release.sys, "argv", argv))
                    actions = {
                        name: stack.enter_context(mock.patch.object(release, name))
                        for name in ("prepare_release", "publish_prepared", "resume_release")
                    }
                    proxy_detection = stack.enter_context(
                        mock.patch.object(release, "detect_windows_proxy"),
                    )
                    release.main()

                self.assertEqual(actions[expected_name].call_args, expected_call)
                for name, action_call in actions.items():
                    if name != expected_name:
                        action_call.assert_not_called()
                proxy_detection.assert_not_called()

    def test_all_ambiguous_action_combinations_fail_before_any_action(self):
        action_flags = ("--prepare", "--publish-prepared", "--resume")
        action_aliases = ("prepare", "publish-prepared", "resume")
        invalid = []
        for index, left in enumerate(action_flags):
            for right in action_flags[index + 1:]:
                invalid.append(["release.py", "1.2.3", left, right])
        for alias in action_aliases:
            for action_flag in action_flags:
                invalid.append(["release.py", alias, "1.2.3", action_flag])
        for action_flag in action_flags:
            invalid.append(["release.py", "1.2.3", action_flag, "--dry-run"])
            invalid.append(["release.py", "1.2.3", action_flag, "--skip-tests"])
        for alias in action_aliases:
            invalid.append(["release.py", alias, "1.2.3", "--dry-run"])
            invalid.append(["release.py", alias, "1.2.3", "--skip-tests"])

        for argv in invalid:
            with self.subTest(argv=argv):
                self.assert_rejected_before_action(argv)

    def test_resume_rejects_a_never_started_prepared_credential(self):
        credential = {
            "version": "1.2.3",
            "tag": "v1.2.3",
            "state": "prepared",
        }
        with mock.patch.object(
            release,
            "_load_prepared_credential",
            return_value=(Path("credential.json"), credential),
        ):
            with self.assertRaises(SystemExit):
                release.resume_release("1.2.3", auto_yes=True)

    def test_publish_marks_credential_started_before_continuation(self):
        credential = {
            "version": "1.2.3",
            "tag": "v1.2.3",
            "state": "prepared",
            "publication": {"startedAt": None},
        }

        def save(path, value):
            return value

        with mock.patch.object(
            release,
            "_load_prepared_credential",
            return_value=(Path("credential.json"), credential),
        ), mock.patch.object(release, "_validate_prepared_candidate"), \
                mock.patch.object(release, "save_credential", side_effect=save), \
                mock.patch.object(release, "_continue_publication") as continuation:
            release.publish_prepared("1.2.3", auto_yes=True)

        started = continuation.call_args.args[1]
        self.assertEqual(started["state"], "publishing")
        self.assertIsNotNone(started["publication"]["startedAt"])


if __name__ == "__main__":
    unittest.main()
