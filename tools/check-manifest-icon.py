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
  M2  every declared manifest loads, unconditionally (no presence test), as a JSON
      object; a declared manifest that is absent or unreadable fails closed;
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
  F1  each component, walked from the plugin root with os.lstat, exists and is not a
      symlink, and each non-final component is a directory;
  F2  the final component is a regular file;
  F3  backstop: the resolved icon path lies inside both the plugin root and the
      repository;
  F4  the file is opened with O_NOFOLLOW and O_NONBLOCK (so a FIFO swapped in
      cannot stall the open), re-checked as a regular file through fstat, and read in full up to MAX_ICON_BYTES + 1 bytes; a file whose length
      changes between fstat and the read fails closed;
  F5  the file is not empty and its size is strictly below MAX_ICON_BYTES, checked
      before any parse;
  I1  the format is decided by the file signature alone, PNG or JPEG;
  I3  a PNG is walked chunk by chunk without decompression: IHDR first with length
      13, every chunk complete with a valid CRC and a four-letter ASCII type, a
      valid bit depth and colour type pair, compression 0, filter 0, interlace 0
      or 1, at least one IDAT before IEND, and no byte after IEND; every other
      chunk, ancillary or private, is skipped by its length and never interpreted;
  I4  a JPEG is walked marker by marker from the SOI: fill bytes and standalone
      markers are skipped, every other segment is skipped by its length, and the
      first frame header (SOF0 to SOF15, never DHT, JPG, or DAC) supplies the
      dimensions; SOS, EOI, a second SOI, marker 0x00, a non-marker byte, a
      truncated segment, a length below 2, or a frame header that is short or
      declares 0 components, height 0 (DNL), or width 0 is refused;
  I5  the image is square, each side 512 to 2048 pixels inclusive;
  I6  each conforming icon field prints one success line to stdout.

Repository-policy checks (taken from the row 64 brief and plan, not from a verified
Claude Code specification, so labelled as such):
  P3  the "./" prefix and the canonical-path form;
  I2  the lower-cased file extension is consistent with the signature (.png for a
      PNG; .jpg or .jpeg for a JPEG); the signature decides the format and the
      extension never does, but a JPEG named .png is refused;
  F5  the 2 MB limit is read as 2,000,000 bytes, strictly below; a 2 MiB
      (2,097,152-byte) reading would accept files the decimal reading refuses, so
      the stricter decimal reading is used while the CLI limit is unverified;
  I5  the square shape and the 512 to 2048 side bounds;
  M4  the required icon on cleanlanguage/.claude-plugin/plugin.json.

The base directory of an icon path is the plugin root: the grandparent of a manifest
inside a .claude-plugin directory, otherwise the directory holding the manifest.
Manifest reads use utf-8-sig, so a leading UTF-8 byte-order mark does not falsely
reject a conforming manifest, and reject the non-standard JSON constants NaN and
Infinity. Filesystem inspection uses os.lstat mode bits rather than the Path
predicates, which suppress OSErrors on some Python versions and would turn an
inspection failure into a silent skip. O_NOFOLLOW, O_NONBLOCK, and O_CLOEXEC are
POSIX flags; the gate targets the Linux CI runner.

Residuals this gate does not cover:
  1. Header validity is not image validity: IDAT is never decompressed and JPEG scan
     data is never decoded, so a PNG with valid framing and a corrupt stream, or a
     JPEG with a valid frame header and corrupt entropy data, passes.
  2. Renderability is not checked: arithmetic-coded and lossless JPEG frame types
     (SOF3, SOF9 to SOF11, SOF15), CMYK or Adobe APP14-transformed JPEGs, 16-bit and
     palette PNGs, and APNG pass the header checks, though some renderers cannot
     show them. A multi-picture (MPO) file reports its first frame. EXIF orientation
     is ignored; a rotation preserves squareness and side length, so it cannot turn
     a passing icon into a failing one.
  3. Symlink races: the lstat walk and O_NOFOLLOW close the race on the final
     component; a directory component swapped between the walk and the open
     remains, bounded by the resolve backstop and by CI running on a fresh
     checkout.
  4. Local versus CI: the tree walk sees untracked manifests and icons that CI will
     not, so a local pass can rest on an uncommitted file; CI on the checkout is the
     authoritative run. The walk does not descend into a symlinked directory, so a
     manifest reached only through one is not reconciled.
  5. A case-insensitive filesystem can resolve a differently cased icon path
     locally while the Linux CI runner refuses it; CI is authoritative.
  6. The floor (PNG or JPEG, square, 512 to 2048, under 2 MB read as 2,000,000
     bytes, the "./" prefix, extension consistency) is repository policy from the
     row 64 brief and plan, not a verified CLI specification; the pinned CLI
     validator remains the authority on what Claude Code accepts.
  7. Scope: only top-level icon keys and plugins[i].icon keys are examined; an icon
     key at any other nesting is not seen. YAML icon references
     (cleanlanguage/agents/openai.yaml) are outside this gate; its icon_small is an
     SVG this gate would refuse, so those references stay with release-package.sh.
  8. A marketplace icon is refused rather than checked, because its base directory
     is unverified.
  9. The plugin-root branch of the F3 backstop is reachable only through a race
     that F1 otherwise closes, so no test drives it directly.

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
from typing import NoReturn

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

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
# Frame headers SOF0 to SOF15; 0xC4 (DHT), 0xC8 (JPG, reserved) and 0xCC (DAC) are
# never frame headers.
SOF_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)
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


