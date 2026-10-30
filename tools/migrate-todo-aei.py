#!/usr/bin/env python3
"""One-shot conversion of the 4-column backlog table to the 8-column AEI table (item 28.2 stage 2).

Old shape:  | # | Opened | Item | Closure evidence required |
New shape:  | # | Opened | State | Granted | Blocker | Evidence | Item | Closure evidence required |

Each old data row becomes a new row with state "open", granted "yes", blocker "-" and evidence "-".
granted "yes" is the conservative default: "no" would route the row to the proposed bucket, which
never blocks a Stop (aiqt_hooks.py:8118-8120), so a row is demoted only by a recorded decision. The
id, opened, item and closure cell segments are copied byte for byte, including their surrounding
blanks and any "\\|" escape, and so is any text after the closing bar. The header and the separator
row gain the four new columns. Every line that is not a table line is copied byte for byte, line
endings included. Blocker annotation is a separate, reviewed step after this mechanical pass.

The old table is parsed with a parser of its own, independent of tools/orch-enumerate-backlog.py, so
the loss check can compare two parsers rather than one parser with itself:
- a table line begins with "|" at column 0 (the first character of the line once only its "\\n"
  terminator is removed); any other line that contains a "|" anywhere is rejected naming the line,
  whatever comes before the bar (an indent, an invisible, combining or filler character such as
  U+200B, U+034F, U+FE0F, U+3164, U+FFA0 or a U+FEFF byte order mark, a blockquote marker, a GFM
  row with no leading pipe, or plain prose), so no row is ever copied through as prose, where both
  loss-check dumps would agree on the loss. This is a single rule rather than a list of prefix
  classes; the backlog keeps every "|" inside a column-0 table line. The message names, by code
  point, each character before the first "|" that is not printable ASCII;
- a line that holds no "|" but reads as the first two cells of a data row is rejected naming the
  line: skipping its leading characters that are whitespace, ">" (a blockquote marker) or outside
  printable ASCII, it starts with an item id (digits with optional dotted parts, such as 27 or
  28.2), then at least one whitespace or ASCII punctuation character, then a date written
  YYYY-MM-DD. Such a line is a row that has lost all its pipes; copied through as prose, it would
  vanish from both loss-check dumps alike, and since the backlog mixes rows with blank lines, prose
  and HTML comments inside one table span, the structure alone cannot single it out. Prose,
  headings, list items and HTML comments do not start that way and are copied as before. Residual
  (disclosed): a row that has lost its pipes and also its id or date shape, or whose cells follow
  printable ASCII such as "- " or "<!--", cannot be told from prose and is copied through; the
  hook anti-shrinkage checkpoint covers only ids that an earlier enumeration listed, so it is no
  backstop for an id that was never enumerated;
- cells are split on "|" not preceded by a backslash, and the line must end with an unescaped "|";
- the header is the table line whose first cell is "#" and must equal the old header exactly; an
  input that already carries the new header is refused as already migrated;
- a separator row has 4 cells of dashes and colons; every other table line is a data row of exactly
  4 cells with an id matching ^[0-9]+(\\.[0-9]+)*$, unique, after the header;
- one header only, and at least one data row (an empty table is refused, never converted).
The whole input is parsed before anything is written, so a malformed input writes nothing.

Write safety: the script never writes in place. The output path must be given explicitly, must not
exist (not even as a dangling symlink), and must not resolve to the input. It is created with
O_CREAT | O_EXCL and mode 0600, so an existing file is never overwritten. A write that fails part
way (for example ENOSPC) removes the partial output it created and exits 1, so a failed run never
leaves a truncated file that a later step could mistake for a complete conversion. Applying the
output to the record store is a separate step outside this script.

Usage:
    migrate-todo-aei.py <input> <output>
        Convert; print a one-line JSON summary (count of converted rows) on stdout.
    migrate-todo-aei.py --dump-old-cells <input>
        Print the id, opened, item and closure cells of every old data row (stripped of the
        surrounding blanks, escapes kept as written) with a sha256 per row, for the loss check.
Exit 0 on success, 1 on a refused or malformed input or output, 2 on a usage error. An input that is
not valid UTF-8 is refused naming the line and the byte offset of the first invalid byte.

The script runs isolated: started without -I, it re-executes itself under python3 -I before it
imports anything beyond os and sys, so a file planted beside it cannot shadow a standard-library
import (the same guard as tools/orch-enumerate-backlog.py). A failed re-execution exits 1.
"""
import os
import sys

if not sys.flags.isolated:
    # Isolated mode keeps this script directory and the environment off the import path, so a file
    # written beside the script cannot shadow a standard-library module (SECI config rule).
    try:
        os.execv(sys.executable, [sys.executable, "-I", os.path.abspath(__file__)] + sys.argv[1:])
    except OSError as exc:
        print("migrate-todo-aei: FAIL: cannot re-execute under python3 -I: {}".format(exc),
              file=sys.stderr)
        sys.exit(1)

