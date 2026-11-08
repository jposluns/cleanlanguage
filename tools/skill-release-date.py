#!/usr/bin/env python3
"""Extract the strict Clean Language skill release date, the one shared way.

This is the single strict extractor for the ``Released:`` line in
``cleanlanguage/skills/cleanlanguage/SKILL.md`` and in the four portable
renderings under ``site/downloads/``. It is the sibling of
``tools/skill-version.py`` and reads the content the same way: a
universal-newline text read, so a ``CRLF`` or a lone ``CR`` line ending agrees,
and a ``NUL`` byte is preserved (and so rejected) rather than stripped.

The field (item 26) is one meta line, directly after the ``Version:`` line:

    Released: YYYY-MM-DD

meaning the UTC calendar day on which the matching GitHub Release was first
published. The rules, all enforced here so every caller agrees:

  - A line looks like a ``Released:`` key when, once every Unicode format
    character (category ``Cf``, for example a zero-width space or a byte
    order mark) is removed from it, it starts with ``released`` in any case,
    optionally behind any run of leading whitespace and Markdown markers
    (``>``, ``#``, ``*``, ``_``, ``+``, ``-``, a table pipe ``|``, an opening
    bracket ``[``, or an ordered-list number followed by ``.`` or ``)``), and
    the word is followed by optional blanks or emphasis markers (``*``,
    ``_``) and then a colon, either ``:`` or the full-width colon ``U+FF1A``.
    A key-like line decorated in any other way, for example inside inline
    code or an HTML tag, is not detected.
  - The first line that looks like a ``Released:`` key is authoritative. It must
    be spelled exactly ``Released:`` and match
    ``Released:[ \\t]*YYYY-MM-DD[ \\t]*``; a malformed first line is rejected,
    never skipped to a later well-formed one.
  - The value must be a real calendar date (``datetime.date.fromisoformat``).
  - The line must be the line immediately after the first ``Version:`` line.
  - A second line that looks like a ``Released:`` key, anywhere and however it
    is decorated within the rule above, is rejected, so a stale copy cannot
    survive beside a fresh one.
  - Absent (no line looks like a ``Released:`` key) is a distinct outcome from
    malformed, because absence is legitimate at or below the baseline version.

The baseline is declared once, here: ``1.0.14`` is the last release that carries
no date. Callers require the line when the skill version sorts above it and
accept it absent at or below it.

Input modes:
  ``FILE`` reads that file; ``-`` or no argument reads all of stdin (so a
  producer piped in completes and can take no ``SIGPIPE``).
  ``--baseline`` prints the baseline version. Shell callers, through
  ``tools/skill-release-date-client.py``, ask for it first as an availability
  probe, so a missing or broken extractor is named as that before any content
  is judged; what tells a content verdict from a failure is the ``--json``
  contract the client checks, not the probe.
  ``--requires-date VERSION`` prints ``required`` when ``VERSION`` sorts above
  the baseline (compared numerically, part by part, so ``1.0.100`` is above
  ``1.0.14`` and ``1.00.14`` equals it) and ``optional`` otherwise. Every
  baseline comparison uses this one rule; no caller re-implements it. A part
  with more digits than the interpreter converts to an integer
  (``sys.get_int_max_str_digits``) is malformed; an interpreter without that
  function has no such limit, so there every part compares.
  ``--check-date VALUE`` validates a bare ``YYYY-MM-DD`` calendar date and
  prints it.
  ``--published-day VALUE`` prints the UTC day of a release ``published_at``
  value; see ``release_day_from_published_at`` for the assumption it carries.
  ``--publish-window EXPECTED NOW`` checks, immediately before a release is
  created, that the UTC instant ``NOW`` (``YYYY-MM-DDTHH:MM:SSZ``, read from
  the clock by the caller) falls on the day ``EXPECTED`` with at least
  ``PUBLISH_MARGIN_SECONDS`` left before UTC midnight, and prints
  ``EXPECTED``; otherwise it refuses with exit 5.
  ``--confirm-published EXPECTED PUBLISHED_AT`` checks, after a release is
  created, that its ``published_at`` falls on the day ``EXPECTED`` and prints
  that day; a different day is refused with exit 5, naming both days.
  ``--json`` reads one JSON request object from stdin and prints one JSON
  reply object. Its callers are ``tools/check-release-checksum-live.py`` and
  ``tools/skill-release-date-client.py``, which every shell caller runs; each
  runs this file as a separate ``python3 -I`` child. The request is
  ``{"op": "baseline"}``; ``{"op": OP, "arg": TEXT}`` for the ops
  ``extract`` (``TEXT`` is the content as read with universal newlines, as
  the gate reads it with ``Path.read_text``; it is passed to ``extract``
  unchanged, so a ``CR`` left in it is part of its line, not a line ending),
  ``requires_release_date`` (``TEXT`` is a version),
  ``release_day_from_published_at`` (``TEXT`` is a ``published_at`` value)
  and ``parse_date`` (``TEXT`` is a day, as for ``--check-date``);
  ``{"op": "publish_window", "expected": DAY, "now": INSTANT}``, as for
  ``--publish-window``; or ``{"op": "confirm_published", "expected": DAY,
  "published_at": INSTANT}``, as for ``--confirm-published``; with no other
  key and every value a string (``JSON_REQUEST_KEYS``). The reply echoes
  ``op`` and carries ``outcome``: ``value`` with ``value`` (a day, a JSON
  ``true`` or ``false``, or the baseline version), ``absent`` with no further
  key (``extract`` only: no line looks like the key), ``malformed`` with
  ``message`` (the text of the ``Malformed`` verdict), or ``refused`` with
  ``message`` (``publish_window`` and ``confirm_published`` only: the text
  the CLI prints with exit 5). It is printed as ASCII JSON with sorted keys
  and one trailing newline. This mode is designed to exit 0 when it has
  delivered a reply, whatever its outcome, 2 on a bad request, and 6 on an
  internal error; any other exit, whatever its cause, is a failure of the
  child too, and each caller reads every exit other than 0 as a failure of
  the child, whatever stdout holds.

Exit codes:
  0  success; the requested value is printed to stdout
  1  malformed line or value, or the input is not valid UTF-8
  2  usage error
  3  absent: no ``Released:`` line
  4  could not evaluate: the input file could not be read
  5  refused: a well-formed value that names the wrong day
     (``--publish-window``, ``--confirm-published``)
  6  the extractor itself failed unexpectedly (an internal error); every
     caller reports this as the extractor failing, never as a content verdict
     or as unreadable input
  Under ``--json``, 0 means a reply was delivered, 2 a bad request, and 6 an
  internal error (see Input modes).
"""

