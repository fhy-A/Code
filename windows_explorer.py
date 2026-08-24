"""Windows Explorer selection and foreground activation without UI simulation."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import ntpath
import os
from pathlib import Path
import subprocess
import time


class ExplorerIntegrationError(RuntimeError):
    """A bounded Explorer integration failure safe to expose to the caller."""


def normalize_windows_path(value):
    """Return a case-insensitive identity for a filesystem path."""
    text = os.fspath(value or "").strip().replace("/", "\\")
    if text.startswith("\\\\?\\UNC\\"):
        text = "\\\\" + text[8:]
    elif text.startswith("\\\\?\\"):
        text = text[4:]
    normalized = ntpath.normpath(text)
    drive, tail = ntpath.splitdrive(normalized)
    if tail == "\\":
        return f"{drive.casefold()}\\"
    return normalized.rstrip("\\").casefold()


def _resolved_path(value):
    return Path(value).expanduser().resolve(strict=False)


def _path_is_within(target, root):
    target = _resolved_path(target)
    root = _resolved_path(root)
    return target == root or root in target.parents


def nearest_existing_directory(target, allowed_root):
    """Find the nearest existing directory without climbing above allowed_root."""
    target = _resolved_path(target)
    allowed_root = _resolved_path(allowed_root)
    if not _path_is_within(target, allowed_root):
        raise ExplorerIntegrationError("explorer target is outside the allowed root")
    candidate = target if target.exists() and target.is_dir() else target.parent
    while _path_is_within(candidate, allowed_root):
        if candidate.exists() and candidate.is_dir():
            return candidate
        if candidate == allowed_root or candidate.parent == candidate:
            break
        candidate = candidate.parent
    if allowed_root.exists() and allowed_root.is_dir():
        return allowed_root
    raise ExplorerIntegrationError("no existing Explorer directory is available")


def exact_explorer_window(windows, target_directory):
    """Return (hwnd, status) only when one exact filesystem path is represented."""
    target_key = normalize_windows_path(target_directory)
    matches = set()
    for item in windows or ():
        try:
            hwnd = int(item.get("hwnd") if isinstance(item, dict) else item.hwnd)
            path = item.get("path") if isinstance(item, dict) else item.path
        except (AttributeError, TypeError, ValueError):
            continue
        if hwnd > 0 and normalize_windows_path(path) == target_key:
            matches.add(hwnd)
    if len(matches) == 1:
        return next(iter(matches)), "unique"
    if len(matches) > 1:
        return None, "ambiguous"
    return None, "not_found"


def _powershell_utf8_json_script(body):
    """Wrap a PowerShell JSON producer with a code-page-independent UTF-8 sink."""
    return (r"""
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
""" + str(body).strip() + r"""
$bytes = $utf8.GetBytes([string]$json)
$stdout = [Console]::OpenStandardOutput()
$stdout.Write($bytes, 0, $bytes.Length)
$stdout.Flush()
""").strip()


class ShellWindowsProvider:
    """Enumerate Explorer windows through Shell.Application/IShellWindows."""

    _SCRIPT = _powershell_utf8_json_script(r"""
