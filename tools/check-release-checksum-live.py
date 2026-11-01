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
check goes red on exactly that drift. It runs in CI on pushes to main and on a
daily schedule, and the orchestrator runs it as the final step of the runbook.

Behaviour:
  - Reads the version and displayed checksum from ``site/verify/index.html``.
  - If the release ``vX`` for that version is not published yet, the pass is
    conditional. The site is legitimately ahead of the release only when it
    names the current skill version (``Version:`` in ``cleanlanguage/skills/cleanlanguage/SKILL.md``)
    and the tag ``vX`` does not exist yet, which is the pre-tag window the
    release runbook creates. In that window the SKILL.md ``Released:`` line is
    still checked, with no further network call: a malformed line exits 3, and
    a line missing above the undated baseline fails. A different version with
    no release is a real
    inconsistency and fails. An existing tag with no published release is a
    deleted or unfinished release and reads as unverifiable, as does a release
    or tag status that cannot be read; on each such path the SKILL.md
    ``Released:`` line is still checked with no further network call, and the
    more severe code wins. When the release status of the version the site
    names cannot be read and SKILL.md names a different version, the
    release-date check below probes the release SKILL.md names instead. One
    broken state
    stays invisible to this check: a bump that updated both the verify page and
    SKILL.md but whose tag was never pushed is indistinguishable from the
    pre-tag window by repository state alone.
  - If the release exists, downloads the version-named zip and its ``.sha256``,
    proves the release is self-consistent (the zip hashes to its own manifest),
    and requires the site's displayed checksum to equal that published digest.
  - Separately, and whatever version the site names, checks the release for
    the version SKILL.md names on its own terms (item 26, G4): it probes that
    release; on 200 it requires the SKILL.md ``Released:`` line to name the UTC
    day of the release ``published_at`` record and requires the release record
    to be immutable (``immutable`` exactly true, so its assets and record
    cannot have been replaced since publication); on 404 it checks the tag
    exactly as the same-version path does, so only a confirmed absent tag
    means the release is not published yet and the date comparison is
    skipped (a line missing above the undated baseline still fails there, as
    in the pre-tag window), while an existing tag, or a tag whose status cannot be read, cannot be
    verified; any other release status cannot be verified. The line may be
    absent only when that version is at or below the undated baseline
    declared in ``tools/skill-release-date.py``; the line and that rule are
    read first, and then no network call is made for the date check at all.
    An undated release at or below that baseline is therefore not checked for
    immutability either.
    The meaning of ``published_at`` is an assumption,
    isolated in ``release_day_from_published_at`` in that tool; see its
    docstring.

Requires the ``gh`` CLI and, in CI, ``GH_TOKEN`` with ``contents: read``.

Exit codes:
  0  the site checksum matches the published release, or the site is
     legitimately ahead of an unpublished release (it names the current skill
     version, the tag does not exist yet, and the SKILL.md Released line is
     well formed, and present above the undated baseline)
  1  drift or inconsistency: the release is published but the site shows a
     different checksum, or the site names an unreleased version that is not
     the current skill version, or the SKILL.md Released date disagrees with
     the published release, or the Released line is missing above the undated
     baseline (also in the pre-tag window)
  2  could not verify (gh or network error, the published release is malformed,
     its ``published_at`` is unreadable or malformed, its ``immutable`` field is
     not exactly true, the release SKILL.md names returns a status other than
     200 or 404, or the tag exists with no published release)
  3  a required file could not be read, the SKILL.md Released line is
     malformed, or a call of tools/skill-release-date.py, which runs in a
     child process, did not give a result the gate could accept (see
     run_release_date_child)

The release-date check and the site-checksum comparison both run and both
are reported when the release the site names is published, including when its
download fails, its downloaded assets cannot be read, or its manifest is
malformed or undecodable, and also when that
release returns a status other than 200 or 404, or a status that cannot be
read while SKILL.md names a different version, and when the site names an
unreleased version that is not the current skill version, so neither failure
hides the other. Within the date check of a published release, a Released line
missing above the undated baseline does not hide an immutable field that is not
exactly true: both are reported and the more severe 2 wins. The extractor is probed inside main, not at import, so a
probe that ends in exit 3 is reported and contributes 3 while the checksum
comparison still runs and reports. The gate then exits with the most severe code, the highest
one (3 over 2 over 1 over 0), since 2 and 3 mean a check could not complete.