from __future__ import annotations

import datetime
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

PROG = "skill-release-date"

# Item 26: 1.0.14 is the last undated release. The Released line is required
# when the skill version sorts above this and accepted absent at or below it.
BASELINE_VERSION = "1.0.14"

# Item 26 (G3): the release workflow refuses to start publishing when fewer
# than this many seconds remain in the UTC day, so the creation of the release
# and its asset uploads cannot slip past midnight onto a later day than the
# Released line names.
PUBLISH_MARGIN_SECONDS = 600

# Any line that looks like the key, whatever its case, leading whitespace or
# leading Markdown markers (a table pipe and an opening bracket among them),
# and with an ASCII or a full-width colon, matched after format characters are
# removed (see looks_like_key). The first such line is the authoritative one;
# if it is not spelled exactly "Released:" it is malformed, never read as
# absent.
RELEASED_KEY_LIKE = re.compile(r"(?:\s|[>#*_+|\[-]|[0-9]+[.)])*released(?:[ \t]|[*_])*[:\uff1a]", re.IGNORECASE)

# Item 26: the exit code for an internal failure of the extractor itself,
# distinct from 4 (the input could not be read).
INTERNAL_ERROR_EXIT = 6
RELEASED_LINE = re.compile(r"Released:[ \t]*([0-9]{4}-[0-9]{2}-[0-9]{2})[ \t]*")
DATE_FORM = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
BARE_VERSION = re.compile(r"([0-9]+)\.([0-9]+)\.([0-9]+)")
PUBLISHED_AT_FORM = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2})T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
VERSION_LINE = re.compile(r"Version:[ \t]*[0-9]+\.[0-9]+\.[0-9]+[ \t]*")


class Malformed(ValueError):
    """A Released line or value that breaks the strict grammar."""


class Refused(ValueError):
    """A well-formed value that names the wrong day: exit 5 in the CLI, the
    ``refused`` outcome under ``--json``. Not a ``Malformed``."""


def looks_like_key(line: str) -> bool:
    """True when ``line`` looks like a Released key under the module rule:
    format characters (category ``Cf``) are removed first, so an invisible
    zero-width character cannot hide a stale copy."""
    visible = "".join(ch for ch in line if unicodedata.category(ch) != "Cf")
    return RELEASED_KEY_LIKE.match(visible) is not None


