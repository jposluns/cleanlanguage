#!/usr/bin/env python3
"""Run the strict Released-line extractor for a shell caller, through --json.

Row 89. The shell callers of ``tools/skill-release-date.py`` (the release
workflow, ``tools/release-package.sh``, ``tools/release-dry-run.sh`` and
``tools/check-portable-text-sync.sh``) run this client instead of the
extractor's CLI modes. The CLI gives its content verdicts as exit codes, and
exit 1, its malformed verdict, is also what Python returns for a SyntaxError
or any uncaught exception, so a broken extractor could read as malformed
content. This client runs the extractor in its ``--json`` mode, checks the
reply against the contract, and gives a content verdict only from a reply
that meets it. Anything else, whatever the cause, is reported as the
extractor being unavailable.

Usage, one word and exactly its arguments, with no option parsing (so
``-``, ``--json``, an empty string and ``-x`` are always values):

    baseline                               --baseline
    extract-file PATH                      FILE (PATH is read as a file,
                                           even when it is "-")
    extract-stdin                          - (all of stdin is read first)
    requires-date VERSION                  --requires-date VERSION
    check-date VALUE                       --check-date VALUE
    published-day PUBLISHED_AT             --published-day PUBLISHED_AT
    publish-window EXPECTED NOW            --publish-window EXPECTED NOW
    confirm-published EXPECTED PUBLISHED_AT
                                           --confirm-published EXPECTED
                                           PUBLISHED_AT

Each word names the CLI mode it replaces. The client prints what that mode
prints, on the same stream and with the same ``skill-release-date: `` prefix,
and exits with that mode's documented code plus 10, so 0 stays 0:

  0   the value, printed to stdout (``required`` or ``optional`` for
      requires-date)
  11  malformed (CLI 1), or the input is not valid UTF-8
  13  absent: no Released line (CLI 3), extract only
  14  the client could not read its input (CLI 4)
  15  refused (CLI 5), publish-window and confirm-published only
  16  unavailable: the extractor did not deliver a reply that meets the
      contract, whatever the cause (an exit other than 0, a signal, a
      timeout, too much output, not JSON, a breach of the contract, or an
      error in the client machinery). The client prints one line,
      ``skill-release-date-client: skill-release-date.py <reason> in <op>,
      so the extractor is unavailable``, followed by ``; it printed: <text>``
      when the extractor wrote anything to stderr (at most STDERR_LIMIT
      bytes of it, its lines joined with `` | `` so the message stays one
      line). When the client machinery itself fails outside the run of the
      extractor, the line is ``skill-release-date-client:
      skill-release-date.py could not be run, waited for, or read (<type>:
      <error>), so the extractor is unavailable``, with no ``in <op>``
  2   a usage error of the client

No code below 10 other than 0 and 2 carries a meaning, so an exit that
Python, bash or a signal produces on its own (1 or 2 from a broken or
missing client, 126, 127, 128 and above) is never read as a verdict; every
caller reads any exit it does not name as the tool being unavailable.

The file reads (extract-file and extract-stdin) happen in the client, which
decodes exactly as the extractor's CLI does (universal newlines, strict
UTF-8) and sends the text as the ``arg`` of an ``extract`` request.

Before it starts the child, the client resets SIGCHLD to its default
disposition (reset_sigchld), because an ignored SIGCHLD, inherited across
exec from the caller, makes the kernel reap the child as it ends, so its
exit status is lost; when the reset fails, the client exits 16 and starts no
child. The extractor runs as ``sys.executable -I skill-release-date.py
--json`` with an empty environment, its own directory as the working
directory and a session of its own. The request is its stdin and its stdout
and stderr go to temporary files, so the client never blocks on a pipe and
reads only a bounded part of each (RESULT_LIMIT plus
ECHO_BYTES_PER_CHARACTER bytes for each character of the request values,
and STDERR_LIMIT). While the child runs, an ordinary write cannot grow any
file it writes past its cap: output_cap(limit) bytes, one byte past the
larger read bound, or a lower file size limit the caller set, soft or hard
(applied_cap). The cap is RLIMIT_FSIZE, set in the child before exec as
both its soft and its hard limit, so a child without CAP_SYS_RESOURCE
cannot raise it, and an extractor that writes too much by accident cannot
fill temporary storage within the timeout. After the wait, a child whose
stdout or stderr has a final size that reached that cap, including a
lower limit the caller set, is unavailable, and the reason names that
cap. The client
waits for the child with a non-blocking
waitpid (wait_child), at most CHILD_TIMEOUT_SECONDS, and exits 16 when the
wait reports that the child is no longer its child, since its exit status
is then lost (Popen.wait would read that as exit 0). With SIGCHLD at its
default and no other reaper in the client, a child that has not been
reaped by the client is still a zombie or running, so on a timeout the
client kills the process group of the child, whose group id cannot have
been reused, and then reaps the child, waiting at most REAP_GRACE_SECONDS
for it to end;
a child that a kill does not end within that grace is left unreaped and the
client exits 16, naming that. Residuals: after a normal end the group is not
killed, because without a wait that leaves the child unreaped (not
available on every platform the maintainer tools run on) a kill after the
reap could reach a reused id, so a process the extractor starts can outlive
a normal end; a process that leaves the group can outlive a timeout; a
signal that ends the client while it waits leaves the child to run on;
RLIMIT_FSIZE bounds the logical size of a file, not the storage allocated
to it, so deliberate child code can reserve disk blocks past the end of a
file (with fallocate, for example) without growing it; the check reads only
the final size, so a child that fills stdout to the cap, truncates it and
writes a valid reply is accepted; a child, or a process it starts, that
holds CAP_SYS_RESOURCE (as a client run as root gives it) can raise the
hard limit and then the soft one, so the cap does not bound it; and the
stdin file is bounded the same
way but not checked, so a child that fills it and still replies validly
keeps its verdict. The
extractor starts no process, so none of these arises from the extractor as
it is.

The contract (CONTRACT, REQUEST_KEYS, REPLY_KEYS) extends the one in
``tools/check-release-checksum-live.py``, rule for rule, with the ops and the
``refused`` outcome the shell callers need; tests pin the two equal on the
ops they share and REQUEST_KEYS equal to the extractor's JSON_REQUEST_KEYS.

The client runs on Python 3.9 and later and uses only the standard library.
"""

