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

Exit codes:
  0  the manifest is valid and consistent
  1  the manifest is invalid or inconsistent
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

    print(f"check-agent-plugin-manifest: cleanlanguage/plugin.json is valid Agent Plugins {name!r} (schema 1.0.0).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
