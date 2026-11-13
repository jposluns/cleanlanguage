# Repository workflow

## Merging pull requests

Claude may merge a pull request to `main` automatically once its required CI
checks are green, without waiting for further approval. On this repository the
required checks are the Cloudflare Pages build and the GitHub Actions checks
`Plugin manifests`, `Skill discovery`, and `Agent Plugins manifest`, each of the
3 pinned to the GitHub Actions app. `tools/ci-status.sh` insists on those 4
checks and also on the GitHub Actions check `CI status tests`. Of the 4 GitHub
Actions checks it insists on, it reads any conclusion other than success,
skipped and neutral included, as a failure. Do not merge while any required
check is failing or still pending, and do not merge a pull request that has
unresolved review threads requesting changes.

A pull request whose head commit message carries a skip marker such as `[skip
ci]` gets no run of those GitHub Actions checks, and one whose merge with `main`
has conflicts gets no new run of them, so neither can merge until a commit that
clears the condition is pushed to it. Through `tools/ci-status.sh` a head that
lacks a check it insists on never reads green: a single reading is red when a
check that has run on that head did not pass, pending when every check that has
run on it passed or is still running, and unreadable when no check has run on
it; a wait (`--wait`) ends red at once when a check did not pass, and otherwise
ends not green when its window closes. A head that ran its checks before its
merge with `main` came to conflict keeps those runs, so `tools/ci-status.sh` can
read it green while GitHub refuses the merge. No workflow has a `merge_group`
trigger, so a merge queue would never see these checks; on 2026-10-31 the
maintainer decided not to add one now, and one must be added before any merge
queue is turned on.

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
