---
name: no-worker-identifiers
description: Adopter-owned rule that no worker email address, account identifier, seat label or other third-party identifier appears on any public or potentially public surface of this repository.
---

# No worker identifiers on public surfaces

Adopter-owned, under the reserved `.claude/rules/external/` namespace (maintainer decision,
2026-11-26, fleet rule Entry 244). The vendored rules under `rules/aiqt/` and
`rules/security/` stay unedited.

No worker email address, account identifier, seat label or other third-party identifier may
appear on any public or potentially public surface of this repository: commit messages and
trailers, pull request titles, descriptions and comments, code, tests, fixtures, docs, the
site, release notes and package metadata. 2 exemptions: the maintainer's own name and email
address, and the security contact in `site/.well-known/security.txt`, which is the
maintainer's address. Internal channels use a role name (for example "a claude worker")
where a role will do. A fixture that needs an address uses a reserved documentation domain
(`.invalid`, `.test`, `.example`, or `example.com`, `example.org` or `example.net`), never a
real account.

Mechanical coverage: `tools/test-no-worker-identifiers.py` scans every tracked file, the
vendored trees included, for email-shaped text outside the exemptions, and fails the
Orchestration registry workflow and `tools/run_all_checks.sh` on a hit. It fails closed: a
file that git lists but that cannot be read is a failure naming the file, never a skip.

Residual: the scan catches the email class only. A seat label, a bare account handle or a
numeric account identifier passes it, because a committed pattern that names a real label
would itself publish the label; those forms rest on this rule, on the standing line that
every QA and drafting brief carries, and on any scan the maintainer keeps outside the
repository. An address split across lines, assembled by code, or written with the word "at"
passes; an untracked file, a tracked symbolic link and a submodule are not read; an address
inside compressed or encoded binary content passes; surfaces that are not files in this
tree, such as a pull request title, description or comment, are not reached by the scan,
and `tools/check-pr-text.py` carries no identifier pattern today. A label that leaked into
the history of an older pull request and was removed later is held for the maintainer and
is out of scope for this rule's enforcement.
