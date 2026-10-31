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
    release runbook creates. A different version with no release is a real
    inconsistency and fails. An existing tag with no published release is a
    deleted or unfinished release and reads as unverifiable. One broken state
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
    means the release is not published yet and the date check is skipped,
    while an existing tag, or a tag whose status cannot be read, cannot be
    verified; any other release status cannot be verified. The line may be
    absent only when that version is at or below the undated baseline
    declared in ``tools/skill-release-date.py``; the line and that rule are
    read first, and then no network call is made for the date check at all.
    The meaning of ``published_at`` is an assumption,
    isolated in ``release_day_from_published_at`` in that tool; see its
    docstring.

Requires the ``gh`` CLI and, in CI, ``GH_TOKEN`` with ``contents: read``.

Exit codes:
  0  the site checksum matches the published release, or the site is
     legitimately ahead of an unpublished release (it names the current skill
     version and the tag does not exist yet)
  1  drift or inconsistency: the release is published but the site shows a
     different checksum, or the site names an unreleased version that is not
     the current skill version, or the SKILL.md Released date disagrees with
     the published release (or is missing above the undated baseline)
  2  could not verify (gh or network error, the published release is malformed,
     its ``published_at`` is unreadable or malformed, its ``immutable`` field is
     not exactly true, the release SKILL.md names returns a status other than
     200 or 404, or the tag exists with no published release)
  3  a required file could not be read, the SKILL.md Released line is
     malformed, or tools/skill-release-date.py could not be loaded, lacks a
     usable attribute this gate uses (see RELEASE_DATE_API), or failed
     unexpectedly

The release-date check and the site-checksum comparison both run and both
are reported when the release the site names is published, including when its
download fails or its manifest is malformed, and when the site names an
unreleased version that is not the current skill version, so neither failure
hides the other. The extractor is loaded inside main, not at import, so a load
failure is reported and contributes exit 3 while the checksum comparison still
runs and reports. The gate then exits with the most severe code, the highest
one (3 over 2 over 1 over 0), since 2 and 3 mean a check could not complete.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
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
    if kind == "a function":
        return callable(value)
    if kind == "an exception class":
        return isinstance(value, type) and issubclass(value, Exception)
    return isinstance(value, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value) is not None


def _unavailable(message: str) -> None:
    print(f"check-release-checksum-live: {message}", file=sys.stderr)
    raise SystemExit(3)


