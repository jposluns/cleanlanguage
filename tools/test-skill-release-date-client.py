#!/usr/bin/env python3
"""Tests for tools/skill-release-date-client.py, the client the shell callers
of the Released-line extractor run (row 89).

The client runs tools/skill-release-date.py in its --json mode and gives a
content verdict only from a reply that meets the contract. These tests pin:
that it agrees with the extractor's CLI, stream for stream, with each exit
code raised by 10 (T1); that every reply that breaks the contract, and every
extractor that is broken, missing or crashes, reads as unavailable (exit 16),
never as a verdict (T2, T3); its grammar (T4); the bounds on the child's
output and time (T5); that the child runs isolated with an empty environment
(T6); that its contract agrees with the live checksum gate's and its request
keys with the extractor's (T7); the shape of its source (T8); and its
unreadable-input and machinery-error paths (T9).

The tests run offline and touch only throwaway directories.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLIENT = REPO / "tools" / "skill-release-date-client.py"
EXTRACTOR = REPO / "tools" / "skill-release-date.py"
GATE = REPO / "tools" / "check-release-checksum-live.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


client = _load("srd_client", CLIENT)
srd = _load("srd", EXTRACTOR)

GUARD = '\nif __name__ == "__main__":\n'
IMPORT_ANCHOR = "from pathlib import Path\n"

VALID = "# Skill\nVersion: 1.0.15  \nReleased: 2026-11-15  \nAuthor: x\n"
ABSENT = "# Skill\nVersion: 1.0.14  \nAuthor: x\n"

# A copy of the extractor whose --json mode breaks for the op BROKEN_OP only,
# in the way MODE names, while every other op still answers through the real
# json_main, and whose CLI content modes exit 1 (the defect row 89 removes:
# the old probe passes, and every CLI content call reads as malformed).
BROKEN_HOOK = '''
_real_json_main = json_main
def json_main():
    data = sys.stdin.buffer.read()
    request = json.loads(data.decode("utf-8"))
    if request["op"] != {op!r}:
        sys.stdin = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8")
        return _real_json_main()
{body}
_real_main = main
def main(argv):
    if argv[1:] in (["--baseline"], ["--json"]):
        return _real_main(argv)
    return 1
'''
MODES = {
    "exit1": "    raise SystemExit(1)",
    "notjson": "    print('not json')\n    return 0",
    "otherop": (
        "    other = 'extract' if request['op'] == 'baseline' else 'baseline'\n"
        "    value = '2026-11-15' if other == 'extract' else '1.0.14'\n"
        "    print(json.dumps({'op': other, 'outcome': 'value', 'value': value}))\n"
        "    return 0"
    ),
    "badvalue": "    print(json.dumps({'op': request['op'], 'outcome': 'value', 'value': '2026-11-15 '}))\n    return 0",
    "refused": "    print(json.dumps({'op': request['op'], 'outcome': 'refused', 'message': 'x'}))\n    return 0",
}


def broken_extractor(op: str, mode: str) -> str:
    source = EXTRACTOR.read_text(encoding="utf-8")
    if source.count(GUARD) != 1:
        raise AssertionError("the extractor __main__ guard is not unique")
    return source.replace(GUARD, BROKEN_HOOK.format(op=op, body=MODES[mode]) + GUARD)


def expected_reason(op: str, mode: str) -> str:
    return {
        "exit1": f"exited 1 in {op}",
        "notjson": f"did not print a JSON result in {op}",
        "otherop": f"(it answers an op other than {op}) in {op}",
        "badvalue": f"(the value is not {client.CONTRACT[op][1]}) in {op}",
        "refused": f"(refused is not a result of {op}) in {op}",
    }[mode]


# One request per op that the real extractor answers with a value.
WORDS = {
    "extract": ("extract-file", "SKILL.md"),
    "requires_release_date": ("requires-date", "1.0.15"),
    "release_day_from_published_at": ("published-day", "2026-11-15T12:00:00Z"),
    "baseline": ("baseline",),
    "parse_date": ("check-date", "2026-11-15"),
    "publish_window": ("publish-window", "2026-11-15", "2026-11-15T12:00:00Z"),
    "confirm_published": ("confirm-published", "2026-11-15", "2026-11-15T12:00:00Z"),
}

# Reads all of standard input, then fails the read.
UNREADABLE_STDIN_HOOK = (
    "class _UnreadableStdin:\n"
    "    class buffer:\n"
    "        @staticmethod\n"
    "        def read():\n"
    "            sys.__stdin__.buffer.read()\n"
    "            raise OSError(5, \"injected read error\")\n"
    "sys.stdin = _UnreadableStdin()\n"
)


def run_client(*words: str, data: bytes | None = None, cwd: Path | None = None, client_path: Path = CLIENT,
               env: dict | None = None):
    proc = subprocess.run(
        [sys.executable, "-I", str(client_path), *words],
        input=data if data is not None else b"", capture_output=True, cwd=cwd, env=env,
    )
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


def run_cli(*args: str, data: bytes | None = None, cwd: Path | None = None):
    proc = subprocess.run(
        [sys.executable, "-I", str(EXTRACTOR), *args],
        input=data if data is not None else b"", capture_output=True, cwd=cwd,
    )
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


class Pair:
    """A throwaway directory holding a client and an extractor beside it."""

    def __init__(self, extractor: str | None, client_source: str | None = None):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.client = self.root / "skill-release-date-client.py"
        self.client.write_text(client_source or CLIENT.read_text(encoding="utf-8"), encoding="utf-8")
        if extractor is not None:
            (self.root / "skill-release-date.py").write_text(extractor, encoding="utf-8")
        (self.root / "SKILL.md").write_text(VALID, encoding="utf-8")

    def run(self, *words: str, data: bytes | None = None):
        return run_client(*words, data=data, cwd=self.root, client_path=self.client)

    def close(self):
        self._tmp.cleanup()


class ParityTest(unittest.TestCase):
    """T1: the client prints what the CLI prints, on the same streams, and
    exits with the CLI's code plus 10 (0 stays 0)."""

    def assertParity(self, words, cli_args, data=None, cwd=None):
        cli = run_cli(*cli_args, data=data, cwd=cwd)
        got = run_client(*words, data=data, cwd=cwd)
        self.assertIn(cli[0], (0, 1, 3, 4, 5), cli)
        self.assertEqual(got[0], 0 if cli[0] == 0 else cli[0] + 10, (cli, got))
        self.assertEqual(got[1:], cli[1:])

    def test_reads_agree(self):
        corpus = (
            ("valid", VALID.encode()),
            ("absent", ABSENT.encode()),
            ("duplicate line", (VALID + "Released: 2026-11-16\n").encode()),
            ("misspelt key", b"Version: 1.0.15\nreleased: 2026-11-15\n"),
            ("line away from Version", b"Version: 1.0.15\nAuthor: x\nReleased: 2026-11-15\n"),
            ("CRLF", VALID.replace("\n", "\r\n").encode()),
            ("lone CR", VALID.replace("\n", "\r").encode()),
            ("NUL in the line", b"Version: 1.0.15\nReleased: 2026-11-15\x00\n"),
            ("byte order mark", b"\xef\xbb\xbf" + VALID.encode()),
            ("invalid UTF-8", VALID.encode() + b"\xff\n"),
            ("empty", b""),
            ("200 KB valid", (VALID + ("x" * 99 + "\n") * 2000).encode()),
        )
        with tempfile.TemporaryDirectory() as tmp:
            for label, data in corpus:
                path = Path(tmp) / "SKILL.md"
                path.write_bytes(data)
                with self.subTest(label, mode="file"):
                    self.assertParity(("extract-file", str(path)), (str(path),))
                with self.subTest(label, mode="stdin"):
                    self.assertParity(("extract-stdin",), (), data=data)
            with self.subTest("a directory"):
                self.assertParity(("extract-file", tmp), (tmp,))
            with self.subTest("a missing path"):
                missing = str(Path(tmp) / "missing.md")
                self.assertParity(("extract-file", missing), (missing,))

    def test_values_agree(self):
        rows = [("requires-date", "--requires-date", (v,)) for v in
                ("1.0.14", "1.00.14", "1.0.15", "1.0.100", "1.0", "", "-x", "--json", "1.0.15 ")]
        rows += [("check-date", "--check-date", (v,)) for v in
                 ("2026-11-15", "2026-02-30", "", "15 November 2026", "-")]
        rows += [("published-day", "--published-day", (v,)) for v in
                 ("2026-11-15T23:59:59Z", "null", "", "2026-11-15T00:00:00", "2026-13-01T00:00:00Z")]
        rows += [("publish-window", "--publish-window", pair) for pair in (
            ("2026-11-15", "2026-11-15T12:00:00Z"), ("2026-11-15", "2026-11-15T23:55:00Z"),
            ("2026-11-15", "2026-11-16T00:00:01Z"), ("soon", "2026-11-15T12:00:00Z"), ("2026-11-15", "now"),
        )]
        rows += [("confirm-published", "--confirm-published", pair) for pair in (
            ("2026-11-15", "2026-11-15T12:00:00Z"), ("2026-11-15", "2026-11-16T00:00:02Z"),
            ("2026-11-15", "null"), ("15/11/2026", "2026-11-15T12:00:00Z"),
        )]
        rows += [("baseline", "--baseline", ())]
        for word, flag, values in rows:
            with self.subTest(word=word, values=values):
                self.assertParity((word, *values), (flag, *values))


