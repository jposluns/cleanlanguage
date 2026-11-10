#!/usr/bin/env python3
"""Fail if the site's published checksum does not match the released asset.

``check-release-links.py`` proves the displayed checksum is well formed and
internally consistent, but deliberately fetches nothing. This companion closes
that gap over the network: it confirms the checksum shown on the verify page is
the true SHA-256 of the published release asset for the version the site names.

It is the machine-visible completion signal for a release. The release workflow
publishes the assets and stops; the orchestrator flips the site checksum out of
band under a user token (see the release runbook), matching the rest of the
fleet, which keeps pull request authorship out of Actions. If that flip is
forgotten or wrong, a release run still goes green, so without this check the
site could show a stale checksum indefinitely with nothing to surface it. This
check goes red on drift between the site and the published release, and also
when it cannot verify the release; the Exit codes entries below state each
condition that turns it red and its code. It runs in CI on a pull request or a
push to main that changes a file it or its tests read, which the workflow's
path filters name, on a daily schedule and on manual dispatch, and the
orchestrator runs it as the final step of the runbook. GitHub may not run a
path-filtered workflow for a change to more files than it compares, which is
not checked offline; the daily schedule still runs the gate on main.

Behaviour:
  - Reads the version and displayed checksum from ``site/verify/index.html``.
    While ``site-src/release.json`` holds the zero placeholder of a version
    bump, the page shows no checksum and says that it appears once the
    version is published; the version is read from that note and the site
    checksum is taken as the placeholder. When that version has a published
    release whose zip and ``.sha256`` the gate can download and read, with a
    well-formed manifest that the zip hashes to, the page fails as drift.
    When the release is published but the gate cannot download or read those
    assets, the manifest is malformed or the zip does not hash to it, or
    when the release status cannot be read or is neither 200 nor 404, the
    comparison cannot run and reports no drift. Exit codes below gives the
    code for each outcome. With no published release (status 404), the page
    is held to the rules for an unpublished release below, which pass only
    in the pre-tag window. Without the note, the version is read from the
    first sentence that names the published checksum's version and the
    checksum from the first checksum element. The gate is whole-page
    equality: the page must equal, byte for byte, the page that
    ``tools/build-site.py`` renders at base /
    from the committed sources for that version, its tag and that checksum or
    the placeholder (rendered_verify_page, verify_page), whatever version
    SKILL.md names, as ``tools/check-release-links.py`` requires of the same
    page for ``release.json``. The page it reads is ``site/verify/index.html``
    of the checked-out commit, not the deployed site, so the gate fetches no
    page of https://cleanlanguage.ai/, and a deploy that Cloudflare Pages has
    not finished cannot fail the push run of the commit it deploys. Any other
    page is refused, whatever it adds, removes or hides: a contradicting step,
    markup such as ``noscript``, ``select`` or a misnested ``details`` around
    or before the download block, an inline script, or a second checksum in
    any form, its groups joined by U+200B or by dots included. So does a page
    that a browser shows the same way, such as one with a double space in
    step 1 or with the html element's attributes in another order: the
    committed page is always the generator's render, so the remedy is to run
    ``tools/build-site.py``. While ``site-src/site.json`` names a base other
    than /, a draft is staged: ``tools/build-site.py`` writes only the draft,
    not the live pages, and the gate still renders this page at base / from
    the sources, the draft's changes included. So a correct live page that
    the draft renders differently is refused, and running
    ``tools/build-site.py`` cannot clear it; the report then says that a
    draft is staged and that promotion, after the owner approves it, is the
    remedy (staged_draft, draft_advice): the pull request of step 5 under
    "Staging at /draft/ and promotion" in ``.baseline/README.md``, of which
    ``tools/build-site.py --base / --promote`` is 1 step. Every page that is
    not the render is refused, whether or not a draft is staged. For a clearer
    report, the gate first
    applies the rule that ``tools/check-release-links.py`` also applies
    (download_block_problems), and reports the equality only for a page that
    keeps it: the page carries the download block that ``tools/build-site.py``
    renders for that version and checksum (download_block) exactly once, byte
    for byte, where build() writes it, and no other part of the page,
    comments, scripts and hidden elements included, carries the checksum
    element's id, the class ``sum``, the not-yet-published note, "published
    checksum" wording, a 64 digit hexadecimal value (in its text, also in
    groups split by whitespace, hyphens or colons), a link to a ``.sha256``
    file or to a path that ``site/_redirects`` sends there, or a step that
    tells the reader not to install the file. A page whose comments nest too
    deeply for the rule's reader breaks the rule too, never an uncaught
    RecursionError. ``site/_redirects`` is a
    required file in either state. A page that is not the render or breaks the
    rule, or shows the placeholder as the published checksum, is refused
    before any release is read, and the gate also stops there when the
    generator cannot render the block or, for any reason it refuses a build,
    the page. A page that passes is the
    render, so it shows the checksum it was read by in its checksum element,
    or the note for the zero placeholder; when the gate can download and
    read the published release's zip and ``.sha256``, with a well-formed
    manifest that the zip hashes to, the comparison below holds that
    checksum, or the placeholder, to the published one.
  - The equality holds the page to the generator, not the generator to what
    it should write. A change to ``site-src/pages/verify.html``, to the
    generator code that renders the page, or to what its head loads, made in
    the sources and regenerated, is refused above, before any release is
    read, only when it fails one of the checks above, such as the check that
    the page carries the not-yet-published note or a checksum element and the
    sentence that names its version (which deleting ``{{release.sum_block}}``
    from ``site-src/pages/verify.html`` fails) or the rule above
    (download_block_problems), which a plain 64 digit hexadecimal value added
    before the next-page link breaks. Any other such
    change passes these checks of the page, as a second checksum in the page
    source whose groups are joined by dots does, and as a zip file name for
    another version written in place of the current one does.
    ``tools/test-build-site.py`` pins the whole rendered page in each state
    (VERIFY_PAGE_PIN) and the site's own stylesheet (SITE_CSS_PIN), so a
    change to the page as rendered for the stand-in release, or to that
    stylesheet, fails there until the pin is updated on purpose. The pin
    holds the page as rendered for a stand-in release (PIN_VERSION,
    PIN_CHECKSUM) and the stand-in date PIN_DATE, and the same test requires
    the render for ``site-src/release.json`` at the
    ``modified`` dates in ``site-src/site.json``, which
    ``tools/check-release-links.py`` requires this page to be, and the render
    for that version with the checksum "a" * 64 and the verify page's
    ``modified`` date 2099-12-31, to be the pinned rendering of the same
    state with the stand-in values replaced (check_committed_render). A
    generator change that renders differently only for sets of release
    values and date that none of these renders uses passes the pin, that
    comparison and, once regenerated, these checks of the page, until the
    committed ``release.json`` and verify page ``modified`` date become a set
    it renders differently for; the test runs on every pull request and push
    to ``main`` (``site-draft.yml``), so it fails then.
    ``tools/check-release-links.py`` names the
    stylesheet and script files the page loads and the gate that pins each.
  - If the release ``vX`` for that version is not published yet, the pass is
    conditional. The site is ahead of the release in the one state this gate
    passes only when it names the current skill version (``Version:`` in
    ``cleanlanguage/skills/cleanlanguage/SKILL.md``), the page carries the
    not-yet-published note, and the tag ``vX`` does not exist yet, which is the
    pre-tag window the release runbook creates. In that window the SKILL.md
    ``Released:`` line is still checked, with no further network call: a
    malformed line exits 3, and a line missing above the undated baseline
    fails. Before the tag, no checksum for the version is published, so a page
    that shows a well-formed checksum as published there (the previous
    version's digest or a locally built one passed to
    ``tools/set-release-links.py``) is an inconsistency and fails, the Released
    line still checked and the more severe code winning.
    ``tools/build-site.py`` refuses a checksum close to the zero placeholder
    (56 or more of its 64 digits 0), such as a mistyped placeholder, so a page
    that shows one is not the render and is refused before any release is read.
    A different version with no release is a real inconsistency and fails. An
    existing tag with no published release is a deleted or unfinished release
    and reads as unverifiable, as does a release or tag status that cannot be
    read or is neither 200 nor 404; on each such path the SKILL.md
    ``Released:`` line is still checked with no further network call, and the
    more severe code wins. When the release status of the version the site
    names cannot be read, or is neither 200 nor 404, and SKILL.md names a
    different version, the release-date check below probes the release SKILL.md
    names instead. One broken state stays invisible to this check: a bump that
    updated both the verify page and SKILL.md but whose tag was never pushed is
    indistinguishable from the pre-tag window by repository state alone.
  - If the release exists, downloads the version-named zip and its ``.sha256``,
    proves the release is self-consistent (the zip hashes to its own manifest),
    and requires the site's displayed checksum, or the placeholder while the
    page carries the note, to equal that published digest: a difference is
    drift. A download or read that fails, a malformed manifest or a zip that
    does not hash to it stops only this comparison, and the release-date
    check below still runs.
  - Separately, and whatever version the site names, checks the release for
    the version SKILL.md names on its own terms (item 26): it probes that
    release; on 200 it requires the SKILL.md ``Released:`` line to name the
    UTC day of the release ``published_at`` record and requires the release
    record to be immutable (``immutable`` exactly true, so its assets and
    record cannot have been replaced since publication); on 404 it checks the
    tag exactly as the same-version path does, so only a confirmed absent tag
    means the release is not published yet and the date comparison is skipped
    (a line missing above the undated baseline still fails there, as in the
    pre-tag window), while an existing tag, or a tag whose status cannot be
    read or is neither 200 nor 404, cannot be verified; any other release
    status cannot be verified. The line may be absent only when that version
    is at or below the undated baseline declared in
    ``tools/skill-release-date.py``; the line and that rule are read first,
    and then no network call is made for the date check at all. An undated
    release at or below that baseline is therefore not checked for
    immutability either. The meaning of ``published_at`` is an assumption,
    isolated in ``release_day_from_published_at`` in that tool; see its
    docstring.

Requires the ``gh`` CLI and, in CI, ``GH_TOKEN`` with ``contents: read``.

Exit codes:
  0  every check that ran passed: the site checksum matches the published
     release and the release-date check of the version SKILL.md names
     passes, or the site is ahead of an unpublished release in the pre-tag
     window (it names the current skill version and carries the
     not-yet-published note, the tag does not exist yet, and the SKILL.md
     Released line is well formed, and present above the undated baseline)
  1  drift or inconsistency: the release is published, the gate can
     download and read its zip and ``.sha256``, the manifest is well formed
     and the zip hashes to it, and the site shows a different checksum or
     says that the checksum is not yet published, or the site names an
     unreleased version that is not the current skill version, or it shows
     a checksum as published while the release and its tag do not exist,
     or the SKILL.md Released date disagrees with
     the published release, or the Released line is missing above the undated
     baseline (also in the pre-tag window)
  2  could not verify: a gh or network error; a status other than 200 or 404
     for the release the site names, for the release SKILL.md names, or for
     a tag the gate reads; a tag that exists with no published release; a
     published release whose zip or ``.sha256`` the gate cannot download or
     read, whose manifest is malformed, or whose zip does not hash to its
     manifest; or a published release whose ``published_at`` is unreadable
     or malformed or whose ``immutable`` field is not exactly true
  3  a required file could not be read, the verify page is not the page the
     generator writes for the state it shows, or the generator could not
     render its download block or the page (see Behaviour), the SKILL.md
     Released line is
     malformed, a call of tools/skill-release-date.py, which runs in a
     child process, did not give a result the gate could accept (see
     run_release_date_child), or SIGCHLD could not be reset to its default
     disposition (see reset_sigchld)

When the verify page passes its own checks and the release it names is
published, the release-date check and the site-checksum comparison both run,
and each reports any failure it finds, also when the comparison stops because
the download fails, the downloaded assets cannot be read, or the manifest is
malformed or undecodable. When that release returns a status other than 200 or
404, or a status that cannot be read while SKILL.md names a different version,
and when the site names an unreleased version that is not the current skill
version, the comparison does not run: the gate reports a release it could not
verify, or the inconsistency, and the release-date check still runs and reports
any failure it finds. So neither failure hides the other. Within the date check
of a published release, a Released line missing above the undated baseline does
not hide an immutable field that is not exactly true: both are reported and the
more severe 2 wins. The extractor is probed inside main, not at import, so a
probe that ends in exit 3 is reported and contributes 3 while the checksum
comparison still runs and reports. The gate then exits with the most severe
code, the highest one (3 over 2 over 1 over 0), since 2 and 3 mean a check
could not complete.

Before it starts any child, main resets SIGCHLD to its default
disposition (reset_sigchld), because an ignored SIGCHLD, inherited across
exec from the caller, makes the kernel reap each child as it ends, so the gate
could not see an extractor child end, and the exit status of a gh child would
be lost. The verdict therefore does not depend on that inherited state; when
the reset fails, the gate exits 3 before it starts any child.

The extractor runs in a separate python3 -I child for each call
(run_release_date_child), so extractor code never runs in this process, and
what it does to its own process, such as exiting, raising, rewriting a
global, or signalling itself, acts on the child. The timeout applies to each
child: a gate run starts several children, and the gate waits for each child
for up to CHILD_TIMEOUT_SECONDS and then, after a kill, for up to
REAP_GRACE_SECONDS more before it reaps the child, so these waits can hold
the gate for up to their sum on each call (the residual below is outside
these bounds). The gate takes a result from a child only when the child
exits 0 and prints exactly one JSON object that matches the contract, and
it reads only a bounded part of what the child prints (see RESULT_LIMIT).
While the child runs, an ordinary write cannot grow any one file it writes
past its cap: output_cap(limit) bytes, one byte past the larger read bound,
or a lower file size limit the caller set, soft or hard (applied_cap). The
cap is RLIMIT_FSIZE, set in the child before exec as both its soft and its
hard limit, so a child without CAP_SYS_RESOURCE, and any process it starts
without it, cannot raise it. After the wait, a child whose stdout or stderr
has a final size that reached that cap, including a lower limit the caller
set, is unavailable, and the reason names that cap. Residuals: RLIMIT_FSIZE
limits the logical size of a file, not the disk space allocated to it, so
deliberate child code can reserve disk blocks past the end of a file (with
fallocate, for example) without growing it; the cap is not compared with
the free space of the file system, so a file below the cap can still run
out of space; the check reads only the final size, so a child that fills
stdout to the cap, truncates it and writes a valid reply is accepted; the
cap applies to each file, not to their total, so a child can write any
number of files, each up to the cap; the cap limits how far a write can
extend a file, so a file already larger than the cap keeps its size and
its content can still be changed;
a child, or a process it starts, that holds CAP_SYS_RESOURCE (as a gate
run as root gives it) can raise the hard limit and then the soft one, so
the cap holds only until it raises it; and its stdin file has the same cap
but is not checked, so a child that fills it and still replies validly
keeps its verdict.
Every other outcome of a child that the gate observes exits 3 with its
report, never 2, 1, or 0. On a normal end and on a timeout, the gate kills
the process group of the child before it reaps the child, or exits 3 when it
cannot; on the other paths described in run_release_date_child it may
not. The gate reaps a child only once it has seen that child end, and when
it sees no end within REAP_GRACE_SECONDS of a kill, it exits 3 and leaves
the child unreaped. A process the child started is killed with the group
only while it is in the group: a process that leaves the child's process
group, by any means, can outlive the gate.
Separation is not a sandbox. The child runs with the uid, filesystem, and
network of the gate, so extractor code can do whatever that uid can do,
including writing files, reaching the network, and signalling the gate.
While the child runs, its ordinary writes cannot grow any one file past its
cap, except as the residuals above state, but the child can still reserve
disk blocks past the end of a file, create any number of files and write
to each up to the cap, and use CPU and memory. A signal
it sends to the gate acts on the gate as that signal acts on any process:
it can interrupt, stop, or end the gate outside the exit codes above, and
no bound of the gate limits its effect.
More generally, extractor code can act on the gate and on its own children
through the uid, by signals, tracing, resource limits, or any other means
that uid has, and so can hold, stop, or end the gate, or keep from the gate
what a child does, beyond any bound of the gate and outside the exit codes
above. A report of the gate states what the gate saw, which such action can
make differ from what the child did. If the gate is killed while it waits,
the child, in its own session, can be left running. Each call reads the
extractor file afresh, so a file replaced during a run can give different
calls different code. The extractor remains the authority on content, so
changed extractor code that returns a wrong but well-formed answer, or
classifies a value as malformed, is not detectable here, as it never was;
the stderr the gate relays on a failure is extractor-controlled text, as the
error text it reported was before.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import resource
import signal
import stat
import subprocess
import sys
import tempfile
import time
import types
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERIFY_PAGE = REPO_ROOT / "site" / "verify" / "index.html"
REDIRECTS = REPO_ROOT / "site" / "_redirects"
SKILL = REPO_ROOT / "cleanlanguage" / "skills" / "cleanlanguage" / "SKILL.md"
REPO = "jposluns/cleanlanguage"

# The verify page's checksum element exactly as tools/build-site.py writes it, from which the gate reads the
# checksum and the version that select the download block it requires (download_block_problems).
DISPLAYED_SUM = re.compile(r'<code class="sum" id="published-checksum">([^<]*)</code>')
DISPLAYED_VERSION = re.compile(r"published checksum for version ([0-9][0-9.]*) is")
# The verify page's note while site-src/release.json holds the zero placeholder (tools/build-site.py, sum_tokens).
PENDING_VERSION = re.compile(r"The checksum for version ([0-9][0-9.]*) appears here once that version is published; "
                             r"compare the checksum of your file with it then\.")
PLACEHOLDER = "0" * 64
# What download_block_problems refuses outside the download block, as tools/check-release-links.py reads it, and the
# address of the verify page, against which it resolves a relative link.
PENDING_NOTE = re.compile(r"appears\s+here\s+once\s+that\s+version\s+is\s+published", re.I)
PUBLISHED_WORDING = re.compile(r"published\s+checksum", re.I)
REJECTING_STEP = re.compile(r"\bdo\s+not\s+install\b|\bdon['’]t\s+install\b", re.I)
HEX64 = re.compile(r"[0-9a-fA-F]{64}")
# A 64 digit hexadecimal value in the page's text, whole or in groups split by whitespace, hyphens or colons.
HEX_GROUPS = re.compile(r"[0-9a-fA-F](?:[\s:-]*[0-9a-fA-F]){63}")
SUM_ID = "published-checksum"
VERIFY_URL = "https://cleanlanguage.ai/verify/"
# The generator, which renders the download block (download_block), and the elements build() writes around that
# block on the verify page, each with its attributes: html, body, main, the wrap div and the source's doc div.
GENERATOR = Path(__file__).resolve().parent / "build-site.py"
BLOCK_ANCESTORS = (
    ("html", (("lang", "en"), ("class", "site-cleanlanguage"))),
    ("body", ()),
    ("main", (("id", "main-content"),)),
    ("div", (("class", "wrap"),)),
    ("div", (("class", "doc"),)),
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SKILL_VERSION = re.compile(r"^Version:[ \t]*([0-9]+\.[0-9]+\.[0-9]+)[ \t]*$", re.M)
VERSION_LINE = re.compile(r"^Version:[^\n]*", re.M)

# The one shared strict Released-line extractor (item 26), run as a separate
# python3 -I child with a JSON request and reply (see run_release_date_child)
# so this gate applies the same grammar, the same baseline, and the same single
# published_at interpretation as every other caller.
RELEASE_DATE_TOOL = Path(__file__).resolve().parent / "skill-release-date.py"

# Row 80: the bounds on one extractor child. CHILD_TIMEOUT_SECONDS applies to
# each child separately (see the module docstring); on a timeout the gate
# kills the process group of the child where it can, and exits 3. After a
# kill, the gate waits at most REAP_GRACE_SECONDS to see the child end before
# it reaps it, and exits 3, leaving it unreaped, when it sees no end, so no
# reap blocks the gate. Of what the child prints, the gate reads at most
# STDERR_LIMIT bytes of stderr and 1 byte more than the stdout bound, which is
# RESULT_LIMIT bytes plus ECHO_BYTES_PER_CHARACTER bytes for each character of
# the request argument, so a longer stdout is refused and the memory a reply
# takes stays bounded by the request the gate already holds.
# ECHO_BYTES_PER_CHARACTER is the most bytes one character can take through
# repr and then ASCII JSON (a printable character outside the basic plane
# becomes a surrogate pair of 2 \uXXXX escapes, 12 bytes); the allowance is
# there so that a malformed message that echoes the argument keeps its verdict
# (see test_an_echoed_request_of_any_size_keeps_its_verdict). Row 100: while
# the child runs, an ordinary write cannot grow a file past
# applied_cap(output_cap(limit)) bytes (RLIMIT_FSIZE, soft and hard), and
# after the wait a stdout or stderr file whose final size, checked with fstat,
# reached the cap exits 3 naming the cap (see the module docstring for what
# this does not bound).
CHILD_TIMEOUT_SECONDS = 20
REAP_GRACE_SECONDS = 5
RESULT_LIMIT = 65536
ECHO_BYTES_PER_CHARACTER = 12
STDERR_LIMIT = 4096

# The exit code of an internal failure of the extractor itself.
EXTRACTOR_INTERNAL_ERROR = 6

DAY_FORM = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
BASELINE_FORM = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


def _is_day(value) -> bool:
    return type(value) is str and DAY_FORM.fullmatch(value) is not None


def _is_flag(value) -> bool:
    return type(value) is bool


def _is_version(value) -> bool:
    return type(value) is str and BASELINE_FORM.fullmatch(value) is not None


# The JSON contract of the extractor --json mode: for each op, the check its
# value must pass, what that check requires (for the report), and the outcomes
# the op may reply with. Types are checked by identity, so 0, 1, or "true" is
# never read as a bool.
RELEASE_DATE_CONTRACT = {
    "extract": (_is_day, "a YYYY-MM-DD string", ("value", "absent", "malformed")),
    "requires_release_date": (_is_flag, "a JSON true or false", ("value", "malformed")),
    "release_day_from_published_at": (_is_day, "a YYYY-MM-DD string", ("value", "malformed")),
    "baseline": (_is_version, "a bare X.Y.Z version string", ("value",)),
}

# The exact key set of a reply with each outcome.
REPLY_KEYS = {
    "value": frozenset({"op", "outcome", "value"}),
    "absent": frozenset({"op", "outcome"}),
    "malformed": frozenset({"op", "outcome", "message"}),
}


def _unavailable(message: str) -> None:
    print(f"check-release-checksum-live: {message}", file=sys.stderr)
    raise SystemExit(3)


class ReleaseDateMalformed(Exception):
    """The extractor's ``Malformed`` verdict on content, re-raised under a
    class this gate owns, so no caller looks the extractor class up."""


class _RepeatedKey(Exception):
    """A JSON object in a reply names one key more than once."""


def _object_without_repeated_keys(pairs: list) -> dict:
    """Build a JSON object from its ``pairs``, refusing a repeated key, so
    a reply is never read with the last of two values winning."""
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise _RepeatedKey()
    return dict(pairs)


def _wait_unreaped(proc: subprocess.Popen, timeout: float) -> bool:
    """Wait up to ``timeout`` seconds for the child ``proc`` to end, without
    reaping it (os.waitid with WNOWAIT), so neither its pid nor the group id
    it leads can be reused while the gate may still signal them. Returns
    True when the child has ended and False on a timeout. WNOHANG with a
    short sleep bounds the wait, as Popen.wait does with a timeout."""
    deadline = time.monotonic() + timeout
    delay = 0.0005
    while os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG) is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        delay = min(delay * 2, remaining, 0.05)
        time.sleep(delay)
    return True


def _reap(proc: subprocess.Popen) -> str | None:
    """Reap the child ``proc`` once the gate sees it end, waiting at most
    REAP_GRACE_SECONDS for that with the same non-blocking poll as the main
    wait (_wait_unreaped), so the reap never blocks the gate. Returns None
    once the child is reaped, or the reason when the gate saw no end within
    that grace; the child is then left unreaped."""
    if not _wait_unreaped(proc, REAP_GRACE_SECONDS):
        return (
            f"could not be reaped (the gate saw no end of it within "
            f"{REAP_GRACE_SECONDS} seconds after its kill)"
        )
    proc.wait()
    return None


def _kill_group(proc: subprocess.Popen, ended: bool) -> str | None:
    """Kill the process group of the child ``proc``, which has not been
    reaped yet, so neither its pid nor the group id it leads can have been
    reused, and then reap the child (see _reap); ``ended`` is whether the
    child has already ended. Returns None, or the reason when the group
    could not be killed or the child could not be reaped: when the group
    could not be killed, the gate tries to kill the child itself when
    ``ended`` is false, and reaps the child only when it has ended or that
    kill succeeded, so it never waits on a child it could not kill."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as error:
        problem = f"could not kill the process group of its child ({type(error).__name__}: {error})"
        if not ended:
            try:
                os.kill(proc.pid, signal.SIGKILL)
            except OSError:
                proc.poll()
                return problem
        unreaped = _reap(proc)
        return problem if unreaped is None else f"{problem}, and {unreaped}"
    return _reap(proc)


