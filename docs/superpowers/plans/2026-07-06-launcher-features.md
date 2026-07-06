# Four Launcher Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix gapped window tiling, add an "open-only" zone, add find-app-by-name when adding entries, and add a Windows-following dark mode with manual override.

**Architecture:** Four independent changes. The positioning fix inflates zone rects by the invisible DWM border so visible edges land flush. "Open-only" is a sentinel zone that skips positioning. Find-by-name resolves an app name to an exe via the App Paths registry and Start Menu shortcuts. Dark mode centralizes color literals into a palette and rebuilds the Settings window body on theme change.

**Tech Stack:** Python 3, `pywin32`, `ctypes` (DWM), `winreg`, `win32com` (shortcut resolution), Tkinter/ttk, `pytest` (tests also run standalone via `__main__`).

## Global Constraints

- Windows-only; assumes `pywin32`, `wt.exe`, and `%APPDATA%` present.
- Flat module layout, one responsibility per file. No package nesting.
- All coordinates are physical pixels (DPI awareness set in `main.py`).
- Window matching is by process basename, case-insensitive.
- Tests import top-level modules via `sys.path.insert(0, <repo root>)` and use `mock.patch` for Win32 calls; every test file ends with an `assert`-based `__main__` block.
- `config.load()` / `config.save()` are the only cross-thread contact point; do not add new shared mutable state.
- Run all tests with: `python -m pytest tests/` (from `D:\data\Program\app-launcher`).
- GitNexus: run `mcp__gitnexus__impact` on any function before editing it; run `mcp__gitnexus__detect_changes` before each commit. Re-index with `npx gitnexus analyze` if a tool reports the index stale.

---

### Task 1: `inflate_for_border` — border-aware rect math

**Files:**
- Modify: `monitors.py` (append new function after `zone_rect`)
- Test: `tests/test_zones.py` (add test + `__main__` line)

**Interfaces:**
- Produces: `monitors.inflate_for_border(rect: tuple[int,int,int,int], margins: tuple[int,int,int,int]) -> tuple[int,int,int,int]`. `rect` is `(x, y, w, h)` (desired *visible* rect); `margins` is `(left, top, right, bottom)` invisible-border thickness. Returns the outer rect `(x-left, y-top, w+left+right, h+top+bottom)` to pass to `SetWindowPos`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_zones.py` (after `test_halves_tile_exactly`):

```python
def test_inflate_for_border():
    # Zero margins is a no-op.
    assert inflate_for_border((0, 0, 1280, 1440), (0, 0, 0, 0)) == (0, 0, 1280, 1440)
    # 7px shadow on left/right/bottom, 0 on top (typical DWM border).
    assert inflate_for_border((0, 0, 1280, 1440), (7, 0, 7, 7)) == (-7, 0, 1294, 1447)
    # Offset (virtual-desktop) rect inflates the same way.
    assert inflate_for_border((2560, -120, 960, 1200), (7, 0, 7, 7)) == (2553, -120, 974, 1207)
```

Update the import at the top of the file:

```python
from monitors import zone_rect, inflate_for_border
```

And add to the `__main__` block:

```python
    test_inflate_for_border()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_zones.py::test_inflate_for_border -v`
Expected: FAIL with `ImportError: cannot import name 'inflate_for_border'`.

- [ ] **Step 3: Write minimal implementation**

Append to `monitors.py`:

```python
def inflate_for_border(rect, margins):
    """Expand a visible-target rect outward by the invisible-border margins so
    the window's outer bounds land where SetWindowPos needs them for the
    *visible* edges to match rect. margins is (left, top, right, bottom)."""
    x, y, w, h = rect
    left, top, right, bottom = margins
    return (x - left, y - top, w + left + right, h + top + bottom)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_zones.py -v`
Expected: PASS (all zone tests including the new one).

- [ ] **Step 5: Commit**

```bash
git add monitors.py tests/test_zones.py
git commit -m "feat: add inflate_for_border for flush window tiling"
```

---

### Task 2: `_frame_margins` + flush positioning

**Files:**
- Modify: `launcher.py` (add imports + `_frame_margins`, edit `_position` non-maximized branch)
- Test: `tests/test_config.py` (add test + `__main__` line)

**Interfaces:**
- Consumes: `monitors.inflate_for_border` (Task 1).
- Produces: `launcher._frame_margins(hwnd: int) -> tuple[int,int,int,int]` returning `(left, top, right, bottom)` DWM border thickness, `(0,0,0,0)` on any failure.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py` (after `test_position_maximized_restore`):

