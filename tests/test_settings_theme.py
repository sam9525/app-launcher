import pathlib
import sys
import unittest.mock as mock

import customtkinter as ctk

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import config
import settings_ui


def test_settings_invalid_theme():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        old_config = config.CONFIG_PATH
        config.CONFIG_PATH = pathlib.Path(d) / "config.json"
        try:
            # Save config with invalid theme
            config.save(
                {"hotkey": "ctrl+alt+l", "entries": [], "theme": "invalid-theme-xyz"}
            )

            def mock_mainloop(self):
                try:
                    switches = []

                    def find_switches(widget):
                        if isinstance(widget, ctk.CTkSwitch):
                            switches.append(widget)
                        for child in widget.winfo_children():
                            find_switches(child)

                    find_switches(self)
                    theme_switch = None
                    for sw in switches:
                        if sw.cget("text") == "Dark":
                            theme_switch = sw
                            break

                    assert theme_switch is not None, "Theme switch not found"
                    var = theme_switch.cget("variable")
                    assert var.get() in ("light", "dark")
                finally:
                    self.destroy()

            with mock.patch.object(ctk.CTk, "mainloop", mock_mainloop):
                settings_ui._run()

        finally:
            config.CONFIG_PATH = old_config


if __name__ == "__main__":
    test_settings_invalid_theme()
    print("test_settings_invalid_theme passed successfully!")
