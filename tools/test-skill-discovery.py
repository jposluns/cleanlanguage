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
        self.expect_exit(1, "must be a canonical './skills/<name>' path")

    def test_skills_entry_traversal_fails(self):
        self.write_manifest({"name": "cleanlanguage", "skills": ["./skills/../../evil"]})
        self.expect_exit(1, "must be a canonical './skills/<name>' path")

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

    def test_duplicate_frontmatter_key_fails(self):
        # Duplicate mapping keys are rejected outright rather than silently kept
        # last-wins, so a second matching name cannot mask a mismatched first value.
        self.skill_md().write_text(
            "---\nname: cleanlanguage\nname: other\ndescription: x\n---\nBody.\n",
            encoding="utf-8",
        )
        self.expect_exit(1, "duplicate key")

    def test_frontmatter_block_scalar_description_fails(self):
        # An empty block scalar parses to an empty string under PyYAML.
        self.skill_md().write_text(
            "---\nname: cleanlanguage\ndescription: |\n---\nBody.\n",
            encoding="utf-8",
        )
        self.expect_exit(1, "must be a non-empty string")

    def test_multiline_block_scalar_description_passes(self):
        # A block scalar with real content parses to a non-empty string.
        self.skill_md().write_text(
            "---\nname: cleanlanguage\ndescription: |\n  Line one.\n  Line two.\n---\nBody.\n",
            encoding="utf-8",
        )
        self.assertEqual(gate.main(), 0)

    def test_invalid_yaml_frontmatter_fails(self):
        self.skill_md().write_text(
            "---\nname: [unclosed\n---\nBody.\n", encoding="utf-8"
        )
        self.expect_exit(1, "is not valid YAML")

    def test_non_mapping_frontmatter_fails(self):
        # Frontmatter that parses to a bare scalar rather than a mapping.
        self.skill_md().write_text(
            "---\njust a scalar\n---\nBody.\n", encoding="utf-8"
        )
        self.expect_exit(1, "is not a YAML mapping")

    def test_whitespace_only_description_fails(self):
        self.skill_md().write_text(
            '---\nname: cleanlanguage\ndescription: " "\n---\nBody.\n',
            encoding="utf-8",
        )
        self.expect_exit(1, "must be a non-empty string")

    # --- 15: name matches directory ----------------------------------------

    def test_name_directory_mismatch_fails(self):
        self.skill_md().write_text(
            make_frontmatter(name="other"), encoding="utf-8"
        )
        self.expect_exit(1, "does not match its directory")

    # --- 16-17: bidirectional reconciliation and eponymous policy ----------

    def test_undeclared_skill_dir_fails(self):
        # C10 reverse reconciliation: an on-disk skill directory with no entry.
        # The needle is unique to C10 (C11 shares the bare "is not declared").
        (self.skills_dir / "extra").mkdir()
        self.expect_exit(1, "skill directory skills/extra is not declared")

    def test_eponymous_skill_absent_fails(self):
        # Only a non-eponymous skill exists and is declared; the plugin's own
        # ./skills/cleanlanguage entry is absent (C11). The needle is unique to
        # C11 (C10 shares the bare "is not declared").
        import shutil

        shutil.rmtree(self.skills_dir / "cleanlanguage")
        self.write_skill("other")
        self.write_manifest({"name": "cleanlanguage", "skills": ["./skills/other"]})
        self.expect_exit(1, "expected skill entry")

    def test_eponymous_name_derived_from_manifest(self):
        # A valid tree whose plugin/skill name is not "cleanlanguage" still passes.
        # This fails if C11's expected entry is ever hardcoded to "cleanlanguage"
        # rather than derived from the manifest name (guard-input-soundness).
        import shutil

        shutil.rmtree(self.skills_dir / "cleanlanguage")
        self.write_skill("otherplug")
        self.write_manifest({"name": "otherplug", "skills": ["./skills/otherplug"]})
        self.assertEqual(gate.main(), 0)

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

    # --- 22-23: Claude manifest load (C0) ----------------------------------

    def test_malformed_manifest_json_fails(self):
        self.claude_manifest.write_text("{not json", encoding="utf-8")
        self.expect_exit(1, "is not valid JSON")

    def test_non_object_manifest_fails(self):
        self.claude_manifest.write_text("[1, 2, 3]", encoding="utf-8")
        self.expect_exit(1, "is not a JSON object")

    # --- 24: duplicate skills entry ----------------------------------------

    def test_duplicate_skills_entry_fails(self):
        self.write_manifest(
            {
                "name": "cleanlanguage",
                "skills": ["./skills/cleanlanguage", "./skills/cleanlanguage"],
            }
        )
        self.expect_exit(1, "is declared more than once")

    # --- 25-27: declared entry disk shape (C4/C5) --------------------------

    def test_skill_entry_resolves_to_file_fails(self):
        # A declared entry that resolves to a file, not a directory, under skills/.
        (self.skills_dir / "afile").write_text("x", encoding="utf-8")
        self.write_manifest(
            {
                "name": "cleanlanguage",
                "skills": ["./skills/cleanlanguage", "./skills/afile"],
            }
        )
        self.expect_exit(1, "is not a directory under skills/")

    def test_symlink_skill_md_fails(self):
        # SKILL.md is a symlink to a valid regular file inside the plugin (C5).
        target = self.skills_dir / "cleanlanguage" / "real.md"
        target.write_text(make_frontmatter(name="cleanlanguage"), encoding="utf-8")
        self.skill_md().unlink()
        os.symlink(str(target), str(self.skill_md()))
        self.expect_exit(1, "must be a regular file, not a symlink")

    def test_non_regular_skill_md_fails(self):
        # SKILL.md is a directory, not a regular file (C5).
        self.skill_md().unlink()
        self.skill_md().mkdir()
        self.expect_exit(1, "SKILL.md is missing")

    # --- 28-29: reverse reconciliation and legacy symlink (C10/C12) --------

    def test_undeclared_symlink_alias_dir_fails(self):
        # An on-disk skills/alias symlink to the declared skills/cleanlanguage is
        # itself an undeclared skill directory (C10).
        os.symlink(
            str(self.skills_dir / "cleanlanguage"),
            str(self.skills_dir / "alias"),
        )
        self.expect_exit(1, "skills/alias is not declared")

    def test_dangling_legacy_symlink_fails(self):
        # A legacy cleanlanguage/SKILL.md that is a dangling symlink (C12).
        os.symlink(str(self.plugin_root / "nonexistent"), str(self.legacy_skill))
        self.expect_exit(1, "legacy")

    # --- 30: reverse reconciliation fails closed on an unreadable skills/ ---

    def test_skills_dir_unreadable_fails_closed(self):
        # C10's iterdir must fail closed (exit 3) when skills/ cannot be listed.
        # chmod on the directory trips an earlier per-entry check rather than the
        # iterdir path (and would be a no-op as root), so drive the OSError at
        # iterdir directly; the mock leaves no unreadable temp dir behind.
        from unittest import mock

        with mock.patch.object(
            gate.Path, "iterdir", side_effect=OSError("Permission denied")
        ):
            self.expect_exit(3, "could not be read")

    # --- 21: CRLF frontmatter tolerated ------------------------------------

    def test_name_with_surrounding_whitespace_fails(self):
        # The frontmatter name is compared verbatim to the directory basename, so a
        # whitespace-padded name that would strip-match is still a mismatch (C9).
        self.skill_md().write_text(
            "---\nname: ' cleanlanguage '\ndescription: x\n---\nBody.\n",
            encoding="utf-8",
        )
        self.expect_exit(1, "does not match its directory")

    def test_manifest_name_missing_fails(self):
        # The manifest name is load-bearing for C11; a missing name fails closed with
        # a clear message rather than resolving an './skills/None' entry (C0).
        self.write_manifest({"skills": ["./skills/cleanlanguage"]})
        self.expect_exit(1, "'name' is missing or not a non-empty string")

    def test_entry_reaching_skill_via_sibling_path_fails(self):
        # codex round-2 HIGH: an entry outside './skills/' that resolves into skills/
        # through a symlink, paired with an undeclared same-basename skills/<x>
        # directory, previously passed by basename reconciliation. It must now be
        # rejected at entry syntax.
        (self.skills_dir / "extra").mkdir()  # undeclared, no SKILL.md
        (self.plugin_root / "elsewhere").mkdir()
        os.symlink(
            str(self.skills_dir / "cleanlanguage"),
            str(self.plugin_root / "elsewhere" / "extra"),
        )
        self.write_manifest(
            {
                "name": "cleanlanguage",
                "skills": ["./skills/cleanlanguage", "./elsewhere/extra"],
            }
        )
        self.expect_exit(1, "must be a canonical './skills/<name>' path")

    def test_deeply_nested_frontmatter_fails_closed(self):
        # Deeply nested YAML raises RecursionError, which PyYAML does not wrap as a
        # YAMLError; the gate catches it and fails closed (exit 3) rather than letting
        # a traceback escape.
        body = "[" * 5000 + "]" * 5000
        self.skill_md().write_text(f"---\n{body}\n---\nBody.\n", encoding="utf-8")
        self.expect_exit(3, "could not be decoded")

    def test_entry_metadata_oserror_fails_closed(self):
        # A filesystem-metadata error while inspecting a declared entry fails closed
        # (exit 3) rather than escaping as an uncaught OSError.
        from unittest import mock

        with mock.patch.object(
            gate.Path, "is_dir", side_effect=OSError("Permission denied")
        ):
            self.expect_exit(3, "could not be inspected")

    def test_crlf_frontmatter_passes(self):
        self.skill_md().write_bytes(
            b"---\r\nname: cleanlanguage\r\ndescription: x\r\n---\r\nBody.\r\n"
        )
        self.assertEqual(gate.main(), 0)


if __name__ == "__main__":
    unittest.main()
