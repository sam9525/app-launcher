import pathlib
import sys
import time
import unittest.mock as mock
import customtkinter as ctk

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import config
import launcher
import settings_ui


def test_open_one_respects_run_lock():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        old_config = config.CONFIG_PATH
        config.CONFIG_PATH = pathlib.Path(d) / "config.json"
        try:
            # Save config with one app entry
            config.save(
                {
                    "hotkey": "ctrl+alt+l",
                    "entries": [
                        {
                            "name": "test_app",
                            "enabled": True,
                            "kind": "app",
                            "path": "notepad.exe",
                            "monitor": 1,
                            "zone": "maximized",
                        }
                    ],
                }
            )

            captured_on_open = []
            orig_make_block = settings_ui._make_block

            def mock_make_block(
                parent, entry, command, on_toggle, on_open, mons, accent
            ):
                captured_on_open.append(on_open)
                return orig_make_block(
                    parent, entry, command, on_toggle, on_open, mons, accent
                )

            def mock_mainloop(self):
                try:
                    assert len(captured_on_open) > 0, "on_open callback not captured"
                    on_open_fn = captured_on_open[0]

                    # Setup: ensure the lock is released initially
                    if launcher._run_lock.locked():
                        launcher._run_lock.release()

                    with mock.patch("launcher._handle_entry") as mock_handle:
                        # Case 1: Lock is free. on_open_fn should acquire it, run _handle_entry, then release it.
                        on_open_fn()

                        # Wait a bit for the thread to run
                        for _ in range(20):
                            if mock_handle.called:
                                break
                            time.sleep(0.05)

                        mock_handle.assert_called_once_with(
                            {
                                "name": "test_app",
                                "enabled": True,
                                "kind": "app",
                                "path": "notepad.exe",
                                "monitor": 1,
                                "zone": "maximized",
                            },
                            {},
                        )
                        assert not launcher._run_lock.locked()

                        # Reset mock
                        mock_handle.reset_mock()

                        # Case 2: Lock is already acquired by something else. on_open_fn should return immediately.
                        launcher._run_lock.acquire()
                        try:
                            on_open_fn()
                            time.sleep(0.2)  # wait to see if it runs
                            mock_handle.assert_not_called()
                        finally:
                            launcher._run_lock.release()

                finally:
                    self.destroy()

            with (
                mock.patch("settings_ui._make_block", mock_make_block),
                mock.patch.object(ctk.CTk, "mainloop", mock_mainloop),
            ):
                settings_ui._run()

        finally:
            config.CONFIG_PATH = old_config


if __name__ == "__main__":
    test_open_one_respects_run_lock()
    print("test_open_one_respects_run_lock passed successfully!")
