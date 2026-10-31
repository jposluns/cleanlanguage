#!/usr/bin/env python3
"""Tests for check-manifest-icon.py.

Patch the gate repository root and manifest set to a temporary fixture holding all
five manifests and a generated icon, and drive the failure and success paths
offline with the standard library. Every image fixture is built at run time; no
binary fixture file is tracked. OSError paths are driven by unittest.mock, not by
chmod.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import struct
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


def png_chunk(chunk_type: bytes, payload: bytes, corrupt: bool = False) -> bytes:
    crc = zlib.crc32(chunk_type + payload)
    if corrupt:
        crc ^= 1
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)


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
    ihdr = struct.pack(">IIBBBBB", width, height, depth, colour, 0, 0, interlace)
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


def frame_payload(width, height, components=3) -> bytes:
    table = b"".join(bytes([index + 1, 0x11, 0]) for index in range(components))
    return struct.pack(">BHHB", 8, height, width, components) + table


def make_jpeg(width, height, sof=0xC0, pre=(), components=3, fill=b"", with_sos=True, with_eoi=True):
    """SOI, pre-segments (raw bytes), fill bytes, a frame header, a minimal SOS, EOI."""
    out = b"\xff\xd8" + b"".join(pre) + fill + jpeg_segment(sof, frame_payload(width, height, components))
    if with_sos:
        out += jpeg_segment(0xDA, bytes([1, 1, 0, 0, 63, 0])) + b"\x00\x01\x02"
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

    def expect_pass(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(gate.main(), 0)
        return out.getvalue()

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
        pre = (jpeg_segment(0xE0, b"JFIF\x00"), b"\xff\xff\xff\xd0", b"\xff\x01")
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
        self.write_json(MARKET, {"name": "m", "plugins": [{"name": "a"}, "s", {"icon": "./x.png"}]})
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
                      "./assets/CL\nicon.png", "./assets/CL\ud800icon.png"):
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

    def test_plugin_root_resolving_outside_repository_fails(self):
        with tempfile.TemporaryDirectory() as outside:
            moved = Path(outside) / "cleanlanguage"
            shutil.move(str(self.root / "cleanlanguage"), str(moved))
            os.symlink(moved, self.root / "cleanlanguage")
            self.expect_exit(1, "resolves outside the repository")

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
                    calls.append(Path(path))
                    return real_open(path, *args, **kwargs)

                self.set_icon_value(f"./assets/{name}")
                with mock.patch.object(gate.os, "open", side_effect=spy):
                    self.expect_exit(1, "is not a regular file")
                self.assertEqual(calls, [])

    def test_fstat_non_regular_fails(self):
        fifo_mode = os.stat_result((0o010644, 0, 0, 1, 0, 0, 100, 0, 0, 0))
        with mock.patch.object(gate.os, "fstat", return_value=fifo_mode):
            self.expect_exit(1, "is not a regular file")

    def test_fstat_oserror_fails_closed(self):
        with mock.patch.object(gate.os, "fstat", side_effect=OSError(5, "Input/output error")):
            self.expect_exit(3, "could not be read")

    def test_icon_component_not_directory_fails(self):
        self.set_icon_value("./assets/CL_icon.png/inner.png")
        self.expect_exit(1, "is not a regular file")

    def test_icon_open_oserror_fails_closed(self):
        with mock.patch.object(gate.os, "open", side_effect=PermissionError(13, "Permission denied")):
            self.expect_exit(3, "could not be read")

    def test_icon_read_oserror_fails_closed(self):
        with mock.patch.object(gate.os, "read", side_effect=OSError(5, "Input/output error")):
            self.expect_exit(3, "could not be read")

    def test_icon_lstat_oserror_fails_closed(self):
        real_lstat = os.lstat

        def fake_lstat(path, *args, **kwargs):
            if Path(path).name == "CL_icon.png":
                raise PermissionError(13, "Permission denied", str(path))
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(gate.os, "lstat", side_effect=fake_lstat):
            self.expect_exit(3, "could not be inspected")

    def test_file_changed_during_read_fails_closed(self):
        with mock.patch.object(gate.os, "read", return_value=b""):
            self.expect_exit(3, "changed while it was read")

    def test_empty_file_fails(self):
        self.set_icon("CL_icon.png", b"")
        self.expect_exit(1, "is empty")

    def test_size_at_limit_fails(self):
        self.set_icon("CL_icon.png", padded_png(gate.MAX_ICON_BYTES))
        self.expect_exit(1, f"is {gate.MAX_ICON_BYTES} bytes; it must be under 2 MB (2000000 bytes)")

    # Signature and extension (I1, I2).

    def test_foreign_signatures_fail(self):
        for data in (b"GIF89a" + bytes(20), b"RIFF\x00\x00\x00\x00WEBPVP8 ",
                     b"<svg xmlns=\"http://www.w3.org/2000/svg\"/>", b"\x89PNG\r\n"):
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

    def test_png_zero_width_fails(self):
        self.set_icon("CL_icon.png", make_png(0, 512))
        self.expect_exit(1, "width or height is 0")

    def test_png_dimension_above_u31_fails(self):
        self.set_icon("CL_icon.png", make_png(2**31, 2**31))
        self.expect_exit(1, "width or height is above 2**31 - 1")

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
        for depth, colour in ((8, 1), (16, 3), (4, 6), (2, 2)):
            with self.subTest(depth=depth, colour=colour):
                self.set_icon("CL_icon.png", make_png(512, 512, depth=depth, colour=colour))
                self.expect_exit(1, f"bit depth {depth} and colour type {colour} are not a valid pair")

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
        self.expect_exit(1, "is too short for 3 components")
        self.set_icon("icon.jpg", b"\xff\xd8" + jpeg_segment(0xC0, bytes(4)) + b"\xff\xd9")
        self.expect_exit(1, "frame header at offset 2 is too short")

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

    def test_jpeg_every_frame_marker_accepted(self):
        for marker in sorted(gate.SOF_MARKERS):
            with self.subTest(marker=hex(marker)):
                self.set_icon("icon.jpg", make_jpeg(512, 512, sof=marker))
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
