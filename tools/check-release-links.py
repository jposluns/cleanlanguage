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
   while ``release.json`` holds the zero placeholder, the page names that
   version in its note that the checksum appears once that version is
   published.
5. ``site/_redirects`` names the same version, so the shareable short paths and
   the direct links cannot point at different releases.
6. Every version-named zip file name written out on a page outside a release
   URL, such as an example download name or the file in a hash command, names
   that same version, so a page cannot send the reader looking for an old file.
   This covers every page under ``site/``.
7. ``site-src/release.json``, the one source of every version string the
   generated pages show, names the same version, the tag ``v<version>``, and a
   well-formed checksum that is the zero placeholder or not close to it: a
   checksum other than the placeholder with 56 or more of its 64 digits 0
   (NEAR_PLACEHOLDER_ZEROS), such as a mistyped placeholder, fails, and
   ``tools/set-release-links.py`` and ``tools/build-site.py`` refuse it. A real
   SHA-256 has that many 0 digits with a probability of about 10^-58.
8. On the install and verify pages, every ``version X.Y.Z`` label names that
   version, and each page names the release at least once. The verify page is
   in 1 of 2 states, chosen by ``release.json``, and is checked against what
   the generator writes for that state. The gate is whole-page equality: the
   committed ``site/verify/index.html`` must equal, byte for byte, the page
   that ``tools/build-site.py`` renders for it at base / from the committed
   sources and ``release.json`` (rendered_verify_page, verify_page), checked
   once ``release.json`` names the SKILL.md version, its tag and a
   well-formed checksum. Any other page fails, whatever it adds, removes or
   hides: a reworded or contradicting step, a second checksum in any form,
   a template element or misnested markup around the download block, an
   inline script, or a carriage return. So does a page that a browser shows
   the same way, such as one with the html element's attributes in another
   order or a double space in step 1: the committed page is always the
   generator's render, so the remedy is to run ``tools/build-site.py``.
   ``tools/check-release-checksum-live.py`` holds the same page to the render
   for the version and checksum it shows. The equality holds the page to the
   generator, not the generator to what it should write: a change to
   ``site-src/pages/verify.html``, to the generator code that renders the
   page, or to what its head loads, that is regenerated passes it, and
   ``tools/test-build-site.py`` pins the whole rendered page in each state
   (VERIFY_PAGE_PIN), so a change to the page as rendered for the stand-in
   release fails there. The pin holds the page as rendered for a stand-in
   release (PIN_VERSION, PIN_CHECKSUM) and the stand-in date PIN_DATE, and
   the same test requires the page this gate renders, for ``release.json``
   at the ``modified`` dates in ``site-src/site.json``, and the render for
   that version with the checksum "a" * 64 and the verify page's
   ``modified`` date 2099-12-31, to be the pinned rendering of the same
   state with the stand-in values replaced (check_committed_render). A
   generator change that renders differently only for sets of release
   values and date that none of these renders uses passes the pin, that
   comparison and, once regenerated, this gate, until the committed
   ``release.json`` and verify page ``modified`` date become a set it
   renders differently for; the test runs on every pull request and push to
   ``main`` (``site-draft.yml``), so it fails then. For a
   clear report of what is wrong, the gate also applies the rule that both
   gates carry (download_block_problems): ``tools/build-site.py`` renders the
   page's download block, steps 1 to 3, for the SKILL.md version and the
   checksum in ``release.json`` (download_block, verify_download_block), and
   the page must
   carry that block exactly once, byte for byte, as a start tag that the parsed
   page opens inside exactly the elements build() writes around it
   (BLOCK_ANCESTORS), with 1 html and 1 body start tag. With a published
   checksum, the block holds the checksum element with that checksum, the
   sentence that names its version, the step 1 lead, the link to the checksum
   file and step 3; with the zero placeholder a version bump writes, it holds
   the note that the checksum appears once that version is published, and none
   of those. No other part of the page, comments, scripts and hidden elements
   included, may carry the checksum element's id, the class ``sum``, the
   not-yet-published note, "published checksum" wording, a 64 digit
   hexadecimal value (in its text, also in groups split by whitespace,
   hyphens or colons), a link to a ``.sha256`` file or to a path that
   ``site/_redirects`` sends there (a run of slashes read as 1), or a step
   that tells the reader not to install the file. A page whose comments nest
   too deeply for the rule's reader breaks the rule too, never an uncaught
   RecursionError. Outside the block the page is
   read both as written and as parsed markup (PageReader), in which an end tag
   does not close an element across a ``template``, ``table`` or other scope
   boundary. That reading models only that part of how a browser builds the
   page, so the rule alone passes some markup that hides the block in a
   browser; the equality refuses it. tools/check-release-checksum-live.py
   carries the rule verbatim. Where it gives a clearer report, the gate also
   names a published page that carries the not-yet-published note or shows a
   checksum other than ``release.json``. Neither the equality nor the rule
   reads the stylesheet and script files the page loads. The verify page
   loads 3 stylesheets, the baseline's ``fonts.css``, ``palettes.css`` and
   ``baseline.css`` under ``assets/baseline/``, and 2 baseline scripts,
   ``scheme.js`` and ``copy.js``, each with the baseline version as its
   ``?v=`` token; ``tools/check-baseline-pin.py`` holds each to the digest
   that the pinned baseline version publishes, so an edit to one fails that
   gate, and a new baseline version changes the tokens, so it fails the pin
   in ``tools/test-build-site.py`` until the pin is updated on purpose. A
   site-owned stylesheet, ``site-src/assets/site.css``, which the site does
   not have, would add a link to the page, which fails that pin, and
   SITE_CSS_PIN there pins its content.

