#!/usr/bin/env python3
"""Tests for tools/check-flow-mode.py: its verdict on the flow.md texts it must pass or fail.

Each case runs the check as a separate process, isolated (-I), and asserts its exit status, 0 for
a pass and 1 for a failure, and for a failure the report line that names the reason, except 5
cases that start no check process: 1 compares the check's table with the test's own list and
with flow.md, 2 call the check's findings in this process with the check's table changed, for
each edit of an opening text and for each character of WHITE in it, 1 loads a copy of the check
whose bytecode cache is stale, and 1 parses the check's source to find its sites. Each case that
reads the check in this process compiles or parses it from its source as it is now, so no
bytecode cache stands in for that source. Most cases give the check the text on standard input.
Each case that starts the check reads its standard output alone, and each run that it starts
through launch() must write nothing to standard error, so a check that writes a line there, in
place of standard output or as well, fails; the case of a folder as a standard stream starts the
check without launch(), since Python itself stops before the check runs and writes its own fatal
error there, as the check's docstring states. A case that loads the check or calls its findings
in this process does not read standard error.

The check pins the 7 paragraphs of .claude/commands/flow.md that NAMED below lists, by name and
opening text; every edit of those 7 paragraphs that changes more than the white space between
their words or after their last word fails the check, and so does a blank line put inside 1 of
them. The report that a paragraph still found once has changed stays until the paragraph's
sha256 in the check's PARAGRAPHS is updated. The test holds its own list, so a check whose table
drops, adds or moves a paragraph fails, and it reads the paragraph texts only from flow.md.

The verdict cases are these. The committed flow.md passes on standard input, as a path argument
and as the default path. Each pass in a verdict case must print only the whole pass line, which
names the text read, "-" on standard input and the file through a path or the default path, and
gives the count of pinned paragraphs. The check's table
names the 7 paragraphs of NAMED, in that order and with the same opening texts; each of its
sha256 values is the one this test computes from flow.md, and each stands alone on 1 line of the
check in the form that the report gives. The entry list of the whole-line rule, Entries 61, 63,
64 and 69, lies inside the pinned FAILED LEG paragraph. The mode text of main's flow.md at ee6be48
fails with 16 findings, 9 from the mode tests and 1 for each pinned paragraph, which the copied
lines do not hold; the case copies the lines of that flow.md that the mode tests report, so it
needs no git history and runs in a shallow checkout. For each of the 7 pinned paragraphs, the
committed flow.md with 1 change each fails with the report that the paragraph has changed when a
word is appended to it, its last character is removed, a character is joined just after its
opening text, a letter changes case, a comma becomes a semicolon, 2 words are joined, a blank
line or a line of white space is put inside it, a line is added just after it, or the blank line
after it is removed so that it joins the next paragraph; it fails with the paragraph found 0
times when its opening text changes, when an indent is put before its opening text, when a blank
line or a line of white space is put inside its opening text, or when the blank line before it
is removed so that it joins the paragraph before it, and found 2 times when it is repeated; and
it passes when the white space between 2 of its words is replaced by a line
break and an indent, a carriage return and a line break, a tab, a no-break space, an em space, an
ideographic space, a unit separator (U+001F), a line separator (U+2028) or a doubled space, and
when white space is put after its last word. With every pinned paragraph changed at once, the
committed flow.md passes when the first space inside each opening text and the first space after
it are both replaced by each of those kinds of white space or by any 1 character that
str.isspace() counts as white space; it fails with the report that each paragraph has changed
when a line that holds only 1 such character, other than a line feed or a carriage return, is put
inside each paragraph; and it reads the same bytes on standard input and through a path by 1
rule, under which only a line feed, a carriage return or both end a line: each other white-space
character doubled between 2 words of each paragraph passes, and 2 line feeds, 2 carriage
returns, 2 carriage return and line feed pairs, or a carriage return, a space and a line feed
there fail with the report that each paragraph has changed. The MODE line tests and the bare
"attended" test read lines by the same rule, on standard input and through a path: "- MODE ("
just after a line feed, a carriage return or both makes a second MODE line, and just after any
other white-space character it does not; the 2 quotes of a quotation on either side of a line
end do not pair, so the "attended" inside it is bare, and a closing quote at the start of a line
pairs with the next quote on that line, while across any other white-space character the quotes
pair as on 1 line; the absent-record sentence wrapped at any white-space character is found; and
the committed flow.md with carriage returns, or carriage return and line feed pairs, for its line
ends passes. Each of 3 texts gives its whole expected output, every report line in order with
its counts and line numbers, and the count of findings, on standard input, through a path and
through the default path, which a copy of the check with only its DEFAULT line rewritten reads
when it runs with no argument, as CI runs the check; each report line names the text read, "-"
on standard input and the file's path through a path and through the default path, a file whose
name holds every kind of white space that ends no line inside it and at its end, which each
report gives as it is. Each text is read as built and again after 99999 blank lines, so that each
line number and line range that the check reports for it has 6 digits. Between them the 3 texts
give every kind of report line
of the check's findings: the committed flow.md with every test failed at once, by a word
appended to each pinned paragraph, a third value on the MODE line that holds every kind of
white space that ends no line between 2 of its letters, with every kind of white space that ends
no line at either end of each value, which the report leaves out while it keeps the white space
inside the third value, a bare "attended" added on a line that holds every such kind between 2
of its words, which its report keeps, and the absent-record sentence removed, gives 10 reports;
with the opening text of each pinned paragraph changed, its MODE line left unclosed and a
second, unclosed MODE line with every kind of white space that ends no line between 2 of its
words and at its end added, it gives 10, 1 for each paragraph found 0 times, 1 for 2 MODE lines
and 2 for a MODE line with no closing parenthesis, each giving the line without the white space
at its ends and with the white space between its words kept; and with each pinned paragraph
repeated and its MODE line renamed, it gives 8, 1 for each paragraph found 2 times and 1 for no
MODE line. Each report of a number found gives that number
on each of the 3 reads, which print the whole expected output: with the MODE line written each
number of times from 2 to 11, and 99, 100, 101 and 1000 times, the opening text of each pinned
paragraph starting a different number of paragraphs from that number up, so from 2 to 17, 99 to
107 and 1000 to 1006, and as many lines that hold a bare "attended", each with every kind of
white space that ends no line at either end, as MODE lines put at the end, the check prints the
report of each number found, the
report of each bare "attended" with its line number and the line without that white space, and a
count of findings from 10 to 19, 107 to 109 or 1008. For each pinned paragraph, the report of a
change names the paragraph and its line
range, gives its new sha256 and gives the 1-line update to PARAGRAPHS as the way to clear that
report alone, and a copy of the check with that 1 line updated passes the changed text. For each
pinned paragraph whose opening text is changed, the report is the line that the paragraph was
found 0 times, with no sha256; a copy of the check with only the paragraph's sha256 updated
still fails with that line, a copy with only the row's opening text rewritten fails with the
report that the paragraph has changed, and a copy with the row's opening text and sha256 both
rewritten passes. The check's findings give the same 3 verdicts for those 3 table states after
each 1-character edit of any opening text that changes more than its white space: each of its
characters, the trailing space of an opening text included, put in another case when it has
one, replaced by a character that is not white space, or removed, which joins 2 words when it
is the space between them; a character that is not white space put before each of its
characters; and a space put between 2 of its characters that are not white space. With a bare
"attended" or a second MODE line added to a pinned paragraph and only that paragraph's sha256
updated, the check fails with the report of that line and no report that the paragraph has
changed. Each pinned paragraph passes at the start of the file and at the end of the file with
no final line break, and with its last character removed fails at each of them. A mention of an
opening text inside another paragraph passes, and a third mode value named inside each pinned
paragraph fails with the report that each paragraph has changed and no report of a bare
"attended". The committed flow.md fails with each of these rule changes: Entry 62 put back
in the entry list of the whole-line rule, before, inside or after it, or between it and the
attribution to Entry 125, and the list's count made 5; the attribution to Entry 125 removed; the
whole-line test replaced; the found clause reverted to "on its cited line"; the range of a range
quote widened to 2 lines; the allowances made alternatives only; a quote of part of a line
allowed; the quote conditions bound to every leg; a checker for each family; a clause negated;
the tier floor replaced and in other words; the header naming 3 tier rules; the statement of the
tier rules kept here cut; the header and the tiers paragraph saying that only the CODEX ROLE
LIMIT states the floor; the floor reversed in cycle step 4; and every statement of the floor
removed from the header, from cycle step 4 and from the tiers paragraph, which states it twice.
The committed flow.md with 1 change each fails when its
MODE line names a third value, repeats a value, names a value with capital letters, drops either
value, uses a comma as the separator or puts its values inside double quotes, when the MODE line
names 5 values with no white space around their separators, whose report gives each value apart,
when the MODE line
is renamed so that none is left, when a second MODE line is added, closed or with no closing
parenthesis, when the MODE line loses its closing parenthesis, when a line holds an unquoted bare
"attended" in lower case, with a capital letter or inside typographic quotes, when such a line
comes after line 250, when a line holds a longer word that starts with "attended-autonomous",
such as "attended-autonomously", or "attended-autonomous" with a character of WORD_CHARACTERS
just after it, whose whole report gives that line, when a bare "attended" follows a closing
quote at once, as in
'un"stored"attended', since the check reads a quotation as a space and so does not join the text
on its 2 sides, when the absent-record sentence is removed, and when either wording of that
sentence has a word character just before its first word or just after its last. WORD_CHARACTERS
holds, for each Unicode category that holds a character that Python's re reads as a word
character, the first such character in ASCII and the first outside it, each where there is one.
It passes with the MODE values in
the other order, with each kind of white space that ends no line, alone and with every other
kind, at either end of each MODE value, with a parenthesis after the MODE line's closing
parenthesis, with a quoted "attended", with a quotation just after
"attended-autonomous", as
in 'attended-autonomous"x"ly', with a longer word that holds "attended", with each character of
WORD_CHARACTERS just before or just after "attended", with
"Attended-Autonomous" in capital letters outside the MODE line, and with the absent-record
sentence in its second wording, in capital letters, or wrapped across a line break. A byte order
mark before a line that would otherwise be a second MODE line passes on standard input, through
a path and through the default path. A path that
does not exist gives exit status 1 and as its whole output the 1 line that it cannot be read,
which names the path and gives the error that Python gives for reading it, through a path and
through the default path; an empty argument gives the same through a path, naming the empty path
and giving the error that Python gives for reading the current folder, so it is never read as the
default path; text that is not UTF-8 gives the same on standard input, through a path
and through the default path, with the error that Python gives for decoding it; a folder, a path
through a file, a symbolic link to itself, a name too long and a file with no read permission
each give the same through a path and through the default path, with the error that Python gives
for reading it, the last skipped for an account that can read it all the same; a descriptor open
only for writing and a closed standard input each give the same on standard input; and 2 or 3
arguments, the path of flow.md or "-" among them, give exit status 1 and as the whole output the
usage line. A file whose name holds a byte that is not UTF-8, and a file whose name holds every
kind of white space that ends no line inside it and at its end, each give, through a path and
through the default path, of a copy of the check in a folder whose name holds the same bytes, the
pass line, a finding and the line that the file cannot be read, each naming the file by the
bytes of its name, under the inherited locale, under C, POSIX, C.UTF-8 and en_US.UTF-8, and with
a sys.stdout that writes only ASCII, which stands in for a locale whose encoding lacks a
character that the output holds; with that sys.stdout, the 3 texts
that give every kind of report line give their whole output on standard input. Output that
cannot be written whole, to a closed standard output, a standard output open only for reading, a
pipe whose reading end is closed or a full device, gives exit status 1 and nothing on standard
error for the usage line, the line that the text cannot be read, a failure and a pass, the full
device skipped where the system has no /dev/full. A folder as standard input or standard output
stops Python before the check runs, with exit status 1, nothing on standard output and Python's
fatal error on standard error, a folder as standard error does the same with nothing on
standard output, and the check's docstring states that exception.

The residual cases hold the limits that the check's docstring states: outside the 7 pinned
paragraphs, the line '- A third mode, supervised, is also read.' passes, and the line
'- A third mode, attended-only, is also read.', which holds a bare "attended", fails; a paragraph
there that starts with the opening text of a pinned paragraph fails with that paragraph found 2
times; an indented line that starts "- MODE (" after its indent, and a line that starts with
each shorter part of "- MODE (" and then another character, are not counted and pass, a retired
default inside straight double quotes passes, a sentence that contradicts the
absent rule passes, the matched absent-rule sentence negated passes, the absent-rule sentence
inside a quotation that rejects it passes, the absent rule in other words fails, an ordinary
English use of "attended" fails, a quoted "attended" whose quotes wrap across a line break
fails, and a bare "attended" passes on a line that closes a quotation wrapped from the line above
when it stands between that closing quote and the next opening quote. Text outside the 7 pinned
paragraphs is not pinned: an edit of the keep-ahead buffer paragraph passes, and so does a
paragraph elsewhere that adds Entry 62 to the entries of the whole-line rule. The other ways in
which an edit there fails, a MODE line added or changed, the absent-record sentence removed, a
pinned paragraph joined to the text beside it and text that is not UTF-8, each have a verdict
case above. No case writes more than 1000 MODE lines, 1006 paragraphs that start with an opening
text or 1008 findings, or a line number of more than 6 digits, so no verdict case fails on a
check that bounded a count or a line number above those numbers; the code digest of the registry
case below fails on that change of code until CODE_SHA256 is updated, and the check's docstring
states this limit.

The registry cases hold the sites of the check that the cases above drive.
test_every_site_has_a_driver compares a digest of the check's code with CODE_SHA256. The digest
is the sha256 of the syntax tree that the check's bytes parse to, without its docstrings and the
sha256 values of PARAGRAPHS, unparsed, and unparsing leaves out the line and column positions
that the tree holds. So a change to that unparsed tree fails until the digest is updated; the
update in the diff is the reviewer's cue to check the registries. An edit that leaves the
unparsed tree as it is changes the check's bytes but keeps the digest, so the CODE_SHA256 pin
does not fail on it. An edit of a comment, of layout, of the quotes of a string, of how a number
is written or of parentheses that change no grouping can leave that tree as it is, and each of
those kinds of edit can also change it. The edits that change it form a class, and these are
examples of it, not a complete list: such an edit can change it inside the = field of an
f-string or inside an interpolation of a template string;
parentheses put around the name that an annotated assignment targets, or around the targets of
a del, can change it; an edit of an encoding declaration, which is a comment, can change it when
a string in the source is not ASCII; and re-indenting a block that holds a string written over
more than 1 line can change it. The digest's value depends on how
the Python that runs the test unparses a syntax tree. The case also requires
the codec of the encoding that tokenize.detect_encoding finds for those bytes to be UTF-8, with
or without a byte order mark. When Python runs a file, it reads the line
that holds an encoding declaration, and any line before it, before it applies the declaration,
while compile() of the bytes applies it to every line, so under a declaration of another encoding
the code that Python runs can differ from the tree that the digest holds; under UTF-8 Python
decodes the file that it runs as compile() decodes the bytes. Python reads a carriage return and
line feed pair, and any other carriage return, as a line feed, both when it looks for that
declaration and when it parses, so the case reads the bytes with those line ends made line feeds
to find the encoding and to apply the rows below. Each of MUTATIONS, a single textual replacement
of the check's source, must change the digest, and each of PRESERVED, the module docstring or a
function docstring reworded, a comment reworded, a sha256 of PARAGRAPHS updated, a blank line
added, the quotes of a string changed, a number written in hexadecimal and parentheses that
change no grouping added, must keep it; a row of either that edits a sha256 of PARAGRAPHS is
tried on each sha256 that the check's PARAGRAPHS holds, and on no other value. MUTATIONS holds,
among its rows, a comparison operator changed, the name __name__ changed and the upper bound of
a slice changed, and, for each of the 7 rows of PARAGRAPHS that NAMED lists, 1 row that puts a
full stop at the end of its name, 1 that changes the case of the first letter of its name, 1
that puts a full stop at the end of its opening text, 1 that puts a space at the end of its
opening text, 1 that doubles the first space inside its opening text and 1 that deletes that
space, and, for each opening text that ends with a space, 1 row that deletes that space.
FORM_PAIRS holds pairs of sources in forms that the check does not hold. Each pair tries a
condition of code_form() that the check's own source does not. The only statement of each source
of the pair of 2 keyword arguments of a call swapped is an expression that is a call, so the pair
tries the condition isinstance(first.value, ast.Constant) of code_form() on a module: a
code_form() that removes the first statement of a module whenever it is an expression fails it.
The pair also tries that code_form() keeps apart 2 sources that differ only in the order of 2
keyword arguments of a call, so a code_form() that sorts them fails it. code_form()
must make 2 sources equal that differ only in the docstring of a class or of an async function,
in a function of its docstring alone against one of pass alone, or in an empty module against a
blank line, and keep apart 2 that differ only in a string first in the body of an if, a for, a
while, a with or a try, in a number, a call, bytes, an assignment of a string or a return of a
string first in a function, in a string after the docstring of a function, in the order of 2
keyword arguments of a call, in a sha256 that is the third item of a row in a form that
code_form() must not rewrite, a row of a PARAGRAPHS bound together with a second name, bound by
an annotated assignment, bound to a tuple or bound inside a function, a row of a list bound to
an attribute named PARAGRAPHS, to another name or to a longer name that starts with PARAGRAPHS,
a row that is a list or a row of 4 items, or in a third item of a row of PARAGRAPHS that is a
name, a number, or 63 or 65 hexadecimal digits. So a code_form() that
fails 1 of those rows fails the case. Each row is evidence for its own edit only: a code_form()
that hides or keeps only what no row edits passes, such as one that also removes a string first
in the body of an except clause or of an async for. The same case finds, in the
check's syntax tree, 4 sets of sites, each site keyed by its function's name, its ordinal there
among the sites of the same form and its form, never by line number, the form of a call being the
whole call with its arguments: the calls that strip, split or substitute text, with each other
use of WHITE_SPACE and LINE_END; the report lines that findings appends and that outcome returns;
the arguments formatted into the output that are not text, which are counts and line numbers; and
the calls inside outcome's try and each call that reads. It also finds the names to which the
check binds a compiled regular expression at its top level, which PATTERN_SITES lists. Each
registry equals the sites of the forms that its extractor lists, and the case names each site
that is unregistered or missing. A site of another form is caught by the code digest, not by a
registry. Each registry entry names a case, and each entry of the 4 sets also names a domain, 1
of WHITE, INLINE_WHITE, OUTPUT_KINDS, READS, NAME_KINDS, TIMES, LEADS and PASS. A driver's code,
through the helpers and constants that it names, names its domain constant and launch() or the
check's findings. This does not show that it runs them, that it tries each value of the domain,
or that it would fail on a change at its site. The report lines name each of the 11 kinds of
OUTPUT_KINDS once, and the read routes name each of the 3 reads of READS. The reads of each route
are those that its branch of outcome's try gives, standard input for the branch taken on "-" and
a path and the default path for the other, and its driver names each of those reads as an item
of READS. Every run that the test makes through launch() fails on any byte on standard error.
The pin shows only that the check's code is the code last reviewed against the registries:
whether each registered case would fail on a change of meaning at its site, every input that no
case writes, and the environments that the test does not create rest on review and on mutants
run by hand, not on any assertion of this test. The code does not bound counts or line numbers,
and the test holds their values only as far as the cases above write them.
test_each_kind_of_output_names_each_kind_of_name is a
coverage counter of the cross product of OUTPUT_KINDS and NAME_KINDS: for "-" on standard input,
and for SPACED_NAME and UNDECODED_NAME through a path and through the default path, it compares
the whole output of the 3 texts of failing_texts(), the committed flow.md, text that cannot be
read and 2 arguments, counts the cell of each line's kind and that kind of name, and fails when a
cell of the 33 is not counted. test_white_space_of_each_kind_inside_each_row_opening_text_passes
calls the check's findings with each character of WHITE in place of the first space of each row's
opening text, and each such row still finds its paragraph unchanged.

Usage: python3 -I tools/test-check-flow-mode.py
Exit 0 when every case passes; 1 otherwise.
"""
import ast
import codecs
import errno
import hashlib
import importlib.util
import io
import os
import py_compile
import re
import subprocess
import sys
import tempfile
import tokenize
import types
import unicodedata
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK = ROOT / "tools" / "check-flow-mode.py"
FLOW = ROOT / ".claude" / "commands" / "flow.md"

