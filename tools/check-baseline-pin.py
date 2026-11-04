#!/usr/bin/env python3
"""Check that the copied baseline files still match their pin, offline.

``tools/copy-baseline.py`` copies the runtime files of a verified baseline
version into ``<output root>/assets/baseline/`` and records each file's SHA-256
in ``.baseline/pin.toml``, in the baseline README's format: a ``version`` key
and a ``[files]`` table of path to digest, the paths under ``assets/baseline/``
relative to the output root and the build tool's key relative to the repository
root. The output root follows the base path in ``site-src/site.json``
(``site/draft/`` while staged, ``site/`` after promotion). The copied files are
never edited. This gate makes an edit, a replacement, a deletion or an addition
fail. The pin is also the one source of the baseline version: the generator
(``tools/build-site.py``) reads it for the ``?v=`` asset tokens.

What it verifies
----------------

1. ``.baseline/pin.toml`` parses as TOML and holds exactly ``version`` (X.Y.Z)
   and a non-empty ``[files]`` table whose every key is a relative path under
   ``assets/baseline/``, or exactly the build tool key
   ``.baseline/check_palette.py`` (``TOOLS``), and whose every value is a
   lower-case SHA-256. Any other key is malformed. A malformed pin is a
   failure (exit 3), never a pass.
2. Each pinned file appears in the version's ``SHA256SUMS`` (kept as
   ``.baseline/SHA256SUMS``) under its name within the package, with the same
   digest, so the pin cannot name a file or a digest the published version
   does not have. The build tool's name within the package is
   ``tools/check_palette.py``.
3. Each pinned file exists under the output root as a regular file, not a
   link, and hashes to its pinned digest. The build tool is checked the same
   way at its path from the repository root, ``.baseline/check_palette.py``.
4. No file under ``<output root>/assets/baseline/`` is missing from the pin,
   and no file named ``check_palette.py`` exists anywhere under ``site/``: the
   build tool is pinned but never served.
5. The pin holds these files of the README's runtime and licence set
   (``REQUIRED``): the 3 stylesheets, 5 of the README's 6 scripts (this site
   leaves out ``matrix.js``, by the owner's decision), ``LICENSE``,
   ``NOTICE.md`` and
   ``marks/NOTICE.md``, and the build tool key ``.baseline/check_palette.py``,
   so a copy that drops one, such as ``rail.js``, fails even when the files
   present match.
6. The pin's version is the version that ``SHA256SUMS`` belongs to:
   ``SHA256SUMS`` lines carry no version, so the gate reads it from the
   version's own README, copied unserved to ``.baseline/README.md``, which
   must hash to the ``README.md`` digest that ``SHA256SUMS`` lists and start
   with ``# Baseline X.Y.Z: `` naming the pin's version. The specification,
   copied unserved to ``.baseline/SPECIFICATION.md`` and read by
   ``tools/test-build-site.py``, must hash to its listed digest too.
7. ``NOTICE.md``'s ``## Site template`` section is exactly the entry that the
   README's "Adoption in a repository" step 7 prescribes, with ``<version>``
   set to the pin's version (its lines other than blank ones, compared byte
   for byte, up to the next heading of level 1 or 2, so a subsection's lines
   count), so an entry edited by hand, extended, or left on an earlier
   version, fails. It is read only when the README matches its digest.

Every folder is listed with ``os.scandir``, so a folder or file that cannot be
read fails closed (exit 3) rather than reading as empty.

What it does not verify
-----------------------

It does not fetch anything, and the README's pin format carries no digest of
``SHA256SUMS`` itself: ``tools/copy-baseline.py`` checks that digest at copy
time against the published value the operator supplies, and the pin's comment
records it for review. The README's heading and the wording of its step 7 are
the template's conventions, not a published format: a version that rewords
either fails closed (exit 3) until this gate and ``tools/copy-baseline.py``
learn the new form.

Exit codes:
  0  every copied file matches the pin
  1  a file drifted, is missing, is extra, or disagrees with SHA256SUMS; the
     pin's version is not the README's; or NOTICE.md's Site template entry
     is not the one the README prescribes
  3  the pin or a file could not be read, the pin is malformed, or the README
     lacks its version heading or its step 7 NOTICE entry
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python older than 3.11
    print("check-baseline-pin: Python 3.11 or later is required (tomllib)", file=sys.stderr)
    raise SystemExit(3)

REPO_ROOT = Path(__file__).resolve().parent.parent
PIN = Path(".baseline/pin.toml")
SUMS = Path(".baseline/SHA256SUMS")
SITE_JSON = Path("site-src/site.json")
NOTICE = Path("NOTICE.md")
# The version's documents, copied unserved to .baseline/ by tools/copy-baseline.py: their names in SHA256SUMS.
DOCUMENTS = ("README.md", "SPECIFICATION.md")
README_HEADING = re.compile(r"^# Baseline ([0-9]+\.[0-9]+\.[0-9]+): ")
# The README's "Adoption in a repository" step 7 and the prefix of its quoted NOTICE entry, read by notice_entry(),
# which tools/copy-baseline.py loads from here; the entry's section in NOTICE.md, which only a heading of the same or a
# higher level (1 or 2 "#" and a space) ends.
NOTICE_STEP = "7. Add this entry to the repository's NOTICE:"
ENTRY_PREFIX = "   > "
NOTICE_SECTION = "## Site template"
SECTION_END = re.compile(r"^#{1,2} ")
PREFIX = "assets/baseline/"
# The pinned build tool: its key in the pin, from the repository root, and its name in SHA256SUMS.
TOOLS = {".baseline/check_palette.py": "tools/check_palette.py"}
REQUIRED = [
    PREFIX + name
    for name in ("baseline.css", "palettes.css", "fonts.css", "copy.js", "select.js", "search.js", "rail.js",
                 "scheme.js", "LICENSE", "NOTICE.md", "marks/NOTICE.md")
] + list(TOOLS)

HEX64 = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
REL_PATH = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")
SUM_LINE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9._/-]+)$")


class Unreadable(Exception):
    """An input the gate must read could not be read, or is malformed."""


def read_bytes(path: Path) -> bytes:
    try:
        info = os.lstat(path)
    except OSError as error:
        raise Unreadable(f"{path} could not be read: {error}") from error
    if not stat.S_ISREG(info.st_mode):
        raise Unreadable(f"{path} is not a regular file")
    try:
        return path.read_bytes()
    except OSError as error:
        raise Unreadable(f"{path} could not be read: {error}") from error


def load_pin(root: Path) -> tuple[str, dict[str, str]]:
    """The pinned version and files; raises Unreadable on any malformed pin."""
    try:
        pin = tomllib.loads(read_bytes(root / PIN).decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as error:
        raise Unreadable(f"{PIN} is not valid TOML: {error}") from error
    if set(pin) != {"version", "files"}:
        raise Unreadable(f"{PIN} must hold exactly version and [files], found {sorted(pin)}")
    version, files = pin["version"], pin["files"]
    if not isinstance(version, str) or not VERSION.match(version):
        raise Unreadable(f"{PIN} version {version!r} is not X.Y.Z")
    if not isinstance(files, dict) or not files:
        raise Unreadable(f"{PIN} pins no [files]")
    for path, digest in files.items():
        if path in TOOLS:
            pass
        elif not path.startswith(PREFIX) or not REL_PATH.match(path) or ".." in path.split("/"):
            raise Unreadable(f"{PIN} pins {path!r}, which is not a relative path under {PREFIX} or a pinned build tool")
        if not isinstance(digest, str) or not HEX64.match(digest):
            raise Unreadable(f"{PIN} pins {path} with a malformed sha256")
    return version, files


def output_root(root: Path) -> Path:
    try:
        base = json.loads(read_bytes(root / SITE_JSON).decode("utf-8")).get("base")
    except (UnicodeError, ValueError, AttributeError) as error:
        raise Unreadable(f"{SITE_JSON} is not a JSON object with a base: {error}") from error
    if base == "/":
        return root / "site"
    if not isinstance(base, str) or not re.match(r"^/[a-z0-9-]+/$", base):
        raise Unreadable(f"{SITE_JSON} base {base!r} must be / or a single folder such as /draft/")
    return root / "site" / base.strip("/")


def list_tree(directory: Path) -> list[str]:
    found: list[str] = []
    stack = [directory]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as error:
            raise Unreadable(f"{current} could not be listed: {error}") from error
        for entry in entries:
            try:
                mode = entry.stat(follow_symlinks=False).st_mode
            except OSError as error:
                raise Unreadable(f"{entry.path} could not be read: {error}") from error
            if stat.S_ISDIR(mode):
                stack.append(Path(entry.path))
            else:
                found.append(Path(entry.path).relative_to(directory).as_posix())
    return sorted(found)


def notice_entry(readme: str) -> str | None:
    """The NOTICE entry of the README's step 7, or None unless it is exactly 1 quoted line holding <version> once."""
    lines = readme.split("\n")
    steps = [number for number, line in enumerate(lines) if NOTICE_STEP[len("7. "):] in line]
    if len(steps) != 1 or lines[steps[0]] != NOTICE_STEP:
        return None
    rest = lines[steps[0] + 1:]
    while rest and not rest[0].strip():
        rest = rest[1:]
    quoted = []
    while rest and rest[0].lstrip().startswith(">"):
        quoted.append(rest.pop(0))
    if len(quoted) != 1 or not quoted[0].startswith(ENTRY_PREFIX) or quoted[0].count("<version>") != 1:
        return None
    return quoted[0][len(ENTRY_PREFIX):]


