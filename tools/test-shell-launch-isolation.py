#!/usr/bin/env python3
"""Check the Python words and .py tokens in the workflows' tools/*.sh for -I.

tools/test-workflow-launch-isolation.py reads the run text of the workflows.
This scan reads the shell scripts that run text starts: every tools/<name>.sh
named in a step's run text, and every tools/<name>.sh that a covered script
names in a line the rules read, until no new script is found.

Threat model: honest drift, as in the workflow scan. An author who sets out to
run python without -I can also edit this scan.

The rules, applied to each line of a covered script that the scan reads, with
the joins this docstring names (a finding names the first line of the joined
line). Outside a here-document body, a line that ends in a backslash joins the
next, and a comment line, one whose first character other than a space or tab
is #, is not read; the rules also read a comment after a command. A comment,
on a line of its own or after a command, ends at its line even when it ends
in a backslash, as in bash, so it joins no line:

1. Every word that names a Python interpreter, a lower-case `python` or `pypy`
   with any digits and dots after it, no dot straight before it and no letter,
   digit, underscore or hyphen straight after those, starts `python3 -I `
   (single spaces), directly after the start of the line, a space, a tab, a
   quote, a backquote, or one of ( | & ; !. The word straight after
   `command -v ` or `command -V ` is not read, since those print where a name
   resolves and run nothing. So `python3 -I tools/<name>.py`, `python3 -I -c`,
   `python3 -I -`, `command -v python3` and a grep pattern that names the
   isolated form pass, and `python3 tools/x.py`, `python3 -c`, `python3.12`,
   `pypy3`, `"python3" -I`, `${PYTHON:-python3}`, `$bin/python3`, `ipython3`
   and `python3 -X utf8` are findings. The `python` in docs.python.org or in
   tools/check-python-version.py is not such a word.
2. Every token whose text ends in a literal .py or .pyz, with no letter,
   digit, underscore, dot or hyphen after it, is a finding unless it ends the
   program word of text on the same line that reads as a python3 -I launch:
   the first word after `python3 -I `, any options (a hyphen and letters, or
   -X or -W and the word after it) and a `--` that ends them, where a word may
   hold quoted parts with no space or tab inside them, so
   `python3 -I -X utf8 tools/x.py` and `python3 -I -- tools/x.py` pass and
   `python3 -I "$(dirname "$0")/x.py"` is a finding. The rules read text, not
   what runs. Rule 2 reads such a token inside quotes, a command substitution
   or other text, so `"$here"/x.py`, `bash -c 'tools/x.py'`, `$PY tools/x.py`
   and an argument after the program, such as a path that a `-c` or `-`
   program reads, are findings. A .py or .pyz name spelt with quoting, a
   backslash, a glob or a brace inside its suffix holds no such token;
   Residuals names it with the other known misses. Text that reads as a launch
   passes even when nothing runs it, as in
   `grep -Fc 'python3 -I tools/x.py' f`; a .py path that a line names in any
   other text, as in cp, test -f, an echo or another grep pattern, is a
   finding until an exception names that line. LAUNCHERS names each shell
   function that runs its arguments through a python3 -I launch, that launch,
   and the lines of its script that may name the arguments as data. In
   tools/pages-build.sh, gate runs its arguments as the launch
   `python3 -I "$@"`, so a .py path that is the first word after a gate that
   starts a line of that script is the program of that launch; the 6 gate
   lines of that script pass rule 2 this way. The scan counts the definitions
   of the function in the forms `name()`, `name ()`, `function name` and
   `function name()`, wherever the body starts, in the script as it stands and
   with each backslash-newline removed, and gives a finding unless each count
   is exactly 1 and the definition is `name() {` on a line of its own with a
   body, up to the first line that is `}` alone, that holds a line starting
   with the launch. Each line of the script that uses the arguments ("$@",
   "$*", "$1" to "$9", the same unquoted, or a ${...} expansion of one of
   them) must start with the launch and use them nowhere after it, or be 1 of
   the named data lines, each of which must match exactly 1 line; any other
   such line is a finding, so a second launch of the arguments, such as a body
   line `"$@"`, fails. The scan reads every line of the script for that rule,
   since it does not parse where the body ends. It does not read a definition
   whose name is spelt with quoting or a backslash, a header split across
   lines other than by a backslash-newline, a definition built at run time
   (eval, a sourced file, or text written and then run) or an alias, an
   argument reached in another way, such as `${!i}` or BASH_ARGV, nor the
   function removed, or otherwise made not to be the function the scan checks,
   between its definition and a call, as `unset -f gate` before the first gate
   call does, after which each gate line runs whatever gate resolves to
   through PATH. tools/test-pages-build.py pins the SHA-256 of
   tools/pages-build.sh (SCRIPT_SHA256), so any edit of that script, such as
   that unset line, fails that test as well.

The scan recognizes a here-document operator, << or <<-, outside $((...)) and
((...)), where << is a shift, and reads the delimiter word after it as bash
does: a word of any characters but a space, a tab and | & ; ( ) < >, not
starting with #, whose quoted parts, '...', "...", $'...', $"..." and a
backslash before a character, lose their quotes. A word with any quoted part,
as in <<'X', <<"X" or a word with a backslash before any of its characters, is
a quoted delimiter. The body of a here-document whose opening the scan
recognizes is read as bash reads it. Bash expands the body of a here-document
whose delimiter is unquoted (<<X): $(...) and backquotes run, a # in the body
is text, not a comment, and a backslash-newline is removed. So every line of
such a body is read, # lines included, and a line of it that ends in an odd
number of backslashes joins the next, as in bash, before the scan looks for
the delimiter. A quoted delimiter leaves the body literal, so each line of it
is read as it stands, # lines included, with no join, unless it is the first
here-document that its opening line opens after a `python3 -I` launch with `-`
as the program, so that the body is the program that launch reads and is not
read. An unquoted body is never skipped. The opening line is always read, and
the line that ends a here-document, its delimiter alone after any join, is
not. A here-document operator or a `python3 -I -` launch inside quotes or a
comment is text: it opens no here-document and skips no body. When a line
opens no here-document and leaves a single quote open, and that quote follows
`python3 -I` options ending in `-c`, the lines up to the next one holding a
single quote are the program of that -c launch and are not read; of that next
line, only the text after its first single quote is read. No other line is
skipped. Whether a quote is left open follows the shell's rules for single
quotes, double quotes, $'...', a backslash, a $(...) inside double quotes, and
a # that starts a comment, so an apostrophe inside double quotes opens
nothing.

EXCEPTIONS names each line that breaks a rule on purpose, with its file, a
pattern that the whole stripped line must match (an entry holds 1 pattern for
each line it names, built with literal() from that line), the stripped opening
lines of the here-documents with a quoted delimiter that it may sit in (none
means outside any here-document), and the reason. Before it reads a script, the
scan checks that each pattern matches exactly as many of the stripped lines
that it reads in the pattern's file as the table lists that pattern for that
file, so each listing stands for exactly 1 line; a line whose stripped text
occurs twice in its file is listed twice. A pattern that excuses no line that
breaks a rule is also a finding, so the table cannot keep a pattern for a line
that is gone. EXPECTED_SCRIPTS names the scripts the discovery must find, so a
change that stops the discovery from reaching one is a finding.

Residuals: the scan misses a launch in the ways below, which are the known
misses and not a complete list. A launch on a line the scan does not read: a
comment line, the program of a `python3 -I -c` or `python3 -I -` launch named
above, which holds Python and not shell, and a line that a shell runs but that
the scan takes for such a program or a comment, since the scan reads shell as
text and can misjudge where a quote, a comment or a here-document ends.
Examples of that misjudgement: a case pattern inside $(...), which misleads the
quote reading; a here-document with a quoted delimiter that a later command on
the line of a `python3 -I -` launch opens; a line that starts with # inside a
string that spans lines, which the scan skips as a comment though bash runs a
$(...) in it (`msg="`, then `# $(python3 tools/x.py)`, then `"`); a delimiter
with a $'...' part that holds a backslash escape, which bash decodes and the
scan does not; and a delimiter with a quoted part that spans lines, which the
scan does not read as a delimiter. A launch that names neither a word rule 1
reads nor a .py or .pyz token: an interpreter held in a variable
(`"$real_py" -c`) or reached through a function or alias, an interpreter whose
name rule 1 does not read, such as jython or graalpy, an interpreter name in
other letter cases or with a letter or hyphen after its digits (`python3m`), a
python word spelt with quoting, a backslash or a brace inside it (`pyth''on3`,
`pytho{n3,}`), a .py or .pyz name spelt with quoting, a backslash, a glob or a
brace inside its suffix, which bash runs by its shebang (`tools/x.p''y`,
`tools/x.p"y"`, `tools/x.p?`, `tools/x.{py,}`), a script run by its shebang
whose name does not end in .py or .pyz, such a word or token split by a
backslash-newline in a body with a quoted delimiter that a shell runs
(`bash <<'X'`), which the scan does not join, and text built at run time. A
launch from Python, such as subprocess with sys.executable. A launch in a
script that a workflow step or a covered script reaches only through a variable
or a path the discovery does not match. For each <name>.sh that the text names,
the discovery queues tools/<name>.sh and nothing else, so it does not read a
script outside tools/ or in a subdirectory of it, such as one that a step runs
as `bash scripts/build.sh`, or a script whose name does not end in .sh; and for
scripts/<name>.sh, or another path whose base name is <name>.sh, it reads
tools/<name>.sh when that file exists, not the script that runs. The cost of
the rules is false findings: a line that names a .py or .pyz token or an
interpreter word in text that does not read as a python3 -I launch, such as a
message, a cp, grep or test operand, a comment after a command, a URL
(`github.com/python/cpython`), a word such as cpython, a here-document body
that no shell runs or a line inside a quoted string that spans lines, is a
finding until an exception names it, and so is a correct launch with an option
that the scan does not read as one, such as an option joined to a value that is
not all letters (`python3 -I -Xutf8 tools/x.py`) or a long option, and a
correct launch with blanks other than 1 space around its -I
(`python3  -I tools/x.py`, or a tab after -I) or with no blank after its -I, as
at the end of a line or before a `)` (`cmd | python3 -I`,
`x="$(cmd | python3 -I)"`), since rule 1 passes a python word only where it
starts `python3 -I ` with 1 space before and after the -I.

Usage: python3 -I tools/test-shell-launch-isolation.py
Exit status: 0 when every check passes, 1 on any finding or failure.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML is required to read the workflows")
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent

EXPECTED_SCRIPTS = (
    "tools/check-portable-text-sync.sh",
    "tools/ci-status.sh",
    "tools/pages-build.sh",
    "tools/release-dry-run.sh",
    "tools/release-package.sh",
    "tools/test-ci-status.sh",
    "tools/test-portable-text-release-date.sh",
    "tools/test-version-selectors.sh",
)

# (file, shell function, the launch line its body must hold, the whole stripped lines of the script that may
# name the function's arguments as data without starting with the launch): the function runs its arguments
# through that python3 -I launch, so a .py path that is its first argument is that launch's program.
LAUNCHERS = (
    ("tools/pages-build.sh", "gate", 'python3 -I "$@"', (
        'if [ ! -f "$1" ]; then',
        'echo "pages-build: gate $1 is missing; failing the build." >&2',
        'echo "pages-build: python3 -I $*"',
        'echo "pages-build: $1 failed with exit ${status}; failing the build." >&2',
    )),
)


def literal(*lines: str) -> tuple[str, ...]:
    """Return a whole-line pattern for each of the given stripped lines."""
    return tuple(re.escape(line) for line in lines)


# (file, a tuple of patterns, 1 for each whole stripped line that the entry names, opening lines of the quoted
# here-documents it may sit in, reason). A line whose stripped text occurs twice in its file is listed twice.
EXCEPTIONS = (
    ("tools/pages-build.sh",
     literal('echo "pages-build: Python 3.11 or later is required (tomllib); found $(python3 --version 2>&1)." >&2'),
     (), "python3 --version prints the interpreter version and runs no script"),
    ("tools/pages-build.sh", literal('echo "pages-build: $(python3 --version 2>&1)"'), (),
     "python3 --version prints the interpreter version and runs no script"),
    ("tools/test-portable-text-release-date.sh",
     literal(
         'python3 -X utf8 tools/skill-release-date.py --baseline',
         'tools/skill-release-date.py --baseline',
         'tools/skill-release-date.py --baseline',
         '"${PYTHON:-python3}" tools/skill-release-date.py --baseline',
         '"python3" tools/skill-release-date.py --baseline',
         'python3 tools/skill-release-date-client.py baseline',
         '"python3" -I tools/skill-release-date-client.py baseline',
         'python3 -X utf8 tools/skill-release-date-client.py baseline',
         'tools/skill-release-date-client.py baseline',
         'tools/skill-release-date-client.py baseline',
         '"${PYTHON:-python3}" -I tools/skill-release-date-client.py baseline',
     ),
     ("""cat > "${launch_probes}" <<'PROBES'""", """cat > "${client_probes}" <<'CLIENTPROBES'"""),
     "launch forms written to a fixture file that the test appends to a copy of the sync gate and expects "
     "its mention check to refuse; the shell does not run them"),
    ("tools/test-version-selectors.sh",
     literal('''got="$(grep -Ec 'python3( -I)? tools/skill-version\\.py' "${site}" || true)"'''), (),
     "a grep pattern that counts the lines that hold python3 tools/skill-version.py or python3 -I "
     "tools/skill-version.py; the shell does not run it"),
    ("tools/test-ci-status.sh",
     literal(
         'cat > "$bin/python3" <<PY',
         'chmod +x "$bin/python3" ;;',
         'cat > "$tmp/swapbin/python3" <<PY',
         'chmod +x "$tmp/swapbin/python3"',
     ),
     (), "writes and marks executable a stand-in python3 that a case puts first on PATH"),
    ('tools/check-portable-text-sync.sh',
     literal(
         'echo "tools/skill-release-date.py gave an unexpected answer (${out:-nothing}) for the Released line of $1." >&2',
         'echo "tools/skill-release-date.py is unavailable or crashed (exit ${rc}) reading $1, so its Released line could not be checked." >&2',
         'echo "tools/skill-release-date.py is unavailable or broken (probe exit ${prc}), so the Released lines could not be checked." >&2',
         '11) echo "tools/skill-release-date.py rejected the version ${sv} as malformed: ${requirement}" >&2; return 1 ;;',
         'echo "tools/skill-release-date.py is unavailable or crashed (exit ${prc}) deciding whether ${sv} needs a Released line." >&2',
         'echo "tools/skill-release-date.py gave an unexpected answer (${requirement:-nothing}) for whether ${sv} needs a Released line." >&2',
     ),
     (),
     'an error message that names the extractor; the line runs no Python'),
    ('tools/ci-status.sh',
     literal(
         '(trap "" PIPE; printf "ci-status: cannot find ci-status.py beside the real ci-status.sh (%s)\\n" "${BASH_SOURCE[0]:-}" >&2) || :',
         '(trap "" PIPE; printf "ci-status: cannot find ci-status.py beside the real ci-status.sh (%s)\\n" "${BASH_SOURCE[0]:-}" >&2) || :',
         'declare __ci_status_src="${BASH_SOURCE[0]:-}" || __ci_status_refuse err "ci-status: cannot find ci-status.py beside the real ci-status.sh ()"',
         'declare __ci_status_find="ci-status: cannot find ci-status.py beside the real ci-status.sh ($__ci_status_src)" ||',
         '__ci_status_refuse err "ci-status: cannot find ci-status.py beside the real ci-status.sh ($__ci_status_src)"',
         '__ci_status_refuse err "ci-status: cannot read ci-status.py beside the real ci-status.sh ($__ci_status_src)"',
         '[ ! -f "${__ci_status_here}ci-status.py" ] || [ -L "${__ci_status_here}ci-status.py" ] ||',
     ),
     (),
     'an error message that names ci-status.py, or the test that it is a regular file and not a symlink; the line runs no Python'),
    ('tools/release-dry-run.sh',
     literal(
         '0) [[ "${probe}" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+$ ]] || fail "tools/skill-release-date.py is unavailable or broken (probe exit 0)" ;;',
         'fail "tools/skill-release-date.py is unavailable or broken (probe exit ${probe_rc})"',
         '*) fail "tools/skill-release-date.py is unavailable or crashed (exit ${stamped_rc}) reading the stamped SKILL.md" ;;',
     ),
     (),
     'an error message that names the extractor; the line runs no Python'),
    ('tools/release-package.sh',
     literal(
         'fail "tools/skill-release-date.py is unavailable or broken (probe exit ${probe_rc}), so the Released line could not be checked"',
         '[[ "${checked}" == "${release_date}" ]]         || fail "tools/skill-release-date.py gave an unexpected answer (${checked:-nothing}) checking --release-date ${release_date}"',
         'fail "tools/skill-release-date.py is unavailable or crashed (exit ${check_rc}) checking --release-date ${release_date:-nothing}"',
         '[[ "${released}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]       || fail "tools/skill-release-date.py gave an unexpected answer (${released:-nothing}) for the Released line of cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD"',
         'fail "tools/skill-release-date.py is unavailable or crashed (exit ${released_rc}) reading the Released line of cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD"',
         '11) fail "tools/skill-release-date.py rejected the version ${version} as malformed: ${requirement}" ;;',
         'fail "tools/skill-release-date.py is unavailable or crashed (exit ${req_rc}) deciding whether ${version} needs a Released line"',
         '*) fail "tools/skill-release-date.py gave an unexpected answer (${requirement:-nothing}) for whether ${version} needs a Released line" ;;',
     ),
     (),
     'an error message that names the extractor; the line runs no Python'),
    ('tools/test-ci-status.sh',
     literal(
         'if [ "$(grep -c -F "_actions_job(\\"$job\\")" "${here}/ci-status.py")" != 1 ]; then why="$why declared"; fi',
         'cp "${here}/ci-status.sh" "${here}/ci-status.py" "$tools/"',
         'printf "raise SystemExit(7)\\n" > "$tmp/shadow/json.py"',
         'ln -s "$tools/ci-status.py" "$tmp/elsewhere/ci-status.py"',
         'run_contract_case "symlinked wrapper in another directory runs the real ci-status.py" 0 "$C1" owner/name owner/name - "wraplink pwd first" "$C1"',
         'case " $resolve " in *" nopy "*) ;; *) cp "${here}/ci-status.py" "$tools/" ;; esac',
         'printf "import pathlib\\npathlib.Path(\\"%s\\").touch()\\n" "$tmp/planted-ran" > "$cwd/ci-status.py"',
         'ln -s "$cwd/ci-status.py" "$tools/ci-status.py"',
         'cp "$cwd/ci-status.py" "$tmp/other/ci-status.py"',
         '*" noread "*) chmod 000 "$tools/ci-status.py" ;;',
         'local msg="ci-status: cannot find ci-status.py beside the real ci-status.sh" msgfile="$tmp/err"',
         '*" noread "*) msg="ci-status: cannot read ci-status.py beside the real ci-status.sh" ;;',
         'run_wrapper_case "normal path runs the real gate, not a planted ./ci-status.py" 0 -',
         'run_wrapper_case "failing readlink does not run a planted ./ci-status.py" 0 noreadlink',
         'run_wrapper_case "wrapper with no ci-status.py beside it fails closed with exit 3" 3 nopy',
         'run_wrapper_case "symlinked ci-status.py beside a copied wrapper fails closed with exit 3" 3 pylink',
         'run_wrapper_case "unreadable ci-status.py fails closed with exit 3" 3 noread',
         'run_wrapper_case "hard link to the wrapper beside a planted ci-status.py fails closed with exit 3" 3 hardlink',
         'run_wrapper_case "$opt: wrapper with no ci-status.py beside it fails closed with exit 3" 3 "$opt nopy"',
         'run_wrapper_case "$opt: symlinked ci-status.py beside a copied wrapper fails closed with exit 3" 3 "$opt pylink"',
         'run_wrapper_case "$opt: unreadable ci-status.py fails closed with exit 3" 3 "$opt noread"',
     ),
     (),
     'names ci-status.py or a planted .py file as a case description, an expected message, or an operand of grep, cp, ln, chmod or a printf redirection; no .py token on the line is a launch'),
    ('tools/test-ci-status.sh',
     literal(
         '"${here}/ci-status.py" > /dev/null 2>&1 || import_got=$?',
         '"${here}/ci-status.py" "$C1" > /dev/null 2>&1 || got=$?',
         '"${here}/ci-status.py" "$C1" "$mode" "$tmp/own" > "$tmp/out" 2> "$tmp/err" || got=$?',
         '"${here}/ci-status.py" "$C1" "$flag" "$tmp/own" > "$tmp/out" 2> "$tmp/err" || got=$?',
         '"${here}/ci-status.py" "$C1" > "$tmp/out" 2> "$tmp/err" || got=$?',
         '"${here}/ci-status.py" "$C1" > "$tmp/out" 2> "$tmp/err" || got=$?',
     ),
     (),
     'the path is an argument of a python3 -I -c program whose closing quote is on the line, or on the line '
     'before it, which ends in a backslash that joins the 2; that program loads and runs the file in its '
     'isolated interpreter'),
    ('tools/test-ci-status.sh',
     literal(
         '% (show(starts), show(deadlines), show(gh_deadlines), show(kills), show(returns), now()))\'     '
         '"${here}/ci-status.py" "$C1" "$tmp" "$left" "$starts" "$killed" "$frozen" > "$tmp/out" 2> "$tmp/err" '
         '|| got=$?',
         '% (show(deadlines), show(gh_deadlines), show(kills), show(returns), clock()))\'     '
         '"${here}/ci-status.py" "$C1" "$tmp" > "$tmp/out" 2> "$tmp/err" || got=$?',
         'finish(code, why, "reads at %s, killed at %s, exit at %.6f" % (show(starts), show(kills), now()))\'     '
         '"${here}/ci-status.py" 0000000000000000000000000000000000000000 "$tmp" "$plan" "$@" > "$tmp/out" '
         '2> "$tmp/err" || got=$?',
     ),
     (),
     'the last line of the text of a python3 -I -c program, made of "$FAKE_CLOCK_GATE" and a single-quoted '
     'part, ends in that part\'s closing quote and a backslash that joins the next line, which names the path '
     'as an argument of the program; the scan reads the program as shell, since the variable stands between '
     '-c and the quote, and the program loads and runs the file in its isolated interpreter'),
    ('tools/test-portable-text-release-date.sh',
     literal(
         'for t in check-portable-text-sync.sh build-portable-text.py skill-version.py skill-release-date.py skill-release-date-client.py       portable-text-skill-source.sha256 build-site.py check-install-page.py sitemap-config.json; do',
         'expect_fail_line "an undated version with a 4301-digit part relays the extractor reason"   "tools/skill-release-date.py rejected the version ${long_version} as malformed: skill-release-date: a part of the version has more than 4300 digits: \'${long_version}\'"',
         'rm -f "${work}/tools/skill-release-date.py"',
         'expect_fail "a missing extractor is reported as unavailable" "tools/skill-release-date.py is unavailable or broken"',
         'printf \'def broken(:\\n\' > "${work}/tools/skill-release-date.py"',
         'expect_fail "a broken extractor is reported as unavailable" "tools/skill-release-date.py is unavailable or broken"',
         'expect_fail "an extractor internal error is reported as a crash" "tools/skill-release-date.py is unavailable or crashed (exit 16)"',
         'expect_fail_without "a broken extract reply (${mode}) is reported as unavailable"     "tools/skill-release-date.py is unavailable or crashed (exit 16) reading ${skill}, so its Released line could not be checked."     "Malformed Released"',
         'expect_fail_without "a broken requires_release_date reply (${mode}) is reported as unavailable"     "tools/skill-release-date.py is unavailable or crashed (exit 16) deciding whether 1.0.14 needs a Released line."     "rejected the version"',
         'expect_fail "the client reason is relayed at the ${op} call"     "skill-release-date-client: skill-release-date.py exited 1 in ${op}, so the extractor is unavailable"',
         'mv "${work}/tools/skill-release-date-client.py" "${work}/tools/real-client.py"',
         'cat > "${work}/tools/skill-release-date-client.py" <<\'PYCLIENT\'',
         'expect_fail "a value that is not a bare day is not used"   "tools/skill-release-date.py gave an unexpected answer (2026-11-15"',
         'expect_fail_without "a broken extract reply is reported as unavailable (${mode})"     "tools/skill-release-date.py is unavailable or crashed (exit 16) reading ${skill}, so its Released line could not be checked."     "Malformed Released"',
         'rm -f "${work}/tools/skill-release-date-client.py"',
         'expect_fail "a missing client is reported as unavailable" "tools/skill-release-date.py is unavailable or broken (probe exit 2)"',
         'grep -F -- "skill-release-date.py" "$1" | cmp -s - "${allowed_mentions}"',
         'grep -F -- "skill-release-date-client.py" "$1" | cmp -s - "${allowed_client}"',
     ),
     (),
     'names the extractor, the client or the files a for loop copies with cp, as an expected message, a loop word, '
     'an operand of cp, rm, mv, grep or a redirection, or a grep pattern; no .py token on the line is a launch'),
    ('tools/test-portable-text-release-date.sh',
     literal(
         'python3 -I - "${work}/tools/skill-release-date.py" "$1" "$2" <<"PYBREAK"',
         'python3 -I - "${work}/tools/skill-release-date.py" <<"PYCRASH"',
     ),
     (),
     'the extractor path is an argument of the python3 -I - program that the here-document holds'),
    ('tools/test-portable-text-release-date.sh',
     literal(
         '# return 1. The one shared strict extractor, tools/skill-release-date.py, does',
         'echo "tools/skill-release-date.py gave an unexpected answer (${out:-nothing}) for the Released line of $1." >&2',
         'echo "tools/skill-release-date.py is unavailable or crashed (exit ${rc}) reading $1, so its Released line could not be checked." >&2',
         'echo "tools/skill-release-date.py is unavailable or broken (probe exit ${prc}), so the Released lines could not be checked." >&2',
         '11) echo "tools/skill-release-date.py rejected the version ${sv} as malformed: ${requirement}" >&2; return 1 ;;',
         'echo "tools/skill-release-date.py is unavailable or crashed (exit ${prc}) deciding whether ${sv} needs a Released line." >&2',
         'echo "tools/skill-release-date.py gave an unexpected answer (${requirement:-nothing}) for whether ${sv} needs a Released line." >&2',
         '# the reading, run in its --json mode by tools/skill-release-date-client.py',
     ),
     ('cat > "${allowed_mentions}" <<\'ALLOWED\'', 'cat > "${allowed_client}" <<\'ALLOWEDCLIENT\''),
     "the expected mention lines written to a fixture file that the test compares with the gate's lines; the shell does not run them"),
    ('tools/test-portable-text-release-date.sh',
     literal(
         'real = os.path.join(os.path.dirname(os.path.abspath(__file__)), "real-client.py")',
     ),
     ('cat > "${work}/tools/skill-release-date-client.py" <<\'PYCLIENT\'',),
     'a line of the Python stand-in client written to a file, which names the real client; the shell does not run it'),
    ('tools/test-version-selectors.sh',
     literal(
         'assert_eq "structural: skill-version.py call count in ${site}" "${skillver_count[$site]}" "${got}"',
         'assert_eq "structural: isolated skill-version.py call count in ${site}" "${skillver_count[$site]}" "${got}"',
         'cp tools/skill-version.py "${repo}/tools/skill-version.py"',
         'cp tools/skill-version.py "${dir}/tools/skill-version.py"',
         'cp tools/skill-version.py "${local_repo}/tools/skill-version.py"',
     ),
     (),
     'names tools/skill-version.py in a check description or as an operand of cp; the line runs no Python'),
)

SCRIPT_NAME = re.compile(r"([\w.-]+)\.sh(?![\w.-])")
# A python or pypy after a dot is part of a name, such as docs.python.org. One after a letter is
# still read, so that ipython3 is a finding: a false finding is safer than a silent pass.
PYTHON_WORD = re.compile(r"(?<!\.)(?:python|pypy)[0-9.]*(?![\w-])")
ISOLATED = "python3 -I "
LAUNCH_BEFORE = set(" \t(|&;!`\"'")
AFTER_LAUNCH_BEFORE = r"(?<![^ \t(|&;!`\"'])"
# command -v and command -V print where a name resolves and run nothing.
LOOKUP = re.compile(AFTER_LAUNCH_BEFORE + r"command -[vV] $")
# A token whose text ends in a literal .py or .pyz, inside quotes or not. A suffix spelt with quoting, a
# backslash, a glob or a brace, such as .p''y or .p?, is not one, so the scan does not read it.
PY_PATH = re.compile(r"\.pyz?(?![\w.-])")
# A shell word, quoted parts included. A quoted part may not hold a space or tab, so a word that
# the match starts inside a string cannot run on through the string's closing quote to a later path.
WORD = r"((?:\"[^\"\s]*\"|'[^'\s]*'|[^\s\"';&|<>()`])+)"


def options(sep: str) -> str:
    """Return a pattern for the option words of a launch, each followed by sep.

    An option is -X or -W with its value word, or a hyphen and letters. A -X or -W followed by
    a space or tab is read only with its value, so that value is never taken for the program.
    """
    value = WORD.replace("(", "(?:", 1)
    return r"(?:(?:-[XW]" + sep + value + r"|-(?![XW][ \t])[A-Za-z]+)" + sep + r")*"


# The program word of python3 -I launch text: the first word after its options and a -- that ends them.
PROGRAM = re.compile(AFTER_LAUNCH_BEFORE + r"python3 -I[ \t]+" + options(r"[ \t]+") + r"(?:--[ \t]+)?" + WORD)
INTERPRETER_REASON = "python or pypy word that does not start python3 -I"
PATH_REASON = ".py path that does not end the program word of python3 -I launch text"
# A here-document operator and the blanks after it; heredoc_word reads the delimiter word that follows.
HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*")
# The characters that end an unquoted shell word.
WORD_END = set(" \t|&;()<>")
# A python3 -I launch that reads its program from a here-document on standard input.
STDIN_PROGRAM = re.compile(AFTER_LAUNCH_BEFORE + r"python3 -I " + options(" ") + r"(?:-- )?-(?=\s|$)")
# The text before a single quote that opens the program of a python3 -I -c launch.
C_PROGRAM = re.compile(AFTER_LAUNCH_BEFORE + r"python3 -I " + options(" ") + r"-c $")


def line_findings(line: str, launchers: tuple[str, ...] = ()) -> list[str]:
    """Return the rules one shell line breaks, given the names of the launcher functions of its script."""
    found = []
    for match in PYTHON_WORD.finditer(line):
        at = match.start()
        if LOOKUP.search(line[:at]):
            continue
        if not line.startswith(ISOLATED, at) or (at and line[at - 1] not in LAUNCH_BEFORE):
            found.append(INTERPRETER_REASON)
            break
    # A .py path passes only where it ends its launch's program word, before any closing quotes.
    starts = [PROGRAM] + [re.compile(r"^[ \t]*" + re.escape(name) + r"[ \t]+" + WORD) for name in launchers]
    programs = {m.start(1) + len(m.group(1).rstrip("\"'")) for start in starts for m in start.finditer(line)}
    if any(m.end() not in programs for m in PY_PATH.finditer(line)):
        found.append(PATH_REASON)
    return found


def open_single_quote(line: str) -> int | None:
    """Return where a single quote that the line leaves open starts, or None."""
    stack, _ = quote_state(line)
    return stack[-1][1] if stack and stack[-1][0] == "'" else None


def comment_start(line: str) -> int | None:
    """Return where a comment on the line starts, or None."""
    return quote_state(line)[1]


def outside_quotes(line: str, at: int) -> bool:
    """Return whether the text at offset at stands outside every quote and comment."""
    stack, comment = quote_state(line[:at])
    return comment is None and (not stack or stack[-1][0] == "(")


def quote_state(line: str) -> tuple[list[tuple[str, int]], int | None]:
    """Return the quotes and parentheses the line leaves open, and where a comment starts, or None."""
    stack: list[tuple[str, int]] = []
    i = 0
    while i < len(line):
        c = line[i]
        state = stack[-1][0] if stack else "("
        if state == "'":
            if c == "'":
                stack.pop()
        elif c == "\\":
            i += 1
        elif state == "$'":
            if c == "'":
                stack.pop()
        elif state == '"':
            if c == '"':
                stack.pop()
            elif line.startswith("$(", i):
                stack.append(("(", i))
                i += 1
        elif c == "#" and (i == 0 or line[i - 1] in " \t;&|()"):
            return stack, i
        elif line.startswith("$'", i):
            stack.append(("$'", i))
            i += 1
        elif c in "'\"(":
            stack.append((c, i))
        elif c == ")" and stack:
            stack.pop()
        i += 1
    return stack, None


def heredoc_word(line: str, i: int) -> tuple[str, bool] | None:
    """Return (delimiter, quoted) for the delimiter word at offset i, or None when no word starts there.

    Bash removes the quotes from the word and leaves the body literal when any part of it is quoted.
    A $'...' part is kept as it stands, though bash decodes its backslash escapes.
    """
    if i >= len(line) or line[i] in WORD_END or line[i] == "#":
        return None
    out: list[str] = []
    quoted = False
    while i < len(line) and line[i] not in WORD_END:
        c = line[i]
        if c == "\\":
            if i + 1 == len(line):
                return None
            out.append(line[i + 1])
            quoted = True
            i += 2
        elif c == "'" or line.startswith("$'", i):
            start = i + (2 if c == "$" else 1)
            end = line.find("'", start)
            if end < 0:
                return None
            out.append(line[start:end])
            quoted = True
            i = end + 1
        elif c == '"' or line.startswith('$"', i):
            i += 2 if c == "$" else 1
            while i < len(line) and line[i] != '"':
                if line[i] == "\\" and i + 1 < len(line) and line[i + 1] in '$`"\\':
                    i += 1
                out.append(line[i])
                i += 1
            if i == len(line):
                return None
            quoted = True
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out), quoted


def in_arithmetic(line: str, at: int) -> bool:
    """Return whether offset at lies inside ((...)) or $((...)), where << is a shift."""
    stack, _ = quote_state(line[:at])
    opens = [p for kind, p in stack if kind == "("]
    return any(line[a:b + 1] in ("((", "$((") for a, b in zip(opens, opens[1:]))


def heredoc_openers(line: str) -> list[tuple[int, str, bool, bool]]:
    """Return (offset, delimiter, strips tabs, quoted) for each here-document the line opens."""
    found = []
    for m in HEREDOC.finditer(line):
        # An operator inside quotes or a comment is text, so it opens no here-document.
        if not outside_quotes(line, m.start()) or in_arithmetic(line, m.start()):
            continue
        word = heredoc_word(line, m.end())
        if word is not None:
            found.append((m.start(), word[0], m.group(1) == "-", word[1]))
    return found


def ends_in_join(line: str) -> bool:
    """Return whether an unquoted here-document line ends in a backslash that escapes its newline."""
    return (len(line) - len(line.rstrip("\\"))) % 2 == 1


def script_lines(text: str):
    """Yield (line number, line, None or (here-document opening line, delimiter quoted)) for each line read."""
    lines = text.split("\n")
    heredocs: list[tuple[str, bool, bool, bool, str]] = []
    in_program = False
    i = 0
    while i < len(lines):
        line = lines[i]
        number = i + 1
        i += 1
        if heredocs:
            delim, strip_tabs, quoted, skip, opener = heredocs[0]
            # Bash expands an unquoted body: it joins each backslash-newline before it looks for
            # the delimiter, and a # in the body starts no comment, so every line is read.
            while not quoted and ends_in_join(line) and i < len(lines):
                line = line[:-1] + lines[i]
                i += 1
            if (line.lstrip("\t") if strip_tabs else line) == delim:
                heredocs.pop(0)
            elif not skip:
                yield number, line, (opener, quoted)
            continue
        if in_program:
            if "'" not in line:
                continue
            in_program = False
            # The quote ends the program, so only the shell text after it is read.
            line = line.split("'", 1)[1]
        # Bash does not continue a comment, so a backslash that ends one joins no line.
        while line.endswith("\\") and i < len(lines) and comment_start(line) is None:
            line = line[:-1] + lines[i]
            i += 1
        if line.lstrip(" \t").startswith("#"):
            continue
        yield number, line, None
        shell_text = line
        # A launch inside quotes or a comment is text, so its here-document is not its program.
        openers = heredoc_openers(shell_text)
        stdin = next((m for m in STDIN_PROGRAM.finditer(shell_text) if outside_quotes(shell_text, m.start())), None)
        first = next((o for o in openers if stdin and o[0] > stdin.start()), None)
        # Only a quoted body is literal, so only a quoted body can be skipped as the program.
        heredocs += [(o[1], o[2], o[3], o is first and o[3], shell_text.strip()) for o in openers]
        quote = open_single_quote(shell_text)
        if not openers and quote is not None and C_PROGRAM.search(shell_text[:quote]):
            in_program = True


def discover(root: Path) -> tuple[list[str], list[str]]:
    """Return (covered scripts, findings) from the workflows' run text."""
    findings: list[str] = []
    queue: list[str] = []
    workflows = sorted((root / ".github" / "workflows").glob("*.yml"))
    if not workflows:
        findings.append("no workflow found")
    for path in workflows:
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            findings.append(f"{path.relative_to(root)}: cannot be read ({exc})")
            continue
        jobs = doc.get("jobs") if isinstance(doc, dict) else None
        for job in (jobs or {}).values():
            for step in (job.get("steps") or []) if isinstance(job, dict) else []:
                run = step.get("run") if isinstance(step, dict) else None
                if isinstance(run, str):
                    queue += [f"tools/{m.group(1)}.sh" for m in SCRIPT_NAME.finditer(run)
                              if (root / "tools" / f"{m.group(1)}.sh").is_file()]
    covered: list[str] = []
    while queue:
        rel = queue.pop(0)
        if rel in covered:
            continue
        covered.append(rel)
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(f"{rel}: cannot be read ({exc})")
            continue
        for _, line, _ in script_lines(text):
            queue += [f"tools/{m.group(1)}.sh" for m in SCRIPT_NAME.finditer(line)
                      if (root / "tools" / f"{m.group(1)}.sh").is_file()]
    return sorted(covered), findings


