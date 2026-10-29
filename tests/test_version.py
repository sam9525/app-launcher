import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import version  # noqa: E402


def test_version_is_dotted_ints():
    assert (
        all(p.isdigit() for p in version.VERSION.split("."))
        and version.VERSION.count(".") == 2
    )


def test_iss_has_no_hardcoded_version():
    iss = (ROOT / "installer" / "app-launcher.iss").read_text(encoding="utf-8")
    assert "AppVersion={#AppVersion}" in iss
    assert re.search(r"^AppVersion=\d", iss, re.M) is None
    assert "#error" in iss


def test_build_bat_passes_version():
    bat = (ROOT / "installer" / "build.bat").read_text(encoding="utf-8")
    assert "/DAppVersion=" in bat and "version" in bat.lower()


def test_build_bat_clears_tcl_tk_before_pyinstaller():
    bat = (ROOT / "installer" / "build.bat").read_text(encoding="utf-8")
    lines = [line.strip().lower() for line in bat.splitlines()]
    pyi = next(i for i, line in enumerate(lines) if line.startswith("pyinstaller"))
    for var in ("tcl_library", "tk_library"):
        assert f"set {var}=" in lines[:pyi], var


if __name__ == "__main__":
    test_version_is_dotted_ints()
    test_iss_has_no_hardcoded_version()
    test_build_bat_passes_version()
    test_build_bat_clears_tcl_tk_before_pyinstaller()
    print("test_version OK")
