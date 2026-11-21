#!/usr/bin/env python3
"""Tests for tools/check-licence-names.py, the licence-name gate.

Each case builds a throwaway git repository in a temporary folder (git init and git add; no commit
and no identity are needed, since the gate reads the index and the work tree). The repository
holds the gate's 3 files: a copy of the gate and of this test from this test's own folder, and an
allowlist with 1 row, README.md, 1, keep, CC BY-SA 4.0, for README.md, whose 1 matching line holds
that marker. The gate runs as a separate process, python3 -I with --root, with the git
configuration of the machine and of the user left out and the search for a repository stopped at
the temporary folder, so the result depends on the case alone.

Every refusal case first runs the gate on the unchanged repository, a control that must exit 0,
then makes 1 change and requires exit 1 and a problem line that names the cause. So each case fails
when the gate does not refuse the change, and also when the gate refuses the unchanged repository.
The controls of their own: the unchanged repository reports 1 line in 1 file and 0 problems;
--list prints README.md:1 and the total; a file whose lines end in carriage returns only is 1 line;
an untracked file that names a term is not read. A case for a file whose mode the runner can still
read after chmod 000, as root can, is skipped and says so.

Exit 0 when every case passes; 1 otherwise.
"""

from __future__ import annotations

import os
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
ROW = "README.md\t1\tkeep\tCC BY-SA 4.0"
HEADER = "# path\tcount\towner\tmarker\n"
README = b"# Example\n\nLicence: CC BY-SA 4.0\n"


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

    def add_row(self, row: str) -> None:
        self.write(ALLOWLIST, (HEADER + ROW + "\n" + row + "\n").encode("utf-8"))
        self.git("add", ALLOWLIST)

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

    def control(self):
        code, out, err = self.repo.gate()
        self.assertEqual((code, err), (0, ""), f"the unchanged repository must pass:\n{out}{err}")
        self.assertIn("checked: 1 lines in 1 files; 0 problem(s)", out)

    def refused(self, cause: str, *args: str, env: dict | None = None):
        """Exit 1 with a problem line on standard error that holds cause."""
        code, out, err = self.repo.gate(*args, env=env)
        self.assertEqual(code, 1, f"the gate must refuse this change:\n{out}{err}")
        lines = [line for line in err.splitlines() if line.startswith("check-licence-names: ")]
        self.assertTrue(any(cause in line for line in lines), f"no problem line names {cause!r}:\n{err}")


class Controls(GateCase):
    def test_unchanged_repository_passes(self):
        self.control()

    def test_list_prints_each_file_and_the_total(self):
        code, out, err = self.repo.gate("--list")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines(), ["README.md:1", "total: 1 lines in 1 files"])

    def test_carriage_returns_alone_do_not_end_a_line(self):
        self.repo.write("notes.txt", b"CC BY-SA 4.0\rBY-SA again\rCC BY-SA 4.0\r")
        self.repo.git("add", "notes.txt")
        self.repo.add_row("notes.txt\t1\tkeep\tCC BY-SA 4.0")
        code, out, err = self.repo.gate()
        self.assertEqual((code, err), (0, ""), out + err)
        self.assertIn("checked: 2 lines in 2 files; 0 problem(s)", out)

    def test_untracked_file_is_not_read(self):
        self.repo.write("untracked.md", b"ShareAlike\n")
        self.control()


