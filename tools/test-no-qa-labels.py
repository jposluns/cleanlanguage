#!/usr/bin/env python3
"""Lint: the orchestration sources carry no internal review-history labels.

A comment or docstring that names the review pass or the finding that once motivated it, such as
"(round 7)", "(fix round 16, M1)", "(F1)", "finding S3" or "claude QA round 10", or that credits
a model family with a finding, such as "codex reproduced" or "the gemini seed", means nothing to a
later reader and mixes numbering schemes. The text states the reason itself instead.

The test scans each file in SCANNED in two ways. Every physical line is matched against
LABEL_PATTERNS. Every prose block, which in a Python file is a run of comments on consecutive
lines or a string statement such as a docstring and elsewhere is a paragraph of consecutive
non-blank lines, is matched line by line against PROSE_PATTERNS as well, and then as one text with
all its line breaks joined against both sets, so a label spread over any number of lines is caught
and reported at the line where it starts. Docstrings are found with ast.get_docstring, so the
docstring of a one-line suite counts too. PROSE_PATTERNS holds the widened bare finding id, which
applies to prose only because code legitimately carries short identifiers such as the closure
value "C1". A match on a line in ALLOWLIST, the reviewed set of lines whose match is a
cross-reference to a named plan rather than a review label, passes. A scanned file that is
missing, unreadable or does not tokenize and parse is a failure, never a skip, and an allowlist
entry that no longer matches a scanned line is a failure too, so the allowlist cannot silently go
stale.

Run with --probe PATH... to apply the same scan to any files or directories, for example the
whole tools/ directory: it prints every hit and every unreadable file, and exits 1 when there is
one.

Residual: this lint is a best-effort guard, not a complete one. Its patterns are a denylist over
prose, and its residual is open-ended: a label in any phrasing, synonym or layout the patterns do
not list passes, and no list of known gaps can close that set. Completeness over the class of
review-history labels therefore rests on an independent search of the scanned files, not on this
lint. The known residual forms are these: a review pass named in words ("the third review"); a
round number after a colon that a letter of any script, any character of Unicode category L,
follows on the same physical line, with or without a space between, as in the text
"round: 7 decimal places" or a time in microseconds written with the micro sign or the Greek
mu, or that a decimal continuation follows, as in "round: 7.5"; a round number that any letter
suffix follows, an ordinal or any other, as in "round 7th" or "round 7a"; a finding id of three
or more capital letters or of more than two digits; a finding id with a hyphen or a
letter suffix, such as "the F-1 case" or "the F1a case", anywhere outside parentheses and the
word "finding"; in prose, a bare id that follows "point " or starts with "PR" (the forms the
plan uses for its open points and pull-request slices), exclusions the code-line bare id pattern
does not make, so "point F1" is still caught on any line; a reviewer named other than as codex,
claude or gemini; a family name more than two words away from its review or credit word, or
credited by a verb outside REVIEW_WORD; in a Python file, a label split across two lines of a
string that is not a statement of its own, such as an argument or an assigned value, which is
matched line by line only; and a bare id in code that does not use one of the letters of the
code-line bare id pattern. The colon form also has false failures, accepted as low severity: any
colon round number that neither a letter nor a decimal continuation follows on its own physical
line is caught, even in ordinary text. Examples, not a complete list: a word that follows the
number only on the next physical line does not exempt it, so such a line fails until the text is
reflowed to keep the word on the line of the number; and a number that a bracket, a percent sign,
an arrow or a numeric character that is not a letter, such as superscript two, a vulgar fraction
or a Roman numeral sign, follows is caught. The PatternSelfCheck case pins the forms the patterns
are known to cover, a letter of each Unicode letter category that exempts the colon form, the
ordinary code and prose they must not flag, these accepted false failures and, for each Python
placement, the literal set of forms it skips because they would end its string literal early, so
a pattern weakened or widened past any of those sets fails the suite.
"""
import ast
import bisect
import io
import re
import sys
import tokenize
import unicodedata
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The files the orchestration work owns, repository-relative.
SCANNED = (
    ".aiqt/config.md",
    ".github/workflows/orchestration-registry.yml",
    "tools/check-orchestration-registry.py",
    "tools/migrate-todo-aei.py",
    "tools/orch-enumerate-backlog.py",
    "tools/orch_doctor.py",
    "tools/test-orch-enumerate-backlog.py",
    "tools/test-orch-migrate-todo.py",
    "tools/test-orch-stage1-hooks.py",
    "tools/test-orch-stage2-hooks.py",
    "tools/test-orchestration-registry.py",
)

FAMILY = r"(?:codex|claude|gemini)"
REVIEW_WORD = (r"(?:reproduc\w*|found|finds|finding\w*|refut\w*|flag\w*|raised|raises"
               r"|caught|spotted|spots|noticed|notices|confirmed|confirms"
               r"|seeds?|review\w*|QA|rounds?)")
