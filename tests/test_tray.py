import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import win32con
import tray


def test_parse_hotkey():
    mods, vk = tray._parse_hotkey("ctrl+alt+l")
    assert mods == (win32con.MOD_CONTROL | win32con.MOD_ALT)
    assert vk == ord("L")

    mods, vk = tray._parse_hotkey("shift+win+k")
    assert mods == (win32con.MOD_SHIFT | win32con.MOD_WIN)
    assert vk == ord("K")


def test_make_icon():
    icon = tray.make_icon()
    assert icon.title == "App Launcher"
    assert icon.name == "AppLauncher"

    # Check menu items exist
    menu_items = list(icon.menu)
    assert len(menu_items) == 3
    assert menu_items[0].text == "Launch"
    assert menu_items[1].text == "Settings"
    assert menu_items[2].text == "Exit"


if __name__ == "__main__":
    test_parse_hotkey()
    test_make_icon()
    print("test_tray OK")
