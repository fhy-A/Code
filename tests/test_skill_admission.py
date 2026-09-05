import copy
import hashlib
import json
import shutil

import pytest

from code_runtime import skill_admission
from code_runtime import skill_lifecycle
from code_runtime import skill_lifecycle_v2
from code_runtime import skill_registry
from code_runtime import skill_revisions
from code_runtime import skill_store

lifecycle = skill_lifecycle_v2


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _write_skill(root, name, *, body="instructions", allowed="", keywords="", extra=None):
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    frontmatter = ["---", f"name: {name}", "description: immutable test"]
    if allowed:
        frontmatter.append(f"allowed-tools: {allowed}")
    if keywords:
        frontmatter.append(f"keywords: {keywords}")
    (directory / "SKILL.md").write_text("\n".join([*frontmatter, "---", "", body]), encoding="utf-8", newline="\n")
    for relative, payload in (extra or {}).items():
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload if isinstance(payload, bytes) else payload.encode())
    return directory


def _fixture(tmp_path):
    data, bundle = tmp_path / "profile", tmp_path / "bundle"
    data.mkdir(parents=True); bundle.mkdir(parents=True)
    script = b"print('ok')\n"
    dependency = {
        "schemaVersion": 1,
        "skill": "xlsx",
        "capabilities": {
            "create": {
                "required": [{
                    "type": "command",
                    "name": "python",
                    "installHint": "do not persist this presentation hint",
                }],
                "optional": [],
            },
        },
    }
    evidence = {
        "schemaVersion": 1,
        "requirements": [{
            "id": "write",
            "type": "artifact",
            "tool": "write_file",
            "minCount": 1,
            "artifactKind": "file",
        }],
        "enforcement": {"schemaVersion": 1, "mode": "explicit_only"},
    }
    resources = {
        "schemaVersion": 1,
        "skill": "xlsx",
        "resources": [{
            "id": "runner",
            "path": "scripts/run.py",
            "sha256": hashlib.sha256(script).hexdigest(),
            "kind": "python",
            "protocol": "code-test/v1",
            "modelVisible": True,
            "arguments": ["<workbook.xlsx>"],
        }],
    }
    _write_skill(bundle, "xlsx", body="create workbook", allowed="read_file, write_file", extra={
        "dependencies.json": _json(dependency),
        "evidence.json": _json(evidence),
        "code-resources.json": _json(resources),
        "scripts/run.py": script,
        "private.txt": "C:\\private\\token=secret-value",
    })
    _write_skill(bundle, "document-design", body="polish layout", allowed="read_file, write_file")
    (data / "skills").mkdir()
    shutil.copytree(bundle / "xlsx", data / "skills" / "xlsx")
    shutil.copytree(bundle / "document-design", data / "skills" / "document-design")
    catalog = skill_revisions.build_bundled_catalog(bundle, {
        "document-design": "code.bundle/document-design",
        "xlsx": "code.bundle/xlsx",
    })
    registry = skill_store.SkillStore(data, bundle, write_enabled=True).bootstrap(catalog)
    return data, bundle, registry


def _request(explicit="", disabled=None):
    return {"schemaVersion": 1, "explicitSkill": explicit, "disabledNames": disabled or []}


def _prepare(data, message, *, explicit="", disabled=None, reader=None):
    return skill_admission.prepare_immutable_admission(
        reader=reader or skill_store.SkillStoreReader(data),
        messages=[{"role": "system", "content": "unused pure input"}],
        user_message=message,
        request=_request(explicit, disabled),
        initial_tool_names=["read_file", "write_file", "run_command", "task"],
        available_input_tokens=100_000,
        estimate_tokens=lambda value: len(value) // 4,
    )


