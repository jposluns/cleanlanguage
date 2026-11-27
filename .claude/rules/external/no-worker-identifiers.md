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
The maintainer's own name is no third-party identifier. 2 exemptions: the maintainer's own
email address, which is also the security contact in `site/.well-known/security.txt`, and
an address at a reserved documentation domain, as below. Internal channels use a role name
(for example "a claude worker") where a role will do. A fixture that needs an address uses
a reserved documentation domain, never a real account. Each of `example.com`,
`example.org`, and `example.net` is reserved, with every domain under it; so is every domain
under the top-level domain `.invalid`, `.test`, or `.example`. The scan passes such an
address on any line only when every candidate that it reads at the at sign is exempt, that
is, when each shorter domain that the address holds, ending after 2 or more letters that
follow a dot, is reserved as well: an address at `example.com`, at `mail.example.org`, or at
a name directly under `.test` passes, and 1 at `mail.corp.example.com` is caught, since
`mail.corp` is not reserved. Other email-shaped text that names no account is no third
exemption, and the scan passes it only on a reviewed line: the exact-line allowlist in the
suite, `ALLOWLIST`, holds such lines, today 1, the user details of a URL on this site's own
domain in a release-link test, whose host must stay this site's origin; an entry for 1 file
covers no other file, and an entry that no longer matches a line of its file that holds a
hit fails.

Mechanical coverage: `tools/test-no-worker-identifiers.py` scans every tracked file, the
vendored trees included, for email-shaped text outside the exemptions and the allowlisted
lines, and scans the whole name of every tracked path, its folder names included, in the
same way with no allowlist, for a symbolic link and a submodule as for a file. It fails the
Orchestration registry workflow and `tools/run_all_checks.sh` on a hit. It reads every
candidate address around every at sign, so an exempt candidate cannot hide an overlapping
address, and its work grows linearly with the size of a file. A failure names the file, the
line number, and a digest of the match, never the matched text or the line. A path whose
name holds a hit is never named: every failure for it, the hit in its name included, names
it by a digest of the path name. The suite checks each expected digest against a sha256
that it computes apart from the helper that makes the digest. It fails closed: a git
ls-files that fails, that cannot be started, or that lists no path, and a file that git
lists but that cannot be read, are failures, never a skip. Each such failure gives a fixed
category with only the exit code of git or the errno name or type of the error, never a
diagnostic of git, the message of an exception, the error text of the system, or the path
of the repository or of git, and names a file that cannot be read as every failure names
its file. So no failure line copies an address that the scan catches, in a file or in a
path name, or that such environment text holds.

Residual: the scan catches the email class only. A seat label, a bare account handle, or a
numeric account identifier passes it, because a committed pattern that names a real label
would itself publish the label; those forms rest on this rule, on the standing line that
every QA and drafting brief carries, and on any scan the maintainer keeps outside the
repository. An address split across lines, assembled by code, or written with the word "at"
passes; an untracked file, the target of a tracked symbolic link, and the content of a
submodule are not read; an address inside compressed or encoded binary content passes; an
at sign outside ASCII, such as a confusable like the fullwidth or the small commercial at
sign, passes, and so does an at sign written as an HTML character reference or
percent-encoded, since the scan searches only for the ASCII at sign; an address whose local
part ends, right before the at sign, in a letter outside ASCII or in a mark such as a tilde,
an exclamation mark, or an apostrophe passes, since its local part is then empty; an
address with a quoted local part, with a domain written with letters outside ASCII or as a
literal in square brackets, with an underscore in its domain, or with a dot of its domain
written as an HTML character reference or percent-encoded, can pass, since the scan reads
only ASCII letters, digits, and a few marks around an at sign; surfaces that are not files
in this tree, such as a pull request title, description, or comment, are not reached by the
scan, and `tools/check-pr-text.py` carries no identifier pattern today. The digest of a
match or of a path name lets a reader who already holds a guess of the address confirm the
guess, though it does not reveal the address. A path name is held back only from the output
of the scan: git, and any other step of a workflow that lists or names files, can still
print it, so the rule, not the scan, keeps an address out of a path name. On a red run,
unittest also prints a traceback for each failed case, which holds the absolute path of the
suite file in the checkout, and a failed self-check can print the values that it compared,
the path of its temporary folder among them, so a checkout path or a temporary folder path
that holds an address reaches the CI log. A label that leaked into the history of an older
pull request and was removed later is held for the maintainer and is out of scope for this
rule's enforcement.

Accepted false failures: a legitimate new third-party address is caught and needs a
maintainer decision; email-shaped text that is no address is caught and is reworded to a
reserved documentation domain, or is added to `ALLOWLIST` after review; a fixture address
at a reserved domain that also holds a shorter domain that is not reserved, such as 1 at
`mail.corp.example.com` or 1 that appends the label `example` to an ordinary domain, is
caught and is reworded to a reserved domain with no such shorter domain; and an action
pinned to a version tag in which a dot is followed directly by 2 or more letters, such as
`v1.2.3-alpha.beta.1` or `v2.0.0-rc.ab`, is caught, since a domain then ends after those
letters, unless every domain that the tag ends is exempt, as in `v1.2.3-pre.test.1`, whose
letters form a reserved last label, or `v1.0.0-rc.example.com`, while a tag whose every dot
is followed by a digit, such as `v1.2.3-rc.1`, passes.
