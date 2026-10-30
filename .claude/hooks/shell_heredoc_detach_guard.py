#!/usr/bin/env python3
"""shell_heredoc_detach_guard: an adopter-owned PreToolUse Bash hook for this repository.

Owner and scope. This file is adopter-owned: it sits under .claude/hooks/, outside every path listed in
.aiqt/pin.toml [vendored], and is the local compensating control for the heredoc lifting reduction of the
items 38 and 40 re-vendor. The upstream orch_truncation_guard (rule trkasy, track-launched-work) lifts a
single ampersand in the body of a here-document under a quoted delimiter, so a shell that runs such a body
can detach a child the foreground call does not track, and the vendored guard allows it (upstream
discloses this residual).

The rule. This hook does not parse bash. It reads the command as text and denies it when all three of
these tests hold:
  1. a here-document operator, two less-than signs that no third less-than sign adjoins (so a
     here-string is not one), stands on a physical line that holds a quote (an apostrophe or a double
     quote) or a backslash anywhere after that operator;
  2. an ampersand character stands anywhere in the text, operators included: a double ampersand, an
     ampersand redirection and the stderr pipe all count;
  3. a shell name stands anywhere in the text: bash, dash, zsh or ksh as a substring of any word
     (case-sensitive, so ksh93 and mksh count), or sh as a word bounded on each side by a character
     that is not a letter or a digit, or by the edge of the text, with an optional digit suffix (sh5),
     or the variable SHELL or BASH expanded.
Each test reads the command both as written and with every backslash-newline pair removed, as bash
removes a line continuation, and test 3 also reads it with every quote and backslash removed, so a name
split by quotes or by a backslash still counts. The three need not be related: the operator, the
ampersand and the shell name may sit anywhere in the command.

RESIDUAL (disclosed; a coarse best-effort rule, not complete coverage):
  Cost, over-refusal. A command that holds the three is denied even when nothing detaches. This covers
  every command chained with a double ampersand, or carrying an ampersand redirection (such as 2>&1,
  &> or >&2) or the stderr pipe, that also holds a quoted here-document and a shell name; an
  ampersand that is only data, quoted, escaped, in a comment, in a case fall-through terminator or in an
  input duplication; a quote or a backslash after the operator that is not part of the delimiter, and two
  less-than signs that are no here-document operator at all (a left shift); and a shell name inside a
  longer word (dashboard, .bashrc, a file name ending in .sh), as an argument, in a shebang line or in
  prose. The remedy is to split the command, so that the here-document and the ampersand sit in separate
  calls, or to avoid the here-document (write the body to a file first, or pass it some other way); a
  job meant to run in the background goes through the tracked background dispatch (run_in_background).
  What still passes:
  1. A shell reached without its name in the text: through a variable other than SHELL or BASH, an
     alias or a function, a name built by an expansion or by ANSI-C quoting, sh glued to a letter or a
     digit before it (env -Ssh) or to a letter after it (shx), a name written in another case, another
     interpreter (ash, yash, posh, a renamed shell binary), a script file run directly, or eval, source
     or the dot command reading the body.
  2. A detacher with no ampersand character in the text: setsid, nohup, disown, coproc, at, a terminal
     multiplexer, or an ampersand built by an expansion (such as printf with an octal escape) and then
     run through eval or a nested shell.
  3. A command with no here-document operator followed on its line by a quote or a backslash: an
     unquoted delimiter, a here-string, a pipe from echo or printf, or a script file. This hook does not
     judge them; they are left to the vendored trkasy guard, and this hook does not establish which of
     them that guard catches.
  4. An unreadable hook payload (not JSON, or no command string) is allowed with a note; the vendored
     trkasy guard denies such a payload.

Fail-closed exit. A deny, and an internal error at any point after the hook starts, end with exit status
2, the status that blocks the call. Every output write on those paths is guarded: the hook tries the JSON
deny on stdout and the reason on stderr, ignores a write that fails (a closed, absent or broken stream),
and leaves through os._exit, which skips the interpreter shutdown flush that could otherwise fail and
change the status.

Launch with python3 -I. Plain ASCII, standard library only.
"""

import json
import os
import re
import sys

# The characters this rule matches that are written once, here, as named constants.
AMP = "&"
APOS = "'"

