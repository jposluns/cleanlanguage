#!/usr/bin/env python3
"""Tests for check-agent-plugin-manifest.py.

Patch the gate's manifest paths to a temp fixture and drive the failure and
success paths offline with the standard library.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "check-agent-plugin-manifest.py"
spec = importlib.util.spec_from_file_location("check_agent_plugin_manifest", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"


def valid_manifest():
    return {
        "$schema": SCHEMA,
        "name": "cleanlanguage",
        "version": "1.0.14",
        "description": "d",
        "author": {"name": "Jeff Posluns", "url": "https://cleanlanguage.ai/"},
        "keywords": ["writing"],
    }


class AgentPluginManifestTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self._saved = (gate.REPO_ROOT, gate.MANIFEST, gate.CLAUDE_MANIFEST, gate.MARKETPLACE)
        gate.REPO_ROOT = root
        gate.MANIFEST = root / "cleanlanguage" / "plugin.json"
        gate.CLAUDE_MANIFEST = root / "cleanlanguage" / ".claude-plugin" / "plugin.json"
        gate.MARKETPLACE = root / ".claude-plugin" / "marketplace.json"
        gate.MANIFEST.parent.mkdir(parents=True)
        gate.CLAUDE_MANIFEST.parent.mkdir(parents=True)
        gate.MARKETPLACE.parent.mkdir(parents=True)
        gate.CLAUDE_MANIFEST.write_text(
            json.dumps({"name": "cleanlanguage", "version": "1.0.14"}), encoding="utf-8"
        )
        gate.MARKETPLACE.write_text(
            json.dumps({"plugins": [{"name": "cleanlanguage"}]}), encoding="utf-8"
        )

    def tearDown(self):
        (gate.REPO_ROOT, gate.MANIFEST, gate.CLAUDE_MANIFEST, gate.MARKETPLACE) = self._saved
        self._tmp.cleanup()

    def write(self, manifest):
        gate.MANIFEST.write_text(json.dumps(manifest), encoding="utf-8")

    def expect_exit(self, code, needle):
        err = io.StringIO()
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(err):
            gate.main()
        self.assertEqual(caught.exception.code, code)
        self.assertIn(needle, err.getvalue())

    def test_valid_passes(self):
        self.write(valid_manifest())
        self.assertEqual(gate.main(), 0)

    def test_wrong_schema_fails(self):
        manifest = valid_manifest()
        manifest["$schema"] = "https://example.com/x.json"
        self.write(manifest)
        self.expect_exit(1, "$schema must be")

    def test_bad_name_fails(self):
        manifest = valid_manifest()
        manifest["name"] = "Clean_Language"
        self.write(manifest)
        self.expect_exit(1, "name must match")

    def test_unknown_key_fails(self):
        manifest = valid_manifest()
        manifest["displayName"] = "Clean Language"
        self.write(manifest)
        self.expect_exit(1, "unknown top-level keys")

    def test_version_mismatch_with_claude_fails(self):
        manifest = valid_manifest()
        manifest["version"] = "9.9.9"
        self.write(manifest)
        self.expect_exit(1, "does not match the Claude manifest version")

    def test_name_mismatch_fails(self):
        manifest = valid_manifest()
        manifest["name"] = "other-name"
        self.write(manifest)
        self.expect_exit(1, "does not match")

    def test_unreadable_manifest_fails_closed(self):
        gate.MANIFEST.write_bytes(b"\xff")
        self.expect_exit(3, "could not be read")


if __name__ == "__main__":
    unittest.main()
