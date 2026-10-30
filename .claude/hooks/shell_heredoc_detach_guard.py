#!/usr/bin/env python3
"""shell_heredoc_detach_guard: an adopter-owned PreToolUse Bash hook for this repository.

Owner and scope. This file is adopter-owned: it sits under .claude/hooks/, outside every path listed in
.aiqt/pin.toml [vendored], and is the local compensating control for the heredoc lifting reduction of the
items 38 and 40 re-vendor. The upstream orch_truncation_guard (rule trkasy, track-launched-work) lifts a
single ampersand that sits in the body of a here-document under a quoted delimiter, including a body fed to a shell, so a
command that runs bash on a quoted here-document whose body ends a line with a single ampersand (sleep 100
followed by the ampersand) detaches a child the foreground call does not track, and the vendored guard
allows it (upstream discloses this residual). This hook denies exactly that shape and nothing else.

What it denies. A command that feeds a here-document under a quoted delimiter (the delimiter word in single
or double quotes or behind a backslash, with the plain or the tab-stripping operator) to a shell
interpreter, where the body holds a backgrounding ampersand. The here-document is fed to a shell when the
command that carries it, or a later stage of the same pipeline, has as its command word sh, bash, dash, zsh
or ksh, with or without a directory path, after any leading assignments and reserved words and after the
wrappers env (with its options and assignments, and the words of env -S), command and exec. A pipeline goes
on past a newline that follows a pipe or the stderr pipe, as bash reads it, so a shell named on a later
line, after the body and any blank or comment lines, is a later stage of the same pipeline (a newline
after a double ampersand or a double bar likewise continues the command list, not the pipeline). A
backgrounding ampersand is a single ampersand that ends a command: not one of a double ampersand, not one
inside a redirection operator (descriptor duplication such as 2 to 1, or the combined stdout and stderr
redirections), not the stderr pipe, not a case fall-through terminator, and not one inside quotes or a
comment. Every further here-document inside such a body is judged as well, whatever its delimiter and at
any depth: the body of one under an unquoted delimiter is read for its expansions (command substitutions,
backquotes, and the substitutions inside parameter expansions), which the shell running the outer body
performs wherever that here-document is fed and whatever quotes stand around them in its body; and the
body of one fed to a shell, quoted or not, is read as commands, with its own further here-documents
judged the same way, recursively. An ampersand in the body of a quoted further here-document fed to a
command other than a shell is data. A body that holds no ampersand character at all is never parsed.

Two readers judge a body, and either one finding a backgrounding ampersand denies: this file's own small
lexer (Scanner, below), and the vendored hook's shared lexer, _lex_command in
plugin/aiqt-guardrails-hooks/hooks/scripts/aiqt_hooks.py, loaded by path with bytecode writing off, and
only when a body read as commands holds an ampersand. That lexer is a private function of the vendored
module, so a re-vendor can rename or change it; the hook then notes that the second reader was unavailable
and decides on its own reading, and the test suite fails until the import is repaired. The vendored lexer
refuses some bodies (an unquoted here-document, a here-string, a process substitution); the hook then
decides on its own reading and notes the refusal.

What it allows. Every other command, silently: every here-document fed to anything but a shell (cat, tee,
python, git commit -F -, the commit-message form that wraps cat in a command substitution), whatever
quotes or ampersands its body holds; a shell-fed here-document whose body holds only double ampersands,
redirections or quoted ampersands; and a top-level here-document under an unquoted delimiter, one that
no quoted shell-fed body holds (outside this hook; the vendored guard reads such a body and denies a bare
ampersand in it or in its command substitutions).

Fail-closed posture. When this hook cannot read a command or a body, it denies only where the targeted
shape may be present: the body of a shell-fed quoted here-document that holds an ampersand where its
own lexer cannot read that body or a here-document body nested in it, or the nesting runs deeper than
the bound; or a whole command it cannot read (or that is
longer than the size bound, or that raises an internal error) that holds a here-document operator, an
ampersand and a shell name as a word. Everywhere else it allows, with a note when the command held a
here-document operator.

RESIDUAL (disclosed; this guard is best-effort and does not cover every way to detach a child):
  1. Interpreter recognition is by the written command word only. A shell reached through a variable
     (such as SHELL), an alias or function, another wrapper (sudo, nohup, nice, timeout, xargs, setsid,
     ssh, busybox), another shell name (ash, mksh, yash), a subshell group as a later pipeline stage, a
     group or subshell that carries the here-document, a process substitution, or eval, source or the dot
     command reading the body is not seen.
  2. Detachers that carry no single ampersand (setsid, nohup without one, disown, coproc, a nested
     bash -c string inside the body) are not seen.
  3. The lexer is a best-effort reading of bash, not a guarantee: case patterns inside a command
     substitution, extended globs, single quotes inside a parameter expansion within double quotes, ANSI-C
     escapes and arithmetic can be read differently from bash. A misreading can hide an ampersand (a
     silent allow) or invent one (an over-refusal).
  4. Inside a command substitution or backquotes a body ends at a line that starts with the delimiter
     followed by a closing parenthesis, as bash 5.3 reads it; an older bash reads further lines as body,
     and an ampersand in those lines is not judged.
  5. Over-refusal: a shell-fed here-document is denied whatever the shell arguments, so bash -c with a
     command string, bash with a script operand, and a here-document on a descriptor other than 0 are
     denied when the body holds a backgrounding ampersand, although that body is then not read as
     commands. The remedy is to run the job in the foreground or through the tracked background dispatch.
  6. An unreadable hook payload (not JSON, or no command string) is allowed with a note; the vendored
     trkasy guard denies such a payload.
  7. The vendored lexer adds denies only, and reads only bodies read as commands; where it is absent,
     renamed or refuses a body (it refuses every body that holds an unquoted here-document), coverage
     rests on this file lexer alone (noted on each such call). The expansions of an unquoted body are read
     by this file lexer alone.
  8. Text an expansion produces is not read: when an unquoted here-document body inside a shell-fed body
     is itself fed to a shell, a command substitution or parameter expansion in it can print text (a
     backgrounding ampersand among it) that the shell then runs as commands, and that text is not judged.
  9. A top-level here-document under an unquoted delimiter, outside every quoted shell-fed body, is not
     judged by this hook; it rests on the vendored trkasy guard, which reads such a body.

Launch with python3 -I. Plain ASCII, standard library only.
"""