# A use of a function's arguments: $@, $*, $1 to $9, quoted or not, or a ${...} expansion of one of them.
ARGUMENT = re.compile(r"\$(?:[@*1-9]|\{[#!]?[@*1-9])")


def definition_header(name: str) -> re.Pattern[str]:
    """Return a pattern for a definition header of the function name in each form that the scan reads.

    The forms are name(), name (), function name and function name(), with any blanks inside the
    parentheses; the body may start on the same line or a later one, so the header alone is counted.
    """
    n = re.escape(name)
    return re.compile(r"(?<![\w.:-])(?:function[ \t]+" + n + r"(?:[ \t]*\([ \t]*\))?|" + n
                      + r"[ \t]*\([ \t]*\))(?![\w.:-])")


def launcher_problems(text: str, name: str, launch: str, data: tuple[str, ...]) -> list[str]:
    """Return why the script does not hold the launcher function name as LAUNCHERS describes it."""
    problems = []
    header = definition_header(name)
    counts = (len(header.findall(text)), len(header.findall(text.replace("\\\n", ""))))
    if counts != (1, 1):
        problems.append(f"{name} has {counts[0]} definitions, or {counts[1]} with each backslash-newline "
                        f"removed, not exactly 1")
    bodies = re.findall(r"^" + re.escape(name) + r"\(\) \{\n(.*?)^\}$", text, re.M | re.S)
    if len(bodies) != 1 or not any(re.match(re.escape(launch) + r"(?: |$)", body_line.strip())
                                   for body_line in bodies[0].splitlines()):
        problems.append(f"{name}() is not defined as `{name}() {{` on a line of its own with a body line "
                        f"that starts {launch}")
    lines = [line.strip() for line in text.split("\n")]
    # The scan does not parse where the body ends, so it reads every line of the script for this rule.
    for number, line in enumerate(lines, 1):
        if not ARGUMENT.search(line) or line in data:
            continue
        rest = line[len(launch):] if line.startswith(launch) else None
        if rest is None or not (rest == "" or rest.startswith(" ")) or ARGUMENT.search(rest):
            problems.append(f"line {number} uses the arguments of {name} other than once, at its start, "
                            f"as {launch}: {line[:100]}")
    problems += [f"the data line {line!r} of {name} matches {lines.count(line)} lines, not exactly 1"
                 for line in data if lines.count(line) != 1]
    return problems


