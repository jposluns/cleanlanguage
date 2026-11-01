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
     malformed, or tools/skill-release-date.py could not be loaded, lacks a
     usable attribute this gate uses (see RELEASE_DATE_API), failed
     unexpectedly, or returned a value of a type the gate does not expect

The release-date check and the site-checksum comparison both run and both
are reported when the release the site names is published, including when its
download fails, its downloaded assets cannot be read, or its manifest is
malformed or undecodable, and also when that
release returns a status other than 200 or 404, or a status that cannot be
read while SKILL.md names a different version, and when the site names an
unreleased version that is not the current skill version, so neither failure
hides the other. Within the date check of a published release, a Released line
missing above the undated baseline does not hide an immutable field that is not
exactly true: both are reported and the more severe 2 wins. The extractor is loaded inside main, not at import, so a load
failure is reported and contributes exit 3 while the checksum comparison still
runs and reports. The gate then exits with the most severe code, the highest
one (3 over 2 over 1 over 0), since 2 and 3 mean a check could not complete.

The extractor runs in this process, so every call the gate makes into
extractor-defined code is guarded: loading the module, each attribute lookup
and its validation, each function call, the Malformed class checks, and the
class name and text of a caught error. Every classification or type decision
the gate makes from an object the extractor provides reads only what that code
cannot fake: the real type of the object, through type(), never its __class__,
and exact builtin types, with no isinstance or issubclass call that could run an
extractor hook. The Malformed class must be a class whose own type is exactly
the builtin type, that subclasses Exception, and whose real MRO holds no class
that is not an Exception but BaseException and object, so it is not also a
SystemExit or a KeyboardInterrupt (see _plain_exception_class), and a caught
error is a content
verdict only when its own class is exactly that Malformed class, and that class
still passes that check when the error is classified (see
_malformed_verdict); a subclass of Malformed is not a verdict, since the
extractor raises only Malformed itself. Anything else exits 3, never 2. A
caught error is described only
through _describe, never by its repr, and a returned value and
BASELINE_VERSION must be of the exact built-in type the gate expects, so no
extractor method of theirs runs later. Whatever that code raises, a SystemExit
of any code or any other exception, exits 3 with its report, with one
exception: a KeyboardInterrupt is let through as an interrupt, because the
gate cannot tell one the extractor raises from a real Ctrl-C by its type. It
is let through only when its class is exactly KeyboardInterrupt, the class a
real Ctrl-C raises (see _is_interrupt). Every other error, a subclass of
KeyboardInterrupt included, exits 3 with its report like any other error, so
no interrupt the gate lets through can also be a SystemExit,
ReleaseDateMalformed, or any other class a handler of the gate would read as
a result of the gate. The residual the gate cannot close in-process:
extractor code that calls os._exit, signals its own process, never returns,
or changes the interpreter state the gate relies on (its globals, sys,
builtins, or a thread, finalizer, or exit handler it leaves behind) acts
outside any handler, so it can still end the gate with another code. So does
an extractor that raises KeyboardInterrupt itself, at load or in a call: the
gate ends as an interrupt, with the SIGINT status (130 in a shell), not 3;
raised at load, it ends the gate before the checksum comparison runs or
reports; and the interpreter prints its text in the
traceback outside any guard, so an extractor-defined str runs unguarded
there. That status is never 0 or 1 unless that unguarded code itself calls
os._exit, the residual above.
Only running the extractor in a separate process would close that residual,
and the gate does not.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import stat
import subprocess
import sys
import tempfile
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

# The one shared strict Released-line extractor (item 26), loaded as a module
# so this gate applies the same grammar, the same baseline, and the same single
# published_at interpretation as every other caller.
RELEASE_DATE_TOOL = Path(__file__).resolve().parent / "skill-release-date.py"

# Every attribute of the loaded extractor this gate uses, with the kind it must
# be. The gate reads the module only through release_date_attr and
# release_date_call, by these names, and the loader validates all of them, so
# an incomplete or incompatible extractor exits 3 (unavailable) naming the
# attribute, never surfacing later as a stray AttributeError (exit 1, drift).
RELEASE_DATE_API = (
    ("extract", "a function"),
    ("requires_release_date", "a function"),
    ("release_day_from_published_at", "a function"),
    ("Malformed", "an exception class"),
    ("BASELINE_VERSION", "a bare X.Y.Z version string"),
)


def _api_kind_ok(value, kind: str) -> bool:
    # The version must be an exact str, not a subclass, so formatting it in a
    # report runs no extractor-defined method (fix round 4, F1).
    if kind == "a function":
        return callable(value)
    if kind == "an exception class":
        return _plain_exception_class(value)
    return type(value) is str and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value) is not None


