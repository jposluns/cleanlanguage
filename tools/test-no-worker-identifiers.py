#!/usr/bin/env python3
"""Check: no tracked file holds a worker or other third-party email address.

The adopter-owned rule .claude/rules/external/no-worker-identifiers.md bars any worker email
address, account identifier, seat label or other third-party identifier from every public or
potentially public surface of this repository. This suite enforces the email class of that rule
on every file that git ls-files --stage lists at the repository root, the vendored trees .aiqt/,
.baseline/, plugin/, .claude/rules/aiqt/ and .claude/rules/security/ included. A pack update that
imports a third-party address therefore fails here and needs a maintainer decision; the vendored
files are never edited to pass.

Candidates, read from the raw bytes of each file by candidates(). The scan visits every at sign,
so no candidate can hide another. Around each at sign it takes the local part, the longest run of
ASCII letters, digits and the characters . _ % + and - that ends right before it, and the domain
run, the longest run of ASCII letters, digits, dots and hyphens that starts right after it. Neither
run holds an at sign, so the domain run of 1 at sign can be the local part of the next, and both
are read. Each dot of the domain run that has at least 1 byte of the run before it and 2 or more
ASCII letters right after it ends a domain after those letters, and each such domain gives a
candidate: the local part, the at sign and that domain. So a reserved name at the end of a longer
domain run cannot hide the candidate that stops before it. Reading bytes keeps every tracked file
in scope, images included, with no decode failure.

Work. Each byte is read a bounded number of times: once in a local part, once in a domain run and
once more for the letters after a dot, and each candidate is tested with slices no longer than
its last label or an exempt name. So the work grows linearly with the size of a file, and text
that holds no at sign costs 1 search for it.

The alphabetic last label keeps out text such as an action pinned to a plain version tag, whose
last label starts with a digit, or to a 40-character commit, whose domain part holds no dot.

A candidate is exempt when, folded to lower case:

1. It is exactly the maintainer's own address, MAINTAINER. This covers the security contact in
   site/.well-known/security.txt, the plugin metadata, the security-txt checker and its tests,
   and the mixed-case form in the vendored specification.
2. Its domain is reserved for documentation: its last label is in RESERVED_LAST_LABELS, or the
   domain is, or ends with a dot and then, 1 of RESERVED_DOMAINS.

An at sign is a hit when 1 or more of its candidates is not exempt; it is reported 1 time. A hit
passes when its line is in ALLOWLIST, the reviewed set of exact line texts, by file, for
email-shaped text that is no address. An allowlist entry that is not the exact text of a line of
its file that holds a hit is a failure, so the allowlist cannot silently go stale.

Report. A failure names the file, the line number, 1 more than the number of line feeds before
the hit, and the first 16 hexadecimal digits of the sha256 of the hit, the longest candidate of
its at sign that is not exempt. It never holds the text of the hit or of its line, so a leaked
address is not copied into the CI log. A stale allowlist entry is named by its file, its position
and the same digest of its text.

It fails closed: a git ls-files that fails or that cannot be started, and a listed file that is
missing or cannot be read, are failures that name the cause or the file, never a skip. Entries of
mode 120000 and 160000, a tracked symbolic link and a submodule, are not read.

Each caught example in the self-checks below is assembled at run time from parts, so this file's
own source holds no text that candidates() takes as a candidate and the suite needs no entry for
itself.

Residual: the email class only. A seat label, a bare account handle or a numeric account
identifier passes, since a committed pattern that names a real label would itself publish it. An
address split across lines, assembled by code, or written with the word "at" passes; an
untracked file, a tracked symbolic link, a submodule, and an address inside compressed or encoded
binary content pass; an at sign outside ASCII, such as a confusable, passes; a surface that is
not a file in this tree, such as a pull request title, description or comment, is not reached,
and tools/check-pr-text.py carries no identifier pattern today. The digest in a failure lets a
reader who already holds a guess of the address confirm the guess; it does not reveal the address.
Accepted false failures: a legitimate new third-party address is caught and needs a maintainer
decision; an email-shaped text that is no address is caught and is reworded to a reserved domain,
or is added to ALLOWLIST after review; and an action pinned to a version tag with a dotted
prerelease label of 2 or more letters before a final number is caught, since its domain then ends
at that label.
"""
import hashlib
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LETTER_BYTES = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
DOMAIN_BYTES = LETTER_BYTES | frozenset(b"0123456789.-")
LOCAL_BYTES = DOMAIN_BYTES | frozenset(b"_%+")
# The maintainer's own address, the only real address that this repository may hold.
MAINTAINER = "jeff" + "@" + "posluns.ca"
RESERVED_LAST_LABELS = ("invalid", "test", "example")
RESERVED_DOMAINS = ("example.com", "example.org", "example.net")
# The modes of a symbolic link and of a submodule in the output of git ls-files --stage.
UNREAD_MODES = ("120000", "160000")
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