```python
def test_position_half_inflates_for_border():
    hwnd = 12345
    with mock.patch("monitors.get_monitors", return_value=[(0, 0, 1920, 1080)]), \
         mock.patch("monitors.zone_rect", return_value=(0, 0, 960, 1080)), \
         mock.patch("launcher._frame_margins", return_value=(7, 0, 7, 7)), \
         mock.patch("win32gui.IsIconic", return_value=False), \
         mock.patch("win32gui.GetWindowPlacement",
                    return_value=(0, win32con.SW_SHOWNORMAL, (0, 0), (0, 0), (0, 0, 100, 100))), \
         mock.patch("win32gui.ShowWindow"), \
         mock.patch("win32gui.SetWindowPos") as mock_set_pos:
        import launcher
        launcher._position(hwnd, 1, "left-half")
        # Visible target (0,0,960,1080) inflated by (7,0,7,7) -> outer (-7,0,974,1087).
        mock_set_pos.assert_called_once_with(
            hwnd, 0, -7, 0, 974, 1087,
            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
```

Add to the `__main__` block:

```python
    test_position_half_inflates_for_border()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py::test_position_half_inflates_for_border -v`
Expected: FAIL — `SetWindowPos` called with `(hwnd, 0, 0, 0, 960, 1080, ...)` (un-inflated), not the inflated coords.

- [ ] **Step 3: Write minimal implementation**

In `launcher.py`, add near the top imports (after `import time`):

```python
import ctypes
from ctypes import wintypes
```

Add a constant near the other module constants (after `TERMINAL_PROCESS`):

```python
DWMWA_EXTENDED_FRAME_BOUNDS = 9
```

Add the helper (place it directly above `_position`):

```python
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
```

Replace the non-maximized `else` branch of `_position` (currently `launcher.py:180-185`):

```python
    else:
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] == win32con.SW_SHOWMAXIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        ox, oy, ow, oh = monitors.inflate_for_border((x, y, w, h), _frame_margins(hwnd))
        win32gui.SetWindowPos(hwnd, 0, ox, oy, ow, oh,
                              win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (including the existing `test_position_maximized_restore`, which is untouched).

- [ ] **Step 5: Commit**

```bash
git add launcher.py tests/test_config.py
git commit -m "fix: tile windows flush to screen edge using DWM border margins"
```

---

### Task 3: "open-only" zone

**Files:**
- Modify: `config.py` (append to `ZONES`)
- Modify: `launcher.py` (early-return in `_position`)
- Test: `tests/test_config.py` (add test + `__main__` line)

**Interfaces:**
- Produces: zone value `"open-only"` — when set, `_position` finds/launches but never moves or resizes the window.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py` (after `test_position_half_inflates_for_border`):

```python
def test_position_open_only_is_noop():
    hwnd = 12345
    with mock.patch("monitors.get_monitors") as mock_get_mons, \
         mock.patch("win32gui.SetWindowPos") as mock_set_pos, \
         mock.patch("win32gui.ShowWindow") as mock_show:
        import launcher
        launcher._position(hwnd, 1, "open-only")
        mock_get_mons.assert_not_called()
        mock_set_pos.assert_not_called()
        mock_show.assert_not_called()


def test_open_only_in_zones():
    assert "open-only" in config.ZONES
```

Add to the `__main__` block:

```python
    test_position_open_only_is_noop()
    test_open_only_in_zones()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py::test_position_open_only_is_noop tests/test_config.py::test_open_only_in_zones -v`
Expected: FAIL — `test_open_only_in_zones` fails (not in `ZONES`); `test_position_open_only_is_noop` fails (`get_monitors` is called).

- [ ] **Step 3: Write minimal implementation**

In `config.py`, change the `ZONES` list to append the sentinel:

