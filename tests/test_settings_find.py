import pathlib
import sys
import unittest.mock as mock
import tkinter as tk
import customtkinter as ctk

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import settings_ui
import config
import app_index

def test_settings_find_button():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        old_config = config.CONFIG_PATH
        config.CONFIG_PATH = pathlib.Path(d) / "config.json"
        try:
            # Save a default empty config
            config.save({"hotkey": "ctrl+alt+l", "entries": []})
            
            def mock_mainloop(self):
                try:
                    plus_tiles = []
                    def find_plus_tiles(widget):
                        if isinstance(widget, ctk.CTkFrame):
                            # Check if it has a label child with text "+"
                            for child in widget.winfo_children():
                                if isinstance(child, ctk.CTkLabel) and child.cget("text") == "+":
                                    plus_tiles.append(widget)
                                    break
                        for child in widget.winfo_children():
                            find_plus_tiles(child)
                    
                    find_plus_tiles(self)
                    assert len(plus_tiles) > 0, "No plus tile found"
                    
                    with mock.patch("app_index.resolve") as mock_resolve:
                        mock_resolve.return_value = "C:/Windows/System32/notepad.exe"
                        
                        # Trigger plus tile click to load empty panel
                        plus_tile = plus_tiles[0]
                        plus_tile.event_generate("<Button-1>")
                        
                        buttons = []
                        entries = []
                        def find_widgets(widget):
                            if isinstance(widget, ctk.CTkButton):
                                buttons.append(widget)
                            if isinstance(widget, ctk.CTkEntry):
                                entries.append(widget)
                            for child in widget.winfo_children():
                                find_widgets(child)
                                
                        find_widgets(self)
                        
                        find_btn = None
                        for btn in buttons:
                            try:
                                if btn.cget("text") == "Find":
                                    find_btn = btn
                                    break
                            except Exception:
                                pass
                                
                        assert find_btn is not None, "Find button not found in UI"
                        
                        name_entry = None
                        path_entry = None
                        for entry in entries:
                            info = entry.grid_info()
                            if info.get("row") == 1 and info.get("column") == 1:
                                name_entry = entry
                            elif info.get("row") == 2 and info.get("column") == 1:
                                path_entry = entry
                                
                        assert name_entry is not None, "Name Entry not found"
                        assert path_entry is not None, "Path Entry not found"
                        
                        name_var = name_entry.cget("textvariable")
                        name_var.set("notepad")
                        
                        # Click the "Find" button
                        find_btn.invoke()
                        
                        # Verify app_index.resolve was called with 'notepad'
                        mock_resolve.assert_called_once_with("notepad")
                        
                        # Verify Path entry got set to the resolved path
                        path_var = path_entry.cget("textvariable")
                        assert path_var.get() == "C:\\Windows\\System32\\notepad.exe"
                        
                    # Now test the case where no match is found
                    with mock.patch("app_index.resolve") as mock_resolve, \
                         mock.patch("tkinter.messagebox.showinfo") as mock_showinfo:
                        mock_resolve.return_value = None
                        
                        name_var.set("unknown_app_abc")
                        find_btn.invoke()
                        
                        mock_resolve.assert_called_once_with("unknown_app_abc")
                        mock_showinfo.assert_called_once()
                        # Path shouldn't have changed
                        assert path_var.get() == "C:\\Windows\\System32\\notepad.exe"
                        
                finally:
                    self.destroy()
            
            with mock.patch.object(ctk.CTk, "mainloop", mock_mainloop):
                settings_ui._run()
                
        finally:
            config.CONFIG_PATH = old_config

if __name__ == "__main__":
    test_settings_find_button()
    print("test_settings_find_button passed successfully!")