def tracked_files(root, git=GIT):
    """(repository-relative path, mode) for each entry that git ls-files --stage lists at root.

    Each path appears 1 time, in sorted order. A git ls-files that fails raises
    subprocess.CalledProcessError, and a git that cannot be started raises OSError.
    """
    listed = subprocess.run([git, "-C", str(root), "ls-files", "--stage", "-z"],
                            capture_output=True, check=True, stdin=subprocess.DEVNULL).stdout
    entries = {}
    for entry in listed.split(b"\0"):
        if entry:
            info, _, path = entry.partition(b"\t")
            entries[os.fsdecode(path)] = info.split()[0].decode("ascii")
    return sorted(entries.items())


def scan(root, allowlist, git=GIT):
    """(failures, number of files read) for the tracked files at root under allowlist.

    A failure is a line of text: a hit as path:line: and a digest, a file that cannot be read, a
    stale allowlist entry, or a git ls-files that fails or cannot be started. No failure holds
    the text of a hit or of its line.
    """
    try:
        entries = tracked_files(root, git)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or b"").decode("utf-8", "replace").strip()
        return ["git ls-files failed: exit {} {}".format(error.returncode, detail)], 0
    except OSError as error:
        return ["git ls-files failed: git could not be started: {}".format(error)], 0
    if not entries:
        return ["git ls-files listed no file at {}".format(root)], 0
    failures = []
    read = 0
    used = set()
    for rel, mode in entries:
        if mode in UNREAD_MODES:
            continue
        try:
            data = (Path(root) / rel).read_bytes()
        except OSError as error:
            failures.append("{}: unreadable: {}".format(rel, error.strerror or error))
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
            failures.append("{}:{}: email-shaped text, sha256 {}".format(rel, number, hit))
    for rel, lines in sorted(allowlist.items()):
        for position, line in enumerate(lines, 1):
            if (rel, line.encode("utf-8")) not in used:
                failures.append("{}: stale allowlist entry {}, no line that holds a hit, sha256 {}".format(
                    rel, position, digest(line.encode("utf-8"))))
    return failures, read


def caught(local, domain):
    """An address assembled from its parts, so that this source holds no matchable text."""
    return local + "@" + domain


