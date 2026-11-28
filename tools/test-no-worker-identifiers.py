#!/usr/bin/env python3
"""Check: no tracked file or path name holds a worker or other third-party email address.

The adopter-owned rule .claude/rules/external/no-worker-identifiers.md bars any worker email
address, account identifier, seat label, or other third-party identifier from every public or
potentially public surface of this repository. This suite enforces the email class of that rule
on the stored blob of every file that git ls-files --stage lists at the repository root, and on
the name of every path it lists, the vendored trees .aiqt/, .baseline/, plugin/,
.claude/rules/aiqt/, and .claude/rules/security/ included. A pack update that imports a
third-party address therefore fails here and needs a maintainer decision; the vendored files are
never edited to pass.

Input. The content of each entry is read from the stored blob that the index names, never from
the working copy: git ls-files --stage gives the mode and the object name of each entry, and 1
call of git cat-file --batch, with replace objects off, gives the raw bytes of those blobs. So no
attribute, filter, or encoding, such as a working-tree-encoding of UTF-16LE, and no state of the
working copy, such as a file that is changed, removed, or replaced by a folder, changes what is
scanned: each file is scanned as the bytes that git stores and publishes. A tracked symbolic
link, mode 120000, is scanned by its own target text, the blob that git stores for it, never by
the file that it points to. The object of a submodule, mode 160000, is a commit of another
repository and is not read.

Candidates, read from the raw bytes of each blob, and of each path name, by candidates(). The
scan visits every at sign, so no candidate can hide another. Around each at sign it takes the
local part, the longest run of ASCII letters, digits, and the 5 characters . _ % + - that ends
right before it, and the domain run, the longest run of ASCII letters, digits, dots, and
hyphens that starts right after it; any other byte ends a run. Neither run holds an at sign, so
the domain run of 1 at sign can be the local part of the next, and both are read. Each dot of
the domain run that has at least 1 byte of the run before it and 2 or more ASCII letters right
after it ends a domain after those letters, and each such domain gives a candidate: the local
part, the at sign, and that domain. So a reserved name at the end of a longer domain run cannot
hide the candidate that stops before it. An at sign whose local part is empty, because the byte
right before it is not 1 of those named for the local part or it starts the data, gives no
candidate, and neither does 1 whose domain run ends no domain. Reading bytes keeps every tracked
blob in scope, images included, with no decode failure.

Work. Each byte is read a bounded number of times. The searches for an at sign, for a dot, and
for the line feeds that give the line number and the line of a hit each read only from where
the previous search of their kind stopped; each byte lies in at most 1 local part and 1 domain
run, and the letters after a dot are read once more to end a domain. Each candidate is tested
with slices no longer than its last label or an exempt name, and each hit is digested once,
over its longest candidate that is not exempt, which lies inside its local part and domain run.
So the work grows linearly with the size of a file, and text that holds no at sign costs 1
search for it.

The alphabetic last label keeps out text such as an action pinned to a plain version tag, whose
last label starts with a digit, or to a 40-character commit, whose domain part holds no dot.

Exemptions. 2 exemptions, each tested on a candidate folded to lower case, so each holds in any
letter case:

1. The candidate is exactly the maintainer's own email address, MAINTAINER. This covers the
   security contact in site/.well-known/security.txt, the plugin metadata, the security-txt
   checker and its tests, and the mixed-case form in the vendored specification.
2. The domain of the candidate is reserved for documentation: its last label is invalid, test,
   or example (RESERVED_LAST_LABELS), or it is, or ends with a dot and then, example.com,
   example.org, or example.net (RESERVED_DOMAINS).

An at sign passes only when every candidate that the scan reads at it is exempt, under either
exemption, or when it lies in a file on a line that the reviewed exact-line allowlist holds for
that file. So, off such a line, an address passes only when each shorter domain that it holds,
ending after 2 or more letters that follow a dot, gives an exempt candidate as well. An at sign
with 1 or more candidates that are not exempt is a hit, reported 1 time. A hit passes when its
line is in ALLOWLIST, the reviewed set of exact line texts, by file, for email-shaped text that
is no address. An allowlist entry that is not the exact text of a line of its file that holds a
hit is a failure, so the allowlist cannot silently go stale.

Path names. The whole name of every path that git lists, the names of its folders included, is
scanned as its raw bytes in the same way, with no allowlist, for a tracked symbolic link and a
submodule as for a file. Each name is read unquoted from git ls-files -z, so a name that holds a
space, a tab, a line feed, a double quote, a backslash, or a byte outside ASCII, valid UTF-8 or
not, is read and scanned as it is. A path name that holds a hit is never written: each hit in it
is a failure that names the path as path sha256 and the first 16 hexadecimal digits of the
sha256 of the path name, with the digest of the hit, and every other failure for that path (a
hit in its content, an unreadable blob, or a stale allowlist entry) names the path by that same
digest.

Report. What each failure names: a hit in the content of a file, or in the stored target text of
a tracked symbolic link, names 3 items, the file or link, the line number, which is 1 more than
the number of line feeds before the hit, and the first 16 hexadecimal digits of the sha256 of
the hit, the longest candidate of its at sign that is not exempt, and it is the only failure
that names a line; a hit in a path name names the path and
the digest of the hit, and no line; a stale allowlist entry names its file, its position, and
the same digest of its text, and no line; and the fail-closed failures below name no line and no
digest of a hit: a blob that cannot be read names its path and a fixed category, and a git call
that fails, that cannot be started, that lists no path, or whose listing is not as requested
names no path either, only a fixed category. No failure holds the text of a hit or of its line,
and each names a path whose name holds a hit only by the digest of that name, so this suite
copies no address that it catches, in a file or in a path name, into the CI log. Any other path
is written as printable_path() gives it: each character that is not printable, such as a line
feed, a carriage return, or the escape byte that starts a terminal escape sequence, and each
backslash, is written as a backslash escape, so each failure is 1 line of printable text and no
control character of a path name reaches the CI log. On a red run, the tree case prints every
failure in full, 1 to a line after a count, and never through a list comparison, which unittest
shortens when it is long, so no failure is dropped from the CI log.

It fails closed: a git ls-files that fails, that cannot be started, that lists no path, or whose
reply is not a listing as requested, a git cat-file that fails or that cannot be started, and a
listed entry whose stored blob cannot be read, are failures, never a skip. Each such failure is
a fixed category with only an exit code, a symbol from a fixed table, a fixed word, or the name
of a type, never text from the environment: a git ls-files or a git cat-file that fails gives
its exit code; a git that cannot be started gives the errno name of the error, such as ENOENT,
or, when the error carries no errno that the errno module names, the name of the type of the
error; a blob that cannot be read gives missing, when git holds no such object, not a blob, when
the object is of another type, or unexpected reply, when git cat-file does not answer for that
object as requested, a header whose size has more digits than Python will convert to an integer
included; a git ls-files whose reply is not a listing as requested, such as 1 with an entry of
too few fields, a byte outside ASCII in a field, an empty field, or a stray separator, gives
unexpected reply; an empty listing gives no detail. Each parse of a reply of git, the listing
and the blobs alike, gives a fixed word on any reply that it cannot read and never raises an
error, so a malformed reply ends the scan in 1 of these failure lines, never in a traceback. So
no failure line holds a diagnostic of git, a message of an exception, an error text of the
system, or the path of the repository root or of the git program, whatever address such text
holds. An unreadable blob is named by its path, or by the digest of its path name when that name
holds a hit.

Each caught example in the self-checks below is assembled at run time from parts, so this file's
own source holds no text that candidates() takes as a candidate and the suite needs no entry for
itself. The expected digests of the self-checks come from 3 sources, none of them digest(): a
known-answer literal, the first 16 hexadecimal digits of the sha256 of the bytes abc, which the
digest case compares with both sha256_prefix() and digest(); sha256_prefix(), the
expected-digest helper, which takes the first 16 hexadecimal digits of hashlib.sha256 and gives
every other expected digest but 1; and that 1, which the digest case computes in its own body
with hashlib.sha256. So a change to digest() or to its length, such as 1 that copies the hit in
hexadecimal, fails a case.

Spellings that the scan catches, a closed set: outside the exemptions and the allowlisted lines,
the scan catches an address when, and only when, its text holds all 4 of these parts, in any
letter case: a local part of 1 or more ASCII letters, digits, dots, underscores, percent signs,
plus signs, or hyphens; right after it, the ASCII at sign itself, the 1 byte 0x40; right after
that, a domain run of ASCII letters, digits, dots, or hyphens; and in that run, a dot with at
least 1 byte of the run before it and 2 or more ASCII letters right after it. Every other
spelling of an address passes, whatever its encoding or inserted character. Examples only, not
a complete list, of other spellings that pass where they leave those 4 parts incomplete: an
address split across lines; an address assembled by code; an address written with the word at;
an at sign outside ASCII, the fullwidth or the small commercial at sign; an at sign written as
an HTML character reference, decimal, hexadecimal, or named; a percent-encoded at sign; an at
sign written as a backslash escape; an at sign written as quoted-printable; a space, a tab, a
carriage return, a less-than sign, or a zero-width space right after the at sign; a local part
that ends in a letter outside ASCII, a tilde, an exclamation mark, or an apostrophe; a quoted
local part; a domain written with letters outside ASCII; a domain written as a literal in
square brackets; an underscore in the domain; a zero-width space inside the domain; a soft
hyphen inside the domain; a zero-width joiner, a zero-width non-joiner, a word joiner, or a
byte order mark inside the domain; a dot of the domain written as an HTML character reference,
decimal, hexadecimal, or named; a percent-encoded dot of the domain; a dot of the domain
written as a backslash escape; a dot of the domain written as quoted-printable; a dot of the
domain written as the word dot, bare or in square brackets; a fullwidth or an ideographic full
stop in place of a dot of the domain; and a space before a dot of the domain. Each of the 4
parts is pinned by its own subtest of test_each_caught_spelling_is_caught, and each example by
its own subtest of test_each_example_of_a_spelling_that_passes_gives_no_candidate, each named
with the words of the lists above, and test_this_docstring_states_each_caught_spelling_and_example
fails when either list above and the names of those subtests differ.

Residual: the scan catches the email class only, and within it only the closed set of spellings
above. A seat label, a bare account handle, or a numeric account identifier passes it, because a
committed pattern that names a real label would itself publish the label; those forms rest on
the rule, on the standing line that every QA and drafting brief carries, and on any scan the
maintainer keeps outside the repository. An untracked file, the file that a tracked symbolic
link points to, and the content of a submodule are not read; a tracked symbolic link is scanned
only by its own target text. The scan reads what the index holds, so an edit of a tracked file
that is not staged, and each stage of an unmerged entry but the highest that the index holds,
are not read either: an address in either passes a local run, while CI checks out a clean commit
and is not affected. A file kept outside git, for example by Git LFS, whose blob is a
pointer, is scanned only as its stored pointer, so an address in the file that the pointer
names passes. An address inside compressed or encoded binary content passes, since the scan
neither decompresses nor decodes, unless that content holds the address as it is; a surface
that is not a file in this tree, such as a pull request title, description, or comment, is not
reached, and tools/check-pr-text.py carries no identifier pattern today. The digest of a hit or
of a path name lets a reader who already holds a guess of the address confirm the guess; it does
not reveal the address. The suite holds a path name back only from its own output, and the scan
cannot keep a name out of the output of git or any other tool. On a red run,
unittest also prints a traceback for each failed case, which holds the absolute path of this
file in the checkout, and a failed self-check can
print the values that it compared, the path of its temporary folder among them, so a checkout
path or a temporary folder path that holds an address reaches the CI log. A label that leaked
into the history of an older pull request and was removed later is held for the maintainer and
is out of scope for this rule's enforcement. Each of the 3 forms that name no address, the seat
label, the bare account handle, and the numeric account identifier, is pinned by its own
subtest, named for the form, of test_each_residual_text_form_gives_no_candidate, and compressed
or encoded content is pinned by its own case,
test_compressed_or_encoded_content_gives_no_candidate, with 1 subtest for each compression or
encoding. Each place that this residual names as not read is pinned by its own case:
test_an_untracked_file_is_not_read,
test_the_file_that_a_tracked_symbolic_link_points_to_is_not_read,
test_the_content_of_a_submodule_is_not_read,
test_an_edit_of_a_tracked_file_that_is_not_staged_is_not_read,
test_each_stage_of_an_unmerged_entry_but_the_highest_is_not_read, and
test_a_file_kept_outside_git_is_scanned_only_as_its_stored_pointer. A surface that is not a file
in this tree is outside the input of the suite, so no case pins it.

Accepted false failures: a legitimate new third-party address is caught and needs a maintainer
decision; an email-shaped text that is no address is caught and is reworded to a reserved domain,
or is added to ALLOWLIST after review; a fixture address at a reserved domain whose domain run
also ends a shorter domain that is not reserved, such as 1 at mail.corp.example.com or 1
that appends the label example to an ordinary domain, is caught, since that shorter candidate
is not exempt, and is reworded to a reserved domain with no such shorter domain; and an action
pinned to a version tag in which a dot is followed directly by 2 or more letters, such as
v1.2.3-alpha.beta.1 or v2.0.0-rc.ab, is caught, since a domain then ends after those letters,
unless every domain that the tag ends is exempt, as in v1.2.3-pre.test.1, whose letters form a
reserved last label, or v1.0.0-rc.example.com, while a tag whose every dot is followed by a
digit, such as v1.2.3-rc.1, passes.
"""
import base64
import bz2
import errno
import gzip
import hashlib
import io
import lzma
import os
import subprocess
import tempfile
import time
import unittest
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

