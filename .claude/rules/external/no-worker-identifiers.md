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
The maintainer's own name is no third-party identifier. 2 exemptions, each tested on a
candidate folded to lower case, so each holds in any letter case: (1) the candidate is
exactly the maintainer's own email address, which is also the security contact in
`site/.well-known/security.txt`; (2) the domain of the candidate is reserved for
documentation: its last label is `invalid`, `test`, or `example`, or it is, or ends with a
dot and then, `example.com`, `example.org`, or `example.net`. An at sign passes only when
every candidate that the scan reads at it is exempt, under either exemption, or when it lies
in a file on a line that the reviewed exact-line allowlist holds for that file. So, off such
a line, an address passes only when each shorter domain that it holds, ending after 2 or
more letters that follow a dot, gives an exempt candidate as well: an address at
`example.com`, at `mail.example.org`, or at a name directly under `.test` passes, and 1 at
`mail.corp.example.com` is caught, since `mail.corp` is not reserved. Internal channels use
a role name (for example "a claude worker") where a role will do. A fixture that needs an
address uses a reserved documentation domain, never a real account. Other email-shaped text
that names no account is no third exemption, and the scan passes it only on a reviewed line:
the exact-line allowlist in the suite, `ALLOWLIST`, holds such lines, today 1, the user
details of a URL on this site's own domain in a release-link test, whose host must stay this
site's origin; an entry for 1 file covers no other file, and an entry that no longer matches
a line of its file that holds a hit fails.

Mechanical coverage: `tools/test-no-worker-identifiers.py` scans every tracked file, the
vendored trees included, for email-shaped text outside the exemptions and the allowlisted
lines, and scans the whole name of every tracked path, its folder names included, in the
same way with no allowlist, for a symbolic link and a submodule as for a file. It fails the
Orchestration registry workflow and `tools/run_all_checks.sh` on a hit. It reads every
candidate address around every at sign, so an exempt candidate cannot hide an overlapping
address, and its work grows linearly with the size of a file. A failure names the file, the
line number, and a digest of the match, never the matched text or the line. A red run
prints every failure in full, 1 to a line, never through a list comparison that unittest
shortens when it is long. A path whose name holds a hit is never named: every failure for
it, the hit in its name included, names it by a digest of the path name. Any other path name
is printed with each character that is not printable, such as a line feed, a carriage return,
or the escape byte of a terminal escape sequence, and each backslash written as a backslash
escape, so each failure is 1 line and no control character of a path name reaches the CI
log. The suite takes each expected digest from a source apart from the helper that makes the
digest: a known-answer literal, an expected-digest helper that calls `hashlib` directly, or,
in 1 case, `hashlib` called in the case itself. It fails closed: a git ls-files that fails, that
cannot be started, or that lists no path, and a file that git lists but that cannot be
read, are failures, never a skip. Each such failure gives a fixed category with only the
exit code of git or the errno name or type of the error, never a diagnostic of git, the
message of an exception, the error text of the system, or the path of the repository or of
git, and names a file that cannot be read as every failure names its file. So no failure
line copies an address that the scan catches, in a file or in a path name, or that such
environment text holds.

Residual: the scan catches the email class only. A seat label, a bare account handle, or a
numeric account identifier passes it, because a committed pattern that names a real label
would itself publish the label; those forms rest on this rule, on the standing line that
every QA and drafting brief carries, and on any scan the maintainer keeps outside the
repository. An address split across lines, assembled by code, or written with the word "at"
passes; an untracked file, the target of a tracked symbolic link, and the content of a
submodule are not read; an address inside compressed or encoded binary content passes,
since the scan neither decompresses nor decodes, unless that content holds the address as
it is; an at sign outside ASCII, such as a confusable like the fullwidth or the small
commercial at sign, passes, and so does an at sign written as an HTML character reference,
such as the decimal or the named form, or percent-encoded, since the scan searches only for
the ASCII at sign; an address whose local part ends, right before the at sign, in a byte
that the local part does not name, such as a letter outside ASCII, a tilde, an exclamation
mark, or an apostrophe, passes, since its local part is then empty; an address with a
quoted local part, with a domain written with letters outside ASCII or as a literal in
square brackets, with an underscore in its domain, or with a dot of its domain written as an
HTML character reference or percent-encoded, can pass, since the scan reads raw bytes and a
byte that a run does not name ends that run: the local part, which ends right before the at
sign, names ASCII letters, digits, and the 5 characters `.`, `_`, `%`, `+`, and `-`, and the
domain run, which starts right after it, names ASCII letters, digits, dots, and hyphens;
surfaces that are not files in this tree, such as a pull request title, description, or
comment, are not reached by the scan, and `tools/check-pr-text.py` carries no identifier
pattern today. The suite pins each form of text in this list that passes with its own
subtest, named for the form, apart from compressed or encoded content, which has its own
case, and each place in this list that is not read with its own case; a surface that is not
a file in this tree is outside its input, so no case pins it. The digest of a
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
