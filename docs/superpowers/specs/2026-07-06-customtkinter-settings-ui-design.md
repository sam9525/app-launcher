# Design: CustomTkinter restyle of `settings_ui.py`

**Date:** 2026-07-06
**Scope:** `settings_ui.py` only. Behavior-preserving visual modernization.
**Goal:** Replace the dated `ttk`/`tk` widgets with CustomTkinter for a modern
rounded look, without changing what the Settings window does.

## Motivation

The current UI works but looks like old Windows: square `ttk` buttons,
dropdowns, spinboxes, and radio buttons. Plain `tkinter` can't produce rounded
modern widgets without heavy Canvas hacking, so CustomTkinter is the right tool.
A secondary win: `cfg["theme"]` is already exactly `"system" | "light" | "dark"`,
which maps 1:1 onto CTk's `set_appearance_mode(...)`, letting us delete the
entire manual theming layer.

## Non-goals

- No behavior changes: same grid, same slide-in edit panel, same field toggle,
  same Save/Disable/Remove, same threading model.
- No redesign of the signature UI (icon grid, sliding panel) — restyle only.
- No changes to `config.py`, `launcher.py`, `monitors.py`, `app_index.py`, or
  `tray.py`.

## Behavior that must stay identical

- Icon-tile grid; click a tile to edit; plus-tile to add a new entry.
- Left slide-in edit panel with the existing `place()` animation.
- App/Terminal kind switch that shows/hides the relevant fields.
- Save / Disable / Remove actions and their validation (name required,
  path-exists confirm dialog).
- Find (resolve by name) and browse (`…`) buttons.
- Theme selector: System / Light / Dark.
- Launch Now.
- Re-opening Settings lifts the existing window (`<<Lift>>` event).
- Dedicated UI thread; `config.save()` is the only cross-thread contact.
- Win32 icon extraction, letter-tile fallback, dimmed icons for disabled entries.

## Changes

### Dependency

- Add `customtkinter` to `requirements.txt`.
- `pip install -r requirements.txt`.
- Target Python 3.11.9 (confirmed local).

### Root & theming (net deletion)

- `tk.Tk()` → `ctk.CTk()`.
- Call `ctk.set_appearance_mode(cfg["theme"])` at startup (`"system"` follows
  Windows automatically — replaces `config.resolve_theme` usage inside the UI;
  `resolve_theme` itself stays in `config.py`, untouched, for any other caller).
- **Delete `_palette()`** and every `style.configure(...)` / `style.map(...)`
  line — CTk widgets self-theme by appearance mode.
- **Delete the theme-change rebuild.** Today `on_theme_change` destroys and
  rebuilds the whole widget tree via `build_ui()`. With CTk it becomes:
  `ctk.set_appearance_mode(new_mode)` + `config.save(cfg)`. Widgets recolor live.
  The `build_ui()` rebuild wrapper is removed; UI is built once.
- Functions that currently thread a `pal` dict argument
  (`_make_block`, `_make_plus_tile`) drop that parameter.

### Widget swaps (1:1, same layout and grid positions)

| Current | Becomes |
|---|---|
| `ttk.Button` | `CTkButton` |
| `ttk.Entry` | `CTkEntry` |
| `ttk.Combobox` (Zone, Theme) | `CTkOptionMenu` |
| `ttk.Spinbox` (Monitor) | `CTkOptionMenu`, values `"1".."9"` |
| `ttk.Radiobutton` App/Terminal | `CTkSegmentedButton` (values `["App", "Terminal"]`) |
| `tk.Frame` tile (`_make_block`) | `CTkFrame(corner_radius, border_width=1)`; hover swaps `border_color` |
| icon `tk.Label` image | `CTkLabel` with `ctk.CTkImage` (HiDPI-correct) |

Notes:
- `CTkSegmentedButton` uses display labels `"App"`/`"Terminal"`; map to the
  stored `kind` values `"app"`/`"terminal"` at read/write. Its `command`
  callback drives the existing `update_kind()`.
- Monitor `CTkOptionMenu` keeps the current clamp logic (`max(1, int(...))`);
  values are strings `"1"`–`"9"`.
- Icon images move from `ImageTk.PhotoImage` to `ctk.CTkImage`
  (`light_image`/`dark_image` can be the same PIL image; size = `_ICON_SIZE`).
  The existing `_photo_cache` keying stays; type changes to `CTkImage`.

### Scroll region

Replace the hand-built `Canvas + ttk.Scrollbar + inner frame + create_window +
scrollregion bind + _on_mousewheel + _on_canvas_leave + bind_all` machinery with
a single **`CTkScrollableFrame`** (built-in mousewheel + scroll region).

- Column reflow on resize is preserved: bind `<Configure>` on the scrollable
  frame and recompute `cols = max(1, width // (_BLOCK + 2*_PAD))`, calling
  `refresh()` when the column count changes (same logic as `on_canvas_resize`).
- **This is the one place with mild behavior risk:** mousewheel is now CTk's
  built-in handling rather than the manual `bind_all`. User-visible scrolling is
  the same; verify during manual testing.

### Plus tile

`_make_plus_tile` Canvas dashed-square becomes a `CTkFrame` with matching rounded
corners and a large "+" `CTkLabel`, clickable. Minor accepted visual change: the
dashed outline is dropped in favor of a solid rounded border consistent with the
restyled tiles.

### Kept as-is

- `filedialog`, `messagebox` — CTk has no replacement; OS dialogs are fine.
- Win32 icon extraction (`_extract_exe_icon`), `_letter_tile` (hash colors are
  theme-independent), dimmed-icon grayscale conversion.
- The `place()`-based slide animation on the edit panel (`CTkFrame` supports
  `place`/`place_configure`).
- Dedicated-thread lifecycle (`open_settings`, `_run`, `<<Lift>>`).

## Net effect

Modern rounded look **and** a shorter file: the manual palette, the `ttk.Style`
block, the theme-rebuild wrapper, and the Canvas scroll machinery all disappear.

## Verification

`settings_ui.py` has no unit tests today and none are added — it is a
Win32 + GUI module running on a dedicated thread, not meaningfully unit-testable
without a display. Verification is manual:

1. `py main.py` → open Settings.
2. Confirm: tile grid renders and reflows on resize; clicking a tile slides the
   edit panel in; plus-tile opens a blank panel.
3. App ↔ Terminal segmented button toggles the correct field set.
4. Save / Disable / Remove behave as before, including name-required and
   path-missing confirmation dialogs.
5. Find and `…` browse populate the path/workdir fields.
6. Theme selector switches System / Light / Dark live (no window rebuild flash).
7. Launch Now triggers `launcher.launch_all`.
8. Re-open Settings while open → existing window lifts.

Pure-logic tests are untouched and must still pass:
`py -m pytest tests/` (or `py tests/test_zones.py`, `py tests/test_config.py`).
