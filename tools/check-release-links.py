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
2. That version matches ``Version:`` in ``cleanlanguage/skills/cleanlanguage/SKILL.md``, which is the
   source of truth the release workflow validates the tag against.
3. The tag in each URL is that version prefixed with ``v``.
4. The published checksum displayed on the verify page is a well-formed SHA-256,
   and the version named in the sentence above it agrees with the links; or,
   while the release is not yet published, the page names that version in its
   note that the checksum appears once that version is published.
5. ``site/_redirects`` names the same version, so the shareable short paths and
   the direct links cannot point at different releases.
6. Every version-named zip file name written out on a page outside a release
   URL, such as an example download name or the file in a hash command, names
   that same version, so a page cannot send the reader looking for an old file.
   This covers every page under ``site/``.
7. ``site-src/release.json``, the one source of every version string the
   generated pages show, names the same version, the tag ``v<version>``, and a
   well-formed checksum.
8. On the install and verify pages, every ``version X.Y.Z`` label names that
   version, and each page names the release at least once. The verify page is
   in 1 of 2 states, chosen by ``release.json``. With a published checksum, it
   displays exactly 1 checksum element, the same checksum as ``release.json``,
   and carries no not-yet-published note. With the zero placeholder a version
   bump writes, it carries that note exactly once, for that version, and no
   checksum element, no "published checksum" wording and no link to a
   ``.sha256`` file, so it never shows the placeholder as the published value.

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

import os
import re
import stat
import sys
from pathlib import Path
from typing import NoReturn

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_ROOT = REPO_ROOT / "site"
SKILL = REPO_ROOT / "cleanlanguage" / "skills" / "cleanlanguage" / "SKILL.md"
REDIRECTS = SITE_ROOT / "_redirects"
INSTALL_PAGE = SITE_ROOT / "install" / "index.html"
VERIFY_PAGE = SITE_ROOT / "verify" / "index.html"
RELEASE_JSON = REPO_ROOT / "site-src" / "release.json"

RELEASE_URL = re.compile(
    r"https://github\.com/jposluns/cleanlanguage/releases/download/"
    r"(?P<tag>[^/\"\s]+)/cleanlanguage-(?P<version>[0-9][0-9.]*)\.zip(?:\.sha256)?"
)
ZIP_NAME = re.compile(r"cleanlanguage-(?P<version>[0-9][0-9.]*)\.zip")
SKILL_VERSION = re.compile(r"^Version:[ \t]*([0-9]+\.[0-9]+\.[0-9]+)[ \t]*$", re.M)
VERSION_LINE = re.compile(r"^Version:[^\n]*", re.M)
# The verify page's checksum element exactly as tools/build-site.py writes it (the template's
# download block): no other attribute, such as hidden, passes.
DISPLAYED_SUM = re.compile(r'<code class="sum" id="published-checksum">([^<]*)</code>')
SUM_ELEMENT = '<code class="sum" id="published-checksum">'
DISPLAYED_VERSION = re.compile(r"published checksum for version ([0-9][0-9.]*) is")
# The verify page's note while release.json holds the zero placeholder, as tools/build-site.py writes it (sum_tokens).
PENDING_VERSION = re.compile(r"The checksum for version ([0-9][0-9.]*) appears here once that version is published\.")
PUBLISHED_WORDING = re.compile(r"published checksum", re.I)
PLACEHOLDER = "0" * 64
NAMED_ZIP = re.compile(r"cleanlanguage-([0-9][0-9.]*[0-9])\.zip")
VERSION_LABEL = re.compile(r"\bversion ([0-9]+\.[0-9]+\.[0-9]+)\b")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def die(message: str) -> NoReturn:
    print(f"check-release-links: {message}", file=sys.stderr)
    raise SystemExit(3)