def parse_date(value: str) -> str:
    """Return ``value`` if it is a bare ``YYYY-MM-DD`` real calendar date."""
    if not isinstance(value, str) or DATE_FORM.fullmatch(value) is None:
        raise Malformed(f"not a bare YYYY-MM-DD date: {value!r}")
    try:
        datetime.date.fromisoformat(value)
    except ValueError as error:
        raise Malformed(f"not a real calendar date: {value!r} ({error})") from None
    return value


def extract(text: str) -> str | None:
    """Return the Released date in ``text``, or None when no line carries the key.

    ``text`` is already decoded with universal newlines. Raises ``Malformed``
    on any breach of the grammar in the module docstring.
    """
    lines = text.split("\n")
    keyed = [i for i, line in enumerate(lines) if looks_like_key(line)]
    if not keyed:
        return None
    first = keyed[0]
    line = lines[first]
    if not line.startswith("Released:"):
        raise Malformed(f"the first Released line is not spelled exactly Released: {line!r}")
    match = RELEASED_LINE.fullmatch(line)
    if match is None:
        raise Malformed(f"the first Released line is not a bare YYYY-MM-DD date: {line!r}")
    value = parse_date(match.group(1))
    if len(keyed) > 1:
        numbers = ", ".join(str(i + 1) for i in keyed)
        raise Malformed(f"more than one Released line (lines {numbers})")
    version_index = next((i for i, l in enumerate(lines) if l.startswith("Version:")), None)
    if version_index is None:
        raise Malformed("a Released line is present but there is no Version: line")
    # The Version line the Released line hangs from must itself be a bare
    # X.Y.Z, checked before the placement rule, so a date is never accepted
    # beside a malformed version.
    if VERSION_LINE.fullmatch(lines[version_index]) is None:
        raise Malformed(
            f"the first Version: line (line {version_index + 1}) is not a bare X.Y.Z "
            f"version: {lines[version_index]!r}"
        )
    if first != version_index + 1:
        raise Malformed(
            f"the Released line (line {first + 1}) is not the line directly after "
            f"the first Version: line (line {version_index + 1})"
        )
    return value


def version_key(version: str) -> tuple[int, int, int]:
    match = BARE_VERSION.fullmatch(version)
    if match is None:
        raise Malformed(f"not a bare X.Y.Z version: {version!r}")
    # int() raises a ValueError for a digit run longer than the interpreter's
    # limit, which would read as an internal error. The limit is read here at
    # run time because an interpreter flag can lower it; 0 means no limit. An
    # interpreter without sys.get_int_max_str_digits (Python 3.9 before 3.9.14,
    # 3.10 before 3.10.7) has no limit, and the client, which runs this file
    # with its own interpreter, supports Python 3.9 and later.
    get_limit = getattr(sys, "get_int_max_str_digits", None)
    limit = 0 if get_limit is None else get_limit()
    if limit and any(len(part) > limit for part in match.groups()):
        raise Malformed(f"a part of the version has more than {limit} digits: {version!r}")
    return tuple(int(part) for part in match.groups())


def requires_release_date(version: str) -> bool:
    """True when ``version`` sorts above the baseline, so the line is required."""
    return version_key(version) > version_key(BASELINE_VERSION)


def release_day_from_published_at(value: str) -> str:
    """Return the UTC calendar day (``YYYY-MM-DD``) of a release ``published_at``.

    UNVERIFIED ASSUMPTION (item 26). This function is the one place the release
    tooling relies on the meaning of the GitHub REST API ``published_at`` field of
    a release record. It assumes that the field:

      - is the UTC instant at which the release was FIRST published, in the
        form ``YYYY-MM-DDTHH:MM:SSZ``;
      - is fixed at first publication, so a re-run still reports the
        original publication instant (the release workflow has no path
        that re-uploads the assets of a published release, which is
        immutable);
      - is null for a draft (``gh api --jq .published_at`` then prints
        ``null``, which is rejected here, failing closed).

    That assumption has not been corroborated against the API documentation or
    a probe of a live release record. Both the release-time check (G3, in
    ``.github/workflows/release-skill.yml``) and the post-release comparison
    (G4, in ``tools/check-release-checksum-live.py``) reach ``published_at`` only
    through this function, so if the assumption is refuted the fix is here and
    in the field each caller reads, nowhere else.

    Raises ``Malformed`` for any value not in exactly that form, including a
    null, an offset other than ``Z``, fractional seconds, or an impossible date
    or time.
    """
    return parse_instant(value, "published_at").date().isoformat()


