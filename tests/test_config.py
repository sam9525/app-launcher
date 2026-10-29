import pathlib
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import win32con

import config
import settings_ui
import tray


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
                {
                    "name": "VS Code",
                    "enabled": True,
                    "kind": "app",
                    "path": "C:\\apps\\Code.exe",
                    "args": "",
                    "match_process": "Code.exe",
                    "monitor": 1,
                    "zone": "left-half",
                },
                {
                    "name": "Claude",
                    "enabled": True,
                    "kind": "terminal",
                    "workdir": "D:\\proj",
                    "startup_command": "claude",
                    "monitor": 2,
                    "zone": "right-half",
                },
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


def test_tray_on_exit():
    mock_icon = mock.Mock()
    with mock.patch("win32gui.UnregisterHotKey") as mock_unregister:
        tray._on_exit(mock_icon)
        mock_unregister.assert_called_once_with(None, tray.HOTKEY_ID)
        mock_icon.stop.assert_called_once()


def test_send_startup_command_com_init_uninit():
    hwnd = 12345
    with (
        mock.patch("win32gui.GetForegroundWindow", return_value=hwnd),
        mock.patch("win32gui.SetForegroundWindow"),
        mock.patch("pythoncom.CoInitialize") as mock_co_init,
        mock.patch("pythoncom.CoUninitialize") as mock_co_uninit,
        mock.patch("win32com.client.Dispatch") as mock_dispatch,
        mock.patch("time.sleep"),
    ):
        import launcher

        # Mock Dispatch object to allow SendKeys call
        mock_shell = mock.Mock()
        mock_dispatch.return_value = mock_shell

        res = launcher._send_startup_command(hwnd, "test_cmd")

        assert res is True
        mock_co_init.assert_called_once()
        mock_co_uninit.assert_called_once()
        mock_dispatch.assert_called_once_with("WScript.Shell")
        mock_shell.SendKeys.assert_called_once()


def test_send_startup_command_com_uninit_on_error():
    hwnd = 12345
    with (
        mock.patch("win32gui.GetForegroundWindow", return_value=hwnd),
        mock.patch("win32gui.SetForegroundWindow"),
        mock.patch("pythoncom.CoInitialize") as mock_co_init,
        mock.patch("pythoncom.CoUninitialize") as mock_co_uninit,
        mock.patch("win32com.client.Dispatch", side_effect=RuntimeError("COM error")),
        mock.patch("time.sleep"),
    ):
        import launcher

        try:
            launcher._send_startup_command(hwnd, "test_cmd")
        except RuntimeError:
            pass

        mock_co_init.assert_called_once()
        mock_co_uninit.assert_called_once()


def test_terminal_launched_once_then_skipped():
    import launcher

    entry = {
        "name": "Claude",
        "kind": "terminal",
        "workdir": "D:\\proj",
        "startup_command": "",
        "monitor": 1,
        "zone": "maximized",
    }
    launcher._launched_terminals.clear()
    with (
        mock.patch("launcher._windows_for", return_value=[]),
        mock.patch("launcher._spawn") as mock_spawn,
        mock.patch("launcher._poll_new_window", return_value=999),
        mock.patch("launcher._position") as mock_position,
    ):
        # First press: spawns, positions, marks.
        assert launcher._handle_entry(entry, {}) is None
        assert mock_spawn.call_count == 1
        assert mock_position.call_count == 1
        assert launcher._terminal_key(entry) in launcher._launched_terminals
        # Second press: skipped entirely, no respawn, no reposition.
        assert launcher._handle_entry(entry, {}) is None
        assert mock_spawn.call_count == 1
        assert mock_position.call_count == 1
    launcher._launched_terminals.clear()


