#!/usr/bin/env python3
"""Cross-runtime owner lease for one physical Git worktree.

The active lease and bounded reclaim history live in the worktree-specific
Git-dir, so they never enter the working tree or Git status.  This helper is a
local write-exclusion mechanism only; it grants no external-operation rights.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCHEMA = "workbar-owner-lease/v1"
HISTORY_SCHEMA = "workbar-owner-lease-history/v1"
STATE_NAME = "workbar-owner-lease.json"
LOCK_NAME = "workbar-owner-lease.lock"
HISTORY_NAME = "workbar-owner-lease-history.json"
TEMP_GLOB = "workbar-owner-lease*.tmp-*"

DEFAULT_TTL_SECONDS = 900
MIN_TTL_SECONDS = 60
MAX_TTL_SECONDS = 3600
CLOCK_SKEW_GRACE_SECONDS = 5
HISTORY_LIMIT = 8
LOCK_TIMEOUT_SECONDS = 10.0
MAX_STATE_BYTES = 64 * 1024

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CONFLICT = 3
EXIT_RECOVERY_REQUIRED = 4
EXIT_ENVIRONMENT = 5

_HEX_HEAD = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_LEASE_KEYS = {
    "schema",
    "leaseId",
    "runtime",
    "approvalId",
    "developerId",
    "stage",
    "baseHead",
    "relayId",
    "acquiredAt",
    "renewedAt",
    "expiresAt",
    "ttlSeconds",
}


class LeaseError(Exception):
    def __init__(self, message: str, *, code: int, status: str):
        super().__init__(message)
        self.code = code
        self.status = status


class UsageError(LeaseError):
    def __init__(self, message: str):
        super().__init__(message, code=EXIT_USAGE, status="invalid_arguments")


class ConflictError(LeaseError):
    def __init__(self, message: str):
        super().__init__(message, code=EXIT_CONFLICT, status="conflict")


class RecoveryRequiredError(LeaseError):
    def __init__(self, message: str):
        super().__init__(message, code=EXIT_RECOVERY_REQUIRED, status="recovery_required")


class EnvironmentError(LeaseError):
    def __init__(self, message: str):
        super().__init__(message, code=EXIT_ENVIRONMENT, status="environment_error")


class LeaseArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise UsageError(message)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise RecoveryRequiredError(f"lease field {field} is invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RecoveryRequiredError(f"lease field {field} is invalid") from exc
    if parsed.tzinfo is None:
        raise RecoveryRequiredError(f"lease field {field} is invalid")
    return parsed.astimezone(timezone.utc)


def _validate_text(value: object, field: str, *, maximum: int = 240) -> str:
    if not isinstance(value, str):
        raise RecoveryRequiredError(f"lease field {field} is invalid")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum or _CONTROL.search(normalized):
        raise RecoveryRequiredError(f"lease field {field} is invalid")
    return normalized


def _validate_cli_text(value: str, field: str) -> str:
    try:
        return _validate_text(value, field)
    except RecoveryRequiredError as exc:
        raise UsageError(str(exc)) from exc


def _validate_ttl(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UsageError("ttl-seconds must be an integer")
    if value < MIN_TTL_SECONDS or value > MAX_TTL_SECONDS:
        raise UsageError(
            f"ttl-seconds must be between {MIN_TTL_SECONDS} and {MAX_TTL_SECONDS}",
        )
    return value


def _validate_lease(lease: object) -> dict:
    if not isinstance(lease, dict) or set(lease) != _LEASE_KEYS:
        raise RecoveryRequiredError("lease schema or fields are invalid")
    if lease.get("schema") != SCHEMA:
        raise RecoveryRequiredError("lease schema or fields are invalid")

    try:
        uuid.UUID(str(lease.get("leaseId")))
    except (ValueError, AttributeError) as exc:
        raise RecoveryRequiredError("lease field leaseId is invalid") from exc

    if lease.get("runtime") not in {"codex", "dsh"}:
        raise RecoveryRequiredError("lease field runtime is invalid")
    for field in ("approvalId", "developerId", "stage", "relayId"):
        _validate_text(lease.get(field), field)

    base_head = lease.get("baseHead")
    if not isinstance(base_head, str) or not _HEX_HEAD.fullmatch(base_head):
        raise RecoveryRequiredError("lease field baseHead is invalid")

    ttl = lease.get("ttlSeconds")
    if isinstance(ttl, bool) or not isinstance(ttl, int):
        raise RecoveryRequiredError("lease field ttlSeconds is invalid")
    if ttl < MIN_TTL_SECONDS or ttl > MAX_TTL_SECONDS:
        raise RecoveryRequiredError("lease field ttlSeconds is invalid")

    acquired = _parse_utc(lease.get("acquiredAt"), "acquiredAt")
    renewed = _parse_utc(lease.get("renewedAt"), "renewedAt")
    expires = _parse_utc(lease.get("expiresAt"), "expiresAt")
    if acquired > renewed or renewed >= expires:
        raise RecoveryRequiredError("lease timestamps are invalid")
    if abs((expires - renewed).total_seconds() - ttl) > 0.001:
        raise RecoveryRequiredError("lease expiry does not match ttlSeconds")
    return lease


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EnvironmentError("git command could not be executed") from exc


def resolve_git_dir(repo: Path) -> Path:
    result = _run_git(repo, "rev-parse", "--absolute-git-dir")
    if result.returncode != 0 or not result.stdout.strip():
        raise EnvironmentError("repository Git-dir could not be resolved")
    return Path(result.stdout.strip()).resolve()


def _git_head(repo: Path) -> str:
    result = _run_git(repo, "rev-parse", "HEAD")
    head = result.stdout.strip().lower()
    if result.returncode != 0 or not _HEX_HEAD.fullmatch(head):
        raise EnvironmentError("repository HEAD could not be resolved")
    return head


def _ensure_cached_empty(repo: Path) -> None:
    result = _run_git(repo, "diff", "--cached", "--quiet", "--exit-code")
    if result.returncode == 1:
        raise RecoveryRequiredError("cached is not empty; user review is required")
    if result.returncode != 0:
        raise EnvironmentError("cached state could not be inspected")


def _paths(git_dir: Path) -> tuple[Path, Path, Path]:
    return (
        git_dir / STATE_NAME,
        git_dir / LOCK_NAME,
        git_dir / HISTORY_NAME,
    )


def _incomplete_temps(git_dir: Path) -> list[Path]:
    try:
        return sorted(git_dir.glob(TEMP_GLOB))
    except OSError as exc:
        raise EnvironmentError("lease temporary state could not be inspected") from exc


def _read_json(path: Path, *, label: str) -> object:
    try:
        if path.stat().st_size > MAX_STATE_BYTES:
            raise RecoveryRequiredError(f"{label} is too large")
        return json.loads(path.read_text(encoding="utf-8"))
    except RecoveryRequiredError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecoveryRequiredError(f"{label} is damaged") from exc


def _load_lease(git_dir: Path) -> dict | None:
    state_path, _, _ = _paths(git_dir)
    if _incomplete_temps(git_dir):
        raise RecoveryRequiredError("lease initialization or update is incomplete")
    if not state_path.exists():
        return None
    return _validate_lease(_read_json(state_path, label="lease state"))


def _load_history(git_dir: Path) -> list[dict]:
    _, _, history_path = _paths(git_dir)
    if not history_path.exists():
        return []
    payload = _read_json(history_path, label="lease history")
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "entries"}
        or payload.get("schema") != HISTORY_SCHEMA
        or not isinstance(payload.get("entries"), list)
        or len(payload["entries"]) > HISTORY_LIMIT
        or not all(isinstance(entry, dict) for entry in payload["entries"])
    ):
        raise RecoveryRequiredError("lease history is damaged")
    return payload["entries"]


def _fsync_parent(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_json(path: Path, payload: object) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    descriptor = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_parent(path)
    except OSError as exc:
        raise EnvironmentError("lease state could not be written atomically") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _initialize_lock_file(lock_path: Path) -> None:
    try:
        descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    except OSError as exc:
        raise EnvironmentError("lease mutation lock could not be initialized") from exc
    try:
        os.write(descriptor, b"\0")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _try_lock(stream) -> bool:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    import fcntl

    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(stream) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def _mutation_lock(git_dir: Path):
    _, lock_path, _ = _paths(git_dir)
    _initialize_lock_file(lock_path)
    try:
        stream = lock_path.open("r+b", buffering=0)
    except OSError as exc:
        raise EnvironmentError("lease mutation lock could not be opened") from exc

    locked = False
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    try:
        while time.monotonic() < deadline:
            if _try_lock(stream):
                locked = True
                break
            time.sleep(0.025)
        if not locked:
            raise EnvironmentError("lease mutation lock timed out")
        yield
    finally:
        if locked:
            try:
                _unlock(stream)
            except OSError:
                pass
        stream.close()


def _holder_from_args(args: argparse.Namespace) -> dict[str, str]:
    runtime = args.runtime
    if runtime not in {"codex", "dsh"}:
        raise UsageError("runtime must be codex or dsh")
    return {
        "runtime": runtime,
        "approvalId": _validate_cli_text(args.approval_id, "approval-id"),
        "developerId": _validate_cli_text(args.developer_id, "developer-id"),
    }


def _same_holder(lease: dict, holder: dict[str, str]) -> bool:
    return all(lease[key] == holder[key] for key in ("runtime", "approvalId", "developerId"))


def _lease_timing(lease: dict, now: datetime) -> tuple[str, bool]:
    expires = _parse_utc(lease["expiresAt"], "expiresAt")
    within_grace = expires < now <= expires + timedelta(seconds=CLOCK_SKEW_GRACE_SECONDS)
    if now > expires + timedelta(seconds=CLOCK_SKEW_GRACE_SECONDS):
        return "expired", False
    return "active", within_grace


def _new_lease(
    holder: dict[str, str],
    *,
    stage: str,
    relay_id: str,
    base_head: str,
    ttl: int,
    now: datetime,
) -> dict:
    renewed = now
    return {
        "schema": SCHEMA,
        "leaseId": str(uuid.uuid4()),
        **holder,
        "stage": stage,
        "baseHead": base_head,
        "relayId": relay_id,
        "acquiredAt": _format_utc(now),
        "renewedAt": _format_utc(renewed),
        "expiresAt": _format_utc(renewed + timedelta(seconds=ttl)),
        "ttlSeconds": ttl,
    }


def _renew_lease(lease: dict, *, stage: str, relay_id: str, ttl: int, now: datetime) -> dict:
    prior_renewed = _parse_utc(lease["renewedAt"], "renewedAt")
    effective_now = max(now, prior_renewed)
    renewed = dict(lease)
    renewed.update(
        {
            "stage": stage,
            "relayId": relay_id,
            "renewedAt": _format_utc(effective_now),
            "expiresAt": _format_utc(effective_now + timedelta(seconds=ttl)),
            "ttlSeconds": ttl,
        },
    )
    return _validate_lease(renewed)


def acquire(args: argparse.Namespace) -> dict:
    repo = Path(args.repo).resolve()
    git_dir = resolve_git_dir(repo)
    holder = _holder_from_args(args)
    stage = _validate_cli_text(args.stage, "stage")
    relay_id = _validate_cli_text(args.relay_id, "relay-id")
    ttl = _validate_ttl(args.ttl_seconds)

    with _mutation_lock(git_dir):
        lease = _load_lease(git_dir)
        now = _utc_now()
        if lease is None:
            _ensure_cached_empty(repo)
            lease = _new_lease(
                holder,
                stage=stage,
                relay_id=relay_id,
                base_head=_git_head(repo),
                ttl=ttl,
                now=now,
            )
            _atomic_write_json(_paths(git_dir)[0], lease)
            action = "acquired"
        else:
            timing, _ = _lease_timing(lease, now)
            if timing == "expired":
                raise RecoveryRequiredError("lease is expired; explicit reclaim is required")
            if not _same_holder(lease, holder):
                raise ConflictError("lease is held by a different owner")
            lease = _renew_lease(
                lease,
                stage=stage,
                relay_id=relay_id,
                ttl=ttl,
                now=now,
            )
            _atomic_write_json(_paths(git_dir)[0], lease)
            action = "renewed"
    return {"ok": True, "action": action, "status": "active", "lease": lease}


def renew(args: argparse.Namespace) -> dict:
    repo = Path(args.repo).resolve()
    git_dir = resolve_git_dir(repo)
    holder = _holder_from_args(args)
    lease_id = _validate_cli_text(args.lease_id, "lease-id")
    stage = _validate_cli_text(args.stage, "stage")
    relay_id = _validate_cli_text(args.relay_id, "relay-id")
    ttl = _validate_ttl(args.ttl_seconds)

    with _mutation_lock(git_dir):
        lease = _load_lease(git_dir)
        if lease is None:
            raise ConflictError("no active lease exists")
        timing, _ = _lease_timing(lease, _utc_now())
        if timing == "expired":
            raise RecoveryRequiredError("lease is expired; explicit reclaim is required")
        if lease["leaseId"] != lease_id or not _same_holder(lease, holder):
            raise ConflictError("leaseId or owner does not match")
        lease = _renew_lease(
            lease,
            stage=stage,
            relay_id=relay_id,
            ttl=ttl,
            now=_utc_now(),
        )
        _atomic_write_json(_paths(git_dir)[0], lease)
    return {"ok": True, "action": "renewed", "status": "active", "lease": lease}


def release(args: argparse.Namespace) -> dict:
    repo = Path(args.repo).resolve()
    git_dir = resolve_git_dir(repo)
    holder = _holder_from_args(args)
    lease_id = _validate_cli_text(args.lease_id, "lease-id")

    with _mutation_lock(git_dir):
        lease = _load_lease(git_dir)
        if lease is None:
            raise ConflictError("no active lease exists")
        if lease["leaseId"] != lease_id or not _same_holder(lease, holder):
            raise ConflictError("leaseId or owner does not match")
        try:
            _paths(git_dir)[0].unlink()
            _fsync_parent(_paths(git_dir)[0])
        except OSError as exc:
            raise EnvironmentError("lease state could not be released") from exc
    return {"ok": True, "action": "released", "status": "none", "lease": lease}


def _history_entry(previous: dict, new_holder: dict[str, str], now: datetime) -> dict:
    return {
        "leaseId": previous["leaseId"],
        "runtime": previous["runtime"],
        "approvalId": previous["approvalId"],
        "developerId": previous["developerId"],
        "stage": previous["stage"],
        "baseHead": previous["baseHead"],
        "relayId": previous["relayId"],
        "acquiredAt": previous["acquiredAt"],
        "renewedAt": previous["renewedAt"],
        "expiresAt": previous["expiresAt"],
        "reclaimedAt": _format_utc(now),
        "reclaimedBy": dict(new_holder),
    }


def reclaim(args: argparse.Namespace) -> dict:
    repo = Path(args.repo).resolve()
    git_dir = resolve_git_dir(repo)
    holder = _holder_from_args(args)
    expected_lease_id = _validate_cli_text(args.expected_lease_id, "expected-lease-id")
    stage = _validate_cli_text(args.stage, "stage")
    relay_id = _validate_cli_text(args.relay_id, "relay-id")
    ttl = _validate_ttl(args.ttl_seconds)

    with _mutation_lock(git_dir):
        previous = _load_lease(git_dir)
        if previous is None:
            raise ConflictError("no lease exists; use acquire")
        timing, _ = _lease_timing(previous, _utc_now())
        if timing != "expired":
            raise ConflictError("lease is still active")
        if previous["leaseId"] != expected_lease_id:
            raise ConflictError("expected leaseId does not match")

        _ensure_cached_empty(repo)
        current_head = _git_head(repo)
        if current_head != previous["baseHead"]:
            raise RecoveryRequiredError("HEAD differs from the expired lease baseline")

        now = _utc_now()
        history = _load_history(git_dir)
        entry = _history_entry(previous, holder, now)
        history = [item for item in history if item.get("leaseId") != previous["leaseId"]]
        history = [*history, entry][-HISTORY_LIMIT:]
        _atomic_write_json(
            _paths(git_dir)[2],
            {"schema": HISTORY_SCHEMA, "entries": history},
        )

        lease = _new_lease(
            holder,
            stage=stage,
            relay_id=relay_id,
            base_head=current_head,
            ttl=ttl,
            now=now,
        )
        _atomic_write_json(_paths(git_dir)[0], lease)
    return {
        "ok": True,
        "action": "reclaimed",
        "status": "active",
        "lease": lease,
        "previousLeaseId": previous["leaseId"],
    }


def status(args: argparse.Namespace) -> dict:
    repo = Path(args.repo).resolve()
    git_dir = resolve_git_dir(repo)
    lease = _load_lease(git_dir)
    if lease is None:
        return {"ok": True, "action": "status", "status": "none"}
    timing, within_grace = _lease_timing(lease, _utc_now())
    return {
        "ok": True,
        "action": "status",
        "status": timing,
        "withinClockSkewGrace": within_grace,
        "lease": lease,
    }


def _add_common(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--repo", default=".", help="path inside the target Git worktree")
    subparser.add_argument("--json", action="store_true", help="emit stable JSON")


def _add_holder(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--runtime", required=True, choices=("codex", "dsh"))
    subparser.add_argument("--approval-id", required=True)
    subparser.add_argument("--developer-id", required=True)


def _add_ttl(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--ttl-seconds", type=int, default=DEFAULT_TTL_SECONDS)


def build_parser() -> argparse.ArgumentParser:
    parser = LeaseArgumentParser(
        description="Atomic owner lease for a shared Code worktree",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="read lease state without writing")
    _add_common(status_parser)
    status_parser.set_defaults(handler=status)

    acquire_parser = subparsers.add_parser("acquire", help="acquire or idempotently renew")
    _add_common(acquire_parser)
    _add_holder(acquire_parser)
    _add_ttl(acquire_parser)
    acquire_parser.add_argument("--stage", required=True)
    acquire_parser.add_argument("--relay-id", required=True)
    acquire_parser.set_defaults(handler=acquire)

    renew_parser = subparsers.add_parser("renew", help="renew a matching active lease")
    _add_common(renew_parser)
    _add_holder(renew_parser)
    _add_ttl(renew_parser)
    renew_parser.add_argument("--lease-id", required=True)
    renew_parser.add_argument("--stage", required=True)
    renew_parser.add_argument("--relay-id", required=True)
    renew_parser.set_defaults(handler=renew)

    release_parser = subparsers.add_parser("release", help="release a matching lease")
    _add_common(release_parser)
    _add_holder(release_parser)
    release_parser.add_argument("--lease-id", required=True)
    release_parser.set_defaults(handler=release)

    reclaim_parser = subparsers.add_parser("reclaim", help="audit and replace an expired lease")
    _add_common(reclaim_parser)
    _add_holder(reclaim_parser)
    _add_ttl(reclaim_parser)
    reclaim_parser.add_argument("--expected-lease-id", required=True)
    reclaim_parser.add_argument("--stage", required=True)
    reclaim_parser.add_argument("--relay-id", required=True)
    reclaim_parser.set_defaults(handler=reclaim)
    return parser


def _quoted(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _emit(payload: dict, *, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return

    if not payload.get("ok"):
        print(
            "ERROR"
            f" status={payload['status']}"
            f" code={payload['code']}"
            f" message={_quoted(payload['error'])}",
            file=sys.stderr,
        )
        return

    action = str(payload["action"]).upper()
    fields = [f"status={payload['status']}"]
    lease = payload.get("lease")
    if isinstance(lease, dict):
        for key in (
            "leaseId",
            "runtime",
            "approvalId",
            "developerId",
            "stage",
            "relayId",
            "baseHead",
            "expiresAt",
        ):
            fields.append(f"{key}={_quoted(lease[key])}")
    if "withinClockSkewGrace" in payload:
        fields.append(f"withinClockSkewGrace={str(payload['withinClockSkewGrace']).lower()}")
    print(f"{action} " + " ".join(fields))


def _json_requested(argv: list[str]) -> bool:
    return "--json" in argv


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    json_mode = _json_requested(raw_argv)
    try:
        args = build_parser().parse_args(raw_argv)
        json_mode = bool(args.json)
        payload = args.handler(args)
        _emit(payload, json_mode=json_mode)
        return EXIT_OK
    except LeaseError as exc:
        payload = {
            "ok": False,
            "status": exc.status,
            "code": exc.code,
            "error": str(exc),
        }
        _emit(payload, json_mode=json_mode)
        return exc.code
    except Exception:
        payload = {
            "ok": False,
            "status": "environment_error",
            "code": EXIT_ENVIRONMENT,
            "error": "unexpected owner lease failure",
        }
        _emit(payload, json_mode=json_mode)
        return EXIT_ENVIRONMENT


if __name__ == "__main__":
    raise SystemExit(main())
