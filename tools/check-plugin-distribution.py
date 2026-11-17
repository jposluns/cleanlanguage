#!/usr/bin/env python3
"""Offline consistency check of the plugin distribution (TODO 234).

The fleet plugin distribution standard asks for an offline check, stdlib only
and with no network, beside the pinned `claude plugin validate` runs, because
that validator passes a marketplace whose relative source names a folder that
does not exist. This gate reads the manifests as they are on disk and makes 4
checks; CHECKS maps the tag that starts the FAIL lines of each to its name.
MARKETPLACE is the repository's marketplace and VENDORED_MARKETPLACE the
vendored one; "both marketplaces" means these 2.

  Names agree: the name of MARKETPLACE, the name of its first plugin entry,
      the names of CLAUDE_MANIFEST and AGENT_MANIFEST and the site_key of
      SITE_JSON are PROJECT, and MARKETPLACE lists exactly 1 plugin. In both
      marketplaces, each marketplace name and plugin entry name is a nonempty
      string that does not start with a prefix of RESERVED_PREFIXES after
      str.casefold; no 2 plugin entries have names equal after str.casefold;
      and each entry whose source resolves has the name of the manifest it
      reaches.
  Sources exist: in both marketplaces, the plugins key holds a list, and
      each plugin entry is a JSON object whose source is a string that starts
      with "./", has no empty, "." or ".." component, is a path the operating
      system accepts, and resolves, through the walk rules (below), to a
      folder that holds a regular .claude-plugin/plugin.json. The entry of
      MARKETPLACE reaches CLAUDE_MANIFEST.
  Versions agree: the versions of CLAUDE_MANIFEST and AGENT_MANIFEST, the
      version in the first Version: line of SKILL_MD as the patterns of
      tools/skill-version.py read it, after universal newlines, and the
      version of each plugin entry of MARKETPLACE that holds a version key,
      are each a nonempty string, and are all the same. The versions of the
      vendored entries are not read.
  Dependencies resolve: a dependencies key, in a plugin entry of either
      marketplace or in the manifest its source reaches, holds a list; each
      item is a nonempty string that names, exactly as written, another
      plugin entry of the same marketplace, as NAME or NAME@<marketplace
      name>; and no list names 1 plugin twice. The count of items read is
      printed.

Walk rules: every path the gate reads, and every source, is reached 1
component at a time with os.lstat, none a symlink, each spelled as os.listdir
of its folder lists it. The hosted catalog and the release zips are not
checked here.

Output and exit status:
  0: every check holds; a line of counts, then a last line that starts "OK:".
  1: an inconsistency; 1 line "FAIL <tag>: ..." for each, a line of counts,
     and a last line "FAIL: <n> inconsistencies" ("FAIL: 1 inconsistency" for
     1).
  3: the gate could not make its checks: on standard error, 1 cause line and
     a last line "UNREADABLE: exit 3". The causes: an input file that is
     missing, that the walk rules refuse, that is not a regular file or not
     UTF-8, that json.loads refuses (NaN, Infinity and -Infinity among
     them), that nests arrays and objects more than MAX_JSON_DEPTH levels
     deep, that repeats a key in a JSON object, or that is not a JSON object;
     a source folder the operating system will not let the gate reach or list
     for a cause other than a missing or too long name; an extractor that
     raises an exception of any class while it loads, or lacks a VERSION_LINE
     or a SKILL_VERSION pattern of text whose group 1 holds the version; and
     any other exception, of any class, that reaches main.
  Every line goes through emit, which writes each character that
  str.isprintable refuses as its Python backslash escape, so each line the
  gate prints is 1 line. Where a line shows the name of an exception's type,
  its message or the strerror of an OSError, the gate makes each into a str
  of its own type, with what that writes to sys.stdout or sys.stderr
  dropped; a name, message or strerror whose making raises an exception of
  any class, or a name that is not a str, is shown by a stand-in. What the
  extractor writes to sys.stdout or sys.stderr while it loads is dropped.

Residual: the gate does not ask git which files are tracked and does not run
the Claude Code CLI. The extractor, and the code that makes an exception's
name, message or strerror, are code the gate runs in its own process, and
only what that code writes to sys.stdout or sys.stderr while it runs is
dropped. Nothing else it does is confined, among it a write to a file
descriptor or to sys.__stdout__, a change to the interpreter or to the
gate, and code it leaves to run later, such as an atexit handler or a
thread, whose output can come after the last line stated above. A file
swapped between the walk and the open is met by O_NOFOLLOW, O_NONBLOCK and
the check after the open; O_NOFOLLOW covers only the last component, so a
folder on the path swapped for a symlink in that time is followed. An
exception raised while the gate writes to standard error is not caught.

Usage: python3 -I tools/check-plugin-distribution.py
"""

