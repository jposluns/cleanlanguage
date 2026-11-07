#!/usr/bin/env python3
"""Deny AskUserQuestion while the host operating-mode file does not say attended.

Claude Code runs this script as a PreToolUse hook that .claude/settings.json registers for
AskUserQuestion. It reads the hook payload from stdin and, for an AskUserQuestion call, reads
/opt/orch-operator/operating-mode, a JSON object whose "mode" member the orchestrator sets for the
whole host. Only the exact value "attended" lets the question through, with one exception: where
lstat reports /opt/orch-operator itself absent, the host declares no operating-mode, so the guard
allows the question with a one-line note. Every other state denies and names its cause, because a
blocking question in an unattended session stalls the run until someone notices, while a wrongly
denied question only asks the agent to record the decision and continue.

The vendored orch_ask_guard does not enforce this: it reads an "Operating-mode:" text line from a
mode record that this repository does not declare, so it allows the question and logs a fail-open
event. This guard is the repository's own layer, and it stays as a second layer after a re-vendored
hook reads the JSON file.

Decisions, in the order the guard makes them:

- an argument it does not know or cannot parse, or a hook payload that is not a JSON object: deny,
  whatever the tool, because the guard reads both before it looks at the tool;
- a tool other than AskUserQuestion: allow, silently;
- lstat reporting /opt/orch-operator itself absent: allow, with a one-line systemMessage, so that
  contributor machines and hosts without the orchestrator stay usable;
- lstat on /opt/orch-operator failing for any other reason, such as a parent directory the guard
  cannot search: deny;
- the mode file missing, unreadable, a symlink (opened with O_NOFOLLOW), or not a regular file: deny;
- the opened file not owned by uid 0, or writable by its group or by others (fstat on the open
  descriptor): deny;
- content over 4096 bytes, not strict UTF-8, not one JSON object (NaN, Infinity and -Infinity
  included, since JSON has no such values), holding a duplicate key, or with a "mode" that is
  absent or not a string: deny;
- "mode" exactly "attended": allow, silently; "unattended" or any other value, including a case
  variant: deny;
- any other exception the guard raises at any of these steps, before it prints its verdict: deny,
  since a denied question cannot wedge a session.

The phase, set_by and set_at members do not affect the decision. The guard writes no file; it only
prints its verdict. The deny output has the shape the vendored hooks use: permissionDecision deny on
exit 0.

Test-only arguments: --mode-file PATH reads PATH instead, and the directory that holds PATH takes the
place of /opt/orch-operator for the absent-directory rule; --expect-owner-uid UID expects that owner
instead of uid 0. The registration in .claude/settings.json passes neither.

Residual: this guard covers only AskUserQuestion calls in sessions that load this checkout's
.claude/settings.json. It does not cover other checkouts, other repositories, or non-Claude worker
families; a session that can edit this script or .claude/settings.json can disarm it, visibly in
review; removing /opt/orch-operator disarms it; the guard trusts root's file: it checks that uid 0
owns /opt/orch-operator/operating-mode and that neither its group nor others can write it, so root
controls the decision, and it does not check the directory that holds the file; the file holds one
mode for the whole host, so an attended session is blocked while the host says unattended; the
4096-byte bound limits size, not time, so a slow open or read of a regular file, such as one on a
stalled network filesystem, is bounded only by the hook's 10-second timeout, and the tests do not
show what Claude Code does with the call when that timeout expires; and the vendored orch_ask_guard
continues to log a fail-open audit event on every question until the upstream fix is re-vendored.
"""
import errno
import json
import os
import stat
import sys

MODE_FILE = "/opt/orch-operator/operating-mode"
EXPECTED_OWNER_UID = 0
MAX_BYTES = 4096
TOOL = "AskUserQuestion"
ATTENDED = "attended"
UNATTENDED = "unattended"

# The record-and-continue instruction, worded as the vendored orch_ask_guard words it, so an agent
# meets one instruction whichever guard denies first.
RECORD_AND_CONTINUE = (
    "RECORD the decision as pending (the registry's pending-decisions surface) with your "
    "recommended option and rationale, then CONTINUE with the next authorized independent item. "
    "If the decision sits at the human-oversight threshold (high-consequence, irreversible, or "
    "outward-facing), record it and HOLD that item; the hold never licenses acting without the "
    "answer.")


class Unusable(Exception):
    """The mode file cannot be read as a mode; the message names the cause."""


def deny(reason, banner):
    """A PreToolUse deny, honoured on exit 0."""
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason},
            "systemMessage": banner}


def deny_unattended(mode_file):
    return deny("AskUserQuestion BLOCKED: the host operating-mode in {} is unattended. {} If the "
                "maintainer is in fact present, the maintainer sets \"mode\" to \"attended\" in that "
                "file first; then re-issue.".format(mode_file, RECORD_AND_CONTINUE),
                "Repository guard: denied a blocking question; the host operating-mode is unattended.")


