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
- one header only, and at least one data row (an empty table is refused at its header line, never
  converted). An input with no header is refused at the line where the scan ended, as "line N (end
  of input)", N being the last line of the input (the empty remainder after a final newline is not
  counted).
The whole input is parsed before anything is written, so a malformed input writes nothing.

Read safety: the input must be a regular file (a symlink to one is followed). It is opened
non-blocking and its type is checked with fstat on the open descriptor, so a FIFO with no writer, a
directory, a device such as /dev/null, or any other file that is not regular is refused (exit 1)
naming the path and the file type, instead of blocking indefinitely or converting an empty input.
Every read of a path in this script goes through that one checked helper (_read_regular), and the
test suite scans the source to keep it so; the only other open is the exclusive create of the
output below.

Write safety: the script never writes in place. The output path must be given explicitly, must not
exist (not even as a dangling symlink), and must not resolve to the input. It is created with
O_CREAT | O_EXCL and mode 0600, so an existing file is never overwritten. A write that fails part
way, by an OSError such as ENOSPC or by any other exception (for example a MemoryError while the
text is encoded, or a KeyboardInterrupt), removes the partial output it created where it can, so
a later step does not mistake a truncated file for a complete conversion. The path is unlinked
only once it is confirmed to name the file this run created (the device and inode read with fstat
after the create), so a file this run did not create is never removed: a path whose identity was
never read, or that now names another file, is left in place.
An OSError is refused with exit 1 there, and any other exception propagates to the runtime guard
below (or, for a KeyboardInterrupt, ends the run). Either refusal names the output and says, in the
same words, what became of the partial output: removed, left in place because the path no longer
names the file this run created, left in place because it could not be confirmed as the file this
run created and to be checked and deleted before any retry, or NOT removed and to be deleted
before any retry. Applying the output to the record store is a separate step outside this script.

Usage:
    migrate-todo-aei.py <input> <output>
        Convert; print a one-line JSON summary (count of converted rows) on stdout.
    migrate-todo-aei.py --dump-old-cells <input>
        Print the id, opened, item and closure cells of every old data row (stripped of the
        surrounding blanks, escapes kept as written) with a sha256 per row, for the loss check.
Exit 0 on success, 1 on a refused or malformed input or output or an unexpected error, 2 on a
usage error. An input that is not valid UTF-8 is refused naming the line and the byte offset of the
first invalid byte.

Every refusal begins, after the "migrate-todo-aei: FAIL: " prefix, with its position: "line N" for a
line of the input, "line N (end of input)" where the scan ended, "line N (end of input, output
refused)" for an output refused after the whole input was read, "before line 1 (input unreadable)"
for an input that cannot be opened or read or is not a regular file, and "before line 1 (no input
read)" for a usage error, an output path equal to the input path, or a failed re-execution. This
holds for every refusal the script writes. A refusal that has no line to name says so rather than
naming an invented one. One top-level guard in main covers the whole run (argument handling,
path resolution, reading, parsing, writing the output file, and writing and flushing stdout): any
exception that escapes the handling above (any Exception, including a BrokenPipeError on stdout and
the FileNotFoundError that os.getcwd raises when the working directory is gone) becomes a refusal
through _fail, exit 1, at the position the run had reached: "before line 1 (no input read)" until
the whole input has been read, "line N (end of input)" after it, and "line N (end of input, output
refused)" once the output step has started (a refusal after the output file was written in full
says so, and the file is left in place). The guard closes stdout before it fails, so the
interpreter does not report a broken pipe a second time at exit; it does not catch
KeyboardInterrupt or the SystemExit that _fail raises. The test suite also scans the source for
every ordinary path that can write a refusal (each MigrationError construction and raise, each
_fail call, each line position handed to a helper, and each write to standard error or exit) so
that each keeps its position. Residual (disclosed): that static scan guards ordinary refusal paths
only; it does not cover deliberately obfuscated routes (a signal or os.kill, exec, a subprocess
writing to descriptor 2, an attribute name built from strings, a line position passed through a
local alias, or assert). The runtime guard turns any escaping exception into a positioned refusal,
so the remaining residual is a process ended without an exception (a signal, exec or os._exit),
which names no position.

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
        print("migrate-todo-aei: FAIL: before line 1 (no input read): cannot re-execute under "
              "python3 -I: {}".format(exc), file=sys.stderr)
        sys.exit(1)

import hashlib
import json
import re
import stat
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
READ_CHUNK = 1 << 20
# The position of a refusal that comes before any line is read: an input that cannot be opened or
# read, or is not a regular file, has no line to name, so the message says so and invents none.
BEFORE_INPUT = "before line 1 (input unreadable)"
# The position of a refusal made before the input is read: a usage error, or an output path that is
# the input path.
NOT_READ = "before line 1 (no input read)"


