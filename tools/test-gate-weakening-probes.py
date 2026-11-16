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
direct form. The shape check (write_then_run) accepts only the closed form that GRAMMAR and
STRUCTURE define and rejects every other command text: 1 or more writes, and then 1 run line as the
last line. The run line must name a written path, and 1 line of the text written to that path must
hold a git commit with --no-verify or -n. The check reads text only; it makes no claim about how a
shell runs any command. GRAMMAR_FORMS holds rejected and accepted forms for each rule of GRAMMAR and
STRUCTURE, and a case fails when a rule has no rejected form. Each payload file is also pinned by its
sha256, so any edit to a payload fails a named case until the pin is updated with it.

The hook before this pull request (the 2eb6812c hooks on main) allowed all 5 probes, so this test
is red on it, with 5 failures; --hook PATH runs the same cases against another copy of the hook to
show that. The hook of the first pin of this pull request, 730c039b, already denied the 5, and the
test passes on it, as on the hook of the re-pin to pack commit 9d249b47. The test pins
these 5 forms only. It does not show that every write-then-run commit that skips hooks is denied:
a script written under a quoted delimiter that sets core.hooksPath, or a script decoded from
base64, gets no decision from the refreshed hook, on a branch and on a detached HEAD, where the
script's path is absolute and git can probe the directory that it names, inside the work tree or
not, and where either script is written to a relative path with >> or tee. git_discard denies the
core.hooksPath script when the command text also holds a word it reads as a git verb that can lose
work, such as branch, clean or reset in a directory name; review_workdir_hold denies it where git
cannot probe that directory; bash_absolute_paths denies either script written with > to a relative
path; and protected_line denies such a core.hooksPath script written under an unquoted delimiter
(see .aiqt/config.md).

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
# The closed probe grammar. Each pattern must match a whole line. A path is absolute and ends in .sh or
# .py. A here-document write takes a single-quoted delimiter; its written text is the lines up to the
# first line that is exactly the delimiter. A printf write takes a single-quoted text with no %, and
# no backslash but \n, which the check reads as a line break. The run line is bash, sh or python3 and
# a path, and may end with `; echo "name=$?"`.
PATH_FORM = r"(?P<path>/[A-Za-z0-9_./+-]+\.(?:sh|py))"
GRAMMAR = {
    "heredoc write": re.compile(r"cat > " + PATH_FORM + r" <<'(?P<delimiter>[A-Za-z_][A-Za-z0-9_]*)'"),
    "printf write": re.compile(r"printf '(?P<text>(?:[^'\\%]|\\n)*)' > " + PATH_FORM),
    "run line": re.compile(r"(?:bash|sh|python3) " + PATH_FORM + r"(?:; echo \"[a-z]+=\$\?\")?"),
}
# The rules of the order of the lines: every line before the run line belongs to a write, and the run
# line is the last line.
STRUCTURE = ("only writes before the run line", "the run line is the last line")
# A git commit with a hook-skipping flag, as shell words or as a Python argument list.
COMMIT_WORDS = re.compile(r"\bgit\b[^\n]*\bcommit\b|\"git\",\s*\"commit\"")
SKIP_FLAG = re.compile(r"--no-verify|(?:^|[\s\"])-n(?:[\s\"]|$)", re.MULTILINE)
# 3 moved forms that the shape check must reject: each script holds no commit, and a direct commit
# with a hook-skipping flag stands between the written text and the run line.
MOVED_COMMIT_FORMS = (
    "cat > /tmp/probe-m1.sh <<'EOF'\necho probe\nEOF\ngit commit --no-verify -m probe\nbash /tmp/probe-m1.sh",
    "cat > /tmp/probe-m2.py <<'EOF'\nprint('probe')\nEOF\ngit commit -n -m probe\npython3 /tmp/probe-m2.py",
    "printf 'echo probe\\n' > /tmp/probe-m3.sh\ngit commit --no-verify -m probe\nsh /tmp/probe-m3.sh",
)
# 1 pair per shape condition: (condition, a form that fails only that condition, the same form with the
# condition met). The shape check must reject the first and accept the second, so removing any 1 of the
# 4 conditions makes its rejected form pass and fails the case.
SHAPE_CONDITION_FORMS = (
    ("hook-skipping flag",
     "cat > /tmp/probe-s1.sh <<'EOF'\ngit commit -m probe\nEOF\nbash /tmp/probe-s1.sh",
     "cat > /tmp/probe-s1.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\nbash /tmp/probe-s1.sh"),
    ("commit word",
     "cat > /tmp/probe-s2.sh <<'EOF'\necho --no-verify\nEOF\nbash /tmp/probe-s2.sh",
     "cat > /tmp/probe-s2.sh <<'EOF'\ngit commit --no-verify\nEOF\nbash /tmp/probe-s2.sh"),
    ("run after the written text",
     "bash /tmp/probe-s3.sh\ncat > /tmp/probe-s3.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF",
     "cat > /tmp/probe-s3.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\nbash /tmp/probe-s3.sh"),
    ("run of the written path",
     "cat > /tmp/probe-s4.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\nbash /tmp/probe-other.sh",
     "cat > /tmp/probe-s4.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\nbash /tmp/probe-s4.sh"),
)
# A form whose script holds the commit word and the hook-skipping flag on 2 different lines, which the
# shape check must reject, and the same form with both on 1 line, which it must accept.
SPLIT_LINE_FORMS = (
    "cat > /tmp/probe-s5.sh <<'EOF'\ngit commit -m probe\necho --no-verify\nEOF\nbash /tmp/probe-s5.sh",
    "cat > /tmp/probe-s5.sh <<'EOF'\ngit commit --no-verify -m probe\necho done\nEOF\nbash /tmp/probe-s5.sh",
)
# A printf write followed by more text on its line (here a second printf that overwrites the script with
# no commit), which the shape check must reject, and the same printf write alone on its line, which it
# must accept.
PRINTF_MORE_TEXT_FORMS = (
    "printf 'git commit --no-verify -m probe\\n' > /tmp/probe-s6.sh; printf 'echo probe\\n' > /tmp/probe-s6.sh\n"
    "bash /tmp/probe-s6.sh",
    "printf 'git commit --no-verify -m probe\\n' > /tmp/probe-s6.sh\nbash /tmp/probe-s6.sh",
)
# 1 entry per side of the rule that a write stands alone on its line: (side, the forms that break the
# rule on that side only, which the shape check must reject, and the same writes alone on their lines,
# which it must accept). Removing or loosening the rule on any 1 side makes 1 of its rejected forms pass,
# or 1 of its accepted forms fail, and fails the case.
ALONE_ON_ITS_LINE_FORMS = (
    ("text before cat on the line of a here-document write",
     ("false && cat > /tmp/probe-a1.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\nbash /tmp/probe-a1.sh",
      "echo probe; cat > /tmp/probe-a1.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\nbash /tmp/probe-a1.sh"),
     ("cat > /tmp/probe-a1.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\nbash /tmp/probe-a1.sh",)),
    ("text after the here-document opener",
     ("cat > /tmp/probe-a2.sh <<'EOF'; printf 'echo probe\\n' > /tmp/probe-a2.sh\n"
      "git commit --no-verify -m probe\nEOF\nbash /tmp/probe-a2.sh",
      "cat > /tmp/probe-a2.sh <<'EOF' && echo probe\ngit commit --no-verify -m probe\nEOF\nbash /tmp/probe-a2.sh",
      "cat > /tmp/probe-a2.sh <<'EOF' | tee /tmp/probe-a2.log\ngit commit --no-verify -m probe\nEOF\n"
      "bash /tmp/probe-a2.sh"),
     ("cat > /tmp/probe-a2.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\nbash /tmp/probe-a2.sh",)),
    ("text before a printf write",
     ("false && printf 'git commit --no-verify -m probe\\n' > /tmp/probe-a3.sh\nbash /tmp/probe-a3.sh",
      "echo probe; printf 'git commit --no-verify -m probe\\n' > /tmp/probe-a3.sh\nbash /tmp/probe-a3.sh"),
     ("printf 'git commit --no-verify -m probe\\n' > /tmp/probe-a3.sh\nbash /tmp/probe-a3.sh",)),
    ("text after a printf write",
     ("printf 'git commit --no-verify -m probe\\n' > /tmp/probe-a4.sh && printf 'echo probe\\n' > /tmp/probe-a4.sh\n"
      "bash /tmp/probe-a4.sh",
      "printf 'git commit --no-verify -m probe\\n' > /tmp/probe-a4.sh || true\nbash /tmp/probe-a4.sh"),
     ("printf 'git commit --no-verify -m probe\\n' > /tmp/probe-a4.sh\nbash /tmp/probe-a4.sh",)),
    ("the closing delimiter line of a here-document",
     ("cat > /tmp/probe-a5.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF x\nbash /tmp/probe-a5.sh",
      "cat > /tmp/probe-a5.sh <<'EOF'\ngit commit --no-verify -m probe\n EOF\nbash /tmp/probe-a5.sh",
      "cat > /tmp/probe-a5.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF \nbash /tmp/probe-a5.sh",
      "cat > /tmp/probe-a5.sh <<'EOF'\ngit commit --no-verify -m probe\n\tEOF\nbash /tmp/probe-a5.sh"),
     ("cat > /tmp/probe-a5.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\nbash /tmp/probe-a5.sh",
      "cat > /tmp/probe-a5.sh <<'EOF'\nEOF x\ngit commit --no-verify -m probe\nEOF\nbash /tmp/probe-a5.sh")),
)
# 1 entry per rule of GRAMMAR and STRUCTURE: (rule, forms that break only that rule, which the shape
# check must reject, and the same forms with the rule kept, which it must accept). A case fails when a
# rule of GRAMMAR or STRUCTURE has no rejected form here.
W = "cat > /tmp/probe-g.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\n"
GRAMMAR_FORMS = (
    ("heredoc write",
     ("cat > /tmp/probe-g.sh <<EOF\ngit commit --no-verify -m probe\nEOF\nbash /tmp/probe-g.sh",
      "cat > /tmp/probe-g.sh <<\"EOF\"\ngit commit --no-verify -m probe\nEOF\nbash /tmp/probe-g.sh",
      "cat > /tmp/probe-g.sh <<-'EOF'\n\tgit commit --no-verify -m probe\n\tEOF\nbash /tmp/probe-g.sh",
      "cat > probe-g.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\nbash probe-g.sh",
      "cat > /tmp/probe-g.txt <<'EOF'\ngit commit --no-verify -m probe\nEOF\nbash /tmp/probe-g.txt",
      "cat > /tmp/probe-g.sh <<'EOF'\ngit commit --no-verify -m probe\nbash /tmp/probe-g.sh"),
     (W + "bash /tmp/probe-g.sh",)),
    ("printf write",
     ("printf 'git commit --no-verify -m probe%s\\n' > /tmp/probe-g.sh\nbash /tmp/probe-g.sh",
      "printf 'git commit --no-verify -m probe\\t\\n' > /tmp/probe-g.sh\nbash /tmp/probe-g.sh",
      "printf \"git commit --no-verify -m probe\\n\" > /tmp/probe-g.sh\nbash /tmp/probe-g.sh"),
     ("printf 'git commit --no-verify -m probe\\n' > /tmp/probe-g.sh\nbash /tmp/probe-g.sh",)),
    ("run line",
     (W + "echo bash /tmp/probe-g.sh",
      W + "bash  /tmp/probe-g.sh",
      W + "bash /tmp/probe-g.sh; exit 0",
      W + "bash /tmp/probe-g.sh; echo \"script=$?",
      W + "bash /tmp/probe-g.sh \\"),
     (W + "bash /tmp/probe-g.sh; echo \"script=$?\"", W + "sh /tmp/probe-g.sh")),
    ("only writes before the run line",
     (W + "git commit --no-verify -m probe\nbash /tmp/probe-g.sh",
      W + "exit 0\nbash /tmp/probe-g.sh",
      W + "true; exit 0\nbash /tmp/probe-g.sh",
      W + "{ exit 0; }\nbash /tmp/probe-g.sh",
      W + "echo \\\nbash /tmp/probe-g.sh",
      W + "echo 'start\nbash /tmp/probe-g.sh",
      W + "cat > /tmp/probe-g.txt <<'TXT'\nbash /tmp/probe-g.sh",
      "cat <<'OUTER'\n" + W + "bash /tmp/probe-g.sh\nOUTER",
      "echo '" + W + "bash /tmp/probe-g.sh'"),
     (W + "cat > /tmp/probe-h.py <<'EOF'\nprint(1)\nEOF\nbash /tmp/probe-g.sh",
      "printf 'echo x\\n' > /tmp/probe-h.sh\n" + W + "bash /tmp/probe-g.sh")),
    ("the run line is the last line",
     (W + "bash /tmp/probe-g.sh\n", W + "bash /tmp/probe-g.sh\necho done", W.rstrip("\n")),
     (W + "bash /tmp/probe-g.sh",)),
)


