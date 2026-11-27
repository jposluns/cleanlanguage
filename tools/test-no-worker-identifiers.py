#!/usr/bin/env python3
"""Check: no tracked file holds a worker or other third-party email address.

The adopter-owned rule .claude/rules/external/no-worker-identifiers.md bars any worker email
address, account identifier, seat label or other third-party identifier from every public or
potentially public surface of this repository. This suite enforces the email class of that rule
on every file that git ls-files --stage lists at the repository root, the vendored trees .aiqt/,
.baseline/, plugin/, .claude/rules/aiqt/ and .claude/rules/security/ included. A pack update that
imports a third-party address therefore fails here and needs a maintainer decision; the vendored
files are never edited to pass.

The pattern, ADDRESS, is applied to the raw bytes of each file: a local part of ASCII letters,
digits and the characters . _ % + and -, 1 at sign, and a dotted domain whose last label is 2 or
more ASCII letters. Reading bytes keeps every tracked file in scope, images included, with no
decode failure; a reported line number is 1 more than the number of line feeds before the match.
The alphabetic last label keeps out text such as an action pinned to a version tag, whose last
label starts with a digit, or to a 40-character commit, whose domain part holds no dot.

A match passes when the whole match, folded to lower case, is exempt:

1. It is exactly the maintainer's own address, MAINTAINER. This covers the security contact in
   site/.well-known/security.txt, the plugin metadata, the security-txt checker and its tests,
   and the mixed-case form in the vendored specification.
2. Its domain is reserved for documentation: its last label is in RESERVED_LAST_LABELS, or the
   domain is, or ends with a dot and then, 1 of RESERVED_DOMAINS.
3. Its line is in ALLOWLIST, the reviewed set of exact line texts, by file. An allowlist entry
   that is not the exact text of a line of its file that holds a non-exempt match is a failure,
   so the allowlist cannot silently go stale.

It fails closed: a git ls-files that fails, and a listed file that is missing or cannot be read,
are failures that name the cause or the file, never a skip. Entries of mode 120000 and 160000, a
tracked symbolic link and a submodule, are not read.

Each caught example in the self-checks below is assembled at run time from parts, so this file's
own source holds no text that ADDRESS matches and the suite needs no entry for itself.

Residual: the email class only. A seat label, a bare account handle or a numeric account
identifier passes, since a committed pattern that names a real label would itself publish it. An
address split across lines, assembled by code, or written with the word "at" passes; an
untracked file, a tracked symbolic link, a submodule, and an address inside compressed or encoded
binary content pass; an at sign outside ASCII, such as a confusable, passes; a surface that is
not a file in this tree, such as a pull request title, description or comment, is not reached,
and tools/check-pr-text.py carries no identifier pattern today. Accepted false failures: a
legitimate new third-party address is caught and needs a maintainer decision, and an
email-shaped text that is no address is caught and is reworded to a reserved domain, or is added
to ALLOWLIST after review.
"""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ADDRESS = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# The maintainer's own address, the only real address that this repository may hold.
MAINTAINER = "jeff" + "@" + "posluns.ca"
RESERVED_LAST_LABELS = ("invalid", "test", "example")
RESERVED_DOMAINS = ("example.com", "example.org", "example.net")
# The modes of a symbolic link and of a submodule in the output of git ls-files --stage.
UNREAD_MODES = ("120000", "160000")

# Reviewed lines whose match is no worker or third-party address, each the exact text of the
# line: a URL-userinfo fixture at the project's own domain, which the release-link tests use as
# a redirect form that the checker must refuse.
ALLOWLIST = {
    "tools/test-release-links.py": (
        "        (\"/r https://" + "user" + "@" + "cleanlanguage.ai/downloads/a.md 301\", \"form\"),",
    ),
}


def exempt(match):
    """Whether a whole match of ADDRESS, folded to lower case, is an exempt address."""
    text = match.decode("ascii").lower()
    if text == MAINTAINER:
        return True
    domain = text.rpartition("@")[2]
    if domain.rpartition(".")[2] in RESERVED_LAST_LABELS:
        return True
    return any(domain == name or domain.endswith("." + name) for name in RESERVED_DOMAINS)


def tracked_files(root):
    """(repository-relative path, mode) for each entry that git ls-files --stage lists at root.

    Each path appears 1 time, in sorted order. A git ls-files that fails raises
    subprocess.CalledProcessError, and a git that cannot be started raises OSError.
    """
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "--stage", "-z"],
                            capture_output=True, check=True, stdin=subprocess.DEVNULL).stdout
    entries = {}
    for entry in listed.split(b"\0"):
        if entry:
            info, _, path = entry.partition(b"\t")
            entries[os.fsdecode(path)] = info.split()[0].decode("ascii")
    return sorted(entries.items())


def hits_in(data):
    """(line number, line text) for each non-exempt match of ADDRESS in the bytes data."""
    found = []
    for match in ADDRESS.finditer(data):
        if exempt(match.group(0)):
            continue
        start = data.rfind(b"\n", 0, match.start()) + 1
        end = data.find(b"\n", match.end())
        line = data[start:] if end < 0 else data[start:end]
        found.append((data.count(b"\n", 0, match.start()) + 1, line.decode("utf-8", "replace")))
    return found


