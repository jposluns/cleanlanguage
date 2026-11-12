#!/usr/bin/env python3
"""Lint: the repository's sources carry no internal review-history labels.

A comment or docstring that names the review pass or the finding that once motivated it, such as
"(F1)", "finding S3" or a numbered pass or finding of the kinds the fixtures below hold, or that
credits a model family with a finding, such as "codex reproduced" or "the gemini seed", means
nothing to a later reader and mixes numbering schemes. Such text states the reason itself, in place
of the label.

The test scans each file in SCANNED in two ways. Every physical line is matched against
LABEL_PATTERNS. Every prose block is matched against both sets. A prose block is, in a Python
file, a run of comments on consecutive lines or a string statement such as a docstring, and
elsewhere a paragraph of consecutive non-blank lines. A comment run or a paragraph is matched line
by line and then as one text with all its line breaks joined, so a label spread over any number of
lines is caught and reported at the line where it starts. A string statement is matched once, as a
whole, on its decoded value as Python builds it, and each match is reported at the physical line
where it starts, so a label spread over its lines is caught there too. The value match does not
split a value that Python reads as exempt or as a longer word or id into lines or parts that would
read otherwise, but each physical line of the statement is still matched against LABEL_PATTERNS
as source text, as every line is, so a part of such a value can still be caught on its own line,
an accepted false failure listed below. Docstrings are found with ast.get_docstring, so the
docstring of a one-line suite counts too, and a string statement may be a plain, f-string,
template string or bytes literal. Its prose is read from the parsed literal, never cut from the
source: the decoded text of a plain or bytes literal, and only the top-level literal text of an
f-string or template string, whose replacement fields are code and each read as one space, the whole
field: any format spec or nested literal and, in a self-documenting field such as {x = }, the
expression, the = and the spaces around it, which Python also puts into the value. Each part of an
implicitly concatenated literal is read from its own delimiter, with its own prefix, and joined to
the next part as Python joins them, with nothing between, and a backslash that ends a line of a part
joins the next line with nothing between, while an unpaired backslash, one left over after the pairs
before it, just before a replacement field, which escapes nothing, stays the backslash Python keeps;
a line break inside one part, written or escaped, is the newline it is, with the space around
it stripped. Every pattern but the round number pattern reads a line break, in a string value or
between the lines of a comment run or paragraph, as one space; the round number pattern keeps it, so
a letter exempts a colon round number only on the line of the number. Before Python 3.12 the
tokenizer does not separate the fields of an f-string, so an f-string statement fails the scan
there. PROSE_PATTERNS holds the widened bare finding id, which applies to prose only because code
legitimately carries short identifiers such as the closure value "C1". A match on a line in
ALLOWLIST, the reviewed set of lines whose match is a cross-reference to a named plan rather than a
review label, passes. A scanned file that is missing, unreadable or does not tokenize and parse is a
failure, never a skip, and an allowlist entry that no longer matches a scanned line is a failure
too, so the allowlist cannot silently go stale.

A second, narrower pass, the history pass, reads every file that git ls-files lists under
HISTORY_SCOPE (tools/, site-src/ and .github/), the files that the backlog probes read with git
grep, as git grep reads it, split at each line feed only, so a carriage return stays in its line and
each line has the number git grep gives it, and matches each physical line against HISTORY_PATTERNS:
the 5 patterns of LABEL_PATTERNS that HISTORY_LABEL_NAMES names, and the 2 backlog probes that the
pass must fail on, each the git grep -i probe of its backlog row written as a case-insensitive
Python pattern whose word boundary counts only an ASCII letter, digit or underscore as a word
character, as git grep does in the C locale. It skips only the fixture lines of this lint, the file
FIXTURE_FILE names: a line of an assignment of data, made directly in the body of a class at the top
level of this lint to names that FIXTURE_NAMES lists for that class, that lies between a comment
line that is FIXTURE_START and the next comment line that is FIXTURE_END and holds no comment, where
an assignment of data is one whose value holds no call, lambda, comprehension or formatted string.
Every other line of this lint is read: its docstrings, its comments and its test code, and any
comment or other statement inside a fixture block, an assignment to another name or in a function or
a nested class among them, and a string line that reads as a marker opens and closes no block. The
HistoryPatternSelfCheck case pins those 7 patterns, and the scope, the fixture rule and the reading
of tracked files, against a run of git grep, are pinned too. Two classes at the top level of this
lint that share a name are a failure. FixtureNameRegistry, a static check of the source, fails when
a name in FIXTURE_NAMES is not a fixture of its class or is read by no method of that class other
than as a message argument of an assert call; it cannot tell an example from other data, so a name
read only through self.fail, an alias, subTest(msg=...) or len passes it, and so does a class that a
later binding of its name, other than a second class, hides from unittest. These patterns name a
review pass or a finding by number and match no plan or contract id, so the pass covers files whose
ids would fail the full patterns, such as tools/test-ci-status.sh, whose $C1 and $C2 read as bare
ids. A tracked file that cannot be read as UTF-8, or that is missing, is a failure that names the
file, and so are a fixture block left open, a carriage return in this lint and a git ls-files that
fails. Its residuals: it matches single lines only, so a label split across lines or written in
words passes; it reads no untracked file, as git grep reads none; it reads no tracked symbolic link
and no submodule, as git grep reads neither, so the file that a tracked link points to is read only
when it is itself a tracked file in the 3 folders; and it reads no tracked file outside them, among
them .aiqt/, the adopted governance files, .baseline/, the pinned upstream package, whose
SPECIFICATION.md has a line that the backlog probe of numbered review rounds matches, and plugin/,
the vendored hooks, whose aiqt_hooks.py has lines that the backlog probe of numbered findings and
rounds matches. Its accepted false failures: ordinary text in which a space and a digit follow the
word discovery, verify, finding or round, in any case, such as a count of files to verify or of
files found, or a plain round number that a letter or a decimal continuation follows, which
LABEL_PATTERNS exempts, is caught, and is reworded; so is a line that the first probe matches only
because a letter or digit outside ASCII comes just before its first word, which git grep passes
under C.UTF-8 and fails under LC_ALL=C; and so is a line in which a capital I with a dot above,
U+0130, stands for an i of a word of a history pattern, as in the forms DOTTED_CAPITAL_I holds,
which neither probe matches under either locale and the pass fails, since the case-insensitive
matching of Python folds that letter to i. A dotless i, U+0131, or a long s, U+017F, in place of an
i or an s of a probe word, as in the forms C_UTF8_FOLDS holds, is caught too, and is no false
failure, since a probe matches such a line under C.UTF-8.

Run with --probe PATH... to apply the same scan to any files or directories, for example the
whole tools/ directory: it prints every hit and every unreadable file, and exits 1 when there is
one.

Residual: this lint is a best-effort guard, not a complete one. Its patterns are a denylist over
prose, and its residual is open-ended: a label in any phrasing, synonym or layout the patterns do
not list passes, and no list of known gaps can close that set. Completeness over the class of
review-history labels therefore rests on an independent search of the scanned files, not on this
lint. The known residual forms are these: a review pass named in words ("the third review"); a round
number, in the plain form or the colon form, that one rule exempts, because a letter of any script,
any character of Unicode category L, follows it, directly in the plain form, as in "round-7th" or
"round-7a", and on the same line with or without a space between, a line being a physical line of a
comment or paragraph and a line of the decoded value of a string statement, in the colon form, as in
the text "round: 7 decimal places" or a time in microseconds written with the micro sign or the
Greek mu, or because a decimal continuation follows it, as in "round-7.5" or "round: 7.5"; a round
number written in decimal digits other than the ASCII digits 0 to 9, such as Arabic-Indic or
fullwidth digits, which neither form matches; a finding id of three or more capital letters or of
more than two digits; a finding id with a hyphen or a letter suffix, such as "the F-1 case" or "the
F1a case", anywhere outside parentheses and the word "finding"; in prose, a bare id that follows
"point " or starts with "PR" (the forms the plan uses for its open points and pull-request slices),
exclusions the code-line bare id pattern does not make, so "point F1" is still caught on any line; a
reviewer named other than as codex, claude or gemini; a family name more than two words away from
its review or credit word, or credited by a verb outside REVIEW_WORD; in a Python file, a label
split across two lines of a string that is not a statement of its own, such as an argument or an
assigned value, which is matched line by line only; in an f-string or template string statement, a
label inside a replacement field or its format spec, which is code and so is matched only line by
line against LABEL_PATTERNS, never against PROSE_PATTERNS or across a line break, and a label that a
replacement field interrupts, whose place reads as one space; and a bare id in code that does not
use one of the letters of the code-line bare id pattern. Both round number forms also have false
failures, accepted as low severity: a round number that the rule above does not exempt is caught in
either form, even in ordinary text, whatever follows it, including the end of the text. Examples,
not a complete list: in the colon form, a word that follows the number only on the next line in the
sense above does not exempt it, so such a line fails until reflowed to keep the word on the line of
the number; in the plain form, a word after a space does not exempt it; in either form, a number
that a bracket, a percent sign, an arrow, an underscore or a numeric character that is not a letter,
such as superscript two, a vulgar fraction or a Roman numeral sign, follows is caught; and in a
Python file, where both forms are matched against every physical line of code as well as of prose,
ordinary arithmetic and identifiers in code, such as the lines that CODE_FALSE_FAILURES holds, are
caught. Code lines stay matched because a label in a string literal that is not a statement of its
own, such as an assertion message, would otherwise pass. A further accepted false failure: in an
f-string or template string statement, the one space that stands for a replacement field can
complete a label in the decoded text, so the text "fix", a field and the text "round" written
together read as the label of a round of fixes and are caught. A further accepted false failure:
ordinary text in which the word finding or findings, a space and an optional number sign come before
a number, such as a count of files found, is caught by the numbered finding pattern, in every file
this lint scans in full and, through the history pass, in tools/, site-src/ and .github/. The
pattern is kept this wide because the plural and the number sign are forms that a label takes too,
as in a list of numbered findings or a finding named by a number sign. Neither backlog probe matches
those 2 forms, so in the 3 folders the singular form, which the first probe matches too, costs
nothing more there, while the plural and the number-sign forms are a cost of this pattern alone,
which the NUMBERED_FINDING_ONLY fixtures pin. A further accepted false failure: in a Python file,
each physical line of a string statement is matched against LABEL_PATTERNS as source text as well as
in the value, so a physical line that matches LABEL_PATTERNS on its own is caught there even where
the value reads otherwise. Such a line can hold an id or a round number that the rest of the value
completes into a longer id or an exempt round number, from a later part of an implicitly
concatenated literal, from the next line after a joining backslash or from an escape later on the
same line, as in the parts "the F1" and "00 case", whose value reads as the id F100, and in the
samples of VALUE_LINE_FALSE_FAILURES. A physical line that matches no pattern of LABEL_PATTERNS on
its own is not caught this way, so a value that reads as a longer id or an exempt round number
passes when no line of it matches on its own. The PatternSelfCheck case pins the forms the patterns
are known to cover, a letter of each Unicode letter category that exempts either form, the ordinary
code and prose they must not flag, these accepted false failures, a second round number match of
each form in one searched text, the earlier match when both forms match one searched text and, for
each Python placement, the literal set of forms it skips because they would end its string literal
early and leave source that does not tokenize or parse, so a pattern weakened or widened past any of
those sets fails the suite.
"""
import ast
import bisect
import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import tokenize
import unicodedata
import unittest
import warnings
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

# The files scanned with every pattern, repository-relative: the files the orchestration work owns,
# every workflow, the 2 launch scans, and tools/check-release-checksum-live.py,
# tools/test-release-checksum-live.py and tools/test-skill-release-date.py.
SCANNED = (
    ".aiqt/config.md",
    ".claude/hooks/ask_mode_guard.py",
    ".github/workflows/agent-plugin-manifest.yml",
    ".github/workflows/ci-status-test.yml",
    ".github/workflows/install-page.yml",
    ".github/workflows/link-check.yml",
    ".github/workflows/manifest-icon.yml",
    ".github/workflows/orchestration-registry.yml",
    ".github/workflows/page-metadata.yml",
    ".github/workflows/pages-build.yml",
    ".github/workflows/plugin-drift.yml",
    ".github/workflows/plugin-validate.yml",
    ".github/workflows/portable-text-sync.yml",
    ".github/workflows/release-checksum-live.yml",
    ".github/workflows/release-dry-run.yml",
    ".github/workflows/release-skill.yml",
    ".github/workflows/site-draft.yml",
    ".github/workflows/site-hardening.yml",
    ".github/workflows/sitemap.yml",
    ".github/workflows/skill-discovery.yml",
    ".github/workflows/workflow-isolation.yml",
    "tools/check-flow-mode.py",
    "tools/check-orchestration-registry.py",
    "tools/check-release-checksum-live.py",
    "tools/migrate-todo-aei.py",
    "tools/orch-enumerate-backlog.py",
    "tools/orch_doctor.py",
    "tools/test-ask-mode-guard.py",
    "tools/test-check-flow-mode.py",
    "tools/test-orch-enumerate-backlog.py",
    "tools/test-orch-migrate-todo.py",
    "tools/test-orch-stage1-hooks.py",
    "tools/test-orch-stage2-hooks.py",
    "tools/test-orchestration-registry.py",
    "tools/test-release-checksum-live.py",
    "tools/test-shell-launch-isolation.py",
    "tools/test-skill-release-date.py",
    "tools/test-workflow-launch-isolation.py",
)

FAMILY = r"(?:codex|claude|gemini)"
REVIEW_WORD = (r"(?:reproduc\w*|found|finds|finding\w*|refut\w*|flag\w*|raised|raises"
               r"|caught|spotted|spots|noticed|notices|confirmed|confirms"
               r"|seeds?|review\w*|QA|rounds?)")
NEAR = r"(?:\W+\w+){0,2}?\W+"