from __future__ import annotations

import io
import json
import os
import re
import resource
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROG = "skill-release-date-client"
TOOL_PROG = "skill-release-date"
RELEASE_DATE_TOOL = Path(__file__).resolve().parent / "skill-release-date.py"

# The bounds on one extractor child, equal to the gate's. After a timeout
# kill, the client waits at most REAP_GRACE_SECONDS to see the child end.
CHILD_TIMEOUT_SECONDS = 20
REAP_GRACE_SECONDS = 5
RESULT_LIMIT = 65536
ECHO_BYTES_PER_CHARACTER = 12
STDERR_LIMIT = 4096

# The exit code of an internal failure of the extractor itself.
EXTRACTOR_INTERNAL_ERROR = 6

EXIT_USAGE = 2
EXIT_MALFORMED = 11
EXIT_ABSENT = 13
EXIT_UNREADABLE = 14
EXIT_REFUSED = 15
EXIT_UNAVAILABLE = 16

DAY_FORM = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
BASELINE_FORM = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


def _is_day(value) -> bool:
    return type(value) is str and DAY_FORM.fullmatch(value) is not None


def _is_flag(value) -> bool:
    return type(value) is bool


def _is_version(value) -> bool:
    return type(value) is str and BASELINE_FORM.fullmatch(value) is not None


# For each op: the check its value must pass, what that check requires (for
# the report), and the outcomes the op may reply with.
CONTRACT = {
    "extract": (_is_day, "a YYYY-MM-DD string", ("value", "absent", "malformed")),
    "requires_release_date": (_is_flag, "a JSON true or false", ("value", "malformed")),
    "release_day_from_published_at": (_is_day, "a YYYY-MM-DD string", ("value", "malformed")),
    "baseline": (_is_version, "a bare X.Y.Z version string", ("value",)),
    "parse_date": (_is_day, "a YYYY-MM-DD string", ("value", "malformed")),
    "publish_window": (_is_day, "a YYYY-MM-DD string", ("value", "malformed", "refused")),
    "confirm_published": (_is_day, "a YYYY-MM-DD string", ("value", "malformed", "refused")),
}

