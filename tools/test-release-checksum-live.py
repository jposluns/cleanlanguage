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
reported as such, never read as drift. The gate reads the extractor module only through the
attributes it declares and validates at load. The network reads of that record are replaced
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
import hashlib
import importlib.util
import io
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "check-release-checksum-live.py"
spec = importlib.util.spec_from_file_location("check_release_checksum_live", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
# The gate loads the extractor inside main, never at import, so a load failure
# cannot hide the checksum comparison; load it here once for the tests that
# patch the loaded module.
if gate.RELEASE_DATE is None:
    gate.RELEASE_DATE = gate._load_release_date_tool()

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


class _Hostile:
    """Fix round 4 (F1): a value every method of which the gate could reach
    exits 0, standing in for extractor-defined code that misbehaves."""

    def _exit(self, *args, **kwargs):
        raise SystemExit(0)

    __repr__ = __str__ = __format__ = __bool__ = __eq__ = __ne__ = _exit
    __hash__ = None


class _ExitingText(Exception):
    """An error whose repr and str exit 0."""

    def __repr__(self):
        raise SystemExit(0)

    __str__ = __repr__


class _RaisingText(Exception):
    """An error whose repr and str raise RuntimeError."""

    def __repr__(self):
        raise RuntimeError("repr failed")

    __str__ = __repr__


class _ExitingNameMeta(type):
    @property
    def __name__(cls):
        raise SystemExit(0)


class _ExitingName(Exception, metaclass=_ExitingNameMeta):
    """An error whose class name and str exit 0."""

    def __str__(self):
        raise SystemExit(0)


class _Escape(BaseException):
    """An error outside Exception and SystemExit."""


class _ExitingMalformed(gate.RELEASE_DATE.Malformed):
    """A Malformed verdict whose str exits 0."""

    def __str__(self):
        raise SystemExit(0)


class _ExitingCheckMeta(type):
    def __instancecheck__(cls, instance):
        raise SystemExit(0)

    def __subclasscheck__(cls, subclass):
        raise SystemExit(0)


class _ExitingCheckMalformed(Exception, metaclass=_ExitingCheckMeta):
    """A Malformed class whose instance and subclass checks exit 0."""


class _ExitingVersion(str):
    """A BASELINE_VERSION whose format and str exit 0."""

    def __format__(self, spec):
        raise SystemExit(0)

    __str__ = __format__


_REAL_MALFORMED = gate.RELEASE_DATE.Malformed


class _ClassSpoofExit(SystemExit):
    """Fix round 5: a SystemExit whose __class__ property names the real
    Malformed class, a claim isinstance honours."""

    __class__ = property(lambda self: _REAL_MALFORMED)


class _ClassSpoofError(RuntimeError):
    """Fix round 5: an ordinary error whose __class__ property names the real
    Malformed class, so only the real type of the error can refuse it."""

    __class__ = property(lambda self: _REAL_MALFORMED)


class _MalformedExit(SystemExit, _REAL_MALFORMED):
    """Fix round 5: a SystemExit that really inherits the Malformed class."""


class _MroSpoofMeta(type):
    def mro(cls):
        return (cls, _REAL_MALFORMED) + _REAL_MALFORMED.__mro__[1:]


class _MroSpoofExit(SystemExit, metaclass=_MroSpoofMeta):
    """Fix round 5: an error built on SystemExit whose metaclass gives it an
    MRO that names the Malformed class."""


class _AcceptingInstanceMeta(type):
    def __instancecheck__(cls, instance):
        return True


class _AcceptingInstanceMalformed(Exception, metaclass=_AcceptingInstanceMeta):
    """Fix round 5: a Malformed class whose instance check accepts anything."""


class _AcceptingSubclassMeta(type):
    def __subclasscheck__(cls, subclass):
        return True


class _AcceptingSubclassMalformed(Exception, metaclass=_AcceptingSubclassMeta):
    """Fix round 5: a Malformed class whose subclass check accepts anything."""


class _PretendClass:
    """Fix round 5: a Malformed that only claims to be an exception class,
    through a __class__ property and __bases__, and whose own instance and
    subclass checks accept anything."""

    __class__ = property(lambda self: type)
    __bases__ = (Exception,)

    def __instancecheck__(self, instance):
        return True

    def __subclasscheck__(self, subclass):
        return True


class _ExitingStr(str):
    """Fix round 6 (claude MEDIUM 1): a str subclass every method of which
    the gate could reach exits 0. isinstance(value, str) accepts it, so only
    an exact type check refuses it."""

    def _exit(self, *args, **kwargs):
        raise SystemExit(0)

    __eq__ = __ne__ = __format__ = __str__ = __repr__ = __bool__ = __len__ = _exit
    __hash__ = str.__hash__


class _ClaimsType:
    """Fix round 6: a value that only claims, through a __class__ property,
    to be of the builtin type ``claimed``, a claim isinstance honours, and
    every method of which the gate could reach exits 0. bool cannot be
    subclassed, so such a claim is the only way a value other than True or
    False passes isinstance(value, bool)."""

    claimed = None
    __class__ = property(lambda self: type(self).claimed)

    def _exit(self, *args, **kwargs):
        raise SystemExit(0)

    __eq__ = __ne__ = __format__ = __str__ = __repr__ = __bool__ = __len__ = _exit
    __hash__ = None


class _ClaimsStr(_ClaimsType):
    claimed = str


class _ClaimsBool(_ClaimsType):
    claimed = bool


class _ClaimsNone(_ClaimsType):
    """Fix round 7 (codex LOW): a value that only claims to be None, so
    only an exact type check refuses it as a result of extract. NoneType
    cannot be subclassed, so such a claim is the only way a value other than
    None passes isinstance(value, type(None))."""

    claimed = type(None)


class _ExitingStrText(Exception):
    """Fix round 6: an error whose str is an _ExitingStr."""

    def __str__(self):
        return _ExitingStr("boom")


class _ExitingStrNameMeta(type):
    @property
    def __name__(cls):
        return _ExitingStr("Boom")


class _ExitingStrName(Exception, metaclass=_ExitingStrNameMeta):
    """Fix round 6: an error whose class name is an _ExitingStr."""


class _ClaimsStrNameMeta(type):
    @property
    def __name__(cls):
        return _ClaimsStr()


class _ClaimsStrName(Exception, metaclass=_ClaimsStrNameMeta):
    """Fix round 6: an error whose class name only claims to be a str."""


class _ExitingStrMalformed(_REAL_MALFORMED):
    """Fix round 6: a genuine Malformed verdict whose str is an _ExitingStr."""

    def __str__(self):
        return _ExitingStr("bad stamp")


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
        self.assertEqual(gate.main(), 0)
        self.assertEqual(self.asked, [f"v{AHEAD}"])

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
        self.fixtures(CURRENT, ZIP_SUM, AHEAD)
        self.published("2026-11-15T09:30:00Z", statuses={f"v{AHEAD}": 404}, tags={f"v{AHEAD}": 503})
        with self.assertRaises(SystemExit) as caught:
            gate.main()
        self.assertEqual(caught.exception.code, 2)

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
        with self.assertRaises(SystemExit) as caught:
            gate.main()
        self.assertEqual(caught.exception.code, 2)

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
        def undecodable(*args, check=True):
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

        def denied(*args, check=True):
            raise PermissionError(13, "Permission denied")

        readers = (
            ("release_immutable", self._saved[7]), ("release_published_at", self._saved[6]),
            ("release_status", self._saved[3]), ("tag_status", self._saved[4]),
        )
        for name, reader in readers:
            for fake in (undecodable, denied):
                with self.subTest(name, error=fake.__name__):
                    gate.gh = fake
                    err = io.StringIO()
                    with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(err):
                        reader("v1.0.15")
                    self.assertEqual(caught.exception.code, 2)
                    self.assertIn("could not verify: could not read", err.getvalue())

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
        # Round 5: the extractor is loaded inside main, so a load failure
        # contributes exit 3 while the checksum comparison still runs and
        # reports the drift.
        real = (MODULE_PATH.parent / "skill-release-date.py").read_text(encoding="utf-8")
        for label, body, reason in (
            ("missing extractor", None, "could not load skill-release-date.py"),
            ("syntax-broken extractor", "def broken(:\n", "SyntaxError"),
            ("API-invalid extractor", real + "\nextract = 5\n", "lacks a usable extract "),
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
        # F5: an unexpected failure of the loaded extractor is unavailable
        # (exit 3), never a drift verdict (exit 1).
        saved = gate.RELEASE_DATE.release_day_from_published_at

        def crash(value):
            raise RuntimeError("boom")

        gate.RELEASE_DATE.release_day_from_published_at = crash
        try:
            self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
            self.published("2026-11-15T09:30:00Z")
            with self.assertRaises(SystemExit) as caught:
                gate.main()
            self.assertEqual(caught.exception.code, 3)
        finally:
            gate.RELEASE_DATE.release_day_from_published_at = saved

    def test_extractor_raising_system_exit_exits_3(self):
        # Row 58: an extractor that raises SystemExit, whatever its code, is
        # unavailable (exit 3), never a pass (0) or a drift (1), whether it
        # raises it inside a call or from a lookup on the module.
        def stop_with(code):
            def stop(*args, **kwargs):
                raise SystemExit(code)
            return stop

        # Fix round 4 (F2): 2 and 3 too, the codes release_date_code and main
        # absorb as could not verify, so a pass-through of either fails here.
        for stop_code in (0, 1, 2, 3, None):
            for place in ("call", "lookup"):
                with self.subTest(code=stop_code, place=place):
                    saved = gate.RELEASE_DATE.release_day_from_published_at
                    if place == "call":
                        gate.RELEASE_DATE.release_day_from_published_at = stop_with(stop_code)
                        reason = "failed unexpectedly in release_day_from_published_at"
                    else:
                        del gate.RELEASE_DATE.release_day_from_published_at
                        gate.RELEASE_DATE.__getattr__ = stop_with(stop_code)
                        reason = "lacks release_day_from_published_at"
                    try:
                        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
                        self.published("2026-11-15T09:30:00Z")
                        code, out, err = self.main_reports()
                        self.assertEqual(code, 3, (out, err))
                        self.assertIn(reason, err)
                        self.assertIn("SystemExit", err)
                    finally:
                        vars(gate.RELEASE_DATE).pop("__getattr__", None)
                        gate.RELEASE_DATE.release_day_from_published_at = saved

    def test_extractor_code_run_by_the_gate_cannot_escape_exit_3(self):
        # Fix round 4 (F1): beyond the call itself the gate reaches extractor
        # code through the repr, str, and class name of a caught error, the
        # Malformed class checks, and the methods of a returned value or of
        # BASELINE_VERSION. Whatever that code raises, a SystemExit of any
        # code or another exception, the gate exits 3 (unavailable), never 0
        # (a silent pass) or 1 (drift), and the checksum comparison still runs.
        def raising(error):
            def call(*args, **kwargs):
                raise error
            return call

        def returning(value):
            def call(*args, **kwargs):
                return value
            return call

        released = "Released: 2026-11-15  "
        failed = "failed unexpectedly in release_day_from_published_at"
        cases = (
            ("repr and str exit 0", "release_day_from_published_at", raising(_ExitingText()), released, failed),
            ("repr and str raise", "release_day_from_published_at", raising(_RaisingText()), released, failed),
            ("a SystemExit code whose repr exits 0", "release_day_from_published_at",
             raising(SystemExit(_Hostile())), released, failed),
            ("class name and str exit 0", "release_day_from_published_at", raising(_ExitingName()), released, failed),
            ("a BaseException subclass", "release_day_from_published_at", raising(_Escape()), released, failed),
            ("a Malformed verdict whose str exits 0", "release_day_from_published_at",
             raising(_ExitingMalformed()), released, failed),
            # Fix round 5: a Malformed class with a custom metaclass is refused
            # as unusable before any of its hooks can run.
            ("a Malformed class whose checks exit 0", "Malformed", _ExitingCheckMalformed, released,
             "lacks a usable Malformed (expected an exception class)"),
            ("extract returns a hostile value", "extract", returning(_Hostile()), released,
             "returned an unusable result from extract"),
            ("requires_release_date returns a hostile value", "requires_release_date", returning(_Hostile()), None,
             "returned an unusable result from requires_release_date"),
            ("release_day_from_published_at returns a hostile value", "release_day_from_published_at",
             returning(_Hostile()), released, "returned an unusable result from release_day_from_published_at"),
            ("BASELINE_VERSION with a hostile format", "BASELINE_VERSION", _ExitingVersion("1.0.14"), None,
             "lacks a usable BASELINE_VERSION "),
            # Fix round 6 (claude MEDIUM 1): each exact type check, of the result
            # of every extractor function and of the text _guarded_text reads,
            # refuses a str subclass and a value that only claims its type,
            # either of which isinstance would accept and whose methods would
            # then exit 0 later in the gate.
            ("extract returns a str subclass whose methods exit 0", "extract",
             returning(_ExitingStr("2026-11-15")), released, "returned an unusable result from extract"),
            ("extract returns a value that only claims to be a str", "extract",
             returning(_ClaimsStr()), released, "returned an unusable result from extract"),
            # Fix round 7 (codex LOW): the None alternative of extract is
            # checked by identity too, so a value that only claims to be None
            # is refused.
            ("extract returns a value that only claims to be None", "extract",
             returning(_ClaimsNone()), released, "returned an unusable result from extract"),
            ("requires_release_date returns a value that only claims to be a bool", "requires_release_date",
             returning(_ClaimsBool()), None, "returned an unusable result from requires_release_date"),
            ("release_day_from_published_at returns a str subclass whose methods exit 0",
             "release_day_from_published_at", returning(_ExitingStr("2026-11-15")), released,
             "returned an unusable result from release_day_from_published_at"),
            ("release_day_from_published_at returns a value that only claims to be a str",
             "release_day_from_published_at", returning(_ClaimsStr()), released,
             "returned an unusable result from release_day_from_published_at"),
            ("an error whose str is a str subclass whose methods exit 0", "release_day_from_published_at",
             raising(_ExitingStrText()), released, failed + ": _ExitingStrText: (its message could not be read)"),
            ("an error whose class name is a str subclass whose methods exit 0", "release_day_from_published_at",
             raising(_ExitingStrName()), released, failed + ": an error whose class name could not be read"),
            ("an error whose class name only claims to be a str", "release_day_from_published_at",
             raising(_ClaimsStrName()), released, failed + ": an error whose class name could not be read"),
            ("a Malformed verdict whose str is a str subclass whose methods exit 0",
             "release_day_from_published_at", raising(_ExitingStrMalformed()), released,
             failed + ": _ExitingStrMalformed: (its message could not be read)"),
            # Fix round 7 (claude informational): _describe reads the class name
            # from the real type of the error, never its __class__, so an error
            # whose __class__ property names another class is described by the
            # name of its own class.
            ("an error whose __class__ property names another class", "release_day_from_published_at",
             raising(_ClassSpoofError("boom")), released, failed + ": _ClassSpoofError: boom"),
        )
        for label, name, value, line, reason in cases:
            with self.subTest(label):
                saved = vars(gate.RELEASE_DATE)[name]
                saved_day = gate.RELEASE_DATE.release_day_from_published_at
                setattr(gate.RELEASE_DATE, name, value)
                if name == "Malformed":
                    gate.RELEASE_DATE.release_day_from_published_at = raising(RuntimeError("boom"))
                try:
                    self.fixtures(AHEAD, ZIP_SUM, AHEAD, line)
                    self.published("2026-11-15T09:30:00Z")
                    code, out, err = self.main_reports()
                    self.assertEqual(code, 3, (out, err))
                    self.assertIn(reason, err)
                    self.assertIn("matches the published", out)
                finally:
                    setattr(gate.RELEASE_DATE, name, saved)
                    gate.RELEASE_DATE.release_day_from_published_at = saved_day

    def test_hostile_error_text_from_an_api_lookup_exits_3(self):
        # Fix round 6 (claude MEDIUM 1): release_date_attr describes a failed
        # lookup through _describe too, so an error whose str or class name is
        # a str subclass whose methods exit 0 still exits 3 with the report,
        # and the checksum comparison still runs.
        for label, error, shown in (
            ("str", _ExitingStrText(), "_ExitingStrText: (its message could not be read)"),
            ("class name", _ExitingStrName(), "an error whose class name could not be read"),
        ):
            with self.subTest(label):
                saved = gate.RELEASE_DATE.release_day_from_published_at

                def lookup(name):
                    raise error

                del gate.RELEASE_DATE.release_day_from_published_at
                gate.RELEASE_DATE.__getattr__ = lookup
                try:
                    self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
                    self.published("2026-11-15T09:30:00Z")
                    code, out, err = self.main_reports()
                    self.assertEqual(code, 3, (out, err))
                    self.assertIn("lacks release_day_from_published_at: " + shown, err)
                    self.assertIn("matches the published", out)
                finally:
                    vars(gate.RELEASE_DATE).pop("__getattr__", None)
                    gate.RELEASE_DATE.release_day_from_published_at = saved

    def test_spoofed_malformed_classification_exits_3(self):
        # Fix round 5 (codex MEDIUM): the Malformed classification reads only
        # what extractor code cannot fake. A SystemExit of any code, or an
        # error that only claims to be a Malformed verdict through a __class__
        # property, a metaclass instance or subclass check, or a metaclass
        # mro, or a Malformed that only claims to be a class, is unavailable
        # (exit 3), never a content verdict (exit 2), and the checksum
        # comparison still runs.
        failed = "failed unexpectedly in release_day_from_published_at"
        unusable = "lacks a usable Malformed (expected an exception class)"
        cases = (
            ("a SystemExit whose __class__ property names Malformed", _ClassSpoofExit, None, failed),
            ("a SystemExit that also inherits Malformed", _MalformedExit, None, failed),
            ("an error built on SystemExit whose metaclass mro names Malformed", _MroSpoofExit, None, failed),
            ("a Malformed metaclass whose instance check accepts anything", SystemExit,
             _AcceptingInstanceMalformed, unusable),
            ("a Malformed metaclass whose subclass check accepts anything", SystemExit,
             _AcceptingSubclassMalformed, unusable),
            ("a Malformed that only claims to be a class", SystemExit, _PretendClass(), unusable),
        )
        for label, error_class, malformed, reason in cases:
            for stop_code in (0, 1, 2, 3, None):
                with self.subTest(label, code=stop_code):
                    self.assert_verdict(error_class(stop_code), malformed, 3, reason)
        with self.subTest("an ordinary error whose __class__ property names Malformed"):
            self.assert_verdict(_ClassSpoofError("boom"), None, 3, failed)
        # The control: a genuine Malformed verdict is still a content verdict.
        with self.subTest("a genuine Malformed verdict"):
            self.assert_verdict(_REAL_MALFORMED("bad stamp"), None, 2,
                                f"the published_at of release v{AHEAD} is unusable: bad stamp")

    def assert_verdict(self, error, malformed, expected, reason):
        """Run the gate with release_day_from_published_at raising ``error``
        and, unless it is None, Malformed replaced by ``malformed``."""
        saved_day = gate.RELEASE_DATE.release_day_from_published_at
        saved_malformed = gate.RELEASE_DATE.Malformed

        def raising(*args, **kwargs):
            raise error

        gate.RELEASE_DATE.release_day_from_published_at = raising
        if malformed is not None:
            gate.RELEASE_DATE.Malformed = malformed
        try:
            self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
            self.published("2026-11-15T09:30:00Z")
            code, out, err = self.main_reports()
            self.assertEqual(code, expected, (out, err))
            self.assertIn(reason, err)
            if expected == 3:
                self.assertNotIn("is unusable", err)
            self.assertIn("matches the published", out)
        finally:
            gate.RELEASE_DATE.release_day_from_published_at = saved_day
            gate.RELEASE_DATE.Malformed = saved_malformed

    def test_unexpected_status_of_the_site_release_does_not_hide_the_date_check(self):
        # Row 62: a status other than 200 or 404 for the release the site
        # names stops only the checksum comparison (exit 2); the release-date
        # check still runs and reports, and the more severe code wins. A
        # malformed line is read before any probe of the newer release.
        for label, released, expected, reason, probed in (
            ("date mismatch", "Released: 2026-11-15  ", 2, "Release date inconsistency found",
             [f"v{CURRENT}", f"v{AHEAD}"]),
            ("malformed Released line", "Released: soon", 3,
             "Released line in cleanlanguage/skills/cleanlanguage/SKILL.md is malformed", [f"v{CURRENT}"]),
        ):
            with self.subTest(label):
                self.fixtures(CURRENT, ZIP_SUM, AHEAD, released)
                self.published("2026-11-16T00:00:01Z", statuses={f"v{CURRENT}": 503})
                code, out, err = self.main_reports()
                self.assertEqual(code, expected, (out, err))
                self.assertIn(f"could not verify: unexpected HTTP 503 reading release v{CURRENT}", err)
                self.assertIn(reason, out + err)
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
        # R3: every lookup is resolved inside the protected wrapper, so an
        # attribute missing at call time is unavailable (exit 3), never an
        # uncaught AttributeError (exit 1, drift).
        for name, released in (
            ("extract", "Released: 2026-11-15  "),
            ("release_day_from_published_at", "Released: 2026-11-15  "),
            ("requires_release_date", None),
            ("Malformed", "Released: 2026-11-15  "),
        ):
            with self.subTest(name):
                saved = getattr(gate.RELEASE_DATE, name)
                delattr(gate.RELEASE_DATE, name)
                try:
                    self.fixtures(AHEAD, ZIP_SUM, AHEAD, released)
                    self.published("2026-11-15T09:30:00Z")
                    with self.assertRaises(SystemExit) as caught:
                        gate.main()
                    self.assertEqual(caught.exception.code, 3)
                finally:
                    setattr(gate.RELEASE_DATE, name, saved)

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
        for tag_state, stop in (
            (200, "exists but release"), (503, "unexpected HTTP 503 reading tag"),
            ("unreadable", "could not read the tag status"),
        ):
            for label, version, released, expected, reason in (
                ("malformed line", AHEAD, "Released: soon", 3,
                 "the Released line in cleanlanguage/skills/cleanlanguage/SKILL.md is malformed"),
                ("line missing above the baseline", AHEAD, None, 2,
                 f"names {AHEAD}, above the undated baseline {CURRENT}, but has no Released: line"),
                ("valid line", AHEAD, "Released: 2026-11-15  ", 2, None),
                ("undated baseline", CURRENT, None, 2, None),
            ):
                with self.subTest(tag=tag_state, case=label):
                    code, out, err = self.offline_reports(version, released, tag_state)
                    self.assertEqual(code, expected, (out, err))
                    self.assertIn("could not verify: ", err)
                    self.assertIn(stop, err)
                    if reason is None:
                        self.assertNotIn("inconsistency", out)
                    else:
                        self.assertIn(reason, out + err)

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

        for label, site, skill, released, expected, reason in (
            ("malformed line, same version", AHEAD, AHEAD, "Released: soon", 3, "is malformed"),
            ("malformed line, newer SKILL.md, read before any probe", CURRENT, AHEAD,
             "Released: soon", 3, "is malformed"),
            ("line missing above the baseline", AHEAD, AHEAD, None, 2,
             f"the release state of v{AHEAD}, the version the verify page names, could not be verified"),
            ("valid line", AHEAD, AHEAD, "Released: 2026-11-15  ", 2, None),
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
                self.assertIn("could not read the release status", err)
                if reason is None:
                    self.assertNotIn("inconsistency", out)
                else:
                    self.assertIn(reason, out + err)
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

        for label, released, newer, immutable, expected, reason, asked in (
            ("date mismatch", "Released: 2026-11-01  ", 200, "true", 2,
             "Release date inconsistency found", [f"v{AHEAD}"]),
            ("matching date", "Released: 2026-11-15  ", 200, "true", 2,
             f"matches the publication day of release v{AHEAD}", [f"v{AHEAD}"]),
            ("line missing above the baseline", None, 200, "true", 2,
             f"names {AHEAD}, above the undated baseline {CURRENT}, but has no Released: line", []),
            ("record not immutable", "Released: 2026-11-15  ", 200, "false", 2,
             f"the immutable field of release v{AHEAD} is", []),
            ("newer release not published", "Released: 2026-11-15  ", 404, "true", 2,
             f"Release v{AHEAD}, the version SKILL.md names, is not published yet", []),
            ("newer release unexpected status", "Released: 2026-11-15  ", 503, "true", 2,
             f"unexpected HTTP 503 reading release v{AHEAD}, the version SKILL.md names", []),
        ):
            with self.subTest(label):
                self.fixtures(CURRENT, OTHER_SUM, AHEAD, released)
                self.published("2026-11-15T09:30:00Z", immutable=immutable)
                gate.release_status = statuses(newer)
                gate.gh = unexpected_call
                code, out, err = self.main_reports()
                self.assertEqual(code, expected, (out, err))
                self.assertIn("could not read the release status for v1.0.14", err)
                self.assertIn(reason, out + err)
                self.assertEqual(self.probed, [f"v{CURRENT}", f"v{AHEAD}"])
                self.assertEqual(self.asked, asked)
                self.assertNotIn(f"v{CURRENT}", self.tag_probed + self.immutable_asked)

    def test_unverifiable_newer_release_still_reports_a_missing_released_line(self):
        # Sibling of MEDIUM 2 inside the date check: an unverifiable state of
        # the release SKILL.md names keeps exit 2 but still reports a Released
        # line missing above the baseline.
        for label, statuses, tags in (
            ("tag without release", {f"v{AHEAD}": 404}, {f"v{AHEAD}": 200}),
            ("unexpected tag status", {f"v{AHEAD}": 404}, {f"v{AHEAD}": 503}),
            ("unexpected release status", {f"v{AHEAD}": 503}, {}),
        ):
            with self.subTest(label):
                self.fixtures(CURRENT, ZIP_SUM, AHEAD)
                self.published("2026-11-15T09:30:00Z", statuses=statuses, tags=tags)
                code, out, err = self.main_reports()
                self.assertEqual(code, 2, (out, err))
                self.assertIn("could not verify: ", err)
                self.assertIn(
                    f"the release state of v{AHEAD}, the version SKILL.md names, could not be verified", out
                )
                self.assertIn(f"names {AHEAD}, above the undated baseline {CURRENT}, but has no Released: line", out)

    def test_unexpected_status_of_the_same_release_reports_once_and_keeps_the_date_check(self):
        # Row 62, same-version case: the site and SKILL.md name the same
        # release and it returns 503. A malformed Released line still exits 3,
        # and the status is reported in one could-not-verify line, not two.
        for label, released, expected, reason in (
            ("malformed Released line", "Released: soon", 3,
             "the Released line in cleanlanguage/skills/cleanlanguage/SKILL.md is malformed"),
            ("line missing above the baseline", None, 2,
             f"names {AHEAD}, above the undated baseline {CURRENT}, but has no Released: line"),
            ("valid line", "Released: 2026-11-15  ", 2, None),
        ):
            with self.subTest(label):
                self.fixtures(AHEAD, ZIP_SUM, AHEAD, released)
                self.published("2026-11-15T09:30:00Z", statuses={f"v{AHEAD}": 503})
                code, out, err = self.main_reports()
                self.assertEqual(code, expected, (out, err))
                self.assertEqual(err.count("unexpected HTTP 503 reading release"), 1, err)
                if reason is not None:
                    self.assertIn(reason, out + err)
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


class ModuleLoadTest(unittest.TestCase):
    """F5: the gate exits 3 (unavailable), not 1 (drift), when the extractor
    module cannot be loaded, whatever the reason."""

    def run_with_extractor(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = root / "tools"
            tools.mkdir()
            shutil.copy2(MODULE_PATH, tools / MODULE_PATH.name)
            if body is not None:
                (tools / "skill-release-date.py").write_text(body, encoding="utf-8")
            # The gate loads the extractor inside main and goes on to the
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
            proc = subprocess.run(
                [sys.executable, "-I", str(tools / MODULE_PATH.name)], capture_output=True, text=True,
                env={"PATH": str(empty)},
            )
        return proc.returncode, proc.stderr

    def test_missing_extractor_exits_3(self):
        code, err = self.run_with_extractor(None)
        self.assertEqual(code, 3, err)
        self.assertIn("the extractor is unavailable", err)

    def test_syntax_error_exits_3(self):
        code, err = self.run_with_extractor("def broken(:\n")
        self.assertEqual(code, 3, err)
        self.assertIn("SyntaxError", err)

    def test_exception_while_loading_exits_3(self):
        code, err = self.run_with_extractor("raise RuntimeError(\"boom\")\n")
        self.assertEqual(code, 3, err)
        self.assertIn("RuntimeError", err)

    def test_extractor_keyboard_interrupt_is_an_interrupt_not_a_pass_or_drift(self):
        # Fix round 5 (claude LOW 1): the documented residual. A
        # KeyboardInterrupt the extractor raises, or a subclass, at load or in
        # a call, is let through as an interrupt, since the gate cannot tell it
        # from a real Ctrl-C by its type: the gate ends with the SIGINT status,
        # never 0 (a pass) or 1 (drift), and at load before the checksum
        # comparison runs.
        source = (MODULE_PATH.parent / "skill-release-date.py").read_text(encoding="utf-8")
        subclass = "class K(KeyboardInterrupt):\n    pass\n"
        for label, body, at_load in (
            ("KeyboardInterrupt at load", "raise KeyboardInterrupt()\n", True),
            ("a KeyboardInterrupt subclass at load", subclass + "raise K()\n", True),
            ("KeyboardInterrupt in a call",
             source + "\ndef extract(text):\n    raise KeyboardInterrupt()\n", False),
            ("a KeyboardInterrupt subclass in a call",
             source + "\n" + subclass + "def extract(text):\n    raise K()\n", False),
        ):
            with self.subTest(label):
                code, err = self.run_with_extractor(body)
                self.assertNotIn(code, (0, 1), err)
                self.assertEqual(code, -signal.SIGINT, err)
                self.assertIn("KeyboardInterrupt" if "subclass" not in label else "K", err)
                if at_load:
                    self.assertNotIn("the gh CLI is not available", err)

    def test_system_exit_while_loading_exits_3(self):
        # Row 58: an extractor that raises SystemExit while it loads, or from
        # a lookup the load validates, is unavailable (exit 3), whatever code
        # it raises, never a pass (0) or a drift (1).
        source = (MODULE_PATH.parent / "skill-release-date.py").read_text(encoding="utf-8")
        lookup = source + "\ndel extract\ndef __getattr__(name):\n    raise SystemExit(0)\n"
        for label, body, reason in (
            ("SystemExit(0) at load", "raise SystemExit(0)\n", "could not load skill-release-date.py"),
            ("SystemExit(1) at load", "raise SystemExit(1)\n", "could not load skill-release-date.py"),
            # Fix round 4 (F2): the codes main absorbs as could not verify.
            ("SystemExit(2) at load", "raise SystemExit(2)\n", "could not load skill-release-date.py"),
            ("SystemExit(3) at load", "raise SystemExit(3)\n", "could not load skill-release-date.py"),
            ("bare SystemExit at load", "raise SystemExit\n", "could not load skill-release-date.py"),
            ("SystemExit(0) from an API lookup", lookup, "lacks a usable extract "),
        ):
            with self.subTest(label):
                code, err = self.run_with_extractor(body)
                self.assertEqual(code, 3, err)
                self.assertIn(reason, err)
                self.assertIn("the extractor is unavailable", err)

    def test_extractor_code_run_while_reporting_a_load_failure_exits_3(self):
        # Fix round 4 (F1): the report of a load failure runs no unguarded
        # extractor code, so an error whose repr, str, or class name exits or
        # raises, a SystemExit whose code does, or an error outside Exception
        # and SystemExit, still exits 3 with the report, never 0 or 1.
        source = (MODULE_PATH.parent / "skill-release-date.py").read_text(encoding="utf-8")
        hostile_text = "    def __repr__(self):\n        raise SystemExit(0)\n    __str__ = __repr__\n"
        for label, body, reason in (
            ("a SystemExit code whose repr exits 0",
             "class C:\n" + hostile_text + "raise SystemExit(C())\n", "could not load skill-release-date.py"),
            ("an error whose repr and str exit 0",
             "class E(Exception):\n" + hostile_text + "raise E()\n", "could not load skill-release-date.py"),
            ("an error whose repr and str raise",
             "class E(Exception):\n    def __repr__(self):\n        raise RuntimeError(\"x\")\n"
             "    __str__ = __repr__\nraise E()\n", "could not load skill-release-date.py"),
            ("an error whose class name and str exit 0",
             "class M(type):\n    @property\n    def __name__(cls):\n        raise SystemExit(0)\n"
             "class E(Exception, metaclass=M):\n    def __str__(self):\n        raise SystemExit(0)\n"
             "raise E()\n", "could not load skill-release-date.py"),
            ("a BaseException subclass at load",
             "class B(BaseException):\n    pass\nraise B()\n", "could not load skill-release-date.py"),
            # Fix round 6 (claude MEDIUM 1): a text or class name that is a str
            # subclass whose methods exit 0 is refused by the exact type check
            # in _guarded_text, so the load report still exits 3.
            ("an error whose str is a str subclass whose methods exit 0",
             "class S(str):\n    def _exit(self, *args, **kwargs):\n        raise SystemExit(0)\n"
             "    __eq__ = __ne__ = __format__ = __str__ = __repr__ = __bool__ = __len__ = _exit\n"
             "    __hash__ = str.__hash__\n"
             "class E(Exception):\n    def __str__(self):\n        return S(\"boom\")\nraise E()\n",
             "could not load skill-release-date.py (the extractor is unavailable): E: (its message could not be read)"),
            ("an error whose class name is a str subclass whose methods exit 0",
             "class S(str):\n    def _exit(self, *args, **kwargs):\n        raise SystemExit(0)\n"
             "    __eq__ = __ne__ = __format__ = __str__ = __repr__ = __bool__ = __len__ = _exit\n"
             "    __hash__ = str.__hash__\n"
             "class M(type):\n    @property\n    def __name__(cls):\n        return S(\"E\")\n"
             "class E(Exception, metaclass=M):\n    pass\nraise E()\n",
             "could not load skill-release-date.py (the extractor is unavailable): "
             "an error whose class name could not be read"),
            ("a BaseException subclass from an API lookup",
             source + "\nclass B(BaseException):\n    pass\ndel extract\ndef __getattr__(name):\n    raise B()\n",
             "lacks a usable extract "),
        ):
            with self.subTest(label):
                code, err = self.run_with_extractor(body)
                self.assertEqual(code, 3, err)
                self.assertIn(reason, err)
                self.assertIn("the extractor is unavailable", err)

    def test_incomplete_extractor_api_exits_3_naming_the_attribute(self):
        # R3: the API the gate uses is validated at load time.
        source = (MODULE_PATH.parent / "skill-release-date.py").read_text(encoding="utf-8")
        for label, tail, name in (
            ("missing extract", "del extract\n", "extract"),
            ("missing Malformed", "del Malformed\n", "Malformed"),
            ("non-callable extract", "extract = 5\n", "extract"),
            ("missing requires_release_date", "del requires_release_date\n", "requires_release_date"),
            ("missing release_day_from_published_at", "del release_day_from_published_at\n",
             "release_day_from_published_at"),
            ("Malformed not an exception class", "Malformed = \"x\"\n", "Malformed"),
            # Fix round 5: a Malformed class with a custom metaclass is refused.
            ("Malformed with a custom metaclass",
             "class _Meta(type):\n    pass\nclass Malformed(ValueError, metaclass=_Meta):\n    pass\n",
             "Malformed"),
            ("BASELINE_VERSION not a version", "BASELINE_VERSION = 14\n", "BASELINE_VERSION"),
        ):
            with self.subTest(label):
                code, err = self.run_with_extractor(source + "\n" + tail)
                self.assertEqual(code, 3, err)
                self.assertIn(f"lacks a usable {name} ", err)
                self.assertNotIn("does not exist", err)


class ExtractorApiTest(unittest.TestCase):
    """R3: the class of every reference to an attribute of the loaded
    extractor module. The gate names none directly; it passes declared names
    to release_date_call and release_date_attr, the only lookup is the one in
    release_date_attr, and every declared name is usable in the real
    extractor."""

    def setUp(self):
        self.tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))

    def test_no_direct_attribute_of_the_loaded_module(self):
        direct = [
            node.lineno for node in ast.walk(self.tree)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "RELEASE_DATE"
        ]
        self.assertEqual(direct, [])

    def test_every_routed_name_is_declared(self):
        declared = {name for name, _kind in gate.RELEASE_DATE_API}
        routed, dynamic = [], []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in (
                "release_date_call", "release_date_attr"
            ):
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    routed.append(first.value)
                else:
                    dynamic.append(ast.unparse(first))
        self.assertTrue(routed)
        self.assertLessEqual(set(routed), declared)
        # The only non-literal name is the wrapper passing its own parameter on.
        self.assertEqual(dynamic, ["name"])

    def test_the_only_lookup_on_the_module_is_in_release_date_attr(self):
        lookups = []
        for func in ast.walk(self.tree):
            if isinstance(func, ast.FunctionDef):
                for node in ast.walk(func):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                            and node.func.id in ("getattr", "hasattr", "setattr", "delattr")
                            and node.args and isinstance(node.args[0], ast.Name)
                            and node.args[0].id == "RELEASE_DATE"):
                        lookups.append(func.name)
        self.assertEqual(lookups, ["release_date_attr"])

    def test_every_declared_name_is_usable_in_the_real_extractor(self):
        for name, kind in gate.RELEASE_DATE_API:
            with self.subTest(name):
                self.assertTrue(gate._api_kind_ok(getattr(gate.RELEASE_DATE, name), kind))


if __name__ == "__main__":
    unittest.main()
