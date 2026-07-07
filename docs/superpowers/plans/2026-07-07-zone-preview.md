# Zone Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show each app's target monitor+zone as a small clickable monitor-map on the settings tiles and detail panel, and make the Monitor dropdown list only real connected monitors.

**Architecture:** A new `zone_preview.py` holds pure layout/hit-test geometry (`layout_monitors`, `pick_zone`) plus a thin `tkinter.Canvas` builder (`build_map`). `settings_ui.py` calls `build_map` in two places: display-only under each tile's switch, and clickable under the detail panel's Zone dropdown. Geometry reuses `monitors.zone_rect`; no config schema change.

**Tech Stack:** Python, `tkinter.Canvas`, `customtkinter`, `pywin32` (via existing `monitors`).

## Global Constraints

- Windows-only; all coordinates are physical pixels.
- Flat module layout, one responsibility per file (no packages).
- Tests are plain-Python, assert-based, runnable via `python tests/<file>.py` with an `__main__` block printing `<name> OK` — no pytest fixtures, no Win32, no Canvas/root.
- No config schema change — `entry["monitor"]` (1-based, over `monitors.get_monitors()` order) and `entry["zone"]` already exist.
- Zones are the 10 in `config.ZONES`; the 9 spatial ones are everything except `open-only`.
- Follow existing style; match `monitors.py` (pure geometry) and `test_zones.py` (test shape).
- Per project CLAUDE.md: run `gitnexus_impact({target, direction:"upstream"})` before editing a symbol, and `gitnexus_detect_changes()` before committing.

---

### Task 1: `zone_preview.py` — geometry + map builder

**Files:**
- Create: `zone_preview.py`
- Test: `tests/test_zone_preview.py`

**Interfaces:**
- Consumes: `monitors.zone_rect(rect, zone) -> (x, y, w, h)` from `monitors.py`.
- Produces:
  - `layout_monitors(mons, max_w, max_h, gap=3) -> list[(x, y, w, h)]` — pure; `mons` is a list of `(x, y, w, h)`; returns float pixel rects in monitor order.
  - `pick_zone(mon_px_rect, x, y) -> str` — pure; returns one of the 9 spatial zone names.
  - `build_map(parent, mons, monitor_index, zone, width, height, accent, bg, on_pick=None) -> tkinter.Canvas` — draws the map; `monitor_index` is 1-based; `on_pick(monitor_1based, zone)` fires on click when provided.

- [ ] **Step 1: Write the failing test**

Create `tests/test_zone_preview.py`:

```python
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from zone_preview import layout_monitors, pick_zone

MON_16_9 = (0, 0, 1920, 1080)
SQUARE = (0, 0, 100, 100)  # even dims so zone centers are exact


def _approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


def test_layout_single_monitor_fits_and_keeps_aspect():
    rects = layout_monitors([MON_16_9], 90, 28, gap=3)
    assert len(rects) == 1
    x, y, w, h = rects[0]
    assert x >= -1e-6 and y >= -1e-6
    assert x + w <= 90 + 1e-6 and y + h <= 28 + 1e-6
    assert _approx(w / h, 1920 / 1080, tol=1e-3)


def test_layout_two_monitors_ordered_non_overlapping_in_box():
    rects = layout_monitors([MON_16_9, MON_16_9], 90, 28, gap=3)
    assert len(rects) == 2
    (x0, _y0, w0, _h0), (x1, _y1, _w1, _h1) = rects
    assert x1 >= x0 + w0 - 1e-6  # second starts at/after first ends
    for x, y, w, h in rects:
        assert x >= -1e-6 and x + w <= 90 + 1e-6
        assert y >= -1e-6 and y + h <= 28 + 1e-6


def test_pick_zone_center_edges_corners():
    assert pick_zone(SQUARE, 50, 50) == "maximized"
    assert pick_zone(SQUARE, 5, 5) == "top-left"
    assert pick_zone(SQUARE, 95, 5) == "top-right"
    assert pick_zone(SQUARE, 5, 95) == "bottom-left"
    assert pick_zone(SQUARE, 95, 95) == "bottom-right"
    assert pick_zone(SQUARE, 2, 50) == "left-half"
    assert pick_zone(SQUARE, 98, 50) == "right-half"
    assert pick_zone(SQUARE, 50, 2) == "top-half"
    assert pick_zone(SQUARE, 50, 98) == "bottom-half"


if __name__ == "__main__":
    test_layout_single_monitor_fits_and_keeps_aspect()
    test_layout_two_monitors_ordered_non_overlapping_in_box()
    test_pick_zone_center_edges_corners()
    print("test_zone_preview OK")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python tests/test_zone_preview.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'zone_preview'`.

