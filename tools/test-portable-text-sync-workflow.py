#!/usr/bin/env python3
"""Tests that the path filters of .github/workflows/portable-text-sync.yml list every input its steps read.

The workflow runs only when a listed path changes, so an input the filters do
not list can change alone without running the gate, and the breakage surfaces
later on an unrelated pull request (row 119). INPUTS is the authoritative
list; extend it and both paths blocks in the same change. The tests check:

1. both triggers carry exactly INPUTS, in order;
2. every script a workflow step runs is itself listed;
3. every path the fresh() fixture of tools/test-portable-text-release-date.sh
   copies from the checkout is covered by a filter entry;
4. every repository path the Python test files name in a REPO / "..." chain
   or in the FILES list of tools/test-instructions-page.py is covered;
5. every non-glob entry exists on disk (a glob entry's base folder must
   exist), so a typo cannot pass as coverage.

Residual: a path built at run time from a variable or from data is not
derived here (site-src/site.json names the page sources, which site-src/**
covers), and a new read added to a gate in a form these anchors do not parse
is caught only by the hermetic fixtures failing, not by this test. The paths
blocks are parsed by their exact indentation, so a reformat fails here, which
is the safe direction.

Usage:
  python3 -I tools/test-portable-text-sync-workflow.py
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "portable-text-sync.yml"
RELEASE_DATE_TEST = REPO_ROOT / "tools" / "test-portable-text-release-date.sh"
# The Python test files whose REPO / "..." chains name checkout inputs.
ANCHOR_FILES = (
    "tools/test-skill-release-date.py",
    "tools/test-skill-release-date-client.py",
    "tools/test-instructions-page.py",
)

# The filter entries, in the order the workflow lists them. Each comment names
# the line that reads the entry; a new input extends this tuple and both paths
# blocks of the workflow in the same change.
INPUTS = (
    "cleanlanguage/skills/cleanlanguage/SKILL.md",  # check-portable-text-sync.sh:119, build-portable-text.py:28
    "cleanlanguage/skills/cleanlanguage/references/**",  # check-portable-text-sync.sh:182, build-portable-text.py:29
    "cleanlanguage/skills/**",  # copied whole: test-portable-text-release-date.sh:54, test-skill-release-date.py:1266
    "site/downloads/cleanlanguage.md",  # check-portable-text-sync.sh:39, check-instructions-page.py:76
    "site/downloads/cleanlanguage-29k.md",  # check-portable-text-sync.sh:40
    "site/downloads/cleanlanguage-11k.md",  # check-portable-text-sync.sh:41
    "site/downloads/cleanlanguage-8k.md",  # check-portable-text-sync.sh:42
    "site/downloads/*.md",  # copied by glob: test-portable-text-release-date.sh:55
    "tools/build-portable-text.py",  # check-portable-text-sync.sh:197, 200, 206
    "tools/build-site.py",  # test-portable-text-release-date.sh:51, run by check-portable-text-sync.sh:198
    "tools/sitemap-config.json",  # test-portable-text-release-date.sh:51, read by build-site.py:777
    "site-src/**",  # test-portable-text-release-date.sh:56, read by build-site.py:833, 171, 860, 865, 888
    ".baseline/pin.toml",  # test-portable-text-release-date.sh:57, read by build-site.py:399
    "site/instructions/index.html",  # check-instructions-page.py:77, test-instructions-page.py:20
    "tools/portable-text-skill-source.sha256",  # check-portable-text-sync.sh:38, 209
    "tools/skill-version.py",  # check-portable-text-sync.sh:60
    "tools/skill-release-date.py",  # skill-release-date-client.py:147
    "tools/test-skill-release-date.py",  # workflow step
    "tools/skill-release-date-client.py",  # check-portable-text-sync.sh:84, 137, 146
    "tools/test-skill-release-date-client.py",  # workflow step
    "tools/check-release-checksum-live.py",  # test-skill-release-date-client.py:42, loaded at 493, 838, 851
    "tools/test-portable-text-release-date.sh",  # workflow step
    "tools/check-portable-text-sync.sh",  # workflow step
    "tools/check-instructions-page.py",  # workflow step
    "tools/check-inline-code.py",  # check-instructions-page.py:85, test-instructions-page.py:20
    "tools/test-instructions-page.py",  # workflow step
    "tools/test-portable-text-sync-workflow.py",  # workflow step (this test)
    ".gitattributes",  # checkout attributes change the bytes the byte-exact checks compare
    "**/.gitattributes",
    ".github/workflows/portable-text-sync.yml",
)

# Entries that need not exist in the checkout (no .gitattributes is the
# current, intended state).
ABSENT_OK = {".gitattributes", "**/.gitattributes"}


def glob_regex(pattern: str) -> re.Pattern:
    """A GitHub Actions paths glob: ** spans folders, * stays inside one."""
    parts = re.split(r"(\*\*|\*)", pattern)
    return re.compile("".join(".*" if p == "**" else "[^/]*" if p == "*" else re.escape(p) for p in parts) + r"\Z")


FILTERS = [glob_regex(entry) for entry in INPUTS]


def covered(path: str) -> bool:
    """A file is covered when an entry matches it; a folder when an entry matches a new file inside it."""
    probe = path + "/probe.md" if (REPO_ROOT / path).is_dir() else path
    return any(f.match(probe) for f in FILTERS)


def workflow_paths() -> list[list[str]]:
    blocks, current = [], None
    for line in WORKFLOW.read_text(encoding="utf-8").splitlines():
        if line == "    paths:":
            current = []
            blocks.append(current)
        elif current is not None and line.startswith('      - "') and line.endswith('"'):
            current.append(line[len('      - "'):-1])
        else:
            current = None
    return blocks


def fresh_copies() -> list[str]:
    """Each path fresh() copies from the checkout, derived from its own text."""
    lines = RELEASE_DATE_TEST.read_text(encoding="utf-8").splitlines()
    start = lines.index("fresh() {")
    end = lines.index("}", start)
    body = "\n".join(lines[start:end])
    loop = re.search(r"for t in (.*?); do", body, re.S)
    found = ["tools/" + name for name in loop.group(1).replace("\\", " ").split()]
    found += [m.group(1) for m in re.finditer(r'cp -[pR] "\$\{repo_root\}"?/([^" ]+)', body)
              if "$" not in m.group(1)]
    return found


def anchor_paths() -> list[tuple[str, str]]:
    """(path, file) for each checkout path the anchor files name."""
    chain = re.compile(r'\bREPO(?:_ROOT)?((?:\s*/\s*"[^"]+")+)')
    found = []
    for relative in ANCHOR_FILES:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        for match in chain.finditer(text):
            found.append(("/".join(re.findall(r'"([^"]+)"', match.group(1))), relative))
        files_list = re.search(r"^FILES = \[(.*?)\]", text, re.S | re.M)
        if files_list:
            found += [(item, relative) for item in re.findall(r'"([^"]+)"', files_list.group(1))]
    return [(p, w) for p, w in found if (REPO_ROOT / p).exists()]


class FilterTests(unittest.TestCase):
    def test_both_triggers_list_exactly_the_inputs(self):
        blocks = workflow_paths()
        self.assertEqual(len(blocks), 2, "expected a paths list under pull_request and under push")
        for block in blocks:
            self.assertEqual(block, list(INPUTS))

    def test_every_step_script_is_listed(self):
        runs = [line.split("run:", 1)[1] for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith("run:")]
        scripts = [m.group(0) for run in runs for m in re.finditer(r"tools/[\w.-]+", run)]
        self.assertEqual(len(scripts), len(runs), "each step runs one script under tools/")
        for script in scripts:
            with self.subTest(script):
                self.assertIn(script, INPUTS)

    def test_fresh_copies_are_covered(self):
        copies = fresh_copies()
        self.assertGreaterEqual(len(copies), 12, "fresh() was not parsed")
        for path in copies:
            with self.subTest(path):
                self.assertTrue(covered(path), f"fresh() copies {path}, which the paths filters do not list")

    def test_python_test_anchors_are_covered(self):
        anchors = anchor_paths()
        self.assertGreaterEqual(len(anchors), 8, "the anchor files were not parsed")
        for path, where in anchors:
            with self.subTest(path=path, where=where):
                self.assertTrue(covered(path), f"{where} names {path}, which the paths filters do not list")

    def test_listed_files_exist(self):
        for entry in INPUTS:
            if entry in ABSENT_OK:
                continue
            with self.subTest(entry):
                if entry.endswith("/**"):
                    self.assertTrue((REPO_ROOT / entry[:-3]).is_dir(), f"{entry} has no base folder")
                elif "*" not in entry:
                    self.assertTrue((REPO_ROOT / entry).is_file(), f"{entry} does not exist")

    def test_the_glob_reading_matches_github(self):
        self.assertTrue(covered("site-src/pages/new.html"))
        self.assertTrue(covered("site/downloads/new.md"))
        self.assertTrue(covered("cleanlanguage/skills/cleanlanguage/new-file.txt"))
        self.assertFalse(covered("site/downloads/sub/new.md"))
        self.assertFalse(covered("tools/new-tool.py"))


if __name__ == "__main__":
    unittest.main()