def _load_release_date_tool():
    # Any failure to load, a missing or unreadable file, a SyntaxError, or an
    # exception raised while the module runs, means the extractor is
    # unavailable: exit 3, never the drift exit 1 a stray traceback would give.
    try:
        spec = importlib.util.spec_from_file_location("skill_release_date", RELEASE_DATE_TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as error:
        _unavailable(f"could not load {RELEASE_DATE_TOOL.name} (the extractor is unavailable): {error!r}")
    for name, kind in RELEASE_DATE_API:
        try:
            usable = _api_kind_ok(getattr(module, name), kind)
        except Exception:
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
    """Return the attribute ``name`` of the loaded extractor. A lookup that
    fails, or an extractor that cannot be loaded, exits 3 as unavailable,
    never as a drift."""
    if load_release_date_tool() != 0:
        raise SystemExit(3)
    try:
        return getattr(RELEASE_DATE, name)
    except Exception as error:
        _unavailable(f"{RELEASE_DATE_TOOL.name} lacks {name}: {error!r}")


def release_date_call(name: str, *args):
    """Call the function ``name`` of the loaded extractor, resolving it here.

    Its ``Malformed`` verdict on content is raised as ``ReleaseDateMalformed``;
    any other exception, including a function or class that has gone missing
    or is not callable, means the extractor itself failed, which exits 3 as
    unavailable, never as a content verdict or a drift."""
    function = release_date_attr(name)
    malformed = release_date_attr("Malformed")
    try:
        return function(*args)
    except Exception as error:
        if isinstance(malformed, type) and issubclass(malformed, Exception) and isinstance(error, malformed):
            raise ReleaseDateMalformed(str(error)) from None
        _unavailable(f"{RELEASE_DATE_TOOL.name} failed unexpectedly in {name}: {error!r}")


def die(message: str) -> None:
    print(f"check-release-checksum-live: {message}", file=sys.stderr)
    raise SystemExit(3)


def cannot_verify(message: str) -> None:
    print(f"check-release-checksum-live: could not verify: {message}", file=sys.stderr)
    raise SystemExit(2)


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
    if not SKILL.is_file():
        die(f"{SKILL.relative_to(REPO_ROOT)} does not exist")
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
    if not SKILL.is_file():
        die(f"{SKILL.relative_to(REPO_ROOT)} does not exist")
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


def check_release_date(site_version: str, site_status: int) -> bool:
    """G4 (item 26): check the release SKILL.md names, on its own terms.

    The release probed is the one for the SKILL.md version, whatever version
    the site names, so a site that still names the previous release cannot
    hide a wrong date on a published newer one. Returns False (after printing
    why) on an inconsistency; exits 2 when the state cannot be verified."""
    current = skill_version()
    tag = f"v{current}"
    # The line and the baseline rule are read first: an undated release at or
    # below the baseline checks no date, so it makes no network call at all.
    released = skill_released()
    try:
        required = released is None and release_date_call("requires_release_date", current)
    except ReleaseDateMalformed as error:
        die(f"the SKILL.md version {current} was rejected by the extractor: {error}")
    if released is None and not required:
        return True
    status = site_status if current == site_version else release_status(tag)
    if status == 404:
        # As on the same-version path in main: only a confirmed absent tag
        # means the release is not published yet. An existing tag with no
        # release is a deleted or failed release, and a tag status that cannot
        # be read cannot be verified.
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
        return True
    if status != 200:
        cannot_verify(f"unexpected HTTP {status} reading release {tag}, the version SKILL.md names")
    if released is None:
        baseline = release_date_attr("BASELINE_VERSION")
        print("Release date inconsistency found:")
        print(f"  - release {tag} is published")
        print(
            f"  - cleanlanguage/skills/cleanlanguage/SKILL.md names {current}, above the "
            f"undated baseline {baseline}, but has no Released: line"
        )
        return False
    # The date comparison relies on published_at still being the first
    # publication instant; an immutable release cannot have had its assets
    # replaced since, so anything but exactly true cannot be verified.
    immutable = release_immutable(tag)
    if immutable != "true":
        cannot_verify(
            f"the immutable field of release {tag} is {immutable!r}, not true, so its "
            f"published_at cannot be relied on as the first publication instant"
        )
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
            "version whose Released line names its own publication day. The "
            "first-publication readback the release workflow printed when it "
            "created the release (its run log) records the day GitHub recorded."
        )
        return False
    print(f"The SKILL.md Released date {released} matches the publication day of release {tag}.")
    return True


def release_date_code(site_version: str, site_status: int) -> int:
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
        if not zip_path.is_file() or not manifest_path.is_file():
            cannot_verify(f"release {tag} is missing {zip_name} or {manifest_name}")

        # The manifest must be exactly one line: a 64-hex digest, two spaces, and
        # the expected basename. A crafted path inside it cannot redirect the check.
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
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


def check_site_checksum() -> int:
    """Check the site checksum and the release date, returning the most
    severe code of the checks that ran (0 to 3), or stopping with 2 or 3 when
    the gate cannot go on; main combines it with the extractor load."""
    if not VERIFY_PAGE.is_file():
        die(f"{VERIFY_PAGE.relative_to(REPO_ROOT)} does not exist")
    verify = VERIFY_PAGE.read_text(encoding="utf-8")

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

    status = release_status(tag)
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
        tag_state = tag_status(tag)
        if tag_state == 200:
            cannot_verify(
                f"tag {tag} exists but release {tag} is not published; if a release "
                f"run is publishing {tag} right now, re-run this check once it "
                f"completes, and otherwise the release was deleted or its publish failed"
            )
        if tag_state != 404:
            cannot_verify(f"unexpected HTTP {tag_state} reading tag {tag}")
        print(
            f"Release {tag} is not published yet; the site and SKILL.md both name "
            f"{version} ahead of the release, which is expected before the tag. "
            f"Nothing to reconcile."
        )
        return 0
    if status != 200:
        cannot_verify(f"unexpected HTTP {status} reading release {tag}")

    # A failed download or a malformed release stops only the checksum
    # comparison (exit 2); the release-date check below still runs and reports.
    try:
        claimed = published_digest(tag, zip_name, manifest_name)
    except SystemExit as stop:
        if stop.code != 2:
            raise
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
    runs and reports; the most severe code wins (3 over 2 over 1 over 0)."""
    load_code = load_release_date_tool()
    try:
        code = check_site_checksum()
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
