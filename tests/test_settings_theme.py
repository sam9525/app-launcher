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
                    option_menus = []

                    def find_option_menus(widget):
                        if isinstance(widget, ctk.CTkOptionMenu):
                            option_menus.append(widget)
                        for child in widget.winfo_children():
                            find_option_menus(child)

                    find_option_menus(self)
                    theme_menu = None
                    for menu in option_menus:
                        vals = menu.cget("values")
                        # Handle different types returned by customtkinter cget
                        if isinstance(vals, str):
                            vals_list = [v.strip() for v in vals.split()]
                        else:
                            vals_list = list(vals)
                        if (
                            "System" in vals_list
                            and "Light" in vals_list
                            and "Dark" in vals_list
                        ):
                            theme_menu = menu
                            break

                    assert theme_menu is not None, "Theme OptionMenu not found"
                    var = theme_menu.cget("variable")
                    assert var.get() == "System"
                finally:
                    self.destroy()

            with mock.patch.object(ctk.CTk, "mainloop", mock_mainloop):
                settings_ui._run()

        finally:
            config.CONFIG_PATH = old_config


if __name__ == "__main__":
    test_settings_invalid_theme()
    print("test_settings_invalid_theme passed successfully!")
