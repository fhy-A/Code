"""Pure, exact v2 management metadata and deterministic state transitions.

Revision objects and the bootstrap facts keep their original v1 identities.
This module neither reads sources nor grants execution authority.
"""
from __future__ import annotations

import copy
import hashlib
import re

from . import skill_revisions as revisions
from . import skill_store as legacy

REGISTRY_SCHEMA = "code-skill-install-registry/v2"
TRANSACTION_SCHEMA = "code-skill-store-transaction/v2"
PHASES = ("prepared", "captured", "objects-published", "registry-published", "committed")
TERMINAL = {"committed", "aborted"}
OP_ID = re.compile(r"op2_[0-9a-f]{64}\Z")
OP_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
PACKAGE_KINDS = {"create-local", "import-local", "edit-local", "fork-bundled", "update-bundled"}
KINDS = PACKAGE_KINDS | {
    "convert-v2", "rollback", "set-enabled", "uninstall", "restore",
    "select-candidate", "migrate-preferences",
}
_INSTALL_FIELDS = {
    "installationId", "skillId", "kind", "displayName", "revisionId",
    "sourceState", "sourceObservationIds", "enabled", "uninstalled", "retainedRevisionIds",
}
_BINDING_FIELDS = {
    "routingAlias", "state", "reasonCode", "candidates", "activeCandidate",
    "selectedInstallationId",
}
_REASONS = legacy._BINDING_REASONS | {
    "selection-required", "installation-disabled", "installation-uninstalled",
}


def _integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 2**53 - 1


def _hash(value):
    return isinstance(value, str) and legacy._HASH.fullmatch(value) is not None


def _sorted_unique(value, limit, code):
    legacy._bounded_list(value, limit, code)
    if any(not isinstance(item, str) for item in value) or value != sorted(set(value)):
        legacy._fail(code)
    return value


def operation_id(root_id, key_hash):
    return "op2_" + hashlib.sha256(legacy._canonical(["management-v2", root_id, key_hash])).hexdigest()


def normalize_request(value):
    if not isinstance(value, dict) or not isinstance(value.get("kind"), str) or value["kind"] not in KINDS:
        legacy._fail("management_request_invalid")
    kind = value["kind"]
    fields = {"kind"}
    if kind in PACKAGE_KINDS | {"rollback"}:
        fields |= {"routingAlias", "revisionId", "conflict"}
    if kind not in {"convert-v2", "create-local", "import-local", "migrate-preferences"}:
        fields.add("installationId")
    if kind == "set-enabled":
        fields.add("enabled")
    if kind == "select-candidate":
        fields.add("routingAlias")
    if kind == "update-bundled":
        fields.add("catalog")
    if kind == "migrate-preferences":
        fields |= {"disabledNames", "confirmed"}
    legacy._exact(value, fields, "management_request_invalid")
    if "installationId" in fields and not legacy._INSTALL_ID.fullmatch(str(value["installationId"])):
        legacy._fail("management_identity_invalid")
    if "routingAlias" in fields:
        legacy._alias(value["routingAlias"])
    if "revisionId" in fields and not _hash(value["revisionId"]):
        legacy._fail("management_revision_invalid")
    if "conflict" in fields and value["conflict"] not in ("reject", "select-new"):
        legacy._fail("management_request_invalid")
    if "enabled" in fields and type(value["enabled"]) is not bool:
        legacy._fail("management_request_invalid")
    if kind == "update-bundled":
        catalog = revisions.normalize_bundled_catalog(value["catalog"])
        if catalog != value["catalog"]:
            legacy._fail("management_catalog_invalid")
    if kind == "migrate-preferences":
        if value["confirmed"] is not True:
            legacy._fail("management_confirmation_required")
        names = legacy._bounded_list(value["disabledNames"], legacy.MAX_BINDINGS, "management_request_invalid")
        if any(not isinstance(name, str) for name in names):
            legacy._fail("management_request_invalid")
        for name in names:
            legacy._alias(name)
        if len({name.casefold() for name in names}) != len(names) or names != sorted(names, key=str.casefold):
            legacy._fail("management_request_invalid")
    return copy.deepcopy(value)


