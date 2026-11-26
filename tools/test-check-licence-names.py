#!/usr/bin/env python3
"""Tests for tools/check-licence-names.py, the licence-name gate.

Each case builds a throwaway git repository in a temporary folder (git init and git add; no commit
and no identity are needed, since the gate reads the index and the work tree). The repository
holds the gate's 3 files: a copy of the gate and of this test from this test's own folder, and an
allowlist with 1 row, README.md, 1, keep, CC BY-SA 4.0, for README.md, whose 1 matching line holds
that marker. The gate runs as a separate process, python3 -I with --root, in 1 case through a
python3 -I launcher that first removes os.O_NOFOLLOW. The gate, git and the
probe process below each run in the temporary folder and get an environment built from fixed
values alone, so no variable of the caller's environment, such as XDG_CONFIG_HOME, HOME or a
variable whose name starts with GIT_, is passed on to them: PATH, the folder of the git found on
the caller's PATH; HOME, an empty folder in the temporary folder; the git configuration of the
machine and of the user left out (GIT_CONFIG_NOSYSTEM=1 and GIT_CONFIG_GLOBAL set to the null
device); git's messages in the C locale (LC_ALL=C); and the search for a repository stopped at
the temporary folder (GIT_CEILING_DIRECTORIES). git init takes no template (--template=), so no
hook, exclude file or description of a template reaches the repository. So the result depends on
the case alone. The caller's environment is read for 2 things only, and the tests build settings
from them: where git is, whose folder is the PATH of each process, and where Python's tempfile
makes the temporary folder, which holds HOME and the repository. The folder in which a case builds
its repository, the temporary folder or, in 2 cases, a folder named case inside it, is the value
of GIT_CEILING_DIRECTORIES and the working folder of each process that the case starts; the git
that the gate starts works in the root folder that the gate opened. Each stand-in git below and
each probe process records the environment that it gets, and the case requires it to equal those
values exactly.

Every refusal case that runs the gate first runs it on the unchanged repository, a control that
must exit 0 and print exactly the summary line, or for a case of --list exactly the list. It then
makes the change that it tests, to the repository or to the PATH that the gate is given; a change
can take more than 1 step, such as tracking a file and then deleting it from the work tree, or
tracking 2 files. It then requires exit 1; problem lines that match, 1 for 1, the cause and any
consequence the case names, each consequence with the reason it follows, each matched as a part
of its line, with no problem line left over; and on standard output exactly 1 summary line whose
problem count is the number of problem lines, or for --list only path:count lines and then 1
total line. Each subtest makes its change to the unchanged repository, since it undoes or
overwrites the change of the subtest before it. So each case fails when the gate does not refuse
the change, when it names another cause or an extra problem, and when it refuses the unchanged
repository. Every run of the gate must also write nothing outside printable ASCII, so a control
byte that reaches the output unescaped, in any field, fails the case.

The controls of their own: the unchanged repository reports 1 line in 1 file and 0 problems;
--list prints README.md:1 and the total, and does not parse the allowlist; a line ends only at a
line feed, so carriage returns, other control bytes, binary and non-UTF-8 bytes stay in their
line; near misses of the 3 terms match nothing; an untracked file is not read; an executable
tracked file is read like any other; a marker is literal text, so a marker that a regular
expression would read in another way claims the line that holds it; an unknown option exits 2;
run without --root, the gate checks the repository that holds it, both with and without --list;
--list passes with an allowlist that is not UTF-8; git settings in the caller's environment that
would ignore README.md or point git at another repository change no result; GIT_DIR,
GIT_INDEX_FILE and GIT_COMMON_DIR in the gate's own environment, which would point git at another
repository or index, change no result; and git init leaves .git with no hook, exclude file or
description, which only a template gives, even when GIT_TEMPLATE_DIR names a template that a
git init without --template= copies.

9 cases call the gate's file reader in a separate python3 -I process that loads the gate by file
path: 1 reads a regular file as a control; 6 replace os.lstat or os.fdopen in that process alone
to reach an open descriptor that is not a regular file, a symbolic link that appears after the
lstat check, a symbolic link to a folder outside the work tree and a file, each in place of a
parent after the lstat check, and a read error, once with the system's text and once with a text
of whitespace, characters outside printable ASCII, a backslash and more than 300 characters; 1
replaces os.open to move a folder at depth 1, a folder at depth 2 and a file out of the work
tree, each just after the gate opens it; and 1 removes os.O_NOFOLLOW. The process opens the root
with the gate's own opener. These reach what a race or a failing disk could cause. The problem
line of that last text is compared whole: the text must come out as 1 line, cut to 300
characters and then escaped. A parent link
sits at depth 1 and at depth 2, and each parent case runs once with os.O_DIRECTORY and once with
it removed, as on a system without it, so the gate must open each parent without following a
link, and must refuse a parent that is not a folder when it opens it and, without
os.O_DIRECTORY, when it checks the folder that it opened. A parent link must be refused with the
error that opening a link without following it gives, NotADirectoryError with os.O_DIRECTORY and
ELOOP without it, while a real folder at the same depth, read the same way, gives its file's
bytes. 7 cases give the
gate a stand-in git, a Python script alone on its PATH: 1 exits 3 with a message like that text;
1 lists the repository's 4 files and paths that are not plain relative, 1 of them leading out of
the work tree, to the gate and to --list; 1 lists the repository's 4 files and, before it exits,
replaces the root with a symbolic link to another folder and records its working folder, to the
gate and to --list; and 4 list 3 entries that cannot be read, 1 with no tab, 1 with 2 fields
before its tab and 1 with 4, to the gate and to --list, 2 beside the repository's 4 files and 2
alone. The problem line of the first, compared whole, must show the message the
same way. A case for a file whose mode the runner can still read after chmod 000, as root can, is
skipped and says so.

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
from unittest import mock

HERE = Path(__file__).resolve().parent
# Where git is, found once on the caller's PATH: with the temporary folder that tempfile picks, the
# only value that the tests take from the caller's environment. Its folder is the PATH of each process.
FOUND_GIT = shutil.which("git")
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
# An error's text and git's message of whitespace (tab, carriage return, line feed, vertical tab,
# 0x1c, U+00A0, U+2028), an escape byte, non-ASCII letters, a backslash and more than 300 characters.
ODD_TAIL = "\t\x1b[31m\r\n  d\xe9j\xe0 \\ vu\x0b\x1c\xa0\N{LINE SEPARATOR}" + "\xe9" * 400
ODD_SHOWN = "\\x1b[31m d\\xe9j\\xe0 \\\\ vu "
ODD_RAW_LENGTH = 16
# What a stand-in git lists: the 4 files of the repository, as git ls-files --stage -z would, then
# an entry with no tab, an entry with 2 fields before its tab and an entry with 4.
LISTING = b"".join(b"100644 " + b"0" * 40 + b" 0\t" + path.encode("ascii") + b"\0"
                   for path in ("README.md", *NAMED_EXCEPTIONS))
BAD_ENTRIES = (b"100644 n\x1bo 0\0" + b"100644 bad\tmi\x1bss.md\0"
               + b"100644 " + b"0" * 40 + b" 0 more\tsur\x1bplus.md\0")
BAD_ENTRY_PROBLEMS = (PREFIX + "git ls-files gave an entry that cannot be read: 100644 n\\x1bo 0",
                      PREFIX + "git ls-files gave an entry that cannot be read: 100644 bad\\x09mi\\x1bss.md",
                      PREFIX + "git ls-files gave an entry that cannot be read: 100644 " + "0" * 40
                      + " 0 more\\x09sur\\x1bplus.md")
NOT_PLAIN = " the tracked path is not a regular file in the work tree, since it is not a plain relative path"


def escaped(text: str) -> str:
    """text as the gate's docstring says that a field is shown, for a path that the temporary folder
    fixes, whose characters the case cannot write out; the fixed escapes are written out in full."""
    out = []
    for char in text:
        code = ord(char)
        if char == "\\":
            out.append("\\\\")
        elif " " <= char <= "~":
            out.append(char)
        else:
            out.append(f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}" if code < 0x10000 else f"\\U{code:08x}")
    return "".join(out)


PROBE = """
import errno, importlib.util, json, os, sys
ODD_ERROR = """ + repr(ODD_TAIL) + """
from pathlib import Path
environment = dict(os.environ)
gate_path, mode, root, name, decoy = sys.argv[1:6]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("gate", gate_path)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
real_lstat, real_fdopen = os.lstat, os.fdopen
if mode in ("descriptor", "swap"):
    os.lstat = lambda path, *args, **kwargs: real_lstat(decoy)