HOOK = "shell_heredoc_detach_guard"
# Test 1: a here-document operator that no third less-than sign adjoins, then, later on the same physical
# line, a quote or a backslash. Only the first operator on a line is needed, since its tail holds the
# tail of every later one, which keeps the scan linear.
HEREDOC_OPERATOR = re.compile(r"(?<!<)<<(?!<)")
QUOTE_OR_BACKSLASH = re.compile("[" + APOS + r"\"\\]")
# Test 3: bash, dash, zsh or ksh anywhere; sh as a word with an optional digit suffix.
SHELL_NAME = re.compile(r"bash|dash|zsh|ksh|(?<![A-Za-z0-9])sh[0-9]*(?![A-Za-z0-9])")
SHELL_VARIABLE = re.compile(r"\$\{?(SHELL|BASH)(?![A-Za-z0-9_])")


def quoted_heredoc(text):
    """Test 1: True when a line holds a here-document operator followed on that line by a quote or a
    backslash."""
    for line in text.split("\n"):
        m = HEREDOC_OPERATOR.search(line)
        if m is not None and QUOTE_OR_BACKSLASH.search(line, m.end()) is not None:
            return True
    return False


def shell_name(texts):
    """Test 3: the first shell name or variable found in any of the texts, as written or with every
    quote and backslash removed; else None."""
    for text in texts:
        for candidate in (text, QUOTE_OR_BACKSLASH.sub("", text)):
            for pattern in (SHELL_NAME, SHELL_VARIABLE):
                m = pattern.search(candidate)
                if m is not None:
                    return m.group(0)
    return None


def _deny_reason(name):
    return ("Adopter hook {} (compensating control for rule trkasy, track-launched-work): this command holds "
            "a here-document operator with a quote or a backslash after it on its line, an ampersand and "
            "the shell name {}, the shape that can detach a child the foreground call does not track. The "
            "hook reads the text coarsely and refuses the shape, even where nothing detaches. Split the "
            "command so that the here-document and the ampersand sit in separate calls, avoid the "
            "here-document (for example, write the body to a file first), or launch a background job "
            "through the tracked background dispatch (run_in_background).").format(HOOK, name)


def decide(command):
    """None (allow) or (deny, reason)."""
    if "<" not in command or AMP not in command:
        return None
    texts = (command, command.replace("\\\n", ""))
    if not any(quoted_heredoc(text) for text in texts):
        return None
    name = shell_name(texts)
    if name is not None:
        return ("deny", _deny_reason(name))  # DENY-RULE
    return None


def _write(stream_name, data):
    """Write data to sys.stdout or sys.stderr and flush it. False, never an exception, when the stream is
    closed, absent or broken."""
    try:
        stream = getattr(sys, stream_name)
        stream.write(data)
        stream.flush()
        return True
    except Exception:
        return False


def _deny(message):
    """Report a deny on every channel that still works and return exit status 2."""
    try:
        document = json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                      "permissionDecision": "deny",
                                                      "permissionDecisionReason": message},
                               "systemMessage": "Adopter hook {}: denied a command holding a quoted "
                                                "here-document, an ampersand and a shell name.".format(HOOK)})
        _write("stdout", document + "\n")
    except Exception:
        pass
    _write("stderr", message + "\n")
    return 2


def _note(message):
    """An allow with a note; a failed write still allows."""
    _write("stdout", json.dumps({"systemMessage": message}) + "\n")
    return 0


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except Exception as exc:
        return _note("Adopter hook {}: the hook payload could not be read ({}); allowed (the vendored trkasy "
                     "guard judges an unreadable payload).".format(HOOK, type(exc).__name__))
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return _note("Adopter hook {}: the Bash payload carried no command string; allowed (the vendored "
                     "trkasy guard judges an unreadable payload).".format(HOOK))
    try:
        outcome = decide(command)
    except Exception as exc:
        return _deny("Adopter hook {}: an internal error ({}) stopped the judging of the command "
                     "(fail-closed).".format(HOOK, type(exc).__name__))
    if outcome is None:
        return 0
    return _deny(outcome[1])


def run():
    """Run main and leave with its status; any exception that escapes it denies (fail-closed)."""
    try:
        code = main()
    except BaseException as exc:
        _write("stderr", "Adopter hook {}: an internal error ({}) stopped the hook (fail-closed).\n".format(
            HOOK, type(exc).__name__))
        code = 2
    if code not in (0, 2):
        code = 2
    os._exit(code)


if __name__ == "__main__":
    run()
