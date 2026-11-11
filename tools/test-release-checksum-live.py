#!/usr/bin/env python3
"""Tests for the live checksum gate's conditional 404 pass.

The gate must not pass unconditionally when the release the verify page names
is not published. It passes on a 404 only in the pre-tag window: the site
names the current skill version and carries the not-yet-published note, and
the tag does not exist yet; a checksum shown as published there fails. Even
then the Released line is checked with no further network call, so
a malformed line exits 3 and a line missing above the baseline fails. A
mismatched unreleased version fails, a tag with no published release is
unverifiable, and the published-release comparison and the transient-error
handling are preserved. The page a version bump builds from the zero
placeholder, which says that the checksum appears once the version is
published, passes in the pre-tag window and fails as drift once the release is
published and the gate can download and read its zip and .sha256, with a
well-formed manifest that the zip hashes to; a page in neither state
exits 3, with 1 case for each part of the
rule that holds the page to the download block tools/build-site.py renders for
it, including markup that a browser shows the same way, comments and hidden
elements, and that rule is pinned to the copy that check-release-links.py
carries. The page must also be the generator's whole render for the version
and checksum it shows: elsewhere the fixture page stands in for that render,
and WholePageTest runs the real generator on a copy of its inputs, on each
page form that its cases list. Once the release SKILL.md names is published, its
Released line (item 26) must name the UTC day of the release published_at
record, checked for the release SKILL.md names whatever version the site
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
import codecs
import contextlib
import errno
import hashlib
import importlib.util
import io
import json
import locale
import os
import py_compile
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

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

def verify_page(version: str, checksum: str) -> str:
    """A verify page laid out as tools/build-site.py writes it: the download block the generator renders for
    ``version`` and ``checksum`` (the gate's download_block), inside the elements build() writes around it
    (BLOCK_ANCESTORS)."""
    return ('<!doctype html>\n<html lang="en" class="site-cleanlanguage">\n<head><title>Verify</title></head>\n<body>\n'
            '<main id="main-content">\n<div class="wrap"><div class="doc"><h1>Verify your download</h1>\n'
            + gate.download_block(version, checksum) + '<div class="next"></div></div></div>\n</main>\n</body>\n</html>\n')


class Page:
    """A verify page in 1 state, written with format as the fixtures were: VERIFY.format(version=..., checksum=...)
    for a published checksum, PENDING.format(version=...) for the zero placeholder."""

    def __init__(self, checksum: str | None = None) -> None:
        self.checksum = checksum

    def format(self, version: str, checksum: str | None = None) -> str:
        return verify_page(version, self.checksum or checksum)


VERIFY = Page()
# site/_redirects, with the short path to the checksum file the verify page may not link in the placeholder state.
REDIRECTS = (
    f"/download https://github.com/jposluns/cleanlanguage/releases/download/v{AHEAD}/cleanlanguage-{AHEAD}.zip 302\n"
    f"/download/checksum https://github.com/jposluns/cleanlanguage/releases/download/v{AHEAD}/"
    f"cleanlanguage-{AHEAD}.zip.sha256 302\n"
)
# The verify page while site-src/release.json holds the zero placeholder, as tools/build-site.py writes it.
PENDING = Page("0" * 64)


def outside(page: str, extra: str) -> str:
    """``page`` with ``extra`` after the download block, inside main."""
    return page.replace('<div class="next">', extra + '<div class="next">', 1)


def fixture_render(version: str, checksum: str) -> bytes:
    """The fixture page for ``version`` and ``checksum``, which stands in for the generator's whole render
    (rendered_verify_page) in the tests that do not run the real generator on a copy of its inputs."""
    return verify_page(version, checksum).encode("utf-8")


# Appended to a copy of tools/build-site.py that a gate copy runs as a script (ModuleLoadTest): its verify_page()
# returns fixture-render.html beside the copy's tools folder, which stands in for the whole render.
STAND_IN_RENDER = (
    "\n\ndef verify_page(root, release=None, date=None):\n"
    "    return (root / \"fixture-render.html\").read_bytes()\n"
)


# The inputs tools/build-site.py renders the site from, as tools/test-build-site.py copies them.
GENERATOR_INPUTS = (
    "site-src", "cleanlanguage/skills/cleanlanguage/SKILL.md", "cleanlanguage/skills/cleanlanguage/references",
    "site/downloads", "site/assets/baseline", "site/_headers", "site/_redirects", "site/robots.txt", "site/sitemap.xml",
    "site/.well-known", "site/README.md", "site/images", ".baseline/pin.toml", "tools/sitemap-config.json",
    "tools/check-install-page.py",
)


def copy_generator_inputs(root: Path) -> None:
    """Copy GENERATOR_INPUTS from this repository into ``root``."""
    for relative in GENERATOR_INPUTS:
        source, target = MODULE_PATH.parent.parent / relative, root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copyfile(source, target)


def exclude_draft_home(root: Path) -> None:
    """Exclude the draft's home page from the sitemap under ``root``, as the draft branch does: tools/build-site.py
    refuses to build a staged draft without that exclusion."""
    path = root / "tools/sitemap-config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["exclude"] = [entry for entry in data["exclude"] if entry != "draft/index.html"] + ["draft/index.html"]
    path.write_text(json.dumps(data), encoding="utf-8")


def render_with(generator: Path, root: Path, version: str, checksum: str) -> bytes:
    """The whole verify page as the generator at ``generator`` renders it from ``root`` for these release values."""
    generator_spec = importlib.util.spec_from_file_location("build_site_for_fixture", generator)
    module = importlib.util.module_from_spec(generator_spec)
    generator_spec.loader.exec_module(module)
    return module.verify_page(root, {"version": version, "tag": f"v{version}", "checksum": checksum})


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

# Row 80: TIMEOUT_WRAPPER, except that the first wait of the gate for each
# child, the one CHILD_TIMEOUT_SECONDS bounds, starts only once the child has
# ended or a file named "ready" exists beside the gate copy, polled for at most
# READY_SECONDS. The fake extractor writes that file only after it has written
# every file the test reads, so a busy host can slow the child down but cannot
# make the 1 second timeout fire before the child is ready. The wait the gate
# then makes, its kill, its reap and its report are the real ones.
READY_SECONDS = 60
READY_TIMEOUT_WRAPPER = (
    "import importlib.util, os, sys, time\n"
    "spec = importlib.util.spec_from_file_location(\"gate_copy\", sys.argv[1])\n"
    "gate = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(gate)\n"
    "gate.CHILD_TIMEOUT_SECONDS = 1\n"
    "ready = os.path.join(os.path.dirname(sys.argv[1]), \"ready\")\n"
    "real_wait = gate._wait_unreaped\n"
    "seen = set()\n"
    "def wait_when_ready(proc, timeout):\n"
    "    if proc.pid not in seen:\n"
    "        seen.add(proc.pid)\n"
    f"        deadline = time.monotonic() + {READY_SECONDS}\n"
    "        while not os.path.exists(ready) and time.monotonic() < deadline:\n"
    "            if real_wait(proc, 0.05):\n"
    "                return True\n"
    "    return real_wait(proc, timeout)\n"
    "gate._wait_unreaped = wait_when_ready\n"
    "sys.exit(gate.main())\n"
)

# The source a fake extractor runs to say it is ready (see
# READY_TIMEOUT_WRAPPER), indented for the body of a function.
SAY_READY = "    (Path(__file__).resolve().parent / \"ready\").write_text(\"ready\", encoding=\"utf-8\")\n"


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


class ReverseSortedKeys(frozenset):
    """A key set of REPLY_KEYS that iterates in reverse sorted order. A report
    that lists the keys of a set without sorting them then differs from the
    sorted list under every hash seed, not only under some, so a test that pins
    the sorted list fails without the sort."""

    def __iter__(self):
        return iter(sorted(frozenset.__iter__(self), reverse=True))


def process_state(pid: int) -> str | None:
    """The State letter of process ``pid``, or None when it does not exist.
    A process reaped between the open and the read of its status file makes the
    read fail with ESRCH (ProcessLookupError), which also means it no longer
    exists."""
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except (FileNotFoundError, ProcessLookupError):
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
            gate.release_published_at, gate.release_immutable, gate.REDIRECTS,
        )
        # Row 80: a test may point the gate at a fake extractor, shorten
        # the child timeout or the reap grace, or change the output bounds;
        # each is restored after it.
        self._saved_child = (
            gate.RELEASE_DATE_TOOL, gate.CHILD_TIMEOUT_SECONDS, gate.REAP_GRACE_SECONDS,
            gate.RESULT_LIMIT, gate.ECHO_BYTES_PER_CHARACTER, gate.STDERR_LIMIT,
        )
        root = Path(self._tmp.name)
        gate.REPO_ROOT = root
        gate.VERIFY_PAGE = root / "index.html"
        gate.SKILL = root / "SKILL.md"
        gate.REDIRECTS = root / "_redirects"
        gate.REDIRECTS.write_text(REDIRECTS, encoding="utf-8")
        gate.release_status = unexpected_call
        gate.tag_status = unexpected_call
        gate.gh = unexpected_call
        gate.release_published_at = unexpected_call
        gate.release_immutable = unexpected_call
        # The fixture page stands in for the generator's whole render; WholePageTest runs the real one.
        self._saved_render = gate.rendered_verify_page
        gate.rendered_verify_page = fixture_render

    def tearDown(self):
        (gate.REPO_ROOT, gate.VERIFY_PAGE, gate.SKILL, gate.release_status,
         gate.tag_status, gate.gh, gate.release_published_at,
         gate.release_immutable, gate.REDIRECTS) = self._saved
        gate.rendered_verify_page = self._saved_render
        (gate.RELEASE_DATE_TOOL, gate.CHILD_TIMEOUT_SECONDS, gate.REAP_GRACE_SECONDS,
         gate.RESULT_LIMIT, gate.ECHO_BYTES_PER_CHARACTER, gate.STDERR_LIMIT) = self._saved_child
        self._tmp.cleanup()

    @contextlib.contextmanager
    def timeout_when_ready(self, ready: Path):
        """Within the block, the first wait of the gate for each child, the one
        CHILD_TIMEOUT_SECONDS bounds, starts only once the child has ended or
        ``ready`` exists, polled for at most READY_SECONDS, as
        READY_TIMEOUT_WRAPPER does for a gate in a process of its own; every
        later wait, and the kill, the reap and the report, are the real ones. A
        busy host can then slow a child down without a short timeout firing
        before the child has reached the state a test needs."""
        real_wait = gate._wait_unreaped
        seen = set()
        # The monotonic time at which the gate first found ``ready``, so a
        # test can bound the time the gate takes from then on.
        state = {}

        def wait_when_ready(proc, timeout):
            if proc.pid not in seen:
                seen.add(proc.pid)
                deadline = time.monotonic() + READY_SECONDS
                while not ready.exists() and time.monotonic() < deadline:
                    if real_wait(proc, 0.05):
                        return True
                if ready.exists():
                    state.setdefault("ready_at", time.monotonic())
            return real_wait(proc, timeout)

        gate._wait_unreaped = wait_when_ready
        try:
            yield state
        finally:
            gate._wait_unreaped = real_wait

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
        # The manifest ends in a newline, as the one sha256sum writes in
        # tools/release-package.sh.
        (target / f"cleanlanguage-{version}.zip.sha256").write_text(
            f"{ZIP_SUM}  cleanlanguage-{version}.zip\n", encoding="utf-8"
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

    # --- The Released line (item 26) against the release record --------------

    def test_released_date_matching_published_day_passes(self):
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-15T23:59:59Z")
        code, out = self.main_output()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.asked, [f"v{AHEAD}"])
        # A correctly dated published release prints no missing-line report and
        # no inconsistency.
        self.assertIn(f"matches the publication day of release v{AHEAD}", out)
        self.assertNotIn("has no Released: line", out)
        self.assertNotIn("inconsistency", out)

    def test_released_date_differing_from_published_day_fails(self):
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-16T00:00:01Z")
        self.assertEqual(gate.main(), 1)

    def test_mismatch_message_states_both_values_and_defers_to_the_readback(self):
        # Never tell the maintainer to copy a record that may have moved.
        self.fixtures(AHEAD, ZIP_SUM, AHEAD, "Released: 2026-11-15  ")
        self.published("2026-11-16T00:00:01Z")
        code, out = self.main_output()
        self.assertEqual(code, 1)
        self.assertIn("says Released: 2026-11-15", out)
        self.assertIn("published_at reads 2026-11-16T00:00:01Z (UTC day 2026-11-16)", out)
        self.assertIn("first-publication readback", out)
        self.assertNotIn("Correct the line to match the release record", out)
        # The release is immutable, so the remedy is a corrective new version;
        # no republish or asset replacement is offered. Row 74: the wording
        # matches the release workflow, which says corrective new version.
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
        # Both checks run and both are reported, and the more severe code wins.
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
        # A dated 1.0.14 is compared like any other dated release.
        self.fixtures(CURRENT, ZIP_SUM, CURRENT, "Released: 2026-11-15  ")
        self.published("2026-11-15T09:30:00Z")
        self.assertEqual(gate.main(), 0)
        self.assertEqual(self.asked, [f"v{CURRENT}"])

    def test_dated_baseline_mismatched_fails(self):
        self.fixtures(CURRENT, ZIP_SUM, CURRENT, "Released: 2026-11-15  ")
        self.published("2026-11-16T09:30:00Z")
        self.assertEqual(gate.main(), 1)

    def test_release_that_is_not_immutable_is_unverifiable(self):
        # The date comparison relies on an immutable release record.
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

    def test_readers_remove_only_one_final_newline(self):
        # Each record reader returns what gh printed with only 1 final newline
        # removed, so a second newline, a carriage return, or a blank on either
        # side stays in the value and reaches the check that refuses it.
        for name, reader, field in (
            ("release_published_at", self._saved[6], "2026-11-15T09:30:00Z"),
            ("release_immutable", self._saved[7], "true"),
        ):
            for printed, expected in (
                (field + "\n", field), (field, field), (field + "\n\n", field + "\n"), (field + "\r\n", field + "\r"),
                (" " + field + "\n", " " + field), (field + " \n", field + " "), (field + "\t\n", field + "\t"),
            ):
                with self.subTest(name, printed=printed):
                    gate.gh = lambda *args, check=True, out=printed: subprocess.CompletedProcess(args, 0, out, "")
                    self.assertEqual(reader("v1.0.15"), expected)

    def test_the_real_gh_wrapper_fails_closed_on_output_that_does_not_decode(self):
        # The real gh wrapper decodes what gh prints strictly, so a byte that
        # is not UTF-8 is unverifiable (exit 2) in every reader, never replaced
        # or read in another encoding. The wrapper decodes with the locale
        # encoding, which this test requires to be UTF-8.
        self.assertEqual(codecs.lookup(locale.getpreferredencoding(False)).name, "utf-8")
        bindir = Path(self._tmp.name) / "undecodable-gh"
        bindir.mkdir()
        fake = bindir / "gh"
        fake.write_text("#!/bin/sh\nprintf 'HTTP/2.0 200 OK\\n\\377\\n'\n", encoding="ascii")
        fake.chmod(0o755)
        readers = (
            ("release_immutable", self._saved[7], "the immutable field of release v1.0.15"),
            ("release_published_at", self._saved[6], "published_at for release v1.0.15"),
            ("release_status", self._saved[3], "the release status for v1.0.15"),
            ("tag_status", self._saved[4], "the tag status for v1.0.15"),
        )
        for name, reader, what in readers:
            with self.subTest(name):
                gate.gh = self._saved[5]
                saved_path = os.environ.get("PATH")
                os.environ["PATH"] = str(bindir)
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
                lines = err.getvalue().splitlines()
                self.assertEqual(len(lines), 1, err.getvalue())
                self.assertTrue(
                    lines[0].startswith(f"{self.CV}could not read {what}: UnicodeDecodeError("), err.getvalue()
                )
                self.assertEqual(out.getvalue(), "")

    def test_undated_release_reads_no_record_field(self):
        # An undated release at or below the baseline reads neither field.
        self.fixtures(CURRENT, ZIP_SUM, CURRENT)
        self.published("2026-11-15T09:30:00Z", immutable="false")
        self.assertEqual(gate.main(), 0)
        self.assertEqual((self.asked, self.immutable_asked), ([], []))

    def test_baseline_rule_is_numeric_for_an_undated_published_release(self):
        # The same rule the extractor applies everywhere.
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

    # --- The release SKILL.md names is checked on its own terms -------------

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
        # As on the same-version path, a tag with no release is a deleted or
        # failed release, never a release not yet published.
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
        # The line and the baseline rule are read first, so an undated release
        # at or below the baseline makes no network call for the date check.
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
        # A present Released line is never reported as missing beside the
        # unverifiable state.
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
        # An OSError other than a missing gh, or gh output that does not
        # decode, is unverifiable (exit 2), never a traceback read as drift.
        # The report is pinned exactly, including the OSError or UnicodeError
        # branch of api_status behind release_status and tag_status.
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
        # A gh that is absent is unverifiable (exit 2) in every reader,
        # including the FileNotFoundError branch of api_status behind
        # release_status and tag_status, both through a gh that raises
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
        # The date check stops with exit 2 and the checksum drift is still
        # reported.
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
            "REPO_ROOT", "VERIFY_PAGE", "SKILL", "REDIRECTS", "GENERATOR", "release_status", "tag_status", "gh",
            "release_published_at", "release_immutable", "rendered_verify_page",
        ):
            setattr(fresh, name, getattr(gate, name))
        return fresh

    def test_extractor_load_failure_does_not_hide_checksum_drift(self):
        # The extractor is probed inside main, so a failure to run it
        # contributes exit 3 while the checksum comparison still runs and
        # reports the drift. Row 80: each reason is the child outcome, with the
        # child stderr relayed.
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
        # The load failure contributes exit 3 on every path, including one that
        # needs no date check.
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
        # The site names an unreleased version that is not the current one, so
        # the checksum comparison reports an inconsistency; that does not hide
        # the date check of the release SKILL.md names, which is still checked
        # on its own terms, and the more severe code wins.
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
        # A failed download or a malformed manifest stops only the checksum
        # comparison (exit 2), so an unusable download does not hide the date
        # check: it still runs and reports, and the more severe code wins.
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
        # An unexpected failure of the extractor is unavailable (exit 3), never
        # a drift verdict (exit 1). Row 80: the child exits 6 and its stderr is
        # relayed.
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
        # unavailable (exit 3), never a pass (0) or a drift (1). That holds for
        # 2 and 3 too, the codes release_date_code and main absorb as could not
        # verify. Row 80: the child ends with that code and an empty stdout, so
        # 0 and None print no result and the others exit nonzero.
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
        # With a Released line present, the baseline rule is not asked, so no
        # extractor code runs for it. Row 80: a call would run the failing
        # function in a child and exit 3.
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
        # A release status for the version the verify page names that cannot be
        # read (2), beside a SKILL.md with no Version line (3), exits with the
        # more severe 3 and its report.
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
        # Download output that does not decode stops only the checksum
        # comparison (exit 2) with its report, never an uncaught
        # UnicodeDecodeError read as drift; the date check still runs and
        # reports.
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
        # A function missing at call time is unavailable (exit 3), never an
        # uncaught error (exit 1, drift). Row 80: the child fails with a
        # NameError (exit 6). A missing Malformed fails only where a verdict is
        # raised, so its row reads an unusable published_at.
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
        # Before the tag, the only page the window passes is the note.
        self.fixtures(AHEAD, OTHER_SUM, AHEAD, "Released: 2026-11-15")
        gate.VERIFY_PAGE.write_text(PENDING.format(version=AHEAD), encoding="utf-8")
        gate.release_status = lambda tag: 404
        gate.tag_status = lambda tag: 404
        self.assertEqual(gate.main(), 0)

    def test_a_checksum_shown_as_published_before_the_tag_fails(self):
        # An honest mistake at the bump, a well-formed checksum passed to
        # tools/set-release-links.py for a version with no release and no tag, fails (exit 1), the Released line still
        # checked and the more severe code winning; nothing beyond the release and the tag is read over the network. A
        # mistyped placeholder exits 3 before this, as the generator refuses to render it (WholePageTest).
        for label, checksum, released, expected in (
            ("the previous version's digest", ZIP_SUM, "Released: 2026-11-15", 1),
            ("a locally built digest", OTHER_SUM, "Released: 2026-11-15", 1),
            ("a locally built digest and a missing Released line", OTHER_SUM, None, 1),
            ("a locally built digest and a malformed Released line", OTHER_SUM, "Released: soon", 3),
        ):
            with self.subTest(label):
                self.fixtures(AHEAD, checksum, AHEAD, released)
                self.published(None, statuses={f"v{AHEAD}": 404})
                gate.gh = unexpected_call
                code, out, err = self.main_reports()
                self.assertEqual(code, expected, (out, err))
                self.assertEqual((self.probed, self.tag_probed), ([f"v{AHEAD}"], [f"v{AHEAD}"]))
                self.assertIn("Release checksum inconsistency found:\n"
                              f"  - the verify page shows {checksum} as the published checksum for version {AHEAD}\n"
                              f"  - release v{AHEAD} is not published yet and its tag does not exist, so no checksum for "
                              f"{AHEAD} is published\n", out)
                self.assertIn(f"tools/set-release-links.py for {AHEAD} with the zero placeholder checksum", out)
                self.assertNotIn("Nothing to reconcile", out)
                if released is None:
                    self.assertIn(f"names {AHEAD}, above the undated baseline {CURRENT}, but has no Released: line", out)

    def test_not_yet_published_page_passes_in_the_pre_tag_window(self):
        # The page a version bump builds from the zero placeholder names its version in the note.
        self.fixtures(AHEAD, OTHER_SUM, AHEAD, "Released: 2026-11-15")
        gate.VERIFY_PAGE.write_text(PENDING.format(version=AHEAD), encoding="utf-8")
        self.published(None, statuses={f"v{AHEAD}": 404})
        gate.gh = unexpected_call
        code, out, err = self.main_reports()
        self.assertEqual(code, 0, (out, err))
        self.assertEqual((self.probed, self.tag_probed), ([f"v{AHEAD}"], [f"v{AHEAD}"]))

    def test_not_yet_published_page_beside_a_published_release_fails(self):
        # The site still holds the placeholder once the release is live: drift, exit 1 here, where no other check
        # fails with a higher code.
        self.fixtures(CURRENT, ZIP_SUM, CURRENT)
        gate.VERIFY_PAGE.write_text(PENDING.format(version=CURRENT), encoding="utf-8")
        gate.release_status = lambda tag: 200
        gate.gh = self.fake_download
        code, out, err = self.main_reports()
        self.assertEqual(code, 1, (out, err))
        self.assertIn(f"  - the verify page says the checksum for version {CURRENT} is not yet published\n", out)
        self.assertIn(f"  - the published cleanlanguage-{CURRENT}.zip is {ZIP_SUM}\n", out)

    def test_a_page_in_neither_state_exits_3(self):
        # The zero placeholder shown as the published checksum, and a page with the note that breaks the rule
        # (download_block_problems), are refused before any release is read: 1 case for each part of the rule.
        note = (f"<p>The checksum for version {CURRENT} appears here once that version is published; compare the "
                "checksum of your file with it then.</p>\n")
        mixed = "the verify page carries the not-yet-published note, but "
        url = f"https://github.com/jposluns/cleanlanguage/releases/download/v{CURRENT}/cleanlanguage-{CURRENT}.zip"
        pending = PENDING.format(version=CURRENT)
        element = "carries the checksum element's id outside the download block"
        sum_class = "carries the class sum outside the download block"
        noted = "carries the not-yet-published note outside the download block"
        worded = 'says "published checksum" outside the download block'
        hexadecimal = "carries a 64 digit hexadecimal value outside the download block"
        linked = "links a .sha256 checksum file outside the download block"
        rejects = "has a step that tells the reader not to install the file outside the download block"
        block = "does not carry the download block that tools/build-site.py writes for this state exactly once, byte for byte"
        placed = "does not carry the download block where tools/build-site.py writes it"
        start, end = pending.index('<p class="lbl blk">Step 1</p>'), pending.index('<div class="next">')
        for label, page, report in (
            ("the placeholder as the published checksum",
             VERIFY.format(version=CURRENT, checksum=ZIP_SUM).replace(ZIP_SUM, "0" * 64),
             "the verify page shows the zero placeholder as the published checksum"),
            ("the note beside a published checksum", outside(VERIFY.format(version=CURRENT, checksum=ZIP_SUM), note),
             mixed + block + " (found 0)"),
            # Outside the block, the page
            # is read as parsed markup and as written, comments and hidden elements included.
            ("the note beside the checksum element with its attributes in the other order",
             outside(pending, f'<code id="published-checksum" class="sum">{ZIP_SUM}</code>\n'),
             mixed + "; ".join((element, sum_class, hexadecimal))),
            ("the note beside the checksum element with another attribute",
             outside(pending, "<code class='x' hidden id=published-checksum></code>\n"), mixed + element),
            ("the note beside 64 zeros in an element of the class sum without the id",
             outside(pending, f'<code class="sum">{"0" * 64}</code>\n'), mixed + "; ".join((sum_class, hexadecimal))),
            ("the note beside a link through the checksum redirect", outside(pending, '<a href="/download/checksum">f</a>\n'),
             mixed + linked),
            ("the note beside a link through the checksum redirect with a doubled slash",
             outside(pending, '<a href="/download//checksum">f</a>\n'), mixed + linked),
            ("the note beside a relative link through the checksum redirect",
             outside(pending, '<a href="../download/Checksum/">file</a>\n'), mixed + linked),
            ("the note beside a link to the checksum file with an encoded dot",
             outside(pending, f'<a href="{url}%2Esha256">file</a>\n'), mixed + linked),
            ("the note beside published checksum wording split by markup",
             outside(pending, "<p>The published <b>checksum</b> is below.</p>\n"), mixed + worded),
            ("the note beside a step that rejects the download split by markup",
             outside(pending, "<p>If they differ, do <em>not</em> install the file.</p>\n"), mixed + rejects),
            ("the note beside the checksum sentence alone",
             outside(pending, f"<p>The published checksum for version {CURRENT} is:</p>\n"), mixed + worded),
            ("the note beside a link to the checksum file", outside(pending, f'<a href="{url}.sha256">checksum file</a>\n'),
             mixed + linked),
            ("the note beside a step that rejects the download",
             outside(pending, "<p>Compare the 2 values. If they still differ, do not install the file.</p>\n"),
             mixed + rejects),
            ("the note beside 64 hexadecimal digits in a comment", outside(pending, f"<!-- {ZIP_SUM} -->\n"),
             mixed + hexadecimal),
            ("2 notes", outside(pending, note), mixed + noted),
            ("a second note for another version", outside(pending, note.replace(CURRENT, BOGUS)), mixed + noted),
            ("the note only in a comment", pending.replace(note.strip(), f"<!-- {note.strip()} -->"),
             mixed + block + " (found 0)"),
            ("the block hidden", pending[:start] + "<div hidden>" + pending[start:end] + "</div>" + pending[end:],
             mixed + placed),
            ("the block in a template", pending[:start] + "<template>" + pending[start:end] + "</template>" + pending[end:],
             mixed + placed),
            ("a stray body start tag with a hidden attribute", outside(pending, "<body hidden>"), mixed + placed),
            ("the block twice", outside(pending, pending[start:end]), mixed + block + " (found 2)"),
            ("a stray html start tag", outside(pending, "<html hidden>"), mixed + placed),
            ("the block in a self-closed div, which a browser leaves open",
             pending[:start] + "<div hidden/>" + pending[start:], mixed + placed),
            ("the note beside the class sum in a comment", outside(pending, '<!-- <i class="x sum"></i> -->'),
             mixed + sum_class),
            ("the note beside the checksum element's id in a script",
             outside(pending, '<script>f("published-checksum")</script>'), mixed + element),
            ("the note beside the checksum element's id as a character reference",
             outside(pending, "<i id=published&#45;checksum></i>"), mixed + element),
            ("the note beside a link to the checksum file in a script", outside(pending, '<script>f("/x.SHA256")</script>'),
             mixed + linked),
            ("the note beside a step that rejects the download in a contraction",
             outside(pending, "<p>If they differ, don&#8217;t install the file.</p>"), mixed + rejects),
        ):
            with self.subTest(label):
                self.assertNotEqual(page, pending)
                gate.VERIFY_PAGE.write_text(page, encoding="utf-8")
                gate.SKILL.write_text(f"Version: {CURRENT}\n", encoding="utf-8")
                gate.release_status = unexpected_call
                self.assertEqual(self.main_reports(), (3, "", f"check-release-checksum-live: {report}\n"))

    def test_a_published_page_without_the_rest_of_its_state_exits_3(self):
        # A page with a real checksum
        # carries the download block the generator writes for it, unchanged and where the generator writes it,
        # and nothing outside it that belongs to either state, or it is refused before any release is read.
        page = VERIFY.format(version=CURRENT, checksum=ZIP_SUM)
        lead = "<p>Download the skill. The published checksum is shown under the link.</p>"
        link_start = page.index(f'<a href="https://github.com/jposluns/cleanlanguage/releases/download/v{CURRENT}/'
                                f'cleanlanguage-{CURRENT}.zip.sha256"')
        link = page[link_start:page.index("</a>", link_start) + 4]
        start, end = page.index('<p class="lbl blk">Step 1</p>'), page.index('<div class="next">')
        step = page[page.index('<p class="lbl blk">Step 3</p>'):end]
        code = f'<code class="sum" id="published-checksum">{ZIP_SUM}</code>'
        shown = "the verify page shows a published checksum, but "
        block = ("does not carry the download block that tools/build-site.py writes for this state exactly once, "
                 "byte for byte (found 0)")
        placed = "does not carry the download block where tools/build-site.py writes it"
        for label, changed, report in (
            ("no step 1 lead", page.replace(lead, "<p>Download the skill.</p>"), block),
            ("the step 1 lead in a comment only", page.replace(lead, f"<p>Download the skill.<!-- {lead} --></p>"), block),
            ("the step 1 lead hidden", page.replace(lead, f"<div hidden>{lead}</div>"), block),
            ("no link to the checksum file", page.replace(link, "published checksum file"), block),
            ("the link to the checksum file hidden", page.replace(link, f"<span hidden>{link}</span>"), block),
            ("a link to the checksum file of another version", page.replace(link, link.replace(CURRENT, BOGUS)), block),
            ("no step 3", page.replace(step, ""), block),
            ("step 3 hidden", page.replace(step, f"<div hidden>{step}</div>"), block),
            ("a step 3 that rejects a matching value", page.replace("still differ after", "match after"), block),
            ("step 3, the link and the step 1 lead removed",
             page.replace(lead, "<p>Download the skill.</p>").replace(link, "published checksum file").replace(step, ""),
             block),
            ("the checksum element in a comment beside a visible one",
             page.replace(code, f'<!-- {code} --><code id="published-checksum" class="sum">{OTHER_SUM}</code>'), block),
            ("a second, wrong checksum element beside the real one",
             page.replace(code, code + f'<code class="sum" id="published-checksum">{OTHER_SUM}</code>'), block),
            ("a second, wrong checksum element after the block",
             outside(page, f'<code class="sum" id="published-checksum">{OTHER_SUM}</code>'),
             "carries the checksum element's id outside the download block; carries the class sum outside the "
             "download block; carries a 64 digit hexadecimal value outside the download block"),
            ("the note split by markup after the block",
             outside(page, "<p>It appears <b>here</b> once that version is published.</p>"),
             "carries the not-yet-published note outside the download block"),
            ("the whole block hidden", page[:start] + "<div hidden>" + page[start:end] + "</div>" + page[end:], placed),
            ("the whole block in a comment", page[:start] + "<!--" + page[start:end] + "-->" + page[end:], placed),
            # An end tag does not close an element across a template or a
            # table, and a second checksum in groups counts.
            ("a template that ends the doc div around the block",
             page[:start] + '<template></div><div class="doc">' + page[start:end] + "</div></template>" + page[end:],
             placed),
            ("a details element misnested in a table before the block",
             page[:start] + "<details><table></details>" + page[start:], placed),
            ("a second checksum in groups of 8 after the block",
             outside(page, "<p>" + " ".join(OTHER_SUM[i:i + 8] for i in range(0, 64, 8)) + "</p>"),
             "carries a 64 digit hexadecimal value outside the download block"),
            ("a second checksum in groups split by hyphens after the block",
             outside(page, "<p>" + "-".join(ZIP_SUM[i:i + 4] for i in range(0, 64, 4)) + "</p>"),
             "carries a 64 digit hexadecimal value outside the download block"),
        ):
            with self.subTest(label):
                self.assertNotEqual(changed, page)
                gate.VERIFY_PAGE.write_text(changed, encoding="utf-8")
                gate.SKILL.write_text(f"Version: {CURRENT}\n", encoding="utf-8")
                gate.release_status = unexpected_call
                self.assertEqual(self.main_reports(), (3, "", f"check-release-checksum-live: {shown}{report}\n"))

    def test_prose_outside_the_block_is_a_stated_residual(self):
        # The rule does not read the meaning of prose, so a contradicting step 3
        # outside the block passes it here; tools/check-release-links.py refuses that page by whole-page equality.
        page = outside(VERIFY.format(version=CURRENT, checksum=ZIP_SUM),
                       "<p>Correction to step 3: if the two values match, delete the file.</p>")
        redirects = gate.REDIRECTS.read_text(encoding="utf-8")
        self.assertEqual(gate.download_block_problems(page, gate.download_block(CURRENT, ZIP_SUM), redirects), [])

    def test_each_state_reads_site_redirects(self):
        # The paths to the checksum file come from site/_redirects, a required file in either state.
        for label, page in (("placeholder", PENDING.format(version=CURRENT)),
                            ("published", VERIFY.format(version=CURRENT, checksum=ZIP_SUM))):
            with self.subTest(label):
                gate.VERIFY_PAGE.write_text(page, encoding="utf-8")
                gate.SKILL.write_text(f"Version: {CURRENT}\n", encoding="utf-8")
                gate.release_status = unexpected_call
                if gate.REDIRECTS.exists():
                    gate.REDIRECTS.unlink()
                self.assertEqual(self.main_reports(), (3, "", "check-release-checksum-live: _redirects does not exist\n"))

    def test_a_generator_that_cannot_render_the_block_exits_3(self):
        gate.VERIFY_PAGE.write_text(VERIFY.format(version=CURRENT, checksum=ZIP_SUM), encoding="utf-8")
        gate.SKILL.write_text(f"Version: {CURRENT}\n", encoding="utf-8")
        gate.release_status = unexpected_call
        saved = gate.GENERATOR
        missing = Path(self._tmp.name) / "build-site.py"
        gate.GENERATOR = missing
        try:
            code, out, err = self.main_reports()
        finally:
            gate.GENERATOR = saved
        self.assertEqual((code, out), (3, ""))
        # The generator is missing, and the refusal names the exception's type and the missing file's path.
        self.assertIn("check-release-checksum-live: tools/build-site.py could not render the verify page's download "
                      f"block: FileNotFoundError: [Errno 2] No such file or directory: '{missing}'\n", err)

    def pre_tag_reports(self, version, released=None):
        """Run the gate in the pre-tag window for ``version``, asserting the
        release and the tag are each probed once and nothing else is read
        over the network; returns (exit code, stdout, stderr). The page is the
        note, the only page the window passes."""
        self.fixtures(version, OTHER_SUM, version, released)
        gate.VERIFY_PAGE.write_text(PENDING.format(version=version), encoding="utf-8")
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
        # The pre-tag window says there is nothing to reconcile only when the
        # gate passes, never beside a Released line missing above the baseline
        # (exit 1) or a malformed line (exit 3).
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
        # A probe that fails in main, beside later calls that succeed, still
        # ends the gate with 3, so the window does not say there is nothing to
        # reconcile. Row 80: the probe is the first child, and its failure is
        # reported once.
        self.fixtures(AHEAD, OTHER_SUM, AHEAD, "Released: 2026-11-15  ")
        gate.VERIFY_PAGE.write_text(PENDING.format(version=AHEAD), encoding="utf-8")
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
        # main combines the probe result with the check result through max. The
        # probe result is 0 or 3 and a drift or date mismatch verdict is 1, so
        # a failed probe (3) wins over the verdict, and a clean probe (0)
        # leaves the verdict (1). Each later call runs a child of its own, so
        # the verdict is still reached and reported. This kills code = code,
        # code = load_code and code = min(load_code, code) at the combining
        # line of main.
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

    def test_a_status_is_three_ascii_digits_after_the_protocol(self):
        # A status is read only from a line that starts with "HTTP/" and a
        # version of digits and dots, then 1 space and 3 ASCII digits that end
        # the line or are followed by a space; the last such line wins. Any
        # other line is no status, so a gh read with no such line is
        # unverifiable.
        for stdout, status in (
            ("HTTP/2.0 404 Not Found\n", 404), ("HTTP/2 404", 404), ("HTTP/1.1 200 OK\nX-Note: HTTP/1.1 500\n", 200),
            ("HTTP/2.0 302 Found\nHTTP/2.0 404 Not Found\n", 404),
        ):
            with self.subTest(stdout):
                gate.gh = lambda *args, check=True, out=stdout: subprocess.CompletedProcess(args, 0, out, "")
                self.assertEqual(gate.api_status("repos/x/y", "the status"), status)
        for stdout in (
            "HTTP/2 \u0664\u0660\u0664\n", "HTTP/2 4\u0660\u0664\n", "HTTP/2 4040\n", "HTTP/2 40\n", "HTTP/2 404x\n",
            "HTTP/2 404\tNot Found\n", "http/2 404\n", " HTTP/2 404\n", "X-Note: HTTP/1.1 404\n", "HTTP/ 404\n",
            "HTTP/two 404\n", "HTTP/\u0662 404\n", "HTTP/2  404\n", "HTTP/2\t404\n", "HTTP2 404\n",
        ):
            with self.subTest(stdout):
                gate.gh = lambda *args, check=True, out=stdout: subprocess.CompletedProcess(args, 0, out, "")
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as stop:
                    gate.api_status("repos/x/y", "the status")
                self.assertEqual((stop.exception.code, err.getvalue()),
                                 (2, self.CV + "could not read the status (gh exit 0)\n"))

    def test_every_part_of_the_skill_version_patterns_is_pinned(self):
        # The version line is the first line that starts with "Version:", and
        # it is a bare X.Y.Z of ASCII digits with any run of spaces and tabs,
        # none included, after the colon and after the version; anything else
        # exits 3 with the exact report.
        for text, version in (
            ("Version:1.0.14\n", "1.0.14"), ("Version:\t1.0.14\n", "1.0.14"), ("Version: 1.0.14\n", "1.0.14"),
            ("Version: \t 1.0.14 \t \n", "1.0.14"), ("Version: 1234.567.89\n", "1234.567.89"),
            ("# Title\n\nVersion: 1.0.14\n", "1.0.14"), ("Versioning notes\nVersion: 1.0.14\n", "1.0.14"),
            ("See Version: 9.9.9\nVersion: 1.0.14\n", "1.0.14"), ("version: 9.9.9\nVersion: 1.0.14\n", "1.0.14"),
        ):
            with self.subTest(text):
                gate.SKILL.write_text(text, encoding="utf-8")
                self.assertEqual(gate.skill_version(), version)
        not_bare = (
            "check-release-checksum-live: the first 'Version:' line in "
            "cleanlanguage/skills/cleanlanguage/SKILL.md is not a bare X.Y.Z version\n"
        )
        for text in (
            "Version:\nVersion: 1.0.14\n", "Version: \u0661.0.14\n", "Version: 1.\u0660.14\n",
            "Version: 1.0.\u0661\u0664\n", "Version:\u00a01.0.14\n", "Version: 1.0.14\u00a0\n", "Version:\x0c1.0.14\n",
            "Version: 1.0.14\x0b\n", "Version: 1x0.14\n", "Version: 1.0x14\n", "Version: 1..14\n", "Version: .0.14\n",
            "Version: 1.0.\n", "Version: 1.0.14 x\n", "Version: 1.0.14.1\n",
        ):
            with self.subTest(text):
                gate.SKILL.write_text(text, encoding="utf-8")
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as stop:
                    gate.skill_version()
                self.assertEqual((stop.exception.code, err.getvalue()), (3, not_bare))

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

    # --- No early exit hides the Released line, and every required read fails
    # closed ------------------------------------------------------------------

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
        # An existing tag, an unexpected tag status, or one that cannot be read
        # stops only the release verification (exit 2); the Released line is
        # still checked offline and the more severe code wins, so a malformed
        # line (exit 3) is not hidden.
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
        # A release status for the version the site names that cannot be read
        # stops only the checksum comparison (exit 2); for the same version the
        # Released line is still checked offline, with no further probe. A
        # malformed line is read before any probe of a newer release SKILL.md
        # names, so it exits 3 with no further probe either; the probe of a
        # newer release is pinned in the next test (row 62).
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
        # Row 62: when the release status of the version the site names cannot
        # be read and SKILL.md names a newer version, that newer release was
        # never probed, so its state is not unknown: the release-date check
        # probes it on its own terms, as the unexpected-status path does, and a
        # wrong date on it is reported. The checksum comparison still cannot
        # run, so the exit stays at least 2.
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
        # Inside the date check, an unverifiable state of the release SKILL.md
        # names keeps exit 2 but still reports a Released line missing above
        # the baseline.
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
        # A verify page that cannot be read or decoded is a required file that
        # cannot be read (exit 3), never an uncaught traceback (exit 1, drift),
        # and nothing is read over the network.
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
        # The read failure and the extractor load failure are both reported,
        # and the most severe code (3) is kept.
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
        # A downloaded zip that cannot be read stops only the checksum
        # comparison (exit 2), never an uncaught traceback read as drift; the
        # release-date check still runs and reports.
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


    # --- No early return hides a more severe result, and a required file is
    # reported by its real stat error -----------------------------------------

    def test_missing_released_line_does_not_hide_an_immutable_failure(self):
        # On the published path a Released line missing above the baseline
        # (exit 1) does not hide an immutable field that is not exactly true,
        # or cannot be read (exit 2): both are reported, the more severe 2
        # wins, and published_at is not read, since there is no line to compare
        # it with.
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
        # With an immutable release the missing line still exits 1.
        self.fixtures(AHEAD, ZIP_SUM, AHEAD)
        self.published("2026-11-15T09:30:00Z")
        code, out, err = self.main_reports()
        self.assertEqual(code, 1, (out, err))
        self.assertIn("but has no Released: line", out)
        self.assertEqual(self.immutable_asked, [f"v{AHEAD}"])
        self.assertEqual(self.asked, [])

    @unittest.skipIf(os.geteuid() == 0, "root searches a directory whatever its mode")
    def test_required_file_behind_an_unsearchable_directory_is_unreadable_not_missing(self):
        # A verify page or SKILL.md that cannot be reached because its
        # directory cannot be searched is reported by its real stat error (exit
        # 3), never as a file that does not exist.
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
        # skill_released and skill_version each check SKILL.md.
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
        # An absent required file still reads as missing; a directory in its
        # place is not a regular file.
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
        # The downloaded assets are reported by their real stat error (exit 2),
        # never as missing from the release.
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
        # Row 80 (2.4): each rule of the contract is checked, by exact type and
        # exact key set, and a breach exits 3 naming the rule. The key sets
        # iterate in reverse sorted order here, so the sorted key list of each
        # report is pinned under every hash seed.
        self.addCleanup(setattr, gate, "REPLY_KEYS", gate.REPLY_KEYS)
        gate.REPLY_KEYS = {outcome: ReverseSortedKeys(keys) for outcome, keys in gate.REPLY_KEYS.items()}
        self.assertEqual(list(gate.REPLY_KEYS["value"]), ["value", "outcome", "op"])
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
            ("an outcome that is a list", "extract", {"op": "extract", "outcome": ["value"]},
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
            ("a day with a three-digit year", "extract", {"op": "extract", "outcome": "value", "value": day[1:]},
             day_form),
            ("a day with a five-digit year", "extract", {"op": "extract", "outcome": "value", "value": "2" + day},
             day_form),
            # Each part of the day form is its exact number of ASCII digits,
            # joined by hyphens.
            *((f"the day {value!r}", "extract", {"op": "extract", "outcome": "value", "value": value}, day_form)
              for value in (
                  "\u0662\u0660\u0662\u0666-11-15", "2026-\u0661\u0661-15", "2026-11-\u0661\u0665", "20261115",
                  "2026-1115", "202611-15", "2026-1-15", "2026-11-5", "2026-011-15", "2026-11-015", "2026/11/15",
                  "2026.11.15", "2026.11-15", "2026-11.15", "2026/11-15", "2026-11/15", " 2026-11-15",
              )),
            ("a null day", "extract", {"op": "extract", "outcome": "value", "value": None}, day_form),
            ("a published day not in the day form", "release_day_from_published_at",
             {"op": "release_day_from_published_at", "outcome": "value", "value": "2026-11-1x"}, day_form),
            ("a published day with trailing text", "release_day_from_published_at",
             {"op": "release_day_from_published_at", "outcome": "value", "value": day + "x"}, day_form),
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
            ("baseline with trailing text", "baseline", {"op": "baseline", "outcome": "value", "value": "1.0.14x"},
             version),
            ("baseline with a trailing newline", "baseline",
             {"op": "baseline", "outcome": "value", "value": "1.0.14\n"}, version),
            # Each part of the baseline is 1 or more ASCII digits, joined by
            # dots.
            *((f"baseline {value!r}", "baseline", {"op": "baseline", "outcome": "value", "value": value}, version)
              for value in (
                  "\u0661.0.14", "1.\u0660.14", "1.0.\u0661\u0664", "1x0.14", "1.0x14", "1..14", ".0.14", "1.0.",
                  " 1.0.14", "1.0.14.1",
              )),
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
        # Row 100: a reply that reaches the output cap, 65538 bytes here,
        # stops there and is refused naming the cap; what the child then
        # prints about its refused write is relayed after it.
        valid = b'{"op": "baseline", "outcome": "value", "value": "1.0.14"}'
        padded = valid + b" " * (gate.RESULT_LIMIT - len(valid))
        self.assertEqual(gate.RESULT_LIMIT, 65536)
        for label, output, expected in (
            ("70000 bytes of spaces before a valid reply", b" " * 70000 + valid, "capped"),
            ("a valid reply one byte over the limit", padded + b" ", None),
            ("a valid reply of exactly the limit", padded, ("value", CURRENT)),
        ):
            with self.subTest(label):
                self.fake_extractor(forging({"baseline": output}))
                result, err = self.call_reports("baseline")
                if expected == "capped":
                    self.assertEqual(result, ("exit", 3), err)
                    self.assertTrue(err.startswith(self.unavailable(
                        "wrote stdout up to the output cap of 65538 bytes", "baseline") + "; it printed: "), err)
                elif expected is None:
                    self.assertEqual(result, ("exit", 3), err)
                    self.assertEqual(err.splitlines(), [self.unavailable("printed more than 65536 bytes", "baseline")])
                else:
                    self.assertEqual((result, err), (expected, ""))

    def test_a_valid_reply_with_a_nonzero_exit_exits_3(self):
        # Row 80: a reply counts only when the child exits 0.
        valid = b'{"op": "baseline", "outcome": "value", "value": "1.0.14"}\n'
        # The codes on each side of the internal-error code are plain exits.
        for exit_code, reason in (
            (1, "exited 1"), (2, "exited 2"), (5, "exited 5"), (6, "failed unexpectedly (internal error)"),
            (7, "exited 7"),
        ):
            with self.subTest(exit_code=exit_code):
                self.fake_extractor(forging({"baseline": valid}, code=exit_code))
                result, err = self.call_reports("baseline")
                self.assertEqual(result, ("exit", 3), err)
                self.assertEqual(err.splitlines(), [self.unavailable(reason, "baseline")])

    def test_a_nonzero_exit_is_reported_before_an_oversized_stdout(self):
        # The exit code is checked before the size of stdout, so a child that
        # exits 1 with more than the bound on stdout is reported as exiting 1.
        self.assertEqual(gate.RESULT_LIMIT, 65536)
        self.fake_extractor(forging({"baseline": b" " * 65537}, code=1))
        result, err = self.call_reports("baseline")
        self.assertEqual(result, ("exit", 3), err)
        self.assertEqual(err, self.unavailable("exited 1", "baseline") + "\n")

    def test_a_reply_followed_by_a_form_feed_or_a_vertical_tab_is_not_json(self):
        # The reply is parsed as printed, never stripped first, so a valid
        # reply followed by a character that JSON does not count as whitespace
        # is no JSON result.
        valid = b'{"op": "baseline", "outcome": "value", "value": "1.0.14"}'
        for label, output in (
            ("a form feed and a newline", valid + b"\x0c\n"),
            ("a vertical tab", valid + b"\x0b"),
        ):
            with self.subTest(label):
                self.fake_extractor(forging({"baseline": output}))
                result, err = self.call_reports("baseline")
                self.assertEqual(result, ("exit", 3), err)
                self.assertEqual(err, self.unavailable("did not print a JSON result", "baseline") + "\n")

    def test_a_reply_preceded_by_a_form_feed_or_a_vertical_tab_is_not_json(self):
        # The reply is not stripped on the left either, so a valid reply behind
        # a character that JSON does not count as whitespace is no JSON result.
        valid = b'{"op": "baseline", "outcome": "value", "value": "1.0.14"}\n'
        for label, output in (
            ("a form feed", b"\x0c" + valid),
            ("a vertical tab", b"\x0b" + valid),
        ):
            with self.subTest(label):
                self.fake_extractor(forging({"baseline": output}))
                result, err = self.call_reports("baseline")
                self.assertEqual(result, ("exit", 3), err)
                self.assertEqual(err, self.unavailable("did not print a JSON result", "baseline") + "\n")

    def test_a_malformed_message_reaches_the_caller_unchanged(self):
        # The message of a malformed reply is raised exactly as the child
        # printed it, never stripped, so a report quotes the verdict of the
        # extractor as it was given.
        message = "  padded verdict \n"
        self.fake_extractor(forging({"extract": json.dumps(
            {"op": "extract", "outcome": "malformed", "message": message}
        ).encode("ascii") + b"\n"}))
        self.assertEqual(self.call_reports("extract", "x"), (("malformed", message), ""))

    def test_a_sigchld_reset_that_raises_oserror_exits_3_before_any_child(self):
        # An OSError from the reset of SIGCHLD, which Linux gives only under a
        # mock, exits 3 naming it, as a ValueError does, and no child is
        # started.
        tool = self.fake_extractor(logging_extractor(fail_first=False))
        refused = OSError(errno.EINVAL, "Invalid argument")
        err = io.StringIO()
        with mock.patch.object(gate.signal, "signal", side_effect=refused) as reset, \
                contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as stop:
            gate.main()
        self.assertEqual(stop.exception.code, 3)
        reset.assert_called_once_with(signal.SIGCHLD, signal.SIG_DFL)
        self.assertEqual(err.getvalue(), (
            "check-release-checksum-live: could not reset SIGCHLD to its default disposition "
            "(OSError: [Errno 22] Invalid argument), so the end of a child could be lost\n"
        ))
        self.assertFalse((tool.parent / "runs.log").exists(), "a child was started")

    def test_the_relayed_stderr_is_stripped(self):
        # The relayed stderr is stripped, so a trailing newline adds no blank
        # line, and stderr of only whitespace relays nothing. It is stripped at
        # both ends, so leading spaces or a leading newline add nothing before
        # the text either.
        for label, printed, expected in (
            ("a trailing newline", b"boom\n", self.unavailable("exited 1", "baseline") + "; it printed: boom\n"),
            ("only whitespace", b"\n", self.unavailable("exited 1", "baseline") + "\n"),
            ("leading spaces", b"  boom\n", self.unavailable("exited 1", "baseline") + "; it printed: boom\n"),
            ("a leading newline", b"\nboom", self.unavailable("exited 1", "baseline") + "; it printed: boom\n"),
        ):
            with self.subTest(label):
                self.fake_extractor(extractor_with(
                    "def json_main():\n"
                    "    sys.stdin.buffer.read()\n"
                    f"    sys.stderr.buffer.write({printed!r})\n"
                    "    return 1\n"
                ))
                result, err = self.call_reports("baseline")
                self.assertEqual(result, ("exit", 3), err)
                self.assertEqual(err, expected)

    def test_the_relayed_stderr_is_decoded_as_utf_8(self):
        # The relayed stderr is decoded as UTF-8, so a character outside ASCII
        # is relayed as itself, never replaced or read as Latin-1.
        self.fake_extractor(extractor_with(
            "def json_main():\n"
            "    sys.stdin.buffer.read()\n"
            "    sys.stderr.buffer.write(\"\\u00e9chec\\n\".encode(\"utf-8\"))\n"
            "    return 1\n"
        ))
        result, err = self.call_reports("baseline")
        self.assertEqual(result, ("exit", 3), err)
        self.assertEqual(err, self.unavailable("exited 1", "baseline") + "; it printed: \u00e9chec\n")

    def test_a_child_that_prints_and_hangs_relays_its_stderr(self):
        # When the gate sees no end of the child within the timeout, the report
        # relays what the child printed to stderr, as it does for every other
        # failure of a child that ran. The 1 second timeout starts only once
        # the child has printed and is ready (timeout_when_ready).
        tool = self.fake_extractor(extractor_with(
            "def extract(text):\n"
            "    import time\n"
            "    sys.stderr.write(\"stuck\\n\")\n"
            "    sys.stderr.flush()\n"
            + SAY_READY +
            "    time.sleep(300)\n"
        ))
        gate.CHILD_TIMEOUT_SECONDS = 1
        with self.timeout_when_ready(tool.parent / "ready"):
            result, err = self.call_reports("extract", "x")
        self.assertTrue((tool.parent / "ready").exists(), "the extract child did not get ready")
        self.assertEqual(result, ("exit", 3), err)
        self.assertEqual(err, self.unavailable("was not seen to end within 1 seconds", "extract")
                         + "; it printed: stuck\n")

    def test_the_relayed_gh_stderr_is_stripped(self):
        # A failed download relays the gh stderr stripped at both ends, so
        # leading or trailing whitespace adds nothing to the report line.
        for label, printed in (
            ("surrounding spaces and a newline", "  HTTP 502\n"),
            ("a leading newline", "\nHTTP 502"),
        ):
            with self.subTest(label):
                def failed(*args, check=True):
                    raise subprocess.CalledProcessError(1, ["gh", *args], "", printed)

                gate.gh = failed
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as stop:
                    gate.published_digest(f"v{AHEAD}", f"cleanlanguage-{AHEAD}.zip", f"cleanlanguage-{AHEAD}.zip.sha256")
                self.assertEqual(stop.exception.code, 2)
                self.assertEqual(err.getvalue(), self.CV + (
                    f"could not download cleanlanguage-{AHEAD}.zip / cleanlanguage-{AHEAD}.zip.sha256 "
                    f"from v{AHEAD}: HTTP 502\n"
                ))

    def test_the_verify_page_must_show_a_bare_checksum_and_version(self):
        # The verify page is read by exact patterns. An empty checksum block, a
        # checksum 1 digit short, and a version that does not start with a
        # digit each exit 3 with their own report, before any release is read.
        short = ZIP_SUM[:63]
        sha = "is not a 64 character lower-case SHA-256"
        for label, version, checksum, report in (
            ("an empty checksum block", CURRENT, "", f"the displayed checksum '' {sha}"),
            ("a checksum one digit short", CURRENT, short, f"the displayed checksum {short!r} {sha}"),
            ("a version that starts with a dot", "." + CURRENT, ZIP_SUM,
             "the verify page does not state which version its checksum belongs to"),
        ):
            with self.subTest(label):
                self.fixtures(version, checksum, CURRENT)
                self.assertEqual(self.main_reports(), (3, "", f"check-release-checksum-live: {report}\n"))

    def test_every_part_of_the_verify_page_patterns_is_pinned(self):
        # The checksum block, the checksum and the version on the verify page
        # are each read by an exact pattern, so a page that the shipped pattern
        # and a pattern with 1 part changed would answer differently exits 3
        # with its own report, before any release is read. The checksum is
        # exactly 64 lower-case hex digits once stripped. The version is the
        # shipped pattern, as the release tooling writes it
        # (tools/set-release-links.py): an ASCII digit and then any run of
        # ASCII digits and dots, between "version " and " is"; a version in
        # that form that is not the current one is read as such, and reported
        # as a release that is not published.
        sha = "is not a 64 character lower-case SHA-256"
        no_block = 'the verify page has no <code class="sum" id="published-checksum"> block'
        unstated = "the verify page does not state which version its checksum belongs to"
        stated = f"<p>The published checksum for version {CURRENT} is:</p>\n"
        block = '<code class="sum" id="published-checksum">{}</code>\n'
        self.assertNotEqual(ZIP_SUM.upper(), ZIP_SUM)
        other_script = ZIP_SUM[:63] + "\u0661"
        cases = [
            ("a block that holds markup", stated + block.format(f"<b>{ZIP_SUM}</b>"), no_block),
            ("a block closed by another tag", stated + '<code class="sum" id="published-checksum">abc</span>\n', no_block),
            ("an upper-case block", stated + '<CODE CLASS="sum" ID="published-checksum">abc</CODE>\n', no_block),
            ("a checksum on a line of its own", stated + block.format("\n abc\n"),
             f"the displayed checksum 'abc' {sha}"),
            ("an upper-case checksum", stated + block.format(ZIP_SUM.upper()),
             f"the displayed checksum {ZIP_SUM.upper()!r} {sha}"),
            ("a checksum with a digit of another script", stated + block.format(other_script),
             f"the displayed checksum {other_script!r} {sha}"),
            ("a checksum one digit too long", stated + block.format(ZIP_SUM + "0"),
             f"the displayed checksum {ZIP_SUM + '0'!r} {sha}"),
        ]
        for sentence in (
            "version .0.14 is", "version 1x0.14 is", "version 1.0x14 is", "version \u0661.0.14 is",
            "version 1.\u0660.14 is", "version 1.0.\u0661\u0664 is", "version 1.0.14 was", "version\n1.0.14 is",
            "version 1.0.14\nis", "Version 1.0.14 is",
        ):
            cases.append((sentence, f"<p>The published checksum for {sentence}:</p>\n" + block.format(ZIP_SUM),
                          unstated))
        cases.append(("an upper-case sentence", "<p>The Published Checksum For Version 1.0.14 is:</p>\n"
                      + block.format(ZIP_SUM), unstated))
        for label, page, report in cases:
            with self.subTest(label):
                gate.VERIFY_PAGE.write_text(page, encoding="utf-8")
                gate.SKILL.write_text(f"Version: {CURRENT}\n", encoding="utf-8")
                self.assertEqual(self.main_reports(), (3, "", f"check-release-checksum-live: {report}\n"))

        class Probed(Exception):
            pass

        def probe(tag):
            raise Probed(tag)

        for version in (CURRENT, "1234.0.100"):
            with self.subTest(version):
                self.fixtures(version, ZIP_SUM, CURRENT)
                gate.release_status = probe
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    with self.assertRaises(Probed) as caught:
                        gate.main()
                self.assertEqual((str(caught.exception), out.getvalue(), err.getvalue()), (f"v{version}", "", ""))
        # A version of one, two or four parts, or with an empty part, is in
        # the shipped form, so the gate reads its release status and reports
        # it, with no release, as a version that is not the current one.
        for version in ("7", "0.9.1", "1.0", "1.0.14.1", "1..14", "1.0.", "1234.0.100"):
            with self.subTest(version):
                self.fixtures(version, ZIP_SUM, CURRENT)
                probed = []
                gate.release_status = lambda tag: probed.append(tag) or 404
                self.assertEqual(self.main_reports(), (1, (
                    "Release checksum inconsistency found:\n"
                    f"  - the verify page names version {version}, which has no published release\n"
                    f"  - cleanlanguage/skills/cleanlanguage/SKILL.md names {CURRENT} as the current version\n"
                    "\n"
                    "A site legitimately ahead of its release names the current skill version. This looks like a "
                    "typo or a stale bump; align the verify page with SKILL.md, or publish release "
                    f"v{version}.\n"
                ), ""))
                self.assertEqual(probed, [f"v{version}"])

    def test_a_second_checksum_block_or_version_sentence_exits_3(self):
        # A page with 2 checksum blocks, or 2 version sentences, is not read by its first: it carries more than the
        # download block of the checksum and version it is read by, so it is refused before any release is read.
        page = VERIFY.format(version=CURRENT, checksum=ZIP_SUM)
        code = f'<code class="sum" id="published-checksum">{ZIP_SUM}</code>'
        sentence = f"<p>The published checksum for version {CURRENT} is:</p>"
        shown = "check-release-checksum-live: the verify page shows a published checksum, but "
        block = ("does not carry the download block that tools/build-site.py writes for this state exactly once, "
                 "byte for byte (found 0)")
        for label, changed, report in (
            ("a second checksum block after the first", page.replace(code, code + code.replace(ZIP_SUM, "abc")), block),
            ("a second, wrong checksum block before the block, which is read",
             page.replace("<h1>", code.replace(ZIP_SUM, OTHER_SUM) + "<h1>"), block),
            ("another version first", page.replace("<h1>", sentence.replace(CURRENT, "1234.0.100") + "<h1>"), block),
            ("a second sentence after the block", outside(page, sentence),
             'says "published checksum" outside the download block'),
        ):
            with self.subTest(label):
                gate.VERIFY_PAGE.write_text(changed, encoding="utf-8")
                gate.SKILL.write_text(f"Version: {CURRENT}\n", encoding="utf-8")
                gate.release_status = unexpected_call
                self.assertEqual(self.main_reports(), (3, "", f"{shown}{report}\n"))

    def test_a_manifest_with_or_without_a_final_newline_is_one_line(self):
        # The manifest is read as lines, so a final newline, which a real
        # manifest ends in, ends its 1 line rather than starting a second,
        # empty one.
        for label, ending in (("with a final newline", "\n"), ("without a final newline", "")):
            with self.subTest(label):
                def manifest(*args, check=True):
                    self.fake_download(*args, check=check)
                    target = Path(args[args.index("--dir") + 1])
                    (target / f"cleanlanguage-{AHEAD}.zip.sha256").write_text(
                        f"{ZIP_SUM}  cleanlanguage-{AHEAD}.zip{ending}", encoding="utf-8"
                    )
                    return subprocess.CompletedProcess(args, 0, "", "")

                gate.gh = manifest
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    digest = gate.published_digest(
                        f"v{AHEAD}", f"cleanlanguage-{AHEAD}.zip", f"cleanlanguage-{AHEAD}.zip.sha256"
                    )
                self.assertEqual((digest, err.getvalue()), (ZIP_SUM, ""))

    def test_a_manifest_ending_in_a_blank_line_is_not_one_line(self):
        # The final newline ends the one line, but a second newline starts a
        # second, empty one, so a manifest ending in a blank line is not
        # exactly one line and is unverifiable, before its form is read.
        def manifest(*args, check=True):
            self.fake_download(*args, check=check)
            target = Path(args[args.index("--dir") + 1])
            (target / f"cleanlanguage-{AHEAD}.zip.sha256").write_text(
                f"{ZIP_SUM}  cleanlanguage-{AHEAD}.zip\n\n", encoding="utf-8"
            )
            return subprocess.CompletedProcess(args, 0, "", "")

        gate.gh = manifest
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as stop:
            gate.published_digest(f"v{AHEAD}", f"cleanlanguage-{AHEAD}.zip", f"cleanlanguage-{AHEAD}.zip.sha256")
        self.assertEqual(stop.exception.code, 2)
        self.assertEqual(err.getvalue(), self.CV + f"cleanlanguage-{AHEAD}.zip.sha256 is not exactly one line\n")

    def test_a_manifest_digest_one_digit_short_is_unverifiable(self):
        # The digest of the manifest has exactly 64 hex digits; 1 digit short
        # fails its form, before the zip is hashed.
        short = ZIP_SUM[:63]

        def short_manifest(*args, check=True):
            self.fake_download(*args, check=check)
            target = Path(args[args.index("--dir") + 1])
            (target / f"cleanlanguage-{AHEAD}.zip.sha256").write_text(
                f"{short}  cleanlanguage-{AHEAD}.zip", encoding="utf-8"
            )
            return subprocess.CompletedProcess(args, 0, "", "")

        gate.gh = short_manifest
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as stop:
            gate.published_digest(f"v{AHEAD}", f"cleanlanguage-{AHEAD}.zip", f"cleanlanguage-{AHEAD}.zip.sha256")
        self.assertEqual(stop.exception.code, 2)
        self.assertEqual(err.getvalue(), self.CV + (
            f"cleanlanguage-{AHEAD}.zip.sha256 is not '<digest>  cleanlanguage-{AHEAD}.zip'\n"
        ))

    def test_a_refused_stdout_relays_the_stderr(self):
        # A child that exits 0 but prints a stdout the gate refuses, one over
        # the bound, one that is not JSON, or one that breaks the contract,
        # relays what it printed to stderr with the reason, as every other
        # failure of a child that ran does.
        self.assertEqual(gate.RESULT_LIMIT, 65536)
        for label, output, reason in (
            ("over the bound", "b\" \" * 65537", "printed more than 65536 bytes"),
            ("not JSON", "b\"not json\\n\"", "did not print a JSON result"),
            ("against the contract", "b\"[]\\n\"",
             "printed a result that does not match the contract (not a JSON object)"),
        ):
            with self.subTest(label):
                self.fake_extractor(extractor_with(
                    "def json_main():\n"
                    "    sys.stdin.buffer.read()\n"
                    f"    sys.stdout.buffer.write({output})\n"
                    "    sys.stderr.buffer.write(b\"warned\\n\")\n"
                    "    return 0\n"
                ))
                result, err = self.call_reports("baseline")
                self.assertEqual(result, ("exit", 3), err)
                self.assertEqual(err, self.unavailable(reason, "baseline") + "; it printed: warned\n")

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
            ("a lone surrogate, carried only by ASCII escaping", valid + "\ud800\n"),
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
        # Row 80: a spawn failure, or an interpreter path that is empty,
        # None, or relative, exits 3 as unavailable without running anything.
        gate.RELEASE_DATE_TOOL = Path(self._tmp.name) / "no-such-directory" / "skill-release-date.py"
        result, err = self.call_reports("baseline")
        self.assertEqual(result, ("exit", 3), err)
        self.assertTrue(err.startswith(
            "check-release-checksum-live: skill-release-date.py could not run (FileNotFoundError: "
        ), err)
        self.assertTrue(err.endswith(" in baseline, so the extractor is unavailable\n"), err)
        gate.RELEASE_DATE_TOOL = EXTRACTOR_PATH
        for executable in ("", None, "python3"):
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
        # Row 80: a KeyboardInterrupt while the gate waits, where the group can
        # be killed, kills the child group, reaps the child, and propagates
        # unchanged. It is raised here from a stubbed os.waitid, not by a real
        # signal, which can arrive at any point of the wait; an Exception while
        # waiting exits 3 instead (see
        # test_a_failure_while_waiting_kills_and_reaps_the_child_and_exits_3).
        # The gate waits with os.waitid, so the interrupt is raised from there.
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
            # Only the wait is interrupted; the reap after the kill polls the
            # real os.waitid.
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
        # the child classifies with the same except Malformed the CLI uses, so
        # a subclass of Malformed raised by a modified
        # release_day_from_published_at is a content verdict (2).
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


    # --- Row 80: the child machinery, its group, its bound -------------------

    MACHINERY = "could not be run, waited for, or read"

    def recording_popen(self, procs):
        """A Popen subclass that appends each child it starts to ``procs``."""

        class Recording(subprocess.Popen):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                procs.append(self)

        return Recording

    def test_a_failure_in_the_child_machinery_exits_3(self):
        # An Exception (here an OSError or a RuntimeError) raised while the
        # gate creates the temporary files, writes or rewinds the request, or
        # rewinds or reads the output exits 3 naming it, never a traceback
        # (exit 1), and leaves no child unreaped. A KeyboardInterrupt there is
        # not caught and passes through (see run_release_date_child).
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
        # An Exception other than ChildProcessError (here an OSError or a
        # RuntimeError) while the gate waits, where the group can be killed,
        # kills the child group while the child is unreaped, reaps the child,
        # and exits 3 naming the exception.
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
                    # real os.waitid.
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
        # When the wait reports that the child is no longer a child of the
        # gate, its pid and group id may already be reused, so the gate signals
        # neither and exits 3 naming the error.
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
        # A process the child started that is still in its group, here a direct
        # child and the grandchild of a double fork (which keeps the group), is
        # killed once the child has ended normally, and the group is killed
        # while the ended child is still unreaped.
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
        # The disclosed residual, observed: a process that leaves the child's
        # process group, by any means, can outlive the gate. Here a process the
        # child started calls setpgid into a new group, so the group kill does
        # not reach it and it is still running after the gate has returned its
        # reply.
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
            # Any live state counts, so the check does not depend on whether
            # the process is sleeping or still runnable when it is read.
            self.assertNotIn(process_state(pid), (None, "Z"), f"the process {pid} that left the group did not outlive the gate")
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
        # An OSError other than ProcessLookupError from the group kill exits 3
        # naming it, after the child is killed directly where it still runs and
        # reaped where it can be; a child that cannot be killed either is not
        # waited for.
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
                # Only a subtest that times out shortens the timeout, so a
                # normal end on a busy host never races it.
                gate.CHILD_TIMEOUT_SECONDS = self._saved_child[1] if body is None else 1
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
                # Far below the 300 seconds the hung child sleeps, so a gate
                # that waited for it still fails, with room for a busy host to
                # start and end a child.
                self.assertLess(elapsed, 60)

    def test_an_echoed_request_of_any_size_keeps_its_verdict(self):
        # The stdout bound grows with the request, so the malformed messages
        # tested here, which echo a long argument enlarged by repr and by ASCII
        # JSON escaping, keep the verdict and the message the extractor gives.
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
        # The bound is RESULT_LIMIT plus 12 bytes for each character of the
        # argument; a reply of exactly that size is accepted and 1 byte more is
        # refused, naming the bound.
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
        # A reply is exactly 1 JSON object that matches the contract, so a key
        # given twice is refused, never read with the last value winning.
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

    # A fake extractor whose extract op has a process in another session seize
    # the child with ptrace (the child names it its tracer first), so the end
    # of the child is reported to that tracer, which holds it for HOLD seconds,
    # and not to the gate; the child writes the tracer pid to tracer.pid beside
    # it and exits 9 when the seize is refused. The tracer closes its own copy
    # of the go pipe, so when the child ends before it says go (as when it is
    # killed first) the tracer reads the end of the pipe and exits at once
    # instead of waiting for ever in a session of its own, where no kill of the
    # child group reaches it.
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
        "        os.close(go_w)\n"
        "        if os.read(go_r, 1) != b\"x\":\n"
        "            os._exit(0)\n"
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
        + SAY_READY +
        "    return _real_extract(text)\n"
    )

    def test_a_child_whose_end_is_hidden_from_the_gate_ends_the_gate_within_the_bound(self):
        # A process of the same uid in another session seizes the child with
        # ptrace, so the child's end is reported to it and not to the gate. The
        # gate sees no end within the timeout, kills the group, then sees no
        # end within the reap grace either, and exits 3 naming that it could
        # not reap the child, leaving it, within the 2 bounds, instead of
        # blocking in a reap until the tracer exits (30 seconds here). The test
        # skips only where the host refuses the seize; the next test simulates
        # the same outcome in-process on every host.
        tool = self.fake_extractor(extractor_with(self.TRACED.replace("HOLD", "30")))
        gate.CHILD_TIMEOUT_SECONDS = 1
        gate.REAP_GRACE_SECONDS = 1
        procs = []
        real_popen = subprocess.Popen
        gate.subprocess.Popen = self.recording_popen(procs)
        pid_file = tool.parent / "tracer.pid"
        try:
            # The 1 second timeout starts only once the seize has succeeded, so
            # it cannot fire while the child is still being seized on a busy
            # host. The bound below is measured from then, so the time a busy
            # host takes to start the child does not count against it.
            with self.timeout_when_ready(tool.parent / "ready") as ready_state:
                started = time.monotonic()
                result, err = self.call_reports("extract", self.ARGS["extract"])
                elapsed = time.monotonic() - ready_state.get("ready_at", started)
            if result == ("exit", 3) and "exited 9" in err:
                self.skipTest("this host refuses PTRACE_SEIZE of the child")
            self.assertTrue((tool.parent / "ready").exists(), "the child was not seized before the timeout")
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
        # The outcome of the previous test, simulated in-process on every host:
        # os.waitid never reports the end of the child, as when another process
        # holds it, so after the timeout and the group kill the gate polls for
        # at most the reap grace, exits 3 naming that it could not reap the
        # child, and does not reap it.
        self.fake_extractor(extractor_with("def extract(text):\n    import time\n    time.sleep(300)\n"))
        gate.CHILD_TIMEOUT_SECONDS = 1
        gate.REAP_GRACE_SECONDS = 1
        procs, kills = [], []
        real_popen, real_killpg, real_waitid = subprocess.Popen, os.killpg, os.waitid

        def recording(pgid, sig):
            kills.append((pgid, sig))
            real_killpg(pgid, sig)

        guard = time.monotonic()

        def hidden(idtype, ident, options):
            # A gate whose waits had no bound would poll for ever; it fails
            # here instead of hanging the suite.
            if time.monotonic() - guard > 30:
                raise AssertionError("the gate polled for more than 30 seconds")
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
        # Each place in the gate that turns an outcome of release_date_call
        # into an exit code or a message (the malformed and absent mapping in
        # release_date_call, the probe in probe_release_date_tool, the
        # malformed handlers in skill_released, released_line, and
        # check_release_date, and the baseline in report_missing_released_line)
        # is pinned here through main, with its exact exit and output. Every
        # value the gate takes from the extractor here, the extracted day, the
        # baseline rule, the published day, and the baseline itself, is also
        # given by a fake extractor that answers differently from the real one
        # (a baseline of 1.0.20, not 1.0.14), so a gate that put today's real
        # answer in place of any of these calls fails this test as well as one
        # that dropped a handler.
        def site_matches(version):
            return (f"The verify page checksum {ZIP_SUM} matches the published cleanlanguage-{version}.zip "
                    f"for release v{version}.")

        matches = site_matches(AHEAD)
        later = "1.0.21"
        other_baseline = extractor_with("BASELINE_VERSION = \"1.0.20\"\n")
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
            ("a baseline other than today's: the missing line names it", other_baseline, ZIP_SUM, later, None,
             "2026-11-15T09:30:00Z",
             (1, [
                 "Release date inconsistency found:",
                 f"  - release v{later} is published",
                 f"  - cleanlanguage/skills/cleanlanguage/SKILL.md names {later}, above the undated baseline "
                 f"1.0.20, but has no Released: line",
                 site_matches(later),
             ], [])),
            ("a baseline other than today's: a version at or below it needs no line", other_baseline, ZIP_SUM,
             AHEAD, None, "2026-11-15T09:30:00Z",
             (0, [matches], [])),
            ("a published day other than today's reading of published_at", extractor_with(
                "def release_day_from_published_at(value):\n    return \"2026-11-16\"\n"
            ), ZIP_SUM, AHEAD, "Released: 2026-11-16", "2026-11-15T09:30:00Z",
             (0, [f"The SKILL.md Released date 2026-11-16 matches the publication day of release v{AHEAD}.",
                  matches], [])),
            ("an extracted day other than today's reading of the line", extractor_with(
                "def extract(text):\n    return \"2026-11-17\"\n"
            ), ZIP_SUM, AHEAD, "Released: 2026-11-15", "2026-11-17T09:30:00Z",
             (0, [f"The SKILL.md Released date 2026-11-17 matches the publication day of release v{AHEAD}.",
                  matches], [])),
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


    # --- The wait, the reap, and the kill, pinned exactly --------------------

    def on_fake_clock(self, end_at):
        """Point the gate at a fake clock that starts at 100 and advances only
        by the sleeps of the gate, and at an os.waitid that reports the end of
        the child once that clock reaches ``end_at``. Returns the clock state,
        the sleeps, the waitid calls, and a function that restores the real
        clock and waitid. A wait that sleeps more than 10000 times, or reads
        the clock more than 100000 times, fails instead of hanging."""
        state = {"now": 100.0, "reads": 0}
        sleeps, waits = [], []
        real_time, real_waitid = gate.time, os.waitid

        def monotonic():
            state["reads"] += 1
            if state["reads"] > 100000:
                raise AssertionError("the wait read the clock more than 100000 times")
            return state["now"]

        def sleep(seconds):
            if len(sleeps) >= 10000:
                raise AssertionError("the wait slept more than 10000 times")
            sleeps.append(seconds)
            state["now"] += seconds

        def waitid(idtype, ident, options):
            waits.append((idtype, ident, options))
            return types.SimpleNamespace(si_pid=ident) if state["now"] >= end_at else None

        gate.time = types.SimpleNamespace(monotonic=monotonic, sleep=sleep)
        gate.os.waitid = waitid

        def restore():
            gate.time = real_time
            gate.os.waitid = real_waitid

        return state, sleeps, waits, restore

    def test_the_wait_polls_within_its_deadline_on_a_fake_clock(self):
        # _wait_unreaped waits exactly its timeout argument (here 7.25 seconds,
        # no default of the gate), never sleeps past the deadline or more than
        # 0.05 seconds at a time, starts at 1 millisecond and doubles, never
        # sleeps for 0 seconds, polls only with WEXITED, WNOWAIT, and WNOHANG
        # for this pid, and returns True at the first poll that sees the end.
        child = types.SimpleNamespace(pid=4242)
        flags = os.WEXITED | os.WNOWAIT | os.WNOHANG
        for label, end_at, expected, low, high in (
            ("no end within the timeout", float("inf"), False, 7.25, 7.25),
            ("an end after 0.5 seconds", 100.5, True, 0.5, 0.55),
        ):
            with self.subTest(label):
                state, sleeps, waits, restore = self.on_fake_clock(end_at)
                try:
                    result = gate._wait_unreaped(child, 7.25)
                finally:
                    restore()
                self.assertIs(result, expected)
                elapsed = state["now"] - 100.0
                self.assertGreaterEqual(elapsed, low - 1e-9)
                self.assertLessEqual(elapsed, high + 1e-9)
                self.assertEqual(sleeps[:3], [0.001, 0.002, 0.004])
                self.assertLessEqual(max(sleeps), 0.05)
                self.assertGreater(min(sleeps), 0)
                self.assertEqual(set(waits), {(os.P_PID, 4242, flags)})
                self.assertEqual(len(waits), len(sleeps) + 1)

    def test_the_reap_waits_only_its_grace_on_a_fake_clock(self):
        # _reap waits at most REAP_GRACE_SECONDS (here 2.75, no default of the
        # gate) for the end of the child and names that grace when it sees no
        # end, without reaping; it reaps once, with Popen.wait, only after it
        # sees the end.
        gate.REAP_GRACE_SECONDS = 2.75
        for label, end_at, expected, elapsed, reaped in (
            ("no end within the grace", float("inf"),
             "could not be reaped (the gate saw no end of it within 2.75 seconds after its kill)", 2.75, 0),
            ("an end after 1 second", 101.0, None, None, 1),
        ):
            with self.subTest(label):
                reaps = []
                child = types.SimpleNamespace(pid=4242, wait=lambda: reaps.append("wait"))
                state, sleeps, waits, restore = self.on_fake_clock(end_at)
                try:
                    result = gate._reap(child)
                finally:
                    restore()
                self.assertEqual(result, expected)
                self.assertEqual(len(reaps), reaped)
                if elapsed is not None:
                    self.assertAlmostEqual(state["now"] - 100.0, elapsed, places=9)
                else:
                    self.assertLessEqual(state["now"], 101.05 + 1e-9)

    def kill_reports(self, op, arg, killpg, kill, waitid=None):
        """Run release_date_call for ``op`` with os.killpg, os.kill, and,
        when given, os.waitid replaced, recording each os.kill call. Returns
        (result, stderr, the os.kill calls, the return codes of the children,
        seconds taken); every child left running is killed and reaped."""
        procs, kills = [], []
        real_popen, real_killpg, real_kill, real_waitid = subprocess.Popen, os.killpg, os.kill, os.waitid

        def recording_kill(pid, sig):
            kills.append((pid, sig))
            kill(pid, sig)

        gate.subprocess.Popen = self.recording_popen(procs)
        gate.os.killpg = killpg
        gate.os.kill = recording_kill
        if waitid is not None:
            gate.os.waitid = waitid
        try:
            started = time.monotonic()
            try:
                result, err = self.call_reports(op, arg)
            except KeyboardInterrupt:
                result, err = ("interrupt", None), ""
            elapsed = time.monotonic() - started
            returncodes = [proc.returncode for proc in procs]
        finally:
            gate.subprocess.Popen = real_popen
            gate.os.killpg = real_killpg
            gate.os.kill = real_kill
            gate.os.waitid = real_waitid
            for proc in procs:
                if proc.returncode is None:
                    proc.kill()
                    proc.wait()
        return result, err, [(sig, pid == procs[0].pid) for pid, sig in kills], returncodes, elapsed

    DENIED = PermissionError(errno.EPERM, "Operation not permitted")
    DENIED_NAMED = "PermissionError: [Errno 1] Operation not permitted"
    HUNG = "def extract(text):\n    import time\n    time.sleep(300)\n"

    def denied(self, *args):
        raise self.DENIED

    def test_a_failed_group_kill_kills_the_child_directly_only_when_it_has_not_ended(self):
        # When the group kill fails, the gate kills the child itself, with
        # SIGKILL, only when the child has not ended (after a timeout), and
        # never after a normal end, even when that kill would fail too; either
        # way it reaps the child it can and exits 3 naming the group kill.
        problem = f"could not kill the process group of its child ({self.DENIED_NAMED})"
        gate.REAP_GRACE_SECONDS = 1
        for label, body, op, arg, kill, expected_kills, returncodes in (
            ("after a normal end", None, "baseline", None, os.kill, [], [0]),
            ("after a normal end, with a direct kill that would fail", None, "baseline", None, self.denied, [], [0]),
            ("after a timeout", self.HUNG, "extract", "x", os.kill, [(signal.SIGKILL, True)], [-signal.SIGKILL]),
        ):
            with self.subTest(label):
                if body is None:
                    gate.RELEASE_DATE_TOOL = EXTRACTOR_PATH
                else:
                    self.fake_extractor(extractor_with(body))
                # Only the subtest that times out shortens the timeout, so a
                # normal end on a busy host never races it.
                gate.CHILD_TIMEOUT_SECONDS = self._saved_child[1] if body is None else 1
                result, err, kills, codes, elapsed = self.kill_reports(op, arg, self.denied, kill)
                self.assertEqual(result, ("exit", 3), err)
                self.assertEqual(err.splitlines(), [self.unavailable(problem, op)])
                self.assertEqual(kills, expected_kills)
                self.assertEqual(codes, returncodes)
                # Far below the 300 seconds the hung child sleeps, so a gate
                # that waited for it still fails, with room for a busy host to
                # start and end a child.
                self.assertLess(elapsed, 60)

    def test_a_group_kill_that_finds_no_process_still_reaps_the_child(self):
        # A group kill that reports no such process (ProcessLookupError) is not
        # a failure: the gate reaps the ended child and returns its reply. On
        # Linux this cannot happen while the child is unreaped, as the child
        # leads its own session and so stays in its group; it is simulated
        # here.
        def missing(*args):
            raise ProcessLookupError(errno.ESRCH, "No such process")

        gate.RELEASE_DATE_TOOL = EXTRACTOR_PATH
        result, err, kills, codes, elapsed = self.kill_reports("baseline", None, missing, os.kill)
        self.assertEqual((result, err), (("value", CURRENT), ""))
        self.assertEqual(kills, [])
        self.assertEqual(codes, [0])

    def test_a_failed_direct_kill_still_reaps_a_child_that_has_ended(self):
        # When the group kill and the direct kill both fail, the gate does not
        # wait for the child, but a child that has already ended (here it is
        # killed, and becomes a zombie, before the direct kill reports its
        # failure) is still reaped by a non-blocking poll.
        self.fake_extractor(extractor_with(self.HUNG))
        gate.CHILD_TIMEOUT_SECONDS = 1
        real_kill = os.kill

        def ends_then_fails(pid, sig):
            real_kill(pid, signal.SIGKILL)
            deadline = time.monotonic() + 10
            while process_state(pid) != "Z" and time.monotonic() < deadline:
                time.sleep(0.01)
            raise self.DENIED

        result, err, kills, codes, elapsed = self.kill_reports("extract", "x", self.denied, ends_then_fails)
        self.assertEqual(result, ("exit", 3), err)
        self.assertEqual(err.splitlines(), [self.unavailable(
            f"could not kill the process group of its child ({self.DENIED_NAMED})", "extract"
        )])
        self.assertEqual(kills, [(signal.SIGKILL, True)])
        self.assertEqual(codes, [-signal.SIGKILL])

    def test_a_failed_group_kill_with_a_hidden_end_leaves_the_child_unreaped(self):
        # After a failed group kill and a direct kill, the reap is bounded by
        # REAP_GRACE_SECONDS like every other reap. Here os.waitid never
        # reports the end of the child, so the gate names both the group kill
        # and the reap it could not do, leaves the child unreaped, and returns
        # within the bounds, where an unbounded wait would have reaped it.
        self.fake_extractor(extractor_with(self.HUNG))
        gate.CHILD_TIMEOUT_SECONDS = 1
        gate.REAP_GRACE_SECONDS = 1
        real_waitid = os.waitid
        started = time.monotonic()

        def hidden(idtype, ident, options):
            # A gate whose waits had no bound would poll for ever; it fails
            # here instead of hanging the suite.
            if time.monotonic() - started > 30:
                raise AssertionError("the gate polled for more than 30 seconds")
            if options & os.WNOHANG:
                return None
            return real_waitid(idtype, ident, options)

        result, err, kills, codes, elapsed = self.kill_reports("extract", "x", self.denied, os.kill, waitid=hidden)
        self.assertEqual(result, ("exit", 3), err)
        self.assertEqual(err.splitlines(), [self.unavailable(
            f"could not kill the process group of its child ({self.DENIED_NAMED}), and could not be reaped "
            f"(the gate saw no end of it within 1 seconds after its kill)", "extract"
        )])
        self.assertEqual(kills, [(signal.SIGKILL, True)])
        self.assertEqual(codes, [None])
        self.assertLess(elapsed, 10)

    def test_an_interrupt_while_waiting_with_a_group_that_cannot_be_killed_exits_3(self):
        # A KeyboardInterrupt while the gate waits, when the group cannot be
        # killed, kills the child directly, as a child that has not ended,
        # reaps it, and exits 3 naming the group kill instead of passing the
        # interrupt on.
        self.fake_extractor(extractor_with(self.HUNG))
        gate.REAP_GRACE_SECONDS = 1
        real_waitid = os.waitid
        calls = []

        def interrupted(*args):
            calls.append(args)
            if len(calls) == 1:
                raise KeyboardInterrupt()
            return real_waitid(*args)

        result, err, kills, codes, elapsed = self.kill_reports(
            "extract", "x", self.denied, os.kill, waitid=interrupted
        )
        self.assertEqual(result, ("exit", 3), err)
        self.assertEqual(err.splitlines(), [self.unavailable(
            f"could not kill the process group of its child ({self.DENIED_NAMED})", "extract"
        )])
        self.assertEqual(kills, [(signal.SIGKILL, True)])
        self.assertEqual(codes, [-signal.SIGKILL])
        self.assertLess(elapsed, 10)

    def test_the_output_bounds_follow_the_limits_of_the_gate(self):
        # The stdout bound is RESULT_LIMIT plus ECHO_BYTES_PER_CHARACTER bytes
        # for each character of the argument, and at most STDERR_LIMIT bytes of
        # stderr are read and relayed, each taken from the gate at the call:
        # with limits other than the defaults (300, 7, and 33), a reply of
        # exactly the bound is accepted, 1 byte more is refused naming the
        # bound, the reads ask for 1 byte over the bound and for STDERR_LIMIT
        # bytes, and the relayed stderr is its first 33 bytes, decoded with
        # replacement.
        gate.RESULT_LIMIT, gate.ECHO_BYTES_PER_CHARACTER, gate.STDERR_LIMIT = 300, 7, 33
        limit = 300 + 7 * len("xy")
        valid = b'{"op": "extract", "outcome": "absent"}'
        padded = valid + b" " * (limit - len(valid))
        real_temporary_file = tempfile.TemporaryFile
        for label, output, expected in (
            ("a reply of exactly the bound", padded, (("value", None), "")),
            ("a reply one byte over the bound", padded + b" ",
             (("exit", 3), self.unavailable(f"printed more than {limit} bytes", "extract") + "\n")),
        ):
            with self.subTest(label):
                self.fake_extractor(forging({"extract": output}))
                reads = []

                class Recording:
                    def __init__(self, real, position):
                        self._real, self._position = real, position

                    def __getattr__(self, name):
                        return getattr(self._real, name)

                    def read(self, *args):
                        reads.append((self._position, args))
                        return self._real.read(*args)

                    def __enter__(self):
                        self._real.__enter__()
                        return self

                    def __exit__(self, *exc):
                        return self._real.__exit__(*exc)

                made = []

                def factory(*args, **kwargs):
                    made.append(None)
                    return Recording(real_temporary_file(*args, **kwargs), len(made) - 1)

                gate.tempfile = types.SimpleNamespace(TemporaryFile=factory)
                try:
                    result = self.call_reports("extract", "xy")
                finally:
                    gate.tempfile = tempfile
                self.assertEqual(result, expected)
                self.assertEqual(sorted(reads), [(1, (limit + 1,)), (2, (33,))])
        self.fake_extractor(extractor_with(
            "def json_main():\n"
            "    sys.stdin.buffer.read()\n"
            "    sys.stderr.buffer.write(b\"\\xff\" + b\"e\" * 100)\n"
            "    return 1\n"
        ))
        result, err = self.call_reports("extract", "xy")
        self.assertEqual(result, ("exit", 3), err)
        self.assertEqual(err.splitlines(), [self.unavailable("exited 1", "extract") + "; it printed: \ufffd" + "e" * 32])

    # --- Row 100: the output cap of the child ---------------------------------

    @contextlib.contextmanager
    def recorded_sizes(self):
        """Within the block, each temporary file the gate makes records its
        size in bytes as it closes, keyed by the order the gate made it in
        (0 stdin, 1 stdout, 2 stderr for one child)."""
        real_temporary_file = tempfile.TemporaryFile
        sizes = {}
        made = []

        class Sized:
            def __init__(self, real, position):
                self._real, self._position = real, position

            def __getattr__(self, name):
                return getattr(self._real, name)

            def __enter__(self):
                self._real.__enter__()
                return self

            def __exit__(self, *exc):
                sizes[self._position] = os.fstat(self._real.fileno()).st_size
                return self._real.__exit__(*exc)

        def factory(*args, **kwargs):
            made.append(None)
            return Sized(real_temporary_file(*args, **kwargs), len(made) - 1)

        gate.tempfile = types.SimpleNamespace(TemporaryFile=factory)
        try:
            yield sizes
        finally:
            gate.tempfile = tempfile

    @staticmethod
    def fast_writer(fds, reply=b""):
        """Extractor source whose --json mode reads its request, writes 1 MiB
        to each file descriptor in ``fds`` in 64 KiB writes, going on past
        any write that fails, then prints ``reply`` and exits 0."""
        return extractor_with(
            "def json_main():\n"
            "    import os\n"
            "    sys.stdin.buffer.read()\n"
            f"    for fd in {tuple(fds)!r}:\n"
            "        for _ in range(16):\n"
            "            try:\n"
            "                os.write(fd, b\"x\" * 65536)\n"
            "            except OSError:\n"
            "                pass\n"
            f"    sys.stdout.buffer.write({reply!r})\n"
            "    sys.stdout.buffer.flush()\n"
            "    return 0\n"
        )

    def test_each_file_the_child_writes_ends_at_the_cap_under_ordinary_writes(self):
        # Row 100: while the child runs, an ordinary write cannot grow a file
        # it writes past the cap, one byte past the larger read bound, so
        # each file this child writes 1 MiB to ends at the cap. A stdout or
        # stderr whose final size reached the cap exits 3 naming the cap,
        # before the exit code and the reply are read. Stdin is bounded by
        # the same limit but not named, so a valid reply keeps its verdict.
        # Storage reserved past the end of a file is not measured here.
        gate.RESULT_LIMIT, gate.ECHO_BYTES_PER_CHARACTER, gate.STDERR_LIMIT = 300, 7, 33
        cap = 300 + 7 * len("xy") + 2
        absent = b'{"op": "extract", "outcome": "absent"}'
        relayed = "; it printed: " + "x" * 33
        for label, fds, reply, expected in (
            ("stdout", (1,), b"",
             (("exit", 3), self.unavailable(f"wrote stdout up to the output cap of {cap} bytes", "extract") + "\n")),
            ("stderr", (2,), b"",
             (("exit", 3), self.unavailable(f"wrote stderr up to the output cap of {cap} bytes", "extract")
              + relayed + "\n")),
            ("stdout and stderr", (1, 2), b"",
             (("exit", 3), self.unavailable(f"wrote stdout and stderr up to the output cap of {cap} bytes", "extract")
              + relayed + "\n")),
            ("stdin", (0,), absent, (("value", None), "")),
        ):
            with self.subTest(label):
                self.fake_extractor(self.fast_writer(fds, reply))
                with self.recorded_sizes() as sizes:
                    result = self.call_reports("extract", "xy")
                self.assertEqual(result, expected)
                self.assertEqual(sorted(sizes), [0, 1, 2])
                for fd in fds:
                    self.assertEqual(sizes[fd], cap, sizes)
                self.assertLessEqual(max(sizes.values()), cap, sizes)

    def test_the_child_runs_under_the_file_size_limit(self):
        # Row 100: the child gets the cap as both its soft and its hard file
        # size limit, set by a preexec_fn the gate passes to Popen.
        gate.RESULT_LIMIT, gate.ECHO_BYTES_PER_CHARACTER, gate.STDERR_LIMIT = 300, 7, 33
        cap = 300 + 7 * len("xy") + 2
        for inherited in resource.getrlimit(resource.RLIMIT_FSIZE):
            if inherited != resource.RLIM_INFINITY and inherited < cap:
                cap = inherited
        self.fake_extractor(extractor_with(
            "def json_main():\n"
            "    import resource\n"
            "    sys.stdin.buffer.read()\n"
            "    soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)\n"
            "    message = \"%d %d\" % (soft, hard)\n"
            "    print(json.dumps({\"op\": \"extract\", \"outcome\": \"malformed\", \"message\": message}))\n"
            "    return 0\n"
        ))
        calls = []
        real_popen = subprocess.Popen

        class Recording(real_popen):
            def __init__(self, args, **kwargs):
                calls.append(kwargs)
                super().__init__(args, **kwargs)

        gate.subprocess.Popen = Recording
        try:
            result, err = self.call_reports("extract", "xy")
        finally:
            gate.subprocess.Popen = real_popen
        self.assertEqual(result, ("malformed", f"{cap} {cap}"), err)
        self.assertEqual(len(calls), 1)
        self.assertTrue(callable(calls[0].get("preexec_fn")), calls[0])

    def test_the_child_cannot_raise_its_soft_file_size_limit_past_the_cap(self):
        # Row 100: the cap is the hard limit as well as the soft one, and
        # setrlimit refuses a soft limit above the hard limit for every
        # process, so a child that tries to raise its soft limit back to no
        # limit is refused and its writes still stop at the cap. With the
        # inherited hard limit left in place, the raise would succeed and the
        # file would grow past the cap. A child with CAP_SYS_RESOURCE could
        # raise the hard limit first; that residual is not exercised here.
        gate.RESULT_LIMIT, gate.ECHO_BYTES_PER_CHARACTER, gate.STDERR_LIMIT = 300, 7, 33
        cap = 300 + 7 * len("xy") + 2
        tool = self.fake_extractor(extractor_with(
            "def json_main():\n"
            "    import os, resource\n"
            "    sys.stdin.buffer.read()\n"
            "    soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)\n"
            "    try:\n"
            "        resource.setrlimit(resource.RLIMIT_FSIZE, (resource.RLIM_INFINITY, hard))\n"
            "        outcome = \"raised\"\n"
            "    except (OSError, ValueError) as error:\n"
            "        outcome = \"refused \" + type(error).__name__\n"
            "    (Path(__file__).resolve().parent / \"raise.log\").write_text(outcome, encoding=\"utf-8\")\n"
            "    for _ in range(16):\n"
            "        try:\n"
            "            os.write(1, b\"x\" * 65536)\n"
            "        except OSError:\n"
            "            pass\n"
            "    return 0\n"
        ))
        with self.recorded_sizes() as sizes:
            result = self.call_reports("extract", "xy")
        self.assertEqual((tool.parent / "raise.log").read_text(encoding="utf-8"), "refused ValueError")
        self.assertEqual(sizes[1], cap, sizes)
        self.assertEqual(result, (("exit", 3), self.unavailable(
            f"wrote stdout up to the output cap of {cap} bytes", "extract") + "\n"))

    def test_a_capped_child_that_hangs_reports_the_cap_not_the_timeout(self):
        # Row 100: the cap check comes before the timeout check, as the
        # run_release_date_child docstring states, so a child that fills
        # stdout to the cap and then hangs past the timeout exits 3 naming
        # the cap, not the timeout. The 1 second timeout starts only once
        # the child has filled stdout and is ready (timeout_when_ready).
        gate.RESULT_LIMIT, gate.ECHO_BYTES_PER_CHARACTER, gate.STDERR_LIMIT = 300, 7, 33
        cap = 300 + 7 * len("xy") + 2
        tool = self.fake_extractor(extractor_with(
            "def json_main():\n"
            "    import os, time\n"
            "    sys.stdin.buffer.read()\n"
            "    for _ in range(16):\n"
            "        try:\n"
            "            os.write(1, b\"x\" * 65536)\n"
            "        except OSError:\n"
            "            pass\n"
            + SAY_READY +
            "    time.sleep(300)\n"
            "    return 0\n"
        ))
        gate.CHILD_TIMEOUT_SECONDS = 1
        with self.timeout_when_ready(tool.parent / "ready"):
            result, err = self.call_reports("extract", "xy")
        self.assertTrue((tool.parent / "ready").exists(), "the extract child did not get ready")
        self.assertEqual((result, err), (("exit", 3), self.unavailable(
            f"wrote stdout up to the output cap of {cap} bytes", "extract") + "\n"))

    def test_only_the_final_size_of_stdout_is_checked_against_the_cap(self):
        # Row 100: the fstat check reads the final size of stdout, as the
        # docstrings state. A child that fills stdout to the cap (its write
        # past the cap fails with EFBIG), truncates it, and writes a valid
        # reply is accepted: the documented residual, pinned so that a change
        # to the semantics is a deliberate one.
        gate.RESULT_LIMIT, gate.ECHO_BYTES_PER_CHARACTER, gate.STDERR_LIMIT = 300, 7, 33
        cap = 300 + 7 * len("xy") + 2
        absent = b'{"op": "extract", "outcome": "absent"}'
        tool = self.fake_extractor(extractor_with(
            "def json_main():\n"
            "    import errno, os\n"
            "    sys.stdin.buffer.read()\n"
            "    refused = 0\n"
            "    for _ in range(16):\n"
            "        try:\n"
            "            os.write(1, b\"x\" * 65536)\n"
            "        except OSError as error:\n"
            "            refused += error.errno == errno.EFBIG\n"
            "    reached = os.fstat(1).st_size\n"
            "    (Path(__file__).resolve().parent / \"filled.log\").write_text(\n"
            "        \"%d %d\" % (reached, refused), encoding=\"utf-8\")\n"
            "    os.ftruncate(1, 0)\n"
            "    os.lseek(1, 0, os.SEEK_SET)\n"
            f"    os.write(1, {absent!r})\n"
            "    return 0\n"
        ))
        with self.recorded_sizes() as sizes:
            result = self.call_reports("extract", "xy")
        self.assertEqual((tool.parent / "filled.log").read_text(encoding="utf-8"), f"{cap} 15")
        self.assertEqual(sizes[1], len(absent), sizes)
        self.assertEqual(result, (("value", None), ""))

    def test_the_cap_is_one_byte_past_the_larger_read_bound_or_a_lower_inherited_limit(self):
        # Row 100: the cap is one byte past the larger of limit + 1 and
        # STDERR_LIMIT, so a reply one byte over the bound is still refused
        # as too long (see test_the_output_bounds_follow_the_limits_of_the_gate),
        # and a finite inherited file size limit below it, soft or hard, is
        # the cap instead: a lower soft limit the caller set is kept rather
        # than raised, and a lower hard limit is one a child without
        # CAP_SYS_RESOURCE cannot raise.
        gate.STDERR_LIMIT = 33
        self.assertEqual(gate.output_cap(314), 316)
        self.assertEqual(gate.output_cap(10), 34)
        real_resource = gate.resource
        infinity = resource.RLIM_INFINITY
        for limits, expected in (
            ((200, 200), 200),
            ((infinity, 200), 200),
            ((100, 400), 100),
            ((200, infinity), 200),
            ((1024, infinity), 316),
            ((316, 316), 316),
            ((infinity, infinity), 316),
        ):
            with self.subTest(limits=limits):
                asked = []

                def getrlimit(which, limits=limits):
                    asked.append(which)
                    return limits

                gate.resource = types.SimpleNamespace(
                    getrlimit=getrlimit, RLIMIT_FSIZE=resource.RLIMIT_FSIZE, RLIM_INFINITY=infinity,
                )
                try:
                    self.assertEqual(gate.applied_cap(316), expected)
                finally:
                    gate.resource = real_resource
                self.assertEqual(asked, [resource.RLIMIT_FSIZE])

    def test_a_child_ended_by_a_signal_with_no_name_exits_3_naming_its_number(self):
        # A signal that has no name in signal.Signals, here the real-time
        # signal 40, is named by its number, never a traceback.
        self.assertNotIn(40, {member.value for member in signal.Signals})
        self.fake_extractor(extractor_with("def extract(text):\n    import os\n    os.kill(os.getpid(), 40)\n"))
        result, err = self.call_reports("extract", "x")
        self.assertEqual(result, ("exit", 3), err)
        self.assertEqual(err.splitlines(), [self.unavailable("was killed by signal 40", "extract")])

    def test_a_child_ended_by_signal_1_exits_3_naming_it(self):
        # Signal 1 (SIGHUP), the lowest signal number, is a signal end like any
        # other, reported by its name with what the child printed, never as an
        # exit. The child restores the default action first, as an ignored
        # SIGHUP (under nohup, for one) is inherited across exec.
        self.assertEqual(signal.SIGHUP.value, 1)
        self.fake_extractor(extractor_with(
            "def extract(text):\n"
            "    import os, signal\n"
            "    sys.stderr.write(\"hung up\\n\")\n"
            "    sys.stderr.flush()\n"
            "    signal.signal(signal.SIGHUP, signal.SIG_DFL)\n"
            "    os.kill(os.getpid(), signal.SIGHUP)\n"
        ))
        result, err = self.call_reports("extract", "x")
        self.assertEqual(result, ("exit", 3), err)
        self.assertEqual(err, self.unavailable("was killed by signal SIGHUP", "extract") + "; it printed: hung up\n")


class ModuleLoadTest(unittest.TestCase):
    """The gate exits 3 (unavailable), not 1 (drift), when the extractor cannot
    be run or its child fails, for each reason tested here. Row 80: each test
    runs a copy of the gate as a script, so an outcome that would end or hang
    the gate itself is observed by the test rather than suffered by it.
    Extractor code that signals the gate itself is the accepted residual, not
    an exit 3 (see
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
            # The generator and the page source the gate renders the download block from, and site/_redirects. The
            # copy's verify_page() returns the fixture page, which stands in for the generator's whole render. The
            # generator loads tools/check-install-page.py from its own folder, so the copy gets it beside it and no
            # path through the generator fails on a missing reader.
            (tools / "build-site.py").write_text(
                (MODULE_PATH.parent / "build-site.py").read_text(encoding="utf-8") + STAND_IN_RENDER, encoding="utf-8")
            shutil.copyfile(MODULE_PATH.parent / "check-install-page.py", tools / "check-install-page.py")
            (root / "fixture-render.html").write_bytes(page.read_bytes())
            source = root / "site-src" / "pages" / "verify.html"
            source.parent.mkdir(parents=True)
            shutil.copy2(MODULE_PATH.parent.parent / "site-src" / "pages" / "verify.html", source)
            (root / "site" / "_redirects").write_text(REDIRECTS, encoding="utf-8")
            skill = root / "cleanlanguage" / "skills" / "cleanlanguage" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(f"Version: {AHEAD}\n", encoding="utf-8")
            empty = root / "empty-path"
            empty.mkdir()
            # A TMPDIR inside this directory, so the temporary files of the
            # gate, which its children write to, never go to bare /tmp. A child
            # runs with an empty environment, so a temporary file it made
            # itself would not follow TMPDIR.
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
        # comparison still runs. An interrupt the extractor sends to the gate
        # is still a residual (see
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
        # A subclass of KeyboardInterrupt the extractor raises, at load or in a
        # call, exits 3 with its report. Row 80: Python ends the child with
        # SIGINT for it as for KeyboardInterrupt itself.
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
        # A KeyboardInterrupt that is also a SystemExit, at load or in a call,
        # exits 3 with its report, never the code the SystemExit carries or an
        # interrupt. Row 80: Python 3.14 ends the child for it with SIGINT, as
        # for a KeyboardInterrupt (observed), so the report names the signal
        # whatever code it carries.
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
            # The codes main absorbs as could not verify.
            ("SystemExit(2) at load", "raise SystemExit(2)\n", "exited 2"),
            ("SystemExit(3) at load", "raise SystemExit(3)\n", "exited 3"),
            ("bare SystemExit at load", "raise SystemExit\n", "did not print a JSON result"),
        ):
            with self.subTest(label):
                code, err = self.run_with_extractor(body)
                self.assertEqual(code, 3, err)
                self.assertIn(f"skill-release-date.py {reason} in baseline, so the extractor is unavailable", err)

    def test_extractor_code_run_while_reporting_a_load_failure_exits_3(self):
        # An error whose repr, str, or class name exits or raises, a SystemExit
        # whose code does, or an error outside Exception and SystemExit, still
        # exits 3 with the report, never 0 or 1. Row 80: that code runs only in
        # the child, while Python reports it.
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
        # An incomplete or incompatible extractor exits 3 naming what it lacks.
        # Row 80: a function that is missing or not callable fails the child
        # that runs it (exit 6, its NameError or TypeError relayed), and a
        # baseline that is not a bare version breaks the contract. A missing
        # release_day_from_published_at is reached only on a published release
        # (see test_extractor_attribute_gone_at_call_time), and the Malformed
        # class rows have no subject, since no extractor class reaches the
        # gate.
        internal = "failed unexpectedly (internal error)"
        version = "printed a result that does not match the contract (the value is not a bare X.Y.Z version string)"
        for label, tail, reason, detail in (
            ("missing extract", "del extract\n", f"{internal} in extract", "NameError(\"name 'extract' is not defined\")"),
            ("non-callable extract", "extract = 5\n", f"{internal} in extract", "TypeError(\"'int' object is not callable\")"),
            ("missing requires_release_date", "del requires_release_date\n", f"{internal} in requires_release_date",
             "NameError(\"name 'requires_release_date' is not defined\")"),
            ("BASELINE_VERSION not a version", "BASELINE_VERSION = 14\n", f"{version} in baseline", None),
            # An exact str that is not a bare version is refused by the gate
            # itself, even beside a baseline rule that would not reject it.
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
        # The wrapper sets a 1 second child timeout; without the child the gate
        # hangs and the outer timeout fails the test. The timeout starts only
        # once the probe has ended and the extract child is ready, so a busy
        # host cannot make it fire in the probe.
        code, err, ready = self.run_with_extractor(
            extractor_with("def extract(text):\n    import time\n" + SAY_READY + "    time.sleep(300)\n"),
            wrapper=READY_TIMEOUT_WRAPPER, inspect=lambda tools: (tools / "ready").exists(),
        )
        self.assertTrue(ready, "the extract child did not get ready")
        self.assertEqual(code, 3, err)
        self.assertIn("skill-release-date.py was not seen to end within 1 seconds in extract, "
                      "so the extractor is unavailable", err)
        self.assertIn("the gh CLI is not available", err)

    def test_a_hung_extractor_and_what_it_forked_are_killed(self):
        # A process the hung child started in its group is killed with it: once
        # the gate has exited it is gone, or a zombie where no process reaps
        # it, never still running. The child writes the pid file whole (a
        # rename) and then says it is ready, and the 1 second timeout starts
        # only then (READY_TIMEOUT_WRAPPER), so on a busy host the kill can
        # never come before the pid file exists.
        body = extractor_with(
            "def extract(text):\n"
            "    import os, subprocess, time\n"
            "    here = Path(__file__).resolve().parent\n"
            "    grandchild = subprocess.Popen([sys.executable, \"-I\", \"-c\", \"import time; time.sleep(300)\"])\n"
            "    with open(here / \"grandchild.pid.part\", \"w\", encoding=\"utf-8\") as handle:\n"
            "        handle.write(str(grandchild.pid))\n"
            "    os.replace(here / \"grandchild.pid.part\", here / \"grandchild.pid\")\n"
            + SAY_READY +
            "    time.sleep(300)\n"
        )

        def grandchild_state(tools):
            if not (tools / "ready").exists():
                raise AssertionError("the extract child did not get ready")
            pid = int((tools / "grandchild.pid").read_text(encoding="utf-8"))
            deadline = time.monotonic() + 10
            state = process_state(pid)
            while state not in (None, "Z") and time.monotonic() < deadline:
                time.sleep(0.1)
                state = process_state(pid)
            return pid, state

        code, err, (pid, state) = self.run_with_extractor(body, wrapper=READY_TIMEOUT_WRAPPER, inspect=grandchild_state)
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

    # --- SIGCHLD is reset before any child starts, or the gate exits 3 -------

    def test_an_ignored_sigchld_inherited_by_the_gate_keeps_the_verdict(self):
        # A caller that ignores SIGCHLD passes that disposition across exec,
        # which makes the kernel reap each child as it ends, so the gate
        # could never see an extractor child end and would exit 3 on every
        # run. The gate resets SIGCHLD to its default before any child, so
        # its verdict, here 2 with gh absent, is the same as with the
        # default disposition.
        launch = (
            "import os, signal, sys\n"
            "signal.signal(signal.SIGCHLD, signal.{})\n"
            "os.execv(sys.executable, [sys.executable, \"-I\", sys.argv[1]])\n"
        )
        body = EXTRACTOR_PATH.read_text(encoding="utf-8")
        for disposition in ("SIG_DFL", "SIG_IGN"):
            with self.subTest(disposition):
                code, err = self.run_with_extractor(body, wrapper=launch.format(disposition))
                self.assertEqual(code, 2, err)
                self.assertEqual(err.splitlines(), ["check-release-checksum-live: could not verify: the gh CLI is not available"])

    def test_a_sigchld_that_cannot_be_reset_exits_3_before_any_child(self):
        # The reset is refused in a thread other than the main thread
        # (ValueError); the gate then exits 3 naming it and starts no child.
        wrapper = (
            "import importlib.util, sys, threading\n"
            "spec = importlib.util.spec_from_file_location(\"gate_copy\", sys.argv[1])\n"
            "gate = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(gate)\n"
            "codes = []\n"
            "def run():\n"
            "    try:\n"
            "        codes.append(gate.main())\n"
            "    except SystemExit as stop:\n"
            "        codes.append(stop.code)\n"
            "thread = threading.Thread(target=run)\n"
            "thread.start()\n"
            "thread.join()\n"
            "sys.exit(codes[0] if codes else 70)\n"
        )
        code, err, started = self.run_with_extractor(
            logging_extractor(fail_first=False), wrapper=wrapper, inspect=lambda tools: (tools / "runs.log").exists(),
        )
        self.assertEqual(code, 3, err)
        lines = err.splitlines()
        self.assertEqual(len(lines), 1, err)
        self.assertTrue(lines[0].startswith(
            "check-release-checksum-live: could not reset SIGCHLD to its default disposition (ValueError: "
        ), err)
        self.assertTrue(lines[0].endswith("), so the end of a child could be lost"), err)
        self.assertFalse(started, "a child was started")

    # --- Row 80: the accepted same-uid residual, observed ---------------------

    def test_extractor_that_interrupts_the_gate_ends_the_gate_by_sigint(self):
        # The child runs with the uid of the gate, so extractor code can signal
        # the gate. An interrupt it sends to its parent, the gate, while the
        # gate waits ends the gate by SIGINT, with no report and none of its
        # exit codes, after the gate has killed the child. The probe sleeps
        # first, so the gate is already waiting. The probe signals its parent
        # only when one argument of that parent resolves to the gate copy that
        # run_with_extractor started, and otherwise loads as the real
        # extractor, so on a gate that runs extractor code in its own process,
        # whose parent is this test runner, the test fails instead of
        # interrupting the runner. A stop (SIGSTOP) is the same residual and is
        # not run here, as it would halt the gate.
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
        # A gate run in this suite is given a TMPDIR inside the test's own
        # temporary directory, so no temporary file of the gate, and so none
        # its child writes to, goes to bare /tmp. An audit hook records where
        # each temporary file is made.
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
        # With the open-file limit so low that the temporary files of a child
        # cannot all be created, the probe exits 3 naming the error, and the
        # gate exits 3, never a traceback (exit 1).
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

    def test_an_inherited_file_size_limit_below_the_cap_is_the_cap(self):
        # Row 100: a caller that leaves a file size limit below the cap, a
        # hard one (ulimit -H -f in a CI job, say) or a soft one with no hard
        # limit, gives the child that limit as its cap, as both its soft and
        # its hard limit, so a soft limit is kept rather than raised. The
        # child reports its limits on stderr, then writes fast, and the gate
        # exits 3 naming that cap, never a traceback.
        body = extractor_with(
            "def json_main():\n"
            "    import os, resource\n"
            "    sys.stdin.buffer.read()\n"
            "    os.write(2, (\"%d %d\" % resource.getrlimit(resource.RLIMIT_FSIZE)).encode())\n"
            "    for _ in range(16):\n"
            "        try:\n"
            "            os.write(1, b\"x\" * 65536)\n"
            "        except OSError:\n"
            "            pass\n"
            "    return 0\n"
        )
        for label, limits in (("hard", "(200, 200)"), ("soft", "(200, resource.RLIM_INFINITY)")):
            with self.subTest(label):
                wrapper = (
                    "import importlib.util, resource, sys\n"
                    f"resource.setrlimit(resource.RLIMIT_FSIZE, {limits})\n"
                    "spec = importlib.util.spec_from_file_location(\"gate_copy\", sys.argv[1])\n"
                    "gate = importlib.util.module_from_spec(spec)\n"
                    "spec.loader.exec_module(gate)\n"
                    "sys.exit(gate.main())\n"
                )
                code, err = self.run_with_extractor(body, wrapper=wrapper)
                self.assertEqual(code, 3, err)
                self.assertIn("skill-release-date.py wrote stdout up to the output cap of 200 bytes in baseline, "
                              "so the extractor is unavailable; it printed: 200 200\n", err)
                self.assertNotIn("Traceback", err)


class ControlConstantTest(unittest.TestCase):
    """Every control constant of the gate, each bound, timeout, exit code, and
    table of the extractor contract, is pinned at its shipped value, as a test
    that shortens or widens one for its own purpose cannot show that the
    shipped value is the one stated."""

    def test_the_child_bounds_keep_their_shipped_values(self):
        self.assertEqual(gate.CHILD_TIMEOUT_SECONDS, 20)
        self.assertEqual(gate.REAP_GRACE_SECONDS, 5)
        self.assertEqual(gate.RESULT_LIMIT, 65536)
        self.assertEqual(gate.ECHO_BYTES_PER_CHARACTER, 12)
        self.assertEqual(gate.STDERR_LIMIT, 4096)
        self.assertEqual(gate.EXTRACTOR_INTERNAL_ERROR, 6)

    def test_the_contract_tables_keep_their_shipped_values(self):
        self.assertEqual(gate.REPLY_KEYS, {
            "value": frozenset({"op", "outcome", "value"}),
            "absent": frozenset({"op", "outcome"}),
            "malformed": frozenset({"op", "outcome", "message"}),
        })
        self.assertEqual(gate.RELEASE_DATE_CONTRACT, {
            "extract": (gate._is_day, "a YYYY-MM-DD string", ("value", "absent", "malformed")),
            "requires_release_date": (gate._is_flag, "a JSON true or false", ("value", "malformed")),
            "release_day_from_published_at": (gate._is_day, "a YYYY-MM-DD string", ("value", "malformed")),
            "baseline": (gate._is_version, "a bare X.Y.Z version string", ("value",)),
        })


class ContractRoutingTest(unittest.TestCase):
    """Row 80: every op the gate names is in the contract, every op of the
    contract is used, and the only calls inside a function of the gate that
    start a process through an attribute of subprocess or os are in gh and in
    run_release_date_child. A start at module level, or through another name,
    an alias, or another module, is not detected."""

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


class SharedPlaceholderRuleTest(unittest.TestCase):
    """The rule of the verify page is one rule in 2 copies: this gate and check-release-links.py carry
    download_block_problems and what it reads verbatim, so the 2 gates cannot accept different pages."""

    def test_the_two_gates_carry_the_same_rule(self):
        links_path = MODULE_PATH.parent / "check-release-links.py"
        links_spec = importlib.util.spec_from_file_location("check_release_links_shared", links_path)
        links = importlib.util.module_from_spec(links_spec)
        links_spec.loader.exec_module(links)

        def definition(path: Path, name: str) -> str:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            found = [ast.dump(node) for node in tree.body
                     if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name]
            self.assertEqual(len(found), 1, path.name)
            return found[0]

        # The rule, its rendering of the download block, the reader of the parsed page and the reading of
        # site/_redirects.
        for name in ("download_block_problems", "download_block", "PageReader", "checksum_paths", "targets_checksum"):
            with self.subTest(name):
                self.assertEqual(definition(MODULE_PATH, name), definition(links_path, name))
        for name in ("PENDING_VERSION", "DISPLAYED_SUM", "PENDING_NOTE", "PUBLISHED_WORDING", "REJECTING_STEP", "HEX64",
                     "HEX_GROUPS"):
            with self.subTest(name):
                ours, theirs = getattr(gate, name), getattr(links, name)
                self.assertEqual((ours.pattern, ours.flags), (theirs.pattern, theirs.flags))
        for name in ("PLACEHOLDER", "SUM_ID", "VERIFY_URL", "GENERATOR", "BLOCK_ANCESTORS"):
            with self.subTest(name):
                self.assertEqual(getattr(gate, name), getattr(links, name))

    def test_the_paths_to_the_checksum_file_follow_each_redirect(self):
        # A path that redirects to another path to the checksum file serves it too, whatever the order of
        # the lines; a comment and a path to the zip do not.
        redirects = (
            "/sum /download/checksum/ 302\n"
            "/download/checksum https://example.com/v1/cleanlanguage-1.zip.sha256 302\n"
            "#/commented https://example.com/cleanlanguage-1.zip.sha256 302\n"
            "/download https://example.com/v1/cleanlanguage-1.zip 302\n"
        )
        self.assertEqual(gate.checksum_paths(redirects), {"/sum", "/download/checksum"})

    def test_a_value_that_is_not_a_url_reaches_nothing(self):
        self.assertFalse(gate.targets_checksum("http://[cleanlanguage.sha256", {"/download/checksum"}))


class DisplayedSumMarkupTest(unittest.TestCase):
    """The verify page's checksum element is read exactly as the generator writes it; any other form fails."""

    def test_live_markup(self):
        match = gate.DISPLAYED_SUM.search(VERIFY.format(version=CURRENT, checksum=ZIP_SUM))
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), ZIP_SUM)

    def test_extra_attributes_do_not_match(self):
        for page in (
            f'<code class="sum" id="published-checksum" hidden>{ZIP_SUM}</code>',
            f'<code id="published-checksum">{ZIP_SUM}</code>',
            f'<code id="published-checksum" class="sum">{ZIP_SUM}</code>',
            f'<code data-id="published-checksum">{ZIP_SUM}</code>',
            f'<code id="published-checksum-old">{ZIP_SUM}</code>',
        ):
            self.assertIsNone(gate.DISPLAYED_SUM.search(page), page)