class BrokenExtractorTest(unittest.TestCase):
    """T2, T3: every reply that breaks the contract, and every broken,
    missing or crashed extractor, reads as unavailable (exit 16)."""

    def test_each_broken_reply_at_each_op_is_unavailable(self):
        for op, words in WORDS.items():
            for mode in MODES:
                if mode == "refused" and "refused" in client.CONTRACT[op][2]:
                    continue
                with self.subTest(op=op, mode=mode):
                    pair = Pair(broken_extractor(op, mode))
                    try:
                        code, out, err = pair.run(*words)
                    finally:
                        pair.close()
                    self.assertEqual((code, out), (16, ""), err)
                    self.assertTrue(err.startswith("skill-release-date-client: skill-release-date.py "), err)
                    self.assertIn(expected_reason(op, mode), err)
                    self.assertIn("so the extractor is unavailable", err)
                    self.assertEqual(err.count("\n"), 1, err)

    def test_the_other_ops_still_answer_beside_a_broken_one(self):
        pair = Pair(broken_extractor("extract", "exit1"))
        try:
            self.assertEqual(pair.run("baseline"), (0, "1.0.14\n", ""))
            self.assertEqual(pair.run("requires-date", "1.0.15"), (0, "required\n", ""))
        finally:
            pair.close()

    def test_a_broken_or_missing_extractor_is_unavailable(self):
        imports = EXTRACTOR.read_text(encoding="utf-8").replace(
            IMPORT_ANCHOR, IMPORT_ANCHOR + "import cleanlanguage_no_such_module\n", 1)
        for label, body, fragments in (
            ("syntax-broken", "def broken(:\n", ("exited 1 in baseline", "SyntaxError")),
            ("import-broken", imports, ("exited 1 in baseline", "ModuleNotFoundError")),
            ("missing", None, ("exited 2 in baseline", "can't open file")),
        ):
            with self.subTest(label):
                pair = Pair(body)
                try:
                    code, out, err = pair.run("baseline")
                finally:
                    pair.close()
                self.assertEqual((code, out), (16, ""), err)
                for fragment in fragments:
                    self.assertIn(fragment, err)
                self.assertIn("so the extractor is unavailable; it printed: ", err)

    def test_each_end_of_the_child_is_named(self):
        for label, body, fragment in (
            ("an internal error", "import sys\nsys.stderr.write('boom')\nraise SystemExit(6)\n",
             "failed unexpectedly (internal error) in baseline, so the extractor is unavailable; it printed: boom"),
            ("another exit", "raise SystemExit(3)\n", "exited 3 in baseline, so the extractor is unavailable\n"),
            ("a signal", "import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n",
             "was killed by signal SIGKILL in baseline"),
            ("a repeated key", "print('{\"op\": \"baseline\", \"op\": \"baseline\", \"outcome\": \"value\", "
                               "\"value\": \"1.0.14\"}')\n",
             "(a key appears more than once) in baseline"),
            ("not an object", "print('[]')\n", "(not a JSON object) in baseline"),
            ("an extra key", "print('{\"op\": \"baseline\", \"outcome\": \"value\", \"value\": \"1.0.14\", "
                             "\"x\": 1}')\n",
             "(a result with outcome value has exactly the keys op, outcome, value) in baseline"),
            ("an unknown outcome", "print('{\"op\": \"baseline\", \"outcome\": \"maybe\"}')\n",
             "(its outcome is not value, absent, malformed, or refused) in baseline"),
            ("a message that is not a string", "print('{\"op\": \"baseline\", \"outcome\": \"malformed\", "
                                               "\"message\": 5}')\n",
             "(malformed is not a result of baseline) in baseline"),
            ("non-ASCII output", "import sys\nsys.stdout.buffer.write(b'\\xff')\n",
             "did not print a JSON result in baseline"),
        ):
            with self.subTest(label):
                pair = Pair(body)
                try:
                    code, out, err = pair.run("baseline")
                finally:
                    pair.close()
                self.assertEqual((code, out), (16, ""), err)
                self.assertIn(fragment, err)

    def test_a_message_that_is_not_a_string_is_a_breach(self):
        body = ("print('{\"op\": \"requires_release_date\", \"outcome\": \"malformed\", \"message\": 5}')\n")
        pair = Pair(body)
        try:
            code, out, err = pair.run("requires-date", "1.0")
        finally:
            pair.close()
        self.assertEqual((code, out), (16, ""), err)
        self.assertIn("(the message is not a string) in requires_release_date", err)


