#!/usr/bin/env python3
"""shell_heredoc_detach_guard: an adopter-owned PreToolUse Bash hook for this repository.

Owner and scope. This file is adopter-owned: it sits under .claude/hooks/, outside every path listed in
.aiqt/pin.toml [vendored], and is the local compensating control for the heredoc lifting reduction of the
items 38 and 40 re-vendor. The upstream orch_truncation_guard (rule trkasy, track-launched-work) lifts a
single ampersand in the body of a here-document under a quoted delimiter, so a shell that runs such a body
can detach a child the foreground call does not track, and the vendored guard allows it (upstream
discloses this residual).

The rule. This hook does not parse bash. It reads the command as text and denies it when all three of
these appear anywhere in it:
  1. a here-document operator (the plain or the tab-stripping form, not a here-string) whose delimiter
     word holds a quote or a backslash anywhere, so a fully quoted, a partly quoted, an ANSI-C quoted
     and a backslash-escaped delimiter all count;
  2. a single ampersand: an ampersand that is not part of a double ampersand, of the redirection
     operators ampersand-greater-than (with its append form) or greater-than-ampersand, or of the
     stderr pipe, read left to right as bash reads operators;
  3. a shell name, sh, bash, dash, zsh or ksh, standing as a word, with or without a directory path,
     or the variable SHELL or BASH expanded.
Before the three tests a backslash-newline pair is removed, as bash removes a line continuation, and the
shell name is also sought with every quote and backslash removed, so a name split by quotes or by a
backslash still counts.
The three need not be related: the ampersand and the shell name may sit anywhere in the command.

RESIDUAL (disclosed; a coarse best-effort rule, not complete coverage):
  Cost, over-refusal. A command that holds the three is denied even when nothing detaches: an
  ampersand in a body that is only data, inside quotes, in a comment, escaped, in a case fall-through
  terminator or in an input duplication (less-than-ampersand); a shell name as an argument, in a
  shebang line or in prose. The remedy is to run the job in the foreground, to use the tracked
  background dispatch (run_in_background), or to avoid the here-document (write the body to a file
  first, or pass it some other way).
  What still passes:
  1. A shell reached without its name in the text: through a variable other than SHELL or BASH, an
     alias or a function, a name built by an expansion or by ANSI-C quoting, another interpreter (ash,
     mksh, yash, a renamed shell binary), a script file run directly, or eval, source or the dot
     command reading the body.
  2. A detacher with no single ampersand in the text: setsid, nohup, disown, coproc, at, a terminal
     multiplexer, or an ampersand built by an expansion and then run through eval or a nested shell.
  3. A command with no quoted here-document: an unquoted delimiter, a here-string, a pipe from echo or
     printf, or a script file. This hook does not judge them; they are left to the vendored trkasy
     guard, and this hook does not establish which of them that guard catches.
  4. An unreadable hook payload (not JSON, or no command string) is allowed with a note; the vendored
     trkasy guard denies such a payload.

An internal error while a command holding a less-than sign is judged denies (fail-closed).

Launch with python3 -I. Plain ASCII, standard library only.
"""

import json
import re
import sys

# The characters this rule matches that are written once, here, as named constants.
AMP = "&"
APOS = "'"

HOOK = "shell_heredoc_detach_guard"
# A here-document operator (not a here-string) whose delimiter word, up to the first bash metacharacter,
# holds a quote or a backslash.
QUOTED_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?[ \t]*[^ \t\n;|<>()" + AMP + r"]*[" + APOS + r"\"\\]")
SHELL_NAME = re.compile(r"(?<![A-Za-z0-9_.-])(sh|bash|dash|zsh|ksh)(?![A-Za-z0-9_])")
SHELL_VARIABLE = re.compile(r"\$\{?(SHELL|BASH)(?![A-Za-z0-9_])")
QUOTES_AND_BACKSLASHES = re.compile("[" + APOS + r"\"\\]")


def single_ampersand(text):
    """True when the text holds an ampersand that is not part of a double ampersand, an ampersand-greater-
    than, a greater-than-ampersand or the stderr pipe, reading operators left to right."""
    i = text.find(AMP)
    while i >= 0:
        nxt = text[i + 1:i + 2]
        prev = text[i - 1:i]
        if nxt == AMP:
            i = text.find(AMP, i + 2)
        elif nxt == ">" or prev in (">", "|"):
            i = text.find(AMP, i + 1)
        else:
            return True
    return False


def shell_name(text):
    """The shell name or variable the text holds, as written or with every quote and backslash removed;
    else None."""
    for candidate in (text, QUOTES_AND_BACKSLASHES.sub("", text)):
        for pattern in (SHELL_NAME, SHELL_VARIABLE):
            m = pattern.search(candidate)
            if m is not None:
                return m.group(0)
    return None


def _deny_reason(name):
    return ("Adopter hook {} (compensating control for rule trkasy, track-launched-work): this command holds "
            "a here-document under a quoted delimiter, a single ampersand and the shell name {}, the shape "
            "that can detach a child the foreground call does not track. The hook reads the text coarsely "
            "and does not parse the body, so it refuses the shape. Run the job in the foreground, launch it "
            "through the tracked background dispatch (run_in_background), or avoid the here-document (for "
            "example, write the body to a file first).").format(HOOK, name)


def decide(command):
    """None (allow) or (deny, reason)."""
    if "<" not in command:
        return None
    text = command.replace("\\\n", "")
    if QUOTED_HEREDOC.search(text) is None or not single_ampersand(text):
        return None
    name = shell_name(text)
    if name is not None:
        return ("deny", _deny_reason(name))  # DENY-RULE
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
        outcome = None
        if "<" in command:
            outcome = ("deny", "Adopter hook {}: an internal error ({}) stopped the reading of a command that "
                       "may hold a here-document (fail-closed).".format(HOOK, type(exc).__name__))
    if outcome is None:
        return 0
    message = outcome[1]
    try:
        _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                      "permissionDecisionReason": message},
               "systemMessage": "Adopter hook {}: denied a command holding a quoted here-document, a single "
                                "ampersand and a shell name.".format(HOOK)})
    except Exception:
        sys.stderr.write(message + "\n")
        return 2  # the deny could not be written as JSON: block through the exit status instead
    return 0


if __name__ == "__main__":
    sys.exit(main())
