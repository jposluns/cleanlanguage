#!/usr/bin/env python3
"""Tests for tools/check-plugin-distribution.py.

Each case builds a temporary tree that holds the files the gate reads, points
the gate's REPO_ROOT at it, as tools/test-agent-plugin-manifest.py points that
gate's paths at a fixture, and runs the gate's main; 1 case instead runs a
copy of the gate in the tree as a command, through subprocess. The
conforming tree must pass, also with a byte-order mark before a JSON file;
each case then changes 1 thing. Every case requires the exit status and the
last line: "OK:" for exit 0, "FAIL: " for exit 1 and "UNREADABLE: exit 3" on
standard error for exit 3. Every case that expects a failure also requires
its text, with the tag of its check as the gate's CHECKS holds it, except 2
cases that require of their failure only the exact last line: the count line
for 1 and for 2 inconsistencies, and "UNREADABLE: exit 3".

Every case that runs the gate's main through expect, and the command case,
also requires the lines of the exit status, split at every line break that
str.splitlines knows: for exit 1, 1 line "FAIL <tag>: " under 1 of the 4
tags for each inconsistency the count line names, then the line of counts
and the count line; for exit 0, the line of counts and the "OK:" line; for
exit 3, nothing on standard output, and on standard error the cause and
"UNREADABLE: exit 3". A main that lets any exception escape fails the case.
Loading the gate must not run it: a gate that raises, or runs its main,
while this test loads it stops the test with exit 1 before any case runs.
A symlinked source, .claude-plugin folder or manifest, a version that is
not a string and an empty version each require exactly 1 inconsistency, so
a refusal that adds a second line for the same fault fails.

- The names check fails on: the marketplace named jposluns; a plugin entry
  name that differs from the manifest name; a second plugin entry or none; a
  Claude or Agent Plugins manifest name or a site key that differs; a vendored
  entry named unlike the manifest it reaches; a marketplace name that is
  missing or empty; a marketplace name or a plugin entry name, in each
  marketplace, that starts with each reserved prefix, in lower case, upper
  case and title case, and with "anthropics-" spelled with a long s; each
  name and the site key that differ from cleanlanguage only in letter case;
  and, with the FAIL lines and the count line and no traceback, a plugin
  entry name that is an array or an object, a marketplace name that is an
  array where a qualified dependency reads it, and a manifest name that is
  an array where its entry and its own dependencies read it; a plugin
  name listed twice in the repository's marketplace and in the vendored
  one, there also in another letter case; in the vendored one, a
  marketplace name with a reserved prefix and a plugin name listed twice
  that are equal only under Unicode case folding (a long s); and, with no
  traceback, a repository marketplace whose plugins list is missing or is
  an object, or whose 1 entry is a string. 2 vendored entries named "" are
  2 names that are not names, and neither is a plugin listed twice.
- The sources check fails on: a missing source folder; a source with a "..",
  a "." or an empty component, the "." and the empty component in each
  marketplace; a source with a NUL character or with a character the file
  system encoding cannot hold, in each marketplace; a source with a
  component too long for the file system, in each marketplace; a source in
  each marketplace, a .claude-plugin folder or a manifest file name,
  spelled in another letter case on a file system that folds letter case,
  which the case imitates by giving the gate an os.lstat, an os.open and
  an os.listdir that fold letter case; a source without "./", an entry
  with no source and an object source, in each marketplace; a source that
  is a file; a manifest that is a directory; a symlinked source folder, a
  symlinked .claude-plugin folder or a symlinked manifest; a marketplace
  with no plugins list or with an entry that is not an object; and a source of the
  repository's entry that reaches another plugin or a copy of this one.
- The versions check fails on: a version that differs in the Claude
  manifest, the Agent Plugins manifest, the SKILL.md Version: line or a
  marketplace entry; a version that is missing, empty or not a string; a
  SKILL.md with no Version: line; and a SKILL.md whose first Version: line
  is not a bare X.Y.Z, alone or before a valid one. It passes on a SKILL.md
  whose lines end in CR LF or in a lone CR, and on a vendored entry whose
  version differs, is not a string or is empty, since those versions are
  not read.
- The dependencies check fails on: a dependency that names no plugin of its
  marketplace, is qualified with another marketplace or with an empty one
  (a name and "@" alone), or names the plugin itself, from an entry and from
  a plugin manifest of each marketplace, the plugin itself also from the
  repository's entry as a bare and as a qualified name; on a plugin that 1
  list names twice, from an entry and from a plugin manifest of each
  marketplace, as the same bare name, as a bare and a qualified name, or as
  a qualified and a bare name; on dependencies that are not a list, a JSON
  null in a marketplace entry and in a plugin manifest of each marketplace
  among them; and on a dependency that is not a name, an object or an
  empty string, from an entry and from a plugin manifest of each
  marketplace.
  Dependencies that
  resolve pass, among them 2 that a plugin entry holds on 2 other plugins of
  its marketplace, and 3 lists that each name the same plugin once.
- Exit 3 holds for: a repeated JSON key; a missing file; a file that is not a
  regular file; an input folder that is a file; an input file and a source
  folder that deny permission; an
  input folder and a source folder that can be searched but not listed
  (mode 0111); NaN; JSON nested 1 level deeper than the gate's bound of 64, which every
  supported Python decodes, in arrays and in objects, while JSON at the
  bound passes, in arrays with escaped quotes and brackets inside a string
  and in objects, and so does JSON nested 3 levels deep that holds more
  than 64 arrays, or more than 64 objects, in all; a JSON file that is not
  an object; a file or a SKILL.md that is not UTF-8; a symlinked input file
  or input folder; an input folder and an input file name spelled in
  another letter case on a file system that folds letter case, imitated as
  above; and an extractor that is missing, symlinked, raises an exception,
  SystemExit, BaseException, GeneratorExit or KeyboardInterrupt while it
  loads, also an exception whose message holds a line break or cannot be
  shown, lacks VERSION_LINE or SKILL_VERSION, holds
  either as a pattern of bytes, has a SKILL_VERSION with no group 1, or has
  one whose group 1 takes no part in its match. What an extractor prints to
  standard output and standard error while it loads is not in the output.
  An exception raised in the gate itself, outside the extractor, also gives
  exit 3 with 1 cause line and no traceback: a TypeError, a BaseException,
  KeyboardInterrupt and SystemExit, also one whose message holds a line
  break or cannot be shown. A missing input file gives its exact cause
  line. An OSError with no strerror, as one built by hand has, raised by
  os.lstat, os.listdir or os.open on an input or by os.fstat or os.read
  while one is read, and by os.lstat or os.listdir on a source folder, is
  shown by its message, and an input/output error while an input is read
  by its strerror, which the case imitates by giving the gate an os whose
  1 function raises it; with the errno of a name too long, on a source
  folder, an OSError with no strerror is a failure of the sources check,
  exit 1.
- A line break in a path or a name is written as an escape on its line, at
  each place one enters a line of output: a missing source in each
  marketplace, with each of LF, CR, VT, NEL and U+2028; a source that is a
  file, a symlinked source, a source in another letter case, a source of
  the repository's entry that reaches another manifest, the manifest path
  of a names failure and of a dependencies failure, and a source folder
  that denies permission or cannot be listed (on standard error); and a
  marketplace name, a name with a reserved prefix, a version, a dependency
  and the marketplace name a qualified dependency reads.
- Run as a command, the gate exits 0, 1 and 3 with the same last lines, and
  a missing source whose path holds a line break and a lone surrogate gives
  1 FAIL line, with both written as escapes.
- The count lines read "1 relative source", "1 dependency" and "FAIL: 1
  inconsistency" for 1, and the plural for 0 and for more than 1.

A last case runs the gate on the repository itself and requires exit 0 and a
last line "OK:", so this test fails while the repository's own names,
sources, versions or dependencies disagree.

The permission cases, those of mode 0111 among them, need a user whose
permissions the file system enforces, so they are skipped when the test
runs as root.

The SKILL.md version is read by a copy of the real tools/skill-version.py in
each tree, which the gate reaches from REPO_ROOT like every other file.

Usage: python3 -I tools/test-check-plugin-distribution.py
Exit status: 0 when every case passes, 1 otherwise.
"""

from __future__ import annotations