NEAR = r"(?:\W+\w+){0,2}?\W+"


class RoundNumberPattern:
    """The review round number pattern, whose colon form is exempt only before a letter.

    The colon form passes only when a letter of any script, a character whose Unicode category
    starts with L, or a decimal continuation follows the number, so "round: 7 decimal places", a
    time in microseconds and "round: 7.5" pass. Any other ending, such as a closing quote, a
    bracket, a mark or a numeric character that is not a letter (superscript two, a vulgar
    fraction or a Roman numeral sign), is caught. The re module has no letter class, so the letter
    test is made in code, and search returns a match the way re.Pattern.search does.

    The matches of both forms are found once for each text searched and kept, so the run of
    searches split_hits makes over one joined block, one from every start position, costs time
    linear in the block instead of a rescan of every remaining exempt colon form for each match.
    A kept match is the match a search from any position up to its start would return: the re
    module tests a word boundary against the whole text, not only from the search position, and
    every match of either form starts where the word round starts and holds no other such start,
    so a search from a later position cannot find a match that starts inside an earlier one.
    """

    PLAIN = re.compile(r"(?i)\brounds?[-\s]*#?[0-9]+\b")
    COLON = re.compile(r"(?i)\brounds?\s*:\s*#?[0-9]+(?!\.?[0-9])")
    SPACE = re.compile(r"\s*")

    def __init__(self):
        self.text = None
        self.plain = self.colon = ()
        self.plain_starts = self.colon_starts = ()

    def letter_follows(self, text, match):
        """Whether a letter follows match in text, after any whitespace."""
        after = self.SPACE.match(text, match.end()).end()
        return after < len(text) and unicodedata.category(text[after]).startswith("L")

    def index(self, text):
        """Find and keep the plain matches and the unexempt colon matches of text, once per text."""
        if text is not self.text:
            self.plain = tuple(self.PLAIN.finditer(text))
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


# Matched against every physical line and every joined prose block.
LABEL_PATTERNS = (
    # The colon form is exempt only before a letter or a decimal continuation; see the class.
    ("a review round number", RoundNumberPattern()),
    ("a fix round", re.compile(r"(?i)\bfix[- ]rounds?\b")),
    ("a QA round", re.compile(r"(?i)\bQA round\b")),
    ("a model-family QA attribution", re.compile(r"(?i)\b(?:codex|claude|gemini) QA\b")),
    ("a reviewer attribution", re.compile(
        r"(?i)\b" + FAMILY + r"\b" + NEAR + REVIEW_WORD + r"\b"
        r"|\b" + REVIEW_WORD + r"\b" + NEAR + FAMILY + r"\b")),
    ("a parenthesized finding id", re.compile(r"\([A-Z]{1,2}-?[0-9]{1,2}[a-z]?(?:[,);:]| and )")),
    ("a named finding id", re.compile(r"(?i)\bfindings? [A-Z]{1,2}-?[0-9]{1,2}[a-z]?\b")),
    ("a severity-numbered finding", re.compile(r"(?i)\b(?:CRITICAL|HIGH|MEDIUM|LOW)-[0-9]+\b")),
    ("a bare finding id", re.compile(r"\b(?:AA|BB|[FGMRSTUWX])[0-9]{1,2}\b")),
)

# Matched against prose only: comments and docstrings in a Python file, every line elsewhere.
PROSE_PATTERNS = (
    ("a bare finding id in prose", re.compile(r"(?<!point )\b(?!PR[0-9])[A-Z]{1,2}[0-9]{1,2}\b")),
)

ALL_PATTERNS = LABEL_PATTERNS + PROSE_PATTERNS

# Reviewed lines whose match is not a review label: the T1 to T15 identifiers of the armed-behaviour
# proofs in the item 28.2 stage-2 plan (section 3), which the stage-2 suite names its cases after,
# and the plan open points P5 and P6. Each entry is the exact text of the line.
ALLOWLIST = {
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


def string_statements(tree):
    """The string-literal expression statements of a parsed module, in source order.

    Every docstring is found with ast.get_docstring on each module, class and function, wherever
    it sits, so the docstring of a one-line suite is included; every other statement that is a
    string literal alone is included as well.
    """
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, DOCSTRING_OWNERS) and ast.get_docstring(node, clean=False) is not None:
            value = node.body[0].value
            found[(value.lineno, value.col_offset)] = value
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
              and isinstance(node.value.value, str)):
            found[(node.value.lineno, node.value.col_offset)] = node.value
    return [found[key] for key in sorted(found)]