def test_explicit_capture_is_same_revision_bounded_and_lifecycle_ready(tmp_path):
    data, _bundle, registry = _fixture(tmp_path)
    result = _prepare(data, "make a workbook", explicit="xlsx")
    assert result["activeSkillNames"] == ["xlsx"]
    assert result["allowedTools"] == ["read_file", "write_file"]
    assert result["registry"] == {key: registry[key] for key in (
        "schema", "dataRootId", "generation", "registryHash",
    )}
    capture = result["captures"][0]
    installation = next(item for item in registry["installations"] if item["displayName"] == "xlsx")
    assert {key: capture[key] for key in ("skillId", "installationId", "revisionId")} == {
        key: installation[key] for key in ("skillId", "installationId", "revisionId")
    }
    assert capture["routingAlias"] == "xlsx"
    assert capture["role"] == "owner"
    assert not {"kind", "sourceState", "sourceObservationIds", "catalogHash"} & set(capture)
    assert capture["body"] == "create workbook"
    assert capture["evidence"]["state"] == "ready"
    assert capture["dependency"]["capabilities"] == ["create"]
    assert "installHint" not in str(capture["dependency"]["manifest"])
    assert capture["resources"]["contract"]["resources"][0]["path"] == "scripts/run.py"
    stored = skill_store.SkillStoreReader(data).read_active("xlsx")
    file_hashes = {item["path"]: item["digest"] for item in stored["object"]["files"]}
    assert capture["evidence"]["contentHash"] == file_hashes["evidence.json"]
    assert capture["dependency"]["manifestHash"] == file_hashes["dependencies.json"]
    assert capture["resources"]["contractHash"] == file_hashes["code-resources.json"]
    lifecycle = skill_lifecycle_v2.build_skill_lifecycle(result)
    serialized = json.dumps(lifecycle, ensure_ascii=False)
    assert "create workbook" not in serialized
    assert "secret-value" not in serialized
    assert str(data) not in serialized


def test_automatic_resolution_matches_existing_pure_resolver_and_order(tmp_path):
    data, bundle, _registry = _fixture(tmp_path)
    message = "创建一个 xlsx 工作簿并美化视觉布局"
    mutable = skill_registry.build_skill_registry_snapshot(data / "skills", bundle)
    expected = skill_registry.resolve_skill_shadow(mutable, message)
    expected_names = [expected["owner"]["name"], *[item["name"] for item in expected["modifiers"]]]
    result = _prepare(data, message)
    assert expected_names == ["xlsx", "document-design"]
    assert result["activeSkillNames"] == expected_names
    assert [item["role"] for item in result["captures"]] == ["owner", "modifier"]
    assert result["allowedTools"] == ["read_file", "write_file"]


def test_admission_never_falls_back_after_mutable_roots_are_removed(tmp_path):
    data, bundle, _registry = _fixture(tmp_path)
    before = _prepare(data, "xlsx", explicit="xlsx")
    shutil.rmtree(data / "skills")
    shutil.rmtree(bundle)
    after = _prepare(data, "xlsx", explicit="xlsx")
    assert after == before


def test_no_match_is_pure_schema_capability_only(tmp_path):
    data, _bundle, _registry = _fixture(tmp_path)
    result = _prepare(data, "hello world")
    assert result["captures"] == []
    assert result["activeSkillNames"] == []
    lifecycle = skill_lifecycle_v2.build_skill_lifecycle(result)
    assert lifecycle["activation"]["outcome"] == "none"
    assert lifecycle["activation"]["registry"] == result["registry"]


def test_disabled_or_blocked_explicit_skill_is_unavailable(tmp_path):
    data, _bundle, _registry = _fixture(tmp_path / "disabled")
    with pytest.raises(skill_admission.SkillAdmissionError) as caught:
        _prepare(data, "xlsx", explicit="xlsx", disabled=["xlsx"])
    assert caught.value.code == "immutable_explicit_skill_unavailable"

    data, bundle, catalog_registry = _fixture(tmp_path / "blocked")
    del catalog_registry
    # A fresh modified profile produces a blocked binding; it is never captured.
    other = tmp_path / "blocked-fresh"
    other_data, other_bundle = other / "profile", other / "bundle"
    other_data.mkdir(parents=True); other_bundle.mkdir()
    _write_skill(other_bundle, "alpha")
    (other_data / "skills").mkdir(); _write_skill(other_data / "skills", "alpha", body="modified")
    catalog = skill_revisions.build_bundled_catalog(other_bundle, {"alpha": "code.bundle/alpha"})
    skill_store.SkillStore(other_data, other_bundle, write_enabled=True).bootstrap(catalog)
    with pytest.raises(skill_admission.SkillAdmissionError) as caught:
        _prepare(other_data, "alpha", explicit="alpha")
    assert caught.value.code == "immutable_explicit_skill_unavailable"


