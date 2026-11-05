"""Offline checks for check_install.py (no network): python -m pytest test_check_install.py"""

import urllib.error
from pathlib import Path

import pytest
from packaging.requirements import Requirement

import check_install as ci


def release(requires_python: str | None, *files: str) -> dict:
    return {"info": {"requires_python": requires_python}, "urls": [{"filename": f} for f in files]}


ALL_PLATFORMS = ("x-1.0-cp312-cp312-win_amd64.whl", "x-1.0-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
                 "x-1.0-cp312-cp312-macosx_11_0_arm64.whl")


def test_promised_minors_follow_requires_python():
    assert ci.promised_minors(">=3.11") == [11, 12, 13, 14, 15]
    assert ci.promised_minors(">=3.10,<3.12") == [10, 11]
    assert ci.promised_minors("") == list(ci.KNOWN_MINORS)


def test_a_release_whose_requires_python_excludes_the_minor_is_no():
    # the motivating case: README said 3.11+, but scipy 1.18.1 needs 3.12
    assert ci.verdict(release(">=3.12", *ALL_PLATFORMS), 11) == "NO"
    assert ci.verdict(release(">=3.12", *ALL_PLATFORMS), 12) == "OK"


def test_an_unreadable_requires_python_counts_as_supported():
    assert ci.verdict(release("not a specifier", *ALL_PLATFORMS), 12) == "OK"


def test_wheels_for_every_platform_are_ok_and_a_missing_platform_with_an_sdist_is_src():
    assert ci.verdict(release(None, *ALL_PLATFORMS), 12) == "OK"
    assert ci.verdict(release(None, *ALL_PLATFORMS[:2], "x-1.0.tar.gz"), 12) == "SRC"


def test_a_missing_platform_without_an_sdist_is_no():
    assert ci.verdict(release(None, *ALL_PLATFORMS[:2]), 12) == "NO"


def test_a_wheel_for_another_minor_does_not_count():
    assert ci.verdict(release(None, *ALL_PLATFORMS), 13) == "NO"


@pytest.mark.parametrize(("filename", "minor", "platform", "fits"), [
    ("p-1-py3-none-any.whl", 9, "win", True),
    ("p-1-py2.py3-none-any.whl", 13, "linux", True),
    ("p-1-cp39-abi3-win_amd64.whl", 13, "win", True),        # stable ABI works on later minors
    ("p-1-cp313-abi3-win_amd64.whl", 13, "win", True),       # ... and on its own minor
    ("p-1-cp314-abi3-win_amd64.whl", 13, "win", False),      # but not on earlier ones
    ("p-1-cp313-cp313t-win_amd64.whl", 13, "win", False),    # free-threaded build only
    ("p-1-cp313-cp313-win32.whl", 13, "win", False),         # 32-bit Windows
    ("p-1-cp313-cp313-musllinux_1_2_x86_64.whl", 13, "linux", False),   # Alpine, not glibc Linux
    ("p-1-cp313-cp313-manylinux_2_17_aarch64.whl", 13, "linux", False),  # ARM Linux
    ("p-1-cp313-cp313-manylinux2014_i686.whl", 13, "linux", False),      # 32-bit Linux
    ("p-1-cp313-cp313-manylinux1_x86_64.whl", 13, "linux", True),
    ("p-1-cp313-cp313-macosx_10_13_x86_64.whl", 13, "mac", False),       # Intel-only Mac wheel
    ("p-1-cp313-cp313-macosx_10_13_universal2.whl", 13, "mac", True),
    ("p-1-cp313-cp313-macosx_11_0_arm64.whl", 13, "win", False),         # wrong platform
    ("p-1.0-1build-cp313-cp313-win_amd64.whl", 13, "win", True),         # with a build tag
])
def test_wheel_fits_reads_python_abi_and_platform_tags(filename, minor, platform, fits):
    assert ci.wheel_fits(filename, minor, ci.PLATFORMS[platform]) is fits


