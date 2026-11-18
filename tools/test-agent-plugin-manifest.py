#!/usr/bin/env python3
"""Tests for check-agent-plugin-manifest.py.

Patch the gate's manifest paths to a temp fixture and drive the failure and
success paths offline with the standard library. The fixture also holds a root
LICENSE and NOTICE.md and their copies under cleanlanguage/. The cases name the
2 files in COPIED_FILES below, not in the gate's own list.

The gate's refusal of each kind of licence copy is tested on every runner,
with no skip, through a seam. FakeNode answers os.stat and os.lstat for the
exact path of 1 file with a stat result of the kind under test, while the
file behind it stays a real, regular copy equal to its root file, and it
records every io.open, open, os.open, os.listdir and os.scandir of that path.
The gate asks for the type of a copy through pathlib's is_symlink, exists and
is_file, which look up os.lstat and os.stat when they are called, so the gate
sees the fake's type. For each copy and each of the 11 kinds in COPY_KINDS (a
symlink to a regular file, to a FIFO or to a character device, a dangling
symlink, a missing copy, a folder, a FIFO, a socket, a character device, a
block device and a type that Linux does not use),
test_licence_copy_kind_refused_untouched requires exit 1, the message for that
kind and no recorded access to the copy, so a gate that opens, reads or lists
a copy before refusing it fails, whether or not it ignores the error. A
control requires that a regular type through the same fake passes, that the
fake answered the gate and that the recorder saw the gate read the copy, so a
fake that no longer reaches the gate fails. A further seam case gives a root
LICENSE or NOTICE.md the type of a symlink and requires that the gate read it
through: it passes when its bytes equal the copy, and fails with the message
that the copy differs when they do not.

Real-node smoke cases make, where the OS allows it, a copy that is a symlink
(to the root file, to a FIFO, or to a path that does not exist), a FIFO, a
Unix socket or a character device, and a root file that is a symlink. Each
requires that the real node has the type that FakeNode gives that kind, and
runs the gate on it. They check outcomes only: the exit code, the message,
that the gate ends and, for a FIFO, whether anything opened it for reading:

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

Every FIFO, Unix socket, symlink and device node that a smoke case makes is
made through make_node. Where the OS refuses to make that kind of node, with
EPERM, EACCES, EOPNOTSUPP or ENOSYS from the call that makes it, the smoke
case or subtest skips, naming the error; the seam still tests the gate's
refusal of that kind. Any other error from that call, such as a path that
already exists, or a socket path longer than a socket address holds, as
under a long TMPDIR, is raised, so the case errors.
test_make_node_skips_only_on_refusal pins this policy, and a skip on any
other error fails it. unittest counts a skipped case as skipped, not as
failed, so a run whose other cases pass ends with OK (skipped=N) and exit 0.
The script then prints, after unittest's summary, each skip that unittest
recorded, with the test's id, which for a subtest carries its parameters, so
each skipped subtest is named once.

These residuals remain:

- The seam reaches the gate only while the gate asks for a file type through
  os.stat or os.lstat looked up when it is called. A gate that asks another
  way sees the real regular copy and accepts it, so every refusal subtest
  fails: a false alarm on a correct refactor, never a silent pass, and whoever
  changes that route must update FakeNode.
- Only io.open, open, os.open, os.listdir and os.scandir of the exact path
  string are recorded. A read before the refusal through io.FileIO, a dir_fd,
  a bytes path, another spelling of the path, a subprocess or ctypes is not
  caught.
- The seam case for a root file cannot catch a gate that detects a root
  symlink without os.lstat; the real-node case catches it where the OS lets
  the test make a symlink.
- Where the OS refuses to make a kind of node, nothing on that runner checks
  that FakeNode describes that kind as the kernel does. No unprivileged run
  can make a block device, so that kind has no smoke case, and a character
  device has one only where the run has the CAP_MKNOD capability.
- Deleting the lines that print the skip records fails no case; unittest's
  own summary still reads skipped=N.
- The seam has been run on Python 3.14 only. If a Python release reaches the
  type of a file another way, the seam fails closed, as in the first item.
"""
from __future__ import annotations

