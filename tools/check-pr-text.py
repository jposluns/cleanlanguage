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
- an empty or blank text, in either text, which includes a description whose body is null: a
  text is blank when nothing is left of it once whitespace, U+200B, U+FEFF and HTML comments are
  removed, and a comment opened with "<!--" and never closed runs to the end of the text;
- a code fence that is opened and never closed, in either text, reported at the line of its
  opener, since every line after that opener is masked as fenced code;
- in the squash message only, a line over 72 characters;
- in the squash message only, a revision id: 7 to 40 characters from 0 to 9 and a to f, holding
  at least 1 digit and at least 1 letter, matched on the raw line, so a revision id written as
  inline code still fails;
- in the squash message only, a subject that does not end with " (#<number>)".

Before the label, dash and spelling checks, the gate masks fenced code blocks, inline code spans,
URLs, and the text on 1 line between a pair of straight double quote marks, or between U+201C
and the next U+201D, which holds quoted language and also any other text between such a pair,
such as the text between 2 inch marks. A mixed or reversed pair, such as a straight mark closed
by U+201D, or U+201D before U+201C, is not masked. Each masked character becomes a space, so a
word boundary next to a masked span survives.

A fenced code block opens on a line of 0 to 3 spaces and then 3 or more backticks or tildes; a
backtick opener with a backtick in the rest of its line is not a fence. The block runs to the
next line of 0 to 3 spaces and then at least as many of the opener's character, followed by
nothing but spaces or tabs, as CommonMark reads it. When a fence is never closed, the block runs
to the end of the text, as a renderer shows those lines as code, and the unclosed fence is
reported as a defect, so the masked lines do not pass unseen. An inline code span opens on a run
of backticks and closes on the next run of exactly as many backticks on the same line; a run
with no such closer is plain text. The scan that finds the spans takes time linear in the length
of the line. A URL starts with http:// or https:// and ends before the first whitespace, angle
bracket, quote mark (straight, or U+2018, U+2019, U+201C or U+201D), backtick, U+2013 or U+2014;
a parenthesis is part of it only in a pair, such as (bar), with no parenthesis inside; and a
trailing full stop, comma, semicolon, colon, exclamation mark or question mark is not part of it.

The width check skips fenced code and a line whose excess over 72 characters lies in 1 URL: the
URL starts within the first 73 characters, so that every character past the 72nd is part of it,
and reaches the end of the line, so a line that goes on past the URL, even with closing
punctuation alone, is checked as any other. The description has no width check, because a
renderer reflows a Markdown paragraph, so an unwrapped paragraph is honest there, and no
revision-id check, because a revision id is legitimate in a description. A carriage return
before a line feed is dropped before any check.

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
not hold, such as vaporis-; a listed stem with a prefix or a further suffix, such as the stem
organ after the prefix re- or before the ending -isational, or the stem author after un-; a
dash other than U+2013 and U+2014, such as the figure dash U+2012 or the horizontal bar U+2015;
a defect inside a masked region, such as an em dash inside double quotes, between 2 inch marks
or in the lines that an unclosed fence masks; a defect in a region that the gate masks but a
renderer shows as prose, such as a fence inside an HTML block or a span opened by a backtick
escaped with a backslash; a message typed into the merge dialog that differs from the
committed file; and a description edited after the last run.

The known false failures are a class, accepted with no escape: honest text that the gate reads
otherwise than a renderer shows it, or that its patterns cannot tell from a defect. Examples:
code in an indented block, in a list item or in a blockquote, which the gate reads as prose, and
whose fence line can be reported as never closed; a code span or a quotation that wraps a line,
since each mask works on 1 line; in a squash message, a URL in angle brackets or backticks, or
followed by punctuation, that runs past 72 characters; in a squash message, a line that
combining marks push past 72 code points, since the width counts code points; a run of 7 to 40
hexadecimal characters with a digit and a letter in a squash message, such as a 12-character hex
run, a digest prefix or the revision id in a commit URL; and a bare id of 1 or 2 capital
letters and 1 or 2 digits in prose, which the lint reads as a finding id.

Usage, from any working directory: the gate finds the lint and the squash folder from its own
path, never from the working directory, and reads any UTF-8 text file.

    check-pr-text.py --event PATH                 the payload, then .github/squash/<number>.txt
    check-pr-text.py --description PATH           a description file
    check-pr-text.py --squash PATH [--number N]   a squash-message file