def main() -> int:
    for path in (SKILL, REDIRECTS, INSTALL_PAGE, VERIFY_PAGE, RELEASE_JSON):
        try:
            info = path.stat()
        except FileNotFoundError:
            die(f"{path.relative_to(REPO_ROOT)} does not exist")
        except OSError as error:
            die(f"{path.relative_to(REPO_ROOT)} could not be read: {error}")
        # is_file() rejected non-regular files; preserve that so a fifo, socket,
        # or directory at a required path fails closed here instead of reaching a
        # read that could hang (a writer-less fifo) or consume unintended bytes.
        if not stat.S_ISREG(info.st_mode):
            die(f"{path.relative_to(REPO_ROOT)} is not a regular file")

    try:
        skill_text = SKILL.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        die(f"cleanlanguage/skills/cleanlanguage/SKILL.md could not be read: {error}")
    line = VERSION_LINE.search(skill_text)
    if line is None:
        die("no 'Version:' line found in cleanlanguage/skills/cleanlanguage/SKILL.md")
    match = SKILL_VERSION.match(line.group(0))
    if match is None:
        die("the first 'Version:' line in cleanlanguage/skills/cleanlanguage/SKILL.md is not a bare X.Y.Z version")
    expected = match.group(1)

    problems: list[str] = []
    found: dict[str, list[str]] = {}

    def collect_site_files(root: Path) -> list[Path]:
        # Walk site/ with os.scandir so every listing or classification error
        # fails closed. os.walk and Path.rglob both swallow such errors: a
        # directory that cannot be listed, or an entry whose is_dir() raises,
        # is silently dropped along with its subtree. Here each OSError, from
        # scandir or from is_dir, routes through die (exit 3), naming the path.
        found_paths: list[Path] = []
        stack = [root]
        while stack:
            directory = stack.pop()
            try:
                entries = list(os.scandir(directory))
            except OSError as error:
                die(f"{directory.relative_to(REPO_ROOT).as_posix()} could not be read: {error}")
            for entry in entries:
                entry_path = Path(entry.path)
                try:
                    is_directory = entry.is_dir(follow_symlinks=False)
                except OSError as error:
                    die(f"{entry_path.relative_to(REPO_ROOT).as_posix()} could not be read: {error}")
                if is_directory:
                    stack.append(entry_path)
                else:
                    found_paths.append(entry_path)
        return found_paths

    site_paths = collect_site_files(SITE_ROOT)

    for path in sorted(site_paths):
        if path.suffix not in {".html", ""} or path.name.startswith("."):
            continue
        try:
            mode = path.stat().st_mode
        except OSError as error:
            die(f"{path.relative_to(REPO_ROOT).as_posix()} could not be read: {error}")
        if not stat.S_ISREG(mode):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError) as error:
            die(f"{path.relative_to(REPO_ROOT).as_posix()} could not be read: {error}")
        relative = path.relative_to(REPO_ROOT).as_posix()
        url_spans: list[tuple[int, int]] = []
        for hit in RELEASE_URL.finditer(text):
            url_spans.append(hit.span())
            version, tag = hit.group("version"), hit.group("tag")
            found.setdefault(version, []).append(relative)
            if version != expected:
                problems.append(
                    f"{relative} links at version {version}, but SKILL.md says {expected}"
                )
            if tag != f"v{version}":
                problems.append(f"{relative} uses tag {tag} for version {version}")
        # A file name written out bare, outside a release URL, goes stale on a
        # release exactly as a link does. A name inside a URL is judged above.
        for name in ZIP_NAME.finditer(text):
            if any(start <= name.start() and name.end() <= end for start, end in url_spans):
                continue
            if name.group("version") != expected:
                problems.append(
                    f"{relative} names the file cleanlanguage-{name.group('version')}.zip, "
                    f"but SKILL.md says {expected}"
                )

    if not found:
        die(f"no release-asset URLs found under {SITE_ROOT.relative_to(REPO_ROOT)}")

    try:
        redirects = REDIRECTS.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        die(f"site/_redirects could not be read: {error}")
    if not RELEASE_URL.search(redirects):
        problems.append("site/_redirects contains no release-asset URL")

    try:
        verify = VERIFY_PAGE.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        die(f"site/verify/index.html could not be read: {error}")
    # The not-yet-published note names the version in place of the checksum and its sentence; check 8
    # holds each state to release.json and refuses a page that mixes them.
    pending = PENDING_VERSION.search(verify)
    if pending is not None:
        if pending.group(1) != expected:
            problems.append(
                f"the verify page says the checksum for version {pending.group(1)} appears once "
                f"that version is published, but SKILL.md says {expected}"
            )
    else:
        shown = DISPLAYED_SUM.search(verify)
        if shown is None:
            problems.append(f"the verify page has no {SUM_ELEMENT} block")
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

    problems += check_release_source(expected)

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
    state = (
        "the verify page says the checksum appears once that version is published"
        if pending is not None else "the displayed checksum is well formed"
    )
    print(
        f"Every release link on the site names version {expected} "
        f"({places} across {len(set(sum(found.values(), [])))} files), "
        f"and {state}."
    )
    return 0


