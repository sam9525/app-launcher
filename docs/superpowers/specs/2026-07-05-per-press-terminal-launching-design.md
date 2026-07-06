# Per-Press Terminal Launching — Design

**Date:** 2026-07-05
**Status:** Approved, pending implementation

## Problem

Terminal entries for different projects cannot be distinguished. Pressing the
hotkey to open a second project's terminal repositions the first project's
existing terminal instead of launching a new one.

## Root Cause

`_handle_entry` (`launcher.py:58-59`) matches every terminal on the shared
process name `windowsterminal.exe`. `_find_window` therefore returns whichever
Windows Terminal window already exists and repositions it; a second terminal
never spawns because the "find" step always succeeds first. All terminals look
identical to the matcher since they share one broker process.

## Behavior

Split on `kind == "terminal"`:

- **Regular apps** (`kind != "terminal"`): unchanged. Find-or-launch by process
  basename, reposition on every press. Stays detectable.
- **Terminals**: never call `_find_window`.
  1. **First press** for that entry → spawn a fresh terminal (existing pre-spawn
     snapshot + `_poll_new_window` logic), position it, send `startup_command`,
     then mark it launched.
  2. **Later presses** → the mark is set, so the entry is skipped entirely: no
     respawn, no reposition.

## The Mark

- Module-level `_launched_terminals: set` in `launcher.py`.
- Key: `(name, workdir)` per entry.
- Scope: process lifetime. A fresh launcher run starts empty. Not persisted to
  disk.

### Accepted Tradeoff (Option 1)

Closing a marked terminal does **not** let the hotkey reopen it — the user opens
it manually. Restarting the launcher clears all marks. Editing a terminal's
`workdir` in Settings changes its key, so it counts as new and will relaunch.

## Reporting

A skipped (already-launched) terminal returns `None` from `_handle_entry` —
counts as success in the `Launched X/Y` summary, no extra noise.

## Scope

- **Files touched:** `launcher.py` only.
  - `_handle_entry`: early skip-check for marked terminals; terminal branch stops
    calling `_find_window` and always spawns.
  - New module-level `_launched_terminals` set + `(name, workdir)` key helper.
- No config schema change. No UI change.

## Test

A small `assert`-based check in `tests/` verifying the same terminal entry is
spawned once and skipped on a second call, with the Win32 spawn/poll stubbed out.