def retained_ids(registry):
    return {revision_id for item in registry["installations"]
            for revision_id in item.get("retainedRevisionIds", [item["revisionId"]])}


def _legacy_facts(value):
    """Reuse the precise v1 observation/tombstone contract, without relabeling it."""
    facts = {key: copy.deepcopy(value[key]) for key in ("dataRootId", "sourceObservations", "bundledTombstones")}
    probe = {"schema": legacy.REGISTRY_SCHEMA, "generation": 0, "installations": [],
             "bindings": [], "operationReceipts": [], **facts}
    probe["registryHash"] = legacy._registry_hash(probe)
    try:
        legacy.normalize_registry(probe)
    except (KeyError, TypeError, ValueError) as exc:
        raise legacy.SkillStoreError("registry_legacy_facts_invalid") from exc


def _refresh_binding(binding, installations):
    selected = binding["selectedInstallationId"]
    if selected is None:
        binding["activeCandidate"] = None
        return
    item = installations[selected]
    if item["uninstalled"]:
        binding.update(state="uninstalled", reasonCode="installation-uninstalled", activeCandidate=None)
    elif not item["enabled"]:
        binding.update(state="disabled", reasonCode="installation-disabled", activeCandidate=None)
    else:
        binding.update(state="ready", reasonCode=None, activeCandidate={
            "installationId": selected, "revisionId": item["revisionId"],
        })


