"""Code-owned, offline PPT Master runtime boundary.

This module owns input confinement, dependency/vendor verification, process
lifecycle, atomic publication, and restart-safe receipts.  The vendored source
is never placed on ``PYTHONPATH`` and no user-controlled command or output path
is accepted.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import shutil
import stat
import subprocess
import threading
import time
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

from scripts.validate_ppt_master_vendor import validate_vendor_package


APP_ROOT = Path(__file__).resolve().parent
SKILL_ROOT = APP_ROOT / "data" / "skills" / "ppt-master"
MANAGED_PYTHON = APP_ROOT / "data" / "runtime" / "python" / (
    "Scripts/python.exe" if os.name == "nt" else "bin/python"
)
WORKER_PATH = APP_ROOT / "scripts" / "ppt_master_worker.py"
LOCK_PATH = SKILL_ROOT / "dependency-lock.json"
DEPENDENCY_RECEIPT_PATH = SKILL_ROOT / "dependency-receipt.json"
MAX_INPUT_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 25 * 1024 * 1024
TIMEOUT_SECONDS = 30
OUTPUT_RELATIVE_ROOT = PurePosixPath("output/ppt-master")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_URL_RE = re.compile(r"(?i)(?:https?|ftp|file)://|\bdata:")
_REMOTE_HTML_RE = re.compile(r"(?is)<\s*(?:img|iframe|object|embed|script|link)\b")
_runtime_lock = threading.Lock()


class PptMasterRuntimeError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        cancelled: bool = False,
        timed_out: bool = False,
        outcome_unknown: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.cancelled = cancelled
        self.timed_out = timed_out
        self.outcome_unknown = outcome_unknown

    def tool_result(self) -> dict:
        return {
            "ok": False,
            "action": "create_ppt_master_deck",
            "errorCode": self.code,
            "error": str(self),
            "cancelled": self.cancelled,
            "timedOut": self.timed_out,
            "outcomeUnknown": self.outcome_unknown,
            "notReplayed": self.outcome_unknown,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_reparse(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _assert_regular_path(path: Path, *, directory: bool | None = None) -> None:
    if path.is_symlink() or _is_reparse(path):
        raise PptMasterRuntimeError("ppt_master_reparse_blocked", "Symlink/reparse paths are not allowed.")
    if directory is True and not path.is_dir():
        raise PptMasterRuntimeError("ppt_master_path_invalid", "Expected a regular directory.")
    if directory is False and not path.is_file():
        raise PptMasterRuntimeError("ppt_master_path_invalid", "Expected a regular file.")


def _project_root(value: object) -> Path:
    raw = str(value or "")
    if not raw:
        raise PptMasterRuntimeError("ppt_master_project_missing", "The AgentRun project root is missing.")
    root = Path(raw).resolve(strict=True)
    _assert_regular_path(root, directory=True)
    return root


def _safe_relative_source(root: Path, value: object) -> Path:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise PptMasterRuntimeError("ppt_master_source_path_invalid", "sourcePath must be project-relative.")
    relative = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise PptMasterRuntimeError("ppt_master_source_path_invalid", "sourcePath contains an unsafe segment.")
    if relative.suffix.lower() not in {".md", ".txt"}:
        raise PptMasterRuntimeError("ppt_master_source_type_blocked", "Only .md and .txt source files are allowed.")
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists():
            _assert_regular_path(current, directory=None)
    target = current.resolve(strict=True)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PptMasterRuntimeError("ppt_master_source_outside_project", "sourcePath escapes the project root.") from exc
    _assert_regular_path(target, directory=False)
    return target


def _normalize_markdown(payload: dict, project_root: Path) -> tuple[str, str, str]:
    has_inline = "markdown" in payload and payload.get("markdown") is not None
    has_path = bool(str(payload.get("sourcePath") or "").strip())
    if has_inline == has_path:
        raise PptMasterRuntimeError(
            "ppt_master_source_ambiguous",
            "Provide exactly one of inline markdown or sourcePath.",
        )
    if has_path:
        source = _safe_relative_source(project_root, payload.get("sourcePath"))
        size = source.stat().st_size
        if size > MAX_INPUT_BYTES:
            raise PptMasterRuntimeError("ppt_master_source_too_large", "The source file exceeds 1 MiB.")
        try:
            text = source.read_bytes().decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise PptMasterRuntimeError("ppt_master_source_encoding", "The source file is not valid UTF-8.") from exc
        source_kind = "project_file"
        source_name = source.relative_to(project_root).as_posix()
    else:
        text = payload.get("markdown")
        if not isinstance(text, str):
            raise PptMasterRuntimeError("ppt_master_source_encoding", "Inline markdown must be a UTF-8 string.")
        source_kind = "inline"
        source_name = "inline.md"
    try:
        raw = text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise PptMasterRuntimeError("ppt_master_source_encoding", "The source is not valid UTF-8.") from exc
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise PptMasterRuntimeError("ppt_master_source_too_large", "The source must be 1 byte to 1 MiB.")
    if "\x00" in text:
        raise PptMasterRuntimeError("ppt_master_source_invalid", "NUL bytes are not allowed.")
    if _URL_RE.search(text) or _REMOTE_HTML_RE.search(text):
        raise PptMasterRuntimeError(
            "ppt_master_remote_content_blocked",
            "URLs, remote resources, and active HTML are not allowed in the offline pilot.",
        )
    return text.replace("\r\n", "\n").replace("\r", "\n"), source_kind, source_name


def _validate_runtime_contract() -> dict:
    if not MANAGED_PYTHON.is_file() or not WORKER_PATH.is_file():
        raise PptMasterRuntimeError("ppt_master_runtime_unavailable", "The managed runtime is incomplete.")
    _assert_regular_path(MANAGED_PYTHON, directory=False)
    lock_bytes = LOCK_PATH.read_bytes()
    receipt = json.loads(DEPENDENCY_RECEIPT_PATH.read_text(encoding="utf-8"))
    if receipt.get("schema") != "code-ppt-master-dependency-receipt/v1":
        raise PptMasterRuntimeError("ppt_master_receipt_invalid", "The dependency receipt schema is invalid.")
    if receipt.get("status") != "installed" or receipt.get("capability") != "offline-core":
        raise PptMasterRuntimeError("ppt_master_runtime_unavailable", "The offline-core receipt is not installed.")
    if receipt.get("lockSha256") != hashlib.sha256(lock_bytes).hexdigest():
        raise PptMasterRuntimeError("ppt_master_receipt_invalid", "The dependency lock differs from its receipt.")
    vendor = validate_vendor_package(SKILL_ROOT)
    return {"receipt": receipt, "vendor": vendor}


def _run_id(value: object) -> str:
    run_id = str(value or "")
    if not _RUN_ID_RE.fullmatch(run_id):
        raise PptMasterRuntimeError("ppt_master_run_id_invalid", "The AgentRun id is invalid.")
    return run_id


def _ensure_directory_chain(root: Path, relative: PurePosixPath) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists():
            _assert_regular_path(current, directory=True)
        else:
            current.mkdir()
            _assert_regular_path(current, directory=True)
    return current


def _target_paths(project_root: Path, run_id: str, *, create: bool) -> tuple[Path, Path, str]:
    relative_dir = OUTPUT_RELATIVE_ROOT / run_id
    final_dir = project_root.joinpath(*relative_dir.parts)
    if create:
        output_root = _ensure_directory_chain(project_root, OUTPUT_RELATIVE_ROOT)
        staging_root = _ensure_directory_chain(project_root, OUTPUT_RELATIVE_ROOT / ".staging")
    else:
        output_root = project_root.joinpath(*OUTPUT_RELATIVE_ROOT.parts)
        staging_root = output_root / ".staging"
        for path in (project_root / "output", output_root, staging_root):
            if path.exists():
                _assert_regular_path(path, directory=True)
    staging_dir = staging_root / run_id
    return final_dir, staging_dir, (relative_dir / "presentation.pptx").as_posix()


def prepare_ppt_master_preview(payload: dict) -> dict:
    project_root = _project_root(payload.get("_projectRoot"))
    run_id = _run_id(payload.get("_agentRunId"))
    _validate_runtime_contract()
    _normalize_markdown(payload, project_root)
    final_dir, _, relative_path = _target_paths(project_root, run_id, create=False)
    if final_dir.exists():
        receipt = final_dir / "receipt.json"
        if not receipt.is_file():
            raise PptMasterRuntimeError("ppt_master_output_exists", "The run output directory already exists.")
    return {
        "action": "create_ppt_master_deck",
        "path": relative_path,
        "diff": f"Create editable PowerPoint -> {relative_path}",
        "size": 0,
    }


def _relationship_source(name: str) -> str:
    path = PurePosixPath(name)
    if name == "_rels/.rels":
        return ""
    parts = list(path.parts)
    if len(parts) < 3 or parts[-2] != "_rels" or not parts[-1].endswith(".rels"):
        raise PptMasterRuntimeError("ppt_master_ooxml_invalid", f"Invalid relationships part: {name}")
    return PurePosixPath(*parts[:-2], parts[-1][:-5]).as_posix()


def _validate_pptx(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > MAX_OUTPUT_BYTES:
        raise PptMasterRuntimeError("ppt_master_output_invalid", "Generated PPTX size is invalid.")
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise PptMasterRuntimeError("ppt_master_ooxml_invalid", "Generated PPTX has a corrupt ZIP member.")
            names = set(archive.namelist())
            required = {"[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml"}
            if not required <= names:
                raise PptMasterRuntimeError("ppt_master_ooxml_invalid", "Generated PPTX is missing required OOXML parts.")
            if any(name.startswith("ppt/media/") for name in names):
                raise PptMasterRuntimeError("ppt_master_media_blocked", "The offline pilot produced a media part.")
            for name in names:
                member = PurePosixPath(name)
                if member.is_absolute() or any(part in {"", ".", ".."} for part in member.parts):
                    raise PptMasterRuntimeError("ppt_master_ooxml_invalid", "Generated PPTX has an unsafe part path.")
                if not name.endswith(".rels"):
                    continue
                source = _relationship_source(name)
                base = PurePosixPath(source).parent.as_posix() if source else ""
                root = ET.fromstring(archive.read(name))
                for rel in root:
                    if str(rel.attrib.get("TargetMode") or "").lower() == "external":
                        raise PptMasterRuntimeError("ppt_master_external_relationship", "External OOXML relationships are blocked.")
                    target = str(rel.attrib.get("Target") or "").replace("\\", "/")
                    if not target or target.startswith("/"):
                        raise PptMasterRuntimeError("ppt_master_ooxml_invalid", "Invalid OOXML relationship target.")
                    resolved = posixpath.normpath(posixpath.join(base, target))
                    if resolved == ".." or resolved.startswith("../") or resolved not in names:
                        raise PptMasterRuntimeError("ppt_master_ooxml_invalid", "OOXML relationship target is missing or unsafe.")
            slide_names = sorted(
                name for name in names if re.fullmatch(r"ppt/slides/slide[0-9]+\.xml", name)
            )
            if not 1 <= len(slide_names) <= 12:
                raise PptMasterRuntimeError("ppt_master_ooxml_invalid", "Generated PPTX slide count is outside 1..12.")
            namespaces = {
                "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
                "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
                "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
            }
            metrics = {"slides": len(slide_names), "shapes": 0, "tables": 0, "charts": 0}
            for name in slide_names:
                root = ET.fromstring(archive.read(name))
                metrics["shapes"] += len(root.findall(".//p:sp", namespaces))
                metrics["tables"] += len(root.findall(".//a:tbl", namespaces))
                metrics["charts"] += len(root.findall(".//c:chart", namespaces))
            return metrics
    except (OSError, ET.ParseError, zipfile.BadZipFile) as exc:
        raise PptMasterRuntimeError("ppt_master_ooxml_invalid", "Generated PPTX failed OOXML validation.") from exc


def _atomic_json(path: Path, payload: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temp, path)


def _clean_worker_residue(staging_dir: Path) -> None:
    windows_cache = staging_dir / "%SystemDrive%"
    if windows_cache.exists():
        _assert_regular_path(windows_cache, directory=True)
        pending = [windows_cache]
        while pending:
            current = pending.pop()
            for child in current.iterdir():
                _assert_regular_path(child)
                if child.is_dir():
                    pending.append(child)
        shutil.rmtree(windows_cache)
    allowed = {
        "presentation.pptx",
        "prepared.json",
        "request.json",
        "worker-result.json",
    }
    extras = sorted(path.name for path in staging_dir.iterdir() if path.name not in allowed)
    if extras:
        raise PptMasterRuntimeError(
            "ppt_master_worker_residue",
            "Worker created unexpected staging entries: " + ", ".join(extras),
        )


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            import signal

            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=3)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def _attach_kill_on_close_job(process: subprocess.Popen):
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class BASIC_LIMIT(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class EXTENDED_LIMIT(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BASIC_LIMIT),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
    info = EXTENDED_LIMIT()
    info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        kernel32.CloseHandle(job)
        raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
    if not kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(process._handle)):
        kernel32.CloseHandle(job)
        raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
    return job


def _close_job(job) -> None:
    if job and os.name == "nt":
        import ctypes

        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(job)


def _public_success(relative_path: str, deck: Path, metrics: dict, *, replayed: bool) -> dict:
    return {
        "ok": True,
        "action": "create_ppt_master_deck",
        "path": relative_path,
        "size": deck.stat().st_size,
        "sha256": _sha256(deck),
        "slideCount": metrics["slides"],
        "shapeCount": metrics["shapes"],
        "tableCount": metrics["tables"],
        "chartCount": metrics["charts"],
        "editable": True,
        "offline": True,
        "replayed": replayed,
    }


def _recover_final(final_dir: Path, operation_id: str, input_sha256: str, relative_path: str) -> dict | None:
    if not final_dir.exists():
        return None
    _assert_regular_path(final_dir, directory=True)
    receipt_path, deck = final_dir / "receipt.json", final_dir / "presentation.pptx"
    if not receipt_path.is_file() or not deck.is_file():
        raise PptMasterRuntimeError("ppt_master_output_exists", "The run output directory is not a completed receipt.")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        receipt.get("schema") != "code-ppt-master-output-receipt/v1"
        or receipt.get("operationId") != operation_id
        or receipt.get("inputSha256") != input_sha256
        or receipt.get("deckSha256") != _sha256(deck)
    ):
        raise PptMasterRuntimeError("ppt_master_output_conflict", "Existing output does not match this execution.")
    metrics = _validate_pptx(deck)
    return _public_success(relative_path, deck, metrics, replayed=True)


def execute_ppt_master_tool(payload: dict) -> dict:
    payload = dict(payload or {})
    cancel_event = payload.pop("_cancelEvent", None)
    operation_id = str(payload.pop("_operationId", "") or "")
    project_root = _project_root(payload.pop("_projectRoot", ""))
    run_id = _run_id(payload.pop("_agentRunId", ""))
    payload.pop("_toolCallId", None)
    if not re.fullmatch(r"[0-9a-f]{64}", operation_id):
        raise PptMasterRuntimeError("ppt_master_operation_invalid", "The execution operation id is invalid.")

    with _runtime_lock:
        contract = _validate_runtime_contract()
        markdown, source_kind, source_name = _normalize_markdown(payload, project_root)
        input_sha256 = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        final_dir, staging_dir, relative_path = _target_paths(project_root, run_id, create=True)
        recovered = _recover_final(final_dir, operation_id, input_sha256, relative_path)
        if recovered:
            return recovered

        if staging_dir.exists():
            _assert_regular_path(staging_dir, directory=True)
            prepared_path = staging_dir / "prepared.json"
            result_path = staging_dir / "worker-result.json"
            deck = staging_dir / "presentation.pptx"
            prepared = json.loads(prepared_path.read_text(encoding="utf-8")) if prepared_path.is_file() else {}
            if prepared.get("operationId") != operation_id or prepared.get("inputSha256") != input_sha256:
                raise PptMasterRuntimeError("ppt_master_staging_conflict", "Existing run staging belongs to another execution.")
            if result_path.is_file() and deck.is_file():
                worker_result = json.loads(result_path.read_text(encoding="utf-8"))
                metrics = _validate_pptx(deck)
                if worker_result.get("deckSha256") != _sha256(deck):
                    raise PptMasterRuntimeError("ppt_master_staging_invalid", "Recovered worker output hash is invalid.")
            else:
                shutil.rmtree(staging_dir)
                raise PptMasterRuntimeError(
                    "ppt_master_previous_outcome_unknown",
                    "A prior worker did not leave a completed receipt; this execution was not replayed.",
                    outcome_unknown=True,
                )
        else:
            staging_dir.mkdir()
            prepared = {
                "schema": "code-ppt-master-prepared/v1",
                "operationId": operation_id,
                "inputSha256": input_sha256,
                "runId": run_id,
            }
            _atomic_json(staging_dir / "prepared.json", prepared)
            request = {
                "schema": "code-ppt-master-worker/v1",
                "runId": run_id,
                "sourceKind": source_kind,
                "sourceName": source_name,
                "markdown": markdown,
                "expectedDependencies": contract["receipt"]["packages"],
            }
            _atomic_json(staging_dir / "request.json", request)
            env = {
                key: os.environ[key]
                for key in ("SystemRoot", "WINDIR", "COMSPEC", "TEMP", "TMP")
                if os.environ.get(key)
            }
            env.update({"PYTHONNOUSERSITE": "1", "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            process = subprocess.Popen(
                [
                    str(MANAGED_PYTHON), "-I", "-B", str(WORKER_PATH),
                    "--request", str(staging_dir / "request.json"),
                    "--output", str(staging_dir / "presentation.pptx"),
                    "--result", str(staging_dir / "worker-result.json"),
                ],
                cwd=str(staging_dir),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
                start_new_session=os.name != "nt",
            )
            job = None
            try:
                job = _attach_kill_on_close_job(process)
            except Exception as exc:
                _terminate_process_tree(process)
                shutil.rmtree(staging_dir, ignore_errors=True)
                raise PptMasterRuntimeError("ppt_master_process_isolation", "Worker process isolation failed.") from exc
            deadline = time.monotonic() + TIMEOUT_SECONDS
            try:
                while process.poll() is None:
                    if cancel_event is not None and cancel_event.is_set():
                        _terminate_process_tree(process)
                        shutil.rmtree(staging_dir, ignore_errors=True)
                        raise PptMasterRuntimeError(
                            "ppt_master_cancelled", "PPT generation was cancelled.", cancelled=True
                        )
                    if time.monotonic() >= deadline:
                        _terminate_process_tree(process)
                        shutil.rmtree(staging_dir, ignore_errors=True)
                        raise PptMasterRuntimeError(
                            "ppt_master_timeout", "PPT generation exceeded 30 seconds.", timed_out=True
                        )
                    time.sleep(0.05)
                stdout, stderr = process.communicate(timeout=2)
            finally:
                _close_job(job)
            if process.returncode:
                shutil.rmtree(staging_dir, ignore_errors=True)
                raise PptMasterRuntimeError(
                    "ppt_master_worker_failed",
                    (stderr or stdout or "PPT worker failed.")[-1000:],
                )
            result_path = staging_dir / "worker-result.json"
            deck = staging_dir / "presentation.pptx"
            if not result_path.is_file():
                shutil.rmtree(staging_dir, ignore_errors=True)
                raise PptMasterRuntimeError("ppt_master_worker_failed", "PPT worker result is missing.")
            worker_result = json.loads(result_path.read_text(encoding="utf-8"))
            metrics = _validate_pptx(deck)
            if worker_result.get("deckSha256") != _sha256(deck):
                shutil.rmtree(staging_dir, ignore_errors=True)
                raise PptMasterRuntimeError("ppt_master_output_invalid", "PPT worker output hash is invalid.")

        _clean_worker_residue(staging_dir)
        deck = staging_dir / "presentation.pptx"
        metrics = _validate_pptx(deck)
        receipt = {
            "schema": "code-ppt-master-output-receipt/v1",
            "operationId": operation_id,
            "runId": run_id,
            "inputSha256": input_sha256,
            "deckSha256": _sha256(deck),
            "size": deck.stat().st_size,
            "metrics": metrics,
            "vendorManifestDigest": contract["vendor"]["manifestDigest"],
            "offline": True,
        }
        _atomic_json(staging_dir / "receipt.json", receipt)
        for private in ("request.json", "prepared.json", "worker-result.json"):
            (staging_dir / private).unlink(missing_ok=True)
        if final_dir.exists():
            raise PptMasterRuntimeError("ppt_master_output_exists", "The run output directory appeared before publish.")
        try:
            os.rename(staging_dir, final_dir)
        except OSError as exc:
            raise PptMasterRuntimeError("ppt_master_publish_failed", "Atomic PPT publication failed.") from exc
        return _public_success(relative_path, final_dir / "presentation.pptx", metrics, replayed=False)
