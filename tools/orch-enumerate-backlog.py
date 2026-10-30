#!/usr/bin/env python3
"""Enumerate the project backlog as one AEI v1 JSON object for the orchestration hooks.

The AIQT orchestration hooks run the registry `enumerator` argv on every Stop, TeammateIdle and
in-roster scheduling call (aiqt_hooks.py:7962-7989, cwd = the repo root, never through a shell) and
validate its stdout with `validate_enumeration` (aiqt_hooks.py:7904-7959). A non-zero exit, a non-JSON
stdout, or an invalid enumeration is ENUMERATOR_ERROR, which denies the Stop and the scheduling call.
This script therefore fails CLOSED: every unreadable input and every malformed row exits 1 naming its
position, and it never prints an empty or partial enumeration in place of an error (an empty backlog
must be affirmed in the file, never inferred from the absence of rows). Every failure message the
script writes begins, after the "orch-enumerate-backlog: FAIL: " prefix, with its position: "line N"
for a line of the input, "line N (end of input)" where the scan ended, "before line 1 (input
unreadable)" for a backlog that cannot be opened or read or is not a regular file, and "before line
1 (no input read)" for a usage error or a failed re-execution. A failure that has no line to name
says so rather than naming an invented one. One top-level guard in main covers the whole run
(argument handling, path resolution, reading, parsing, and writing and flushing stdout): any
exception that escapes the handling above (any Exception, including a BrokenPipeError on stdout and
the FileNotFoundError that os.getcwd raises when the working directory is gone) becomes a failure
through _fail, exit 1, at the position the run had reached, "before line 1 (no input read)" until
the whole input has been read and "line N (end of input)" after it. A KeyboardInterrupt that
reaches main is reported by the same guard in the same form, one line through _fail at the position
the run had reached, but with exit 130 (128 plus SIGINT, the status a shell gives a run ended by an
interrupt), never exit 1, so an interrupted run is not swallowed. The guard closes stdout before it
fails, so the interpreter does not report a broken pipe a second time at exit; it does not catch the
SystemExit that _fail raises. The test suite also scans the source for
every ordinary path that can write a failure (each BacklogError construction and raise, each _fail
call, each line position handed to a helper, and each write to standard error or exit) so that each
keeps its position. Residual (disclosed): that static scan guards ordinary failure paths only; it
does not cover deliberately obfuscated routes (a signal or os.kill, exec, a subprocess writing to
descriptor 2, an attribute name built from strings, a line position passed through a local alias,
or assert). The runtime guard turns any escaping exception into a positioned failure, so the
remaining residual is a process ended without an exception (a signal other than SIGINT, exec or
os._exit), a KeyboardInterrupt raised before main starts (during the re-execution or the imports),
and a second KeyboardInterrupt while the guard writes its failure, none of which names a position.

Backlog grammar (a markdown table, parsed strictly):

    | # | Opened | State | Granted | Blocker | Evidence | Item | Closure evidence required |

- A line is a table line only if it begins with "|" at column 0 (the first character of the raw
  line, after removing only the "\\n" terminator). Every other line that contains a "|" anywhere is
  rejected naming the line, whatever precedes the bar: an indent, an invisible or combining
  character (for example U+200B, U+034F, U+FE0F, U+3164, U+FFA0 or a U+FEFF byte order mark, even
  before a line-1 header), a blockquote marker, a GFM row written without its leading pipe, or plain
  prose. This is one rule, not a list of prefix classes, so no unlisted prefix can hide a row as
  prose. The backlog format keeps every "|" inside a column-0 table line, so prose never carries
  one. The message names each character before the first "|" that is not printable ASCII by its
  code point.
- A line with no "|" at all that has the shape of a data row's first two cells is rejected naming
  the line: once its leading run of whitespace, blockquote markers (">") and characters outside
  printable ASCII is skipped, it begins with an item id (^[0-9]+(\\.[0-9]+)*), then one or more
  whitespace or ASCII punctuation characters, then an ISO date (YYYY-MM-DD). This is a row that
  has lost all its pipes, which would otherwise read as prose and drop out of the enumeration;
  the backlog interleaves rows with blank lines, prose and HTML comments, so the table structure
  alone cannot tell such a line apart. Ordinary prose, a heading, a list item and an HTML comment
  do not have that shape and pass. Residual (disclosed): a row that has lost its pipes and also
  its id or date shape, or whose first cells are led by printable ASCII such as "- " or "<!--",
  cannot be told from prose and is not caught here; the hook anti-shrinkage checkpoint covers
  only ids that an earlier enumeration listed, so an id never enumerated before has no second
  line of defence.
- The table line whose first cell is "#" is the header; its cells must equal the header above exactly,
  and only one header may appear. A row (separator or data) before the header is rejected.
- A separator row (every cell made of dashes and colons, with at least one dash) is skipped.
- Every other table line is a data row of exactly 8 cells, split on "|" not preceded by a backslash
  (a "\\|" inside a cell is a literal bar). The line must end with an unescaped "|" (trailing blanks
  and a carriage return are allowed after it).
- id: matches ^[0-9]+(\\.[0-9]+)*$ and is unique.
- state: open, closed or proposed. granted: yes or no.
- blocker: "-" or "<kind>:<ref>", split at the FIRST colon (a not-before ref contains colons). kind
  is one of tracked-task, human-decision, external, foreign-lease, not-before; ref is non-blank by
  the str.strip() test the hook applies (aiqt_hooks.py:7949), so a ref of only Unicode whitespace
  such as U+00A0 or U+2003 is rejected here, naming the line, rather than by the hook as
  ENUMERATOR_ERROR. A not-before ref must parse as an ISO-8601 time with an explicit UTC offset or
  "Z".
- evidence: "-" or "<ISO-8601 observed time with offset or Z>; <non-blank free text>". It is required
  for an external or foreign-lease blocker and must be "-" for every other row, since the hook reads
  evidence only for those two kinds (aiqt_hooks.py:8152-8166). The free text is non-blank by the
  str.strip() test the hook applies to it (aiqt_hooks.py:8165), so a description of only Unicode
  whitespace such as U+00A0 is rejected here, naming the line, rather than enumerated as evidence the
  hook then treats as absent.
- Every other strip in this script with an explicit character set (" \\t", " \\t\\r" or "\\r")
  narrows a value that is then matched exactly, parsed, or emitted with its blank test made by
  str.strip(), so a narrower blank class can only refuse a row, never accept one the hook would read
  as blank. The test suite scans the source for such strip calls and holds each to a recorded reason.
- A file with no table line at all is valid only when it carries the single column-0 line
  "<!-- aei: empty backlog -->", which affirms an empty backlog. That marker beside a table, a repeated
  marker, a header with no data row, or a data row with no header is rejected. An input with no table
  and no marker is reported at the line where the scan ended, as "line N (end of input)", N being the
  last line of the input (the empty remainder after a final newline is not counted).

The item title is the first 120 characters of the item cell, with "\\|" read as "|". Whether a blocker
actually blocks (a fresh observation, a pending decision at a row-id position, a live ledger row, a
future not-before) is judged by the hook, not here.

Usage:
    orch-enumerate-backlog.py <backlog-path>
        Print the AEI v1 enumeration on stdout; exit 0.
    orch-enumerate-backlog.py --dump-cells <backlog-path>
        Print the id, opened, item and closure cells of every data row (each cell stripped of the
        surrounding blanks, escapes kept as written) with a sha256 per row, for the migration
        loss check. This mode applies the same validation as the enumeration.
Exit 0 on success, 1 on an unreadable or malformed backlog or an unexpected error, 2 on a usage
error, 130 on a KeyboardInterrupt. A backlog that is not valid UTF-8 is reported with the line and
the byte offset of the first invalid byte. The backlog path is the only project-specific input; the
script carries no store path of its own.

The backlog must be a regular file (a symlink to one is followed). It is opened non-blocking and its
type is checked with fstat on the open descriptor, so a FIFO with no writer, a directory, a device
such as /dev/null, or any other file that is not regular exits 1 naming the path and the file type,
instead of blocking indefinitely or reading as an empty input. Every read of a path in this script
goes through that one checked helper (_read_regular), and the test suite scans the source to keep
it so.

The script runs isolated: started without -I, it re-executes itself under python3 -I before it
imports anything beyond os and sys, so a file planted beside it cannot shadow a standard-library
import (the same guard as tools/orch_doctor.py). A failed re-execution exits 1.
"""
import os
import sys