MODE_LINE = "- MODE (attended-autonomous | unattended)"
ABSENT_WORDS = "reads an absent mode record as unattended"
# A new bullet goes before this one, so it lands in the mode section and away from the MODE line.
DECISIONS = "- DECISIONS: "

# The lines of .claude/commands/flow.md at main ee6be48 that the check reports, copied with the
# lines that open their items: cycle step 5, the first 2 lines of cycle step 8, the MODE bullet and
# the first line of the DECISIONS bullet. That file has no absent-record sentence either, so the
# mode tests report here what they report on the whole file; the copied lines hold none of the 7
# pinned paragraphs, so the check also reports each of those.
MAIN_MODE_TEXT = """\
5. AUTHORIZE within the standing grant. Not covered: attended -> surface a work-naming go, hold THIS
   item, and continue other independent queued work (a question never halts independent work);
   unattended -> DEFER (propose a ?HOLD on the affected STEP, route to the next independent item), never
   self-grant, never self-author a block.
8. PAUSE (after a merge, after a plan is verified pre-implementation, or when the queue composition
   changed): refresh; if an attended boundary is open, surface accumulated decisions, up to 4
- MODE (attended | unattended) parameterizes the question policy/timer/routing; it GRANTS NO authority.
  Absent = attended (conservative). The ONE governed transition is a decision-timeout switching
  attended -> unattended (the safe/conservative direction only). An inbound operator message is a
  TRANSIENT attended boundary and does NOT silently flip the mode.
- DECISIONS: blocking + attended -> surface immediately, up to 4 per round, in the four-role shape.
"""

WRONG_MODES = "the MODE line names"
BARE = "unquoted bare \"attended\""
UNCLOSED = "the MODE line has no closing parenthesis"
NO_ABSENT = "no statement that an absent mode record is read as unattended"
CHANGED = "{}, a pinned paragraph, has changed: its sha256 is now "
NOT_ONCE = "expected 1 pinned paragraph, {}, starting {!r}, found {}"
PINS_PRESENT = "the 7 pinned paragraphs are unchanged"
# The whole output of a pass, written out here with the name of the text read, so that a check
# whose pass line names another file or another count fails.
PASS = ("OK: {}: the MODE line names the writer's 2 modes, no line holds an unquoted bare"
        " \"attended\", the absent-record sentence is present, and the 7 pinned paragraphs are"
        " unchanged\n")
MODE_COUNT = "expected 1 MODE line starting \"- MODE (\", found {}"
SECOND_MODE = MODE_COUNT.format(2)
NO_MODE = MODE_COUNT.format(0)
UNREADABLE = "cannot be read: "
# The whole output when more than 1 argument is given.
USAGE = "usage: python3 -I tools/check-flow-mode.py [PATH]\n"
ABSENT_ATTENDED = "- Absent = attended (conservative)."
# The numbers of MODE lines that the case of each number found writes: each from 2 to 11, so that
# the count runs from 1 digit to 2, and 99, 100, 101 and 1000, so that it runs to 3 and 4 digits.
TIMES = list(range(2, 12)) + [99, 100, 101, 1000]
# The numbers of blank lines put before each of the 3 texts of the case that compares the 3 reads:
# none, and 99999, so that each line number and line range that the check reports has 6 digits.
LEADS = [0, 99999]
# The report line for a changed paragraph, written out here with the name of the text read, so
# that a check whose report drops any part of it, names another file, or gives a 1-line update
# that does not match its table, fails.
REPORT = ("FAIL: {}:{}-{}: {}, a pinned paragraph, has changed: its sha256 is now {}; to clear this"
          " report alone, replace the line '     \"{}\"),' of PARAGRAPHS in"
          " tools/check-flow-mode.py with '     \"{}\"),'")
DIGEST_LINE = "     \"{}\"),"
ENTRIES = "Entries 61, 63, 64 and 69"

# The 7 pinned paragraphs, by the name the check's report gives each and the text it starts with.
NAMED = [
    ("the header", "INTERIM. This command's own inlined text"),
    ("the cycle steps", "1. REFRESH: "),
    ("the seeding paragraph", "Per item (the machine-local"),
    ("FAILED LEG", "FAILED LEG (every family, every tier):"),
    ("the CODEX ROLE LIMIT", "CODEX ROLE LIMIT: "),
    ("the tiers paragraph", "The tiers (light, substantive, and sensitive)"),
    ("VERIFIER DIVERSITY", "VERIFIER DIVERSITY (QA, every tier):"),
]
BLANK_LINE = re.compile(r"\n[^\S\n]*\n")

# Kinds of white space that may stand between 2 words of a pinned paragraph, each by name.
SPACES = [
    ("a line break and an indent", "\n   "),
    ("a carriage return and a line break", "\r\n"),
    ("a tab", "\t"),
    ("a no-break space", chr(0x00A0)),
    ("an em space", chr(0x2003)),
    ("an ideographic space", chr(0x3000)),
    ("a unit separator", chr(0x001F)),
    ("a line separator", chr(0x2028)),
    ("a doubled space", "  "),
]
# Every character that str.isspace() counts as white space, and those of them that end no line.
WHITE = [chr(code) for code in range(sys.maxunicode + 1) if chr(code).isspace()]
INLINE_WHITE = [space for space in WHITE if space not in "\n\r"]


def word_characters():
    """For each Unicode category that holds a character that Python's re reads as a word
    character, the first such character in ASCII and the first outside it, each where there is
    one, in order of code point: characters that may stand next to "attended" in a word that is
    not bare."""
    chosen = {}
    for code in range(sys.maxunicode + 1):
        char = chr(code)
        if re.fullmatch(r"\w", char):
            chosen.setdefault((unicodedata.category(char), char.isascii()), char)
    return sorted(set(chosen.values()))


WORD_CHARACTERS = word_characters()
# Every kind of white space that ends no line, run together, put at the ends of the lines and of
# the MODE values whose white space at either end the check's reports remove: a check that
# removes only some kinds leaves a kind that it misses in its report.
PADDING = "".join(INLINE_WHITE)
# Text that holds every kind of white space that ends no line between 2 of its words or letters,
# which the reports that quote it must keep: a check that collapses or removes white space inside
# the text that a report quotes changes it. The third MODE value, the line that holds a bare
# "attended" and the second, unclosed MODE line of failing_texts(), and the name of the file that
# each case of a whole output reads through a path; that name also ends with that white space.
THIRD = "super" + PADDING + "vised"
BARE_LINE = "- Absent =" + PADDING + "attended (conservative)."
UNCLOSED_LINE = "- MODE (supervised" + PADDING + "is a third mode."
SPACED_NAME = "flow" + PADDING + ".md" + PADDING
# The file name that holds a byte that is not UTF-8, as bytes, which a report must give as that
# byte.
UNDECODED_NAME = b"flow-\xff.md"
# The 3 reads of the text that the check makes, by the name each case gives it.
READS = ["standard input", "path", "default path"]
# The 3 kinds of name that the check gives the text read: "-" for standard input, and the 2 file
# names that a path and the default path name.
NAME_KINDS = ["-", SPACED_NAME, UNDECODED_NAME]
# The 11 kinds of line that the check writes: the 7 kinds of finding, the count of findings, the
# usage line, the line that the text cannot be read and the pass line.
OUTPUT_KINDS = ["MODE lines found", "MODE line unclosed", "MODE values", "bare attended",
                "absent-record sentence missing", "pinned paragraph not found once",
                "pinned paragraph changed", "count of findings", "usage", "cannot be read", "pass"]
# The locales under which the check must name a file by the bytes of its name: None keeps the
# inherited locale. Under en_US.UTF-8, where it is installed, Python's standard output fails on a
# path name that is not UTF-8; where it is not, Python falls back as it does under C.
LOCALES = [None, "C", "POSIX", "C.UTF-8", "en_US.UTF-8"]
# A run of the check in which sys.stdout writes only ASCII and fails on any other character, as
# Python's standard output does under a locale whose encoding lacks a character that the output
# holds, whatever locales the system has: a check that wrote through sys.stdout fails on any
# character outside ASCII, while a check that writes its UTF-8 bytes itself does not.
ASCII_STDOUT = ("import io, runpy, sys; sys.stdout = io.TextIOWrapper("
                "io.FileIO(1, 'w', closefd=False), encoding='ascii', errors='strict',"
                " line_buffering=True); check = sys.argv[1]; sys.argv = sys.argv[1:];"
                " runpy.run_path(check, run_name='__main__')")

# Rule changes in the pinned paragraphs, each as the paragraph it is in, a text that flow.md
# holds once, and its replacement.
RULE_CHANGES = [
    ("FAILED LEG", ENTRIES, "Entries 61, 62, 63, 64 and 69"),
    ("FAILED LEG", ENTRIES, "Entries 62, 61, 63, 64 and 69"),
    ("FAILED LEG", ENTRIES, "Entries 61, 63, 64 and 69 and of Entry 62"),
    ("FAILED LEG", ENTRIES, "Entries 61, 63, 64, 69 and 62"),
    ("FAILED LEG", ENTRIES, "Entries 61, 63, 64 and 69, 62"),
    ("FAILED LEG", "as these 4):", "as these 4) and Entry 62:"),
    ("FAILED LEG", "as these 4):", "as these 5):"),
    ("FAILED LEG", "Entry 125 states, the rule", "Entry 125 states, the rule of Entry 62 and the rule"),
    ("FAILED LEG", "the whole-line rule that Entry 125 states,", "the whole-line rule,"),
    ("FAILED LEG", "must be a whole line, from the line's first character to its last",
     "must be found within 1 line"),
    ("FAILED LEG", "is the whole of its cited line", "is on its cited line"),
    ("FAILED LEG", "within 1 line of the cited range", "within 2 lines of the cited range"),
    ("FAILED LEG", "only once either or both of 2 allowances apply",
     "only once each of 2 allowances applies alone"),
    ("FAILED LEG", "a quote of only part of a line, text", "text"),
    ("FAILED LEG", "conditions bind review legs only", "conditions bind every leg"),
    ("FAILED LEG", "and 1 checker applies it", "and a checker for each family applies it"),
    ("FAILED LEG", "(2) a quote in it is absent", "(2) it is false that a quote in it is absent"),
    ("the CODEX ROLE LIMIT", "A critical change is never graded light:",
     "A critical change may be graded light:"),
    ("the CODEX ROLE LIMIT", "A critical change is never graded light:",
     "A critical change is never given the light tier:"),
    ("the header", "governs, apart from the 2", "governs, apart from the 3"),
    ("the header", "HOLD; that section and the CODEX ROLE LIMIT below both state",
     "HOLD; the CODEX ROLE LIMIT below states"),
    ("the cycle steps", "which never grades a critical", "which may grade a critical"),
    ("the tiers paragraph",
     "escalation is immediate and de-escalation needs a maintainer decision and a",
     "escalation is immediate and de-escalation needs a"),
    ("the tiers paragraph", "The CODEX ROLE LIMIT and that section both state the",
     "The CODEX ROLE LIMIT states the"),
]

# The floor that a critical change is never graded light, removed from each of the 3 pinned
# paragraphs outside the CODEX ROLE LIMIT that state it, each as the paragraph and the changes,
# applied in turn, that remove every statement of the floor in it.
FLOOR_REMOVALS = [
    ("the header", [("HOLD; that section and the CODEX ROLE LIMIT below both state the floor that"
                     " a critical change is\nnever graded light; and except", "HOLD; and except")]),
    ("the cycle steps", [("section, which never grades a critical\n   change light, the same floor"
                          " as the CODEX ROLE LIMIT below. Record", "section. Record")]),
    ("the tiers paragraph", [
        (" bars a light grade for it\n(the same floor as that section's),", ""),
        (" The CODEX ROLE LIMIT and that section both state the\nfloor that a critical change is"
         " never graded light.", "")]),
]


def launch(args, check=CHECK, ascii_stdout=False, env=None, **streams):
    """The finished run of the check with args, each a str or bytes, with the standard streams
    that streams give, under env, and through ASCII_STDOUT when ascii_stdout is set. The check
    writes nothing to standard error, so a run that writes anything there fails the case that
    made it."""
    wrapper = ["-c", ASCII_STDOUT] if ascii_stdout else []
    run = subprocess.run([sys.executable, "-I"] + wrapper + [str(check)] + args,
                         stderr=subprocess.PIPE, timeout=60, check=False, env=env, **streams)
    if run.stderr:
        raise AssertionError("expected nothing on standard error, found {!r}".format(
            run.stderr.decode("utf-8", "replace")))
    return run


def run_check(args, data=b"", check=CHECK, stdin=None, closed=False):
    """The exit status of the check run with args, and its output, which is its standard output
    alone. Its standard input is data, or the file descriptor stdin when one is given, or none at
    all when closed is set."""
    if closed:
        source = {"stdin": subprocess.DEVNULL, "preexec_fn": lambda: os.close(0)}
    else:
        source = {"input": data} if stdin is None else {"stdin": stdin}
    run = launch(args, check, stdout=subprocess.PIPE, **source)
    return run.returncode, run.stdout.decode("utf-8", "replace")


def verdict(text, check=CHECK):
    """The exit status of the check run on text, and its output."""
    return run_check(["-"], text.encode("utf-8"), check)


def committed():
    """The committed flow.md."""
    return FLOW.read_text(encoding="utf-8")


def changed(old, new):
    """The committed flow.md with its one occurrence of old replaced by new."""
    text = committed()
    if text.count(old) != 1:
        raise AssertionError("expected 1 {!r} in {}, found {}".format(old, FLOW, text.count(old)))
    return text.replace(old, new)


def added(line):
    """The committed flow.md with line added as a bullet just before the DECISIONS bullet."""
    return changed(DECISIONS, line + "\n" + DECISIONS)


def replaced(text, old, new):
    """text with its one occurrence of old replaced by new."""
    if text.count(old) != 1:
        raise AssertionError("expected 1 {!r}, found {}".format(old, text.count(old)))
    return text.replace(old, new)


