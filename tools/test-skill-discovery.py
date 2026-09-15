#!/usr/bin/env python3
"""Tests for check-skill-discovery.py.

Patch the gate's path constants to a temp fixture and drive every failure and
success branch offline with the standard library. The fixture tree mirrors the
real layout: <tmp>/cleanlanguage/.claude-plugin/plugin.json declares the skills
array, and each skill lives at <tmp>/cleanlanguage/skills/<name>/SKILL.md.

Each case perturbs only its one input from the valid baseline, so it is
failing-first for its own branch.
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

MODULE_PATH = Path(__file__).resolve().parent / "check-skill-discovery.py"
spec = importlib.util.spec_from_file_location("check_skill_discovery", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def make_frontmatter(name="cleanlanguage", description="Clean Language prose standard."):
    return f"---\nname: {name}\ndescription: {description}\n---\nBody text.\n"


class SkillDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.plugin_root = self.root / "cleanlanguage"
        self.skills_dir = self.plugin_root / "skills"
        self.claude_manifest = self.plugin_root / ".claude-plugin" / "plugin.json"
        self.legacy_skill = self.plugin_root / "SKILL.md"

        self._saved = (
            gate.REPO_ROOT,
            gate.PLUGIN_ROOT,
            gate.CLAUDE_MANIFEST,
            gate.LEGACY_SKILL,
        )
        gate.REPO_ROOT = self.root
        gate.PLUGIN_ROOT = self.plugin_root
        gate.CLAUDE_MANIFEST = self.claude_manifest
        gate.LEGACY_SKILL = self.legacy_skill

        # Valid baseline: one declared, on-disk, conforming skill.
        self.claude_manifest.parent.mkdir(parents=True)
        self.write_skill("cleanlanguage")
        self.write_manifest({"name": "cleanlanguage", "skills": ["./skills/cleanlanguage"]})

    def tearDown(self):
        (
            gate.REPO_ROOT,
            gate.PLUGIN_ROOT,
            gate.CLAUDE_MANIFEST,
            gate.LEGACY_SKILL,
        ) = self._saved
        self._tmp.cleanup()

    # --- fixture builders --------------------------------------------------

    def write_manifest(self, manifest):
        self.claude_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    def write_skill(self, dirname, text=None):
        skill_dir = self.skills_dir / dirname
        skill_dir.mkdir(parents=True, exist_ok=True)
        if text is None:
            text = make_frontmatter(name=dirname)
        (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")

    def skill_md(self, dirname="cleanlanguage"):
        return self.skills_dir / dirname / "SKILL.md"

    # --- assertions --------------------------------------------------------

    def expect_exit(self, code, needle):
        err = io.StringIO()
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(err):
            gate.main()
        self.assertEqual(caught.exception.code, code)
        self.assertIn(needle, err.getvalue())

    # --- 1: happy path -----------------------------------------------------

    def test_valid_passes(self):
        self.assertEqual(gate.main(), 0)

    # --- 2-6: skills array shape and entry syntax --------------------------

    def test_no_skills_array_fails(self):
        self.write_manifest({"name": "cleanlanguage"})
        self.expect_exit(1, "has no 'skills' array")

    def test_skills_entry_not_string_fails(self):
        self.write_manifest({"name": "cleanlanguage", "skills": [123]})
        self.expect_exit(1, "is not a string")

    def test_skills_entry_no_dot_slash_fails(self):
        self.write_manifest({"name": "cleanlanguage", "skills": ["skills/cleanlanguage"]})
        self.expect_exit(1, "must be a canonical plugin-relative path")

    def test_skills_entry_traversal_fails(self):
        self.write_manifest({"name": "cleanlanguage", "skills": ["./skills/../../evil"]})
        self.expect_exit(1, "must be a canonical plugin-relative path")

    def test_skills_entry_symlink_escape_fails(self):
        # An in-fixture symlink under skills/ that points outside the tmp root;
        # the entry is syntactically canonical but resolves out of the plugin.
        os.symlink(str(self.root.parent), str(self.skills_dir / "escape"))
        self.write_manifest({"name": "cleanlanguage", "skills": ["./skills/escape"]})
        self.expect_exit(1, "resolves outside the plugin root")

    # --- 7-8: declared path exists on disk ---------------------------------

    def test_skill_dir_missing_fails(self):
        self.write_manifest({"name": "cleanlanguage", "skills": ["./skills/missing"]})
        self.expect_exit(1, "does not exist")

    def test_skill_md_missing_fails(self):
        self.skill_md().unlink()
        self.expect_exit(1, "SKILL.md is missing")

    # --- 9-14: frontmatter parsing -----------------------------------------

    def test_no_frontmatter_block_fails(self):
        self.skill_md().write_text("# Title\nno frontmatter here.\n", encoding="utf-8")
        self.expect_exit(1, "no YAML frontmatter block")

    def test_unterminated_frontmatter_fails(self):
        self.skill_md().write_text(
            "---\nname: cleanlanguage\ndescription: x\nBody with no close.\n",
            encoding="utf-8",
        )
        self.expect_exit(1, "unterminated YAML frontmatter")

    def test_frontmatter_missing_name_fails(self):
        self.skill_md().write_text(
            "---\ndescription: x\n---\nBody.\n", encoding="utf-8"
        )
        self.expect_exit(1, "missing 'name'")

    def test_frontmatter_missing_description_fails(self):
        self.skill_md().write_text(
            "---\nname: cleanlanguage\n---\nBody.\n", encoding="utf-8"
        )
        self.expect_exit(1, "missing 'description'")

    def test_frontmatter_duplicate_name_fails(self):
        self.skill_md().write_text(
            "---\nname: cleanlanguage\nname: cleanlanguage\ndescription: x\n---\nBody.\n",
            encoding="utf-8",
        )
        self.expect_exit(1, "duplicate")

    def test_frontmatter_block_scalar_description_fails(self):
        self.skill_md().write_text(
            "---\nname: cleanlanguage\ndescription: >-\n  folded value\n---\nBody.\n",
            encoding="utf-8",
        )
        self.expect_exit(1, "does not parse")

    # --- 15: name matches directory ----------------------------------------

    def test_name_directory_mismatch_fails(self):
        self.skill_md().write_text(
            make_frontmatter(name="other"), encoding="utf-8"
        )
        self.expect_exit(1, "does not match its directory")

    # --- 16-17: bidirectional reconciliation and eponymous policy ----------

    def test_undeclared_skill_dir_fails(self):
        (self.skills_dir / "extra").mkdir()
        self.expect_exit(1, "is not declared")

    def test_eponymous_skill_absent_fails(self):
        # Only a non-eponymous skill exists and is declared; the plugin's own
        # ./skills/cleanlanguage entry is absent.
        import shutil

        shutil.rmtree(self.skills_dir / "cleanlanguage")
        self.write_skill("other")
        self.write_manifest({"name": "cleanlanguage", "skills": ["./skills/other"]})
        self.expect_exit(1, "is not declared")

    # --- 18: legacy relocation guard ---------------------------------------

    def test_legacy_root_skill_md_fails(self):
        self.legacy_skill.write_text("legacy\n", encoding="utf-8")
        self.expect_exit(1, "legacy")

    # --- 19-20: unreadable inputs fail closed ------------------------------

    def test_unreadable_skill_md_fails_closed(self):
        self.skill_md().write_bytes(b"\xff")
        self.expect_exit(3, "could not be read")

    def test_unreadable_manifest_fails_closed(self):
        self.claude_manifest.write_bytes(b"\xff")
        self.expect_exit(3, "could not be read")

    # --- 21: CRLF frontmatter tolerated ------------------------------------

    def test_crlf_frontmatter_passes(self):
        self.skill_md().write_bytes(
            b"---\r\nname: cleanlanguage\r\ndescription: x\r\n---\r\nBody.\r\n"
        )
        self.assertEqual(gate.main(), 0)


if __name__ == "__main__":
    unittest.main()
