---
name: no-worker-identifiers
description: Adopter-owned rule that no worker email address, account identifier, seat label, or other third-party identifier appears on any public or potentially public surface of this repository.
---

# No worker identifiers on public surfaces

Adopter-owned, under the reserved `.claude/rules/external/` namespace (maintainer decision,
2026-11-26, fleet rule Entry 244). The vendored rules under `rules/aiqt/` and
`rules/security/` stay unedited.

No worker email address, account identifier, seat label, or other third-party identifier
may appear on any public or potentially public surface of this repository: commit messages
and trailers; pull request titles, descriptions, and comments; code, tests, fixtures, docs,
the site, release notes, and package metadata; and the names of tracked files and folders.
2 exemptions: the maintainer's own name and email address, and the security contact in
`site/.well-known/security.txt`, which is the maintainer's address. Internal channels use a
role name (for example "a claude worker") where a role will do. A fixture that needs an
address uses a reserved documentation domain, never a real account, and the scan passes such
an address on any line. Each of `example.com`, `example.org`, and `example.net` is reserved,
with every domain under it; so is every domain under the top-level domain `.invalid`,
`.test`, or `.example`. Other email-shaped text that names no account is no third
exemption, and the scan passes it only on a reviewed line: the exact-line allowlist in the
suite, `ALLOWLIST`, holds such lines, today 1, the user details of a URL on this site's own
domain in a release-link test, whose host must stay this site's origin; an entry that no
longer matches its line fails.

Mechanical coverage: `tools/test-no-worker-identifiers.py` scans every tracked file, the
vendored trees included, for email-shaped text outside the exemptions and the allowlisted
lines, and scans the whole name of every tracked path, its folder names included, in the
same way with no allowlist, for a symbolic link and a submodule as for a file. It fails the
Orchestration registry workflow and `tools/run_all_checks.sh` on a hit. It reads every
candidate address around every at sign, so an exempt candidate cannot hide an overlapping
address, and its work grows linearly with the size of a file. A failure names the file, the
line number, and a digest of the match, never the matched text or the line. A path whose
name holds a hit is never named: every failure for it, the hit in its name included, names
it by a digest of the path name. So the scan copies no address that it catches, in a file or
in a path name, into the public CI log. It fails closed: a git ls-files that fails or cannot
be started, and a file that git lists but that cannot be read, are failures naming the cause
or the file, never a skip.

Residual: the scan catches the email class only. A seat label, a bare account handle, or a
numeric account identifier passes it, because a committed pattern that names a real label
would itself publish the label; those forms rest on this rule, on the standing line that
every QA and drafting brief carries, and on any scan the maintainer keeps outside the
repository. An address split across lines, assembled by code, or written with the word "at"
passes; an untracked file, the target of a tracked symbolic link, and the content of a
submodule are not read; an address inside compressed or encoded binary content passes; an
address with a quoted local part, or with a domain written with letters outside ASCII, can
pass, since the scan reads only ASCII letters, digits, and a few marks around an at sign;
surfaces that are not files in this tree, such as a pull request title, description, or
comment, are not reached by the scan, and `tools/check-pr-text.py` carries no identifier
pattern today. The digest of a match or of a path name lets a reader who already holds a
guess of the address confirm the guess, though it does not reveal the address. A path name
is held back only from the output of the scan: git, and any other step of a workflow that
lists or names files, can still print it, so the rule, not the scan, keeps an address out of
a path name. A label that leaked into the history of an older pull request and was removed
later is held for the maintainer and is out of scope for this rule's enforcement.

Accepted false failures: a legitimate new third-party address is caught and needs a
maintainer decision; email-shaped text that is no address is caught and is reworded to a
reserved documentation domain, or is added to `ALLOWLIST` after review; and an action pinned
to a version tag in which a dot is followed directly by 2 or more letters, such as
`v1.2.3-alpha.beta.1` or `v2.0.0-rc.ab`, is caught, since a domain then ends after those
letters, unless every domain that the tag ends is exempt, as in `v1.2.3-pre.test.1`, whose
letters form a reserved last label, or `v1.0.0-rc.example.com`, while a tag whose every dot
is followed by a digit, such as `v1.2.3-rc.1`, passes.
