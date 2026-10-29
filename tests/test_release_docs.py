import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import version  # noqa: E402


def test_releasing_is_version_free():
    text = (ROOT / "RELEASING.md").read_text(encoding="utf-8")
    assert "X.Y.Z" in text
    assert "--no-ff" in text and "git tag -a" in text
    assert re.search(r"\b0\.\d+\.\d+\b", text) is None


def test_readme_points_to_releasing():
    assert "RELEASING.md" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_readme_names_every_module():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for py in sorted(ROOT.glob("*.py")):
        assert py.name in readme, py.name


def test_changelog_has_current_version():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## v{version.VERSION}" in text.splitlines()


if __name__ == "__main__":
    test_releasing_is_version_free()
    test_readme_points_to_releasing()
    test_readme_names_every_module()
    test_changelog_has_current_version()
    print("ok")
