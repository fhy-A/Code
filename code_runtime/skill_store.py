"""Default-off immutable Skill storage for isolated Stage 4B bootstrap tests."""
from __future__ import annotations
from contextlib import contextmanager
import hashlib, json
import os, re
from pathlib import Path
import shutil, stat
import threading
import time
import unicodedata
import uuid
from . import skill_revisions as revisions
ROOT_SCHEMA, REGISTRY_SCHEMA = "code-skill-data-root/v1", "code-skill-install-registry/v1"
TRANSACTION_SCHEMA, STORE_DIRECTORY = "code-skill-store-transaction/v1", "skill-store-v1"
MAX_ROOT_BYTES, MAX_REGISTRY_BYTES = 4 * 1024, 4 * 1024**2
MAX_JOURNAL_BYTES, MAX_MANIFEST_BYTES = 6 * 1024**2, 8 * 1024**2
MAX_INSTALLATIONS, MAX_BINDINGS = 512, 512
MAX_OBSERVATIONS, MAX_TOMBSTONES, MAX_RECEIPTS = 1024, 256, 512
MAX_OBJECTS, MAX_TRANSACTIONS = 1024, 512
MAX_NEW_OBJECT_BYTES, MAX_STORE_BYTES = 1024**3, 8 * 1024**3
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ROOT_ID = re.compile(r"dr1_[0-9a-f]{32}\Z")
_INSTALL_ID = re.compile(r"si1_[0-9a-f]{32}\Z")
_LOCAL_ID = re.compile(r"local\.skill/[0-9a-f]{32}\Z")
_BUNDLE_ID = re.compile(r"code\.bundle/[a-z0-9][a-z0-9._-]{0,127}\Z")
_OP_ID = re.compile(r"op1_[0-9a-f]{64}\Z")
_OPAQUE = re.compile(r"~invalid-[0-9a-f]{16}\Z")
_TEMP = re.compile(r"^\.(?:root\.json|registry\.json|op1_[0-9a-f]{64}\.json)\.(op1_[0-9a-f]{64})\.[0-9a-f]{32}\.tmp\Z")
_PHASES = ("prepared", "root-bound", "copying", "staged-verified", "objects-published", "registry-published", "committed")
_BINDING_REASONS = {"source-invalid", "shared-development-unconfirmed", "same-name-modified", "tombstone-conflict", "bundled-tombstoned", "legacy-root-missing", "legacy-bundled-missing", "unmatched-legacy-tombstone"}
_OBSERVATION_ERRORS = {"invalid": "source-invalid", "unsafe": "source-unsafe", "unreadable": "source-unreadable"}
_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}
class SkillStoreError(RuntimeError):
    def __init__(self, code, message="Skill store operation failed"):
        self.code = str(code); super().__init__(message)
class SkillStoreInterruption(RuntimeError):
    """Test-only process-crash analogue raised by a supplied fault injector."""
def _fail(code, message="Skill store operation failed"):
    raise SkillStoreError(code, message)
