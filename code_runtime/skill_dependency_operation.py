"""One bounded, fail-closed managed Skill dependency operation per data root.

The server owns plans and the data-directory lease. This helper neither queues
work nor restores environments. An interrupted writer is never replayed.
"""
from __future__ import annotations

import copy
from functools import wraps
import hashlib
import json
import os
import re
from pathlib import Path
import stat
import subprocess
import sys
import threading
import time
import uuid


SCHEMA = "code-skill-dependency-operation/v1"
MARKER = "skill-dependency-operation.json"
GATE = threading.RLock()
MAX_BYTES = 64 * 1024
TARGET_FIELDS = {"dataRootId", "installationId", "revisionId", "manifestHash", "capability"}
STATES = {"running", "exited", "settled"}


class DependencyOperationError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def fail(code):
    raise DependencyOperationError(code)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def fingerprint(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def serialized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with GATE:
            return function(*args, **kwargs)
    return wrapped


def _safe(path, *, directory=False, missing=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing:
            return False
        fail("dependency_operation_path_unavailable")
    if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
            or (not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))
            or (directory and not stat.S_ISDIR(info.st_mode))):
        fail("dependency_operation_path_unsafe")
    return True


def check_runtime_paths(data_root, plan):
    root = Path(data_root).absolute()
    for relative in ("runtime", "runtime/python", "runtime/python/Scripts", "runtime/python/Lib",
                     "runtime/python/Lib/site-packages", "runtime/node", "runtime/node/node_modules"):
        _safe(root / relative, directory=True, missing=True)
    for relative in ("runtime/python/Scripts/python.exe", "runtime/python/python.exe"):
        _safe(root / relative, missing=True)
    for step in plan.get("steps", []):
        for raw in step.get("_ensureDirectories", []):
            try:
                Path(raw).absolute().relative_to(root / "runtime")
            except ValueError:
                fail("dependency_operation_path_unsafe")


def _validate_settlement(value):
    binding, target = value["binding"], value["target"]
    if "target" in binding:
        valid = set(binding) == {"target", "runtime", "checkedAt"} and binding["target"] == target
    else:
        valid = (set(binding) == {"version", "authority", "capability", "checkedStatus", "manifestHash", "runtime", "checkedAt"}
                 and type(binding.get("version")) is int and binding["version"] == 2
                 and isinstance(binding.get("authority"), dict)
                 and binding["authority"].get("installationId") == target["installationId"]
                 and binding["authority"].get("revisionId") == target["revisionId"]
                 and binding["manifestHash"] == target["manifestHash"]
                 and binding["capability"] == target["capability"] and binding["checkedStatus"] == "ready")
    if not valid or not isinstance(binding.get("checkedAt"), str) or not binding["checkedAt"]:
        fail("dependency_operation_binding_invalid")
    from .skill_runtime_v2 import _normalize_runtime
    try:
        if _normalize_runtime(binding["runtime"]) != binding["runtime"]:
            fail("dependency_operation_binding_invalid")
    except (ValueError, RuntimeError, TypeError):
        fail("dependency_operation_binding_invalid")


