# Explorer Groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `explorer` entry kind that opens one File Explorer window per group with each configured folder as a tab, positioned into a monitor zone.

**Architecture:** Mirror the existing `terminal` path in `launcher.py` — one shared process (`explorer.exe`), launched once per run then left alone. Tabs are created by focus-confirmed SendKeys (the only mechanism Windows offers), capped per window. Settings UI gains a third kind with a plain textbox folder editor.

**Tech Stack:** Python, pywin32 (`win32gui`, `win32com`, `pythoncom`), `subprocess`, CustomTkinter.

## Global Constraints

- Windows-only; physical pixels (DPI awareness set in `main.py`).
- Config is schemaless — no validation layer; new fields just appear in the dict.
- `launch_all()` is the single entry point; one bad entry never stops the loop.
- Tabs are **best-effort**: type only when the window is confirmed foreground; never blind-type into the wrong window.
- Cap: `MAX_EXPLORER_FOLDERS = 6` folders per group (first tab + 5 more).
- Match existing style: flat modules, `# ponytail:` comments naming deliberate shortcuts and their upgrade path.

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `launcher.py` | find-or-launch + position core | Add explorer constants, `parse_folder_lines`, explorer branch in `_handle_entry`, `_send_explorer_tabs`, extract `_confirm_foreground`, extend `_spawn` |
| `settings_ui.py` | entry-list editor | Add `Explorer` kind segment, folders textbox editor, save/load, icon case |
| `tests/test_explorer.py` | pure-logic self-check | Create — `parse_folder_lines` + empty-folders early return |
| `config.py` | config load/save | **Untouched** (schemaless) |

---

## Task 1: Launcher constants + folder-line parser

**Files:**
- Modify: `launcher.py` (constants near line 25, set near line 34, new pure helper)
- Test: `tests/test_explorer.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `launcher.EXPLORER_PROCESS: str = "explorer.exe"`
  - `launcher.MAX_EXPLORER_FOLDERS: int = 6`
  - `launcher.EXPLORER_TAB_DELAY: float = 0.4`
  - `launcher._launched_explorers: set`
  - `launcher.parse_folder_lines(text: str) -> list[str]` — one path per line, blanks/whitespace dropped.

- [ ] **Step 1: Write the failing test**

Create `tests/test_explorer.py`:

```python
"""Pure-logic checks for the explorer kind. No Win32 side effects here."""

import launcher


def test_parse_folder_lines_strips_blanks_and_whitespace():
    text = "  C:\\a  \n\n C:\\b\n\t\nD:\\c\n"
    assert launcher.parse_folder_lines(text) == ["C:\\a", "C:\\b", "D:\\c"]


def test_parse_folder_lines_empty():
    assert launcher.parse_folder_lines("\n  \n\t") == []


def test_cap_constant_is_six():
    assert launcher.MAX_EXPLORER_FOLDERS == 6


if __name__ == "__main__":
    test_parse_folder_lines_strips_blanks_and_whitespace()
    test_parse_folder_lines_empty()
    test_cap_constant_is_six()
    print("ok")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_explorer.py`
Expected: FAIL — `AttributeError: module 'launcher' has no attribute 'parse_folder_lines'`

- [ ] **Step 3: Add constants**

In `launcher.py`, after line 25 (`TERMINAL_PROCESS = "windowsterminal.exe"`) add:

```python
EXPLORER_PROCESS = "explorer.exe"
MAX_EXPLORER_FOLDERS = 6  # first tab + 5 more; caps focus-steal time
EXPLORER_TAB_DELAY = 0.4  # ponytail: fixed sleep between tab keystrokes; the flaky knob
```

After line 34 (`_launched_terminals: set = set()`) add:

```python
# Explorer groups launched once per run, keyed (name, tuple(folders)).
# ponytail: in-memory set, no persistence — a fresh run reopens windows
_launched_explorers: set = set()
```

- [ ] **Step 4: Add the parser**

In `launcher.py`, immediately after `_terminal_key` (ends at line 38, before `def launch_all`), add:

```python
def parse_folder_lines(text: str) -> list[str]:
    """One folder path per line; blanks and surrounding whitespace dropped."""
    return [ln.strip() for ln in text.splitlines() if ln.strip()]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python tests/test_explorer.py`
Expected: `ok`

Also run the whole suite to confirm nothing broke:
Run: `python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add launcher.py tests/test_explorer.py
git commit -m "feat: explorer constants and folder-line parser"
```

---

## Task 2: Explorer launch branch + tab sender

**Files:**
- Modify: `launcher.py` — extract `_confirm_foreground` (refactor of `_send_startup_command`), add explorer branch in `_handle_entry`, add `_send_explorer_tabs`, extend `_spawn`
- Test: `tests/test_explorer.py` (add empty-folders case)

**Interfaces:**
- Consumes: `EXPLORER_PROCESS`, `MAX_EXPLORER_FOLDERS`, `EXPLORER_TAB_DELAY`, `_launched_explorers`, `parse_folder_lines` (Task 1); existing `_windows_for`, `_poll_new_window`, `_position`, `_spawn`, `_sendkeys_escape`, `FOREGROUND_RETRIES`, `FOREGROUND_RETRY_DELAY`.
- Produces:
  - `_confirm_foreground(hwnd: int) -> bool`
  - `_send_explorer_tabs(hwnd: int, folders: list) -> int` (count of tabs sent)
  - `_handle_entry` handling `kind == "explorer"`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_explorer.py` (before `if __name__`):

