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
refused case writes nothing.
"""

from __future__ import annotations

import collections
import json
import os
import shutil
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
            self.skipTest("vendored hook not found: {}".format(HOOK))
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
        self.refuse(old_fixture(rows=["  | 1 | a | b | c |"]), "line 7: indented")

    def test_second_header(self):
        self.refuse(old_fixture(rows=["| 1 | a | b | c |", OLD_HEADER]), "line 8: second header")

    def test_empty_table(self):
        self.refuse(old_fixture(rows=[]), "no data row")

    def test_dump_old_cells_fails_closed(self):
        self.write_src(old_fixture(rows=["| 1 | a | b |"]))
        r = self.py(MIGRATE, "--dump-old-cells", self.src)
        self.assert_refused(r, "line 7: row has 3 cells")


if __name__ == "__main__":
    unittest.main()
