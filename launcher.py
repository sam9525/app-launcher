"""Find-or-launch-then-position core. Single public entry point: launch_all()."""

import ctypes
import os
import shlex
import subprocess
import sys
import threading
import time
from ctypes import wintypes

import pythoncom
import pywintypes
import win32api
import win32com.client
import win32con
import win32gui
import win32process
from win32com.shell import shell

import config
import monitors

POLL_INTERVAL = 0.3
POLL_TIMEOUT = 15.0
FOREGROUND_RETRIES = 8  # 8 * 0.25 s ~= 2 s of foreground confirmation attempts
FOREGROUND_RETRY_DELAY = 0.25
TERMINAL_PROCESS = "windowsterminal.exe"
EXPLORER_PROCESS = "explorer.exe"
MAX_EXPLORER_FOLDERS = 6  # first tab + 5 more; caps focus-steal time
# Predefined delays between the tab keystrokes. The one that matters most is
# TAB_OPEN: a freshly Ctrl+T'd tab lands on "Home" and isn't ready for address-
# bar input for a moment — too short and the tab stays blank. Tune upward if
# folders still land on Home (slower machine / heavier Explorer).
EXPLORER_WINDOW_READY_DELAY = 1.0  # window open -> input-ready before 1st Ctrl+T
EXPLORER_TAB_OPEN_DELAY = 1.0  # after Ctrl+T: let the new tab become input-ready
EXPLORER_FOCUS_DELAY = 0.4  # after Ctrl+L: let the address bar take focus
EXPLORER_NAV_DELAY = 0.6  # after Enter: let the folder load before the next tab
DWMWA_EXTENDED_FRAME_BOUNDS = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000  # works on elevated processes too
TOKEN_QUERY = 0x0008
TOKEN_ELEVATION_CLASS = 20  # TOKEN_INFORMATION_CLASS.TokenElevation
_MAX_PATH_CHARS = 32768
ERROR_ELEVATION_REQUIRED = 740
ERROR_CANCELLED = 1223  # user declined the UAC prompt
SEE_MASK_NOASYNC = 0x00000100  # absent from pywin32 shellcon

# Private DLL handles: argtypes (64-bit HANDLEs) must not leak into ctypes.windll.
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
_advapi32.OpenProcessToken.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.HANDLE),
]
_advapi32.OpenProcessToken.restype = wintypes.BOOL
_advapi32.GetTokenInformation.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    wintypes.LPVOID,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
_advapi32.GetTokenInformation.restype = wintypes.BOOL

# ponytail: global lock; fine for a single user mashing one hotkey
_run_lock = threading.Lock()

# Terminals are launched once per app run, then left alone. Keyed by
# (name, workdir); cleared only by restarting the launcher.
# ponytail: in-memory set, no persistence — a fresh run reopens terminals
_launched_terminals: set = set()

# Explorer groups launched once per run, keyed (name, tuple(folders)).
# ponytail: in-memory set, no persistence — a fresh run reopens windows
_launched_explorers: set = set()

# Admin apps launched once per run, keyed (name, path). Their windows are never
# positioned (the launcher can't move an elevated window), so a second press
# must not raise another UAC prompt.
# ponytail: in-memory set, no persistence — a fresh run asks for approval again
_launched_admin: set = set()


def _terminal_key(entry: dict) -> tuple:
    return (entry.get("name"), entry.get("workdir"))


