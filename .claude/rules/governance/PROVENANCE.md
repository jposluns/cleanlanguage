# Provenance of adopted governance rules

The governance rule files in this directory are adopted verbatim from the
Claude Code rules pack in Jeff Posluns's `grc_library` project:

- Source: `jposluns/grc_library`, path `dev-security/claude-rules/governance/`
- Source repository: https://github.com/jposluns/grc_library
- Licence: CC BY-SA 4.0

Adopted files:

- `express-authorization-before-execution.md`
- `evidence-grounded-completion.md`
- `clarify-before-acting.md`

These are a curated subset chosen for their relevance to a small content and
website repository maintained with Claude Code. The security and
language-specific rules in the source pack were not adopted, because this
repository contains no application code. The source pack carries further
governance rules that may be adopted later if the need arises.

Vendored copies do not update automatically. To refresh them, re-copy from the
source repository and record the change here.

## Refresh record

- 2026-08-15: The AIQT Principle statement in `.claude/CLAUDE.md` was updated to
  the latest form supplied by the maintainer. The update adds Progress to the
  priority ordering between the top tier and Speed, revises the four facet
  definitions, and extends the halt clause to name progress. The five rules of
  AIQT were not adopted; the section points to https://aiqt.ai for the full
  standard.
