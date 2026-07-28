"""Independent source-mode entry point for developing Code with Code.

The packaged release keeps using port 3010 and ``%USERPROFILE%\\.code``.
This entry point uses port 3011 and the repository ``data`` directory by
default, and deliberately imports ``server`` instead of executing
``server.py`` so the release instance is never selected by source startup
cleanup.
"""

import importlib
import os
from http.server import ThreadingHTTPServer
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DEV_PORT = 3011


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


def run_dev_server(server_module=None, server_factory=ThreadingHTTPServer):
    """Run the source instance without invoking ``server.py`` cleanup."""
    port, data_dir = configure_dev_environment()
    data_dir.mkdir(parents=True, exist_ok=True)

    if server_module is None:
        server_module = importlib.import_module("server")

    server_factory.daemon_threads = True
    server_module._migrate_sessions_to_hierarchy()
    server_module._migrate_codex_project_sessions_support()
    server_module._migrate_project_root_paths()

    httpd = server_factory(("127.0.0.1", port), server_module.CodeHandler)
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