```python
def test_handle_entry_empty_folders_returns_note():
    # Empty folders short-circuits before any Win32 call.
    note = launcher._handle_entry({"kind": "explorer", "folders": []}, {})
    assert note == "no folders configured"
```

And add its call inside `if __name__ == "__main__":`:

```python
    test_handle_entry_empty_folders_returns_note()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python tests/test_explorer.py`
Expected: FAIL — the explorer branch does not exist yet, so `_handle_entry` falls through to the app path and raises `KeyError: 'match_process'`.

- [ ] **Step 3: Extract `_confirm_foreground` (DRY refactor)**

Replace the body of `_send_startup_command` (lines 233-249) so the foreground loop lives in a reusable helper. Replace:

```python
def _send_startup_command(hwnd: int, command: str) -> bool:
    """Type command into the terminal ONLY if it is confirmed foreground."""
    for _ in range(FOREGROUND_RETRIES):
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass  # Windows foreground-lock can refuse; retry
        if win32gui.GetForegroundWindow() == hwnd:
            pythoncom.CoInitialize()  # launch_all runs on worker threads
            try:
                shell = win32com.client.Dispatch("WScript.Shell")
                shell.SendKeys(_sendkeys_escape(command) + "{ENTER}")
                return True
            finally:
                pythoncom.CoUninitialize()
        time.sleep(FOREGROUND_RETRY_DELAY)
    return False  # never type into the wrong window
```

with:

```python
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
        shell = win32com.client.Dispatch("WScript.Shell")
        shell.SendKeys(_sendkeys_escape(command) + "{ENTER}")
        return True
    finally:
        pythoncom.CoUninitialize()
```

- [ ] **Step 4: Add `_send_explorer_tabs`**

Immediately after the new `_send_startup_command`, add:

```python
def _send_explorer_tabs(hwnd: int, folders: list) -> int:
    """Open each folder as a new tab via keystrokes, ONLY while hwnd stays
    confirmed foreground. Returns the number of tabs sent; stops at the first
    folder where foreground can't be confirmed (never blind-type).
    # ponytail: focus-stealing SendKeys is the only tab mechanism Windows offers
    """
    sent = 0
    for path in folders:
        if not _confirm_foreground(hwnd):
            break
        pythoncom.CoInitialize()
        try:
            shell = win32com.client.Dispatch("WScript.Shell")
            shell.SendKeys("^t")  # new tab
            time.sleep(EXPLORER_TAB_DELAY)
            shell.SendKeys("^l")  # focus address bar
            time.sleep(EXPLORER_TAB_DELAY)
            shell.SendKeys(_sendkeys_escape(path) + "{ENTER}")
            time.sleep(EXPLORER_TAB_DELAY)
        finally:
            pythoncom.CoUninitialize()
        sent += 1
    return sent
```

- [ ] **Step 5: Add the explorer branch in `_handle_entry`**

In `_handle_entry`, insert the explorer branch after the terminal block (after line 94 `return None`, before the `# Regular apps:` comment at line 96):

```python
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
            notes.append(f"{len(capped) - 1 - sent} tab(s) not added")
        return "; ".join(notes) or None
```

- [ ] **Step 6: Extend `_spawn`**

Replace `_spawn` (lines 111-115):

