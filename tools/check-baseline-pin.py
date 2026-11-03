#!/usr/bin/env python3
"""Check that the copied baseline files still match their pin, offline.

``tools/copy-baseline.py`` copies the runtime files of a verified baseline
version into ``<output root>/assets/baseline/`` and records each file's SHA-256
in ``.baseline/pin.toml``, in the baseline README's format: a ``version`` key
and a ``[files]`` table of path to digest, the paths relative to the output
root. The output root follows the base path in ``site-src/site.json``
(``site/draft/`` while staged, ``site/`` after promotion). The copied files are
never edited. This gate makes an edit, a replacement, a deletion or an addition
fail. The pin is also the one source of the baseline version: the generator
(``tools/build-site.py``) reads it for the ``?v=`` asset tokens.

What it verifies
----------------

1. ``.baseline/pin.toml`` parses as TOML and holds exactly ``version`` (X.Y.Z)
   and a non-empty ``[files]`` table whose every key is a relative path under
   ``assets/baseline/`` and whose every value is a lower-case SHA-256. A
   malformed pin is a failure (exit 3), never a pass.
2. Each pinned file appears in the version's ``SHA256SUMS`` (kept as
   ``.baseline/SHA256SUMS``) under its name within the package, with the same
   digest, so the pin cannot name a file or a digest the published version
   does not have.
3. Each pinned file exists under the output root as a regular file, not a
   link, and hashes to its pinned digest.
4. No file under ``<output root>/assets/baseline/`` is missing from the pin.
5. The pin holds the files of the README's runtime and licence set that
   ``REQUIRED`` names: the 3 stylesheets, 4 of the 5 scripts (``copy.js``,
   ``select.js``, ``search.js`` and ``rail.js``), ``LICENSE``, ``NOTICE.md``
   and ``marks/NOTICE.md``, so a copy that drops one, such as ``rail.js``,
   fails even when the files present match. ``REQUIRED`` leaves out
   ``matrix.js``, which the template owner's 1.5.1 notice says to copy only
   where a page uses it, and no page here does. A page that starts using
   ``matrix.js`` needs it added to ``TOP_FILES`` in ``tools/copy-baseline.py``
   and to ``REQUIRED`` first, or its file will not be copied or pinned.

Every folder is listed with ``os.scandir``, so a folder or file that cannot be
read fails closed (exit 3) rather than reading as empty.

What it does not verify
-----------------------

It does not fetch anything, and the README's pin format carries no digest of
``SHA256SUMS`` itself: ``tools/copy-baseline.py`` checks that digest at copy
time against the published value the operator supplies, and the pin's comment
records it for review.

Exit codes:
  0  every copied file matches the pin
  1  a file drifted, is missing, is extra, or disagrees with SHA256SUMS
  3  the pin or a file could not be read, or the pin is malformed
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
PREFIX = "assets/baseline/"
REQUIRED = [
    PREFIX + name
    for name in ("baseline.css", "palettes.css", "fonts.css", "copy.js", "select.js", "search.js", "rail.js",
                 "LICENSE", "NOTICE.md", "marks/NOTICE.md")
]

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
        if not path.startswith(PREFIX) or not REL_PATH.match(path) or ".." in path.split("/"):
            raise Unreadable(f"{PIN} pins {path!r}, which is not a relative path under {PREFIX}")
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


def check(root: Path) -> list[str]:
    _, files = load_pin(root)
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
        if published.get(path[len(PREFIX):]) != digest:
            problems.append(f"{path} is pinned with a digest the version's SHA256SUMS does not list.")
        target = out / path
        try:
            info = os.lstat(target)
        except FileNotFoundError:
            problems.append(f"{shown}/{path} is pinned but missing.")
            continue
        except OSError as error:
            raise Unreadable(f"{target} could not be read: {error}") from error
        if not stat.S_ISREG(info.st_mode):
            problems.append(f"{shown}/{path} is not a regular file (a link or a folder).")
            continue
        if hashlib.sha256(read_bytes(target)).hexdigest() != digest:
            problems.append(f"{shown}/{path} differs from its pinned digest; never edit a copied file.")

    for path in REQUIRED:
        if path not in files:
            problems.append(f"{path} is part of the baseline's runtime and licence set but is not pinned.")

    copied = out / PREFIX
    if not copied.is_dir():
        raise Unreadable(f"{shown}/{PREFIX} is missing")
    for name in list_tree(copied):
        if PREFIX + name not in files:
            problems.append(f"{shown}/{PREFIX}{name} is not in the pin.")
    return problems


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
    print(f"All {len(files)} copied files of baseline {version} match the pin and the version's SHA256SUMS, and no file is unpinned.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
