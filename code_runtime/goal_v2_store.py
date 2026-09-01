"""Crash-aware append-only storage for the isolated Goal v2 fact source."""

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

from .goal_v2_protocol import (
    GoalV2FoldState,
    GoalV2ProtocolError,
    GoalV2TransitionError,
    apply_event,
    build_event,
    canonical_json,
    require_identifier,
    require_revision,
)


GOAL_V2_DIRECTORY_NAME = "goals-v2"
_SESSION_ID_RE = re.compile(r"[A-Za-z0-9_-]{8,64}\Z")
_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}


class GoalV2StoreError(RuntimeError):
    """Base Goal v2 persistence failure."""


class GoalV2ConflictError(GoalV2StoreError):
    """CAS, idempotency, ownership, or lifecycle conflict."""


class GoalV2CorruptionError(GoalV2StoreError):
    """Mutation refused because the v2 sidecar is not fully trusted."""


class GoalV2PersistenceError(GoalV2StoreError):
    """The append or durability boundary failed."""


@dataclass
class GoalV2ReadResult:
    state: GoalV2FoldState
    health: str = "healthy"
    writable: bool = True
    error: dict[str, Any] | None = None
    exists: bool = False

    def projection(self) -> dict[str, Any]:
        result = self.state.projection()
        result.update({
            "health": self.health,
            "writable": self.writable,
            "exists": self.exists,
            "error": copy.deepcopy(self.error),
        })
        return result


def _safe_session_id(session_id: str) -> str:
    value = str(session_id or "")
    if not _SESSION_ID_RE.fullmatch(value):
        raise ValueError("invalid session id")
    return value


def _safe_actor(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise GoalV2ProtocolError(
            "actor must be a non-empty string of at most 64 characters"
        )
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


class GoalV2Service:
    """The sole writer for Session-scoped ``data/goals-v2`` event logs.

    ``data_root`` is the parent data directory, not a Goal directory.  The
    service always appends below a dedicated ``goals-v2`` child, so callers
    cannot accidentally mix v2 events with legacy ``goals`` or
    ``goal-workflows`` sidecars.
    """

    def __init__(
        self,
        data_root: Path | str,
        *,
        clock: Callable[[], str] | None = None,
    ):
        self.data_root = Path(data_root)
        self.root = self.data_root / GOAL_V2_DIRECTORY_NAME
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

    def read(self, session_id: str) -> GoalV2ReadResult:
        safe_id = _safe_session_id(session_id)
        path = self.events_path(safe_id)
        state = GoalV2FoldState(safe_id)
        if not path.exists():
            return GoalV2ReadResult(state=state)
        try:
            payload = path.read_bytes()
        except FileNotFoundError:
            return GoalV2ReadResult(state=state)
        except OSError as exc:
            return GoalV2ReadResult(
                state=state,
                health="corrupted",
                writable=False,
                exists=True,
                error={"kind": "read_error", "line": None, "message": str(exc)[:240]},
            )

        lines = payload.splitlines(keepends=True)
        if lines and not lines[-1].endswith((b"\n", b"\r")):
            complete_lines = lines[:-1]
            tail_error = {
                "kind": "partial_tail",
                "line": len(lines),
                "message": "unterminated trailing Goal v2 event ignored",
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
            except (UnicodeError, json.JSONDecodeError, GoalV2ProtocolError) as exc:
                return GoalV2ReadResult(
                    state=state,
                    health="corrupted",
                    writable=False,
                    exists=True,
                    error={
                        "kind": "invalid_event",
                        "line": number,
                        "message": str(exc)[:240],
                    },
                )
        if tail_error:
            return GoalV2ReadResult(
                state=state,
                health="degraded",
                writable=False,
                exists=True,
                error=tail_error,
            )
        return GoalV2ReadResult(state=state, exists=True)

    def archive_sidecar(self, session_id: str, destination: Path | str) -> bool:
        """Copy one v2 fact log under the same cross-process mutation lock."""
        safe_id = _safe_session_id(session_id)
        source = self.events_path(safe_id)
        if not source.exists():
            return False
        with self._mutation_lock(safe_id):
            if not source.exists():
                return False
            target = Path(destination)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(source, target)
            except OSError as exc:
                raise GoalV2PersistenceError(
                    f"failed to archive Goal v2 sidecar: {exc}"
                ) from exc
        return True

    def delete_sidecar(self, session_id: str) -> bool:
        """Remove current v2 facts only as part of explicit Session deletion."""
        safe_id = _safe_session_id(session_id)
        path = self.events_path(safe_id)
        if not path.exists():
            return False
        with self._mutation_lock(safe_id):
            existed = path.exists()
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                raise GoalV2PersistenceError(
                    f"failed to delete Goal v2 sidecar: {exc}"
                ) from exc
        return existed

    @staticmethod
    def _idempotent_result(
        read_result: GoalV2ReadResult,
        idempotency_key: str,
        desired_hash: str,
    ) -> dict[str, Any] | None:
        previous_hash = read_result.state.idempotency.get(idempotency_key)
        if previous_hash is None:
            return None
        if previous_hash != desired_hash:
            raise GoalV2ConflictError(
                "idempotency key was already used with a different payload"
            )
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
                        raise OSError("short write while appending Goal v2 event")
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            raise GoalV2PersistenceError(
                f"failed to durably append Goal v2 event: {exc}"
            ) from exc

    def append(
        self,
        session_id: str,
        goal_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        expected_revision: int,
        idempotency_key: str,
        actor: str = "server",
    ) -> dict[str, Any]:
        safe_id = _safe_session_id(session_id)
        goal_id = require_identifier(goal_id, "goal_id")
        expected_revision = require_revision(
            expected_revision, "expected_revision", allow_zero=True
        )
        idempotency_key = require_identifier(idempotency_key, "idempotency_key")
        actor = _safe_actor(actor)

        candidate = build_event(
            event_id="candidate",
            event_type=event_type,
            session_id=safe_id,
            goal_id=goal_id,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            actor=actor,
            created_at="1970-01-01T00:00:00",
            payload=payload,
        )
        desired_hash = candidate["requestHash"]

        with self._mutation_lock(safe_id):
            current = self.read(safe_id)
            if not current.writable:
                raise GoalV2CorruptionError(
                    "Goal v2 sidecar is degraded or corrupted; mutation refused"
                )
            no_op = self._idempotent_result(
                current, idempotency_key, desired_hash
            )
            if no_op is not None:
                return no_op
            if current.state.revision != expected_revision:
                raise GoalV2ConflictError(
                    f"stale Goal v2 revision: expected {expected_revision}, "
                    f"current {current.state.revision}"
                )
            event = build_event(
                event_id=uuid.uuid4().hex,
                event_type=event_type,
                session_id=safe_id,
                goal_id=goal_id,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
                actor=actor,
                created_at=self.clock(),
                payload=payload,
            )
            trial = copy.deepcopy(current.state)
            try:
                apply_event(trial, event)
            except GoalV2TransitionError as exc:
                raise GoalV2ConflictError(str(exc)) from exc
            self._append_event(self.events_path(safe_id), event)
            result = GoalV2ReadResult(state=trial, exists=True).projection()
            result.update({"accepted": True, "noOp": False})
            return result
