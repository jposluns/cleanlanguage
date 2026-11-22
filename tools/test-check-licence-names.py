#!/usr/bin/env python3
"""Tests for tools/check-licence-names.py, the licence-name gate.

Each case builds a throwaway git repository in a temporary folder (git init and git add; no commit
and no identity are needed, since the gate reads the index and the work tree). The repository
holds the gate's 3 files: a copy of the gate and of this test from this test's own folder, and an
allowlist with 1 row, README.md, 1, keep, CC BY-SA 4.0, for README.md, whose 1 matching line holds
that marker. The gate runs as a separate process, python3 -I with --root, with the git
configuration of the machine and of the user left out and the search for a repository stopped at
the temporary folder, so the result depends on the case alone.

Every refusal case first runs the gate on the unchanged repository, a control that must exit 0
and print exactly the summary line, then makes 1 change (a case with subtests undoes each change
before the next) and requires exit 1, a standard output of exactly 1 summary line whose problem
count is the number of problem lines, and problem lines that are exactly the cause and any
consequence the case names, each consequence with the reason it follows. So each case fails when
the gate does not refuse the change, when it names another cause or an extra problem, and when it
refuses the unchanged repository. Every run of the gate must also write nothing outside printable
ASCII, so a control byte in a path, count, owner or marker that reaches the output fails the case.

The controls of their own: the unchanged repository reports 1 line in 1 file and 0 problems;
--list prints README.md:1 and the total, and does not parse the allowlist; a line ends only at a
line feed, so carriage returns, other control bytes, binary and non-UTF-8 bytes stay in their
line; near misses of the 3 terms match nothing; an untracked file is not read; an unknown option
exits 2.

4 cases call the gate's read_file in a separate python3 -I process that loads the gate by file
path. 1 reads a regular file as a control. The other 3 replace os.lstat or os.fdopen in that
process alone, to reach what a race or a failing disk could cause: an open descriptor that is not
a regular file, a symbolic link that appears after the lstat check, and a read error. A case for
a file whose mode the runner can still read after chmod 000, as root can, is skipped and says so.

Exit 0 when every case passes; 1 otherwise.
"""

from __future__ import annotations

import errno
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE / "check-licence-names.py"
SELF = HERE / "test-check-licence-names.py"
ALLOWLIST = "tools/licence-names-allowlist.tsv"
NAMED_EXCEPTIONS = ("tools/check-licence-names.py", ALLOWLIST, "tools/test-check-licence-names.py")
ROW = "README.md\t1\tkeep\tCC BY-SA 4.0"
HEADER = "# path\tcount\towner\tmarker\n"
README = b"# Example\n\nLicence: CC BY-SA 4.0\n"
PREFIX = "check-licence-names: "
SUMMARY = re.compile(r"check-licence-names: checked: \d+ lines in \d+ files; (\d+) problem\(s\)\n")
CONTROL_OUT = PREFIX + "checked: 1 lines in 1 files; 0 problem(s)\n"
BAD_COUNT = "is not canonical ASCII decimal: digits 0 to 9 only, from 1, with no sign, space or leading zero"
TERM = b"CC BY-SA 4.0"
# Each byte run here ends a line for some reader (str.splitlines, a vertical-tab split and others),
# but not for the gate, which splits at a line feed only.
SEPARATORS = (b"\x0b", b"\x0c", b"\x1c", b"\x1d", b"\x1e", b"\x85", "\u2028".encode(), "\u2029".encode())
PROBE = """
import errno, importlib.util, json, os, sys
from pathlib import Path
gate_path, mode, root, name, decoy = sys.argv[1:6]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("gate", gate_path)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
real_lstat, real_fdopen = os.lstat, os.fdopen
if mode in ("descriptor", "swap"):
    os.lstat = lambda path, *args, **kwargs: real_lstat(decoy)
if mode == "read-error":
    class Failing:
        def __init__(self, handle):
            self.handle = handle
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            self.handle.close()
        def fileno(self):
            return self.handle.fileno()
        def read(self, *args):
            raise OSError(errno.EIO, os.strerror(errno.EIO))
    os.fdopen = lambda *args, **kwargs: Failing(real_fdopen(*args, **kwargs))
problems = []
data = gate.read_file(Path(root), name, problems)
print(json.dumps({"data": None if data is None else data.decode("latin-1"), "problems": problems}))
"""