The extractor runs in a separate python3 -I child for each call
(run_release_date_child), so extractor code never runs in this process, and
what it does to its own process, such as exiting, raising, rewriting a
global, or signalling itself, acts on the child. The timeout applies to each
child: a gate run starts several children, so a child that hangs can hold the
gate for up to CHILD_TIMEOUT_SECONDS on each call. The gate takes a result
from a child only when the child exits 0 and prints exactly one JSON object
that matches the contract, and it reads only a bounded part of what the child
prints (see RESULT_LIMIT). Every other outcome of a child that the gate
observes exits 3 with its report, never 2, 1, or 0. On a normal end and on a
timeout, the gate kills the process group of the child before it reaps the
child, or exits 3 when it cannot; on the other paths described in
run_release_date_child it may not. A process the child started is killed
with the group only while it is in the group: a process that leaves the
child's process group, by any means, can outlive the gate.
Separation is not a sandbox. The child runs with the uid, filesystem, and
network of the gate, so extractor code can do whatever that uid can do,
including writing files, reaching the network, using CPU, memory, and disk,
and signalling the gate. A signal it sends to the gate acts on the gate as
that signal acts on any process: it can interrupt, stop, or end the gate
outside the exit codes above, and no bound of the gate limits its effect. If
the gate is killed while it waits, the child, in its own session, can be left
running. Each call reads the extractor file afresh, so a file replaced during
a run can give different calls different code. The extractor remains the
authority on content, so changed extractor code that returns a wrong but
well-formed answer, or classifies a value as malformed, is not detectable
here, as it never was; the stderr the gate relays on a failure is
extractor-controlled text, as the error text it reported was before.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERIFY_PAGE = REPO_ROOT / "site" / "verify" / "index.html"
SKILL = REPO_ROOT / "cleanlanguage" / "skills" / "cleanlanguage" / "SKILL.md"
REPO = "jposluns/cleanlanguage"

DISPLAYED_SUM = re.compile(r'<code id="published-checksum">([^<]*)</code>')
DISPLAYED_VERSION = re.compile(r"published checksum for version ([0-9][0-9.]*) is")
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
# kills the process group of the child where it can, and exits 3. Of what the
# child prints, the gate reads at most STDERR_LIMIT bytes of stderr and one
# byte more than the stdout bound, which is RESULT_LIMIT bytes plus
# ECHO_BYTES_PER_CHARACTER bytes for each character of the request argument,
# so a longer stdout is refused and the memory a reply takes stays bounded by
# the request the gate already holds. ECHO_BYTES_PER_CHARACTER is the most
# bytes one character can take through repr and then ASCII JSON (a printable
# character outside the basic plane becomes a surrogate pair of two \uXXXX
# escapes, 12 bytes); the allowance is there so that a malformed message that
# echoes the argument keeps its verdict (see
# test_an_echoed_request_of_any_size_keeps_its_verdict).
CHILD_TIMEOUT_SECONDS = 20
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


def _kill_group(proc: subprocess.Popen, ended: bool) -> str | None:
    """Kill the process group of the child ``proc``, which has not been
    reaped yet, so neither its pid nor the group id it leads can have been
    reused, and then reap the child; ``ended`` is whether the child has
    already ended. Returns None, or the reason when the group could not be
    killed: the gate then tries to kill the child itself when ``ended`` is
    false, and reaps the child only when it has ended or that kill
    succeeded, so it never waits on a child it could not kill."""
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
        proc.wait()
        return problem
    proc.wait()
    return None