import hashlib
import json
import re
import string

PROG = "migrate-todo-aei"
OLD_HEADER = ["#", "Opened", "Item", "Closure evidence required"]
NEW_HEADER = ["#", "Opened", "State", "Granted", "Blocker", "Evidence", "Item",
              "Closure evidence required"]
ID_RE = re.compile(r"^[0-9]+(\.[0-9]+)*$")
BAR_RE = re.compile(r"(?<!\\)\|")
DASH_RE = re.compile(r"^:?-+:?$")
NEW_DATA_CELLS = (" open ", " yes ", " - ", " - ")
NEW_HEADER_CELLS = (" State ", " Granted ", " Blocker ", " Evidence ")
NEW_SEPARATOR_CELLS = (" --- ", " --- ", " --- ", " --- ")


class MigrationError(Exception):
    """A refused or malformed input or output."""


def _fail(msg, code=1):
    print("{}: FAIL: {}".format(PROG, msg), file=sys.stderr)
    sys.exit(code)


def _misplaced_bar(line):
    """None when line is a column-0 table line or holds no "|"; otherwise a description of the
    text before its first "|", with every character outside printable ASCII given by code point.
    A single rule, independent of what the prefix is made of."""
    if line[:1] == "|":
        return None
    cut = line.find("|")
    if cut < 0:
        return None
    lead = line[:cut]
    hidden = []
    for ch in lead:
        code = ord(ch)
        if not 0x20 <= code <= 0x7E:
            label = "U+%04X" % code
            if label not in hidden:
                hidden.append(label)
    if hidden:
        return "{} character(s), including {}".format(len(lead), ", ".join(hidden))
    return "{} character(s) of printable ASCII {!r}".format(len(lead), lead[:40])


def _ascii_digits(text):
    return bool(text) and all("0" <= ch <= "9" for ch in text)


def _starts_like_a_row(line):
    """True when a line without "|" opens with an item id and a YYYY-MM-DD date, the first two
    cells of a row that has lost its pipes. Leading whitespace, ">" and characters outside
    printable ASCII are skipped first; every candidate id end is tried, so a dotted id such as 28.2
    directly followed by ".2026-10-01" is still seen."""
    n = len(line)
    start = 0
    while start < n and (line[start].isspace() or line[start] == ">"
                         or not "!" <= line[start] <= "~"):
        start += 1
    stop = start
    while stop < n and (line[stop] == "." or "0" <= line[stop] <= "9"):
        stop += 1
    for end in range(start + 1, stop + 1):
        if not ID_RE.match(line[start:end]):
            continue
        pos = end
        while pos < n and (line[pos].isspace() or line[pos] in string.punctuation):
            pos += 1
        if pos == end:
            continue
        date = line[pos:pos + 10]
        if (len(date) == 10 and date[4] == "-" and date[7] == "-" and _ascii_digits(date[:4])
                and _ascii_digits(date[5:7]) and _ascii_digits(date[8:])):
            return True
    return False


def _segments(line, lineno):
    """(segments, tail) for a table line: the raw cell segments and the text after the closing bar."""
    content = line[:-1] if line.endswith("\r") else line
    body = content.rstrip(" \t")
    tail = line[len(body):]
    parts = BAR_RE.split(body)
    # A line beginning with "|" splits to a leading "" part; a closing unescaped bar gives a trailing "".
    if len(parts) < 3 or parts[0] != "" or parts[-1] != "":
        raise MigrationError("line {}: table row does not end with an unescaped \"|\"".format(lineno))
    return parts[1:-1], tail


def _row(segments, inserted, tail):
    """Rebuild an 8-cell line: id and opened segments, the four inserted cells, item and closure."""
    cells = list(segments[:2]) + list(inserted) + list(segments[2:])
    return "|" + "|".join(cells) + "|" + tail


