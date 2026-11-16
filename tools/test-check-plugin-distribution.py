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
cases that require only the exact last line: the count line for 1 and for 2
inconsistencies, and "UNREADABLE: exit 3".

- The names check fails on: the marketplace named jposluns; a plugin entry
  name that differs from the manifest name; a second plugin entry or none; a
  Claude or Agent Plugins manifest name or a site key that differs; a vendored
  entry named unlike the manifest it reaches; a marketplace name that is
  missing or empty; a marketplace name or a plugin entry name that starts
  with each reserved prefix, in lower case or in another letter case; each
  name and the site key that differ from cleanlanguage only in letter case;
  and, with the FAIL lines and the count line and no traceback, a plugin
  entry name that is an array or an object, a marketplace name that is an
  array where a qualified dependency reads it, and a manifest name that is
  an array where its entry and its own dependencies read it; and a plugin
  name listed twice in the repository's marketplace and in the vendored
  one, there also in another letter case.
- The sources check fails on: a missing source folder; a source with a "..",
  a "." or an empty component, the "." in each marketplace; a source with a
  NUL character or with a character the file system encoding cannot hold;
  a source with a component too long for the file system, in each
  marketplace; a source in each marketplace, or a .claude-plugin folder,
  spelled in another letter case on a file system that folds letter case,
  which the case imitates by giving the gate an os.lstat, an os.open and
  an os.listdir that fold letter case; a source without "./"; a
  source that is a file; a manifest that is a directory; a symlinked source
  folder, a symlinked .claude-plugin folder or a symlinked manifest; an
  entry with no source; an object source; a vendored marketplace with no
  plugins list or with an entry that is not an object; and a source of the
  repository's entry that reaches another plugin or a copy of this one.
- The versions check fails on: a version that differs in the Claude
  manifest, the Agent Plugins manifest, the SKILL.md Version: line or a
  marketplace entry; a version that is missing, empty or not a string; and a
  SKILL.md with no Version: line.
- The dependencies check fails on: a dependency that names no plugin of its
  marketplace, is qualified with another marketplace or with an empty one
  (a name and "@" alone), or names the plugin itself, from a marketplace
  entry, as a bare or a qualified name, or from a plugin manifest; on a
  plugin that 1 list names twice, as the same bare name, as a bare and a
  qualified name, or in a plugin manifest; and on dependencies that are not
  a list, a JSON null in a marketplace entry and in a plugin manifest of
  each marketplace among them, or not names, an empty string among them.
  Dependencies that
  resolve pass, among them 2 that a plugin entry holds on 2 other plugins of
  its marketplace, and 3 lists that each name the same plugin once.
- Exit 3 holds for: a repeated JSON key; a missing file; a file that is not a
  regular file; an input file and a source folder that deny permission;
  NaN; JSON nested 1 level deeper than the gate's bound of 64, which every
  supported Python decodes, in arrays and in objects, while JSON at the
  bound passes, in arrays with escaped quotes and brackets inside a string
  and in objects, and so does JSON nested 3 levels deep that holds more
  than 64 arrays, or more than 64 objects, in all; a JSON file that is not
  an object; a file or a SKILL.md that is not UTF-8; a symlinked input file
  or input folder; an input folder spelled in another letter case on a file
  system that folds letter case, imitated as above; and an extractor that
  is missing, symlinked, raises an exception
  or SystemExit while it loads, lacks VERSION_LINE or SKILL_VERSION, or
  holds either as a pattern of bytes.
- Run as a command, the gate exits 0, 1 and 3 with the same last lines.
- The count lines read "1 relative source", "1 dependency" and "FAIL: 1
  inconsistency" for 1, and the plural for 0 and for more than 1.

A last case runs the gate on the repository itself and requires exit 0 and a
last line "OK:", so this test fails while the repository's own names,
sources, versions or dependencies disagree.

The permission cases need a user whose permissions the file system enforces,
so they are skipped when the test runs as root.

The SKILL.md version is read by a copy of the real tools/skill-version.py in
each tree, which the gate reaches from REPO_ROOT like every other file.