if mode in ("parent", "parent-bare"):
    # Each part before the last passes the lstat check as the folder decoy does.
    last = name.rsplit("/", 1)[-1]
    os.lstat = lambda path, *args, **kwargs: real_lstat(path, *args, **kwargs) if path == last else real_lstat(decoy)
if mode == "parent-bare" and hasattr(os, "O_DIRECTORY"):
    del os.O_DIRECTORY
if mode in ("read-error", "odd-error"):
    text = os.strerror(errno.EIO) if mode == "read-error" else ODD_ERROR
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
            raise OSError(errno.EIO, text)
    os.fdopen = lambda *args, **kwargs: Failing(real_fdopen(*args, **kwargs))
if mode == "no-nofollow":
    del os.O_NOFOLLOW
if mode == "move":
    # Just after the gate opens the entry decoy, inside a folder, it moves to the folder away beside
    # the root, and the file that the gate is about to read gets bytes that name a term.
    real_open, moved = os.open, []
    def opening(path, *args, **kwargs):
        fd = real_open(path, *args, **kwargs)
        if not moved and kwargs.get("dir_fd") is not None and path == os.path.basename(decoy):
            moved.append(path)
            away = Path(root).parent / "away" / os.path.basename(decoy)
            os.rename(decoy, away)
            with open(away / os.path.relpath(os.path.join(root, name), decoy), "r+b") as moved_file:
                moved_file.write(b"OUTSIDE BYTES CC BY-SA 4.0\\n")
        return fd
    os.open = opening
problems = []
descriptor = gate.open_root(Path(root), problems)
if descriptor is None:
    # As a caller that did not use the gate's opener would, so the reader's own refusal is reached too.
    descriptor = os.open(root, os.O_RDONLY)
data = gate.read_file(descriptor, name, problems)
os.close(descriptor)
print(json.dumps({"data": None if data is None else data.decode("latin-1"), "problems": problems,
                  "environment": environment}))
