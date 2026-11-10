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
  version-named assets, and the fixed redirects kept since promotion (the old
  download names, ``/privacy`` and the old icon paths), so a release never
  drops them.
* ``site-src/release.json``: the version, tag and checksum that every version
  string of the generated pages comes from.
* The generated pages under ``site/``, regenerated in-process by
  ``tools/build-site.py`` with those values: the download blocks of the install
  and verify pages, their version labels, the displayed checksum and the
  version named beside it, the file names in the hash commands, the install
  page's example file name, and any other page that shows a release value.
* ``site-src/site.json``: the ``modified`` date of every indexable page whose
  output this run changes, set to ``--date``, so the regenerated page carries
  that ``article:modified_time`` and JSON-LD ``dateModified`` and the
  page-metadata gate still passes on the pull request this rewrite feeds.
  ``site/sitemap.xml`` is regenerated separately by
  ``tools/generate-sitemap.py``; this writer does not edit it.

The stable ``cleanlanguage.zip`` is deliberately not linked from the site. It
exists as an always-latest URL to share by hand; the site serves version-named
files so repeat downloads stay distinguishable in a Downloads folder.

Usage
-----

    tools/set-release-links.py --version 1.0.12 --checksum <sha256> --date 2026-09-01

``--tag`` defaults to ``v<version>``. ``--check`` reports what would change and
exits non-zero if anything would, without writing. ``--checksum`` is the zero
placeholder until the release is published, and the published checksum after
that; a checksum other than the placeholder with 56 or more of its 64 digits 0,
such as a mistyped placeholder, is refused (exit 2). A ``tools/build-site.py``
that is not a regular file, that cannot be read, compiled or run, or that
defines no ``build()``, ``BuildError`` or ``Unreadable`` is refused with the
same exit 2, the exit of every refusal this writer makes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import stat
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE = REPO_ROOT / "site"
REPO_SLUG = "jposluns/cleanlanguage"

SHA256 = re.compile(r"^[0-9a-f]{64}$")
# The zero placeholder a version bump passes until the release is published. A checksum other than it with at least
# NEAR_PLACEHOLDER_ZEROS 0 digits of its 64, such as a mistyped placeholder, is refused, as tools/build-site.py
# and tools/check-release-links.py refuse it; a real SHA-256 has that many with a probability of about 10^-58.
PLACEHOLDER = "0" * 64
NEAR_PLACEHOLDER_ZEROS = 56


def die(message: str) -> None:
    print(f"set-release-links: {message}", file=sys.stderr)
    raise SystemExit(2)


def redirects_body(zip_url: str, sum_url: str) -> str:
    return (
        f"/claude/download {zip_url} 302\n"
        f"/download {zip_url} 302\n"
        f"/download/checksum {sum_url} 302\n"
        f"/downloads/cleanlanguage-instructions.txt /downloads/cleanlanguage-11k.md 301\n"
        f"/downloads/clean-language-instructions.txt /downloads/cleanlanguage-11k.md 301\n"
        f"/downloads/cleanlanguage-short.md /downloads/cleanlanguage-11k.md 301\n"
        f"/privacy https://posluns.ca/privacy/ 301\n"
        f"/privacy/ https://posluns.ca/privacy/ 301\n"
        f"/favicon.svg /assets/baseline/logos/cleanlanguage-favicon.svg 301\n"
        f"/apple-touch-icon.png /assets/baseline/logos/cleanlanguage-touch.png 301\n"
    )


def stamp_modified(text: str, page_id: str, date: str) -> str:
    """Set the ``modified`` date of 1 page entry in the text of site-src/site.json, keeping its layout.

    The page-metadata gate requires article:modified_time and JSON-LD
    dateModified to be no older than the file's last change, so a release that
    rewrites a page must also restamp it.
    """
    pattern = r'(\{"id": "' + re.escape(page_id) + r'", [^\n]*?"modified": ")[0-9]{4}-[0-9]{2}-[0-9]{2}(")'
    text, n = re.subn(pattern, lambda m: m.group(1) + date + m.group(2), text)
    if n != 1:
        die(f"expected one modified date for page {page_id!r} in site-src/site.json, found {n}")
    return text


def rewrite(version: str, tag: str, checksum: str, date: str) -> dict[Path, str | bytes]:
    base = f"https://github.com/{REPO_SLUG}/releases/download/{tag}"
    zip_url = f"{base}/cleanlanguage-{version}.zip"
    sum_url = f"{zip_url}.sha256"

    planned: dict[Path, str | bytes] = {SITE / "_redirects": redirects_body(zip_url, sum_url)}
    release = {"version": version, "tag": tag, "checksum": checksum}
    planned[REPO_ROOT / "site-src" / "release.json"] = json.dumps(release, indent=2) + "\n"
    planned.update(site_pages(release, date))
    return planned


