import json
import os
from pathlib import Path
import shutil

import pytest

from code_runtime import skill_revisions as revisions


ROOT = Path(__file__).resolve().parents[1]


def _write_skill(root, directory, *, body="body", extra=None, newline="\n"):
    skill = root / directory
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_bytes(
        newline.join(("---", f"name: {directory}", "description: test", "---", "", body)).encode()
    )
    for relative, payload in (extra or {}).items():
        path = skill / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload if isinstance(payload, bytes) else payload.encode())
    return skill


def _snapshot(root):
    if not Path(root).exists():
        return None
    return {
        path.relative_to(root).as_posix(): (
            "dir" if path.is_dir() else path.read_bytes()
        )
        for path in sorted(Path(root).rglob("*"), key=lambda item: item.as_posix())
        if not path.is_symlink()
    }


def _catalog_for(root, assignments):
    return revisions.build_bundled_catalog(root, assignments)


def test_revision_is_order_root_and_line_ending_independent(tmp_path):
    first = _write_skill(
        tmp_path / "one", "alpha", newline="\r\n",
        extra={"z.txt": "z\r\n", "nested/a.txt": "a\r\n"},
    )
    second = _write_skill(
        tmp_path / "two", "renamed", newline="\n",
        extra={"nested/a.txt": "a\n", "z.txt": "z\n"},
    )
    (second / "SKILL.md").write_bytes((first / "SKILL.md").read_bytes().replace(b"\r\n", b"\n"))

    left = revisions.build_skill_revision(first)
    right = revisions.build_skill_revision(second)

    assert left == right
    assert left["schema"] == revisions.REVISION_SCHEMA
    assert left["revisionId"].startswith("sha256:")
    assert [item["path"] for item in left["files"]] == [
        "SKILL.md", "nested/a.txt", "z.txt",
    ]
    assert all(item["contentMode"] == "utf8-lf" for item in left["files"])


@pytest.mark.parametrize(
    "relative",
    ["SKILL.md", "dependencies.json", "evidence.json", "code-resources.json", "scripts/run.py"],
)
def test_every_package_component_changes_revision(tmp_path, relative):
    extra = {
        "dependencies.json": "{}\n",
        "evidence.json": "{}\n",
        "code-resources.json": "{}\n",
        "scripts/run.py": "print('one')\n",
    }
    skill = _write_skill(tmp_path, "alpha", extra=extra)
    before = revisions.build_skill_revision(skill)["revisionId"]
    target = skill / relative
    target.write_bytes(target.read_bytes() + b"changed\n")
    assert revisions.build_skill_revision(skill)["revisionId"] != before


def test_binary_bytes_are_not_line_normalized(tmp_path):
    skill = _write_skill(tmp_path, "alpha", extra={"asset.bin": b"\x00a\r\nb"})
    manifest = revisions.build_skill_revision(skill)
    binary = next(item for item in manifest["files"] if item["path"] == "asset.bin")
    assert binary["contentMode"] == "binary"
    assert binary["size"] == 5


@pytest.mark.parametrize("path", ["../escape", "/absolute", "a/../b", "a:/b", "trail. "])
def test_manifest_unsafe_paths_fail_closed(path):
    payload = {
        "schema": revisions.REVISION_SCHEMA,
        "files": [{
            "path": path,
            "size": 1,
            "digest": "sha256:" + "0" * 64,
            "contentMode": "binary",
        }],
    }
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.normalize_revision_manifest(payload)
    assert caught.value.code == "revision_path_invalid"


def test_manifest_case_and_unicode_aliases_fail_closed():
    files = [
        {"path": name, "size": 1, "digest": "sha256:" + digit * 64, "contentMode": "binary"}
        for name, digit in (("A.txt", "0"), ("a.TXT", "1"))
    ]
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.normalize_revision_manifest({"schema": revisions.REVISION_SCHEMA, "files": files})
    assert caught.value.code == "revision_path_collision"


def test_revision_manifest_rejects_wrong_identity_and_missing_skill_document(tmp_path):
    skill = _write_skill(tmp_path, "alpha")
    manifest = revisions.build_skill_revision(skill)
    manifest["revisionId"] = "sha256:" + "0" * 64
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.normalize_revision_manifest(manifest)
    assert caught.value.code == "revision_id_mismatch"

    (skill / "SKILL.md").unlink()
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.build_skill_revision(skill)
    assert caught.value.code == "revision_skill_document_missing"


