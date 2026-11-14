#!/usr/bin/env python3
"""Tests for tools/check-pr-text.py, the pull request text gate.

Each case runs the gate as a separate process, as CI and a hand run do, with a temporary folder as
its working directory, and checks its exit status and its output. The suite starts every child
through run_child(), which sets a memory limit, a CPU limit and, where a case asks, a stack limit
in the child before it runs the gate or the suite, and enforces a wall timeout on the child from
the process that started it, so a gate that never ends stops at a limit. When a child of the top
suite process hits its wall timeout, run_child() kills its whole process group, which holds every
process the child started through run_child(); LIMIT_LAUNCH and run_child() state which process
runs under which limit. The suite sets no limit on its own top process: in CI the job's time
limit in the workflow bounds it, and on a local run nothing in the suite does. A case that needs
a squash folder copies the gate and the label lint into a temporary tree, since the gate finds
both from its own path. Every review-history label and every dash a case feeds the gate is built
when the case runs, by joining strings or from an escape, so this file carries none of them as
text.

The cases fall in 5 groups. DefectClasses holds a failing case for each mechanical defect class,
which includes a code fence that is never closed and a blank text, in each text, and the digit
bound and the subject binding. Exemptions holds the cases at the edges of the masks, the
exemptions and the scope limits, which pass honest text inside an edge and fail text just outside
it, and 3 cases that enumerate every code point from U+0000 to U+FFFF but the surrogates and
compare the gate with the sets its docstring names: the characters that end a URL, the
characters that may follow a fence closer's run, and the quote pairs that the quote mask masks.
UnreadableInputs holds a case for each branch of the exit contract and each kind of unreadable
input and usage error, where the deeply nested payload runs the gate under a soft stack limit of
1 MiB that the case sets, or the hard limit when that is lower, so the JSON reader overflows its
stack on any runner. OutputAndHonestTexts holds the output prefixes and escapes, runs from other
folders and without -B, a bound on the time of the inline-code scan, a case that the scan ends
on each shape of backtick run, the memory, CPU and wall limits of a child, a case that a
grandchild ends with its timed-out parent, a static case that every child runs under its limits,
the job's time limit in the workflow, and honest texts that pass. MutantSweep generates the
mutation sites of the gate from its source, checks that each has a row or an argument that it is
equivalent, and runs the cases each row names on a copy of the gate with the site applied; its
docstring states its operators, its kill and equivalence criterion, its rule for a child that
hits a limit and its residual. The class of counts stated with their selection rule has no case:
it stays a judgement for reviewers, because no part of it is mechanical.
"""
import ast
import collections
import contextlib
import io
import json
import os
import re
import resource
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tokenize
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE / "check-pr-text.py"
SUITE = HERE / "test-check-pr-text.py"
LINT = HERE / "test-no-qa-labels.py"
WORKFLOW = HERE.parent / ".github" / "workflows" / "pr-text.yml"
PREFIXES = ("description", "squash", "unreadable:", "pr-text:")

EM_DASH = "\u2014"
EN_DASH = "\u2013"
# Review-history labels, joined at run time so that this file holds none as text.
ROUND_LABEL = "fixed in rou" + "nd 7"
FIX_LABEL = "a fix" + " round"
BARE_ID = "R" + "3"
OTHER_BARE_ID = "F" + "1"
ISE_WORD = "standard" + "ise"
# The -ise stems of the gate's denylist, each checked by test_every_ise_stem_fails.
ISE_STEMS = (
    "apolog", "author", "capital", "categor", "central", "character", "critic", "custom",
    "emphas", "final", "formal", "general", "harmon", "initial", "legal", "local", "maxim",
    "memor", "minim", "mobil", "modern", "neutral", "normal", "optim", "organ", "parameter",
    "priorit", "random", "real", "recogn", "sanit", "serial", "special", "stabil",
    "standard", "summar", "synchron", "token", "util", "visual",
)
SHA1 = "e233a7f0c1d2b3a4e5f60718293a4b5c6d7e8f90"
SHA256 = "a1" * 32
CLEAN_SUBJECT = "Add the pull request text gate (#999)"
CLEAN_SQUASH = CLEAN_SUBJECT + "\n\nAdd a gate that checks the texts of a pull request.\n"
UNCLOSED = "the code fence opened on line {} is never closed"
# Each character that ends a URL: whitespace, angle brackets, quote marks, a backtick, a
# parenthesis outside a pair, U+2013, U+2014 and the curly quote marks.
URL_STOPPERS = (" ", "\t", "<", ">", '"', "'", "`", "(", ")", EN_DASH, EM_DASH,
                "\u201c", "\u201d", "\u2018", "\u2019")
ISE_ENDINGS = ("e", "es", "ed", "ing", "er", "ers", "able", "ation", "ations")
# The sets the gate docstring names, each checked by enumerating U+0000 to U+FFFF: the marks
# that end a URL besides whitespace as Python's \s reads it, the characters that may follow a
# fence closer's run, and the 2 quote pairs the quote mask masks.
URL_STOPPER_MARKS = "<>\"'`()" + EN_DASH + EM_DASH + "\u2018\u2019\u201c\u201d"
FENCE_CLOSER_TAIL = " \t"
QUOTE_PAIRS = (('"', '"'), ("\u201c", "\u201d"))
# The code points of the Unicode Quotation_Mark property, each pair of which the quote mask
# enumeration checks.
QUOTATION_MARKS = (0x22, 0x27, 0xab, 0xbb, 0x2018, 0x2019, 0x201a, 0x201b, 0x201c, 0x201d,
                   0x201e, 0x201f, 0x2039, 0x203a, 0x2e42, 0x300c, 0x300d, 0x300e, 0x300f,
                   0x301d, 0x301e, 0x301f, 0xfe41, 0xfe42, 0xfe43, 0xfe44, 0xff02, 0xff07,
                   0xff62, 0xff63)


def url_stopper_set():
    """Each code point up to U+FFFF but U+000A that ends a URL, as the gate docstring names."""
    return {chr(code) for code in range(0x10000)
            if not 0xd800 <= code <= 0xdfff and code != 0x0a
            and (re.match(r"\s", chr(code)) or chr(code) in URL_STOPPER_MARKS)}
# The inline-code scan must finish this many backticks within this many seconds.
BACKTICK_RUN = 20000
TIME_BOUND = 10
# The wall timeout, in seconds, of the case that runs the code-span scan on each shape of run.
SPAN_TIMEOUT = 10
# The deep-nesting case runs the gate with this many levels under a soft stack limit of
# DEEP_STACK bytes, or the hard limit when that is lower, which LIMIT_LAUNCH sets, so the JSON
# reader overflows its stack, and so reaches the RecursionError branch, whatever stack limit
# the runner has.
DEEP_LEVELS = 100000
DEEP_STACK = 1024 * 1024
# Every child this suite starts goes through run_child(), which starts LIMIT_LAUNCH: a child
# that sets RLIMIT_AS, its address space, to the memory limit given as its first argument;
# when its second argument is not "-", the soft stack limit given there; RLIMIT_CPU to a soft
# limit of the seconds given as its third argument, which sends SIGXCPU, and a hard limit
# CPU_GRACE s above it, which sends SIGKILL; and RLIMIT_CORE to a soft limit of 0, so a child
# that SIGXCPU ends writes no core file. Each limit is never above the hard limit it inherits.
# It then sets CHILD_MARK in its environment and replaces itself with python3 run with the rest
# of its arguments. Each process the child starts inherits each limit and the mark, and a limit
# set below an inherited one is the lower of the 2; RLIMIT_CPU bounds the CPU time of each
# process on its own, not the sum over a tree, and not the time a process waits or sleeps.
# run_child() enforces the wall timeout, from the process that starts the child.
CHILD_MARK = "CHECK_PR_TEXT_CHILD"
CPU_GRACE = 5
LIMIT_LAUNCH = ("import os, resource, sys\n"
                "def cap(kind, soft, hard=None):\n"
                "    inherited = resource.getrlimit(kind)[1]\n"
                "    hard = inherited if hard is None else hard\n"
                "    if inherited != resource.RLIM_INFINITY:\n"
                "        soft, hard = min(soft, inherited), min(hard, inherited)\n"
                "    return soft, hard\n"
                "memory = cap(resource.RLIMIT_AS, int(sys.argv[1]))[0]\n"
                "resource.setrlimit(resource.RLIMIT_AS, (memory, memory))\n"
                "if sys.argv[2] != '-':\n"
                "    resource.setrlimit(resource.RLIMIT_STACK,\n"
                "                       cap(resource.RLIMIT_STACK, int(sys.argv[2])))\n"
                "cpu = int(sys.argv[3])\n"
                "resource.setrlimit(resource.RLIMIT_CPU,\n"
                "                   cap(resource.RLIMIT_CPU, cpu, cpu + " + str(CPU_GRACE) + "))\n"
                "resource.setrlimit(resource.RLIMIT_CORE,\n"
                "                   (0, resource.getrlimit(resource.RLIMIT_CORE)[1]))\n"
                "os.environ['" + CHILD_MARK + "'] = '1'\n"
                "os.execv(sys.executable, [sys.executable, *sys.argv[4:]])\n")
# The memory limit and the wall timeout of each gate child, from measured runs under each stack
# limit: the largest and slowest gate child, the gate on the 5460060-byte input of the quote
# pair enumeration, reached a maxrss of 319 MiB in at most 14.2 s, and failed under an address
# space of 320 MiB but passed under 384 MiB.
GATE_MEMORY = 1024 * 1024 * 1024
GATE_TIMEOUT = 60
# The CPU limit of each child but a sweep child, in seconds, equal to GATE_TIMEOUT: a backstop
# for a child whose enforcing process is gone, such as a gate child whose sweep child something
# outside the suite killed. The child of most CPU time, the gate child on the input of the
# quote pair enumeration, used 15.3 s under an 8192 KiB stack and 12.2 s with no stack limit,
# so GATE_CPU is 3.9 times the larger. A child of 1 thread uses at most 1 s of CPU time per
# second of wall time, so while its enforcing process lives, its CPU limit can end it before
# its wall timeout only by the moments between its start and the start of that timeout; on a
# slower runner, a child that nears GATE_CPU nears its wall timeout first, and the margin
# covers a runner 3.9 times slower. Its cost is 2 more calls that set a limit in each child.
# It bounds CPU time, not wall time, and does not end a process that waits or sleeps.
GATE_CPU = 60
# The memory limit of each sweep child, the suite run on the named cases of 1 row. Each gate
# child it starts inherits it, so in a sweep a gate child runs under SWEEP_MEMORY too; the run
# of every named case on an unmutated copy, with the gate children it started, reached a
# maxrss of 26 MiB in at most 35.8 s. At most SWEEP_WORKERS sweep children run at once, each
# with at most 1 gate child, so the children of a sweep hold at most
# SWEEP_WORKERS * 2 * SWEEP_MEMORY bytes of address space.
SWEEP_MEMORY = 192 * 1024 * 1024
# Each line that run_child() writes to standard error when a child hits a limit starts so.
LIMIT_HIT = "limit hit: "
# The case that a grandchild ends with its timed-out parent runs this parent, which imports the
# suite and starts ORPHAN_SPIN through run_child(), as a sweep child starts a gate child, under
# a wall timeout of ORPHAN_TIMEOUT s; each writes its PID to a file in the case's temporary
# folder. ORPHAN_BOUND, the seconds the case waits for the grandchild after the timeout of its
# parent, is well under GATE_CPU, so the CPU limit cannot end the grandchild within it.
ORPHAN_PARENT = (
    "import importlib.util, os, sys\n"
    "suite_path, fd, folder, spin = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]\n"
    "open(os.path.join(folder, 'parent.pid'), 'w').write(str(os.getpid()))\n"
    "spec = importlib.util.spec_from_file_location('suite', suite_path)\n"
    "suite = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(suite)\n"
    "suite.run_child(['-I', '-B', '-c', spin, fd, folder], memory=suite.GATE_MEMORY,\n"
    "                timeout=suite.GATE_TIMEOUT, cwd=folder, pass_fds=(fd,))\n")
ORPHAN_SPIN = ("import os, sys\n"
               "open(os.path.join(sys.argv[2], 'grandchild.pid'), 'w').write(str(os.getpid()))\n"
               "os.write(int(sys.argv[1]), b'started\\n')\n"
               "while True:\n"
               "    pass\n")
ORPHAN_TIMEOUT = 5
ORPHAN_BOUND = 5


def memory_limit(memory):
    """The address space limit a child asked for memory bytes gets: never above the inherited."""
    hard = resource.getrlimit(resource.RLIMIT_AS)[1]
    return memory if hard == resource.RLIM_INFINITY else min(memory, hard)


def cpu_limits(cpu):
    """The (soft, hard) CPU limits in seconds for cpu, each never above the inherited hard."""
    hard = resource.getrlimit(resource.RLIMIT_CPU)[1]
    if hard == resource.RLIM_INFINITY:
        return cpu, cpu + CPU_GRACE
    return min(cpu, hard), min(cpu + CPU_GRACE, hard)


def cpu_hit(returncode, cpu):
    """The limit a child that ended with returncode hit, when a CPU limit ends it so, or None.

    The soft CPU limit ends a child by SIGXCPU and the hard one by SIGKILL; any SIGKILL that
    run_child() did not send, such as one from the kernel when memory runs out, is named so too.
    """
    if returncode not in (-signal.SIGXCPU, -signal.SIGKILL):
        return None
    return "the CPU limit of {} s ({})".format(cpu_limits(cpu)[0],
                                               signal.Signals(-returncode).name)


def run_child(args, *, memory, timeout, cwd, stack=None, cpu=GATE_CPU, **options):
    """The finished python3 child run with args under memory, CPU and wall limits.

    The child runs through LIMIT_LAUNCH with RLIMIT_AS set to memory bytes, RLIMIT_CPU set to
    cpu seconds and a hard limit CPU_GRACE s above it, and, when stack is given, the soft stack
    limit set to stack bytes. This process enforces the wall timeout of timeout seconds: on that
    timeout, or on any other exception while the child runs, KeyboardInterrupt included, it
    kills the child and reaps it before it re-raises.

    The nested shape, a call made inside a child that run_child() started, as a sweep child runs
    a gate child: LIMIT_LAUNCH sets CHILD_MARK in each child, so a call reads from it whether it
    is outermost. Only an outermost call starts its child in a new session, and so a new process
    group, and on a timeout or an exception it kills that whole group with os.killpg and
    SIGKILL. A nested call keeps its child in the process group of its caller, which is the
    group of the outermost child above it, so that os.killpg reaches it: when SWEEP_TIMEOUT
    stops a sweep child, the gate child it is running ends with it. If every call started a new
    session, the gate child would be in a group of its own, which the kill of the sweep child's
    group would not reach. A nested call that times out kills its own child by its PID alone,
    since a kill of the group would kill its caller too; a process that child started stays in
    the outermost group, which only the outermost call's timeout or exception kills. A gate child
    starts no process. A child in a new session also leaves the group of the process that starts
    it, so a signal sent to that group, such as SIGINT from a terminal, does not reach it.

    A child stopped by its wall timeout raises subprocess.TimeoutExpired. A child whose output
    names MemoryError, as the gate's report does when it stops on its memory limit, and a child
    that cpu_hit() reads as ended by its CPU limit, are returned. For each, 1 line that starts
    with LIMIT_HIT and names the limit goes to standard error, where the sweep reads it.
    """
    command = [sys.executable, "-I", "-B", "-c", LIMIT_LAUNCH, str(memory),
               "-" if stack is None else str(stack), str(cpu), *map(str, args)]
    outermost = os.environ.get(CHILD_MARK) != "1"
    with subprocess.Popen(command, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          start_new_session=outermost, **options) as child:
        try:
            stdout, stderr = child.communicate(timeout=timeout)
        except BaseException as error:
            if outermost and child.returncode is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            child.kill()
            child.wait()
            if isinstance(error, subprocess.TimeoutExpired):
                print("{}the wall timeout of {} s".format(LIMIT_HIT, timeout), file=sys.stderr,
                      flush=True)
            raise
    done = subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
    found = done.stdout + done.stderr
    if ("MemoryError" if isinstance(found, str) else b"MemoryError") in found:
        print("{}the memory limit of {} bytes".format(LIMIT_HIT, memory_limit(memory)),
              file=sys.stderr, flush=True)
    hit = cpu_hit(done.returncode, cpu)
    if hit:
        print(LIMIT_HIT + hit, file=sys.stderr, flush=True)
    return done


