"""Monitor-map preview: which monitor+zone an entry targets, drawn as small
squares. Pure geometry (layout_monitors, pick_zone) is testable without a GUI;
build_map draws it on a tkinter.Canvas. All coordinates are physical pixels."""

import tkinter as tk

import config
import monitors

# The 9 spatial zones are every zone except the trailing non-spatial "open-only".
_SPATIAL_ZONES = config.ZONES[:-1]


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


def build_map(
    parent, mons, monitor_index, zone, width, height, accent, bg, on_pick=None
):
    """Canvas of one square per monitor, target zone filled in accent. If
    on_pick is given, a click calls on_pick(monitor_1based, zone)."""
    canvas = tk.Canvas(
        parent, width=width, height=height, highlightthickness=0, bd=0, bg=bg
    )
    rects = layout_monitors(mons, width - 2, height - 2, gap=3)
    # Mirror launcher's clamp: an out-of-range monitor index positions on the
    # primary monitor (launcher.py), so highlight monitor 1 in that case.
    target = monitor_index if 1 <= monitor_index <= len(mons) else 1
    outline = "#888888"
    for i, (x, y, w, h) in enumerate(rects):
        x0, y0 = x + 1, y + 1
        is_target = (i + 1 == target) and (zone in _SPATIAL_ZONES)
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