class Refusals(GateCase):
    def test_unclaimed_line_in_another_file(self):
        self.control()
        self.repo.write("other.md", b"CC BY-SA 4.0\n")
        self.repo.git("add", "other.md")
        self.refused("other.md:1: names a licence term and no allowlist row claims it")

    def test_each_term_in_another_letter_case(self):
        self.control()
        for number, term in enumerate((b"by-sa", b"SHAREALIKE", b"creative COMMONS"), 1):
            with self.subTest(term=term):
                name = f"case{number}.md"
                self.repo.write(name, b"plain\n" + term + b"\n")
                self.repo.git("add", name)
                self.refused(f"{name}:2: names a licence term and no allowlist row claims it")

    def test_line_matching_no_marker_of_its_file(self):
        self.control()
        self.repo.write("README.md", README + b"ShareAlike\n")
        self.repo.git("add", "README.md")
        self.refused("README.md:4: names a licence term and no allowlist row claims it")

    def test_removed_line_leaves_a_stale_row(self):
        self.control()
        self.repo.write("README.md", b"# Example\n")
        self.repo.git("add", "README.md")
        self.refused("is stale: it claims 0 line(s), the allowlist says 1")

    def test_count_off_by_one(self):
        self.control()
        self.repo.write(ALLOWLIST, (HEADER + "README.md\t2\tkeep\tCC BY-SA 4.0\n").encode("utf-8"))
        self.repo.git("add", ALLOWLIST)
        self.refused("is stale: it claims 1 line(s), the allowlist says 2")

    def test_two_markers_on_one_line(self):
        self.control()
        self.repo.add_row("README.md\t1\tunit-3\tBY-SA 4.0")
        self.refused("README.md:3: holds the markers of allowlist rows")

    def test_malformed_rows(self):
        self.control()
        cases = (
            ("README.md\t1\tkeep", "it has 3 tab-separated field(s), not 4"),
            ("README.md\t1\tkeep\tLicence:\tmore", "it has 5 tab-separated field(s), not 4"),
            ("README.md\t1\tkeep\tLicence:\r", "it holds a carriage return"),
            ("README.md\t0\tkeep\tLicence:", "the count '0' is not a number from 1 with no leading zero"),
            ("README.md\t01\tkeep\tLicence:", "the count '01' is not a number from 1 with no leading zero"),
            ("README.md\t1\tunit-9\tLicence:", "the owner 'unit-9' is none of unit-2, unit-3, keep"),
            ("README.md\t1\tkeep\t", "the marker is empty"),
            (ROW, "it repeats the path and marker of row 2"),
            ("missing.md\t1\tkeep\tLicence:", "missing.md is not a tracked path"),
            ("tools/check-licence-names.py\t1\tkeep\tLicence:", "tools/check-licence-names.py is a named exception"),
        )
        for row, cause in cases:
            with self.subTest(row=row):
                self.repo.add_row(row)
                self.refused(f"{ALLOWLIST}:3: malformed row: {cause}")

    def test_missing_allowlist(self):
        self.control()
        (self.repo.root / ALLOWLIST).unlink()
        self.refused("the allowlist cannot be read")

    def test_allowlist_not_utf8(self):
        self.control()
        self.repo.write(ALLOWLIST, (HEADER + ROW + "\n# \xff\n").encode("latin-1"))
        self.repo.git("add", ALLOWLIST)
        self.refused("the allowlist is not UTF-8")

    def test_tracked_file_deleted_from_the_work_tree(self):
        self.control()
        self.repo.write("gone.md", b"no term\n")
        self.repo.git("add", "gone.md")
        (self.repo.root / "gone.md").unlink()
        self.refused("gone.md: cannot read the tracked file")

    def test_tracked_symbolic_link(self):
        self.control()
        os.symlink("README.md", self.repo.root / "link.md")
        self.repo.git("add", "link.md")
        self.refused("link.md: tracked with mode 120000")

    def test_tracked_submodule_entry(self):
        self.control()
        self.repo.git("update-index", "--add", "--cacheinfo", f"160000,{'1' + '0' * 39},sub")
        self.refused("sub: tracked with mode 160000")

    def test_folder_in_place_of_a_tracked_file(self):
        self.control()
        self.repo.write("place.md", b"no term\n")
        self.repo.git("add", "place.md")
        (self.repo.root / "place.md").unlink()
        (self.repo.root / "place.md").mkdir()
        self.refused("place.md: the tracked path is not a regular file in the work tree")

    def test_unmerged_entry(self):
        self.control()
        blob = self.repo.git("hash-object", "-w", "README.md").strip()
        info = (f"0 {'0' * 40}\tREADME.md\n100644 {blob} 1\tREADME.md\n"
                f"100644 {blob} 2\tREADME.md\n").encode("ascii")
        self.repo.git("update-index", "--index-info", stdin=info)
        self.refused("README.md: an unmerged index entry (stage 1)")

    def test_gate_file_untracked(self):
        self.control()
        self.repo.git("rm", "--cached", "-q", "tools/test-check-licence-names.py")
        self.refused("tools/test-check-licence-names.py: a named exception that git does not track")

    def test_gate_file_without_a_matching_line(self):
        self.control()
        self.repo.write("tools/test-check-licence-names.py", b"print('no term')\n")
        self.repo.git("add", "tools/test-check-licence-names.py")
        self.refused("tools/test-check-licence-names.py: a named exception that holds no matching line")

    def test_not_a_git_repository(self):
        self.control()
        shutil.rmtree(self.repo.root / ".git")
        self.refused("so no tracked file can be listed")

    def test_git_cannot_run(self):
        self.control()
        empty = self.repo.base / "no-commands"
        empty.mkdir()
        self.refused("cannot run git ls-files", env=dict(self.repo.env, PATH=str(empty)))

    def test_empty_index(self):
        self.control()
        self.repo.git("rm", "-r", "--cached", "-q", ".")
        self.refused("git ls-files lists no tracked file")

    def test_list_fails_on_an_unreadable_file(self):
        code, out, err = self.repo.gate("--list")
        self.assertEqual(code, 0, out + err)
        os.symlink("README.md", self.repo.root / "link.md")
        self.repo.git("add", "link.md")
        self.refused("link.md: tracked with mode 120000", "--list")

    def test_file_content_is_data(self):
        self.control()
        marker = self.repo.base / "ran"
        name = "$(touch ran);x.md"
        self.repo.write(name, f"`touch {marker}` $(touch {marker}) --root / CC BY-SA 4.0\n".encode("utf-8"))
        self.repo.git("add", "--", name)
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
        self.refused("README.md: cannot read the tracked file: PermissionError")


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    sys.exit(0 if result.wasSuccessful() else 1)
