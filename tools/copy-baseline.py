#!/usr/bin/env python3
"""Copy the runtime files of a verified baseline version into the site and write the pin.

The baseline is the shared site template, published as immutable versions at
https://posluns.ca/baseline/<version>/. This tool imports no network module
and fetches nothing. It reads an unpacked version folder that the operator has
already downloaded as the archive and verified against
https://posluns.ca/baseline/SHA256SUMS, and refuses to copy unless:

1. ``SHA256SUMS`` in that folder hashes to the digest given on the command line
   (the value published in https://posluns.dev/hashes.txt),
2. every file listed in ``SHA256SUMS`` exists and hashes to its listed digest,
   and no file in the folder is missing from it, and
3. ``SHA256SUMS`` lists every build tool that ``tools/check-baseline-pin.py``
   pins (its ``TOOLS``): ``tools/check_palette.py``, the card builder
   ``tools/build_card.js``, and its 3 Inter fonts and their licence in
   ``tools/card-fonts/``, so the served files are never replaced by a version
   that lacks one, and
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
path in ``site-src/site.json`` (``site/draft/`` while staged). It copies each
build tool in the gate's ``TOOLS`` from ``tools/`` in the version to the same
path under ``.baseline/``, pinned but never served: ``tools/check_palette.py``
(from 1.6.0) to ``.baseline/check_palette.py``, and the card builder
``tools/build_card.js`` with its ``tools/card-fonts/`` files to
``.baseline/build_card.js`` and ``.baseline/card-fonts/``, since the builder
reads its fonts from beside itself. It clears ``.baseline/card-fonts/`` before
it copies, as it clears the served copy folder, so a stray file there never
outlives a copy.

It changes nothing outside the paths it manages: the served copy folder, the
build tools' folders under ``.baseline/`` such as ``card-fonts/``, and the
files it writes in ``.baseline/``, with any missing folder above them created.
It writes each file as a new file beside its target and renames it over the
target, so it never writes into an existing file: another hard link to a
target keeps its content. It reads each file in the version folder once,
checks those bytes against their ``SHA256SUMS`` digest, and writes the same
bytes, so the file it writes is the file it checked. It compiles the gate it
loads from source without reading or writing byte code, so a cache file under
``tools/__pycache__/`` is never run, and before its first change to a managed
path it writes nothing, not even there.

Before its first write it refuses (exit 1) a link, or a file
in place of a folder, at a folder it clears or writes into or at any folder
above one under the repository root, and a link or a folder in place of a file
it writes outside the folders it clears, so it never writes through a link.
Before its first write it also refuses (exit 1) a link, or an entry of the
wrong kind, at ``site-src/`` or ``site-src/site.json``, from which it reads
the output root, since it would read the output root from wherever the link
leads. It refuses (exit 1) a ``--from`` folder that is itself a link, before
it reads the version, since it would read the version from wherever the link
leads while taking the version number from the link's own name. Before its
first write it also refuses (exit 1) a ``--from`` folder that is, is inside,
or holds a folder it clears or writes into or a file it writes, since it would
delete or change its own input before copying it. It compares the ``--from``
folder and each folder above it with each of those paths, and the ``--from``
folder with each folder above each path, by device and inode rather than by
name, so a link above the ``--from`` folder cannot hide an overlap.

The tool has 4 limits. A folder mounted below a folder this tool clears, or
below the ``--from`` folder, is not compared, so a bind mount of the
``--from`` folder inside the served copy folder is not caught, and clearing
that folder would delete the files in the mount; keep mounts out of these
folders. The checks run once, before the first change, so they do not cover a
process that changes the tree while this tool runs. A run stopped by the
system between creating a new file and renaming it leaves that file, named
``.<name>.<random>.tmp``, beside its target. An interrupt (Ctrl-C) ends the
run with Python's own traceback rather than exit 3, and after the first change
the copy and the pin may then be incomplete.

It copies ``SHA256SUMS`` to ``.baseline/SHA256SUMS`` (not published) and writes
``.baseline/pin.toml`` in the README's format: a ``version`` key and a
``[files]`` table of path to SHA-256, the paths under ``assets/baseline/``
relative to the output root and the build tools' keys under ``.baseline/``
relative to the repository root. The pin is written from scratch with the
gate's ``TOOLS``, so the 2 tools cannot disagree on the build tools. It also
copies the documents ``README.md`` and ``SPECIFICATION.md`` to ``.baseline/``,
like ``SHA256SUMS`` never served and
not pinned (the maintainer ruled on 2026-11-04 to keep these 2 unserved copies):
``tools/check-baseline-pin.py`` checks each against its ``SHA256SUMS`` digest,
the README's version against the pin's and its NOTICE entry against
``NOTICE.md``, and ``tools/test-build-site.py`` reads specification 7.24 from
the copy.
``tools/check-baseline-pin.py`` checks the copy offline on every pull request.

It ends by running that gate's own ``check()``, in process, on the repository
it wrote, and reports success only when the gate passes. Otherwise it exits
with the gate's code and names the gate's problems; the copy and the pin are
written by then. The checks before the first write cover only the paths this
tool writes and reads, so this last check is what catches the rest of the
tree, such as a link elsewhere under ``site/``. Since the gate compares
``NOTICE.md``'s ``## Site template`` entry with the pin's version, update that
entry to the new version before the copy, or the copy exits 1 naming it.

It needs Python 3.11 or later, since the gate it loads imports ``tomllib``.

Usage:
    python3 -I tools/copy-baseline.py --from <unpacked version folder> \\
        --sums-sha256 <sha256 of SHA256SUMS> --archive-sha256 <sha256 of the archive>

Exit codes:
  0  copied and pinned, and tools/check-baseline-pin.py passes the tree; or
     --help, for which argparse prints its help and nothing is read or written
  1  before anything is read: the --from folder's name is not a version
     number, or a --sums-sha256 or --archive-sha256 value is not 64 lower-case
     hexadecimal digits, each matched as the whole value, so that a value
     with a trailing newline is refused;
     before the first write: SHA256SUMS or a file in the folder did not match
     its digest; a SHA256SUMS line is malformed, or names a file twice or
     outside the folder; the folder lacks a file that SHA256SUMS lists, holds
     a file that it does not list, or holds an entry that is neither a
     regular file nor a folder, such as a link; SHA256SUMS does not list a
     build tool in the gate's TOOLS, README.md or SPECIFICATION.md; its README
     lacks the folder's version heading or the step 7 NOTICE entry, or holds
     a carriage return; the --from folder is a link, or is, is inside, or
     holds a folder or file it clears or writes; a folder or file it writes,
     or site-src/ or site-src/site.json, is a link or of the wrong kind; or,
     after the copy and the pin are written, tools/check-baseline-pin.py finds
     a problem in the tree, which it names
  2  argparse refuses the command line, such as a missing or unknown option;
     argparse prints its usage and error lines, not this tool's own 1 line,
     and nothing is read or written
  3  an input could not be read, or Python is older than 3.11; or any failure
     after the first change to a managed path and before the pin is written,
     whatever raised it (an interrupt aside), with a message that says that
     the copy and the pin may be incomplete; or, after the copy and the pin
     are written, tools/check-baseline-pin.py could not read the tree or found
     it malformed, which it names; or any other unexpected error, named by its
     type, in place of a traceback
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
import secrets
import shutil
import stat
import sys
from pathlib import Path

# Nothing this tool imports from here on writes byte code: the tool changes no file outside the paths it manages.
sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parent.parent
PIN_DIR = REPO_ROOT / ".baseline"
PREFIX = "assets/baseline/"
# The documents copied to .baseline/, never served and not pinned; tools/check-baseline-pin.py checks each.
DOCUMENTS = ("README.md", "SPECIFICATION.md")
README_HEADING = re.compile(r"^# Baseline ([0-9]+\.[0-9]+\.[0-9]+): ")
# The gate whose TOOLS names the build tools to copy and pin, and whose notice_entry() reads the README's "Adoption in
# a repository" step 7 for both tools.
GATE = Path(__file__).resolve().parent / "check-baseline-pin.py"

TOP_FILES = {"baseline.css", "palettes.css", "fonts.css", "copy.js", "select.js", "search.js", "rail.js", "scheme.js", "LICENSE", "NOTICE.md"}
FOLDERS = ("fonts/", "logos/", "marks/")
# Each value these validate is matched whole with fullmatch(): "$" also matches before a final newline, so match()
# would accept a value that ends in one.
SUM_LINE = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9._/-]+)")
HEX64 = re.compile(r"[0-9a-f]{64}")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
BASE = re.compile(r"/[a-z0-9-]+/")


# True from just before the first change to a managed path until the pin is written: a failure in that span leaves a
# partial copy, whatever raised it, so die() reports it as such.
copying = False


def die(code: int, message: str) -> None:
    if copying:
        code = 3
        message = f"{message}; the copy and the pin may be incomplete"
    print(f"copy-baseline: {message}", file=sys.stderr)
    raise SystemExit(code)


def read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        die(3, f"{path} could not be read: {error}")
    return b""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_new(target: Path, data: bytes) -> None:
    """Write data to a new file beside target, then rename it over target. The rename replaces the folder entry, not
    the file it named, so a write never lands in an existing file and another hard link to target keeps its
    content."""
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(8)}.tmp")
    # O_EXCL makes open() fail on an existing entry, so the new file is never one that is already linked elsewhere.
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(temporary, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def load_gate():
    """tools/check-baseline-pin.py as a module, for its TOOLS, notice_entry(), NOTICE_STEP, ENTRY_PREFIX, and the
    check() and Unreadable with which this tool checks the tree it wrote. The gate is compiled from its source and
    no cached byte code is read or written, so loading it writes nothing, not even under tools/__pycache__/, and a
    stale or planted cache file there is never run, as the normal loader would run one. The gate's tomllib guard
    exits on Python older than 3.11; its message is dropped and this tool reports the floor in its own words."""
    try:
        spec = importlib.util.spec_from_file_location("check_baseline_pin", GATE)
        module = importlib.util.module_from_spec(spec)
        code = compile(GATE.read_bytes(), str(GATE), "exec", dont_inherit=True)
        with contextlib.redirect_stderr(io.StringIO()):
            exec(code, module.__dict__)
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
    if not isinstance(base, str) or not BASE.fullmatch(base):
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


def check_target(path: Path, folder: bool, action: str = "write through") -> None:
    """Exit 1 unless path, and each folder above it under the repository root, is absent or a folder and never a link,
    or, when path is a file this tool writes or reads, unless it is absent or a regular file. Writing through a link
    would change what it leads to, and reading through one would take an input from wherever it leads."""
    parts = path.relative_to(REPO_ROOT).parts
    for depth in range(1, len(parts) + 1):
        current = REPO_ROOT.joinpath(*parts[:depth])
        shown = current.relative_to(REPO_ROOT).as_posix()
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return
        except OSError as error:
            die(3, f"{shown} could not be read: {error}")
        if stat.S_ISLNK(mode):
            die(1, f"{shown} is a link; refusing to {action} it")
        if depth == len(parts) and not folder:
            if not stat.S_ISREG(mode):
                die(1, f"{shown} is not a regular file")
        elif not stat.S_ISDIR(mode):
            die(1, f"{shown} is not a folder")


def identity(path: Path) -> tuple[int, int] | None:
    """The device and inode of path, or None when it is absent."""
    try:
        status = os.stat(path)
    except FileNotFoundError:
        return None
    except OSError as error:
        die(3, f"{path} could not be read: {error}")
    return status.st_dev, status.st_ino


def check_source_apart(source: Path, target: Path) -> None:
    """Exit 1 if the --from folder is target, is inside it, or holds it. The --from folder and each folder above it
    are compared with target, and the --from folder with each folder above target, by device and inode rather than
    by name, so a link above the --from folder cannot hide an overlap. Folders below target or below the --from
    folder are not compared, so a folder mounted there can: a bind mount of the --from folder inside a folder this
    tool clears is not caught."""
    shown = target.relative_to(REPO_ROOT).as_posix()
    target_id = identity(target)
    if target_id is not None:
        resolved = source.resolve()
        for folder in (resolved, *resolved.parents):
            if identity(folder) == target_id:
                relation = "is" if folder == resolved else "is inside"
                die(1, f"the --from folder {source} {relation} {shown}, which this tool clears or writes; "
                       "unpack the version outside the repository's copy and pin folders")
    source_id = identity(source)
    for folder in (target, *target.parents):
        if identity(folder) == source_id:
            die(1, f"the --from folder {source} holds {shown}, which this tool clears or writes; "
                   "unpack the version outside the repository")


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy and pin a verified baseline version.")
    parser.add_argument("--from", dest="source", required=True, help="unpacked version folder")
    parser.add_argument("--sums-sha256", required=True, help="published sha256 of SHA256SUMS")
    parser.add_argument("--archive-sha256", required=True, help="published sha256 of the archive")
    args = parser.parse_args()

    source = Path(args.source)
    version = source.name
    if not VERSION.fullmatch(version):
        die(1, f"the folder name {version!r} is not a version number")
    for value, label in ((args.sums_sha256, "--sums-sha256"), (args.archive_sha256, "--archive-sha256")):
        if not HEX64.fullmatch(value):
            die(1, f"{label} is not a 64 character lower-case SHA-256")
    # A linked version folder would be read from wherever the link leads, while the version number comes from the
    # link's own name.
    try:
        source_mode = os.lstat(source).st_mode
    except OSError as error:
        die(3, f"{source} could not be read: {error}")
    if stat.S_ISLNK(source_mode):
        die(1, f"{source} is a link; give the unpacked version folder itself")

    # The gate's TOOLS, so that the pin written here is never one the gate refuses for a missing build tool. It is
    # loaded before any file of the version is read, so that an old Python is reported first, and so that code that
    # tools/test-baseline-pin.py appends to the gate sees every read of the version.
    gate = load_gate()
    tools = gate.TOOLS

    # Each file in the version is read once, and the bytes checked are the bytes written, so a file that changes
    # while this tool runs cannot be written unchecked.
    sums_data = read(source / "SHA256SUMS")
    if sha256(sums_data) != args.sums_sha256:
        die(1, "SHA256SUMS does not hash to the published digest")
    try:
        sums_text = sums_data.decode("utf-8")
    except UnicodeError as error:
        die(3, f"SHA256SUMS could not be read: {error}")

    listed: dict[str, str] = {}
    for number, line in enumerate(sums_text.splitlines(), start=1):
        match = SUM_LINE.fullmatch(line)
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
    for tool_source in tools.values():
        if tool_source not in listed:
            die(1, f"SHA256SUMS does not list {tool_source}")
    for name in DOCUMENTS:
        if name not in listed:
            die(1, f"SHA256SUMS does not list the document {name}")
    chosen = sorted(name for name in listed if wanted(name))
    kept = {*chosen, *tools.values(), *DOCUMENTS}
    contents: dict[str, bytes] = {}
    for name, digest in listed.items():
        data = read(source / name)
        if sha256(data) != digest:
            die(1, f"{name} does not match its SHA256SUMS digest")
        if name in kept:
            contents[name] = data
    try:
        readme = contents["README.md"].decode("utf-8")
    except UnicodeError as error:
        die(3, f"README.md could not be read: {error}")
    heading = README_HEADING.match(readme)
    if heading is None or heading.group(1) != version:
        die(1, f"README.md does not start with the heading '# Baseline {version}: ', the folder's version")
    if gate.notice_entry(readme) is None:
        die(1, f"README.md holds a carriage return or has no step 7 {gate.NOTICE_STEP[len('7. '):]!r} "
               f"that opens with its 1 quoted line, the entry, starting {gate.ENTRY_PREFIX!r} and holding "
               "<version> once, followed by a blank line or the step's end, and holds no '<blockquote'")

    # The output root comes from site-src/site.json, so neither it nor its folder may lead elsewhere.
    check_target(REPO_ROOT / "site-src" / "site.json", folder=False, action="read through")
    dest = output_root() / PREFIX
    # The build tools' own folders under .baseline/, such as card-fonts/, are rebuilt like the served copy folder, so
    # that the gate finds no stray file there. Every folder cleared or written into, and every file written beside
    # them, is checked before the first write.
    tool_folders = sorted({(REPO_ROOT / key).parent for key in tools} - {PIN_DIR})
    for folder in (dest, PIN_DIR, *tool_folders):
        check_target(folder, folder=True)
    written_files = ([REPO_ROOT / key for key in tools if (REPO_ROOT / key).parent == PIN_DIR]
                     + [PIN_DIR / name for name in ("SHA256SUMS", "pin.toml", *DOCUMENTS)])
    for path in written_files:
        check_target(path, folder=False)
    # A version folder inside a folder cleared below would be deleted before it is copied, and one that holds a
    # folder or file written below would be changed by the copy, so the copy would remove or alter its own input.
    for target in (dest, *tool_folders, PIN_DIR, *written_files):
        check_source_apart(source, target)
    global copying
    copying = True
    for folder in (dest, *tool_folders):
        if folder.exists():
            shutil.rmtree(folder)
    for name in chosen:
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        write_new(target, contents[name])

    PIN_DIR.mkdir(exist_ok=True)
    for key, tool_source in tools.items():
        target = REPO_ROOT / key
        target.parent.mkdir(parents=True, exist_ok=True)
        write_new(target, contents[tool_source])
    write_new(PIN_DIR / "SHA256SUMS", sums_data)
    for name in DOCUMENTS:
        write_new(PIN_DIR / name, contents[name])
    lines = [
        "# Baseline pin, in the format of the baseline README (\"Adoption in a repository\", step 3).",
        "# Written by tools/copy-baseline.py and checked by tools/check-baseline-pin.py; the paths under",
        "# assets/baseline/ are relative to the site's output root (site/draft/ while staged, site/ after",
        "# promotion), and each build tool's key under .baseline/ is relative to the repository root, outside site/.",
        f"# Source: https://posluns.ca/baseline/baseline-{version}.tar.gz, archive sha256 {args.archive_sha256};",
        f"# SHA256SUMS sha256 {args.sums_sha256}, copied to .baseline/SHA256SUMS.",
        "# Never edit a copied file; a new version arrives as a new copy and a new pin.",
        f'version = "{version}"',
        "",
        "[files]",
    ]
    lines += [f'"{PREFIX}{name}" = "{listed[name]}"' for name in chosen]
    lines += [f'"{key}" = "{listed[tool_source]}"' for key, tool_source in tools.items()]
    write_new(PIN_DIR / "pin.toml", ("\n".join(lines) + "\n").encode("utf-8"))
    copying = False
    # The checks before the first write cover only the paths written and read here; the gate checks the whole tree,
    # so success is reported only for a tree the gate passes.
    try:
        problems = gate.check(REPO_ROOT)
    except gate.Unreadable as error:
        die(3, f"wrote the copy and the pin, but {GATE.name} could not check the tree: {error}")
    if problems:
        print(f"copy-baseline: wrote the copy and the pin, but {GATE.name} refuses the tree:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"copied {len(chosen) + len(tools)} files of baseline {version} ({len(chosen)} to {PREFIX} and "
          f"{len(tools)} build tool files to .baseline/) and wrote .baseline/pin.toml; copied the documents "
          f"{' and '.join(DOCUMENTS)} to .baseline/, not pinned; {GATE.name} passes the tree")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except OSError as error:
        # A file that cannot be read or written ends the run with the documented code, not a traceback; once copying
        # has begun, die() adds that the copy and the pin may be incomplete, since the gate's check has not run.
        die(3, f"a file could not be read or written: {error}")
    except Exception as error:
        # Any other error, such as a RecursionError from a deeply nested path, also ends the run with exit 3 and no
        # traceback, so that a failure after the first change is never reported without saying that the copy and the
        # pin may be incomplete. An interrupt or a SystemExit is not an Exception and passes through.
        die(3, f"stopped by an unexpected {type(error).__name__}: {error}")