def test_symlink_or_reparse_and_special_files_fail_closed(tmp_path, monkeypatch):
    skill = _write_skill(tmp_path, "alpha", extra={"target.txt": "target", "unsafe": "x"})
    link = skill / "link.txt"
    try:
        os.symlink(skill / "target.txt", link)
        with pytest.raises(revisions.SkillRevisionError) as caught:
            revisions.build_skill_revision(skill)
        assert caught.value.code == "revision_path_unsafe"
        link.unlink()
    except (OSError, NotImplementedError):
        original = revisions._path_kind
        monkeypatch.setattr(
            revisions, "_path_kind",
            lambda path: "unsafe" if Path(path).name == "unsafe" else original(path),
        )
        with pytest.raises(revisions.SkillRevisionError) as caught:
            revisions.build_skill_revision(skill)
        assert caught.value.code == "revision_path_unsafe"
        monkeypatch.setattr(revisions, "_path_kind", original)

    original = revisions._path_kind
    monkeypatch.setattr(
        revisions, "_path_kind",
        lambda path: "special" if Path(path).name == "unsafe" else original(path),
    )
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.build_skill_revision(skill)
    assert caught.value.code == "revision_path_special"


def test_unreadable_and_change_during_read_fail_closed(tmp_path, monkeypatch):
    skill = _write_skill(tmp_path, "alpha")
    original = revisions._read_file_bytes

    def denied(path):
        if Path(path).name == "SKILL.md":
            raise PermissionError("denied")
        return original(path)

    monkeypatch.setattr(revisions, "_read_file_bytes", denied)
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.build_skill_revision(skill)
    assert caught.value.code == "revision_file_unreadable"

    calls = 0

    def changing(path):
        nonlocal calls
        calls += 1
        payload = original(path)
        if calls == 1:
            Path(path).write_bytes(payload + b"x")
        return payload

    monkeypatch.setattr(revisions, "_read_file_bytes", changing)
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.build_skill_revision(skill)
    assert caught.value.code == "revision_changed_during_read"


def test_count_file_total_and_depth_bounds(tmp_path, monkeypatch):
    skill = _write_skill(tmp_path, "alpha", extra={"a": "12", "b": "34"})
    monkeypatch.setattr(revisions, "MAX_FILES", 2)
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.build_skill_revision(skill)
    assert caught.value.code == "revision_file_count_exceeded"

    monkeypatch.setattr(revisions, "MAX_FILES", 10)
    monkeypatch.setattr(revisions, "MAX_FILE_BYTES", 1)
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.build_skill_revision(skill)
    assert caught.value.code == "revision_file_size_exceeded"

    monkeypatch.setattr(revisions, "MAX_FILE_BYTES", 1024)
    monkeypatch.setattr(revisions, "MAX_TOTAL_BYTES", 3)
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.build_skill_revision(skill)
    assert caught.value.code == "revision_total_size_exceeded"

    monkeypatch.setattr(revisions, "MAX_TOTAL_BYTES", 4096)
    monkeypatch.setattr(revisions, "MAX_DEPTH", 1)
    nested = skill / "nested"
    nested.mkdir()
    (nested / "deep.txt").write_text("x")
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.build_skill_revision(skill)
    assert caught.value.code == "revision_depth_exceeded"


def test_transient_python_cache_is_not_part_of_packaged_revision(tmp_path):
    skill = _write_skill(tmp_path, "alpha")
    before = revisions.build_skill_revision(skill)
    cache = skill / "scripts" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "helper.cpython-312.pyc").write_bytes(b"cache")
    assert revisions.build_skill_revision(skill) == before


def test_catalog_is_canonical_unique_and_requires_explicit_assignments(tmp_path):
    _write_skill(tmp_path, "beta")
    _write_skill(tmp_path, "alpha")
    assignments = {
        "alpha": "code.bundle/alpha-stable",
        "beta": "code.bundle/beta-stable",
    }
    catalog = _catalog_for(tmp_path, assignments)
    assert catalog["schema"] == revisions.CATALOG_SCHEMA
    assert [item["directory"] for item in catalog["skills"]] == ["alpha", "beta"]
    assert revisions.normalize_bundled_catalog(catalog) == catalog
    assert revisions.render_bundled_catalog(catalog) == revisions.render_bundled_catalog(catalog)

    _write_skill(tmp_path, "new-skill")
    with pytest.raises(revisions.SkillRevisionError) as caught:
        _catalog_for(tmp_path, assignments)
    assert caught.value.code == "catalog_assignment_required"


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda value: value["skills"].append(dict(value["skills"][0])), "catalog_directory_duplicate"),
        (lambda value: value["skills"][1].update(skillId=value["skills"][0]["skillId"]), "catalog_skill_id_duplicate"),
        (lambda value: value["skills"][0].update(skillId="alpha"), "catalog_skill_id_invalid"),
        (lambda value: value.update(extra=True), "catalog_invalid"),
    ],
)
def test_malformed_catalog_fails_closed(tmp_path, mutation, code):
    _write_skill(tmp_path, "alpha")
    _write_skill(tmp_path, "beta")
    catalog = _catalog_for(tmp_path, {
        "alpha": "code.bundle/alpha", "beta": "code.bundle/beta",
    })
    mutation(catalog)
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.normalize_bundled_catalog(catalog)
    assert caught.value.code == code


