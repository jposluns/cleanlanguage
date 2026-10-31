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
  - If the release exists and is the version SKILL.md names, also requires the
    SKILL.md ``Released:`` line (item 26) to name the UTC day of the release
    ``published_at`` record. The line may be absent only when that version is
    at or below the undated baseline declared in ``tools/skill-release-date.py``.
    The meaning of ``published_at`` is an assumption, isolated in
    ``release_day_from_published_at`` in that tool; see its docstring.

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
     its ``published_at`` is unreadable or malformed, or the tag exists with no
     published release)
  3  a required file could not be read, or the SKILL.md Released line is
     malformed
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


def _load_release_date_tool():
    try:
        spec = importlib.util.spec_from_file_location("skill_release_date", RELEASE_DATE_TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError, AttributeError) as error:
        print(
            f"check-release-checksum-live: could not load {RELEASE_DATE_TOOL.name}: {error}",
            file=sys.stderr,
        )
        raise SystemExit(3)
    return module


RELEASE_DATE = _load_release_date_tool()


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

    The value is interpreted only by ``RELEASE_DATE.release_day_from_published_at``,
    which states the assumption it rests on. A gh failure is unverifiable.
    """
    try:
        proc = gh("api", f"repos/{REPO}/releases/tags/{tag}", "--jq", ".published_at", check=False)
    except FileNotFoundError:
        cannot_verify("the gh CLI is not available")
    if proc.returncode != 0:
        cannot_verify(f"could not read published_at for release {tag} (gh exit {proc.returncode})")
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
        return RELEASE_DATE.extract(text)
    except RELEASE_DATE.Malformed as error:
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


def main() -> int:
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
            return 1
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

    # Item 26 (G4): once the release SKILL.md names is published, its Released
    # line must name the UTC day of that release published_at, so a date edited
    # after release, or a release that slipped past UTC midnight after the
    # release-time check fixed the date, goes red here.
    if version == skill_version():
        released = skill_released()
        if released is None:
            if RELEASE_DATE.requires_release_date(version):
                print("Release date inconsistency found:")
                print(f"  - release {tag} is published")
                print(
                    f"  - cleanlanguage/skills/cleanlanguage/SKILL.md names {version}, above the "
                    f"undated baseline {RELEASE_DATE.BASELINE_VERSION}, but has no Released: line"
                )
                return 1
        else:
            try:
                published_day = RELEASE_DATE.release_day_from_published_at(release_published_at(tag))
            except RELEASE_DATE.Malformed as error:
                cannot_verify(f"the published_at of release {tag} is unusable: {error}")
            if released != published_day:
                print("Release date inconsistency found:")
                print(f"  - cleanlanguage/skills/cleanlanguage/SKILL.md says Released: {released}")
                print(f"  - release {tag} was published on {published_day} (UTC)")
                print(
                    "\nThe Released line must name the UTC day the release was first "
                    "published. Correct the line to match the release record."
                )
                return 1
            print(f"The SKILL.md Released date {released} matches the publication day of release {tag}.")

    if site_sum != claimed:
        print("Release checksum drift found:")
        print(f"  - the verify page shows {site_sum} for version {version}")
        print(f"  - the published {zip_name} is {claimed}")
        print(
            f"\nThe release {tag} is published but the site was not flipped to its "
            f"checksum. Run the orchestrator's post-release site flip "
            f"(tools/set-release-links.py with checksum {claimed}); see the release runbook."
        )
        return 1

    print(
        f"The verify page checksum {site_sum} matches the published {zip_name} "
        f"for release {tag}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
