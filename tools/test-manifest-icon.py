#!/usr/bin/env python3
"""Tests for check-manifest-icon.py.

Patch the gate repository root and manifest set to a temporary fixture holding all
five manifests and a generated icon, and drive the failure and success paths
offline with the standard library. Every image fixture is built at run time; no
binary fixture file is tracked. OSError paths are driven by unittest.mock, not by
chmod; a mock of a descriptor call is scoped to the descriptors opened for either
the icon or the manifests, so it cannot fire on the wrong file.
"""
from __future__ import annotations

import contextlib
import errno
import importlib.util
import io
import json
import os
import shutil
import signal
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parent / "check-manifest-icon.py"
spec = importlib.util.spec_from_file_location("check_manifest_icon", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

REAL_ICON = Path(__file__).resolve().parent.parent / "cleanlanguage" / "assets" / "CL_icon.png"

CLAUDE = "cleanlanguage/.claude-plugin/plugin.json"
MARKET = ".claude-plugin/marketplace.json"
HOOKS = "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json"
MANIFESTS = (
    MARKET,
    CLAUDE,
    "cleanlanguage/plugin.json",
    "plugin/.claude-plugin/marketplace.json",
    HOOKS,
)


class StalledOpen(Exception):
    """Raised by the alarm handler when an open blocks; deliberately not an OSError."""


def png_chunk(chunk_type: bytes, payload: bytes, corrupt: bool = False) -> bytes:
    crc = zlib.crc32(chunk_type + payload)
    if corrupt:
        crc ^= 1
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)


def ihdr_payload(width, height, depth=8, colour=6, interlace=0) -> bytes:
    return struct.pack(">IIBBBBB", width, height, depth, colour, 0, 0, interlace)


IDAT = png_chunk(b"IDAT", zlib.compress(b""))
IEND = png_chunk(b"IEND", b"")


def png_from(*chunks) -> bytes:
    """The PNG signature followed by the given complete chunks, in order."""
    return gate.PNG_SIGNATURE + b"".join(chunks)


def make_png(
    width,
    height,
    depth=8,
    colour=6,
    interlace=0,
    before_idat=(),
    with_idat=True,
    with_iend=True,
    trailing=b"",
    corrupt_crc_of=None,
    first_chunk=None,
    ihdr_length=13,
):
    """A complete PNG: signature, IHDR, extra chunks, one IDAT, IEND, trailing bytes."""
    ihdr = ihdr_payload(width, height, depth, colour, interlace)
    ihdr = (ihdr + bytes(16))[:ihdr_length]
    out = gate.PNG_SIGNATURE
    if first_chunk is not None:
        out += png_chunk(*first_chunk)
    out += png_chunk(b"IHDR", ihdr, corrupt_crc_of == b"IHDR")
    for chunk_type, payload in before_idat:
        out += png_chunk(chunk_type, payload, corrupt_crc_of == chunk_type)
    if with_idat:
        out += png_chunk(b"IDAT", zlib.compress(b""), corrupt_crc_of == b"IDAT")
    if with_iend:
        out += png_chunk(b"IEND", b"", corrupt_crc_of == b"IEND")
    return out + trailing


def padded_png(total: int) -> bytes:
    """A 512 x 512 PNG padded by one private ancillary chunk to exactly total bytes."""
    base = len(make_png(512, 512))
    return make_png(512, 512, before_idat=((b"prVt", bytes(total - base - 12)),))