def test_catalog_freshness_detects_tree_and_sidecar_drift(tmp_path):
    alpha = _write_skill(tmp_path, "alpha", extra={"dependencies.json": "{}\n"})
    catalog = _catalog_for(tmp_path, {"alpha": "code.bundle/alpha"})
    assert revisions.validate_bundled_catalog(tmp_path, catalog)["skillCount"] == 1

    (alpha / "dependencies.json").write_text('{"changed":true}\n')
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.validate_bundled_catalog(tmp_path, catalog)
    assert caught.value.code == "catalog_stale"

    shutil.rmtree(alpha)
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.validate_bundled_catalog(tmp_path, catalog)
    assert caught.value.code == "catalog_coverage_changed"

    _write_skill(tmp_path, "renamed")
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.validate_bundled_catalog(tmp_path, catalog)
    assert caught.value.code == "catalog_coverage_changed"


def test_catalog_rename_requires_an_explicit_stable_id_mapping(tmp_path):
    original = _write_skill(tmp_path, "alpha")
    first = _catalog_for(tmp_path, {"alpha": "code.bundle/stable-alpha"})
    original.rename(tmp_path / "renamed")
    second = _catalog_for(tmp_path, {"renamed": "code.bundle/stable-alpha"})
    assert second["skills"][0]["skillId"] == first["skills"][0]["skillId"]
    assert second["skills"][0]["revisionId"] == first["skills"][0]["revisionId"]


def test_catalog_round_trip_load_and_current_repo_freshness(tmp_path):
    _write_skill(tmp_path, "alpha")
    catalog = _catalog_for(tmp_path, {"alpha": "code.bundle/alpha"})
    path = tmp_path / revisions.CATALOG_FILENAME
    path.write_text(revisions.render_bundled_catalog(catalog), encoding="utf-8")
    assert revisions.load_bundled_catalog(path) == catalog

    current_path = ROOT / "data" / "skills" / revisions.CATALOG_FILENAME
    current = revisions.load_bundled_catalog(current_path)
    checked = revisions.validate_bundled_catalog(ROOT / "data" / "skills", current)
    assert checked == {"ok": True, "skillCount": len(current["skills"]), "catalogHash": checked["catalogHash"]}


def test_planner_classifies_exact_modified_local_and_tombstone_without_writes(tmp_path):
    bundled = tmp_path / "bundle"
    installed = tmp_path / "profile" / "skills"
    alpha = _write_skill(bundled, "alpha")
    _write_skill(bundled, "beta")
    _write_skill(bundled, "gamma")
    catalog = _catalog_for(bundled, {
        "alpha": "code.bundle/alpha",
        "beta": "code.bundle/beta",
        "gamma": "code.bundle/gamma",
    })
    installed.mkdir(parents=True)
    shutil.copytree(alpha, installed / "alpha")
    _write_skill(installed, "beta", body="locally modified")
    _write_skill(installed, "local", body="custom")
    (installed.parent / "bundled-skills-state.json").write_text(json.dumps({
        "schema": "code-bundled-skills/v1", "tombstones": ["gamma"],
    }))
    before = _snapshot(tmp_path)

    plan = revisions.plan_legacy_migration(installed, bundled, catalog)

    assert _snapshot(tmp_path) == before
    by_dir = {item["directory"]: item for item in plan["entries"]}
    assert by_dir["alpha"]["classification"] == "exact-bundled"
    assert by_dir["beta"]["classification"] == "same-name-modified"
    assert by_dir["local"]["classification"] == "local-custom"
    assert by_dir["gamma"]["classification"] == "tombstoned-bundled"
    assert by_dir["gamma"]["bundledState"] == "tombstoned"
    rendered = json.dumps(plan, sort_keys=True)
    assert str(tmp_path) not in rendered
    assert "command" not in rendered and "body" not in rendered


def test_same_name_custom_is_distinct_from_bundled_tombstone(tmp_path):
    bundled = tmp_path / "bundle"
    installed = tmp_path / "profile" / "skills"
    _write_skill(bundled, "alpha", body="bundled")
    _write_skill(installed, "alpha", body="custom")
    catalog = _catalog_for(bundled, {"alpha": "code.bundle/alpha"})
    (installed.parent / "bundled-skills-state.json").write_text(json.dumps({
        "schema": "code-bundled-skills/v1", "tombstones": ["alpha"],
    }))
    item = revisions.plan_legacy_migration(installed, bundled, catalog)["entries"][0]
    assert item["classification"] == "same-name-modified"
    assert item["bundledState"] == "tombstoned"
    assert item["installed"]["revisionId"] != item["bundledRevisionId"]