def document_problems(root: Path, version: str, published: dict[str, str]) -> list[str]:
    """Items 6 and 7: the copied documents match SHA256SUMS, the README names the pin's version, and NOTICE.md's
    Site template section is the README's step 7 entry for that version."""
    problems: list[str] = []
    texts: dict[str, str] = {}
    for name in DOCUMENTS:
        path = PIN.parent / name
        data = read_bytes(root / path)
        if name not in published:
            problems.append(f"{path} cannot be checked: the version's SHA256SUMS does not list {name}.")
            continue
        if hashlib.sha256(data).hexdigest() != published[name]:
            problems.append(f"{path} does not hash to the {name} digest the version's SHA256SUMS lists.")
            continue
        try:
            texts[name] = data.decode("utf-8")
        except UnicodeError as error:
            raise Unreadable(f"{path} is not UTF-8: {error}") from error
    readme = texts.get("README.md")
    if readme is None:
        return problems
    heading = README_HEADING.match(readme)
    if heading is None:
        raise Unreadable(f"{PIN.parent / 'README.md'} does not start with a '# Baseline X.Y.Z: ' heading")
    if heading.group(1) != version:
        problems.append(f"{PIN} names version {version}, but the README that SHA256SUMS lists is baseline "
                        f"{heading.group(1)}: the pin and SHA256SUMS belong to different versions.")
    entry = notice_entry(readme)
    if entry is None:
        raise Unreadable(f"{PIN.parent / 'README.md'} has no step 7 {NOTICE_STEP[len('7. '):]!r} "
                         "with 1 quoted entry holding <version> once")
    try:
        lines = read_bytes(root / NOTICE).decode("utf-8").split("\n")
    except UnicodeError as error:
        raise Unreadable(f"{NOTICE} is not UTF-8: {error}") from error
    if lines.count(NOTICE_SECTION) != 1:
        problems.append(f"{NOTICE} has no single {NOTICE_SECTION!r} section for the entry the baseline README's step 7 "
                        "prescribes.")
        return problems
    section = []
    for line in lines[lines.index(NOTICE_SECTION) + 1:]:
        if SECTION_END.match(line):
            break
        if line.strip():
            section.append(line)
    if section != [entry.replace("<version>", version)]:
        problems.append(f"{NOTICE}'s {NOTICE_SECTION!r} section is not exactly the entry the baseline README's step 7 "
                        f"prescribes for baseline {version}.")
    return problems