```python
def _spawn(entry: dict) -> None:
    if entry.get("kind") == "terminal":
        subprocess.Popen(["wt.exe", "-d", entry["workdir"]])
    else:
        subprocess.Popen([entry["path"]] + shlex.split(entry.get("args", "")))
```

with:

```python
def _spawn(entry: dict) -> None:
    if entry.get("kind") == "terminal":
        subprocess.Popen(["wt.exe", "-d", entry["workdir"]])
    elif entry.get("kind") == "explorer":
        subprocess.Popen(["explorer.exe", entry["folders"][0]])
    else:
        subprocess.Popen([entry["path"]] + shlex.split(entry.get("args", "")))
```

- [ ] **Step 7: Run tests**

Run: `python tests/test_explorer.py`
Expected: `ok`

Run: `python -m pytest tests/ -q`
Expected: all pass (confirms the `_send_startup_command` refactor didn't break anything importable).

- [ ] **Step 8: Manual verification (live desktop)**

The tab/position path is Win32 side-effect — verify by hand. Temporarily add a group to `%APPDATA%\AppLauncher\config.json` `entries` (or wait for Task 3's UI), e.g.:

```json
{ "name": "Test", "enabled": true, "kind": "explorer", "monitor": 1,
  "zone": "left-half", "folders": ["C:\\Windows", "C:\\Users", "C:\\Program Files"] }
```

Run: `python main.py`, press the hotkey.
Expected: one Explorer window opens on monitor 1 left-half with three tabs (Windows, Users, Program Files). Pressing the hotkey again does nothing (open-once). Remove the temp entry afterward if you added it by hand.

- [ ] **Step 9: Commit**

```bash
git add launcher.py tests/test_explorer.py
git commit -m "feat: explorer group launch with capped best-effort tabs"
```

---

## Task 3: Settings UI — Explorer kind editor

**Files:**
- Modify: `settings_ui.py` — `_icon_image` (lines 171-196), `kind_seg` (477-481), explorer widgets, `update_kind` (540-545), `save_entry` (547-590), `load_panel` (625-647)

**Interfaces:**
- Consumes: `launcher.parse_folder_lines` (Task 1); existing `add_row`, `body`, `kind_seg`, `filedialog`, `messagebox`.
- Produces: an `Explorer` kind fully editable and saved as `{"kind": "explorer", "folders": [...], "monitor", "zone", ...}`.

- [ ] **Step 1: Explorer icon tile**

In `_icon_image`, replace the `src = (...)` expression (lines 172-177):

```python
    src = (
        shutil.which("wt.exe")
        if entry.get("kind") == "terminal"
        else entry.get("path", "")
    ) or ""
```

with:

```python
    kind = entry.get("kind")
    if kind == "terminal":
        src = shutil.which("wt.exe") or ""
    elif kind == "explorer":
        src = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "explorer.exe")
    else:
        src = entry.get("path", "") or ""
```

- [ ] **Step 2: Add Explorer to the kind selector**

Replace the `kind_seg` construction (lines 477-481):

```python
    kind_seg = ctk.CTkSegmentedButton(
        body, values=["App", "Terminal"], command=lambda _v: update_kind()
    )
    kind_seg.set("App")
    add_row(0, "Kind", kind_seg)
```

with:

```python
    kind_seg = ctk.CTkSegmentedButton(
        body, values=["App", "Terminal", "Explorer"], command=lambda _v: update_kind()
    )
    kind_seg.set("App")
    add_row(0, "Kind", kind_seg)
```

- [ ] **Step 3: Add the folders editor widgets**

After the `terminal_widgets = add_row(...)` block (ends line 501), add:

```python
    folders_box = ctk.CTkTextbox(body, height=90)

    def browse_folder_append():
        p = filedialog.askdirectory(parent=root)
        if p:
            p = p.replace("/", "\\")
            cur = folders_box.get("1.0", "end").strip()
            folders_box.delete("1.0", "end")
            folders_box.insert("1.0", cur + "\n" + p if cur else p)

    explorer_widgets = add_row(
        5,
        "Folders",
        folders_box,
        ctk.CTkButton(body, text="…", width=30, command=browse_folder_append),
    )
```

(Row 5 overlaps the terminal `Workdir` row; that is fine — `update_kind` only ever grids one kind's widgets at a time.)

- [ ] **Step 4: Make `update_kind` three-way**

Replace `update_kind` (lines 540-545):

```python
    def update_kind():
        is_app = kind_seg.get() == "App"
        for w in app_widgets:
            w.grid() if is_app else w.grid_remove()
        for w in terminal_widgets:
            w.grid_remove() if is_app else w.grid()
```

with:

```python
    def update_kind():
        kind = kind_seg.get()
        sets = {"App": app_widgets, "Terminal": terminal_widgets, "Explorer": explorer_widgets}
        for name, widgets in sets.items():
            for w in widgets:
                w.grid() if name == kind else w.grid_remove()
```

- [ ] **Step 5: Handle explorer in `save_entry`**

In `save_entry`, replace the kind + per-kind block (lines 560-577):

```python
        kind = "app" if kind_seg.get() == "App" else "terminal"
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
```

with:

```python
        kind = {"App": "app", "Terminal": "terminal", "Explorer": "explorer"}[kind_seg.get()]
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
        elif kind == "terminal":
            entry["workdir"] = workdir_var.get().strip()
            entry["startup_command"] = cmd_var.get().strip()
            check_path = entry["workdir"]
        else:  # explorer
            folders = launcher.parse_folder_lines(folders_box.get("1.0", "end"))
            if not folders:
                messagebox.showwarning(
                    "App Launcher", "At least one folder is required.", parent=root
                )
                return
            entry["folders"] = folders
            check_path = folders[0]
```

(`launcher` is already imported at the top of `settings_ui.py`.)

- [ ] **Step 6: Populate the editor in `load_panel`**

In `load_panel`, replace the kind + field-loading lines (lines 630-638):

```python
        kind_seg.set("App" if e.get("kind", "app") == "app" else "Terminal")
        name_var.set(e.get("name", ""))
        path_var.set(e.get("path", ""))
        args_var.set(e.get("args", ""))
        match_var.set(e.get("match_process", ""))
        workdir_var.set(e.get("workdir", ""))
        cmd_var.set(e.get("startup_command", ""))
        mon_var.set(str(e.get("monitor", 1)))
        zone_var.set(e.get("zone", "maximized"))
```

with:

```python
        kind_seg.set(
            {"app": "App", "terminal": "Terminal", "explorer": "Explorer"}[
                e.get("kind", "app")
            ]
        )
        name_var.set(e.get("name", ""))
        path_var.set(e.get("path", ""))
        args_var.set(e.get("args", ""))
        match_var.set(e.get("match_process", ""))
        workdir_var.set(e.get("workdir", ""))
        cmd_var.set(e.get("startup_command", ""))
        folders_box.delete("1.0", "end")
        folders_box.insert("1.0", "\n".join(e.get("folders", [])))
        mon_var.set(str(e.get("monitor", 1)))
        zone_var.set(e.get("zone", "maximized"))
```

- [ ] **Step 7: Manual verification (GUI)**

Run: `python main.py`, open Settings from the tray.
Expected checks:
1. `+` tile → panel opens; kind selector shows App / Terminal / Explorer.
2. Pick **Explorer** → Path/Args/Match and Workdir/Startup rows hide; a Folders textbox + `…` button appear.
3. `…` appends a picked folder as a new line.
4. Type/append two or three folders, set a monitor + zone, Save → a tile appears with the Explorer icon.
5. Re-open the tile → the folders textbox is repopulated, kind is Explorer.
6. Click **Open** on the tile (or press the hotkey) → the group opens with tabs in the chosen zone.
7. Saving Explorer with an empty folders box → "At least one folder is required." warning, no save.

- [ ] **Step 8: Commit**

```bash
git add settings_ui.py
git commit -m "feat: Explorer kind editor in settings UI"
```

---

## Self-Review notes

- **Spec coverage:** data model (Task 1 parser + Task 2 branch), launch-once/leave-alone (Task 2 `_launched_explorers`), cap + summary notes (Task 2), best-effort foreground tabs (Task 2 `_confirm_foreground`/`_send_explorer_tabs`), UI third kind + textbox editor + icon (Task 3), `parse_folder_lines` GUI-free + tested (Task 1), `config.py` untouched — all covered.
- **Type consistency:** `parse_folder_lines(str)->list[str]`, `_confirm_foreground(int)->bool`, `_send_explorer_tabs(int, list)->int` used consistently across tasks. `MAX_EXPLORER_FOLDERS`/`EXPLORER_PROCESS`/`EXPLORER_TAB_DELAY` names match every reference.
- **Known limitation (documented, not a gap):** if `explorer.exe <folder0>` reuses an existing window, no new window is detected and tabs aren't added — commented in code, acceptable for the launch-fresh case.
