#!/usr/bin/env python3
"""Tests for check-agent-plugin-manifest.py.

Patch the gate's manifest paths to a temp fixture and drive the failure and
success paths offline with the standard library. The fixture also holds a root
LICENSE and NOTICE.md and their copies under cleanlanguage/, so the licence copy
cases can make a copy differ, go missing, or become a symlink, a FIFO, a folder,
a socket or a character device. On Linux the only other files that are not
regular are block devices, which no case makes. Creating a device node needs
the CAP_MKNOD capability, which an unprivileged run lacks, so there the device
case skips, as below, and the gate's refusal of a copy that is a device goes
untested. A further case makes a root LICENSE or NOTICE.md a symlink and
requires that the gate read it through the link: it passes when the link leads
to a file equal to the copy, and fails with the message that the copy differs
when it leads to a different file. The cases name the 2 files in COPIED_FILES
below, not in the gate's own list.

The licence-copy cases check outcomes only: the exit code, the message, that
the gate ends and, for a FIFO, whether anything opened it for reading. They
state no rule about how the gate reads a file:

- The edit sweep makes every copy that differs from its root file by 1 byte
  inserted (a space, a CR or an LF), 1 byte deleted, or 1 byte replaced (a
  letter by the same letter in the other case, any other byte by x or y), at
  every offset of the fixture texts below. For the repository's real LICENSE
  and NOTICE.md it makes the replacement at every offset, and every edit at
  offsets 0, len - 1 and len (where only an insertion exists). The gate must
  refuse every one of them with exit 1 and the message that the copy differs
  from the root file.
- A copy that is a FIFO, or a symlink to a FIFO, is checked in a process of
  its own, which must exit 1 with the copy's message within FIFO_TIMEOUT
  seconds, while a FifoWitness waits to open the FIFO for writing. A gate
  that opens the FIFO for reading before refusing the copy, with or without
  blocking, ends that wait, so it fails the case.
- A gate that reads a missing copy, a folder or a socket with its own
  read_bytes before refusing it stops with exit 3, not 1, so it fails the
  case for a missing copy, for a folder or for a socket.

Every FIFO, Unix socket, symlink and device node that a case makes is made
through make_node. Where the OS refuses to make that kind of node, with
EPERM, EACCES, EOPNOTSUPP or ENOSYS from the call that makes it, the case or
subtest cannot set up the state it tests, so it skips, naming the error, and
observes nothing about the gate. Any other error from that call, such as a
path that already exists, or a socket path longer than a socket address
holds, as under a long TMPDIR, is raised, so the case errors. unittest counts
a skipped case as skipped, not as failed, so a run whose other cases pass
ends with OK (skipped=N) and exit 0. When the OS refused any node, the run
then prints, after unittest's summary, the number of cases or subtests that
did not run for that reason, says that they observed nothing about the gate,
and names each, with the node and the error.

No case catches a gate that, before refusing a copy, reads through a symlink
to a regular file, lists a folder, tries to read a missing copy, a folder or a
socket and ignores the error, or opens a FIFO neither for reading nor with
blocking, such as with O_PATH: each leaves the exit code and the message the
same. No case makes a symlink to a device, such as /dev/zero, so a gate that
reads through one before refusing it is untested too. No case makes a block
device, and where the OS refuses to make a character device, as it does for
an unprivileged run, no case makes a device at all, so there a gate that
refuses only the other kinds and reads a device copy is untested as well.
Where the OS refuses to make a FIFO, a socket or a symlink, the cases that
need one skip, so there a gate that mishandles that kind passes the run, which
still exits 0; the summary line names those cases.
"""
from __future__ import annotations

import contextlib
import errno
import importlib.util
import io
import json
import os
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
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
# Seconds the gate may take to refuse a FIFO copy.
FIFO_TIMEOUT = 10
# The errors with which the OS refuses to make a kind of node: the run lacks
# the privilege (EPERM, EACCES), or the file system or the kernel does not
# support that kind (EOPNOTSUPP, ENOSYS). make_node skips only on these.
REFUSAL_ERRNOS = frozenset({errno.EPERM, errno.EACCES, errno.EOPNOTSUPP, errno.ENOSYS})
# One line for each case or subtest that skipped because the OS refused to
# make its node, printed after unittest's summary.
REFUSED_NODES: list[str] = []
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


