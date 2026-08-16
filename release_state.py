"""Sealed local credentials for the two-stage Code release workflow."""

from __future__ import annotations

import copy
import hashlib
import json
import locale
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Iterable


SCHEMA = "code-release-prepared/v1"
SEAL_FIELD = "credentialSha256"


class CredentialError(ValueError):
    """Raised when a prepared-release credential is missing or invalid."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def seal_credential(payload: dict[str, Any]) -> dict[str, Any]:
    sealed = copy.deepcopy(payload)
    sealed.pop(SEAL_FIELD, None)
    sealed[SEAL_FIELD] = sha256_bytes(canonical_json(sealed))
    return sealed


def validate_credential(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise CredentialError("凭证根节点必须是对象")
    if payload.get("schema") != SCHEMA:
        raise CredentialError("凭证 schema 不受支持")
    expected = payload.get(SEAL_FIELD)
    if not isinstance(expected, str) or len(expected) != 64:
        raise CredentialError("凭证缺少有效摘要")
    unsigned = copy.deepcopy(payload)
    unsigned.pop(SEAL_FIELD, None)
    actual = sha256_bytes(canonical_json(unsigned))
    if actual != expected:
        raise CredentialError("凭证摘要不匹配，文件可能损坏或被篡改")
    required = (
        "version",
        "tag",
        "state",
        "baseline",
        "releaseFiles",
        "verification",
        "artifact",
        "environment",
        "publication",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        raise CredentialError(f"凭证缺少字段: {', '.join(missing)}")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(payload.get("version", ""))):
        raise CredentialError("凭证版本号格式无效")
    if payload.get("tag") != f"v{payload['version']}":
        raise CredentialError("凭证 tag 与版本号不匹配")
    if payload.get("state") not in {"prepared", "publishing", "published"}:
        raise CredentialError("凭证状态无效")
    if not isinstance(payload.get("releaseFiles"), list):
        raise CredentialError("凭证 releaseFiles 必须是数组")
    return copy.deepcopy(payload)


def resolve_credential_path(root: Path, version: str) -> Path:
    root = Path(root)
    dot_git = root / ".git"
    relative = Path("code-release") / f"v{version}.json"
    if dot_git.is_dir():
        return dot_git / relative
    if dot_git.is_file():
        raw = dot_git.read_bytes()
        decoded = None
        for encoding in ("utf-8-sig", locale.getpreferredencoding(False), "mbcs"):
            try:
                decoded = raw.decode(encoding)
                break
            except (LookupError, UnicodeDecodeError):
                continue
        if decoded and decoded.strip().lower().startswith("gitdir:"):
            git_dir = Path(decoded.split(":", 1)[1].strip())
            if not git_dir.is_absolute():
                git_dir = root / git_dir
            return git_dir / relative

    result = subprocess.run(
        ["git", "rev-parse", "--git-path", f"code-release/v{version}.json"],
        cwd=str(root),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise CredentialError("无法解析 Git 内部凭证路径")
    decoded = None
    for encoding in ("utf-8", locale.getpreferredencoding(False), "mbcs"):
        try:
            decoded = result.stdout.decode(encoding).strip()
            break
        except (LookupError, UnicodeDecodeError):
            continue
    if not decoded:
        raise CredentialError("Git 内部凭证路径编码无法识别")
    path = Path(decoded)
    return path if path.is_absolute() else Path(root) / path


def load_credential(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CredentialError("找不到 prepared 凭证，请先运行 prepare") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CredentialError(f"无法读取 prepared 凭证: {exc}") from exc
    return validate_credential(payload)


def save_credential(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    sealed = seal_credential(payload)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=destination.name + ".",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as stream:
            temp_name = Path(stream.name)
            stream.write(canonical_json(sealed) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, destination)
    finally:
        if temp_name is not None and temp_name.exists():
            temp_name.unlink()
    return sealed


def invalidate_credential(path: Path) -> None:
    Path(path).unlink(missing_ok=True)


def record_files(root: Path, relative_paths: Iterable[str]) -> list[dict[str, Any]]:
    records = []
    for relative in relative_paths:
        path = Path(root) / relative
        if not path.is_file():
            raise CredentialError(f"发布白名单文件不存在: {relative}")
        records.append(
            {
                "path": relative.replace("\\", "/"),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def validate_recorded_files(root: Path, records: Iterable[dict[str, Any]]) -> list[str]:
    errors = []
    for record in records:
        relative = str(record.get("path", ""))
        if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            errors.append(f"凭证包含不安全路径: {relative or '<empty>'}")
            continue
        path = Path(root) / relative
        if not path.is_file():
            errors.append(f"发布文件缺失: {relative}")
            continue
        if path.stat().st_size != record.get("size"):
            errors.append(f"发布文件大小变化: {relative}")
            continue
        if sha256_file(path) != record.get("sha256"):
            errors.append(f"发布文件哈希变化: {relative}")
    return errors