"""
# Runs the gate, named by its first argument, after it removes os.O_NOFOLLOW, as on a system without it.
WITHOUT_NOFOLLOW = ("import os, runpy, sys\ndel os.O_NOFOLLOW\nsys.argv = sys.argv[1:]\n"
                    "runpy.run_path(sys.argv[0], run_name='__main__')\n")
NO_NOFOLLOW = "this system has no O_NOFOLLOW, so no path can be opened without following a symbolic link"


class Repo:
    """A throwaway git repository of 4 files: the gate's 3 files, the allowlist among them, and README.md."""

    def __init__(self, base: Path):
        self.base = base
        self.root = base / "repo"
        (self.root / "tools").mkdir(parents=True)
        shutil.copyfile(GATE, self.root / "tools" / "check-licence-names.py")
        shutil.copyfile(SELF, self.root / "tools" / "test-check-licence-names.py")
        self.write(ALLOWLIST, (HEADER + ROW + "\n").encode("utf-8"))
        self.write("README.md", README)
        if FOUND_GIT is None:
            raise AssertionError("no git is on the caller's PATH")
        home = base / "home"
        home.mkdir()
        # Built from fixed values alone, so no variable of the caller's environment, such as
        # XDG_CONFIG_HOME, whose git/ignore git would read, HOME, GIT_DIR or GIT_CONFIG_COUNT,
        # reaches git, the gate or the probe.
        self.env = {
            "PATH": str(Path(FOUND_GIT).parent),
            "HOME": str(home),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CEILING_DIRECTORIES": str(base),
            "LC_ALL": "C",
        }
        self.git("init", "-q", "--template=")
        self.git("add", "-A")

    def write(self, rel: str, data: bytes) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def git(self, *args: str, stdin: bytes = b"") -> str:
        done = subprocess.run(["git", "-C", str(self.root), *args], input=stdin, capture_output=True,
                              env=self.env, cwd=self.base, timeout=60)
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

    def track_executable(self, rel: str, data: bytes) -> None:
        """Track rel as an executable file, and fail unless git lists it with mode 100755."""
        self.write(rel, data)
        (self.root / rel).chmod(0o755)
        self.git("add", "--", rel)
        listed = self.git("ls-files", "--stage", "--", rel)
        if not listed.startswith("100755 "):
            raise AssertionError(f"git does not track {rel} as executable: {listed!r}")

    def gate(self, *args: str, env: dict | None = None, default_root: bool = False, without_nofollow: bool = False):
        # With default_root, the copy of the gate in the repository runs without --root.
        command = ([str(self.root / "tools" / "check-licence-names.py")] if default_root
                   else [str(GATE), "--root", str(self.root)])
        if without_nofollow:
            command = ["-c", WITHOUT_NOFOLLOW, *command]
        done = subprocess.run([sys.executable, "-I", *command, *args], capture_output=True, env=env or self.env,
                              cwd=self.base, stdin=subprocess.DEVNULL, timeout=120)
        return (done.returncode, done.stdout.decode("utf-8", "replace"),
                done.stderr.decode("utf-8", "replace"))


class GateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Repo(Path(self.tmp.name))
        self.stand_in = None

    def built_environment(self, path: str) -> dict:
        """The environment that each process of the case must get, with path as its PATH. It is
        written out here apart from Repo, so a change to the environment that Repo builds fails."""
        return {"PATH": path, "HOME": str(self.repo.base / "home"), "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CEILING_DIRECTORIES": str(self.repo.base), "LC_ALL": "C"}

    def run_gate(self, *args: str, env: dict | None = None, default_root: bool = False, without_nofollow: bool = False):
        code, out, err = self.repo.gate(*args, env=env, default_root=default_root, without_nofollow=without_nofollow)
        shown = [char for char in out + err if char != "\n" and not " " <= char <= "~"]
        self.assertEqual(shown, [], f"the output holds characters outside printable ASCII:\n{out}{err}")
        if env is not None and env is self.stand_in:
            record = self.repo.base / "git-environment.json"
            self.assertTrue(record.exists(), "the gate did not run the stand-in git")
            given = json.loads(record.read_text(encoding="utf-8"))
            record.unlink()
            self.assertEqual(given, self.built_environment(str(self.repo.base / "fake-git")),
                             "the stand-in git got another environment")
        return code, out, err

    def passes(self, out_text: str = CONTROL_OUT, *args: str, env: dict | None = None, default_root: bool = False):
        code, out, err = self.run_gate(*args, env=env, default_root=default_root)
        self.assertEqual((code, err), (0, ""), f"the gate must pass:\n{out}{err}")
        self.assertEqual(out, out_text)

    def control(self):
        self.passes()

    def refused(self, cause: str, *args: str, env: dict | None = None, also: tuple = (), out_text: str = "",
                without_nofollow: bool = False):
        """Exit 1 and problem lines that are exactly cause and also, each matched as a substring once."""
        code, out, err = self.run_gate(*args, env=env, without_nofollow=without_nofollow)
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
        return err

    def fake_git(self, stdout: bytes, stderr: bytes, code: int, then: str = "") -> dict:
        """The gate's environment with a stand-in git alone on PATH: a script that records the
        environment it gets, writes stdout and stderr, runs the Python lines then and exits with code,
        whatever its arguments."""
        folder = self.repo.base / "fake-git"
        folder.mkdir()
        script = folder / "git"
        record = self.repo.base / "git-environment.json"
        script.write_text(f"#!{sys.executable} -I\nimport json, os, sys\n"
                          f"with open({str(record)!r}, 'w', encoding='utf-8') as out:\n"
                          "    json.dump(dict(os.environ), out)\n"
                          f"sys.stdout.buffer.write({stdout!r})\n"
                          f"sys.stderr.buffer.write({stderr!r})\n{then}sys.exit({code})\n", encoding="utf-8")
        script.chmod(0o755)
        self.stand_in = dict(self.repo.env, PATH=str(folder))
        return self.stand_in

    def probe(self, mode: str, name: str, decoy: str):
        done = subprocess.run([sys.executable, "-I", "-c", PROBE, str(GATE), mode, str(self.repo.root), name,
                               str(self.repo.root / decoy)], capture_output=True, stdin=subprocess.DEVNULL,
                              env=self.repo.env, cwd=self.repo.base, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
        result = json.loads(done.stdout)
        self.assertEqual(result.pop("environment"), self.built_environment(str(Path(FOUND_GIT).parent)),
                         "the probe process got another environment")
        return result


class Controls(GateCase):
    def test_unchanged_repository_passes(self):
        self.control()

    def test_list_prints_each_file_and_the_total(self):
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")

    def test_list_does_not_parse_the_allowlist(self):
        self.repo.set_rows("README.md\t5\tkeep\tCC BY-SA 4.0", "README.md\t0\tkeep")
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")

    def test_list_passes_with_an_allowlist_that_is_not_utf8(self):
        self.repo.write(ALLOWLIST, (HEADER + ROW + "\n# \xff\n").encode("latin-1"))
        self.repo.git("add", ALLOWLIST)
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")

    def test_default_root_is_the_repository_that_holds_the_gate(self):
        # Both launchers run the gate with no --root, so its default root is the repository of its own file.
        self.passes(default_root=True)
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list", default_root=True)

    def test_marker_is_literal_text(self):
        # As a regular expression, [CC] BY-SA would need a C before " BY-SA", which this line does not hold.
        self.repo.track("bracket.md", b"Licence: [CC] BY-SA\n")
        self.repo.add_row("bracket.md\t1\tkeep\t[CC] BY-SA")
        self.passes(PREFIX + "checked: 2 lines in 2 files; 0 problem(s)\n")

    def test_git_location_settings_of_the_gate_change_no_result(self):
        # Each setting points git at an index or repository whose listing differs from the root's: a copy
        # of the index and of .git taken while extra.md, whose line no row claims, was tracked, and a
        # folder that is not a repository. If git used it, the gate would report extra.md or fail.
        self.repo.track("extra.md", b"CC BY-SA 4.0\n")
        shutil.copyfile(self.repo.root / ".git" / "index", self.repo.base / "other-index")
        shutil.copytree(self.repo.root / ".git", self.repo.base / "other-git")
        self.repo.git("rm", "-q", "-f", "--", "extra.md")
        self.control()
        settings = {"GIT_INDEX_FILE": str(self.repo.base / "other-index"), "GIT_DIR": str(self.repo.base / "other-git"),
                    "GIT_COMMON_DIR": str(self.repo.base / "home")}
        for name, value in settings.items():
            with self.subTest(setting=name):
                env = dict(self.repo.env, **{name: value})
                self.passes(env=env)
                self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list", env=env)

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

    def test_executable_file_is_read(self):
        self.repo.track_executable("tool.sh", b"#!/bin/sh\n# CC BY-SA 4.0\n")
        self.repo.add_row("tool.sh\t1\tkeep\tCC BY-SA 4.0")
        self.passes(PREFIX + "checked: 2 lines in 2 files; 0 problem(s)\n")
        self.passes("README.md:1\ntool.sh:1\ntotal: 2 lines in 2 files\n", "--list")

    def test_unknown_option_exits_2(self):
        code, out, err = self.run_gate("--bogus")
        self.assertEqual((code, out), (2, ""), err)
        self.assertIn("unrecognized arguments: --bogus", err)

    def test_read_file_returns_a_regular_file(self):
        self.assertEqual(self.probe("plain", "README.md", "README.md"),
                         {"data": README.decode("latin-1"), "problems": []})

    def test_root_replaced_while_git_lists(self):
        # The stand-in git runs after the gate opens the root. It moves the root folder aside, puts a
        # link in its place to a folder whose README.md holds a line that no row claims, and records
        # its working folder. A gate that opened the root again by its path would read that folder and
        # report the line; one that ran git at the root's path would give git another working folder.
        self.control()
        replacement, held = self.repo.base / "replacement", self.repo.base / "held"
        shutil.copytree(self.repo.root, replacement, ignore=shutil.ignore_patterns(".git"))
        (replacement / "README.md").write_bytes(README + b"ShareAlike\n")
        record = self.repo.base / "git-folder.txt"
        swap = (f"import os\nos.rename({str(self.repo.root)!r}, {str(held)!r})\n"
                f"os.symlink({str(replacement)!r}, {str(self.repo.root)!r})\n"
                f"open({str(record)!r}, 'w', encoding='utf-8').write(os.getcwd())\n")
        env = self.fake_git(LISTING, b"", 0, then=swap)
        for args, out_text in (((), CONTROL_OUT), (("--list",), "README.md:1\ntotal: 1 lines in 1 files\n")):
            with self.subTest(args=args):
                try:
                    self.passes(out_text, *args, env=env)
                    self.assertEqual(Path(record.read_text(encoding="utf-8")).resolve(), held.resolve(),
                                     "git did not work in the root folder that the gate opened")
                finally:
                    # Undo the swap, so the next subtest meets the unchanged repository.
                    record.unlink(missing_ok=True)
                    if self.repo.root.is_symlink():
                        self.repo.root.unlink()
                        held.rename(self.repo.root)

    def test_git_settings_of_the_caller_change_no_result(self):
        # If any of these reached git, git add -A would leave README.md out, through the excludes file
        # under XDG_CONFIG_HOME or HOME or the core.excludesFile of GIT_CONFIG_COUNT, or git would look
        # for the repository at GIT_DIR, so the repository built under them would not pass.
        caller = self.repo.base / "caller"
        for folder in (caller / "git", caller / ".config" / "git"):
            folder.mkdir(parents=True)
            (folder / "ignore").write_bytes(b"*.md\n")
        (caller / "exclude").write_bytes(b"*.md\n")
        settings = {"XDG_CONFIG_HOME": str(caller), "HOME": str(caller), "GIT_DIR": str(caller / "none"),
                    "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.excludesFile",
                    "GIT_CONFIG_VALUE_0": str(caller / "exclude")}
        with mock.patch.dict(os.environ, settings):
            self.repo = Repo(self.repo.base / "case")
            self.control()
            self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")

    def test_git_init_takes_no_template(self):
        # A template gives .git its hooks, its info/exclude, which git add reads, and its description.
        made = sorted(entry.name for entry in (self.repo.root / ".git").iterdir())
        self.assertEqual([name for name in made if name in ("branches", "description", "hooks", "info")], [], made)
        # A populated template that git init copies when it is not given --template=, so the result
        # does not depend on the template that the installed git has.
        template = self.repo.base / "template"
        (template / "hooks").mkdir(parents=True)
        (template / "info").mkdir()
        (template / "description").write_bytes(b"from the template\n")
        (template / "info" / "exclude").write_bytes(b"*.md\n")

        class Templated(Repo):
            def git(self, *args: str, stdin: bytes = b"") -> str:
                self.env = dict(self.env, GIT_TEMPLATE_DIR=str(template))
                return super().git(*args, stdin=stdin)

        copied = self.repo.base / "copied"
        copied.mkdir()
        done = subprocess.run(["git", "-C", str(copied), "init", "-q"], capture_output=True, cwd=self.repo.base,
                              env=dict(self.repo.env, GIT_TEMPLATE_DIR=str(template)), timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((copied / ".git" / "description").read_bytes(), b"from the template\n")
        templated = Templated(self.repo.base / "case")
        made = sorted(entry.name for entry in (templated.root / ".git").iterdir())
        self.assertEqual([name for name in made if name in ("branches", "description", "hooks", "info")], [], made)


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

    def test_term_inside_other_letters_or_digits(self):
        # The search is for a substring, so a term with a letter or digit on each side still matches.
        self.control()
        for number, term in enumerate((b"xBY-SAx", b"9ShareAlike9", b"aCreative Commonsz"), 1):
            with self.subTest(term=term):
                name = f"inside{number}.md"
                self.repo.track(name, b"plain\n" + term + b"\n")
                self.refused(f"{name}:2: names a licence term and no allowlist row claims it")
                self.repo.git("rm", "-q", "-f", name)
                self.control()

    def test_unclaimed_line_in_an_executable_file(self):
        self.control()
        self.repo.track_executable("tool.sh", b"#!/bin/sh\n# CC BY-SA 4.0\n")
        self.refused("tool.sh:2: names a licence term and no allowlist row claims it",
                     out_text=PREFIX + "checked: 2 lines in 2 files; 1 problem(s)\n")

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

    def test_marker_is_not_a_pattern(self):
        # As a regular expression, the dot of 4.0 would match the x of 4x0 and claim the line.
        self.control()
        self.repo.track("dotted.md", b"Licence: CC BY-SA 4x0\n")
        self.repo.add_row("dotted.md\t1\tkeep\tCC BY-SA 4.0")
        self.refused("dotted.md:1: names a licence term and no allowlist row claims it",
                     also=("dotted.md: allowlist row 3 (keep, marker 'CC BY-SA 4.0') is stale: it claims 0 line(s), "
                           "the allowlist says 1",))

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
        # A line that holds the markers of 2 rows is claimed by neither, so each row, of count 1, claims 0
        # lines and is stale.
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

    def test_row_without_4_fields_or_with_a_carriage_return_is_no_earlier_row(self):
        self.control()
        cases = (("README.md\t1\r\tkeep\tCC BY-SA 4.0", "it holds a carriage return"),
                 ("README.md\t1\tkeep\tCC BY-SA 4.0\tmore", "it has 5 tab-separated field(s), not 4"))
        for row, cause in cases:
            with self.subTest(row=row):
                # The well-formed row after it repeats no earlier row, so it claims the README.md line.
                self.repo.set_rows(row, ROW)
                self.refused(f"{ALLOWLIST}:2: malformed row: {cause}")

    def test_shown_fields_are_escaped_once(self):
        self.control()
        # An escape byte, a backslash, DEL (0x7f), a Latin-1 letter, a character of the BMP and 1 above it.
        name = "a\x1bb\\c\x7f\u00e9\u2028\U0001f600.md"
        shown = "a\\x1bb\\\\c\\x7f\\xe9\\u2028\\U0001f600.md"
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
        # The allowlist is read 2 times, as a named exception and as the allowlist, and with no row
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

    def test_parent_that_is_not_a_folder_in_the_work_tree(self):
        # The file that a parent link would reach holds no term, so a gate that read through the link
        # would report the row of the tracked file as stale in place of this cause.
        self.control()
        outside = self.repo.base / "outside"
        outside.mkdir()
        (outside / "notes.md").write_bytes(b"no term\n")
        (self.repo.root / "elsewhere").mkdir()
        (self.repo.root / "elsewhere" / "notes.md").write_bytes(b"no term\n")
        cases = (("sub/notes.md", "sub", "a link to a folder outside the work tree"),
                 ("deep/sub/notes.md", "deep/sub", "a link to a folder outside the work tree"),
                 ("sub/notes.md", "sub", "a link to a folder inside the work tree"),
                 ("deep/sub/notes.md", "deep", "a file"))
        for path, parent, kind in cases:
            with self.subTest(path=path, parent=parent, kind=kind):
                self.repo.track(path, b"ShareAlike\n")
                self.repo.add_row(f"{path}\t1\tkeep\tShareAlike")
                self.passes(PREFIX + "checked: 2 lines in 2 files; 0 problem(s)\n")
                shutil.rmtree(self.repo.root / parent)
                if kind == "a file":
                    (self.repo.root / parent).write_bytes(b"no term\n")
                else:
                    target = outside if "outside" in kind else Path("elsewhere")
                    os.symlink(target, self.repo.root / parent)
                self.refused(f"{PREFIX}{path}: the tracked path is not a regular file in the work tree, since its "
                             f"parent {parent} is not a folder in the work tree",
                             out_text=PREFIX + "checked: 1 lines in 1 files; 1 problem(s)\n")
                (self.repo.root / parent).unlink()
                self.repo.git("rm", "-q", "--cached", "--", path)
                self.repo.set_rows(ROW)
                self.control()

    def test_list_fails_on_a_parent_that_is_not_a_folder(self):
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")
        self.repo.track("sub/notes.md", b"ShareAlike\n")
        self.passes("README.md:1\nsub/notes.md:1\ntotal: 2 lines in 2 files\n", "--list")
        outside = self.repo.base / "outside"
        outside.mkdir()
        (outside / "notes.md").write_bytes(b"no term\n")
        shutil.rmtree(self.repo.root / "sub")
        os.symlink(outside, self.repo.root / "sub")
        self.refused(f"{PREFIX}sub/notes.md: the tracked path is not a regular file in the work tree, since its "
                     "parent sub is not a folder in the work tree", "--list",
                     out_text="README.md:1\ntotal: 1 lines in 1 files\n")

    def test_path_that_is_not_plain_relative(self):
        # Each path would reach a file with a matching line if the gate opened it as written: 1 outside
        # the work tree, 1 the copy of the gate, 1 a file with a name outside ASCII and the others
        # README.md. The only part of tools//check-licence-names.py that is refused is its empty part, and
        # the absolute paths are written in the file system's encoding, whatever the temporary folder holds.
        self.control()
        (self.repo.base / "outside.md").write_bytes(b"CC BY-SA 4.0\n")
        (self.repo.root / "d\xe9j\xe0.md").write_bytes(b"CC BY-SA 4.0\n")
        paths = ("../outside.md", str(self.repo.root / "README.md"), str(self.repo.root / "d\xe9j\xe0.md"),
                 "./README.md", "tools//../README.md", "tools//check-licence-names.py", "tools/../README.md")
        listing = LISTING + b"".join(b"100644 " + b"0" * 40 + b" 0\t" + os.fsencode(path) + b"\0"
                                     for path in paths)
        env = self.fake_git(listing, b"", 0)
        causes = [f"{PREFIX}{escaped(path)}:{NOT_PLAIN}" for path in paths]
        self.refused(causes[0], also=tuple(causes[1:]), env=env,
                     out_text=PREFIX + f"checked: 1 lines in 1 files; {len(paths)} problem(s)\n")
        self.refused(causes[0], "--list", also=tuple(causes[1:]), env=env,
                     out_text="README.md:1\ntotal: 1 lines in 1 files\n")

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

    def test_parent_link_after_the_lstat_check(self):
        # Each link leads to a folder outside the work tree whose notes.md holds a term, so a reader
        # that followed it would return those bytes.
        outside = self.repo.base / "outside"
        outside.mkdir()
        (outside / "notes.md").write_bytes(b"OUTSIDE BYTES CC BY-SA 4.0\n")
        (self.repo.root / "deep").mkdir()
        os.symlink(outside, self.repo.root / "sub")
        os.symlink(outside, self.repo.root / "deep" / "sub")
        # The controls: real folders at the same depths, read through the same replaced os.lstat.
        (self.repo.root / "real" / "sub").mkdir(parents=True)
        (self.repo.root / "real" / "notes.md").write_bytes(b"inside\n")
        (self.repo.root / "real" / "sub" / "notes.md").write_bytes(b"inside\n")
        # Opened without following it, a link is refused as not a folder with os.O_DIRECTORY, and as a
        # link (ELOOP) without it, so a read error of another kind does not pass.
        refusals = {"parent": f"NotADirectoryError: [Errno {errno.ENOTDIR}]",
                    "parent-bare": f"OSError: [Errno {errno.ELOOP}]"}
        for mode, refusal in refusals.items():
            for name, real in (("sub/notes.md", "real/notes.md"), ("deep/sub/notes.md", "real/sub/notes.md")):
                with self.subTest(mode=mode, name=real):
                    self.assertEqual(self.probe(mode, real, "tools"), {"data": "inside\n", "problems": []})
                with self.subTest(mode=mode, name=name):
                    result = self.probe(mode, name, "tools")
                    self.assertIsNone(result["data"], result)
                    self.assertEqual(len(result["problems"]), 1, result)
                    self.assertTrue(result["problems"][0].startswith(f"{name}: cannot read the tracked file: {refusal}"),
                                    result)

    def test_parent_file_after_the_lstat_check(self):
        (self.repo.root / "flat").write_bytes(b"no term\n")
        with self.subTest(mode="parent"):
            # Opened as a folder, the file is refused at once.
            result = self.probe("parent", "flat/notes.md", "tools")
            self.assertIsNone(result["data"], result)
            self.assertEqual(len(result["problems"]), 1, result)
            self.assertTrue(result["problems"][0].startswith(
                f"flat/notes.md: cannot read the tracked file: NotADirectoryError: [Errno {errno.ENOTDIR}]"), result)
        with self.subTest(mode="parent-bare"):
            # Without os.O_DIRECTORY the file opens, and the check of what was opened refuses it.
            self.assertEqual(self.probe("parent-bare", "flat/notes.md", "tools"),
                             {"data": None, "problems": ["flat/notes.md: the tracked path is not a regular file in "
                                                         "the work tree, since its parent flat is not a folder in "
                                                         "the work tree"]})

    def test_entry_moved_out_after_the_open(self):
        # Each entry moves out of the work tree just after the gate opens it, and the file then holds
        # bytes that name a term, so a reader that did not check each entry after the read would
        # return those bytes.
        cases = (("sub/notes.md", "sub"), ("deep/sub/notes.md", "deep/sub"), ("sub/notes.md", "sub/notes.md"))
        for name, moved in cases:
            with self.subTest(name=name, moved=moved):
                for folder in ("sub", "deep", "away"):
                    shutil.rmtree(self.repo.root / folder, ignore_errors=True)
                    shutil.rmtree(self.repo.base / folder, ignore_errors=True)
                (self.repo.base / "away").mkdir()
                (self.repo.root / name).parent.mkdir(parents=True)
                (self.repo.root / name).write_bytes(b"inside\n")
                self.assertEqual(self.probe("plain", name, name), {"data": "inside\n", "problems": []})
                self.assertEqual(self.probe("move", name, moved),
                                 {"data": None, "problems": [f"{name}: the work tree changed while the gate read the "
                                                             f"file, since {moved} is no longer where the gate "
                                                             "opened it"]})

    def test_reader_without_o_nofollow(self):
        # The opener and the reader each refuse, so neither falls back to an open that follows a link.
        self.assertEqual(self.probe("no-nofollow", "README.md", "README.md"),
                         {"data": None, "problems": [f"{NO_NOFOLLOW}, and the gate runs no git and reads no file",
                                                     f"README.md: cannot read the tracked file: {NO_NOFOLLOW}"]})

    def test_read_error(self):
        self.assertEqual(self.probe("read-error", "README.md", "README.md"),
                         {"data": None, "problems": [f"README.md: cannot read the tracked file: OSError: [Errno "
                                                     f"{errno.EIO}] {os.strerror(errno.EIO)}"]})

    def test_error_text_is_one_line_cut_and_escaped(self):
        # The text is made 1 line and cut to 300 characters before it is escaped, so no escape is cut.
        prefix = f"[Errno {errno.EIO}] "
        detail = prefix + ODD_SHOWN + "\\xe9" * (300 - len(prefix) - ODD_RAW_LENGTH)
        self.assertEqual(self.probe("odd-error", "README.md", "README.md"),
                         {"data": None, "problems": [f"README.md: cannot read the tracked file: OSError: {detail}"]})

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

    def test_system_without_o_nofollow(self):
        self.control()
        cause = f"{PREFIX}{NO_NOFOLLOW}, and the gate runs no git and reads no file"
        self.refused(cause, without_nofollow=True, out_text=PREFIX + "checked: 0 lines in 0 files; 1 problem(s)\n")
        self.refused(cause, "--list", without_nofollow=True, out_text="total: 0 lines in 0 files\n")

    def test_root_that_is_not_a_folder(self):
        self.control()
        self.repo.root.rename(self.repo.base / "held")
        self.repo.root.write_bytes(b"CC BY-SA 4.0\n")
        cause = f"{PREFIX}{escaped(str(self.repo.root))}: cannot open the root folder: NotADirectoryError"
        self.refused(cause, out_text=PREFIX + "checked: 0 lines in 0 files; 1 problem(s)\n")
        self.refused(cause, "--list", out_text="total: 0 lines in 0 files\n")

    def test_git_cannot_run(self):
        self.control()
        empty = self.repo.base / "no-commands"
        empty.mkdir()
        self.refused(f"{PREFIX}cannot run git ls-files, so no tracked file can be listed: FileNotFoundError",
                     env=dict(self.repo.env, PATH=str(empty)))

    def test_git_message_is_one_line_cut_and_escaped(self):
        self.control()
        # The byte 0xff is read as U+FFFD; with "fatal: " that makes 8 characters before the odd tail.
        detail = "\\" + "ufffdfatal: " + ODD_SHOWN + "\\xe9" * (300 - 8 - ODD_RAW_LENGTH)
        line = f"{PREFIX}git ls-files exited 3, so no tracked file can be listed: {detail}"
        err = self.refused(line, env=self.fake_git(b"", b"\xfffatal:" + ODD_TAIL.encode("utf-8"), 3),
                           out_text=PREFIX + "checked: 0 lines in 0 files; 1 problem(s)\n")
        self.assertEqual(err, line + "\n")

    def test_entry_of_git_ls_files_that_cannot_be_read(self):
        self.control()
        self.refused(BAD_ENTRY_PROBLEMS[0], also=BAD_ENTRY_PROBLEMS[1:],
                     env=self.fake_git(LISTING + BAD_ENTRIES, b"", 0),
                     out_text=PREFIX + "checked: 1 lines in 1 files; 3 problem(s)\n")

    def test_only_entries_that_cannot_be_read(self):
        # git listed entries, so the gate names each and not an empty listing as a cause.
        self.control()
        self.refused(BAD_ENTRY_PROBLEMS[0], also=BAD_ENTRY_PROBLEMS[1:], env=self.fake_git(BAD_ENTRIES, b"", 0),
                     out_text=PREFIX + "checked: 0 lines in 0 files; 3 problem(s)\n")

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

    def test_list_fails_on_an_entry_that_cannot_be_read(self):
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")
        self.refused(BAD_ENTRY_PROBLEMS[0], "--list", also=BAD_ENTRY_PROBLEMS[1:],
                     env=self.fake_git(LISTING + BAD_ENTRIES, b"", 0),
                     out_text="README.md:1\ntotal: 1 lines in 1 files\n")

    def test_list_fails_on_only_entries_that_cannot_be_read(self):
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")
        self.refused(BAD_ENTRY_PROBLEMS[0], "--list", also=BAD_ENTRY_PROBLEMS[1:],
                     env=self.fake_git(BAD_ENTRIES, b"", 0), out_text="total: 0 lines in 0 files\n")

    def test_list_fails_when_git_cannot_run(self):
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")
        empty = self.repo.base / "no-commands"
        empty.mkdir()
        self.refused(f"{PREFIX}cannot run git ls-files, so no tracked file can be listed: FileNotFoundError", "--list",
                     env=dict(self.repo.env, PATH=str(empty)), out_text="total: 0 lines in 0 files\n")

    def test_list_fails_outside_a_git_repository(self):
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")
        shutil.rmtree(self.repo.root / ".git")
        self.refused(f"{PREFIX}git ls-files exited 128, so no tracked file can be listed: fatal: not a git repository",
                     "--list", out_text="total: 0 lines in 0 files\n")

    def test_list_fails_on_an_empty_index(self):
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")
        self.repo.git("rm", "-r", "--cached", "-q", ".")
        self.refused(f"{PREFIX}git ls-files lists no tracked file, so there is nothing to compare", "--list",
                     out_text="total: 0 lines in 0 files\n")

    def test_list_fails_on_an_unmerged_entry(self):
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")
        blob = self.repo.git("hash-object", "-w", "README.md").strip()
        for stage in ("1", "2", "3"):
            with self.subTest(stage=stage):
                info = f"0 {'0' * 40}\tREADME.md\n100644 {blob} {stage}\tREADME.md\n".encode("ascii")
                self.repo.git("update-index", "--index-info", stdin=info)
                self.refused(f"{PREFIX}README.md: an unmerged index entry (stage {stage}), so the gate cannot tell "
                             "which version is tracked", "--list", out_text="README.md:1\ntotal: 1 lines in 1 files\n")
                self.repo.git("add", "README.md")
                self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")

    def test_list_fails_on_a_file_that_cannot_be_read(self):
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")
        with self.subTest(path="gone.md"):
            self.repo.track("gone.md", b"no term\n")
            (self.repo.root / "gone.md").unlink()
            self.refused(f"{PREFIX}gone.md: cannot read the tracked file: FileNotFoundError", "--list",
                         out_text="README.md:1\ntotal: 1 lines in 1 files\n")
            self.repo.git("rm", "-q", "--cached", "--", "gone.md")
            self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")
        with self.subTest(path=ALLOWLIST):
            # --list reads the allowlist only as a named exception, so it reports 1 problem.
            before = (self.repo.root / ALLOWLIST).read_bytes()
            (self.repo.root / ALLOWLIST).unlink()
            self.refused(f"{PREFIX}{ALLOWLIST}: cannot read the tracked file: FileNotFoundError", "--list",
                         out_text="README.md:1\ntotal: 1 lines in 1 files\n")
            self.repo.write(ALLOWLIST, before)
            self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")

    def test_list_fails_on_a_named_exception_without_a_matching_line(self):
        self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")
        contents = {ALLOWLIST: (HEADER + "README.md\t1\tkeep\tLicence:\n").encode("utf-8")}
        for path in NAMED_EXCEPTIONS:
            with self.subTest(path=path):
                before = (self.repo.root / path).read_bytes()
                self.repo.track(path, contents.get(path, b"print('no term')\n"))
                self.refused(f"{PREFIX}{path}: a named exception that holds no matching line", "--list",
                             out_text="README.md:1\ntotal: 1 lines in 1 files\n")
                self.repo.track(path, before)
                self.passes("README.md:1\ntotal: 1 lines in 1 files\n", "--list")

    def test_file_content_is_data(self):
        self.control()
        # The gate runs in the temporary folder, so the relative touch of the name and the absolute touch
        # of the content would each make the 1 file that the case checks.
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
