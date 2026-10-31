#!/usr/bin/env python3
"""Validate every plugin manifest icon field against the repository icon floor.

A Claude plugin manifest may carry an "icon" field naming an image file relative to
the plugin root. The pinned CLI validator (plugin-validate.yml) is the authority on
what Claude Code accepts; this gate is the repository floor beneath it, offline,
standard library only, and fail-closed: an icon field that names a missing,
unreadable, unparseable, or out-of-bounds image is a failure, never a silent skip.

What it checks:
  M1  every file named plugin.json or marketplace.json in the repository tree (the
      top-level .git directory is pruned) is declared in MANIFESTS, so a new
      manifest cannot carry an icon past the gate unseen; a tree that cannot be
      listed fails closed;
  M2  every declared manifest is reached from the repository root with os.lstat on
      each path component: no component is a symlink, every component before the
      manifest is a directory, and the manifest is a regular file; it is opened
      with O_NOFOLLOW and O_NONBLOCK, re-checked as a regular file through fstat,
      and loads, unconditionally (no presence test), as a JSON object; a declared
      manifest that is absent or unreadable fails closed;
  M3  the icon fields examined are the top-level "icon" key of each manifest and the
      "icon" key of each object in a top-level "plugins" array (plugins[i].icon); an
      icon in a marketplace manifest is refused, because the directory its path
      resolves against is unverified;
  M4  each manifest in REQUIRED_ICON_MANIFESTS declares a top-level icon (the
      maintainer decision of 2026-10-31 to keep the published plugin icon), each
      such manifest is itself declared in MANIFESTS, and a run that checks no icon
      field at all fails as vacuous;
  P1  the icon value is a string with non-whitespace content;
  P2  it holds no control character (below 0x20, or 0x7F), no NUL, no surrogate, and
      no backslash;
  P3  it is a canonical "./" relative path: every component after the "./" prefix is
      non-empty and neither "." nor "..", with no trailing slash, so an absolute or
      traversing path is refused before any filesystem call;
  F1  each path component, walked with os.lstat from the repository root through
      the plugin root (the plugin root itself included) and on to the icon file,
      exists and is not a symlink, and every component before the icon file is a
      directory;
  F2  the final component is a regular file;
  F3  backstop: the resolved icon path lies inside both the plugin root and the
      repository;
  F4  the file is opened with O_NOFOLLOW (so a final component swapped for a symlink
      after the walk is refused with ELOOP) and O_NONBLOCK (so a FIFO swapped in
      cannot stall the open), re-checked as a regular file through fstat, and read
      in full up to MAX_ICON_BYTES + 1 bytes; a file whose length changes between
      fstat and the read fails closed;
  F5  the file is not empty and its size is strictly below MAX_ICON_BYTES, checked
      before any parse;
  I1  the format is decided by the file signature alone, PNG or JPEG;
  I3  a PNG is walked chunk by chunk without decompression: IHDR first with length
      13 and never repeated; every chunk complete with a valid CRC, a four-letter
      ASCII type, and a length at most 2**31 - 1; a valid bit depth and colour type
      pair, compression 0, filter 0, interlace 0 or 1; a critical chunk (upper-case
      first letter) whose type is not in PNG_CRITICAL (IHDR, PLTE, IDAT, IEND) is
      refused; PLTE appears at most once, before the first IDAT, never for colour
      types 0 and 4, with a length that is a multiple of 3 from 3 to 768 and, for
      colour type 3, no more entries than the bit depth can index; colour type 3
      has a PLTE before its first IDAT; at least one IDAT precedes IEND and the
      IDAT chunks are consecutive; IEND has an empty payload and no byte follows
      it; every ancillary chunk (lower-case first letter), public or private, is
      skipped by its length and never interpreted;
  I4  a JPEG is walked marker by marker from the SOI to the first scan header (SOS):
      fill bytes and standalone markers (TEM, RST0 to RST7) are skipped, every other
      segment is skipped by its length, and exactly one frame header must precede
      the first SOS and supplies the dimensions; the frame header is SOF0, SOF1, or
      SOF2 (the repository policy below), every other frame marker (SOF3, SOF5 to
      SOF7, SOF9 to SOF11, SOF13 to SOF15) is refused by name as an unsupported
      JPEG process wherever it appears before the first SOS, and DHT, JPG, and DAC
      are never frame headers; the frame header declares at least 1 component with
      distinct identifiers, a component table that fits its length, a sample
      precision valid for its frame marker (ITU-T T.81 Table B.2: 8 for SOF0; 8 or
      12 for SOF1 and SOF2), and a non-zero height (a DNL height is refused) and
      width; the scan header declares 1 to 4 components, has length exactly
      6 + 2 * Ns, names each component once and only components the frame header
      declares, and gives each component a DC and an AC Huffman table selector
      within the range its frame marker allows (ITU-T T.81 Table B.3,
      SOS_TABLE_SELECTORS: 0 to 1 each for SOF0; 0 to 3 each for SOF1 and SOF2);
      an SOS before the frame header, a second frame header, a second SOI, an EOI,
      a marker 0x00, a non-marker byte, a truncated segment, a length below 2, or
      a file that ends before the first SOS is refused; the walk stops at the end
      of the first scan header;
  I5  the image is square, each side 512 to 2048 pixels inclusive;
  I6  each conforming icon field prints one success line to stdout;
  I7  every fixed-width field and every single byte that parse_png and parse_jpeg
      read goes through a bounds-checked reader (read_struct, read_byte) that
      refuses, as an image error, a read past the end of its chunk or segment or
      past the end of the file, so a malformed image is refused with a gate
      message even where an earlier length check is missing, never by an uncaught
      struct.error or IndexError.

Repository-policy checks (taken from the row 64 brief and plan, not from a verified
Claude Code specification, so labelled as such):
  P3  the "./" prefix and the canonical-path form;
  I2  the lower-cased file extension is consistent with the signature (.png for a
      PNG; .jpg or .jpeg for a JPEG); the signature decides the format and the
      extension never does, but a JPEG named .png is refused;
  I4  the accepted JPEG processes: only SOF0 (baseline), SOF1 (extended
      sequential, Huffman coding), and SOF2 (progressive, Huffman coding). The
      policy accepts only the processes that web clients are expected to render:
      an arithmetic-coded, lossless, or differential (hierarchical) frame can
      decode in a reference decoder and still fail to render in a client, so it
      is refused by name rather than passed. This is an orchestrator policy
      decision of row 64, not a verified Claude Code specification, and the JPEG
      support of particular clients was not verified in this change;
  F5  the 2 MB limit is read as 2,000,000 bytes, strictly below; a 2 MiB
      (2,097,152-byte) reading would accept files the decimal reading refuses, so
      the stricter decimal reading is used while the CLI limit is unverified;
  I5  the square shape and the 512 to 2048 side bounds;
  M4  the required icon on cleanlanguage/.claude-plugin/plugin.json.

The base directory of an icon path is the plugin root: the grandparent of a manifest
inside a .claude-plugin directory, otherwise the directory holding the manifest.
Manifest reads decode utf-8-sig, so a leading UTF-8 byte-order mark does not falsely
reject a conforming manifest, and reject the non-standard JSON constants NaN and
Infinity. Filesystem inspection uses os.lstat mode bits rather than the Path
predicates, which suppress OSErrors on some Python versions and would turn an
inspection failure into a silent skip. REPO_ROOT is the trust anchor: it is derived
from the resolved path of this file, so it holds no symlink, and the walks start
below it. O_NOFOLLOW, O_NONBLOCK, and O_CLOEXEC are POSIX flags; the gate targets
the Linux CI runner.

Residuals this gate does not cover:
  1. Header validity is not image validity. The walks check only what I3 and I4
     state. The list below is the closed set of what they leave unchecked: every
     field the code reads but does not validate, every byte it skips, and every
     structure after the point where a walk stops, derived from each byte offset
     parse_png and parse_jpeg read.
     PNG (the walk reads every chunk header and CRC from the signature to IEND
     and refuses any byte after IEND, so no structure lies beyond it):
       a. chunk type letters 2 to 4: the private bit (letter 2), the reserved bit
          (letter 3, which the specification requires to be upper case), and the
          safe-to-copy bit (letter 4) are not interpreted; only letter 1 is;
       b. PLTE: only its length is read; the palette entries are not;
       c. IDAT: the payload is never read or decompressed, so the zlib header, the
          deflate stream, the Adler-32 checksum, the filter byte of each scanline,
          and the decompressed length are unchecked, a zero-length IDAT passes,
          and for colour type 3 a pixel index beyond the palette is unchecked;
       d. ancillary chunks (lower-case first letter), public or private: the
          walk checks only that the type is four ASCII letters, that the length
          is at most 2**31 - 1 and fits in the file, that the CRC matches, that
          the chunk lies after IHDR and before IEND, and that no chunk lies
          between two IDAT chunks. No other rule on an ancillary chunk is
          checked: not its payload, its length against any other field, its
          position within that span apart from the IDAT run, its multiplicity,
          or any relation to IHDR, PLTE or another chunk (for example a tRNS
          before PLTE or for colour type 4 or 6, a tRNS or hIST whose length
          does not match the PLTE entry count, or a hIST with no PLTE), so APNG
          frame chunks pass unread.
     JPEG (the walk stops at the end of the first scan header):
       e. segments skipped by their length with the payload unread: APP0 to APP15,
          COM, DQT, DHT, DAC, DRI, DNL, DHP, EXP, JPG (0xC8), JPG0 to JPG13 (0xF0
          to 0xFD), and the reserved markers 0x02 to 0xBF, which the walk treats as
          length segments; a skipped segment of length 2 passes; no segment is
          required, so a JPEG with no DQT or DHT passes;
       f. marker placement: a DNL, DHP, or EXP before the first scan, and a
          standalone TEM or RST0 to RST7 marker before the first scan, are
          accepted; the hierarchical structure is not checked: a DHP segment is
          skipped, so a hierarchical image whose first frame header is SOF0,
          SOF1, or SOF2 passes with its dimensions read from that first frame
          header, not from the DHP segment, and its differential frames lie
          after the first scan header, unread (item i);
       g. frame header: the sampling factors byte and the quantization table
          selector byte of each component, every byte after the component table
          within the segment length, and the component count limit of a process
          (at most 4 for a progressive frame) are not checked;
       h. scan header: the spectral selection start and end (Ss, Se) and the
          successive approximation byte (Ah, Al) are not read; whether the scan
          components follow the frame header order, whether an interleaved scan
          stays within 10 blocks per MCU, and whether the quantization and
          Huffman tables that the frame and scan select were defined are not
          checked; the table selectors are checked for range only;
       i. everything after the end of the first scan header: the entropy-coded
          data, the RST markers within it, any later scans and the segments
          between them, a DNL after the first scan, the EOI marker, and any bytes
          after EOI, so a JPEG truncated or corrupted anywhere after its first
          scan header passes.
  2. Renderability is not checked beyond the accepted JPEG processes: 12-bit
     JPEGs (SOF1 or SOF2 at precision 12), a hierarchical JPEG whose first frame
     header is SOF0, SOF1, or SOF2 (item 1f), CMYK or Adobe APP14-transformed
     JPEGs, 16-bit and palette PNGs, and APNG pass the header checks, though some
     renderers cannot show them. A multi-picture (MPO) file reports its first
     frame. EXIF orientation is ignored; a rotation preserves squareness and side
     length, so it cannot turn a passing icon into a failing one.
  3. Symlink races and hard links: the lstat walks refuse a symlink on every path
     component from below the repository root to the manifest and to the icon, and
     O_NOFOLLOW closes the race on the final component of both; a directory
     component swapped for a symlink between a walk and its open remains, bounded
     for an icon by the resolve backstop and for both by CI running on a fresh
     checkout. A hard link is indistinguishable from a regular file, so an icon
     hard-linked to a file outside the plugin root passes locally; git cannot
     record a hard link, so CI cannot see one.
  4. Local versus CI: the tree walk sees untracked manifests and icons that CI will
     not, so a local pass can rest on an uncommitted file; CI on the checkout is the
     authoritative run. The walk does not descend into a symlinked directory, so a
     manifest reached only through one is not reconciled.
  5. A case-insensitive filesystem can resolve a differently cased icon path
     locally while the Linux CI runner refuses it; CI is authoritative.
  6. The floor (PNG or JPEG, square, 512 to 2048, under 2 MB read as 2,000,000
     bytes, the "./" prefix, extension consistency, the accepted JPEG processes)
     is repository policy from the row 64 brief, plan, and orchestrator
     decisions, not a verified CLI specification; the pinned CLI
     validator remains the authority on what Claude Code accepts. The PNG and JPEG
     structural rules above are applied from the format specifications as known to
     the author; they were not re-verified against the specification texts in this
     change.
  7. Scope: only top-level icon keys and plugins[i].icon keys are examined; an icon
     key at any other nesting is not seen. YAML icon references
     (cleanlanguage/agents/openai.yaml) are outside this gate; its icon_small is an
     SVG this gate would refuse, so those references stay with release-package.sh.
  8. A marketplace icon is refused rather than checked, because its base directory
     is unverified.

Exit codes:
  0  every icon field was checked and conforms
  1  an invalid icon field, path, image, or manifest set
  3  a manifest, directory, or icon that could not be read, inspected, resolved, or
     decoded
"""
from __future__ import annotations

