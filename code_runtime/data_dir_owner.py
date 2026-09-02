"""Process-lifetime, non-blocking ownership locks for Code data directories.

The lock file deliberately lives beside (rather than inside) the target data
directory.  A first packaged launch must acquire ownership before a legacy
``~/.agent-lite`` migration decides whether ``~/.code`` exists.
"""

from __future__ import annotations

import atexit
import errno
import hashlib
import os
import stat
import threading
from pathlib import Path


class DataDirOwnerError(RuntimeError):
    """A data-directory owner lock cannot be acquired safely."""

    code = "data_dir_owner_unavailable"
    retryable = False


class DataDirInUseError(DataDirOwnerError):
    """Another process currently owns the requested data directory."""

    code = "data_dir_owner_busy"
    retryable = True


class DataDirOwnerUnavailableError(DataDirOwnerError):
    """The lock storage is unavailable or unsafe."""

    code = "data_dir_owner_unavailable"


_OWNERS_GUARD = threading.RLock()
_OWNERS: dict[str, "DataDirOwner"] = {}
# The detached updater uses the same Windows byte-range lock after its source
# process exits.  Keep the position public rather than duplicating a magic
# value in a generated PowerShell helper.
WINDOWS_LOCK_OFFSET = 0
WINDOWS_LOCK_LENGTH = 1


def _is_reparse_point(info) -> bool:
    """Reject links/reparse points rather than locking an ambiguous pathname."""
    return bool(int(getattr(info, "st_file_attributes", 0)) & 0x0400)


def _is_safe_directory(info) -> bool:
    return (
        stat.S_ISDIR(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and not _is_reparse_point(info)
    )


def _is_safe_lock_file(info) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and not _is_reparse_point(info)
        and int(getattr(info, "st_nlink", 1)) == 1
    )


def _canonical_data_dir(data_dir: Path | str) -> Path:
    try:
        lexical_target = Path(data_dir).expanduser().absolute()
        try:
            existing = lexical_target.lstat()
        except FileNotFoundError:
            existing = None
        if existing is not None and not _is_safe_directory(existing):
            raise DataDirOwnerUnavailableError("data directory is unavailable")
        target = lexical_target.resolve(strict=False)
    except DataDirOwnerError:
        raise
    except (OSError, RuntimeError, TypeError) as exc:
        raise DataDirOwnerUnavailableError("data directory is unavailable") from exc
    if not target.name:
        raise DataDirOwnerUnavailableError("data directory is unavailable")
    return target


def _owner_key(target: Path) -> str:
    return os.path.normcase(str(target))


def lock_path_for(data_dir: Path | str) -> Path:
    """Return the stable, non-data sidecar used to serialize one DATA_DIR."""
    target = _canonical_data_dir(data_dir)
    digest = hashlib.sha256(
        _owner_key(target).encode("utf-8")
    ).hexdigest()[:20]
    return target.parent / f".{target.name}.code-data-owner-{digest}.lock"


def _ensure_lock_parent(lock_path: Path) -> None:
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        info = lock_path.parent.lstat()
    except OSError as exc:
        raise DataDirOwnerUnavailableError("data directory is unavailable") from exc
    if not _is_safe_directory(info):
        raise DataDirOwnerUnavailableError("data directory is unavailable")


