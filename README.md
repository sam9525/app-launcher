# App Launcher

A Windows-only Python tray app: one hotkey (`Ctrl+Alt+L` by default) finds-or-launches a configured set of apps, terminals, and Explorer folder groups, then positions each into a monitor zone.

## Install & Run

Run `AppLauncher-Setup.exe`, or from source:

```
pip install -r requirements.txt
python main.py
```

Requires Windows, Python 3.10+, and Windows Terminal (`wt.exe`) for terminal entries.

## Usage

- **Hotkey** or tray icon **Launch**: for each enabled entry, find its window by process name (or launch it), then move it to its zone. Press again to re-tile.
- Tray icon **Settings**: edit entries. Each entry is a tile with an enable switch, an **Open** button, and a preview of which monitor and zone it lands in.
- Tray icon **Update available**: appears when a newer GitHub release exists (checked at startup and daily); click it to open the release page.
- Tray icon **Exit**: quit.

The Settings top bar shows the app version and has a **Dark** switch (the default follows the Windows apps theme and accent colour) and a **Run at startup** switch, which is turned on the first time the app runs.

The hotkey is not editable in Settings; change the top-level `hotkey` key in `config.json` and restart.

## Configuration

Stored at `%APPDATA%\AppLauncher\config.json` (edit entries and theme via Settings, the rest by hand):

```json
{
  "hotkey": "ctrl+alt+l",
  "theme": "system",
  "entries": [
    {
      "name": "Editor",
      "kind": "app",
      "path": "C:\\Program Files\\Editor\\editor.exe",
      "args": "",
      "match_process": "editor.exe",
      "monitor": 1,
      "zone": "left-half",
      "enabled": true
    },
    {
      "name": "Shell",
      "kind": "terminal",
      "workdir": "D:\\data",
      "startup_command": "git status",
      "monitor": 2,
      "zone": "right-half"
    },
    {
      "name": "Project folders",
      "kind": "explorer",
      "folders": ["D:\\data", "D:\\data\\Program"],
      "monitor": 2,
      "zone": "bottom-half"
    }
  ]
}
```

- `kind`:
  - `"app"` — launched from `path`, matched by `match_process`. Apps that need admin rights open through a UAC prompt, are not placed in a zone, and launch at most once per launcher run; cancelling shows `admin approval declined`.
  - `"terminal"` — spawned via `wt.exe -d workdir`; optional `startup_command` is typed into the new terminal.
  - `"explorer"` — first folder in `folders` opens a window, the rest become tabs in it (capped at 6 folders; extras are reported as a note).
- `monitor`: 1-indexed; out-of-range falls back to the primary monitor.
- `zone`: `maximized`, `left-half`, `right-half`, `top-half`, `bottom-half`, `top-left`, `top-right`, `bottom-left`, `bottom-right`, or `open-only` (launch without positioning).
- `enabled`: defaults to `true`; disabled entries are skipped on launch.
- `hotkey` (top level): defaults to `ctrl+alt+l`.
- `theme` (top level): `system`, `light`, or `dark`; the Settings Dark switch writes `dark` or `light`.

A corrupt config is backed up as `config.json.bad` and replaced with an empty default, and Settings opens automatically.

## Tests

```
python -m pytest tests/
```

Covers zone math, config I/O, launch and spawn behaviour, the update check, and the Settings window and tray (some tests mock Win32 and Tk calls).

## Releasing

1. Add a `## vX.Y.Z` section to [CHANGELOG.md](CHANGELOG.md) (a test requires one for the current version).
2. Bump `VERSION` in `version.py` on `develop` (the only place a version is typed).
3. Merge `develop` into `master` with `--no-ff`.
4. Tag the merge commit `vX.Y.Z` (annotated).

The installer build (`installer\build.bat`) reads `VERSION` and passes it to Inno Setup.

## Layout

```
main.py          entry: DPI awareness, single-instance mutex, hotkey thread, tray loop
config.py        load/save config.json, run-at-startup + Windows theme registry
monitors.py      monitor enumeration + zone→rect math
launcher.py      find-or-launch-then-position core
tray.py          tray icon/menu + global hotkey message loop
settings_ui.py   CustomTkinter entry editor
zone_preview.py  monitor/zone preview map drawn on the entry tiles
app_index.py     installed-app lookup for the entry picker
updates.py       daily GitHub release check behind the tray update item
version.py       VERSION, the only place the version number is typed
```
