#!/usr/bin/env python3
"""Validate that the Clean Language plugin's skills are discoverable and consistent.

The Claude plugin manifest (cleanlanguage/.claude-plugin/plugin.json) declares its
skills in a "skills" array of plugin-relative paths, and each declared skill lives at
skills/<name>/SKILL.md with YAML frontmatter carrying at least a name and a
description. This gate cross-checks that declaration against the skills on disk,
without a network fetch and fail-closed: a declared skill that is absent, an
unreadable required file, or frontmatter that is not valid YAML is a failure, never
a silent skip.

What it checks (C0-C12):
  - the Claude manifest loads as a JSON object and carries a non-empty string name;
  - "skills" is a non-empty array of canonical plugin-relative strings, each of the
    form "./skills/<name>" (a single path component under skills/, so a declaration
    cannot reach a skill through a sibling directory or a symlink alias), with no
    duplicate entry, each resolving inside the plugin root, to a directory directly
    under skills/, that holds a regular (non-symlink) SKILL.md file resolving inside
    the plugin root;
  - each SKILL.md opens a YAML frontmatter block on line 1, closes it, and parses as
    a YAML mapping with no duplicate keys, carrying a non-empty string name and
    description;
  - the declaration and the disk agree in both directions: every declared skill
    exists and every skill directory on disk is declared.

Repo-policy checks (grounded in this repository's conventions, not a verified Agent
Plugins spec requirement, so labelled as such):
  - C9  the frontmatter name equals the skill's directory basename exactly, compared
        verbatim with no surrounding whitespace tolerated (name == dir);
  - C11 the plugin's eponymous skill ./skills/<plugin name> is declared, where the
        plugin name is read from the Claude manifest and never hardcoded;
  - C12 no legacy cleanlanguage/SKILL.md remains after the item 43 PR2 relocation of
        the skill under skills/<name>/.

Frontmatter parsing: the block is located offline (line 1 opens it, the next exact
`---` closes it) and its body is parsed with a PyYAML SafeLoader subclass that
rejects duplicate mapping keys (correct YAML, offline, with no network install), then
checked for a non-empty string name and description. The full frontmatter schema is
still owned by the pinned `claude plugin validate --strict` run. PyYAML is the CI
runner's ambient install, the same dependency the sibling release-package and
manifest tooling already rely on; leaving it unpinned is a recorded, sibling-
consistent residual, not an omission. The SKILL.md filename match is exact, correct
on the Linux CI runner; a case-insensitive filesystem is a known non-CI edge.

Exit codes:
  0  the skills are discoverable and consistent
  1  an inconsistency, including a declared skill or file that is absent
  3  an existing required file could not be read or decoded
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NoReturn

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "cleanlanguage"
CLAUDE_MANIFEST = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
LEGACY_SKILL = PLUGIN_ROOT / "SKILL.md"

SKILLS_PREFIX = "./skills/"


def die(message: str, code: int = 1) -> NoReturn:
    print(f"check-skill-discovery: {message}", file=sys.stderr)
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


def read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        die(f"{path.relative_to(REPO_ROOT).as_posix()} could not be read: {error}", 3)


if yaml is not None:

    class _NoDuplicateKeyLoader(yaml.SafeLoader):
        """SafeLoader that rejects duplicate mapping keys rather than last-wins.

        PyYAML's default construction silently keeps the last of duplicate keys,
        which lets a malformed frontmatter with a second, matching name slip a
        mismatched first value past the gate. Rejecting the duplicate outright keeps
        the parse unambiguous.
        """

    def _construct_no_duplicates(loader: "yaml.SafeLoader", node: "yaml.nodes.MappingNode") -> dict:
        mapping: dict = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=True)
            if key in mapping:
                raise yaml.YAMLError(f"duplicate key {key!r} in frontmatter mapping")
            mapping[key] = loader.construct_object(value_node, deep=True)
        return mapping

    _NoDuplicateKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_no_duplicates
    )
else:  # pragma: no cover
    _NoDuplicateKeyLoader = None


def parse_frontmatter(text: str, entry: str) -> dict:
    """Return the name/description scalars from a SKILL.md frontmatter block.

    The block is located offline: line 1 must be exactly `---` (a trailing carriage
    return is tolerated), and the block runs to the next exact `---`; an unterminated
    block fails closed. The block body is parsed with a PyYAML SafeLoader subclass
    that rejects duplicate keys, and a non-empty string name and description are
    required. The name is returned verbatim (not stripped), so C9 compares the exact
    frontmatter value against the directory basename. The full frontmatter schema is
    owned by the pinned `claude plugin validate --strict` run, not by this gate.
    """
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r") != "---":
        die(f"SKILL.md at {entry} has no YAML frontmatter block")

    end = None
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r") == "---":
            end = index
            break
    if end is None:
        die(f"SKILL.md at {entry} has an unterminated YAML frontmatter block")

    block_text = "\n".join(lines[1:end])

    if yaml is None:
        die("PyYAML is required to validate SKILL.md frontmatter", 3)
    try:
        data = yaml.load(block_text, Loader=_NoDuplicateKeyLoader)
    except yaml.YAMLError as error:
        die(f"SKILL.md frontmatter at {entry} is not valid YAML: {error}")
    except RecursionError:
        die(f"SKILL.md frontmatter at {entry} could not be decoded (too deeply nested)", 3)
    if not isinstance(data, dict):
        die(f"SKILL.md frontmatter at {entry} is not a YAML mapping")

    fields: dict[str, str] = {}
    for key in ("name", "description"):
        value = data.get(key)
        if value is None:
            die(f"SKILL.md frontmatter at {entry} is missing {key!r}")
        if not isinstance(value, str) or not value.strip():
            die(f"SKILL.md frontmatter at {entry} {key!r} must be a non-empty string")
        fields[key] = value
    return fields


def _check_entry_syntax(entry: str) -> None:
    """C2: entry is a canonical './skills/<name>' path, one component under skills/.

    Requiring the literal './skills/' prefix and a single trailing component keeps a
    declaration from reaching a skill directory through a sibling path or a symlink
    alias, so the reverse reconciliation below can trust each entry's name.
    """
    name = entry[len(SKILLS_PREFIX):] if entry.startswith(SKILLS_PREFIX) else ""
    if (
        "\\" in entry
        or not entry.startswith(SKILLS_PREFIX)
        or not name
        or "/" in name
        or name in (".", "..")
    ):
        die(f"skills entry {entry!r} must be a canonical './skills/<name>' path")


def _entry_name(entry: str) -> str:
    """The single skill-directory component of a validated './skills/<name>' entry."""
    return entry[len(SKILLS_PREFIX):]


def main() -> int:
    plugin_root = PLUGIN_ROOT.resolve()
    skills_dir = PLUGIN_ROOT / "skills"

    manifest = load(CLAUDE_MANIFEST)  # C0
    claude_name = manifest.get("name")
    if not isinstance(claude_name, str) or not claude_name.strip():  # C0
        die("the Claude manifest 'name' is missing or not a non-empty string")

    skills = manifest.get("skills")  # C1
    if not isinstance(skills, list) or not skills:
        die("the Claude manifest has no 'skills' array")
    for i, entry in enumerate(skills):
        if not isinstance(entry, str):
            die(f"skills entry at index {i} is not a string")

    seen_entries: set[str] = set()
    for entry in skills:
        if entry in seen_entries:
            die(f"skills entry {entry!r} is declared more than once")
        seen_entries.add(entry)

    for entry in skills:
        _check_entry_syntax(entry)  # C2

        try:
            resolved = (PLUGIN_ROOT / entry).resolve()
            if not resolved.is_relative_to(plugin_root):  # C3
                die(f"skills entry {entry!r} resolves outside the plugin root")
            if not resolved.exists():  # C4
                die(f"skills directory for {entry!r} does not exist")
            if not resolved.is_dir() or resolved.parent != skills_dir.resolve():
                die(f"skills entry {entry!r} is not a directory under skills/")

            skill_md = resolved / "SKILL.md"  # C5
            if skill_md.is_symlink():
                die(f"SKILL.md at {entry} must be a regular file, not a symlink")
            if not skill_md.is_file():
                die(f"SKILL.md is missing at {entry}/SKILL.md")
            if not skill_md.resolve().is_relative_to(plugin_root):
                die(f"SKILL.md at {entry} resolves outside the plugin root")
        except OSError as error:
            die(f"skills entry {entry!r} could not be inspected: {error}", 3)

        text = read_utf8(skill_md)  # C6
        fields = parse_frontmatter(text, entry)  # C6/C7/C8

        dir_name = resolved.name  # C9 (repo policy: name == dir, exact, no strip)
        if fields["name"] != dir_name:
            die(f"skill name {fields['name']!r} does not match its directory {dir_name!r}")

    # C10: reverse reconciliation, every skill directory on disk is declared. Entries
    # are validated './skills/<name>' forms, so the declared set is exactly those
    # names; deriving them from the fixed prefix (not an arbitrary entry basename)
    # keeps an undeclared sibling directory from being masked by a look-alike entry.
    declared_names = {_entry_name(entry) for entry in skills}
    try:
        children = sorted(skills_dir.iterdir())
    except OSError as error:
        die(f"{skills_dir.relative_to(REPO_ROOT).as_posix()} could not be read: {error}", 3)
    for child in children:
        try:
            is_dir = child.is_dir()
        except OSError as error:
            die(f"skills/{child.name} could not be inspected: {error}", 3)
        if is_dir and child.name not in declared_names:
            die(
                f"skill directory skills/{child.name} is not declared in the "
                "Claude manifest skills array"
            )

    # C11: repo policy, the eponymous skill is declared (name from the manifest).
    expected = f"./skills/{claude_name}"
    if expected not in skills:
        die(f"expected skill entry {expected!r} is not declared in the Claude manifest skills array")

    # C12: repo policy, no legacy root SKILL.md survives the relocation.
    try:
        legacy_present = LEGACY_SKILL.is_symlink() or LEGACY_SKILL.exists()
    except OSError as error:
        die(f"legacy cleanlanguage/SKILL.md could not be inspected: {error}", 3)
    if legacy_present:
        die("legacy cleanlanguage/SKILL.md must not exist; the skill lives under skills/<name>/")

    print(
        f"check-skill-discovery: {claude_name!r} skill discovery is conformant "
        f"({len(skills)} skill(s) resolved)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