def deny_cause(cause):
    return deny("AskUserQuestion BLOCKED: the host operating-mode cannot be confirmed as attended "
                "({}). Treat the session as unattended. {}".format(cause, RECORD_AND_CONTINUE),
                "Repository guard: denied a blocking question; the host operating-mode cannot be "
                "confirmed as attended: {}.".format(cause))


def reject_constant(name):
    """A json parse_constant hook that refuses NaN, Infinity and -Infinity, which json.loads accepts
    although JSON does not define them."""
    raise ValueError("{} is not a JSON value".format(name))


def reject_duplicates(pairs):
    """A json object_pairs_hook that refuses a repeated key, which json.loads would let win silently."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise Unusable("duplicate key {!r}".format(key))
        obj[key] = value
    return obj


def read_bounded(fd):
    """At most MAX_BYTES + 1 bytes from fd, so oversized content is seen without reading all of it."""
    chunks = []
    size = 0
    while size <= MAX_BYTES:
        chunk = os.read(fd, MAX_BYTES + 1 - size)
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks)


def read_mode(mode_file, expect_uid):
    """The "mode" string from mode_file; raises Unusable naming why it cannot be read."""
    # O_NOFOLLOW refuses a symlink; O_NONBLOCK keeps a FIFO with no writer from hanging the open.
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(mode_file, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise Unusable("{} is a symlink".format(mode_file)) from None
        if exc.errno == errno.ENOENT:
            raise Unusable("{} is missing".format(mode_file)) from None
        raise Unusable("{} is unreadable: {}".format(mode_file, exc.strerror)) from None
    try:
        # Checked on the open descriptor, so the file judged is the file read.
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise Unusable("{} is not a regular file".format(mode_file))
        if info.st_uid != expect_uid:
            raise Unusable("{} is owned by uid {}, not uid {}".format(
                mode_file, info.st_uid, expect_uid))
        writers = [who for who, bit in (("group", stat.S_IWGRP), ("others", stat.S_IWOTH))
                   if info.st_mode & bit]
        if writers:
            raise Unusable("{} is writable by {} (mode {:04o})".format(
                mode_file, " and ".join(writers), stat.S_IMODE(info.st_mode)))
        try:
            data = read_bounded(fd)
        except OSError as exc:
            raise Unusable("{} is unreadable: {}".format(mode_file, exc.strerror)) from None
    finally:
        os.close(fd)
    if len(data) > MAX_BYTES:
        raise Unusable("{} is over {} bytes".format(mode_file, MAX_BYTES))
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise Unusable("{} is not UTF-8".format(mode_file)) from None
    try:
        record = json.loads(text, object_pairs_hook=reject_duplicates,
                            parse_constant=reject_constant)
    except ValueError as exc:
        raise Unusable("{} is not one JSON document: {}".format(mode_file, exc)) from None
    if not isinstance(record, dict):
        raise Unusable("{} is not a JSON object".format(mode_file))
    if "mode" not in record:
        raise Unusable("{} has no \"mode\" member".format(mode_file))
    if not isinstance(record["mode"], str):
        raise Unusable("\"mode\" is not a string in {}".format(mode_file))
    return record["mode"]


def decide(payload, mode_file, expect_uid):
    """The verdict object to print, or None for a silent allow."""
    if payload.get("tool_name") != TOOL:
        return None
    host_dir = os.path.dirname(os.path.abspath(mode_file))
    try:
        os.lstat(host_dir)
    except FileNotFoundError:
        return {"systemMessage": "Repository guard: {} is absent, so this host declares no "
                                 "operating-mode; AskUserQuestion allowed.".format(host_dir)}
    except OSError as exc:
        return deny_cause("{} cannot be checked: {}".format(host_dir, exc.strerror))
    try:
        mode = read_mode(mode_file, expect_uid)
    except Unusable as exc:
        return deny_cause(str(exc))
    if mode == ATTENDED:
        return None
    if mode == UNATTENDED:
        return deny_unattended(mode_file)
    return deny_cause("unknown mode {!r} in {}".format(mode[:64], mode_file))


def parse_args(argv):
    """(mode file, expected owner uid) from the test-only arguments; anything else raises."""
    mode_file, expect_uid = MODE_FILE, EXPECTED_OWNER_UID
    args = list(argv)
    while args:
        name = args.pop(0)
        if name == "--mode-file" and args:
            mode_file = args.pop(0)
        elif name == "--expect-owner-uid" and args:
            expect_uid = int(args.pop(0))
        else:
            raise ValueError("unknown argument {!r}".format(name))
    return mode_file, expect_uid


def main(argv):
    try:
        mode_file, expect_uid = parse_args(argv)
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        verdict = decide(payload, mode_file, expect_uid)
    except Exception as exc:  # fail closed: a denied question cannot wedge a session
        verdict = deny_cause("guard internal error: {}".format(type(exc).__name__))
    if verdict is not None:
        sys.stdout.write(json.dumps(verdict) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
