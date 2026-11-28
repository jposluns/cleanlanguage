#!/usr/bin/env python3
"""Tests for tools/skill-release-date-client.py, the client the shell callers
of the Released-line extractor run (row 89).

The client runs tools/skill-release-date.py in its --json mode and gives a
content verdict only from a reply that meets the contract. These tests pin:
that it agrees with the extractor's CLI, stream for stream, with each exit
code raised by 10 (T1); that every reply that breaks the contract, and every
extractor that is broken, missing or crashes, reads as unavailable (exit 16),
never as a verdict (T2, T3); its grammar (T4); the bounds on the child's
output and time, including the reap after a timeout kill (T5); that the
child runs isolated with an empty environment
(T6); that its contract agrees with the live checksum gate's and its request
keys with the extractor's (T7); the shape of its source (T8); and its
unreadable-input and machinery-error paths (T9).

The tests run offline and touch only throwaway directories.
"""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import os
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from unittest import mock

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

    def test_the_last_representable_day_is_a_verdict(self):
        # Row 99: on 9999-12-31 the publish window gives a value or a
        # refusal (exit 15), never the unavailable exit 16.
        day = "9999-12-31"
        self.assertEqual(run_client("publish-window", day, "9999-12-31T12:00:00Z"), (0, day + "\n", ""))
        code, out, err = run_client("publish-window", day, "9999-12-31T23:55:00Z")
        self.assertEqual((code, out), (15, ""), err)
        self.assertIn("only 300 seconds remain in the UTC day 9999-12-31", err)
        for now in ("9999-12-31T12:00:00Z", "9999-12-31T23:55:00Z"):
            with self.subTest(now):
                self.assertParity(("publish-window", day, now), ("--publish-window", day, now))

    def test_a_version_part_past_the_integer_digit_limit_is_malformed(self):
        # Row 101: a 4301-digit part is malformed (exit 11), never the
        # unavailable exit 16, and a 4300-digit part still compares.
        version = "1.0." + "9" * 4301
        self.assertEqual(
            run_client("requires-date", version),
            (11, "", f"skill-release-date: a part of the version has more than 4300 digits: {version!r}\n"),
        )
        self.assertEqual(run_client("requires-date", "1.0." + "9" * 4300), (0, "required\n", ""))
        for version in ("1.0." + "9" * 4301, "1.0." + "9" * 4300):
            with self.subTest(digits=len(version) - 4):
                self.assertParity(("requires-date", version), ("--requires-date", version))


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

    def test_a_reply_for_another_op_is_a_breach_even_with_a_valid_value(self):
        # The op echo is the only rule this reply breaks: its value is a day,
        # as the check-date op needs, and its outcome and keys are valid.
        body = ("print('{\"op\": \"release_day_from_published_at\", \"outcome\": \"value\", "
                "\"value\": \"2026-11-15\"}')\n")
        pair = Pair(body)
        try:
            code, out, err = pair.run("check-date", "2026-11-15")
        finally:
            pair.close()
        self.assertEqual((code, out), (16, ""), err)
        self.assertIn("(it answers an op other than parse_date) in parse_date, so the extractor is unavailable", err)

    def test_a_valid_reply_with_a_non_zero_exit_is_unavailable(self):
        # The exit is the only rule each child breaks: its reply meets the
        # contract in full, and it then exits 1 or 120.
        reply = "{\"op\": \"baseline\", \"outcome\": \"value\", \"value\": \"1.0.14\"}"
        for exit_code in (1, 120):
            with self.subTest(exit_code=exit_code):
                pair = Pair(f"print({reply!r})\nraise SystemExit({exit_code})\n")
                try:
                    code, out, err = pair.run("baseline")
                finally:
                    pair.close()
                self.assertEqual((code, out), (16, ""), err)
                self.assertEqual(
                    err,
                    f"skill-release-date-client: skill-release-date.py exited {exit_code} in baseline, "
                    "so the extractor is unavailable\n",
                )

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


# The group-kill check's bounds, in seconds: how long the readiness poll may
# hold the client's first wait, how long the client's run, less that poll,
# may take, how long the group may take to end after the client returns,
# and the stub's own end, which each of its processes reaches that long
# after it enters its wait for the release.
POLL_SECONDS = 60
RUN_SECONDS = 15
CHECK_SECONDS = 10
OWN_END_SECONDS = 90

# The stub child of the group-kill check. Its source ignores SIGTERM, SIGINT
# and SIGHUP, and Python ignores SIGPIPE and SIGXFSZ at start-up. When the
# client starts it, it keeps every signal that the test thread blocks as
# blocked, and every signal other than SIGCHLD, SIGPIPE and SIGXFSZ that the
# test process ignores as ignored. The client changes those 3 dispositions
# before exec: its reset_sigchld resets SIGCHLD to its default in its own
# process, the test process, before it starts the child, and its Popen, with
# its default restore_signals, resets SIGPIPE and SIGXFSZ to their default
# action in the child. SIGCHLD's default action, like ignoring it, leaves the
# stub running. So, unless the test thread blocks it, SIGPIPE or SIGXFSZ can
# end the stub before Python ignores it, and SIGTERM, SIGINT or SIGHUP can end
# it before its source ignores it if the test process does not ignore it.
# Examples of a signal that ends it early, not a complete list: SIGKILL, and
# SIGUSR1 when the test neither ignores nor blocks SIGUSR1. It first reads
# its own end, in seconds, with float from the file own_end, which the check
# writes beside it,
# so a plain int or float passed as own_end reaches it only as a number; a
# value with methods of its own can still change its source, as the comment
# in check_group_kill states. A text that float does not take raises at that
# read, before the stub opens either FIFO, so the stub never writes the ready
# byte. Its leader forks 1 member into its group and then writes 1 byte to
# the FIFO alive, so the member holds the write end of alive when the test
# reads that byte, and the test reads end of file on alive only once every
# process holding that write end, the leader and the member, has ended. Each
# process then waits for end of file on the FIFO lifeline, whose only write
# end the test holds, or for its own end, and exits. The test closes lifeline
# when its check ends, and the kernel closes it when the test process ends in
# any other way, SIGKILL included. Each open is non-blocking, so a stub that
# finds no reader of alive fails at once rather than block. On Linux, select
# reports nothing for a FIFO read end opened while no writer has it open, so a
# stub that opens lifeline after the test has closed it would wait at its
# select until its own end. It therefore makes 1 read of lifeline first: a
# read that returns, as a read does with end of file when no writer has the
# FIFO open, rather than fail with BlockingIOError, finds no writer, and the
# stub exits at once.
#
# The bounds this order gives, derived from the source below. Start-up
# here and in the check means interpreter start-up and then the read of
# own_end, which come before the first read of lifeline. A process reaches
# its wait only after start-up and the first read, and the member only
# after the fork, so its own end comes own_end seconds after it enters that
# wait, not after it starts, and nothing in the test bounds start-up. After
# the release, a process past the first read sees end of file at its wait
# and exits at once; a process not yet at that read exits there when it
# gets to it, so it outlives the release by the rest of its start-up,
# however long that is. The leader writes the ready byte only after the
# first read and the fork, so once the test has read that byte, the leader
# and the member are past the read. test_the_check_names_no_signal_function
# pins this order.
GROUP_STUB = (
    "import os, select, signal\n"
    "for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):\n"
    "    signal.signal(number, signal.SIG_IGN)\n"
    "with open('own_end') as file:\n"
    "    own_end = float(file.read())\n"
    "lifeline = os.open('lifeline', os.O_RDONLY | os.O_NONBLOCK)\n"
    "try:\n"
    "    os.read(lifeline, 1)\n"
    "    os._exit(0)\n"
    "except BlockingIOError:\n"
    "    pass\n"
    "alive = os.open('alive', os.O_WRONLY | os.O_NONBLOCK)\n"
    "if os.fork() != 0:\n"
    "    os.write(alive, b'r')\n"
    "select.select([lifeline], [], [], own_end)\n"
    "os._exit(0)\n"
)

# Names through which Python code sends a signal, examples, not a complete
# list: os, signal and subprocess functions and Popen methods that send one to
# a process or a thread, and abort, alarm, raise_signal and setitimer, which
# send one to the caller itself. The group-kill check names none of them.
SIGNAL_NAMES = ("abort", "alarm", "kill", "killpg", "pidfd_send_signal", "pthread_kill", "raise_signal",
                "send_signal", "setitimer", "terminate")

