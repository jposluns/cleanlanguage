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

The probes must stay write-then-run forms, since the hook before the refresh already denied the
direct form: each probe command must write a script file and then, on a later line, run that same
file with bash, sh or python3, and the text written between the two must hold a git commit with
--no-verify or -n. Each payload file is also pinned by its sha256, so any edit to a payload fails a
named case until the pin is updated with it.

The hooks before the refresh to pack commit 730c039b allowed all 5 probes, so this test is red on
them; --hook PATH runs the same cases against another copy of the hook to show that. The test pins
these 5 forms only. It does not show that every write-then-run commit that skips hooks is denied:
a written script that sets core.hooksPath, or a script decoded from base64, gets no decision from
the refreshed hook (see .aiqt/config.md).

Usage: python3 -I tools/test-gate-weakening-probes.py [--hook PATH]
"""
import hashlib
import json
import re
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
# The sha256 of each payload file as committed.
PAYLOAD_SHA256 = {
    "p1": "b176529cb9feb66d1b5c2d8d53647bf1329e3ab7d48b106a8e1a149d2e74060e",
    "p2": "4637e5e9171ff273333087666eb30c501e04095c76e482ccad26ec22d93bec6f",
    "p3": "f1fc52194416e7d1aee31ebff571a4ccde5ba7f99e375a2b61685dd51d107945",
    "p4": "9e9bd3785e5baf76c9ac591e441355fff8ceb9d190a02c970255b2c2348ddad9",
    "p5": "ff9dc43e5d25ca5136a5be92d3682ec984ec4e069afad3e2a81db8bb05ea113e",
    "c1": "83fd994d0fd708e27f00fd291a84716cebadc174e09afe853064b1ad90c96ce6",
    "c2": "cc5a3f5a0b4c1c4c6a24e570a1932c2c5829a8906afd260ada04ee72cdd701eb",
}
# A write of a script file: "> path" where the path ends in .sh or .py.
SCRIPT_WRITE = re.compile(r">\s*(/[^\s;&|'\"]+\.(?:sh|py))")
# A run of a script file at the start of a line: bash, sh or python3 and the path.
SCRIPT_RUN = re.compile(r"^(?:bash|sh|python3)\s+([^\s;&|'\"]+)", re.MULTILINE)
# A git commit with a hook-skipping flag, as shell words or as a Python argument list.
COMMIT_WORDS = re.compile(r"\bgit\b[^\n]*\bcommit\b|\"git\",\s*\"commit\"")
SKIP_FLAG = re.compile(r"--no-verify|(?:^|[\s\"])-n(?:[\s\"]|$)", re.MULTILINE)


def write_then_run(command):
    """The script path when command writes a script, runs it on a later line with bash, sh or python3,
    and the text from the start of the writing line to the run holds a git commit with a hook-skipping
    flag; else None."""
    for write in SCRIPT_WRITE.finditer(command):
        path = write.group(1)
        line_start = command.rfind("\n", 0, write.start()) + 1
        for run in SCRIPT_RUN.finditer(command, write.end()):
            if run.group(1) != path:
                continue
            between = command[line_start:run.start()]
            if "\n" in between and COMMIT_WORDS.search(between) and SKIP_FLAG.search(between):
                return path
    return None


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

    def test_each_probe_writes_a_script_then_runs_it(self):
        for name in PROBES:
            with self.subTest(probe=name):
                path = PAYLOADS / (name + ".json")
                command = json.loads(path.read_text(encoding="utf-8"))["tool_input"]["command"]
                self.assertIsNotNone(write_then_run(command),
                                     "probe {} is not a write-then-run commit form: {!r}"
                                     .format(name, command[:200]))

    def test_each_payload_matches_its_pinned_sha256(self):
        for name in PROBES + CONTROLS:
            with self.subTest(payload=name):
                digest = hashlib.sha256((PAYLOADS / (name + ".json")).read_bytes()).hexdigest()
                self.assertEqual(digest, PAYLOAD_SHA256[name])

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