class MigrationError(Exception):
    """A refused or malformed input or output; the message begins with its position, a line of the
    input or "before line 1" with the reason no line was read."""


def _fail(msg, code=1):
    print("{}: FAIL: {}".format(PROG, msg), file=sys.stderr)
    sys.exit(code)


def _input_error(detail):
    """The MigrationError for an input that was not read: it has no line, so the position is
    BEFORE_INPUT."""
    return MigrationError("{}: {}".format(BEFORE_INPUT, detail))


def _last_line(lines):
    """The number of the last line of a split text; the empty remainder after a final newline is
    not a line."""
    return len(lines) - 1 if len(lines) > 1 and lines[-1] == "" else len(lines)


def _output_error(text, detail):
    """The MigrationError for an output refused after the whole input was read: the position is
    the end of input. convert emits exactly one output line per input line, so the last line of the
    output text is the last line of the input."""
    return MigrationError("line {} (end of input, output refused): {}".format(
        _last_line(text.split("\n")), detail))


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
    lines = text.split("\n")
    for lineno, line in enumerate(lines, start=1):
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
        # Name the last line read; the empty remainder after a final newline is not a line.
        raise MigrationError("line {} (end of input): no 4-column header row, so no backlog table"
                             .format(_last_line(lines)))
    if not rows:
        raise MigrationError("line {}: header with no data row (an empty table is not converted)"
                             .format(header_at))
    return "\n".join(out), rows


def _type_name(mode):
    """A name for the file type of an st_mode that is not a regular file."""
    for test, name in ((stat.S_ISDIR, "directory"), (stat.S_ISCHR, "character device"),
                       (stat.S_ISBLK, "block device"), (stat.S_ISFIFO, "FIFO"),
                       (stat.S_ISSOCK, "socket"), (stat.S_ISLNK, "symbolic link")):
        if test(mode):
            return name
    return "file of unknown type (st_mode {:o})".format(stat.S_IFMT(mode))