class GateCase(unittest.TestCase):
    """Helpers that write inputs and run the gate, each run a child under run_child()."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.cwd = self.tmp / "elsewhere"
        self.cwd.mkdir()

    def write(self, name, text):
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def run_gate(self, *args, gate=GATE, cwd=None, timeout=GATE_TIMEOUT, memory=GATE_MEMORY):
        """(exit status, output lines) of the gate run with args, under memory and timeout."""
        done = run_child(["-I", "-B", gate, *args], memory=memory, timeout=timeout,
                         cwd=cwd or self.cwd, text=True, encoding="utf-8")
        return done.returncode, done.stdout.splitlines()

    def tree(self, squash=None, number=999, lint=True):
        """A copy of the gate in a temporary tree, with the lint and a squash file if given."""
        root = self.tmp / "tree"
        (root / "tools").mkdir(parents=True)
        shutil.copyfile(GATE, root / "tools" / "check-pr-text.py")
        if lint:
            shutil.copyfile(LINT, root / "tools" / "test-no-qa-labels.py")
        if squash is not None:
            (root / ".github" / "squash").mkdir(parents=True)
            (root / ".github" / "squash" / "{}.txt".format(number)).write_text(
                squash, encoding="utf-8")
        return root / "tools" / "check-pr-text.py"

    def event(self, body, number=999, name="event.json"):
        payload = {"action": "opened", "number": number,
                   "pull_request": {"number": number, "body": body}}
        return self.write(name, json.dumps(payload))

    def description(self, text):
        return self.run_gate("--description", self.write("description.md", text))

    def squash(self, text, number=999):
        return self.run_gate("--squash", self.write("squash.txt", text), "--number", number)

    def assertResult(self, result, status, defects):
        code, lines = result
        self.assertEqual(code, status, lines)
        self.assertTrue(lines, "no output")
        self.assertEqual(lines[-1], "pr-text: {} defect(s)".format(defects), lines)

    def assertReports(self, result, fragment):
        self.assertTrue(any(fragment in line for line in result[1]), result[1])


class DefectClasses(GateCase):
    """Each mechanical class fails with a committed case."""

    def test_squash_line_over_72_characters_fails(self):
        result = self.squash(CLEAN_SUBJECT + "\n\n" + "a" * 73 + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:3: 73 characters, over 72")

    def test_squash_line_of_72_characters_passes(self):
        self.assertResult(self.squash(CLEAN_SUBJECT + "\n\n" + "a" * 72 + "\n"), 0, 0)

    def test_label_in_description_fails(self):
        result = self.description("Intro.\n\nThis was " + ROUND_LABEL + ".\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:3: a review round number")

    def test_fix_label_in_description_fails(self):
        self.assertResult(self.description("This came from " + FIX_LABEL + ".\n"), 1, 1)

    def test_label_in_squash_message_fails(self):
        result = self.squash(CLEAN_SQUASH + "\nThis was " + ROUND_LABEL + ".\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:5: a review round number")

    def test_label_right_after_masked_span_fails(self):
        for text in ("See `x`" + BARE_ID + " for it.\n", 'See "x"' + OTHER_BARE_ID + " here.\n"):
            with self.subTest(text=text):
                result = self.description(text)
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description:1: a bare finding id")

    def test_revision_id_in_squash_message_fails(self):
        result = self.squash(CLEAN_SQUASH + "\nBuilt on e233a7f.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:5: a revision id: e233a7f")

    def test_revision_id_with_its_only_digit_or_letter_first_fails(self):
        for run in ("1abcdef", "a123456"):
            with self.subTest(run=run):
                result = self.squash(CLEAN_SQUASH + "\nBuilt on " + run + ".\n")
                self.assertResult(result, 1, 1)
                self.assertReports(result, "squash:5: a revision id: " + run)

    def test_number_option_of_1_digit_binds(self):
        path = self.write("squash.txt", "Add a thing (#5)\n\nBody.\n")
        self.assertResult(self.run_gate("--squash", path, "--number", "5"), 0, 0)
        self.assertResult(self.run_gate("--squash", path, "--number", "6"), 1, 1)

    def test_full_revision_id_in_squash_message_fails(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nBuilt on " + SHA1 + ".\n"), 1, 1)

    def test_revision_id_in_backticks_in_squash_message_fails(self):
        result = self.squash(CLEAN_SQUASH + "\nBuilt on `e233a7f`.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "a revision id: e233a7f")

    def test_em_dash_fails(self):
        result = self.description("The gate " + EM_DASH + " a new check.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an em dash, U+2014")

    def test_em_dash_in_squash_message_fails(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nA gate " + EM_DASH + " new.\n"), 1, 1)

    def test_en_dash_fails(self):
        result = self.description("The gate " + EN_DASH + " a new check.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an en dash, U+2013")

    def test_en_dash_in_numeric_range_fails(self):
        result = self.description("See pages 12" + EN_DASH + "14.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "an en dash, U+2013")

    def test_dash_after_lone_backtick_and_double_span_fails(self):
        result = self.description("A lone ` backtick, then prose " + EM_DASH
                                  + " shown, then ``code``.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an em dash, U+2014")

    def test_dash_closed_up_after_url_fails(self):
        result = self.description("See https://example.com" + EM_DASH + "the page.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an em dash, U+2014")

    def test_ise_spelling_fails(self):
        result = self.description("We " + ISE_WORD + " the texts.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an -ise spelling: " + ISE_WORD)

    def test_ise_spelling_in_squash_message_fails(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nWe " + ISE_WORD + " it.\n"), 1, 1)

    def test_ised_word_fails(self):
        result = self.description("We " + ISE_WORD + "d the texts.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "an -ise spelling: " + ISE_WORD + "d")

    def test_every_ise_stem_fails(self):
        words = [stem + "ise" for stem in ISE_STEMS]
        result = self.description("".join("We " + word + " it.\n\n" for word in words))
        self.assertResult(result, 1, len(words))
        for word in words:
            self.assertReports(result, "an -ise spelling: " + word)

    def test_ise_word_right_after_masked_span_fails(self):
        result = self.description("Run `x`organ" + "ise now.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an -ise spelling")

    def test_each_ise_ending_fails(self):
        for ending in ISE_ENDINGS:
            word = "organ" + "is" + ending
            with self.subTest(word=word):
                result = self.description("We see " + word + " here.\n")
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description:1: an -ise spelling: " + word)

    def test_ise_spelling_with_a_capital_fails(self):
        word = "Organ" + "ise"
        result = self.description(word + " the texts.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "an -ise spelling: " + word)

    def test_empty_description_fails(self):
        result = self.description(" \n\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description: the text is empty")

    def test_blank_description_fails(self):
        for text in ("\u200b\n", "\ufeff\n", "<!-- Describe the change here. -->\n",
                     " <!-- a -->\n\u200b<!-- an unclosed comment\n\nwith prose\n"):
            with self.subTest(text=text):
                result = self.description(text)
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description: the text is empty")

    def test_empty_squash_file_fails(self):
        for text in ("", "<!-- a comment -->\n\u200b\n"):
            with self.subTest(text=text):
                result = self.squash(text)
                self.assertResult(result, 1, 1)
                self.assertReports(result, "squash: the text is empty")

    def test_null_body_fails(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        result = self.run_gate("--event", self.event(None), gate=gate)
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description: the text is empty")

    def test_unclosed_fence_in_description_fails(self):
        result = self.description("Intro.\n\n```\nThe gate " + EM_DASH + " a new check.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:3: " + UNCLOSED.format(3))

    def test_unclosed_fence_in_squash_message_fails(self):
        result = self.squash(CLEAN_SQUASH + "\n```\n" + ROUND_LABEL + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:5: " + UNCLOSED.format(5))

    def test_backtick_in_fence_info_string_is_not_a_fence(self):
        text = "Intro.\n\n``` a`b\nprose " + EM_DASH + " shown\n```\n"
        result = self.description(text)
        self.assertResult(result, 1, 2)
        self.assertReports(result, "description:4: an em dash, U+2014")
        self.assertReports(result, "description:5: " + UNCLOSED.format(5))

    def test_squash_subject_without_its_number_fails(self):
        result = self.squash("Add the pull request text gate\n\nA body.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, 'squash:1: the subject does not end with " (#999)"')

    def test_squash_subject_with_wrong_number_under_number_option_fails(self):
        path = self.write("squash.txt", CLEAN_SQUASH)
        result = self.run_gate("--squash", path, "--number", 998)
        self.assertResult(result, 1, 1)
        self.assertReports(result, '" (#998)"')

    def test_event_squash_subject_with_wrong_number_fails(self):
        gate = self.tree(squash=CLEAN_SQUASH.replace("(#999)", "(#998)"))
        self.assertResult(self.run_gate("--event", self.event("A body."), gate=gate), 1, 1)

    def test_number_option_binding_passes(self):
        result = self.squash(CLEAN_SQUASH)
        self.assertResult(result, 0, 0)
        self.assertNotIn("pr-text: subject binding not checked", result[1])

    def test_number_comes_from_squash_file_name(self):
        folder = self.tmp / "other" / ".github" / "squash"
        folder.mkdir(parents=True)
        (folder / "998.txt").write_text(CLEAN_SQUASH, encoding="utf-8")
        result = self.run_gate("--squash", folder / "998.txt")
        self.assertResult(result, 1, 1)
        self.assertReports(result, '" (#998)"')

    def test_squash_names_with_a_leading_zero_are_not_bound(self):
        folder = self.tmp / "other" / ".github" / "squash"
        folder.mkdir(parents=True)
        message = "Add a thing (#5)\n\nBody.\n"
        for name in ("0.txt", "007.txt", "7.txt"):
            (folder / name).write_text(message, encoding="utf-8")
        for name in ("0.txt", "007.txt"):
            with self.subTest(name=name):
                result = self.run_gate("--squash", folder / name)
                self.assertResult(result, 0, 0)
                self.assertIn("pr-text: subject binding not checked", result[1])
        result = self.run_gate("--squash", folder / "7.txt")
        self.assertResult(result, 1, 1)
        self.assertReports(result, '" (#7)"')

    def test_binding_not_checked_line_is_not_a_defect(self):
        result = self.run_gate("--squash", self.write("message.txt", CLEAN_SQUASH))
        self.assertResult(result, 0, 0)
        self.assertIn("pr-text: subject binding not checked", result[1])

    def test_number_name_outside_a_squash_folder_is_not_bound(self):
        result = self.run_gate("--squash", self.write("998.txt", CLEAN_SQUASH))
        self.assertResult(result, 0, 0)
        self.assertIn("pr-text: subject binding not checked", result[1])

    def squash_name(self, digits):
        """A real squash file named by digits in a squash folder, whose subject ends (#5)."""
        folder = self.tmp / "other" / ".github" / "squash"
        folder.mkdir(parents=True)
        path = folder / (digits + ".txt")
        path.write_text("Add a thing (#5)\n\nBody.\n", encoding="utf-8")
        return path

    def test_squash_name_of_18_digits_binds_the_subject(self):
        result = self.run_gate("--squash", self.squash_name("9" * 18))
        self.assertResult(result, 1, 1)
        self.assertReports(result, '" (#' + "9" * 18 + ')"')

    def test_squash_name_of_19_digits_is_not_bound(self):
        result = self.run_gate("--squash", self.squash_name("9" * 19))
        self.assertResult(result, 0, 0)
        self.assertIn("pr-text: subject binding not checked", result[1])

    def test_payload_number_1_is_read(self):
        gate = self.tree(squash="Add a thing (#1)\n\nBody.\n", number=1)
        self.assertResult(self.run_gate("--event", self.event("A body.", number=1), gate=gate),
                          0, 0)

    def test_event_number_of_19_digits_binds_the_subject(self):
        number = 1234567890123456789
        for subject, status in ((number, 0), (5, 1)):
            with self.subTest(subject=subject):
                gate = self.tree(squash="Add a thing (#{})\n\nBody.\n".format(subject),
                                 number=number)
                result = self.run_gate("--event", self.event("A body.", number=number),
                                       gate=gate)
                self.assertResult(result, status, status)
                shutil.rmtree(self.tmp / "tree")

    def test_blank_text_reports_only_that_it_is_empty(self):
        result = self.description("<!--\n```\n" + EM_DASH)
        self.assertResult(result, 1, 1)
        self.assertEqual(result[1][0], "description: the text is empty", result[1])

    def test_squash_name_with_a_further_suffix_is_not_bound(self):
        folder = self.tmp / "other" / ".github" / "squash"
        folder.mkdir(parents=True)
        for name in ("5.txt.bak", "5xtxt"):
            with self.subTest(name=name):
                (folder / name).write_text("Add a thing (#4)\n\nBody.\n", encoding="utf-8")
                result = self.run_gate("--squash", folder / name)
                self.assertResult(result, 0, 0)
                self.assertIn("pr-text: subject binding not checked", result[1])


class Exemptions(GateCase):
    """Each mask, exemption and scope limit: honest text inside it passes, and text outside it
    fails; the URL stoppers, the fence closer's tail and the quote pairs by enumeration."""

    def test_label_and_width_inside_fence_pass(self):
        fence = "```\n" + ROUND_LABEL + "\n" + "b" * 90 + "\n```\n"
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + fence), 0, 0)
        self.assertResult(self.description("Intro.\n\n" + fence), 0, 0)

    def test_closed_fence_then_clean_prose_passes(self):
        fence = "```\n" + ROUND_LABEL + "\n```\n"
        self.assertResult(self.description("Intro.\n\n" + fence + "\nClean prose after it.\n"),
                          0, 0)
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + fence + "\nClean prose after it.\n"),
                          0, 0)

    def test_dash_after_closed_fence_fails(self):
        fence = "```\ncode\n```\n"
        result = self.description("Intro.\n\n" + fence + "\nThe gate " + EM_DASH + " new.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:7: an em dash, U+2014")

    def test_closer_with_trailing_text_leaves_fence_open(self):
        result = self.description("```\ncode\n``` x\nprose " + EM_DASH + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: " + UNCLOSED.format(1))

    def test_shorter_closer_leaves_fence_open(self):
        result = self.description("````\ncode\n```\nprose " + EM_DASH + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: " + UNCLOSED.format(1))

    def test_other_character_closer_leaves_fence_open(self):
        result = self.description("```\ncode\n~~~\nprose " + EM_DASH + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: " + UNCLOSED.format(1))

    def test_closer_with_trailing_whitespace_closes_fence(self):
        result = self.description("```\ncode\n``` \t\nprose " + EM_DASH + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:4: an em dash, U+2014")

    def test_closer_followed_by_a_tab_or_a_space_closes_fence(self):
        for tail in ("\t", " "):
            with self.subTest(tail=tail):
                result = self.description("```\ncode\n```" + tail + "\nprose " + EM_DASH + "\n")
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description:4: an em dash, U+2014")

    def test_closer_followed_by_other_whitespace_leaves_fence_open(self):
        for char in ("\x0c", "\x0b", "\x1c", "\xa0", "\x85"):
            with self.subTest(char=hex(ord(char))):
                result = self.description("Intro.\n\n```\ncode\n```" + char + "\n\nAfter.\n")
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description:3: " + UNCLOSED.format(3))

    def test_fence_indented_4_spaces_is_not_a_fence(self):
        result = self.description("Intro.\n\n    ```\nprose " + EM_DASH + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:4: an em dash, U+2014")
        result = self.description("```\ncode\n    ```\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: " + UNCLOSED.format(1))

    def test_fence_indented_1_to_3_spaces_masks_its_lines(self):
        for indent in (" ", "  ", "   "):
            with self.subTest(indent=len(indent)):
                text = "Intro.\n\n" + indent + "```\nprose " + EM_DASH + "\n" + indent + "```\n"
                self.assertResult(self.description(text), 0, 0)

    def test_run_of_2_backticks_or_tildes_is_not_a_fence(self):
        for run in ("``", "~~"):
            with self.subTest(run=run):
                result = self.description("Intro.\n\n" + run + " a\nprose " + EM_DASH + "\n")
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description:4: an em dash, U+2014")

    def test_tilde_fence_masks_its_lines(self):
        fence = "~~~\n" + ROUND_LABEL + "\n" + "b" * 90 + "\n~~~\n"
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + fence), 0, 0)
        self.assertResult(self.description("Intro.\n\n" + fence), 0, 0)

    def test_span_scan_resumes_after_its_closer(self):
        result = self.description("`a``b` " + EM_DASH + " c``\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an em dash, U+2014")

    def test_span_closes_on_the_nearest_run_of_its_length(self):
        result = self.description("Use `a` here " + EM_DASH + " and `b` there.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an em dash, U+2014")

    def test_backtick_run_inside_a_line_is_not_a_fence(self):
        result = self.description("Intro ```\nprose " + EM_DASH + " x\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:2: an em dash, U+2014")

    def test_indented_shorter_closer_leaves_fence_open(self):
        result = self.description("````\ncode\n ```\nprose " + EM_DASH + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: " + UNCLOSED.format(1))

    def test_long_line_next_to_a_fence_fails(self):
        long = "c" * 73
        result = self.squash(CLEAN_SQUASH + "\n" + long + "\n```\ncode\n```\n" + long + "\n")
        self.assertResult(result, 1, 2)
        self.assertReports(result, "squash:5: 73 characters, over 72")
        self.assertReports(result, "squash:9: 73 characters, over 72")

    def test_span_after_a_lone_backtick_is_masked(self):
        text = "A lone ` backtick, then ``" + ISE_WORD + "`` here.\n"
        self.assertResult(self.description(text), 0, 0)

    def test_span_right_after_another_span_is_masked(self):
        self.assertResult(self.description("Use ``a`` `" + ISE_WORD + "` here.\n"), 0, 0)

    def test_masked_span_reads_as_spaces(self):
        # Each character of a code span or of a quoted pair, its marks included, becomes a
        # space, so the label around it reads as the lint's phrase with spaces in it.
        for span in ("`x`", '""', "\u201c\u201d"):
            with self.subTest(span=span):
                text = "This was " + ROUND_LABEL.replace(" 7", span + "7") + ".\n"
                result = self.description(text)
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description:1: a review round number")

    def test_tilde_fence_of_4_closes_only_on_4_or_more(self):
        result = self.description("~~~~\ncode\n~~~~\nprose " + EM_DASH + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:4: an em dash, U+2014")
        result = self.description("~~~~\ncode\n~~~\nprose " + EM_DASH + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: " + UNCLOSED.format(1))

    def test_url_of_only_its_scheme_ending_a_long_line_passes(self):
        line = "a" * 66 + " https://"
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + line + "\n"), 0, 0)

    def test_empty_parenthesis_pair_is_part_of_a_url(self):
        self.assertResult(self.description("See https://e.com/x()" + ISE_WORD + " here.\n"),
                          0, 0)

    def test_empty_comment_then_text_is_not_blank(self):
        self.assertResult(self.description("<!----> Real text.\n"), 0, 0)

    def test_inline_span_at_line_start_is_not_a_fence(self):
        self.assertResult(self.description("```x`y``` is inline code.\n"), 0, 0)

    def test_label_in_backticks_passes(self):
        self.assertResult(self.description("The lint catches `" + ROUND_LABEL + "`.\n"), 0, 0)

    def test_long_url_line_passes(self):
        line = "See https://example.com/" + "c" * 80
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + line + "\n"), 0, 0)

    def test_long_line_with_url_before_the_excess_fails(self):
        line = "See https://example.com/ and then " + "d " * 30
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + line + "\n"), 1, 1)

    def test_url_starting_past_72_characters_fails(self):
        line = "a " * 37 + "https://example.com/x"
        result = self.squash(CLEAN_SQUASH + "\n" + line + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:5: 95 characters, over 72")

    def url_line(self, start):
        """A line whose URL starts at character start, counted from 1, and ends the line."""
        line = "a" * (start - 2) + " https://example.com/x"
        self.assertEqual(line.index("https://") + 1, start)
        return line

    def test_url_starting_at_character_72_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + self.url_line(72) + "\n"), 0, 0)

    def test_url_starting_at_character_73_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + self.url_line(73) + "\n"), 0, 0)

    def test_url_starting_at_character_74_fails(self):
        result = self.squash(CLEAN_SQUASH + "\n" + self.url_line(74) + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:5: 94 characters, over 72")

    def test_prose_glued_to_url_fails(self):
        line = "(see https://example.com/x)," + ",".join(["and", "then", "words"] * 10)
        result = self.squash(CLEAN_SQUASH + "\n" + line + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:5: {} characters, over 72".format(len(line)))

    def test_url_followed_by_punctuation_past_72_characters_fails(self):
        line = "(See https://example.com/" + "c" * 70 + ")."
        result = self.squash(CLEAN_SQUASH + "\n" + line + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:5: {} characters, over 72".format(len(line)))

    def test_url_ending_in_each_trailing_mark_past_72_characters_fails(self):
        for mark in ".,;:!?":
            with self.subTest(mark=mark):
                line = "See https://example.com/" + "c" * 70 + mark
                result = self.squash(CLEAN_SQUASH + "\n" + line + "\n")
                self.assertResult(result, 1, 1)
                self.assertReports(result, "squash:5: 95 characters, over 72")

    def test_long_url_with_a_parenthesis_pair_passes(self):
        line = "See https://en.wikipedia.org/wiki/" + "C" * 50 + "_(bar)"
        self.assertResult(self.squash(CLEAN_SQUASH + "\n" + line + "\n"), 0, 0)

    def test_each_url_stopper_ends_the_url(self):
        for stop in URL_STOPPERS:
            with self.subTest(stop=hex(ord(stop))):
                result = self.description("See https://e.com/a" + stop + ISE_WORD + " it.\n")
                self.assertResult(result, 1, 2 if stop in (EN_DASH, EM_DASH) else 1)
                self.assertReports(result, "description:1: an -ise spelling: " + ISE_WORD)

    def test_each_url_stopper_ends_a_parenthesis_pair(self):
        for stop in URL_STOPPERS:
            with self.subTest(stop=hex(ord(stop))):
                text = "See https://e.com/(a" + stop + "b)" + ISE_WORD + " it.\n"
                result = self.description(text)
                self.assertResult(result, 1, 2 if stop in (EN_DASH, EM_DASH) else 1)
                self.assertReports(result, "description:1: an -ise spelling: " + ISE_WORD)

    def test_dash_after_curly_quoted_url_fails(self):
        text = "He said \u201csee https://x.org/a\u201d " + EM_DASH + " and \u201cb\u201d.\n"
        result = self.description(text)
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an em dash, U+2014")

    def test_curly_quoted_url_ending_a_long_squash_line_fails(self):
        line = "See \u201chttps://example.org/" + "a" * 70 + "\u201d"
        result = self.squash(CLEAN_SQUASH + "\n" + line + "\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "squash:5: {} characters, over 72".format(len(line)))

    def test_ise_word_inside_url_passes(self):
        text = "See https://example.com/organ" + "ise-the-texts for it.\n"
        self.assertResult(self.description(text), 0, 0)

    def test_label_inside_double_quotes_passes(self):
        self.assertResult(self.description('The lint catches "' + ROUND_LABEL + '".\n'), 0, 0)

    def test_dash_inside_curly_quotes_passes(self):
        text = "He said \u201ca " + EM_DASH + " b\u201d.\n"
        self.assertResult(self.description(text), 0, 0)

    def test_text_between_2_quoted_pairs_is_checked(self):
        for opener, closer in (('"', '"'), ("\u201c", "\u201d")):
            with self.subTest(opener=hex(ord(opener))):
                text = ("He said " + opener + "a" + closer + " " + EM_DASH + " and " + opener
                        + "b" + closer + ".\n")
                result = self.description(text)
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description:1: an em dash, U+2014")

    def test_mixed_or_reversed_quote_pair_is_not_masked(self):
        for opener, closer in (("\u201d", "\u201d"), ('"', "\u201d"), ("\u201c", '"')):
            with self.subTest(opener=hex(ord(opener)), closer=hex(ord(closer))):
                text = "He said " + opener + "a " + EM_DASH + " b" + closer + ".\n"
                result = self.description(text)
                self.assertResult(result, 1, 1)
                self.assertReports(result, "description:1: an em dash, U+2014")

    def test_sha256_digest_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nThe digest:\n" + SHA256 + "\n"), 0, 0)

    def test_41_character_hex_run_passes(self):
        run = "a1" * 20 + "b"
        self.assertResult(self.squash(CLEAN_SQUASH + "\nThe run " + run + ".\n"), 0, 0)

    def test_word_of_letters_a_to_f_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nThe effaced and defaced page.\n"), 0, 0)

    def test_run_of_digits_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nDated 20261113, at 1234567.\n"), 0, 0)

    def test_short_hex_word_with_digit_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nThe cafe1 host.\n"), 0, 0)

    def test_6_character_hex_word_with_digit_passes(self):
        self.assertResult(self.squash(CLEAN_SQUASH + "\nThe c0ffee host.\n"), 0, 0)

    def test_long_description_paragraph_passes(self):
        self.assertResult(self.description("word " * 60 + "\n"), 0, 0)

    def test_revision_id_in_description_passes(self):
        self.assertResult(self.description("Built on e233a7f and " + SHA1 + ".\n"), 0, 0)

    def test_dash_on_closed_fence_opener_line_passes(self):
        text = "Intro.\n\n~~~ text " + EM_DASH + " x\ncode\n~~~\n"
        self.assertResult(self.description(text), 0, 0)

    def test_ise_stem_inside_a_longer_word_is_not_matched(self):
        self.assertResult(self.description("We re" + ISE_WORD + " it.\n"), 0, 0)

    def test_url_glued_after_a_letter_is_not_masked(self):
        result = self.description("Seehttps://e.com/" + ISE_WORD + " here.\n")
        self.assertResult(result, 1, 1)
        self.assertReports(result, "description:1: an -ise spelling: " + ISE_WORD)

    def test_word_inside_http_url_passes(self):
        self.assertResult(self.description("See http://e.com/" + ISE_WORD + " here.\n"), 0, 0)

    def test_text_between_2_comments_is_not_blank(self):
        self.assertResult(self.description("<!-- a --> Real text here. <!-- b -->\n"), 0, 0)

    def test_comment_opener_broken_by_a_zero_width_space_is_text(self):
        self.assertResult(self.description("<\u200b!-- x -->\n"), 0, 0)

    def enumerate_lines(self, build, skip=("\n",)):
        """The code points from U+0000 to U+FFFF, surrogates and skip left out, and the
        description of 1 line per code point that build makes, with the gate's result."""
        chars = [chr(code) for code in range(0x10000)
                 if not 0xd800 <= code <= 0xdfff and chr(code) not in skip]
        lines = [build(char) for char in chars]
        code, output = self.description("\n".join(lines) + "\n")
        self.assertIn(code, (0, 1), output[-3:])
        self.assertEqual(output[-1], "pr-text: {} defect(s)".format(len(output) - 1),
                         output[-3:])
        return chars, output

    def reported(self, output, fragment):
        """The line numbers of the output lines that hold fragment."""
        found = set()
        for line in output:
            match = re.match(r"description:([0-9]+): ", line)
            if match and fragment in line:
                found.add(int(match.group(1)))
        return found

    def test_url_ends_only_before_its_stopper_set(self):
        # 1 line per code point: a URL, the code point, then an -ise word. The word is
        # reported only when the code point ends the URL; U+000A ends every line.
        chars, output = self.enumerate_lines(
            lambda char: "https://e.com/x" + char + ISE_WORD)
        ended = {chars[number - 1] for number in self.reported(output, "an -ise spelling")}
        self.assertEqual(sorted(map(ord, ended)), sorted(map(ord, url_stopper_set())))

    def test_fence_closer_takes_only_spaces_and_tabs_after_its_run(self):
        # Per code point: an opener, a closer followed by the code point, a dash line that is
        # prose only when that closer closed the fence, then 2 lines that leave no fence open
        # whichever way the closer went.
        # U+000D is left out, since a carriage return before a line feed is dropped, and a
        # backtick lengthens the closer's run of backticks, which then still closes.
        chars = [chr(code) for code in range(0x10000)
                 if not 0xd800 <= code <= 0xdfff and chr(code) not in ("\n", "\r")]
        blocks = ["```\n```" + char + "\nx " + EM_DASH + "\n```" + char + "\n````\n"
                  for char in chars]
        code, output = self.description("Intro.\n\n" + "".join(blocks))
        self.assertIn(code, (0, 1), output[-3:])
        self.assertNotIn("never closed", "\n".join(output[-3:]))
        closed = {chars[(number - 5) // 5] for number in self.reported(output, "an em dash")}
        self.assertEqual(sorted(map(ord, closed)), sorted(map(ord, FENCE_CLOSER_TAIL + "`")))

    def test_quote_mask_masks_only_its_2_pairs(self):
        # Each code point as an opener closed by itself, by the straight mark and by U+201D,
        # and as a closer after the straight mark and after U+201C, and every ordered pair of
        # 2 quotation marks; the backtick, which opens a code span, and U+000A are left out.
        # A dash between the 2 marks is reported only when the pair is not masked.
        chars = [chr(code) for code in range(0x10000)
                 if not 0xd800 <= code <= 0xdfff and chr(code) not in ("\n", "`")]
        pairs = []
        for char in chars:
            pairs.extend([(char, char), (char, '"'), (char, chr(0x201d)), ('"', char),
                          (chr(0x201c), char)])
        marks = [chr(code) for code in QUOTATION_MARKS]
        pairs.extend((opener, closer) for opener in marks for closer in marks)
        pairs = sorted(set(pairs))
        text = "".join("a " + opener + "x " + EM_DASH + " y" + closer + " b\n"
                       for opener, closer in pairs)
        code, output = self.description(text)
        self.assertIn(code, (0, 1), output[-3:])
        shown = self.reported(output, "an em dash")
        masked = {pairs[number - 1] for number in range(1, len(pairs) + 1)
                  if number not in shown}
        self.assertEqual(masked, set(QUOTE_PAIRS))


class UnreadableInputs(GateCase):
    """The exit contract: each kind of usage error and unreadable input exits 2, with the count
    of the defects reported before it as the last line, and each reason line is pinned.

    The deeply nested payload runs the gate under a soft stack limit of DEEP_STACK, 1 MiB, or
    the hard limit when that is lower, set in a child that then replaces itself with the gate,
    so the JSON reader overflows its stack and the gate reports it through its RecursionError
    branch whatever stack limit the runner has. With a larger stack the reader can read the
    whole payload and raise a ValueError instead, or parse a balanced one with no error.
    """

    def assertUnreadable(self, result, fragment):
        self.assertResult(result, 2, 0)
        self.assertTrue(any(line.startswith("unreadable: ") and fragment in line
                            for line in result[1]), result[1])

    def assertUsage(self, result, fragment):
        self.assertResult(result, 2, 0)
        self.assertTrue(result[1][0].startswith("pr-text: " + fragment), result[1])

    def test_missing_payload_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        self.assertUnreadable(self.run_gate("--event", self.tmp / "none.json", gate=gate),
                              "event payload")

    def test_unparseable_payload_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        result = self.run_gate("--event", self.write("event.json", "{not json"), gate=gate)
        self.assertUnreadable(result, "not JSON")

    def test_deeply_nested_payload_exits_2(self):
        # The gate runs under a stack limit this case sets, so the payload overflows on every
        # runner; the message shows that the RecursionError branch, not the ValueError
        # branch, reported it.
        gate = self.tree(squash=CLEAN_SQUASH)
        for text in ("[" * DEEP_LEVELS, '{"pull_request": ' + "[" * DEEP_LEVELS):
            with self.subTest(start=text[:20]):
                path = self.write("deep.json", text)
                done = run_child(["-I", "-B", gate, "--event", path], memory=GATE_MEMORY,
                                 timeout=GATE_TIMEOUT, cwd=self.cwd, stack=DEEP_STACK,
                                 text=True, encoding="utf-8")
                result = done.returncode, done.stdout.splitlines()
                self.assertUnreadable(result, "not JSON")
                self.assertRegex(result[1][0], r"^unreadable: .*: not JSON: "
                                 r"(?i:stack overflow|maximum recursion depth)")

    def test_other_event_type_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        payload = self.write("push.json", json.dumps({"ref": "refs/heads/main", "commits": []}))
        self.assertUnreadable(self.run_gate("--event", payload, gate=gate),
                              "not a pull request event")

    def test_payload_without_number_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        payload = self.write("event.json", json.dumps({"pull_request": {"body": "A body."}}))
        self.assertUnreadable(self.run_gate("--event", payload, gate=gate), "number")

    def test_body_that_is_a_number_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        payload = self.write("event.json", json.dumps({"pull_request": {"number": 999,
                                                                        "body": 5}}))
        self.assertUnreadable(self.run_gate("--event", payload, gate=gate),
                              "the pull request body is not text")

    def test_undecodable_text_exits_2(self):
        path = self.tmp / "description.md"
        path.write_bytes(b"A body \xff with a bad byte.\n")
        self.assertUnreadable(self.run_gate("--description", path), "not UTF-8")

    def test_undecodable_squash_file_exits_2(self):
        path = self.tmp / "squash.txt"
        path.write_bytes(CLEAN_SQUASH.encode("utf-8") + b"\xfe\n")
        self.assertUnreadable(self.run_gate("--squash", path, "--number", 999), "not UTF-8")

    def test_missing_text_file_exits_2(self):
        self.assertUnreadable(self.run_gate("--description", self.tmp / "none.md"),
                              "description file")

    def test_missing_squash_file_exits_2(self):
        gate = self.tree(squash=None)
        self.assertUnreadable(self.run_gate("--event", self.event("A body."), gate=gate),
                              "squash file")

    def test_missing_squash_file_in_squash_mode_exits_2(self):
        self.assertUnreadable(self.run_gate("--squash", self.tmp / "none.txt", "--number", 999),
                              "squash file")

    def test_squash_name_too_long_to_open_exits_2(self):
        path = self.tmp / "other" / ".github" / "squash" / ("9" * 4301 + ".txt")
        self.assertUnreadable(self.run_gate("--squash", path), "squash file")

    def test_folder_given_as_text_file_exits_2(self):
        self.assertUnreadable(self.run_gate("--description", self.cwd), "description file")

    def test_unreadable_line_names_its_input(self):
        result = self.run_gate("--description", self.tmp / "none.md")
        self.assertResult(result, 2, 0)
        self.assertEqual(result[1][0], "unreadable: description file {}: No such file or "
                         "directory".format(self.tmp / "none.md"), result[1])

    def test_payload_number_below_1_exits_2(self):
        gate = self.tree(squash="Add a thing (#0)\n\nBody.\n", number=0)
        self.assertUnreadable(self.run_gate("--event", self.event("A body.", number=0), gate=gate),
                              "no positive integer pull request number")

    def test_removed_working_directory_exits_2(self):
        folder = self.tmp / "removed"
        code = ("import os, runpy, sys; os.mkdir(sys.argv[1]); os.chdir(sys.argv[1]);"
                " os.rmdir(sys.argv[1]); sys.argv = [sys.argv[2], '--squash', 'x.txt'];"
                " runpy.run_path(sys.argv[0], run_name='__main__')")
        done = run_child(["-I", "-B", "-c", code, folder, GATE], memory=GATE_MEMORY,
                         timeout=GATE_TIMEOUT, cwd=self.cwd, text=True, encoding="utf-8")
        result = (done.returncode, done.stdout.splitlines())
        self.assertUnreadable(result, "the working directory cannot be read")
        self.assertTrue(result[1][0].endswith(
            "the working directory cannot be read: No such file or directory"), result[1])

    def test_unloadable_lint_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        self.assertUnreadable(self.run_gate("--event", self.event("A body."), gate=gate),
                              "label lint")

    def test_lint_that_raises_on_load_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        (gate.parent / "test-no-qa-labels.py").write_text("raise RuntimeError('x')\n")
        self.assertUnreadable(self.run_gate("--description", self.write("d.md", "Hi.\n"),
                                            gate=gate), "label lint")

    def test_lint_that_exits_on_load_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        (gate.parent / "test-no-qa-labels.py").write_text("raise SystemExit(0)\n")
        self.assertUnreadable(self.run_gate("--description", self.write("d.md", "Hi.\n"),
                                            gate=gate), "label lint")

    def test_scan_of_the_wrong_signature_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        (gate.parent / "test-no-qa-labels.py").write_text("def scan(x):\n    return []\n")
        self.assertUnreadable(self.run_gate("--description", self.write("d.md", "Hi.\n"),
                                            gate=gate), "unexpected error: TypeError")

    def test_scan_that_raises_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        (gate.parent / "test-no-qa-labels.py").write_text(
            "def scan(rel, text):\n    raise ValueError('x')\n")
        self.assertUnreadable(self.run_gate("--description", self.write("d.md", "Hi.\n"),
                                            gate=gate), "unexpected error: ValueError")

    def test_scan_that_exits_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        # The second scan is a generator, so it exits when the gate reads its hits.
        for lint in ("def scan(rel, text):\n    raise SystemExit(0)\n",
                     "def scan(rel, text):\n    raise SystemExit(0)\n    yield rel\n"):
            with self.subTest(lint=lint):
                (gate.parent / "test-no-qa-labels.py").write_text(lint)
                result = self.run_gate("--description", self.write("d.md", "Hi.\n"), gate=gate)
                self.assertUnreadable(result, "unexpected error: SystemExit")

    def test_error_whose_message_exits_exits_2(self):
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        error = ("class E(Exception):\n    def __str__(self):\n        raise SystemExit(0)\n\n\n")
        # The first lint raises the error from its scan, the second while it loads.
        for lint, fragment in ((error + "def scan(rel, text):\n    raise E()\n",
                                "unexpected error: E (its message cannot be formatted)"),
                               (error + "raise E()\n",
                                "cannot be loaded: E (its message cannot be formatted)")):
            with self.subTest(lint=lint):
                (gate.parent / "test-no-qa-labels.py").write_text(lint)
                result = self.run_gate("--description", self.write("d.md", "Hi.\n"), gate=gate)
                self.assertUnreadable(result, fragment)

    def run_lint(self, lint):
        """The result of the gate on a clean description, with lint as the label lint."""
        gate = self.tree(squash=CLEAN_SQUASH, lint=False)
        (gate.parent / "test-no-qa-labels.py").write_text(lint)
        return self.run_gate("--description", self.write("d.md", "Hi.\n"), gate=gate)

    def test_lint_interrupted_while_it_loads_exits_2(self):
        self.assertUnreadable(self.run_lint("raise KeyboardInterrupt\n"),
                              "cannot be loaded: KeyboardInterrupt")

    def test_scan_interrupted_exits_2(self):
        self.assertUnreadable(self.run_lint("def scan(rel, text):\n    raise KeyboardInterrupt\n"),
                              "unexpected error: KeyboardInterrupt")

    def test_error_whose_message_raises_an_interrupt_exits_2(self):
        lint = ("class E(Exception):\n    def __str__(self):\n"
                "        raise KeyboardInterrupt\n\n\ndef scan(rel, text):\n    raise E()\n")
        self.assertUnreadable(self.run_lint(lint),
                              "unexpected error: E (its message cannot be formatted)")

    def test_error_whose_type_name_cannot_be_formatted_exits_2(self):
        lint = ("class S(str):\n    def __str__(self):\n        raise SystemExit(0)\n\n\n"
                "class E(Exception):\n    pass\n\n\nE.__name__ = S('E')\n\n\n"
                "def scan(rel, text):\n    raise E('x')\n")
        self.assertUnreadable(self.run_lint(lint), "unexpected error: an exception: x")

    def test_type_name_of_a_str_subclass_is_described_as_text(self):
        # The name formats as itself, a str subclass whose concatenation exits.
        lint = ("class N(str):\n    def __str__(self):\n        return self\n\n"
                "    def __add__(self, other):\n        raise SystemExit(0)\n\n\n"
                "class E(Exception):\n    pass\n\n\nE.__name__ = N('E')\n\n\n"
                "def scan(rel, text):\n    raise E('x')\n")
        self.assertUnreadable(self.run_lint(lint), "unexpected error: E: x")

    def test_message_of_a_str_subclass_is_described_as_text(self):
        # The message formats as a str subclass whose concatenation from the left exits.
        lint = ("class S(str):\n    def __radd__(self, other):\n        raise SystemExit(0)\n\n\n"
                "class E(Exception):\n    def __str__(self):\n        return S('x')\n\n\n"
                "def scan(rel, text):\n    raise E()\n")
        self.assertUnreadable(self.run_lint(lint), "unexpected error: E: x")

    def test_no_arguments_is_a_usage_error(self):
        result = self.run_gate()
        self.assertResult(result, 2, 0)
        self.assertTrue(result[1][0].startswith("pr-text: no mode given; usage: "), result[1])

    def test_bad_arguments_are_usage_errors(self):
        path = self.write("d.md", "Hi.\n")
        for args, fragment in ((("--description",), "--description needs 1 value"),
                               (("--bogus", path), "unknown argument --bogus"),
                               (("--description", path, "--number", "5"),
                                "--number applies to --squash only"),
                               (("--squash", path, "--number", "x"),
                                "--number takes a positive integer"),
                               (("--event", path, "--description", path), "give exactly 1 of"),
                               (("--number", "5"), "give exactly 1 of")):
            with self.subTest(args=args):
                self.assertUsage(self.run_gate(*args), fragment)

    def test_flag_given_twice_is_a_usage_error(self):
        path = self.write("d.md", "Hi.\n")
        self.assertUsage(self.run_gate("--description", path, "--description", path),
                         "--description needs 1 value and is given once")

    def test_number_option_with_a_leading_zero_is_a_usage_error(self):
        path = self.write("squash.txt", CLEAN_SQUASH)
        self.assertUsage(self.run_gate("--squash", path, "--number", "007"),
                         "--number takes a positive integer")

    def test_number_option_over_the_digit_bound_is_a_usage_error(self):
        path = self.write("squash.txt", CLEAN_SQUASH)
        self.assertUsage(self.run_gate("--squash", path, "--number", "9" * 5000),
                         "--number takes at most 18 digits")

    def test_defect_then_unreadable_squash_file_exits_2_with_its_count(self):
        gate = self.tree(squash=None)
        code, lines = self.run_gate("--event", self.event("A body " + EM_DASH + " x.\n",
                                                          number=998), gate=gate)
        self.assertEqual(code, 2, lines)
        self.assertEqual(len(lines), 3, lines)
        self.assertTrue(lines[0].startswith("description:1: an em dash, U+2014"), lines)
        self.assertTrue(lines[1].startswith("unreadable: squash file "), lines)
        self.assertEqual(lines[2], "pr-text: 1 defect(s)")

    def test_payload_number_true_is_not_an_integer(self):
        gate = self.tree(squash="Add a thing (#1)\n\nBody.\n", number=1)
        self.assertUnreadable(self.run_gate("--event", self.event("A body.", number=True),
                                            gate=gate),
                              "no positive integer pull request number")

    def test_payload_that_is_a_list_is_not_a_pull_request_event(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        payload = self.write("event.json", json.dumps([{"pull_request": {"number": 999}}]))
        self.assertUnreadable(self.run_gate("--event", payload, gate=gate),
                              "not a pull request event")

    def test_number_option_with_trailing_text_is_a_usage_error(self):
        path = self.write("squash.txt", CLEAN_SQUASH)
        self.assertUsage(self.run_gate("--squash", path, "--number", "5x"),
                         "--number takes a positive integer")

    def test_number_option_of_18_digits_binds_and_19_is_a_usage_error(self):
        path = self.write("squash.txt", "Add a thing (#" + "9" * 18 + ")\n\nBody.\n")
        self.assertResult(self.run_gate("--squash", path, "--number", "9" * 18), 0, 0)
        self.assertUsage(self.run_gate("--squash", path, "--number", "9" * 19),
                         "--number takes at most 18 digits")


class OutputAndHonestTexts(GateCase):
    """Output prefixes, runs from other folders, cost bounds, and honest texts that pass."""

    def assertPrefixed(self, lines):
        self.assertTrue(lines)
        for line in lines:
            self.assertTrue(line.startswith(PREFIXES), line)
            self.assertTrue(line.isascii(), line)

    def test_defect_lines_start_with_their_prefix(self):
        text = "::error::" + ROUND_LABEL + "\n::warning::x " + EM_DASH + " y\n"
        gate = self.tree(squash="::error::" + EM_DASH + "\n")
        code, lines = self.run_gate("--event", self.event(text), gate=gate)
        self.assertEqual(code, 1, lines)
        self.assertPrefixed(lines)
        self.assertTrue(any(line.startswith("description:1: ") for line in lines), lines)
        self.assertTrue(any(line.startswith("squash:1: ") for line in lines), lines)

    def test_unreadable_lines_start_with_their_prefix(self):
        payload = self.write("::error::x.json", "::error::not json\n")
        gate = self.tree(squash=CLEAN_SQUASH)
        code, lines = self.run_gate("--event", payload, gate=gate)
        self.assertEqual(code, 2, lines)
        self.assertPrefixed(lines)
        self.assertTrue(lines[0].startswith("unreadable: "), lines)

    def test_carriage_return_and_del_are_escaped(self):
        path = self.write("description.md", "a\r::error::b\x7fc " + EM_DASH + " d\n")
        done = run_child(["-I", "-B", GATE, "--description", path], memory=GATE_MEMORY,
                         timeout=GATE_TIMEOUT, cwd=self.cwd)
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertNotIn(b"\r", done.stdout)
        self.assertNotIn(b"\x7f", done.stdout)
        self.assertIn(b"a\\x0d::error::b\\x7fc \\u2014 d", done.stdout)

    def test_reported_line_escapes_each_range_edge(self):
        text = "a " + EM_DASH + " \x1f ~\x7f\xff\u0100\uffff\U00010000 b\n"
        result = self.description(text)
        self.assertResult(result, 1, 1)
        self.assertIn("description:1: an em dash, U+2014: a \\u2014 \\x1f ~\\x7f\\xff\\u0100"
                      "\\uffff\\U00010000 b", result[1])

    def test_squash_file_with_crlf_line_endings_passes(self):
        path = self.tmp / "squash.txt"
        text = CLEAN_SQUASH + "\n```\ncode\n```\n"
        path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        self.assertResult(self.run_gate("--squash", path, "--number", 999), 0, 0)

    def test_event_body_with_crlf_line_endings_passes(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        body = "Intro.\r\n\r\n```\r\ncode\r\n```\r\n\r\nAfter.\r\n"
        self.assertResult(self.run_gate("--event", self.event(body), gate=gate), 0, 0)

    def test_event_from_another_working_directory(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        result = self.run_gate("--event", self.event("A clean body."), gate=gate, cwd=self.cwd)
        self.assertResult(result, 0, 0)

    def test_hand_run_on_files_outside_the_tree(self):
        outside = self.tmp / "frozen"
        outside.mkdir()
        body = outside / "body.md"
        body.write_text("A frozen description.\n", encoding="utf-8")
        message = outside / "squash.txt"
        message.write_text(CLEAN_SQUASH, encoding="utf-8")
        self.assertResult(self.run_gate("--description", body, cwd=self.cwd), 0, 0)
        self.assertResult(self.run_gate("--squash", message, "--number", 999, cwd=self.cwd), 0, 0)

    def test_long_backtick_run_is_scanned_in_bounded_time(self):
        path = self.write("description.md", "x " + "`" * BACKTICK_RUN + "\n")
        start = time.monotonic()
        try:
            result = self.run_gate("--description", path, timeout=TIME_BOUND)
        except subprocess.TimeoutExpired:
            self.fail("the gate ran over {} s on {} backticks".format(TIME_BOUND, BACKTICK_RUN))
        self.assertLess(time.monotonic() - start, TIME_BOUND)
        self.assertResult(result, 0, 0)

    def test_code_span_scan_ends_on_each_run_shape(self):
        # A closed span, a lone run, and a run with no closer before a closed span, each
        # under a wall timeout of SPAN_TIMEOUT s and GATE_MEMORY bytes, so a scan that stops
        # advancing fails here by a limit in seconds; the output pins which runs were masked.
        text = ("A closed `span " + EM_DASH + "` here.\nA lone ` run " + EM_DASH
                + " here.\nA run `` with no closer, then `code " + EM_DASH + "` here.\n")
        result = self.run_gate("--description", self.write("description.md", text),
                               timeout=SPAN_TIMEOUT)
        self.assertEqual(result, (1, ["description:2: an em dash, U+2014: A lone ` run "
                                      "\\u2014 here.", "pr-text: 1 defect(s)"]))

    def test_child_over_its_memory_limit_fails_by_it(self):
        code = ("import resource, sys; print(*resource.getrlimit(resource.RLIMIT_AS));"
                " sys.stdout.flush(); bytearray(int(sys.argv[1]))")
        limit = memory_limit(GATE_MEMORY)
        done = run_child(["-I", "-B", "-c", code, limit + 64 * 1024 * 1024], memory=GATE_MEMORY,
                         timeout=GATE_TIMEOUT, cwd=self.cwd, text=True, encoding="utf-8")
        self.assertEqual(done.stdout.split(), [str(limit)] * 2, done.stderr)
        self.assertNotEqual(done.returncode, 0, done.stderr)
        self.assertIn("MemoryError", done.stderr)

    def test_child_over_its_wall_timeout_is_stopped(self):
        start = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            run_child(["-I", "-B", "-c", "while True: pass"], memory=GATE_MEMORY, timeout=1,
                      cwd=self.cwd)
        self.assertLess(time.monotonic() - start, SPAN_TIMEOUT)

    def test_child_reads_its_cpu_limit(self):
        code = "import resource; print(*resource.getrlimit(resource.RLIMIT_CPU))"
        done = run_child(["-I", "-B", "-c", code], memory=GATE_MEMORY, timeout=GATE_TIMEOUT,
                         cwd=self.cwd, text=True, encoding="utf-8")
        self.assertEqual(done.stdout.split(), [str(limit) for limit in cpu_limits(GATE_CPU)],
                         done.stderr)

    def test_child_over_its_cpu_limit_is_named(self):
        # A child that spins under a CPU limit of 1 s ends by SIGXCPU within its wall timeout,
        # and run_child() names the limit on a LIMIT_HIT line, which the sweep reads.
        found = io.StringIO()
        with contextlib.redirect_stderr(found):
            done = run_child(["-I", "-B", "-c", "while True: pass"], memory=GATE_MEMORY,
                             timeout=SPAN_TIMEOUT, cwd=self.cwd, cpu=1)
        self.assertEqual(done.returncode, -signal.SIGXCPU, found.getvalue())
        self.assertEqual(found.getvalue(), "{}the CPU limit of {} s (SIGXCPU)\n".format(
            LIMIT_HIT, cpu_limits(1)[0]))

    def stop_recorded(self, folder):
        """Kill each process whose PID a case recorded in folder; ignore one already gone."""
        for name in ("grandchild.pid", "parent.pid"):
            path = folder / name
            if path.exists() and path.read_text().strip().isdigit():
                try:
                    os.kill(int(path.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_grandchild_ends_with_its_timed_out_parent(self):
        # The nested shape of the sweep: a parent child started through run_child() starts a
        # spinning grandchild through run_child() and is stopped by its own wall timeout. Once
        # the parent is gone and this process has closed its copy, only the grandchild holds
        # the write end of the pipe, so the read end sees EOF only when the grandchild has
        # ended, whether or not a parent has reaped it. The cleanup kills each recorded PID.
        read, write = os.pipe()
        self.addCleanup(os.close, read)
        self.addCleanup(self.stop_recorded, self.tmp)
        try:
            with self.assertRaises(subprocess.TimeoutExpired):
                run_child(["-I", "-B", "-c", ORPHAN_PARENT, SUITE, write, self.tmp, ORPHAN_SPIN],
                          memory=GATE_MEMORY, timeout=ORPHAN_TIMEOUT, cwd=self.cwd,
                          pass_fds=(write,))
        finally:
            os.close(write)
        found, ended = b"", False
        deadline = time.monotonic() + ORPHAN_BOUND
        while not ended and select.select([read], [], [], max(0, deadline - time.monotonic()))[0]:
            chunk = os.read(read, 64)
            found, ended = found + chunk, not chunk
        self.assertEqual(found, b"started\n", "the grandchild did not start")
        self.assertTrue(ended, "the grandchild ran on {} s after the timeout of its parent".format(
            ORPHAN_BOUND))

    def test_every_child_runs_under_its_limits(self):
        # The one call that starts a process is in run_child(): it starts LIMIT_LAUNCH, an
        # outermost call in a new session, waits with a timeout, and kills the child's group
        # on a timeout; run_child() takes its memory limit and timeout with no default, and
        # LIMIT_LAUNCH sets the memory and CPU limits and the mark of a nested call.
        def starts_a_process(node):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)):
                return False
            module, name = node.func.value.id, node.func.attr
            return (module == "subprocess" and name in (
                "run", "Popen", "call", "check_call", "check_output", "getoutput",
                "getstatusoutput") or module == "os" and name.startswith(
                    ("exec", "spawn", "system", "popen", "fork", "posix_spawn")))
        tree = ast.parse(SUITE.read_text(encoding="utf-8"))
        calls = [node for node in ast.walk(tree) if starts_a_process(node)]
        self.assertEqual([ast.unparse(node.func) for node in calls], ["subprocess.Popen"])
        child = next(node for node in ast.walk(tree)
                     if isinstance(node, ast.FunctionDef) and node.name == "run_child")
        call = next(node for node in ast.walk(child) if starts_a_process(node))
        self.assertIn(("start_new_session", "outermost"),
                      [(keyword.arg, ast.unparse(keyword.value)) for keyword in call.keywords])
        self.assertEqual(ast.unparse(call.args[0]), "command")
        made = [ast.unparse(node) for node in ast.walk(child) if isinstance(node, ast.Call)]
        self.assertIn("child.communicate(timeout=timeout)", made)
        self.assertIn("os.killpg(child.pid, signal.SIGKILL)", made)
        assigned = [ast.unparse(node) for node in ast.walk(child) if isinstance(node, ast.Assign)]
        self.assertIn("outermost = os.environ.get(CHILD_MARK) != '1'", assigned)
        command = next(node.value for node in ast.walk(child) if isinstance(node, ast.Assign)
                       and ast.unparse(node.targets[0]) == "command")
        self.assertEqual([ast.unparse(item) for item in command.elts[:5]],
                         ["sys.executable", "'-I'", "'-B'", "'-c'", "LIMIT_LAUNCH"])
        self.assertEqual([arg.arg for arg in child.args.kwonlyargs[:2]], ["memory", "timeout"])
        self.assertEqual(child.args.kw_defaults[:2], [None, None])
        self.assertIn("resource.setrlimit(resource.RLIMIT_AS", LIMIT_LAUNCH)
        self.assertIn("resource.setrlimit(resource.RLIMIT_CPU", LIMIT_LAUNCH)
        self.assertIn("os.environ['" + CHILD_MARK + "'] = '1'", LIMIT_LAUNCH)

    def test_workflow_job_has_a_time_limit(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        found = re.findall(r"(?m)^    timeout-minutes: ([0-9]+)$", text)
        self.assertEqual(len(found), 1, "the check job needs 1 timeout-minutes line")
        self.assertTrue(1 <= int(found[0]) <= 30, found)

    def test_clean_event_passes(self):
        body = ("## Summary\n\nAdds a gate, in 3 files, with a range of 12-14 and the word"
                " advise.\r\n\r\n- See `tools/check-pr-text.py`.\n")
        gate = self.tree(squash=CLEAN_SQUASH)
        self.assertResult(self.run_gate("--event", self.event(body), gate=gate), 0, 0)

    def test_one_em_dash_in_an_event_is_one_defect(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        body = "A body " + EM_DASH + " with 1 dash.\n"
        self.assertResult(self.run_gate("--event", self.event(body), gate=gate), 1, 1)

    def test_event_description_has_no_width_or_revision_check(self):
        gate = self.tree(squash=CLEAN_SQUASH)
        body = ("Built on e233a7f." + " word" * 40)[:127]
        self.assertResult(self.run_gate("--event", self.event(body), gate=gate), 0, 0)

    def test_gate_run_without_dash_b_writes_no_bytecode(self):
        # The workflow runs the gate with -I alone, so the gate itself keeps the lint it
        # loads from writing a bytecode file into the tree.
        gate = self.tree(squash=CLEAN_SQUASH)
        done = run_child(["-I", gate, "--event", self.event("A body.")], memory=GATE_MEMORY,
                         timeout=GATE_TIMEOUT, cwd=self.cwd, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertFalse((gate.parent / "__pycache__").exists())


D = "DefectClasses."
E = "Exemptions."
U = "UnreadableInputs."
O = "OutputAndHonestTexts."


# The site generator of the sweep: it reads the gate source and yields each mutation
# site of the closed set OPERATORS; see MutantSweep.
GATE_FUNCTIONS = ("compile", "fullmatch", "match", "search")
MATCH_METHODS = ("fullmatch", "match", "search")
COMPARE_PARTNERS = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
                    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Is: ast.IsNot,
                    ast.IsNot: ast.Is, ast.In: ast.NotIn, ast.NotIn: ast.In}
COMPARE_TEXT = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==",
                ast.NotEq: "!=", ast.Is: "is", ast.IsNot: "is not", ast.In: "in",
                ast.NotIn: "not in"}
# The closed set of operators the generator applies, in the order it reports them.
OPERATORS = (
    "statement deleted", "comparison changed", "boolean operator swapped", "not removed",
    "boolean constant flipped", "integer constant changed", "exception type removed",
    "BaseException narrowed", "handler body replaced by raise", "match method changed",
    "any and all swapped", "pattern member removed", "regex anchor deleted",
    "regex lookaround deleted", "regex alternative deleted", "regex class member deleted",
    "regex class made plain", "regex quantifier changed", "regex escape removed",
    "regex flag removed",
)
REGEX_META = ".^$*+?{}[]()|\\"
REGEX_CLASS_ESCAPES = "sSdDwWntrfv"
REGEX_ANCHOR_ESCAPES = "bBAZ"
PLACEHOLDER = "\x00"
Site = collections.namedtuple("Site", "words operator old new occurrence count")


class UnknownConstruct(Exception):
    """A construct of the gate's source that the generator does not know."""


def ordinal(number):
    """1st, 2nd, 3rd, 4th and so on."""
    if number % 100 in (11, 12, 13):
        return "{}th".format(number)
    return "{}{}".format(number, {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th"))


def occurrences(text, old):
    """The offsets of every occurrence of old in text, overlapping ones included."""
    found = []
    start = text.find(old)
    while start != -1:
        found.append(start)
        start = text.find(old, start + 1)
    return found


def apply_site(text, site):
    """text with the site applied, or None when its old text no longer occurs as recorded."""
    starts = occurrences(text, site.old)
    if len(starts) != site.count or not 1 <= site.occurrence <= len(starts):
        return None
    start = starts[site.occurrence - 1]
    return text[:start] + site.new + text[start + len(site.old):]


class SourceMap:
    """Offsets of the gate source by line and column; the gate is ASCII, so a column is a byte."""

    def __init__(self, text):
        if not text.isascii():
            raise UnknownConstruct("the gate source is not ASCII")
        self.text = text
        self.starts = [0]
        for index, char in enumerate(text):
            if char == "\n":
                self.starts.append(index + 1)

    def offset(self, line, column):
        return self.starts[line - 1] + column

    def start(self, node):
        return self.offset(node.lineno, node.col_offset)

    def end(self, node):
        return self.offset(node.end_lineno, node.end_col_offset)

    def line_start(self, line):
        return self.starts[line - 1]

    def line_end(self, line):
        """The offset just past the line feed that ends line."""
        return self.starts[line] if line < len(self.starts) else len(self.text)

    def segment(self, node):
        return self.text[self.start(node):self.end(node)]


def edited(text, edits):
    """text with each (start, end, replacement) edit made; edits do not overlap."""
    for start, end, new in sorted(edits, reverse=True):
        text = text[:start] + new + text[end:]
    return text


def as_site(text, mutated, words, operator):
    """The site that turns text into mutated, as the smallest block of whole lines."""
    old_lines = text.split("\n")
    new_lines = mutated.split("\n")
    first = 0
    while first < min(len(old_lines), len(new_lines)) and old_lines[first] == new_lines[first]:
        first += 1
    tail = 0
    while (tail < min(len(old_lines), len(new_lines)) - first
           and old_lines[-1 - tail] == new_lines[-1 - tail]):
        tail += 1
    if first == 0:
        raise UnknownConstruct("a change on the first line: " + words)
    old_block = old_lines[first:len(old_lines) - tail]
    new_block = new_lines[first:len(new_lines) - tail]
    old = "\n" + "".join(line + "\n" for line in old_block)
    new = "\n" + "".join(line + "\n" for line in new_block)
    offset = sum(len(line) + 1 for line in old_lines[:first]) - 1
    starts = occurrences(text, old)
    site = Site(words, operator, old, new, starts.index(offset) + 1, len(starts))
    if apply_site(text, site) != mutated:
        raise UnknownConstruct("a site that does not reproduce its change: " + words)
    return site


def scope_name(stack):
    """The words that name where a node is: a function, a method or a module constant."""
    return "in " + stack[-1] if stack else "at module level"


def regex_parse(pattern):
    """The mutation sites of 1 pattern, as (operator, words, edits on the pattern) triples.

    The tokenizer knows the constructs the gate's patterns use: literals, the escapes \\s \\S
    \\d \\D \\w \\W \\n \\t \\r \\f \\v \\uXXXX \\xXX, an escaped metacharacter or quote mark,
    the anchors ^ $ \\A \\Z \\b \\B, the dot, character classes with ranges and negation,
    groups (plain, (?:, (?=, (?!, (?<= and (?<!), inline flags such as (?i), alternation and the
    quantifiers * + ? {m} {m,} {m,n}, each greedy or lazy. Anything else raises
    UnknownConstruct with its text.
    """
    found = []
    position = [0]

    def peek(offset=0):
        index = position[0] + offset
        return pattern[index] if index < len(pattern) else ""

    def escape_length(index):
        """The length of the escape that starts at index, and whether it is an anchor."""
        char = pattern[index + 1] if index + 1 < len(pattern) else ""
        if char in REGEX_ANCHOR_ESCAPES and char:
            return 2, "anchor"
        if char == "u":
            if not re.fullmatch(r"[0-9a-fA-F]{4}", pattern[index + 2:index + 6]):
                raise UnknownConstruct("a short \\u escape in " + pattern)
            return 6, "atom"
        if char == "x":
            return 4, "atom"
        if char and char in REGEX_CLASS_ESCAPES:
            return 2, "atom"
        if char and char in REGEX_META:
            return 2, "meta"
        if char in ("\"", "'"):
            return 2, "atom"
        raise UnknownConstruct("the escape \\{} in {}".format(char, pattern))

    def quantifier(atom_start):
        start = position[0]
        char = peek()
        if char in ("*", "+", "?"):
            position[0] += 1
            kind = char
        elif char == "{":
            match = re.compile(r"\{([0-9]+)(,?)([0-9]*)\}").match(pattern, start)
            if not match:
                raise UnknownConstruct("a brace that is not a quantifier in " + pattern)
            position[0] = match.end()
            kind = "{}"
        else:
            return
        text = pattern[start:position[0]]
        lazy = peek() == "?"
        if peek() == "+":
            raise UnknownConstruct("a possessive quantifier in " + pattern)
        if lazy:
            position[0] += 1
        whole = pattern[start:position[0]]
        changes = []
        if kind == "*":
            changes.append("+")
        elif kind == "+":
            changes.append("*")
        elif kind == "?":
            changes.append("")
        else:
            low, comma, high = match.group(1), match.group(2), match.group(3)
            low = int(low)
            if comma and high:
                high = int(high)
                if low >= 1:
                    changes.append("{{{},{}}}".format(low - 1, high))
                if low + 1 <= high:
                    changes.append("{{{},{}}}".format(low + 1, high))
                if high - 1 >= max(low, 1):
                    changes.append("{{{},{}}}".format(low, high - 1))
                changes.append("{{{},{}}}".format(low, high + 1))
            elif comma:
                if low >= 1:
                    changes.append("{{{},}}".format(low - 1))
                changes.append("{{{},}}".format(low + 1))
            else:
                if low >= 1:
                    changes.append("{{{}}}".format(low - 1))
                changes.append("{{{}}}".format(low + 1))
        for change in changes:
            new = change + ("?" if lazy and change else "")
            found.append(("regex quantifier changed",
                          "the quantifier `{}` changed to `{}`".format(whole, new or "nothing"),
                          [(start, position[0], new)]))
        if lazy:
            found.append(("regex quantifier changed",
                          "the lazy quantifier `{}` made greedy".format(whole),
                          [(position[0] - 1, position[0], "")]))
        else:
            found.append(("regex quantifier changed",
                          "the quantifier `{}` made lazy".format(whole),
                          [(position[0], position[0], "?")]))

    def char_class():
        start = position[0]
        position[0] += 1
        negated = peek() == "^"
        if negated:
            position[0] += 1
        members = []
        if peek() == "]":
            raise UnknownConstruct("a class that starts with ] in " + pattern)
        while True:
            char = peek()
            if not char:
                raise UnknownConstruct("an unclosed class in " + pattern)
            if char == "]":
                position[0] += 1
                break
            member_start = position[0]
            if char == "\\":
                length, kind = escape_length(position[0])
                if kind == "anchor":
                    raise UnknownConstruct("an anchor escape in a class in " + pattern)
                position[0] += length
            elif char == "[":
                raise UnknownConstruct("a nested class in " + pattern)
            else:
                position[0] += 1
            if peek() == "-" and peek(1) not in ("]", ""):
                position[0] += 1
                if peek() == "\\":
                    position[0] += escape_length(position[0])[0]
                else:
                    position[0] += 1
            members.append((member_start, position[0]))
        text = pattern[start:position[0]]
        if len(members) >= 2:
            for member_start, member_end in members:
                found.append(("regex class member deleted",
                              "the member `{}` deleted from the class `{}`".format(
                                  pattern[member_start:member_end], text),
                              [(member_start, member_end, "")]))
        if negated:
            found.append(("regex class made plain",
                          "the negated class `{}` made plain".format(text),
                          [(start + 1, start + 2, "")]))

    def sequence(depth):
        """Parse branches up to a closing parenthesis or the end; record the alternatives."""
        branches = []
        branch_start = position[0]
        while True:
            char = peek()
            if char == "" or char == ")":
                if char == ")" and depth == 0:
                    raise UnknownConstruct("an unbalanced ) in " + pattern)
                branches.append((branch_start, position[0]))
                break
            if char == "|":
                branches.append((branch_start, position[0]))
                position[0] += 1
                branch_start = position[0]
                continue
            atom()
        if len(branches) >= 2:
            for index, (start, end) in enumerate(branches):
                if index == 0:
                    span = (start, branches[1][0])
                else:
                    span = (branches[index - 1][1], end)
                found.append(("regex alternative deleted",
                              "the alternative `{}` deleted".format(pattern[start:end]),
                              [(span[0], span[1], "")]))

    def atom():
        start = position[0]
        char = peek()
        if char == "(":
            head = pattern[start:start + 4]
            flags = re.compile(r"\(\?([a-zA-Z]+)\)").match(pattern, start)
            if flags:
                position[0] = flags.end()
                found.append(("regex flag removed",
                              "the inline flag `{}` deleted".format(flags.group(0)),
                              [(start, flags.end(), "")]))
                return
            if head.startswith("(?<=") or head.startswith("(?<!"):
                kind, position[0] = "lookbehind", start + 4
            elif head.startswith("(?=") or head.startswith("(?!"):
                kind, position[0] = "lookahead", start + 3
            elif head.startswith("(?:"):
                kind, position[0] = "group", start + 3
            elif head.startswith("(?"):
                raise UnknownConstruct("the group {} in {}".format(head, pattern))
            else:
                kind, position[0] = "group", start + 1
            sequence(1)
            if peek() != ")":
                raise UnknownConstruct("an unclosed group in " + pattern)
            position[0] += 1
            if kind != "group":
                found.append(("regex lookaround deleted",
                              "the {} `{}` deleted".format(kind, pattern[start:position[0]]),
                              [(start, position[0], "")]))
                if peek() in ("*", "+", "?", "{"):
                    raise UnknownConstruct("a repeated lookaround in " + pattern)
                return
            quantifier(start)
            return
        if char == "[":
            char_class()
            quantifier(start)
            return
        if char in ("^", "$"):
            position[0] += 1
            found.append(("regex anchor deleted", "the anchor `{}` deleted".format(char),
                          [(start, start + 1, "")]))
            return
        if char == "\\":
            length, kind = escape_length(start)
            position[0] += length
            text = pattern[start:position[0]]
            if kind == "anchor":
                found.append(("regex anchor deleted", "the anchor `{}` deleted".format(text),
                              [(start, position[0], "")]))
                return
            if kind == "meta":
                found.append(("regex escape removed",
                              "the escape of `{}` removed".format(text),
                              [(start, start + 1, "")]))
            quantifier(start)
            return
        if char in ("*", "+", "?", "{"):
            raise UnknownConstruct("a quantifier with nothing to repeat in " + pattern)
        position[0] += 1
        quantifier(start)

    sequence(0)
    return found


def string_tokens(source):
    """The (start, end, text) offsets of every string token of source."""
    tokens = []
    smap = SourceMap(source)
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.STRING:
            tokens.append((smap.offset(*token.start), smap.offset(*token.end), token.string))
    return tokens


def pattern_pieces(node, smap, tokens):
    """(pattern, offsets) of a pattern expression: each source offset, or None for a part
    that is not a string literal, which stands as 1 placeholder character."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = pattern_pieces(node.left, smap, tokens)
        right = pattern_pieces(node.right, smap, tokens)
        return left[0] + right[0], left[1] + right[1]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        text, offsets = "", []
        start, end = smap.start(node), smap.end(node)
        for token_start, token_end, token in tokens:
            if token_start < start or token_end > end:
                continue
            prefix = re.match(r"[A-Za-z]*", token).group(0)
            quote = token[len(prefix)]
            if token[len(prefix):len(prefix) + 3] == quote * 3:
                raise UnknownConstruct("a triple-quoted pattern: " + token)
            body = token[len(prefix) + 1:-1]
            if "r" not in prefix.lower() and "\\" in body:
                raise UnknownConstruct("a pattern literal that is not raw: " + token)
            text += body
            offsets.extend(range(token_start + len(prefix) + 1, token_end - 1))
        if text != node.value:
            raise UnknownConstruct("a pattern literal the tokens do not rebuild: " + token)
        return text, offsets
    return PLACEHOLDER, [None]


def pattern_edits(offsets, edits):
    """The source edits of edits on a pattern, or None when one touches a placeholder."""
    source = []
    for start, end, new in edits:
        if start == end:
            if start == 0 or offsets[start - 1] is None:
                return None
            source.append((offsets[start - 1] + 1, offsets[start - 1] + 1, new))
            continue
        span = offsets[start:end]
        if None in span:
            return None
        runs = [[span[0], span[0] + 1]]
        for offset in span[1:]:
            if offset == runs[-1][1]:
                runs[-1][1] = offset + 1
            else:
                runs.append([offset, offset + 1])
        source.append((runs[0][0], runs[0][1], new))
        source.extend((run_start, run_end, "") for run_start, run_end in runs[1:])
    return source


def is_re_call(node):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "re"
            and node.func.attr in GATE_FUNCTIONS)


def generate_sites(source):
    """Every mutation site of the gate source, for the closed set of OPERATORS."""
    smap = SourceMap(source)
    tree = ast.parse(source)
    tokens = string_tokens(source)
    raw = []

    def add(operator, words, edits):
        raw.append((operator, words, edited(source, edits)))

    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    body = [node for node in body if not (
        isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__")]
    pattern_names = set()
    pattern_calls = []

    def statements(stack, block, inside):
        """Deletion sites of each statement of a block, and of each block within it."""
        for statement in block:
            if (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)):
                continue
            if isinstance(statement, (ast.FunctionDef, ast.ClassDef)):
                continue
            if inside:
                first = smap.line_start(statement.lineno)
                last = smap.line_end(statement.end_lineno)
                line = source[first:smap.line_end(statement.lineno)]
                indent = line[:len(line) - len(line.lstrip(" "))]
                only = len([s for s in block if not (
                    isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]) == 1
                head = line.strip()
                add("statement deleted", "{}, the statement `{}` deleted".format(
                    scope_name(stack), head),
                    [(first, last, indent + "pass\n" if only else "")])
            for field in ("body", "orelse", "finalbody"):
                inner = getattr(statement, field, None)
                if isinstance(inner, list) and inner and isinstance(inner[0], ast.stmt):
                    statements(stack, inner, inside)
            for handler in getattr(statement, "handlers", []):
                statements(stack, handler.body, inside)

    def expressions(stack, node):
        """The expression sites of node and every node within it."""
        for child in ast.walk(node):
            where = scope_name(stack)
            if isinstance(child, ast.Compare):
                operands = [child.left] + list(child.comparators)
                for index, operator in enumerate(child.ops):
                    gap_start = smap.end(operands[index])
                    gap_end = smap.start(operands[index + 1])
                    gap = source[gap_start:gap_end]
                    old = COMPARE_TEXT[type(operator)]
                    new = COMPARE_TEXT[COMPARE_PARTNERS[type(operator)]]
                    match = re.search(r"(?<![<>=!a-z])" + re.escape(old).replace(r"\ ", r"\s+")
                                      + r"(?![<>=a-z])", gap)
                    if not match:
                        raise UnknownConstruct("a comparison whose operator is not found: " + gap)
                    add("comparison changed", "{}, `{}` changed to `{}` in `{}`".format(
                        where, old, new, smap.segment(child)),
                        [(gap_start + match.start(), gap_start + match.end(), new)])
            elif isinstance(child, ast.BoolOp):
                old = "and" if isinstance(child.op, ast.And) else "or"
                new = "or" if old == "and" else "and"
                for index in range(len(child.values) - 1):
                    gap_start = smap.end(child.values[index])
                    gap = source[gap_start:smap.start(child.values[index + 1])]
                    match = re.search(r"\b" + old + r"\b", gap)
                    if not match:
                        raise UnknownConstruct("a boolean operator not found: " + gap)
                    add("boolean operator swapped", "{}, `{}` changed to `{}` before `{}`".format(
                        where, old, new, smap.segment(child.values[index + 1])),
                        [(gap_start + match.start(), gap_start + match.end(), new)])
            elif isinstance(child, ast.UnaryOp) and isinstance(child.op, ast.Not):
                add("not removed", "{}, `not` removed from `{}`".format(
                    where, smap.segment(child)),
                    [(smap.start(child), smap.start(child.operand), "")])
            elif isinstance(child, ast.Constant) and isinstance(child.value, bool):
                add("boolean constant flipped", "{}, `{}` changed to `{}` in `{}`".format(
                    where, child.value, not child.value, line_of(child)),
                    [(smap.start(child), smap.end(child), str(not child.value))])
            elif (isinstance(child, ast.Constant) and isinstance(child.value, int)
                  and not isinstance(child.value, bool)):
                text = smap.segment(child)
                for step, way in ((1, "up"), (-1, "down")):
                    value = child.value + step
                    new = format(value, "#x") if text.startswith("0x") else str(value)
                    add("integer constant changed", "{}, `{}` changed {} to `{}` in `{}`".format(
                        where, text, way, new, line_of(child)),
                        [(smap.start(child), smap.end(child), new)])
            elif isinstance(child, ast.Call):
                function = child.func
                if (isinstance(function, ast.Attribute) and function.attr in MATCH_METHODS):
                    end = smap.end(function)
                    for other in MATCH_METHODS:
                        if other != function.attr:
                            add("match method changed", "{}, `{}` changed to `{}` in `{}`".format(
                                where, function.attr, other, line_of(child)),
                                [(end - len(function.attr), end, other)])
                if isinstance(function, ast.Name) and function.id in ("any", "all"):
                    other = "all" if function.id == "any" else "any"
                    add("any and all swapped", "{}, `{}` changed to `{}`".format(
                        where, function.id, other),
                        [(smap.start(function), smap.end(function), other)])
                if is_re_call(child):
                    pattern_calls.append((stack[-1] if stack else None, child))
            elif isinstance(child, ast.ExceptHandler):
                handler_sites(stack, child)

    def line_of(node):
        line = source[smap.line_start(node.lineno):smap.line_end(node.lineno)]
        return line.strip()

    def handler_sites(stack, handler):
        where = scope_name(stack)
        head = line_of(handler)
        kind = handler.type
        if isinstance(kind, ast.Tuple) and len(kind.elts) >= 2:
            names = [smap.segment(element) for element in kind.elts]
            for index, name in enumerate(names):
                rest = names[:index] + names[index + 1:]
                new = "(" + ", ".join(rest) + ("," if len(rest) == 1 else "") + ")"
                add("exception type removed", "{}, `{}` removed from `{}`".format(
                    where, name, head), [(smap.start(kind), smap.end(kind), new)])
        if isinstance(kind, ast.Name) and kind.id == "BaseException":
            add("BaseException narrowed", "{}, `BaseException` changed to `Exception` in `{}`"
                .format(where, head), [(smap.start(kind), smap.end(kind), "Exception")])
        first = smap.line_start(handler.body[0].lineno)
        last = smap.line_end(handler.body[-1].end_lineno)
        line = source[first:smap.line_end(handler.body[0].lineno)]
        indent = line[:len(line) - len(line.lstrip(" "))]
        add("handler body replaced by raise", "{}, the body of `{}` replaced by `raise`".format(
            where, head), [(first, last, indent + "raise\n")])

    for node in body:
        if isinstance(node, ast.FunctionDef):
            stack = [node.name + "()"]
            statements(stack, node.body, True)
            expressions(stack, node)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    stack = ["{}.{}()".format(node.name, item.name)]
                    statements(stack, item.body, True)
                    expressions(stack, item)
                elif not (isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant)):
                    raise UnknownConstruct("a class body statement: " + line_of(item))
        else:
            name = None
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
            stack = ["the constant " + name] if name else []
            expressions(stack, node)

    constants = {node.targets[0].id: node.value for node in body
                 if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    for scope, call in pattern_calls:
        if not call.args:
            raise UnknownConstruct("a re call with no pattern")
        where = "in the pattern " + (scope[len("the constant "):] if scope and scope.startswith(
            "the constant ") else "of `{}` in {}".format(smap.segment(call.func), scope))
        argument = call.args[0]
        for part in ast.walk(argument):
            if (isinstance(part, ast.Call) and isinstance(part.func, ast.Attribute)
                    and part.func.attr == "join" and part.args
                    and isinstance(part.args[0], ast.Name)):
                pattern_names.add(part.args[0].id)
        pattern, offsets = pattern_pieces(argument, smap, tokens)
        for operator, words, edits in regex_parse(pattern):
            source_edits = pattern_edits(offsets, edits)
            if source_edits is None:
                raise UnknownConstruct("a regex site that touches a joined part: " + words)
            add(operator, "{}, {}".format(where, words), source_edits)
        if call.func.attr == "compile":
            extra = list(call.args[1:]) + [keyword.value for keyword in call.keywords]
            for flag in extra:
                add("regex flag removed", "{}, the flags argument `{}` removed".format(
                    where, smap.segment(flag)),
                    [(smap.end(argument), smap.end(flag), "")])
    for name in sorted(pattern_names):
        value = constants.get(name)
        if not (isinstance(value, ast.Tuple) and all(
                isinstance(element, ast.Constant) and isinstance(element.value, str)
                for element in value.elts)):
            raise UnknownConstruct("a joined pattern part that is not a tuple of strings: " + name)
        for element in value.elts:
            start, end = smap.start(element), smap.end(element)
            tail = re.compile(r", ?|,").match(source, end)
            add("pattern member removed", "in the constant {}, the member `{}` removed".format(
                name, element.value), [(start, tail.end() if tail else end, "")])

    counted = collections.Counter()
    sites = []
    for operator, words, mutated in raw:
        counted[words] += 1
        full = "{}, at its {} occurrence".format(words, ordinal(counted[words]))
        sites.append(as_site(source, mutated, full, operator))
    return sites

# The generated sites that have a row: the words of the site, then the cases that must fail
# once it is applied.
SWEEP_ROWS = {
    'in the constant WIDTH, `72` changed up to `73` in `WIDTH = 72`, at its 1st occurrence':
        (D + 'test_squash_line_over_72_characters_fails',),
    'in the constant WIDTH, `72` changed down to `71` in `WIDTH = 72`, at its 1st occurrence':
        (D + 'test_squash_line_of_72_characters_passes',),
    'in the constant MAX_DIGITS, `18` changed up to `19` in `MAX_DIGITS = 18`, at its 1st '
    'occurrence':
        (D + 'test_squash_name_of_19_digits_is_not_bound',),
    'in the constant MAX_DIGITS, `18` changed down to `17` in `MAX_DIGITS = 18`, at its 1st '
    'occurrence':
        (D + 'test_squash_name_of_18_digits_binds_the_subject',),
    'in the constant EXIT_DEFECT, `1` changed up to `2` in `EXIT_DEFECT = 1`, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in the constant EXIT_DEFECT, `1` changed down to `0` in `EXIT_DEFECT = 1`, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in the constant EXIT_UNREADABLE, `2` changed up to `3` in `EXIT_UNREADABLE = 2`, at its '
    '1st occurrence':
        (U + 'test_body_that_is_a_number_exits_2',),
    'in the constant EXIT_UNREADABLE, `2` changed down to `1` in `EXIT_UNREADABLE = 2`, at its '
    '1st occurrence':
        (U + 'test_body_that_is_a_number_exits_2',),
    'in the constant EXIT_USAGE, `2` changed up to `3` in `EXIT_USAGE = 2`, at its 1st '
    'occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in the constant EXIT_USAGE, `2` changed down to `1` in `EXIT_USAGE = 2`, at its 1st '
    'occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in ascii_text(), the statement `out = []` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in ascii_text(), the statement `for char in text:` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in ascii_text(), the statement `code = ord(char)` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in ascii_text(), the statement `if 0x20 <= code < 0x7f:` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in ascii_text(), the statement `out.append(char)` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in ascii_text(), the statement `elif code < 0x100:` deleted, at its 1st occurrence':
        (O + 'test_carriage_return_and_del_are_escaped',),
    'in ascii_text(), the statement `out.append("\\\\x{:02x}".format(code))` deleted, at its '
    '1st occurrence':
        (O + 'test_carriage_return_and_del_are_escaped',),
    'in ascii_text(), the statement `elif code < 0x10000:` deleted, at its 1st occurrence':
        (O + 'test_carriage_return_and_del_are_escaped',),
    'in ascii_text(), the statement `out.append("\\\\u{:04x}".format(code))` deleted, at its '
    '1st occurrence':
        (O + 'test_carriage_return_and_del_are_escaped',),
    'in ascii_text(), the statement `out.append("\\\\U{:08x}".format(code))` deleted, at its '
    '1st occurrence':
        (O + 'test_reported_line_escapes_each_range_edge',),
    'in ascii_text(), the statement `return "".join(out)` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in ascii_text(), `<=` changed to `<` in `0x20 <= code < 0x7f`, at its 1st occurrence':
        (O + 'test_reported_line_escapes_each_range_edge',),
    'in ascii_text(), `<` changed to `<=` in `0x20 <= code < 0x7f`, at its 1st occurrence':
        (O + 'test_carriage_return_and_del_are_escaped',),
    'in ascii_text(), `0x20` changed up to `0x21` in `if 0x20 <= code < 0x7f:`, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in ascii_text(), `0x20` changed down to `0x1f` in `if 0x20 <= code < 0x7f:`, at its 1st '
    'occurrence':
        (O + 'test_reported_line_escapes_each_range_edge',),
    'in ascii_text(), `0x7f` changed up to `0x80` in `if 0x20 <= code < 0x7f:`, at its 1st '
    'occurrence':
        (O + 'test_carriage_return_and_del_are_escaped',),
    'in ascii_text(), `0x7f` changed down to `0x7e` in `if 0x20 <= code < 0x7f:`, at its 1st '
    'occurrence':
        (O + 'test_reported_line_escapes_each_range_edge',),
    'in ascii_text(), `<` changed to `<=` in `code < 0x100`, at its 1st occurrence':
        (O + 'test_reported_line_escapes_each_range_edge',),
    'in ascii_text(), `0x100` changed up to `0x101` in `elif code < 0x100:`, at its 1st '
    'occurrence':
        (O + 'test_reported_line_escapes_each_range_edge',),
    'in ascii_text(), `0x100` changed down to `0xff` in `elif code < 0x100:`, at its 1st '
    'occurrence':
        (O + 'test_reported_line_escapes_each_range_edge',),
    'in ascii_text(), `<` changed to `<=` in `code < 0x10000`, at its 1st occurrence':
        (O + 'test_reported_line_escapes_each_range_edge',),
    'in ascii_text(), `0x10000` changed up to `0x10001` in `elif code < 0x10000:`, at its 1st '
    'occurrence':
        (O + 'test_reported_line_escapes_each_range_edge',),
    'in ascii_text(), `0x10000` changed down to `0xffff` in `elif code < 0x10000:`, at its 1st '
    'occurrence':
        (O + 'test_reported_line_escapes_each_range_edge',),
    'in emit(), the statement `print(prefix + ascii_text(detail))` deleted, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in Report.__init__(), the statement `self.count = 0` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in Report.__init__(), `0` changed up to `1` in `self.count = 0`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in Report.__init__(), `0` changed down to `-1` in `self.count = 0`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in Report.defect(), the statement `self.count += 1` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in Report.defect(), the statement `emit(prefix, detail)` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in Report.defect(), `1` changed up to `2` in `self.count += 1`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in Report.defect(), `1` changed down to `0` in `self.count += 1`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in Report.note(), the statement `emit(prefix, detail)` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in read_utf8(), the statement `try:` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in read_utf8(), the statement `data = Path(path).read_bytes()` deleted, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in read_utf8(), the statement `raise Unreadable("{} {}: {}".format(what, path, '
    'error.strerror or error)) from error` deleted, at its 1st occurrence':
        (U + 'test_folder_given_as_text_file_exits_2',),
    'in read_utf8(), the statement `try:` deleted, at its 2nd occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in read_utf8(), the statement `text = data.decode("utf-8", "strict")` deleted, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in read_utf8(), the statement `raise Unreadable("{} {}: not UTF-8: {}".format(what, path, '
    'error)) from error` deleted, at its 1st occurrence':
        (U + 'test_undecodable_squash_file_exits_2',),
    'in read_utf8(), the statement `return text.replace("\\r\\n", "\\n")` deleted, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in read_utf8(), the body of `except OSError as error:` replaced by `raise`, at its 1st '
    'occurrence':
        (U + 'test_folder_given_as_text_file_exits_2',),
    'in read_utf8(), the body of `except UnicodeDecodeError as error:` replaced by `raise`, at '
    'its 1st occurrence':
        (U + 'test_undecodable_squash_file_exits_2',),
    'in read_utf8(), `or` changed to `and` before `error`, at its 1st occurrence':
        (U + 'test_unreadable_line_names_its_input',),
    'in read_event(), the statement `text = read_utf8(path, "event payload")` deleted, at its '
    '1st occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in read_event(), the statement `try:` deleted, at its 1st occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in read_event(), the statement `event = json.loads(text)` deleted, at its 1st occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in read_event(), the statement `raise Unreadable("event payload {}: not JSON: '
    '{}".format(path, error)) from error` deleted, at its 1st occurrence':
        (U + 'test_deeply_nested_payload_exits_2',),
    'in read_event(), the statement `pull = event.get("pull_request") if isinstance(event, '
    'dict) else None` deleted, at its 1st occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in read_event(), the statement `if not isinstance(pull, dict):` deleted, at its 1st '
    'occurrence':
        (U + 'test_other_event_type_exits_2',),
    'in read_event(), the statement `raise Unreadable("event payload {}: not a pull request '
    'event".format(path))` deleted, at its 1st occurrence':
        (U + 'test_other_event_type_exits_2',),
    'in read_event(), the statement `number = pull.get("number")` deleted, at its 1st occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in read_event(), the statement `if type(number) is not int or number < 1:` deleted, at its '
    '1st occurrence':
        (U + 'test_payload_number_below_1_exits_2',),
    'in read_event(), the statement `raise Unreadable("event payload {}: no positive integer '
    'pull request number".format(path))` deleted, at its 1st occurrence':
        (U + 'test_payload_number_below_1_exits_2',),
    'in read_event(), the statement `body = pull.get("body")` deleted, at its 1st occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in read_event(), the statement `if body is None:` deleted, at its 1st occurrence':
        (D + 'test_null_body_fails',),
    'in read_event(), the statement `body = ""` deleted, at its 1st occurrence':
        (D + 'test_null_body_fails',),
    'in read_event(), the statement `if not isinstance(body, str):` deleted, at its 1st '
    'occurrence':
        (U + 'test_body_that_is_a_number_exits_2',),
    'in read_event(), the statement `raise Unreadable("event payload {}: the pull request body '
    'is not text".format(path))` deleted, at its 1st occurrence':
        (U + 'test_body_that_is_a_number_exits_2',),
    'in read_event(), the statement `return number, body.replace("\\r\\n", "\\n")` deleted, at '
    'its 1st occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in read_event(), `ValueError` removed from `except (ValueError, RecursionError) as '
    'error:`, at its 1st occurrence':
        (U + 'test_unparseable_payload_exits_2',),
    'in read_event(), `RecursionError` removed from `except (ValueError, RecursionError) as '
    'error:`, at its 1st occurrence':
        (U + 'test_deeply_nested_payload_exits_2',),
    'in read_event(), the body of `except (ValueError, RecursionError) as error:` replaced by '
    '`raise`, at its 1st occurrence':
        (U + 'test_deeply_nested_payload_exits_2',),
    'in read_event(), `not` removed from `not isinstance(pull, dict)`, at its 1st occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in read_event(), `or` changed to `and` before `number < 1`, at its 1st occurrence':
        (U + 'test_payload_number_below_1_exits_2',),
    'in read_event(), `is` changed to `is not` in `body is None`, at its 1st occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in read_event(), `not` removed from `not isinstance(body, str)`, at its 1st occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in read_event(), `is not` changed to `is` in `type(number) is not int`, at its 1st '
    'occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in read_event(), `<` changed to `<=` in `number < 1`, at its 1st occurrence':
        (D + 'test_payload_number_1_is_read',),
    'in read_event(), `1` changed up to `2` in `if type(number) is not int or number < 1:`, at '
    'its 1st occurrence':
        (D + 'test_payload_number_1_is_read',),
    'in read_event(), `1` changed down to `0` in `if type(number) is not int or number < 1:`, '
    'at its 1st occurrence':
        (U + 'test_payload_number_below_1_exits_2',),
    'in describe(), the statement `try:` deleted, at its 1st occurrence':
        (U + 'test_error_whose_message_exits_exits_2',),
    'in describe(), the statement `name = str.__str__(str(type(error).__name__))` deleted, at '
    'its 1st occurrence':
        (U + 'test_error_whose_message_exits_exits_2',),
    'in describe(), the statement `name = "an exception"` deleted, at its 1st occurrence':
        (U + 'test_error_whose_type_name_cannot_be_formatted_exits_2',),
    'in describe(), the statement `try:` deleted, at its 2nd occurrence':
        (U + 'test_error_whose_message_exits_exits_2',),
    'in describe(), the statement `text = str.__str__(str(error))` deleted, at its 1st '
    'occurrence':
        (U + 'test_error_whose_message_exits_exits_2',),
    'in describe(), the statement `return name + " (its message cannot be formatted)"` deleted, '
    'at its 1st occurrence':
        (U + 'test_error_whose_message_exits_exits_2',),
    'in describe(), the statement `return name + ": " + text` deleted, at its 1st occurrence':
        (U + 'test_error_whose_type_name_cannot_be_formatted_exits_2',),
    'in describe(), `BaseException` changed to `Exception` in `except BaseException:`, at its '
    '1st occurrence':
        (U + 'test_error_whose_type_name_cannot_be_formatted_exits_2',),
    'in describe(), the body of `except BaseException:` replaced by `raise`, at its 1st '
    'occurrence':
        (U + 'test_error_whose_type_name_cannot_be_formatted_exits_2',),
    'in describe(), `BaseException` changed to `Exception` in `except BaseException:`, at its '
    '2nd occurrence':
        (U + 'test_error_whose_message_exits_exits_2',),
    'in describe(), the body of `except BaseException:` replaced by `raise`, at its 2nd '
    'occurrence':
        (U + 'test_error_whose_message_exits_exits_2',),
    'in load_scan(), the statement `sys.dont_write_bytecode = True` deleted, at its 1st '
    'occurrence':
        (O + 'test_gate_run_without_dash_b_writes_no_bytecode',),
    'in load_scan(), the statement `try:` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in load_scan(), the statement `spec = '
    'importlib.util.spec_from_file_location("pr_text_label_lint", LINT)` deleted, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in load_scan(), the statement `module = importlib.util.module_from_spec(spec)` deleted, at '
    'its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in load_scan(), the statement `spec.loader.exec_module(module)` deleted, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in load_scan(), the statement `scan = module.scan` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in load_scan(), the statement `raise Unreadable(LINT_FAILURE.format(LINT, '
    'describe(error))) from error` deleted, at its 1st occurrence':
        (U + 'test_error_whose_message_exits_exits_2',),
    'in load_scan(), the statement `return scan` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in load_scan(), `True` changed to `False` in `sys.dont_write_bytecode = True`, at its 1st '
    'occurrence':
        (O + 'test_gate_run_without_dash_b_writes_no_bytecode',),
    'in load_scan(), `BaseException` changed to `Exception` in `except BaseException as '
    'error:`, at its 1st occurrence':
        (U + 'test_lint_that_exits_on_load_exits_2',),
    'in load_scan(), the body of `except BaseException as error:` replaced by `raise`, at its '
    '1st occurrence':
        (U + 'test_error_whose_message_exits_exits_2',),
    'in blank(), the statement `return not INVISIBLE.sub("", COMMENT.sub("", text))` deleted, '
    'at its 1st occurrence':
        (D + 'test_blank_description_fails',),
    'in blank(), `not` removed from `not INVISIBLE.sub("", COMMENT.sub("", text))`, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), the statement `inside = set()` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), the statement `opener = None` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), the statement `for index, line in enumerate(lines):` deleted, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), the statement `match = FENCE.match(line)` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), the statement `if opener is None:` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), the statement `if match:` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), the statement `opener = match.group(1)` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), the statement `start = index` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), the statement `inside.add(index)` deleted, at its 1st occurrence':
        (E + 'test_dash_on_closed_fence_opener_line_passes',),
    'in fenced(), the statement `continue` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), the statement `inside.add(index)` deleted, at its 2nd occurrence':
        (D + 'test_unclosed_fence_in_description_fails',),
    'in fenced(), the statement `if (match and match.group(1)[0] == opener[0] and '
    'len(match.group(1)) >= len(opener)` deleted, at its 1st occurrence':
        (E + 'test_closed_fence_then_clean_prose_passes',),
    'in fenced(), the statement `opener = None` deleted, at its 2nd occurrence':
        (E + 'test_closed_fence_then_clean_prose_passes',),
    'in fenced(), the statement `return inside, (start if opener is not None else None)` '
    'deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), `match` changed to `fullmatch` in `match = FENCE.match(line)`, at its 1st '
    'occurrence':
        (E + 'test_closer_followed_by_a_tab_or_a_space_closes_fence',),
    'in fenced(), `match` changed to `search` in `match = FENCE.match(line)`, at its 1st '
    'occurrence':
        (E + 'test_backtick_run_inside_a_line_is_not_a_fence',),
    'in fenced(), `is` changed to `is not` in `opener is None`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), `and` changed to `or` before `match.group(1)[0] == opener[0]`, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), `and` changed to `or` before `len(match.group(1)) >= len(opener)`, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), `and` changed to `or` before `not line[match.end():].strip(" \\t")`, at its '
    '1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), `==` changed to `!=` in `match.group(1)[0] == opener[0]`, at its 1st '
    'occurrence':
        (E + 'test_closed_fence_then_clean_prose_passes',),
    'in fenced(), `>=` changed to `>` in `len(match.group(1)) >= len(opener)`, at its 1st '
    'occurrence':
        (E + 'test_closed_fence_then_clean_prose_passes',),
    'in fenced(), `not` removed from `not line[match.end():].strip(" \\t")`, at its 1st '
    'occurrence':
        (E + 'test_closed_fence_then_clean_prose_passes',),
    'in fenced(), `is not` changed to `is` in `opener is not None`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), `1` changed up to `2` in `opener = match.group(1)`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in fenced(), `1` changed down to `0` in `opener = match.group(1)`, at its 1st occurrence':
        (E + 'test_fence_indented_1_to_3_spaces_masks_its_lines',),
    'in fenced(), `1` changed up to `2` in `if (match and match.group(1)[0] == opener[0] and '
    'len(match.group(1)) >= len(opener)`, at its 1st occurrence':
        (E + 'test_closed_fence_then_clean_prose_passes',),
    'in fenced(), `1` changed down to `0` in `if (match and match.group(1)[0] == opener[0] and '
    'len(match.group(1)) >= len(opener)`, at its 1st occurrence':
        (E + 'test_fence_indented_1_to_3_spaces_masks_its_lines',),
    'in fenced(), `1` changed up to `2` in `if (match and match.group(1)[0] == opener[0] and '
    'len(match.group(1)) >= len(opener)`, at its 2nd occurrence':
        (E + 'test_closed_fence_then_clean_prose_passes',),
    'in fenced(), `1` changed down to `0` in `if (match and match.group(1)[0] == opener[0] and '
    'len(match.group(1)) >= len(opener)`, at its 2nd occurrence':
        (E + 'test_indented_shorter_closer_leaves_fence_open',),
    'in code_spans(), the statement `runs = [match.span() for match in '
    'BACKTICKS.finditer(line)]` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in code_spans(), the statement `closer = [None] * len(runs)` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in code_spans(), the statement `later = {}` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in code_spans(), the statement `for index in range(len(runs) - 1, -1, -1):` deleted, at '
    'its 1st occurrence':
        (E + 'test_label_in_backticks_passes',),
    'in code_spans(), the statement `width = runs[index][1] - runs[index][0]` deleted, at its '
    '1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in code_spans(), the statement `closer[index] = later.get(width)` deleted, at its 1st '
    'occurrence':
        (E + 'test_label_in_backticks_passes',),
    'in code_spans(), the statement `later[width] = index` deleted, at its 1st occurrence':
        (E + 'test_label_in_backticks_passes',),
    'in code_spans(), the statement `spans = []` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in code_spans(), the statement `index = 0` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in code_spans(), the statement `while index < len(runs):` deleted, at its 1st occurrence':
        (E + 'test_label_in_backticks_passes',),
    'in code_spans(), the statement `if closer[index] is None:` deleted, at its 1st occurrence':
        (O + 'test_code_span_scan_ends_on_each_run_shape',),
    'in code_spans(), the statement `index += 1` deleted, at its 1st occurrence':
        (O + 'test_code_span_scan_ends_on_each_run_shape',),
    'in code_spans(), the statement `spans.append((runs[index][0], runs[closer[index]][1]))` '
    'deleted, at its 1st occurrence':
        (E + 'test_label_in_backticks_passes',),
    'in code_spans(), the statement `index = closer[index] + 1` deleted, at its 1st occurrence':
        (O + 'test_code_span_scan_ends_on_each_run_shape',),
    'in code_spans(), the statement `return spans` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in code_spans(), `0` changed up to `1` in `index = 0`, at its 1st occurrence':
        (E + 'test_label_in_backticks_passes',),
    'in code_spans(), `0` changed down to `-1` in `index = 0`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in code_spans(), `<` changed to `<=` in `index < len(runs)`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in code_spans(), `is` changed to `is not` in `closer[index] is None`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in code_spans(), `1` changed up to `2` in `for index in range(len(runs) - 1, -1, -1):`, at '
    'its 1st occurrence':
        (E + 'test_label_in_backticks_passes',),
    'in code_spans(), `1` changed down to `0` in `for index in range(len(runs) - 1, -1, -1):`, '
    'at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in code_spans(), `1` changed up to `2` in `for index in range(len(runs) - 1, -1, -1):`, at '
    'its 2nd occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in code_spans(), `1` changed down to `0` in `for index in range(len(runs) - 1, -1, -1):`, '
    'at its 2nd occurrence':
        (E + 'test_label_in_backticks_passes',),
    'in code_spans(), `1` changed up to `2` in `for index in range(len(runs) - 1, -1, -1):`, at '
    'its 3rd occurrence':
        (E + 'test_label_in_backticks_passes',),
    'in code_spans(), `1` changed down to `0` in `for index in range(len(runs) - 1, -1, -1):`, '
    'at its 3rd occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in code_spans(), `1` changed up to `2` in `index += 1`, at its 1st occurrence':
        (E + 'test_span_after_a_lone_backtick_is_masked',),
    'in code_spans(), `1` changed down to `0` in `index += 1`, at its 1st occurrence':
        (O + 'test_code_span_scan_ends_on_each_run_shape',),
    'in code_spans(), `1` changed up to `2` in `width = runs[index][1] - runs[index][0]`, at '
    'its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in code_spans(), `1` changed down to `0` in `width = runs[index][1] - runs[index][0]`, at '
    'its 1st occurrence':
        (D + 'test_dash_after_lone_backtick_and_double_span_fails',),
    'in code_spans(), `0` changed up to `1` in `width = runs[index][1] - runs[index][0]`, at '
    'its 1st occurrence':
        (D + 'test_dash_after_lone_backtick_and_double_span_fails',),
    'in code_spans(), `0` changed down to `-1` in `width = runs[index][1] - runs[index][0]`, at '
    'its 1st occurrence':
        (D + 'test_dash_after_lone_backtick_and_double_span_fails',),
    'in code_spans(), `1` changed up to `2` in `index = closer[index] + 1`, at its 1st '
    'occurrence':
        (E + 'test_span_right_after_another_span_is_masked',),
    'in code_spans(), `1` changed down to `0` in `index = closer[index] + 1`, at its 1st '
    'occurrence':
        (E + 'test_span_closes_on_the_nearest_run_of_its_length',),
    'in code_spans(), `0` changed up to `1` in `spans.append((runs[index][0], '
    'runs[closer[index]][1]))`, at its 1st occurrence':
        (E + 'test_masked_span_reads_as_spaces',),
    'in code_spans(), `0` changed down to `-1` in `spans.append((runs[index][0], '
    'runs[closer[index]][1]))`, at its 1st occurrence':
        (E + 'test_masked_span_reads_as_spaces',),
    'in code_spans(), `1` changed up to `2` in `spans.append((runs[index][0], '
    'runs[closer[index]][1]))`, at its 1st occurrence':
        (D + 'test_dash_after_lone_backtick_and_double_span_fails',),
    'in code_spans(), `1` changed down to `0` in `spans.append((runs[index][0], '
    'runs[closer[index]][1]))`, at its 1st occurrence':
        (E + 'test_masked_span_reads_as_spaces',),
    'in masked(), the statement `chars = list(line)` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in masked(), the statement `for start, end in spans:` deleted, at its 1st occurrence':
        (E + 'test_dash_inside_curly_quotes_passes',),
    'in masked(), the statement `chars[start:end] = MASK_CHAR * (end - start)` deleted, at its '
    '1st occurrence':
        (E + 'test_dash_inside_curly_quotes_passes',),
    'in masked(), the statement `return "".join(chars)` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in mask(), the statement `line = masked(line, code_spans(line))` deleted, at its 1st '
    'occurrence':
        (E + 'test_label_in_backticks_passes',),
    'in mask(), the statement `for pattern in MASKS:` deleted, at its 1st occurrence':
        (E + 'test_dash_inside_curly_quotes_passes',),
    'in mask(), the statement `line = masked(line, [match.span() for match in '
    'pattern.finditer(line)])` deleted, at its 1st occurrence':
        (E + 'test_dash_inside_curly_quotes_passes',),
    'in mask(), the statement `return line` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in excess_is_url(), the statement `return any(match.start() <= WIDTH and match.end() >= '
    'len(line)` deleted, at its 1st occurrence':
        (E + 'test_long_url_line_passes',),
    'in excess_is_url(), `any` changed to `all`, at its 1st occurrence':
        (D + 'test_squash_line_over_72_characters_fails',),
    'in excess_is_url(), `and` changed to `or` before `match.end() >= len(line)`, at its 1st '
    'occurrence':
        (E + 'test_curly_quoted_url_ending_a_long_squash_line_fails',),
    'in excess_is_url(), `<=` changed to `<` in `match.start() <= WIDTH`, at its 1st occurrence':
        (E + 'test_url_starting_at_character_73_passes',),
    'in excess_is_url(), `>=` changed to `>` in `match.end() >= len(line)`, at its 1st '
    'occurrence':
        (E + 'test_long_url_line_passes',),
    'in check_text(), the statement `if blank(text):` deleted, at its 1st occurrence':
        (D + 'test_blank_description_fails',),
    'in check_text(), the statement `report.defect(prefix, ": the text is empty")` deleted, at '
    'its 1st occurrence':
        (D + 'test_blank_description_fails',),
    'in check_text(), the statement `return` deleted, at its 1st occurrence':
        (D + 'test_blank_text_reports_only_that_it_is_empty',),
    'in check_text(), the statement `lines = text.split("\\n")` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), the statement `fence, unclosed = fenced(lines)` deleted, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), the statement `if unclosed is not None:` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), the statement `report.defect(prefix, ":{0}: the code fence opened on line '
    '{0} is never closed".format(` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), the statement `prose = ["" if index in fence else mask(line) for index, '
    'line in enumerate(lines)]` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), the statement `rel = prefix + ".md"` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), the statement `hits = scan(rel, "\\n".join(prose))` deleted, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), the statement `for hit in hits:` deleted, at its 1st occurrence':
        (D + 'test_fix_label_in_description_fails',),
    'in check_text(), the statement `report.defect(prefix, hit[len(rel):])` deleted, at its 1st '
    'occurrence':
        (D + 'test_fix_label_in_description_fails',),
    'in check_text(), the statement `for number, line in enumerate(prose, 1):` deleted, at its '
    '1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), the statement `for name, dash in DASHES:` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), the statement `if dash in line:` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), the statement `report.defect(prefix, ":{}: {}: {}".format(number, name, '
    'line.strip()))` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), the statement `for match in ISE.finditer(line):` deleted, at its 1st '
    'occurrence':
        (D + 'test_each_ise_ending_fails',),
    'in check_text(), the statement `report.defect(prefix, ":{}: an -ise spelling: '
    '{}".format(number, match.group(0)))` deleted, at its 1st occurrence':
        (D + 'test_each_ise_ending_fails',),
    'in check_text(), the statement `width_applies = squash` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), the statement `revision_applies = squash` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), the statement `if width_applies:` deleted, at its 1st occurrence':
        (D + 'test_squash_line_over_72_characters_fails',),
    'in check_text(), the statement `for number, line in enumerate(lines, 1):` deleted, at its '
    '1st occurrence':
        (D + 'test_squash_line_over_72_characters_fails',),
    'in check_text(), the statement `exempt = number - 1 in fence or excess_is_url(line)` '
    'deleted, at its 1st occurrence':
        (D + 'test_squash_line_over_72_characters_fails',),
    'in check_text(), the statement `if len(line) > WIDTH and not exempt:` deleted, at its 1st '
    'occurrence':
        (D + 'test_squash_line_over_72_characters_fails',),
    'in check_text(), the statement `report.defect(prefix, ":{}: {} characters, over {}: '
    '{}".format(` deleted, at its 1st occurrence':
        (D + 'test_squash_line_over_72_characters_fails',),
    'in check_text(), the statement `if revision_applies:` deleted, at its 1st occurrence':
        (D + 'test_full_revision_id_in_squash_message_fails',),
    'in check_text(), the statement `for number, raw in enumerate(lines, 1):` deleted, at its '
    '1st occurrence':
        (D + 'test_full_revision_id_in_squash_message_fails',),
    'in check_text(), the statement `for match in REVISION.finditer(raw):` deleted, at its 1st '
    'occurrence':
        (D + 'test_full_revision_id_in_squash_message_fails',),
    'in check_text(), the statement `report.defect(prefix, ":{}: a revision id: '
    '{}".format(number, match.group(0)))` deleted, at its 1st occurrence':
        (D + 'test_full_revision_id_in_squash_message_fails',),
    'in check_text(), `is not` changed to `is` in `unclosed is not None`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), `1` changed up to `2` in `for number, line in enumerate(prose, 1):`, at '
    'its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), `1` changed down to `0` in `for number, line in enumerate(prose, 1):`, at '
    'its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), `in` changed to `not in` in `index in fence`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), `in` changed to `not in` in `dash in line`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), `1` changed up to `2` in `for number, line in enumerate(lines, 1):`, at '
    'its 1st occurrence':
        (D + 'test_squash_line_over_72_characters_fails',),
    'in check_text(), `1` changed down to `0` in `for number, line in enumerate(lines, 1):`, at '
    'its 1st occurrence':
        (D + 'test_squash_line_over_72_characters_fails',),
    'in check_text(), `or` changed to `and` before `excess_is_url(line)`, at its 1st occurrence':
        (E + 'test_label_and_width_inside_fence_pass',),
    'in check_text(), `and` changed to `or` before `not exempt`, at its 1st occurrence':
        (D + 'test_binding_not_checked_line_is_not_a_defect',),
    'in check_text(), `1` changed up to `2` in `for number, raw in enumerate(lines, 1):`, at '
    'its 1st occurrence':
        (D + 'test_revision_id_in_squash_message_fails',),
    'in check_text(), `1` changed down to `0` in `for number, raw in enumerate(lines, 1):`, at '
    'its 1st occurrence':
        (D + 'test_revision_id_in_squash_message_fails',),
    'in check_text(), `in` changed to `not in` in `number - 1 in fence`, at its 1st occurrence':
        (D + 'test_squash_line_over_72_characters_fails',),
    'in check_text(), `>` changed to `>=` in `len(line) > WIDTH`, at its 1st occurrence':
        (D + 'test_squash_line_of_72_characters_passes',),
    'in check_text(), `not` removed from `not exempt`, at its 1st occurrence':
        (D + 'test_squash_line_over_72_characters_fails',),
    'in check_text(), `1` changed up to `2` in `unclosed + 1))`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), `1` changed down to `0` in `unclosed + 1))`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in check_text(), `0` changed up to `1` in `report.defect(prefix, ":{}: an -ise spelling: '
    '{}".format(number, match.group(0)))`, at its 1st occurrence':
        (D + 'test_each_ise_ending_fails',),
    'in check_text(), `0` changed down to `-1` in `report.defect(prefix, ":{}: an -ise '
    'spelling: {}".format(number, match.group(0)))`, at its 1st occurrence':
        (D + 'test_each_ise_ending_fails',),
    'in check_text(), `1` changed up to `2` in `exempt = number - 1 in fence or '
    'excess_is_url(line)`, at its 1st occurrence':
        (E + 'test_long_line_next_to_a_fence_fails',),
    'in check_text(), `1` changed down to `0` in `exempt = number - 1 in fence or '
    'excess_is_url(line)`, at its 1st occurrence':
        (E + 'test_long_line_next_to_a_fence_fails',),
    'in check_text(), `0` changed up to `1` in `report.defect(prefix, ":{}: a revision id: '
    '{}".format(number, match.group(0)))`, at its 1st occurrence':
        (D + 'test_full_revision_id_in_squash_message_fails',),
    'in check_text(), `0` changed down to `-1` in `report.defect(prefix, ":{}: a revision id: '
    '{}".format(number, match.group(0)))`, at its 1st occurrence':
        (D + 'test_full_revision_id_in_squash_message_fails',),
    'in check_squash(), the statement `check_text(report, "squash", text, True, scan)` deleted, '
    'at its 1st occurrence':
        (D + 'test_em_dash_in_squash_message_fails',),
    'in check_squash(), the statement `if blank(text):` deleted, at its 1st occurrence':
        (D + 'test_empty_squash_file_fails',),
    'in check_squash(), the statement `return` deleted, at its 1st occurrence':
        (D + 'test_empty_squash_file_fails',),
    'in check_squash(), the statement `if number is None:` deleted, at its 1st occurrence':
        (D + 'test_binding_not_checked_line_is_not_a_defect',),
    'in check_squash(), the statement `report.note("pr-text:", " subject binding not checked")` '
    'deleted, at its 1st occurrence':
        (D + 'test_binding_not_checked_line_is_not_a_defect',),
    'in check_squash(), the statement `return` deleted, at its 2nd occurrence':
        (D + 'test_binding_not_checked_line_is_not_a_defect',),
    'in check_squash(), the statement `subject = text.split("\\n", 1)[0]` deleted, at its 1st '
    'occurrence':
        (D + 'test_em_dash_in_squash_message_fails',),
    'in check_squash(), the statement `suffix = " (#{})".format(number)` deleted, at its 1st '
    'occurrence':
        (D + 'test_em_dash_in_squash_message_fails',),
    'in check_squash(), the statement `if not subject.endswith(suffix):` deleted, at its 1st '
    'occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in check_squash(), the statement `report.defect("squash", \':1: the subject does not end '
    'with "{}": {}\'.format(` deleted, at its 1st occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in check_squash(), `is` changed to `is not` in `number is None`, at its 1st occurrence':
        (D + 'test_binding_not_checked_line_is_not_a_defect',),
    'in check_squash(), `not` removed from `not subject.endswith(suffix)`, at its 1st occurrence':
        (D + 'test_em_dash_in_squash_message_fails',),
    'in check_squash(), `True` changed to `False` in `check_text(report, "squash", text, True, '
    'scan)`, at its 1st occurrence':
        (D + 'test_full_revision_id_in_squash_message_fails',),
    'in check_squash(), `0` changed up to `1` in `subject = text.split("\\n", 1)[0]`, at its '
    '1st occurrence':
        (D + 'test_em_dash_in_squash_message_fails',),
    'in check_squash(), `0` changed down to `-1` in `subject = text.split("\\n", 1)[0]`, at its '
    '1st occurrence':
        (D + 'test_em_dash_in_squash_message_fails',),
    'in check_squash(), `1` changed down to `0` in `subject = text.split("\\n", 1)[0]`, at its '
    '1st occurrence':
        (D + 'test_em_dash_in_squash_message_fails',),
    'in bounded_number(), the statement `if len(digits) > MAX_DIGITS:` deleted, at its 1st '
    'occurrence':
        (D + 'test_squash_name_of_19_digits_is_not_bound',),
    'in bounded_number(), the statement `return None` deleted, at its 1st occurrence':
        (D + 'test_squash_name_of_19_digits_is_not_bound',),
    'in bounded_number(), the statement `return int(digits)` deleted, at its 1st occurrence':
        (D + 'test_em_dash_in_squash_message_fails',),
    'in bounded_number(), `>` changed to `>=` in `len(digits) > MAX_DIGITS`, at its 1st '
    'occurrence':
        (D + 'test_squash_name_of_18_digits_binds_the_subject',),
    'in number_from_name(), the statement `try:` deleted, at its 1st occurrence':
        (D + 'test_binding_not_checked_line_is_not_a_defect',),
    'in number_from_name(), the statement `parts = Path(path).absolute().parts` deleted, at its '
    '1st occurrence':
        (D + 'test_binding_not_checked_line_is_not_a_defect',),
    'in number_from_name(), the statement `raise Unreadable("squash file {}: the working '
    'directory cannot be read: {}".format(` deleted, at its 1st occurrence':
        (U + 'test_removed_working_directory_exits_2',),
    'in number_from_name(), the statement `if parts[-3:-1] == (".github", "squash") and '
    'SQUASH_NAME.fullmatch(parts[-1]):` deleted, at its 1st occurrence':
        (D + 'test_number_comes_from_squash_file_name',),
    'in number_from_name(), the statement `return bounded_number(parts[-1][:-len(".txt")])` '
    'deleted, at its 1st occurrence':
        (D + 'test_number_comes_from_squash_file_name',),
    'in number_from_name(), the body of `except OSError as error:` replaced by `raise`, at its '
    '1st occurrence':
        (U + 'test_removed_working_directory_exits_2',),
    'in number_from_name(), `and` changed to `or` before `SQUASH_NAME.fullmatch(parts[-1])`, at '
    'its 1st occurrence':
        (D + 'test_number_name_outside_a_squash_folder_is_not_bound',),
    'in number_from_name(), `==` changed to `!=` in `parts[-3:-1] == (".github", "squash")`, at '
    'its 1st occurrence':
        (D + 'test_number_comes_from_squash_file_name',),
    'in number_from_name(), `fullmatch` changed to `match` in `if parts[-3:-1] == (".github", '
    '"squash") and SQUASH_NAME.fullmatch(parts[-1]):`, at its 1st occurrence':
        (D + 'test_squash_name_with_a_further_suffix_is_not_bound',),
    'in number_from_name(), `fullmatch` changed to `search` in `if parts[-3:-1] == (".github", '
    '"squash") and SQUASH_NAME.fullmatch(parts[-1]):`, at its 1st occurrence':
        (D + 'test_squash_names_with_a_leading_zero_are_not_bound',),
    'in number_from_name(), `or` changed to `and` before `error`, at its 1st occurrence':
        (U + 'test_removed_working_directory_exits_2',),
    'in number_from_name(), `1` changed up to `2` in `if parts[-3:-1] == (".github", "squash") '
    'and SQUASH_NAME.fullmatch(parts[-1]):`, at its 1st occurrence':
        (D + 'test_number_comes_from_squash_file_name',),
    'in number_from_name(), `1` changed down to `0` in `if parts[-3:-1] == (".github", '
    '"squash") and SQUASH_NAME.fullmatch(parts[-1]):`, at its 1st occurrence':
        (D + 'test_number_comes_from_squash_file_name',),
    'in number_from_name(), `3` changed up to `4` in `if parts[-3:-1] == (".github", "squash") '
    'and SQUASH_NAME.fullmatch(parts[-1]):`, at its 1st occurrence':
        (D + 'test_number_comes_from_squash_file_name',),
    'in number_from_name(), `3` changed down to `2` in `if parts[-3:-1] == (".github", '
    '"squash") and SQUASH_NAME.fullmatch(parts[-1]):`, at its 1st occurrence':
        (D + 'test_number_comes_from_squash_file_name',),
    'in number_from_name(), `1` changed up to `2` in `if parts[-3:-1] == (".github", "squash") '
    'and SQUASH_NAME.fullmatch(parts[-1]):`, at its 2nd occurrence':
        (D + 'test_number_comes_from_squash_file_name',),
    'in number_from_name(), `1` changed down to `0` in `if parts[-3:-1] == (".github", '
    '"squash") and SQUASH_NAME.fullmatch(parts[-1]):`, at its 2nd occurrence':
        (D + 'test_number_comes_from_squash_file_name',),
    'in number_from_name(), `1` changed up to `2` in `return '
    'bounded_number(parts[-1][:-len(".txt")])`, at its 1st occurrence':
        (D + 'test_number_comes_from_squash_file_name',),
    'in number_from_name(), `1` changed down to `0` in `return '
    'bounded_number(parts[-1][:-len(".txt")])`, at its 1st occurrence':
        (D + 'test_number_comes_from_squash_file_name',),
    'in parse(), the statement `if not argv:` deleted, at its 1st occurrence':
        (U + 'test_no_arguments_is_a_usage_error',),
    'in parse(), the statement `raise Usage("no mode given")` deleted, at its 1st occurrence':
        (U + 'test_no_arguments_is_a_usage_error',),
    'in parse(), the statement `options = {}` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), the statement `rest = list(argv)` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), the statement `while rest:` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), the statement `flag = rest.pop(0)` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), the statement `if flag not in ("--event", "--description", "--squash", '
    '"--number"):` deleted, at its 1st occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in parse(), the statement `raise Usage("unknown argument {}".format(flag))` deleted, at '
    'its 1st occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in parse(), the statement `if flag in options or not rest:` deleted, at its 1st occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in parse(), the statement `raise Usage("{} needs 1 value and is given once".format(flag))` '
    'deleted, at its 1st occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in parse(), the statement `options[flag] = rest.pop(0)` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), the statement `modes = [flag for flag in ("--event", "--description", '
    '"--squash") if flag in options]` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), the statement `if len(modes) != 1:` deleted, at its 1st occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in parse(), the statement `raise Usage("give exactly 1 of --event, --description and '
    '--squash")` deleted, at its 1st occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in parse(), the statement `number = None` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), the statement `if "--number" in options:` deleted, at its 1st occurrence':
        (D + 'test_number_option_binding_passes',),
    'in parse(), the statement `if modes[0] != "--squash":` deleted, at its 1st occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in parse(), the statement `raise Usage("--number applies to --squash only")` deleted, at '
    'its 1st occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in parse(), the statement `if not re.fullmatch(r"[1-9][0-9]*", options["--number"]):` '
    'deleted, at its 1st occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in parse(), the statement `raise Usage("--number takes a positive integer")` deleted, at '
    'its 1st occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in parse(), the statement `number = bounded_number(options["--number"])` deleted, at its '
    '1st occurrence':
        (D + 'test_em_dash_in_squash_message_fails',),
    'in parse(), the statement `if number is None:` deleted, at its 1st occurrence':
        (U + 'test_number_option_of_18_digits_binds_and_19_is_a_usage_error',),
    'in parse(), the statement `raise Usage("--number takes at most {} '
    'digits".format(MAX_DIGITS))` deleted, at its 1st occurrence':
        (U + 'test_number_option_of_18_digits_binds_and_19_is_a_usage_error',),
    'in parse(), the statement `return modes[0], options[modes[0]], number` deleted, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), `not` removed from `not argv`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), `!=` changed to `==` in `len(modes) != 1`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), `in` changed to `not in` in `"--number" in options`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), `not in` changed to `in` in `flag not in ("--event", "--description", '
    '"--squash", "--number")`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), `or` changed to `and` before `not rest`, at its 1st occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in parse(), `1` changed up to `2` in `if len(modes) != 1:`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), `1` changed down to `0` in `if len(modes) != 1:`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), `!=` changed to `==` in `modes[0] != "--squash"`, at its 1st occurrence':
        (D + 'test_em_dash_in_squash_message_fails',),
    'in parse(), `not` removed from `not re.fullmatch(r"[1-9][0-9]*", options["--number"])`, at '
    'its 1st occurrence':
        (D + 'test_em_dash_in_squash_message_fails',),
    'in parse(), `is` changed to `is not` in `number is None`, at its 1st occurrence':
        (D + 'test_em_dash_in_squash_message_fails',),
    'in parse(), `0` changed up to `1` in `flag = rest.pop(0)`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), `0` changed down to `-1` in `flag = rest.pop(0)`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), `in` changed to `not in` in `flag in options`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), `not` removed from `not rest`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), `0` changed up to `1` in `options[flag] = rest.pop(0)`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), `0` changed down to `-1` in `options[flag] = rest.pop(0)`, at its 1st '
    'occurrence':
        (D + 'test_em_dash_in_squash_message_fails',),
    'in parse(), `in` changed to `not in` in `flag in options`, at its 2nd occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), `fullmatch` changed to `match` in `if not re.fullmatch(r"[1-9][0-9]*", '
    'options["--number"]):`, at its 1st occurrence':
        (U + 'test_number_option_with_trailing_text_is_a_usage_error',),
    'in parse(), `fullmatch` changed to `search` in `if not re.fullmatch(r"[1-9][0-9]*", '
    'options["--number"]):`, at its 1st occurrence':
        (U + 'test_number_option_with_a_leading_zero_is_a_usage_error',),
    'in parse(), `0` changed up to `1` in `return modes[0], options[modes[0]], number`, at its '
    '1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in parse(), `0` changed up to `1` in `if modes[0] != "--squash":`, at its 1st occurrence':
        (D + 'test_em_dash_in_squash_message_fails',),
    'in parse(), `0` changed up to `1` in `return modes[0], options[modes[0]], number`, at its '
    '2nd occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in main(), the statement `report = Report()` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in main(), the statement `try:` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in main(), the statement `mode, path, given_number = parse(argv)` deleted, at its 1st '
    'occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in main(), the statement `scan = load_scan()` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in main(), the statement `if mode == "--event":` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in main(), the statement `number, body = read_event(path)` deleted, at its 1st occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in main(), the statement `check_text(report, "description", body, False, scan)` deleted, '
    'at its 1st occurrence':
        (D + 'test_null_body_fails',),
    'in main(), the statement `squash_path = SQUASH_DIR / "{}.txt".format(number)` deleted, at '
    'its 1st occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in main(), the statement `check_squash(report, read_utf8(squash_path, "squash file"), '
    'number, scan)` deleted, at its 1st occurrence':
        (D + 'test_event_squash_subject_with_wrong_number_fails',),
    'in main(), the statement `elif mode == "--description":` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in main(), the statement `check_text(report, "description", read_utf8(path, "description '
    'file"), False, scan)` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in main(), the statement `number = given_number if given_number is not None else '
    'number_from_name(path)` deleted, at its 1st occurrence':
        (D + 'test_binding_not_checked_line_is_not_a_defect',),
    'in main(), the statement `check_squash(report, read_utf8(path, "squash file"), number, '
    'scan)` deleted, at its 1st occurrence':
        (D + 'test_binding_not_checked_line_is_not_a_defect',),
    'in main(), the statement `status = EXIT_DEFECT if report.count else 0` deleted, at its 1st '
    'occurrence':
        (D + 'test_binding_not_checked_line_is_not_a_defect',),
    'in main(), the statement `report.note("pr-text:", " {}; {}".format(error, USAGE))` '
    'deleted, at its 1st occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in main(), the statement `status = EXIT_USAGE` deleted, at its 1st occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in main(), the statement `report.note("unreadable:", " {}".format(error))` deleted, at its '
    '1st occurrence':
        (U + 'test_body_that_is_a_number_exits_2',),
    'in main(), the statement `status = EXIT_UNREADABLE` deleted, at its 1st occurrence':
        (U + 'test_body_that_is_a_number_exits_2',),
    'in main(), the statement `report.note("unreadable:", " the gate stopped on an unexpected '
    'error: {}".format(` deleted, at its 1st occurrence':
        (U + 'test_error_whose_message_exits_exits_2',),
    'in main(), the statement `status = EXIT_UNREADABLE` deleted, at its 2nd occurrence':
        (U + 'test_error_whose_message_exits_exits_2',),
    'in main(), the statement `report.note("pr-text:", " {} defect(s)".format(report.count))` '
    'deleted, at its 1st occurrence':
        (D + 'test_em_dash_fails',),
    'in main(), the statement `return status` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in main(), the body of `except Usage as error:` replaced by `raise`, at its 1st occurrence':
        (U + 'test_bad_arguments_are_usage_errors',),
    'in main(), the body of `except Unreadable as error:` replaced by `raise`, at its 1st '
    'occurrence':
        (U + 'test_body_that_is_a_number_exits_2',),
    'in main(), `BaseException` changed to `Exception` in `except BaseException as error:`, at '
    'its 1st occurrence':
        (U + 'test_scan_that_exits_exits_2',),
    'in main(), the body of `except BaseException as error:` replaced by `raise`, at its 1st '
    'occurrence':
        (U + 'test_error_whose_message_exits_exits_2',),
    'in main(), `==` changed to `!=` in `mode == "--event"`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in main(), `==` changed to `!=` in `mode == "--description"`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in main(), `0` changed up to `1` in `status = EXIT_DEFECT if report.count else 0`, at its '
    '1st occurrence':
        (D + 'test_binding_not_checked_line_is_not_a_defect',),
    'in main(), `0` changed down to `-1` in `status = EXIT_DEFECT if report.count else 0`, at '
    'its 1st occurrence':
        (D + 'test_binding_not_checked_line_is_not_a_defect',),
    'in main(), `False` changed to `True` in `check_text(report, "description", body, False, '
    'scan)`, at its 1st occurrence':
        (O + 'test_event_description_has_no_width_or_revision_check',),
    'in main(), `False` changed to `True` in `check_text(report, "description", read_utf8(path, '
    '"description file"), False, scan)`, at its 1st occurrence':
        (E + 'test_long_description_paragraph_passes',),
    'in main(), `is not` changed to `is` in `given_number is not None`, at its 1st occurrence':
        (D + 'test_number_comes_from_squash_file_name',),
    'in the pattern FENCE, the quantifier `{0,3}` changed to `{1,3}`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in the pattern FENCE, the quantifier `{0,3}` changed to `{0,2}`, at its 1st occurrence':
        (E + 'test_fence_indented_1_to_3_spaces_masks_its_lines',),
    'in the pattern FENCE, the quantifier `{0,3}` changed to `{0,4}`, at its 1st occurrence':
        (E + 'test_fence_indented_4_spaces_is_not_a_fence',),
    'in the pattern FENCE, the quantifier `{3,}` changed to `{2,}`, at its 1st occurrence':
        (E + 'test_run_of_2_backticks_or_tildes_is_not_a_fence',),
    'in the pattern FENCE, the quantifier `{3,}` changed to `{4,}`, at its 1st occurrence':
        (D + 'test_unclosed_fence_in_description_fails',),
    'in the pattern FENCE, the negated class `[^`]` made plain, at its 1st occurrence':
        (E + 'test_closer_followed_by_a_tab_or_a_space_closes_fence',),
    'in the pattern FENCE, the quantifier `*` changed to `+`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in the pattern FENCE, the anchor `$` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in the pattern FENCE, the lookahead `(?=[^`]*$)` deleted, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in the pattern FENCE, the quantifier `{3,}` changed to `{2,}`, at its 2nd occurrence':
        (E + 'test_run_of_2_backticks_or_tildes_is_not_a_fence',),
    'in the pattern FENCE, the quantifier `{3,}` changed to `{4,}`, at its 2nd occurrence':
        (E + 'test_tilde_fence_masks_its_lines',),
    'in the pattern FENCE, the quantifier `{3,}` made lazy, at its 2nd occurrence':
        (E + 'test_tilde_fence_of_4_closes_only_on_4_or_more',),
    'in the pattern FENCE, the alternative ``{3,}(?=[^`]*$)` deleted, at its 1st occurrence':
        (E + 'test_label_and_width_inside_fence_pass',),
    'in the pattern FENCE, the alternative `~{3,}` deleted, at its 1st occurrence':
        (E + 'test_tilde_fence_masks_its_lines',),
    'in the pattern BACKTICKS, the quantifier `+` changed to `*`, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in the pattern BACKTICKS, the quantifier `+` made lazy, at its 1st occurrence':
        (D + 'test_dash_after_lone_backtick_and_double_span_fails',),
    'in the pattern URL, the anchor `\\b` deleted, at its 1st occurrence':
        (E + 'test_url_glued_after_a_letter_is_not_masked',),
    'in the pattern URL, the quantifier `?` changed to `nothing`, at its 1st occurrence':
        (E + 'test_word_inside_http_url_passes',),
    'in the pattern URL, the member `\\s` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 1st occurrence':
        (E + 'test_each_url_stopper_ends_the_url',),
    'in the pattern URL, the member `<` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 1st occurrence':
        (E + 'test_each_url_stopper_ends_the_url',),
    'in the pattern URL, the member `>` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 1st occurrence':
        (E + 'test_each_url_stopper_ends_the_url',),
    'in the pattern URL, the member `\\"` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 1st occurrence':
        (E + 'test_each_url_stopper_ends_the_url',),
    "in the pattern URL, the member `'` deleted from the class "
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 1st occurrence':
        (E + 'test_each_url_stopper_ends_the_url',),
    'in the pattern URL, the member ``` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 1st occurrence':
        (E + 'test_each_url_stopper_ends_the_url',),
    'in the pattern URL, the member `(` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 1st occurrence':
        (E + 'test_each_url_stopper_ends_the_url',),
    'in the pattern URL, the member `)` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 1st occurrence':
        (E + 'test_each_url_stopper_ends_the_url',),
    'in the pattern URL, the member `\\u2013` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 1st occurrence':
        (E + 'test_each_url_stopper_ends_the_url',),
    'in the pattern URL, the member `\\u2014` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 1st occurrence':
        (E + 'test_each_url_stopper_ends_the_url',),
    'in the pattern URL, the member `\\u201c` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 1st occurrence':
        (E + 'test_each_url_stopper_ends_the_url',),
    'in the pattern URL, the member `\\u201d` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 1st occurrence':
        (E + 'test_each_url_stopper_ends_the_url',),
    'in the pattern URL, the member `\\u2018` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 1st occurrence':
        (E + 'test_each_url_stopper_ends_the_url',),
    'in the pattern URL, the member `\\u2019` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 1st occurrence':
        (E + 'test_each_url_stopper_ends_the_url',),
    'in the pattern URL, the negated class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]` made plain, at its 1st '
    'occurrence':
        (E + 'test_ise_word_inside_url_passes',),
    'in the pattern URL, the escape of `\\(` removed, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in the pattern URL, the member `\\s` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 2nd occurrence':
        (E + 'test_each_url_stopper_ends_a_parenthesis_pair',),
    'in the pattern URL, the member `<` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 2nd occurrence':
        (E + 'test_each_url_stopper_ends_a_parenthesis_pair',),
    'in the pattern URL, the member `>` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 2nd occurrence':
        (E + 'test_each_url_stopper_ends_a_parenthesis_pair',),
    'in the pattern URL, the member `\\"` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 2nd occurrence':
        (E + 'test_each_url_stopper_ends_a_parenthesis_pair',),
    "in the pattern URL, the member `'` deleted from the class "
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 2nd occurrence':
        (E + 'test_each_url_stopper_ends_a_parenthesis_pair',),
    'in the pattern URL, the member ``` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 2nd occurrence':
        (E + 'test_each_url_stopper_ends_a_parenthesis_pair',),
    'in the pattern URL, the member `(` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 2nd occurrence':
        (E + 'test_each_url_stopper_ends_a_parenthesis_pair',),
    'in the pattern URL, the member `)` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 2nd occurrence':
        (E + 'test_each_url_stopper_ends_a_parenthesis_pair',),
    'in the pattern URL, the member `\\u2013` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 2nd occurrence':
        (E + 'test_each_url_stopper_ends_a_parenthesis_pair',),
    'in the pattern URL, the member `\\u2014` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 2nd occurrence':
        (E + 'test_each_url_stopper_ends_a_parenthesis_pair',),
    'in the pattern URL, the member `\\u201c` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 2nd occurrence':
        (E + 'test_each_url_stopper_ends_a_parenthesis_pair',),
    'in the pattern URL, the member `\\u201d` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 2nd occurrence':
        (E + 'test_each_url_stopper_ends_a_parenthesis_pair',),
    'in the pattern URL, the member `\\u2018` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 2nd occurrence':
        (E + 'test_each_url_stopper_ends_a_parenthesis_pair',),
    'in the pattern URL, the member `\\u2019` deleted from the class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]`, at its 2nd occurrence':
        (E + 'test_each_url_stopper_ends_a_parenthesis_pair',),
    'in the pattern URL, the negated class '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]` made plain, at its 2nd '
    'occurrence':
        (E + 'test_long_url_with_a_parenthesis_pair_passes',),
    'in the pattern URL, the quantifier `*` changed to `+`, at its 1st occurrence':
        (E + 'test_empty_parenthesis_pair_is_part_of_a_url',),
    'in the pattern URL, the escape of `\\)` removed, at its 1st occurrence':
        (D + 'test_backtick_in_fence_info_string_is_not_a_fence',),
    'in the pattern URL, the alternative '
    '`[^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]` deleted, at its 1st occurrence':
        (E + 'test_ise_word_inside_url_passes',),
    'in the pattern URL, the alternative '
    '`\\([^\\s<>\\"\'`()\\u2013\\u2014\\u201c\\u201d\\u2018\\u2019]*\\)` deleted, at its 1st '
    'occurrence':
        (E + 'test_long_url_with_a_parenthesis_pair_passes',),
    'in the pattern URL, the quantifier `*` changed to `+`, at its 2nd occurrence':
        (E + 'test_url_of_only_its_scheme_ending_a_long_line_passes',),
    'in the pattern URL, the quantifier `*` made lazy, at its 2nd occurrence':
        (E + 'test_ise_word_inside_url_passes',),
    'in the pattern URL, the member `.` deleted from the class `[.,;:!?]`, at its 1st occurrence':
        (E + 'test_url_ending_in_each_trailing_mark_past_72_characters_fails',),
    'in the pattern URL, the member `,` deleted from the class `[.,;:!?]`, at its 1st occurrence':
        (E + 'test_url_ending_in_each_trailing_mark_past_72_characters_fails',),
    'in the pattern URL, the member `;` deleted from the class `[.,;:!?]`, at its 1st occurrence':
        (E + 'test_url_ending_in_each_trailing_mark_past_72_characters_fails',),
    'in the pattern URL, the member `:` deleted from the class `[.,;:!?]`, at its 1st occurrence':
        (E + 'test_url_ending_in_each_trailing_mark_past_72_characters_fails',),
    'in the pattern URL, the member `!` deleted from the class `[.,;:!?]`, at its 1st occurrence':
        (E + 'test_url_ending_in_each_trailing_mark_past_72_characters_fails',),
    'in the pattern URL, the member `?` deleted from the class `[.,;:!?]`, at its 1st occurrence':
        (E + 'test_url_ending_in_each_trailing_mark_past_72_characters_fails',),
    'in the pattern URL, the lookbehind `(?<![.,;:!?])` deleted, at its 1st occurrence':
        (E + 'test_url_ending_in_each_trailing_mark_past_72_characters_fails',),
    'in the pattern QUOTED, the member `\\"` deleted from the class `[^\\"\\n]`, at its 1st '
    'occurrence':
        (E + 'test_text_between_2_quoted_pairs_is_checked',),
    'in the pattern QUOTED, the negated class `[^\\"\\n]` made plain, at its 1st occurrence':
        (E + 'test_label_inside_double_quotes_passes',),
    'in the pattern QUOTED, the quantifier `*` changed to `+`, at its 1st occurrence':
        (E + 'test_masked_span_reads_as_spaces',),
    'in the pattern QUOTED, the member `\\u201d` deleted from the class `[^\\u201d\\n]`, at its '
    '1st occurrence':
        (E + 'test_text_between_2_quoted_pairs_is_checked',),
    'in the pattern QUOTED, the negated class `[^\\u201d\\n]` made plain, at its 1st occurrence':
        (E + 'test_dash_inside_curly_quotes_passes',),
    'in the pattern QUOTED, the quantifier `*` changed to `+`, at its 2nd occurrence':
        (E + 'test_masked_span_reads_as_spaces',),
    'in the pattern QUOTED, the alternative `\\"[^\\"\\n]*\\"` deleted, at its 1st occurrence':
        (E + 'test_label_inside_double_quotes_passes',),
    'in the pattern QUOTED, the alternative `\\u201c[^\\u201d\\n]*\\u201d` deleted, at its 1st '
    'occurrence':
        (E + 'test_dash_inside_curly_quotes_passes',),
    'in the pattern COMMENT, the quantifier `*?` changed to `+?`, at its 1st occurrence':
        (E + 'test_empty_comment_then_text_is_not_blank',),
    'in the pattern COMMENT, the lazy quantifier `*?` made greedy, at its 1st occurrence':
        (E + 'test_empty_comment_then_text_is_not_blank',),
    'in the pattern COMMENT, the anchor `\\Z` deleted, at its 1st occurrence':
        (D + 'test_blank_description_fails',),
    'in the pattern COMMENT, the alternative `-->` deleted, at its 1st occurrence':
        (E + 'test_empty_comment_then_text_is_not_blank',),
    'in the pattern COMMENT, the alternative `\\Z` deleted, at its 1st occurrence':
        (D + 'test_blank_description_fails',),
    'in the pattern COMMENT, the flags argument `re.S` removed, at its 1st occurrence':
        (D + 'test_blank_description_fails',),
    'in the pattern INVISIBLE, the member `\\s` deleted from the class `[\\s\\u200b\\ufeff]`, '
    'at its 1st occurrence':
        (D + 'test_empty_description_fails',),
    'in the pattern INVISIBLE, the member `\\u200b` deleted from the class '
    '`[\\s\\u200b\\ufeff]`, at its 1st occurrence':
        (D + 'test_blank_description_fails',),
    'in the pattern INVISIBLE, the member `\\ufeff` deleted from the class '
    '`[\\s\\u200b\\ufeff]`, at its 1st occurrence':
        (D + 'test_blank_description_fails',),
    'in the pattern ISE, the inline flag `(?i)` deleted, at its 1st occurrence':
        (D + 'test_ise_spelling_with_a_capital_fails',),
    'in the pattern ISE, the anchor `\\b` deleted, at its 1st occurrence':
        (E + 'test_ise_stem_inside_a_longer_word_is_not_matched',),
    'in the pattern ISE, the alternative `e` deleted, at its 1st occurrence':
        (D + 'test_each_ise_ending_fails',),
    'in the pattern ISE, the alternative `es` deleted, at its 1st occurrence':
        (D + 'test_each_ise_ending_fails',),
    'in the pattern ISE, the alternative `ed` deleted, at its 1st occurrence':
        (D + 'test_each_ise_ending_fails',),
    'in the pattern ISE, the alternative `ing` deleted, at its 1st occurrence':
        (D + 'test_each_ise_ending_fails',),
    'in the pattern ISE, the alternative `er` deleted, at its 1st occurrence':
        (D + 'test_each_ise_ending_fails',),
    'in the pattern ISE, the alternative `ers` deleted, at its 1st occurrence':
        (D + 'test_each_ise_ending_fails',),
    'in the pattern ISE, the alternative `able` deleted, at its 1st occurrence':
        (D + 'test_each_ise_ending_fails',),
    'in the pattern ISE, the alternative `ation` deleted, at its 1st occurrence':
        (D + 'test_each_ise_ending_fails',),
    'in the pattern ISE, the alternative `ations` deleted, at its 1st occurrence':
        (D + 'test_each_ise_ending_fails',),
    'in the pattern ISE, the anchor `\\b` deleted, at its 2nd occurrence':
        (D + 'test_each_ise_ending_fails',),
    'in the pattern REVISION, the anchor `\\b` deleted, at its 1st occurrence':
        (E + 'test_41_character_hex_run_passes',),
    'in the pattern REVISION, the member `a-f` deleted from the class `[0-9a-f]`, at its 1st '
    'occurrence':
        (D + 'test_full_revision_id_in_squash_message_fails',),
    'in the pattern REVISION, the quantifier `*` changed to `+`, at its 1st occurrence':
        (D + 'test_revision_id_with_its_only_digit_or_letter_first_fails',),
    'in the pattern REVISION, the lookahead `(?=[0-9a-f]*[0-9])` deleted, at its 1st occurrence':
        (E + 'test_word_of_letters_a_to_f_passes',),
    'in the pattern REVISION, the member `0-9` deleted from the class `[0-9a-f]`, at its 2nd '
    'occurrence':
        (D + 'test_revision_id_with_its_only_digit_or_letter_first_fails',),
    'in the pattern REVISION, the quantifier `*` changed to `+`, at its 2nd occurrence':
        (D + 'test_revision_id_with_its_only_digit_or_letter_first_fails',),
    'in the pattern REVISION, the lookahead `(?=[0-9a-f]*[a-f])` deleted, at its 1st occurrence':
        (E + 'test_run_of_digits_passes',),
    'in the pattern REVISION, the member `0-9` deleted from the class `[0-9a-f]`, at its 3rd '
    'occurrence':
        (D + 'test_full_revision_id_in_squash_message_fails',),
    'in the pattern REVISION, the member `a-f` deleted from the class `[0-9a-f]`, at its 3rd '
    'occurrence':
        (D + 'test_full_revision_id_in_squash_message_fails',),
    'in the pattern REVISION, the quantifier `{7,40}` changed to `{6,40}`, at its 1st occurrence':
        (E + 'test_6_character_hex_word_with_digit_passes',),
    'in the pattern REVISION, the quantifier `{7,40}` changed to `{8,40}`, at its 1st occurrence':
        (D + 'test_revision_id_in_squash_message_fails',),
    'in the pattern REVISION, the quantifier `{7,40}` changed to `{7,39}`, at its 1st occurrence':
        (D + 'test_full_revision_id_in_squash_message_fails',),
    'in the pattern REVISION, the quantifier `{7,40}` changed to `{7,41}`, at its 1st occurrence':
        (E + 'test_41_character_hex_run_passes',),
    'in the pattern REVISION, the anchor `\\b` deleted, at its 2nd occurrence':
        (E + 'test_41_character_hex_run_passes',),
    'in the pattern SQUASH_NAME, the quantifier `*` changed to `+`, at its 1st occurrence':
        (D + 'test_squash_names_with_a_leading_zero_are_not_bound',),
    'in the pattern SQUASH_NAME, the escape of `\\.` removed, at its 1st occurrence':
        (D + 'test_squash_name_with_a_further_suffix_is_not_bound',),
    'in the pattern of `re.fullmatch` in parse(), the quantifier `*` changed to `+`, at its 1st '
    'occurrence':
        (D + 'test_number_option_of_1_digit_binds',),
    'in the constant ISE_STEMS, the member `apolog` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `author` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `capital` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `categor` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `central` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `character` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `critic` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `custom` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `emphas` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `final` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `formal` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `general` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `harmon` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `initial` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `legal` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `local` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `maxim` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `memor` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `minim` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `mobil` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `modern` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `neutral` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `normal` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `optim` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `organ` removed, at its 1st occurrence':
        (D + 'test_each_ise_ending_fails',),
    'in the constant ISE_STEMS, the member `parameter` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `priorit` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `random` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `real` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `recogn` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `sanit` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `serial` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `special` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `stabil` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `standard` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `summar` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `synchron` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `token` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `util` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
    'in the constant ISE_STEMS, the member `visual` removed, at its 1st occurrence':
        (D + 'test_every_ise_stem_fails',),
}

# The generated sites that are equivalent: the mutated gate gives the same exit status and the
# same output, byte for byte, as the gate on every input. Each entry carries the argument.
EQUIVALENT_SITES = {
    'in fenced(), the statement `start = None` deleted, at its 1st occurrence':
        'start is read only in the return, and only when opener is not None, which holds only '
        'after the loop has set start, so the value None is never read.',
    'in fenced(), `0` changed up to `1` in `if (match and match.group(1)[0] == opener[0] and '
    'len(match.group(1)) >= len(opener)`, at its 1st occurrence':
        'match.group(1) and opener are each a run of 3 or more of 1 character, so index 1 names '
        'the same character as index 0.',
    'in fenced(), `0` changed down to `-1` in `if (match and match.group(1)[0] == opener[0] and '
    'len(match.group(1)) >= len(opener)`, at its 1st occurrence':
        'match.group(1) and opener are each a run of 3 or more of 1 character, so index -1 '
        'names the same character as index 0.',
    'in fenced(), `0` changed up to `1` in `if (match and match.group(1)[0] == opener[0] and '
    'len(match.group(1)) >= len(opener)`, at its 2nd occurrence':
        'match.group(1) and opener are each a run of 3 or more of 1 character, so index 1 names '
        'the same character as index 0.',
    'in fenced(), `0` changed down to `-1` in `if (match and match.group(1)[0] == opener[0] and '
    'len(match.group(1)) >= len(opener)`, at its 2nd occurrence':
        'match.group(1) and opener are each a run of 3 or more of 1 character, so index -1 '
        'names the same character as index 0.',
    'in check_squash(), `1` changed up to `2` in `subject = text.split("\\n", 1)[0]`, at its '
    '1st occurrence':
        'the subject is the text before the first line feed, and a split of at most 2 gives the '
        'same first piece as a split of at most 1.',
    'in number_from_name(), the statement `return None` deleted, at its 1st occurrence':
        'the function then ends and returns None, the same value.',
    'in parse(), `0` changed down to `-1` in `return modes[0], options[modes[0]], number`, at '
    'its 1st occurrence':
        'modes holds exactly 1 flag once the length test before it has passed, so index -1 '
        'names the same flag as index 0.',
    'in parse(), `0` changed down to `-1` in `if modes[0] != "--squash":`, at its 1st occurrence':
        'modes holds exactly 1 flag once the length test before it has passed, so index -1 '
        'names the same flag as index 0.',
    'in parse(), `0` changed down to `-1` in `return modes[0], options[modes[0]], number`, at '
    'its 2nd occurrence':
        'modes holds exactly 1 flag once the length test before it has passed, so index -1 '
        'names the same flag as index 0.',
    'in the pattern FENCE, the quantifier `{0,3}` made lazy, at its 1st occurrence':
        'the character after the spaces must be a backtick or a tilde, so a lazy run of spaces '
        'ends where the greedy run ends, and match() returns the same match.',
    'in the pattern FENCE, the quantifier `{3,}` made lazy, at its 1st occurrence':
        'the lookahead after the run of backticks requires that no backtick follows, so a lazy '
        'run grows to the end of the run, as the greedy one does.',
    'in the pattern FENCE, the quantifier `*` made lazy, at its 1st occurrence':
        'a lookahead asks only whether its pattern matches, and a lazy run matches where the '
        'greedy run matches, so the lookahead gives the same answer.',
    'in the pattern URL, the quantifier `?` made lazy, at its 1st occurrence':
        'the 3 characters :// must follow, so a lazy s is taken exactly when the text has it, '
        'and the match is the same.',
    'in the pattern URL, the quantifier `*` made lazy, at its 1st occurrence':
        'the class refuses the mark that follows the run, so a lazy run grows to the first such '
        'mark, where the greedy run stops, and the match is the same.',
    'in the pattern QUOTED, the member `\\n` deleted from the class `[^\\"\\n]`, at its 1st '
    'occurrence':
        'the mask reads 1 line, which holds no line feed, so the class never meets one.',
    'in the pattern QUOTED, the quantifier `*` made lazy, at its 1st occurrence':
        'the class refuses the mark that follows the run, so a lazy run grows to the first such '
        'mark, where the greedy run stops, and the match is the same.',
    'in the pattern QUOTED, the member `\\n` deleted from the class `[^\\u201d\\n]`, at its 1st '
    'occurrence':
        'the mask reads 1 line, which holds no line feed, so the class never meets one.',
    'in the pattern QUOTED, the quantifier `*` made lazy, at its 2nd occurrence':
        'the class refuses the mark that follows the run, so a lazy run grows to the first such '
        'mark, where the greedy run stops, and the match is the same.',
    'in the pattern REVISION, the member `0-9` deleted from the class `[0-9a-f]`, at its 1st '
    'occurrence':
        'the lookahead reads a run of hex digits, so the first character after its leading '
        'letters a to f is a digit exactly when the run holds a digit; the lookahead matches on '
        'the same runs as before.',
    'in the pattern REVISION, the quantifier `*` made lazy, at its 1st occurrence':
        'a lookahead asks only whether its pattern matches, and a lazy run matches where the '
        'greedy run matches, so the lookahead gives the same answer.',
    'in the pattern REVISION, the member `a-f` deleted from the class `[0-9a-f]`, at its 2nd '
    'occurrence':
        'the lookahead reads a run of hex digits, so the first character after its leading '
        'digits is a letter a to f exactly when the run holds such a letter; the lookahead '
        'matches on the same runs as before.',
    'in the pattern REVISION, the quantifier `*` made lazy, at its 2nd occurrence':
        'a lookahead asks only whether its pattern matches, and a lazy run matches where the '
        'greedy run matches, so the lookahead gives the same answer.',
    'in the pattern REVISION, the quantifier `{7,40}` made lazy, at its 1st occurrence':
        'the word boundary after the run needs a character that is not a hex digit, so a lazy '
        'run grows to the end of the hex run, where the greedy run ends, and the matches are '
        'the same.',
    'in the pattern SQUASH_NAME, the quantifier `*` made lazy, at its 1st occurrence':
        'the pattern is matched with fullmatch, which must reach the end of the text either '
        'way, so a lazy run matches the same texts.',
    'in the pattern of `re.fullmatch` in parse(), the quantifier `*` made lazy, at its 1st '
    'occurrence':
        'the pattern is matched with fullmatch, which must reach the end of the text either '
        'way, so a lazy run matches the same texts.',
}


def row(words, old, new, ids, count=1, target="gate"):
    """1 hand row: (words, target file, old text, new text, count, case ids)."""
    return (words, target, old, new, count, tuple(ids))


# Hand-written rows of changes the generator does not make, such as a change of several tokens,
# a restored clause or a change of the workflow; the adequacy test leaves them alone.
HAND_ROWS = (
    row(
        'the integer type test of the payload number widened to isinstance',
        'type(number) is not int',
        'not isinstance(number, int)',
        [U + 'test_payload_number_true_is_not_an_integer']),
    row(
        'the test that the payload is an object dropped',
        'pull = event.get("pull_request") if isinstance(event, dict) else None',
        'pull = event.get("pull_request")',
        [U + 'test_payload_that_is_a_list_is_not_a_pull_request_event']),
    row(
        'the 2 substitutions of the blank test swapped',
        'return not INVISIBLE.sub("", COMMENT.sub("", text))',
        'return not COMMENT.sub("", INVISIBLE.sub("", text))',
        [E + 'test_comment_opener_broken_by_a_zero_width_space_is_text']),
    row(
        'the fence indent bound dropped',
        'r" {0,3}(',
        'r"(',
        [E + 'test_fence_indented_1_to_3_spaces_masks_its_lines']),
    row(
        'the fence indent bound widened to any number of spaces',
        'r" {0,3}(',
        'r" *(',
        [E + 'test_fence_indented_4_spaces_is_not_a_fence']),
    row(
        'a closer of the other character accepted',
        'match.group(1)[0] == opener[0]',
        'True',
        [E + 'test_other_character_closer_leaves_fence_open']),
    row(
        'a shorter closer accepted',
        'len(match.group(1)) >= len(opener)',
        'True',
        [E + 'test_shorter_closer_leaves_fence_open']),
    row(
        'the closer strip widened back to any whitespace',
        '.strip(" \\t")',
        '.strip()',
        [E + 'test_closer_followed_by_other_whitespace_leaves_fence_open']),
    row(
        'the closer strip narrowed to spaces',
        '.strip(" \\t")',
        '.strip(" ")',
        [E + 'test_closer_followed_by_a_tab_or_a_space_closes_fence']),
    row(
        'the closer strip narrowed to tabs',
        '.strip(" \\t")',
        '.strip("\\t")',
        [E + 'test_closer_followed_by_a_tab_or_a_space_closes_fence']),
    row(
        'a closer with trailing text accepted',
        '\n                and not line[match.end():].strip(" \\t")):',
        '):',
        [E + 'test_closer_with_trailing_text_leaves_fence_open']),
    row(
        'the fenced lines dropped from the fenced set',
        'return inside, (start if',
        'return set(), (start if',
        [E + 'test_label_and_width_inside_fence_pass']),
    row(
        'the unclosed-fence report made never to apply',
        'if unclosed is not None:',
        'if False:',
        [D + 'test_unclosed_fence_in_description_fails']),
    row(
        'a span that closes on the farthest run of the same length',
        'later[width] = index',
        'later.setdefault(width, index)',
        [E + 'test_span_closes_on_the_nearest_run_of_its_length']),
    row(
        'the step of the inline-span scan changed',
        'index = closer[index] + 1',
        'index += 1',
        [E + 'test_span_scan_resumes_after_its_closer']),
    row(
        'no closer found for any backtick run',
        'closer[index] = later.get(width)',
        'closer[index] = None',
        [E + 'test_label_in_backticks_passes']),
    row(
        'the inline-code mask skipped',
        'line = masked(line, code_spans(line))',
        'line = masked(line, [])',
        [E + 'test_label_in_backticks_passes']),
    row(
        'the curly quote marks removed from both classes of the URL pattern',
        '\\u2014\\u201c\\u201d\\u2018\\u2019]',
        '\\u2014]',
        [
         E + 'test_dash_after_curly_quoted_url_fails',
         E + 'test_curly_quoted_url_ending_a_long_squash_line_fails',
        ], count=2),
    row(
        'the parenthesis-pair branch of the URL pattern disabled',
        '|\\([^',
        '|(?!)\\([^',
        [E + 'test_long_url_with_a_parenthesis_pair_passes']),
    row(
        'the mask written with an underscore',
        'MASK_CHAR = " "',
        'MASK_CHAR = "_"',
        [D + 'test_label_right_after_masked_span_fails']),
    row(
        'the URL mask removed',
        'MASKS = (URL, QUOTED)',
        'MASKS = (QUOTED,)',
        [E + 'test_ise_word_inside_url_passes']),
    row(
        'the quote mask removed',
        'MASKS = (URL, QUOTED)',
        'MASKS = (URL,)',
        [E + 'test_label_inside_double_quotes_passes']),
    row(
        'the unclosed comment no longer runs to the end',
        '(?:-->|\\Z)',
        '-->',
        [D + 'test_blank_description_fails']),
    row(
        'the blank test reduced to whitespace only',
        'return not INVISIBLE.sub("", COMMENT.sub("", text))',
        'return not text.strip()',
        [D + 'test_blank_description_fails']),
    row(
        'the empty-text check made never to apply',
        'if blank(text):\n        report.defect(prefix',
        'if False:\n        report.defect(prefix',
        [D + 'test_empty_description_fails']),
    row(
        'the squash check made to go on after a blank text',
        'if blank(text):\n        return',
        'if False:\n        return',
        [D + 'test_empty_squash_file_fails']),
    row(
        'the label scan replaced by an empty list of hits',
        'hits = scan(rel, "\\n".join(prose))',
        'hits = []',
        [D + 'test_label_in_description_fails']),
    row(
        'the em dash removed from the dash check',
        '("an em dash, U+2014", "\\u2014"),',
        '',
        [D + 'test_em_dash_fails']),
    row(
        'the en dash removed from the dash check',
        '("an en dash, U+2013", "\\u2013"),',
        '',
        [D + 'test_en_dash_fails']),
    row(
        'the width check applied to the description',
        'width_applies = squash',
        'width_applies = True',
        [E + 'test_long_description_paragraph_passes']),
    row(
        'the revision check applied to the description',
        'revision_applies = squash',
        'revision_applies = True',
        [E + 'test_revision_id_in_description_passes']),
    row(
        'the URL-excess width exemption removed',
        'exempt = number - 1 in fence or excess_is_url(line)',
        'exempt = number - 1 in fence',
        [E + 'test_long_url_line_passes']),
    row(
        'the fenced-code width exemption removed',
        'exempt = number - 1 in fence or excess_is_url(line)',
        'exempt = excess_is_url(line)',
        [E + 'test_label_and_width_inside_fence_pass']),
    row(
        'the URL start bound dropped',
        'match.start() <= WIDTH and ',
        '',
        [E + 'test_url_starting_past_72_characters_fails']),
    row(
        'the URL end test dropped',
        'match.end() >= len(line)',
        'True',
        [E + 'test_long_line_with_url_before_the_excess_fails']),
    row(
        'the fenced lines given to the prose checks',
        '"" if index in fence else mask(line)',
        'mask(line)',
        [E + 'test_label_and_width_inside_fence_pass']),
    row(
        'the revision check run on the masked lines',
        'for number, raw in enumerate(lines, 1):',
        'for number, raw in enumerate(prose, 1):',
        [D + 'test_revision_id_in_backticks_in_squash_message_fails']),
    row(
        'the revision pattern made to match nothing',
        'REVISION = re.compile(r"\\b',
        'REVISION = re.compile(r"(?!)\\b',
        [D + 'test_revision_id_in_squash_message_fails']),
    row(
        'the subject suffix check made never to apply',
        'if not subject.endswith(suffix):',
        'if False:',
        [D + 'test_squash_subject_without_its_number_fails']),
    row(
        'the binding note skipped when no number is known',
        'if number is None:\n        report.note',
        'if False:\n        report.note',
        [D + 'test_binding_not_checked_line_is_not_a_defect']),
    row(
        'the digit bound off by 1 upwards',
        'if len(digits) > MAX_DIGITS:',
        'if len(digits) > MAX_DIGITS + 1:',
        [
         D + 'test_squash_name_of_19_digits_is_not_bound',
         U + 'test_number_option_of_18_digits_binds_and_19_is_a_usage_error',
        ]),
    row(
        'the digit bound made never to apply',
        'if len(digits) > MAX_DIGITS:',
        'if False:',
        [
         U + 'test_number_option_over_the_digit_bound_is_a_usage_error',
         U + 'test_squash_name_too_long_to_open_exits_2',
        ]),
    row(
        'the digit bound raised to 100',
        'MAX_DIGITS = 18',
        'MAX_DIGITS = 100',
        [D + 'test_squash_name_of_19_digits_is_not_bound']),
    row(
        'the squash folder test dropped from the file name binding',
        'parts[-3:-1] == (".github", "squash") and ',
        '',
        [D + 'test_number_name_outside_a_squash_folder_is_not_bound']),
    row(
        'the squash name pattern made to allow a leading zero',
        'r"[1-9][0-9]*\\.txt"',
        'r"[0-9]+\\.txt"',
        [D + 'test_squash_names_with_a_leading_zero_are_not_bound']),
    row(
        'the number option ignored in favour of the file name',
        'number = given_number if given_number is not None else number_from_name(path)',
        'number = number_from_name(path)',
        [D + 'test_number_option_binding_passes']),
    row(
        'the CRLF replace in the text reader dropped',
        'return text.replace("\\r\\n", "\\n")',
        'return text',
        [O + 'test_squash_file_with_crlf_line_endings_passes']),
    row(
        'the CRLF replace in the payload reader dropped',
        'return number, body.replace("\\r\\n", "\\n")',
        'return number, body',
        [O + 'test_event_body_with_crlf_line_endings_passes']),
    row(
        'UTF-8 decoded with replacement',
        '"utf-8", "strict"',
        '"utf-8", "replace"',
        [U + 'test_undecodable_text_exits_2']),
    row(
        'the decode handler narrowed to an exception that never occurs',
        'except UnicodeDecodeError as error:',
        'except ImportError as error:',
        [U + 'test_undecodable_text_exits_2']),
    row(
        'the file read handler narrowed to a missing file',
        '    except OSError as error:\n        raise Unreadable("{} {}: {}"',
        '    except FileNotFoundError as error:\n        raise Unreadable("{} {}: {}"',
        [U + 'test_folder_given_as_text_file_exits_2']),
    row(
        'a missing file read as empty',
        'raise Unreadable("{} {}: {}".format(what, path, error.strerror or error)) from error',
        'return ""',
        [U + 'test_missing_squash_file_exits_2']),
    row(
        'a payload with no pull request read as the pull request itself',
        'pull = event.get("pull_request") if',
        'pull = event if',
        [U + 'test_other_event_type_exits_2']),
    row(
        'the pull request test made never to apply',
        'if not isinstance(pull, dict):',
        'if False:',
        [U + 'test_other_event_type_exits_2']),
    row(
        'the integer type test of the number dropped',
        'type(number) is not int or ',
        '',
        [U + 'test_payload_without_number_exits_2']),
    row(
        'a null body no longer read as empty',
        'if body is None:',
        'if False:',
        [D + 'test_null_body_fails']),
    row(
        'the body-not-text check made never to apply',
        'if not isinstance(body, str):',
        'if False:',
        [U + 'test_body_that_is_a_number_exits_2']),
    row(
        'the handler for an unreadable working directory narrowed to one that never occurs',
        '    except OSError as error:\n        raise Unreadable("squash file {}: the',
        '    except ZeroDivisionError as error:\n        raise Unreadable("squash file {}: the',
        [U + 'test_removed_working_directory_exits_2']),
    row(
        'the lint found from the working directory',
        'LINT = ROOT / "tools" / "test-no-qa-labels.py"',
        'LINT = Path("tools") / "test-no-qa-labels.py"',
        [O + 'test_event_from_another_working_directory']),
    row(
        'the squash folder taken from the working directory',
        'SQUASH_DIR = ROOT / ".github" / "squash"',
        'SQUASH_DIR = Path(".github") / "squash"',
        [O + 'test_event_from_another_working_directory']),
    row(
        'an unloadable lint read as a scan with no hits',
        'raise Unreadable(LINT_FAILURE.format(LINT, describe(error))) from error',
        'return lambda rel, text: []',
        [U + 'test_unloadable_lint_exits_2']),
    row(
        'the message of an error raised while the lint loads formatted directly',
        'LINT_FAILURE.format(LINT, describe(error))',
        'LINT_FAILURE.format(LINT, error)',
        [U + 'test_error_whose_message_exits_exits_2']),
    row(
        'str.__str__ dropped where the type name is described',
        'name = str.__str__(str(type(error).__name__))',
        'name = str(type(error).__name__)',
        [U + 'test_type_name_of_a_str_subclass_is_described_as_text']),
    row(
        'str.__str__ dropped where an error is described',
        'text = str.__str__(str(error))',
        'text = str(error)',
        [U + 'test_message_of_a_str_subclass_is_described_as_text']),
    row(
        'a KeyboardInterrupt re-raise restored where a message is formatted',
        'text = str.__str__(str(error))\n    except BaseException:',
        'text = str.__str__(str(error))\n    except KeyboardInterrupt:\n        raise\n    '
        'except BaseException:',
        [U + 'test_error_whose_message_raises_an_interrupt_exits_2']),
    row(
        'a KeyboardInterrupt re-raise restored where the lint loads',
        'scan = module.scan\n    except BaseException',
        'scan = module.scan\n    except KeyboardInterrupt:\n        raise\n    except '
        'BaseException',
        [U + 'test_lint_interrupted_while_it_loads_exits_2']),
    row(
        'a KeyboardInterrupt re-raise restored in main()',
        'status = EXIT_UNREADABLE\n    except BaseException',
        'status = EXIT_UNREADABLE\n    except KeyboardInterrupt:\n        raise\n    except '
        'BaseException',
        [U + 'test_scan_interrupted_exits_2']),
    row(
        'the catch-all handler of main() narrowed to one that never occurs',
        '    except BaseException as error:\n        # A scan',
        '    except ZeroDivisionError as error:\n        # A scan',
        [U + 'test_scan_that_raises_exits_2']),
    row(
        'the message of an error caught in main() formatted directly',
        'describe(error)))\n        status',
        'error))\n        status',
        [U + 'test_error_whose_message_exits_exits_2']),
    row(
        'the no-argument guard of parse() dropped',
        'if not argv:',
        'if False:',
        [U + 'test_no_arguments_is_a_usage_error']),
    row(
        'the unknown-argument guard of parse() dropped',
        'if flag not in ("--event", "--description", "--squash", "--number"):',
        'if False:',
        [U + 'test_bad_arguments_are_usage_errors']),
    row(
        'the duplicate-flag test dropped',
        'if flag in options or not rest:',
        'if not rest:',
        [U + 'test_flag_given_twice_is_a_usage_error']),
    row(
        'the missing-value test dropped',
        'if flag in options or not rest:',
        'if flag in options:',
        [U + 'test_bad_arguments_are_usage_errors']),
    row(
        'the mode count test made to allow no mode',
        'if len(modes) != 1:',
        'if len(modes) > 1:',
        [U + 'test_bad_arguments_are_usage_errors']),
    row(
        'the mode count test made to allow 2 modes',
        'if len(modes) != 1:',
        'if len(modes) < 1:',
        [U + 'test_bad_arguments_are_usage_errors']),
    row(
        'the number option allowed with every mode',
        'if modes[0] != "--squash":',
        'if False:',
        [U + 'test_bad_arguments_are_usage_errors']),
    row(
        'the number option made to allow a leading zero',
        'r"[1-9][0-9]*", options',
        'r"[0-9]+", options',
        [U + 'test_number_option_with_a_leading_zero_is_a_usage_error']),
    row(
        'the number option bound made never to apply',
        'if number is None:\n            raise Usage',
        'if False:\n            raise Usage',
        [U + 'test_number_option_over_the_digit_bound_is_a_usage_error']),
    row(
        'the usage handler of main() narrowed to one that never occurs',
        'except Usage as error:',
        'except ZeroDivisionError as error:',
        [U + 'test_no_arguments_is_a_usage_error']),
    row(
        'the unreadable handler of main() narrowed to one that never occurs',
        'except Unreadable as error:',
        'except ZeroDivisionError as error:',
        [U + 'test_unreadable_line_names_its_input']),
    row(
        'unreadable input given exit 0',
        'EXIT_UNREADABLE = 2',
        'EXIT_UNREADABLE = 0',
        [U + 'test_missing_payload_exits_2']),
    row(
        'a usage error given exit 0',
        'EXIT_USAGE = 2',
        'EXIT_USAGE = 0',
        [U + 'test_no_arguments_is_a_usage_error']),
    row(
        'a defect given exit 0',
        'status = EXIT_DEFECT if report.count else 0',
        'status = 0',
        [D + 'test_em_dash_fails']),
    row(
        'report lines printed without their prefix',
        'print(prefix + ascii_text(detail))',
        'print(ascii_text(detail))',
        [O + 'test_defect_lines_start_with_their_prefix']),
    row(
        'report lines printed without escapes',
        'print(prefix + ascii_text(detail))',
        'print(prefix + detail)',
        [O + 'test_carriage_return_and_del_are_escaped']),
    row(
        "the job's time limit removed from the workflow",
        '    timeout-minutes: 10\n',
        '',
        [O + 'test_workflow_job_has_a_time_limit'], target='workflow'),
)
SWEEP_TARGETS = {"gate": Path("tools") / "check-pr-text.py",
                 "workflow": Path(".github") / "workflows" / "pr-text.yml"}
# At most this many sweep children run at once, and each is stopped after SWEEP_TIMEOUT s.
SWEEP_WORKERS = 8
SWEEP_TIMEOUT = 300
# The CPU limit of each sweep child, in seconds, equal to SWEEP_TIMEOUT, so that, as with
# GATE_CPU, the wall timeout stops a sweep child of 1 thread first while the top suite process
# lives, and a sweep child that spins after that process is gone ends by it. A sweep child, not
# counting its gate children, used at most 0.48 s under an 8192 KiB stack and 0.44 s with no
# stack limit, so SWEEP_CPU is over 600 times that; the margin is set by the timeout, not by
# the measure, and leaves room for a row that names a case of more CPU time in the suite
# process. Its cost and residual are those of GATE_CPU: a sweep child that waits on its gate
# child uses no CPU time, so after the top suite process is gone it runs on, at most until its
# named cases end, each gate child under its own limits and the timeout the sweep child still
# enforces.
SWEEP_CPU = 300
# The rows whose mutated gate never ends on an input of their named cases, each with the limit
# that stops it and the argument, read from the mutated code, that the gate no longer ends.
SCAN_STALLS = ("In the loop `while index < len(runs):`, {}, so on the first run {} index stays "
               "where it is, nothing is appended, and the loop runs at constant memory until "
               "the wall timeout stops it.")
RUNAWAY_SITES = {
    'in code_spans(), the statement `index = closer[index] + 1` deleted, at its 1st occurrence':
        ("memory limit",
         "In the loop `while index < len(runs):`, the else branch appends a span and no longer "
         "moves index past its closer, so on the first run that has a closer it appends the "
         "same span on each pass and the list grows until the memory limit stops the gate."),
    'in code_spans(), the statement `if closer[index] is None:` deleted, at its 1st occurrence':
        ("wall timeout", SCAN_STALLS.format("the whole if and else are replaced by pass",
                                            "of any kind")),
    'in code_spans(), the statement `index += 1` deleted, at its 1st occurrence':
        ("wall timeout", SCAN_STALLS.format("the branch for a run with no closer is pass",
                                            "with no closer")),
    'in code_spans(), `1` changed down to `0` in `index += 1`, at its 1st occurrence':
        ("wall timeout", SCAN_STALLS.format("the branch for a run with no closer adds 0",
                                            "with no closer")),
}


class MutantSweep(unittest.TestCase):
    """The mutant sweep: a site generated from the gate source, or a hand row, per guard.

    generate_sites() reads tools/check-pr-text.py, leaves out its docstrings and its
    "if __name__" block, and yields every site of a closed set of operators, OPERATORS. In the
    Python code, from its ast: each statement of a function body deleted, or replaced by pass
    when it is the only statement of its block; each comparison operator replaced by its
    partner (< and <=, > and >=, == and !=, is and is not, in and not in); each and or or
    swapped; each not removed; each True or False flipped; each integer constant changed by 1
    up and by 1 down; in each except clause, each member of its tuple removed, BaseException
    replaced by Exception and the handler body replaced by raise; each call of fullmatch, match
    or search replaced by each of the other 2; any and all swapped; and each member of a tuple
    of strings joined into a pattern, such as ISE_STEMS, removed. In each pattern literal given
    to re.compile, re.fullmatch, re.match or re.search, the pieces joined to build ISE
    included, read by regex_parse(): each anchor and word boundary deleted; each lookahead and
    lookbehind deleted; each alternative of each alternation deleted; each member or range of a
    class of 2 or more members deleted, and a negated class made plain; each quantifier changed
    ({m,n} with m and n each 1 up and 1 down where valid, * to +, + to *, ? removed) and made
    lazy or greedy; each escaped metacharacter unescaped; and each inline flag and each flags
    argument removed. regex_parse() raises UnknownConstruct on a construct it does not know, so
    a new construct fails the adequacy test by name. Each site is named in words, from where it
    is, the operator and the text it changes, and its occurrence, with its exact old text,
    whole lines, its new text and the number of times its old text occurs.

    The adequacy test runs no mutant. It fails when a generated site has neither a row in
    SWEEP_ROWS nor an entry in EQUIVALENT_SITES, when a row or an entry names a site the
    generator does not yield, and when an operator of OPERATORS yields no site, since each of
    them has a site in the gate as it stands, so a broken generator cannot pass by yielding
    nothing. HAND_ROWS holds rows the generator does not make, which it leaves alone.

    The kill criterion: a row is killed when its named cases, run on a copy of the tree with
    the site or the hand row applied, exit 1 with FAILED, under the limit-hit rule. Each sweep
    child runs in a new session under SWEEP_MEMORY and SWEEP_CPU, and under SWEEP_TIMEOUT,
    which the top suite process enforces; each gate child it starts runs in its process group
    under the lower of GATE_MEMORY and SWEEP_MEMORY, under GATE_CPU and under its case's wall
    timeout, which the sweep child enforces. When SWEEP_TIMEOUT stops a sweep child, the top
    suite process kills its whole process group, so a gate child it is running ends with it.
    A child hits a limit when a gate child reports MemoryError, is ended by its CPU limit or is
    stopped by its timeout, which run_child() names on a LIMIT_HIT line, or when the sweep child
    itself raises MemoryError, is ended by SWEEP_CPU or is stopped by SWEEP_TIMEOUT. The
    limit-hit rule: RUNAWAY_SITES lists each row whose mutated gate never
    ends on an input of its named cases, with the limit that stops it and the argument, read
    from the mutated code, that the gate no longer ends or grows with no bound. A listed row is
    killed only when its named cases fail and the child hit that limit; a row not listed that
    hits any limit fails the sweep, naming the row and the limit, and is not killed. The 4
    listed rows each name test_code_span_scan_ends_on_each_run_shape, which runs the gate on a
    closed span, a lone run and a run with no closer under a wall timeout of SPAN_TIMEOUT s, so
    each is killed in seconds: the row that grows by the memory limit, the 3 that spin by the
    timeout. A site is equivalent only when the
    mutated gate gives the same exit status and the same output, byte for byte, as the gate on
    every input; each entry of EQUIVALENT_SITES carries the argument. A site that changes only
    the reason in a line is not equivalent: it has a row whose case pins that reason. For each
    row the sweep copies the gate, this suite, the label lint and the workflow into a fresh
    temporary tree, checks that the old text occurs the recorded number of times, applies the
    change and runs the named cases there in a separate process. The named cases also pass on
    an unmutated copy. No row names a case of this class, so the sweep cannot run itself.

    Residual: a change outside the operators passes unswept unless a hand row holds it, such as
    a change of 2 tokens at once, a changed string constant, a changed message, a changed
    docstring, a deleted statement at module level, a member deleted from a class of 1 member,
    and a change in the "if __name__" block or in the label lint. A listed row is killed by a
    limit, not by a wrong output of a gate that ends.
    """

    def copy_tree(self, root):
        """Copy the gate, this suite, the lint and the workflow into root."""
        for source, target in ((GATE, SWEEP_TARGETS["gate"]), (SUITE, Path("tools") / SUITE.name),
                               (LINT, Path("tools") / LINT.name),
                               (WORKFLOW, SWEEP_TARGETS["workflow"])):
            (root / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, root / target)

    def run_cases(self, root, ids):
        """(exit status, last line of the report, limits hit) of the named cases run in root.

        The limits hit are the LIMIT_HIT lines of the child, and a MemoryError of the child
        itself, its own CPU limit as cpu_hit() reads it, or its own timeout, each named once.
        """
        try:
            done = run_child(["-I", "-B", root / "tools" / SUITE.name, *ids],
                             memory=SWEEP_MEMORY, timeout=SWEEP_TIMEOUT, cwd=root, text=True,
                             encoding="utf-8", cpu=SWEEP_CPU)
        except subprocess.TimeoutExpired:
            return None, "timed out", ["the sweep timeout of {} s".format(SWEEP_TIMEOUT)]
        lines = done.stderr.strip().splitlines()
        hits = sorted({line[len(LIMIT_HIT):] for line in lines if line.startswith(LIMIT_HIT)})
        if "MemoryError" in done.stderr and not hits:
            hits = ["the memory limit of {} bytes".format(SWEEP_MEMORY)]
        own = cpu_hit(done.returncode, SWEEP_CPU)
        if own and own not in hits:
            hits.append(own)
        return done.returncode, lines[-1] if lines else "", hits

    def missing_cases(self, ids):
        return [case for case in ids
                if not hasattr(globals().get(case.partition(".")[0]), case.partition(".")[2])]

    def killed(self, words, path, mutated, ids, root):
        """None when the named cases fail on the mutated file, or the reason they do not.

        A row hits a limit, and that kills it, only when RUNAWAY_SITES lists it with that
        limit; a row that hits any other limit is not killed.
        """
        path.write_text(mutated, encoding="utf-8")
        code, last, hits = self.run_cases(root, ids)
        limit = RUNAWAY_SITES.get(words, (None,))[0]
        if limit is None and hits:
            return "hit a limit but is not a runaway site: " + "; ".join(hits)
        if limit is not None and not any(limit in hit for hit in hits):
            return "a runaway site whose cases did not fail by its {}: exit {}, {}".format(
                limit, code, last)
        if code == 1 and last.startswith("FAILED"):
            return None
        return "survived: exit {}, {}".format(code, last)

    def mutate_site(self, item):
        """None when the generated site of a row is killed, or the reason it is not."""
        words, ids = item
        missing = self.missing_cases(ids)
        if missing:
            return "names a case that does not exist: " + ", ".join(missing)
        site = self.sites.get(words)
        if site is None:
            return "names a site the generator does not yield"
        root = Path(tempfile.mkdtemp())
        try:
            self.copy_tree(root)
            path = root / SWEEP_TARGETS["gate"]
            mutated = apply_site(path.read_text(encoding="utf-8"), site)
            if mutated is None:
                return "the old text does not occur {} times".format(site.count)
            return self.killed(words, path, mutated, ids, root)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def mutate_hand(self, sweep_row):
        """None when a hand row is killed, or the reason it is not."""
        words, target, old, new, count, ids = sweep_row
        missing = self.missing_cases(ids)
        if missing:
            return "names a case that does not exist: " + ", ".join(missing)
        root = Path(tempfile.mkdtemp())
        try:
            self.copy_tree(root)
            path = root / SWEEP_TARGETS[target]
            text = path.read_text(encoding="utf-8")
            found = text.count(old)
            if found != count:
                return "the text occurs {} times, not {}".format(found, count)
            return self.killed(words, path, text.replace(old, new), ids, root)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def setUp(self):
        self.sites = {site.words: site
                      for site in generate_sites(GATE.read_text(encoding="utf-8"))}

    def test_rows_are_well_formed(self):
        names = [sweep_row[0] for sweep_row in HAND_ROWS]
        self.assertEqual(len(names), len(set(names)), "each hand row needs its own name")
        self.assertFalse(set(SWEEP_ROWS) & set(EQUIVALENT_SITES))
        for words, target, old, new, count, ids in HAND_ROWS:
            with self.subTest(row=words):
                self.assertIn(target, SWEEP_TARGETS)
                self.assertNotEqual(old, new)
                self.assertGreaterEqual(count, 1)
        for words, ids in list(SWEEP_ROWS.items()) + [(r[0], r[5]) for r in HAND_ROWS]:
            with self.subTest(row=words):
                self.assertTrue(ids)
                for case in ids:
                    class_name, _, method = case.partition(".")
                    self.assertNotEqual(class_name, type(self).__name__, "the sweep would recurse")
                    self.assertTrue(hasattr(globals().get(class_name), method), case)
        for words, argument in EQUIVALENT_SITES.items():
            with self.subTest(site=words):
                self.assertTrue(argument.strip())
        rows = set(SWEEP_ROWS) | set(names)
        for words, (limit, argument) in RUNAWAY_SITES.items():
            with self.subTest(runaway=words):
                self.assertIn(words, rows)
                self.assertIn(limit, ("memory limit", "wall timeout"))
                self.assertTrue(argument.strip())

    def test_generated_sites_are_adequate(self):
        generated = set(self.sites)
        listed = set(SWEEP_ROWS) | set(EQUIVALENT_SITES)
        self.assertEqual(sorted(generated - listed), [], "generated sites with no row")
        self.assertEqual(sorted(listed - generated), [], "rows of sites not generated")
        counts = collections.Counter(site.operator for site in self.sites.values())
        self.assertEqual([operator for operator in OPERATORS if not counts[operator]], [],
                         "operators with no site")

    def test_named_cases_pass_unmutated(self):
        ids = sorted({case for ids in SWEEP_ROWS.values() for case in ids}
                     | {case for sweep_row in HAND_ROWS for case in sweep_row[5]})
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        self.copy_tree(root)
        self.assertEqual(self.run_cases(root, ids), (0, "OK", []))

    def test_each_row_is_killed(self):
        with ThreadPoolExecutor(max_workers=SWEEP_WORKERS) as pool:
            site_results = list(pool.map(self.mutate_site, SWEEP_ROWS.items()))
            hand_results = list(pool.map(self.mutate_hand, HAND_ROWS))
        for words, reason in zip(SWEEP_ROWS, site_results):
            with self.subTest(row=words):
                self.assertIsNone(reason, words)
        for sweep_row, reason in zip(HAND_ROWS, hand_results):
            with self.subTest(row=sweep_row[0]):
                self.assertIsNone(reason, sweep_row[0])


if __name__ == "__main__":
    unittest.main()
