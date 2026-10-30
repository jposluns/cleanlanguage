#!/usr/bin/env python3
"""Lint: the orchestration sources carry no internal review-history labels.

A comment or docstring that names the review pass or the finding that once motivated it, such as
"(round 7)", "(fix round 16, M1)", "(F1)", "finding S3" or "claude QA round 10", or that credits
a model family with a finding, such as "codex reproduced" or "the gemini seed", means nothing to a
later reader and mixes numbering schemes. The text states the reason itself instead.

The test scans each file in SCANNED in two ways. Every physical line is matched against
LABEL_PATTERNS. Every prose block, which in a Python file is a run of comments on consecutive
lines or a docstring and elsewhere is a paragraph of consecutive non-blank lines, is matched line
by line against PROSE_PATTERNS as well, and then with its line breaks joined against both sets, so
a label split across two lines is caught and reported at the line where it starts. PROSE_PATTERNS
holds the widened bare finding id, which applies to prose only because code legitimately carries
short identifiers such as the closure value "C1". A match on a line in ALLOWLIST, the reviewed set
of lines whose match is a cross-reference to a named plan rather than a review label, passes. A
scanned file that is missing, unreadable or does not tokenize is a failure, never a skip, and an
allowlist entry that no longer matches a scanned line is a failure too, so the allowlist cannot
silently go stale.

Run with --probe PATH... to apply the same scan to any files or directories, for example the
whole tools/ directory: it prints every hit and every unreadable file, and exits 1 when there is
one.

Residual: the patterns are a denylist over prose. A label in a form none of them matches passes,
for example a review pass named in words ("the third review"), a finding id of three or more
capital letters or of more than two digits, a bare id that follows "point " or starts with "PR"
(the forms the plan uses for its open points and pull-request slices), a reviewer named other than
as codex, claude or gemini, or a family name more than two words away from the review word. In a
Python file a string that is not a docstring is matched line by line only, so a label split across
two lines of an ordinary string literal passes, and a bare id in code passes unless it uses one of
the letters of the code-line bare id pattern. The PatternSelfCheck case pins the forms the patterns
are known to cover, so a weakened pattern fails the suite.
"""
import io
import re
import sys
import tokenize
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
               r"|seeds?|review\w*|QA|rounds?)")
NEAR = r"(?:\W+\w+){0,2}?\W+"

# Matched against every physical line and every joined prose block.
LABEL_PATTERNS = (
    ("a review round number", re.compile(r"(?i)\bround[- ]?[0-9]+\b")),
    ("a fix round", re.compile(r"(?i)\bfix round\b")),
    ("a QA round", re.compile(r"(?i)\bQA round\b")),
    ("a model-family QA attribution", re.compile(r"(?i)\b(?:codex|claude|gemini) QA\b")),
    ("a reviewer attribution", re.compile(
        r"(?i)\b" + FAMILY + r"\b" + NEAR + REVIEW_WORD + r"\b"
        r"|\b" + REVIEW_WORD + r"\b" + NEAR + FAMILY + r"\b")),
    ("a parenthesized finding id", re.compile(r"\([A-Z]{1,2}[0-9]{1,2}(?:[,);:]| and )")),
    ("a named finding id", re.compile(r"(?i)\bfindings? [A-Z]{1,2}[0-9]{1,2}\b")),
    ("a severity-numbered finding", re.compile(r"\b(?:CRITICAL|HIGH|MEDIUM|LOW)-[0-9]+\b")),
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
SKIPPED = (tokenize.NL, tokenize.COMMENT)
LOGICAL_START = (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING)


def labels_in(line, patterns=ALL_PATTERNS):
    """The names of the patterns that match line."""
    return [name for name, pattern in patterns if pattern.search(line)]


def read_text(path):
    """The text of a file. A missing or unreadable file raises, so the caller fails."""
    return Path(path).read_text(encoding="utf-8")


def python_blocks(text):
    """The prose blocks of Python source: comment runs on consecutive lines, and docstrings.

    Each block is a list of (line number, text) segments. A source that does not tokenize raises.
    """
    blocks = []
    run = []
    tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    significant = [tok for tok in tokens if tok.type not in SKIPPED]
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            row = tok.start[0]
            if run and run[-1][0] != row - 1:
                blocks.append(run)
                run = []
            run.append((row, tok.string.lstrip("#").strip()))
    if run:
        blocks.append(run)
    for index, tok in enumerate(significant):
        if tok.type != tokenize.STRING:
            continue
        before = significant[index - 1].type if index else None
        after = significant[index + 1].type if index + 1 < len(significant) else None
        if before not in LOGICAL_START + (None,) or after not in (tokenize.NEWLINE, tokenize.ENDMARKER):
            continue
        opening = QUOTE_OPEN.match(tok.string)
        if opening is None:
            continue
        body = tok.string[len(opening.group(0)):len(tok.string) - len(opening.group(1))]
        row = tok.start[0]
        blocks.append([(row + offset, part.strip()) for offset, part in enumerate(body.split("\n"))])
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

    A match is reported at the segment where it starts. Each break is searched with a window of
    the three segments from there, and from every start position, so an earlier match on the same
    line cannot hide a later one that crosses the break.
    """
    hits = []
    for index in range(len(block) - 1):
        window = " ".join(text for _, text in block[index:index + 3])
        boundary = len(block[index][1])
        for name, pattern in ALL_PATTERNS:
            position = 0
            while position <= boundary:
                match = pattern.search(window, position)
                if match is None or match.start() >= boundary:
                    break
                if match.end() > boundary:
                    hits.append((block[index][0], name, match.group(0)))
                    break
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
    PROSE = ("U+3164", "aiqt_hooks.py:8414", "\\x1f", "class T01StopActionable", "sha256",
             "item 28.2 stage 2, PR1-d", "open point P5", "round-trip through json.dumps",
             "Point the command at the QA cycle", "commit d191071", "UTF-8", "line 8:", "the g1 prefix",
             "The PR1-f doctor tests", "HTTP 400", "SHA256", "a codex worker", "the gemini CLI",
             "maintained with Claude", "Claude, Anthropic, OpenAI, Codex, Copilot, or Gemini")
    CODE = ("closure=\"C1\", opened=\"2026-09-01\"", "[\"2\", \"2026-09-02\", \"Second\", \"C2\"]")
    SPLIT = (("a write that fails removes its output (finding", "L5). A row"),
             ("even when the spellings differ (codex", "reproduced: state_dir x)"),
             ("refuting the gemini", "seed claim"),
             ("as fixed in round", "7 of review"),
             ("as fixed in (fix", "round 16, M1)"))

    def test_every_known_label_form_is_caught(self):
        for text in self.LABELS:
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

    def test_bare_id_in_python_prose_is_caught(self):
        self.assertTrue(scan("x.py", "# the L5 case\nx = 1\n"))
        self.assertTrue(scan("x.py", "def f():\n    \"\"\"Handle the\n    L5 case.\"\"\"\n"))

    def test_a_label_split_across_lines_is_caught_at_its_start(self):
        for first, second in self.SPLIT:
            for rel, text in (("x.py", "# {}\n# {}\n".format(first, second)),
                              ("x.py", "\"\"\"{}\n{}\n\"\"\"\n".format(first, second)),
                              ("x.md", "{}\n{}\n".format(first, second))):
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
