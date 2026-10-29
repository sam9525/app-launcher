import pathlib
import sys
import unittest.mock as mock

import customtkinter as ctk

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import config
import settings_ui


def test_settings_explorer_flow():
    import tempfile
    import time

    with tempfile.TemporaryDirectory() as d:
        old_config = config.CONFIG_PATH
        config.CONFIG_PATH = pathlib.Path(d) / "config.json"
        try:
            # 1. Save config with an existing explorer entry
            initial_entries = [
                {
                    "name": "My Explorer",
                    "enabled": True,
                    "kind": "explorer",
                    "folders": ["C:\\Windows", "C:\\Users"],
                    "monitor": 1,
                    "zone": "maximized",
                }
            ]
            config.save({"hotkey": "ctrl+alt+l", "entries": initial_entries})

            def mock_mainloop(self):
                try:
                    # Helper to process events and let animations run
                    def wait_for_animation():
                        for _ in range(25):
                            self.update()
                            time.sleep(0.02)

                    # Let Tkinter layout the widgets and process events
                    self.update_idletasks()
                    self.update()

                    # Find the exact bound grandchild widgets of "My Explorer" tile
                    bound_widgets = []

                    def find_bound(widget):
                        try:
                            binds = widget.bind("<Button-1>")
                            if binds:
                                path = str(widget)
                                if "ctkscrollableframe" in path:
                                    bound_widgets.append(widget)
                        except Exception:
                            pass
                        for child in widget.winfo_children():
                            find_bound(child)

                    find_bound(self)
                    print(
                        f"DEBUG: Found bound widgets in scrollable frame: "
                        f"{bound_widgets}"
                    )
                    assert (
                        len(bound_widgets) > 0
                    ), "No bound widgets found for explorer tile"

                    # Locate widgets we need: kind_seg, name_entry, folders_box,
                    # save_btn
                    kind_seg = None
                    name_var = None
                    folders_box = None
                    save_btn = None

                    def find_panel_widgets(widget):
                        nonlocal kind_seg, name_var, folders_box, save_btn
                        if isinstance(widget, ctk.CTkSegmentedButton):
                            kind_seg = widget
                        elif isinstance(widget, ctk.CTkEntry):
                            info = widget.grid_info()
                            if info.get("row") == 1 and info.get("column") == 1:
                                name_var = widget.cget("textvariable")
                        elif isinstance(widget, ctk.CTkTextbox):
                            folders_box = widget
                        elif (
                            isinstance(widget, ctk.CTkButton)
                            and widget.cget("text") == "Save"
                        ):
                            save_btn = widget
                        for child in widget.winfo_children():
                            find_panel_widgets(child)

                    find_panel_widgets(self)

                    assert kind_seg is not None, "kind_seg not found"
                    assert folders_box is not None, "folders_box not found"
                    assert save_btn is not None, "save_btn not found"
                    assert name_var is not None, "name_var not found"

                    # Generate Button-1 on the first bound grandchild of our tile
                    print(f"DEBUG: Generating event on {bound_widgets[0]}")
                    bound_widgets[0].event_generate("<Button-1>")
                    wait_for_animation()

                    print(f"DEBUG: kind_seg after event: {kind_seg.get()}")

                    # Verify fields are loaded correctly
                    assert kind_seg.get() == "Explorer"
                    assert name_var.get() == "My Explorer"
                    assert (
                        folders_box.get("1.0", "end").strip()
                        == "C:\\Windows\nC:\\Users"
                    )

                    # 3. Test validation error when empty
                    folders_box.delete("1.0", "end")
                    with mock.patch("settings_ui.messagebox.showwarning") as mock_warn:
                        save_btn.invoke()
                        # No wait needed here since it should return early on warning
                        self.update()
                        mock_warn.assert_called_once()
                        # Verify it did not save (still original entries in config)
                        cfg = config.load()
                        assert len(cfg["entries"]) == 1
                        assert cfg["entries"][0]["folders"] == [
                            "C:\\Windows",
                            "C:\\Users",
                        ]

                    # 3b. Test validation warning when multiple folders do not exist
                    folders_box.delete("1.0", "end")
                    folders_box.insert(
                        "1.0", "C:\\InvalidPathXYZ1\nC:\\InvalidPathXYZ2"
                    )
                    with mock.patch(
                        "settings_ui.messagebox.askyesno", return_value=False
                    ) as mock_ask:
                        save_btn.invoke()
                        assert mock_ask.called
                        msg = mock_ask.call_args[0][1]
                        assert "C:\\InvalidPathXYZ1" in msg
                        assert "C:\\InvalidPathXYZ2" in msg
                        assert "The following folders do not exist" in msg
                        cfg = config.load()
                        assert len(cfg["entries"]) == 1

                    # 4. Test modifying and saving
                    folders_box.delete("1.0", "end")
                    folders_box.insert("1.0", "C:\\Program Files\nD:\\projects")
                    with mock.patch(
                        "settings_ui.messagebox.askyesno", return_value=True
                    ):
                        save_btn.invoke()
                    wait_for_animation()  # wait for save and slide-close animation

                    # Verify it saved successfully
                    cfg = config.load()
                    assert len(cfg["entries"]) == 1
                    assert cfg["entries"][0]["kind"] == "explorer"
                    assert cfg["entries"][0]["folders"] == [
                        "C:\\Program Files",
                        "D:\\projects",
                    ]

                    # 5. Create a new Explorer entry via plus tile
                    plus_tiles = []

                    def find_plus_tiles(widget):
                        if isinstance(widget, ctk.CTkFrame):
                            for child in widget.winfo_children():
                                if (
                                    isinstance(child, ctk.CTkLabel)
                                    and child.cget("text") == "+"
                                ):
                                    plus_tiles.append(widget)
                                    break
                        for child in widget.winfo_children():
                            find_plus_tiles(child)

                    find_plus_tiles(self)
                    assert len(plus_tiles) > 0

                    # Find bound widgets of the plus tile
                    plus_bound = []

                    def find_plus_bound(widget):
                        try:
                            binds = widget.bind("<Button-1>")
                            if binds:
                                # We check if it is part of the plus tile hierarchy
                                path = str(widget)
                                if "ctkscrollableframe" in path:
                                    plus_bound.append(widget)
                        except Exception:
                            pass
                        for child in widget.winfo_children():
                            find_plus_bound(child)

                    find_plus_bound(plus_tiles[0])
                    assert len(plus_bound) > 0

                    # Trigger plus tile click
                    plus_bound[0].event_generate("<Button-1>")
                    wait_for_animation()

                    # It should default to App
                    assert kind_seg.get() == "App"

                    # Switch to Explorer
                    kind_seg.set("Explorer")
                    # Trigger command manually
                    kind_seg.cget("command")("Explorer")

                    name_var.set("New Explorer")
                    folders_box.delete("1.0", "end")
                    folders_box.insert("1.0", "C:\\NewFolder")

                    with mock.patch(
                        "settings_ui.messagebox.askyesno", return_value=True
                    ):
                        save_btn.invoke()
                    wait_for_animation()

                    cfg = config.load()
                    assert len(cfg["entries"]) == 2
                    assert cfg["entries"][1]["name"] == "New Explorer"
                    assert cfg["entries"][1]["kind"] == "explorer"
                    assert cfg["entries"][1]["folders"] == ["C:\\NewFolder"]

                finally:
                    self.destroy()

            with mock.patch.object(ctk.CTk, "mainloop", mock_mainloop):
                settings_ui._run()

        finally:
            config.CONFIG_PATH = old_config


if __name__ == "__main__":
    test_settings_explorer_flow()
