"""Release recovery with real synthetic Git/files; no network or real packaging."""
import copy
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest import mock

import pytest

import build_exe
import release
from devtools import release_inputs, release_state


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout.strip()


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "docs/releases").mkdir(parents=True)
    (root / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    (root / "README.md").write_text('<img src="https://img.shields.io/badge/version-1.0.0-2563EB" alt="Version 1.0.0"> Code-v1.0.0.exe', encoding="utf-8")
    (root / "file_version_info.txt").write_text("'FileVersion', '1.0.0'\n'ProductVersion', '1.0.0'\n'OriginalFilename', 'Code-v1.0.0.exe'\nfilevers=(1, 0, 0, 0)\nprodvers=(1, 0, 0, 0)", encoding="utf-8")
    (root / ".gitignore").write_text("dist/\nbuild/\n", encoding="utf-8")
    (root / "app.py").write_text("# synthetic source\n", encoding="utf-8")
    (root / "docs/releases/v1.0.1.md").write_text("## 更新\n\n合成发布说明。\n", encoding="utf-8")
    git(root, "init", "-b", "master")
    git(root, "config", "user.name", "Synthetic release")
    git(root, "config", "user.email", "release@example.invalid")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    head = git(root, "rev-parse", "HEAD")
    for name, value in {"ROOT": root, "VERSION_FILE": root / "VERSION",
                        "README_FILE": root / "README.md", "VERSION_INFO_FILE": root / "file_version_info.txt",
                        "RELEASES_DIR": root / "docs/releases"}.items():
        monkeypatch.setattr(release, name, value)
    env = {"platform": "test", "machine": "test", "python": "3.test", "git": "git old",
           "gh": "gh old", "repository": "synthetic/repo", "branch": "master"}
    monkeypatch.setattr(release, "_environment_fingerprint", lambda repo: copy.deepcopy(env))
    monkeypatch.setattr(release, "build_environment", lambda root: {"node": "test", "packages": "test"})
    monkeypatch.setattr(release, "frontend_proof", lambda root: {"synthetic": "frontend"})
    monkeypatch.setattr(release, "remote_read_only_preflight", lambda version, baseline: {"repository": "synthetic/repo", "originHead": head})
    monkeypatch.setattr(release, "require_prepare_inputs", lambda version: None)
    monkeypatch.setattr(release, "prepare_frontend_assets", mock.Mock())
    quality = mock.Mock()
    monkeypatch.setattr(release, "run_release_quality_checks", quality)
    artifact = root / "dist/Code-v1.0.1.exe"

    def build(version):
        artifact.parent.mkdir(exist_ok=True)
        artifact.write_bytes(b"synthetic exe, no executable code")

    builder = mock.Mock(side_effect=build)
    monkeypatch.setattr(release, "build_exe", builder)
    monkeypatch.setattr(release, "require_exe_metadata", lambda version: release._expected_exe_metadata(version))
    release.prepare_release("1.0.1")
    path = release._credential_path("1.0.1")
    return SimpleNamespace(root=root, path=path, env=env, quality=quality, builder=builder,
                           artifact=artifact, notes=root / "docs/releases/v1.0.1.md",
                           load=lambda: release_state.load_credential(path))


@pytest.mark.parametrize("change", ["notes", "git", "gh", "both"])
def test_refresh_reuses_exact_product_evidence(candidate, change):
    c = candidate
    original = c.load()
    if change in {"notes", "both"}:
        c.notes.write_text(c.notes.read_text(encoding="utf-8").replace("合成发布说明", "新的中文发布说明"), encoding="utf-8")
    if change in {"git", "gh", "both"}:
        c.env["gh" if change == "both" else change] += " upgraded"
    release.refresh_prepared("1.0.1")
    refreshed = c.load()
    assert refreshed["verification"] == original["verification"]
    assert refreshed["artifact"] == original["artifact"]
    assert refreshed["baseline"] == original["baseline"]
    assert c.quality.call_count == c.builder.call_count == 1
    assert refreshed["refresh"]["fullSuiteRerun"] is False
    assert refreshed["state"] == "prepared" and not refreshed["publication"]["startedAt"]
    assert len(list((c.path.parent / "audit").glob("*.json"))) == 1


@pytest.mark.parametrize("relative", ["app.py", "tests/new_test.py", "unknown.txt", "data/unknown.md", "data/skills/demo/SKILL.md", "data/skills/demo/resource.bin", "assets/ignored.dat"])
def test_unknown_or_actual_input_changes_never_refresh(candidate, relative):
    c = candidate
    original = c.path.read_bytes()
    target = c.root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"changed")
    with pytest.raises(SystemExit):
        release.refresh_prepared("1.0.1")
    assert c.path.read_bytes() == original
    assert c.quality.call_count == c.builder.call_count == 1