class WholePageTest(unittest.TestCase):
    """The gate on a copy of the generator's inputs with the real tools/build-site.py: the committed verify page is
    the render for the version and checksum it shows, a page rendered for another version that has no published
    release (release status 404) reaches the inconsistency report, and every page form that
    test_every_listed_page_form_exits_3 lists, made on the page alone, in either state, exits 3 before any
    release is read. A page for another version that has a published release reaches the checksum step
    instead, which compares only when the gate can download and read that release's zip and .sha256, with a
    well-formed manifest that the zip hashes to; these tests do not run it."""

    NAMES = ("REPO_ROOT", "VERIFY_PAGE", "SKILL", "REDIRECTS", "GENERATOR", "release_status", "tag_status", "gh",
             "release_published_at", "release_immutable")
    SUM = "0123456789abcdef" * 4
    OTHER = "fedcba9876543210" * 4

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        copy_generator_inputs(self.root)
        (self.root / "tools").mkdir(exist_ok=True)
        shutil.copyfile(MODULE_PATH.parent / "build-site.py", self.root / "tools" / "build-site.py")
        self.page = self.root / "site/verify/index.html"
        generator_spec = importlib.util.spec_from_file_location("build_site_for_live", self.root / "tools/build-site.py")
        self.generator = importlib.util.module_from_spec(generator_spec)
        generator_spec.loader.exec_module(self.generator)
        self.version = self.generator.skill_version(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def gate_run(self) -> tuple[int, str]:
        """Run the gate on the copy in the pre-tag window, the release and its tag absent."""
        saved = {name: getattr(gate, name) for name in self.NAMES}
        gate.REPO_ROOT, gate.VERIFY_PAGE = self.root, self.page
        gate.SKILL = self.root / "cleanlanguage/skills/cleanlanguage/SKILL.md"
        gate.REDIRECTS = self.root / "site/_redirects"
        gate.GENERATOR = self.root / "tools/build-site.py"
        gate.release_status = gate.tag_status = lambda tag: 404
        gate.gh = gate.release_published_at = gate.release_immutable = unexpected_call
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                try:
                    code = gate.main()
                except SystemExit as stop:
                    code = stop.code
        finally:
            for name, value in saved.items():
                setattr(gate, name, value)
        return code, out.getvalue()

    def publish(self, checksum: str) -> str:
        """Set ``checksum`` in the copy's release.json and regenerate the copy's site, returning the verify page."""
        release_path = self.root / "site-src/release.json"
        release = json.loads(release_path.read_text(encoding="utf-8"))
        release["checksum"] = checksum
        release_path.write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.generator.main(["--root", str(self.root)]), 0)
        return self.page.read_text(encoding="utf-8")

    def test_the_committed_verify_page_is_the_render(self):
        release = json.loads((MODULE_PATH.parent.parent / "site-src/release.json").read_text(encoding="utf-8"))
        self.assertEqual((MODULE_PATH.parent.parent / "site/verify/index.html").read_bytes(),
                         gate.rendered_verify_page(release["version"], release["checksum"]))

    def test_a_page_for_another_version_reaches_the_inconsistency_report(self):
        # The render is for the version and checksum the page shows, not for release.json, so a page that the
        # generator writes for a version other than the SKILL.md version, one with no published release, is
        # still an inconsistency: exit 1 here, where no other check fails with a higher code.
        for checksum in ("0" * 64, self.SUM):
            with self.subTest(checksum[:8]):
                self.publish(checksum)
                release = {"version": BOGUS, "tag": f"v{BOGUS}", "checksum": checksum}
                self.page.write_bytes(self.generator.verify_page(self.root, release))
                code, output = self.gate_run()
                self.assertEqual(code, 1, output)
                self.assertIn(f"  - the verify page names version {BOGUS}, which has no published release\n", output)

    def test_a_checksum_close_to_the_placeholder_exits_3(self):
        # The generator refuses a checksum other than the zero placeholder with 56 or more of its 64
        # digits 0, such as a mistyped placeholder, so a page that shows one is not the render: exit 3 before any
        # release is read.
        page = self.publish(self.SUM)
        for checksum in ("0" * 63 + "1", "0" * 56 + "89abcdef"):
            with self.subTest(checksum):
                self.page.write_text(page.replace(self.SUM, checksum), encoding="utf-8")
                code, output = self.gate_run()
                self.assertEqual(code, 3, output)
                # The checksum comes from the page, not release.json, which holds SUM.
                self.assertIn(f"tools/build-site.py could not render the verify page: BuildError: the checksum "
                              f"{checksum} is not the zero placeholder but has {checksum.count('0')} of its 64 digits 0",
                              output)
                self.assertNotIn("release.json", output)

    def test_every_listed_page_form_exits_3(self):
        start_tag = '<p class="lbl blk">Step 1</p>'
        for checksum, state in (("0" * 64, "placeholder"), (self.SUM, "published")):
            page = self.publish(checksum)
            code, output = self.gate_run()
            # In the pre-tag window the render with a published checksum is an
            # inconsistency (exit 1 here, where no other check fails with a higher code), the render with the note
            # passes.
            self.assertEqual(code, 0 if state == "placeholder" else 1, output)
            if state == "published":
                self.assertIn(f"  - the verify page shows {self.SUM} as the published checksum for version {self.version}\n",
                              output)
            start, end = page.index(start_tag), page.index('<div class="next">')
            block = page[start:end]
            forms = [
                ("a step that says to install the file anyway, before the next-page link",
                 outside(page, "<p>If the values differ, install the file anyway.</p>")),
                ("a step 4 after step 3", outside(page, '<p class="lbl blk">Step 4</p>\n<p>Install the file.</p>\n')),
                ("the block inside noscript markup",
                 page[:start] + '<noscript></div><div class="doc">' + block + "</noscript>" + page[end:]),
                ("the block inside select markup",
                 page[:start] + '<select></div><div class="doc">' + block + "</select>" + page[end:]),
                ("a details element misnested in a span before step 1",
                 page[:start] + "<span><details></span>" + page[start:]),
                ("an inline script that removes the block",
                 outside(page, "<script>document.querySelector('.download').remove()</script>")),
                ("a second checksum joined by U+200B",
                 outside(page, "<p>" + "\u200b".join(self.OTHER[i:i + 8] for i in range(0, 64, 8)) + "</p>")),
                ("a second checksum joined by dots",
                 outside(page, "<p>" + ".".join(self.OTHER[i:i + 8] for i in range(0, 64, 8)) + "</p>")),
            ]
            rendered = (f"is not the page tools/build-site.py renders for version {self.version} and that checksum "
                        "from the committed sources (first at line ")
            # The shared rule refuses a double space in step 1 first, as byte equality does.
            refused = "does not carry the download block that tools/build-site.py writes for this state exactly once"
            reports = [(label, changed, rendered) for label, changed in forms] + [
                ("a double space in step 1", page.replace("<p>Download the skill.", "<p>Download the  skill.", 1),
                 refused),
                # Comments nested 400 deep before step 1 exit 3, never a traceback.
                ("comments nested 400 deep before step 1",
                 page[:start] + "<!--" * 400 + "-->" + page[start:], "nests comments too deeply to be read")]
            for label, changed, report in reports:
                with self.subTest(f"{label}, {state}"):
                    self.assertNotEqual(changed, page)
                    self.page.write_text(changed, encoding="utf-8")
                    code, output = self.gate_run()
                    self.assertEqual(code, 3, output)
                    self.assertIn(report, output)
            self.page.write_text(page, encoding="utf-8")

    def test_a_staged_draft_names_promotion_as_the_remedy(self):
        # With a draft staged under /draft/ and one nav label changed, tools/build-site.py
        # writes only site/draft/, so the correct live page is not the render; the gate exits 3, says so and names
        # promotion, and still refuses a wrong live page. Without a draft, it still says to run tools/build-site.py.
        rendered = (f"is not the page tools/build-site.py renders for version {self.version} and that checksum from "
                    "the committed sources (first at line ")
        staged = ("). site-src/site.json names base /draft/, so a draft is staged: tools/build-site.py writes only the "
                  "draft, not the live pages")
        # The advice points to the whole promotion, not only the build, 1 step of it.
        remedy = ("Promotion after the owner approves it is the remedy: the pull request of step 5 under \"Staging at "
                  "/draft/ and promotion\" in .baseline/README.md, of which tools/build-site.py --base / --promote is "
                  "1 step")
        site_json = self.root / "site-src/site.json"
        original = site_json.read_text(encoding="utf-8")
        sitemap_config = self.root / "tools/sitemap-config.json"
        original_sitemap = sitemap_config.read_text(encoding="utf-8")
        for checksum, state in (("0" * 64, "placeholder"), (self.SUM, "published")):
            with self.subTest(state):
                page = self.publish(checksum)
                wrong = outside(page, "<p>If the values differ, install the file anyway.</p>")
                self.page.write_text(wrong, encoding="utf-8")
                code, output = self.gate_run()
                self.assertEqual(code, 3, output)
                self.assertIn(rendered, output)
                self.assertIn("; run tools/build-site.py", output)
                self.assertNotIn("a draft is staged", output)
                self.page.write_text(page, encoding="utf-8")
                config = json.loads(original)
                config["base"] = "/draft/"
                next(entry for entry in config["pages"] if entry["id"] == "install")["nav_label"] = "Install it"
                site_json.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
                exclude_draft_home(self.root)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(self.generator.main(["--root", str(self.root)]), 0)
                self.assertEqual(self.page.read_text(encoding="utf-8"), page)
                self.assertTrue((self.root / "site/draft/verify/index.html").is_file())
                for label, written in (("the correct live page", page), ("a wrong live page", wrong)):
                    self.page.write_text(written, encoding="utf-8")
                    code, output = self.gate_run()
                    self.assertEqual(code, 3, f"{label}: {output}")
                    self.assertIn(rendered, output)
                    self.assertIn(staged, output)
                    self.assertIn(remedy, output)
                    self.assertNotIn("run tools/build-site.py", output)
                site_json.write_text(original, encoding="utf-8")
                sitemap_config.write_text(original_sitemap, encoding="utf-8")
                self.page.write_text(page, encoding="utf-8")