def output_cap(limit: int) -> int:
    """The size limit, in bytes, on each file the child writes, under
    ordinary writes: one byte past the larger of the two read bounds
    (``limit + 1`` bytes of stdout and STDERR_LIMIT bytes of stderr), so a
    reply one byte too long is still read and refused as too long. An
    ordinary write cannot extend a file past the cap. For what the cap
    does not bound, see the residuals in the module docstring."""
    return max(limit + 1, STDERR_LIMIT) + 1


def applied_cap(cap: int) -> int:
    """The file size limit the child gets, as both its soft and its hard
    limit: the lowest of ``cap``, a finite inherited soft limit and a
    finite inherited hard limit. A lower soft limit the caller set is kept
    for the child rather than raised, and a lower hard limit is one that a
    process without CAP_SYS_RESOURCE cannot raise."""
    soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    for inherited in (soft, hard):
        if inherited != resource.RLIM_INFINITY and inherited < cap:
            cap = inherited
    return cap


def run_release_date_child(op: str, arg: str | None = None) -> dict:
    """Run the extractor once, as ``skill-release-date.py --json`` under
    ``sys.executable -I``, for the op ``op`` with ``arg``, and return its
    reply, checked against the contract (RELEASE_DATE_CONTRACT and
    REPLY_KEYS).

    The child gets an empty environment, the tool directory as its working
    directory, and its own session, so it leads a process group of its own.
    The request is written to a temporary file that is its stdin, and its
    stdout and stderr go to temporary files, so the gate never blocks on a
    pipe and reads only a bounded part of each. While the child runs, an
    ordinary write cannot grow any file it writes past
    applied_cap(output_cap(limit)) bytes, which is lower than
    output_cap(limit) when the caller set a lower file size limit
    (RLIMIT_FSIZE, set by limit_output before exec as both its soft and
    its hard limit), and after the wait a stdout or stderr file whose
    final size, checked with fstat, reached that cap exits 3 naming that
    cap before the exit code is read. The module docstring lists what the
    cap and this check do not bound. The wait, bounded by
    CHILD_TIMEOUT_SECONDS for this
    child, leaves the child unreaped. On a normal end and on a timeout, the
    process group of the child is then killed before the child is reaped,
    or the call exits 3 when the group cannot be killed; on the other
    paths this docstring describes it may not
    be. The child is reaped only once the gate sees it end, and when the
    gate sees no end within REAP_GRACE_SECONDS of the kill, the call exits 3
    and leaves the child unreaped (see _reap). A process the child started
    is killed with the group only while it is in the group, so a process
    that leaves the child's process group, by any means, can outlive the
    gate. A wait that reports the child is no longer a child of the gate
    (ChildProcessError) signals nothing, as its pid may be reused, and
    exits 3.

    This function returns only a reply from a child that exits 0 and whose
    stdout, within the bound (see RESULT_LIMIT), is exactly one ASCII JSON
    object, with no key repeated, that matches the contract. When it does
    not return, it exits 3 as unavailable, naming the reason and relaying at
    most STDERR_LIMIT bytes of the child stderr, or an exception passes
    through it; it never gives a content verdict, a pass, or a drift for any
    other outcome. Every Exception raised while the gate prepares, starts,
    waits for, kills, reaps, or reads its child exits 3 that way.

    A BaseException that is not an Exception, such as a KeyboardInterrupt,
    is not caught that way. When one reaches the gate while it waits, the
    gate kills the group and reaps the child before it passes on, or exits 3
    when the group cannot be killed or the child cannot be reaped; one
    raised anywhere else, including during that kill, passes on at once,
    and a child already started may then be left unkilled, unreaped, or
    both."""

    def fail(reason: str, printed: bytes = b"") -> None:
        message = f"{RELEASE_DATE_TOOL.name} {reason} in {op}, so the extractor is unavailable"
        shown = printed.decode("utf-8", errors="replace").strip()
        if shown:
            message += f"; it printed: {shown}"
        _unavailable(message)

    executable = sys.executable
    if not executable or not os.path.isabs(executable):
        fail(f"could not run (the interpreter path {executable!r} is not absolute)")
    request = {"op": op} if arg is None else {"op": op, "arg": arg}
    limit = RESULT_LIMIT + ECHO_BYTES_PER_CHARACTER * (0 if arg is None else len(arg))
    try:
        cap = applied_cap(output_cap(limit))

        def limit_output() -> None:
            # Runs in the child, before exec: an ordinary write cannot grow a
            # file past cap; the module docstring lists what the cap does
            # not bound. The cap is the hard limit too, so a child
            # without CAP_SYS_RESOURCE, or a process it starts without it,
            # can neither raise the soft limit past the cap nor raise the
            # hard limit.
            # The gate has no threads (it imports no threading, and
            # reset_sigchld already requires the main thread), so a
            # preexec_fn is safe here.
            resource.setrlimit(resource.RLIMIT_FSIZE, (cap, cap))

        with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as stdout, \
                tempfile.TemporaryFile() as stderr:
            stdin.write(json.dumps(request, ensure_ascii=True).encode("ascii"))
            stdin.seek(0)
            try:
                proc = subprocess.Popen(
                    [executable, "-I", str(RELEASE_DATE_TOOL), "--json"],
                    stdin=stdin, stdout=stdout, stderr=stderr, env={},
                    cwd=RELEASE_DATE_TOOL.parent, start_new_session=True,
                    preexec_fn=limit_output,
                )
            except OSError as error:
                fail(f"could not run ({type(error).__name__}: {error})")
            try:
                ended = _wait_unreaped(proc, CHILD_TIMEOUT_SECONDS)
            except ChildProcessError:
                # The child is no longer a child of the gate, so its pid and
                # group id may already be reused: neither is signalled.
                raise
            except BaseException:
                problem = _kill_group(proc, ended=False)
                if problem is not None:
                    fail(problem)
                raise
            problem = _kill_group(proc, ended)
            if problem is not None:
                fail(problem)
            stderr.seek(0)
            printed = stderr.read(STDERR_LIMIT)
            stdout.seek(0)
            data = stdout.read(limit + 1)
            capped = [name for name, handle in (("stdout", stdout), ("stderr", stderr))
                      if os.fstat(handle.fileno()).st_size >= cap]
    except Exception as error:
        # An Exception from the machinery of the gate itself exits 3, never
        # a traceback read as drift (exit 1); a BaseException that is not an
        # Exception, SystemExit from fail among them, passes through.
        fail(f"could not be run, waited for, or read ({type(error).__name__}: {error})")
    if capped:
        fail(f"wrote {' and '.join(capped)} up to the output cap of {cap} bytes", printed)
    code = proc.returncode
    if not ended:
        # Only what the gate saw is reported: it saw no end of the child
        # within the timeout, which is not proof that the child was running.
        fail(f"was not seen to end within {CHILD_TIMEOUT_SECONDS} seconds", printed)
    if code < 0:
        try:
            name = signal.Signals(-code).name
        except ValueError:
            name = str(-code)
        fail(f"was killed by signal {name}", printed)
    if code == EXTRACTOR_INTERNAL_ERROR:
        fail("failed unexpectedly (internal error)", printed)
    if code != 0:
        fail(f"exited {code}", printed)
    if len(data) > limit:
        fail(f"printed more than {limit} bytes", printed)

    def breach(rule: str) -> None:
        fail(f"printed a result that does not match the contract ({rule})", printed)

    try:
        reply = json.loads(data.decode("ascii"), object_pairs_hook=_object_without_repeated_keys)
    except _RepeatedKey:
        breach("a key appears more than once")
    except (ValueError, RecursionError):
        fail("did not print a JSON result", printed)
    if type(reply) is not dict:
        breach("not a JSON object")
    outcome = reply.get("outcome")
    if type(outcome) is not str or outcome not in REPLY_KEYS:
        breach("its outcome is not value, absent, or malformed")
    if set(reply) != REPLY_KEYS[outcome]:
        breach(f"a result with outcome {outcome} has exactly the keys {', '.join(sorted(REPLY_KEYS[outcome]))}")
    if type(reply["op"]) is not str or reply["op"] != op:
        breach(f"it answers an op other than {op}")
    check, expected, outcomes = RELEASE_DATE_CONTRACT[op]
    if outcome not in outcomes:
        breach(f"{outcome} is not a result of {op}")
    if outcome == "value" and not check(reply["value"]):
        breach(f"the value is not {expected}")
    if outcome == "malformed" and type(reply["message"]) is not str:
        breach("the message is not a string")
    return reply