@pytest.mark.parametrize("filename,payload,code", [
    ("dependencies.json", b"{broken", "immutable_explicit_skill_unavailable"),
    ("code-resources.json", b"{broken", "immutable_explicit_skill_unavailable"),
    ("evidence.json", _json({"schemaVersion": 1, "requirements": [], "padding": "x" * (70 * 1024)}).encode(), "immutable_sidecar_too_large"),
], ids=["bad-dependencies", "bad-resources", "oversize-evidence"])
def test_malformed_or_oversize_sidecars_fail_closed(tmp_path, filename, payload, code):
    data, bundle, _registry = _fixture(tmp_path)
    # Rebuild a separate store because immutable objects themselves must not be edited.
    shutil.rmtree(data / skill_store.STORE_DIRECTORY)
    (data / "skills" / "xlsx" / filename).write_bytes(payload)
    shutil.rmtree(bundle / "xlsx")
    shutil.copytree(data / "skills" / "xlsx", bundle / "xlsx")
    catalog = skill_revisions.build_bundled_catalog(bundle, {
        "document-design": "code.bundle/document-design", "xlsx": "code.bundle/xlsx",
    })
    skill_store.SkillStore(data, bundle, write_enabled=True).bootstrap(catalog)
    with pytest.raises(skill_admission.SkillAdmissionError) as caught:
        _prepare(data, "xlsx", explicit="xlsx")
    assert caught.value.code == code


def test_resource_hash_mismatch_and_evidence_tool_expansion_are_blocked(tmp_path):
    data, bundle, _registry = _fixture(tmp_path / "resource")
    shutil.rmtree(data / skill_store.STORE_DIRECTORY)
    contract_path = data / "skills" / "xlsx" / "code-resources.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["resources"][0]["sha256"] = "0" * 64
    contract_path.write_text(_json(contract), encoding="utf-8", newline="\n")
    shutil.rmtree(bundle / "xlsx"); shutil.copytree(data / "skills" / "xlsx", bundle / "xlsx")
    catalog = skill_revisions.build_bundled_catalog(bundle, {
        "document-design": "code.bundle/document-design", "xlsx": "code.bundle/xlsx",
    })
    skill_store.SkillStore(data, bundle, write_enabled=True).bootstrap(catalog)
    with pytest.raises(skill_admission.SkillAdmissionError) as caught:
        _prepare(data, "xlsx", explicit="xlsx")
    assert caught.value.code == "immutable_resources_invalid"

    data, _bundle, _registry = _fixture(tmp_path / "evidence")
    result = skill_admission.prepare_immutable_admission(
        reader=skill_store.SkillStoreReader(data), messages=[], user_message="xlsx",
        request=_request("xlsx"), initial_tool_names=["read_file"],
        available_input_tokens=100_000, estimate_tokens=lambda value: len(value) // 4,
    )
    assert result["captures"][0]["evidence"] == {
        "state": "invalid",
        "contentHash": result["captures"][0]["evidence"]["contentHash"],
    }


def test_oversize_executable_resource_is_not_captured(tmp_path):
    data, bundle, _registry = _fixture(tmp_path)
    shutil.rmtree(data / skill_store.STORE_DIRECTORY)
    script = b"x" * (2 * 1024 * 1024 + 1)
    script_path = data / "skills" / "xlsx" / "scripts" / "run.py"
    script_path.write_bytes(script)
    contract_path = data / "skills" / "xlsx" / "code-resources.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["resources"][0]["sha256"] = hashlib.sha256(script).hexdigest()
    contract_path.write_text(_json(contract), encoding="utf-8", newline="\n")
    shutil.rmtree(bundle / "xlsx"); shutil.copytree(data / "skills" / "xlsx", bundle / "xlsx")
    catalog = skill_revisions.build_bundled_catalog(bundle, {
        "document-design": "code.bundle/document-design", "xlsx": "code.bundle/xlsx",
    })
    skill_store.SkillStore(data, bundle, write_enabled=True).bootstrap(catalog)
    with pytest.raises(skill_admission.SkillAdmissionError) as caught:
        _prepare(data, "xlsx", explicit="xlsx")
    assert caught.value.code == "immutable_resources_invalid"