import importlib.util
import json
import os
import re
import sys

# The three characters this lexer matches that are written once, here, as named constants.
AMP = "&"
APOS = "'"
BQ = "`"

SHELLS = frozenset(("sh", "bash", "dash", "zsh", "ksh"))
MAX_COMMAND = 1 << 20  # characters; a longer command is not lexed (fail-closed only on the targeted shape)
MAX_DEPTH = 16  # nesting of substitutions, backquotes and recursive body readings
VENDORED_REL = ("plugin", "aiqt-guardrails-hooks", "hooks", "scripts", "aiqt_hooks.py")
VENDORED_FUNC = "_lex_command"
HOOK = "shell_heredoc_detach_guard"

# Reserved words that may precede the command word of a simple command (time also takes -p).
RESERVED = frozenset(("!", "{", "if", "then", "else", "elif", "do", "while", "until", "time"))
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\[[^\]]*\])?\+?=")
FD_WORD = re.compile(r"[0-9]+|\{[A-Za-z_][A-Za-z0-9_]*\}")
WORD_BREAKS = frozenset(" \t\n;|<>()" + AMP)
DQ_ESCAPES = ("$", BQ, "\"", "\\")
# A shell name standing as a word, used only to decide whether an unreadable command may be the targeted
# shape (the fail-closed prefilter).
SHELL_TOKEN = re.compile(r"(?<![A-Za-z0-9_.-])(?:sh|bash|dash|zsh|ksh)(?![A-Za-z0-9_.-])")


class ParseError(ValueError):
    """This hook lexer cannot read the text."""