import builtins
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
# Errors outside REFUSAL_ERRNOS on which make_node must raise, not skip.
OTHER_ERRNOS = (errno.EEXIST, errno.ENAMETOOLONG, errno.ENOENT)
# A file type that Linux does not use (a Solaris door has this value).
FOREIGN_TYPE = 0o150000
# Each kind of node a licence copy can be: its label, the type that lstat of
# the copy gives, the type that stat of it gives (None where that call finds
# nothing) and the end of the gate's message for it.
COPY_KINDS = (
    ("symlink to a regular file", stat.S_IFLNK, stat.S_IFREG, "is a symlink"),
    ("symlink to a FIFO", stat.S_IFLNK, stat.S_IFIFO, "is a symlink"),
    ("symlink to a character device", stat.S_IFLNK, stat.S_IFCHR, "is a symlink"),
    ("dangling symlink", stat.S_IFLNK, None, "is a symlink"),
    ("missing", None, None, "is missing"),
    ("folder", stat.S_IFDIR, stat.S_IFDIR, "is not a regular file"),
    ("FIFO", stat.S_IFIFO, stat.S_IFIFO, "is not a regular file"),
    ("socket", stat.S_IFSOCK, stat.S_IFSOCK, "is not a regular file"),
    ("character device", stat.S_IFCHR, stat.S_IFCHR, "is not a regular file"),
    ("block device", stat.S_IFBLK, stat.S_IFBLK, "is not a regular file"),
    ("type that Linux does not use", FOREIGN_TYPE, FOREIGN_TYPE, "is not a regular file"),
)
KIND_TYPES = {label: (ltype, ftype) for label, ltype, ftype, _ in COPY_KINDS}
# The real calls, taken before any FakeNode replaces them.
REAL_STAT = os.stat
REAL_LSTAT = os.lstat
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


