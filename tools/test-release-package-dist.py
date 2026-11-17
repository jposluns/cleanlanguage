#!/usr/bin/env python3
"""Check what tools/release-package.sh leaves in dist/ after each build.

The packager is meant to work as follows, and the cases below check it at
the builds and on the planted paths that they name. A build that passes
every check writes dist/cleanlanguage.zip, dist/cleanlanguage-<version>.zip
and a .sha256 beside each. A build that is refused at a check, or ended by
SIGHUP, SIGINT or SIGTERM at any point from its first removal on, must
leave no zip and no .sha256 in dist/, neither a new one nor one that an
earlier build wrote, so that a reader cannot take a stale or unverified zip
for the refused build; a removal that fails is the exception, and then the
build fails and the output it could not remove stays. Apart from its own
work folder, the packager removes an entry of dist/ only when it is a
regular file with an output name. Its only recursive removal is that of its
work folder, which it makes in dist/ with mktemp, by the path that mktemp
gave; a folder with a work-folder name that an earlier build left stays. A
build refuses with exit 1 a dist that is a symbolic link or that exists and
is not a folder at the start, a dist that is a symbolic link after it makes
dist/, and a symbolic link, folder, FIFO or other object that is not a
regular file at 1 of the 4 names it writes, since its rename into dist/
would replace that object. It moves each output from its work folder to the
folder that holds it, so a work folder moved away before the moves makes
the build fail, and a folder put at an output name after the refusal makes
the move fail. The name test takes only ASCII digits, whatever the locale.
The packager makes no claim for another process of the same user that
renames or replaces dist/ or the work folder while a build runs; cases 19
to 21 make such a change only to pin the refusal or failure that the
packager states for it.

Every build here runs in a clone that the test makes in a temporary folder
with `git clone --no-local`, never in the checkout it runs from, so a dist/
folder in the checkout is never touched. The clone carries the checkout's
HEAD; the checkout's tools/release-package.sh, tools/skill-release-date.py
and tools/skill-release-date-client.py are copied into it, so the code under
test is the checkout's, uncommitted changes included. The test runs
read-only git commands and git clone only; it sets core.autocrlf for 1 build
through the GIT_CONFIG_COUNT, GIT_CONFIG_KEY_0 and GIT_CONFIG_VALUE_0
variables of that build's environment, never by a git config command. Each
build runs with TMPDIR set to a folder of the temporary folder, and without
the BASHOPTS, SHELLOPTS, GLOBIGNORE and BASH_ENV of the test's own
environment; the cases of inherited shell options set 1 of these 4.
Each stand-in command is a short sh script that the test writes into its
temporary folder and puts first on the PATH of 1 build. A build that the
test starts and then signals writes its error output to a file of the
temporary folder, not to a pipe, and its standard output is discarded, so
it cannot block on a full pipe while the test waits for its stand-in.

The near-miss plants are generated, not picked by hand (near_misses): from
each of the 4 output names of the version at HEAD and from the 2 output
names of SAMPLE_VERSION (1.0.0), whose version parts have 1 digit each,
every name made by deleting 1 character, inserting 1 character of ALPHABET
(a letter, a digit, a dot, a hyphen, an underscore) at any position,
replacing 1 character by 1 of ALPHABET, or changing the letter case of 1
letter, and the name in capital letters; and the 4 names that repeat an
optional group of an output name (a second version part, a second
.sha256). A name that is itself an output name is left out. Each is planted
as a regular file. So a loosening of the name test of the removal that
admits a name of this set removes a plant, and a case fails; a loosening
that admits only names outside the set, such as a name 2 edits away, is not
caught by it. Besides these, the test plants a plain file, a folder of
scripts, a folder at the output name of another version, a regular file
with a work-folder name (OTHER_PLANTS), a symbolic link with a work-folder
name to a folder outside dist/ (WORK_LINK), and 2 leftover work folders
(LEFTOVER_WORK), each holding a file at an output name. After each build
that follows a planting, each planted path must be there with its bytes
unchanged, the link must still point at the same unchanged folder, and each
leftover work folder must still hold its file. Before the refused build of
case 2 and of case 3, before the build of case 4 and of case 10 that
follows a good build, before the build of case 9 that follows a good build,
and before each build of case 11 that receives a signal during its first
removal, the test also plants the 2 outputs of an earlier build for each
version of STALE_VERSIONS: 10.20.30, a version each of whose parts holds
the 10 digits in turn, and a version each of whose parts has 20 digits, so
that a narrowing of the output test that drops a digit at any part, or
takes fewer than 20 digits in a part, keeps a stale output, and a case
fails.

In its set-up, before any case, the test builds the clone with the packager
of REFERENCE_COMMIT, which gives the reference digest. The cases, all in
that clone:

1. A good build with the checkout's packager exits 0, writes the 4 outputs,
   and gives the reference digest for both zips with matching .sha256 files;
   it keeps the planted paths. A good build with no dist/ exits 0 and writes
   the 4 outputs.
2. After a good build, a build refused before the archive is made
   (--tag v0.0.0, --release-date 2020-01-01, and the unknown argument
   --bogus) leaves no zip and no .sha256 in dist/.
3. After a good build, a build with core.autocrlf=true, refused by the check
   that compares each archived file with its git blob, leaves no zip and no
   .sha256 in dist/.
4. After a good build, a build whose move of the .sha256 files into dist/
   fails, through a stand-in mv that refuses each move of a .sha256 file,
   leaves no zip and no .sha256 in dist/, including the 2 zips it had
   already moved.
5. In a good build, a stand-in mv records each of the 4 moves into dist/:
   each is `mv -fT -- <work>/<name> <work>/../<name>`, where <work> is a
   folder of dist/ with a work-folder name, and both zips are in dist/
   before either .sha256 is moved there.
6. In a good build, a stand-in unzip records that no output name is present
   in dist/ at any of its calls, so no output reaches dist/ before the checks
   that read the staged zip.
7. A dist that is a symbolic link to a folder, a dangling symbolic link, a
   plain file or a FIFO is refused with exit 1 and the packager's message,
   and the folder it points at, the missing target, the file or the FIFO
   is unchanged.
8. A folder named dist/cleanlanguage.zip/ is refused with exit 1 and the
   packager's message, is kept with its contents, and dist/ holds no zip
   and no .sha256; a stand-in mktemp that records its calls was never
   called.
9. A symbolic link to a file outside dist/ at dist/cleanlanguage.zip and at
   dist/cleanlanguage.zip.sha256, a dangling symbolic link at the
   version-named .sha256, and a FIFO at the version-named zip are each
   refused with exit 1 and the packager's message in a build with no
   arguments. The link at dist/cleanlanguage.zip, the dangling link and
   the FIFO are also each refused after a good build, in a build whose
   stand-in mv runs each move and then fails for a .sha256 file. The
   refusal comes before any move, so these builds never call that mv; a
   build without the refusal would reach the moves, replace the object,
   and fail at the first move of a .sha256 file, so the exit trap would
   remove what replaced the object and the case would fail. In each build
   the object, and the file or missing path that a link points at, is
   unchanged, dist/ holds no zip and no .sha256, and a stand-in mktemp that
   records its calls was never called.
10. After a good build, a build whose stand-in rm fails at the
    version-named zip exits 1 with the packager's message for a failed
    removal; that zip is still there, and each other earlier output is
    gone. The removal runs in dist/ and gives rm each name as ./<name>,
    which is the argument at which the stand-in fails.
11. A build that receives SIGTERM, SIGHUP or SIGINT while a stand-in mv
    holds the move of the .sha256 files exits 143, 129 or 130, and leaves
    no zip and no .sha256 in dist/. After a good build, a build refused by
    --bogus that receives SIGTERM, SIGHUP or SIGINT while a stand-in rm
    holds the first removal in dist/ exits 143, 129 or 130 before the
    argument check, and leaves no zip and no .sha256 in dist/, neither the
    good build's nor a stale one. The test resets the 3 signals to their
    default action in the build's process, since bash cannot trap a
    signal that was ignored when it started.
12. With BASHOPTS=dotglob, BASHOPTS=nocasematch, SHELLOPTS=noglob,
    GLOBIGNORE=dist/*:*, or BASH_ENV naming a file that assigns
    GLOBIGNORE=dist/*:*, in its environment, a good build keeps the planted
    paths, and a build refused by --bogus after it, with nothing planted
    again, leaves no zip and no .sha256 in dist/. With BASHOPTS=failglob, a
    good build that starts with an empty dist/, where nothing is planted,
    writes the 4 outputs, and a build refused by --bogus after it leaves no
    zip and no .sha256 in dist/.
13. Under the first locale of WIDE_LOCALES in which a bash [0-9] takes an
    Arabic-Indic digit, a good build keeps the planted paths and 2 files
    whose names are an output name with digits outside ASCII. The case is
    skipped, with that reason, when no such locale is installed.
14. A stand-in mktemp records the work folder of a build. After a good
    build, and after a build whose stand-in mv refuses each move of a
    .sha256 file with exit 7, it is gone; the failed build exits 7 and
    leaves no zip and no .sha256 in dist/. In a build with that mv, a
    stand-in rm that fails at ./cleanlanguage.zip, in dist/, leaves that
    zip in place, and the build still exits 7 and removes its work folder;
    a stand-in rm that fails at the work folder leaves it in place, and the
    build still exits 7 with no output in dist/. In a good build, a
    stand-in rm that fails at the work folder leaves it in place, and the
    build still exits 0 with its 4 outputs. A build with that mv that
    receives SIGTERM, SIGHUP or SIGINT while a stand-in rm holds the first
    removal of its exit trap still exits 7, leaves no zip and no .sha256 in
    dist/, and leaves no work folder.
15. After a good build, a build refused by --bogus keeps the planted
    paths, among them the near miss Cleanlanguage.zip, and removes the
    outputs of version 11111111111.0.0.
16. The packager's code, with its comment lines and the Python programs
    that it passes to python3 -c set aside, holds exactly 1 rm with a
    recursive option, `rm -rf -- "${work}" || true`, no rmdir in a for,
    while or until loop, no rmdir with its parents option, no find -delete,
    and the line that sets work from mktemp -d with a template in dist/.
17. A stand-in rm records each call and a stand-in mktemp the work folder:
    a good build, a build refused by the blob check under
    core.autocrlf=true, and a build whose stand-in mv refuses each move of
    a .sha256 file each call rm with a recursive option exactly once, with
    the path that mktemp gave as its only operand; a build refused by
    --bogus calls it never.
18. A folder with a work-folder name that holds a file, as a SIGKILL could
    leave, is kept unchanged by a good build, by a build refused by
    --bogus, by a build refused by the blob check, and by a build whose
    move of the .sha256 files fails.
19. A stand-in mkdir that, at the build's `mkdir -p dist`, first puts at
    dist a symbolic link to a folder outside the clone that holds a file
    named cleanlanguage.zip makes the build exit 1 with the message for a
    linked dist; the outside folder is unchanged, and the stand-in mktemp
    was never called.
20. A stand-in cmp that, after its last call, makes a folder holding a
    file at dist/cleanlanguage.zip makes the build fail rather than move
    the zip into that folder; the folder is unchanged, and dist/ holds no
    zip and no .sha256.
21. A stand-in cmp that, after its last call, moves the work folder out of
    dist/ makes the build fail; the moved folder still holds src/ and the
    4 staged files, so no move took place, and dist/ holds no output and
    no work folder.
22. In a good build with nothing planted, a stand-in zip records 1 call,
    which writes cleanlanguage.zip in a folder of dist/ with a work-folder
    name and runs in src/cleanlanguage/ of that folder; the build exits 0
    and writes the 4 outputs.

Each case starts with no dist/ in the clone.

REFERENCE_COMMIT names the commit of the last packager that wrote dist/
before its checks, and the reference comparison in case 1 holds only while
the packager gives the same bytes as that commit's packager. An intended
change to the packager's output therefore makes case 1 fail by design.
REFERENCE_COMMIT then moves to the commit that makes the change, in the
same pull request.

Usage:
  python3 -I tools/test-release-package-dist.py

Needs git, bash, zip, unzip, sha256sum and GNU coreutils, and the full
history of the checkout, since it reads tools/release-package.sh at
REFERENCE_COMMIT.
"""

