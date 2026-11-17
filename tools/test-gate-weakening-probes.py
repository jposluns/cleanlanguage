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
direct form. Each payload file is pinned by its sha256, so any edit to a payload fails a named case
until the pin is updated with it, and each probe must pass the shape check (write_then_run). The
check reads text only; it makes no claim about how a shell runs a command. It returns a path only
for 1 or more writes, each alone on its line and each to a path not written before, and then, as
the last line, a run with bash, sh or python3 of a written path, where 1 line of the text written
to that path holds the words git and commit, in that order, and --no-verify or -n as a whole word.
SHAPE_SHA256 pins the sha256 of the check's source, so any edit of the check fails a named case
until the pin is updated with it; the pin shows that the source changed, not that the changed check
keeps its rules. SHAPE_RULES lists rules of the check, each with a form that the check rejects and
an edit of the check's source that removes or loosens the rule. 1 case fails when the check accepts
a listed form. Another fails when a listed edit does not match the check's source exactly once, or
when the check with the edit applied still rejects the form. A form pins only the loosening that it
exercises: a loosening of a listed rule in a direction that no listed form exercises passes those 2
cases and fails only the source pin, and a rule that is not listed is pinned by the source pin alone.

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
# The lines between these 2 markers are the shape check; a case runs them with each edit of SHAPE_RULES.
SHAPE_BEGIN = "# The shape check: begin"
SHAPE_END = "# The shape check: end"
# The shape check: begin
# A path is absolute, of the characters A-Z a-z 0-9 _ . / -, and ends in .sh or .py. A here-document
# write is `cat > PATH <<'EOF'`; its written text is the lines up to the first line that is exactly
# EOF. A printf write is `printf 'TEXT' > PATH`; TEXT holds no ', no % and no backslash but \n, at
# which the check splits it into lines. The run line is bash, sh or python3 and a path, and may end
# with `; echo "script=$?"`. A commit line holds the words git and commit, in that order, and the
# flag --no-verify or -n as a whole word: with a line end, whitespace or a double quote on each side.
PATH_FORM = r"(?P<path>/[A-Za-z0-9_./-]+\.(?:sh|py))"
HEREDOC_WRITE = re.compile(r"cat > " + PATH_FORM + r" <<'EOF'")
PRINTF_WRITE = re.compile(r"printf '(?P<text>(?:[^'\\%]|\\n)*)' > " + PATH_FORM)
RUN_LINE = re.compile(r"(?:bash|sh|python3) " + PATH_FORM + r"(?:; echo \"script=\$\?\")?")
COMMIT_WORDS = re.compile(r"\bgit\b.*\bcommit\b")
SKIP_FLAG = re.compile(r"(?<![^\s\"])(?:--no-verify|-n)(?![^\s\"])")


def write_then_run(command):
    """The run path when command is 1 or more writes, each alone on its line and each to a path not
    written before, and then, as the last line, a run of a written path whose written text holds a
    commit line; else None."""
    lines = command.split("\n")
    written = {}
    i = 0
    while i < len(lines) - 1:
        heredoc = HEREDOC_WRITE.fullmatch(lines[i])
        printf = PRINTF_WRITE.fullmatch(lines[i])
        if heredoc and "EOF" in lines[i + 1:]:
            close = lines.index("EOF", i + 1)
            path, text, i = heredoc["path"], lines[i + 1:close], close + 1
        elif printf:
            path, text, i = printf["path"], printf["text"].split("\\n"), i + 1
        else:
            return None
        if path in written:
            return None
        written[path] = text
    run = RUN_LINE.fullmatch(lines[-1])
    if run and any(COMMIT_WORDS.search(line) and SKIP_FLAG.search(line) for line in written.get(run["path"], ())):
        return run["path"]
    return None
# The shape check: end