def load_generator():
    """tools/build-site.py, read, compiled and run as a fresh module. The source is always read, so no cached bytecode
    stands in for it; a source that is not a regular file, or that cannot be read, compiled or run, or that defines no
    build(), BuildError or Unreadable, is refused (exit 2)."""
    path = REPO_ROOT / "tools" / "build-site.py"
    try:
        info = os.lstat(path)
    except OSError as error:
        die(f"tools/build-site.py could not be read: {error}")
    if not stat.S_ISREG(info.st_mode):
        die("tools/build-site.py is not a regular file")
    try:
        source = path.read_bytes()
    except OSError as error:
        die(f"tools/build-site.py could not be read: {error}")
    module = types.ModuleType("build_site")
    module.__file__ = str(path)
    try:
        exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    except (Exception, SystemExit) as error:
        die(f"tools/build-site.py could not be loaded: {error!r}")
    for attribute in ("build", "BuildError", "Unreadable"):
        if not hasattr(module, attribute):
            die(f"tools/build-site.py defines no {attribute}")
    return module


def output_name(page: dict) -> str:
    return page["path"] if page["path"].endswith(".html") else page["path"] + "index.html"


def site_pages(release: dict, date: str) -> dict[Path, str | bytes]:
    """The generated pages with this release's values, and site.json restamped for each page that changes.

    A page changes when its regenerated output differs from the committed file. Only an
    indexable page carries a modified date, so a noindex page is regenerated but never stamped.
    """
    module = load_generator()
    site_json = REPO_ROOT / "site-src" / "site.json"
    try:
        original = site_json.read_text(encoding="utf-8")
        pages = json.loads(original)["pages"]
        names = [(page["id"], output_name(page), bool(page.get("noindex"))) for page in pages]
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        die(f"site-src/site.json could not be read: {error}")
    planned: dict[Path, str | bytes] = {}
    try:
        out, outputs, _ = module.build(REPO_ROOT, release=release, config=json.loads(original))
        text = original
        for page_id, name, noindex in names:
            path = REPO_ROOT / out / name
            current = path.read_bytes() if path.is_file() else None
            if not noindex and outputs[name] != current:
                text = stamp_modified(text, page_id, date)
        if text != original:
            planned[site_json] = text
            out, outputs, _ = module.build(REPO_ROOT, release=release, config=json.loads(text))
    except (module.BuildError, module.Unreadable) as error:
        die(f"the site pages could not be regenerated: {error}")
    planned.update({REPO_ROOT / out / name: data for name, data in outputs.items()})
    return planned


def main() -> int:
    parser = argparse.ArgumentParser(description="Point the site at a release.")
    parser.add_argument("--version", required=True, help="release version, for example 1.0.12")
    parser.add_argument("--tag", default=None, help="release tag; defaults to v<version>")
    parser.add_argument("--checksum", required=True, help="SHA-256 of the version-named zip")
    parser.add_argument(
        "--date",
        required=True,
        help="date to stamp as modified on the pages this run changes, YYYY-MM-DD",
    )
    parser.add_argument("--check", action="store_true", help="report changes without writing")
    args = parser.parse_args()

    if not re.match(r"^[0-9][0-9.]*$", args.version):
        die(f"{args.version!r} is not a version number")
    checksum = args.checksum.strip().split()[0] if args.checksum.strip() else ""
    if not SHA256.match(checksum):
        die(f"{args.checksum!r} is not a 64 character lower-case SHA-256")
    if checksum != PLACEHOLDER and checksum.count("0") >= NEAR_PLACEHOLDER_ZEROS:
        die(
            f"{checksum} is not the zero placeholder but has {checksum.count('0')} of its 64 digits 0, such as "
            "a mistyped placeholder; pass the zero placeholder until the release is published, and the "
            "published release checksum after that"
        )
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", args.date):
        die(f"{args.date!r} is not a YYYY-MM-DD date")
    try:
        dt.date.fromisoformat(args.date)
    except ValueError:
        die(f"{args.date!r} is not a real calendar date")
    tag = args.tag or f"v{args.version}"

    planned = rewrite(args.version, tag, checksum, args.date)

    changed = []
    for path, new_text in planned.items():
        new_bytes = new_text if isinstance(new_text, bytes) else new_text.encode("utf-8")
        current = path.read_bytes() if path.is_file() else None
        if current != new_bytes:
            changed.append(path.relative_to(REPO_ROOT).as_posix())
            if not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(new_bytes)

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
