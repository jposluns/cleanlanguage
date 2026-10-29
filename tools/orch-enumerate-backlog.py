#!/usr/bin/env python3
"""Enumerate the project backlog as one AEI v1 JSON object for the orchestration hooks.

The AIQT orchestration hooks run the registry `enumerator` argv on every Stop, TeammateIdle and
in-roster scheduling call (aiqt_hooks.py:7962-7989, cwd = the repo root, never through a shell) and
validate its stdout with `validate_enumeration` (aiqt_hooks.py:7904-7959). A non-zero exit, a non-JSON
stdout, or an invalid enumeration is ENUMERATOR_ERROR, which denies the Stop and the scheduling call.
This script therefore fails CLOSED: every unreadable input and every malformed row exits 1 naming the
line, and it never prints an empty or partial enumeration in place of an error (an empty backlog must
be affirmed in the file, never inferred from the absence of rows).

Backlog grammar (a markdown table, parsed strictly):

    | # | Opened | State | Granted | Blocker | Evidence | Item | Closure evidence required |

- A line is a table line only if it begins with "|" at column 0. A line whose first non-blank
  character is "|" but which is indented is rejected, so an indented row can never be skipped silently.
- The table line whose first cell is "#" is the header; its cells must equal the header above exactly,
  and only one header may appear. A row (separator or data) before the header is rejected.
- A separator row (every cell made of dashes and colons, with at least one dash) is skipped.
- Every other table line is a data row of exactly 8 cells, split on "|" not preceded by a backslash
  (a "\\|" inside a cell is a literal bar). The line must end with an unescaped "|" (trailing blanks
  and a carriage return are allowed after it).
- id: matches ^[0-9]+(\\.[0-9]+)*$ and is unique.
- state: open, closed or proposed. granted: yes or no.
- blocker: "-" or "<kind>:<ref>", split at the FIRST colon (a not-before ref contains colons). kind
  is one of tracked-task, human-decision, external, foreign-lease, not-before; ref is non-blank. A
  not-before ref must parse as an ISO-8601 time with an explicit UTC offset or "Z".
- evidence: "-" or "<ISO-8601 observed time with offset or Z>; <non-blank free text>". It is required
  for an external or foreign-lease blocker and must be "-" for every other row, since the hook reads
  evidence only for those two kinds (aiqt_hooks.py:8152-8166).
- A file with no table line at all is valid only when it carries the single column-0 line
  "<!-- aei: empty backlog -->", which affirms an empty backlog. That marker beside a table, a repeated
  marker, a header with no data row, or a data row with no header is rejected.

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
Exit 0 on success, 1 on an unreadable or malformed backlog, 2 on a usage error. The backlog path is
the only project-specific input; the script carries no store path of its own.
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

PROG = "orch-enumerate-backlog"
HEADER = ("#", "Opened", "State", "Granted", "Blocker", "Evidence", "Item",
          "Closure evidence required")
NCELLS = len(HEADER)
EMPTY_MARKER = "<!-- aei: empty backlog -->"
ID_RE = re.compile(r"^[0-9]+(\.[0-9]+)*$")
SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")
# Mirrors _ORCH_STATES and _ORCH_BLOCKER_KINDS (aiqt_hooks.py:7549-7551).
STATES = ("open", "closed", "proposed")
GRANTED = {"yes": True, "no": False}
BLOCKER_KINDS = ("tracked-task", "human-decision", "external", "foreign-lease", "not-before")
EVIDENCE_KINDS = ("external", "foreign-lease")
TITLE_MAX = 120


class BacklogError(Exception):
    """A malformed or unreadable backlog; the message names the line where one applies."""


def _fail(msg, code=1):
    print("{}: FAIL: {}".format(PROG, msg), file=sys.stderr)
    sys.exit(code)


def _line_error(lineno, detail):
    return BacklogError("line {}: {}".format(lineno, detail))


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
    if not ref:
        raise _line_error(lineno, "blocker {} has a blank ref".format(kind))
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
    if not text:
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
            if line.lstrip(" \t").startswith("|"):
                raise _line_error(lineno, "indented table line (a table row must begin at column 0)")
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
    if not table_seen:
        raise BacklogError("no backlog table and no \"{}\" marker (an empty backlog must be "
                           "affirmed)".format(EMPTY_MARKER))
    if header_line is None:
        raise BacklogError("no header row")
    if not items:
        raise _line_error(header_line, "header with no data row")
    return items, rows


def read_backlog(path):
    """Read the backlog as strict UTF-8; every read failure is a BacklogError, never an empty file."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise BacklogError("cannot read backlog {}: {}".format(path, exc.strerror or exc))
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BacklogError("backlog {} is not valid UTF-8 (byte offset {})".format(path, exc.start))


def row_digest(row):
    """The sha256 of one (id, opened, item, closure) tuple, as canonical JSON in UTF-8."""
    return hashlib.sha256(json.dumps(list(row), ensure_ascii=False).encode("utf-8")).hexdigest()


def main(argv):
    dump = False
    if argv and argv[0] == "--dump-cells":
        dump = True
        argv = argv[1:]
    if len(argv) != 1 or not argv[0] or argv[0].startswith("-"):
        _fail("usage: {0}.py <backlog-path> | {0}.py --dump-cells <backlog-path>".format(PROG), 2)
    path = os.path.abspath(argv[0])
    try:
        items, rows = parse_backlog(read_backlog(path))
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
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