- [ ] **Step 3: Write `zone_preview.py`**

Create `zone_preview.py`:

```python
"""Monitor-map preview: which monitor+zone an entry targets, drawn as small
squares. Pure geometry (layout_monitors, pick_zone) is testable without a GUI;
build_map draws it on a tkinter.Canvas. All coordinates are physical pixels."""

import tkinter as tk

import monitors

_SPATIAL_ZONES = [
    "maximized",
    "left-half",
    "right-half",
    "top-half",
    "bottom-half",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
]


def layout_monitors(mons, max_w, max_h, gap=3):
    """Lay monitors left-to-right at a shared height, aspect-preserved, scaled
    to fit a max_w x max_h box. Returns pixel rects in monitor order."""
    if not mons:
        return []
    h = float(max_h)
    widths = [(w / mon_h) * h for (_x, _y, w, mon_h) in mons]
    total = sum(widths) + gap * (len(mons) - 1)
    s = min(1.0, max_w / total) if total > 0 else 1.0
    h *= s
    widths = [w * s for w in widths]
    g = gap * s
    top = (max_h - h) / 2
    rects = []
    cx = 0.0
    for w in widths:
        rects.append((cx, top, w, h))
        cx += w + g
    return rects


def pick_zone(mon_px_rect, x, y):
    """Spatial zone whose zone-rect center is nearest (x, y): center ->
    maximized, edge -> a half, corner -> a quarter."""
    best, best_d = "maximized", None
    for z in _SPATIAL_ZONES:
        rx, ry, rw, rh = monitors.zone_rect(mon_px_rect, z)
        cx, cy = rx + rw / 2, ry + rh / 2
        d = (cx - x) ** 2 + (cy - y) ** 2
        if best_d is None or d < best_d:
            best, best_d = z, d
    return best


def build_map(parent, mons, monitor_index, zone, width, height, accent, bg,
              on_pick=None):
    """Canvas of one square per monitor, target zone filled in accent. If
    on_pick is given, a click calls on_pick(monitor_1based, zone)."""
    canvas = tk.Canvas(
        parent, width=width, height=height, highlightthickness=0, bd=0, bg=bg
    )
    rects = layout_monitors(mons, width - 2, height - 2, gap=3)
    outline = "#888888"
    for i, (x, y, w, h) in enumerate(rects):
        x0, y0 = x + 1, y + 1
        is_target = (i + 1 == monitor_index) and (zone in _SPATIAL_ZONES)
        canvas.create_rectangle(x0, y0, x0 + w, y0 + h, outline=outline, width=1)
        if is_target:
            zx, zy, zw, zh = monitors.zone_rect((x0, y0, w, h), zone)
            canvas.create_rectangle(
                zx, zy, zx + zw, zy + zh, fill=accent, outline=accent
            )
        canvas.create_text(
            x0 + w / 2,
            y0 + h / 2,
            text=str(i + 1),
            fill="white" if is_target else outline,
        )

    if on_pick is not None:
        canvas.configure(cursor="hand2")

        def click(e):
            for i, (x, y, w, h) in enumerate(rects):
                x0, y0 = x + 1, y + 1
                if x0 <= e.x <= x0 + w and y0 <= e.y <= y0 + h:
                    on_pick(i + 1, pick_zone((x0, y0, w, h), e.x, e.y))
                    return

        canvas.bind("<Button-1>", click)
    return canvas
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python tests/test_zone_preview.py`
Expected: `test_zone_preview OK`.

- [ ] **Step 5: Run the full suite to confirm nothing regressed**

