"""Owned synthetic model choices, real HTTP/AgentRun/Skill loading and UI."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import shutil
from pathlib import Path
import sys
import threading


ROOT = Path(sys.argv[1]).resolve()
DATA, APP, PROJECT = ROOT / "profile", ROOT / "app", ROOT / "project"
os.environ.update(CODE_DATA_DIR=str(DATA), CODE_PORT="0", CODE_INSTANCE_MODE="release",
                  CODE_ROUTING_V2="0", CODE_SKILL_ACTIVATION_V1="0",
                  CODE_SKILL_IMMUTABLE_ADMISSION_V1="1", CODE_SKILL_MODEL_LOADING_V1="1",
                  CODE_SKILL_COMPLETION_ENFORCEMENT_V1="0", NO_PROXY="127.0.0.1,localhost,::1")
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import server
from code_runtime import data_dir_owner, skill_revisions

MODEL = "h4-simulated-skill-choice"
gate, waiting = threading.Event(), threading.Event()
stopping = threading.Event()


def prepare():
    repo = Path(__file__).resolve().parents[3]
    APP.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "app.js", "styles.css", "code-icon.ico", "VERSION"):
        shutil.copy2(repo / name, APP / name)
    for name in ("src", "dist/frontend"):
        shutil.copytree(repo / name, APP / name, dirs_exist_ok=True)
    PROJECT.mkdir(parents=True, exist_ok=True)
    (PROJECT / "input.txt").write_text("synthetic ordinary result", encoding="utf-8")
    bundled = APP / "data" / "skills"
    for name, description in (("ledger", "Analyze ledger data with fixed packaged rules"),
                              ("refine", "Improve the wording of a completed report")):
        for parent in (bundled, DATA / "skills"):
            package = parent / name
            package.mkdir(parents=True, exist_ok=True)
            (package / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: {description}\nallowed-tools: use_skill read_file write_file check_skill_dependencies read_skill_resource\n---\n\nH4_PINNED_BODY_{name}\n",
                encoding="utf-8")
    catalog = skill_revisions.build_bundled_catalog(bundled, {name: f"code.bundle/{name}" for name in ("ledger", "refine")})
    (bundled / skill_revisions.CATALOG_FILENAME).write_text(skill_revisions.render_bundled_catalog(catalog), encoding="utf-8")


class Upstream(BaseHTTPRequestHandler):
    def log_message(self, *_args): pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        with (ROOT / "simulated-model-requests.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
        messages = payload.get("messages", [])
        text = " ".join(str(item.get("content", "")) for item in messages if item.get("role") == "user")
        completed = {item.get("tool_call_id") for item in messages if item.get("role") == "tool"}
        steps = []
        if "H4_MID" in text:
            steps = [("before", "read_file", {"path": "input.txt"}),
                     ("owner", "use_skill", {"name": "ledger", "role": "owner"}),
                     ("modifier", "use_skill", {"name": "refine", "role": "modifier"})]
        elif "H4_FAILURE" in text:
            steps = [("unavailable", "use_skill", {"name": "missing", "role": "owner"})]
        step = next((item for item in steps if item[0] not in completed), None)
        if step:
            call_id, name, args = step
            delta = {"tool_calls": [{"index": 0, "id": call_id, "type": "function",
                                      "function": {"name": name, "arguments": json.dumps(args)}}]}
        else:
            delta = {"content": "H4_SIMULATED_CHOICE_FINAL"}
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.end_headers()
        self.wfile.write(("data: " + json.dumps({"choices": [{"delta": delta, "finish_reason": "tool_calls" if step else "stop"}]}) + "\n\ndata: [DONE]\n\n").encode())
        self.wfile.flush()


def main():
    prepare()
    owner = data_dir_owner.acquire_data_dir_owner(DATA)
    server.APP_DIR = APP
    server._ensure_runtime_data_directories()
    server.write_json(server.CONFIG_PATH, {"projectRoot": str(PROJECT)})
    server.PROJECTS_MIGRATION_FLAG.write_text("isolated", encoding="utf-8")
    server.PROJECT_ROOTS_MIGRATION_FLAG.write_text("isolated", encoding="utf-8")
    server._initialize_immutable_skill_runtime(owner, legacy_sync_result={"ok": True})
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    upstream.daemon_threads = True
    fake_url = f"http://127.0.0.1:{upstream.server_port}"
    server.default_project_root = lambda: str(PROJECT)
    original_config = server.load_config
    server.load_config = lambda: {**original_config(), "projectRoot": str(PROJECT), "userHome": str(PROJECT), "newApiBaseUrl": fake_url}
    server.CODEX_SESSIONS_DIR = ROOT / "isolated-home" / ".codex" / "sessions"
    server.CLAUDE_PROJECTS_DIR = ROOT / "isolated-home" / ".claude" / "projects"
    original_load = server._execute_agent_skill_load

    def controlled_load(run, args, call_id, **kwargs):
        if Path(run["cwd"]).resolve() != PROJECT:
            raise RuntimeError("H4 workspace escaped synthetic project")
        if args.get("name") == "ledger" and not gate.is_set():
            waiting.set()
            if not gate.wait(30):
                raise RuntimeError("synthetic load observation gate timed out")
        return original_load(run, args, call_id, **kwargs)

    server._execute_agent_skill_load = controlled_load

    class Handler(server.CodeHandler):
        def log_message(self, *_args): pass

        def send_json(self, *args, **kwargs):
            try:
                return super().send_json(*args, **kwargs)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError) as exc:
                with (ROOT / "http-response-aborts.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"method": self.command, "path": self.path,
                                             "error": type(exc).__name__}) + "\n")
                raise

        def do_GET(self):
            route = self.path.split("?", 1)[0]
            if route == "/__h4/state":
                self.send_json({"waiting": waiting.is_set(), "released": gate.is_set()})
            elif route == "/proxy/models":
                self.send_json({"data": [{"id": MODEL, "object": "model", "owned_by": "synthetic"}]})
            elif route.startswith("/api/") and not route.startswith((
                    "/api/sessions", "/api/agent/", "/api/runtime/", "/api/skills", "/api/skill-management/")) and route not in {
                    "/api/config", "/api/browser-heartbeat", "/api/projects", "/api/check-path", "/api/model-routes"}:
                self.send_json({"ok": True, "data": [], "files": [], "entries": [], "found": False})
            else:
                super().do_GET()

        def do_POST(self):
            route = self.path.split("?", 1)[0]
            if route.startswith("/__h4/"):
                self.consume_request_body(max_bytes=65536)
                if route == "/__h4/release": gate.set()
                if route == "/__h4/off": server._SKILL_MODEL_LOADING_ENABLED = False
                if route == "/__h4/on": server._SKILL_MODEL_LOADING_ENABLED = True
                self.send_json({"ok": True})
            elif route.startswith(("/api/agent/", "/api/sessions")) or route == "/api/config":
                super().do_POST()
            else:
                self.consume_request_body(max_bytes=1024 * 1024)
                self.send_json({"ok": True, "valid": route == "/api/code/auth/validate", "tokens": [], "keys": {},
                                "version": 1, "catalogRevision": 0, "routes": [], "changed": False, "routingV2": False,
                                "account": {"id": 7, "username": "h4-simulated"}})

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    threads = [threading.Thread(target=item.serve_forever, daemon=True) for item in (httpd, upstream)]
    for thread in threads: thread.start()
    print(json.dumps({"type": "ready", "codeUrl": f"http://127.0.0.1:{httpd.server_port}", "fakeUrl": fake_url,
                      "root": str(ROOT), "model": MODEL, "simulatedChoices": True}), flush=True)
    try:
        for line in sys.stdin:
            if json.loads(line).get("command") == "shutdown": break
    finally:
        gate.set()
        for run in list(server._agent_runs.values()): run["cancel_event"].set()
        for run in list(server._agent_runs.values()):
            worker = run.get("worker")
            if worker is not None: worker.join(timeout=5)
        for listener in (httpd, upstream):
            listener.shutdown()
            listener.server_close()
        for thread in threads: thread.join(timeout=5)
        alive = [run["id"] for run in server._agent_runs.values() if run.get("worker") and run["worker"].is_alive()]
        print(json.dumps({"type": "stopped", "workersStopped": not alive, "listenersStopped": all(not item.is_alive() for item in threads)}), flush=True)
        if alive: return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
