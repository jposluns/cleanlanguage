#!/usr/bin/env python3
"""Behaviour tests for the vendored gate_weakening hook on write-then-run commit probes.

Each case reads 1 payload file under tools/payloads/gate-weakening/: a PreToolUse event for the Bash
tool whose tool_input command string holds the probe text. The test passes that JSON, unchanged
except for the cwd field, on standard input to

    python3 -I plugin/aiqt-guardrails-hooks/hooks/scripts/aiqt_hooks.py gate_weakening

and asserts the exit code and the verdict the hook prints. The probe text is data: nothing in this
test, and no shell, ever runs it; the payload files are the only place it is written, and the cwd
given to the hook is an empty temporary directory.

The 5 probes write a script that makes a git commit with a hook-bypass flag and then run it: p1 is
the exact command text of the reported case; p2 a heredoc shell script run with bash; p3 the same
with the short flag, run with sh; p4 a printf-written script run with bash; p5 a heredoc Python
script that commits through subprocess, run with python3. The hook must deny each, with a reason
that begins "AIQT rule gatdis". The 2 controls, a plain status call (c1) and a heredoc script with
no git command (c2), must pass with no decision. Every case expects exit 0, since the hook denies
through permissionDecision on exit 0. A missing hook or payload fails the case rather than
skipping it, so an absent file cannot read as a green run.

The hooks before the refresh to pack commit 730c039b allowed all 5 probes, so this test is red on
them; --hook PATH runs the same cases against another copy of the hook to show that.

Usage: python3 -I tools/test-gate-weakening-probes.py [--hook PATH]
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
HOOK = REPO_ROOT / "plugin" / "aiqt-guardrails-hooks" / "hooks" / "scripts" / "aiqt_hooks.py"
PAYLOADS = HERE / "payloads" / "gate-weakening"
PROBES = ("p1", "p2", "p3", "p4", "p5")
CONTROLS = ("c1", "c2")
DENY_PREFIX = "AIQT rule gatdis"
TIMEOUT = 60


def run_hook(name):
    """(completed process, payload) for the payload file name.json, fed to the hook on stdin."""
    path = PAYLOADS / (name + ".json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="gate-weakening-") as cwd:
        payload["cwd"] = cwd
        proc = subprocess.run([sys.executable, "-I", str(HOOK), "gate_weakening"],
                              input=json.dumps(payload), capture_output=True, text=True,
                              cwd=cwd, timeout=TIMEOUT)
    return proc, payload


def decision(proc):
    """The (permissionDecision, reason) the hook printed, or (None, None) for no decision."""
    out = proc.stdout.strip()
    if not out:
        return None, None
    obj = json.loads(out.splitlines()[0])
    spec = obj.get("hookSpecificOutput") or {}
    return spec.get("permissionDecision"), spec.get("permissionDecisionReason")


class GateWeakeningProbes(unittest.TestCase):
    def setUp(self):
        if not HOOK.is_file():
            self.fail("vendored hook not found: {}".format(HOOK))

    def test_payloads_are_bash_pretooluse_events(self):
        for name in PROBES + CONTROLS:
            with self.subTest(payload=name):
                path = PAYLOADS / (name + ".json")
                self.assertTrue(path.is_file(), "payload not found: {}".format(path))
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload.get("hook_event_name"), "PreToolUse")
                self.assertEqual(payload.get("tool_name"), "Bash")
                command = payload.get("tool_input", {}).get("command")
                self.assertIsInstance(command, str)
                self.assertTrue(command.strip())

    def test_each_probe_is_denied_by_gatdis(self):
        for name in PROBES:
            with self.subTest(probe=name):
                proc, _payload = run_hook(name)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                verdict, reason = decision(proc)
                self.assertEqual(verdict, "deny", "probe {} was not denied: {!r}"
                                 .format(name, proc.stdout[:300]))
                self.assertTrue(reason.startswith(DENY_PREFIX), reason)

    def test_each_control_passes_with_no_decision(self):
        for name in CONTROLS:
            with self.subTest(control=name):
                proc, _payload = run_hook(name)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(decision(proc), (None, None), proc.stdout[:300])


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--hook"]:
        if len(args) < 2:
            print("usage: test-gate-weakening-probes.py [--hook PATH]", file=sys.stderr)
            sys.exit(2)
        HOOK = Path(args[1]).resolve()
        args = args[2:]
    unittest.main(argv=[sys.argv[0]] + args)