LETTER_BYTES = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
DOMAIN_BYTES = LETTER_BYTES | frozenset(b"0123456789.-")
LOCAL_BYTES = DOMAIN_BYTES | frozenset(b"_%+")
# The maintainer's own address, the only real address that this repository may hold.
MAINTAINER = "jeff" + "@" + "posluns.ca"
RESERVED_LAST_LABELS = ("invalid", "test", "example")
RESERVED_DOMAINS = ("example.com", "example.org", "example.net")
# The mode of a submodule in the output of git ls-files --stage, whose object is a commit of
# another repository and is not read. A symbolic link, mode 120000, is read: its stored blob is
# its own target text.
UNREAD_MODES = ("160000",)
# The bytes that each field of an entry of git ls-files --stage may hold: a mode of 6 octal
# digits, an object name of 40 or 64 lowercase hexadecimal digits, and a stage of 1 digit.
OCTAL_BYTES = frozenset(b"01234567")
HEX_BYTES = frozenset(b"0123456789abcdef")
STAGES = (b"0", b"1", b"2", b"3")
GIT = "git"
DIGEST_DIGITS = 16

# Reviewed lines whose email-shaped text is no worker or third-party address, each the exact text
# of the line: a URL-userinfo fixture at the project's own domain, which the release-link tests
# use as a redirect form on this site's origin that the checker must refuse. Its host must stay
# this site's origin to keep that meaning, so it cannot move to a reserved documentation domain.
ALLOWLIST = {
    "tools/test-release-links.py": (
        "        (\"/r https://" + "user" + "@" + "cleanlanguage.ai/downloads/a.md 301\", \"form\"),",
    ),
}

MAINTAINER_BYTES = MAINTAINER.encode("ascii")
RESERVED_LAST_LABEL_BYTES = tuple(label.encode("ascii") for label in RESERVED_LAST_LABELS)
RESERVED_DOMAIN_BYTES = tuple(name.encode("ascii") for name in RESERVED_DOMAINS)


def digest(data):
    """The first DIGEST_DIGITS hexadecimal digits of the sha256 of the bytes data."""
    return hashlib.sha256(data).hexdigest()[:DIGEST_DIGITS]


def domain_ends(data, begin, stop):
    """(dot, end) for each domain that the domain run data[begin:stop] ends, in ascending order.

    A domain ends after the letters that follow a dot when the dot has at least 1 byte of the run
    before it and 2 or more ASCII letters right after it.
    """
    ends = []
    dot = data.find(b".", begin + 1, stop)
    while dot >= 0:
        end = dot + 1
        while end < stop and data[end] in LETTER_BYTES:
            end += 1
        if end - dot > 2:
            ends.append((dot, end))
        dot = data.find(b".", end, stop)
    return ends


def candidates(data):
    """(start, at, ends) for each at sign of the bytes data that gives a candidate, in order.

    start is where its local part starts, at is the position of the at sign, and ends lists the
    (dot, end) of each domain, so each data[start:end] is a candidate.
    """
    found = []
    at = data.find(b"@")
    while at >= 0:
        start = at
        while start > 0 and data[start - 1] in LOCAL_BYTES:
            start -= 1
        stop = at + 1
        while stop < len(data) and data[stop] in DOMAIN_BYTES:
            stop += 1
        if start < at:
            ends = domain_ends(data, at + 1, stop)
            if ends:
                found.append((start, at, ends))
        at = data.find(b"@", stop)
    return found


def exempt(data, start, at, dot, end):
    """Whether the candidate data[start:end], its at sign at at and its last dot at dot, is exempt."""
    if end - start == len(MAINTAINER_BYTES) and data[start:end].lower() == MAINTAINER_BYTES:
        return True
    if data[dot + 1:end].lower() in RESERVED_LAST_LABEL_BYTES:
        return True
    size = end - at - 1
    for name in RESERVED_DOMAIN_BYTES:
        if size == len(name) and data[at + 1:end].lower() == name:
            return True
        if size > len(name) and data[end - len(name) - 1:end].lower() == b"." + name:
            return True
    return False


def hits_in(data):
    """(line number, line start, line end, digest) for each hit in the bytes data.

    The line runs from line start up to line end, its line feed or the end of data excluded, and
    the digest is that of the longest candidate of the at sign that is not exempt. Line numbers
    and lines are found from the previous hit on, so the work stays linear.
    """
    found = []
    number = 1
    counted = 0
    line_start = 0
    line_end = -1
    for start, at, ends in candidates(data):
        open_ends = [end for dot, end in ends if not exempt(data, start, at, dot, end)]
        if not open_ends:
            continue
        number += data.count(b"\n", counted, start)
        counted = start
        if start > line_end:
            line_start = data.rfind(b"\n", max(line_end, 0), start) + 1
            line_end = data.find(b"\n", start)
            if line_end < 0:
                line_end = len(data)
        found.append((number, line_start, line_end, digest(data[start:open_ends[-1]])))
    return found


def error_category(error):
    """The fixed category of the OSError error: its errno name, or the name of its type.

    The errno name, such as ENOENT, comes from the fixed table of the errno module; an error whose
    errno that table does not name gives the name of its type. Neither holds text from the
    environment, so no message, path, or error text of the system that the error carries is used.
    """
    name = errno.errorcode.get(error.errno) if isinstance(error.errno, int) else None
    return name or type(error).__name__


def tracked_files(root, git=GIT):
    """(repository-relative path, mode, object name) for each entry of git ls-files --stage.

    The object name is that of the stored blob that the index names for the path. Each path
    appears 1 time, in sorted order. A reply that is not a listing as requested gives the fixed
    word unexpected reply in place of the list, never an error: a listing that no NUL ends, an
    empty entry, an entry with no tab or with an empty path, an entry whose part before its
    first tab is not 3 fields that 1 space each separates, a mode that is not 6 octal digits, an
    object name that is not 40 or 64 lowercase hexadecimal digits, a stage other than 0, 1, 2,
    or 3, or a path name that os.fsdecode() cannot decode. So an entry with too few or too many
    fields, an empty field, a byte outside ASCII in a field, or a stray separator gives
    unexpected reply. A git ls-files that fails raises subprocess.CalledProcessError, and a git
    that cannot be started raises OSError.
    """
    listed = subprocess.run([git, "-C", str(root), "ls-files", "--stage", "-z"],
                            capture_output=True, check=True, stdin=subprocess.DEVNULL).stdout
    if not listed:
        return []
    if not listed.endswith(b"\0"):
        return "unexpected reply"
    entries = {}
    for entry in listed[:-1].split(b"\0"):
        info, tab, path = entry.partition(b"\t")
        fields = info.split(b" ")
        if not tab or not path or len(fields) != 3:
            return "unexpected reply"
        mode, name, stage = fields
        if (len(mode) != 6 or not set(mode) <= OCTAL_BYTES or len(name) not in (40, 64)
                or not set(name) <= HEX_BYTES or stage not in STAGES):
            return "unexpected reply"
        try:
            rel = os.fsdecode(path)
        except ValueError:
            return "unexpected reply"
        entries[rel] = (mode.decode("ascii"), name.decode("ascii"))
    return [(rel, mode, name) for rel, (mode, name) in sorted(entries.items())]


def stored_blobs(root, names, git=GIT):
    """{object name: the raw bytes of its stored blob, or a fixed category} for each of names.

    1 call of git cat-file --batch reads every object from the object store at root, with
    replace objects off, so no attribute, filter, encoding, or state of the working copy changes
    the bytes. An object that cannot be read as a blob gives 1 fixed word in place of its bytes:
    missing, when git reports no such object; not a blob, when the object is of another type; or
    unexpected reply, when the reply does not answer for that object as requested. A header of 2
    fields other than missing gives unexpected reply for that object only, and the read goes on
    to the next object. Any other reply that does not answer stops the read, so that object and
    every later object give unexpected reply: a reply that ends before the object is answered, a
    header that names another object or that has too many or too few fields, a size that is no
    number, a size with more digits than Python will convert to an integer, 4300 by default, or a
    body that is cut short or that no line feed ends. A git cat-file that fails raises
    subprocess.CalledProcessError, and a git that cannot be started raises OSError.
    """
    request = b"".join(name.encode("ascii") + b"\n" for name in names)
    reply = subprocess.run([git, "--no-replace-objects", "-C", str(root), "cat-file", "--batch"],
                           input=request, capture_output=True, check=True).stdout
    blobs = {}
    position = 0
    for name in names:
        header_end = reply.find(b"\n", position)
        header = reply[position:header_end].split(b" ") if header_end >= 0 else []
        if header[:1] != [name.encode("ascii")] or len(header) not in (2, 3):
            break
        if len(header) == 2:
            blobs[name] = "missing" if header[1] == b"missing" else "unexpected reply"
            position = header_end + 1
            continue
        try:
            size = int(header[2]) if header[2].isdigit() else -1
        except ValueError:
            size = -1
        body_end = header_end + 1 + size
        if size < 0 or reply[body_end:body_end + 1] != b"\n":
            break
        blobs[name] = reply[header_end + 1:body_end] if header[1] == b"blob" else "not a blob"
        position = body_end + 1
    for name in names:
        blobs.setdefault(name, "unexpected reply")
    return blobs


def printable_path(rel):
    """The path rel as 1 line of printable text, each character that is not printable escaped.

    A character that str.isprintable() rejects, such as a line feed, a carriage return, the
    escape byte that starts a terminal escape sequence, or the 8-bit control sequence introducer,
    and each backslash, is written as a backslash escape: \\xHH for a character below 0x80 and for
    a byte of the name that is not valid UTF-8, which os.fsdecode() gives as a surrogate, and
    \\uHHHH or \\UHHHHHHHH with its code point for any other. So DEL, 0x7f, is written as \\x7f.
    Every other character, a printable character outside ASCII included, stays as it is. Every
    backslash of the result starts an escape, so no 2 path names give the same text.
    """
    parts = []
    for char in rel:
        value = ord(char)
        if char.isprintable() and char != "\\":
            parts.append(char)
        elif value < 0x80:
            parts.append("\\x{:02x}".format(value))
        elif 0xDC80 <= value <= 0xDCFF:
            parts.append("\\x{:02x}".format(value - 0xDC00))
        elif value <= 0xFFFF:
            parts.append("\\u{:04x}".format(value))
        else:
            parts.append("\\U{:08x}".format(value))
    return "".join(parts)


