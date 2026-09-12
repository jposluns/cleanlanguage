#!/usr/bin/env python3
"""Tests for check-release-links.py's skill-version parsing.

The gate reads the current version from the first ``Version:`` line of
``cleanlanguage/SKILL.md``. These tests pin the failure paths, which reject a
malformed, missing, or unreadable version before the gate walks the site, so no
site fixture is needed. They run offline with the standard library: the fixtures
patch the module's file paths.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "check-release-links.py"
spec = importlib.util.spec_from_file_location("check_release_links", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class VersionParseTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = (
            gate.REPO_ROOT, gate.SITE_ROOT, gate.SKILL,
            gate.REDIRECTS, gate.VERIFY_PAGE,
        )
        root = Path(self._tmp.name)
        gate.REPO_ROOT = root
        gate.SITE_ROOT = root / "site"
        gate.SKILL = root / "SKILL.md"
        gate.REDIRECTS = root / "_redirects"
        gate.VERIFY_PAGE = root / "verify.html"
        # REDIRECTS and VERIFY_PAGE must exist so main() reaches the version
        # parse; each test writes SKILL.md itself. SITE_ROOT is left absent, so a
        # test that parses a valid version would find no links and pass, while
        # these tests all fail at the parse before the site walk.
        gate.REDIRECTS.write_text("", encoding="utf-8")
        gate.VERIFY_PAGE.write_text("", encoding="utf-8")

    def tearDown(self):
        (gate.REPO_ROOT, gate.SITE_ROOT, gate.SKILL, gate.REDIRECTS,
         gate.VERIFY_PAGE) = self._saved
        self._tmp.cleanup()

    def _expect_die(self, needle: str):
        # Assert both exit 3 AND the version-parse-specific message, so a test
        # cannot pass on an unrelated later exit-3 path (for example the empty
        # SITE_ROOT reporting no release URLs).
        err = io.StringIO()
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(err):
            gate.main()
        self.assertEqual(caught.exception.code, 3)
        self.assertIn(needle, err.getvalue())

    def test_malformed_first_version_line_is_rejected(self):
        # The first Version line is authoritative; a malformed first line must
        # fail rather than fall through to a later valid one.
        gate.SKILL.write_text(
            "Version: 9.9.9 trailing\nVersion: 1.2.3\n", encoding="utf-8"
        )
        self._expect_die("not a bare X.Y.Z version")

    def test_dotted_version_is_rejected(self):
        gate.SKILL.write_text("Version: 1.0.\n", encoding="utf-8")
        self._expect_die("not a bare X.Y.Z version")

    def test_missing_version_line_is_rejected(self):
        gate.SKILL.write_text("name: cleanlanguage\n", encoding="utf-8")
        self._expect_die("no 'Version:' line found")

    def test_non_utf8_skill_is_rejected(self):
        gate.SKILL.write_bytes(b"Version: 1.0.14\xff\n")
        self._expect_die("could not be read")


if __name__ == "__main__":
    unittest.main()