Run: `python -m pytest tests/`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add zone_preview.py tests/test_zone_preview.py
git commit -m "feat: zone_preview monitor-map geometry and canvas builder"
```

---

### Task 2: Wire the map into `settings_ui.py`

**Files:**
- Modify: `settings_ui.py`

**Interfaces:**
- Consumes: `zone_preview.build_map(...)`, `zone_preview` module (Task 1); existing `monitors.get_monitors()`.
- Produces: no new external interface; UI behavior only.

Before editing, per project CLAUDE.md run impact analysis on the symbols being changed:

```
gitnexus_impact({target: "_make_block", direction: "upstream"})
gitnexus_impact({target: "_run", direction: "upstream"})
```

Report the blast radius; both are UI-internal so risk is expected LOW. This task has no unit test (GUI wiring); it is verified by running the app.

- [ ] **Step 1: Import the module and add the color-resolve helper**

In `settings_ui.py`, add `import zone_preview` alongside the other local imports (`import app_index` … `import monitors`).

After the `_TILE_BORDER` constant (near line 40), add:

```python
def _resolve(pair):
    """Pick the light or dark member of a CTk [light, dark] color pair for the
    current appearance mode — tk.Canvas needs a concrete bg color."""
    return pair[0] if ctk.get_appearance_mode() == "Light" else pair[1]
```

- [ ] **Step 2: Add the display-only map to `_make_block`**

Change the signature of `_make_block` (currently `def _make_block(parent, entry, command, on_toggle, on_open) -> ctk.CTkFrame:`) to accept the monitor list and accent:

```python
def _make_block(parent, entry, command, on_toggle, on_open, mons, accent) -> ctk.CTkFrame:
```

Inside `_make_block`, between the switch pack (`sw.pack(pady=(6, 2))`) and the Open button line, insert the map:

```python
    sw.pack(pady=(6, 2))
    zone_preview.build_map(
        wrap,
        mons,
        entry.get("monitor", 1),
        entry.get("zone", "maximized"),
        width=_BLOCK,
        height=30,
        accent=accent,
        bg=_resolve(ctk.ThemeManager.theme["CTk"]["fg_color"]),
    ).pack(pady=(4, 2))
    ctk.CTkButton(wrap, text="Open", width=_BLOCK, height=24, command=on_open).pack()
```

(The existing `ctk.CTkButton(wrap, text="Open", ...)` line stays; the map goes just before it.)

- [ ] **Step 3: Enumerate monitors once in `_run` and fix the Monitor dropdown**

In `_run`, after `cfg.setdefault("theme", "system")` (near line 272), add:

```python
    mons = monitors.get_monitors()
```

Replace the existing monitor-count / values lines (currently):

```python
    monitor_count = max(1, len(monitors.get_monitors()))
    mon_values = [str(i) for i in range(1, max(monitor_count, 9) + 1)]
```

with:

```python
    monitor_count = max(1, len(mons))
    mon_values = [str(i) for i in range(1, monitor_count + 1)]
```

- [ ] **Step 4: Pass `mons`/accent through the `refresh()` call**

In `refresh()`, update the `_make_block(...)` call to pass the two new args:

```python
            block = _make_block(
                grid,
                entry,
                lambda i=i: load_panel(i),
                lambda i=i: toggle_at(i),
                lambda e=entry: open_one(e),
                mons,
                _ACCENT,
            )
```

- [ ] **Step 5: Give the Monitor/Zone option menus names**

Replace the two `add_row` calls that build the Monitor and Zone menus (currently lines ~481-488):

```python
    add_row(
        7,
        "Monitor",
        ctk.CTkOptionMenu(body, values=mon_values, variable=mon_var, width=70),
    )
    add_row(
        8, "Zone", ctk.CTkOptionMenu(body, values=list(config.ZONES), variable=zone_var)
    )
```

with named widgets so their `command` can be wired after `redraw_map` exists:

```python
    mon_menu = ctk.CTkOptionMenu(body, values=mon_values, variable=mon_var, width=70)
    add_row(7, "Monitor", mon_menu)
    zone_menu = ctk.CTkOptionMenu(body, values=list(config.ZONES), variable=zone_var)
    add_row(8, "Zone", zone_menu)
