#!/usr/bin/env python3
"""Tests for tools/check-orchestration-registry.py.

Pins the structural gate on `.aiqt/orchestration.json`: the committed registry must
stay valid, and every malformation class the hook would classify `bad` (which, once a
lease or mode arms the scope-gated guards, fails them OPEN) must be rejected before it
lands. Runs offline with the standard library; the CI workflow invokes it after the
check itself.
"""

from __future__ import annotations

import json
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

    def test_companion_control_char(self):
        self._reject({"version": 1, "companion_stores": ["/opt/x\nevil"]})


if __name__ == "__main__":
    unittest.main()
