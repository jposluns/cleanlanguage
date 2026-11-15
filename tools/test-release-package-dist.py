#!/usr/bin/env python3
"""Check what tools/release-package.sh leaves in dist/ after each build.

The packager is meant to work as follows, and the cases below check it at
the builds and on the planted paths that they name. A build that passes
every check writes dist/cleanlanguage.zip, dist/cleanlanguage-<version>.zip
and a .sha256 beside each. A build that is refused at a check must leave
no zip and no .sha256 in dist/, neither a new one nor one that an earlier
build wrote, so that a reader cannot take a stale or unverified zip for the
refused build; a removal that fails is the exception, and then the build
exits 1 and the output it could not remove stays. The packager removes
entries of dist/ by name and type: a regular file with an output name, and
a folder with a staging name together with everything that folder holds,
whoever wrote it. It keeps every other entry of dist/ as it is. A build
refuses with exit 1 when 1 of the 4 names it writes is held by a symbolic
link, folder, FIFO or other object that is not a regular file, since its
rename into dist/ would replace that object; it refuses after it has
removed the outputs of an earlier build and before it makes its first work
folder, so before it writes anything to dist/.

Every build here runs in a clone that the test makes in a temporary folder
with `git clone --no-local`, never in the checkout it runs from, so a dist/
folder in the checkout is never touched. The clone carries the checkout's
HEAD; the checkout's tools/release-package.sh, tools/skill-release-date.py
and tools/skill-release-date-client.py are copied into it, so the code under
test is the checkout's, uncommitted changes included. The test runs
read-only git commands and git clone only; it sets core.autocrlf for 1 build
through the GIT_CONFIG_COUNT, GIT_CONFIG_KEY_0 and GIT_CONFIG_VALUE_0
variables of that build's environment, never by a git config command.
Each stand-in command is a short sh script that the test writes into its
temporary folder and puts first on the PATH of 1 build. The stand-in mv of
case 5, the stand-in unzip of case 6 and the stand-in mktemp of cases 8
and 9 each record every call into a file there. The stand-in mv of case 4
refuses each move of a .sha256 file, that of case 9 runs each move and then
fails for a .sha256 file, and the stand-in rm of case 10 fails at 1 path
of dist/; none of these 3 records anything.

Before each build of cases 1 to 6, 8, 9 and 10, except the build with no
dist/, the test plants in dist/ a set of files and folders that the
packager did not write (PLANTS), many with names that differ from an output
name or a staging name in 1 place, a symbolic link with a staging name to
a folder outside dist/ (STAGING_LINK), and 2 leftover staging folders
(LEFTOVER_STAGING), each holding a file. After the build, each planted path
must be there with its bytes unchanged, the link must still point at the
same unchanged folder, and the leftover staging folders must be gone,
except the 1 at which the stand-in rm of case 10 fails, which must still
hold its file. Before each refused build of cases 2 to 4 and 10, and
each build of case 9 that follows a good build, it also plants the 2
outputs of an earlier build for version STALE_VERSION.
The reference build, the build with no dist/ in case 1 and case 7 plant
nothing in dist/; case 7 makes dist itself a link, a file or a FIFO.

In its set-up, before any case, the test builds the clone with the packager
of REFERENCE_COMMIT, which gives the reference digest. The cases, all in
that clone:

1. A good build with the checkout's packager exits 0, writes the 4 outputs,
   and gives the reference digest for both zips with matching .sha256 files;
   it keeps the planted paths and removes the leftover staging folders. A
   good build with no dist/ exits 0 and writes the 4 outputs.
2. After a good build, a build refused before the archive is made
   (--tag v0.0.0, --release-date 2020-01-01, and the unknown argument
   --bogus) leaves no zip and no .sha256 in dist/.
3. After a good build, a build with core.autocrlf=true, refused by the check
   that compares each archived file with its git blob, leaves no zip and no
   .sha256 in dist/.
4. After a good build, a build whose move of the .sha256 files into dist/
   fails, through the stand-in mv, leaves no zip and no .sha256 in dist/,
   including the 2 zips it had already moved.
5. In a good build, the stand-in mv records each move into dist/: each
   source lies in a staging folder inside dist/, and both zips are in dist/
   before either .sha256 is moved there.
6. In a good build, the stand-in unzip records that no output name is
   present in dist/ at any of its calls, so no output reaches dist/ before
   the checks that read the staged zip.
7. A dist that is a symbolic link to a folder, a dangling symbolic link, a
   plain file or a FIFO is refused with exit 1 and the packager's message,
   and the folder it points at, the missing target, the file or the FIFO
   is unchanged.
8. A folder named dist/cleanlanguage.zip/ is refused with exit 1 and the
   packager's message, is kept with its contents, and dist/ holds no zip
   and no .sha256; the stand-in mktemp was never called.
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
   unchanged, dist/ holds no zip and no .sha256, and the stand-in mktemp
   was never called.
10. After a good build, a build whose stand-in rm fails at the
    version-named zip, and a build whose stand-in rm fails at the first
    leftover staging folder, each exit 1 with the packager's message for a
    failed removal; the path that the stand-in refused is still there, and
    each other earlier output and leftover staging folder is gone.

Each case starts with no dist/ in the clone.

REFERENCE_COMMIT names the commit of the last packager that wrote dist/
before its checks, and the reference comparison in case 1 holds only while
the packager gives the same bytes as that commit's packager. An intended
change to the packager's output therefore makes case 1 fail by design.
REFERENCE_COMMIT then moves to the commit that makes the change, in the
same pull request.

Usage:
  python3 -I tools/test-release-package-dist.py

Needs git, bash, zip, unzip and sha256sum, and the full history of the
checkout, since it reads tools/release-package.sh at REFERENCE_COMMIT.
"""

