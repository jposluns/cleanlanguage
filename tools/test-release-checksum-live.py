#!/usr/bin/env python3
"""Tests for the live checksum gate's conditional 404 pass.

The gate must not pass unconditionally when the release the verify page names
is not published. It passes on a 404 only in the legitimate pre-tag window:
the site names the current skill version and the tag does not exist yet. A
mismatched unreleased version fails, a tag with no published release is
unverifiable, and the published-release comparison and the transient-error
handling are preserved. Once the release SKILL.md names is published, its
Released line (item 26) must name the UTC day of the release published_at
record (G4); the network read of that record is replaced by injected
fixtures. These tests pin all of that offline: the fixtures
patch the module's file paths and network readers, so no gh CLI and no
network access are needed. The CI workflow invokes this file before the gate
itself runs against the real pages, so the regression proof runs even when
the network gate cannot.
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "check-release-checksum-live.py"
spec = importlib.util.spec_from_file_location("check_release_checksum_live", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

CURRENT = "1.0.14"
AHEAD = "1.0.15"
BOGUS = "9.9.9"
ZIP_BYTES = b"not a real zip, but hashing does not care"
ZIP_SUM = hashlib.sha256(ZIP_BYTES).hexdigest()
OTHER_SUM = "f" * 64

VERIFY = """<!doctype html>
<html><body>
<p>The published checksum for version {version} is:</p>
<pre><code id="published-checksum">{checksum}</code></pre>
</body></html>
"""


def unexpected_call(*args, **kwargs):
    raise AssertionError(f"unexpected call: {args}")


class ConditionalPassTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = (
            gate.REPO_ROOT, gate.VERIFY_PAGE, gate.SKILL,
            gate.release_status, gate.tag_status, gate.gh,
            gate.release_published_at,
        )
        root = Path(self._tmp.name)
        gate.REPO_ROOT = root
        gate.VERIFY_PAGE = root / "index.html"
        gate.SKILL = root / "SKILL.md"
        gate.release_status = unexpected_call
        gate.tag_status = unexpected_call
        gate.gh = unexpected_call
        gate.release_published_at = unexpected_call

    def tearDown(self):
        (gate.REPO_ROOT, gate.VERIFY_PAGE, gate.SKILL, gate.release_status,
         gate.tag_status, gate.gh, gate.release_published_at) = self._saved
        self._tmp.cleanup()

    def fixtures(self, site_version, site_sum, skill_version, released=None):
        gate.VERIFY_PAGE.write_text(
            VERIFY.format(version=site_version, checksum=site_sum), encoding="utf-8"
        )
        text = f"Version: {skill_version}  \n"
        if released is not None:
            text += f"{released}\n"
        gate.SKILL.write_text(text, encoding="utf-8")

    def fake_download(self, *args, check=True):
        self.assertEqual(args[:2], ("release", "download"))
        self.assertIn("--repo", args)
        self.assertEqual(args[args.index("--repo") + 1], "jposluns/cleanlanguage")
        version = args[2].removeprefix("v")
        target = Path(args[args.index("--dir") + 1])
        (target / f"cleanlanguage-{version}.zip").write_bytes(ZIP_BYTES)
        (target / f"cleanlanguage-{version}.zip.sha256").write_text(
            f"{ZIP_SUM}  cleanlanguage-{version}.zip", encoding="utf-8"
        )
        return subprocess.CompletedProcess(args, 0, "", "")

    def published(self, published_at):
        """Stand in for the release record read, recording each tag asked for."""
        self.asked = []

        def reader(tag):
            self.asked.append(tag)
            return published_at

        gate.release_published_at = reader
        gate.release_status = lambda tag: 200
        gate.gh = self.fake_download

    # --- G4 (item 26): the Released line against the release record ---------

    def test_released_date_matching_published_day_passes(self):
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-15T23:59:59Z")
        self.assertEqual(gate.main(), 0)
        self.assertEqual(self.asked, [f"v{AHEAD}"])

    def test_released_date_differing_from_published_day_fails(self):
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-16T00:00:01Z")
        self.assertEqual(gate.main(), 1)

    def test_missing_released_line_above_baseline_fails(self):
        self.fixtures(AHEAD, ZIP_SUM, AHEAD)
        self.published("2026-11-15T09:30:00Z")
        self.assertEqual(gate.main(), 1)
        self.assertEqual(self.asked, [])

    def test_missing_released_line_at_baseline_passes(self):
        self.fixtures(CURRENT, ZIP_SUM, CURRENT)
        self.published("2026-11-15T09:30:00Z")
        self.assertEqual(gate.main(), 0)
        self.assertEqual(self.asked, [])

    def test_unusable_published_at_is_unverifiable(self):
        for value in ("null", "", "2026-11-15", "2026-11-15T09:30:00+01:00"):
            with self.subTest(value):
                self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
                self.published(value)
                with self.assertRaises(SystemExit) as caught:
                    gate.main()
                self.assertEqual(caught.exception.code, 2)

    def test_malformed_released_line_on_published_path_exits_3(self):
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: soon")
        self.published("2026-11-15T09:30:00Z")
        with self.assertRaises(SystemExit) as caught:
            gate.main()
        self.assertEqual(caught.exception.code, 3)

    def test_site_naming_an_older_release_skips_the_date_check(self):
        # After a bump, SKILL.md is ahead of the published release the site
        # still names; the date belongs to the unpublished version, so the
        # published release record is not compared with it.
        self.fixtures(CURRENT, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2020-01-01T00:00:00Z")
        self.assertEqual(gate.main(), 0)
        self.assertEqual(self.asked, [])

    def test_published_at_reader_fails_closed_on_gh_error(self):
        # The real reader: a gh failure is unverifiable, never an empty value.
        gate.release_published_at = self._saved[6]
        gate.gh = lambda *args, check=True: subprocess.CompletedProcess(args, 1, "", "HTTP 502")
        with self.assertRaises(SystemExit) as caught:
            gate.release_published_at("v1.0.15")
        self.assertEqual(caught.exception.code, 2)

    def test_published_at_reader_asks_for_the_published_at_field(self):
        gate.release_published_at = self._saved[6]
        seen = []

        def fake(*args, check=True):
            seen.append(args)
            return subprocess.CompletedProcess(args, 0, "2026-11-15T09:30:00Z\n", "")

        gate.gh = fake
        self.assertEqual(gate.release_published_at("v1.0.15"), "2026-11-15T09:30:00Z")
        self.assertEqual(
            seen,
            [("api", "repos/jposluns/cleanlanguage/releases/tags/v1.0.15", "--jq", ".published_at")],
        )

    def test_published_release_with_matching_checksum_passes(self):
        self.fixtures(CURRENT, ZIP_SUM, CURRENT)
        gate.release_status = lambda tag: 200
        gate.gh = self.fake_download
        self.assertEqual(gate.main(), 0)

    def test_published_release_with_drift_still_fails(self):
        self.fixtures(CURRENT, OTHER_SUM, CURRENT)
        gate.release_status = lambda tag: 200
        gate.gh = self.fake_download
        self.assertEqual(gate.main(), 1)

    def test_pre_tag_window_passes(self):
        self.fixtures(AHEAD, OTHER_SUM, AHEAD)
        gate.release_status = lambda tag: 404
        gate.tag_status = lambda tag: 404
        self.assertEqual(gate.main(), 0)

    def test_unreleased_version_that_is_not_current_fails(self):
        self.fixtures(BOGUS, OTHER_SUM, CURRENT)
        gate.release_status = lambda tag: 404
        self.assertEqual(gate.main(), 1)

    def test_tag_without_release_is_unverifiable(self):
        self.fixtures(AHEAD, OTHER_SUM, AHEAD)
        gate.release_status = lambda tag: 404
        gate.tag_status = lambda tag: 200
        with self.assertRaises(SystemExit) as caught:
            gate.main()
        self.assertEqual(caught.exception.code, 2)

    def test_unexpected_release_status_is_unverifiable(self):
        self.fixtures(CURRENT, ZIP_SUM, CURRENT)
        gate.release_status = lambda tag: 503
        with self.assertRaises(SystemExit) as caught:
            gate.main()
        self.assertEqual(caught.exception.code, 2)

    def test_missing_skill_file_on_the_404_path_exits_3(self):
        gate.VERIFY_PAGE.write_text(
            VERIFY.format(version=AHEAD, checksum=OTHER_SUM), encoding="utf-8"
        )
        gate.release_status = lambda tag: 404
        with self.assertRaises(SystemExit) as caught:
            gate.main()
        self.assertEqual(caught.exception.code, 3)

    def test_unparseable_status_is_unverifiable_not_404(self):
        # api_status is the real status parser (release_status and tag_status
        # both delegate to it); setUp stubs those two, so exercise the parser
        # directly with a gh call that yields no HTTP status line.
        gate.gh = lambda *args, check=True: subprocess.CompletedProcess(
            args, 1, "", "network hiccup"
        )
        with self.assertRaises(SystemExit) as caught:
            gate.api_status(
                "repos/jposluns/cleanlanguage/releases/tags/v1.0.14",
                "the release status for v1.0.14",
            )
        self.assertEqual(caught.exception.code, 2)

    def test_malformed_version_line_on_404_path_exits_3(self):
        # A "Version:" label with the number on the next line must not be read
        # across the newline; the gate cannot confirm the current version and
        # exits 3 rather than treating the site as legitimately ahead.
        gate.VERIFY_PAGE.write_text(
            VERIFY.format(version=AHEAD, checksum=OTHER_SUM), encoding="utf-8"
        )
        gate.SKILL.write_text("Version:\n1.0.15\n", encoding="utf-8")
        gate.release_status = lambda tag: 404
        gate.tag_status = lambda tag: 404
        with self.assertRaises(SystemExit) as caught:
            gate.main()
        self.assertEqual(caught.exception.code, 3)

    def test_non_utf8_skill_on_404_path_exits_3(self):
        gate.VERIFY_PAGE.write_text(
            VERIFY.format(version=AHEAD, checksum=OTHER_SUM), encoding="utf-8"
        )
        gate.SKILL.write_bytes(b"Version: 1.0.15\xff\n")
        gate.release_status = lambda tag: 404
        with self.assertRaises(SystemExit) as caught:
            gate.main()
        self.assertEqual(caught.exception.code, 3)

    def test_malformed_dotted_version_is_rejected(self):
        # The version must be three numeric parts (the release tooling's
        # format); a trailing-dot or empty-segment version is rejected, not
        # read as legitimately ahead.
        self.fixtures(AHEAD, OTHER_SUM, "1.0.")
        gate.release_status = lambda tag: 404
        with self.assertRaises(SystemExit) as caught:
            gate.main()
        self.assertEqual(caught.exception.code, 3)

    def test_status_lines_split_across_streams_are_not_fused(self):
        # gh stdout may lack a trailing newline; the parser must not fuse the
        # last stdout line with the first stderr line and read the wrong status.
        gate.gh = lambda *args, check=True: subprocess.CompletedProcess(
            args, 0, "HTTP/2 200", "HTTP/2 404"
        )
        self.assertEqual(gate.api_status("repos/x/y", "the status"), 404)

    def test_malformed_first_version_line_is_not_bypassed(self):
        # The first Version line is authoritative (as in release-package.sh); a
        # malformed first line must fail even if a later line is well formed,
        # rather than silently falling through to it.
        gate.VERIFY_PAGE.write_text(
            VERIFY.format(version="1.2.3", checksum=OTHER_SUM), encoding="utf-8"
        )
        gate.SKILL.write_text(
            "Version: 9.9.9 trailing-text\nVersion: 1.2.3\n", encoding="utf-8"
        )
        gate.release_status = lambda tag: 404
        gate.tag_status = lambda tag: 404
        with self.assertRaises(SystemExit) as caught:
            gate.main()
        self.assertEqual(caught.exception.code, 3)


if __name__ == "__main__":
    unittest.main()
