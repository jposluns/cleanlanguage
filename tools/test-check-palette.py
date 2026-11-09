#!/usr/bin/env python3
"""Tests for tools/check-palette.py: the pinned palette gate and its wrapper.

Each case runs the wrapper as a separate process and asserts its exit code. The
first runs it on this repository and applies no change. Each other case copies
the wrapper and the files it reads into a temporary repository (under $TMPDIR)
and runs it there: the case named "the committed tree" applies no change, the 4
cases that copy the palettes to site/draft/ each apply 3 mutation functions
through both(...), and every other case applies 1 mutation function, which may
edit several places. An uncaught exception in the wrapper, or in the pinned
gate whose exit status the wrapper returns, also ends the wrapper with exit 1,
so each case that expects exit 1 also requires a text that the wrapper or the
pinned gate prints on stdout for that refusal. Each case that expects exit 3
also requires stderr to start with "check-palette: ", the prefix of the line
the wrapper prints when it cannot read an input, and to hold a text that only
its own refusal prints there, so that the case fails when the wrapper exits 3
for another reason. The cases that change the base in site-src/site.json check
that the wrapper reads the output root from it. Base / reads site/, so a
contrast failure only in a copy of the palettes under site/draft/ exits 0. Base
/draft/ reads site/draft/: a contrast failure in the copy there, with site/
clean, exits 1; a clean copy there, with the palettes under site/ removed,
exits 0; and a site-palette.css under site/draft/assets/, beside a clean copy
there and the clean palettes under site/, exits 1. An invalid base, a missing
base, a JSON list and invalid JSON each exit 3. The pinned gate also reads the
baseline.css beside the palettes, so the copies carry it, and a missing
baseline.css or one lacking a component token exits 1. The case named "the
pinned gate as a link to a byte-identical copy" exits 3: the wrapper refuses a
pinned gate that is not a regular file, even when the file that the link names
matches the pin. Exit 0 when every case passes; 1 otherwise, naming each
failing case.
"""

from __future__ import annotations

import json
import re
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
# From baseline 1.9.1 the pinned gate also reads the baseline.css beside the palettes it is given.
BASELINE_CSS = "site/assets/baseline/baseline.css"
SITE_JSON = "site-src/site.json"
FILES = [TOOL, PIN, PALETTES, BASELINE_CSS, SITE_JSON]
# The palettes of the output root at base /draft/, and the baseline.css beside them.
DRAFT_PALETTES = "site/draft/assets/baseline/palettes.css"
DRAFT_BASELINE_CSS = "site/draft/assets/baseline/baseline.css"
MISSING = object()


def make_root(scratch: Path) -> Path:
    root = scratch / "repo"
    (root / "tools").mkdir(parents=True)
    shutil.copyfile(WRAPPER, root / "tools" / WRAPPER.name)
    for relative in FILES:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, root / relative)
    return root


def run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-I", str(root / "tools" / WRAPPER.name)],
                          capture_output=True, text=True)


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


def link_tool(root: Path) -> None:
    """A link to a byte-identical copy of the pinned gate: the digest matches, so only the regular-file check refuses it."""
    path = root / TOOL
    copy = path.with_name("check_palette_copy.py")
    shutil.copyfile(path, copy)
    path.unlink()
    path.symlink_to(copy.name)


def dark_text_muted_on_bg(root: Path, palettes: str = PALETTES) -> None:
    """Replace every "--text-muted: X;" in palettes, in any rule, with "--text-muted: B;": a real contrast failure.

    X and B are the first --text-muted and --bg values from the start of this site's first dark rule,
    .site-cleanlanguage:not([data-scheme="light"]) {.
    """
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
    shutil.copyfile(root / BASELINE_CSS, root / DRAFT_BASELINE_CSS)


def remove_site_palettes(root: Path) -> None:
    (root / PALETTES).unlink()


def remove_baseline_css(root: Path) -> None:
    (root / BASELINE_CSS).unlink()


def drop_component_token(root: Path) -> None:
    """Remove the one declaration of the component token --th-rule from baseline.css."""
    path = root / BASELINE_CSS
    text = path.read_text(encoding="utf-8")
    found = re.findall(r" ?--th-rule: [^;]*;", text)
    if len(found) != 1:
        raise AssertionError(f"{BASELINE_CSS} does not declare --th-rule exactly once")
    path.write_text(text.replace(found[0], "", 1), encoding="utf-8")


def both(*faults):
    def apply(root: Path) -> None:
        for fault in faults:
            fault(root)
    return apply


