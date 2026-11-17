#!/usr/bin/env python3
"""Validate cleanlanguage/plugin.json against the Agent Plugins 1.0.0 schema.

The Clean Language plugin carries a root plugin.json so it conforms to the Agent
Plugins standard (https://agent-plugins.org) alongside the Claude plugin format
in .claude-plugin/plugin.json. This gate checks that manifest structurally,
without a network fetch: required $schema and name, the name pattern, known-only
top-level keys (the schema is additionalProperties: false), field types, and the
author object shape. It also cross-checks that the name and version agree with
the Claude manifest, and that the name agrees with the marketplace entry (which
carries no version). This gate requires the Agent Plugins version and requires it
to equal the Claude manifest version, so the two manifests cannot drift.

It also requires cleanlanguage/LICENSE and cleanlanguage/NOTICE.md to be regular
files whose bytes equal the root LICENSE and NOTICE.md. A copy that is a symlink,
is missing, or is a FIFO, a folder or any other file that is not regular fails
with exit 1, and the code reads a copy only after those checks. The tests
observe that order for a FIFO: a copy that is a FIFO, or a symlink to one, must
end within FIFO_TIMEOUT (10 seconds) with exit 1 and its message while nothing
opens the FIFO (test_licence_copy_fifo_fails and the FIFO subtests of
test_licence_copy_symlink_fails in tools/test-agent-plugin-manifest.py), so a
gate that opens such a FIFO first, with or without blocking, fails. They also
observe it for a missing copy and a folder read with read_bytes, whose error
stops the gate with exit 3, not 1. A read before the refusal through a link to
a regular file, a listing of a folder, or a read of a missing copy or a folder
whose error is ignored is an untested residual: no case catches it, because
the exit code and the message stay the same. The plugin installs the
cleanlanguage/ tree and the skill zip takes these 2 files from it, so a copy
that drifted from the root file would ship a licence text the repository does
not state. The gate reads the working tree; tools/release-package.sh makes the
same comparison on the git blobs at HEAD.

Exit codes:
  0  the manifest is valid and consistent, and the licence copies equal the root files
  1  the manifest is invalid or inconsistent, or a licence copy is missing, is not a
     regular file or differs from its root file
  3  a required file could not be read
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import NoReturn

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "cleanlanguage" / "plugin.json"
CLAUDE_MANIFEST = REPO_ROOT / "cleanlanguage" / ".claude-plugin" / "plugin.json"
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"

SCHEMA_URL = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
NAME_RE = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\Z")
KNOWN_KEYS = {
    "$schema", "name", "version", "description", "author",
    "homepage", "repository", "license", "keywords", "extensions",
}
AUTHOR_KEYS = {"name", "email", "url"}
# The root files that cleanlanguage/ carries as byte-equal copies.
LICENCE_FILES = ("LICENSE", "NOTICE.md")


def die(message: str, code: int = 1) -> NoReturn:
    print(f"check-agent-plugin-manifest: {message}", file=sys.stderr)
    raise SystemExit(code)


def _reject_constant(token: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant {token!r}")


def load(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        die(f"{path.relative_to(REPO_ROOT).as_posix()} could not be read: {error}", 3)
    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as error:
        die(f"{path.relative_to(REPO_ROOT).as_posix()} is not valid JSON: {error}")
    if not isinstance(data, dict):
        die(f"{path.relative_to(REPO_ROOT).as_posix()} is not a JSON object")
    return data


def read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        die(f"{path.relative_to(REPO_ROOT).as_posix()} could not be read: {error}", 3)


def check_licence_copies() -> None:
    """Each file of LICENCE_FILES under cleanlanguage/ is a regular file equal to the root file.

    A copy that is a symlink, is missing, or is a FIFO, a folder or any other
    file that is not regular fails with exit 1, and a copy is read only after
    it passes those checks. The tests observe that order for a FIFO copy, or a
    symlink to one, which must end with exit 1 and its message within the
    test's time limit while nothing opens the FIFO, with or without blocking
    (test_licence_copy_fifo_fails, and the FIFO subtests of
    test_licence_copy_symlink_fails), and for a missing copy or a folder read
    with read_bytes, whose error stops the gate with exit 3, not 1. No case
    catches a read before the refusal through a link to a regular file, a
    listing of a folder, or a read of a missing copy or a folder whose error
    is ignored: each leaves the exit code and the message the same.
    """
    for name in LICENCE_FILES:
        root = REPO_ROOT / name
        copy = REPO_ROOT / "cleanlanguage" / name
        if copy.is_symlink():
            die(f"cleanlanguage/{name} is a symlink; it must be a regular file that copies the root {name}")
        if not copy.exists():
            die(f"cleanlanguage/{name} is missing; it must be a copy of the root {name}")
        if not copy.is_file():
            die(f"cleanlanguage/{name} is not a regular file; it must be a regular file that copies the root {name}")
        if read_bytes(copy) != read_bytes(root):
            die(f"cleanlanguage/{name} differs from the root {name}; copy the root file over it")


def main() -> int:
    manifest = load(MANIFEST)

    if manifest.get("$schema") != SCHEMA_URL:
        die(f"$schema must be {SCHEMA_URL!r}, got {manifest.get('$schema')!r}")
    name = manifest.get("name")
    if not isinstance(name, str) or not (1 <= len(name) <= 64) or not NAME_RE.match(name):
        die(f"name must match the Agent Plugins name pattern, got {name!r}")

    unknown = set(manifest) - KNOWN_KEYS
    if unknown:
        die(f"unknown top-level keys not in the Agent Plugins schema: {sorted(unknown)}")

    for key in ("version", "description", "homepage", "repository", "license"):
        if key in manifest and not isinstance(manifest[key], str):
            die(f"{key} must be a string")
    if "keywords" in manifest:
        keywords = manifest["keywords"]
        if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
            die("keywords must be an array of strings")
    if "author" in manifest:
        author = manifest["author"]
        if not isinstance(author, dict):
            die("author must be an object")
        author_unknown = set(author) - AUTHOR_KEYS
        if author_unknown:
            die(f"author has unknown keys: {sorted(author_unknown)}")
        for key, value in author.items():
            if not isinstance(value, str):
                die(f"author.{key} must be a string")
    if "extensions" in manifest:
        extensions = manifest["extensions"]
        if not isinstance(extensions, dict):
            die("extensions must be an object")
        for namespace, value in extensions.items():
            if not isinstance(value, dict):
                die(f"extensions.{namespace} must be an object")

    claude = load(CLAUDE_MANIFEST)
    if claude.get("name") != name:
        die(f"name {name!r} does not match the Claude manifest name {claude.get('name')!r}")
    version = manifest.get("version")
    if not isinstance(version, str):
        die("version is required and must be a string")
    if version != claude.get("version"):
        die(f"version {version!r} does not match the Claude manifest version {claude.get('version')!r}")

    market = load(MARKETPLACE)
    plugins = market.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        die("marketplace.json has no plugins array")
    first = plugins[0]
    if not isinstance(first, dict):
        die("marketplace.json plugins[0] is not an object")
    if first.get("name") != name:
        die(f"name {name!r} does not match marketplace plugins[0].name {first.get('name')!r}")

    check_licence_copies()

    print(f"check-agent-plugin-manifest: cleanlanguage/plugin.json is valid Agent Plugins {name!r} (schema 1.0.0), "
          "and cleanlanguage/LICENSE and cleanlanguage/NOTICE.md equal the root files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
