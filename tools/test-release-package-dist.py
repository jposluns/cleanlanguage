#!/usr/bin/env python3
"""Check what tools/release-package.sh leaves in dist/ after each build.

A build that passes every check writes dist/cleanlanguage.zip,
dist/cleanlanguage-<version>.zip and a .sha256 beside each. A build that is
refused at any check must leave no zip and no .sha256 in dist/, neither a new
one nor one that an earlier build wrote, so that a reader cannot take a stale
or unverified zip for the refused build. Every other file in dist/ is kept.

Every build here runs in a clone that the test makes in a temporary folder
with `git clone --no-local`, never in the checkout it runs from, so a dist/
folder in the checkout is never touched. The clone carries the checkout's
HEAD; the checkout's tools/release-package.sh, tools/skill-release-date.py
and tools/skill-release-date-client.py are copied into it, so the code under
test is the checkout's, uncommitted changes included. The test runs
read-only git commands and git clone only; it sets core.autocrlf for 1 build
through the GIT_CONFIG_COUNT, GIT_CONFIG_KEY_0 and GIT_CONFIG_VALUE_0
variables of that build's environment, never by a git config command.

Cases, all in 1 clone:

1. The packager of REFERENCE_COMMIT builds the clone and gives the reference
   digest.
2. A good build with the checkout's packager exits 0, writes the 4 outputs,
   and gives the reference digest for both zips with matching .sha256 files;
   it keeps a file the test placed in dist/ beforehand.
3. After a good build, a build refused before the archive is made
   (--tag v0.0.0, and --release-date 2020-01-01), with a stale version-named
   pair planted beside the outputs, leaves no zip and no .sha256 in dist/.
4. After a good build, a build with core.autocrlf=true, refused by the check
   that compares every archived file with its git blob, leaves no zip and no
   .sha256 in dist/.
5. After a good build, a build whose move of the .sha256 files into dist/
   fails, through a stand-in mv first on the PATH, leaves no zip and no
   .sha256 in dist/, including the 2 zips it had already moved.

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
BUILD_TIMEOUT = 300


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True, timeout=BUILD_TIMEOUT).stdout


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def outputs(dist: Path) -> list:
    """Every entry in dist/ that is a zip, a .sha256 or an output folder."""
    if not dist.is_dir():
        return []
    return sorted(p.name for p in dist.iterdir()
                  if p.name.endswith((".zip", ".sha256")) or p.name.startswith(".release-package."))


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
        if self.dist.exists():
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

    def good_build(self):
        self.dist.mkdir(exist_ok=True)
        (self.dist / KEEP).write_bytes(KEEP_TEXT)
        code, stderr = self.build()
        self.assertEqual(code, 0, stderr)
        names = ["cleanlanguage-%s.zip" % self.version, "cleanlanguage-%s.zip.sha256" % self.version,
                 "cleanlanguage.zip", "cleanlanguage.zip.sha256"]
        self.assertEqual(outputs(self.dist), names)

    def assert_kept(self):
        keep = self.dist / KEEP
        self.assertTrue(keep.is_file(), "the build removed %s, which it did not write" % keep)
        self.assertEqual(keep.read_bytes(), KEEP_TEXT)

    def assert_refused_leaves_nothing(self, *args: str, autocrlf: bool = False, path_prefix: str = "",
                                      reason: str):
        self.good_build()
        stale = self.dist / "cleanlanguage-0.0.1.zip"
        stale.write_bytes(b"stale")
        (self.dist / "cleanlanguage-0.0.1.zip.sha256").write_bytes(b"stale\n")
        code, stderr = self.build(*args, autocrlf=autocrlf, path_prefix=path_prefix)
        self.assertEqual(code, 1, stderr)
        self.assertIn(reason, stderr)
        self.assertEqual(outputs(self.dist), [], "a refused build left output in dist/")
        self.assert_kept()

    def test_good_build_keeps_other_files(self):
        self.good_build()
        self.assert_kept()

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


if __name__ == "__main__":
    unittest.main()