def _open_lock_file(lock_path: Path):
    descriptor = None
    file_obj = None
    opened = False
    try:
        try:
            before = lock_path.lstat()
        except FileNotFoundError:
            before = None
        if before is not None and not _is_safe_lock_file(before):
            raise DataDirOwnerUnavailableError("data directory lock is unsafe")
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(lock_path, flags, 0o600)
        try:
            os.set_inheritable(descriptor, False)
        except OSError as exc:
            raise DataDirOwnerUnavailableError("data directory lock is unavailable") from exc
        file_obj = os.fdopen(descriptor, "r+b", closefd=True)
        descriptor = None
        after = os.fstat(file_obj.fileno())
        current = lock_path.lstat()
        if (
            not _is_safe_lock_file(after)
            or not _is_safe_lock_file(current)
            or (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise DataDirOwnerUnavailableError("data directory lock is unsafe")
        opened = True
        return file_obj
    except DataDirOwnerUnavailableError:
        raise
    except OSError as exc:
        raise DataDirOwnerUnavailableError("data directory lock is unavailable") from exc
    finally:
        if file_obj is not None and not opened:
            # Ownership transfers only through the successful return above.
            # A pathname replacement must not leave a descriptor open.
            try:
                if not file_obj.closed:
                    file_obj.close()
            except OSError:
                pass
        elif descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _try_lock(file_obj) -> bool:
    if os.name == "nt":
        import msvcrt

        file_obj.seek(0, os.SEEK_END)
        if file_obj.tell() == 0:
            file_obj.write(b"\0")
            file_obj.flush()
            os.fsync(file_obj.fileno())
        file_obj.seek(WINDOWS_LOCK_OFFSET)
        try:
            msvcrt.locking(
                file_obj.fileno(),
                msvcrt.LK_NBLCK,
                WINDOWS_LOCK_LENGTH,
            )
            return True
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK, 13, 36}:
                return False
            raise

    import fcntl

    try:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
            return False
        raise


def _unlock(file_obj) -> None:
    if os.name == "nt":
        import msvcrt

        file_obj.seek(WINDOWS_LOCK_OFFSET)
        msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, WINDOWS_LOCK_LENGTH)
        return

    import fcntl

    fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


class DataDirOwner:
    """One process-held owner for a single canonical DATA_DIR."""

    def __init__(self, key: str, target: Path, lock_path: Path, file_obj):
        self._key = key
        self.data_dir = target
        self.lock_path = lock_path
        self._file_obj = file_obj
        self._released = False

    @property
    def released(self) -> bool:
        return self._released

    def release(self) -> None:
        file_obj = None
        with _OWNERS_GUARD:
            if self._released:
                return
            self._released = True
            if _OWNERS.get(self._key) is self:
                _OWNERS.pop(self._key, None)
            file_obj = self._file_obj
            self._file_obj = None
        if file_obj is not None:
            try:
                _unlock(file_obj)
            except OSError:
                # Process shutdown still closes the descriptor.  Do not turn
                # shutdown cleanup into a second startup failure.
                pass
            finally:
                try:
                    file_obj.close()
                except OSError:
                    pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()


def acquire_data_dir_owner(data_dir: Path | str) -> DataDirOwner:
    """Acquire a non-blocking, process-lifetime owner for ``data_dir``."""
    target = _canonical_data_dir(data_dir)
    key = _owner_key(target)
    with _OWNERS_GUARD:
        existing = _OWNERS.get(key)
        if existing is not None and not existing.released:
            # Windows byte-range locks are process-scoped, so a second open
            # in this process must not be mistaken for a separate owner.
            # Reject it instead of handing out ref-counted aliases that could
            # release the kernel lock before the other caller is finished.
            raise DataDirInUseError("data directory is already in use")

        path = lock_path_for(target)
        _ensure_lock_parent(path)
        file_obj = _open_lock_file(path)
        try:
            locked = _try_lock(file_obj)
        except OSError as exc:
            file_obj.close()
            raise DataDirOwnerUnavailableError("data directory lock is unavailable") from exc
        except Exception as exc:
            file_obj.close()
            raise DataDirOwnerUnavailableError("data directory lock is unavailable") from exc
        if not locked:
            file_obj.close()
            raise DataDirInUseError("data directory is already in use")
        owner = DataDirOwner(key, target, path, file_obj)
        _OWNERS[key] = owner
        return owner


def _release_all_at_exit() -> None:
    with _OWNERS_GUARD:
        owners = list(_OWNERS.values())
    for owner in owners:
        owner.release()


atexit.register(_release_all_at_exit)