@pytest.mark.parametrize("change", ["frame", "readme", "artifact", "python", "head", "cached", "placeholder", "frontend", "build_environment", "remote"])
def test_refresh_failure_is_zero_credential_mutation(candidate, monkeypatch, change):
    c = candidate
    original = c.path.read_bytes()
    if change == "frame":
        c.notes.write_text(c.notes.read_text(encoding="utf-8") + "outside", encoding="utf-8")
    elif change == "placeholder":
        c.notes.write_text(c.notes.read_text(encoding="utf-8").replace("合成发布说明", "待补充"), encoding="utf-8")
    elif change == "readme":
        (c.root / "README.md").write_text("changed", encoding="utf-8")
    elif change == "artifact":
        c.artifact.write_bytes(b"corrupt")
    elif change == "python":
        c.env["python"] = "new"
    elif change == "head":
        git(c.root, "commit", "--allow-empty", "-m", "drift")
    elif change == "cached":
        git(c.root, "add", "VERSION")
    elif change == "frontend":
        monkeypatch.setattr(release, "frontend_proof", lambda root: {"changed": True})
    elif change == "build_environment":
        monkeypatch.setattr(release, "build_environment", lambda root: {"changed": True})
    else:
        monkeypatch.setattr(release, "remote_read_only_preflight", lambda *args: (_ for _ in ()).throw(SystemExit(1)))
    with pytest.raises(SystemExit):
        release.refresh_prepared("1.0.1")
    assert c.path.read_bytes() == original


@pytest.mark.parametrize("legacy", [False, True])
def test_same_version_reprepare_and_failed_retry_preserve_user_files(candidate, monkeypatch, legacy):
    c = candidate
    source = c.load()
    if legacy:
        source["schema"] = release_state.SCHEMA
        source.pop("reuseBinding")
        release_state.save_credential(c.path, source)
    (c.root / "app.py").write_text("# changed source\n", encoding="utf-8")
    git(c.root, "add", "app.py")
    git(c.root, "commit", "-m", "commit product repair before reprepare")
    c.notes.write_text(c.notes.read_text(encoding="utf-8").replace("合成发布说明", "用户新增说明"), encoding="utf-8")
    before = {p: (c.root / p).read_bytes() for p in release._release_paths("1.0.1")}
    c.quality.side_effect = RuntimeError("synthetic quality failure")
    with pytest.raises(RuntimeError, match="synthetic quality"):
        release.reprepare_release("1.0.1")
    assert c.load()["state"] == "reprepare_pending"
    assert before == {p: (c.root / p).read_bytes() for p in before}
    with pytest.raises(SystemExit):
        release.publish_prepared("1.0.1", auto_yes=True)
    c.quality.side_effect = None
    release.reprepare_release("1.0.1")
    assert c.load()["schema"] == release_state.CURRENT_SCHEMA
    assert c.load()["state"] == "prepared"
    assert c.load()["baseline"]["oldVersion"] == "1.0.0"
    assert "用户新增说明" in c.notes.read_text(encoding="utf-8")
    assert c.quality.call_count == 3 and c.builder.call_count == 2