class Heredoc(object):
    __slots__ = ("delim", "quoted", "strip_tabs", "nest", "body", "terminated")

    def __init__(self, delim, quoted, strip_tabs, nest):
        self.delim, self.quoted, self.strip_tabs, self.nest = delim, quoted, strip_tabs, nest
        self.body, self.terminated = None, False


class Command(object):
    __slots__ = ("words", "heredocs")

    def __init__(self):
        self.words = []  # (decoded text, opaque) pairs, redirections absent
        self.heredocs = []


class _State(object):
    """The parse state of one command list: the command being read, its pipeline, and the word in hand."""
    __slots__ = ("cmd", "pipeline", "word", "opaque", "target", "cont")

    def __init__(self):
        self.cmd, self.pipeline = Command(), []
        self.word, self.opaque, self.target = None, False, False
        self.cont = False  # the last separator was a pipe, a double bar or a double ampersand

    def add(self, text):
        if self.word is None:
            self.word = []
        self.word.append(text)


class Scanner(object):
    """A small bash lexer, enough to find here-documents, their bodies, the simple commands and pipelines
    that carry them, and every single ampersand that ends a command (amps). It reads single and double
    quotes, backslash escapes, comments at a word start, command and arithmetic substitutions, parameter
    expansions, ANSI-C quotes, backquotes, process substitutions, here-strings and redirections. Bodies are
    read at the newline that ends the line of their operator, in operator order, at any nesting. It raises
    ParseError on an unclosed quote, substitution or parenthesis, on a malformed here-document delimiter,
    and past MAX_DEPTH."""

    def __init__(self, text, depth, nest=0):
        if depth > MAX_DEPTH:
            raise ParseError("a nesting deeper than {} levels".format(MAX_DEPTH))
        self.s, self.n, self.i = text, len(text), 0
        self.depth, self.base_nest = depth, nest
        self.pipelines = []  # lists of Command
        self.amps = 0
        self.pending = []

    def run(self):
        self.parse_list(None, self.base_nest)
        for hd in self.pending:  # an operator with no line after it: an empty, unterminated body
            hd.body, hd.terminated = "", False
        self.pending = []
        return self

    # -- command lists ---------------------------------------------------------------------------------
    def parse_list(self, stop, nest):
        s, st = self.s, _State()
        while self.i < self.n:
            c = s[self.i]
            if c in " \t":
                self.end_word(st)
                self.i += 1
            elif c == "\n":
                self.end_word(st)
                if not (st.cont and not st.cmd.words and not st.cmd.heredocs):
                    # a newline right after a pipe, a double bar or a double ampersand continues the
                    # pipeline or the list, as bash reads it; any other newline ends the command
                    self.end_command(st, "\n")
                self.i += 1
                self.read_bodies()
            elif c == "#" and st.word is None:
                j = s.find("\n", self.i)
                self.i = self.n if j < 0 else j
            elif c == "\\":
                if s[self.i + 1:self.i + 2] == "\n":
                    self.i += 2
                elif self.i + 1 < self.n:
                    st.add(s[self.i + 1])
                    self.i += 2
                else:
                    st.add("\\")
                    self.i += 1
            elif c == APOS:
                j = s.find(APOS, self.i + 1)
                if j < 0:
                    raise ParseError("an unclosed single quote")
                st.add(s[self.i + 1:j])
                self.i = j + 1
            elif c == "\"":
                self.i += 1
                st.add(self.read_dquote(st, nest))
            elif c == "$":
                st.add(self.read_dollar(st, nest, False))
            elif c == BQ:
                st.add(self.read_backquote())
                st.opaque = True
            elif c in "<>":
                self.read_angle(st, nest)
            elif c == AMP:
                nxt = s[self.i + 1:self.i + 2]
                self.end_word(st)
                if nxt == AMP:
                    self.end_command(st, AMP + AMP)
                    self.i += 2
                elif nxt == ">":
                    self.i += 3 if s[self.i + 2:self.i + 3] == ">" else 2
                    st.target = True
                else:
                    self.amps += 1
                    self.end_command(st, AMP)
                    self.i += 1
            elif c == "|":
                self.end_word(st)
                nxt = s[self.i + 1:self.i + 2]
                if nxt == "|":
                    self.end_command(st, "||")
                    self.i += 2
                else:
                    self.end_command(st, "|")
                    self.i += 2 if nxt == AMP else 1
            elif c == ";":
                self.end_word(st)
                op = ";"
                for cand in (";;" + AMP, ";;", ";" + AMP):
                    if s.startswith(cand, self.i):
                        op = cand
                        break
                self.end_command(st, op)
                self.i += len(op)
            elif c == "(":
                self.end_word(st)
                self.end_command(st, "(")
                self.i += 1
                self.parse_list(")", nest)
            elif c == ")":
                self.end_word(st)
                self.end_command(st, ")")
                self.i += 1
                if stop == ")":
                    return
                # a closing parenthesis with nothing open: a case pattern, read as a separator
            else:
                st.add(c)
                self.i += 1
        if stop is not None:
            raise ParseError("an unclosed parenthesis or substitution")
        self.end_word(st)
        self.end_command(st, "")

    def scan_expansions(self):
        """Read the text as the body of an unquoted here-document, as bash expands it: a backslash escapes
        only a dollar sign, a backquote, a backslash or a newline; a dollar sign starts a parameter,
        command or arithmetic expansion; a backquote starts a command substitution; quotes and every other
        character are literal. The command substitutions are read as command lists (amps, pipelines and
        here-documents, whose bodies come from the lines that follow, as bash reads them)."""
        s, st = self.s, _State()
        while self.i < self.n:
            c = s[self.i]
            if c == "\\":
                nxt = s[self.i + 1:self.i + 2]
                self.i += 2 if nxt and nxt in ("$", BQ, "\\", "\n") else 1
            elif c == "$":
                self.read_dollar(st, self.base_nest, True)
            elif c == BQ:
                self.read_backquote()
            elif c == "\n":
                self.i += 1
                self.read_bodies()
            else:
                self.i += 1
        for hd in self.pending:  # an operator with no line after it: an empty, unterminated body
            hd.body, hd.terminated = "", False
        self.pending = []
        return self

    def end_word(self, st):
        if st.word is None:
            return
        text = "".join(st.word)
        if st.target:
            st.target = False
        else:
            st.cmd.words.append((text, st.opaque))
        st.word, st.opaque = None, False

    def end_command(self, st, sep):
        st.target = False
        st.cont = sep in ("|", "||", AMP + AMP)
        if st.cmd.words or st.cmd.heredocs:
            st.pipeline.append(st.cmd)
        st.cmd = Command()
        if sep != "|" and st.pipeline:
            self.pipelines.append(st.pipeline)
            st.pipeline = []

    # -- here-documents --------------------------------------------------------------------------------
    def read_heredoc_op(self, st, nest):
        s, i = self.s, self.i + 2
        strip_tabs = s[i:i + 1] == "-"
        if strip_tabs:
            i += 1
        while i < self.n and s[i] in " \t":
            i += 1
        parts, quoted, started = [], False, False
        while i < self.n and s[i] not in WORD_BREAKS:
            c, started = s[i], True
            if c == APOS:
                j = s.find(APOS, i + 1)
                if j < 0:
                    raise ParseError("an unclosed quote in a here-document delimiter")
                parts.append(s[i + 1:j])
                quoted, i = True, j + 1
            elif c == "\"":
                j, buf = i + 1, []
                while j < self.n and s[j] != "\"":
                    if s[j] == "\\" and j + 1 < self.n and s[j + 1] in DQ_ESCAPES:
                        buf.append(s[j + 1])
                        j += 2
                    else:
                        buf.append(s[j])
                        j += 1
                if j >= self.n:
                    raise ParseError("an unclosed quote in a here-document delimiter")
                parts.append("".join(buf))
                quoted, i = True, j + 1
            elif c == "\\":
                if i + 1 >= self.n or s[i + 1] == "\n":
                    raise ParseError("a backslash ending a here-document delimiter")
                parts.append(s[i + 1])
                quoted, i = True, i + 2
            elif c == "$" and i + 1 < self.n and s[i + 1] in (APOS, "\""):
                raise ParseError("an ANSI-C or locale quote in a here-document delimiter")
            else:
                parts.append(c)
                i += 1
        if not started:
            raise ParseError("a here-document operator with no delimiter word")
        hd = Heredoc("".join(parts), quoted, strip_tabs, nest)
        st.cmd.heredocs.append(hd)
        self.pending.append(hd)
        self.i = i

    def read_bodies(self):
        s = self.s
        while self.pending:
            hd = self.pending.pop(0)
            lines = []
            while True:
                if self.i >= self.n:
                    hd.terminated = False
                    break
                j = s.find("\n", self.i)
                end = self.n if j < 0 else j
                line = s[self.i:end]
                cmp = line.lstrip("\t") if hd.strip_tabs else line
                if cmp == hd.delim:
                    self.i = self.n if j < 0 else j + 1
                    hd.terminated = True
                    break
                if (hd.nest > 0 and hd.delim and cmp.startswith(hd.delim)
                        and cmp[len(hd.delim):len(hd.delim) + 1] == ")"):
                    self.i += (len(line) - len(cmp)) + len(hd.delim)
                    hd.terminated = True
                    break
                lines.append(cmp)
                self.i = self.n if j < 0 else j + 1
            hd.body = "".join(line + "\n" for line in lines)

    # -- words -----------------------------------------------------------------------------------------
    def read_angle(self, st, nest):
        s, i = self.s, self.i
        st.cont = False
        if st.word is not None and not st.opaque and FD_WORD.fullmatch("".join(st.word)):
            st.word = None  # an fd number or {name} written against the operator belongs to the redirect
        self.end_word(st)
        if s.startswith("<<<", i):
            self.i, st.target = i + 3, True
        elif s.startswith("<<", i):
            self.read_heredoc_op(st, nest)
        elif s.startswith("<(", i) or s.startswith(">(", i):
            self.i = i + 2
            self.parse_list(")", nest + 1)
            st.add("")
            st.opaque = True
        else:
            op = s[i]
            for cand in (">>", ">|", ">" + AMP, "<" + AMP, "<>"):
                if s.startswith(cand, i):
                    op = cand
                    break
            self.i, st.target = i + len(op), True

    def read_dquote(self, st, nest):
        s, buf = self.s, []
        while self.i < self.n:
            c = s[self.i]
            if c == "\"":
                self.i += 1
                return "".join(buf)
            if c == "\\":
                nxt = s[self.i + 1:self.i + 2]
                if nxt == "\n":
                    self.i += 2
                elif nxt and nxt in DQ_ESCAPES:
                    buf.append(nxt)
                    self.i += 2
                else:
                    buf.append(c)
                    self.i += 1
            elif c == "$":
                buf.append(self.read_dollar(st, nest, True))
            elif c == BQ:
                buf.append(self.read_backquote())
                st.opaque = True
            else:
                buf.append(c)
                self.i += 1
        raise ParseError("an unclosed double quote")

    def read_dollar(self, st, nest, in_dquote):
        s, i = self.s, self.i
        nxt = s[i + 1:i + 2]
        if nxt == "(":
            self.i = i + 2
            self.parse_list(")", nest + 1)
            st.opaque = True
            return ""
        if nxt == "{":
            self.i = i + 2
            self.skip_brace(nest)
            st.opaque = True
            return ""
        if nxt == APOS and not in_dquote:
            self.i = i + 2
            st.opaque = True
            return self.read_ansi()
        if nxt == "\"" and not in_dquote:
            self.i = i + 2
            return self.read_dquote(st, nest)
        self.i = i + 1
        st.opaque = True
        return "$"

    def read_ansi(self):
        s, buf = self.s, []
        while self.i < self.n:
            c = s[self.i]
            if c == "\\":
                buf.append(s[self.i:self.i + 2])
                self.i += 2
            elif c == APOS:
                self.i += 1
                return "".join(buf)
            else:
                buf.append(c)
                self.i += 1
        raise ParseError("an unclosed ANSI-C quote")

    def skip_brace(self, nest):
        s, depth, dummy = self.s, 1, _State()
        while self.i < self.n:
            c = s[self.i]
            nxt = s[self.i + 1:self.i + 2]
            if c == "}":
                depth -= 1
                self.i += 1
                if depth == 0:
                    return
            elif c == "\\":
                self.i += 2
            elif c == APOS:
                j = s.find(APOS, self.i + 1)
                if j < 0:
                    raise ParseError("an unclosed single quote in a parameter expansion")
                self.i = j + 1
            elif c == "\"":
                self.i += 1
                self.read_dquote(dummy, nest)
            elif c == "$" and nxt == "{":
                depth += 1
                self.i += 2
            elif c == "$" and nxt == "(":
                self.i += 2
                self.parse_list(")", nest + 1)
            elif c == BQ:
                self.read_backquote()
            else:
                self.i += 1
        raise ParseError("an unclosed parameter expansion")

    def read_backquote(self):
        s, j, buf = self.s, self.i + 1, []
        while j < self.n:
            c = s[j]
            if c == "\\" and j + 1 < self.n and s[j + 1] in (BQ, "\\", "$"):
                buf.append(s[j + 1])
                j += 2
                continue
            if c == BQ:
                break
            buf.append(c)
            j += 1
        else:
            raise ParseError("an unclosed backquote")
        self.i = j + 1
        inner = Scanner("".join(buf), self.depth + 1, 1).run()
        self.pipelines.extend(inner.pipelines)
        self.amps += inner.amps
        return ""


