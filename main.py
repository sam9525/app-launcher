"""Entry point: DPI awareness, single-instance mutex, hotkey thread, tray loop."""

import ctypes
import threading


def main() -> None:
    # Must run before any monitor/window call so all coords are physical pixels
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

    import win32api
    import win32event
    import winerror

    mutex = win32event.CreateMutex(None, False, "Global\\AppLauncherSingleton")
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        MB_ICONINFORMATION = 0x40
        ctypes.windll.user32.MessageBoxW(
            0, "App Launcher is already running.", "App Launcher", MB_ICONINFORMATION
        )
        return

    import config
    import tray

    config.load()
    was_reset = getattr(config.load, "was_reset", False)

    icon = tray.make_icon()
    threading.Thread(target=tray.hotkey_thread, args=(icon,), daemon=True).start()

    if was_reset:  # missing/corrupt config: get the user straight into Settings
        try:
            import settings_ui

            settings_ui.open_settings()
        except ImportError:
            pass  # settings_ui lands in the next task

    icon.run()  # owns the main thread until Exit; `mutex` stays alive in this frame


if __name__ == "__main__":
    main()
