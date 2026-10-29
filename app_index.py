"""Resolve an app name to its executable path. Best-effort: the Windows
App Paths registry first, then Start Menu shortcuts; first match wins."""

import os
import winreg

import pythoncom
import win32com.client

_APP_PATHS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"


def _from_app_paths(target: str) -> str | None:
    """Match an App Paths subkey (e.g. 'chrome.exe') by name or stem."""
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            key = winreg.OpenKey(root, _APP_PATHS)
        except OSError:
            continue
        try:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                stem = os.path.splitext(sub)[0].lower()
                if target in (sub.lower(), stem):
                    try:
                        with winreg.OpenKey(key, sub) as sk:
                            path, _ = winreg.QueryValueEx(sk, "")  # default value
                    except OSError:
                        continue
                    if path:
                        path = os.path.expandvars(path.strip().strip('"'))
                        if os.path.exists(path):
                            return path
        finally:
            key.Close()
    return None


def _start_menu_dirs() -> list[str]:
    dirs = []
    for env in ("ProgramData", "APPDATA"):
        base = os.environ.get(env)
        if base:
            dirs.append(os.path.join(base, r"Microsoft\Windows\Start Menu\Programs"))
    return dirs


def _from_start_menu(target: str) -> str | None:
    """Find a .lnk whose filename stem equals target and return its exe."""
    # ponytail: CoInitialize without a matching uninit — the caller thread
    # (Tk UI or a one-shot resolve) is long-lived; balancing is only relevant
    # at process exit.
    pythoncom.CoInitialize()
    shell = win32com.client.Dispatch("WScript.Shell")
    for base in _start_menu_dirs():
        for dirpath, _subdirs, files in os.walk(base):
            for f in files:
                if not f.lower().endswith(".lnk"):
                    continue
                if os.path.splitext(f)[0].lower() != target:
                    continue
                try:
                    tgt = shell.CreateShortcut(os.path.join(dirpath, f)).TargetPath
                except Exception:
                    continue
                if tgt and tgt.lower().endswith(".exe") and os.path.exists(tgt):
                    return tgt
    return None


def resolve(name: str) -> str | None:
    target = (name or "").strip().lower()
    if not target:
        return None
    return _from_app_paths(target) or _from_start_menu(target)
