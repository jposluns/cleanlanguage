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
same way with no allowlist, for a symbolic link and a submodule as for a file. It reads the
content of each tracked entry from the stored blob that the index names, through
`git ls-files --stage` and 1 `git cat-file --batch` call, never from the working copy, so no
attribute, filter, encoding, such as a `working-tree-encoding` of UTF-16LE, or state of the
working copy changes what is scanned; a tracked symbolic link is scanned by its own stored
target text, not by the file that it points to. It fails the Orchestration registry workflow
and `tools/run_all_checks.sh` on a hit. It reads every candidate address around every at
sign, so an exempt candidate cannot hide an overlapping address, and its work grows linearly
with the size of a file. Only a hit in the content of a file, or in the stored target text of
a tracked symbolic link, names a line: that failure names the file or link, the line number,
and a digest of the match. A hit in a path name names the path and
a digest of the match, and no line; a stale allowlist entry names its file, its position, and
a digest of its text, and no line; and the fail-closed failures below name no line and no
digest of a match. No failure holds the matched text or the line. A red run
prints every failure in full, 1 to a line, never through a list comparison that unittest
shortens when it is long. A path whose name holds a hit is never named: every failure for
it, the hit in its name included, names it by a digest of the path name. Any other path name
is printed with each character that is not printable, such as a line feed, a carriage return,
or the escape byte of a terminal escape sequence, and each backslash written as a backslash
escape, so each failure is 1 line and no control character of a path name reaches the CI
log. The suite takes each expected digest from a source apart from the helper that makes the
digest: a known-answer literal, an expected-digest helper that calls `hashlib` directly, or,
in 1 case, `hashlib` called in the case itself. It fails closed: a git ls-files that fails, that
cannot be started, or that lists no path, a git cat-file that fails or that cannot be
started, a reply of either that the scan cannot read, and a tracked entry whose stored blob
cannot be read, are failures, never a skip. Each such failure gives a fixed category with
only the exit code of git, the errno name or type of the error, or a fixed word: unexpected
reply for a reply that the scan cannot read, in the line git ls-files gave an unexpected
reply or git cat-file gave an unexpected reply, which names the step, and missing, not a
blob, or unexpected reply for a blob that cannot be read; never a diagnostic of git, the
message of an exception, the error text of the system, or the path of the repository or of
git. A failure of a git call names no path;
a blob that cannot be read is named as every failure names its file. So no failure
line copies an address that the scan catches, in a file or in a path name, or that such
environment text holds.

Spellings that the scan catches, a closed set: outside the exemptions and the allowlisted
lines, the scan catches an address when, and only when, its text holds all 4 of these parts,
in any letter case: a local part of 1 or more ASCII letters, digits, dots, underscores,
percent signs, plus signs, or hyphens; right after it, the ASCII at sign itself, the 1 byte
0x40; right after that, a domain run of ASCII letters, digits, dots, or hyphens; and in that
run, a dot with at least 1 byte of the run before it and 2 or more ASCII letters right after
it. Every other spelling of an address passes, whatever its encoding or inserted character.
Examples only, not a complete list, of other spellings that pass where they leave those 4
parts incomplete: an address split across lines; an address assembled by code; an address
written with the word at; an at sign outside ASCII, the fullwidth or the small commercial at
sign; an at sign written as an HTML character reference, decimal, hexadecimal, or named; a
percent-encoded at sign; an at sign written as a backslash escape; an at sign written as
quoted-printable; a space, a tab, a carriage return, a less-than sign, or a zero-width space
right after the at sign; a local part that ends in a letter outside ASCII, a tilde, an
exclamation mark, or an apostrophe; a quoted local part; a domain written with letters
outside ASCII; a domain written as a literal in square brackets; an underscore in the
domain; a zero-width space inside the domain; a soft hyphen inside the domain; a zero-width
joiner, a zero-width non-joiner, a word joiner, or a byte order mark inside the domain; a
dot of the domain written as an HTML character reference, decimal, hexadecimal, or named; a
percent-encoded dot of the domain; a dot of the domain written as a backslash escape; a dot
of the domain written as quoted-printable; a dot of the domain written as the word dot, bare
or in square brackets; a fullwidth or an ideographic full stop in place of a dot of the
domain; and a space before a dot of the domain. The suite pins each of the 4 parts and each
example with its own subtest, named with the words of these lists, and 1 case of the suite
fails when the lists in its own docstring and the names of those subtests differ.

Residual: the scan catches the email class only, and within it only the closed set of
spellings above. A seat label, a bare account handle, or a numeric account identifier
passes it, because a committed pattern that names a real label would itself publish the
label; those forms rest on this rule, on the standing line that every QA and drafting brief
carries, and on any scan the maintainer keeps outside the repository. An untracked file, the
file that a tracked symbolic link points to, and the content of a submodule are not read; a
tracked symbolic link is scanned only by its own target text. The scan reads what the index
holds, so an edit of a tracked file that is not staged, and each stage of an unmerged entry
but the highest that the index holds, are not read either: an address in either passes a
local run, while CI checks out a clean commit and is not affected. A file kept outside git, for
example by Git LFS, whose blob is a pointer, is scanned only as its stored pointer, so an
address in the file that the pointer names passes. An address
inside compressed or encoded binary content passes, since the scan neither decompresses nor
decodes, unless that content holds the address as it is; surfaces that are not files in
this tree, such as a pull request title, description, or comment, are not reached by the
scan, and `tools/check-pr-text.py` carries no identifier pattern today. The suite pins each
of the 3 forms in this list that name no address with its own subtest, named for the form,
compressed or encoded content with its own case, which has 1 subtest for each compression or encoding, and each place in this list that is not
read with its own case; a surface that is not a file in this tree is outside its input, so
no case pins it. The digest of a
match or of a path name lets a reader who already holds a guess of the address confirm the
guess, though it does not reveal the address. The suite holds a path name back only from its
own output, and the scan cannot keep a name out of the output of git or any other tool. On a
red run,
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
caught, since that shorter candidate is not exempt, and is reworded to a reserved domain with no
such shorter domain; and an action
pinned to a version tag in which a dot is followed directly by 2 or more letters, such as
`v1.2.3-alpha.beta.1` or `v2.0.0-rc.ab`, is caught, since a domain then ends after those
letters, unless every domain that the tag ends is exempt, as in `v1.2.3-pre.test.1`, whose
letters form a reserved last label, or `v1.0.0-rc.example.com`, while a tag whose every dot
is followed by a digit, such as `v1.2.3-rc.1`, passes.
