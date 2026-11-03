#!/usr/bin/env python3
"""Tests that the path filters of .github/workflows/portable-text-sync.yml list every input its steps read.

The workflow runs only when a listed path changes, so an input the filters do
not list can change alone without running the gate, and the breakage surfaces
later on an unrelated pull request (row 119). INPUTS is the authoritative
list; extend it and both paths blocks in the same change. The tests check:

1. the workflow's on: block is exactly a pull_request trigger and a push
   trigger on main, each with a paths list of exactly INPUTS, in order, so a
   line in any other form fails;
2. every entry uses only the pattern characters this test reads (no !, ?, [
   or +), so an exclusion or a class cannot pass as coverage;
3. every script a workflow step runs is itself listed, and so is every file
   this test reads;
4. every path tools/test-portable-text-release-date.sh names through
   repo_root, and every path its fresh() fixture copies, is covered, and a
   line of fresh() in a form this test does not read fails;
5. every repository path that a Python script the steps run, other than
   this test, names in a REPO / "..." chain is covered, and so is every
   item of the FILES list of tools/test-instructions-page.py, each a string
   or a name bound to one, whether or not the path exists;
6. every non-glob entry exists on disk and every glob entry matches a file
   in the checkout, so a typo cannot pass as coverage.

A source this test cannot read, a FILES item it cannot resolve, and a
derivation that finds fewer paths than its floor all fail.

Residual: a path built at run time from a variable or from data is not
derived here (site-src/site.json names the page sources, which site-src/**
covers), and neither is a read a gate makes in a form these anchors do not
parse, such as the os.path.join reads of tools/build-portable-text.py. The
hermetic fixtures catch such a read only when it fails on a file they did
not copy; an optional read, skipped when the file is absent, is caught by
neither. The shell scripts the steps run also launch python3 without -I in
places, for example tools/check-portable-text-sync.sh:60, 197, 200 and 206,
so a new file that such a launch finds on its module path, named after a
module it imports (tools/re.py beside those scripts, for example), is read
without being listed. Making those launches isolated is the separate
backlog row that tools/test-workflow-launch-isolation.py names among its
residuals, not this row.

Usage:
  python3 -I tools/test-portable-text-sync-workflow.py
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD = "tools/test-portable-text-sync-workflow.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "portable-text-sync.yml"
RELEASE_DATE_TEST = REPO_ROOT / "tools" / "test-portable-text-release-date.sh"
# The anchor file whose FILES list names the files it copies.
FILES_SOURCE = "tools/test-instructions-page.py"

# The filter entries, in the order the workflow lists them. Each comment names
# the line that reads the entry; a new input extends this tuple and both paths
# blocks of the workflow in the same change.
INPUTS = (
    "cleanlanguage/skills/cleanlanguage/SKILL.md",  # check-portable-text-sync.sh:119, build-portable-text.py:28
    "cleanlanguage/skills/cleanlanguage/references/**",  # check-portable-text-sync.sh:182, build-portable-text.py:29
    "cleanlanguage/skills/**",  # copied whole: test-skill-release-date.py:1266; its skill: release-date.sh:54
    "site/downloads/cleanlanguage.md",  # check-portable-text-sync.sh:39, check-instructions-page.py:76
    "site/downloads/cleanlanguage-29k.md",  # check-portable-text-sync.sh:40
    "site/downloads/cleanlanguage-11k.md",  # check-portable-text-sync.sh:41
    "site/downloads/cleanlanguage-8k.md",  # check-portable-text-sync.sh:42
    "site/downloads/*.md",  # copied by glob: test-portable-text-release-date.sh:55
    "tools/build-portable-text.py",  # check-portable-text-sync.sh:197, 200, 206
    "tools/build-site.py",  # test-portable-text-release-date.sh:51, run by check-portable-text-sync.sh:198
    "tools/sitemap-config.json",  # test-portable-text-release-date.sh:51, read by build-site.py:777
    "site-src/**",  # test-portable-text-release-date.sh:56, read by build-site.py:833, 170, 860, 865, 888
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
    ".github/workflows/portable-text-sync.yml",  # read by this test
)

# Entries that need not exist in the checkout (no .gitattributes is the
# current, intended state).
ABSENT_OK = {".gitattributes", "**/.gitattributes"}

# The pattern characters glob_regex reads; an entry with any other, such as !
# or ?, fails here rather than being misread.
ENTRY = re.compile(r"[\w.*/-]+")

# The lines of fresh() this test reads: the one loop and its copy, a copy of a
# literal checkout path, and the lines that copy nothing.
FRESH_LOOP = re.compile(r"for t in ([\w. -]+); do")
LOOP_COPY = 'cp -p "${repo_root}/tools/${t}" "${work}/tools/${t}"'
FRESH_COPY = re.compile(r'cp -[pR] "\$\{repo_root\}"?/([\w./*-]+)"? "\$\{work\}/[^"$]*"')
FRESH_OTHER = re.compile(r'|#.*|rm -rf "\$\{work\}"|mkdir -p( "\$\{work\}[^"$]*")+|local t|done')


def glob_regex(pattern: str) -> re.Pattern:
    """A GitHub Actions paths glob: ** spans folders, * stays inside one."""
    parts = re.split(r"(\*\*|\*)", pattern)
    return re.compile("".join(".*" if p == "**" else "[^/]*" if p == "*" else re.escape(p) for p in parts) + r"\Z")


def covered(path: str, entries: tuple[str, ...] = INPUTS) -> bool:
    """A file is covered when an entry matches it; a folder when an entry matches a new file inside it."""
    probe = path + "/probe.md" if (REPO_ROOT / path).is_dir() else path
    return any(glob_regex(entry).match(probe) for entry in entries)


def on_block(text: str) -> list[str]:
    """The lines of the workflow's one on: key, up to the next top-level line."""
    lines = text.splitlines()
    keys = [i for i, line in enumerate(lines) if re.match(r"""(["']?)on\1\s*:""", line)]
    if len(keys) != 1 or lines[keys[0]] != "on:":
        raise ValueError("expected one top-level trigger key, written as on:")
    block = []
    for line in lines[keys[0] + 1:]:
        if line and not line.startswith(" "):
            break
        block.append(line)
    while block and not block[-1]:
        block.pop()
    return block