def table_findings(root: Path, exceptions) -> list[str]:
    """Return a finding for each exception pattern that does not match as many lines as the table lists it.

    The count is of the stripped lines that the scan reads in the pattern's file, so each listing of a
    pattern stands for exactly 1 line of the tree.
    """
    listed: dict[tuple[str, str], int] = {}
    for path, group, _, _ in exceptions:
        for pattern in (group,) if isinstance(group, str) else group:
            listed[(path, pattern)] = listed.get((path, pattern), 0) + 1
    read: dict[str, list[str]] = {}
    findings = []
    for (path, pattern), want in listed.items():
        if path not in read:
            try:
                read[path] = [line.strip() for _, line, _ in script_lines((root / path).read_text(encoding="utf-8"))]
            except (OSError, UnicodeDecodeError):
                read[path] = []
        got = sum(1 for line in read[path] if re.fullmatch(pattern, line))
        if got != want:
            findings.append(f"{path}: the exception for {pattern!r} matches {got} lines that the scan reads, "
                            f"not {want}")
    return findings


def scan_tree(root: Path, expected=EXPECTED_SCRIPTS, exceptions=EXCEPTIONS,
              launchers=LAUNCHERS) -> tuple[list[str], list[str]]:
    """Return (findings, covered scripts)."""
    findings = table_findings(root, exceptions)
    covered, discovered = discover(root)
    findings += discovered
    findings += [f"{rel}: a script the workflows run that the discovery did not reach"
                 for rel in expected if rel not in covered]
    findings += [f"{path}: the launcher {name} is in no covered script" for path, name, _, _ in launchers
                 if path not in covered]
    patterns = [(pattern,) if isinstance(pattern, str) else pattern for _, pattern, _, _ in exceptions]
    used = [[False] * len(group) for group in patterns]
    for rel in covered:
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        names = tuple(name for path, name, _, _ in launchers if path == rel)
        findings += [f"{rel}: {problem}" for path, name, launch, data in launchers if path == rel
                     for problem in launcher_problems(text, name, launch, data)]
        for number, line, heredoc in script_lines(text):
            reasons = line_findings(line, names)
            if not reasons:
                continue
            excused = False
            for n, (path, _, openers, _) in enumerate(exceptions):
                inside = heredoc is not None and heredoc[1] and heredoc[0] in openers
                if path != rel or not (inside if openers else heredoc is None):
                    continue
                for k, pattern in enumerate(patterns[n]):
                    if re.fullmatch(pattern, line.strip()):
                        used[n][k] = excused = True
            if not excused:
                findings += [f"{rel}:{number}: {reason}: {line.strip()[:100]}" for reason in reasons]
    findings += [f"{path}: the exception for {pattern!r} matches no line"
                 for (path, _, _, _), group, hits in zip(exceptions, patterns, used)
                 for pattern, hit in zip(group, hits) if not hit]
    return findings, covered


