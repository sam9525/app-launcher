import contextlib
import http.client
import io
import json
import pathlib
import sys
import tempfile
import urllib.error
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import updates

VALID_URL = updates.RELEASES_PREFIX + "tag/v9.0.0"
EMPTY = {"checked_at": 0.0, "latest_tag": None, "latest_url": None}
NOW = 1_000_000_000.0


@contextlib.contextmanager
def stamp_file(content=None):
    """Point STAMP_PATH at a temp file, optionally pre-filled (str or dict)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "update-check.json"
        if isinstance(content, dict):
            content = json.dumps(content)
        if content is not None:
            path.write_text(content, encoding="utf-8")
        with mock.patch.object(updates, "STAMP_PATH", path):
            yield path


def stamp(checked_at, tag=None, url=None):
    return {"checked_at": checked_at, "latest_tag": tag, "latest_url": url}


def fake_response(payload):
    return io.BytesIO(json.dumps(payload).encode())


def test_is_newer():
    assert updates.is_newer("v0.2.10", "0.2.9")
    assert not updates.is_newer("v0.2.1", "0.2.1")
    assert not updates.is_newer("v0.2.0", "0.2.1")
    assert not updates.is_newer("nightly", "0.2.1")


def test_fetch_rejects_foreign_url():
    payload = {"tag_name": "v9.0.0", "html_url": "https://evil.example/x"}
    with mock.patch("urllib.request.urlopen", return_value=fake_response(payload)):
        assert updates.fetch_latest() is None


def test_fetch_ok():
    payload = {"tag_name": "v9.0.0", "html_url": VALID_URL}
    with mock.patch("urllib.request.urlopen", return_value=fake_response(payload)):
        assert updates.fetch_latest() == (
            "v9.0.0",
            updates.RELEASES_PREFIX + "tag/v9.0.0",
        )


def test_fetch_offline_is_none():
    with mock.patch(
        "urllib.request.urlopen", side_effect=urllib.error.URLError("down")
    ):
        assert updates.fetch_latest() is None


def test_corrupt_stamp_is_empty():
    with stamp_file("{not json"):
        assert updates.load_stamp() == EMPTY


def test_saved_foreign_url_ignored():
    with stamp_file(stamp(NOW, "v9.0.0", "https://evil.example/x")):
        assert updates.saved_newer() is None


def test_saved_old_tag_not_reported():
    with stamp_file(stamp(NOW, "v0.2.1", VALID_URL)):
        assert updates.saved_newer() is None


def test_fresh_stamp_skips_fetch():
    with stamp_file(stamp(NOW - 60)):
        cb = mock.Mock()
        with mock.patch.object(updates, "fetch_latest") as fetch:
            wait = updates.run_due_check(cb, NOW)
        fetch.assert_not_called()
        assert 0 < wait <= updates.CHECK_INTERVAL


def test_due_check_reports_and_saves():
    with stamp_file(stamp(0.0)):
        cb = mock.Mock()
        with mock.patch.object(
            updates, "fetch_latest", return_value=("v9.0.0", VALID_URL)
        ):
            updates.run_due_check(cb, NOW)
        cb.assert_called_once_with("v9.0.0", VALID_URL)
        assert updates.load_stamp()["latest_tag"] == "v9.0.0"


def test_offline_keeps_saved_result():
    with stamp_file(stamp(1.0, "v9.0.0", VALID_URL)):
        cb = mock.Mock()
        with mock.patch.object(updates, "fetch_latest", return_value=None):
            updates.run_due_check(cb, NOW)
        s = updates.load_stamp()
        assert s["checked_at"] == NOW and s["latest_tag"] == "v9.0.0"


def test_future_stamp_waits_one_interval():
    with stamp_file(stamp(NOW + 10 * 24 * 60 * 60)):
        cb = mock.Mock()
        with mock.patch.object(updates, "fetch_latest") as fetch:
            assert updates.run_due_check(cb, NOW) == updates.CHECK_INTERVAL
        fetch.assert_not_called()
        with mock.patch.object(updates, "fetch_latest", return_value=None) as fetch:
            updates.run_due_check(cb, NOW + updates.CHECK_INTERVAL)
        fetch.assert_called_once()


def test_fetch_incomplete_read_is_none():
    response = mock.MagicMock()
    response.__enter__.return_value.read.side_effect = http.client.IncompleteRead(b"")
    with mock.patch("urllib.request.urlopen", return_value=response):
        assert updates.fetch_latest() is None


def test_overflow_stamp_is_empty():
    huge = "1" + "0" * 399
    with stamp_file(
        '{"checked_at": %s, "latest_tag": null, "latest_url": null}' % huge
    ):
        assert updates.load_stamp() == EMPTY


def test_infinite_stamp_is_empty():
    with stamp_file('{"checked_at": Infinity, "latest_tag": null, "latest_url": null}'):
        assert updates.load_stamp() == EMPTY


class StopTest(BaseException):
    """Ends the endless watch loop; BaseException so watch cannot swallow it."""


def test_watch_survives_callback_error():
    sleeps = []
    calls = []

    def flaky_check(on_newer, now):
        calls.append(now)
        if len(calls) == 1:
            raise RuntimeError("callback blew up")
        raise StopTest

    with stamp_file(), mock.patch.object(
        updates, "run_due_check", side_effect=flaky_check
    ), mock.patch("time.sleep", side_effect=sleeps.append):
        try:
            updates.watch(mock.Mock())
        except StopTest:
            pass
    assert sleeps == [updates.STARTUP_DELAY, updates.CHECK_INTERVAL]


def test_watch_waits_before_first_check():
    events = []

    def record_check(on_newer, now):
        events.append("check")
        raise StopTest

    with mock.patch.object(
        updates, "saved_newer", return_value=None
    ), mock.patch.object(
        updates, "run_due_check", side_effect=record_check
    ), mock.patch(
        "time.sleep", side_effect=lambda s: events.append(("sleep", s))
    ):
        try:
            updates.watch(mock.Mock())
        except StopTest:
            pass
    assert events == [("sleep", updates.STARTUP_DELAY), "check"]


def test_parse_rejects_odd_digits():
    assert updates.parse_version("v1_0.2") is None
    assert updates.parse_version("v+1.0.0") is None


if __name__ == "__main__":
    test_is_newer()
    test_fetch_rejects_foreign_url()
    test_fetch_ok()
    test_fetch_offline_is_none()
    test_corrupt_stamp_is_empty()
    test_saved_foreign_url_ignored()
    test_saved_old_tag_not_reported()
    test_fresh_stamp_skips_fetch()
    test_due_check_reports_and_saves()
    test_offline_keeps_saved_result()
    test_future_stamp_waits_one_interval()
    test_fetch_incomplete_read_is_none()
    test_overflow_stamp_is_empty()
    test_infinite_stamp_is_empty()
    test_watch_survives_callback_error()
    test_watch_waits_before_first_check()
    test_parse_rejects_odd_digits()
    print("test_updates OK")