import contextlib
import errno
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parent / "check-plugin-distribution.py"
REAL_EXTRACTOR = Path(__file__).resolve().parent / "skill-version.py"
EXTRACTOR_REL = "tools/skill-version.py"
# Written out, not read from the gate, so a gate that drops a prefix fails.
RESERVED_PREFIXES = ("claude-", "anthropic-", "anthropics-", "cc-plugin-")
# Written out, not read from the gate, so a gate that drops or raises its bound fails.
MAX_JSON_DEPTH = 64
# The tags of the 4 checks, written out, so a FAIL line under any other tag fails.
TAGS = ("D1", "D2", "D3", "D4")
# Line breaks that str.splitlines honours, to put into paths and names.
BREAKS = ("\n", "\r", "\x0b", "\x85", "\u2028")
# A folder name that holds a line break and, after it, the start of a forged FAIL line; and how the
# gate shows it.
BROKEN = "h\nFAIL D9: k"
BROKEN_SHOWN = "h\\nFAIL D9: k"
spec = importlib.util.spec_from_file_location("check_plugin_distribution", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(gate)
except BaseException as error:
    # A gate that runs its main when it is loaded, or cannot be loaded, would end this test before any
    # case runs, with the gate's own exit status; stop with exit 1 instead.
    raise SystemExit(f"loading {MODULE_PATH} raised {type(error).__name__}: {error}") from None

VERSION = "1.0.15"


def marketplace() -> dict:
    return {
        "name": "cleanlanguage",
        "owner": {"name": "Jeff Posluns", "url": "https://cleanlanguage.ai/"},
        "description": "d",
        "plugins": [{"name": "cleanlanguage", "source": "./cleanlanguage", "category": "productivity"}],
    }


def vendored() -> dict:
    return {
        "name": "aiqt-guardrails",
        "owner": {"name": "Jeff Posluns"},
        "plugins": [{"name": "aiqt-guardrails-hooks", "source": "./aiqt-guardrails-hooks"}],
    }


def manifest(name: str = "cleanlanguage", version: str = VERSION) -> dict:
    return {"name": name, "version": version, "description": "d"}


class FoldingOs:
    """The os module as the gate meets it on a file system that folds letter case, as macOS does by
    default: os.lstat, os.open and os.listdir find a path whose names are missing as spelled under
    another letter case, while os.listdir lists each name as its folder holds it."""

    def __init__(self, root: Path):
        self.root = root

    def __getattr__(self, name):
        return getattr(os, name)

    def fold(self, path) -> Path:
        path = Path(path)
        if os.path.lexists(path):
            return path
        current = self.root
        for part in path.relative_to(self.root).parts:
            held = os.listdir(current) if os.path.isdir(current) else []
            current = current / next((name for name in held if name.lower() == part.lower()), part)
        return current

    def lstat(self, path):
        return os.lstat(self.fold(path))

    def open(self, path, flags, mode=0o777):
        return os.open(self.fold(path), flags, mode)

    def listdir(self, path):
        return os.listdir(self.fold(path))


class FaultyOs:
    """The os module with 1 function that raises an OSError on each path that holds marker (on every
    call when marker is None): with the errno and strerror given, as a device fault gives one, or with
    no strerror, as an OSError built by hand has, and the errno given."""

    def __init__(self, name: str, marker: str | None, number: int | None = None, strerror: str | None = None):
        self.name, self.marker, self.number, self.strerror = name, marker, number, strerror

    def __getattr__(self, name):
        real = getattr(os, name)
        if name != self.name:
            return real

        def faulty(*args, **kwargs):
            if self.marker is None or self.marker in str(args[0]):
                if self.strerror is not None:
                    raise OSError(self.number, self.strerror)
                error = OSError("no text")
                error.errno = self.number
                raise error
            return real(*args, **kwargs)
        return faulty


class PluginDistributionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._saved = gate.REPO_ROOT
        gate.REPO_ROOT = self.root
        self.write_json(gate.MARKETPLACE, marketplace())
        self.write_json(gate.VENDORED_MARKETPLACE, vendored())
        self.write_json("plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json",
                        manifest("aiqt-guardrails-hooks", "0.4.0"))
        self.write_json(gate.CLAUDE_MANIFEST, {**manifest(), "skills": ["./skills/cleanlanguage"]})
        self.write_json(gate.AGENT_MANIFEST, manifest())
        self.write_json(gate.SITE_JSON, {"schema": 1, "site_key": "cleanlanguage"})
        self.write_text(gate.SKILL_MD, f"---\nname: cleanlanguage\n---\n\n# Clean Language\n\nVersion: {VERSION}  \n")
        (self.root / "tools").mkdir()
        shutil.copyfile(REAL_EXTRACTOR, self.root / EXTRACTOR_REL)

    def tearDown(self):
        gate.REPO_ROOT = self._saved
        self._tmp.cleanup()

    def write_text(self, rel: str, text: str):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def write_json(self, rel: str, data: dict):
        self.write_text(rel, json.dumps(data, indent=2) + "\n")

    def edit_json(self, rel: str, change):
        data = json.loads((self.root / rel).read_text(encoding="utf-8"))
        change(data)
        self.write_json(rel, data)

    def run_gate(self):
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = gate.main()
        except BaseException as error:
            self.fail(f"the gate's main let {type(error).__name__} escape, a traceback in place of an exit "
                      f"status\n{out.getvalue()}{err.getvalue()}")
        return code, out.getvalue(), err.getvalue()

    def assert_lines(self, code: int, out: str, err: str):
        """The lines of each exit status, split as str.splitlines splits them, at every line break
        Python knows: for exit 1, 1 "FAIL <tag>: " line under a tag of TAGS for each inconsistency
        the count line names, then the count line and that line; for exit 0, the count line and the
        "OK: " line; for exit 3, nothing on standard output and 2 lines on standard error."""
        lines, problems = out.splitlines(), err.splitlines()
        if code == 3:
            self.assertEqual(lines, [], out + err)
            self.assertEqual(len(problems), 2, out + err)
            self.assertTrue(problems[0].startswith("check-plugin-distribution: "), out + err)
            self.assertEqual(problems[1], "UNREADABLE: exit 3", out + err)
            return
        self.assertEqual(problems, [], out + err)
        self.assertGreaterEqual(len(lines), 2, out + err)
        self.assertRegex(lines[-2], r"^check-plugin-distribution: \d+ relative sources? resolved, \d+ "
                                    r"dependenc(y|ies) read$")
        if code == 0:
            self.assertEqual(len(lines), 2, out + err)
            self.assertTrue(lines[-1].startswith("OK: "), out + err)
            return
        failures = lines[:-2]
        self.assertTrue(failures, out + err)
        for line in failures:
            self.assertTrue(line.startswith(tuple(f"FAIL {tag}: " for tag in TAGS)), f"{line!r}\n{out}")
        noun = "inconsistency" if len(failures) == 1 else "inconsistencies"
        self.assertEqual(lines[-1], f"FAIL: {len(failures)} {noun}", out + err)

    def expect(self, code: int, *needles: str, count: int | None = None):
        """Run the gate's main: the exit status, each needle, the last line and the lines of the status,
        and with count, a count line of exactly count inconsistencies."""
        got, out, err = self.run_gate()
        output = out + err
        self.assertEqual(got, code, output)
        for needle in needles:
            self.assertIn(needle, output)
        if count is not None:
            self.assertEqual(out.splitlines()[-1], f"FAIL: {count} inconsistenc{'y' if count == 1 else 'ies'}", output)
        stream, start = {0: (out, "OK: "), 1: (out, "FAIL: "), 3: (err, "UNREADABLE: exit 3")}[code]
        last = (stream.splitlines() or [""])[-1]
        self.assertTrue(last.startswith(start), f"last line {last!r} does not start {start!r}\n{output}")
        self.assert_lines(code, out, err)
        return output

    def add_vendored(self, name: str):
        """Add a plugin entry to the vendored marketplace, with a manifest of the same name."""
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"].append({"name": name, "source": f"./{name}"}))
        self.write_json(f"plugin/{name}/.claude-plugin/plugin.json", manifest(name, "0.4.0"))

    def edit_extractor(self, old: str, new: str):
        path = self.root / EXTRACTOR_REL
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_conforming_tree_passes(self):
        output = self.expect(0, "OK: D1 to D4 hold", "2 relative sources resolved", "0 dependencies read")
        self.assertNotIn("FAIL", output)

    def test_marketplace_named_jposluns_fails_d1(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d.update(name="jposluns"))
        self.expect(1, "FAIL D1: .claude-plugin/marketplace.json name is 'jposluns', not 'cleanlanguage'")

    def test_entry_name_differs_from_manifest_name_fails_d1(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(name="clean-language"))
        self.expect(1, "FAIL D1: .claude-plugin/marketplace.json plugins[0].name is 'clean-language'")

    def test_manifest_name_differs_fails_d1(self):
        self.edit_json(gate.CLAUDE_MANIFEST, lambda d: d.update(name="clean-language"))
        self.expect(1, "FAIL D1: cleanlanguage/.claude-plugin/plugin.json name is 'clean-language'")

    def test_second_plugin_entry_fails_d1(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"].append(dict(d["plugins"][0])))
        self.expect(1, "FAIL D1: .claude-plugin/marketplace.json lists 2 plugins, not exactly 1")

    def test_reserved_prefix_fails_d1(self):
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(name="claude-guardrails"))
        self.expect(1, "FAIL D1: plugin/.claude-plugin/marketplace.json name 'claude-guardrails' starts with a "
                       "reserved prefix")

    def test_missing_source_folder_fails_d2(self):
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(source="./absent"))
        self.expect(1, "FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0].source './absent' does not "
                       "resolve: plugin/absent is missing")

    def test_source_with_dotdot_fails_d2(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(source="./x/../cleanlanguage"))
        self.expect(1, "FAIL D2: .claude-plugin/marketplace.json plugins[0].source './x/../cleanlanguage' has an "
                       "empty, '.' or '..' component")

    def test_symlinked_source_fails_d2(self):
        os.symlink(self.root / "cleanlanguage", self.root / "linked")
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(source="./linked"))
        self.expect(1, "FAIL D2: .claude-plugin/marketplace.json plugins[0].source './linked' does not resolve: "
                       "linked is a symlink", count=1)

    def test_claude_manifest_version_differs_fails_d3(self):
        self.edit_json(gate.CLAUDE_MANIFEST, lambda d: d.update(version="1.0.16"))
        self.expect(1, "FAIL D3: the versions differ", "cleanlanguage/.claude-plugin/plugin.json version '1.0.16'")

    def test_agent_manifest_version_differs_fails_d3(self):
        self.edit_json(gate.AGENT_MANIFEST, lambda d: d.update(version="1.0.16"))
        self.expect(1, "FAIL D3: the versions differ", "cleanlanguage/plugin.json version '1.0.16'")

    def test_skill_version_differs_fails_d3(self):
        self.write_text(gate.SKILL_MD, "# Clean Language\n\nVersion: 1.0.16\n")
        self.expect(1, "FAIL D3: the versions differ", "SKILL.md Version: line '1.0.16'")

    def test_marketplace_entry_version_differs_fails_d3(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(version="1.0.16"))
        self.expect(1, "FAIL D3: the versions differ", "plugins[0].version '1.0.16'")

    def test_unresolved_dependency_fails_d4(self):
        self.edit_json("plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json",
                       lambda d: d.update(dependencies=["cleanlanguage"]))
        self.expect(1, "FAIL D4: plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json dependency "
                       "'cleanlanguage' names no plugin", "1 dependency read")

    def test_resolved_dependency_is_counted(self):
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"].append(
            {"name": "aiqt-skill", "source": "./aiqt-skill", "dependencies": ["aiqt-guardrails-hooks@aiqt-guardrails"]}))
        self.write_json("plugin/aiqt-skill/.claude-plugin/plugin.json", manifest("aiqt-skill", "0.4.0"))
        self.edit_json("plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json",
                       lambda d: d.update(dependencies=["aiqt-skill"]))
        self.expect(0, "2 dependencies read", "3 relative sources resolved")

    def test_duplicate_json_key_exits_3(self):
        self.write_text(gate.AGENT_MANIFEST, '{"name": "cleanlanguage", "version": "1.0.15", "version": "1.0.15"}\n')
        self.expect(3, "cleanlanguage/plugin.json repeats the key 'version'")

    def test_unreadable_file_exits_3(self):
        (self.root / gate.SITE_JSON).unlink()
        (self.root / gate.SITE_JSON).mkdir()
        self.expect(3, "site-src/site.json could not be read: it is not a regular file")

    def test_missing_file_exits_3(self):
        (self.root / gate.VENDORED_MARKETPLACE).unlink()
        # The exact cause line: a refusal of the gate is shown as it is, not as an exception that stopped it.
        self.expect(3, "check-plugin-distribution: plugin/.claude-plugin/marketplace.json could not be read: "
                       f"{os.strerror(errno.ENOENT)}\nUNREADABLE: exit 3\n")

    def test_source_reaching_another_plugin_fails_d2_and_d1(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(source="./plugin/aiqt-guardrails-hooks"))
        self.expect(1, "FAIL D2: .claude-plugin/marketplace.json plugins[0].source './plugin/aiqt-guardrails-hooks' "
                       "reaches plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json, not "
                       "cleanlanguage/.claude-plugin/plugin.json",
                    "FAIL D1: .claude-plugin/marketplace.json plugins[0].name is 'cleanlanguage', but the manifest "
                    "its source reaches, plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json, is named "
                    "'aiqt-guardrails-hooks'")

    def test_source_reaching_a_copy_of_the_plugin_fails_d2(self):
        self.write_json("copy/.claude-plugin/plugin.json", manifest())
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(source="./copy"))
        output = self.expect(1, "FAIL D2: .claude-plugin/marketplace.json plugins[0].source './copy' reaches "
                                "copy/.claude-plugin/plugin.json, not cleanlanguage/.claude-plugin/plugin.json")
        self.assertNotIn("FAIL D1", output)

    def test_object_source_fails_d2(self):
        for rel in (gate.MARKETPLACE, gate.VENDORED_MARKETPLACE):
            with self.subTest(rel=rel):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d["plugins"][0].update(source={"source": "github", "repo": "someone/else"}))
                try:
                    self.expect(1, f"FAIL D2: {rel} plugins[0].source {{'source': 'github', 'repo': 'someone/else'}} is "
                                   "not a string, so this gate cannot read where it leads", "1 relative source resolved")
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_vendored_entry_named_unlike_its_manifest_fails_d1(self):
        self.edit_json("plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json", lambda d: d.update(name="aiqt-hooks"))
        self.expect(1, "FAIL D1: plugin/.claude-plugin/marketplace.json plugins[0].name is 'aiqt-guardrails-hooks', "
                       "but the manifest its source reaches, plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json, "
                       "is named 'aiqt-hooks'")

    def test_empty_plugins_list_fails_d1(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d.update(plugins=[]))
        self.expect(1, "FAIL D1: .claude-plugin/marketplace.json lists 0 plugins, not exactly 1")

    def test_agent_manifest_name_differs_fails_d1(self):
        self.edit_json(gate.AGENT_MANIFEST, lambda d: d.update(name="clean-language"))
        self.expect(1, "FAIL D1: cleanlanguage/plugin.json name is 'clean-language', not 'cleanlanguage'")

    def test_site_key_differs_fails_d1(self):
        self.edit_json(gate.SITE_JSON, lambda d: d.update(site_key="jposluns"))
        self.expect(1, "FAIL D1: site-src/site.json site_key is 'jposluns', not 'cleanlanguage'")

    def test_source_without_dot_slash_fails_d2(self):
        for rel, source in ((gate.MARKETPLACE, "cleanlanguage"), (gate.VENDORED_MARKETPLACE, "aiqt-guardrails-hooks")):
            with self.subTest(rel=rel):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                try:
                    output = self.expect(1, f"FAIL D2: {rel} plugins[0].source '{source}' does not start with './'")
                    self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_source_that_is_a_file_fails_d2(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(source="./cleanlanguage/plugin.json"))
        self.expect(1, "FAIL D2: .claude-plugin/marketplace.json plugins[0].source './cleanlanguage/plugin.json' "
                       "does not resolve: cleanlanguage/plugin.json is not a directory")

    def test_manifest_that_is_a_directory_fails_d2(self):
        path = self.root / "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        path.unlink()
        path.mkdir()
        self.expect(1, "FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0].source './aiqt-guardrails-hooks' "
                       "does not resolve: plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json is not a regular "
                       "file")

    def test_entry_without_source_fails_d2(self):
        for rel in (gate.MARKETPLACE, gate.VENDORED_MARKETPLACE):
            with self.subTest(rel=rel):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d["plugins"][0].pop("source"))
                try:
                    output = self.expect(1, f"FAIL D2: {rel} plugins[0] has no source", "1 relative source resolved")
                    self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_missing_manifest_version_fails_d3(self):
        self.edit_json(gate.CLAUDE_MANIFEST, lambda d: d.pop("version"))
        self.expect(1, "FAIL D3: cleanlanguage/.claude-plugin/plugin.json version is None, not a version")

    def test_entry_version_not_a_string_fails_d3(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(version=1.0))
        self.expect(1, "FAIL D3: .claude-plugin/marketplace.json plugins[0].version is 1.0, not a version", count=1)

    def test_skill_without_version_line_fails_d3(self):
        self.write_text(gate.SKILL_MD, "---\nname: cleanlanguage\n---\n\n# Clean Language\n")
        self.expect(1, "FAIL D3: cleanlanguage/skills/cleanlanguage/SKILL.md Version: line is None, not a version")

    def test_dependency_of_another_marketplace_fails_d4(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["cleanlanguage@jposluns"]))
        self.expect(1, "FAIL D4: .claude-plugin/marketplace.json plugins[0] dependency 'cleanlanguage@jposluns' "
                       "names no plugin of the marketplace 'cleanlanguage'")

    def test_dependencies_not_a_list_fails_d4(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies="cleanlanguage"))
        self.expect(1, "FAIL D4: .claude-plugin/marketplace.json plugins[0] dependencies is not a list")

    def test_dependency_not_a_name_fails_d4(self):
        self.edit_json(gate.CLAUDE_MANIFEST, lambda d: d.update(dependencies=[{"name": "x"}]))
        self.expect(1, "FAIL D4: cleanlanguage/.claude-plugin/plugin.json names the dependency {'name': 'x'}, not "
                       "a plugin name")

    def test_nan_exits_3(self):
        self.write_text(gate.SITE_JSON, '{"schema": NaN, "site_key": "cleanlanguage"}\n')
        self.expect(3, "site-src/site.json is not valid JSON: non-standard JSON constant 'NaN'")

    def test_json_that_is_not_an_object_exits_3(self):
        self.write_text(gate.AGENT_MANIFEST, '["cleanlanguage"]\n')
        self.expect(3, "cleanlanguage/plugin.json is not a JSON object")

    def test_json_not_utf8_exits_3(self):
        (self.root / gate.MARKETPLACE).write_bytes(b'{"name": "clean\xfflanguage"}\n')
        self.expect(3, ".claude-plugin/marketplace.json is not UTF-8")

    def test_skill_not_utf8_exits_3(self):
        (self.root / gate.SKILL_MD).write_bytes(b"Version: 1.0.15\n\xff\n")
        self.expect(3, "cleanlanguage/skills/cleanlanguage/SKILL.md is not UTF-8")

    def test_symlinked_input_file_exits_3(self):
        target = self.root / "site.json.real"
        (self.root / gate.SITE_JSON).rename(target)
        os.symlink(target, self.root / gate.SITE_JSON)
        self.expect(3, "site-src/site.json could not be read: the component 'site.json' is a symlink")

    # Cases for docstring claims that the cases above did not hold.

    def test_each_reserved_prefix_fails_d1(self):
        for prefix in RESERVED_PREFIXES:
            with self.subTest(prefix=prefix):
                self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(name=f"{prefix}guardrails"))
                self.expect(1, f"FAIL D1: plugin/.claude-plugin/marketplace.json name '{prefix}guardrails' starts "
                               "with a reserved prefix")

    def test_reserved_prefix_in_entry_name_fails_d1(self):
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(name="cc-plugin-hooks"))
        self.expect(1, "FAIL D1: plugin/.claude-plugin/marketplace.json plugins[0].name 'cc-plugin-hooks' starts "
                       "with a reserved prefix")

    def test_marketplace_name_missing_or_empty_fails_d1(self):
        for change, shown in ((lambda d: d.pop("name"), "None"), (lambda d: d.update(name=""), "''")):
            with self.subTest(name=shown):
                self.write_json(gate.VENDORED_MARKETPLACE, vendored())
                self.edit_json(gate.VENDORED_MARKETPLACE, change)
                self.expect(1, f"FAIL D1: plugin/.claude-plugin/marketplace.json name is {shown}, not a name")

    def test_symlinked_manifest_folder_fails_d2(self):
        folder = self.root / "plugin/aiqt-guardrails-hooks/.claude-plugin"
        folder.rename(folder.with_name("real-claude-plugin"))
        os.symlink(folder.with_name("real-claude-plugin"), folder)
        self.expect(1, "FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0].source './aiqt-guardrails-hooks' "
                       "does not resolve: plugin/aiqt-guardrails-hooks/.claude-plugin is a symlink", count=1)

    def test_symlinked_manifest_fails_d2(self):
        path = self.root / "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        path.rename(path.with_name("real.json"))
        os.symlink(path.with_name("real.json"), path)
        self.expect(1, "FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0].source './aiqt-guardrails-hooks' "
                       "does not resolve: plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json is a symlink", count=1)

    def test_symlinked_input_folder_exits_3(self):
        (self.root / "site-src").rename(self.root / "site-src.real")
        os.symlink(self.root / "site-src.real", self.root / "site-src")
        self.expect(3, "site-src/site.json could not be read: the component 'site-src' is a symlink")

    def test_byte_order_mark_passes(self):
        path = self.root / gate.MARKETPLACE
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        self.expect(0, "OK: D1 to D4 hold")

    def test_vendored_entry_not_an_object_fails_d2(self):
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(plugins=["aiqt-guardrails-hooks"]))
        self.expect(1, "FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0] is not a JSON object")

    def test_vendored_marketplace_without_plugins_list_fails_d2(self):
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.pop("plugins"))
        self.expect(1, "FAIL D2: plugin/.claude-plugin/marketplace.json has no plugins list")

    def test_empty_version_fails_d3(self):
        self.edit_json(gate.AGENT_MANIFEST, lambda d: d.update(version=""))
        self.expect(1, "FAIL D3: cleanlanguage/plugin.json version is '', not a version", count=1)

    def test_failure_count_line(self):
        self.edit_json(gate.SITE_JSON, lambda d: d.update(site_key="jposluns"))
        output = self.expect(1)
        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
        self.edit_json(gate.AGENT_MANIFEST, lambda d: d.update(name="clean-language"))
        output = self.expect(1)
        self.assertEqual(output.splitlines()[-1], "FAIL: 2 inconsistencies")

    def test_unreadable_last_line(self):
        (self.root / gate.SITE_JSON).unlink()
        got, out, err = self.run_gate()
        self.assertEqual(got, 3, out + err)
        self.assertEqual(err.splitlines()[-1], "UNREADABLE: exit 3")

    def test_deeply_nested_json_exits_3(self):
        # A conforming site object whose "deep" member nests arrays to the given total depth (the object
        # is level 1). Its string holds escaped quotes and brackets, which the bound must not count.
        def site(depth: int) -> str:
            inner = depth - 1
            return ('{"schema": 1, "site_key": "cleanlanguage", "note": "' + '\\"[{' * 100 + '", "deep": '
                    + "[" * inner + "]" * inner + "}\n")
        self.write_text(gate.SITE_JSON, site(MAX_JSON_DEPTH))
        self.expect(0, "OK: D1 to D4 hold")
        self.write_text(gate.SITE_JSON, site(MAX_JSON_DEPTH + 1))
        self.expect(3, f"site-src/site.json is nested too deeply to decode: more than {MAX_JSON_DEPTH} levels")

    def test_source_with_empty_component_fails_d2(self):
        for rel, folder in ((gate.MARKETPLACE, "cleanlanguage"), (gate.VENDORED_MARKETPLACE, "aiqt-guardrails-hooks")):
            for source in (f"./{folder}/", f".//{folder}"):
                with self.subTest(rel=rel, source=source):
                    saved = (self.root / rel).read_bytes()
                    self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                    try:
                        output = self.expect(1, f"FAIL D2: {rel} plugins[0].source '{source}' has an empty, '.' or "
                                                "'..' component", "1 relative source resolved")
                        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                    finally:
                        (self.root / rel).write_bytes(saved)

    # The extractor: reached from REPO_ROOT, and exit 3 when it cannot be used.

    def test_extractor_without_a_pattern_exits_3(self):
        for name in ("VERSION_LINE", "SKILL_VERSION"):
            with self.subTest(name=name):
                shutil.copyfile(REAL_EXTRACTOR, self.root / EXTRACTOR_REL)
                self.edit_extractor(f"{name} = re.compile", f"{name}_GONE = re.compile")
                self.expect(3, f"the extractor tools/skill-version.py could not be used: it has no {name} "
                               "pattern of text")

    def test_extractor_raising_while_it_loads_exits_3(self):
        # Any BaseException, and a message that holds a line break or cannot be shown, which the cause
        # line must hold on 1 line.
        unshowable = ("class Unshowable(Exception):\n    def __str__(self):\n        raise ValueError('no text')\n"
                      "raise Unshowable()")
        for statement, shown in (("raise RuntimeError('broken')", "RuntimeError: broken"),
                                 ("raise SystemExit(0)", "SystemExit: 0"),
                                 ("raise BaseException('boom')", "BaseException: boom"),
                                 ("raise GeneratorExit", "GeneratorExit: "),
                                 ("raise KeyboardInterrupt", "KeyboardInterrupt: "),
                                 ("raise RuntimeError('a\\nUNREADABLE: exit 3')", "RuntimeError: a\\nUNREADABLE: exit 3"),
                                 (unshowable, "Unshowable: (a message that cannot be shown)")):
            with self.subTest(statement=statement):
                shutil.copyfile(REAL_EXTRACTOR, self.root / EXTRACTOR_REL)
                self.edit_extractor('PROG = "skill-version"\n', f'PROG = "skill-version"\n{statement}\n')
                self.expect(3, f"the extractor tools/skill-version.py could not be loaded: {shown}")

    def test_any_exception_in_the_gate_exits_3_on_1_line(self):
        # An exception raised in the gate itself, not in the extractor, of any class, also with a message
        # that holds a line break or cannot be shown: exit 3 and 1 cause line, never a traceback.
        class Unshowable(Exception):
            def __str__(self):
                raise ValueError("no text")

        for error, shown in ((TypeError("a\nFAIL D1: x"), "TypeError: a\\nFAIL D1: x"),
                             (BaseException("b\r\nUNREADABLE: exit 3"), "BaseException: b\\r\\nUNREADABLE: exit 3"),
                             (KeyboardInterrupt(), "KeyboardInterrupt: "),
                             (SystemExit(0), "SystemExit: 0"),
                             (Unshowable(), "Unshowable: (a message that cannot be shown)")):
            with self.subTest(error=type(error).__name__):
                with mock.patch.object(gate, "check_versions", side_effect=error):
                    output = self.expect(3, f"check-plugin-distribution: the gate stopped on {shown}\n")
                self.assertNotIn("Traceback", output)

    def test_missing_extractor_exits_3(self):
        (self.root / EXTRACTOR_REL).unlink()
        self.expect(3, "tools/skill-version.py could not be read")

    def test_symlinked_extractor_exits_3(self):
        path = self.root / EXTRACTOR_REL
        path.rename(path.with_name("real-skill-version.py"))
        os.symlink(path.with_name("real-skill-version.py"), path)
        self.expect(3, "tools/skill-version.py could not be read: the component 'skill-version.py' is a symlink")

    # The reserved prefixes in another letter case.

    def test_reserved_prefix_in_any_case_fails_d1(self):
        for name in ("Claude-x", "ANTHROPIC-x", "Anthropics-x", "CC-Plugin-x"):
            with self.subTest(name=name):
                self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(name=name))
                self.expect(1, f"FAIL D1: plugin/.claude-plugin/marketplace.json name '{name}' starts with a "
                               "reserved prefix")

    # The count lines for 1 and for more than 1.

    def test_count_lines_read_for_1(self):
        # An empty vendored list resolves no source and is no failure; the 1 dependency is the 1 failure.
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(plugins=[]))
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["cleanlanguage"]))
        output = self.expect(1, "FAIL D4: .claude-plugin/marketplace.json plugins[0] dependency 'cleanlanguage' "
                                "names the plugin itself")
        self.assertIn("check-plugin-distribution: 1 relative source resolved, 1 dependency read\n", output)
        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")

    def test_count_lines_read_for_more_than_1(self):
        self.add_vendored("aiqt-skill")
        self.add_vendored("aiqt-docs")
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(
            dependencies=["aiqt-skill", "aiqt-docs@aiqt-guardrails"]))
        output = self.expect(0)
        self.assertIn("check-plugin-distribution: 4 relative sources resolved, 2 dependencies read\n", output)

    # A value of an unexpected JSON type, at each place the gate reads one: the FAIL lines and the
    # count line, never a traceback.

    def test_entry_name_that_is_an_array_fails_d1(self):
        # Read by the names check, by the reach check and by the dependencies check's set of names.
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(name=["x"]))
        output = self.expect(1, "FAIL D1: plugin/.claude-plugin/marketplace.json plugins[0].name is ['x'], not a name",
                             "FAIL D1: plugin/.claude-plugin/marketplace.json plugins[0].name is ['x'], but the "
                             "manifest its source reaches",
                             "check-plugin-distribution: 2 relative sources resolved, 0 dependencies read\n")
        self.assertEqual(output.splitlines()[-1], "FAIL: 2 inconsistencies")

    def test_entry_name_that_is_an_object_fails_d1(self):
        # The repository's second entry: read by the names check and by the dependencies check.
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"].append({"name": {"a": 1}, "source": "./absent"}))
        self.expect(1, "FAIL D1: .claude-plugin/marketplace.json lists 2 plugins, not exactly 1",
                    "FAIL D1: .claude-plugin/marketplace.json plugins[1].name is {'a': 1}, not a name")

    def test_marketplace_name_that_is_an_array_fails_d1_and_d4(self):
        # Read by the names check and by a qualified dependency.
        self.add_vendored("aiqt-skill")
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(name=["x"]))
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["aiqt-skill@x"]))
        self.expect(1, "FAIL D1: plugin/.claude-plugin/marketplace.json name is ['x'], not a name",
                    "FAIL D4: plugin/.claude-plugin/marketplace.json plugins[0] dependency 'aiqt-skill@x' names no "
                    "plugin of the marketplace ['x']")

    def test_manifest_name_that_is_an_array_fails_d1(self):
        # Read by the reach check, and by the dependencies check as the manifest's own name.
        self.add_vendored("aiqt-skill")
        self.edit_json("plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json",
                       lambda d: d.update(name=["x"], dependencies=["aiqt-skill"]))
        self.expect(1, "FAIL D1: plugin/.claude-plugin/marketplace.json plugins[0].name is 'aiqt-guardrails-hooks', "
                       "but the manifest its source reaches, plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json, "
                       "is named ['x']", "1 dependency read")

    # Cases for mutants that the cases above let pass, for a plugin that depends on itself and for a
    # dependency listed twice.

    def test_project_name_in_another_letter_case_fails_d1(self):
        for rel, key, label in ((gate.MARKETPLACE, "name", ".claude-plugin/marketplace.json name"),
                                (gate.CLAUDE_MANIFEST, "name", "cleanlanguage/.claude-plugin/plugin.json name"),
                                (gate.AGENT_MANIFEST, "name", "cleanlanguage/plugin.json name"),
                                (gate.SITE_JSON, "site_key", "site-src/site.json site_key")):
            with self.subTest(label=label):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d.update({key: "CleanLanguage"}))
                self.expect(1, f"FAIL D1: {label} is 'CleanLanguage', not 'cleanlanguage'")
                (self.root / rel).write_bytes(saved)
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(name="CleanLanguage"))
        self.expect(1, "FAIL D1: .claude-plugin/marketplace.json plugins[0].name is 'CleanLanguage', not "
                       "'cleanlanguage'")

    def test_dependency_with_an_empty_marketplace_fails_d4(self):
        self.add_vendored("aiqt-skill")
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["aiqt-skill@"]))
        self.expect(1, "FAIL D4: plugin/.claude-plugin/marketplace.json plugins[0] dependency 'aiqt-skill@' names no "
                       "plugin of the marketplace 'aiqt-guardrails'")

    def test_empty_dependency_fails_d4(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=[""]))
        self.expect(1, "FAIL D4: .claude-plugin/marketplace.json plugins[0] names the dependency '', not a plugin name")

    def test_extractor_pattern_of_bytes_exits_3(self):
        for name in ("VERSION_LINE", "SKILL_VERSION"):
            with self.subTest(name=name):
                shutil.copyfile(REAL_EXTRACTOR, self.root / EXTRACTOR_REL)
                self.edit_extractor(f'{name} = re.compile(r"', f'{name} = re.compile(rb"')
                self.expect(3, f"the extractor tools/skill-version.py could not be used: it has no {name} "
                               "pattern of text")

    def test_self_dependency_fails_d4(self):
        hooks = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        for rel, change, label, dep in (
                (gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["cleanlanguage"]),
                 ".claude-plugin/marketplace.json plugins[0]", "cleanlanguage"),
                (gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["cleanlanguage@cleanlanguage"]),
                 ".claude-plugin/marketplace.json plugins[0]", "cleanlanguage@cleanlanguage"),
                (gate.CLAUDE_MANIFEST, lambda d: d.update(dependencies=["cleanlanguage"]),
                 "cleanlanguage/.claude-plugin/plugin.json", "cleanlanguage"),
                (gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["aiqt-guardrails-hooks"]),
                 "plugin/.claude-plugin/marketplace.json plugins[0]", "aiqt-guardrails-hooks"),
                (hooks, lambda d: d.update(dependencies=["aiqt-guardrails-hooks@aiqt-guardrails"]),
                 hooks, "aiqt-guardrails-hooks@aiqt-guardrails")):
            with self.subTest(label=label, dep=dep):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, change)
                output = self.expect(1, f"FAIL D4: {label} dependency {dep!r} names the plugin itself, which this "
                                        "gate refuses")
                self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                (self.root / rel).write_bytes(saved)

    def test_repeated_dependency_fails_d4(self):
        hooks = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        self.add_vendored("aiqt-skill")
        for rel, change, label, dep in (
                (gate.VENDORED_MARKETPLACE,
                 lambda d: d["plugins"][0].update(dependencies=["aiqt-skill", "aiqt-skill"]),
                 "plugin/.claude-plugin/marketplace.json plugins[0]", "aiqt-skill"),
                (gate.VENDORED_MARKETPLACE,
                 lambda d: d["plugins"][0].update(dependencies=["aiqt-skill", "aiqt-skill@aiqt-guardrails"]),
                 "plugin/.claude-plugin/marketplace.json plugins[0]", "aiqt-skill@aiqt-guardrails"),
                (hooks, lambda d: d.update(dependencies=["aiqt-skill@aiqt-guardrails", "aiqt-skill"]),
                 hooks, "aiqt-skill")):
            with self.subTest(label=label, dep=dep):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, change)
                try:
                    output = self.expect(1, f"FAIL D4: {label} dependency {dep!r} names the plugin 'aiqt-skill' a "
                                            "second time, which this gate refuses", "2 dependencies read")
                    self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_source_that_is_no_path_fails_d2(self):
        for rel in (gate.MARKETPLACE, gate.VENDORED_MARKETPLACE):
            for source, shown in (("./a\x00b", "'./a\\x00b'"), ("./\ud800", "'./\\ud800'")):
                with self.subTest(rel=rel, source=shown):
                    saved = (self.root / rel).read_bytes()
                    self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                    try:
                        output = self.expect(1, f"FAIL D2: {rel} plugins[0].source {shown} is not a path the "
                                                "operating system accepts", "1 relative source resolved")
                        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                    finally:
                        (self.root / rel).write_bytes(saved)

    # Cases for a "." component, an unusable source, a null dependency list, the depth count, the scope
    # of the repeated-dependency check, denied permissions and the command-line entry point.

    def test_source_with_dot_component_fails_d2(self):
        for rel, folder in ((gate.MARKETPLACE, "cleanlanguage"), (gate.VENDORED_MARKETPLACE, "aiqt-guardrails-hooks")):
            for source in (f"././{folder}", f"./{folder}/."):
                with self.subTest(rel=rel, source=source):
                    saved = (self.root / rel).read_bytes()
                    self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                    try:
                        output = self.expect(1, f"FAIL D2: {rel} plugins[0].source '{source}' has an empty, '.' "
                                                "or '..' component", "1 relative source resolved")
                        self.assertNotIn("reaches", output)
                        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                    finally:
                        (self.root / rel).write_bytes(saved)

    def test_source_with_too_long_component_fails_d2(self):
        source = "./" + "a" * 300
        for rel in (gate.MARKETPLACE, gate.VENDORED_MARKETPLACE):
            with self.subTest(rel=rel):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                try:
                    output = self.expect(1, f"FAIL D2: {rel} plugins[0].source '{source}' is not a path the operating "
                                            f"system accepts: {os.strerror(errno.ENAMETOOLONG)}\n",
                                         "1 relative source resolved")
                    self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_null_dependencies_fails_d4(self):
        hooks = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        for rel, change, label in (
                (gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=None),
                 ".claude-plugin/marketplace.json plugins[0]"),
                (gate.CLAUDE_MANIFEST, lambda d: d.update(dependencies=None),
                 "cleanlanguage/.claude-plugin/plugin.json"),
                (gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=None),
                 "plugin/.claude-plugin/marketplace.json plugins[0]"),
                (hooks, lambda d: d.update(dependencies=None), hooks)):
            with self.subTest(label=label):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, change)
                try:
                    output = self.expect(1, f"FAIL D4: {label} dependencies is not a list")
                    self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_many_sibling_arrays_within_the_depth_bound_pass(self):
        # 3 levels deep, but more than MAX_JSON_DEPTH arrays and objects in all: the bound counts nesting.
        siblings = ", ".join(["[]"] * (MAX_JSON_DEPTH + 6))
        self.write_text(gate.SITE_JSON, '{"schema": 1, "site_key": "cleanlanguage", "deep": [' + siblings + "]}\n")
        self.expect(0, "OK: D1 to D4 hold")

    # Cases for objects beside the arrays above, a plugin name listed twice and a file system that
    # folds letter case.

    def test_many_sibling_objects_within_the_depth_bound_pass(self):
        # The same with objects: each closing brace lowers the count, as each closing bracket does.
        siblings = ", ".join(['{"a": 1}'] * (MAX_JSON_DEPTH + 6))
        self.write_text(gate.SITE_JSON, '{"schema": 1, "site_key": "cleanlanguage", "deep": [' + siblings + "]}\n")
        self.expect(0, "OK: D1 to D4 hold")

    def test_deeply_nested_objects_exit_3(self):
        # A conforming site object whose "deep" member nests objects to the given total depth.
        def site(depth: int) -> str:
            inner = depth - 1
            return ('{"schema": 1, "site_key": "cleanlanguage", "deep": ' + '{"a": ' * (inner - 1) + "{}"
                    + "}" * (inner - 1) + "}\n")
        self.write_text(gate.SITE_JSON, site(MAX_JSON_DEPTH))
        self.expect(0, "OK: D1 to D4 hold")
        self.write_text(gate.SITE_JSON, site(MAX_JSON_DEPTH + 1))
        self.expect(3, f"site-src/site.json is nested too deeply to decode: more than {MAX_JSON_DEPTH} levels")

    def test_plugin_listed_twice_in_the_repository_marketplace_fails_d1(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"].append(dict(d["plugins"][0])))
        output = self.expect(1, "FAIL D1: .claude-plugin/marketplace.json lists 2 plugins, not exactly 1",
                             "FAIL D1: .claude-plugin/marketplace.json plugins[1].name 'cleanlanguage' lists the "
                             "plugin of plugins[0] a second time, which this gate refuses",
                             "3 relative sources resolved")
        self.assertEqual(output.splitlines()[-1], "FAIL: 2 inconsistencies")

    def test_plugin_listed_twice_in_the_vendored_marketplace_fails_d1(self):
        # The second listing comes after another plugin; in another letter case it reaches a manifest
        # of its own name, so the repeated name is the 1 failure.
        self.add_vendored("aiqt-skill")
        self.write_json("plugin/aiqt-hooks-copy/.claude-plugin/plugin.json", manifest("AIQT-Guardrails-Hooks", "0.4.0"))
        for name, source in (("aiqt-guardrails-hooks", "./aiqt-guardrails-hooks"),
                             ("AIQT-Guardrails-Hooks", "./aiqt-hooks-copy")):
            with self.subTest(name=name):
                saved = (self.root / gate.VENDORED_MARKETPLACE).read_bytes()
                self.edit_json(gate.VENDORED_MARKETPLACE,
                               lambda d: d["plugins"].append({"name": name, "source": source}))
                try:
                    output = self.expect(1, f"FAIL D1: plugin/.claude-plugin/marketplace.json plugins[2].name {name!r} "
                                            "lists the plugin of plugins[0] a second time, which this gate refuses",
                                            "4 relative sources resolved")
                    self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                finally:
                    (self.root / gate.VENDORED_MARKETPLACE).write_bytes(saved)

    def test_source_in_another_letter_case_fails_d2(self):
        # Each spelling reaches its folder through a folding os.lstat, but is not how the folder lists it.
        # A stored name is renamed for the last 2: the .claude-plugin folder and the manifest's final file name.
        folder = self.root / "plugin/aiqt-guardrails-hooks/.claude-plugin"
        for rel, source, rename, shown in (
                (gate.MARKETPLACE, "./CleanLanguage", None, "CleanLanguage"),
                (gate.VENDORED_MARKETPLACE, "./AIQT-Guardrails-Hooks", None, "plugin/AIQT-Guardrails-Hooks"),
                (gate.VENDORED_MARKETPLACE, "./aiqt-guardrails-hooks", (folder, ".Claude-Plugin"),
                 "plugin/aiqt-guardrails-hooks/.claude-plugin"),
                (gate.VENDORED_MARKETPLACE, "./aiqt-guardrails-hooks", (folder / "plugin.json", "Plugin.json"),
                 "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json")):
            with self.subTest(source=source, rename=rename and rename[1]):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                if rename:
                    rename[0].rename(rename[0].with_name(rename[1]))
                try:
                    with mock.patch.object(gate, "os", FoldingOs(self.root)):
                        output = self.expect(1, f"FAIL D2: {rel} plugins[0].source '{source}' does not resolve: {shown} "
                                                "is not spelled as its folder lists it", "1 relative source resolved")
                    self.assertNotIn("reaches", output)
                    self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                finally:
                    (self.root / rel).write_bytes(saved)
                    if rename:
                        rename[0].with_name(rename[1]).rename(rename[0])

    def test_input_folder_in_another_letter_case_exits_3(self):
        (self.root / "site-src").rename(self.root / "Site-Src")
        with mock.patch.object(gate, "os", FoldingOs(self.root)):
            self.expect(3, "site-src/site.json could not be read: the component 'site-src' is not spelled as its "
                           "folder lists it")

    def test_lists_naming_the_same_plugin_pass(self):
        # An entry's list, its manifest's list and another entry's list each name aiqt-skill once.
        self.add_vendored("aiqt-skill")
        self.add_vendored("aiqt-docs")
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: (d["plugins"][0].update(dependencies=["aiqt-skill"]),
                                                             d["plugins"][2].update(dependencies=["aiqt-skill"])))
        self.edit_json("plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json",
                       lambda d: d.update(dependencies=["aiqt-skill@aiqt-guardrails"]))
        output = self.expect(0, "OK: D1 to D4 hold", "4 relative sources resolved, 3 dependencies read")
        self.assertNotIn("FAIL", output)

    @contextlib.contextmanager
    def denied(self, rel: str, kept: int = 0):
        """rel with every permission but those of kept taken away, given back before the tree is removed."""
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root is not refused by file permissions")
        path = self.root / rel
        mode = path.stat().st_mode
        path.chmod(kept)
        try:
            yield
        finally:
            path.chmod(mode)

    def test_input_file_denying_permission_exits_3(self):
        with self.denied(gate.SITE_JSON):
            self.expect(3, "site-src/site.json could not be read: Permission denied")

    def test_source_folder_denying_permission_exits_3(self):
        with self.denied("plugin/aiqt-guardrails-hooks"):
            self.expect(3, "plugin/aiqt-guardrails-hooks/.claude-plugin could not be read: Permission denied")

    # Cases for a folder that can be searched but not listed, a malformed first Version: line, a final
    # file name in another letter case, names equal only under case folding, a dependency listed twice
    # in the repository's marketplace and an extractor pattern with no usable group 1.

    def test_source_folder_that_cannot_be_listed_exits_3(self):
        # Mode 0111: os.lstat reaches the .claude-plugin folder inside, but os.listdir of the folder fails.
        with self.denied("plugin/aiqt-guardrails-hooks", 0o111):
            self.expect(3, "plugin/aiqt-guardrails-hooks could not be listed: Permission denied")

    def test_input_folder_that_cannot_be_listed_exits_3(self):
        # Mode 0111: os.lstat reaches site.json, but os.listdir of site-src fails.
        with self.denied("site-src", 0o111):
            self.expect(3, "site-src/site.json could not be read: Permission denied")

    def test_malformed_first_version_line_fails_d3(self):
        # The first Version: line is not a bare X.Y.Z, alone and before a valid one, which is never read.
        for lines in (f"Version: {VERSION} beta\n", f"Version: {VERSION} beta\n\nVersion: {VERSION}\n"):
            with self.subTest(lines=lines):
                self.write_text(gate.SKILL_MD, "---\nname: cleanlanguage\n---\n\n# Clean Language\n\n" + lines)
                output = self.expect(1, "FAIL D3: cleanlanguage/skills/cleanlanguage/SKILL.md Version: line is None, "
                                        "not a version")
                self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")

    def test_input_file_name_in_another_letter_case_exits_3(self):
        (self.root / gate.SITE_JSON).rename(self.root / "site-src/Site.json")
        with mock.patch.object(gate, "os", FoldingOs(self.root)):
            self.expect(3, "site-src/site.json could not be read: the component 'site.json' is not spelled as its "
                           "folder lists it")

    def test_names_equal_under_case_folding_fail_d1(self):
        # The long s (U+017F) folds to "s", while str.lower keeps it.
        name = "anthropic\u017f-hooks"
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(name=name))
        self.expect(1, f"FAIL D1: plugin/.claude-plugin/marketplace.json name {name!r} starts with a reserved prefix")
        self.write_json(gate.VENDORED_MARKETPLACE, vendored())
        name = "aiqt-\u017fkill"
        self.add_vendored("aiqt-skill")
        self.write_json("plugin/aiqt-skill-copy/.claude-plugin/plugin.json", manifest(name, "0.4.0"))
        self.edit_json(gate.VENDORED_MARKETPLACE,
                       lambda d: d["plugins"].append({"name": name, "source": "./aiqt-skill-copy"}))
        output = self.expect(1, f"FAIL D1: plugin/.claude-plugin/marketplace.json plugins[2].name {name!r} lists the "
                                "plugin of plugins[1] a second time, which this gate refuses",
                             "4 relative sources resolved")
        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")

    def test_repeated_dependency_in_the_repository_marketplace_fails_d4(self):
        # A second plugin there, so that its entry and manifest can name a plugin other than their own; the
        # second entry and the source it reaches are the 2 other failures.
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"].append({"name": "helper", "source": "./helper"}))
        self.write_json("helper/.claude-plugin/plugin.json", manifest("helper"))
        for rel, change, label, dep in (
                (gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["helper", "helper@cleanlanguage"]),
                 ".claude-plugin/marketplace.json plugins[0]", "helper@cleanlanguage"),
                (gate.CLAUDE_MANIFEST, lambda d: d.update(dependencies=["helper@cleanlanguage", "helper"]),
                 "cleanlanguage/.claude-plugin/plugin.json", "helper")):
            with self.subTest(label=label):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, change)
                try:
                    output = self.expect(1, f"FAIL D4: {label} dependency {dep!r} names the plugin 'helper' a second "
                                            "time, which this gate refuses",
                                         "FAIL D1: .claude-plugin/marketplace.json lists 2 plugins, not exactly 1",
                                         "FAIL D2: .claude-plugin/marketplace.json plugins[1].source './helper' reaches "
                                         "helper/.claude-plugin/plugin.json, not cleanlanguage/.claude-plugin/plugin.json",
                                         "3 relative sources resolved, 2 dependencies read")
                    self.assertEqual(output.splitlines()[-1], "FAIL: 3 inconsistencies")
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_extractor_pattern_without_group_1_exits_3(self):
        for old, new, shown in (
                (r"([0-9]+\.[0-9]+\.[0-9]+)", r"(?:[0-9]+\.[0-9]+\.[0-9]+)", "its SKILL_VERSION pattern has no group 1"),
                ('SKILL_VERSION = re.compile(r"^Version:', 'SKILL_VERSION = re.compile(r"^(unused)?Version:',
                 f"its SKILL_VERSION pattern matched 'Version: {VERSION}  ' with no text in group 1")):
            with self.subTest(new=new):
                shutil.copyfile(REAL_EXTRACTOR, self.root / EXTRACTOR_REL)
                self.edit_extractor(old, new)
                self.expect(3, f"the extractor tools/skill-version.py could not be used: {shown}")

    # Cases for an extractor that writes while it loads, a line break at each place a path or a name
    # enters a line of output, the rules of the names, sources and dependencies checks in each place
    # they apply, the line endings of SKILL.md and the versions of vendored entries.

    def test_extractor_output_while_it_loads_is_dropped(self):
        self.edit_extractor('PROG = "skill-version"\n', 'PROG = "skill-version"\nimport sys\nprint("FAIL D9: forged")\n'
                            'print("UNREADABLE: exit 3", file=sys.stderr)\n')
        output = self.expect(0, "OK: D1 to D4 hold")
        self.assertNotIn("D9", output)
        self.assertNotIn("UNREADABLE", output)

    def test_line_break_in_a_missing_source_stays_on_1_line(self):
        for rel, base in ((gate.MARKETPLACE, ""), (gate.VENDORED_MARKETPLACE, "plugin/")):
            for brk in BREAKS:
                source, shown = f"./a{brk}FAIL D9: forged", repr(brk)[1:-1]
                with self.subTest(rel=rel, brk=shown):
                    saved = (self.root / rel).read_bytes()
                    self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                    try:
                        output = self.expect(1, f"FAIL D2: {rel} plugins[0].source {source!r} does not resolve: "
                                                f"{base}a{shown}FAIL D9: forged is missing")
                        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                    finally:
                        (self.root / rel).write_bytes(saved)

    def point_vendored_entry(self, folder: str):
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(source=f"./{folder}"))

    def test_line_break_in_a_source_that_is_a_file_stays_on_1_line(self):
        self.write_text(f"plugin/{BROKEN}", "x")
        self.point_vendored_entry(BROKEN)
        self.expect(1, f"does not resolve: plugin/{BROKEN_SHOWN} is not a directory")

    def test_line_break_in_a_symlinked_source_stays_on_1_line(self):
        os.symlink(self.root / "plugin/aiqt-guardrails-hooks", self.root / f"plugin/{BROKEN}")
        self.point_vendored_entry(BROKEN)
        self.expect(1, f"does not resolve: plugin/{BROKEN_SHOWN} is a symlink")

    def test_line_break_in_a_source_in_another_letter_case_stays_on_1_line(self):
        self.write_json(f"plugin/{BROKEN}/.claude-plugin/plugin.json", manifest("aiqt-guardrails-hooks", "0.4.0"))
        self.point_vendored_entry(BROKEN.upper())
        with mock.patch.object(gate, "os", FoldingOs(self.root)):
            self.expect(1, f"does not resolve: plugin/{repr(BROKEN.upper())[1:-1]} is not spelled as its folder lists "
                           "it")

    def test_line_break_in_a_path_another_plugin_reaches_stays_on_1_line(self):
        self.write_json(f"{BROKEN}/.claude-plugin/plugin.json", manifest())
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(source=f"./{BROKEN}"))
        self.expect(1, f"reaches {BROKEN_SHOWN}/.claude-plugin/plugin.json, not cleanlanguage/.claude-plugin/plugin.json")

    def test_line_break_in_a_manifest_path_of_the_names_check_stays_on_1_line(self):
        self.write_json(f"plugin/{BROKEN}/.claude-plugin/plugin.json", manifest("other", "0.4.0"))
        self.point_vendored_entry(BROKEN)
        self.expect(1, f"FAIL D1: plugin/.claude-plugin/marketplace.json plugins[0].name is 'aiqt-guardrails-hooks', "
                       f"but the manifest its source reaches, plugin/{BROKEN_SHOWN}/.claude-plugin/plugin.json, is "
                       "named 'other'")

    def test_line_break_in_a_manifest_path_of_the_dependencies_check_stays_on_1_line(self):
        self.write_json(f"plugin/{BROKEN}/.claude-plugin/plugin.json",
                        {**manifest("aiqt-guardrails-hooks", "0.4.0"), "dependencies": ["nope"]})
        self.point_vendored_entry(BROKEN)
        self.expect(1, f"FAIL D4: plugin/{BROKEN_SHOWN}/.claude-plugin/plugin.json dependency 'nope' names no plugin")

    def test_line_break_in_an_unreadable_source_path_stays_on_1_line(self):
        self.write_json(f"plugin/{BROKEN}/.claude-plugin/plugin.json", manifest("aiqt-guardrails-hooks", "0.4.0"))
        self.point_vendored_entry(BROKEN)
        for kept, shown in ((0, f"plugin/{BROKEN_SHOWN}/.claude-plugin could not be read: Permission denied"),
                            (0o111, f"plugin/{BROKEN_SHOWN} could not be listed: Permission denied")):
            with self.subTest(kept=oct(kept)):
                with self.denied(f"plugin/{BROKEN}", kept):
                    self.expect(3, shown)

    def test_line_break_in_a_name_or_value_stays_on_1_line(self):
        for rel, change, needle in (
                (gate.MARKETPLACE, lambda d: d.update(name="clean\nlanguage"),
                 "FAIL D1: .claude-plugin/marketplace.json name is 'clean\\nlanguage', not 'cleanlanguage'"),
                (gate.VENDORED_MARKETPLACE, lambda d: d.update(name="claude-\nFAIL D9: x"),
                 "FAIL D1: plugin/.claude-plugin/marketplace.json name 'claude-\\nFAIL D9: x' starts with a reserved prefix"),
                (gate.AGENT_MANIFEST, lambda d: d.update(version="1.0.15\nFAIL D9: x"),
                 "cleanlanguage/plugin.json version '1.0.15\\nFAIL D9: x'"),
                (gate.MARKETPLACE, lambda d: d["plugins"][0].update(dependencies=["a\nFAIL D9: b"]),
                 "FAIL D4: .claude-plugin/marketplace.json plugins[0] dependency 'a\\nFAIL D9: b' names no plugin"),
                (gate.VENDORED_MARKETPLACE, lambda d: (d.update(name="m\nFAIL D9: n"),
                                                       d["plugins"][0].update(dependencies=["x@y"])),
                 "names no plugin of the marketplace 'm\\nFAIL D9: n'")):
            with self.subTest(needle=needle):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, change)
                try:
                    self.expect(1, needle)
                finally:
                    (self.root / rel).write_bytes(saved)

    def test_reserved_prefix_in_each_name_fails_d1(self):
        # Each prefix in lower case, upper case and title case, and "anthropics-" with a long s, as a
        # marketplace name and as a plugin entry name in each marketplace. A vendored entry's manifest
        # takes the same name, so the prefix is the 1 failure there.
        hooks = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        spellings = [form for prefix in RESERVED_PREFIXES for form in (prefix, prefix.upper(), prefix.title())]
        spellings.append("anthropic\u017f-")
        for spelling in spellings:
            name = f"{spelling}x"
            for rel, label, change in (
                    (gate.MARKETPLACE, f"{gate.MARKETPLACE} name", lambda d: d.update(name=name)),
                    (gate.MARKETPLACE, f"{gate.MARKETPLACE} plugins[0].name", lambda d: d["plugins"][0].update(name=name)),
                    (gate.VENDORED_MARKETPLACE, f"{gate.VENDORED_MARKETPLACE} name", lambda d: d.update(name=name)),
                    (gate.VENDORED_MARKETPLACE, f"{gate.VENDORED_MARKETPLACE} plugins[0].name",
                     lambda d: d["plugins"][0].update(name=name))):
                with self.subTest(label=label, name=name):
                    saved = {path: (self.root / path).read_bytes() for path in (rel, hooks)}
                    self.edit_json(rel, change)
                    if label == f"{gate.VENDORED_MARKETPLACE} plugins[0].name":
                        self.edit_json(hooks, lambda d: d.update(name=name))
                    try:
                        output = self.expect(1, f"FAIL D1: {label} {name!r} starts with a reserved prefix")
                        if rel == gate.VENDORED_MARKETPLACE:
                            self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                    finally:
                        for path, data in saved.items():
                            (self.root / path).write_bytes(data)

    def test_dependency_faults_fail_d4_in_each_place(self):
        # A dependency that names no plugin, is qualified with another marketplace or an empty one, or is
        # not a name, from an entry and from a plugin manifest of each marketplace.
        hooks = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        for rel, entry, label, plugin, market in (
                (gate.MARKETPLACE, True, ".claude-plugin/marketplace.json plugins[0]", "cleanlanguage", "cleanlanguage"),
                (gate.CLAUDE_MANIFEST, False, gate.CLAUDE_MANIFEST, "cleanlanguage", "cleanlanguage"),
                (gate.VENDORED_MARKETPLACE, True, "plugin/.claude-plugin/marketplace.json plugins[0]",
                 "aiqt-guardrails-hooks", "aiqt-guardrails"),
                (hooks, False, hooks, "aiqt-guardrails-hooks", "aiqt-guardrails")):
            for dep, fault in (("no-such-plugin", "names no plugin"), (f"{plugin}@other", "names no plugin"),
                               (f"{plugin}@", "names no plugin"), ({"name": "x"}, "not a name"), ("", "not a name")):
                with self.subTest(label=label, dep=dep):
                    saved = (self.root / rel).read_bytes()
                    if entry:
                        self.edit_json(rel, lambda d: d["plugins"][0].update(dependencies=[dep]))
                    else:
                        self.edit_json(rel, lambda d: d.update(dependencies=[dep]))
                    if fault == "names no plugin":
                        needle = f"FAIL D4: {label} dependency {dep!r} names no plugin of the marketplace {market!r}"
                    else:
                        needle = f"FAIL D4: {label} names the dependency {dep!r}, not a plugin name"
                    try:
                        output = self.expect(1, needle, "1 dependency read")
                        self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                    finally:
                        (self.root / rel).write_bytes(saved)

    def test_repository_plugins_not_a_list_fails_d1_and_d2(self):
        # A missing plugins list and an object in its place: the FAIL lines, never a traceback.
        for change in (lambda d: d.pop("plugins"), lambda d: d.update(plugins={"name": "cleanlanguage"})):
            with self.subTest(change=change):
                self.write_json(gate.MARKETPLACE, marketplace())
                self.edit_json(gate.MARKETPLACE, change)
                output = self.expect(1, "FAIL D1: .claude-plugin/marketplace.json lists no plugins, not exactly 1",
                                     "FAIL D2: .claude-plugin/marketplace.json has no plugins list")
                self.assertEqual(output.splitlines()[-1], "FAIL: 2 inconsistencies")

    def test_repository_entry_that_is_a_string_fails_d1_and_d2(self):
        # A string that holds "version": the versions check reads only an entry that is an object.
        self.edit_json(gate.MARKETPLACE, lambda d: d.update(plugins=["version"]))
        output = self.expect(1, "FAIL D1: .claude-plugin/marketplace.json plugins[0].name is None, not 'cleanlanguage'",
                             "FAIL D2: .claude-plugin/marketplace.json plugins[0] is not a JSON object")
        self.assertEqual(output.splitlines()[-1], "FAIL: 2 inconsistencies")

    def test_empty_name_listed_twice_fails_d1_once_each(self):
        # 2 entries named "", whose manifest is named "" too: each is not a name, and neither is a plugin
        # listed a second time.
        self.edit_json("plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json", lambda d: d.update(name=""))
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d.update(plugins=[
            {"name": "", "source": "./aiqt-guardrails-hooks"}, {"name": "", "source": "./aiqt-guardrails-hooks"}]))
        output = self.expect(1, "FAIL D1: plugin/.claude-plugin/marketplace.json plugins[0].name is '', not a name",
                             "FAIL D1: plugin/.claude-plugin/marketplace.json plugins[1].name is '', not a name")
        self.assertNotIn("a second time", output)
        self.assertEqual(output.splitlines()[-1], "FAIL: 2 inconsistencies")

    def test_input_folder_that_is_a_file_exits_3(self):
        shutil.rmtree(self.root / "site-src")
        self.write_text("site-src", "x\n")
        self.expect(3, "site-src/site.json could not be read: the component 'site-src' is not a directory")

    def test_os_error_is_shown_by_its_strerror_or_its_message(self):
        # At each place the gate turns an OSError into a refusal: an OSError with no strerror, as one built
        # by hand has, is shown by its message; a fault while a file is read, by its strerror alone.
        with mock.patch.object(gate, "os", FaultyOs("read", None, errno.EIO, "Input/output error")):
            self.expect(3, "check-plugin-distribution: .claude-plugin/marketplace.json could not be read: "
                           "Input/output error\nUNREADABLE: exit 3\n")
        for name, marker, number, code, line in (
                ("lstat", "site-src", None, 3, "site-src/site.json could not be read: no text"),
                ("listdir", "site-src", None, 3, "site-src/site.json could not be read: no text"),
                ("open", "site-src", None, 3, "site-src/site.json could not be read: no text"),
                ("fstat", None, None, 3, ".claude-plugin/marketplace.json could not be read: no text"),
                ("read", None, None, 3, ".claude-plugin/marketplace.json could not be read: no text"),
                ("lstat", "aiqt-guardrails-hooks", None, 3, "plugin/aiqt-guardrails-hooks could not be read: no text"),
                ("listdir", "aiqt-guardrails-hooks", None, 3,
                 "plugin/aiqt-guardrails-hooks could not be listed: no text"),
                ("lstat", "aiqt-guardrails-hooks", errno.ENAMETOOLONG, 1,
                 "FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0].source './aiqt-guardrails-hooks' is not "
                 "a path the operating system accepts: no text")):
            with self.subTest(name=name, marker=marker, number=number):
                with mock.patch.object(gate, "os", FaultyOs(name, marker, number)):
                    if code == 3:
                        self.expect(3, f"check-plugin-distribution: {line}\nUNREADABLE: exit 3\n")
                    else:
                        self.expect(1, f"{line}\n", count=1)

    def test_skill_line_endings_pass(self):
        # Universal newlines: CR LF and a lone CR each end a line as LF does.
        text = f"---\nname: cleanlanguage\n---\n\n# Clean Language\n\nVersion: {VERSION}  \nReleased: 2026-11-08\n"
        for ending in ("\r\n", "\r"):
            with self.subTest(ending=repr(ending)):
                (self.root / gate.SKILL_MD).write_bytes(text.replace("\n", ending).encode("utf-8"))
                self.expect(0, f"at version {VERSION}")

    def test_vendored_entry_versions_are_not_read(self):
        # Other plugins, with versions of their own: neither compared nor required to be a string.
        for version in ("0.4.0", 1, ""):
            with self.subTest(version=version):
                self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(version=version))
                self.expect(0, "OK: D1 to D4 hold")

    def test_gate_runs_as_a_command(self):
        # A copy of the gate in the tree, so its REPO_ROOT is the tree, run as CI runs it.
        script = self.root / "tools" / "check-plugin-distribution.py"
        shutil.copyfile(MODULE_PATH, script)

        def command():
            done = subprocess.run([sys.executable, "-I", str(script)], cwd=self.root, capture_output=True,
                                  text=True, errors="backslashreplace", timeout=120)
            return done.returncode, done.stdout, done.stderr

        code, out, err = command()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.splitlines()[-1].startswith("OK: D1 to D4 hold"), out + err)
        self.assert_lines(code, out, err)
        self.edit_json(gate.SITE_JSON, lambda d: d.update(site_key="jposluns"))
        code, out, err = command()
        self.assertEqual(code, 1, out + err)
        self.assertIn("FAIL D1: site-src/site.json site_key is 'jposluns', not 'cleanlanguage'\n", out)
        self.assertEqual(out.splitlines()[-1], "FAIL: 1 inconsistency")
        self.assert_lines(code, out, err)
        # A missing source whose path holds a line break and a lone surrogate, which printed raw is no
        # UTF-8 text: 1 FAIL line, with both written as escapes.
        self.write_json(gate.SITE_JSON, {"schema": 1, "site_key": "cleanlanguage"})
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(source="./a\nFAIL D9: \udcff"))
        code, out, err = command()
        self.assertEqual(code, 1, out + err)
        self.assertIn("does not resolve: plugin/a\\nFAIL D9: \\udcff is missing\n", out)
        self.assert_lines(code, out, err)
        self.write_json(gate.VENDORED_MARKETPLACE, vendored())
        (self.root / gate.SITE_JSON).unlink()
        code, out, err = command()
        self.assertEqual(code, 3, out + err)
        self.assertIn("site-src/site.json could not be read", err)
        self.assertEqual(err.splitlines()[-1], "UNREADABLE: exit 3")
        self.assert_lines(code, out, err)


class RepositoryTreeTest(unittest.TestCase):
    def test_repository_is_consistent(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = gate.main()
        output = out.getvalue() + err.getvalue()
        self.assertEqual(code, 0, output)
        self.assertTrue(out.getvalue().splitlines()[-1].startswith("OK: D1 to D4 hold"), output)
        self.assertNotIn("FAIL", output)


if __name__ == "__main__":
    unittest.main()