import hashlib
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = ("release-package.sh", "skill-release-date.py", "skill-release-date-client.py")
REFERENCE_COMMIT = "8d6de113182691d313c7cb6bdfb01df7423d280c"
KEEP = "keep.txt"
KEEP_TEXT = b"a file the packager does not write\n"
# The characters that the near misses insert or put in place of another: a
# letter, a digit, a dot, a hyphen and an underscore.
ALPHABET = "a0.-_"
# A second version for the near misses, whose parts have 1 digit each, so
# that deleting 1 character can leave a version part empty whatever the
# version at HEAD is.
SAMPLE_VERSION = "1.0.0"
# Entries of dist/ that the packager did not write and that are not near
# misses, each of which a build must keep byte for byte: a plain file, a
# folder of scripts, a folder at the output name of another version, and a
# regular file with a work-folder name.
OTHER_PLANTS = {
    KEEP: KEEP_TEXT,
    "edit-scripts/keep.py": b"print('kept')\n",
    "cleanlanguage-1.0.0.zip/keep.txt": b"a folder with an output name\n",
    ".release-package.FiLe12": b"a file with a work-folder name\n",
}
# Earlier builds' outputs for other versions, planted by plant_stale before
# the refused or later build of the cases that call it. Each version part of
# the first has 2 digits, so that a version test that takes only 1 digit in
# a part keeps them; each part of the second holds each of the 10 digits, so
# that a version test that drops a digit from a part, or takes fewer than
# 10 digits in a part, keeps them; each part of the third has 20 digits,
# so that a version test that takes fewer than 20 digits in a part keeps
# them.
STALE_VERSIONS = ("10.20.30", "0123456789.0123456789.0123456789",
                  "01234567890123456789.01234567890123456789.01234567890123456789")
# A symbolic link with a work-folder name, to a folder outside dist/ that
# holds WORK_LINK_FILE; the build must keep the link and leave the folder as
# it is.
WORK_LINK = ".release-package.LnK456"
WORK_LINK_FILE = "keep.txt"
# Leftover work folders, as a build ended by SIGKILL could leave, each
# holding a file at an output name; a build must keep each unchanged.
LEFTOVER_WORK = (".release-package.AbC123", ".release-package.zZ9999")
LEFTOVER_FILE = "cleanlanguage.zip"
LEFTOVER_TEXT = b"left by a killed build\n"
# Locales in which a bash range may take characters outside ASCII; the
# locale case uses the first of them in which [0-9] takes an Arabic-Indic
# digit, and is skipped, with that reason, when none does.
WIDE_LOCALES = ("en_US.UTF-8", "en_GB.UTF-8", "de_DE.UTF-8", "fr_FR.UTF-8")
# Names outside ASCII that a range test of the removal takes under such a
# locale and that the packager never gives, each planted as a regular file:
# a version in Arabic-Indic digits, and a version with 1 Arabic-Indic digit.
NON_ASCII_FILES = ("cleanlanguage-%s.%s.%s.zip" % (chr(0x661), chr(0x660), chr(0x660)),
                   "cleanlanguage-1.0.%s.zip.sha256" % chr(0x663))
REFUSED_NAME = "exists and is not a regular file that the packager wrote"
REMOVAL_FAILED = ("release-package: could not remove every earlier output from dist/; "
                  "any it could not remove is still there")
LINKED_DIST = "release-package: dist is a symbolic link; the packager writes only into a real dist/ folder"
OUTPUT_NAME = re.compile(r"cleanlanguage(-[0-9]+\.[0-9]+\.[0-9]+)?\.zip(\.sha256)?")
WORK_NAME = re.compile(r"\.release-package\.[A-Za-z0-9]{6}")
# The GLOBIGNORE of the 2 cases that set it: a colon-separated list of dist/*,
# which hides every entry from a glob dist/*, and *, which hides every
# entry from the glob * that the removal, run in dist/, uses.
GLOBIGNORE_VALUE = "dist/*:*"
# Variables of the test's own environment that would change how bash globs
# and matches, or run code before the packager; no build inherits them.
SHELL_VARIABLES = ("BASHOPTS", "SHELLOPTS", "GLOBIGNORE", "BASH_ENV")
BUILD_TIMEOUT = 300
# The exit code of the stand-in mv that refuses a move with a code other than 1.
MOVE_EXIT = 7
# An rm option word that asks for a recursive removal.
RECURSIVE_OPTION = re.compile(r"-[A-Za-z]*[rR][A-Za-z]*|--recursive")


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True, timeout=BUILD_TIMEOUT).stdout


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def edits(name: str) -> set:
    """Every name made from name by deleting 1 character, inserting 1
    character of ALPHABET at any position, replacing 1 character by 1 of
    ALPHABET, or changing the letter case of 1 letter, and name in capital
    letters."""
    made = {name.upper()}
    for i in range(len(name) + 1):
        for c in ALPHABET:
            made.add(name[:i] + c + name[i:])
    for i in range(len(name)):
        made.add(name[:i] + name[i + 1:])
        for c in ALPHABET:
            made.add(name[:i] + c + name[i + 1:])
        if name[i].isalpha():
            made.add(name[:i] + name[i].swapcase() + name[i + 1:])
    return made