def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
def _digest(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()
def _exact(value, fields, code):
    if not isinstance(value, dict) or set(value) != set(fields): _fail(code)
def _bounded_list(value, limit, code):
    if not isinstance(value, list) or len(value) > limit: _fail(code)
    return value
def _safe_dir(path):
    if revisions._path_kind(path) != "directory": _fail("store_path_unsafe")
def _safe_file(path):
    if revisions._path_kind(path) != "file": _fail("store_path_unsafe")
    try:
        if int(getattr(os.lstat(path), "st_nlink", 1)) != 1: _fail("store_path_unsafe")
    except OSError as exc: raise SkillStoreError("store_path_unreadable") from exc
def _safe_tree_bytes(root):
    total, pending = 0, [Path(root)]
    while pending:
        current = pending.pop(); _safe_dir(current)
        for item in current.iterdir():
            kind = revisions._path_kind(item)
            if kind == "directory": pending.append(item)
            elif kind == "file": _safe_file(item); total += os.lstat(item).st_size
            else: _fail("store_path_unsafe")
            if total > MAX_STORE_BYTES: _fail("store_size_limit")
    return total
def _remove_safe_tree(path):
    _safe_tree_bytes(path); shutil.rmtree(path)
def _thread_lock(path):
    key = os.path.normcase(str(Path(path).resolve(strict=False)))
    with _LOCKS_GUARD: return _THREAD_LOCKS.setdefault(key, threading.RLock())
def _alias(value):
    try: return revisions._normalize_directory(value)
    except revisions.SkillRevisionError as exc: raise SkillStoreError("registry_alias_invalid") from exc
def _display(value):
    if not isinstance(value, str) or not value or unicodedata.normalize("NFC", value) != value or len(value.encode("utf-8")) > 256 or any(ord(char) < 0x20 for char in value):
        _fail("registry_display_name_invalid")
    return value
def _state_hash(registry):
    keys = ("schema", "dataRootId", "generation", "installations", "bindings", "bundledTombstones", "sourceObservations")
    return _digest(_canonical({key: registry[key] for key in keys}))
def _registry_hash(registry):
    return _digest(_canonical({key: value for key, value in registry.items() if key != "registryHash"}))
def _operation_id(root_id, request_hash):
    return "op1_" + hashlib.sha256(_canonical(["bootstrap-v1", root_id, request_hash])).hexdigest()
def _normalize_hints(value):
    if value is None: return {}
    if not isinstance(value, dict) or len(value) > revisions.MAX_SKILLS: _fail("identity_hints_invalid")
    result, used = {}, set()
    for raw_name, hint in value.items():
        name = _alias(raw_name); _exact(hint, {"skillId", "installationId"}, "identity_hints_invalid")
        sid, iid = hint["skillId"], hint["installationId"]
        if not _LOCAL_ID.fullmatch(str(sid)) or not _INSTALL_ID.fullmatch(str(iid)) or sid in used or iid in used: _fail("identity_hints_invalid")
        used.update((sid, iid)); result[name] = {"skillId": sid, "installationId": iid}
    return dict(sorted(result.items()))
def _observation(source_kind, root_kind, directory, state, revision_id, catalog_hash, error_code):
    if directory.startswith("~invalid-"):
        if not _OPAQUE.fullmatch(directory): _fail("observation_locator_invalid")
    else: _alias(directory)
    base = {"sourceKind": source_kind, "locator": {"rootKind": root_kind, "directoryToken": directory}, "state": state, "revisionId": revision_id, "catalogHash": catalog_hash, "errorCode": error_code}
    return {"sourceObservationId": "so1_" + hashlib.sha256(_canonical(base)).hexdigest(), **base}
def normalize_registry(value):
    top = {"schema", "dataRootId", "generation", "installations", "bindings", "bundledTombstones", "sourceObservations", "operationReceipts", "registryHash"}
    _exact(value, top, "registry_invalid")
    if value.get("schema") != REGISTRY_SCHEMA or not _ROOT_ID.fullmatch(str(value.get("dataRootId"))): _fail("registry_invalid")
    generation = value.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or not 0 <= generation <= 2**53 - 1: _fail("registry_generation_invalid")
    observations, observation_ids = [], set()
    for item in _bounded_list(value.get("sourceObservations"), MAX_OBSERVATIONS, "registry_observations_invalid"):
        fields = {"sourceObservationId", "sourceKind", "locator", "state", "revisionId", "catalogHash", "errorCode"}
        _exact(item, fields, "registry_observations_invalid"); _exact(item["locator"], {"rootKind", "directoryToken"}, "registry_observations_invalid")
        if item["sourceKind"] not in {"bundled-catalog", "legacy-installed", "workspace-development"} or item["locator"]["rootKind"] not in {"bundled", "legacy", "shared"}: _fail("registry_observations_invalid")
        expected = _observation(item["sourceKind"], item["locator"]["rootKind"], item["locator"]["directoryToken"], item["state"], item["revisionId"], item["catalogHash"], item["errorCode"])
        if item != expected or item["sourceObservationId"] in observation_ids: _fail("registry_observations_invalid")
        state, error = item["state"], item["errorCode"]
        if state == "ready":
            if not _HASH.fullmatch(str(item["revisionId"])) or error is not None: _fail("registry_observations_invalid")
        elif state == "missing":
            if item["revisionId"] is not None or error is not None: _fail("registry_observations_invalid")
        elif state in _OBSERVATION_ERRORS:
            if item["revisionId"] is not None or error != _OBSERVATION_ERRORS[state]: _fail("registry_observations_invalid")
        else: _fail("registry_observations_invalid")
        if item["catalogHash"] is not None and not _HASH.fullmatch(str(item["catalogHash"])): _fail("registry_observations_invalid")
        observation_ids.add(item["sourceObservationId"]); observations.append(item)
    if observations != sorted(observations, key=lambda item: item["sourceObservationId"]): _fail("registry_not_canonical")
    installations, installation_ids, skill_ids = [], set(), set()
    for item in _bounded_list(value.get("installations"), MAX_INSTALLATIONS, "registry_installations_invalid"):
        fields = {"installationId", "skillId", "kind", "displayName", "revisionId", "sourceState", "sourceObservationIds"}
        _exact(item, fields, "registry_installations_invalid"); iid, sid, sources = str(item["installationId"]), str(item["skillId"]), item["sourceObservationIds"]
        bad = (not _INSTALL_ID.fullmatch(iid) or iid in installation_ids or sid in skill_ids or item["kind"] not in {"bundled", "local"}
               or not (_BUNDLE_ID.fullmatch(sid) if item["kind"] == "bundled" else _LOCAL_ID.fullmatch(sid)) or not _HASH.fullmatch(str(item["revisionId"]))
               or item["sourceState"] not in {"present", "catalog-only", "source-missing"} or not isinstance(sources, list)
               or not 1 <= len(sources) <= 2 or sources != sorted(set(sources)) or not set(sources) <= observation_ids)
        if bad: _fail("registry_installations_invalid")
        _display(item["displayName"]); installation_ids.add(iid); skill_ids.add(sid); installations.append(item)
    if installations != sorted(installations, key=lambda item: item["installationId"]): _fail("registry_not_canonical")
    by_install = {item["installationId"]: item for item in installations}
    bindings, aliases, candidate_count = [], set(), 0
    for item in _bounded_list(value.get("bindings"), MAX_BINDINGS, "registry_bindings_invalid"):
        _exact(item, {"routingAlias", "state", "reasonCode", "candidates", "activeCandidate"}, "registry_bindings_invalid")
        name, candidates = _alias(item["routingAlias"]), item["candidates"]
        if name.casefold() in aliases or item["state"] not in {"ready", "blocked", "tombstoned"} or not isinstance(candidates, list) or len(candidates) > 2: _fail("registry_bindings_invalid")
        for candidate in candidates:
            _exact(candidate, {"installationId", "revisionId"}, "registry_bindings_invalid"); installed = by_install.get(candidate["installationId"])
            if installed is None or candidate["revisionId"] != installed["revisionId"]: _fail("registry_bindings_invalid")
        if candidates != sorted(candidates, key=lambda item: (item["installationId"], item["revisionId"])) or len({item["installationId"] for item in candidates}) != len(candidates): _fail("registry_not_canonical")
        if item["state"] == "ready":
            if not candidates or item["activeCandidate"] not in candidates or item["reasonCode"] is not None: _fail("registry_bindings_invalid")
        elif item["activeCandidate"] is not None or not isinstance(item["reasonCode"], str) or item["reasonCode"] not in _BINDING_REASONS: _fail("registry_bindings_invalid")
        aliases.add(name.casefold()); candidate_count += len(candidates); bindings.append(item)
    if candidate_count > 1024 or bindings != sorted(bindings, key=lambda item: (item["routingAlias"].casefold(), item["routingAlias"])): _fail("registry_not_canonical")
    tombstones, tombstone_names = [], set()
    for item in _bounded_list(value.get("bundledTombstones"), MAX_TOMBSTONES, "registry_tombstones_invalid"):
        _exact(item, {"legacyName", "skillId", "catalogRevisionId", "state"}, "registry_tombstones_invalid"); name = _alias(item["legacyName"])
        if name.casefold() in tombstone_names or item["state"] not in {"matched", "unmatched"}: _fail("registry_tombstones_invalid")
        if item["state"] == "matched":
            if not _BUNDLE_ID.fullmatch(str(item["skillId"])) or not _HASH.fullmatch(str(item["catalogRevisionId"])): _fail("registry_tombstones_invalid")
        elif item["skillId"] is not None or item["catalogRevisionId"] is not None: _fail("registry_tombstones_invalid")
        tombstone_names.add(name.casefold()); tombstones.append(item)
    if tombstones != sorted(tombstones, key=lambda item: (item["legacyName"].casefold(), item["legacyName"])): _fail("registry_not_canonical")
    base = {"schema": REGISTRY_SCHEMA, "dataRootId": value["dataRootId"], "generation": generation, "installations": installations, "bindings": bindings, "bundledTombstones": tombstones, "sourceObservations": observations}
    result_hash, receipts, operations = _state_hash(base), [], set()
    for item in _bounded_list(value.get("operationReceipts"), MAX_RECEIPTS, "registry_receipts_invalid"):
        _exact(item, {"operationId", "kind", "requestHash", "appliedGeneration", "resultStateHash"}, "registry_receipts_invalid")
        if not _OP_ID.fullmatch(str(item["operationId"])) or item["operationId"] in operations or item["kind"] != "bootstrap-v1" or not _HASH.fullmatch(str(item["requestHash"])) or item["appliedGeneration"] != generation or item["resultStateHash"] != result_hash: _fail("registry_receipts_invalid")
        operations.add(item["operationId"]); receipts.append(item)
    if receipts != sorted(receipts, key=lambda item: item["operationId"]): _fail("registry_not_canonical")
    normalized = {**base, "operationReceipts": receipts, "registryHash": value.get("registryHash")}
    if normalized["registryHash"] != _registry_hash(normalized): _fail("registry_hash_mismatch")
    return normalized
class SkillStore:
    def __init__(self, data_root, bundled_root, *, write_enabled=False, fault_injector=None, lock_timeout=5.0):
        if data_root is None or bundled_root is None: raise ValueError("explicit data_root and bundled_root are required")
        self.data_root, self.bundled_root = Path(data_root), Path(bundled_root)
        self.root, self.write_enabled = self.data_root / STORE_DIRECTORY, bool(write_enabled)
        self.fault_injector, self.lock_timeout = fault_injector, max(0.01, min(float(lock_timeout), 30.0))
    def _hit(self, point):
        if self.fault_injector is not None: self.fault_injector(point)
    def _inspect_layout(self):
        kind = revisions._path_kind(self.root)
        if kind == "missing": return set()
        _safe_dir(self.root); allowed = {"root.json", "registry.json", "registry.lock", "objects", "transactions", "staging"}
        for item in self.root.iterdir():
            if item.name in allowed: _safe_dir(item) if item.name in {"objects", "transactions", "staging"} else _safe_file(item)
            elif _TEMP.fullmatch(item.name): _safe_file(item)
            else: _fail("store_layout_unknown")
        transactions = self.root / "transactions"
        if transactions.exists():
            count = 0
            for item in transactions.iterdir():
                if _OP_ID.fullmatch(item.stem) and item.suffix == ".json": _safe_file(item); count += 1
                elif _TEMP.fullmatch(item.name): _safe_file(item)
                else: _fail("store_layout_unknown")
            if count > MAX_TRANSACTIONS: _fail("store_transaction_limit")
        staging = self.root / "staging"
        if staging.exists():
            items = list(staging.iterdir())
            if len(items) > 1: _fail("store_transaction_conflict")
            for item in items:
                if not _OP_ID.fullmatch(item.name): _fail("store_layout_unknown")
                _safe_dir(item)
        objects_root, objects, object_ids = self.root / "objects", self.root / "objects" / "sha256", set()
        if objects_root.exists() and {item.name for item in objects_root.iterdir()} - {"sha256"}: _fail("store_layout_unknown")
        if objects.exists():
            _safe_dir(objects)
            for prefix in objects.iterdir():
                if not re.fullmatch(r"[0-9a-f]{2}", prefix.name): _fail("store_layout_unknown")
                _safe_dir(prefix)
                for item in prefix.iterdir():
                    if not re.fullmatch(r"[0-9a-f]{64}", item.name) or not item.name.startswith(prefix.name): _fail("store_layout_unknown")
                    _safe_dir(item); object_ids.add("sha256:" + item.name)
            if len(object_ids) > MAX_OBJECTS: _fail("store_object_limit")
        _safe_tree_bytes(self.root)
        return object_ids
    def _initial_state(self, *, lock_held=False):
        """Classify a store before any lock or skeleton write."""
        if revisions._path_kind(self.root) == "missing":
            return "empty"
        _safe_dir(self.root)
        allowed = {"registry.lock", "objects", "transactions", "staging"}
        children = {item.name: item for item in self.root.iterdir()}
        if set(children) - allowed:
            return "existing"
        lock = children.get("registry.lock")
        if lock is not None and not lock_held:
            _safe_file(lock)
            if os.lstat(lock).st_size > 1:
                return "existing"
        for name in ("transactions", "staging"):
            directory = children.get(name)
            if directory is not None:
                _safe_dir(directory)
                if next(directory.iterdir(), None) is not None:
                    return "existing"
        objects = children.get("objects")
        if objects is not None:
            _safe_dir(objects)
            object_children = {item.name: item for item in objects.iterdir()}
            if set(object_children) - {"sha256"}:
                return "existing"
            hashes = object_children.get("sha256")
            if hashes is not None:
                _safe_dir(hashes)
                if next(hashes.iterdir(), None) is not None:
                    return "existing"
        return "empty"
    def _preflight(self, catalog, hints):
        _safe_dir(self.data_root); _safe_dir(self.bundled_root); self._inspect_layout()
        catalog = revisions.normalize_bundled_catalog(catalog)
        plan = revisions.plan_legacy_migration(self.data_root / "skills", self.bundled_root, catalog)
        if plan["installedRootState"] in {"unsafe", "unreadable"}: _fail("legacy_root_invalid")
        legacy = {key: plan[key] for key in ("rootMode", "installedRootState", "unmatchedTombstones", "entries")}
        legacy_hash = _digest(_canonical(legacy))
        request_hash = _digest(_canonical({"operationKind": "bootstrap-v1", "catalogHash": plan["catalogHash"], "planHash": plan["planHash"], "legacySnapshotHash": legacy_hash, "identityHints": hints}))
        return catalog, plan, legacy_hash, request_hash
    @contextmanager
    def _mutation_lock(self):
        self.root.mkdir(exist_ok=True); _safe_dir(self.root); path = self.root / "registry.lock"
        with _thread_lock(path):
            flags = os.O_RDWR | os.O_CREAT
            if hasattr(os, "O_BINARY"): flags |= os.O_BINARY
            if hasattr(os, "O_NOFOLLOW"): flags |= os.O_NOFOLLOW
            with os.fdopen(os.open(path, flags, 0o600), "r+b", closefd=True) as stream:
                after, current = os.fstat(stream.fileno()), os.lstat(path)
                if revisions._path_kind(path) != "file" or not stat.S_ISREG(after.st_mode) or int(getattr(after, "st_nlink", 1)) != 1 or (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino): _fail("store_lock_unsafe")
                if after.st_size == 0: stream.write(b"\0"); stream.flush(); os.fsync(stream.fileno())
                deadline = time.monotonic() + self.lock_timeout
                while True:
                    try:
                        if os.name == "nt":
                            import msvcrt
                            stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError as exc:
                        if time.monotonic() >= deadline: raise SkillStoreError("store_busy") from exc
                        time.sleep(0.01)
                try: yield
                finally:
                    try:
                        if os.name == "nt":
                            import msvcrt
                            stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                    except OSError: pass
    def _ensure_skeleton(self):
        for path in (self.root / "objects" / "sha256", self.root / "transactions", self.root / "staging"):
            path.mkdir(parents=True, exist_ok=True); _safe_dir(path)
        self._hit("after-skeleton")
    def _atomic_json(self, path, value, operation_id, label):
        payload, preserve = _canonical(value) + b"\n", False
        temporary = path.with_name(f".{path.name}.{operation_id}.{uuid.uuid4().hex}.tmp")
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_BINARY"): flags |= os.O_BINARY
            with os.fdopen(os.open(temporary, flags, 0o600), "wb", closefd=True) as stream:
                stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            self._hit(f"after-{label}-temp")
            if label in {"root", "registry"} and path.exists(): _fail(f"{label}_cas_conflict")
            for attempt in range(5):
                try: os.replace(temporary, path); temporary = None; break
                except PermissionError:
                    if attempt == 4: raise
                    time.sleep(0.01 * 2**attempt)
            _safe_file(path)
            if revisions._stable_file(path) != payload: _fail("store_write_verify_failed")
            self._hit(f"after-{label}-publish")
        except SkillStoreInterruption: preserve = True; raise
        finally:
            if not preserve and temporary is not None and temporary.exists():
                try: temporary.unlink()
                except OSError: pass
    def _load_json(self, path, maximum, code):
        _safe_file(path); raw = revisions._stable_file(path)
        if len(raw) > maximum: _fail(code)
        try: return raw, json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc: raise SkillStoreError(code) from exc
    def _load_root(self):
        path = self.root / "root.json"
        if revisions._path_kind(path) == "missing": return None
        raw, value = self._load_json(path, MAX_ROOT_BYTES, "root_invalid"); _exact(value, {"schema", "dataRootId"}, "root_invalid")
        if value["schema"] != ROOT_SCHEMA or not _ROOT_ID.fullmatch(str(value["dataRootId"])) or raw != _canonical(value) + b"\n": _fail("root_invalid")
        return value
    def _object_path(self, revision_id, *, staging=None):
        value = str(revision_id).removeprefix("sha256:")
        base = self.root / "objects" if staging is None else self.root / "staging" / staging / "objects"
        return base / "sha256" / value[:2] / value
    def _verify_object(self, directory, expected_revision=None):
        kind = revisions._path_kind(directory)
        if kind == "missing": _fail("object_missing")
        if kind != "directory": _fail("object_corrupt")
        _safe_dir(directory); children = {item.name: item for item in directory.iterdir()}
        if set(children) != {"manifest.json", "content"}: _fail("object_corrupt")
        _safe_dir(children["content"]); raw, value = self._load_json(children["manifest.json"], MAX_MANIFEST_BYTES, "object_corrupt")
        try: manifest = revisions.normalize_revision_manifest(value)
        except revisions.SkillRevisionError as exc: raise SkillStoreError("object_corrupt") from exc
        if raw != _canonical(manifest) + b"\n" or expected_revision is not None and manifest["revisionId"] != expected_revision: _fail("object_corrupt")
        expected = {item["path"]: item for item in manifest["files"]}
        expected_dirs = {parent.as_posix() for name in expected for parent in Path(name).parents if parent.as_posix() != "."}
        found, found_dirs, pending = {}, set(), [children["content"]]
        while pending:
            current = pending.pop()
            for item in current.iterdir():
                relative, kind = item.relative_to(children["content"]).as_posix(), revisions._path_kind(item)
                if kind == "directory":
                    if relative not in expected_dirs: _fail("object_corrupt")
                    found_dirs.add(relative); pending.append(item)
                elif kind == "file": _safe_file(item); found[relative] = item
                else: _fail("object_corrupt")
        if set(found) != set(expected) or found_dirs != expected_dirs: _fail("object_corrupt")
        for name, path in found.items():
            payload = revisions._stable_file(path)
            mode, canonical, item = *revisions._canonical_content(payload), expected[name]
            if canonical != payload or mode != item["contentMode"] or len(payload) != item["size"] or revisions._digest(payload) != item["digest"]: _fail("object_corrupt")
        return manifest
    def _load_registry(self, verify_objects=True):
        path = self.root / "registry.json"
        if revisions._path_kind(path) == "missing": return None
        raw, value = self._load_json(path, MAX_REGISTRY_BYTES, "registry_invalid"); registry = normalize_registry(value)
        if raw != _canonical(registry) + b"\n": _fail("registry_not_canonical")
        root = self._load_root()
        if root is None or root["dataRootId"] != registry["dataRootId"]: _fail("registry_root_mismatch")
        if verify_objects:
            for revision_id in sorted({item["revisionId"] for item in registry["installations"]}): self._verify_object(self._object_path(revision_id), revision_id)
        return registry
    def _normalize_journal(self, value):
        fields = {"schema", "operationId", "operationKind", "phase", "journalGeneration", "dataRootId", "requestHash", "planHash", "catalogHash", "legacySnapshotHash", "baseRegistry", "targetRegistry", "objectRevisionIds", "newObjectBytes"}
        _exact(value, fields, "journal_invalid")
        hashes = ("requestHash", "planHash", "catalogHash", "legacySnapshotHash")
        if value["schema"] != TRANSACTION_SCHEMA or value["operationKind"] != "bootstrap-v1" or value["phase"] not in _PHASES or not _ROOT_ID.fullmatch(str(value["dataRootId"])) or not all(_HASH.fullmatch(str(value[key])) for key in hashes) or value["operationId"] != _operation_id(value["dataRootId"], value["requestHash"]): _fail("journal_invalid")
        if isinstance(value["journalGeneration"], bool) or not isinstance(value["journalGeneration"], int) or value["journalGeneration"] < 0: _fail("journal_invalid")
        _exact(value["baseRegistry"], {"generation", "registryHash"}, "journal_invalid"); base = value["baseRegistry"]
        if (base["generation"], base["registryHash"]) != (None, None) and (isinstance(base["generation"], bool) or not isinstance(base["generation"], int) or not _HASH.fullmatch(str(base["registryHash"]))): _fail("journal_invalid")
        target, objects = normalize_registry(value["targetRegistry"]), value["objectRevisionIds"]
        bad = (target["dataRootId"] != value["dataRootId"] or not isinstance(objects, list) or objects != sorted(set(objects))
               or len(objects) > MAX_INSTALLATIONS or not all(_HASH.fullmatch(str(item)) for item in objects)
               or set(objects) != {item["revisionId"] for item in target["installations"]}
               or isinstance(value["newObjectBytes"], bool) or not isinstance(value["newObjectBytes"], int) or not 0 <= value["newObjectBytes"] <= MAX_NEW_OBJECT_BYTES)
        if bad: _fail("journal_invalid")
        receipt = next((item for item in target["operationReceipts"] if item["operationId"] == value["operationId"]), None)
        if receipt is None or receipt["requestHash"] != value["requestHash"]: _fail("journal_invalid")
        return {**value, "targetRegistry": target}
    def _journals(self):
        result, directory = [], self.root / "transactions"
        if not directory.exists(): return result
        for path in sorted(directory.glob("op1_*.json")):
            raw, value = self._load_json(path, MAX_JOURNAL_BYTES, "journal_invalid"); journal = self._normalize_journal(value)
            if path.stem != journal["operationId"] or raw != _canonical(journal) + b"\n": _fail("journal_invalid")
            result.append(journal)
        if len(result) > MAX_TRANSACTIONS or sum(item["phase"] != "committed" for item in result) > 1: _fail("store_transaction_conflict")
        return result
    def _write_journal(self, journal, phase=None):
        updated = dict(journal)
        if phase is not None and phase != updated["phase"]: updated["phase"], updated["journalGeneration"] = phase, updated["journalGeneration"] + 1
        updated = self._normalize_journal(updated)
        if len(_canonical(updated)) + 1 > MAX_JOURNAL_BYTES: _fail("journal_size_limit")
        path = self.root / "transactions" / f"{updated['operationId']}.json"
        if path.exists():
            raw, current = self._load_json(path, MAX_JOURNAL_BYTES, "journal_invalid")
            if self._normalize_journal(current) != journal or raw != _canonical(journal) + b"\n": _fail("journal_cas_conflict")
        self._atomic_json(path, updated, updated["operationId"], f"journal-{updated['phase']}")
        return updated
    def _partial_stage_known(self, target, manifest, contents):
        if revisions._path_kind(target) != "directory": return False
        allowed_top, expected_dirs = {"content", "manifest.json"}, {parent.as_posix() for name in contents for parent in Path(name).parents if parent.as_posix() != "."}
        for item in target.iterdir():
            if item.name not in allowed_top: return False
            if item.name == "manifest.json":
                if revisions._path_kind(item) != "file": return False
                _safe_file(item)
                if revisions._stable_file(item) != _canonical(manifest) + b"\n": return False
            else:
                if revisions._path_kind(item) != "directory": return False
                pending = [item]
                while pending:
                    current = pending.pop()
                    for child in current.iterdir():
                        relative, kind = child.relative_to(item).as_posix(), revisions._path_kind(child)
                        if kind == "directory" and relative in expected_dirs: pending.append(child)
                        elif kind == "file" and relative in contents:
                            _safe_file(child)
                            if revisions._stable_file(child) != contents[relative]: return False
                        else: return False
        return True
    def _stage_object(self, operation_id, revision_id, source):
        manifest, contents = revisions.read_skill_revision(source)
        if manifest["revisionId"] != revision_id: _fail("bootstrap_source_changed")
        final = self._object_path(revision_id)
        if final.exists(): self._verify_object(final, revision_id); return
        target = self._object_path(revision_id, staging=operation_id)
        if target.exists():
            try: self._verify_object(target, revision_id); return
            except SkillStoreError:
                if not self._partial_stage_known(target, manifest, contents): _fail("staging_unknown")
                _remove_safe_tree(target)
        content = target / "content"; content.mkdir(parents=True)
        for relative, payload in contents.items():
            path = content / Path(relative); path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "xb") as stream: stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            self._hit("after-staging-file")
        with open(target / "manifest.json", "xb") as stream: stream.write(_canonical(manifest) + b"\n"); stream.flush(); os.fsync(stream.fileno())
        self._verify_object(target, revision_id)
    def _publish_object(self, operation_id, revision_id):
        final = self._object_path(revision_id)
        if final.exists(): self._verify_object(final, revision_id); return
        staging = self._object_path(revision_id, staging=operation_id); self._verify_object(staging, revision_id); final.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(5):
            try: os.rename(staging, final); break
            except FileExistsError: self._verify_object(final, revision_id); return
            except PermissionError:
                if attempt == 4: raise
                time.sleep(0.01 * 2**attempt)
        self._verify_object(final, revision_id); self._hit("after-object-publish")
    def _build_target(self, root_id, request_hash, plan, hints, fixed=None):
        installs, bindings, observations, tombstones, materials, used_hints = [], [], [], [], {}, set()
        observation_ids, installation_ids, skill_ids, catalog_hash = set(), set(), set(), plan["catalogHash"]
        fixed_ids = {(item["kind"], item["displayName"]): (item["skillId"], item["installationId"]) for item in (fixed or {}).get("installations", [])}
        def observe(kind, root_kind, name, state="ready", revision_id=None, error=None):
            item = _observation(kind, root_kind, name, state, revision_id, catalog_hash if kind != "legacy-installed" else None, error)
            if item["sourceObservationId"] not in observation_ids: observation_ids.add(item["sourceObservationId"]); observations.append(item)
            return item["sourceObservationId"]
        def identity(name, local):
            key = ("local" if local else "bundled", name)
            if key in fixed_ids:
                if local and name in hints:
                    if fixed_ids[key] != (hints[name]["skillId"], hints[name]["installationId"]): _fail("identity_hints_invalid")
                    used_hints.add(name)
                return fixed_ids[key]
            if local and name in hints: used_hints.add(name); return hints[name]["skillId"], hints[name]["installationId"]
            for _ in range(8):
                sid, iid = ("local.skill/" + uuid.uuid4().hex if local else None), "si1_" + uuid.uuid4().hex
                if iid not in installation_ids and (not local or sid not in skill_ids): return sid, iid
            _fail("identity_collision")
        def install(name, kind, revision_id, source_state, source_ids, bundle_id=None):
            sid, iid = identity(name, kind == "local"); sid = bundle_id if kind == "bundled" else sid
            if iid in installation_ids or sid in skill_ids: _fail("identity_collision")
            installation_ids.add(iid); skill_ids.add(sid)
            installs.append({"installationId": iid, "skillId": sid, "kind": kind, "displayName": name, "revisionId": revision_id, "sourceState": source_state, "sourceObservationIds": sorted(set(source_ids))})
            return {"installationId": iid, "revisionId": revision_id}
        def material(revision_id, path):
            if revisions.build_skill_revision(path)["revisionId"] != revision_id: _fail("bootstrap_source_changed")
            materials.setdefault(revision_id, Path(path))
        def add_tombstone(entry):
            item = {"legacyName": entry["directory"], "skillId": entry.get("skillId"), "catalogRevisionId": entry.get("bundledRevisionId"), "state": "matched"}
            if item not in tombstones: tombstones.append(item)
        for entry in plan["entries"]:
            name, classification = entry["directory"], entry["classification"]
            installed_path, bundled_path = self.data_root / "skills" / name, self.bundled_root / name
            candidates, state, reason, active = [], "blocked", classification, None
            observed, bundled = entry["installed"].get("revisionId"), entry.get("bundledRevisionId")
            if classification == "invalid":
                invalid_state = entry["installed"].get("state", "invalid")
                invalid_state = invalid_state if invalid_state in _OBSERVATION_ERRORS else "invalid"
                observe("legacy-installed", "legacy", name, invalid_state, None, _OBSERVATION_ERRORS[invalid_state])
                if not name.startswith("~invalid-"): bindings.append({"routingAlias": name, "state": state, "reasonCode": "source-invalid", "candidates": [], "activeCandidate": None})
                continue
            if classification in {"exact-bundled", "shared-development"} and observed == bundled:
                kind, root_kind = (("workspace-development", "shared") if classification == "shared-development" else ("legacy-installed", "legacy"))
                sources = [observe(kind, root_kind, name, revision_id=observed), observe("bundled-catalog", "bundled", name, revision_id=bundled)]
                material(observed, installed_path); candidates.append(install(name, "bundled", observed, "present", sources, entry["skillId"]))
                if classification == "exact-bundled": state, reason, active = "ready", None, candidates[0]
                else: reason = "shared-development-unconfirmed"
            elif classification == "local-custom":
                source = observe("legacy-installed", "legacy", name, revision_id=observed); material(observed, installed_path)
                candidates.append(install(name, "local", observed, "present", [source])); state, reason, active = "ready", None, candidates[0]
            elif classification in {"same-name-modified", "tombstone-conflict"} or classification == "shared-development" and observed != bundled:
                kind, root_kind = (("workspace-development", "shared") if classification == "shared-development" else ("legacy-installed", "legacy"))
                source = observe(kind, root_kind, name, revision_id=observed); material(observed, installed_path); candidates.append(install(name, "local", observed, "present", [source]))
                if entry.get("bundledState") == "tombstoned" or classification == "tombstone-conflict": add_tombstone(entry); reason = "tombstone-conflict"
                else:
                    source = observe("bundled-catalog", "bundled", name, revision_id=bundled); material(bundled, bundled_path)
                    candidates.append(install(name, "bundled", bundled, "catalog-only", [source], entry["skillId"])); reason = "shared-development-unconfirmed" if classification == "shared-development" else "same-name-modified"
            elif classification == "tombstoned-bundled": add_tombstone(entry); state, reason = "tombstoned", "bundled-tombstoned"
            elif classification == "bundled-missing":
                source = observe("bundled-catalog", "bundled", name, revision_id=bundled); material(bundled, bundled_path)
                candidates.append(install(name, "bundled", bundled, "catalog-only", [source], entry["skillId"])); reason = "legacy-root-missing" if plan["installedRootState"] == "missing" else "legacy-bundled-missing"
            else: _fail("bootstrap_classification_unknown")
            bindings.append({"routingAlias": name, "state": state, "reasonCode": reason, "candidates": sorted(candidates, key=lambda item: item["installationId"]), "activeCandidate": active})
        aliases = {item["routingAlias"].casefold() for item in bindings}
        for name in plan["unmatchedTombstones"]:
            tombstones.append({"legacyName": name, "skillId": None, "catalogRevisionId": None, "state": "unmatched"})
            if name.casefold() not in aliases: bindings.append({"routingAlias": name, "state": "tombstoned", "reasonCode": "unmatched-legacy-tombstone", "candidates": [], "activeCandidate": None})
        if used_hints != set(hints): _fail("identity_hint_unused")
        installs.sort(key=lambda item: item["installationId"]); bindings.sort(key=lambda item: (item["routingAlias"].casefold(), item["routingAlias"]))
        observations.sort(key=lambda item: item["sourceObservationId"]); tombstones.sort(key=lambda item: (item["legacyName"].casefold(), item["legacyName"]))
        base = {"schema": REGISTRY_SCHEMA, "dataRootId": root_id, "generation": 0, "installations": installs, "bindings": bindings, "bundledTombstones": tombstones, "sourceObservations": observations}
        operation_id = _operation_id(root_id, request_hash)
        receipt = {"operationId": operation_id, "kind": "bootstrap-v1", "requestHash": request_hash, "appliedGeneration": 0, "resultStateHash": _state_hash(base)}
        registry = {**base, "operationReceipts": [receipt], "registryHash": None}; registry["registryHash"] = _registry_hash(registry)
        return normalize_registry(registry), materials
    def _clean_stage(self, operation_id, allowed_ids):
        path = self.root / "staging" / operation_id
        if not path.exists(): return
        _safe_dir(path); objects = path / "objects"
        if {item.name for item in path.iterdir()} - {"objects"}: _fail("staging_unknown")
        if objects.exists():
            _safe_dir(objects)
            if {item.name for item in objects.iterdir()} - {"sha256"}: _fail("staging_unknown")
            hashes = objects / "sha256"
            if hashes.exists():
                _safe_dir(hashes)
                for prefix in hashes.iterdir():
                    if not re.fullmatch(r"[0-9a-f]{2}", prefix.name): _fail("staging_unknown")
                    _safe_dir(prefix)
                    for item in prefix.iterdir():
                        revision_id = "sha256:" + item.name
                        if revision_id not in allowed_ids or not item.name.startswith(prefix.name): _fail("staging_unknown")
                        self._verify_object(item, revision_id)
        _remove_safe_tree(path)
    def _clean_temps(self, known, empty=False):
        for directory in (self.root, self.root / "transactions"):
            if not directory.exists(): continue
            for item in directory.iterdir():
                match = _TEMP.fullmatch(item.name)
                if match:
                    if match.group(1) not in known and not empty: _fail("store_temp_unknown")
                    _safe_file(item); item.unlink()
    def read_registry(self):
        self._inspect_layout(); registry = self._load_registry()
        if registry is None and self.root.exists(): _fail("registry_missing")
        return registry
    def _recover_captured(self, journal, root, registry):
        operation_id, target = journal["operationId"], journal["targetRegistry"]
        if root is None:
            self._atomic_json(self.root / "root.json", {"schema": ROOT_SCHEMA, "dataRootId": journal["dataRootId"]}, operation_id, "root")
            root = self._load_root()
        if root["dataRootId"] != journal["dataRootId"]: _fail("root_mismatch")
        phase_index, staged_index = _PHASES.index(journal["phase"]), _PHASES.index("staged-verified")
        for revision_id in journal["objectRevisionIds"]:
            final = self._object_path(revision_id)
            if final.exists(): self._verify_object(final, revision_id)
            elif phase_index == staged_index: self._verify_object(self._object_path(revision_id, staging=operation_id), revision_id)
            else: _fail("bootstrap_recovery_capture_missing")
        if phase_index == staged_index:
            for revision_id in journal["objectRevisionIds"]: self._publish_object(operation_id, revision_id)
            journal = self._write_journal(journal, "objects-published")
        for revision_id in journal["objectRevisionIds"]: self._verify_object(self._object_path(revision_id), revision_id)
        current = registry or (self._load_registry() if (self.root / "registry.json").exists() else None)
        if current is None:
            if _PHASES.index(journal["phase"]) > _PHASES.index("objects-published"): _fail("bootstrap_recovery_registry_missing")
            self._atomic_json(self.root / "registry.json", target, operation_id, "registry"); current = self._load_registry()
        if current != target: _fail("registry_cas_conflict")
        if _PHASES.index(journal["phase"]) < _PHASES.index("registry-published"): journal = self._write_journal(journal, "registry-published")
        if journal["phase"] != "committed": journal = self._write_journal(journal, "committed")
        self._clean_stage(operation_id, set(journal["objectRevisionIds"])); return current
    def bootstrap(self, catalog, *, identity_hints=None):
        if not self.write_enabled: _fail("store_writes_disabled")
        hints = _normalize_hints(identity_hints)
        initial_state = self._initial_state()
        first = self._preflight(catalog, hints) if initial_state == "empty" else None
        if initial_state != "empty": self._inspect_layout()
        with self._mutation_lock():
            if first is not None and self._initial_state(lock_held=True) != "empty":
                first = None
            self._ensure_skeleton()
            journals, root = self._journals(), self._load_root()
            if len(journals) > 1: _fail("store_transaction_conflict")
            registry = self._load_registry() if (self.root / "registry.json").exists() else None
            active = [item for item in journals if item["phase"] != "committed"]
            known = {item["operationId"] for item in journals}
            staged = {item.name for item in (self.root / "staging").iterdir()}
            if staged - known: _fail("staging_unknown")
            referenced = {item["revisionId"] for item in (registry or {}).get("installations", [])}
            referenced.update(revision_id for item in journals for revision_id in item["objectRevisionIds"])
            if self._inspect_layout() - referenced: _fail("store_object_unknown")
            late = journals[0] if journals and _PHASES.index(journals[0]["phase"]) >= _PHASES.index("staged-verified") else None
            if late is not None:
                self._clean_temps(known); current = self._recover_captured(late, root, registry)
                try: current_request = self._preflight(catalog, hints)[3]
                except (SkillStoreError, revisions.SkillRevisionError) as exc: raise SkillStoreError("bootstrap_already_committed_conflict") from exc
                if current_request != late["requestHash"]: _fail("bootstrap_already_committed_conflict")
                return current
            try: second = self._preflight(catalog, hints)
            except (SkillStoreError, revisions.SkillRevisionError) as exc:
                if active: raise SkillStoreError("bootstrap_recovery_source_conflict") from exc
                raise
            if first is not None and first[1:] != second[1:]: _fail("bootstrap_preflight_changed")
            _catalog, plan, legacy_hash, request_hash = second
            matching = active[0] if active else None
            if matching is not None and (matching["requestHash"] != request_hash or matching["planHash"] != plan["planHash"] or matching["legacySnapshotHash"] != legacy_hash): _fail("bootstrap_recovery_source_conflict")
            if matching is None and (journals or root is not None or registry is not None): _fail("bootstrap_store_incomplete")
            root_id = matching["dataRootId"] if matching else "dr1_" + uuid.uuid4().hex
            operation_id = matching["operationId"] if matching else _operation_id(root_id, request_hash)
            self._clean_temps(known, empty=root is None and registry is None and not journals)
            target, materials = self._build_target(root_id, request_hash, plan, hints, matching["targetRegistry"] if matching else None)
            if len(_canonical(target)) + 1 > MAX_REGISTRY_BYTES: _fail("registry_size_limit")
            if matching is None:
                object_ids = sorted(materials); new_bytes = sum(revisions.build_skill_revision(materials[item])["summary"]["totalSize"] for item in object_ids if not self._object_path(item).exists())
                existing_ids = self._inspect_layout()
                if new_bytes > MAX_NEW_OBJECT_BYTES or _safe_tree_bytes(self.root) + new_bytes > MAX_STORE_BYTES: _fail("store_new_bytes_limit")
                if len(existing_ids | set(object_ids)) > MAX_OBJECTS: _fail("store_object_limit")
                journal = {"schema": TRANSACTION_SCHEMA, "operationId": operation_id, "operationKind": "bootstrap-v1", "phase": "prepared", "journalGeneration": 0, "dataRootId": root_id, "requestHash": request_hash, "planHash": plan["planHash"], "catalogHash": plan["catalogHash"], "legacySnapshotHash": legacy_hash, "baseRegistry": {"generation": None, "registryHash": None}, "targetRegistry": target, "objectRevisionIds": object_ids, "newObjectBytes": new_bytes}
                if _safe_tree_bytes(self.root) + new_bytes + len(_canonical(journal)) + len(_canonical(target)) + 2 > MAX_STORE_BYTES: _fail("store_size_limit")
                if len(journals) >= MAX_TRANSACTIONS: _fail("store_transaction_limit")
                journal = self._write_journal(journal)
            else:
                journal = matching
                if journal["targetRegistry"] != target: _fail("bootstrap_recovery_source_conflict")
            if root is None: self._atomic_json(self.root / "root.json", {"schema": ROOT_SCHEMA, "dataRootId": root_id}, operation_id, "root")
            elif root["dataRootId"] != root_id: _fail("root_mismatch")
            journal = self._write_journal(journal, "root-bound"); journal = self._write_journal(journal, "copying")
            for revision_id in journal["objectRevisionIds"]:
                if not self._object_path(revision_id).exists() and revision_id not in materials: _fail("bootstrap_source_missing")
                if revision_id in materials: self._stage_object(operation_id, revision_id, materials[revision_id])
            journal = self._write_journal(journal, "staged-verified")
            current = self._recover_captured(journal, self._load_root(), None)
            self._hit("after-cleanup"); return current