def test_read_pins_takes_exact_pins_and_warns_about_what_it_skips(tmp_path: Path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.12"\ndependencies = ["a==1.0", "b>=2", "w==1.*"]\n'
        '[project.optional-dependencies]\ndev = ["c==3.0"]\n', encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("# comment\nd==4.0  # pinned\n-e .\nA==1.0\nnot a pin!!\n",
                                               encoding="utf-8")
    requires_python, pins = ci.read_pins(tmp_path)
    assert requires_python == ">=3.12"
    assert sorted(str(p) for p in pins) == ["a==1.0", "c==3.0", "d==4.0"]  # b loose, w wildcard, A duplicate
    err = capsys.readouterr().err
    assert "wildcard pin not checked: w==1.*" in err and "not a valid requirement, skipped: not a pin!!" in err


@pytest.mark.parametrize(("text", "flagged"), [
    ("Needs Python 3.11 or newer.", True),
    ("Works on python 3.11+", True),
    ("Requires python>=3.10", True),
    ("Not supported on Python 3.8; tested on 3.9.", False),  # incidental mentions are not promises
    ("Needs Python 3.12 or newer.", False),
])
def test_readme_promising_an_older_python_is_a_mismatch(tmp_path: Path, text: str, flagged: bool):
    (tmp_path / "README.md").write_text(text, encoding="utf-8")
    assert (ci.readme_mismatch(tmp_path, [12, 13]) is not None) is flagged


def test_a_marker_for_older_pythons_does_not_apply_to_newer_ones():
    req = Requirement('tomli==2.0.1; python_version < "3.11"')
    assert ci.marker_applies(req, 10) and not ci.marker_applies(req, 12)


def project(tmp_path: Path, deps: str, readme: str = "") -> Path:
    (tmp_path / "pyproject.toml").write_text(f'[project]\nrequires-python = ">=3.12"\ndependencies = [{deps}]\n',
                                             encoding="utf-8")
    if readme:
        (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    return tmp_path


def fake_pypi(monkeypatch, releases: dict) -> None:
    def fetch(name: str, version: str):
        value = releases[f"{name}=={version}"]
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(ci, "fetch_release", fetch)


def wheels_for(minors: range) -> list[str]:
    return [f"x-1-cp3{m}-cp3{m}-{p}.whl" for m in minors
            for p in ("win_amd64", "manylinux_2_17_x86_64", "macosx_11_0_arm64")]


def test_main_passes_when_every_pin_installs(tmp_path: Path, monkeypatch):
    fake_pypi(monkeypatch, {"a==1.0": release(">=3.9", *wheels_for(range(12, 16)))})
    assert ci.main([str(project(tmp_path, '"a==1.0"'))]) == 0


def test_main_fails_on_a_no_cell_a_missing_release_or_a_readme_mismatch(tmp_path: Path, monkeypatch, capsys):
    fake_pypi(monkeypatch, {"a==1.0": release(">=3.13", *wheels_for(range(12, 16))), "b==2.0": None})
    assert ci.main([str(project(tmp_path, '"a==1.0", "b==2.0"', "Python 3.11 or newer"))]) == 1
    out = capsys.readouterr().out
    assert "3.12:NO" in out and "b==2.0" in out and "MISSING" in out and "BLOCKER: README.md promises" in out


def test_main_exits_2_when_pypi_is_unreachable(tmp_path: Path, monkeypatch, capsys):
    fake_pypi(monkeypatch, {"a==1.0": urllib.error.URLError("no network")})
    assert ci.main([str(project(tmp_path, '"a==1.0"'))]) == 2
    assert "PyPI unreachable while checking a" in capsys.readouterr().err


def test_main_exits_2_on_a_malformed_pyproject(tmp_path: Path, capsys):
    (tmp_path / "pyproject.toml").write_text("[project\n", encoding="utf-8")
    assert ci.main([str(tmp_path)]) == 2
    assert "cannot read the dependency files" in capsys.readouterr().err


def test_main_refuses_a_folder_without_dependency_files(tmp_path: Path, capsys):
    assert ci.main([str(tmp_path)]) == 2
    assert "no pyproject.toml or requirements" in capsys.readouterr().err
