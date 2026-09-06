"""Versioned, explicit management facade over the immutable D1 engine.

Constructors and reads do not bootstrap, migrate, repair, or acquire an owner.
Packages are captured only from a supplied directory or an exact retained object.
"""
from __future__ import annotations

import copy
from functools import wraps
import json
from pathlib import Path

from . import skill_admission as admission
from . import skill_registry
from . import skill_revisions as revisions
from . import skill_store as store_api
from . import skill_store_management as management
from . import skill_store_v2 as metadata


PROTOCOL = "skill-management/v1"
BASE_FIELDS = {"schema", "dataRootId", "generation", "registryHash"}
MAX_REQUEST_BYTES = 1024 * 1024


class SkillManagementError(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = str(code), int(status)
        super().__init__(self.code)

    def public_payload(self):
        return {"ok": False, "error": self.code, "errorCode": self.code,
                "protocol": PROTOCOL}


def _fail(code, status=409):
    raise SkillManagementError(code, status)


def _public_errors(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (store_api.SkillStoreError, revisions.SkillRevisionError,
                admission.SkillAdmissionError, skill_registry.SkillRegistryError) as exc:
            raise SkillManagementError(exc.code) from exc
        except (OSError, UnicodeError) as exc:
            raise SkillManagementError("management_material_unavailable") from exc
    return wrapped


def _shape(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        _fail("management_transport_invalid", 400)


def _protocol(value):
    if not isinstance(value, dict) or value.get("protocol") != PROTOCOL:
        _fail("management_protocol_required", 400)


def _base(registry):
    return {key: registry[key] for key in BASE_FIELDS}


def _validate_base(value, registry, *, current=False):
    _shape(value, BASE_FIELDS)
    if (value.get("schema") not in {store_api.REGISTRY_SCHEMA, metadata.REGISTRY_SCHEMA}
            or type(value.get("generation")) is not int or value["generation"] < 0
            or not isinstance(value.get("registryHash"), str)
            or not store_api._HASH.fullmatch(value["registryHash"])):
        _fail("management_base_invalid", 400)
    if value.get("dataRootId") != registry["dataRootId"]:
        _fail("management_root_mismatch")
    if current and value != _base(registry):
        _fail("registry_cas_conflict")


def _package(contents):
    files, canonical = [], {}
    for path, raw in sorted(contents.items()):
        if not isinstance(raw, bytes):
            _fail("management_package_invalid", 400)
        mode, payload = revisions._canonical_content(raw)
        canonical[path] = payload
        files.append({"path": path, "size": len(payload), "contentMode": mode,
                      "digest": revisions._digest(payload)})
    manifest = revisions.normalize_revision_manifest({"schema": revisions.REVISION_SCHEMA, "files": files})
    return management.CapturedPackage(manifest, tuple(sorted(canonical.items())))


def _document_name(document):
    if not isinstance(document, str) or len(document.encode("utf-8")) > skill_registry.MAX_SKILL_BYTES:
        _fail("management_document_invalid", 400)
    parsed = skill_registry.parse_skill_document(document)
    name = parsed["meta"].get("name")
    store_api._alias(name)
    return name


class SkillManagementService:
    def __init__(self, data_root, bundled_root, *, owner=None, admission_enabled=False,
                 server_instance_id="", catalog_loader=None):
        self.data_root, self.bundled_root = Path(data_root), Path(bundled_root)
        self.owner, self.admission_enabled = owner, bool(admission_enabled)
        self.server_instance_id = str(server_instance_id)
        self.store = store_api.SkillStore(self.data_root, self.bundled_root, write_enabled=True)
        self.reader = store_api.SkillStoreReader(self.data_root)
        self.catalog_loader = catalog_loader or (
            lambda: revisions.load_bundled_catalog(self.bundled_root / revisions.CATALOG_FILENAME)
        )

    def has_store(self):
        # lexists semantics: a broken link/invalid skeleton is not legacy mode.
        return revisions._path_kind(self.store.root) != "missing"

    def _registry(self):
        if not self.has_store():
            _fail("management_store_required")
        return self.reader.read_registry()

    def _writer(self):
        if not self.has_store():
            _fail("management_store_required")
        if not self.admission_enabled:
            _fail("management_read_only")
        return management.SkillStoreManager(self.store, owner=self.owner)

    @staticmethod
    def _installation(registry, iid):
        if not isinstance(iid, str) or not store_api._INSTALL_ID.fullmatch(iid):
            _fail("management_identity_invalid", 400)
        item = next((item for item in registry["installations"] if item["installationId"] == iid), None)
        if item is None:
            _fail("management_installation_missing", 404)
        return item

    def _object(self, registry, iid, revision_id=None):
        item = self._installation(registry, iid)
        revision_id = item["revisionId"] if revision_id is None else revision_id
        if revision_id not in item.get("retainedRevisionIds", [item["revisionId"]]):
            _fail("management_revision_not_retained", 404)
        return item, self.reader.read_pinned(registry["dataRootId"], revision_id)

    def snapshot(self):
        result = {"protocol": PROTOCOL, "serverInstanceId": self.server_instance_id,
                  "mode": "legacy", "registry": None, "installations": [], "bindings": [],
                  "admissionEnabled": self.admission_enabled, "errorCode": "",
                  "capabilities": {"read": False, "write": False, "convert": False}}
        try:
            if not self.has_store():
                return result
            with self.reader.management_view() as (registry, state, read_revision):
                managed = registry["schema"] == metadata.REGISTRY_SCHEMA
                writable = bool(self.admission_enabled and self.owner is not None and not self.owner.released)
                result.update(mode="managed-v2" if managed else "immutable-v1", registry=_base(registry),
                              bindings=copy.deepcopy(registry["bindings"]), transactionState=state["state"],
                              capabilities={"read": True, "write": writable and managed,
                                            "convert": writable and not managed})
                for item in registry["installations"]:
                    entry = copy.deepcopy(item)
                    binding = next((b for b in registry["bindings"]
                                    if any(c["installationId"] == item["installationId"] for c in b["candidates"])), None)
                    pinned = read_revision(item["revisionId"], paths={"SKILL.md"})
                    descriptor, _ = admission._descriptor({"routingAlias": item["displayName"], "object": pinned})
                    entry.update(description=descriptor["description"],
                                 enabled=item.get("enabled", True), uninstalled=item.get("uninstalled", False),
                                 retainedRevisionIds=item.get("retainedRevisionIds", [item["revisionId"]]),
                                 routingAlias=binding["routingAlias"] if binding else item["displayName"],
                                 selected=bool(binding and (binding.get("selectedInstallationId") or
                                               (binding.get("activeCandidate") or {}).get("installationId")) == item["installationId"]))
                    result["installations"].append(entry)
            return result
        except (store_api.SkillStoreError, revisions.SkillRevisionError, SkillManagementError, OSError) as exc:
            result.update(mode="unavailable", errorCode=getattr(exc, "code", "management_store_unavailable"),
                          registry=None, installations=[], bindings=[],
                          capabilities={"read": False, "write": False, "convert": False})
            return result

    @_public_errors
    def detail(self, iid, revision_id=None, *, data_root_id=None):
        if not self.has_store():
            _fail("management_store_required")
        with self.reader.management_view() as (registry, _, read_revision):
            if data_root_id is not None and data_root_id != registry["dataRootId"]:
                _fail("management_identity_required", 400)
            item = self._installation(registry, iid)
            revision_id = item["revisionId"] if revision_id is None else revision_id
            if revision_id not in item.get("retainedRevisionIds", [item["revisionId"]]):
                _fail("management_revision_not_retained", 404)
            pinned = read_revision(revision_id)
            files = {entry["path"]: entry for entry in pinned["files"]}
            document = files["SKILL.md"]["content"].decode("utf-8")
            name = _document_name(document)
            selection = {"routingAlias": name, "object": pinned}
            descriptor, body = admission._descriptor(selection)
            dependency = admission._dependency(selection, name)
            return {"protocol": PROTOCOL, "dataRootId": registry["dataRootId"], **copy.deepcopy(item),
                    "revisionId": pinned["revisionId"], "name": name, "document": document, "body": body,
                    "description": descriptor["description"], "keywords": descriptor["routingKeywords"],
                    "tools": descriptor["allowedTools"], "diagnostics": descriptor["diagnostics"],
                    "dependency": dependency,
                    "dependencyDocument": files["dependencies.json"]["content"].decode("utf-8") if "dependencies.json" in files else None,
                    "files": pinned["manifest"]["files"]}

    @_public_errors
    def resource(self, iid, revision_id, relative):
        normalized = revisions._normalize_relative(relative)
        if normalized != relative:
            _fail("management_resource_invalid", 400)
        registry = self._registry()
        _, pinned = self._object(registry, iid, revision_id)
        item = next((item for item in pinned["files"] if item["path"] == relative), None)
        if item is None or item["contentMode"] != "utf8-lf" or item["size"] > skill_registry.MAX_SKILL_BYTES:
            _fail("management_resource_unavailable", 404)
        if self._registry() != registry:
            _fail("registry_changed")
        return {"protocol": PROTOCOL, "dataRootId": registry["dataRootId"], "installationId": iid,
                "revisionId": revision_id, "path": relative, "content": item["content"].decode("utf-8")}

    def _material(self, source, request, registry, *, current=True):
        kind = request["kind"]
        if kind not in metadata.PACKAGE_KINDS:
            if source is not None:
                _fail("management_unexpected_package", 400)
            return None
        if kind == "update-bundled":
            _shape(source, {"type"})
            if source["type"] != "packaged-catalog":
                _fail("management_material_invalid", 400)
            catalog = revisions.normalize_bundled_catalog(self.catalog_loader())
            if catalog != request["catalog"]:
                _fail("management_catalog_changed")
            return management.capture_package(self.bundled_root / request["routingAlias"])
        if kind == "import-local":
            _shape(source, {"type", "sourceRoot"})
            path = source.get("sourceRoot")
            if source["type"] != "directory" or not isinstance(path, str) or not path or len(path) > 4096:
                _fail("management_material_invalid", 400)
            return management.capture_package(Path(path))
        fields = {"type", "document"}
        if kind in {"edit-local", "fork-bundled"}:
            fields |= {"installationId", "revisionId"}
        _shape(source, fields, {"dependencyDocument"})
        if source["type"] != "document":
            _fail("management_material_invalid", 400)
        name = _document_name(source["document"])
        contents, original_name = {}, name
        if kind in {"edit-local", "fork-bundled"}:
            if source["installationId"] != request["installationId"]:
                _fail("management_identity_invalid", 400)
            item, pinned = self._object(registry, source["installationId"], source["revisionId"])
            if current and item["revisionId"] != source["revisionId"]:
                _fail("management_base_revision_changed")
            contents = {entry["path"]: entry["content"] for entry in pinned["files"]}
            original_name = _document_name(contents["SKILL.md"].decode("utf-8"))
        contents["SKILL.md"] = source["document"].encode("utf-8")
        if "dependencyDocument" in source:
            value = source["dependencyDocument"]
            if value is None:
                contents.pop("dependencies.json", None)
            elif isinstance(value, str) and len(value.encode("utf-8")) <= 128 * 1024:
                contents["dependencies.json"] = value.encode("utf-8")
            else:
                _fail("management_dependency_document_invalid", 400)
        if name != original_name:
            for filename in ("dependencies.json", "evidence.json", "code-resources.json"):
                if filename in contents:
                    try:
                        sidecar = json.loads(contents[filename].decode("utf-8-sig"))
                    except (ValueError, UnicodeError) as exc:
                        raise SkillManagementError("management_package_contract_invalid") from exc
                    if isinstance(sidecar, dict) and sidecar.get("skill") == original_name:
                        sidecar["skill"] = name
                        contents[filename] = store_api._canonical(sidecar) + b"\n"
        return _package(contents)

    @_public_errors
    def preview(self, payload):
        _protocol(payload)
        kind = payload.get("kind")
        if not isinstance(kind, str) or kind not in metadata.KINDS:
            _fail("management_request_invalid", 400)
        fields = {"protocol", "base", "kind"}
        optional = set()
        if kind not in {"convert-v2", "create-local", "import-local", "migrate-preferences"}:
            fields.add("installationId")
        if kind in metadata.PACKAGE_KINDS - {"update-bundled"}:
            optional.add("routingAlias")
            optional.add("conflict")
        if kind in {"create-local", "edit-local", "fork-bundled"}:
            fields.add("document")
            optional.add("dependencyDocument")
        if kind in {"edit-local", "fork-bundled"}:
            fields.add("revisionId")
        if kind == "import-local":
            fields.add("sourceRoot")
        if kind == "rollback":
            fields.add("revisionId")
            optional.add("conflict")
        if kind == "set-enabled":
            fields.add("enabled")
        if kind == "select-candidate":
            fields.add("routingAlias")
        if kind == "migrate-preferences":
            fields |= {"disabledNames", "confirmed"}
        _shape(payload, fields, optional)
        self._writer()
        registry = self._registry()
        _validate_base(payload["base"], registry, current=True)
        request = {"kind": kind}
        for key in ("installationId", "routingAlias", "enabled", "disabledNames", "confirmed"):
            if key in payload:
                request[key] = payload[key]
        source = None
        if kind in {"create-local", "edit-local", "fork-bundled"}:
            request.setdefault("routingAlias", _document_name(payload["document"]))
            source = {"type": "document", "document": payload["document"]}
            if kind != "create-local":
                source.update(installationId=payload["installationId"], revisionId=payload["revisionId"])
            if "dependencyDocument" in payload:
                source["dependencyDocument"] = payload["dependencyDocument"]
        elif kind == "import-local":
            source = {"type": "directory", "sourceRoot": payload["sourceRoot"]}
        elif kind == "update-bundled":
            item = self._installation(registry, payload["installationId"])
            catalog = revisions.normalize_bundled_catalog(self.catalog_loader())
            target = next((entry for entry in catalog["skills"] if entry["skillId"] == item["skillId"]), None)
            if target is None:
                _fail("management_catalog_identity_mismatch")
            request.update(catalog=catalog, routingAlias=target["directory"], revisionId=target["revisionId"])
            source = {"type": "packaged-catalog"}
        elif kind == "rollback":
            _, pinned = self._object(registry, payload["installationId"], payload["revisionId"])
            raw = next(entry["content"] for entry in pinned["files"] if entry["path"] == "SKILL.md")
            request.update(revisionId=payload["revisionId"], routingAlias=_document_name(raw.decode("utf-8")))
        if kind in metadata.PACKAGE_KINDS | {"rollback"}:
            request["conflict"] = payload.get("conflict", "reject")
        if source is not None:
            captured = self._material(source, request, registry)
            if kind == "import-local" and "routingAlias" not in request:
                request["routingAlias"] = _document_name(dict(captured.files)["SKILL.md"].decode("utf-8"))
            if kind != "update-bundled":
                request["revisionId"] = captured.manifest["revisionId"]
            management._checked_package(captured, request)
        request = metadata.normalize_request(request)
        op_id = metadata.operation_id(registry["dataRootId"], store_api._digest(
            b"preview:" + store_api._canonical(request) + registry["registryHash"].encode()))
        target = metadata.make_target(registry, request, op_id)
        if self._registry() != registry:
            _fail("registry_changed")
        return {"protocol": PROTOCOL, "base": _base(registry), "request": request, "material": source,
                "confirmationRequired": kind in {"convert-v2", "migrate-preferences"},
                "targetGeneration": target["generation"]}

    @_public_errors
    def receipt(self, operation_key):
        registry = self._registry()
        key_hash = management.SkillStoreManager._key(operation_key)
        op_id = metadata.operation_id(registry["dataRootId"], key_hash)
        receipt = management.SkillStoreManager._receipt(registry, op_id)
        if receipt is None:
            _fail("management_receipt_missing", 404)
        return {"protocol": PROTOCOL, "receipt": receipt}

    @_public_errors
    def apply(self, payload):
        _protocol(payload)
        _shape(payload, {"protocol", "operationKey", "base", "request"}, {"material", "confirmed"})
        request = metadata.normalize_request(payload["request"])
        manager = self._writer()
        registry, journals, _ = manager._view()
        if not isinstance(payload["base"], dict) or payload["base"].get("dataRootId") != registry["dataRootId"]:
            _fail("management_root_mismatch")
        key_hash = manager._key(payload["operationKey"])
        op_id = metadata.operation_id(registry["dataRootId"], key_hash)
        receipt = manager._receipt(registry, op_id)
        pending = next((entry for entry in journals if entry["operationId"] == op_id), None)
        frozen = receipt or pending
        if frozen and frozen["requestHash"] != store_api._digest(store_api._canonical(request)):
            _fail("management_operation_key_conflict")
        if frozen is None:
            _validate_base(payload["base"], registry, current=True)
        operation_base = pending["baseRegistry"] if pending is not None else registry if receipt is not None else payload["base"]
        options = {"base_generation": operation_base["generation"],
                   "base_registry_hash": operation_base["registryHash"]}
        if receipt is not None:
            # Let the engine finish an interrupted receipt/journal boundary;
            # never rebuild source material or check a newer catalog first.
            receipt = manager.apply(payload["operationKey"], request, **options)
        else:
            if request["kind"] in {"convert-v2", "migrate-preferences"} and payload.get("confirmed") is not True:
                _fail("management_confirmation_required")
            if pending is None:
                _validate_base(payload["base"], registry, current=True)
            if pending is not None:
                try:
                    receipt = manager.apply(payload["operationKey"], request, **options)
                except store_api.SkillStoreError as exc:
                    if exc.code != "management_capture_required":
                        raise
            if receipt is None:
                material = self._material(payload.get("material"), request, registry, current=pending is None)
                receipt = manager.apply(payload["operationKey"], request, package=material, **options)
        return {"protocol": PROTOCOL, "receipt": receipt, "snapshot": self.snapshot()}
