"""pystray icon/menu + RegisterHotKey message loop (runs on a daemon thread)."""

import threading

import pystray
import win32con
import win32gui
from PIL import Image

import config
import launcher

HOTKEY_ID = 1
_MODS = {
    "ctrl": win32con.MOD_CONTROL,
    "alt": win32con.MOD_ALT,
    "shift": win32con.MOD_SHIFT,
    "win": win32con.MOD_WIN,
}


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


def make_icon() -> pystray.Icon:
    image = Image.new(
        "RGB", (16, 16), (45, 125, 210)
    )  # solid square, no asset to maintain
    menu = pystray.Menu(
        pystray.MenuItem("Launch", _launch_async, default=True),
        pystray.MenuItem("Settings", _open_settings),
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
        rc, msg = win32gui.GetMessage(None, 0, 0)
        if rc == 0:  # WM_QUIT
            break
        if msg[1] == win32con.WM_HOTKEY:
            _launch_async(icon)
