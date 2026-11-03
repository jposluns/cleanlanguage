# Repository workflow

## Merging pull requests

Claude may merge a pull request to `main` automatically once its required CI
checks are green, without waiting for further approval. On this repository the
required check is the Cloudflare Pages build. `tools/ci-status.sh` also insists
on the GitHub Actions checks `Plugin manifests`, `Skill discovery`, and `Agent
Plugins manifest`, ahead of them becoming required on `main`, so a pull request
lacking any of them does not read green through it. Do not merge while any
required check is failing or still pending, and do not merge a pull request that
has unresolved review threads requesting changes.

Once the GitHub Actions checks `Plugin manifests`, `Skill discovery`, and
`Agent Plugins manifest` are also required on `main`, a pull request whose head
commit message carries a skip marker such as `[skip ci]` gets no run of those
three checks and cannot merge until a new commit without a skip marker is
pushed to it. Such a head already does not read green through
`tools/ci-status.sh`, which insists on those three checks today.

## Commit attribution

Do not credit Claude in commit metadata. Omit the `Co-authored-by` trailer
naming Claude or an Anthropic no-reply address, and omit the `Claude-Session`
trailer, so no commit adds Claude to the GitHub contributors list or carries an
assistant-session link. Credit human contributors as co-authors as usual, and
keep the maintainer as the commit author.

## Writing conventions

All repository and website prose follows the Clean Language standard defined in
[`cleanlanguage/skills/cleanlanguage/SKILL.md`](cleanlanguage/skills/cleanlanguage/SKILL.md) and its references. That
skill is the authority. It requires Oxford English with -ize endings and no em
dashes or en dashes, and it governs tone, structure, and semantic preservation.

## Claude Code rules

Session guidance, the adopted governance disciplines, and the Clean Language
authoring rule live in [`.claude/`](.claude/CLAUDE.md).
