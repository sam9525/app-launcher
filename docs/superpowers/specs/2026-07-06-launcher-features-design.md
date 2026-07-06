# Design — Four launcher enhancements

Date: 2026-07-06

Four independent changes to the App Launcher: a positioning bug fix, an
"open-only" zone, find-app-by-name, and a dark mode. Each is small and can
land independently.

## 1. Flush positioning (bug fix)

### Problem
Non-maximized zones (`left-half`, etc.) leave a visible gap at the screen edge
and between tiled halves. Cause: `_position` sets the window's **outer bounding
box** to the zone rect via `SetWindowPos`, but modern Windows windows have an
invisible DWM drop-shadow border (~7px left/right/bottom, ~0 top). The
*visible* edge sits inset from the bounding box by that margin. Windows Snap
compensates for this; we don't.

### Fix
- `monitors.py` — new pure function:
  ```
  inflate_for_border(rect, margins) -> rect
  ```
  `rect` and `margins` are both `(left, top, right, bottom)`-style tuples.
  Given a target visible rect `(x, y, w, h)` and margins `(l, t, r, b)`,
  returns the outer rect to pass to `SetWindowPos`:
  `(x - l, y - t, w + l + r, h + t + b)`. Pure math, unit-tested.

- `launcher.py` — new helper `_frame_margins(hwnd) -> tuple[int,int,int,int]`:
  compares `win32gui.GetWindowRect(hwnd)` (outer bounds) against the DWM
  extended frame bounds (`DwmGetWindowAttribute` with
  `DWMWA_EXTENDED_FRAME_BOUNDS = 9`, called via `ctypes`/`dwmapi.dll` into a
  `RECT`). Margins = `(vis_left - outer_left, vis_top - outer_top,
  outer_right - vis_right, outer_bottom - vis_bottom)`. On any failure returns
  `(0, 0, 0, 0)` — i.e. today's behavior.

- `_position` applies the inflation to **non-maximized, non-open-only** zones
  only. The `maximized` path is unchanged (`SW_MAXIMIZE` already fills the work
  area correctly).

### Test
`tests/test_zones.py` gains assertions on `inflate_for_border` (e.g. a
left-half rect inflated by `(7,0,7,7)` produces the expected outer rect;
zero margins are a no-op).

## 2. "Open only" zone

A zone that finds-or-launches the app but never moves or resizes it.

- `config.py` — add `"open-only"` to `ZONES` (appears in the Zone dropdown).
- `launcher.py` — `_position` early-returns immediately when
  `zone == "open-only"`: no restore, no border math, no `SetWindowPos`.

No other changes; `_handle_entry` already routes all zones through `_position`.

## 3. Find app by name

Resolve a typed app name to its executable path, so adding an app doesn't
require hunting for the `.exe` manually.

- New module `app_index.py`:
  ```
  resolve(name: str) -> str | None
  ```
  Search order, first hit wins:
  1. **App Paths registry** — enumerate
     `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\*` and the
     `HKCU` equivalent (via `winreg`). Keys look like `chrome.exe`; the default
     value is the full path. Match `name` (case-insensitive) against the key
     stem.
  2. **Start Menu shortcuts** — scan `.lnk` files under
     `%ProgramData%\Microsoft\Windows\Start Menu\Programs` and
     `%APPDATA%\Microsoft\Windows\Start Menu\Programs` (recursive). Match the
     shortcut filename stem against `name`; resolve the target with
     `win32com.client.Dispatch("WScript.Shell").CreateShortcut(lnk).TargetPath`.
  Returns the path string, or `None` if nothing matches or the target is not an
  existing file.

- `settings_ui.py` — a **"Find"** button next to the Path field's `…` browse
  button. On click: `resolve(name_var.get())`; if a path is returned, set
  `path_var`; otherwise a messagebox suggesting the browse button. Match-process
  continues to auto-fill from the path on save (existing behavior).

### Test
`tests/test_app_index.py` — a light self-check that `resolve` returns `None`
for a nonsense name and does not raise. (Registry/filesystem content is
machine-dependent, so no positive-match assertion is hard-coded.)

## 4. Dark mode (follow Windows theme, with manual override)

### Config
- `cfg["theme"]` = `"system"` (default) | `"light"` | `"dark"`.
- `config.py` — new `resolve_theme(cfg) -> str` returning `"light"` or
  `"dark"`. For `"system"`, read
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize` value
  `AppsUseLightTheme` (`0` → dark, `1`/missing → light) via `winreg`.

### UI theming
- `settings_ui.py` — new `_palette(is_dark) -> dict` centralizing every color
  literal currently hardcoded (window/canvas/panel backgrounds, block border
  `#dcdcdc`, hover blue `#4a90d9`, text greys `#404040`/`#a0a0a0`, plus-tile
  colors). `_make_block`, `_make_plus_tile`, and the panel/canvas construction
  read from the palette instead of literals.
- ttk widgets (Entry, Combobox, Button, Spinbox, Scrollbar) are restyled via a
  `clam`-based `ttk.Style` so backgrounds/foregrounds actually apply in dark
  mode (the default Windows ttk theme ignores background colors).
- A theme selector (System / Light / Dark — combobox or menubutton) in the top
  bar next to "Launch Now". Changing it saves `cfg["theme"]` and **rebuilds the
  window body** to apply immediately.

### Live re-theming
UI construction (everything after `root = tk.Tk()` in `_run`) moves into a
re-callable `build_ui()`. Applying a theme change destroys the current body
widgets and calls `build_ui()` again with the new palette. The Tk root and the
`_ui_thread` guard are unchanged.

### Test
No automated test — Tkinter rendering isn't unit-testable here. `resolve_theme`
gets a small assertion in `tests/test_config.py` (explicit `"light"`/`"dark"`
pass through unchanged).

## Trade-offs / known ceilings

- **Dark mode** is functional, not pixel-perfect. Native ttk dark support on
  Windows is limited; the `clam` restyle covers the common widgets but some
  system-drawn chrome (window title bar) stays OS-themed. Letter-tile icons
  keep their existing hash colors.
- **`resolve(name)`** is best-effort — first App Paths / Start Menu match.
  Ambiguous names may resolve wrong; the manual `…` browse button remains the
  reliable path.
- **Border fix** depends on DWM. If `DwmGetWindowAttribute` fails, positioning
  falls back to today's (slightly-gapped) behavior rather than erroring.

## Build order

1. `monitors.inflate_for_border` + test → `launcher._frame_margins` + wire into
   `_position` (bug fix, self-contained).
2. `open-only` zone (`config.ZONES` + `_position` early-return).
3. `app_index.py` + Settings "Find" button.
4. Dark mode: `config.resolve_theme` → `_palette` refactor → theme selector +
   `build_ui()` live rebuild.