```python
ZONES = [
    "maximized", "left-half", "right-half", "top-half", "bottom-half",
    "top-left", "top-right", "bottom-left", "bottom-right", "open-only",
]
```

In `launcher.py`, add an early return as the first lines of `_position` (before `mons = monitors.get_monitors()`):

```python
def _position(hwnd: int, monitor_index: int, zone: str) -> None:
    if zone == "open-only":
        return  # find/launch only — leave the window where it opened
    mons = monitors.get_monitors()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config.py launcher.py tests/test_config.py
git commit -m "feat: add open-only zone that launches without repositioning"
```

---

### Task 4: `app_index.py` — resolve app name to exe

**Files:**
- Create: `app_index.py`
- Create: `tests/test_app_index.py`

**Interfaces:**
- Produces: `app_index.resolve(name: str) -> str | None` — returns an existing `.exe` path for the given app name (App Paths registry first, then Start Menu `.lnk` targets), or `None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_app_index.py`:

```python
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app_index import resolve


def test_resolve_empty_returns_none():
    assert resolve("") is None
    assert resolve("   ") is None


def test_resolve_nonsense_returns_none_no_raise():
    # A name that matches nothing must return None, never raise.
    assert resolve("zzz_no_such_app_xyzzy_98765") is None


if __name__ == "__main__":
    test_resolve_empty_returns_none()
    test_resolve_nonsense_returns_none_no_raise()
    print("test_app_index OK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_app_index.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app_index'`.

- [ ] **Step 3: Write minimal implementation**

Create `app_index.py`:

```python
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
                            path, _ = winreg.QueryValueEx(sk, None)  # default value
                    except OSError:
                        continue
                    if path and os.path.exists(path):
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_app_index.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app_index.py tests/test_app_index.py
git commit -m "feat: resolve app name to exe via App Paths and Start Menu"
```

---

### Task 5: "Find" button in Settings

**Files:**
- Modify: `settings_ui.py` (import `app_index`; add `find_by_name`; add a Find button beside the Path field)

**Interfaces:**
- Consumes: `app_index.resolve` (Task 4), `path_var`, `name_var` (existing StringVars in `_run`).

Note: this task edits the current (pre-dark-mode) `_run`. Task 7 rewrites `_run` and carries the same Find button forward — the code below is written so Task 7's rewrite already includes it. If Task 7 lands first for any reason, this button is already present and this task is a no-op.

- [ ] **Step 1: Add the import**

In `settings_ui.py`, add to the local imports (after `import monitors`):

```python
import app_index
```

- [ ] **Step 2: Add the resolver callback**

In `_run`, directly after the `browse_dir` function (currently `settings_ui.py:364-367`), add:

```python
    def find_by_name():
        p = app_index.resolve(name_var.get())
        if p:
            path_var.set(p.replace("/", "\\"))
        else:
            messagebox.showinfo(
                "App Launcher",
                "No match found — use the … button to browse.",
                parent=root,
            )
```

- [ ] **Step 3: Add the Find button beside Path**

Replace the `app_widgets = (...)` block (currently `settings_ui.py:395-404`) with a version that puts Find + browse in a small frame:

```python
    path_buttons = ttk.Frame(body)
    ttk.Button(path_buttons, text="Find", width=5, command=find_by_name).pack(side="left")
    ttk.Button(path_buttons, text="…", width=3, command=browse_file).pack(
        side="left", padx=(4, 0)
    )
    app_widgets = (
        add_row(2, "Path", ttk.Entry(body, textvariable=path_var), path_buttons)
        + add_row(3, "Args", ttk.Entry(body, textvariable=args_var))
        + add_row(4, "Match process", ttk.Entry(body, textvariable=match_var))
    )
```

- [ ] **Step 4: Verify manually**

Run: `python main.py`, open Settings (tray → Settings), click the `+` tile, type a known app name (e.g. `notepad`) into Name, click **Find**.
Expected: the Path field fills with the resolved `.exe` path. An unknown name shows the "No match found" info dialog. Existing tests still green: `python -m pytest tests/ -v`.

- [ ] **Step 5: Commit**

```bash
git add settings_ui.py
git commit -m "feat: add Find button to resolve app path by name"
```

