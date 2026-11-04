#!/usr/bin/env python3
"""Tests for tools/check-palette.py: the pinned palette gate and its wrapper.

Each case copies the wrapper and the files it reads into a temporary repository
(under $TMPDIR), applies its changes, runs the wrapper there as a separate
process and asserts its exit code. The case named "the committed tree" applies
no change, the 4 cases that copy the palettes to site/draft/ each apply 3
through both(...), and every other case applies 1. The first case runs the
wrapper on this repository.
The cases that change the base in site-src/site.json check that the wrapper
reads the output root from it. Base / reads site/, so a contrast failure only
in a copy of the palettes under site/draft/ exits 0. Base /draft/ reads
site/draft/: a contrast failure in the copy there, with site/ clean, exits 1;
a clean copy there, with the palettes under site/ removed, exits 0; and a
site-palette.css under site/draft/assets/, beside a clean copy there and the
clean palettes under site/, exits 1. An invalid base, a missing base, a JSON
list and invalid JSON each exit 3.
Exit 0 when every case passes; 1 otherwise, naming each failing case.
"""

from __future__ import annotations

import json
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
SITE_JSON = "site-src/site.json"
FILES = [TOOL, PIN, PALETTES, SITE_JSON]
# The palettes of the output root at base /draft/.
DRAFT_PALETTES = "site/draft/assets/baseline/palettes.css"
MISSING = object()


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


def dark_text_muted_on_bg(root: Path, palettes: str = PALETTES) -> None:
    """Set the dark --text-muted of this site to its dark --bg, in every dark form: a real contrast failure."""
    path = root / palettes
    text = path.read_text(encoding="utf-8")
    block = text.index(".site-cleanlanguage:not([data-scheme=\"light\"]) {")
    bg = text[text.index("--bg: ", block) + 6:text.index(";", text.index("--bg: ", block))]
    muted = text[text.index("--text-muted: ", block) + 14:text.index(";", text.index("--text-muted: ", block))]
    old = f"--text-muted: {muted};"
    if old not in text or bg == muted:
        raise AssertionError("the dark --text-muted of cleanlanguage was not found")
    path.write_text(text.replace(old, f"--text-muted: {bg};"), encoding="utf-8")


def plant_site_palette(root: Path, assets: str = "site/assets") -> None:
    (root / assets / "site-palette.css").write_text(".site-cleanlanguage { --bg: #ffffff; }\n", encoding="utf-8")


def set_base(value):
    """Set the base in site-src/site.json to value, or remove it when value is MISSING."""
    def apply(root: Path) -> None:
        path = root / SITE_JSON
        site = json.loads(path.read_text(encoding="utf-8"))
        if value is MISSING:
            del site["base"]
        else:
            site["base"] = value
        path.write_text(json.dumps(site, indent=2) + "\n", encoding="utf-8")
    return apply


def write_site_json(text: str):
    return lambda root: (root / SITE_JSON).write_text(text, encoding="utf-8")


def copy_palettes_to_draft(root: Path) -> None:
    (root / DRAFT_PALETTES).parent.mkdir(parents=True)
    shutil.copyfile(root / PALETTES, root / DRAFT_PALETTES)


def remove_site_palettes(root: Path) -> None:
    (root / PALETTES).unlink()


def both(*faults):
    def apply(root: Path) -> None:
        for fault in faults:
            fault(root)
    return apply


CASES = [
    ("the committed tree", None, 0),
    ("the pinned gate with a harmless edit", edit_tool, 1),
    ("the pinned gate's pin entry removed", drop_pin_entry, 3),
    ("the pinned gate deleted", delete_tool, 3),
    ("dark --text-muted set to the dark --bg", dark_text_muted_on_bg, 1),
    ("a site-palette.css under site/assets/", plant_site_palette, 1),
    ("base / with a contrast failure only under site/draft/", both(
        set_base("/"), copy_palettes_to_draft, lambda root: dark_text_muted_on_bg(root, DRAFT_PALETTES)), 0),
    ("base /draft/ with a contrast failure only under site/draft/", both(
        set_base("/draft/"), copy_palettes_to_draft, lambda root: dark_text_muted_on_bg(root, DRAFT_PALETTES)), 1),
    ("base /draft/ with clean palettes only under site/draft/",
        both(set_base("/draft/"), copy_palettes_to_draft, remove_site_palettes), 0),
    ("base /draft/ with a site-palette.css under site/draft/assets/", both(
        set_base("/draft/"), copy_palettes_to_draft, lambda root: plant_site_palette(root, "site/draft/assets")), 1),
    ("base /Draft/", set_base("/Draft/"), 3),
    ("base draft/", set_base("draft/"), 3),
    ("base /a/b/", set_base("/a/b/"), 3),
    ("a base that is not a string", set_base(1), 3),
    ("no base", set_base(MISSING), 3),
    ("a site.json that holds a JSON list", write_site_json("[]\n"), 3),
    ("a site.json that is not valid JSON", write_site_json("{\n"), 3),
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