@pytest.mark.parametrize("state", ["publishing", "published"])
def test_started_publication_never_rebinds(candidate, state):
    c = candidate
    source = c.load()
    source["state"] = state
    source["publication"]["startedAt"] = "2026-09-08T00:00:00Z"
    release_state.save_credential(c.path, source)
    original = c.path.read_bytes()
    for action in (release.refresh_prepared, release.reprepare_release):
        with pytest.raises(SystemExit):
            action("1.0.1")
        assert c.path.read_bytes() == original


def test_v1_does_not_gain_refresh_evidence(candidate):
    source = candidate.load()
    source["schema"] = release_state.SCHEMA
    source.pop("reuseBinding")
    release_state.save_credential(candidate.path, source)
    release._validate_prepared_candidate(source, "1.0.1")
    with pytest.raises(SystemExit, match="1"):
        release.refresh_prepared("1.0.1")


@pytest.mark.parametrize("defect", ["seal", "schema", "old_version", "committed_version", "cached"])
def test_reprepare_rejects_uncertain_source(candidate, defect):
    c = candidate
    source = c.load()
    if defect == "seal":
        c.path.write_text("{broken", encoding="utf-8")
    elif defect == "schema":
        source["schema"] = "unknown"
        release_state.save_credential(c.path, source)
    elif defect == "old_version":
        source["baseline"]["oldVersion"] = "0.0.0"
        release_state.save_credential(c.path, source)
    elif defect == "committed_version":
        git(c.root, "add", "VERSION")
        git(c.root, "commit", "-m", "manual version commit")
    else:
        git(c.root, "add", "VERSION")
    original = c.path.read_bytes()
    with pytest.raises(SystemExit):
        release.reprepare_release("1.0.1")
    assert c.path.read_bytes() == original


@pytest.mark.parametrize("untracked", [False, True])
def test_reprepare_rejects_uncommitted_product_before_any_gate(candidate, untracked):
    c = candidate
    target = c.root / ("new_product.py" if untracked else "app.py")
    target.write_text("# repair must be committed first\n", encoding="utf-8")
    original = c.path.read_bytes()
    with pytest.raises(SystemExit):
        release.reprepare_release("1.0.1")
    assert c.path.read_bytes() == original
    assert c.quality.call_count == c.builder.call_count == 1


def test_protected_nonpackaged_untracked_is_not_read_or_rejected(candidate, monkeypatch):
    c = candidate
    protected = []
    for name in ("data/generated-assets/one", "data/image-route-registry.json", "data/skill-store-v1/one"):
        path = c.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic protected bytes")
        protected.append(path)
    original = release_inputs.sha256_file
    def guarded(path):
        assert Path(path) not in protected
        return original(path)
    monkeypatch.setattr(release_inputs, "sha256_file", guarded)
    release.refresh_prepared("1.0.1")
    assert c.quality.call_count == 1


def test_refresh_atomic_replace_failure_keeps_source(candidate, monkeypatch):
    c = candidate
    original = c.path.read_bytes()
    c.env["gh"] = "upgrade"
    replace = release_state.os.replace
    def fail_candidate(src, dest):
        if Path(dest) == c.path:
            raise OSError("synthetic atomic replacement failure")
        return replace(src, dest)
    monkeypatch.setattr(release_state.os, "replace", fail_candidate)
    with pytest.raises(OSError):
        release.refresh_prepared("1.0.1")
    assert c.path.read_bytes() == original


@pytest.mark.parametrize("when", ["quality", "build"])
def test_prepare_rejects_environment_drift_before_sealing(candidate, monkeypatch, when):
    c = candidate
    environment = {"node": "test", "packages": "test"}
    monkeypatch.setattr(release, "build_environment", lambda root: copy.deepcopy(environment))
    if when == "quality":
        c.quality.side_effect = lambda **kwargs: environment.update(node="changed during quality")
    else:
        original = c.builder.side_effect
        def changed(version):
            original(version)
            environment["node"] = "changed during packaging"
        c.builder.side_effect = changed
    with pytest.raises(SystemExit):
        release.reprepare_release("1.0.1")
    assert c.load()["state"] == "reprepare_pending"
    if when == "quality":
        assert c.builder.call_count == 1


