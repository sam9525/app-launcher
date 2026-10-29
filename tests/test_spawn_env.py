"""Spawned apps must not inherit the frozen exe's _MEI Tcl/Tk paths."""

import pathlib
import sys
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import launcher

MEI = r"C:\Users\me\AppData\Local\Temp\_MEI12345"
TERMINAL = {"name": "Shell", "kind": "terminal", "workdir": r"C:\work"}


def _spawn_env(environ: dict, meipass: str | None) -> dict:
    with mock.patch.dict("os.environ", environ, clear=True), mock.patch.object(
        sys, "_MEIPASS", meipass, create=True
    ), mock.patch("subprocess.Popen") as popen:
        launcher._spawn(TERMINAL)
    return popen.call_args.kwargs["env"]


def test_mei_tcl_tk_paths_removed():
    env = _spawn_env(
        {
            "PATH": r"C:\Windows",
            "TCL_LIBRARY": MEI + r"\_tcl_data",
            "TK_LIBRARY": MEI + r"\_tk_data",
        },
        MEI,
    )
    assert "TCL_LIBRARY" not in env
    assert "TK_LIBRARY" not in env
    assert env["PATH"] == r"C:\Windows"


def test_user_tcl_path_kept():
    env = _spawn_env({"TCL_LIBRARY": r"C:\Tcl\lib\tcl8.6"}, MEI)
    assert env["TCL_LIBRARY"] == r"C:\Tcl\lib\tcl8.6"


def test_from_source_env_untouched():
    env = _spawn_env({"TCL_LIBRARY": MEI + r"\_tcl_data"}, None)
    assert env["TCL_LIBRARY"] == MEI + r"\_tcl_data"


if __name__ == "__main__":
    test_mei_tcl_tk_paths_removed()
    test_user_tcl_path_kept()
    test_from_source_env_untouched()
    print("ok")