def check_release_source(expected: str) -> list[str]:
    """Checks 7 and 8: release.json, and the install and verify pages generated from it.

    A stale bare file name on either page is check 6's (ZIP_NAME, site-wide), so it is
    not reported twice here; these pages must still name the release at least once."""
    import json

    problems: list[str] = []
    try:
        release = json.loads(RELEASE_JSON.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError) as error:
        die(f"site-src/release.json could not be read: {error}")
    if not isinstance(release, dict):
        die("site-src/release.json is not a JSON object")
    if release.get("version") != expected:
        problems.append(f"site-src/release.json names version {release.get('version')!r}, but SKILL.md says {expected}")
    if release.get("tag") != f"v{expected}":
        problems.append(f"site-src/release.json names tag {release.get('tag')!r}, not v{expected}")
    checksum = release.get("checksum")
    if not isinstance(checksum, str) or not SHA256.match(checksum):
        problems.append("site-src/release.json carries no 64 character lower-case SHA-256 checksum")
    for page in (INSTALL_PAGE, VERIFY_PAGE):
        relative = page.relative_to(REPO_ROOT).as_posix()
        try:
            text = page.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError) as error:
            die(f"{relative} could not be read: {error}")
        labels = set(VERSION_LABEL.findall(text))
        if not labels and not NAMED_ZIP.search(text):
            problems.append(f"{relative} names no release version")
        for version in sorted(labels - {expected}):
            problems.append(f"{relative} names version {version}, but SKILL.md says {expected}")
        if page == VERIFY_PAGE and checksum == PLACEHOLDER:
            # The release is not yet published: no value is called the published checksum, no link
            # names the checksum file, and the note names this version once.
            if DISPLAYED_SUM.search(text) or PUBLISHED_WORDING.search(text) or ".zip.sha256" in text:
                problems.append(
                    f"{relative} shows published checksum wording or links the checksum file, but "
                    f"site-src/release.json holds the zero placeholder"
                )
            if PENDING_VERSION.findall(text) != [expected]:
                problems.append(
                    f"{relative} must say once that the checksum for version {expected} appears here "
                    f"once that version is published"
                )
        elif page == VERIFY_PAGE:
            if PENDING_VERSION.search(text):
                problems.append(
                    f"{relative} says the checksum is not yet published, but site-src/release.json "
                    f"holds a published checksum"
                )
            shown = DISPLAYED_SUM.findall(text)
            if len(shown) != 1:
                problems.append(f"{relative} must show exactly 1 {SUM_ELEMENT}, found {len(shown)}")
            elif shown[0].strip() != checksum:
                problems.append(f"{relative} shows a checksum other than site-src/release.json")
            stated = DISPLAYED_VERSION.search(text)
            if stated is None or stated.group(1) != expected:
                problems.append(f"{relative} does not state that its checksum is for version {expected}")
    return problems


if __name__ == "__main__":
    sys.exit(main())
