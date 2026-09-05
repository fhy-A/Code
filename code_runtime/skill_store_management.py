"""Explicit profile-owned Skill transactions. No API, source discovery, or GC.

The registry replacement is the sole commit point. Journaled requests and
receipts remain immutable across later generations; only captured package bytes
may drive late recovery. Published objects are never removed here.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import os
from pathlib import Path
import re

from . import data_dir_owner
from . import skill_admission
from . import skill_revisions as revisions
from . import skill_store as legacy
from . import skill_store_v2 as metadata


@dataclass(frozen=True)
class CapturedPackage:
    manifest: dict
    files: tuple


def capture_package(root):
    """Capture only the explicitly supplied root, without writing anything."""
    for _, path in revisions._walk_package_files(Path(root)):
        legacy._safe_file(path)
    manifest, contents = revisions.read_skill_revision(Path(root))
    for _, path in revisions._walk_package_files(Path(root)):
        legacy._safe_file(path)
    return CapturedPackage(copy.deepcopy(manifest), tuple(sorted(contents.items())))


def _checked_package(value, request):
    captured = value if isinstance(value, CapturedPackage) else capture_package(value)
    try:
        manifest = revisions.normalize_revision_manifest(captured.manifest)
    except (KeyError, TypeError, ValueError) as exc:
        raise legacy.SkillStoreError("management_package_invalid") from exc
    if manifest != captured.manifest or manifest["revisionId"] != request["revisionId"]:
        legacy._fail("management_source_changed")
    if not isinstance(captured.files, tuple) or len(captured.files) != len(manifest["files"]):
        legacy._fail("management_package_invalid")
    contents = {}
    for pair in captured.files:
        if not isinstance(pair, tuple) or len(pair) != 2 or not isinstance(pair[0], str) or not isinstance(pair[1], bytes):
            legacy._fail("management_package_invalid")
        if pair[0] in contents:
            legacy._fail("management_package_invalid")
        contents[pair[0]] = pair[1]
    if set(contents) != {item["path"] for item in manifest["files"]}:
        legacy._fail("management_package_invalid")
    files = []
    for item in manifest["files"]:
        payload = contents[item["path"]]
        mode, canonical = revisions._canonical_content(payload)
        if (payload != canonical or len(payload) != item["size"] or mode != item["contentMode"]
                or revisions._digest(payload) != item["digest"]):
            legacy._fail("management_package_invalid")
        files.append({**item, "content": payload})
    selection = {"routingAlias": request["routingAlias"], "object": {"files": files}}
    descriptor, body = skill_admission._descriptor(selection)
    if (not body or descriptor.get("name") != request["routingAlias"]
            or any(item.get("severity") == "error" for item in descriptor["diagnostics"])):
        legacy._fail("management_package_identity_invalid")
    try:
        if skill_admission._evidence(selection, descriptor["name"])["state"] == "invalid":
            legacy._fail("management_package_contract_invalid")
        skill_admission._dependency(selection, descriptor["name"])
        skill_admission._resources(selection, descriptor["name"])
    except skill_admission.SkillAdmissionError as exc:
        raise legacy.SkillStoreError("management_package_contract_invalid") from exc
    return manifest, contents


def _stage_check(store, journal, *, cleanup=False, contents=None):
    """Identify only this journal's staging; unknown data is never cleaned."""
    root = store.root / "staging" / journal["operationId"]
    if not root.exists():
        return
    legacy._safe_dir(root)
    if {item.name for item in root.iterdir()} - {"objects"}:
        legacy._fail("staging_unknown")
    objects = root / "objects"
    if not objects.exists():
        return
    legacy._safe_dir(objects)
    if {item.name for item in objects.iterdir()} - {"sha256"}:
        legacy._fail("staging_unknown")
    hashes = objects / "sha256"
    if not hashes.exists():
        return
    legacy._safe_dir(hashes)
    manifests = {item["revisionId"]: item for item in journal["objectManifests"]}
    for prefix in hashes.iterdir():
        legacy._safe_dir(prefix)
        if not re.fullmatch(r"[0-9a-f]{2}", prefix.name):
            legacy._fail("staging_unknown")
        for directory in prefix.iterdir():
            legacy._safe_dir(directory)
            rev = "sha256:" + directory.name
            if rev not in manifests or not directory.name.startswith(prefix.name):
                legacy._fail("staging_unknown")
            manifest = manifests[rev]
            if {item.name for item in directory.iterdir()} - {"manifest.json", "content"}:
                legacy._fail("staging_unknown")
            document = directory / "manifest.json"
            if document.exists():
                legacy._safe_file(document)
                payload = revisions._stable_file(document)
                if not (legacy._canonical(manifest) + b"\n").startswith(payload):
                    legacy._fail("staging_unknown")
            content = directory / "content"
            if not content.exists():
                continue
            legacy._safe_dir(content)
            expected = {item["path"]: item for item in manifest["files"]}
            expected_dirs = {parent.as_posix() for name in expected
                             for parent in Path(name).parents if parent.as_posix() != "."}
            pending = [content]
            while pending:
                for item in pending.pop().iterdir():
                    relative = item.relative_to(content).as_posix()
                    if revisions._path_kind(item) == "directory" and relative in expected_dirs:
                        legacy._safe_dir(item)
                        pending.append(item)
                        continue
                    if relative not in expected:
                        legacy._fail("staging_unknown")
                    legacy._safe_file(item)
                    payload = revisions._stable_file(item)
                    entry = expected[relative]
                    if len(payload) == entry["size"]:
                        if revisions._digest(payload) != entry["digest"]:
                            legacy._fail("staging_unknown")
                    elif len(payload) > entry["size"] or cleanup and (
                        contents is None or not contents[relative].startswith(payload)
                    ):
                        legacy._fail("staging_unknown")