# -- interpretation ------------------------------------------------------------------------------------
def shell_word(cmd):
    """The shell name a simple command runs as its command word (sh, bash, dash, zsh or ksh), after leading
    reserved words and assignments and the wrappers env, command and exec; else None. An opaque command
    word (one that carried an expansion) is not resolved (residual 1)."""
    words = list(cmd.words)
    k = 0
    while k < len(words):
        text, opaque = words[k]
        if not opaque and text in RESERVED:
            k += 1
            if text == "time" and k < len(words) and words[k][0] == "-p":
                k += 1
            continue
        if ASSIGNMENT.match(text):
            k += 1
            continue
        break
    while k < len(words):
        text, opaque = words[k]
        if opaque:
            return None
        name = text.rsplit("/", 1)[-1]
        if name == "env":
            k += 1
            while k < len(words):
                arg = words[k][0]
                if arg == "--":
                    k += 1
                    break
                if arg in ("-S", "--split-string") and k + 1 < len(words):
                    words[k + 1:k + 2] = [(w, words[k + 1][1]) for w in words[k + 1][0].split()]
                    k += 1
                elif arg.startswith("-S") and len(arg) > 2:
                    words[k:k + 1] = [(w, words[k][1]) for w in arg[2:].split()]
                elif arg in ("-u", "-C", "--unset", "--chdir"):
                    k += 2
                elif arg.startswith("-") or ASSIGNMENT.match(arg):
                    k += 1
                else:
                    break
            continue
        if name in ("command", "exec"):
            k += 1
            while k < len(words) and words[k][0].startswith("-"):
                k += 2 if (name == "exec" and words[k][0] == "-a") else 1
            continue
        return name if name in SHELLS else None
    return None


