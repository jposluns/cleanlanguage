# Session hand-off

This file used to carry the working state of a maintenance session. It no longer
does.

**Operational session state is machine-local and unpublished.** The backlog,
findings, decisions, and resume point live in the maintainer's local store, which
is not part of this repository and is not published.

**Public release history is on the
[releases page](https://github.com/jposluns/cleanlanguage/releases).** Every
tagged release is produced by `.github/workflows/release-skill.yml`, so the
releases page records what actually shipped. `README.md` names it as the full
changelog.

**Contributor rules live in repository guidance.** [`CLAUDE.md`](CLAUDE.md) holds
the merge and writing conventions, [`.claude/`](.claude/CLAUDE.md) holds the
session rules and adopted governance disciplines, and
[`.claude/rules/clean-language-authoring.md`](.claude/rules/clean-language-authoring.md)
holds the writing standard and its standing exceptions.

The earlier full text remains in git history at commit `647569e`.