class PatternSelfCheck(unittest.TestCase):
    """The candidates and each exemption, pinned with examples assembled at run time.

    Each exemption case first asserts that the text gives the candidate it exempts.
    """

    PLACEHOLDER_DOMAIN = "placeholder-mail" + "." + "com"

    def texts(self, text):
        data = text.encode("ascii")
        return [data[start:end].decode("ascii") for start, _, ends in candidates(data) for _, end in ends]

    def digests(self, text):
        return [hit for _, _, _, hit in hits_in(text.encode("ascii"))]

    def test_a_third_party_address_is_caught(self):
        address = caught("worker-label-example", self.PLACEHOLDER_DOMAIN)
        self.assertEqual(self.texts("contact " + address + " today"), [address])
        line = "by " + address
        self.assertEqual(hits_in(("x\n" + line + "\n").encode("ascii")),
                         [(2, 2, 2 + len(line), digest(address.encode("ascii")))])

    def test_an_exempt_candidate_hides_no_other(self):
        # A prefix, an at sign, a dotted local part that ends in a reserved label, a 2nd at sign and
        # a non-reserved domain: the 2nd at sign gives its own candidate, which is caught.
        address = caught("w." + "example", self.PLACEHOLDER_DOMAIN)
        self.assertEqual(self.digests(address), [digest(address.encode("ascii"))])
        masked = "p" + "@" + address
        self.assertEqual(self.texts(masked), [caught("p", "w." + "example"), address])
        self.assertEqual(self.digests(masked), [digest(address.encode("ascii"))])
        # The maintainer's address in front of a 2nd at sign hides nothing either.
        behind = MAINTAINER + "@" + self.PLACEHOLDER_DOMAIN
        self.assertEqual(self.texts(behind), [MAINTAINER, caught("posluns.ca", self.PLACEHOLDER_DOMAIN)])
        self.assertEqual(len(self.digests(behind)), 1)
        # A reserved last label after the domain hides nothing: the shorter domain is caught.
        plain = caught("worker", self.PLACEHOLDER_DOMAIN)
        suffixed = plain + "." + "example"
        self.assertEqual(self.texts(suffixed), [plain, suffixed])
        self.assertEqual(self.digests(suffixed), [digest(plain.encode("ascii"))])

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

    def test_reserved_documentation_domains_are_exempt(self):
        for domain in ("example" + "." + "invalid", "x" + "." + "test", "host" + "." + "example",
                       "example" + "." + "com", "mail.example" + "." + "org", "example" + "." + "net",
                       "X" + "." + "TEST", "Example" + "." + "Com"):
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

    def test_non_addresses_are_not_matched(self):
        pin = "actions/checkout" + "@" + "v4.4.0"
        commit = "actions/checkout" + "@" + "0123456789abcdef0123456789abcdef01234567"
        for text in (pin, commit, "the maintainer, Jeff Posluns", "a @ b . co", "user" + "@" + "host",
                     "a" + "@" + "b.c", "a" + "@" + ".com", "@" + "host.com", "x" + "@" + "host.c1"):
            with self.subTest(text=text):
                self.assertEqual(self.texts(text), [])

    def test_a_prerelease_version_tag_is_caught(self):
        # The accepted false failure that the residual states: the domain ends at the prerelease label.
        pin = "actions/checkout" + "@" + "v1.2.3-alpha.beta.1"
        self.assertEqual(self.texts(pin), ["checkout" + "@" + "v1.2.3-alpha.beta"])
        self.assertEqual(len(hits_in(pin.encode("ascii"))), 1)

    def test_long_address_free_text_costs_bounded_work(self):
        # About 150000 bytes each, with no candidate: a run with no at sign, a long local part and a
        # long dotted domain run, many at signs, and many dots. A search that retries the local part
        # from every byte takes many seconds on the first.
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

    def add(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        self.git("add", "--", rel)

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
                                    + digest(address.encode("ascii"))])
        self.assertNotIn("worker-label-example", failures[0])
        self.assertNotIn("second", failures[0])

    def test_a_masked_address_fails(self):
        address = caught("w." + "example", "placeholder-mail" + "." + "com")
        self.add("m.txt", "p" + "@" + address + "\n")
        failures, _ = scan(self.root, {})
        self.assertEqual(failures, ["m.txt:1: email-shaped text, sha256 " + digest(address.encode("ascii"))])

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
                         + digest(moved.encode("ascii")))

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

    def test_a_missing_tracked_file_fails_naming_it(self):
        self.add("gone.txt", "text\n")
        (self.root / "gone.txt").unlink()
        failures, _ = scan(self.root, {})
        self.assertEqual(len(failures), 1, failures)
        self.assertTrue(failures[0].startswith("gone.txt: unreadable: "), failures)

    def test_an_unreadable_tracked_file_fails_naming_it(self):
        self.add("odd.txt", "text\n")
        (self.root / "odd.txt").unlink()
        (self.root / "odd.txt").mkdir()
        failures, _ = scan(self.root, {})
        self.assertEqual(len(failures), 1, failures)
        self.assertTrue(failures[0].startswith("odd.txt: unreadable: "), failures)

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

    def test_a_symbolic_link_is_not_read(self):
        self.add("real.txt", "text\n")
        os.symlink("real.txt", self.root / "link.txt")
        self.git("add", "--", "link.txt")
        self.assertEqual(scan(self.root, {}), ([], 1))

    def test_a_submodule_is_not_read(self):
        # A submodule entry with no checkout behind it, which a read would report as missing.
        self.add("real.txt", "text\n")
        self.git("update-index", "--add", "--cacheinfo", "160000," + "1" * 40 + ",sub")
        self.assertEqual(scan(self.root, {}), ([], 1))


class NoWorkerIdentifiersInTree(unittest.TestCase):
    """Every tracked file of this repository holds no hit outside the allowlist."""

    def test_every_tracked_file(self):
        failures, read = scan(ROOT, ALLOWLIST)
        self.assertEqual(failures, [], "{} failure(s) in {} files read".format(len(failures), read))
        self.assertGreater(read, 0)


if __name__ == "__main__":
    unittest.main()
