#!/usr/bin/env python3
"""Check that the allowlist claims every tracked line that names a licence term, and no more.

The search. A line names a licence term when it holds BY-SA, ShareAlike or Creative Commons in
any ASCII letter case, as LC_ALL=C git grep -a -i -E reads that 3-way alternation. Each tracked
file is read from the work tree as bytes and split at each line feed only, so a carriage return
stays in its line, each line has the number that LC_ALL=C git grep -a -n gives it, and a file need
not be UTF-8 to be read. The comparison with git grep needs both settings: under a UTF-8 locale
git grep -i also matches non-ASCII forms that this gate does not, such as a long s (U+017F) in
place of an s, and without -a git grep reports a match in a file it treats as binary, such as one
that holds a NUL byte, with no line number.

The tracked files are the entries that git ls-files --stage -z lists for the repository at the
root, run with a fixed argument list and no shell. Git gets the gate's environment without
GIT_DIR, GIT_INDEX_FILE and GIT_COMMON_DIR, the 3 settings that would point it at another
repository or index than the one it finds at the root. File content is data: no line of a file is
run, parsed as code or printed whole; besides the gate's own words and counts, a problem line
shows only the fields that the output paragraph below names, written as that paragraph states.

The allowlist, tools/licence-names-allowlist.tsv, is UTF-8 text with LF line ends. A line that is
empty or starts with # is skipped. Every other line is a row of exactly 4 fields separated by a
tab: a repository-relative path, a count, an owner (unit-2, unit-3 or keep) and a marker, a
literal text matched with its letter case. The count is canonical ASCII decimal: it matches
[1-9][0-9]* in full, so a sign, a space, a leading zero, a digit outside ASCII or any other
spelling is a bad count. It is compared as text with the decimal number of claimed lines, so a
count of any length is read. A row claims each matching line of its path that holds its marker
and the marker of no other row of that path.

The gate fails on a matching line that no row of its path claims (unclaimed); on a matching line
that holds the markers of 2 or more rows of its path (ambiguous), which none of those rows claims,
so a broad marker cannot quietly take lines of another kind; on a row whose claimed lines differ
in number from its count (stale), fewer or more, which includes a row whose lines are gone, though
a row of a path that cannot be read is not reported stale, since its lines are unknown; and on a
malformed row, which claims nothing: a row with a number of fields other than 4, a carriage
return, a count that is not canonical ASCII decimal, an owner other than unit-2, unit-3 or keep,
an empty marker, a path that is not tracked, a path of a named exception, or the path and marker
of an earlier row that has 4 fields and no carriage return, whether or not that earlier row is
well formed.

The named exceptions are the gate's own 3 files, NAMED_EXCEPTIONS: this gate, the allowlist and
tools/test-check-licence-names.py. Their lines are not compared, since they must hold the terms.
Each must be tracked and must hold at least 1 matching line, so the list cannot quietly cover a
file that needs no exemption.

The gate fails closed, exiting 1 and naming the cause, and turns no error into an empty or clean
result: when git ls-files cannot run, fails or lists nothing; when it gives an entry that cannot
be read (one with no tab, or without exactly 3 fields before its tab); when an entry is unmerged
(a stage other than 0); when a tracked path has a mode other than 100644 or 100755, such as a
symbolic link (120000) or a submodule (160000); when a tracked path is not a regular file in the
work tree (which includes a path that is absolute, a path with a part that is empty, 1 dot
or 2 dots, and a path with a parent at any depth that is a symbolic link or anything else but a
folder) or cannot be opened or read; and when the allowlist cannot be read or is not UTF-8. When
git ls-files lists entries and the gate can read none of them, it names each entry and no other
cause.

Output and exit codes. Each problem goes to standard error, prefixed "check-licence-names: ",
then, without --list, the line "check-licence-names: checked: N lines in M files; P problem(s)"
goes to standard output, where N and M count the matching lines and files outside the named
exceptions. Git's message (its standard error, read as UTF-8 with U+FFFD in place of bytes that
are not UTF-8) and an error's text are first made 1 line, each run of whitespace that Python's
str.split finds written as 1 space, or dropped at either end, and cut to their first 300
characters. Then, in every field that a problem line or --list shows (a path, line number,
allowlist row number, count, owner, marker, mode, stage, entry of git ls-files, git's exit code,
git's message or an error's text),
each character outside printable ASCII is written once as \\xHH, \\uHHHH or \\UHHHHHHHH, and a
backslash as \\\\, so no control byte reaches the output and no escape is cut. Exit 0 when the
allowlist and the tree agree; 1 on any problem; 2 on a bad invocation, such as an unknown option (argparse's
own code). --list prints "path:count" for each file outside the named exceptions with a matching
line, then "total: N lines in M files". It does not parse the allowlist, so it reports no
unclaimed or ambiguous line, no stale or malformed row and no allowlist that is not UTF-8. It
exits 1 when git ls-files cannot run, fails or lists nothing; on an entry of git ls-files that
cannot be read; on an unmerged entry; on a tracked path with a mode other than 100644 or 100755;
on a tracked path, the allowlist included, that is not a regular file in the work tree or cannot
be read; and on a named exception that is not tracked or holds no matching line. --root PATH
points the gate at another repository.

Not covered: another spelling of a licence, such as one in words without the 3 terms, a term split
over 2 lines or a lookalike character outside ASCII; untracked and ignored files; the index copy
of a file whose work-tree copy differs (in CI they are equal); a folder of the work tree that is a
mount point and a file that is a hard link, each read where it stands; a work tree that changes
while the gate runs, since the root is opened by its path for each file and an opened folder is
read wherever it is moved, so a root replaced or a folder moved out of the work tree during the
run can lead a read outside it; whether a line is a true statement of a licence; whether the
owner of a row is right, which is reviewed prose; and the named exceptions' own lines. A row
counts lines per file, so fixing 1 line and adding another of the same kind in the same file
passes.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERN = re.compile(rb"BY-SA|ShareAlike|Creative Commons", re.IGNORECASE)
ALLOWLIST = "tools/licence-names-allowlist.tsv"
NAMED_EXCEPTIONS = ("tools/check-licence-names.py", ALLOWLIST, "tools/test-check-licence-names.py")
OWNERS = ("unit-2", "unit-3", "keep")
REGULAR_MODES = ("100644", "100755")
COUNT = re.compile(r"[1-9][0-9]*")
PREFIX = "check-licence-names: "
# The settings that would point git at another repository or index than the one at the root.
GIT_LOCATIONS = ("GIT_DIR", "GIT_INDEX_FILE", "GIT_COMMON_DIR")


def shown(text: str) -> str:
    """text with every character outside printable ASCII, and the backslash, written as an escape."""
    out = []
    for char in text:
        code = ord(char)
        if char == "\\":
            out.append("\\\\")
        elif 0x20 <= code < 0x7F:
            out.append(char)
        elif code < 0x100:
            out.append(f"\\x{code:02x}")
        elif code < 0x10000:
            out.append(f"\\u{code:04x}")
        else:
            out.append(f"\\U{code:08x}")
    return "".join(out)


def error_text(error: BaseException) -> str:
    return f"{type(error).__name__}: {shown(' '.join(str(error).split())[:300])}"


def tracked(root: Path, problems: list):
    """{path: mode} for each entry git ls-files lists, or None when the listing fails."""
    argv = ["git", "-C", str(root), "ls-files", "--stage", "-z"]
    env = {name: value for name, value in os.environ.items() if name not in GIT_LOCATIONS}
    try:
        done = subprocess.run(argv, capture_output=True, stdin=subprocess.DEVNULL, shell=False, env=env)
    except OSError as error:
        problems.append(f"cannot run git ls-files, so no tracked file can be listed: {error_text(error)}")
        return None
    if done.returncode != 0:
        detail = shown(" ".join(done.stderr.decode("utf-8", "replace").split())[:300])
        problems.append(f"git ls-files exited {done.returncode}, so no tracked file can be listed: {detail}")
        return None
    entries, listed = {}, 0
    for entry in done.stdout.split(b"\0"):
        if not entry:
            continue
        listed += 1
        info, tab, raw = entry.partition(b"\t")
        fields = info.split()
        if not tab or len(fields) != 3:
            problems.append(f"git ls-files gave an entry that cannot be read: {shown(os.fsdecode(entry))}")
            continue
        path = os.fsdecode(raw)
        mode, stage = fields[0].decode("ascii", "replace"), fields[2].decode("ascii", "replace")
        if stage != "0":
            problems.append(f"{shown(path)}: an unmerged index entry (stage {shown(stage)}), so the gate "
                            "cannot tell which version is tracked")
        entries.setdefault(path, mode)
    if not listed:
        problems.append("git ls-files lists no tracked file, so there is nothing to compare")
        return None
    # When git listed entries and each was refused above with its own problem, nothing is compared.
    return entries or None


def read_file(root: Path, path: str, problems: list):
    """The bytes of the regular work-tree file at path, or None, with a problem, when it cannot be read.

    The path is opened 1 part at a time from the root, each part inside the folder opened before it and
    none through a symbolic link, so a symbolic link in the work tree cannot lead a read outside it. A
    work tree that changes while the gate runs is not covered: the root is opened by its path for each
    file and an opened folder is read wherever it is moved, so a root replaced or a folder moved out of
    the work tree during the run can lead a read outside it."""
    not_regular = f"{shown(path)}: the tracked path is not a regular file in the work tree"
    parts = path.split("/")
    # An absolute path has an empty first part.
    if any(part in ("", ".", "..") for part in parts):
        problems.append(f"{not_regular}, since it is not a plain relative path")
        return None
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    folder_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow
    folder = None
    try:
        folder = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        for number, part in enumerate(parts[:-1], 1):
            not_folder = f"{not_regular}, since its parent {shown('/'.join(parts[:number]))} is not a folder in the work tree"
            if not stat.S_ISDIR(os.lstat(part, dir_fd=folder).st_mode):
                problems.append(not_folder)
                return None
            inner = os.open(part, folder_flags, dir_fd=folder)
            os.close(folder)
            folder = inner
            if not stat.S_ISDIR(os.fstat(folder).st_mode):
                problems.append(not_folder)
                return None
        if not stat.S_ISREG(os.lstat(parts[-1], dir_fd=folder).st_mode):
            problems.append(not_regular)
            return None
        fd = os.open(parts[-1], os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0), dir_fd=folder)
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                problems.append(not_regular)
                return None
            return handle.read()
    except OSError as error:
        problems.append(f"{shown(path)}: cannot read the tracked file: {error_text(error)}")
        return None
    finally:
        if folder is not None:
            os.close(folder)


def matching_lines(data: bytes) -> list:
    """(line number, line) for each line of data, split at LF only, that names a licence term."""
    return [(number, line) for number, line in enumerate(data.split(b"\n"), 1) if PATTERN.search(line)]


def scan(root: Path, entries: dict, problems: list):
    """({path: [(number, line)]} for files outside the named exceptions, the set of unreadable paths)."""
    found, unreadable = {}, set()
    for path, mode in sorted(entries.items()):
        if mode not in REGULAR_MODES:
            problems.append(f"{shown(path)}: tracked with mode {shown(mode)}, not as a regular file "
                            "(a symbolic link or a submodule), so the gate cannot read it")
            unreadable.add(path)
            continue
        data = read_file(root, path, problems)
        if data is None:
            unreadable.add(path)
            continue
        lines = matching_lines(data)
        if path in NAMED_EXCEPTIONS:
            if not lines:
                problems.append(f"{shown(path)}: a named exception that holds no matching line")
        elif lines:
            found[path] = lines
    for path in NAMED_EXCEPTIONS:
        if path not in entries:
            problems.append(f"{shown(path)}: a named exception that git does not track")
    return found, unreadable


def read_allowlist(root: Path, entries: dict, problems: list) -> list:
    """The well-formed rows of the allowlist, each (row line number, path, count text, owner, marker)."""
    data = read_file(root, ALLOWLIST, problems)
    if data is None:
        problems.append(f"{ALLOWLIST}: the allowlist cannot be read, so no line can be claimed")
        return []
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        problems.append(f"{ALLOWLIST}: the allowlist is not UTF-8: {error_text(error)}")
        return []
    rows, seen = [], {}
    for number, line in enumerate(text.split("\n"), 1):
        if line == "" or line.startswith("#"):
            continue
        where = f"{ALLOWLIST}:{number}: malformed row"
        if "\r" in line:
            problems.append(f"{where}: it holds a carriage return")
            continue
        fields = line.split("\t")
        if len(fields) != 4:
            problems.append(f"{where}: it has {len(fields)} tab-separated field(s), not 4")
            continue
        path, count, owner, marker = fields
        earlier = seen.setdefault((path, marker), number)
        if earlier == number:
            earlier = None
        if not COUNT.fullmatch(count):
            problems.append(f"{where}: the count '{shown(count)}' is not canonical ASCII decimal: digits 0 to 9 "
                            "only, from 1, with no sign, space or leading zero")
        elif owner not in OWNERS:
            problems.append(f"{where}: the owner '{shown(owner)}' is none of {', '.join(OWNERS)}")
        elif not marker:
            problems.append(f"{where}: the marker is empty")
        elif path in NAMED_EXCEPTIONS:
            problems.append(f"{where}: {shown(path)} is a named exception, whose lines are not compared")
        elif path not in entries:
            problems.append(f"{where}: {shown(path)} is not a tracked path")
        elif earlier is not None:
            problems.append(f"{where}: it repeats the path and marker of row {earlier}")
        else:
            rows.append((number, path, count, owner, marker))
    return rows


def compare(found: dict, unreadable: set, rows: list, problems: list) -> None:
    by_path = {}
    for row in rows:
        by_path.setdefault(row[1], []).append(row)
    claimed = {row[0]: 0 for row in rows}
    for path, lines in found.items():
        mine = by_path.get(path, [])
        for number, line in lines:
            holders = [row for row in mine if row[4].encode("utf-8") in line]
            if not holders:
                problems.append(f"{shown(path)}:{number}: names a licence term and no allowlist row claims it")
            elif len(holders) > 1:
                problems.append(f"{shown(path)}:{number}: holds the markers of allowlist rows "
                                f"{', '.join(str(row[0]) for row in holders)}, so it is ambiguous and no row "
                                "claims it")
            else:
                claimed[holders[0][0]] += 1
    for number, path, count, owner, marker in rows:
        if path in unreadable:
            continue
        if str(claimed[number]) != count:
            problems.append(f"{shown(path)}: allowlist row {number} ({shown(owner)}, marker '{shown(marker)}') is "
                            f"stale: it claims {claimed[number]} line(s), the allowlist says {shown(count)}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check that the licence-name allowlist matches the tracked tree.")
    parser.add_argument("--root", type=Path, default=ROOT, help="the repository to check (default: this one)")
    parser.add_argument("--list", action="store_true", help="print path:count per file and the total")
    args = parser.parse_args(argv)
    root = args.root
    problems = []
    entries = tracked(root, problems)
    found, unreadable = scan(root, entries, problems) if entries is not None else ({}, set())
    lines = sum(len(v) for v in found.values())
    if args.list:
        for path, matched in sorted(found.items()):
            print(f"{shown(path)}:{len(matched)}")
        print(f"total: {lines} lines in {len(found)} files")
    elif entries is not None:
        compare(found, unreadable, read_allowlist(root, entries, problems), problems)
    for problem in problems:
        print(PREFIX + problem, file=sys.stderr)
    if not args.list:
        print(f"{PREFIX}checked: {lines} lines in {len(found)} files; {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
