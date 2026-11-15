#!/usr/bin/env python3
"""Tests for tools/check-plugin-distribution.py.

Each case builds a temporary tree that holds the files the gate reads, points
the gate's REPO_ROOT at it, as tools/test-agent-plugin-manifest.py points that
gate's paths at a fixture, and runs the gate's main. The conforming tree must
pass; each case then changes 1 thing and requires the exit status and the tag
of the failing check in the output, as the gate's CHECKS holds it: the
marketplace named jposluns, a plugin entry name that differs from the manifest
name, a second plugin entry and a reserved name prefix fail the names check; a
missing source folder, a source with a ".." component and a symlinked source
fail the sources check; a version that differs in the Claude manifest, the
Agent Plugins manifest, the SKILL.md Version: line or a marketplace entry fails
the versions check; a dependency that names no plugin of its marketplace fails
the dependencies check, while one that does passes with its count printed; a
repeated JSON key, a missing file and a file that is not a regular file
exit 3. Further cases hold the gate's other claims: a source of the
repository's entry that reaches another plugin or a copy of this one, an
object source, an empty plugins list, a differing Agent Plugins manifest name
or site key, a vendored entry named unlike the manifest it reaches, a source
without "./", a source that is a file, a manifest that is a directory, an
entry with no source, a version that is missing or not a string, a SKILL.md
with no Version: line, a dependency qualified with another marketplace and
dependencies that are not a list or not names each fail their check; NaN, a
JSON file that is not an object, a file or a SKILL.md that is not UTF-8 and a
symlinked input file exit 3. A last case runs the gate on the repository
itself, so this test fails while the repository's own names, sources,
versions or dependencies disagree.

The SKILL.md version is read by the real tools/skill-version.py, which the
gate loads from beside itself.

Usage: python3 -I tools/test-check-plugin-distribution.py
Exit status: 0 when every case passes, 1 otherwise.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "check-plugin-distribution.py"
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
        return code, out.getvalue() + err.getvalue()

    def expect(self, code: int, *needles: str):
        got, output = self.run_gate()
        self.assertEqual(got, code, output)
        for needle in needles:
            self.assertIn(needle, output)
        return output

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
                       "empty or '..' component")

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
                       "'cleanlanguage' names no plugin", "1 dependencies read")

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
                    "1 relative sources resolved")

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


class RepositoryTreeTest(unittest.TestCase):
    def test_repository_is_consistent(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = gate.main()
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())


if __name__ == "__main__":
    unittest.main()
