#!/usr/bin/env python3
"""Check /flow's mode text and 7 pinned rule paragraphs for a literal regression.

.claude/commands/flow.md tells an orchestrator session how to read the host's mode record. The
only writer of that record, orch-set-mode, writes exactly 2 values, attended-autonomous and
unattended, and .claude/hooks/ask_mode_guard.py names the same 2. A session that follows a /flow
that names another value, or that reads a missing record as "attended", can put a blocking
question to a host that nobody attends. flow.md also states rules that the maintainer's decisions
and the coordinator's rulings set and that a later edit could revert unseen. This check is a
literal regression check of 10 things in flow.md, not a reading of what its sentences mean. It
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
- each of the 7 paragraphs of flow.md into which this change writes rule text, outside the mode
  section, must be in the file once and unchanged: the header, the cycle steps (cycle step 4,
  GRADE, among them), the seeding paragraph, FAILED LEG (the entry list of its whole-line rule,
  Entries 61, 63, 64 and 69, among its text), the CODEX ROLE LIMIT, the tiers paragraph and
  VERIFIER DIVERSITY. A paragraph is a maximal run of lines that are not blank, and a line is
  blank when it is empty or holds only white space, as Python's str.isspace() defines it. Each
  row of PARAGRAPHS gives a paragraph's name, the text that its first line starts with, and the
  sha256 of the paragraph with each run of white space, as Python's str.split() defines it,
  collapsed to 1 space and none at either end. So the check fails when no paragraph or more than
  1 paragraph starts with that text, so an indent put before that text fails too, and when the
  paragraph differs in anything other than the amount or kind of white space between its words
  or after its last word: a character that is not white space added, removed or changed, a
  letter in another case, 2 words joined, a line added to it, or a blank line put inside it. That
  is the cost of this contract: every edit of these 7 paragraphs, meant or not, fails this check
  until the paragraph's sha256 in PARAGRAPHS is updated. For each such paragraph the report gives
  its name, its line range, its new sha256 and the 1-line update to PARAGRAPHS that accepts it.

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
absent rule in other words fails. A pinned paragraph with its words kept and only the white space
between them changed passes, and so does a mention of its opening text inside another paragraph.
Text outside the 7 paragraphs is not pinned: an edit there passes, and so does a paragraph
elsewhere that contradicts one of them, such as one that adds Entry 62 to the entries of the
whole-line rule. An edit committed with the paragraph's new sha256 in PARAGRAPHS passes; the
changed row in the diff is what shows it to a reviewer. tools/test-check-flow-mode.py holds a case
for each verdict named in this docstring.
"""
import hashlib
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

# The 7 paragraphs of flow.md into which this change writes rule text, outside the mode section,
# each with the name the report gives it, the text its first line starts with, and the sha256 of
# its text with its white space collapsed. flow.md is the only copy of their text. Each sha256
# stands alone on its line in the form of DIGEST_LINE, so accepting an edit of a paragraph is
# the 1-line update that the report gives.
PARAGRAPHS = [
    ("the header", "INTERIM. This command's own inlined text",
     "eff52ed68ba81c266e056737cf7fbdeaf8973371d07d8bb43dcc6ff30c95e7ae"),
    ("the cycle steps", "1. REFRESH: ",
     "989b6c8929d8818cd2b63341f622dfaed510c89efed1ef9bf6e12dc050131a94"),
    ("the seeding paragraph", "Per item (the machine-local",
     "9a967eaf04b8ff43cdd6ac9ca8f84600f039c2e5ce3217e456f392a9c86e777d"),
    ("FAILED LEG", "FAILED LEG (every family, every tier):",
     "205b52031f15672704d3a10e7b0b367a28cc6f38da3cb97f79d149130af74ae3"),
    ("the CODEX ROLE LIMIT", "CODEX ROLE LIMIT: ",
     "bf963078ff3d181f83f457ad7aad1294461d8b9f0a17bbbc21bb5be1dcb46843"),
    ("the tiers paragraph", "The tiers (light, substantive, and sensitive)",
     "6a4d7ca0524b52a69295cd0a39d0eb8ab3dfc50a1baa0e0041f09789e9a926d7"),
    ("VERIFIER DIVERSITY", "VERIFIER DIVERSITY (QA, every tier):",
     "eb1f7fc8e9bb4929122a59dbed2fe04ba7629339393a87f6adb23ae85510a70d"),
]
DIGEST_LINE = "     \"{}\"),"
TABLE_FILE = "tools/check-flow-mode.py"


def paragraphs(lines):
    """Each paragraph of lines, a maximal run of lines that are not blank, as its first and last
    line numbers and its text."""
    found = []
    start = None
    for number, line in enumerate(lines + [""], 1):
        if line.strip():
            if start is None:
                start = number
        elif start is not None:
            found.append((start, number - 1, "\n".join(lines[start - 1:number - 1])))
            start = None
    return found


def digest(paragraph):
    """The sha256 of paragraph with each run of white space collapsed to 1 space."""
    return hashlib.sha256(" ".join(paragraph.split()).encode("utf-8")).hexdigest()


def changed_report(name, first, last, label, pinned, now):
    """The report line for a pinned paragraph whose sha256 is no longer the pinned one."""
    return ("{}:{}-{}: {}, a pinned paragraph, has changed: its sha256 is now {}; to accept the"
            " change, replace the line '{}' of PARAGRAPHS in {} with '{}'".format(
                name, first, last, label, now, DIGEST_LINE.format(pinned), TABLE_FILE,
                DIGEST_LINE.format(now)))


def findings(text, name):
    """The report lines for each way text drifts from the writer's values and for each pinned
    paragraph that it does not hold once and unchanged."""
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
    blocks = paragraphs(lines)
    for label, opening, pinned in PARAGRAPHS:
        starting = [block for block in blocks if block[2].startswith(opening)]
        if len(starting) != 1:
            found.append("{}: expected 1 pinned paragraph, {}, starting {!r}, found {}".format(
                name, label, opening, len(starting)))
            continue
        first, last, paragraph = starting[0]
        now = digest(paragraph)
        if now != pinned:
            found.append(changed_report(name, first, last, label, pinned, now))
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
          "\"attended\", the absent-record sentence is present, and the {} pinned paragraphs are "
          "unchanged".format(source, len(PARAGRAPHS)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