---

### Task 6: `config.resolve_theme`

**Files:**
- Modify: `config.py` (add `import winreg`; add `resolve_theme`)
- Test: `tests/test_config.py` (add tests + `__main__` lines)

**Interfaces:**
- Produces: `config.resolve_theme(cfg: dict) -> str` returning `"light"` or `"dark"`. Reads `cfg["theme"]` (`"system"` | `"light"` | `"dark"`, default `"system"`); for `"system"` reads the Windows `AppsUseLightTheme` registry value.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py` (after the last test, before `__main__`):

```python
def test_resolve_theme_explicit():
    assert config.resolve_theme({"theme": "dark"}) == "dark"
    assert config.resolve_theme({"theme": "light"}) == "light"


def test_resolve_theme_system_reads_registry():
    # AppsUseLightTheme == 0 -> dark, non-zero/1 -> light.
    with mock.patch("winreg.OpenKey"), \
         mock.patch("winreg.QueryValueEx", return_value=(0, 4)):
        assert config.resolve_theme({"theme": "system"}) == "dark"
    with mock.patch("winreg.OpenKey"), \
         mock.patch("winreg.QueryValueEx", return_value=(1, 4)):
        assert config.resolve_theme({}) == "light"  # default is 'system'


def test_resolve_theme_registry_failure_defaults_light():
    with mock.patch("winreg.OpenKey", side_effect=OSError):
        assert config.resolve_theme({"theme": "system"}) == "light"
```

Add to the `__main__` block:

```python
    test_resolve_theme_explicit()
    test_resolve_theme_system_reads_registry()
    test_resolve_theme_registry_failure_defaults_light()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py::test_resolve_theme_explicit -v`
Expected: FAIL with `AttributeError: module 'config' has no attribute 'resolve_theme'`.

- [ ] **Step 3: Write minimal implementation**

In `config.py`, add `import winreg` to the imports (after `import os`), and append:

```python
_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def resolve_theme(cfg: dict) -> str:
    """Effective theme, 'light' or 'dark'. cfg['theme'] is 'system' (default),
    'light', or 'dark'; 'system' follows the Windows AppsUseLightTheme setting."""
    pref = cfg.get("theme", "system")
    if pref in ("light", "dark"):
        return pref
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE) as k:
            apps_light, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return "light" if apps_light else "dark"
    except OSError:
        return "light"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add resolve_theme following Windows apps theme"
```

---

### Task 7: Dark-mode Settings UI

**Files:**
- Modify: `settings_ui.py` (add `_palette`; give `_make_block`/`_make_plus_tile` a palette arg; wrap `_run` body in a re-callable `build_ui`; add a theme selector)
- Test: `tests/test_config.py` (add a `_palette` sanity test + `__main__` line)

**Interfaces:**
- Consumes: `config.resolve_theme` (Task 6), `app_index.resolve` (Task 4).
- Produces: `settings_ui._palette(is_dark: bool) -> dict` with keys `bg`, `field`, `border`, `hover`, `text`, `text_dim`. `_make_block(parent, entry, command, pal)` and `_make_plus_tile(parent, command, pal)` now take the palette dict.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py` (after the `resolve_theme` tests):

```python
def test_palette_light_dark_differ():
    light = settings_ui._palette(False)
    dark = settings_ui._palette(True)
    keys = {"bg", "field", "border", "hover", "text", "text_dim"}
    assert keys <= set(light) and keys <= set(dark)
    assert light["bg"] != dark["bg"]
    assert light["text"] != dark["text"]
```

Add to the `__main__` block:

```python
    test_palette_light_dark_differ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py::test_palette_light_dark_differ -v`
Expected: FAIL with `AttributeError: module 'settings_ui' has no attribute '_palette'`.

- [ ] **Step 3: Add `_palette`**

In `settings_ui.py`, add after the module constants (`_PANEL_W = 340`):