from __future__ import annotations

import contextlib
import errno
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
# The deepest nesting of arrays and objects a JSON input may have; a top-level
# object is 1 level. Far below any default recursion limit, so every supported
# interpreter decodes JSON at this depth, and far above the manifests' own.
MAX_JSON_DEPTH = 64
# The value read for a key a JSON object does not hold, unlike any value JSON can hold.
ABSENT = object()


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


def one_line(text: str) -> str:
    """text with each character that str.isprintable refuses written as its Python backslash escape,
    so the text is 1 line."""
    return "".join(char if char.isprintable() else repr(char)[1:-1] for char in text)


def emit(line: str, stream=None) -> None:
    """Print 1 line of output, to stream or else to standard output, as 1 line whatever it holds."""
    print(one_line(line), file=stream)


def plain(make, stand_in: str) -> str:
    """What make returns, as a str of its own type, with what make writes to sys.stdout and sys.stderr
    dropped; or stand_in when make raises an exception of any class or returns no str."""
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return str.__str__(make())
    except BaseException:
        return stand_in


def shown(error: BaseException) -> str:
    """The message of the exception, as plain makes it."""
    return plain(lambda: str(error), "(a message that cannot be shown)")


def reason(error: OSError) -> str:
    """The strerror of the OSError, or its message when it has none, as plain makes it."""
    return plain(lambda: str(error.strerror or error), "(a message that cannot be shown)")


def described(error: BaseException) -> str:
    """The name of the exception's type and its message, each as plain makes it."""
    return f"{plain(lambda: type(error).__name__, '(a name that cannot be shown)')}: {shown(error)}"


def walk(rel: str) -> Path:
    """The path of rel below REPO_ROOT, reached with os.lstat on each component,
    none a symlink, each spelled as its folder lists it, each before the last a
    directory, the last a regular file."""
    current = REPO_ROOT
    parts = rel.split("/")
    for index, part in enumerate(parts):
        parent, current = current, current / part
        try:
            info = os.lstat(current)
            # A file system that folds letter case lets os.lstat find the name in another case too.
            listed = part in os.listdir(parent)
        except OSError as error:
            raise Unreadable(f"{rel} could not be read: {reason(error)}") from error
        if not listed:
            raise Unreadable(f"{rel} could not be read: the component {part!r} is not spelled as its folder "
                             "lists it")
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
        raise Unreadable(f"{rel} could not be read: {reason(error)}") from error
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
        raise Unreadable(f"{rel} could not be read: {reason(error)}") from error
    finally:
        os.close(fd)
    return b"".join(blocks)


def exceeds_depth(text: str, limit: int) -> bool:
    """Whether the arrays and objects of the JSON text, counted outside strings, nest more than
    limit levels deep. Iterative, so it never depends on the recursion limit. On text that is valid
    JSON so far, the count is the decoder's own nesting; a stray closing bracket only lowers it, and
    the decoder refuses such text before it nests any further."""
    depth = 0
    in_string = escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > limit:
                return True
        elif char in "]}":
            depth -= 1
    return False


