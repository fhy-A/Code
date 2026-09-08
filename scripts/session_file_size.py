"""Read Codex rollout metadata only; thresholds are team advice, not limits."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat


MIB = 1024 * 1024
TASK_ID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.I)
ADVICE = {
    "normal": "正常复用",
    "observe": "观察；阶段结束检查",
    "recommend_rotation": "建议阶段结束后轮换",
    "strongly_recommend_rotation": "强烈建议轮换后再承接新阶段",
    "unknown": "无法判断；不得按小文件处理",
}


def classify_size(size_bytes):
    if size_bytes < 100 * MIB:
        return "normal"
    if size_bytes < 300 * MIB:
        return "observe"
    if size_bytes < 500 * MIB:
        return "recommend_rotation"
    return "strongly_recommend_rotation"


def _linked(metadata):
    # Reject Windows junctions/reparse points as well as POSIX symlinks.
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def inspect_session(task_id, codex_home):
    """Enumerate names and stat metadata; never open a session file."""
    result = {
        "schema": "code-session-file-size/v1",
        "taskId": task_id,
        "status": "unknown",
        "level": "unknown",
        "reason": "invalid_task_id",
        "advice": ADVICE["unknown"],
        "path": None,
        "sizeBytes": None,
        "sizeMiB": None,
        "modifiedAt": None,
        "matchCount": 0,
        "measuredAt": datetime.now(timezone.utc).isoformat(),
    }
    if not TASK_ID.fullmatch(task_id):
        return result
    task_id = task_id.lower()
    result["taskId"] = task_id
    matches = []
    home = Path(codex_home).expanduser().absolute()
    try:
        home_stat = home.lstat()
        if _linked(home_stat) or not stat.S_ISDIR(home_stat.st_mode):
            result["reason"] = "unsafe_search_root"
            return result
        for root_name in ("sessions", "archived_sessions"):
            root = home / root_name
            try:
                root_stat = root.lstat()
            except FileNotFoundError:
                # Either store can legitimately be absent. No match still means unknown.
                continue
            if _linked(root_stat) or not stat.S_ISDIR(root_stat.st_mode):
                result["reason"] = "unsafe_search_root"
                return result
            pending = [root]
            while pending:
                directory = pending.pop()
                with os.scandir(directory) as entries:
                    for entry in entries:
                        metadata = entry.stat(follow_symlinks=False)
                        if _linked(metadata):
                            # An unsearched subtree could hide a duplicate; do not guess.
                            result["reason"] = "unsafe_search_entry"
                            return result
                        if stat.S_ISDIR(metadata.st_mode):
                            pending.append(Path(entry.path))
                        elif (
                            entry.name.lower().startswith("rollout-")
                            and entry.name.lower().endswith(f"-{task_id}.jsonl")
                        ):
                            if not stat.S_ISREG(metadata.st_mode):
                                result["reason"] = "not_regular_file"
                                return result
                            matches.append(Path(entry.path))
        result["matchCount"] = len(matches)
        if len(matches) != 1:
            result["reason"] = "not_found" if not matches else "multiple_matches"
            return result
        # Refresh the one candidate after enumeration. A disappearing file is unknown.
        metadata = matches[0].lstat()
        if _linked(metadata) or not stat.S_ISREG(metadata.st_mode):
            result["reason"] = "not_regular_file"
            return result
        modified = datetime.fromtimestamp(metadata.st_mtime, timezone.utc).isoformat()
    except (OSError, ValueError, OverflowError):
        result["reason"] = "metadata_unavailable"
        return result
    level = classify_size(metadata.st_size)
    result.update(
        status="ok",
        level=level,
        reason="measured",
        advice=ADVICE[level],
        path=str(matches[0]),
        sizeBytes=metadata.st_size,
        sizeMiB=round(metadata.st_size / MIB, 3),
        modifiedAt=modified,
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_id", help="exact task UUID (not a prefix or title)")
    parser.add_argument(
        "--codex-home", type=Path,
        default=Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex"),
        help="metadata search root; defaults to CODEX_HOME or ~/.codex",
    )
    parser.add_argument("--json", action="store_true", help="emit structured result")
    args = parser.parse_args(argv)
    result = inspect_session(args.task_id, args.codex_home)
    if args.json:
        # ASCII escaping also makes redirected output safe on Windows legacy encodings.
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    else:
        size = result["sizeBytes"]
        detail = f"{size} bytes ({result['sizeMiB']:.3f} MiB)" if size is not None else "unknown"
        print(
            f"{result['status']} level={result['level']} size={detail} "
            f"reason={result['reason']} advice={result['advice']}"
        )
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
