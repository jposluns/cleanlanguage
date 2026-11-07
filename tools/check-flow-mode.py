#!/usr/bin/env python3
"""Check /flow's mode text for a literal regression to the retired mode words.

.claude/commands/flow.md tells an orchestrator session how to read the host's mode record. The
only writer of that record, orch-set-mode, writes exactly 2 values, attended-autonomous and
unattended, and .claude/hooks/ask_mode_guard.py takes the same 2. A session that follows a /flow
that names another value, or that reads a missing record as "attended", can put a blocking
question to a host that nobody attends. This check is a literal regression check of 3 things in
flow.md, not a reading of what its sentences mean. It fails when any of them is missing:

- exactly 1 line is a MODE line, a line that starts "- MODE (", and it names exactly
  attended-autonomous and unattended, separated by "|", in either order: a missing value, an
  extra value or another separator fails, and so do no MODE line and 2 MODE lines;
- no line may hold an unquoted bare "attended": the word "attended", in any letter case, that is
  not part of a longer word such as "unattended", is not the start of "attended-autonomous", and
  is not inside a pair of double quotes on one line;
- the file must hold the sentence that an absent mode record is read as unattended, in the words
  "reads an absent mode record as unattended" or "an absent mode record is read as unattended",
  in any letter case and matched across line breaks.

Usage: python3 -I tools/check-flow-mode.py [PATH]
PATH defaults to .claude/commands/flow.md in this checkout; "-" reads the text from standard input,
so a copy from another commit can be checked through git show.
Exit status: 0 when every check passes, 1 on any finding, when the text cannot be read or is not
UTF-8, and when more than 1 argument is given.

Residual: the check reads text literally. A mode value other than the 2 is checked only on the
MODE line, so a third value named on any other line passes. Any text inside a pair of double
quotes on one line is skipped, so a bare value or a retired default written inside quotes passes.
Any ordinary use of the English word "attended" outside double quotes, such as "the call was
attended", fails the check, so such a sentence must be reworded or quote the word. The check
cannot tell whether a sentence states the rule it matches or only mentions those words. So a
sentence elsewhere that contradicts the absent rule passes while the matched words stay; the
matched sentence itself can be negated and still pass, as in "The session never reads an absent
mode record as unattended; it reads it as attended-autonomous"; and a correct statement of the
absent rule in other words fails. A quoted phrase that wraps across a line break is not skipped,
so it can fail the check falsely. tools/test-check-flow-mode.py holds a case for each verdict
named in this docstring.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / ".claude" / "commands" / "flow.md"

# The 2 values orch-set-mode writes, as the guard copies them; a change to the writer's list is a
# change to this check.
WRITER_VALUES = ["attended-autonomous", "unattended"]

MODE_LINE = re.compile(r"^- MODE \(([^)\n]*)\)", re.MULTILINE)
BARE_ATTENDED = re.compile(r"(?i)\battended\b(?!-autonomous\b)")
QUOTED = re.compile(r"\"[^\"\n]*\"")
ABSENT_RULE = re.compile(r"(?i)\breads an absent mode record as unattended\b"
                         r"|\ban absent mode record is read as unattended\b")


def findings(text, name):
    """The report lines for each way text drifts from the writer's values."""
    found = []
    modes = MODE_LINE.findall(text)
    if len(modes) != 1:
        found.append("{}: expected 1 MODE line starting \"- MODE (\", found {}".format(name, len(modes)))
    for values in modes:
        named = [value.strip() for value in values.split("|")]
        if sorted(named) != sorted(WRITER_VALUES):
            found.append("{}: the MODE line names {}, not exactly {}".format(
                name, " | ".join(named), " | ".join(WRITER_VALUES)))
    for number, line in enumerate(text.split("\n"), 1):
        # flow.md names the retired value inside double quotes, so quoted text is skipped and
        # only an unquoted "attended" is reported, whatever the sentence around it means.
        if BARE_ATTENDED.search(QUOTED.sub("", line)):
            found.append("{}:{}: unquoted bare \"attended\": {}".format(
                name, number, line.strip()))
    if not ABSENT_RULE.search(" ".join(text.split())):
        found.append("{}: no statement that an absent mode record is read as unattended".format(name))
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
          "\"attended\", and the absent-record sentence is present".format(source))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
