# Zone Preview Design

## Goal

Show, on each app tile and in the detail panel, exactly where an app will be
placed: a mini monitor-map with one square per physical monitor and the app's
target zone highlighted. In the detail panel the map is clickable to set the
zone. The Monitor dropdown lists only real connected monitors, numbered to
match.

## Behavior

- **Tiles (main grid):** display-only map under the enable switch, above the
  Open button.
- **Detail panel:** the same map under the Zone dropdown, **clickable** —
  clicking a region sets monitor + zone on the pending edit. The map redraws
  live when the Monitor or Zone dropdown changes. Nothing saves until Save
  (consistent with the existing "edit then Save" panel model).
- **Monitor dropdown:** lists exactly the connected monitors (drop the current
  pad-to-9). Numbering is 1-based over `monitors.get_monitors()` order (primary
  first), so it matches the map labels and existing `entry["monitor"]`
  semantics.

## New file: `zone_preview.py`

One responsibility: render a monitor-map and turn clicks into a zone pick.
Geometry is pure and testable (mirrors how `monitors.py` is structured).

### `layout_monitors(mons, max_w, max_h, gap=3) -> list[(x, y, w, h)]` — pure

- Input `mons` is the `monitors.get_monitors()` list of `(x, y, w, h)`.
- Lay monitors left-to-right at a shared target height, each aspect-preserved
  (width = mon_w / mon_h * height), separated by `gap` px.
- If total width exceeds `max_w` (or height exceeds `max_h`), scale the whole
  row down uniformly to fit.
- Return pixel rects in monitor order, so index i corresponds to monitor i+1.

### `pick_zone(mon_px_rect, x, y) -> str` — pure

- Given a monitor's drawn pixel rect and a click point inside it, return the
  zone whose zone-rect center is nearest the click.
- Candidates: the 9 spatial zones (`maximized`, halves, quarters). Zone rects
  come from `monitors.zone_rect(mon_px_rect, zone)`; center → `maximized`,
  edge → a half, corner → a quarter.
- `open-only` is not spatial and is not returned here; it is selectable only via
  the Zone dropdown.

### `build_map(parent, mons, monitor_index, zone, width, height, accent, on_pick=None) -> Canvas`

- Draws each monitor as a rectangle via `layout_monitors`, labeled with its
  1-based number.
- Fills the target zone of the target monitor (`monitor_index`, 1-based) in
  `accent`. For `zone == "open-only"` (or any non-spatial zone) draw the target
  monitor outline only, no fill.
- Highlight rect comes from `monitors.zone_rect(target_px_rect, zone)`.
- If `on_pick` is given, bind `<Button-1>`: find which monitor rect contains the
  click, resolve the zone via `pick_zone`, and call
  `on_pick(monitor_1based, zone)`. Clicks outside any monitor rect are ignored.

## `settings_ui.py` changes (surgical)

1. `_run()`: enumerate monitors once (`mons = monitors.get_monitors()`); pass
   `mons` and `_ACCENT` down to tile and panel map builders.
2. `_make_block(...)`: insert a display-only `build_map` (no `on_pick`) between
   the switch and the Open button. Reads `entry["monitor"]` / `entry["zone"]`.
3. Detail panel:
   - Add a clickable `build_map` row under Zone. `on_pick(mon, zone)` sets
     `mon_var`/`zone_var` and redraws the map.
   - Wire the Monitor and Zone `CTkOptionMenu` `command=` to redraw the map.
   - `load_panel` draws/redraws the map for the loaded entry.
   - The buttons row (`btns`) shifts down one grid row to make room.
4. `mon_values = [str(i) for i in range(1, monitor_count + 1)]` — drop
   `max(monitor_count, 9)` padding.

## Data / config

No config schema change. `monitor` and `zone` already exist per entry. The
panel map only updates the pending edit's vars; save flows through the existing
`save_entry`.

## UI note

Each tile block grows ~28px taller to fit the map. Accepted.

## Tests

`tests/test_zone_preview.py` — assert-based `__main__`, no Win32/Canvas:

- `layout_monitors`: 1 monitor → 1 rect; 2 monitors → 2 non-overlapping rects
  ordered left-to-right; oversized input scaled to fit `max_w`/`max_h`;
  aspect ratio preserved.
- `pick_zone`: center → `maximized`; each corner → its quarter; each edge
  midpoint → its half.

## Build order

`zone_preview.py` (pure geometry + tests) → wire into `settings_ui.py`.
