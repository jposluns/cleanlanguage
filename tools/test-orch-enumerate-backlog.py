#!/usr/bin/env python3
"""Tests for tools/orch-enumerate-backlog.py (item 28.2 stage 2, PR1-d).

The enumerator is the registry `enumerator` the orchestration hooks run on every Stop and in-roster
scheduling call (aiqt_hooks.py:7962-7989). These tests drive the script as a subprocess under
python3 -I against synthetic fixtures only, and validate every successful enumeration with the hook
function `validate_enumeration` (aiqt_hooks.py:7904-7959), imported from the vendored hook by path in
a separate python3 -I process, so the contract under test is the one the hook enforces, not a copy of
it. One test also runs the enumerator through the hook function `_orch_enumerate` with a relative
script path and cwd = the repo root, as the registry declares it.

Fail-closed cases assert exit 1, an empty stdout, and a stderr that names the offending line, since a
non-zero exit is ENUMERATOR_ERROR in the hook (aiqt_hooks.py:7979-7981) and an empty enumeration
would read as a drained backlog. The real backlog is never read.

A missing required input (the enumerator or the vendored hook) fails the test rather than skipping
it, so an absent file can never read as a green run. The HiddenTablePrefix cases prove that a row
whose "|" is kept off column 0 by an invisible, combining, filler, no-break or blockquote prefix
fails closed rather than vanishing as prose (findings F1 and G1), that a GFM row with no leading
pipe and a prose line with a mid-line pipe fail closed too (G1: one rule, any "|" off a column-0
table line), and the class probe runs that rule over every code point of the Basic Multilingual
Plane. The Isolation case proves the script re-executes itself under python3 -I (finding F7).

The PipeFreeRow cases prove that a row which has lost all its pipes, a line with no "|" that opens
with an item id and an ISO date (after any leading whitespace, blockquote marker or character outside
printable ASCII), fails closed naming the line rather than vanishing as prose, while ordinary prose,
a plain lazy continuation line and an HTML comment pass, and that the two-parser loss check refuses
both dumps (finding R2). The BlockerProperty cases prove that a ref of only Unicode whitespace fails
closed naming the line, and that every exit-0 enumeration over a grid of blocker kinds and edge refs
and evidence values passes the vendored validate_enumeration (finding R5). An invalid UTF-8 input is
reported with its line as well as its byte offset (finding R7).

The InputFileType cases prove that a backlog path that is not a regular file, a FIFO with no writer,
a symlink to one, a directory, or /dev/null, exits 1 promptly naming the path and the file type
rather than blocking indefinitely or reading as an empty input, while a regular file, a symlink to
one, and a file larger than one read chunk still enumerate (finding S3). Each run is bounded by a
subprocess timeout, so a blocking open fails the test instead of hanging the suite. The SourceProbe
case is the class probe for that finding: it scans the enumerator source for every reference to an
opener (open, fdopen, read_text, read_bytes, write_text, write_bytes, called, aliased or imported)
and requires exactly one, the os.open inside the checked helper, so a new unchecked open fails the
suite. The EndOfInput cases prove that an input with no backlog table is reported at the line where
the scan ended (finding S4). The EvidenceBlankness cases prove that an evidence description of only
Unicode whitespace, such as U+00A0, fails closed naming the line, since the vendored
validate_enumeration accepts such evidence and the hook classification then treats it as absent
(aiqt_hooks.py:8165), while a real description enumerates and classifies blocked (round 6 U3). The
StripProbe case is the class probe for that finding: it scans the enumerator source for every strip,
lstrip or rstrip call with an explicit character set and requires each to be in a recorded allowlist
with its reason, and requires each emitted value among them to carry the bare str.strip() blank test
the hook applies, so a new narrower blank test fails the suite.

The ErrorPosition cases prove that every failure the enumerator can produce begins with its position
(round 9 X1): a line of the input, the line where the scan ended, or "before line 1" with the reason
no line was read, for a missing, unreadable, FIFO, directory, device and invalid UTF-8 input, a
malformed table, a usage error and a failed re-execution, in both modes. The PositionProbe case is
the class probe for that finding: it scans the enumerator source for every BacklogError construction
and every _fail call and requires each message to begin with a position, so a new failure that names
none fails the suite.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SCRIPT = HERE / "orch-enumerate-backlog.py"
MIGRATE = HERE / "migrate-todo-aei.py"
HOOK = REPO_ROOT / "plugin" / "aiqt-guardrails-hooks" / "hooks" / "scripts" / "aiqt_hooks.py"

HEADER = "| # | Opened | State | Granted | Blocker | Evidence | Item | Closure evidence required |"
SEPARATOR = "|---|---|---|---|---|---|---|---|"

# Runs in a separate python3 -I process: import the vendored hook by path and validate the JSON on
# stdin, printing {"items": ..., "error": ...}.
VALIDATE_PROG = """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("aiqt_hooks_under_test", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
items, err = mod.validate_enumeration(json.loads(sys.stdin.read()))
print(json.dumps({"items": items, "error": err}))
"""

# Runs the enumerator through the hook function _orch_enumerate exactly as the registry declares it.
ENUMERATE_PROG = """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("aiqt_hooks_under_test", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
reg = {"enumerator": {"argv": json.loads(sys.argv[3]), "timeout": 5}}
status, detail = mod._orch_enumerate(reg, sys.argv[2])
print(json.dumps({"status": status, "detail": detail}))
"""


# Prefixes that keep a "|" off column 0 while it stays the first visible character (findings F1 and
# G1). The G1 entries are outside the classes the F1 fix enumerated: U+034F and U+FE0F are category
# Mn, and U+3164 and U+FFA0 are blank fillers of category Lo.
HIDDEN_PREFIXES = [
    ("combining grapheme joiner U+034F", "\u034f"),
    ("variation selector-16 U+FE0F", "\ufe0f"),
    ("hangul filler U+3164", "\u3164"),
    ("halfwidth hangul filler U+FFA0", "\uffa0"),
    ("no-break space U+00A0", "\u00a0"),
    ("zero-width space U+200B", "\u200b"),
    ("byte order mark U+FEFF", "\ufeff"),
    ("ideographic space U+3000", "\u3000"),
    ("word joiner U+2060", "\u2060"),
    ("left-to-right mark U+200E", "\u200e"),
    ("blockquote marker and space", "> "),
    ("bare blockquote marker", ">"),
    ("nested blockquote", "> > "),
    ("space then no-break space", " \u00a0"),
    ("tab then blockquote", "\t> "),
    ("blockquote then zero-width space", ">\u200b"),
]


# Runs in a separate python3 -I process: load the enumerator by path and call parse_backlog on the
# fixture text (argv[2]) once per code point from U+0000 to U+FFFF, the code point prepended to the
# data row at line 8. Surrogates (not encodable in a file), "|" itself, and "\n" (the line
# terminator, which ends line 8 rather than prefixing it) are excluded. Prints the code points that
# did NOT fail closed with the column-0 error at line 8, and the count probed.
CLASS_PROBE_PROG = """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("enumerator_under_test", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
head, data_row, tail = json.loads(sys.argv[2])
escaped, probed = [], 0
for cp in range(0x10000):
    if 0xD800 <= cp <= 0xDFFF or cp in (0x0A, 0x7C):
        continue
    probed += 1
    try:
        mod.parse_backlog(head + chr(cp) + data_row + tail)
    except mod.BacklogError as exc:
        if str(exc).startswith("line 8: ") and "does not begin with" in str(exc):
            continue
    escaped.append("U+%04X" % cp)
print(json.dumps({"probed": probed, "escaped": escaped}))
"""


# Runs in a separate python3 -I -B process with bytecode writing off: load the enumerator and the
# vendored hook by path, then for each (name, backlog text) case in the JSON file argv[3] write the
# text to argv[4], run the enumerator main on it with stdout and stderr captured, and pass every
# exit-0 stdout through the hook validate_enumeration. Prints one result per case.
PROPERTY_PROG = """
import contextlib, importlib.util, io, json, sys
sys.dont_write_bytecode = True

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

enum = load("enumerator_under_test", sys.argv[1])
hook = load("aiqt_hooks_under_test", sys.argv[2])
with open(sys.argv[3], encoding="utf-8") as fh:
    cases = json.load(fh)
results = []
for name, text in cases:
    with open(sys.argv[4], "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = enum.main([sys.argv[4]])
        except SystemExit as exc:
            code = exc.code
    verdict = None
    if code == 0:
        items, error = hook.validate_enumeration(json.loads(out.getvalue()))
        verdict = error
    results.append({"name": name, "code": code, "stdout": out.getvalue(), "stderr": err.getvalue(),
                    "hook_error": verdict})
print(json.dumps(results))
"""

# Refs at the edge of blankness: str.strip() (the hook test, aiqt_hooks.py:7949) removes every one
# of the Unicode whitespace characters below, while U+200B is not whitespace and is a real ref.
UNICODE_BLANK_REFS = ["\u00a0", "\u2003", "\u3000", "\u2028", "\x85", "\x0b", "\x0c", "\x1c",
                      "\x1f", "\r", "\u00a0\u2003", " \u00a0\t"]
EDGE_REFS = (["PD-7", "x", " x ", "a:b:c", "\u200b", "\u00a0x\u00a0", "", " ", "\t", "-",
              "2099-01-01T00:00:00Z", "2099-01-01T00:00:00+05:30", " 2099-01-01T00:00:00Z ",
              "\u00a02099-01-01T00:00:00Z", "2099-01-01T00:00:00Z\u2003", "2099-01-01T00:00:00"]
             + UNICODE_BLANK_REFS)
EDGE_EVIDENCE = ["-", "2026-10-29T12:00:00Z; seen upstream", "2026-10-29T12:00:00Z;\u00a0",
                 "2026-10-29T12:00:00Z; \u2003note", "\u00a0; text", "2026-10-29T12:00:00Z"]
BLOCKER_KINDS = ("tracked-task", "human-decision", "external", "foreign-lease", "not-before")


# Runs in a separate python3 -I process: import the vendored hook by path and, for each evidence
# string in the JSON list argv[2], pass one external-blocker item through validate_enumeration and then
# classify_backlog (aiqt_hooks.py:7904-7959 and 8101-8177), printing the validation error and the
# blocked and actionable rows per case.
HOOK_EVIDENCE_PROG = """
import importlib.util, json, sys
from datetime import datetime, timezone
spec = importlib.util.spec_from_file_location("aiqt_hooks_under_test", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
now = datetime.now(timezone.utc).isoformat()
out = []
for ev in json.loads(sys.argv[2]):
    payload = {"version": 1, "generated_at_utc": now, "source": {"locator": "fixture"},
               "items": [{"id": "1", "title": "An item", "state": "open", "granted": True,
                          "blocker": {"kind": "external", "ref": "x", "evidence": ev,
                                      "observed_at_utc": now}}]}
    items, err = mod.validate_enumeration(payload)
    classes = mod.classify_backlog(items or [], set(), True, "", {})
    out.append({"error": err, "blocked": [list(b) for b in classes["blocked"]],
                "actionable": [list(a) for a in classes["actionable"]]})
print(json.dumps(out))
"""


def row(iid, state="open", granted="yes", blocker="-", evidence="-", item="An item",
        closure="Merged PR", opened="2026-10-01"):
    return "| {} | {} | {} | {} | {} | {} | {} | {} |".format(
        iid, opened, state, granted, blocker, evidence, item, closure)


def table(*rows, prose_before=("# Backlog", "", "Item numbers are permanent and never reused.", ""),
          prose_after=("", "Trailing note.")):
    return "\n".join(list(prose_before) + [HEADER, SEPARATOR] + list(rows) + list(prose_after)) + "\n"


class EnumeratorHarness(unittest.TestCase):

    def setUp(self):
        if not SCRIPT.exists():
            self.fail("enumerator not found: {}".format(SCRIPT))
        self._tmp = Path(tempfile.mkdtemp(prefix="orch-enum-"))

    def tearDown(self):
        for dirpath, _dirs, files in os.walk(self._tmp):
            for name in files:
                try:
                    os.chmod(os.path.join(dirpath, name), 0o600)
                except OSError:
                    pass
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write(self, text, name="TODO.md"):
        path = self._tmp / name
        if isinstance(text, bytes):
            path.write_bytes(text)
        else:
            path.write_text(text, encoding="utf-8")
        return path

    def run_enum(self, *args):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *[str(a) for a in args]],
                              capture_output=True, text=True)

    def enumerate_ok(self, text):
        r = self.run_enum(self.write(text))
        self.assertEqual(r.returncode, 0, "enumerator failed: {}".format(r.stderr))
        return json.loads(r.stdout)

    def hook_validate(self, stdout_text):
        if not HOOK.exists():
            self.fail("vendored hook not found: {}".format(HOOK))
        r = subprocess.run([sys.executable, "-I", "-c", VALIDATE_PROG, str(HOOK)],
                           input=stdout_text, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, "hook validation process failed: {}".format(r.stderr))
        return json.loads(r.stdout)

    def assert_fails(self, text_or_path, line=None, needle=None):
        path = text_or_path if isinstance(text_or_path, Path) else self.write(text_or_path)
        r = self.run_enum(path)
        self.assertEqual(r.returncode, 1, "expected exit 1, got {}: {}".format(r.returncode, r.stderr))
        self.assertEqual(r.stdout, "", "a failing enumerator prints no enumeration")
        if line is not None:
            self.assertIn("line {}:".format(line), r.stderr)
        if needle is not None:
            self.assertIn(needle, r.stderr)
        return r


class Golden(EnumeratorHarness):
    """An 8-column fixture enumerates to the expected items, and the hook accepts the output."""

    FUTURE = "2099-01-01T00:00:00Z"
    OBSERVED = "2026-10-29T12:00:00Z"

    def fixture(self):
        return table(
            row("1", item="Open granted item with no blocker"),
            row("2", state="closed", item="Closed item"),
            row("3", state="proposed", granted="no", item="Proposed item"),
            row("4", granted="no", item="Open but not granted"),
            row("5", blocker="human-decision:PD-7", item="Waits on a decision"),
            row("6", blocker="not-before:" + self.FUTURE, item="Deferred"),
            row("7", blocker="external:upstream-pack-release",
                evidence=self.OBSERVED + "; pack release not yet tagged", item="Upstream"),
            row("8.1", blocker="foreign-lease:lab_infra",
                evidence=self.OBSERVED + "; lab_infra holds the host lease", item="Foreign lease"),
            row("9", blocker="tracked-task:task-abc", item="Waits on a task"),
            row("10", item="Pipe \\| inside the item", closure="Check \\| passes"),
        )

    def expected_items(self):
        return [
            {"id": "1", "title": "Open granted item with no blocker", "state": "open",
             "granted": True, "blocker": None},
            {"id": "2", "title": "Closed item", "state": "closed", "granted": True, "blocker": None},
            {"id": "3", "title": "Proposed item", "state": "proposed", "granted": False,
             "blocker": None},
            {"id": "4", "title": "Open but not granted", "state": "open", "granted": False,
             "blocker": None},
            {"id": "5", "title": "Waits on a decision", "state": "open", "granted": True,
             "blocker": {"kind": "human-decision", "ref": "PD-7"}},
            {"id": "6", "title": "Deferred", "state": "open", "granted": True,
             "blocker": {"kind": "not-before", "ref": self.FUTURE}},
            {"id": "7", "title": "Upstream", "state": "open", "granted": True,
             "blocker": {"kind": "external", "ref": "upstream-pack-release",
                         "evidence": "pack release not yet tagged",
                         "observed_at_utc": self.OBSERVED}},
            {"id": "8.1", "title": "Foreign lease", "state": "open", "granted": True,
             "blocker": {"kind": "foreign-lease", "ref": "lab_infra",
                         "evidence": "lab_infra holds the host lease",
                         "observed_at_utc": self.OBSERVED}},
            {"id": "9", "title": "Waits on a task", "state": "open", "granted": True,
             "blocker": {"kind": "tracked-task", "ref": "task-abc"}},
            {"id": "10", "title": "Pipe | inside the item", "state": "open", "granted": True,
             "blocker": None},
        ]

    def test_golden_items(self):
        out = self.enumerate_ok(self.fixture())
        self.assertEqual(out["version"], 1)
        self.assertIs(type(out["version"]), int)
        self.assertEqual(out["items"], self.expected_items())

    def test_hook_validate_enumeration_accepts_output(self):
        r = self.run_enum(self.write(self.fixture()))
        self.assertEqual(r.returncode, 0, r.stderr)
        verdict = self.hook_validate(r.stdout)
        self.assertIsNone(verdict["error"], "the hook rejected the enumeration: {}"
                          .format(verdict["error"]))
        self.assertEqual(verdict["items"], self.expected_items())

    def test_hook_rejects_a_corrupted_output(self):
        # Proves the validation step is live: the same output with an invalid state is refused.
        out = self.enumerate_ok(self.fixture())
        out["items"][0]["state"] = "done"
        verdict = self.hook_validate(json.dumps(out))
        self.assertIsNone(verdict["items"])
        self.assertIn("invalid state", verdict["error"])

    def test_source_locator_is_the_absolute_backlog_path(self):
        path = self.write(self.fixture())
        rel = os.path.relpath(path, os.getcwd())
        r = self.run_enum(rel)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["source"], {"locator": str(path)})

    def test_generated_at_utc_is_within_five_seconds_of_the_test_clock(self):
        before = datetime.now(timezone.utc)
        out = self.enumerate_ok(self.fixture())
        after = datetime.now(timezone.utc)
        gen = datetime.fromisoformat(out["generated_at_utc"].replace("Z", "+00:00"))
        self.assertIsNotNone(gen.tzinfo)
        self.assertLessEqual(abs((gen - before).total_seconds()), 5)
        self.assertLessEqual(abs((after - gen).total_seconds()), 5)

    def test_hook_runs_the_enumerator_from_the_repo_root(self):
        if not HOOK.exists():
            self.fail("vendored hook not found: {}".format(HOOK))
        path = self.write(self.fixture())
        argv = [sys.executable, "-I", "tools/orch-enumerate-backlog.py", str(path)]
        r = subprocess.run([sys.executable, "-I", "-c", ENUMERATE_PROG, str(HOOK), str(REPO_ROOT),
                            json.dumps(argv)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json.loads(r.stdout)
        self.assertEqual(res["status"], "ok", res["detail"])
        self.assertEqual([it["id"] for it in res["detail"]], [it["id"] for it in self.expected_items()])

    def test_hook_reports_enumerator_error_on_a_malformed_backlog(self):
        if not HOOK.exists():
            self.fail("vendored hook not found: {}".format(HOOK))
        path = self.write(table(row("1", state="done")))
        argv = [sys.executable, "-I", "tools/orch-enumerate-backlog.py", str(path)]
        r = subprocess.run([sys.executable, "-I", "-c", ENUMERATE_PROG, str(HOOK), str(REPO_ROOT),
                            json.dumps(argv)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json.loads(r.stdout)
        self.assertEqual(res["status"], "ENUMERATOR_ERROR")
        self.assertIn("line 7:", res["detail"])


class Cells(EnumeratorHarness):
    """Cell-level parsing: escaped bars, colon-bearing refs, titles, padding, line endings."""

    def test_escaped_bar_survives_in_title_and_cell_dump(self):
        out = self.enumerate_ok(table(row("1", item="a \\| b", closure="c \\| d")))
        self.assertEqual(out["items"][0]["title"], "a | b")
        r = self.run_enum("--dump-cells", self.write(table(row("1", item="a \\| b",
                                                               closure="c \\| d"))))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["rows"][0]["cells"], ["1", "2026-10-01", "a \\| b",
                                                                   "c \\| d"])

    def test_not_before_ref_with_colons_parses(self):
        ref = "2099-06-30T23:59:58+00:00"
        out = self.enumerate_ok(table(row("1", blocker="not-before:" + ref)))
        self.assertEqual(out["items"][0]["blocker"], {"kind": "not-before", "ref": ref})

    def test_title_is_the_first_120_characters(self):
        item = "x" * 150
        out = self.enumerate_ok(table(row("1", item=item)))
        self.assertEqual(out["items"][0]["title"], "x" * 120)

    def test_padding_and_crlf_are_tolerated(self):
        text = (HEADER + "\r\n" + SEPARATOR + "\r\n"
                + "|  1  | 2026-10-01 |open|yes|-|-|  Item one  | Done |  \r\n")
        out = self.enumerate_ok(text)
        self.assertEqual(out["items"][0]["id"], "1")
        self.assertEqual(out["items"][0]["title"], "Item one")

    def test_dump_cells_prints_the_four_original_cells_per_row(self):
        text = table(row("1", item="First", closure="C1", opened="2026-09-01"),
                     row("2", state="closed", blocker="human-decision:PD-1", item="Second",
                         closure="C2", opened="2026-09-02"))
        r = self.run_enum("--dump-cells", self.write(text))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["count"], 2)
        self.assertEqual([x["cells"] for x in out["rows"]],
                         [["1", "2026-09-01", "First", "C1"], ["2", "2026-09-02", "Second", "C2"]])
        for x in out["rows"]:
            self.assertRegex(x["sha256"], r"^[0-9a-f]{64}$")

    def test_dump_cells_fails_closed_like_the_enumeration(self):
        r = self.run_enum("--dump-cells", self.write(table(row("1", state="done"))))
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, "")
        self.assertIn("line 7:", r.stderr)

    def test_empty_backlog_marker_affirms_an_empty_enumeration(self):
        r = self.run_enum(self.write("# Backlog\n\n<!-- aei: empty backlog -->\n"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["items"], [])
        verdict = self.hook_validate(r.stdout)
        self.assertIsNone(verdict["error"])
        self.assertEqual(verdict["items"], [])


class FailClosed(EnumeratorHarness):
    """Every unreadable input and malformed row exits 1, naming the line where one applies.

    In the table() fixture the header is line 5, the separator line 6, and the first row line 7.
    """

    def test_missing_file(self):
        self.assert_fails(self._tmp / "absent.md", needle="cannot read backlog")

    def test_directory_operand(self):
        self.assert_fails(self._tmp, needle="is not a regular file (it is a directory)")

    def test_unreadable_file(self):
        if os.geteuid() == 0:
            self.skipTest("root reads a mode-000 file")
        path = self.write(table(row("1")))
        os.chmod(path, 0)
        self.assert_fails(path, needle="cannot read backlog")

    def test_invalid_utf8(self):
        self.assert_fails(self.write(table(row("1")).encode("utf-8") + b"\xff\xfe\n"),
                          needle="not valid UTF-8")

    def test_invalid_utf8_names_the_line(self):
        # Finding R7: the report names the line of the first invalid byte, not only its offset.
        text = table(row("1")).encode("utf-8")
        line = text.count(b"\n") + 1
        r = self.assert_fails(self.write(text + b"bad \xff byte\n"), line=line,
                              needle="not valid UTF-8 (byte offset {})".format(len(text) + 4))
        r = self.assert_fails(self.write(b"# Backlog\n\nbad \xc3 here\n" + text), line=3,
                              needle="not valid UTF-8 (byte offset 15)")

    def test_missing_header(self):
        self.assert_fails("# Backlog\n\n" + row("1") + "\n", line=3, needle="before the header")

    def test_no_header_with_only_a_separator(self):
        self.assert_fails(SEPARATOR + "\n", line=1, needle="before the header")

    def test_wrong_header_old_four_column_shape(self):
        old = "| # | Opened | Item | Closure evidence required |"
        self.assert_fails("x\n" + old + "\n|---|---|---|---|\n| 1 | d | i | c |\n", line=2,
                          needle="header does not match")

    def test_second_header(self):
        self.assert_fails(table(row("1"), HEADER), line=8, needle="second header")

    def test_header_with_no_data_row(self):
        self.assert_fails(table(), line=5, needle="no data row")

    def test_wrong_cell_count(self):
        self.assert_fails(table("| 1 | 2026-10-01 | open | yes | - | Item | Done |"), line=7,
                          needle="7 cells, expected 8")

    def test_separator_wrong_cell_count(self):
        text = "\n".join([HEADER, "|---|---|", row("1")]) + "\n"
        self.assert_fails(text, line=2, needle="separator row")

    def test_unterminated_row(self):
        self.assert_fails(table(row("1")[:-1]), line=7, needle="does not end")

    def test_row_ending_in_an_escaped_bar(self):
        self.assert_fails(table(row("1")[:-1] + "\\|"), line=7, needle="does not end")

    def test_indented_row(self):
        self.assert_fails(table("  " + row("1")), line=7, needle="does not begin with")

    def test_bad_state(self):
        self.assert_fails(table(row("1", state="done")), line=7, needle="invalid state")

    def test_bad_granted(self):
        self.assert_fails(table(row("1", granted="true")), line=7, needle="invalid granted")

    def test_unknown_blocker_kind(self):
        self.assert_fails(table(row("1", blocker="waiting:PD-1")), line=7,
                          needle="unknown blocker kind")

    def test_blocker_without_colon(self):
        self.assert_fails(table(row("1", blocker="human-decision")), line=7, needle="blocker")

    def test_blank_ref(self):
        self.assert_fails(table(row("1", blocker="human-decision:  ")), line=7, needle="blank ref")

    def test_blank_ref_of_only_unicode_whitespace(self):
        # Finding R5: the hook rejects a ref whose str.strip() is empty (aiqt_hooks.py:7949), so the
        # enumerator fails closed on it naming the line rather than exit 0 into ENUMERATOR_ERROR.
        for kind in BLOCKER_KINDS:
            for ref in UNICODE_BLANK_REFS:
                with self.subTest(kind=kind, ref="".join("U+%04X" % ord(c) for c in ref)):
                    self.assert_fails(table(row("1", blocker=kind + ":" + ref)), line=7,
                                      needle="blank ref")

    def test_unparseable_not_before(self):
        self.assert_fails(table(row("1", blocker="not-before:next week")), line=7,
                          needle="not-before ref")

    def test_not_before_without_offset(self):
        self.assert_fails(table(row("1", blocker="not-before:2099-01-01T00:00:00")), line=7,
                          needle="not-before ref")

    def test_duplicate_id(self):
        self.assert_fails(table(row("1"), row("2"), row("1")), line=9, needle="duplicate item id 1")

    def test_bad_id(self):
        self.assert_fails(table(row("CL-1")), line=7, needle="bad item id")

    def test_bad_id_trailing_dot(self):
        self.assert_fails(table(row("1.")), line=7, needle="bad item id")

    def test_external_evidence_without_parseable_time(self):
        self.assert_fails(table(row("1", blocker="external:x", evidence="yesterday; seen upstream")),
                          line=7, needle="observed time")

    def test_external_evidence_without_separator(self):
        self.assert_fails(table(row("1", blocker="external:x", evidence="2026-10-29T12:00:00Z")),
                          line=7, needle="observed time")

    def test_external_evidence_blank_description(self):
        self.assert_fails(table(row("1", blocker="external:x", evidence="2026-10-29T12:00:00Z;  ")),
                          line=7, needle="blank description")

    def test_external_without_evidence(self):
        self.assert_fails(table(row("1", blocker="foreign-lease:x")), line=7,
                          needle="requires an evidence cell")

    def test_evidence_on_a_non_evidence_row(self):
        self.assert_fails(table(row("1", evidence="2026-10-29T12:00:00Z; note")), line=7,
                          needle="evidence must be")

    def test_non_table_file_without_the_empty_marker(self):
        self.assert_fails("# Backlog\n\nNothing here.\n", needle="an empty backlog must be affirmed")

    def test_empty_file(self):
        self.assert_fails("", needle="an empty backlog must be affirmed")

    def test_empty_marker_beside_a_table(self):
        self.assert_fails("<!-- aei: empty backlog -->\n" + table(row("1")), line=1,
                          needle="marker beside a table")

    def test_repeated_empty_marker(self):
        self.assert_fails("<!-- aei: empty backlog -->\n<!-- aei: empty backlog -->\n", line=2,
                          needle="repeated empty-backlog marker")

    def test_usage_errors_exit_2(self):
        for args in ([], ["a", "b"], ["--dump-cells"], ["--other", "x"]):
            r = self.run_enum(*args)
            self.assertEqual(r.returncode, 2, "args {!r}: {}".format(args, r.stderr))
            self.assertEqual(r.stdout, "")


class HiddenTablePrefix(EnumeratorHarness):
    """A "|" kept off column 0 by an invisible, no-break or blockquote prefix fails closed (F1).

    Before the fix such a row read as prose: the enumeration exited 0 without the item. In the
    table() fixture the header is line 5 and the rows start at line 7.
    """

    def test_prefixed_data_row_fails_closed(self):
        for name, prefix in HIDDEN_PREFIXES:
            with self.subTest(prefix=name):
                self.assert_fails(table(row("1"), prefix + row("2"), row("3")), line=8,
                                  needle="does not begin with")

    def test_prefixed_data_row_fails_the_cell_dump(self):
        for name, prefix in HIDDEN_PREFIXES:
            with self.subTest(prefix=name):
                r = self.run_enum("--dump-cells",
                                  self.write(table(row("1"), prefix + row("2"))))
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertEqual(r.stdout, "")
                self.assertIn("line 8:", r.stderr)

    def test_prefixed_header_fails_closed(self):
        for name, prefix in HIDDEN_PREFIXES:
            with self.subTest(prefix=name):
                text = table(row("1")).replace(HEADER, prefix + HEADER, 1)
                self.assert_fails(text, line=5, needle="does not begin with")

    def test_byte_order_mark_before_a_first_line_header(self):
        text = "\ufeff" + HEADER + "\n" + SEPARATOR + "\n" + row("1") + "\n"
        self.assert_fails(text, line=1, needle="U+FEFF")

    def test_message_names_the_prefix_characters(self):
        r = self.assert_fails(table("\u00a0\u200b> " + row("1")), line=7)
        for name in ("U+00A0", "U+200B", "blockquote marker", "space"):
            self.assertIn(name, r.stderr)

    def test_message_names_the_g1_prefix_characters_by_code_point(self):
        for name, prefix in HIDDEN_PREFIXES[:4]:
            with self.subTest(prefix=name):
                r = self.assert_fails(table(row("1"), prefix + row("2")), line=8)
                self.assertIn("U+{:04X}".format(ord(prefix)), r.stderr)

    def test_gfm_row_without_a_leading_pipe_mid_table_fails_closed(self):
        # GFM accepts a row with no leading pipe, so a renderer shows it as a row of the table;
        # before G1 the enumerator read it as prose and dropped item 2 silently.
        self.assert_fails(table(row("1"), row("2")[1:].lstrip(), row("3")), line=8,
                          needle="does not begin with")
        self.assert_fails(table(row("1"), "2 | 2026-10-01 | open | yes | - | - | Item | Done |",
                                row("3")), line=8, needle="does not begin with")

    def test_prose_with_a_mid_line_bar_fails_closed(self):
        # Replaces the F1-era test that prose with a "|" after other text passes: under G1 any "|"
        # outside a column-0 table line fails closed, because a rule that lets some prefixed bars
        # through has to enumerate which, and any prefix outside the list hides a row. The backlog
        # format keeps every "|" inside a table line, so this costs nothing on a valid backlog.
        prose = ("Prose with a | bar mid-line.", "> A quoted line with a | bar.",
                 "\u00a0No-break led prose | with a bar.", "\u200b> quoted | text")
        for line in prose:
            with self.subTest(line=line):
                self.assert_fails(table(row("1"), prose_before=("# Backlog", "", line, "")),
                                  line=3, needle="does not begin with")
                self.assert_fails(table(row("1"), prose_after=("", line)), line=9,
                                  needle="does not begin with")

    def test_prose_without_a_bar_is_still_prose(self):
        prose = ("\ufeffTitle line", "> ", "\u00a0", "> A quoted line without a bar.",
                 "\u3164Filler-led prose.")
        text = table(row("1"), prose_before=("# Backlog", "") + prose + ("",),
                     prose_after=("",) + prose)
        out = self.enumerate_ok(text)
        self.assertEqual([it["id"] for it in out["items"]], ["1"])

    def test_class_probe_every_bmp_code_point_before_a_row_fails_closed(self):
        lines = table(row("1"), "\x00", row("10")).split("\n")
        self.assertEqual(lines[7], "\x00", "precondition: the probed row is line 8")
        head = "\n".join(lines[:7]) + "\n"
        tail = "\n" + "\n".join(lines[8:])
        r = subprocess.run([sys.executable, "-I", "-c", CLASS_PROBE_PROG, str(SCRIPT),
                            json.dumps([head, row("9"), tail])],
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json.loads(r.stdout)
        self.assertEqual(res["probed"], 0x10000 - 0x800 - 2)
        self.assertEqual(res["escaped"], [], "code points whose prefixed row did not fail closed")
        # The CLI path agrees with the in-process function on a sample of the probed code points.
        for cp in (0x00, 0x09, 0x20, 0x3E, 0x41, 0xA0, 0x34F, 0x200B, 0x3164, 0xFE0F, 0xFEFF, 0xFFA0,
                   0xFFFF):
            with self.subTest(cp="U+%04X" % cp):
                self.assert_fails(head + chr(cp) + row("9") + tail, line=8,
                                  needle="does not begin with")


class PipeFreeRow(EnumeratorHarness):
    """A data row that has lost all its pipes fails closed naming the line (finding R2).

    Before the fix such a line read as prose: the enumeration exited 0 without the item. In the
    table() fixture the header is line 5 and the rows start at line 7, so the probed line is 8.
    """

    NEEDLE = "begins with an item id and an ISO date"
    ROW_SHAPED = [
        ("pipe-free row", "2 2026-10-01 open yes - - Some item text Done"),
        ("pipe-free row with leading spaces", "   2 2026-10-01 open yes - - Some item text Done"),
        ("pipe-free row with only stray spaces", " 2  2026-10-01  open  yes  -  -  Item  Done "),
        ("tab separated", "2\t2026-10-01\topen\tyes\t-\t-\tItem\tDone"),
        ("dotted id", "28.2 2026-10-01 open yes - - Stage 2 Done"),
        ("dotted id then a dot", "28.2.2026-10-01 open yes - - Stage 2 Done"),
        ("comma separator", "27, 2026-10-01, open, yes, -, -, Item, Done"),
        ("blockquote marker", "> 2 2026-10-01 open yes - - Item Done"),
        ("nested blockquote", "> > 2 2026-10-01 Item"),
        ("no-break space lead", "\u00a02 2026-10-01 Item"),
        ("zero-width space lead", "\u200b2 2026-10-01 Item"),
        ("byte order mark lead", "\ufeff2 2026-10-01 Item"),
        ("hangul filler lead", "\u3164 2 2026-10-01 Item"),
        ("no-break space separator", "2\u00a02026-10-01 Item"),
        ("crlf ending", "2 2026-10-01 Item\r"),
        ("id and date only", "2 2026-10-01"),
    ]
    PROSE = [
        "Item 27 was opened on 2026-10-01.",
        "2026-10-01: a dated note.",
        "# 2026 plans",
        "Version 2 ships soon.",
        "See item 27 and item 28.2 for the detail.",
        "27 items remain.",
        "<!-- reviewed 2026-10-01 -->",
        "<!-- 27 2026-10-01 parked -->",
        "",
        "   ",
        "> A quoted line.",
    ]

    def test_pipe_free_row_fails_closed(self):
        for name, line in self.ROW_SHAPED:
            with self.subTest(case=name):
                self.assert_fails(table(row("1"), line, row("3")), line=8, needle=self.NEEDLE)

    def test_pipe_free_row_fails_the_cell_dump(self):
        for name, line in self.ROW_SHAPED[:3]:
            with self.subTest(case=name):
                r = self.run_enum("--dump-cells", self.write(table(row("1"), line, row("3"))))
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertEqual(r.stdout, "")
                self.assertIn("line 8:", r.stderr)
                self.assertIn(self.NEEDLE, r.stderr)

    def test_lazy_continuation_with_the_row_shape_fails_closed(self):
        # GFM reads a non-blank line directly after a row as a lazy continuation of the table; one
        # that opens with an id and a date is a row whose pipes were lost.
        self.assert_fails(table(row("1"), row("2"), "3 2026-10-02 continued as a row"), line=9,
                          needle=self.NEEDLE)

    def test_lazy_continuation_of_plain_prose_passes(self):
        out = self.enumerate_ok(table(row("1"), "continued as plain prose, with no id or date",
                                      row("2")))
        self.assertEqual([it["id"] for it in out["items"]], ["1", "2"])

    def test_html_comment_directly_after_a_row_passes(self):
        for comment in ("<!-- reviewed 2026-10-01 -->", "<!-- note -->",
                        "<!-- 27 2026-10-01 parked -->"):
            with self.subTest(comment=comment):
                out = self.enumerate_ok(table(row("1"), comment, row("2")))
                self.assertEqual([it["id"] for it in out["items"]], ["1", "2"])

    def test_ordinary_prose_passes(self):
        text = table(row("1"), prose_before=("# Backlog", "") + tuple(self.PROSE) + ("",),
                     prose_after=("",) + tuple(self.PROSE))
        out = self.enumerate_ok(text)
        self.assertEqual([it["id"] for it in out["items"]], ["1"])

    def test_two_parser_loss_check_refuses_both_dumps(self):
        # Without the rule both dumps would omit the row and agree on the loss; with it, each
        # parser refuses its dump naming the line.
        if not MIGRATE.exists():
            self.fail("migration not found: {}".format(MIGRATE))
        old = "\n".join(["# Backlog", "", "| # | Opened | Item | Closure evidence required |",
                         "|---|---|---|---|", "| 1 | 2026-09-01 | First | Merged |",
                         "2 2026-10-01 Lost its pipes Merged", "| 3 | 2026-10-02 | Third | Merged |",
                         ""])
        for name, line in self.ROW_SHAPED[:2]:
            with self.subTest(case=name):
                src = self.write(old.replace("2 2026-10-01 Lost its pipes Merged", line),
                                 name="old.md")
                m = subprocess.run([sys.executable, "-I", str(MIGRATE), "--dump-old-cells",
                                    str(src)], capture_output=True, text=True)
                self.assertEqual(m.returncode, 1, m.stderr)
                self.assertEqual(m.stdout, "")
                self.assertIn("line 6: ", m.stderr)
                r = self.run_enum("--dump-cells", self.write(table(row("1"), line, row("3"))))
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertEqual(r.stdout, "")
                self.assertIn("line 8: ", r.stderr)


class BlockerProperty(EnumeratorHarness):
    """Every exit-0 enumeration over a grid of blockers passes the hook validator (finding R5)."""

    def cases(self):
        out = []
        for kind in BLOCKER_KINDS:
            for ref in EDGE_REFS:
                for evidence in EDGE_EVIDENCE:
                    name = "{}:{} / {}".format(kind, ascii(ref), ascii(evidence))
                    out.append((name, table(row("1", blocker=kind + ":" + ref, evidence=evidence))))
        for evidence in EDGE_EVIDENCE:
            out.append(("no blocker / " + ascii(evidence), table(row("1", evidence=evidence))))
        return out

    def test_every_exit_zero_output_passes_validate_enumeration(self):
        if not HOOK.exists():
            self.fail("vendored hook not found: {}".format(HOOK))
        cases = self.cases()
        case_file = self._tmp / "cases.json"
        case_file.write_text(json.dumps(cases), encoding="utf-8")
        r = subprocess.run([sys.executable, "-I", "-B", "-c", PROPERTY_PROG, str(SCRIPT), str(HOOK),
                            str(case_file), str(self._tmp / "case.md")],
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr)
        results = json.loads(r.stdout)
        self.assertEqual(len(results), len(cases))
        passed = {kind: 0 for kind in BLOCKER_KINDS}
        for res in results:
            with self.subTest(case=res["name"]):
                if res["code"] == 0:
                    self.assertIsNone(res["hook_error"], "exit 0 but the hook rejects the output")
                    for kind in BLOCKER_KINDS:
                        if res["name"].startswith(kind + ":"):
                            passed[kind] += 1
                else:
                    self.assertEqual(res["code"], 1)
                    self.assertEqual(res["stdout"], "", "a failing enumerator prints nothing")
                    self.assertIn("line 7:", res["stderr"])
        # Non-vacuous: every kind has accepted cases, so the property was exercised on each.
        for kind, count in passed.items():
            self.assertGreater(count, 0, "no exit-0 case for {}".format(kind))
        # The CLI path agrees with the in-process run on a sample of the grid.
        by_name = {res["name"]: res for res in results}
        for name, text in cases[::37]:
            with self.subTest(cli=name):
                cli = self.run_enum(self.write(text))
                self.assertEqual(cli.returncode, by_name[name]["code"], cli.stderr)


class Isolation(EnumeratorHarness):
    """Started without -I, the enumerator re-executes itself under python3 -I (finding F7)."""

    def test_reexecutes_isolated_so_a_planted_module_cannot_shadow_the_stdlib(self):
        tooldir = self._tmp / "tooldir"
        tooldir.mkdir()
        copy = tooldir / SCRIPT.name
        shutil.copyfile(SCRIPT, copy)
        # A planted json.py beside the script: a non-isolated start puts this directory first on
        # the import path, so "import json" would load it and exit 97.
        (tooldir / "json.py").write_text("raise SystemExit(97)\n", encoding="utf-8")
        (tooldir / "probe.py").write_text("import json\n", encoding="utf-8")
        env = dict(os.environ)
        env.pop("PYTHONSAFEPATH", None)
        probe = subprocess.run([sys.executable, str(tooldir / "probe.py")], capture_output=True,
                               text=True, env=env)
        self.assertEqual(probe.returncode, 97, "precondition: the planted module shadows json")
        path = self.write(table(row("1")))
        r = subprocess.run([sys.executable, str(copy), str(path)], capture_output=True, text=True,
                           env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([it["id"] for it in json.loads(r.stdout)["items"]], ["1"])


class InputFileType(EnumeratorHarness):
    """The backlog path must be a regular file (finding S3). A FIFO with no writer, a symlink to a
    FIFO, a directory and /dev/null each exit 1 within a short timeout, naming the path and the file
    type, in both modes; a regular file and a symlink to one still enumerate."""

    TIMEOUT = 20

    def run_bounded(self, *args):
        try:
            return subprocess.run([sys.executable, "-I", str(SCRIPT), *[str(a) for a in args]],
                                  capture_output=True, text=True, timeout=self.TIMEOUT)
        except subprocess.TimeoutExpired:
            self.fail("the enumerator did not exit within {} s for {!r}: the open blocked"
                      .format(self.TIMEOUT, [str(a) for a in args]))

    def assert_type_refused(self, path, kind):
        for args in ((path,), ("--dump-cells", path)):
            with self.subTest(args=[str(a) for a in args]):
                r = self.run_bounded(*args)
                self.assertEqual(r.returncode, 1, "expected exit 1: {}".format(r.stderr))
                self.assertEqual(r.stdout, "", "a failing enumerator prints no enumeration")
                self.assertIn("backlog {} is not a regular file (it is a {})".format(
                    os.path.abspath(str(path)), kind), r.stderr)

    def test_fifo_with_no_writer_fails_closed_promptly(self):
        fifo = self._tmp / "TODO.fifo"
        os.mkfifo(fifo)
        self.assert_type_refused(fifo, "FIFO")

    def test_symlink_to_a_fifo_fails_closed_promptly(self):
        fifo = self._tmp / "TODO.fifo"
        os.mkfifo(fifo)
        link = self._tmp / "TODO.md"
        os.symlink(fifo, link)
        self.assert_type_refused(link, "FIFO")

    def test_directory_fails_closed(self):
        directory = self._tmp / "TODO.d"
        directory.mkdir()
        self.assert_type_refused(directory, "directory")

    def test_dev_null_fails_closed(self):
        if not os.path.exists(os.devnull):
            self.fail("{} is absent, so the device case cannot run".format(os.devnull))
        self.assert_type_refused(Path(os.devnull), "character device")

    def test_regular_file_and_a_symlink_to_one_still_enumerate(self):
        path = self.write(table(row("1"), row("2")))
        link = self._tmp / "link.md"
        os.symlink(path, link)
        for target in (path, link):
            with self.subTest(path=str(target)):
                r = self.run_bounded(target)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual([it["id"] for it in json.loads(r.stdout)["items"]], ["1", "2"])

    def test_a_file_larger_than_one_read_chunk_is_read_to_its_end(self):
        rows = [row(str(n), item="x" * 120) for n in range(1, 12001)]
        path = self.write(table(*rows))
        self.assertGreater(path.stat().st_size, 1 << 20, "precondition: more than one read chunk")
        r = self.run_bounded(path)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(json.loads(r.stdout)["items"]), 12000)


# Every name that opens or reads a path; a reference to any of them, called, aliased or imported,
# counts, so a bare alias such as "f = os.open" cannot slip past the probe.
OPENERS = ("open", "fdopen", "read_text", "read_bytes", "write_text", "write_bytes")


def opener_references(source):
    """(enclosing function, dotted name) for every reference to an opener in source, in order."""
    found = []

    def dotted(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return dotted(node.value) + "." + node.attr
        return "?"

    def visit(node, func):
        for child in ast.iter_child_nodes(node):
            inner = func
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = child.name
            if isinstance(child, ast.Name) and child.id in OPENERS:
                found.append((func, child.id))
            elif isinstance(child, ast.Attribute) and child.attr in OPENERS:
                found.append((func, dotted(child)))
            elif isinstance(child, ast.alias) and child.name.split(".")[-1] in OPENERS:
                found.append((func, "import " + child.name))
            visit(child, inner)

    visit(ast.parse(source), "<module>")
    return found


def opener_call_tokens(source):
    """The number of opener names followed by "(" in the code tokens (strings and comments are not
    code), an independent count of the textual open( calls."""
    toks = [t for t in tokenize.generate_tokens(io.StringIO(source).readline)
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                              tokenize.DEDENT)]
    return sum(1 for a, b in zip(toks, toks[1:])
               if a.type == tokenize.NAME and a.string in OPENERS
               and b.type == tokenize.OP and b.string == "(")


class SourceProbe(unittest.TestCase):
    """Class probe for finding S3: every path the enumerator opens goes through _read_regular."""

    def test_every_open_in_the_enumerator_goes_through_the_checked_helper(self):
        if not SCRIPT.exists():
            self.fail("enumerator not found: {}".format(SCRIPT))
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertEqual(opener_references(source), [("_read_regular", "os.open")],
                         "an open outside the checked helper _read_regular")
        self.assertEqual(opener_call_tokens(source), 1, "a textual open( call outside the helper")
        helper = next(node for node in ast.walk(ast.parse(source))
                      if isinstance(node, ast.FunctionDef) and node.name == "_read_regular")
        names = {n.attr for n in ast.walk(helper) if isinstance(n, ast.Attribute)}
        for needed in ("O_NONBLOCK", "O_CLOEXEC", "fstat", "S_ISREG", "set_blocking"):
            self.assertIn(needed, names, "the checked helper no longer uses {}".format(needed))


class EvidenceBlankness(EnumeratorHarness):
    # Round 6 U3: the evidence description is non-blank by the str.strip() test the hook applies
    # (aiqt_hooks.py:8165), not by a narrower blank class.

    def test_evidence_of_only_unicode_whitespace_fails_closed(self):
        for kind in ("external", "foreign-lease"):
            for blank in UNICODE_BLANK_REFS:
                with self.subTest(kind=kind, text="".join("U+%04X" % ord(c) for c in blank)):
                    self.assert_fails(table(row("1", blocker=kind + ":x",
                                                evidence="2026-10-29T12:00:00Z;" + blank)),
                                      line=7, needle="blank description")

    def test_the_hook_treats_unicode_whitespace_evidence_as_absent(self):
        if not HOOK.exists():
            self.fail("vendored hook not found: {}".format(HOOK))
        r = subprocess.run([sys.executable, "-I", "-c", HOOK_EVIDENCE_PROG, str(HOOK),
                            json.dumps(["\u00a0", " \u00a0\u2003 ", "seen upstream"])],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        blank, mixed, real = json.loads(r.stdout)
        for name, res in (("U+00A0", blank), ("mixed Unicode blanks", mixed)):
            with self.subTest(evidence=name):
                # The hook accepts the enumeration, then reads the evidence as absent: the item is
                # actionable, never blocked, so an exit-0 enumeration of it would misstate the row.
                self.assertIsNone(res["error"])
                self.assertEqual(res["blocked"], [])
                self.assertEqual(len(res["actionable"]), 1)
                self.assertIn("has no fresh (non-future) evidence", res["actionable"][0][2])
        self.assertIsNone(real["error"])
        self.assertEqual(real["blocked"], [["1", "external", "x"]], "contrast: real evidence blocks")

    def test_a_real_description_led_by_unicode_whitespace_still_enumerates(self):
        # Contrast: the bare str.strip() test refuses only a blank description, never real text.
        out = self.enumerate_ok(table(row("1", blocker="external:x",
                                          evidence="2026-10-29T12:00:00Z; \u00a0seen upstream")))
        blocker = out["items"][0]["blocker"]
        self.assertEqual(blocker["evidence"], "\u00a0seen upstream")
        self.assertIsNone(self.hook_validate(json.dumps(out))["error"])


# Every strip call with an explicit character set in the enumerator, keyed by (enclosing function,
# receiver, method, characters), with why its blank class may be narrower than str.strip(). A
# "refuses" entry narrows a value that is then matched exactly or parsed, so a non-ASCII blank left
# in it makes the row fail closed; an "emitted" entry narrows a value the AEI output carries, so its
# blank test must be the bare str.strip() the hook applies to that field.
STRIP_ALLOWLIST = {
    ("_split_cells", "line", "rstrip", " \t\r"):
        ("refuses", "trailing blanks after the final bar; any other trailing character fails the "
                    "unescaped-bar end test"),
    ("_parse_blocker", "kind", "strip", " \t"):
        ("refuses", "matched exactly against BLOCKER_KINDS, as the hook matches the kind "
                    "(aiqt_hooks.py:7948)"),
    ("_parse_blocker", "ref", "strip", " \t"):
        ("emitted", "the blocker ref; its blank test is ref.strip(), the hook test at "
                    "aiqt_hooks.py:7949"),
    ("_parse_evidence", "when", "strip", " \t"):
        ("refuses", "parsed by _parse_utc; any other blank makes the time unparseable"),
    ("_parse_evidence", "text", "strip", " \t"):
        ("emitted", "the evidence description; its blank test is text.strip(), the hook test at "
                    "aiqt_hooks.py:8165"),
    ("parse_backlog", "line", "rstrip", "\r"):
        ("refuses", "matched exactly against EMPTY_MARKER; a line with any other trailing blank is "
                    "not the marker, so an unaffirmed empty backlog still fails"),
    ("parse_backlog", "c", "strip", " \t"):
        ("refuses", "each cell is then matched exactly (header, id, state, granted, the - of the "
                    "blocker and evidence cells), parsed (blocker, evidence), or carried as text the "
                    "hook never blank-tests (the item title, aiqt_hooks.py:7957)"),
}


def explicit_strip_calls(source):
    # (enclosing function, receiver, method, characters, function node) for every strip, lstrip or
    # rstrip call that passes an argument, in source order.
    found = []

    def visit(node, func, func_node):
        for child in ast.iter_child_nodes(node):
            inner, inner_node = func, func_node
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner, inner_node = child.name, child
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) \
                    and child.func.attr in ("strip", "lstrip", "rstrip") \
                    and (child.args or child.keywords):
                arg = child.args[0] if child.args else None
                chars = arg.value if isinstance(arg, ast.Constant) else ast.dump(arg or child)
                found.append((func, ast.unparse(child.func.value), child.func.attr, chars,
                              func_node))
            visit(child, inner, inner_node)

    visit(ast.parse(source), "<module>", None)
    return found


def has_bare_blank_test(func_node, name):
    # True when func_node holds "not <name>.strip()" with no argument, the hook blank test.
    for node in ast.walk(func_node):
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not) \
                and isinstance(node.operand, ast.Call) \
                and isinstance(node.operand.func, ast.Attribute) \
                and node.operand.func.attr == "strip" and not node.operand.args \
                and not node.operand.keywords \
                and isinstance(node.operand.func.value, ast.Name) \
                and node.operand.func.value.id == name:
            return True
    return False


class StripProbe(unittest.TestCase):
    # Class probe for round 6 U3: no strip with an explicit character set narrows a blank test the
    # hook makes with str.strip().

    def test_every_explicit_strip_is_allowlisted_with_its_reason(self):
        if not SCRIPT.exists():
            self.fail("enumerator not found: {}".format(SCRIPT))
        calls = explicit_strip_calls(SCRIPT.read_text(encoding="utf-8"))
        keys = [c[:4] for c in calls]
        self.assertEqual(len(keys), len(set(keys)), "a strip call is repeated; record it once")
        self.assertEqual(sorted(keys), sorted(STRIP_ALLOWLIST),
                         "an explicit-character strip outside the allowlist, or a stale entry")
        for func, receiver, method, chars, func_node in calls:
            category, reason = STRIP_ALLOWLIST[(func, receiver, method, chars)]
            with self.subTest(call="{}: {}.{}({})".format(func, receiver, method, ascii(chars))):
                self.assertIn(category, ("refuses", "emitted"))
                self.assertTrue(reason.strip())
                if category == "emitted":
                    self.assertTrue(has_bare_blank_test(func_node, receiver),
                                    "{} in {} is emitted, so its blank test must be the bare "
                                    "{}.strip() the hook applies".format(receiver, func, receiver))


# Round 9 X1: a failure message, after the "FAIL: " prefix, begins with its position.
POSITION_RE = re.compile(r"^orch-enumerate-backlog: FAIL: (line [1-9][0-9]*(?: \(end of input\))?"
                         r"|before line 1 \((?:input unreadable|no input read)\)): \S")
BEFORE_INPUT = "before line 1 (input unreadable)"
NOT_READ = "before line 1 (no input read)"

# Runs the enumerator with sys.executable pointing at an absent interpreter, so its re-execution
# under python3 -I fails (the same technique as the doctor suite).
FAILED_REEXEC_PROG = """
import runpy, sys
sys.executable = sys.argv[2]
sys.argv = [sys.argv[1], sys.argv[3]]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


class ErrorPosition(EnumeratorHarness):
    """Every failure the enumerator can produce names its position (round 9 X1). In the table()
    fixture the header is line 5 and the first row line 7."""

    TIMEOUT = 20

    def run_bounded(self, *args):
        try:
            return subprocess.run([sys.executable, "-I", str(SCRIPT), *[str(a) for a in args]],
                                  capture_output=True, text=True, timeout=self.TIMEOUT)
        except subprocess.TimeoutExpired:
            self.fail("the enumerator did not exit within {} s for {!r}"
                      .format(self.TIMEOUT, [str(a) for a in args]))

    def assert_position(self, r, position, code=1):
        self.assertEqual(r.returncode, code, "expected exit {}: {}".format(code, r.stderr))
        self.assertEqual(r.stdout, "", "a failing enumerator prints no enumeration")
        lines = r.stderr.splitlines()
        self.assertEqual(len(lines), 1, "one failure line: {!r}".format(r.stderr))
        match = POSITION_RE.match(lines[0])
        self.assertIsNotNone(match, "the failure names no position: {!r}".format(lines[0]))
        self.assertEqual(match.group(1), position, lines[0])

    def assert_path_position(self, path, position):
        for args in ((path,), ("--dump-cells", path)):
            with self.subTest(args=[str(a) for a in args]):
                self.assert_position(self.run_bounded(*args), position)

    def test_missing_input(self):
        self.assert_path_position(self._tmp / "absent.md", BEFORE_INPUT)

    def test_unreadable_input(self):
        if os.geteuid() == 0:
            self.skipTest("root reads a mode-000 file")
        path = self.write(table(row("1")))
        os.chmod(path, 0)
        self.assert_path_position(path, BEFORE_INPUT)

    def test_a_path_through_a_file_and_a_symlink_loop(self):
        # ENOTDIR and ELOOP from the open, cases that also run as root.
        through = self.write(table(row("1"))) / "child.md"
        loop = self._tmp / "loop.md"
        os.symlink(loop.name, loop)
        for path in (through, loop):
            with self.subTest(path=str(path)):
                self.assert_path_position(path, BEFORE_INPUT)

    def test_fifo_symlink_to_a_fifo_directory_and_device(self):
        fifo = self._tmp / "TODO.fifo"
        os.mkfifo(fifo)
        link = self._tmp / "link.md"
        os.symlink(fifo, link)
        directory = self._tmp / "TODO.d"
        directory.mkdir()
        if not os.path.exists(os.devnull):
            self.fail("{} is absent, so the device case cannot run".format(os.devnull))
        for path in (fifo, link, directory, Path(os.devnull)):
            with self.subTest(path=str(path)):
                self.assert_path_position(path, BEFORE_INPUT)

    def test_invalid_utf8(self):
        text = table(row("1")).encode("utf-8")
        line = text.count(b"\n") + 1
        self.assert_path_position(self.write(text + b"bad \xff byte\n"), "line {}".format(line))
        self.assert_path_position(self.write(b"# Backlog\n\nbad \xc3 here\n" + text), "line 3")

    def test_malformed_table_no_table_and_header_without_rows(self):
        cases = [(table(row("1", state="done")), "line 7"), (table(), "line 5"),
                 ("# Backlog\n\nNothing here.\n", "line 3 (end of input)"),
                 ("", "line 1 (end of input)")]
        for text, position in cases:
            with self.subTest(position=position):
                self.assert_path_position(self.write(text), position)

    def test_usage_errors(self):
        for args in ([], ["a.md", "b.md"], ["-x"], ["--dump-cells"], [""],
                     ["--dump-cells", "a.md", "b.md"]):
            with self.subTest(args=args):
                self.assert_position(self.run_bounded(*args), NOT_READ, code=2)

    def test_a_failed_reexecution(self):
        missing = self._tmp / "no-such-python"
        self.assertFalse(missing.exists(), "precondition: the interpreter path is absent")
        env = dict(os.environ)
        env.pop("PYTHONSAFEPATH", None)
        r = subprocess.run([sys.executable, "-c", FAILED_REEXEC_PROG, str(SCRIPT), str(missing),
                            str(self.write(table(row("1"))))], capture_output=True, text=True,
                           env=env, cwd=str(self._tmp), timeout=self.TIMEOUT)
        self.assertNotIn("Traceback", r.stderr)
        self.assert_position(r, NOT_READ)


def _names_a_position(arg, error_name):
    # True when a message argument begins with a position: a template starting "line {}" or
    # "before line 1", or "{}: " (or "{0}: ") formatted with BEFORE_INPUT or NOT_READ first; for
    # _fail, also str(exc), which relays an error whose construction this probe checks.
    if error_name == "_fail" and isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) \
            and arg.func.id == "str" and len(arg.args) == 1 \
            and isinstance(arg.args[0], ast.Name) and arg.args[0].id == "exc":
        return True
    template, first = None, None
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        template = arg.value
    elif isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) \
            and arg.func.attr == "format" and isinstance(arg.func.value, ast.Constant) \
            and isinstance(arg.func.value.value, str):
        template = arg.func.value.value
        first = arg.args[0] if arg.args else None
    if template is None:
        return False
    if template.startswith(("line {}", "before line 1")):
        return True
    return template.startswith(("{}: ", "{0}: ")) and isinstance(first, ast.Name) \
        and first.id in ("BEFORE_INPUT", "NOT_READ")


def position_probe(source, error_name):
    """(checked, violations) over every call of error_name or _fail in source: checked is the
    number of calls, violations the (line, source) of each whose message names no position."""
    checked, bad = 0, []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in (error_name, "_fail"):
            checked += 1
            if not _names_a_position(node.args[0] if node.args else None, node.func.id):
                bad.append((node.lineno, ast.unparse(node)))
    return checked, bad


def module_constants(source):
    return {node.targets[0].id: node.value.value for node in ast.parse(source).body
            if isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant)}


class PositionProbe(unittest.TestCase):
    # Class probe for round 9 X1: every BacklogError construction and every _fail call in the
    # enumerator begins its message with a position.

    def test_every_failure_message_in_the_enumerator_names_a_position(self):
        if not SCRIPT.exists():
            self.fail("enumerator not found: {}".format(SCRIPT))
        source = SCRIPT.read_text(encoding="utf-8")
        checked, bad = position_probe(source, "BacklogError")
        # 6 at round 9: _line_error, _input_error, the two end-of-input errors, the usage _fail and
        # the _fail that relays a BacklogError. Every line-numbered failure goes through _line_error.
        self.assertGreaterEqual(checked, 6, "the probe found fewer failure sites than the "
                                "enumerator held at round 9, so it is not reading them")
        self.assertEqual(bad, [], "a failure message that names no position")
        constants = module_constants(source)
        self.assertEqual(constants.get("BEFORE_INPUT"), BEFORE_INPUT)
        self.assertEqual(constants.get("NOT_READ"), NOT_READ)
        self.assertIn("FAIL: before line 1 (no input read): cannot re-execute", source)


class EndOfInput(EnumeratorHarness):
    """An input with no backlog table is reported at the line where the scan ended (finding S4)."""

    def test_no_table_names_the_last_line(self):
        cases = [("# Backlog\n\nNothing here.\n", 3), ("# Backlog\n\nNothing here.", 3),
                 ("", 1), ("one line\n", 1), ("a\n\n\n", 3)]
        for text, line in cases:
            with self.subTest(text=text):
                self.assert_fails(text, needle="line {} (end of input): no backlog table".format(line))


if __name__ == "__main__":
    unittest.main()
