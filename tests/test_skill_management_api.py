"""Management transport tests: all inputs and packages are synthetic."""
import copy
import json
from unittest import mock

import pytest

from code_runtime import data_dir_owner, skill_store, skill_store_management
from code_runtime import skill_management_api as api
from tests.test_skill_store import _fixture, _snapshot, _write_skill


@pytest.fixture
def service(tmp_path):
    data, bundle, catalog = _fixture(tmp_path)
    _write_skill(data / "skills", "local", extra={"assets/blob.bin": b"\x00\xff\x81"})
    store = skill_store.SkillStore(data, bundle, write_enabled=True)
    store.bootstrap(catalog)
    with data_dir_owner.acquire_data_dir_owner(data) as owner:
        yield api.SkillManagementService(
            data, bundle, owner=owner, admission_enabled=True,
            server_instance_id="synthetic", catalog_loader=lambda: catalog,
        )


def _preview(service, kind, **fields):
    return service.preview({
        "protocol": api.PROTOCOL, "base": service.snapshot()["registry"],
        "kind": kind, **fields,
    })


def _commit(service, preview, key="operation", confirmed=True):
    return service.apply({
        "protocol": api.PROTOCOL, "operationKey": key,
        "base": preview["base"], "request": preview["request"],
        "material": preview.get("material"), "confirmed": confirmed,
    })


def _convert(service):
    return _commit(service, _preview(service, "convert-v2"), "convert")


def _item(service, name):
    return next(item for item in service.snapshot()["installations"]
                if item["displayName"] == name)


def test_empty_service_is_read_only_and_never_bootstraps(tmp_path):
    data, bundle, _ = _fixture(tmp_path)
    before = _snapshot(data)
    service = api.SkillManagementService(data, bundle)
    result = service.snapshot()
    assert result["mode"] == "legacy"
    assert result["registry"] is None
    assert _snapshot(data) == before
    with pytest.raises(api.SkillManagementError, match="management_store_required"):
        service.preview({"protocol": api.PROTOCOL, "kind": "convert-v2", "base": None})
    assert _snapshot(data) == before


def test_conversion_needs_confirmation_and_off_is_read_only(service):
    assert service.snapshot()["mode"] == "immutable-v1"
    before = _snapshot(service.data_root)
    preview = _preview(service, "convert-v2")
    assert _snapshot(service.data_root) == before
    with pytest.raises(api.SkillManagementError, match="management_confirmation_required"):
        _commit(service, preview, confirmed=False)
    assert _snapshot(service.data_root) == before
    _commit(service, preview, "convert")
    assert service.snapshot()["mode"] == "managed-v2"
    service.admission_enabled = False
    before = _snapshot(service.data_root)
    assert service.snapshot()["capabilities"]["write"] is False
    with pytest.raises(api.SkillManagementError, match="management_read_only"):
        _preview(service, "set-enabled", installationId=_item(service, "local")["installationId"], enabled=False)
    assert _snapshot(service.data_root) == before


def test_edit_preserves_full_document_and_all_other_package_bytes(service):
    _convert(service)
    item = _item(service, "local")
    original = service.detail(item["installationId"], item["revisionId"])
    document = original["document"].replace("description: test", "description: test\nlicense: MIT\nmetadata:\n  owner: example")
    document += "\n\nNew body\n"
    preview = _preview(service, "edit-local", installationId=item["installationId"],
                       revisionId=item["revisionId"], routingAlias="local", document=document)
    _commit(service, preview, "edit")
    updated = _item(service, "local")
    detail = service.detail(updated["installationId"], updated["revisionId"])
    assert detail["document"] == document
    assert "license: MIT" in detail["document"]
    reader = skill_store.SkillStoreReader(service.data_root)
    old = reader.read_pinned(original["dataRootId"], item["revisionId"])
    new = reader.read_pinned(original["dataRootId"], updated["revisionId"])
    assert {f["path"]: f["content"] for f in old["files"] if f["path"] != "SKILL.md"} == {
        f["path"]: f["content"] for f in new["files"] if f["path"] != "SKILL.md"}
    assert service.detail(item["installationId"], item["revisionId"])["document"] == original["document"]


