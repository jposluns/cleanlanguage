#!/usr/bin/env python3
"""Tests for the live checksum gate's conditional 404 pass.

The gate must not pass unconditionally when the release the verify page names
is not published. It passes on a 404 only in the legitimate pre-tag window:
the site names the current skill version and the tag does not exist yet,
and even then the Released line is checked with no further network call, so
a malformed line exits 3 and a line missing above the baseline fails. A
mismatched unreleased version fails, a tag with no published release is
unverifiable, and the published-release comparison and the transient-error
handling are preserved. Once the release SKILL.md names is published, its
Released line (item 26) must name the UTC day of the release published_at
record (G4), checked for the release SKILL.md names whatever version the site
names, and that release must be immutable; an unpublished release SKILL.md
names counts as not yet published only when its tag is confirmed absent, and an
undated release at or below the baseline makes no network call for the date
check. A date failure never hides checksum drift: both are reported and the
more severe code wins. A release state that cannot be verified never hides the
Released line check, and an unreadable verify page or downloaded asset is
reported as such, never read as drift. The gate runs the extractor as a separate python3 -I
child for each call, reads only a bounded part of what the child prints, and
accepts only one JSON reply that matches the contract. The network reads of that record are replaced
by injected fixtures. These tests pin all of that offline: the
fixtures
patch the module's file paths and network readers, so no gh CLI and no
network access are needed. The CI workflow invokes this file before the gate
itself runs against the real pages, so the regression proof runs even when
the network gate cannot.
"""

from __future__ import annotations

import ast
import contextlib
import errno
import hashlib
import importlib.util
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import types
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


# Row 80: the gate runs the extractor as a separate python3 -I child, so a
# fake extractor is a source file the child runs. The real extractor is also
# imported here, only as the reference the child replies are compared with.
EXTRACTOR_PATH = MODULE_PATH.parent / "skill-release-date.py"
reference_spec = importlib.util.spec_from_file_location("skill_release_date_reference", EXTRACTOR_PATH)
REFERENCE = importlib.util.module_from_spec(reference_spec)
reference_spec.loader.exec_module(REFERENCE)

MAIN_GUARD = '\nif __name__ == "__main__":\n'

# The report of a probe that fails with exit 1 and prints nothing.
PROBE_FAILED = (
    "check-release-checksum-live: skill-release-date.py exited 1 in baseline, "
    "so the extractor is unavailable"
)

# Runs a copy of the gate (its path the first argument) with a 1 second child
# timeout, so a hung child is observed without a 20 second wait.
TIMEOUT_WRAPPER = (
    "import importlib.util, sys\n"
    "spec = importlib.util.spec_from_file_location(\"gate_copy\", sys.argv[1])\n"
    "gate = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(gate)\n"
    "gate.CHILD_TIMEOUT_SECONDS = 1\n"
    "sys.exit(gate.main())\n"
)


def extractor_with(extra: str) -> str:
    """Return the real extractor source with ``extra`` inserted just before
    its __main__ guard, so a definition in ``extra`` replaces the real one
    before main runs in the child."""
    source = EXTRACTOR_PATH.read_text(encoding="utf-8")
    if source.count(MAIN_GUARD) != 1:
        raise AssertionError("the extractor has no single __main__ guard")
    return source.replace(MAIN_GUARD, "\n" + extra + MAIN_GUARD, 1)


def forging(outputs: dict, code: int = 0) -> str:
    """Return extractor source whose --json mode, for each op named in
    ``outputs`` (or for every op, under the key "*"), prints those raw bytes
    and exits ``code``, and answers every other op as the real extractor
    does."""
    return extractor_with(
        "_real_json_main = json_main\n"
        f"_FORGED = {outputs!r}\n"
        "def json_main():\n"
        "    data = sys.stdin.buffer.read()\n"
        "    op = json.loads(data)[\"op\"]\n"
        "    forged = _FORGED.get(op, _FORGED.get(\"*\"))\n"
        "    if forged is not None:\n"
        "        sys.stdout.flush()\n"
        "        sys.stdout.buffer.write(forged)\n"
        "        sys.stdout.buffer.flush()\n"
        f"        return {code!r}\n"
        "    sys.stdin = io.TextIOWrapper(io.BytesIO(data))\n"
        "    return _real_json_main()\n"
    )


def logging_extractor(fail_first: bool) -> str:
    """Return extractor source that appends the op of each --json run to
    runs.log beside it and, when ``fail_first`` is true, exits 1 with nothing
    printed on its first run there, answering every other run as the real
    extractor does."""
    return extractor_with(
        "_real_json_main = json_main\n"
        "def json_main():\n"
        "    data = sys.stdin.buffer.read()\n"
        "    here = Path(__file__).resolve().parent\n"
        "    with open(here / \"runs.log\", \"a\", encoding=\"utf-8\") as log:\n"
        "        log.write(json.loads(data)[\"op\"] + \"\\n\")\n"
        f"    if {fail_first!r} and not (here / \"failed-once\").exists():\n"
        "        (here / \"failed-once\").write_text(\"x\", encoding=\"utf-8\")\n"
        "        raise SystemExit(1)\n"
        "    sys.stdin = io.TextIOWrapper(io.BytesIO(data))\n"
        "    return _real_json_main()\n"
    )


def logged_runs(tool: Path) -> list[str]:
    """The ops of the --json runs of the logging extractor ``tool``."""
    return (tool.parent / "runs.log").read_text(encoding="utf-8").splitlines()


def process_state(pid: int) -> str | None:
    """The State letter of process ``pid``, or None when it does not exist."""
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    for line in status.splitlines():
        if line.startswith("State:"):
            return line.split()[1]
    return None


def unexpected_call(*args, **kwargs):
    raise AssertionError(f"unexpected call: {args}")


class ConditionalPassTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = (
            gate.REPO_ROOT, gate.VERIFY_PAGE, gate.SKILL,
            gate.release_status, gate.tag_status, gate.gh,
            gate.release_published_at, gate.release_immutable,
        )
        # Row 80: a test may point the gate at a fake extractor or shorten
        # the child timeout; both are restored after it.
        self._saved_child = (gate.RELEASE_DATE_TOOL, gate.CHILD_TIMEOUT_SECONDS, gate.REAP_GRACE_SECONDS)
        root = Path(self._tmp.name)
        gate.REPO_ROOT = root
        gate.VERIFY_PAGE = root / "index.html"
        gate.SKILL = root / "SKILL.md"
        gate.release_status = unexpected_call
        gate.tag_status = unexpected_call
        gate.gh = unexpected_call
        gate.release_published_at = unexpected_call
        gate.release_immutable = unexpected_call

    def tearDown(self):
        (gate.REPO_ROOT, gate.VERIFY_PAGE, gate.SKILL, gate.release_status,
         gate.tag_status, gate.gh, gate.release_published_at,
         gate.release_immutable) = self._saved
        gate.RELEASE_DATE_TOOL, gate.CHILD_TIMEOUT_SECONDS, gate.REAP_GRACE_SECONDS = self._saved_child
        self._tmp.cleanup()

    def fake_extractor(self, body):
        """Write the extractor source ``body`` into a fresh directory and
        point the gate at it, returning its path."""
        folder = Path(tempfile.mkdtemp(dir=self._tmp.name))
        tool = folder / "skill-release-date.py"
        tool.write_text(body, encoding="utf-8")
        gate.RELEASE_DATE_TOOL = tool
        return tool

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

    def published(self, published_at, statuses=None, immutable="true", tags=None):
        """Stand in for the release record reads, recording each tag asked for.

        ``statuses`` maps a tag to its release status (default 200);
        ``immutable`` is the raw immutable field every release reports;
        ``tags`` maps a tag to its tag ref status (default 404)."""
        self.asked = []
        self.probed = []
        self.immutable_asked = []
        self.tag_probed = []
        statuses = statuses or {}
        tags = tags or {}

        def tag_reader(tag):
            self.tag_probed.append(tag)
            return tags.get(tag, 404)

        gate.tag_status = tag_reader

        def reader(tag):
            self.asked.append(tag)
            return published_at

        def status(tag):
            self.probed.append(tag)
            return statuses.get(tag, 200)

        def immutable_reader(tag):
            self.immutable_asked.append(tag)
            return immutable

        gate.release_published_at = reader
        gate.release_immutable = immutable_reader
        gate.release_status = status
        gate.gh = self.fake_download

    def main_output(self):
        """Run the gate, returning (exit code, stdout)."""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = gate.main()
        return code, buffer.getvalue()

    # --- G4 (item 26): the Released line against the release record ---------

    def test_released_date_matching_published_day_passes(self):
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-15T23:59:59Z")
        code, out = self.main_output()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.asked, [f"v{AHEAD}"])
        # VERIFY 5.1 (codex LOW 2): a correctly dated published release
        # prints no missing-line report and no inconsistency.
        self.assertIn(f"matches the publication day of release v{AHEAD}", out)
        self.assertNotIn("has no Released: line", out)
        self.assertNotIn("inconsistency", out)

    def test_released_date_differing_from_published_day_fails(self):
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-16T00:00:01Z")
        self.assertEqual(gate.main(), 1)

    def test_mismatch_message_states_both_values_and_defers_to_the_readback(self):
        # F3: never tell the maintainer to copy a record that may have moved.
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-16T00:00:01Z")
        code, out = self.main_output()
        self.assertEqual(code, 1)
        self.assertIn("says Released: 2026-11-15", out)
        self.assertIn("published_at reads 2026-11-16T00:00:01Z (UTC day 2026-11-16)", out)
        self.assertIn("first-publication readback", out)
        self.assertNotIn("Correct the line to match the release record", out)
        # R4: the release is immutable, so the remedy is a corrective new
        # version; no republish or asset replacement is offered. Row 74: the
        # wording matches the release workflow, which says corrective new
        # version.
        self.assertIn("the remedy is a corrective new version", out)
        self.assertNotIn("corrective version", out)
        self.assertNotIn("asset replacement", out)
        self.assertNotIn("force", out)
        self.assertNotIn("may have moved", out)

    def main_reports(self):
        """Run the gate, returning (exit code, stdout, stderr) whether it
        returns or stops with SystemExit."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = gate.main()
            except SystemExit as stop:
                code = stop.code
        return code, out.getvalue(), err.getvalue()

    # Exact report lines, for tests that assert the whole gate output (claim 6).
    CV = "check-release-checksum-live: could not verify: "
    SHOWN = "cleanlanguage/skills/cleanlanguage/SKILL.md"
    REMEDY = (
        "The Released line must name the UTC day the release was first published. The release is "
        "immutable, so neither its published zip nor its record can be replaced. If the line was "
        "edited after the release, restore the value the published zip carries; if the published "
        "zip itself names the wrong day, the remedy is a corrective new version whose Released line "
        "names its own publication day. The first-publication readback the release workflow printed "
        "when it created the release (its run log) records the day GitHub recorded."
    )

    def missing_line(self, situation):
        return [
            "Release date inconsistency found:",
            f"  - {situation}",
            f"  - {self.SHOWN} names {AHEAD}, above the undated baseline {CURRENT}, but has no Released: line",
        ]

    def malformed_line(self):
        soon = "Released: soon"
        return (
            f"check-release-checksum-live: the Released line in {self.SHOWN} is malformed: "
            f"the first Released line is not a bare YYYY-MM-DD date: {soon!r}"
        )

    def site_matches(self):
        return (
            f"The verify page checksum {ZIP_SUM} matches the published "
            f"cleanlanguage-{CURRENT}.zip for release v{CURRENT}."
        )

    def tag_exists(self, tag, names=""):
        return (
            f"tag {tag} exists but release {tag}{names} is not published; if a release run is "
            f"publishing {tag} right now, re-run this check once it completes, and otherwise the "
            f"release was deleted or its publish failed"
        )

    def date_mismatch(self, released, tag, published_at, day):
        return [
            "Release date inconsistency found:",
            f"  - {self.SHOWN} says Released: {released}",
            f"  - release {tag} published_at reads {published_at} (UTC day {day})",
            "",
            self.REMEDY,
        ]

    def test_date_failure_does_not_hide_checksum_drift(self):
        # T5: both checks run and both are reported, the more severe code wins.
        for label, released, published, immutable, expected, reason in (
            ("date mismatch", "Released: 2026-11-15  ", "2026-11-16T00:00:01Z", "true", 1,
             "Release date inconsistency found"),
            ("record not immutable", "Released: 2026-11-15  ", "2026-11-15T09:30:00Z", "false", 2,
             "could not verify: the immutable field of release"),
            ("malformed Released line", "Released: soon", "2026-11-15T09:30:00Z", "true", 3,
             "Released line in cleanlanguage/skills/cleanlanguage/SKILL.md is malformed"),
        ):
            with self.subTest(label):
                self.fixtures(AHEAD, OTHER_SUM, AHEAD, released)
                self.published(published, immutable=immutable)
                code, out, err = self.main_reports()
                self.assertEqual(code, expected, (out, err))
                self.assertIn(reason, out + err)
                self.assertIn("Release checksum drift found", out)

    def test_date_failure_beside_a_matching_checksum_still_fails(self):
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-16T00:00:01Z")
        code, out, err = self.main_reports()
        self.assertEqual(code, 1, (out, err))
        self.assertIn("Release date inconsistency found", out)
        self.assertIn("matches the published", out)

    def test_dated_baseline_matching_passes(self):
        # F13: a dated 1.0.14 is compared like any other dated release.
        self.fixtures(CURRENT, ZIP_SUM, CURRENT, "Released: 2026-11-15  ")
        self.published("2026-11-15T09:30:00Z")
        self.assertEqual(gate.main(), 0)
        self.assertEqual(self.asked, [f"v{CURRENT}"])

    def test_dated_baseline_mismatched_fails(self):
        self.fixtures(CURRENT, ZIP_SUM, CURRENT, "Released: 2026-11-15  ")
        self.published("2026-11-16T09:30:00Z")
        self.assertEqual(gate.main(), 1)

    def test_release_that_is_not_immutable_is_unverifiable(self):
        # F14: the date comparison relies on an immutable release record.
        for value in ("false", "null", "", "True", "true "):
            with self.subTest(value):
                self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
                self.published("2026-11-15T09:30:00Z", immutable=value)
                with self.assertRaises(SystemExit) as caught:
                    gate.main()
                self.assertEqual(caught.exception.code, 2)
                self.assertEqual(self.immutable_asked, [f"v{AHEAD}"])

    def test_immutable_reader_asks_for_the_immutable_field(self):
        gate.release_immutable = self._saved[7]
        seen = []

        def fake(*args, check=True):
            seen.append(args)
            return subprocess.CompletedProcess(args, 0, "true\n", "")

        gate.gh = fake
        self.assertEqual(gate.release_immutable("v1.0.15"), "true")
        self.assertEqual(
            seen, [("api", "repos/jposluns/cleanlanguage/releases/tags/v1.0.15", "--jq", ".immutable")]
        )

    def test_immutable_reader_fails_closed_on_gh_error(self):
        gate.release_immutable = self._saved[7]
        gate.gh = lambda *args, check=True: subprocess.CompletedProcess(args, 1, "", "HTTP 502")
        with self.assertRaises(SystemExit) as caught:
            gate.release_immutable("v1.0.15")
        self.assertEqual(caught.exception.code, 2)

    def test_undated_release_reads_no_record_field(self):
        # F9: an undated release at or below the baseline reads neither field.
        self.fixtures(CURRENT, ZIP_SUM, CURRENT)
        self.published("2026-11-15T09:30:00Z", immutable="false")
        self.assertEqual(gate.main(), 0)
        self.assertEqual((self.asked, self.immutable_asked), ([], []))

    def test_baseline_rule_is_numeric_for_an_undated_published_release(self):
        # F7: the same rule the extractor applies everywhere.
        for version, expected in (
            ("1.0.9", 0), ("1.0.14", 0), ("1.00.14", 0),
            ("1.0.15", 1), ("1.0.100", 1), ("1.1.0", 1),
        ):
            with self.subTest(version):
                self.fixtures(version, ZIP_SUM, version)
                self.published("2026-11-15T09:30:00Z")
                self.assertEqual(gate.main(), expected)

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

    # --- F2: the release SKILL.md names is checked on its own terms ---------

    def test_site_naming_an_older_release_still_checks_the_newer_date(self):
        # The site still names 1.0.14; v1.0.15 is published on another day.
        self.fixtures(CURRENT, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-16T00:00:05Z")
        self.assertEqual(gate.main(), 1)
        self.assertEqual(self.asked, [f"v{AHEAD}"])
        self.assertEqual(self.probed, [f"v{CURRENT}", f"v{AHEAD}"])

    def test_site_naming_an_older_release_with_a_matching_newer_date_passes(self):
        self.fixtures(CURRENT, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-15T09:30:00Z")
        self.assertEqual(gate.main(), 0)
        self.assertEqual(self.asked, [f"v{AHEAD}"])

    def test_unpublished_newer_release_skips_the_date_check(self):
        self.fixtures(CURRENT, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2020-01-01T00:00:00Z", statuses={f"v{AHEAD}": 404})
        self.assertEqual(gate.main(), 0)
        self.assertEqual(self.asked, [])
        self.assertEqual(self.probed, [f"v{CURRENT}", f"v{AHEAD}"])
        self.assertEqual(self.tag_probed, [f"v{AHEAD}"])

    def test_unpublished_newer_release_with_an_existing_tag_is_unverifiable(self):
        # R2: as on the same-version path, a tag with no release is a deleted
        # or failed release, never a release not yet published.
        self.fixtures(CURRENT, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-15T09:30:00Z", statuses={f"v{AHEAD}": 404}, tags={f"v{AHEAD}": 200})
        with self.assertRaises(SystemExit) as caught:
            gate.main()
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(self.tag_probed, [f"v{AHEAD}"])
        self.assertEqual(self.asked, [])

    def test_unpublished_newer_release_whose_tag_cannot_be_checked_is_unverifiable(self):
        # Claim 6: the gate output is fully determined, so the exact stdout and
        # stderr lines are asserted; each status is reported in exactly one
        # line, on stderr, and any further line on either stream, in any
        # wording, fails.
        self.fixtures(CURRENT, ZIP_SUM, AHEAD)
        self.published("2026-11-15T09:30:00Z", statuses={f"v{AHEAD}": 404}, tags={f"v{AHEAD}": 503})
        code, out, err = self.main_reports()
        self.assertEqual(code, 2, (out, err))
        self.assertEqual(err.splitlines(), [f"{self.CV}unexpected HTTP 503 reading tag v{AHEAD}"], err)
        self.assertEqual(out.splitlines(), self.missing_line(
            f"the release state of v{AHEAD}, the version SKILL.md names, could not be verified"
        ) + [self.site_matches()], out)

    def test_undated_baseline_beside_an_older_site_release_makes_no_probe(self):
        # R5: the line and the baseline rule are read first, so an undated
        # release at or below the baseline makes no network call for G4.
        self.fixtures("1.0.13", ZIP_SUM, CURRENT)
        self.published("2026-11-15T09:30:00Z")
        self.assertEqual(gate.main(), 0)
        self.assertEqual(self.probed, ["v1.0.13"])
        self.assertEqual((self.tag_probed, self.asked, self.immutable_asked), ([], [], []))

    def test_unexpected_status_of_the_newer_release_is_unverifiable(self):
        self.fixtures(CURRENT, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-15T09:30:00Z", statuses={f"v{AHEAD}": 503})
        code, out, err = self.main_reports()
        self.assertEqual(code, 2, (out, err))
        # Fix round 8 (operator sweep): a present Released line is never
        # reported as missing beside the unverifiable state.
        self.assertNotIn("has no Released: line", out)
        # Claim 6: the gate output is fully determined, so the exact stdout and
        # stderr lines are asserted; each status is reported in exactly one
        # line, on stderr, and any further line on either stream, in any
        # wording, fails.
        self.assertEqual(
            err.splitlines(),
            [f"{self.CV}unexpected HTTP 503 reading release v{AHEAD}, the version SKILL.md names"],
            err,
        )
        self.assertEqual(out.splitlines(), [self.site_matches()], out)

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

    def test_readers_fail_closed_on_an_os_or_decode_error(self):
        # U3: an OSError other than a missing gh, or gh output that does not
        # decode, is unverifiable (exit 2), never a traceback read as drift.
        # DISCOVERY 9 (LOW 1): the report is pinned exactly, including the
        # OSError or UnicodeError branch of api_status behind release_status
        # and tag_status.
        undecodable_error = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        denied_error = PermissionError(13, "Permission denied")

        def undecodable(*args, check=True):
            raise undecodable_error

        def denied(*args, check=True):
            raise denied_error

        readers = (
            ("release_immutable", self._saved[7], "the immutable field of release v1.0.15"),
            ("release_published_at", self._saved[6], "published_at for release v1.0.15"),
            ("release_status", self._saved[3], "the release status for v1.0.15"),
            ("tag_status", self._saved[4], "the tag status for v1.0.15"),
        )
        for name, reader, what in readers:
            for fake, error in ((undecodable, undecodable_error), (denied, denied_error)):
                with self.subTest(name, error=fake.__name__):
                    gate.gh = fake
                    out, err = io.StringIO(), io.StringIO()
                    with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(out), \
                            contextlib.redirect_stderr(err):
                        reader("v1.0.15")
                    self.assertEqual(caught.exception.code, 2)
                    # Claim 6: the gate output is fully determined, so the exact stdout and
                    # stderr lines are asserted; each status is reported in exactly one
                    # line, on stderr, and any further line on either stream, in any
                    # wording, fails.
                    self.assertEqual(
                        err.getvalue().splitlines(), [f"{self.CV}could not read {what}: {error!r}"],
                        err.getvalue(),
                    )
                    self.assertEqual(out.getvalue().splitlines(), [], out.getvalue())

    def test_readers_report_a_missing_gh_in_exactly_one_line(self):
        # DISCOVERY 9 (LOW 1): a gh that is absent is unverifiable (exit 2) in
        # every reader, including the FileNotFoundError branch of api_status
        # behind release_status and tag_status, both through a gh that raises
        # FileNotFoundError and through the real gh wrapper on an empty PATH.
        def absent(*args, check=True):
            raise FileNotFoundError(2, "No such file or directory", "gh")

        readers = (
            ("release_immutable", self._saved[7]), ("release_published_at", self._saved[6]),
            ("release_status", self._saved[3]), ("tag_status", self._saved[4]),
        )
        empty = Path(self._tmp.name) / "empty-path"
        empty.mkdir()
        for name, reader in readers:
            for label, fake in (
                ("a gh that raises FileNotFoundError", absent),
                ("the real gh wrapper on an empty PATH", self._saved[5]),
            ):
                with self.subTest(name, gh=label):
                    gate.gh = fake
                    saved_path = os.environ.get("PATH")
                    os.environ["PATH"] = str(empty)
                    out, err = io.StringIO(), io.StringIO()
                    try:
                        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(out), \
                                contextlib.redirect_stderr(err):
                            reader("v1.0.15")
                    finally:
                        if saved_path is None:
                            os.environ.pop("PATH", None)
                        else:
                            os.environ["PATH"] = saved_path
                    self.assertEqual(caught.exception.code, 2)
                    # Claim 6: the gate output is fully determined, so the exact stdout and
                    # stderr lines are asserted; each status is reported in exactly one
                    # line, on stderr, and any further line on either stream, in any
                    # wording, fails.
                    self.assertEqual(
                        err.getvalue().splitlines(), [f"{self.CV}the gh CLI is not available"],
                        err.getvalue(),
                    )
                    self.assertEqual(out.getvalue().splitlines(), [], out.getvalue())

    def test_undecodable_immutable_read_does_not_hide_checksum_drift(self):
        # U3: the date check stops with exit 2 and the checksum drift is
        # still reported.
        self.fixtures(AHEAD, OTHER_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-15T09:30:00Z")
        gate.release_immutable = self._saved[7]

        def fake(*args, check=True):
            if args[:1] == ("api",):
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
            return self.fake_download(*args, check=check)

        gate.gh = fake
        code, out, err = self.main_reports()
        self.assertEqual(code, 2, (out, err))
        self.assertIn("could not verify: could not read the immutable field of release", err)
        self.assertIn("Release checksum drift found", out)

    def gate_beside(self, tools, body):
        """Load a fresh copy of the gate from ``tools`` beside the extractor
        source ``body`` (None for no extractor), wired to the fixtures and
        readers of this test. A stop while loading fails the test, since the
        gate must load and reach main whatever the extractor holds."""
        shutil.copy2(MODULE_PATH, tools / MODULE_PATH.name)
        if body is not None:
            (tools / "skill-release-date.py").write_text(body, encoding="utf-8")
        fresh_spec = importlib.util.spec_from_file_location(
            "check_release_checksum_live_fresh", tools / MODULE_PATH.name
        )
        fresh = importlib.util.module_from_spec(fresh_spec)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                fresh_spec.loader.exec_module(fresh)
            except SystemExit as stop:
                self.fail(f"loading the gate stopped with exit {stop.code} before main ran: {err.getvalue()}")
        for name in (
            "REPO_ROOT", "VERIFY_PAGE", "SKILL", "release_status", "tag_status", "gh",
            "release_published_at", "release_immutable",
        ):
            setattr(fresh, name, getattr(gate, name))
        return fresh

    def test_extractor_load_failure_does_not_hide_checksum_drift(self):
        # Round 5: the extractor is probed inside main, so a failure to run
        # it contributes exit 3 while the checksum comparison still runs and
        # reports the drift. Row 80: each reason is the child outcome, with
        # the child stderr relayed.
        for label, body, reasons in (
            ("missing extractor", None, ("exited 2 in baseline", "can't open file")),
            ("syntax-broken extractor", "def broken(:\n", ("exited 1 in baseline", "SyntaxError")),
            ("API-invalid extractor", extractor_with("extract = 5\n"),
             ("failed unexpectedly (internal error) in extract", "TypeError")),
        ):
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                self.fixtures(AHEAD, OTHER_SUM, AHEAD, "Released: 2026-11-15  ")
                self.published("2026-11-15T09:30:00Z")
                fresh = self.gate_beside(Path(tmp), body)
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    try:
                        code = fresh.main()
                    except SystemExit as stop:
                        code = stop.code
                self.assertEqual(code, 3, (out.getvalue(), err.getvalue()))
                for reason in reasons:
                    self.assertIn(reason, err.getvalue())
                self.assertIn("the extractor is unavailable", err.getvalue())
                self.assertIn("Release checksum drift found", out.getvalue())

    def test_extractor_load_failure_still_exits_3_in_the_pre_tag_window(self):
        # The load failure contributes exit 3 on every path, as it did when
        # the load ran at import, including one that needs no date check.
        with tempfile.TemporaryDirectory() as tmp:
            self.fixtures(AHEAD, OTHER_SUM, AHEAD)
            gate.release_status = lambda tag: 404
            gate.tag_status = lambda tag: 404
            fresh = self.gate_beside(Path(tmp), None)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as caught:
                    fresh.main()
            self.assertEqual(caught.exception.code, 3, (out.getvalue(), err.getvalue()))
            self.assertIn("the extractor is unavailable", err.getvalue())
            self.assertIn("is not published yet", out.getvalue())
            self.assertNotIn("Nothing to reconcile", out.getvalue())

    def test_unreleased_other_version_does_not_hide_the_date_check(self):
        # Sibling (a): the site names an unreleased version that is not the
        # current one; the release SKILL.md names is still checked on its own
        # terms and the more severe code wins.
        for label, published, immutable, expected, reason in (
            ("date mismatch", "2026-11-16T00:00:01Z", "true", 1, "Release date inconsistency found"),
            ("record not immutable", "2026-11-15T09:30:00Z", "false", 2,
             "could not verify: the immutable field of release"),
        ):
            with self.subTest(label):
                self.fixtures(BOGUS, OTHER_SUM, AHEAD, "Released: 2026-11-15  ")
                self.published(published, statuses={f"v{BOGUS}": 404}, immutable=immutable)
                code, out, err = self.main_reports()
                self.assertEqual(code, expected, (out, err))
                self.assertIn("Release checksum inconsistency found", out)
                self.assertIn(reason, out + err)
                self.assertEqual(self.probed, [f"v{BOGUS}", f"v{AHEAD}"])

    def test_unusable_download_does_not_hide_the_date_check(self):
        # Sibling (b): a failed download or a malformed manifest stops only
        # the checksum comparison (exit 2); the date check still runs and
        # reports, and the more severe code wins.
        def failed(*args, check=True):
            raise subprocess.CalledProcessError(1, ["gh", *args], "", "HTTP 502")

        def two_line_manifest(*args, check=True):
            self.fake_download(*args, check=check)
            version = args[2].removeprefix("v")
            target = Path(args[args.index("--dir") + 1])
            (target / f"cleanlanguage-{version}.zip.sha256").write_text(
                f"{ZIP_SUM}  cleanlanguage-{version}.zip\nextra\n", encoding="utf-8"
            )
            return subprocess.CompletedProcess(args, 0, "", "")

        for label, download, released, expected, reason, stop in (
            ("failed download, date mismatch", failed, "Released: 2026-11-15  ", 2,
             "Release date inconsistency found", "could not download"),
            ("malformed manifest, malformed Released line", two_line_manifest, "Released: soon", 3,
             "Released line in cleanlanguage/skills/cleanlanguage/SKILL.md is malformed",
             "is not exactly one line"),
        ):
            with self.subTest(label):
                self.fixtures(AHEAD, OTHER_SUM, AHEAD, released)
                self.published("2026-11-16T00:00:01Z")
                gate.gh = download
                code, out, err = self.main_reports()
                self.assertEqual(code, expected, (out, err))
                self.assertIn(reason, out + err)
                self.assertIn("could not verify: ", err)
                self.assertIn(stop, err)
                self.assertNotIn("Release checksum drift found", out)

    def test_extractor_crash_inside_a_call_exits_3(self):
        # F5: an unexpected failure of the extractor is unavailable (exit 3),
        # never a drift verdict (exit 1). Row 80: the child exits 6 and its
        # stderr is relayed.
        self.fake_extractor(extractor_with(
            "def release_day_from_published_at(value):\n    raise RuntimeError(\"boom\")\n"
        ))
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-15T09:30:00Z")
        code, out, err = self.main_reports()
        self.assertEqual(code, 3, (out, err))
        self.assertIn(
            "check-release-checksum-live: skill-release-date.py failed unexpectedly (internal error) in "
            "release_day_from_published_at, so the extractor is unavailable; it printed: ",
            err,
        )
        self.assertIn("RuntimeError('boom')", err)
        self.assertIn("matches the published", out)

    def test_extractor_raising_system_exit_exits_3(self):
        # Row 58: an extractor that raises SystemExit, whatever its code, is
        # unavailable (exit 3), never a pass (0) or a drift (1). Fix round 4
        # (F2): 2 and 3 too, the codes release_date_code and main absorb as
        # could not verify. Row 80: the child ends with that code and an
        # empty stdout, so 0 and None print no result and the others exit
        # nonzero; no lookup on a module exists any more.
        for stop_code, reason in (
            (0, "did not print a JSON result"), (1, "exited 1"), (2, "exited 2"), (3, "exited 3"),
            (None, "did not print a JSON result"),
        ):
            with self.subTest(code=stop_code):
                self.fake_extractor(extractor_with(
                    f"def release_day_from_published_at(value):\n    raise SystemExit({stop_code!r})\n"
                ))
                self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
                self.published("2026-11-15T09:30:00Z")
                code, out, err = self.main_reports()
                self.assertEqual(code, 3, (out, err))
                self.assertEqual(err.splitlines(), [
                    f"check-release-checksum-live: skill-release-date.py {reason} in "
                    f"release_day_from_published_at, so the extractor is unavailable"
                ], err)
                self.assertIn("matches the published", out)

    def test_requires_release_date_is_not_called_when_the_line_is_present(self):
        # Fix round 8 (operator sweep): with a Released line present, the
        # baseline rule is not asked, so no extractor code runs for it. Row
        # 80: a call would run the failing function in a child and exit 3.
        self.fake_extractor(extractor_with(
            "def requires_release_date(version):\n"
            "    raise RuntimeError(\"requires_release_date was called\")\n"
        ))
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-15T09:30:00Z")
        code, out, err = self.main_reports()
        self.assertEqual(code, 0, (out, err))
        self.assertEqual(err, "")

    def test_unreadable_site_status_beside_a_skill_file_with_no_version_exits_3(self):
        # DISCOVERY 6 (claude LOW 1): a release status for the version the
        # verify page names that cannot be read (2), beside a SKILL.md with no
        # Version line (3), exits with the more severe 3 and its report.
        def unreadable(tag):
            gate.cannot_verify(f"could not read the release status for {tag} (gh exit 1)")

        self.fixtures(AHEAD, OTHER_SUM, AHEAD, "Released: 2026-11-15  ")
        gate.SKILL.write_text("Released: 2026-11-15\n", encoding="utf-8")
        gate.release_status = unreadable
        code, out, err = self.main_reports()
        self.assertEqual(code, 3, (out, err))
        # Claim 6: the gate output is fully determined, so the exact stdout and
        # stderr lines are asserted; each status is reported in exactly one
        # line, on stderr, and any further line on either stream, in any
        # wording, fails.
        self.assertEqual(err.splitlines(), [
            f"{self.CV}could not read the release status for v{AHEAD} (gh exit 1)",
            f"check-release-checksum-live: no 'Version:' line found in {self.SHOWN}",
        ], err)
        self.assertEqual(out.splitlines(), [], out)

    def test_undecodable_download_output_is_unverifiable(self):
        # DISCOVERY 6 (claude LOW 2): download output that does not decode
        # stops only the checksum comparison (exit 2) with its report, never
        # an uncaught UnicodeDecodeError read as drift; the date check still
        # runs and reports.
        def undecodable(*args, check=True):
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

        self.fixtures(AHEAD, OTHER_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-15T09:30:00Z")
        gate.gh = undecodable
        code, out, err = self.main_reports()
        self.assertEqual(code, 2, (out, err))
        self.assertIn(f"could not verify: could not download or read cleanlanguage-{AHEAD}.zip", err)
        self.assertIn("UnicodeDecodeError", err)
        self.assertIn("matches the publication day", out)
        self.assertNotIn("Release checksum drift found", out)

    def test_unexpected_status_of_the_site_release_does_not_hide_the_date_check(self):
        # Row 62: a status other than 200 or 404 for the release the site
        # names stops only the checksum comparison (exit 2); the release-date
        # check still runs and reports, and the more severe code wins. A
        # malformed line is read before any probe of the newer release.
        status = f"{self.CV}unexpected HTTP 503 reading release v{CURRENT}"
        for label, released, expected, out_lines, err_lines, probed in (
            ("date mismatch", "Released: 2026-11-15  ", 2,
             self.date_mismatch("2026-11-15", f"v{AHEAD}", "2026-11-16T00:00:01Z", "2026-11-16"),
             [status], [f"v{CURRENT}", f"v{AHEAD}"]),
            ("malformed Released line", "Released: soon", 3, [], [status, self.malformed_line()],
             [f"v{CURRENT}"]),
        ):
            with self.subTest(label):
                self.fixtures(CURRENT, ZIP_SUM, AHEAD, released)
                self.published("2026-11-16T00:00:01Z", statuses={f"v{CURRENT}": 503})
                code, out, err = self.main_reports()
                self.assertEqual(code, expected, (out, err))
                # Claim 6: the gate output is fully determined, so the exact stdout and
                # stderr lines are asserted; each status is reported in exactly one
                # line, on stderr, and any further line on either stream, in any
                # wording, fails.
                self.assertEqual(err.splitlines(), err_lines, err)
                self.assertEqual(out.splitlines(), out_lines, out)
                self.assertEqual(self.probed, probed)

    def test_undecodable_manifest_is_unverifiable(self):
        # Row 63: a published manifest that is not UTF-8 cannot be verified
        # (exit 2), never an uncaught UnicodeDecodeError read as drift; the
        # release-date check still runs and reports.
        def undecodable_manifest(*args, check=True):
            self.fake_download(*args, check=check)
            version = args[2].removeprefix("v")
            target = Path(args[args.index("--dir") + 1])
            (target / f"cleanlanguage-{version}.zip.sha256").write_bytes(
                ZIP_SUM.encode("ascii") + b"  cleanlanguage-\xff.zip"
            )
            return subprocess.CompletedProcess(args, 0, "", "")

        self.fixtures(AHEAD, OTHER_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-16T00:00:01Z")
        gate.gh = undecodable_manifest
        code, out, err = self.main_reports()
        self.assertEqual(code, 2, (out, err))
        self.assertIn(f"could not verify: could not read cleanlanguage-{AHEAD}.zip.sha256 from v{AHEAD}", err)
        self.assertIn("Release date inconsistency found", out)
        self.assertNotIn("Release checksum drift found", out)

    def test_extractor_attribute_gone_at_call_time_exits_3(self):
        # R3: a function missing at call time is unavailable (exit 3), never
        # an uncaught error (exit 1, drift). Row 80: the child fails with a
        # NameError (exit 6). A missing Malformed fails only where a verdict
        # is raised, so its row reads an unusable published_at.
        released = "Released: 2026-11-15  "
        for name, line, published_at, op in (
            ("extract", released, "2026-11-15T09:30:00Z", "extract"),
            ("release_day_from_published_at", released, "2026-11-15T09:30:00Z", "release_day_from_published_at"),
            ("requires_release_date", None, "2026-11-15T09:30:00Z", "requires_release_date"),
            ("Malformed", released, "null", "release_day_from_published_at"),
        ):
            with self.subTest(name):
                self.fake_extractor(extractor_with(f"del {name}\n"))
                self.fixtures(AHEAD, ZIP_SUM, AHEAD, line)
                self.published(published_at)
                code, out, err = self.main_reports()
                self.assertEqual(code, 3, (out, err))
                self.assertIn(
                    f"skill-release-date.py failed unexpectedly (internal error) in {op}, "
                    f"so the extractor is unavailable",
                    err,
                )
                self.assertIn(f"NameError(\"name '{name}' is not defined\")", err)

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
        self.fixtures(AHEAD, OTHER_SUM, AHEAD, "Released: 2026-11-15")
        gate.release_status = lambda tag: 404
        gate.tag_status = lambda tag: 404
        self.assertEqual(gate.main(), 0)

    def pre_tag_reports(self, version, released=None):
        """Run the gate in the pre-tag window for ``version``, asserting the
        release and the tag are each probed once and nothing else is read
        over the network; returns (exit code, stdout, stderr)."""
        self.fixtures(version, OTHER_SUM, version, released)
        self.published(None, statuses={f"v{version}": 404})
        gate.gh = unexpected_call
        gate.release_published_at = unexpected_call
        gate.release_immutable = unexpected_call
        code, out, err = self.main_reports()
        self.assertEqual(self.probed, [f"v{version}"])
        self.assertEqual(self.tag_probed, [f"v{version}"])
        self.assertIn("is not published yet", out)
        return code, out, err

    def test_pre_tag_window_with_a_valid_released_line_passes(self):
        code, out, err = self.pre_tag_reports(AHEAD, "Released: 2026-11-15  ")
        self.assertEqual(code, 0, (out, err))
        self.assertNotIn("inconsistency", out)

    def test_pre_tag_window_with_a_malformed_released_line_exits_3(self):
        for label, line in (
            ("impossible date", "Released: 2026-13-45"),
            ("wrong case", "released: 2026-11-15"),
        ):
            with self.subTest(label):
                code, out, err = self.pre_tag_reports(AHEAD, line)
                self.assertEqual(code, 3, (out, err))
                self.assertIn("the Released line in cleanlanguage/skills/cleanlanguage/SKILL.md is malformed", err)

    def test_pre_tag_window_missing_released_line_above_baseline_fails(self):
        code, out, err = self.pre_tag_reports(AHEAD)
        self.assertEqual(code, 1, (out, err))
        self.assertIn("Release date inconsistency found", out)
        self.assertIn(f"names {AHEAD}, above the undated baseline {CURRENT}, but has no Released: line", out)

    def test_pre_tag_window_undated_baseline_passes(self):
        code, out, err = self.pre_tag_reports(CURRENT)
        self.assertEqual(code, 0, (out, err))
        self.assertNotIn("inconsistency", out)

    def test_pre_tag_window_says_nothing_to_reconcile_only_when_clean(self):
        # Fix round 8 (claude, pre-existing): the pre-tag window says there is
        # nothing to reconcile only when the gate passes, never beside a
        # Released line missing above the baseline (exit 1) or a malformed
        # line (exit 3).
        for label, version, released, expected in (
            ("valid line", AHEAD, "Released: 2026-11-15  ", 0),
            ("undated baseline", CURRENT, None, 0),
            ("missing line above the baseline", AHEAD, None, 1),
            ("malformed line", AHEAD, "Released: soon", 3),
        ):
            with self.subTest(label):
                code, out, err = self.pre_tag_reports(version, released)
                self.assertEqual(code, expected, (out, err))
                if expected == 0:
                    self.assertIn("Nothing to reconcile.", out)
                else:
                    self.assertNotIn("Nothing to reconcile", out)

    def test_pre_tag_window_after_a_failed_first_load_never_says_nothing_to_reconcile(self):
        # Fix round 8: a probe that fails in main, beside later calls that
        # succeed, still ends the gate with 3, so the window does not say
        # there is nothing to reconcile. Row 80: the probe is the first
        # child, and its failure is reported once.
        self.fixtures(AHEAD, OTHER_SUM, AHEAD, "Released: 2026-11-15  ")
        gate.release_status = lambda tag: 404
        gate.tag_status = lambda tag: 404
        tool = self.fake_extractor(logging_extractor(fail_first=True))
        code, out, err = self.main_reports()
        self.assertEqual(code, 3, (out, err))
        self.assertTrue((tool.parent / "failed-once").exists())
        self.assertEqual(logged_runs(tool), ["baseline", "extract"])
        self.assertEqual(err.splitlines(), [PROBE_FAILED], err)
        self.assertIn("is not published yet", out)
        self.assertNotIn("Nothing to reconcile", out)

    def test_failed_first_load_combines_with_a_drift_or_mismatch_verdict(self):
        # DISCOVERY 9 (LOW 2): main combines the probe result with the check
        # result through max. The probe result is 0 or 3 and a drift or date
        # mismatch verdict is 1, so a failed probe (3) wins over the verdict,
        # and a clean probe (0) leaves the verdict (1). Each later call runs a
        # child of its own, so the verdict is still reached and reported.
        # This kills code = code, code = load_code and
        # code = min(load_code, code) at the combining line of main.
        drift = "Release checksum drift found:"
        mismatch = "Release date inconsistency found:"
        for label, site_sum, published_at, flaky_load, expected, reports in (
            ("failed load beside checksum drift", OTHER_SUM, "2026-11-15T09:30:00Z", True, 3, [drift]),
            ("failed load beside a date mismatch", ZIP_SUM, "2026-11-16T00:00:01Z", True, 3, [mismatch]),
            ("failed load beside drift and a date mismatch", OTHER_SUM, "2026-11-16T00:00:01Z", True, 3,
             [mismatch, drift]),
            ("clean load beside checksum drift", OTHER_SUM, "2026-11-15T09:30:00Z", False, 1, [drift]),
            ("clean load beside a date mismatch", ZIP_SUM, "2026-11-16T00:00:01Z", False, 1, [mismatch]),
        ):
            with self.subTest(label):
                self.fixtures(AHEAD, site_sum, AHEAD, "Released: 2026-11-15  ")
                self.published(published_at)
                tool = self.fake_extractor(logging_extractor(fail_first=flaky_load))
                code, out, err = self.main_reports()
                self.assertEqual(code, expected, (out, err))
                self.assertEqual(logged_runs(tool), ["baseline", "extract", "release_day_from_published_at"])
                self.assertEqual(err.splitlines(), [PROBE_FAILED] if flaky_load else [], err)
                lines = out.splitlines()
                self.assertEqual([line for line in lines if line in (drift, mismatch)], reports, out)
                if mismatch in reports:
                    start = lines.index(mismatch)
                    self.assertEqual(
                        lines[start:start + 5],
                        self.date_mismatch("2026-11-15", f"v{AHEAD}", "2026-11-16T00:00:01Z", "2026-11-16"),
                        out,
                    )
                if drift in reports:
                    start = lines.index(drift)
                    self.assertEqual(lines[start + 1:start + 3], [
                        f"  - the verify page shows {OTHER_SUM} for version {AHEAD}",
                        f"  - the published cleanlanguage-{AHEAD}.zip is {ZIP_SUM}",
                    ], out)

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
        code, out, err = self.main_reports()
        self.assertEqual(code, 2, (out, err))
        # Claim 6: the gate output is fully determined, so the exact stdout and
        # stderr lines are asserted; each status is reported in exactly one
        # line, on stderr, and any further line on either stream, in any
        # wording, fails.
        self.assertEqual(err.splitlines(), [f"{self.CV}unexpected HTTP 503 reading release v{CURRENT}"], err)
        self.assertEqual(out.splitlines(), [], out)

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
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as caught:
                gate.api_status(
                    "repos/jposluns/cleanlanguage/releases/tags/v1.0.14",
                    "the release status for v1.0.14",
                )
        self.assertEqual(caught.exception.code, 2)
        # Claim 6: the gate output is fully determined, so the exact stdout and
        # stderr lines are asserted; each status is reported in exactly one
        # line, on stderr, and any further line on either stream, in any
        # wording, fails.
        self.assertEqual(
            err.getvalue().splitlines(), [f"{self.CV}could not read the release status for v1.0.14 (gh exit 1)"],
            err.getvalue(),
        )
        self.assertEqual(out.getvalue().splitlines(), [], out.getvalue())

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

    # --- Fix round 1: no early exit hides the Released line, and every
    # required read fails closed ---------------------------------------------

    def offline_reports(self, version, released, tag_state):
        """Run the gate with the site and SKILL.md naming ``version``, its
        release returning 404 and its tag ``tag_state`` (an HTTP status, or
        "unreadable" for a tag status that cannot be read), asserting nothing
        but the two probes is read over the network; returns (exit code,
        stdout, stderr)."""
        self.fixtures(version, OTHER_SUM, version, released)
        self.published(None, statuses={f"v{version}": 404}, tags={f"v{version}": tag_state})
        if tag_state == "unreadable":
            def unreadable(tag):
                self.tag_probed.append(tag)
                gate.cannot_verify(f"could not read the tag status for {tag} (gh exit 1)")
            gate.tag_status = unreadable
        gate.gh = unexpected_call
        gate.release_published_at = unexpected_call
        gate.release_immutable = unexpected_call
        code, out, err = self.main_reports()
        self.assertEqual(self.probed, [f"v{version}"])
        self.assertEqual(self.tag_probed, [f"v{version}"])
        return code, out, err

    def test_same_version_tag_without_release_still_checks_the_released_line(self):
        # Codex MEDIUM 2: an existing tag, an unexpected tag status, or one
        # that cannot be read stops only the release verification (exit 2);
        # the Released line is still checked offline and the more severe code
        # wins, so a malformed line (exit 3) is not hidden.
        for tag_state in (200, 503, "unreadable"):
            for label, version, released, expected in (
                ("malformed line", AHEAD, "Released: soon", 3),
                ("line missing above the baseline", AHEAD, None, 2),
                ("valid line", AHEAD, "Released: 2026-11-15  ", 2),
                ("undated baseline", CURRENT, None, 2),
            ):
                with self.subTest(tag=tag_state, case=label):
                    tag = f"v{version}"
                    if tag_state == 200:
                        status = self.CV + self.tag_exists(tag)
                        situation = f"release {tag} is not published but its tag exists"
                    else:
                        if tag_state == 503:
                            status = f"{self.CV}unexpected HTTP 503 reading tag {tag}"
                        else:
                            status = f"{self.CV}could not read the tag status for {tag} (gh exit 1)"
                        situation = f"release {tag} is not published and the state of its tag could not be verified"
                    out_lines, err_lines = [], [status]
                    if label == "malformed line":
                        err_lines.append(self.malformed_line())
                    if label == "line missing above the baseline":
                        out_lines = self.missing_line(situation)
                    code, out, err = self.offline_reports(version, released, tag_state)
                    self.assertEqual(code, expected, (out, err))
                    # Claim 6: the gate output is fully determined, so the exact stdout and
                    # stderr lines are asserted; each status is reported in exactly one
                    # line, on stderr, and any further line on either stream, in any
                    # wording, fails.
                    self.assertEqual(err.splitlines(), err_lines, err)
                    self.assertEqual(out.splitlines(), out_lines, out)

    def test_unreadable_site_release_status_still_checks_the_released_line(self):
        # Sibling of MEDIUM 2: a release status for the version the site names
        # that cannot be read stops only the checksum comparison (exit 2); for
        # the same version the Released line is still checked offline, with no
        # further probe. A malformed line is read before any probe of a newer
        # release SKILL.md names, so it exits 3 with no further probe either;
        # the probe of a newer release is pinned in the next test (row 62).
        def unreadable(tag):
            self.probed.append(tag)
            gate.cannot_verify(f"could not read the release status for {tag} (gh exit 1)")

        for label, site, skill, released, expected, out_lines, extra_err in (
            ("malformed line, same version", AHEAD, AHEAD, "Released: soon", 3, [], [self.malformed_line()]),
            ("malformed line, newer SKILL.md, read before any probe", CURRENT, AHEAD,
             "Released: soon", 3, [], [self.malformed_line()]),
            ("line missing above the baseline", AHEAD, AHEAD, None, 2, self.missing_line(
                f"the release state of v{AHEAD}, the version the verify page names, could not be verified"
            ), []),
            ("valid line", AHEAD, AHEAD, "Released: 2026-11-15  ", 2, [], []),
        ):
            with self.subTest(label):
                self.fixtures(site, OTHER_SUM, skill, released)
                self.published(None)
                gate.release_status = unreadable
                gate.tag_status = unexpected_call
                gate.gh = unexpected_call
                gate.release_published_at = unexpected_call
                gate.release_immutable = unexpected_call
                code, out, err = self.main_reports()
                self.assertEqual(code, expected, (out, err))
                # Claim 6: the gate output is fully determined, so the exact stdout and
                # stderr lines are asserted; each status is reported in exactly one
                # line, on stderr, and any further line on either stream, in any
                # wording, fails.
                self.assertEqual(
                    err.splitlines(),
                    [f"{self.CV}could not read the release status for v{site} (gh exit 1)"] + extra_err,
                    err,
                )
                self.assertEqual(out.splitlines(), out_lines, out)
                self.assertEqual(self.probed, [f"v{site}"])

    def test_unreadable_site_release_status_probes_a_newer_skill_release(self):
        # Row 62, LOW 1 of DISCOVERY round 2: when the release status of the
        # version the site names cannot be read and SKILL.md names a newer
        # version, that newer release was never probed, so its state is not
        # unknown: the release-date check probes it on its own terms, as the
        # unexpected-status path does, and a wrong date on it is reported. The
        # checksum comparison still cannot run, so the exit stays at least 2.
        def statuses(newer):
            def status(tag):
                self.probed.append(tag)
                if tag == f"v{CURRENT}":
                    gate.cannot_verify(f"could not read the release status for {tag} (gh exit 1)")
                return newer
            return status

        for label, released, newer, immutable, expected, out_lines, extra_err, asked in (
            ("date mismatch", "Released: 2026-11-01  ", 200, "true", 2,
             self.date_mismatch("2026-11-01", f"v{AHEAD}", "2026-11-15T09:30:00Z", "2026-11-15"), [],
             [f"v{AHEAD}"]),
            ("matching date", "Released: 2026-11-15  ", 200, "true", 2,
             [f"The SKILL.md Released date 2026-11-15 matches the publication day of release v{AHEAD}."], [],
             [f"v{AHEAD}"]),
            ("line missing above the baseline", None, 200, "true", 2,
             self.missing_line(f"release v{AHEAD} is published"), [], []),
            ("record not immutable", "Released: 2026-11-15  ", 200, "false", 2, [],
             [f"{self.CV}the immutable field of release v{AHEAD} is 'false', not true, so its published_at "
              "cannot be relied on as the first publication instant"], []),
            ("newer release not published", "Released: 2026-11-15  ", 404, "true", 2,
             [f"Release v{AHEAD}, the version SKILL.md names, is not published yet and its tag does not exist; "
              "its Released date is checked once it is published."], [], []),
            ("newer release unexpected status", "Released: 2026-11-15  ", 503, "true", 2, [],
             [f"{self.CV}unexpected HTTP 503 reading release v{AHEAD}, the version SKILL.md names"], []),
        ):
            with self.subTest(label):
                self.fixtures(CURRENT, OTHER_SUM, AHEAD, released)
                self.published("2026-11-15T09:30:00Z", immutable=immutable)
                gate.release_status = statuses(newer)
                gate.gh = unexpected_call
                code, out, err = self.main_reports()
                self.assertEqual(code, expected, (out, err))
                # Claim 6: the gate output is fully determined, so the exact stdout and
                # stderr lines are asserted; each status is reported in exactly one
                # line, on stderr, and any further line on either stream, in any
                # wording, fails.
                self.assertEqual(
                    err.splitlines(),
                    [f"{self.CV}could not read the release status for v{CURRENT} (gh exit 1)"] + extra_err,
                    err,
                )
                self.assertEqual(out.splitlines(), out_lines, out)
                self.assertEqual(self.probed, [f"v{CURRENT}", f"v{AHEAD}"])
                self.assertEqual(self.asked, asked)
                self.assertNotIn(f"v{CURRENT}", self.tag_probed + self.immutable_asked)

    def test_unverifiable_newer_release_still_reports_a_missing_released_line(self):
        # Sibling of MEDIUM 2 inside the date check: an unverifiable state of
        # the release SKILL.md names keeps exit 2 but still reports a Released
        # line missing above the baseline.
        for label, statuses, tags, report in (
            ("tag without release", {f"v{AHEAD}": 404}, {f"v{AHEAD}": 200},
             self.tag_exists(f"v{AHEAD}", ", the version SKILL.md names,")),
            ("unexpected tag status", {f"v{AHEAD}": 404}, {f"v{AHEAD}": 503},
             f"unexpected HTTP 503 reading tag v{AHEAD}"),
            ("unexpected release status", {f"v{AHEAD}": 503}, {},
             f"unexpected HTTP 503 reading release v{AHEAD}, the version SKILL.md names"),
        ):
            with self.subTest(label):
                self.fixtures(CURRENT, ZIP_SUM, AHEAD)
                self.published("2026-11-15T09:30:00Z", statuses=statuses, tags=tags)
                code, out, err = self.main_reports()
                self.assertEqual(code, 2, (out, err))
                # Claim 6: the gate output is fully determined, so the exact stdout and
                # stderr lines are asserted; each status is reported in exactly one
                # line, on stderr, and any further line on either stream, in any
                # wording, fails.
                self.assertEqual(err.splitlines(), [self.CV + report], err)
                self.assertEqual(out.splitlines(), self.missing_line(
                    f"the release state of v{AHEAD}, the version SKILL.md names, could not be verified"
                ) + [self.site_matches()], out)

    def test_unexpected_status_of_the_same_release_reports_once_and_keeps_the_date_check(self):
        # Row 62, same-version case: the site and SKILL.md name the same
        # release and it returns 503. A malformed Released line still exits 3,
        # and the status is reported in one could-not-verify line, not two.
        status = f"check-release-checksum-live: could not verify: unexpected HTTP 503 reading release v{AHEAD}"
        skill = "cleanlanguage/skills/cleanlanguage/SKILL.md"
        soon = "Released: soon"
        for label, released, expected, out_lines, err_lines in (
            ("malformed Released line", soon, 3, [], [
                status,
                f"check-release-checksum-live: the Released line in {skill} is malformed: "
                f"the first Released line is not a bare YYYY-MM-DD date: {soon!r}",
            ]),
            ("line missing above the baseline", None, 2, [
                "Release date inconsistency found:",
                f"  - the release state of v{AHEAD}, the version SKILL.md names, could not be verified",
                f"  - {skill} names {AHEAD}, above the undated baseline {CURRENT}, but has no Released: line",
            ], [status]),
            ("valid line", "Released: 2026-11-15  ", 2, [], [status]),
        ):
            with self.subTest(label):
                self.fixtures(AHEAD, ZIP_SUM, AHEAD, released)
                self.published("2026-11-15T09:30:00Z", statuses={f"v{AHEAD}": 503})
                code, out, err = self.main_reports()
                self.assertEqual(code, expected, (out, err))
                # The gate output is fully determined here, so the exact stdout
                # and stderr lines are asserted: the status is reported in exactly
                # one line, on stderr, and any further line on either stream, in
                # any wording, fails.
                self.assertEqual(err.splitlines(), err_lines, err)
                self.assertEqual(out.splitlines(), out_lines, out)
                self.assertEqual(self.probed, [f"v{AHEAD}"])
                self.assertEqual((self.tag_probed, self.asked, self.immutable_asked), ([], [], []))

    def test_unreadable_verify_page_exits_3(self):
        # Codex MEDIUM 1: a verify page that cannot be read or decoded is a
        # required file that cannot be read (exit 3), never an uncaught
        # traceback (exit 1, drift), and nothing is read over the network.
        def undecodable():
            gate.VERIFY_PAGE.write_bytes(b"<p>\xff</p>")

        def denied():
            gate.VERIFY_PAGE.write_text(VERIFY.format(version=AHEAD, checksum=OTHER_SUM), encoding="utf-8")
            gate.VERIFY_PAGE.chmod(0)

        cases = [("undecodable", undecodable, "UnicodeDecodeError")]
        if os.geteuid() != 0:
            cases.append(("permission denied", denied, "PermissionError"))
        for label, make, reason in cases:
            with self.subTest(label):
                gate.SKILL.write_text(f"Version: {AHEAD}\nReleased: 2026-11-15\n", encoding="utf-8")
                make()
                try:
                    code, out, err = self.main_reports()
                finally:
                    gate.VERIFY_PAGE.chmod(0o600)
                self.assertEqual(code, 3, (out, err))
                self.assertIn("index.html could not be read", err)
                self.assertIn(reason, err)

    def test_unreadable_verify_page_beside_an_extractor_load_failure_exits_3(self):
        # MEDIUM 1: the read failure and the extractor load failure are both
        # reported, and the most severe code (3) is kept.
        with tempfile.TemporaryDirectory() as tmp:
            gate.VERIFY_PAGE.write_bytes(b"<p>\xff</p>")
            gate.SKILL.write_text(f"Version: {AHEAD}\n", encoding="utf-8")
            fresh = self.gate_beside(Path(tmp), None)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as caught:
                    fresh.main()
            self.assertEqual(caught.exception.code, 3, (out.getvalue(), err.getvalue()))
            self.assertIn("the extractor is unavailable", err.getvalue())
            self.assertIn("index.html could not be read", err.getvalue())

    def test_unpublished_newer_release_without_a_tag_still_checks_the_released_line(self):
        # The site names an older published release and SKILL.md names a
        # newer version whose release and tag are both absent: as in the
        # same-version pre-tag window, a line missing above the baseline
        # fails (exit 1) and a malformed line exits 3, never a pass.
        for label, released, expected, reason in (
            ("line missing above the baseline", None, 1,
             f"names {AHEAD}, above the undated baseline {CURRENT}, but has no Released: line"),
            ("malformed line", "Released: soon", 3,
             "the Released line in cleanlanguage/skills/cleanlanguage/SKILL.md is malformed"),
            ("valid line", "Released: 2026-11-15  ", 0, None),
        ):
            with self.subTest(label):
                self.fixtures(CURRENT, ZIP_SUM, AHEAD, released)
                self.published("2026-11-15T09:30:00Z", statuses={f"v{AHEAD}": 404})
                code, out, err = self.main_reports()
                self.assertEqual(code, expected, (out, err))
                if reason is None:
                    self.assertNotIn("inconsistency", out)
                else:
                    self.assertIn(reason, out + err)
                self.assertEqual((self.asked, self.immutable_asked), ([], []))

    @unittest.skipIf(os.geteuid() == 0, "root reads a file whatever its mode")
    def test_unreadable_downloaded_zip_does_not_hide_the_date_check(self):
        # Sibling of MEDIUM 1: a downloaded zip that cannot be read stops only
        # the checksum comparison (exit 2), never an uncaught traceback read
        # as drift; the release-date check still runs and reports.
        def unreadable_zip(*args, check=True):
            self.fake_download(*args, check=check)
            version = args[2].removeprefix("v")
            target = Path(args[args.index("--dir") + 1])
            (target / f"cleanlanguage-{version}.zip").chmod(0)
            return subprocess.CompletedProcess(args, 0, "", "")

        self.fixtures(AHEAD, OTHER_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-16T00:00:01Z")
        gate.gh = unreadable_zip
        code, out, err = self.main_reports()
        self.assertEqual(code, 2, (out, err))
        self.assertIn(f"could not verify: could not download or read cleanlanguage-{AHEAD}.zip", err)
        self.assertIn("PermissionError", err)
        self.assertIn("Release date inconsistency found", out)
        self.assertNotIn("Release checksum drift found", out)


    # --- Fix round 2: no early return hides a more severe result, and a
    # required file is reported by its real stat error ------------------------

    def test_missing_released_line_does_not_hide_an_immutable_failure(self):
        # F1 (codex MEDIUM): on the published path a Released line missing
        # above the baseline (exit 1) does not hide an immutable field that
        # is not exactly true, or cannot be read (exit 2): both are reported,
        # the more severe 2 wins, and published_at is not read, since there is
        # no line to compare it with.
        def unreadable(tag):
            self.immutable_asked.append(tag)
            gate.cannot_verify(f"could not read the immutable field of release {tag} (gh exit 1)")

        for label, immutable, reason in (
            ("not immutable", "false", "the immutable field of release v1.0.15 is"),
            ("immutable field unreadable", None, "could not read the immutable field of release v1.0.15"),
        ):
            with self.subTest(label):
                self.fixtures(AHEAD, ZIP_SUM, AHEAD)
                self.published("2026-11-15T09:30:00Z", immutable=immutable)
                if immutable is None:
                    gate.release_immutable = unreadable
                code, out, err = self.main_reports()
                self.assertEqual(code, 2, (out, err))
                self.assertIn(f"names {AHEAD}, above the undated baseline {CURRENT}, but has no Released: line", out)
                self.assertIn(reason, err)
                self.assertIn("matches the published", out)
                self.assertEqual(self.immutable_asked, [f"v{AHEAD}"])
                self.assertEqual(self.asked, [])

    def test_missing_released_line_beside_an_immutable_release_still_fails(self):
        # F1: with an immutable release the missing line still exits 1.
        self.fixtures(AHEAD, ZIP_SUM, AHEAD)
        self.published("2026-11-15T09:30:00Z")
        code, out, err = self.main_reports()
        self.assertEqual(code, 1, (out, err))
        self.assertIn("but has no Released: line", out)
        self.assertEqual(self.immutable_asked, [f"v{AHEAD}"])
        self.assertEqual(self.asked, [])

    @unittest.skipIf(os.geteuid() == 0, "root searches a directory whatever its mode")
    def test_required_file_behind_an_unsearchable_directory_is_unreadable_not_missing(self):
        # F4 (claude LOW): a verify page or SKILL.md that cannot be reached
        # because its directory cannot be searched is reported by its real
        # stat error (exit 3), never as a file that does not exist.
        root = Path(self._tmp.name)
        for label, target in (("verify page", "verify"), ("SKILL.md", "skill")):
            with self.subTest(label):
                folder = root / f"locked-{target}"
                folder.mkdir()
                gate.VERIFY_PAGE = root / "index.html"
                gate.SKILL = root / "SKILL.md"
                if target == "verify":
                    gate.VERIFY_PAGE = folder / "index.html"
                else:
                    gate.SKILL = folder / "SKILL.md"
                self.fixtures(AHEAD, OTHER_SUM, AHEAD, "Released: 2026-11-15  ")
                self.published(None, statuses={f"v{AHEAD}": 404})
                folder.chmod(0)
                try:
                    code, out, err = self.main_reports()
                finally:
                    folder.chmod(0o700)
                shown = (gate.VERIFY_PAGE if target == "verify" else gate.SKILL).relative_to(root)
                self.assertEqual(code, 3, (out, err))
                self.assertIn(f"{shown} could not be read: PermissionError", err)
                self.assertNotIn("does not exist", err)

    @unittest.skipIf(os.geteuid() == 0, "root searches a directory whatever its mode")
    def test_both_skill_readers_report_an_unsearchable_directory(self):
        # F4 sweep: skill_released and skill_version each check SKILL.md.
        folder = Path(self._tmp.name) / "locked"
        folder.mkdir()
        gate.SKILL = folder / "SKILL.md"
        gate.SKILL.write_text(f"Version: {AHEAD}\nReleased: 2026-11-15\n", encoding="utf-8")
        for reader in (gate.skill_released, gate.skill_version):
            with self.subTest(reader.__name__):
                folder.chmod(0)
                err = io.StringIO()
                try:
                    with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(err):
                        reader()
                finally:
                    folder.chmod(0o700)
                self.assertEqual(caught.exception.code, 3)
                self.assertIn("locked/SKILL.md could not be read: PermissionError", err.getvalue())
                self.assertNotIn("does not exist", err.getvalue())

    def test_required_file_that_is_absent_or_not_a_file_is_named_as_such(self):
        # F4: an absent required file still reads as missing; a directory in
        # its place is not a regular file.
        for label, make, reason in (
            ("absent", lambda: None, "index.html does not exist"),
            ("a directory", lambda: gate.VERIFY_PAGE.mkdir(), "index.html is not a regular file"),
        ):
            with self.subTest(label):
                gate.VERIFY_PAGE = Path(self._tmp.name) / label.replace(" ", "-") / "index.html"
                gate.VERIFY_PAGE.parent.mkdir()
                make()
                code, out, err = self.main_reports()
                self.assertEqual(code, 3, (out, err))
                self.assertIn(reason, err)

    @unittest.skipIf(os.geteuid() == 0, "root searches a directory whatever its mode")
    def test_downloaded_asset_behind_an_unsearchable_directory_is_unreadable_not_missing(self):
        # F4 sweep: the downloaded assets are reported by their real stat
        # error (exit 2), never as missing from the release.
        def locked_download(*args, check=True):
            self.fake_download(*args, check=check)
            Path(args[args.index("--dir") + 1]).chmod(0o600)
            return subprocess.CompletedProcess(args, 0, "", "")

        self.fixtures(AHEAD, OTHER_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-15T09:30:00Z")
        gate.gh = locked_download
        code, out, err = self.main_reports()
        self.assertEqual(code, 2, (out, err))
        self.assertIn(f"could not verify: could not read cleanlanguage-{AHEAD}.zip from v{AHEAD}: PermissionError", err)
        self.assertNotIn("is missing", err)
        self.assertIn("matches the publication day", out)

    # --- Row 80: the child contract, run in-process ---------------------------

    def call_reports(self, op, arg=None):
        """Run release_date_call for ``op`` (with ``arg``) and return its
        result, ("value", value), ("malformed", message), or ("exit", code),
        with the stderr it printed."""
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                args = () if arg is None else (arg,)
                result = ("value", gate.release_date_call(op, *args))
            except gate.ReleaseDateMalformed as error:
                result = ("malformed", str(error))
            except SystemExit as stop:
                result = ("exit", stop.code)
        return result, err.getvalue()

    def unavailable(self, reason, op):
        return f"check-release-checksum-live: skill-release-date.py {reason} in {op}, so the extractor is unavailable"

    # An argument for each op that takes one, answered with a value.
    ARGS = {
        "extract": f"Version: {AHEAD}\nReleased: 2026-11-15\n",
        "requires_release_date": AHEAD,
        "release_day_from_published_at": "2026-11-15T09:30:00Z",
        "baseline": None,
    }

    def test_the_real_extractor_meets_the_contract_for_every_op(self):
        for op, arg, expected in (
            ("extract", self.ARGS["extract"], ("value", "2026-11-15")),
            ("extract", f"Version: {AHEAD}\n", ("value", None)),
            ("extract", "Released: soon\n", ("malformed", "the first Released line is not a bare YYYY-MM-DD date: "
                                                          "'Released: soon'")),
            ("requires_release_date", AHEAD, ("value", True)),
            ("requires_release_date", CURRENT, ("value", False)),
            ("release_day_from_published_at", "2026-11-15T23:59:59Z", ("value", "2026-11-15")),
            ("baseline", None, ("value", CURRENT)),
        ):
            with self.subTest(op=op, arg=arg):
                self.assertEqual(self.call_reports(op, arg), (expected, ""))

    def test_a_reply_that_breaks_the_contract_exits_3(self):
        # Row 80 (2.4): each rule of the contract is checked, by exact type
        # and exact key set, and a breach exits 3 naming the rule.
        day = "2026-11-15"
        value_keys = "a result with outcome value has exactly the keys op, outcome, value"
        day_form = "the value is not a YYYY-MM-DD string"
        flag = "the value is not a JSON true or false"
        version = "the value is not a bare X.Y.Z version string"
        cases = (
            ("an extra key", "extract", {"op": "extract", "outcome": "value", "value": day, "extra": 1}, value_keys),
            ("a missing key", "extract", {"op": "extract", "outcome": "value"}, value_keys),
            ("an absent result with a value", "extract", {"op": "extract", "outcome": "absent", "value": day},
             "a result with outcome absent has exactly the keys op, outcome"),
            ("a malformed result with no message", "extract", {"op": "extract", "outcome": "malformed"},
             "a result with outcome malformed has exactly the keys message, op, outcome"),
            ("no outcome", "extract", {"op": "extract", "value": day}, "its outcome is not value, absent, or malformed"),
            ("an unknown outcome", "extract", {"op": "extract", "outcome": "maybe"},
             "its outcome is not value, absent, or malformed"),
            ("an outcome that is not a string", "extract", {"op": "extract", "outcome": 1},
             "its outcome is not value, absent, or malformed"),
            ("the wrong op echoed", "extract", {"op": "baseline", "outcome": "value", "value": day},
             "it answers an op other than extract"),
            ("an op that is not a string", "extract", {"op": 1, "outcome": "value", "value": day},
             "it answers an op other than extract"),
            ("absent for release_day_from_published_at", "release_day_from_published_at",
             {"op": "release_day_from_published_at", "outcome": "absent"},
             "absent is not a result of release_day_from_published_at"),
            ("absent for requires_release_date", "requires_release_date",
             {"op": "requires_release_date", "outcome": "absent"}, "absent is not a result of requires_release_date"),
            ("malformed for baseline", "baseline", {"op": "baseline", "outcome": "malformed", "message": "x"},
             "malformed is not a result of baseline"),
            ("a day that is a number", "extract", {"op": "extract", "outcome": "value", "value": 20261115}, day_form),
            ("a day not in the day form", "extract", {"op": "extract", "outcome": "value", "value": "2026-11-1x"},
             day_form),
            ("a day with trailing text", "extract", {"op": "extract", "outcome": "value", "value": day + "\n"},
             day_form),
            ("a null day", "extract", {"op": "extract", "outcome": "value", "value": None}, day_form),
            ("a published day not in the day form", "release_day_from_published_at",
             {"op": "release_day_from_published_at", "outcome": "value", "value": "2026-11-1x"}, day_form),
            ("requires_release_date 1", "requires_release_date",
             {"op": "requires_release_date", "outcome": "value", "value": 1}, flag),
            ("requires_release_date 0", "requires_release_date",
             {"op": "requires_release_date", "outcome": "value", "value": 0}, flag),
            ("requires_release_date \"true\"", "requires_release_date",
             {"op": "requires_release_date", "outcome": "value", "value": "true"}, flag),
            ("a message that is not a string", "extract", {"op": "extract", "outcome": "malformed", "message": 5},
             "the message is not a string"),
            ("baseline 1.0", "baseline", {"op": "baseline", "outcome": "value", "value": "1.0"}, version),
            ("baseline a number", "baseline", {"op": "baseline", "outcome": "value", "value": 14}, version),
        )
        for label, op, reply, rule in cases:
            with self.subTest(label):
                self.fake_extractor(forging({op: json.dumps(reply).encode("ascii") + b"\n"}))
                result, err = self.call_reports(op, self.ARGS[op])
                self.assertEqual(result, ("exit", 3), err)
                self.assertEqual(err.splitlines(), [self.unavailable(
                    f"printed a result that does not match the contract ({rule})", op
                )], err)

    def test_a_reply_larger_than_the_limit_exits_3(self):
        # Row 80: for a call with no argument, at most RESULT_LIMIT bytes of
        # stdout are accepted (one byte more is read, to detect it); a reply
        # of exactly that size is accepted and one byte more is refused.
        valid = b'{"op": "baseline", "outcome": "value", "value": "1.0.14"}'
        padded = valid + b" " * (gate.RESULT_LIMIT - len(valid))
        self.assertEqual(gate.RESULT_LIMIT, 65536)
        for label, output, expected in (
            ("70000 bytes of spaces before a valid reply", b" " * 70000 + valid, None),
            ("a valid reply one byte over the limit", padded + b" ", None),
            ("a valid reply of exactly the limit", padded, ("value", CURRENT)),
        ):
            with self.subTest(label):
                self.fake_extractor(forging({"baseline": output}))
                result, err = self.call_reports("baseline")
                if expected is None:
                    self.assertEqual(result, ("exit", 3), err)
                    self.assertEqual(err.splitlines(), [self.unavailable("printed more than 65536 bytes", "baseline")])
                else:
                    self.assertEqual((result, err), (expected, ""))

    def test_a_valid_reply_with_a_nonzero_exit_exits_3(self):
        # Row 80: a reply counts only when the child exits 0.
        valid = b'{"op": "baseline", "outcome": "value", "value": "1.0.14"}\n'
        for exit_code, reason in ((1, "exited 1"), (2, "exited 2"), (6, "failed unexpectedly (internal error)")):
            with self.subTest(exit_code=exit_code):
                self.fake_extractor(forging({"baseline": valid}, code=exit_code))
                result, err = self.call_reports("baseline")
                self.assertEqual(result, ("exit", 3), err)
                self.assertEqual(err.splitlines(), [self.unavailable(reason, "baseline")])

    def test_extractor_code_cannot_rewrite_the_gate_state(self):
        # Row 80: extractor code runs in the child, so a search of the live
        # objects for the globals of the gate finds nothing to rewrite there;
        # the verdict is the real one and the gate REPO is unchanged.
        self.fake_extractor(extractor_with(
            "_real_extract = extract\n"
            "def extract(text):\n"
            "    import gc\n"
            "    for found in gc.get_objects():\n"
            "        if type(found) is dict and \"release_date_call\" in found and \"REPO\" in found:\n"
            "            found[\"REPO\"] = \"attacker/repo\"\n"
            "    return _real_extract(text)\n"
        ))
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-15T09:30:00Z")
        code, out, err = self.main_reports()
        self.assertEqual(code, 0, (out, err))
        self.assertEqual(gate.REPO, "jposluns/cleanlanguage")
        self.assertIn(f"matches the publication day of release v{AHEAD}", out)

    def test_the_child_runs_isolated_under_this_interpreter(self):
        # Row 80: the child is this interpreter with -I, the extractor, and
        # --json, in an empty environment, in the tool directory, in a session
        # of its own.
        calls = []
        real_popen = subprocess.Popen

        class Recording(real_popen):
            def __init__(self, args, **kwargs):
                calls.append((list(args), kwargs))
                super().__init__(args, **kwargs)

        gate.subprocess.Popen = Recording
        try:
            result, err = self.call_reports("baseline")
        finally:
            gate.subprocess.Popen = real_popen
        self.assertEqual(result, ("value", CURRENT), err)
        self.assertEqual(len(calls), 1)
        args, kwargs = calls[0]
        self.assertEqual(args, [sys.executable, "-I", str(gate.RELEASE_DATE_TOOL), "--json"])
        self.assertEqual(kwargs["env"], {})
        self.assertEqual(kwargs["cwd"], gate.RELEASE_DATE_TOOL.parent)
        self.assertIs(kwargs["start_new_session"], True)

    def test_the_child_ignores_a_shadowing_module_and_the_gate_environment(self):
        # Row 80: the behavioural twins of the isolation. A json.py beside the
        # extractor is not imported (-I implies -P), and a variable in the
        # environment of the gate does not reach the child (env={}).
        tool = self.fake_extractor(extractor_with(
            "def extract(text):\n"
            "    import os\n"
            "    raise Malformed(\"probe=\" + os.environ.get(\"ROW80_PROBE\", \"unset\"))\n"
        ))
        marker = tool.parent / "shadowed"
        (tool.parent / "json.py").write_text(f"open({str(marker)!r}, \"w\").close()\n", encoding="utf-8")
        saved = os.environ.get("ROW80_PROBE")
        os.environ["ROW80_PROBE"] = "leaked"
        try:
            result, err = self.call_reports("extract", "x")
        finally:
            if saved is None:
                os.environ.pop("ROW80_PROBE", None)
            else:
                os.environ["ROW80_PROBE"] = saved
        self.assertEqual((result, err), (("malformed", "probe=unset"), ""))
        self.assertFalse(marker.exists())

    def test_extract_through_the_child_matches_the_function(self):
        # Row 80: the request carries any text exactly, so the child answer
        # equals the function called directly, message text included.
        valid = f"Version: {AHEAD}\nReleased: 2026-11-15\n"
        big = valid + ("x" * 79 + "\n") * 26215
        corpus = (
            ("a valid line", valid),
            ("CRLF left in the text", valid.replace("\n", "\r\n")),
            ("lone CR left in the text", valid.replace("\n", "\r")),
            ("NUL in the line", f"Version: {AHEAD}\nReleased: 2026-11-15\x00\n"),
            ("line separator in a key-like line", valid + "\u2028Released: 2026-11-01\n"),
            ("byte order mark in a key-like line", valid + "\ufeffReleased: 2026-11-01\n"),
            ("text outside the basic plane", valid + "\U0001f600\n"),
            ("no line", f"Version: {AHEAD}\n"),
            ("a 2 MB valid text", big),
        )
        self.assertGreater(len(big), 2 * 1024 * 1024)
        for label, text in corpus:
            with self.subTest(label):
                try:
                    expected = ("value", REFERENCE.extract(text))
                except REFERENCE.Malformed as error:
                    expected = ("malformed", str(error))
                self.assertEqual(self.call_reports("extract", text), (expected, ""))

    def test_the_gate_reads_skill_md_and_the_child_gets_the_decoded_text(self):
        # Row 80: the gate keeps its own universal-newline read of SKILL.md,
        # so CRLF and lone CR endings agree, and a SKILL.md that is not UTF-8
        # is the read error of the gate, never a child failure.
        for label, data in (
            ("CRLF", f"Version: {AHEAD}\r\nReleased: 2026-11-15\r\n".encode("ascii")),
            ("lone CR", f"Version: {AHEAD}\rReleased: 2026-11-15\r".encode("ascii")),
        ):
            with self.subTest(label):
                gate.SKILL.write_bytes(data)
                self.assertEqual(gate.skill_released(), "2026-11-15")
        gate.SKILL.write_bytes(f"Version: {AHEAD}\nReleased: 2026-11-15\xff\n".encode("latin-1"))
        err = io.StringIO()
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(err):
            gate.skill_released()
        self.assertEqual(caught.exception.code, 3)
        self.assertTrue(err.getvalue().startswith(
            f"check-release-checksum-live: {self.SHOWN} could not be read: 'utf-8' codec can't decode"
        ), err.getvalue())
        self.assertNotIn("unavailable", err.getvalue())

    def test_a_child_that_cannot_be_started_exits_3(self):
        # Row 80: a spawn failure, or an interpreter path that is empty or
        # relative, exits 3 as unavailable without running anything.
        gate.RELEASE_DATE_TOOL = Path(self._tmp.name) / "no-such-directory" / "skill-release-date.py"
        result, err = self.call_reports("baseline")
        self.assertEqual(result, ("exit", 3), err)
        self.assertTrue(err.startswith(
            "check-release-checksum-live: skill-release-date.py could not run (FileNotFoundError: "
        ), err)
        self.assertTrue(err.endswith(" in baseline, so the extractor is unavailable\n"), err)
        gate.RELEASE_DATE_TOOL = EXTRACTOR_PATH
        for executable in ("", "python3"):
            with self.subTest(executable=executable):
                saved = sys.executable
                sys.executable = executable
                try:
                    result, err = self.call_reports("baseline")
                finally:
                    sys.executable = saved
                self.assertEqual(result, ("exit", 3), err)
                self.assertEqual(err.splitlines(), [self.unavailable(
                    f"could not run (the interpreter path {executable!r} is not absolute)", "baseline"
                )])

    def test_a_hung_child_is_killed_with_its_group_before_it_is_reaped(self):
        # Row 80: here, where the group can be killed, a child that has not
        # ended within CHILD_TIMEOUT_SECONDS is killed through its process
        # group while it is still unreaped, so the group id cannot have been
        # reused.
        self.fake_extractor(extractor_with("def extract(text):\n    import time\n    time.sleep(300)\n"))
        gate.CHILD_TIMEOUT_SECONDS = 1
        seen = []
        real_killpg = os.killpg

        def recording(pgid, sig):
            seen.append((pgid, sig, process_state(pgid)))
            real_killpg(pgid, sig)

        gate.os.killpg = recording
        try:
            result, err = self.call_reports("extract", "x")
        finally:
            gate.os.killpg = real_killpg
        self.assertEqual(result, ("exit", 3), err)
        self.assertEqual(err.splitlines(), [self.unavailable("was not seen to end within 1 seconds", "extract")])
        self.assertEqual(len(seen), 1, seen)
        pgid, sig, state = seen[0]
        self.assertEqual(sig, signal.SIGKILL)
        self.assertIsNotNone(state, "the child was reaped before its group was killed")

    def test_an_interrupt_while_waiting_kills_the_group_and_propagates(self):
        # Row 80: a KeyboardInterrupt while the gate waits, where the group
        # can be killed, kills the child group, reaps the child, and
        # propagates unchanged. It is raised here from a stubbed os.waitid,
        # not by a real signal, which can arrive at any point of the wait; an
        # Exception while waiting exits 3 instead (see
        # test_a_failure_while_waiting_kills_and_reaps_the_child_and_exits_3).
        # Fix round 1: the gate waits with os.waitid, so the interrupt is
        # raised from there.
        self.fake_extractor(extractor_with("def extract(text):\n    import time\n    time.sleep(300)\n"))
        procs, kills = [], []
        real_popen = subprocess.Popen
        real_killpg = os.killpg
        real_waitid = os.waitid

        class Recording(real_popen):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                procs.append(self)

        def recording(pgid, sig):
            kills.append((pgid, sig))
            real_killpg(pgid, sig)

        calls = []

        def interrupted(*args):
            # Only the wait is interrupted; the reap after the kill polls
            # the real os.waitid (DISCOVERY round 4, finding 1).
            calls.append(args)
            if len(calls) == 1:
                raise KeyboardInterrupt()
            return real_waitid(*args)

        gate.subprocess.Popen = Recording
        gate.os.killpg = recording
        gate.os.waitid = interrupted
        try:
            with self.assertRaises(KeyboardInterrupt):
                gate.release_date_call("extract", "x")
        finally:
            gate.subprocess.Popen = real_popen
            gate.os.killpg = real_killpg
            gate.os.waitid = real_waitid
        self.assertEqual(len(procs), 1)
        self.assertEqual(kills, [(procs[0].pid, signal.SIGKILL)])
        self.assertEqual(procs[0].returncode, -signal.SIGKILL)

    def test_a_malformed_subclass_from_the_published_day_is_a_content_verdict(self):
        # Row 80, verdict change 3, accepted by the maintainer on 2026-11-01:
        # the child classifies with the same except Malformed the CLI uses,
        # so a subclass of Malformed raised by a modified
        # release_day_from_published_at is a content verdict (2), where the
        # in-process gate exited 3.
        self.fake_extractor(extractor_with(
            "class _Subclass(Malformed):\n    pass\n"
            "def release_day_from_published_at(value):\n    raise _Subclass(\"bad stamp\")\n"
        ))
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-15T09:30:00Z")
        code, out, err = self.main_reports()
        self.assertEqual(code, 2, (out, err))
        self.assertEqual(err.splitlines(), [f"{self.CV}the published_at of release v{AHEAD} is unusable: bad stamp"])
        self.assertEqual(out.splitlines(), [
            f"The verify page checksum {ZIP_SUM} matches the published "
            f"cleanlanguage-{AHEAD}.zip for release v{AHEAD}."
        ], out)


    # --- Row 80 fix round 1: the child machinery, its group, its bound -------

    MACHINERY = "could not be run, waited for, or read"

    def recording_popen(self, procs):
        """A Popen subclass that appends each child it starts to ``procs``."""

        class Recording(subprocess.Popen):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                procs.append(self)

        return Recording

    def test_a_failure_in_the_child_machinery_exits_3(self):
        # Fix round 1 (finding 1): an Exception (here an OSError or a
        # RuntimeError) raised while the gate creates the temporary files,
        # writes or rewinds the request, or rewinds or reads the output exits
        # 3 naming it, never a traceback (exit 1), and leaves no child
        # unreaped. A KeyboardInterrupt there is not caught and passes
        # through (see run_release_date_child).
        real_temporary_file = tempfile.TemporaryFile
        real_popen = subprocess.Popen

        class Faulty:
            """A temporary file whose method ``method`` raises ``error``."""

            def __init__(self, real, method, error):
                self._real, self._method, self._error = real, method, error

            def __getattr__(self, name):
                if name == self._method:
                    def raising(*args, **kwargs):
                        raise self._error
                    return raising
                return getattr(self._real, name)

            def __enter__(self):
                self._real.__enter__()
                return self

            def __exit__(self, *exc):
                return self._real.__exit__(*exc)

        too_many = (OSError(errno.EMFILE, "Too many open files"), "OSError: [Errno 24] Too many open files")
        no_space = (OSError(errno.ENOSPC, "No space left on device"), "OSError: [Errno 28] No space left on device")
        io_error = (OSError(errno.EIO, "Input/output error"), "OSError: [Errno 5] Input/output error")
        # (label, the file: 0 stdin, 1 stdout, 2 stderr, the method that
        # fails or None for its creation, the error and how it is named)
        cases = (
            ("the first temporary file cannot be created", 0, None, too_many),
            ("the last temporary file cannot be created", 2, None, too_many),
            ("the request cannot be written", 0, "write", no_space),
            ("the request cannot be rewound", 0, "seek", io_error),
            ("the stderr cannot be rewound", 2, "seek", io_error),
            ("the stderr cannot be read", 2, "read", io_error),
            ("the stdout cannot be read", 1, "read", io_error),
            ("an error that is not an OSError", 1, "read", (RuntimeError("boom"), "RuntimeError: boom")),
        )
        for label, index, method, (error, named) in cases:
            with self.subTest(label):
                made, procs = [], []

                def factory(*args, **kwargs):
                    position = len(made)
                    made.append(position)
                    if position == index and method is None:
                        raise error
                    real = real_temporary_file(*args, **kwargs)
                    return Faulty(real, method, error) if position == index else real

                gate.tempfile = types.SimpleNamespace(TemporaryFile=factory)
                gate.subprocess.Popen = self.recording_popen(procs)
                try:
                    result, err = self.call_reports("baseline")
                finally:
                    gate.tempfile = tempfile
                    gate.subprocess.Popen = real_popen
                self.assertEqual(result, ("exit", 3), err)
                self.assertEqual(err.splitlines(), [self.unavailable(f"{self.MACHINERY} ({named})", "baseline")])
                self.assertTrue(all(proc.returncode is not None for proc in procs), "a child was left unreaped")

    def test_a_failure_while_waiting_kills_and_reaps_the_child_and_exits_3(self):
        # Fix round 1 (finding 1): an Exception other than ChildProcessError
        # (here an OSError or a RuntimeError) while the gate waits, where the
        # group can be killed, kills the child group while the child is
        # unreaped, reaps the child, and exits 3 naming the exception.
        self.fake_extractor(extractor_with("def extract(text):\n    import time\n    time.sleep(300)\n"))
        gate.CHILD_TIMEOUT_SECONDS = 1
        real_popen, real_killpg, real_waitid = subprocess.Popen, os.killpg, os.waitid
        for label, error, named in (
            ("an OSError", OSError(errno.EINVAL, "Invalid argument"), "OSError: [Errno 22] Invalid argument"),
            ("an error that is not an OSError", RuntimeError("boom"), "RuntimeError: boom"),
        ):
            with self.subTest(label):
                procs, kills = [], []

                def recording(pgid, sig):
                    kills.append((pgid, sig, process_state(pgid)))
                    real_killpg(pgid, sig)

                calls = []

                def failing(*args):
                    # Only the wait fails; the reap after the kill polls the
                    # real os.waitid (DISCOVERY round 4, finding 1).
                    calls.append(args)
                    if len(calls) == 1:
                        raise error
                    return real_waitid(*args)

                gate.subprocess.Popen = self.recording_popen(procs)
                gate.os.killpg = recording
                gate.os.waitid = failing
                try:
                    result, err = self.call_reports("extract", "x")
                finally:
                    gate.subprocess.Popen = real_popen
                    gate.os.killpg = real_killpg
                    gate.os.waitid = real_waitid
                self.assertEqual(result, ("exit", 3), err)
                self.assertEqual(err.splitlines(), [self.unavailable(f"{self.MACHINERY} ({named})", "extract")])
                self.assertEqual(len(procs), 1)
                self.assertEqual([(pgid, sig) for pgid, sig, _ in kills], [(procs[0].pid, signal.SIGKILL)])
                self.assertIsNotNone(kills[0][2], "the child was reaped before its group was killed")
                self.assertEqual(procs[0].returncode, -signal.SIGKILL)

    def test_a_child_reaped_elsewhere_is_never_signalled(self):
        # Fix round 1 (finding 1): when the wait reports that the child is
        # no longer a child of the gate, its pid and group id may already be
        # reused, so the gate signals neither and exits 3 naming the error.
        self.fake_extractor(extractor_with("def extract(text):\n    import time\n    time.sleep(300)\n"))
        gate.CHILD_TIMEOUT_SECONDS = 1
        real_popen, real_killpg, real_waitid = subprocess.Popen, os.killpg, os.waitid
        procs, kills = [], []

        def recording(pgid, sig):
            kills.append((pgid, sig))
            real_killpg(pgid, sig)

        def gone(*args):
            raise ChildProcessError(errno.ECHILD, "No child processes")

        gate.subprocess.Popen = self.recording_popen(procs)
        gate.os.killpg = recording
        gate.os.waitid = gone
        try:
            result, err = self.call_reports("extract", "x")
        finally:
            gate.subprocess.Popen = real_popen
            gate.os.killpg = real_killpg
            gate.os.waitid = real_waitid
            for proc in procs:
                if proc.returncode is None:
                    proc.kill()
                    proc.wait()
        self.assertEqual(result, ("exit", 3), err)
        self.assertEqual(err.splitlines(), [self.unavailable(
            f"{self.MACHINERY} (ChildProcessError: [Errno 10] No child processes)", "extract"
        )])
        self.assertEqual(kills, [])

    def test_what_a_child_forked_ends_with_it_when_it_exits_normally(self):
        # Fix round 1 (finding 2): a process the child started that is still
        # in its group, here a direct child and the grandchild of a double
        # fork (which keeps the group), is killed once the child has ended
        # normally, and the group is killed while the ended child is still
        # unreaped.
        direct = (
            "    grandchild = subprocess.Popen([sys.executable, \"-I\", \"-c\", \"import time; time.sleep(300)\"])\n"
            "    pid = grandchild.pid\n"
        )
        double = (
            "    read, write = os.pipe()\n"
            "    first = os.fork()\n"
            "    if first == 0:\n"
            "        second = os.fork()\n"
            "        if second == 0:\n"
            "            time.sleep(300)\n"
            "            os._exit(0)\n"
            "        os.write(write, str(second).encode(\"ascii\"))\n"
            "        os._exit(0)\n"
            "    os.close(write)\n"
            "    os.waitpid(first, 0)\n"
            "    pid = int(os.read(read, 64))\n"
        )
        real_killpg = os.killpg
        for label, start in (("a direct child", direct), ("a double fork", double)):
            with self.subTest(label):
                tool = self.fake_extractor(extractor_with(
                    "_real_extract = extract\n"
                    "def extract(text):\n"
                    "    import os, subprocess, time\n"
                    + start +
                    "    with open(Path(__file__).resolve().parent / \"grandchild.pid\", \"w\", encoding=\"utf-8\") as handle:\n"
                    "        handle.write(str(pid))\n"
                    "    return _real_extract(text)\n"
                ))
                kills = []

                def recording(pgid, sig):
                    kills.append((pgid, sig, process_state(pgid)))
                    real_killpg(pgid, sig)

                gate.os.killpg = recording
                try:
                    result, err = self.call_reports("extract", self.ARGS["extract"])
                finally:
                    gate.os.killpg = real_killpg
                pid = int((tool.parent / "grandchild.pid").read_text(encoding="utf-8"))
                deadline = time.monotonic() + 10
                state = process_state(pid)
                while state not in (None, "Z") and time.monotonic() < deadline:
                    time.sleep(0.1)
                    state = process_state(pid)
                try:
                    self.assertEqual((result, err), (("value", "2026-11-15"), ""))
                    self.assertIn(state, (None, "Z"), f"the grandchild {pid} is still {state}")
                    self.assertEqual(len(kills), 1, kills)
                    self.assertEqual(kills[0][1], signal.SIGKILL)
                    self.assertEqual(kills[0][2], "Z", "the group was not killed while the ended child was unreaped")
                finally:
                    if state not in (None, "Z"):
                        with contextlib.suppress(OSError):
                            command = Path(f"/proc/{pid}/cmdline").read_bytes()
                            if b"time.sleep(300)" in command or str(tool).encode() in command:
                                os.kill(pid, signal.SIGKILL)

    def test_a_process_that_leaves_the_group_outlives_the_gate(self):
        # Fix round 2 (VERIFY 1.1): the disclosed residual, observed: a
        # process that leaves the child's process group, by any means, can
        # outlive the gate. Here a process the child started calls setpgid
        # into a new group, so the group kill does not reach it and it is
        # still running after the gate has returned its reply.
        tool = self.fake_extractor(extractor_with(
            "_real_extract = extract\n"
            "def extract(text):\n"
            "    import os, time\n"
            "    read, write = os.pipe()\n"
            "    pid = os.fork()\n"
            "    if pid == 0:\n"
            "        os.setpgid(0, 0)\n"
            "        os.write(write, b\"left\")\n"
            "        time.sleep(300)\n"
            "        os._exit(0)\n"
            "    os.close(write)\n"
            "    with open(Path(__file__).resolve().parent / \"leaver.pid\", \"w\", encoding=\"utf-8\") as handle:\n"
            "        handle.write(str(pid))\n"
            "    assert os.read(read, 64) == b\"left\"\n"
            "    return _real_extract(text)\n"
        ))
        pid_file = tool.parent / "leaver.pid"
        try:
            result, err = self.call_reports("extract", self.ARGS["extract"])
            self.assertEqual((result, err), (("value", "2026-11-15"), ""))
            pid = int(pid_file.read_text(encoding="utf-8"))
            time.sleep(0.5)
            self.assertEqual(process_state(pid), "S", f"the process {pid} that left the group did not outlive the gate")
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            self.assertEqual(int(stat.rsplit(")", 1)[1].split()[2]), pid, "the process did not lead a new group")
        finally:
            # Kill the process on every path, but only while it is still the
            # one this test started: it leads its own group and runs the fake
            # extractor.
            with contextlib.suppress(OSError, ValueError):
                pid = int(pid_file.read_text(encoding="utf-8"))
                command = Path(f"/proc/{pid}/cmdline").read_bytes()
                stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
                if int(stat.rsplit(")", 1)[1].split()[2]) == pid and str(tool).encode() in command:
                    os.killpg(pid, signal.SIGKILL)

    def test_a_group_that_cannot_be_killed_exits_3(self):
        # Fix round 1 (finding 3): an OSError other than ProcessLookupError
        # from the group kill exits 3 naming it, after the child is killed
        # directly where it still runs and reaped where it can be; a child
        # that cannot be killed either is not waited for.
        hung = extractor_with("def extract(text):\n    import time\n    time.sleep(300)\n")
        denied = PermissionError(errno.EPERM, "Operation not permitted")
        named = "PermissionError: [Errno 1] Operation not permitted"
        real_popen, real_killpg, real_kill = subprocess.Popen, os.killpg, os.kill
        for label, body, op, arg, error, detail, kill_fails, returncode in (
            ("after a normal exit", None, "baseline", None, denied, named, False, 0),
            ("after a timeout", hung, "extract", "x", denied, named, False, -signal.SIGKILL),
            ("another OSError after a timeout", hung, "extract", "x", OSError(errno.EINVAL, "Invalid argument"),
             "OSError: [Errno 22] Invalid argument", False, -signal.SIGKILL),
            ("after a timeout, with a child that cannot be killed either", hung, "extract", "x", denied, named,
             True, None),
        ):
            with self.subTest(label):
                if body is None:
                    gate.RELEASE_DATE_TOOL = EXTRACTOR_PATH
                else:
                    self.fake_extractor(body)
                gate.CHILD_TIMEOUT_SECONDS = 1
                procs = []

                def failing(*args):
                    raise error

                def kill_denied(*args):
                    raise denied

                gate.subprocess.Popen = self.recording_popen(procs)
                gate.os.killpg = failing
                if kill_fails:
                    gate.os.kill = kill_denied
                try:
                    started = time.monotonic()
                    result, err = self.call_reports(op, arg)
                    elapsed = time.monotonic() - started
                    returncodes = [proc.returncode for proc in procs]
                finally:
                    gate.subprocess.Popen = real_popen
                    gate.os.killpg = real_killpg
                    gate.os.kill = real_kill
                    for proc in procs:
                        if proc.returncode is None:
                            proc.kill()
                            proc.wait()
                self.assertEqual(result, ("exit", 3), err)
                self.assertEqual(err.splitlines(), [self.unavailable(
                    f"could not kill the process group of its child ({detail})", op
                )])
                self.assertEqual(returncodes, [returncode])
                self.assertLess(elapsed, 10)

    def test_an_echoed_request_of_any_size_keeps_its_verdict(self):
        # Fix round 1 (finding 4): the stdout bound grows with the request,
        # so the malformed messages tested here, which echo a long argument
        # enlarged by repr and by ASCII JSON escaping, keep the verdict and
        # the message the extractor gives, as the in-process gate did.
        published = "\u00e9" * 12000
        line = "Released: " + "\u00e9" * 12000
        try:
            REFERENCE.release_day_from_published_at(published)
        except REFERENCE.Malformed as error:
            published_message = str(error)
        text = f"Version: {AHEAD}\n{line}\n"
        try:
            REFERENCE.extract(text)
        except REFERENCE.Malformed as error:
            line_message = str(error)
        self.assertEqual(self.call_reports("release_day_from_published_at", published),
                         (("malformed", published_message), ""))
        self.assertEqual(self.call_reports("extract", text), (("malformed", line_message), ""))
        # The worst case per character: each of these, repeated, is echoed
        # through repr and ASCII JSON at its largest.
        for character in ("\u00e9", "\U0001f600", "\x00", "\\", "\U000e0001", "'", "\"", "\t", "\u2028"):
            for op, arg in (
                ("release_day_from_published_at", character * 20000),
                ("extract", f"Version: {AHEAD}\nReleased: " + character * 20000 + "\n"),
            ):
                with self.subTest(op=op, character=character):
                    function = getattr(REFERENCE, op)
                    try:
                        expected = ("value", function(arg))
                    except REFERENCE.Malformed as error:
                        expected = ("malformed", str(error))
                    self.assertEqual(self.call_reports(op, arg), (expected, ""))
        # Through the whole gate: the published_at verdict stays 2 with its
        # message, and the Released line verdict stays 3 with its message.
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published(published)
        code, out, err = self.main_reports()
        self.assertEqual(code, 2, (out, err))
        self.assertEqual(err.splitlines(), [f"{self.CV}the published_at of release v{AHEAD} is unusable: {published_message}"])
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, line)
        try:
            REFERENCE.extract(gate.SKILL.read_text(encoding="utf-8"))
        except REFERENCE.Malformed as error:
            skill_message = str(error)
        self.published("2026-11-15T09:30:00Z")
        code, out, err = self.main_reports()
        self.assertEqual(code, 3, (out, err))
        self.assertEqual(err.splitlines(), [
            f"check-release-checksum-live: the Released line in {self.SHOWN} is malformed: {skill_message}"
        ])

    def test_the_stdout_bound_of_a_call_with_an_argument_grows_with_it(self):
        # Fix round 1 (finding 4): the bound is RESULT_LIMIT plus 12 bytes
        # for each character of the argument; a reply of exactly that size is
        # accepted and one byte more is refused, naming the bound.
        valid = b'{"op": "extract", "outcome": "absent"}'
        limit = gate.RESULT_LIMIT + 12 * len("xy")
        padded = valid + b" " * (limit - len(valid))
        for label, output, expected in (
            ("a reply of exactly the bound", padded, (("value", None), "")),
            ("a reply one byte over the bound", padded + b" ", None),
        ):
            with self.subTest(label):
                self.fake_extractor(forging({"extract": output}))
                result = self.call_reports("extract", "xy")
                if expected is None:
                    self.assertEqual(result[0], ("exit", 3), result[1])
                    self.assertEqual(result[1].splitlines(), [self.unavailable(
                        f"printed more than {limit} bytes", "extract"
                    )])
                else:
                    self.assertEqual(result, expected)

    def test_a_reply_with_a_repeated_key_exits_3(self):
        # Fix round 1 (finding 5): a reply is exactly one JSON object that
        # matches the contract, so a key given twice is refused, never read
        # with the last value winning.
        rule = "printed a result that does not match the contract (a key appears more than once)"
        for label, output in (
            ("a repeated value", b'{"op": "extract", "outcome": "value", "value": "2026-11-15", "value": "2026-11-16"}\n'),
            ("a repeated outcome", b'{"op": "extract", "outcome": "malformed", "outcome": "absent"}\n'),
            ("a repeated op with the same value", b'{"op": "extract", "op": "extract", "outcome": "absent"}\n'),
        ):
            with self.subTest(label):
                self.fake_extractor(forging({"extract": output}))
                result, err = self.call_reports("extract", "x")
                self.assertEqual(result, ("exit", 3), err)
                self.assertEqual(err.splitlines(), [self.unavailable(rule, "extract")])

    # A fake extractor whose extract op has a process in another session
    # seize the child with ptrace (the child names it its tracer first), so
    # the end of the child is reported to that tracer, which holds it for
    # HOLD seconds, and not to the gate; the child writes the tracer pid to
    # tracer.pid beside it and exits 9 when the seize is refused.
    TRACED = (
        "_real_extract = extract\n"
        "def extract(text):\n"
        "    import ctypes, os, time\n"
        "    libc = ctypes.CDLL(None, use_errno=True)\n"
        "    libc.ptrace.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]\n"
        "    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]\n"
        "    me = os.getpid()\n"
        "    go_r, go_w = os.pipe()\n"
        "    done_r, done_w = os.pipe()\n"
        "    tracer = os.fork()\n"
        "    if tracer == 0:\n"
        "        os.setsid()\n"
        "        os.read(go_r, 1)\n"
        "        seized = libc.ptrace(0x4206, me, None, None) == 0\n"
        "        os.write(done_w, b\"ok\" if seized else b\"refused\")\n"
        "        time.sleep(HOLD)\n"
        "        os._exit(0)\n"
        "    with open(Path(__file__).resolve().parent / \"tracer.pid\", \"w\", encoding=\"utf-8\") as handle:\n"
        "        handle.write(str(tracer))\n"
        "    libc.prctl(0x59616d61, tracer, 0, 0, 0)\n"
        "    os.write(go_w, b\"x\")\n"
        "    if os.read(done_r, 64) != b\"ok\":\n"
        "        raise SystemExit(9)\n"
        "    return _real_extract(text)\n"
    )

    def test_a_child_whose_end_is_hidden_from_the_gate_ends_the_gate_within_the_bound(self):
        # DISCOVERY round 4, finding 1: a process of the same uid in another
        # session seizes the child with ptrace, so the child's end is
        # reported to it and not to the gate. The gate sees no end within
        # the timeout, kills the group, then sees no end within the reap
        # grace either, and exits 3 naming that it could not reap the child,
        # leaving it, within the two bounds, instead of blocking in a reap
        # until the tracer exits (30 seconds here). The test skips only where
        # the host refuses the seize; the next test simulates the same
        # outcome in-process on every host.
        tool = self.fake_extractor(extractor_with(self.TRACED.replace("HOLD", "30")))
        gate.CHILD_TIMEOUT_SECONDS = 1
        gate.REAP_GRACE_SECONDS = 1
        procs = []
        real_popen = subprocess.Popen
        gate.subprocess.Popen = self.recording_popen(procs)
        pid_file = tool.parent / "tracer.pid"
        try:
            started = time.monotonic()
            result, err = self.call_reports("extract", self.ARGS["extract"])
            elapsed = time.monotonic() - started
            if result == ("exit", 3) and "exited 9" in err:
                self.skipTest("this host refuses PTRACE_SEIZE of the child")
            states = [process_state(proc.pid) for proc in procs]
            returncodes = [proc.returncode for proc in procs]
        finally:
            gate.subprocess.Popen = real_popen
            # Kill the tracer by its recorded pid, only while it is the
            # process this test started (it runs the fake extractor), and
            # then reap the child, whose end the gate now sees.
            with contextlib.suppress(OSError, ValueError):
                pid = int(pid_file.read_text(encoding="utf-8"))
                if str(tool).encode() in Path(f"/proc/{pid}/cmdline").read_bytes():
                    os.kill(pid, signal.SIGKILL)
            for proc in procs:
                if proc.returncode is None:
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        proc.wait(timeout=10)
        self.assertEqual(result, ("exit", 3), err)
        self.assertEqual(err.splitlines(), [self.unavailable(
            "could not be reaped (the gate saw no end of it within 1 seconds after its kill)", "extract"
        )])
        self.assertLess(elapsed, 10)
        # The child had ended (a zombie held by the tracer) and was left unreaped.
        self.assertEqual(states, ["Z"])
        self.assertEqual(returncodes, [None])

    def test_a_child_not_seen_to_end_after_its_kill_is_left_unreaped(self):
        # DISCOVERY round 4, finding 1, simulated in-process on every host:
        # os.waitid never reports the end of the child, as when another
        # process holds it, so after the timeout and the group kill the
        # gate polls for at most the reap grace, exits 3 naming that it
        # could not reap the child, and does not reap it.
        self.fake_extractor(extractor_with("def extract(text):\n    import time\n    time.sleep(300)\n"))
        gate.CHILD_TIMEOUT_SECONDS = 1
        gate.REAP_GRACE_SECONDS = 1
        procs, kills = [], []
        real_popen, real_killpg, real_waitid = subprocess.Popen, os.killpg, os.waitid

        def recording(pgid, sig):
            kills.append((pgid, sig))
            real_killpg(pgid, sig)

        def hidden(idtype, ident, options):
            if options & os.WNOHANG:
                return None
            return real_waitid(idtype, ident, options)

        gate.subprocess.Popen = self.recording_popen(procs)
        gate.os.killpg = recording
        gate.os.waitid = hidden
        try:
            started = time.monotonic()
            result, err = self.call_reports("extract", "x")
            elapsed = time.monotonic() - started
            returncodes = [proc.returncode for proc in procs]
        finally:
            gate.subprocess.Popen = real_popen
            gate.os.killpg = real_killpg
            gate.os.waitid = real_waitid
            for proc in procs:
                if proc.returncode is None:
                    proc.kill()
                    proc.wait()
        self.assertEqual(result, ("exit", 3), err)
        self.assertEqual(err.splitlines(), [self.unavailable(
            "could not be reaped (the gate saw no end of it within 1 seconds after its kill)", "extract"
        )])
        self.assertEqual(kills, [(procs[0].pid, signal.SIGKILL)])
        self.assertEqual(returncodes, [None])
        self.assertLess(elapsed, 10)

    def test_every_mapped_extractor_outcome_reaches_its_exit_and_message_through_main(self):
        # DISCOVERY round 4, finding 3, at the width of the class: each place
        # in the gate that turns an outcome of release_date_call into an exit
        # code or a message (the malformed and absent mapping in
        # release_date_call, the probe in probe_release_date_tool, the
        # malformed handlers in skill_released, released_line, and
        # check_release_date, and the baseline in
        # report_missing_released_line) is pinned here through main, with its
        # exact exit and output, so removing any one of them fails this test.
        matches = f"The verify page checksum {ZIP_SUM} matches the published cleanlanguage-{AHEAD}.zip for release v{AHEAD}."
        missing = [
            "Release date inconsistency found:",
            f"  - release v{AHEAD} is published",
            f"  - cleanlanguage/skills/cleanlanguage/SKILL.md names {AHEAD}, above the undated baseline {CURRENT}, "
            f"but has no Released: line",
        ]
        rejected = b'{"message": "a forged verdict", "op": "requires_release_date", "outcome": "malformed"}\n'
        for label, extractor, site_sum, skill, released, published_at, expected in (
            ("extract malformed: skill_released exits 3", None, ZIP_SUM, AHEAD, "Released: soon",
             "2026-11-15T09:30:00Z",
             (3, [matches], [
                 "check-release-checksum-live: the Released line in cleanlanguage/skills/cleanlanguage/SKILL.md "
                 "is malformed: the first Released line is not a bare YYYY-MM-DD date: 'Released: soon'"
             ])),
            ("requires_release_date malformed: released_line exits 3",
             forging({"requires_release_date": rejected}), ZIP_SUM, AHEAD, None, "2026-11-15T09:30:00Z",
             (3, [matches], [
                 f"check-release-checksum-live: the SKILL.md version {AHEAD} was rejected by the extractor: "
                 f"a forged verdict"
             ])),
            ("release_day_from_published_at malformed: check_release_date exits 2", None, ZIP_SUM, AHEAD,
             "Released: 2026-11-15", "null",
             (2, [matches], [
                 f"check-release-checksum-live: could not verify: the published_at of release v{AHEAD} is "
                 f"unusable: published_at is not a YYYY-MM-DDTHH:MM:SSZ instant: 'null'"
             ])),
            ("extract absent above the baseline: the missing line and the baseline are reported", None, ZIP_SUM,
             AHEAD, None, "2026-11-15T09:30:00Z",
             (1, missing + [matches], [])),
            ("extract absent at the baseline: no line is required", None, ZIP_SUM, CURRENT, None,
             "2026-11-15T09:30:00Z",
             (0, [f"The verify page checksum {ZIP_SUM} matches the published cleanlanguage-{CURRENT}.zip "
                  f"for release v{CURRENT}."], [])),
            ("baseline unavailable: the probe contributes 3 and the checks still run",
             forging({"baseline": b""}, code=1), OTHER_SUM, AHEAD, "Released: 2026-11-15", "2026-11-15T09:30:00Z",
             (3, [
                 f"The SKILL.md Released date 2026-11-15 matches the publication day of release v{AHEAD}.",
                 "Release checksum drift found:",
                 f"  - the verify page shows {OTHER_SUM} for version {AHEAD}",
                 f"  - the published cleanlanguage-{AHEAD}.zip is {ZIP_SUM}",
                 "",
                 f"The release v{AHEAD} is published but the site was not flipped to its checksum. Run the "
                 f"orchestrator's post-release site flip (tools/set-release-links.py with checksum {ZIP_SUM}); "
                 f"see the release runbook.",
             ], [PROBE_FAILED])),
        ):
            with self.subTest(label):
                if extractor is None:
                    gate.RELEASE_DATE_TOOL = EXTRACTOR_PATH
                else:
                    self.fake_extractor(extractor)
                self.fixtures(skill, site_sum, skill, released)
                self.published(published_at)
                code, out, err = self.main_reports()
                self.assertEqual((code, out.splitlines(), err.splitlines()), expected)


class ModuleLoadTest(unittest.TestCase):
    """F5: the gate exits 3 (unavailable), not 1 (drift), when the extractor
    cannot be run or its child fails, for each reason tested here. Row 80:
    each test runs a copy of the gate as a script, so an outcome that would
    end or hang the gate itself is observed by the test rather than suffered
    by it. Extractor code that signals the gate itself is the accepted
    residual, not an exit 3 (see
    test_extractor_that_interrupts_the_gate_ends_the_gate_by_sigint)."""

    def run_with_extractor(self, body, wrapper=None, inspect=None):
        """Run a copy of the gate as a script beside the extractor source
        ``body`` (None for no extractor), returning (exit code, stderr).
        ``wrapper``, when given, is Python source run in place of the gate
        script, with the path of the gate copy as its first argument;
        ``inspect``, when given, is called with the tools directory after the
        run, before it is removed, and its result is returned third. An outer
        timeout of 120 seconds makes a gate that hangs fail the test. The gate
        runs with only PATH, an empty directory, and TMPDIR, a directory inside
        the temporary directory of the test."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = root / "tools"
            tools.mkdir()
            shutil.copy2(MODULE_PATH, tools / MODULE_PATH.name)
            if body is not None:
                (tools / "skill-release-date.py").write_text(body, encoding="utf-8")
            # The gate probes the extractor inside main and goes on to the
            # checksum comparison, so give it the pages it reads and an empty
            # PATH: gh is then absent, so no network call can be made.
            page = root / "site" / "verify" / "index.html"
            page.parent.mkdir(parents=True)
            page.write_text(VERIFY.format(version=AHEAD, checksum=OTHER_SUM), encoding="utf-8")
            skill = root / "cleanlanguage" / "skills" / "cleanlanguage" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(f"Version: {AHEAD}\n", encoding="utf-8")
            empty = root / "empty-path"
            empty.mkdir()
            # Fix round 1: a TMPDIR inside this directory, so the temporary
            # files of the gate, which its children write to, never go to
            # bare /tmp. A child runs with an empty environment, so a
            # temporary file it made itself would not follow TMPDIR.
            scratch = root / "tmp"
            scratch.mkdir()
            if wrapper is None:
                command = [sys.executable, "-I", str(tools / MODULE_PATH.name)]
            else:
                command = [sys.executable, "-I", "-c", wrapper, str(tools / MODULE_PATH.name)]
            proc = subprocess.run(
                command, capture_output=True, text=True, env={"PATH": str(empty), "TMPDIR": str(scratch)}, timeout=120,
            )
            inspected = inspect(tools) if inspect is not None else None
        if inspect is not None:
            return proc.returncode, proc.stderr, inspected
        return proc.returncode, proc.stderr

    def test_missing_extractor_exits_3(self):
        code, err = self.run_with_extractor(None)
        self.assertEqual(code, 3, err)
        self.assertIn("skill-release-date.py exited 2 in baseline, so the extractor is unavailable", err)
        self.assertIn("can't open file", err)

    def test_syntax_error_exits_3(self):
        code, err = self.run_with_extractor("def broken(:\n")
        self.assertEqual(code, 3, err)
        self.assertIn("skill-release-date.py exited 1 in baseline, so the extractor is unavailable", err)
        self.assertIn("SyntaxError", err)

    def test_exception_while_loading_exits_3(self):
        code, err = self.run_with_extractor("raise RuntimeError(\"boom\")\n")
        self.assertEqual(code, 3, err)
        self.assertIn("skill-release-date.py exited 1 in baseline, so the extractor is unavailable", err)
        self.assertIn("RuntimeError", err)

    def test_extractor_keyboard_interrupt_exits_3_and_the_comparison_runs(self):
        # Row 80, verdict change 1: a KeyboardInterrupt the extractor raises,
        # at load or in a call, ends only the child, which Python then ends
        # with SIGINT. The gate exits 3 with its report and the checksum
        # comparison still runs, where the in-process gate ended with the
        # SIGINT status (fix round 5 residual, now closed for an interrupt the
        # extractor raises; one it sends to the gate is still a residual, see
        # test_extractor_that_interrupts_the_gate_ends_the_gate_by_sigint).
        for label, body, op in (
            ("KeyboardInterrupt at load", "raise KeyboardInterrupt()\n", "baseline"),
            ("KeyboardInterrupt in a call",
             extractor_with("def extract(text):\n    raise KeyboardInterrupt()\n"), "extract"),
        ):
            with self.subTest(label):
                code, err = self.run_with_extractor(body)
                self.assertEqual(code, 3, err)
                self.assertIn(f"skill-release-date.py was killed by signal SIGINT in {op}, "
                              f"so the extractor is unavailable", err)
                self.assertIn("KeyboardInterrupt", err)
                self.assertIn("the gh CLI is not available", err)

    def test_extractor_keyboard_interrupt_subclass_exits_3(self):
        # Fix round 9: a subclass of KeyboardInterrupt the extractor raises,
        # at load or in a call, exits 3 with its report. Row 80: Python ends
        # the child with SIGINT for it as for KeyboardInterrupt itself.
        subclass = "class K(KeyboardInterrupt):\n    pass\n"
        for label, body, op in (
            ("a KeyboardInterrupt subclass at load", subclass + "raise K()\n", "baseline"),
            ("a KeyboardInterrupt subclass in a call",
             extractor_with(subclass + "def extract(text):\n    raise K()\n"), "extract"),
        ):
            with self.subTest(label):
                code, err = self.run_with_extractor(body)
                self.assertEqual(code, 3, err)
                self.assertIn(f"skill-release-date.py was killed by signal SIGINT in {op}, "
                              f"so the extractor is unavailable", err)
                self.assertIn("the gh CLI is not available", err)

    def test_extractor_interrupt_that_is_also_another_class_exits_3(self):
        # Fix round 8 (claude LOW 1): a KeyboardInterrupt that is also a
        # SystemExit, at load or in a call, exits 3 with its report, never the
        # code the SystemExit carries or an interrupt. Row 80: Python 3.14
        # ends the child for it with SIGINT, as for a KeyboardInterrupt
        # (observed), so the report names the signal whatever code it carries.
        hybrid = "class H(KeyboardInterrupt, SystemExit):\n    pass\n"
        cases = [
            (f"an interrupt that is also SystemExit({code}) at load", hybrid + f"raise H({code})\n",
             "was killed by signal SIGINT in baseline")
            for code in (0, 1, 2, 3)
        ] + [
            ("an interrupt that is also SystemExit(0) in a call",
             extractor_with(hybrid + "def extract(text):\n    raise H(0)\n"), "was killed by signal SIGINT in extract"),
        ]
        for label, body, reason in cases:
            with self.subTest(label):
                code, err = self.run_with_extractor(body)
                self.assertEqual(code, 3, err)
                self.assertIn(f"skill-release-date.py {reason}, so the extractor is unavailable", err)
                self.assertIn("the gh CLI is not available", err)

    def test_system_exit_while_loading_exits_3(self):
        # Row 58: an extractor that raises SystemExit while it loads is
        # unavailable (exit 3), whatever code it raises, never a pass (0) or
        # a drift (1). Row 80: the child ends with that code and prints no
        # result.
        for label, body, reason in (
            ("SystemExit(0) at load", "raise SystemExit(0)\n", "did not print a JSON result"),
            ("SystemExit(1) at load", "raise SystemExit(1)\n", "exited 1"),
            # Fix round 4 (F2): the codes main absorbs as could not verify.
            ("SystemExit(2) at load", "raise SystemExit(2)\n", "exited 2"),
            ("SystemExit(3) at load", "raise SystemExit(3)\n", "exited 3"),
            ("bare SystemExit at load", "raise SystemExit\n", "did not print a JSON result"),
        ):
            with self.subTest(label):
                code, err = self.run_with_extractor(body)
                self.assertEqual(code, 3, err)
                self.assertIn(f"skill-release-date.py {reason} in baseline, so the extractor is unavailable", err)

    def test_extractor_code_run_while_reporting_a_load_failure_exits_3(self):
        # Fix round 4 (F1): an error whose repr, str, or class name exits or
        # raises, a SystemExit whose code does, or an error outside Exception
        # and SystemExit, still exits 3 with the report, never 0 or 1. Row
        # 80: that code runs only in the child, while Python reports it.
        hostile_text = "    def __repr__(self):\n        raise SystemExit(0)\n    __str__ = __repr__\n"
        exiting_str = (
            "class S(str):\n    def _exit(self, *args, **kwargs):\n        raise SystemExit(0)\n"
            "    __eq__ = __ne__ = __format__ = __str__ = __repr__ = __bool__ = __len__ = _exit\n"
            "    __hash__ = str.__hash__\n"
        )
        for label, body in (
            ("a SystemExit code whose repr exits 0", "class C:\n" + hostile_text + "raise SystemExit(C())\n"),
            ("an error whose repr and str exit 0", "class E(Exception):\n" + hostile_text + "raise E()\n"),
            ("an error whose repr and str raise",
             "class E(Exception):\n    def __repr__(self):\n        raise RuntimeError(\"x\")\n"
             "    __str__ = __repr__\nraise E()\n"),
            ("an error whose class name and str exit 0",
             "class M(type):\n    @property\n    def __name__(cls):\n        raise SystemExit(0)\n"
             "class E(Exception, metaclass=M):\n    def __str__(self):\n        raise SystemExit(0)\n"
             "raise E()\n"),
            ("a BaseException subclass at load", "class B(BaseException):\n    pass\nraise B()\n"),
            ("an error whose str is a str subclass whose methods exit 0",
             exiting_str + "class E(Exception):\n    def __str__(self):\n        return S(\"boom\")\nraise E()\n"),
            ("an error whose class name is a str subclass whose methods exit 0",
             exiting_str + "class M(type):\n    @property\n    def __name__(cls):\n        return S(\"E\")\n"
             "class E(Exception, metaclass=M):\n    pass\nraise E()\n"),
        ):
            with self.subTest(label):
                code, err = self.run_with_extractor(body)
                self.assertEqual(code, 3, err)
                self.assertIn(" in baseline, so the extractor is unavailable", err)

    def test_incomplete_extractor_api_exits_3_naming_the_attribute(self):
        # R3: an incomplete or incompatible extractor exits 3 naming what it
        # lacks. Row 80: a function that is missing or not callable fails the
        # child that runs it (exit 6, its NameError or TypeError relayed),
        # and a baseline that is not a bare version breaks the contract. A
        # missing release_day_from_published_at is reached only on a
        # published release (see test_extractor_attribute_gone_at_call_time),
        # and the Malformed class rows have no subject, since no extractor
        # class reaches the gate.
        internal = "failed unexpectedly (internal error)"
        version = "printed a result that does not match the contract (the value is not a bare X.Y.Z version string)"
        for label, tail, reason, detail in (
            ("missing extract", "del extract\n", f"{internal} in extract", "NameError(\"name 'extract' is not defined\")"),
            ("non-callable extract", "extract = 5\n", f"{internal} in extract", "TypeError(\"'int' object is not callable\")"),
            ("missing requires_release_date", "del requires_release_date\n", f"{internal} in requires_release_date",
             "NameError(\"name 'requires_release_date' is not defined\")"),
            ("BASELINE_VERSION not a version", "BASELINE_VERSION = 14\n", f"{version} in baseline", None),
            # Fix round 8 (operator sweep): an exact str that is not a bare
            # version is refused by the gate itself, even beside a baseline
            # rule that would not reject it.
            ("BASELINE_VERSION an exact str that is not a bare version",
             "BASELINE_VERSION = \"1.0\"\ndef requires_release_date(version):\n    return True\n",
             f"{version} in baseline", None),
        ):
            with self.subTest(label):
                code, err = self.run_with_extractor(extractor_with(tail))
                self.assertEqual(code, 3, err)
                self.assertIn(f"skill-release-date.py {reason}, so the extractor is unavailable", err)
                if detail is not None:
                    self.assertIn(detail, err)
                self.assertNotIn("does not exist", err)

    # --- Row 80: what extractor code does to its own process ends only the child

    def test_extractor_that_signals_its_own_process_exits_3(self):
        # Without the child the gate itself would end by that signal.
        for name in ("SIGKILL", "SIGSEGV"):
            with self.subTest(name):
                code, err = self.run_with_extractor(extractor_with(
                    f"def extract(text):\n    import os, signal\n    os.kill(os.getpid(), signal.{name})\n"
                ))
                self.assertEqual(code, 3, err)
                self.assertIn(f"skill-release-date.py was killed by signal {name} in extract, "
                              f"so the extractor is unavailable", err)
                self.assertIn("the gh CLI is not available", err)

    def test_extractor_that_never_returns_exits_3(self):
        # The wrapper sets a 1 second child timeout; without the child the
        # gate hangs and the outer timeout fails the test.
        code, err = self.run_with_extractor(
            extractor_with("def extract(text):\n    import time\n    time.sleep(300)\n"), wrapper=TIMEOUT_WRAPPER,
        )
        self.assertEqual(code, 3, err)
        self.assertIn("skill-release-date.py was not seen to end within 1 seconds in extract, "
                      "so the extractor is unavailable", err)
        self.assertIn("the gh CLI is not available", err)

    def test_a_hung_extractor_and_what_it_forked_are_killed(self):
        # A process the hung child started in its group is killed with it:
        # once the gate has exited it is gone, or a zombie where no process
        # reaps it, never still running.
        body = extractor_with(
            "def extract(text):\n"
            "    import subprocess, time\n"
            "    grandchild = subprocess.Popen([sys.executable, \"-I\", \"-c\", \"import time; time.sleep(300)\"])\n"
            "    with open(Path(__file__).resolve().parent / \"grandchild.pid\", \"w\", encoding=\"utf-8\") as handle:\n"
            "        handle.write(str(grandchild.pid))\n"
            "    time.sleep(300)\n"
        )

        def grandchild_state(tools):
            pid = int((tools / "grandchild.pid").read_text(encoding="utf-8"))
            deadline = time.monotonic() + 10
            state = process_state(pid)
            while state not in (None, "Z") and time.monotonic() < deadline:
                time.sleep(0.1)
                state = process_state(pid)
            return pid, state

        code, err, (pid, state) = self.run_with_extractor(body, wrapper=TIMEOUT_WRAPPER, inspect=grandchild_state)
        try:
            self.assertEqual(code, 3, err)
            self.assertIn("skill-release-date.py was not seen to end within 1 seconds in extract", err)
            self.assertIn(state, (None, "Z"), f"the grandchild {pid} is still {state}")
        finally:
            if state not in (None, "Z"):
                with contextlib.suppress(OSError):
                    if b"time.sleep(300)" in Path(f"/proc/{pid}/cmdline").read_bytes():
                        os.kill(pid, signal.SIGKILL)

    def test_extractor_that_calls_os_exit_exits_3(self):
        # Without the child the gate would end with the code os._exit names.
        exiting = "def extract(text):\n    import os\n"
        for label, body, reason in (
            ("os._exit(0) before any output", extractor_with(exiting + "    os._exit(0)\n"),
             "did not print a JSON result in extract"),
            ("os._exit(0) after half a JSON object",
             extractor_with(exiting + "    sys.stdout.write('{\"op\": \"ext')\n    sys.stdout.flush()\n    os._exit(0)\n"),
             "did not print a JSON result in extract"),
            ("os._exit(0) at load", extractor_with("import os\nos._exit(0)\n"), "did not print a JSON result in baseline"),
            ("os._exit(1)", extractor_with(exiting + "    os._exit(1)\n"), "exited 1 in extract"),
            ("os._exit(3)", extractor_with(exiting + "    os._exit(3)\n"), "exited 3 in extract"),
        ):
            with self.subTest(label):
                code, err = self.run_with_extractor(body)
                self.assertEqual(code, 3, err)
                self.assertIn(f"skill-release-date.py {reason}, so the extractor is unavailable", err)
                self.assertIn("the gh CLI is not available", err)

    def test_extractor_output_that_is_not_one_json_object_exits_3(self):
        valid = b'{"op": "baseline", "outcome": "value", "value": "1.0.14"}'
        no_result = "did not print a JSON result"
        for label, output, reason in (
            ("a bare day", b"2026-11-15\n", no_result),
            ("an object then text", valid + b"\njunk\n", no_result),
            ("two objects", valid + b"\n" + valid + b"\n", no_result),
            ("a byte that is not ASCII", valid[:-1] + b', "x": "\xc3\xa9"}\n', no_result),
            ("nothing at all", b"", no_result),
            ("nesting too deep to parse", b"[" * 60000, no_result),
            ("a top-level list", b"[" + valid + b"]\n",
             "printed a result that does not match the contract (not a JSON object)"),
        ):
            with self.subTest(label):
                code, err = self.run_with_extractor(forging({"*": output}))
                self.assertEqual(code, 3, err)
                self.assertIn(f"skill-release-date.py {reason} in baseline, so the extractor is unavailable", err)
                self.assertIn("the gh CLI is not available", err)

    def test_hostile_exception_in_the_child_exits_3(self):
        # Extractor code that runs while the child reports its own error, or
        # an interrupt it raises, ends only the child.
        hostile = "class _Hostile(Exception):\n    def __repr__(self):\n        {action}\n    __str__ = __repr__\n"
        for label, extra, reason in (
            ("an error whose repr and str raise SystemExit(0)",
             hostile.format(action="raise SystemExit(0)") + "def extract(text):\n    raise _Hostile()\n",
             "did not print a JSON result"),
            ("an error whose repr and str call os._exit(0)",
             hostile.format(action="import os; os._exit(0)") + "def extract(text):\n    raise _Hostile()\n",
             "did not print a JSON result"),
            ("a KeyboardInterrupt", "def extract(text):\n    raise KeyboardInterrupt()\n",
             "was killed by signal SIGINT"),
            ("a KeyboardInterrupt that is also a SystemExit",
             "class _H(KeyboardInterrupt, SystemExit):\n    pass\ndef extract(text):\n    raise _H()\n",
             "was killed by signal SIGINT"),
        ):
            with self.subTest(label):
                code, err = self.run_with_extractor(extractor_with(extra))
                self.assertEqual(code, 3, err)
                self.assertIn(f"skill-release-date.py {reason} in extract, so the extractor is unavailable", err)
                self.assertIn("the gh CLI is not available", err)

    # --- Row 80: the accepted same-uid residual, observed ---------------------

    def test_extractor_that_interrupts_the_gate_ends_the_gate_by_sigint(self):
        # Fix round 3 (DISCOVERY 2, finding 1): the child runs with the uid
        # of the gate, so extractor code can signal the gate. An interrupt
        # it sends to its parent, the gate, while the gate waits ends the
        # gate by SIGINT, with no report and none of its exit codes, after
        # the gate has killed the child. The probe sleeps first, so the gate
        # is already waiting. Fix round 4 (DISCOVERY 3, finding 5): the probe
        # signals its parent only when one argument of that parent resolves
        # to the gate copy that run_with_extractor started, and otherwise
        # loads as the real extractor, so on a gate that runs extractor code
        # in its own process, whose parent is this test runner, the test
        # fails instead of interrupting the runner. A stop (SIGSTOP) is the
        # same residual and is not run here, as it would halt the gate.
        body = extractor_with(
            "import os, signal, time\n"
            "with open(Path(__file__).resolve().parent / \"child.pid\", \"w\", encoding=\"utf-8\") as handle:\n"
            "    handle.write(str(os.getpid()))\n"
            "time.sleep(0.5)\n"
            "_parent = os.getppid()\n"
            f"_gate_copy = os.path.realpath(Path(__file__).resolve().parent / {MODULE_PATH.name!r})\n"
            "try:\n"
            "    with open(f\"/proc/{_parent}/cmdline\", \"rb\") as handle:\n"
            "        _arguments = [argument for argument in handle.read().split(b\"\\0\") if argument]\n"
            "except OSError:\n"
            "    _arguments = []\n"
            "if any(os.path.realpath(os.fsdecode(argument)) == _gate_copy for argument in _arguments):\n"
            "    os.kill(_parent, signal.SIGINT)\n"
            "    time.sleep(300)\n"
        )

        def child_state(tools):
            pid = int((tools / "child.pid").read_text(encoding="utf-8"))
            deadline = time.monotonic() + 10
            state = process_state(pid)
            while state not in (None, "Z") and time.monotonic() < deadline:
                time.sleep(0.1)
                state = process_state(pid)
            return pid, state

        code, err, (pid, state) = self.run_with_extractor(body, inspect=child_state)
        try:
            self.assertEqual(code, -signal.SIGINT, err)
            self.assertIn("KeyboardInterrupt", err)
            self.assertNotIn("so the extractor is unavailable", err)
            self.assertNotIn("the gh CLI is not available", err)
            self.assertIn(state, (None, "Z"), f"the child {pid} is still {state}")
        finally:
            if state not in (None, "Z"):
                with contextlib.suppress(OSError):
                    if b"skill-release-date.py" in Path(f"/proc/{pid}/cmdline").read_bytes():
                        os.kill(pid, signal.SIGKILL)

    def test_the_gate_keeps_its_temporary_files_in_the_test_directory(self):
        # Fix round 1 addition: a gate run in this suite is given a TMPDIR
        # inside the test's own temporary directory, so no temporary file
        # of the gate, and so none its child writes to, goes to bare /tmp.
        # An audit hook records where each temporary file is made.
        wrapper = (
            "import importlib.util, json, os, sys\n"
            "made = []\n"
            "def hook(event, args):\n"
            "    if event in (\"tempfile.mkstemp\", \"tempfile.mkdtemp\"):\n"
            "        made.append(os.fsdecode(args[0]))\n"
            "    elif event == \"open\" and hasattr(os, \"O_TMPFILE\") and type(args[2]) is int \\\n"
            "            and args[2] & os.O_TMPFILE == os.O_TMPFILE:\n"
            "        made.append(os.fsdecode(args[0]))\n"
            "sys.addaudithook(hook)\n"
            "spec = importlib.util.spec_from_file_location(\"gate_copy\", sys.argv[1])\n"
            "gate = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(gate)\n"
            "try:\n"
            "    code = gate.main()\n"
            "except SystemExit as stop:\n"
            "    code = stop.code\n"
            "with open(os.path.join(os.path.dirname(sys.argv[1]), \"temporary-paths.json\"), \"w\") as handle:\n"
            "    json.dump(made, handle)\n"
            "sys.exit(code)\n"
        )

        def outside(tools):
            root = tools.parent.resolve()
            made = json.loads((tools / "temporary-paths.json").read_text(encoding="utf-8"))
            return made, [path for path in made if not Path(path).resolve().is_relative_to(root)]

        code, err, (made, stray) = self.run_with_extractor(
            EXTRACTOR_PATH.read_text(encoding="utf-8"), wrapper=wrapper, inspect=outside,
        )
        # With gh absent the release status cannot be read (2); the
        # Released line is then checked offline.
        self.assertEqual(code, 2, err)
        # The probe and the offline extract each make three temporary files.
        self.assertGreaterEqual(len(made), 6, made)
        self.assertEqual(stray, [], f"temporary files made outside the test directory: {stray}")

    def test_too_few_file_descriptors_exits_3_with_no_traceback(self):
        # Fix round 1 (finding 1): with the open-file limit so low that the
        # temporary files of a child cannot all be created, the probe exits
        # 3 naming the error, and the gate exits 3, never a traceback (exit 1).
        wrapper = (
            "import importlib.util, os, resource, sys\n"
            "spec = importlib.util.spec_from_file_location(\"gate_copy\", sys.argv[1])\n"
            "gate = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(gate)\n"
            "highest = max(int(name) for name in os.listdir(\"/proc/self/fd\"))\n"
            "resource.setrlimit(resource.RLIMIT_NOFILE, (highest + 1, resource.getrlimit(resource.RLIMIT_NOFILE)[1]))\n"
            "sys.exit(gate.main())\n"
        )
        code, err = self.run_with_extractor(EXTRACTOR_PATH.read_text(encoding="utf-8"), wrapper=wrapper)
        self.assertEqual(code, 3, err)
        self.assertIn("skill-release-date.py could not be run, waited for, or read (OSError: [Errno 24] "
                      "Too many open files", err)
        self.assertIn(" in baseline, so the extractor is unavailable", err)
        self.assertNotIn("Traceback", err)