def _plain_exception_class(value) -> bool:
    """True only when ``value`` is a class whose own type is exactly the
    builtin type, that subclasses Exception (fix round 5), and every class on
    its real MRO subclasses Exception or is BaseException or object (fix
    round 10), so it is not also a SystemExit, a KeyboardInterrupt, or any
    other BaseException that is not an Exception. type() reads the real type,
    so a value that only claims to be a class through a __class__ property,
    or a class with a custom metaclass, whose instance, subclass, or mro hooks
    would then decide the Malformed classification, is refused; once its own
    type is exactly the builtin type, its __mro__ is the real one. issubclass
    against the builtin Exception, itself of exactly the builtin type, takes
    the builtin subtype path over the real MRO, and the other tests are by
    identity, so it runs no extractor hook."""
    return type(value) is type and issubclass(value, Exception) and all(
        issubclass(base, Exception) or base is BaseException or base is object for base in value.__mro__
    )


def _is_interrupt(error: BaseException) -> bool:
    """True only when the caught ``error`` is let through as an interrupt:
    its class is exactly KeyboardInterrupt, the class a real Ctrl-C raises
    (fix round 9). type() reads the real class and the identity test runs no
    extractor hook. Every other error, a subclass of KeyboardInterrupt
    included, is handled by the caller as any other error, so the gate
    reports it and exits 3; no interrupt it lets through can also be a
    SystemExit, ReleaseDateMalformed, or any other class that a handler of
    the gate would read as a result of the gate."""
    return type(error) is KeyboardInterrupt


# The exact built-in types each extractor function may return. Checked by
# identity, so no extractor-defined method of a returned value (its bool,
# comparison, or format) runs later in the gate (fix round 4, F1).
RELEASE_DATE_RESULTS = {
    "extract": ((str, type(None)), "a str or None"),
    "requires_release_date": ((bool,), "a bool"),
    "release_day_from_published_at": ((str,), "a str"),
}


def _unavailable(message: str) -> None:
    print(f"check-release-checksum-live: {message}", file=sys.stderr)
    raise SystemExit(3)


def _guarded_text(read, fallback):
    """Return what ``read()`` gives when it is an exact str, else
    ``fallback``. ``read`` runs extractor-defined code (a str or a class-name
    lookup), so anything it raises, a SystemExit included, gives the fallback;
    only a KeyboardInterrupt that _is_interrupt lets through propagates."""
    try:
        text = read()
    except BaseException as error:
        if _is_interrupt(error):
            raise
        return fallback
    return text if type(text) is str else fallback


def _describe(error: BaseException) -> str:
    """Describe an error raised by extractor code by its class name and its
    text, each read under _guarded_text, so describing it can neither raise
    nor exit. The repr is never used: it would run extractor code (an
    extractor-defined repr, or the repr of a SystemExit code) unguarded."""
    name = _guarded_text(lambda: type(error).__name__, "an error whose class name could not be read")
    text = _guarded_text(lambda: str(error), "(its message could not be read)")
    return f"{name}: {text}" if text else name


def _malformed_verdict(error: BaseException, malformed):
    """Return the text of the extractor Malformed verdict ``error``, or None
    when it is not one, and the caller then reports the extractor as failed
    (exit 3). The verdict is decided only from what extractor code cannot fake
    (fix round 9): the real class of ``error``, read with type(), never its
    __class__, must be exactly ``malformed`` by identity, so no isinstance
    call honours a __class__ property, no metaclass hook runs, and a subclass
    of Malformed, a SystemExit or other BaseException that also inherits it
    among them, is never a verdict; and ``malformed`` must still pass
    _plain_exception_class, since extractor code that ran in the call may have
    reassigned its __bases__ so that it no longer subclasses Exception. Both
    checks read only the real type and the builtin subtype path, so neither
    can raise or run extractor code. The text is read under _guarded_text: a
    verdict whose text is not an exact str is not trusted as a content
    verdict."""
    if type(error) is not malformed or not _plain_exception_class(malformed):
        return None
    return _guarded_text(lambda: str(error), None)