What it does not verify
-----------------------

It does not fetch anything. It cannot tell whether the displayed checksum is the
true value of the published asset, only that it is well formed and consistent within
the site. Confirming the value against the release requires the network and is
done by the orchestrator's post-release site flip, which reads the published checksum.
So it passes a well-formed checksum in ``release.json`` for a version that has no
release yet, such as the previous version's digest or a locally built one passed
to ``tools/set-release-links.py`` at a bump; ``tools/check-release-checksum-live.py``
fails that page while the release and its tag do not exist. A checksum close to the
zero placeholder, such as a mistyped placeholder, fails check 7, and the writer and
the generator refuse it.

When a check fails, the closing advice fits the state of ``release.json``: while it
holds the zero placeholder or a checksum close to it (check 7), rerun
``tools/set-release-links.py`` with the placeholder until the release is
published, and flip the site after that; otherwise flip the
site with ``tools/set-release-links.py`` using the published release checksum,
then run ``tools/build-site.py``. Neither advice offers an edit by hand: the
whole-page equality refuses any page that is not the generator's render.

Exit codes:
  0  every check above passes, so every release link names the SKILL.md
     version and the verify page is in the state ``release.json`` selects: it
     is the page the generator writes for the checksum ``release.json``
     holds, or, while that is the zero placeholder, for the note that the
     checksum appears when that version is published
  1  something disagrees
  3  a required file is missing or not a regular file, a required file or a
     file under ``site/`` could not be read, the first ``Version:`` line of
     SKILL.md is missing or not a bare X.Y.Z version, ``release.json`` is not
     a JSON object, no release-asset URL was found under ``site/``, or
     ``tools/build-site.py`` could not render the verify page's download block
     or, for any reason it refuses a build, the whole verify page