def scan(root, allowlist):
    """(failures, number of files read) for the tracked files at root under allowlist.

    A failure is a line of text: a hit as path:line: text, a file that cannot be read, a stale
    allowlist entry, or a git ls-files that fails.
    """
    try:
        entries = tracked_files(root)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or b"").decode("utf-8", "replace").strip()
        return ["git ls-files failed: exit {} {}".format(error.returncode, detail)], 0
    except OSError as error:
        return ["git ls-files failed: {}".format(error)], 0
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
        for number, line in hits_in(data):
            if line in allowlist.get(rel, ()):
                used.add((rel, line))
                continue
            failures.append("{}:{}: {}".format(rel, number, line.strip()))
    for rel, lines in sorted(allowlist.items()):
        for line in lines:
            if (rel, line) not in used:
                failures.append("{}: stale allowlist entry, no line with a non-exempt match: {}".format(
                    rel, line.strip()))
    return failures, read


def caught(local, domain):
    """An address assembled from its parts, so that this source holds no matchable text."""
    return local + "@" + domain


class PatternSelfCheck(unittest.TestCase):
    """The pattern and each exemption, pinned with examples assembled at run time."""

    PLACEHOLDER_DOMAIN = "placeholder-mail" + "." + "com"

    def matches(self, text):
        return [match.group(0).decode("ascii") for match in ADDRESS.finditer(text.encode("ascii"))]

    def test_a_third_party_address_is_caught(self):
        address = caught("worker-label-example", self.PLACEHOLDER_DOMAIN)
        self.assertEqual(self.matches("contact " + address + " today"), [address])
        self.assertEqual(hits_in(("x\nby " + address + "\n").encode("ascii")), [(2, "by " + address)])

    def test_the_maintainer_address_in_any_case_is_exempt(self):
        for text in (MAINTAINER, MAINTAINER.upper(), "Jeff" + "@" + "Posluns.ca"):
            with self.subTest(text=text):
                self.assertEqual(hits_in(("Contact: mailto:" + text + "\n").encode("ascii")), [])

    def test_a_longer_address_at_the_maintainer_domain_is_caught(self):
        address = caught("other", "posluns" + "." + "ca")
        self.assertEqual(len(hits_in(address.encode("ascii"))), 1)

    def test_reserved_documentation_domains_are_exempt(self):
        for domain in ("example" + "." + "invalid", "x" + "." + "test", "host" + "." + "example",
                       "example" + "." + "com", "mail.example" + "." + "org", "example" + "." + "net"):
            with self.subTest(domain=domain):
                self.assertEqual(hits_in(caught("fixture", domain).encode("ascii")), [])

    def test_a_domain_that_only_contains_a_reserved_name_is_caught(self):
        for domain in ("notexample" + "." + "com", "example.com" + "." + "co", "testing" + "." + "io"):
            with self.subTest(domain=domain):
                self.assertEqual(len(hits_in(caught("worker", domain).encode("ascii"))), 1)

    def test_non_addresses_are_not_matched(self):
        pin = "actions/checkout" + "@" + "v4.4.0"
        commit = "actions/checkout" + "@" + "0123456789abcdef0123456789abcdef01234567"
        for text in (pin, commit, "the maintainer, Jeff Posluns", "a @ b . co", "user" + "@" + "host"):
            with self.subTest(text=text):
                self.assertEqual(self.matches(text), [])

    def test_this_source_holds_no_matchable_text(self):
        self.assertEqual(ADDRESS.findall(Path(__file__).read_bytes()), [])


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
        self.add("a.txt", "Contact: mailto:" + MAINTAINER + "\n" + caught("t", "x" + "." + "invalid") + "\n")
        self.assertEqual(scan(self.root, {}), ([], 1))

    def test_a_planted_address_fails_naming_path_and_line(self):
        address = caught("worker-label-example", "placeholder-mail" + "." + "com")
        self.add("docs/note.md", "first\nsecond " + address + "\n")
        failures, _ = scan(self.root, {})
        self.assertEqual(failures, ["docs/note.md:2: second " + address])

    def test_an_allowlisted_line_passes_and_a_stale_entry_fails(self):
        line = "url https://" + caught("user", "project" + "." + "ai") + "/a"
        self.add("t.py", line + "\n")
        self.assertEqual(scan(self.root, {"t.py": (line,)}), ([], 1))
        failures, _ = scan(self.root, {"t.py": (line + " moved",)})
        self.assertEqual(len(failures), 2, failures)
        self.assertTrue(failures[0].startswith("t.py:1: "), failures)
        self.assertIn("stale allowlist entry", failures[1])

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
        self.assertTrue(failures[0].startswith("git ls-files failed: "), failures)

    def test_an_empty_listing_fails(self):
        failures, _ = scan(self.root, {})
        self.assertEqual(len(failures), 1, failures)
        self.assertTrue(failures[0].startswith("git ls-files listed no file"), failures)

    def test_a_symbolic_link_is_not_read(self):
        self.add("real.txt", "text\n")
        os.symlink("real.txt", self.root / "link.txt")
        self.git("add", "--", "link.txt")
        self.assertEqual(scan(self.root, {}), ([], 1))


class NoWorkerIdentifiersInTree(unittest.TestCase):
    """Every tracked file of this repository holds no non-exempt email-shaped text."""

    def test_every_tracked_file(self):
        failures, read = scan(ROOT, ALLOWLIST)
        self.assertEqual(failures, [], "{} failure(s) in {} files read".format(len(failures), read))
        self.assertGreater(read, 0)


if __name__ == "__main__":
    unittest.main()