# The calls of GROUP_STUB, in source order.
STUB_CALLS = (
    "signal.signal(number, signal.SIG_IGN)",
    "open('own_end')",
    "float(file.read())",
    "file.read()",
    "os.open('lifeline', os.O_RDONLY | os.O_NONBLOCK)",
    "os.read(lifeline, 1)",
    "os._exit(0)",
    "os.open('alive', os.O_WRONLY | os.O_NONBLOCK)",
    "os.fork()",
    "os.write(alive, b'r')",
    "select.select([lifeline], [], [], own_end)",
    "os._exit(0)",
)


def end_of_file(fd: int, deadline: float) -> float | None:
    """Wait until ``deadline``, a time.monotonic value, for end of file on
    ``fd``, the non-blocking read end of a FIFO whose writers have opened it,
    and return the time it was seen, a clock reading taken after the read
    that returned it, or None if it was not seen by the deadline. A reading
    later than the deadline counts as not seen, so an end of file that came
    late, or that the process saw late because it was not scheduled, is
    never taken. A byte read on the way is dropped."""
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        readable, _write, _error = select.select([fd], [], [], remaining)
        if readable:
            try:
                if os.read(fd, 1) == b"":
                    seen = time.monotonic()
                    return seen if seen <= deadline else None
            except BlockingIOError:
                pass


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

    def test_a_capped_child_that_hangs_reports_the_cap_not_the_timeout(self):
        # The cap check comes before the timeout check, so a child that fills
        # stdout to the cap and then hangs past the timeout is unavailable
        # naming the cap, not the timeout. The 1 second timeout starts only
        # once the child has filled stdout and written its ready file, polled
        # for at most 60 seconds, so a busy host cannot fire it early.
        cap = client.output_cap(client.RESULT_LIMIT)
        real_wait = client.wait_child
        seen = set()
        with tempfile.TemporaryDirectory() as tmp:
            ready = Path(tmp) / "ready"
            tool = self.stub(tmp, (
                "import os, sys, time\n"
                "sys.stdin.read()\n"
                "for _ in range(16):\n"
                "    try:\n"
                "        os.write(1, b'x' * 65536)\n"
                "    except OSError:\n"
                "        pass\n"
                "open('ready', 'w').write('ready')\n"
                "time.sleep(60)\n"
            ))

            def wait_when_ready(proc, timeout):
                if proc.pid not in seen:
                    seen.add(proc.pid)
                    deadline = time.monotonic() + 60
                    while not ready.exists() and time.monotonic() < deadline:
                        if real_wait(proc, 0.05):
                            return True
                return real_wait(proc, timeout)

            with mock.patch.object(client, "wait_child", wait_when_ready):
                with self.assertRaises(client.Unavailable) as caught:
                    client.run_extractor("baseline", {}, timeout=1, tool=tool)
            self.assertTrue(ready.exists(), "the child did not get ready")
        self.assertEqual(caught.exception.reason, f"wrote stdout up to the output cap of {cap} bytes")

    def test_a_child_that_does_not_end_is_killed_with_its_group(self):
        """The client kills the whole group of a child past its timeout.

        This test asserts nothing about the client's reap: the check's
        finally clause reaps a child that the client left unreaped, so a
        client that skips its wait for the child after the kill passes it.
        2 other tests fail such a client:
        test_a_client_that_kills_only_the_leader_fails_the_check, whose
        SIGTERM subtest expects the reason "could not be reaped", and
        test_a_child_that_a_kill_does_not_end_is_left_unreaped, which
        asserts that reason in full."""
        # The stub's own end comes after the latest end of file the check
        # can take. Derived: started is read before the client starts the
        # stub, so each stub process enters its wait after started, and its
        # own end comes after started + OWN_END_SECONDS. The check takes end
        # of file only as end_of_file returns it, a clock reading taken
        # after the read that saw it and no later than returned +
        # CHECK_SECONDS, and before that it asserts that returned - started,
        # less the poll, is under RUN_SECONDS. The poll lasts POLL_SECONDS
        # at most, plus its last step, 1 real wait of 0.05 seconds and 1
        # read, whose length the code does not bound. So the check takes no
        # end of file seen after started + POLL_SECONDS + RUN_SECONDS +
        # CHECK_SECONDS, 85 seconds, plus that step, and the 5 seconds left
        # before the own end cover the step. Should the step take longer,
        # the own-end assertion fails a group that ended on its own rather
        # than pass it.
        self.assertGreater(OWN_END_SECONDS, POLL_SECONDS + RUN_SECONDS + CHECK_SECONDS)
        self.check_group_kill()

    def check_group_kill(self, check: float = CHECK_SECONDS, own_end: float = OWN_END_SECONDS, witness=None,
                         end_bound: float | None = None, starts: list | None = None):
        # The stub child (GROUP_STUB) forks a member into its group and
        # writes the ready byte to the FIFO alive, and its 2 processes then
        # wait for the release, end of file on the FIFO lifeline, or for their
        # own end, own_end seconds after each enters that wait, which the
        # stub reads from the file own_end that this check writes. The client's
        # first wait is held back until the ready byte is read, polled for at
        # most POLL_SECONDS, so a busy host cannot fire the 1 second timeout
        # before the member exists, and a child that is not ready when the
        # poll ends fails the check. The client must ask that first wait for
        # exactly its 1 second timeout; the wait itself, the group kill and
        # the reap are the real ones. The first real wait must also last at
        # least that timeout, timed from a clock read just before the call
        # to one just after its return. Derived: a real wait that times out
        # returns only once the clock has reached its entry plus the
        # timeout, so a correct client never fails this, and a client whose
        # real wait gives up early fails it unless the time the 2 clock
        # reads and the call add makes up the whole shortfall. The call adds
        # its entry and return and the wait's overrun past its own
        # deadline, its last sleep running over and the waitpid and clock
        # read after it. The code bounds none of these, so a client that
        # gives up early by more than the 2 clock reads take can still pass,
        # by a margin that the host sets. The client's
        # run, from started to returned, less the poll that holds its first
        # wait, must end within RUN_SECONDS.
        #
        # The client's reason is checked first, so a client that fails for
        # another reason is reported with that reason. alive must then read
        # end of file, seen by a clock reading no later than check seconds
        # after the client returns, which shows that no process of the
        # group still holds it: the client
        # killed the member too, not only the leader. That end of file must
        # also come less than own_end seconds after the client's start, or
        # less than end_bound seconds when a caller passes a smaller
        # end_bound, so however late the child gets ready, the group's own
        # end is never taken for the kill.
        #
        # The check sends no signal, so it never names a process by an id
        # that may have been reused. Its finally clause closes lifeline,
        # which ends any process of the group that the client left, and then
        # reaps a child that the client left unreaped; the verdict depends on
        # neither. When the test process ends without unwinding, as on
        # SIGKILL or SIGTERM, the kernel closes lifeline. After either
        # release a stub process ends as GROUP_STUB's comment derives: at
        # once if it is past its first read of lifeline, as the leader and the
        # member are once the ready byte has been read, and otherwise when it
        # reaches that read, which nothing in the test bounds.
        # witness, when given, is called with the path of alive before the
        # stub starts, so that a caller can open a reader of its own.
        #
        # own_end reaches the stub only as the text of the file own_end,
        # written with str after witness is called, and the stub reads it
        # with float, so a plain int or float passed as own_end reaches the
        # stub only as a number. A text that float does not take raises in
        # the stub before it opens either FIFO, so the check fails.
        # end_bound, when given and smaller than own_end, takes the place of
        # own_end in the own-end assertion only; a larger end_bound leaves
        # own_end as the bound. The stub still reads own_end.
        # starts, when given, is a list to which the check appends started,
        # the clock reading it adds the bound to, so a caller can measure
        # from the same instant as the own-end assertion.
        #
        # Residual, not checked, of this check and of its tripwire,
        # test_the_check_names_no_signal_function:
        # - What the tripwire's first 2 assertions miss: an edit that changes
        #   what self.stub finds without an entry in the classes they read or
        #   an attribute of the tripwire's own instance, such as a
        #   __getattribute__ method or an assignment to self.__class__; a class
        #   derived from BoundsTest that does not exist when the tripwire runs,
        #   such as one in another module; an attribute set on an instance
        #   other than the tripwire's own, such as one that a subclass's setUp
        #   sets where the tripwire runs as BoundsTest.<test name>, not on that
        #   subclass as the whole file runs it; a replacement whose qualified
        #   name and first line, which a value gives for itself, are those of
        #   the def statement; a binding of check_group_kill, end_of_file or
        #   stub by a name given as a string anywhere other than those classes,
        #   that instance and the module's end_of_file; a change made after the
        #   tripwire runs or undone before it; an edit that rebinds a name or
        #   function the tripwire calls, such as class_bindings, SUBCLASSES,
        #   BoundsTest, a builtin or a function of ast, or that replaces the
        #   tripwire; an edit that changes the interpreter's own records, as
        #   through ctypes; and an entry hidden by a route that the walk does
        #   not model, such as a metaclass whose mro method puts BoundsTest in
        #   the order of a class that does not have it among its bases, or a
        #   dict subclass, set as the tripwire's instance __dict__, whose items
        #   method leaves out an entry. Code in the test file runs in the
        #   process that the tripwire checks, so no check there holds against
        #   all such code.
        # - What the tripwire's name scan misses: every route to a signal other
        #   than a name in SIGNAL_NAMES in the functions it reads. Such an edit
        #   passes the tripwire unless it also fails 1 of its other 3
        #   assertions: it changes the stub's calls, which the STUB_CALLS pin
        #   rejects, as it rejects os.__dict__["kill"](os.getppid(), 0) added
        #   to the stub, or it binds check_group_kill, end_of_file or stub in a
        #   way the first 2 assertions reject, as they reject a subclass of
        #   BoundsTest whose stub, bound by a def statement, calls
        #   getattr(os, "kill"). Passes of the name scan, examples, not a
        #   complete list: in check_group_kill, getattr(os, "kill") with a
        #   literal name, getattr with a computed name, such as
        #   getattr(os, "ki" + "ll"), os.__dict__["kill"], vars(os)["kill"] and
        #   a shell kill through os.system; a value a caller passes, such as
        #   the witness, which the check calls and which can run any code; a
        #   method of self that a subclass overrides, such as assertLess; a
        #   module global or builtin that a caller rebinds, such as GROUP_STUB,
        #   or a function of os or the client, as the tests here rebind
        #   os.killpg; the body of a decorator; and the code outside those
        #   functions, the client, whose group kill, the behaviour under test,
        #   is the 1 signal that a run of the group-kill test sends, and the
        #   standard library.
        # - The check takes the text of own_end with str, compares end_bound
        #   with own_end when given, and adds check and own_end, or end_bound
        #   in its place when smaller, to clock readings, so a value with
        #   methods of its own runs them in the test. str
        #   runs before the check reads GROUP_STUB, so a method of own_end can
        #   change the stub's source, for example by rebinding GROUP_STUB, and
        #   so add code to the stub. The callers in the test file pass
        #   numbers.
        # - After the release, by the finally clause or by the kernel when the
        #   test process ends, a stub process that has not yet reached its
        #   first read of lifeline ends only when it reaches that read, so it
        #   outlives the release, and a killed test process, by the rest of its
        #   start-up, which nothing in the test bounds. This is derived from
        #   the stub's order. The leader and the member are past that read once
        #   the ready byte has been read, so this arises only for a release
        #   that comes before the test has read that byte: during the poll, or
        #   after a poll that ran out without it.
        # - While the test process is alive but neither closes lifeline nor
        #   ends, as when it is stopped, each stub process lives until its own
        #   end, own_end seconds after it enters its wait, 90 in the group-kill
        #   test. It enters that wait only after start-up, its first read of
        #   lifeline and, for the member, the fork, so its life from its start
        #   is that start-up plus own_end seconds, and nothing in the test
        #   bounds the start-up.
        # - The first-wait timing passes a client whose real wait gives up
        #   early by less than the time the gate's 2 clock reads and the call
        #   add. The call's share includes the wait's overrun past its own
        #   deadline, which the code does not bound, so the margin is set by
        #   the host and is more than the 2 clock reads take.
        # - A process that inherits the write end of lifeline and outlives the
        #   test would keep the stub alive up to its own end. Only a fork
        #   without exec in the test process could do that: the descriptor is
        #   not inheritable across exec, and the test file forks only inside
        #   the stub's source.
        # - A stub process that closed its copy of alive before it ended would
        #   hide from the check. The stub is the test's own code, and its calls
        #   are pinned, so this arises only from an altered stub.
        # - A process that SIGKILL cannot end keeps alive open, and the check
        #   then fails.
        # - When the client gives up without reaping, the finally clause reaps
        #   the leader after the release if it ends within the 5 second reap
        #   grace. A leader that has not ended by then, or one left when the
        #   test process ends without unwinding, stays unreaped until Python's
        #   own collection of finished children or the process that adopts it
        #   reaps it. A leader that has ended holds no descriptor while it
        #   waits to be reaped; one still running, such as a stopped one, holds
        #   the descriptors it has open, the write end of alive among them once
        #   it has opened it.
        # - No signal ends the stub while it ignores or blocks that signal.
        #   Unless the test thread blocks it, SIGPIPE or SIGXFSZ can end the
        #   stub before Python ignores it, and SIGTERM, SIGINT or SIGHUP can
        #   end it before its source ignores it if the test process does not
        #   ignore it. Examples of a signal that ends it early, not a complete
        #   list: SIGKILL, and SIGUSR1 when the test neither ignores nor blocks
        #   SIGUSR1. Without such a signal, it ends on the release or at its
        #   own end, unless it is stopped, as by SIGSTOP.
        # - A correct client still fails the test if the child is not ready
        #   within 60 seconds. It also fails each test that runs the check if
        #   the test process is delayed past 1 of the bounds the check
        #   asserts, or so long, at any point after the client starts the
        #   stub, before or after the test reads the ready byte, that the
        #   stub reaches its own end before the client's first wait times
        #   out. The run bound leaves out the poll, so it does not measure a
        #   delay during the poll.
        # - The design needs FIFOs in the temporary folder, select on them, and
        #   the Linux behaviour that a FIFO reader opened while a writer exists
        #   sees end of file when the last writer closes. The behaviour stated
        #   here is that on Linux; for other platforms and for the Python 3.9
        #   floor it is not established.
        real_wait = client.wait_child
        real_popen = subprocess.Popen
        children = []
        seen = set()
        ready_seen = []
        first_timeouts = []
        first_waits = []
        poll_began = []
        ready_at = []
        with tempfile.TemporaryDirectory() as tmp:
            alive_path = Path(tmp) / "alive"
            lifeline_path = Path(tmp) / "lifeline"
            held = []
            try:
                os.mkfifo(alive_path)
                os.mkfifo(lifeline_path)
                held.append(os.open(alive_path, os.O_RDONLY | os.O_NONBLOCK))
                alive = held[0]
                # A non-blocking write end of a FIFO opens only while a read
                # end is open, so a read end is held just long enough for it.
                reader = os.open(lifeline_path, os.O_RDONLY | os.O_NONBLOCK)
                try:
                    held.append(os.open(lifeline_path, os.O_WRONLY | os.O_NONBLOCK))
                finally:
                    os.close(reader)
                if witness is not None:
                    witness(alive_path)
                (Path(tmp) / "own_end").write_text(str(own_end), encoding="utf-8")
                tool = self.stub(tmp, GROUP_STUB)

                def popen(*args, **kwargs):
                    children.append(real_popen(*args, **kwargs))
                    return children[-1]

                def ready() -> bool:
                    try:
                        return os.read(alive, 1) == b"r"
                    except BlockingIOError:
                        return False

                def wait_when_ready(proc, timeout):
                    if proc.pid not in seen:
                        seen.add(proc.pid)
                        poll_began.append(time.monotonic())
                        deadline = poll_began[0] + POLL_SECONDS
                        got_ready = ready()
                        while not got_ready and time.monotonic() < deadline:
                            if real_wait(proc, 0.05):
                                return True
                            got_ready = ready()
                        ready_seen.append(got_ready)
                        first_timeouts.append(timeout)
                        ready_at.append(time.monotonic())
                        ended = real_wait(proc, timeout)
                        first_waits.append(time.monotonic() - ready_at[0])
                        return ended
                    return real_wait(proc, timeout)

                started = time.monotonic()
                if starts is not None:
                    starts.append(started)
                with mock.patch.object(client.subprocess, "Popen", popen), \
                        mock.patch.object(client, "wait_child", wait_when_ready):
                    with self.assertRaises(client.Unavailable) as caught:
                        client.run_extractor("baseline", {}, timeout=1, tool=tool)
                returned = time.monotonic()
                self.assertEqual(caught.exception.reason, "was not seen to end within 1 seconds")
                self.assertEqual(ready_seen, [True], "the child was not ready when the poll ended")
                self.assertEqual(first_timeouts, [1], "the client's first wait was not its 1 second timeout")
                self.assertGreaterEqual(first_waits[0], 1, "the client's first wait gave up before its 1 second timeout")
                self.assertLess(returned - started - (ready_at[0] - poll_began[0]), RUN_SECONDS)
                ended = end_of_file(alive, returned + check)
                if ended is None:
                    self.fail(f"a process of the child's group outlived the client's kill: alive did not reach "
                              f"end of file within {check} seconds after the client returned")
                bound = own_end if end_bound is None else min(end_bound, own_end)
                self.assertLess(ended, started + bound,
                                "the group may have ended on its own, so its end does not show the kill")
            finally:
                # The release: lifeline first, then alive. A child that the
                # client left unreaped is reaped here if it ends within the
                # reap grace; this sends no signal, and the verdict does not
                # depend on it.
                for fd in reversed(held):
                    os.close(fd)
                for proc in children:
                    if proc.returncode is None:
                        with contextlib.suppress(subprocess.TimeoutExpired):
                            proc.wait(timeout=client.REAP_GRACE_SECONDS)

    def test_a_client_that_kills_only_the_leader_fails_the_check(self):
        # The check runs against 2 stand-ins for the client's group kill,
        # each called while the child is still unreaped: a kill of the
        # leader alone, which leaves the member running, and a SIGTERM to the
        # group, which the stub ignores. Each run must fail, the first at the
        # end of file check and the second at the reason, since the client
        # then gives up after the reap grace. A reader of alive that this
        # test opens before the run must then see end of file before the
        # stub's own end could come, so the release, not that own end, ended
        # what the client left. Derived from the order: the test reads the
        # clock when it opens that reader, before the check starts the stub,
        # and each stub process reaches its own end OWN_END_SECONDS after it
        # enters its wait, so an end of file seen no later than that reading
        # plus OWN_END_SECONDS came before any own end. Only a stub process
        # past its first read of lifeline opens alive, and such a process
        # exits as soon as the release comes. A stub not past that read at
        # the release exits there without opening alive, and on Linux select
        # reports nothing for a FIFO reader that no writer has opened since
        # it was opened, so end_of_file sees no end of file and this
        # assertion then fails rather than pass.
        real_killpg = os.killpg
        for label, kill, message in (
            ("a kill of the leader only", lambda group, sig: os.kill(group, sig),
             "a process of the child's group outlived the client's kill"),
            ("SIGTERM to the group", lambda group, sig: real_killpg(group, signal.SIGTERM),
             "could not be reaped"),
        ):
            with self.subTest(label):
                witnesses = []
                try:
                    with mock.patch.object(client.os, "killpg", kill):
                        with self.assertRaises(AssertionError) as caught:
                            self.check_group_kill(check=2, witness=lambda path: witnesses.append(
                                (os.open(path, os.O_RDONLY | os.O_NONBLOCK), time.monotonic())))
                    self.assertIn(message, str(caught.exception))
                    self.assertEqual(len(witnesses), 1)
                    fd, opened = witnesses[0]
                    self.assertIsNotNone(end_of_file(fd, opened + OWN_END_SECONDS),
                                         "a process of the group outlived the failed check")
                finally:
                    for fd, _opened in witnesses:
                        os.close(fd)

    def test_an_end_of_file_after_the_own_end_bound_does_not_pass(self):
        # The own-end assertion must fail an end of file that comes no
        # earlier than its bound after the client's start, since such an end
        # could be the group's own end, as for a child that gets ready so
        # late that the stub's own end falls inside the check. Each subtest
        # runs the check against the real client and the stub with its own
        # end of OWN_END_SECONDS, so no subtest lets the stub's own end fall
        # inside the check. Each must fail at the own-end assertion, with no
        # dependence on how long any step takes:
        # - A smaller bound, an end_bound of 0.5 seconds: the check asserts
        #   that the client's first real wait lasted at least 1 second and
        #   reads the end of file only after the client returns, so the end
        #   of file it takes comes at least 1 second after started, past
        #   the bound.
        # - The default bound, own_end, with no end_bound, and a larger
        #   bound, an end_bound of 2 * OWN_END_SECONDS, which the check
        #   limits to own_end: the check's end_of_file is replaced for the
        #   run by a stand-in that takes the real one's reading, so a group
        #   that outlives the kill still fails at the end of file check,
        #   and returns the check's started reading, which the check
        #   appends to starts, plus OWN_END_SECONDS: the same instant and
        #   value whose sum is the check's default bound. The reading the
        #   check takes is that bound exactly, the same float, so the
        #   assertion fails it, while a bound raised above own_end by
        #   1 second or by 0.5 seconds takes that reading for the kill and
        #   fails this test, as a test mutant for each raise shows; a
        #   smaller raise may pass this test.
        # Like each test that runs the check, it can still fail on a delay of
        # the test process, as the residual list in check_group_kill states.
        real_end_of_file = end_of_file
        starts = []

        def end_at_the_bound(fd, deadline):
            seen = real_end_of_file(fd, deadline)
            return None if seen is None else starts[-1] + OWN_END_SECONDS

        for label, end_bound, stand_in in (
            ("a smaller bound", 0.5, real_end_of_file),
            ("the default bound", None, end_at_the_bound),
            ("a larger bound", 2 * OWN_END_SECONDS, end_at_the_bound),
        ):
            with self.subTest(label):
                with mock.patch.object(sys.modules[__name__], "end_of_file", stand_in):
                    with self.assertRaises(AssertionError) as caught:
                        self.check_group_kill(end_bound=end_bound, starts=starts)
                self.assertIn("the group may have ended on its own", str(caught.exception))

    def test_an_interrupted_check_releases_its_group(self):
        # The client's group kill raises KeyboardInterrupt, as a Ctrl-C at
        # that point would, so the client neither kills nor reaps the child.
        # The interrupt must pass through the check, and a reader of alive
        # that this test opens before the run must see end of file before
        # the stub's own end could come, so the check's finally clause
        # released the group; that bound is derived as in
        # test_a_client_that_kills_only_the_leader_fails_the_check. Only the
        # injected interrupt is caught; any other, such as a real Ctrl-C, is
        # raised again.
        injected = []

        def interrupt(group, sig):
            injected.append(KeyboardInterrupt("injected"))
            raise injected[-1]

        witnesses = []
        try:
            try:
                with mock.patch.object(client.os, "killpg", interrupt):
                    self.check_group_kill(witness=lambda path: witnesses.append(
                        (os.open(path, os.O_RDONLY | os.O_NONBLOCK), time.monotonic())))
            except KeyboardInterrupt as error:
                if not injected or error is not injected[-1]:
                    raise
            else:
                self.fail("the injected interrupt did not pass through the check")
            self.assertEqual(len(witnesses), 1)
            fd, opened = witnesses[0]
            self.assertIsNotNone(end_of_file(fd, opened + OWN_END_SECONDS),
                                 "a process of the group outlived the interrupted check")
        finally:
            for fd, _opened in witnesses:
                os.close(fd)

    def test_a_stub_started_after_the_release_ends_at_once(self):
        # A stub that opens lifeline only after the test has closed it, as
        # when an interrupt ends the check before the stub starts, would get
        # no report from select at its wait and live until its own end. Its
        # first read sees end of file there, so it must find no writer and
        # exit there, before it opens alive. A reader of alive is held, so
        # that a stub past that read opens alive, forks and writes the ready
        # byte rather than fail at that open. The test waits for the stub's
        # run to end and then reads alive: no byte shows that the stub
        # exited at its first read. The outcome rests on that order, not on
        # how long the stub's start-up takes. The own end is 10 seconds, so a
        # stub that waits for it still ends, without being signalled, and
        # this test then fails at the ready byte.
        with tempfile.TemporaryDirectory() as tmp:
            os.mkfifo(Path(tmp) / "alive")
            os.mkfifo(Path(tmp) / "lifeline")
            alive = os.open(Path(tmp) / "alive", os.O_RDONLY | os.O_NONBLOCK)
            try:
                reader = os.open(Path(tmp) / "lifeline", os.O_RDONLY | os.O_NONBLOCK)
                try:
                    os.close(os.open(Path(tmp) / "lifeline", os.O_WRONLY | os.O_NONBLOCK))
                finally:
                    os.close(reader)
                (Path(tmp) / "own_end").write_text("10", encoding="utf-8")
                tool = self.stub(tmp, GROUP_STUB)
                proc = subprocess.run([sys.executable, "-I", str(tool)], cwd=tmp, capture_output=True)
                wrote = os.read(alive, 1)
            finally:
                os.close(alive)
        self.assertEqual((proc.returncode, proc.stderr), (0, b""))
        self.assertEqual(wrote, b"", "the stub went past its first read of lifeline")

    def test_an_end_of_file_seen_after_its_deadline_is_not_taken(self):
        # end_of_file reads the clock after the read that returns end of
        # file, and must return None when that reading is past the deadline,
        # since a time after the deadline would let a late end of file pass
        # the check. A select that returns 0.2 seconds late stands in for
        # the scheduling delay of a busy host: end_of_file reads a stand-in
        # clock that only that select moves, 0.2 seconds at each return, so
        # the outcome rests on that clock alone, not on how long any step
        # takes. End of file is there from the start, so with a 0.05 second
        # deadline the reading is past it. The control, the same delay with
        # a 5 second deadline, must give a time no later than that deadline.
        real_select = select.select
        clock = [0.0]

        def late_select(*args):
            result = real_select(*args)
            clock[0] += 0.2
            return result

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fifo"
            os.mkfifo(path)
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            try:
                os.close(os.open(path, os.O_WRONLY | os.O_NONBLOCK))
                with mock.patch.object(select, "select", late_select), \
                        mock.patch.object(time, "monotonic", lambda: clock[0]):
                    self.assertIsNone(end_of_file(fd, time.monotonic() + 0.05),
                                      "an end of file seen after the deadline was taken")
                    deadline = time.monotonic() + 5
                    ended = end_of_file(fd, deadline)
                self.assertIsNotNone(ended, "an end of file seen before the deadline was not taken")
                self.assertLessEqual(ended, deadline)
            finally:
                os.close(fd)

    def test_the_check_names_no_signal_function(self):
        # A tripwire, not a proof. The check's design needs no signal: it
        # sees the group only through alive and ends it by closing lifeline.
        # This reads the syntax tree of check_group_kill with the functions
        # it defines, end_of_file, BoundsTest.stub and GROUP_STUB, and
        # asserts, in this order: that the only bindings of BOUND_NAMES that
        # bindings finds anywhere in the test file's syntax are 1 def
        # statement for each name; that class_bindings finds only
        # BoundsTest's own check_group_kill and stub, each the function its
        # def statement made, judged by qualified name and first line, that
        # the module's end_of_file is, judged so, the function its def
        # statement made, and that own_bindings finds no attribute named 1
        # of BOUND_NAMES that the test's own instance holds of its own; that
        # GROUP_STUB makes exactly STUB_CALLS, in that order, the order its
        # bounds rest on; and that no name, attribute or import in any of
        # them is in SIGNAL_NAMES.
        # The first assertion fails an edit that adds a binding that
        # bindings counts or removes 1 of the 3 def statements. The second
        # fails an edit that, in a form that
        # test_the_tripwire_sees_each_binding_of_its_names has a case for,
        # gives BoundsTest, a class that has it among its bases, directly or
        # through other such classes, or a class in their method resolution
        # orders another entry named 1 of BOUND_NAMES, replaces 1 of
        # BoundsTest's 2 entries or the module's end_of_file with a value
        # whose qualified name or first line differs, or gives this test's
        # instance such an attribute. It reads those classes and that
        # instance through the descriptors of type and TestCase, lists each
        # namespace with its items method, compares classes by identity and
        # names as plain str, so these overrides, each of which those cases
        # make, hide no entry from it: a class's __subclasses__; a
        # metaclass's __subclasses__, __mro__, __dict__, __eq__ or
        # __getattribute__, the last also giving a false __qualname__; an
        # entry whose name is a str subclass; and an instance's __dict__
        # property. It does not hold against all code in this file, which
        # can hide an entry by routes that the walk does not model, such as
        # these 2: a metaclass whose mro method puts BoundsTest in the order
        # of a class that does not have it among its bases, so that
        # type.__subclasses__ does not list that class; and a dict subclass,
        # set as this test's instance __dict__, whose items method leaves
        # out an entry.
        # So a stub bound in this file on BoundsTest or a class that has it
        # among its bases by a def or async def statement or by an
        # assignment, a lambda among them, fails the first, and one bound
        # there by a name given as a string, as setattr, type and a mixin's
        # namespace take it, fails the second if it is in place when this
        # test runs. The case test,
        # test_the_tripwire_sees_each_binding_of_its_names, has a case for
        # each of these forms, for each form that bindings names, and for
        # each such override. The name scan fails an edit that uses a signal
        # function by 1 of the names in SIGNAL_NAMES there, such as
        # os.kill(os.getpid(), 0) added to the check.
        # What the first 2 assertions miss and what the name scan misses are
        # the first 2 items of the residual list in check_group_kill's
        # comment.
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        roots = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name in BOUND_NAMES]
        self.assertEqual(bindings(tree), [(name, "FunctionDef") for name in BOUND_NAMES])
        lines = {node.name: min([node.lineno] + [decorator.lineno for decorator in node.decorator_list])
                 for node in roots}
        self.assertEqual(
            (class_bindings(BoundsTest), described(end_of_file), own_bindings(self)),
            ([("BoundsTest", name, "BoundsTest." + name, lines[name]) for name in ("check_group_kill", "stub")],
             ("end_of_file", lines["end_of_file"]), []))
        stub_tree = ast.parse(GROUP_STUB)
        stub_calls = sorted((node for node in ast.walk(stub_tree) if isinstance(node, ast.Call)),
                            key=lambda node: (node.lineno, node.col_offset))
        self.assertEqual(tuple(ast.unparse(node) for node in stub_calls), STUB_CALLS)
        nodes = [node for root in roots + [stub_tree] for node in ast.walk(root)]
        names = [getattr(node, "id", None) or getattr(node, "attr", None) for node in nodes
                 if isinstance(node, (ast.Name, ast.Attribute))]
        names += [name for node in nodes if isinstance(node, ast.alias) for name in (node.name, node.asname)]
        self.assertEqual(sorted(set(names) & set(SIGNAL_NAMES)), [])

    def test_the_tripwire_sees_each_binding_of_its_names(self):
        # A case for each form of binding stub that the tripwire's first 2
        # assertions are meant to see, each form that bindings names among
        # them, for each override that the tripwire's comment says they
        # read past, and for 1 form that they miss. Each form is source text,
        # run with exec on a stand-in, Base, a TestCase whose stub is a lambda,
        # so that it adds no binding to this file's syntax and no class
        # derived from BoundsTest. Each case gives what bindings counts in
        # the form, each (class, qualified name) that class_bindings finds
        # from Base, and what own_bindings finds on an instance of Sub after
        # its setUp. The match cases run only where match parses, on Python
        # 3.10 or later.
        base = "class Base(TestCase):\n    stub = lambda self: 0\n\n"
        indirect = "def indirect(self):\n    return 1\n\n"
        hide = "\nsetattr(Sub, 'st' + 'ub', indirect)\n"
        found = [("Base", "Base.<lambda>")]
        sub = found + [("Sub", "indirect")]
        forms = {
            "def": ("class Sub(Base):\n    def stub(self):\n        return 1\n",
                    [("stub", "FunctionDef")], found + [("Sub", "Sub.stub")], []),
            "async def": ("class Sub(Base):\n    async def stub(self):\n        return 1\n",
                          [("stub", "AsyncFunctionDef")], found + [("Sub", "Sub.stub")], []),
            "class": ("class Sub(Base):\n    class stub:\n        pass\n",
                      [("stub", "ClassDef")], found + [("Sub", "Sub.stub")], []),
            "assignment": (indirect + "class Sub(Base):\n    stub = indirect\n", [("stub", "Name")], sub, []),
            "annotated assignment": (indirect + "class Sub(Base):\n    stub: object = indirect\n",
                                     [("stub", "Name")], sub, []),
            "augmented assignment": ("class Sub(Base):\n    stub = 0\n    stub += 1\n",
                                     [("stub", "Name"), ("stub", "Name")], found + [("Sub", "int")], []),
            ":=": (indirect + "class Sub(Base):\n    (stub := indirect)\n", [("stub", "Name")], sub, []),
            "tuple target": (indirect + "class Sub(Base):\n    stub, other = indirect, 0\n",
                             [("stub", "Name")], sub, []),
            "starred target": ("class Sub(Base):\n    *stub, = (1,)\n",
                               [("stub", "Name")], found + [("Sub", "list")], []),
            "attribute": (indirect + "class Sub(Base):\n    pass\n\nSub.stub = indirect\n",
                          [("stub", "Attribute")], sub, []),
            "lambda": ("class Sub(Base):\n    stub = lambda self: 1\n",
                       [("stub", "Name")], found + [("Sub", "Sub.<lambda>")], []),
            "deletion": ("class Sub(Base):\n    stub = 1\n    del stub\n",
                         [("stub", "Name"), ("stub", "Name")], found, []),
            "for target": ("class Sub(Base):\n    for stub in (1,):\n        pass\n",
                           [("stub", "Name")], found + [("Sub", "int")], []),
            "with target": ("class Sub(Base):\n    with memoryview(b'') as stub:\n        pass\n",
                            [("stub", "Name")], found + [("Sub", "memoryview")], []),
            "comprehension target": ("class Sub(Base):\n    values = [stub for stub in (1,)]\n",
                                     [("stub", "Name")], found, []),
            "except target": ("class Sub(Base):\n    try:\n        raise ValueError\n"
                              "    except ValueError as stub:\n        pass\n",
                              [("stub", "ExceptHandler")], found, []),
            "match capture": ("class Sub(Base):\n    match 1:\n        case stub:\n            pass\n",
                              [("stub", "MatchAs")], found + [("Sub", "int")], []),
            "match star": ("class Sub(Base):\n    match (1,):\n        case (*stub,):\n            pass\n",
                           [("stub", "MatchStar")], found + [("Sub", "list")], []),
            "match rest": ("class Sub(Base):\n    match {}:\n        case {**stub}:\n            pass\n",
                           [("stub", "MatchMapping")], found + [("Sub", "dict")], []),
            "import": ("class Sub(Base):\n    from os import getpid as stub\n",
                       [("stub", "alias")], found + [("Sub", "getpid")], []),
            "parameter": ("class Sub(Base):\n    def method(self, stub=1):\n        return stub\n",
                          [("stub", "arg")], found, []),
            "keyword argument": ("class Sub(Base):\n    values = dict(stub=1)\n", [("stub", "keyword")], found, []),
            "setattr": (indirect + "class Sub(Base):\n    pass\n" + hide, [], sub, []),
            "type": (indirect + "Sub = type('Sub', (Base,), {'st' + 'ub': indirect})\n", [], sub, []),
            "mixin": (indirect + "class Mixin:\n    pass\n\nsetattr(Mixin, 'st' + 'ub', indirect)\n\n"
                      "class Sub(Mixin, Base):\n    pass\n",
                      [], found + [("Mixin", "indirect")], []),
            "base": (indirect + "class Sub(Base):\n    pass\n\nsetattr(Base, 'st' + 'ub', indirect)\n",
                     [], [("Base", "indirect")], []),
            "instance": (indirect + "class Sub(Base):\n    def setUp(self):\n"
                         "        setattr(self, 'st' + 'ub', indirect)\n",
                         [], found, ["stub"]),
            "str subclass name": (indirect + "class Name(str):\n    def __eq__(self, other):\n        return False\n\n"
                                  "    __hash__ = str.__hash__\n\n"
                                  "Sub = type('Sub', (Base,), {Name('st' + 'ub'): indirect})\n",
                                  [], sub, []),
            "__subclasses__": (indirect + "class Hidden(Base):\n    @classmethod\n    def __subclasses__(cls):\n"
                               "        return []\n\nclass Sub(Hidden):\n    pass\n" + hide, [], sub, []),
            "metaclass __subclasses__": (indirect + "class Meta(type):\n    def __subclasses__(cls):\n"
                                         "        return []\n\nclass Hidden(Base, metaclass=Meta):\n    pass\n\n"
                                         "class Sub(Hidden):\n    pass\n" + hide, [], sub, []),
            "metaclass __mro__": (indirect + "class Meta(type):\n    __mro__ = property(lambda cls: (cls,))\n\n"
                                  "class Mixin:\n    pass\n\nsetattr(Mixin, 'st' + 'ub', indirect)\n\n"
                                  "class Sub(Mixin, Base, metaclass=Meta):\n    pass\n",
                                  [], found + [("Mixin", "indirect")], []),
            "metaclass __dict__": (indirect + "class Meta(type):\n    __dict__ = property(lambda cls: {})\n\n"
                                   "class Sub(Base, metaclass=Meta):\n    pass\n" + hide, [], sub, []),
            "metaclass __eq__": (indirect + "class Meta(type):\n    def __eq__(cls, other):\n        return True\n\n"
                                 "    __hash__ = type.__hash__\n\nclass Sub(Base, metaclass=Meta):\n    pass\n" + hide,
                                 [], sub, []),
            "metaclass __getattribute__": (
                indirect + "class Meta(type):\n    def __getattribute__(cls, name):\n"
                "        fake = {'__subclasses__': lambda: [], '__mro__': (), '__dict__': {}, '__qualname__': 'Base'}\n"
                "        return fake[name] if name in fake else type.__getattribute__(cls, name)\n\n"
                "class Sub(Base, metaclass=Meta):\n    pass\n" + hide, [], sub, []),
            "instance __dict__": (indirect + "class Sub(Base):\n    __dict__ = property(lambda self: {})\n\n"
                                  "    def setUp(self):\n        setattr(self, 'st' + 'ub', indirect)\n",
                                  [], found, ["stub"]),
            "__getattribute__, missed": (
                indirect + "class Sub(Base):\n    def __getattribute__(self, name):\n"
                "        return (lambda: 1) if name == 'st' + 'ub' else object.__getattribute__(self, name)\n",
                [], found, []),
        }
        for form, (source, counted, owners, own) in forms.items():
            with self.subTest(form):
                if form.startswith("match") and sys.version_info < (3, 10):
                    self.skipTest("match parses only on Python 3.10 or later")
                namespace = {"TestCase": unittest.TestCase}
                exec(compile(base + source, form, "exec"), namespace)
                instance = namespace["Sub"]()
                instance.setUp()
                self.assertEqual(
                    (bindings(ast.parse(source)), [(row[0], row[2]) for row in class_bindings(namespace["Base"])],
                     own_bindings(instance)),
                    (counted, owners, own))
                if form.endswith("missed"):
                    self.assertEqual(instance.stub(), 1, "the missed form does not change what stub finds")

    def test_bound_constants_equal_the_gates(self):
        gate = _load("crc_gate_bounds", GATE)
        for name in ("CHILD_TIMEOUT_SECONDS", "REAP_GRACE_SECONDS", "RESULT_LIMIT", "ECHO_BYTES_PER_CHARACTER",
                     "STDERR_LIMIT", "EXTRACTOR_INTERNAL_ERROR"):
            with self.subTest(name):
                self.assertEqual(getattr(client, name), getattr(gate, name))
        self.assertEqual(
            (client.CHILD_TIMEOUT_SECONDS, client.REAP_GRACE_SECONDS, client.RESULT_LIMIT,
             client.ECHO_BYTES_PER_CHARACTER, client.STDERR_LIMIT),
            (20, 5, 65536, 12, 4096),
        )

    def test_a_child_that_a_kill_does_not_end_is_left_unreaped(self):
        # A child that a kill does not end, such as one in an uninterruptible
        # sleep, cannot be made in a test, so a stand-in child never ends:
        # every non-blocking waitpid sees it still running, and a blocking
        # wait fails the test, because it would block the client with no
        # bound. The client waits the timeout, kills the group, waits the
        # grace, and then gives up.
        waits = []

        class NeverEnds:
            pid = 999999999
            returncode = None

            def __init__(self, *args, **kwargs):
                pass

            def wait(self, timeout=None):
                raise AssertionError("a Popen wait, which reads a lost status as exit 0")

        def waitpid(pid, options):
            waits.append((pid, options, time.monotonic()))
            if options != os.WNOHANG:
                raise AssertionError("a blocking waitpid")
            return 0, 0

        kills = []
        reason = (f"could not be reaped (the client saw no end of it within "
                  f"{client.REAP_GRACE_SECONDS} seconds after its kill)")
        with mock.patch.object(client.subprocess, "Popen", NeverEnds), \
                mock.patch.object(client.os, "waitpid", waitpid), \
                mock.patch.object(client.os, "killpg", lambda pid, sig: kills.append((pid, sig))):
            started = time.monotonic()
            with self.assertRaises(client.Unavailable) as caught:
                client.run_extractor("baseline", {}, timeout=1)
            elapsed = time.monotonic() - started
            self.assertEqual(caught.exception.reason, reason)
            self.assertGreaterEqual(elapsed, 1 + client.REAP_GRACE_SECONDS)
            self.assertLess(elapsed, 1 + client.REAP_GRACE_SECONDS + 5)
            self.assertTrue(waits and all(pid == NeverEnds.pid for pid, _o, _t in waits), waits)
            kill_time = [t for _p, _o, t in waits]
            self.assertEqual(kills, [(NeverEnds.pid, signal.SIGKILL)])
            self.assertTrue(any(t >= started + 1 for t in kill_time))
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = client.main(["skill-release-date-client", "baseline"])
        self.assertEqual(code, 16)
        self.assertEqual(
            stderr.getvalue(),
            f"skill-release-date-client: skill-release-date.py {reason} in baseline, so the extractor is unavailable\n",
        )

    def test_a_child_whose_status_is_lost_is_unavailable(self):
        # The wait reports that the child is no longer a child of the client
        # (ChildProcessError), so its exit status is lost; Popen.wait would
        # read that as exit 0 and the reply would pass. The client exits 16.
        reply = "{\"op\": \"baseline\", \"outcome\": \"value\", \"value\": \"1.0.14\"}"
        reason = "could not be waited for (it is no longer a child of the client, so its exit status is lost)"
        pair = Pair(f"print({reply!r})\nraise SystemExit(1)\n")
        real_waitpid = os.waitpid

        def waitpid(pid, options):
            # Reap the child here, as another reaper would, then report it lost.
            real_waitpid(pid, 0)
            raise ChildProcessError(10, "No child processes")

        try:
            with mock.patch.object(client.os, "waitpid", waitpid), \
                    mock.patch.object(client, "RELEASE_DATE_TOOL", pair.root / "skill-release-date.py"), \
                    warnings.catch_warnings():
                # The client never saw the status, so it leaves the Popen
                # object unfinished, which warns when it is collected.
                warnings.simplefilter("ignore", ResourceWarning)
                with self.assertRaises(client.Unavailable) as caught:
                    client.run_extractor("baseline", {})
                self.assertEqual(caught.exception.reason, reason)
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()) as stdout:
                    code = client.main(["skill-release-date-client", "baseline"])
        finally:
            pair.close()
        self.assertEqual((code, stdout.getvalue()), (16, ""))
        self.assertEqual(
            stderr.getvalue(),
            f"skill-release-date-client: skill-release-date.py {reason} in baseline, so the extractor is unavailable\n",
        )

    def test_stdout_and_stderr_end_at_the_cap_under_ordinary_writes(self):
        # A child that writes far past the read bound, on stdout or on
        # stderr, with ordinary writes, ends with a file of exactly the cap:
        # its writes past it fail, and the client, seeing a final size that
        # reached the cap, is unavailable naming it. The child reports the
        # size it reached. Storage reserved past the end of a file is not
        # measured here.
        limit = client.RESULT_LIMIT
        cap = client.output_cap(limit)
        self.assertEqual(cap, limit + 2)
        for stream in ("stdout", "stderr"):
            with self.subTest(stream):
                body = (
                    "import os, sys\n"
                    f"handle = sys.{stream}.buffer\n"
                    "try:\n"
                    f"    for _ in range({20 * limit // 65536}):\n"
                    "        handle.write(b'x' * 65536)\n"
                    "        handle.flush()\n"
                    "except OSError:\n"
                    "    pass\n"
                    f"size = os.fstat({1 if stream == 'stdout' else 2}).st_size\n"
                    "open('wrote', 'w').write(str(size))\n"
                )
                pair = Pair(body)
                try:
                    code, out, err = pair.run("baseline")
                    wrote = int((pair.root / "wrote").read_text())
                finally:
                    pair.close()
                self.assertEqual(wrote, cap)
                self.assertEqual((code, out), (16, ""), err)
                self.assertIn(f"skill-release-date.py wrote {stream} up to the output cap of {cap} bytes in baseline", err)
                self.assertEqual(err.count("\n"), 1, err)

    def test_an_inherited_file_size_limit_below_the_cap_is_applied(self):
        # A caller can leave a file size limit below the cap: a hard one
        # (a CI job with ulimit -H -f, say), which a child without
        # CAP_SYS_RESOURCE cannot raise, or a soft one with no hard limit,
        # which the client keeps rather than raises. The child then gets that
        # limit as its cap, as both its soft and its hard limit, and a normal
        # reply still succeeds.
        hard = 50000
        self.assertLess(hard, client.output_cap(client.RESULT_LIMIT))
        for kind, limits in (("hard", f"({hard}, {hard})"), ("soft", f"({hard}, resource.RLIM_INFINITY)")):
            self.check_inherited_limit(kind, limits, hard)
        with mock.patch.object(client.resource, "getrlimit", lambda which: (hard, hard)):
            self.assertEqual(client.applied_cap(client.output_cap(client.RESULT_LIMIT)), hard)
        with mock.patch.object(client.resource, "getrlimit", lambda which: (hard, client.resource.RLIM_INFINITY)):
            self.assertEqual(client.applied_cap(client.output_cap(client.RESULT_LIMIT)), hard)
            self.assertEqual(client.applied_cap(1000), 1000)
        with mock.patch.object(client.resource, "getrlimit", lambda which: (100, 400)):
            self.assertEqual(client.applied_cap(1000), 100)
        with mock.patch.object(client.resource, "getrlimit", lambda which: (client.resource.RLIM_INFINITY, hard)):
            self.assertEqual(client.applied_cap(client.output_cap(client.RESULT_LIMIT)), hard)

    def check_inherited_limit(self, kind, limits, hard):
        """Run the client under the inherited file size limits ``limits``
        (Python source for a (soft, hard) pair) and check that the child
        gets ``hard`` as both limits and that a normal reply succeeds."""
        launch = (
            "import os, resource, sys\n"
            f"resource.setrlimit(resource.RLIMIT_FSIZE, {limits})\n"
            "os.execv(sys.executable, [sys.executable, \"-I\", *sys.argv[1:]])\n"
        )
        report = (
            "import json, resource, sys\n"
            "request = json.loads(sys.stdin.read())\n"
            "soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)\n"
            "message = 'fsize=%d/%d' % (soft, hard)\n"
            "print(json.dumps({'op': request['op'], 'outcome': 'malformed', 'message': message}))\n"
        )
        for label, body, words, expected in (
            ("the cap the child gets", report, ("requires-date", "1.0.15"),
             (11, "", f"skill-release-date: fsize={hard}/{hard}\n")),
            ("a normal reply", EXTRACTOR.read_text(encoding="utf-8"), ("baseline",), (0, "1.0.14\n", "")),
        ):
            with self.subTest(kind=kind, case=label):
                pair = Pair(body)
                try:
                    proc = subprocess.run(
                        [sys.executable, "-I", "-c", launch, str(pair.client), *words],
                        capture_output=True, text=True, cwd=pair.root,
                    )
                finally:
                    pair.close()
                self.assertEqual((proc.returncode, proc.stdout, proc.stderr), expected)

    def test_an_unprivileged_child_cannot_raise_its_file_size_limit(self):
        # The child gets the cap as both its soft and its hard limit, so a
        # child without CAP_SYS_RESOURCE can neither raise its soft limit
        # past the cap nor raise the hard limit; a child with an infinite
        # hard limit could undo the cap. Run with CAP_SYS_RESOURCE (as
        # root), the raise of the hard limit would succeed, the residual the
        # module docstring names.
        body = (
            "import json, resource, sys\n"
            "request = json.loads(sys.stdin.read())\n"
            "soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)\n"
            "try:\n"
            "    resource.setrlimit(resource.RLIMIT_FSIZE, (soft + 1000, max(hard, soft + 1000)))\n"
            "    raised = 'raised'\n"
            "except (ValueError, OSError):\n"
            "    raised = 'refused'\n"
            "message = 'fsize=%d/%d %s' % (soft, hard, raised)\n"
            "print(json.dumps({'op': request['op'], 'outcome': 'malformed', 'message': message}))\n"
        )
        cap = client.output_cap(client.RESULT_LIMIT + client.ECHO_BYTES_PER_CHARACTER * len("1.0.15"))
        pair = Pair(body)
        try:
            self.assertEqual(pair.run("requires-date", "1.0.15"),
                             (11, "", f"skill-release-date: fsize={cap}/{cap} refused\n"))
        finally:
            pair.close()

    def test_relayed_stderr_is_one_line(self):
        # Every line the child wrote to stderr is relayed on the one line,
        # joined with " | "; blank lines and surrounding blanks are dropped.
        body = "import sys\nsys.stderr.write('first line\\n\\n  second line  \\r\\nthird\\n')\nraise SystemExit(3)\n"
        pair = Pair(body)
        try:
            self.assertEqual(
                pair.run("baseline"),
                (16, "", "skill-release-date-client: skill-release-date.py exited 3 in baseline, so the extractor "
                         "is unavailable; it printed: first line | second line | third\n"),
            )
        finally:
            pair.close()

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