"""

from __future__ import annotations

import importlib.util
import os
import re
import stat
import sys
import urllib.parse
from html.parser import HTMLParser
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
# download block), which check 4 and the published state's reports read; the gate is download_block_problems.
DISPLAYED_SUM = re.compile(r'<code class="sum" id="published-checksum">([^<]*)</code>')
SUM_ELEMENT = '<code class="sum" id="published-checksum">'
DISPLAYED_VERSION = re.compile(r"published checksum for version ([0-9][0-9.]*) is")
# The verify page's note while release.json holds the zero placeholder, as tools/build-site.py writes it (sum_tokens).
PENDING_VERSION = re.compile(r"The checksum for version ([0-9][0-9.]*) appears here once that version is published; "
                             r"compare the checksum of your file with it then\.")
PLACEHOLDER = "0" * 64
# A checksum other than the placeholder with at least this many 0 digits of its 64 is close to it, such as a mistyped
# placeholder: check 7 fails it, as tools/build-site.py and tools/set-release-links.py refuse it.
NEAR_PLACEHOLDER_ZEROS = 56
# What download_block_problems refuses outside the download block: the note in any version and any letter case, the
# "published checksum" wording, a step that tells the reader not to install the file, a 64 digit hexadecimal value,
# and the id of the checksum element; and the address of the verify page, against which it resolves a relative link.
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

    source_problems, placeholder, near = check_release_source(expected, redirects)
    problems += source_problems

    if problems:
        print("Release link problems found:")
        for problem in dict.fromkeys(problems):
            print(f"  - {problem}")
        if placeholder or near:
            # DISCOVERY round 5, finding 5: before the release, there is no published checksum to flip the site to.
            # VERIFY round 7.1, finding 1: a checksum close to the placeholder is a mistyped placeholder (check 7).
            held, which = (("the zero placeholder of a version bump", "that placeholder") if placeholder else
                           ("a checksum close to the zero placeholder", "the zero placeholder"))
            print(
                f"\nsite-src/release.json holds {held}. Until release v{expected} "
                f"is published, run tools/set-release-links.py for version {expected} with {which} (see "
                f"the release runbook), so the site matches SKILL.md; once it is published, flip the site with "
                f"tools/set-release-links.py using the published release checksum."
            )
        else:
            print(
                f"\nFlip the site with tools/set-release-links.py using the published "
                f"release checksum (see the release runbook), then run tools/build-site.py, "
                f"so the site matches SKILL.md ({expected})."
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


def check_release_source(expected: str, redirects: str) -> tuple[list[str], bool, bool]:
    """Checks 7 and 8: release.json, and the install and verify pages generated from it. Returns the problems
    found, whether release.json holds the zero placeholder, and whether it holds a well-formed checksum close to it,
    which select the closing advice in main.

    A stale bare file name on either page is check 6's (ZIP_NAME, site-wide), so it is
    not reported twice here; these pages must still name the release at least once.
    ``redirects`` is site/_redirects, whose paths to the checksum file the verify page
    may not link outside its download block, in either state."""
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
    elif near_placeholder(checksum):
        problems.append(
            f"site-src/release.json holds {checksum}, which is not the zero placeholder but has {checksum.count('0')} "
            f"of its 64 digits 0, such as a mistyped placeholder; until release v{expected} is published, run "
            f"tools/set-release-links.py with the zero placeholder"
        )
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
        # The generator refuses a checksum close to the placeholder, which is reported above, so it renders no page.
        if (page != VERIFY_PAGE or not isinstance(checksum, str) or not SHA256.match(checksum)
                or near_placeholder(checksum)):
            continue
        # The gate: the download block that tools/build-site.py writes for the state release.json selects.
        state = "holds the zero placeholder" if checksum == PLACEHOLDER else "holds a published checksum"
        try:
            block = download_block(expected, checksum)
        except LookupError as error:
            die(str(error))
        for problem in download_block_problems(text, block, redirects):
            problems.append(f"{relative} {problem}, but site-src/release.json {state}")
        # The gate: the whole page, byte for byte, as tools/build-site.py renders it from the committed sources. The
        # generator refuses a release.json that disagrees with SKILL.md, which is reported above.
        if release.get("version") == expected and release.get("tag") == f"v{expected}":
            try:
                rendered = rendered_verify_page()
                written = page.read_bytes()
            except LookupError as error:
                die(str(error))
            except OSError as error:
                die(f"{relative} could not be read: {error}")
            if written != rendered:
                problems.append(
                    f"{relative} is not the page tools/build-site.py renders for it from the committed sources, "
                    f"while site-src/release.json {state} ({first_difference(written, rendered)}); "
                    f"run tools/build-site.py"
                )
        # Clearer reports of the commonest ways a page leaves the published state.
        if checksum != PLACEHOLDER:
            if PENDING_VERSION.search(text):
                problems.append(f"{relative} says the checksum is not yet published, but site-src/release.json {state}")
            shown = DISPLAYED_SUM.findall(text)
            if shown and shown[0].strip() != checksum:
                problems.append(f"{relative} shows a checksum other than site-src/release.json")
    near = isinstance(checksum, str) and bool(SHA256.match(checksum)) and near_placeholder(checksum)
    return problems, checksum == PLACEHOLDER, near


def near_placeholder(checksum: str) -> bool:
    """Whether ``checksum`` is not the zero placeholder but has NEAR_PLACEHOLDER_ZEROS or more of its digits 0, such as
    a mistyped placeholder, which check 7 fails."""
    return checksum != PLACEHOLDER and checksum.count("0") >= NEAR_PLACEHOLDER_ZEROS


def rendered_verify_page() -> bytes:
    """site/verify/index.html as tools/build-site.py renders it at base / from the sources under REPO_ROOT and their
    site-src/release.json (verify_page), the page the gate requires byte for byte. Raises LookupError when the
    generator cannot render it, which a refusal on any page causes."""
    try:
        spec = importlib.util.spec_from_file_location("build_site_page", GENERATOR)
        if spec is None or spec.loader is None:
            raise ImportError("no loader")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.verify_page(REPO_ROOT)
    except Exception as error:
        raise LookupError(f"tools/build-site.py could not render the verify page: {error}") from error


def first_difference(written: bytes, rendered: bytes) -> str:
    """Where ``written`` first departs from ``rendered``, by line, for the report."""
    lines, expected = written.split(b"\n"), rendered.split(b"\n")
    for number, (line, wanted) in enumerate(zip(lines, expected), start=1):
        if line != wanted:
            return f"first at line {number}"
    return f"the page has {len(lines)} lines, the render {len(expected)}"


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
    build() writes it when a browser does not: review found the block after ``<noscript></div><div class="doc">``,
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
        spec = importlib.util.spec_from_file_location("build_site", GENERATOR)
        if spec is None or spec.loader is None:
            raise ImportError("no loader")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.verify_download_block(module.REPO_ROOT, version, f"v{version}", checksum)
    except Exception as error:
        raise LookupError(f"tools/build-site.py could not render the verify page's download block: {error}") from error


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


if __name__ == "__main__":
    sys.exit(main())