def expected_on_block() -> list[str]:
    paths = ["    paths:"] + [f'      - "{entry}"' for entry in INPUTS]
    return ["  pull_request:"] + paths + ["  push:", "    branches:", "      - main"] + paths


def step_scripts() -> list[str]:
    """The script each workflow step runs."""
    runs = [line.split("run:", 1)[1] for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("run:")]
    scripts = [m.group(0) for run in runs for m in re.finditer(r"tools/[\w.-]+", run)]
    if not runs or len(scripts) != len(runs):
        raise ValueError("each step runs one script under tools/")
    return scripts


def own_sources() -> list[str]:
    """The files this test reads besides the step scripts."""
    return [path.relative_to(REPO_ROOT).as_posix() for path in (WORKFLOW, RELEASE_DATE_TEST)]


def fresh_copies(text: str) -> list[str]:
    """Each path fresh() copies from the checkout, derived from its own text."""
    lines = text.splitlines()
    start = lines.index("fresh() {")
    end = lines.index("}", start)
    found, loop = [], None
    for line in "\n".join(lines[start + 1:end]).replace("\\\n", " ").splitlines():
        line = line.strip()
        head, copy = FRESH_LOOP.fullmatch(line), FRESH_COPY.fullmatch(line)
        if head and loop is None:
            loop = head.group(1).split()
        elif line == LOOP_COPY and loop:
            found += ["tools/" + name for name in loop]
            loop = []
        elif copy:
            found.append(copy.group(1))
        elif not FRESH_OTHER.fullmatch(line) or (line == "done" and loop != []):
            raise ValueError(f"fresh() has a line this test does not read: {line}")
    return found


def repo_root_paths(text: str) -> list[str]:
    """Each literal checkout path the release-date test names through repo_root."""
    return [m.group(1) for m in re.finditer(r'\$\{?repo_root\}?"?/([^"\s;)]+)', text) if "$" not in m.group(1)]


