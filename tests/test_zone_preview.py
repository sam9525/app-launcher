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
