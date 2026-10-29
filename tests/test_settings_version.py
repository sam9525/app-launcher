"""The Settings heading shows the version from version.py."""

import pathlib
import sys
import tempfile
import unittest.mock as mock

import customtkinter as ctk

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import config
import settings_ui
import version


def _labels(widget) -> list[str]:
    found = [widget.cget("text")] if isinstance(widget, ctk.CTkLabel) else []
    for child in widget.winfo_children():
        found += _labels(child)
    return found


def test_heading_shows_version() -> None:
    seen: list[str] = []

    def mock_mainloop(self):
        try:
            seen.extend(_labels(self))
        finally:
            self.destroy()

    with tempfile.TemporaryDirectory() as d:
        old_config = config.CONFIG_PATH
        config.CONFIG_PATH = pathlib.Path(d) / "config.json"
        try:
            # A made-up version proves the text is read, not typed in.
            with mock.patch.object(version, "VERSION", "9.8.7"), mock.patch.object(
                ctk.CTk, "mainloop", mock_mainloop
            ):
                settings_ui._run()
        finally:
            config.CONFIG_PATH = old_config

    assert "v9.8.7" in seen
    assert "App Launcher" not in seen


if __name__ == "__main__":
    test_heading_shows_version()
    print("ok")
