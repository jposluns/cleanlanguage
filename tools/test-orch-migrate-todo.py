#!/usr/bin/env python3
"""Tests for tools/migrate-todo-aei.py (item 28.2 stage 2, PR1-e).

The migration converts the 4-column backlog table to the 8-column AEI table that
tools/orch-enumerate-backlog.py parses. These tests run both scripts as python3 -I subprocesses on
synthetic old-shape fixtures only (the real backlog is never read) and prove the three loss checks of
the plan on the output:
  (a) the multiset of (id, opened, item, closure) tuple digests from the old file, read by the
      migration parser, equals the one from the new file, read by the enumerator parser;
  (b) the enumerator output on the new file passes the hook function validate_enumeration
      (aiqt_hooks.py:7904-7959), imported by path in a separate python3 -I process, with the old id
      set and every item open and granted;
  (c) the non-table lines of old and new are identical.
They also prove the write-safety contract: the script refuses its input as output, an existing
output path (including a dangling symlink), and an already migrated or malformed input, and in each
refused case writes nothing. A file that appears after the existence check is never truncated (the
exclusive create refuses it), and a write that fails part way removes its partial output (finding
L5). A row whose "|" is kept off column 0 by an invisible, combining, filler, no-break or blockquote
prefix, a GFM row with no leading pipe, and a prose line with a mid-line pipe are each refused by
both parsers, so the two-parser loss check fails rather than agreeing on the loss (findings F1 and
G1: one rule, any "|" off a column-0 table line), and a class probe runs that rule in both parsers
over every code point of the Basic Multilingual Plane. The Isolation case proves the migration
re-executes itself under python3 -I (finding G9). A missing required input (either script or the
vendored hook) fails the test rather than skipping it.
"""

from __future__ import annotations

import collections
import json
import os
import resource
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
MIGRATE = HERE / "migrate-todo-aei.py"
ENUMERATE = HERE / "orch-enumerate-backlog.py"
HOOK = REPO_ROOT / "plugin" / "aiqt-guardrails-hooks" / "hooks" / "scripts" / "aiqt_hooks.py"

OLD_HEADER = "| # | Opened | Item | Closure evidence required |"
NEW_HEADER = "| # | Opened | State | Granted | Blocker | Evidence | Item | Closure evidence required |"

VALIDATE_PROG = """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("aiqt_hooks_under_test", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
items, err = mod.validate_enumeration(json.loads(sys.stdin.read()))
print(json.dumps({"items": items, "error": err}))
"""

# Runs in a separate python3 -I process: import the migration by path, make the existence check
# miss the output (as when the file appears after the check), and call write_output on it. Exit 0
# with "refused: ..." when the exclusive create refuses it, 3 when it wrote.
RACE_PROG = """
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("migrate_under_test", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
os.path.lexists = lambda p: False
try:
    mod.write_output(sys.argv[2], sys.argv[3], "new content\\n")
except mod.MigrationError as exc:
    print("refused: " + str(exc))
    sys.exit(0)
print("written")
sys.exit(3)
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


# The message both parsers give for a "|" off column 0 (the start of it, after "line N: ").
MIGRATE_BAR_ERROR = "a \"|\" off column 0"
ENUMERATE_BAR_ERROR = "does not begin with \"|\" at column 0"

# Runs in a separate python3 -I process: load both scripts by path and call each parser in process
# once per code point from U+0000 to U+FFFF, the code point prepended to the data row at line 8 of
# the old fixture (argv[3], for convert) and of an 8-column fixture (argv[4], for parse_backlog).
# Surrogates (not encodable in a file), "|" itself, and "\n" (the line terminator, which ends line 8
# rather than prefixing it) are excluded. Prints, per parser, the code points that did NOT fail
# closed with the column-0 error at line 8, and the count probed.
CLASS_PROBE_PROG = """
import importlib.util, json, sys

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

