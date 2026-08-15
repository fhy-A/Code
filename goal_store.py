"""Server-owned append-only persistence for Goal protocol v1."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from goal_protocol import (
    GOAL_PROTOCOL_VERSION,
    GoalFoldState,
    GoalProtocolError,
    GoalTransitionError,
    apply_event,
    canonical_json,
    normalize_snapshot,
    request_hash,
)


_SESSION_ID_RE = re.compile(r"[A-Za-z0-9_-]{8,64}\Z")
_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}


class GoalStoreError(RuntimeError):
    """Base persistence failure."""


class GoalConflictError(GoalStoreError):
    """CAS, idempotency, or lifecycle conflict."""


class GoalCorruptionError(GoalStoreError):
    """Mutation refused because the sidecar is not fully trusted."""


class GoalPersistenceError(GoalStoreError):
    """The append or durability boundary failed."""


@dataclass
class GoalReadResult:
    state: GoalFoldState
    health: str = "healthy"
    writable: bool = True
    error: dict[str, Any] | None = None
    exists: bool = False

    def projection(self) -> dict[str, Any]:
        result = self.state.projection()
        result.update({
            "health": self.health,
            "writable": self.writable,
            "armed": False,
            "exists": self.exists,
            "error": copy.deepcopy(self.error),
        })
        return result


def _safe_session_id(session_id: str) -> str:
    value = str(session_id or "")
    if not _SESSION_ID_RE.fullmatch(value):
        raise ValueError("invalid session id")
    return value


def _safe_identifier(value: Any, label: str) -> str:
    text = str(value or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", text):
        raise GoalProtocolError(f"{label} is not a valid identifier")
    return text


def _safe_expected_revision(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GoalProtocolError("expected_revision must be an integer >= 0")
    return value


def _safe_actor(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise GoalProtocolError("actor must be a non-empty string of at most 64 characters")
    return value


def _thread_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve(strict=False)))
    with _LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


def _lock_file(file_obj) -> None:
    if os.name == "nt":
        import msvcrt

        file_obj.seek(0, os.SEEK_END)
        if file_obj.tell() == 0:
            file_obj.write(b"\0")
            file_obj.flush()
        file_obj.seek(0)
        msvcrt.locking(file_obj.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX)


def _unlock_file(file_obj) -> None:
    if os.name == "nt":
        import msvcrt

        file_obj.seek(0)
        msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


class GoalService:
    """Single server-side writer for one directory of Session Goal sidecars."""

    def __init__(self, root: Path | str, *, clock: Callable[[], str] | None = None):
        self.root = Path(root)
        self.clock = clock or self._default_clock

    @staticmethod
    def _default_clock() -> str:
        import datetime as dt

        return dt.datetime.now().replace(microsecond=0).isoformat()

    def events_path(self, session_id: str) -> Path:
        return self.root / f"{_safe_session_id(session_id)}.jsonl"

    def lock_path(self, session_id: str) -> Path:
        return self.root / f"{_safe_session_id(session_id)}.lock"

    @contextmanager
    def _mutation_lock(self, session_id: str):
        lock_path = self.lock_path(session_id)
        self.root.mkdir(parents=True, exist_ok=True)
        local_lock = _thread_lock(lock_path)
        with local_lock:
            with open(lock_path, "a+b") as lock_file:
                _lock_file(lock_file)
                try:
                    yield
                finally:
                    _unlock_file(lock_file)

    def read(self, session_id: str) -> GoalReadResult:
        safe_id = _safe_session_id(session_id)
        path = self.events_path(safe_id)
        state = GoalFoldState(safe_id)
        if not path.exists():
            return GoalReadResult(state=state)
        try:
            payload = path.read_bytes()
        except FileNotFoundError:
            return GoalReadResult(state=state)
        except OSError as exc:
            return GoalReadResult(
                state=state,
                health="corrupted",
                writable=False,
                exists=True,
                error={"kind": "read_error", "line": None, "message": str(exc)[:240]},
            )
        exists = True
        lines = payload.splitlines(keepends=True)
        if lines and not lines[-1].endswith((b"\n", b"\r")):
            complete_lines = lines[:-1]
            tail_error = {
                "kind": "partial_tail",
                "line": len(lines),
                "message": "unterminated trailing Goal event ignored",
            }
        else:
            complete_lines = lines
            tail_error = None
        for number, raw_line in enumerate(complete_lines, start=1):
            if not raw_line.strip():
                continue
            try:
                event = json.loads(raw_line.decode("utf-8"))
                apply_event(state, event)
            except (UnicodeError, json.JSONDecodeError, GoalProtocolError) as exc:
                return GoalReadResult(
                    state=state,
                    health="corrupted",
                    writable=False,
                    exists=exists,
                    error={
                        "kind": "invalid_event",
                        "line": number,
                        "message": str(exc)[:240],
                    },
                )
        if tail_error:
            return GoalReadResult(
                state=state,
                health="degraded",
                writable=False,
                exists=exists,
                error=tail_error,
            )
        return GoalReadResult(state=state, exists=exists)

    @staticmethod
    def _idempotent_result(
        read_result: GoalReadResult,
        idempotency_key: str,
        desired_hash: str,
    ) -> dict[str, Any] | None:
        previous_hash = read_result.state.idempotency.get(idempotency_key)
        if previous_hash is None:
            return None
        if previous_hash != desired_hash:
            raise GoalConflictError("idempotency key was already used with a different payload")
        projection = read_result.projection()
        projection.update({"accepted": True, "noOp": True})
        return projection

    def _append_event(self, path: Path, event: dict[str, Any]) -> None:
        payload = (canonical_json(event) + "\n").encode("utf-8")
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        try:
            fd = os.open(path, flags, 0o600)
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError("short write while appending Goal event")
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            raise GoalPersistenceError(f"failed to durably append Goal event: {exc}") from exc

    def replace(
        self,
        session_id: str,
        snapshot: dict[str, Any],
        *,
        expected_revision: int,
        idempotency_key: str,
        actor: str = "server",
    ) -> dict[str, Any]:
        safe_id = _safe_session_id(session_id)
        expected_revision = _safe_expected_revision(expected_revision)
        idempotency_key = _safe_identifier(idempotency_key, "idempotency_key")
        actor = _safe_actor(actor)
        revision = expected_revision + 1
        normalized_snapshot = normalize_snapshot(
            snapshot, session_id=safe_id, revision=revision
        )
        desired = {
            "operation": "replace",
            "sessionId": safe_id,
            "goalId": normalized_snapshot["goalId"],
            "expectedRevision": expected_revision,
            "snapshot": normalized_snapshot,
        }
        desired_hash = request_hash(desired)
        with self._mutation_lock(safe_id):
            current = self.read(safe_id)
            no_op = self._idempotent_result(current, idempotency_key, desired_hash)
            if no_op is not None:
                return no_op
            if not current.writable:
                raise GoalCorruptionError("Goal sidecar is degraded or corrupted; mutation refused")
            if current.state.revision != expected_revision:
                raise GoalConflictError(
                    f"stale Goal revision: expected {expected_revision}, current {current.state.revision}"
                )
            event = {
                "protocolVersion": GOAL_PROTOCOL_VERSION,
                "eventId": uuid.uuid4().hex,
                "operation": "replace",
                "sessionId": safe_id,
                "goalId": normalized_snapshot["goalId"],
                "revision": revision,
                "expectedRevision": expected_revision,
                "idempotencyKey": idempotency_key,
                "requestHash": desired_hash,
                "actor": actor,
                "createdAt": self.clock(),
                "snapshot": normalized_snapshot,
            }
            trial = copy.deepcopy(current.state)
            try:
                apply_event(trial, event)
            except GoalTransitionError as exc:
                raise GoalConflictError(str(exc)) from exc
            self._append_event(self.events_path(safe_id), event)
            result = GoalReadResult(state=trial, exists=True).projection()
            result.update({"accepted": True, "noOp": False})
            return result

    def clear(
        self,
        session_id: str,
        goal_id: str,
        *,
        expected_revision: int,
        idempotency_key: str,
        actor: str = "server",
    ) -> dict[str, Any]:
        safe_id = _safe_session_id(session_id)
        goal_id = _safe_identifier(goal_id, "goal_id")
        expected_revision = _safe_expected_revision(expected_revision)
        idempotency_key = _safe_identifier(idempotency_key, "idempotency_key")
        actor = _safe_actor(actor)
        desired = {
            "operation": "clear",
            "sessionId": safe_id,
            "goalId": goal_id,
            "expectedRevision": expected_revision,
        }
        desired_hash = request_hash(desired)
        with self._mutation_lock(safe_id):
            current = self.read(safe_id)
            no_op = self._idempotent_result(current, idempotency_key, desired_hash)
            if no_op is not None:
                return no_op
            if not current.writable:
                raise GoalCorruptionError("Goal sidecar is degraded or corrupted; mutation refused")
            if current.state.revision != expected_revision:
                raise GoalConflictError(
                    f"stale Goal revision: expected {expected_revision}, current {current.state.revision}"
                )
            event = {
                "protocolVersion": GOAL_PROTOCOL_VERSION,
                "eventId": uuid.uuid4().hex,
                "operation": "clear",
                "sessionId": safe_id,
                "goalId": goal_id,
                "revision": expected_revision + 1,
                "expectedRevision": expected_revision,
                "idempotencyKey": idempotency_key,
                "requestHash": desired_hash,
                "actor": actor,
                "createdAt": self.clock(),
                "snapshot": None,
            }
            trial = copy.deepcopy(current.state)
            try:
                apply_event(trial, event)
            except GoalTransitionError as exc:
                raise GoalConflictError(str(exc)) from exc
            self._append_event(self.events_path(safe_id), event)
            result = GoalReadResult(state=trial, exists=True).projection()
            result.update({"accepted": True, "noOp": False})
            return result

    def archive(self, session_id: str, destination: Path | str) -> Path | None:
        safe_id = _safe_session_id(session_id)
        source = self.events_path(safe_id)
        destination = Path(destination)
        with self._mutation_lock(safe_id):
            if not source.exists():
                return None
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
            try:
                shutil.copyfile(source, temp)
                with open(temp, "r+b") as handle:
                    os.fsync(handle.fileno())
                os.replace(temp, destination)
            finally:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
        return destination

    def delete(self, session_id: str) -> bool:
        safe_id = _safe_session_id(session_id)
        path = self.events_path(safe_id)
        with self._mutation_lock(safe_id):
            existed = path.exists()
            path.unlink(missing_ok=True)
            return existed