def path_label(rel):
    """The name of rel in a failure: path sha256 and the digest of its name, or printable_path(rel).

    The digest stands for the path whenever its name holds a hit, so that no failure copies it;
    any other path is written by printable_path(), so that no failure holds a control character.
    """
    name = os.fsencode(rel)
    if hits_in(name):
        return "path sha256 " + digest(name)
    return printable_path(rel)


def scan(root, allowlist, git=GIT):
    """(failures, number of blobs read) for the stored blobs and path names of the entries at root.

    The content of each entry is its stored blob, from stored_blobs(), never the working copy. A
    hit in a file passes on a line that allowlist holds for that file. A failure is a line of
    text: a hit in a path name as a digest of the path and of the hit, a hit in a file as
    path:line: and a digest, a blob that cannot be read with its fixed category, a stale
    allowlist entry, a git ls-files or a git cat-file that fails with its exit code, a git that
    cannot be started with the category of its error, a git ls-files that lists no path, or a git
    ls-files whose reply is not a listing as requested. No failure holds the text of a hit or of
    its line, a path whose name holds a hit is named only by the digest of its name, any other
    path is written by printable_path(), so each failure is 1 line with no control character, and
    no failure holds a diagnostic of git, the message of an exception, the error text of the
    system, or the path of root or of git.
    """
    try:
        entries = tracked_files(root, git)
    except subprocess.CalledProcessError as error:
        return ["git ls-files failed: exit {}".format(error.returncode)], 0
    except OSError as error:
        return ["git ls-files failed: git could not be started: {}".format(error_category(error))], 0
    if isinstance(entries, str):
        return ["git ls-files gave an unexpected reply"], 0
    if not entries:
        return ["git ls-files listed no file"], 0
    names = sorted({name for _, mode, name in entries if mode not in UNREAD_MODES})
    try:
        blobs = stored_blobs(root, names, git)
    except subprocess.CalledProcessError as error:
        return ["git cat-file failed: exit {}".format(error.returncode)], 0
    except OSError as error:
        return ["git cat-file failed: git could not be started: {}".format(error_category(error))], 0
    failures = []
    read = 0
    used = set()
    for rel, mode, object_name in entries:
        name = os.fsencode(rel)
        name_hits = hits_in(name)
        label = "path sha256 " + digest(name) if name_hits else printable_path(rel)
        for _, _, _, hit in name_hits:
            failures.append("{}: email-shaped text in the path name, sha256 {}".format(label, hit))
        if mode in UNREAD_MODES:
            continue
        data = blobs[object_name]
        if isinstance(data, str):
            failures.append("{}: unreadable: {}".format(label, data))
            continue
        read += 1
        allowed = {line.encode("utf-8") for line in allowlist.get(rel, ())}
        seen_start = None
        for number, line_start, line_end, hit in hits_in(data):
            if allowed:
                if line_start != seen_start:
                    seen_start = line_start
                    line = data[line_start:line_end]
                if line in allowed:
                    used.add((rel, line))
                    continue
            failures.append("{}:{}: email-shaped text, sha256 {}".format(label, number, hit))
    for rel, lines in sorted(allowlist.items()):
        rel_label = path_label(rel)
        for position, line in enumerate(lines, 1):
            if (rel, line.encode("utf-8")) not in used:
                failures.append("{}: stale allowlist entry {}, no line that holds a hit, sha256 {}".format(
                    rel_label, position, digest(line.encode("utf-8"))))
    return failures, read


def caught(local, domain):
    """An address assembled from its parts, so that this source holds no matchable text."""
    return local + "@" + domain


def sha256_prefix(data):
    """The expected digest of the bytes data, from hashlib directly and never from digest().

    The cases build their expected digests with this, apart from the known-answer literal and
    the 1 direct hashlib.sha256 check of the digest case, so a change to digest(), to
    DIGEST_DIGITS, or to what a failure names fails a case rather than changing the expected text
    with it.
    """
    return hashlib.sha256(data).hexdigest()[:16]