```python
def _palette(is_dark: bool) -> dict:
    if is_dark:
        return {
            "bg": "#1e1e1e",
            "field": "#2d2d2d",
            "border": "#3a3a3a",
            "hover": "#4a90d9",
            "text": "#e0e0e0",
            "text_dim": "#808080",
        }
    return {
        "bg": "#f0f0f0",
        "field": "#ffffff",
        "border": "#dcdcdc",
        "hover": "#4a90d9",
        "text": "#404040",
        "text_dim": "#a0a0a0",
    }
```

- [ ] **Step 4: Palette-ize `_make_block`**

Replace `_make_block` (currently `settings_ui.py:155-195`) with:

```python
def _make_block(parent: tk.Widget, entry: dict, command, pal: dict) -> tk.Frame:
    enabled = entry.get("enabled", True)
    f = tk.Frame(
        parent,
        width=_BLOCK,
        height=_BLOCK,
        bg=pal["bg"],
        cursor="hand2",
        highlightthickness=1,
        highlightbackground=pal["border"],
    )
    f.pack_propagate(False)
    icon = tk.Label(f, image=_icon_image(entry, dimmed=not enabled), bg=pal["bg"])
    name = entry.get("name") or ""
    if len(name) > 12:
        name = name[:11] + "…"
    label = tk.Label(
        f,
        text=name,
        font=("Segoe UI", 9),
        bg=pal["bg"],
        fg=pal["text"] if enabled else pal["text_dim"],
    )
    icon.pack(pady=(12, 2))
    label.pack()

    def on_enter(_e):
        f.configure(highlightbackground=pal["hover"])

    def on_leave(_e):
        x, y = f.winfo_pointerxy()
        fx = f.winfo_rootx()
        fy = f.winfo_rooty()
        fw = f.winfo_width()
        fh = f.winfo_height()
        if not (fx <= x < fx + fw and fy <= y < fy + fh):
            f.configure(highlightbackground=pal["border"])

    f.bind("<Enter>", on_enter)
    f.bind("<Leave>", on_leave)
    for w in (f, icon, label):
        w.bind("<Button-1>", lambda _e: command())
    return f
```

- [ ] **Step 5: Palette-ize `_make_plus_tile`**

Replace `_make_plus_tile` (currently `settings_ui.py:198-207`) with:

```python
def _make_plus_tile(parent: tk.Widget, command, pal: dict) -> tk.Canvas:
    c = tk.Canvas(
        parent, width=_BLOCK, height=_BLOCK, highlightthickness=0,
        cursor="hand2", bg=pal["bg"],
    )
    c.create_rectangle(5, 5, _BLOCK - 5, _BLOCK - 5, dash=(3, 2), outline=pal["text_dim"])
    c.create_text(
        _BLOCK / 2, _BLOCK / 2, text="+", font=("Segoe UI", 24), fill=pal["text_dim"]
    )
    c.bind("<Button-1>", lambda _e: command())
    return c
```

- [ ] **Step 6: Rewrite `_run` with a re-callable `build_ui` and theme selector**

Replace the entire `_run` function (currently `settings_ui.py:223-537`) with the following. The four panel callbacks — `save_entry`, `remove_entry`, `toggle_entry`, `load_panel` — are **copied verbatim** from the current `_run` (`settings_ui.py:440-533`); no logic changes, they just now live inside `build_ui`. They are shown in full below so the function is complete.

