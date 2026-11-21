#!/usr/bin/env python3
"""Check that the allowlist claims every tracked line that names a licence term, and no more.

The search. A line names a licence term when it holds BY-SA, ShareAlike or Creative Commons in
any ASCII letter case, as git grep -i -E reads that 3-way alternation. Each tracked file is read
from the work tree as bytes and split at each line feed only, so a carriage return stays in its
line and each line has the number git grep -n gives it, and a file need not be UTF-8 to be read.

The tracked files are the entries that git ls-files --stage -z lists for the repository at the
root, run with a fixed argument list and no shell. File content is data: no line of a file is
run, parsed as code or printed.

The allowlist, tools/licence-names-allowlist.tsv, is UTF-8 text with LF line ends. A line that is
empty or starts with # is skipped. Every other line is a row of exactly 4 fields separated by a
tab: a repository-relative path, a count matching [1-9][0-9]*, an owner (unit-2, unit-3 or keep)
and a marker, a literal text matched with its letter case. A row claims each matching line of its
path that holds its marker. The gate fails on:

- a matching line that no row of its path claims (unclaimed);
- a matching line that the markers of 2 or more rows of its path claim (ambiguous), so a broad
  marker cannot quietly take lines of another kind;
- a row whose claimed lines differ in number from its count (stale), which includes a row whose
  lines are gone;
- a malformed row: another number of fields, a carriage return, a bad count or owner, an empty
  marker, a path that is not tracked, a path of a named exception, or the path and marker of an
  earlier row. A malformed row claims nothing.

The named exceptions are the gate's own 3 files, NAMED_EXCEPTIONS: this gate, the allowlist and
tools/test-check-licence-names.py. Their lines are not compared, since they must hold the terms.
Each must be tracked and must hold at least 1 matching line, so the list cannot quietly cover a
file that needs no exemption.

Fail closed: the gate exits 1, naming the cause, and turns no error into an empty or clean
result, when git ls-files cannot run, fails or lists nothing; when an entry is unmerged (a stage
other than 0); when a tracked path has a mode other than 100644 or 100755, such as a symbolic link
(120000) or a submodule (160000); when a tracked path is not a regular file in the work tree, or
cannot be opened or read; and when the allowlist cannot be read or is not UTF-8.

Output and exit codes. Each problem goes to standard error, prefixed "check-licence-names: ",
then the line "check-licence-names: checked: N lines in M files; P problem(s)" goes to standard
output, where N and M count the matching lines and files outside the named exceptions. Every
character outside printable ASCII in a path or marker is written as a backslash escape. Exit 0
when the allowlist and the tree agree; 1 on any problem; 2 on a bad invocation (argparse's own
code). --list prints "path:count" for each file outside the named exceptions with a matching line,
then "total: N lines in M files", and exits 1 on a listing or reading problem. --root PATH points
the gate at another repository.

Not covered: another spelling of a licence, such as one in words without the 3 terms, a term split
over 2 lines or a lookalike character outside ASCII; untracked and ignored files; the index copy
of a file whose work-tree copy differs (in CI they are equal); whether a line is a true statement
of a licence; whether the owner of a row is right, which is reviewed prose; and the named
exceptions' own lines. A row counts lines per file, so fixing 1 line and adding another of the
same kind in the same file passes.
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
    return f"{type(error).__name__}: {shown(' '.join(str(error).split()))[:300]}"


def tracked(root: Path, problems: list):
    """{path: mode} for each entry git ls-files lists, or None when the listing fails."""
    argv = ["git", "-C", str(root), "ls-files", "--stage", "-z"]
    try:
        done = subprocess.run(argv, capture_output=True, stdin=subprocess.DEVNULL, shell=False)
    except OSError as error:
        problems.append(f"cannot run git ls-files, so no tracked file can be listed: {error_text(error)}")
        return None
    if done.returncode != 0:
        detail = shown(" ".join(done.stderr.decode("utf-8", "replace").split()))[:300]
        problems.append(f"git ls-files exited {done.returncode}, so no tracked file can be listed: {detail}")
        return None
    entries = {}
    for entry in done.stdout.split(b"\0"):
        if not entry:
            continue
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
    if not entries:
        problems.append("git ls-files lists no tracked file, so there is nothing to compare")
        return None
    return entries


def read_file(root: Path, path: str, problems: list):
    """The bytes of the regular work-tree file at path, or None, with a problem, when it cannot be read."""
    full = root / path
    try:
        info = os.lstat(full)
    except OSError as error:
        problems.append(f"{shown(path)}: cannot read the tracked file: {error_text(error)}")
        return None
    if not stat.S_ISREG(info.st_mode):
        problems.append(f"{shown(path)}: the tracked path is not a regular file in the work tree")
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(full, flags)
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                problems.append(f"{shown(path)}: the tracked path is not a regular file in the work tree")
                return None
            return handle.read()
    except OSError as error:
        problems.append(f"{shown(path)}: cannot read the tracked file: {error_text(error)}")
        return None


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
    """The well-formed rows of the allowlist, each (row line number, path, count, owner, marker)."""
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
        if not COUNT.fullmatch(count):
            problems.append(f"{where}: the count {shown(count)!r} is not a number from 1 with no leading zero")
        elif owner not in OWNERS:
            problems.append(f"{where}: the owner {shown(owner)!r} is none of {', '.join(OWNERS)}")
        elif not marker:
            problems.append(f"{where}: the marker is empty")
        elif path in NAMED_EXCEPTIONS:
            problems.append(f"{where}: {shown(path)} is a named exception, whose lines are not compared")
        elif path not in entries:
            problems.append(f"{where}: {shown(path)} is not a tracked path")
        elif (path, marker) in seen:
            problems.append(f"{where}: it repeats the path and marker of row {seen[(path, marker)]}")
        else:
            seen[(path, marker)] = number
            rows.append((number, path, int(count), owner, marker))
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
        if claimed[number] != count:
            problems.append(f"{shown(path)}: allowlist row {number} ({owner}, marker {shown(marker)!r}) is stale: "
                            f"it claims {claimed[number]} line(s), the allowlist says {count}")


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
