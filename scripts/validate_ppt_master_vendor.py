"""Validate the fixed, non-executable PPT Master static vendor slice.

This module never imports vendored Python.  Its optional preparation mode only
copies an allow-listed set of bytes from an already verified upstream tree and
records their Git blob identities.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


SCHEMA = "code-ppt-master-vendor/v1"
ORIGIN = "https://github.com/hugohe3/ppt-master.git"
TAG = "v5.1.0"
COMMIT = "d6bcaf96b7946667f4a8871b0688b903181db527"
TREE = "cd5fad962cf856ccaf0a5101695439cbff30635a"
UPSTREAM_FILE_COUNT = 13_008
UPSTREAM_BYTES = 115_940_805
UPSTREAM_MANIFEST_SHA256 = (
    "0ebe6478337139a98f0f616a84f611238a8e50469ea06f95d22e8bf35ed602ea"
)
MAX_VENDOR_FILES = 1_000
MAX_VENDOR_BYTES = 15 * 1024 * 1024

PYTHON_SEEDS = (
    "svg_to_pptx.drawingml.elements",
    "svg_to_pptx.native_objects",
    "svg_to_pptx.native_objects.inline_formula",
    "svg_to_pptx.native_objects.formula_compiler",
    "pptx_opc_validation",
    "semantic_table",
)

PYTHON_SOURCE_PATHS = (
    "scripts/hyperlink_contract.py",
    "scripts/language_tags.py",
    "scripts/pptx_effects.py",
    "scripts/pptx_gradients.py",
    "scripts/pptx_opc_validation.py",
    "scripts/pptx_shapes/__init__.py",
    "scripts/pptx_shapes/errors.py",
    "scripts/pptx_shapes/formula.py",
    "scripts/pptx_shapes/loader.py",
    "scripts/pptx_shapes/models.py",
    "scripts/pptx_shapes/registry.py",
    "scripts/pptx_shapes/semantic_hash.py",
    "scripts/pptx_shapes/semantics.py",
    "scripts/pptx_shapes/xml_safety.py",
    "scripts/pptx_to_svg/emu_units.py",
    "scripts/pptx_to_svg/preset_authoring.py",
    "scripts/pptx_to_svg/preset_registry_to_svg.py",
    "scripts/pptx_to_svg/preset_svg_markup.py",
    "scripts/resource_paths.py",
    "scripts/semantic_table.py",
    "scripts/svg_to_pptx/drawingml/__init__.py",
    "scripts/svg_to_pptx/drawingml/context.py",
    "scripts/svg_to_pptx/drawingml/elements.py",
    "scripts/svg_to_pptx/drawingml/hyperlinks.py",
    "scripts/svg_to_pptx/drawingml/paths.py",
    "scripts/svg_to_pptx/drawingml/styles.py",
    "scripts/svg_to_pptx/drawingml/text_properties.py",
    "scripts/svg_to_pptx/drawingml/theme_colors.py",
    "scripts/svg_to_pptx/drawingml/theme_fonts.py",
    "scripts/svg_to_pptx/drawingml/utils.py",
    "scripts/svg_to_pptx/native_objects/__init__.py",
    "scripts/svg_to_pptx/native_objects/chart_data.py",
    "scripts/svg_to_pptx/native_objects/chart_style.py",
    "scripts/svg_to_pptx/native_objects/chart_xml.py",
    "scripts/svg_to_pptx/native_objects/chartex.py",
    "scripts/svg_to_pptx/native_objects/fallback_hash.py",
    "scripts/svg_to_pptx/native_objects/formula.py",
    "scripts/svg_to_pptx/native_objects/formula_ast.py",
    "scripts/svg_to_pptx/native_objects/formula_compiler.py",
    "scripts/svg_to_pptx/native_objects/formula_omml.py",
    "scripts/svg_to_pptx/native_objects/formula_parser.py",
    "scripts/svg_to_pptx/native_objects/formula_profile.py",
    "scripts/svg_to_pptx/native_objects/formula_run_properties.py",
    "scripts/svg_to_pptx/native_objects/inline_formula.py",
    "scripts/svg_to_pptx/native_objects/marker_attributes.py",
    "scripts/svg_to_pptx/native_objects/marker_common.py",
    "scripts/svg_to_pptx/native_objects/marker_status.py",
    "scripts/svg_to_pptx/native_objects/table.py",
    "scripts/svg_to_pptx/native_objects/workbook.py",
)

RESOURCE_SOURCE_PATHS = (
    "LICENSE",
    "SPONSORS.md",
    "SPONSORS_CN.md",
    "references/native-formula.md",
    "references/native-hyperlinks.md",
    "scripts/pptx_shapes/data/LICENSE-APACHE-2.0.txt",
    "scripts/pptx_shapes/data/LICENSE-OPEN-XML-SDK-MIT.txt",
    "scripts/pptx_shapes/data/NOTICE.md",
    "scripts/pptx_shapes/data/presetShapeDefinitions.xml",
    "scripts/pptx_shapes/data/presetShapeSemantics.json",
    "scripts/pptx_shapes/data/shape_type_values.txt",
    "templates/design_spec_reference.md",
    "templates/scaffolds/design_spec.md",
    "templates/scaffolds/spec_lock.md",
    "templates/schemas/design_spec.schema.json",
    "templates/schemas/spec_lock.schema.json",
    "templates/spec_lock_reference.md",
)

SELECTED_SOURCE_PATHS = tuple(sorted((*PYTHON_SOURCE_PATHS, *RESOURCE_SOURCE_PATHS)))
LICENSE_PATHS = (
    "LICENSE",
    "scripts/pptx_shapes/data/LICENSE-APACHE-2.0.txt",
    "scripts/pptx_shapes/data/LICENSE-OPEN-XML-SDK-MIT.txt",
    "scripts/pptx_shapes/data/NOTICE.md",
)
ALLOWED_EXTERNAL_IMPORTS = frozenset(
    {"openpyxl", "pathops", "pptx", "uharfbuzz", "xlsxwriter", "yaml"}
)
DANGEROUS_IMPORT_ROOTS = frozenset(
    {"aiohttp", "flask", "httpx", "requests", "socket", "subprocess", "webbrowser"}
)
DANGEROUS_IMPORT_MODULES = frozenset({"http.client", "urllib.request"})
DANGEROUS_CALLS = frozenset(
    {"os.getenv", "os.path.expanduser", "Path.home", "urllib.request.urlopen"}
)
BANNED_PATH_PATTERNS = (
    re.compile(r"(^|/)\.env(?:\.|$)", re.IGNORECASE),
    re.compile(r"(^|/)config\.py$", re.IGNORECASE),
    re.compile(r"(^|/)(?:update_repo|update_spec)\.py$", re.IGNORECASE),
    re.compile(r"(^|/)(?:image_backends|image_sources|tts_backends|confirm_ui|svg_editor|source_to_md)(/|$)", re.IGNORECASE),
    re.compile(r"(^|/)(?:image_gen|image_search|notes_to_audio|powerpoint_video|narration_sync|server_common)\.py$", re.IGNORECASE),
    re.compile(r"(^|/)templates/(?:brands|decks|icons|sounds)(/|$)", re.IGNORECASE),
    re.compile(r"(^|/)references/ai-image-comparison(/|$)", re.IGNORECASE),
    re.compile(r"(^|/)(?:pptx_animations|animation_config)\.py$", re.IGNORECASE),
)


class VendorValidationError(ValueError):
    """Raised when the static vendor package violates its admission contract."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_blob_oid(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - Git identity