def parse_folder_lines(text: str) -> list[str]:
    """One folder path per line; blanks and surrounding whitespace dropped."""
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def launch_all() -> str:
    if not _run_lock.acquire(blocking=False):
        return "Already running"
    try:
        entries = [
            e for e in config.load().get("entries", []) if e.get("enabled", True)
        ]
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
    monitor = entry.get("monitor", 1)
    zone = entry.get("zone", "maximized")

    if entry.get("kind") == "terminal":
        # Launch once per run; a marked terminal is skipped entirely (no
        # respawn, no reposition) so repeat presses don't pile up windows or
        # hijack another project's terminal. Never _find_window here — all
        # terminals share one process, so a "find" always hits the wrong one.
        key = _terminal_key(entry)
        if key in _launched_terminals:
            return None
        before = set(_windows_for(TERMINAL_PROCESS, pid_names))
        _spawn(entry)
        hwnd = _poll_new_window(TERMINAL_PROCESS, before, pid_names)
        if hwnd is None:
            return "unpositioned (no window within 15 s)"
        _position(hwnd, monitor, zone)
        _launched_terminals.add(key)  # mark only after it actually opened
        command = entry.get("startup_command", "")
        if command and not _send_startup_command(hwnd, command):
            return "opened, command not sent"
        return None

    if entry.get("kind") == "explorer":
        # One shared process like terminals: open once per run, then leave
        # alone. Never _find_window — all Explorer windows share one process.
        folders = entry.get("folders", [])
        if not folders:
            return "no folders configured"
        capped = folders[:MAX_EXPLORER_FOLDERS]
        key = (entry.get("name"), tuple(capped))
        if key in _launched_explorers:
            return None
        before = set(_windows_for(EXPLORER_PROCESS, pid_names))
        _spawn(entry)
        # ponytail: if explorer.exe reuses an existing window instead of
        # spawning one, poll finds nothing new — tabs are not added
        hwnd = _poll_new_window(EXPLORER_PROCESS, before, pid_names)
        if hwnd is None:
            return "unpositioned (no window within 15 s)"
        _position(hwnd, monitor, zone)
        sent = _send_explorer_tabs(hwnd, capped[1:])
        _launched_explorers.add(key)  # mark only after it actually opened
        notes = []
        if len(folders) > MAX_EXPLORER_FOLDERS:
            notes.append(f"capped to {MAX_EXPLORER_FOLDERS} folders")
        if sent < len(capped) - 1:
            notes.append(f"{len(capped) - 1 - sent} tab(s) not sent")
        return "; ".join(notes) or None

    # Regular apps: find-or-launch by process basename, reposition every press.
    proc_name = entry["match_process"]
    hwnd = _find_window(proc_name, pid_names)
    if hwnd:
        if not _window_is_elevated(hwnd):
            _position(hwnd, monitor, zone)
        return None
    admin_key = (entry.get("name"), entry.get("path"))
    if admin_key in _launched_admin:
        return None
    before = set(_windows_for(proc_name, pid_names))
    try:
        elevated = _spawn(entry)
    except pywintypes.error as exc:
        if exc.winerror == ERROR_CANCELLED:
            return "admin approval declined"
        raise
    if elevated:
        _launched_admin.add(admin_key)
        return None
    hwnd = _poll_new_window(proc_name, before, pid_names)
    if hwnd is None:
        return "unpositioned (no window within 15 s)"
    if not _window_is_elevated(hwnd):
        _position(hwnd, monitor, zone)
    return None


def _child_env() -> dict[str, str]:
    """os.environ minus the Tcl/Tk paths PyInstaller points into its _MEI folder,
    which is deleted on exit and breaks Tk in anything launched from here."""
    env = dict(os.environ)
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        for name in ("TCL_LIBRARY", "TK_LIBRARY"):
            if env.get(name, "").lower().startswith(bundle.lower()):
                del env[name]
    return env


def _spawn(entry: dict) -> bool:
    """Starts the entry. True only if it had to be launched elevated via UAC."""
    env = _child_env()
    if entry.get("kind") == "terminal":
        subprocess.Popen(["wt.exe", "-d", entry["workdir"]], env=env)
    elif entry.get("kind") == "explorer":
        subprocess.Popen(["explorer.exe", entry["folders"][0]], env=env)
    else:
        try:
            subprocess.Popen(
                [entry["path"]] + shlex.split(entry.get("args", "")), env=env
            )
        except OSError as exc:
            if exc.winerror != ERROR_ELEVATION_REQUIRED:
                raise
            pythoncom.CoInitialize()  # launch_all runs on worker threads
            try:
                shell.ShellExecuteEx(
                    fMask=SEE_MASK_NOASYNC,
                    lpVerb="runas",
                    lpFile=entry["path"],
                    lpParameters=subprocess.list2cmdline(
                        shlex.split(entry.get("args", ""))
                    ),
                    nShow=win32con.SW_SHOWNORMAL,
                )
            finally:
                pythoncom.CoUninitialize()
            return True
    return False


def _process_basename(pid: int, pid_names: dict) -> str | None:
    if pid not in pid_names:
        pid_names[pid] = None  # stays None if the process can't be queried
        handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            try:
                buf = ctypes.create_unicode_buffer(_MAX_PATH_CHARS)
                size = wintypes.DWORD(len(buf))
                if _kernel32.QueryFullProcessImageNameW(
                    handle, 0, buf, ctypes.byref(size)
                ):
                    pid_names[pid] = os.path.basename(buf.value).lower()
            finally:
                _kernel32.CloseHandle(handle)
    return pid_names[pid]


def _is_elevated(pid: int) -> bool:
    """True if the process runs elevated. Fails safe: any error counts as elevated."""
    process = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        return True
    try:
        token = wintypes.HANDLE()
        if not _advapi32.OpenProcessToken(process, TOKEN_QUERY, ctypes.byref(token)):
            return True
        try:
            elevation = wintypes.DWORD()
            returned = wintypes.DWORD()
            if not _advapi32.GetTokenInformation(
                token,
                TOKEN_ELEVATION_CLASS,
                ctypes.byref(elevation),
                ctypes.sizeof(elevation),
                ctypes.byref(returned),
            ):
                return True
            return bool(elevation.value)
        finally:
            _kernel32.CloseHandle(token)
    finally:
        _kernel32.CloseHandle(process)