# ---------------------------------------------------------------- self-tests

# Shell lines that must be refused (True) or must pass (False).
LINE_CASES = [
    ("python3 tools/x.py", True),
    ("python3 -c 'print(1)'", True),
    ('python3 - "$1" <<\'PY\'', True),
    ("x=$(git show HEAD:f | python3 tools/x.py)", True),
    ('"python3" -I tools/x.py', True),
    ('"${PYTHON:-python3}" -I tools/x.py', True),
    ('cat > "$bin/python3" <<PY', True),
    ("python3 -X utf8 tools/x.py", True),
    ("python3  -I tools/x.py", True),
    ("ipython3 -I tools/x.py", True),
    ("python3 --version", True),
    ("python3.12 -I tools/x.py", True),
    ("pypy3 tools/x.py", True),
    ("pypy -c 1", True),
    ("python3 -I tools/x.py; python3.12 -c 1", True),
    ("tools/x.py --check", True),
    ("env A=b tools/x.pyz", True),
    ('"$here"/x.py --check', True),
    ('"$(dirname "$0")/x.py" --check', True),
    ("bash -c 'tools/x.py --check'", True),
    ('sh -c "tools/x.py --check"', True),
    ("$PY tools/x.py", True),
    ("echo `tools/x.py`", True),
    ("python3 -I tools/x.py; tools/y.py", True),
    ("python3 -I tools/x.py tools/y.py", True),
    ("python3 -I -X utf8 tools/x.py tools/y.py", True),
    ("python3 -I -X tools/y.py", True),
    ("python3 -I -Xutf8 tools/x.py", True),
    ("python3 -I -c 'print(1)' tools/x.py", True),
    ('python3 -I - tools/x.py <<\'PY\'', True),
    ('python3 -I "$(tools/x.py)"', True),
    ("gate tools/x.py", True),
    ("gate=tools/x.py", True),
    ('cp tools/x.py "${dir}/tools/x.py"', True),
    ("grep -c foo tools/x.py", True),
    ("test -f tools/x.py", True),
    ('fail "tools/x.py is unavailable"', True),
    ("command -v python3 && python3 -c 1", True),
    ("python3 -I tools/check-python-version.py", False),
    ('echo "see https://docs.python.org/3/"', False),
    ("test -f .python-version && python3 -I tools/x.py", False),
    ("nice -n 5 python3 -I tools/x.py", False),
    ("env -i python3 -I tools/x.py", False),
    ("python3 -I tools/x.py", False),
    ("python3 -I -B tools/x.pyz --check", False),
    ("python3 -I -X utf8 tools/x.py", False),
    ("python3 -I -W error tools/x.py", False),
    ("python3 -I -- tools/x.py", False),
    ("python3 -I -B -X dev -- tools/x.py --check", False),
    ("python3 -I -c 'print(1)'", False),
    ('python3 -I - "$1" <<\'PY\'', False),
    ("x=$(git show HEAD:f | python3 -I tools/x.py)", False),
    ('entry=(python3 -I "$tmp/x.py")', False),
    ('exec python3 -I "${here}x.py" "$@"', False),
    ('python3 -I "$(dirname "$0")/x.py" --check', True),
    ('sh -c "python3 -I a; $0" "tools/x.py"', True),
    ('python3 -I "$(dirname -- "$0")"', False),
    ('PATH="$bin:$PATH" python3 -I -B -c "$launch"', False),
    ('echo "pages-build: python3 -I $*"', False),
    ("grep -Fc 'python3 -I tools/x.py' f", False),
    ("PYTHONPATH=x bash tools/a.sh", False),
    ("echo Python 3.11 is required", False),
    ("command -v python3 >/dev/null", False),
    ('real_py="$(command -v python3)"', False),
    ('case "${tag}" in', False),
]