def release_date_call(name: str, *args):
    """Run the extractor op ``name`` with ``args`` in a child of its own (see
    run_release_date_child) and map its reply: a ``value`` reply returns the
    value, an ``absent`` reply returns None, and a ``malformed`` reply, the
    extractor's ``Malformed`` verdict on content, is raised as
    ``ReleaseDateMalformed`` with its message. run_release_date_child
    returns only a reply that matches the contract, so no other outcome of
    a child reaches this mapping (see run_release_date_child for what it
    does instead)."""
    reply = run_release_date_child(name, *args)
    if reply["outcome"] == "malformed":
        raise ReleaseDateMalformed(reply["message"])
    if reply["outcome"] == "absent":
        return None
    return reply["value"]


def reset_sigchld() -> None:
    """Reset SIGCHLD to its default disposition before the gate starts any
    child. An ignored SIGCHLD, inherited across exec from the caller, makes
    the kernel reap each child as it ends, so os.waitid would report ECHILD
    for every extractor child and the exit status of a gh child would be
    lost. Exits 3 when the disposition cannot be reset, as in a thread other
    than the main thread (ValueError) or on an OSError."""
    try:
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    except (OSError, ValueError) as error:
        _unavailable(
            f"could not reset SIGCHLD to its default disposition ({type(error).__name__}: {error}), "
            f"so the end of a child could be lost"
        )