# The keys of each request beside "op".
REQUEST_KEYS = {
    "extract": ("arg",),
    "requires_release_date": ("arg",),
    "release_day_from_published_at": ("arg",),
    "baseline": (),
    "parse_date": ("arg",),
    "publish_window": ("expected", "now"),
    "confirm_published": ("expected", "published_at"),
}

# The exact key set of a reply with each outcome.
REPLY_KEYS = {
    "value": frozenset({"op", "outcome", "value"}),
    "absent": frozenset({"op", "outcome"}),
    "malformed": frozenset({"op", "outcome", "message"}),
    "refused": frozenset({"op", "outcome", "message"}),
}

# word -> (op, argument names). extract-file and extract-stdin read their
# input in the client and send it as the arg of an extract request.
GRAMMAR = {
    "baseline": ("baseline", ()),
    "extract-file": ("extract", ("PATH",)),
    "extract-stdin": ("extract", ()),
    "requires-date": ("requires_release_date", ("VERSION",)),
    "check-date": ("parse_date", ("VALUE",)),
    "published-day": ("release_day_from_published_at", ("PUBLISHED_AT",)),
    "publish-window": ("publish_window", ("EXPECTED", "NOW")),
    "confirm-published": ("confirm_published", ("EXPECTED", "PUBLISHED_AT")),
}

USAGE = f"usage: {PROG} " + " | ".join(
    " ".join((word, *names)) for word, (_op, names) in GRAMMAR.items()
)


class Usage(Exception):
    """The arguments do not name one word with exactly its arguments."""


class Unreadable(Exception):
    """The input could not be read (the CLI's exit 4)."""


class Malformed(Exception):
    """The input is not valid UTF-8 (the CLI's exit 1)."""


class Unavailable(Exception):
    """The extractor did not deliver a reply that meets the contract."""

    def __init__(self, reason: str, printed: bytes = b""):
        super().__init__(reason)
        self.reason = reason
        self.printed = printed


