"""Daily check of GitHub's latest release; standard library only."""

import json
import math
import os
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

from version import VERSION

LATEST_URL = "https://api.github.com/repos/sam9525/app-launcher/releases/latest"
RELEASES_PREFIX = "https://github.com/sam9525/app-launcher/releases/"
CHECK_INTERVAL = 24 * 60 * 60
# At login the network is often not up yet; a check now would burn the day's attempt.
STARTUP_DELAY = 90
STAMP_PATH = Path(os.environ["APPDATA"]) / "AppLauncher" / "update-check.json"

_EMPTY_STAMP = {"checked_at": 0.0, "latest_tag": None, "latest_url": None}


def parse_version(tag: str) -> tuple[int, ...] | None:
    parts = tag.removeprefix("v").removeprefix("V").split(".")
    # int() alone would accept " 1", "+1", "-1" and "1_0".
    if not all(p.isascii() and p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def is_newer(tag: str, current: str = VERSION) -> bool:
    latest, installed = parse_version(tag), parse_version(current)
    if latest is None or installed is None:
        return False
    return latest > installed


def fetch_latest() -> tuple[str, str] | None:
    request = urllib.request.Request(
        LATEST_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"AppLauncher/{VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
        tag, url = data["tag_name"], data["html_url"]
    except Exception:
        # Any failure (IncompleteRead, RecursionError, ...) is a silent failed
        # check; it must never escape and kill the watcher thread.
        return None
    if not isinstance(tag, str) or not isinstance(url, str):
        return None
    if not url.startswith(RELEASES_PREFIX):
        return None
    return tag, url


def load_stamp() -> dict:
    try:
        data = json.loads(STAMP_PATH.read_text(encoding="utf-8"))
        checked_at = float(data["checked_at"])
        tag, url = data["latest_tag"], data["latest_url"]
    except Exception:
        # A bad stamp (OverflowError, RecursionError, ...) is treated as empty.
        return dict(_EMPTY_STAMP)
    if not math.isfinite(checked_at):
        # Infinity would postpone checks forever; NaN breaks the comparison.
        return dict(_EMPTY_STAMP)
    if (
        not isinstance(tag, str)
        or not isinstance(url, str)
        or not url.startswith(RELEASES_PREFIX)
    ):
        tag = url = None
    return {"checked_at": checked_at, "latest_tag": tag, "latest_url": url}


def save_stamp(checked_at: float, tag: str | None, url: str | None) -> None:
    stamp = {"checked_at": checked_at, "latest_tag": tag, "latest_url": url}
    try:
        STAMP_PATH.parent.mkdir(parents=True, exist_ok=True)
        STAMP_PATH.write_text(json.dumps(stamp), encoding="utf-8")
    except OSError:
        pass


def saved_newer() -> tuple[str, str] | None:
    stamp = load_stamp()
    tag, url = stamp["latest_tag"], stamp["latest_url"]
    if tag is not None and url is not None and is_newer(tag):
        return tag, url
    return None


def run_due_check(on_newer: Callable[[str, str], None], now: float) -> float:
    """Check if a day has passed; return seconds until the next check."""
    stamp = load_stamp()
    elapsed = now - stamp["checked_at"]
    if 0 <= elapsed < CHECK_INTERVAL:
        return CHECK_INTERVAL - elapsed
    if elapsed < 0:
        # A stamp from the future (clock change) must not block checks for long:
        # rewrite it so the next check is due one interval from now.
        save_stamp(now, stamp["latest_tag"], stamp["latest_url"])
        return CHECK_INTERVAL

    result = fetch_latest()
    # shortcut: a failed check counts as the day's attempt, so while offline we
    # retry once per day at most; ceiling is a day's delay after reconnecting.
    tag, url = result if result else (stamp["latest_tag"], stamp["latest_url"])
    save_stamp(now, tag, url)
    if result and is_newer(result[0]):
        on_newer(*result)
    return CHECK_INTERVAL


def watch(on_newer: Callable[[str, str], None]) -> None:
    try:
        known = saved_newer()
        if known:
            on_newer(*known)
    except Exception:
        # The watcher thread must outlive any failure, including the callback's.
        pass
    time.sleep(STARTUP_DELAY)
    while True:
        try:
            wait = run_due_check(on_newer, time.time())
        except Exception:
            # Same reason: a failed round just waits a day instead of ending checks.
            wait = CHECK_INTERVAL
        time.sleep(wait)