def test_position_maximized_restore():
    hwnd = 12345
    with (
        mock.patch("monitors.get_monitors", return_value=[(0, 0, 1920, 1080)]),
        mock.patch("monitors.zone_rect", return_value=(0, 0, 1920, 1080)),
        mock.patch("win32gui.IsIconic", return_value=False),
        mock.patch("win32gui.GetWindowPlacement") as mock_get_placement,
        mock.patch("win32gui.ShowWindow") as mock_show_window,
        mock.patch("win32gui.SetWindowPos") as mock_set_window_pos,
    ):
        import win32con

        import launcher

        # Case 1: Window is already maximized (SW_SHOWMAXIMIZED)
        mock_get_placement.return_value = (
            0,
            win32con.SW_SHOWMAXIMIZED,
            (0, 0),
            (0, 0),
            (0, 0, 100, 100),
        )

        launcher._position(hwnd, 1, "maximized")

        # Verify SW_RESTORE was called, then SetWindowPos, then SW_MAXIMIZE
        mock_show_window.assert_any_call(hwnd, win32con.SW_RESTORE)
        mock_show_window.assert_any_call(hwnd, win32con.SW_MAXIMIZE)
        mock_set_window_pos.assert_called_once()

        mock_show_window.reset_mock()
        mock_set_window_pos.reset_mock()

        # Case 2: Window is not maximized (SW_SHOWNORMAL)
        mock_get_placement.return_value = (
            0,
            win32con.SW_SHOWNORMAL,
            (0, 0),
            (0, 0),
            (0, 0, 100, 100),
        )

        launcher._position(hwnd, 1, "maximized")

        # SW_RESTORE should not be called, only SW_MAXIMIZE
        restore_calls = [
            call
            for call in mock_show_window.call_args_list
            if call[0][1] == win32con.SW_RESTORE
        ]
        assert len(restore_calls) == 0
        mock_show_window.assert_any_call(hwnd, win32con.SW_MAXIMIZE)
        mock_set_window_pos.assert_called_once()


def test_position_half_inflates_for_border():
    hwnd = 12345
    with (
        mock.patch("monitors.get_monitors", return_value=[(0, 0, 1920, 1080)]),
        mock.patch("monitors.zone_rect", return_value=(0, 0, 960, 1080)),
        mock.patch("launcher._frame_margins", return_value=(7, 0, 7, 7)),
        mock.patch("win32gui.IsIconic", return_value=False),
        mock.patch(
            "win32gui.GetWindowPlacement",
            return_value=(0, win32con.SW_SHOWNORMAL, (0, 0), (0, 0), (0, 0, 100, 100)),
        ),
        mock.patch("win32gui.ShowWindow"),
        mock.patch("win32gui.SetWindowPos") as mock_set_pos,
    ):
        import launcher

        launcher._position(hwnd, 1, "left-half")
        # Visible target (0,0,960,1080) inflated by (7,0,7,7) -> outer (-7,0,974,1087).
        mock_set_pos.assert_called_once_with(
            hwnd, 0, -7, 0, 974, 1087, win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
        )


def test_position_open_only_is_noop():
    hwnd = 12345
    with (
        mock.patch("monitors.get_monitors") as mock_get_mons,
        mock.patch("win32gui.SetWindowPos") as mock_set_pos,
        mock.patch("win32gui.ShowWindow") as mock_show,
    ):
        import launcher

        launcher._position(hwnd, 1, "open-only")
        mock_get_mons.assert_not_called()
        mock_set_pos.assert_not_called()
        mock_show.assert_not_called()


def test_open_only_in_zones():
    assert "open-only" in config.ZONES


def test_resolve_theme_explicit():
    assert config.resolve_theme({"theme": "dark"}) == "dark"
    assert config.resolve_theme({"theme": "light"}) == "light"


def test_resolve_theme_system_reads_registry():
    # AppsUseLightTheme == 0 -> dark, non-zero/1 -> light.
    with (
        mock.patch("winreg.OpenKey"),
        mock.patch("winreg.QueryValueEx", return_value=(0, 4)),
    ):
        assert config.resolve_theme({"theme": "system"}) == "dark"
    with (
        mock.patch("winreg.OpenKey"),
        mock.patch("winreg.QueryValueEx", return_value=(1, 4)),
    ):
        assert config.resolve_theme({}) == "light"  # default is 'system'


def test_resolve_theme_registry_failure_defaults_light():
    with mock.patch("winreg.OpenKey", side_effect=OSError):
        assert config.resolve_theme({"theme": "system"}) == "light"


if __name__ == "__main__":
    test_round_trip()
    test_missing_file_returns_default()
    test_corrupt_file_backed_up_and_default()
    test_unknown_keys_pass_through()
    test_parse_hotkey()
    test_make_icon()
    test_open_settings_starts_thread()
    test_open_settings_lifts_existing_window()
    test_tray_on_exit()
    test_send_startup_command_com_init_uninit()
    test_send_startup_command_com_uninit_on_error()
    test_terminal_launched_once_then_skipped()
    test_position_maximized_restore()
    test_position_half_inflates_for_border()
    test_position_open_only_is_noop()
    test_open_only_in_zones()
    test_resolve_theme_explicit()
    test_resolve_theme_system_reads_registry()
    test_resolve_theme_registry_failure_defaults_light()
    print("test_config OK")
