"""Find-or-launch-then-position core. Single public entry point: launch_all()."""
import os
import shlex
import subprocess
import threading
import time

import pythoncom
import win32api
import win32com.client
import win32con
import win32gui
import win32process

import config
import monitors

POLL_INTERVAL = 0.3
POLL_TIMEOUT = 15.0
FOREGROUND_RETRIES = 8          # 8 * 0.25 s ~= 2 s of foreground confirmation attempts
FOREGROUND_RETRY_DELAY = 0.25
TERMINAL_PROCESS = "windowsterminal.exe"

# ponytail: global lock; fine for a single user mashing one hotkey
_run_lock = threading.Lock()


def launch_all() -> str:
    if not _run_lock.acquire(blocking=False):
        return "Already running"
    try:
        entries = [e for e in config.load().get("entries", []) if e.get("enabled", True)]
        if not entries:
            return "No enabled entries — open Settings"
        pid_names: dict[int, str | None] = {}  # PID -> basename cache, per run
        problems = []
        for entry in entries:
            name = entry.get("name", "?")
            try:
                note = _handle_entry(entry, pid_names)
            except FileNotFoundError:
                note = "path not found"
            except Exception as exc:  # one bad entry never stops the loop
                note = f"failed ({exc})"
            if note:
                problems.append(f"{name}: {note}")
        ok = len(entries) - len(problems)
        summary = f"Launched {ok}/{len(entries)}"
        if problems:
            summary += " — " + "; ".join(problems)
        return summary
    finally:
        _run_lock.release()


def _handle_entry(entry: dict, pid_names: dict) -> str | None:
    """Returns None on full success, else a short problem note for the summary."""
    if entry.get("kind") == "terminal":
        proc_name = TERMINAL_PROCESS
    else:
        proc_name = entry["match_process"]
    monitor = entry.get("monitor", 1)
    zone = entry.get("zone", "maximized")

    hwnd = _find_window(proc_name, pid_names)
    if hwnd:
        _position(hwnd, monitor, zone)
        return None

    # Snapshot HWNDs before spawning; poll for a NEW one. Never poll by spawned
    # PID: wt.exe hands off to a WindowsTerminal.exe broker and exits, and apps
    # like Code.exe parent their window to a child process.
    before = set(_windows_for(proc_name, pid_names))
    _spawn(entry)
    hwnd = _poll_new_window(proc_name, before, pid_names)
    if hwnd is None:
        return "unpositioned (no window within 15 s)"
    _position(hwnd, monitor, zone)

    command = entry.get("startup_command", "")
    if entry.get("kind") == "terminal" and command:
        if not _send_startup_command(hwnd, command):
            return "opened, command not sent"
    return None


def _spawn(entry: dict) -> None:
    if entry.get("kind") == "terminal":
        subprocess.Popen(["wt.exe", "-d", entry["workdir"]])
    else:
        subprocess.Popen([entry["path"]] + shlex.split(entry.get("args", "")))


def _process_basename(pid: int, pid_names: dict) -> str | None:
    if pid not in pid_names:
        try:
            handle = win32api.OpenProcess(
                win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            try:
                path = win32process.GetModuleFileNameEx(handle, 0)
            finally:
                handle.close()
            pid_names[pid] = os.path.basename(path).lower()
        except Exception:  # elevated processes refuse OpenProcess — skip them
            pid_names[pid] = None
    return pid_names[pid]


def _windows_for(process_name: str, pid_names: dict) -> list[int]:
    target = process_name.lower()
    found: list[int] = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowTextLength(hwnd) > 0:
            try:
                _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
                if _process_basename(pid, pid_names) == target:
                    found.append(hwnd)
            except Exception:
                pass
        return True

    win32api.SetLastError(0)
    try:
        win32gui.EnumWindows(callback, None)
    except Exception:
        pass
    return found


def _find_window(process_name: str, pid_names: dict) -> int | None:
    windows = _windows_for(process_name, pid_names)
    return windows[0] if windows else None


def _poll_new_window(process_name: str, before: set, pid_names: dict) -> int | None:
    deadline = time.monotonic() + POLL_TIMEOUT
    while time.monotonic() < deadline:
        for hwnd in _windows_for(process_name, pid_names):
            if hwnd not in before:
                return hwnd
        time.sleep(POLL_INTERVAL)
    return None


def _position(hwnd: int, monitor_index: int, zone: str) -> None:
    mons = monitors.get_monitors()
    # clamp out-of-range monitor index to primary rather than fail
    mon = mons[monitor_index - 1] if 1 <= monitor_index <= len(mons) else mons[0]
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    x, y, w, h = monitors.zone_rect(mon, zone)
    if zone == "maximized":
        # move onto the target monitor first: a window maximizes onto whichever
        # monitor it is on
        win32gui.SetWindowPos(hwnd, 0, x, y, w, h,
                              win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    else:
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] == win32con.SW_SHOWMAXIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetWindowPos(hwnd, 0, x, y, w, h,
                              win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)


def _sendkeys_escape(text: str) -> str:
    return "".join(f"{{{c}}}" if c in "+^%~(){}[]" else c for c in text)


def _send_startup_command(hwnd: int, command: str) -> bool:
    """Type command into the terminal ONLY if it is confirmed foreground."""
    for _ in range(FOREGROUND_RETRIES):
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass  # Windows foreground-lock can refuse; retry
        if win32gui.GetForegroundWindow() == hwnd:
            pythoncom.CoInitialize()  # launch_all runs on worker threads
            shell = win32com.client.Dispatch("WScript.Shell")
            shell.SendKeys(_sendkeys_escape(command) + "{ENTER}")
            return True
        time.sleep(FOREGROUND_RETRY_DELAY)
    return False  # never type into the wrong window



