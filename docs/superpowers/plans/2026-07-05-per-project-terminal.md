# Per-Press Terminal Launching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each terminal entry launch its own window instead of hijacking whichever Windows Terminal already exists.

**Architecture:** Split `_handle_entry` on `kind == "terminal"`. Terminals never call `_find_window`; they spawn once per app run, get positioned, then are marked in a module-level set so later hotkey presses skip them. Regular apps keep their existing find-or-launch behavior unchanged.

**Tech Stack:** Python 3, pywin32, pystray. No new dependencies.

## Global Constraints

- Windows-only. `launcher.py` is the only source file touched; no config schema or UI change.
- Follow the existing test style in `tests/test_config.py`: `unittest.mock`, `assert`-based, plus a call added to the `__main__` block.
- The mark set is in-memory only, keyed `(name, workdir)`, cleared on process restart. Not persisted.
- Per project CLAUDE.md: run `gitnexus_impact` before editing `_handle_entry`, and `gitnexus_detect_changes()` before committing.

---

### Task 1: Terminal launches once per run, apps unchanged

**Files:**
- Modify: `launcher.py` — add `_launched_terminals` set + `_terminal_key`, rewrite `_handle_entry` (currently `launcher.py:56-84`)
- Test: `tests/test_config.py` — add `test_terminal_launched_once_then_skipped`, register it in `__main__`

**Interfaces:**
- Consumes (existing, unchanged): `_windows_for(process_name, pid_names) -> list[int]`, `_spawn(entry) -> None`, `_poll_new_window(process_name, before, pid_names) -> int | None`, `_position(hwnd, monitor, zone) -> None`, `_send_startup_command(hwnd, command) -> bool`, `_find_window(process_name, pid_names) -> int | None`, constant `TERMINAL_PROCESS`.
- Produces: `_launched_terminals: set`, `_terminal_key(entry: dict) -> tuple`, and the same `_handle_entry(entry: dict, pid_names: dict) -> str | None` contract (None on success, else a short note).

- [ ] **Step 0: Impact analysis before editing**

Run: `gitnexus_impact({target: "_handle_entry", direction: "upstream"})`
Expected: `launch_all` is the direct caller. Report the blast radius. The index is stale (`npx gitnexus analyze` may be needed first); this is LOW risk — one function, one caller.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py` (after `test_send_startup_command_com_uninit_on_error`):

```python
def test_terminal_launched_once_then_skipped():
    import launcher
    entry = {"name": "Claude", "kind": "terminal", "workdir": "D:\\proj",
             "startup_command": "", "monitor": 1, "zone": "maximized"}
    launcher._launched_terminals.clear()
    with mock.patch("launcher._windows_for", return_value=[]), \
         mock.patch("launcher._spawn") as mock_spawn, \
         mock.patch("launcher._poll_new_window", return_value=999), \
         mock.patch("launcher._position") as mock_position:
        # First press: spawns, positions, marks.
        assert launcher._handle_entry(entry, {}) is None
        assert mock_spawn.call_count == 1
        assert mock_position.call_count == 1
        assert launcher._terminal_key(entry) in launcher._launched_terminals
        # Second press: skipped entirely, no respawn, no reposition.
        assert launcher._handle_entry(entry, {}) is None
        assert mock_spawn.call_count == 1
        assert mock_position.call_count == 1
    launcher._launched_terminals.clear()
```

Register it in the `__main__` block (add the line alongside the other launcher tests):

```python
    test_terminal_launched_once_then_skipped()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_config.py::test_terminal_launched_once_then_skipped -v`
Expected: FAIL with `AttributeError: module 'launcher' has no attribute '_launched_terminals'`.

- [ ] **Step 3: Add the mark set and key helper**

In `launcher.py`, just below the `_run_lock` definition (after `launcher.py:25`), add:

```python
# Terminals are launched once per app run, then left alone. Keyed by
# (name, workdir); cleared only by restarting the launcher.
# ponytail: in-memory set, no persistence — a fresh run reopens terminals
_launched_terminals: set = set()


def _terminal_key(entry: dict) -> tuple:
    return (entry.get("name"), entry.get("workdir"))
```

- [ ] **Step 4: Rewrite `_handle_entry`**

Replace the whole current `_handle_entry` (`launcher.py:56-84`) with:

```python
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

    # Regular apps: find-or-launch by process basename, reposition every press.
    proc_name = entry["match_process"]
    hwnd = _find_window(proc_name, pid_names)
    if hwnd:
        _position(hwnd, monitor, zone)
        return None
    before = set(_windows_for(proc_name, pid_names))
    _spawn(entry)
    hwnd = _poll_new_window(proc_name, before, pid_names)
    if hwnd is None:
        return "unpositioned (no window within 15 s)"
    _position(hwnd, monitor, zone)
    return None
```

- [ ] **Step 5: Run the new test to verify it passes**

Run: `python -m pytest tests/test_config.py::test_terminal_launched_once_then_skipped -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite for regressions**

Run: `python -m pytest tests/ -v`
Expected: all pass (existing launcher/config/tray/settings tests + the new one).

- [ ] **Step 7: Refresh GitNexus and verify change scope**

Run: `npx gitnexus analyze` then `gitnexus_detect_changes()`
Expected: changes confined to `_handle_entry` (+ new `_launched_terminals`, `_terminal_key`) in `launcher.py`. No unexpected symbols or flows affected.

- [ ] **Step 8: Commit**

```bash
git add launcher.py tests/test_config.py
git commit -m "fix: launch a fresh terminal per project instead of reusing the existing one"
```