With --number N, the subject must end with " (#N)"; N is a number of 1 to 18 digits with no
leading zero. Without it, the number comes from the file name when the path ends
.github/squash/<number>.txt, where <number> is such a number; otherwise, as for 0.txt or 007.txt,
the gate prints the line "pr-text: subject binding not checked", which is not a defect, and goes
on. The bound of 18 digits keeps the conversions of the --number value and of the squash file
name to a number far under the limit of 4300 digits that Python sets. A payload whose number
has more than 4300 digits is reported as unreadable, with "not JSON", since the JSON reader
refuses it.

The exit status and the output, for the inputs the gate reads (the 2 texts, the event payload,
the squash file and the arguments): exit 0 when the texts are clean, 1 on any defect, and 2 on
unreadable input or a usage error. Unreadable input is a missing or unparseable payload, an
event that is not a pull request or whose body is neither null nor text, a missing or
undecodable squash file or text file, a working directory that cannot be read when a relative
squash path needs it, a lint that cannot be loaded or that raises, exits or is interrupted
while it loads, and any other exception raised while the gate reads and checks, such as from a
scan of the lint, SystemExit and KeyboardInterrupt among them. Every output line starts with 1 of
the fixed ASCII prefixes description, squash, unreadable: and pr-text:, and every character
outside printable ASCII in a reported line is written as a backslash escape, so no author text
starts a line of output. The last line is "pr-text: <n> defect(s)", also on exit 2.

Residual of that promise: the label lint is trusted repository code that runs in the gate
process, so a lint that ends the process, such as with os._exit, writes to standard output or
closes it can end the gate with another status, with no count line or with a line that has no
prefix. So can a standard output that cannot be written, and an input that never ends, such as
a FIFO given as the squash file, which the job's time limit ends.
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
MAX_DIGITS = 18
EXIT_DEFECT = 1
EXIT_UNREADABLE = 2
EXIT_USAGE = 2
USAGE = "usage: check-pr-text.py --event PATH | --description PATH | --squash PATH [--number N]"
LINT_FAILURE = "label lint {} cannot be loaded: {}"

FENCE = re.compile(r"^ {0,3}(`{3,}(?=[^`]*$)|~{3,})")
BACKTICKS = re.compile(r"`+")
URL = re.compile(r"\bhttps?://(?:[^\s<>\"'`()\u2013\u2014\u201c\u201d\u2018\u2019]"
                 r"|\([^\s<>\"'`()\u2013\u2014\u201c\u201d\u2018\u2019]*\))*"
                 r"(?<![.,;:!?])")
QUOTED = re.compile(r"\"[^\"\n]*\"|\u201c[^\u201d\n]*\u201d")
MASKS = (URL, QUOTED)
MASK_CHAR = " "
COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)
INVISIBLE = re.compile(r"[\s\u200b\ufeff]")

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


def describe(error):
    """The type name and message of a caught error, as plain text that cannot raise.

    An error from the lint can carry a message whose formatting raises, even SystemExit or
    KeyboardInterrupt; that is caught with every other exception, and the type name, or a
    fixed phrase, stands in for the part that cannot be formatted.
    """
    try:
        name = str.__str__(str(type(error).__name__))
    except BaseException:
        name = "an exception"
    try:
        text = str.__str__(str(error))
    except BaseException:
        return name + " (its message cannot be formatted)"
    return name + ": " + text


