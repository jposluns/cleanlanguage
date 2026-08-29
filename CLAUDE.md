# Repository workflow

## Merging pull requests

Claude may merge a pull request to `main` automatically once its required CI
checks are green, without waiting for further approval. On this repository the
required check is the Cloudflare Pages build. Do not merge while any required
check is failing or still pending, and do not merge a pull request that has
unresolved review threads requesting changes.

## Commit attribution

Do not credit Claude as a commit co-author. Omit any `Co-authored-by` trailer
naming Claude or an Anthropic no-reply address, because GitHub builds the
contributors list from co-authors and this project does not list its AI tooling
there. Credit human contributors as co-authors as usual, and keep the maintainer
as the commit author.

## Writing conventions

All repository and website prose follows the Clean Language standard defined in
[`cleanlanguage/SKILL.md`](cleanlanguage/SKILL.md) and its references. That
skill is the authority. It requires Oxford English with -ize endings and no em
dashes or en dashes, and it governs tone, structure, and semantic preservation.

## Claude Code rules

Session guidance, the adopted governance disciplines, and the Clean Language
authoring rule live in [`.claude/`](.claude/CLAUDE.md).
