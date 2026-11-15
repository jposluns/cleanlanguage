#!/usr/bin/env python3
"""Check what tools/release-package.sh leaves in dist/ after each build.

The packager is meant to work as follows, and the cases below check it at
the builds and on the planted paths that they name. A build that passes
every check writes dist/cleanlanguage.zip, dist/cleanlanguage-<version>.zip
and a .sha256 beside each. A build that is refused at a check, or ended by
SIGHUP, SIGINT or SIGTERM, must leave no zip and no .sha256 in dist/,
neither a new one nor one that an earlier build wrote, so that a reader
cannot take a stale or unverified zip for the refused build; a removal that
fails is the exception, and then the build fails and the output it could
not remove stays. The packager removes entries of dist/ by name and type: a
regular file with an output name, and a folder with a staging name together
with everything that folder holds, whoever wrote it. It keeps the other
entries of dist/ that the cases plant. A build refuses with exit 1 when 1
of the 4 names it writes is held by a symbolic link, folder, FIFO or other
object that is not a regular file, since its rename into dist/ would
replace that object; it refuses after it has removed the outputs of an
earlier build and before it makes its first work folder, so before it
writes anything to dist/. A build refuses with exit 1 when dist is renamed
or replaced by a symbolic link while it runs, and then removes nothing
through the new dist.

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
temporary folder and puts first on the PATH of 1 build.

The near-miss plants are generated, not picked by hand (near_misses): from
each of the 4 output names of the version at HEAD, from the 2 output names
of SAMPLE_VERSION (1.0.0), whose version parts have 1 digit each, and from
the staging name .release-package.AbC123, every name made by deleting 1
character, inserting
1 character of ALPHABET (a letter, a digit, a dot, a hyphen, an underscore)
at any position, or replacing 1 character by 1 of ALPHABET, and the name in
capital letters; and the 4 names that repeat an optional group of an output
name (a second version part, a second .sha256). A name that is itself an
output name or a staging name is left out. Each name made from an output
name is planted as a regular file, and each name made from the staging name
as a folder that holds a file; 1 case plants the latter as regular files.
So a loosening of either name test of the removal that admits a name of
this set removes a plant, and a case fails; a loosening that admits only
names outside the set, such as a name 2 edits away, is not caught by it.
Besides these, the test plants a plain file, a folder of scripts, a folder
at the output name of another version, a regular file with a staging name
(OTHER_PLANTS), a symbolic link with a staging name to a folder outside
dist/ (STAGING_LINK), and 2 leftover staging folders (LEFTOVER_STAGING),
each holding a file. After each build that follows a planting, each planted
path must be there with its bytes unchanged, the link must still point at
the same unchanged folder, and the leftover staging folders must be gone,
except the 1 at which the stand-in rm of case 10 fails, which must still
hold its file. Before each refused build of cases 2 to 4 and 10, and each
build of case 9 that follows a good build, the test also plants the 2
outputs of an earlier build for version STALE_VERSION. The reference build,
the build with no dist/ in case 1, case 7 and the builds of case 11 that
receive a signal while the exit trap runs plant nothing in dist/; case 7
makes dist itself a link, a file or a FIFO.

In its set-up, before any case, the test builds the clone with the packager
of REFERENCE_COMMIT, which gives the reference digest. The cases, all in
that clone:

1. A good build with the checkout's packager exits 0, writes the 4 outputs,
   and gives the reference digest for both zips with matching .sha256 files;
   it keeps the planted paths and removes the leftover staging folders. A
   good build with no dist/ exits 0 and writes the 4 outputs. A good build
   and then a refused build with the staging near misses planted as regular
   files keep them.
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
5. In a good build, a stand-in mv records each move into dist/: each source
   lies in a staging folder inside dist/, and both zips are in dist/ before
   either .sha256 is moved there.
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
    version-named zip, and a build whose stand-in rm fails at the first
    leftover staging folder, each exit 1 with the packager's message for a
    failed removal; the path that the stand-in refused is still there, and
    each other earlier output and leftover staging folder is gone.
11. A build that receives SIGTERM, SIGHUP or SIGINT while a stand-in mv
    holds the move of the .sha256 files exits 143, 129 or 130, and leaves
    no zip and no .sha256 in dist/. A build whose stand-in mv refuses each
    move of a .sha256 file with exit 7, and that receives SIGTERM, SIGHUP
    or SIGINT while a stand-in rm holds the first removal of its exit trap,
    exits 7, leaves no zip and no .sha256 in dist/, and leaves neither of
    its 2 work folders. The test resets the 3 signals to their default
    action in the build's process, since bash cannot trap a signal that
    was ignored when it started.
12. With BASHOPTS=dotglob, BASHOPTS=nocasematch, SHELLOPTS=noglob,
    GLOBIGNORE=dist/*, or BASH_ENV naming a file that assigns
    GLOBIGNORE=dist/*, in its environment, a good build keeps the planted
    paths and removes the leftover staging folders, and a build refused by
    --bogus after it, with nothing planted again, leaves no zip and no
    .sha256 in dist/. With BASHOPTS=failglob, a good build that starts
    with an empty dist/, where nothing is planted, writes the 4 outputs,
    and a build refused by --bogus after it leaves no zip and no .sha256
    in dist/.
13. A build in which dist is renamed and replaced by a symbolic link to a
    folder outside the clone, by a stand-in mktemp after its first call, by
    a stand-in mktemp before its second call, by a stand-in mktemp after
    its second call, or by a stand-in cmp after its last call, exits 1 with
    the packager's message; the outside folder, which holds a file named
    cleanlanguage.zip, is unchanged, and the renamed dist holds no file
    with an output name. After the first 2, it also holds no staging
    folder; after the last 2, the staging folder that the build made stays
    in it, since the build can reach it only through the name dist. A build
    in which a stand-in mktemp, after its first call, renames dist and
    makes a new empty folder dist in its place exits 1 with that message;
    the new folder stays empty, and the renamed dist holds no file with an
    output name and no staging folder. In each of these builds the
    stand-in is not called again after the call at which it replaced dist,
    so a build whose dist was replaced after the first mktemp call makes
    no staging folder at all.
14. A stand-in mktemp records the 2 work folders of a build. After a good
    build, and after a build whose stand-in mv refuses each move of a
    .sha256 file with exit 7, both are gone; the failed build exits 7 and
    leaves no zip and no .sha256 in dist/. In a build with that mv, a
    stand-in rm that fails at dist/cleanlanguage.zip or at the first work
    folder leaves that path in place; the build still exits 7, and every
    other output and work folder is gone. In a good build, a stand-in rm
    that fails at the second work folder, which a failed build has already
    removed with the earlier outputs, leaves that folder in place; the
    build still exits 0 with its 4 outputs, and the first work folder is
    gone.

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
# The staging name from which the staging near misses are made.
STAGING_SAMPLE = ".release-package.AbC123"
# A second version for the near misses, whose parts have 1 digit each, so
# that deleting 1 character can leave a version part empty whatever the
# version at HEAD is.
SAMPLE_VERSION = "1.0.0"
# Entries of dist/ that the packager did not write and that are not near
# misses, each of which a build must keep byte for byte: a plain file, a
# folder of scripts, a folder at the output name of another version, and a
# regular file with a staging name.
OTHER_PLANTS = {
    KEEP: KEEP_TEXT,
    "edit-scripts/keep.py": b"print('kept')\n",
    "cleanlanguage-1.0.0.zip/keep.txt": b"a folder with an output name\n",
    ".release-package.FiLe12": b"a file with a staging name\n",
}
# An earlier build's outputs for another version, planted before each refused
# build; each version part has 2 or more digits, so that a version test that
# takes only 1 digit in a part keeps them.
STALE_VERSION = "10.20.30"
# A symbolic link with a staging name, to a folder outside dist/ that holds
# STAGING_LINK_FILE; the build must keep the link and leave the folder as it is.
STAGING_LINK = ".release-package.LnK456"
STAGING_LINK_FILE = "keep.txt"
# 2 leftover staging folders, each holding a file, which a build must remove;
# 2, so that a removal that stops at its first failure leaves the second.
LEFTOVER_STAGING = (".release-package.AbC123", ".release-package.zZ9999")
REFUSED_NAME = "exists and is not a regular file that the packager wrote"
REMOVAL_FAILED = ("release-package: could not remove every earlier output from dist/; "
                  "any it could not remove is still there")
DIST_REPLACED = ("release-package: dist was replaced while the build ran; "
                 "the packager writes only into the dist/ folder it checked at the start")
OUTPUT_NAME = re.compile(r"cleanlanguage(-[0-9]+\.[0-9]+\.[0-9]+)?\.zip(\.sha256)?")
STAGING_NAME = re.compile(r"\.release-package\.[A-Za-z0-9]{6}")
# Variables of the test's own environment that would change how bash globs
# and matches, or run code before the packager; no build inherits them.
SHELL_VARIABLES = ("BASHOPTS", "SHELLOPTS", "GLOBIGNORE", "BASH_ENV")
BUILD_TIMEOUT = 300
# The exit code of the stand-in mv that refuses a move with a code other than 1.
MOVE_EXIT = 7


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True, timeout=BUILD_TIMEOUT).stdout


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def edits(name: str) -> set:
    """Every name made from name by deleting 1 character, inserting 1
    character of ALPHABET at any position, or replacing 1 character by 1 of
    ALPHABET, and name in capital letters."""
    made = {name.upper()}
    for i in range(len(name) + 1):
        for c in ALPHABET:
            made.add(name[:i] + c + name[i:])
    for i in range(len(name)):
        made.add(name[:i] + name[i + 1:])
        for c in ALPHABET:
            made.add(name[:i] + c + name[i + 1:])
    return made


def near_misses(version: str) -> tuple:
    """The near misses of the output names of version and of SAMPLE_VERSION
    and of the staging name, as 2 sorted lists: those made from an output
    name, which include the 4 names that repeat an optional group, and those
    made from the staging name. No name in either is an output name or a
    staging name."""
    outputs = ["cleanlanguage.zip"] + ["cleanlanguage-%s.zip" % v for v in (version, SAMPLE_VERSION)]
    outputs += [n + ".sha256" for n in outputs]
    from_outputs = set().union(*(edits(n) for n in outputs))
    from_outputs |= {"cleanlanguage-%s-%s.zip" % (version, version),
                     "cleanlanguage-%s-%s.zip.sha256" % (version, version),
                     "cleanlanguage.zip.sha256.sha256",
                     "cleanlanguage-%s.zip.sha256.sha256" % version}
    from_staging = edits(STAGING_SAMPLE) - from_outputs

    def usable(name: str) -> bool:
        return (name not in ("", ".", "..") and "/" not in name
                and not OUTPUT_NAME.fullmatch(name) and not STAGING_NAME.fullmatch(name)
                and name.split("/")[0] not in {p.split("/")[0] for p in OTHER_PLANTS})

    return sorted(filter(usable, from_outputs)), sorted(filter(usable, from_staging))


def outputs(dist: Path) -> list:
    """Every regular file in dist/ with an output name, and every staging
    folder; a symbolic link is neither."""
    if not dist.is_dir() or dist.is_symlink():
        return []
    return sorted(p.name for p in dist.iterdir()
                  if not p.is_symlink()
                  and ((OUTPUT_NAME.fullmatch(p.name) and p.is_file())
                       or (STAGING_NAME.fullmatch(p.name) and p.is_dir())))


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
        cls.moved_dist = cls.clone / "dist.real"
        skill = git("-C", str(cls.clone), "show", "HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md")
        cls.version = next(line.split(":", 1)[1].strip() for line in skill.decode("utf-8").splitlines()
                           if line.startswith("Version:"))
        cls.names = ["cleanlanguage-%s.zip" % cls.version, "cleanlanguage-%s.zip.sha256" % cls.version,
                     "cleanlanguage.zip", "cleanlanguage.zip.sha256"]
        cls.output_misses, cls.staging_misses = near_misses(cls.version)
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
        for path in (self.dist, self.moved_dist):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            elif os.path.lexists(path):
                path.unlink()

    def plants(self, staging_as_files: bool = False) -> dict:
        """The planted files: OTHER_PLANTS, each near miss made from an output
        name as a regular file, and each near miss made from the staging name
        as a folder holding KEEP, or as a regular file."""
        planted = dict(OTHER_PLANTS)
        for name in self.output_misses:
            planted[name] = name.encode("ascii") + b"\n"
        for name in self.staging_misses:
            planted[name if staging_as_files else name + "/" + KEEP] = name.encode("ascii") + b"\n"
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

    def plant(self, staging_as_files: bool = False):
        """Plant the files of plants(), STAGING_LINK and the leftover staging
        folders, each holding a file."""
        self.dist.mkdir(exist_ok=True)
        for rel, data in self.plants(staging_as_files).items():
            path = self.dist / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        link = self.dist / STAGING_LINK
        if not link.is_symlink():
            target = self.outside("staging-link-target")
            (target / STAGING_LINK_FILE).write_bytes(KEEP_TEXT)
            link.symlink_to(target, target_is_directory=True)
        for name in LEFTOVER_STAGING:
            (self.dist / name).mkdir(exist_ok=True)
            (self.dist / name / "cleanlanguage.zip").write_bytes(b"left by a killed build\n")

    def assert_plants_kept(self, kept_staging: str = "", staging_as_files: bool = False):
        """Assert that every plant is unchanged and that every leftover
        staging folder is gone, except kept_staging, whose file must be there."""
        for rel, data in self.plants(staging_as_files).items():
            path = self.dist / rel
            self.assertTrue(path.is_file() and not path.is_symlink(),
                            "the build removed %s, which it did not write" % path)
            self.assertEqual(path.read_bytes(), data, "the build changed %s, which it did not write" % path)
        link = self.dist / STAGING_LINK
        target = Path(self.tmp.name) / "staging-link-target"
        self.assertTrue(link.is_symlink(), "the build removed the link %s, which it did not write" % link)
        self.assertEqual(os.readlink(link), str(target))
        self.assertEqual(snapshot(target), {STAGING_LINK_FILE: KEEP_TEXT},
                         "the build changed the folder that %s points at" % STAGING_LINK)
        for name in LEFTOVER_STAGING:
            if name == kept_staging:
                self.assertEqual(snapshot(self.dist / name), {"cleanlanguage.zip": b"left by a killed build\n"},
                                 "the build changed %s, which it could not remove" % name)
            else:
                self.assertFalse((self.dist / name).exists(), "the build kept the leftover staging folder %s" % name)

    def good_build(self, path_prefix: str = "", extra: dict = None, staging_as_files: bool = False):
        self.plant(staging_as_files)
        code, stderr = self.build(path_prefix=path_prefix, extra=extra)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(outputs(self.dist), self.names)
        self.assert_plants_kept(staging_as_files=staging_as_files)

    def plant_stale(self):
        """Plant the outputs of an earlier build for STALE_VERSION."""
        (self.dist / ("cleanlanguage-%s.zip" % STALE_VERSION)).write_bytes(b"stale")
        (self.dist / ("cleanlanguage-%s.zip.sha256" % STALE_VERSION)).write_bytes(b"stale\n")

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
        present in dist/, separated by commas, then each argument after a
        tab. It then runs the real command."""
        real = self.real(name)
        bin_dir = Path(self.tmp.name) / ("record-" + name)
        bin_dir.mkdir(exist_ok=True)
        log = bin_dir / "calls.log"
        if log.exists():
            log.unlink()
        self.write_script(bin_dir / name,
                          "line=\n"
                          "for n in %s; do\n"
                          "  if [ -e \"dist/$n\" ]; then line=\"$line$n,\"; fi\n"
                          "done\n"
                          "for a in \"$@\"; do line=\"$line\t$a\"; done\n"
                          "printf '%%s\\n' \"$line\" >> '%s'\n"
                          "exec '%s' \"$@\"\n" % (" ".join(self.names), log, real))
        return str(bin_dir), log

    @staticmethod
    def calls(log: Path) -> list:
        """Each recorded call as (the output names present, the arguments)."""
        if not log.exists():
            return []
        result = []
        for line in log.read_text(encoding="utf-8").splitlines():
            present, *args = line.split("\t")
            result.append(([n for n in present.split(",") if n], args))
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

    def test_staging_near_misses_as_files_kept(self):
        self.good_build(staging_as_files=True)
        self.plant(staging_as_files=True)
        self.plant_stale()
        code, stderr = self.build("--bogus")
        self.assertEqual(code, 1, stderr)
        self.assertIn("unknown argument --bogus", stderr)
        self.assertEqual(outputs(self.dist), [], "a refused build left output in dist/")
        self.assert_plants_kept(staging_as_files=True)

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
        anything, at any call with the argument dist/<refused>, and runs the
        real rm for every other call. It records nothing. Return its folder."""
        bin_dir = self.bin_dir("refusing-rm")
        self.write_script(bin_dir / "rm",
                          "for a in \"$@\"; do\n"
                          "  case \"$a\" in 'dist/%s') echo 'rm: refused by the test' >&2; exit 1 ;; esac\n"
                          "done\n"
                          "exec '%s' \"$@\"\n" % (refused, self.real("rm")))
        return str(bin_dir)

    def assert_failed_removal(self, refused: str):
        """After a good build, a build whose removal of dist/<refused> fails
        exits 1 with the packager's removal message; dist/<refused> is still
        there, and every other earlier output and leftover staging folder is
        gone."""
        self.good_build()
        self.plant()
        self.plant_stale()
        code, stderr = self.build(path_prefix=self.refusing_rm(refused))
        self.assertEqual(code, 1, stderr)
        self.assertIn("rm: refused by the test", stderr)
        self.assertIn(REMOVAL_FAILED, stderr)
        self.assertEqual(outputs(self.dist), [refused], "the build removed the wrong set of earlier outputs")
        self.assert_plants_kept(kept_staging=refused if refused in LEFTOVER_STAGING else "")

    def test_failed_removal_of_output_refused(self):
        self.assert_failed_removal("cleanlanguage-%s.zip" % self.version)

    def test_failed_removal_of_staging_folder_refused(self):
        self.assert_failed_removal(LEFTOVER_STAGING[0])

    def test_moves_staged_zips_before_checksums(self):
        bin_dir, log = self.stand_in("mv")
        self.good_build(path_prefix=bin_dir)
        staged = re.compile(re.escape(str(self.dist)) + r"/\.release-package\.[A-Za-z0-9]{6}/[^/]+")
        moves = [(present, [a for a in args[:-1] if not a.startswith("-")])
                 for present, args in self.calls(log) if args and args[-1].rstrip("/") == "dist"]
        moved = [os.path.basename(source) for _, sources in moves for source in sources]
        self.assertEqual(sorted(moved), self.names, "the moves into dist/ were %r" % moves)
        zips = [n for n in self.names if n.endswith(".zip")]
        for present, sources in moves:
            for source in sources:
                self.assertRegex(source, staged, "a move into dist/ took a source outside a staging folder")
            if any(s.endswith(".sha256") for s in sources):
                self.assertTrue(all(z in present for z in zips),
                                "a .sha256 was moved into dist/ before both zips were there: %r" % moves)

    def test_no_output_in_dist_during_checks(self):
        bin_dir, log = self.stand_in("unzip")
        self.good_build(path_prefix=bin_dir)
        calls = self.calls(log)
        self.assertTrue(calls, "the build never called unzip")
        for present, args in calls:
            self.assertEqual(present, [], "unzip %r ran with %r already in dist/" % (args, present))

    def test_symlinked_dist_refused(self):
        target = self.outside("linked-dist")
        for name in ("cleanlanguage.zip", "cleanlanguage-other.zip", "unrelated.txt"):
            (target / name).write_bytes(b"planted in the link target\n")
        before = snapshot(target)
        self.dist.symlink_to(target, target_is_directory=True)
        code, stderr = self.build()
        self.assertEqual(code, 1, stderr)
        self.assertIn("release-package: dist is a symbolic link; the packager writes only into a real dist/ folder",
                      stderr)
        self.assertTrue(self.dist.is_symlink())
        self.assertEqual(snapshot(target), before, "the build changed the folder that dist points at")

    def test_dangling_symlinked_dist_refused(self):
        target = Path(self.tmp.name) / "absent-dist"
        if target.exists():
            shutil.rmtree(target)
        self.dist.symlink_to(target, target_is_directory=True)
        code, stderr = self.build()
        self.assertEqual(code, 1, stderr)
        self.assertIn("release-package: dist is a symbolic link; the packager writes only into a real dist/ folder",
                      stderr)
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
        so the build was refused before it made a work folder, the first of
        which it makes before it writes to dist/."""
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
        proc = subprocess.Popen(["bash", str(self.clone / "tools" / "release-package.sh")],
                                cwd=str(self.clone), env=self.packager_env(path_prefix=str(bin_dir)),
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, preexec_fn=default_signals)
        try:
            deadline = time.monotonic() + BUILD_TIMEOUT
            while not held.exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(held.exists(), "the build never moved a .sha256 file")
            proc.send_signal(sig)
            time.sleep(0.2)
        finally:
            go.write_bytes(b"")
            _, stderr = proc.communicate(timeout=BUILD_TIMEOUT)
        self.assertEqual(proc.returncode, code, stderr)
        self.assertEqual(outputs(self.dist), [], "a build ended by a signal left output in dist/")
        self.assert_plants_kept()

    def test_sigterm_during_move_leaves_nothing(self):
        self.assert_signal_ends_build(signal.SIGTERM, 143)

    def test_sighup_during_move_leaves_nothing(self):
        self.assert_signal_ends_build(signal.SIGHUP, 129)

    def test_sigint_during_move_leaves_nothing(self):
        self.assert_signal_ends_build(signal.SIGINT, 130)

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
        # Nothing is planted: a planted name that starts with
        # .release-package. would give a glob of the removal a match.
        self.assert_inherited_option(plant=False, BASHOPTS="failglob")

    def test_inherited_dotglob(self):
        self.assert_inherited_option(BASHOPTS="dotglob")

    def test_inherited_nocasematch(self):
        self.assert_inherited_option(BASHOPTS="nocasematch")

    def test_inherited_noglob(self):
        self.assert_inherited_option(SHELLOPTS="noglob")

    def test_inherited_globignore(self):
        self.assert_inherited_option(GLOBIGNORE="dist/*")

    def test_globignore_from_bash_env(self):
        # Bash 5.3.9 applies a GLOBIGNORE that a BASH_ENV file assigns, but
        # not one that it takes from its environment.
        bash_env = self.outside("bash-env") / "globignore.sh"
        bash_env.write_text("GLOBIGNORE='dist/*'\n", encoding="ascii")
        self.assert_inherited_option(BASH_ENV=str(bash_env))

    def assert_replaced_dist_refused(self, command: str, call: int, after: bool, staging_kept: bool,
                                     link: bool = True):
        """A stand-in for command renames dist and puts in its place a
        symbolic link to a folder outside the clone, or with link false a new
        empty folder, at its call-th call, after or before it runs the real
        command."""
        target = self.outside("replaced-dist-target")
        (target / "cleanlanguage.zip").write_bytes(b"a reader's file\n")
        before = snapshot(target)
        bin_dir = self.bin_dir("replacing-" + command)
        count = bin_dir / "count"
        swap = "'%s' '%s' '%s' && " % (self.real("mv"), self.dist, self.moved_dist)
        if link:
            swap += "'%s' -s '%s' '%s'" % (self.real("ln"), target, self.dist)
        else:
            swap += "'%s' '%s'" % (self.real("mkdir"), self.dist)
        self.write_script(bin_dir / command,
                          "n=$(($(cat '%s' 2>/dev/null || echo 0) + 1))\n"
                          "echo \"$n\" > '%s'\n"
                          "if [ \"$n\" -eq %d ] && [ %s = before ]; then %s; fi\n"
                          "'%s' \"$@\"\n"
                          "rc=$?\n"
                          "if [ \"$n\" -eq %d ] && [ %s = after ]; then %s; fi\n"
                          "exit \"$rc\"\n"
                          % (count, count, call, "after" if after else "before", swap, self.real(command),
                             call, "after" if after else "before", swap))
        self.plant()
        code, stderr = self.build(path_prefix=str(bin_dir))
        self.assertTrue(self.moved_dist.is_dir(), "the stand-in %s never replaced dist" % command)
        self.assertEqual(snapshot(target), before, "the build changed the folder that the new dist points at")
        self.assertEqual(code, 1, stderr)
        self.assertIn(DIST_REPLACED, stderr)
        # A further call would come after the check that should have ended
        # the build; for mktemp, it would make a staging folder in the new dist.
        self.assertEqual(count.read_text(encoding="ascii").strip(), str(call),
                         "the build called %s again after it replaced dist" % command)
        if not link:
            self.assertFalse(self.dist.is_symlink())
            self.assertEqual(snapshot(self.dist), {}, "the build wrote into the new dist")
        left = outputs(self.moved_dist)
        self.assertEqual([n for n in left if OUTPUT_NAME.fullmatch(n)], [],
                         "the build left an output in the renamed dist")
        if staging_kept:
            self.assertEqual(len(left), 1, "the renamed dist holds %r" % left)
        else:
            self.assertEqual(left, [], "the build left a staging folder in the renamed dist")

    def test_dist_replaced_after_first_mktemp_refused(self):
        self.assert_replaced_dist_refused("mktemp", 1, after=True, staging_kept=False)

    def test_dist_replaced_before_second_mktemp_refused(self):
        self.assert_replaced_dist_refused("mktemp", 2, after=False, staging_kept=False)

    def test_dist_replaced_after_second_mktemp_refused(self):
        self.assert_replaced_dist_refused("mktemp", 2, after=True, staging_kept=True)

    def test_dist_replaced_after_last_cmp_refused(self):
        self.assert_replaced_dist_refused("cmp", self.entry_count, after=True, staging_kept=True)

    def test_dist_replaced_by_folder_after_first_mktemp_refused(self):
        self.assert_replaced_dist_refused("mktemp", 1, after=True, staging_kept=False, link=False)

    def trap_stand_ins(self, move_exit: int = 0, refused: str = "") -> tuple:
        """Write a stand-in mktemp that writes the path of each work folder it
        makes to its log; with move_exit, a stand-in mv that refuses each move
        of a .sha256 file with that exit code; and with refused, a stand-in rm
        that fails, without removing anything, at the argument refused, where
        @1 and @2 name the first and second work folder in the log. Return
        the folder and the log."""
        bin_dir = self.bin_dir("trap-stand-ins")
        log = bin_dir / "work-folders.log"
        self.write_script(bin_dir / "mktemp",
                          "p=$('%s' \"$@\") || exit\n"
                          "printf '%%s\\n' \"$p\" >> '%s'\n"
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
                              "  @2) target=$(sed -n 2p '%s') ;;\n"
                              "esac\n"
                              "for a in \"$@\"; do\n"
                              "  if [ \"$a\" = \"$target\" ]; then echo 'rm: refused by the test' >&2; exit 1; fi\n"
                              "done\n"
                              "exec '%s' \"$@\"\n" % (refused, log, log, self.real("rm")))
        return str(bin_dir), log

    def work_folders(self, log: Path) -> list:
        folders = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        self.assertEqual(len(folders), 2, "the build made the work folders %r" % folders)
        return [Path(f) for f in folders]

    def test_good_build_removes_work_folders(self):
        bin_dir, log = self.trap_stand_ins()
        self.good_build(path_prefix=bin_dir)
        for folder in self.work_folders(log):
            self.assertFalse(os.path.lexists(folder), "the build left its work folder %s" % folder)

    def assert_trap(self, move_exit: int, refused: str):
        """A build whose stand-in mv, with move_exit, refuses each move of a
        .sha256 file with that exit code, and whose stand-in rm fails at
        refused, exits with move_exit, or 0 without it; the path that
        refused names is still there, and every other work folder is gone,
        as is every output of a failed build."""
        bin_dir, log = self.trap_stand_ins(move_exit, refused)
        self.plant()
        code, stderr = self.build(path_prefix=bin_dir)
        self.assertEqual(code, move_exit, stderr)
        if move_exit:
            self.assertIn("mv: refused by the test", stderr)
        folders = self.work_folders(log)
        for index, folder in enumerate(folders, start=1):
            if refused == "@%d" % index:
                self.assertTrue(folder.is_dir(), "the stand-in rm did not keep %s" % folder)
            else:
                self.assertFalse(os.path.lexists(folder), "the build left its work folder %s" % folder)
        expected = [] if move_exit else list(self.names)
        if refused.startswith("dist/"):
            expected.append(refused[len("dist/"):])
        if refused == "@2":
            expected.append(folders[1].name)
        self.assertEqual(outputs(self.dist), sorted(expected), "the exit trap removed the wrong set of outputs")
        self.assert_plants_kept()
        if refused == "@1":
            shutil.rmtree(folders[0])

    def test_failed_build_keeps_exit_code_and_removes_work_folders(self):
        self.assert_trap(MOVE_EXIT, "")

    def test_trap_continues_after_failed_output_removal(self):
        self.assert_trap(MOVE_EXIT, "dist/cleanlanguage.zip")

    def test_trap_continues_after_failed_first_work_folder_removal(self):
        self.assert_trap(MOVE_EXIT, "@1")

    def assert_signal_during_trap(self, sig: int):
        """A build whose stand-in mv refuses each move of a .sha256 file with
        MOVE_EXIT, and whose stand-in rm holds the first removal of the exit
        trap until the test has sent sig to the build, must still complete
        the removals of the trap and exit with MOVE_EXIT. Nothing is planted,
        so the trap makes the first removal in dist/ of the build."""
        bin_dir, log = self.trap_stand_ins(MOVE_EXIT)
        held, go = Path(bin_dir) / "held", Path(bin_dir) / "go"
        self.write_script(Path(bin_dir) / "rm",
                          "for a in \"$@\"; do\n"
                          "  case \"$a\" in dist/*)\n"
                          "    if [ ! -e '%s' ]; then\n"
                          "      : > '%s'\n"
                          "      n=0\n"
                          "      while [ ! -e '%s' ] && [ \"$n\" -lt 1200 ]; do sleep 0.1; n=$((n + 1)); done\n"
                          "    fi\n"
                          "    break ;;\n"
                          "  esac\n"
                          "done\n"
                          "exec '%s' \"$@\"\n" % (held, held, go, self.real("rm")))
        proc = subprocess.Popen(["bash", str(self.clone / "tools" / "release-package.sh")],
                                cwd=str(self.clone), env=self.packager_env(path_prefix=bin_dir),
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, preexec_fn=default_signals)
        try:
            deadline = time.monotonic() + BUILD_TIMEOUT
            while not held.exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(held.exists(), "the exit trap never removed an output from dist/")
            proc.send_signal(sig)
            time.sleep(0.2)
        finally:
            go.write_bytes(b"")
            _, stderr = proc.communicate(timeout=BUILD_TIMEOUT)
        self.assertEqual(proc.returncode, MOVE_EXIT, stderr)
        self.assertIn("mv: refused by the test", stderr)
        self.assertEqual(outputs(self.dist), [], "a signal cut the removals of the exit trap short")
        for folder in self.work_folders(log):
            self.assertFalse(os.path.lexists(folder), "the build left its work folder %s" % folder)

    def test_sigterm_during_exit_trap_ignored(self):
        self.assert_signal_during_trap(signal.SIGTERM)

    def test_sighup_during_exit_trap_ignored(self):
        self.assert_signal_during_trap(signal.SIGHUP)

    def test_sigint_during_exit_trap_ignored(self):
        self.assert_signal_during_trap(signal.SIGINT)

    def test_good_build_exits_0_after_failed_second_work_folder_removal(self):
        # A failed build removes the second work folder, a staging folder in
        # dist/, through its removal of earlier outputs, so only a good build
        # reaches the last removal of the trap with that folder still there.
        self.assert_trap(0, "@2")


if __name__ == "__main__":
    unittest.main()
