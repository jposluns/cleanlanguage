#!/usr/bin/env python3
"""Check a pull request description and its committed squash-message file for text defects.

The gate reads 2 texts: the description, which is the body of the pull request, and the squash
message, the file .github/squash/<number>.txt that the pull request commits and that stays on
main after the merge. The subject, the first line of that file, must end with the pull request
number in the form " (#<number>)", so the file is bound to 1 pull request by its path and by its
subject.

The defect classes, each with a failing case in tools/test-check-pr-text.py:

- a review-history label, in either text: the patterns of tools/test-no-qa-labels.py, loaded by
  file path, whose scan function is called with a name ending .md, so its paragraph reader and
  both of its pattern sets apply;
- an em dash (U+2014) or an en dash (U+2013), in either text, including an en dash in a numeric
  range, which the writing standard replaces with a hyphen or the word "to";
- an -ise spelling of a word whose -ize form the writing standard asks for, in either text, from
  a denylist of stems such as organis- and standardis-;
- an empty or blank text, in either text, which includes a description whose body is null;
- in the squash message only, a line over 72 characters;
- in the squash message only, a revision id: 7 to 40 characters from 0 to 9 and a to f, holding
  at least 1 digit and at least 1 letter, matched on the raw line, so a revision id written as
  inline code still fails;
- in the squash message only, a subject that does not end with " (#<number>)".

Before the label, dash and spelling checks, the gate masks fenced code blocks, inline code spans,
URLs and text inside double quotes, since the writing standard keeps quoted language as it is.
The width check skips fenced code and a line whose excess over 72 characters lies in 1 URL. The
description has no width check, because a renderer reflows a Markdown paragraph, so an unwrapped
paragraph is honest there, and no revision-id check, because a revision id is legitimate in a
description. A carriage return before a line feed is dropped before any check.

The maintainer's decisions that this gate embodies:

- Advisory first: the gate runs on every pull request and blocks no merge. It is not a required
  check, and tools/ci-status.py does not insist on it. The maintainer decides on required status
  after the false-failure rate on real descriptions is measured.
- Existing history stays unchecked: the gate applies to new pull requests. It reads no git
  history and makes no git call, so the squash messages already on main are not checked.
- Counts stated with their selection rule stay a judgement for reviewers. No part of that class
  is mechanical: no pattern tells a count whose selecting rule is stated from one whose rule is
  missing, so the class has no committed failing case.
- The writing-standard checks are the dashes and the -ise spellings only. There is no ASCII
  check, because the writing standard states no ASCII rule, so such a check would enforce a rule
  the standard lacks and fail honest accented or quoted text. There is no numerals check,
  because the numerals rule keeps canonical forms, such as World War II, that a pattern cannot
  tell apart from a number written in words.
- No escape list: there is no allow-list or other escape for an honest false failure; the author
  rewords.

The gate checks the committed squash-message file, not the message typed or pasted into the
merge dialog, and the description as it stands in the event payload of the run.

Residual: this gate is a best-effort guard, not a complete one. Its patterns are denylists over
text, and its residual is open-ended: a defect in any form the patterns do not list passes, and
no list of known gaps can close that set. The known residual forms are these: a label in a
phrasing the lint does not list, such as a review pass named in words (the lint's docstring
names its own residual forms); a revision id in a form the pattern misses, such as one in upper
case, one of more than 40 characters or one made only of digits; an -ise stem the denylist does
not hold, such as vaporis-; a dash other than U+2013 and U+2014, such as the figure dash U+2012
or the horizontal bar U+2015; a defect inside a masked region, such as an em dash inside double
quotes; a message typed into the merge dialog that differs from the committed file; and a
description edited after the last run. The known false failures, accepted with no escape: a run
of 7 to 40 hexadecimal characters with a digit and a letter in a squash message, such as a
12-character hex run or a digest prefix; and a bare id of 1 or 2 capital letters and 1 or 2
digits in prose, which the lint reads as a finding id.

Usage, from any working directory: the gate finds the lint and the squash folder from its own
path, never from the working directory, and reads any UTF-8 text file.

    check-pr-text.py --event PATH                 the payload, then .github/squash/<number>.txt
    check-pr-text.py --description PATH           a description file
    check-pr-text.py --squash PATH [--number N]   a squash-message file

With --number N, the subject must end with " (#N)". Without it, the number comes from the file
name when the path ends .github/squash/<digits>.txt; otherwise the gate prints the line
"pr-text: subject binding not checked", which is not a defect, and goes on.

Exit 0 when the texts are clean, 1 on any defect, and 2 on unreadable input (a missing or
unparseable payload, an event that is not a pull request, a missing or undecodable squash file
or text file, or a lint that cannot be loaded) or a usage error. Every output line starts with
1 of the fixed ASCII prefixes description, squash, unreadable: and pr-text:, and every character
outside printable ASCII in a reported line is written as a backslash escape, so no author text
starts a line of output. The last line is "pr-text: <n> defect(s)", also on exit 2.
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINT = ROOT / "tools" / "test-no-qa-labels.py"
SQUASH_DIR = ROOT / ".github" / "squash"
WIDTH = 72
EXIT_DEFECT = 1
EXIT_UNREADABLE = 2
EXIT_USAGE = 2
USAGE = "usage: check-pr-text.py --event PATH | --description PATH | --squash PATH [--number N]"
LINT_FAILURE = "label lint {} cannot be loaded: {}"

FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
INLINE_CODE = re.compile(r"(`+)[^\n]*?\1")
URL = re.compile(r"\bhttps?://[^\s<>\"'`]+")
QUOTED = re.compile(r"\"[^\"\n]*\"|\u201c[^\u201d\n]*\u201d")
MASKS = (INLINE_CODE, URL, QUOTED)

DASHES = (
    ("an em dash, U+2014", "\u2014"),
    ("an en dash, U+2013", "\u2013"),
)

ISE_STEMS = (
    "apolog", "author", "capital", "categor", "central", "character", "critic", "custom",
    "emphas", "final", "formal", "general", "harmon", "initial", "legal", "local", "maxim",
    "memor", "minim", "mobil", "modern", "neutral", "normal", "optim", "organ", "parameter",
    "priorit", "random", "real", "recogn", "sanit", "serial", "special", "stabil",
    "standard", "summar", "synchron", "token", "util", "visual",
)
ISE = re.compile(r"(?i)\b(?:" + "|".join(ISE_STEMS)
                 + r")is(?:e|es|ed|ing|er|ers|able|ation|ations)\b")

REVISION = re.compile(r"\b(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
SQUASH_NAME = re.compile(r"[1-9][0-9]*\.txt")


class Unreadable(Exception):
    """An input the gate cannot read or does not accept as what it was given as."""


class Usage(Exception):
    """A command line the gate does not accept."""


def ascii_text(text):
    """text with every character outside printable ASCII written as a backslash escape."""
    out = []
    for char in text:
        code = ord(char)
        if 0x20 <= code < 0x7f:
            out.append(char)
        elif code < 0x100:
            out.append("\\x{:02x}".format(code))
        elif code < 0x10000:
            out.append("\\u{:04x}".format(code))
        else:
            out.append("\\U{:08x}".format(code))
    return "".join(out)


def emit(prefix, detail):
    """Print 1 report line: a fixed prefix, then the detail in printable ASCII."""
    print(prefix + ascii_text(detail))


class Report:
    """The report lines printed so far and the number of defects among them."""

    def __init__(self):
        self.count = 0

    def defect(self, prefix, detail):
        self.count += 1
        emit(prefix, detail)

    def note(self, prefix, detail):
        emit(prefix, detail)


def read_utf8(path, what):
    """The text of the file at path, decoded as strict UTF-8, with CRLF read as LF."""
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        raise Unreadable("{} {}: {}".format(what, path, error.strerror or error)) from error
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise Unreadable("{} {}: not UTF-8: {}".format(what, path, error)) from error
    return text.replace("\r\n", "\n")


def read_event(path):
    """(number, description) from a pull request event payload file."""
    text = read_utf8(path, "event payload")
    try:
        event = json.loads(text)
    except (ValueError, RecursionError) as error:
        raise Unreadable("event payload {}: not JSON: {}".format(path, error)) from error
    pull = event.get("pull_request") if isinstance(event, dict) else None
    if not isinstance(pull, dict):
        raise Unreadable("event payload {}: not a pull request event".format(path))
    number = pull.get("number")
    if type(number) is not int or number < 1:
        raise Unreadable("event payload {}: no positive integer pull request number".format(path))
    body = pull.get("body")
    if body is None:
        body = ""
    if not isinstance(body, str):
        raise Unreadable("event payload {}: the pull request body is not text".format(path))
    return number, body.replace("\r\n", "\n")


def load_scan():
    """The scan function of the label lint, loaded by file path; a failure is unreadable input."""
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("pr_text_label_lint", LINT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        scan = module.scan
    except Exception as error:
        raise Unreadable(LINT_FAILURE.format(LINT, error)) from error
    return scan


def fenced(lines):
    """The indexes of the lines inside a fenced code block, its fences included."""
    inside = set()
    opener = None
    for index, line in enumerate(lines):
        match = FENCE.match(line)
        if opener is None:
            if match:
                opener = match.group(1)
                inside.add(index)
            continue
        inside.add(index)
        if (match and match.group(1)[0] == opener[0] and len(match.group(1)) >= len(opener)
                and not line[match.end():].strip()):
            opener = None
    return inside


def mask(line):
    """line with each inline code span, URL and double-quoted text replaced by underscores."""
    for pattern in MASKS:
        line = pattern.sub(lambda match: "_" * len(match.group(0)), line)
    return line


def excess_is_url(line):
    """Whether every character of line past the width limit lies in 1 URL."""
    return any(match.start() <= WIDTH and match.end() >= len(line)
               for match in URL.finditer(line))


def check_text(report, prefix, text, squash, scan):
    """Report the defects of 1 text; squash adds the width and revision-id checks."""
    if not text.strip():
        report.defect(prefix, ": the text is empty")
        return
    lines = text.split("\n")
    fence = fenced(lines)
    prose = ["" if index in fence else mask(line) for index, line in enumerate(lines)]
    rel = prefix + ".md"
    hits = scan(rel, "\n".join(prose))
    for hit in hits:
        report.defect(prefix, hit[len(rel):])
    for number, line in enumerate(prose, 1):
        for name, dash in DASHES:
            if dash in line:
                report.defect(prefix, ":{}: {}: {}".format(number, name, line.strip()))
        for match in ISE.finditer(line):
            report.defect(prefix, ":{}: an -ise spelling: {}".format(number, match.group(0)))
    width_applies = squash
    revision_applies = squash
    if width_applies:
        for number, line in enumerate(lines, 1):
            exempt = number - 1 in fence or excess_is_url(line)
            if len(line) > WIDTH and not exempt:
                report.defect(prefix, ":{}: {} characters, over {}: {}".format(
                    number, len(line), WIDTH, line))
    if revision_applies:
        for number, raw in enumerate(lines, 1):
            for match in REVISION.finditer(raw):
                report.defect(prefix, ":{}: a revision id: {}".format(number, match.group(0)))


def check_squash(report, text, number, scan):
    """Report the defects of a squash message, then its subject binding when number is known."""
    check_text(report, "squash", text, True, scan)
    if not text.strip():
        return
    if number is None:
        report.note("pr-text:", " subject binding not checked")
        return
    subject = text.split("\n", 1)[0]
    suffix = " (#{})".format(number)
    if not subject.endswith(suffix):
        report.defect("squash", ':1: the subject does not end with "{}": {}'.format(
            suffix, subject))


def number_from_name(path):
    """The number in a path that ends .github/squash/<digits>.txt, or None."""
    parts = Path(path).absolute().parts
    if len(parts) >= 3 and parts[-3:-1] == (".github", "squash") and SQUASH_NAME.fullmatch(
            parts[-1]):
        return int(parts[-1][:-len(".txt")])
    return None


def parse(argv):
    """(mode, path, number) from the arguments; raises Usage on anything else."""
    if not argv:
        raise Usage("no mode given")
    options = {}
    rest = list(argv)
    while rest:
        flag = rest.pop(0)
        if flag not in ("--event", "--description", "--squash", "--number"):
            raise Usage("unknown argument {}".format(flag))
        if flag in options or not rest:
            raise Usage("{} needs 1 value and is given once".format(flag))
        options[flag] = rest.pop(0)
    modes = [flag for flag in ("--event", "--description", "--squash") if flag in options]
    if len(modes) != 1:
        raise Usage("give exactly 1 of --event, --description and --squash")
    number = None
    if "--number" in options:
        if modes[0] != "--squash":
            raise Usage("--number applies to --squash only")
        if not re.fullmatch(r"[1-9][0-9]*", options["--number"]):
            raise Usage("--number takes a positive integer")
        number = int(options["--number"])
    return modes[0], options[modes[0]], number


def main(argv):
    """Run the gate on the arguments and return its exit status."""
    report = Report()
    try:
        mode, path, given_number = parse(argv)
        scan = load_scan()
        if mode == "--event":
            number, body = read_event(path)
            check_text(report, "description", body, False, scan)
            squash_path = SQUASH_DIR / "{}.txt".format(number)
            check_squash(report, read_utf8(squash_path, "squash file"), number, scan)
        elif mode == "--description":
            check_text(report, "description", read_utf8(path, "description file"), False, scan)
        else:
            number = given_number if given_number is not None else number_from_name(path)
            check_squash(report, read_utf8(path, "squash file"), number, scan)
        status = EXIT_DEFECT if report.count else 0
    except Usage as error:
        report.note("pr-text:", " {}; {}".format(error, USAGE))
        status = EXIT_USAGE
    except Unreadable as error:
        report.note("unreadable:", " {}".format(error))
        status = EXIT_UNREADABLE
    report.note("pr-text:", " {} defect(s)".format(report.count))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