$items = @()
$shell = New-Object -ComObject Shell.Application
$windows = $shell.Windows()
for ($index = 0; $index -lt $windows.Count; $index++) {
  try {
    $window = $windows.Item($index)
    $hwnd = [Int64]$window.HWND
    $path = [string]$window.Document.Folder.Self.Path
    if ($hwnd -gt 0 -and $path) {
      $items += [PSCustomObject]@{ hwnd = $hwnd; path = $path }
    }
  } catch {}
}
$json = ConvertTo-Json -InputObject $items -Compress
""")

    def __init__(self, timeout=1.5, runner=None):
        self.timeout = float(timeout)
        self._runner = runner or subprocess.run

    def list_windows(self, timeout=None):
        effective_timeout = self.timeout
        if timeout is not None:
            effective_timeout = min(effective_timeout, max(0.05, float(timeout)))
        try:
            completed = self._runner(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", self._SCRIPT],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=effective_timeout,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            raise ExplorerIntegrationError("Explorer window enumeration failed") from exc
        if completed.returncode != 0:
            raise ExplorerIntegrationError("Explorer window enumeration failed")
        try:
            payload = json.loads(completed.stdout or "[]")
        except (TypeError, ValueError) as exc:
            raise ExplorerIntegrationError("Explorer window enumeration failed") from exc
        if not isinstance(payload, list):
            payload = [payload]
        return [
            {"hwnd": int(item["hwnd"]), "path": str(item["path"])}
            for item in payload
            if isinstance(item, dict) and item.get("hwnd") and item.get("path")
        ]


class CtypesShellApi:
    """Use Shell PIDLs for file selection and ShellExecute for directories."""

    def __init__(self):
        if os.name != "nt":
            raise ExplorerIntegrationError("Windows Explorer is unavailable")
        self.shell32 = ctypes.windll.shell32
        self.ole32 = ctypes.windll.ole32
        self.shell32.ILCreateFromPathW.argtypes = [wintypes.LPCWSTR]
        self.shell32.ILCreateFromPathW.restype = ctypes.c_void_p
        self.shell32.ILClone.argtypes = [ctypes.c_void_p]
        self.shell32.ILClone.restype = ctypes.c_void_p
        self.shell32.ILRemoveLastID.argtypes = [ctypes.c_void_p]
        self.shell32.ILRemoveLastID.restype = wintypes.BOOL
        self.shell32.ILFindLastID.argtypes = [ctypes.c_void_p]
        self.shell32.ILFindLastID.restype = ctypes.c_void_p
        self.shell32.SHOpenFolderAndSelectItems.argtypes = [
            ctypes.c_void_p,
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p),
            wintypes.DWORD,
        ]
        self.shell32.SHOpenFolderAndSelectItems.restype = ctypes.c_long
        self.shell32.ShellExecuteW.argtypes = [
            wintypes.HWND,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            ctypes.c_int,
        ]
        self.shell32.ShellExecuteW.restype = ctypes.c_void_p
        self.ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        self.ole32.CoTaskMemFree.restype = None
        self.ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        self.ole32.CoInitializeEx.restype = ctypes.c_long
        self.ole32.CoUninitialize.argtypes = []
        self.ole32.CoUninitialize.restype = None

    def _initialize_com(self):
        result = ctypes.c_long(self.ole32.CoInitializeEx(None, 2)).value
        if result in (0, 1):
            return True
        if result == -2147417850:  # RPC_E_CHANGED_MODE: COM already initialized differently.
            return False
        raise ExplorerIntegrationError("Explorer COM initialization failed")

    def select_file(self, path):
        should_uninitialize = self._initialize_com()
        full_pidl = None
        parent_pidl = None
        try:
            full_pidl = self.shell32.ILCreateFromPathW(str(path))
            if not full_pidl:
                raise ExplorerIntegrationError("Explorer could not resolve the file")
            parent_pidl = self.shell32.ILClone(full_pidl)
            child_pidl = self.shell32.ILFindLastID(full_pidl)
            if not parent_pidl or not child_pidl or not self.shell32.ILRemoveLastID(parent_pidl):
                raise ExplorerIntegrationError("Explorer could not resolve the file parent")
            children = (ctypes.c_void_p * 1)(child_pidl)
            result = self.shell32.SHOpenFolderAndSelectItems(parent_pidl, 1, children, 0)
            if ctypes.c_long(result).value < 0:
                raise ExplorerIntegrationError("Explorer could not select the file")
        finally:
            if parent_pidl:
                self.ole32.CoTaskMemFree(parent_pidl)
            if full_pidl:
                self.ole32.CoTaskMemFree(full_pidl)
            if should_uninitialize:
                self.ole32.CoUninitialize()

    def open_folder(self, path):
        result = self.shell32.ShellExecuteW(None, "open", str(path), None, None, 1)
        value = int(result or 0)
        if value <= 32:
            raise ExplorerIntegrationError("Explorer could not open the folder")


class CtypesWindowApi:
    SW_RESTORE = 9
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOACTIVATE = 0x0010

    def __init__(self):
        if os.name != "nt":
            raise ExplorerIntegrationError("Windows foreground APIs are unavailable")
        self.user32 = ctypes.windll.user32
        self.user32.IsIconic.argtypes = [wintypes.HWND]
        self.user32.IsIconic.restype = wintypes.BOOL
        self.user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.ShowWindow.restype = wintypes.BOOL
        self.user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.user32.SetForegroundWindow.restype = wintypes.BOOL
        self.user32.GetForegroundWindow.argtypes = []
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        self.user32.SetWindowPos.restype = wintypes.BOOL

    def is_iconic(self, hwnd):
        return bool(self.user32.IsIconic(wintypes.HWND(hwnd)))

    def restore(self, hwnd):
        self.user32.ShowWindow(wintypes.HWND(hwnd), self.SW_RESTORE)

    def set_foreground(self, hwnd):
        return bool(self.user32.SetForegroundWindow(wintypes.HWND(hwnd)))

    def get_foreground(self):
        return int(self.user32.GetForegroundWindow() or 0)

    def set_topmost(self, hwnd, enabled):
        insert_after = self.HWND_TOPMOST if enabled else self.HWND_NOTOPMOST
        ok = self.user32.SetWindowPos(
            wintypes.HWND(hwnd),
            wintypes.HWND(insert_after),
            0,
            0,
            0,
            0,
            self.SWP_NOMOVE | self.SWP_NOSIZE | self.SWP_NOACTIVATE,
        )
        if not ok:
            raise ExplorerIntegrationError("Explorer topmost state update failed")


def activate_exact_window(hwnd, window_api):
    """Restore and activate one already-verified HWND with a bounded pulse fallback."""
    restored = False
    try:
        restored = bool(window_api.is_iconic(hwnd))
        if restored:
            window_api.restore(hwnd)
        accepted = bool(window_api.set_foreground(hwnd))
        if accepted and int(window_api.get_foreground() or 0) == int(hwnd):
            return {"foreground": "foreground", "restored": restored, "topmostPulse": False}
    except Exception:
        pass

    pulse_error = None
    foreground = False
    try:
        window_api.set_topmost(hwnd, True)
        window_api.set_foreground(hwnd)
        foreground = int(window_api.get_foreground() or 0) == int(hwnd)
    except Exception:
        foreground = False
    finally:
        try:
            window_api.set_topmost(hwnd, False)
        except Exception as exc:
            pulse_error = exc
    if pulse_error is not None:
        raise ExplorerIntegrationError("Explorer topmost cleanup failed") from pulse_error
    return {
        "foreground": "topmost-pulse" if foreground else "not-confirmed",
        "restored": restored,
        "topmostPulse": True,
    }


class WindowsExplorerController:
    def __init__(self, *, shell_api=None, window_provider=None, window_api=None,
                 timeout=2.0, poll_interval=0.08, clock=None, sleeper=None):
        self.shell_api = shell_api or CtypesShellApi()
        self.window_provider = window_provider or ShellWindowsProvider()
        self.window_api = window_api or CtypesWindowApi()
        self.timeout = max(0.0, float(timeout))
        self.poll_interval = max(0.01, float(poll_interval))
        self.clock = clock or time.monotonic
        self.sleeper = sleeper or time.sleep

    def open(self, target, *, select_file, allowed_root):
        target = _resolved_path(target)
        allowed_root = _resolved_path(allowed_root)
        if not _path_is_within(target, allowed_root):
            raise ExplorerIntegrationError("explorer target is outside the allowed root")

        reasons = []
        selected = False
        if target.exists() and target.is_file() and select_file:
            target_directory = target.parent
            action = "select_file"
            try:
                self.shell_api.select_file(target)
                selected = True
            except Exception as exc:
                raise ExplorerIntegrationError("Explorer file selection failed") from exc
        elif target.exists() and target.is_dir():
            target_directory = target
            action = "open_folder"
            try:
                self.shell_api.open_folder(target_directory)
            except Exception as exc:
                raise ExplorerIntegrationError("Explorer folder open failed") from exc
        else:
            target_directory = nearest_existing_directory(target, allowed_root)
            action = "open_folder"
            reasons.append("target_missing" if not target.exists() else "target_not_selectable")
            try:
                self.shell_api.open_folder(target_directory)
            except Exception as exc:
                raise ExplorerIntegrationError("Explorer fallback folder open failed") from exc

        deadline = self.clock() + self.timeout
        match_status = "not_found"
        provider_failed = False
        attempts = 0
        while True:
            now = self.clock()
            if attempts and now >= deadline:
                break
            remaining = max(0.0, deadline - now)
            try:
                hwnd, match_status = exact_explorer_window(
                    self.window_provider.list_windows(timeout=remaining), target_directory,
                )
                provider_failed = False
            except Exception:
                hwnd = None
                match_status = "unavailable"
                provider_failed = True
            attempts += 1
            if hwnd is not None:
                activation = activate_exact_window(hwnd, self.window_api)
                if activation["foreground"] == "not-confirmed":
                    reasons.append("foreground_not_confirmed")
                return {
                    "ok": True,
                    "action": action,
                    "selected": selected,
                    "degraded": bool(reasons),
                    "degradedReasons": reasons,
                    **activation,
                }
            now = self.clock()
            if now >= deadline:
                break
            self.sleeper(min(self.poll_interval, max(0.0, deadline - now)))

        if provider_failed:
            reasons.append("window_enumeration_unavailable")
            foreground = "window-unavailable"
        elif match_status == "ambiguous":
            reasons.append("window_match_ambiguous")
            foreground = "ambiguous"
        else:
            reasons.append("window_not_found")
            foreground = "window-not-found"
        return {
            "ok": True,
            "action": action,
            "selected": selected,
            "degraded": True,
            "degradedReasons": reasons,
            "foreground": foreground,
            "restored": False,
            "topmostPulse": False,
        }


def open_path_in_explorer(target, *, select_file, allowed_root):
    if os.name != "nt":
        raise ExplorerIntegrationError("Windows Explorer is unavailable")
    return WindowsExplorerController().open(
        target, select_file=bool(select_file), allowed_root=allowed_root,
    )


__all__ = [
    "ExplorerIntegrationError", "ShellWindowsProvider", "WindowsExplorerController",
    "activate_exact_window", "exact_explorer_window", "nearest_existing_directory",
    "normalize_windows_path", "open_path_in_explorer",
]