class SkillStoreReader:
    """Read exact immutable objects without creating or repairing store state."""

    def __init__(self, data_root):
        if data_root is None:
            raise ValueError("explicit data_root is required")
        self._store = SkillStore(data_root, data_root)

    def _root(self, expected=None):
        self._store._inspect_layout()
        root = self._store._load_root()
        if root is None:
            _fail("store_root_missing")
        if expected is not None and root["dataRootId"] != expected:
            _fail("store_data_root_mismatch")
        return root

    def read_registry(self, *, data_root_id=None, verify_objects=True):
        object_ids = self._store._inspect_layout()
        self._root(data_root_id)
        registry = self._store._load_registry(verify_objects=bool(verify_objects))
        if registry is None:
            _fail("registry_missing")
        referenced = {item["revisionId"] for item in registry["installations"]}
        if object_ids != referenced:
            _fail("store_object_unknown")
        return json.loads(_canonical(registry))

    def verify_root(self, data_root_id):
        """Verify only immutable root identity, including no-match recovery."""
        return json.loads(_canonical(self._root(data_root_id)))

    def read_pinned(self, data_root_id, revision_id):
        if not _ROOT_ID.fullmatch(str(data_root_id)):
            _fail("store_data_root_invalid")
        if not _HASH.fullmatch(str(revision_id)):
            _fail("object_revision_invalid")
        root = self._root(data_root_id)
        return self._read_pinned_from_root(root, revision_id)

    def _read_pinned_from_root(self, root, revision_id, *, runtime=False, paths=None):
        """Read one object while a caller already owns a verified root snapshot."""
        if not isinstance(root, dict) or not _ROOT_ID.fullmatch(str(root.get("dataRootId"))):
            _fail("store_data_root_invalid")
        if not _HASH.fullmatch(str(revision_id)):
            _fail("object_revision_invalid")
        directory = self._store._object_path(revision_id)
        if revisions._path_kind(directory) == "missing":
            _fail("object_missing")
        manifest = self._store._verify_object(directory, revision_id)
        files = []
        selected_paths = None if paths is None else set(paths)
        for item in manifest["files"]:
            if selected_paths is not None and item["path"] not in selected_paths:
                continue
            payload = revisions._stable_file(directory / "content" / item["path"])
            mode, canonical = revisions._canonical_content(payload)
            if (canonical != payload or mode != item["contentMode"] or len(payload) != item["size"]
                    or revisions._digest(payload) != item["digest"]):
                _fail("object_changed")
            files.append({**item, "content": payload})
        if self._store._verify_object(directory, revision_id) != manifest:
            _fail("object_changed")
        if self._store._load_root() != root:
            _fail("store_root_changed")
        result = {
            "dataRootId": root["dataRootId"],
            "revisionId": revision_id,
            "manifest": manifest,
            "files": files,
        }
        if runtime:
            result["contentRoot"] = str(directory / "content")
        return result

    def read_runtime(self, data_root_id, revision_id):
        """Return verified bytes plus the current non-authoritative object path."""
        root = self._root(data_root_id)
        return self._read_pinned_from_root(root, revision_id, runtime=True)

    def begin_admission(self):
        """Create a request-scoped O(N + selected) immutable admission view."""
        return SkillStoreAdmissionSnapshot(self)

    def read_active(self, routing_alias):
        alias = _alias(routing_alias)
        registry = self.read_registry()
        matches = [item for item in registry["bindings"] if item["routingAlias"].casefold() == alias.casefold()]
        if not matches:
            _fail("store_binding_missing")
        binding = matches[0]
        if binding["state"] != "ready":
            _fail("store_binding_unavailable")
        candidate = binding["activeCandidate"]
        installation = next(
            (item for item in registry["installations"] if item["installationId"] == candidate["installationId"]),
            None,
        )
        if installation is None or installation["revisionId"] != candidate["revisionId"]:
            _fail("store_active_candidate_invalid")
        pinned = self.read_pinned(registry["dataRootId"], candidate["revisionId"])
        if self.read_registry() != registry:
            _fail("registry_changed")
        return {
            "registry": {key: registry[key] for key in ("schema", "dataRootId", "generation", "registryHash")},
            "routingAlias": binding["routingAlias"],
            "installation": {key: installation[key] for key in ("skillId", "installationId", "displayName", "revisionId")},
            "object": pinned,
        }