class ContractError(Exception):
    """A reply that breaks the contract, with the reason the report names."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class _RepeatedKey(Exception):
    """A JSON object in a reply names one key more than once."""


def _object_without_repeated_keys(pairs: list) -> dict:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise _RepeatedKey()
    return dict(pairs)


def build_request(op: str, fields: dict) -> bytes:
    """The request for ``op`` with ``fields``, as ASCII JSON."""
    if op not in REQUEST_KEYS or set(fields) != set(REQUEST_KEYS[op]):
        raise ValueError(f"a request for {op} takes exactly the keys {REQUEST_KEYS.get(op)}")
    return json.dumps({"op": op, **fields}, ensure_ascii=True).encode("ascii")


def check_reply(op: str, data: bytes, limit: int) -> dict:
    """Return the reply in ``data`` for ``op`` once it meets the contract;
    raise ContractError otherwise."""
    if len(data) > limit:
        raise ContractError(f"printed more than {limit} bytes")

    def breach(rule: str) -> ContractError:
        return ContractError(f"printed a result that does not match the contract ({rule})")

    try:
        reply = json.loads(data.decode("ascii"), object_pairs_hook=_object_without_repeated_keys)
    except _RepeatedKey:
        raise breach("a key appears more than once") from None
    except (ValueError, RecursionError):
        raise ContractError("did not print a JSON result") from None
    if type(reply) is not dict:
        raise breach("not a JSON object")
    outcome = reply.get("outcome")
    if type(outcome) is not str or outcome not in REPLY_KEYS:
        raise breach("its outcome is not value, absent, malformed, or refused")
    if set(reply) != REPLY_KEYS[outcome]:
        raise breach(f"a result with outcome {outcome} has exactly the keys {', '.join(sorted(REPLY_KEYS[outcome]))}")
    if type(reply["op"]) is not str or reply["op"] != op:
        raise breach(f"it answers an op other than {op}")
    check, expected, outcomes = CONTRACT[op]
    if outcome not in outcomes:
        raise breach(f"{outcome} is not a result of {op}")
    if outcome == "value" and not check(reply["value"]):
        raise breach(f"the value is not {expected}")
    if outcome in ("malformed", "refused") and type(reply["message"]) is not str:
        raise breach("the message is not a string")
    return reply


def output_cap(limit: int) -> int:
    """The size limit, in bytes, on each file the child writes, under
    ordinary writes: one byte past the larger of the two read bounds
    (``limit + 1`` bytes of stdout and STDERR_LIMIT bytes of stderr), so a
    reply one byte too long is still read and refused as too long, and an
    ordinary write that would grow a file past the cap fails. It does not
    bound a file already larger than the cap, which the child can write
    within, or storage reserved past the end of a file."""
    return max(limit + 1, STDERR_LIMIT) + 1


def applied_cap(cap: int) -> int:
    """The file size limit the child gets, as both its soft and its hard
    limit: the lowest of ``cap``, a finite inherited soft limit and a
    finite inherited hard limit. A lower soft limit the caller set is kept
    for the child rather than raised, and a lower hard limit is one that a
    process without CAP_SYS_RESOURCE cannot raise."""
    soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    for inherited in (soft, hard):
        if inherited != resource.RLIM_INFINITY and inherited < cap:
            cap = inherited
    return cap


def reset_sigchld() -> None:
    """Reset SIGCHLD to its default disposition before the client starts the
    child. An ignored SIGCHLD, inherited across exec from the caller, makes
    the kernel reap the child as it ends, so its exit status is lost.
    Raises Unavailable when the disposition cannot be reset, as in a thread
    other than the main thread (ValueError) or on an OSError."""
    try:
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    except (OSError, ValueError) as error:
        raise Unavailable(
            f"could not be run safely (SIGCHLD could not be reset to its default disposition: "
            f"{type(error).__name__}: {error}), so its exit status could be lost"
        ) from None


def wait_child(proc: subprocess.Popen, timeout: float) -> bool:
    """Wait up to ``timeout`` seconds for the child ``proc`` to end, with a
    non-blocking waitpid and a short sleep, and reap it when it has ended,
    setting ``proc.returncode``. Returns True when the child has ended and
    False on a timeout, leaving it unreaped. Raises Unavailable when the wait
    reports that the child is no longer a child of the client
    (ChildProcessError): its exit status is then lost, and Popen.wait would
    read that as exit 0."""
    deadline = time.monotonic() + timeout
    delay = 0.0005
    while True:
        try:
            pid, status = os.waitpid(proc.pid, os.WNOHANG)
        except ChildProcessError:
            raise Unavailable(
                "could not be waited for (it is no longer a child of the client, so its exit status is lost)"
            ) from None
        if pid == proc.pid:
            proc.returncode = os.waitstatus_to_exitcode(status)
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        delay = min(delay * 2, remaining, 0.05)
        time.sleep(delay)


def run_extractor(op: str, fields: dict, timeout: float = CHILD_TIMEOUT_SECONDS, tool: Path | None = None) -> dict:
    """Run the extractor once for ``op`` with ``fields`` (see the module
    docstring) and return its reply once it meets the contract; raise
    Unavailable otherwise."""
    tool = RELEASE_DATE_TOOL if tool is None else tool
    executable = sys.executable
    if not executable or not os.path.isabs(executable):
        raise Unavailable(f"could not run (the interpreter path {executable!r} is not absolute)")
    request = build_request(op, fields)
    limit = RESULT_LIMIT + ECHO_BYTES_PER_CHARACTER * sum(len(value) for value in fields.values())
    reset_sigchld()
    try:
        cap = applied_cap(output_cap(limit))

        def limit_output() -> None:
            # Runs in the child, before exec: an ordinary write cannot grow a
            # file past cap, and with the hard limit set to cap too, a child
            # without CAP_SYS_RESOURCE cannot raise it.
            resource.setrlimit(resource.RLIMIT_FSIZE, (cap, cap))

        with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as stdout, \
                tempfile.TemporaryFile() as stderr:
            stdin.write(request)
            stdin.seek(0)
            try:
                proc = subprocess.Popen(
                    [executable, "-I", str(tool), "--json"],
                    stdin=stdin, stdout=stdout, stderr=stderr, env={},
                    cwd=tool.parent, start_new_session=True, preexec_fn=limit_output,
                )
            except OSError as error:
                raise Unavailable(f"could not run ({type(error).__name__}: {error})") from None
            ended = wait_child(proc, timeout)
            if not ended:
                # The child is not reaped yet, so its group id is still its own.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                if not wait_child(proc, REAP_GRACE_SECONDS):
                    # A child that a kill does not end (for example one in an
                    # uninterruptible sleep) is left unreaped rather than
                    # waited for without a bound.
                    raise Unavailable(
                        f"could not be reaped (the client saw no end of it within "
                        f"{REAP_GRACE_SECONDS} seconds after its kill)"
                    )
            stderr.seek(0)
            printed = stderr.read(STDERR_LIMIT)
            stdout.seek(0)
            data = stdout.read(limit + 1)
            capped = [name for name, handle in (("stdout", stdout), ("stderr", stderr))
                      if os.fstat(handle.fileno()).st_size >= cap]
    except Unavailable:
        raise
    except Exception as error:
        raise Unavailable(f"could not be run, waited for, or read ({type(error).__name__}: {error})") from None
    if capped:
        raise Unavailable(f"wrote {' and '.join(capped)} up to the output cap of {cap} bytes", printed)
    code = proc.returncode
    if not ended:
        raise Unavailable(f"was not seen to end within {timeout} seconds", printed)
    if code < 0:
        try:
            name = signal.Signals(-code).name
        except ValueError:
            name = str(-code)
        raise Unavailable(f"was killed by signal {name}", printed)
    if code == EXTRACTOR_INTERNAL_ERROR:
        raise Unavailable("failed unexpectedly (internal error)", printed)
    if code != 0:
        raise Unavailable(f"exited {code}", printed)
    try:
        return check_reply(op, data, limit)
    except ContractError as error:
        raise Unavailable(error.reason, printed) from None


def read_input(path: str | None) -> str:
    """Read ``path``, or all of stdin when it is None, and decode it exactly
    as the extractor's CLI does."""
    where = "standard input" if path is None else path
    try:
        if path is None:
            data = sys.stdin.buffer.read()
        else:
            data = Path(path).read_bytes()
    except OSError as error:
        raise Unreadable(f"could not read {where}: {error}") from None
    try:
        return io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", newline=None).read()
    except UnicodeDecodeError as error:
        raise Malformed(f"{where} is not valid UTF-8: {error}") from None


