#!/usr/bin/env python3
"""Point the site at a release: direct asset links, redirects, and the checksum.

The site links straight at published release assets so a reader or a crawler sees
the real URL and can copy it elsewhere. That puts the version in the pages, so
every release has to rewrite them. This does that rewriting in one place, and
`check-release-links.py` verifies the result.

It is the writer; that check is the reader. Keeping them apart means the release
workflow cannot quietly disagree with the gate, because the gate runs against
whatever this produced.

What it updates
---------------

* ``site/_redirects``: the short shareable paths, still pointing at the
  version-named assets.
* ``site/install/index.html``: both download buttons.
* ``site/verify/index.html``: the download button, the link to the checksum file,
  the displayed checksum value, and the version named beside it.

The stable ``cleanlanguage.zip`` is deliberately not linked from the site. It
exists as an always-latest URL to share by hand; the site serves version-named
files so repeat downloads stay distinguishable in a Downloads folder.

Usage
-----

    tools/set-release-links.py --version 1.0.12 --checksum <sha256>

``--tag`` defaults to ``v<version>``. ``--check`` reports what would change and
exits non-zero if anything would, without writing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE = REPO_ROOT / "site"
REPO_SLUG = "jposluns/cleanlanguage"

SHA256 = re.compile(r"^[0-9a-f]{64}$")
ANY_RELEASE_URL = re.compile(
    rf"https://github\.com/{re.escape(REPO_SLUG)}/releases/download/"
    rf"[^/\"\s]+/cleanlanguage-[0-9][0-9.]*\.zip(\.sha256)?"
)


def die(message: str) -> None:
    print(f"set-release-links: {message}", file=sys.stderr)
    raise SystemExit(2)


def redirects_body(zip_url: str, sum_url: str) -> str:
    return (
        f"/claude/download {zip_url} 302\n"
        f"/download {zip_url} 302\n"
        f"/download/checksum {sum_url} 302\n"
        f"/downloads/cleanlanguage-instructions.txt /downloads/cleanlanguage-short.md 301\n"
        f"/downloads/clean-language-instructions.txt /downloads/cleanlanguage-short.md 301\n"
    )


def rewrite(version: str, tag: str, checksum: str) -> dict[Path, str]:
    base = f"https://github.com/{REPO_SLUG}/releases/download/{tag}"
    zip_url = f"{base}/cleanlanguage-{version}.zip"
    sum_url = f"{zip_url}.sha256"

    planned: dict[Path, str] = {SITE / "_redirects": redirects_body(zip_url, sum_url)}

    for name in ("install/index.html", "verify/index.html"):
        path = SITE / name
        if not path.is_file():
            die(f"{path.relative_to(REPO_ROOT)} does not exist")
        text = path.read_text(encoding="utf-8")

        # Any existing release URL becomes this release's, keeping the .sha256
        # suffix where the original had one.
        def swap(match: re.Match[str]) -> str:
            return sum_url if match.group(1) else zip_url

        text = ANY_RELEASE_URL.sub(swap, text)

        if name.startswith("verify"):
            text, n = re.subn(
                r'(<code id="published-checksum">)[^<]*(</code>)',
                lambda m: m.group(1) + checksum + m.group(2),
                text,
            )
            if n != 1:
                die(f"expected one published-checksum block in {name}, found {n}")
            text, n = re.subn(
                r"(published checksum for version )[0-9][0-9.]*( is)",
                lambda m: m.group(1) + version + m.group(2),
                text,
            )
            if n != 1:
                die(f"expected one checksum version sentence in {name}, found {n}")
            # Bare version-named filenames in the hash commands must also name
            # this release, not only the URLs.
            text = re.sub(r"cleanlanguage-[0-9][0-9.]*\.zip",
                          f"cleanlanguage-{version}.zip", text)

        planned[path] = text
    return planned


def main() -> int:
    parser = argparse.ArgumentParser(description="Point the site at a release.")
    parser.add_argument("--version", required=True, help="release version, for example 1.0.12")
    parser.add_argument("--tag", default=None, help="release tag; defaults to v<version>")
    parser.add_argument("--checksum", required=True, help="SHA-256 of the version-named zip")
    parser.add_argument("--check", action="store_true", help="report changes without writing")
    args = parser.parse_args()

    if not re.match(r"^[0-9][0-9.]*$", args.version):
        die(f"{args.version!r} is not a version number")
    checksum = args.checksum.strip().split()[0] if args.checksum.strip() else ""
    if not SHA256.match(checksum):
        die(f"{args.checksum!r} is not a 64 character lower-case SHA-256")
    tag = args.tag or f"v{args.version}"

    planned = rewrite(args.version, tag, checksum)

    changed = []
    for path, new_text in planned.items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current != new_text:
            changed.append(path.relative_to(REPO_ROOT).as_posix())
            if not args.check:
                path.write_text(new_text, encoding="utf-8")

    if not changed:
        print(f"The site already points at {tag}; nothing to change.")
        return 0

    verb = "would change" if args.check else "updated"
    print(f"{verb} for {tag}:")
    for name in changed:
        print(f"  {name}")
    return 1 if args.check else 0


if __name__ == "__main__":
    sys.exit(main())
