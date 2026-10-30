#!/usr/bin/env python3
"""Regression test for the commit-identity read limit (the commit identity read limit reduction).

The vendored hook reads a command of at most aiqt_hooks.py:_CMTIDN_READ_LIMIT characters in full;
aiqt_hooks.py:find_ai_authorship raises before it reads a longer one, and the handler then judges the
command by its conservative fallback, aiqt_hooks.py:_commit_identity_fallback. The maintainer accepted
that limit as a disclosed reduction together with this test, which keeps the fallback covered: it drives
the vendored hook, registered as hooks.json:commit_identity, with a git commit command of about 200 KiB
whose message carries an AI co-author trailer, once at the start of the message and once past the read
limit, and expects a deny each time. Two controls of the same length, one with no trailer and one with a
human co-author trailer, must be allowed, so a stand-in that denies every command fails as well.

A further test reads the read limit from the hook source and fails when it cannot be found or when the
trailer placed past the limit no longer lies past it, so a re-vendor that raises or renames the limit is
surfaced rather than silently moving the fixture inside the read window.

Residual, disclosed: the test covers the -m form at one length. It does not exercise a command of tens
of MiB, at which the upstream hook can outlast its 10-second timeout; .aiqt/config.md records that
residual as accepted.

Run with python3 -I (the script re-executes itself isolated otherwise). --hook points the test at another
hook file, for a deliberate flip or an upstream hook extracted for a re-vendor; remaining arguments go to
unittest. Each hook run gets a throwaway HOME, XDG_STATE_HOME and working directory under TMPDIR.
"""
import os
import sys

if not sys.flags.isolated:
    try:
        os.execv(sys.executable, [sys.executable, "-I", os.path.abspath(__file__)] + sys.argv[1:])
    except OSError as exc:
        print("test-cmtidn-large-message: FAIL: cannot re-execute under python3 -I: {}".format(exc),
              file=sys.stderr)
        sys.exit(1)

import argparse
import ast
import json
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_HOOK = os.path.join(ROOT, "plugin", "aiqt-guardrails-hooks", "hooks", "scripts", "aiqt_hooks.py")
HOOK = DEFAULT_HOOK
MODE = "commit_identity"
# The read limit at the pinned commit (128 KiB); the fixture places its late trailer past it.
LIMIT_AT_PIN = 128 << 10
# The target length of the commit message body, about 200 KiB.
TARGET = 200 << 10
# The AI identity is assembled from parts, so this file carries no literal AI co-author trailer.
AI_TRAILER = "Co-Authored-By: " + "Cl" + "aude <noreply@" + "anthropic" + ".com>"
HUMAN_TRAILER = "Co-Authored-By: Jane Example <jane@example.invalid>"
FILLER_LINE = "Ordinary prose for a long commit message body, with no identity in it.\n"
SUBJECT = "Describe a long change"


def filler(length):
    return FILLER_LINE * (length // len(FILLER_LINE) + 1)


def commit_command(body):
    """A git commit command whose -m argument is double quoted and holds real newlines.

    The body holds no double quote, backslash, dollar sign or backtick, so a shell passes it through
    unchanged and the hook sees the message exactly as written."""
    for ch in "\"\\$`":
        if ch in body:
            raise ValueError("the fixture body holds a shell-active character {!r}".format(ch))
    return "git commit -m \"" + SUBJECT + "\n\n" + body + "\""


def _const(node):
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.BinOp):
        left, right = _const(node.left), _const(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.LShift):
            return left << right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Add):
            return left + right
    return None


def read_limit(path):
    """The integer bound to _CMTIDN_READ_LIMIT at the top level of the hook, or None when the hook does not
    bind it exactly once to a constant integer expression."""
    with open(path, "rb") as fh:
        tree = ast.parse(fh.read(), filename=path)
    values = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "_CMTIDN_READ_LIMIT" for t in node.targets):
                values.append(_const(node.value))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "_CMTIDN_READ_LIMIT" and node.value is not None:
                values.append(_const(node.value))
    if len(values) != 1 or values[0] is None:
        return None
    return values[0]