def parse_argv(argv: list) -> tuple:
    """Return (word, op, values) for ``argv``, or raise Usage."""
    args = argv[1:]
    if not args or args[0] not in GRAMMAR:
        raise Usage()
    word = args[0]
    op, names = GRAMMAR[word]
    if len(args) - 1 != len(names):
        raise Usage()
    return word, op, args[1:]


def verdict(message: str, code: int) -> int:
    print(f"{TOOL_PROG}: {message}", file=sys.stderr)
    return code


def main(argv: list) -> int:
    try:
        word, op, values = parse_argv(argv)
    except Usage:
        print(f"{PROG}: {USAGE}", file=sys.stderr)
        return EXIT_USAGE
    try:
        if word == "extract-file":
            fields = {"arg": read_input(values[0])}
        elif word == "extract-stdin":
            fields = {"arg": read_input(None)}
        else:
            fields = dict(zip(REQUEST_KEYS[op], values))
    except Unreadable as error:
        return verdict(str(error), EXIT_UNREADABLE)
    except Malformed as error:
        return verdict(str(error), EXIT_MALFORMED)
    try:
        reply = run_extractor(op, fields)
    except Unavailable as error:
        message = f"{PROG}: {RELEASE_DATE_TOOL.name} {error.reason} in {op}, so the extractor is unavailable"
        lines = error.printed.decode("utf-8", errors="replace").splitlines()
        shown = " | ".join(line.strip() for line in lines if line.strip())
        if shown:
            message += f"; it printed: {shown}"
        print(message, file=sys.stderr)
        return EXIT_UNAVAILABLE
    outcome = reply["outcome"]
    if outcome == "malformed":
        return verdict(reply["message"], EXIT_MALFORMED)
    if outcome == "refused":
        return verdict(reply["message"], EXIT_REFUSED)
    if outcome == "absent":
        return verdict("no Released: line found", EXIT_ABSENT)
    value = reply["value"]
    if type(value) is bool:
        print("required" if value else "optional")
    else:
        print(value)
    return 0


if __name__ == "__main__":
    try:
        code = main(sys.argv)
    except SystemExit:
        raise
    except Exception as error:  # a failure of the client machinery is never a verdict
        print(
            f"{PROG}: {RELEASE_DATE_TOOL.name} could not be run, waited for, or read "
            f"({type(error).__name__}: {error}), so the extractor is unavailable",
            file=sys.stderr,
        )
        code = EXIT_UNAVAILABLE
    sys.exit(code)