# An uncaught exception in the wrapper, or in the pinned gate whose exit status the wrapper returns, also ends the
# wrapper with exit 1, so every case that expects exit 1 adds a 4th item: text that the wrapper or the pinned gate
# prints on stdout for that refusal. The wrapper prints each refusal that exits 3 as 1 stderr line with this prefix,
# so a case that expects exit 3 requires stderr to start with it and adds a 4th item: text that only its own refusal
# prints on stderr.
UNREADABLE = "check-palette: "
# The pinned gate's contrast matrix row for --text-muted, in its format of a 12-column name and 14-column cells,
# when the first cell, on --bg, is the same colour: a ratio of 1.00:1, below its 4.5:1 threshold. The gate prints a
# ratio only for a pairing of 2 set tokens, so an unset token, which also makes its summary report a failure, never
# prints this.
CONTRAST_FAILED = f"{'text-muted':<12} {'1.00:1 FAIL':>14}"


def bad_base(shown: str) -> str:
    return f"{SITE_JSON} base {shown} must be / or a single folder such as /draft/"


CASES = [
    ("the committed tree", None, 0),
    ("the pinned gate with a harmless edit", edit_tool, 1,
        f"check-palette: {TOOL} differs from its pinned digest"),
    ("the pinned gate's pin entry removed", drop_pin_entry, 3, f"{PIN} does not pin {TOOL} with a lower-case sha256"),
    ("the pinned gate deleted", delete_tool, 3, f"{TOOL} could not be read: [Errno 2] "),
    ("the pinned gate as a link to a byte-identical copy", link_tool, 3, f"{TOOL} is not a regular file"),
    ("dark --text-muted set to the dark --bg", dark_text_muted_on_bg, 1, CONTRAST_FAILED),
    ("a site-palette.css under site/assets/", plant_site_palette, 1,
        "check-palette: site/assets/site-palette.css exists"),
    ("baseline.css missing beside the palettes", remove_baseline_css, 1, "/baseline.css: [Errno 2] "),
    ("baseline.css lacking a component token", drop_component_token, 1,
        "FAIL cleanlanguage / light: --th-rule is not set"),
    ("base / with a contrast failure only under site/draft/", both(
        set_base("/"), copy_palettes_to_draft, lambda root: dark_text_muted_on_bg(root, DRAFT_PALETTES)), 0),
    ("base /draft/ with a contrast failure only under site/draft/", both(
        set_base("/draft/"), copy_palettes_to_draft, lambda root: dark_text_muted_on_bg(root, DRAFT_PALETTES)), 1,
        CONTRAST_FAILED),
    ("base /draft/ with clean palettes only under site/draft/",
        both(set_base("/draft/"), copy_palettes_to_draft, remove_site_palettes), 0),
    ("base /draft/ with a site-palette.css under site/draft/assets/", both(
        set_base("/draft/"), copy_palettes_to_draft, lambda root: plant_site_palette(root, "site/draft/assets")), 1,
        "check-palette: site/draft/assets/site-palette.css exists"),
    ("base /Draft/", set_base("/Draft/"), 3, bad_base("'/Draft/'")),
    ("base draft/", set_base("draft/"), 3, bad_base("'draft/'")),
    ("base /a/b/", set_base("/a/b/"), 3, bad_base("'/a/b/'")),
    ("a base that is not a string", set_base(1), 3, bad_base("1")),
    ("no base", set_base(MISSING), 3, bad_base("None")),
    ("a site.json that holds a JSON list", write_site_json("[]\n"), 3,
        f"{SITE_JSON} is not a JSON object with a base: 'list' object has no attribute 'get'"),
    ("a site.json that is not valid JSON", write_site_json("{\n"), 3,
        f"{SITE_JSON} is not a JSON object with a base: Expecting property name enclosed in double quotes"),
]


def tail(result: subprocess.CompletedProcess[str]) -> str:
    """The last 300 characters of the wrapper's stdout and stderr, with each run of white space collapsed."""
    return " ".join((result.stdout + result.stderr).split())[-300:]


def main() -> int:
    failures: list[str] = []
    ran = 0
    result = run(REPO_ROOT)
    ran += 1
    if result.returncode != 0:
        failures.append(f"this repository: exit {result.returncode}, expected 0: {tail(result)}")
    for name, fault, expected, *says in CASES:
        if expected in (1, 3) and not says:
            failures.append(f"{name}: expects exit {expected} but names no text for its refusal")
            continue
        stream = "stderr" if expected == 3 else "stdout"
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            if fault:
                fault(root)
            result = run(root)
            ran += 1
            shown = result.stderr if expected == 3 else result.stdout
            if (result.returncode != expected or not all(text in shown for text in says)
                    or (expected == 3 and not result.stderr.startswith(UNREADABLE))):
                wanted = "".join(f" with {text!r} on {stream}" for text in says)
                if expected == 3:
                    wanted += f" with stderr starting {UNREADABLE!r}"
                failures.append(f"{name}: exit {result.returncode}, expected {expected}{wanted}: {tail(result)}")
    if failures:
        print("test-check-palette: failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"test-check-palette: all {ran} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