class RoundNumberPattern:
    """The review round number pattern, whose two forms are exempt only before a letter.

    One rule decides the plain form, the word round or rounds, then any hyphens or spaces, an
    optional number sign and a number, and the colon form, the word, a colon and a number, with any
    spaces around the colon: a round number passes only when a letter of any script, a character
    whose Unicode category starts with L, follows it, directly in the plain form and after any
    spaces on the same line of the searched text in the colon form, or when a decimal continuation
    follows it. So "round-7th", "round-7a", "round-7.5", "round: 7 decimal places", a time in
    microseconds and "round: 7.5" pass. Any other ending, or the end of the text, is caught: in the
    plain form a space before a word, in the colon form a line break before a word, and in either
    form a closing quote, a bracket, a mark, an underscore or a numeric character that is not a
    letter (superscript two, a vulgar fraction or a Roman numeral sign). The re module has no letter
    class, and its word boundary counts those numeric characters and the underscore as word
    characters, so the letter test is made in code, and search returns a match the way
    re.Pattern.search does. Prose is searched for this pattern with its line breaks kept, so a
    letter on the next line never exempts the colon form.

    The matches of both forms are found once for each text searched and kept, so the run of
    searches made over one joined block or string value, one from every start position, costs time
    linear in the text instead of a rescan of every remaining exempt match for each match.
    A kept match is the match a search from any position up to its start would return: the re
    module tests a word boundary against the whole text, not only from the search position, and
    every match of either form starts where the word round starts and holds no other such start,
    so a search from a later position cannot find a match that starts inside an earlier one.
    """

    PLAIN = re.compile(r"(?i)\brounds?[-\s]*#?[0-9]+(?!\.?[0-9])")
    COLON = re.compile(r"(?i)\brounds?\s*:\s*#?[0-9]+(?!\.?[0-9])")
    SPACE = re.compile(r"[^\S\n]*")

    def __init__(self):
        self.text = None
        self.plain = self.colon = ()
        self.plain_starts = self.colon_starts = ()

    @staticmethod
    def letter_at(text, at):
        """Whether the character of text at index at is a letter."""
        return at < len(text) and unicodedata.category(text[at]).startswith("L")

    def letter_follows(self, text, match):
        """Whether a letter follows match in text, after any spaces on the same line."""
        return self.letter_at(text, self.SPACE.match(text, match.end()).end())

    def index(self, text):
        """Find and keep the unexempt matches of both forms in text, once per text."""
        if text is not self.text:
            self.plain = tuple(match for match in self.PLAIN.finditer(text)
                               if not self.letter_at(text, match.end()))
            self.colon = tuple(match for match in self.COLON.finditer(text)
                               if not self.letter_follows(text, match))
            self.plain_starts = tuple(match.start() for match in self.plain)
            self.colon_starts = tuple(match.start() for match in self.colon)
            self.text = text

    @staticmethod
    def first_from(matches, starts, pos):
        """The first of matches that starts at or after pos, or None."""
        at = bisect.bisect_left(starts, pos)
        return matches[at] if at < len(matches) else None

    def colon_search(self, text, pos):
        """The first colon-form match at or after pos that no letter follows, or None."""
        self.index(text)
        return self.first_from(self.colon, self.colon_starts, pos)

    def search(self, text, pos=0):
        """The earliest match of either form at or after pos, or None."""
        self.index(text)
        found = [match for match in (self.first_from(self.plain, self.plain_starts, pos),
                                     self.first_from(self.colon, self.colon_starts, pos)) if match]
        return min(found, key=lambda match: match.start()) if found else None


# Matched against every physical line, every line and joined text of a comment run or paragraph,
# and the whole value of every string statement.
LABEL_PATTERNS = (
    # Each form is exempt only before a letter or a decimal continuation; see the class.
    ("a review round number", RoundNumberPattern()),
    ("a round of fixes", re.compile(r"(?i)\bfix[- ]rounds?\b")),
    ("a round of QA", re.compile(r"(?i)\bQA round\b")),
    ("a model-family QA attribution", re.compile(r"(?i)\b(?:codex|claude|gemini) QA\b")),
    ("a reviewer attribution", re.compile(
        r"(?i)\b" + FAMILY + r"\b" + NEAR + REVIEW_WORD + r"\b"
        r"|\b" + REVIEW_WORD + r"\b" + NEAR + FAMILY + r"\b")),
    ("a parenthesized finding id", re.compile(r"\([A-Z]{1,2}-?[0-9]{1,2}[a-z]?(?:[,);:]| and )")),
    ("a named finding id", re.compile(r"(?i)\bfindings? [A-Z]{1,2}-?[0-9]{1,2}[a-z]?\b")),
    ("a numbered finding", re.compile(r"(?i)\bfindings? #?[0-9]")),
    # Upper case only, so that ordinary text in which the verb verify comes before a number passes
    # in the files outside the history pass.
    ("a numbered review pass", re.compile(r"\b(?:DISCOVERY|VERIFY)(?: rounds?)?[- ]#?[0-9]")),
    ("a severity-numbered finding", re.compile(r"(?i)\b(?:CRITICAL|HIGH|MEDIUM|LOW)-[0-9]+\b")),
    ("a bare finding id", re.compile(r"\b(?:AA|BB|[FGMRSTUWX])[0-9]{1,2}\b")),
)

# Matched against prose only: comments and docstrings in a Python file, every line elsewhere.
PROSE_PATTERNS = (
    ("a bare finding id in prose", re.compile(r"(?<!point )\b(?!PR[0-9])[A-Z]{1,2}[0-9]{1,2}\b")),
)

ALL_PATTERNS = LABEL_PATTERNS + PROSE_PATTERNS

# The history pass reads every tracked file under these folders, line by line, against the patterns
# that name a review pass or a numbered finding: 5 of LABEL_PATTERNS, and the 2 backlog probes the
# pass must fail on, each written as its git grep -iE text with (?i) and non-capturing groups, and
# with each word boundary written as ASCII_BOUNDARY, the boundary that git grep reads in the C
# locale, where only an ASCII letter, digit or underscore is a word character; under C.UTF-8 git
# grep finds a boundary in no more places. Plan and contract ids, such as C1 or T9, match none of
# them, so the pass needs no allowlist.
HISTORY_SCOPE = ("tools", "site-src", ".github")
HISTORY_LABEL_NAMES = ("a review round number", "a round of fixes", "a round of QA", "a numbered finding",
                       "a numbered review pass")
ASCII_BOUNDARY = r"(?<!(?-i:[0-9A-Z_a-z]))"
HISTORY_PROBES = (
    ("a review pass or a finding by number, as the backlog probe reads it", re.compile(
        r"(?i)" + ASCII_BOUNDARY + r"(?:discovery|verify)(?: round)? [0-9]|" + ASCII_BOUNDARY + r"finding [0-9]|"
        + ASCII_BOUNDARY + r"round [0-9]")),
    ("a numbered review round, as the backlog probe reads it", re.compile(
        r"(?i)(?:fix|review|qa|discovery|verify) round [0-9]|round [0-9]+ (?:miss|reproduction|finding)")),
)
HISTORY_PATTERNS = (tuple(pattern for pattern in LABEL_PATTERNS if pattern[0] in HISTORY_LABEL_NAMES)
                    + HISTORY_PROBES)
# The history pass skips only the fixture lines of this file, the label forms its self-checks use as
# examples, which the maintainer allows and nothing else. A fixture line lies between a comment line
# that is FIXTURE_START and the next comment line that is FIXTURE_END, once each is stripped,
# belongs to an assignment of data that lies wholly inside that block, made directly in the body of
# a class at the top level of this file to names that FIXTURE_NAMES lists for that class, and holds
# no comment. A value of data holds only the node types in FIXTURE_DATA, so a value with a call, a
# lambda, a comprehension or a formatted string is not data, and its lines are read. An assignment
# to any other name, at module level, in a function or in a nested class is read too, and so is a
# docstring or other string line that reads as a marker, which opens and closes no block. Two
# classes at the top level of this file that share a name are a failure, so no class that a later
# one hides holds fixture lines.
FIXTURE_FILE = "tools/test-no-qa-labels.py"
FIXTURE_START = "# history pass fixtures: start"
FIXTURE_END = "# history pass fixtures: end"
FIXTURE_DATA = (ast.Constant, ast.Tuple, ast.List, ast.Dict, ast.Name, ast.Subscript, ast.BinOp, ast.Add, ast.Load)
# The fixture names, by the class that holds them: the class attributes whose values the self-checks
# of that class read as examples, or as the results they expect for them. FixtureNameRegistry, a
# static check of the source, fails when a name here is not assigned once as data in a fixture block
# of its class, or is read by no method of that class other than as a message argument of an assert
# call. It cannot tell an example from other data, so a name that a method reads only through
# self.fail, an alias, subTest(msg=...) or len passes it, and so does a class that a later binding
# of its name, other than a second class, hides from unittest.
FIXTURE_NAMES = {
    "NoReviewHistoryInScope": ("PLANTS",),
    "HistoryPatternSelfCheck": ("FIXTURES", "PROBE_ONLY", "C_LOCALE_ONLY", "FALSE_FAILURES", "NUMBERED_FINDING_ONLY",
                                "DOTTED_CAPITAL_I", "C_UTF8_FOLDS"),
    "PatternSelfCheck": (
        "LABELS", "WIDENED", "PROSE", "LETTER_EXEMPT", "FALSE_FAILURES", "FALSE_FAILURE_PYTHON",
        "CODE_FALSE_FAILURES", "CODE_STRING_LABELS", "CODE", "ORDINARY_PYTHON", "COMMENT_LABELS", "PLACEMENTS",
        "EXPECTED_SKIPS", "DOUBLE_QUOTE_FORMS", "DOUBLE_QUOTE_SKIPS", "ESCAPED_FORMS", "ESCAPED_SKIPS",
        "ADJACENT_FORMS", "ADJACENT_EARLY", "ADJACENT_SKIPS", "ORACLE_CASES", "LITERAL_KIND_STATEMENTS",
        "LITERAL_KIND_CODE", "PARSED_TEXT_STATEMENTS", "FIELD_CODE_STATEMENTS", "FIELD_TEXT_LABELS",
        "LITERAL_LED_CODE", "DECODED_LABELS", "CONCATENATED_LABELS", "CONCATENATED_CLEAN", "RAW_FSTRING_LABELS",
        "RAW_FSTRING_CLEAN", "VALUE_CLEAN", "VALUE_LABELS", "VALUE_COLON", "VALUE_LINE_FALSE_FAILURES",
        "FIELD_BACKSLASH_STATEMENTS", "JOINED_REPORT", "FIELD_JOINING_STATEMENTS", "SPLIT", "SPREAD",
        "PLAIN_NUMBER", "COLON_NUMBER", "SPLIT_COLON_CAUGHT", "SPLIT_COLON_REPORT", "SPLIT_COLON_EXEMPT",
        "SECOND_IN_ONE_TEXT", "SECOND_ACROSS_LINES", "EARLIER_IN_ONE_TEXT", "EARLIER_ACROSS_LINES"),
}
# The modes of a symbolic link and of a submodule in the output of git ls-files --stage. The history
# pass reads neither, as git grep reads neither.
UNREAD_MODES = ("120000", "160000")

# Reviewed lines whose match is not a review label: the T1 to T15 identifiers of the armed-behaviour
# proofs in the item 28.2 stage-2 plan (section 3), which the stage-2 suite names its cases after,
# and the plan open points P5 and P6; and, in the release-date tests, an ISO 8601 instant whose T00
# reads as a bare id. Each entry is the exact text of the line.
ALLOWLIST = {
    "tools/test-skill-release-date.py": (
        "            \"2026-01-01T00:00:Z\", \"2026-01-01T:00:00Z\", \"2026-01-01T00::00Z\", \"2026-01-T00:00:00Z\",",
    ),
    "tools/test-orch-stage2-hooks.py": (
        "Every armed-behaviour proof (T1 to T15 of the item 28.2 stage-2 plan, section 3, PR1-g) runs against the",
        "Optional keys: T6 (`attestations`, open point P5) and T12 (`mistakes_register`, open point P6) cover keys",
        "arm whichever way P5 and P6 are decided.",
        "uid and cannot run here; T11 proves the declared path is the one consulted (spoof-recorded) and that a",
        "        which T6 and T12 add). drop removes keys; overrides replace or add them.\"\"\"",
        "        # The stage-1 posture under a live lease (aiqt_hooks.py:7966-7968, 8208-8213; stage-1 T1:639-646).",
        "# T1. Stop with one open granted unblocked item denies, naming the id (aiqt_hooks.py:8253-8262)",
        "# T2. Stop with every item closed or proposed allows (aiqt_hooks.py:8116-8120, 8246-8247)",
        "# T3. human-decision blockers against the declared pending-decisions record (aiqt_hooks.py:8138-8150)",
        "# T4. not-before blockers (aiqt_hooks.py:8170-8176)",
        "# T5. Anti-shrinkage checkpoint (aiqt_hooks.py:8335-8431)",
        "# T6. attestations (OPTIONAL KEY, open point P5; aiqt_hooks.py:8050-8098, 8155-8164, 9625-9661)",
        "# T7. staleness horizons (aiqt_hooks.py:8022, 8152-8154, 8294-8301)",
        "# T8. orch_yield_tool over the scheduling tools (aiqt_hooks.py:8646-8721)",
        "# T9. orch_ask_guard against the declared mode record (aiqt_hooks.py:8724-8766)",
        "# T10. Scope by mode record when the lease is stale (aiqt_hooks.py:7779-7817)",
        "# T11. escape declaration (aiqt_hooks.py:7841-7901, 8511-8526)",
        "# T12. mistakes_register (OPTIONAL KEY, open point P6; aiqt_hooks.py:9677-9693)",
        "# T13. TeammateIdle mirrors the Stop decision (aiqt_hooks.py:8624-8627)",
        "# T14. Runtime posture pins on malformed stage-2 values inside a registry the hook reads as ok",
        "# T15. Enumerator timeout yields ENUMERATOR_ERROR, never a hang (aiqt_hooks.py:7974-7978)",
    ),
}