def test_invalid_legacy_state_fails_closed_and_missing_root_is_reported(tmp_path):
    bundled = tmp_path / "bundle"
    installed = tmp_path / "profile" / "skills"
    _write_skill(bundled, "alpha")
    catalog = _catalog_for(bundled, {"alpha": "code.bundle/alpha"})
    installed.mkdir(parents=True)
    state = installed.parent / "bundled-skills-state.json"
    state.write_text("{broken")
    before = _snapshot(tmp_path)
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.plan_legacy_migration(installed, bundled, catalog)
    assert caught.value.code == "legacy_state_invalid"
    assert _snapshot(tmp_path) == before

    state.unlink()
    installed.rmdir()
    plan = revisions.plan_legacy_migration(installed, bundled, catalog)
    assert plan["installedRootState"] == "missing"
    assert plan["entries"][0]["classification"] == "bundled-missing"


def test_planner_preserves_unmatched_tombstones_and_reports_unreadable_root(tmp_path, monkeypatch):
    bundled = tmp_path / "bundle"
    installed = tmp_path / "profile" / "skills"
    _write_skill(bundled, "alpha")
    installed.mkdir(parents=True)
    catalog = _catalog_for(bundled, {"alpha": "code.bundle/alpha"})
    (installed.parent / "bundled-skills-state.json").write_text(json.dumps({
        "schema": "code-bundled-skills/v1", "tombstones": ["removed-legacy"],
    }))
    plan = revisions.plan_legacy_migration(installed, bundled, catalog)
    assert plan["unmatchedTombstones"] == ["removed-legacy"]

    monkeypatch.setattr(revisions, "_installed_observations", lambda _root: ("unreadable", {}))
    unreadable = revisions.plan_legacy_migration(installed, bundled, catalog)
    assert unreadable["installedRootState"] == "unreadable"
    assert unreadable["entries"][0]["classification"] == "invalid"


def test_planner_rejects_a_changing_installed_snapshot(tmp_path, monkeypatch):
    bundled = tmp_path / "bundle"
    installed = tmp_path / "profile" / "skills"
    _write_skill(bundled, "alpha")
    _write_skill(installed, "alpha")
    catalog = _catalog_for(bundled, {"alpha": "code.bundle/alpha"})
    stable = revisions._installed_observations(installed)
    calls = 0

    def changing(_root):
        nonlocal calls
        calls += 1
        return stable if calls == 1 else ("ready", {})

    monkeypatch.setattr(revisions, "_installed_observations", changing)
    with pytest.raises(revisions.SkillRevisionError) as caught:
        revisions.plan_legacy_migration(installed, bundled, catalog)
    assert caught.value.code == "migration_source_changed"


def test_shared_and_relocated_roots_are_deterministic(tmp_path):
    bundled = tmp_path / "bundle"
    _write_skill(bundled, "alpha")
    catalog = _catalog_for(bundled, {"alpha": "code.bundle/alpha"})
    shared = revisions.plan_legacy_migration(bundled, bundled, catalog)
    assert shared["rootMode"] == "shared-development"
    assert shared["entries"][0]["classification"] == "shared-development"

    first = tmp_path / "one" / "skills"
    second = tmp_path / "two" / "skills"
    shutil.copytree(bundled, first)
    shutil.copytree(bundled, second)
    left = revisions.plan_legacy_migration(first, bundled, catalog)
    right = revisions.plan_legacy_migration(second, bundled, catalog)
    assert left == right


def test_unsafe_installed_root_is_reported_without_traversal(tmp_path):
    bundled = tmp_path / "bundle"
    _write_skill(bundled, "alpha")
    catalog = _catalog_for(bundled, {"alpha": "code.bundle/alpha"})
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "skills-link"
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        link = target
        original = revisions._path_kind
        revisions._path_kind = lambda path: (
            "unsafe" if Path(path) == link else original(path)
        )
    try:
        plan = revisions.plan_legacy_migration(link, bundled, catalog)
        assert plan["installedRootState"] == "unsafe"
        assert plan["entries"][0]["classification"] == "invalid"
    finally:
        if link == target:
            revisions._path_kind = original


def test_invalid_installed_directory_name_is_reported_opaquely(tmp_path):
    bundled = tmp_path / "bundle"
    installed = tmp_path / "profile" / "skills"
    _write_skill(bundled, "alpha")
    invalid = installed / "bad name"
    invalid.mkdir(parents=True)
    (invalid / "SKILL.md").write_text("secret body")
    catalog = _catalog_for(bundled, {"alpha": "code.bundle/alpha"})
    plan = revisions.plan_legacy_migration(installed, bundled, catalog)
    invalid_entry = next(item for item in plan["entries"] if item["classification"] == "invalid")
    assert invalid_entry["directory"].startswith("~invalid-")
    assert "bad name" not in json.dumps(plan)
    assert invalid_entry["installed"]["errorCode"] == "revision_path_invalid"
