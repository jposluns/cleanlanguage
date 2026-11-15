#!/usr/bin/env python3
"""Offline consistency check of the plugin distribution (TODO 234).

The fleet plugin distribution standard asks for an offline consistency check,
stdlib only and with no network, beside the pinned `claude plugin validate`
runs, because that validator passes a marketplace whose relative source names
a folder that does not exist. This gate reads the repository's manifests and
makes 4 checks. Each failure line is FAIL, a space and the tag of its check,
the plan's numbering, which CHECKS maps to the names used here.

  Names agree: the name of .claude-plugin/marketplace.json, the name of its
      plugin entry, the names of cleanlanguage/.claude-plugin/plugin.json and
      cleanlanguage/plugin.json and the site_key of site-src/site.json are all
      PROJECT; the marketplace lists exactly 1 plugin; no marketplace name or
      plugin entry name in either marketplace (the repository's and the
      vendored plugin/.claude-plugin/marketplace.json) is missing, is not a
      string or is empty, or starts with a reserved prefix of
      RESERVED_PREFIXES in any letter case; and in both marketplaces each
      plugin entry whose source resolves has the name of the plugin manifest
      it reaches. Whether the Claude Code CLI reserves the prefixes in any
      letter case is not known offline, so the gate refuses every case.
  Sources exist: in both marketplaces each plugin entry has a string source
      that starts with "./" and has no empty and no ".." component, and it
      resolves below the marketplace root, each component reached with
      os.lstat and none a symlink, to a directory that holds a regular
      .claude-plugin/plugin.json. The plugin entry of
      .claude-plugin/marketplace.json must reach CLAUDE_MANIFEST, this
      repository's plugin. A source that is not a string, such as a GitHub
      source object, is refused, because this gate cannot read where it leads.
  Versions agree: the versions of both plugin manifests, the Version: line of
      the skill's SKILL.md, read with the VERSION_LINE and SKILL_VERSION
      patterns of the shared extractor tools/skill-version.py, and the version
      of any plugin entry of .claude-plugin/marketplace.json that carries one,
      are each a nonempty string and are the same text.
  Dependencies resolve: every dependency named by a plugin entry or by the
      plugin manifest its relative source reaches names a plugin entry of the
      same marketplace, as a bare name or as name@<that marketplace>. The count
      is printed, so a pass with no dependency to resolve is visible.

The checks of the hosted catalog and of the release zips (the standard's
sha256 and zip-content checks) belong to a later unit and are not made here.

Every file, the extractor tools/skill-version.py among them, is reached from
REPO_ROOT with os.lstat on each path component, so no component may be a
symlink, and opened with O_NOFOLLOW; the gate runs the extractor's bytes as
read, so it never opens the extractor again by path. JSON is decoded as
utf-8-sig, so a leading byte-order mark does not fail a conforming file, the
non-standard constants NaN and Infinity are refused, and a key repeated in any
JSON object is refused, as tools/check-manifest-icon.py does, since json.loads
alone keeps only the last value of a repeated key.

Usage: python3 -I tools/check-plugin-distribution.py
Exit status: 0 when every check passes, with a last line that starts "OK:";
1 when a check finds an inconsistency, with 1 line "FAIL <tag>: ..." for each
and a last line "FAIL: <n> inconsistencies" ("FAIL: 1 inconsistency" for 1).
A SKILL.md whose first Version: line is missing or is not a bare X.Y.Z is such
an inconsistency: the versions check fails with exit 1. 3 when an input cannot
be read: a file that is missing, reached through a symlink, not a regular
file, not UTF-8, not JSON, nested too deeply to decode, not a JSON object, or
that repeats a key, or an extractor that cannot be used, because it raises
any exception while it loads or lacks a VERSION_LINE or SKILL_VERSION pattern
of text; the cause goes to standard error, with a last line "UNREADABLE: exit
3". The gate fails closed: it never passes a check it could not make.

Residual: the gate reads the files as they are on disk; it does not ask git
which files are tracked, and it does not run the Claude Code CLI, whose own
reading of the manifests the pinned Plugin manifests job checks.
"""

from __future__ import annotations

import io
import json
import os
import re
import stat
import sys
from pathlib import Path

PROG = "check-plugin-distribution"
REPO_ROOT = Path(__file__).resolve().parent.parent

PROJECT = "cleanlanguage"
RESERVED_PREFIXES = ("claude-", "anthropic-", "anthropics-", "cc-plugin-")
# The tag that starts each failure line of a check, and the check's name.
CHECKS = {
    "D1": "names agree",
    "D2": "sources exist",
    "D3": "versions agree",
    "D4": "dependencies resolve",
}

