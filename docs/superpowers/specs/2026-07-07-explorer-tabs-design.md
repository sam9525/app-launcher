# Explorer Groups — Design Spec

**Date:** 2026-07-07
**Feature:** Open Windows Explorer as configurable groups — one window per group, folders as tabs within it. Multiple groups open multiple windows.

## Goal

Let a user configure named groups of folders. Each group opens as **one Explorer
window** with each folder as a **tab**. Several groups produce several windows,
each with its own tab set. Positioned into a monitor zone like every other entry.

## Key technical constraint

Windows exposes **no supported API or CLI** to open a folder as a *new tab* in an
existing Explorer window. `explorer.exe <path>` opens/reuses a *window*, never a
tab. The only mechanism is simulating keystrokes (`Ctrl+T` → address bar → type
path → `Enter`) while the window is foreground. This is the same class of
fragility the project already accepts for a terminal's `startup_command`, and it
reuses the same foreground-confirmation guard.

## Decisions (from brainstorming)

1. **Model:** group = window, folders = tabs. `folders[0]` is the first tab.
2. **Repeat press:** open once per run, then leave alone — identical to
   terminals (no respawn, no reposition on later presses).
3. **Reliability:** best-effort tabs via SendKeys, only when foreground is
   confirmed; skip cleanly otherwise. Never type into the wrong window.
4. **Cap:** at most `MAX_EXPLORER_FOLDERS = 6` folders per group (first tab + 5
   more). Extra folders ignored with a summary note. Bounds focus-steal time.

## Data model

New entry `kind: "explorer"`. Config stays schemaless (as designed).

```json
{
  "name": "Work",
  "enabled": true,
  "kind": "explorer",
  "monitor": 1,
  "zone": "left-half",
  "folders": ["C:\\proj\\a", "C:\\proj\\b", "D:\\docs"]
}
```

`monitor` / `zone` reuse the existing positioning path unchanged.

## `launcher.py`

New module-level state, mirroring the terminal pattern:

```python
EXPLORER_PROCESS = "explorer.exe"
MAX_EXPLORER_FOLDERS = 6  # first tab + 5 more; caps focus-steal time
_launched_explorers: set = set()  # keyed (name, tuple(folders)); cleared on restart
```

Pure helper (GUI-free, shared with the UI, unit-tested):

```python
def parse_folder_lines(text: str) -> list[str]:
    """One folder path per line; blanks and surrounding whitespace dropped."""
    return [ln.strip() for ln in text.splitlines() if ln.strip()]
```

New branch in `_handle_entry` for `kind == "explorer"`:

1. `folders = entry.get("folders", [])`; if empty → return `"no folders configured"`.
2. `capped = folders[:MAX_EXPLORER_FOLDERS]`.
3. `key = (entry.get("name"), tuple(capped))`; if in `_launched_explorers` → return
   `None` (open once, then leave alone).
4. `before = set(_windows_for(EXPLORER_PROCESS, pid_names))`.
5. `subprocess.Popen(["explorer.exe", capped[0]])` (extend `_spawn`, or inline).
6. `hwnd = _poll_new_window(EXPLORER_PROCESS, before, pid_names)`; if `None` →
   return `"unpositioned (no window within 15 s)"`.
7. `_position(hwnd, monitor, zone)`.
8. `sent = _send_explorer_tabs(hwnd, capped[1:])` — see below.
9. `_launched_explorers.add(key)` (only after the window opened).
10. Build the return note: if `len(folders) > MAX_EXPLORER_FOLDERS`, mention
    capping; if `sent < len(capped) - 1`, mention tabs not added; else `None`.

### `_send_explorer_tabs(hwnd, folders) -> int`

Returns count of tabs successfully sent. Reuses the foreground-confirmation loop
from `_send_startup_command` (`FOREGROUND_RETRIES` / `FOREGROUND_RETRY_DELAY`).
For each folder: confirm `hwnd` is foreground, then via `WScript.Shell.SendKeys`:
`^t` (new tab) → `^l` (focus address bar) → `_sendkeys_escape(path)` → `{ENTER}`,
with short sleeps between steps.

```python
EXPLORER_TAB_DELAY = 0.4  # ponytail: fixed sleep between tab keystrokes; the flaky knob
```

If foreground can't be confirmed for a folder, stop and return the count sent so
far — never blind-type. `pythoncom.CoInitialize/Uninitialize` around the COM use,
as in `_send_startup_command`.

### Honest limitations (commented in code)

- Tabs are focus-stealing best-effort — same fragility class as `startup_command`.
- If `explorer.exe <folder0>` reuses an existing window instead of spawning one,
  the poll finds nothing new and tabs are not added. Acceptable for the
  launch-fresh use case. `# ponytail:` comment names it.

## `settings_ui.py`

- `kind_seg` gains `"Explorer"`: `values=["App", "Terminal", "Explorer"]`.
- New `explorer_widgets`: a `CTkTextbox` (one folder path per line) plus a `…`
  button that appends a `filedialog.askdirectory` pick as a new line. **No custom
  reorderable list widget** — a textbox is the sufficient, lazy editor.
- Parse on save via `launcher.parse_folder_lines(textbox.get("1.0", "end"))` — a
  GUI-free helper (below), so the same logic is unit-testable without Tk.
- `update_kind()` extends to three-way show/hide across app / terminal / explorer
  widget sets.
- `save_entry`: when kind is explorer, write `folders`; skip `path`/`match_process`
  and the `os.path.exists(path)` check (validate first folder exists instead, with
  the same "save anyway?" prompt).
- `load_panel`: populate the textbox from `entry.get("folders", [])`.
- Icon: special-case `src = os.path.join(os.environ["WINDIR"], "explorer.exe")`
  for `kind == "explorer"` in `_icon_image`, mirroring the existing `wt.exe` case,
  so the tile shows the real Explorer icon.
- `open_one` and `zone_preview.build_map` already key off the entry dict — no change.

## Tests

`tests/test_explorer.py` — `assert`-based `__main__` self-check for
`launcher.parse_folder_lines` (blank-line/whitespace stripping) and for the
`folders[:MAX_EXPLORER_FOLDERS]` cap behavior. Everything else is live-desktop
Win32 side-effect, untestable without a real session — same as the rest of
`launcher.py`.

## Files touched

| File | Change |
|------|--------|
| `launcher.py` | explorer branch in `_handle_entry`, `_send_explorer_tabs`, const + set |
| `settings_ui.py` | `Explorer` segment, folders textbox editor, save/load, icon case |
| `tests/test_explorer.py` | folder-list parse/cap self-check |
| `config.py` | untouched (schemaless) |

## Out of scope (YAGNI)

- Reordering tabs, per-tab monitor/zone, tab titles.
- Reliable window re-find on repeat press (would need title matching — unreliable).
- Any tab mechanism other than SendKeys (none exists).