def late_command():
    return commit_command(filler(TARGET) + "\n" + AI_TRAILER + "\n")


def early_command():
    return commit_command(AI_TRAILER + "\n\n" + filler(TARGET))


class LargeCommitMessage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cmtidn-large-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for name in ("home", "xdg", "work"):
            os.mkdir(os.path.join(self.tmp, name))

    def run_hook(self, command):
        work = os.path.join(self.tmp, "work")
        env = dict(os.environ)
        env["HOME"] = os.path.join(self.tmp, "home")
        env["XDG_STATE_HOME"] = os.path.join(self.tmp, "xdg")
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": work,
                   "tool_input": {"command": command}}
        return subprocess.run([sys.executable, "-I", HOOK, MODE], input=json.dumps(payload),
                              capture_output=True, text=True, env=env, cwd=work, timeout=60)

    def decision(self, command):
        """Run the hook and return (decision, reason). No output, or output without a permission decision
        (an informational note), is an allow; anything other than exit 0 is a test failure."""
        result = self.run_hook(command)
        self.assertEqual(result.returncode, 0, "hook exited {}: {}".format(result.returncode, result.stderr))
        out = result.stdout.strip()
        if not out:
            return "allow", ""
        data = json.loads(out.splitlines()[0])
        spec = data.get("hookSpecificOutput") or {}
        return spec.get("permissionDecision", "allow"), spec.get("permissionDecisionReason", "")

    def assertDenied(self, command):
        decision, reason = self.decision(command)
        self.assertEqual(decision, "deny", "the hook did not deny an AI co-author trailer in a command of "
                         "{} characters".format(len(command)))
        self.assertIn("cmtidn", reason)

    def assertAllowed(self, command):
        decision, reason = self.decision(command)
        self.assertEqual(decision, "allow", reason)

    def test_trailer_past_the_read_limit_is_denied(self):
        command = late_command()
        self.assertGreaterEqual(len(command), TARGET)
        self.assertGreater(command.index(AI_TRAILER), LIMIT_AT_PIN)
        self.assertDenied(command)

    def test_trailer_at_the_start_is_denied(self):
        command = early_command()
        self.assertGreaterEqual(len(command), TARGET)
        self.assertLess(command.index(AI_TRAILER), len(SUBJECT) + 64)
        self.assertDenied(command)

    def test_long_message_without_trailer_is_allowed(self):
        command = commit_command(filler(TARGET))
        self.assertGreater(len(command), LIMIT_AT_PIN)
        self.assertAllowed(command)

    def test_long_message_with_human_trailer_is_allowed(self):
        command = commit_command(filler(TARGET) + "\n" + HUMAN_TRAILER + "\n")
        self.assertGreater(command.index(HUMAN_TRAILER), LIMIT_AT_PIN)
        self.assertAllowed(command)

    def test_fixture_lies_past_the_hook_read_limit(self):
        limit = read_limit(HOOK)
        self.assertIsNotNone(limit, "the hook binds no constant _CMTIDN_READ_LIMIT; re-check this test "
                             "against the hook before relying on it")
        self.assertGreater(late_command().index(AI_TRAILER), limit)
        self.assertGreater(len(early_command()), limit)


def main():
    global HOOK
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--hook", default=DEFAULT_HOOK)
    args, rest = parser.parse_known_args()
    HOOK = os.path.abspath(args.hook)
    if not os.path.isfile(HOOK):
        print("test-cmtidn-large-message: FAIL: hook not found: {}".format(HOOK), file=sys.stderr)
        return 1
    print("test-cmtidn-large-message: hook {}".format(HOOK), file=sys.stderr)
    program = unittest.main(argv=[sys.argv[0]] + rest, exit=False, verbosity=2)
    result = program.result
    if result.testsRun == 0:
        print("test-cmtidn-large-message: FAIL: no test ran", file=sys.stderr)
        return 1
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
