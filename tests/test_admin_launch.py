"""Basename and elevation lookups used to match and detect admin windows."""

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import launcher


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


if __name__ == "__main__":
    test_basename_of_own_process()
    test_basename_is_cached()
    test_own_process_not_elevated()
    test_is_elevated_unknown_pid_is_true()
    print("ok")