# The sha256 of the shape check's source, the lines between SHAPE_BEGIN and SHAPE_END joined with \n.
# Any edit of the check fails test_shape_check_matches_its_pinned_sha256 until this pin is updated
# with it. The pin shows that the source changed, not that the changed check still keeps its rules.
SHAPE_SHA256 = "11055a4c604ed905d56b3391637d9017b775a9f3d20b3c2a81c5b7410453136c"
# The rules of the shape check that the test pins by behaviour, 1 entry each: (rule, a form that the
# check rejects, and an edit (old, new) of the shape check's source that removes or loosens the rule).
# The check must reject the form; the edit's old text must occur exactly once in the check's source,
# and the check with the edit applied must accept the form. A form pins only the loosening that it
# exercises: a loosening of a listed rule in a direction that its form does not exercise passes the
# 2 cases that read this table, and only the source pin above fails on it.
W = "cat > /tmp/probe-s.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\n"
RUN = "bash /tmp/probe-s.sh"
# Every printable ASCII character that may not stand next to the flag: all but whitespace and ".
WORD_EDGES = [chr(n) for n in range(33, 127) if chr(n) != '"']
SHAPE_RULES = (
    ("the path is absolute",
     "cat > probe-s.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\nbash probe-s.sh",
     ('r"(?P<path>/[', 'r"(?P<path>/?[')),
    ("the path has only the listed characters",
     "cat > /tmp/$P.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\nbash /tmp/$P.sh",
     ("/[A-Za-z0-9_./-]+", r"/\S+")),
    ("the path ends in .sh or .py",
     "cat > /tmp/probe-s.txt <<'EOF'\ngit commit --no-verify -m probe\nEOF\nbash /tmp/probe-s.txt",
     (r'\.(?:sh|py))"', ')"')),
    ("a here-document write is to a path of PATH_FORM",
     "cat > probe-r.sh <<'EOF'\necho probe\nEOF\n" + W + RUN,
     ('r"cat > " + PATH_FORM', r'r"cat > (?P<path>\S+)"')),
    ("a printf write is to a path of PATH_FORM",
     "printf 'echo probe\\n' > probe-r.sh\n" + W + RUN,
     ("' > \" + PATH_FORM)", r"""' > (?P<path>\S+)")""")),
    ("a here-document write is cat > PATH",
     "cat >> /tmp/probe-s.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\n" + RUN,
     ('r"cat > "', 'r"cat >>? "')),
    ("the here-document delimiter is 'EOF'",
     "cat > /tmp/probe-s.sh <<EOF\ngit commit --no-verify -m probe\nEOF\n" + RUN,
     ("r\" <<'EOF'\")", "r\" <<'?EOF'?\")")),
    ("a here-document write is alone on its line",
     "echo probe; cat > /tmp/probe-s.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\n" + RUN,
     ("HEREDOC_WRITE.fullmatch(", "HEREDOC_WRITE.search(")),
    ("a here-document has a closing line",
     "cat > /tmp/probe-s.sh <<'EOF'\ngit commit --no-verify -m probe\n" + RUN,
     ('if heredoc and "EOF" in lines[i + 1:]:\n            close = lines.index("EOF", i + 1)',
      'if heredoc:\n            close = lines.index("EOF", i + 1) if "EOF" in lines[i + 1:] else len(lines) - 1')),
    ("a here-document closes at the first EOF line",
     "cat > /tmp/probe-s.sh <<'EOF'\nEOF\ngit commit --no-verify -m probe\nEOF\n" + RUN,
     ('close = lines.index("EOF", i + 1)', 'close = len(lines) - 1 - lines[::-1].index("EOF")')),
    ("a here-document's text ends before its closing line",
     "cat > /tmp/probe-s.sh <<'EOF'\necho probe\nEOF\n"
     "cat > /tmp/probe-t.sh <<'EOF'\ngit commit --no-verify -m probe\nEOF\n" + RUN,
     ("lines[i + 1:close]", "lines[i + 1:]")),
    ("a printf write is printf > PATH",
     "printf 'git commit --no-verify -m probe\\n' >> /tmp/probe-s.sh\n" + RUN,
     (")*)' > \"", ")*)' >>? \"")),
    ("printf text is single-quoted",
     "printf \"git commit --no-verify -m probe\\n\" > /tmp/probe-s.sh\n" + RUN,
     ("r\"printf '(?P<text>(?:[^'\\\\%]|\\\\n)*)' > \"",
      "r\"printf ['\\\"](?P<text>(?:[^'\\\"\\\\%]|\\\\n)*)['\\\"] > \"")),
    ("printf text has no %",
     "printf 'git commit --no-verify -m probe%s\\n' > /tmp/probe-s.sh\n" + RUN,
     ("[^'\\\\%]", "[^'\\\\]")),
    ("printf text has no backslash but \\n",
     "printf 'git commit --no-verify -m probe\\t\\n' > /tmp/probe-s.sh\n" + RUN,
     ("[^'\\\\%]", "[^'%]")),
    ("printf text is read as lines at \\n",
     "printf 'git commit -m probe\\necho --no-verify x\\n' > /tmp/probe-s.sh\n" + RUN,
     ('printf["text"].split("\\\\n")', '[printf["text"]]')),
    ("a printf write is alone on its line",
     "echo probe; printf 'git commit --no-verify -m probe\\n' > /tmp/probe-s.sh\n" + RUN,
     ("PRINTF_WRITE.fullmatch(", "PRINTF_WRITE.search(")),
    ("only writes come before the run line",
     W + "git commit --no-verify -m probe\n" + RUN,
     ("        else:\n            return None\n", "        else:\n            i += 1\n            continue\n")),
    ("every line before the last line is read",
     "printf 'git commit --no-verify -m probe\\n' > /tmp/probe-s.sh\nexit 0\n" + RUN,
     ("while i < len(lines) - 1:", "while i < len(lines) - 2:")),
    ("each path is written once",
     "printf 'echo probe\\n' > /tmp/probe-s.sh\n" + W + RUN,
     ("        if path in written:\n            return None\n", "")),
    ("the run line is bash, sh or python3 and a path",
     W + "rm /tmp/probe-s.sh",
     ('r"(?:bash|sh|python3) "', r'r"\S+ "')),
    ("the run line ends with the path or with the echo of its status",
     W + "bash /tmp/probe-s.sh; exit 0",
     (r'r"(?:; echo \"script=\$\?\")?"', r'r"(?:;.*)?"')),
    ("the run line is the whole last line",
     W + "echo " + RUN,
     ("RUN_LINE.fullmatch(", "RUN_LINE.search(")),
    ("the run line runs a written path",
     W + "bash /tmp/probe-other.sh",
     ('written.get(run["path"], ())', "[line for text in written.values() for line in text]")),
    ("the commit line holds the word git",
     "cat > /tmp/probe-s.sh <<'EOF'\necho commit --no-verify\nEOF\n" + RUN,
     (r'r"\bgit\b.*\bcommit\b"', r'r"\bcommit\b"')),
    ("the commit line holds the word commit",
     "cat > /tmp/probe-s.sh <<'EOF'\ngit log -n 1\nEOF\n" + RUN,
     (r'r"\bgit\b.*\bcommit\b"', r'r"\bgit\b"')),
    ("the flag starts a word",
     "cat > /tmp/probe-s.sh <<'EOF'\n" + "".join("git commit -m x{0}-n\ngit commit x{0}--no-verify\n".format(c)
                                                 for c in WORD_EDGES) + "EOF\n" + RUN,
     (r'(?<![^\s\"])(?:--no-verify|-n)', '(?:--no-verify|-n)')),
    ("the flag ends a word",
     "cat > /tmp/probe-s.sh <<'EOF'\n" + "".join("git commit -n{0} -m x\ngit commit --no-verify{0} -m x\n".format(c)
                                                 for c in WORD_EDGES) + "EOF\n" + RUN,
     (r'(?:--no-verify|-n)(?![^\s\"])', '(?:--no-verify|-n)')),
    ("the flag is in lower case",
     "cat > /tmp/probe-s.sh <<'EOF'\ngit commit --NO-VERIFY -m probe\ngit commit -N -m probe\nEOF\n" + RUN,
     (r'(?![^\s\"])")', r'(?![^\s\"])", re.I)')),
    ("the commit words are in lower case",
     "cat > /tmp/probe-s.sh <<'EOF'\nGIT COMMIT --no-verify -m probe\nEOF\n" + RUN,
     (r'\bcommit\b")', r'\bcommit\b", re.I)')),
    ("the commit words are in the order git, commit",
     "cat > /tmp/probe-s.sh <<'EOF'\ncommit --no-verify -m git\nEOF\n" + RUN,
     (r'r"\bgit\b.*\bcommit\b")', r'r"\bgit\b.*\bcommit\b|\bcommit\b.*\bgit\b")')),
    ("the run line's only suffix is the echo of its status",
     W + "bash /tmp/probe-s.sh; true",
     (r'\$\?\")?")', r'\$\?\")?(?:; true)?")')),
    ("the run line has nothing before the run",
     W + "   " + RUN,
     ("RUN_LINE.fullmatch(lines[-1])", "RUN_LINE.fullmatch(lines[-1].lstrip())")),
    ("a here-document write line has nothing after its delimiter",
     "cat > /tmp/probe-s.sh <<'EOF'\r\ngit commit --no-verify -m probe\nEOF\n" + RUN,
     ("HEREDOC_WRITE.fullmatch(lines[i])", "HEREDOC_WRITE.fullmatch(lines[i].rstrip())")),
    ("a printf write line has nothing after its path",
     "printf 'git commit --no-verify -m probe\\n' > /tmp/probe-s.sh \n" + RUN,
     ("PRINTF_WRITE.fullmatch(lines[i])", "PRINTF_WRITE.fullmatch(lines[i].rstrip())")),
    ("the commit words and the flag are on 1 line",
     "cat > /tmp/probe-s.sh <<'EOF'\ngit commit -m probe\necho --no-verify\nEOF\n" + RUN,
     ('any(COMMIT_WORDS.search(line) and SKIP_FLAG.search(line) for line in written.get(run["path"], ()))',
      'COMMIT_WORDS.search("\\n".join(written.get(run["path"], ()))) '
      'and SKIP_FLAG.search("\\n".join(written.get(run["path"], ())))')),
    ("the command splits into lines only at \\n",
     W + RUN + "\r",
     ('command.split("\\n")', "command.splitlines()")),
)


