#!/usr/bin/env python3
"""Tests for tools/check-palette.py: the pinned palette gate and its wrapper.

Each case copies the wrapper and the files it reads into a temporary repository
(under $TMPDIR), applies 1 fault, runs the wrapper there as a separate process
and asserts its exit code. The first case runs the wrapper on this repository.
Exit 0 when every case passes; 1 otherwise, naming each failing case.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER = REPO_ROOT / "tools" / "check-palette.py"
TOOL = ".baseline/check_palette.py"
PIN = ".baseline/pin.toml"
PALETTES = "site/assets/baseline/palettes.css"
FILES = [TOOL, PIN, PALETTES, "site-src/site.json"]


def make_root(scratch: Path) -> Path:
    root = scratch / "repo"
    (root / "tools").mkdir(parents=True)
    shutil.copyfile(WRAPPER, root / "tools" / WRAPPER.name)
    for relative in FILES:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, root / relative)
    return root


def run(root: Path) -> int:
    return subprocess.run([sys.executable, "-I", str(root / "tools" / WRAPPER.name)],
                          capture_output=True, text=True).returncode


def edit_tool(root: Path) -> None:
    """A harmless edit: the edited gate still runs and passes, so only the digest check can refuse it."""
    path = root / TOOL
    path.write_bytes(path.read_bytes() + b"# edited\n")


def drop_pin_entry(root: Path) -> None:
    path = root / PIN
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [line for line in lines if not line.startswith(f'"{TOOL}" = ')]
    if len(kept) != len(lines) - 1:
        raise AssertionError(f"{PIN} does not pin {TOOL} exactly once")
    path.write_text("".join(kept), encoding="utf-8")


def delete_tool(root: Path) -> None:
    (root / TOOL).unlink()


def dark_text_muted_on_bg(root: Path) -> None:
    """Set the dark --text-muted of this site to its dark --bg, in every dark form: a real contrast failure."""
    path = root / PALETTES
    text = path.read_text(encoding="utf-8")
    block = text.index(".site-cleanlanguage:not([data-scheme=\"light\"]) {")
    bg = text[text.index("--bg: ", block) + 6:text.index(";", text.index("--bg: ", block))]
    muted = text[text.index("--text-muted: ", block) + 14:text.index(";", text.index("--text-muted: ", block))]
    old = f"--text-muted: {muted};"
    if old not in text or bg == muted:
        raise AssertionError("the dark --text-muted of cleanlanguage was not found")
    path.write_text(text.replace(old, f"--text-muted: {bg};"), encoding="utf-8")


def plant_site_palette(root: Path) -> None:
    (root / "site" / "assets" / "site-palette.css").write_text(".site-cleanlanguage { --bg: #ffffff; }\n", encoding="utf-8")


CASES = [
    ("the committed tree", None, 0),
    ("the pinned gate with a harmless edit", edit_tool, 1),
    ("the pinned gate's pin entry removed", drop_pin_entry, 3),
    ("the pinned gate deleted", delete_tool, 3),
    ("dark --text-muted set to the dark --bg", dark_text_muted_on_bg, 1),
    ("a site-palette.css under site/assets/", plant_site_palette, 1),
]


def main() -> int:
    failures: list[str] = []
    ran = 0
    code = run(REPO_ROOT)
    ran += 1
    if code != 0:
        failures.append(f"this repository: exit {code}, expected 0")
    for name, fault, expected in CASES:
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            if fault:
                fault(root)
            code = run(root)
            ran += 1
            if code != expected:
                failures.append(f"{name}: exit {code}, expected {expected}")
    if failures:
        print("test-check-palette: failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"test-check-palette: all {ran} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