def python_blocks(text):
    """The prose blocks of Python source: comment runs on consecutive lines, and string statements.

    Each block is a list of (line number, text) segments, and a string statement starts at the
    line where its literal starts. A source that does not tokenize or parse raises.
    """
    blocks = []
    run = []
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT:
            row = tok.start[0]
            if run and run[-1][0] != row - 1:
                blocks.append(run)
                run = []
            run.append((row, tok.string.lstrip("#").strip()))
    if run:
        blocks.append(run)
    for value in string_statements(ast.parse(text)):
        literal = ast.get_source_segment(text, value)
        opening = QUOTE_OPEN.match(literal or "")
        if opening is None:
            continue
        body = literal[len(opening.group(0)):len(literal) - len(opening.group(1))]
        blocks.append([(value.lineno + offset, part.strip()) for offset, part in enumerate(body.split("\n"))])
    return blocks


def paragraph_blocks(lines):
    """The prose blocks of a non-Python file: paragraphs of consecutive non-blank lines."""
    blocks = []
    run = []
    for number, line in enumerate(lines, 1):
        if line.strip():
            run.append((number, re.sub(r"^\s*#*\s*", "", line).rstrip()))
        elif run:
            blocks.append(run)
            run = []
    if run:
        blocks.append(run)
    return blocks


def split_hits(block):
    """(line number, pattern name, matched text) for each match that crosses a line break.

    The whole block is joined with single spaces and searched as one text, from every start
    position, so a label spread over any number of lines is caught and an earlier match cannot
    hide a later one. A match is reported at the segment where it starts.
    """
    starts = []
    offset = 0
    for _, text in block:
        starts.append(offset)
        offset += len(text) + 1
    joined = " ".join(text for _, text in block)
    hits = []
    for name, pattern in ALL_PATTERNS:
        position = 0
        while True:
            match = pattern.search(joined, position)
            if match is None:
                break
            first = bisect.bisect_right(starts, match.start()) - 1
            last = bisect.bisect_right(starts, match.end()) - 1
            hit = (block[first][0], name, match.group(0))
            if last > first and hit not in hits:
                hits.append(hit)
            position = match.start() + 1
    return hits


def scan(rel, text, allowlist=()):
    """Every unreviewed label in text, as report lines naming rel and the starting line number."""
    lines = text.split("\n")
    allowed = set(allowlist)
    blocks = python_blocks(text) if rel.endswith(".py") else paragraph_blocks(lines)
    names_at = {}
    for number, line in enumerate(lines, 1):
        names_at.setdefault(number, []).extend(labels_in(line, LABEL_PATTERNS))
    for block in blocks:
        for number, segment in block:
            for name in labels_in(segment, PROSE_PATTERNS):
                if name not in names_at[number]:
                    names_at[number].append(name)
    found = []
    for number, names in sorted(names_at.items()):
        if names and lines[number - 1] not in allowed:
            found.append("{}:{}: {}: {}".format(rel, number, ", ".join(names), lines[number - 1].strip()))
    for block in blocks:
        for number, name, matched in split_hits(block):
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

    def test_allowlist_names_only_scanned_files(self):
        self.assertEqual(sorted(set(ALLOWLIST) - set(SCANNED)), [])

    def test_every_allowlist_entry_is_a_live_match(self):
        for rel, entries in ALLOWLIST.items():
            lines = read_text(ROOT / rel).split("\n")
            for entry in entries:
                with self.subTest(file=rel, entry=entry):
                    self.assertEqual(lines.count(entry), 1, "allowlisted line absent or repeated")
                    self.assertTrue(labels_in(entry), "allowlisted line matches no pattern; remove it")