def check(root: Path) -> list[str]:
    version, files = load_pin(root)
    out = output_root(root)
    problems: list[str] = []
    published: dict[str, str] = {}
    try:
        sums_text = read_bytes(root / SUMS).decode("utf-8")
    except UnicodeError as error:
        raise Unreadable(f"{SUMS} is not UTF-8: {error}") from error
    for number, line in enumerate(sums_text.splitlines(), start=1):
        match = SUM_LINE.match(line)
        if match is None:
            raise Unreadable(f"{SUMS} line {number} is malformed")
        published[match.group(2)] = match.group(1)

    shown = out.relative_to(root).as_posix()
    for path, digest in sorted(files.items()):
        if path in TOOLS:
            package_name, target, label = TOOLS[path], root / path, path
        else:
            package_name, target, label = path[len(PREFIX):], out / path, f"{shown}/{path}"
        if published.get(package_name) != digest:
            problems.append(f"{path} is pinned with a digest the version's SHA256SUMS does not list.")
        try:
            info = os.lstat(target)
        except FileNotFoundError:
            problems.append(f"{label} is pinned but missing.")
            continue
        except OSError as error:
            raise Unreadable(f"{target} could not be read: {error}") from error
        if not stat.S_ISREG(info.st_mode):
            problems.append(f"{label} is not a regular file (a link or a folder).")
            continue
        if hashlib.sha256(read_bytes(target)).hexdigest() != digest:
            problems.append(f"{label} differs from its pinned digest; never edit a copied file.")

    for path in REQUIRED:
        if path not in files:
            problems.append(f"{path} is part of the baseline's runtime and licence set but is not pinned.")

    copied = out / PREFIX
    if not copied.is_dir():
        raise Unreadable(f"{shown}/{PREFIX} is missing")
    for name in list_tree(copied):
        if PREFIX + name not in files:
            problems.append(f"{shown}/{PREFIX}{name} is not in the pin.")

    served = root / "site"
    tool_names = {Path(key).name for key in TOOLS}
    for name in list_tree(served):
        if Path(name).name in tool_names:
            problems.append(f"site/{name} is a pinned build tool under the served tree; it is never served.")
    return problems + document_problems(root, version, published)


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else REPO_ROOT
    try:
        problems = check(root)
    except Unreadable as error:
        print(f"check-baseline-pin: {error}", file=sys.stderr)
        return 3
    if problems:
        print("Baseline pin problems found:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    version, files = load_pin(root)
    print(f"All {len(files)} copied files of baseline {version} match the pin and the version's SHA256SUMS, and no file is unpinned; "
          f"its README names {version} and NOTICE.md carries its Site template entry.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
