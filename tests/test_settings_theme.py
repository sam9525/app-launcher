import pathlib
import sys
import unittest.mock as mock
import tkinter as tk

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import settings_ui
import config

def test_settings_invalid_theme():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        old_config = config.CONFIG_PATH
        config.CONFIG_PATH = pathlib.Path(d) / "config.json"
        try:
            # Save config with invalid theme
            config.save({"hotkey": "ctrl+alt+l", "entries": [], "theme": "invalid-theme-xyz"})
            
            def mock_mainloop(self):
                try:
                    comboboxes = []
                    def find_comboboxes(widget):
                        if widget.winfo_class() == "TCombobox":
                            comboboxes.append(widget)
                        for child in widget.winfo_children():
                            find_comboboxes(child)
                    
                    find_comboboxes(self)
                    theme_cb = None
                    for cb in comboboxes:
                        # Values in Combobox are a Tcl tuple or list
                        vals = cb.cget("values")
                        # Handle different types returned by tkinter cget
                        if isinstance(vals, str):
                            vals_list = [v.strip() for v in vals.split()]
                        else:
                            vals_list = list(vals)
                        if "System" in vals_list and "Light" in vals_list and "Dark" in vals_list:
                            theme_cb = cb
                            break
                    
                    assert theme_cb is not None, "Theme Combobox not found"
                    var_name = theme_cb.cget("textvariable")
                    assert self.getvar(var_name) == "System"
                finally:
                    self.destroy()
            
            with mock.patch.object(tk.Tk, "mainloop", mock_mainloop):
                settings_ui._run()
                
        finally:
            config.CONFIG_PATH = old_config

if __name__ == "__main__":
    test_settings_invalid_theme()
    print("test_settings_invalid_theme passed successfully!")