def _window_is_elevated(hwnd: int) -> bool:
    """True if the window's process is elevated; errors count as elevated."""
    try:
        _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
        return _is_elevated(pid)
    except Exception:
        return True


def _windows_for(process_name: str, pid_names: dict) -> list[int]:
    target = process_name.lower()
    found: list[int] = []

    def callback(hwnd, _):
        try:
            if (
                win32gui.IsWindowVisible(hwnd)
                and win32gui.GetWindowTextLength(hwnd) > 0
            ):
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


def _frame_margins(hwnd: int) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) thickness of the invisible DWM border, so a
    zone rect can be inflated to make the *visible* window edges land flush.
    Returns (0, 0, 0, 0) if DWM can't be queried — positioning then behaves as
    it did before (bounding box aligned, slight visible gap)."""
    try:
        outer = win32gui.GetWindowRect(hwnd)  # (left, top, right, bottom)
        rect = wintypes.RECT()
        hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )
        if hr != 0:
            return (0, 0, 0, 0)
        return (
            rect.left - outer[0],
            rect.top - outer[1],
            outer[2] - rect.right,
            outer[3] - rect.bottom,
        )
    except Exception:
        return (0, 0, 0, 0)


def _position(hwnd: int, monitor_index: int, zone: str) -> None:
    if zone == "open-only":
        return  # find/launch only — leave the window where it opened
    mons = monitors.get_monitors()
    # clamp out-of-range monitor index to primary rather than fail
    mon = mons[monitor_index - 1] if 1 <= monitor_index <= len(mons) else mons[0]
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    x, y, w, h = monitors.zone_rect(mon, zone)
    if zone == "maximized":
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] == win32con.SW_SHOWMAXIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        # move onto the target monitor first: a window maximizes onto whichever
        # monitor it is on
        win32gui.SetWindowPos(
            hwnd, 0, x, y, w, h, win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
        )
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    else:
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] == win32con.SW_SHOWMAXIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        ox, oy, ow, oh = monitors.inflate_for_border((x, y, w, h), _frame_margins(hwnd))
        win32gui.SetWindowPos(
            hwnd, 0, ox, oy, ow, oh, win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
        )


def _sendkeys_escape(text: str) -> str:
    return "".join(f"{{{c}}}" if c in "+^%~(){}[]" else c for c in text)


def _confirm_foreground(hwnd: int) -> bool:
    """Try to raise hwnd to the foreground; True once it actually is."""
    for _ in range(FOREGROUND_RETRIES):
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass  # Windows foreground-lock can refuse; retry
        if win32gui.GetForegroundWindow() == hwnd:
            return True
        time.sleep(FOREGROUND_RETRY_DELAY)
    return False


def _send_startup_command(hwnd: int, command: str) -> bool:
    """Type command into the terminal ONLY if it is confirmed foreground."""
    if not _confirm_foreground(hwnd):
        return False  # never type into the wrong window
    pythoncom.CoInitialize()  # launch_all runs on worker threads
    try:
        wsh = win32com.client.Dispatch("WScript.Shell")
        wsh.SendKeys(_sendkeys_escape(command) + "{ENTER}")
        return True
    finally:
        pythoncom.CoUninitialize()


def _send_explorer_tabs(hwnd: int, folders: list) -> int:
    """Open each folder as a new tab via keystrokes, ONLY while hwnd stays
    confirmed foreground. Returns the number of tabs sent; stops at the first
    folder where foreground can't be confirmed (never blind-type).
    # ponytail: focus-stealing SendKeys is the only tab mechanism Windows offers
    """
    sent = 0
    pythoncom.CoInitialize()
    try:
        keys = win32com.client.Dispatch("WScript.Shell")
        # the window just opened via explorer.exe — let it settle before the
        # first Ctrl+T, or that tab races the window's own initial load
        time.sleep(EXPLORER_WINDOW_READY_DELAY)
        for path in folders:
            if not _confirm_foreground(hwnd):
                break
            keys.SendKeys("^t")  # new tab (lands on Home)
            time.sleep(EXPLORER_TAB_OPEN_DELAY)
            keys.SendKeys("^l")  # focus the address bar
            time.sleep(EXPLORER_FOCUS_DELAY)
            keys.SendKeys(_sendkeys_escape(path) + "{ENTER}")
            time.sleep(EXPLORER_NAV_DELAY)
            sent += 1
    finally:
        pythoncom.CoUninitialize()
    return sent