def normalize_registry(value):
    legacy._exact(value, {"schema", "dataRootId", "generation", "installations", "bindings",
                          "bundledTombstones", "sourceObservations", "operationReceipts", "registryHash"},
                  "registry_invalid")
    if (value["schema"] != REGISTRY_SCHEMA or not legacy._ROOT_ID.fullmatch(str(value["dataRootId"]))
            or not _integer(value["generation"], 1)):
        legacy._fail("registry_invalid")
    _legacy_facts(value)
    observations = {item["sourceObservationId"] for item in value["sourceObservations"]}
    installs, skill_ids = {}, set()
    for item in legacy._bounded_list(value["installations"], legacy.MAX_INSTALLATIONS, "registry_installations_invalid"):
        legacy._exact(item, _INSTALL_FIELDS, "registry_installations_invalid")
        iid, sid = item["installationId"], item["skillId"]
        if (not isinstance(iid, str) or not legacy._INSTALL_ID.fullmatch(iid) or iid in installs
                or not isinstance(sid, str) or sid in skill_ids or item["kind"] not in ("bundled", "local")
                or not (legacy._BUNDLE_ID if item["kind"] == "bundled" else legacy._LOCAL_ID).fullmatch(sid)
                or not _hash(item["revisionId"]) or type(item["enabled"]) is not bool
                or type(item["uninstalled"]) is not bool
                or item["sourceState"] not in ("present", "catalog-only", "source-missing", "managed")):
            legacy._fail("registry_installations_invalid")
        legacy._display(item["displayName"])
        sources = _sorted_unique(item["sourceObservationIds"], 2, "registry_installations_invalid")
        if not set(sources) <= observations or not sources and item["sourceState"] != "managed":
            legacy._fail("registry_installations_invalid")
        retained = _sorted_unique(item["retainedRevisionIds"], legacy.MAX_OBJECTS, "registry_retention_invalid")
        if item["revisionId"] not in retained or any(not _hash(rev) for rev in retained):
            legacy._fail("registry_retention_invalid")
        installs[iid] = item
        skill_ids.add(sid)
    if list(installs) != sorted(installs) or len(retained_ids(value)) > legacy.MAX_OBJECTS:
        legacy._fail("registry_not_canonical")
    aliases, bound = set(), set()
    for binding in legacy._bounded_list(value["bindings"], legacy.MAX_BINDINGS, "registry_bindings_invalid"):
        legacy._exact(binding, _BINDING_FIELDS, "registry_bindings_invalid")
        alias = legacy._alias(binding["routingAlias"])
        candidates = legacy._bounded_list(binding["candidates"], 2, "registry_bindings_invalid")
        ids = []
        for candidate in candidates:
            legacy._exact(candidate, {"installationId", "revisionId"}, "registry_bindings_invalid")
            iid = candidate["installationId"]
            if not isinstance(iid, str) or iid not in installs or candidate["revisionId"] != installs[iid]["revisionId"]:
                legacy._fail("registry_bindings_invalid")
            ids.append(iid)
        if alias.casefold() in aliases or ids != sorted(set(ids)) or bound.intersection(ids):
            legacy._fail("registry_bindings_invalid")
        aliases.add(alias.casefold())
        bound.update(ids)
        selected = binding["selectedInstallationId"]
        if selected is None:
            if (binding["state"] not in ("blocked", "tombstoned") or binding["activeCandidate"] is not None
                    or not isinstance(binding["reasonCode"], str) or binding["reasonCode"] not in _REASONS):
                legacy._fail("registry_bindings_invalid")
        else:
            if not isinstance(selected, str) or selected not in ids:
                legacy._fail("registry_bindings_invalid")
            expected = copy.deepcopy(binding)
            _refresh_binding(expected, installs)
            if binding != expected:
                legacy._fail("registry_bindings_invalid")
    if bound != set(installs) or value["bindings"] != sorted(value["bindings"], key=lambda item: (item["routingAlias"].casefold(), item["routingAlias"])):
        legacy._fail("registry_not_canonical")
    operations, generations = [], set()
    for receipt in legacy._bounded_list(value["operationReceipts"], legacy.MAX_RECEIPTS, "registry_receipts_invalid"):
        if not isinstance(receipt, dict):
            legacy._fail("registry_receipts_invalid")
        old = receipt.get("kind") == "bootstrap-v1"
        fields = {"operationId", "kind", "requestHash", "appliedGeneration", "resultStateHash"}
        legacy._exact(receipt, fields if old else fields | {"result"}, "registry_receipts_invalid")
        op = receipt["operationId"]
        generation = receipt["appliedGeneration"]
        if (not isinstance(op, str) or not (legacy._OP_ID if old else OP_ID).fullmatch(op)
                or op in operations or not _integer(generation) or generation > value["generation"]
                or generation in generations or not _hash(receipt["requestHash"])
                or not _hash(receipt["resultStateHash"]) or old and generation != 0
                or not old and (not isinstance(receipt["kind"], str) or receipt["kind"] not in KINDS or generation == 0)):
            legacy._fail("registry_receipts_invalid")
        if not old:
            result = receipt["result"]
            legacy._exact(result, {"installationId", "revisionId"}, "registry_receipts_invalid")
            iid, rev = result["installationId"], result["revisionId"]
            if (iid is None) != (rev is None) or iid is not None and (
                not isinstance(iid, str) or iid not in installs or rev not in installs[iid]["retainedRevisionIds"]
            ):
                legacy._fail("registry_receipts_invalid")
        if generation == value["generation"] and receipt["resultStateHash"] != legacy._state_hash(value):
            legacy._fail("registry_receipts_invalid")
        operations.append(op)
        generations.add(generation)
    if (operations != sorted(operations) or len(operations) != value["generation"] + 1
            or generations != set(range(len(operations)))):
        legacy._fail("registry_receipts_invalid")
    if value["registryHash"] != legacy._registry_hash(value):
        legacy._fail("registry_hash_mismatch")
    return copy.deepcopy(value)


