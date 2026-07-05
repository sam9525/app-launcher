"""Monitor enumeration and zone->rect math. All coordinates are physical pixels."""


def zone_rect(mon: tuple[int, int, int, int], zone: str) -> tuple[int, int, int, int]:
    x, y, w, h = mon
    hw, hh = w // 2, h // 2
    # w - hw / h - hh guarantee halves tile the monitor exactly on odd dimensions
    return {
        "maximized": (x, y, w, h),
        "left-half": (x, y, hw, h),
        "right-half": (x + hw, y, w - hw, h),
        "top-half": (x, y, w, hh),
        "bottom-half": (x, y + hh, w, h - hh),
        "top-left": (x, y, hw, hh),
        "top-right": (x + hw, y, w - hw, hh),
        "bottom-left": (x, y + hh, hw, h - hh),
        "bottom-right": (x + hw, y + hh, w - hw, h - hh),
    }[zone]