Usage: python3 -I tools/test-check-plugin-distribution.py
Exit status: 0 when every case passes, 1 otherwise.
"""

from __future__ import annotations

import contextlib
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
spec = importlib.util.spec_from_file_location("check_plugin_distribution", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

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
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = gate.main()
        return code, out.getvalue(), err.getvalue()

    def expect(self, code: int, *needles: str):
        got, out, err = self.run_gate()
        output = out + err
        self.assertEqual(got, code, output)
        for needle in needles:
            self.assertIn(needle, output)
        stream, start = {0: (out, "OK: "), 1: (out, "FAIL: "), 3: (err, "UNREADABLE: exit 3")}[code]
        last = (stream.splitlines() or [""])[-1]
        self.assertTrue(last.startswith(start), f"last line {last!r} does not start {start!r}\n{output}")
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
                       "linked is a symlink")

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
        self.expect(3, "plugin/.claude-plugin/marketplace.json could not be read")

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
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(
            source={"source": "github", "repo": "someone/else"}))
        self.expect(1, "FAIL D2: .claude-plugin/marketplace.json plugins[0].source {'source': 'github', 'repo': "
                       "'someone/else'} is not a string, so this gate cannot read where it leads",
                    "1 relative source resolved")

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
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(source="cleanlanguage"))
        self.expect(1, "FAIL D2: .claude-plugin/marketplace.json plugins[0].source 'cleanlanguage' does not start "
                       "with './'")

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
        self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].pop("source"))
        self.expect(1, "FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0] has no source")

    def test_missing_manifest_version_fails_d3(self):
        self.edit_json(gate.CLAUDE_MANIFEST, lambda d: d.pop("version"))
        self.expect(1, "FAIL D3: cleanlanguage/.claude-plugin/plugin.json version is None, not a version")

    def test_entry_version_not_a_string_fails_d3(self):
        self.edit_json(gate.MARKETPLACE, lambda d: d["plugins"][0].update(version=1.0))
        self.expect(1, "FAIL D3: .claude-plugin/marketplace.json plugins[0].version is 1.0, not a version")

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
                       "does not resolve: plugin/aiqt-guardrails-hooks/.claude-plugin is a symlink")

    def test_symlinked_manifest_fails_d2(self):
        path = self.root / "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
        path.rename(path.with_name("real.json"))
        os.symlink(path.with_name("real.json"), path)
        self.expect(1, "FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0].source './aiqt-guardrails-hooks' "
                       "does not resolve: plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json is a symlink")

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
        self.expect(1, "FAIL D3: cleanlanguage/plugin.json version is '', not a version")

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
        for source in ("./aiqt-guardrails-hooks/", ".//aiqt-guardrails-hooks"):
            with self.subTest(source=source):
                self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(source=source))
                self.expect(1, f"FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0].source '{source}' has "
                               "an empty, '.' or '..' component")

    # The extractor: reached from REPO_ROOT, and exit 3 when it cannot be used.

    def test_extractor_without_a_pattern_exits_3(self):
        for name in ("VERSION_LINE", "SKILL_VERSION"):
            with self.subTest(name=name):
                shutil.copyfile(REAL_EXTRACTOR, self.root / EXTRACTOR_REL)
                self.edit_extractor(f"{name} = re.compile", f"{name}_GONE = re.compile")
                self.expect(3, f"the extractor tools/skill-version.py could not be used: it has no {name} "
                               "pattern of text")

    def test_extractor_raising_while_it_loads_exits_3(self):
        for statement, shown in (("raise RuntimeError('broken')", "RuntimeError: broken"),
                                 ("raise SystemExit(0)", "SystemExit: 0")):
            with self.subTest(statement=statement):
                shutil.copyfile(REAL_EXTRACTOR, self.root / EXTRACTOR_REL)
                self.edit_extractor('PROG = "skill-version"\n', f'PROG = "skill-version"\n{statement}\n')
                self.expect(3, f"the extractor tools/skill-version.py could not be loaded: {shown}")

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
        for source, shown in (("./a\x00b", "'./a\\x00b'"), ("./\ud800", "'./\\ud800'")):
            with self.subTest(source=shown):
                self.edit_json(gate.VENDORED_MARKETPLACE, lambda d: d["plugins"][0].update(source=source))
                self.expect(1, f"FAIL D2: plugin/.claude-plugin/marketplace.json plugins[0].source {shown} is not a "
                               "path the operating system accepts")

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
                                            "system accepts: ", "1 relative source resolved")
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
        folder = self.root / "plugin/aiqt-guardrails-hooks/.claude-plugin"
        for rel, source, rename, shown in (
                (gate.MARKETPLACE, "./CleanLanguage", False, "CleanLanguage"),
                (gate.VENDORED_MARKETPLACE, "./AIQT-Guardrails-Hooks", False, "plugin/AIQT-Guardrails-Hooks"),
                (gate.VENDORED_MARKETPLACE, "./aiqt-guardrails-hooks", True,
                 "plugin/aiqt-guardrails-hooks/.claude-plugin")):
            with self.subTest(source=source, rename=rename):
                saved = (self.root / rel).read_bytes()
                self.edit_json(rel, lambda d: d["plugins"][0].update(source=source))
                if rename:
                    folder.rename(folder.with_name(".Claude-Plugin"))
                try:
                    with mock.patch.object(gate, "os", FoldingOs(self.root)):
                        output = self.expect(1, f"FAIL D2: {rel} plugins[0].source '{source}' does not resolve: {shown} "
                                                "is not spelled as its folder lists it", "1 relative source resolved")
                    self.assertNotIn("reaches", output)
                    self.assertEqual(output.splitlines()[-1], "FAIL: 1 inconsistency")
                finally:
                    (self.root / rel).write_bytes(saved)
                    if rename:
                        folder.with_name(".Claude-Plugin").rename(folder)

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
    def denied(self, rel: str):
        """rel with every permission taken away, given back before the tree is removed."""
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root is not refused by file permissions")
        path = self.root / rel
        mode = path.stat().st_mode
        path.chmod(0)
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

    def test_gate_runs_as_a_command(self):
        # A copy of the gate in the tree, so its REPO_ROOT is the tree, run as CI runs it.
        script = self.root / "tools" / "check-plugin-distribution.py"
        shutil.copyfile(MODULE_PATH, script)

        def command():
            done = subprocess.run([sys.executable, "-I", str(script)], cwd=self.root, capture_output=True,
                                  text=True, timeout=120)
            return done.returncode, done.stdout, done.stderr

        code, out, err = command()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.splitlines()[-1].startswith("OK: D1 to D4 hold"), out + err)
        self.edit_json(gate.SITE_JSON, lambda d: d.update(site_key="jposluns"))
        code, out, err = command()
        self.assertEqual(code, 1, out + err)
        self.assertIn("FAIL D1: site-src/site.json site_key is 'jposluns', not 'cleanlanguage'\n", out)
        self.assertEqual(out.splitlines()[-1], "FAIL: 1 inconsistency")
        (self.root / gate.SITE_JSON).unlink()
        code, out, err = command()
        self.assertEqual(code, 3, out + err)
        self.assertIn("site-src/site.json could not be read", err)
        self.assertEqual(err.splitlines()[-1], "UNREADABLE: exit 3")


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
