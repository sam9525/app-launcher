import pathlib
import sys
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import tray
import updates

URL = "https://github.com/sam9525/app-launcher/releases/tag/v0.3.0"


def test_notify_once_per_tag():
    tray._update = None
    try:
        icon = mock.MagicMock()
        tray._on_newer(icon, "v0.3.0", URL)
        tray._on_newer(icon, "v0.3.0", URL)
        icon.notify.assert_called_once_with(
            "App Launcher v0.3.0 is available. Open it from the tray menu."
        )
        icon.update_menu.assert_called_once()
    finally:
        tray._update = None


def test_menu_item_hidden_until_update():
    tray._update = None
    try:
        items = list(tray.make_icon().menu.items)
        labels = [i.text for i in items]
        assert labels[:2] == ["Launch", "Settings"] and labels[-1] == "Exit"
        assert not items[2].visible
        tray._update = ("v0.3.0", URL)
        assert items[2].visible and items[2].text == "Update available (v0.3.0)"
    finally:
        tray._update = None


def test_open_release_opens_url():
    tray._update = ("v0.3.0", URL)
    try:
        with mock.patch("webbrowser.open") as op:
            tray._open_release(mock.MagicMock())
        op.assert_called_once_with(URL)
    finally:
        tray._update = None


def test_watch_thread_is_daemon():
    tray._update = None
    try:
        with mock.patch("threading.Thread") as T:
            tray.start_update_watch(mock.MagicMock())
        assert T.call_args.kwargs["daemon"] is True
        assert T.call_args.kwargs["target"] is updates.watch
        T.return_value.start.assert_called_once()
        T.call_args.kwargs["args"][0]("v0.3.0", URL)
        assert tray._update == ("v0.3.0", URL)
    finally:
        tray._update = None


if __name__ == "__main__":
    test_notify_once_per_tag()
    test_menu_item_hidden_until_update()
    test_open_release_opens_url()
    test_watch_thread_is_daemon()
    print("test_tray_update OK")