def probe_release_date_tool() -> int:
    """Run the extractor once, for its baseline, before the checks. Returns 0,
    or 3 after reporting why the extractor is unavailable. Each later call
    runs a child of its own, so a failure here is reported once and stays in
    effect through the load_code main combines, even when a later call
    succeeds, while each later call stands on its own."""
    try:
        release_date_call("baseline")
    except SystemExit as stop:
        if stop.code != 3:
            raise
        return 3
    return 0


def die(message: str) -> None:
    print(f"check-release-checksum-live: {message}", file=sys.stderr)
    raise SystemExit(3)


def cannot_verify(message: str) -> None:
    print(f"check-release-checksum-live: could not verify: {message}", file=sys.stderr)
    raise SystemExit(2)


def require_regular_file(path: Path, shown: str) -> None:
    """Exit 3 unless the required file ``path`` (named ``shown``) is a regular
    file, naming the real reason. An absent path reads as missing; a stat that
    fails for another reason, such as a directory that cannot be searched, is
    reported as that error, never as a missing file, since ``Path.is_file``
    reads any such error as False."""
    try:
        mode = path.stat().st_mode
    except (FileNotFoundError, NotADirectoryError):
        die(f"{shown} does not exist")
    except OSError as error:
        die(f"{shown} could not be read: {type(error).__name__}: {error}")
    if not stat.S_ISREG(mode):
        die(f"{shown} is not a regular file")


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=check)