```python
def _run() -> None:
    global _root
    root = tk.Tk()
    _root = root
    root.title("App Launcher — Settings")
    root.geometry("720x480")
    root.minsize(480, 320)
    root.bind("<<Lift>>", lambda e: (root.deiconify(), root.lift(), root.focus_force()))

    cfg = config.load()
    cfg.setdefault("hotkey", config.DEFAULT_HOTKEY)
    cfg.setdefault("entries", [])
    cfg.setdefault("theme", "system")

    style = ttk.Style(root)
    theme_labels = {"system": "System", "light": "Light", "dark": "Dark"}

    def build_ui():
        pal = _palette(config.resolve_theme(cfg) == "dark")
        for w in root.winfo_children():
            w.destroy()
        _photo_cache.clear()  # drop icons cached for the destroyed widget tree
        root.configure(bg=pal["bg"])
        try:
            style.theme_use("clam")  # 'clam' honors background colors; native themes don't
        except tk.TclError:
            pass
        style.configure(".", background=pal["bg"], foreground=pal["text"])
        style.configure("TFrame", background=pal["bg"])
        style.configure("TLabel", background=pal["bg"], foreground=pal["text"])
        style.configure("TButton", background=pal["field"], foreground=pal["text"])
        style.map("TButton", background=[("active", pal["hover"])])
        style.configure("TRadiobutton", background=pal["bg"], foreground=pal["text"])
        style.map("TRadiobutton", background=[("active", pal["bg"])])
        style.configure("TEntry", fieldbackground=pal["field"], foreground=pal["text"])
        style.configure("TSpinbox", fieldbackground=pal["field"], foreground=pal["text"])
        style.configure("TCombobox", fieldbackground=pal["field"], foreground=pal["text"])
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", pal["field"])],
            foreground=[("readonly", pal["text"])],
        )

        def launch_now():
            threading.Thread(target=launcher.launch_all, daemon=True).start()

        top = ttk.Frame(root, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text="App Launcher", font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Button(top, text="Launch Now", command=launch_now).pack(side="right")

        theme_var = tk.StringVar(value=theme_labels[cfg.get("theme", "system")])

        def on_theme_change(_e=None):
            inv = {v: k for k, v in theme_labels.items()}
            cfg["theme"] = inv.get(theme_var.get(), "system")
            config.save(cfg)
            build_ui()  # rebuild body with the new palette (closes any open edit panel)

        theme_box = ttk.Combobox(
            top, values=list(theme_labels.values()),
            textvariable=theme_var, state="readonly", width=8,
        )
        theme_box.pack(side="right", padx=(0, 8))
        theme_box.bind("<<ComboboxSelected>>", on_theme_change)

        host = tk.Frame(root, bg=pal["bg"])
        host.pack(fill="both", expand=True)

        canvas = tk.Canvas(host, highlightthickness=0, bg=pal["bg"])
        vsb = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=pal["bg"])
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        def _on_mousewheel(e):
            units = -2 if e.delta > 0 else 2
            canvas.yview_scroll(units, "units")

        def _on_canvas_leave(_e):
            x, y = canvas.winfo_pointerxy()
            cx = canvas.winfo_rootx()
            cy = canvas.winfo_rooty()
            cw = canvas.winfo_width()
            ch = canvas.winfo_height()
            if not (cx <= x < cx + cw and cy <= y < cy + ch):
                canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", lambda _: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", _on_canvas_leave)

        grid_cols = [0]

        def persist():
            config.save(cfg)
            refresh()

        def refresh():
            for w in inner.winfo_children():
                w.destroy()
            cols = max(1, canvas.winfo_width() // (_BLOCK + 2 * _PAD))
            grid_cols[0] = cols
            for i, entry in enumerate(cfg["entries"]):
                block = _make_block(inner, entry, lambda i=i: load_panel(i), pal)
                block.grid(row=i // cols, column=i % cols, padx=_PAD, pady=_PAD)
            n = len(cfg["entries"])
            plus = _make_plus_tile(inner, lambda: load_panel(None), pal)
            plus.grid(row=n // cols, column=n % cols, padx=_PAD, pady=_PAD)

        def on_canvas_resize(event):
            canvas.itemconfigure(inner_id, width=event.width)
            if max(1, event.width // (_BLOCK + 2 * _PAD)) != grid_cols[0]:
                refresh()

        canvas.bind("<Configure>", on_canvas_resize)

        panel = tk.Frame(
            host, highlightthickness=1, highlightbackground=pal["border"], bg=pal["bg"]
        )
        anim = {"busy": False, "open": False}
        state = {"index": None}

        def slide(frm, to, done=None):
            anim["busy"] = True
            steps = 10

            def tick(i):
                if not root.winfo_exists() or not panel.winfo_exists():
                    return
                panel.place_configure(x=int(frm + (to - frm) * i / steps))
                if i < steps:
                    root.after(15, lambda: tick(i + 1))
                else:
                    anim["busy"] = False
                    if done:
                        done()

            tick(1)

        def open_panel():
            if anim["open"]:
                return
            for child in inner.winfo_children():
                if isinstance(child, tk.Frame):
                    child.configure(highlightbackground=pal["border"])
            anim["open"] = True
            panel.place(x=-_PANEL_W, y=0, width=_PANEL_W, relheight=1.0)
            panel.lift()
            slide(-_PANEL_W, 0)

        def close_panel():
            if not anim["open"] or anim["busy"]:
                return
            anim["open"] = False
            slide(0, -_PANEL_W, done=panel.place_forget)

        header = ttk.Frame(panel, padding=(8, 8, 8, 0))
        header.pack(fill="x")
        ttk.Button(header, text="◀ Back", command=close_panel).pack(side="left")

        kind_var = tk.StringVar(value="app")
        name_var = tk.StringVar()
        path_var = tk.StringVar()
        args_var = tk.StringVar()
        match_var = tk.StringVar()
        workdir_var = tk.StringVar()
        cmd_var = tk.StringVar()
        mon_var = tk.StringVar(value="1")
        zone_var = tk.StringVar(value="maximized")

        body = ttk.Frame(panel, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        def browse_file():
            p = filedialog.askopenfilename(
                parent=root, filetypes=[("Programs", "*.exe"), ("All files", "*.*")]
            )
            if p:
                path_var.set(p.replace("/", "\\"))

        def browse_dir():
            p = filedialog.askdirectory(parent=root)
            if p:
                workdir_var.set(p.replace("/", "\\"))

        def find_by_name():
            p = app_index.resolve(name_var.get())
            if p:
                path_var.set(p.replace("/", "\\"))
            else:
                messagebox.showinfo(
                    "App Launcher",
                    "No match found — use the … button to browse.",
                    parent=root,
                )

        def add_row(r, label, widget, extra=None):
            lbl = ttk.Label(body, text=label)
            lbl.grid(row=r, column=0, sticky="w", pady=3, padx=(0, 8))
            widget.grid(row=r, column=1, sticky="we", pady=3)
            if extra is not None:
                extra.grid(row=r, column=2, padx=(4, 0))
            return [lbl, widget] + ([extra] if extra is not None else [])

        kind_frame = ttk.Frame(body)
        ttk.Radiobutton(
            kind_frame, text="App", variable=kind_var, value="app",
            command=lambda: update_kind(),
        ).pack(side="left")
        ttk.Radiobutton(
            kind_frame, text="Terminal", variable=kind_var, value="terminal",
            command=lambda: update_kind(),
        ).pack(side="left", padx=(8, 0))
        add_row(0, "Kind", kind_frame)
        add_row(1, "Name", ttk.Entry(body, textvariable=name_var))

        path_buttons = ttk.Frame(body)
        ttk.Button(path_buttons, text="Find", width=5, command=find_by_name).pack(side="left")
        ttk.Button(path_buttons, text="…", width=3, command=browse_file).pack(
            side="left", padx=(4, 0)
        )
        app_widgets = (
            add_row(2, "Path", ttk.Entry(body, textvariable=path_var), path_buttons)
            + add_row(3, "Args", ttk.Entry(body, textvariable=args_var))
            + add_row(4, "Match process", ttk.Entry(body, textvariable=match_var))
        )
        terminal_widgets = add_row(
            5, "Workdir",
            ttk.Entry(body, textvariable=workdir_var),
            ttk.Button(body, text="…", width=3, command=browse_dir),
        ) + add_row(6, "Startup command", ttk.Entry(body, textvariable=cmd_var))

        monitor_count = max(1, len(monitors.get_monitors()))
        add_row(
            7, "Monitor",
            ttk.Spinbox(body, from_=1, to=max(monitor_count, 9), textvariable=mon_var, width=5),
        )
        add_row(
            8, "Zone",
            ttk.Combobox(body, values=config.ZONES, textvariable=zone_var, state="readonly"),
        )

        def update_kind():
            is_app = kind_var.get() == "app"
            for w in app_widgets:
                w.grid() if is_app else w.grid_remove()
            for w in terminal_widgets:
                w.grid_remove() if is_app else w.grid()

        def save_entry():
            if anim["busy"]:
                return
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("App Launcher", "Name is required.", parent=root)
                return
            try:
                monitor = max(1, int(mon_var.get()))
            except ValueError:
                monitor = 1
            i = state["index"]
            old = cfg["entries"][i] if i is not None else {}
            kind = kind_var.get()
            entry = {
                "name": name,
                "enabled": old.get("enabled", True),
                "kind": kind,
                "monitor": monitor,
                "zone": zone_var.get(),
            }
            if kind == "app":
                path = path_var.get().strip()
                entry["path"] = path
                entry["args"] = args_var.get().strip()
                entry["match_process"] = match_var.get().strip() or os.path.basename(path)
                check_path = path
            else:
                entry["workdir"] = workdir_var.get().strip()
                entry["startup_command"] = cmd_var.get().strip()
                check_path = entry["workdir"]
            if check_path and not os.path.exists(check_path):
                if not messagebox.askyesno(
                    "App Launcher",
                    f"{check_path} does not exist. Save anyway?",
                    parent=root,
                ):
                    return
            if i is None:
                cfg["entries"].append(entry)
            else:
                cfg["entries"][i] = entry
            persist()
            close_panel()

        def remove_entry():
            if state["index"] is None:
                return
            if anim["busy"]:
                return
            del cfg["entries"][state["index"]]
            persist()
            close_panel()

        def toggle_entry():
            if state["index"] is None:
                return
            if anim["busy"]:
                return
            e = cfg["entries"][state["index"]]
            e["enabled"] = not e.get("enabled", True)
            persist()
            close_panel()

        btns = ttk.Frame(body)
        btns.grid(row=9, column=0, columnspan=3, sticky="we", pady=(12, 0))
        save_btn = ttk.Button(btns, text="Save", command=save_entry)
        toggle_btn = ttk.Button(btns, text="Disable", command=toggle_entry)
        remove_btn = ttk.Button(btns, text="Remove", command=remove_entry)
        save_btn.pack(side="left")

        def load_panel(i):
            if anim["busy"]:
                return
            state["index"] = i
            e = cfg["entries"][i] if i is not None else {}
            kind_var.set(e.get("kind", "app"))
            name_var.set(e.get("name", ""))
            path_var.set(e.get("path", ""))
            args_var.set(e.get("args", ""))
            match_var.set(e.get("match_process", ""))
            workdir_var.set(e.get("workdir", ""))
            cmd_var.set(e.get("startup_command", ""))
            mon_var.set(str(e.get("monitor", 1)))
            zone_var.set(e.get("zone", "maximized"))
            update_kind()
            toggle_btn.pack_forget()
            remove_btn.pack_forget()
            if i is not None:
                toggle_btn.configure(text="Disable" if e.get("enabled", True) else "Enable")
                toggle_btn.pack(side="left", padx=6)
                remove_btn.pack(side="left")
            open_panel()

        refresh()

    build_ui()
    root.mainloop()
    _root = None
```

