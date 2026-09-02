"""Render one validated PPTX to PDF through a verified LibreOffice install.

The resource is intentionally self-contained: it accepts the exact deck and
output directory supplied by the current task, uses argument arrays and an
isolated LibreOffice profile, and never discovers helper scripts elsewhere.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from office.validate import PptxValidationError, validate_presentation


SCHEMA = "code-pptx-render/v1"
DEFAULT_TIMEOUT_SECONDS = 60
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 300

_PUBLIC_ERRORS = {
    "invalid_arguments": "Usage: render.py DECK.pptx OUTPUT_DIRECTORY [--soffice PATH] [--timeout SECONDS].",
    "invalid_timeout": "timeout must be an integer between 1 and 300.",
    "soffice_not_found": "LibreOffice is required for PPTX rendering but was not found.",
    "soffice_invalid": "The selected LibreOffice executable is not a supported installation.",
    "output_directory_invalid": "The output directory is not available for PPTX rendering.",
    "render_failed": "LibreOffice could not render the presentation.",
    "output_missing": "LibreOffice did not produce the expected PDF.",
    "timeout": "PPTX rendering timed out.",
    "cancelled": "PPTX rendering was cancelled.",
}


class PptxRenderError(RuntimeError):
    def __init__(self, error_code):
        self.error_code = str(error_code or "render_failed")
        super().__init__(_PUBLIC_ERRORS.get(self.error_code, _PUBLIC_ERRORS["render_failed"]))


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
        and not _is_link_or_reparse(path)
        and path.is_file()
        and (path.parent / "soffice.bin").is_file()
        and (path.parent / "fundamental.ini").is_file()
    )


def _candidate_soffice_paths():
    if sys.platform == "win32":
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            value = os.environ.get(variable)
            if value:
                yield Path(value) / "LibreOffice" / "program" / "soffice.exe"
        return
    for name in ("soffice", "libreoffice"):
        value = shutil.which(name)
        if value:
            yield Path(value)


def find_soffice(executable=""):
    candidates = [Path(executable)] if executable else list(_candidate_soffice_paths())
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
    raise PptxRenderError("soffice_invalid" if executable else "soffice_not_found")


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


def _bounded_timeout(value):
    try:
        timeout = int(str(value or DEFAULT_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        raise PptxRenderError("invalid_timeout")
    if not MIN_TIMEOUT_SECONDS <= timeout <= MAX_TIMEOUT_SECONDS:
        raise PptxRenderError("invalid_timeout")
    return timeout


def _output_directory(value):
    directory = Path(value)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise PptxRenderError("output_directory_invalid")
    if _is_link_or_reparse(directory) or not directory.is_dir():
        raise PptxRenderError("output_directory_invalid")
    try:
        return directory.resolve(strict=True)
    except OSError:
        raise PptxRenderError("output_directory_invalid")


def render_presentation(deck, output_directory, *, timeout_seconds=DEFAULT_TIMEOUT_SECONDS, soffice_path=""):
    try:
        validate_presentation(deck)
    except PptxValidationError as exc:
        raise PptxRenderError(exc.error_code) from exc
    deck = Path(deck).resolve(strict=True)
    output_directory = _output_directory(output_directory)
    timeout = _bounded_timeout(timeout_seconds)
    office = find_soffice(soffice_path)
    process = None
    with tempfile.TemporaryDirectory(prefix="code-pptx-render-") as temp:
        profile_dir = Path(temp) / "profile"
        profile_dir.mkdir()
        arguments = [
            str(office),
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            "--nolockcheck",
            f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_directory),
            str(deck),
        ]
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
        try:
            process = subprocess.Popen(arguments, **options)
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _terminate_process_tree(process)
                    raise PptxRenderError("timeout")
                try:
                    process.communicate(timeout=min(0.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode != 0:
                raise PptxRenderError("render_failed")
        except PptxRenderError:
            raise
        except KeyboardInterrupt:
            _terminate_process_tree(process)
            raise PptxRenderError("cancelled")
        except Exception:
            _terminate_process_tree(process)
            raise PptxRenderError("render_failed")
    output = output_directory / f"{deck.stem}.pdf"
    if _is_link_or_reparse(output) or not output.is_file():
        raise PptxRenderError("output_missing")
    return {
        "schema": SCHEMA,
        "status": "success",
        "pdf": str(output.resolve(strict=True)),
    }


def _write_json(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("deck", nargs="?")
    parser.add_argument("output_directory", nargs="?")
    parser.add_argument("--soffice", default="")
    parser.add_argument("--timeout", default=str(DEFAULT_TIMEOUT_SECONDS))
    try:
        arguments = parser.parse_args(argv)
        if not arguments.deck or not arguments.output_directory:
            raise PptxRenderError("invalid_arguments")
        result = render_presentation(
            arguments.deck,
            arguments.output_directory,
            timeout_seconds=_bounded_timeout(arguments.timeout),
            soffice_path=arguments.soffice,
        )
        _write_json(result)
        return 0
    except SystemExit:
        error = PptxRenderError("invalid_arguments")
        _write_json({"schema": SCHEMA, "errorCode": error.error_code, "error": str(error)})
        return 2
    except PptxRenderError as exc:
        _write_json({"schema": SCHEMA, "errorCode": exc.error_code, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