def test_actual_node_resolved_esbuild_bytes_are_bound(tmp_path):
    import os
    package = tmp_path / "node_modules/esbuild"
    package.mkdir(parents=True)
    (package / "package.json").write_text('{"main":"index.js"}', encoding="utf-8")
    entry = package / "index.js"
    entry.write_text("exports.version='synthetic';", encoding="utf-8")
    platform = "win32" if os.name == "nt" else "linux"
    binary = tmp_path / f"node_modules/@esbuild/{platform}-x64" / ("esbuild.exe" if os.name == "nt" else "bin/esbuild")
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"synthetic engine 1")
    lock = tmp_path / "package-lock.json"
    lock.write_bytes(b"unchanged lock")
    with mock.patch.dict(os.environ, {"ESBUILD_BINARY_PATH": str(binary)}):
        first = release_inputs.build_environment(tmp_path)
        binary.write_bytes(b"synthetic engine 2, same exported version")
        second = release_inputs.build_environment(tmp_path)
        entry.write_text("exports.version='synthetic'; // wrapper drift", encoding="utf-8")
        third = release_inputs.build_environment(tmp_path)
    assert first["esbuild"]["version"] == second["esbuild"]["version"]
    assert first["esbuild"]["binarySha256"] != second["esbuild"]["binarySha256"]
    assert second["esbuild"]["entrySha256"] != third["esbuild"]["entrySha256"]
    assert lock.read_bytes() == b"unchanged lock"


def test_packager_refuses_missing_or_changed_proof_before_packaging(tmp_path, monkeypatch):
    monkeypatch.setattr(build_exe, "APP_DIR", tmp_path)
    stage = mock.Mock()
    monkeypatch.setattr(build_exe, "prepare_bundled_skills_for_packaging", stage)
    with pytest.raises(FileNotFoundError):
        build_exe.main(["--frontend-proof", str(tmp_path / "missing.json")])
    stage.assert_not_called()


def test_gate_detects_actual_esbuild_drift_before_packaging(candidate, monkeypatch):
    import os
    c = candidate
    package = c.root / "node_modules/esbuild"
    package.mkdir(parents=True)
    (package / "package.json").write_text('{"main":"index.js"}', encoding="utf-8")
    (package / "index.js").write_text("exports.version='same-version';", encoding="utf-8")
    binary = c.root / "synthetic-esbuild-engine"
    binary.write_bytes(b"before")
    git(c.root, "add", "node_modules", "synthetic-esbuild-engine")
    git(c.root, "commit", "-m", "synthetic tool inputs")
    monkeypatch.setenv("ESBUILD_BINARY_PATH", str(binary))
    monkeypatch.setattr(release, "build_environment", release_inputs.build_environment)
    c.quality.side_effect = lambda **kwargs: binary.write_bytes(b"after, same version")
    with pytest.raises(SystemExit):
        release.reprepare_release("1.0.1")
    assert c.load()["state"] == "reprepare_pending"
    assert c.builder.call_count == 1


@pytest.mark.parametrize("action,function", [("refresh-prepared", "refresh_prepared"), ("reprepare", "reprepare_release")])
def test_new_explicit_cli_and_alias_share_one_action(monkeypatch, action, function):
    for args in (["release.py", "1.2.3", "--" + action, "--no-proxy"],
                 ["release.py", action, "1.2.3", "--no-proxy"]):
        monkeypatch.setattr(release.sys, "argv", args)
        with mock.patch.object(release, function) as operation:
            release.main()
        operation.assert_called_once_with("1.2.3")


@pytest.mark.parametrize("state", ["new", "starter", None])
def test_asset_state_must_be_uploaded(candidate, state):
    c = candidate
    credential = c.load()
    asset = {"name": c.artifact.name, "size": c.artifact.stat().st_size,
             "digest": "sha256:" + release_state.sha256_file(c.artifact), "state": state}
    with pytest.raises(SystemExit):
        release._audit_release_asset({"assets": [asset]}, credential)


