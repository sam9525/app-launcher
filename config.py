"""Load/save %APPDATA%\\AppLauncher\\config.json. No schema validation by design."""
import json
import os
from pathlib import Path

CONFIG_PATH = Path(os.environ["APPDATA"]) / "AppLauncher" / "config.json"
DEFAULT_HOTKEY = "ctrl+alt+l"
ZONES = [
    "maximized", "left-half", "right-half", "top-half", "bottom-half",
    "top-left", "top-right", "bottom-left", "bottom-right",
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
