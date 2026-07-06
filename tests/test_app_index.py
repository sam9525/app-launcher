import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app_index import resolve


def test_resolve_empty_returns_none():
    assert resolve("") is None
    assert resolve("   ") is None


def test_resolve_nonsense_returns_none_no_raise():
    # A name that matches nothing must return None, never raise.
    assert resolve("zzz_no_such_app_xyzzy_98765") is None


def test_resolve_chrome_app_paths():
    # Chrome is registered in App Paths
    res = resolve("chrome")
    assert res is not None
    assert res.lower().endswith("chrome.exe")
    assert os.path.exists(res)

    res_exe = resolve("chrome.exe")
    assert res_exe == res


def test_resolve_vscode_start_menu():
    # Visual Studio Code shortcut exists in Start Menu
    res = resolve("Visual Studio Code")
    assert res is not None
    assert res.lower().endswith("code.exe")
    assert os.path.exists(res)


if __name__ == "__main__":
    test_resolve_empty_returns_none()
    test_resolve_nonsense_returns_none_no_raise()
    test_resolve_chrome_app_paths()
    test_resolve_vscode_start_menu()
    print("test_app_index OK")
