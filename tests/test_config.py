import pathlib
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import config
import win32con
import tray
import settings_ui


def _in_tmp(fn):
    """Point config.CONFIG_PATH at a fresh temp dir for the duration of fn."""
    with tempfile.TemporaryDirectory() as d:
        old = config.CONFIG_PATH
        config.CONFIG_PATH = pathlib.Path(d) / "config.json"
        try:
            fn(pathlib.Path(d))
        finally:
            config.CONFIG_PATH = old


def test_round_trip():
    def body(_d):
        cfg = {
            "hotkey": "ctrl+alt+l",
            "entries": [
                {"name": "VS Code", "enabled": True, "kind": "app",
                 "path": "C:\\apps\\Code.exe", "args": "", "match_process": "Code.exe",
                 "monitor": 1, "zone": "left-half"},
                {"name": "Claude", "enabled": True, "kind": "terminal",
                 "workdir": "D:\\proj", "startup_command": "claude",
                 "monitor": 2, "zone": "right-half"},
            ],
        }
        config.save(cfg)
        loaded = config.load()
        assert loaded == cfg
        assert config.load.was_reset is False

    _in_tmp(body)


def test_missing_file_returns_default():
    def body(_d):
        loaded = config.load()
        assert loaded == {"hotkey": config.DEFAULT_HOTKEY, "entries": []}
        assert config.load.was_reset is True

    _in_tmp(body)


def test_corrupt_file_backed_up_and_default():
    def body(d):
        config.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        config.CONFIG_PATH.write_bytes(b"\x00\xffnot json{{{")
        loaded = config.load()
        assert loaded == {"hotkey": config.DEFAULT_HOTKEY, "entries": []}
        assert config.load.was_reset is True
        assert (d / "config.json.bad").exists()
        assert not config.CONFIG_PATH.exists()

    _in_tmp(body)


def test_unknown_keys_pass_through():
    def body(_d):
        cfg = {"hotkey": "ctrl+alt+l", "entries": [], "future_field": 42}
        config.save(cfg)
        assert config.load()["future_field"] == 42

    _in_tmp(body)


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


def test_open_settings_starts_thread():
    with mock.patch("threading.Thread") as mock_thread:
        settings_ui._ui_thread = None
        settings_ui.open_settings()
        mock_thread.assert_called_once_with(target=settings_ui._run, daemon=True)
        mock_thread.return_value.start.assert_called_once()


def test_open_settings_lifts_existing_window():
    mock_thread = mock.Mock()
    mock_thread.is_alive.return_value = True
    settings_ui._ui_thread = mock_thread

    mock_root = mock.Mock()
    settings_ui._root = mock_root

    settings_ui.open_settings()
    mock_root.event_generate.assert_called_once_with("<<Lift>>", when="tail")


if __name__ == "__main__":
    test_round_trip()
    test_missing_file_returns_default()
    test_corrupt_file_backed_up_and_default()
    test_unknown_keys_pass_through()
    test_parse_hotkey()
    test_make_icon()
    test_open_settings_starts_thread()
    test_open_settings_lifts_existing_window()
    print("test_config OK")