def heredoc_consumers(scanner):
    """Each (shell name or None, Heredoc) for every here-document the scanner read, quoted or not: the shell
    name when the command that carries it, or a later stage of its pipeline, runs a shell, else None."""
    for pipeline in scanner.pipelines:
        for k, cmd in enumerate(pipeline):
            if not cmd.heredocs:
                continue
            consumer = shell_word(cmd)
            if consumer is None:
                for later in pipeline[k + 1:]:
                    consumer = shell_word(later)
                    if consumer is not None:
                        break
            for hd in cmd.heredocs:
                yield consumer, hd


def shell_fed_heredocs(scanner):
    """Each (shell name, Heredoc) where a quoted-delimiter here-document of the command is fed to a shell.
    A top-level body under an unquoted delimiter is left to the vendored guard (residual 9)."""
    for consumer, hd in heredoc_consumers(scanner):
        if consumer is not None and hd.quoted:
            yield consumer, hd


_VENDORED = []  # memo: [function or None, reason]


def _repo_root():
    here = os.path.dirname(os.path.abspath(__file__))  # <root>/.claude/hooks
    return os.path.dirname(os.path.dirname(here))


def vendored_lexer():
    """The vendored hook module _lex_command, loaded by path once with bytecode writing off, or None and the
    reason it is unavailable."""
    if _VENDORED:
        return _VENDORED[0], _VENDORED[1]
    path = os.path.join(_repo_root(), *VENDORED_REL)
    func, reason = None, ""
    if not os.path.isfile(path):
        reason = "the vendored hook module {} is absent".format(path)
    else:
        sys.dont_write_bytecode = True
        try:
            spec = importlib.util.spec_from_file_location("_aiqt_vendored_for_" + HOOK, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            func = getattr(module, VENDORED_FUNC, None)
            if not callable(func):
                func, reason = None, "the vendored hook module has no {}".format(VENDORED_FUNC)
        except Exception as exc:  # the second reader only adds denies; its loss is noted
            func, reason = None, "the vendored hook module failed to load ({})".format(type(exc).__name__)
    _VENDORED[:] = [func, reason]
    return func, reason


def vendored_background(body, notes):
    """True when the vendored lexer reads a segment of body ended by a single ampersand; False when it reads
    none, refuses the body, or is unavailable (the last two noted). That lexer reads a case fall-through
    terminator (a semicolon, or two, written against an ampersand) as a semicolon separator followed by an
    empty segment ended by an ampersand; such an empty segment right after a semicolon separator is either
    that terminator or a bash syntax error, never a background job, so it is not counted."""
    func, reason = vendored_lexer()
    if func is None:
        notes.append(reason)
        return False
    try:
        segments = func(body)
    except ValueError:
        notes.append("the vendored lexer refused a shell-fed body")
        return False
    except Exception as exc:
        notes.append("the vendored lexer raised {}".format(type(exc).__name__))
        return False
    previous = None
    for seg in segments:
        sep = getattr(seg, "sep_after", None)
        if sep == AMP:
            empty = not getattr(seg, "argv", None) and not getattr(seg, "redirects", None)
            if not (empty and previous == ";"):
                return True
        previous = sep
    return False


def judge_scanned(inner, depth, notes):
    """(verdict, why) over a scanned text that a shell runs: a backgrounding ampersand in the text itself,
    or one in any here-document it carries. Every here-document counts, quoted or not: the expansions of
    an unquoted body run wherever that here-document is fed, and a body fed to a shell runs as commands."""
    if inner.amps:
        return "background", "this hook lexer"
    for consumer, hd in heredoc_consumers(inner):
        if not hd.quoted:
            verdict, why = judge_expansions(hd.body, depth + 1, notes)
            if verdict != "clean":
                return verdict, why
        if consumer is not None:
            verdict, why = judge_body(hd.body, depth + 1, notes)
            if verdict != "clean":
                return verdict, why
    return "clean", ""


def judge_body(body, depth, notes):
    """(background, reader), (error, why) or (clean, empty) for a here-document body a shell runs as
    commands."""
    if AMP not in body:
        return "clean", ""
    try:
        inner = Scanner(body, depth + 1).run()
    except ParseError as exc:
        return "error", str(exc)
    verdict, why = judge_scanned(inner, depth, notes)
    if verdict != "clean":
        return verdict, why
    if vendored_background(body, notes):
        return "background", "the vendored lexer"
    return "clean", ""


def judge_expansions(body, depth, notes):
    """(background, reader), (error, why) or (clean, empty) for the expansions of an unquoted here-document
    body inside a text a shell runs: its command substitutions, backquotes and the substitutions inside its
    parameter expansions run wherever the here-document is fed."""
    if AMP not in body:
        return "clean", ""
    try:
        inner = Scanner(body, depth + 1).scan_expansions()
    except ParseError as exc:
        return "error", str(exc)
    return judge_scanned(inner, depth, notes)


def may_be_target(command):
    """Whether an unreadable command may be the targeted shape: a here-document operator, an ampersand and a
    shell name as a word all appear in it."""
    return "<<" in command and AMP in command and SHELL_TOKEN.search(command) is not None


def _deny_reason(consumer, why):
    return ("Adopter hook {} (compensating control for rule trkasy, track-launched-work): this command feeds "
            "a quoted here-document to the shell {}, and the body holds a single ampersand that backgrounds "
            "a command (read by {}). The child runs detached from this foreground call, so its result and "
            "its failure are lost. Run the job in the foreground, or launch it through the tracked "
            "background dispatch (run_in_background).").format(HOOK, consumer, why)


def decide(command):
    """None (allow silently), (note, message) (allow with a note) or (deny, reason)."""
    if "<<" not in command:
        return None
    if len(command) > MAX_COMMAND:
        if may_be_target(command):
            return ("deny", "Adopter hook {}: this command is longer than {} characters and holds a "
                    "here-document, an ampersand and a shell name, so the hook cannot rule out a "
                    "shell-fed body that backgrounds a command (fail-closed). Split the command or write the "
                    "data to a file.".format(HOOK, MAX_COMMAND))
        return ("note", "Adopter hook {}: a command longer than {} characters was not read; allowed.".format(
            HOOK, MAX_COMMAND))
    try:
        scanner = Scanner(command, 0).run()
    except ParseError as exc:
        if may_be_target(command):
            return ("deny", "Adopter hook {}: this command holds a here-document, an ampersand and a shell "
                    "name, and the hook could not read it ({}), so it cannot rule out a shell-fed body that "
                    "backgrounds a command (fail-closed).".format(HOOK, exc))
        return ("note", "Adopter hook {}: could not read a command holding a here-document ({}); it "
                "cannot be the shell-fed shape this hook targets, so it is allowed.".format(HOOK, exc))
    notes = []
    for consumer, hd in shell_fed_heredocs(scanner):
        verdict, why = judge_body(hd.body, 0, notes)
        if verdict == "background":
            return ("deny", _deny_reason(consumer, why))  # DENY-RULE
        if verdict == "error":
            return ("deny", "Adopter hook {}: this command feeds a quoted here-document holding an ampersand "
                    "to the shell {}, and the hook could not read the body ({}), so it cannot rule out a "
                    "backgrounding ampersand (fail-closed).".format(HOOK, consumer, why))
    if notes:
        return ("note", "Adopter hook {}: a shell-fed here-document body was judged by this hook lexer "
                "alone: {}.".format(HOOK, "; ".join(sorted(set(notes)))))
    return None


def _emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")
    sys.stdout.flush()


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except Exception as exc:
        _emit({"systemMessage": "Adopter hook {}: the hook payload could not be read ({}); allowed (the "
               "vendored trkasy guard judges an unreadable payload).".format(HOOK, type(exc).__name__)})
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        _emit({"systemMessage": "Adopter hook {}: the Bash payload carried no command string; allowed (the "
               "vendored trkasy guard judges an unreadable payload).".format(HOOK)})
        return 0
    try:
        outcome = decide(command)
    except Exception as exc:
        if may_be_target(command):
            outcome = ("deny", "Adopter hook {}: an internal error ({}) stopped the reading of a command that "
                       "holds a here-document, an ampersand and a shell name (fail-closed).".format(
                           HOOK, type(exc).__name__))
        else:
            outcome = ("note", "Adopter hook {}: an internal error ({}); allowed.".format(
                HOOK, type(exc).__name__))
    if outcome is None:
        return 0
    kind, message = outcome
    if kind == "note":
        try:
            _emit({"systemMessage": message})
        except Exception:
            pass
        return 0
    try:
        _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                      "permissionDecisionReason": message},
               "systemMessage": "Adopter hook {}: denied a shell-fed here-document whose body backgrounds a "
                                "command, or that could not be read.".format(HOOK)})
    except Exception:
        sys.stderr.write(message + "\n")
        return 2  # the deny could not be written as JSON: block through the exit status instead
    return 0


if __name__ == "__main__":
    sys.exit(main())