def load_faults(defined: str, renamed: str) -> list[tuple[str, object, type]]:
    """6 faults, each on its own copy of tools/build-site.py and each with the exception that the gate's LookupError
    carries as its cause: the file missing, its mode 000, its mode 000 beside a valid cached file, a syntax error, the
    definition that starts with ``defined`` changed to start with ``renamed``, and a syntax error beside a cached file
    of the unbroken source that the normal loader runs without comparing it with the source (an unchecked hash-based
    file). For each fault but the renaming, that cause is the exception the load raises; the renamed copy loads, and the
    cause is the AttributeError that the render call raises when it reads the missing name. Beside a cached file, a gate
    that always reads the source gives that cause, and one that runs the cached file in its place does not. Root reads a
    file whatever its mode, so under root the 2 mode-000 faults skip their case instead."""
    def missing(path: Path) -> None:
        path.unlink()

    @unittest.skipIf(os.geteuid() == 0, "root reads a file whatever its mode")
    def locked(path: Path) -> None:
        os.chmod(path, 0)

    @unittest.skipIf(os.geteuid() == 0, "root reads a file whatever its mode")
    def cached_locked(path: Path) -> None:
        py_compile.compile(str(path), cfile=importlib.util.cache_from_source(str(path)), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        os.chmod(path, 0)

    def broken(path: Path) -> None:
        path.write_bytes(path.read_bytes() + b"\ndef (\n")

    def rename(path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        if defined not in text:
            raise AssertionError(f"{defined!r} is not in {path.name}")
        path.write_text(text.replace(defined, renamed, 1), encoding="utf-8")

    def stale(path: Path) -> None:
        py_compile.compile(str(path), cfile=importlib.util.cache_from_source(str(path)), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        broken(path)

    name = defined.removeprefix("def ").removesuffix("(")
    return [("missing", missing, FileNotFoundError), ("with mode 000", locked, PermissionError),
            ("with mode 000 beside a valid cached file", cached_locked, PermissionError),
            ("with a syntax error", broken, SyntaxError), (f"with {name} renamed", rename, AttributeError),
            ("with a syntax error beside a stale cached file", stale, SyntaxError)]


class GeneratorLoadTest(unittest.TestCase):
    """A tools/build-site.py with each fault that load_faults() gives is a generator that cannot render, which the gate
    raises as LookupError and main() refuses with exit 3; the gate never runs a cached file in place of the source. No
    case reads the network."""

    GENERATOR = Path(__file__).resolve().parent / "build-site.py"

    def test_each_load_failure_is_a_generator_that_cannot_render(self):
        for render, defined in ((gate.download_block, "def verify_download_block("),
                                (gate.rendered_verify_page, "def verify_page(")):
            for name, fault, cause in load_faults(defined, defined.replace("(", "_unused(")):
                with self.subTest(f"{defined}: tools/build-site.py {name}"), tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "build-site.py"
                    shutil.copyfile(self.GENERATOR, path)
                    fault(path)
                    with mock.patch.object(gate, "GENERATOR", path), self.assertRaises(LookupError) as raised:
                        render(CURRENT, ZIP_SUM)
                    self.assertTrue(str(raised.exception).startswith("tools/build-site.py could not render"),
                                    raised.exception)
                    self.assertIsInstance(raised.exception.__cause__, cause)
                    # The message ends with the cause's type and text, and for an OSError that text names the
                    # generator's path, so that the refusal says which file could not be read.
                    error = raised.exception.__cause__
                    self.assertTrue(str(raised.exception).endswith(f": {type(error).__name__}: {error}"),
                                    raised.exception)
                    if issubclass(cause, OSError):
                        self.assertIn(f": '{path}'", str(raised.exception))

    def test_a_generator_that_exits_while_it_loads_cannot_render(self):
        for render in (gate.download_block, gate.rendered_verify_page):
            for code, statement, shown in ((0, "raise SystemExit(0)", "SystemExit: 0"),
                                           (1, "raise SystemExit(1)", "SystemExit: 1"),
                                           (None, "raise SystemExit", "SystemExit")):
                with self.subTest(f"{render.__name__}: {shown} at import"), tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "build-site.py"
                    path.write_bytes(self.GENERATOR.read_bytes() + f"\n{statement}\n".encode("ascii"))
                    with mock.patch.object(gate, "GENERATOR", path), self.assertRaises(LookupError) as raised:
                        render(CURRENT, ZIP_SUM)
                    self.assertTrue(str(raised.exception).startswith("tools/build-site.py could not render"),
                                    raised.exception)
                    # The message names the exception, so that the exit is never shown as a bare code or as nothing.
                    self.assertTrue(str(raised.exception).endswith(f": {shown}"), raised.exception)
                    self.assertIsInstance(raised.exception.__cause__, SystemExit)
                    self.assertEqual(raised.exception.__cause__.code, code)


# The audit hook of WorkflowPathsTest records the path of each file opened while TRACE is a list. An audit hook cannot
# be removed, so it is installed once (TRACE_HOOK_INSTALLED) and does nothing while TRACE is None, as it is outside the
# trace. No test outcome depends on installing it once: were it installed on each run, a second run of the coverage test
# in the same process would add a second hook, which records the same files again, and the test reads them as a set; so
# no test pins it.
TRACE: list[str] | None = None
TRACE_HOOK_INSTALLED = False


def trace_opens(event: str, args: tuple) -> None:
    """Record the absolute path of each file opened while TRACE is a list, and ignore every other event. No broken
    workflow or generator fails the tests only because of the isinstance test or os.fsdecode: they keep a correct
    generator from making the coverage test error, since a file opened by its descriptor (os.open, then open on the
    descriptor) gives the hook an int, which os.fsdecode refuses, and a file opened by a bytes path gives the hook
    bytes, which Path refuses unless os.fsdecode turns them into text."""
    if event == "open" and TRACE is not None and isinstance(args[0], (str, bytes, os.PathLike)):
        TRACE.append(os.path.abspath(os.fsdecode(args[0])))


class WorkflowPathsTest(unittest.TestCase):
    """.github/workflows/release-checksum-live.yml runs these tests and then the gate on a pull request or a push to
    main that changes a file they read, so its push and pull_request triggers each carry a path filter that names every
    such file: each of OWN_FILES, and each of GENERATOR_INPUTS, a directory as its path followed by /**. The daily
    schedule and manual dispatch run these tests and then the gate whatever changed, and a failing test stops the job
    before the gate runs, so a change to main that a path filter misses is still checked at the next scheduled run.
    Residuals: these tests pin both lists, but no test compares them with the sentence of the gate's module docstring
    that says what runs it, so the 2 can disagree; and GitHub may not run a path-filtered workflow for a change to more
    files than it compares, which is not checked offline."""

    WORKFLOW = MODULE_PATH.parent.parent / ".github/workflows/release-checksum-live.yml"
    # The files the gate or its tests read that GENERATOR_INPUTS does not list: the page the gate checks, the gate,
    # these tests and the workflow that runs them, the Released-line extractor the gate runs as a child, the other gate
    # whose shared functions these tests compare with the gate's, and the generator the gate renders the page with.
    OWN_FILES = ("site/verify/index.html", "tools/check-release-checksum-live.py",
                 "tools/test-release-checksum-live.py", ".github/workflows/release-checksum-live.yml",
                 "tools/skill-release-date.py", "tools/check-release-links.py", "tools/build-site.py")

    @classmethod
    def expected(cls) -> set[str]:
        """The entries each trigger must name: each of OWN_FILES, and each of GENERATOR_INPUTS, a directory as its path
        followed by /**."""
        root = MODULE_PATH.parent.parent
        return set(cls.OWN_FILES) | {f"{entry}/**" if (root / entry).is_dir() else entry for entry in GENERATOR_INPUTS}

    def path_lists(self) -> dict[str, list[str]]:
        """The entries of each path filter under the workflow's on key, by trigger and in order, read as text: a list
        starts at a line that is 4 spaces and paths:, under a trigger key indented 2 spaces, and runs to the next key, a
        line indented 4 spaces or less whose text after the indent starts with neither whitespace, # nor a hyphen. A
        line of the list whose text after the indent starts with a hyphen is an entry line. An entry line of 6 spaces, a
        hyphen, a space and an entry in double quotes is read without the quotes, and any other entry line is kept
        whole, so that it never equals an expected entry: an entry that the reader cannot read exactly, such as one
        written without quotes, fails the list test even when it names an expected entry. The reader skips a blank line,
        a comment line, a line indented more than 4 spaces and a line whose text after the indent starts with a tab, in
        a list or outside one, and a list goes on past such a line, so an entry after it is read and fails the list test
        unless it is expected. As runs show, PyYAML reads an entry after a blank line or a comment line as part of the
        list, so a blank line or a comment line between 2 expected entries passes; it cannot load the workflow when that
        line is instead a line of text indented more than 4 spaces or one whose text after the indent starts with a tab,
        which passes too when no entry that is not expected follows it. No broken workflow fails the tests only because
        of 5 of its tests. The continue after an entry line changes only how a failure is reported: without it, an entry
        line indented more than 4 spaces is skipped next, and one indented 4 spaces or less, which is kept whole and so
        fails the list test, ends the list, so that the tests also report the entries after it as missing. The length
        test makes an empty entry a failure, not an IndexError, and the test that a trigger key was read skips a paths
        key under no trigger key, which would otherwise be read under None, so that the list test could raise a
        TypeError rather than fail. The test that the section is on: is in both branches, though either alone would do,
        since each top-level key resets the trigger; without both, a list under a mistyped on key would be read.
        Residuals: the reader reads the lines of the workflow, not its YAML, so it does not see an entry that a workflow
        hides where its YAML reading differs from its line layout, and, as runs show, both tests pass while PyYAML reads
        no path list, or a list other than the one read, in each of these forms: a repeated key, such as a second on:,
        trigger or paths key, whose value PyYAML keeps in place of the first; a quoted or block scalar in place of a
        list; a key written otherwise than as the line it expects, such as one with a comment after its colon, whose
        list is not read, or is read as part of the list of the trigger before it; and a comment that holds a character
        PyYAML takes as a line break, such as U+2028, after which PyYAML reads a repeated key. How GitHub reads these
        forms is not checked offline."""
        lists: dict[str, list[str]] = {}
        section = trigger = None
        listing: list[str] | None = None
        for line in self.WORKFLOW.read_text(encoding="utf-8").splitlines():
            text = line.lstrip(" ")
            if listing is not None and text.startswith("-"):
                entry = line.removeprefix("      - ")
                listing.append(entry[1:-1] if len(entry) > 1 and entry[0] == entry[-1] == '"' else line)
                continue
            if len(line) - len(text) > 4 or text[:1].strip() in ("", "#"):
                continue
            listing = None
            if not line[0].isspace():
                section, trigger = line, None
            elif section == "on:" and line.startswith("  ") and not line.startswith("   ") and line.endswith(":"):
                trigger = line.strip().removesuffix(":")
            elif section == "on:" and trigger is not None and line == "    paths:":
                listing = lists.setdefault(trigger, [])
        return lists

    def test_each_trigger_names_exactly_the_files_the_gate_reads(self):
        """Each trigger names exactly the entries of expected(), each once, and the workflow has no paths-ignore filter,
        which could exclude a file that a list names. path_lists reads the workflow's layout, not its YAML, so an
        equivalent workflow laid out otherwise fails here until path_lists is updated. Its subtests change only how a
        failure is reported."""
        text = self.WORKFLOW.read_text(encoding="utf-8")
        lists = self.path_lists()
        self.assertEqual(sorted(lists), ["pull_request", "push"])
        for trigger in ("push", "pull_request"):
            with self.subTest(trigger):
                self.assertNotIn("paths-ignore", text)
                entries = lists[trigger]
                self.assertEqual(len(entries), len(set(entries)), f"{trigger} names an entry more than once: {entries}")
                self.assertEqual(set(entries), self.expected())

    def test_each_trigger_covers_every_file_the_render_opens(self):
        """Each trigger covers every repository file that the gate's render opens: the download block and the whole
        page, for the committed release and for the zero placeholder, rendered through the gate as it renders them,
        while an audit hook records each file opened. An entry covers the file it names, and an entry that ends in /**
        covers every file under its directory; this matcher is not GitHub's, so how GitHub matches ** under a directory
        whose name starts with a dot, as in site/.well-known/**, is not checked here. Residuals: the trace covers only
        the render, which does not run the extractor tools/skill-release-date.py, so OWN_FILES lists it by hand; a file
        that the gate reads outside the render in a whole run, such as site/_redirects and site/verify/index.html, or
        that these tests read, is pinned only by the hand-kept OWN_FILES and GENERATOR_INPUTS, so a new read of that
        kind is seen by neither test; the render runs on the committed sources, so a file that it opens only while
        site-src/site.json stages a draft is not traced; and a new generator input that a copy of GENERATOR_INPUTS can
        do without, so that WholePageTest still passes, and that neither traced render opens, is seen by neither test.
        The 2 assertIn checks do not read the workflow, so they catch no broken workflow: they make a trace that records
        neither file fail, such as one whose hook records nothing, since the loop that follows then checks nothing. The
        finally sets TRACE back to None so that the hook does nothing for the rest of the process and the trace stops
        growing; no test outcome depends on it, since the test reads the trace only to compute files and no file is
        opened between the end of the render and that computation, so no test pins it. The test checks both triggers,
        which catches no broken workflow when the list test also runs, since that test requires both lists to name the
        same entries; it is kept so that the test run alone still fails on a file missing from 1 list. The default of
        lists.get makes a trigger with no list fail on each file, not raise a TypeError. The subtests, and the sorting
        and the set that give files, change only how a failure is reported."""
        global TRACE, TRACE_HOOK_INSTALLED
        root = MODULE_PATH.parent.parent
        release = json.loads((root / "site-src/release.json").read_text(encoding="utf-8"))
        if not TRACE_HOOK_INSTALLED:
            sys.addaudithook(trace_opens)
            TRACE_HOOK_INSTALLED = True
        TRACE = []
        try:
            for checksum in (release["checksum"], "0" * 64):
                gate.download_block(release["version"], checksum)
                gate.rendered_verify_page(release["version"], checksum)
            opened = TRACE
        finally:
            TRACE = None
        files = sorted({path.relative_to(root).as_posix() for path in map(Path, opened) if path.is_relative_to(root)})
        self.assertIn("tools/build-site.py", files)
        self.assertIn("site-src/pages/verify.html", files)
        lists = self.path_lists()
        for trigger in ("push", "pull_request"):
            for relative in files:
                with self.subTest(f"{trigger}: {relative}"):
                    self.assertTrue(any(entry == relative or (entry.endswith("/**") and relative.startswith(entry[:-2]))
                                        for entry in lists.get(trigger, ())), f"no {trigger} entry covers {relative}")


if __name__ == "__main__":
    unittest.main()