mig = load("migrate_under_test", sys.argv[1])
enum = load("enumerator_under_test", sys.argv[2])
old_parts, new_parts = json.loads(sys.argv[3]), json.loads(sys.argv[4])
needles = json.loads(sys.argv[5])
result = {"probed": 0, "migrate": [], "enumerate": []}
for cp in range(0x10000):
    if 0xD800 <= cp <= 0xDFFF or cp in (0x0A, 0x7C):
        continue
    result["probed"] += 1
    for key, parts, call, error in (("migrate", old_parts, mig.convert, mig.MigrationError),
                                    ("enumerate", new_parts, enum.parse_backlog,
                                     enum.BacklogError)):
        try:
            call(parts[0] + chr(cp) + parts[1] + parts[2])
        except error as exc:
            if str(exc).startswith("line 8: ") and needles[key] in str(exc):
                continue
        result[key].append("U+%04X" % cp)
print(json.dumps(result))
"""


def _limit_file_size():
    # Child-side: cap regular-file writes at 16 bytes and ignore SIGXFSZ, so the write past the cap
    # fails with EFBIG part way, as a full disk fails with ENOSPC.
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    resource.setrlimit(resource.RLIMIT_FSIZE, (16, 16))


OLD_ROWS = [
    "| 1 | 2026-09-01 | Ship the release notes | Merged PR and green CI |",
    "| 12 | 2026-09-14 | Pipe \\| inside an item, with `code` | Checklist \\| item ticked |",
    "|28.2|2026-10-01|  Stage 2 arming  |Hook fire proofs recorded|",
    "| 30 | 2026-10-20 | Non-ASCII text: caf\u00e9 na\u00efve | Gate passes |",
    "| 46 | 2026-10-28 | Point the command at the QA cycle | PR merged |  ",
]


def old_fixture(rows=OLD_ROWS, newline="\n"):
    lines = ["# Backlog", "", "Item numbers are permanent and never reused.", "",
             OLD_HEADER, "|---|:---|---|---:|"] + list(rows) + ["", "Footer prose.", ""]
    return newline.join(lines)


def non_table_lines(text):
    return [line for line in text.split("\n") if not line.startswith("|")]


class MigrateHarness(unittest.TestCase):

    def setUp(self):
        for script in (MIGRATE, ENUMERATE):
            if not script.exists():
                self.fail("script not found: {}".format(script))
        self._tmp = Path(tempfile.mkdtemp(prefix="orch-migrate-"))
        self.src = self._tmp / "TODO.md"
        self.dst = self._tmp / "TODO.aei.md"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write_src(self, text):
        data = text if isinstance(text, bytes) else text.encode("utf-8")
        self.src.write_bytes(data)
        return data

    def py(self, script, *args, cwd=None):
        return subprocess.run([sys.executable, "-I", str(script), *[str(a) for a in args]],
                              capture_output=True, text=True, cwd=cwd)

    def migrate_ok(self, text):
        self.write_src(text)
        r = self.py(MIGRATE, self.src, self.dst)
        self.assertEqual(r.returncode, 0, "migration failed: {}".format(r.stderr))
        return json.loads(r.stdout)

    def assert_refused(self, result, needle):
        self.assertEqual(result.returncode, 1, "expected exit 1: {}".format(result.stderr))
        self.assertEqual(result.stdout, "")
        self.assertIn(needle, result.stderr)


class Conversion(MigrateHarness):

    def test_n_rows_convert_to_n_rows(self):
        summary = self.migrate_ok(old_fixture())
        self.assertEqual(summary["converted"], len(OLD_ROWS))
        new = self.dst.read_text(encoding="utf-8")
        data_rows = [line for line in new.split("\n") if line.startswith("|")][2:]
        self.assertEqual(len(data_rows), len(OLD_ROWS))
        self.assertIn(NEW_HEADER, new.split("\n"))

    def test_rows_copy_cell_segments_byte_for_byte(self):
        self.migrate_ok(old_fixture())
        new_lines = self.dst.read_text(encoding="utf-8").split("\n")
        self.assertIn("| 1 | 2026-09-01 | open | yes | - | - | Ship the release notes "
                      "| Merged PR and green CI |", new_lines)
        self.assertIn("| 12 | 2026-09-14 | open | yes | - | - | Pipe \\| inside an item, with "
                      "`code` | Checklist \\| item ticked |", new_lines)
        self.assertIn("|28.2|2026-10-01| open | yes | - | - |  Stage 2 arming  "
                      "|Hook fire proofs recorded|", new_lines)
        # Trailing blanks after the closing bar are kept.
        self.assertIn("| 46 | 2026-10-28 | open | yes | - | - | Point the command at the QA cycle "
                      "| PR merged |  ", new_lines)
        self.assertIn("|---|:---| --- | --- | --- | --- |---|---:|", new_lines)

    def test_a_loss_check_tuple_digest_multisets_match(self):
        self.migrate_ok(old_fixture())
        old = self.py(MIGRATE, "--dump-old-cells", self.src)
        self.assertEqual(old.returncode, 0, old.stderr)
        new = self.py(ENUMERATE, "--dump-cells", self.dst)
        self.assertEqual(new.returncode, 0, new.stderr)
        old_out, new_out = json.loads(old.stdout), json.loads(new.stdout)
        self.assertEqual(old_out["count"], len(OLD_ROWS))
        self.assertEqual(new_out["count"], old_out["count"])
        self.assertEqual(collections.Counter(r["sha256"] for r in old_out["rows"]),
                         collections.Counter(r["sha256"] for r in new_out["rows"]))
        self.assertEqual(sorted(r["cells"][0] for r in old_out["rows"]),
                         sorted(r["cells"][0] for r in new_out["rows"]))
        self.assertEqual([r["cells"] for r in old_out["rows"]], [r["cells"] for r in new_out["rows"]])

    def test_a_loss_check_detects_a_changed_cell(self):
        # The digest comparison is live: an edited item cell in the new file changes the multiset.
        self.migrate_ok(old_fixture())
        old = json.loads(self.py(MIGRATE, "--dump-old-cells", self.src).stdout)
        tampered = self._tmp / "tampered.md"
        tampered.write_text(self.dst.read_text(encoding="utf-8")
                            .replace("Ship the release notes", "Ship the notes"), encoding="utf-8")
        new = json.loads(self.py(ENUMERATE, "--dump-cells", tampered).stdout)
        self.assertNotEqual(collections.Counter(r["sha256"] for r in old["rows"]),
                            collections.Counter(r["sha256"] for r in new["rows"]))

    def test_b_loss_check_enumeration_passes_the_hook(self):
        if not HOOK.exists():
            self.fail("vendored hook not found: {}".format(HOOK))
        self.migrate_ok(old_fixture())
        r = self.py(ENUMERATE, self.dst)
        self.assertEqual(r.returncode, 0, r.stderr)
        v = subprocess.run([sys.executable, "-I", "-c", VALIDATE_PROG, str(HOOK)],
                           input=r.stdout, capture_output=True, text=True)
        self.assertEqual(v.returncode, 0, v.stderr)
        verdict = json.loads(v.stdout)
        self.assertIsNone(verdict["error"], verdict["error"])
        self.assertEqual({it["id"] for it in verdict["items"]}, {"1", "12", "28.2", "30", "46"})
        for it in verdict["items"]:
            self.assertEqual(it["state"], "open")
            self.assertIs(it["granted"], True)
            self.assertIsNone(it["blocker"])

    def test_c_loss_check_non_table_lines_identical(self):
        src = old_fixture()
        self.migrate_ok(src)
        new = self.dst.read_text(encoding="utf-8")
        self.assertEqual(non_table_lines(src), non_table_lines(new))
        self.assertTrue(new.endswith("\n"))

    def test_crlf_and_no_final_newline_are_preserved(self):
        src = old_fixture(newline="\r\n").rstrip("\r\n")
        self.write_src(src)
        r = self.py(MIGRATE, self.src, self.dst)
        self.assertEqual(r.returncode, 0, r.stderr)
        new = self.dst.read_bytes().decode("utf-8")
        self.assertFalse(new.endswith("\n"))
        self.assertEqual(new.count("\r\n"), src.count("\r\n"))
        self.assertEqual(non_table_lines(src), non_table_lines(new))
        e = self.py(ENUMERATE, self.dst)
        self.assertEqual(e.returncode, 0, e.stderr)
        self.assertEqual(len(json.loads(e.stdout)["items"]), len(OLD_ROWS))

    def test_output_is_created_private(self):
        self.migrate_ok(old_fixture())
        mode = stat.S_IMODE(os.stat(self.dst).st_mode)
        self.assertEqual(mode >> 6 << 6, mode, "group and other permission bits are clear")

    def test_input_is_not_modified(self):
        data = self.write_src(old_fixture())
        r = self.py(MIGRATE, self.src, self.dst)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.src.read_bytes(), data)


class WriteSafety(MigrateHarness):

    def test_refuses_to_write_to_its_input_path(self):
        data = self.write_src(old_fixture())
        self.assert_refused(self.py(MIGRATE, self.src, self.src), "input path")
        self.assertEqual(self.src.read_bytes(), data)

    def test_refuses_an_alias_spelling_of_its_input(self):
        data = self.write_src(old_fixture())
        sub = self._tmp / "sub"
        sub.mkdir()
        alias = str(sub) + "/../TODO.md"
        self.assert_refused(self.py(MIGRATE, self.src, alias), "input path")
        self.assertEqual(self.src.read_bytes(), data)

    def test_refuses_a_relative_spelling_of_its_input(self):
        data = self.write_src(old_fixture())
        self.assert_refused(self.py(MIGRATE, self.src, "TODO.md", cwd=self._tmp), "input path")
        self.assertEqual(self.src.read_bytes(), data)

    def test_refuses_a_symlink_to_its_input(self):
        data = self.write_src(old_fixture())
        link = self._tmp / "link.md"
        link.symlink_to(self.src)
        self.assert_refused(self.py(MIGRATE, self.src, link), "already exists")
        self.assertEqual(self.src.read_bytes(), data)

    def test_refuses_an_existing_output(self):
        self.write_src(old_fixture())
        self.dst.write_bytes(b"keep me\n")
        self.assert_refused(self.py(MIGRATE, self.src, self.dst), "already exists")
        self.assertEqual(self.dst.read_bytes(), b"keep me\n")

    def test_refuses_a_dangling_symlink_output(self):
        self.write_src(old_fixture())
        target = self._tmp / "nowhere.md"
        self.dst.symlink_to(target)
        self.assert_refused(self.py(MIGRATE, self.src, self.dst), "already exists")
        self.assertFalse(target.exists(), "nothing is written through a dangling symlink")

    def test_never_truncates_an_output_that_appears_after_the_check(self):
        # Red if O_EXCL were replaced by O_TRUNC: the create would then open and truncate the file.
        self.write_src(old_fixture())
        self.dst.write_bytes(b"keep me\n")
        r = subprocess.run([sys.executable, "-I", "-c", RACE_PROG, str(MIGRATE), str(self.src),
                            str(self.dst)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("refused: cannot create output", r.stdout)
        self.assertEqual(self.dst.read_bytes(), b"keep me\n")

    def test_a_failed_write_removes_the_partial_output(self):
        self.write_src(old_fixture())
        r = subprocess.run([sys.executable, "-I", str(MIGRATE), str(self.src), str(self.dst)],
                           capture_output=True, text=True, preexec_fn=_limit_file_size)
        self.assert_refused(r, "cannot write output")
        self.assertIn("the partial output was removed", r.stderr)
        self.assertFalse(os.path.lexists(self.dst), "a failed write leaves no partial output")

    def test_refuses_an_output_in_a_missing_directory(self):
        self.write_src(old_fixture())
        out = self._tmp / "absent-dir" / "out.md"
        self.assert_refused(self.py(MIGRATE, self.src, out), "cannot create output")
        self.assertFalse(out.parent.exists())

    def test_usage_errors_exit_2(self):
        for args in ([], [self.src], [self.src, self.dst, "x"], ["--dump-old-cells"]):
            r = self.py(MIGRATE, *args)
            self.assertEqual(r.returncode, 2, "args {!r}: {}".format(args, r.stderr))
        self.assertFalse(self.dst.exists())


class MalformedInput(MigrateHarness):
    """A malformed or already migrated input is refused and writes no output."""

    def refuse(self, text, needle):
        self.write_src(text)
        self.assert_refused(self.py(MIGRATE, self.src, self.dst), needle)
        self.assertFalse(os.path.lexists(self.dst), "a refused migration writes nothing")

    def test_missing_input(self):
        self.assert_refused(self.py(MIGRATE, self._tmp / "absent.md", self.dst), "cannot read input")
        self.assertFalse(os.path.lexists(self.dst))

    def test_invalid_utf8(self):
        self.refuse(old_fixture().encode("utf-8") + b"\xff\n", "not valid UTF-8")

    def test_already_migrated(self):
        text = "\n".join([NEW_HEADER, "|---|---|---|---|---|---|---|---|",
                          "| 1 | d | open | yes | - | - | i | c |"]) + "\n"
        self.refuse(text, "already carries the 8-column header")

    def test_wrong_header(self):
        self.refuse("| # | Item | Opened | Closure evidence required |\n| 1 | a | b | c |\n",
                    "header is not the expected")

    def test_no_header(self):
        self.refuse("# Backlog\n\nNo table.\n", "no 4-column header")

    def test_row_before_header(self):
        self.refuse("| 1 | a | b | c |\n" + OLD_HEADER + "\n", "line 1: table row before the header")

    def test_wrong_cell_count(self):
        self.refuse(old_fixture(rows=["| 1 | 2026-09-01 | only three |"]), "line 7: row has 3 cells")

    def test_unterminated_row(self):
        self.refuse(old_fixture(rows=["| 1 | 2026-09-01 | item | closure"]), "line 7: table row")

    def test_bad_id(self):
        self.refuse(old_fixture(rows=["| CL-1 | 2026-09-01 | item | closure |"]), "bad item id")

    def test_duplicate_id(self):
        self.refuse(old_fixture(rows=["| 1 | a | b | c |", "| 1 | d | e | f |"]),
                    "line 8: duplicate item id 1")

    def test_indented_row(self):
        self.refuse(old_fixture(rows=["  | 1 | a | b | c |"]), "line 7: " + MIGRATE_BAR_ERROR)

    def test_second_header(self):
        self.refuse(old_fixture(rows=["| 1 | a | b | c |", OLD_HEADER]), "line 8: second header")

    def test_empty_table(self):
        self.refuse(old_fixture(rows=[]), "no data row")

    def test_dump_old_cells_fails_closed(self):
        self.write_src(old_fixture(rows=["| 1 | a | b |"]))
        r = self.py(MIGRATE, "--dump-old-cells", self.src)
        self.assert_refused(r, "line 7: row has 3 cells")


class HiddenTablePrefix(MigrateHarness):
    """A "|" off column 0 is refused, whatever keeps it there (F1 and G1).

    Before F1 the migration copied a prefixed row through as prose and both dumps omitted it, so
    the digest multisets agreed and the loss check could not see the loss. The F1 fix enumerated
    prefix classes, so a prefix outside them (G1) still hid the row. In old_fixture() the header is
    line 5 and the rows start at line 7.
    """

    # Each line keeps old row 12 (or a "|") off column 0: the prefixed rows, a GFM row with no
    # leading pipe, and prose with a mid-line pipe.
    MISPLACED = ([(name, prefix + OLD_ROWS[1]) for name, prefix in HIDDEN_PREFIXES]
                 + [("GFM row with no leading pipe", OLD_ROWS[1][1:].lstrip()),
                    ("prose with a mid-line pipe", "Prose with a | bar mid-line.")])

    def rows_with(self, prefix):
        return [OLD_ROWS[0], prefix + OLD_ROWS[1]] + OLD_ROWS[2:]

    def clear_dst(self):
        # Each subtest starts with no output, so an output a failing subtest wrote
        # cannot make every later subtest fail too.
        if os.path.lexists(self.dst):
            os.unlink(self.dst)

    def test_prefixed_row_is_refused_and_writes_nothing(self):
        for name, prefix in HIDDEN_PREFIXES:
            with self.subTest(prefix=name):
                self.clear_dst()
                self.write_src(old_fixture(rows=self.rows_with(prefix)))
                self.assert_refused(self.py(MIGRATE, self.src, self.dst),
                                    "line 8: " + MIGRATE_BAR_ERROR)
                self.assertFalse(os.path.lexists(self.dst))

    def test_prefixed_header_is_refused(self):
        for name, prefix in HIDDEN_PREFIXES:
            with self.subTest(prefix=name):
                self.clear_dst()
                self.write_src(old_fixture().replace(OLD_HEADER, prefix + OLD_HEADER, 1))
                self.assert_refused(self.py(MIGRATE, self.src, self.dst),
                                    "line 5: " + MIGRATE_BAR_ERROR)
                self.assertFalse(os.path.lexists(self.dst))

    def test_byte_order_mark_before_a_first_line_header(self):
        self.write_src("\ufeff" + OLD_HEADER + "\n|---|---|---|---|\n" + OLD_ROWS[0] + "\n")
        r = self.py(MIGRATE, self.src, self.dst)
        self.assert_refused(r, "line 1: " + MIGRATE_BAR_ERROR)
        self.assertIn("U+FEFF", r.stderr)
        self.assertFalse(os.path.lexists(self.dst))

    def test_message_names_the_prefix_characters_by_code_point(self):
        for name, prefix in HIDDEN_PREFIXES[:4] + [("mixed", "\u00a0\u200b> ")]:
            with self.subTest(prefix=name):
                self.clear_dst()
                self.write_src(old_fixture(rows=self.rows_with(prefix)))
                r = self.py(MIGRATE, self.src, self.dst)
                self.assert_refused(r, "line 8: " + MIGRATE_BAR_ERROR)
                for ch in prefix:
                    if not " " <= ch <= "~":
                        self.assertIn("U+{:04X}".format(ord(ch)), r.stderr)

    def test_gfm_row_without_a_leading_pipe_mid_table_is_refused(self):
        # GFM accepts a row with no leading pipe, so a renderer shows it as a row of the table;
        # before G1 the migration copied it through as prose and both dumps dropped item 12.
        self.write_src(old_fixture(rows=[OLD_ROWS[0], OLD_ROWS[1][1:].lstrip()] + OLD_ROWS[2:]))
        self.assert_refused(self.py(MIGRATE, self.src, self.dst), "line 8: " + MIGRATE_BAR_ERROR)
        self.assertFalse(os.path.lexists(self.dst))

    def test_two_parser_loss_check_fails_rather_than_agreeing(self):
        for name, line in self.MISPLACED:
            with self.subTest(case=name):
                self.clear_dst()
                # The old file with the misplaced line: the migration parser refuses its dump.
                self.write_src(old_fixture(rows=[OLD_ROWS[0], line] + OLD_ROWS[2:]))
                old = self.py(MIGRATE, "--dump-old-cells", self.src)
                self.assert_refused(old, "line 8: " + MIGRATE_BAR_ERROR)
                # The new file a parser without the rule would write (the line copied through as
                # prose): the enumerator parser refuses its dump, so no two counts can agree.
                carried = self._tmp / "carried.md"
                carried.write_text("\n".join([
                    NEW_HEADER, "|---|---|---|---|---|---|---|---|",
                    "| 1 | 2026-09-01 | open | yes | - | - | Ship the release notes | Merged |",
                    line, ""]), encoding="utf-8")
                new = self.py(ENUMERATE, "--dump-cells", carried)
                self.assertEqual(new.returncode, 1, new.stderr)
                self.assertEqual(new.stdout, "")
                self.assertIn("line 4: ", new.stderr)
                self.assertIn(ENUMERATE_BAR_ERROR, new.stderr)

    def test_prose_with_a_mid_line_bar_is_refused(self):
        # Replaces the F1-era test that prose with a "|" after other text is copied: under G1 any
        # "|" outside a column-0 table line is refused, because a rule that lets some prefixed bars
        # through has to enumerate which, and any prefix outside the list hides a row. The backlog
        # keeps every "|" inside a table line, so this refuses nothing in a valid backlog.
        for line in ("Prose with a | bar mid-line.", "> A quoted line with a | bar.",
                     "\u00a0No-break led prose | with a bar.", "\u200b> quoted | text"):
            with self.subTest(line=line):
                self.clear_dst()
                self.write_src(line + "\n" + old_fixture())
                self.assert_refused(self.py(MIGRATE, self.src, self.dst),
                                    "line 1: " + MIGRATE_BAR_ERROR)
                self.assertFalse(os.path.lexists(self.dst))

    def test_prose_without_a_bar_is_copied(self):
        prose = ["\ufeffTitle line", "> ", "\u00a0", "> A quoted line without a bar.",
                 "\u3164Filler-led prose."]
        src = "\n".join(prose) + "\n" + old_fixture()
        self.migrate_ok(src)
        new = self.dst.read_text(encoding="utf-8")
        self.assertEqual(non_table_lines(src), non_table_lines(new))
        self.assertEqual(json.loads(self.py(ENUMERATE, "--dump-cells", self.dst).stdout)["count"],
                         len(OLD_ROWS))

    def test_class_probe_every_bmp_code_point_fails_both_parsers(self):
        old_lines = old_fixture(rows=[OLD_ROWS[0], "\x00"]).split("\n")
        self.assertEqual(old_lines[7], "\x00", "precondition: the probed old row is line 8")
        old_parts = ["\n".join(old_lines[:7]) + "\n", "| 9 | 2026-10-01 | Probe item | Probe |",
                     "\n" + "\n".join(old_lines[8:])]
        new_lines = ["# Backlog", "", "Item numbers are permanent and never reused.", "",
                     NEW_HEADER, "|---|---|---|---|---|---|---|---|",
                     "| 1 | 2026-09-01 | open | yes | - | - | First | Merged |", "\x00",
                     "", "Footer prose.", ""]
        self.assertEqual(new_lines[7], "\x00", "precondition: the probed new row is line 8")
        new_parts = ["\n".join(new_lines[:7]) + "\n",
                     "| 9 | 2026-10-01 | open | yes | - | - | Probe item | Probe |",
                     "\n" + "\n".join(new_lines[8:])]
        r = subprocess.run([sys.executable, "-I", "-c", CLASS_PROBE_PROG, str(MIGRATE),
                            str(ENUMERATE), json.dumps(old_parts), json.dumps(new_parts),
                            json.dumps({"migrate": MIGRATE_BAR_ERROR,
                                        "enumerate": ENUMERATE_BAR_ERROR})],
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json.loads(r.stdout)
        self.assertEqual(res["probed"], 0x10000 - 0x800 - 2)
        self.assertEqual(res["migrate"], [], "code points the migration parser let through")
        self.assertEqual(res["enumerate"], [], "code points the enumerator parser let through")
        # The CLI paths agree with the in-process parsers on a sample of the probed code points.
        for cp in (0x00, 0x20, 0x41, 0xA0, 0x34F, 0x3164, 0xFE0F, 0xFFA0, 0xFFFF):
            with self.subTest(cp="U+%04X" % cp):
                self.clear_dst()
                self.write_src(old_parts[0] + chr(cp) + old_parts[1] + old_parts[2])
                self.assert_refused(self.py(MIGRATE, "--dump-old-cells", self.src),
                                    "line 8: " + MIGRATE_BAR_ERROR)
                carried = self._tmp / "probe-new.md"
                carried.write_text(new_parts[0] + chr(cp) + new_parts[1] + new_parts[2],
                                   encoding="utf-8")
                new = self.py(ENUMERATE, "--dump-cells", carried)
                self.assertEqual(new.returncode, 1, new.stderr)
                self.assertIn("line 8: ", new.stderr)


class Isolation(MigrateHarness):
    """Started without -I, the migration re-executes itself under python3 -I (finding G9)."""

    def test_reexecutes_isolated_so_a_planted_module_cannot_shadow_the_stdlib(self):
        tooldir = self._tmp / "tooldir"
        tooldir.mkdir()
        copy = tooldir / MIGRATE.name
        shutil.copyfile(MIGRATE, copy)
        # A planted json.py beside the script: a non-isolated start puts this directory first on
        # the import path, so "import json" would load it and exit 97.
        (tooldir / "json.py").write_text("raise SystemExit(97)\n", encoding="utf-8")
        (tooldir / "probe.py").write_text("import json\n", encoding="utf-8")
        env = dict(os.environ)
        env.pop("PYTHONSAFEPATH", None)
        probe = subprocess.run([sys.executable, str(tooldir / "probe.py")], capture_output=True,
                               text=True, env=env)
        self.assertEqual(probe.returncode, 97, "precondition: the planted module shadows json")
        self.write_src(old_fixture())
        r = subprocess.run([sys.executable, str(copy), str(self.src), str(self.dst)],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["converted"], len(OLD_ROWS))
        self.assertTrue(self.dst.exists())


if __name__ == "__main__":
    unittest.main()
