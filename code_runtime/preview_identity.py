"""Small, server-owned preview identities; no imports with runtime side effects."""
import hashlib
import json
import os
from pathlib import Path
import re
import uuid


class PreviewConflict(ValueError):
    def __init__(self, code="preview_scope_changed"):
        super().__init__(code)
        self.code = code


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def path_identity(path):
    return os.path.normcase(str(Path(path).resolve()))


def new_identity():
    return {"version": 1, "id": uuid.uuid4().hex}


def identity_id(value):
    if (not isinstance(value, dict) or type(value.get("version")) is not int or value.get("version") != 1
            or not isinstance(value.get("id"), str)
            or not re.fullmatch(r"[a-f0-9]{32}", value["id"])):
        raise PreviewConflict("preview_identity_unavailable")
    return value["id"]


def source_identity(data_dir, write_json, *, initialize=False):
    """Caller serializes initialization. Preserve corrupt/unknown existing state."""
    path = Path(data_dir) / "preview-workspace" / "source.json"
    if path.is_symlink():
        raise PreviewConflict("preview_source_unavailable")
    binding = digest(path_identity(data_dir))
    if not path.exists():
        if not initialize:
            raise PreviewConflict("preview_source_unavailable")
        payload = {"schema": "code-preview-source/v1", "dataSourceId": uuid.uuid4().hex,
                   "rootBinding": binding}
        write_json(path, payload)
    try:
        if path.stat().st_size > 4096:
            raise ValueError("oversized identity")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (payload.get("schema") != "code-preview-source/v1"
                or payload.get("rootBinding") != binding
                or not re.fullmatch(r"[a-f0-9]{32}", payload.get("dataSourceId", ""))):
            raise ValueError("invalid identity")
        return payload["dataSourceId"]
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise PreviewConflict("preview_source_unavailable") from exc


def resolve_read_path(value, root, home):
    """Match legacy project resolution, without creating output directories."""
    root, home = Path(root).resolve(), Path(home).resolve()
    value = str(value or "").strip()
    candidate = Path(value).expanduser()
    target = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if target == root or root in target.parents:
        return root, target
    if target == home or home in target.parents:
        return home, target
    if value and not candidate.is_absolute():
        fallback = (home / value).resolve()
        if fallback.exists():
            return home, fallback
    return root, root / "output" / target.name if value else root / "output"