def test_capture_rechecks_reader_identity(tmp_path):
    data, _bundle, _registry = _fixture(tmp_path)

    class ChangingReader:
        def __init__(self):
            self.reader = skill_store.SkillStoreReader(data)
            self.calls = 0

        def read_registry(self):
            return self.reader.read_registry()

        def read_active(self, alias):
            self.calls += 1
            value = self.reader.read_active(alias)
            if self.calls > 2:
                value = copy.deepcopy(value)
                value["installation"]["revisionId"] = "sha256:" + "f" * 64
            return value

    with pytest.raises(skill_admission.SkillAdmissionError) as caught:
        _prepare(data, "xlsx", explicit="xlsx", reader=ChangingReader())
    assert caught.value.code == "immutable_capture_changed"


# Pure lifecycle/v2 contract coverage shares the C1 foundation test file.
def _hash(char):
    return "sha256:" + char * 64


def _dependency(skill="alpha"):
    manifest = {
        "schemaVersion": 1,
        "skill": skill,
        "capabilities": [{
            "id": "run",
            "required": [{
                "id": "command:python",
                "type": "command",
                "name": "python",
                "optional": False,
            }],
            "optional": [],
        }],
    }
    return {
        "state": "ready",
        "manifestHash": _hash("4"),
        "capabilities": ["run"],
        "manifest": manifest,
    }


def _resources(skill="alpha"):
    return {
        "state": "ready",
        "contractHash": _hash("5"),
        "contract": {
            "schemaVersion": 1,
            "skill": skill,
            "resources": [{
                "id": "runner",
                "path": "scripts/run.py",
                "sha256": "6" * 64,
                "kind": "python",
                "protocol": "code-test/v1",
                "modelVisible": True,
                "arguments": ["<input>"],
            }],
        },
    }


def _evidence():
    return {
        "state": "ready",
        "contentHash": _hash("3"),
        "contract": {
            "schemaVersion": 1,
            "requirements": [{
                "id": "write",
                "type": "artifact",
                "tool": "write_file",
                "minCount": 1,
                "artifactKind": "file",
            }],
            "enforcement": {"schemaVersion": 1, "mode": "explicit_only"},
        },
    }


def _selected(name="alpha", role="owner", char="1"):
    return {
        "name": name,
        "routingAlias": name,
        "displayName": name.title(),
        "role": role,
        "skillId": f"code.bundle/{name}",
        "installationId": "si1_" + char * 32,
        "revisionId": _hash(char),
        "skillContentHash": _hash("2" if char == "1" else "7"),
        "evidence": _evidence(),
        "dependency": _dependency(name),
        "resources": _resources(name),
    }


def _lifecycle(*selected, intent="automatic", outcome=None):
    selected = list(selected) if selected else ([] if outcome == "none" else [_selected()])
    return {
        "schemaVersion": 2,
        "mode": "immutable-v1",
        "activation": {
            "schemaVersion": 2,
            "intentKind": intent,
            "outcome": outcome or ("activated" if selected else "none"),
            "registry": {
                "schema": "code-skill-install-registry/v1",
                "dataRootId": "dr1_" + "8" * 32,
                "generation": 0,
                "registryHash": _hash("9"),
            },
            "selected": selected,
        },
        "access": {"schemaVersion": 3, "resourceBindings": []},
    }


def _set(path, value):
    def mutate(target):
        current = target
        for part in path[:-1]:
            current = current[part]
        current[path[-1]] = value
    return mutate