QUOTE_OPEN = re.compile(r"(?is)^[a-z]*(\"\"\"|\x27\x27\x27|\"|\x27)")
DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def labels_in(line, patterns=ALL_PATTERNS):
    """The names of the patterns that match line."""
    return [name for name, pattern in patterns if pattern.search(line)]


def read_text(path):
    """The text of a file. A missing or unreadable file raises, so the caller fails."""
    return Path(path).read_text(encoding="utf-8")


def read_as_git_grep(path):
    """The text of a file as git grep reads it, decoded as UTF-8 with every carriage return kept.

    Split at each line feed, it gives the lines and line numbers that git grep gives, even where a
    carriage return stands alone. A missing or unreadable file raises, so the caller fails.
    """
    return Path(path).read_bytes().decode("utf-8")


# An f-string, and a template string where this Python parses one, is a node of its own kind.
FORMATTED_LITERALS = (ast.JoinedStr,) + ((ast.TemplateStr,) if hasattr(ast, "TemplateStr") else ())


def token_types(*names):
    """The token types among names that the tokenizer of this Python defines."""
    return {getattr(tokenize, name) for name in names if hasattr(tokenize, name)}


# From Python 3.12 the tokenizer splits an f-string, and from 3.14 a template string, into a start,
# its literal text, the tokens of its fields and an end; before 3.12 an f-string is one STRING token.
FORMATTED_STARTS = token_types("FSTRING_START", "TSTRING_START")
FORMATTED_MIDDLES = token_types("FSTRING_MIDDLE", "TSTRING_MIDDLE")
FORMATTED_ENDS = token_types("FSTRING_END", "TSTRING_END")


def opening_of(literal):
    """The prefix and the delimiter that open the source text of a string literal."""
    opening = QUOTE_OPEN.match(literal)
    return opening.group(0)[:-len(opening.group(1))], opening.group(1)


def decoded(raw, prefix, ends_line=True):
    """The text of raw, one physical line of the body of a literal that prefix opens, as Python reads it.

    A raw literal keeps its text as written. Any other has its escapes decoded. A backslash that
    ends raw is dropped when ends_line is true, since it joins the line to the next, and kept when
    ends_line is false, as when it ends the literal text just before a replacement field of an
    f-string or template string, where it escapes nothing and Python keeps it. A bytes literal is
    read as Latin-1, one character for each byte. An escape that does not decode raises, so the
    scan fails.
    """
    prefix = prefix.lower()
    if "r" in prefix:
        return raw
    quoted = []
    at = 0
    while at < len(raw):
        if raw[at] == "\\":
            if at + 1 < len(raw):
                quoted.append(raw[at:at + 2])
            elif not ends_line:
                quoted.append("\\\\")
            at += 2
        else:
            quoted.append("\\\"" if raw[at] == "\"" else raw[at])
            at += 1
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        value = ast.literal_eval(("b" if "b" in prefix else "") + "\"" + "".join(quoted) + "\"")
    return value.decode("latin-1") if isinstance(value, bytes) else value


def literal_pieces(tokens):
    """(line number, text, breaks) for each piece of literal text in the tokens of a string statement.

    The tokens are those of one statement that is a string literal alone, so each part of an
    implicitly concatenated literal is read from its own delimiter, with its own prefix. A plain or
    bytes literal gives its decoded text. An f-string or template string gives only its top-level
    literal text: each of its replacement fields, with any conversion, format spec or nested
    literal in it, is code and stands as one space at the line where the field opens. A part that
    spans lines gives one piece for each of its physical lines. breaks is true for a piece that
    follows a line break inside the same part, which the parsed text holds, and false for a piece
    that Python joins directly to the one before it: the first piece of a part, a replacement
    field, the literal text after a field, and a line after a backslash that joins it to the line
    before. Before Python 3.12 an f-string is one STRING token whose fields the tokenizer does not
    separate, so it raises ValueError rather than be read with its fields as prose.
    """
    pieces = []
    depths = []
    prefix = ""

    def joins_next(line):
        """Whether line, in a literal that prefix opens, ends with a backslash that joins the next."""
        return "r" not in prefix.lower() and (len(line) - len(line.rstrip("\\"))) % 2 == 1

    def add(row, raw):
        lines = raw.split("\n")
        for offset, part in enumerate(lines):
            breaks = offset > 0 and not joins_next(lines[offset - 1])
            pieces.append((row + offset, decoded(part, prefix, offset < len(lines) - 1), breaks))

    for tok in tokens:
        if tok.type in FORMATTED_STARTS:
            if not depths:
                prefix = opening_of(tok.string)[0]
            depths.append(0)
        elif tok.type in FORMATTED_ENDS:
            depths.pop()
        elif tok.type in FORMATTED_MIDDLES:
            if depths == [0]:
                add(tok.start[0], tok.string)
        elif tok.type == tokenize.OP and depths and tok.string in ("{", "}"):
            if tok.string == "{":
                if depths == [0]:
                    pieces.append((tok.start[0], " ", False))
                depths[-1] += 1
            else:
                depths[-1] -= 1
        elif tok.type == tokenize.STRING and not depths:
            prefix, delimiter = opening_of(tok.string)
            if not set(prefix.lower()).isdisjoint("ft"):
                raise ValueError("this Python does not separate the fields of an f-string: " + tok.string)
            add(tok.start[0], tok.string[len(prefix) + len(delimiter):len(tok.string) - len(delimiter)])
    return pieces


def char_column(lines, lineno, offset):
    """The character column in line lineno of lines at the UTF-8 byte offset that ast gives."""
    return len(lines[lineno - 1].encode("utf-8")[:offset].decode("utf-8"))


def is_string_literal(value):
    """Whether value is a string literal of any kind: plain, bytes, f-string or template string."""
    return (isinstance(value, FORMATTED_LITERALS)
            or (isinstance(value, ast.Constant) and isinstance(value.value, (str, bytes))))


def string_statements(tree):
    """The string-literal expression statements of a parsed module, in source order.

    Every docstring is found with ast.get_docstring on each module, class and function, wherever
    it sits, so the docstring of a one-line suite is included; every other statement that is a
    string literal alone, of any kind that is_string_literal names, is included as well, so a
    docstring-style f-string, template string or bytes statement is prose too.
    """
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, DOCSTRING_OWNERS) and ast.get_docstring(node, clean=False) is not None:
            value = node.body[0].value
            found[(value.lineno, value.col_offset)] = value
        elif isinstance(node, ast.Expr) and is_string_literal(node.value):
            found[(node.value.lineno, node.value.col_offset)] = node.value
    return [found[key] for key in sorted(found)]


LINE_BREAK = re.compile(r"[^\S\n]*\n[^\S\n]*")


def statement_value(pieces):
    """The decoded value of a string statement, and the physical line of each of its characters.

    pieces are the literal pieces of the statement, as literal_pieces reads them. They are joined
    as Python joins them, with nothing between, and a piece that follows a line break inside its
    part is put after a newline at the line of the piece. Each newline of the value, from a line
    break in the source or from an escape, keeps its own line and loses the space around it, so the
    indentation of a docstring does not hide a label split across two of its lines. Returns the
    value and a list that holds the line number of each of its characters.
    """
    chars = []
    rows = []
    for row, part, breaks in pieces:
        if breaks:
            chars.append("\n")
            rows.append(row)
        chars.extend(part)
        rows.extend([row] * len(part))
    value = "".join(chars)
    text = []
    lines = []
    at = 0
    for gap in LINE_BREAK.finditer(value):
        text.append(value[at:gap.start()] + "\n")
        lines.extend(rows[at:gap.start()] + [rows[value.index("\n", gap.start())]])
        at = gap.end()
    text.append(value[at:])
    lines.extend(rows[at:])
    return "".join(text), lines


def python_blocks(text):
    """The prose blocks of Python source: comment runs on consecutive lines, and string statements.

    Returns the comment runs, each a list of (line number, text, joiner) segments joined by one
    space, as paragraph_blocks gives a paragraph, and the string statements, each as the value and
    line numbers that statement_value gives for the pieces that literal_pieces reads from the
    tokens of the statement. A source that does not tokenize or parse raises.
    """
    tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    blocks = []
    run = []
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            row = tok.start[0]
            if run and run[-1][0] != row - 1:
                blocks.append(run)
                run = []
            run.append((row, tok.string.lstrip("#").strip(), " "))
    if run:
        blocks.append(run)
    lines = text.split("\n")
    starts = [tok.start for tok in tokens]
    values = []
    for value in string_statements(ast.parse(text)):
        begin = (value.lineno, char_column(lines, value.lineno, value.col_offset))
        end = (value.end_lineno, char_column(lines, value.end_lineno, value.end_col_offset))
        at = bisect.bisect_left(starts, begin)
        statement = []
        while at < len(tokens) and tokens[at].start < end:
            statement.append(tokens[at])
            at += 1
        values.append(statement_value(literal_pieces(statement)))
    return blocks, values


def paragraph_blocks(lines):
    """The prose blocks of a non-Python file: paragraphs of consecutive non-blank lines.

    Each block is a list of (line number, text, joiner) segments, joined by one space.
    """
    blocks = []
    run = []
    for number, line in enumerate(lines, 1):
        if line.strip():
            run.append((number, re.sub(r"^\s*#*\s*", "", line).rstrip(), " "))
        elif run:
            blocks.append(run)
            run = []
    if run:
        blocks.append(run)
    return blocks


def block_text(block, glue):
    """The segments of block joined as one text, with the offsets that place each segment in it.

    glue maps the joiner of each segment after the first to the separator put before it. Returns
    the text, the offset where the text of each segment starts and the offset where its separator
    starts.
    """
    parts = []
    starts = []
    begins = []
    offset = 0
    for index, (_, text, joiner) in enumerate(block):
        separator = glue(joiner) if index else ""
        begins.append(offset)
        offset += len(separator)
        starts.append(offset)
        parts.append(separator + text)
        offset += len(text)
    return "".join(parts), starts, begins


def every_match(pattern, text):
    """Each match of pattern in text, searched from every start position.

    A search from each position after the start of the last match means an earlier match cannot
    hide a later one.
    """
    position = 0
    while True:
        match = pattern.search(text, position)
        if match is None:
            return
        yield match
        position = match.start() + 1


def split_hits(block):
    """(line number, pattern name, matched text) for each match in a block that crosses a line break.

    The block is a comment run or a paragraph. It is joined by one space between its lines and
    searched as one text, from every start position, so a label spread over any number of lines is
    caught and an earlier match cannot hide a later one. The round number pattern searches the
    block with a line break in place of each joining space instead, so a letter exempts its colon
    form only on the physical line of the number. A match is reported at the segment where it
    starts, with any line break in its text shown as a space; it crosses a line break when its last
    character lies in a later segment or in the separator before one.
    """
    joined = block_text(block, lambda joiner: joiner)
    lined = block_text(block, lambda joiner: "\n")
    hits = []
    for name, pattern in ALL_PATTERNS:
        searched, starts, begins = lined if isinstance(pattern, RoundNumberPattern) else joined
        for match in every_match(pattern, searched):
            first = bisect.bisect_right(starts, match.start()) - 1
            last = bisect.bisect_right(begins, match.end() - 1) - 1
            hit = (block[first][0], name, match.group(0).replace("\n", " "))
            if last > first and hit not in hits:
                hits.append(hit)
    return hits


def value_hits(value, lines):
    """(line number, pattern name, matched text, crosses) for each match in a string value.

    value and lines are what statement_value gives for one string statement. The value is searched
    once as a whole for each pattern, from every start position: by the round number pattern with
    its newlines kept, so a letter exempts the colon form only on the line of the number, and by
    every other pattern with each newline read as one space. A match is reported at the physical
    line where it starts, with any newline in its text shown as a space, and crosses is true when
    its last character lies on a later physical line.
    """
    spaced = value.replace("\n", " ")
    hits = []
    for name, pattern in ALL_PATTERNS:
        searched = value if isinstance(pattern, RoundNumberPattern) else spaced
        for match in every_match(pattern, searched):
            first = lines[match.start()]
            hit = (first, name, match.group(0).replace("\n", " "), lines[match.end() - 1] > first)
            if hit not in hits:
                hits.append(hit)
    return hits


def scan(rel, text, allowlist=()):
    """Every unreviewed label in text, as report lines naming rel and the starting line number.

    A match that lies on one physical line is reported with the names of every pattern that
    matches there and the text of the line, which ALLOWLIST can pass; a match that crosses a line
    break is reported on its own at the line where it starts.
    """
    lines = text.split("\n")
    allowed = set(allowlist)
    blocks, values = python_blocks(text) if rel.endswith(".py") else (paragraph_blocks(lines), [])
    names_at = {}
    for number, line in enumerate(lines, 1):
        names_at.setdefault(number, []).extend(labels_in(line, LABEL_PATTERNS))
    across = []
    for block in blocks:
        for number, segment, _ in block:
            for name in labels_in(segment):
                if name not in names_at[number]:
                    names_at[number].append(name)
        across.extend(split_hits(block))
    for value, rows in values:
        for number, name, matched, crosses in value_hits(value, rows):
            if crosses:
                across.append((number, name, matched))
            elif name not in names_at[number]:
                names_at[number].append(name)
    found = []
    for number, names in sorted(names_at.items()):
        if names and lines[number - 1] not in allowed:
            found.append("{}:{}: {}: {}".format(rel, number, ", ".join(names), lines[number - 1].strip()))
    for number, name, matched in across:
        found.append("{}:{}: {} across a line break: {}".format(rel, number, name, matched))
    return found