# The functions the tripwire reads, each bound in this file only by its def.
BOUND_NAMES = ("check_group_kill", "end_of_file", "stub")


# The interpreter's own records of a class and of a test's instance, read
# through the descriptors that type and unittest.TestCase define rather than
# by attribute lookup, which a class or its metaclass can override: the
# classes that list a class among their bases, its method resolution order,
# its namespace, its qualified name, and the attributes an instance holds of
# its own.
SUBCLASSES = type.__subclasses__
MRO = type.__dict__["__mro__"].__get__
NAMESPACE = type.__dict__["__dict__"].__get__
QUALNAME = type.__dict__["__qualname__"].__get__
INSTANCE_DICT = NAMESPACE(unittest.TestCase)["__dict__"].__get__


def bindings(tree: ast.AST) -> list:
    """Each (name, node type) for a node of ``tree`` that has 1 of
    BOUND_NAMES as its id, attr, name, asname, rest or arg and is not a
    read. Among them, each with a case in
    test_the_tripwire_sees_each_binding_of_its_names: a def, async def or
    class statement; an assignment to a name, plain, annotated, augmented,
    by :=, or as part of a tuple or a starred target; an assignment to an
    attribute; a lambda so assigned; a deletion; a for, with,
    comprehension, except or match target; an import; a parameter; and a
    keyword argument. A name given only as a string, as to setattr or in a
    dict, is not counted."""
    return sorted((value, type(node).__name__) for node in ast.walk(tree)
                  if not isinstance(getattr(node, "ctx", None), ast.Load)
                  for value in (getattr(node, field, None) for field in ("id", "attr", "name", "asname", "rest", "arg"))
                  if value in BOUND_NAMES)


