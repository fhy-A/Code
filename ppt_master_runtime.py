"""Code-owned, offline PPT Master runtime boundary.

This module owns input confinement, dependency/vendor verification, process
lifecycle, atomic publication, and restart-safe receipts.  The vendored source
is never placed on ``PYTHONPATH`` and no user-controlled command or output path
is accepted.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
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
PYTHON_ROOT = MANAGED_PYTHON.parents[1]
WORKER_PATH = APP_ROOT / "scripts" / "ppt_master_worker.py"
LOCK_PATH = SKILL_ROOT / "dependency-lock.json"
DEPENDENCY_RECEIPT_PATH = SKILL_ROOT / "dependency-receipt.json"
EXPECTED_DEPENDENCY_RECEIPT_DIGEST = "c6930137d85d570ea171be06e4b7d97909f979ba6bf32c502184677bfebfc73c"
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


def _path_lexists(path: Path) -> bool:
    return os.path.lexists(str(path))


def _assert_owned_path(root: Path, path: Path, *, directory: bool) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise PptMasterRuntimeError(
            "ppt_master_path_invalid", "Run-owned file escaped its directory."
        ) from exc
    _assert_regular_path(root, directory=True)
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        if not _path_lexists(current):
            raise PptMasterRuntimeError("ppt_master_path_invalid", "Expected run-owned file is missing.")
        _assert_regular_path(
            current,
            directory=directory if index == len(relative.parts) - 1 else True,
        )


def _assert_owned_regular_file(root: Path, path: Path) -> None:
    _assert_owned_path(root, path, directory=False)
    if path.lstat().st_nlink != 1:
        raise PptMasterRuntimeError(
            "ppt_master_reparse_blocked", "Linked files are not allowed in run-owned paths."
        )


def _assert_owned_regular_directory(root: Path, path: Path) -> None:
    _assert_owned_path(root, path, directory=True)


def _canonical_distribution_name(value: object) -> str:
    return re.sub(r"[-_.]+", "-", str(value or "").strip()).lower()


def _managed_site_packages() -> Path:
    if os.name == "nt":
        return PYTHON_ROOT / "Lib" / "site-packages"
    library_root = PYTHON_ROOT / "lib"
    _assert_owned_regular_directory(PYTHON_ROOT, library_root)
    candidates = sorted(library_root.glob("python*/site-packages"))
    if len(candidates) != 1:
        raise PptMasterRuntimeError(
            "ppt_master_dependency_integrity", "Managed dependency integrity check failed."
        )
    return candidates[0]


def _dependency_integrity_error() -> PptMasterRuntimeError:
    return PptMasterRuntimeError(
        "ppt_master_dependency_integrity",
        "Managed PPT Master dependencies failed the locked integrity check.",
    )


def _validate_ppt_master_dependency_installation() -> dict:
    _assert_regular_path(PYTHON_ROOT, directory=True)
    _assert_regular_path(LOCK_PATH, directory=False)
    _assert_regular_path(DEPENDENCY_RECEIPT_PATH, directory=False)
    lock_bytes = LOCK_PATH.read_bytes()
    lock = json.loads(lock_bytes.decode("utf-8"))
    receipt = json.loads(DEPENDENCY_RECEIPT_PATH.read_text(encoding="utf-8"))
    receipt_digest = hashlib.sha256(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if (
        lock.get("skill") != "ppt-master"
        or lock.get("capability") != "offline-core"
        or receipt.get("schema") != "code-ppt-master-dependency-receipt/v1"
        or receipt.get("status") != "installed"
        or receipt.get("skill") != "ppt-master"
        or receipt.get("capability") != "offline-core"
        or receipt.get("managedRuntime") != "data/runtime/python"
        or receipt.get("lockSha256") != hashlib.sha256(lock_bytes).hexdigest()
        or receipt_digest != EXPECTED_DEPENDENCY_RECEIPT_DIGEST
    ):
        raise _dependency_integrity_error()

    locked = {
        _canonical_distribution_name(item.get("project")): item
        for item in lock.get("wheels", [])
        if item.get("project")
    }
    admitted = {"skia-pathops": "0.9.2", "uharfbuzz": "0.50.0"}
    if set(locked) != set(admitted) or any(
        str(locked[name].get("version")) != version
        or not re.fullmatch(r"[0-9a-f]{64}", str(locked[name].get("sha256") or ""))
        for name, version in admitted.items()
    ):
        raise _dependency_integrity_error()
    received = {
        _canonical_distribution_name(item.get("project")): item
        for item in receipt.get("packages", [])
        if item.get("project")
    }
    if set(received) != set(admitted):
        raise _dependency_integrity_error()
    for name, version in admitted.items():
        item = received[name]
        if (
            str(item.get("version")) != version
            or item.get("wheelSha256") != locked[name].get("sha256")
            or not re.fullmatch(r"[A-Za-z0-9_.-]+\.dist-info", str(item.get("distInfo") or ""))
            or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("recordSha256") or ""))
        ):
            raise _dependency_integrity_error()

    site_packages = _managed_site_packages()
    _assert_owned_regular_directory(PYTHON_ROOT, site_packages)
    target_dist_infos: dict[str, list[tuple[Path, str, str]]] = {name: [] for name in admitted}
    for directory in site_packages.glob("*.dist-info"):
        stem = directory.name[:-len(".dist-info")]
        candidate_name = _canonical_distribution_name(stem.rsplit("-", 1)[0])
        if candidate_name not in admitted:
            continue
        _assert_owned_regular_file(site_packages, directory / "METADATA")
        metadata = (directory / "METADATA").read_text(encoding="utf-8")
        fields = {}
        for line in metadata.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key in {"Name", "Version"} and key not in fields:
                fields[key] = value.strip()
        actual_name = _canonical_distribution_name(fields.get("Name"))
        if actual_name in admitted:
            target_dist_infos[actual_name].append((directory, fields.get("Version", ""), directory.name))

    checked_files = 0
    for name, version in admitted.items():
        matches = target_dist_infos[name]
        expected_dist_info = str(received[name]["distInfo"])
        if len(matches) != 1 or matches[0][1] != version or matches[0][2] != expected_dist_info:
            raise _dependency_integrity_error()
        dist_dir = matches[0][0]
        record_path = dist_dir / "RECORD"
        _assert_owned_regular_file(site_packages, record_path)
        record_bytes = record_path.read_bytes()
        if hashlib.sha256(record_bytes).hexdigest() != received[name]["recordSha256"]:
            raise _dependency_integrity_error()
        record_relative = record_path.relative_to(site_packages).as_posix()
        rows = list(csv.reader(record_bytes.decode("utf-8").splitlines()))
        if not rows:
            raise _dependency_integrity_error()
        seen_paths = set()
        for row in rows:
            if len(row) != 3:
                raise _dependency_integrity_error()
            relative_name, encoded_hash, size_text = row
            relative = PurePosixPath(relative_name)
            if (
                not relative_name
                or "\\" in relative_name
                or relative.is_absolute()
                or any(part in {"", ".", ".."} for part in relative.parts)
                or relative_name in seen_paths
            ):
                raise _dependency_integrity_error()
            seen_paths.add(relative_name)
            installed_file = site_packages.joinpath(*relative.parts)
            _assert_owned_regular_file(site_packages, installed_file)
            if relative_name == record_relative:
                if encoded_hash or size_text:
                    raise _dependency_integrity_error()
                continue
            if not encoded_hash.startswith("sha256=") or not size_text.isdigit():
                raise _dependency_integrity_error()
            payload = installed_file.read_bytes()
            actual_hash = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode("ascii")
            if encoded_hash[7:] != actual_hash or int(size_text) != len(payload):
                raise _dependency_integrity_error()
            checked_files += 1
        if record_relative not in seen_paths:
            raise _dependency_integrity_error()
    return {"ok": True, "receipt": receipt, "lock": lock, "checkedFiles": checked_files}


def validate_ppt_master_dependency_installation() -> dict:
    try:
        return _validate_ppt_master_dependency_installation()
    except PptMasterRuntimeError as exc:
        if exc.code == "ppt_master_dependency_integrity":
            raise
        raise _dependency_integrity_error() from None
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, json.JSONDecodeError, csv.Error):
        raise _dependency_integrity_error() from None


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
        if _path_lexists(current):
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
    dependencies = validate_ppt_master_dependency_installation()
    vendor = validate_vendor_package(SKILL_ROOT)
    return {"receipt": dependencies["receipt"], "vendor": vendor}


def _run_id(value: object) -> str:
    run_id = str(value or "")
    if not _RUN_ID_RE.fullmatch(run_id):
        raise PptMasterRuntimeError("ppt_master_run_id_invalid", "The AgentRun id is invalid.")
    return run_id


def _ensure_directory_chain(root: Path, relative: PurePosixPath) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        if _path_lexists(current):
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
            if _path_lexists(path):
                _assert_regular_path(path, directory=True)
    staging_dir = staging_root / run_id
    return final_dir, staging_dir, (relative_dir / "presentation.pptx").as_posix()


def prepare_ppt_master_preview(payload: dict) -> dict:
    project_root = _project_root(payload.get("_projectRoot"))
    run_id = _run_id(payload.get("_agentRunId"))
    _validate_runtime_contract()
    _normalize_markdown(payload, project_root)
    final_dir, _, relative_path = _target_paths(project_root, run_id, create=False)
    if _path_lexists(final_dir):
        _assert_regular_path(final_dir, directory=True)
        receipt = final_dir / "receipt.json"
        if not _path_lexists(receipt):
            raise PptMasterRuntimeError("ppt_master_output_exists", "The run output directory already exists.")
        _assert_owned_regular_file(final_dir, receipt)
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


def _allowed_pptx_part(name: str) -> bool:
    patterns = (
        r"\[Content_Types\]\.xml",
        r"_rels/\.rels",
        r"docProps/(?:app|core)\.xml",
        r"docProps/thumbnail\.jpeg",
        r"ppt/(?:presProps|presentation|tableStyles|viewProps)\.xml",
        r"ppt/_rels/presentation\.xml\.rels",
        r"ppt/(?:slides|slideLayouts|slideMasters)/(?:slide|slideLayout|slideMaster)[0-9]+\.xml",
        r"ppt/(?:slides|slideLayouts|slideMasters)/_rels/(?:slide|slideLayout|slideMaster)[0-9]+\.xml\.rels",
        r"ppt/theme/theme[0-9]+\.xml",
        r"ppt/charts/chart[0-9]+\.xml",
        r"ppt/charts/_rels/chart[0-9]+\.xml\.rels",
        r"ppt/embeddings/Microsoft_Excel_Sheet[0-9]+\.xlsx",
        r"ppt/printerSettings/printerSettings[0-9]+\.bin",
    )
    return any(re.fullmatch(pattern, name) for pattern in patterns)


def _validate_chart_workbook(payload: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as workbook:
            listed_names = workbook.namelist()
            names = set(listed_names)
            if len(names) != len(listed_names):
                raise PptMasterRuntimeError(
                    "ppt_master_forbidden_part", "Embedded chart workbook has duplicate parts."
                )
            allowed_patterns = (
                r"\[Content_Types\]\.xml",
                r"_rels/\.rels",
                r"docProps/(?:app|core)\.xml",
                r"xl/_rels/workbook\.xml\.rels",
                r"xl/(?:sharedStrings|styles|workbook)\.xml",
                r"xl/theme/theme[0-9]+\.xml",
                r"xl/worksheets/sheet[0-9]+\.xml",
            )
            if not {"[Content_Types].xml", "xl/workbook.xml"} <= names:
                raise PptMasterRuntimeError(
                    "ppt_master_forbidden_part", "Embedded chart workbook is invalid."
                )
            for name in names:
                path = PurePosixPath(name)
                if (
                    path.is_absolute()
                    or any(part in {"", ".", ".."} for part in path.parts)
                    or not any(re.fullmatch(pattern, name) for pattern in allowed_patterns)
                ):
                    raise PptMasterRuntimeError(
                        "ppt_master_forbidden_part", "Embedded chart workbook contains a forbidden part."
                    )
            workbook_content_types = ET.fromstring(workbook.read("[Content_Types].xml"))
            allowed_workbook_content_types = {
                "application/xml",
                "application/vnd.openxmlformats-package.relationships+xml",
                "application/vnd.openxmlformats-package.core-properties+xml",
                "application/vnd.openxmlformats-officedocument.extended-properties+xml",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml",
                "application/vnd.openxmlformats-officedocument.theme+xml",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml",
            }
            if any(
                str(item.attrib.get("ContentType") or "") not in allowed_workbook_content_types
                for item in workbook_content_types
            ):
                raise PptMasterRuntimeError(
                    "ppt_master_forbidden_part", "Embedded chart workbook has a forbidden content type."
                )
            for info in workbook.infolist():
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_IFMT(unix_mode) == stat.S_IFLNK or (info.flag_bits & 0x1):
                    raise PptMasterRuntimeError(
                        "ppt_master_forbidden_part", "Embedded chart workbook has an unsafe ZIP member."
                    )
            for name in names:
                if not name.endswith(".rels"):
                    continue
                source = _relationship_source(name)
                base = PurePosixPath(source).parent.as_posix() if source else ""
                root = ET.fromstring(workbook.read(name))
                allowed_relationship_types = {
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties",
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings",
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles",
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme",
                    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
                    "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties",
                }
                for rel in root:
                    if str(rel.attrib.get("TargetMode") or "").lower() == "external":
                        raise PptMasterRuntimeError(
                            "ppt_master_forbidden_part", "Embedded chart workbook has an external relationship."
                        )
                    if str(rel.attrib.get("Type") or "") not in allowed_relationship_types:
                        raise PptMasterRuntimeError(
                            "ppt_master_forbidden_part", "Embedded chart workbook relationship type is forbidden."
                        )
                    target = str(rel.attrib.get("Target") or "").replace("\\", "/")
                    resolved = posixpath.normpath(posixpath.join(base, target))
                    if (
                        not target
                        or target.startswith("/")
                        or resolved == ".."
                        or resolved.startswith("../")
                        or resolved not in names
                    ):
                        raise PptMasterRuntimeError(
                            "ppt_master_forbidden_part", "Embedded chart workbook relationship is unsafe."
                        )
    except (ET.ParseError, zipfile.BadZipFile) as exc:
        raise PptMasterRuntimeError(
            "ppt_master_forbidden_part", "Embedded chart workbook failed validation."
        ) from exc


def _validate_pptx(path: Path, *, owned_root: Path | None = None) -> dict:
    if owned_root is None:
        _assert_regular_path(path, directory=False)
    else:
        _assert_owned_regular_file(owned_root, path)
    if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > MAX_OUTPUT_BYTES:
        raise PptMasterRuntimeError("ppt_master_output_invalid", "Generated PPTX size is invalid.")
    try:
        with zipfile.ZipFile(path) as archive:
            listed_names = archive.namelist()
            names = set(listed_names)
            if len(names) != len(listed_names):
                raise PptMasterRuntimeError(
                    "ppt_master_forbidden_part", "Generated PPTX contains duplicate internal parts."
                )
            for info in archive.infolist():
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_IFMT(unix_mode) == stat.S_IFLNK or (info.flag_bits & 0x1):
                    raise PptMasterRuntimeError(
                        "ppt_master_forbidden_part", "Generated PPTX contains an unsafe ZIP member."
                    )
            required = {"[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml"}
            if not required <= names:
                raise PptMasterRuntimeError("ppt_master_ooxml_invalid", "Generated PPTX is missing required OOXML parts.")
            for name in names:
                member = PurePosixPath(name)
                if member.is_absolute() or any(part in {"", ".", ".."} for part in member.parts):
                    raise PptMasterRuntimeError("ppt_master_ooxml_invalid", "Generated PPTX has an unsafe part path.")
                if not _allowed_pptx_part(name):
                    raise PptMasterRuntimeError(
                        "ppt_master_forbidden_part", "Generated PPTX contains a forbidden internal part."
                    )
            if archive.testzip() is not None:
                raise PptMasterRuntimeError("ppt_master_ooxml_invalid", "Generated PPTX has a corrupt ZIP member.")
            content_types = ET.fromstring(archive.read("[Content_Types].xml"))
            allowed_content_types = {
                "application/xml",
                "image/jpeg",
                "application/vnd.openxmlformats-package.relationships+xml",
                "application/vnd.openxmlformats-package.core-properties+xml",
                "application/vnd.openxmlformats-officedocument.extended-properties+xml",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.openxmlformats-officedocument.drawingml.chart+xml",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
                "application/vnd.openxmlformats-officedocument.presentationml.presProps+xml",
                "application/vnd.openxmlformats-officedocument.presentationml.slide+xml",
                "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml",
                "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml",
                "application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml",
                "application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml",
                "application/vnd.openxmlformats-officedocument.presentationml.printerSettings",
                "application/vnd.openxmlformats-officedocument.theme+xml",
            }
            if any(
                str(item.attrib.get("ContentType") or "") not in allowed_content_types
                for item in content_types
            ):
                raise PptMasterRuntimeError(
                    "ppt_master_forbidden_part", "Generated PPTX declares a forbidden content type."
                )
            chart_workbook_targets = set()
            allowed_relationship_types = {
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/package",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/printerSettings",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps",
                "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties",
                "http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail",
            }
            embeddings = {
                name for name in names
                if re.fullmatch(r"ppt/embeddings/Microsoft_Excel_Sheet[0-9]+\.xlsx", name)
            }
            for name in names:
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
                    relationship_type = str(rel.attrib.get("Type") or "")
                    if relationship_type not in allowed_relationship_types:
                        raise PptMasterRuntimeError(
                            "ppt_master_forbidden_part", "Generated PPTX relationship type is forbidden."
                        )
                    if relationship_type.endswith("/package"):
                        if not source.startswith("ppt/charts/chart") or resolved not in embeddings:
                            raise PptMasterRuntimeError(
                                "ppt_master_forbidden_part", "Forbidden embedded package relationship."
                            )
                        chart_workbook_targets.add(resolved)
            if embeddings != chart_workbook_targets:
                raise PptMasterRuntimeError(
                    "ppt_master_forbidden_part", "Chart workbook ownership is incomplete."
                )
            for name in embeddings:
                _validate_chart_workbook(archive.read(name))
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
    if _path_lexists(temp):
        raise PptMasterRuntimeError("ppt_master_path_invalid", "Atomic staging path already exists.")
    with temp.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    os.replace(temp, path)


def _validate_staging_files(staging_dir: Path) -> None:
    for name in ("prepared.json", "request.json", "worker-result.json", "presentation.pptx"):
        path = staging_dir / name
        if _path_lexists(path):
            _assert_owned_regular_file(staging_dir, path)


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
    if not _path_lexists(final_dir):
        return None
    _assert_regular_path(final_dir, directory=True)
    receipt_path, deck = final_dir / "receipt.json", final_dir / "presentation.pptx"
    if not _path_lexists(receipt_path) or not _path_lexists(deck):
        raise PptMasterRuntimeError("ppt_master_output_exists", "The run output directory is not a completed receipt.")
    _assert_owned_regular_file(final_dir, receipt_path)
    _assert_owned_regular_file(final_dir, deck)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        receipt.get("schema") != "code-ppt-master-output-receipt/v1"
        or receipt.get("operationId") != operation_id
        or receipt.get("inputSha256") != input_sha256
        or receipt.get("deckSha256") != _sha256(deck)
    ):
        raise PptMasterRuntimeError("ppt_master_output_conflict", "Existing output does not match this execution.")
    metrics = _validate_pptx(deck, owned_root=final_dir)
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

        if _path_lexists(staging_dir):
            _assert_regular_path(staging_dir, directory=True)
            _validate_staging_files(staging_dir)
            prepared_path = staging_dir / "prepared.json"
            result_path = staging_dir / "worker-result.json"
            deck = staging_dir / "presentation.pptx"
            prepared = json.loads(prepared_path.read_text(encoding="utf-8")) if _path_lexists(prepared_path) else {}
            if prepared.get("operationId") != operation_id or prepared.get("inputSha256") != input_sha256:
                raise PptMasterRuntimeError("ppt_master_staging_conflict", "Existing run staging belongs to another execution.")
            if _path_lexists(result_path) and _path_lexists(deck):
                worker_result = json.loads(result_path.read_text(encoding="utf-8"))
                metrics = _validate_pptx(deck, owned_root=staging_dir)
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
            _validate_staging_files(staging_dir)
            if not _path_lexists(result_path):
                shutil.rmtree(staging_dir, ignore_errors=True)
                raise PptMasterRuntimeError("ppt_master_worker_failed", "PPT worker result is missing.")
            worker_result = json.loads(result_path.read_text(encoding="utf-8"))
            metrics = _validate_pptx(deck, owned_root=staging_dir)
            if worker_result.get("deckSha256") != _sha256(deck):
                shutil.rmtree(staging_dir, ignore_errors=True)
                raise PptMasterRuntimeError("ppt_master_output_invalid", "PPT worker output hash is invalid.")

        _clean_worker_residue(staging_dir)
        deck = staging_dir / "presentation.pptx"
        metrics = _validate_pptx(deck, owned_root=staging_dir)
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
        if _path_lexists(final_dir):
            raise PptMasterRuntimeError("ppt_master_output_exists", "The run output directory appeared before publish.")
        try:
            os.rename(staging_dir, final_dir)
        except OSError as exc:
            raise PptMasterRuntimeError("ppt_master_publish_failed", "Atomic PPT publication failed.") from exc
        return _public_success(relative_path, final_dir / "presentation.pptx", metrics, replayed=False)
