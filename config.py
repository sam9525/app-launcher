"""Load/save %APPDATA%\\AppLauncher\\config.json. No schema validation by design."""

import json
import os
import sys
import winreg
from pathlib import Path

CONFIG_PATH = Path(os.environ["APPDATA"]) / "AppLauncher" / "config.json"
DEFAULT_HOTKEY = "ctrl+alt+l"
ZONES = [
    "maximized",
    "left-half",
    "right-half",
    "top-half",
    "bottom-half",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "open-only",
]


def load() -> dict:
    load.was_reset = False
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        load.was_reset = True
    except ValueError:  # JSONDecodeError and UnicodeDecodeError are both ValueError
        # keep the bad file recoverable, then start fresh
        CONFIG_PATH.replace(CONFIG_PATH.with_name(CONFIG_PATH.name + ".bad"))
        load.was_reset = True
    return {"hotkey": DEFAULT_HOTKEY, "entries": []}


def save(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_name(CONFIG_PATH.name + ".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "AppLauncher"  # same name the installer's startup task uses


def _startup_command() -> str:
    exe = sys.executable
    if getattr(sys, "frozen", False):  # PyInstaller build: exe is the app itself
        return f'"{exe}"'
    main = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return f'"{exe}" "{main}"'


def is_run_at_startup() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, _RUN_VALUE)
        return True
    except OSError:
        return False


def set_run_at_startup(enabled: bool) -> None:
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as k:
        if enabled:
            winreg.SetValueEx(k, _RUN_VALUE, 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                winreg.DeleteValue(k, _RUN_VALUE)
            except FileNotFoundError:
                pass


_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def resolve_theme(cfg: dict) -> str:
    """Effective theme, 'light' or 'dark'. cfg['theme'] is 'system' (default),
    'light', or 'dark'; 'system' follows the Windows AppsUseLightTheme setting."""
    pref = cfg.get("theme", "system")
    if pref in ("light", "dark"):
        return pref
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE) as k:
            apps_light, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return "light" if apps_light else "dark"
    except OSError:
        return "light"