# Repository-relative paths, each split on "/" for the walk.
MARKETPLACE = ".claude-plugin/marketplace.json"
VENDORED_MARKETPLACE = "plugin/.claude-plugin/marketplace.json"
CLAUDE_MANIFEST = "cleanlanguage/.claude-plugin/plugin.json"
AGENT_MANIFEST = "cleanlanguage/plugin.json"
SITE_JSON = "site-src/site.json"
SKILL_MD = "cleanlanguage/skills/cleanlanguage/SKILL.md"
EXTRACTOR = "tools/skill-version.py"

OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
READ_BLOCK = 65536


class Unreadable(Exception):
    """An input that cannot be read; the message names it and the cause."""


class DuplicateKey(Exception):
    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


def _unique_object(pairs: list) -> dict:
    """object_pairs_hook: build 1 JSON object, refusing a key that appears twice."""
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKey(key)
        result[key] = value
    return result


def _reject_constant(token: str):
    raise ValueError(f"non-standard JSON constant {token!r}")


def walk(rel: str) -> Path:
    """The path of rel below REPO_ROOT, reached with os.lstat on each component,
    none a symlink, each before the last a directory, the last a regular file."""
    current = REPO_ROOT
    parts = rel.split("/")
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = os.lstat(current)
        except OSError as error:
            raise Unreadable(f"{rel} could not be read: {error.strerror or error}") from error
        if stat.S_ISLNK(info.st_mode):
            raise Unreadable(f"{rel} could not be read: the component {part!r} is a symlink")
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise Unreadable(f"{rel} could not be read: the component {part!r} is not a directory")
        if index == len(parts) - 1 and not stat.S_ISREG(info.st_mode):
            raise Unreadable(f"{rel} could not be read: it is not a regular file")
    return current


def read_bytes(rel: str) -> bytes:
    path = walk(rel)
    try:
        fd = os.open(path, OPEN_FLAGS)
    except OSError as error:
        raise Unreadable(f"{rel} could not be read: {error.strerror or error}") from error
    blocks = []
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Unreadable(f"{rel} could not be read: it is not a regular file")
        while True:
            block = os.read(fd, READ_BLOCK)
            if not block:
                break
            blocks.append(block)
    except OSError as error:
        raise Unreadable(f"{rel} could not be read: {error.strerror or error}") from error
    finally:
        os.close(fd)
    return b"".join(blocks)