def load_json(rel: str) -> dict:
    try:
        text = read_bytes(rel).decode("utf-8-sig")
    except UnicodeError as error:
        raise Unreadable(f"{rel} is not UTF-8: {shown(error)}") from error
    if exceeds_depth(text, MAX_JSON_DEPTH):
        raise Unreadable(f"{rel} is nested too deeply to decode: more than {MAX_JSON_DEPTH} levels of arrays "
                         "and objects")
    try:
        data = json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    except DuplicateKey as error:
        raise Unreadable(f"{rel} repeats the key {error.key!r} in a JSON object") from error
    except RecursionError as error:
        raise Unreadable(f"{rel} is nested too deeply to decode: the decoder raised RecursionError") from error
    except ValueError as error:
        raise Unreadable(f"{rel} could not be decoded as JSON: {shown(error)}") from error
    if not isinstance(data, dict):
        raise Unreadable(f"{rel} is not a JSON object")
    return data


def extractor_patterns() -> tuple:
    """VERSION_LINE and SKILL_VERSION of the shared extractor, whose bytes are reached and read like
    every other input and run as read, never opened again by path, with what it writes to sys.stdout
    and sys.stderr dropped. Any exception while it runs, any BaseException among them, a pattern
    that is missing or is not a compiled pattern of text, or a SKILL_VERSION pattern with no group 1
    to hold the version, makes the extractor unusable."""
    source = read_bytes(EXTRACTOR)
    namespace = {"__name__": "skill_version"}
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            exec(compile(source, EXTRACTOR, "exec", dont_inherit=True), namespace)
    except BaseException as error:
        raise Unreadable(f"the extractor {EXTRACTOR} could not be loaded: {described(error)}") from error
    patterns = []
    for name in ("VERSION_LINE", "SKILL_VERSION"):
        pattern = namespace.get(name)
        if not isinstance(pattern, re.Pattern) or not isinstance(pattern.pattern, str):
            raise Unreadable(f"the extractor {EXTRACTOR} could not be used: it has no {name} pattern of text")
        patterns.append(pattern)
    if patterns[1].groups < 1:
        raise Unreadable(f"the extractor {EXTRACTOR} could not be used: its SKILL_VERSION pattern has no group 1")
    return tuple(patterns)


def skill_version() -> str | None:
    """The SKILL.md version as the shared extractor reads it, with universal newlines, or None when
    its first Version: line is missing or is not a bare X.Y.Z."""
    data = read_bytes(SKILL_MD)
    version_line, skill_version_pattern = extractor_patterns()
    try:
        text = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", newline=None).read()
    except UnicodeDecodeError as error:
        raise Unreadable(f"{SKILL_MD} is not UTF-8: {shown(error)}") from error
    line = version_line.search(text)
    match = skill_version_pattern.match(line.group(0)) if line else None
    if not match:
        return None
    value = match.group(1)
    if not isinstance(value, str):
        raise Unreadable(f"the extractor {EXTRACTOR} could not be used: its SKILL_VERSION pattern matched "
                         f"{line.group(0)!r} with no text in group 1")
    return value


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
        # The index of the first entry with each plugin name after case folding, so that a second is refused.
        listed: dict = {}
        repeats = []
        for index, entry in enumerate(data.get("plugins") if isinstance(data.get("plugins"), list) else []):
            if isinstance(entry, dict):
                name = entry.get("name")
                names.append((f"{rel} plugins[{index}].name", name))
                if isinstance(name, str) and name:
                    key = name.casefold()
                    if key in listed:
                        repeats.append(f"D1: {rel} plugins[{index}].name {name!r} lists the plugin of "
                                       f"plugins[{listed[key]}] a second time, which this gate refuses")
                    else:
                        listed[key] = index
        for label, value in names:
            if not isinstance(value, str) or not value:
                failures.append(f"D1: {label} is {value!r}, not a name")
            elif value.casefold().startswith(RESERVED_PREFIXES):
                failures.append(f"D1: {label} {value!r} starts with a reserved prefix")
        failures.extend(repeats)