class DependencyOperation:
    def __init__(self, data_root):
        self.root = Path(data_root).absolute()
        self.path = self.root / MARKER

    def read(self):
        # No bootstrap, directories, or mutation lock on a read.
        if not _safe(self.root, directory=True, missing=True):
            return None
        if list(self.root.glob(MARKER + ".tmp-*")):
            fail("dependency_operation_interrupted")
        if not _safe(self.path, missing=True):
            return None
        if self.path.stat().st_size > MAX_BYTES:
            fail("dependency_operation_invalid")
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            fail("dependency_operation_invalid")
        fields = {"schema", "operationId", "requester", "target", "planFingerprint",
                  "state", "result", "binding", "digest"}
        if (not isinstance(value, dict) or set(value) != fields or value["schema"] != SCHEMA
                or not isinstance(value["state"], str) or value["state"] not in STATES or not isinstance(value["target"], dict)
                or set(value["target"]) != TARGET_FIELDS
                or any(not isinstance(v, str) or not v or len(v) > 256 for v in value["target"].values())
                or not isinstance(value["requester"], str) or len(value["requester"]) > 128
                or not isinstance(value["result"], dict)
                or not isinstance(value["binding"], dict)
                or not isinstance(value["operationId"], str) or not re.fullmatch(r"[0-9a-f]{32}", value["operationId"])
                or not isinstance(value["planFingerprint"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["planFingerprint"])
                or value["digest"] != fingerprint({k: v for k, v in value.items() if k != "digest"})
                or (value["state"] == "settled" and not value["binding"])):
            fail("dependency_operation_invalid")
        if value["state"] == "settled":
            _validate_settlement(value)
        result = value["result"]
        if value["state"] == "running":
            if result or value["binding"]:
                fail("dependency_operation_invalid")
        elif (result.get("writerExited") is not True or type(result.get("ok")) is not bool
                or set(result) - {"ok", "errorCode", "cancelled", "timedOut", "writerExited", "exitCode"}
                or any(type(result[key]) is not bool for key in ("cancelled", "timedOut") if key in result)
                or ("exitCode" in result and type(result["exitCode"]) is not int)
                or ("errorCode" in result and not isinstance(result["errorCode"], str))
                or (result["ok"] and (result.get("cancelled") or result.get("timedOut")))
                or (value["state"] == "exited" and value["binding"])):
            fail("dependency_operation_invalid")
        return value

    def _write(self, value, owner):
        from .data_dir_owner import DataDirOwner
        if (not isinstance(owner, DataDirOwner) or owner.released
                or os.path.normcase(str(owner.data_dir.resolve())) != os.path.normcase(str(self.root.resolve()))):
            fail("dependency_operation_owner_required")
        _safe(self.root, directory=True)
        _safe(self.path, missing=True)
        value = copy.deepcopy(value)
        value["digest"] = fingerprint({k: v for k, v in value.items() if k != "digest"})
        raw = _canonical(value)
        if len(raw) > MAX_BYTES:
            fail("dependency_operation_too_large")
        temporary = self.root / (MARKER + ".tmp-" + uuid.uuid4().hex)
        # Deliberately retain an incomplete temporary file on any failure.
        with temporary.open("xb") as stream:
            if stream.write(raw) != len(raw):
                fail("dependency_operation_short_write")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)
        if os.name != "nt":
            descriptor = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return value

    def assert_available(self):
        value = self.read()
        if value and value["state"] != "settled":
            fail("dependency_operation_unsettled")

    def begin(self, target, requester, plan, owner):
        with GATE:
            previous = self.read()
            if previous and previous["state"] != "settled":
                if previous["state"] == "running":
                    fail("dependency_writer_unknown")
                if previous["target"] != target:
                    fail("dependency_operation_target_conflict")
            value = {"schema": SCHEMA, "operationId": uuid.uuid4().hex,
                     "requester": requester, "target": copy.deepcopy(target),
                     "planFingerprint": fingerprint(plan), "state": "running",
                     "result": {}, "binding": {}}
            return self._write(value, owner)

    def exited(self, operation_id, result, owner):
        with GATE:
            value = self.read()
            if not value or value["operationId"] != operation_id or value["state"] != "running":
                fail("dependency_operation_identity_conflict")
            if result.get("writerExited") is not True:
                return value
            value.update(state="exited", result={key: result[key] for key in (
                "ok", "errorCode", "cancelled", "timedOut", "writerExited", "exitCode",
            ) if key in result})
            return self._write(value, owner)

    def settle(self, target, binding, owner):
        with GATE:
            value = self.read()
            if not value or value["state"] != "exited" or value["target"] != target:
                fail("dependency_operation_not_settleable")
            if not isinstance(binding, dict) or not binding:
                fail("dependency_operation_binding_required")
            value.update(state="settled", binding=copy.deepcopy(binding))
            _validate_settlement(value)
            return self._write(value, owner)