def load_scan():
    """The scan function of the label lint, loaded by file path; a failure is unreadable input.

    A lint that exits or is interrupted while it loads raises SystemExit or KeyboardInterrupt,
    which is caught with every other exception and reported.
    """
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("pr_text_label_lint", LINT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        scan = module.scan
    except BaseException as error:
        raise Unreadable(LINT_FAILURE.format(LINT, describe(error))) from error
    return scan


def blank(text):
    """Whether nothing is left of text once HTML comments, whitespace, U+200B and U+FEFF go.

    A comment runs from "<!--" to the next "-->", or to the end of the text when it is never
    closed.
    """
    return not INVISIBLE.sub("", COMMENT.sub("", text))


def fenced(lines):
    """(inside, unclosed) for the fenced code blocks of lines.

    inside holds the indexes of the lines inside a fenced code block, its fences included; when
    a fence is opened and never closed, every line from its opener to the end is inside, as a
    renderer shows them as code. unclosed is the index of that opener, or None when every fence
    is closed.
    """
    inside = set()
    opener = None
    start = None
    for index, line in enumerate(lines):
        match = FENCE.match(line)
        if opener is None:
            if match:
                opener = match.group(1)
                start = index
                inside.add(index)
            continue
        inside.add(index)
        if (match and match.group(1)[0] == opener[0] and len(match.group(1)) >= len(opener)
                and not line[match.end():].strip(" \t")):
            opener = None
    return inside, (start if opener is not None else None)


def code_spans(line):
    """The (start, end) spans of the inline code spans of line, found in linear time.

    A span opens on a run of backticks and closes on the next run of exactly as many backticks;
    a run with no such closer on the line is plain text, and the scan goes on after it. closer
    holds, for each run, the index of the next run of the same length, found in 1 pass from the
    end of the line.
    """
    runs = [match.span() for match in BACKTICKS.finditer(line)]
    closer = [None] * len(runs)
    later = {}
    for index in range(len(runs) - 1, -1, -1):
        width = runs[index][1] - runs[index][0]
        closer[index] = later.get(width)
        later[width] = index
    spans = []
    index = 0
    while index < len(runs):
        if closer[index] is None:
            index += 1
        else:
            spans.append((runs[index][0], runs[closer[index]][1]))
            index = closer[index] + 1
    return spans


def masked(line, spans):
    """line with each character of each (start, end) span written as MASK_CHAR."""
    chars = list(line)
    for start, end in spans:
        chars[start:end] = MASK_CHAR * (end - start)
    return "".join(chars)


def mask(line):
    """line with each inline code span, then each URL and double-quoted text, masked."""
    line = masked(line, code_spans(line))
    for pattern in MASKS:
        line = masked(line, [match.span() for match in pattern.finditer(line)])
    return line


def excess_is_url(line):
    """Whether every character of line past the width limit lies in 1 URL."""
    return any(match.start() <= WIDTH and match.end() >= len(line)
               for match in URL.finditer(line))


def check_text(report, prefix, text, squash, scan):
    """Report the defects of 1 text; squash adds the width and revision-id checks."""
    if blank(text):
        report.defect(prefix, ": the text is empty")
        return
    lines = text.split("\n")
    fence, unclosed = fenced(lines)
    if unclosed is not None:
        report.defect(prefix, ":{0}: the code fence opened on line {0} is never closed".format(
            unclosed + 1))
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
    if blank(text):
        return
    if number is None:
        report.note("pr-text:", " subject binding not checked")
        return
    subject = text.split("\n", 1)[0]
    suffix = " (#{})".format(number)
    if not subject.endswith(suffix):
        report.defect("squash", ':1: the subject does not end with "{}": {}'.format(
            suffix, subject))


def bounded_number(digits):
    """int(digits), or None when digits holds more than MAX_DIGITS digits."""
    if len(digits) > MAX_DIGITS:
        return None
    return int(digits)


def number_from_name(path):
    """The number in a path that ends .github/squash/<number>.txt, or None."""
    try:
        parts = Path(path).absolute().parts
    except OSError as error:
        raise Unreadable("squash file {}: the working directory cannot be read: {}".format(
            path, error.strerror or error)) from error
    if len(parts) >= 3 and parts[-3:-1] == (".github", "squash") and SQUASH_NAME.fullmatch(
            parts[-1]):
        return bounded_number(parts[-1][:-len(".txt")])
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
        number = bounded_number(options["--number"])
        if number is None:
            raise Usage("--number takes at most {} digits".format(MAX_DIGITS))
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
    except BaseException as error:
        # A scan of the lint, or a hit it returns, that raises SystemExit or KeyboardInterrupt
        # is caught here, as load_scan() catches a lint that does so while it loads, so it
        # cannot end the gate with no report. describe() keeps an error whose message raises
        # from escaping this handler.
        report.note("unreadable:", " the gate stopped on an unexpected error: {}".format(
            describe(error)))
        status = EXIT_UNREADABLE
    report.note("pr-text:", " {} defect(s)".format(report.count))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
