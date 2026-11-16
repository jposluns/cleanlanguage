#!/usr/bin/env python3
"""Check /flow's mode text and 8 pinned rule texts for a literal regression.

.claude/commands/flow.md tells an orchestrator session how to read the host's mode record. The
only writer of that record, orch-set-mode, writes exactly 2 values, attended-autonomous and
unattended, and .claude/hooks/ask_mode_guard.py names the same 2. A session that follows a /flow
that names another value, or that reads a missing record as "attended", can put a blocking
question to a host that nobody attends. flow.md also states rules that the maintainer's decisions
and the coordinator's rulings set and that a later edit could revert unseen. This check is a
literal regression check of 11 things in flow.md, not a reading of what its sentences mean. It
fails when any of them is missing:

- exactly 1 line is a MODE line, a line whose first characters are "- MODE (", closed or not; that
  line closes its parenthesis on the same line, and the text between the parentheses names
  exactly attended-autonomous and unattended, each once and in lower case, separated by "|", in
  either order: a missing value, an extra or repeated value, a value with a capital letter,
  another separator or a value inside quotes fails, and so do no MODE line, 2 MODE lines and a
  MODE line with no closing parenthesis;
- no line may hold an unquoted bare "attended": the word "attended", in any letter case, with no
  letter, digit or underscore just before or just after it, so "unattended" and "attendedness"
  are not bare; that is not followed at once by "-autonomous", in any letter case, with no
  letter, digit or underscore just after that, so "attended-autonomous" and "Attended-Autonomous"
  are not bare while "attended-autonomously" is; and that is not between a pair of straight double
  quotes (") that the check pairs left to right on the same line. The test reads each such
  quotation, its quotes included, as 1 space, so the text on its 2 sides stays apart, as it is
  in the line, and is never joined into a word that the line does not hold: the line 'A legacy
  un"stored"attended record.' holds a bare "attended" and fails, and the line 'The session runs
  attended-autonomous"x"ly.' holds none and passes;
- the file must hold the sentence that an absent mode record is read as unattended, in the words
  "reads an absent mode record as unattended" or "an absent mode record is read as unattended",
  in any letter case and matched across line breaks;
- the file must hold each of these 8 pinned texts, in the letter case given and matched across
  line breaks, each a run of spaces and line breaks matching any other such run, and each
  bounded: a space, a line break, or the start or end of the file must come just before its first
  character and just after its last, so a pinned text joined to other characters on either side
  fails. Each pinned text runs from where its clause or phrase starts in flow.md to the
  punctuation that ends it, so a word added to it, removed from it or changed in it fails, and
  so does an entry list that adds an entry, such as Entry 62, before or after its other entries:
  - the header's statement of which tier rules /flow keeps: "apart from the 2 tier rules that it
    names as kept here, the escalation rule of cycle step 4 (GRADE) and the AIQT HOLD;";
  - the attribution of the whole-line rule to Entry 125: "(3) a quote in it breaches the
    whole-line rule that Entry 125 states,";
  - the entry list of the whole-line rule: "the rule of the maintainer decisions of Entries 61,
    63, 64 and 69 (2026-11-14 and 2026-11-15; the coordinator's correction recorded with Entry
    127, 2026-11-15, gives the rule's entries as these 4):";
  - the whole-line test of the FAILED LEG rule: "a single-line quote must be a whole line, from
    the line's first character to its last, and a range quote must be whole lines;";
  - the allowances of the whole-line rule: "either of them also when it matches in that way only
    once either or both of 2 allowances apply, each line's leading spaces stripped or its
    Markdown formatting marks (backticks, emphasis asterisks or underscores) missing, with each
    offset, range, collapse and mark recorded;";
  - the failures of the whole-line rule: "a quote of only part of a line, text more than 1 line
    off, changed or missing words, a dropped comment marker, or any other changed character
    fails it.";
  - the tier floor of the CODEX ROLE LIMIT: "A critical change is never graded light: it is of at
    least the substantive tier,";
  - the statement of which tier rules /flow keeps: "so do the 2 tier rules kept here, which the
    "Working method" section names: in cycle step 4 (GRADE), escalation is immediate and
    de-escalation needs a maintainer decision and a recorded basis; and the AIQT HOLD above.".

Usage: python3 -I tools/check-flow-mode.py [PATH]
PATH defaults to .claude/commands/flow.md in this checkout; "-" reads the text from standard input,
so a copy from another commit can be checked through git show.
Exit status: 0 when every check passes, 1 on any finding, when the text cannot be read or is not
UTF-8, and when more than 1 argument is given.

Residual: the check reads text literally. Outside the MODE line, the bare "attended" test is the
only test that can fail a line for what it holds, so a line there fails exactly when it holds a
bare "attended" outside the text that this test skips as quoted, and passes otherwise, whatever
mode value it names: a third value such as "supervised" named there passes, and one that holds a
bare "attended", such as "attended-only", fails. A line that holds "- MODE (" after any other
character, such as an indented one, is not a MODE line, so the MODE line tests do not read it. Only
the bare "attended" test skips quoted text, and only text between straight double quotes that it
pairs left to right on one line, so a retired default written inside such quotes passes, while
"attended" inside typographic quotes (U+201C and U+201D) fails. Straight double quotes do not show
which one opens a quotation and which one closes it, so this pairing can differ from the author's
quotations when a quotation wraps across a line break. A quoted phrase that wraps is not skipped,
so it can fail the check falsely. A bare "attended" can also pass: a line that closes a quotation
opened on the line above pairs that closing quote with the next opening quote on the line, so a
bare "attended" between them is skipped, as in the line 'unattended" though Absent = attended
"for now".'. No pairing rule for straight quotes recovers every author's quotations, so the check
keeps this simple rule and states this limit. The MODE line and absent-rule tests read quoted
text as any other text, so the absent-rule sentence inside a quotation that rejects it passes.
Any ordinary use of the English word "attended" outside the text that the check skips, such as
"the call was attended", fails the check, so such a sentence must be reworded or quote the word.
The check cannot tell whether a sentence states the rule it matches or only mentions those words.
So a sentence elsewhere that contradicts the absent rule passes while the matched words stay; the
matched sentence itself can be negated and still pass, as in "The session never reads an absent
mode record as unattended; it reads it as attended-autonomous"; and a correct statement of the
absent rule in other words fails. The same holds for each pinned text: one rewrapped across
other line breaks passes, one kept inside a sentence that negates it passes, a sentence elsewhere
that contradicts it passes, such as one that adds Entry 62 to the entries of the whole-line rule,
and the same rule in other words fails. tools/test-check-flow-mode.py holds a case for each
verdict named in this docstring.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / ".claude" / "commands" / "flow.md"

# The 2 values orch-set-mode writes, as the guard copies them; a change to the writer's list is a
# change to this check.
WRITER_VALUES = ["attended-autonomous", "unattended"]

# Every line that starts with this prefix counts as a MODE line, closed or not, so a second
# declaration cannot escape the count by leaving out its closing parenthesis.
MODE_PREFIX = "- MODE ("
MODE_VALUES = re.compile(r"- MODE \(([^)]*)\)")
BARE_ATTENDED = re.compile(r"(?i)\battended\b(?!-autonomous\b)")
QUOTED = re.compile(r"\"[^\"\n]*\"")
ABSENT_RULE = re.compile(r"(?i)\breads an absent mode record as unattended\b"
                         r"|\ban absent mode record is read as unattended\b")

# Texts that flow.md must hold word for word, each with the name the report gives it. The check
# collapses each run of spaces and line breaks in flow.md to 1 space before it looks for them, so
# a pin matches however its words wrap. Each pin runs from where its clause or phrase starts to
# the punctuation that ends it, and PIN_TEXTS bounds each match by white space or the end of the
# text on both sides, so a pin that a longer text holds, such as an entry list with a further
# entry joined to it, does not match.
PINS = [
    ("the header's statement of which tier rules /flow keeps",
     "apart from the 2 tier rules that it names as kept here, the escalation rule of cycle step 4"
     " (GRADE) and the AIQT HOLD;"),
    ("the attribution of the whole-line rule to Entry 125",
     "(3) a quote in it breaches the whole-line rule that Entry 125 states,"),
    ("the entry list of the whole-line rule",
     "the rule of the maintainer decisions of Entries 61, 63, 64 and 69 (2026-11-14 and"
     " 2026-11-15; the coordinator's correction recorded with Entry 127, 2026-11-15, gives the"
     " rule's entries as these 4):"),
    ("the whole-line test of the FAILED LEG rule",
     "a single-line quote must be a whole line, from the line's first character to its last, and a"
     " range quote must be whole lines;"),
    ("the allowances of the whole-line rule",
     "either of them also when it matches in that way only once either or both of 2 allowances"
     " apply, each line's leading spaces stripped or its Markdown formatting marks (backticks,"
     " emphasis asterisks or underscores) missing, with each offset, range, collapse and mark"
     " recorded;"),
    ("the failures of the whole-line rule",
     "a quote of only part of a line, text more than 1 line off, changed or missing words, a"
     " dropped comment marker, or any other changed character fails it."),
    ("the tier floor of the CODEX ROLE LIMIT",
     "A critical change is never graded light: it is of at least the substantive tier,"),
    ("the statement of which tier rules /flow keeps",
     "so do the 2 tier rules kept here, which the \"Working method\" section names: in cycle step 4"
     " (GRADE), escalation is immediate and de-escalation needs a maintainer decision and a"
     " recorded basis; and the AIQT HOLD above."),
]
PIN_TEXTS = [(label, pin, re.compile(r"(?<!\S)" + re.escape(pin) + r"(?!\S)"))
             for label, pin in PINS]


def findings(text, name):
    """The report lines for each way text drifts from the writer's values and for each pinned
    text that it does not hold."""
    found = []
    lines = text.split("\n")
    modes = [(number, line) for number, line in enumerate(lines, 1) if line.startswith(MODE_PREFIX)]
    if len(modes) != 1:
        found.append("{}: expected 1 MODE line starting \"- MODE (\", found {}".format(name, len(modes)))
    for number, line in modes:
        closed = MODE_VALUES.match(line)
        if not closed:
            found.append("{}:{}: the MODE line has no closing parenthesis: {}".format(
                name, number, line.strip()))
            continue
        values = closed.group(1)
        named = [value.strip() for value in values.split("|")]
        if sorted(named) != sorted(WRITER_VALUES):
            found.append("{}: the MODE line names {}, not exactly {}".format(
                name, " | ".join(named), " | ".join(WRITER_VALUES)))
    for number, line in enumerate(lines, 1):
        # flow.md names the retired value inside straight double quotes, so this test alone skips
        # text between straight double quotes paired left to right on the line and reports every
        # other bare "attended", whatever the sentence means. The docstring states where that
        # pairing differs from the author's quotations. Each skipped quotation becomes 1 space, not
        # nothing, so the text on its 2 sides stays apart and the test sees the line's own word
        # boundaries: deleting it would join that text into words that the line does not hold.
        if BARE_ATTENDED.search(QUOTED.sub(" ", line)):
            found.append("{}:{}: unquoted bare \"attended\": {}".format(
                name, number, line.strip()))
    joined = " ".join(text.split())
    if not ABSENT_RULE.search(joined):
        found.append("{}: no statement that an absent mode record is read as unattended".format(name))
    for label, pin, bounded in PIN_TEXTS:
        if not bounded.search(joined):
            found.append("{}: the pinned text of {} is missing: {}".format(name, label, pin))
    return found


def main(argv):
    if len(argv) > 1:
        print("usage: python3 -I tools/check-flow-mode.py [PATH]")
        return 1
    source = argv[0] if argv else str(DEFAULT)
    try:
        if source == "-":
            text = sys.stdin.buffer.read().decode("utf-8")
        else:
            text = Path(source).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print("FAIL: {} cannot be read: {}".format(source, exc))
        return 1
    found = findings(text, source)
    for line in found:
        print("FAIL: " + line)
    if found:
        print("FAIL: {} finding(s)".format(len(found)))
        return 1
    print("OK: {}: the MODE line names the writer's 2 modes, no line holds an unquoted bare "
          "\"attended\", and the absent-record sentence and the {} pinned texts are present".format(
              source, len(PINS)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