def span(text, opening):
    """The start and end offsets in text of the 1 paragraph that starts a line with opening and
    ends before the next blank line or at the end of text."""
    if text.count("\n" + opening) != 1:
        raise AssertionError("expected 1 line starting {!r} in {}".format(opening, FLOW))
    start = text.index("\n" + opening) + 1
    blank = BLANK_LINE.search(text, start)
    return start, blank.start() if blank else len(text)


def line_range(text, opening):
    """The first and last line numbers in text of the paragraph that starts with opening."""
    start, end = span(text, opening)
    return text.count("\n", 0, start) + 1, text.count("\n", 0, end) + 1


def line_of(text, fragment):
    """The number of the 1 line of text, split at line feeds, that holds fragment, and that line
    with the white space at either end removed."""
    lines = text.split("\n")
    numbers = [number for number, line in enumerate(lines, 1) if fragment in line]
    if len(numbers) != 1:
        raise AssertionError("expected 1 line holding {!r}, found {}".format(fragment, len(numbers)))
    return numbers[0], lines[numbers[0] - 1].strip()


def with_paragraph(opening, change):
    """The committed flow.md with the paragraph that starts with opening replaced by change of
    it."""
    text = committed()
    start, end = span(text, opening)
    return text[:start] + change(text[start:end]) + text[end:]


def with_paragraphs(change):
    """The committed flow.md with each of the 7 pinned paragraphs replaced by change of it and its
    opening text."""
    text = committed()
    spans = sorted((span(text, opening), opening) for _, opening in NAMED)
    parts = []
    done = 0
    for (start, end), opening in spans:
        parts += [text[done:start], change(text[start:end], opening)]
        done = end
    return "".join(parts) + text[done:]


def code_point(space):
    """The name of a character by its code point, such as U+00A0."""
    return "U+{:04X}".format(ord(space))


def own_digest(paragraph):
    """The sha256 of paragraph with each run of white space collapsed to 1 space, as this test
    computes it."""
    return hashlib.sha256(" ".join(paragraph.split()).encode("utf-8")).hexdigest()


def check_module(path=CHECK):
    """The check at path, tools/check-flow-mode.py by default, loaded as a module without running
    its main. It is compiled from the bytes of its source as they are now, so no bytecode cache,
    whose recorded size and time an edit can leave unchanged, stands in for that source."""
    module = types.ModuleType("check_flow_mode")
    module.__file__ = str(path)
    exec(compile(Path(path).read_bytes(), str(path), "exec"), module.__dict__)
    return module


def default_copy(folder, default):
    """A copy of the check in folder whose DEFAULT line alone is rewritten to name default, so
    that the copy run with no argument reads default, as CI runs the check."""
    source = CHECK.read_text(encoding="utf-8")
    copied, count = re.subn(r"(?m)^DEFAULT = .*$",
                            lambda match: "DEFAULT = Path({!r})".format(str(default)), source)
    if count != 1:
        raise AssertionError("expected 1 DEFAULT line in {}, found {}".format(CHECK, count))
    path = Path(folder) / "check-flow-mode.py"
    path.write_text(copied, encoding="utf-8")
    return path


def failing_text():
    """The committed flow.md with every test failed at once: a word appended to each pinned
    paragraph, a third value, THIRD, on the MODE line, with PADDING at either end of each value,
    which the report of those values leaves out while it keeps the white space inside THIRD, a
    bare "attended" added on BARE_LINE, and the absent-record sentence removed."""
    text = with_paragraphs(lambda p, o: p + " x")
    values = ["attended-autonomous", "unattended", THIRD]
    text = replaced(text, MODE_LINE, "- MODE ({})".format(
        "|".join(PADDING + value + PADDING for value in values)))
    text = replaced(text, ABSENT_WORDS, "reads the mode record")
    return replaced(text, DECISIONS, BARE_LINE + "\n" + DECISIONS)


def output(lines):
    """The whole output of a check that reports lines, each line ended by a line feed, and then
    the line with the number of findings."""
    return "".join(line + "\n" for line in lines + ["FAIL: {} finding(s)".format(len(lines))])


def failing_texts(lead=0):
    """Texts that between them give every kind of report line that the check's findings give,
    each with a function that gives, for the name of the text read, the whole output that the
    check must print, in its order, each report line with its counts and line numbers and the last
    line with the number of findings: failing_text(); the committed flow.md with the opening text
    of each pinned paragraph changed, its MODE line left unclosed and a second, unclosed MODE line,
    UNCLOSED_LINE, with PADDING at its end added, which the report of that line leaves out while
    it keeps the white space inside UNCLOSED_LINE; and the committed
    flow.md with each pinned paragraph repeated and its MODE line renamed so that none is left.
    Each text starts with lead blank lines, which move each line number and line range that the
    check reports for it down by lead. Each sha256 is the one this test computes, so the expected
    output owes nothing to the check."""
    text = committed()
    pinned = {opening: own_digest(text[slice(*span(text, opening))]) for _, opening in NAMED}
    failed = "\n" * lead + failing_text()
    bare, bare_line = line_of(failed, BARE_LINE)
    changes = []
    for name, opening in NAMED:
        first, last = line_range(failed, opening)
        now = own_digest(failed[slice(*span(failed, opening))])
        changes.append((first, last, name, now, pinned[opening], now))
    lost = with_paragraphs(lambda p, o: "x" + p[1:])
    lost = replaced(lost, MODE_LINE, MODE_LINE[:-1])
    lost = "\n" * lead + replaced(lost, DECISIONS, UNCLOSED_LINE + PADDING + "\n" + DECISIONS)
    unclosed = sorted([line_of(lost, MODE_LINE[:-1]), line_of(lost, UNCLOSED_LINE)])
    repeated = with_paragraphs(lambda p, o: p + "\n\n" + p)
    repeated = "\n" * lead + replaced(repeated, MODE_LINE, MODE_LINE.replace("MODE", "Mode"))

    return [
        ("every test failed", failed, lambda source: output(
            ["FAIL: {}: {} attended-autonomous | unattended | {}, not exactly"
             " attended-autonomous | unattended".format(source, WRONG_MODES, THIRD),
             "FAIL: {}:{}: {}: {}".format(source, bare, BARE, bare_line),
             "FAIL: {}: {}".format(source, NO_ABSENT)]
            + [REPORT.format(source, *change) for change in changes])),
        ("each opening text changed", lost, lambda source: output(
            ["FAIL: {}: {}".format(source, SECOND_MODE)]
            + ["FAIL: {}:{}: {}: {}".format(source, number, UNCLOSED, line)
               for number, line in unclosed]
            + ["FAIL: {}: {}".format(source, NOT_ONCE.format(name, opening, 0))
               for name, opening in NAMED])),
        ("each pinned paragraph repeated", repeated, lambda source: output(
            ["FAIL: {}: {}".format(source, NO_MODE)]
            + ["FAIL: {}: {}".format(source, NOT_ONCE.format(name, opening, 2))
               for name, opening in NAMED])),
    ]


def counted_text(times):
    """The committed flow.md with its MODE line written times times, the opening text of the
    pinned paragraph in row r of NAMED starting times + r paragraphs, the copies at the end of
    the file, and times lines that hold a bare "attended", each with PADDING at either end,
    after them, with a function that gives, for the name of the text read, the whole output that
    the check must print: the report of the number of MODE lines, the report of each bare
    "attended" with its line number and the line without that white space, the report of the
    number of paragraphs found for each pinned paragraph, and the count of times + 8 findings."""
    counts = {opening: times + row for row, (_, opening) in enumerate(NAMED)}
    text = replaced(committed(), DECISIONS,
                    (MODE_LINE + " is repeated.\n") * (times - 1) + DECISIONS)
    if not text.endswith("\n"):
        raise AssertionError("expected {} to end with a line feed".format(FLOW))
    copies = [opening + " is copied here."
              for _, opening in NAMED for _ in range(counts[opening] - 1)]
    text += ("\n" + "\n\n".join(copies) + "\n\n"
             + (PADDING + ABSENT_ATTENDED + PADDING + "\n") * times)
    lines = text.split("\n")
    bare = [number for number, line in enumerate(lines, 1) if line.strip() == ABSENT_ATTENDED]
    if len(bare) != times:
        raise AssertionError("expected {} lines {!r}, found {}".format(
            times, ABSENT_ATTENDED, len(bare)))
    return text, lambda source: output(
        ["FAIL: {}: {}".format(source, MODE_COUNT.format(times))]
        + ["FAIL: {}:{}: {}: {}".format(source, number, BARE, ABSENT_ATTENDED) for number in bare]
        + ["FAIL: {}: {}".format(source, NOT_ONCE.format(name, opening, counts[opening]))
           for name, opening in NAMED])


def read_error(read):
    """The text of the error that read raises, as Python gives it."""
    try:
        read()
    except (OSError, UnicodeDecodeError) as exc:
        return str(exc)
    raise AssertionError("expected the read to fail")


def other_characters(char):
    """The characters that may replace char in an edit that an opening text match must refuse:
    char in another case, when it has one, and a character that is neither char nor white space."""
    edits = [char.swapcase()] if len(char.swapcase()) == 1 and char.swapcase() != char else []
    return edits + ["#" if char != "#" else "%"]


def opening_edits(paragraph, opening):
    """Each 1-character edit of the opening text that paragraph starts with that changes more than
    the white space between its words, as a name and the edited opening text: each character
    replaced by one of other_characters or removed, a character that is not white space put
    before each character, and a space put before each character after the first where no white
    space stands on either side. Removing the 1 white-space character between 2 words joins
    them. A space put before the first character is an indent, which a case of its own covers,
    and no opening text starts with white space, so that edit is left out here."""
    if not paragraph.startswith(opening):
        raise AssertionError("expected a paragraph starting {!r}".format(opening))
    edits = []
    for index, char in enumerate(opening):
        for new in other_characters(char):
            edits.append(("{} replaced by {!r}".format(index, new),
                          opening[:index] + new + opening[index + 1:]))
        # The character after the opening text decides whether removing white space at its end
        # leaves white space there.
        if char.isspace() and (index == 0 or paragraph[index - 1].isspace()
                               or paragraph[index + 1].isspace()):
            raise AssertionError("expected 1 white-space character at {} of {!r}".format(
                index, opening))
        edits.append(("{} removed".format(index), opening[:index] + opening[index + 1:]))
        edits.append(("# put before {}".format(index), opening[:index] + "#" + opening[index:]))
        if index > 0 and not char.isspace() and not opening[index - 1].isspace():
            edits.append(("a space put before {}".format(index),
                          opening[:index] + " " + opening[index:]))
    return edits


def after(paragraph, opening, pattern):
    """The offset of the first match of pattern in paragraph after its opening text."""
    return re.compile(pattern).search(paragraph, len(opening)).start()


def space_at(paragraph, opening):
    """The offset of the first space between 2 words of paragraph after its opening text."""
    return after(paragraph, opening, r"\w \w") + 1


# The sha256 of code_form() of the check's bytes: the check's syntax tree, without its docstrings
# and the sha256 values of PARAGRAPHS, unparsed, which leaves out the line and column positions
# that the tree holds. test_every_site_has_a_driver compares that sha256 with this value, so a
# change to that unparsed tree fails until this line is updated; the update in the diff is the
# reviewer's cue to check the registries below against the new code. An edit that leaves the
# unparsed tree as it is keeps this value. An edit of a comment, of layout, of the quotes of a
# string, of how a number is written or of parentheses that change no grouping can leave that tree
# as it is, and each of those kinds of edit can also change it; the edits that change it form a
# class, and the docstring of code_form() names examples of it, not a complete list. The value
# depends on how the Python that runs the test unparses a syntax tree.
CODE_SHA256 = "bca3b3045e2fc6f5039f7baa0da7d0d3abcf371c5a82fd255bc68d4093dce27f"
# The value that code_form() puts in place of each sha256 of PARAGRAPHS that it leaves out. It is
# 64 lowercase hexadecimal digits, as each value that it replaces is. A constant that code_form()
# keeps can equal it, such as the third item of a row of a PARAGRAPHS that code_form() does not
# rewrite, or a constant elsewhere in the check; code_form() never compares a value with it.
PLACEHOLDER = "0" * 64
# The text that stands, in MUTATIONS and PRESERVED, for a sha256 of PARAGRAPHS. A row that holds
# it is tried once for each sha256 that paragraph_digests() reads from the check's PARAGRAPHS, and
# for no other value, so that an update of any of them leaves both lists as they are.
DIGEST = "<a sha256 of PARAGRAPHS>"
# The self-check of code_form(): single textual replacements on the check's source, with each
# carriage return and line feed pair and each other carriage return made a line feed, each of
# which must occur there exactly once. Each of MUTATIONS must change code_form()'s digest and
# each of PRESERVED must keep it, so a code_form() that keeps the digest for 1 of those mutations,
# or changes it for 1 of those edits, fails. Each row is evidence for its own edit only. 1 fixed
# row changes the name of the first row of PARAGRAPHS, the header, to the heading, an edit of
# letters after its first. The other rows that edit the name or the opening text of a row of
# PARAGRAPHS are built from NAMED, 6 for each of its 7 rows: a full stop put at the end of its
# name, the case of the first letter of its name changed, a full stop put at the end of its
# opening text, a space put at the end of its opening text, the first space inside its opening
# text doubled and that space deleted; and 1 more for each opening text that ends with a space:
# that space deleted.
MUTATIONS = [
    ("a match capture cuts the text before it is split", "    lines = LINE_END.split(text)\n",
     "    match text[:8000000]:\n        case text:\n            pass\n"
     "    lines = LINE_END.split(text)\n"),
    ("a match capture rewrites the source before it is read",
     "    source = argv[0] if argv else str(DEFAULT)\n",
     "    source = argv[0] if argv else str(DEFAULT)\n"
     "    match \"-\" if source == \"--\" else source:\n        case source:\n            pass\n"),
    ("sys.exit given a string for 4 arguments", "    sys.exit(main(sys.argv[1:]))",
     "    sys.exit(main(sys.argv[1:]) if len(sys.argv) < 5 else \"usage\")"),
    ("os imported under another name", "            data = data[os.write(1, data):]",
     "            import os as _os\n            data = data[_os.write(1, data):]"),
    ("stderr imported from sys", "    status, lines = outcome(argv)\n",
     "    from sys import stderr\n    stderr.write(\"\")\n    status, lines = outcome(argv)\n"),
    ("str.replace before the line split", "    lines = LINE_END.split(text)",
     "    lines = LINE_END.split(text.replace(\"\\u2029\", \" \"))"),
    ("a condition rewritten", "    if len(argv) > 1:", "    if len(argv) >= 2:"),
    ("a module constant made a tuple", "WRITER_VALUES = [\"attended-autonomous\", \"unattended\"]",
     "WRITER_VALUES = (\"attended-autonomous\", \"unattended\")"),
    ("a module constant shortened", "MODE_PREFIX = \"- MODE (\"", "MODE_PREFIX = \"- MODE\""),
    ("a sink reached through getattr", "    return status if write(lines) else 1",
     "    getattr(sys, \"stderr\").write(\"\")\n    return status if write(lines) else 1"),
    ("a sha256 of PARAGRAPHS replaced by an expression of the same value",
     "\"" + DIGEST + "\"", "\"" + DIGEST + "\"[:64]"),
    ("a sha256 of PARAGRAPHS replaced by 64 hexadecimal digits that are not lower case",
     "\"" + DIGEST + "\"", "\"" + "F" * 64 + "\""),
    ("a text inside a function changed", "[PATH]\"]", "[FILE]\"]"),
    ("the name of a row of PARAGRAPHS changed", "(\"the header\", ", "(\"the heading\", "),
    ("a comparison operator changed", "    if len(modes) != 1:", "    if len(modes) > 1:"),
    ("a name that starts with an underscore changed", "if __name__ ==", "if __file__ =="),
    ("the upper bound of a slice changed", "lines[start - 1:number - 1]",
     "lines[start - 1:number]"),
] + [("the name of {} changed, a row of PARAGRAPHS".format(name), "(\"{}\", ".format(name),
      "(\"{}.\", ".format(name)) for name, _ in NAMED] + [
    ("the case of the first letter of the name of {} changed, a row of PARAGRAPHS".format(name),
     "(\"{}\", ".format(name), "(\"{}\", ".format(name[0].swapcase() + name[1:]))
    for name, _ in NAMED] + [
    ("the opening text of {} changed, a row of PARAGRAPHS".format(name), "\"{}\"".format(opening),
     "\"{}.\"".format(opening)) for name, opening in NAMED] + [
    ("a space put at the end of the opening text of {}, a row of PARAGRAPHS".format(name),
     "\"{}\"".format(opening), "\"{} \"".format(opening)) for name, opening in NAMED] + [
    ("the first space inside the opening text of {} doubled, a row of PARAGRAPHS".format(name),
     "\"{}\"".format(opening), "\"{}\"".format(opening.replace(" ", "  ", 1)))
    for name, opening in NAMED] + [
    ("the first space inside the opening text of {} deleted, a row of PARAGRAPHS".format(name),
     "\"{}\"".format(opening), "\"{}\"".format(opening.replace(" ", "", 1)))
    for name, opening in NAMED] + [
    ("the space at the end of the opening text of {} deleted, a row of PARAGRAPHS".format(name),
     "\"{}\"".format(opening), "\"{}\"".format(opening[:-1]))
    for name, opening in NAMED if opening.endswith(" ")]