def resolve_source(rel: str, index: int, source, failures: list):
    """The sources check for 1 entry: the repository-relative plugin folder, or None."""
    label = f"D2: {rel} plugins[{index}].source {source!r}"
    if not source.startswith("./"):
        failures.append(f"{label} does not start with './'")
        return None
    parts = source[2:].split("/")
    if any(part in ("", ".", "..") for part in parts):
        failures.append(f"{label} has an empty, '.' or '..' component")
        return None
    base = rel.split("/")[:-2]
    current = REPO_ROOT.joinpath(*base) if base else REPO_ROOT
    steps = [*parts, ".claude-plugin", "plugin.json"]
    for position, part in enumerate(steps):
        parent, current = current, current / part
        try:
            info = os.lstat(current)
        except ValueError:
            # A NUL character, or a character the file system encoding cannot hold.
            failures.append(f"{label} is not a path the operating system accepts")
            return None
        except FileNotFoundError:
            failures.append(f"{label} does not resolve: {current.relative_to(REPO_ROOT)} is missing")
            return None
        except OSError as error:
            if error.errno == errno.ENAMETOOLONG:
                # A fault of the source text, not of the tree, so a failure of this check.
                failures.append(f"{label} is not a path the operating system accepts: {reason(error)}")
                return None
            raise Unreadable(f"{current.relative_to(REPO_ROOT)} could not be read: {reason(error)}") from error
        try:
            # A file system that folds letter case lets os.lstat find the name in another case too.
            listed = part in os.listdir(parent)
        except OSError as error:
            raise Unreadable(f"{parent.relative_to(REPO_ROOT)} could not be listed: {reason(error)}") from error
        if not listed:
            failures.append(f"{label} does not resolve: {current.relative_to(REPO_ROOT)} is not spelled as its "
                            "folder lists it")
            return None
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
        # Only a string name can be named by a dependency; the names check reports any other, and a
        # name listed twice.
        names = {e["name"] for e in entries if isinstance(e, dict) and isinstance(e.get("name"), str)}
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            lists = [(f"{rel} plugins[{index}]", entry.get("name"), entry.get("dependencies", ABSENT))]
            if (rel, index) in folders:
                manifest = f"{folders[(rel, index)]}/.claude-plugin/plugin.json"
                reached = load_json(manifest)
                lists.append((manifest, reached.get("name"), reached.get("dependencies", ABSENT)))
            for label, own, deps in lists:
                # Only a missing key is no list; an explicit JSON null is refused below as not a list.
                if deps is ABSENT:
                    continue
                if not isinstance(deps, list):
                    failures.append(f"D4: {label} dependencies is not a list")
                    continue
                # The plugins this list has already named, so that a second naming of one is refused.
                seen = set()
                for dep in deps:
                    count += 1
                    if not isinstance(dep, str) or not dep:
                        failures.append(f"D4: {label} names the dependency {dep!r}, not a plugin name")
                        continue
                    name, at, where = dep.partition("@")
                    if (at and where != market) or name not in names:
                        failures.append(f"D4: {label} dependency {dep!r} names no plugin of the marketplace "
                                        f"{market!r} in {rel}")
                    elif name == own:
                        failures.append(f"D4: {label} dependency {dep!r} names the plugin itself, which this gate "
                                        "refuses")
                    elif name in seen:
                        failures.append(f"D4: {label} dependency {dep!r} names the plugin {name!r} a second time, "
                                        "which this gate refuses")
                    else:
                        seen.add(name)
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
        emit(f"FAIL {failure}")
    emit(f"{PROG}: {counted(len(folders), 'relative source', 'relative sources')} resolved, "
         f"{counted(count, 'dependency', 'dependencies')} read")
    if failures:
        emit(f"FAIL: {counted(len(failures), 'inconsistency', 'inconsistencies')}")
        return 1
    tags = list(CHECKS)
    emit(f"OK: {tags[0]} to {tags[-1]} hold ({', '.join(CHECKS.values())}); the plugin, marketplace and site "
         f"key are {PROJECT!r} at version {version}")
    return 0


def main() -> int:
    try:
        return run()
    except Unreadable as error:
        cause = shown(error)
    except BaseException as error:
        # Whatever else stops the gate, of any class, it could not make its checks: exit 3, never a
        # traceback and never exit 1, which means an inconsistency found.
        cause = f"the gate stopped on {described(error)}"
    emit(f"{PROG}: {cause}", sys.stderr)
    emit("UNREADABLE: exit 3", sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(main())