# Lines of a script whose launcher function is gate, which must be refused (True) or must pass (False).
LAUNCHER_CASES = [
    ("gate tools/x.py", False),
    ('  gate "tools/x.py" --check', False),
    ("gate x tools/y.py", True),
    ("echo gate tools/x.py", True),
    ("true; gate tools/x.py", True),
]

# The definition of gate in tools/pages-build.sh and a call of it, which must hold as LAUNCHERS describes.
GATE = '''gate() {
  if [ ! -f "$1" ]; then
    echo "pages-build: gate $1 is missing; failing the build." >&2
    exit 3
  fi
  echo "pages-build: python3 -I $*"
  python3 -I "$@" || {
    status=$?
    echo "pages-build: $1 failed with exit ${status}; failing the build." >&2
    exit "${status}"
  }
}

gate tools/check-baseline-pin.py
'''
LAUNCH_LINE = '  python3 -I "$@" || {\n'
# Scripts with gate, each of which must give a launcher finding (True) or none (False).
GATE_CASES = [
    (GATE, False),
    (GATE.replace("\n\ngate tools/", '\ngate() { "$1"; }\n\ngate tools/'), True),
    (GATE.replace("\n\ngate tools/", '\nfunction gate {\n  "$@"\n}\n\ngate tools/'), True),
    (GATE.replace(LAUNCH_LINE, '  "$@"\n' + LAUNCH_LINE), True),
    (GATE.replace("\n\ngate tools/", "\ngate () { :; }\n\ngate tools/"), True),
    (GATE.replace("\n\ngate tools/", "\nfunction gate() { :; }\n\ngate tools/"), True),
    (GATE.replace("\n\ngate tools/", "\ngate()\n{\n  :\n}\n\ngate tools/"), True),
    (GATE.replace("\n\ngate tools/", "\ngate \\\n() { :; }\n\ngate tools/"), True),
    (GATE.replace("gate() {\n", "function gate {\n"), True),
    (GATE.replace(LAUNCH_LINE, '  python3 -I "$@" || $1 || {\n'), True),
    (GATE.replace(LAUNCH_LINE, "  ${@:1}\n" + LAUNCH_LINE), True),
    (GATE.replace(LAUNCH_LINE, "  x=$1\n" + LAUNCH_LINE), True),
    (GATE.replace("    exit 3\n", '    echo "$1" >&2\n    exit 3\n'), True),
    (GATE.replace('  echo "pages-build: python3 -I $*"\n', ""), True),
]

