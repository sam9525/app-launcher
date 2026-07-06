# App Launcher

A Windows-only Python tray app: one hotkey (`Ctrl+Alt+L` by default) finds-or-launches a configured set of apps and terminals, then positions each into a monitor zone.

## Install & Run

```
pip install -r requirements.txt
python main.py
```

Requires Windows, Python 3.10+, and Windows Terminal (`wt.exe`) for terminal entries.

## Usage

- **Hotkey** or tray icon **Launch**: for each configured entry, find its window by process name (or launch it), then move it to its zone. Press again to re-tile.
- Tray icon **Settings**: edit entries and the hotkey in a small Tkinter UI.
- Tray icon **Exit**: quit.

## Configuration

Stored at `%APPDATA%\AppLauncher\config.json` (edit via Settings or by hand):

```json
{
  "hotkey": "ctrl+alt+l",
  "entries": [
    {
      "name": "Editor",
      "kind": "app",
      "path": "C:\\Program Files\\Editor\\editor.exe",
      "args": "",
      "match_process": "editor.exe",
      "monitor": 1,
      "zone": "left-half"
    },
    {
      "name": "Shell",
      "kind": "terminal",
      "workdir": "D:\\data",
      "startup_command": "git status",
      "monitor": 2,
      "zone": "right-half"
    }
  ]
}
```

- `kind`: `"app"` (launched from `path`, matched by `match_process`) or `"terminal"` (spawned via `wt.exe -d workdir`; optional `startup_command` is typed into the new terminal).
- `monitor`: 1-indexed; out-of-range falls back to the primary monitor.
- `zone`: `maximized`, `left-half`, `right-half`, `top-half`, `bottom-half`, `top-left`, `top-right`, `bottom-left`, `bottom-right`.

A corrupt config is backed up as `config.json.bad` and replaced with an empty default, and Settings opens automatically.

## Tests

```
python -m pytest tests/
```

Pure-Python tests only (zone math, config I/O) — no Win32 mocking.

## Layout

```
main.py         entry: DPI awareness, single-instance mutex, hotkey thread, tray loop
config.py       load/save config.json
monitors.py     monitor enumeration + zone→rect math
launcher.py     find-or-launch-then-position core
tray.py         tray icon/menu + global hotkey message loop
settings_ui.py  Tkinter entry editor
```