import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = ("release-package.sh", "skill-release-date.py", "skill-release-date-client.py")
REFERENCE_COMMIT = "8d6de113182691d313c7cb6bdfb01df7423d280c"
KEEP = "keep.txt"
KEEP_TEXT = b"a file the packager does not write\n"
# Files and folders that the packager did not write, each of which a build
# must keep byte for byte: a plain file, a folder of scripts, names close to
# an output name, a folder that carries a version-named output name, folders
# whose names are close to a staging name, and a regular file with a staging
# name. Most of the names close to an output name or a staging name differ
# from it in 1 place, so that a name test of the removal that loses or
# loosens that place removes the plant: a prefix, a suffix, an empty or
# non-digit version part, a character other than a dot where the name has a
# dot, a dot where it has a hyphen, 5 or 7 characters after the last dot of
# a staging name, or a character there that is not a letter or digit.
PLANTS = {
    KEEP: KEEP_TEXT,
    "edit-scripts/keep.py": b"print('kept')\n",
    "cleanlanguage-notes.zip": b"notes\n",
    "cleanlanguage.txt": b"text\n",
    "cleanlanguage-1.0.zip": b"2-part version\n",
    "cleanlanguage-1.0.0.zip.bak": b"backup\n",
    "cleanlanguage-1.0.0.zip.sha256.old": b"old checksum\n",
    "xcleanlanguage.zip": b"a prefix before an output name\n",
    "cleanlanguage.1.0.0.zip": b"a dot, not a hyphen, before the version\n",
    "cleanlanguage-.0.0.zip": b"an empty first version part\n",
    "cleanlanguage-1..0.zip": b"an empty second version part\n",
    "cleanlanguage-1.0..zip": b"an empty third version part\n",
    "cleanlanguage-a.0.0.zip": b"a letter as the first version part\n",
    "cleanlanguage-0.a.0.zip": b"a letter as the second version part\n",
    "cleanlanguage-0.0.a.zip": b"a letter as the third version part\n",
    "cleanlanguage-1x0.0.zip": b"no dot after the first version part\n",
    "cleanlanguage-1.0x0.zip": b"no dot after the second version part\n",
    "cleanlanguageXzip": b"no dot before zip\n",
    "cleanlanguage.zipXsha256": b"no dot before sha256\n",
    "cleanlanguage-1.0.0.zip/keep.txt": b"a folder with an output name\n",
    ".release-package.keep/keep.txt": b"not a staging folder\n",
    ".release-package.AbC12/keep.txt": b"5 characters, not a staging folder\n",
    ".release-package.AbC1234/keep.txt": b"7 characters, not a staging folder\n",
    ".release-package.AbC_12/keep.txt": b"an underscore, not a staging folder\n",
    ".release-package.AbC-12/keep.txt": b"a hyphen, not a staging folder\n",
    ".release-package.AbC.12/keep.txt": b"a dot, not a staging folder\n",
    "Xrelease-package.AbC123/keep.txt": b"no dot before release-package\n",
    "keep.release-package.AbC123/keep.txt": b"a prefix before a staging name\n",
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
OUTPUT_NAME = re.compile(r"cleanlanguage(-[0-9]+\.[0-9]+\.[0-9]+)?\.zip(\.sha256)?")
STAGING_NAME = re.compile(r"\.release-package\.[A-Za-z0-9]{6}")
BUILD_TIMEOUT = 300


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True, timeout=BUILD_TIMEOUT).stdout


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


class DistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.clone = Path(cls.tmp.name) / "clone"
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
        reference = cls.clone / "tools" / "release-package-reference.sh"
        reference.write_bytes(git("-C", str(REPO), "show", REFERENCE_COMMIT + ":tools/release-package.sh"))
        code, stderr = cls.run_packager(reference)
        if code != 0:
            raise AssertionError(f"the reference packager failed with exit {code}: {stderr}")
        cls.reference_digest = sha256(cls.dist / "cleanlanguage.zip")
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

    @classmethod
    def run_packager(cls, script: Path, *args: str, autocrlf: bool = False, path_prefix: str = ""):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG")}
        if autocrlf:
            env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.autocrlf", GIT_CONFIG_VALUE_0="true")
        if path_prefix:
            env["PATH"] = path_prefix + os.pathsep + env.get("PATH", "")
        proc = subprocess.run(["bash", str(script), *args], cwd=str(cls.clone), env=env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=BUILD_TIMEOUT)
        return proc.returncode, proc.stderr

    def build(self, *args: str, autocrlf: bool = False, path_prefix: str = ""):
        return self.run_packager(self.clone / "tools" / "release-package.sh", *args, autocrlf=autocrlf,
                                 path_prefix=path_prefix)

    def outside(self, name: str) -> Path:
        """A new, empty folder of the temporary folder, outside the clone."""
        folder = Path(self.tmp.name) / name
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir()
        return folder

    def plant(self):
        """Plant PLANTS, STAGING_LINK and the leftover staging folders, each holding a file."""
        self.dist.mkdir(exist_ok=True)
        for rel, data in PLANTS.items():
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

    def assert_plants_kept(self, kept_staging: str = ""):
        """Assert that every plant is unchanged and that every leftover
        staging folder is gone, except kept_staging, whose file must be there."""
        for rel, data in PLANTS.items():
            path = self.dist / rel
            self.assertTrue(path.is_file(), "the build removed %s, which it did not write" % path)
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

    def good_build(self, path_prefix: str = ""):
        self.plant()
        code, stderr = self.build(path_prefix=path_prefix)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(outputs(self.dist), self.names)
        self.assert_plants_kept()

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
        real = shutil.which(name)
        self.assertIsNotNone(real, "%s is not on the PATH" % name)
        bin_dir = Path(self.tmp.name) / ("record-" + name)
        bin_dir.mkdir(exist_ok=True)
        log = bin_dir / "calls.log"
        if log.exists():
            log.unlink()
        (bin_dir / name).write_text(
            "#!/bin/sh\n"
            "line=\n"
            "for n in %s; do\n"
            "  if [ -e \"dist/$n\" ]; then line=\"$line$n,\"; fi\n"
            "done\n"
            "for a in \"$@\"; do line=\"$line\t$a\"; done\n"
            "printf '%%s\\n' \"$line\" >> '%s'\n"
            "exec '%s' \"$@\"\n" % (" ".join(self.names), log, real), encoding="ascii")
        os.chmod(bin_dir / name, 0o755)
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

    def test_refused_tag_leaves_nothing(self):
        self.assert_refused_leaves_nothing("--tag", "v0.0.0", reason="does not match the tag (v0.0.0)")

    def test_refused_release_date_leaves_nothing(self):
        self.assert_refused_leaves_nothing("--release-date", "2020-01-01",
                                           reason="does not match the release date (2020-01-01)")

    def test_refused_unknown_argument_leaves_nothing(self):
        self.assert_refused_leaves_nothing("--bogus", reason="unknown argument --bogus")

    def test_autocrlf_build_leaves_nothing(self):
        self.assert_refused_leaves_nothing(autocrlf=True, reason="differs from its git blob")

    def test_failed_move_leaves_nothing(self):
        # A stand-in mv, first on the PATH, that refuses any move of a .sha256
        # file and runs the real mv for every other, so the build fails after
        # it has moved the 2 zips into dist/.
        real_mv = shutil.which("mv")
        self.assertIsNotNone(real_mv, "mv is not on the PATH")
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / "mv").write_text(
            "#!/bin/sh\n"
            "for a in \"$@\"; do\n"
            "  case \"$a\" in *.sha256) echo 'mv: refused by the test' >&2; exit 1 ;; esac\n"
            "done\n"
            "exec '%s' \"$@\"\n" % real_mv, encoding="ascii")
        os.chmod(bin_dir / "mv", 0o755)
        self.assert_refused_leaves_nothing(path_prefix=str(bin_dir), reason="mv: refused by the test")

    def refusing_rm(self, refused: str) -> str:
        """Write a stand-in rm, first on the PATH, that fails, without removing
        anything, at any call with the argument dist/<refused>, and runs the
        real rm for every other call. It records nothing. Return its folder."""
        real_rm = shutil.which("rm")
        self.assertIsNotNone(real_rm, "rm is not on the PATH")
        bin_dir = Path(self.tmp.name) / "refusing-rm"
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / "rm").write_text(
            "#!/bin/sh\n"
            "for a in \"$@\"; do\n"
            "  case \"$a\" in 'dist/%s') echo 'rm: refused by the test' >&2; exit 1 ;; esac\n"
            "done\n"
            "exec '%s' \"$@\"\n" % (refused, real_rm), encoding="ascii")
        os.chmod(bin_dir / "rm", 0o755)
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
        target = Path(self.tmp.name) / "linked-dist"
        if target.exists():
            shutil.rmtree(target)
        target.mkdir()
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
        real_mv = shutil.which("mv")
        self.assertIsNotNone(real_mv, "mv is not on the PATH")
        bin_dir = Path(self.tmp.name) / "move-then-fail"
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / "mv").write_text(
            "#!/bin/sh\n"
            "'%s' \"$@\" || exit\n"
            "for a in \"$@\"; do\n"
            "  case \"$a\" in *.sha256) echo 'mv: failed after the move, by the test' >&2; exit 1 ;; esac\n"
            "done\n" % real_mv, encoding="ascii")
        os.chmod(bin_dir / "mv", 0o755)
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


if __name__ == "__main__":
    unittest.main()