class SkillStoreAdmissionSnapshot:
    """One bounded admission snapshot; never shared across requests."""

    def __init__(self, reader):
        if not isinstance(reader, SkillStoreReader):
            raise TypeError("reader must be a SkillStoreReader")
        self._reader = reader
        self.registry = reader.read_registry(verify_objects=False)
        self._root = {
            "schema": ROOT_SCHEMA,
            "dataRootId": self.registry["dataRootId"],
        }
        self._closed = False
        self._route_reads = {}
        self._capture_reads = {}
        self._captured_revisions = set()

    @property
    def metrics(self):
        return {
            "registryReads": 1 + int(self._closed),
            "routeObjectReads": dict(self._route_reads),
            "captureObjectReads": dict(self._capture_reads),
            "finalObjectReads": len(self._captured_revisions) if self._closed else 0,
        }

    def _binding(self, routing_alias):
        if self._closed:
            _fail("admission_snapshot_closed")
        alias = _alias(routing_alias)
        matches = [
            item for item in self.registry["bindings"]
            if item["routingAlias"].casefold() == alias.casefold()
        ]
        if not matches:
            _fail("store_binding_missing")
        binding = matches[0]
        if binding["state"] != "ready":
            _fail("store_binding_unavailable")
        candidate = binding["activeCandidate"]
        installation = next((
            item for item in self.registry["installations"]
            if item["installationId"] == candidate["installationId"]
        ), None)
        if installation is None or installation["revisionId"] != candidate["revisionId"]:
            _fail("store_active_candidate_invalid")
        return binding, installation

    def _selection(self, routing_alias, counter, *, capture):
        binding, installation = self._binding(routing_alias)
        alias = binding["routingAlias"]
        counter[alias] = counter.get(alias, 0) + 1
        pinned = self._reader._read_pinned_from_root(
            self._root, installation["revisionId"],
            paths=None if capture else {
                "SKILL.md", "evidence.json", "dependencies.json", "code-resources.json",
            },
        )
        if capture:
            self._captured_revisions.add(installation["revisionId"])
        return {
            "registry": {
                key: self.registry[key]
                for key in ("schema", "dataRootId", "generation", "registryHash")
            },
            "routingAlias": alias,
            "installation": {
                key: installation[key]
                for key in ("skillId", "installationId", "displayName", "revisionId")
            },
            "object": pinned,
        }

    def read_active(self, routing_alias):
        """Read a routing candidate exactly once for descriptor discovery."""
        return self._selection(routing_alias, self._route_reads, capture=False)

    def capture_active(self, routing_alias):
        """Re-read a selected object so returned payload bytes are verified directly."""
        return self._selection(routing_alias, self._capture_reads, capture=True)

    def finish(self):
        if self._closed:
            return json.loads(_canonical(self.registry))
        current = self._reader.read_registry(
            data_root_id=self.registry["dataRootId"], verify_objects=False,
        )
        if current != self.registry:
            _fail("registry_changed")
        for revision_id in sorted(self._captured_revisions):
            self._reader._read_pinned_from_root(
                self._root, revision_id, paths=set(),
            )
        self._closed = True
        return json.loads(_canonical(self.registry))
