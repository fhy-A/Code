"""
Code launcher — entry point for PyInstaller bundle.
"""
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from bundled_skills import sync_missing_bundled_skills


def has_existing_browser(port=3010):
    """Check the old server before it is stopped so an existing tab can be reused."""
    import urllib.request as _request
    try:
        with _request.urlopen(f"http://127.0.0.1:{port}/api/has-browser", timeout=1.5) as response:
            return bool(json.loads(response.read()).get("hasBrowser"))
    except Exception:
        return False


def should_reuse_browser(port=3010, argv=None):
    """Reuse a connected page, including after the updater stopped the old server."""
    args = sys.argv if argv is None else argv
    return "--reuse-browser" in args or has_existing_browser(port)


def kill_existing():
    """Stop older packaged/dev instances while preserving this PyInstaller process pair."""
    protected_pids = {os.getpid(), os.getppid()}
    killed = 0
    try:
        script = r"""
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    ($_.Name -match '^Code(?:-v[0-9.]+)?[.]exe$') -or
    (($_.Name -match '^pythonw?(?:[0-9.]+)?[.]exe$') -and
     ($_.CommandLine -match '(?i)(^|[\\/\s])server[.]py([\s\"]|$)'))
} | ForEach-Object { $_.ProcessId }
""".strip()
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for line in result.stdout.splitlines():
            pid_str = line.strip()
            if not pid_str.isdigit():
                continue
            pid = int(pid_str)
            if pid in protected_pids:
                continue
            stopped = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if stopped.returncode == 0:
                killed += 1
    except Exception:
        pass
    return killed


def get_code_home():
    """Return the Code installation directory: %USERPROFILE%\\.code"""
    return Path.home() / ".code"


def create_desktop_shortcut(target_exe):
    """Create or update a desktop shortcut pointing to *target_exe*.

    Uses PowerShell + WScript.Shell to produce a proper .lnk file.
    Failures are non-fatal but logged to install.log.
    """
    if os.name != "nt":
        return False
    target_exe = Path(target_exe).resolve()
    target_dir = target_exe.parent
    ps_script = (
        "$desktop = [Environment]::GetFolderPath('Desktop');"
        "$lnk = Join-Path $desktop 'Code.lnk';"
        "$ws = New-Object -ComObject WScript.Shell;"
        "$s = $ws.CreateShortcut($lnk);"
        "$s.TargetPath = '{target}';"
        "$s.WorkingDirectory = '{workdir}';"
        "$s.IconLocation = '{icon}';"
        "$s.Description = 'Code - AI Coding Assistant';"
        "$s.Save();"
        "Write-Output 'ok'"
    ).format(
        target=str(target_exe).replace("'", "''"),
        workdir=str(target_dir).replace("'", "''"),
        icon=str(target_exe).replace("'", "''"),
    )
    log_dir = Path.home() / ".code"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "install.log"
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        ok = result.returncode == 0 and "ok" in result.stdout
        if not ok:
            _append_log(log_path,
                f"Shortcut creation failed: rc={result.returncode} "
                f"stdout={result.stdout.strip()!r} stderr={result.stderr.strip()!r}")
        return ok
    except Exception as exc:
        _append_log(log_path, f"Shortcut creation exception: {exc}")
        return False


def _append_log(log_path, message):
    """Append a timestamped line to the install log."""
    import datetime as _dt
    try:
        ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
    except Exception:
        pass