def _manifest_digest(entries: list[dict]) -> str:
    payload = "".join(
        f"{item['path']}\t{item['size']}\t{item['sha256']}\t{item['gitBlobOid']}\n"
        for item in entries
    ).encode("utf-8")
    return _sha256(payload)


def _git_metadata(git_root: Path) -> tuple[dict[str, dict], dict[str, str]]:
    def run(*arguments: str) -> str:
        completed = subprocess.run(
            ["git", "-c", "core.quotePath=false", "-C", str(git_root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return completed.stdout.strip()

    metadata = {
        "origin": run("remote", "get-url", "origin"),
        "commit": run("rev-parse", "HEAD"),
        "tree": run("rev-parse", "HEAD^{tree}"),
        "tagCommit": run("rev-parse", f"refs/tags/{TAG}"),
    }
    tree_entries: dict[str, dict] = {}
    for line in run("ls-tree", "-r", "-l", "--full-tree", "HEAD").splitlines():
        match = re.fullmatch(
            r"(\d{6})\s+(\w+)\s+([0-9a-f]{40})\s+(\d+|-)\t(.+)", line
        )
        if match is None:
            raise VendorValidationError(f"cannot parse upstream tree entry: {line!r}")
        mode, kind, oid, size, path = match.groups()
        tree_entries[path] = {
            "mode": mode,
            "type": kind,
            "oid": oid,
            "size": None if size == "-" else int(size),
        }
    return tree_entries, metadata


def prepare_vendor_package(source_root: Path, git_root: Path, skill_dir: Path) -> dict:
    """Copy the allow-listed exact blobs and create the immutable manifest."""
    source_root = source_root.resolve()
    git_root = git_root.resolve()
    skill_dir = skill_dir.resolve()
    vendor_root = skill_dir / "vendor"
    manifest_path = skill_dir / "vendor-manifest.json"
    if vendor_root.exists() or manifest_path.exists():
        raise VendorValidationError("vendor output already exists")
    if source_root.name != "ppt-master" or source_root.parent.name != "skills":
        raise VendorValidationError("source root is not the fixed PPT Master skill root")

    tree_entries, metadata = _git_metadata(git_root)
    expected_metadata = {
        "origin": ORIGIN,
        "commit": COMMIT,
        "tree": TREE,
        "tagCommit": COMMIT,
    }
    if metadata != expected_metadata:
        raise VendorValidationError(f"upstream provenance mismatch: {metadata}")

    entries = []
    for relative in SELECTED_SOURCE_PATHS:
        source_path = source_root / Path(relative)
        full_source_path = f"skills/ppt-master/{relative}"
        tree_entry = tree_entries.get(full_source_path)
        if tree_entry is None or tree_entry["type"] != "blob":
            raise VendorValidationError(f"source is not a tracked blob: {relative}")
        if tree_entry["mode"] != "100644":
            raise VendorValidationError(f"unexpected source mode for {relative}")
        data = source_path.read_bytes()
        if len(data) != tree_entry["size"] or _git_blob_oid(data) != tree_entry["oid"]:
            raise VendorValidationError(f"source bytes do not match Git: {relative}")
        target = vendor_root / Path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        entries.append(
            {
                "path": relative,
                "sourcePath": full_source_path,
                "mode": tree_entry["mode"],
                "size": len(data),
                "sha256": _sha256(data),
                "gitBlobOid": tree_entry["oid"],
                "category": "python" if relative.endswith(".py") else "resource",
            }
        )

    entries.sort(key=lambda item: item["path"])
    manifest = {
        "schema": SCHEMA,
        "source": {
            "repository": ORIGIN,
            "tag": TAG,
            "commit": COMMIT,
            "tree": TREE,
        },
        "upstreamInventory": {
            "files": UPSTREAM_FILE_COUNT,
            "bytes": UPSTREAM_BYTES,
            "manifestSha256": UPSTREAM_MANIFEST_SHA256,
        },
        "selection": {
            "kind": "static-offline-core",
            "pythonSeeds": list(PYTHON_SEEDS),
            "closure": "top-level AST imports plus explicitly selected lazy native-object modules",
            "executableEntrypoints": [],
            "allowedExternalImports": sorted(ALLOWED_EXTERNAL_IMPORTS),
            "excludedCapabilities": [
                "automatic-update",
                "credentials-and-dotenv",
                "direct-network-and-providers",
                "web-and-image-download",
                "tts-audio-narration-video-animation",
                "confirm-ui-and-svg-editor-services",
                "image-to-pptx",
                "brands-icons-sounds-decks-and-ai-comparison-assets",
            ],
        },
        "licenseClosure": list(LICENSE_PATHS),
        "limits": {"maxFiles": MAX_VENDOR_FILES, "maxBytes": MAX_VENDOR_BYTES},
        "fileCount": len(entries),
        "totalBytes": sum(item["size"] for item in entries),
        "manifestDigest": _manifest_digest(entries),
        "files": entries,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _safe_relative_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise VendorValidationError(f"symlink is forbidden: {path}")
        if path.is_file():
            resolved = path.resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError as exc:
                raise VendorValidationError(f"path escaped vendor root: {path}") from exc
            files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def _dotted_name(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _dangerous_python_uses(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    findings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in DANGEROUS_IMPORT_ROOTS:
                    findings.add(f"import:{alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if (
                node.module in DANGEROUS_IMPORT_MODULES
                or node.module.split(".", 1)[0] in DANGEROUS_IMPORT_ROOTS
            ):
                findings.add(f"import:{node.module}")
        elif isinstance(node, ast.Call):
            name = _dotted_name(node.func)
            if (
                name in DANGEROUS_CALLS
                or name.endswith(".expanduser")
                or name.endswith(".startfile")
                or name.startswith(
                    ("httpx.", "requests.", "socket.", "subprocess.", "webbrowser.")
                )
            ):
                findings.add(f"call:{name}")
        elif isinstance(node, ast.Attribute) and _dotted_name(node) == "os.environ":
            findings.add("access:os.environ")
    return sorted(findings)


def _module_map(scripts_root: Path) -> dict[str, Path]:
    modules = {}
    for path in scripts_root.rglob("*.py"):
        parts = list(path.relative_to(scripts_root).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        modules[".".join(parts)] = path
    return modules


def _top_level_imports(tree: ast.Module) -> list[ast.AST]:
    imports = []
    queue = list(tree.body)
    while queue:
        node = queue.pop(0)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(node)
        elif isinstance(node, (ast.If, ast.Try, ast.With)):
            queue[0:0] = list(getattr(node, "body", ()))
            queue[0:0] = list(getattr(node, "orelse", ()))
            queue[0:0] = list(getattr(node, "finalbody", ()))
            for handler in getattr(node, "handlers", ()):
                queue[0:0] = list(handler.body)
    return imports


def _validate_import_closure(scripts_root: Path) -> None:
    modules = _module_map(scripts_root)
    local_roots = {name.split(".", 1)[0] for name in modules}
    unresolved = []
    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        package = module.split(".") if path.name == "__init__.py" else module.split(".")[:-1]
        for node in _top_level_imports(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                if node.level:
                    base = package[: max(0, len(package) - node.level + 1)]
                    if node.module:
                        base += node.module.split(".")
                    resolved = ".".join(base)
                    if resolved and resolved not in modules:
                        unresolved.append(f"{module}: missing relative module {resolved}")
                    continue
                names = [node.module] if node.module else []
            for imported in names:
                root = imported.split(".", 1)[0]
                if root in local_roots:
                    if not any(
                        imported == candidate or imported.startswith(candidate + ".")
                        for candidate in modules
                    ):
                        unresolved.append(f"{module}: missing local module {imported}")
                elif root not in sys.stdlib_module_names and root not in ALLOWED_EXTERNAL_IMPORTS:
                    unresolved.append(f"{module}: undeclared external import {imported}")
    if unresolved:
        raise VendorValidationError("; ".join(sorted(set(unresolved))))


def validate_vendor_package(skill_dir: Path) -> dict:
    """Validate provenance, inventory, safety, licensing, and static closure."""
    skill_dir = skill_dir.resolve()
    vendor_root = skill_dir / "vendor"
    manifest_path = skill_dir / "vendor-manifest.json"
    if not vendor_root.is_dir() or not manifest_path.is_file():
        raise VendorValidationError("PPT Master static vendor package is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise VendorValidationError("unsupported vendor manifest schema")
    if manifest.get("source") != {
        "repository": ORIGIN,
        "tag": TAG,
        "commit": COMMIT,
        "tree": TREE,
    }:
        raise VendorValidationError("vendor provenance is not the approved fixed source")
    if manifest.get("upstreamInventory") != {
        "files": UPSTREAM_FILE_COUNT,
        "bytes": UPSTREAM_BYTES,
        "manifestSha256": UPSTREAM_MANIFEST_SHA256,
    }:
        raise VendorValidationError("upstream inventory evidence changed")

    selection = manifest.get("selection") or {}
    if selection.get("kind") != "static-offline-core":
        raise VendorValidationError("vendor selection is not static-offline-core")
    if selection.get("pythonSeeds") != list(PYTHON_SEEDS):
        raise VendorValidationError("Python closure seeds changed")
    if selection.get("executableEntrypoints") != []:
        raise VendorValidationError("static package must not expose an entrypoint")
    if set(selection.get("allowedExternalImports") or []) != ALLOWED_EXTERNAL_IMPORTS:
        raise VendorValidationError("external import allow-list changed")

    entries = manifest.get("files")
    if not isinstance(entries, list) or entries != sorted(entries, key=lambda item: item["path"]):
        raise VendorValidationError("vendor manifest files must be a sorted array")
    if [item.get("path") for item in entries] != list(SELECTED_SOURCE_PATHS):
        raise VendorValidationError("vendor selection differs from the approved closure")
    actual_paths = [path.relative_to(vendor_root).as_posix() for path in _safe_relative_files(vendor_root)]
    if actual_paths != list(SELECTED_SOURCE_PATHS):
        raise VendorValidationError("vendor directory has missing or extra files")

    total_bytes = 0
    for item in entries:
        relative = item["path"]
        for pattern in BANNED_PATH_PATTERNS:
            if pattern.search(relative):
                raise VendorValidationError(f"forbidden capability path included: {relative}")
        if item.get("sourcePath") != f"skills/ppt-master/{relative}":
            raise VendorValidationError(f"invalid source path for {relative}")
        if item.get("mode") != "100644":
            raise VendorValidationError(f"non-regular source mode for {relative}")
        path = vendor_root / Path(relative)
        data = path.read_bytes()
        if item.get("size") != len(data):
            raise VendorValidationError(f"size mismatch: {relative}")
        if item.get("sha256") != _sha256(data):
            raise VendorValidationError(f"SHA-256 mismatch: {relative}")
        if item.get("gitBlobOid") != _git_blob_oid(data):
            raise VendorValidationError(f"Git blob mismatch: {relative}")
        if relative.endswith(".py"):
            findings = _dangerous_python_uses(path)
            if findings:
                raise VendorValidationError(f"dangerous Python use in {relative}: {findings}")
        total_bytes += len(data)

    if len(entries) > MAX_VENDOR_FILES or total_bytes > MAX_VENDOR_BYTES:
        raise VendorValidationError("vendor package exceeds the approved size budget")
    if manifest.get("fileCount") != len(entries) or manifest.get("totalBytes") != total_bytes:
        raise VendorValidationError("vendor manifest totals are incorrect")
    if manifest.get("manifestDigest") != _manifest_digest(entries):
        raise VendorValidationError("vendor manifest digest mismatch")
    if tuple(manifest.get("licenseClosure") or ()) != LICENSE_PATHS:
        raise VendorValidationError("license closure changed")
    for relative in LICENSE_PATHS:
        if not (vendor_root / relative).is_file():
            raise VendorValidationError(f"license closure is missing {relative}")

    _validate_import_closure(vendor_root / "scripts")
    return {
        "ok": True,
        "schema": SCHEMA,
        "commit": COMMIT,
        "tree": TREE,
        "fileCount": len(entries),
        "totalBytes": total_bytes,
        "manifestDigest": manifest["manifestDigest"],
        "executableEntrypoints": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skill-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "skills" / "ppt-master",
    )
    parser.add_argument("--prepare-source-root", type=Path)
    parser.add_argument("--git-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.prepare_source_root is not None:
            if args.git_root is None:
                raise VendorValidationError("--git-root is required with preparation mode")
            prepare_vendor_package(args.prepare_source_root, args.git_root, args.skill_dir)
        result = validate_vendor_package(args.skill_dir)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        payload = {"ok": False, "error": str(exc)}
        print(json.dumps(payload, ensure_ascii=False) if args.json else f"ERROR {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False) if args.json else f"OK {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