class Repo:
    """A throwaway git repository holding the gate's 3 files, the allowlist and README.md."""

    def __init__(self, base: Path):
        self.base = base
        self.root = base / "repo"
        (self.root / "tools").mkdir(parents=True)
        shutil.copyfile(GATE, self.root / "tools" / "check-licence-names.py")
        shutil.copyfile(SELF, self.root / "tools" / "test-check-licence-names.py")
        self.write(ALLOWLIST, (HEADER + ROW + "\n").encode("utf-8"))
        self.write("README.md", README)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                        GIT_CEILING_DIRECTORIES=str(base))
        for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"):
            self.env.pop(name, None)
        self.git("init", "-q")
        self.git("add", "-A")

    def write(self, rel: str, data: bytes) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def git(self, *args: str, stdin: bytes = b"") -> str:
        done = subprocess.run(["git", "-C", str(self.root), *args], input=stdin, capture_output=True,
                              env=self.env, timeout=60)
        if done.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed: {done.stderr.decode('utf-8', 'replace')}")
        return done.stdout.decode("utf-8", "replace")

    def set_rows(self, *rows: str) -> None:
        self.write(ALLOWLIST, (HEADER + "".join(row + "\n" for row in rows)).encode("utf-8"))
        self.git("add", ALLOWLIST)

    def add_row(self, row: str) -> None:
        self.set_rows(ROW, row)

    def track(self, rel: str, data: bytes) -> None:
        self.write(rel, data)
        self.git("add", "--", rel)

    def gate(self, *args: str, env: dict | None = None):
        done = subprocess.run([sys.executable, "-I", str(GATE), "--root", str(self.root), *args],
                              capture_output=True, env=env or self.env, stdin=subprocess.DEVNULL, timeout=120)
        return (done.returncode, done.stdout.decode("utf-8", "replace"),
                done.stderr.decode("utf-8", "replace"))


class GateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Repo(Path(self.tmp.name))

    def run_gate(self, *args: str, env: dict | None = None):
        code, out, err = self.repo.gate(*args, env=env)
        shown = [char for char in out + err if char != "\n" and not " " <= char <= "~"]
        self.assertEqual(shown, [], f"the output holds characters outside printable ASCII:\n{out}{err}")
        return code, out, err

    def passes(self, out_text: str = CONTROL_OUT, *args: str):
        code, out, err = self.run_gate(*args)
        self.assertEqual((code, err), (0, ""), f"the gate must pass:\n{out}{err}")
        self.assertEqual(out, out_text)

    def control(self):
        self.passes()

    def refused(self, cause: str, *args: str, env: dict | None = None, also: tuple = (), out_text: str = ""):
        """Exit 1 and problem lines that are exactly cause and also, each matched as a substring once."""
        code, out, err = self.run_gate(*args, env=env)
        self.assertEqual(code, 1, f"the gate must refuse this change:\n{out}{err}")
        lines = err.splitlines()
        self.assertTrue(all(line.startswith(PREFIX) for line in lines), f"a line is not a problem line:\n{err}")
        wanted, left = [cause, *also], list(lines)
        for text in wanted:
            match = next((line for line in left if text in line), None)
            self.assertIsNotNone(match, f"no problem line names {text!r}:\n{err}")
            left.remove(match)
        self.assertEqual(left, [], f"problem lines that the case does not name:\n{err}")
        if "--list" in args:
            *listed, total = out.splitlines()
            self.assertRegex(total, r"^total: \d+ lines in \d+ files$")
            self.assertTrue(all(re.fullmatch(r".+:\d+", line) for line in listed), out)
        else:
            summary = SUMMARY.fullmatch(out)
            self.assertIsNotNone(summary, f"standard output is not exactly 1 summary line:\n{out}")
            self.assertEqual(int(summary.group(1)), len(lines), out)
        if out_text:
            self.assertEqual(out, out_text)

    def probe(self, mode: str, name: str, decoy: str):
        done = subprocess.run([sys.executable, "-I", "-c", PROBE, str(GATE), mode, str(self.repo.root), name,
                               str(self.repo.root / decoy)], capture_output=True, stdin=subprocess.DEVNULL,
                              timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
        return json.loads(done.stdout)


class Controls(GateCase):
    def test_unchanged_repository_passes(self):
        self.control()

    def test_list_prints_each_file_and_the_total(self):
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")

    def test_list_does_not_parse_the_allowlist(self):
        self.repo.set_rows("README.md\t5\tkeep\tCC BY-SA 4.0", "README.md\t0\tkeep")
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")

    def test_carriage_returns_alone_do_not_end_a_line(self):
        self.repo.track("notes.txt", b"CC BY-SA 4.0\rBY-SA again\rCC BY-SA 4.0\r")
        self.repo.add_row("notes.txt\t1\tkeep\tCC BY-SA 4.0")
        self.passes(PREFIX + "checked: 2 lines in 2 files; 0 problem(s)\n")

    def test_other_control_binary_and_non_utf8_bytes_do_not_end_a_line(self):
        self.repo.track("ctl.txt", b"plain\n" + b"".join(sep + TERM for sep in SEPARATORS) + b"\n")
        self.repo.track("bin.dat", b"\x00\xff\xfe\n\x00" + TERM + b"\x00\xff\n\x00\n")
        self.repo.set_rows(ROW, "ctl.txt\t1\tkeep\tCC BY-SA 4.0", "bin.dat\t1\tkeep\tCC BY-SA 4.0")
        self.passes(PREFIX + "checked: 3 lines in 3 files; 0 problem(s)\n")

    def test_near_misses_of_the_terms_match_nothing(self):
        near = ("BY SA", "BY_SA", "BYSA", "BY-S A", "BY\u2010SA", "Share Alike", "Share-Alike", "\u017fhareAlike",
                "CreativeCommons", "Creative  Commons", "Creative\tCommons", "Creative Common", "Apache-2.0", "MIT")
        self.repo.track("near.txt", "".join(text + "\n" for text in near).encode("utf-8"))
        self.control()

    def test_untracked_file_is_not_read(self):
        self.repo.write("untracked.md", b"ShareAlike\n")
        self.control()

    def test_unknown_option_exits_2(self):
        code, out, err = self.run_gate("--bogus")
        self.assertEqual((code, out), (2, ""), err)
        self.assertIn("unrecognized arguments: --bogus", err)

    def test_read_file_returns_a_regular_file(self):
        self.assertEqual(self.probe("plain", "README.md", "README.md"),
                         {"data": README.decode("latin-1"), "problems": []})


class Refusals(GateCase):
    def test_unclaimed_line_in_another_file(self):
        self.control()
        self.repo.track("other.md", b"CC BY-SA 4.0\n")
        self.refused("other.md:1: names a licence term and no allowlist row claims it")

    def test_each_term_in_another_letter_case(self):
        self.control()
        for number, term in enumerate((b"by-sa", b"SHAREALIKE", b"creative COMMONS"), 1):
            with self.subTest(term=term):
                name = f"case{number}.md"
                self.repo.track(name, b"plain\n" + term + b"\n")
                self.refused(f"{name}:2: names a licence term and no allowlist row claims it")
                self.repo.git("rm", "-q", "-f", name)
                self.control()

    def test_line_ends_only_at_a_line_feed(self):
        self.control()
        self.repo.track("ctl.txt", b"plain\n" + b"".join(sep + TERM for sep in SEPARATORS) + b"\nplain\n")
        self.repo.track("bin.dat", b"\x00\xff\xfe\n\x00" + TERM + b"\x00\xff\n\x00\n")
        self.refused("ctl.txt:2: names a licence term and no allowlist row claims it",
                     also=("bin.dat:2: names a licence term and no allowlist row claims it",),
                     out_text=PREFIX + "checked: 3 lines in 3 files; 2 problem(s)\n")

    def test_line_matching_no_marker_of_its_file(self):
        self.control()
        self.repo.track("README.md", README + b"ShareAlike\n")
        self.refused("README.md:4: names a licence term and no allowlist row claims it")

    def test_marker_is_matched_with_its_letter_case(self):
        self.control()
        # A line that no row claims leaves its row, of count 1, claiming 0 lines, so the row is stale too.
        with self.subTest(case="marker in lower case, line in upper case"):
            self.repo.set_rows("README.md\t1\tkeep\tcc by-sa 4.0")
            self.refused("README.md:3: names a licence term and no allowlist row claims it",
                         also=("allowlist row 2 (keep, marker 'cc by-sa 4.0') is stale: it claims 0 line(s), "
                               "the allowlist says 1",))
            self.repo.set_rows(ROW)
            self.control()
        with self.subTest(case="marker in upper case, line in lower case"):
            self.repo.track("README.md", b"# Example\n\nLicence: cc by-sa 4.0\n")
            self.refused("README.md:3: names a licence term and no allowlist row claims it",
                         also=("allowlist row 2 (keep, marker 'CC BY-SA 4.0') is stale: it claims 0 line(s), "
                               "the allowlist says 1",))
            self.repo.track("README.md", README)
            self.control()

    def test_removed_line_leaves_a_stale_row(self):
        self.control()
        self.repo.track("README.md", b"# Example\n")
        self.refused("is stale: it claims 0 line(s), the allowlist says 1")

    def test_count_off_by_one(self):
        self.control()
        self.repo.set_rows("README.md\t2\tkeep\tCC BY-SA 4.0")
        self.refused("is stale: it claims 1 line(s), the allowlist says 2")

    def test_new_line_of_a_claimed_kind_leaves_a_stale_row(self):
        self.control()
        self.repo.track("README.md", README + b"Licence: CC BY-SA 4.0\n")
        self.refused("README.md: allowlist row 2 (keep, marker 'CC BY-SA 4.0') is stale: it claims 2 line(s), "
                     "the allowlist says 1")

    def test_count_of_any_length_is_read(self):
        self.control()
        count = "1" + "0" * 5000
        self.repo.set_rows(f"README.md\t{count}\tkeep\tCC BY-SA 4.0")
        self.refused(f"is stale: it claims 1 line(s), the allowlist says {count}")

    def test_two_markers_on_one_line(self):
        self.control()
        self.repo.add_row("README.md\t1\tunit-3\tBY-SA 4.0")
        # A line that 2 rows claim is claimed by neither, so each row, of count 1, claims 0 lines and is stale.
        self.refused("README.md:3: holds the markers of allowlist rows 2, 3, so it is ambiguous and no row claims it",
                     also=("allowlist row 2 (keep, marker 'CC BY-SA 4.0') is stale: it claims 0 line(s)",
                           "allowlist row 3 (unit-3, marker 'BY-SA 4.0') is stale: it claims 0 line(s)"))

    def test_malformed_rows(self):
        self.control()
        cases = [
            ("README.md\t1\tkeep", "it has 3 tab-separated field(s), not 4"),
            ("README.md\t1\tkeep\tLicence:\tmore", "it has 5 tab-separated field(s), not 4"),
            ("README.md\t1\tkeep\tLicence:\r", "it holds a carriage return"),
            ("README.md\t1\tunit-9\tLicence:", "the owner 'unit-9' is none of unit-2, unit-3, keep"),
            ("README.md\t1\tkeep\t", "the marker is empty"),
            (ROW, "it repeats the path and marker of row 2"),
            ("missing.md\t1\tkeep\tLicence:", "missing.md is not a tracked path"),
        ]
        cases += [(f"{path}\t1\tkeep\tLicence:", f"{path} is a named exception") for path in NAMED_EXCEPTIONS]
        counts = (("0", "0"), ("01", "01"), ("00", "00"), ("+1", "+1"), ("-1", "-1"), (" 1", " 1"), ("1 ", "1 "),
                  ("", ""), ("1x", "1x"), ("1_0", "1_0"), ("1.0", "1.0"), ("0x1", "0x1"), ("1e3", "1e3"),
                  ("\u0661", "\\u0661"), ("1\u0663", "1\\u0663"), ("\uff11", "\\uff11"), ("\u00b9", "\\xb9"))
        cases += [(f"README.md\t{count}\tkeep\tLicence:", f"the count '{shown}' {BAD_COUNT}") for count, shown in counts]
        for row, cause in cases:
            with self.subTest(row=row):
                self.repo.add_row(row)
                self.refused(f"{ALLOWLIST}:3: malformed row: {cause}")

    def test_repeat_of_a_malformed_row(self):
        self.control()
        self.repo.set_rows(ROW, "README.md\t0\tkeep\tLicence:", "README.md\t1\tkeep\tLicence:")
        self.refused(f"{ALLOWLIST}:3: malformed row: the count '0' {BAD_COUNT}",
                     also=(f"{ALLOWLIST}:4: malformed row: it repeats the path and marker of row 3",))

    def test_shown_fields_are_escaped_once(self):
        self.control()
        name = "a\x1bb\\c\u00e9\u2028.md"
        shown = "a\\x1bb\\\\c\\xe9\\u2028.md"
        with self.subTest(field="path"):
            self.repo.track(name, b"CC BY-SA 4.0\n")
            self.refused(f"{PREFIX}{shown}:1: names a licence term and no allowlist row claims it")
            self.passes(f"README.md:1\n{shown}:1\ntotal: 2 lines in 2 files\n", "--list")
            self.repo.git("rm", "-q", "-f", "--", name)
            self.control()
        rows = (
            ("README.md\t1\tkeep\tx\x1by",
             f"{PREFIX}README.md: allowlist row 3 (keep, marker 'x\\x1by') is stale: it claims 0 line(s), "
             "the allowlist says 1"),
            ("README.md\t1\x1b\tkeep\tLicence:", f"{PREFIX}{ALLOWLIST}:3: malformed row: the count '1\\x1b' {BAD_COUNT}"),
            ("README.md\t1\tke\x1bep\tLicence:",
             f"{PREFIX}{ALLOWLIST}:3: malformed row: the owner 'ke\\x1bep' is none of unit-2, unit-3, keep"),
            ("mi\x1bss.md\t1\tkeep\tLicence:", f"{PREFIX}{ALLOWLIST}:3: malformed row: mi\\x1bss.md is not a tracked path"),
        )
        for row, line in rows:
            with self.subTest(row=row):
                self.repo.add_row(row)
                self.refused(line)

    def test_missing_allowlist(self):
        self.control()
        (self.repo.root / ALLOWLIST).unlink()
        # The allowlist is read twice, as a named exception and as the allowlist, and with no row
        # left the README.md line is unclaimed.
        self.refused("the allowlist cannot be read",
                     also=(f"{ALLOWLIST}: cannot read the tracked file: FileNotFoundError",
                           f"{ALLOWLIST}: cannot read the tracked file: FileNotFoundError",
                           "README.md:3: names a licence term and no allowlist row claims it"))

    def test_allowlist_not_utf8(self):
        self.control()
        self.repo.write(ALLOWLIST, (HEADER + ROW + "\n# \xff\n").encode("latin-1"))
        self.repo.git("add", ALLOWLIST)
        # With the allowlist refused, no row claims the README.md line.
        self.refused("the allowlist is not UTF-8",
                     also=("README.md:3: names a licence term and no allowlist row claims it",))

    def test_tracked_file_deleted_from_the_work_tree(self):
        self.control()
        self.repo.track("gone.md", b"no term\n")
        (self.repo.root / "gone.md").unlink()
        self.refused("gone.md: cannot read the tracked file: FileNotFoundError")

    def test_tracked_symbolic_link(self):
        self.control()
        os.symlink("README.md", self.repo.root / "link.md")
        self.repo.git("add", "link.md")
        self.refused("link.md: tracked with mode 120000")

    def test_work_tree_symbolic_link_at_a_regular_entry(self):
        self.control()
        outside = self.repo.base / "outside.md"
        outside.write_bytes(README + b"ShareAlike\n")
        (self.repo.root / "README.md").unlink()
        os.symlink(outside, self.repo.root / "README.md")
        self.refused(f"{PREFIX}README.md: the tracked path is not a regular file in the work tree",
                     out_text=PREFIX + "checked: 0 lines in 0 files; 1 problem(s)\n")

    def test_work_tree_fifo_at_a_regular_entry(self):
        self.control()
        (self.repo.root / "README.md").unlink()
        os.mkfifo(self.repo.root / "README.md")
        self.refused(f"{PREFIX}README.md: the tracked path is not a regular file in the work tree",
                     out_text=PREFIX + "checked: 0 lines in 0 files; 1 problem(s)\n")

    def test_tracked_submodule_entry(self):
        self.control()
        self.repo.git("update-index", "--add", "--cacheinfo", f"160000,{'1' + '0' * 39},sub")
        self.refused("sub: tracked with mode 160000")

    def test_folder_in_place_of_a_tracked_file(self):
        self.control()
        self.repo.track("place.md", b"no term\n")
        (self.repo.root / "place.md").unlink()
        (self.repo.root / "place.md").mkdir()
        self.refused("place.md: the tracked path is not a regular file in the work tree")

    def test_descriptor_that_is_not_a_regular_file(self):
        os.mkfifo(self.repo.root / "fifo")
        self.assertEqual(self.probe("descriptor", "fifo", "README.md"),
                         {"data": None, "problems": ["fifo: the tracked path is not a regular file in the work tree"]})

    def test_symbolic_link_after_the_lstat_check(self):
        os.symlink("README.md", self.repo.root / "link.md")
        result = self.probe("swap", "link.md", "README.md")
        self.assertIsNone(result["data"])
        self.assertEqual(len(result["problems"]), 1, result)
        self.assertTrue(result["problems"][0].startswith(
            f"link.md: cannot read the tracked file: OSError: [Errno {errno.ELOOP}]"), result)

    def test_read_error(self):
        self.assertEqual(self.probe("read-error", "README.md", "README.md"),
                         {"data": None, "problems": [f"README.md: cannot read the tracked file: OSError: [Errno "
                                                     f"{errno.EIO}] {os.strerror(errno.EIO)}"]})

    def test_unmerged_entry_at_each_stage(self):
        self.control()
        blob = self.repo.git("hash-object", "-w", "README.md").strip()
        for stage in ("1", "2", "3"):
            with self.subTest(stage=stage):
                info = f"0 {'0' * 40}\tREADME.md\n100644 {blob} {stage}\tREADME.md\n".encode("ascii")
                self.repo.git("update-index", "--index-info", stdin=info)
                self.refused(f"{PREFIX}README.md: an unmerged index entry (stage {stage}), so the gate cannot tell "
                             "which version is tracked")
                self.repo.git("add", "README.md")
                self.control()

    def test_named_exception_untracked(self):
        self.control()
        for path in NAMED_EXCEPTIONS:
            with self.subTest(path=path):
                self.repo.git("rm", "--cached", "-q", path)
                self.refused(f"{PREFIX}{path}: a named exception that git does not track")
                self.repo.git("add", path)
                self.control()

    def test_named_exception_without_a_matching_line(self):
        self.control()
        contents = {ALLOWLIST: (HEADER + "README.md\t1\tkeep\tLicence:\n").encode("utf-8")}
        for path in NAMED_EXCEPTIONS:
            with self.subTest(path=path):
                before = (self.repo.root / path).read_bytes()
                self.repo.track(path, contents.get(path, b"print('no term')\n"))
                self.refused(f"{PREFIX}{path}: a named exception that holds no matching line")
                self.repo.track(path, before)
                self.control()

    def test_not_a_git_repository(self):
        self.control()
        shutil.rmtree(self.repo.root / ".git")
        self.refused(f"{PREFIX}git ls-files exited 128, so no tracked file can be listed: fatal: not a git repository")

    def test_git_cannot_run(self):
        self.control()
        empty = self.repo.base / "no-commands"
        empty.mkdir()
        self.refused(f"{PREFIX}cannot run git ls-files, so no tracked file can be listed: FileNotFoundError",
                     env=dict(self.repo.env, PATH=str(empty)))

    def test_empty_index(self):
        self.control()
        self.repo.git("rm", "-r", "--cached", "-q", ".")
        self.refused("git ls-files lists no tracked file")

    def test_list_fails_on_an_unreadable_file(self):
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")
        os.symlink("README.md", self.repo.root / "link.md")
        self.repo.git("add", "link.md")
        self.refused("link.md: tracked with mode 120000", "--list")

    def test_list_fails_on_a_named_exception(self):
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")
        self.repo.git("rm", "--cached", "-q", ALLOWLIST)
        self.refused(f"{ALLOWLIST}: a named exception that git does not track", "--list")

    def test_file_content_is_data(self):
        self.control()
        marker = self.repo.base / "ran"
        name = "$(touch ran);x.md"
        self.repo.track(name, f"`touch {marker}` $(touch {marker}) --root / CC BY-SA 4.0\n".encode("utf-8"))
        self.refused("$(touch ran);x.md:1: names a licence term and no allowlist row claims it")
        self.assertFalse(marker.exists(), "a file's name or content ran as a command")

    def test_unreadable_file(self):
        self.control()
        path = self.repo.root / "README.md"
        path.chmod(0)
        self.addCleanup(path.chmod, 0o644)
        try:
            with open(path, "rb"):
                readable = True
        except PermissionError:
            readable = False
        if readable:
            self.skipTest("this process can read a file of mode 000, as root can")
        # The README.md row is not reported stale, since the lines of a file that cannot be read are unknown.
        self.refused("README.md: cannot read the tracked file: PermissionError")


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    sys.exit(0 if result.wasSuccessful() else 1)