def ensure_installed():
    """Make sure the current executable lives under %USERPROFILE%\\.code.

    On first run from a downloaded location (Desktop, Downloads, etc.) the
    launcher copies itself to .code\\Code-v{version}.exe, creates a desktop
    shortcut, and relaunches from there.  In dev mode this is a no-op.

    On every startup from .code\\ the desktop shortcut is refreshed to point
    to the currently running versioned executable.
    """
    if not getattr(sys, 'frozen', False):
        return

    current = Path(sys.executable).resolve()
    target_dir = get_code_home()

    if current.parent != target_dir:
        # First run from a temporary location — copy ourselves into .code\
        target_dir.mkdir(parents=True, exist_ok=True)
        target_exe = target_dir / current.name  # preserve versioned name
        print(f"Installing Code to {target_exe} ...")
        try:
            shutil.copy2(current, target_exe)
            print("  Copied executable.")
        except OSError as exc:
            print(f"  Copy failed: {exc}")
            print("  Please move the file manually to: " + str(target_exe))
            return
        if not create_desktop_shortcut(target_exe):
            print("  Shortcut creation failed — see install.log for details.")
        subprocess.Popen(
            [str(target_exe), "--reuse-browser"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        )
        os._exit(0)

    # Running from .code\\ — always keep the desktop shortcut pointed at us
    # so it survives version bumps after an update.
    create_desktop_shortcut(current)


def get_base_dir():
    """Get the directory containing app files (handles PyInstaller bundle)."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def migrate_old_data_dir():
    """Migrate legacy ~/.agent-lite/ to ~/.code/ (brand rename)."""
    old_home = Path.home() / ".agent-lite"
    new_home = Path.home() / ".code"
    if not old_home.exists() or new_home.exists():
        return new_home
    try:
        shutil.copytree(str(old_home), str(new_home), dirs_exist_ok=True)
        shutil.rmtree(str(old_home), ignore_errors=True)
        print(f"Migrated data: {old_home} -> {new_home}")
    except Exception as e:
        print(f"Data migration failed (non-fatal): {e}")
    return new_home


def ensure_dirs():
    """Create required directories if they don't exist."""
    data_home = Path.home() / ".code"
    for sub in ["sessions", "memory", "skills", "attachments", "file-backups"]:
        (data_home / sub).mkdir(parents=True, exist_ok=True)
    return data_home


def sync_bundled_skills_at_startup(base, data_dir):
    """Fill missing bundled Skills without blocking startup on bad state/copies."""
    try:
        return sync_missing_bundled_skills(
            Path(base) / "data" / "skills",
            Path(data_dir) / "skills",
        )
    except Exception as exc:
        return {
            "ok": False,
            "status": "sync_failed",
            "copied": [],
            "existing": [],
            "tombstoned": [],
            "errors": [{"stage": "sync", "error": str(exc)}],
        }


def hide_console():
    """Hide the console window (--console build) so user only sees tray + browser."""
    if os.name != "nt":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


def main():
    hide_console()
    try:
        _main()
    except Exception as e:
        import traceback
        crash_log = Path.home() / ".code" / "crash.log"
        crash_log.parent.mkdir(parents=True, exist_ok=True)
        with open(crash_log, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        raise


def _main():
    port = 3010
    had_browser = should_reuse_browser(port)

    # Kill any existing Code processes before starting.
    killed = kill_existing()
    if killed:
        import time
        time.sleep(0.5)

    # On first run from a downloaded location, copy ourselves into
    # %USERPROFILE%\\.code\\Code.exe, create a desktop shortcut, and
    # relaunch from there.  In dev mode this is a no-op.
    ensure_installed()

    base = get_base_dir()
    migrate_old_data_dir()
    data_dir = ensure_dirs()

    # Copy tray icon to data dir so pystray can load it reliably (PyInstaller
    # extraction can corrupt binary files in the temp directory)
    _ico_src = base / "code-icon.ico"
    _ico_dst = data_dir / "code-icon.ico"
    if _ico_src.exists():
        shutil.copy2(_ico_src, _ico_dst)

    # Keep the legacy first-run-only memory copy. Bundled Skills use their own
    # per-directory, tombstone-aware upgrade synchronizer.
    bundled_data = base / "data"
    if bundled_data.exists():
        memory_src = bundled_data / "memory"
        memory_dst = data_dir / "memory"
        if memory_src.exists() and not any(memory_dst.iterdir()):
            for item in memory_src.iterdir():
                if item.is_file():
                    (memory_dst / item.name).write_text(
                        item.read_text(encoding="utf-8-sig"),
                        encoding="utf-8",
                    )
                elif item.is_dir():
                    shutil.copytree(item, memory_dst / item.name)
        sync_bundled_skills_at_startup(base, data_dir)

    # Set environment for server
    os.environ["CODE_PORT"] = "3010"
    os.environ["CODE_DATA_DIR"] = str(data_dir)

    # Import and start server
    os.chdir(str(base))
    import server
    import threading
    from http.server import ThreadingHTTPServer

    # Override DATA_DIR paths in server module
    server.DATA_DIR = data_dir
    server.SESSIONS_DIR = data_dir / "sessions"
    server.MEMORY_DIR = data_dir / "memory"
    server.SKILLS_DIR = data_dir / "skills"
    server.ATTACHMENTS_DIR = data_dir / "attachments"
    server.FILE_BACKUP_DIR = data_dir / "file-backups"
    server.CONFIG_PATH = data_dir / "config.json"
    for d in [server.DATA_DIR, server.SESSIONS_DIR, server.MEMORY_DIR,
              server.SKILLS_DIR, server.ATTACHMENTS_DIR, server.FILE_BACKUP_DIR]:
        d.mkdir(exist_ok=True)

    port = int(os.environ.get("CODE_PORT", "3010"))
    server_obj = ThreadingHTTPServer(("127.0.0.1", port), server.CodeHandler)

    # pystray's Windows backend requires its message loop on the main thread.
    # Keep the HTTP server in a worker so the packaged app gets a reliable tray.
    server_thread = threading.Thread(
        target=server_obj.serve_forever,
        daemon=False,
        name="code-http",
    )
    server_thread.start()
    print(f"Code running at http://127.0.0.1:{port}")
    # Existing pages detect the new server instance and refresh themselves.
    # Open a browser only when no page was connected before the restart.
    if not had_browser:
        webbrowser.open(f"http://127.0.0.1:{port}")

    try:
        tray_started = server.run_tray_main_thread(port, server_obj)
        if not tray_started:
            server_thread.join()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server_obj.shutdown()
        server_obj.server_close()
        server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