def api_status(path: str, what: str) -> int:
    """Return the HTTP status for a GitHub API path.

    A transient error must not read as "not found", so a status this cannot
    parse is treated as unverifiable rather than as a 404.
    """
    try:
        proc = gh("api", "--include", "--silent", path, check=False)
    except FileNotFoundError:
        cannot_verify("the gh CLI is not available")
    except (OSError, UnicodeError) as error:
        cannot_verify(f"could not read {what}: {error!r}")
    # A status is three ASCII digits that end the line or are followed by a
    # space ("HTTP/2.0 404 Not Found"), so int never reads a digit of another
    # script and a longer number is never cut to its first three digits.
    codes = re.findall(r"^HTTP/[0-9.]+ ([0-9]{3})(?: |$)", proc.stdout + "\n" + proc.stderr, re.M)
    if not codes:
        cannot_verify(f"could not read {what} (gh exit {proc.returncode})")
    return int(codes[-1])


def release_status(tag: str) -> int:
    """Return the HTTP status for the release, mirroring the release workflow."""
    return api_status(f"repos/{REPO}/releases/tags/{tag}", f"the release status for {tag}")


def tag_status(tag: str) -> int:
    """Return the HTTP status for the tag ref itself."""
    return api_status(f"repos/{REPO}/git/ref/tags/{tag}", f"the tag status for {tag}")


def release_published_at(tag: str) -> str:
    """Return the raw ``published_at`` value of release ``tag``, as gh prints it.

    The value is interpreted only by the extractor ``release_day_from_published_at``,
    which states the assumption it rests on. A gh failure, including an
    OSError or output that does not decode, is unverifiable.
    """
    try:
        proc = gh("api", f"repos/{REPO}/releases/tags/{tag}", "--jq", ".published_at", check=False)
    except FileNotFoundError:
        cannot_verify("the gh CLI is not available")
    except (OSError, UnicodeError) as error:
        cannot_verify(f"could not read published_at for release {tag}: {error!r}")
    if proc.returncode != 0:
        cannot_verify(f"could not read published_at for release {tag} (gh exit {proc.returncode})")
    return proc.stdout.removesuffix("\n")


def release_immutable(tag: str) -> str:
    """Return the raw ``immutable`` field of release ``tag``, as gh prints it.

    The caller accepts only exactly ``true``. A gh failure, including an
    OSError or output that does not decode, is unverifiable."""
    try:
        proc = gh("api", f"repos/{REPO}/releases/tags/{tag}", "--jq", ".immutable", check=False)
    except FileNotFoundError:
        cannot_verify("the gh CLI is not available")
    except (OSError, UnicodeError) as error:
        cannot_verify(f"could not read the immutable field of release {tag}: {error!r}")
    if proc.returncode != 0:
        cannot_verify(f"could not read the immutable field of release {tag} (gh exit {proc.returncode})")
    return proc.stdout.removesuffix("\n")


def skill_released() -> str | None:
    """Return the ``Released:`` date in SKILL.md, or None when it has no line.

    A malformed line is a required file that cannot be read correctly (exit 3).
    """
    require_regular_file(SKILL, str(SKILL.relative_to(REPO_ROOT)))
    try:
        text = SKILL.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        die(f"cleanlanguage/skills/cleanlanguage/SKILL.md could not be read: {error}")
    try:
        return release_date_call("extract", text)
    except ReleaseDateMalformed as error:
        die(f"the Released line in cleanlanguage/skills/cleanlanguage/SKILL.md is malformed: {error}")


def skill_version() -> str:
    """Return the current version named by ``cleanlanguage/skills/cleanlanguage/SKILL.md``."""
    require_regular_file(SKILL, str(SKILL.relative_to(REPO_ROOT)))
    try:
        text = SKILL.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        die(f"cleanlanguage/skills/cleanlanguage/SKILL.md could not be read: {error}")
    line = VERSION_LINE.search(text)
    if line is None:
        die("no 'Version:' line found in cleanlanguage/skills/cleanlanguage/SKILL.md")
    match = SKILL_VERSION.match(line.group(0))
    if match is None:
        die("the first 'Version:' line in cleanlanguage/skills/cleanlanguage/SKILL.md is not a bare X.Y.Z version")
    return match.group(1)


def released_line(current: str) -> tuple[str | None, bool]:
    """Return the SKILL.md Released date, or None, and whether the line is
    required for version ``current``; reads no network state. A malformed line
    or version exits 3."""
    released = skill_released()
    try:
        required = released is None and release_date_call("requires_release_date", current)
    except ReleaseDateMalformed as error:
        die(f"the SKILL.md version {current} was rejected by the extractor: {error}")
    return released, required


def report_missing_released_line(current: str, situation: str) -> None:
    """Report a Released line missing above the undated baseline for version
    ``current``; ``situation`` states the release state the gate observed."""
    baseline = release_date_call("baseline")
    print("Release date inconsistency found:")
    print(f"  - {situation}")
    print(
        f"  - cleanlanguage/skills/cleanlanguage/SKILL.md names {current}, above the "
        f"undated baseline {baseline}, but has no Released: line"
    )


def offline_release_line_code(situation: str) -> int:
    """Check the SKILL.md Released line with no network call, on a path where
    the release state is already known (the pre-tag window, or a tag with no
    release) or cannot be verified (a release or tag status that cannot be
    read, or a tag status that is neither 200 nor 404); ``situation`` states
    that state. A malformed line is never hidden behind a could-not-verify
    result.
    Returns 0, 1 when the line is missing above the undated baseline, or the
    code (2 or 3) the check stopped with, after its own report."""
    try:
        current = skill_version()
        released, required = released_line(current)
        if released is None and required:
            report_missing_released_line(current, situation)
            return 1
    except SystemExit as stop:
        if stop.code in (2, 3):
            return stop.code
        raise
    return 0