@pytest.mark.parametrize("mutation", [
    _set(("schemaVersion",), 1),
    _set(("mode",), "canonical-v1"),
    _set(("activation", "schemaVersion"), 1),
    _set(("activation", "intentKind"), "legacy"),
    _set(("activation", "registry", "schema"), "other"),
    _set(("activation", "registry", "dataRootId"), "dr1_bad"),
    _set(("activation", "registry", "generation"), True),
    _set(("activation", "registry", "registryHash"), _hash("A")),
    _set(("activation", "selected", 0, "name"), "../alpha"),
    _set(("activation", "selected", 0, "routingAlias"), "C:/alpha"),
    _set(("activation", "selected", 0, "displayName"), "bad\nname"),
    _set(("activation", "selected", 0, "role"), "modifier"),
    _set(("activation", "selected", 0, "skillId"), "unknown/alpha"),
    _set(("activation", "selected", 0, "installationId"), "si1_bad"),
    _set(("activation", "selected", 0, "revisionId"), _hash("A")),
    _set(("activation", "selected", 0, "skillContentHash"), "bad"),
    _set(("activation", "selected", 0, "evidence", "contentHash"), "bad"),
    _set(("activation", "selected", 0, "evidence", "contract", "requirements", 0, "tool"), "../tool"),
    _set(("activation", "selected", 0, "dependency", "manifestHash"), "bad"),
    _set(("activation", "selected", 0, "dependency", "capabilities"), ["other"]),
    _set(("activation", "selected", 0, "dependency", "manifest", "skill"), "other"),
    _set(("activation", "selected", 0, "resources", "contractHash"), "bad"),
    _set(("activation", "selected", 0, "resources", "contract", "skill"), "other"),
    _set(("activation", "selected", 0, "resources", "contract", "resources", 0, "path"), "C:/run.py"),
    _set(("activation", "selected", 0, "resources", "contract", "resources", 0, "arguments"), ["C:/secret"]),
    _set(("access", "schemaVersion"), 2),
])
def test_every_authority_field_tamper_fails_closed(mutation):
    value = _lifecycle()
    mutation(value)
    with pytest.raises(lifecycle.SkillLifecycleV2Error):
        lifecycle.normalize_skill_lifecycle(value)


def test_build_normalize_and_existing_compatible_projection_drop_ephemeral_body():
    selected = _selected()
    admission = {
        "intentKind": "explicit",
        "registry": _lifecycle()["activation"]["registry"],
        "captures": [{key: value for key, value in selected.items() if key != "role"} | {
            "body": "private instructions",
        }],
    }
    value = lifecycle.build_skill_lifecycle(admission)
    assert value == lifecycle.normalize_skill_lifecycle(value)
    assert "private instructions" not in str(value)
    projection = lifecycle.project_skill_lifecycle(value)
    assert projection == {
        "activeSkillNames": ["alpha"],
        "dependencies": {"alpha": ["run"]},
        "captures": [{
            "name": "alpha",
            "contentHash": _hash("2"),
            "evidenceState": "ready",
            "evidence": _evidence()["contract"],
        }],
        "explicit": True,
    }
    assert "revisionId" not in str(projection)


def test_access_binding_is_exact_idempotent_and_conflict_safe():
    value = lifecycle.normalize_skill_lifecycle(_lifecycle())
    bound = lifecycle.bind_text_resource(
        value, "si1_" + "1" * 32, _hash("1"), "references/guide.md", _hash("a"),
    )
    assert lifecycle.bind_text_resource(
        bound, "si1_" + "1" * 32, _hash("1"), "references/guide.md", _hash("a"),
    ) == bound
    with pytest.raises(lifecycle.SkillLifecycleV2Error) as caught:
        lifecycle.bind_text_resource(
            bound, "si1_" + "1" * 32, _hash("1"), "references/guide.md", _hash("b"),
        )
    assert caught.value.code == "skill_lifecycle_v2_access_conflict"
    duplicate = copy.deepcopy(bound)
    duplicate["access"]["resourceBindings"].append(copy.deepcopy(duplicate["access"]["resourceBindings"][0]))
    with pytest.raises(lifecycle.SkillLifecycleV2Error):
        lifecycle.normalize_skill_lifecycle(duplicate)