def parse_instant(value: str, what: str) -> datetime.datetime:
    """Return the UTC instant ``value`` (exactly ``YYYY-MM-DDTHH:MM:SSZ``)."""
    if not isinstance(value, str):
        raise Malformed(f"{what} is not a string: {value!r}")
    if PUBLISHED_AT_FORM.fullmatch(value) is None:
        raise Malformed(f"{what} is not a YYYY-MM-DDTHH:MM:SSZ instant: {value!r}")
    try:
        instant = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise Malformed(f"{what} is not a real instant: {value!r} ({error})") from None
    return instant.replace(tzinfo=datetime.timezone.utc)


def publish_window_problem(expected: str, now: datetime.datetime) -> str | None:
    """Why publishing must not start at ``now`` for a release dated ``expected``.

    None when ``now`` falls on the UTC day ``expected`` with at least
    ``PUBLISH_MARGIN_SECONDS`` left before the next UTC midnight."""
    today = now.date().isoformat()
    if today != expected:
        return (
            f"the UTC day is now {today} ({now:%Y-%m-%dT%H:%M:%SZ}), not {expected}, "
            f"the day the Released line names"
        )
    # Counted from the time of day, never from the next date, which does not
    # exist after 9999-12-31. Exact because parse_instant yields whole seconds.
    remaining = 86400 - (now.hour * 3600 + now.minute * 60 + now.second)
    if remaining < PUBLISH_MARGIN_SECONDS:
        left = "1 second remains" if remaining == 1 else f"{remaining} seconds remain"
        return (
            f"only {left} in the UTC day {expected} "
            f"({now:%Y-%m-%dT%H:%M:%SZ}); publishing is refused within "
            f"{PUBLISH_MARGIN_SECONDS // 60} minutes of UTC midnight, so the release "
            f"cannot land on a later day than its Released line names"
        )
    return None


def publish_window_verdict(expected_text: str, now_text: str) -> str:
    """Return ``expected_text`` once publishing may start at ``now_text``;
    raise ``Malformed`` for a bad day or instant and ``Refused`` otherwise."""
    expected = parse_date(expected_text)
    now = parse_instant(now_text, "the current instant")
    problem = publish_window_problem(expected, now)
    if problem is not None:
        raise Refused(f"refusing to start publishing: {problem}")
    return expected


def confirm_published_verdict(expected_text: str, published_at: str) -> str:
    """Return the UTC day of ``published_at`` once it is ``expected_text``;
    raise ``Malformed`` for a bad value and ``Refused`` for another day."""
    expected = parse_date(expected_text)
    day = release_day_from_published_at(published_at)
    if day != expected:
        raise Refused(
            f"the release was published on {day} (UTC; published_at {published_at}), "
            f"but its Released line names {expected}"
        )
    return day


def die(message: str, code: int = 1):
    print(f"{PROG}: {message}", file=sys.stderr)
    raise SystemExit(code)


def read_universal(source: str | None) -> str:
    """Read ``source`` (a path, or stdin for ``-``/None) with universal newlines,
    byte-identical to ``Path.read_text(encoding="utf-8")``."""
    where = "standard input" if source in (None, "-") else source
    try:
        if source in (None, "-"):
            data = sys.stdin.buffer.read()
        else:
            data = Path(source).read_bytes()
    except OSError as error:
        die(f"could not read {where}: {error}", 4)
    try:
        return io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", newline=None).read()
    except UnicodeDecodeError as error:
        die(f"{where} is not valid UTF-8: {error}")


USAGE = (
    f"usage: {PROG} [FILE|-] | --baseline | --requires-date VERSION"
    f" | --check-date YYYY-MM-DD | --published-day PUBLISHED_AT"
    f" | --publish-window YYYY-MM-DD NOW | --confirm-published YYYY-MM-DD PUBLISHED_AT"
    f" | --json"
)

# Row 80: the ops of the --json mode, named after the functions they run,
# each with the exact keys of its request beside "op". Row 89 added
# parse_date, publish_window and confirm_published for the shell callers.
JSON_REQUEST_KEYS = {
    "extract": ("arg",),
    "requires_release_date": ("arg",),
    "release_day_from_published_at": ("arg",),
    "baseline": (),
    "parse_date": ("arg",),
    "publish_window": ("expected", "now"),
    "confirm_published": ("expected", "published_at"),
}
JSON_OPS = tuple(JSON_REQUEST_KEYS)