def jpeg_segment(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def frame_payload(width, height, components=3, precision=8, identifiers=None) -> bytes:
    if identifiers is None:
        identifiers = range(1, components + 1)
    table = b"".join(bytes([identifier, 0x11, 0]) for identifier in identifiers)
    return struct.pack(">BHHB", precision, height, width, components) + table


SOS = jpeg_segment(0xDA, bytes([1, 1, 0, 0, 63, 0]))
SOI = b"\xff\xd8"


def table_jpeg(sof, tables):
    """SOI, a 3-component frame header, a scan with the given table bytes, EOI.

    The scan names components 1 onward, one per table selector byte (DC table in
    the high four bits, AC table in the low four bits).
    """
    entries = b"".join(bytes([index + 1, value]) for index, value in enumerate(tables))
    scan = jpeg_segment(0xDA, bytes([len(tables)]) + entries + bytes([0, 63, 0]))
    return SOI + jpeg_segment(sof, frame_payload(512, 512)) + scan + b"\x00\xff\xd9"


def make_jpeg(width, height, sof=0xC0, pre=(), components=3, fill=b"", with_sos=True,
              with_eoi=True, precision=8):
    """SOI, pre-segments (raw bytes), fill bytes, a frame header, a minimal SOS, EOI."""
    out = SOI + b"".join(pre) + fill + jpeg_segment(
        sof, frame_payload(width, height, components, precision)
    )
    if with_sos:
        out += SOS + b"\x00\x01\x02"
    if with_eoi:
        out += b"\xff\xd9"
    return out


class ManifestIconTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._saved = (gate.REPO_ROOT, gate.MANIFESTS, gate.REQUIRED_ICON_MANIFESTS)
        gate.REPO_ROOT = self.root
        gate.MANIFESTS = MANIFESTS
        gate.REQUIRED_ICON_MANIFESTS = (CLAUDE,)
        for rel in MANIFESTS:
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        self.write_json(MARKET, {"name": "m", "plugins": [{"name": "cleanlanguage"}]})
        self.write_json("plugin/.claude-plugin/marketplace.json", {"name": "p", "plugins": []})
        self.write_json("cleanlanguage/plugin.json", {"name": "cleanlanguage"})
        self.write_json(HOOKS, {"name": "hooks"})
        self.claude = {
            "name": "cleanlanguage",
            "version": "1.0.14",
            "icon": "./assets/CL_icon.png",
            "skills": ["./skills/cleanlanguage"],
        }
        self.write_json(CLAUDE, self.claude)
        self.assets = self.root / "cleanlanguage" / "assets"
        self.assets.mkdir()
        (self.assets / "CL_icon.png").write_bytes(make_png(512, 512))

    def tearDown(self):
        (gate.REPO_ROOT, gate.MANIFESTS, gate.REQUIRED_ICON_MANIFESTS) = self._saved
        self._tmp.cleanup()

    def write_json(self, rel, data):
        (self.root / rel).write_text(json.dumps(data), encoding="utf-8")

    def set_icon(self, name, data, value=None):
        (self.assets / name).write_bytes(data)
        self.claude["icon"] = value if value is not None else f"./assets/{name}"
        self.write_json(CLAUDE, self.claude)

    def set_icon_value(self, value):
        self.claude["icon"] = value
        self.write_json(CLAUDE, self.claude)

    def expect_exit(self, code, needle):
        err = io.StringIO()
        out = io.StringIO()
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            gate.main()
        self.assertEqual(caught.exception.code, code, err.getvalue())
        self.assertIn(needle, err.getvalue())
        return err.getvalue()

    def expect_image_error(self, name, image_format, reason):
        """Expect exit 1 whose whole stderr is the parse refusal of icon name for reason."""
        err = self.expect_exit(1, reason)
        icon = "./assets/" + name
        self.assertEqual(
            err,
            f"check-manifest-icon: {CLAUDE} field icon: icon file {icon!r} is not a "
            f"parseable {image_format}: {reason}\n",
        )

    def resolve_raising(self, target, error):
        """Patch Path.resolve to raise error for the path target only."""
        real_resolve = Path.resolve

        def fake_resolve(path, *args, **kwargs):
            if path == target:
                raise error
            return real_resolve(path, *args, **kwargs)

        return mock.patch.object(gate.Path, "resolve", autospec=True, side_effect=fake_resolve)

    def expect_pass(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(gate.main(), 0)
        return out.getvalue()

    def run_check_icon(self, base, repo_root=None, icon="./assets/CL_icon.png"):
        """Call check_icon directly; return (exit code, stderr) or (0, stdout)."""
        err = io.StringIO()
        out = io.StringIO()
        if repo_root is None:
            repo_root = self.root.resolve()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            try:
                gate.check_icon(CLAUDE, "icon", icon, base, repo_root)
            except SystemExit as caught:
                return caught.code, err.getvalue()
        return 0, out.getvalue()

    @contextlib.contextmanager
    def scoped_io(self, manifests=False, open_error=None, fstat_result=None,
                  fstat_error=None, read_result=None, read_error=None, read_sizes=None):
        """Mock os.open, os.fstat and os.read for the icon only, or for manifests only.

        Yields the list of scoped paths whose open was attempted, so a test can show
        the mock reached the file it targets. When read_sizes is a list, every scoped
        read returns a full block of the size it asks for and appends that size, so
        the file never ends. More than 10000 scoped reads of any kind raise
        RuntimeError, so an unbounded read loop fails the test instead of hanging it.
        """
        real_open, real_fstat, real_read = os.open, os.fstat, os.read
        attempts = []
        scoped_fds = set()

        def in_scope(path):
            return (Path(os.fsdecode(path)).suffix == ".json") == manifests

        def fake_open(path, flags, *args, **kwargs):
            if not in_scope(path):
                return real_open(path, flags, *args, **kwargs)
            attempts.append(Path(os.fsdecode(path)))
            if open_error is not None:
                raise open_error
            fd = real_open(path, flags, *args, **kwargs)
            scoped_fds.add(fd)
            return fd

        def fake_fstat(fd, *args, **kwargs):
            if fd in scoped_fds:
                if fstat_error is not None:
                    raise fstat_error
                if fstat_result is not None:
                    return fstat_result
            return real_fstat(fd, *args, **kwargs)

        reads = []

        def fake_read(fd, count):
            if fd in scoped_fds:
                reads.append(count)
                if len(reads) > 10000:
                    raise RuntimeError("a scoped read loop is unbounded")
                if read_error is not None:
                    raise read_error
                if read_result is not None:
                    return read_result
                if read_sizes is not None:
                    read_sizes.append(count)
                    return bytes(count)
            return real_read(fd, count)

        with mock.patch.object(gate.os, "open", side_effect=fake_open), \
                mock.patch.object(gate.os, "fstat", side_effect=fake_fstat), \
                mock.patch.object(gate.os, "read", side_effect=fake_read):
            yield attempts

    # Pass cases.

    def test_repository_icon_passes(self):
        self.set_icon("CL_icon.png", REAL_ICON.read_bytes())
        self.assertIn("512 x 512 pixels, 18590 bytes", self.expect_pass())

    def test_png_512_passes(self):
        out = self.expect_pass()
        self.assertIn(f"{CLAUDE} field icon: ./assets/CL_icon.png is a PNG of 512 x 512 pixels", out)

    def test_png_2048_passes(self):
        self.set_icon("CL_icon.png", make_png(2048, 2048))
        self.assertIn("2048 x 2048", self.expect_pass())

    def test_png_ancillary_and_private_chunks_pass(self):
        extra = (
            (b"tEXt", b"Comment\x00hello"),
            (b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00<x/>"),
            (b"pHYs", bytes(9)),
            (b"mkBF", b"\xff\xc0\x00\x11 private"),
            (b"zTXt", b"Comment\x00\x00" + zlib.compress(b"z")),
        )
        self.set_icon("CL_icon.png", make_png(512, 512, before_idat=extra))
        self.assertIn("512 x 512", self.expect_pass())

    def test_interlaced_png_passes(self):
        self.set_icon("CL_icon.png", make_png(512, 512, interlace=1))
        self.expect_pass()

    def test_jpeg_baseline_passes(self):
        self.set_icon("icon.jpg", make_jpeg(512, 512))
        self.assertIn("is a JPEG of 512 x 512 pixels", self.expect_pass())

    def test_jpeg_progressive_1024_passes(self):
        self.set_icon("icon.jpeg", make_jpeg(1024, 1024, sof=0xC2))
        self.assertIn("is a JPEG of 1024 x 1024 pixels", self.expect_pass())

    def test_jpeg_skips_segments_by_length(self):
        exif_thumbnail_sof = b"\xff\xc0\x00\x11\x08\x00\x64\x00\x64\x03" + bytes(9)
        pre = (
            jpeg_segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"),
            jpeg_segment(0xE1, b"Exif\x00\x00" + exif_thumbnail_sof),
            jpeg_segment(0xEE, b"Adobe\x00\x64\x00\x00\x00\x00\x01"),
            jpeg_segment(0xDB, bytes(65)),
            jpeg_segment(0xC4, bytes(17) + bytes(4)),
        )
        self.set_icon("icon.jpg", make_jpeg(512, 512, pre=pre))
        self.assertIn("is a JPEG of 512 x 512 pixels", self.expect_pass())

    def test_jpeg_fill_bytes_and_rst_before_sof_pass(self):
        rst = b"".join(bytes([0xFF, marker]) for marker in range(0xD0, 0xD8))
        pre = (jpeg_segment(0xE0, b"JFIF\x00"), b"\xff\xff\xff\xd0", b"\xff\x01", rst)
        self.set_icon("icon.jpg", make_jpeg(512, 512, pre=pre, fill=b"\xff\xff"))
        self.expect_pass()

    def test_jpeg_named_jpg_and_png_named_png_pass(self):
        for name, data in (
            ("a.jpg", make_jpeg(512, 512)),
            ("b.JPEG", make_jpeg(512, 512)),
            ("c.png", make_png(512, 512)),
            ("d.PNG", make_png(512, 512)),
        ):
            with self.subTest(name=name):
                self.set_icon(name, data)
                self.expect_pass()

    def test_size_just_under_limit_passes(self):
        self.set_icon("CL_icon.png", padded_png(gate.MAX_ICON_BYTES - 1))
        self.assertIn(f"{gate.MAX_ICON_BYTES - 1} bytes", self.expect_pass())

    def test_bom_manifest_passes(self):
        (self.root / CLAUDE).write_bytes(b"\xef\xbb\xbf" + json.dumps(self.claude).encode("utf-8"))
        self.expect_pass()

    def test_other_manifests_without_icon_pass(self):
        out = self.expect_pass()
        self.assertEqual(len(out.strip().splitlines()), 1)

    def test_dot_vcs_directory_is_pruned(self):
        hidden = self.root / ".git"
        hidden.mkdir()
        (hidden / "plugin.json").write_text("{}", encoding="utf-8")
        self.expect_pass()

    # Manifest set (M1, M2).

    def test_unlisted_manifest_on_disk_fails(self):
        (self.root / "extra").mkdir()
        (self.root / "extra" / "plugin.json").write_text("{}", encoding="utf-8")
        self.expect_exit(1, "extra/plugin.json is on disk but not declared in MANIFESTS")

    def test_unlisted_marketplace_on_disk_fails(self):
        (self.root / "extra" / ".claude-plugin").mkdir(parents=True)
        (self.root / "extra" / ".claude-plugin" / "marketplace.json").write_text("{}", encoding="utf-8")
        self.expect_exit(1, "extra/.claude-plugin/marketplace.json is on disk but not declared in MANIFESTS")

    def test_declared_manifest_set_and_root_are_exact(self):
        real_root, real_manifests, real_required = self._saved
        self.assertEqual(real_root, MODULE_PATH.parent.parent)
        self.assertEqual(real_manifests, MANIFESTS)
        self.assertEqual(real_required, (CLAUDE,))

    def test_tree_walk_oserror_fails_closed(self):
        with mock.patch.object(gate.os, "walk", side_effect=OSError("walk refused")):
            self.expect_exit(3, "could not be listed")

    def test_tree_walk_unlistable_directory_fails_closed(self):
        real_scandir = os.scandir
        target = self.root / "plugin"

        def fake_scandir(path="."):
            if Path(os.fsdecode(path)) == target:
                raise PermissionError(13, "Permission denied", str(path))
            return real_scandir(path)

        with mock.patch.object(gate.os, "scandir", side_effect=fake_scandir):
            self.expect_exit(3, "could not be listed")

    def test_listed_manifest_absent_fails_closed(self):
        (self.root / HOOKS).unlink()
        self.expect_exit(3, f"{HOOKS} could not be read")

    def test_manifest_unreadable_fails_closed(self):
        (self.root / CLAUDE).write_bytes(b"\xff")
        self.expect_exit(3, "could not be read")

    def test_manifest_invalid_json_fails(self):
        (self.root / CLAUDE).write_text("{", encoding="utf-8")
        self.expect_exit(1, "is not valid JSON")

    def test_manifest_nan_constant_fails(self):
        (self.root / CLAUDE).write_text("{\"x\": NaN}", encoding="utf-8")
        self.expect_exit(1, "non-standard JSON constant")

    def test_manifest_not_object_fails(self):
        (self.root / CLAUDE).write_text("[1]", encoding="utf-8")
        self.expect_exit(1, "is not a JSON object")

    def test_manifest_json_recursion_fails_closed(self):
        with mock.patch.object(gate.json, "loads", side_effect=RecursionError):
            self.expect_exit(3, "could not be decoded")

    # Manifest paths (M2): no symlink anywhere, regular file, opened without following.

    def test_manifest_symlink_file_fails(self):
        real = self.root / "cleanlanguage" / ".claude-plugin" / "real.json"
        real.write_text(json.dumps(self.claude), encoding="utf-8")
        (self.root / CLAUDE).unlink()
        os.symlink("real.json", self.root / CLAUDE)
        self.expect_exit(1, f"{CLAUDE} path component " + repr("plugin.json") + " is a symlink")

    def test_manifest_symlink_directory_fails(self):
        with tempfile.TemporaryDirectory() as outside:
            Path(outside, "plugin.json").write_text(json.dumps(self.claude), encoding="utf-8")
            shutil.rmtree(self.root / "cleanlanguage" / ".claude-plugin")
            os.symlink(outside, self.root / "cleanlanguage" / ".claude-plugin")
            self.expect_exit(1, f"{CLAUDE} path component " + repr(".claude-plugin") + " is a symlink")

    def test_manifest_component_not_directory_fails(self):
        shutil.rmtree(self.root / "plugin")
        (self.root / "plugin").write_text("not a directory", encoding="utf-8")
        self.expect_exit(
            1, "plugin/.claude-plugin/marketplace.json path component " + repr("plugin") + " is not a directory"
        )

    def test_manifest_is_directory_fails(self):
        (self.root / HOOKS).unlink()
        (self.root / HOOKS).mkdir()
        self.expect_exit(1, f"{HOOKS} is not a regular file")

    def test_non_regular_manifest_is_never_opened(self):
        (self.root / HOOKS).unlink()
        os.mkfifo(self.root / HOOKS)
        real_open = os.open
        calls = []

        def spy(path, *args, **kwargs):
            calls.append(Path(os.fsdecode(path)))
            return real_open(path, *args, **kwargs)

        with mock.patch.object(gate.os, "open", side_effect=spy):
            self.expect_exit(1, f"{HOOKS} is not a regular file")
        self.assertNotIn(self.root / HOOKS, calls)
        self.assertEqual(len(calls), 4)

    def test_manifest_lstat_oserror_fails_closed(self):
        real_lstat = os.lstat
        target = self.root / "cleanlanguage" / ".claude-plugin"

        def fake_lstat(path, *args, **kwargs):
            if Path(os.fsdecode(path)) == target:
                raise PermissionError(13, "Permission denied", str(path))
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(gate.os, "lstat", side_effect=fake_lstat):
            self.expect_exit(3, f"{CLAUDE} could not be read")

    def test_manifest_open_oserror_fails_closed(self):
        with self.scoped_io(manifests=True, open_error=PermissionError(13, "Permission denied")) as attempts:
            self.expect_exit(3, f"{MARKET} could not be read")
        self.assertEqual(len(attempts), 1)

    def test_manifest_fstat_non_regular_fails(self):
        fifo_mode = os.stat_result((0o010644, 0, 0, 1, 0, 0, 100, 0, 0, 0))
        with self.scoped_io(manifests=True, fstat_result=fifo_mode):
            self.expect_exit(1, f"{MARKET} is not a regular file")

    def test_manifest_read_stops_at_end_of_file(self):
        with self.scoped_io(manifests=True, read_result=b""):
            self.expect_exit(1, f"{MARKET} is not valid JSON")

    def test_manifest_read_oserror_fails_closed(self):
        with self.scoped_io(manifests=True, read_error=OSError(5, "Input/output error")):
            self.expect_exit(3, f"{MARKET} could not be read: [Errno 5]")

    def test_manifest_final_symlink_missed_by_lstat_is_refused_by_open(self):
        real = self.root / "cleanlanguage" / ".claude-plugin" / "real.json"
        real.write_text(json.dumps(self.claude), encoding="utf-8")
        (self.root / CLAUDE).unlink()
        os.symlink("real.json", self.root / CLAUDE)
        real_lstat = os.lstat
        target = self.root / CLAUDE

        def fake_lstat(path, *args, **kwargs):
            if Path(os.fsdecode(path)) == target:
                return os.stat(path)
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(gate.os, "lstat", side_effect=fake_lstat):
            self.expect_exit(3, f"{CLAUDE} could not be read: [Errno {errno.ELOOP}]")

    def test_open_flags_refuse_symlinks_and_never_block(self):
        real_open = os.open
        seen = []

        def spy(path, flags, *args, **kwargs):
            seen.append((Path(os.fsdecode(path)).suffix, flags))
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(gate.os, "open", side_effect=spy):
            self.expect_pass()
        self.assertEqual(sorted(suffix for suffix, _ in seen), [".json"] * 5 + [".png"])
        for suffix, flags in seen:
            with self.subTest(suffix=suffix):
                for label, bit in (("O_NOFOLLOW", os.O_NOFOLLOW), ("O_NONBLOCK", os.O_NONBLOCK),
                                   ("O_CLOEXEC", os.O_CLOEXEC)):
                    self.assertEqual(flags | bit, flags, f"{suffix} open lacks {label}")
                self.assertNotEqual(flags | os.O_WRONLY, flags)
                self.assertNotEqual(flags | os.O_RDWR, flags)

    # Required icon and marketplace scope (M3, M4).

    def test_icon_missing_from_required_manifest_fails(self):
        del self.claude["icon"]
        self.write_json(CLAUDE, self.claude)
        self.expect_exit(1, f"{CLAUDE} field icon is missing")

    def test_required_manifest_not_declared_fails(self):
        gate.REQUIRED_ICON_MANIFESTS = (CLAUDE, "other/.claude-plugin/plugin.json")
        self.expect_exit(1, "required icon manifest other/.claude-plugin/plugin.json is not declared")

    def test_no_icon_checked_is_vacuous(self):
        gate.REQUIRED_ICON_MANIFESTS = ()
        del self.claude["icon"]
        self.write_json(CLAUDE, self.claude)
        self.expect_exit(1, "no icon field was checked")

    def test_marketplace_icon_fails(self):
        self.write_json(MARKET, {"name": "m", "icon": "./x.png", "plugins": []})
        self.expect_exit(1, f"{MARKET} field icon: an icon in a marketplace manifest is not supported")
        self.write_json(MARKET, {"name": "m", "plugins": [{"name": "a"}, "icon", {"icon": "./x.png"}]})
        self.expect_exit(1, f"{MARKET} field plugins[2].icon: an icon in a marketplace manifest")

    def test_plugin_entry_icon_in_plugin_manifest_is_checked(self):
        self.write_json(HOOKS, {"name": "hooks", "plugins": [{"icon": "./missing.png"}]})
        self.expect_exit(1, f"{HOOKS} field plugins[0].icon: icon file does not exist")

    def test_other_manifest_icon_resolves_against_its_plugin_root(self):
        hooks_root = self.root / "plugin" / "aiqt-guardrails-hooks"
        (hooks_root / "hooks.png").write_bytes(make_png(600, 600))
        self.write_json(HOOKS, {"name": "hooks", "icon": "./hooks.png"})
        out = self.expect_pass()
        self.assertIn(f"{HOOKS} field icon: ./hooks.png is a PNG of 600 x 600", out)

    # Path syntax (P1-P3).

    def test_icon_not_string_fails(self):
        for value in (123, None, ["./a.png"]):
            with self.subTest(value=value):
                self.set_icon_value(value)
                self.expect_exit(1, "must be a non-empty string")

    def test_icon_empty_or_whitespace_fails(self):
        for value in ("", "   "):
            with self.subTest(value=value):
                self.set_icon_value(value)
                self.expect_exit(1, "must be a non-empty string")

    def test_icon_absolute_path_fails(self):
        self.set_icon_value("/etc/passwd")
        self.expect_exit(1, "must be a canonical ./relative path")

    def test_icon_traversal_fails(self):
        for value in ("../x.png", "./a/../../x.png", "./assets/./CL_icon.png",
                      "./assets//CL_icon.png", "./assets/CL_icon.png/", "./", "./..", ".//x"):
            with self.subTest(value=value):
                self.set_icon_value(value)
                self.expect_exit(1, "must be a canonical ./relative path")

    def test_icon_without_dot_slash_fails(self):
        self.set_icon_value("assets/CL_icon.png")
        self.expect_exit(1, "must be a canonical ./relative path")

    def test_icon_backslash_fails(self):
        self.set_icon_value(".\\assets\\CL_icon.png")
        self.expect_exit(1, "backslash")

    def test_icon_nul_fails(self):
        self.set_icon_value("./assets/CL_icon.png\x00")
        self.expect_exit(1, "NUL")

    def test_icon_control_and_surrogate_fail(self):
        for value in ("./assets/CL\x01icon.png", "./assets/CL\x7ficon.png",
                      "./assets/CL\nicon.png", "./assets/CL\x1ficon.png", "./assets/CL\ud800icon.png",
                      "./assets/CL\udffficon.png"):
            with self.subTest(value=value):
                self.set_icon_value(value)
                self.expect_exit(1, "contains a control, NUL, surrogate, or backslash character")

    # Filesystem (F1-F5).

    def test_icon_file_missing_fails(self):
        self.set_icon_value("./assets/absent.png")
        self.expect_exit(1, "icon file does not exist")

    def test_icon_parent_missing_fails(self):
        self.set_icon_value("./nowhere/CL_icon.png")
        self.expect_exit(1, "icon file does not exist")

    def test_icon_symlink_final_component_fails(self):
        (self.assets / "real.png").write_bytes(make_png(512, 512))
        os.symlink("real.png", self.assets / "link.png")
        self.set_icon_value("./assets/link.png")
        self.expect_exit(1, "path component " + repr("link.png") + " of")

    def test_icon_symlink_directory_component_outside_fails(self):
        with tempfile.TemporaryDirectory() as outside:
            Path(outside, "CL_icon.png").write_bytes(make_png(512, 512))
            shutil.rmtree(self.assets)
            os.symlink(outside, self.assets)
            self.expect_exit(1, "is a symlink")

    def test_plugin_root_symlink_outside_repository_fails(self):
        with tempfile.TemporaryDirectory() as outside:
            moved = Path(outside) / "cleanlanguage"
            shutil.move(str(self.root / "cleanlanguage"), str(moved))
            os.symlink(moved, self.root / "cleanlanguage")
            self.expect_exit(1, "component " + repr("cleanlanguage") + " is a symlink")

    def test_symlinked_plugin_root_inside_repository_fails(self):
        hidden = self.root / ".git"
        hidden.mkdir()
        shutil.move(str(self.root / "cleanlanguage"), str(hidden / "qa-root"))
        os.symlink(".git/qa-root", self.root / "cleanlanguage")
        self.expect_exit(1, "component " + repr("cleanlanguage") + " is a symlink")

    def test_check_icon_refuses_symlinked_plugin_root(self):
        shutil.move(str(self.root / "cleanlanguage"), str(self.root / "real-plugin"))
        os.symlink("real-plugin", self.root / "cleanlanguage")
        code, text = self.run_check_icon(self.root / "cleanlanguage")
        self.assertEqual(code, 1, text)
        self.assertIn("plugin root component " + repr("cleanlanguage") + " is a symlink", text)

    def test_check_icon_refuses_plugin_root_that_is_not_a_directory(self):
        code, text = self.run_check_icon(self.root / "cleanlanguage" / "plugin.json")
        self.assertEqual(code, 1, text)
        self.assertIn("plugin root component " + repr("plugin.json") + " is not a directory", text)

    def test_check_icon_plugin_root_outside_repository_root_fails_closed(self):
        with tempfile.TemporaryDirectory() as outside:
            code, text = self.run_check_icon(Path(outside))
        self.assertEqual(code, 3, text)
        self.assertIn("is not inside the repository root", text)

    def test_check_icon_plugin_root_uninspectable_fails_closed(self):
        real_lstat = os.lstat
        target = self.root / "cleanlanguage"

        def fake_lstat(path, *args, **kwargs):
            if Path(os.fsdecode(path)) == target:
                raise PermissionError(13, "Permission denied", str(path))
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(gate.os, "lstat", side_effect=fake_lstat):
            code, text = self.run_check_icon(target)
        self.assertEqual(code, 3, text)
        self.assertIn("plugin root component " + repr("cleanlanguage") + " could not be inspected", text)

    def test_check_icon_resolving_outside_repository_fails(self):
        with tempfile.TemporaryDirectory() as outside:
            code, text = self.run_check_icon(self.root / "cleanlanguage", Path(outside).resolve())
        self.assertEqual(code, 1, text)
        self.assertIn("resolves outside the repository", text)

    def test_icon_resolving_outside_plugin_root_fails(self):
        other = self.root / "other"
        other.mkdir()
        (other / "CL_icon.png").write_bytes(make_png(512, 512))
        shutil.rmtree(self.assets)
        os.symlink("../other", self.assets)
        real_lstat = os.lstat
        lied = []

        def fake_lstat(path, *args, **kwargs):
            # Lie only to the gate walk, as a directory swapped in after it would; the
            # tree walk (os.walk calls os.path.islink) and resolve() see the truth.
            frame = sys._getframe(1)
            while frame is not None and frame.f_code.co_filename == mock.__file__:
                frame = frame.f_back
            caller = frame.f_code.co_name if frame is not None else ""
            if Path(os.fsdecode(path)) == self.assets and caller == "walk_without_symlinks":
                lied.append(path)
                return os.stat(path)
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(gate.os, "lstat", side_effect=fake_lstat):
            self.expect_exit(1, "resolves outside the plugin root")
        self.assertEqual(len(lied), 1)

    def test_icon_is_directory_fails(self):
        (self.assets / "dir.png").mkdir()
        self.set_icon_value("./assets/dir.png")
        self.expect_exit(1, "is not a regular file")

    def test_non_regular_icon_is_never_opened(self):
        (self.assets / "dir.png").mkdir()
        os.mkfifo(self.assets / "fifo.png")
        real_open = os.open
        for name in ("dir.png", "fifo.png"):
            with self.subTest(name=name):
                calls = []

                def spy(path, *args, **kwargs):
                    calls.append(Path(os.fsdecode(path)))
                    return real_open(path, *args, **kwargs)

                self.set_icon_value(f"./assets/{name}")
                with mock.patch.object(gate.os, "open", side_effect=spy):
                    self.expect_exit(1, "is not a regular file")
                self.assertEqual([call for call in calls if call.suffix != ".json"], [])
                self.assertEqual(len(calls), 5)

    def test_final_symlink_missed_by_lstat_is_refused_by_open(self):
        (self.assets / "real.png").write_bytes(make_png(512, 512))
        os.symlink("real.png", self.assets / "link.png")
        self.set_icon_value("./assets/link.png")
        real_lstat = os.lstat
        target = self.assets / "link.png"

        def fake_lstat(path, *args, **kwargs):
            if Path(os.fsdecode(path)) == target:
                return os.stat(path)
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(gate.os, "lstat", side_effect=fake_lstat):
            self.expect_exit(3, "icon file " + repr("./assets/link.png") + f" could not be read: [Errno {errno.ELOOP}]")

    def test_fifo_missed_by_lstat_does_not_stall_the_open(self):
        os.mkfifo(self.assets / "fifo.png")
        self.set_icon_value("./assets/fifo.png")
        regular = os.lstat(self.assets / "CL_icon.png")
        real_lstat = os.lstat
        target = self.assets / "fifo.png"

        def fake_lstat(path, *args, **kwargs):
            if Path(os.fsdecode(path)) == target:
                return regular
            return real_lstat(path, *args, **kwargs)

        def on_alarm(signum, frame):
            raise StalledOpen("the open of a FIFO blocked")

        previous = signal.signal(signal.SIGALRM, on_alarm)
        signal.alarm(5)
        try:
            with mock.patch.object(gate.os, "lstat", side_effect=fake_lstat):
                self.expect_exit(1, "is not a regular file")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)

    def test_fstat_non_regular_fails(self):
        fifo_mode = os.stat_result((0o010644, 0, 0, 1, 0, 0, 100, 0, 0, 0))
        with self.scoped_io(fstat_result=fifo_mode) as attempts:
            self.expect_exit(1, "field icon: icon path " + repr("./assets/CL_icon.png") + " is not a regular file")
        self.assertEqual(len(attempts), 1)

    def test_fstat_oserror_fails_closed(self):
        with self.scoped_io(fstat_error=OSError(5, "Input/output error")):
            self.expect_exit(3, "field icon: icon file " + repr("./assets/CL_icon.png") + " could not be read")

    def test_icon_component_not_directory_fails(self):
        self.set_icon_value("./assets/CL_icon.png/inner.png")
        self.expect_exit(1, "is not a regular file")

    def test_icon_open_oserror_fails_closed(self):
        with self.scoped_io(open_error=PermissionError(13, "Permission denied")) as attempts:
            self.expect_exit(3, "field icon: icon file " + repr("./assets/CL_icon.png") + " could not be read")
        self.assertEqual(len(attempts), 1)

    def test_icon_read_oserror_fails_closed(self):
        with self.scoped_io(read_error=OSError(5, "Input/output error")):
            self.expect_exit(3, "field icon: icon file " + repr("./assets/CL_icon.png") + " could not be read")

    def test_icon_lstat_oserror_fails_closed(self):
        real_lstat = os.lstat

        def fake_lstat(path, *args, **kwargs):
            if Path(path).name == "CL_icon.png":
                raise PermissionError(13, "Permission denied", str(path))
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(gate.os, "lstat", side_effect=fake_lstat):
            self.expect_exit(3, "could not be inspected")

    def test_icon_lstat_io_error_fails_closed(self):
        real_lstat = os.lstat

        def fake_lstat(path, *args, **kwargs):
            if Path(path).name == "CL_icon.png":
                raise OSError(errno.EIO, "Input/output error", str(path))
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(gate.os, "lstat", side_effect=fake_lstat):
            self.expect_exit(3, "icon path " + repr("./assets/CL_icon.png") + " could not be inspected: [Errno 5]")

    def test_file_changed_during_read_fails_closed(self):
        with self.scoped_io(read_result=b""):
            self.expect_exit(3, "changed while it was read")

    def test_icon_read_is_bounded(self):
        # A file that grows without end is read to MAX_ICON_BYTES + 1 bytes at most,
        # in blocks of at most READ_BLOCK, and then refused as changed.
        sizes = []
        with self.scoped_io(read_sizes=sizes) as attempts:
            self.expect_exit(
                3, "field icon: icon file " + repr("./assets/CL_icon.png") + " changed while it was read"
            )
        self.assertEqual(len(attempts), 1)
        self.assertEqual(sum(sizes), 2000001)
        self.assertEqual(len(sizes), 31)
        self.assertEqual(max(sizes), 65536)
        self.assertEqual(sizes[-1], 2000001 - 30 * 65536)

    def test_icon_resolve_failure_fails_closed(self):
        icon = self.assets / "CL_icon.png"
        plugin_root = self.root / "cleanlanguage"
        for target in (icon, plugin_root):
            for error in (OSError(errno.ELOOP, "Too many levels of symbolic links"),
                          RuntimeError("Symlink loop from " + repr(str(target)))):
                with self.subTest(target=target.name, error=type(error).__name__):
                    with self.resolve_raising(target, error):
                        self.expect_exit(
                            3,
                            "field icon: icon path " + repr("./assets/CL_icon.png")
                            + f" could not be resolved: {error}",
                        )

    def test_repository_root_resolve_failure_fails_closed(self):
        for error in (OSError(errno.EACCES, "Permission denied"), RuntimeError("Symlink loop")):
            with self.subTest(error=type(error).__name__):
                with self.resolve_raising(self.root, error):
                    err = self.expect_exit(3, f"the repository root could not be resolved: {error}")
                self.assertEqual(err, f"check-manifest-icon: the repository root could not be resolved: {error}\n")

    def test_empty_file_fails(self):
        self.set_icon("CL_icon.png", b"")
        self.expect_exit(1, "is empty")

    def test_size_at_limit_fails(self):
        self.set_icon("CL_icon.png", padded_png(gate.MAX_ICON_BYTES))
        self.expect_exit(1, f"is {gate.MAX_ICON_BYTES} bytes; it must be under 2 MB (2000000 bytes)")

    # Signature and extension (I1, I2).

    def test_foreign_signatures_fail(self):
        for data in (b"GIF89a" + bytes(20), b"RIFF\x00\x00\x00\x00WEBPVP8 ",
                     b"<svg xmlns=\"http://www.w3.org/2000/svg\"/>", b"\x89PNG\r\n",
                     b"\xff\xd8\x00" + bytes(20)):
            with self.subTest(data=data[:8]):
                self.set_icon("CL_icon.png", data)
                self.expect_exit(1, "is neither PNG nor JPEG by file signature")

    def test_extension_mismatch_fails(self):
        self.set_icon("CL_icon.png", make_jpeg(512, 512))
        self.expect_exit(1, "has extension " + repr(".png") + ", which does not match its JPEG signature")
        self.set_icon("icon.jpg", make_png(512, 512))
        self.expect_exit(1, "has extension " + repr(".jpg") + ", which does not match its PNG signature")
        self.set_icon("noext", make_png(512, 512))
        self.expect_exit(1, "does not match its PNG signature")

    # PNG structure (I3).

    def test_png_truncated_mid_chunk_fails(self):
        data = make_png(512, 512)
        self.set_icon("CL_icon.png", data[:len(data) - 15])
        self.expect_exit(1, "is truncated")

    def test_png_truncated_chunk_header_fails(self):
        data = make_png(512, 512, with_iend=False) + b"\x00\x00\x00"
        self.set_icon("CL_icon.png", data)
        self.expect_exit(1, "chunk header at offset")

    def test_png_bad_crc_fails(self):
        for chunk_type in (b"IHDR", b"IDAT"):
            with self.subTest(chunk=chunk_type):
                self.set_icon("CL_icon.png", make_png(512, 512, corrupt_crc_of=chunk_type))
                self.expect_exit(1, "bad CRC")

    def test_png_bad_chunk_type_fails(self):
        self.set_icon("CL_icon.png", make_png(512, 512, before_idat=((b"ab1d", b""),)))
        self.expect_exit(1, "is not four ASCII letters")

    def test_png_oversized_chunk_length_fails(self):
        data = make_png(512, 512, with_iend=False) + struct.pack(">I", 2**31) + b"tEXt"
        self.set_icon("CL_icon.png", data)
        self.expect_exit(1, "above 2**31 - 1")

    def test_png_first_chunk_not_ihdr_fails(self):
        self.set_icon("CL_icon.png", make_png(512, 512, first_chunk=(b"CgBI", b"\x50\x00\x20\x06")))
        self.expect_exit(1, "first chunk is " + repr("CgBI") + ", not IHDR")

    def test_png_ihdr_wrong_length_fails(self):
        self.set_icon("CL_icon.png", make_png(512, 512, ihdr_length=12))
        self.expect_exit(1, "IHDR length is 12, not 13")

    def test_png_zero_dimension_fails(self):
        for width, height in ((0, 512), (512, 0), (0, 0)):
            with self.subTest(width=width, height=height):
                self.set_icon("CL_icon.png", make_png(width, height))
                self.expect_image_error("CL_icon.png", "PNG", "width or height is 0")

    def test_png_dimension_above_u31_fails(self):
        for width, height in ((2**31, 2**31), (512, 2**31), (2**31, 512), (2**32 - 1, 512)):
            with self.subTest(width=width, height=height):
                self.set_icon("CL_icon.png", make_png(width, height))
                self.expect_image_error("CL_icon.png", "PNG", "width or height is above 2**31 - 1")

    def test_png_missing_iend_fails(self):
        self.set_icon("CL_icon.png", make_png(512, 512, with_iend=False))
        self.expect_exit(1, "no IEND chunk")

    def test_png_trailing_bytes_fails(self):
        self.set_icon("CL_icon.png", make_png(512, 512, trailing=b"junk"))
        self.expect_exit(1, "4 bytes follow IEND")

    def test_png_no_idat_fails(self):
        self.set_icon("CL_icon.png", make_png(512, 512, with_idat=False))
        self.expect_exit(1, "no IDAT chunk before IEND")

    def test_png_bad_depth_colour_pair_fails(self):
        valid = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
        for colour in range(8):
            for depth in (0, 1, 2, 3, 4, 8, 16, 32):
                if depth in valid.get(colour, set()):
                    continue
                with self.subTest(depth=depth, colour=colour):
                    self.set_icon("CL_icon.png", make_png(512, 512, depth=depth, colour=colour))
                    self.expect_exit(1, f"bit depth {depth} and colour type {colour} are not a valid pair")

    def test_png_valid_depth_colour_pairs_pass(self):
        valid = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
        for colour, depths in valid.items():
            for depth in sorted(depths):
                with self.subTest(depth=depth, colour=colour):
                    extra = ((b"PLTE", bytes(3)),) if colour == 3 else ()
                    self.set_icon("CL_icon.png", make_png(512, 512, depth=depth, colour=colour, before_idat=extra))
                    self.expect_pass()

    def test_png_bad_methods_fail(self):
        for index, needle in ((10, "compression method 1 is not 0"),
                              (11, "filter method 1 is not 0"),
                              (12, "interlace method 2 is not 0 or 1")):
            with self.subTest(needle=needle):
                fields = [512, 512, 8, 6, 0, 0, 0]
                fields[index - 6] = 2 if index == 12 else 1
                ihdr = struct.pack(">IIBBBBB", *fields)
                data = gate.PNG_SIGNATURE + png_chunk(b"IHDR", ihdr)
                data += png_chunk(b"IDAT", zlib.compress(b"")) + png_chunk(b"IEND", b"")
                self.set_icon("CL_icon.png", data)
                self.expect_exit(1, needle)

    def test_png_iend_with_payload_fails(self):
        data = png_from(png_chunk(b"IHDR", ihdr_payload(512, 512)), IDAT, png_chunk(b"IEND", b"hostile"))
        self.set_icon("CL_icon.png", data)
        self.expect_exit(1, "IEND length is 7, not 0")

    def test_png_second_ihdr_fails(self):
        self.set_icon("CL_icon.png", make_png(512, 512, before_idat=((b"IHDR", ihdr_payload(100, 200)),)))
        self.expect_exit(1, "a second IHDR chunk appears at offset 33")

    def test_png_unknown_critical_chunk_fails(self):
        for chunk_type in (b"ZZZZ", b"CgBI", b"Idat"):
            with self.subTest(chunk=chunk_type):
                self.set_icon("CL_icon.png", make_png(512, 512, before_idat=((chunk_type, b""),)))
                self.expect_exit(1, "unknown critical chunk " + repr(chunk_type.decode("ascii")))

    def test_png_critical_set_is_exact(self):
        self.assertEqual(gate.PNG_CRITICAL, frozenset({"IHDR", "PLTE", "IDAT", "IEND"}))

    def test_png_critical_set_governs_the_refusal(self):
        # The unknown-critical refusal reads PNG_CRITICAL: a type dropped from the set
        # is refused as unknown, and a type added to it is no longer refused.
        plte = make_png(512, 512, colour=2, before_idat=((b"PLTE", bytes(3)),))
        for critical, data, chunk_type in (
            (gate.PNG_CRITICAL - {"PLTE"}, plte, "PLTE"),
            (gate.PNG_CRITICAL - {"IDAT"}, make_png(512, 512), "IDAT"),
            (frozenset(), make_png(512, 512), "IHDR"),
        ):
            with self.subTest(chunk=chunk_type):
                self.set_icon("CL_icon.png", data)
                with mock.patch.object(gate, "PNG_CRITICAL", critical):
                    self.expect_exit(1, "unknown critical chunk " + repr(chunk_type))
        self.set_icon("CL_icon.png", make_png(512, 512, before_idat=((b"ZZZZ", b""),)))
        self.expect_exit(1, "unknown critical chunk " + repr("ZZZZ"))
        with mock.patch.object(gate, "PNG_CRITICAL", gate.PNG_CRITICAL | {"ZZZZ"}):
            self.expect_pass()

    def test_png_palette_without_plte_fails(self):
        self.set_icon("CL_icon.png", make_png(512, 512, colour=3))
        self.expect_exit(1, "colour type 3 has no PLTE chunk before IDAT")

    def test_png_valid_palettes_pass(self):
        for depth, colour, entries in ((8, 3, 256), (1, 3, 2), (8, 2, 16), (8, 6, 1)):
            with self.subTest(depth=depth, colour=colour, entries=entries):
                plte = ((b"PLTE", bytes(3 * entries)),)
                self.set_icon("CL_icon.png", make_png(512, 512, depth=depth, colour=colour, before_idat=plte))
                self.expect_pass()

    def test_png_plte_rules_fail(self):
        ihdr3 = png_chunk(b"IHDR", ihdr_payload(512, 512, colour=3))
        ihdr2 = png_chunk(b"IHDR", ihdr_payload(512, 512, colour=2))
        plte = png_chunk(b"PLTE", bytes(3))
        cases = (
            (make_png(512, 512, colour=0, before_idat=((b"PLTE", bytes(3)),)),
             "colour type 0 must not carry a PLTE chunk"),
            (make_png(512, 512, colour=4, before_idat=((b"PLTE", bytes(3)),)),
             "colour type 4 must not carry a PLTE chunk"),
            (make_png(512, 512, colour=3, before_idat=((b"PLTE", bytes(4)),)),
             "PLTE length 4 is not a multiple of 3 from 3 to 768"),
            (make_png(512, 512, colour=3, before_idat=((b"PLTE", b""),)),
             "PLTE length 0 is not a multiple of 3 from 3 to 768"),
            (make_png(512, 512, colour=3, before_idat=((b"PLTE", bytes(771)),)),
             "PLTE length 771 is not a multiple of 3 from 3 to 768"),
            (make_png(512, 512, depth=1, colour=3, before_idat=((b"PLTE", bytes(9)),)),
             "PLTE has 3 entries, more than bit depth 1 can index"),
            (png_from(ihdr3, plte, plte, IDAT, IEND), "a second PLTE chunk appears"),
            (png_from(ihdr2, IDAT, plte, IEND), "follows IDAT"),
        )
        for data, needle in cases:
            with self.subTest(needle=needle):
                self.set_icon("CL_icon.png", data)
                self.expect_exit(1, needle)

    def test_png_idat_not_consecutive_fails(self):
        ihdr = png_chunk(b"IHDR", ihdr_payload(512, 512))
        data = png_from(ihdr, IDAT, png_chunk(b"tEXt", b"a\x00b"), IDAT, IEND)
        self.set_icon("CL_icon.png", data)
        self.expect_exit(1, "is not consecutive with the earlier IDAT")

    def test_png_consecutive_idat_pass(self):
        ihdr = png_chunk(b"IHDR", ihdr_payload(512, 512))
        self.set_icon("CL_icon.png", png_from(ihdr, IDAT, IDAT, IDAT, IEND))
        self.expect_pass()

    # JPEG structure (I4).

    def test_jpeg_sos_before_sof_fails(self):
        pre = (jpeg_segment(0xDA, bytes([1, 1, 0, 0, 63, 0])),)
        self.set_icon("icon.jpg", make_jpeg(512, 512, pre=pre))
        self.expect_exit(1, "scan data (SOS) begins before any frame header")

    def test_jpeg_truncated_segment_fails(self):
        self.set_icon("icon.jpg", b"\xff\xd8\xff\xdb\x00\x50" + bytes(10))
        self.expect_exit(1, "segment at offset 2 is truncated")

    def test_jpeg_truncated_length_fails(self):
        self.set_icon("icon.jpg", b"\xff\xd8\xff\xdb\x00")
        self.expect_exit(1, "segment at offset 2 is truncated")

    def test_jpeg_segment_length_below_two_fails(self):
        self.set_icon("icon.jpg", b"\xff\xd8\xff\xdb\x00\x01" + make_jpeg(512, 512)[2:])
        self.expect_exit(1, "segment length 1 at offset 2 is below 2")

    def test_jpeg_dnl_height_zero_fails(self):
        self.set_icon("icon.jpg", make_jpeg(512, 0))
        self.expect_exit(1, "height 0 (DNL)")

    def test_jpeg_width_zero_fails(self):
        self.set_icon("icon.jpg", make_jpeg(0, 512))
        self.expect_exit(1, "frame header declares width 0")

    def test_jpeg_zero_components_fails(self):
        self.set_icon("icon.jpg", make_jpeg(512, 512, components=0))
        self.expect_exit(1, "frame header declares 0 components")

    def test_jpeg_short_frame_header_fails(self):
        short = jpeg_segment(0xC0, struct.pack(">BHHB", 8, 512, 512, 3) + bytes(3))
        self.set_icon("icon.jpg", b"\xff\xd8" + short + b"\xff\xd9")
        self.expect_image_error("icon.jpg", "JPEG", "frame header at offset 2 is too short for 3 components")
        short = jpeg_segment(0xC0, struct.pack(">BHHB", 8, 512, 512, 3) + bytes(7))
        self.set_icon("icon.jpg", b"\xff\xd8" + short + b"\xff\xd9")
        self.expect_image_error("icon.jpg", "JPEG", "frame header at offset 2 is too short for 3 components")
        # A frame header shorter than its fixed fields, followed by more bytes or at
        # the end of the file, is refused by the length check with a gate message.
        for data in (b"\xff\xd8" + jpeg_segment(0xC0, bytes(4)) + b"\xff\xd9",
                     b"\xff\xd8" + jpeg_segment(0xC0, bytes(4)),
                     b"\xff\xd8" + jpeg_segment(0xC0, bytes(5)),
                     b"\xff\xd8" + jpeg_segment(0xC2, b"")):
            with self.subTest(data=data):
                self.set_icon("icon.jpg", data)
                self.expect_image_error("icon.jpg", "JPEG", "frame header at offset 2 is too short")

    def test_bounded_readers_refuse_reads_past_their_structure(self):
        # I7: the second layer under every length check in both parsers.
        data = bytes(range(10))
        self.assertEqual(gate.read_struct(">H", data, 8, 10), (0x0809,))
        self.assertEqual(gate.read_struct(">BHHB", data, 0, 6), (0, 0x0102, 0x0304, 5))
        self.assertEqual(gate.read_byte(data, 9, 10), 9)
        self.assertEqual(gate.read_byte(data, 0, 1), 0)
        for start, limit in ((9, 10), (4, 5), (9, 20), (-1, 10), (-2, 10), (10, 30)):
            with self.subTest(reader="read_struct", start=start, limit=limit):
                with self.assertRaises(gate.ImageError) as caught:
                    gate.read_struct(">H", data, start, limit)
                self.assertEqual(
                    str(caught.exception), f"a 2-byte field at offset {start} reads past the end of its structure"
                )
        for index, limit in ((10, 10), (5, 5), (10, 20), (-1, 10), (0, 0)):
            with self.subTest(reader="read_byte", index=index, limit=limit):
                with self.assertRaises(gate.ImageError) as caught:
                    gate.read_byte(data, index, limit)
                self.assertEqual(str(caught.exception), f"the byte at offset {index} lies past the end of its structure")

    def test_jpeg_garbage_after_soi_fails(self):
        self.set_icon("icon.jpg", b"\xff\xd8\xff\x01\x41\x42" + bytes(20))
        self.expect_exit(1, "byte at offset 4 is not a marker prefix")

    def test_jpeg_marker_zero_fails(self):
        self.set_icon("icon.jpg", b"\xff\xd8\xff\x00" + bytes(20))
        self.expect_exit(1, "marker 0x00 at offset 2 is not valid")

    def test_jpeg_second_soi_fails(self):
        self.set_icon("icon.jpg", b"\xff\xd8" + make_jpeg(512, 512))
        self.expect_exit(1, "a second SOI appears before the frame header")

    def test_jpeg_eoi_before_sof_fails(self):
        self.set_icon("icon.jpg", b"\xff\xd8\xff\xd9")
        self.expect_exit(1, "EOI reached before any frame header")

    def test_jpeg_ends_before_frame_header_fails(self):
        for data in (b"\xff\xd8" + jpeg_segment(0xE0, b"JFIF\x00"), b"\xff\xd8\xff\xff"):
            with self.subTest(data=data):
                self.set_icon("icon.jpg", data)
                self.expect_exit(1, "file ends before any frame header")

    def test_jpeg_dht_not_mistaken_for_sof(self):
        dht = jpeg_segment(0xC4, frame_payload(512, 512))
        self.set_icon("icon.jpg", make_jpeg(300, 300, pre=(dht,)))
        self.expect_exit(1, "300 x 300 pixels; each side must be 512 to 2048")

    def test_jpeg_non_frame_markers_skipped(self):
        for marker in (0xC8, 0xCC):
            with self.subTest(marker=marker):
                decoy = jpeg_segment(marker, frame_payload(512, 512))
                self.set_icon("icon.jpg", make_jpeg(300, 300, pre=(decoy,)))
                self.expect_exit(1, "300 x 300 pixels")

    def test_jpeg_supported_frame_markers_accepted(self):
        for marker in (0xC0, 0xC1, 0xC2):
            with self.subTest(marker=hex(marker)):
                self.set_icon("icon.jpg", make_jpeg(512, 512, sof=marker))
                self.expect_pass()

    def test_jpeg_unsupported_processes_refused_by_name(self):
        # Repository policy: only SOF0, SOF1 and SOF2, the processes web clients are
        # expected to render, are accepted; every other frame marker is refused by name.
        names = {
            0xC3: "SOF3, lossless",
            0xC5: "SOF5, differential sequential",
            0xC6: "SOF6, differential progressive",
            0xC7: "SOF7, differential lossless",
            0xC9: "SOF9, extended sequential, arithmetic coding",
            0xCA: "SOF10, progressive, arithmetic coding",
            0xCB: "SOF11, lossless, arithmetic coding",
            0xCD: "SOF13, differential sequential, arithmetic coding",
            0xCE: "SOF14, differential progressive, arithmetic coding",
            0xCF: "SOF15, differential lossless, arithmetic coding",
        }
        frame = jpeg_segment(0xC0, frame_payload(512, 512))
        for marker, name in names.items():
            for label, data, offset in (
                ("first", make_jpeg(512, 512, sof=marker), 2),
                ("selectors 4 and 5", table_jpeg(marker, (0x45, 0x55, 0x55)), 2),
                ("truncated", SOI + bytes([0xFF, marker]), 2),
                ("after SOF0", SOI + frame + jpeg_segment(marker, frame_payload(512, 512)) + SOS, 21),
            ):
                with self.subTest(marker=hex(marker), case=label):
                    self.set_icon("icon.jpg", data)
                    self.expect_image_error(
                        "icon.jpg", "JPEG",
                        f"frame marker 0x{marker:02X} at offset {offset} ({name}) is an unsupported "
                        "JPEG process; only SOF0, SOF1, and SOF2 are accepted",
                    )

    def test_jpeg_frame_marker_set_is_exact(self):
        self.assertEqual(set(gate.SOF_MARKERS), {0xC0, 0xC1, 0xC2})
        self.assertEqual(set(gate.UNSUPPORTED_SOF), {0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF})

    def test_jpeg_ends_after_frame_header_fails(self):
        frame = jpeg_segment(0xC0, frame_payload(512, 512))
        for data in (SOI + frame, SOI + frame + jpeg_segment(0xC4, bytes(21)),
                     make_jpeg(512, 512, with_sos=False, with_eoi=False), SOI + frame + b"\xff"):
            with self.subTest(size=len(data)):
                self.set_icon("icon.jpg", data)
                self.expect_exit(1, "file ends before any scan (SOS)")

    def test_jpeg_eoi_before_sos_fails(self):
        self.set_icon("icon.jpg", make_jpeg(512, 512, with_sos=False))
        self.expect_exit(1, "EOI reached before any scan (SOS)")

    def test_jpeg_invalid_precision_fails(self):
        for marker, precision in ((0xC0, 0), (0xC0, 12), (0xC0, 16), (0xC1, 0), (0xC1, 16),
                                  (0xC2, 0), (0xC2, 16), (0xC2, 255)):
            with self.subTest(marker=hex(marker), precision=precision):
                self.set_icon("icon.jpg", make_jpeg(512, 512, sof=marker, precision=precision))
                self.expect_exit(
                    1, f"sample precision {precision} is not valid for frame marker 0x{marker:02X}"
                )

    def test_jpeg_minimal_frame_with_zero_precision_fails(self):
        data = SOI + jpeg_segment(0xC0, struct.pack(">BHHB", 0, 512, 512, 1) + bytes([1, 0x11, 0]))
        self.assertEqual(len(data), 15)
        self.set_icon("icon.jpg", data)
        self.expect_exit(1, "sample precision 0 is not valid for frame marker 0xC0")

    def test_jpeg_valid_precisions_pass(self):
        for marker, precision in ((0xC0, 8), (0xC1, 8), (0xC1, 12), (0xC2, 8), (0xC2, 12)):
            with self.subTest(marker=hex(marker), precision=precision):
                self.set_icon("icon.jpg", make_jpeg(512, 512, sof=marker, precision=precision))
                self.expect_pass()

    def test_jpeg_second_frame_header_fails(self):
        frame = jpeg_segment(0xC0, frame_payload(512, 512))
        self.set_icon("icon.jpg", SOI + frame + frame + SOS + b"\xff\xd9")
        self.expect_exit(1, "a second frame header at offset 21 appears before the first scan (SOS)")

    def test_jpeg_markers_after_frame_header_fail(self):
        frame = jpeg_segment(0xC0, frame_payload(512, 512))
        for tail, needle in (
            (b"\xff\xd8" + SOS, "a second SOI appears before the first scan (SOS)"),
            (b"\xff\x00" + SOS, "marker 0x00 at offset 21 is not valid before the first scan (SOS)"),
            (b"\x41" + SOS, "byte at offset 21 is not a marker prefix"),
        ):
            with self.subTest(needle=needle):
                self.set_icon("icon.jpg", SOI + frame + tail)
                self.expect_exit(1, needle)

    def test_jpeg_duplicate_frame_identifiers_fail(self):
        frame = jpeg_segment(0xC0, frame_payload(512, 512, identifiers=(1, 1, 2)))
        self.set_icon("icon.jpg", SOI + frame + SOS + b"\xff\xd9")
        self.expect_exit(1, "frame header declares a component identifier twice")

    def test_jpeg_bad_scan_header_fails(self):
        frame = jpeg_segment(0xC0, frame_payload(512, 512))
        for scan, needle in (
            (jpeg_segment(0xDA, b""), "scan header at offset 21 is too short"),
            (jpeg_segment(0xDA, bytes([1])), "scan header at offset 21 has length 3, not 8 for 1 components"),
            (jpeg_segment(0xDA, bytes([0, 0, 63, 0])), "scan header declares 0 components, not 1 to 4"),
            (jpeg_segment(0xDA, bytes([5] + [1, 0] * 5 + [0, 63, 0])),
             "scan header declares 5 components, not 1 to 4"),
            (jpeg_segment(0xDA, bytes([1, 1, 0, 0, 63, 0, 0])),
             "scan header at offset 21 has length 9, not 8 for 1 components"),
            (jpeg_segment(0xDA, bytes([1, 9, 0, 0, 63, 0])),
             "scan header names component 9, which the frame header does not declare"),
            (jpeg_segment(0xDA, bytes([2, 1, 0, 1, 0, 0, 63, 0])), "scan header names a component twice"),
        ):
            with self.subTest(needle=needle):
                self.set_icon("icon.jpg", SOI + frame + scan + b"\x00\xff\xd9")
                self.expect_exit(1, needle)

    def test_jpeg_scan_table_selectors_out_of_range_fail(self):
        # ITU-T T.81 Table B.3: SOF0 0 to 1; SOF1 and SOF2 0 to 3.
        for sof, tables, component, dc, ac, dc_max, ac_max in (
            (0xC0, (0x20,), 1, 2, 0, 1, 1),
            (0xC0, (0x02,), 1, 0, 2, 1, 1),
            (0xC0, (0xFF,), 1, 15, 15, 1, 1),
            (0xC0, (0x00, 0x11, 0x12), 3, 1, 2, 1, 1),
            (0xC1, (0x40,), 1, 4, 0, 3, 3),
            (0xC1, (0x04,), 1, 0, 4, 3, 3),
            (0xC2, (0x04,), 1, 0, 4, 3, 3),
            (0xC2, (0x33, 0x44), 2, 4, 4, 3, 3),
            (0xC2, (0x40,), 1, 4, 0, 3, 3),
        ):
            with self.subTest(sof=hex(sof), tables=tables):
                self.set_icon("icon.jpg", table_jpeg(sof, tables))
                self.expect_exit(
                    1,
                    f"scan header gives component {component} DC table {dc} and AC table "
                    f"{ac}; frame marker 0x{sof:02X} allows DC 0 to {dc_max} and AC 0 to {ac_max}",
                )

    def test_jpeg_scan_table_selectors_in_range_pass(self):
        for sof, tables in (
            (0xC0, (0x00, 0x11, 0x11)),
            (0xC0, (0x10, 0x01)),
            (0xC1, (0x33,)),
            (0xC1, (0x30, 0x03)),
            (0xC2, (0x30, 0x03)),
            (0xC2, (0x33, 0x22, 0x11)),
        ):
            with self.subTest(sof=hex(sof), tables=tables):
                self.set_icon("icon.jpg", table_jpeg(sof, tables))
                self.expect_pass()

    def test_jpeg_scan_table_selector_limits_are_exact(self):
        self.assertEqual(gate.SOS_TABLE_SELECTORS, {0xC0: (1, 1), 0xC1: (3, 3), 0xC2: (3, 3)})
        self.assertEqual(
            gate.SOF_PRECISIONS,
            {0xC0: frozenset({8}), 0xC1: frozenset({8, 12}), 0xC2: frozenset({8, 12})},
        )

    def test_jpeg_segments_between_frame_and_scan_are_skipped(self):
        frame = jpeg_segment(0xC0, frame_payload(512, 512))
        between = (
            jpeg_segment(0xC4, b"\x00\xff\xc0\x00\x11\x08\x00\x64\x00\x64\xff\xda" + bytes(9)),
            jpeg_segment(0xDB, bytes(65)),
            jpeg_segment(0xDD, b"\x00\x10"),
            jpeg_segment(0xFE, b"comment \xff\xd9"),
            b"\xff\xff",
        )
        scan = jpeg_segment(0xDA, bytes([3, 1, 0, 2, 0x11, 3, 0x11, 0, 63, 0]))
        self.set_icon("icon.jpg", SOI + frame + b"".join(between) + scan + b"\x12\x34\xff\xd9")
        self.assertIn("is a JPEG of 512 x 512 pixels", self.expect_pass())

    def test_jpeg_walk_stops_at_the_first_scan_header(self):
        # Residual 1: nothing after the first scan header is read.
        frame = jpeg_segment(0xC0, frame_payload(512, 512))
        for tail in (b"", b"\xff\xd8 not entropy data", b"\x00" * 7):
            with self.subTest(tail=tail):
                self.set_icon("icon.jpg", SOI + frame + SOS + tail)
                self.expect_pass()

    # Geometry (I5) and message shape.

    def test_not_square_fails(self):
        self.set_icon("CL_icon.png", make_png(512, 513))
        self.expect_exit(1, "512 x 513 pixels; it must be square")
        self.set_icon("icon.jpg", make_jpeg(600, 512))
        self.expect_exit(1, "600 x 512 pixels; it must be square")

    def test_too_small_fails(self):
        self.set_icon("CL_icon.png", make_png(511, 511))
        self.expect_exit(1, "each side must be 512 to 2048")

    def test_too_large_fails(self):
        self.set_icon("CL_icon.png", make_png(2049, 2049))
        self.expect_exit(1, "each side must be 512 to 2048")

    def test_message_names_manifest_and_field(self):
        self.set_icon("CL_icon.png", make_png(511, 511))
        err = self.expect_exit(1, "each side must be 512 to 2048")
        self.assertTrue(err.startswith(f"check-manifest-icon: {CLAUDE} field icon: "), err)


if __name__ == "__main__":
    unittest.main()
