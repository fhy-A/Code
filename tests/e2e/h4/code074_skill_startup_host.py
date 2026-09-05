"""Isolated process host for CODE-074 immutable startup HTTP integration."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time


SKILL = "startup-alpha"
FINAL = "H4_IMMUTABLE_STARTUP_FINAL"


def _emit(value):
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")), flush=True)


def _paths(root):
    return root / "profile", root / "app", root / "project"


def _prepare(root, repo_root):
    sys.path.insert(0, str(repo_root))
    from code_runtime import skill_revisions

    data, app, project = _paths(root)
    bundled = app / "data" / "skills"
    installed = data / "skills"
    skill_text = (
        f"---\nname: {SKILL}\ndescription: immutable startup fixture\n"
        "allowed-tools: read_file, write_file\n---\n\nUse the fixed revision.\n"
    )
    for parent in (bundled, installed):
        target = parent / SKILL
        target.mkdir(parents=True, exist_ok=True)
        (target / "SKILL.md").write_text(
            skill_text, encoding="utf-8", newline="\n",
        )
    project.mkdir(parents=True, exist_ok=True)
    catalog = skill_revisions.build_bundled_catalog(
        bundled, {SKILL: f"code.bundle/{SKILL}"},
    )
    (bundled / skill_revisions.CATALOG_FILENAME).write_text(
        skill_revisions.render_bundled_catalog(catalog),
        encoding="utf-8", newline="\n",
    )
    _emit({"type": "prepared", "ok": True})


class _Upstream(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        payload = json.loads(self.rfile.read(length) or b"{}")
        messages = payload.get("messages") or []
        wants_hold = any(
            message.get("role") == "user"
            and "hold-v6" in str(message.get("content") or "")
            for message in messages
        )
        has_tool_result = any(message.get("role") == "tool" for message in messages)
        if wants_hold and not has_tool_result:
            frames = [{"choices": [{
                "delta": {"tool_calls": [{
                    "index": 0,
                    "id": "startup-write",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": json.dumps({
                            "path": "startup-result.txt", "content": "not written",
                        }, separators=(",", ":")),
                    },
                }]},
                "finish_reason": "tool_calls",
            }]}]
        else:
            frames = [{"choices": [{
                "delta": {"content": FINAL}, "finish_reason": "stop",
            }]}]
        frames.append({"choices": [], "usage": {
            "prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5,
        }})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.end_headers()
        for frame in frames:
            self.wfile.write(("data: " + json.dumps(frame) + "\n\n").encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def _store_snapshot(data):
    store = data / "skill-store-v1"
    digest = hashlib.sha256()
    for path in sorted(store.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(store).as_posix()
        digest.update(relative.encode("utf-8") + b"\0")
        if path.is_file():
            digest.update(path.read_bytes())
    registry = json.loads((store / "registry.json").read_text(encoding="utf-8"))
    return {
        "treeHash": digest.hexdigest(),
        "dataRootId": registry["dataRootId"],
        "generation": registry["generation"],
        "registryHash": registry["registryHash"],
        "receiptCount": len(registry["operationReceipts"]),
    }


def _serve(root, repo_root, enabled, sync_failed, delay_ready):
    data, app, _project = _paths(root)
    os.environ.update({
        "CODE_DATA_DIR": str(data),
        "CODE_PORT": "0",
        "CODE_INSTANCE_MODE": "release",
        "CODE_ROUTING_V2": "0",
        "CODE_SKILL_ACTIVATION_V1": "0",
        "CODE_SKILL_IMMUTABLE_ADMISSION_V1": "1" if enabled else "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "NO_PROXY": "127.0.0.1,localhost,::1",
    })
    sys.path.insert(0, str(repo_root))
    import server
    from code_runtime import data_dir_owner, skill_runtime_startup

    server.APP_DIR = app
    try:
        owner = data_dir_owner.acquire_data_dir_owner(data)
    except data_dir_owner.DataDirOwnerError as exc:
        _emit({"type": "owner-error", "code": exc.code, "listenerPublished": False})
        return 3
    # Match the real entry points: ownership is process-lifetime and is
    # released by data_dir_owner's atexit hook only after all writers stop.
    server._ensure_runtime_data_directories()
    try:
        startup = server._initialize_immutable_skill_runtime(
            owner,
            legacy_sync_result={"ok": not sync_failed},
        )
    except skill_runtime_startup.ImmutableSkillStartupError as exc:
        _emit({
            "type": "startup-error", "code": exc.code,
            "listenerPublished": False,
        })
        return 2

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    upstream.daemon_threads = True
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()

    class Handler(server.CodeHandler):
        def log_message(self, *_args):
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    _emit({
        "type": "listening",
        "codePort": httpd.server_address[1],
        "fakePort": upstream.server_address[1],
    })
    if delay_ready:
        time.sleep(5)
    store = None
    if startup["readerReady"]:
        store = _store_snapshot(data)
    _emit({
        "type": "ready",
        "codeUrl": f"http://127.0.0.1:{httpd.server_address[1]}",
        "fakeUrl": f"http://127.0.0.1:{upstream.server_address[1]}",
        "startup": startup,
        "store": store,
    })
    for line in sys.stdin:
        try:
            command = json.loads(line)
        except json.JSONDecodeError:
            continue
        if command.get("command") == "shutdown":
            break
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=3)
    upstream.shutdown()
    upstream.server_close()
    upstream_thread.join(timeout=3)
    _emit({
        "type": "stopped",
        "portsClosed": [not thread.is_alive(), not upstream_thread.is_alive()],
    })
    return 0


def main():
    if len(sys.argv) < 3:
        return 64
    root = Path(sys.argv[1]).resolve()
    repo_root = Path(__file__).resolve().parents[3]
    action = sys.argv[2]
    if action == "prepare":
        _prepare(root, repo_root)
        return 0
    if action != "serve" or len(sys.argv) < 4:
        return 64
    enabled = sys.argv[3] == "on"
    options = set(sys.argv[4:])
    return _serve(
        root, repo_root, enabled,
        "sync-failed" in options, "delay-ready" in options,
    )


if __name__ == "__main__":
    raise SystemExit(main())