class GrammarTest(unittest.TestCase):
    """T4: one word and exactly its arguments, with no option parsing."""

    def test_usage_errors_exit_2(self):
        usage = f"skill-release-date-client: {client.USAGE}\n"
        cases = [(), ("nope",), ("--baseline",), ("--json",), ("Baseline",)]
        for word, (_op, names) in client.GRAMMAR.items():
            cases.append((word, *(["x"] * (len(names) + 1))))
            if names:
                cases.append((word, *(["x"] * (len(names) - 1))))
        for words in cases:
            with self.subTest(words=words):
                self.assertEqual(run_client(*words), (2, "", usage))

    def test_the_usage_line(self):
        self.assertEqual(
            client.USAGE,
            "usage: skill-release-date-client baseline | extract-file PATH | extract-stdin"
            " | requires-date VERSION | check-date VALUE | published-day PUBLISHED_AT"
            " | publish-window EXPECTED NOW | confirm-published EXPECTED PUBLISHED_AT",
        )

    def test_option_like_values_are_values(self):
        for words in (
            ("requires-date", "-"), ("requires-date", "--json"), ("requires-date", ""),
            ("check-date", "-x"), ("published-day", "--baseline"),
            ("publish-window", "-", "--json"), ("confirm-published", "", "-x"),
        ):
            with self.subTest(words=words):
                code, out, err = run_client(*words)
                self.assertEqual((code, out), (11, ""), err)
                self.assertTrue(err.startswith("skill-release-date: "), err)

    def test_extract_file_dash_reads_a_file_named_dash(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "-").write_text(VALID, encoding="utf-8")
            self.assertEqual(run_client("extract-file", "-", data=ABSENT.encode(), cwd=Path(tmp)),
                             (0, "2026-11-15\n", ""))

    def test_exit_constants(self):
        self.assertEqual(
            (client.EXIT_USAGE, client.EXIT_MALFORMED, client.EXIT_ABSENT, client.EXIT_UNREADABLE,
             client.EXIT_REFUSED, client.EXIT_UNAVAILABLE),
            (2, 11, 13, 14, 15, 16),
        )


