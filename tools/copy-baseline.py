#!/usr/bin/env python3
"""Copy the runtime files of a verified baseline version into the site and write the pin.

The baseline is the shared site template, published as immutable versions at
https://posluns.ca/baseline/<version>/. This tool never fetches anything. It
reads an unpacked version folder that the operator has already downloaded as
the archive and verified against https://posluns.ca/baseline/SHA256SUMS, and
refuses to copy unless:

1. ``SHA256SUMS`` in that folder hashes to the digest given on the command line
   (the value published in https://posluns.dev/hashes.txt),
2. every file listed in ``SHA256SUMS`` exists and hashes to its listed digest,
   and no file in the folder is missing from it, and
3. ``SHA256SUMS`` lists the build tool ``tools/check_palette.py``, so the served
   files are never replaced by a version that lacks it, and
4. ``SHA256SUMS`` lists the documents ``README.md`` and ``SPECIFICATION.md``,
   the README's first line names the folder's version (``# Baseline X.Y.Z: ``),
   and its "Adoption in a repository" step 7 carries exactly 1 NOTICE entry, 1
   quoted line holding ``<version>`` once, which ``tools/check-baseline-pin.py``
   compares with ``NOTICE.md``. The README is read as that gate reads it, as
   bytes decoded without newline translation, by the gate's own
   ``notice_entry()``, which this tool loads from
   ``tools/check-baseline-pin.py`` next to it, so a README the gate would
   refuse, such as one with a carriage return in any line, is refused here too.

It then copies these of the runtime and licence files that the baseline README
lists ("Adoption in a repository", step 2): the stylesheets, the fonts with
their licence files, 5 of its 6 scripts (``rail.js`` from 1.3.0, ``scheme.js``
from 1.6.0; this site leaves out ``matrix.js``, by the owner's decision), the
logos, the marks with ``marks/NOTICE.md``, ``LICENSE`` and ``NOTICE.md``
(never ``reference/`` or ``tools/``), byte for byte
into ``<output root>/assets/baseline/``, where the output root follows the base
path in ``site-src/site.json`` (``site/draft/`` while staged). It copies the
pinned build tool ``tools/check_palette.py`` (from 1.6.0) to
``.baseline/check_palette.py``, which is pinned but never served, and it copies
``SHA256SUMS`` to ``.baseline/SHA256SUMS`` (not published) and writes
``.baseline/pin.toml`` in the README's format: a ``version`` key and a
``[files]`` table of path to SHA-256, the paths under ``assets/baseline/``
relative to the output root and the build tool's ``.baseline/check_palette.py``
relative to the repository root. It also copies the documents ``README.md`` and
``SPECIFICATION.md`` to ``.baseline/``, like ``SHA256SUMS`` never served and
not pinned (the maintainer ruled on 2026-11-04 to keep these 2 unserved copies):
``tools/check-baseline-pin.py`` checks each against its ``SHA256SUMS`` digest,
the README's version against the pin's and its NOTICE entry against
``NOTICE.md``, and ``tools/test-build-site.py`` reads specification 7.24 from
the copy.
``tools/check-baseline-pin.py`` checks the copy offline on every pull request.

It needs Python 3.11 or later, since the gate it loads imports ``tomllib``.

Usage:
    python3 -I tools/copy-baseline.py --from <unpacked version folder> \\
        --sums-sha256 <sha256 of SHA256SUMS> --archive-sha256 <sha256 of the archive>

Exit codes:
  0  copied and pinned
  1  a digest did not match, the folder is not a complete version, or its README
     lacks the folder's version heading or the step 7 NOTICE entry, or holds a
     carriage return
  3  an input could not be read, or Python is older than 3.11
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
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
TOOL_SOURCE = "tools/check_palette.py"
TOOL_NAME = "check_palette.py"
# The documents copied to .baseline/, never served and not pinned; tools/check-baseline-pin.py checks each.
DOCUMENTS = ("README.md", "SPECIFICATION.md")
README_HEADING = re.compile(r"^# Baseline ([0-9]+\.[0-9]+\.[0-9]+): ")
# The gate whose notice_entry() reads the README's "Adoption in a repository" step 7 for both tools.
GATE = Path(__file__).resolve().parent / "check-baseline-pin.py"

TOP_FILES = {"baseline.css", "palettes.css", "fonts.css", "copy.js", "select.js", "search.js", "rail.js", "scheme.js", "LICENSE", "NOTICE.md"}
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


def load_gate():
    """tools/check-baseline-pin.py as a module, for its notice_entry() and NOTICE_STEP. The gate's tomllib guard
    exits on Python older than 3.11; its message is dropped and this tool reports the floor in its own words."""
    try:
        spec = importlib.util.spec_from_file_location("check_baseline_pin", GATE)
        module = importlib.util.module_from_spec(spec)
        with contextlib.redirect_stderr(io.StringIO()):
            spec.loader.exec_module(module)
    except (OSError, SyntaxError) as error:
        die(3, f"{GATE} could not be loaded: {error}")
    except SystemExit:
        die(3, f"Python 3.11 or later is required (tomllib, which {GATE.name} imports)")
    return module


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
    tool_digest = listed.get(TOOL_SOURCE)
    if tool_digest is None:
        die(1, f"SHA256SUMS does not list {TOOL_SOURCE}")
    for name in DOCUMENTS:
        if name not in listed:
            die(1, f"SHA256SUMS does not list the document {name}")
    try:
        readme = (source / "README.md").read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as error:
        die(3, f"README.md could not be read: {error}")
    heading = README_HEADING.match(readme)
    if heading is None or heading.group(1) != version:
        die(1, f"README.md does not start with the heading '# Baseline {version}: ', the folder's version")
    gate = load_gate()
    if gate.notice_entry(readme) is None:
        die(1, f"README.md holds a carriage return or has no step 7 {gate.NOTICE_STEP[len('7. '):]!r} "
               "with 1 quoted entry holding <version> once")

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

    if sha256(source / TOOL_SOURCE) != tool_digest:
        die(1, f"{TOOL_SOURCE} does not match its SHA256SUMS digest")
    PIN_DIR.mkdir(exist_ok=True)
    shutil.copyfile(source / TOOL_SOURCE, PIN_DIR / TOOL_NAME)
    if sha256(PIN_DIR / TOOL_NAME) != tool_digest:
        die(1, f"the copy of {TOOL_SOURCE} does not match its digest")
    shutil.copyfile(sums_path, PIN_DIR / "SHA256SUMS")
    for name in DOCUMENTS:
        shutil.copyfile(source / name, PIN_DIR / name)
        if sha256(PIN_DIR / name) != listed[name]:
            die(1, f"the copy of {name} does not match its digest")
    lines = [
        "# Baseline pin, in the format of the baseline README (\"Adoption in a repository\", step 3).",
        "# Written by tools/copy-baseline.py and checked by tools/check-baseline-pin.py; the paths under",
        "# assets/baseline/ are relative to the site's output root (site/draft/ while staged, site/ after",
        f"# promotion), and .baseline/{TOOL_NAME} is relative to the repository root, outside site/.",
        f"# Source: https://posluns.ca/baseline/baseline-{version}.tar.gz, archive sha256 {args.archive_sha256};",
        f"# SHA256SUMS sha256 {args.sums_sha256}, copied to .baseline/SHA256SUMS.",
        "# Never edit a copied file; a new version arrives as a new copy and a new pin.",
        f'version = "{version}"',
        "",
        "[files]",
    ]
    lines += [f'"{PREFIX}{name}" = "{listed[name]}"' for name in chosen]
    lines += [f'".baseline/{TOOL_NAME}" = "{tool_digest}"']
    (PIN_DIR / "pin.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"copied {len(chosen) + 1} files of baseline {version} ({len(chosen)} to {PREFIX} and .baseline/{TOOL_NAME}) "
          f"and wrote .baseline/pin.toml; copied the documents {' and '.join(DOCUMENTS)} to .baseline/, not pinned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