def single_edits(data: bytes, every_kind_at=None):
    """Yield (kind, offset, edited) for the 1-byte insertions, deletions and
    replacements of ``data`` described in the module docstring: a replacement
    at every offset, and the insertions and the deletion at every offset in
    ``every_kind_at``, or at every offset when it is None."""
    for offset in range(len(data) + 1):
        every_kind = every_kind_at is None or offset in every_kind_at
        if every_kind:
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
        if every_kind:
            yield "delete", offset, data[:offset] + data[offset + 1:]


def bind_socket(path: Path) -> None:
    """Bind a Unix socket at ``path`` and close it, which leaves the socket
    file in place."""
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(path))


class FifoWitness:
    """A thread that waits to open the FIFO at ``path`` for writing, which
    records whether anything opened that FIFO for reading.

    An open of a FIFO for writing waits until a reader opens it. On Linux a
    reader that opens the FIFO, with or without O_NONBLOCK, ends that wait
    even if it closes the FIFO at once, so a gate that only opens the FIFO
    and closes it is recorded as well as one that reads it. The writer closes
    the FIFO without writing, so a gate that reads it gets no bytes and ends.
    Start the witness before the gate, and call ``opened_by_reader`` before
    ``release``, so that release's own open of the FIFO is not counted. An
    open by the gate before the thread begins to wait would go unrecorded,
    so that race can only hide an open, never report one that did not
    happen.
    """

    def __init__(self, path: Path):
        self.path = path
        self._waiting = threading.Event()
        self._opened = threading.Event()
        self._writer = threading.Thread(target=self._wait_for_reader, daemon=True)
        self._writer.start()
        self._waiting.wait(FIFO_TIMEOUT)

    def _wait_for_reader(self) -> None:
        self._waiting.set()
        try:
            os.close(os.open(self.path, os.O_WRONLY))
        except OSError:
            return
        self._opened.set()

    def opened_by_reader(self) -> bool:
        return self._opened.wait(0.2)

    def release(self) -> bool:
        """End a writer still waiting for a reader: open the FIFO for reading
        without blocking until the writer ends. Return whether it ended."""
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
            root = gate.REPO_ROOT / name
            if root.is_symlink():
                root.unlink()
            root.write_bytes(data)
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

    def expect_fifo_refusal(self, fifo: Path, needle):
        """Require the bounded refusal with ``needle`` while a FifoWitness
        watches ``fifo``, and require that nothing opened ``fifo`` for
        reading."""
        witness = FifoWitness(fifo)
        try:
            self.expect_bounded_refusal(needle)
            opened = witness.opened_by_reader()
        finally:
            ended = witness.release()
        self.assertTrue(ended, "the FIFO witness did not end")
        self.assertFalse(opened, f"the gate opened the FIFO {fifo.relative_to(gate.REPO_ROOT).as_posix()} "
                                 "before refusing the copy")

    def make_node(self, kind: str, path: Path, create, *args) -> None:
        """Make the node of ``kind`` (a FIFO, a Unix socket, a symlink or a
        device) at ``path`` by calling ``create(*args)``. Where the OS refuses
        to make that kind of node, with an error in REFUSAL_ERRNOS, the case
        cannot set up the state it tests, so it records the refusal in
        REFUSED_NODES and skips, naming the error. Any other error, such as a
        path that already exists or a socket path longer than a socket
        address holds, is raised, so the case errors."""
        try:
            create(*args)
        except OSError as error:
            if error.errno not in REFUSAL_ERRNOS:
                raise
            reason = f"the OS refused to make {kind} at {path.relative_to(gate.REPO_ROOT).as_posix()}: {error}"
            REFUSED_NODES.append(f"{self.id()}: {reason}")
            self.skipTest(reason)

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
        # fixture texts; for the real files, a replaced byte at every offset
        # and every edit at the first and last offsets. So a comparison that
        # ignores the byte at any offset of a real file, such as one of
        # sampled windows, or that compares a prefix no longer than the real
        # file, also fails.
        for name in COPIED_FILES:
            real = (REAL_ROOT / name).read_bytes()
            self.assertGreater(len(real), 1000)
            for label, data, edits in (
                ("fixture", LICENCE_TEXTS[name], single_edits(LICENCE_TEXTS[name])),
                ("real", real, single_edits(real, {0, len(real) - 1, len(real)})),
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
                self.make_node("a symlink", copy, copy.symlink_to, gate.REPO_ROOT / name)
                self.expect_exit(1, f"cleanlanguage/{name} is a symlink")
            with self.subTest(name, target="FIFO"):
                self.restore_licence_files()
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.unlink()
                fifo = gate.REPO_ROOT / f"{name}.fifo"
                self.make_node("a FIFO", fifo, os.mkfifo, fifo)
                try:
                    self.make_node("a symlink", copy, copy.symlink_to, fifo)
                    # A gate that opens the FIFO for reading through the link
                    # before refusing the link fails, with or without
                    # blocking.
                    self.expect_fifo_refusal(fifo, f"cleanlanguage/{name} is a symlink")
                finally:
                    fifo.unlink()

    def test_licence_copy_fifo_fails(self):
        # A FifoWitness waits to open the FIFO for writing, so a gate that
        # opens the FIFO for reading before refusing it fails, with or without
        # blocking.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            with self.subTest(name):
                self.restore_licence_files()
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.unlink()
                self.make_node("a FIFO", copy, os.mkfifo, copy)
                self.expect_fifo_refusal(copy, f"cleanlanguage/{name} is not a regular file")

    def test_licence_copy_folder_fails(self):
        self.write(valid_manifest())
        for name in COPIED_FILES:
            with self.subTest(name):
                self.restore_licence_files()
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.unlink()
                copy.mkdir()
                self.expect_exit(1, f"cleanlanguage/{name} is not a regular file")

    def test_licence_copy_socket_fails(self):
        # A Unix socket is the remaining kind that is not regular and that an
        # unprivileged test can make. Opening it fails, so a gate that reads it
        # with read_bytes before refusing it stops with exit 3, not 1. Where
        # the OS refuses to make the socket, each subtest skips, naming the
        # error.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            with self.subTest(name):
                self.restore_licence_files()
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.unlink()
                self.make_node("a Unix socket", copy, bind_socket, copy)
                self.expect_exit(1, f"cleanlanguage/{name} is not a regular file")

    def test_licence_copy_device_fails(self):
        # A character device with the numbers of /dev/null reads as empty, so
        # a gate that reads it before refusing it gives the message that the
        # copy differs, not the one required here. Making it needs the
        # CAP_MKNOD capability; where the OS refuses, each subtest skips,
        # naming the error.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            with self.subTest(name):
                self.restore_licence_files()
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.unlink()
                self.make_node("a character device", copy, os.mknod, copy,
                               stat.S_IFCHR | 0o600, os.makedev(1, 3))
                self.expect_exit(1, f"cleanlanguage/{name} is not a regular file")

    def test_root_licence_symlink_is_read_through(self):
        # The gate refuses a copy that is a symlink but not a root file that
        # is one: it reads the root file through the link, so it compares the
        # copy with the bytes of the file the link leads to. A root file
        # linked to its own copy passes, and one linked to a different file
        # fails with the message that the copy differs.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            root = gate.REPO_ROOT / name
            copy = gate.REPO_ROOT / "cleanlanguage" / name
            with self.subTest(name, target="its copy"):
                self.restore_licence_files()
                root.unlink()
                self.make_node("a symlink", root, root.symlink_to, copy)
                self.assertEqual(gate.main(), 0)
            with self.subTest(name, target="a different file"):
                self.restore_licence_files()
                other = gate.REPO_ROOT / f"{name}.other"
                other.write_bytes(LICENCE_TEXTS[name] + b"Other text.\n")
                root.unlink()
                self.make_node("a symlink", root, root.symlink_to, other)
                self.expect_exit(1, f"cleanlanguage/{name} differs from the root {name}")
        self.restore_licence_files()

    def test_unreadable_root_licence_fails_closed(self):
        self.write(valid_manifest())
        (gate.REPO_ROOT / "LICENSE").unlink()
        self.expect_exit(3, "LICENSE could not be read")


if __name__ == "__main__":
    program = unittest.main(exit=False)
    if REFUSED_NODES:
        print(f"test-agent-plugin-manifest: {len(REFUSED_NODES)} case(s) or subtest(s) did not run, because "
              "the OS refused to make the node each needs; unittest counts them as skipped, not as failed, "
              "and they observed nothing about the gate:", file=sys.stderr)
        for line in REFUSED_NODES:
            print(f"  {line}", file=sys.stderr)
    sys.exit(0 if program.result.wasSuccessful() else 1)
