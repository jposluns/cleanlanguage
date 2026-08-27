#!/usr/bin/env python3
"""Check that every release link on the site names the current version.

The site links straight at the published release assets rather than through a
redirect, so a reader or a crawler sees the real URL and can copy it. The cost of
that choice is that the version now appears in the pages themselves, in more than
one place, and every one of them goes stale the moment a release ships.

This makes that failure loud. Without it, a stale link still returns a file, just
the wrong one: an old version, silently, with a checksum on the page that does not
match what the reader downloaded. Nothing else in the build would notice, because
the markup is valid and the URL resolves.

What it verifies
----------------

1. Every release-asset URL under ``site/`` names one and the same version.
2. That version matches ``Version:`` in ``cleanlanguage/SKILL.md``, which is the
   source of truth the release workflow validates the tag against.
3. The tag in each URL is that version prefixed with ``v``.
4. The published checksum displayed on the verify page is a well-formed SHA-256,
   and the version named in the sentence above it agrees with the links.
5. ``site/_redirects`` names the same version, so the shareable short paths and
   the direct links cannot point at different releases.

What it does not verify
-----------------------

It does not fetch anything. It cannot tell whether the displayed checksum is the
true value of the published asset, only that it is well formed and consistent within
the site. Confirming the value against the release requires the network and is
done by the orchestrator's post-release site flip, which reads the published checksum.

Exit codes:
  0  every release link and the displayed checksum agree with SKILL.md
  1  something disagrees
  3  a required file could not be read
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_ROOT = REPO_ROOT / "site"
SKILL = REPO_ROOT / "cleanlanguage" / "SKILL.md"
REDIRECTS = SITE_ROOT / "_redirects"
VERIFY_PAGE = SITE_ROOT / "verify" / "index.html"

RELEASE_URL = re.compile(
    r"https://github\.com/jposluns/cleanlanguage/releases/download/"
    r"(?P<tag>[^/\"\s]+)/cleanlanguage-(?P<version>[0-9][0-9.]*)\.zip(?:\.sha256)?"
)
SKILL_VERSION = re.compile(r"^Version:\s*([0-9][0-9.]*)", re.M)
DISPLAYED_SUM = re.compile(r'<code id="published-checksum">([^<]*)</code>')
DISPLAYED_VERSION = re.compile(r"published checksum for version ([0-9][0-9.]*) is")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def die(message: str) -> None:
    print(f"check-release-links: {message}", file=sys.stderr)
    raise SystemExit(3)


def main() -> int:
    for path in (SKILL, REDIRECTS, VERIFY_PAGE):
        if not path.is_file():
            die(f"{path.relative_to(REPO_ROOT)} does not exist")

    match = SKILL_VERSION.search(SKILL.read_text(encoding="utf-8"))
    if match is None:
        die("no 'Version:' line found in cleanlanguage/SKILL.md")
    expected = match.group(1)

    problems: list[str] = []
    found: dict[str, list[str]] = {}

    for path in sorted(SITE_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in {".html", ""} or path.name.startswith("."):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        for hit in RELEASE_URL.finditer(text):
            version, tag = hit.group("version"), hit.group("tag")
            found.setdefault(version, []).append(relative)
            if version != expected:
                problems.append(
                    f"{relative} links at version {version}, but SKILL.md says {expected}"
                )
            if tag != f"v{version}":
                problems.append(f"{relative} uses tag {tag} for version {version}")

    if not found:
        die(f"no release-asset URLs found under {SITE_ROOT.relative_to(REPO_ROOT)}")

    redirects = REDIRECTS.read_text(encoding="utf-8")
    if not RELEASE_URL.search(redirects):
        problems.append("site/_redirects contains no release-asset URL")

    verify = VERIFY_PAGE.read_text(encoding="utf-8")
    shown = DISPLAYED_SUM.search(verify)
    if shown is None:
        problems.append('the verify page has no <code id="published-checksum"> block')
    elif not SHA256.match(shown.group(1).strip()):
        problems.append(
            f"the displayed checksum {shown.group(1).strip()!r} is not a 64 character "
            f"lower-case SHA-256"
        )

    stated = DISPLAYED_VERSION.search(verify)
    if stated is None:
        problems.append("the verify page does not state which version its checksum belongs to")
    elif stated.group(1) != expected:
        problems.append(
            f"the verify page says its checksum is for version {stated.group(1)}, "
            f"but SKILL.md says {expected}"
        )

    if problems:
        print("Release link problems found:")
        for problem in dict.fromkeys(problems):
            print(f"  - {problem}")
        print(
            f"\nFlip the site with tools/set-release-links.py using the published "
            f"release checksum (see the release runbook), or update the version and "
            f"checksum by hand, so the site matches SKILL.md ({expected})."
        )
        return 1

    places = sum(len(v) for v in found.values())
    print(
        f"Every release link on the site names version {expected} "
        f"({places} across {len(set(sum(found.values(), [])))} files), "
        f"and the displayed checksum is well formed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
