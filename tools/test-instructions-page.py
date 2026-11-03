#!/usr/bin/env python3
"""Tests for tools/check-instructions-page.py on the live page and the template page under /draft/.

Each case copies the gate and the files it reads into a temporary repository
(under $TMPDIR), applies 1 fault, runs the gate there as a separate process and
asserts its exit code. Exit 0 when every case passes; 1 otherwise.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tools" / "check-instructions-page.py"
LIVE = "site/instructions/index.html"
DRAFT = "site/draft/instructions/index.html"
FILES = ["site/downloads/cleanlanguage.md", LIVE, DRAFT, "tools/check-inline-code.py"]
BUTTON = '<button class="copy" type="button" data-copy="instructions-text" hidden>Copy</button>'


def make_root(scratch: Path) -> Path:
    root = scratch / "repo"
    (root / "tools").mkdir(parents=True)
    shutil.copyfile(GATE, root / "tools" / GATE.name)
    for relative in FILES:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, root / relative)
    return root


def edit(relative: str, old: str, new: str):
    def apply(root: Path) -> None:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise AssertionError(f"{old!r} is not in {relative}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return apply


CASES = [
    ("the committed tree", None, 0),
    ("1 character changed in the draft block", edit(DRAFT, "Apply the precedence order", "Apply the precedence orders"), 1),
    ("1 character changed in the live block", edit(LIVE, "Apply the precedence order", "Apply the precedence orders"), 1),
    ("the draft copy button removed", edit(DRAFT, BUTTON, ""), 1),
    ("the draft copy button shown", edit(DRAFT, BUTTON, BUTTON.replace(" hidden", "")), 1),
    ("markup added inside the draft block", edit(DRAFT, BUTTON, BUTTON + "<span>x</span>"), 1),
    ("a second copy button in the draft block", edit(DRAFT, BUTTON, BUTTON + BUTTON), 1),
    ("an inline script on the draft page", edit(DRAFT, "</main>", "<script>x()</script></main>"), 1),
    ("an inline style on the draft page", edit(DRAFT, "<h1>", '<h1 style="x">'), 1),
    ("I5: an application/x-javascript script on the live page",
        edit(LIVE, "</main>", '<script type="application/x-javascript">alert(1)</script></main>'), 1),
    ("I2B: src= inside another attribute's quoted value on the live page",
        edit(LIVE, "</main>", "<script title='src=\"/install/\"'>alert(1)</script></main>"), 1),
    ("I3: an event handler after a slash on the draft page",
        edit(DRAFT, "</main>", '<span/onclick="alert(1)">x</span></main>'), 1),
    ("I4: a javascript: link on the live page", edit(LIVE, "</main>", '<a href="javascript:alert(1)">x</a></main>'), 1),
    ("the inline-code gate missing", lambda root: (root / "tools/check-inline-code.py").unlink(), 3),
    ("the draft page missing", lambda root: (root / DRAFT).unlink(), 3),
    ("a second block on the draft page", edit(DRAFT, "</main>", '<pre id="instructions-text">x</pre></main>'), 3),
]


def main() -> int:
    failures: list[str] = []
    for name, fault, expected in CASES:
        with tempfile.TemporaryDirectory() as scratch:
            root = make_root(Path(scratch))
            if fault:
                fault(root)
            result = subprocess.run([sys.executable, "-I", str(root / "tools" / GATE.name)], capture_output=True, text=True)
            if result.returncode != expected:
                failures.append(f"{name}: exit {result.returncode}, expected {expected}: {(result.stdout + result.stderr).strip()[:300]}")
    if failures:
        print("test-instructions-page: failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"test-instructions-page: all {len(CASES)} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