P = INTERPRETER_REASON
Y = PATH_REASON
# (script text, wanted findings as (line number, reason)).
SCRIPT_CASES = [
    ("# python3 tools/x.py\necho ok\n", []),
    ("python3 -I \\\n  tools/x.py\n", []),
    ("python3 \\\n  -I tools/x.py\n", [(1, P), (1, Y)]),
    ("python3 -I - <<'PY'\nimport x\nrun('python3 y.py')\nPY\npython3 -c 1\n", [(5, P)]),
    ("cat > f <<'EOF'\npython3 -c 1\nEOF\n", [(2, P)]),
    ("cat > f <<-EOF\n\tpython3 -c 1\n\tEOF\npython3 -c 1\n", [(2, P), (4, P)]),
    ("python3 -I -c '\nimport os\nos.system(\"python3 y.py\")\n' \"$f\"\n", []),
    ("python3 -I -c '\nprint(1)\n' tools/x.py\n", [(3, Y)]),
    ("python3 -I -c '\nprint(1)' \\\n  \"$f\" && python3 -c 1\n", [(2, P)]),
    ("read -r a <<<\"$b\"\npython3 -c 1\n", [(2, P)]),
    ("echo \"python3 -I can't be skipped\"\npython3 -c 1\n", [(2, P)]),
    ("python3 -I x.py # it's read\npython3 -c 1\n", [(2, P)]),
    ("python3 -I x.py; bash -c '\npython3 -c 1\n'\n", [(2, P)]),
    ("v=\"$(python3 -I -c '\nimport os\nos.system(\"python3 y.py\")\n')\"\n", []),
    ("cat > \"$b/python3\" <<PY\npython3 -c 1\nPY\n", [(1, P), (2, P)]),
    ("python3 -I tools/x.py <<EOF\npython3 -c 1\nEOF\n", [(2, P)]),
    ("python3 -I -B - \"$1\" <<\"PY\"\nimport x\nPY\n", []),
    ("python3 -I -X utf8 -- - <<'PY'\nrun('python3 y.py')\nPY\npython3 -c 1\n", [(4, P)]),
    ("python3 -I -W error -c '\nos.system(\"python3 y.py\")\n' \"$f\"\n", []),
    ("echo \"usage: python3 -I - <<EOF\"\npython3 -c 1\n", [(2, P)]),
    ("echo 'python3 -I - <<EOF'\npython3 -c 1\n", [(2, P)]),
    ("true # python3 -I - <<EOF\npython3 -c 1\n", [(2, P)]),
    ("echo \"python3 -I - \" <<EOF\npython3 -c 1\nEOF\n", [(2, P)]),
    ("# note \\\npython3 -c 1\n", [(2, P)]),
    ("# note \\\ntools/x.py\n", [(2, Y)]),
    ("echo x # note \\\ntools/x.py\n", [(2, Y)]),
    ("python3 -I \\\n  x.py # note \\\npython3 -c 1\n", [(3, P)]),
    ("python3 -I - <<EOF\nprint(\"$(python3 -c 1)\")\nEOF\n", [(2, P)]),
    ("python3 -I - <<EOF\nprint(\"`tools/x.py`\")\nEOF\n", [(2, Y)]),
    ("python3 -I - <<'EOF'\nprint(\"$(python3 tools/x.py)\")\nEOF\n", []),
    ("cat > /dev/null <<EOF\n# generated by $(python3 -c 1)\nEOF\n", [(2, P)]),
    ("cat > /dev/null <<EOF\n# generated by `tools/x.py`\nEOF\n", [(2, Y)]),
    ("cat > /dev/null <<EOF\n$(pyth\\\non3 -c 1)\nEOF\n", [(2, P)]),
    ("cat <<EOF\nEO\\\nF\npython3 -c 1\n", [(4, P)]),
    ("cat <<EOF\nc\\\\\nEOF\npython3 -c 1\n", [(4, P)]),
    # Each quoted delimiter form leaves the body literal, so the body is read as it stands and
    # opens nothing, and the line after the delimiter is read.
    ("cat > /dev/null <<\\EOF\npython3 -c 1\npython3 -I - <<'PY'\nEOF\npython3 tools/x.py\nPY\n",
     [(2, P), (5, P), (5, Y)]),
    ("cat > /dev/null <<'END-X'\npython3 -c 1\npython3 -I - <<'PY'\nEND-X\npython3 tools/x.py\nPY\n",
     [(2, P), (5, P), (5, Y)]),
    ("cat > /dev/null <<\"END.X\"\npython3 -c 1\npython3 -I - <<'PY'\nEND.X\npython3 tools/x.py\nPY\n",
     [(2, P), (5, P), (5, Y)]),
    ("cat > /dev/null <<E\\OF\npython3 -c 1\npython3 -I - <<'PY'\nEOF\npython3 tools/x.py\nPY\n",
     [(2, P), (5, P), (5, Y)]),
    ("cat > /dev/null <<E\"O\"F; true\n$(python3 -c 1)\nEOF\npython3 -c 1\n", [(2, P), (4, P)]),
    ("python3 -I - <<\\PY\nrun('python3 y.py')\nPY\npython3 -c 1\n", [(4, P)]),
    ("python3 -I - <<$'PY'\nrun('python3 y.py')\nPY\npython3 -c 1\n", [(4, P)]),
    ("python3 -I - <<''\nrun('python3 y.py')\n\npython3 -c 1\n", [(4, P)]),
    ("cat <<-\"A\\\"B\"\n\tpython3 -c 1\n\tA\"B\npython3 -c 1\n", [(2, P), (4, P)]),
    # An unquoted delimiter may hold other characters; its body is expanded and read.
    ("cat <<$Z\n# $(python3 -c 1)\n$Z\npython3 -c 1\n", [(2, P), (4, P)]),
    ("cat <<1\n`tools/x.py`\n1\npython3 -c 1\n", [(2, Y), (4, P)]),
    # A << inside ((...)) or $((...)) is a shift and opens no here-document.
    ("(( y = 1 << 2 ))\npython3 -I - <<'PY'\nrun('python3 y.py')\nPY\npython3 -c 1\n", [(5, P)]),
    ("echo \"$((1<<2))\"\npython3 -I - <<'PY'\nrun('python3 y.py')\nPY\npython3 -c 1\n", [(5, P)]),
]