class NoReviewLabels(unittest.TestCase):
    def test_scanned_files_carry_no_unreviewed_label(self):
        found = []
        scanned = 0
        for rel in SCANNED:
            text = read_text(ROOT / rel)
            scanned += len(text.split("\n"))
            found.extend(scan(rel, text, ALLOWLIST.get(rel, ())))
        self.assertGreater(scanned, 0, "no line was scanned")
        self.assertEqual(found, [], "review-history labels found:\n" + "\n".join(found))

    def test_scanned_holds_every_workflow_both_launch_scans_and_the_release_sources(self):
        workflows = sorted(path.relative_to(ROOT).as_posix()
                           for pattern in ("*.yml", "*.yaml")
                           for path in (ROOT / ".github/workflows").glob(pattern))
        self.assertGreater(len(workflows), 0, "no workflow was found")
        for rel in workflows + ["tools/test-shell-launch-isolation.py", "tools/test-workflow-launch-isolation.py",
                                "tools/check-release-checksum-live.py", "tools/test-release-checksum-live.py",
                                "tools/test-skill-release-date.py"]:
            with self.subTest(file=rel):
                self.assertIn(rel, SCANNED)

    def test_allowlist_names_only_scanned_files(self):
        self.assertEqual(sorted(set(ALLOWLIST) - set(SCANNED)), [])

    def test_every_allowlist_entry_is_a_live_match(self):
        for rel, entries in ALLOWLIST.items():
            lines = read_text(ROOT / rel).split("\n")
            for entry in entries:
                with self.subTest(file=rel, entry=entry):
                    self.assertEqual(lines.count(entry), 1, "allowlisted line absent or repeated")
                    self.assertTrue(labels_in(entry), "allowlisted line matches no pattern; remove it")


def tracked_history_files(root=ROOT):
    """(repository-relative path, mode) for each file that git ls-files lists under HISTORY_SCOPE.

    The list is the index of the repository at root, the files that git grep reads, in sorted order,
    each path once. A git ls-files that fails raises subprocess.CalledProcessError.
    """
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "--stage", "-z", "--"] + list(HISTORY_SCOPE),
                            capture_output=True, check=True).stdout
    entries = {}
    for entry in listed.split(b"\0"):
        if entry:
            info, _, path = entry.partition(b"\t")
            entries[os.fsdecode(path)] = info.split()[0].decode("ascii")
    return sorted(entries.items())


def fixture_lines(text):
    """The numbers of the fixture lines of text, the source of this lint.

    A block runs from a comment line that is FIXTURE_START to the next comment line that is
    FIXTURE_END, once each is stripped; a line inside a string that reads as a marker is not one. A
    start inside an open block, an end outside one, a block left open or a carriage return in text,
    which would make the lines Python parses differ from the lines the pass reads, raises
    ValueError, so the history pass fails, and so do 2 classes at the top level of text that share a
    name, since the later one would hide the earlier one from unittest and from FixtureNameRegistry,
    which reads the last class of each name. A fixture line lies inside a block, belongs to an
    assignment of data that lies wholly inside that block, made directly in the body of a class at
    the top level of text to names that FIXTURE_NAMES lists for that class, and holds no comment; a
    value of data holds only the node types in FIXTURE_DATA.
    """
    if "\r" in text:
        raise ValueError("line {}: a carriage return".format(text[:text.index("\r")].count("\n") + 1))
    tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    commented = {tok.start[0] for tok in tokens if tok.type == tokenize.COMMENT}
    source = text.split("\n")
    blocks = []
    start = None
    for number in sorted(commented):
        line = source[number - 1].strip()
        if line == FIXTURE_START:
            if start is not None:
                raise ValueError("line {}: a fixture block starts inside another".format(number))
            start = number
        elif line == FIXTURE_END:
            if start is None:
                raise ValueError("line {}: a fixture block ends outside one".format(number))
            blocks.append((start, number))
            start = None
    if start is not None:
        raise ValueError("line {}: a fixture block is left open".format(start))
    lines = set()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tree = ast.parse(text)
    classes = [owner for owner in tree.body if isinstance(owner, ast.ClassDef)]
    for owner in classes:
        if [other.name for other in classes].count(owner.name) > 1:
            raise ValueError("line {}: another class at the top level is named {}".format(owner.lineno, owner.name))
    for owner in tree.body:
        if not isinstance(owner, ast.ClassDef) or owner.name not in FIXTURE_NAMES:
            continue
        for node in owner.body:
            if (isinstance(node, ast.Assign)
                    and all(isinstance(target, ast.Name) and target.id in FIXTURE_NAMES[owner.name]
                            for target in node.targets)
                    and all(isinstance(part, FIXTURE_DATA) for part in ast.walk(node.value))
                    and any(first < node.lineno and node.end_lineno < last for first, last in blocks)):
                lines.update(range(node.lineno, node.end_lineno + 1))
    return lines - commented


def history_hits(rel, text):
    """A report line for each line of text, the file rel, that a history pattern matches.

    Only in FIXTURE_FILE are lines skipped, and only the fixture lines that fixture_lines finds.
    """
    skipped = fixture_lines(text) if rel == FIXTURE_FILE else set()
    found = []
    for number, line in enumerate(text.split("\n"), 1):
        names = [] if number in skipped else labels_in(line, HISTORY_PATTERNS)
        if names:
            found.append("{}:{}: {}: {}".format(rel, number, ", ".join(names), line.strip()))
    return found


def history_report(root=ROOT):
    """The report of the history pass over the repository at root, and the number of files it read.

    Each tracked file under HISTORY_SCOPE is read as git grep reads it, apart from a symbolic link
    and a submodule, which git grep reads neither of. A file that is missing, cannot be read as
    UTF-8 or, for this lint, holds a fixture block left open or a carriage return or does not parse,
    is reported with its path, and a git ls-files that fails is reported too.
    """
    try:
        entries = tracked_history_files(root)
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", b"") or b""
        return ["git ls-files failed: {} {}".format(error, detail.decode("utf-8", "replace").strip())], 0
    found = []
    read = 0
    for rel, mode in entries:
        if mode in UNREAD_MODES:
            continue
        try:
            found.extend(history_hits(rel, read_as_git_grep(Path(root) / rel)))
        except (OSError, UnicodeDecodeError, ValueError, SyntaxError, tokenize.TokenError) as error:
            found.append("{}: unreadable: {}".format(rel, error))
            continue
        read += 1
    return found, read


