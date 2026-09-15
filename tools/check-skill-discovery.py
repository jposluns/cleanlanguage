#!/usr/bin/env python3
"""Validate that the Clean Language plugin's skills are discoverable and consistent.

The Claude plugin manifest (cleanlanguage/.claude-plugin/plugin.json) declares its
skills in a "skills" array of plugin-relative paths, and each declared skill lives at
skills/<name>/SKILL.md with YAML frontmatter carrying at least a name and a
description. This gate cross-checks that declaration against the skills on disk,
without a network fetch and fail-closed: a declared skill that is absent, an
unreadable required file, or a construct the offline scanner cannot parse is a
failure, never a silent skip.

What it checks (C0-C12):
  - the Claude manifest loads as a JSON object;
  - "skills" is a non-empty array of canonical plugin-relative strings ("./..."),
    each resolving inside the plugin root, to a directory under skills/, that holds
    a regular SKILL.md file resolving inside the plugin root;
  - each SKILL.md opens a YAML frontmatter block on line 1, closes it, and carries a
    single-occurrence, non-empty name and description;
  - the declaration and the disk agree in both directions: every declared skill
    exists and every skill directory on disk is declared.

Repo-policy checks (grounded in this repository's conventions, not a verified Agent
Plugins spec requirement, so labelled as such):
  - C9  the frontmatter name equals the skill's directory basename (name == dir);
  - C11 the plugin's eponymous skill ./skills/<plugin name> is declared, where the
        plugin name is read from the Claude manifest and never hardcoded;
  - C12 no legacy cleanlanguage/SKILL.md remains after the item 43 PR2 relocation of
        the skill under skills/<name>/.

Frontmatter scanner residual (disclosed): the scanner reads only single-line plain
or single/double-quoted scalars for name and description. Anything richer (block
scalars, multi-line values, flow collections) fails closed rather than being
guessed at; the pinned `claude plugin validate --strict` run owns the full
frontmatter schema. The SKILL.md filename match is exact, correct on the Linux CI
runner; a case-insensitive filesystem is a known non-CI edge.

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

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "cleanlanguage"
CLAUDE_MANIFEST = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
LEGACY_SKILL = PLUGIN_ROOT / "SKILL.md"

BLOCK_SCALAR_INDICATORS = {">", ">-", ">+", "|", "|-", "|+"}


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


def _strip_one_quote_layer(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1].strip()
    return value


def parse_frontmatter(text: str, entry: str) -> dict:
    """Return the name/description scalars from a SKILL.md frontmatter block.

    Strict, offline, fail-closed: line 1 must be exactly `---` (a trailing carriage
    return is tolerated); the block runs to the next exact `---`; an unterminated
    block, a duplicate key, an empty value, or a block-scalar indicator all fail.
    """
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r") != "---":
        die(f"SKILL.md at {entry} has no YAML frontmatter block")

    body = None
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r") == "---":
            body = lines[1:index]
            break
    if body is None:
        die(f"SKILL.md at {entry} has an unterminated YAML frontmatter block")

    seen: set[str] = set()
    fields: dict[str, str] = {}
    for raw in body:
        line = raw.rstrip("\r")
        if line[:1] in (" ", "\t"):
            continue  # indented continuation line, ignored
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key not in ("name", "description"):
            continue  # other keys are out of this gate's scope
        if key in seen:
            die(f"SKILL.md frontmatter at {entry} has a duplicate {key!r} key")
        seen.add(key)
        value = value.strip()
        if value in BLOCK_SCALAR_INDICATORS:
            die(
                f"SKILL.md frontmatter at {entry} {key!r} uses a YAML construct the "
                "offline gate does not parse; use a single-line scalar"
            )
        value = _strip_one_quote_layer(value)
        if value:
            fields[key] = value

    for key in ("name", "description"):
        if key not in fields:
            die(f"SKILL.md frontmatter at {entry} is missing {key!r}")
    return fields


def _check_entry_syntax(entry: str) -> None:
    """C2: entry is a canonical plugin-relative path beginning with './'."""
    canonical = (
        entry.startswith("./")
        and "\\" not in entry
        and all(part not in ("", ".", "..") for part in entry[2:].split("/"))
    )
    if not canonical:
        die(f"skills entry {entry!r} must be a canonical plugin-relative path beginning with './'")


def main() -> int:
    plugin_root = PLUGIN_ROOT.resolve()
    skills_dir = PLUGIN_ROOT / "skills"

    manifest = load(CLAUDE_MANIFEST)  # C0
    claude_name = manifest.get("name")

    skills = manifest.get("skills")  # C1
    if not isinstance(skills, list) or not skills:
        die("the Claude manifest has no 'skills' array")
    for i, entry in enumerate(skills):
        if not isinstance(entry, str):
            die(f"skills entry at index {i} is not a string")

    declared_dirs: set[Path] = set()
    for entry in skills:
        _check_entry_syntax(entry)  # C2

        resolved = (PLUGIN_ROOT / entry).resolve()
        if not resolved.is_relative_to(plugin_root):  # C3
            die(f"skills entry {entry!r} resolves outside the plugin root")

        if not resolved.exists():  # C4
            die(f"skills directory for {entry!r} does not exist")
        if not resolved.is_dir() or resolved.parent != skills_dir.resolve():
            die(f"skills entry {entry!r} is not a directory under skills/")

        skill_md = resolved / "SKILL.md"  # C5
        if not skill_md.is_file():
            die(f"SKILL.md is missing at {entry}/SKILL.md")
        if not skill_md.resolve().is_relative_to(plugin_root):
            die(f"SKILL.md at {entry} resolves outside the plugin root")

        text = read_utf8(skill_md)  # C6
        fields = parse_frontmatter(text, entry)  # C6/C7/C8

        dir_name = resolved.name  # C9 (repo policy: name == dir)
        if fields["name"] != dir_name:
            die(f"skill name {fields['name']!r} does not match its directory {dir_name!r}")

        declared_dirs.add(resolved)

    # C10: reverse reconciliation, every skill directory on disk is declared.
    for child in sorted(skills_dir.iterdir()):
        if child.is_dir() and child.resolve() not in declared_dirs:
            die(
                f"skill directory skills/{child.name} is not declared in the "
                "Claude manifest skills array"
            )

    # C11: repo policy, the eponymous skill is declared (name from the manifest).
    expected = f"./skills/{claude_name}"
    if expected not in skills:
        die(f"expected skill entry {expected!r} is not declared in the Claude manifest skills array")

    # C12: repo policy, no legacy root SKILL.md survives the relocation.
    if LEGACY_SKILL.exists():
        die("legacy cleanlanguage/SKILL.md must not exist; the skill lives under skills/<name>/")

    print(
        f"check-skill-discovery: {claude_name!r} skill discovery is conformant "
        f"({len(skills)} skill(s) resolved)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