- [ ] **Step 7: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: PASS. `test_open_settings_starts_thread` and `test_open_settings_lifts_existing_window` still pass — `open_settings`, `_ui_thread`, and `_root` are unchanged.

- [ ] **Step 8: Verify manually**

Run: `python main.py`, open Settings. With the theme selector at **System**, confirm the window matches your Windows apps theme. Switch to **Dark** → the window (grid, panel, entry fields, buttons, dropdowns) restyles immediately. Switch to **Light** → restyles back. Reopen Settings and confirm the choice persisted. Open the edit panel and confirm the **Find** button still works.

- [ ] **Step 9: Commit**

```bash
git add settings_ui.py tests/test_config.py
git commit -m "feat: add dark mode following Windows theme with manual override"
```

---

## Notes / known ceilings

- Dark mode is functional, not pixel-perfect: `clam` restyles the common ttk widgets, but the OS-drawn window title bar stays system-themed. Letter-tile icons keep their name-hash colors.
- `resolve(name)` is first-match best-effort; the `…` browse button remains the reliable fallback for ambiguous names.
- The border fix depends on DWM; `_frame_margins` returns `(0,0,0,0)` on failure, falling back to today's slightly-gapped placement rather than erroring.
- Toggling the theme rebuilds the Settings body and therefore closes any open edit panel — an accepted minor UX cost of live re-theming.
