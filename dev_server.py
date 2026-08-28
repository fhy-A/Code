"""Independent source-mode entry point for developing Code with Code.

The packaged release keeps using port 3010 and ``%USERPROFILE%\\.code``.
This entry point uses port 3011 and the repository ``data`` directory by
default, and deliberately imports ``server`` instead of executing
``server.py`` so the release instance is never selected by source startup
cleanup.
"""

import importlib
import os
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import parse


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DEV_PORT = 3011
FRONTEND_BUILD_SCRIPT = APP_DIR / "scripts" / "build-frontend.mjs"
_FRONTEND_BUILD_LOCK = threading.Lock()


def _frontend_command_output(result, limit=2000):
    output = "\n".join(
        part.strip()
        for part in (result.stdout or "", result.stderr or "")
        if part and part.strip()
    )
    return output[-limit:] if output else "No command output."


def _hidden_subprocess_kwargs():
    """Prevent short-lived frontend build consoles from flashing on Windows."""
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "startupinfo": startupinfo,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
    }


def _run_frontend_command(*arguments):
    command = ["node", str(FRONTEND_BUILD_SCRIPT), *arguments]
    try:
        return subprocess.run(
            command,
            cwd=APP_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
            **_hidden_subprocess_kwargs(),
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Node.js is required to build the Code development frontend."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Frontend build timed out after 60 seconds.") from exc


def ensure_frontend_build():
    """Verify the generated frontend and rebuild it when source inputs changed."""
    with _FRONTEND_BUILD_LOCK:
        freshness = _run_frontend_command("--check")
        if freshness.returncode == 0:
            return False

        build = _run_frontend_command()
        if build.returncode != 0:
            raise RuntimeError(
                "Frontend build failed:\n" + _frontend_command_output(build)
            )

        verified = _run_frontend_command("--check")
        if verified.returncode != 0:
            raise RuntimeError(
                "Frontend build verification failed:\n"
                + _frontend_command_output(verified)
            )
        return True


def create_dev_handler(base_handler, ensure_frontend=ensure_frontend_build):
    """Wrap the application handler with source-mode frontend freshness checks."""

    class DevelopmentCodeHandler(base_handler):
        def do_GET(self):
            route = parse.urlsplit(self.path).path
            if route in {"/", "/index.html"}:
                try:
                    rebuilt = ensure_frontend()
                except RuntimeError as exc:
                    print(f"Code Dev frontend unavailable: {exc}")
                    self.send_error(503, "Frontend build failed")
                    return
                if rebuilt:
                    print("Code Dev frontend rebuilt from current sources.")
            return super().do_GET()

    DevelopmentCodeHandler.__name__ = f"Development{base_handler.__name__}"
    return DevelopmentCodeHandler


def configure_dev_environment(environ=None):
    """Configure and return the isolated development port and data directory."""
    env = os.environ if environ is None else environ

    raw_port = str(env.get("CODE_DEV_PORT") or DEFAULT_DEV_PORT).strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError(f"Invalid CODE_DEV_PORT: {raw_port}") from exc
    if not 1024 <= port <= 65535:
        raise ValueError("CODE_DEV_PORT must be between 1024 and 65535")

    raw_data_dir = str(env.get("CODE_DEV_DATA_DIR") or "").strip()
    data_dir = (
        Path(raw_data_dir).expanduser().resolve()
        if raw_data_dir
        else (APP_DIR / "data").resolve()
    )

    env["CODE_PORT"] = str(port)
    env["CODE_DATA_DIR"] = str(data_dir)
    env["CODE_RESTART_ENTRY"] = str((APP_DIR / "dev_server.py").resolve())
    env["CODE_INSTANCE_MODE"] = "dev"
    return port, data_dir


def run_dev_server(
    server_module=None,
    server_factory=ThreadingHTTPServer,
    ensure_frontend=ensure_frontend_build,
):
    """Run the source instance without invoking ``server.py`` cleanup."""
    port, data_dir = configure_dev_environment()
    data_dir.mkdir(parents=True, exist_ok=True)

    rebuilt = ensure_frontend()
    if rebuilt:
        print("Code Dev frontend rebuilt from current sources.")

    if server_module is None:
        server_module = importlib.import_module("server")

    server_factory.daemon_threads = True
    server_module._migrate_sessions_to_hierarchy()
    server_module._migrate_codex_project_sessions_support()
    server_module._migrate_project_root_paths()
    server_module._start_agent_run_nonterminal_index_build()

    handler = create_dev_handler(server_module.CodeHandler, ensure_frontend)
    httpd = server_factory(("127.0.0.1", port), handler)
    httpd.socket.settimeout(2.0)
    server_module.start_tray(port, httpd)

    print(f"Code Dev is running: http://127.0.0.1:{port}")
    print(f"Development data: {data_dir}")
    print(f"Project root: {server_module.load_config()['projectRoot']}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Code Dev...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_dev_server()
