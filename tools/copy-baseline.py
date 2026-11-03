#!/usr/bin/env python3
"""Copy the runtime files of a verified baseline version into the site and write the pin.

The baseline is the shared site template, published as immutable versions at
https://posluns.ca/baseline/<version>/. This tool never fetches anything. It
reads an unpacked version folder that the operator has already downloaded as
the archive and verified against https://posluns.ca/baseline/SHA256SUMS, and
refuses to copy unless:

1. ``SHA256SUMS`` in that folder hashes to the digest given on the command line
   (the value published in https://posluns.dev/hashes.txt), and
2. every file listed in ``SHA256SUMS`` exists and hashes to its listed digest,
   and no file in the folder is missing from it.

It then copies the runtime and licence files that the baseline README lists
in "Adoption in a repository", step 2, except ``matrix.js``, byte for byte
into ``<output root>/assets/baseline/``, where the output root follows the base
path in ``site-src/site.json`` (``site/draft/`` while staged). The copy is the
stylesheets, the fonts with their licence files, 4 of the 5 scripts
(``copy.js``, ``select.js``, ``search.js`` and, from 1.3.0, ``rail.js``), the
logos, the marks with ``marks/NOTICE.md``, ``LICENSE`` and ``NOTICE.md``;
never ``reference/``, ``tools/`` or the documents. The fifth script,
``matrix.js``, is left out: the template owner's 1.5.1 notice says to copy it
only where a page uses it, and no page here does. A page that starts using
``matrix.js`` needs it added to ``TOP_FILES`` here and to ``REQUIRED`` in
``tools/check-baseline-pin.py`` first, or its file will not be copied or
pinned.

It copies ``SHA256SUMS`` to ``.baseline/SHA256SUMS`` (not published) and writes
``.baseline/pin.toml`` in the README's format: a ``version`` key and a
``[files]`` table of path to SHA-256, the paths relative to the output root.
``tools/check-baseline-pin.py`` checks the copy offline on every pull request.

Usage:
    python3 -I tools/copy-baseline.py --from <unpacked version folder> \\
        --sums-sha256 <sha256 of SHA256SUMS> --archive-sha256 <sha256 of the archive>

Exit codes:
  0  copied and pinned
  1  a digest did not match, or the folder is not a complete version
  3  an input could not be read
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PIN_DIR = REPO_ROOT / ".baseline"
PREFIX = "assets/baseline/"

TOP_FILES = {"baseline.css", "palettes.css", "fonts.css", "copy.js", "select.js", "search.js", "rail.js", "LICENSE", "NOTICE.md"}
FOLDERS = ("fonts/", "logos/", "marks/")
SUM_LINE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9._/-]+)$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def die(code: int, message: str) -> None:
    print(f"copy-baseline: {message}", file=sys.stderr)
    raise SystemExit(code)


def sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        die(3, f"{path} could not be read: {error}")
    return ""


def wanted(name: str) -> bool:
    return name in TOP_FILES or name.startswith(FOLDERS)


def output_root() -> Path:
    try:
        base = json.loads((REPO_ROOT / "site-src" / "site.json").read_text(encoding="utf-8"))["base"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        die(3, f"site-src/site.json has no readable base: {error}")
    if base == "/":
        return REPO_ROOT / "site"
    if not isinstance(base, str) or not re.match(r"^/[a-z0-9-]+/$", base):
        die(3, f"site-src/site.json base {base!r} must be / or a single folder such as /draft/")
    return REPO_ROOT / "site" / base.strip("/")


def list_files(root: Path) -> list[str]:
    found: list[str] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as error:
            die(3, f"{directory} could not be listed: {error}")
        for entry in entries:
            try:
                mode = entry.stat(follow_symlinks=False).st_mode
            except OSError as error:
                die(3, f"{entry.path} could not be read: {error}")
            if stat.S_ISDIR(mode):
                stack.append(Path(entry.path))
            elif stat.S_ISREG(mode):
                found.append(Path(entry.path).relative_to(root).as_posix())
            else:
                die(1, f"{entry.path} is not a regular file or folder")
    return sorted(found)


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy and pin a verified baseline version.")
    parser.add_argument("--from", dest="source", required=True, help="unpacked version folder")
    parser.add_argument("--sums-sha256", required=True, help="published sha256 of SHA256SUMS")
    parser.add_argument("--archive-sha256", required=True, help="published sha256 of the archive")
    args = parser.parse_args()

    source = Path(args.source)
    version = source.name
    if not VERSION.match(version):
        die(1, f"the folder name {version!r} is not a version number")
    for value, label in ((args.sums_sha256, "--sums-sha256"), (args.archive_sha256, "--archive-sha256")):
        if not HEX64.match(value):
            die(1, f"{label} is not a 64 character lower-case SHA-256")

    sums_path = source / "SHA256SUMS"
    if sha256(sums_path) != args.sums_sha256:
        die(1, "SHA256SUMS does not hash to the published digest")
    try:
        sums_text = sums_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        die(3, f"SHA256SUMS could not be read: {error}")

    listed: dict[str, str] = {}
    for number, line in enumerate(sums_text.splitlines(), start=1):
        match = SUM_LINE.match(line)
        if match is None:
            die(1, f"SHA256SUMS line {number} is malformed: {line!r}")
        digest, name = match.groups()
        if name in listed or name.startswith("/") or ".." in name.split("/"):
            die(1, f"SHA256SUMS line {number} names {name!r} twice or outside the folder")
        listed[name] = digest

    present = [name for name in list_files(source) if name != "SHA256SUMS"]
    if sorted(listed) != present:
        missing = sorted(set(listed) - set(present))
        extra = sorted(set(present) - set(listed))
        die(1, f"the folder does not match SHA256SUMS: missing {missing}, unlisted {extra}")
    for name, digest in listed.items():
        if sha256(source / name) != digest:
            die(1, f"{name} does not match its SHA256SUMS digest")

    chosen = sorted(name for name in listed if wanted(name))
    dest = output_root() / PREFIX
    if dest.exists():
        shutil.rmtree(dest)
    for name in chosen:
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
        if sha256(target) != listed[name]:
            die(1, f"the copy of {name} does not match its digest")

    PIN_DIR.mkdir(exist_ok=True)
    shutil.copyfile(sums_path, PIN_DIR / "SHA256SUMS")
    lines = [
        "# Baseline pin, in the format of the baseline README (\"Adoption in a repository\", step 3).",
        "# Written by tools/copy-baseline.py and checked by tools/check-baseline-pin.py; the paths are",
        "# relative to the site's output root (site/draft/ while staged, site/ after promotion).",
        f"# Source: https://posluns.ca/baseline/baseline-{version}.tar.gz, archive sha256 {args.archive_sha256};",
        f"# SHA256SUMS sha256 {args.sums_sha256}, copied to .baseline/SHA256SUMS.",
        "# Never edit a copied file; a new version arrives as a new copy and a new pin.",
        f'version = "{version}"',
        "",
        "[files]",
    ]
    lines += [f'"{PREFIX}{name}" = "{listed[name]}"' for name in chosen]
    (PIN_DIR / "pin.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"copied {len(chosen)} files of baseline {version} and wrote .baseline/pin.toml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
