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
  - If the release ``vX`` for that version is not published yet, there is no
    drift to report: the site is legitimately ahead of the release, which the
    release workflow's own precondition requires. Passes.
  - If the release exists, downloads the version-named zip and its ``.sha256``,
    proves the release is self-consistent (the zip hashes to its own manifest),
    and requires the site's displayed checksum to equal that published digest.

Requires the ``gh`` CLI and, in CI, ``GH_TOKEN`` with ``contents: read``.

Exit codes:
  0  the site checksum matches the published release, or the release is not yet
     published (nothing to reconcile)
  1  drift: the release is published but the site shows a different checksum
  2  could not verify (gh or network error, or the published release is malformed)
  3  a required file could not be read
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERIFY_PAGE = REPO_ROOT / "site" / "verify" / "index.html"
REPO = "jposluns/cleanlanguage"

DISPLAYED_SUM = re.compile(r'<code id="published-checksum">([^<]*)</code>')
DISPLAYED_VERSION = re.compile(r"published checksum for version ([0-9][0-9.]*) is")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def die(message: str) -> None:
    print(f"check-release-checksum-live: {message}", file=sys.stderr)
    raise SystemExit(3)


def cannot_verify(message: str) -> None:
    print(f"check-release-checksum-live: could not verify: {message}", file=sys.stderr)
    raise SystemExit(2)


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=check)


def release_status(tag: str) -> int:
    """Return the HTTP status for the release, mirroring the release workflow.

    A transient error must not read as "no release", so a status this cannot
    parse is treated as unverifiable rather than as a 404.
    """
    try:
        proc = gh(
            "api", "--include", "--silent",
            f"repos/{REPO}/releases/tags/{tag}", check=False,
        )
    except FileNotFoundError:
        cannot_verify("the gh CLI is not available")
    codes = re.findall(r"^HTTP/[0-9.]+ (\d{3})", proc.stdout + proc.stderr, re.M)
    if not codes:
        cannot_verify(
            f"could not read the release status for {tag} (gh exit {proc.returncode})"
        )
    return int(codes[-1])


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
        print(
            f"Release {tag} is not published yet; the site names {version} ahead of "
            f"the release, which is expected before the tag. Nothing to reconcile."
        )
        return 0
    if status != 200:
        cannot_verify(f"unexpected HTTP {status} reading release {tag}")

    with tempfile.TemporaryDirectory() as tmp:
        try:
            gh(
                "release", "download", tag, "--dir", tmp, "--clobber",
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
