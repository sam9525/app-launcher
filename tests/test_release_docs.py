import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import version  # noqa: E402


def test_readme_names_every_module():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for py in sorted(ROOT.glob("*.py")):
        assert py.name in readme, py.name


def test_changelog_has_current_version():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## v{version.VERSION}" in text.splitlines()


if __name__ == "__main__":
    test_readme_names_every_module()
    test_changelog_has_current_version()
    print("ok")