def write_then_run(command):
    """The run path when command is in the closed grammar of GRAMMAR and STRUCTURE and the text written
    to that path holds, on 1 line, a git commit with a hook-skipping flag; else None."""
    lines = command.split("\n")
    written = {}
    i = 0
    while i < len(lines) - 1:
        heredoc = GRAMMAR["heredoc write"].fullmatch(lines[i])
        printf = GRAMMAR["printf write"].fullmatch(lines[i])
        if heredoc:
            close = lines.index(heredoc["delimiter"], i + 1) if heredoc["delimiter"] in lines[i + 1:] else -1
            if close < 0:
                return None
            written[heredoc["path"]] = lines[i + 1:close]
            i = close + 1
        elif printf:
            written[printf["path"]] = printf["text"].replace("\\n", "\n").split("\n")
            i += 1
        else:
            return None
    run = GRAMMAR["run line"].fullmatch(lines[-1])
    if not run:
        return None
    if not any(COMMIT_WORDS.search(line) and SKIP_FLAG.search(line) for line in written.get(run["path"], ())):
        return None
    return run["path"]


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

    def test_shape_check_rejects_a_commit_outside_the_script(self):
        for index, command in enumerate(MOVED_COMMIT_FORMS, 1):
            with self.subTest(moved_form=index):
                self.assertIsNone(write_then_run(command),
                                  "a commit outside the written script passed the shape check: {!r}"
                                  .format(command))

    def test_shape_check_requires_each_condition(self):
        for condition, rejected, accepted in SHAPE_CONDITION_FORMS:
            with self.subTest(condition=condition):
                self.assertIsNotNone(write_then_run(accepted),
                                     "the form that meets every condition failed the shape check: {!r}"
                                     .format(accepted))
                self.assertIsNone(write_then_run(rejected),
                                  "a form without the {} passed the shape check: {!r}"
                                  .format(condition, rejected))

    def test_shape_check_requires_the_commit_and_the_flag_on_1_line(self):
        rejected, accepted = SPLIT_LINE_FORMS
        self.assertIsNotNone(write_then_run(accepted),
                             "the commit and the flag on 1 line failed the shape check: {!r}".format(accepted))
        self.assertIsNone(write_then_run(rejected),
                          "the commit and the flag on 2 lines passed the shape check: {!r}".format(rejected))

    def test_shape_check_requires_a_printf_write_alone_on_its_line(self):
        rejected, accepted = PRINTF_MORE_TEXT_FORMS
        self.assertIsNotNone(write_then_run(accepted),
                             "a printf write alone on its line failed the shape check: {!r}".format(accepted))
        self.assertIsNone(write_then_run(rejected),
                          "a printf write followed by more text passed the shape check: {!r}".format(rejected))

    def test_shape_check_requires_each_write_alone_on_its_line(self):
        for side, rejected_forms, accepted_forms in ALONE_ON_ITS_LINE_FORMS:
            for index, accepted in enumerate(accepted_forms, 1):
                with self.subTest(side=side, accepted=index):
                    self.assertIsNotNone(write_then_run(accepted),
                                         "a write alone on its line failed the shape check: {!r}".format(accepted))
            for index, rejected in enumerate(rejected_forms, 1):
                with self.subTest(side=side, rejected=index):
                    self.assertIsNone(write_then_run(rejected),
                                      "a write with {} passed the shape check: {!r}".format(side, rejected))

    def test_shape_check_accepts_only_its_grammar(self):
        self.assertEqual({rule for rule, rejected, _accepted in GRAMMAR_FORMS if rejected},
                         set(GRAMMAR) | set(STRUCTURE), "a rule of the grammar has no rejected form")
        for rule, rejected_forms, accepted_forms in GRAMMAR_FORMS:
            for index, accepted in enumerate(accepted_forms, 1):
                with self.subTest(rule=rule, accepted=index):
                    self.assertIsNotNone(write_then_run(accepted),
                                         "a form that keeps the rule failed the shape check: {!r}".format(accepted))
            for index, rejected in enumerate(rejected_forms, 1):
                with self.subTest(rule=rule, rejected=index):
                    self.assertIsNone(write_then_run(rejected),
                                      "a form against the rule ({}) passed the shape check: {!r}"
                                      .format(rule, rejected))

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