def test_selected_count_order_uniqueness_and_none_contract():
    modifier = _selected("beta", "modifier", "b")
    assert [item["role"] for item in lifecycle.normalize_skill_lifecycle(
        _lifecycle(_selected(), modifier),
    )["activation"]["selected"]] == ["owner", "modifier"]
    for value in (
        _lifecycle(_selected(), _selected()),
        _lifecycle(_selected(), modifier, _selected("gamma", "modifier", "c")),
        _lifecycle(intent="explicit", outcome="none"),
    ):
        with pytest.raises(lifecycle.SkillLifecycleV2Error):
            lifecycle.normalize_skill_lifecycle(value)
    empty = lifecycle.normalize_skill_lifecycle(_lifecycle(outcome="none"))
    assert empty["activation"]["selected"] == []

    duplicate_install = _selected("beta", "modifier", "b")
    duplicate_install["installationId"] = "si1_" + "1" * 32
    duplicate_skill = _selected("beta", "modifier", "b")
    duplicate_skill["skillId"] = "code.bundle/alpha"
    for value in (_lifecycle(_selected(), duplicate_install), _lifecycle(_selected(), duplicate_skill)):
        with pytest.raises(lifecycle.SkillLifecycleV2Error):
            lifecycle.normalize_skill_lifecycle(value)


def test_v1_and_v2_modules_do_not_reinterpret_each_other():
    assert skill_lifecycle.LIFECYCLE_SCHEMA_VERSION == 1
    with pytest.raises(lifecycle.SkillLifecycleV2Error):
        lifecycle.normalize_skill_lifecycle({"schemaVersion": 1})
    with pytest.raises(skill_lifecycle.SkillLifecycleError) as caught:
        skill_lifecycle.normalize_skill_lifecycle(_lifecycle())
    assert caught.value.code == "skill_lifecycle_version_unsupported"


def test_contract_and_lifecycle_bounds_are_not_broadened():
    assert lifecycle.MAX_LIFECYCLE_BYTES <= skill_lifecycle.MAX_LIFECYCLE_BYTES
    assert lifecycle.MAX_EVIDENCE_CONTRACT_BYTES <= skill_lifecycle.MAX_EVIDENCE_CONTRACT_BYTES
    value = _lifecycle()
    value["activation"]["selected"][0]["dependency"]["manifest"]["capabilities"] = [
        {"id": f"cap{i}", "required": [], "optional": []} for i in range(5000)
    ]
    value["activation"]["selected"][0]["dependency"]["capabilities"] = [f"cap{i}" for i in range(5000)]
    with pytest.raises(lifecycle.SkillLifecycleV2Error) as caught:
        lifecycle.normalize_skill_lifecycle(value)
    assert caught.value.code == "skill_lifecycle_v2_size_limit"


@pytest.mark.parametrize("captures", [None, {}, "invalid"])
def test_lifecycle_builder_rejects_malformed_captures_instead_of_none(captures):
    admission = {
        "intentKind": "automatic",
        "registry": _lifecycle(outcome="none")["activation"]["registry"],
        "captures": captures,
    }
    with pytest.raises(lifecycle.SkillLifecycleV2Error) as caught:
        lifecycle.build_skill_lifecycle(admission)
    assert caught.value.code == "skill_lifecycle_v2_admission_invalid"
    assert lifecycle.build_skill_lifecycle({**admission, "captures": []})["activation"]["outcome"] == "none"


@pytest.mark.parametrize("mutation", [
    _set(("schemaVersion",), 2.0),
    _set(("activation", "schemaVersion"), 2.0),
    _set(("access", "schemaVersion"), 3.0),
    _set(("activation", "selected", 0, "evidence", "contract", "enforcement", "schemaVersion"), True),
])
def test_lifecycle_versions_require_integers(mutation):
    value = _lifecycle()
    mutation(value)
    with pytest.raises(lifecycle.SkillLifecycleV2Error):
        lifecycle.normalize_skill_lifecycle(value)


@pytest.mark.parametrize("alias", ["", ".", "./SKILL.md", "references//guide.md", "references/./guide.md"])
def test_bind_text_resource_rejects_noncanonical_path_aliases(alias):
    value = lifecycle.normalize_skill_lifecycle(_lifecycle())
    with pytest.raises(lifecycle.SkillLifecycleV2Error) as caught:
        lifecycle.bind_text_resource(
            value, "si1_" + "1" * 32, _hash("1"), alias, _hash("a"),
        )
    assert caught.value.code == "skill_lifecycle_v2_path_invalid"
    compatible = lifecycle.bind_text_resource(
        value, "si1_" + "1" * 32, _hash("1"), "references\\guide.md", _hash("a"),
    )
    assert compatible["access"]["resourceBindings"][0]["file"] == "references/guide.md"