```

- [ ] **Step 6: Add the clickable panel map holder, redraw + pick callbacks, and wire the menus**

Immediately after the `add_row(8, "Zone", zone_menu)` block from Step 5 (before the `update_kind` definition), insert:

```python
    map_holder = ctk.CTkFrame(body, fg_color="transparent")
    map_holder.grid(row=9, column=0, columnspan=3, sticky="we", pady=(8, 0))

    def redraw_map():
        for w in map_holder.winfo_children():
            w.destroy()
        try:
            mon = max(1, int(mon_var.get()))
        except ValueError:
            mon = 1
        zone_preview.build_map(
            map_holder,
            mons,
            mon,
            zone_var.get(),
            width=_PANEL_W - 40,
            height=72,
            accent=_ACCENT,
            bg=_resolve(ctk.ThemeManager.theme["CTkFrame"]["fg_color"]),
            on_pick=on_pick_zone,
        ).pack()

    def on_pick_zone(mon, zone):
        mon_var.set(str(mon))
        zone_var.set(zone)
        redraw_map()

    mon_menu.configure(command=lambda _v: redraw_map())
    zone_menu.configure(command=lambda _v: redraw_map())
```

- [ ] **Step 7: Move the buttons row down and redraw the map on panel load**

The buttons frame currently grids at row 9 (`btns.grid(row=9, column=0, columnspan=3, sticky="we", pady=(12, 0))`). Change it to row 10:

```python
    btns.grid(row=10, column=0, columnspan=3, sticky="we", pady=(12, 0))
```

In `load_panel`, after `zone_var.set(e.get("zone", "maximized"))` and before `open_panel()`, add a redraw so the map reflects the loaded entry:

```python
        update_kind()
        redraw_map()
```

(There is an existing `update_kind()` call near the end of `load_panel`; add `redraw_map()` right after it.)

- [ ] **Step 8: Refresh tiles on theme toggle so map backgrounds stay correct**

In `on_theme_toggle`, after `ctk.set_appearance_mode(cfg["theme"])`, add `refresh()` so the tile canvases are rebuilt with the new appearance-mode background:

```python
    def on_theme_toggle():
        cfg["theme"] = theme_var.get()
        config.save(cfg)
        ctk.set_appearance_mode(cfg["theme"])
        refresh()
```

- [ ] **Step 9: Verify the full suite still passes**

Run: `python -m pytest tests/`
Expected: all tests pass (no settings_ui tests exist; this confirms Task 1 and existing tests are green).

- [ ] **Step 10: Manual verification — run the app**

Run: `python main.py`, then open Settings from the tray icon.
Confirm:
- Each tile shows small monitor square(s) under the switch; the target zone is filled in the accent color; multi-monitor systems show one square per monitor numbered to match.
- Opening an entry shows a larger map under the Zone dropdown.
- Clicking a corner/edge/center of a monitor square in the panel updates the Monitor + Zone dropdowns and the highlight; changing the Monitor or Zone dropdown updates the map live.
- The Monitor dropdown lists exactly the connected monitors (e.g. `1` and `2` on a dual-monitor setup, not up to `9`).
- Saving persists the picked monitor/zone (reopen the entry to confirm).

- [ ] **Step 11: Verify change scope, then commit**

Run: `gitnexus_detect_changes()` and confirm only `settings_ui.py` symbols are affected.

```bash
git add settings_ui.py
git commit -m "feat: show target monitor+zone map on tiles and clickable in detail panel"
```

- [ ] **Step 12: Reindex GitNexus**

Run: `npx gitnexus analyze`
```

## Self-Review

**Spec coverage:**
- Tile display-only map → Task 2 Step 2. ✓
- Panel clickable map under Zone → Task 2 Steps 6-7. ✓
- Live update on Monitor/Zone change → Task 2 Step 6 (`command=redraw_map`). ✓
- Monitor dropdown = real monitors → Task 2 Step 3. ✓
- `layout_monitors` / `pick_zone` / `build_map` per spec → Task 1. ✓
- `open-only` / non-spatial = outline only → `build_map` `is_target` guard. ✓
- No config schema change → confirmed; only `entry` reads. ✓
- Tests for layout + pick_zone → Task 1 Step 1. ✓
- Build order (geometry first) → Task 1 before Task 2. ✓

**Placeholder scan:** none — every code step shows full code.

**Type consistency:** `build_map(parent, mons, monitor_index, zone, width, height, accent, bg, on_pick=None)` — the `bg` keyword and 1-based `monitor_index` match every call site (tile Step 2, panel Step 6). `layout_monitors`/`pick_zone` signatures match their test and `build_map` usage. `redraw_map`/`on_pick_zone` referenced only after both are defined in the same scope (Step 6).
