#!/usr/bin/env python3
"""Tests for check-agent-plugin-manifest.py.

Patch the gate's manifest paths to a temp fixture and drive the failure and
success paths offline with the standard library. The fixture also holds a root
LICENSE and NOTICE.md and their copies under cleanlanguage/, so the licence copy
cases can make a copy differ, go missing, or become a symlink, a FIFO or a
folder. The cases name the 2 files in COPIED_FILES below, not in the gate's own
list.

The licence-copy cases check outcomes only: the exit code, the message, and
that the gate ends. They state no rule about how the gate reads a file:

- The edit sweep makes every copy that differs from its root file by 1 byte
  inserted (a space, a CR or an LF), 1 byte deleted, or 1 byte replaced (a
  letter by the same letter in the other case, any other byte by x or y), at
  every offset of the fixture texts below, and at offsets 0, len - 1 and len
  (where only an insertion exists) of the repository's real LICENSE and
  NOTICE.md. The gate must refuse every one of them with exit 1 and the
  message that the copy differs from the root file.
- A copy that is a FIFO with no writer, or a symlink to such a FIFO, is
  checked in a process of its own, which must exit 1 with the copy's message
  within FIFO_TIMEOUT seconds. A gate that opens that FIFO for a blocking
  read, as open() and Path.read_bytes do, waits for a writer that never
  comes, so it fails the case by timing out.

No case catches a gate that, before refusing a copy, reads through a symlink
to a regular file, reads a folder, or opens a FIFO without blocking: each
leaves the exit code and the message the same.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "check-agent-plugin-manifest.py"
REAL_ROOT = MODULE_PATH.parent.parent
spec = importlib.util.spec_from_file_location("check_agent_plugin_manifest", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
# The root files that cleanlanguage/ must carry as byte-equal copies, named
# here and not read from the gate, so a gate that drops 1 of them fails.
COPIED_FILES = ("LICENSE", "NOTICE.md")
LICENCE_TEXTS = {
    "LICENSE": b"Apache License\nVersion 2.0, January 2004\nhttp://www.apache.org/licenses/\n\nTERMS AND CONDITIONS\n",
    "NOTICE.md": b"# Notice\n\n## Scope\n\nThe licence text is in [LICENSE](LICENSE).\n\n## Clean Language\n\nCopyright line.\n",
}
# Seconds the gate may take to refuse a FIFO copy that has no writer.
FIFO_TIMEOUT = 10
# Runs the gate's licence-copy check on the fixture root given as argv[2].
DRIVER = (
    "import importlib.util, sys\n"
    "from pathlib import Path\n"
    "spec = importlib.util.spec_from_file_location('gate', sys.argv[1])\n"
    "gate = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(gate)\n"
    "gate.REPO_ROOT = Path(sys.argv[2])\n"
    "gate.check_licence_copies()\n"
)


def single_edits(data: bytes):
    """Yield (kind, offset, edited) for every 1-byte insertion, deletion and
    replacement of ``data`` described in the module docstring."""
    for offset in range(len(data) + 1):
        for inserted in (b" ", b"\r", b"\n"):
            yield f"insert {inserted!r}", offset, data[:offset] + inserted + data[offset:]
        if offset == len(data):
            break
        byte = data[offset:offset + 1]
        if byte.isalpha():
            replaced = byte.swapcase()
        else:
            replaced = b"x" if byte != b"x" else b"y"
        yield "replace", offset, data[:offset] + replaced + data[offset + 1:]
        yield "delete", offset, data[:offset] + data[offset + 1:]


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
        self.restore_licence_files()

    def restore_licence_files(self):
        """Write each root licence file and a regular, equal copy, replacing
        whatever a case left at the copy's path."""
        for name, data in LICENCE_TEXTS.items():
            (gate.REPO_ROOT / name).write_bytes(data)
            copy = gate.REPO_ROOT / "cleanlanguage" / name
            if copy.is_dir() and not copy.is_symlink():
                copy.rmdir()
            elif copy.is_symlink() or copy.exists():
                copy.unlink()
            copy.write_bytes(data)

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

    def expect_bounded_refusal(self, needle):
        """Run the licence-copy check in a process of its own and require exit
        1 with ``needle`` within FIFO_TIMEOUT seconds; on timeout, kill the
        process group, so a reader the gate started ends too."""
        proc = subprocess.Popen(
            [sys.executable, "-I", "-c", DRIVER, str(MODULE_PATH), str(gate.REPO_ROOT)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
        )
        try:
            _out, err = proc.communicate(timeout=FIFO_TIMEOUT)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            self.fail(f"the gate did not end within {FIFO_TIMEOUT} s; it waits on a FIFO copy")
        self.assertEqual(proc.returncode, 1, err)
        self.assertIn(needle, err.decode("utf-8", "replace"))

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
        self.expect_exit(1, "does not match the Claude manifest name")

    def test_unreadable_manifest_fails_closed(self):
        gate.MANIFEST.write_bytes(b"\xff")
        self.expect_exit(3, "could not be read")

    def test_unreadable_claude_manifest_fails_closed(self):
        self.write(valid_manifest())
        gate.CLAUDE_MANIFEST.write_bytes(b"\xff")
        self.expect_exit(3, "could not be read")

    def test_marketplace_name_mismatch_fails(self):
        # Claude name matches the root manifest, but the marketplace entry does
        # not, so the marketplace cross-check must fire.
        gate.CLAUDE_MANIFEST.write_text(
            json.dumps({"name": "other-name", "version": "1.0.14"}), encoding="utf-8"
        )
        manifest = valid_manifest()
        manifest["name"] = "other-name"
        self.write(manifest)
        self.expect_exit(1, "marketplace plugins[0].name")

    def test_extensions_value_not_object_fails(self):
        manifest = valid_manifest()
        manifest["extensions"] = {"org.example": 42}
        self.write(manifest)
        self.expect_exit(1, "must be an object")

    def test_missing_version_fails(self):
        manifest = valid_manifest()
        del manifest["version"]
        self.write(manifest)
        self.expect_exit(1, "version is required")

    def test_trailing_newline_name_fails(self):
        manifest = valid_manifest()
        manifest["name"] = "cleanlanguage\n"
        self.write(manifest)
        self.expect_exit(1, "name must match")

    def test_non_standard_json_number_fails(self):
        # Python's json accepts NaN/Infinity by default; the gate must reject
        # them as not valid JSON.
        gate.MANIFEST.write_text(
            '{"$schema": "' + SCHEMA + '", "name": "cleanlanguage", "version": NaN}',
            encoding="utf-8",
        )
        self.expect_exit(1, "is not valid JSON")

    def test_non_list_plugins_fails(self):
        gate.MARKETPLACE.write_text(
            json.dumps({"plugins": "not-a-list"}), encoding="utf-8"
        )
        self.write(valid_manifest())
        self.expect_exit(1, "no plugins array")

    def test_deeply_nested_json_fails_closed(self):
        # A pathologically deep JSON document makes json.loads raise
        # RecursionError; the gate must fail closed, not raise an uncaught
        # traceback.
        gate.MANIFEST.write_text('{"x":' + "[" * 100000, encoding="utf-8")
        self.expect_exit(1, "is not valid JSON")

    def test_root_skills_key_stays_rejected(self):
        # Step-3 decision: skill discovery is convention-based; the root
        # Agent Plugins manifest carries no skills field.
        manifest = valid_manifest()
        manifest["skills"] = ["./skills/cleanlanguage"]
        self.write(manifest)
        self.expect_exit(1, "unknown top-level keys")

    def test_licence_copy_differs_fails(self):
        # A valid manifest still fails when cleanlanguage/LICENSE is not a
        # byte-equal copy of the root LICENSE, even by 1 trailing byte.
        self.write(valid_manifest())
        (gate.REPO_ROOT / "cleanlanguage" / "LICENSE").write_bytes(LICENCE_TEXTS["LICENSE"] + b"\n")
        self.expect_exit(1, "cleanlanguage/LICENSE differs from the root LICENSE")

    def test_notice_copy_differs_fails(self):
        self.write(valid_manifest())
        (gate.REPO_ROOT / "cleanlanguage" / "NOTICE.md").write_bytes(b"# Notice\n\nOther scope.\n")
        self.expect_exit(1, "cleanlanguage/NOTICE.md differs from the root NOTICE.md")

    def test_root_licence_changed_alone_fails(self):
        # Editing the root file without its copy is the same drift.
        self.write(valid_manifest())
        (gate.REPO_ROOT / "LICENSE").write_bytes(b"Another licence\n")
        self.expect_exit(1, "cleanlanguage/LICENSE differs from the root LICENSE")

    def test_licence_copy_missing_fails(self):
        self.write(valid_manifest())
        for name in COPIED_FILES:
            with self.subTest(name):
                self.restore_licence_files()
                (gate.REPO_ROOT / "cleanlanguage" / name).unlink()
                self.expect_exit(1, f"cleanlanguage/{name} is missing")

    def test_licence_copy_single_edit_sweep_fails(self):
        # See the module docstring: every 1-byte edit at every offset of the
        # fixture texts, and at the first and last offsets of the real files,
        # so a comparison of any prefix shorter than the real file also fails.
        for name in COPIED_FILES:
            real = (REAL_ROOT / name).read_bytes()
            self.assertGreater(len(real), 1000)
            for label, data, edits in (
                ("fixture", LICENCE_TEXTS[name], single_edits(LICENCE_TEXTS[name])),
                ("real", real, (edit for edit in single_edits(real)
                                if edit[1] in (0, len(real) - 1, len(real)))),
            ):
                root = gate.REPO_ROOT / name
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                root.write_bytes(data)
                copy.write_bytes(data)
                gate.check_licence_copies()  # the unedited pair passes
                needle = f"cleanlanguage/{name} differs from the root {name}"
                accepted = []
                count = 0
                for kind, offset, edited in edits:
                    self.assertNotEqual(edited, data)
                    copy.write_bytes(edited)
                    count += 1
                    err = io.StringIO()
                    try:
                        with contextlib.redirect_stderr(err):
                            gate.check_licence_copies()
                    except SystemExit as stop:
                        if stop.code != 1 or needle not in err.getvalue():
                            accepted.append((kind, offset, f"exit {stop.code}: {err.getvalue().strip()}"))
                        continue
                    accepted.append((kind, offset, "accepted"))
                self.assertGreaterEqual(count, 10)
                self.assertEqual(accepted[:5], [],
                                 f"{label} cleanlanguage/{name}: {len(accepted)} of {count} edits not refused "
                                 f"with exit 1 and {needle!r}")
            self.restore_licence_files()

    def test_licence_copy_symlink_fails(self):
        # A symlink to the root file reads equal, but the plugin tree would
        # then point outside itself, so only a regular file passes.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            with self.subTest(name, target="root file"):
                self.restore_licence_files()
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.unlink()
                copy.symlink_to(gate.REPO_ROOT / name)
                self.expect_exit(1, f"cleanlanguage/{name} is a symlink")
            with self.subTest(name, target="FIFO"):
                self.restore_licence_files()
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.unlink()
                fifo = gate.REPO_ROOT / f"{name}.fifo"
                os.mkfifo(fifo)
                copy.symlink_to(fifo)
                try:
                    self.expect_bounded_refusal(f"cleanlanguage/{name} is a symlink")
                finally:
                    fifo.unlink()

    def test_licence_copy_fifo_fails(self):
        # A FIFO with no writer: a gate that opens it for a blocking read
        # waits for ever, so the case fails by timing out.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            with self.subTest(name):
                self.restore_licence_files()
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.unlink()
                os.mkfifo(copy)
                self.expect_bounded_refusal(f"cleanlanguage/{name} is not a regular file")

    def test_licence_copy_folder_fails(self):
        self.write(valid_manifest())
        for name in COPIED_FILES:
            with self.subTest(name):
                self.restore_licence_files()
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.unlink()
                copy.mkdir()
                self.expect_exit(1, f"cleanlanguage/{name} is not a regular file")

    def test_unreadable_root_licence_fails_closed(self):
        self.write(valid_manifest())
        (gate.REPO_ROOT / "LICENSE").unlink()
        self.expect_exit(3, "LICENSE could not be read")


if __name__ == "__main__":
    unittest.main()
