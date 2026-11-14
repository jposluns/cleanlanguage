#!/usr/bin/env python3
"""Check what tools/release-package.sh leaves in dist/ after each build.

A build that passes every check writes dist/cleanlanguage.zip,
dist/cleanlanguage-<version>.zip and a .sha256 beside each. A build that is
refused at any check must leave no zip and no .sha256 in dist/, neither a new
one nor one that an earlier build wrote, so that a reader cannot take a stale
or unverified zip for the refused build. The packager removes only its own
outputs and its staging folders; every other file and folder in dist/ is kept.

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
temporary folder, and each records into a file there.

Before every good build and every refused build, the test plants in dist/ a
set of files and folders that the packager did not write (PLANTS), some with
names close to an output name, and a leftover staging folder
(LEFTOVER_STAGING). After the build, every planted path must be there with
its bytes unchanged, and the leftover staging folder must be gone.

Cases, all in 1 clone:

1. The packager of REFERENCE_COMMIT builds the clone and gives the reference
   digest.
2. A good build with the checkout's packager exits 0, writes the 4 outputs,
   and gives the reference digest for both zips with matching .sha256 files;
   it keeps the planted paths and removes the leftover staging folder.
3. After a good build, a build refused before the archive is made
   (--tag v0.0.0, --release-date 2020-01-01, and the unknown argument
   --bogus), with a stale version-named pair planted beside the outputs,
   leaves no zip and no .sha256 in dist/.
4. After a good build, a build with core.autocrlf=true, refused by the check
   that compares every archived file with its git blob, leaves no zip and no
   .sha256 in dist/.
5. After a good build, a build whose move of the .sha256 files into dist/
   fails, through a stand-in mv first on the PATH, leaves no zip and no
   .sha256 in dist/, including the 2 zips it had already moved.
6. In a good build, a stand-in mv first on the PATH records each move into
   dist/: every source lies in a staging folder inside dist/, and both zips
   are in dist/ before either .sha256 is moved there.
7. In a good build, a stand-in unzip first on the PATH records that no
   output name is present in dist/ at any call, so no output reaches dist/
   before the checks that read the staged zip.
8. A dist that is a symbolic link to a folder, or a plain file, is refused
   with exit 1 and the packager's message, and the folder it points at, or
   the file, is unchanged.
9. A folder named dist/cleanlanguage.zip/ is kept; the move onto it fails,
   so the build exits 1 and leaves no zip and no .sha256 in dist/.

Each case starts from an empty dist/.

REFERENCE_COMMIT names the commit of the last packager that wrote dist/
before its checks, and the reference comparison in case 2 holds only while
the packager gives the same bytes as that commit's packager. An intended
change to the packager's output therefore makes case 2 fail by design.
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
# an output name, a folder that carries a version-named output name, and a
# folder whose name is not a staging name (4 characters after the last dot,
# not 6).
PLANTS = {
    KEEP: KEEP_TEXT,
    "edit-scripts/keep.py": b"print('kept')\n",
    "cleanlanguage-notes.zip": b"notes\n",
    "cleanlanguage.txt": b"text\n",
    "cleanlanguage-1.0.zip": b"two-part version\n",
    "cleanlanguage-1.0.0.zip.bak": b"backup\n",
    "cleanlanguage-1.0.0.zip.sha256.old": b"old checksum\n",
    "cleanlanguage-1.0.0.zip/keep.txt": b"a folder with an output name\n",
    ".release-package.keep/keep.txt": b"not a staging folder\n",
}
LEFTOVER_STAGING = ".release-package.AbC123"
OUTPUT_NAME = re.compile(r"cleanlanguage(-[0-9]+\.[0-9]+\.[0-9]+)?\.zip(\.sha256)?")
STAGING_NAME = re.compile(r"\.release-package\.[A-Za-z0-9]{6}")
BUILD_TIMEOUT = 300


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True, timeout=BUILD_TIMEOUT).stdout


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def outputs(dist: Path) -> list:
    """Every regular file in dist/ with an output name, and every staging folder."""
    if not dist.is_dir() or dist.is_symlink():
        return []
    return sorted(p.name for p in dist.iterdir()
                  if (OUTPUT_NAME.fullmatch(p.name) and p.is_file() and not p.is_symlink())
                  or (STAGING_NAME.fullmatch(p.name) and p.is_dir()))


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
        if self.dist.is_symlink() or self.dist.is_file():
            self.dist.unlink()
        elif self.dist.exists():
            shutil.rmtree(self.dist)

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

    def plant(self):
        """Plant PLANTS and a leftover staging folder holding a file."""
        self.dist.mkdir(exist_ok=True)
        for rel, data in PLANTS.items():
            path = self.dist / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (self.dist / LEFTOVER_STAGING).mkdir(exist_ok=True)
        (self.dist / LEFTOVER_STAGING / "cleanlanguage.zip").write_bytes(b"left by a killed build\n")

    def assert_plants_kept(self):
        for rel, data in PLANTS.items():
            path = self.dist / rel
            self.assertTrue(path.is_file(), "the build removed %s, which it did not write" % path)
            self.assertEqual(path.read_bytes(), data, "the build changed %s, which it did not write" % path)
        self.assertFalse((self.dist / LEFTOVER_STAGING).exists(),
                         "the build kept the leftover staging folder %s" % LEFTOVER_STAGING)

    def good_build(self, path_prefix: str = ""):
        self.plant()
        code, stderr = self.build(path_prefix=path_prefix)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(outputs(self.dist), self.names)
        self.assert_plants_kept()

    def assert_refused_leaves_nothing(self, *args: str, autocrlf: bool = False, path_prefix: str = "",
                                      reason: str):
        self.good_build()
        self.plant()
        stale = self.dist / "cleanlanguage-0.0.1.zip"
        stale.write_bytes(b"stale")
        (self.dist / "cleanlanguage-0.0.1.zip.sha256").write_bytes(b"stale\n")
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

    def test_file_dist_refused(self):
        self.dist.write_bytes(KEEP_TEXT)
        code, stderr = self.build()
        self.assertEqual(code, 1, stderr)
        self.assertIn("release-package: dist exists and is not a folder", stderr)
        self.assertTrue(self.dist.is_file() and not self.dist.is_symlink())
        self.assertEqual(self.dist.read_bytes(), KEEP_TEXT)

    def test_output_name_folder_kept(self):
        self.plant()
        folder = self.dist / "cleanlanguage.zip"
        folder.mkdir()
        (folder / KEEP).write_bytes(KEEP_TEXT)
        code, stderr = self.build()
        self.assertEqual(code, 1, stderr)
        self.assertEqual((folder / KEEP).read_bytes(), KEEP_TEXT)
        self.assertEqual(outputs(self.dist), [], "a failed move left output in dist/")
        self.assert_plants_kept()


if __name__ == "__main__":
    unittest.main()
