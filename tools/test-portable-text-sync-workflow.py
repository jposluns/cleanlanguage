#!/usr/bin/env python3
"""Tests that .github/workflows/portable-text-sync.yml carries no path filter on either trigger.

The steps of that workflow read files across the repository, and a path list
cannot be kept complete against those reads, so the workflow runs on every
pull request and every push to main (row 119). This test fails if a paths or
paths-ignore filter comes back under either trigger.

That workflow runs this test, and so does workflow-isolation.yml, so a pull
request that adds a filter to that workflow which its own changed files fall
outside still runs it. The test also fails unless each workflow holds the
two lines of LAUNCH together exactly once, and fails if the triggers of
workflow-isolation.yml fail the checks below. It reads text, so a pull
request that filters both workflows away from its own files, or that skips
a launch with a step condition, is not caught; only review catches it.

It reads each file with a small line reader, not a YAML parser, and fails
closed. Blank lines and lines that hold only a comment are skipped. Every
other line at the left margin must be a plain key with no quotes; the
top-level keys must be exactly name, on, permissions and jobs, each once and
in that order; the on: line must be exactly on:; and the lines under it must
be exactly a bare pull_request trigger and a push trigger on main. A file
that cannot be read as UTF-8 text, or that holds a tab, a carriage return
(a CRLF line end included) or any other character outside printable ASCII,
also fails. So a filter in block form, in a flow mapping or behind a quoted
key fails, and so does any other change to the triggers, which is then made
in this test and the workflow together. YAML syntax is not checked: a value
outside on: that is not valid YAML passes here, and
tools/test-workflow-launch-isolation.py, which parses every workflow, fails
on it.

Usage:
  python3 -I tools/test-portable-text-sync-workflow.py
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "portable-text-sync.yml"
ISOLATION = REPO_ROOT / ".github" / "workflows" / "workflow-isolation.yml"

TOP_KEYS = ["name", "on", "permissions", "jobs"]
TRIGGERS = ["  pull_request:", "  push:", "    branches:", "      - main"]
TOP_LINE = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*):(?: .*)?")
LAUNCH = ["        shell: bash", "        run: python3 -I tools/test-portable-text-sync-workflow.py"]


def read(path: Path) -> str:
    """The workflow text, decoded from the bytes on disk so that a carriage return is kept.

    A file that cannot be read as UTF-8 raises ValueError.
    """
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise ValueError(f"cannot read {path}: {err}") from err


def launches(text: str) -> int:
    """How many times the two lines of LAUNCH stand together, each a whole line."""
    lines = text.split("\n")
    return sum(lines[i:i + 2] == LAUNCH for i in range(len(lines)))


def triggers(text: str) -> list[str]:
    """The lines under the on: key, less blank lines and comment lines.

    Raises ValueError for a character outside printable ASCII, an indented
    line before any top-level key, a line at the left margin that is not a
    plain key, a repeated top-level key, an on: line written any other way,
    or top-level keys other than name, on, permissions and jobs in that
    order. A filter under a trigger does not raise: its lines come back with
    the others, for the caller to compare. Past the printable ASCII check,
    nothing on or under the name, permissions and jobs lines is checked, and
    nor is the YAML syntax of any line.
    """
    blocks: dict[str, list[str]] = {}
    current = None
    for number, line in enumerate(text.split("\n"), 1):
        if re.search(r"[^\x20-\x7e]", line):
            raise ValueError(f"line {number} holds a character outside printable ASCII")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith(" "):
            if current is None:
                raise ValueError(f"line {number} is indented before any top-level key")
            blocks[current].append(line)
            continue
        key = TOP_LINE.fullmatch(line)
        if key is None:
            raise ValueError(f"line {number} is not a plain top-level key: {line}")
        current = key.group(1)
        if current in blocks:
            raise ValueError(f"line {number} repeats the top-level key {current}")
        if current == "on" and line != "on:":
            raise ValueError(f"line {number} is not written as on:")
        blocks[current] = []
    if list(blocks) != TOP_KEYS:
        raise ValueError(f"the top-level keys are {list(blocks)}, not {TOP_KEYS}")
    return blocks["on"]


def edited(text: str, old: str, new: str) -> str:
    if old not in text:
        raise AssertionError(f"{old!r} is not in the workflow")
    return text.replace(old, new, 1)


class TriggerTests(unittest.TestCase):
    def test_both_triggers_carry_no_filter(self):
        self.assertEqual(triggers(read(WORKFLOW)), TRIGGERS)

    def test_a_filter_under_either_trigger_fails(self):
        text = read(WORKFLOW)
        for old, new in (("  pull_request:\n", '  pull_request:\n    paths:\n      - "site-src/**"\n'),
                         ("  pull_request:\n", "  pull_request:\n    paths-ignore:\n      - docs/**\n"),
                         ("      - main\n", '      - main\n    paths:\n      - "tools/**"\n'),
                         ("      - main\n", "      - main\n    paths-ignore: [docs/**]\n"),
                         ("      - main\n", '      - main\n    "paths": ["tools/**"]\n'),
                         ("  pull_request:\n", "  pull_request: {paths: [tools/**]}\n")):
            with self.subTest(new):
                self.assertNotEqual(triggers(edited(text, old, new)), TRIGGERS)

    def test_a_commented_filter_is_skipped(self):
        text = edited(read(WORKFLOW), "  pull_request:\n", '  pull_request:\n    # paths:\n#     - "tools/**"\n')
        self.assertEqual(triggers(text), TRIGGERS)

    def test_an_unexpected_shape_fails(self):
        text = read(WORKFLOW)
        for old, new in (("on:\n", '"on":\n'), ("on:\n", "on: [pull_request, push]\n"),
                         ("on:\n", "on: # triggers\n"), ("permissions:\n", "on:\n  push:\npermissions:\n"),
                         ("permissions:\n", "On:\n  push:\npermissions:\n"), ("      - main\n", "\t- main\n"),
                         ("on:\n", "on:\r\n"), ("name:", "---\nname:")):
            with self.subTest(new), self.assertRaises(ValueError):
                triggers(edited(text, old, new))

    def test_an_unreadable_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.yml"
            bad.write_bytes(b"on: \xff\n")
            for path in (bad, Path(tmp) / "missing.yml"):
                with self.subTest(path.name), self.assertRaises(ValueError):
                    read(path)

    def test_a_carriage_return_on_disk_fails(self):
        text = read(WORKFLOW)
        with tempfile.TemporaryDirectory() as tmp:
            for name, ending in (("crlf.yml", "\r\n"), ("cr.yml", "\r")):
                path = Path(tmp) / name
                path.write_bytes(text.replace("\n", ending).encode("utf-8"))
                with self.subTest(name), self.assertRaises(ValueError):
                    triggers(read(path))


class LaunchTests(unittest.TestCase):
    def test_both_workflows_launch_this_test(self):
        for path in (WORKFLOW, ISOLATION):
            with self.subTest(path.name):
                self.assertEqual(launches(read(path)), 1)

    def test_workflow_isolation_carries_no_filter(self):
        self.assertEqual(triggers(read(ISOLATION)), TRIGGERS)

    def test_a_removed_or_altered_launch_fails(self):
        text, step = read(ISOLATION), "\n".join(LAUNCH)
        for old, new in ((LAUNCH[1] + "\n", ""), (step, "#" + step),
                         (LAUNCH[1], LAUNCH[1].replace(" -I", ""))):
            with self.subTest(new):
                self.assertEqual(launches(edited(text, old, new)), 0)


if __name__ == "__main__":
    unittest.main()
