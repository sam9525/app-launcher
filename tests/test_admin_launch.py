"""Basename and elevation lookups used to match and detect admin windows."""

import os
import pathlib
import sys
from unittest import mock

import pywintypes

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import launcher

ENTRY = {
    "name": "Tool",
    "path": r"C:\Tools\tool.exe",
    "args": '-a "b c"',
    "match_process": "tool.exe",
    "monitor": 1,
    "zone": "left-half",
}


def test_basename_of_own_process():
    assert (
        launcher._process_basename(os.getpid(), {})
        == os.path.basename(sys.executable).lower()
    )


def test_basename_is_cached():
    cache = {}
    launcher._process_basename(os.getpid(), cache)
    assert os.getpid() in cache


def test_own_process_not_elevated():
    # The suite runs without admin rights, like the launcher.
    assert launcher._is_elevated(os.getpid()) is False


def test_is_elevated_unknown_pid_is_true():
    assert launcher._is_elevated(0) is True  # PID 0 can't be opened: fail safe


def _err740():
    return OSError(None, "elevation required", None, 740)


def test_spawn_falls_back_to_runas_on_740():
    entry = {**ENTRY, "args": "-a 'b c'"}  # normalises to -a "b c"
    with mock.patch("subprocess.Popen", side_effect=_err740()), mock.patch.object(
        launcher.shell, "ShellExecuteEx"
    ) as sx:
        assert launcher._spawn(entry) is True
    kw = sx.call_args.kwargs
    assert kw["lpVerb"] == "runas"
    assert kw["lpFile"] == entry["path"]
    assert kw["lpParameters"] == '-a "b c"'


def test_spawn_normal_returns_false():
    with mock.patch("subprocess.Popen"):
        assert launcher._spawn(ENTRY) is False


def test_elevated_launch_not_positioned_and_once_per_run():
    launcher._launched_admin.clear()
    with mock.patch.object(
        launcher, "_find_window", return_value=None
    ), mock.patch.object(launcher, "_windows_for", return_value=[]), mock.patch.object(
        launcher, "_spawn", return_value=True
    ) as sp, mock.patch.object(
        launcher, "_poll_new_window"
    ) as poll, mock.patch.object(
        launcher, "_position"
    ) as pos:
        assert launcher._handle_entry(ENTRY, {}) is None
        assert launcher._handle_entry(ENTRY, {}) is None
    assert sp.call_count == 1
    poll.assert_not_called()
    pos.assert_not_called()


def test_declined_then_retries():
    launcher._launched_admin.clear()
    cancel = pywintypes.error(1223, "ShellExecuteEx", "cancelled")
    with mock.patch.object(
        launcher, "_find_window", return_value=None
    ), mock.patch.object(launcher, "_windows_for", return_value=[]), mock.patch.object(
        launcher, "_spawn", side_effect=[cancel, True]
    ) as sp:
        assert launcher._handle_entry(ENTRY, {}) == "admin approval declined"
        assert launcher._handle_entry(ENTRY, {}) is None
    assert sp.call_count == 2


def test_open_admin_window_found_not_positioned():
    with mock.patch.object(
        launcher, "_find_window", return_value=111
    ), mock.patch.object(
        launcher, "_window_is_elevated", return_value=True
    ), mock.patch.object(
        launcher, "_spawn"
    ) as sp, mock.patch.object(
        launcher, "_position"
    ) as pos:
        assert launcher._handle_entry(ENTRY, {}) is None
    sp.assert_not_called()
    pos.assert_not_called()


def test_polled_admin_window_not_positioned():
    launcher._launched_admin.clear()
    with mock.patch.object(
        launcher, "_find_window", return_value=None
    ), mock.patch.object(launcher, "_windows_for", return_value=[]), mock.patch.object(
        launcher, "_spawn", return_value=False
    ), mock.patch.object(
        launcher, "_poll_new_window", return_value=222
    ), mock.patch.object(
        launcher, "_window_is_elevated", return_value=True
    ), mock.patch.object(
        launcher, "_position"
    ) as pos:
        assert launcher._handle_entry(ENTRY, {}) is None
    pos.assert_not_called()


def test_normal_window_still_positioned():
    with mock.patch.object(
        launcher, "_find_window", return_value=333
    ), mock.patch.object(
        launcher, "_window_is_elevated", return_value=False
    ), mock.patch.object(
        launcher, "_position"
    ) as pos:
        launcher._handle_entry(ENTRY, {})
    pos.assert_called_once_with(333, 1, "left-half")


if __name__ == "__main__":
    test_basename_of_own_process()
    test_basename_is_cached()
    test_own_process_not_elevated()
    test_is_elevated_unknown_pid_is_true()
    test_spawn_falls_back_to_runas_on_740()
    test_spawn_normal_returns_false()
    test_elevated_launch_not_positioned_and_once_per_run()
    test_declined_then_retries()
    test_open_admin_window_found_not_positioned()
    test_polled_admin_window_not_positioned()
    test_normal_window_still_positioned()
    print("ok")