def test_original_receipt_before_new_cas_material_or_catalog_reads(service):
    _convert(service)
    item = _item(service, "local")
    detail = service.detail(item["installationId"], item["revisionId"])
    first = _preview(service, "edit-local", installationId=item["installationId"], revisionId=item["revisionId"],
                     routingAlias="local", document=detail["document"] + "\nA")
    receipt = _commit(service, first, "A")["receipt"]
    second = _preview(service, "set-enabled", installationId=item["installationId"], enabled=False)
    _commit(service, second, "B")
    before = _snapshot(service.data_root)
    with mock.patch.object(service, "_material", side_effect=AssertionError("material must not be reread")):
        assert _commit(service, first, "A")["receipt"] == receipt
        bad_new_cas = copy.deepcopy(first)
        bad_new_cas["base"]["generation"] = "not-a-new-CAS"
        bad_new_cas["base"]["registryHash"] = "not-a-new-hash"
        assert _commit(service, bad_new_cas, "A")["receipt"] == receipt
        assert service.receipt("A")["receipt"] == receipt
    assert _snapshot(service.data_root) == before
    with pytest.raises(api.SkillManagementError, match="management_operation_key_conflict"):
        _commit(service, second, "A")
    with pytest.raises(api.SkillManagementError, match="registry_cas_conflict"):
        _commit(service, first, "new")


def test_foreign_root_revision_and_material_tampering_are_rejected(service):
    _convert(service)
    local, bundled = _item(service, "local"), _item(service, "alpha")
    with pytest.raises(api.SkillManagementError, match="management_revision_not_retained"):
        service.detail(local["installationId"], bundled["revisionId"])
    preview = _preview(service, "set-enabled", installationId=local["installationId"], enabled=False)
    foreign = copy.deepcopy(preview)
    foreign["base"]["dataRootId"] = "dr1_" + "0" * 32
    with pytest.raises(api.SkillManagementError, match="management_root_mismatch"):
        _commit(service, foreign)
    edit = _preview(service, "edit-local", installationId=local["installationId"], revisionId=local["revisionId"],
                    routingAlias="local", document=service.detail(local["installationId"])["document"] + "\nnew")
    edit["material"]["document"] += "\ntampered"
    before = _snapshot(service.data_root)
    with pytest.raises(api.SkillManagementError, match="management_source_changed"):
        _commit(service, edit, "tampered")
    assert _snapshot(service.data_root) == before


def test_local_import_is_explicit_and_source_drift_does_not_replan(service, tmp_path):
    _convert(service)
    source = _write_skill(tmp_path / "input", "imported", extra={"scripts/example.py": "print('local')\n"})
    preview = _preview(service, "import-local", routingAlias="imported", sourceRoot=str(source))
    (source / "scripts" / "example.py").write_text("print('changed')\n")
    before = _snapshot(service.data_root)
    with pytest.raises(api.SkillManagementError, match="management_source_changed"):
        _commit(service, preview)
    assert _snapshot(service.data_root) == before


def test_bundled_edit_requires_fork_and_selection_is_explicit(service):
    _convert(service)
    item = _item(service, "alpha")
    document = service.detail(item["installationId"])["document"] + "\nlocal change"
    with pytest.raises(api.SkillManagementError, match="management_bundled_requires_fork"):
        _preview(service, "edit-local", installationId=item["installationId"], revisionId=item["revisionId"],
                 routingAlias="alpha", document=document)
    fork = _preview(service, "fork-bundled", installationId=item["installationId"], revisionId=item["revisionId"],
                     routingAlias="alpha", document=document, conflict="select-new")
    result = _commit(service, fork, "fork")
    assert result["receipt"]["result"]["installationId"] != item["installationId"]
    assert service.detail(item["installationId"], item["revisionId"])["kind"] == "bundled"


@pytest.mark.parametrize("extra", [{"unknown": True}, {"protocol": "future"}, {"base": {}}])
def test_preview_rejects_unknown_transport_and_malformed_base(service, extra):
    body = {"protocol": api.PROTOCOL, "base": service.snapshot()["registry"], "kind": "convert-v2", **extra}
    before = _snapshot(service.data_root)
    with pytest.raises(api.SkillManagementError):
        service.preview(body)
    assert _snapshot(service.data_root) == before


@pytest.mark.parametrize("point", ["after-journal-prepared-publish", "after-journal-captured-publish", "after-managed-registry-publish"])
def test_pending_transport_retry_uses_frozen_base_and_material(service, point):
    from tests.test_skill_store import _CrashOnce
    _convert(service)
    item = _item(service, "local")
    document = service.detail(item["installationId"])["document"] + "\nrevision B"
    preview = _preview(service, "edit-local", installationId=item["installationId"], revisionId=item["revisionId"], document=document)
    service.store.fault_injector = _CrashOnce(point)
    with pytest.raises(RuntimeError):
        _commit(service, preview, "interrupted")
    service.store.fault_injector = None
    preview["base"]["generation"] = "ignore-new-CAS"
    result = _commit(service, preview, "interrupted")
    assert result["receipt"]["appliedGeneration"] == 2
    assert service.detail(item["installationId"])["document"] == document