class NoReviewHistoryInScope(unittest.TestCase):
    # history pass fixtures: start
    # Probe-matching lines planted into a copy of this lint, each of which the pass must report.
    PLANTS = ("round 3 of the plan", "fix round 2", "Verify 3 and discovery 2")
    # history pass fixtures: end

    # The 2 backlog probes, verbatim, as git grep -iE reads them.
    ROW_172_PROBE = r"\b(discovery|verify)( round)? [0-9]|\bfinding [0-9]|\bround [0-9]"
    ROW_183_PROBE = r"(fix|review|qa|discovery|verify) round [0-9]|round [0-9]+ (miss|reproduction|finding)"

    def test_no_file_in_scope_names_a_review_pass_or_a_numbered_finding(self):
        found, read = history_report()
        self.assertGreater(read, 0, "no file was read")
        self.assertEqual(found, [], "review-history labels found:\n" + "\n".join(found))

    def test_the_history_scope_is_the_3_folders(self):
        self.assertEqual(HISTORY_SCOPE, ("tools", "site-src", ".github"))
        read = {rel.split("/")[0] for rel, _ in tracked_history_files()}
        self.assertEqual(read, set(HISTORY_SCOPE), "a folder of the scope holds no file the pass reads")

    def test_the_fixture_file_is_this_lint(self):
        self.assertEqual(FIXTURE_FILE, "tools/test-no-qa-labels.py")
        self.assertEqual((ROOT / FIXTURE_FILE).resolve(), Path(__file__).resolve())
        self.assertEqual((FIXTURE_START, FIXTURE_END),
                         ("# history pass fixtures: start", "# history pass fixtures: end"))

    @staticmethod
    def planted(text, after, line):
        """text with line put after the first line whose stripped text is after, and its number."""
        lines = text.split("\n")
        at = next(index for index, old in enumerate(lines) if old.strip() == after) + 1
        return "\n".join(lines[:at] + [line] + lines[at:]), at + 1

    def test_a_plant_outside_the_fixture_lines_of_this_lint_fails(self):
        own = read_text(ROOT / FIXTURE_FILE)
        self.assertEqual(history_hits(FIXTURE_FILE, own), [])
        docstring_head = own.split("\n")[1].strip()
        comment_before = "class NoReviewHistoryInScope(unittest.TestCase):"
        test_head = "def test_the_fixture_file_is_this_lint(self):"
        for plant in self.PLANTS:
            value = "\"{}\"".format(plant)
            # (where, the stripped line the plant follows, the planted lines, the offset in them of
            # the line that must be reported). FIXTURE_START is first met in this class, whose only
            # fixture name is PLANTS, so in each case only the rule that the case names keeps its
            # line out of the skip.
            cases = (("the module docstring", docstring_head, plant, 0),
                     ("a comment", "", "# " + plant, 0),
                     ("test code", test_head, "        planted = " + value, 0),
                     ("a comment in a fixture block", FIXTURE_START, "    # " + plant, 0),
                     ("a call in a fixture block", FIXTURE_START, "    PLANTS = str({})".format(value), 0),
                     ("a fixture line with a comment", FIXTURE_START, "    PLANTS = {}  # planted".format(value), 0),
                     ("a name outside FIXTURE_NAMES in a fixture block", FIXTURE_START, "    MESSAGE = " + value, 0),
                     ("a local of a method in a fixture block", FIXTURE_START,
                      "    def helper(self):\n        PLANTS = " + value, 1),
                     ("a class in a method in a fixture block", FIXTURE_START,
                      "    def helper(self):\n        class K:\n            PLANTS = " + value, 2),
                     ("a string line that reads as a marker", FIXTURE_END,
                      "    \"\"\"\n    {}\n    \"\"\"\n    PLANTS = {}\n    \"\"\"\n    {}\n    \"\"\"".format(
                          FIXTURE_START, value, FIXTURE_END), 3))
            for where, after, line, offset in cases:
                with self.subTest(plant=plant, where=where):
                    if where == "a comment":
                        lines = own.split("\n")
                        at = lines.index(comment_before)
                        text, number = "\n".join(lines[:at] + [line] + lines[at:]), at + 1
                    else:
                        text, number = self.planted(own, after, line)
                    found = history_hits(FIXTURE_FILE, text)
                    self.assertEqual([hit.split(":")[1] for hit in found], [str(number + offset)], found)
            with self.subTest(plant=plant, where="a class in a module function in a fixture block"):
                lines = own.split("\n")
                at = lines.index(comment_before)
                block = [FIXTURE_START, "def helper():", "    class NoReviewHistoryInScope:",
                         "        PLANTS = " + value, FIXTURE_END]
                found = history_hits(FIXTURE_FILE, "\n".join(lines[:at] + block + lines[at:]))
                self.assertEqual([hit.split(":")[1] for hit in found], [str(at + 4)], found)
            with self.subTest(plant=plant, where="a fixture line"):
                text, _ = self.planted(own, FIXTURE_START, "    PLANTS = " + value)
                self.assertEqual(history_hits(FIXTURE_FILE, text), [])
            with self.subTest(plant=plant, where="a fixture block of another file"):
                text = "class C:\n    {}\n    X = \"{}\"\n    {}\n".format(FIXTURE_START, plant, FIXTURE_END)
                found = history_hits("tools/other.py", text)
                self.assertEqual([hit.split(":")[1] for hit in found], ["3"], found)
        with self.subTest(where="this lint at another path with the same file name"):
            matched = [number for number, line in enumerate(own.split("\n"), 1) if labels_in(line, HISTORY_PATTERNS)]
            found = history_hits("tools/copy/test-no-qa-labels.py", own)
            self.assertGreater(len(matched), 0)
            self.assertEqual([int(hit.split(":")[1]) for hit in found], matched, found)

    def test_a_malformed_fixture_block_fails(self):
        for text in ("{}\nX = 1\n".format(FIXTURE_START), "X = 1\n{}\n".format(FIXTURE_END),
                     "{0}\n{0}\nX = 1\n{1}\n".format(FIXTURE_START, FIXTURE_END), "X = 1\r\n"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    history_hits(FIXTURE_FILE, text)

    def test_a_class_name_used_twice_fails(self):
        # A class that a later class of the same name hides never runs, and FixtureNameRegistry
        # reads only the later one, so a fixture block in the hidden class would skip lines that no
        # check reads. The first text puts such a class, with a plant as its fixture, between 2
        # classes of this lint.
        own = read_text(ROOT / FIXTURE_FILE)
        lines = own.split("\n")
        at = lines.index("class HistoryPatternSelfCheck(unittest.TestCase):")
        hidden = ["class PatternSelfCheck:", "    " + FIXTURE_START, "    LABELS = (\"{}\",)".format(self.PLANTS[1]),
                  "    " + FIXTURE_END, "", ""]
        for text in ("\n".join(lines[:at] + hidden + lines[at:]), "class A:\n    pass\n\n\nclass A:\n    pass\n"):
            with self.subTest(text=text[:20]):
                with self.assertRaises(ValueError):
                    history_hits(FIXTURE_FILE, text)

    def test_the_pass_reads_the_tracked_files_as_git_grep_does(self):
        # The lines the pass reports in readable files must be the lines that git grep, run with
        # both backlog probes under LC_ALL=C, prints for the same index: so a force-added file and a
        # folder starting with _ are read, an untracked file, a file outside the 3 folders, a
        # tracked symbolic link and a submodule, here a gitlink entry with an empty folder, are not,
        # and a lone carriage return keeps the line numbers of git grep. The line of tools/c.txt,
        # which the first probe matches under LC_ALL=C and not under C.UTF-8, since an e with an
        # acute accent comes just before round, ties the run of git grep to that locale. A tracked
        # file that is missing or not UTF-8, which git grep passes over, is a failure that names the
        # file in the report.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)

            def git(*args, **options):
                return subprocess.run(["git", "-C", str(root)] + list(args), capture_output=True, **options)

            git("init", "-q", check=True)
            files = {"tools/__pycache__/x.txt": self.PLANTS[1], "site-src/_cache/y.md": self.PLANTS[0],
                     ".github/z.yml": "clean", "outside.md": self.PLANTS[2], "tools/gone.txt": "clean",
                     "tools/cr.txt": "x\r" + self.PLANTS[2] + "\nx\r" + self.PLANTS[1] + "\nx\r" + self.PLANTS[0],
                     "tools/c.txt": "\u00e9" + self.PLANTS[0]}
            for rel, line in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_bytes((line + "\n").encode("utf-8"))
            (root / "tools/bad.txt").write_bytes(b"\xff\xfe\n")
            (root / "tools/link.md").symlink_to("../outside.md")
            git("add", "-f", "--", ".", check=True)
            git("update-index", "--add", "--cacheinfo", "160000," + "1" * 40 + ",tools/sub", check=True)
            (root / "tools/sub").mkdir()
            (root / "tools/gone.txt").unlink()
            (root / "tools/untracked.txt").write_text(self.PLANTS[2] + "\n", encoding="utf-8")
            found, read = history_report(root)
            grep = git("grep", "-n", "-z", "-iE", "-e", self.ROW_172_PROBE, "-e", self.ROW_183_PROBE, "--",
                       *HISTORY_SCOPE, env=dict(os.environ, LC_ALL="C"))
        self.assertEqual(grep.returncode, 0, grep.stderr)
        printed = sorted((entry.split(b"\0")[0].decode("utf-8"), int(entry.split(b"\0")[1]))
                         for entry in grep.stdout.split(b"\n") if entry)
        hits = sorted((hit.split(":")[0], int(hit.split(":")[1])) for hit in found if ": unreadable: " not in hit)
        self.assertEqual(hits, printed, found)
        self.assertEqual(printed, [("site-src/_cache/y.md", 1), ("tools/__pycache__/x.txt", 1), ("tools/c.txt", 1),
                                   ("tools/cr.txt", 1), ("tools/cr.txt", 2), ("tools/cr.txt", 3)])
        self.assertEqual(sorted(hit.split(":")[0] for hit in found if ": unreadable: " in hit),
                         ["tools/bad.txt", "tools/gone.txt"], found)
        self.assertEqual(read, 5, found)

    def test_a_failed_listing_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            found, read = history_report(Path(folder) / "missing")
        self.assertEqual((len(found), read), (1, 0), found)
        self.assertTrue(found[0].startswith("git ls-files failed: "), found)


class HistoryPatternSelfCheck(unittest.TestCase):
    # The history pass, pinned literally: the 5 label patterns it shares with LABEL_PATTERNS, by
    # name, and the 2 backlog probes, by name and pattern text.
    LABEL_NAMES = ("a review round number", "a round of fixes", "a round of QA", "a numbered finding",
                   "a numbered review pass")
    PROBES = (("a review pass or a finding by number, as the backlog probe reads it",
               r"(?i)(?<!(?-i:[0-9A-Z_a-z]))(?:discovery|verify)(?: round)? [0-9]|(?<!(?-i:[0-9A-Z_a-z]))finding [0-9]"
               r"|(?<!(?-i:[0-9A-Z_a-z]))round [0-9]"),
              ("a numbered review round, as the backlog probe reads it",
               r"(?i)(?:fix|review|qa|discovery|verify) round [0-9]|round [0-9]+ (?:miss|reproduction|finding)"))
    # history pass fixtures: start
    # A fixture for each history pattern, which that pattern must catch.
    FIXTURES = {"a review round number": "fixed in round-7", "a round of fixes": "the fix-round change",
                "a round of QA": "the QA round", "a numbered finding": "finding #3",
                "a numbered review pass": "VERIFY round 9.1",
                PROBES[0][0]: "Verify 3", PROBES[1][0]: "around 3 misses"}
    # Forms the 5 label patterns pass, as a lower-case pass name or a round number that a letter or
    # a decimal continuation exempts, and that the backlog probes, and so the history pass, catch,
    # among them the second probe in upper case and with a number of 2 digits.
    PROBE_ONLY = ("Verify 3", "discovery 2", "round 7th", "round 7.5", "round 7a", "Verify round 9.1",
                  "around 3 misses", "AROUND 3 MISSES", "around 12 misses")
    # Forms that the first probe matches as git grep reads it under LC_ALL=C, where a letter or
    # digit outside ASCII before its first word leaves a word boundary, and that the label patterns
    # pass: an e with an acute accent, a dotless i, a Cyrillic letter, an n with a tilde, the Kelvin
    # sign and an Arabic-Indic digit.
    C_LOCALE_ONLY = ("\u00e9round 3", "\u0131round 3", "\u0434discovery 2", "\u00f1finding 3", "\u212around 3",
                     "\u0663round 3")
    # Ordinary text that the history pass catches, an accepted false failure that stays caught.
    FALSE_FAILURES = ("verify 3 files", "finding 3 files were removed", "finding 2 issues")
    # Ordinary text that only the numbered finding pattern catches, as the plural or with a number
    # sign, which neither backlog probe matches: a cost of keeping that pattern wide, pinned here.
    NUMBERED_FINDING_ONLY = ("the findings 2 tools printed", "findings 2 and 3", "finding #3 files")
    # Forms with a capital I with a dot above, U+0130, in place of an i of a probe word, which
    # neither backlog probe matches under LC_ALL=C or C.UTF-8 and the history pass catches, since
    # the case-insensitive matching of Python folds that letter to i: an accepted false failure,
    # which stays caught.
    DOTTED_CAPITAL_I = ("ver\u0130fy 3", "f\u0130nding 3", "d\u0130scovery 3", "find\u0130ng 3")
    # Forms with a dotless i, U+0131, or a long s, U+017F, in place of an i or an s of a probe word,
    # which a probe matches under C.UTF-8 and not under LC_ALL=C, and which the history pass
    # catches, since the case-insensitive matching of Python folds those letters as well.
    C_UTF8_FOLDS = ("d\u0131scovery 3", "di\u017fcovery 3", "around 3 mi\u017fses")
    # history pass fixtures: end

    def test_the_history_patterns_are_pinned(self):
        labels = dict(LABEL_PATTERNS)
        self.assertEqual(HISTORY_PATTERNS,
                         tuple((name, labels[name]) for name in self.LABEL_NAMES)
                         + tuple((name, re.compile(text)) for name, text in self.PROBES))

    def test_each_history_pattern_catches_its_fixture(self):
        self.assertEqual(sorted(self.FIXTURES), sorted(name for name, _ in HISTORY_PATTERNS))
        for name, pattern in HISTORY_PATTERNS:
            with self.subTest(pattern=name):
                self.assertTrue(pattern.search(self.FIXTURES[name]), self.FIXTURES[name])

    def test_the_backlog_probes_catch_what_the_label_patterns_pass(self):
        shared = HISTORY_PATTERNS[:len(self.LABEL_NAMES)]
        for text in self.PROBE_ONLY:
            with self.subTest(text=text):
                self.assertEqual(labels_in(text, shared), [], text)
                self.assertTrue(labels_in(text, HISTORY_PATTERNS), text)

    def test_the_first_probe_catches_what_git_grep_matches_in_the_c_locale(self):
        shared = HISTORY_PATTERNS[:len(self.LABEL_NAMES)]
        for text in self.C_LOCALE_ONLY:
            with self.subTest(text=text):
                self.assertFalse(text[0].isascii(), text)
                self.assertEqual(labels_in(text, shared), [], text)
                self.assertEqual(labels_in(text, HISTORY_PATTERNS), [self.PROBES[0][0]], text)

    def test_only_the_numbered_finding_pattern_catches_its_wider_forms(self):
        for text in self.NUMBERED_FINDING_ONLY:
            with self.subTest(text=text):
                self.assertEqual(labels_in(text, HISTORY_PATTERNS), ["a numbered finding"], text)

    def test_ordinary_counts_stay_caught(self):
        for text in self.FALSE_FAILURES:
            with self.subTest(text=text):
                self.assertTrue(labels_in(text, HISTORY_PATTERNS), text)
        for text in self.FALSE_FAILURES[1:]:
            with self.subTest(text=text):
                self.assertEqual(labels_in(text, LABEL_PATTERNS), ["a numbered finding"], text)

    def test_a_capital_i_with_a_dot_above_stays_caught(self):
        for text in self.DOTTED_CAPITAL_I:
            with self.subTest(text=text):
                self.assertIn("\u0130", text)
                self.assertTrue(labels_in(text, HISTORY_PATTERNS), text)

    def test_a_dotless_i_or_a_long_s_stays_caught(self):
        for text in self.C_UTF8_FOLDS:
            with self.subTest(text=text):
                self.assertTrue({"\u0131", "\u017f"} & set(text), text)
                self.assertTrue(labels_in(text, HISTORY_PATTERNS[len(self.LABEL_NAMES):]), text)


class FixtureNameRegistry(unittest.TestCase):
    @staticmethod
    def message_arguments(call):
        """The arguments of an assert call of unittest that are its message, not its subject."""
        if not (isinstance(call.func, ast.Attribute) and call.func.attr.startswith("assert")):
            return []
        subjects = 1 if call.func.attr in ("assertTrue", "assertFalse", "assertIsNone", "assertIsNotNone") else 2
        return call.args[subjects:] + [keyword.value for keyword in call.keywords if keyword.arg == "msg"]

    def test_each_fixture_name_is_a_fixture_that_its_class_reads(self):
        own = read_text(ROOT / FIXTURE_FILE)
        tree = ast.parse(own)
        skipped = fixture_lines(own)
        classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
        self.assertEqual(sorted(set(FIXTURE_NAMES) - set(classes)), [])
        for owner, names in FIXTURE_NAMES.items():
            assigned = {}
            for node in classes[owner].body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            assigned.setdefault(target.id, []).append(node)
            messages = {id(part) for call in ast.walk(classes[owner]) if isinstance(call, ast.Call)
                        for argument in self.message_arguments(call) for part in ast.walk(argument)}
            read = {node.attr for method in classes[owner].body
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                    for node in ast.walk(method)
                    if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load)
                    and isinstance(node.value, ast.Name) and node.value.id in ("self", "cls", owner)
                    and id(node) not in messages}
            self.assertEqual(len(names), len(set(names)), owner)
            for name in names:
                with self.subTest(owner=owner, name=name):
                    self.assertEqual(len(assigned.get(name, [])), 1, "assigned other than once")
                    node = assigned[name][0]
                    self.assertTrue(set(range(node.lineno, node.end_lineno + 1)) <= skipped,
                                    "not a fixture: outside a block, not data or commented")
                    self.assertIn(name, read, "read by no method of its class other than as a message")


