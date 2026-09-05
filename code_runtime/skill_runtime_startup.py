"""Process-owned immutable Skill startup without lazy per-request IO."""

from __future__ import annotations

import os
from pathlib import Path
import threading

from . import data_dir_owner
from . import skill_revisions
from . import skill_store


class ImmutableSkillStartupError(RuntimeError):
    def __init__(self, code, message="Immutable Skill startup is unavailable"):
        self.code = str(code)
        super().__init__(message)


def _path_key(value):
    try:
        path = Path(value).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ImmutableSkillStartupError("skill_runtime_startup_path_invalid") from exc
    return os.path.normcase(os.path.normpath(str(path)))


class ImmutableSkillStartupRuntime:
    """Initialize exactly once while the entrypoint owns the selected profile."""

    def __init__(self, *, store_factory=skill_store.SkillStore,
                 reader_factory=skill_store.SkillStoreReader,
                 catalog_loader=skill_revisions.load_bundled_catalog):
        self._store_factory = store_factory
        self._reader_factory = reader_factory
        self._catalog_loader = catalog_loader
        self._guard = threading.RLock()
        self._initialized = False
        self._identity = None
        self._status = "uninitialized"
        self._admission_enabled = False
        self._reader = None
        self._error_code = ""

    def snapshot(self):
        with self._guard:
            return {
                "status": self._status,
                "admissionEnabled": self._admission_enabled,
                "readerReady": self._reader is not None,
                "errorCode": self._error_code,
            }

    def recovery_reader(self):
        with self._guard:
            return self._reader

    def admission_reader(self):
        with self._guard:
            return self._reader if self._admission_enabled else None

    def _unavailable(self, code, admission_enabled, cause=None):
        self._status = "unavailable"
        self._admission_enabled = bool(admission_enabled)
        self._reader = None
        self._error_code = str(code or "skill_runtime_startup_failed")
        if admission_enabled:
            raise ImmutableSkillStartupError(self._error_code) from cause
        return self.snapshot()

    def initialize(self, *, owner, data_root, bundled_root, admission_enabled,
                   legacy_sync_result=None):
        if not isinstance(owner, data_dir_owner.DataDirOwner) or owner.released:
            raise ImmutableSkillStartupError("skill_runtime_owner_required")
        data_key = _path_key(data_root)
        if _path_key(owner.data_dir) != data_key:
            raise ImmutableSkillStartupError("skill_runtime_owner_mismatch")
        bundled_key = _path_key(bundled_root)
        enabled = bool(admission_enabled)
        identity = (id(owner), data_key, bundled_key, enabled)
        with self._guard:
            if self._initialized:
                if identity == self._identity:
                    if self._status == "unavailable" and self._admission_enabled:
                        raise ImmutableSkillStartupError(self._error_code)
                    return self.snapshot()
                raise ImmutableSkillStartupError(
                    "skill_runtime_startup_reinitialize_conflict"
                )
            self._initialized = True
            self._identity = identity
            self._admission_enabled = enabled
            try:
                store = self._store_factory(
                    Path(data_root), Path(bundled_root), write_enabled=True,
                )
                startup = store.inspect_startup_state()
                state = startup["state"]
                if state == "empty" and not enabled:
                    self._status = "disabled"
                    return self.snapshot()
                if state == "empty":
                    if legacy_sync_result is not None and (
                        not isinstance(legacy_sync_result, dict)
                        or legacy_sync_result.get("ok") is not True
                    ):
                        return self._unavailable(
                            "skill_runtime_legacy_sync_failed", enabled,
                        )
                    store.bootstrap_from_catalog_loader(
                        lambda: self._catalog_loader(
                            Path(bundled_root) / skill_revisions.CATALOG_FILENAME
                        )
                    )
                elif state == "recoverable":
                    if startup.get("management") is True:
                        from .skill_store_management import SkillStoreManager
                        SkillStoreManager(store, owner=owner).recover()
                    else:
                        store.bootstrap_from_catalog_loader(
                            lambda: self._catalog_loader(
                                Path(bundled_root) / skill_revisions.CATALOG_FILENAME
                            )
                        )
                reader = self._reader_factory(Path(data_root))
                reader.read_registry()
            except (skill_store.SkillStoreError,
                    skill_revisions.SkillRevisionError) as exc:
                return self._unavailable(exc.code, enabled, exc)
            except OSError as exc:
                return self._unavailable(
                    "skill_runtime_startup_io_failed", enabled, exc,
                )
            self._reader = reader
            self._status = "ready"
            self._error_code = ""
            return self.snapshot()