def run_release_date_child(op: str, arg: str | None = None) -> dict:
    """Run the extractor once, as ``skill-release-date.py --json`` under
    ``sys.executable -I``, for the op ``op`` with ``arg``, and return its
    reply, checked against the contract (RELEASE_DATE_CONTRACT and
    REPLY_KEYS).

    The child gets an empty environment, the tool directory as its working
    directory, and its own session, so it leads a process group of its own.
    The request is written to a temporary file that is its stdin, and its
    stdout and stderr go to temporary files, so the gate never blocks on a
    pipe and reads only a bounded part of each. The wait, bounded by
    CHILD_TIMEOUT_SECONDS for this child, leaves the child unreaped. On a
    normal end and on a timeout, the process group of the child is then
    killed before the child is reaped, or the call exits 3 when the group
    cannot be killed; on the other paths this docstring describes it may not
    be. A process the child started is killed with the group only while it
    is in the group, so a process that leaves the child's process group, by
    any means, can outlive the gate. A wait that reports the child is no
    longer a child of the gate (ChildProcessError) signals nothing, as its
    pid may be reused, and exits 3.

    This function returns only a reply from a child that exits 0 and whose
    stdout, within the bound (see RESULT_LIMIT), is exactly one ASCII JSON
    object, with no key repeated, that matches the contract. When it does
    not return, it exits 3 as unavailable, naming the reason and relaying at
    most STDERR_LIMIT bytes of the child stderr, or an exception passes
    through it; it never gives a content verdict, a pass, or a drift for any
    other outcome. Every Exception raised while the gate prepares, starts,
    waits for, kills, or reads its child exits 3 that way.

    A BaseException that is not an Exception, such as a KeyboardInterrupt,
    is not caught that way. When one reaches the gate while it waits, the
    gate kills the group and reaps the child before it passes on, or exits 3
    when the group cannot be killed; one raised anywhere else, including
    during that kill, passes on at once, and a child already started may
    then be left unkilled, unreaped, or both."""

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
        with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as stdout, \
                tempfile.TemporaryFile() as stderr:
            stdin.write(json.dumps(request, ensure_ascii=True).encode("ascii"))
            stdin.seek(0)
            try:
                proc = subprocess.Popen(
                    [executable, "-I", str(RELEASE_DATE_TOOL), "--json"],
                    stdin=stdin, stdout=stdout, stderr=stderr, env={},
                    cwd=RELEASE_DATE_TOOL.parent, start_new_session=True,
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
    except Exception as error:
        # An Exception from the machinery of the gate itself exits 3, never
        # a traceback read as drift (exit 1); a BaseException that is not an
        # Exception, SystemExit from fail among them, passes through.
        fail(f"could not be run, waited for, or read ({type(error).__name__}: {error})")
    code = proc.returncode
    if not ended:
        fail(f"did not finish within {CHILD_TIMEOUT_SECONDS} seconds", printed)
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
    codes = re.findall(r"^HTTP/[0-9.]+ (\d{3})", proc.stdout + "\n" + proc.stderr, re.M)
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
    release) or cannot be read; ``situation`` states that state. A malformed
    line is never hidden behind a could-not-verify result.
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
    """G4 (item 26): check the release SKILL.md names, on its own terms.

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

    shown = DISPLAYED_SUM.search(verify)
    if shown is None:
        die('the verify page has no <code id="published-checksum"> block')
    site_sum = shown.group(1).strip()
    if not SHA256.match(site_sum):
        die(f"the displayed checksum {site_sum!r} is not a 64 character lower-case SHA-256")

    stated = DISPLAYED_VERSION.search(verify)
    if stated is None:
        die("the verify page does not state which version its checksum belongs to")
    version = stated.group(1)
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
        print(
            f"Release {tag} is not published yet; the site and SKILL.md both name "
            f"{version} ahead of the release, which is expected before the tag."
        )
        # The release and its tag are confirmed absent, so the Released line
        # is checked offline: a malformed line, or one missing above the
        # undated baseline, is still reported in this window. Fix round 8:
        # the window says there is nothing to reconcile only when that check
        # and the extractor probe both pass, so the gate then exits 0.
        code = offline_release_line_code(f"release {tag} is not published yet and its tag does not exist")
        if max(load_code, code) == 0:
            print("Nothing to reconcile.")
        return code
    if status != 200:
        # The checksum comparison cannot run (exit 2), but the release-date
        # check below still runs and reports, and the more severe code wins.
        print(
            f"check-release-checksum-live: could not verify: unexpected HTTP {status} reading release {tag}",
            file=sys.stderr,
        )
        return max(2, release_date_code(version, status))

    # A failed download or a malformed release stops only the checksum
    # comparison (exit 2); the release-date check below still runs and reports.
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

    # Item 26 (G4): the release SKILL.md names is checked on its own terms,
    # whatever version the site names (see check_release_date). A date edited
    # after release goes red here; a release that slipped past UTC midnight is
    # refused or caught by the release workflow itself, and goes red here too.
    # Both checks run and report before the gate exits with the more severe
    # code, so a date failure cannot hide checksum drift.
    date_code = release_date_code(version, status)

    if claimed is None:
        checksum_code = 2
    elif site_sum != claimed:
        print("Release checksum drift found:")
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
    """Run the gate. The extractor is probed here, inside the protected path,
    so a probe that ends in exit 3 contributes 3 while the checksum comparison
    still runs and reports; the most severe code wins (3 over 2 over 1 over
    0)."""
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