def _read_regular(path):
    """The bytes of path, refused with a MigrationError unless it is a regular file. The open does
    not block, so a FIFO with no writer cannot hang the run; fstat checks the type of the open
    descriptor itself, so the checked file is the read file. The descriptor is then switched back to
    blocking mode and read until end of file. No other function opens a path for reading."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError as exc:
        raise _input_error("cannot read input {}: {}".format(path, exc.strerror or exc))
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            raise _input_error("input {} is not a regular file (it is a {}); only a regular file "
                               "is converted".format(path, _type_name(mode)))
        os.set_blocking(fd, True)
        parts = []
        chunk = os.read(fd, READ_CHUNK)
        while chunk:
            parts.append(chunk)
            chunk = os.read(fd, READ_CHUNK)
        return b"".join(parts)
    except OSError as exc:
        raise _input_error("cannot read input {}: {}".format(path, exc.strerror or exc))
    finally:
        os.close(fd)


def read_input(path):
    data = _read_regular(path)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        line = data[:exc.start].count(b"\n") + 1
        raise MigrationError("line {}: input {} is not valid UTF-8 (byte offset {})"
                             .format(line, path, exc.start))


def write_output(in_path, out_path, text, reached=None):
    """Create out_path exclusively; refuse an existing path or one that resolves to the input. Every
    refusal is positioned at the end of input, since the whole input was read before the output.
    When an exception other than an OSError interrupts the write, reached["partial"] (if reached is
    given) records the output path and what became of the partial output, for the runtime guard."""
    if os.path.lexists(out_path):
        raise _output_error(text, "output {} already exists (it is never overwritten)"
                            .format(out_path))
    if os.path.realpath(out_path) == os.path.realpath(in_path):
        raise _output_error(text, "output {} resolves to the input".format(out_path))
    try:
        fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as exc:
        raise _output_error(text, "cannot create output {}: {}".format(out_path,
                                                                       exc.strerror or exc))
    created, finished, removed = None, False, False
    try:
        created = os.fstat(fd)
        fh = os.fdopen(fd, "wb")
        fd = None
        with fh:
            fh.write(text.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        finished = True
    except OSError as exc:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            fd = None
        removed = True
        raise _output_error(text, "cannot write output {}: {}; {}".format(
            out_path, exc.strerror or exc, _remove_partial(out_path, created)))
    finally:
        # Any other exception, an Exception that is not an OSError or a BaseException such as
        # KeyboardInterrupt, still removes the partial output under the same-inode condition; the
        # exception then propagates unchanged to the runtime guard in main, which reports the
        # removal result recorded here.
        if not finished and not removed:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            status = _remove_partial(out_path, created)
            if reached is not None:
                reached["partial"] = (out_path, status)


def _remove_partial(out_path, created):
    """Remove the partial output this run created; the path is unlinked only while it is still the
    file the exclusive create made (same device and inode), so a file swapped in since is kept.
    When that identity was never read (created is None, an fstat that failed after the create),
    nothing is unlinked and the status says the path must be checked and deleted before any retry.
    It is total: an Exception that is not an OSError, from the check, the removal or the formatting
    of a status, returns a status naming its type instead of escaping, so the refusal of the caller
    always says what became of the partial output. KeyboardInterrupt and SystemExit are not
    Exception and pass through."""
    try:
        if created is None:
            return ("the partial output could not be confirmed as the file this run created, so "
                    "the path was left in place; check it and delete it before any retry")
        try:
            current = os.lstat(out_path)
        except OSError as exc:
            return "the partial output could not be checked ({})".format(exc.strerror or exc)
        if (current.st_dev, current.st_ino) != (created.st_dev, created.st_ino):
            return "the path no longer names the file this run created, so it was left in place"
        try:
            os.unlink(out_path)
        except OSError as exc:
            return "the partial output could NOT be removed ({}); delete it before any retry".format(
                exc.strerror or exc)
        return "the partial output was removed"
    except Exception as exc:
        return ("the partial output could not be checked or removed (unexpected {}); delete it "
                "before any retry".format(type(exc).__name__))


def row_digest(row):
    """The sha256 of one (id, opened, item, closure) tuple, as canonical JSON in UTF-8."""
    return hashlib.sha256(json.dumps(list(row), ensure_ascii=False).encode("utf-8")).hexdigest()


def _discard_stdout():
    """Close stdout before a refusal. A close whose final flush fails still closes the stream, so
    the interpreter does not flush the pending bytes again at exit and report a broken pipe a second
    time with an unpositioned message."""
    stream = sys.stdout
    if stream is None:
        return
    try:
        stream.close()
    except (OSError, ValueError):
        pass


def _unexpected(exc, reached):
    """Refuse, exit 1, for an exception that escaped the handling in _run, at the position the
    run had reached: before line 1 until the whole input was read, then the end of input, and the
    end of input with the output refused once the output step had started."""
    _discard_stdout()
    detail = "unexpected {}: {}".format(type(exc).__name__, " ".join(str(exc).splitlines()))
    if reached["written"] is not None:
        detail += (" (the output {} was written in full before this error and is left in place)"
                   .format(reached["written"]))
    if reached["partial"] is not None:
        detail += "; output {}: {}".format(*reached["partial"])
    if reached["line"] is None:
        _fail("{}: {}".format(NOT_READ, detail))
    if reached["output"]:
        _fail("line {} (end of input, output refused): {}".format(reached["line"], detail))
    _fail("line {} (end of input): {}".format(reached["line"], detail))


def main(argv):
    """The whole run under one guard: any Exception that escapes _run, from argument handling to
    the flush of stdout, is a positioned refusal. KeyboardInterrupt and the SystemExit of _fail are
    not Exception and pass through."""
    reached = {"line": None, "output": False, "written": None, "partial": None}
    try:
        _run(argv, reached)
    except Exception as exc:
        _unexpected(exc, reached)
    return 0


def _run(argv, reached):
    """Convert (or dump) the input named by argv. reached["line"] is set to the end line once the
    whole input has been read, reached["output"] once the output step starts,
    reached["written"] to the output path once it is written in full, and reached["partial"] by
    write_output when an interrupted write left a partial output to remove."""
    if len(argv) == 2 and argv[0] == "--dump-old-cells":
        in_path = os.path.abspath(argv[1])
        try:
            text = read_input(in_path)
            reached["line"] = _last_line(text.split("\n"))
            _text, rows = convert(text)
        except MigrationError as exc:
            _fail(str(exc))
        out = {"source": in_path, "count": len(rows),
               "rows": [{"cells": list(r), "sha256": row_digest(r)} for r in rows]}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()
        return
    if len(argv) != 2 or not all(argv) or any(a.startswith("-") for a in argv):
        _fail("{0}: usage: {1}.py <input> <output> | {1}.py --dump-old-cells <input>"
              .format(NOT_READ, PROG), 2)
    in_path, out_path = os.path.abspath(argv[0]), os.path.abspath(argv[1])
    try:
        if in_path == out_path:
            raise MigrationError("{}: output path is the input path (the script never writes in "
                                 "place)".format(NOT_READ))
        text = read_input(in_path)
        reached["line"] = _last_line(text.split("\n"))
        new_text, rows = convert(text)
        reached["output"] = True
        write_output(in_path, out_path, new_text, reached)
    except MigrationError as exc:
        _fail(str(exc))
    reached["written"] = out_path
    sys.stdout.write(json.dumps({"input": in_path, "output": out_path, "converted": len(rows)}) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
