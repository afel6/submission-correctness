"""Check that every exactly pinned dependency installs on every Python version the project promises.

usage: python check_install.py [REPO]        (REPO defaults to the current folder; needs Python 3.11+ and `packaging`)

Reads pyproject.toml ([project] requires-python, dependencies, optional-dependencies) and requirements*.txt, asks
PyPI about each `name==version` pin, and prints one row per pin with, for each promised CPython 3.x minor:
  OK   a wheel exists for Windows x64, Linux x86_64 (glibc) and Apple-silicon macOS
  SRC  some platform has only a source package: fine if pure Python, needs a compiler if not
  NO   that release does not support this Python, or cannot be installed on some platform (blocker)
  -    the requirement's environment marker excludes this Python (markers use this machine's OS)
A pin PyPI does not know (typo, removed release) is reported as MISSING (blocker). A README sentence that promises an
older Python ("Python 3.X or newer", "3.X+", ">=3.X") than requires-python is a blocker too.

Exit code: 0 no blockers, 1 at least one blocker, 2 bad input or PyPI unreachable.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet

# ponytail: CPython minors to consider; add the next one when it is released.
KNOWN_MINORS = range(8, 16)
PLATFORMS = {
    "win": re.compile(r"win_amd64"),
    "linux": re.compile(r"manylinux(1|2010|2014|_\d+_\d+)_x86_64"),
    "mac": re.compile(r"macosx_\d+_\d+_(arm64|universal2)"),
}
README_CLAIM = re.compile(r"python\s*(?:>=\s*)?3\.(\d+)\s*(?:\+|or\s+(?:newer|later|above|higher))"
                          r"|python\s*>=\s*3\.(\d+)", re.IGNORECASE)
PYPI = "https://pypi.org/pypi/{name}/{version}/json"


def promised_minors(requires_python: str) -> list[int]:
    """The CPython 3.x minors that ``requires_python`` allows (all known ones when it is empty)."""
    spec = SpecifierSet(requires_python)
    return [m for m in KNOWN_MINORS if spec.contains(f"3.{m}.0", prereleases=True)]


def exact_version(req: Requirement) -> str | None:
    """The version of an exact ``==`` pin (no wildcard), else None."""
    return next((s.version for s in req.specifier if s.operator == "==" and "*" not in s.version), None)


def requirement_lines(repo: Path) -> tuple[str, list[str]]:
    """requires-python and the raw requirement strings of pyproject.toml and requirements*.txt."""
    lines: list[str] = []
    requires_python = ""
    pyproject = repo / "pyproject.toml"
    if pyproject.is_file():
        project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
        requires_python = project.get("requires-python", "")
        lines += project.get("dependencies", [])
        for extra in project.get("optional-dependencies", {}).values():
            lines += extra
    for req_file in sorted(repo.glob("requirements*.txt")):
        for raw in req_file.read_text(encoding="utf-8").splitlines():
            text = raw.split("#", 1)[0].strip()
            if text and not text.startswith("-"):
                lines.append(text)
    return requires_python, lines


def read_pins(repo: Path) -> tuple[str, list[Requirement]]:
    """requires-python and every exact pin, once each; unreadable or unchecked lines are reported on stderr."""
    requires_python, lines = requirement_lines(repo)
    pins: dict[str, Requirement] = {}
    for line in lines:
        try:
            req = Requirement(line)
        except InvalidRequirement:
            print(f"warning: not a valid requirement, skipped: {line}", file=sys.stderr)
            continue
        version = exact_version(req)
        if version is None:
            if any(s.operator == "==" for s in req.specifier):
                print(f"warning: wildcard pin not checked: {line}", file=sys.stderr)
            continue
        pins.setdefault(f"{req.name.lower()}=={version}", req)
    return requires_python, list(pins.values())


def fetch_release(name: str, version: str) -> dict | None:
    """PyPI's JSON for one release, or None when PyPI has no such release (404)."""
    try:
        with urllib.request.urlopen(PYPI.format(name=name, version=version), timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def wheel_fits(filename: str, minor: int, platform: re.Pattern[str]) -> bool:
    """Whether wheel ``filename`` installs on CPython 3.``minor`` on the platform ``platform`` matches."""
    python_tags, abi_tag, platform_tags = filename[: -len(".whl")].split("-")[-3:]
    if platform_tags != "any" and not any(platform.fullmatch(tag) for tag in platform_tags.split(".")):
        return False
    if abi_tag.startswith("cp3") and abi_tag.endswith("t"):  # free-threaded build, a separate interpreter
        return False
    for tag in python_tags.split("."):
        if tag in ("py3", f"cp3{minor}"):
            return True
        if abi_tag == "abi3" and tag.startswith("cp3") and tag[3:].isdigit() and int(tag[3:]) <= minor:
            return True
    return False


def supports(requires_python: str, minor: int) -> bool:
    """Whether a release's requires_python allows CPython 3.``minor`` (an unreadable value counts as yes)."""
    try:
        return SpecifierSet(requires_python).contains(f"3.{minor}.0", prereleases=True)
    except InvalidSpecifier:
        return True


def verdict(release: dict, minor: int) -> str:
    """OK, SRC or NO for one release on CPython 3.``minor``."""
    if not supports(release["info"].get("requires_python") or "", minor):
        return "NO"
    files = [f["filename"] for f in release.get("urls", [])]
    wheels = [f for f in files if f.endswith(".whl")]
    if all(any(wheel_fits(w, minor, platform) for w in wheels) for platform in PLATFORMS.values()):
        return "OK"
    return "SRC" if any(not f.endswith(".whl") for f in files) else "NO"  # no wheel and no source: not installable


def readme_mismatch(repo: Path, minors: list[int]) -> str | None:
    """A message when README.md promises an older Python ("3.X or newer", "3.X+", ">=3.X") than requires-python."""
    readme = repo / "README.md"
    if not readme.is_file() or not minors:
        return None
    claimed = [int(a or b) for a, b in README_CLAIM.findall(readme.read_text(encoding="utf-8"))]
    older = sorted({m for m in claimed if m < minors[0]})
    if older:
        return f"README.md promises Python 3.{older[0]}, but requires-python starts at 3.{minors[0]}"
    return None


def marker_applies(req: Requirement, minor: int) -> bool:
    """Whether ``req``'s environment marker (if any) holds on CPython 3.``minor`` on this machine's OS."""
    if req.marker is None:
        return True
    env = {**default_environment(), "python_version": f"3.{minor}", "python_full_version": f"3.{minor}.0"}
    return req.marker.evaluate(env)


def pin_row(req: Requirement, minors: list[int]) -> tuple[str, int]:
    """One report row for ``req`` and its number of blocking cells."""
    version = exact_version(req) or ""
    label = f"{req.name + '==' + version:<34}"
    release = fetch_release(req.name, version)
    if release is None:
        return f"{label}MISSING: no such release on PyPI (typo or removed)", 1
    cells = [verdict(release, m) if marker_applies(req, m) else "-" for m in minors]
    return label + "  ".join(f"3.{m}:{c}" for m, c in zip(minors, cells, strict=True)), cells.count("NO")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    repo = Path(args[0] if args else ".")
    if not (repo / "pyproject.toml").is_file() and not any(repo.glob("requirements*.txt")):
        print(f"error: {repo}: no pyproject.toml or requirements*.txt here", file=sys.stderr)
        return 2
    try:
        requires_python, pins = read_pins(repo)
        minors = promised_minors(requires_python)
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError, InvalidSpecifier) as exc:
        print(f"error: cannot read the dependency files in {repo}: {exc}", file=sys.stderr)
        return 2
    if not minors:
        print(f"error: requires-python {requires_python!r} allows no known Python 3 version", file=sys.stderr)
        return 2
    print(f"requires-python: {requires_python or '(not set)'} -> checking 3.{minors[0]}..3.{minors[-1]}")
    blockers = 0
    for req in sorted(pins, key=lambda r: r.name.lower()):
        try:
            row, blocked = pin_row(req, minors)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"error: PyPI unreachable while checking {req.name}: {exc}", file=sys.stderr)
            return 2
        print(row)
        blockers += blocked
    mismatch = readme_mismatch(repo, minors)
    if mismatch:
        print(f"BLOCKER: {mismatch}")
        blockers += 1
    print(f"{blockers} blocker(s). NO/MISSING = not installable; SRC = source only (a compiler if not pure Python)")
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
