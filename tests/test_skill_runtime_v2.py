"""Immutable Skill runtime/v2 pure and store-backed contracts."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
from unittest import mock

import pytest

from code_runtime import skill_admission
from code_runtime import skill_completion
from code_runtime import skill_lifecycle_v2
from code_runtime import skill_outcome
from code_runtime import skill_revisions
from code_runtime import skill_runtime_v2
from code_runtime import skill_store
from tests import test_skill_admission as admission_fixture


def _request(name=""):
    return {"schemaVersion": 1, "explicitSkill": name, "disabledNames": []}


def _prepare(reader, message, *, explicit="", tools=None):
    return skill_admission.prepare_immutable_admission(
        reader=reader,
        messages=[{"role": "system", "content": "pure"}],
        user_message=message,
        request=_request(explicit),
        initial_tool_names=tools or ["read_file", "write_file", "run_command"],
        available_input_tokens=100_000,
        estimate_tokens=lambda value: max(1, len(value) // 4),
    )


def test_runtime_v2_module_has_no_mutable_or_bundled_discovery_path():
    source = Path(skill_runtime_v2.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "SKILLS_DIR", "resolve_skill_manifest(",
        "resolve_skill_resources", "read_skill(", "bundled_skills_dir",
    ):
        assert forbidden not in source


@pytest.mark.parametrize("count", [1, 64, 256])
def test_admission_snapshot_has_linear_real_read_counts(tmp_path, count):
    data, bundle = tmp_path / "data", tmp_path / "bundle"
    installed = data / "skills"
    installed.mkdir(parents=True)
    bundle.mkdir()
    identities = {}
    for index in range(count):
        name = f"skill-{index:03d}"
        text = f"---\nname: {name}\ndescription: linear fixture\n---\nbody {index}\n"
        (bundle / name).mkdir()
        (bundle / name / "SKILL.md").write_text(text, encoding="utf-8", newline="\n")
        shutil.copytree(bundle / name, installed / name)
        identities[name] = f"code.bundle/{name}"
    catalog = skill_revisions.build_bundled_catalog(bundle, identities)
    skill_store.SkillStore(data, bundle, write_enabled=True).bootstrap(catalog)
    reader = skill_store.SkillStoreReader(data)
    with mock.patch.object(reader, "read_registry", wraps=reader.read_registry) as registries, mock.patch.object(
        reader, "_read_pinned_from_root", wraps=reader._read_pinned_from_root,
    ) as objects, mock.patch.object(
        reader._store, "_verify_object", wraps=reader._store._verify_object,
    ) as verifications:
        result = _prepare(reader, f"skill-{count - 1:03d}", explicit=f"skill-{count - 1:03d}")
    assert result["activeSkillNames"] == [f"skill-{count - 1:03d}"]
    assert registries.call_count == 2
    assert objects.call_count == count + 2
    assert verifications.call_count <= 2 * count + 4


def test_no_match_still_requires_exact_root_for_nonterminal_runtime(tmp_path):
    data, _bundle, _registry = admission_fixture._fixture(tmp_path / "one")
    reader = skill_store.SkillStoreReader(data)
    lifecycle = skill_lifecycle_v2.build_skill_lifecycle(
        _prepare(reader, "hello world")
    )
    assert lifecycle["activation"]["selected"] == []
    assert skill_runtime_v2.verify_lifecycle(reader, lifecycle) == lifecycle
    with pytest.raises(skill_runtime_v2.ImmutableSkillRuntimeError) as missing:
        skill_runtime_v2.verify_lifecycle(None, lifecycle)
    assert missing.value.code == "skill_revision_unavailable"
    assert missing.value.temporary is True

    other_data, _other_bundle, _ = admission_fixture._fixture(tmp_path / "two")
    with pytest.raises(skill_runtime_v2.ImmutableSkillRuntimeError) as wrong_root:
        skill_runtime_v2.verify_lifecycle(
            skill_store.SkillStoreReader(other_data), lifecycle,
        )
    assert wrong_root.value.code == "skill_revision_unavailable"


def test_routing_snapshot_verifies_object_without_retaining_nonrouting_bodies(tmp_path):
    data, _bundle, _registry = admission_fixture._fixture(tmp_path)
    snapshot = skill_store.SkillStoreReader(data).begin_admission()
    selection = snapshot.read_active("xlsx")
    retained = {item["path"] for item in selection["object"]["files"]}
    manifested = {item["path"] for item in selection["object"]["manifest"]["files"]}
    assert "scripts/run.py" in manifested
    assert "private.txt" in manifested
    assert "scripts/run.py" not in retained
    assert "private.txt" not in retained
    assert "SKILL.md" in retained
    snapshot.finish()


def test_pinned_sidecars_match_frozen_normalized_contracts(tmp_path):
    data, _bundle, _registry = admission_fixture._fixture(tmp_path)
    reader = skill_store.SkillStoreReader(data)
    lifecycle = skill_lifecycle_v2.build_skill_lifecycle(
        _prepare(reader, "xlsx", explicit="xlsx")
    )
    assert skill_runtime_v2.verify_lifecycle(reader, lifecycle) == lifecycle

    evidence_changed = copy.deepcopy(lifecycle)
    evidence_changed["activation"]["selected"][0]["evidence"]["contract"]["requirements"][0]["minCount"] = 2
    with pytest.raises(skill_runtime_v2.ImmutableSkillRuntimeError) as evidence_error:
        skill_runtime_v2.verify_lifecycle(reader, evidence_changed)
    assert evidence_error.value.code == "skill_revision_contract_conflict"

    dependency_changed = copy.deepcopy(lifecycle)
    dependency = dependency_changed["activation"]["selected"][0]["dependency"]
    dependency["manifest"]["capabilities"][0]["id"] = "create2"
    dependency["capabilities"] = ["create2"]
    with pytest.raises(skill_runtime_v2.ImmutableSkillRuntimeError) as dependency_error:
        skill_runtime_v2.verify_lifecycle(reader, dependency_changed)
    assert dependency_error.value.code == "skill_revision_contract_conflict"

    resource_changed = copy.deepcopy(lifecycle)
    resource_changed["activation"]["selected"][0]["resources"]["contract"]["resources"][0]["arguments"] = ["<changed.xlsx>"]
    with pytest.raises(skill_runtime_v2.ImmutableSkillRuntimeError) as resource_error:
        skill_runtime_v2.verify_lifecycle(reader, resource_changed)
    assert resource_error.value.code == "skill_revision_contract_conflict"

    downgraded = skill_lifecycle_v2.build_skill_lifecycle(
        _prepare(reader, "xlsx", explicit="xlsx", tools=["read_file"])
    )
    assert downgraded["activation"]["selected"][0]["evidence"]["state"] == "invalid"
    assert skill_runtime_v2.verify_lifecycle(reader, downgraded) == downgraded

    selected = lifecycle["activation"]["selected"][0]
    bad_access = skill_lifecycle_v2.bind_text_resource(
        lifecycle, selected["installationId"], selected["revisionId"],
        "private.txt", "sha256:" + "0" * 64,
    )
    with pytest.raises(skill_runtime_v2.ImmutableSkillRuntimeError) as access_error:
        skill_runtime_v2.verify_lifecycle(reader, bad_access)
    assert access_error.value.code == "skill_revision_contract_conflict"


def test_runtime_resource_paths_reproject_after_same_root_move(tmp_path):
    data, _bundle, _registry = admission_fixture._fixture(tmp_path / "source")
    reader = skill_store.SkillStoreReader(data)
    lifecycle = skill_lifecycle_v2.build_skill_lifecycle(
        _prepare(reader, "xlsx", explicit="xlsx")
    )
    before = skill_runtime_v2.runtime_resources(reader, lifecycle, "xlsx")
    moved = tmp_path / "moved"
    moved.mkdir()
    shutil.copytree(
        data / skill_store.STORE_DIRECTORY,
        moved / skill_store.STORE_DIRECTORY,
    )
    after = skill_runtime_v2.runtime_resources(
        skill_store.SkillStoreReader(moved), lifecycle, "xlsx",
    )
    assert before["resources"][0]["path"] != after["resources"][0]["path"]
    assert str(data) in before["resources"][0]["path"]
    assert str(moved) in after["resources"][0]["path"]


def test_exact_execution_context_drives_receipt_v2_and_completion_v2(tmp_path):
    data, _bundle, _registry = admission_fixture._fixture(tmp_path)
    reader = skill_store.SkillStoreReader(data)
    lifecycle = skill_lifecycle_v2.build_skill_lifecycle(
        _prepare(reader, "xlsx", explicit="xlsx")
    )
    context = skill_runtime_v2.build_execution_context(
        reader, lifecycle, "write_file", {"path": "book.xlsx"}, bindings={},
    )
    execution = {
        "name": "write_file",
        "arguments": json.dumps({"path": "book.xlsx"}),
        "fingerprint": "a" * 64,
        "status": "completed",
        "outcome": "succeeded",
        "result": {"ok": True, "action": "write_file", "path": "book.xlsx"},
        "skillExecutionContext": context,
    }
    outcome = skill_outcome.project_immutable_skill_outcome(
        lifecycle, {"call-1": execution}, "run-1", "completed",
    )
    receipt = outcome["skills"][0]["requirements"][0]["actual"][0]
    assert outcome["version"] == 3
    assert receipt["version"] == 2
    assert receipt["authority"] == outcome["skills"][0]["authority"]
    assert receipt["callId"] == "call-1"

    tampered = copy.deepcopy(execution)
    tampered["skillExecutionContext"]["skills"][0]["revisionId"] = "sha256:" + "f" * 64
    rejected = skill_outcome.project_immutable_skill_outcome(
        lifecycle, {"call-1": tampered}, "run-1", "completed",
    )
    assert rejected["skills"][0]["requirements"][0]["gap"] is True
    assert rejected["skills"][0]["requirements"][0]["acceptedSucceeded"] == 0

    completion_lifecycle = copy.deepcopy(lifecycle)
    evidence = completion_lifecycle["activation"]["selected"][0]["evidence"]
    evidence["contract"] = {
        "schemaVersion": 2,
        "requirements": evidence["contract"]["requirements"],
        "enforcement": {
            "schemaVersion": 2,
            "mode": "owner_completion_once",
            "activationKinds": ["explicit"],
        },
    }
    completion_lifecycle = skill_lifecycle_v2.normalize_skill_lifecycle(completion_lifecycle)
    plan = skill_completion.build_plan(
        completion_lifecycle,
        {"write_file": {"effect": "file_mutation", "idempotent": False}},
        [], enabled=True,
    )
    completion_outcome = skill_outcome.project_immutable_skill_outcome(
        completion_lifecycle, {"call-1": execution}, "run-1", "completed",
    )
    assert plan["version"] == 2
    assert skill_completion.evaluate(
        plan, completion_outcome,
        {"write_file": {"effect": "file_mutation", "idempotent": False}},
    )["status"] == "satisfied"
    missing_outcome = skill_outcome.project_immutable_skill_outcome(
        completion_lifecycle, {}, "run-1", "active",
    )
    evaluation = skill_completion.evaluate(
        plan, missing_outcome,
        {"write_file": {"effect": "file_mutation", "idempotent": False}},
    )
    assert evaluation["status"] == "recoverable"
    continuing = skill_completion.begin_continuation(
        plan, evaluation, "run-1", 1, "candidate",
    )
    assert continuing["version"] == 2
    assert skill_completion.validate_repair_batch(
        continuing,
        [{
            "id": "repair-1", "fingerprint": "c" * 64,
            "function": {"name": "write_file"},
            "arguments": {"path": "book.xlsx", "content": "x"},
            "parseError": "", "validationErrors": [],
        }],
        {"write_file": {"effect": "file_mutation", "idempotent": False}},
        {},
    ) == ["repair-1"]

    command_lifecycle = copy.deepcopy(lifecycle)
    command_evidence = command_lifecycle["activation"]["selected"][0]["evidence"]
    command_evidence["contract"]["requirements"] = [{
        "id": "command", "type": "tool_execution",
        "tool": "run_command", "minCount": 1,
    }]
    command_lifecycle = skill_lifecycle_v2.normalize_skill_lifecycle(command_lifecycle)
    selected = command_lifecycle["activation"]["selected"][0]
    authority = skill_runtime_v2.authority_from_selected(selected)
    command_context = skill_runtime_v2.normalize_execution_context({
        "version": 1,
        "dataRootId": command_lifecycle["activation"]["registry"]["dataRootId"],
        "skills": [{
            **authority,
            "capability": "create",
            "manifestHash": selected["dependency"]["manifestHash"],
        }],
    }, command_lifecycle)
    command_outcome = skill_outcome.project_immutable_skill_outcome(
        command_lifecycle,
        {"command-1": {
            "name": "run_command", "arguments": json.dumps({"command": "python --version"}),
            "fingerprint": "d" * 64, "status": "completed", "outcome": "succeeded",
            "result": {"ok": True, "action": "run_command", "exitCode": 0},
            "skillExecutionContext": command_context,
        }},
        "run-2", "completed",
    )
    command_receipt = command_outcome["skills"][0]["requirements"][0]["actual"][0]
    assert command_receipt["source"] == "runtime_exact_single"