def shape_source():
    """The source lines of the shape check, between SHAPE_BEGIN and SHAPE_END, as 1 string."""
    lines = Path(__file__).read_text(encoding="utf-8").split("\n")
    return "\n".join(lines[lines.index(SHAPE_BEGIN) + 1:lines.index(SHAPE_END)])


def shape_check(source):
    """The write_then_run function that source defines."""
    namespace = {"re": re}
    exec(source, namespace)
    return namespace["write_then_run"]


def probe_command(name):
    """The command text of the payload file name.json."""
    return json.loads((PAYLOADS / (name + ".json")).read_text(encoding="utf-8"))["tool_input"]["command"]


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

    def test_shape_check_matches_its_pinned_sha256(self):
        digest = hashlib.sha256(shape_source().encode("utf-8")).hexdigest()
        self.assertEqual(digest, SHAPE_SHA256, "the shape check changed: give each rule it adds, removes or "
                         "loosens an entry in SHAPE_RULES whose form exercises it, then update SHAPE_SHA256")

    def test_shape_check_rejects_the_form_of_each_rule(self):
        for rule, rejected, _edit in SHAPE_RULES:
            with self.subTest(rule=rule):
                self.assertIsNone(write_then_run(rejected),
                                  "a form against the rule ({}) passed the shape check: {!r}".format(rule, rejected))

    def test_each_rule_is_what_rejects_its_form(self):
        source = shape_source()
        unchanged = shape_check(source)
        for form in [probe_command(name) for name in PROBES] + [rejected for _rule, rejected, _edit in SHAPE_RULES]:
            self.assertEqual(unchanged(form), write_then_run(form), "the shape source read back differs")
        for rule, rejected, (old, new) in SHAPE_RULES:
            with self.subTest(rule=rule):
                self.assertEqual(source.count(old), 1, "the edit for the rule ({}) does not match the shape "
                                 "check once: {!r}".format(rule, old))
                self.assertIsNotNone(shape_check(source.replace(old, new))(rejected),
                                     "the shape check without the rule ({}) still rejects its form: {!r}"
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