def json_main() -> int:
    """Answer one JSON request from stdin with one JSON reply on stdout (see
    ``--json`` in the module docstring). A bad request exits 2 with nothing on
    stdout; only ``Malformed``, or a subclass of it, is a ``malformed``
    reply, as in every other mode, only ``Refused`` is a ``refused`` reply
    (the exit 5 of the CLI), and an Exception that the internal-error
    guard catches exits 6 instead of a reply. Each op is answered by its own
    branch, and an op in JSON_OPS that no branch answers raises such an
    Exception, so it is never answered as another op. The mode is designed
    to exit 0, 2, or 6; any other exit, or any other end of the child,
    whatever its cause, is a failure of the child, which the gate treats as
    such."""
    data = sys.stdin.buffer.read()
    try:
        request = json.loads(data.decode("utf-8"))
    except (ValueError, RecursionError) as error:
        die(f"--json: the request is not a UTF-8 JSON value: {error}", 2)
    if type(request) is not dict:
        die("--json: the request is not a JSON object", 2)
    op = request.get("op")
    if type(op) is not str or op not in JSON_OPS:
        die(f"--json: the request names no known op: {op!r}", 2)
    fields = JSON_REQUEST_KEYS[op]
    keys = {"op", *fields}
    if set(request) != keys:
        die(f"--json: a request for {op} has exactly the keys {', '.join(sorted(keys))}", 2)
    for key in fields:
        if type(request[key]) is not str:
            die(f"--json: the {key} of a request for {op} is not a string", 2)
    arg = request.get("arg")
    reply = {"op": op}
    try:
        if op == "baseline":
            value = BASELINE_VERSION
        elif op == "extract":
            value = extract(arg)
        elif op == "requires_release_date":
            value = requires_release_date(arg)
        elif op == "release_day_from_published_at":
            value = release_day_from_published_at(arg)
        elif op == "parse_date":
            value = parse_date(arg)
        elif op == "publish_window":
            value = publish_window_verdict(request["expected"], request["now"])
        elif op == "confirm_published":
            value = confirm_published_verdict(request["expected"], request["published_at"])
        else:
            raise RuntimeError(f"--json: no branch answers the op {op!r}")
    except Malformed as error:
        reply["outcome"] = "malformed"
        reply["message"] = str(error)
    except Refused as error:
        reply["outcome"] = "refused"
        reply["message"] = str(error)
    else:
        if value is None:
            reply["outcome"] = "absent"
        else:
            reply["outcome"] = "value"
            reply["value"] = value
    print(json.dumps(reply, ensure_ascii=True, sort_keys=True))
    return 0


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args == ["--json"]:
        return json_main()
    if args == ["--baseline"]:
        print(BASELINE_VERSION)
        return 0
    if len(args) == 2 and args[0] == "--requires-date":
        try:
            required = requires_release_date(args[1])
        except Malformed as error:
            die(str(error))
        print("required" if required else "optional")
        return 0
    if len(args) == 3 and args[0] == "--publish-window":
        try:
            expected = publish_window_verdict(args[1], args[2])
        except Malformed as error:
            die(str(error))
        except Refused as error:
            die(str(error), 5)
        print(expected)
        return 0
    if len(args) == 3 and args[0] == "--confirm-published":
        try:
            day = confirm_published_verdict(args[1], args[2])
        except Malformed as error:
            die(str(error))
        except Refused as error:
            die(str(error), 5)
        print(day)
        return 0
    if len(args) == 2 and args[0] in ("--check-date", "--published-day"):
        try:
            if args[0] == "--check-date":
                value = parse_date(args[1])
            else:
                value = release_day_from_published_at(args[1])
        except Malformed as error:
            die(str(error))
        print(value)
        return 0
    if len(args) > 1 or (args and args[0].startswith("--")):
        die(USAGE, 2)
    source = args[0] if args else None
    text = read_universal(source)
    try:
        value = extract(text)
    except Malformed as error:
        die(str(error))
    if value is None:
        die("no Released: line found", 3)
    print(value)
    return 0


if __name__ == "__main__":
    try:
        code = main(sys.argv)
    except SystemExit:
        raise
    except Exception as error:  # an internal failure has its own exit, never malformed or unreadable
        print(f"{PROG}: internal error: {error!r}", file=sys.stderr)
        code = INTERNAL_ERROR_EXIT
    sys.exit(code)
