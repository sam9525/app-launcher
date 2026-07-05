import pathlib
import sys
import unittest.mock as mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import settings_ui


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
    test_open_settings_starts_thread()
    test_open_settings_lifts_existing_window()
    print("test_settings_ui OK")
