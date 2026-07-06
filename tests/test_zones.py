import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from monitors import inflate_for_border, zone_rect

# Odd width/height so the w - hw / h - hh forms are exercised.
ODD = (0, 0, 2561, 1441)
# Non-origin rect: negative/offset virtual-desktop coords.
OFFSET = (2560, -120, 1920, 1200)

ALL_ZONES = [
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


def test_odd_monitor_all_zones():
    # hw = 1280, hh = 720; w - hw = 1281, h - hh = 721
    assert zone_rect(ODD, "maximized") == (0, 0, 2561, 1441)
    assert zone_rect(ODD, "left-half") == (0, 0, 1280, 1441)
    assert zone_rect(ODD, "right-half") == (1280, 0, 1281, 1441)
    assert zone_rect(ODD, "top-half") == (0, 0, 2561, 720)
    assert zone_rect(ODD, "bottom-half") == (0, 720, 2561, 721)
    assert zone_rect(ODD, "top-left") == (0, 0, 1280, 720)
    assert zone_rect(ODD, "top-right") == (1280, 0, 1281, 720)
    assert zone_rect(ODD, "bottom-left") == (0, 720, 1280, 721)
    assert zone_rect(ODD, "bottom-right") == (1280, 720, 1281, 721)


def test_offset_monitor_all_zones():
    # hw = 960, hh = 600
    assert zone_rect(OFFSET, "maximized") == (2560, -120, 1920, 1200)
    assert zone_rect(OFFSET, "left-half") == (2560, -120, 960, 1200)
    assert zone_rect(OFFSET, "right-half") == (3520, -120, 960, 1200)
    assert zone_rect(OFFSET, "top-half") == (2560, -120, 1920, 600)
    assert zone_rect(OFFSET, "bottom-half") == (2560, 480, 1920, 600)
    assert zone_rect(OFFSET, "top-left") == (2560, -120, 960, 600)
    assert zone_rect(OFFSET, "top-right") == (3520, -120, 960, 600)
    assert zone_rect(OFFSET, "bottom-left") == (2560, 480, 960, 600)
    assert zone_rect(OFFSET, "bottom-right") == (3520, 480, 960, 600)


def test_halves_tile_exactly():
    for mon in (ODD, OFFSET):
        x, y, w, h = mon
        lx, ly, lw, lh = zone_rect(mon, "left-half")
        rx, ry, rw, rh = zone_rect(mon, "right-half")
        assert lx + lw == rx and lw + rw == w and lh == rh == h and ly == ry == y
        tx, ty, tw, th = zone_rect(mon, "top-half")
        bx, by, bw, bh = zone_rect(mon, "bottom-half")
        assert ty + th == by and th + bh == h and tw == bw == w and tx == bx == x


def test_inflate_for_border():
    # Zero margins is a no-op.
    assert inflate_for_border((0, 0, 1280, 1440), (0, 0, 0, 0)) == (0, 0, 1280, 1440)
    # 7px shadow on left/right/bottom, 0 on top (typical DWM border).
    assert inflate_for_border((0, 0, 1280, 1440), (7, 0, 7, 7)) == (-7, 0, 1294, 1447)
    # Offset (virtual-desktop) rect inflates the same way.
    assert inflate_for_border((2560, -120, 960, 1200), (7, 0, 7, 7)) == (
        2553,
        -120,
        974,
        1207,
    )


if __name__ == "__main__":
    test_odd_monitor_all_zones()
    test_offset_monitor_all_zones()
    test_halves_tile_exactly()
    test_inflate_for_border()
    print("test_zones OK")