def _assign_alias(target, item, alias, conflict):
    iid = item["installationId"]
    bindings = target["bindings"]
    previous = next((b for b in bindings if any(c["installationId"] == iid for c in b["candidates"])), None)
    destination = next((b for b in bindings if b["routingAlias"].casefold() == alias.casefold()), None)
    if destination is not None and destination is not previous and conflict != "select-new":
        legacy._fail("management_alias_conflict")
    if destination is previous and previous is not None:
        if previous["routingAlias"] != alias and len(previous["candidates"]) != 1:
            legacy._fail("management_alias_conflict")
        previous["routingAlias"] = alias
        for candidate in previous["candidates"]:
            if candidate["installationId"] == iid:
                candidate["revisionId"] = item["revisionId"]
        # Editing an unselected candidate is not authority to select it.
        return
    if destination is not None and len(destination["candidates"]) >= 2:
        legacy._fail("management_alias_conflict")
    if previous is not None:
        previous["candidates"] = [c for c in previous["candidates"] if c["installationId"] != iid]
        if previous["selectedInstallationId"] == iid:
            previous.update(selectedInstallationId=None, activeCandidate=None,
                            state="blocked", reasonCode="selection-required")
        if not previous["candidates"]:
            bindings.remove(previous)
    if destination is None:
        destination = {"routingAlias": alias, "state": "blocked", "reasonCode": "selection-required",
                       "candidates": [], "activeCandidate": None, "selectedInstallationId": None}
        bindings.append(destination)
    destination["candidates"].append({"installationId": iid, "revisionId": item["revisionId"]})
    destination["selectedInstallationId"] = iid


def make_target(base, request, op_id):
    """Compute a new generation, including its immutable historical receipt."""
    base = legacy.normalize_registry(base)
    request = normalize_request(request)
    return _make_target_from_validated(base, request, op_id)


def _make_target_from_validated(base, request, op_id):
    """Use this call's validated copies; never retain trust across calls."""
    kind = request["kind"]
    if not OP_ID.fullmatch(str(op_id)):
        legacy._fail("management_identity_invalid")
    if base["schema"] != REGISTRY_SCHEMA and kind != "convert-v2":
        legacy._fail("management_conversion_required")
    if base["schema"] == REGISTRY_SCHEMA and kind == "convert-v2":
        legacy._fail("management_already_managed")
    target = copy.deepcopy(base)
    target["schema"] = REGISTRY_SCHEMA
    target["generation"] += 1
    if kind == "convert-v2":
        for item in target["installations"]:
            item.update(enabled=True, uninstalled=False, retainedRevisionIds=[item["revisionId"]])
        for binding in target["bindings"]:
            selected = binding["activeCandidate"]
            binding["selectedInstallationId"] = selected["installationId"] if selected else None
    installs = {item["installationId"]: item for item in target["installations"]}
    item = installs.get(request.get("installationId"))
    if "installationId" in request and item is None:
        legacy._fail("management_installation_missing")
    if item is not None and item["uninstalled"] and kind not in {"restore", "uninstall"}:
        legacy._fail("management_installation_uninstalled")
    if kind == "edit-local" and item["kind"] != "local":
        legacy._fail("management_bundled_requires_fork")
    if kind in {"fork-bundled", "update-bundled"} and item["kind"] != "bundled":
        legacy._fail("management_bundled_required")
    if kind == "update-bundled":
        expected = {"skillId": item["skillId"], "directory": request["routingAlias"],
                    "revisionId": request["revisionId"]}
        if expected not in request["catalog"]["skills"]:
            legacy._fail("management_catalog_identity_mismatch")
    if kind in {"create-local", "import-local", "fork-bundled"}:
        identity = hashlib.sha256(legacy._canonical([op_id, "local-installation"])).hexdigest()[:32]
        item = {"installationId": "si1_" + identity, "skillId": "local.skill/" + identity,
                "kind": "local", "displayName": request["routingAlias"], "revisionId": request["revisionId"],
                "sourceState": "managed", "sourceObservationIds": [], "enabled": True,
                "uninstalled": False, "retainedRevisionIds": []}
        if item["installationId"] in installs or any(i["skillId"] == item["skillId"] for i in installs.values()):
            legacy._fail("identity_collision")
        installs[item["installationId"]] = item
        target["installations"].append(item)
    if kind == "rollback" and request["revisionId"] not in item["retainedRevisionIds"]:
        legacy._fail("management_revision_not_retained")
    if kind in PACKAGE_KINDS | {"rollback"}:
        item.update(revisionId=request["revisionId"], displayName=request["routingAlias"],
                    sourceState="managed", sourceObservationIds=[])
        item["retainedRevisionIds"] = sorted(set(item["retainedRevisionIds"]) | {item["revisionId"]})
        _assign_alias(target, item, request["routingAlias"], request["conflict"])
    elif kind == "set-enabled":
        item["enabled"] = request["enabled"]
    elif kind in {"uninstall", "restore"}:
        item["uninstalled"] = kind == "uninstall"
    elif kind == "select-candidate":
        binding = next((b for b in target["bindings"] if b["routingAlias"] == request["routingAlias"]), None)
        if binding is None or not any(c["installationId"] == item["installationId"] for c in binding["candidates"]):
            legacy._fail("management_alias_conflict")
        binding["selectedInstallationId"] = item["installationId"]
    elif kind == "migrate-preferences":
        by_name = {b["routingAlias"].casefold(): b for b in target["bindings"]}
        for name in request["disabledNames"]:
            if name.casefold() not in by_name:
                legacy._fail("management_alias_missing")
            for candidate in by_name[name.casefold()]["candidates"]:
                installs[candidate["installationId"]]["enabled"] = False
    for binding in target["bindings"]:
        binding["candidates"].sort(key=lambda candidate: candidate["installationId"])
        _refresh_binding(binding, installs)
    target["bindings"].sort(key=lambda b: (b["routingAlias"].casefold(), b["routingAlias"]))
    target["installations"].sort(key=lambda installed: installed["installationId"])
    receipt = {"operationId": op_id, "kind": kind, "requestHash": legacy._digest(legacy._canonical(request)),
               "appliedGeneration": target["generation"], "resultStateHash": legacy._state_hash(target),
               "result": {"installationId": item["installationId"] if item else None,
                          "revisionId": item["revisionId"] if item else None}}
    target["operationReceipts"].append(receipt)
    target["operationReceipts"].sort(key=lambda value: value["operationId"])
    target["registryHash"] = legacy._registry_hash(target)
    return normalize_registry(target)