class PatternSelfCheck(unittest.TestCase):
    """The candidates and each exemption, pinned with examples assembled at run time.

    Each exemption case first asserts that the text gives the candidate it exempts.
    """

    PLACEHOLDER_DOMAIN = "placeholder-mail" + "." + "com"
    # The bytes that the docstring names for each run, spelt out here apart from LOCAL_BYTES and
    # DOMAIN_BYTES, so that a change to either set fails a case.
    DOCUMENTED_DOMAIN_BYTES = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                                        b"0123456789.-")
    DOCUMENTED_LOCAL_BYTES = DOCUMENTED_DOMAIN_BYTES | frozenset(b"._%+-")

    def byte_texts(self, data):
        return [data[start:end] for start, _, ends in candidates(data) for _, end in ends]

    def texts(self, text):
        return [data.decode("ascii") for data in self.byte_texts(text.encode("ascii"))]

    def digests(self, text):
        return [hit for _, _, _, hit in hits_in(text.encode("ascii"))]

    def test_a_third_party_address_is_caught(self):
        address = caught("worker-label-example", self.PLACEHOLDER_DOMAIN)
        self.assertEqual(self.texts("contact " + address + " today"), [address])
        line = "by " + address
        self.assertEqual(hits_in(("x\n" + line + "\n").encode("ascii")),
                         [(2, 2, 2 + len(line), sha256_prefix(address.encode("ascii")))])

    def test_the_digest_is_the_first_16_hexadecimal_digits_of_the_sha256(self):
        # A known value pins hashlib and the length apart from both helpers; then the digest of a
        # hit is computed in the case with hashlib directly.
        self.assertEqual(sha256_prefix(b"abc"), "ba7816bf8f01cfea")
        self.assertEqual(digest(b"abc"), "ba7816bf8f01cfea")
        address = caught("worker-label-example", self.PLACEHOLDER_DOMAIN).encode("ascii")
        self.assertEqual(self.digests(address.decode("ascii")), [hashlib.sha256(address).hexdigest()[:16]])

    def test_each_residual_text_form_gives_no_candidate(self):
        """Each of the 3 forms that name no address and that the residual states pass gives no candidate.

        Each subtest is named for its form and holds every text of that form, each assembled at
        run time; it fails when any of those texts gives a candidate. The control, an address
        written plainly, is caught.
        """
        local = "worker-label-example"
        domain = self.PLACEHOLDER_DOMAIN
        self.assertEqual(len(hits_in(caught(local, domain).encode("ascii"))), 1)
        forms = (
            ("a seat label", ("seat-label-example",)),
            ("a bare account handle", (local, "@" + local)),
            ("a numeric account identifier", ("0123456789" + "01",)),
        )
        for form, texts in forms:
            with self.subTest(form=form):
                self.assertEqual([candidates(text.encode("utf-8")) for text in texts],
                                 [[] for _ in texts])

    def caught_spellings(self):
        """(part, ((text, longest candidate), ...)) for each of the 4 parts of the caught spellings.

        Each part is named with the words of the module docstring, and each text, assembled at run
        time, holds all 4 parts and varies the part of its subtest over what the docstring names
        for it, in upper and lower case.
        """
        domain = self.PLACEHOLDER_DOMAIN
        plain = caught("worker-label-example", domain)
        whole = [(caught(local, domain), caught(local, domain))
                 for local in ("worker", "WORKER", "w", "worker2", "0123", "w.orker", "w_orker",
                               "w%orker", "w+orker", "w-orker")]
        runs = [(caught("worker", name), caught("worker", name))
                for name in ("placeholdermail" + "." + "com", "PLACEHOLDER-MAIL" + "." + "COM",
                             "mail2" + "." + "com", "mail" + "." + "placeholder-mail" + "." + "com",
                             "placeholder-mail" + "." + "com")]
        return (
            ("a local part of 1 or more ASCII letters, digits, dots, underscores, percent signs, plus"
             " signs, or hyphens", whole),
            ("right after it, the ASCII at sign itself, the 1 byte 0x40", [(plain, plain)]),
            ("right after that, a domain run of ASCII letters, digits, dots, or hyphens", runs),
            ("in that run, a dot with at least 1 byte of the run before it and 2 or more ASCII letters"
             " right after it", [
                 (caught("worker", "h" + "." + "co"), caught("worker", "h" + "." + "co")),
                 (caught("worker", "host" + "." + "com1"), caught("worker", "host" + "." + "com")),
                 (caught("worker", "host" + "." + "co-uk"), caught("worker", "host" + "." + "co"))]),
        )

    def test_each_caught_spelling_is_caught(self):
        """Each of the 4 parts of the caught spellings, in its own subtest: every text is caught.

        Each text gives 1 hit, whose longest candidate is the expected address and whose digest
        is that of the address, so a change to what the scan reads for a part fails its subtest.
        """
        for part, texts in self.caught_spellings():
            with self.subTest(part=part):
                for text, address in texts:
                    self.assertEqual(text.encode("ascii")[text.index("@")], 0x40)
                    self.assertEqual(self.texts(text)[-1], address)
                    self.assertEqual(self.digests(text), [sha256_prefix(address.encode("ascii"))])

    def passing_spellings(self):
        """(form, texts) for each example of a spelling that passes, named as the docstring names it.

        Each text is assembled at run time.
        """
        local = "worker-label-example"
        domain = self.PLACEHOLDER_DOMAIN
        return (
            ("an address split across lines", (
                local + "\n" + "@" + domain, caught(local, "\n" + domain),
                caught(local, "placeholder-mail" + "\n" + "." + "com"))),
            ("an address assembled by code", (
                "\"" + local + "\" + \"" + "@" + "\" + \"" + domain + "\"",)),
            ("an address written with the word at", (
                local + " at " + domain, local + " [at] " + domain, local + " (at) " + domain)),
            ("an at sign outside ASCII, the fullwidth or the small commercial at sign", (
                local + chr(0xFF20) + domain, local + chr(0xFE6B) + domain)),
            ("an at sign written as an HTML character reference, decimal, hexadecimal, or named", (
                local + "&#" + "64;" + domain, local + "&#x" + "40;" + domain,
                local + "&com" + "mat;" + domain)),
            ("a percent-encoded at sign", (local + "%" + "40" + domain,)),
            ("an at sign written as a backslash escape", (
                local + "\\u" + "0040" + domain, local + "\\x" + "40" + domain,
                local + "\\" + "100" + domain)),
            ("an at sign written as quoted-printable", (local + "=" + "40" + domain,)),
            ("a space, a tab, a carriage return, a less-than sign, or a zero-width space right after"
             " the at sign", (
                local + "@" + " " + domain, local + "@" + "\t" + domain, local + "@" + "\r" + domain,
                local + "@" + "<" + domain, local + "@" + chr(0x200B) + domain)),
            ("a local part that ends in a letter outside ASCII, a tilde, an exclamation mark, or an"
             " apostrophe", (
                 "jos" + chr(233) + "@" + domain, "a~" + "@" + domain, "a!" + "@" + domain,
                 "a'" + "@" + domain)),
            ("a quoted local part", (
                "\"" + local + "\"" + "@" + domain, "\"worker label\"" + "@" + domain)),
            ("a domain written with letters outside ASCII", (
                caught(local, "plac" + chr(233) + "holder" + "." + "com"),
                caught(local, chr(252) + "ber" + "." + "com"))),
            ("a domain written as a literal in square brackets", (caught(local, "[192.0.2.1]"),)),
            ("an underscore in the domain", (caught(local, "placeholder_mail" + "." + "com"),)),
            ("a zero-width space inside the domain", (
                caught(local, "placeholder-mail" + chr(0x200B) + "." + "com"),
                caught(local, "place" + chr(0x200B) + "holder-mail" + "." + "com"))),
            ("a soft hyphen inside the domain", (
                caught(local, "placeholder-mail" + chr(0xAD) + "." + "com"),
                caught(local, "place" + chr(0xAD) + "holder-mail" + "." + "com"))),
            ("a zero-width joiner, a zero-width non-joiner, a word joiner, or a byte order mark inside"
             " the domain", tuple(
                text for mark in (chr(0x200D), chr(0x200C), chr(0x2060), chr(0xFEFF))
                for text in (caught(local, "placeholder-mail" + mark + "." + "com"),
                             caught(local, "place" + mark + "holder-mail" + "." + "com")))),
            ("a dot of the domain written as an HTML character reference, decimal, hexadecimal, or"
             " named", (
                caught(local, "placeholder-mail" + "&#" + "46;" + "com"),
                caught(local, "placeholder-mail" + "&#x" + "2E;" + "com"),
                caught(local, "placeholder-mail" + "&per" + "iod;" + "com"))),
            ("a percent-encoded dot of the domain", (
                caught(local, "placeholder-mail" + "%" + "2E" + "com"),)),
            ("a dot of the domain written as a backslash escape", (
                caught(local, "placeholder-mail" + "\\x" + "2e" + "com"),
                caught(local, "placeholder-mail" + "\\u" + "002e" + "com"),
                caught(local, "placeholder-mail" + "\\" + "056" + "com"))),
            ("a dot of the domain written as quoted-printable", (
                caught(local, "placeholder-mail" + "=" + "2E" + "com"),)),
            ("a dot of the domain written as the word dot, bare or in square brackets", (
                caught(local, "placeholder-mail" + " dot " + "com"),
                caught(local, "placeholder-mail" + "[dot]" + "com"))),
            ("a fullwidth or an ideographic full stop in place of a dot of the domain", (
                caught(local, "placeholder-mail" + chr(0xFF0E) + "com"),
                caught(local, "placeholder-mail" + chr(0x3002) + "com"))),
            ("a space before a dot of the domain", (
                caught(local, "placeholder-mail" + " " + "." + "com"),)),
        )

    def test_each_example_of_a_spelling_that_passes_gives_no_candidate(self):
        """Each example of a spelling that passes gives no candidate, in its own subtest.

        Each subtest is named for its example, as the docstring names it, and holds every text of
        that example; it fails when any of those texts gives a candidate. The control, the same
        address written plainly, is caught.
        """
        self.assertEqual(len(hits_in(caught("worker-label-example", self.PLACEHOLDER_DOMAIN).encode("ascii"))), 1)
        for form, texts in self.passing_spellings():
            with self.subTest(form=form):
                self.assertEqual([candidates(text.encode("utf-8")) for text in texts],
                                 [[] for _ in texts])

    def stated_list(self, text, lead):
        """The items of the list in text that follows lead and ends at the next full stop.

        The text is read with each run of whitespace as 1 space, and the items are split at each
        semicolon and space, with the "and " that opens the last item removed.
        """
        flat = " ".join(text.split())
        start = flat.index(lead) + len(lead)
        items = flat[start:flat.index(".", start)].split("; ")
        if items[-1].startswith("and "):
            items[-1] = items[-1][len("and "):]
        return items

    def test_this_docstring_states_each_caught_spelling_and_example(self):
        """The module docstring names each caught part and each example as its subtest is named.

        The docstring states that every other spelling passes, and its 2 lists name, in order,
        exactly the subtests of test_each_caught_spelling_is_caught and of
        test_each_example_of_a_spelling_that_passes_gives_no_candidate, so a change to the text or
        to a subtest fails here until the other follows it.
        """
        doc = globals()["__doc__"]
        self.assertIn("Every other spelling of an address passes, whatever its encoding or inserted"
                      " character.", " ".join(doc.split()))
        self.assertEqual(self.stated_list(doc, "its text holds all 4 of these parts, in any letter case: "),
                         [part for part, _ in self.caught_spellings()])
        self.assertEqual(self.stated_list(doc, "Examples only, not a complete list, of other spellings that"
                                               " pass where they leave those 4 parts incomplete: "),
                         [form for form, _ in self.passing_spellings()])

    def test_compressed_or_encoded_content_gives_no_candidate(self):
        """An address inside compressed or encoded binary content gives no candidate.

        The set, 9 forms, 1 subtest each: zlib, gzip, bz2, and lzma compression, and base64,
        hexadecimal, UTF-16 with a byte order mark, UTF-16 big-endian with no byte order mark,
        and UTF-32 with a byte order mark encoding of 8 lines that each hold an address, named
        zlib, gzip, bz2, lzma, base64, hex, utf-16, utf-16-be, and utf-32, in that order. The
        control: those lines, before they are compressed or encoded, give 8 hits, and no form
        holds a line as it is. Content that holds the address as it is, such as a block that lzma
        stores uncompressed when it cannot shrink it, is caught; the lines repeat so that each
        compressor shrinks them.
        """
        line = ("contact " + caught("worker-label-example", self.PLACEHOLDER_DOMAIN) + "\n").encode("ascii")
        plain = line * 8
        self.assertEqual(len(hits_in(plain)), 8)
        for name, data in (("zlib", zlib.compress(plain)), ("gzip", gzip.compress(plain, mtime=0)),
                           ("bz2", bz2.compress(plain)), ("lzma", lzma.compress(plain)),
                           ("base64", base64.b64encode(plain)), ("hex", plain.hex().encode("ascii")),
                           ("utf-16", plain.decode("ascii").encode("utf-16")),
                           ("utf-16-be", plain.decode("ascii").encode("utf-16-be")),
                           ("utf-32", plain.decode("ascii").encode("utf-32"))):
            with self.subTest(form=name):
                self.assertNotIn(line, data)
                self.assertEqual(candidates(data), [])

    def test_an_exempt_candidate_hides_no_other(self):
        # A prefix, an at sign, a dotted local part that ends in a reserved label, a 2nd at sign,
        # and a non-reserved domain: the 2nd at sign gives its own candidate, which is caught.
        address = caught("w." + "example", self.PLACEHOLDER_DOMAIN)
        self.assertEqual(self.digests(address), [sha256_prefix(address.encode("ascii"))])
        masked = "p" + "@" + address
        self.assertEqual(self.texts(masked), [caught("p", "w." + "example"), address])
        self.assertEqual(self.digests(masked), [sha256_prefix(address.encode("ascii"))])
        # The maintainer's address in front of a 2nd at sign hides nothing either.
        behind = MAINTAINER + "@" + self.PLACEHOLDER_DOMAIN
        self.assertEqual(self.texts(behind), [MAINTAINER, caught("posluns.ca", self.PLACEHOLDER_DOMAIN)])
        self.assertEqual(len(self.digests(behind)), 1)
        # A reserved last label after the domain hides nothing: the shorter domain is caught.
        plain = caught("worker", self.PLACEHOLDER_DOMAIN)
        suffixed = plain + "." + "example"
        self.assertEqual(self.texts(suffixed), [plain, suffixed])
        self.assertEqual(self.digests(suffixed), [sha256_prefix(plain.encode("ascii"))])

    def test_the_maintainer_address_in_any_case_is_exempt(self):
        for text in (MAINTAINER, MAINTAINER.upper(), "Jeff" + "@" + "Posluns.ca"):
            with self.subTest(text=text):
                line = "Contact: mailto:" + text + "\n"
                self.assertEqual(self.texts(line), [text])
                self.assertEqual(hits_in(line.encode("ascii")), [])

    def test_a_longer_address_at_the_maintainer_domain_is_caught(self):
        for address in (caught("other", "posluns" + "." + "ca"), "worker." + MAINTAINER, "x" + MAINTAINER,
                        MAINTAINER + "x", MAINTAINER + "." + "co"):
            with self.subTest(address=address):
                self.assertIn(address, self.texts(address))
                self.assertEqual(len(hits_in(address.encode("ascii"))), 1)

    def test_each_byte_value_extends_the_local_part_only_when_the_docstring_names_it(self):
        # Every byte value between a prefix and the maintainer's address. A byte that the docstring
        # puts in the local part joins the prefix to it, so the longer candidate is caught; any other
        # byte ends the local part, so the candidate is exactly the maintainer's address and exempt.
        for value in range(256):
            text = b"x" + bytes([value]) + MAINTAINER_BYTES
            with self.subTest(byte=value):
                if value in self.DOCUMENTED_LOCAL_BYTES:
                    self.assertEqual(self.byte_texts(text), [text])
                    self.assertEqual(len(hits_in(text)), 1)
                else:
                    self.assertEqual(hits_in(text), [])

    def test_each_byte_value_extends_the_domain_run_only_when_the_docstring_names_it(self):
        # Every byte value inside a domain. A byte that the docstring puts in the domain run keeps the
        # run whole, so the candidate is the whole text; any other byte ends the run before its dot.
        for value in range(256):
            text = b"worker" + b"@" + b"h" + bytes([value]) + b"x.com"
            with self.subTest(byte=value):
                if value in self.DOCUMENTED_DOMAIN_BYTES:
                    expected = [text]
                elif value == ord("@"):
                    expected = [b"h" + b"@" + b"x.com"]
                else:
                    expected = []
                self.assertEqual(self.byte_texts(text), expected)
                self.assertEqual(len(hits_in(text)), len(expected))

    def test_reserved_documentation_domains_are_exempt(self):
        for domain in ("example" + "." + "invalid", "x" + "." + "test", "host" + "." + "example",
                       "example" + "." + "com", "mail.example" + "." + "org", "example" + "." + "net",
                       "X" + "." + "TEST", "Example" + "." + "Com", "Mail.Example" + "." + "Org",
                       "a.EXAMPLE" + "." + "NET", "b.Example" + "." + "com"):
            with self.subTest(domain=domain):
                address = caught("fixture", domain)
                self.assertIn(address, self.texts(address))
                self.assertEqual(hits_in(address.encode("ascii")), [])

    def test_a_domain_that_only_contains_a_reserved_name_is_caught(self):
        for domain in ("notexample" + "." + "com", "example.com" + "." + "co", "testing" + "." + "io",
                       "host" + "." + "testing", "host" + "." + "examples", "host" + "." + "invalidx",
                       "host" + "." + "mytest", "host" + "." + "notexample", "host" + "." + "texample"):
            with self.subTest(domain=domain):
                address = caught("worker", domain)
                self.assertIn(address, self.texts(address))
                self.assertEqual(len(hits_in(address.encode("ascii"))), 1)

    def test_a_reserved_domain_address_passes_only_when_every_candidate_is_exempt(self):
        # The accepted false failure that the rule states: a whole domain that is reserved, whose
        # run also ends a shorter domain that is not, is caught with the digest of that shorter
        # candidate. A reserved domain whose every shorter domain is reserved as well passes.
        for domain, shorter in (("mail.corp" + "." + "example.com", "mail.corp"),
                                ("host.co" + "." + "test", "host.co")):
            with self.subTest(domain=domain):
                address = caught("fixture", domain)
                self.assertEqual(self.texts(address)[-1], address)
                self.assertEqual(self.digests(address),
                                 [sha256_prefix(caught("fixture", shorter).encode("ascii"))])
        for domain in ("mail.example" + "." + "org", "a.b.example" + "." + "com"):
            with self.subTest(domain=domain):
                address = caught("fixture", domain)
                self.assertEqual(self.texts(address)[-1], address)
                self.assertEqual(hits_in(address.encode("ascii")), [])

    def test_non_addresses_are_not_matched(self):
        pin = "actions/checkout" + "@" + "v4.4.0"
        commit = "actions/checkout" + "@" + "0123456789abcdef0123456789abcdef01234567"
        for text in (pin, commit, "the maintainer, Jeff Posluns", "a @ b . co", "user" + "@" + "host",
                     "a" + "@" + "b.c", "a" + "@" + ".com", "@" + "host.com", "x" + "@" + "host.c1"):
            with self.subTest(text=text):
                self.assertEqual(self.texts(text), [])

    def test_a_version_tag_is_caught_only_where_a_dot_is_followed_by_2_letters(self):
        # The accepted false failure that the residual states: a domain ends after those letters,
        # whatever follows them, and a tag whose every dot is followed by a digit gives no candidate.
        for tag, domain in (("v1.2.3-alpha.beta.1", "v1.2.3-alpha.beta"), ("v2.0.0-rc.ab", "v2.0.0-rc.ab"),
                            ("v1.2.3.beta", "v1.2.3.beta"), ("v3.0.0-rc.beta2", "v3.0.0-rc.beta")):
            with self.subTest(tag=tag):
                pin = "actions/checkout" + "@" + tag
                self.assertEqual(self.texts(pin), ["checkout" + "@" + domain])
                self.assertEqual(len(hits_in(pin.encode("ascii"))), 1)
        for tag in ("v1.2.3-rc.1", "v1.0.0-beta.2", "v1.2.3-alpha.1", "v1.10.0-rc.12"):
            with self.subTest(tag=tag):
                self.assertEqual(self.texts("actions/checkout" + "@" + tag), [])

    def test_a_version_tag_passes_where_every_domain_it_ends_is_exempt(self):
        # The exception that the residual states: the letters after a dot form a reserved last
        # label, in any case, or close a reserved documentation domain, so every candidate is
        # exempt. Where 1 domain the tag ends is not exempt, the tag is still caught.
        for tag, domains in (("v1.2.3-pre.test.1", ("v1.2.3-pre.test",)),
                             ("v2.0.0.example", ("v2.0.0.example",)),
                             ("v1.0.0-rc.Invalid", ("v1.0.0-rc.Invalid",)),
                             ("v1.0.0-rc.example.com", ("v1.0.0-rc.example", "v1.0.0-rc.example.com"))):
            with self.subTest(tag=tag):
                pin = "actions/checkout" + "@" + tag
                self.assertEqual(self.texts(pin), ["checkout" + "@" + domain for domain in domains])
                self.assertEqual(hits_in(pin.encode("ascii")), [])
        caught_part = "checkout" + "@" + "v1.2.3-alpha.test.beta"
        pin = "actions/" + caught_part
        self.assertEqual(self.texts(pin), ["checkout" + "@" + "v1.2.3-alpha.test", caught_part])
        self.assertEqual(self.digests(pin), [sha256_prefix(caught_part.encode("ascii"))])

    def test_the_digest_is_that_of_the_longest_candidate_that_is_not_exempt(self):
        # 1 domain run that ends 3 domains: 2 that are not exempt and, after them, a reserved one.
        shorter = caught("worker", "host" + "." + "co")
        longer = shorter + "." + "uk"
        text = longer + "." + "example"
        self.assertEqual(self.texts(text), [shorter, longer, text])
        self.assertEqual(self.digests(text), [sha256_prefix(longer.encode("ascii"))])

    def test_long_address_free_text_costs_bounded_work(self):
        # About 150000 bytes each, with no candidate: a run with no at sign, a long local part
        # before a long dotted domain run, many at signs, and many dots. A search that retries the
        # local part from every byte takes many seconds on the first.
        for data in (b"a" * 150000, b"a" * 75000 + b"@" + b"a.1" * 25000, (b"a.b" + b"@") * 37500,
                     b"x" + b"@" + b"a1." * 50000):
            with self.subTest(size=len(data), head=data[:8]):
                began = time.monotonic()
                self.assertEqual(hits_in(data), [])
                self.assertLess(time.monotonic() - began, 2.0)

    def test_this_source_holds_no_matchable_text(self):
        self.assertEqual(candidates(Path(__file__).read_bytes()), [])


