"""Bounded structural validation for one user-supplied PPTX package.

This is a clean-room Code helper built from the public Open Packaging
Conventions and PresentationML layout.  It validates only the explicitly
supplied deck; it never searches for templates, scripts, or sibling folders.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import zipfile
from pathlib import Path


SCHEMA = "code-pptx-validate/v1"
MAX_DECK_BYTES = 256 * 1024 * 1024
MAX_ENTRIES = 8_000
MAX_ENTRY_BYTES = 64 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
_SLIDE_NAME = re.compile(r"ppt/slides/slide[1-9][0-9]*\.xml$")

_PUBLIC_ERRORS = {
    "invalid_arguments": "Usage: validate.py DECK.pptx.",
    "deck_not_found": "The presentation does not exist or is not a regular file.",
    "deck_type_unsupported": "Only .pptx presentations are supported.",
    "deck_too_large": "The presentation is too large to validate safely.",
    "deck_invalid": "The presentation is not a readable PPTX package.",
    "deck_unsafe": "The presentation package contains an unsafe or unsupported entry.",
    "dependency_missing": "The managed PPTX validation dependency is unavailable.",
}


class PptxValidationError(RuntimeError):
    def __init__(self, error_code):
        self.error_code = str(error_code or "deck_invalid")
        super().__init__(_PUBLIC_ERRORS.get(self.error_code, _PUBLIC_ERRORS["deck_invalid"]))


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


def _deck_path(value):
    path = Path(value)
    if _is_link_or_reparse(path) or not path.is_file():
        raise PptxValidationError("deck_not_found")
    if path.suffix.lower() != ".pptx":
        raise PptxValidationError("deck_type_unsupported")
    try:
        if path.stat().st_size > MAX_DECK_BYTES:
            raise PptxValidationError("deck_too_large")
    except OSError:
        raise PptxValidationError("deck_not_found")
    if not zipfile.is_zipfile(path):
        raise PptxValidationError("deck_invalid")
    try:
        return path.resolve(strict=True)
    except OSError:
        raise PptxValidationError("deck_not_found")


def _safe_entry_name(name):
    normalized = str(name or "").replace("\\", "/")
    parts = normalized.split("/")
    return bool(
        normalized
        and not normalized.startswith("/")
        and not normalized.startswith("../")
        and not any(part in {"", ".", ".."} for part in parts)
        and not any(part.startswith(".") and part != ".rels" for part in parts)
    )


def _parse_xml(payload):
    try:
        from defusedxml import ElementTree as safe_element_tree
    except ImportError:
        raise PptxValidationError("dependency_missing")
    try:
        return safe_element_tree.fromstring(payload)
    except Exception:
        raise PptxValidationError("deck_invalid")


def validate_presentation(value):
    """Validate the bounded package structure and return a compact summary."""
    deck = _deck_path(value)
    try:
        with zipfile.ZipFile(deck, "r") as archive:
            entries = archive.infolist()
            if not entries or len(entries) > MAX_ENTRIES:
                raise PptxValidationError("deck_invalid")
            names = set()
            total_uncompressed = 0
            for item in entries:
                if item.is_dir():
                    continue
                if not _safe_entry_name(item.filename):
                    raise PptxValidationError("deck_unsafe")
                if item.filename in names:
                    raise PptxValidationError("deck_invalid")
                names.add(item.filename)
                if item.file_size < 0 or item.file_size > MAX_ENTRY_BYTES:
                    raise PptxValidationError("deck_invalid")
                total_uncompressed += item.file_size
                if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise PptxValidationError("deck_invalid")
            required = {
                "[Content_Types].xml",
                "_rels/.rels",
                "ppt/presentation.xml",
                "ppt/_rels/presentation.xml.rels",
            }
            if not required.issubset(names):
                raise PptxValidationError("deck_invalid")
            content_types = _parse_xml(archive.read("[Content_Types].xml"))
            presentation = _parse_xml(archive.read("ppt/presentation.xml"))
            relationships = _parse_xml(archive.read("ppt/_rels/presentation.xml.rels"))
            if not content_types.tag.endswith("Types"):
                raise PptxValidationError("deck_invalid")
            if not presentation.tag.endswith("presentation"):
                raise PptxValidationError("deck_invalid")
            if not relationships.tag.endswith("Relationships"):
                raise PptxValidationError("deck_invalid")
            if any(name.lower().endswith("vbaproject.bin") for name in names):
                raise PptxValidationError("deck_unsafe")
            slides = sorted(name for name in names if _SLIDE_NAME.fullmatch(name))
            if not slides:
                raise PptxValidationError("deck_invalid")
            for slide in slides:
                _parse_xml(archive.read(slide))
    except PptxValidationError:
        raise
    except (OSError, zipfile.BadZipFile, KeyError):
        raise PptxValidationError("deck_invalid")
    return {
        "schema": SCHEMA,
        "status": "success",
        "slides": len(slides),
    }


def _write_json(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("deck", nargs="?")
    try:
        arguments = parser.parse_args(argv)
        if not arguments.deck:
            raise PptxValidationError("invalid_arguments")
        _write_json(validate_presentation(arguments.deck))
        return 0
    except SystemExit:
        error = PptxValidationError("invalid_arguments")
        _write_json({"schema": SCHEMA, "errorCode": error.error_code, "error": str(error)})
        return 2
    except PptxValidationError as exc:
        _write_json({"schema": SCHEMA, "errorCode": exc.error_code, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