def _load_release_date_tool():
    # Any failure to load, a missing or unreadable file, a SyntaxError, or an
    # exception raised while the module runs, SystemExit included, means the
    # extractor is unavailable: exit 3, never the drift exit 1 a stray
    # traceback would give, nor the code a SystemExit carries (row 58).
    # Fix round 4 (F1): any BaseException but an interrupt, and the report
    # describes the error through _describe, never its repr. Fix round 8: an
    # interrupt is only what _is_interrupt lets through.
    try:
        spec = importlib.util.spec_from_file_location("skill_release_date", RELEASE_DATE_TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except BaseException as error:
        if _is_interrupt(error):
            raise
        _unavailable(f"could not load {RELEASE_DATE_TOOL.name} (the extractor is unavailable): {_describe(error)}")
    for name, kind in RELEASE_DATE_API:
        try:
            usable = _api_kind_ok(getattr(module, name), kind)
        except BaseException as error:
            if _is_interrupt(error):
                raise
            usable = False
        if not usable:
            _unavailable(
                f"{RELEASE_DATE_TOOL.name} lacks a usable {name} (expected {kind}), "
                f"so the extractor is unavailable"
            )
    return module


# None until load_release_date_tool runs inside main: loading at import would
# exit 3 before main, so a load failure would hide the checksum comparison.
RELEASE_DATE = None


def load_release_date_tool() -> int:
    """Load the extractor if it is not loaded yet. Returns 0, or 3 after
    reporting why the extractor is unavailable; a failed load is retried at
    the next use."""
    global RELEASE_DATE
    if RELEASE_DATE is None:
        try:
            RELEASE_DATE = _load_release_date_tool()
        except SystemExit as stop:
            if stop.code != 3:
                raise
            return 3
    return 0


class ReleaseDateMalformed(Exception):
    """The extractor's ``Malformed`` verdict on content, re-raised under a
    class this gate owns, so no caller looks the extractor class up."""


def release_date_attr(name: str):
    """Return the attribute ``name`` of the loaded extractor, validated again
    against its declared kind, since the module can change after it loads. A
    lookup or validation that fails, a value no longer of its kind, or an
    extractor that cannot be loaded, exits 3 as unavailable, never as a
    drift."""
    if load_release_date_tool() != 0:
        raise SystemExit(3)
    kind = dict(RELEASE_DATE_API)[name]
    try:
        value = getattr(RELEASE_DATE, name)
        usable = _api_kind_ok(value, kind)
    except BaseException as error:
        if _is_interrupt(error):
            raise
        _unavailable(f"{RELEASE_DATE_TOOL.name} lacks {name}: {_describe(error)}")
    if not usable:
        _unavailable(
            f"{RELEASE_DATE_TOOL.name} lacks a usable {name} (expected {kind}), "
            f"so the extractor is unavailable"
        )
    return value


def release_date_call(name: str, *args):
    """Call the function ``name`` of the loaded extractor, resolving it here.

    Its ``Malformed`` verdict on content is raised as ``ReleaseDateMalformed``;
    any other exception or SystemExit, including a function or class that has
    gone missing or is not callable, means the extractor itself failed, which
    exits 3 as unavailable, never as a content verdict, a pass, or a drift.
    So does a returned value not of the exact type RELEASE_DATE_RESULTS
    names, and the handler runs extractor code only under a guard."""
    function = release_date_attr(name)
    malformed = release_date_attr("Malformed")
    try:
        result = function(*args)
    except BaseException as error:
        if _is_interrupt(error):
            raise
        verdict = _malformed_verdict(error, malformed)
        if verdict is not None:
            raise ReleaseDateMalformed(verdict) from None
        _unavailable(f"{RELEASE_DATE_TOOL.name} failed unexpectedly in {name}: {_describe(error)}")
    allowed, expected = RELEASE_DATE_RESULTS[name]
    if not any(type(result) is kind for kind in allowed):
        _unavailable(
            f"{RELEASE_DATE_TOOL.name} returned an unusable result from {name} "
            f"(expected {expected}), so the extractor is unavailable"
        )
    return result


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
    baseline = release_date_attr("BASELINE_VERSION")
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
    its extractor load, which the pre-tag window also reads so that it says
    there is nothing to reconcile only when the gate passes."""
    require_regular_file(VERIFY_PAGE, str(VERIFY_PAGE.relative_to(REPO_ROOT)))
    # A required file that cannot be read or decoded exits 3, never an
    # uncaught traceback (exit 1, drift); main still combines it with the
    # extractor load result.
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
        # and the extractor load both pass, so the gate then exits 0.
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
    """Run the gate. The extractor is loaded here, inside the protected path,
    so a load failure contributes exit 3 while the checksum comparison still
    runs and reports; the most severe code wins (3 over 2 over 1 over 0). The
    exception is a KeyboardInterrupt the extractor raises while it loads that
    _is_interrupt lets through as an interrupt, so the gate ends with the
    SIGINT status before the comparison runs (see the residual in the module
    docstring)."""
    load_code = load_release_date_tool()
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
