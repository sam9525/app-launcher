"""Pure-logic checks for the explorer kind. No Win32 side effects here."""

import launcher


def test_parse_folder_lines_strips_blanks_and_whitespace():
    text = "  C:\\a  \n\n C:\\b\n\t\nD:\\c\n"
    assert launcher.parse_folder_lines(text) == ["C:\\a", "C:\\b", "D:\\c"]


def test_parse_folder_lines_empty():
    assert launcher.parse_folder_lines("\n  \n\t") == []


def test_cap_constant_is_six():
    assert launcher.MAX_EXPLORER_FOLDERS == 6


def test_handle_entry_empty_folders_returns_note():
    # Empty folders short-circuits before any Win32 call.
    note = launcher._handle_entry({"kind": "explorer", "folders": []}, {})
    assert note == "no folders configured"


if __name__ == "__main__":
    test_parse_folder_lines_strips_blanks_and_whitespace()
    test_parse_folder_lines_empty()
    test_cap_constant_is_six()
    test_handle_entry_empty_folders_returns_note()
    print("ok")