def convert(text):
    """(new_text, rows) for the old-shape backlog text; rows are the stripped 4-cell tuples."""
    out, rows, seen = [], [], {}
    header_at = None
    for lineno, line in enumerate(text.split("\n"), start=1):
        if not line.startswith("|"):
            misplaced = _misplaced_bar(line)
            if misplaced is not None:
                raise MigrationError("line {}: a \"|\" off column 0 (before it: {}); a table row "
                                     "must begin with \"|\" at column 0 and no other line may "
                                     "contain \"|\", so no row is copied through as prose"
                                     .format(lineno, misplaced))
            if _starts_like_a_row(line):
                raise MigrationError("line {}: no \"|\" on this line, but it opens with an item "
                                     "id and a YYYY-MM-DD date like a data row whose pipes were "
                                     "lost; it is refused rather than copied through as prose"
                                     .format(lineno))
            out.append(line)
            continue
        segments, tail = _segments(line, lineno)
        cells = [s.strip(" \t") for s in segments]
        if cells[0] == "#":
            if header_at is not None:
                raise MigrationError("line {}: second header (first at line {})"
                                     .format(lineno, header_at))
            if cells == NEW_HEADER:
                raise MigrationError("line {}: input already carries the 8-column header".format(lineno))
            if cells != OLD_HEADER:
                raise MigrationError("line {}: header is not the expected 4-column header".format(lineno))
            header_at = lineno
            out.append(_row(segments, NEW_HEADER_CELLS, tail))
            continue
        if header_at is None:
            raise MigrationError("line {}: table row before the header".format(lineno))
        if len(cells) != len(OLD_HEADER):
            raise MigrationError("line {}: row has {} cells, expected {}"
                                 .format(lineno, len(cells), len(OLD_HEADER)))
        if all(DASH_RE.match(c) for c in cells):
            out.append(_row(segments, NEW_SEPARATOR_CELLS, tail))
            continue
        iid = cells[0]
        if not ID_RE.match(iid):
            raise MigrationError("line {}: bad item id {!r}".format(lineno, iid))
        if iid in seen:
            raise MigrationError("line {}: duplicate item id {} (first at line {})"
                                 .format(lineno, iid, seen[iid]))
        seen[iid] = lineno
        rows.append(tuple(cells))
        out.append(_row(segments, NEW_DATA_CELLS, tail))
    if header_at is None:
        raise MigrationError("no 4-column header row")
    if not rows:
        raise MigrationError("the table has no data row (an empty table is not converted)")
    return "\n".join(out), rows


def read_input(path):
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise MigrationError("cannot read input {}: {}".format(path, exc.strerror or exc))
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        line = data[:exc.start].count(b"\n") + 1
        raise MigrationError("input {} is not valid UTF-8 (line {}, byte offset {})"
                             .format(path, line, exc.start))


def write_output(in_path, out_path, text):
    """Create out_path exclusively; refuse an existing path or one that resolves to the input."""
    if os.path.lexists(out_path):
        raise MigrationError("output {} already exists (it is never overwritten)".format(out_path))
    if os.path.realpath(out_path) == os.path.realpath(in_path):
        raise MigrationError("output {} resolves to the input".format(out_path))
    try:
        fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as exc:
        raise MigrationError("cannot create output {}: {}".format(out_path, exc.strerror or exc))
    created = None
    try:
        created = os.fstat(fd)
        fh = os.fdopen(fd, "wb")
        fd = None
        with fh:
            fh.write(text.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
    except OSError as exc:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        raise MigrationError("cannot write output {}: {}; {}".format(
            out_path, exc.strerror or exc, _remove_partial(out_path, created)))


def _remove_partial(out_path, created):
    """Remove the partial output this run created; the path is unlinked only while it is still the
    file the exclusive create made (same device and inode), so a file swapped in since is kept."""
    try:
        current = os.lstat(out_path)
    except OSError as exc:
        return "the partial output could not be checked ({})".format(exc.strerror or exc)
    if created is not None and (current.st_dev, current.st_ino) != (created.st_dev, created.st_ino):
        return "the path no longer names the file this run created, so it was left in place"
    try:
        os.unlink(out_path)
    except OSError as exc:
        return "the partial output could NOT be removed ({}); delete it before any retry".format(
            exc.strerror or exc)
    return "the partial output was removed"


def row_digest(row):
    """The sha256 of one (id, opened, item, closure) tuple, as canonical JSON in UTF-8."""
    return hashlib.sha256(json.dumps(list(row), ensure_ascii=False).encode("utf-8")).hexdigest()


def main(argv):
    if len(argv) == 2 and argv[0] == "--dump-old-cells":
        in_path = os.path.abspath(argv[1])
        try:
            _text, rows = convert(read_input(in_path))
        except MigrationError as exc:
            _fail(str(exc))
        out = {"source": in_path, "count": len(rows),
               "rows": [{"cells": list(r), "sha256": row_digest(r)} for r in rows]}
        sys.stdout.write(json.dumps(out) + "\n")
        return 0
    if len(argv) != 2 or not all(argv) or any(a.startswith("-") for a in argv):
        _fail("usage: {0}.py <input> <output> | {0}.py --dump-old-cells <input>".format(PROG), 2)
    in_path, out_path = os.path.abspath(argv[0]), os.path.abspath(argv[1])
    try:
        if in_path == out_path:
            raise MigrationError("output path is the input path (the script never writes in place)")
        new_text, rows = convert(read_input(in_path))
        write_output(in_path, out_path, new_text)
    except MigrationError as exc:
        _fail(str(exc))
    sys.stdout.write(json.dumps({"input": in_path, "output": out_path, "converted": len(rows)}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