def check_release_date(site_version: str, site_status: int | None) -> bool:
    """Item 26: check the release SKILL.md names, on its own terms.

    The release probed is the one for the SKILL.md version, whatever version
    the site names, so a site that still names the previous release cannot
    hide a wrong date on a published newer one. ``site_status`` is the status
    already read for the release the site names; it is None only when that
    status could not be read and SKILL.md names a different version, so it is
    never used. Returns False (after printing why) on an inconsistency; exits
    2 when the state cannot be verified."""
    current = skill_version()
    tag = f"v{current}"
    # The line and the baseline rule are read first: an undated release at or
    # below the baseline checks no date, so it makes no network call at all.
    released, required = released_line(current)
    if released is None and not required:
        return True
    try:
        status = site_status if current == site_version else release_status(tag)
        if status == 404:
            # As on the same-version path in main: only a confirmed absent tag
            # means the release is not published yet. An existing tag with no
            # release is a deleted or failed release, and a tag status that
            # cannot be read cannot be verified.
            tag_state = tag_status(tag)
            if tag_state == 200:
                cannot_verify(
                    f"tag {tag} exists but release {tag}, the version SKILL.md names, is not "
                    f"published; if a release run is publishing {tag} right now, re-run this "
                    f"check once it completes, and otherwise the release was deleted or its "
                    f"publish failed"
                )
            if tag_state != 404:
                cannot_verify(f"unexpected HTTP {tag_state} reading tag {tag}")
            print(
                f"Release {tag}, the version SKILL.md names, is not published yet and its "
                f"tag does not exist; its Released date is checked once it is published."
            )
            # As in the same-version pre-tag window, a line missing above the
            # undated baseline still fails (a malformed one already exited 3).
            if released is None:
                report_missing_released_line(
                    current, f"release {tag}, the version SKILL.md names, is not published yet and its tag does not exist"
                )
                return False
            return True
        if status != 200:
            if current == site_version:
                # The same release the site names: the caller has already
                # reported this status, so it is not reported twice.
                raise SystemExit(2)
            cannot_verify(f"unexpected HTTP {status} reading release {tag}, the version SKILL.md names")
    except SystemExit as stop:
        # A release state that cannot be verified does not hide a Released
        # line missing above the baseline: it is reported too, and the exit
        # stays the more severe 2.
        if stop.code == 2 and released is None:
            report_missing_released_line(
                current, f"the release state of {tag}, the version SKILL.md names, could not be verified"
            )
        raise
    # A Released line missing above the baseline (exit 1) does not hide the
    # immutable check, a property of the release record itself: the missing
    # line is reported first, and an immutable field that is not exactly true,
    # or cannot be read, still stops with the more severe 2.
    if released is None:
        report_missing_released_line(current, f"release {tag} is published")
    # The date comparison relies on published_at still being the first
    # publication instant; an immutable release cannot have had its assets
    # replaced since, so anything but exactly true cannot be verified.
    immutable = release_immutable(tag)
    if immutable != "true":
        cannot_verify(
            f"the immutable field of release {tag} is {immutable!r}, not true, so its "
            f"published_at cannot be relied on as the first publication instant"
        )
    if released is None:
        # With no line there is no day to compare, so published_at is not read.
        return False
    raw = release_published_at(tag)
    try:
        published_day = release_date_call("release_day_from_published_at", raw)
    except ReleaseDateMalformed as error:
        cannot_verify(f"the published_at of release {tag} is unusable: {error}")
    if released != published_day:
        print("Release date inconsistency found:")
        print(f"  - cleanlanguage/skills/cleanlanguage/SKILL.md says Released: {released}")
        print(f"  - release {tag} published_at reads {raw} (UTC day {published_day})")
        print(
            "\nThe Released line must name the UTC day the release was first "
            "published. The release is immutable, so neither its published zip "
            "nor its record can be replaced. If the line was edited after the "
            "release, restore the value the published zip carries; if the "
            "published zip itself names the wrong day, the remedy is a corrective "
            "new version whose Released line names its own publication day. The "
            "first-publication readback the release workflow printed when it "
            "created the release (its run log) records the day GitHub recorded."
        )
        return False
    print(f"The SKILL.md Released date {released} matches the publication day of release {tag}.")
    return True


def release_date_code(site_version: str, site_status: int | None) -> int:
    """Run check_release_date and return its exit code (0 or 1), or the code
    (2 or 3) it stopped with, after its own report, so the caller can still
    run and report the checksum comparison."""
    try:
        return 0 if check_release_date(site_version, site_status) else 1
    except SystemExit as stop:
        if stop.code in (2, 3):
            return stop.code
        raise


