#!/usr/bin/env python3
"""Tests for check-agent-plugin-manifest.py.

Patch the gate's manifest paths to a temp fixture and drive the failure and
success paths offline with the standard library. The fixture also holds a root
LICENSE and NOTICE.md and their copies under cleanlanguage/, so the licence copy
cases can make a copy differ, go missing, or become a symlink, a FIFO or a
folder. Each fixture text is longer than 64 bytes, and the cases for a missing
copy, a symlink, a FIFO, a folder, a same-length difference, a difference past
the first 64 bytes, a difference only in line endings, a difference only in
case and a difference only in trailing spaces each cover both files. These
cases name the 2 files in COPIED_FILES below, not in the gate's own list, so a
gate that drops a file from its list, compares lengths, compares only a prefix,
or ignores line endings, case or trailing spaces fails a case. The FIFO case,
and the symlink case whose link points at a FIFO, also fail when the gate opens
that FIFO, and the symlink case whose link points at the root file fails when
the gate opens the link or the file it points at through open(), io.open() or
os.open(), so a gate that reads a copy that is not a regular file before
refusing it fails a case.
"""
from __future__ import annotations

import builtins
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parent / "check-agent-plugin-manifest.py"
spec = importlib.util.spec_from_file_location("check_agent_plugin_manifest", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
# The root files that cleanlanguage/ must carry as byte-equal copies, named
# here and not read from the gate, so a gate that drops 1 of them fails.
COPIED_FILES = ("LICENSE", "NOTICE.md")
# Each text is longer than 64 bytes, so a difference can lie past a 64-byte
# prefix, and holds several LF line endings, so a copy can differ in CR LF only.
LICENCE_TEXTS = {
    "LICENSE": b"Apache License\nVersion 2.0, January 2004\nhttp://www.apache.org/licenses/\n\nTERMS AND CONDITIONS\n",
    "NOTICE.md": b"# Notice\n\n## Scope\n\nThe licence text is in [LICENSE](LICENSE).\n\n## Clean Language\n\nCopyright line.\n",
}


def with_byte_changed(data: bytes, index: int) -> bytes:
    """``data`` with the byte at ``index`` replaced by another, so the length stays the same."""
    changed = b"x" if data[index:index + 1] != b"x" else b"y"
    return data[:index] + changed + data[index + 1:]


@contextlib.contextmanager
def recording_opens():
    """Within the block, record the resolved path of every file opened by
    name through open(), io.open() or os.open(). Path.read_bytes and
    Path.read_text open through io.open, so a read in any of these forms is
    recorded, and a link is recorded as the file it points at."""
    opened = []
    real_open, real_io_open, real_os_open = builtins.open, io.open, os.open

    def note(file) -> None:
        if not isinstance(file, int):
            opened.append(os.path.realpath(os.fsdecode(os.fspath(file))))

    def spy_open(file, *args, **kwargs):
        note(file)
        return real_open(file, *args, **kwargs)

    def spy_io_open(file, *args, **kwargs):
        note(file)
        return real_io_open(file, *args, **kwargs)

    def spy_os_open(path, *args, **kwargs):
        note(path)
        return real_os_open(path, *args, **kwargs)

    with mock.patch.object(builtins, "open", spy_open), mock.patch.object(io, "open", spy_io_open), \
            mock.patch.object(os, "open", spy_os_open):
        yield opened


class FifoWitness:
    """A FIFO at ``path`` and a thread that writes ``data`` into it once a
    reader opens it, which records whether anything opened the FIFO.

    A gate that reads the FIFO gets ``data``, the root file's bytes, so it
    finds them equal and does not block. ``opened_by_reader`` tells whether a
    reader opened the FIFO before ``release``: a gate that reads the FIFO to
    its end returns only after the writer has opened it and recorded that, and
    the short wait covers a gate that opens it and closes it without reading.
    ``release`` opens the FIFO itself, so the writer ends, and records nothing.
    """

    def __init__(self, path: Path, data: bytes):
        self.path = path
        self.data = data
        self._opened = threading.Event()
        self._releasing = threading.Event()
        os.mkfifo(path)
        self._writer = threading.Thread(target=self._feed, daemon=True)
        self._writer.start()

    def _feed(self) -> None:
        try:
            with open(self.path, "wb") as fifo:
                if not self._releasing.is_set():
                    self._opened.set()
                fifo.write(self.data)
        except OSError:
            pass

    def opened_by_reader(self) -> bool:
        return self._opened.wait(0.2)

    def release(self) -> bool:
        """End a writer still waiting for a reader: open the FIFO for reading
        without blocking until the writer ends. Return whether it ended."""
        self._releasing.set()
        for _ in range(100):
            if not self._writer.is_alive():
                return True
            reader = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
            try:
                self._writer.join(0.05)
            finally:
                os.close(reader)
        return not self._writer.is_alive()


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

    def test_licence_copy_symlink_fails(self):
        # A symlink to the root file reads equal, but the plugin tree would
        # then point outside itself, so only a regular file passes. The case
        # records every file the gate opens through open(), io.open() or
        # os.open(), which Path.read_bytes and Path.read_text use, and fails
        # if the gate opens the link or the root file the link points at,
        # which the gate has no reason to read before it refuses the link. A second link points at a FIFO that
        # a writer feeds with the root file's bytes, and the case fails if the
        # gate opens that FIFO. So a gate that reads through a link before
        # refusing it fails here, whether the link points at a regular file
        # or at a FIFO.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            with self.subTest(name, target="root file"):
                self.restore_licence_files()
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.unlink()
                copy.symlink_to(gate.REPO_ROOT / name)
                target = os.path.realpath(copy)
                self.assertEqual(target, os.path.realpath(gate.REPO_ROOT / name))
                # The recorder sees a read through the link in the form the
                # gate reads a copy, so an empty record is not a blind one.
                with recording_opens() as opened:
                    gate.read_bytes(copy)
                self.assertIn(target, opened)
                with recording_opens() as opened:
                    self.expect_exit(1, f"cleanlanguage/{name} is a symlink")
                self.assertNotIn(target, opened,
                                 f"the gate read through the symlink cleanlanguage/{name} before refusing it")
            with self.subTest(name, target="FIFO"):
                self.restore_licence_files()
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.unlink()
                fifo = gate.REPO_ROOT / f"{name}.fifo"
                witness = FifoWitness(fifo, LICENCE_TEXTS[name])
                copy.symlink_to(fifo)
                try:
                    self.expect_exit(1, f"cleanlanguage/{name} is a symlink")
                    opened = witness.opened_by_reader()
                finally:
                    ended = witness.release()
                    fifo.unlink()
                self.assertTrue(ended, "the FIFO writer did not end")
                self.assertFalse(opened, f"the gate read through the symlink cleanlanguage/{name} before refusing it")

    def test_licence_copy_same_length_difference_fails(self):
        # 1 changed byte keeps the length, so a gate that compares only
        # lengths passes this copy.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            with self.subTest(name):
                self.restore_licence_files()
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.write_bytes(with_byte_changed(LICENCE_TEXTS[name], 0))
                self.assertEqual(len(copy.read_bytes()), len(LICENCE_TEXTS[name]))
                self.expect_exit(1, f"cleanlanguage/{name} differs from the root {name}")

    def test_licence_copy_late_difference_fails(self):
        # The changed byte lies past the first 64 bytes and keeps the length,
        # so a gate that compares a 64-byte prefix or the lengths passes this
        # copy.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            with self.subTest(name):
                self.restore_licence_files()
                index = len(LICENCE_TEXTS[name]) - 2
                self.assertGreaterEqual(index, 64)
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.write_bytes(with_byte_changed(LICENCE_TEXTS[name], index))
                self.expect_exit(1, f"cleanlanguage/{name} differs from the root {name}")

    def test_licence_copy_line_ending_difference_fails(self):
        # The copy differs from its root file only in CR LF line endings, so a
        # gate that reads text with universal newlines, or folds CR LF to LF
        # before comparing, passes this copy.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            with self.subTest(name):
                self.restore_licence_files()
                data = LICENCE_TEXTS[name]
                crlf = data.replace(b"\n", b"\r\n")
                self.assertNotEqual(crlf, data)
                self.assertEqual(crlf.replace(b"\r\n", b"\n"), data)
                (gate.REPO_ROOT / "cleanlanguage" / name).write_bytes(crlf)
                self.expect_exit(1, f"cleanlanguage/{name} differs from the root {name}")

    def test_licence_copy_case_difference_fails(self):
        # The copy differs from its root file only in the case of its
        # letters, so a gate that lowercases or uppercases both texts before
        # comparing them passes this copy.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            with self.subTest(name):
                self.restore_licence_files()
                data = LICENCE_TEXTS[name]
                swapped = data.swapcase()
                self.assertNotEqual(swapped, data)
                self.assertEqual(swapped.lower(), data.lower())
                self.assertEqual(swapped.upper(), data.upper())
                (gate.REPO_ROOT / "cleanlanguage" / name).write_bytes(swapped)
                self.expect_exit(1, f"cleanlanguage/{name} differs from the root {name}")

    def test_licence_copy_trailing_space_difference_fails(self):
        # The copy differs from its root file only by 1 space at the end of
        # its first line, or by 1 space after its last line ending, so a gate
        # that strips trailing spaces from each line, or from the end of the
        # text, before comparing passes 1 of these copies.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            data = LICENCE_TEXTS[name]
            first_end = data.index(b"\n")
            for where, spaced in (("line end", data[:first_end] + b" " + data[first_end:]),
                                  ("text end", data + b" ")):
                with self.subTest(name, where=where):
                    self.restore_licence_files()
                    self.assertNotEqual(spaced, data)
                    self.assertEqual(
                        b"\n".join(line.rstrip(b" ") for line in spaced.split(b"\n")), data)
                    (gate.REPO_ROOT / "cleanlanguage" / name).write_bytes(spaced)
                    self.expect_exit(1, f"cleanlanguage/{name} differs from the root {name}")

    def test_licence_copy_fifo_fails(self):
        # A FIFO is neither a symlink nor missing. A writer feeds it the root
        # file's bytes, so a gate that reads it finds them equal and does not
        # block; the case also fails if the gate opens the FIFO at all, so it
        # passes only for a gate that refuses the FIFO before reading it.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            with self.subTest(name):
                self.restore_licence_files()
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.unlink()
                witness = FifoWitness(copy, LICENCE_TEXTS[name])
                try:
                    self.expect_exit(1, f"cleanlanguage/{name} is not a regular file")
                    opened = witness.opened_by_reader()
                finally:
                    ended = witness.release()
                self.assertTrue(ended, "the FIFO writer did not end")
                self.assertFalse(opened, f"the gate read the FIFO cleanlanguage/{name} before refusing it")

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