class FakeNode:
    """While in place, answer os.stat and os.lstat for 1 path with a stat
    result of the given types, and record every access to that path.

    ``ltype`` is the type that os.lstat gives and ``ftype`` the type that
    os.stat gives when it follows a symlink; None means that the call finds
    nothing. The other fields come from the real file, which stays as it is.
    A call with a dir_fd, or with any other path, goes to the real function.
    Every io.open, open, os.open, os.listdir and os.scandir of the path is
    recorded in ``touched`` before the real call, and every stat or lstat
    that the fake answered in ``answered``. Only the exact path string is
    matched: another spelling of the path, a bytes path or a dir_fd is not.
    """

    def __init__(self, path, ltype, ftype):
        self.path = os.fspath(path)
        self.ltype = ltype
        self.ftype = ftype
        self.touched: list[str] = []
        self.answered: list[str] = []
        self._saved: list[tuple[object, str, object]] = []

    def _hit(self, target) -> bool:
        try:
            return os.fspath(target) == self.path
        except TypeError:
            return False

    def _result(self, file_type):
        if file_type is None:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self.path)
        mode = file_type | (0o777 if file_type == stat.S_IFLNK else 0o644)
        return os.stat_result((mode,) + tuple(REAL_LSTAT(self.path))[1:10])

    def stat(self, path, *, dir_fd=None, follow_symlinks=True):
        if dir_fd is None and self._hit(path):
            self.answered.append("stat" if follow_symlinks else "lstat")
            return self._result(self.ftype if follow_symlinks else self.ltype)
        return REAL_STAT(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    def lstat(self, path, *, dir_fd=None):
        if dir_fd is None and self._hit(path):
            self.answered.append("lstat")
            return self._result(self.ltype)
        return REAL_LSTAT(path, dir_fd=dir_fd)

    def _recorder(self, label, real, keyword):
        def record(*args, **kwargs):
            target = args[0] if args else kwargs.get(keyword)
            if target is not None and self._hit(target):
                self.touched.append(label)
            return real(*args, **kwargs)
        return record

    def __enter__(self):
        patches = [
            (os, "stat", self.stat),
            (os, "lstat", self.lstat),
            (io, "open", self._recorder("io.open", io.open, "file")),
            (builtins, "open", self._recorder("open", builtins.open, "file")),
            (os, "open", self._recorder("os.open", os.open, "path")),
            (os, "listdir", self._recorder("os.listdir", os.listdir, "path")),
            (os, "scandir", self._recorder("os.scandir", os.scandir, "path")),
        ]
        for owner, name, replacement in patches:
            self._saved.append((owner, name, getattr(owner, name)))
            setattr(owner, name, replacement)
        return self

    def __exit__(self, *exc_info):
        while self._saved:
            owner, name, original = self._saved.pop()
            setattr(owner, name, original)
        return False


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
        to make that kind of node, with an error in REFUSAL_ERRNOS, the smoke
        case cannot set up the state it tests, so it skips, naming the error.
        Any other error, such as a path that already exists or a socket path
        longer than a socket address holds, is raised, so the case errors."""
        try:
            create(*args)
        except OSError as error:
            if error.errno not in REFUSAL_ERRNOS:
                raise
            self.skipTest(f"the OS refused to make {kind} at {path.relative_to(gate.REPO_ROOT).as_posix()}: {error}")

    def assert_real_kind(self, path: Path, label: str) -> None:
        """Require that the real node at ``path`` has the types that FakeNode
        gives the kind ``label`` in COPY_KINDS, so the seam describes that
        kind as the kernel does."""
        ltype, ftype = KIND_TYPES[label]
        self.assertEqual(stat.S_IFMT(REAL_LSTAT(path).st_mode), ltype, f"lstat type of a real {label}")
        if ftype is None:
            with self.assertRaises(FileNotFoundError):
                REAL_STAT(path)
        else:
            self.assertEqual(stat.S_IFMT(REAL_STAT(path).st_mode), ftype, f"stat type of a real {label}")

    def run_through_fake(self, fake: FakeNode):
        """Run the gate with ``fake`` in place; return its exit code and its
        stderr. An exit without SystemExit is 0."""
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            with fake:
                try:
                    code = gate.main()
                except SystemExit as stop:
                    code = stop.code
        return code, err.getvalue()

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

    def test_licence_copy_kind_refused_untouched(self):
        # The seam: on every runner and with no skip, each kind of copy in
        # COPY_KINDS must fail with exit 1 and its message before the gate
        # opens, reads or lists the copy, which stays a real regular file
        # equal to its root file, so a gate that accepts the kind, or reads
        # the copy before refusing it, fails.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            copy = gate.REPO_ROOT / "cleanlanguage" / name
            for label, ltype, ftype, message in COPY_KINDS:
                with self.subTest(name, kind=label):
                    self.restore_licence_files()
                    fake = FakeNode(copy, ltype, ftype)
                    code, err = self.run_through_fake(fake)
                    self.assertTrue(fake.answered, "the gate never asked the fake for the copy's type")
                    self.assertEqual(code, 1, err)
                    self.assertIn(f"cleanlanguage/{name} {message}", err)
                    self.assertEqual(fake.touched, [], f"the gate reached cleanlanguage/{name} before refusing it")

    def test_regular_copy_through_fake_is_read(self):
        # The control: a regular copy through the same fake passes, the fake
        # answered both calls, and the recorder saw the gate read the copy,
        # so a fake that no longer reaches the gate fails here.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            with self.subTest(name):
                self.restore_licence_files()
                fake = FakeNode(gate.REPO_ROOT / "cleanlanguage" / name, stat.S_IFREG, stat.S_IFREG)
                code, err = self.run_through_fake(fake)
                self.assertEqual(code, 0, err)
                self.assertIn("lstat", fake.answered)
                self.assertIn("stat", fake.answered)
                self.assertIn("io.open", fake.touched)

    def test_root_symlink_read_through_fake(self):
        # A root file whose lstat gives a symlink must be read, not refused:
        # it passes when its bytes equal the copy and fails with the message
        # that the copy differs when they do not.
        self.write(valid_manifest())
        for name in COPIED_FILES:
            root = gate.REPO_ROOT / name
            for target, data, code_wanted in (
                ("equal bytes", LICENCE_TEXTS[name], 0),
                ("different bytes", LICENCE_TEXTS[name] + b"Other text.\n", 1),
            ):
                with self.subTest(name, root=target):
                    self.restore_licence_files()
                    root.write_bytes(data)
                    fake = FakeNode(root, stat.S_IFLNK, stat.S_IFREG)
                    code, err = self.run_through_fake(fake)
                    self.assertEqual(code, code_wanted, err)
                    if code_wanted:
                        self.assertIn(f"cleanlanguage/{name} differs from the root {name}", err)
                    self.assertIn("io.open", fake.touched)
        self.restore_licence_files()

    def test_make_node_skips_only_on_refusal(self):
        # make_node must skip on each refusal error and raise every other
        # error. A skip counts as a pass in unittest, so a skip on any other
        # error is caught here and fails the subtest.
        path = gate.REPO_ROOT / "cleanlanguage" / "node"

        def refuse(code):
            raise OSError(code, os.strerror(code), str(path))

        for code in sorted(REFUSAL_ERRNOS):
            with self.subTest(errno=errno.errorcode[code]):
                with self.assertRaises(unittest.SkipTest) as caught:
                    self.make_node("a test node", path, refuse, code)
                self.assertIn(os.strerror(code), str(caught.exception))
        for code in OTHER_ERRNOS:
            with self.subTest(errno=errno.errorcode[code]):
                try:
                    self.make_node("a test node", path, refuse, code)
                except unittest.SkipTest as skip:
                    self.fail(f"make_node skipped on {errno.errorcode[code]}: {skip}")
                except OSError as error:
                    self.assertEqual(error.errno, code)
                else:
                    self.fail(f"make_node did not raise {errno.errorcode[code]}")

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
                self.assert_real_kind(copy, "symlink to a regular file")
                self.expect_exit(1, f"cleanlanguage/{name} is a symlink")
            with self.subTest(name, target="nothing"):
                # A dangling link is a symlink, not a missing copy.
                self.restore_licence_files()
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.unlink()
                self.make_node("a symlink", copy, copy.symlink_to, gate.REPO_ROOT / f"{name}.absent")
                self.assert_real_kind(copy, "dangling symlink")
                self.expect_exit(1, f"cleanlanguage/{name} is a symlink")
            with self.subTest(name, target="FIFO"):
                self.restore_licence_files()
                copy = gate.REPO_ROOT / "cleanlanguage" / name
                copy.unlink()
                fifo = gate.REPO_ROOT / f"{name}.fifo"
                self.make_node("a FIFO", fifo, os.mkfifo, fifo)
                try:
                    self.make_node("a symlink", copy, copy.symlink_to, fifo)
                    self.assert_real_kind(copy, "symlink to a FIFO")
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
                self.assert_real_kind(copy, "FIFO")
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
                self.assert_real_kind(copy, "socket")
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
                self.assert_real_kind(copy, "character device")
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
                self.assert_real_kind(root, "symlink to a regular file")
                self.assertEqual(gate.main(), 0)
            with self.subTest(name, target="a different file"):
                self.restore_licence_files()
                other = gate.REPO_ROOT / f"{name}.other"
                other.write_bytes(LICENCE_TEXTS[name] + b"Other text.\n")
                root.unlink()
                self.make_node("a symlink", root, root.symlink_to, other)
                self.assert_real_kind(root, "symlink to a regular file")
                self.expect_exit(1, f"cleanlanguage/{name} differs from the root {name}")
        self.restore_licence_files()

    def test_unreadable_root_licence_fails_closed(self):
        self.write(valid_manifest())
        (gate.REPO_ROOT / "LICENSE").unlink()
        self.expect_exit(3, "LICENSE could not be read")


if __name__ == "__main__":
    program = unittest.main(exit=False)
    # unittest's own skip records; a subtest's id carries its parameters.
    for test, reason in program.result.skipped:
        print(f"test-agent-plugin-manifest: skipped {test.id()}: {reason}", file=sys.stderr)
    sys.exit(0 if program.result.wasSuccessful() else 1)