def load_json(rel: str) -> dict:
    try:
        text = read_bytes(rel).decode("utf-8-sig")
    except UnicodeError as error:
        raise Unreadable(f"{rel} is not UTF-8: {error}") from error
    try:
        data = json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    except DuplicateKey as error:
        raise Unreadable(f"{rel} repeats the key {error.key!r} in a JSON object") from error
    except RecursionError as error:
        raise Unreadable(f"{rel} is nested too deeply to decode") from error
    except ValueError as error:
        raise Unreadable(f"{rel} is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise Unreadable(f"{rel} is not a JSON object")
    return data


def extractor_patterns() -> tuple:
    """VERSION_LINE and SKILL_VERSION of the shared extractor, whose bytes are reached and read like
    every other input and run as read, never opened again by path. Any exception while it runs, or a
    pattern that is missing or is not a compiled pattern of text, makes the extractor unusable."""
    source = read_bytes(EXTRACTOR)
    namespace = {"__name__": "skill_version"}
    try:
        exec(compile(source, EXTRACTOR, "exec", dont_inherit=True), namespace)
    except (Exception, SystemExit) as error:
        raise Unreadable(f"the extractor {EXTRACTOR} could not be loaded: {type(error).__name__}: {error}") from error
    patterns = []
    for name in ("VERSION_LINE", "SKILL_VERSION"):
        pattern = namespace.get(name)
        if not isinstance(pattern, re.Pattern) or not isinstance(pattern.pattern, str):
            raise Unreadable(f"the extractor {EXTRACTOR} could not be used: it has no {name} pattern of text")
        patterns.append(pattern)
    return tuple(patterns)


def skill_version() -> str | None:
    """The SKILL.md version as the shared extractor reads it, or None when its
    first Version: line is missing or is not a bare X.Y.Z."""
    data = read_bytes(SKILL_MD)
    version_line, skill_version_pattern = extractor_patterns()
    try:
        text = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", newline=None).read()
    except UnicodeDecodeError as error:
        raise Unreadable(f"{SKILL_MD} is not UTF-8: {error}") from error
    line = version_line.search(text)
    match = skill_version_pattern.match(line.group(0)) if line else None
    return match.group(1) if match else None


def plugin_entries(rel: str, data: dict, failures: list, check: str) -> list:
    """(index in plugins, entry) for each entry that is a JSON object; a failure for each other."""
    plugins = data.get("plugins")
    if not isinstance(plugins, list):
        failures.append(f"{check}: {rel} has no plugins list")
        return []
    entries = []
    for index, entry in enumerate(plugins):
        if isinstance(entry, dict):
            entries.append((index, entry))
        else:
            failures.append(f"{check}: {rel} plugins[{index}] is not a JSON object")
    return entries


def check_names(markets: dict, claude: dict, agent: dict, site: dict, failures: list) -> None:
    """The names check."""
    root = markets[MARKETPLACE]
    pairs = [(f"{MARKETPLACE} name", root.get("name"))]
    plugins = root.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1:
        count = len(plugins) if isinstance(plugins, list) else "no"
        failures.append(f"D1: {MARKETPLACE} lists {count} plugins, not exactly 1")
    if isinstance(plugins, list) and plugins:
        first = plugins[0] if isinstance(plugins[0], dict) else {}
        pairs.append((f"{MARKETPLACE} plugins[0].name", first.get("name")))
    pairs += [(f"{CLAUDE_MANIFEST} name", claude.get("name")),
              (f"{AGENT_MANIFEST} name", agent.get("name")),
              (f"{SITE_JSON} site_key", site.get("site_key"))]
    for label, value in pairs:
        if value != PROJECT:
            failures.append(f"D1: {label} is {value!r}, not {PROJECT!r}")
    for rel, data in markets.items():
        names = [(f"{rel} name", data.get("name"))]
        for index, entry in enumerate(data.get("plugins") if isinstance(data.get("plugins"), list) else []):
            if isinstance(entry, dict):
                names.append((f"{rel} plugins[{index}].name", entry.get("name")))
        for label, value in names:
            if not isinstance(value, str) or not value:
                failures.append(f"D1: {label} is {value!r}, not a name")
            elif value.lower().startswith(RESERVED_PREFIXES):
                failures.append(f"D1: {label} {value!r} starts with a reserved prefix")


def resolve_source(rel: str, index: int, source, failures: list):
    """The sources check for 1 entry: the repository-relative plugin folder, or None."""
    label = f"D2: {rel} plugins[{index}].source {source!r}"
    if not source.startswith("./"):
        failures.append(f"{label} does not start with './'")
        return None
    parts = source[2:].split("/")
    if any(part in ("", "..") for part in parts):
        failures.append(f"{label} has an empty or '..' component")
        return None
    base = rel.split("/")[:-2]
    current = REPO_ROOT.joinpath(*base) if base else REPO_ROOT
    steps = [*parts, ".claude-plugin", "plugin.json"]
    for position, part in enumerate(steps):
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            failures.append(f"{label} does not resolve: {current.relative_to(REPO_ROOT)} is missing")
            return None
        except OSError as error:
            raise Unreadable(f"{current.relative_to(REPO_ROOT)} could not be read: {error.strerror or error}") from error
        if stat.S_ISLNK(info.st_mode):
            failures.append(f"{label} does not resolve: {current.relative_to(REPO_ROOT)} is a symlink")
            return None
        wanted = stat.S_ISREG if position == len(steps) - 1 else stat.S_ISDIR
        if not wanted(info.st_mode):
            kind = "a regular file" if wanted is stat.S_ISREG else "a directory"
            failures.append(f"{label} does not resolve: {current.relative_to(REPO_ROOT)} is not {kind}")
            return None
    return "/".join([*base, *parts])


def check_sources(markets: dict, failures: list) -> dict:
    """The sources check: the folders by (marketplace, entry index)."""
    folders = {}
    for rel, data in markets.items():
        for index, entry in plugin_entries(rel, data, failures, "D2"):
            if "source" not in entry:
                failures.append(f"D2: {rel} plugins[{index}] has no source")
                continue
            source = entry["source"]
            if not isinstance(source, str):
                failures.append(f"D2: {rel} plugins[{index}].source {source!r} is not a string, so this gate "
                                "cannot read where it leads")
                continue
            folder = resolve_source(rel, index, source, failures)
            if folder is not None:
                folders[(rel, index)] = folder
    return folders


def check_reach(markets: dict, folders: dict, failures: list) -> None:
    """Each resolved entry has the name of the manifest it reaches (names check), and the entry of
    MARKETPLACE reaches CLAUDE_MANIFEST (sources check)."""
    for (rel, index), folder in folders.items():
        entry = markets[rel]["plugins"][index]
        manifest = f"{folder}/.claude-plugin/plugin.json"
        if rel == MARKETPLACE and manifest != CLAUDE_MANIFEST:
            failures.append(f"D2: {rel} plugins[{index}].source {entry['source']!r} reaches {manifest}, "
                            f"not {CLAUDE_MANIFEST}")
        reached = load_json(manifest).get("name")
        if reached != entry.get("name"):
            failures.append(f"D1: {rel} plugins[{index}].name is {entry.get('name')!r}, but the manifest its "
                            f"source reaches, {manifest}, is named {reached!r}")


def check_versions(markets: dict, claude: dict, agent: dict, version, failures: list) -> None:
    """The versions check."""
    found = [(f"{CLAUDE_MANIFEST} version", claude.get("version")),
             (f"{AGENT_MANIFEST} version", agent.get("version")),
             (f"{SKILL_MD} Version: line", version)]
    root = markets[MARKETPLACE]
    for index, entry in enumerate(root.get("plugins") if isinstance(root.get("plugins"), list) else []):
        if isinstance(entry, dict) and "version" in entry:
            found.append((f"{MARKETPLACE} plugins[{index}].version", entry["version"]))
    for label, value in found:
        if not isinstance(value, str) or not value:
            failures.append(f"D3: {label} is {value!r}, not a version")
    values = {value for _, value in found if isinstance(value, str) and value}
    if len(values) > 1:
        listed = "; ".join(f"{label} {value!r}" for label, value in found)
        failures.append(f"D3: the versions differ: {listed}")


def check_dependencies(markets: dict, folders: dict, failures: list) -> int:
    """The dependencies check: the count of dependencies read."""
    count = 0
    for rel, data in markets.items():
        market = data.get("name")
        entries = data.get("plugins") if isinstance(data.get("plugins"), list) else []
        names = {e.get("name") for e in entries if isinstance(e, dict)}
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            lists = [(f"{rel} plugins[{index}]", entry.get("dependencies"))]
            if (rel, index) in folders:
                manifest = f"{folders[(rel, index)]}/.claude-plugin/plugin.json"
                lists.append((manifest, load_json(manifest).get("dependencies")))
            for label, deps in lists:
                if deps is None:
                    continue
                if not isinstance(deps, list):
                    failures.append(f"D4: {label} dependencies is not a list")
                    continue
                for dep in deps:
                    count += 1
                    if not isinstance(dep, str) or not dep:
                        failures.append(f"D4: {label} names the dependency {dep!r}, not a plugin name")
                        continue
                    name, at, where = dep.partition("@")
                    if (at and where != market) or name not in names:
                        failures.append(f"D4: {label} dependency {dep!r} names no plugin of the marketplace "
                                        f"{market!r} in {rel}")
    return count


def counted(number: int, one: str, more: str) -> str:
    """The number and the noun, singular for 1 and plural for any other number."""
    return f"{number} {one if number == 1 else more}"


def run() -> int:
    failures: list = []
    markets = {MARKETPLACE: load_json(MARKETPLACE), VENDORED_MARKETPLACE: load_json(VENDORED_MARKETPLACE)}
    claude = load_json(CLAUDE_MANIFEST)
    agent = load_json(AGENT_MANIFEST)
    site = load_json(SITE_JSON)
    version = skill_version()
    check_names(markets, claude, agent, site, failures)
    folders = check_sources(markets, failures)
    check_reach(markets, folders, failures)
    check_versions(markets, claude, agent, version, failures)
    count = check_dependencies(markets, folders, failures)
    for failure in failures:
        print(f"FAIL {failure}")
    print(f"{PROG}: {counted(len(folders), 'relative source', 'relative sources')} resolved, "
          f"{counted(count, 'dependency', 'dependencies')} read")
    if failures:
        print(f"FAIL: {counted(len(failures), 'inconsistency', 'inconsistencies')}")
        return 1
    tags = list(CHECKS)
    print(f"OK: {tags[0]} to {tags[-1]} hold ({', '.join(CHECKS.values())}); the plugin, marketplace and site "
          f"key are {PROJECT!r} at version {version}")
    return 0


def main() -> int:
    try:
        return run()
    except Unreadable as error:
        print(f"{PROG}: {error}", file=sys.stderr)
        print("UNREADABLE: exit 3", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