class PatternSelfCheck(unittest.TestCase):
    LABELS = ("(round 7)", "(round-5 fix)", "Round 2 G5: x", "(fix round 16, M1)", "(fix round 17, F1)",
              "Fix round 16 (M1): x", "claude QA round 10", "codex QA HIGH-1", "(codex QA F6)", "(F1)",
              "(G1)", "(M2)", "(AA2)", "(BB1)", "(F1 and G1)", "finding S3", "findings F1 and G1",
              "Finding R7: x", "--- R3: x", "the F1-era test", "HIGH-2: x", "before G1 the",
              "(L5)", "(H3: x)", "(Q2; x)", "finding L5", "the L5 fix", "(codex reproduced: x)",
              "refuting the gemini seed\x27s claim", "flagged by codex", "the claude review",
              "gemini found that", "a codex finding", "raised in the gemini round")
    # Forms added when the guard was widened: round numbers with a colon at a label position, a
    # plural, a number sign or a hyphen, a hyphenated fix round, the credit verbs, a severity id in
    # any case, a hyphenated finding id in parentheses or after the word finding, and a
    # letter-suffixed finding id.
    WIDENED = ("as fixed in round: 7", "rounds 7 and 8", "round #7", "the fix-round change",
               "codex caught this", "spotted by gemini", "claude noticed the gap", "gemini confirmed it",
               "High-1: x", "a high-2 case", "(F1a)", "finding F-1", "(F-1)", "round: 7.",
               "as fixed in round: 7, then", "(round: 7)", "round 7", "round-7", "round: 7",
               "round: 7]", "round: 7?", "round: 7!", "**round: 7**")
    PROSE = ("U+3164", "aiqt_hooks.py:8414", "\\x1f", "class T01StopActionable", "sha256",
             "item 28.2 stage 2, PR1-d", "open point P5", "round-trip through json.dumps",
             "Point the command at the QA cycle", "commit d191071", "UTF-8", "line 8:", "the g1 prefix",
             "The PR1-f doctor tests", "HTTP 400", "SHA256", "a codex worker", "the gemini CLI",
             "maintained with Claude", "Claude, Anthropic, OpenAI, Codex, Copilot, or Gemini",
             "U+FFA0", "U+D800..U+DFFF", "round: 7 decimal places", "round: 7.5",
             "Time per round: 7\u00b5s", "Time per round: 7 \u03bcs",
             "round: 7\u00b5", "round: 7 \u03bc", "round: 7\u5e74")
    # The colon form is exempt before a letter of any script, so one sample stands for each of
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
    FALSE_FAILURE_PYTHON = ("# Keep round: 7\n# decimal places\nx = 1\n",)
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
    # early, by holding its delimiter, cannot sit inside it, so it is skipped for that placement
    # only, and the skipped set must be exactly the forms that would, judged from the delimiter of
    # that placement alone, and equal the literal set pinned for that placement in EXPECTED_SKIPS.
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
    # pinned literally in PLACEMENTS order and must match the skip derived from the delimiter of
    # each placement alone.
    DOUBLE_QUOTE_FORMS = ("the \"round 7\" case", "\"round 7\"")
    DOUBLE_QUOTE_SKIPS = ((), (), (), ("\"round 7\"",), (), ("\"round 7\"",), (), (), ("\"round 7\"",))
    SPLIT = (("a write that fails removes its output (finding", "L5). A row"),
             ("even when the spellings differ (codex", "reproduced: state_dir x)"),
             ("refuting the gemini", "seed claim"),
             ("as fixed in round", "7 of review"),
             ("as fixed in (fix", "round 16, M1)"))
    SPREAD = ("codex", "independently", "also", "reproduced this failure.")

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

    @staticmethod
    def character_after_number(text):
        """The first character after the colon round number in text."""
        return re.search(r"round: 7\s*(.)", text).group(1)

    def test_a_letter_of_every_category_exempts_the_colon_form(self):
        for text in self.LETTER_EXEMPT:
            with self.subTest(text=text):
                self.assertEqual(labels_in(text), [], text)
                self.assertEqual(scan("x.py", "# {}\nx = 1\n".format(text)), [], text)
                self.assertEqual(scan("x.md", text + "\n"), [], text)
        letters = [self.character_after_number(text) for text in self.LETTER_EXEMPT]
        self.assertEqual({unicodedata.category(char) for char in letters}, {"Lu", "Ll", "Lt", "Lm", "Lo"})
        scripts = {unicodedata.name(char).split()[0] for char in letters}
        self.assertTrue({"CYRILLIC", "ARABIC", "HEBREW", "MODIFIER"} <= scripts, scripts)

    def test_a_numeric_character_that_is_not_a_letter_stays_caught(self):
        numerals = [self.character_after_number(text) for text in self.FALSE_FAILURES
                    if not self.character_after_number(text).isascii()]
        self.assertEqual({unicodedata.category(char) for char in numerals}, {"No", "Nl"})
        for char in numerals:
            for text in ("round: 7" + char, "round: 7 " + char):
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
    def expected_skip(placement, text):
        """Whether text, put in placement, would end the string literal that holds it early.

        The delimiter is the one that opens the literal of the placement itself, read from the
        token that holds the placeholder, so a comment placement never skips and a quote
        character other than that delimiter never counts. A form skips when the delimiter occurs
        in the literal body before the closing delimiter, as a single quote does inside a
        single-quoted literal or a final double quote does just before triple closing quotes.
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
        return (body + delimiter).find(delimiter) < len(body)

    def test_a_double_quote_form_is_judged_by_the_delimiter_of_each_placement(self):
        self.assertEqual(len(self.DOUBLE_QUOTE_SKIPS), len(self.PLACEMENTS))
        for placement, expected in zip(self.PLACEMENTS, self.DOUBLE_QUOTE_SKIPS):
            skipped = set()
            for text in self.DOUBLE_QUOTE_FORMS:
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


def probe(paths):
    """Scan every file under paths with the lint and print each hit. Returns the exit status."""
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
            except (OSError, UnicodeDecodeError, tokenize.TokenError, SyntaxError) as error:
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