class ContractRoutingTest(unittest.TestCase):
    """Row 80 (replaces the R3 attribute routing): every op the gate names is
    in the contract, every op of the contract is used, and the only calls
    inside a function of the gate that start a process through an attribute
    of subprocess or os are in gh and in run_release_date_child. A start at
    module level, or through another name, an alias, or another module, is
    not detected."""

    def setUp(self):
        self.tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))

    def test_every_routed_op_is_in_the_contract(self):
        routed, dynamic = [], []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in (
                "release_date_call", "run_release_date_child"
            ):
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    routed.append(first.value)
                else:
                    dynamic.append(ast.unparse(first))
        self.assertEqual(sorted(set(routed)), sorted(gate.RELEASE_DATE_CONTRACT))
        # The only non-literal op is release_date_call passing its own
        # parameter on.
        self.assertEqual(dynamic, ["name"])

    def test_processes_start_only_in_gh_and_the_child_runner(self):
        starters = {"Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput",
                    "system", "popen", "fork", "forkpty", "startfile"}
        starts = []
        for func in ast.walk(self.tree):
            if isinstance(func, ast.FunctionDef):
                for node in ast.walk(func):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id in ("subprocess", "os")
                            and (node.func.attr in starters
                                 or node.func.attr.startswith(("exec", "spawn", "posix_spawn")))):
                        starts.append((func.name, node.func.value.id, node.func.attr))
        self.assertEqual(sorted(starts), [("gh", "subprocess", "run"), ("run_release_date_child", "subprocess", "Popen")])


if __name__ == "__main__":
    unittest.main()