def inspect_managed_state(store, journals, object_ids):
    """Read-only lineage/eligibility check, including interrupted conversion."""
    originals = [item for item in journals if item["schema"] == legacy.TRANSACTION_SCHEMA]
    changes = [item for item in journals if item["schema"] == metadata.TRANSACTION_SCHEMA]
    if len(originals) != 1 or originals[0]["phase"] != "committed" or not changes:
        legacy._fail("management_lineage_invalid")
    current = originals[0]["targetRegistry"]
    root = store._load_root()
    if root is None or root["dataRootId"] != current["dataRootId"]:
        legacy._fail("registry_root_mismatch")
    known = {current["registryHash"]: current}
    eligible = metadata.retained_ids(current)
    active = None
    changes.sort(key=lambda item: (item["baseRegistry"]["generation"], item["phase"] != "aborted", item["operationId"]))
    for journal in changes:
        base, target = journal["baseRegistry"], journal["targetRegistry"]
        if base != known.get(base["registryHash"]) or journal["dataRootId"] != root["dataRootId"]:
            legacy._fail("management_lineage_invalid")
        eligible.update(item["revisionId"] for item in journal["objectManifests"])
        if journal["phase"] == "aborted":
            continue
        if base != current or active is not None:
            legacy._fail("management_lineage_invalid")
        if journal["phase"] == "committed":
            current = target
            known[current["registryHash"]] = current
            eligible.update(metadata.retained_ids(current))
        else:
            active = journal
    actual = store._load_registry(verify_objects=False)
    if actual != current:
        if (active is None or actual != active["targetRegistry"]
                or metadata.PHASES.index(active["phase"]) < metadata.PHASES.index("objects-published")):
            legacy._fail("registry_cas_conflict")
    elif active is not None and active["phase"] == "registry-published":
        legacy._fail("management_committed_registry_missing")
    if object_ids - eligible:
        legacy._fail("store_object_unknown")
    if metadata.retained_ids(actual) - object_ids:
        legacy._fail("object_missing")
    by_operation = {item["operationId"]: item for item in changes}
    for staged in (store.root / "staging").iterdir():
        if staged.name not in by_operation:
            legacy._fail("staging_unknown")
        _stage_check(store, by_operation[staged.name])
    if active is not None:
        return {"state": "recoverable", "management": True,
                "operationId": active["operationId"], "phase": active["phase"]}
    return {"state": "committed", "management": True, "dataRootId": root["dataRootId"],
            "generation": actual["generation"], "registryHash": actual["registryHash"]}