def files_list(text: str, relative: str) -> list[str]:
    """The FILES list of an anchor file, each item a string or a name bound to one."""
    found = re.search(r"^FILES = \[(.*?)\]", text, re.S | re.M)
    if found is None:
        if relative == FILES_SOURCE:
            raise ValueError(f"{relative} has no FILES list")
        return []
    items = []
    for item in (part.strip() for part in found.group(1).split(",")):
        if not item:
            continue
        string = re.fullmatch(r'"([^"]+)"', item)
        bound = re.search(rf'^{item} = "([^"]+)"$', text, re.M) if item.isidentifier() else None
        if not (string or bound):
            raise ValueError(f"{relative} lists {item!r} in FILES, which this test cannot resolve")
        items.append((string or bound).group(1))
    return items


def anchor_paths(texts: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """(path, file) for each checkout path the Python scripts the steps run name."""
    chain = re.compile(r'\bREPO(?:_ROOT)?((?:\s*/\s*"[^"]+")+)')
    found = []
    for relative in [s for s in step_scripts() if s.endswith(".py") and s != GUARD]:
        text = (texts or {}).get(relative) or (REPO_ROOT / relative).read_text(encoding="utf-8")
        for match in chain.finditer(text):
            found.append(("/".join(re.findall(r'"([^"]+)"', match.group(1))), relative))
        found += [(item, relative) for item in files_list(text, relative)]
    return found


def checkout_files() -> list[str]:
    """Each file of the checkout outside .git, as a repository path."""
    paths = (p.relative_to(REPO_ROOT) for p in REPO_ROOT.rglob("*"))
    return [p.as_posix() for p in paths if p.parts[0] != ".git" and (REPO_ROOT / p).is_file()]


def matches_a_file(entry: str, files: list[str]) -> bool:
    return any(glob_regex(entry).match(f) for f in files)


class FilterTests(unittest.TestCase):
    def test_both_triggers_list_exactly_the_inputs(self):
        self.assertEqual(on_block(WORKFLOW.read_text(encoding="utf-8")), expected_on_block())

    def test_every_entry_is_a_form_this_test_reads(self):
        for entry in INPUTS:
            with self.subTest(entry):
                self.assertTrue(ENTRY.fullmatch(entry), f"{entry} uses a pattern character this test does not read")

    def test_every_step_script_is_listed(self):
        for script in step_scripts():
            with self.subTest(script):
                self.assertIn(script, INPUTS)

    def test_every_file_this_test_reads_is_covered(self):
        for relative in own_sources():
            with self.subTest(relative):
                self.assertTrue(covered(relative), f"this test reads {relative}, which the paths filters do not list")

    def test_fresh_copies_are_covered(self):
        copies = fresh_copies(RELEASE_DATE_TEST.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(copies), 12, "fresh() was not parsed")
        for path in copies:
            with self.subTest(path):
                self.assertTrue(covered(path), f"fresh() copies {path}, which the paths filters do not list")

    def test_release_date_test_paths_are_covered(self):
        paths = repo_root_paths(RELEASE_DATE_TEST.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(paths), 9, "the release-date test was not parsed")
        for path in paths:
            with self.subTest(path):
                self.assertTrue(covered(path), f"the release-date test reads {path}, which the filters do not list")

    def test_python_test_anchors_are_covered(self):
        anchors = anchor_paths()
        self.assertGreaterEqual(len(anchors), 13, "the anchor files were not parsed")
        for path, where in anchors:
            with self.subTest(path=path, where=where):
                self.assertTrue(covered(path), f"{where} names {path}, which the paths filters do not list")

    def test_listed_files_exist(self):
        files = checkout_files()
        for entry in INPUTS:
            if entry in ABSENT_OK:
                continue
            with self.subTest(entry):
                if "*" in entry:
                    self.assertTrue(matches_a_file(entry, files), f"{entry} matches no file in the checkout")
                else:
                    self.assertTrue((REPO_ROOT / entry).is_file(), f"{entry} does not exist")

    def test_the_glob_reading_matches_github(self):
        self.assertTrue(covered("site-src/pages/new.html"))
        self.assertTrue(covered("site/downloads/new.md"))
        self.assertTrue(covered("cleanlanguage/skills/cleanlanguage/new-file.txt"))
        self.assertFalse(covered("site/downloads/sub/new.md"))
        self.assertFalse(covered("tools/new-tool.py"))


def edited(text: str, old: str, new: str) -> str:
    if old not in text:
        raise AssertionError(f"{old!r} is not in the source")
    return text.replace(old, new, 1)


class RuleTests(unittest.TestCase):
    """Each rule above refuses the drift it was written for."""

    def test_an_unread_line_in_the_triggers_fails(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for old, new in (("  push:\n", "      - '!site-src/**'\n  push:\n"),
                         ("  push:\n", "  push:\n    paths-ignore:\n      - \"site-src/**\"\n"),
                         ("on:\n", "on:\n  workflow_dispatch:\n")):
            with self.subTest(new):
                self.assertNotEqual(on_block(edited(text, old, new)), expected_on_block())
        with self.assertRaises(ValueError):
            on_block(text + '"on":\n  push:\n')

    def test_an_exclusion_is_not_a_form_this_test_reads(self):
        for entry in ("!site-src/*.json", "site-src/[ab].json", "site-src/?.json", "tools/a+.py"):
            with self.subTest(entry):
                self.assertIsNone(ENTRY.fullmatch(entry))

    def test_this_tests_own_sources_need_an_entry(self):
        entries = tuple(entry for entry in INPUTS if not entry.startswith(".github/"))
        uncovered = [path for path in own_sources() if not covered(path, entries)]
        self.assertEqual(uncovered, [".github/workflows/portable-text-sync.yml"])

    def test_a_copy_in_another_form_fails(self):
        text = RELEASE_DATE_TEST.read_text(encoding="utf-8")
        site_src = '  cp -R "${repo_root}/site-src" "${work}/site-src"\n'
        for copy in ('cp -a "${repo_root}/README.md" "${work}/README.md"', 'cp "${repo_root}/README.md" "${work}/"',
                     'cp -pR "${repo_root}/README.md" "${work}/"', 'cp -p "$repo_root/README.md" "${work}/"'):
            with self.subTest(copy), self.assertRaises(ValueError):
                fresh_copies(edited(text, site_src, site_src + "  " + copy + "\n"))

    def test_a_second_loop_fails(self):
        text = RELEASE_DATE_TEST.read_text(encoding="utf-8")
        done = "  done\n"
        loop = '  for t in a.json; do\n    cp -a "${repo_root}/tools/${t}" "${work}/tools/${t}"\n  done\n'
        with self.assertRaises(ValueError):
            fresh_copies(edited(text, done, done + loop))

    def test_a_repo_root_read_outside_fresh_is_derived(self):
        text = RELEASE_DATE_TEST.read_text(encoding="utf-8") + 'cat "${repo_root}/README.md"\n'
        self.assertIn("README.md", repo_root_paths(text))
        self.assertFalse(covered("README.md"))

    def test_a_files_item_named_by_a_variable_is_derived(self):
        self.assertIn(("site/instructions/index.html", FILES_SOURCE), anchor_paths())

    def test_a_files_list_that_cannot_be_read_fails(self):
        text = (REPO_ROOT / FILES_SOURCE).read_text(encoding="utf-8")
        for old, new in (("PAGE, ", "str(GATE), "), ("PAGE, ", "MISSING, "), ("FILES = [", "COPIED = [")):
            with self.subTest(new), self.assertRaises(ValueError):
                anchor_paths({FILES_SOURCE: edited(text, old, new)})

    def test_a_named_path_that_does_not_exist_is_kept(self):
        line = 'MISSING = REPO_ROOT / "tools" / "absent-input.json"\n'
        text = (REPO_ROOT / FILES_SOURCE).read_text(encoding="utf-8") + line
        self.assertIn(("tools/absent-input.json", FILES_SOURCE), anchor_paths({FILES_SOURCE: text}))

    def test_a_glob_that_matches_no_file_fails(self):
        files = checkout_files()
        self.assertTrue(matches_a_file("site/downloads/*.md", files))
        self.assertFalse(matches_a_file("site/downloadds/*.md", files))
        self.assertFalse(matches_a_file("site/downloads/*.mdx", files))


if __name__ == "__main__":
    unittest.main()
