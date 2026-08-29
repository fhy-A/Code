#!/usr/bin/env python3
"""Audit exact Python wheels without importing or executing their contents.

The validator consumes previously downloaded PyPI JSON and wheel files.  It is
intentionally standard-library only so the admission decision cannot depend on
the candidate distributions.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import re
import stat
import struct
import sys
import zipfile
from email.parser import BytesParser
from email.policy import default
from pathlib import Path, PurePosixPath


class WheelAuditError(RuntimeError):
    """Raised when a wheel violates the locked admission contract."""


def canonical_project_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", str(value or "").strip()).lower()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_zip_name(name: str) -> PurePosixPath:
    if not name or "\\" in name or "\x00" in name:
        raise WheelAuditError(f"unsafe ZIP member name: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise WheelAuditError(f"unsafe ZIP member path: {name!r}")
    if re.match(r"^[A-Za-z]:", name):
        raise WheelAuditError(f"drive-qualified ZIP member path: {name!r}")
    return path


def _rva_offset(payload: bytes, section_offset: int, section_count: int, rva: int) -> int:
    for index in range(section_count):
        offset = section_offset + index * 40
        if offset + 40 > len(payload):
            break
        virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from(
            "<IIII", payload, offset + 8
        )
        span = max(virtual_size, raw_size)
        if virtual_address <= rva < virtual_address + span:
            resolved = raw_offset + (rva - virtual_address)
            if resolved >= len(payload):
                break
            return resolved
    raise WheelAuditError(f"PE RVA 0x{rva:x} is outside file sections")


def pe_imports(payload: bytes) -> list[str]:
    if len(payload) < 64 or payload[:2] != b"MZ":
        raise WheelAuditError("native payload is not a PE image")
    pe_offset = struct.unpack_from("<I", payload, 0x3C)[0]
    if pe_offset + 24 > len(payload) or payload[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise WheelAuditError("native payload has an invalid PE header")
    section_count = struct.unpack_from("<H", payload, pe_offset + 6)[0]
    optional_size = struct.unpack_from("<H", payload, pe_offset + 20)[0]
    optional_offset = pe_offset + 24
    if optional_offset + optional_size > len(payload):
        raise WheelAuditError("native payload has a truncated optional header")
    magic = struct.unpack_from("<H", payload, optional_offset)[0]
    if magic == 0x10B:
        data_directory_offset = optional_offset + 96
    elif magic == 0x20B:
        data_directory_offset = optional_offset + 112
    else:
        raise WheelAuditError(f"unsupported PE optional header: 0x{magic:x}")
    import_rva, import_size = struct.unpack_from("<II", payload, data_directory_offset + 8)
    if not import_rva or not import_size:
        return []
    section_offset = optional_offset + optional_size
    descriptor_offset = _rva_offset(payload, section_offset, section_count, import_rva)
    imports: list[str] = []
    for index in range(4096):
        offset = descriptor_offset + index * 20
        if offset + 20 > len(payload):
            raise WheelAuditError("PE import table is truncated")
        descriptor = struct.unpack_from("<IIIII", payload, offset)
        if descriptor == (0, 0, 0, 0, 0):
            break
        name_rva = descriptor[3]
        name_offset = _rva_offset(payload, section_offset, section_count, name_rva)
        end = payload.find(b"\0", name_offset, min(len(payload), name_offset + 512))
        if end < 0:
            raise WheelAuditError("PE import name is unterminated")
        imports.append(payload[name_offset:end].decode("ascii", errors="strict"))
    else:
        raise WheelAuditError("PE import table is unbounded")
    return sorted(set(imports), key=str.lower)


_WINDOWS_RUNTIME_DLLS = {
    "advapi32.dll",
    "bcrypt.dll",
    "dwrite.dll",
    "gdi32.dll",
    "kernel32.dll",
    "msvcp140.dll",
    "ole32.dll",
    "rpcrt4.dll",
    "shell32.dll",
    "ucrtbase.dll",
    "user32.dll",
    "usp10.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "version.dll",
    "ws2_32.dll",
}


def _classify_native_imports(native_payloads: list[dict]) -> dict:
    bundled = {PurePosixPath(item["path"]).name.lower() for item in native_payloads}
    bundled_imports: set[str] = set()
    external_imports: set[str] = set()
    unexplained_imports: set[str] = set()
    for item in native_payloads:
        for value in item["imports"]:
            normalized = value.lower()
            if normalized in bundled:
                bundled_imports.add(value)
            elif (
                normalized in _WINDOWS_RUNTIME_DLLS
                or normalized.startswith("api-ms-win-")
                or re.fullmatch(r"python3(?:12)?\.dll", normalized)
            ):
                external_imports.add(value)
            else:
                unexplained_imports.add(value)
    return {
        "bundledImports": sorted(bundled_imports, key=str.lower),
        "externalRuntimeImports": sorted(external_imports, key=str.lower),
        "unexplainedImports": sorted(unexplained_imports, key=str.lower),
    }


def _record_digest(payload: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode("ascii")


def audit_wheel(wheel_path: Path, release: dict, expected_name: str, expected_version: str) -> dict:
    selected = next(
        (item for item in release.get("urls", []) if item.get("filename") == wheel_path.name),
        None,
    )
    if not selected:
        raise WheelAuditError(f"{wheel_path.name}: file is absent from official release JSON")
    if selected.get("packagetype") != "bdist_wheel" or selected.get("yanked"):
        raise WheelAuditError(f"{wheel_path.name}: official file is not an admitted wheel")
    actual_sha256 = sha256_file(wheel_path)
    expected_sha256 = str((selected.get("digests") or {}).get("sha256") or "")
    if actual_sha256 != expected_sha256:
        raise WheelAuditError(f"{wheel_path.name}: PyPI SHA-256 mismatch")
    if wheel_path.stat().st_size != int(selected.get("size") or -1):
        raise WheelAuditError(f"{wheel_path.name}: PyPI size mismatch")

    with zipfile.ZipFile(wheel_path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise WheelAuditError(f"{wheel_path.name}: duplicate ZIP members")
        for info in infos:
            _safe_zip_name(info.filename.rstrip("/"))
            if info.flag_bits & 0x1:
                raise WheelAuditError(f"{wheel_path.name}: encrypted ZIP member")
            if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise WheelAuditError(f"{wheel_path.name}: unexpected ZIP compression")
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            if unix_mode and stat.S_ISLNK(unix_mode):
                raise WheelAuditError(f"{wheel_path.name}: symbolic link member")

        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        wheel_names = [name for name in names if name.endswith(".dist-info/WHEEL")]
        record_names = [name for name in names if name.endswith(".dist-info/RECORD")]
        if not (len(metadata_names) == len(wheel_names) == len(record_names) == 1):
            raise WheelAuditError(f"{wheel_path.name}: invalid dist-info cardinality")

        metadata = BytesParser(policy=default).parsebytes(archive.read(metadata_names[0]))
        if canonical_project_name(metadata.get("Name", "")) != canonical_project_name(expected_name):
            raise WheelAuditError(f"{wheel_path.name}: METADATA project mismatch")
        if str(metadata.get("Version", "")) != expected_version:
            raise WheelAuditError(f"{wheel_path.name}: METADATA version mismatch")

        wheel_text = archive.read(wheel_names[0]).decode("utf-8", errors="strict")
        tags = sorted(
            line.split(":", 1)[1].strip()
            for line in wheel_text.splitlines()
            if line.lower().startswith("tag:")
        )
        if not tags or not any(tag.endswith("-win_amd64") for tag in tags):
            raise WheelAuditError(f"{wheel_path.name}: wheel is not Windows x64")
        compatible = any(
            tag.startswith("cp312-cp312-")
            or re.match(r"^cp3(?:[0-1][0-9])-abi3-win_amd64$", tag)
            for tag in tags
        )
        if not compatible:
            raise WheelAuditError(f"{wheel_path.name}: wheel is not compatible with CPython 3.12")

        record_rows = list(csv.reader(io.StringIO(archive.read(record_names[0]).decode("utf-8"))))
        record = {row[0]: row[1:] for row in record_rows if len(row) == 3}
        if set(record) != set(names):
            missing = sorted(set(names) - set(record))
            extra = sorted(set(record) - set(names))
            raise WheelAuditError(
                f"{wheel_path.name}: RECORD members differ; missing={missing}, extra={extra}"
            )
        for info in infos:
            digest_field, size_field = record[info.filename]
            if info.filename == record_names[0]:
                if digest_field or size_field:
                    raise WheelAuditError(f"{wheel_path.name}: RECORD self-entry is not empty")
                continue
            payload = archive.read(info.filename)
            if digest_field != f"sha256={_record_digest(payload)}":
                raise WheelAuditError(f"{wheel_path.name}: RECORD digest mismatch: {info.filename}")
            if size_field != str(len(payload)):
                raise WheelAuditError(f"{wheel_path.name}: RECORD size mismatch: {info.filename}")

        native_payloads = []
        for name in names:
            if PurePosixPath(name).suffix.lower() in {".pyd", ".dll", ".exe"}:
                payload = archive.read(name)
                native_payloads.append(
                    {
                        "path": name,
                        "size": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "imports": pe_imports(payload),
                    }
                )
        if not native_payloads:
            raise WheelAuditError(f"{wheel_path.name}: expected native extension is absent")
        native_imports = _classify_native_imports(native_payloads)
        if native_imports["unexplainedImports"]:
            raise WheelAuditError(
                f"{wheel_path.name}: unexplained PE imports: "
                + ", ".join(native_imports["unexplainedImports"])
            )

        license_files = sorted(
            name for name in names
            if ".dist-info/licenses/" in name.lower()
            or PurePosixPath(name).name.lower().startswith(("license", "copying"))
        )
        if not license_files:
            raise WheelAuditError(f"{wheel_path.name}: packaged license file is absent")

        return {
            "project": expected_name,
            "version": expected_version,
            "filename": wheel_path.name,
            "url": selected.get("url"),
            "size": wheel_path.stat().st_size,
            "sha256": actual_sha256,
            "requiresPython": selected.get("requires_python") or release.get("info", {}).get("requires_python"),
            "wheelTags": tags,
            "metadata": {
                "license": str(metadata.get("License", "")),
                "licenseExpression": str(metadata.get("License-Expression", "")),
                "licenseFiles": license_files,
                "requiresDist": list(metadata.get_all("Requires-Dist", [])),
            },
            "archive": {
                "fileCount": len(infos),
                "uncompressedBytes": sum(info.file_size for info in infos),
                "compressedBytes": sum(info.compress_size for info in infos),
                "symlinks": 0,
                "encryptedMembers": 0,
                "duplicateMembers": 0,
            },
            "nativePayloads": native_payloads,
            "nativeImports": native_imports,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--require", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    requirements = []
    for raw in args.require:
        name, separator, version = raw.partition("==")
        if not separator or not name.strip() or not version.strip():
            raise WheelAuditError(f"invalid exact requirement: {raw!r}")
        requirements.append((name.strip(), version.strip()))
    if not requirements:
        raise WheelAuditError("at least one --require is required")

    wheels = []
    for name, version in requirements:
        json_path = root / f"{name}-{version}.json"
        release = json.loads(json_path.read_text(encoding="utf-8"))
        candidates = []
        canonical = canonical_project_name(name)
        for wheel_path in root.glob("*.whl"):
            if canonical_project_name(wheel_path.name.split("-", 1)[0]) == canonical:
                candidates.append(wheel_path)
        if len(candidates) != 1:
            raise WheelAuditError(f"{name}=={version}: expected one wheel, found {len(candidates)}")
        wheels.append(audit_wheel(candidates[0], release, name, version))

    report = {
        "schemaVersion": 1,
        "source": "https://pypi.org/pypi/<project>/<version>/json",
        "target": {"python": "CPython 3.12", "platform": "Windows x64"},
        "wheels": wheels,
    }
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile, WheelAuditError) as exc:
        print(f"wheel audit failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