PRESERVED = [
    ("the module docstring reworded", "#!/usr/bin/env python3\n\"\"\"",
     "#!/usr/bin/env python3\n\"\"\"Reworded. "),
    ("a function docstring reworded", "def paragraphs(lines):\n    \"\"\"",
     "def paragraphs(lines):\n    \"\"\"Reworded. "),
    ("a comment reworded", "# The 2 values orch-set-mode writes,",
     "# The values that orch-set-mode writes,"),
    ("a sha256 of PARAGRAPHS updated, as the check's own report asks",
     "\"" + DIGEST + "\"", "\"" + "f" * 64 + "\""),
    ("a blank line added", "\n\n\ndef digest(paragraph):", "\n\n\n\ndef digest(paragraph):"),
    ("the quotes of a string changed", "\" \".join(paragraph.split())",
     "' '.join(paragraph.split())"),
    ("a number written in hexadecimal", "        return 1, [\"usage",
     "        return 0x1, [\"usage"),
    ("parentheses that change no grouping added", "    found = findings(text, source)",
     "    found = (findings(text, source))"),
]
# The self-check of code_form() on forms that the check does not hold, so that no replacement of
# its source can try them. Each pair tries a condition of code_form() that the check's own source
# does not. The only statement of each source of the pair of 2 keyword arguments of a call
# swapped is an expression that is a call, so the pair tries the condition
# isinstance(first.value, ast.Constant) of code_form() on a module: a code_form() that removes
# the first statement of a module whenever it is an expression fails it. The pair also tries
# that code_form() keeps apart 2 sources that differ only in the order of 2 keyword arguments of
# a call, so a code_form() that sorts them fails it. True marks a pair that code_form() must make
# equal: its 2 sources differ only in a docstring, in a body of a docstring alone against a body
# of pass alone, or in a blank line.
# False marks a pair that it must keep apart: its 2 sources differ only in a part that is
# neither a docstring nor a sha256 of PARAGRAPHS, which is a constant of 64 lowercase hexadecimal
# digits that is the third item of a 3-item tuple row of the list that an assignment at the top
# level, without an annotation, binds to the name PARAGRAPHS alone.
FORM_PAIRS = [
    ("a class docstring reworded", b"class Note:\n    \"\"\"A.\"\"\"\n",
     b"class Note:\n    \"\"\"B.\"\"\"\n", True),
    ("an async function docstring reworded", b"async def note():\n    \"\"\"A.\"\"\"\n",
     b"async def note():\n    \"\"\"B.\"\"\"\n", True),
    ("a function of its docstring alone and a function of pass alone",
     b"def note():\n    \"\"\"A.\"\"\"\n", b"def note():\n    pass\n", True),
    ("an empty module and a module of a blank line", b"", b"\n", True),
    ("a string first in the body of an if changed", b"if note:\n    \"A.\"\n",
     b"if note:\n    \"B.\"\n", False),
    ("a string first in the body of a for changed", b"for note in notes:\n    \"A.\"\n",
     b"for note in notes:\n    \"B.\"\n", False),
    ("a string first in the body of a while changed", b"while note:\n    \"A.\"\n",
     b"while note:\n    \"B.\"\n", False),
    ("a string first in the body of a with changed", b"with note:\n    \"A.\"\n",
     b"with note:\n    \"B.\"\n", False),
    ("a string first in the body of a try changed", b"try:\n    \"A.\"\nfinally:\n    pass\n",
     b"try:\n    \"B.\"\nfinally:\n    pass\n", False),
    ("a number first in a function changed", b"def note():\n    1\n", b"def note():\n    2\n",
     False),
    ("a call first in a function changed", b"def note():\n    note()\n",
     b"def note():\n    note(1)\n", False),
    ("bytes first in a function changed", b"def note():\n    b\"A.\"\n",
     b"def note():\n    b\"B.\"\n", False),
    ("an assignment of a string first in a function changed", b"def note():\n    x = \"A.\"\n",
     b"def note():\n    x = \"B.\"\n", False),
    ("a return of a string first in a function changed", b"def note():\n    return \"A.\"\n",
     b"def note():\n    return \"B.\"\n", False),
    ("a string after the docstring of a function changed",
     b"def note():\n    \"\"\"A.\"\"\"\n    \"B.\"\n",
     b"def note():\n    \"\"\"A.\"\"\"\n    \"C.\"\n", False),
    ("2 keyword arguments of a call swapped", b"note(one=first(), two=second())\n",
     b"note(two=second(), one=first())\n", False),
    ("a sha256 of a PARAGRAPHS bound together with a second name changed",
     b"PARAGRAPHS = TABLE = [(\"a\", \"b\", \"" + b"1" * 64 + b"\")]\n",
     b"PARAGRAPHS = TABLE = [(\"a\", \"b\", \"" + b"2" * 64 + b"\")]\n", False),
    ("a sha256 of a PARAGRAPHS bound to a tuple changed",
     b"PARAGRAPHS = ((\"a\", \"b\", \"" + b"1" * 64 + b"\"),)\n",
     b"PARAGRAPHS = ((\"a\", \"b\", \"" + b"2" * 64 + b"\"),)\n", False),
    ("a sha256 of a PARAGRAPHS bound inside a function changed",
     b"def note():\n    PARAGRAPHS = [(\"a\", \"b\", \"" + b"1" * 64 + b"\")]\n",
     b"def note():\n    PARAGRAPHS = [(\"a\", \"b\", \"" + b"2" * 64 + b"\")]\n", False),
    ("a sha256 of a PARAGRAPHS bound by an annotated assignment changed",
     b"PARAGRAPHS: list = [(\"a\", \"b\", \"" + b"1" * 64 + b"\")]\n",
     b"PARAGRAPHS: list = [(\"a\", \"b\", \"" + b"2" * 64 + b"\")]\n", False),
    ("a sha256 of a list bound to an attribute named PARAGRAPHS changed",
     b"note.PARAGRAPHS = [(\"a\", \"b\", \"" + b"1" * 64 + b"\")]\n",
     b"note.PARAGRAPHS = [(\"a\", \"b\", \"" + b"2" * 64 + b"\")]\n", False),
    ("a sha256 of a list bound to another name changed",
     b"TABLE = [(\"a\", \"b\", \"" + b"1" * 64 + b"\")]\n",
     b"TABLE = [(\"a\", \"b\", \"" + b"2" * 64 + b"\")]\n", False),
    ("a sha256 of a list bound to a longer name that starts with PARAGRAPHS changed",
     b"PARAGRAPHS_OLD = [(\"a\", \"b\", \"" + b"1" * 64 + b"\")]\n",
     b"PARAGRAPHS_OLD = [(\"a\", \"b\", \"" + b"2" * 64 + b"\")]\n", False),
    ("a sha256 of a row of PARAGRAPHS that is a list changed",
     b"PARAGRAPHS = [[\"a\", \"b\", \"" + b"1" * 64 + b"\"]]\n",
     b"PARAGRAPHS = [[\"a\", \"b\", \"" + b"2" * 64 + b"\"]]\n", False),
    ("a sha256 as the third of 4 items of a row of PARAGRAPHS changed",
     b"PARAGRAPHS = [(\"a\", \"b\", \"" + b"1" * 64 + b"\", \"c\")]\n",
     b"PARAGRAPHS = [(\"a\", \"b\", \"" + b"2" * 64 + b"\", \"c\")]\n", False),
    ("a name as the third item of a row of PARAGRAPHS changed",
     b"PARAGRAPHS = [(\"a\", \"b\", ONE)]\n", b"PARAGRAPHS = [(\"a\", \"b\", TWO)]\n", False),
    ("a number as the third item of a row of PARAGRAPHS changed",
     b"PARAGRAPHS = [(\"a\", \"b\", 1)]\n", b"PARAGRAPHS = [(\"a\", \"b\", 2)]\n", False),
    ("63 hexadecimal digits as the third item of a row of PARAGRAPHS changed",
     b"PARAGRAPHS = [(\"a\", \"b\", \"" + b"1" * 63 + b"\")]\n",
     b"PARAGRAPHS = [(\"a\", \"b\", \"" + b"2" * 63 + b"\")]\n", False),
    ("65 hexadecimal digits as the third item of a row of PARAGRAPHS changed",
     b"PARAGRAPHS = [(\"a\", \"b\", \"" + b"1" * 65 + b"\")]\n",
     b"PARAGRAPHS = [(\"a\", \"b\", \"" + b"1" * 64 + b"2\")]\n", False),
]
# The constants whose values a registry entry may name as the domain that its driver tries.
# PASS stands for the constant count of pinned paragraphs, which the pass line spells.
DOMAINS = ("WHITE", "INLINE_WHITE", "OUTPUT_KINDS", "READS", "NAME_KINDS", "TIMES", "LEADS", "PASS")
# The registries of the sites of the check, each site keyed by its function's name ("<module>" for
# the code outside its functions), its ordinal there among the sites of the same form, and its
# form, never by line number, with the case of Verdicts that drives it. The form of a call is the
# whole call, its arguments included. Each registry must equal the sites of the forms that its
# extractor lists, so an entry that names a site of those forms that the check no longer has
# fails, and so does such a site with no entry. A site of another form is caught by
# CODE_SHA256, not by a registry.
# The calls that strip, split or substitute text, and each other use of WHITE_SPACE or LINE_END,
# with the domain of white space that the driver tries.
WHITE_METHODS = ("strip", "lstrip", "rstrip", "split", "rsplit", "splitlines", "sub", "subn",
                 "isspace", "replace", "translate", "expandtabs", "partition", "rpartition",
                 "removeprefix", "removesuffix")
WHITE_SPACE_SITES = {
    ("paragraphs", 1, "line.strip()"):
        ("INLINE_WHITE", "test_a_line_of_each_kind_of_white_space_inside_each_paragraph_fails"),
    ("digest", 1, "paragraph.split()"): ("WHITE", "test_white_space_inside_each_opening_text_passes"),
    ("starts_with", 1, "WHITE_SPACE.sub(' ', paragraph)"):
        ("WHITE", "test_white_space_inside_each_opening_text_passes"),
    ("starts_with", 1, "WHITE_SPACE.sub(' ', opening)"):
        ("WHITE", "test_white_space_of_each_kind_inside_each_row_opening_text_passes"),
    ("findings", 1, "LINE_END.split(text)"):
        ("INLINE_WHITE", "test_only_a_line_feed_or_a_carriage_return_ends_a_line"),
    ("findings", 1, "line.strip()"):
        ("INLINE_WHITE", "test_every_test_fails_alike_on_standard_input_by_path_and_by_default"),
    ("findings", 1, "value.strip()"):
        ("INLINE_WHITE", "test_white_space_of_each_kind_around_the_mode_values_passes"),
    ("findings", 1, "values.split('|')"):
        ("INLINE_WHITE", "test_white_space_of_each_kind_around_the_mode_values_passes"),
    ("findings", 1, "QUOTED.sub(' ', line)"):
        ("INLINE_WHITE", "test_each_test_reads_lines_by_the_same_rule"),
    ("findings", 2, "line.strip()"):
        ("INLINE_WHITE", "test_each_report_of_a_number_found_gives_that_number"),
    ("findings", 1, "text.split()"): ("INLINE_WHITE", "test_each_test_reads_lines_by_the_same_rule"),
}
# The report lines: each line that findings appends to the list that it returns, and each line of
# the lists that outcome returns, by the first 4 words of its template or the function that makes
# it, with the kind of OUTPUT_KINDS that it writes. EACH_FINDING is the "FAIL: " prefix that
# outcome puts before each line of findings.
EACH_FINDING = "each finding"
COUNTER = "test_each_kind_of_output_names_each_kind_of_name"
REPORT_SITES = {
    ("findings", 1, "expected 1 MODE line"): ("MODE lines found", COUNTER),
    ("findings", 1, "the MODE line has"): ("MODE line unclosed", COUNTER),
    ("findings", 1, "the MODE line names"): ("MODE values", COUNTER),
    ("findings", 1, "unquoted bare attended"): ("bare attended", COUNTER),
    ("findings", 1, "no statement that an"): ("absent-record sentence missing", COUNTER),
    ("findings", 1, "expected 1 pinned paragraph"): ("pinned paragraph not found once", COUNTER),
    ("findings", 1, "changed_report"): ("pinned paragraph changed", COUNTER),
    ("outcome", 1, "usage python3 I tools"): ("usage", COUNTER),
    ("outcome", 1, "FAIL cannot be read"): ("cannot be read", COUNTER),
    ("outcome", 1, "FAIL"): (EACH_FINDING, COUNTER),
    ("outcome", 1, "FAIL finding s"): ("count of findings", COUNTER),
    ("outcome", 1, "OK the MODE line"): ("pass", COUNTER),
}
# The numbers in the output: each argument of a format call, an f-string or a % format that is not
# 1 of these text names or a call of 1 of these text methods, with the domain of numbers that the
# driver tries.
TEXT_ARGUMENTS = ("name", "label", "opening", "now", "pinned", "source", "exc", "TABLE_FILE")
TEXT_METHODS = ("strip", "join", "format")
NUMBER_SITES = {
    ("findings", 1, "len(modes)"): ("TIMES", "test_each_report_of_a_number_found_gives_that_number"),
    ("findings", 1, "number"):
        ("LEADS", "test_every_test_fails_alike_on_standard_input_by_path_and_by_default"),
    ("findings", 2, "number"):
        ("LEADS", "test_every_test_fails_alike_on_standard_input_by_path_and_by_default"),
    ("findings", 1, "len(starting)"):
        ("TIMES", "test_each_report_of_a_number_found_gives_that_number"),
    ("changed_report", 1, "first"):
        ("LEADS", "test_every_test_fails_alike_on_standard_input_by_path_and_by_default"),
    ("changed_report", 1, "last"):
        ("LEADS", "test_every_test_fails_alike_on_standard_input_by_path_and_by_default"),
    ("outcome", 1, "len(found)"): ("TIMES", "test_each_report_of_a_number_found_gives_that_number"),
    ("outcome", 1, "len(PARAGRAPHS)"): ("PASS", "test_the_committed_flow_passes"),
}
# The routes to the line that the text cannot be read: each call inside outcome's try, and each
# call anywhere that reads, with the reads of READS that reach it, which the case finds from the
# branch of outcome's try that holds the call, and a driver that names each of those reads as an
# item of READS.
READ_NAMES = ("open", "input")
READ_ATTRIBUTES = ("read", "read_text", "read_bytes", "readline", "readlines", "readinto",
                   "decode", "open", "fdopen")
ROUTE_SITES = {
    ("outcome", 1, "open(0, 'rb', closefd=False)"):
        (("standard input",), "test_each_kind_of_failed_read_fails"),
    ("outcome", 1, "stream.read().decode('utf-8')"):
        (("standard input",), "test_text_that_is_not_utf8_fails"),
    ("outcome", 1, "stream.read()"): (("standard input",), "test_each_kind_of_failed_read_fails"),
    ("outcome", 1, "Path(source).read_text(encoding='utf-8')"):
        (("path", "default path"), "test_each_kind_of_failed_read_fails"),
    ("outcome", 1, "Path(source)"): (("path", "default path"), "test_each_kind_of_failed_read_fails"),
}
# The regular expressions that the check binds to a name at its top level, each by that name, with
# the case that drives it. The patterns themselves are code, which CODE_SHA256 holds.
PATTERN_SITES = {
    "MODE_VALUES": "test_text_after_the_mode_line_s_closing_parenthesis_passes",
    "BARE_ATTENDED": "test_a_word_character_of_each_category_next_to_attended_is_not_bare",
    "QUOTED": "test_each_test_reads_lines_by_the_same_rule",
    "ABSENT_RULE": "test_the_absent_rule_inside_a_longer_word_fails",
    "LINE_END": "test_only_a_line_feed_or_a_carriage_return_ends_a_line",
    "WHITE_SPACE": "test_white_space_inside_each_opening_text_passes",
}
# The name that references() gives a case that calls the check's findings in its own process,
# since such a case runs the check without launch().
IN_PROCESS = "<findings>"
# The pattern that the rest of each kind of finding, the line after "FAIL: " and the name of the
# text read, matches, and of the line that the text cannot be read.
FINDING_PATTERNS = [
    ("MODE lines found", ": " + re.escape(MODE_COUNT.format("")) + "[0-9]+$"),
    ("MODE line unclosed", ":[0-9]+: " + re.escape(UNCLOSED) + ": "),
    ("MODE values", ": " + re.escape(WRONG_MODES) + " "),
    ("bare attended", ":[0-9]+: " + re.escape(BARE) + ": "),
    ("absent-record sentence missing", ": " + re.escape(NO_ABSENT) + "$"),
    ("pinned paragraph not found once", ": " + re.escape(NOT_ONCE.split("{}")[0])),
    ("pinned paragraph changed", ":[0-9]+-[0-9]+: .*, a pinned paragraph, has changed: "),
    ("cannot be read", " " + re.escape(UNREADABLE)),
]