class BoundsTest(unittest.TestCase):
    """T5: the child's output and time are bounded."""

    def stub(self, tmp: str, body: str) -> Path:
        path = Path(tmp) / "stub.py"
        path.write_text(body, encoding="utf-8")
        return path

    def test_output_past_the_bound_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            limit = client.RESULT_LIMIT
            tool = self.stub(tmp, f"import sys\nsys.stdout.write('x' * {limit + 1})\n")
            with self.assertRaises(client.Unavailable) as caught:
                client.run_extractor("baseline", {}, tool=tool)
            self.assertEqual(caught.exception.reason, f"printed more than {limit} bytes")
            # The bound grows with the request, so an echoed value keeps its verdict.
            tool = self.stub(tmp, f"import sys\nsys.stdout.write('x' * {limit + 1 + 12 * 3})\n")
            with self.assertRaises(client.Unavailable) as caught:
                client.run_extractor("parse_date", {"arg": "abc"}, tool=tool)
            self.assertEqual(caught.exception.reason, f"printed more than {limit + 36} bytes")

    def test_a_reply_at_the_bound_is_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            reply = '{"op": "baseline", "outcome": "value", "value": "1.0.14"}'
            pad = client.RESULT_LIMIT - len(reply)
            tool = self.stub(tmp, f"import sys\nsys.stdout.write({reply!r} + ' ' * {pad})\n")
            self.assertEqual(client.run_extractor("baseline", {}, tool=tool)["value"], "1.0.14")

    def test_a_child_that_does_not_end_is_killed_with_its_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool = self.stub(tmp, (
                "import os, time\n"
                "pid = os.fork()\n"
                "if pid == 0:\n"
                "    time.sleep(60)\n"
                "    os._exit(0)\n"
                "open('sleeper.pid', 'w').write(str(pid))\n"
                "time.sleep(60)\n"
            ))
            started = time.monotonic()
            with self.assertRaises(client.Unavailable) as caught:
                client.run_extractor("baseline", {}, timeout=1, tool=tool)
            self.assertLess(time.monotonic() - started, 15)
            self.assertEqual(caught.exception.reason, "was not seen to end within 1 seconds")
            sleeper = int((Path(tmp) / "sleeper.pid").read_text())
            deadline = time.monotonic() + 10
            while True:
                try:
                    os.kill(sleeper, 0)
                except ProcessLookupError:
                    break
                if time.monotonic() > deadline:
                    self.fail(f"the sleeper {sleeper} outlived the timeout")
                time.sleep(0.05)

    def test_bound_constants_equal_the_gates(self):
        gate = _load("crc_gate_bounds", GATE)
        for name in ("CHILD_TIMEOUT_SECONDS", "RESULT_LIMIT", "ECHO_BYTES_PER_CHARACTER", "STDERR_LIMIT",
                     "EXTRACTOR_INTERNAL_ERROR"):
            with self.subTest(name):
                self.assertEqual(getattr(client, name), getattr(gate, name))
        self.assertEqual(
            (client.CHILD_TIMEOUT_SECONDS, client.RESULT_LIMIT, client.ECHO_BYTES_PER_CHARACTER, client.STDERR_LIMIT),
            (20, 65536, 12, 4096),
        )

    def test_relayed_stderr_is_bounded(self):
        body = f"import sys\nsys.stderr.write('e' * {client.STDERR_LIMIT + 100})\nraise SystemExit(3)\n"
        pair = Pair(body)
        try:
            code, _out, err = pair.run("baseline")
        finally:
            pair.close()
        self.assertEqual(code, 16)
        self.assertEqual(err.count("e" * client.STDERR_LIMIT), 1)
        self.assertNotIn("e" * (client.STDERR_LIMIT + 1), err)


