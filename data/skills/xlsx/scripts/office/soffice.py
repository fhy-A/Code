"""Bounded LibreOffice process adapter for the Code XLSX Skill.

Clean-room implementation based on LibreOffice's documented command-line
interface.  Commands are always argument arrays and use an isolated profile.
"""

from __future__ import annotations

import os
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path


_PUBLIC_ERRORS = {
    "soffice_not_found": "LibreOffice is required for formula recalculation but was not found.",
    "soffice_invalid": "The selected LibreOffice executable is not a supported installation.",
    "cancelled": "LibreOffice recalculation was cancelled.",
    "timeout": "LibreOffice recalculation timed out.",
    "process_failed": "LibreOffice could not recalculate the workbook.",
    "output_missing": "LibreOffice did not produce the expected workbook.",
}


class SofficeError(RuntimeError):
    def __init__(self, error_code):
        self.error_code = str(error_code or "process_failed")
        super().__init__(_PUBLIC_ERRORS.get(self.error_code, _PUBLIC_ERRORS["process_failed"]))


def _is_link_or_reparse(path):
    try:
        metadata = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(metadata.st_mode):
        return True
    attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400) or 0x400)
    return bool(attributes & reparse_flag)


def _valid_windows_installation(path):
    path = Path(path)
    return (
        path.name.lower() == "soffice.exe"
        and path.is_file()
        and not _is_link_or_reparse(path)
        and (path.parent / "soffice.bin").is_file()
        and (path.parent / "fundamental.ini").is_file()
    )


def _candidate_paths():
    if sys.platform == "win32":
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            value = os.environ.get(variable)
            if value:
                yield Path(value) / "LibreOffice" / "program" / "soffice.exe"
        path_candidate = shutil.which("soffice.exe") or shutil.which("soffice")
        if path_candidate:
            yield Path(path_candidate)
        return
    for name in ("soffice", "libreoffice"):
        candidate = shutil.which(name)
        if candidate:
            yield Path(candidate)


def find_soffice(executable=""):
    """Return one verified LibreOffice executable without filesystem search."""
    candidates = [Path(executable)] if executable else list(_candidate_paths())
    for candidate in candidates:
        if sys.platform == "win32":
            if _valid_windows_installation(candidate):
                return candidate.resolve(strict=True)
            continue
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    raise SofficeError("soffice_invalid" if executable else "soffice_not_found")


def _terminate_process_tree(process):
    if process is None or process.poll() is not None:
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
            os.killpg(process.pid, signal.SIGTERM)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass
    try:
        process.wait(timeout=3)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def run_soffice_conversion(
    source,
    output_dir,
    profile_dir,
    *,
    timeout_seconds,
    executable="",
    cancel_event=None,
):
    """Recalculate one copied XLSX through an isolated LibreOffice profile."""
    if cancel_event is not None and cancel_event.is_set():
        raise SofficeError("cancelled")
    source = Path(source)
    output_dir = Path(output_dir)
    profile_dir = Path(profile_dir)
    if not source.is_file() or source.is_symlink():
        raise SofficeError("process_failed")
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)
    office = find_soffice(executable)
    arguments = [
        str(office),
        "--headless",
        "--nologo",
        "--nodefault",
        "--nofirststartwizard",
        "--nolockcheck",
        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
        "--convert-to",
        "xlsx",
        "--outdir",
        str(output_dir.resolve()),
        str(source.resolve()),
    ]
    process = None
    try:
        options = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if os.name == "nt":
            options["creationflags"] = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
        else:
            options["start_new_session"] = True
        process = subprocess.Popen(arguments, **options)
        deadline = time.monotonic() + float(timeout_seconds)
        while True:
            if cancel_event is not None and cancel_event.is_set():
                _terminate_process_tree(process)
                raise SofficeError("cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate_process_tree(process)
                raise SofficeError("timeout")
            try:
                process.communicate(timeout=min(0.1, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode != 0:
            raise SofficeError("process_failed")
    except SofficeError:
        raise
    except KeyboardInterrupt:
        _terminate_process_tree(process)
        raise SofficeError("cancelled")
    except Exception:
        _terminate_process_tree(process)
        raise SofficeError("process_failed")
    expected = output_dir / source.name
    if not expected.is_file() or expected.is_symlink() or _is_link_or_reparse(expected):
        raise SofficeError("output_missing")
    return expected