def described(value) -> tuple:
    """The qualified name of ``value`` and the first line of its code, the
    line of its def statement or of its first decorator, or 0 for a value
    with no code."""
    code = getattr(value, "__code__", None)
    return getattr(value, "__qualname__", type(value).__name__), getattr(code, "co_firstlineno", 0)


def entries(namespace) -> list:
    """Each (name, qualified name, first line) for an entry of ``namespace``,
    as its items method lists them, whose name is a plain str equal to 1 of
    BOUND_NAMES, or is not a plain str, whatever it compares equal to."""
    return [(name if type(name) is str else object.__repr__(name),) + described(value)
            for name, value in namespace.items() if type(name) is not str or name in BOUND_NAMES]


def class_bindings(root: type) -> list:
    """Each (class, name, qualified name, first line) for an entry that
    entries finds in the namespace of ``root``, of each class that exists
    when this runs and has it among its bases, directly or through other
    such classes, or of each class in the method resolution order of any of
    them, however the entry was bound. It reads each class through
    SUBCLASSES, MRO, NAMESPACE and QUALNAME and tells classes apart by
    identity, so the overrides of a class or of its metaclass that
    test_the_tripwire_sees_each_binding_of_its_names has a case for change
    neither which classes nor which entries it finds. Other routes can: a
    metaclass whose mro method puts ``root`` in the order of a class that
    does not have it among its bases hides that class and its entries,
    since SUBCLASSES does not list it. The qualified name and first line of
    an entry come from the entry's value."""
    classes = [root]
    for cls in classes:
        classes.extend(sub for sub in SUBCLASSES(cls) if not any(sub is known for known in classes))
    owners = []
    for cls in classes:
        owners.extend(owner for owner in MRO(cls) if not any(owner is known for known in owners))
    return sorted((QUALNAME(owner),) + entry for owner in owners for entry in entries(NAMESPACE(owner)))