@pytest.mark.parametrize("field,value", [("isDraft", True), ("isPrerelease", True), ("isDraft", None), ("publishedAt", None)])
def test_remote_status_missing_or_nonfinal_is_rejected(candidate, field, value):
    c = candidate
    info = {"tagName": "v1.0.1", "name": "Code v1.0.1", "body": c.notes.read_text(encoding="utf-8"),
            "targetCommitish": "master", "isDraft": False, "isPrerelease": False, "publishedAt": "2026-09-08T00:00:00Z"}
    info[field] = value
    with pytest.raises(SystemExit):
        release._audit_release_metadata(info, c.load())


@pytest.mark.parametrize("helper,args", [(release.git_commit_and_tag, ("1.0.1",)),
                                        (release.push_to_github, ("1.0.1",)),
                                        (release.create_github_release, ("1.0.1", "sha"))])
def test_old_helpers_are_never_mutating(helper, args):
    with mock.patch.object(release, "run") as command, mock.patch.object(release, "run_quiet") as quiet:
        helper(*args, dry_run=True)
        with pytest.raises(SystemExit):
            helper(*args)
    command.assert_not_called()
    quiet.assert_not_called()


def frontend_fixture(root):
    (root / "dist/frontend").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src/input.js").write_text("synthetic", encoding="utf-8")
    (root / "dist/frontend/code.bundle.js").write_text("synthetic", encoding="utf-8")
    state = {"inputs": ["src/input.js"], "outputs": {"code.bundle.js": {}}}
    (root / "dist/frontend/code.bundle.state.json").write_text(json.dumps(state), encoding="utf-8")


@pytest.mark.parametrize("change", [None, "src/input.js", "dist/frontend/code.bundle.js", "toolchain", "during_check"])
def test_frontend_proof_exact_binding(tmp_path, monkeypatch, change):
    frontend_fixture(tmp_path)
    monkeypatch.setattr(release_inputs, "build_environment", lambda root: {"node": "old"})
    proof = release_inputs.frontend_proof(tmp_path)
    if change == "toolchain":
        monkeypatch.setattr(release_inputs, "build_environment", lambda root: {"node": "new"})
    elif change and change != "during_check":
        (tmp_path / change).write_text("tampered", encoding="utf-8")
    def check(*args, **kwargs):
        if change == "during_check":
            (tmp_path / "src/input.js").write_text("changed during validation", encoding="utf-8")
    with mock.patch.object(release_inputs.subprocess, "run", side_effect=check) as run:
        if change:
            with pytest.raises(release_state.CredentialError):
                release_inputs.verify_frontend(tmp_path, proof)
        else:
            release_inputs.verify_frontend(tmp_path, proof)
            assert run.call_count == 2


@pytest.mark.parametrize("reuse", [False, True])
def test_packaging_entry_isolated_and_standalone_self_sufficient(tmp_path, monkeypatch, reuse):
    monkeypatch.setattr(build_exe, "APP_DIR", tmp_path)
    (tmp_path / "VERSION").write_text("9.8.7\n", encoding="utf-8")
    build = mock.Mock()
    verify = mock.Mock()
    monkeypatch.setattr(build_exe, "build_frontend_assets", build)
    monkeypatch.setattr(build_exe, "verify_frontend", verify)
    monkeypatch.setattr(build_exe, "prepare_bundled_skills_for_packaging", lambda: tmp_path / "synthetic-skills")
    for name in ("FRONTEND_BUNDLE", "FRONTEND_CLASSIC_FALLBACK"):
        monkeypatch.setattr(build_exe, name, tmp_path / name)
    proof = tmp_path / "proof.json"
    proof.write_text('{}', encoding="utf-8")
    with mock.patch.object(build_exe.subprocess, "run") as run:
        build_exe.main(["--frontend-proof", str(proof)] if reuse else [])
    assert build.call_count == (0 if reuse else 1)
    assert verify.call_count == (2 if reuse else 0)
    args = run.call_args.args[0]
    assert "PyInstaller" in args and args[args.index("--name") + 1] == "Code-v9.8.7"
    assert str(tmp_path / "data/memory") + ";data/memory" in args
    assert not (tmp_path / "dist/Code-v9.8.7.exe").exists()
