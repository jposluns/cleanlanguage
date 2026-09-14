#!/usr/bin/env python3
"""Tests for tools/check-orchestration-registry.py.

Pins the structural gate on `.aiqt/orchestration.json`: the committed registry must
stay valid, and every malformation class the hook would classify `bad` (a corrupt
registry has divergent, partly fail-open orchestrator outcomes once armed, and its
`orch_yield_tool` denies scheduling fail-closed even unarmed) must be rejected before
it lands. Runs offline with the standard library; the CI workflow invokes it after the
check itself.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR = HERE / "check-orchestration-registry.py"
REPO_ROOT = HERE.parent
REAL_REGISTRY = REPO_ROOT / ".aiqt" / "orchestration.json"


def _run(path) -> int:
    """Run the validator against `path`; return its exit code."""
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        capture_output=True, text=True,
    ).returncode


def _write(tmpdir, payload) -> Path:
    """Write `payload` (a str written verbatim, or any object dumped as JSON) to a temp file."""
    p = Path(tmpdir) / "orchestration.json"
    if isinstance(payload, str):
        p.write_text(payload, encoding="utf-8")
    else:
        p.write_text(json.dumps(payload), encoding="utf-8")
    return p


class RealRegistry(unittest.TestCase):
    def test_committed_registry_is_valid(self):
        # The actual committed registry must always pass; this is the regression guard.
        if not REAL_REGISTRY.exists():
            self.skipTest("no committed .aiqt/orchestration.json")
        self.assertEqual(_run(REAL_REGISTRY), 0)


class Accepts(unittest.TestCase):
    def test_absent_is_ok(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(Path(d) / "does-not-exist.json"), 0)

    def test_minimal_companion_store(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "companion_stores": ["/opt/x/private"]})), 0)

    def test_version_only(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1})), 0)

    def test_empty_companion_list(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "companion_stores": []})), 0)

    def test_windows_absolute_path_accepted(self):
        # The hook's _is_absolute is OS-agnostic; a drive-and-root Windows path is structurally
        # absolute, so the gate must accept it even running on POSIX, to match what the hook accepts.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "companion_stores": ["C:\\repo"]})), 0)


class Rejects(unittest.TestCase):
    def _reject(self, payload):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, payload)), 1)

    def test_invalid_json(self):
        self._reject("{ not json")

    def test_top_level_not_object(self):
        self._reject([1, 2, 3])

    def test_version_missing(self):
        self._reject({"companion_stores": ["/opt/x"]})

    def test_version_two(self):
        self._reject({"version": 2})

    def test_version_bool(self):
        # bool is a subclass of int; it must be rejected, mirroring the hook's `type(v) is int`.
        self._reject({"version": True})

    def test_version_string(self):
        self._reject({"version": "1"})

    def test_companion_not_a_list(self):
        self._reject({"version": 1, "companion_stores": "/opt/x"})

    def test_companion_relative_path(self):
        self._reject({"version": 1, "companion_stores": ["relative/path"]})

    def test_companion_empty_string(self):
        self._reject({"version": 1, "companion_stores": [""]})

    def test_companion_non_string(self):
        self._reject({"version": 1, "companion_stores": [123]})

    def test_companion_control_char_low(self):
        self._reject({"version": 1, "companion_stores": ["/opt/x\nevil"]})

    def test_companion_control_char_del(self):
        # 0x7f (DEL) is >= 0x20 but the hook rejects it too; the gate must match.
        self._reject({"version": 1, "companion_stores": ["/opt/x\u007f"]})

    def test_present_but_unreadable_dangling_symlink(self):
        # A dangling registry symlink is present (lstat succeeds) but unreadable (open follows to a
        # missing target); the hook classifies this bad, so the gate must fail, not treat it as absent.
        with tempfile.TemporaryDirectory() as d:
            link = Path(d) / "orchestration.json"
            os.symlink(str(Path(d) / "missing-target.json"), str(link))
            self.assertEqual(_run(link), 1)

    def test_invalid_utf8(self):
        # A non-UTF-8 registry must fail CLEANLY: a FAIL diagnostic on stderr, no traceback. Asserting
        # only exit 1 would pass even without the decode handler (an uncaught traceback also exits 1),
        # so this checks stderr and therefore fails without the handler that catches the read-time
        # UnicodeError.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "orchestration.json"
            p.write_bytes(b"\xff\xfe\x00")
            r = subprocess.run(
                [sys.executable, str(VALIDATOR), str(p)], capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 1)
            self.assertIn("FAIL", r.stderr)
            self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