class IsolationTest(unittest.TestCase):
    """T6: the child runs under -I with an empty environment."""

    def test_the_child_is_isolated(self):
        body = (
            "import json, os, sys\n"
            "request = json.loads(sys.stdin.read())\n"
            "message = 'isolated=%d env=%s' % (sys.flags.isolated, ','.join(sorted(os.environ)))\n"
            "print(json.dumps({'op': request['op'], 'outcome': 'malformed', 'message': message}))\n"
        )
        pair = Pair(body)
        try:
            env = dict(os.environ, ROW89_CANARY="1", PYTHONPATH="/nowhere")
            proc = subprocess.run([sys.executable, "-I", str(pair.client), "requires-date", "x"],
                                  capture_output=True, text=True, env=env, cwd=pair.root)
        finally:
            pair.close()
        self.assertEqual(proc.returncode, 11, proc.stderr)
        self.assertTrue(proc.stderr.startswith("skill-release-date: isolated=1 env="), proc.stderr)
        names = proc.stderr.strip().split("env=", 1)[1]
        # Python itself may set LC_CTYPE when it coerces the C locale.
        self.assertTrue(set(filter(None, names.split(","))) <= {"LC_CTYPE"}, names)


class ContractDriftTest(unittest.TestCase):
    """T7: the client's contract agrees with the live checksum gate's, op by
    op, and its request keys with the extractor's."""

    PROBES = ("2026-11-15", "2026-11-15 ", "2026-13-45", True, False, "true", 1, 0, None, "1.0.14", "1.0",
              [], "2026-11-15T00:00:00Z", "1.0.14\n")

    def test_the_gates_ops_agree(self):
        gate = _load("crc_gate_drift", GATE)
        for op, (check, expected, outcomes) in gate.RELEASE_DATE_CONTRACT.items():
            with self.subTest(op):
                ccheck, cexpected, coutcomes = client.CONTRACT[op]
                self.assertEqual((cexpected, coutcomes), (expected, outcomes))
                for probe in self.PROBES:
                    self.assertEqual(ccheck(probe), check(probe), probe)
        self.assertEqual(gate.REPLY_KEYS, {k: client.REPLY_KEYS[k] for k in gate.REPLY_KEYS})
        self.assertEqual(client.REPLY_KEYS["refused"], client.REPLY_KEYS["malformed"])
        self.assertEqual(gate.DAY_FORM.pattern, client.DAY_FORM.pattern)
        self.assertEqual(gate.BASELINE_FORM.pattern, client.BASELINE_FORM.pattern)

    def test_the_ops_agree_with_the_extractor(self):
        gate = _load("crc_gate_ops", GATE)
        self.assertEqual(client.REQUEST_KEYS, srd.JSON_REQUEST_KEYS)
        self.assertEqual(set(client.CONTRACT), set(srd.JSON_OPS))
        grammar_ops = {op for op, _names in client.GRAMMAR.values()}
        self.assertLessEqual(grammar_ops, set(client.CONTRACT))
        # No op is unused: each is run by the gate or by a client word.
        self.assertEqual(grammar_ops | set(gate.RELEASE_DATE_CONTRACT), set(client.CONTRACT))
        # refused is a result of the two day checks only, as in the extractor.
        self.assertEqual({op for op, (_c, _e, outs) in client.CONTRACT.items() if "refused" in outs},
                         {"publish_window", "confirm_published"})


