#!/usr/bin/env python3
"""Lint: the orchestration sources carry no internal review-history labels.

A comment or docstring that names the review pass or the finding that once motivated it, such as
"(round 7)", "(fix round 16, M1)", "(F1)", "finding S3" or "claude QA round 10", means nothing to a
later reader and mixes numbering schemes. The text states the reason itself instead. This test
scans every line of each file in SCANNED for the patterns in LABEL_PATTERNS and fails on any match
that is not in ALLOWLIST, the reviewed set of lines whose match is a cross-reference to a named
plan rather than a review label. A scanned file that is missing or unreadable is a failure, never
a skip, and an allowlist entry that no longer matches a scanned line is a failure too, so the
allowlist cannot silently go stale.

Residual: the patterns are a denylist over prose. A label in a form none of them matches, for
example a review pass named in words ("the third review"), passes. The PatternSelfCheck case pins
the forms the patterns are known to cover, so a weakened pattern fails the suite.
"""
import re
import sys
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

LABEL_PATTERNS = (
    ("a review round number", re.compile(r"(?i)\bround[- ]?[0-9]+\b")),
    ("a fix round", re.compile(r"(?i)\bfix round\b")),
    ("a QA round", re.compile(r"(?i)\bQA round\b")),
    ("a model-family QA attribution", re.compile(r"(?i)\b(?:codex|claude|gemini) QA\b")),
    ("a parenthesized finding id", re.compile(r"\([A-Z]{1,2}[0-9]{1,2}(?:[,)]| and )")),
    ("a named finding id", re.compile(r"(?i)\bfindings? [A-Z]{1,2}[0-9]{1,2}\b")),
    ("a severity-numbered finding", re.compile(r"\b(?:CRITICAL|HIGH|MEDIUM|LOW)-[0-9]+\b")),
    ("a bare finding id", re.compile(r"\b(?:AA|BB|[FGMRSTUWX])[0-9]{1,2}\b")),
)

# Reviewed lines whose match is not a review label: the T1 to T15 identifiers of the armed-behaviour
# proofs in the item 28.2 stage-2 plan (section 3), which the stage-2 suite names its cases after.
# Each entry is the exact text of the line.
ALLOWLIST = {
    "tools/test-orch-stage2-hooks.py": (
        "Every armed-behaviour proof (T1 to T15 of the item 28.2 stage-2 plan, section 3, PR1-g) runs against the",
        "Optional keys: T6 (`attestations`, open point P5) and T12 (`mistakes_register`, open point P6) cover keys",
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


def labels_in(line):
    """The names of the label patterns that match line."""
    return [name for name, pattern in LABEL_PATTERNS if pattern.search(line)]


def read_lines(rel):
    """The lines of a scanned file. A missing or unreadable file raises, so the test fails."""
    return (ROOT / rel).read_text(encoding="utf-8").split("\n")


class NoReviewLabels(unittest.TestCase):
    def test_scanned_files_carry_no_unreviewed_label(self):
        found = []
        scanned = 0
        for rel in SCANNED:
            allowed = set(ALLOWLIST.get(rel, ()))
            for number, line in enumerate(read_lines(rel), 1):
                scanned += 1
                names = labels_in(line)
                if names and line not in allowed:
                    found.append("{}:{}: {}: {}".format(rel, number, ", ".join(names), line.strip()))
        self.assertGreater(scanned, 0, "no line was scanned")
        self.assertEqual(found, [], "review-history labels found:\n" + "\n".join(found))

    def test_allowlist_names_only_scanned_files(self):
        self.assertEqual(sorted(set(ALLOWLIST) - set(SCANNED)), [])

    def test_every_allowlist_entry_is_a_live_match(self):
        for rel, entries in ALLOWLIST.items():
            lines = read_lines(rel)
            for entry in entries:
                with self.subTest(file=rel, entry=entry):
                    self.assertEqual(lines.count(entry), 1, "allowlisted line absent or repeated")
                    self.assertTrue(labels_in(entry), "allowlisted line matches no pattern; remove it")


class PatternSelfCheck(unittest.TestCase):
    LABELS = ("(round 7)", "(round-5 fix)", "Round 2 G5: x", "(fix round 16, M1)", "(fix round 17, F1)",
              "Fix round 16 (M1): x", "claude QA round 10", "codex QA HIGH-1", "(codex QA F6)", "(F1)",
              "(G1)", "(M2)", "(AA2)", "(BB1)", "(F1 and G1)", "finding S3", "findings F1 and G1",
              "Finding R7: x", "--- R3: x", "the F1-era test", "HIGH-2: x", "before G1 the")
    PROSE = ("U+3164", "aiqt_hooks.py:8414", "\\x1f", "class T01StopActionable", "sha256",
             "item 28.2 stage 2, PR1-d", "open point P5", "round-trip through json.dumps",
             "Point the command at the QA cycle", "commit d191071", "UTF-8", "line 8:", "the g1 prefix")

    def test_every_known_label_form_is_caught(self):
        for text in self.LABELS:
            with self.subTest(text=text):
                self.assertTrue(labels_in(text), text)

    def test_ordinary_prose_and_code_are_not_caught(self):
        for text in self.PROSE:
            with self.subTest(text=text):
                self.assertEqual(labels_in(text), [], text)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    sys.exit(0 if result.wasSuccessful() else 1)
