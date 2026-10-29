import pathlib
import sys
import unittest.mock as mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app_index import resolve


def test_resolve_empty_returns_none():
    assert resolve("") is None
    assert resolve("   ") is None


@mock.patch("app_index.winreg.OpenKey")
@mock.patch("app_index.os.walk")
def test_resolve_nonsense_returns_none_no_raise(mock_walk, mock_open):
    # A name that matches nothing must return None, never raise.
    mock_open.side_effect = OSError()
    mock_walk.return_value = []
    assert resolve("zzz_no_such_app_xyzzy_98765") is None


@mock.patch("app_index.winreg.OpenKey")
@mock.patch("app_index.winreg.EnumKey")
@mock.patch("app_index.winreg.QueryValueEx")
@mock.patch("app_index.os.path.exists")
def test_resolve_chrome_app_paths(mock_exists, mock_query_val, mock_enum, mock_open):
    # Mocking EnumKey to return 'chrome.exe' on index 0, then raise OSError
    def enum_side_effect(key, index):
        if index == 0:
            return "chrome.exe"
        raise OSError()

    mock_enum.side_effect = enum_side_effect

    # Mocking QueryValueEx to return path with double quotes
    mock_query_val.return_value = (
        '"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"',
        1,
    )

    # Mocking exists to return True for the expected path
    def exists_side_effect(p):
        return p == "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"

    mock_exists.side_effect = exists_side_effect

    # OpenKey returns mock key objects
    mock_app_paths_key = mock.MagicMock()
    mock_sub_key = mock.MagicMock()

    def open_side_effect(root_or_key, subkey):
        if subkey == "chrome.exe":
            return mock_sub_key
        return mock_app_paths_key

    mock_open.side_effect = open_side_effect

    res = resolve("chrome")
    assert res == "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"

    res_exe = resolve("chrome.exe")
    assert res_exe == res


@mock.patch("app_index.winreg.OpenKey")
@mock.patch("app_index.pythoncom.CoInitialize")
@mock.patch("app_index.win32com.client.Dispatch")
@mock.patch("app_index.os.walk")
@mock.patch("app_index.os.path.exists")
@mock.patch.dict(
    "os.environ",
    {"ProgramData": "C:\\ProgramData", "APPDATA": "C:\\Users\\User\\AppData\\Roaming"},
)
def test_resolve_vscode_start_menu(
    mock_exists, mock_walk, mock_dispatch, mock_coinit, mock_open
):
    # Make app paths return None
    mock_open.side_effect = OSError()

    # Mock os.walk to return the vs code shortcut file
    mock_walk.return_value = [
        (
            "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs",
            [],
            ["Visual Studio Code.lnk"],
        )
    ]

    # Mock dispatch and CreateShortcut
    mock_shell = mock.MagicMock()
    mock_shortcut = mock.MagicMock()
    mock_shortcut.TargetPath = "C:\\Program Files\\Microsoft VS Code\\Code.exe"
    mock_shell.CreateShortcut.return_value = mock_shortcut
    mock_dispatch.return_value = mock_shell

    # Mock exists
    mock_exists.side_effect = lambda p: (
        p == "C:\\Program Files\\Microsoft VS Code\\Code.exe"
    )

    res = resolve("Visual Studio Code")
    assert res == "C:\\Program Files\\Microsoft VS Code\\Code.exe"

    # Verify CoInitialize was called
    mock_coinit.assert_called_once()
    mock_dispatch.assert_called_once_with("WScript.Shell")
    mock_shell.CreateShortcut.assert_called_once_with(
        "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs"
        "\\Visual Studio Code.lnk"
    )


@mock.patch("app_index.winreg.OpenKey")
@mock.patch("app_index.winreg.EnumKey")
@mock.patch("app_index.winreg.QueryValueEx")
@mock.patch("app_index.os.path.exists")
@mock.patch.dict("os.environ", {"SOME_VAR": "C:\\MyFolder"})
def test_resolve_app_paths_env_expansion(
    mock_exists, mock_query_val, mock_enum, mock_open
):
    def enum_side_effect(key, index):
        if index == 0:
            return "my_app.exe"
        raise OSError()

    mock_enum.side_effect = enum_side_effect

    mock_query_val.return_value = (
        '"%SOME_VAR%\\my_app.exe"',
        1,
    )

    mock_exists.side_effect = lambda p: p == "C:\\MyFolder\\my_app.exe"

    mock_app_paths_key = mock.MagicMock()
    mock_sub_key = mock.MagicMock()
    mock_open.side_effect = lambda root, sub: (
        mock_sub_key if sub == "my_app.exe" else mock_app_paths_key
    )

    res = resolve("my_app")
    assert res == "C:\\MyFolder\\my_app.exe"


if __name__ == "__main__":
    test_resolve_empty_returns_none()
    test_resolve_nonsense_returns_none_no_raise()
    test_resolve_chrome_app_paths()
    test_resolve_vscode_start_menu()
    test_resolve_app_paths_env_expansion()
    print("test_app_index OK")