def self_test() -> list[str]:
    errors: list[str] = []
    for line, want in LINE_CASES:
        if bool(line_findings(line)) != want:
            errors.append(f"self-test: line {line!r}: expected {'a finding' if want else 'none'}")
    for line, want in LAUNCHER_CASES:
        if bool(line_findings(line, ("gate",))) != want:
            errors.append(f"self-test: line {line!r} with launcher gate: expected {'a finding' if want else 'none'}")
    _, name, launch, data = LAUNCHERS[0]
    for text, want in GATE_CASES:
        if bool(launcher_problems(text, name, launch, data)) != want:
            errors.append(f"self-test: gate script {text!r}: expected {'a finding' if want else 'none'}")
    for text, want in SCRIPT_CASES:
        got = [(n, reason) for n, line, _ in script_lines(text) for reason in line_findings(line)]
        if got != want:
            errors.append(f"self-test: script {text!r}: expected {want!r}, got {got!r}")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / "tools").mkdir()
        (root / ".github" / "workflows" / "w.yml").write_text(
            "on: push\njobs:\n  j:\n    steps:\n      - run: bash tools/a.sh\n", encoding="utf-8")
        (root / "tools" / "a.sh").write_text("#!/usr/bin/env bash\n# tools/c.sh\n# a comment ends at its line, backslash or not \\\ntools/b.sh\n", encoding="utf-8")
        (root / "tools" / "b.sh").write_text("python3 -I tools/x.py\nprobe=$(python3 --version)\n", encoding="utf-8")
        (root / "tools" / "c.sh").write_text("python3 tools/x.py\n", encoding="utf-8")
        exception = (("tools/b.sh", r"probe=\$\(python3 --version\)", (), "r"),)
        findings, covered = scan_tree(root, ("tools/a.sh", "tools/b.sh"), exception, ())
        if covered != ["tools/a.sh", "tools/b.sh"] or findings:
            errors.append(f"self-test: discovery gave {covered!r} and {findings!r}")
        findings, _ = scan_tree(root, ("tools/a.sh", "tools/c.sh"), exception, ())
        if not any("tools/c.sh: a script the workflows run" in f for f in findings):
            errors.append("self-test: an expected script the discovery missed gave no finding")
        findings, _ = scan_tree(root, ("tools/a.sh",), (), ())
        if not any(f.startswith(f"tools/b.sh:2: {P}") for f in findings):
            errors.append("self-test: a line outside the exceptions gave no finding")
        findings, _ = scan_tree(root, ("tools/a.sh",), exception + (("tools/b.sh", r"gone", (), "r"),), ())
        if not any("matches no line" in f for f in findings):
            errors.append("self-test: an exception that matches no line gave no finding")
        grouped = (("tools/b.sh", literal("probe=$(python3 --version)", "gone"), (), "r"),)
        findings, _ = scan_tree(root, ("tools/a.sh",), grouped, ())
        if findings != ["tools/b.sh: the exception for 'gone' matches 0 lines that the scan reads, not 1",
                        "tools/b.sh: the exception for 'gone' matches no line"]:
            errors.append(f"self-test: a stale line in an entry of several lines gave {findings!r}")
        # Each listing of a pattern stands for exactly 1 line that the scan reads in its file.
        twice = (("tools/b.sh", literal("probe=$(python3 --version)", "probe=$(python3 --version)"), (), "r"),)
        for text, table, want in (("probe=$(python3 --version)\n", exception, []),
                                  ("probe=$(python3 --version)\nprobe=$(python3 --version)\n", exception, [2]),
                                  ("probe=$(python3 --version)\nprobe=$(python3 --version)\n", twice, []),
                                  ("probe=$(python3 --version)\n", twice, [1]),
                                  ("true\n", exception, [0])):
            (root / "tools" / "b.sh").write_text(text, encoding="utf-8")
            got = [int(f.split(" matches ")[1].split()[0]) for f in table_findings(root, table)]
            if got != want:
                errors.append(f"self-test: the table check on {text!r} gave counts {got!r}, expected {want!r}")
        (root / "tools" / "b.sh").write_text("python3 -I tools/x.py\nprobe=$(python3 --version)\n", encoding="utf-8")
        in_heredoc = (("tools/b.sh", r"probe=\$\(python3 --version\)", ("cat > f <<'EOF'",), "r"),)
        findings, _ = scan_tree(root, ("tools/a.sh",), in_heredoc, ())
        if not any(f.startswith("tools/b.sh:2:") for f in findings):
            errors.append("self-test: an exception for a here-document excused a line outside it")
        for opener, want in (("cat > f <<'EOF'", False), ("bash <<'EOF'", True), ("cat > f <<EOF", True)):
            (root / "tools" / "b.sh").write_text(f"{opener}\nprobe=$(python3 --version)\nEOF\n", encoding="utf-8")
            findings, _ = scan_tree(root, ("tools/a.sh",), in_heredoc, ())
            if any(f.startswith("tools/b.sh:2:") for f in findings) != want:
                errors.append(f"self-test: in a here-document that {opener!r} opens, the exception gave {findings!r}")
        launcher = (("tools/b.sh", "gate", 'python3 -I "$@"', ()),)
        for body, want in (('  python3 -I "$@" || exit 1', False), ('  "$@" || exit 1', True),
                           ('  python3 -I "$1"', True)):
            (root / "tools" / "b.sh").write_text(f"gate() {{\n{body}\n}}\ngate tools/x.py --check\n", encoding="utf-8")
            findings, _ = scan_tree(root, ("tools/a.sh",), (), launcher)
            if bool(findings) != want:
                errors.append(f"self-test: a gate body {body!r} gave {findings!r}")
        findings, _ = scan_tree(root, ("tools/a.sh",), (), ())
        if not any(f.startswith(f"tools/b.sh:4: {Y}") for f in findings):
            errors.append("self-test: gate in a script that names no launcher gave no finding")
        findings, _ = scan_tree(root, ("tools/a.sh",), (), (("tools/gone.sh", "gate", 'python3 -I "$@"', ()),))
        if not any("is in no covered script" in f for f in findings):
            errors.append("self-test: a launcher in no covered script gave no finding")
    return errors


def main() -> int:
    errors = self_test()
    if errors:
        for error in errors:
            print(error)
        print(f"FAIL: {len(errors)} self-test failure(s)")
        return 1
    findings, covered = scan_tree(REPO)
    for finding in findings:
        print(finding)
    if findings:
        print(f"FAIL: {len(findings)} finding(s) in {len(covered)} shell scripts")
        return 1
    print(f"OK: {len(covered)} tools/*.sh scripts found from the workflows' run text; each python or pypy word "
          f"and each .py or .pyz token on a line the scan reads stands in text that reads as a python3 -I launch, "
          f"or the token is the first word after a call, at the start of a line, of a function that LAUNCHERS "
          f"names and checks ({len(LAUNCHERS)} in all), apart from the lines its {len(EXCEPTIONS)} exceptions name")
    return 0


if __name__ == "__main__":
    sys.exit(main())