def own_bindings(instance: unittest.TestCase) -> list:
    """The name of each entry that entries finds among the attributes that
    ``instance`` holds of its own, read through INSTANCE_DICT and listed by
    the items method of the object found there. A dict subclass set as the
    instance's __dict__ can override that method and so hide an entry."""
    return sorted(entry[0] for entry in entries(INSTANCE_DICT(instance)))


class InheritedSigchldTest(unittest.TestCase):
    """The exit status of the child does not depend on the SIGCHLD
    disposition the client inherits: an ignored SIGCHLD would make the
    kernel reap the child, losing its status, so the client resets it."""

    LAUNCH = (
        "import os, signal, sys\n"
        "signal.signal(signal.SIGCHLD, signal.{})\n"
        "os.execv(sys.executable, [sys.executable, \"-I\", *sys.argv[1:]])\n"
    )

    def test_an_ignored_sigchld_keeps_a_non_zero_exit_unavailable(self):
        # The child prints a reply that meets the contract and exits 1. With
        # SIGCHLD ignored and not reset, that exit is lost and the client
        # would print 1.0.14 and exit 0.
        reply = "{\"op\": \"baseline\", \"outcome\": \"value\", \"value\": \"1.0.14\"}"
        pair = Pair(f"print({reply!r})\nraise SystemExit(1)\n")
        try:
            for disposition in ("SIG_DFL", "SIG_IGN"):
                with self.subTest(disposition):
                    proc = subprocess.run(
                        [sys.executable, "-I", "-c", self.LAUNCH.format(disposition), str(pair.client), "baseline"],
                        capture_output=True, text=True, cwd=pair.root,
                    )
                    self.assertEqual((proc.returncode, proc.stdout), (16, ""), proc.stderr)
                    self.assertEqual(
                        proc.stderr,
                        "skill-release-date-client: skill-release-date.py exited 1 in baseline, "
                        "so the extractor is unavailable\n",
                    )
        finally:
            pair.close()

    def test_an_ignored_sigchld_keeps_a_valid_reply(self):
        pair = Pair(EXTRACTOR.read_text(encoding="utf-8"))
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", self.LAUNCH.format("SIG_IGN"), str(pair.client), "requires-date",
                 "1.0.15"],
                capture_output=True, text=True, cwd=pair.root,
            )
        finally:
            pair.close()
        self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "required\n", ""))

    def test_a_sigchld_that_cannot_be_reset_starts_no_child(self):
        # The reset is refused in a thread other than the main thread
        # (ValueError); the client then exits 16 naming it and starts no child.
        pair = Pair("open('started', 'w').write('1')\n")
        script = (
            "import contextlib, importlib.util, io, sys, threading\n"
            "spec = importlib.util.spec_from_file_location(\"client_copy\", sys.argv[1])\n"
            "client = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(client)\n"
            "codes = []\n"
            "thread = threading.Thread(target=lambda: codes.append(client.main([\"c\", \"baseline\"])))\n"
            "thread.start()\n"
            "thread.join()\n"
            "sys.exit(codes[0] if codes else 70)\n"
        )
        try:
            proc = subprocess.run([sys.executable, "-I", "-c", script, str(pair.client)],
                                  capture_output=True, text=True, cwd=pair.root)
            started = (pair.root / "started").exists()
        finally:
            pair.close()
        self.assertEqual((proc.returncode, proc.stdout), (16, ""), proc.stderr)
        self.assertTrue(proc.stderr.startswith(
            "skill-release-date-client: skill-release-date.py could not be run safely (SIGCHLD could not be "
            "reset to its default disposition: ValueError: "), proc.stderr)
        self.assertTrue(proc.stderr.endswith(
            "), so its exit status could be lost in baseline, so the extractor is unavailable\n"), proc.stderr)
        self.assertFalse(started, "a child was started")


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