if not sys.flags.isolated:
    # Isolated mode keeps this script directory and the environment off the import path, so a file
    # written beside the script cannot shadow a standard-library module (SECI config rule).
    try:
        os.execv(sys.executable, [sys.executable, "-I", os.path.abspath(__file__)] + sys.argv[1:])
    except OSError as exc:
        print("orch-enumerate-backlog: FAIL: before line 1 (no input read): cannot re-execute "
              "under python3 -I: {}".format(exc), file=sys.stderr)
        sys.exit(1)

import hashlib
import json
import re
import stat
from datetime import datetime, timezone

PROG = "orch-enumerate-backlog"
HEADER = ("#", "Opened", "State", "Granted", "Blocker", "Evidence", "Item",
          "Closure evidence required")
NCELLS = len(HEADER)
EMPTY_MARKER = "<!-- aei: empty backlog -->"
ID_RE = re.compile(r"^[0-9]+(\.[0-9]+)*$")
SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")
# A pipe-free line with the shape of a data row's first two cells: a leading run of whitespace, ">"
# and characters outside printable ASCII (the class [^!-=?-~]), an item id, one or more whitespace or
# ASCII punctuation characters, then an ISO date.
PIPE_FREE_ROW_RE = re.compile(r"[^!-=?-~]*[0-9]+(?:\.[0-9]+)*(?:\s|[!-/:-@\[-`{-~])+"
                              r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# Mirrors _ORCH_STATES and _ORCH_BLOCKER_KINDS (aiqt_hooks.py:7549-7551).
STATES = ("open", "closed", "proposed")
GRANTED = {"yes": True, "no": False}
BLOCKER_KINDS = ("tracked-task", "human-decision", "external", "foreign-lease", "not-before")
EVIDENCE_KINDS = ("external", "foreign-lease")
TITLE_MAX = 120
# File types other than regular, named in the refusal for a backlog path that is not a regular file.
FILE_TYPES = ((stat.S_ISDIR, "directory"), (stat.S_ISCHR, "character device"),
              (stat.S_ISBLK, "block device"), (stat.S_ISFIFO, "FIFO"), (stat.S_ISSOCK, "socket"),
              (stat.S_ISLNK, "symbolic link"))
READ_CHUNK = 1 << 20
# The position of a failure that comes before any line is read: a backlog that cannot be opened or
# read, or is not a regular file, has no line to name, so the message says so and invents none.
BEFORE_INPUT = "before line 1 (input unreadable)"
# The position of a usage error, where no backlog path was accepted and nothing was read.
NOT_READ = "before line 1 (no input read)"


class BacklogError(Exception):
    """A malformed or unreadable backlog; the message begins with its position, a line of the input
    or "before line 1" with the reason no line was read."""


def _fail(msg, code=1):
    print("{}: FAIL: {}".format(PROG, msg), file=sys.stderr)
    sys.exit(code)


def _line_error(lineno, detail):
    return BacklogError("line {}: {}".format(lineno, detail))


def _input_error(detail):
    """The BacklogError for a backlog that was not read: it has no line, so the position is
    BEFORE_INPUT."""
    return BacklogError("{}: {}".format(BEFORE_INPUT, detail))


def _off_column_bar_error(line, lineno):
    """The BacklogError for a line that holds a "|" but does not begin with one, else None. One
    rule, with no list of allowed or forbidden prefix characters: any "|" off a column-0 table line
    fails closed, so a row can never be dropped as prose whatever keeps its bar off column 0. The
    message lists the characters before the first "|", each one that is not printable ASCII named
    by its code point."""
    if line.startswith("|") or "|" not in line:
        return None
    names = []
    for ch in line[:line.index("|")]:
        if ch == " ":
            name = "space"
        elif ch == "\t":
            name = "tab"
        elif ch == ">":
            name = "blockquote marker \">\""
        elif " " < ch <= "~":
            name = "text"
        else:
            name = "U+{:04X}".format(ord(ch))
        if name not in names:
            names.append(name)
    return _line_error(lineno, "a line containing \"|\" does not begin with \"|\" at column 0 "
                       "(before the first \"|\": {}); a table row must begin with \"|\" at column "
                       "0, and no \"|\" may appear outside a table row, so no row can be lost as "
                       "prose".format(", ".join(names)))


def _pipe_free_row_error(line, lineno):
    """The BacklogError for a line with no "|" that begins, after its leading run of whitespace,
    blockquote markers and non-printable-ASCII characters, with an item id and an ISO date: a data
    row that has lost all its pipes. None for every other line, so prose and comments pass."""
    if "|" in line or not PIPE_FREE_ROW_RE.match(line):
        return None
    return _line_error(lineno, "a line without \"|\" begins with an item id and an ISO date, the "
                       "first two cells of a data row that has lost its pipes; a table row must "
                       "begin with \"|\" at column 0, so this row is refused rather than lost as "
                       "prose")


def _split_cells(line, lineno):
    """Split a table line into its raw cell segments (blanks kept). The line begins with "|"."""
    body = line.rstrip(" \t\r")
    cells, current, i = [], [], 1
    terminated = False
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body) and body[i + 1] == "|":
            current.append("\\|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(current))
            current = []
            terminated = i == len(body) - 1
            i += 1
            continue
        current.append(ch)
        terminated = False
        i += 1
    if not terminated:
        raise _line_error(lineno, "table row does not end with an unescaped \"|\"")
    return cells


def _parse_utc(text):
    """An aware datetime for an ISO-8601 time that carries an explicit offset or Z, else None.
    The hook parser treats a naive time as UTC (aiqt_hooks.py:7571-7582); this is stricter, so the
    written time always states its zone."""
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        return None
    return value


def _parse_blocker(cell, lineno):
    if cell == "-":
        return None
    kind, sep, ref = cell.partition(":")
    kind, ref = kind.strip(" \t"), ref.strip(" \t")
    if not sep:
        raise _line_error(lineno, "blocker {!r} is neither \"-\" nor \"<kind>:<ref>\"".format(cell))
    if kind not in BLOCKER_KINDS:
        raise _line_error(lineno, "unknown blocker kind {!r}".format(kind))
    if not ref.strip():
        # The same str.strip() test the hook applies (aiqt_hooks.py:7949), so a ref of only Unicode
        # whitespace (U+00A0, U+2003 and the like) fails here, naming the line, never in the hook.
        raise _line_error(lineno, "blocker {} has a blank ref (empty or only whitespace)"
                          .format(kind))
    if kind == "not-before" and _parse_utc(ref) is None:
        raise _line_error(lineno, "not-before ref {!r} is not an ISO-8601 time with an offset"
                          .format(ref))
    return {"kind": kind, "ref": ref}


def _parse_evidence(cell, blocker, lineno):
    kind = blocker["kind"] if blocker else None
    if kind not in EVIDENCE_KINDS:
        if cell != "-":
            raise _line_error(lineno, "evidence must be \"-\" unless the blocker is external or "
                              "foreign-lease")
        return
    if cell == "-":
        raise _line_error(lineno, "a {} blocker requires an evidence cell".format(kind))
    when, sep, text = cell.partition(";")
    when, text = when.strip(" \t"), text.strip(" \t")
    if not sep or _parse_utc(when) is None:
        raise _line_error(lineno, "evidence {!r} does not start with an ISO-8601 observed time with "
                          "an offset, then \";\"".format(cell))
    if not text.strip():
        # The same str.strip() test the hook applies to the evidence (aiqt_hooks.py:8165), so a
        # description of only Unicode whitespace (U+00A0, U+2003 and the like) fails here, naming the
        # line, never reaching the hook as evidence it treats as absent.
        raise _line_error(lineno, "evidence has a blank description after the observed time")
    blocker["evidence"] = text
    blocker["observed_at_utc"] = when


def parse_backlog(text):
    """Parse the backlog text into (items, rows). items are AEI v1 item objects in file order; rows
    are the (id, opened, item, closure) cell tuples, stripped, escapes kept. Raises BacklogError."""
    lines = text.split("\n")
    header_line = None
    markers = []
    items, rows = [], []
    seen = {}
    table_seen = False
    for lineno, line in enumerate(lines, start=1):
        if line.rstrip("\r") == EMPTY_MARKER:
            markers.append(lineno)
            continue
        if not line.startswith("|"):
            error = _off_column_bar_error(line, lineno) or _pipe_free_row_error(line, lineno)
            if error is not None:
                raise error
            continue
        table_seen = True
        raw = _split_cells(line, lineno)
        cells = [c.strip(" \t") for c in raw]
        if cells and cells[0] == "#":
            if header_line is not None:
                raise _line_error(lineno, "second header (the header is already at line {})"
                                  .format(header_line))
            if tuple(cells) != HEADER:
                raise _line_error(lineno, "header does not match the expected header \"| {} |\""
                                  .format(" | ".join(HEADER)))
            header_line = lineno
            continue
        if header_line is None:
            raise _line_error(lineno, "table row before the header")
        if cells and all(SEPARATOR_CELL_RE.match(c) for c in cells):
            if len(cells) != NCELLS:
                raise _line_error(lineno, "separator row has {} cells, expected {}"
                                  .format(len(cells), NCELLS))
            continue
        if len(cells) != NCELLS:
            raise _line_error(lineno, "row has {} cells, expected {}".format(len(cells), NCELLS))
        iid, opened, state, granted, blocker_cell, evidence_cell, item, closure = cells
        if not ID_RE.match(iid):
            raise _line_error(lineno, "bad item id {!r}".format(iid))
        if iid in seen:
            raise _line_error(lineno, "duplicate item id {} (first at line {})".format(iid, seen[iid]))
        seen[iid] = lineno
        if state not in STATES:
            raise _line_error(lineno, "item {} has invalid state {!r}".format(iid, state))
        if granted not in GRANTED:
            raise _line_error(lineno, "item {} has invalid granted {!r} (yes or no)".format(iid, granted))
        blocker = _parse_blocker(blocker_cell, lineno)
        _parse_evidence(evidence_cell, blocker, lineno)
        title = item.replace("\\|", "|")[:TITLE_MAX]
        items.append({"id": iid, "title": title, "state": state, "granted": GRANTED[granted],
                      "blocker": blocker})
        rows.append((iid, opened, item, closure))
    if markers:
        if len(markers) > 1:
            raise _line_error(markers[1], "repeated empty-backlog marker")
        if table_seen:
            raise _line_error(markers[0], "empty-backlog marker beside a table")
        return [], []
    # The last line the scan read; the empty remainder after a final newline is not a line.
    end_line = len(lines) - 1 if len(lines) > 1 and lines[-1] == "" else len(lines)
    if not table_seen:
        raise BacklogError("line {} (end of input): no backlog table and no \"{}\" marker (an "
                           "empty backlog must be affirmed)".format(end_line, EMPTY_MARKER))
    if header_line is None:
        # Defensive: a table line before the header already fails above, so this is not reached.
        raise BacklogError("line {} (end of input): no header row".format(end_line))
    if not items:
        raise _line_error(header_line, "header with no data row")
    return items, rows


def _file_type(mode):
    """The name of the file type of an st_mode that is not a regular file."""
    for test, name in FILE_TYPES:
        if test(mode):
            return name
    return "file of unknown type (st_mode {:o})".format(stat.S_IFMT(mode))


def _read_regular(path):
    """The bytes of path, which must be a regular file; every other outcome is a BacklogError.
    The open is non-blocking, so a FIFO with no writer cannot hang the read, and the type is checked
    with fstat on the open descriptor, so the file checked is the file read. Blocking mode is then
    restored and the descriptor is read to its end. This is the only place the script opens a path."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError as exc:
        raise _input_error("cannot read backlog {}: {}".format(path, exc.strerror or exc))
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            raise _input_error("backlog {} is not a regular file (it is a {}); only a regular file "
                               "is read".format(path, _file_type(mode)))
        os.set_blocking(fd, True)
        chunks = []
        while True:
            chunk = os.read(fd, READ_CHUNK)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    except OSError as exc:
        raise _input_error("cannot read backlog {}: {}".format(path, exc.strerror or exc))
    finally:
        os.close(fd)


def read_backlog(path):
    """Read the backlog as strict UTF-8; every read failure is a BacklogError, never an empty file."""
    data = _read_regular(path)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _line_error(data.count(b"\n", 0, exc.start) + 1,
                          "backlog {} is not valid UTF-8 (byte offset {})".format(path, exc.start))


def row_digest(row):
    """The sha256 of one (id, opened, item, closure) tuple, as canonical JSON in UTF-8."""
    return hashlib.sha256(json.dumps(list(row), ensure_ascii=False).encode("utf-8")).hexdigest()


def _end_line(text):
    """The number of the last line of text, where a scan of the whole input ends; the empty
    remainder after a final newline is not a line (the count parse_backlog makes)."""
    if text.endswith("\n"):
        return max(text.count("\n"), 1)
    return text.count("\n") + 1


def _discard_stdout():
    """Close stdout before a failure. A close whose final flush fails still closes the stream, so
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
    """Fail, exit 1, for an exception that escaped the handling in _run, at the position the run
    had reached: before line 1 until the whole input was read, then the end of input."""
    _discard_stdout()
    detail = "unexpected {}: {}".format(type(exc).__name__, " ".join(str(exc).splitlines()))
    if reached["line"] is None:
        _fail("{}: {}".format(NOT_READ, detail))
    _fail("line {} (end of input): {}".format(reached["line"], detail))


def _interrupted(reached):
    """Fail, exit 130, for a KeyboardInterrupt that reached main: one line through _fail at the
    position the run had reached, as _unexpected gives it. Exit 130 (128 plus SIGINT) keeps an
    interrupted run apart from a malformed backlog (exit 1)."""
    _discard_stdout()
    detail = "interrupted (KeyboardInterrupt)"
    if reached["line"] is None:
        _fail("{}: {}".format(NOT_READ, detail), 130)
    _fail("line {} (end of input): {}".format(reached["line"], detail), 130)


def main(argv):
    """The whole run under one guard: any Exception that escapes _run, from argument handling to
    the flush of stdout, is a positioned failure, exit 1, and a KeyboardInterrupt is a positioned
    failure, exit 130, each in one line through _fail. The SystemExit of _fail is not caught."""
    reached = {"line": None}
    try:
        _run(argv, reached)
    except KeyboardInterrupt:
        _interrupted(reached)
    except Exception as exc:
        _unexpected(exc, reached)
    return 0


def _run(argv, reached):
    """Enumerate (or dump) the backlog named by argv; reached["line"] is set to the end line once
    the whole input has been read."""
    dump = False
    if argv and argv[0] == "--dump-cells":
        dump = True
        argv = argv[1:]
    if len(argv) != 1 or not argv[0] or argv[0].startswith("-"):
        _fail("{0}: usage: {1}.py <backlog-path> | {1}.py --dump-cells <backlog-path>"
              .format(NOT_READ, PROG), 2)
    path = os.path.abspath(argv[0])
    try:
        text = read_backlog(path)
        reached["line"] = _end_line(text)
        items, rows = parse_backlog(text)
    except BacklogError as exc:
        _fail(str(exc))
    if dump:
        out = {"source": path, "count": len(rows),
               "rows": [{"cells": list(r), "sha256": row_digest(r)} for r in rows]}
    else:
        out = {"version": 1,
               "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")
               .replace("+00:00", "Z"),
               "source": {"locator": path},
               "items": items}
    # ASCII-escaped JSON, so the output does not depend on the stdout encoding of the caller.
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