class SkillStoreManager:
    """Internal engine: explicit owner, operation key, frozen request, and CAS."""

    def __init__(self, store, *, owner):
        if not isinstance(store, legacy.SkillStore):
            raise TypeError("store must be a SkillStore")
        self.store, self.owner = store, owner
        self._check_owner()

    def _check_owner(self):
        if not isinstance(self.owner, data_dir_owner.DataDirOwner) or self.owner.released:
            legacy._fail("management_owner_required")
        legacy._safe_dir(self.store.data_root)
        if os.path.normcase(str(self.owner.data_dir.resolve())) != os.path.normcase(str(self.store.data_root.resolve())):
            legacy._fail("management_owner_mismatch")
        if not self.store.write_enabled:
            legacy._fail("store_writes_disabled")

    def _view(self):
        objects = self.store._inspect_layout()
        journals = self.store._journals()
        if self.store._uses_management():
            inspect_managed_state(self.store, journals, objects)
        else:
            state = self.store.inspect_startup_state()
            if state["state"] != "committed":
                legacy._fail("management_v1_store_required")
        return self.store._load_registry(), journals, objects

    @staticmethod
    def _key(key):
        if not isinstance(key, str) or not metadata.OP_KEY.fullmatch(key):
            legacy._fail("management_operation_key_invalid")
        return legacy._digest(key.encode("utf-8"))

    @staticmethod
    def _receipt(registry, op_id):
        return next((copy.deepcopy(item) for item in registry["operationReceipts"]
                     if item["operationId"] == op_id), None)

    def _close_v1(self, catalog_loader):
        """Only an explicit conversion may finish an existing bootstrap first."""
        if self.store._uses_management():
            return
        self.store._inspect_layout()
        journals = self.store._journals()
        if len(journals) != 1 or journals[0]["phase"] == "committed":
            return
        if legacy._PHASES.index(journals[0]["phase"]) >= legacy._PHASES.index("staged-verified"):
            with self.store._mutation_lock():
                self._check_owner()
                journals = self.store._journals()
                self.store._clean_temps({item["operationId"] for item in journals})
                self.store._recover_captured(journals[0], self.store._load_root(), self.store._load_registry())
        elif callable(catalog_loader):
            self.store.bootstrap_from_catalog_loader(catalog_loader)
        else:
            legacy._fail("management_bootstrap_source_required")

    def apply(self, operation_key, request, *, base_generation, base_registry_hash,
              package=None, catalog_loader=None):
        self._check_owner()
        request = metadata.normalize_request(request)
        key_hash = self._key(operation_key)
        if request["kind"] == "convert-v2":
            self._close_v1(catalog_loader)
        if not self.store.root.exists():
            legacy._fail("management_v1_store_required")
        with self.store._mutation_lock():
            self._check_owner()
            registry, journals, objects = self._view()
            op_id = metadata.operation_id(registry["dataRootId"], key_hash)
            request_hash = legacy._digest(legacy._canonical(request))
            matching = next((j for j in journals if j["operationId"] == op_id), None)
            receipt = self._receipt(registry, op_id)
            # Lookup precedes CAS, package/source IO, and any new-operation work.
            if receipt is not None or matching is not None:
                frozen = receipt or matching
                if frozen["requestHash"] != request_hash:
                    legacy._fail("management_operation_key_conflict")
                if matching is not None and matching["phase"] == "aborted":
                    legacy._fail("management_operation_aborted")
                if receipt is not None:
                    if matching["phase"] != "committed":
                        self._resume(matching)
                    self._cleanup_terminal(self.store._journals())
                    return receipt
                return self._resume(matching, package=package)
            if any(j["phase"] not in metadata.TERMINAL for j in journals):
                legacy._fail("store_transaction_conflict")
            if (type(base_generation) is not int or registry["generation"] != base_generation
                    or registry["registryHash"] != base_registry_hash):
                legacy._fail("registry_cas_conflict")
            target = metadata.make_target(registry, request, op_id)
            material = None
            if request["kind"] in metadata.PACKAGE_KINDS:
                if package is None:
                    legacy._fail("management_capture_required")
                material = _checked_package(package, request)
            elif package is not None:
                legacy._fail("management_unexpected_package")
            elif request["kind"] == "rollback":
                pinned = legacy.SkillStoreReader(self.store.data_root)._read_pinned_from_root(
                    self.store._load_root(), request["revisionId"],
                )
                material_check = CapturedPackage(pinned["manifest"], tuple(
                    (entry["path"], entry["content"]) for entry in pinned["files"]
                ))
                _checked_package(material_check, request)
            journal = {"schema": metadata.TRANSACTION_SCHEMA, "operationId": op_id,
                       "operationKeyHash": key_hash, "request": request, "requestHash": request_hash,
                       "phase": "prepared", "journalGeneration": 0, "dataRootId": registry["dataRootId"],
                       "baseRegistry": registry, "targetRegistry": target,
                       "objectManifests": [material[0]] if material is not None else []}
            self._capacity(journal, journals, objects)
            self._claim_prepared_temps(journal)
            self._cleanup_terminal(journals)
            self.store._hit("after-management-preflight")
            journal = self.store._write_journal(journal)
            return self._resume(journal, material=material)

    def _claim_prepared_temps(self, journal):
        """Only an explicit exact retry may discard an unpublished prepare."""
        op_id = journal["operationId"]
        owned = []
        for path in (self.store.root / "transactions").glob(f".{op_id}.json.{op_id}.*.tmp"):
            if not legacy._TEMP.fullmatch(path.name):
                legacy._fail("store_temp_unknown")
            raw, value = self.store._load_json(path, legacy.MAX_JOURNAL_BYTES, "store_temp_unknown")
            if metadata.normalize_journal(value) != journal or raw != legacy._canonical(journal) + b"\n":
                legacy._fail("store_temp_unknown")
            owned.append(path)
        for path in owned:
            path.unlink()

    def _capacity(self, journal, journals, objects):
        if len(journals) >= legacy.MAX_TRANSACTIONS:
            legacy._fail("store_transaction_limit")
        incoming = {item["revisionId"] for item in journal["objectManifests"]}
        if len(objects | incoming) > legacy.MAX_OBJECTS:
            legacy._fail("store_object_limit")
        size = sum(item["summary"]["totalSize"] for item in journal["objectManifests"]
                   if item["revisionId"] not in objects)
        if size > legacy.MAX_NEW_OBJECT_BYTES:
            legacy._fail("store_new_bytes_limit")
        registry_size = len(legacy._canonical(journal["targetRegistry"])) + 1
        journal_size = len(legacy._canonical(journal)) + 1
        if registry_size > legacy.MAX_REGISTRY_BYTES:
            legacy._fail("registry_size_limit")
        if journal_size > legacy.MAX_JOURNAL_BYTES:
            legacy._fail("journal_size_limit")
        # Include an atomic-replacement journal and registry, not only file bytes.
        if legacy._safe_tree_bytes(self.store.root) + size + 2 * journal_size + registry_size > legacy.MAX_STORE_BYTES:
            legacy._fail("store_size_limit")

    def _stage_package(self, journal, manifest, contents):
        rev, op_id = manifest["revisionId"], journal["operationId"]
        final = self.store._object_path(rev)
        if final.exists():
            self.store._verify_object(final, rev)
            return
        target = self.store._object_path(rev, staging=op_id)
        if target.exists():
            try:
                self.store._verify_object(target, rev)
                return
            except legacy.SkillStoreError:
                _stage_check(self.store, journal, cleanup=True, contents=contents)
                legacy._remove_safe_tree(target)
        content = target / "content"
        content.mkdir(parents=True)
        for relative, payload in contents.items():
            path = content / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            self.store._hit("after-staging-file")
        with open(target / "manifest.json", "xb") as stream:
            stream.write(legacy._canonical(manifest) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.store._verify_object(target, rev)
        self.store._hit("after-management-capture")

    def _resume(self, journal, *, package=None, material=None):
        if journal["phase"] in metadata.TERMINAL:
            legacy._fail("management_operation_aborted" if journal["phase"] == "aborted" else "management_already_committed")
        op_id = journal["operationId"]
        current = self.store._load_registry()
        target, base = journal["targetRegistry"], journal["baseRegistry"]
        if current not in (base, target):
            legacy._fail("registry_cas_conflict")
        if journal["phase"] == "prepared":
            for manifest in journal["objectManifests"]:
                rev = manifest["revisionId"]
                final, staged = self.store._object_path(rev), self.store._object_path(rev, staging=op_id)
                if final.exists():
                    self.store._verify_object(final, rev)
                    continue
                try:
                    self.store._verify_object(staged, rev)
                    continue
                except legacy.SkillStoreError:
                    if material is None and package is not None:
                        material = _checked_package(package, journal["request"])
                    if material is None:
                        legacy._fail("management_capture_required")
                    if material[0] != manifest:
                        legacy._fail("management_source_changed")
                    self._stage_package(journal, *material)
            journal = self.store._write_journal(journal, "captured")
        if journal["phase"] == "captured":
            for manifest in journal["objectManifests"]:
                self.store._publish_object(op_id, manifest["revisionId"])
            journal = self.store._write_journal(journal, "objects-published")
        for rev in metadata.retained_ids(target):
            self.store._verify_object(self.store._object_path(rev), rev)
        if current == base:
            if journal["phase"] != "objects-published":
                legacy._fail("management_committed_registry_missing")
            if self.store._load_registry() != base:
                legacy._fail("registry_cas_conflict")
            self.store._atomic_json(self.store.root / "registry.json", target, op_id, "managed-registry")
        if self.store._load_registry() != target:
            legacy._fail("registry_cas_conflict")
        if journal["phase"] == "objects-published":
            journal = self.store._write_journal(journal, "registry-published")
        journal = self.store._write_journal(journal, "committed")
        self.store._hit("after-management-receipt")
        self._cleanup_terminal(self.store._journals())
        self.store._hit("after-management-cleanup")
        return self._receipt(target, op_id)

    def _cleanup_terminal(self, journals, *, contents=None):
        for journal in journals:
            if journal["schema"] != metadata.TRANSACTION_SCHEMA or journal["phase"] not in metadata.TERMINAL:
                continue
            path = self.store.root / "staging" / journal["operationId"]
            if path.exists():
                _stage_check(self.store, journal, cleanup=True, contents=contents)
                legacy._remove_safe_tree(path)
        self._clean_temps(journals)

    def _clean_temps(self, journals):
        by_id = {item["operationId"]: item for item in journals}
        owned = []
        for directory in (self.store.root, self.store.root / "transactions"):
            for path in directory.iterdir():
                match = legacy._TEMP.fullmatch(path.name)
                if match is None:
                    continue
                journal = by_id.get(match.group(1))
                if journal is None:
                    legacy._fail("store_temp_unknown")
                if journal["schema"] == legacy.TRANSACTION_SCHEMA:
                    continue
                raw, value = self.store._load_json(path, legacy.MAX_JOURNAL_BYTES, "store_temp_unknown")
                if directory == self.store.root and path.name.startswith(".registry.json."):
                    expected = journal["targetRegistry"]
                elif directory.name == "transactions" and path.name.startswith(f".{journal['operationId']}.json."):
                    normalized = metadata.normalize_journal(value)
                    expected = {**journal, "phase": normalized["phase"],
                                "journalGeneration": normalized["journalGeneration"]}
                else:
                    legacy._fail("store_temp_unknown")
                if value != expected or raw != legacy._canonical(expected) + b"\n":
                    legacy._fail("store_temp_unknown")
                owned.append(path)
        for path in owned:
            path.unlink()
        self.store._clean_temps(set(by_id))

    def recover(self, *, package=None):
        """Recover v2 only. Never discover sources or initiate v1 conversion."""
        self._check_owner()
        if not self.store._uses_management():
            legacy._fail("management_conversion_required")
        with self.store._mutation_lock():
            self._check_owner()
            registry, journals, _ = self._view()
            active = next((item for item in journals if item["phase"] not in metadata.TERMINAL), None)
            if active is not None:
                return self._resume(active, package=package)
            self._cleanup_terminal(journals)
            return {"state": "committed", "generation": registry["generation"]}

    def abort(self, operation_key, *, package=None):
        """Abort before registry publication; retain every published object."""
        self._check_owner()
        key_hash = self._key(operation_key)
        with self.store._mutation_lock():
            self._check_owner()
            registry, journals, _ = self._view()
            op_id = metadata.operation_id(registry["dataRootId"], key_hash)
            journal = next((item for item in journals if item["operationId"] == op_id), None)
            if journal is None:
                legacy._fail("management_operation_missing")
            if self._receipt(registry, op_id) is not None or journal["phase"] == "committed":
                legacy._fail("management_already_committed")
            contents = _checked_package(package, journal["request"])[1] if package is not None else None
            _stage_check(self.store, journal, cleanup=True, contents=contents)
            if journal["phase"] != "aborted":
                self.store._write_journal(journal, "aborted")
            self._cleanup_terminal(self.store._journals(), contents=contents)
            return {"operationId": op_id, "state": "aborted", "requestHash": journal["requestHash"]}