class FixtureRepository(unittest.TestCase):
    """The scan on a temporary repository: a hit, the allowlist, and every fail-closed path."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.git("init", "-q")

    def git(self, *args):
        env = dict(os.environ, GIT_CEILING_DIRECTORIES=self.tmp.name)
        subprocess.run(["git", "-C", str(self.root)] + list(args), check=True, capture_output=True,
                       stdin=subprocess.DEVNULL, env=env)

    def git_out(self, *args, data=b""):
        """The output of git at the fixture, its last line feed removed, with data as its input."""
        env = dict(os.environ, GIT_CEILING_DIRECTORIES=self.tmp.name)
        return subprocess.run(["git", "-C", str(self.root)] + list(args), check=True, capture_output=True,
                              input=data, env=env).stdout.decode("ascii").strip()

    def add(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        self.git("add", "--", rel)

    def add_entry(self, mode, object_name, rel):
        """An index entry for rel that names object_name, with no file behind it."""
        self.git("update-index", "--add", "--cacheinfo", "{},{},{}".format(mode, object_name, rel))

    def missing_object(self):
        """The object name of a blob that the repository does not hold."""
        return self.git_out("hash-object", "--stdin", data=b"never written\n")

    def tree_object(self):
        """The object name of an empty tree, written to the repository."""
        return self.git_out("mktree")

    def test_a_clean_repository_passes(self):
        text = "Contact: mailto:" + MAINTAINER + "\n" + caught("t", "x" + "." + "invalid") + "\n"
        self.assertEqual(len(candidates(text.encode("ascii"))), 2)
        self.add("a.txt", text)
        self.assertEqual(scan(self.root, {}), ([], 1))

    def test_a_planted_address_fails_naming_path_line_and_digest_only(self):
        address = caught("worker-label-example", "placeholder-mail" + "." + "com")
        self.add("docs/note.md", "first\nsecond " + address + "\n")
        failures, _ = scan(self.root, {})
        self.assertEqual(failures, ["docs/note.md:2: email-shaped text, sha256 "
                                    + sha256_prefix(address.encode("ascii"))])
        self.assertNotIn("worker-label-example", failures[0])
        self.assertNotIn("second", failures[0])

    def test_a_masked_address_fails(self):
        address = caught("w." + "example", "placeholder-mail" + "." + "com")
        self.add("m.txt", "p" + "@" + address + "\n")
        failures, _ = scan(self.root, {})
        self.assertEqual(failures, ["m.txt:1: email-shaped text, sha256 " + sha256_prefix(address.encode("ascii"))])

    def test_an_address_in_a_path_name_fails_naming_the_path_by_its_digest_only(self):
        # A regular file whose name and content each hold an address, and a symbolic link whose name
        # holds 1: each failure names its path by the digest of the path name, never the name. The
        # link is read as its own target text, which holds no address.
        address = caught("worker-label-example", "placeholder-mail" + "." + "com")
        rel = "docs/" + address + ".md"
        link = "to-" + address
        self.add(rel, "first\nsecond " + address + "\n")
        os.symlink("docs", self.root / link)
        self.git("add", "--", link)
        failures, read = scan(self.root, {})
        self.assertEqual(read, 2)
        named = "path sha256 " + sha256_prefix(rel.encode("ascii"))
        self.assertEqual(failures, [
            named + ": email-shaped text in the path name, sha256 " + sha256_prefix((address + ".md").encode("ascii")),
            named + ":2: email-shaped text, sha256 " + sha256_prefix(address.encode("ascii")),
            "path sha256 " + sha256_prefix(link.encode("ascii")) + ": email-shaped text in the path name, sha256 "
            + sha256_prefix(link.encode("ascii"))])
        for failure in failures:
            self.assertNotIn("worker-label-example", failure)
            self.assertNotIn("placeholder-mail", failure)

    def test_an_address_in_a_folder_name_names_every_failure_of_the_path_by_its_digest(self):
        # The address in the first folder of 1 path and in a middle folder of another, never in the
        # last component: each failure, a stale entry included, names its path by its digest.
        address = caught("worker-label-example", "placeholder-mail" + "." + "com")
        first = address + "/note.md"
        middle = "docs/" + address + "/deep/note.md"
        for rel in (first, middle):
            self.add(rel, "first\nsecond " + address + "\n")
        failures, read = scan(self.root, {first: ("gone",)})
        self.assertEqual(read, 2)
        hit = sha256_prefix(address.encode("ascii"))
        expected = []
        for rel in (middle, first):
            named = "path sha256 " + sha256_prefix(rel.encode("ascii"))
            expected += [named + ": email-shaped text in the path name, sha256 " + hit,
                         named + ":2: email-shaped text, sha256 " + hit]
        expected.append("path sha256 " + sha256_prefix(first.encode("ascii"))
                        + ": stale allowlist entry 1, no line that holds a hit, sha256 " + sha256_prefix(b"gone"))
        self.assertEqual(failures, expected)
        for failure in failures:
            self.assertNotIn("worker-label-example", failure)
            self.assertNotIn("placeholder-mail", failure)

    def test_a_submodule_whose_name_holds_an_address_fails_unread_naming_its_digest(self):
        # A submodule entry with no checkout behind it: its name is scanned, and it is not read.
        address = caught("worker", "placeholder-mail" + "." + "com")
        sub = "mods/" + address
        self.add("real.txt", "text\n")
        self.git("update-index", "--add", "--cacheinfo", "160000," + "1" * 40 + "," + sub)
        self.assertEqual(scan(self.root, {}), (["path sha256 " + sha256_prefix(sub.encode("ascii"))
                                                + ": email-shaped text in the path name, sha256 "
                                                + sha256_prefix(address.encode("ascii"))], 1))

    def test_a_path_name_with_a_space_or_a_byte_outside_ascii_is_read_and_scanned(self):
        # Names that git quotes, or that hold a separator, when it lists paths without -z. Each
        # file is read, and a name that holds an address is named only by its digest. A file
        # system that refuses a name that is not valid UTF-8, as on macOS, drops the 2 such names.
        raw = os.fsdecode(b"raw\xff.txt")
        try:
            (self.root / raw).write_bytes(b"")
            (self.root / raw).unlink()
            raw_names = True
        except OSError:
            raw_names = False
        clean = ("with space.txt", "tab\tname.txt", "line\nfeed.txt", "double\"quote.txt",
                 "back\\slash.txt", "caf" + chr(233) + ".txt") + ((raw,) if raw_names else ())
        for rel in clean:
            self.add(rel, "text\n")
        self.assertEqual(scan(self.root, {}), ([], len(clean)))
        address = caught("worker-label-example", "placeholder-mail" + "." + "com")
        hit = sha256_prefix(address.encode("ascii"))
        marked = (("my notes/" + address + " copy.md", hit),
                  ("caf" + chr(233) + "/" + address + "/x.md", hit))
        if raw_names:
            marked += ((os.fsdecode(b"raw\xff/") + address + "/x.md", hit),)
        for rel, _ in marked:
            self.add(rel, "x " + address + "\n")
        failures, read = scan(self.root, {})
        self.assertEqual(read, len(clean) + len(marked))
        expected = []
        for rel, name_hit in sorted(marked):
            named = "path sha256 " + sha256_prefix(os.fsencode(rel))
            expected += [named + ": email-shaped text in the path name, sha256 " + name_hit,
                         named + ":1: email-shaped text, sha256 " + hit]
        self.assertEqual(failures, expected)
        for failure in failures:
            self.assertNotIn("placeholder-mail", failure)
            self.assertTrue(failure.isascii(), failure)

    def address_folder(self):
        """A new folder in the temporary folder whose name is an address assembled at run time."""
        folder = Path(self.tmp.name) / caught("worker-label-example", "placeholder-mail" + "." + "com")
        folder.mkdir()
        return folder

    def assert_no_address(self, failures):
        for failure in failures:
            self.assertNotIn("worker-label-example", failure)
            self.assertNotIn("placeholder-mail", failure)

    def test_an_unreadable_blob_is_named_by_a_fixed_category_only(self):
        # Entries whose stored object is missing or is no blob, 1 of them at a path that holds an
        # address: each failure holds the fixed category only, and names that path by its digest.
        rel = caught("worker", "placeholder-mail" + "." + "com")
        named = "path sha256 " + sha256_prefix(rel.encode("ascii"))
        self.add_entry("100644", self.missing_object(), rel)
        self.add_entry("100644", self.missing_object(), "plain.txt")
        self.add_entry("100644", self.tree_object(), "tree.txt")
        self.assertEqual(scan(self.root, {}), ([
            "plain.txt: unreadable: missing",
            "tree.txt: unreadable: not a blob",
            named + ": email-shaped text in the path name, sha256 " + sha256_prefix(rel.encode("ascii")),
            named + ": unreadable: missing"], 0))

    def test_a_blob_read_that_fails_names_only_its_exit_code_or_errno_name_or_error_type(self):
        # A git cat-file that fails with a diagnostic that holds an address, and start errors whose
        # text holds it: each failure is the exit code alone, or the errno name, or the name of
        # the type when the error has no errno, or has 1 that the errno table does not name. The
        # listing before it runs as usual.
        self.add("a.txt", "text\n")
        program = str(self.address_folder() / "no-such-git")
        self.assertNotIn(1 << 20, errno.errorcode)
        run = subprocess.run
        for error, text in ((subprocess.CalledProcessError(128, [GIT], output=b"", stderr=program.encode()),
                             "exit 128"),
                            (OSError(errno.EACCES, "denied for " + program, program),
                             "git could not be started: EACCES"),
                            (OSError(program), "git could not be started: OSError"),
                            (OSError(1 << 20, "no errno name for " + program, program),
                             "git could not be started: OSError")):
            with self.subTest(text=text, errno=getattr(error, "errno", None)):
                def blob_read_fails(args, **kwargs):
                    if "cat-file" in args:
                        raise error
                    return run(args, **kwargs)
                with mock.patch.object(subprocess, "run", side_effect=blob_read_fails):
                    failures, read = scan(self.root, {})
                self.assertEqual((failures, read), (["git cat-file failed: " + text], 0))

    def test_a_failed_listing_names_only_its_exit_code(self):
        # A real git that fails in a folder whose path holds an address, so that its diagnostic
        # holds the address, and a git whose given diagnostic holds it: each failure is the exit
        # code alone.
        missing = self.address_folder() / "missing-folder"
        stderr = subprocess.run([GIT, "-C", str(missing), "ls-files"], capture_output=True,
                                stdin=subprocess.DEVNULL).stderr
        self.assertIn(b"placeholder-mail", stderr)
        failures, read = scan(missing, {})
        self.assertEqual(read, 0)
        self.assertEqual(len(failures), 1, failures)
        self.assertRegex(failures[0], r"\Agit ls-files failed: exit [0-9]+\Z")
        self.assert_no_address(failures)
        error = subprocess.CalledProcessError(128, [GIT], output=b"", stderr=stderr)
        with mock.patch.object(subprocess, "run", side_effect=error):
            self.assertEqual(scan(self.root, {}), (["git ls-files failed: exit 128"], 0))

    def test_a_git_that_cannot_start_names_only_its_errno_name_or_error_type(self):
        # A real program path that holds an address, then start errors whose text holds it: each
        # failure is the errno name, or the name of the type when the error has no errno, or has 1
        # that the errno table does not name.
        self.add("a.txt", "text\n")
        program = str(self.address_folder() / "no-such-git")
        failures, read = scan(self.root, {}, git=program)
        self.assertEqual((failures, read), (["git ls-files failed: git could not be started: ENOENT"], 0))
        self.assertNotIn(1 << 20, errno.errorcode)
        for error, text in ((OSError(errno.EACCES, "denied for " + program, program), "EACCES"),
                            (OSError(program), "OSError"),
                            (OSError(1 << 20, "no errno name for " + program, program), "OSError")):
            with self.subTest(text=text, errno=error.errno):
                self.assertIn("placeholder-mail", str(error))
                with mock.patch.object(subprocess, "run", side_effect=error):
                    failures, read = scan(self.root, {})
                self.assertEqual((failures, read), (["git ls-files failed: git could not be started: " + text], 0))

    def test_an_empty_listing_names_no_path(self):
        # An empty repository whose path holds an address: the failure names no path.
        repo = self.address_folder() / "repo"
        repo.mkdir()
        subprocess.run([GIT, "-C", str(repo), "init", "-q"], check=True, capture_output=True,
                       stdin=subprocess.DEVNULL, env=dict(os.environ, GIT_CEILING_DIRECTORIES=self.tmp.name))
        self.assertEqual(scan(repo, {}), (["git ls-files listed no file"], 0))

    def test_an_unreadable_file_or_stale_entry_of_such_a_path_names_only_its_digest(self):
        rel = caught("worker", "placeholder-mail" + "." + "com")
        named = "path sha256 " + sha256_prefix(rel.encode("ascii"))
        self.add_entry("100644", self.missing_object(), rel)
        failures, _ = scan(self.root, {rel: ("gone",)})
        self.assertEqual(len(failures), 3, failures)
        self.assertEqual(failures[0], named + ": email-shaped text in the path name, sha256 "
                         + sha256_prefix(rel.encode("ascii")))
        self.assertEqual(failures[1], named + ": unreadable: missing")
        self.assertEqual(failures[2], named + ": stale allowlist entry 1, no line that holds a hit, sha256 "
                         + sha256_prefix(b"gone"))
        for failure in failures:
            self.assertNotIn("placeholder-mail", failure)

    def test_an_allowlisted_line_passes_and_a_stale_entry_fails(self):
        line = "url https://" + caught("user", "project" + "." + "ai") + "/a"
        self.assertEqual(len(hits_in(line.encode("ascii"))), 1)
        self.add("t.py", line + "\n")
        self.assertEqual(scan(self.root, {"t.py": (line,)}), ([], 1))
        moved = line + " moved"
        failures, _ = scan(self.root, {"t.py": (moved,)})
        self.assertEqual(len(failures), 2, failures)
        self.assertTrue(failures[0].startswith("t.py:1: email-shaped text, sha256 "), failures)
        self.assertEqual(failures[1], "t.py: stale allowlist entry 1, no line that holds a hit, sha256 "
                         + sha256_prefix(moved.encode("ascii")))

    def test_an_allowlist_entry_covers_only_its_exact_line(self):
        line = "url https://" + caught("user", "project" + "." + "ai") + "/a"
        longer = line + " " + caught("worker-label-example", "placeholder-mail" + "." + "com")
        self.add("t.py", line + "\n" + longer + "\n" + " " + line + "\n")
        failures, _ = scan(self.root, {"t.py": (line,)})
        self.assertEqual(len(failures), 3, failures)
        self.assertEqual([failure.split(" ")[0] for failure in failures], ["t.py:2:", "t.py:2:", "t.py:3:"])

    def test_an_empty_allowlist_passes_no_hit(self):
        line = "url https://" + caught("user", "project" + "." + "ai") + "/a"
        self.add("t.py", line + "\n")
        for allowlist in ({}, {"t.py": ()}):
            with self.subTest(allowlist=allowlist):
                failures, _ = scan(self.root, allowlist)
                self.assertEqual(len(failures), 1, failures)

    def test_an_allowlist_entry_applies_only_to_its_own_file(self):
        # The same line in 2 files, with an entry for 1 of them: the line in the other file fails.
        address = caught("user", "project" + "." + "ai")
        line = "url https://" + address + "/a"
        self.add("t.py", line + "\n")
        self.add("u.py", line + "\n")
        self.assertEqual(scan(self.root, {"t.py": (line,)}),
                         (["u.py:1: email-shaped text, sha256 " + sha256_prefix(address.encode("ascii"))], 2))

    def test_an_allowlist_entry_whose_line_holds_no_hit_is_stale(self):
        # 3 lines, each present exactly as an entry: 1 with no at sign, 1 whose only candidate is
        # exempt, and 1 that holds a hit. Only the last entry is used; the 2 others are stale.
        plain = "url https://project.ai/a"
        exempt_only = "url https://" + caught("user", "example" + "." + "com") + "/a"
        held = "url https://" + caught("user", "project" + "." + "ai") + "/a"
        self.assertEqual(len(candidates(exempt_only.encode("ascii"))), 1)
        self.assertEqual(hits_in(exempt_only.encode("ascii")), [])
        self.add("t.py", plain + "\n" + exempt_only + "\n" + held + "\n")
        self.assertEqual(scan(self.root, {"t.py": (plain, exempt_only, held)}), ([
            "t.py: stale allowlist entry 1, no line that holds a hit, sha256 "
            + sha256_prefix(plain.encode("ascii")),
            "t.py: stale allowlist entry 2, no line that holds a hit, sha256 "
            + sha256_prefix(exempt_only.encode("ascii"))], 1))

    def test_a_missing_stored_blob_fails_naming_it(self):
        self.add_entry("100644", self.missing_object(), "gone.txt")
        self.assertEqual(scan(self.root, {}), (["gone.txt: unreadable: missing"], 0))

    def test_a_stored_object_that_is_no_blob_fails_naming_it(self):
        self.add_entry("100644", self.tree_object(), "odd.txt")
        self.assertEqual(scan(self.root, {}), (["odd.txt: unreadable: not a blob"], 0))

    def listing_reply(self, reply):
        """A patch of subprocess.run under which git ls-files gives reply as its output.

        Every other call runs as usual.
        """
        run = subprocess.run

        def reply_with(args, **kwargs):
            if "ls-files" in args:
                return subprocess.CompletedProcess(args, 0, stdout=reply, stderr=b"")
            return run(args, **kwargs)
        return mock.patch.object(subprocess, "run", side_effect=reply_with)

    def test_each_malformed_listing_gives_unexpected_reply(self):
        """Each malformation of a reply of git ls-files gives unexpected reply, never an error.

        Each subtest feeds tracked_files() 1 reply and names the malformation that it holds: an
        entry with too few fields, with 1 field, or with too many fields; an empty field; a byte
        outside ASCII in the mode or in the object name; a mode that is not 6 octal digits, an
        object name that is not 40 or 64 lowercase hexadecimal digits, or a stage other than 0,
        1, 2, or 3; a stray separator, a tab in place of a space or a NUL inside an entry; an
        entry with no tab, an empty entry, or an empty path; a listing that no NUL ends; and a
        path name that os.fsdecode() cannot decode, as on Windows, whose decoder refuses a byte
        that is not valid UTF-8. Each expects the fixed word unexpected reply from
        tracked_files() and the fixed failure line from scan(), and fails when its reply gives
        a listing or raises an error. The control: a well-formed reply, whose path names hold a
        space, a tab, a letter outside ASCII, and a byte that is not valid UTF-8, gives its
        entries.
        """
        short, long = b"a" * 40, b"b" * 64
        good = (b"100644 " + short + b" 0\tdocs/a b\tc.txt\0" + b"120000 " + long + b" 0\tl\xc3\xa9\0"
                + b"100644 " + short + b" 0\traw\xff.txt\0")
        with self.listing_reply(good):
            self.assertEqual(tracked_files(self.root), [
                ("docs/a b\tc.txt", "100644", short.decode("ascii")),
                ("l" + chr(0xE9), "120000", long.decode("ascii")),
                (os.fsdecode(b"raw\xff.txt"), "100644", short.decode("ascii"))])

        def strict(data):
            return data.decode("utf-8", "surrogatepass")
        for malformation, reply, decode in (
                ("an entry with too few fields", b"100644 " + short + b"\tp.txt\0", None),
                ("an entry with 1 field", b"100644\tp.txt\0", None),
                ("an entry with too many fields", b"100644 " + short + b" 0 x\tp.txt\0", None),
                ("an empty field", b"100644  " + short + b" 0\tp.txt\0", None),
                ("a mode with a byte outside ASCII", b"1006\xc3\xa9 " + short + b" 0\tp.txt\0", None),
                ("an object name with a byte outside ASCII",
                 b"100644 " + b"a" * 38 + b"\xc3\xa9 0\tp.txt\0", None),
                ("a mode that is not 6 octal digits", b"100648 " + short + b" 0\tp.txt\0", None),
                ("an object name that is not 40 or 64 lowercase hexadecimal digits",
                 b"100644 " + b"A" * 40 + b" 0\tp.txt\0", None),
                ("a stage other than 0, 1, 2, or 3", b"100644 " + short + b" 4\tp.txt\0", None),
                ("a stray separator, a tab in place of a space", b"100644\t" + short + b" 0\tp.txt\0", None),
                ("a stray separator, a NUL inside an entry", b"100644 " + short + b" 0\tp\0.txt\0", None),
                ("an entry with no tab", b"100644 " + short + b" 0 p.txt\0", None),
                ("an empty entry", b"100644 " + short + b" 0\tp.txt\0\0", None),
                ("an empty path", b"100644 " + short + b" 0\t\0", None),
                ("a listing that no NUL ends", b"100644 " + short + b" 0\tp.txt", None),
                ("a path name that os.fsdecode() cannot decode, as on Windows",
                 b"100644 " + short + b" 0\traw\xff.txt\0", strict)):
            with self.subTest(malformation=malformation):
                decoder = mock.patch.object(os, "fsdecode", side_effect=decode or os.fsdecode)
                with self.listing_reply(reply), decoder:
                    self.assertEqual(tracked_files(self.root), "unexpected reply")
                    self.assertEqual(scan(self.root, {}), (["git ls-files gave an unexpected reply"], 0))

    def batch_reply(self, reply):
        """A patch of subprocess.run under which git cat-file --batch gives reply as its output.

        Every other call runs as usual, so a listing before it reads the fixture.
        """
        run = subprocess.run

        def reply_with(args, **kwargs):
            if "cat-file" in args:
                return subprocess.CompletedProcess(args, 0, stdout=reply, stderr=b"")
            return run(args, **kwargs)
        return mock.patch.object(subprocess, "run", side_effect=reply_with)

    def test_each_malformed_or_short_batch_reply_gives_unexpected_reply(self):
        """Each way that a reply of git cat-file fails to answer for an object gives unexpected reply.

        Each subtest feeds stored_blobs() 1 reply for 2 objects, first and second, and names the
        fail-closed path that it takes: a reply that ends before an object is answered, a header
        that names another object, a header with too many fields, an empty field or a stray
        separator among them, or too few fields, a header of 2 fields other than missing, a size
        that is no number, digits outside ASCII among them, a size with more digits than Python
        will convert to an integer, and a body that is cut short or that no line feed ends. Each
        fails when its path gives bytes, an empty clean blob among them, or raises an error, in
        place of unexpected reply. A reply that does not answer stops the read, so every later
        object gives unexpected reply too; a header of 2 fields does not.
        """
        first, second, other = "1" * 40, "2" * 40, "3" * 40
        answered = first.encode("ascii") + b" blob 5\ntext\n\n"
        for path, reply, expected in (
                ("a reply that ends before an object is answered", answered,
                 {first: b"text\n", second: "unexpected reply"}),
                ("an empty reply", b"", {first: "unexpected reply", second: "unexpected reply"}),
                ("a header that names another object", answered + other.encode("ascii") + b" blob 5\ntext\n\n",
                 {first: b"text\n", second: "unexpected reply"}),
                ("a header with too many fields", answered + second.encode("ascii") + b" blob 5 x\ntext\n\n",
                 {first: b"text\n", second: "unexpected reply"}),
                ("a header with too few fields", answered + second.encode("ascii") + b"\n",
                 {first: b"text\n", second: "unexpected reply"}),
                ("a header with an empty field", answered + second.encode("ascii") + b"  blob 5\ntext\n\n",
                 {first: b"text\n", second: "unexpected reply"}),
                ("a header with a stray separator", answered + second.encode("ascii") + b" blob 5 \ntext\n\n",
                 {first: b"text\n", second: "unexpected reply"}),
                ("a size of digits outside ASCII",
                 answered + second.encode("ascii") + b" blob " + chr(0x665).encode("utf-8") + b"\ntext\n\n",
                 {first: b"text\n", second: "unexpected reply"}),
                ("a header of 2 fields other than missing",
                 first.encode("ascii") + b" ambiguous\n" + second.encode("ascii") + b" blob 5\ntext\n\n",
                 {first: "unexpected reply", second: b"text\n"}),
                ("a size that is no number", answered + second.encode("ascii") + b" blob x\n\n",
                 {first: b"text\n", second: "unexpected reply"}),
                ("a size with more digits than Python will convert to an integer",
                 first.encode("ascii") + b" blob " + b"1" * 4301 + b"\ntext\n\n"
                 + second.encode("ascii") + b" blob 5\ntext\n\n",
                 {first: "unexpected reply", second: "unexpected reply"}),
                ("a body that is cut short", answered + second.encode("ascii") + b" blob 50\ntext\n",
                 {first: b"text\n", second: "unexpected reply"}),
                ("a body that no line feed ends", answered + second.encode("ascii") + b" blob 4\ntextX",
                 {first: b"text\n", second: "unexpected reply"}),
                ("every object after a reply that does not answer",
                 first.encode("ascii") + b" blob x\n\n" + second.encode("ascii") + b" blob 5\ntext\n\n",
                 {first: "unexpected reply", second: "unexpected reply"})):
            with self.subTest(path=path):
                with self.batch_reply(reply):
                    self.assertEqual(stored_blobs(self.root, [first, second]), expected)

    def test_a_short_batch_reply_fails_naming_the_file_it_leaves_unanswered(self):
        # A reply that answers for the first blob only: the second file fails as unexpected reply,
        # and is not read as an empty clean blob.
        self.add("a.txt", "text\n")
        self.add("b.txt", "more\n")
        name = self.git_out("rev-parse", ":a.txt")
        with self.batch_reply(name.encode("ascii") + b" blob 5\ntext\n\n"):
            self.assertEqual(scan(self.root, {}), (["b.txt: unreadable: unexpected reply"], 1))

    def test_a_replace_ref_does_not_change_what_is_scanned(self):
        """A stored blob that holds an address fails though a replace ref names a clean blob for it.

        The control: git cat-file with replace objects on gives the clean text for that blob. The
        scan turns them off, so it reads the blob that the index names, the 1 that git publishes.
        """
        line, hit = self.address_line()
        self.add("note.txt", line.decode("ascii"))
        stored = self.git_out("rev-parse", ":note.txt")
        clean = self.git_out("hash-object", "-w", "--stdin", data=b"text\n")
        self.git("replace", stored, clean)
        self.assertEqual(self.git_out("cat-file", "blob", stored), "text")
        self.assertEqual(scan(self.root, {}), (["note.txt:1: email-shaped text, sha256 " + hit], 1))

    def test_a_failed_git_call_fails(self):
        # A folder that does not exist, so git -C fails wherever the temporary folder lies.
        failures, read = scan(Path(self.tmp.name) / "missing-folder", {})
        self.assertEqual(read, 0)
        self.assertEqual(len(failures), 1, failures)
        self.assertTrue(failures[0].startswith("git ls-files failed: exit "), failures)

    def test_a_git_that_cannot_start_fails(self):
        # A clean repository, so only the missing program can make the scan fail.
        self.add("a.txt", "text\n")
        self.assertEqual(scan(self.root, {}), ([], 1))
        failures, read = scan(self.root, {}, git=str(Path(self.tmp.name) / "no-such-git"))
        self.assertEqual(read, 0)
        self.assertEqual(len(failures), 1, failures)
        self.assertTrue(failures[0].startswith("git ls-files failed: git could not be started: "), failures)

    def test_an_empty_listing_fails(self):
        failures, _ = scan(self.root, {})
        self.assertEqual(len(failures), 1, failures)
        self.assertTrue(failures[0].startswith("git ls-files listed no file"), failures)

    def test_a_symbolic_link_is_read_as_its_own_target_text(self):
        # A link whose target text holds no address passes, and its blob is read.
        self.add("real.txt", "text\n")
        os.symlink("real.txt", self.root / "link.txt")
        self.git("add", "--", "link.txt")
        self.assertEqual(scan(self.root, {}), ([], 2))

    def test_a_symbolic_link_whose_own_target_text_holds_an_address_fails(self):
        # The target text is the stored blob of the link; the file it names does not exist, so a
        # scan that follows the link instead reads nothing there.
        address = caught("worker-label-example", "placeholder-mail" + "." + "com")
        os.symlink(address, self.root / "link.txt")
        self.git("add", "--", "link.txt")
        self.assertFalse((self.root / "link.txt").exists())
        self.assertEqual(scan(self.root, {}), (["link.txt:1: email-shaped text, sha256 "
                                                + sha256_prefix(address.encode("ascii"))], 1))

    def test_a_working_tree_encoding_file_whose_blob_holds_an_address_fails(self):
        """A file that git turns into UTF-16LE in the working copy is scanned as its stored blob.

        The attribute working-tree-encoding makes git store the file as UTF-8 and write it out
        as UTF-16LE, so the working copy gives no candidate while the blob, which git publishes,
        holds the address as it is.
        """
        line, hit = self.address_line()
        self.add(".gitattributes", "enc.txt text working-tree-encoding=UTF-16LE\n")
        working = line.decode("ascii").encode("utf-16-le")
        (self.root / "enc.txt").write_bytes(working)
        self.git("add", "--", "enc.txt")
        self.assertEqual(candidates((self.root / "enc.txt").read_bytes()), [])
        self.assertEqual(self.git_out("cat-file", "blob", ":enc.txt").encode("ascii") + b"\n", line)
        self.assertEqual(scan(self.root, {}), (["enc.txt:1: email-shaped text, sha256 " + hit], 2))

    def test_the_state_of_the_working_copy_does_not_change_what_is_scanned(self):
        """A stored blob that holds an address fails whatever the working copy holds at its path.

        The working copy is rewritten without the address, then removed, then replaced by a
        folder; the index is left as it is, so each scan reads the same blob.
        """
        line, hit = self.address_line()
        self.add("note.txt", line.decode("ascii"))
        expected = (["note.txt:1: email-shaped text, sha256 " + hit], 1)
        self.assertEqual(scan(self.root, {}), expected)
        path = self.root / "note.txt"
        path.write_bytes(b"text\n")
        self.assertEqual(scan(self.root, {}), expected)
        path.unlink()
        self.assertEqual(scan(self.root, {}), expected)
        path.mkdir()
        self.assertEqual(scan(self.root, {}), expected)

    def test_a_submodule_is_not_read(self):
        # A submodule entry with no checkout behind it, which a read would report as missing.
        self.add("real.txt", "text\n")
        self.git("update-index", "--add", "--cacheinfo", "160000," + "1" * 40 + ",sub")
        self.assertEqual(scan(self.root, {}), ([], 1))

    def address_line(self):
        """A line that holds an address assembled at run time, and the expected digest of its hit."""
        address = caught("worker-label-example", "placeholder-mail" + "." + "com")
        line = ("x " + address + "\n").encode("ascii")
        self.assertEqual(len(hits_in(line)), 1)
        return line, sha256_prefix(address.encode("ascii"))

    def test_an_untracked_file_is_not_read(self):
        """An address-bearing file that git does not list passes; the control: once added, it fails."""
        line, hit = self.address_line()
        self.add("tracked.txt", "text\n")
        (self.root / "untracked.txt").write_bytes(line)
        self.assertEqual(scan(self.root, {}), ([], 1))
        self.git("add", "--", "untracked.txt")
        self.assertEqual(scan(self.root, {}), (["untracked.txt:1: email-shaped text, sha256 " + hit], 2))

    def test_an_edit_of_a_tracked_file_that_is_not_staged_is_not_read(self):
        """An address in an edit of a tracked file that is not staged passes; the control: staged, it fails."""
        line, hit = self.address_line()
        self.add("note.txt", "text\n")
        (self.root / "note.txt").write_bytes(line)
        self.assertEqual(scan(self.root, {}), ([], 1))
        self.git("add", "--", "note.txt")
        self.assertEqual(scan(self.root, {}), (["note.txt:1: email-shaped text, sha256 " + hit], 1))

    def test_each_stage_of_an_unmerged_entry_but_the_highest_is_not_read(self):
        """An unmerged entry is read only as the highest stage that the index holds for its path.

        Stages 1 and 2 hold an address and stage 3 holds none: the scan passes. The control: with
        the address in stage 3 as well, it fails.
        """
        line, hit = self.address_line()
        held = self.git_out("hash-object", "-w", "--stdin", data=line)
        clean = self.git_out("hash-object", "-w", "--stdin", data=b"text\n")

        def unmerged(third):
            info = "".join("100644 {} {}\tnote.txt\n".format(name, stage)
                           for stage, name in ((1, held), (2, held), (3, third)))
            self.git_out("update-index", "--index-info", data=info.encode("ascii"))
            self.assertEqual(len(self.git_out("ls-files", "--stage").splitlines()), 3)
        unmerged(clean)
        self.assertEqual(scan(self.root, {}), ([], 1))
        unmerged(held)
        self.assertEqual(scan(self.root, {}), (["note.txt:1: email-shaped text, sha256 " + hit], 1))

    def test_the_file_that_a_tracked_symbolic_link_points_to_is_not_read(self):
        """A tracked link to an address-bearing file outside the repository passes.

        The link is read as its own target text, a path that holds no address. The control: the
        same file, tracked in the repository, fails.
        """
        line, hit = self.address_line()
        target = Path(self.tmp.name) / "outside.txt"
        target.write_bytes(line)
        self.add("real.txt", "text\n")
        os.symlink(str(target), self.root / "link.txt")
        self.git("add", "--", "link.txt")
        self.assertEqual(scan(self.root, {}), ([], 2))
        self.add("copy.txt", line.decode("ascii"))
        self.assertEqual(scan(self.root, {}), (["copy.txt:1: email-shaped text, sha256 " + hit], 3))

    def test_a_file_kept_outside_git_is_scanned_only_as_its_stored_pointer(self):
        """A file whose blob is a pointer, as Git LFS stores it, is scanned as that pointer.

        The pointer is staged and the working copy then holds the address, as a checkout that
        fetches the file would; the scan passes. The control: the same text, staged, fails.
        """
        line, hit = self.address_line()
        pointer = ("version https://git-lfs.github.com/spec/v1\noid sha256:" + hashlib.sha256(line).hexdigest()
                   + "\nsize {}\n".format(len(line)))
        self.add("big.bin", pointer)
        (self.root / "big.bin").write_bytes(line)
        self.assertEqual(scan(self.root, {}), ([], 1))
        self.git("add", "--", "big.bin")
        self.assertEqual(scan(self.root, {}), (["big.bin:1: email-shaped text, sha256 " + hit], 1))

    def test_the_content_of_a_submodule_is_not_read(self):
        """A submodule whose checkout holds an address-bearing file passes.

        The control: the same file, tracked in the repository, fails.
        """
        line, hit = self.address_line()
        self.add("real.txt", "text\n")
        (self.root / "sub").mkdir()
        (self.root / "sub" / "note.txt").write_bytes(line)
        self.git("update-index", "--add", "--cacheinfo", "160000," + "1" * 40 + ",sub")
        self.assertEqual(scan(self.root, {}), ([], 1))
        self.add("copy.txt", line.decode("ascii"))
        self.assertEqual(scan(self.root, {}), (["copy.txt:1: email-shaped text, sha256 " + hit], 2))

    def test_a_red_tree_case_prints_every_failure_in_full(self):
        """The tree case, run on a repository with more failures than unittest shows in a diff.

        The failures, as a list, are longer than the default diff limit of unittest, so a list
        comparison would shorten them. The output of the run must hold every failure that the
        scan returns as a whole line, and no address.
        """
        line, _ = self.address_line()
        for index in range(40):
            self.add("f{:02d}.txt".format(index), line.decode("ascii"))
        failures, read = scan(self.root, {})
        self.assertEqual((len(failures), read), (40, 40))
        self.assertGreater(len(repr(failures)), unittest.TestCase.maxDiff)
        stream = io.StringIO()
        tree_case = unittest.defaultTestLoader.loadTestsFromTestCase(NoWorkerIdentifiersInTree)
        with mock.patch.dict(globals(), {"ROOT": self.root, "ALLOWLIST": {}}):
            result = unittest.TextTestRunner(stream=stream, verbosity=0).run(tree_case)
        self.assertEqual((result.testsRun, len(result.failures), len(result.errors)), (1, 1, 0))
        lines = stream.getvalue().splitlines()
        self.assertIn("AssertionError: 40 failure(s) in 40 files read:", lines)
        dropped = [failure for failure in failures if failure not in lines]
        self.assertEqual(len(dropped), 0, "{} of {} failures dropped".format(len(dropped), len(failures)))
        self.assert_no_address(lines)

    # The control characters that must never reach the output raw: every character below 0x20
    # but the line feed that ends each output line, 0x7f, and the 8-bit controls 0x80 to 0x9f,
    # among them the 8-bit control sequence introducer that starts a terminal escape sequence.
    RAW_CONTROLS = frozenset(chr(value) for value in list(range(0x20)) + list(range(0x7F, 0xA0))) - {"\n"}

    def assert_tree_output_escapes(self, names):
        """The tree case, run on 1 file for each path in names, prints each failure as 1 line.

        names holds (path, the escaped text that names it in a failure). Each file holds a hit, so
        each path is named in a failure. The output must hold each failure as a whole line, and no
        character of RAW_CONTROLS and no address.
        """
        line, hit = self.address_line()
        for rel, _ in names:
            self.add(rel, line.decode("ascii"))
        failures, read = scan(self.root, {})
        self.assertEqual((failures, read),
                         ([shown + ":1: email-shaped text, sha256 " + hit for _, shown in sorted(names)],
                          len(names)))
        stream = io.StringIO()
        tree_case = unittest.defaultTestLoader.loadTestsFromTestCase(NoWorkerIdentifiersInTree)
        with mock.patch.dict(globals(), {"ROOT": self.root, "ALLOWLIST": {}}):
            result = unittest.TextTestRunner(stream=stream, verbosity=0).run(tree_case)
        self.assertEqual((result.testsRun, len(result.failures), len(result.errors)), (1, 1, 0))
        output = stream.getvalue()
        raw = sorted({"0x{:02x}".format(ord(char)) for char in output if char in self.RAW_CONTROLS})
        self.assertEqual(raw, [], "raw control characters in the output")
        lines = output.split("\n")
        self.assertIn("AssertionError: {} failure(s) in {} files read:".format(len(names), len(names)), lines)
        dropped = [failure for failure in failures if failure not in lines]
        self.assertEqual(len(dropped), 0, "{} of {} failures not a whole line".format(len(dropped), len(failures)))
        self.assert_no_address(lines)

    def test_a_line_feed_in_a_path_name_is_escaped_in_the_output(self):
        self.assert_tree_output_escapes([("line" + "\n" + "feed.txt", "line" + "\\x0a" + "feed.txt")])

    def test_a_carriage_return_in_a_path_name_is_escaped_in_the_output(self):
        self.assert_tree_output_escapes([("carriage" + "\r" + "return.txt",
                                          "carriage" + "\\x0d" + "return.txt")])

    def test_a_terminal_escape_sequence_in_a_path_name_is_escaped_in_the_output(self):
        # Cursor up 1 line and erase it, once with the escape byte and once with the 8-bit
        # control sequence introducer, each of which would hide an earlier failure line on screen.
        self.assert_tree_output_escapes([
            ("erase" + "\x1b[1A\x1b[2K" + "line.txt", "erase" + "\\x1b[1A\\x1b[2K" + "line.txt"),
            ("csi" + "\x9b1A\x9b2K" + "line.txt", "csi" + "\\u009b1A\\u009b2K" + "line.txt")])

    def test_a_backslash_in_a_path_name_is_escaped_in_the_output(self):
        # A name that holds the 4 characters \x0a and a name that holds a line feed: with the
        # backslash escaped, the 2 names give 2 texts.
        self.assert_tree_output_escapes([
            ("text" + "\\" + "x0afeed.txt", "text" + "\\x5c" + "x0afeed.txt"),
            ("text" + "\n" + "feed.txt", "text" + "\\x0a" + "feed.txt")])

    def test_a_byte_that_is_not_valid_utf_8_in_a_path_name_is_escaped_in_the_output(self):
        # os.fsdecode() gives the byte 0xff as a surrogate, which is written as \xff, the byte. A
        # file system that refuses a name that is not valid UTF-8, as on macOS, skips this case.
        rel = os.fsdecode(b"raw" + b"\xff" + b".txt")
        try:
            (self.root / rel).write_bytes(b"")
            (self.root / rel).unlink()
        except OSError:
            self.skipTest("the file system refuses a name that is not valid UTF-8")
        self.assert_tree_output_escapes([(rel, "raw" + "\\xff" + ".txt")])

    def test_a_bidirectional_override_in_a_path_name_is_escaped_in_the_output(self):
        # A character at U+00A0 or above that is not printable: the right-to-left override,
        # which would show the rest of the failure line reversed on screen.
        self.assert_tree_output_escapes([("bidi" + chr(0x202E) + "txt.md", "bidi" + "\\u202e" + "txt.md")])

    def test_an_astral_character_that_is_not_printable_in_a_path_name_is_escaped_in_the_output(self):
        # A character above U+FFFF that is not printable: a tag character, which a terminal
        # shows as nothing.
        self.assert_tree_output_escapes([("tag" + chr(0xE0041) + "name.txt", "tag" + "\\U000e0041" + "name.txt")])

    def test_a_delete_character_in_a_path_name_is_escaped_as_a_byte_in_the_output(self):
        # DEL, 0x7f, is not printable and lies below 0x80, so it is written as \x7f, the byte, not
        # by the code point form of a character at 0x80 or above.
        self.assert_tree_output_escapes([("del" + chr(0x7F) + "name.txt", "del" + "\\x7f" + "name.txt")])

    def test_a_printable_character_outside_ascii_in_a_path_name_stays_raw_in_the_output(self):
        # A printable letter outside ASCII, in the Latin-1 range and above it, and a printable
        # character above U+FFFF: each stays as it is, and only what is not printable is escaped.
        rel = "caf" + chr(0xE9) + "-" + chr(0x540D) + "-" + chr(0x1D400) + ".txt"
        self.assertTrue(rel.isprintable())
        self.assert_tree_output_escapes([(rel, rel)])


def tree_report(failures, read):
    """The message of a red tree case: a count, then every failure in full, 1 to a line.

    Each failure is 1 line of printable text, since scan() names each path by printable_path()
    or by a digest.
    """
    return "\n".join(["{} failure(s) in {} files read:".format(len(failures), read)] + failures)


class NoWorkerIdentifiersInTree(unittest.TestCase):
    """Every tracked file of this repository holds no hit outside the allowlist.

    A red run prints every failure through tree_report(), never through a list comparison,
    which unittest shortens when it is long.
    """

    def test_every_tracked_file(self):
        failures, read = scan(ROOT, ALLOWLIST)
        if failures:
            self.fail(tree_report(failures, read))
        self.assertGreater(read, 0)


if __name__ == "__main__":
    unittest.main()