def normalize_journal(value):
    legacy._exact(value, {"schema", "operationId", "operationKeyHash", "request", "requestHash", "phase",
                          "journalGeneration", "dataRootId", "baseRegistry", "targetRegistry", "objectManifests"},
                  "journal_invalid")
    if (value["schema"] != TRANSACTION_SCHEMA or not isinstance(value["phase"], str)
            or value["phase"] not in set(PHASES) | {"aborted"}
            or not _integer(value["journalGeneration"]) or not _hash(value["operationKeyHash"])):
        legacy._fail("journal_invalid")
    if (value["phase"] == "aborted" and not 1 <= value["journalGeneration"] <= 3
            or value["phase"] != "aborted" and value["journalGeneration"] != PHASES.index(value["phase"])):
        legacy._fail("journal_invalid")
    base = legacy.normalize_registry(value["baseRegistry"])
    if base["schema"] != REGISTRY_SCHEMA:
        base = copy.deepcopy(base)  # The legacy v1 normalizer retains nested references.
    request = normalize_request(value["request"])
    if (value["dataRootId"] != base["dataRootId"]
            or value["operationId"] != operation_id(base["dataRootId"], value["operationKeyHash"])
            or value["requestHash"] != legacy._digest(legacy._canonical(request))):
        legacy._fail("journal_invalid")
    target = _make_target_from_validated(base, request, value["operationId"])
    if target != value["targetRegistry"]:
        legacy._fail("journal_target_invalid")
    manifests = legacy._bounded_list(value["objectManifests"], 1, "journal_invalid")
    expected = [request["revisionId"]] if request["kind"] in PACKAGE_KINDS else []
    try:
        normalized = [revisions.normalize_revision_manifest(item) for item in manifests]
    except (KeyError, TypeError, ValueError) as exc:
        raise legacy.SkillStoreError("journal_invalid") from exc
    if normalized != manifests or [item["revisionId"] for item in manifests] != expected:
        legacy._fail("journal_invalid")
    # These four nested values already have independent validated copies.
    # All remaining fields are schema-checked scalars. Reusing the copies
    # avoids cloning both registries again without sharing caller mutations.
    return {**value, "baseRegistry": base, "targetRegistry": target,
            "request": request, "objectManifests": normalized}
