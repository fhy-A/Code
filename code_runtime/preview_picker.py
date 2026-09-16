"""Bounded directory metadata for the page-local preview file picker."""
import json
import os
from pathlib import Path, PureWindowsPath
import stat
import time

from .preview_identity import PreviewConflict, digest, path_identity

MAX_RESULTS = 200
MAX_ENTRIES = 2000
MAX_DIRECTORIES = 100
MAX_DEPTH = 8
MAX_SECONDS = 0.35
MAX_BYTES = 240 * 1024


def list_entries(root, relative_path="", query="", *, skip_names=(), clock=time.monotonic):
    """Never read content, follow links, use a home fallback, or create paths."""
    raw = str(relative_path or "").replace("\\", "/")
    query = str(query or "").strip()
    if (len(raw) > 4096 or "\0" in raw or PureWindowsPath(raw).drive
            or raw.startswith("/") or any(part in {".", ".."} for part in raw.split("/"))):
        raise PreviewConflict("preview_picker_path_unavailable")
    if len(query) > 128 or "\0" in query:
        raise ValueError("preview_picker_query_invalid")
    try:
        root = Path(root).resolve(strict=True)
        target = (root / raw).resolve(strict=True)
        if (len(str(root)) > 4096 or not target.is_dir()
                or (target != root and root not in target.parents)):
            raise PreviewConflict("preview_picker_path_unavailable")
        # Reject every linked component, including Windows directory junctions.
        for part in [root / Path(*Path(raw).parts[:i]) for i in range(1, len(Path(raw).parts) + 1)]:
            metadata = part.lstat()
            if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
                raise PreviewConflict("preview_picker_path_unavailable")
    except (OSError, RuntimeError) as exc:
        raise PreviewConflict("preview_picker_path_unavailable") from exc
    started = clock()
    queue = [(target, 0)]
    items, reasons = [], set()
    scanned = directories = used_bytes = 0
    needle = query.casefold()
    stop = False
    while queue and not stop:
        if directories >= MAX_DIRECTORIES:
            reasons.add("directories"); break
        if clock() - started >= MAX_SECONDS:
            reasons.add("time"); break
        folder, depth = queue.pop(0)
        # Revalidate the path before each bounded scan and again before emitting.
        if folder.resolve() != folder or (folder != root and root not in folder.parents):
            raise PreviewConflict("preview_picker_path_unavailable")
        directories += 1
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if clock() - started >= MAX_SECONDS:
                        reasons.add("time"); stop = True; break
                    if scanned >= MAX_ENTRIES:
                        reasons.add("entries"); stop = True; break
                    scanned += 1
                    if entry.name in skip_names:
                        continue
                    try:
                        metadata = entry.stat(follow_symlinks=False)
                        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
                            reasons.add("links"); continue
                        directory = stat.S_ISDIR(metadata.st_mode)
                        if not directory and not stat.S_ISREG(metadata.st_mode):
                            continue
                        candidate = Path(entry.path)
                        if candidate.resolve() != candidate or root not in candidate.parents:
                            raise PreviewConflict("preview_picker_path_unavailable")
                        if needle and directory:
                            if depth >= MAX_DEPTH:
                                reasons.add("depth")
                            elif len(queue) + directories >= MAX_DIRECTORIES:
                                reasons.add("directories")
                            else:
                                queue.append((candidate, depth + 1))
                        if needle and (directory or needle not in entry.name.casefold()):
                            continue
                        item = {"name": entry.name, "path": candidate.relative_to(root).as_posix(),
                                "absolutePath": str(candidate), "type": "dir" if directory else "file"}
                        if not directory:
                            item["fileKey"] = digest(path_identity(candidate))
                        size = len(json.dumps(item, ensure_ascii=True).encode("utf-8"))
                        if used_bytes + size > MAX_BYTES:
                            reasons.add("bytes"); stop = True; break
                        if len(items) >= MAX_RESULTS:
                            reasons.add("results"); stop = True; break
                        used_bytes += size
                        items.append(item)
                    except OSError:
                        reasons.add("unreadable")
        except OSError as exc:
            if folder == target:
                raise PreviewConflict("preview_picker_unavailable") from exc
            reasons.add("unreadable")
    if root.resolve() != root or target.resolve() != target:
        raise PreviewConflict("preview_picker_path_unavailable")
    items.sort(key=lambda item: (item["type"] != "dir", item["name"].casefold(), item["path"]))
    return {"root": str(root), "path": raw, "query": query, "items": items,
            "limited": bool(reasons), "reasons": sorted(reasons),
            "scannedEntries": scanned, "scannedDirectories": directories}