def scopes(tree):
    """Each scope of a module's syntax tree, as its name and its nodes: "<module>" for the
    statements outside its functions and classes, and each function or class by its name."""
    defined = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    yield "<module>", [node for node in tree.body if not isinstance(node, defined)]
    for node in tree.body:
        if isinstance(node, defined):
            yield node.name, [node]


def nodes_of(nodes):
    """Each node of the syntax trees of nodes."""
    for node in nodes:
        yield from ast.walk(node)


def position(node):
    """The place of node in the source, outer nodes before the nodes that they hold."""
    return node.lineno, node.col_offset, -node.end_lineno, -node.end_col_offset


def numbered_nodes(scope, nodes, form=ast.unparse):
    """The sites of nodes in scope, each as the scope, its ordinal in source order among the
    sites of the same form there, and its form, with the node of each."""
    sites, counts = {}, {}
    for node in sorted(nodes, key=position):
        text = form(node)
        counts[text] = counts.get(text, 0) + 1
        sites[(scope, counts[text], text)] = node
    return sites


def numbered(scope, nodes, form=ast.unparse):
    """The sites of nodes in scope, each as the scope, its ordinal in source order among the
    sites of the same form there, and its form, so a site put in or taken out is the site
    reported."""
    return set(numbered_nodes(scope, nodes, form))


def report_form(node):
    """The form of a report line: the first 4 words of its template, or the function that makes
    it."""
    for part in ast.walk(node):
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            return " ".join(re.findall(r"[A-Za-z0-9_]+", part.value)[:4])
    return ast.unparse(node.func if isinstance(node, ast.Call) else node)


def is_name(node, *names):
    """Whether node is a name among names."""
    return isinstance(node, ast.Name) and node.id in names


def white_space_sites(tree):
    """The calls of the check that strip, split or substitute text, each as the whole call, and
    each other use of WHITE_SPACE or LINE_END."""
    sites = set()
    for scope, nodes in scopes(tree):
        calls = [node for node in nodes_of(nodes) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr in WHITE_METHODS]
        receivers = {id(call.func.value) for call in calls}
        uses = [node for node in nodes_of(nodes) if is_name(node, "WHITE_SPACE", "LINE_END")
                and isinstance(node.ctx, ast.Load) and id(node) not in receivers]
        sites |= numbered(scope, calls + uses)
    return sites


def report_sites(tree):
    """Each line that the check's findings appends to the list that it returns, each other call on
    that list, and each line of the lists that its outcome returns, each keyed by report_form."""
    sites = set()
    for scope, nodes in scopes(tree):
        lines = []
        if scope == "findings":
            calls = [node for node in nodes_of(nodes) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute) and is_name(node.func.value, "found")]
            lines += [node.args[0] if node.func.attr == "append" and len(node.args) == 1
                      and not node.keywords else node.func for node in calls]
        if scope == "outcome":
            for node in nodes_of(nodes):
                if isinstance(node, ast.Return) and node.value is not None:
                    for part in ast.walk(node.value):
                        if isinstance(part, ast.List):
                            lines += part.elts
                        elif isinstance(part, ast.ListComp):
                            lines.append(part.elt)
        sites |= numbered(scope, lines, report_form)
    return sites


def format_arguments(node):
    """The arguments that node formats into text, when it is a format call, an f-string or a %
    format of a string."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format"):
        return node.args + [keyword.value for keyword in node.keywords]
    if isinstance(node, ast.JoinedStr):
        return [value.value for value in node.values if isinstance(value, ast.FormattedValue)]
    if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod)
            and isinstance(node.left, ast.Constant) and isinstance(node.left.value, str)):
        return node.right.elts if isinstance(node.right, ast.Tuple) else [node.right]
    return []


def is_text(node):
    """Whether node is a text argument: a name of TEXT_ARGUMENTS or a call of TEXT_METHODS."""
    return is_name(node, *TEXT_ARGUMENTS) or (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in TEXT_METHODS)


def number_sites(tree):
    """Each argument that the check formats into its output that is not a text argument."""
    sites = set()
    for scope, nodes in scopes(tree):
        sites |= numbered(scope, [argument for node in nodes_of(nodes)
                                  for argument in format_arguments(node) if not is_text(argument)])
    return sites


def route_nodes(tree):
    """Each call inside a try of the check's outcome, and each call of the check that reads, each
    as the whole call, with its node."""
    sites = {}
    for scope, nodes in scopes(tree):
        inside = [part for node in nodes_of(nodes) if scope == "outcome" and isinstance(node, ast.Try)
                  for statement in node.body for part in ast.walk(statement)]
        reads = [node for node in nodes_of(nodes) if isinstance(node, ast.Call) and (
            is_name(node.func, *READ_NAMES) or (isinstance(node.func, ast.Attribute)
                                                and node.func.attr in READ_ATTRIBUTES))]
        calls = {id(node): node for node in inside + reads if isinstance(node, ast.Call)}
        sites.update(numbered_nodes(scope, list(calls.values())))
    return sites


def route_sites(tree):
    """Each call inside a try of the check's outcome, and each call of the check that reads."""
    return set(route_nodes(tree))


def route_reads(tree):
    """For each route site, the reads of READS that reach it: standard input for a call in the
    body of the 1 if of outcome's try, a path and the default path for a call in its else branch,
    and none for any other call."""
    outcome = [node for node in tree.body
               if isinstance(node, ast.FunctionDef) and node.name == "outcome"][0]
    branch = [node for node in ast.walk(outcome) if isinstance(node, ast.Try)][0].body[0]
    body = {id(part) for statement in branch.body for part in ast.walk(statement)}
    orelse = {id(part) for statement in branch.orelse for part in ast.walk(statement)}
    return {site: tuple(READS[:1]) if id(node) in body else tuple(READS[1:]) if id(node) in orelse
            else () for site, node in route_nodes(tree).items()}


def pattern_sites(tree):
    """Each regular expression that the check compiles, as the name it is bound to at the top
    level, or the call itself anywhere else, and its arguments."""
    named = {id(node.value): node.targets[0].id for node in tree.body
             if isinstance(node, ast.Assign) and len(node.targets) == 1
             and isinstance(node.targets[0], ast.Name)}
    sites = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "re.compile":
            arguments = [ast.literal_eval(argument) if isinstance(argument, ast.Constant)
                         else ast.unparse(argument) for argument in node.args]
            arguments += [ast.unparse(keyword) for keyword in node.keywords]
            sites[named.get(id(node), ast.unparse(node))] = arguments
    return sites