class PatternSelfCheck(unittest.TestCase):
    # history pass fixtures: start
    LABELS = ("(round 7)", "(round-5 fix)", "Round 2 G5: x", "(fix round 16, M1)", "(fix round 17, F1)",
              "Fix round 16 (M1): x", "claude QA round 10", "codex QA HIGH-1", "(codex QA F6)", "(F1)",
              "(G1)", "(M2)", "(AA2)", "(BB1)", "(F1 and G1)", "finding S3", "findings F1 and G1",
              "Finding R7: x", "--- R3: x", "the F1-era test", "HIGH-2: x", "before G1 the",
              "(L5)", "(H3: x)", "(Q2; x)", "finding L5", "the L5 fix", "(codex reproduced: x)",
              "refuting the gemini seed\x27s claim", "flagged by codex", "the claude review",
              "gemini found that", "a codex finding", "raised in the gemini round")
    # Forms added when the guard was widened: round numbers with a colon at a label position, a
    # plural, a number sign or a hyphen, a hyphenated label of a round of fixes, the credit verbs, a
    # severity id in any case, a hyphenated finding id in parentheses or after the word finding, and
    # a letter-suffixed finding id, and a plain round number that an underscore or a numeric
    # character that is not a letter follows, such as superscript two, one half or the Roman numeral
    # eight, and a finding or an upper-case DISCOVERY or VERIFY pass named by its number, with or
    # without a number sign or the word round, even where the round number pattern exempts the
    # decimal number that follows.
    WIDENED = ("as fixed in round: 7", "rounds 7 and 8", "round #7", "the fix-round change",
               "codex caught this", "spotted by gemini", "claude noticed the gap", "gemini confirmed it",
               "High-1: x", "a high-2 case", "(F1a)", "finding F-1", "(F-1)", "round: 7.",
               "as fixed in round: 7, then", "(round: 7)", "round 7", "round-7", "round: 7",
               "round: 7]", "round: 7?", "round: 7!", "**round: 7**",
               "round 7\u00b2", "round 7\u00bd", "round 7\u2167", "round 7_",
               "VERIFY 1.1 finding 1", "DISCOVERY round 4, finding 1", "finding 17",
               "findings 2 and 3", "VERIFY-2", "finding #3", "VERIFY round 9.1")
    PROSE = ("U+3164", "aiqt_hooks.py:8414", "\\x1f", "class T01StopActionable", "sha256",
             "item 28.2 stage 2, PR1-d", "open point P5", "round-trip through json.dumps",
             "Point the command at the QA cycle", "commit d191071", "UTF-8", "line 8:", "the g1 prefix",
             "The PR1-f doctor tests", "HTTP 400", "SHA256", "a codex worker", "the gemini CLI",
             "maintained with Claude", "Claude, Anthropic, OpenAI, Codex, Copilot, or Gemini",
             "U+FFA0", "U+D800..U+DFFF", "round: 7 decimal places", "round: 7.5",
             "Time per round: 7\u00b5s", "Time per round: 7 \u03bcs",
             "round: 7\u00b5", "round: 7 \u03bc", "round: 7\u5e74",
             "round 7th", "round 7a", "round 7.5", "round 7\u0434",
             "verify 3 files", "the finding is")
    # Both forms are exempt before a letter of any script, so one sample stands for each of
    # the five letter categories, from scripts the samples above do not use: Cyrillic small and
    # capital letters (Ll, Lu), Arabic and Hebrew letters (Lo), modifier letters (Lm), titlecase
    # letters (Lt) and the ideographic iteration mark (Lm), with and without a space. They pass,
    # so the exemption cannot narrow to some scripts or drop a category silently.
    LETTER_EXEMPT = ("round: 7 \u0434\u043d\u044f", "round: 7\u0434", "round: 7 \u0414",
                     "round: 7 \u0645", "round: 7\u05d0", "round: 7 \u02b0", "round: 7\u02e0",
                     "round: 7\u3005", "round: 7 \u01c5", "round: 7\u1f88")
    # Accepted low-severity false failures of the colon form, as examples: ordinary text that is
    # caught because neither a letter nor a decimal continuation follows the number on its own
    # line, including a numeric character that is not a letter (superscript two, one half and the
    # Roman numeral eight). They stay caught, so the trade-off cannot change silently.
    FALSE_FAILURES = ("round: 7 (default)", "round: 7%", "round: 7 -> 8",
                      "round: 7\u00b2", "Area per round: 7 \u00bd", "round: 7\u2167")
    # The one space that stands for a replacement field can complete a label in the decoded text of
    # an f-string statement, an accepted low-severity false failure that stays caught.
    FALSE_FAILURE_PYTHON = ("# Keep round: 7\n# decimal places\nx = 1\n", "x = 1\nf\"the fix{x}round case\"\n")
    # Accepted low-severity false failures in Python code, which is matched line by line as prose
    # is: ordinary arithmetic and an identifier that the plain form catches. They stay caught, so
    # code matching cannot be confined to prose silently.
    CODE_FALSE_FAILURES = ("x = rounds - 1\n", "x = rounds-1\n", "round2 = 3\n")
    # Labels in Python string literals that are not statements of their own, an assertion message
    # and an assigned value, which only the matching of code lines catches.
    CODE_STRING_LABELS = ("assert x, \"fixed in round 7\"\n", "message = \x27fixed in round: 7\x27\n")
    CODE = ("closure=\"C1\", opened=\"2026-09-01\"", "[\"2\", \"2026-09-02\", \"Second\", \"C2\"]",
            "[\"PD-7\", \"MR-1\", \"AT-1\", \"CL-1\", 0xFFA0, 0xD800]")
    # Ordinary Python that the hyphen and colon forms must not flag: subtraction, hyphenated
    # register ids in a comment or a docstring, a hyphenated key name, and a colon round count.
    ORDINARY_PYTHON = ("value = F-1\n", "value = T-2\n",
                       "# PD-7, MR-1 and PR-1 are register ids.\nx = 1\n",
                       "def f():\n    \"\"\"Read PD-7, MR-1 and PR-1 from the register.\"\"\"\n",
                       "# Use the F-1 key.\nx = 1\n", "# round: 7 decimal places\nx = 1\n",
                       "# round: 7.5\nx = 1\n",
                       "def f():\n    \"\"\"Keep round: 7 decimal places.\"\"\"\n",
                       "\"\"\"Use round: 7.5\"\"\"\nx = 1\n")
    # Labels that must stay caught when they sit in a Python comment.
    COMMENT_LABELS = ("(F-1)", "finding F-1", "round: 7.", "round 7", "rounds 7 and 8",
                      "round #7", "round-7")
    # Every single-line caught form, in LABELS, COMMENT_LABELS and WIDENED, is checked in each
    # Python placement: a comment, a multi-line function docstring, a one-line suite docstring in
    # double and in single quotes, and a module docstring, with the label mid-sentence and at the
    # very end, just before the closing quotes. A form that would end the literal of a placement
    # early, by holding its delimiter, and leave source that does not tokenize or parse cannot sit
    # inside it, so it is skipped for that placement only, and the skipped set must be exactly the
    # forms that would, judged from the delimiter of that placement and a parse of the source, and
    # equal the literal set pinned for that placement in EXPECTED_SKIPS.
    # The multi-line SPLIT and SPREAD forms are checked in their own tests below.
    PLACEMENTS = ("# fixed in {}\nx = 1\n",
                  "# fixed in {}, so x holds\nx = 1\n",
                  "def f():\n    \"\"\"Handle x.\n\n    Fixed in {}, so x holds.\n    \"\"\"\n",
                  "def f():\n    \"\"\"Handle x.\n\n    Fixed in {}\"\"\"\n",
                  "def f(): \"\"\"Fixed in {}, so x holds.\"\"\"\n",
                  "def f(): \"\"\"Fixed in {}\"\"\"\n",
                  "def f(): \x27Fixed in {}\x27\n",
                  "\"\"\"Handle x.\n\nFixed in {}, so x holds.\n\"\"\"\nx = 1\n",
                  "\"\"\"Handle x.\n\nFixed in {}\"\"\"\nx = 1\n")
    # The forms each placement skips, pinned literally in PLACEMENTS order: only the one-line
    # suite docstring in single quotes skips a form, the one that holds a single quote.
    EXPECTED_SKIPS = ((), (), (), (), (), (), ("refuting the gemini seed\x27s claim",), (), ())
    # Forms that hold a double quote, checked in every placement: one with the quote inside the
    # text, which sits in every placement, and one that ends with the quote, which ends a
    # triple-quoted literal early only where it sits just before the closing quotes. The skips are
    # pinned literally in PLACEMENTS order and must match expected_skip, which skips a form only
    # when the delimiter of the placement shows it ends the literal early and the source that
    # results does not tokenize and parse.
    DOUBLE_QUOTE_FORMS = ("the \"round 7\" case", "\"round 7\"")
    DOUBLE_QUOTE_SKIPS = ((), (), (), ("\"round 7\"",), (), ("\"round 7\"",), (), (), ("\"round 7\"",))
    # Forms that hold a backslash-escaped quote, checked in every placement: an escaped single
    # quote and an escaped double quote at the end of the text, which never end a literal, and a
    # single quote after an escaped backslash, which ends a single-quoted literal early. The skips
    # are pinned literally in PLACEMENTS order and must match expected_skip, whose early closure
    # test reads backslash escapes as the tokenizer does, joined with the parse of the source.
    ESCAPED_FORMS = ("refuting the gemini seed\\\x27s claim", "the \\\"round 7\\\"",
                     "refuting the gemini seed\\\\\x27s claim")
    ESCAPED_SKIPS = ((), (), (), (), (), (), ("refuting the gemini seed\\\\\x27s claim",), (), ())
    # Forms that end a literal early but leave adjacent string literals that still parse, checked in
    # every placement: two double quotes on each side of the label, which end a triple-quoted
    # literal early where they sit just before the closing quotes, and two single quotes on each
    # side, which end the single-quoted literal early. Python joins the adjacent literals, so the
    # source parses and the label is caught, never skipped. The early closures and the empty skips
    # are pinned literally in PLACEMENTS order.
    ADJACENT_FORMS = ("\"\"round 7\"\"", "\x27\x27round 7\x27\x27")
    ADJACENT_EARLY = ((), (), (), ("\"\"round 7\"\"",), (), ("\"\"round 7\"\"",),
                      ("\x27\x27round 7\x27\x27",), (), ("\"\"round 7\"\"",))
    ADJACENT_SKIPS = ((), (), (), (), (), (), (), (), ())
    # Direct checks of the skip oracle, one row per rule it applies: (placement index, text, ends
    # the literal early, parses, skips). An escaped quote never ends the literal and a quote after
    # an escaped backslash does; a backslash before the closing quotes escapes the first of them
    # and leaves the literal unterminated, which counts as early; an early closure that leaves
    # adjacent literals that parse is no skip; and a source that fails to parse with no early
    # closure, in a comment or through a malformed escape in a docstring, is no skip either.
    ORACLE_CASES = ((6, "the change", False, True, False),
                    (6, "refuting the gemini seed\\\x27s claim", False, True, False),
                    (6, "refuting the gemini seed\\\\\x27s claim", True, False, True),
                    (3, "the \\\"round 7\\\"", False, True, False),
                    (3, "\"round 7\"", True, False, True),
                    (3, "\"\"round 7\"\"", True, True, False),
                    (5, "round 7\\", True, False, True),
                    (0, "round 7\n)", False, False, False),
                    (2, "round 7 \\N", False, False, False))
    # String statements of every literal kind, each with a label: an f-string, a bytes literal, a
    # raw bytes literal, an f-string with a replacement field, and a label split over two lines of
    # an f-string. Each is a prose block, so the label is caught at the line where it starts.
    LITERAL_KIND_STATEMENTS = ("x = 1\nf\"\"\"the L5 case\"\"\"\n", "x = 1\nb\"\"\"the L5 case\"\"\"\n",
                               "x = 1\nrb\x27the L5 case\x27\n", "x = 1\nF\"the {x} L5 case\"\n",
                               "x = 1\nf\"\"\"from the gemini\nseed claim\"\"\"\n")
    # The same literal kinds in ordinary code, an assigned value and a call argument, which are not
    # statements of their own, so their short identifiers are not caught.
    LITERAL_KIND_CODE = ("value = f\"C1 {x}\"\n", "value = b\"C1\"\n", "value = rb\x27C1\x27\n",
                         "print(f\"the {x} C1 case\")\n")
    # The prose of a string statement is its parsed literal text: implicitly concatenated literals
    # whose delimiters differ in length, with a label at the end of the last part, and an escape
    # that decodes to a label. Each is caught at the line where it starts.
    PARSED_TEXT_STATEMENTS = ("x = 1\n\"\"\"the case\"\"\" \"and the L5\"\n",
                              "x = 1\nb\"\"\"the case\"\"\" b\x27and the L5\x27\n",
                              "x = 1\nf\"\"\"the {x} case\"\"\" \"and the L5\"\n",
                              "x = 1\n\"the L\\x35 case\"\n")
    # The replacement fields, conversions and format specs of an f-string statement are code, not
    # prose, so a short identifier in them is not caught, while a label in the literal text of the
    # same statement is caught at its own physical line, and at no other line.
    FIELD_CODE_STATEMENTS = ("x = 1\nf\"the {C1} case\"\n", "x = 1\nf\"the {L5!r:>{C1}} case\"\n",
                             "x = 1\nf\"the {x:L5} case\"\n",
                             "x = 1\nf\"\"\"the {f\x27{L5}\x27} case\nand {C1}\"\"\"\n",
                             "x = 1\nf\"{f\x27C1 {x}\x27} ok\"\n")
    FIELD_TEXT_LABELS = (("x = 1\nf\"the {C1} L5 case\"\n", 2),
                         ("x = 1\nf\"\"\"the {C1}\ncase L5\"\"\"\n", 3))
    # Expression statements that start with a literal but are not a literal alone: a percent
    # format, a join and method calls. They are code, so their short identifiers are not caught.
    LITERAL_LED_CODE = ("\"the C1 case %s\" % x\n", "\" C1 \".join(x)\n", "\"the C1 case\".upper()\n",
                        "f\"the {x} C1 case\".strip()\n")
    # Decoded prose is matched against every pattern in its decoded form, so a label that only an
    # escape spells is caught at its own physical line: (source, line, pattern name).
    DECODED_LABELS = (("x = 1\n\"fixed in round \\x37\"\n", 2, "a review round number"),
                      ("x = 1\n\"the fix\\x20round\"\n", 2, "a round of fixes"),
                      ("x = 1\nb\"the codex\\x20QA pass\"\n", 2, "a model-family QA attribution"),
                      ("x = 1\nf\"\"\"the {x} case\nfixed in round \\x37\"\"\"\n", 3, "a review round number"))
    # The parts of one string statement join as Python joins them, with nothing between: a label
    # that two parts on consecutive lines split is caught at the line where it starts, and words
    # that only an inserted space would join into a label are not caught.
    CONCATENATED_LABELS = ("x = 1\n(f\"the L\"\n f\"5 case\")\n", "x = 1\n\"the L\" \\\n\"5 case\"\n",
                           "x = 1\n(\"from the gem\"\n \"ini seed claim\")\n",
                           "x = 1\n(\"fixed in round\"\n \"s 7 and 8\")\n")
    CONCATENATED_CLEAN = ("x = 1\n(\"the fix\"\n \"round trip\")\n", "x = 1\n(f\"a codex\"\n f\"reviewed {x}\")\n")
    # A raw f-string statement reads its literal text raw, from the prefix of its own start token: a
    # label in its literal text is caught, and backslashes that would not decode, or would decode
    # to a label, in a statement with no label are neither caught nor an error.
    RAW_FSTRING_LABELS = ("x = 1\nrf\"the L5 {x} \\d case\"\n", "x = 1\nFR\x27the {x} L5\x27\n")
    RAW_FSTRING_CLEAN = ("x = 1\nrf\"C:\\x\\u {x} \\N done\"\n", "x = 1\nrf\"the L\\x35 {x} case\"\n")
    # The prose of a string statement is matched once, as a whole, on its decoded value as Python
    # builds it, never part by part and never with a line break between parts that the value
    # lacks: parts that spell the exempt round number "round7th" over three lines, a bare id after
    # the word point in the next part, and a longer id that two parts split, are not caught by the
    # value match, and no physical line of these samples matches LABEL_PATTERNS on its own.
    VALUE_CLEAN = ("x = 1\n(\"fixed in round\"\n \"7\"\n \"th of the plan\")\n",
                   "x = 1\n(\"the open point \"\n \"C1 case\")\n",
                   "x = 1\n(\"the C1\"\n \"00 case\")\n")
    # A line break in the value of a string statement is read as Python reads it: an escaped newline
    # is a line break, read as one space, a backslash that ends a line of one part joins the next
    # line with nothing between, in a plain and in a triple-quoted literal, and the indentation
    # around a line break of a docstring is stripped. Each label is caught at the line where it
    # starts: (source, line, pattern name).
    VALUE_LABELS = (("x = 1\n\"the fix\\nround case\"\n", 2, "a round of fixes"),
                    ("x = 1\n\"the finding\\nL5 case\"\n", 2, "a named finding id"),
                    ("x = 1\n\"the L\\\n5 case\"\n", 2, "a bare finding id in prose"),
                    ("x = 1\n\"\"\"the L\\\n5 case\"\"\"\n", 2, "a bare finding id in prose"),
                    ("def f():\n    \"\"\"Handle the fix\n    round case.\"\"\"\n", 2, "a round of fixes"))
    # The colon form is exempt only before a letter on the line of the number in the value: a
    # letter that the next part puts on that line exempts it, and a letter after a line break, an
    # escaped one here, does not. (source, the exact report.)
    VALUE_COLON = (("x = 1\n(\"fixed in round:\"\n \"7 decimal places\")\n", []),
                   ("x = 1\n(\"fixed in round:\"\n \"7\\nof review\")\n",
                    ["x.py:2: a review round number across a line break: round:7"]))
    # Each physical line of a string statement is still matched against LABEL_PATTERNS as source
    # text, so a part that the rest of the value completes into a longer id or an exempt round
    # number, from a later part, from the next line after a joining backslash or from an escape, is
    # caught on its own line, an accepted low-severity false failure that stays caught while the
    # value alone has no match. (source, the exact report.)
    VALUE_LINE_FALSE_FAILURES = (
        ("x = 1\n(\"the F1\"\n \"00 case\")\n", ["x.py:2: a bare finding id: (\"the F1\""]),
        ("x = 1\n(\"the M1\"\n \"23 model\")\n", ["x.py:2: a bare finding id: (\"the M1\""]),
        ("x = 1\n(\"fixed in round 7\"\n \"th of the plan\")\n",
         ["x.py:2: a review round number: (\"fixed in round 7\""]),
        ("x = 1\n\"the F1\\\n00 case\"\n", ["x.py:2: a bare finding id: \"the F1\\"]),
        ("x = 1\n\"the F1\\x300 case\"\n", ["x.py:2: a bare finding id: \"the F1\\x300 case\""]))
    # A backslash just before a replacement field of an f-string or template string statement
    # escapes nothing, and Python keeps it in the literal text, so the decoded value keeps it too
    # and it cannot join the text around the field into a label: one backslash; two, an escaped
    # pair that reads as one backslash and leaves none to keep; and three, of which the escaped
    # pair reads as one backslash and Python keeps the last.
    FIELD_BACKSLASH_STATEMENTS = ("x = 1\nf\"the fix\\{x}round case\"\n",
                                  "x = 1\nf\"the L\\{x}5 case\"\n",
                                  "x = 1\nf\"the fix\\\\{x}round case\"\n",
                                  "x = 1\nf\"the fix\\\\\\{x}round case\"\n")
    # A backslash that ends a physical line of the literal text of an f-string or template string
    # statement still joins the next line with nothing between, as it does in a plain literal, in a
    # triple-quoted and in a single-quoted literal and after a replacement field, so the label it
    # joins is caught at the line where it starts: (source, the exact report).
    JOINED_REPORT = ["x.py:2: a bare finding id in prose across a line break: L5"]
    FIELD_JOINING_STATEMENTS = (("x = 1\nf\"\"\"the L\\\n5 case\"\"\"\n", JOINED_REPORT),
                                ("x = 1\nf\"the L\\\n5 case {x}\"\n", JOINED_REPORT),
                                ("x = 1\nf\"\"\"the {x} L\\\n5 case\"\"\"\n", JOINED_REPORT))
    SPLIT = (("a write that fails removes its output (finding", "L5). A row"),
             ("even when the spellings differ (codex", "reproduced: state_dir x)"),
             ("refuting the gemini", "seed claim"),
             ("as fixed in round", "7 of review"),
             ("as fixed in (fix", "round 16, M1)"))
    SPREAD = ("codex", "independently", "also", "reproduced this failure.")
    # A round number in each form, which the letter and numeral checks complete with a character.
    PLAIN_NUMBER = "round 7"
    COLON_NUMBER = "round: 7"
    # A colon form split before its number over lines, which a letter on the next line does not
    # exempt, and the same with a word on the line of the number, which does: (file, text).
    SPLIT_COLON_CAUGHT = (("x.md", "fixed in round:\n7\nof review\n"),
                          ("x.py", "# fixed in round:\n# 7\n# of review\nx = 1\n"),
                          ("x.py", "\"\"\"fixed in round:\n7\nof review\n\"\"\"\n"))
    SPLIT_COLON_REPORT = ":1: a review round number across a line break: round: 7"
    SPLIT_COLON_EXEMPT = (("x.md", "fixed in round:\n7 decimal places\n"),
                          ("x.py", "# fixed in round:\n# 7 decimal places\nx = 1\n"))
    # 2 round numbers of one form in one text, each found: (text, the matches).
    SECOND_IN_ONE_TEXT = (("fixed in round 7 and round 8", ["round 7", "round 8"]),
                          ("fixed in round: 7, then round: 8", ["round: 7", "round: 8"]))
    # A second round number that a line break splits, reported at line 1: (file, text, match).
    SECOND_ACROSS_LINES = (("x.md", "fixed in round 7 and round\n8 too\n", "round 8"),
                           ("x.py", "# fixed in round 7 and round\n# 8 too\n", "round 8"),
                           ("x.md", "fixed in round: 7, then round:\n8, then x\n", "round: 8"),
                           ("x.py", "# fixed in round: 7, then round:\n# 8, then x\n", "round: 8"))
    # A round number of each form in one text, the earlier found first: (text, the matches).
    EARLIER_IN_ONE_TEXT = (("fixed in round 7 and round: 8", ["round 7", "round: 8"]),
                           ("fixed in round: 7, and round 8", ["round: 7", "round 8"]))
    # The earlier form split over lines, reported at line 1, and the later at line 2: (file, text,
    # the match at line 1).
    EARLIER_ACROSS_LINES = (("x.md", "fixed round\n7 and round: 8\n", "round 7"),
                            ("x.md", "fixed round:\n7, and round 8\n", "round: 7"),
                            ("x.py", "# fixed round\n# 7 and round: 8\n", "round 7"),
                            ("x.py", "# fixed round:\n# 7, and round 8\n", "round: 7"))
    # history pass fixtures: end

    def test_every_known_label_form_is_caught(self):
        for text in self.LABELS + self.WIDENED:
            with self.subTest(text=text):
                self.assertTrue(labels_in(text), text)

    def test_ordinary_prose_and_code_are_not_caught(self):
        for text in self.PROSE:
            with self.subTest(text=text):
                self.assertEqual(labels_in(text), [], text)

    def test_short_identifiers_in_code_are_not_caught(self):
        for text in self.CODE:
            with self.subTest(text=text):
                self.assertEqual(labels_in(text, LABEL_PATTERNS), [], text)
                self.assertEqual(scan("x.py", "value = f({})\n".format(text)), [], text)

    def test_ordinary_python_is_not_caught(self):
        for source in self.ORDINARY_PYTHON:
            with self.subTest(source=source):
                self.assertEqual(scan("x.py", source), [], source)

    def test_labels_in_a_python_comment_are_caught(self):
        for text in self.COMMENT_LABELS:
            with self.subTest(text=text):
                self.assertTrue(scan("x.py", "# fixed in {}\nx = 1\n".format(text)), text)

    def test_accepted_false_failures_stay_caught(self):
        for text in self.FALSE_FAILURES:
            with self.subTest(text=text):
                self.assertTrue(labels_in(text), text)
        for source in self.FALSE_FAILURE_PYTHON:
            with self.subTest(source=source):
                self.assertTrue(scan("x.py", source), source)

    def test_python_code_lines_are_matched_for_round_numbers(self):
        for source in self.CODE_FALSE_FAILURES + self.CODE_STRING_LABELS:
            with self.subTest(source=source):
                self.assertEqual(scan("x.py", source),
                                 ["x.py:1: a review round number: " + source.strip()], source)

    @staticmethod
    def character_after_number(text):
        """The first character after the colon round number in text."""
        return re.search(r"round: [0-9]\s*(.)", text).group(1)

    def test_a_letter_of_every_category_exempts_both_forms(self):
        for text in self.LETTER_EXEMPT:
            with self.subTest(text=text):
                self.assertEqual(labels_in(text), [], text)
                self.assertEqual(scan("x.py", "# {}\nx = 1\n".format(text)), [], text)
                self.assertEqual(scan("x.md", text + "\n"), [], text)
        letters = [self.character_after_number(text) for text in self.LETTER_EXEMPT]
        self.assertEqual({unicodedata.category(char) for char in letters}, {"Lu", "Ll", "Lt", "Lm", "Lo"})
        scripts = {unicodedata.name(char).split()[0] for char in letters}
        self.assertTrue({"CYRILLIC", "ARABIC", "HEBREW", "MODIFIER"} <= scripts, scripts)
        for char in letters:
            with self.subTest(char=char):
                self.assertEqual(labels_in(self.PLAIN_NUMBER + char), [], char)
                self.assertEqual(scan("x.py", "# {}{}\nx = 1\n".format(self.PLAIN_NUMBER, char)), [], char)
                self.assertEqual(scan("x.md", "{}{}\n".format(self.PLAIN_NUMBER, char)), [], char)
                self.assertTrue(labels_in(self.PLAIN_NUMBER + " " + char), char)

    def test_a_numeric_character_that_is_not_a_letter_stays_caught(self):
        numerals = [self.character_after_number(text) for text in self.FALSE_FAILURES
                    if not self.character_after_number(text).isascii()]
        self.assertEqual({unicodedata.category(char) for char in numerals}, {"No", "Nl"})
        for char in numerals:
            for text in (self.COLON_NUMBER + char, self.COLON_NUMBER + " " + char, self.PLAIN_NUMBER + char):
                with self.subTest(text=text):
                    self.assertTrue(labels_in(text), text)
                    self.assertTrue(scan("x.py", "# {}\nx = 1\n".format(text)), text)

    def test_every_caught_form_is_caught_in_every_python_placement(self):
        forms = self.LABELS + self.COMMENT_LABELS + self.WIDENED
        self.assertEqual(len(self.EXPECTED_SKIPS), len(self.PLACEMENTS))
        for placement, expected in zip(self.PLACEMENTS, self.EXPECTED_SKIPS):
            with self.subTest(placement=placement):
                self.assertEqual(scan("x.py", placement.format("the change")), [], placement)
            skipped = set()
            for text in forms:
                source = placement.format(text)
                try:
                    found = scan("x.py", source)
                except (tokenize.TokenError, SyntaxError):
                    skipped.add(text)
                    continue
                with self.subTest(placement=placement, text=text):
                    self.assertTrue(found, source)
            with self.subTest(placement=placement, skipped=sorted(skipped)):
                self.assertEqual(skipped, {text for text in forms if self.expected_skip(placement, text)}, placement)
                self.assertEqual(skipped, set(expected), placement)

    @staticmethod
    def parses(source):
        """Whether source tokenizes and parses as Python."""
        try:
            for _ in tokenize.generate_tokens(io.StringIO(source).readline):
                pass
            ast.parse(source)
        except (tokenize.TokenError, SyntaxError):
            return False
        return True

    @classmethod
    def expected_skip(cls, placement, text):
        """Whether text, put in placement, ends its literal early and leaves source that fails.

        A form skips only when it ends the literal that holds it early, as ends_literal_early
        judges from the delimiter of the placement alone, and the source that results does not
        tokenize and parse. An early closure can leave adjacent string literals that still parse,
        as two double quotes do just before triple closing quotes and two single quotes do inside
        a single-quoted literal, and such a form is checked like any other, not skipped.
        """
        return cls.ends_literal_early(placement, text) and not cls.parses(placement.format(text))

    @staticmethod
    def ends_literal_early(placement, text):
        """Whether text, put in placement, would end the string literal that holds it early.

        The delimiter is the one that opens the literal of the placement itself, read from the
        token that holds the placeholder, so a comment placement never skips and a quote
        character other than that delimiter never counts. A form skips when the delimiter occurs
        in the literal body before the closing delimiter, as a single quote does inside a
        single-quoted literal or a final double quote does just before triple closing quotes. A
        backslash escapes the character after it, as the tokenizer reads the literal, so an escaped
        quote never ends it, while a quote after an escaped backslash does, and a backslash that
        escapes the first closing quote leaves the literal unterminated, which skips too.
        """
        marker = "the change"
        for token in tokenize.generate_tokens(io.StringIO(placement.format(marker)).readline):
            if marker in token.string:
                break
        else:
            raise AssertionError("placement holds no placeholder: " + placement)
        if token.type != tokenize.STRING:
            return False
        opening = QUOTE_OPEN.match(token.string)
        delimiter = opening.group(1)
        body = token.string[len(opening.group(0)):len(token.string) - len(delimiter)]
        body = body.replace(marker, text, 1)
        closed = body + delimiter
        at = 0
        while at < len(closed):
            if closed[at] == "\\":
                at += 2
            elif closed.startswith(delimiter, at):
                return at < len(body)
            else:
                at += 1
        return True

    def check_skips_against_the_oracle(self, forms, skips):
        """Each form in each placement is caught or skipped exactly as expected_skip and skips say."""
        self.assertEqual(len(skips), len(self.PLACEMENTS))
        for placement, expected in zip(self.PLACEMENTS, skips):
            skipped = set()
            for text in forms:
                source = placement.format(text)
                with self.subTest(placement=placement, text=text):
                    try:
                        found = scan("x.py", source)
                    except (tokenize.TokenError, SyntaxError):
                        skipped.add(text)
                    else:
                        self.assertTrue(found, source)
                    self.assertEqual(text in skipped, self.expected_skip(placement, text), source)
            with self.subTest(placement=placement, skipped=sorted(skipped)):
                self.assertEqual(skipped, set(expected), placement)

    def test_a_double_quote_form_is_judged_by_the_delimiter_of_each_placement(self):
        self.check_skips_against_the_oracle(self.DOUBLE_QUOTE_FORMS, self.DOUBLE_QUOTE_SKIPS)

    def test_an_escaped_quote_is_judged_by_the_escape_aware_oracle(self):
        self.check_skips_against_the_oracle(self.ESCAPED_FORMS, self.ESCAPED_SKIPS)

    def test_an_early_closure_that_still_parses_is_caught_not_skipped(self):
        self.assertEqual(len(self.ADJACENT_EARLY), len(self.PLACEMENTS))
        for placement, early in zip(self.PLACEMENTS, self.ADJACENT_EARLY):
            with self.subTest(placement=placement):
                self.assertEqual({text for text in self.ADJACENT_FORMS
                                  if self.ends_literal_early(placement, text)}, set(early), placement)
        self.check_skips_against_the_oracle(self.ADJACENT_FORMS, self.ADJACENT_SKIPS)

    def test_the_skip_oracle_judges_each_rule_directly(self):
        for index, text, early, parsed, skips in self.ORACLE_CASES:
            placement = self.PLACEMENTS[index]
            with self.subTest(placement=placement, text=text):
                self.assertEqual(self.ends_literal_early(placement, text), early, text)
                self.assertEqual(self.parses(placement.format(text)), parsed, text)
                self.assertEqual(self.expected_skip(placement, text), skips, text)

    def test_a_string_statement_of_every_literal_kind_is_a_prose_block(self):
        for source in self.LITERAL_KIND_STATEMENTS:
            with self.subTest(source=source):
                found = scan("x.py", source)
                self.assertTrue(any(hit.startswith("x.py:2: ") for hit in found), found)
        for source in self.LITERAL_KIND_CODE:
            with self.subTest(source=source):
                self.assertEqual(scan("x.py", source), [], source)

    def test_a_template_string_statement_is_a_prose_block(self):
        if not hasattr(ast, "TemplateStr"):
            self.skipTest("this Python parses no template string")
        found = scan("x.py", "x = 1\nt\"\"\"the L5 case\"\"\"\n")
        self.assertTrue(any(hit.startswith("x.py:2: ") for hit in found), found)
        self.assertEqual(scan("x.py", "x = 1\nt\"the {C1:L5} case\"\n"), [])

    def test_the_prose_of_a_string_statement_is_its_parsed_literal_text(self):
        for source in self.PARSED_TEXT_STATEMENTS:
            with self.subTest(source=source):
                found = scan("x.py", source)
                self.assertTrue(any(hit.startswith("x.py:2: ") for hit in found), found)

    def test_the_fields_of_an_f_string_statement_are_code_not_prose(self):
        for source in self.FIELD_CODE_STATEMENTS:
            with self.subTest(source=source):
                self.assertEqual(scan("x.py", source), [], source)
        for source, line in self.FIELD_TEXT_LABELS:
            with self.subTest(source=source):
                found = scan("x.py", source)
                at = "x.py:{}: ".format(line)
                self.assertTrue(any(hit.startswith(at) for hit in found), found)
                self.assertEqual([hit for hit in found if not hit.startswith(at)], [], found)

    def test_an_expression_statement_led_by_a_literal_is_code(self):
        for source in self.LITERAL_LED_CODE:
            with self.subTest(source=source):
                self.assertEqual(scan("x.py", source), [], source)

    def test_decoded_prose_is_matched_against_every_pattern(self):
        for source, line, name in self.DECODED_LABELS:
            with self.subTest(source=source):
                found = scan("x.py", source)
                at = "x.py:{}: {}".format(line, name)
                self.assertTrue(any(hit.startswith(at) for hit in found), found)

    def test_the_parts_of_a_string_statement_join_with_nothing_between(self):
        for source in self.CONCATENATED_LABELS:
            with self.subTest(source=source):
                found = scan("x.py", source)
                self.assertTrue(any(hit.startswith("x.py:2: ") for hit in found), found)
        for source in self.CONCATENATED_CLEAN:
            with self.subTest(source=source):
                self.assertEqual(scan("x.py", source), [], source)

    def test_a_raw_f_string_statement_is_read_raw(self):
        for source in self.RAW_FSTRING_LABELS:
            with self.subTest(source=source):
                found = scan("x.py", source)
                self.assertTrue(any(hit.startswith("x.py:2: ") for hit in found), found)
        for source in self.RAW_FSTRING_CLEAN:
            with self.subTest(source=source):
                self.assertEqual(scan("x.py", source), [], source)

    def test_the_value_of_a_string_statement_is_matched_as_a_whole(self):
        for source in self.VALUE_CLEAN:
            with self.subTest(source=source):
                self.assertEqual(scan("x.py", source), [], source)

    def test_a_line_break_in_a_string_value_is_read_as_python_reads_it(self):
        for source, line, name in self.VALUE_LABELS:
            with self.subTest(source=source):
                found = scan("x.py", source)
                at = "x.py:{}: {}".format(line, name)
                self.assertTrue(any(hit.startswith(at) for hit in found), found)

    def test_a_letter_exempts_the_colon_form_only_on_its_line_of_the_value(self):
        for source, expected in self.VALUE_COLON:
            with self.subTest(source=source):
                self.assertEqual(scan("x.py", source), expected, source)

    def test_a_physical_line_of_a_string_statement_is_still_matched_on_its_own(self):
        for source, expected in self.VALUE_LINE_FALSE_FAILURES:
            with self.subTest(source=source):
                self.assertEqual(scan("x.py", source), expected, source)
                values = python_blocks(source)[1]
                self.assertEqual(len(values), 1, source)
                self.assertEqual(value_hits(*values[0]), [], source)

    @staticmethod
    def built_and_decoded(source):
        """The value Python builds for the last statement of source, and what the scan reads of it.

        Returns that value, the value that the scan decodes from the tokens of the statement, with
        each replacement field read as one space, and the report of the scan of source.
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            node = ast.parse(source).body[-1].value
            found = scan("x.py", source)
            tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        statement = [tok for tok in tokens if node.lineno <= tok.start[0] <= node.end_lineno]
        built = "".join(part.value if isinstance(part, ast.Constant) else " " for part in node.values)
        return built, statement_value(literal_pieces(statement))[0], found

    def test_a_backslash_before_a_replacement_field_is_kept_as_python_keeps_it(self):
        sources = self.FIELD_BACKSLASH_STATEMENTS
        if hasattr(ast, "TemplateStr"):
            sources += ("x = 1\nt\"the fix\\{x}round case\"\n",)
        for source in sources:
            with self.subTest(source=source):
                built, value, found = self.built_and_decoded(source)
                self.assertIn("\\", built, source)
                self.assertEqual(value, built, source)
                self.assertEqual(found, [], source)

    def test_a_backslash_that_ends_a_line_of_an_f_string_still_joins_the_next(self):
        cases = self.FIELD_JOINING_STATEMENTS
        if hasattr(ast, "TemplateStr"):
            cases += (("x = 1\nt\"\"\"the L\\\n5 case\"\"\"\n", self.JOINED_REPORT),)
        for source, expected in cases:
            with self.subTest(source=source):
                built, value, found = self.built_and_decoded(source)
                self.assertNotIn("\\", built, source)
                self.assertEqual(value, built, source)
                self.assertEqual(found, expected, source)

    def test_a_bytes_literal_decodes_with_its_prefix(self):
        self.assertEqual(decoded("the L\\u0035 case", "b"), "the L\\u0035 case")
        self.assertEqual(decoded("the L\\u0035 case", "rb"), "the L\\u0035 case")
        self.assertEqual(decoded("the L\\u0035 case", ""), "the L5 case")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.assertEqual(scan("x.py", "x = 1\nb\"the L\\u0035 case\"\n"), [])
            self.assertTrue(scan("x.py", "x = 1\n\"the L\\u0035 case\"\n"))

    def test_probe_reports_an_f_string_it_cannot_separate_as_unreadable(self):
        message = "this Python does not separate the fields of an f-string"

        def unseparated(tokens):
            raise ValueError(message)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "statement.py"
            path.write_text("\"\"\"Clean.\"\"\"\n", encoding="utf-8")
            try:
                rel = path.resolve().relative_to(ROOT).as_posix()
            except ValueError:
                rel = path.as_posix()
            clean = io.StringIO()
            with contextlib.redirect_stdout(clean):
                self.assertEqual(probe([str(path)]), 0)
            self.assertEqual(clean.getvalue().splitlines(), ["probe: 0 hit(s)"])
            output = io.StringIO()
            with mock.patch.object(sys.modules[__name__], "literal_pieces", unseparated):
                with contextlib.redirect_stdout(output):
                    status = probe([str(path)])
        self.assertEqual(output.getvalue().splitlines(),
                         ["{}: unreadable: {}".format(rel, message), "probe: 1 hit(s)"])
        self.assertEqual(status, 1)

    def test_an_f_string_token_that_hides_its_fields_fails(self):
        text = "f\"the {C1} case\""
        token = tokenize.TokenInfo(tokenize.STRING, text, (1, 0), (1, len(text)), text)
        with self.assertRaises(ValueError):
            literal_pieces([token])

    def test_bare_id_in_python_prose_is_caught(self):
        self.assertTrue(scan("x.py", "# the L5 case\nx = 1\n"))
        self.assertTrue(scan("x.py", "def f():\n    \"\"\"Handle the\n    L5 case.\"\"\"\n"))

    def test_docstring_of_a_one_line_suite_is_caught_at_its_start(self):
        for source in ("x = 1\n\ndef f(): \"\"\"Handle the L5 finding.\"\"\"\n",
                       "x = 1\n\nasync def f(): \"\"\"Handle the L5 finding.\"\"\"\n",
                       "x = 1\n\nclass C: \"\"\"Handle the L5 finding.\"\"\"\n"):
            with self.subTest(source=source):
                found = scan("x.py", source)
                self.assertTrue(any(hit.startswith("x.py:3: ") for hit in found), found)

    def test_a_label_split_across_lines_is_caught_at_its_start(self):
        for first, second in self.SPLIT:
            for rel, text in (("x.py", "# {}\n# {}\n".format(first, second)),
                              ("x.py", "\"\"\"{}\n{}\n\"\"\"\n".format(first, second)),
                              ("x.md", "{}\n{}\n".format(first, second))):
                with self.subTest(rel=rel, text=text):
                    found = scan(rel, text)
                    self.assertTrue(any(hit.startswith(rel + ":1: ") for hit in found), found)

    def test_a_letter_on_the_next_line_does_not_exempt_a_split_colon_form(self):
        for rel, text in self.SPLIT_COLON_CAUGHT:
            with self.subTest(rel=rel, text=text):
                self.assertIn(rel + self.SPLIT_COLON_REPORT, scan(rel, text))
        for rel, text in self.SPLIT_COLON_EXEMPT:
            with self.subTest(rel=rel, text=text):
                self.assertEqual(scan(rel, text), [], text)

    def test_a_label_spread_over_more_than_three_lines_is_caught_at_its_start(self):
        for rel, text in (("x.py", "".join("# {}\n".format(part) for part in self.SPREAD)),
                          ("x.py", "\"\"\"" + "\n".join(self.SPREAD) + "\n\"\"\"\n"),
                          ("x.md", "".join("{}\n".format(part) for part in self.SPREAD))):
            with self.subTest(rel=rel, text=text):
                found = scan(rel, text)
                self.assertTrue(any(hit.startswith(rel + ":1: ") for hit in found), found)

    def test_an_untokenizable_python_file_fails(self):
        with self.assertRaises((tokenize.TokenError, SyntaxError)):
            scan("x.py", "\"\"\"unterminated\n")

    @staticmethod
    def every_round_match(text):
        """Every round number match in text, searched from each start position like split_hits."""
        pattern = RoundNumberPattern()
        found = []
        match = pattern.search(text, 0)
        while match is not None:
            found.append(match.group(0))
            match = pattern.search(text, match.start() + 1)
        return found

    def test_a_second_round_number_in_one_text_is_reported(self):
        for text, matches in self.SECOND_IN_ONE_TEXT:
            with self.subTest(text=text):
                self.assertEqual(self.every_round_match(text), matches)
        for rel, text, second in self.SECOND_ACROSS_LINES:
            with self.subTest(rel=rel, text=text):
                found = scan(rel, text)
                self.assertIn(rel + ":1: a review round number across a line break: " + second, found)

    def test_the_earlier_of_the_two_forms_is_returned(self):
        for text, matches in self.EARLIER_IN_ONE_TEXT:
            with self.subTest(text=text):
                self.assertEqual(self.every_round_match(text), matches)
        for rel, text, first in self.EARLIER_ACROSS_LINES:
            with self.subTest(rel=rel, text=text):
                found = scan(rel, text)
                self.assertIn(rel + ":1: a review round number across a line break: " + first, found)
                self.assertTrue(any(hit.startswith(rel + ":2: a review round number: ") for hit in found), found)


def probe(paths):
    """Scan every file under paths with the lint and print each hit and each unreadable file.

    A file that cannot be read, decoded, tokenized, parsed or, before Python 3.12, separated into
    the fields of an f-string statement is printed as unreadable and counts as a hit. Returns the
    exit status.
    """
    hits = []
    for given in paths:
        root = Path(given)
        files = sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else [root]
        for path in files:
            if "__pycache__" in path.parts:
                continue
            try:
                rel = path.resolve().relative_to(ROOT).as_posix()
            except ValueError:
                rel = path.as_posix()
            try:
                hits.extend(scan(rel, read_text(path), ALLOWLIST.get(rel, ())))
            except (OSError, UnicodeDecodeError, tokenize.TokenError, SyntaxError, ValueError) as error:
                hits.append("{}: unreadable: {}".format(rel, error))
    for hit in hits:
        print(hit)
    print("probe: {} hit(s)".format(len(hits)))
    return 1 if hits else 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--probe"]:
        if not sys.argv[2:]:
            print("probe: no path given", file=sys.stderr)
            sys.exit(2)
        sys.exit(probe(sys.argv[2:]))
    result = unittest.main(exit=False, verbosity=1).result
    sys.exit(0 if result.wasSuccessful() else 1)