def published_digest(tag: str, zip_name: str, manifest_name: str) -> str:
    """Download the release zip and its manifest, prove the zip hashes to its
    own manifest, and return that published digest; exits 2 when it cannot."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            gh(
                "release", "download", tag, "--repo", REPO, "--dir", tmp, "--clobber",
                "--pattern", zip_name, "--pattern", manifest_name,
            )
        except subprocess.CalledProcessError as exc:
            cannot_verify(
                f"could not download {zip_name} / {manifest_name} from {tag}: "
                f"{exc.stderr.strip()}"
            )
        zip_path = Path(tmp) / zip_name
        manifest_path = Path(tmp) / manifest_name
        # A downloaded asset whose stat fails for a reason other than its
        # absence is reported as that error, never as a missing asset.
        for asset in (zip_path, manifest_path):
            try:
                present = stat.S_ISREG(asset.stat().st_mode)
            except (FileNotFoundError, NotADirectoryError):
                present = False
            except OSError as error:
                cannot_verify(f"could not read {asset.name} from {tag}: {type(error).__name__}: {error}")
            if not present:
                cannot_verify(f"release {tag} is missing {zip_name} or {manifest_name}")

        # The manifest must be exactly one line: a 64-hex digest, two spaces, and
        # the expected basename. A crafted path inside it cannot redirect the check.
        try:
            lines = manifest_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as error:
            cannot_verify(f"could not read {manifest_name} from {tag}: {error!r}")
        if len(lines) != 1:
            cannot_verify(f"{manifest_name} is not exactly one line")
        claimed = lines[0].split("  ")[0]
        if not SHA256.match(claimed) or lines[0] != f"{claimed}  {zip_name}":
            cannot_verify(f"{manifest_name} is not '<digest>  {zip_name}'")

        computed = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        if computed != claimed:
            cannot_verify(
                f"published {zip_name} ({computed}) does not match its own "
                f"manifest ({claimed}); the release is malformed"
            )
    return claimed


class PageReader(HTMLParser):
    """The verify page, or a part of it, as parsed markup, as download_block_problems reads it: the id, the class
    names and the value of each attribute of each element, and the text outside scripts and styles, with character
    references decoded and runs of whitespace read as 1 space, so that the order of attributes, their quoting and
    the markup between words do not change what a rule sees; the same of the markup inside each comment, read
    apart (comment_text); and, at the offset of each start tag, the elements open there (open_at). Hidden elements
    are read like any other. An end tag closes the nearest open element of its name only when no element of SCOPE,
    the boundaries of HTML's default scope, is open above it, and is otherwise ignored, so that ``</div>`` inside a
    ``template`` or ``</details>`` inside a ``table`` closes nothing outside it. That is the only part of HTML's tree
    building it models, and a browser builds some other markup otherwise, so the reader can find the block where
    build() writes it when a browser does not: examples are the block after ``<noscript></div><div class="doc">``,
    the same with ``select``, and ``<span><details></span>`` before step 1. Whole-page equality refuses such a page.
    tools/check-release-links.py and tools/check-release-checksum-live.py carry this class verbatim."""

    VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track",
                      "wbr"})
    SCOPE = frozenset({"applet", "caption", "html", "marquee", "object", "table", "td", "template", "th"})

    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=True)
        self.line_starts = [0] + [index + 1 for index, character in enumerate(text) if character == "\n"]
        self.open: list[tuple[str, tuple[tuple[str, str | None], ...]]] = []
        self.open_at: dict[int, tuple[tuple[str, tuple[tuple[str, str | None], ...]], ...]] = {}
        self.starts: list[str] = []
        self.ids: list[str] = []
        self.classes: list[str] = []
        self.values: list[str] = []
        self.chunks: list[str] = []
        self.comments: list[str] = []
        self.skipping = 0
        self.feed(text)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line, column = self.getpos()
        self.open_at[self.line_starts[line - 1] + column] = tuple(self.open)
        self.starts.append(tag)
        for name, value in attrs:
            if value is None:
                continue
            self.values.append(value)
            if name == "id":
                self.ids.append(value.strip())
            elif name == "class":
                self.classes += [part for part in re.split(r"[ \t\n\f\r]+", value) if part]
        if tag in ("script", "style"):
            self.skipping += 1
        if tag not in self.VOID:
            self.open.append((tag, tuple(attrs)))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # As in a browser, a self-closing tag leaves an element open unless it is void or inside svg or math.
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID and any(name in ("svg", "math") for name, _ in self.open[:-1]):
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self.skipping:
            self.skipping -= 1
        for index in range(len(self.open) - 1, -1, -1):
            if self.open[index][0] == tag:
                del self.open[index:]
                break
            if self.open[index][0] in self.SCOPE:
                break

    def handle_data(self, data: str) -> None:
        if not self.skipping:
            self.chunks.append(data)

    def handle_comment(self, data: str) -> None:
        inner = PageReader(data)
        self.ids += inner.ids
        self.classes += inner.classes
        self.values += inner.values
        self.comments.append(inner.text())
        self.comments += inner.comments

    def text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self.chunks))

    def comment_text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.comments))


def checksum_paths(redirects: str) -> set[str]:
    """The site paths that serve the checksum file: each source in ``redirects`` (site/_redirects) whose target is
    a .sha256 file or another such path, in lower case, with each run of slashes read as 1 and without a final
    slash."""
    rules = [line.split()[:2] for line in redirects.splitlines()
             if len(line.split()) >= 2 and not line.split()[0].startswith("#")]
    paths: set[str] = set()
    while True:
        found = {re.sub(r"/+", "/", source).rstrip("/").lower() for source, target in rules
                 if targets_checksum(target, paths)}
        if found <= paths:
            return paths
        paths |= found


def targets_checksum(value: str, paths: set[str]) -> bool:
    """Whether ``value``, read as a link on the verify page, reaches the checksum file: a .sha256 file at any
    address, or a path in ``paths`` (checksum_paths) at any host, with each run of slashes read as 1. A value
    that is not a URL reaches nothing."""
    try:
        path = urllib.parse.unquote(urllib.parse.urlsplit(urllib.parse.urljoin(VERIFY_URL, value.strip())).path)
    except ValueError:
        return False
    path = re.sub(r"/+", "/", path).lower()
    return path.endswith(".sha256") or path.rstrip("/") in paths


def download_block(version: str, checksum: str) -> str:
    """The verify page's download block as tools/build-site.py writes it for ``version``, the tag v``version`` and
    ``checksum`` (verify_download_block): steps 1 to 3, with the published checksum, the link to its file and step
    3, or, for the zero placeholder, the not-yet-published note. Raises LookupError when the generator cannot
    render it. Both gates carry this function verbatim, as download_block_problems says."""
    try:
        module = types.ModuleType("build_site")
        module.__file__ = str(GENERATOR)
        exec(compile(GENERATOR.read_bytes(), str(GENERATOR), "exec", dont_inherit=True), module.__dict__)
        return module.verify_download_block(module.REPO_ROOT, version, f"v{version}", checksum)
    # SystemExit too, so that a generator that exits while it loads or renders is reported as one that cannot render
    # (exit 3), never as the generator's own exit code.
    except (Exception, SystemExit) as error:
        # The message gives the type and the text: the text of an OSError names its file, and a bare SystemExit, whose
        # text is empty, shows as its type alone.
        detail = ": ".join(part for part in (type(error).__name__, str(error)) if part)
        raise LookupError(f"tools/build-site.py could not render the verify page's download block: {detail}") from error


def download_block_problems(text: str, block: str, redirects: str) -> list[str]:
    """The rule of the verify page in either state, one problem for each part ``text`` breaks: it carries
    ``block``, the download block tools/build-site.py renders for that state (download_block), exactly once and
    byte for byte, as a start tag that the parsed page opens inside exactly the elements that build() writes
    around it (BLOCK_ANCESTORS), in a page with 1 html and 1 body start tag; and no other part of the page,
    comments, scripts and hidden elements included, carries the checksum element's id, the class sum, the
    not-yet-published note, "published checksum" wording, a 64 digit hexadecimal value (in the text, also in groups
    split by whitespace, hyphens or colons, HEX_GROUPS), a link to a .sha256 file or to a path that ``redirects``
    (site/_redirects) sends there, or a step that tells the reader not to install the file. It does not read the
    meaning of other prose, so a reworded or contradicting step outside the block passes it, nor the stylesheet
    and script files the page loads. tools/check-release-links.py and tools/check-release-checksum-live.py carry
    this function, download_block, PageReader, checksum_paths, targets_checksum and the patterns and constants
    they read verbatim, and tools/test-release-checksum-live.py requires that the 2 copies match. A page whose
    comments nest too deeply for PageReader, which reads each comment's markup apart, is 1 problem, never an uncaught
    RecursionError."""
    found = text.count(block)
    if found != 1:
        return [f"does not carry the download block that tools/build-site.py writes for this state exactly once, "
                f"byte for byte (found {found})"]
    start = text.index(block)
    rests = (text[:start], text[start + len(block):])
    try:
        page = PageReader(text)
        parts = [PageReader(rest) for rest in rests]
    except RecursionError:
        return ["nests comments too deeply to be read"]
    problems: list[str] = []
    if page.open_at.get(start) != BLOCK_ANCESTORS or page.starts.count("html") != 1 or page.starts.count("body") != 1:
        problems.append("does not carry the download block where tools/build-site.py writes it")
    paths = checksum_paths(redirects)
    for rest, part in zip(rests, parts):
        sources = (rest, part.text(), part.comment_text())
        if SUM_ID in rest.lower() or SUM_ID in (value.lower() for value in part.ids):
            problems.append("carries the checksum element's id outside the download block")
        if "sum" in part.classes:
            problems.append("carries the class sum outside the download block")
        if any(PENDING_NOTE.search(source) for source in sources):
            problems.append("carries the not-yet-published note outside the download block")
        if any(PUBLISHED_WORDING.search(source) for source in sources):
            problems.append('says "published checksum" outside the download block')
        if (any(HEX64.search(source) for source in (*sources, *part.values))
                or any(HEX_GROUPS.search(source) for source in sources[1:])):
            problems.append("carries a 64 digit hexadecimal value outside the download block")
        if ".sha256" in rest.lower() or any(targets_checksum(value, paths) for value in part.values):
            problems.append("links a .sha256 checksum file outside the download block")
        if any(REJECTING_STEP.search(source) for source in sources):
            problems.append("has a step that tells the reader not to install the file outside the download block")
    return list(dict.fromkeys(problems))


def rendered_verify_page(version: str, checksum: str) -> bytes:
    """site/verify/index.html as tools/build-site.py renders it at base / from the committed sources for ``version``,
    the tag v``version`` and ``checksum`` (verify_page), whatever version SKILL.md names: the page the gate requires
    byte for byte. Raises LookupError when the generator cannot render it, which a refusal on any page causes."""
    try:
        module = types.ModuleType("build_site_page")
        module.__file__ = str(GENERATOR)
        exec(compile(GENERATOR.read_bytes(), str(GENERATOR), "exec", dont_inherit=True), module.__dict__)
        release = {"version": version, "tag": f"v{version}", "checksum": checksum}
        return module.verify_page(module.REPO_ROOT, release)
    # SystemExit too, so that a generator that exits while it loads or renders is reported as one that cannot render
    # (exit 3), never as the generator's own exit code.
    except (Exception, SystemExit) as error:
        # The message gives the type and the text: the text of an OSError names its file, and a bare SystemExit, whose
        # text is empty, shows as its type alone.
        detail = ": ".join(part for part in (type(error).__name__, str(error)) if part)
        raise LookupError(f"tools/build-site.py could not render the verify page: {detail}") from error


def staged_draft() -> str | None:
    """The base path site-src/site.json names when it is not /, which means a draft is staged, or None. The gate
    renders the live verify page at base / from the sources, the draft's changes included, while tools/build-site.py
    writes only the draft, so this selects the report and never the verdict. None also when the file cannot be read
    or names no base as a string, so the report is as without a draft; the generator refuses a site.json it cannot
    read, so the gate has already stopped at the render (rendered_verify_page)."""
    try:
        config = json.loads((REPO_ROOT / "site-src" / "site.json").read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError):
        return None
    base = config.get("base") if isinstance(config, dict) else None
    return base if isinstance(base, str) and base != "/" else None


def draft_advice(base: str) -> str:
    """The advice while site-src/site.json names ``base``, a base other than /, so a draft is staged (staged_draft)."""
    return (f"site-src/site.json names base {base}, so a draft is staged: tools/build-site.py writes only the draft, "
            f"not the live pages, and this gate renders the live verify page at base / from the sources, the draft's "
            f"changes included. Promotion after the owner approves it is the remedy: the pull request of step 5 under "
            f"\"Staging at /draft/ and promotion\" in .baseline/README.md, of which tools/build-site.py --base / "
            f"--promote is 1 step")


def first_difference(written: bytes, rendered: bytes) -> str:
    """Where ``written`` first departs from ``rendered``, by line, for the report."""
    lines, expected = written.split(b"\n"), rendered.split(b"\n")
    for number, (line, wanted) in enumerate(zip(lines, expected), start=1):
        if line != wanted:
            return f"first at line {number}"
    return f"the page has {len(lines)} lines, the render {len(expected)}"


def check_site_checksum(load_code: int = 0) -> int:
    """Check the site checksum and the release date, returning the most
    severe code of the checks that ran (0 to 3), or stopping with 2 or 3 when
    the gate cannot go on; main combines it with ``load_code``, the result of
    its extractor probe, which the pre-tag window also reads so that it says
    there is nothing to reconcile only when the gate passes."""
    require_regular_file(VERIFY_PAGE, str(VERIFY_PAGE.relative_to(REPO_ROOT)))
    # A required file that cannot be read or decoded exits 3, never an
    # uncaught traceback (exit 1, drift); main still combines it with the
    # extractor probe result.
    try:
        verify = VERIFY_PAGE.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        die(f"{VERIFY_PAGE.relative_to(REPO_ROOT)} could not be read: {type(error).__name__}: {error}")

    pending = PENDING_VERSION.search(verify)
    if pending is not None:
        # The not-yet-published state: the site holds the zero placeholder, so a
        # published release whose zip and .sha256 published_digest can download
        # and read, with a well-formed manifest that the zip hashes to, makes it
        # drift below.
        version = pending.group(1)
        site_sum = PLACEHOLDER
    else:
        shown = DISPLAYED_SUM.search(verify)
        stated = DISPLAYED_VERSION.search(verify)
        if shown is None:
            die('the verify page has no <code class="sum" id="published-checksum"> block')
        site_sum = shown.group(1).strip()
        if not SHA256.match(site_sum):
            die(f"the displayed checksum {site_sum!r} is not a 64 character lower-case SHA-256")
        if site_sum == PLACEHOLDER:
            die("the verify page shows the zero placeholder as the published checksum")

        if stated is None:
            die("the verify page does not state which version its checksum belongs to")
        version = stated.group(1)
    # The rule tools/check-release-links.py applies: the page carries the download block that tools/build-site.py
    # writes for the version and checksum read above, and nothing outside it that belongs to either state. A page
    # that breaks it is in neither state the generator writes.
    require_regular_file(REDIRECTS, str(REDIRECTS.relative_to(REPO_ROOT)))
    try:
        redirects = REDIRECTS.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        die(f"{REDIRECTS.relative_to(REPO_ROOT)} could not be read: {type(error).__name__}: {error}")
    try:
        block = download_block(version, site_sum)
        rendered = rendered_verify_page(version, site_sum)
    except LookupError as error:
        die(str(error))
    problems = download_block_problems(verify, block, redirects)
    # The gate: the whole page, byte for byte, as tools/build-site.py renders it from the committed sources for the
    # version and checksum read above. The rule above names the commonest faults more clearly, so a page that breaks
    # it is reported by it alone; both stop the gate in die() below.
    try:
        written = VERIFY_PAGE.read_bytes()
    except OSError as error:
        die(f"{VERIFY_PAGE.relative_to(REPO_ROOT)} could not be read: {type(error).__name__}: {error}")
    # While a draft is staged, tools/build-site.py does not write the live page, so the report does not say to run it.
    staged = staged_draft()
    if not problems and written != rendered:
        problems.append(f"is not the page tools/build-site.py renders for version {version} and that checksum from "
                        f"the committed sources ({first_difference(written, rendered)})"
                        + ("; run tools/build-site.py" if staged is None else ""))
    if problems:
        state = "carries the not-yet-published note" if pending is not None else "shows a published checksum"
        die(f"the verify page {state}, but " + "; ".join(problems)
            + ("" if staged is None else f". {draft_advice(staged)}"))
    tag = f"v{version}"
    zip_name = f"cleanlanguage-{version}.zip"
    manifest_name = f"{zip_name}.sha256"

    try:
        status = release_status(tag)
    except SystemExit as stop:
        if stop.code != 2:
            raise
        # The status cannot be read, so the checksum comparison cannot run,
        # and the more severe code wins, so a malformed line (exit 3) is not
        # hidden. When SKILL.md names the same version, the state of its
        # release is this unreadable status, so the Released line is checked
        # offline. When it names a different version, that release was never
        # probed, so the release-date check probes it on its own terms, as on
        # the unexpected-status path below (row 62), and a wrong date on a
        # published newer release is still reported.
        try:
            same_version = skill_version() == version
        except SystemExit as unreadable:
            if unreadable.code != 3:
                raise
            return 3
        if not same_version:
            return max(2, release_date_code(version, None))
        return max(2, offline_release_line_code(
            f"the release state of {tag}, the version the verify page names, could not be verified"
        ))
    if status == 404:
        current = skill_version()
        if version != current:
            print("Release checksum inconsistency found:")
            print(f"  - the verify page names version {version}, which has no published release")
            print(f"  - cleanlanguage/skills/cleanlanguage/SKILL.md names {current} as the current version")
            print(
                f"\nA site legitimately ahead of its release names the current skill "
                f"version. This looks like a typo or a stale bump; align the verify "
                f"page with SKILL.md, or publish release {tag}."
            )
            # The release SKILL.md names is still checked on its own terms, so
            # this inconsistency cannot hide a wrong date on a published release.
            return max(1, release_date_code(version, status))
        try:
            tag_state = tag_status(tag)
        except SystemExit as stop:
            if stop.code != 2:
                raise
            tag_state = None
        if tag_state != 404:
            # The release cannot be verified (exit 2), but the Released line is
            # still checked offline, with no further network call, and the more
            # severe code wins, so a malformed line (exit 3) or a line missing
            # above the baseline is not hidden.
            if tag_state == 200:
                print(
                    f"check-release-checksum-live: could not verify: tag {tag} exists but "
                    f"release {tag} is not published; if a release run is publishing {tag} "
                    f"right now, re-run this check once it completes, and otherwise the "
                    f"release was deleted or its publish failed",
                    file=sys.stderr,
                )
                situation = f"release {tag} is not published but its tag exists"
            else:
                if tag_state is not None:
                    print(
                        f"check-release-checksum-live: could not verify: unexpected HTTP {tag_state} reading tag {tag}",
                        file=sys.stderr,
                    )
                situation = f"release {tag} is not published and the state of its tag could not be verified"
            return max(2, offline_release_line_code(situation))
        situation = f"release {tag} is not published yet and its tag does not exist"
        if pending is None:
            # Before the tag, the only page that states nothing false is the note. A
            # checksum shown as published for a version with no release (the previous version's digest or a locally
            # built one passed to tools/set-release-links.py) fails, as does a page whose step 3 then rejects the
            # download. A checksum close to the zero placeholder, such as a mistyped one, never reaches this point:
            # the generator refuses to render it, so the gate stops at the render above. The Released line is still
            # checked, and the more severe code wins.
            print("Release checksum inconsistency found:")
            print(f"  - the verify page shows {site_sum} as the published checksum for version {version}")
            print(f"  - {situation}, so no checksum for {version} is published")
            print(
                f"\nBefore the tag, the verify page can only say that the checksum is not yet published. Run "
                f"tools/set-release-links.py for {version} with the zero placeholder checksum, and flip the site "
                f"to the published checksum once release {tag} is published; see the release runbook."
            )
            return max(1, offline_release_line_code(situation))
        print(
            f"Release {tag} is not published yet; the site and SKILL.md both name "
            f"{version} ahead of the release, which is expected before the tag."
        )
        # The release and its tag are confirmed absent, so the Released line
        # is checked offline: a malformed line, or one missing above the
        # undated baseline, is still reported in this window. The window says
        # there is nothing to reconcile only when that check and the extractor
        # probe both pass, so the gate then exits 0.
        code = offline_release_line_code(situation)
        if max(load_code, code) == 0:
            print("Nothing to reconcile.")
        return code
    if status != 200:
        # The checksum comparison cannot run (exit 2), but the release-date
        # check below still runs and reports any failure it finds, and the more
        # severe code wins.
        print(
            f"check-release-checksum-live: could not verify: unexpected HTTP {status} reading release {tag}",
            file=sys.stderr,
        )
        return max(2, release_date_code(version, status))

    # A failed download or a malformed release stops only the checksum
    # comparison (exit 2); the release-date check below still runs and reports
    # any failure it finds.
    try:
        claimed = published_digest(tag, zip_name, manifest_name)
    except SystemExit as stop:
        if stop.code != 2:
            raise
        claimed = None
    except (OSError, UnicodeError) as error:
        # The download directory, the downloaded zip, or the gh run itself
        # failed at the operating-system level: the comparison cannot run
        # (exit 2), never an uncaught traceback read as drift (exit 1).
        print(
            f"check-release-checksum-live: could not verify: could not download or read "
            f"{zip_name} / {manifest_name} from {tag}: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        claimed = None

    # Item 26: the release SKILL.md names is checked on its own terms,
    # whatever version the site names (see check_release_date). A date edited
    # after release goes red here; a release that slipped past UTC midnight is
    # refused or caught by the release workflow itself, and goes red here too.
    # Both checks run, and each reports any failure it finds, before the gate
    # exits with the more severe code, so a date failure cannot hide checksum
    # drift.
    date_code = release_date_code(version, status)

    if claimed is None:
        checksum_code = 2
    elif site_sum != claimed:
        print("Release checksum drift found:")
        if pending is not None:
            print(f"  - the verify page says the checksum for version {version} is not yet published")
        else:
            print(f"  - the verify page shows {site_sum} for version {version}")
        print(f"  - the published {zip_name} is {claimed}")
        print(
            f"\nThe release {tag} is published but the site was not flipped to its "
            f"checksum. Run the orchestrator's post-release site flip "
            f"(tools/set-release-links.py with checksum {claimed}); see the release runbook."
        )
        checksum_code = 1
    else:
        print(
            f"The verify page checksum {site_sum} matches the published {zip_name} "
            f"for release {tag}."
        )
        checksum_code = 0
    return max(date_code, checksum_code)


def main() -> int:
    """Run the gate. SIGCHLD is reset first, before any child starts (see
    reset_sigchld). The extractor is then probed here, inside the protected
    path, so a probe that ends in exit 3 contributes 3 while the checksum
    comparison still runs and reports; the most severe code wins (3 over 2
    over 1 over 0)."""
    reset_sigchld()
    load_code = probe_release_date_tool()
    try:
        code = check_site_checksum(load_code)
    except SystemExit as stop:
        if stop.code not in (2, 3):
            raise
        code = stop.code
    code = max(load_code, code)
    if code >= 2:
        raise SystemExit(code)
    return code


if __name__ == "__main__":
    sys.exit(main())
