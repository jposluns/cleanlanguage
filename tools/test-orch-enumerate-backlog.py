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
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SCRIPT = HERE / "orch-enumerate-backlog.py"
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
            self.skipTest("vendored hook not found: {}".format(HOOK))
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
            self.skipTest("vendored hook not found: {}".format(HOOK))
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
            self.skipTest("vendored hook not found: {}".format(HOOK))
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
        self.assert_fails(self._tmp, needle="cannot read backlog")

    def test_unreadable_file(self):
        if os.geteuid() == 0:
            self.skipTest("root reads a mode-000 file")
        path = self.write(table(row("1")))
        os.chmod(path, 0)
        self.assert_fails(path, needle="cannot read backlog")

    def test_invalid_utf8(self):
        self.assert_fails(self.write(table(row("1")).encode("utf-8") + b"\xff\xfe\n"),
                          needle="not valid UTF-8")

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
        self.assert_fails(table("  " + row("1")), line=7, needle="indented")

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


if __name__ == "__main__":
    unittest.main()
