"""pystray icon/menu + RegisterHotKey message loop (runs on a daemon thread)."""

import os
import sys
import threading
import webbrowser

import pystray
import win32con
import win32gui
from PIL import Image

import config
import launcher
import updates

HOTKEY_ID = 1
_MODS = {
    "ctrl": win32con.MOD_CONTROL,
    "alt": win32con.MOD_ALT,
    "shift": win32con.MOD_SHIFT,
    "win": win32con.MOD_WIN,
}


_update: tuple[str, str] | None = None


def _on_newer(icon, tag: str, url: str) -> None:
    global _update
    if _update is not None and _update[0] == tag:
        return  # watch() may report the same tag twice per run
    _update = (tag, url)
    icon.update_menu()
    icon.notify(f"App Launcher {tag} is available. Open it from the tray menu.")


def _open_release(icon, item=None) -> None:
    if _update:
        webbrowser.open(_update[1])


def start_update_watch(icon) -> None:
    icon.visible = True  # pystray does not show the icon itself when setup is given
    threading.Thread(
        target=updates.watch,
        args=(lambda tag, url: _on_newer(icon, tag, url),),
        daemon=True,
    ).start()


def _launch_async(icon, item=None):
    def work():
        icon.notify(launcher.launch_all())

    threading.Thread(target=work, daemon=True).start()


def _open_settings(icon, item=None):
    try:
        import settings_ui  # deferred: built last per spec build order

        settings_ui.open_settings()
    except ImportError:
        icon.notify("Settings UI not built yet")


def _on_exit(icon, item=None):
    try:
        win32gui.UnregisterHotKey(None, HOTKEY_ID)
    except Exception:
        pass
    icon.stop()


def asset_path(name: str) -> str:
    # sys._MEIPASS is set in the PyInstaller build; assets are bundled there
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


ICON_FILE = "app-launcher-icon.ico"


def _icon_image() -> Image.Image:
    try:
        return Image.open(asset_path(ICON_FILE))
    except (FileNotFoundError, OSError):
        # ponytail: fall back to a solid square so a missing asset never kills the tray
        return Image.new("RGB", (16, 16), (45, 125, 210))


def make_icon() -> pystray.Icon:
    image = _icon_image()
    menu = pystray.Menu(
        pystray.MenuItem("Launch", _launch_async, default=True),
        pystray.MenuItem("Settings", _open_settings),
        pystray.MenuItem(
            lambda item: f"Update available ({_update[0]})" if _update else "",
            _open_release,
            visible=lambda item: _update is not None,
        ),
        pystray.MenuItem("Exit", _on_exit),
    )
    return pystray.Icon("AppLauncher", image, "App Launcher", menu)


def _parse_hotkey(spec: str) -> tuple[int, int]:
    *mod_names, key = spec.lower().split("+")
    mods = 0
    for m in mod_names:
        mods |= _MODS[m]
    return mods, ord(key.upper())


def hotkey_thread(icon) -> None:
    """RegisterHotKey must live on the same thread as its GetMessage loop."""
    spec = config.load().get("hotkey", config.DEFAULT_HOTKEY)
    try:
        mods, vk = _parse_hotkey(spec)
        win32gui.RegisterHotKey(None, HOTKEY_ID, mods, vk)
    except Exception:
        icon.notify(f"Hotkey {spec} unavailable — use the tray menu")
        return
    # ponytail: no UnregisterHotKey on exit — daemon thread dies with the
    # process and the OS releases the registration
    while True:
        rc, msg = win32gui.GetMessage(None, 0, 0)  # type: ignore[arg-type]  # stub rejects None hwnd
        if rc == 0:  # WM_QUIT
            break
        if msg[1] == win32con.WM_HOTKEY:
            _launch_async(icon)