import json
import os
import stat
import struct
import sys
import zlib
from pathlib import Path
from typing import NoReturn, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFESTS = (
    ".claude-plugin/marketplace.json",
    "cleanlanguage/.claude-plugin/plugin.json",
    "cleanlanguage/plugin.json",
    "plugin/.claude-plugin/marketplace.json",
    "plugin/aiqt-guardrails-hooks/.claude-plugin/plugin.json",
)
REQUIRED_ICON_MANIFESTS = ("cleanlanguage/.claude-plugin/plugin.json",)
MANIFEST_NAMES = frozenset({"plugin.json", "marketplace.json"})
PRUNED_TOP_LEVEL = frozenset({".git"})

MAX_ICON_BYTES = 2000000
MIN_SIDE = 512
MAX_SIDE = 2048

# Every manifest and icon is opened without following a symlink, without blocking on
# a FIFO, and without leaking the descriptor.
OPEN_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
# The critical PNG chunk types this gate recognizes; parse_png refuses a critical
# chunk (upper-case first letter) whose type is not in this set, as a conforming
# decoder must refuse it.
PNG_CRITICAL = frozenset({"IHDR", "PLTE", "IDAT", "IEND"})
# Valid sample precisions per accepted JPEG frame marker (ITU-T T.81 Table B.2):
# SOF0 (baseline) 8; SOF1 (extended sequential, Huffman) and SOF2 (progressive,
# Huffman) 8 or 12.
SOF_PRECISIONS = {
    0xC0: frozenset({8}),
    0xC1: frozenset({8, 12}),
    0xC2: frozenset({8, 12}),
}
# Largest valid scan-header Huffman table selectors (DC Td, AC Ta) per accepted
# frame marker (ITU-T T.81 Table B.3): SOF0 1 and 1; SOF1 and SOF2 3 and 3.
SOS_TABLE_SELECTORS = {
    0xC0: (1, 1),
    0xC1: (3, 3),
    0xC2: (3, 3),
}
# The accepted frame headers (repository policy: the processes web clients render).
SOF_MARKERS = frozenset(SOF_PRECISIONS)
# Every other frame header, refused by name as an unsupported JPEG process; 0xC4
# (DHT), 0xC8 (JPG, reserved) and 0xCC (DAC) are never frame headers.
UNSUPPORTED_SOF = {
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
EXTENSIONS = {"PNG": frozenset({".png"}), "JPEG": frozenset({".jpg", ".jpeg"})}
# Valid PNG bit depths per colour type.
PNG_DEPTHS = {
    0: frozenset({1, 2, 4, 8, 16}),
    2: frozenset({8, 16}),
    3: frozenset({1, 2, 4, 8}),
    4: frozenset({8, 16}),
    6: frozenset({8, 16}),
}
MAX_U31 = 2**31 - 1
READ_BLOCK = 65536


class ImageError(Exception):
    """An image that does not parse; the message is the reason."""


class WalkError(Exception):
    """A path component that is absent, uninspectable, a symlink, or not a directory."""

    def __init__(self, kind: str, part: str, error: OSError | None = None):
        super().__init__(kind)
        self.kind = kind
        self.part = part
        self.error = error


def die(message: str, code: int = 1) -> NoReturn:
    print(f"check-manifest-icon: {message}", file=sys.stderr)
    raise SystemExit(code)


def _reject_constant(token: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant {token!r}")


def _raise(error: OSError) -> NoReturn:
    raise error


def walk_without_symlinks(
    start: Path, parts: Sequence[str], directories_only: bool = False
) -> tuple[Path, os.stat_result | None]:
    """os.lstat each cumulative component below start; return the last path and stat.

    Every component must exist and must not be a symlink. Every component before the
    last must be a directory, and the last one too when directories_only is true.
    """
    current = start
    info = None
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError as error:
            raise WalkError("missing", part, error) from error
        except OSError as error:
            raise WalkError("error", part, error) from error
        if stat.S_ISLNK(info.st_mode):
            raise WalkError("symlink", part)
        if (directories_only or index < len(parts) - 1) and not stat.S_ISDIR(info.st_mode):
            raise WalkError("notdir", part)
    return current, info


def load(rel: str) -> dict:
    """M2: reach the manifest without symlinks, open it without following one, parse."""
    try:
        path, info = walk_without_symlinks(REPO_ROOT, rel.split("/"))
    except WalkError as walk:
        if walk.kind == "symlink":
            die(
                f"{rel} path component {walk.part!r} is a symlink; a manifest must be "
                "reached without symlinks"
            )
        if walk.kind == "notdir":
            die(f"{rel} path component {walk.part!r} is not a directory")
        die(f"{rel} could not be read: {walk.error}", 3)
    if not stat.S_ISREG(info.st_mode):
        die(f"{rel} is not a regular file")
    try:
        fd = os.open(path, OPEN_FLAGS)
    except OSError as error:
        die(f"{rel} could not be read: {error}", 3)
    blocks: list[bytes] = []
    try:
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                die(f"{rel} is not a regular file")
            while True:
                block = os.read(fd, READ_BLOCK)
                if not block:
                    break
                blocks.append(block)
        except OSError as error:
            die(f"{rel} could not be read: {error}", 3)
    finally:
        os.close(fd)
    try:
        text = b"".join(blocks).decode("utf-8-sig")
    except UnicodeError as error:
        die(f"{rel} could not be read: {error}", 3)
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except RecursionError:
        die(f"{rel} could not be decoded (too deeply nested)", 3)
    except ValueError as error:
        die(f"{rel} is not valid JSON: {error}")
    if not isinstance(data, dict):
        die(f"{rel} is not a JSON object")
    return data


def discover_manifests(root: Path) -> set[str]:
    """M1: every plugin.json or marketplace.json on disk, repository-relative."""
    found: set[str] = set()
    try:
        for dirpath, dirnames, filenames in os.walk(root, onerror=_raise):
            if Path(dirpath) == root:
                dirnames[:] = [name for name in dirnames if name not in PRUNED_TOP_LEVEL]
            for name in filenames:
                if name in MANIFEST_NAMES:
                    found.add((Path(dirpath) / name).relative_to(root).as_posix())
    except OSError as error:
        die(f"the repository tree could not be listed: {error}", 3)
    return found


def icon_fields(data: dict) -> list[tuple[str, object]]:
    """M3: the top-level icon key and each plugins[i].icon key, in order."""
    fields: list[tuple[str, object]] = []
    if "icon" in data:
        fields.append(("icon", data["icon"]))
    plugins = data.get("plugins")
    if isinstance(plugins, list):
        for index, entry in enumerate(plugins):
            if isinstance(entry, dict) and "icon" in entry:
                fields.append((f"plugins[{index}].icon", entry["icon"]))
    return fields


def base_directory(manifest: Path) -> Path:
    """B: the plugin root an icon path resolves against."""
    parent = manifest.parent
    if parent.name == ".claude-plugin":
        return parent.parent
    return parent


def read_struct(fmt: str, data: bytes, start: int, limit: int) -> tuple:
    """I7: unpack fmt at start; refuse a read past limit or past the end of data."""
    end = start + struct.calcsize(fmt)
    if start < 0 or end > min(limit, len(data)):
        raise ImageError(
            f"a {end - start}-byte field at offset {start} reads past the end of its "
            "structure"
        )
    return struct.unpack_from(fmt, data, start)


def read_byte(data: bytes, index: int, limit: int) -> int:
    """I7: return the byte at index; refuse a read past limit or past the end of data."""
    if index < 0 or index >= min(limit, len(data)):
        raise ImageError(f"the byte at offset {index} lies past the end of its structure")
    return data[index]


def parse_png(data: bytes) -> tuple[int, int]:
    """I3: walk every chunk; return (width, height) from IHDR."""
    size = len(data)
    offset = len(PNG_SIGNATURE)
    first = True
    seen_idat = False
    seen_plte = False
    previous = ""
    width = height = depth = colour = 0
    while True:
        if offset == size:
            raise ImageError("no IEND chunk")
        if offset + 8 > size:
            raise ImageError(f"chunk header at offset {offset} is truncated")
        length, raw_type = read_struct(">I4s", data, offset, size)
        if not all(65 <= byte <= 90 or 97 <= byte <= 122 for byte in raw_type):
            raise ImageError(f"chunk type at offset {offset} is not four ASCII letters")
        chunk_type = raw_type.decode("ascii")
        if length > MAX_U31:
            raise ImageError(
                f"chunk {chunk_type!r} at offset {offset} declares length {length}, "
                "above 2**31 - 1"
            )
        if first:
            if chunk_type != "IHDR":
                raise ImageError(f"first chunk is {chunk_type!r}, not IHDR")
            if length != 13:
                raise ImageError(f"IHDR length is {length}, not 13")
        end = offset + 12 + length
        if end > size:
            raise ImageError(f"chunk {chunk_type!r} at offset {offset} is truncated")
        (stored_crc,) = read_struct(">I", data, end - 4, size)
        if zlib.crc32(data[offset + 4:end - 4]) != stored_crc:
            raise ImageError(f"chunk {chunk_type!r} at offset {offset} has a bad CRC")
        if 65 <= raw_type[0] <= 90 and chunk_type not in PNG_CRITICAL:
            raise ImageError(f"unknown critical chunk {chunk_type!r} at offset {offset}")
        if first:
            first = False
            width, height, depth, colour, compression, filtering, interlace = read_struct(
                ">IIBBBBB", data, offset + 8, end - 4
            )
            if width == 0 or height == 0:
                raise ImageError("width or height is 0")
            if width > MAX_U31 or height > MAX_U31:
                raise ImageError("width or height is above 2**31 - 1")
            if depth not in PNG_DEPTHS.get(colour, frozenset()):
                raise ImageError(
                    f"bit depth {depth} and colour type {colour} are not a valid pair"
                )
            if compression != 0:
                raise ImageError(f"compression method {compression} is not 0")
            if filtering != 0:
                raise ImageError(f"filter method {filtering} is not 0")
            if interlace not in (0, 1):
                raise ImageError(f"interlace method {interlace} is not 0 or 1")
        elif chunk_type == "IHDR":
            raise ImageError(f"a second IHDR chunk appears at offset {offset}")
        elif chunk_type == "PLTE":
            if seen_plte:
                raise ImageError(f"a second PLTE chunk appears at offset {offset}")
            if seen_idat:
                raise ImageError(f"the PLTE chunk at offset {offset} follows IDAT")
            if colour in (0, 4):
                raise ImageError(f"colour type {colour} must not carry a PLTE chunk")
            if length == 0 or length % 3 != 0 or length > 768:
                raise ImageError(f"PLTE length {length} is not a multiple of 3 from 3 to 768")
            if colour == 3 and length // 3 > 2**depth:
                raise ImageError(
                    f"PLTE has {length // 3} entries, more than bit depth {depth} can index"
                )
            seen_plte = True
        elif chunk_type == "IDAT":
            if seen_idat and previous != "IDAT":
                raise ImageError(f"IDAT chunk at offset {offset} is not consecutive with the earlier IDAT")
            if colour == 3 and not seen_plte:
                raise ImageError("colour type 3 has no PLTE chunk before IDAT")
            seen_idat = True
        elif chunk_type == "IEND":
            if length != 0:
                raise ImageError(f"IEND length is {length}, not 0")
            if not seen_idat:
                raise ImageError("no IDAT chunk before IEND")
            if end != size:
                raise ImageError(f"{size - end} bytes follow IEND")
            return width, height
        previous = chunk_type
        offset = end


def parse_jpeg(data: bytes) -> tuple[int, int]:
    """I4: walk markers from the SOI to the first SOS; return the frame (width, height)."""
    size = len(data)
    offset = 2
    frame: tuple[int, int, frozenset[int], int] | None = None
    while True:
        phase = "the frame header" if frame is None else "the first scan (SOS)"
        ends = "file ends before any frame header" if frame is None else (
            "file ends before any scan (SOS)"
        )
        if offset >= size:
            raise ImageError(ends)
        if read_byte(data, offset, size) != 0xFF:
            raise ImageError(f"byte at offset {offset} is not a marker prefix")
        while offset < size and read_byte(data, offset, size) == 0xFF:
            offset += 1
        if offset >= size:
            raise ImageError(ends)
        marker = read_byte(data, offset, size)
        marker_offset = offset - 1
        offset += 1
        if marker == 0x00:
            raise ImageError(f"marker 0x00 at offset {marker_offset} is not valid before {phase}")
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if marker == 0xD8:
            raise ImageError(f"a second SOI appears before {phase}")
        if marker == 0xDA and frame is None:
            raise ImageError("scan data (SOS) begins before any frame header")
        if marker == 0xD9:
            if frame is None:
                raise ImageError("EOI reached before any frame header")
            raise ImageError("EOI reached before any scan (SOS)")
        if marker in UNSUPPORTED_SOF:
            raise ImageError(
                f"frame marker 0x{marker:02X} at offset {marker_offset} "
                f"({UNSUPPORTED_SOF[marker]}) is an unsupported JPEG process; only "
                "SOF0, SOF1, and SOF2 are accepted"
            )
        if offset + 2 > size:
            raise ImageError(f"segment at offset {marker_offset} is truncated")
        (length,) = read_struct(">H", data, offset, size)
        limit = offset + length
        if length < 2:
            raise ImageError(f"segment length {length} at offset {marker_offset} is below 2")
        if limit > size:
            raise ImageError(f"segment at offset {marker_offset} is truncated")
        if marker in SOF_MARKERS:
            if frame is not None:
                raise ImageError(
                    f"a second frame header at offset {marker_offset} appears before the "
                    "first scan (SOS)"
                )
            if length < 8:
                raise ImageError(f"frame header at offset {marker_offset} is too short")
            precision, height, width, components = read_struct(
                ">BHHB", data, offset + 2, limit
            )
            if components == 0:
                raise ImageError("frame header declares 0 components")
            if length < 8 + 3 * components:
                raise ImageError(
                    f"frame header at offset {marker_offset} is too short for "
                    f"{components} components"
                )
            identifiers = [
                read_byte(data, offset + 8 + 3 * index, limit) for index in range(components)
            ]
            if len(set(identifiers)) != components:
                raise ImageError("frame header declares a component identifier twice")
            if precision not in SOF_PRECISIONS[marker]:
                raise ImageError(
                    f"sample precision {precision} is not valid for frame marker "
                    f"0x{marker:02X}"
                )
            if height == 0:
                raise ImageError("frame header declares height 0 (DNL), so dimensions cannot be read")
            if width == 0:
                raise ImageError("frame header declares width 0")
            frame = (width, height, frozenset(identifiers), marker)
        elif marker == 0xDA:
            if length < 3:
                raise ImageError(f"scan header at offset {marker_offset} is too short")
            count = read_byte(data, offset + 2, limit)
            if not 1 <= count <= 4:
                raise ImageError(f"scan header declares {count} components, not 1 to 4")
            if length != 6 + 2 * count:
                raise ImageError(
                    f"scan header at offset {marker_offset} has length {length}, not "
                    f"{6 + 2 * count} for {count} components"
                )
            selectors = [read_byte(data, offset + 3 + 2 * index, limit) for index in range(count)]
            if len(set(selectors)) != count:
                raise ImageError("scan header names a component twice")
            for selector in selectors:
                if selector not in frame[2]:
                    raise ImageError(
                        f"scan header names component {selector}, which the frame header "
                        "does not declare"
                    )
            dc_limit, ac_limit = SOS_TABLE_SELECTORS[frame[3]]
            for index, selector in enumerate(selectors):
                dc_table, ac_table = divmod(read_byte(data, offset + 4 + 2 * index, limit), 16)
                if dc_table > dc_limit or ac_table > ac_limit:
                    raise ImageError(
                        f"scan header gives component {selector} DC table {dc_table} and "
                        f"AC table {ac_table}; frame marker 0x{frame[3]:02X} allows DC 0 "
                        f"to {dc_limit} and AC 0 to {ac_limit}"
                    )
            return frame[0], frame[1]
        offset += length


def check_path_syntax(where: str, icon: object) -> list[str]:
    """P1-P3: return the components after the ./ prefix."""
    if not isinstance(icon, str) or not icon.strip():
        die(f"{where} must be a non-empty string, got {icon!r}")
    if any(
        ord(ch) < 0x20 or ord(ch) == 0x7F or 0xD800 <= ord(ch) <= 0xDFFF or ch == "\\"
        for ch in icon
    ):
        die(f"{where} value {icon!r} contains a control, NUL, surrogate, or backslash character")
    rest = icon[2:] if icon.startswith("./") else ""
    parts = rest.split("/")
    if not rest or any(part in ("", ".", "..") for part in parts):
        die(
            f"{where} value {icon!r} must be a canonical ./relative path with no "
            "empty, dot, or dot-dot component"
        )
    return parts


def read_icon(where: str, icon: str, path: Path) -> bytes:
    """F4 and F5: open without following a symlink, bound the size, read in full."""
    try:
        fd = os.open(path, OPEN_FLAGS)
    except OSError as error:
        die(f"{where}: icon file {icon!r} could not be read: {error}", 3)
    try:
        try:
            info = os.fstat(fd)
        except OSError as error:
            die(f"{where}: icon file {icon!r} could not be read: {error}", 3)
        if not stat.S_ISREG(info.st_mode):
            die(f"{where}: icon path {icon!r} is not a regular file")
        if info.st_size == 0:
            die(f"{where}: icon file {icon!r} is empty")
        if info.st_size >= MAX_ICON_BYTES:
            die(
                f"{where}: icon file {icon!r} is {info.st_size} bytes; it must be under "
                f"2 MB ({MAX_ICON_BYTES} bytes)"
            )
        data = bytearray()
        try:
            while len(data) <= MAX_ICON_BYTES:
                block = os.read(fd, min(READ_BLOCK, MAX_ICON_BYTES + 1 - len(data)))
                if not block:
                    break
                data.extend(block)
        except OSError as error:
            die(f"{where}: icon file {icon!r} could not be read: {error}", 3)
    finally:
        os.close(fd)
    if len(data) != info.st_size:
        die(f"{where}: icon file {icon!r} changed while it was read", 3)
    return bytes(data)


def check_icon(rel: str, field: str, icon: object, base: Path, repo_root: Path) -> None:
    where = f"{rel} field {field}"
    parts = check_path_syntax(where, icon)

    # F1: walk from the repository root to the plugin root, the plugin root included,
    # without following any symlink.
    try:
        root_parts = base.relative_to(REPO_ROOT).parts
    except ValueError:
        die(f"{where}: plugin root {base} is not inside the repository root {REPO_ROOT}", 3)
    try:
        walk_without_symlinks(REPO_ROOT, root_parts, directories_only=True)
    except WalkError as walk:
        if walk.kind == "symlink":
            die(
                f"{where}: plugin root component {walk.part!r} is a symlink; the icon "
                "must be reached without symlinks"
            )
        if walk.kind == "notdir":
            die(f"{where}: plugin root component {walk.part!r} is not a directory")
        die(f"{where}: plugin root component {walk.part!r} could not be inspected: {walk.error}", 3)

    # F1/F2: and on from the plugin root to the icon file.
    try:
        current, info = walk_without_symlinks(base, parts)
    except WalkError as walk:
        if walk.kind == "missing":
            die(f"{where}: icon file does not exist: {icon!r}")
        if walk.kind == "error":
            die(f"{where}: icon path {icon!r} could not be inspected: {walk.error}", 3)
        if walk.kind == "symlink":
            die(
                f"{where}: path component {walk.part!r} of {icon!r} is a symlink; the icon "
                "must be reached without symlinks"
            )
        die(f"{where}: icon path {icon!r} is not a regular file")
    if not stat.S_ISREG(info.st_mode):
        die(f"{where}: icon path {icon!r} is not a regular file")

    # F3 backstop: the resolved path stays inside the plugin root and the repository.
    try:
        resolved = current.resolve()
        base_resolved = base.resolve()
    except (OSError, RuntimeError) as error:
        die(f"{where}: icon path {icon!r} could not be resolved: {error}", 3)
    if not resolved.is_relative_to(base_resolved):
        die(f"{where}: icon path {icon!r} resolves outside the plugin root")
    if not resolved.is_relative_to(repo_root):
        die(f"{where}: icon path {icon!r} resolves outside the repository")

    data = read_icon(where, icon, current)

    # I1: the signature decides the format.
    if data[:len(PNG_SIGNATURE)] == PNG_SIGNATURE:
        image_format = "PNG"
    elif data[:len(JPEG_SIGNATURE)] == JPEG_SIGNATURE:
        image_format = "JPEG"
    else:
        die(f"{where}: icon file {icon!r} is neither PNG nor JPEG by file signature")

    # I2 (repository policy): the extension is consistent with the signature.
    extension = Path(parts[-1]).suffix.lower()
    if extension not in EXTENSIONS[image_format]:
        die(
            f"{where}: icon file {icon!r} has extension {extension!r}, which does not "
            f"match its {image_format} signature"
        )

    # I3/I4
    try:
        if image_format == "PNG":
            width, height = parse_png(data)
        else:
            width, height = parse_jpeg(data)
    except ImageError as error:
        die(f"{where}: icon file {icon!r} is not a parseable {image_format}: {error}")

    # I5 (repository policy): square, 512 to 2048 per side.
    if width != height:
        die(f"{where}: icon file {icon!r} is {width} x {height} pixels; it must be square")
    if not MIN_SIDE <= width <= MAX_SIDE:
        die(
            f"{where}: icon file {icon!r} is {width} x {height} pixels; each side must "
            f"be {MIN_SIDE} to {MAX_SIDE}"
        )

    # I6
    print(
        f"check-manifest-icon: {where}: {icon} is a {image_format} of {width} x "
        f"{height} pixels, {len(data)} bytes."
    )


def main() -> int:
    declared = tuple(MANIFESTS)
    for rel in REQUIRED_ICON_MANIFESTS:  # M4: the required set is itself declared
        if rel not in declared:
            die(f"required icon manifest {rel} is not declared in MANIFESTS")

    on_disk = discover_manifests(REPO_ROOT)  # M1
    for rel in sorted(on_disk - set(declared)):
        die(
            f"manifest {rel} is on disk but not declared in MANIFESTS; add it and "
            "review its icon fields"
        )

    loaded = [(rel, load(rel)) for rel in declared]  # M2

    try:
        repo_root = REPO_ROOT.resolve()
    except (OSError, RuntimeError) as error:
        die(f"the repository root could not be resolved: {error}", 3)

    checked = 0
    for rel, data in loaded:
        fields = icon_fields(data)
        if fields and Path(rel).name == "marketplace.json":  # M3
            die(
                f"{rel} field {fields[0][0]}: an icon in a marketplace manifest is not "
                "supported by this gate; the directory its path resolves against is "
                "unverified, so extend the gate before declaring one"
            )
        if rel in REQUIRED_ICON_MANIFESTS and "icon" not in data:  # M4
            die(f"{rel} field icon is missing; the published plugin manifest must declare an icon")
        base = base_directory(REPO_ROOT / rel)
        for field, icon in fields:
            check_icon(rel, field, icon, base, repo_root)
            checked += 1

    if checked == 0:  # M4 backstop
        die("no icon field was checked; the gate would be vacuous")
    return 0


if __name__ == "__main__":
    sys.exit(main())