class _WindowsJob:
    """Keep the one gated installer and all descendants in a Windows job."""
    def __init__(self):
        if os.name != "nt":
            fail("dependency_writer_platform_unsupported")
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.types = ctypes, wintypes
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        self.api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        class BasicLimit(ctypes.Structure):
            _fields_ = [("processTime", ctypes.c_longlong), ("jobTime", ctypes.c_longlong),
                        ("flags", wintypes.DWORD), ("minWorkingSet", ctypes.c_size_t),
                        ("maxWorkingSet", ctypes.c_size_t), ("activeLimit", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]
        class ExtendedLimit(ctypes.Structure):
            _fields_ = [("basic", BasicLimit), ("ioCounters", ctypes.c_ulonglong * 6),
                        ("processMemory", ctypes.c_size_t), ("jobMemory", ctypes.c_size_t),
                        ("peakProcessMemory", ctypes.c_size_t), ("peakJobMemory", ctypes.c_size_t)]
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            fail("dependency_writer_containment_unavailable")
        info = ExtendedLimit()
        info.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE; no breakaway permissions.
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            fail("dependency_writer_containment_unavailable")

    def attach(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, self.types.HANDLE(process._handle)):
            fail("dependency_writer_containment_unavailable")

    def empty(self):
        class Accounting(self.ctypes.Structure):
            _fields_ = [("times", self.ctypes.c_longlong * 4), ("faults", self.types.DWORD),
                        ("total", self.types.DWORD), ("active", self.types.DWORD), ("terminated", self.types.DWORD)]
        value = Accounting()
        if not self.api.QueryInformationJobObject(self.handle, 1, self.ctypes.byref(value), self.ctypes.sizeof(value), None):
            fail("dependency_writer_exit_unknown")
        return value.active == 0

    def stop(self):
        if not self.api.TerminateJobObject(self.handle, 1):
            fail("dependency_writer_exit_unknown")

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def worker_command(host_python=None):
    source = (Path(sys._MEIPASS) / "dependency-worker" / "code_runtime" / Path(__file__).name
              if getattr(sys, "frozen", False) else Path(__file__).absolute())
    executable = host_python or ("" if getattr(sys, "frozen", False) else sys.executable)
    if not executable or not Path(executable).is_file() or not source.is_file():
        return []
    return [str(executable), "-B", str(source), "--worker"]


def execute_contained(plan, *, cancel_event=None, timeout_seconds=300, worker_argv=None):
    """Release a plan only after containment; never infer exit from a dead PID."""
    if cancel_event is not None and cancel_event.is_set():
        return {"ok": False, "cancelled": True, "errorCode": "cancelled", "writerExited": True}
    job, process = None, None
    released = False
    result = {"ok": False, "errorCode": "dependency_writer_exit_unknown", "writerExited": False}
    try:
        job = _WindowsJob()
        # This child reads stdin before importing the executor or creating paths.
        process = subprocess.Popen(
            list(worker_argv or worker_command()),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        job.attach(process)
        released = True
        deadline = time.monotonic() + max(1, min(int(timeout_seconds), 300))
        payload = json.dumps(plan)
        while True:
            try:
                output, _ = process.communicate(payload, timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                payload = None
                cancelled = bool(cancel_event and cancel_event.is_set())
                if cancelled or time.monotonic() >= deadline:
                    job.stop()
                    output, _ = process.communicate(timeout=5)
                    result.update(errorCode="cancelled" if cancelled else "timeout",
                                  cancelled=cancelled, timedOut=not cancelled)
                    break
        if not result.get("cancelled") and not result.get("timedOut"):
            if process.returncode == 0:
                result = json.loads(output)
            else:
                result = {"ok": False, "errorCode": "dependency_worker_failed", "exitCode": process.returncode}
        # Successful parent exit is insufficient: stop leftover job descendants
        # and report failure, then verify the entire job reaches zero processes.
        if not job.empty():
            job.stop()
            result = {"ok": False, "errorCode": "dependency_descendant_outlived_installer"}
        deadline = time.monotonic() + 5
        while not job.empty() and time.monotonic() < deadline:
            time.sleep(0.01)
        result["writerExited"] = job.empty()
        return result
    except Exception as exc:
        result.update(ok=False, errorCode=getattr(exc, "code", "dependency_writer_exit_unknown"))
        if process is None:
            result["writerExited"] = True
        if process is not None and not released:
            process.kill()
            process.communicate(timeout=5)
            result["writerExited"] = True  # The plan never crossed the stdin gate.
        return result
    finally:
        if job is not None:
            job.close()


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        raise SystemExit(2)
    raw = sys.stdin.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise SystemExit(2)
    plan = json.loads(raw)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from code_runtime.skill_dependencies import execute_dependency_operation_plan
    print(json.dumps(execute_dependency_operation_plan(plan)))