class SourceShapeTest(unittest.TestCase):
    """T8: one process start, its argv, one import anchor, the 3.9 floor."""

    def test_source_shape(self):
        source = CLIENT.read_text(encoding="utf-8")
        tree = ast.parse(source, feature_version=(3, 9))
        popens = []
        for function in [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]:
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                        node.func.attr in ("Popen", "run", "call", "check_call", "check_output", "system",
                                           "execv", "execve", "spawnv", "fork"):
                    popens.append((function.name, ast.unparse(node.func), ast.unparse(node.args[0])))
        self.assertEqual(popens, [("run_extractor", "subprocess.Popen",
                                   "[executable, '-I', str(tool), '--json']")])
        self.assertEqual(source.count(IMPORT_ANCHOR), 1)
        self.assertIn("env={}", source)
        self.assertIn("start_new_session=True", source)


class InputAndMachineryTest(unittest.TestCase):
    """T9: an unreadable input is exit 14 and a failure of the client's own
    machinery is exit 16, never a verdict."""

    def test_unreadable_standard_input(self):
        source = CLIENT.read_text(encoding="utf-8")
        pair = Pair(EXTRACTOR.read_text(encoding="utf-8"),
                    source.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + UNREADABLE_STDIN_HOOK, 1))
        try:
            self.assertEqual(
                pair.run("extract-stdin", data=VALID.encode()),
                (14, "", "skill-release-date: could not read standard input: [Errno 5] injected read error\n"),
            )
        finally:
            pair.close()

    def test_a_machinery_error_is_unavailable(self):
        source = CLIENT.read_text(encoding="utf-8")
        hook = (
            "import tempfile as _t\n"
            "def _crash(*args, **kwargs):\n"
            "    raise RuntimeError(\"injected machinery error\")\n"
            "_t.TemporaryFile = _crash\n"
        )
        pair = Pair(EXTRACTOR.read_text(encoding="utf-8"), source.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + hook, 1))
        try:
            self.assertEqual(
                pair.run("baseline"),
                (16, "", "skill-release-date-client: skill-release-date.py could not be run, waited for, or read "
                         "(RuntimeError: injected machinery error) in baseline, so the extractor is unavailable\n"),
            )
        finally:
            pair.close()

    def test_an_error_outside_the_run_is_unavailable(self):
        source = CLIENT.read_text(encoding="utf-8")
        hook = (
            "def _crash(*args, **kwargs):\n"
            "    raise RuntimeError(\"injected error\")\n"
        )
        broken = source.replace(GUARD, "\nparse_argv = _crash\n" + GUARD, 1).replace(
            IMPORT_ANCHOR, IMPORT_ANCHOR + hook, 1)
        pair = Pair(EXTRACTOR.read_text(encoding="utf-8"), broken)
        try:
            self.assertEqual(
                pair.run("baseline"),
                (16, "", "skill-release-date-client: skill-release-date.py could not be run, waited for, or read "
                         "(RuntimeError: injected error), so the extractor is unavailable\n"),
            )
        finally:
            pair.close()


if __name__ == "__main__":
    unittest.main()