def near_misses(version: str) -> list:
    """The near misses of the output names of version and of
    SAMPLE_VERSION, sorted, including the 4 names that repeat an optional
    group. No name is an output name."""
    outputs = ["cleanlanguage.zip"] + ["cleanlanguage-%s.zip" % v for v in (version, SAMPLE_VERSION)]
    outputs += [n + ".sha256" for n in outputs]
    made = set().union(*(edits(n) for n in outputs))
    made |= {"cleanlanguage-%s-%s.zip" % (version, version),
             "cleanlanguage-%s-%s.zip.sha256" % (version, version),
             "cleanlanguage.zip.sha256.sha256",
             "cleanlanguage-%s.zip.sha256.sha256" % version}

    def usable(name: str) -> bool:
        return (name not in ("", ".", "..") and "/" not in name
                and not OUTPUT_NAME.fullmatch(name)
                and name.split("/")[0] not in {p.split("/")[0] for p in OTHER_PLANTS})

    return sorted(filter(usable, made))


def outputs(dist: Path) -> list:
    """Every regular file in dist/ with an output name, and every folder
    with a work-folder name other than LEFTOVER_WORK, which is a work folder
    that a build left; a symbolic link is neither."""
    if not dist.is_dir() or dist.is_symlink():
        return []
    return sorted(p.name for p in dist.iterdir()
                  if not p.is_symlink()
                  and ((OUTPUT_NAME.fullmatch(p.name) and p.is_file())
                       or (WORK_NAME.fullmatch(p.name) and p.is_dir() and p.name not in LEFTOVER_WORK)))


def snapshot(root: Path) -> dict:
    """Every path under root, with the bytes of each file and None for each folder."""
    return {str(p.relative_to(root)): (None if p.is_dir() else p.read_bytes())
            for p in sorted(root.rglob("*"))}


def default_signals():
    """Give SIGHUP, SIGINT and SIGTERM their default action in the build's
    process, so that its bash can trap them even when the test was started
    with 1 of them ignored."""
    for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal.SIG_DFL)


def code_lines(text: str) -> list:
    """(number, line) for each line of a shell script that is not blank, not
    a comment line, and not inside a Python program that the script passes
    to python3 -c in single quotes over several lines."""
    found, in_python = [], False
    for n, line in enumerate(text.splitlines(), 1):
        if in_python:
            in_python = not line.startswith("'")
            continue
        if "python3 -I -c '" in line and line.count("'") % 2 == 1:
            in_python = True
        if line.strip() and not line.lstrip().startswith("#"):
            found.append((n, line))
    return found


class DistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.clone = Path(cls.tmp.name) / "clone"
        cls.work = Path(cls.tmp.name) / "work"
        cls.work.mkdir()
        git("clone", "-q", "--no-local", "--no-hardlinks", str(REPO), str(cls.clone))
        for name in TOOLS:
            shutil.copyfile(REPO / "tools" / name, cls.clone / "tools" / name)
        os.chmod(cls.clone / "tools" / "release-package.sh", 0o755)
        cls.dist = cls.clone / "dist"
        skill = git("-C", str(cls.clone), "show", "HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md")
        cls.version = next(line.split(":", 1)[1].strip() for line in skill.decode("utf-8").splitlines()
                           if line.startswith("Version:"))
        cls.names = ["cleanlanguage-%s.zip" % cls.version, "cleanlanguage-%s.zip.sha256" % cls.version,
                     "cleanlanguage.zip", "cleanlanguage.zip.sha256"]
        cls.output_misses = near_misses(cls.version)
        reference = cls.clone / "tools" / "release-package-reference.sh"
        reference.write_bytes(git("-C", str(REPO), "show", REFERENCE_COMMIT + ":tools/release-package.sh"))
        code, stderr = cls.run_packager(reference)
        if code != 0:
            raise AssertionError(f"the reference packager failed with exit {code}: {stderr}")
        cls.reference_digest = sha256(cls.dist / "cleanlanguage.zip")
        with zipfile.ZipFile(cls.dist / "cleanlanguage.zip") as archive:
            cls.entry_count = len([n for n in archive.namelist() if not n.endswith("/")])
        reference.unlink()
        shutil.rmtree(cls.dist)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        if self.dist.is_dir() and not self.dist.is_symlink():
            shutil.rmtree(self.dist)
        elif os.path.lexists(self.dist):
            self.dist.unlink()

    def plants(self) -> dict:
        """The planted files: OTHER_PLANTS, each near miss as a regular file,
        and the file in each leftover work folder."""
        planted = dict(OTHER_PLANTS)
        for name in self.output_misses:
            planted[name] = name.encode("ascii") + b"\n"
        for name in LEFTOVER_WORK:
            planted[name + "/" + LEFTOVER_FILE] = LEFTOVER_TEXT
        return planted

    @classmethod
    def packager_env(cls, autocrlf: bool = False, path_prefix: str = "", extra: dict = None) -> dict:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("GIT_CONFIG") and k not in SHELL_VARIABLES}
        env["TMPDIR"] = str(cls.work)
        if autocrlf:
            env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.autocrlf", GIT_CONFIG_VALUE_0="true")
        if path_prefix:
            env["PATH"] = path_prefix + os.pathsep + env.get("PATH", "")
        env.update(extra or {})
        return env

    @classmethod
    def run_packager(cls, script: Path, *args: str, autocrlf: bool = False, path_prefix: str = "",
                     extra: dict = None):
        proc = subprocess.run(["bash", str(script), *args], cwd=str(cls.clone),
                              env=cls.packager_env(autocrlf, path_prefix, extra),
                              stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=BUILD_TIMEOUT)
        return proc.returncode, proc.stderr

    def build(self, *args: str, autocrlf: bool = False, path_prefix: str = "", extra: dict = None):
        return self.run_packager(self.clone / "tools" / "release-package.sh", *args, autocrlf=autocrlf,
                                 path_prefix=path_prefix, extra=extra)

    def outside(self, name: str) -> Path:
        """A new, empty folder of the temporary folder, outside the clone."""
        folder = Path(self.tmp.name) / name
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir()
        return folder

    def bin_dir(self, name: str) -> Path:
        """A new, empty folder of the temporary folder for stand-ins."""
        return self.outside(name)

    @staticmethod
    def write_script(path: Path, text: str):
        path.write_text("#!/bin/sh\n" + text, encoding="ascii")
        os.chmod(path, 0o755)

    def real(self, name: str) -> str:
        found = shutil.which(name)
        self.assertIsNotNone(found, "%s is not on the PATH" % name)
        return found

    def plant(self):
        """Plant the files of plants() and WORK_LINK."""
        self.dist.mkdir(exist_ok=True)
        for rel, data in self.plants().items():
            path = self.dist / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        link = self.dist / WORK_LINK
        if not link.is_symlink():
            target = self.outside("work-link-target")
            (target / WORK_LINK_FILE).write_bytes(KEEP_TEXT)
            link.symlink_to(target, target_is_directory=True)

    def assert_plants_kept(self):
        """Assert that every plant is unchanged, among them the file in each
        leftover work folder, and that the link and the folder it points at
        are unchanged."""
        for rel, data in self.plants().items():
            path = self.dist / rel
            self.assertTrue(path.is_file() and not path.is_symlink(),
                            "the build removed %s, which it did not write" % path)
            self.assertEqual(path.read_bytes(), data, "the build changed %s, which it did not write" % path)
        for name in LEFTOVER_WORK:
            self.assertEqual(snapshot(self.dist / name), {LEFTOVER_FILE: LEFTOVER_TEXT},
                             "the build changed the leftover work folder %s" % name)
        link = self.dist / WORK_LINK
        target = Path(self.tmp.name) / "work-link-target"
        self.assertTrue(link.is_symlink(), "the build removed the link %s, which it did not write" % link)
        self.assertEqual(os.readlink(link), str(target))
        self.assertEqual(snapshot(target), {WORK_LINK_FILE: KEEP_TEXT},
                         "the build changed the folder that %s points at" % WORK_LINK)

    def good_build(self, path_prefix: str = "", extra: dict = None):
        self.plant()
        code, stderr = self.build(path_prefix=path_prefix, extra=extra)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(outputs(self.dist), self.names)
        self.assert_plants_kept()

    def plant_stale(self):
        """Plant the outputs of an earlier build for each of STALE_VERSIONS."""
        for version in STALE_VERSIONS:
            (self.dist / ("cleanlanguage-%s.zip" % version)).write_bytes(b"stale")
            (self.dist / ("cleanlanguage-%s.zip.sha256" % version)).write_bytes(b"stale\n")

    def assert_refused_leaves_nothing(self, *args: str, autocrlf: bool = False, path_prefix: str = "",
                                      reason: str):
        self.good_build()
        self.plant()
        self.plant_stale()
        code, stderr = self.build(*args, autocrlf=autocrlf, path_prefix=path_prefix)
        self.assertEqual(code, 1, stderr)
        self.assertIn(reason, stderr)
        self.assertEqual(outputs(self.dist), [], "a refused build left output in dist/")
        self.assert_plants_kept()

    def stand_in(self, name: str) -> tuple:
        """Write a stand-in for name into its own folder of the temporary
        folder. At each call it writes 1 line to its log: the output names
        present in the dist/ of the clone, separated by commas, then its
        working directory and each argument, each after a tab. It then runs
        the real command."""
        real = self.real(name)
        bin_dir = Path(self.tmp.name) / ("record-" + name)
        bin_dir.mkdir(exist_ok=True)
        log = bin_dir / "calls.log"
        if log.exists():
            log.unlink()
        self.write_script(bin_dir / name,
                          "line=\n"
                          "for n in %s; do\n"
                          "  if [ -e '%s'/\"$n\" ]; then line=\"$line$n,\"; fi\n"
                          "done\n"
                          "line=\"$line\t$(pwd -P)\"\n"
                          "for a in \"$@\"; do line=\"$line\t$a\"; done\n"
                          "printf '%%s\\n' \"$line\" >> '%s'\n"
                          "exec '%s' \"$@\"\n" % (" ".join(self.names), self.dist, log, real))
        return str(bin_dir), log

    @staticmethod
    def calls(log: Path) -> list:
        """Each recorded call as (the output names present, the working
        directory, the arguments)."""
        if not log.exists():
            return []
        result = []
        for line in log.read_text(encoding="utf-8").splitlines():
            present, cwd, *args = line.split("\t")
            result.append(([n for n in present.split(",") if n], cwd, args))
        return result

    def test_good_build_keeps_other_files(self):
        self.good_build()

    def test_good_build_without_dist(self):
        code, stderr = self.build()
        self.assertEqual(code, 0, stderr)
        self.assertEqual(outputs(self.dist), self.names)

    def test_good_build_matches_reference(self):
        self.good_build()
        for name in ("cleanlanguage.zip", "cleanlanguage-%s.zip" % self.version):
            with self.subTest(name):
                self.assertEqual(sha256(self.dist / name), self.reference_digest)
                self.assertEqual((self.dist / (name + ".sha256")).read_text(encoding="ascii"),
                                 "%s  %s\n" % (self.reference_digest, name))

    def test_refused_tag_leaves_nothing(self):
        self.assert_refused_leaves_nothing("--tag", "v0.0.0", reason="does not match the tag (v0.0.0)")

    def test_refused_release_date_leaves_nothing(self):
        self.assert_refused_leaves_nothing("--release-date", "2020-01-01",
                                           reason="does not match the release date (2020-01-01)")

    def test_refused_unknown_argument_leaves_nothing(self):
        self.assert_refused_leaves_nothing("--bogus", reason="unknown argument --bogus")

    def test_autocrlf_build_leaves_nothing(self):
        self.assert_refused_leaves_nothing(autocrlf=True, reason="differs from its git blob")

    def refusing_mv(self, folder: str, code: int) -> str:
        """Write a stand-in mv that refuses any move of a .sha256 file with
        exit code, and runs the real mv for every other, so the build fails
        after it has moved the 2 zips into dist/. Return its folder."""
        bin_dir = self.bin_dir(folder)
        self.write_script(bin_dir / "mv",
                          "for a in \"$@\"; do\n"
                          "  case \"$a\" in *.sha256) echo 'mv: refused by the test' >&2; exit %d ;; esac\n"
                          "done\n"
                          "exec '%s' \"$@\"\n" % (code, self.real("mv")))
        return str(bin_dir)

    def test_failed_move_leaves_nothing(self):
        self.assert_refused_leaves_nothing(path_prefix=self.refusing_mv("bin", 1),
                                           reason="mv: refused by the test")

    def refusing_rm(self, refused: str) -> str:
        """Write a stand-in rm, first on the PATH, that fails, without removing
        anything, at any call with the argument ./<refused>, the name by which
        the removal, run in dist/, removes it, and runs the real rm for every
        other call. It records nothing. Return its folder."""
        bin_dir = self.bin_dir("refusing-rm")
        self.write_script(bin_dir / "rm",
                          "for a in \"$@\"; do\n"
                          "  case \"$a\" in './%s') echo 'rm: refused by the test' >&2; exit 1 ;; esac\n"
                          "done\n"
                          "exec '%s' \"$@\"\n" % (refused, self.real("rm")))
        return str(bin_dir)

    def test_failed_removal_of_output_refused(self):
        """After a good build, a build whose removal of the version-named zip
        fails exits 1 with the packager's removal message; that zip is still
        there, and every other earlier output is gone."""
        refused = "cleanlanguage-%s.zip" % self.version
        self.good_build()
        self.plant()
        self.plant_stale()
        code, stderr = self.build(path_prefix=self.refusing_rm(refused))
        self.assertEqual(code, 1, stderr)
        self.assertIn("rm: refused by the test", stderr)
        self.assertIn(REMOVAL_FAILED, stderr)
        self.assertEqual(outputs(self.dist), [refused], "the build removed the wrong set of earlier outputs")
        self.assert_plants_kept()

    def test_moves_staged_zips_before_checksums(self):
        """A stand-in mv records each move into dist/: each of the 4 is
        `mv -fT -- <work>/<name> <work>/../<name>`, where <work> is a folder
        of dist/ with a work-folder name, and both zips are in dist/ before
        either .sha256 is moved there."""
        bin_dir, log = self.stand_in("mv")
        self.good_build(path_prefix=bin_dir)
        dist = os.path.realpath(self.dist)
        moves = [(present, args) for present, _, args in self.calls(log)
                 if args and OUTPUT_NAME.fullmatch(os.path.basename(args[-1]))]
        self.assertEqual(len(moves), 4, "the moves into dist/ were %r" % moves)
        for present, args in moves:
            self.assertEqual(len(args), 4, "a move into dist/ was %r" % args)
            options, end, source, target = args
            self.assertEqual((options, end), ("-fT", "--"), "a move into dist/ was %r" % args)
            folder, name = os.path.split(source)
            self.assertTrue(WORK_NAME.fullmatch(os.path.basename(folder)),
                            "a move into dist/ took a source outside a work folder: %r" % args)
            self.assertEqual(os.path.realpath(os.path.dirname(folder)), dist,
                             "the work folder of a move is not in dist/: %r" % args)
            self.assertEqual(target, folder + "/../" + name, "a move into dist/ was %r" % args)
            if name.endswith(".sha256"):
                self.assertTrue(all(z in present for z in self.names if z.endswith(".zip")),
                                "a .sha256 was moved into dist/ before both zips were there: %r" % moves)
        self.assertEqual(sorted(os.path.basename(args[-1]) for _, args in moves), self.names)

    def test_no_output_in_dist_during_checks(self):
        bin_dir, log = self.stand_in("unzip")
        self.good_build(path_prefix=bin_dir)
        calls = self.calls(log)
        self.assertTrue(calls, "the build never called unzip")
        for present, _, args in calls:
            self.assertEqual(present, [], "unzip %r ran with %r already in dist/" % (args, present))

    def test_zip_runs_in_layout_folder(self):
        """In a good build with nothing planted, a stand-in zip records 1
        call, which writes cleanlanguage.zip in a folder of dist/ with a
        work-folder name and runs in src/cleanlanguage/ of that folder. A
        build that runs zip in another folder fails this case after 1
        build."""
        bin_dir, log = self.stand_in("zip")
        code, stderr = self.build(path_prefix=bin_dir)
        calls = self.calls(log)
        self.assertEqual(len(calls), 1, "the build called zip %d times: %r" % (len(calls), calls))
        _, cwd, args = calls[0]
        folder, name = os.path.split(args[-1])
        self.assertEqual(name, "cleanlanguage.zip", "zip wrote %r" % args[-1])
        self.assertTrue(WORK_NAME.fullmatch(os.path.basename(folder)), "zip wrote %r outside a work folder" % args[-1])
        self.assertEqual(os.path.realpath(os.path.dirname(folder)), os.path.realpath(self.dist),
                         "the work folder of zip is not in dist/: %r" % args[-1])
        self.assertEqual(cwd, os.path.realpath(os.path.join(folder, "src", "cleanlanguage")),
                         "zip ran in %s, not in src/cleanlanguage/ of its work folder" % cwd)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(outputs(self.dist), self.names)

    def test_symlinked_dist_refused(self):
        target = self.outside("linked-dist")
        for name in ("cleanlanguage.zip", "cleanlanguage-other.zip", "unrelated.txt"):
            (target / name).write_bytes(b"planted in the link target\n")
        before = snapshot(target)
        self.dist.symlink_to(target, target_is_directory=True)
        code, stderr = self.build()
        self.assertEqual(code, 1, stderr)
        self.assertIn(LINKED_DIST, stderr)
        self.assertTrue(self.dist.is_symlink())
        self.assertEqual(snapshot(target), before, "the build changed the folder that dist points at")

    def test_dangling_symlinked_dist_refused(self):
        target = Path(self.tmp.name) / "absent-dist"
        if target.exists():
            shutil.rmtree(target)
        self.dist.symlink_to(target, target_is_directory=True)
        code, stderr = self.build()
        self.assertEqual(code, 1, stderr)
        self.assertIn(LINKED_DIST, stderr)
        self.assertTrue(self.dist.is_symlink())
        self.assertEqual(os.readlink(self.dist), str(target))
        self.assertFalse(os.path.lexists(target), "the build created the missing folder that dist points at")

    def test_file_dist_refused(self):
        self.dist.write_bytes(KEEP_TEXT)
        code, stderr = self.build()
        self.assertEqual(code, 1, stderr)
        self.assertIn("release-package: dist exists and is not a folder", stderr)
        self.assertTrue(self.dist.is_file() and not self.dist.is_symlink())
        self.assertEqual(self.dist.read_bytes(), KEEP_TEXT)

    def test_fifo_dist_refused(self):
        os.mkfifo(self.dist)
        code, stderr = self.build()
        self.assertEqual(code, 1, stderr)
        self.assertIn("release-package: dist exists and is not a folder", stderr)
        self.assertTrue(stat.S_ISFIFO(self.dist.lstat().st_mode), "the build replaced the FIFO dist")

    def assert_no_work_folder(self, log: Path):
        """Assert that the stand-in mktemp whose log is given was never called,
        so the build was refused before it made its work folder, which it
        makes before it writes to dist/."""
        self.assertEqual(self.calls(log), [], "the build made a work folder before it was refused")

    def test_output_name_folder_kept(self):
        self.plant()
        folder = self.dist / "cleanlanguage.zip"
        folder.mkdir()
        (folder / KEEP).write_bytes(KEEP_TEXT)
        bin_dir, log = self.stand_in("mktemp")
        code, stderr = self.build(path_prefix=bin_dir)
        self.assertEqual(snapshot(folder), {KEEP: KEEP_TEXT}, "the build changed the folder %s" % folder)
        self.assertEqual(code, 1, stderr)
        self.assertIn("release-package: dist/cleanlanguage.zip " + REFUSED_NAME, stderr)
        self.assertEqual(outputs(self.dist), [], "a refused build left output in dist/")
        self.assert_plants_kept()
        self.assert_no_work_folder(log)

    def plant_object(self, kind: str, name: str) -> tuple:
        """Plant at dist/<name> an object of the given kind that the packager
        did not write: "link" (to a file outside dist/), "dangling link" or
        "fifo". Return the object's path and, for a link, its target."""
        path = self.dist / name
        target = None
        if kind == "link":
            target = self.outside("object-target") / "target.txt"
            target.write_bytes(KEEP_TEXT)
            path.symlink_to(target)
        elif kind == "dangling link":
            target = self.outside("object-target") / "absent"
            path.symlink_to(target)
        else:
            os.mkfifo(path)
        return path, target

    def assert_object_unchanged(self, kind: str, path: Path, target):
        self.assertTrue(os.path.lexists(path), "the build removed %s, which it did not write" % path)
        if kind == "fifo":
            self.assertTrue(stat.S_ISFIFO(path.lstat().st_mode), "the build replaced the FIFO %s" % path)
            return
        self.assertTrue(path.is_symlink(), "the build replaced the link %s" % path)
        self.assertEqual(os.readlink(path), str(target))
        if kind == "link":
            self.assertEqual(snapshot(target.parent), {target.name: KEEP_TEXT},
                             "the build changed the file that %s points at" % path)
        else:
            self.assertEqual(snapshot(target.parent), {}, "the build created what %s points at" % path)

    def move_then_fail(self) -> str:
        """Write a stand-in mv, first on the PATH, that runs the real mv and,
        for a move of a .sha256 file, then fails. It records nothing. Return
        its folder. The packager refuses an object at an output name before
        any move, so a build that passes the object cases never calls it; a
        build that reached the moves would fail at the first move of a .sha256
        file, after the rename had replaced the object and before the exit
        trap removed what replaced it, so the case fails without the refusal."""
        bin_dir = self.bin_dir("move-then-fail")
        self.write_script(bin_dir / "mv",
                          "'%s' \"$@\" || exit\n"
                          "for a in \"$@\"; do\n"
                          "  case \"$a\" in *.sha256) echo 'mv: failed after the move, by the test' >&2; exit 1 ;; esac\n"
                          "done\n" % self.real("mv"))
        return str(bin_dir)

    def assert_object_refused(self, kind: str, name: str, failed_move: bool):
        path_prefix = ""
        if failed_move:
            path_prefix = self.move_then_fail()
            self.good_build()
        self.plant()
        if failed_move:
            self.plant_stale()
            # The object takes the place of the good build's output of that name.
            (self.dist / name).unlink()
        path, target = self.plant_object(kind, name)
        bin_dir, log = self.stand_in("mktemp")
        code, stderr = self.build(path_prefix=os.pathsep.join(p for p in (path_prefix, bin_dir) if p))
        self.assert_object_unchanged(kind, path, target)
        self.assertEqual(code, 1, stderr)
        self.assertIn("release-package: dist/%s %s" % (name, REFUSED_NAME), stderr)
        self.assertEqual(outputs(self.dist), [], "a refused build left output in dist/")
        self.assert_plants_kept()
        self.assert_no_work_folder(log)

    def test_link_at_zip_name_refused(self):
        self.assert_object_refused("link", "cleanlanguage.zip", failed_move=False)

    def test_link_at_zip_name_refused_with_failed_move(self):
        self.assert_object_refused("link", "cleanlanguage.zip", failed_move=True)

    def test_link_at_zip_checksum_name_refused(self):
        self.assert_object_refused("link", "cleanlanguage.zip.sha256", failed_move=False)

    def test_link_at_checksum_name_refused(self):
        self.assert_object_refused("dangling link", "cleanlanguage-%s.zip.sha256" % self.version,
                                   failed_move=False)

    def test_link_at_checksum_name_refused_with_failed_move(self):
        self.assert_object_refused("dangling link", "cleanlanguage-%s.zip.sha256" % self.version,
                                   failed_move=True)

    def test_fifo_at_output_name_refused(self):
        self.assert_object_refused("fifo", "cleanlanguage-%s.zip" % self.version, failed_move=False)

    def test_fifo_at_output_name_refused_with_failed_move(self):
        self.assert_object_refused("fifo", "cleanlanguage-%s.zip" % self.version, failed_move=True)

    def held_signal(self, proc: subprocess.Popen, held: Path, go: Path, sig: int, what: str) -> str:
        """Wait until the stand-in of proc has written held, send sig, then
        write go so that the stand-in goes on; return the build's stderr."""
        try:
            deadline = time.monotonic() + BUILD_TIMEOUT
            while not held.exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(held.exists(), what)
            proc.send_signal(sig)
            time.sleep(0.2)
        finally:
            go.write_bytes(b"")
            proc.wait(timeout=BUILD_TIMEOUT)
            proc.output.seek(0)
            stderr = proc.output.read().decode("utf-8", "replace")
            proc.output.close()
        return stderr

    def popen_build(self, *args: str, path_prefix: str) -> subprocess.Popen:
        """Start a build that the test signals. Its error output goes to a
        file of the temporary folder, never to a pipe that the test does not
        read while it waits, and its standard output is discarded, so a
        build that writes more than a pipe holds does not block until the
        wait ends; held_signal reads the file."""
        output = tempfile.TemporaryFile(dir=self.tmp.name)
        proc = subprocess.Popen(["bash", str(self.clone / "tools" / "release-package.sh"), *args],
                                cwd=str(self.clone), env=self.packager_env(path_prefix=path_prefix),
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=output,
                                preexec_fn=default_signals)
        proc.output = output
        return proc

    def holding_rm(self, bin_dir: Path):
        """Write into bin_dir a stand-in rm that, at its first call with an
        argument that starts with ./ (a removal in dist/), writes held and
        waits for go, then runs the real rm. Return held and go."""
        held, go = bin_dir / "held", bin_dir / "go"
        self.write_script(bin_dir / "rm",
                          "for a in \"$@\"; do\n"
                          "  case \"$a\" in ./*)\n"
                          "    if [ ! -e '%s' ]; then\n"
                          "      : > '%s'\n"
                          "      n=0\n"
                          "      while [ ! -e '%s' ] && [ \"$n\" -lt 1200 ]; do sleep 0.1; n=$((n + 1)); done\n"
                          "    fi\n"
                          "    break ;;\n"
                          "  esac\n"
                          "done\n"
                          "exec '%s' \"$@\"\n" % (held, held, go, self.real("rm")))
        return held, go

    def assert_signal_ends_build(self, sig: int, code: int):
        """A stand-in mv holds each move of a .sha256 file until the test
        has sent sig to the build, then runs the real mv; the build must exit
        with code and leave no zip and no .sha256 in dist/."""
        bin_dir = self.bin_dir("holding-mv")
        held, go = bin_dir / "held", bin_dir / "go"
        self.write_script(bin_dir / "mv",
                          "for a in \"$@\"; do\n"
                          "  case \"$a\" in *.sha256)\n"
                          "    : > '%s'\n"
                          "    n=0\n"
                          "    while [ ! -e '%s' ] && [ \"$n\" -lt 1200 ]; do sleep 0.1; n=$((n + 1)); done\n"
                          "    break ;;\n"
                          "  esac\n"
                          "done\n"
                          "exec '%s' \"$@\"\n" % (held, go, self.real("mv")))
        self.plant()
        proc = self.popen_build(path_prefix=str(bin_dir))
        stderr = self.held_signal(proc, held, go, sig, "the build never moved a .sha256 file")
        self.assertEqual(proc.returncode, code, stderr)
        self.assertEqual(outputs(self.dist), [], "a build ended by a signal left output in dist/")
        self.assert_plants_kept()

    def test_sigterm_during_move_leaves_nothing(self):
        self.assert_signal_ends_build(signal.SIGTERM, 143)

    def test_sighup_during_move_leaves_nothing(self):
        self.assert_signal_ends_build(signal.SIGHUP, 129)

    def test_sigint_during_move_leaves_nothing(self):
        self.assert_signal_ends_build(signal.SIGINT, 130)

    def assert_signal_during_first_removal(self, sig: int, code: int):
        """After a good build, with the plants and the stale outputs planted
        again, a build refused by --bogus whose stand-in rm holds the first
        removal in dist/ until the test has sent sig to the build, then runs
        the real rm, must exit with code and leave no zip and no .sha256 in
        dist/, neither the good build's nor a stale one."""
        self.good_build()
        self.plant()
        self.plant_stale()
        bin_dir = self.bin_dir("holding-rm")
        held, go = self.holding_rm(bin_dir)
        proc = self.popen_build("--bogus", path_prefix=str(bin_dir))
        stderr = self.held_signal(proc, held, go, sig, "the first removal never removed an entry of dist/")
        self.assertEqual(proc.returncode, code, stderr)
        self.assertNotIn("unknown argument --bogus", stderr)
        self.assertEqual(outputs(self.dist), [], "a build ended during its first removal left output in dist/")
        self.assert_plants_kept()

    def test_sigterm_during_first_removal_leaves_nothing(self):
        self.assert_signal_during_first_removal(signal.SIGTERM, 143)

    def test_sighup_during_first_removal_leaves_nothing(self):
        self.assert_signal_during_first_removal(signal.SIGHUP, 129)

    def test_sigint_during_first_removal_leaves_nothing(self):
        self.assert_signal_during_first_removal(signal.SIGINT, 130)

    def wide_locale(self) -> str:
        """The first of WIDE_LOCALES in which a bash [0-9] takes an
        Arabic-Indic digit, or an empty string."""
        for locale in WIDE_LOCALES:
            proc = subprocess.run(["bash", "-c", "[[ $1 =~ ^[0-9]$ ]]", "probe", chr(0x663)],
                                  env=self.packager_env(extra={"LC_ALL": locale}),
                                  stdin=subprocess.DEVNULL, capture_output=True, timeout=BUILD_TIMEOUT)
            if proc.returncode == 0:
                return locale
        return ""

    def test_name_tests_ignore_locale(self):
        """Under a locale in which a bash range takes a digit outside ASCII,
        a good build, with the plants and NON_ASCII_FILES planted, keeps each
        of the latter unchanged and keeps the planted paths."""
        locale = self.wide_locale()
        if not locale:
            self.skipTest("no locale of %s in which a bash range takes a digit outside ASCII is installed"
                          % ", ".join(WIDE_LOCALES))
        self.plant()
        for name in NON_ASCII_FILES:
            with open(os.path.join(os.fsencode(self.dist), name.encode("utf-8")), "wb") as handle:
                handle.write(KEEP_TEXT)
        code, stderr = self.build(extra={"LC_ALL": locale})
        self.assertEqual(code, 0, stderr)
        self.assertEqual(outputs(self.dist), self.names)
        self.assert_plants_kept()
        for name in NON_ASCII_FILES:
            path = os.path.join(os.fsencode(self.dist), name.encode("utf-8"))
            self.assertTrue(os.path.isfile(path), "the build under %s removed %r" % (locale, name))
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), KEEP_TEXT)

    def assert_inherited_option(self, plant: bool = True, **extra: str):
        """A good build and then a build refused by --bogus, with nothing
        planted again, each with extra in its environment. Without plant,
        the good build starts with an empty dist/, so that no glob of the
        removal matches an entry there."""
        if plant:
            self.good_build(extra=extra)
        else:
            self.dist.mkdir()
            code, stderr = self.build(extra=extra)
            self.assertEqual(code, 0, stderr)
            self.assertEqual(outputs(self.dist), self.names)
        code, stderr = self.build("--bogus", extra=extra)
        self.assertEqual(code, 1, stderr)
        self.assertIn("unknown argument --bogus", stderr)
        self.assertEqual(outputs(self.dist), [], "a refused build left output in dist/")
        if plant:
            self.assert_plants_kept()

    def test_inherited_failglob(self):
        # Nothing is planted: any planted name would give the glob * of the
        # removal a match.
        self.assert_inherited_option(plant=False, BASHOPTS="failglob")

    def test_inherited_dotglob(self):
        self.assert_inherited_option(BASHOPTS="dotglob")

    def test_inherited_nocasematch(self):
        self.assert_inherited_option(BASHOPTS="nocasematch")

    def test_inherited_noglob(self):
        self.assert_inherited_option(SHELLOPTS="noglob")

    def test_inherited_globignore(self):
        self.assert_inherited_option(GLOBIGNORE=GLOBIGNORE_VALUE)

    def test_globignore_from_bash_env(self):
        # Bash 5.3.9 applies a GLOBIGNORE that a BASH_ENV file assigns, but
        # not one that it takes from its environment.
        bash_env = self.outside("bash-env") / "globignore.sh"
        bash_env.write_text("GLOBIGNORE='%s'\n" % GLOBIGNORE_VALUE, encoding="ascii")
        self.assert_inherited_option(BASH_ENV=str(bash_env))

    def trap_stand_ins(self, move_exit: int = 0, refused: str = "") -> tuple:
        """Write a stand-in mktemp that writes the full path of each work
        folder it makes to its log; with move_exit, a stand-in mv that refuses
        each move of a .sha256 file with that exit code; and with refused, a
        stand-in rm that fails, without removing anything, at the argument
        refused, where @1 names the path of the work folder in the log, the
        operand by which the exit trap removes it. Return the folder and the
        log."""
        bin_dir = self.bin_dir("trap-stand-ins")
        log = bin_dir / "work-folders.log"
        self.write_script(bin_dir / "mktemp",
                          "p=$('%s' \"$@\") || exit\n"
                          "case \"$p\" in /*) full=$p ;; *) full=\"$(pwd -P)/$p\" ;; esac\n"
                          "printf '%%s\\n' \"$full\" >> '%s'\n"
                          "printf '%%s\\n' \"$p\"\n" % (self.real("mktemp"), log))
        if move_exit:
            self.write_script(bin_dir / "mv",
                              "for a in \"$@\"; do\n"
                              "  case \"$a\" in *.sha256) echo 'mv: refused by the test' >&2; exit %d ;; esac\n"
                              "done\n"
                              "exec '%s' \"$@\"\n" % (move_exit, self.real("mv")))
        if refused:
            self.write_script(bin_dir / "rm",
                              "target='%s'\n"
                              "case \"$target\" in\n"
                              "  @1) target=$(sed -n 1p '%s') ;;\n"
                              "esac\n"
                              "for a in \"$@\"; do\n"
                              "  if [ \"$a\" = \"$target\" ]; then echo 'rm: refused by the test' >&2; exit 1; fi\n"
                              "done\n"
                              "exec '%s' \"$@\"\n" % (refused, log, self.real("rm")))
        return str(bin_dir), log

    def work_folder(self, log: Path) -> Path:
        folders = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        self.assertEqual(len(folders), 1, "the build made the work folders %r" % folders)
        return Path(folders[0])

    def test_good_build_removes_work_folder(self):
        bin_dir, log = self.trap_stand_ins()
        self.good_build(path_prefix=bin_dir)
        folder = self.work_folder(log)
        self.assertFalse(os.path.lexists(folder), "the build left its work folder %s" % folder)

    def assert_trap(self, move_exit: int, refused: str):
        """A build whose stand-in mv, with move_exit, refuses each move of a
        .sha256 file with that exit code, and whose stand-in rm fails at
        refused, exits with move_exit, or 0 without it; the path that
        refused names is still there, the work folder is gone unless rm
        failed at it, and so is every other output of a failed build."""
        bin_dir, log = self.trap_stand_ins(move_exit, refused)
        self.plant()
        code, stderr = self.build(path_prefix=bin_dir)
        self.assertEqual(code, move_exit, stderr)
        if move_exit:
            self.assertIn("mv: refused by the test", stderr)
        folder = self.work_folder(log)
        if refused == "@1":
            self.assertTrue(folder.is_dir(), "the stand-in rm did not keep %s" % folder)
        else:
            self.assertFalse(os.path.lexists(folder), "the build left its work folder %s" % folder)
        expected = [] if move_exit else list(self.names)
        if refused.startswith("./"):
            expected.append(refused[len("./"):])
        if refused == "@1":
            expected.append(folder.name)
        self.assertEqual(outputs(self.dist), sorted(expected), "the exit trap removed the wrong set of outputs")
        self.assert_plants_kept()
        if refused == "@1":
            shutil.rmtree(folder)

    def test_failed_build_keeps_exit_code_and_removes_work_folder(self):
        self.assert_trap(MOVE_EXIT, "")

    def test_trap_continues_after_failed_output_removal(self):
        self.assert_trap(MOVE_EXIT, "./cleanlanguage.zip")

    def test_failed_build_keeps_exit_code_after_failed_work_folder_removal(self):
        self.assert_trap(MOVE_EXIT, "@1")

    def test_good_build_exits_0_after_failed_work_folder_removal(self):
        self.assert_trap(0, "@1")

    def assert_signal_during_trap(self, sig: int):
        """A build whose stand-in mv refuses each move of a .sha256 file with
        MOVE_EXIT, and whose stand-in rm holds the first removal of the exit
        trap until the test has sent sig to the build, must still complete
        the removals of the trap and exit with MOVE_EXIT. Nothing is planted,
        so the trap makes the first removal in dist/ of the build."""
        bin_dir, log = self.trap_stand_ins(MOVE_EXIT)
        held, go = self.holding_rm(Path(bin_dir))
        proc = self.popen_build(path_prefix=bin_dir)
        stderr = self.held_signal(proc, held, go, sig, "the exit trap never removed an output from dist/")
        self.assertEqual(proc.returncode, MOVE_EXIT, stderr)
        self.assertIn("mv: refused by the test", stderr)
        self.assertEqual(outputs(self.dist), [], "a signal cut the removals of the exit trap short")
        folder = self.work_folder(log)
        self.assertFalse(os.path.lexists(folder), "the build left its work folder %s" % folder)

    def test_sigterm_during_exit_trap_ignored(self):
        self.assert_signal_during_trap(signal.SIGTERM)

    def test_sighup_during_exit_trap_ignored(self):
        self.assert_signal_during_trap(signal.SIGHUP)

    def test_sigint_during_exit_trap_ignored(self):
        self.assert_signal_during_trap(signal.SIGINT)

    def test_name_test_edges(self):
        """After a good build, a build refused by --bogus keeps the planted
        paths, among them the regular file Cleanlanguage.zip (an output name
        with a capital initial, which the near misses hold), and removes the
        2 outputs of version 11111111111.0.0, whose first part has 11
        digits."""
        self.assertIn("Cleanlanguage.zip", self.output_misses)
        self.good_build()
        kept_file = self.dist / "Cleanlanguage.zip"
        for name in ("cleanlanguage-11111111111.0.0.zip", "cleanlanguage-11111111111.0.0.zip.sha256"):
            (self.dist / name).write_bytes(b"stale\n")
        code, stderr = self.build("--bogus")
        self.assertEqual(code, 1, stderr)
        self.assertIn("unknown argument --bogus", stderr)
        self.assertTrue(kept_file.is_file(), "the build removed %s" % kept_file)
        self.assertEqual(outputs(self.dist), [], "a refused build left output in dist/")
        self.assert_plants_kept()

    def test_only_recursive_removal_is_work_folder(self):
        """The packager's code, comment lines set aside, holds exactly 1 rm
        with a recursive option, the removal of the work folder by the path
        that mktemp gave; no rmdir in a for or while loop, no rmdir with its
        parents option, and no find -delete."""
        text = (self.clone / "tools" / "release-package.sh").read_text(encoding="utf-8")
        recursive, looped_rmdir, other = [], [], []
        depth = 0
        for number, line in code_lines(text):
            words = line.split()
            if words[0] in ("for", "while", "until"):
                depth += 1
            for index, word in enumerate(words):
                if word == "rm":
                    options = []
                    for option in words[index + 1:]:
                        if not option.startswith("-") or option == "--":
                            break
                        options.append(option)
                    if any(RECURSIVE_OPTION.fullmatch(o) for o in options):
                        recursive.append((number, line.strip()))
                if word == "rmdir":
                    if depth:
                        looped_rmdir.append((number, line.strip()))
                    if any(w in ("-p", "--parents") for w in words[index + 1:]):
                        other.append((number, line.strip()))
                if word == "-delete":
                    other.append((number, line.strip()))
            if words[0] == "done" or words[-1] == "done":
                depth = max(depth - 1, 0)
        self.assertEqual([line for _, line in recursive], ['rm -rf -- "${work}" || true'],
                         "the recursive removals are %r" % recursive)
        self.assertEqual(looped_rmdir, [], "rmdir runs in a loop at %r" % looped_rmdir)
        self.assertEqual(other, [], "other recursive or repeated removals: %r" % other)
        self.assertIn('work="$(mktemp -d "${PWD}/dist/.release-package.XXXXXX")"',
                      [line.strip() for _, line in code_lines(text)])

    def recording_rm(self, bin_dir: Path) -> Path:
        """Write into bin_dir a stand-in rm that writes each call's arguments,
        separated by tabs, as 1 line of its log, then runs the real rm.
        Return the log."""
        log = bin_dir / "rm-calls.log"
        self.write_script(bin_dir / "rm",
                          "line=\n"
                          "for a in \"$@\"; do line=\"$line$a\t\"; done\n"
                          "printf '%%s\\n' \"$line\" >> '%s'\n"
                          "exec '%s' \"$@\"\n" % (log, self.real("rm")))
        return log

    def recursive_removals(self, log: Path) -> list:
        """The operands of each recorded rm call with a recursive option."""
        found = []
        for line in (log.read_text(encoding="utf-8").splitlines() if log.exists() else []):
            args = [a for a in line.split("\t") if a]
            options, operands = [], []
            for index, arg in enumerate(args):
                if arg == "--":
                    operands = args[index + 1:]
                    break
                if not arg.startswith("-"):
                    operands = args[index:]
                    break
                options.append(arg)
            if any(RECURSIVE_OPTION.fullmatch(o) for o in options):
                found.append(operands)
        return found

    def test_recursive_removal_only_of_work_folder(self):
        """A stand-in rm records each call and a stand-in mktemp the work
        folder: a good build, a build refused by the blob check, and a build
        whose move of the .sha256 files fails each call rm with a recursive
        option exactly once, with the path that mktemp gave as its only
        operand; a build refused by --bogus calls it never."""
        for label, args, autocrlf, move_exit in (("good", (), False, 0), ("blob", (), True, 0),
                                                  ("move", (), False, MOVE_EXIT), ("bogus", ("--bogus",), False, 0)):
            with self.subTest(label):
                self.setUp()
                bin_dir, work_log = self.trap_stand_ins(move_exit)
                rm_log = self.recording_rm(Path(bin_dir))
                self.plant()
                code, stderr = self.build(*args, autocrlf=autocrlf, path_prefix=bin_dir)
                self.assertEqual(code, {"good": 0, "blob": 1, "move": MOVE_EXIT, "bogus": 1}[label], stderr)
                removals = self.recursive_removals(rm_log)
                if label == "bogus":
                    self.assertFalse(work_log.exists(), "the build refused by --bogus made a work folder")
                    self.assertEqual(removals, [], "the build refused by --bogus removed %r" % removals)
                else:
                    self.assertEqual(removals, [[str(self.work_folder(work_log))]],
                                     "the recursive removals were %r" % removals)
                self.assert_plants_kept()

    def test_leftover_work_folders_kept(self):
        """A folder with a work-folder name that holds a file, as a SIGKILL
        could leave, is kept unchanged by a good build, by a build refused
        by --bogus, by a build refused by the blob check, and by a build
        whose move of the .sha256 files fails."""
        self.good_build()
        for label, args, autocrlf, prefix in (("bogus", ("--bogus",), False, ""), ("blob", (), True, ""),
                                              ("move", (), False, self.refusing_mv("leftover-mv", 1))):
            with self.subTest(label):
                code, stderr = self.build(*args, autocrlf=autocrlf, path_prefix=prefix)
                self.assertEqual(code, 1, stderr)
                self.assertEqual(outputs(self.dist), [], "a refused build left output in dist/")
                self.assert_plants_kept()

    def test_dist_link_after_mkdir_refused(self):
        """A stand-in mkdir, at the build's `mkdir -p dist`, first puts at
        dist a symbolic link to a folder outside the clone that holds a file
        named cleanlanguage.zip, then runs the real mkdir. The build exits 1
        with the message for a linked dist before it makes its work folder;
        the outside folder is unchanged."""
        target = self.outside("late-linked-dist")
        (target / "cleanlanguage.zip").write_bytes(b"a reader's file\n")
        before = snapshot(target)
        bin_dir, log = self.stand_in("mktemp")
        mkdir_dir = self.bin_dir("linking-mkdir")
        made = mkdir_dir / "linked"
        self.write_script(mkdir_dir / "mkdir",
                          "if [ \"$1\" = -p ] && [ \"$2\" = dist ] && [ ! -e '%s' ]; then\n"
                          "  : > '%s'\n"
                          "  '%s' -s '%s' dist || exit 1\n"
                          "fi\n"
                          "exec '%s' \"$@\"\n" % (made, made, self.real("ln"), target, self.real("mkdir")))
        code, stderr = self.build(path_prefix=os.pathsep.join((str(mkdir_dir), bin_dir)))
        self.assertTrue(made.exists(), "the stand-in mkdir never linked dist")
        self.assertEqual(code, 1, stderr)
        self.assertIn(LINKED_DIST, stderr)
        self.assertTrue(self.dist.is_symlink())
        self.assertEqual(snapshot(target), before, "the build changed the folder that dist points at")
        self.assert_no_work_folder(log)

    def last_cmp(self, bin_dir: Path, action: str):
        """Write into bin_dir a stand-in cmp that runs the real cmp and, after
        its call number entry_count, the last check before the moves, runs
        the sh lines of action."""
        count = bin_dir / "cmp-count"
        self.write_script(bin_dir / "cmp",
                          "'%s' \"$@\"\n"
                          "rc=$?\n"
                          "n=$(($(cat '%s' 2>/dev/null || echo 0) + 1))\n"
                          "echo \"$n\" > '%s'\n"
                          "if [ \"$n\" -eq %d ]; then\n"
                          "%s"
                          "fi\n"
                          "exit \"$rc\"\n" % (self.real("cmp"), count, count, self.entry_count, action))

    def test_folder_at_output_name_after_refusal_fails_move(self):
        """A stand-in cmp, after its last call, makes a folder holding KEEP
        at dist/cleanlanguage.zip. The first move, `mv -fT`, fails rather
        than move the zip into that folder; the folder is unchanged, and
        dist/ holds no zip and no .sha256."""
        bin_dir = self.bin_dir("folder-cmp")
        folder = self.dist / "cleanlanguage.zip"
        self.last_cmp(bin_dir, "'%s' '%s' || exit 1\n"
                               "printf 'a file the packager does not write\\n' > '%s/%s' || exit 1\n"
                      % (self.real("mkdir"), folder, folder, KEEP))
        code, stderr = self.build(path_prefix=str(bin_dir))
        self.assertTrue(folder.is_dir(), "the stand-in cmp never made the folder")
        self.assertNotEqual(code, 0, stderr)
        self.assertEqual(snapshot(folder), {KEEP: KEEP_TEXT}, "the build moved into, or changed, %s" % folder)
        self.assertEqual(outputs(self.dist), [], "dist/ holds %r" % outputs(self.dist))

    def test_work_folder_moved_before_moves_fails(self):
        """A stand-in cmp, after its last call, moves the work folder into a
        folder outside the clone. The first move fails, since its source is
        no longer at the path that mktemp gave; the moved folder holds src/
        and the 4 staged files, and dist/ holds no output and no work
        folder."""
        bin_dir, log = self.trap_stand_ins()
        outside = self.outside("moved-work-parent")
        self.last_cmp(Path(bin_dir), "'%s' \"$(sed -n 1p '%s')\" '%s/' || exit 1\n"
                      % (self.real("mv"), log, outside))
        code, stderr = self.build(path_prefix=bin_dir)
        self.assertNotEqual(code, 0, stderr)
        entries = sorted(outside.iterdir())
        self.assertEqual(len(entries), 1, "the outside folder holds %r" % entries)
        self.assertEqual(entries[0].name, self.work_folder(log).name)
        self.assertEqual(sorted(p.name for p in entries[0].iterdir()), sorted(self.names + ["src"]))
        self.assertEqual(outputs(self.dist), [], "dist/ holds %r" % outputs(self.dist))


if __name__ == "__main__":
    unittest.main()
