# Repository workflow

## Merging pull requests

Claude may merge a pull request to `main` automatically once its required CI
checks are green, without waiting for further approval. On this repository the
required check is the Cloudflare Pages build. Do not merge while any required
check is failing or still pending, and do not merge a pull request that has
unresolved review threads requesting changes.

## Writing conventions

All repository and website prose follows the Clean Language standard defined in
[`cleanlanguage/SKILL.md`](cleanlanguage/SKILL.md) and its references. That
skill is the authority. It requires Oxford English with -ize endings and no em
dashes or en dashes, and it governs tone, structure, and semantic preservation.

## Claude Code rules

Session guidance, the adopted governance disciplines, and the Clean Language
authoring rule live in [`.claude/`](.claude/CLAUDE.md).