def die(message: str, code: int = 1) -> NoReturn:
    print(f"check-manifest-icon: {message}", file=sys.stderr)
    raise SystemExit(code)


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _reject_constant(token: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant {token!r}")


def _raise(error: OSError) -> NoReturn:
    raise error


def load(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        die(f"{_rel(path)} could not be read: {error}", 3)
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except RecursionError:
        die(f"{_rel(path)} could not be decoded (too deeply nested)", 3)
    except ValueError as error:
        die(f"{_rel(path)} is not valid JSON: {error}")
    if not isinstance(data, dict):
        die(f"{_rel(path)} is not a JSON object")
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


def parse_png(data: bytes) -> tuple[int, int]:
    """I3: walk every chunk; return (width, height) from IHDR."""
    size = len(data)
    offset = len(PNG_SIGNATURE)
    first = True
    seen_idat = False
    width = height = 0
    while True:
        if offset == size:
            raise ImageError("no IEND chunk")
        if offset + 8 > size:
            raise ImageError(f"chunk header at offset {offset} is truncated")
        length, raw_type = struct.unpack(">I4s", data[offset:offset + 8])
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
        (stored_crc,) = struct.unpack(">I", data[end - 4:end])
        if zlib.crc32(data[offset + 4:end - 4]) != stored_crc:
            raise ImageError(f"chunk {chunk_type!r} at offset {offset} has a bad CRC")
        payload = data[offset + 8:end - 4]
        if first:
            first = False
            width, height, depth, colour, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
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
        elif chunk_type == "IDAT":
            seen_idat = True
        elif chunk_type == "IEND":
            if not seen_idat:
                raise ImageError("no IDAT chunk before IEND")
            if end != size:
                raise ImageError(f"{size - end} bytes follow IEND")
            return width, height
        offset = end


def parse_jpeg(data: bytes) -> tuple[int, int]:
    """I4: walk markers from the SOI; return (width, height) from the first frame."""
    size = len(data)
    offset = 2
    while True:
        if offset >= size:
            raise ImageError("file ends before any frame header")
        if data[offset] != 0xFF:
            raise ImageError(f"byte at offset {offset} is not a marker prefix")
        while offset < size and data[offset] == 0xFF:
            offset += 1
        if offset >= size:
            raise ImageError("file ends before any frame header")
        marker = data[offset]
        marker_offset = offset - 1
        offset += 1
        if marker == 0x00:
            raise ImageError(
                f"marker 0x00 at offset {marker_offset} is not valid before the frame header"
            )
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if marker == 0xD8:
            raise ImageError("a second SOI appears before the frame header")
        if marker == 0xDA:
            raise ImageError("scan data (SOS) begins before any frame header")
        if marker == 0xD9:
            raise ImageError("EOI reached before any frame header")
        if offset + 2 > size:
            raise ImageError(f"segment at offset {marker_offset} is truncated")
        (length,) = struct.unpack(">H", data[offset:offset + 2])
        if length < 2:
            raise ImageError(f"segment length {length} at offset {marker_offset} is below 2")
        if offset + length > size:
            raise ImageError(f"segment at offset {marker_offset} is truncated")
        if marker in SOF_MARKERS:
            if length < 8:
                raise ImageError(f"frame header at offset {marker_offset} is too short")
            _precision, height, width, components = struct.unpack(
                ">BHHB", data[offset + 2:offset + 8]
            )
            if components == 0:
                raise ImageError("frame header declares 0 components")
            if length < 8 + 3 * components:
                raise ImageError(
                    f"frame header at offset {marker_offset} is too short for "
                    f"{components} components"
                )
            if height == 0:
                raise ImageError("frame header declares height 0 (DNL), so dimensions cannot be read")
            if width == 0:
                raise ImageError("frame header declares width 0")
            return width, height
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
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
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

    # F1/F2: walk from the plugin root without following any symlink.
    current = base
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            die(f"{where}: icon file does not exist: {icon!r}")
        except OSError as error:
            die(f"{where}: icon path {icon!r} could not be inspected: {error}", 3)
        if stat.S_ISLNK(info.st_mode):
            die(
                f"{where}: path component {part!r} of {icon!r} is a symlink; the icon "
                "must be reached without symlinks"
            )
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
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

    loaded = [(rel, load(REPO_ROOT / rel)) for rel in declared]  # M2

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