def code_form(source):
    """The code in source, the bytes of a module, as CODE_SHA256 holds the check's: source parsed
    as compile() parses bytes, with each docstring removed, which is the first statement of the
    module, of a function, of an async function or of a class when that statement is a string
    constant, and with each sha256 of PARAGRAPHS made PLACEHOLDER, then unparsed. A sha256 of
    PARAGRAPHS is a string constant of 64 lowercase hexadecimal digits that is the third item of
    a row that is a tuple display of 3 items, in a list display that an assignment at the top
    level of the module, without an annotation and with the name PARAGRAPHS as its only target,
    binds; no other value is made PLACEHOLDER. Unparsing leaves out the
    line and column positions that the tree holds, so 2 sources whose trees differ only in those
    positions give the same form, and an edit that leaves the unparsed tree as it is keeps the
    form, and so the digest. An edit of a comment, of layout, of the quotes of a string, of how
    a number is written or of parentheses that change no grouping can leave that tree as it is,
    and each of those kinds of edit can also change it. The edits that change it form a class,
    and these are examples of it, not a complete list: such an edit can change it inside
    the = field of an f-string or inside an interpolation of a template string; parentheses
    put around the name that an annotated assignment targets, or around the targets of a del,
    can change it; an edit of an encoding declaration, which is a comment, can change it when a
    string in the source is not ASCII; and re-indenting a block that holds a string written over
    more than 1 line can change it."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                node.body = node.body[1:] or [ast.Pass()]
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and is_name(node.targets[0], "PARAGRAPHS") and isinstance(node.value, ast.List)):
            for row in node.value.elts:
                if (isinstance(row, ast.Tuple) and len(row.elts) == 3
                        and isinstance(row.elts[2], ast.Constant)
                        and isinstance(row.elts[2].value, str)
                        and re.fullmatch(r"[0-9a-f]{64}", row.elts[2].value)):
                    row.elts[2] = ast.Constant(PLACEHOLDER)
    return ast.unparse(tree)


def code_digest(source):
    """The sha256 of code_form() of source."""
    return hashlib.sha256(code_form(source).encode("utf-8")).hexdigest()


def paragraph_digests(source):
    """The third item of each row of the list that source, the bytes of the check, binds to
    PARAGRAPHS at its top level, read from its syntax tree, so no other value of the check is
    among them."""
    table, = [node.value for node in ast.parse(source).body if isinstance(node, ast.Assign)
              and [ast.unparse(target) for target in node.targets] == ["PARAGRAPHS"]]
    return [ast.literal_eval(row.elts[2]) for row in table.elts]


def references(tree):
    """For each function, method and constant at the top level of a module, the names of the
    others that its code names, a method of a class by the class and its name, and IN_PROCESS for
    code that calls a findings attribute, as a case that calls the check's findings does."""
    def named(node, owner):
        found = {part.id for part in ast.walk(node)
                 if isinstance(part, ast.Name) and isinstance(part.ctx, ast.Load)}
        if owner:
            found |= {owner + "." + part.attr for part in ast.walk(node)
                      if isinstance(part, ast.Attribute) and is_name(part.value, "self")}
        if any(isinstance(part, ast.Call) and isinstance(part.func, ast.Attribute)
               and part.func.attr == "findings" for part in ast.walk(node)):
            found.add(IN_PROCESS)
        return found
    graph = {IN_PROCESS: set()}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            graph[node.name] = named(node, None)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    graph[node.name + "." + item.name] = named(item, node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for part in ast.walk(target):
                    if isinstance(part, ast.Name):
                        graph[part.id] = named(node.value, None)
    return graph


def reaches(graph, start, domain):
    """Whether the code of start, through the functions, methods and constants that it names,
    names domain. The search goes no further into a constant of DOMAINS, so a case that names only
    INLINE_WHITE does not reach WHITE, from which INLINE_WHITE is made."""
    seen, todo = set(), [start]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        if name not in DOMAINS:
            todo += [other for other in graph.get(name, ()) if other in graph]
    return domain in seen


def kind_of(line, source):
    """The kind of OUTPUT_KINDS of line, a line of the check's output, for source, the name of the
    text read."""
    if line + "\n" == USAGE:
        return "usage"
    if re.fullmatch(r"FAIL: [0-9]+ finding\(s\)", line):
        return "count of findings"
    if line + "\n" == PASS.format(source):
        return "pass"
    prefix = "FAIL: {}".format(source)
    kinds = [kind for kind, pattern in FINDING_PATTERNS
             if line.startswith(prefix) and re.match(pattern, line[len(prefix):], re.S)]
    if len(kinds) != 1:
        raise AssertionError("expected 1 kind of line for {!r}, found {}".format(line, kinds))
    return kinds[0]


class Verdicts(unittest.TestCase):
    def assert_passes(self, text):
        status, output = verdict(text)
        self.assertEqual(status, 0, output)
        self.assertEqual(output, PASS.format("-"))

    def assert_fails(self, text, reason):
        status, output = verdict(text)
        self.assertEqual(status, 1, output)
        self.assertIn(reason, output)

    def assert_status_one(self, status, output, reason):
        self.assertEqual(status, 1, output)
        self.assertIn(reason, output)

    def assert_passes_with_pins(self, text):
        status, output = verdict(text)
        self.assertEqual(status, 0, output)
        self.assertEqual(output, PASS.format("-"))
        self.assertIn(PINS_PRESENT, output)

    def assert_each_changed(self, status, output):
        self.assertEqual(status, 1, output)
        for name, _ in NAMED:
            self.assertIn(CHANGED.format(name), output)

    def test_the_committed_flow_passes(self):
        self.assert_passes(committed())

    def test_the_committed_flow_passes_with_the_7_paragraphs(self):
        self.assert_passes_with_pins(committed())

    def test_the_check_pins_the_7_paragraphs(self):
        table = check_module().PARAGRAPHS
        self.assertEqual([(name, opening) for name, opening, _ in table], NAMED)
        text = committed()
        source = CHECK.read_text(encoding="utf-8").split("\n")
        for name, opening, pinned in table:
            with self.subTest(paragraph=name):
                start, end = span(text, opening)
                self.assertEqual(pinned, own_digest(text[start:end]))
                self.assertEqual(source.count(DIGEST_LINE.format(pinned)), 1)

    def test_the_check_is_loaded_from_its_source_not_from_a_stale_cache(self):
        # The cases that read the check's table or call its findings in this process load the
        # check from its source as it is now. A copy of the check whose bytecode cache was made
        # from an edit of the same size and time, which the standard loader reads in place of the
        # source, must still load with the table of its source.
        source = CHECK.read_text(encoding="utf-8")
        pinned = check_module().PARAGRAPHS[0][2]
        stale = ("0" if pinned[0] != "0" else "1") + pinned[1:]
        edited = replaced(source, DIGEST_LINE.format(pinned), DIGEST_LINE.format(stale))
        moment = 1700000000
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "check-flow-mode.py"
            path.write_text(edited, encoding="utf-8")
            os.utime(path, (moment, moment))
            py_compile.compile(str(path), cfile=importlib.util.cache_from_source(str(path)),
                               doraise=True,
                               invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
            path.write_text(source, encoding="utf-8")
            os.utime(path, (moment, moment))
            spec = importlib.util.spec_from_file_location("check_flow_mode_cached", str(path))
            cached = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cached)
            self.assertEqual(cached.PARAGRAPHS[0][2], stale)
            self.assertEqual(check_module(path).PARAGRAPHS[0][2], pinned)

    def test_the_entry_list_is_inside_the_pinned_failed_leg_paragraph(self):
        # The opening comes from the check's own table, so the list is pinned only when the check
        # pins the paragraph that holds it.
        openings = {name: opening for name, opening, _ in check_module().PARAGRAPHS}
        text = committed()
        start, end = span(text, openings["FAILED LEG"])
        self.assertEqual(" ".join(text[start:end].split()).count(ENTRIES), 1)
        self.assertEqual(" ".join(text.split()).count(ENTRIES), 1)
        self.assert_passes_with_pins(text)

    def test_each_pinned_paragraph_changed_fails(self):
        # Each change leaves the paragraph's opening text in place, so the paragraph is found and
        # its sha256 differs; a check that ignored any of these changes would pass that copy.
        changes = [
            ("a word appended", lambda p, o: p + " x"),
            ("its last character removed", lambda p, o: p[:-1]),
            ("a character joined after its opening", lambda p, o: p[:len(o)] + "x" + p[len(o):]),
            ("a letter in another case", lambda p, o: (
                lambda i: p[:i] + p[i].upper() + p[i + 1:])(after(p, o, r"[a-z]"))),
            ("a comma made a semicolon", lambda p, o: (
                lambda i: p[:i] + ";" + p[i + 1:])(after(p, o, r","))),
            ("2 words joined", lambda p, o: (
                lambda i: p[:i] + p[i + 1:])(space_at(p, o))),
            ("a blank line put inside", lambda p, o: (
                lambda i: p[:i] + "\n\n" + p[i + 1:])(space_at(p, o))),
            ("a line of white space put inside", lambda p, o: (
                lambda i: p[:i] + "\n \t" + chr(0x00A0) + "\n" + p[i + 1:])(space_at(p, o))),
            ("a line added after it", lambda p, o: p + "\nx"),
        ]
        for name, opening in NAMED:
            for what, change in changes:
                with self.subTest(paragraph=name, change=what):
                    self.assert_fails(with_paragraph(opening, lambda p: change(p, opening)),
                                      CHANGED.format(name))
            with self.subTest(paragraph=name, change="joined to the next paragraph"):
                text = committed()
                _, end = span(text, opening)
                blank = BLANK_LINE.match(text, end)
                self.assert_fails(text[:end] + "\n" + text[blank.end():], CHANGED.format(name))

    def test_each_pinned_paragraph_not_found_once_fails(self):
        for name, opening in NAMED:
            with self.subTest(paragraph=name, change="opening changed"):
                self.assert_fails(with_paragraph(opening, lambda p: "x" + p[1:]),
                                  NOT_ONCE.format(name, opening, 0))
            with self.subTest(paragraph=name, change="indent before its opening"):
                self.assert_fails(with_paragraph(opening, lambda p: " " + p),
                                  NOT_ONCE.format(name, opening, 0))
            # A blank line changes only white space, but it ends the paragraph inside its opening
            # text, so no paragraph starts with that text.
            for what, blank in (("a blank line", "\n\n"), ("a line of white space", "\n\t\n")):
                with self.subTest(paragraph=name, change=what + " inside its opening"):
                    self.assert_fails(with_paragraph(opening, lambda p, b=blank: (
                        lambda i: p[:i] + b + p[i + 1:])(opening.index(" "))),
                        NOT_ONCE.format(name, opening, 0))
            with self.subTest(paragraph=name, change="joined to the paragraph before it"):
                text = committed()
                start, _ = span(text, opening)
                self.assert_fails(text[:start].rstrip() + "\n" + text[start:],
                                  NOT_ONCE.format(name, opening, 0))
            with self.subTest(paragraph=name, change="repeated"):
                self.assert_fails(with_paragraph(opening, lambda p: p + "\n\n" + p),
                                  NOT_ONCE.format(name, opening, 2))

    def test_each_pinned_paragraph_rewrapped_passes(self):
        # Only the amount and kind of white space between words, or after the last word, changes.
        for name, opening in NAMED:
            for what, space in SPACES:
                with self.subTest(paragraph=name, space=what):
                    self.assert_passes_with_pins(with_paragraph(
                        opening, lambda p, s=space, o=opening: (
                            lambda i: p[:i] + s + p[i + 1:])(space_at(p, o))))
            with self.subTest(paragraph=name, space="after its last word"):
                self.assert_passes_with_pins(with_paragraph(opening, lambda p: p + " \t"))

    def test_white_space_inside_each_opening_text_passes(self):
        # The check matches an opening text with its white space made 1 space, so a paragraph
        # rewrapped inside its opening text is still found, and its sha256 does not change.
        kinds = SPACES + [(code_point(space), space) for space in WHITE]
        for what, space in kinds:
            with self.subTest(space=what):
                self.assert_passes_with_pins(with_paragraphs(
                    lambda p, o, s=space: (lambda i, j: p[:i] + s + p[i + 1:j] + s + p[j + 1:])(
                        o.index(" "), space_at(p, o))))

    def test_a_line_of_each_kind_of_white_space_inside_each_paragraph_fails(self):
        # A line that holds only white space is blank, whatever kind it is, so it splits the
        # paragraph and the part that keeps the opening text has another sha256.
        for space in INLINE_WHITE:
            with self.subTest(space=code_point(space)):
                self.assert_each_changed(*verdict(with_paragraphs(
                    lambda p, o, s=space: (lambda i: p[:i] + "\n" + s + "\n" + p[i + 1:])(
                        space_at(p, o)))))

    def test_only_a_line_feed_or_a_carriage_return_ends_a_line(self):
        # Every other white-space character stays inside its line, even one that str.splitlines()
        # reads as a line end, so 2 of them between 2 words make no blank line; 2 line ends there
        # make a blank line, which splits the paragraph. Standard input and a path read the same
        # bytes by the same rule.
        cases = [(code_point(space), space * 2, True) for space in INLINE_WHITE]
        cases += [("2 line feeds", "\n\n", False), ("2 carriage returns", "\r\r", False),
                  ("2 carriage return and line feed pairs", "\r\n\r\n", False),
                  ("a carriage return, a space and a line feed", "\r \n", False)]
        for what, space, passes in cases:
            data = with_paragraphs(lambda p, o, s=space: (lambda i: p[:i] + s + p[i + 1:])(
                space_at(p, o))).encode("utf-8")
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "flow.md"
                path.write_bytes(data)
                for read, args, given in ((READS[0], ["-"], data), (READS[1], [str(path)], b"")):
                    with self.subTest(space=what, read=read):
                        status, output = run_check(args, given)
                        if passes:
                            self.assertEqual(status, 0, output)
                            self.assertEqual(output, PASS.format(args[0]))
                        else:
                            self.assert_each_changed(status, output)

    def test_each_test_reads_lines_by_the_same_rule(self):
        # The MODE line tests and the bare "attended" test read the lines that the paragraph test
        # reads: for them only a line feed, a carriage return or both start a new line, and no
        # other character that str.splitlines() reads as a line end does. The absent-rule test
        # reads white space, not lines, so its sentence is found wrapped at any white-space
        # character.
        ends = [("a line feed", "\n"), ("a carriage return", "\r"),
                ("a carriage return and a line feed", "\r\n")]
        cases = [(what, space, True) for what, space in ends]
        cases += [(code_point(space), space, False) for space in INLINE_WHITE]
        for what, space, ends_line in cases:
            # Across a line end the first quotation leaves its "attended" bare and the second
            # skips it; across any other white space, the reverse.
            second = "- A record that holds \"x" + space + "\" attended \"y\" value."
            text = replaced(committed(), DECISIONS,
                            "- See" + space + MODE_LINE + " above.\n- A record that holds \"the"
                            " retired" + space + "attended\" value.\n" + second + "\n" + DECISIONS)
            data = replaced(text, ABSENT_WORDS, ABSENT_WORDS.replace(" record", space + "record")
                            ).encode("utf-8")
            bare = "attended\" value." if ends_line else second
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "flow.md"
                path.write_bytes(data)
                for read, args, given in ((READS[0], ["-"], data), (READS[1], [str(path)], b"")):
                    with self.subTest(space=what, read=read):
                        status, output = run_check(args, given)
                        # The report quotes the line, which may hold a character that
                        # str.splitlines() reads as a line end, so the output is split at line
                        # feeds only.
                        lines = output.rstrip("\n").split("\n")
                        self.assertEqual(status, 1, output)
                        self.assertEqual(lines[-1], "FAIL: {} finding(s)".format(
                            2 if ends_line else 1), output)
                        self.assertEqual(sum(SECOND_MODE in line for line in lines),
                                         1 if ends_line else 0, output)
                        reports = [line for line in lines if BARE in line]
                        self.assertEqual(len(reports), 1, output)
                        self.assertTrue(reports[0].endswith(BARE + ": " + bare), output)
        for what, end in (("carriage returns", "\r"), ("carriage return and line feed pairs", "\r\n")):
            data = committed().replace("\n", end).encode("utf-8")
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "flow.md"
                path.write_bytes(data)
                for read, args, given in ((READS[0], ["-"], data), (READS[1], [str(path)], b"")):
                    with self.subTest(line_ends=what, read=read):
                        status, output = run_check(args, given)
                        self.assertEqual(status, 0, output)
                        self.assertEqual(output, PASS.format(args[0]))

    def assert_fails_alike_on_each_read(self, flow, expected, **names):
        # CI runs the check with no argument, so no verdict may depend on how the check gets its
        # text. A copy of the check with only its DEFAULT line rewritten runs as a separate
        # process with no argument, as CI runs the check, and reads the changed copy of flow.md.
        # Each read must print the whole expected output, each report line naming the text read:
        # "-" on standard input, and the file's path through a path and through the default path,
        # whose name, SPACED_NAME, holds white space that each report must give as it is.
        with self.subTest(read=READS[0], **names):
            status, output = verdict(flow)
            self.assertEqual(status, 1, output)
            self.assertEqual(output, expected("-"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / SPACED_NAME
            path.write_text(flow, encoding="utf-8")
            copy = default_copy(folder, path)
            for read, args, check in ((READS[1], [str(path)], CHECK), (READS[2], [], copy)):
                with self.subTest(read=read, **names):
                    status, output = run_check(args, check=check)
                    self.assertEqual(status, 1, output)
                    self.assertEqual(output, expected(str(path)))

    def test_every_test_fails_alike_on_standard_input_by_path_and_by_default(self):
        # The texts give between them every kind of report line that the check's findings give,
        # each as built and again after 99999 blank lines, so that each line number and line
        # range that the check reports for it has 6 digits.
        for lead in LEADS:
            for what, text, expected in failing_texts(lead):
                self.assert_fails_alike_on_each_read(text, expected, text=what, lead=lead)

    def test_each_report_of_a_number_found_gives_that_number(self):
        # A report that the MODE line or a pinned paragraph is not found once gives the number
        # found, on each read. Here the MODE line is written each number of times in TIMES, and
        # in each text the opening text of every pinned paragraph starts a different number of
        # paragraphs, from that number up; the lines that hold a bare "attended", as many as the
        # MODE lines, make the count of findings that number and 8, and come after the copies, so
        # that their line numbers run to 5 digits.
        for times in TIMES:
            text, expected = counted_text(times)
            self.assert_fails_alike_on_each_read(text, expected, times=times)

    def test_each_report_of_a_change_gives_the_1_line_update(self):
        table = {name: pinned for name, _, pinned in check_module().PARAGRAPHS}
        source = CHECK.read_text(encoding="utf-8")
        for name, opening in NAMED:
            with self.subTest(paragraph=name):
                text = with_paragraph(opening, lambda p: p + " x")
                first, last = line_range(text, opening)
                start, end = span(text, opening)
                now = own_digest(text[start:end])
                status, output = verdict(text)
                self.assertEqual(status, 1, output)
                self.assertIn(REPORT.format("-", first, last, name, now, table[name], now),
                              output.splitlines())
                old_line = DIGEST_LINE.format(table[name])
                self.assertEqual(source.count(old_line), 1)
                with tempfile.TemporaryDirectory() as folder:
                    updated = Path(folder) / "check-flow-mode.py"
                    updated.write_text(source.replace(old_line, DIGEST_LINE.format(now)),
                                       encoding="utf-8")
                    status, output = verdict(text, updated)
                self.assertEqual(status, 0, output)
                self.assertEqual(output, PASS.format("-"))

    def test_an_edit_of_each_opening_text_needs_its_row_rewritten(self):
        # The check finds a paragraph by its opening text before it compares a sha256, so the
        # report of such an edit gives no sha256; a sha256 update alone does not clear it, and an
        # update of the row's opening text alone leaves the report that the paragraph has changed.
        table = {name: pinned for name, _, pinned in check_module().PARAGRAPHS}
        source = CHECK.read_text(encoding="utf-8")
        for name, opening in NAMED:
            with self.subTest(paragraph=name):
                edited = "x" + opening[1:]
                text = with_paragraph(opening, lambda p: "x" + p[1:])
                first, last = line_range(text, edited)
                start, end = span(text, edited)
                now = own_digest(text[start:end])
                report = "FAIL: -: " + NOT_ONCE.format(name, opening, 0)
                status, output = verdict(text)
                self.assert_status_one(status, output, report)
                self.assertIn(report, output.splitlines())
                old_line = DIGEST_LINE.format(table[name])
                old_row = "(\"{}\", \"{}\",".format(name, opening)
                new_row = "(\"{}\", \"{}\",".format(name, edited)
                self.assertEqual(source.count(old_line), 1)
                self.assertEqual(source.count(old_row), 1)
                digest_only = source.replace(old_line, DIGEST_LINE.format(now))
                opening_only = source.replace(old_row, new_row)
                rewritten = digest_only.replace(old_row, new_row)
                with tempfile.TemporaryDirectory() as folder:
                    updated = Path(folder) / "check-flow-mode.py"
                    updated.write_text(digest_only, encoding="utf-8")
                    status, output = verdict(text, updated)
                    self.assert_status_one(status, output, report)
                    self.assertIn(report, output.splitlines())
                    updated.write_text(opening_only, encoding="utf-8")
                    status, output = verdict(text, updated)
                    self.assertEqual(status, 1, output)
                    self.assertIn(REPORT.format("-", first, last, name, now, table[name], now),
                                  output.splitlines())
                    updated.write_text(rewritten, encoding="utf-8")
                    status, output = verdict(text, updated)
                self.assertEqual(status, 0, output)
                self.assertEqual(output, PASS.format("-"))

    def test_an_edit_of_any_character_of_each_opening_text_needs_its_row_rewritten(self):
        # The check matches every character of an opening text, each letter in its case, and
        # lets only the white space between its words change while at least 1 character of it
        # stays, so a character of it replaced or removed, 2 of its words joined, or a character
        # put inside it, the trailing space of an opening text included, leaves no paragraph that
        # starts with that text. This case calls the check's findings in this process with the
        # table changed for each edit, so it needs no copy of the check.
        module = check_module()
        table = list(module.PARAGRAPHS)
        text = committed()

        def findings_with(row, opening, pinned, data):
            module.PARAGRAPHS = table[:row] + [(table[row][0], opening, pinned)] + table[row + 1:]
            try:
                return module.findings(data, "-")
            finally:
                module.PARAGRAPHS = table

        for row, (name, opening, pinned) in enumerate(table):
            start, end = span(text, opening)
            for what, edited in opening_edits(text[start:end], opening):
                with self.subTest(paragraph=name, edit=what):
                    data = text[:start] + edited + text[start + len(opening):]
                    now = own_digest(data[start:end + len(edited) - len(opening)])
                    self.assertEqual(findings_with(row, opening, now, data),
                                     ["-: " + NOT_ONCE.format(name, opening, 0)])
                    found = findings_with(row, edited, pinned, data)
                    self.assertEqual(len(found), 1, found)
                    self.assertIn(CHANGED.format(name) + now, found[0])
                    self.assertEqual(findings_with(row, edited, now, data), [])

    def test_white_space_of_each_kind_inside_each_row_opening_text_passes(self):
        # The check makes each run of white space in a row's opening text 1 space, as it does in
        # the paragraph, so a row whose opening text holds a character of WHITE in place of its
        # first space still finds its paragraph, unchanged. This case calls the check's findings
        # in this process with the table changed for each character, so it needs no copy of the
        # check.
        module = check_module()
        table = list(module.PARAGRAPHS)
        text = committed()
        for row, (name, opening, pinned) in enumerate(table):
            self.assertIn(" ", opening)
            for space in WHITE:
                with self.subTest(paragraph=name, space=code_point(space)):
                    module.PARAGRAPHS = (table[:row] + [(name, opening.replace(" ", space, 1), pinned)]
                                         + table[row + 1:])
                    try:
                        self.assertEqual(module.findings(text, "-"), [])
                    finally:
                        module.PARAGRAPHS = table

    def test_a_sha256_update_leaves_the_mode_tests_reading_the_paragraph(self):
        # The 1-line update clears only the report that the paragraph has changed, so an edit
        # that the mode tests refuse still fails with the update in place.
        table = {name: pinned for name, _, pinned in check_module().PARAGRAPHS}
        source = CHECK.read_text(encoding="utf-8")
        additions = [(" It was attended.", BARE),
                     ("\n" + MODE_LINE + " is repeated.", SECOND_MODE)]
        for name, opening in NAMED:
            for addition, reason in additions:
                with self.subTest(paragraph=name, reason=reason):
                    text = with_paragraph(opening, lambda p, a=addition: p + a)
                    start, end = span(text, opening)
                    now = own_digest(text[start:end])
                    old_line = DIGEST_LINE.format(table[name])
                    self.assertEqual(source.count(old_line), 1)
                    with tempfile.TemporaryDirectory() as folder:
                        updated = Path(folder) / "check-flow-mode.py"
                        updated.write_text(source.replace(old_line, DIGEST_LINE.format(now)),
                                           encoding="utf-8")
                        status, output = verdict(text, updated)
                    self.assertEqual(status, 1, output)
                    self.assertIn(reason, output)
                    self.assertEqual(output.splitlines()[-1], "FAIL: 1 finding(s)", output)
                    self.assertNotIn(CHANGED.format(name), output)

    def test_a_third_mode_value_named_in_each_pinned_paragraph_fails(self):
        # This sentence passes outside the pinned paragraphs, since it starts no MODE line and
        # holds no bare "attended"; inside a pinned paragraph it changes the paragraph.
        status, output = verdict(with_paragraphs(
            lambda p, o: p + "\nA third mode, supervised, is also read."))
        self.assert_each_changed(status, output)
        self.assertNotIn(BARE, output)

    def test_an_opening_text_inside_another_paragraph_passes(self):
        # Only a paragraph that starts with the opening text counts, so a mention of it inside
        # another paragraph is not a second paragraph of that name.
        for name, opening in NAMED:
            with self.subTest(paragraph=name):
                self.assert_passes_with_pins(added("- See " + opening + " above."))

    def test_each_pinned_paragraph_at_the_start_of_the_file_passes(self):
        # The text starts with the pinned paragraph, so its verdict depends on the check reading
        # a paragraph that starts on line 1.
        text = committed()
        for name, opening in NAMED:
            with self.subTest(paragraph=name):
                start, end = span(text, opening)
                rest = "\n\n" + text[:start] + text[end:]
                self.assert_passes_with_pins(text[start:end] + rest)
                self.assert_fails(text[start:end - 1] + rest, CHANGED.format(name))

    def test_each_pinned_paragraph_at_the_end_of_the_file_passes(self):
        # The text ends with the pinned paragraph and no line break, so the paragraph's verdict
        # depends on the check reading a paragraph that the end of the text closes.
        text = committed()
        for name, opening in NAMED:
            with self.subTest(paragraph=name):
                start, end = span(text, opening)
                rest = text[:start] + text[end:]
                self.assertTrue(rest.endswith("\n"))
                self.assert_passes_with_pins(rest + "\n" + text[start:end])
                self.assert_fails(rest + "\n" + text[start:end - 1], CHANGED.format(name))

    def test_each_rule_change_in_a_pinned_paragraph_fails(self):
        for name, old, new in RULE_CHANGES:
            with self.subTest(paragraph=name, old=old, new=new):
                self.assert_fails(changed(old, new), CHANGED.format(name))
        for name, changes in FLOOR_REMOVALS:
            with self.subTest(paragraph=name, change="the floor removed"):
                text = committed()
                for old, new in changes:
                    text = replaced(text, old, new)
                self.assert_fails(text, CHANGED.format(name))

    def test_the_committed_flow_passes_by_path_and_by_default(self):
        for args in ([str(FLOW)], []):
            with self.subTest(args=args):
                status, output = run_check(args)
                self.assertEqual(status, 0, output)
                self.assertEqual(output, PASS.format(FLOW))

    def test_the_mode_text_of_main_fails(self):
        status, output = verdict(MAIN_MODE_TEXT)
        self.assertEqual(status, 1, output)
        lines = output.splitlines()
        self.assertEqual(lines[-1], "FAIL: 16 finding(s)", output)
        self.assertEqual(sum(WRONG_MODES in line for line in lines), 1, output)
        self.assertEqual(sum(BARE in line for line in lines), 7, output)
        self.assertEqual(sum(NO_ABSENT in line for line in lines), 1, output)
        for name, opening in NAMED:
            self.assertEqual(sum(NOT_ONCE.format(name, opening, 0) in line for line in lines), 1,
                             output)

    def test_a_third_value_on_the_mode_line_fails(self):
        self.assert_fails(changed(MODE_LINE, "- MODE (attended-autonomous | unattended | supervised)"),
                          WRONG_MODES)

    def test_a_repeated_value_on_the_mode_line_fails(self):
        self.assert_fails(changed(MODE_LINE, "- MODE (attended-autonomous | unattended | unattended)"),
                          WRONG_MODES)

    def test_a_capitalized_value_on_the_mode_line_fails(self):
        self.assert_fails(changed(MODE_LINE, "- MODE (Attended-Autonomous | unattended)"), WRONG_MODES)

    def test_a_dropped_value_on_the_mode_line_fails(self):
        for line in ("- MODE (unattended)", "- MODE (attended-autonomous)"):
            with self.subTest(line=line):
                self.assert_fails(changed(MODE_LINE, line), WRONG_MODES)

    def test_another_separator_on_the_mode_line_fails(self):
        self.assert_fails(changed(MODE_LINE, "- MODE (attended-autonomous, unattended)"),
                          WRONG_MODES)

    def test_the_mode_values_in_the_other_order_pass(self):
        self.assert_passes(changed(MODE_LINE, "- MODE (unattended | attended-autonomous)"))

    def test_white_space_of_each_kind_around_the_mode_values_passes(self):
        # The check removes the white space at either end of each MODE value before it compares
        # the values, so each kind of white space that ends no line passes there, alone and with
        # every other kind.
        kinds = [(code_point(space), space) for space in INLINE_WHITE] + [("every kind", PADDING)]
        for what, space in kinds:
            with self.subTest(space=what):
                self.assert_passes(changed(MODE_LINE, "- MODE ({0}attended-autonomous{0}|{0}"
                                                      "unattended{0})".format(space)))

    def test_each_separator_on_the_mode_line_splits_a_value(self):
        # The check splits the MODE values at each "|", so a line of 5 values with no white space
        # around its separators reports each value apart.
        values = ["attended-autonomous", "unattended", "a", "b", "c"]
        status, printed = verdict(changed(MODE_LINE, "- MODE ({})".format("|".join(values))))
        self.assertEqual(status, 1, printed)
        self.assertEqual(printed, output(["FAIL: -: {} {}, not exactly attended-autonomous |"
                                          " unattended".format(WRONG_MODES, " | ".join(values))]))

    def test_text_after_the_mode_line_s_closing_parenthesis_passes(self):
        # The MODE values end at the first closing parenthesis, so a later parenthesis on the line
        # is not read as part of them.
        self.assert_passes(changed(MODE_LINE, MODE_LINE + " is read (see below)"))

    def test_no_mode_line_fails(self):
        self.assert_fails(changed(MODE_LINE, "- Mode (attended-autonomous | unattended)"),
                          "expected 1 MODE line starting \"- MODE (\", found 0")

    def test_a_second_mode_line_fails(self):
        self.assert_fails(added(MODE_LINE + " is repeated."),
                          "expected 1 MODE line starting \"- MODE (\", found 2")

    def test_a_second_unclosed_mode_line_fails(self):
        status, output = verdict(added("- MODE (supervised is a third mode."))
        self.assertEqual(status, 1, output)
        self.assertIn("expected 1 MODE line starting \"- MODE (\", found 2", output)
        self.assertIn(UNCLOSED, output)

    def test_an_unclosed_mode_line_fails(self):
        self.assert_fails(changed(MODE_LINE, "- MODE (attended-autonomous | unattended"), UNCLOSED)

    def test_quoted_values_on_the_mode_line_fail(self):
        self.assert_fails(changed(MODE_LINE, "- MODE (\"attended-autonomous\" | \"unattended\")"),
                          WRONG_MODES)

    def test_an_unquoted_bare_attended_fails(self):
        self.assert_fails(added("- Absent = attended (conservative)."), BARE)

    def test_a_capitalized_bare_attended_fails(self):
        self.assert_fails(added("- Attended is the default."), BARE)

    def test_attended_in_typographic_quotes_fails(self):
        quoted = chr(0x201C) + "attended" + chr(0x201D)
        self.assert_fails(added("- A record that holds " + quoted + " is a legacy record."), BARE)

    def test_a_bare_attended_after_line_250_fails(self):
        # The other bare-word cases add their line just before the DECISIONS bullet, so whether a
        # check that read only the start of the file reaches that line depends on where the bullet
        # is. This case adds its line at the end, after blank lines that place it after line 300
        # whatever line the bullet is on, beyond any likely read limit of such a check.
        text = committed()
        self.assertTrue(text.endswith("\n"))
        count = text.count("\n")
        padding = "\n" * max(0, 300 - count)
        number = count + len(padding) + 1
        status, output = verdict(text + padding + "- Absent = attended (conservative).\n")
        self.assertEqual(status, 1, output)
        self.assertIn("-:{}: {}".format(number, BARE), output)

    def test_the_absent_record_sentence_removed_fails(self):
        self.assert_fails(changed(ABSENT_WORDS, "reads the mode record"), NO_ABSENT)

    def test_a_quoted_attended_passes(self):
        self.assert_passes(added("- A record that holds \"attended\" is a legacy record."))

    def test_a_longer_word_that_holds_attended_passes(self):
        self.assert_passes(added("- The record has no attendedness field."))

    def test_a_word_that_extends_attended_autonomous_fails(self):
        # Only the whole word "attended-autonomous" is exempt, so a longer word that starts with it
        # still holds a bare "attended".
        self.assert_fails(added("- The session runs attended-autonomously."), BARE)

    def test_a_bare_attended_just_after_a_closing_quote_fails(self):
        # The quotation reads as a space, so the "un" before it does not join the "attended" after
        # it, and the line holds a bare "attended" outside the quotes.
        self.assert_fails(added("- A legacy un\"stored\"attended record."), BARE)

    def test_a_word_character_of_each_category_next_to_attended_is_not_bare(self):
        # "attended" is bare only with no word character, as Python's re reads one, just before
        # or just after it, and "attended-autonomous" is exempt only with none just after it. Each
        # character of WORD_CHARACTERS, of each category in ASCII and outside it, is tried there.
        for char in WORD_CHARACTERS:
            with self.subTest(char=code_point(char)):
                self.assert_passes(added("- The record holds attended" + char + " and " + char
                                         + "attended."))
                line = "- The session runs attended-autonomous" + char + "."
                number, _ = line_of(added(line), line)
                status, printed = verdict(added(line))
                self.assertEqual(status, 1, printed)
                self.assertEqual(printed, output(["FAIL: -:{}: {}: {}".format(number, BARE, line)]))

    def test_a_quotation_just_after_attended_autonomous_passes(self):
        # The quotation reads as a space, so the "ly" after it does not extend
        # "attended-autonomous" into a longer word, and the line holds no bare "attended".
        self.assert_passes(added("- The session runs attended-autonomous\"x\"ly."))

    def test_attended_autonomous_in_capital_letters_passes(self):
        self.assert_passes(added("- Attended-Autonomous is one of the writer's 2 values."))

    def test_the_absent_rule_in_its_second_wording_passes(self):
        self.assert_passes(changed("The session " + ABSENT_WORDS,
                                   "An absent mode record is read as unattended"))

    def test_the_absent_rule_in_capital_letters_passes(self):
        self.assert_passes(changed(ABSENT_WORDS, ABSENT_WORDS.upper()))

    def test_the_absent_rule_wrapped_across_a_line_break_passes(self):
        self.assert_passes(changed(ABSENT_WORDS, "reads an absent mode\n  record as unattended"))

    def test_the_absent_rule_inside_a_longer_word_fails(self):
        # Each wording of the absent-record sentence must stand as whole words, so a word
        # character just before its first word or just after its last leaves it missing.
        for wording in (ABSENT_WORDS, "an absent mode record is read as unattended"):
            for before, after in (("x", ""), ("", "ness")):
                with self.subTest(wording=wording, before=before, after=after):
                    self.assert_fails(changed("The session " + ABSENT_WORDS,
                                              "The session " + before + wording + after), NO_ABSENT)

    def assert_unreadable(self, status, output, source, error, reason):
        # The whole output is 1 line, which names the text read and gives the error that Python
        # gives for the failed read, an error that this test gets by its own read and that must
        # hold reason.
        self.assertEqual(status, 1, output)
        self.assertIn(reason, error)
        self.assertEqual(output, "FAIL: {} {}{}\n".format(source, UNREADABLE, error))

    def test_a_path_that_does_not_exist_fails(self):
        # A missing file fails alike through a path and through the default path, as CI reads it.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "missing.md"
            copy = default_copy(folder, path)
            error = read_error(path.read_bytes)
            for read, args, check in ((READS[1], [str(path)], CHECK), (READS[2], [], copy)):
                with self.subTest(read=read):
                    status, output = run_check(args, check=check)
                    self.assert_unreadable(status, output, path, error,
                                           "[Errno {}]".format(errno.ENOENT))

    def test_text_that_is_not_utf8_fails(self):
        # Text that is not UTF-8 fails alike on standard input, through a path and through the
        # default path, as CI reads it.
        data = committed().encode("utf-8") + b"\xff\n"
        error = read_error(lambda: data.decode("utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "flow.md"
            path.write_bytes(data)
            copy = default_copy(folder, path)
            for read, args, given, check, source in (
                    (READS[0], ["-"], data, CHECK, "-"),
                    (READS[1], [str(path)], b"", CHECK, path),
                    (READS[2], [], b"", copy, path)):
                with self.subTest(read=read):
                    status, output = run_check(args, given, check)
                    self.assert_unreadable(status, output, source, error, "can't decode byte 0xff")

    def test_a_byte_order_mark_is_read_alike_on_each_read(self):
        # The check decodes UTF-8 alike on each read, so a byte order mark is the character
        # U+FEFF on standard input as through a path. Here it stands before a line that would
        # otherwise be a second MODE line naming another value, so the text passes on each read.
        data = (chr(0xFEFF) + "- MODE (supervised)\n\n" + committed()).encode("utf-8")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "flow.md"
            path.write_bytes(data)
            copy = default_copy(folder, path)
            for read, args, given, check, source in ((READS[0], ["-"], data, CHECK, "-"),
                                                     (READS[1], [str(path)], b"", CHECK, path),
                                                     (READS[2], [], b"", copy, path)):
                with self.subTest(read=read):
                    status, printed = run_check(args, given, check)
                    self.assertEqual(status, 0, printed)
                    self.assertEqual(printed, PASS.format(source))

    def test_an_empty_path_is_read_as_given(self):
        # PATH is read as given, so an empty argument is the path "", which Python reads as the
        # current folder, never the default path.
        error = read_error(Path("").read_bytes)
        with self.subTest(read=READS[1]):
            status, printed = run_check([""])
            self.assert_unreadable(status, printed, "", error, "[Errno {}]".format(errno.EISDIR))

    def test_each_kind_of_failed_read_fails(self):
        # Any error that Python gives for a failed read, not only a missing file, gives the 1
        # line that the text cannot be read: through a path and through the default path, a
        # folder, a path through a file, a symbolic link to itself, a name too long and a file
        # that cannot be read; on standard input, a descriptor open only for writing and a
        # closed standard input.
        def a_folder(folder):
            path = folder / "flow.md"
            path.mkdir()
            return path

        def through_a_file(folder):
            (folder / "file").write_text("x", encoding="utf-8")
            return folder / "file" / "flow.md"

        def a_loop(folder):
            path = folder / "flow.md"
            path.symlink_to(path.name)
            return path

        def too_long(folder):
            return folder / ("n" * 300)

        def no_read_permission(folder):
            path = folder / "flow.md"
            path.write_bytes(committed().encode("utf-8"))
            path.chmod(0)
            return path

        kinds = [("a folder", a_folder, errno.EISDIR),
                 ("a path through a file", through_a_file, errno.ENOTDIR),
                 ("a symbolic link to itself", a_loop, errno.ELOOP),
                 ("a name too long", too_long, errno.ENAMETOOLONG),
                 ("a file with no read permission", no_read_permission, errno.EACCES)]
        for what, make, number in kinds:
            with tempfile.TemporaryDirectory() as name:
                path = make(Path(name))
                copy = default_copy(name, path)
                for read, args, check in ((READS[1], [str(path)], CHECK), (READS[2], [], copy)):
                    with self.subTest(kind=what, read=read):
                        if number == errno.EACCES and os.access(str(path), os.R_OK):
                            self.skipTest("this account reads a file that has no read permission")
                        error = read_error(path.read_bytes)
                        status, output = run_check(args, check=check)
                        self.assert_unreadable(status, output, path, error,
                                               "[Errno {}]".format(number))
        bad = "[Errno {}]".format(errno.EBADF)
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "flow.md"
            path.write_bytes(committed().encode("utf-8"))
            descriptor = os.open(str(path), os.O_WRONLY)
            try:
                error = read_error(lambda: os.read(descriptor, 1))
                with self.subTest(kind="a descriptor open only for writing", read=READS[0]):
                    status, output = run_check(["-"], stdin=descriptor)
                    self.assert_unreadable(status, output, "-", error, bad)
            finally:
                os.close(descriptor)
        closed = os.open(os.devnull, os.O_RDONLY)
        os.close(closed)
        error = read_error(lambda: os.read(closed, 1))
        with self.subTest(kind="a closed standard input", read=READS[0]):
            status, output = run_check(["-"], closed=True)
            self.assert_unreadable(status, output, "-", error, bad)

    def test_more_than_1_argument_fails(self):
        # The whole output is the usage line, whatever the arguments name.
        for args in ([str(FLOW), str(FLOW)], ["-", "-"], [str(FLOW), "-", str(FLOW)]):
            with self.subTest(args=args):
                status, output = run_check(args, FLOW.read_bytes())
                self.assertEqual(status, 1, output)
                self.assertEqual(output, USAGE)

    def test_each_file_is_named_by_the_bytes_of_its_name_in_every_locale(self):
        # The check writes its output as UTF-8 bytes itself, so the name of the file read reaches
        # standard output as the bytes it is, whatever the locale: a byte that is not UTF-8, and
        # white space inside the name and at its end. The pass line, a finding and the line that
        # the file cannot be read each name the file so, through a path and through the default
        # path, under each locale of LOCALES and with ASCII_STDOUT. The copy of the check that
        # reads the default path lies in a folder whose name holds the same bytes, so the check
        # also resolves its own path through such a name.
        text = added(ABSENT_ATTENDED)
        bare, _ = line_of(text, ABSENT_ATTENDED)
        settings = [(locale, False) for locale in LOCALES] + [("ASCII_STDOUT", True)]
        for kind, base in (("a byte that is not UTF-8", UNDECODED_NAME),
                           ("white space", SPACED_NAME.encode("utf-8"))):
            for report in ("pass", "finding", "cannot be read"):
                with tempfile.TemporaryDirectory() as name:
                    path = os.fsencode(name) + b"/" + base
                    shown = os.fsdecode(path)
                    if report == "pass":
                        Path(shown).write_bytes(committed().encode("utf-8"))
                        status, rest = 0, PASS.format("")[len("OK: "):]
                        expected = b"OK: " + path + rest.encode("utf-8")
                    elif report == "finding":
                        Path(shown).write_bytes(text.encode("utf-8"))
                        status, rest = 1, ":{}: {}: {}\nFAIL: 1 finding(s)\n".format(
                            bare, BARE, ABSENT_ATTENDED)
                        expected = b"FAIL: " + path + rest.encode("utf-8")
                    else:
                        error = read_error(Path(shown).read_bytes)
                        self.assertIn("[Errno {}]".format(errno.ENOENT), error)
                        status, rest = 1, " {}{}\n".format(UNREADABLE, error)
                        expected = b"FAIL: " + path + rest.encode("utf-8")
                    holder = os.fsdecode(os.fsencode(name) + b"/check-" + base)
                    os.mkdir(holder)
                    copy = default_copy(holder, shown)
                    for read, args, check in ((READS[1], [path], CHECK), (READS[2], [], copy)):
                        for setting, wrapped in settings:
                            with self.subTest(name=kind, report=report, read=read, setting=setting):
                                environment = (None if wrapped or setting is None
                                               else dict(os.environ, LC_ALL=setting))
                                run = launch(args, check, ascii_stdout=wrapped, env=environment,
                                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
                                self.assertEqual(run.returncode, status, run.stdout)
                                self.assertEqual(run.stdout, expected)

    def test_every_report_kind_is_written_whatever_the_locale_encodes(self):
        # With a sys.stdout that writes only ASCII, the 3 texts that give every kind of report
        # line give their whole output on standard input. The reports of the MODE values, of a
        # bare "attended" and of an unclosed MODE line quote characters outside ASCII, so a check
        # that wrote any of them through sys.stdout fails here.
        for what, text, expected in failing_texts():
            with self.subTest(text=what):
                run = launch(["-"], ascii_stdout=True, input=text.encode("utf-8"),
                             stdout=subprocess.PIPE)
                self.assertEqual(run.returncode, 1, run.stdout)
                self.assertEqual(run.stdout, expected("-").encode("utf-8"))

    def test_each_kind_of_output_names_each_kind_of_name(self):
        # The coverage counter of the cross product of OUTPUT_KINDS and NAME_KINDS. For each kind
        # of name, on each read that gives it, the whole output of each text below is compared
        # byte for byte, and each line of that output counts the cell of its kind and that kind of
        # name: "-" on standard input, and each file name through a path and through the default
        # path. The texts are the 3 of failing_texts(), the committed flow.md, text that cannot be
        # read and 2 arguments of that kind of name. The case fails when a cell is not counted.
        cells = set()
        for index, name in enumerate(NAME_KINDS):
            with tempfile.TemporaryDirectory() as folder:
                if name == "-":
                    path = None
                    error = read_error(lambda: b"\xff\n".decode("utf-8"))
                    reads = [(READS[0], ["-"], CHECK, "-")]
                else:
                    path = os.fsencode(folder) + b"/" + (
                        name if isinstance(name, bytes) else name.encode("utf-8"))
                    shown = os.fsdecode(path)
                    error = read_error(Path(shown).read_bytes)
                    reads = [(READS[1], [path], CHECK, shown),
                             (READS[2], [], default_copy(folder, shown), shown)]
                texts = [(what, text.encode("utf-8"), 1, expected)
                         for what, text, expected in failing_texts()]
                texts += [("a pass", committed().encode("utf-8"), 0, PASS.format),
                          ("text that cannot be read", b"\xff\n" if path is None else None, 1,
                           lambda source: "FAIL: {} {}{}\n".format(source, UNREADABLE, error))]
                for what, data, status, expected in texts:
                    if path is not None and data is not None:
                        Path(shown).write_bytes(data)
                    elif path is not None and os.path.exists(shown):
                        os.unlink(shown)
                    for read, args, check, source in reads:
                        with self.subTest(name=index, read=read, text=what):
                            streams = ({"input": data} if path is None
                                       else {"stdin": subprocess.DEVNULL})
                            run = launch(args, check, stdout=subprocess.PIPE, **streams)
                            wanted = expected(source)
                            self.assertEqual(run.returncode, status, run.stdout)
                            self.assertEqual(run.stdout, wanted.encode("utf-8", "surrogateescape"))
                            cells |= {(kind_of(line, source), index)
                                      for line in wanted.split("\n")[:-1]}
                with self.subTest(name=index, text="2 arguments"):
                    args = ["-", "-"] if path is None else [path, path]
                    run = launch(args, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
                    self.assertEqual(run.returncode, 1, run.stdout)
                    self.assertEqual(run.stdout, USAGE.encode("utf-8"))
                    cells.add((kind_of(USAGE[:-1], None), index))
        self.assertEqual(sorted(cells), sorted((kind, index) for kind in OUTPUT_KINDS
                                               for index in range(len(NAME_KINDS))))

    def test_output_that_cannot_be_written_gives_status_1_and_nothing_on_standard_error(self):
        # The check writes its whole output itself, so a write that fails ends the check with exit
        # status 1, a pass included, and Python is left no buffer of sys.stdout to flush at exit
        # and to report on standard error: for the usage line, the line that the text cannot be
        # read, a failure and a pass.
        reports = [("the usage line", ["-", "-"], b""),
                   ("the line that the text cannot be read", ["-"], b"\xff\n"),
                   ("a failure", ["-"], b"x\n"),
                   ("a pass", ["-"], committed().encode("utf-8"))]

        def broken_pipe():
            read, write = os.pipe()
            os.close(read)
            return write

        def read_only():
            return os.open(os.devnull, os.O_RDONLY)

        def full_device():
            return os.open("/dev/full", os.O_WRONLY)

        targets = [("a pipe whose reading end is closed", broken_pipe),
                   ("a standard output open only for reading", read_only),
                   ("a full device", full_device)]
        for what, make in targets:
            for report, args, data in reports:
                with self.subTest(stdout=what, report=report):
                    if make is full_device and not os.path.exists("/dev/full"):
                        self.skipTest("this system has no /dev/full")
                    descriptor = make()
                    try:
                        run = launch(args, stdout=descriptor, input=data)
                    finally:
                        os.close(descriptor)
                    self.assertEqual(run.returncode, 1)
        for report, args, data in reports:
            with self.subTest(stdout="a closed standard output", report=report):
                run = launch(args, stdout=subprocess.DEVNULL, input=data,
                             preexec_fn=lambda: os.close(1))
                self.assertEqual(run.returncode, 1)

    def test_a_folder_as_a_standard_stream_stops_python_before_the_check(self):
        # Python opens the 3 standard streams before it runs any code of the check, and it stops
        # with exit status 1 when any of them is a folder, so no code of the check can give its
        # line or keep standard error empty there. This case holds that exception, which the
        # check's docstring states, and Python's fatal error, so that a Python that ran the check
        # with such a stream fails it and calls for the docstring to be revisited.
        stated = " ".join(check_module().__doc__.split())
        self.assertIn("when standard input, standard output or standard error is a folder, Python"
                      " stops before the check runs", stated)
        fatal = b"Fatal Python error: init_sys_streams"
        with tempfile.TemporaryDirectory() as name:
            folder = os.open(name, os.O_RDONLY)
            try:
                for stream in ("stdin", "stdout", "stderr"):
                    with self.subTest(stream=stream):
                        streams = {"stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE,
                                   "stderr": subprocess.PIPE}
                        streams[stream] = folder
                        run = subprocess.run([sys.executable, "-I", str(CHECK), "-"], timeout=60,
                                             check=False, **streams)
                        self.assertEqual(run.returncode, 1, run.stderr)
                        if stream != "stdout":
                            self.assertEqual(run.stdout, b"")
                        if stream != "stderr":
                            self.assertTrue(run.stderr.startswith(fatal), run.stderr)
            finally:
                os.close(folder)

    def test_every_site_has_a_driver(self):
        # The case compares the digest of the check's syntax tree, parsed from its bytes, without
        # its docstrings and the sha256 values of PARAGRAPHS, unparsed, with CODE_SHA256.
        # Unparsing leaves out the line and column positions that the tree holds, so a change to
        # that unparsed tree fails until the digest is updated; the update in the diff is the
        # reviewer's cue to check the registries; an edit that keeps the unparsed tree keeps the
        # digest. It requires the
        # codec that Python finds for those bytes to be UTF-8, with or
        # without a byte order mark, so that Python decodes the file that it runs as compile()
        # decodes the bytes. Python reads a carriage return and line feed pair, and any other
        # carriage return, as a line feed, both when it looks for an encoding declaration and when
        # it parses, so the case reads the bytes with those line ends made line feeds to find the
        # codec and to apply the rows. Each of MUTATIONS must change that digest and each of
        # PRESERVED must keep it, a row that holds DIGEST once for each sha256 of PARAGRAPHS;
        # each pair of FORM_PAIRS must give equal or different digests as it states. So a
        # code_form() that fails 1 of those rows fails; each row is evidence for its own edit
        # only. Each registry equals the sites of the forms that its extractor lists; a site of
        # another form is caught by the code digest, not by a registry. A driver's code names its
        # domain constant and launch() or findings(); this does not show that it runs them, or
        # that it would fail on a change at its site.
        source = CHECK.read_bytes()
        text = re.sub(rb"\r\n?", b"\n", source)
        digests = paragraph_digests(text)
        self.assertTrue(digests, "expected a sha256 in the PARAGRAPHS of {}".format(CHECK))
        now = code_digest(source)
        for edits, changes in ((MUTATIONS, True), (PRESERVED, False)):
            for name, old, new in edits:
                for value in digests if DIGEST in old else [DIGEST]:
                    edit = [part.replace(DIGEST, value).encode("utf-8") for part in (old, new)]
                    with self.subTest(edit=name, sha256=value if DIGEST in old else None):
                        self.assertEqual(text.count(edit[0]), 1,
                                         "expected 1 {!r} in {}".format(edit[0], CHECK))
                        self.assertEqual(code_digest(text.replace(*edit)) != now, changes,
                                         "expected code_form() to {} its sha256 for {}".format(
                                             "change" if changes else "keep", name))
        for name, one, other, same in FORM_PAIRS:
            with self.subTest(form=name):
                self.assertEqual(code_digest(one) == code_digest(other), same,
                                 "expected code_form() to {} the 2 sources of {}".format(
                                     "make equal" if same else "keep apart", name))
        with self.subTest(pin="encoding"):
            found = tokenize.detect_encoding(io.BytesIO(text).readline)[0]
            utf_8 = (codecs.lookup("utf-8"), codecs.lookup("utf-8-sig"))
            self.assertIn(codecs.lookup(found), utf_8,
                          "Python reads {} as {}, not as UTF-8, so the code that it runs from the"
                          " file can differ from the tree that CODE_SHA256 holds".format(
                              CHECK, found))
        with self.subTest(pin="CODE_SHA256"):
            self.assertEqual(now, CODE_SHA256,
                             "the check's code has changed: its code_form() sha256 is now {}; once"
                             " the registries below hold its sites, replace the line 'CODE_SHA256 ="
                             " \"{}\"' of tools/test-check-flow-mode.py with 'CODE_SHA256 = \"{}\"'"
                             .format(now, CODE_SHA256, now))
        tree = ast.parse(source, str(CHECK))
        own = ast.parse(Path(__file__).read_bytes(), __file__)
        graph = references(own)
        cases = {node.name: node for statement in own.body
                 if isinstance(statement, ast.ClassDef) and statement.name == "Verdicts"
                 for node in statement.body if isinstance(node, ast.FunctionDef)}

        def names_a_runner(case):
            return any(reaches(graph, "Verdicts." + case, runner) for runner in ("launch", IN_PROCESS))

        registries = [("white space", white_space_sites, WHITE_SPACE_SITES, None),
                      ("report", report_sites, REPORT_SITES, "OUTPUT_KINDS"),
                      ("number", number_sites, NUMBER_SITES, None),
                      ("read route", route_sites, ROUTE_SITES, "READS")]
        for what, extract, registry, domain in registries:
            with self.subTest(sites=what):
                found = extract(tree)
                self.assertEqual(
                    {"unregistered": sorted(found - set(registry)),
                     "missing": sorted(set(registry) - found)},
                    {"unregistered": [], "missing": []},
                    "{} sites of the check with no registered driver, and registered {} sites"
                    " that the check no longer has".format(what, what))
                for site, (detail, case) in sorted(registry.items()):
                    named = domain or detail
                    self.assertIn(named, DOMAINS, site)
                    self.assertTrue(callable(getattr(Verdicts, case, None)),
                                    "{} names no case {}".format(site, case))
                    self.assertTrue(reaches(graph, "Verdicts." + case, named),
                                    "{}, the driver of {}, does not reach {}".format(
                                        case, site, named))
                    self.assertTrue(names_a_runner(case),
                                    "{}, the driver of {}, names neither launch() nor the check's"
                                    " findings".format(case, site))
        self.assertEqual(sorted(kind for kind, _ in REPORT_SITES.values() if kind != EACH_FINDING),
                         sorted(OUTPUT_KINDS))
        self.assertEqual(sorted({read for reads, _ in ROUTE_SITES.values() for read in reads}),
                         sorted(READS))
        # Each route's reads are those that its branch of outcome's try gives, and its driver
        # names each of them as an item of READS.
        self.assertEqual(route_reads(tree), {site: reads for site, (reads, _) in ROUTE_SITES.items()})
        for site, (reads, case) in sorted(ROUTE_SITES.items()):
            with self.subTest(route=site):
                indexes = {part.slice.value for part in ast.walk(cases[case])
                           if isinstance(part, ast.Subscript) and is_name(part.value, "READS")
                           and isinstance(part.slice, ast.Constant)}
                self.assertLessEqual({READS.index(read) for read in reads}, indexes, case)
        with self.subTest(sites="regular expression"):
            self.assertEqual(sorted(pattern_sites(tree)), sorted(PATTERN_SITES))
            for name, case in sorted(PATTERN_SITES.items()):
                self.assertTrue(callable(getattr(Verdicts, case, None)),
                                "{} names no case {}".format(name, case))
                self.assertTrue(names_a_runner(case),
                                "{}, the driver of {}, names neither launch() nor the check's"
                                " findings".format(case, name))


class Residual(unittest.TestCase):
    def test_a_third_value_outside_the_mode_line_passes(self):
        status, output = verdict(added("- A third mode, supervised, is also read."))
        self.assertEqual(status, 0, output)

    def test_a_third_value_with_a_bare_attended_outside_the_mode_line_fails(self):
        # This line, added outside the pinned paragraphs, is no MODE line, starts no paragraph with
        # a pinned opening text and joins no pinned paragraph, so of the tests that read what a
        # line holds only the bare "attended" test can fail it, whatever mode value it names.
        status, output = verdict(added("- A third mode, attended-only, is also read."))
        self.assertEqual(status, 1, output)
        self.assertIn(BARE, output)

    def test_a_paragraph_elsewhere_that_starts_with_an_opening_text_fails(self):
        # Text outside the pinned paragraphs is not pinned, but a paragraph there that starts with
        # a pinned opening text is a second paragraph of that name.
        text = committed()
        self.assertTrue(text.endswith("\n"))
        for name, opening in NAMED:
            with self.subTest(paragraph=name):
                status, output = verdict(text + "\n" + opening + "a note added outside the pins.\n")
                self.assertEqual(status, 1, output)
                self.assertIn(NOT_ONCE.format(name, opening, 2), output)

    def test_a_quoted_retired_default_passes(self):
        status, output = verdict(added("- Absent = \"attended\" (conservative)."))
        self.assertEqual(status, 0, output)

    def test_an_indented_mode_line_is_not_counted(self):
        status, output = verdict(added("  - MODE (supervised) is a nested bullet."))
        self.assertEqual(status, 0, output)

    def test_a_line_that_starts_with_part_of_the_mode_prefix_is_not_counted(self):
        # A MODE line is a line whose first characters are "- MODE (", so a line that starts with
        # each shorter part of those characters, followed by another character, is no MODE line.
        prefix = "- MODE ("
        for size in range(1, len(prefix)):
            line = prefix[:size] + "x supervised is a note."
            with self.subTest(line=line):
                status, output = verdict(added(line))
                self.assertEqual(status, 0, output)

    def test_the_absent_rule_inside_a_rejecting_quotation_passes(self):
        status, output = verdict(changed(
            "The session " + ABSENT_WORDS,
            "It is false that \"the session " + ABSENT_WORDS + "\"; it reads it as"
            " attended-autonomous"))
        self.assertEqual(status, 0, output)

    def test_a_sentence_that_contradicts_the_absent_rule_passes(self):
        status, output = verdict(added("- A session reads a missing record as attended-autonomous."))
        self.assertEqual(status, 0, output)

    def test_the_matched_absent_sentence_negated_passes(self):
        status, output = verdict(changed(
            "The session " + ABSENT_WORDS,
            "The session never " + ABSENT_WORDS + "; it reads it as attended-autonomous"))
        self.assertEqual(status, 0, output)

    def test_a_quoted_attended_wrapped_across_a_line_break_fails(self):
        status, output = verdict(added("- A record that holds \"the retired\n  attended\" value."))
        self.assertEqual(status, 1, output)
        self.assertIn(BARE, output)

    def test_a_bare_attended_after_a_wrapped_closing_quote_passes(self):
        # The check pairs straight quotes left to right on each line, so the closing quote of the
        # quotation opened on the line above pairs with the opening quote of "for now", and the
        # bare "attended" between them is skipped.
        status, output = verdict(added("- A legacy record is read \"as attended-autonomous, never as\n"
                                       "  unattended\" though Absent = attended \"for now\"."))
        self.assertEqual(status, 0, output)

    def test_the_absent_rule_in_other_words_fails(self):
        status, output = verdict(changed(ABSENT_WORDS, "treats a missing mode record as unattended"))
        self.assertEqual(status, 1, output)
        self.assertIn(NO_ABSENT, output)

    def test_an_ordinary_english_attended_fails(self):
        status, output = verdict(added("- The operator attended the planning call."))
        self.assertEqual(status, 1, output)
        self.assertIn(BARE, output)

    def test_an_edit_outside_the_pinned_paragraphs_passes(self):
        status, output = verdict(changed("Keep-ahead buffer: at every invocation",
                                         "Keep-ahead buffer: at each invocation"))
        self.assertEqual(status, 0, output)
        self.assertIn(PINS_PRESENT, output)

    def test_entry_62_added_to_the_rule_in_another_paragraph_passes(self):
        status, output = verdict(added("- The whole-line rule also rests on Entry 62."))
        self.assertEqual(status, 0, output)
        self.assertIn(PINS_PRESENT, output)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    sys.exit(0 if result.wasSuccessful() else 1)
