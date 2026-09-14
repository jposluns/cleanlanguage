#!/usr/bin/env python3
"""Cross-consumer contract: the packager and the two release gates select and
validate the SKILL.md ``Version:`` line by the same rule.

The two gates (check-release-links.py, check-release-checksum-live.py) already
apply a strict rule: the first ``Version:`` line must be a bare ``X.Y.Z``. This
test pins that the packager (release-package.sh) selects and validates
identically, so a malformed first line fails in all three, and a clean version
still passes. It runs offline: the packager is exercised in a throwaway git
worktree, and the gates are exercised through their own compiled regexes.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACKAGER = REPO / "tools" / "release-package.sh"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "tools" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LINKS = _load("crl_gate", "check-release-links.py")
CHECKSUM = _load("crc_gate", "check-release-checksum-live.py")

HEAD_SKILL = subprocess.run(
    ["git", "-C", str(REPO), "show", "HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md"],
    capture_output=True, text=True, check=True,
).stdout


def skill_with(version_block: str | None) -> str:
    """The real SKILL.md text with its first ``Version:`` line replaced by
    ``version_block`` (which may be empty to drop it, or multi-line)."""
    if version_block is None:
        return HEAD_SKILL
    out, replaced = [], False
    for line in HEAD_SKILL.splitlines(keepends=True):
        if not replaced and line.startswith("Version:"):
            if version_block:
                out.append(version_block + "\n")
            replaced = True
        else:
            out.append(line)
    return "".join(out)


def gate_verdict(gate, skill_text: str):
    """(matched, version) for a gate's select-and-validate, read the way the real
    gate reads a file: through Path.read_text, whose universal-newline handling
    drops a trailing CR from a CRLF line ending."""
    with tempfile.NamedTemporaryFile("wb", suffix=".md", delete=False) as handle:
        handle.write(skill_text.encode("utf-8"))
        path = handle.name
    try:
        text = Path(path).read_text(encoding="utf-8")
    finally:
        os.unlink(path)
    line = gate.VERSION_LINE.search(text)
    if line is None:
        return False, None
    match = gate.SKILL_VERSION.match(line.group(0))
    return (True, match.group(1)) if match else (False, None)


def run_packager(version_block: str | None, plugin_version: str, locale: str | None = None, extra_tail: str = "", raw_skill: bytes | None = None):
    """Build in a throwaway worktree whose HEAD carries the fixture; run the
    CHECKOUT's release-package.sh (so the code under test, not HEAD's copy, is
    exercised). Returns (exit_code, stderr)."""
    skill = skill_with(version_block) + extra_tail
    with tempfile.TemporaryDirectory() as tmp:
        wt = Path(tmp) / "wt"
        subprocess.run(
            ["git", "-C", str(REPO), "worktree", "add", "--detach", str(wt), "HEAD"],
            capture_output=True, check=True,
        )
        try:
            if raw_skill is not None:
                (wt / "cleanlanguage" / "skills" / "cleanlanguage" / "SKILL.md").write_bytes(raw_skill)
            else:
                (wt / "cleanlanguage" / "skills" / "cleanlanguage" / "SKILL.md").write_text(skill, encoding="utf-8")
            pj = wt / "cleanlanguage" / ".claude-plugin" / "plugin.json"
            data = json.loads(pj.read_text(encoding="utf-8"))
            data["version"] = plugin_version
            pj.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(wt), "-c", "user.name=t", "-c", "user.email=t@t",
                 "commit", "-qam", "fixture"],
                capture_output=True, check=True,
            )
            shutil.copyfile(PACKAGER, wt / "tools" / "release-package.sh")
            os.chmod(wt / "tools" / "release-package.sh", 0o755)
            env = dict(os.environ)
            if locale is not None:
                env["LC_ALL"] = locale
            result = subprocess.run(
                ["bash", str(wt / "tools" / "release-package.sh")],
                capture_output=True, text=True, env=env,
            )
            return result.returncode, result.stderr
        finally:
            subprocess.run(
                ["git", "-C", str(REPO), "worktree", "remove", "--force", str(wt)],
                capture_output=True,
            )


# label -> (version_block, plugin_version, packager_accepts, gate_expected_version)
MALFORMED = {
    "two_part": ("Version: 1.2", "1.2", None),
    "four_part": ("Version: 1.2.3.4", "1.2.3.4", None),
    "trailing_text": ("Version: 1.2.3 beta", "1.2.3", None),
    "double_dot": ("Version: 1..2", "1..2", None),
    "draft_then_valid": ("Version: draft\nVersion: 1.2.3", "1.2.3", None),
}


class GateParseTest(unittest.TestCase):
    def test_gates_agree_and_are_identical(self):
        # Both gates apply the identical rule; assert on each so a future
        # divergence between them also goes red.
        for gate in (LINKS, CHECKSUM):
            matched, version = gate_verdict(gate, skill_with(None))
            self.assertTrue(matched)
            self.assertEqual(version, "1.0.14")
            matched, version = gate_verdict(gate, skill_with("Version: 9.9.9  "))
            self.assertTrue(matched)
            self.assertEqual(version, "9.9.9")
            for block, _plugin, _ in MALFORMED.values():
                matched, _ = gate_verdict(gate, skill_with(block))
                self.assertFalse(matched, block)
            matched, _ = gate_verdict(gate, skill_with(""))
            self.assertFalse(matched)


class PackagerContractTest(unittest.TestCase):
    def test_real_head_version_builds(self):
        code, stderr = run_packager(None, "1.0.14")
        self.assertEqual(code, 0, stderr)

    def test_malformed_first_line_is_rejected(self):
        for label, (block, plugin, _) in MALFORMED.items():
            with self.subTest(label):
                code, stderr = run_packager(block, plugin)
                self.assertEqual(code, 1, f"{label}: stderr={stderr!r}")
                self.assertIn("not a bare X.Y.Z", stderr)

    def test_no_version_line_is_rejected(self):
        code, stderr = run_packager("", "1.0.14")
        self.assertEqual(code, 1, stderr)
        self.assertIn("no Version: line found", stderr)


def _locale_available(name: str) -> bool:
    try:
        return subprocess.run(["locale", "-a"], capture_output=True, text=True).stdout \
            .lower().find(name.lower().replace("-", "")) >= 0 or name in \
            subprocess.run(["locale", "-a"], capture_output=True, text=True).stdout
    except OSError:
        return False


class UnicodeAndStressTest(unittest.TestCase):
    """A bash regex class is locale sensitive; the packager must still agree with
    the gates' ASCII rule on non-ASCII blanks and digits, and must not crash on a
    large but valid SKILL.md."""

    def _gates_reject(self, version_block):
        for gate in (LINKS, CHECKSUM):
            matched, _ = gate_verdict(gate, skill_with(version_block))
            self.assertFalse(matched, version_block)

    def test_unicode_blank_is_rejected(self):
        # U+2000 (EN QUAD) is matched by [[:blank:]] under C.UTF-8 but not by the
        # gates' [ \t]; the literal class must reject it, matching the gates.
        block = "Version: 1.2.3\u2000"
        code, stderr = run_packager(block, "1.2.3", locale="C.UTF-8")
        self.assertEqual(code, 1, stderr)
        self.assertIn("not a bare X.Y.Z", stderr)
        self._gates_reject(block)

    def test_unicode_digit_is_rejected(self):
        # A fullwidth digit is matched by [0-9] under a full UTF-8 locale but not
        # by the gates' ASCII [0-9]; the ASCII digit list must reject it.
        if not _locale_available("en_US.utf8"):
            self.skipTest("en_US.UTF-8 locale not installed")
        block = "Version: \uff11.2.3"
        code, stderr = run_packager(block, "\uff11.2.3", locale="en_US.UTF-8")
        self.assertEqual(code, 1, stderr)
        self._gates_reject(block)

    def test_crlf_line_ending_agrees(self):
        # A CRLF line ending: the gate reads with universal newlines (drops the
        # CR) and accepts 1.2.3; the packager strips a trailing CR too, so both
        # accept. The pre-change packager rejected it (the CR survived).
        block = "Version: 1.2.3\r"
        code, stderr = run_packager(block, "1.2.3")
        self.assertEqual(code, 0, stderr)
        for gate in (LINKS, CHECKSUM):
            matched, version = gate_verdict(gate, skill_with(block))
            self.assertTrue(matched)
            self.assertEqual(version, "1.2.3")

    def test_large_valid_skill_builds(self):
        # A large but valid SKILL.md must build, not die with SIGPIPE (exit 141)
        # from an awk pipe that closes early.
        tail = "\n<!-- " + ("x" * 200000) + " -->\n"
        code, stderr = run_packager(None, "1.0.14", extra_tail=tail)
        self.assertEqual(code, 0, stderr)

    def test_nul_in_version_line_is_rejected_by_all_three(self):
        # A NUL in the version line: both the gates and the packager (which now
        # reads the file the same way) reject it, because a NUL is not [ \t] and
        # so breaks the bare-X.Y.Z match. The pre-change packager stripped it.
        block = "Version: 1.2.3\x00"
        code, stderr = run_packager(block, "1.2.3")
        self.assertEqual(code, 1, stderr)
        self.assertIn("not a bare X.Y.Z", stderr)
        self._gates_reject(block)

    def test_nul_outside_version_line_agrees(self):
        # A NUL elsewhere leaves the version line clean, so both accept 1.0.14.
        code, stderr = run_packager(None, "1.0.14", extra_tail="\n<!-- \x00 -->\n")
        self.assertEqual(code, 0, stderr)

    def test_lone_cr_mid_line_selects_the_same_version(self):
        # A bare CR inside a line: read_text universal newlines split there, so
        # the gate's first Version line is 1.0.0; the packager, reading the file
        # the same way, also selects 1.0.0. A plain bash read loop (split on LF
        # only) would have skipped the hidden token and chosen 2.0.0 instead.
        block = "foo\rVersion: 1.0.0\nVersion: 2.0.0"
        code, _ = run_packager(block, "1.0.0")
        self.assertEqual(code, 0)
        matched, version = gate_verdict(LINKS, skill_with(block))
        self.assertTrue(matched)
        self.assertEqual(version, "1.0.0")

    def test_empty_skill_agrees_with_gates(self):
        # An empty SKILL.md: both the packager and the gates report no Version
        # line (exact message parity). A genuine git-read failure is reported
        # separately by the explicit check on the skill read.
        code, stderr = run_packager(None, "1.0.14", raw_skill=b"")
        self.assertEqual(code, 1, stderr)
        self.assertIn("no Version: line found", stderr)
        for gate in (LINKS, CHECKSUM):
            matched, _ = gate_verdict(gate, "")
            self.assertFalse(matched)

    def test_invalid_utf8_is_rejected(self):
        # An invalid UTF-8 byte anywhere: the gates' read_text raises and the
        # packager's decode raises too, so both reject rather than the packager
        # building malformed text.
        head = subprocess.run(
            ["git", "-C", str(REPO), "show", "HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md"],
            capture_output=True, check=True,
        ).stdout
        raw = head + b"\n<!-- \xff -->\n"
        code, stderr = run_packager(None, "1.0.14", raw_skill=raw)
        self.assertEqual(code, 1, stderr)
        self.assertIn("not valid UTF-8", stderr)


class ZipLayoutTest(unittest.TestCase):
    """The skill source lives under skills/cleanlanguage/ for Agent Plugins
    discovery, but the published zip must still carry SKILL.md and its
    references at the archive root. This fails if the packager's re-root step
    is dropped or the source path regresses to the legacy root."""

    def test_source_is_nested_and_zip_is_rooted(self):
        tree = subprocess.run(
            ["git", "-C", str(REPO), "ls-tree", "-r", "--name-only", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        self.assertIn("cleanlanguage/skills/cleanlanguage/SKILL.md", tree)
        self.assertNotIn("cleanlanguage/SKILL.md", tree)
        with tempfile.TemporaryDirectory() as tmp:
            wt = Path(tmp) / "wt"
            subprocess.run(
                ["git", "-C", str(REPO), "worktree", "add", "--detach", str(wt), "HEAD"],
                capture_output=True, check=True,
            )
            try:
                proc = subprocess.run(
                    ["bash", str(wt / "tools" / "release-package.sh")],
                    capture_output=True, text=True,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                zip_path = wt / "dist" / "cleanlanguage.zip"
                entries = subprocess.run(
                    ["unzip", "-Z1", str(zip_path)],
                    capture_output=True, text=True, check=True,
                ).stdout.splitlines()
                self.assertIn("SKILL.md", entries)
                self.assertFalse(
                    any(e.startswith("skills/") for e in entries),
                    "the zip must not carry a skills/ subtree: %r" % entries,
                )
                archived = subprocess.run(
                    ["unzip", "-p", str(zip_path), "SKILL.md"],
                    capture_output=True, check=True,
                ).stdout
                blob = subprocess.run(
                    ["git", "-C", str(REPO), "show",
                     "HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md"],
                    capture_output=True, check=True,
                ).stdout
                self.assertEqual(archived, blob)
            finally:
                subprocess.run(
                    ["git", "-C", str(REPO), "worktree", "remove", "--force", str(wt)],
                    capture_output=True, check=True,
                )


if __name__ == "__main__":
    unittest.main()
