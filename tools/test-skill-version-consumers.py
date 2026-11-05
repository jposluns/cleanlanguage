#!/usr/bin/env python3
"""Cross-consumer contract: the packager and the two release gates select and
validate the SKILL.md ``Version:`` line by the same rule.

The two gates (check-release-links.py, check-release-checksum-live.py) already
apply a strict rule: the first ``Version:`` line must be a bare ``X.Y.Z``. This
test pins that the packager (release-package.sh) selects and validates
identically, so a malformed first line fails in all three, and a clean version
still passes. It runs offline: the packager is exercised in a throwaway git
worktree, and the gates are exercised through their own compiled regexes.
The packager and the dry run read the Released line through
tools/skill-release-date-client.py (row 89), and each tells input the client
could not read (client exit 14) apart from an extractor that failed inside or
broke its contract (client exit 16), which is never read as malformed content;
the dry run read is exercised from the block extracted from its real script.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACKAGER = REPO / "tools" / "release-package.sh"
DRY_RUN = REPO / "tools" / "release-dry-run.sh"
RELEASE_DATE_TOOL = REPO / "tools" / "skill-release-date.py"
CLIENT = REPO / "tools" / "skill-release-date-client.py"

# Row 89: the extractor file name. Each caller reaches the extractor only
# through tools/skill-release-date-client.py, whose name does not contain
# it, so in a caller the lines that name it are only the messages and
# comments listed with the caller; any other line that names it, a launch
# in any form among them (any interpreter, quoted or not, any options, a
# continuation line, or the script run by its shebang), fails the launch
# test. Residual: a launch that builds the name from parts or reads it from
# a variable is not seen.
EXTRACTOR_NAME = 'skill-release-date.py'


def extractor_mentions(text: str) -> list:
    """Each line of ``text`` that names the extractor, once per mention."""
    return [line for line in text.split("\n") for _ in range(line.count(EXTRACTOR_NAME))]


# The forms a direct launch could take; each must fail the launch test.
LAUNCH_PROBES = (
    'python3 -X utf8 tools/skill-release-date.py --baseline',
    'python3 -I \\\n  tools/skill-release-date.py --baseline',
    'tools/skill-release-date.py --baseline',
    '"${PYTHON:-python3}" tools/skill-release-date.py --baseline',
    '"python3" tools/skill-release-date.py --baseline',
)

# Row 89: the client file name, checked the same way. In a caller, the
# lines that name it are only the comments and the launches listed with
# the caller, each launch exactly "python3 -I tools/skill-release-date-
# client.py" and its arguments, so any other line that names it fails:
# a launch without -I, with another interpreter word, quoted or from a
# variable, over a continuation line, by its shebang, or one more launch in
# the listed form. Residual: a launch that builds the name from parts or
# reads it from a variable is not seen.
CLIENT_NAME = 'skill-release-date-client.py'


def client_mentions(text: str) -> list:
    """Each line of ``text`` that names the client, once per mention."""
    return [line for line in text.split("\n") for _ in range(line.count(CLIENT_NAME))]


# The forms another client launch could take; each must fail the check.
CLIENT_LAUNCH_PROBES = (
    'python3 tools/skill-release-date-client.py baseline',
    '"python3" -I tools/skill-release-date-client.py baseline',
    'python3 -X utf8 tools/skill-release-date-client.py baseline',
    'python3 -I \\\n  tools/skill-release-date-client.py baseline',
    'tools/skill-release-date-client.py baseline',
    '"${PYTHON:-python3}" -I tools/skill-release-date-client.py baseline',
    'python3 -I tools/skill-release-date-client.py baseline',
)

# The lines of release-package.sh and release-dry-run.sh that name the
# client: its comments and its launches.
PACKAGER_CLIENT_MENTIONS = (
    '#      tools/skill-release-date-client.py, and fails on a malformed',
    '# tools/skill-release-date-client.py (row 89). The client gives a content',
    'baseline="$(python3 -I tools/skill-release-date-client.py baseline 2>&1)" || probe_rc=$?',
    '  checked="$(python3 -I tools/skill-release-date-client.py check-date "${release_date}" 2>&1)" || check_rc=$?',
    '  git show HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md | python3 -I tools/skill-release-date-client.py extract-stdin 2>&1',
    '    fail "the Released line in cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD is malformed: $(git show HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md | python3 -I tools/skill-release-date-client.py extract-stdin 2>&1 >/dev/null || true)"',
    '  requirement="$(python3 -I tools/skill-release-date-client.py requires-date "${version}" 2>&1)" || req_rc=$?',
)
DRY_RUN_CLIENT_MENTIONS = (
    '# The client, tools/skill-release-date-client.py, runs the extractor in its',
    'probe="$(python3 -I tools/skill-release-date-client.py baseline 2>&1)" || probe_rc=$?',
    'stamped="$(python3 -I tools/skill-release-date-client.py extract-file cleanlanguage/skills/cleanlanguage/SKILL.md)" || stamped_rc=$?',
)

# The lines of release-package.sh and release-dry-run.sh that name the
# extractor: failure messages and comments, none of them a launch.
PACKAGER_MENTIONS = (
    '#      (item 26) through tools/skill-release-date.py, run in its --json mode by',
    '# extractor, tools/skill-release-date.py, run in its --json mode by',
    '  fail "tools/skill-release-date.py is unavailable or broken (probe exit ${probe_rc}), so the Released line could not be checked"',
    '        || fail "tools/skill-release-date.py gave an unexpected answer (${checked:-nothing}) checking --release-date ${release_date}"',
    '      fail "tools/skill-release-date.py is unavailable or crashed (exit ${check_rc}) checking --release-date ${release_date:-nothing}"',
    '      || fail "tools/skill-release-date.py gave an unexpected answer (${released:-nothing}) for the Released line of cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD"',
    '    fail "tools/skill-release-date.py is unavailable or crashed (exit ${released_rc}) reading the Released line of cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD"',
    '    11) fail "tools/skill-release-date.py rejected the version ${version} as not a bare X.Y.Z" ;;',
    '      fail "tools/skill-release-date.py is unavailable or crashed (exit ${req_rc}) deciding whether ${version} needs a Released line"',
    '    *) fail "tools/skill-release-date.py gave an unexpected answer (${requirement:-nothing}) for whether ${version} needs a Released line" ;;',
)
DRY_RUN_MENTIONS = (
    '  0) [[ "${probe}" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+$ ]] || fail "tools/skill-release-date.py is unavailable or broken (probe exit 0)" ;;',
    '    fail "tools/skill-release-date.py is unavailable or broken (probe exit ${probe_rc})"',
    '  *) fail "tools/skill-release-date.py is unavailable or crashed (exit ${stamped_rc}) reading the stamped SKILL.md" ;;',
)

# Reads all of standard input, then fails the read, so the client exits 14
# (its input could not be read) without the writer of the pipe taking a
# SIGPIPE.
UNREADABLE_STDIN_HOOK = (
    "class _UnreadableStdin:\n"
    "    class buffer:\n"
    "        @staticmethod\n"
    "        def read():\n"
    "            sys.__stdin__.buffer.read()\n"
    "            raise OSError(5, \"injected read error\")\n"
    "sys.stdin = _UnreadableStdin()\n"
)
# Fails inside the extractor's extract, after the probe has passed, so it
# exits 6 and the client exits 16.
CRASH_HOOK = (
    "import unicodedata as _crash_mod\n"
    "def _crash(*args, **kwargs):\n"
    "    raise RuntimeError(\"injected internal error\")\n"
    "_crash_mod.category = _crash\n"
)

# Row 89: a stand-in client that answers the probe and the date check as the
# real one does, and then, for the read of the Released line, reads its input
# and ends with the exit code or the stdout given.
STAND_IN_CLIENT = (
    "import sys\n"
    "args = sys.argv[1:]\n"
    "if args == ['baseline']:\n"
    "    print('1.0.14')\n"
    "    raise SystemExit(0)\n"
    "if args[:1] == ['check-date']:\n"
    "    print(args[1])\n"
    "    raise SystemExit(0)\n"
    "sys.stdin.buffer.read()\n"
    "sys.stdout.write({out!r})\n"
    "raise SystemExit({code})\n"
)

# Row 89: a git that fails its third read of HEAD:cleanlanguage/skills/
# cleanlanguage/SKILL.md, which is the Released read of the packager (after
# the skill check and the version read), and runs the real git otherwise.
FAILING_BLOB_GIT = (
    "#!/bin/sh\n"
    "if [ \"$1\" = show ] && [ \"$2\" = HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md ]; then\n"
    "  n=$(cat {count} 2>/dev/null || echo 0)\n"
    "  n=$((n + 1))\n"
    "  echo \"$n\" > {count}\n"
    "  if [ \"$n\" -eq 3 ]; then echo 'fatal: injected blob read failure' >&2; exit 128; fi\n"
    "fi\n"
    "exec {git} \"$@\"\n"
)

# Row 89: a stand-in client that answers the probe and the date check as the
# real one does, and for the read of the Released line ends at once with the
# exit code given and a line on stderr, without reading its input.
EARLY_END_CLIENT = (
    "import sys\n"
    "args = sys.argv[1:]\n"
    "if args == ['baseline']:\n"
    "    print('1.0.14')\n"
    "    raise SystemExit(0)\n"
    "if args[:1] == ['check-date']:\n"
    "    print(args[1])\n"
    "    raise SystemExit(0)\n"
    "print('stand-in ended at once', file=sys.stderr)\n"
    "raise SystemExit({code})\n"
)

# Row 89: a git that, at its third read of HEAD:cleanlanguage/skills/
# cleanlanguage/SKILL.md (the Released read of the packager), writes the
# blob and then writes on until its reader has gone, so that when the client
# ends without reading, git show ends by SIGPIPE (status 141) whatever the
# pipe holds and whenever the client ends. A fixed amount more can fit in a
# larger pipe before the client ends, and git show then ends 0. The writes
# are the shell's own, so no head or yes decides the status; the stand-in
# is only for a client that ends without reading all of its input.
LONG_BLOB_GIT = (
    "#!/bin/sh\n"
    "if [ \"$1\" = show ] && [ \"$2\" = HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md ]; then\n"
    "  n=$(cat {count} 2>/dev/null || echo 0)\n"
    "  n=$((n + 1))\n"
    "  echo \"$n\" > {count}\n"
    "  if [ \"$n\" -eq 3 ]; then\n"
    "    {git} \"$@\" || exit\n"
    "    while :; do echo 'padding past the pipe buffer' || exit; done\n"
    "  fi\n"
    "fi\n"
    "exec {git} \"$@\"\n"
)

# Row 89: a copy of the extractor whose --json mode breaks for the op named
# first, in the way the MODE names, while every other op still answers, and
# whose CLI content modes exit 1 (so the probe passes and an unchanged caller
# reads the content as malformed).
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
    """The real extractor with ``op`` broken in the way ``mode`` names."""
    source = RELEASE_DATE_TOOL.read_text(encoding="utf-8")
    guard = '\nif __name__ == "__main__":\n'
    if source.count(guard) != 1:
        raise AssertionError("the extractor __main__ guard is not unique")
    return source.replace(guard, BROKEN_HOOK.format(op=op, body=MODES[mode]) + guard)


def extractor_with(hook: str, path: Path = RELEASE_DATE_TOOL) -> str:
    """The real extractor source (or the source at ``path``) with ``hook``
    run right after its imports."""
    source = path.read_text(encoding="utf-8")
    anchor = "from pathlib import Path\n"
    if source.count(anchor) != 1:
        raise AssertionError("the import anchor is not unique")
    return source.replace(anchor, anchor + hook)


def client_with(hook: str) -> str:
    """The real client source with ``hook`` run right after its imports."""
    return extractor_with(hook, CLIENT)


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "tools" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LINKS = _load("crl_gate", "check-release-links.py")
CHECKSUM = _load("crc_gate", "check-release-checksum-live.py")

HEAD_SKILL = subprocess.run(
    ["git", "-C", str(REPO), "show", "HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md"],
    capture_output=True, text=True, check=True,
).stdout

# The version at HEAD, read from the first Version: line of the committed
# SKILL.md, for the tests that pass HEAD's version: the gate parse assertion
# and 6 packager calls (7 runs; 1 call runs under 2 errexit modes). 4 calls
# build HEAD's SKILL.md, 2 of them with a comment appended, and reach the
# version comparison; 2 are refused before it, 1 on an empty SKILL.md and 1
# on HEAD's with an invalid UTF-8 byte appended. So they hold at every
# version, a release bump included. Fixture versions and the undated
# baseline stay literal.
HEAD_VERSION = next(line for line in HEAD_SKILL.splitlines()
                    if line.startswith("Version:")).split(":", 1)[1].strip()


def skill_with(version_block: str | None, released_block: str | None = None) -> str:
    """The real SKILL.md text with its first ``Version:`` line replaced by
    ``version_block`` (which may be empty to drop it, or multi-line).

    When ``version_block`` is given, any ``Released:`` line in the real text is
    dropped (so a fixture version is never paired with the real date), and
    ``released_block``, when given, is inserted directly after the version
    block."""
    if version_block is None:
        return HEAD_SKILL
    out, replaced = [], False
    for line in HEAD_SKILL.splitlines(keepends=True):
        if line.startswith("Released:"):
            continue
        if not replaced and line.startswith("Version:"):
            if version_block:
                out.append(version_block + "\n")
            if released_block is not None:
                out.append(released_block + "\n")
            replaced = True
        else:
            out.append(line)
    return "".join(out)


def gate_verdict(gate, skill_text: str):
    """(matched, version) for a gate's select-and-validate, read the way the real
    gate reads a file: through Path.read_text, whose universal-newline handling
    drops a trailing CR from a CRLF line ending."""
    with tempfile.NamedTemporaryFile("wb", suffix=".md", delete=False) as handle:
        handle.write(skill_text.encode("utf-8"))
        path = handle.name
    try:
        text = Path(path).read_text(encoding="utf-8")
    finally:
        os.unlink(path)
    line = gate.VERSION_LINE.search(text)
    if line is None:
        return False, None
    match = gate.SKILL_VERSION.match(line.group(0))
    return (True, match.group(1)) if match else (False, None)


def run_packager(version_block: str | None, plugin_version: str, locale: str | None = None, extra_tail: str = "", raw_skill: bytes | None = None, release_date: str | None = None, released_block: str | None = None, extra_args: tuple = (), extractor: str | None = None, client: str | None = None, path_prefix: str | None = None, bash_options: tuple = ()):
    """Build in a throwaway worktree whose HEAD carries the fixture; run the
    CHECKOUT's release-package.sh, tools/skill-release-date.py and
    tools/skill-release-date-client.py (so the code under test, not HEAD's
    copy, is exercised), passing ``--release-date`` when ``release_date`` is
    given and then ``extra_args``. ``extractor`` replaces the extractor and
    ``client`` the client: ``"missing"`` deletes it, any other text is written
    in its place. ``path_prefix`` is put first on the PATH of the packager,
    and ``bash_options`` are passed to the bash that runs it.
    Returns (exit_code, stderr)."""
    skill = skill_with(version_block, released_block) + extra_tail
    with tempfile.TemporaryDirectory() as tmp:
        wt = Path(tmp) / "wt"
        subprocess.run(
            ["git", "-C", str(REPO), "worktree", "add", "--detach", str(wt), "HEAD"],
            capture_output=True, check=True,
        )
        try:
            if raw_skill is not None:
                (wt / "cleanlanguage" / "skills" / "cleanlanguage" / "SKILL.md").write_bytes(raw_skill)
            else:
                (wt / "cleanlanguage" / "skills" / "cleanlanguage" / "SKILL.md").write_text(skill, encoding="utf-8")
            pj = wt / "cleanlanguage" / ".claude-plugin" / "plugin.json"
            data = json.loads(pj.read_text(encoding="utf-8"))
            data["version"] = plugin_version
            pj.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(wt), "-c", "user.name=t", "-c", "user.email=t@t",
                 "commit", "-qam", "fixture"],
                capture_output=True, check=True,
            )
            shutil.copyfile(PACKAGER, wt / "tools" / "release-package.sh")
            os.chmod(wt / "tools" / "release-package.sh", 0o755)
            shutil.copyfile(RELEASE_DATE_TOOL, wt / "tools" / "skill-release-date.py")
            shutil.copyfile(CLIENT, wt / "tools" / "skill-release-date-client.py")
            for name, body in (("skill-release-date.py", extractor), ("skill-release-date-client.py", client)):
                if body == "missing":
                    (wt / "tools" / name).unlink()
                elif body is not None:
                    (wt / "tools" / name).write_text(body, encoding="utf-8")
            env = dict(os.environ)
            if locale is not None:
                env["LC_ALL"] = locale
            if path_prefix is not None:
                env["PATH"] = path_prefix + os.pathsep + env.get("PATH", "")
            args = ["bash", *bash_options, str(wt / "tools" / "release-package.sh")]
            if release_date is not None:
                args += ["--release-date", release_date]
            args += list(extra_args)
            result = subprocess.run(args, capture_output=True, text=True, env=env)
            return result.returncode, result.stderr
        finally:
            subprocess.run(
                ["git", "-C", str(REPO), "worktree", "remove", "--force", str(wt)],
                capture_output=True,
            )


# label -> (version_block, plugin_version, packager_accepts, gate_expected_version)
MALFORMED = {
    "two_part": ("Version: 1.2", "1.2", None),
    "four_part": ("Version: 1.2.3.4", "1.2.3.4", None),
    "trailing_text": ("Version: 1.2.3 beta", "1.2.3", None),
    "double_dot": ("Version: 1..2", "1..2", None),
    "draft_then_valid": ("Version: draft\nVersion: 1.2.3", "1.2.3", None),
}


class GateParseTest(unittest.TestCase):
    def test_gates_agree_and_are_identical(self):
        # Both gates apply the identical rule; assert on each so a future
        # divergence between them also goes red.
        for gate in (LINKS, CHECKSUM):
            matched, version = gate_verdict(gate, skill_with(None))
            self.assertTrue(matched)
            self.assertEqual(version, HEAD_VERSION)
            matched, version = gate_verdict(gate, skill_with("Version: 9.9.9  "))
            self.assertTrue(matched)
            self.assertEqual(version, "9.9.9")
            for block, _plugin, _ in MALFORMED.values():
                matched, _ = gate_verdict(gate, skill_with(block))
                self.assertFalse(matched, block)
            matched, _ = gate_verdict(gate, skill_with(""))
            self.assertFalse(matched)


class PackagerContractTest(unittest.TestCase):
    def test_real_head_version_builds(self):
        code, stderr = run_packager(None, HEAD_VERSION)
        self.assertEqual(code, 0, stderr)

    def test_malformed_first_line_is_rejected(self):
        for label, (block, plugin, _) in MALFORMED.items():
            with self.subTest(label):
                code, stderr = run_packager(block, plugin)
                self.assertEqual(code, 1, f"{label}: stderr={stderr!r}")
                self.assertIn("not a bare X.Y.Z", stderr)

    def test_no_version_line_is_rejected(self):
        code, stderr = run_packager("", "1.0.14")
        self.assertEqual(code, 1, stderr)
        self.assertIn("no Version: line found", stderr)


class PackagerReleaseDateTest(unittest.TestCase):
    """T3 (item 26): the packager checks the Released line it ships.

    Whether or not ``--release-date`` is given, it refuses a malformed line
    and a missing one above the undated baseline; ``--release-date`` adds the
    check that the HEAD Released line is present and names that day."""

    def test_matching_release_date_builds(self):
        code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", release_date="2026-11-15",
                                    released_block="Released: 2026-11-15  ")
        self.assertEqual(code, 0, stderr)

    def test_mismatched_release_date_fails(self):
        code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", release_date="2026-11-16",
                                    released_block="Released: 2026-11-15  ")
        self.assertEqual(code, 1, stderr)
        self.assertIn("does not match the release date (2026-11-16)", stderr)

    def test_absent_line_above_baseline_with_release_date_fails(self):
        code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", release_date="2026-11-15")
        self.assertEqual(code, 1, stderr)
        self.assertIn("has no Released: line", stderr)

    def test_absent_line_at_baseline_with_release_date_fails(self):
        # Row 60: a given --release-date needs a line to check, so its
        # absence fails at or below the undated baseline too, never a build
        # that silently ignores the flag.
        code, stderr = run_packager("Version: 1.0.14  ", "1.0.14", release_date="2026-11-15")
        self.assertEqual(code, 1, stderr)
        self.assertIn("--release-date 2026-11-15 was given, but SKILL.md at HEAD has no Released: line", stderr)

    def test_absent_line_above_baseline_without_release_date_fails(self):
        # F8: presence above the baseline is enforced without the flag too.
        code, stderr = run_packager("Version: 1.2.3  ", "1.2.3")
        self.assertEqual(code, 1, stderr)
        self.assertIn("has no Released: line, but version 1.2.3 sorts above the undated baseline 1.0.14", stderr)

    def test_dated_line_without_release_date_builds(self):
        code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", released_block="Released: 2026-11-15  ")
        self.assertEqual(code, 0, stderr)

    def test_baseline_rule_is_numeric(self):
        # F7: the extractor decides the comparison, so the packager agrees with
        # every other caller, leading zeros included. Row 60: with
        # --release-date given, an absent line fails at every version.
        for version, builds in (
            ("1.0.9", True), ("1.0.14", True), ("1.00.14", True),
            ("1.0.15", False), ("1.0.100", False), ("1.1.0", False),
        ):
            for release_date in (None, "2026-11-15"):
                with self.subTest(version=version, release_date=release_date):
                    code, stderr = run_packager(f"Version: {version}  ", version, release_date=release_date)
                    if builds and release_date is None:
                        self.assertEqual(code, 0, stderr)
                    else:
                        self.assertEqual(code, 1, stderr)
                        self.assertIn("has no Released: line", stderr)

    def test_trailing_flag_without_a_value_fails_with_a_message(self):
        # F6: a trailing --release-date (or --tag) names what is missing.
        for flag, fragment in (
            ("--release-date", "--release-date needs a YYYY-MM-DD value"),
            ("--tag", "--tag needs a value"),
        ):
            with self.subTest(flag):
                code, stderr = run_packager("Version: 1.0.14  ", "1.0.14", extra_args=(flag,))
                self.assertEqual(code, 1, stderr)
                self.assertIn(fragment, stderr)

    def test_unavailable_extractor_is_not_blamed_on_the_content(self):
        # F5: a missing or broken extractor is unavailable, not a bad date or
        # a malformed line.
        for label, body in (("missing", "missing"), ("broken", "def broken(:\n")):
            with self.subTest(label):
                code, stderr = run_packager("Version: 1.0.14  ", "1.0.14", release_date="2026-11-15",
                                            extractor=body)
                self.assertEqual(code, 1, stderr)
                self.assertIn("tools/skill-release-date.py is unavailable or broken", stderr)
                self.assertNotIn("must be a real YYYY-MM-DD date", stderr)
                self.assertNotIn("malformed", stderr)

    def test_unreadable_input_at_head_is_named_as_unreadable(self):
        # T4: client exit 14 is unreadable input, never a crash.
        code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", release_date="2026-11-15",
                                    released_block="Released: 2026-11-15  ",
                                    client=client_with(UNREADABLE_STDIN_HOOK))
        self.assertEqual(code, 1, stderr)
        self.assertIn("at HEAD for its Released line: the client could not read its input (exit 14)", stderr)
        self.assertNotIn("unavailable or crashed", stderr)

    def test_internal_error_at_head_is_reported_as_a_crash(self):
        # T4: an extractor internal error is the tool failing (client exit
        # 16), never unreadable input.
        code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", release_date="2026-11-15",
                                    released_block="Released: 2026-11-15  ",
                                    extractor=extractor_with(CRASH_HOOK))
        self.assertEqual(code, 1, stderr)
        self.assertIn("unavailable or crashed (exit 16) reading the Released line", stderr)
        self.assertNotIn("could not read", stderr)

    def test_a_broken_extractor_reply_is_unavailable_at_every_call(self):
        # Row 89: at each call of the packager, an extractor that passes the
        # probe but breaks the contract for that call's op reads as the tool
        # being unavailable, never as a verdict on the content.
        sites = (
            ("check-date", "parse_date",
             dict(version_block="Version: 1.2.3  ", plugin_version="1.2.3", release_date="2026-11-15",
                  released_block="Released: 2026-11-15  "),
             "tools/skill-release-date.py is unavailable or crashed (exit 16) checking --release-date 2026-11-15",
             ("must be a real YYYY-MM-DD date",)),
            ("extract", "extract",
             dict(version_block="Version: 1.2.3  ", plugin_version="1.2.3", release_date="2026-11-15",
                  released_block="Released: 2026-11-15  "),
             "tools/skill-release-date.py is unavailable or crashed (exit 16) reading the Released line of "
             "cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD",
             ("malformed", "could not read")),
            ("requires-date", "requires_release_date",
             dict(version_block="Version: 1.0.14  ", plugin_version="1.0.14"),
             "tools/skill-release-date.py is unavailable or crashed (exit 16) deciding whether 1.0.14 needs a "
             "Released line",
             ("rejected the version", "unexpected answer")),
        )
        sites += (
            ("baseline", "baseline",
             dict(version_block="Version: 1.2.3  ", plugin_version="1.2.3", release_date="2026-11-15",
                  released_block="Released: 2026-11-15  "),
             "tools/skill-release-date.py is unavailable or broken (probe exit 16), so the Released line could not "
             "be checked",
             ("malformed", "could not read")),
        )
        for site, op, fixture, expected, absent in sites:
            for mode in MODES:
                with self.subTest(site=site, mode=mode):
                    code, stderr = run_packager(extractor=broken_extractor(op, mode), **fixture)
                    self.assertEqual(code, 1, stderr)
                    self.assertIn(expected, stderr)
                    for fragment in absent:
                        self.assertNotIn(fragment, stderr)
                    # The line in which the client names its reason is relayed
                    # before the message of the packager.
                    lines = stderr.splitlines()
                    self.assertEqual(len(lines), 2, stderr)
                    self.assertTrue(lines[0].startswith("skill-release-date-client: skill-release-date.py "), stderr)
                    self.assertTrue(lines[0].endswith(f" in {op}, so the extractor is unavailable")
                                    or f" in {op}, so the extractor is unavailable; it printed: " in lines[0], stderr)
                    self.assertTrue(lines[1].startswith("release-package: "), stderr)

    def test_a_probe_value_with_another_line_is_not_accepted(self):
        stand_in = STAND_IN_CLIENT.replace("    print('1.0.14')\n", "    print('1.0.14')\n    print('noise')\n", 1)
        self.assertNotEqual(stand_in, STAND_IN_CLIENT)
        code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", released_block="Released: 2026-11-15  ",
                                    client=stand_in.format(out="2026-11-15\n", code=0))
        self.assertEqual(code, 1, stderr)
        self.assertIn("tools/skill-release-date.py is unavailable or broken (probe exit 0)", stderr)

    def test_a_checked_date_with_a_second_line_is_refused(self):
        # Row 89: the date check must print exactly the --release-date given.
        stand_in = STAND_IN_CLIENT.replace("    print(args[1])\n", "    print(args[1])\n    print('X=1')\n", 1)
        self.assertNotEqual(stand_in, STAND_IN_CLIENT)
        code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", release_date="2026-11-15",
                                    released_block="Released: 2026-11-15  ",
                                    client=stand_in.format(out="2026-11-15\n", code=0))
        self.assertEqual(code, 1, stderr)
        self.assertIn("tools/skill-release-date.py gave an unexpected answer (2026-11-15\nX=1) checking --release-date "
                      "2026-11-15", stderr)

    def test_a_client_exit_125_is_not_a_failed_blob_read(self):
        # Row 89: 125 is a client exit like any other, not the failed read of
        # the blob, which the packager reports only from the status of git.
        code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", release_date="2026-11-15",
                                    released_block="Released: 2026-11-15  ",
                                    client=STAND_IN_CLIENT.format(out="", code=125))
        self.assertEqual(code, 1, stderr)
        self.assertIn("tools/skill-release-date.py is unavailable or crashed (exit 125) reading the Released line", stderr)
        self.assertNotIn("could not read", stderr)

    def long_blob_run(self, code: int):
        git = shutil.which("git")
        self.assertIsNotNone(git)
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "git"
            fake.write_text(LONG_BLOB_GIT.format(count=str(Path(tmp) / "count"), git=git), encoding="utf-8")
            fake.chmod(0o755)
            result = run_packager("Version: 1.2.3  ", "1.2.3", release_date="2026-11-15",
                                  released_block="Released: 2026-11-15  ", path_prefix=tmp,
                                  client=EARLY_END_CLIENT.format(code=code))
            reads = int((Path(tmp) / "count").read_text())
        self.assertEqual(reads, 3, result[1])
        return result

    def test_a_client_that_ends_before_the_whole_blob_is_reported_as_itself(self):
        # Row 89: the client ends at once with exit 16, so git show, still
        # writing, ends by SIGPIPE (141). The client's exit and reason are
        # reported, not a failed blob read.
        code, stderr = self.long_blob_run(16)
        self.assertEqual(code, 1, stderr)
        self.assertEqual(stderr.splitlines(), [
            "stand-in ended at once",
            "release-package: tools/skill-release-date.py is unavailable or crashed (exit 16) reading the Released "
            "line of cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD",
        ])

    def test_a_client_that_ends_before_the_whole_blob_with_exit_14_reports_its_reason(self):
        # Row 89: unreadable input beside a SIGPIPE keeps the client's
        # reason before the packager's unreadable-input message.
        code, stderr = self.long_blob_run(14)
        self.assertEqual(code, 1, stderr)
        self.assertEqual(stderr.splitlines(), [
            "stand-in ended at once",
            "release-package: could not read cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD for its Released "
            "line: the client could not read its input (exit 14)",
        ])

    def test_a_content_verdict_beside_a_sigpipe_is_a_failed_blob_read(self):
        # Row 89: a content verdict beside a non-zero blob status may rest on
        # part of the blob, so it is never taken: an absent line (13) or a
        # malformed one (11) beside a SIGPIPE is a failed blob read.
        for verdict in (13, 11):
            with self.subTest(verdict=verdict):
                code, stderr = self.long_blob_run(verdict)
                self.assertEqual(code, 1, stderr)
                self.assertIn("release-package: could not read cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD for "
                              "its Released line\n", stderr)
                self.assertNotIn("unavailable or crashed", stderr)

    def test_a_failed_blob_read_is_named_as_such(self):
        # Row 89: a git show that fails at the Released read is reported as
        # that, whatever the client did with the input it got.
        git = shutil.which("git")
        self.assertIsNotNone(git)
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "git"
            fake.write_text(FAILING_BLOB_GIT.format(count=str(Path(tmp) / "count"), git=git), encoding="utf-8")
            fake.chmod(0o755)
            code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", release_date="2026-11-15",
                                        released_block="Released: 2026-11-15  ", path_prefix=tmp)
            reads = int((Path(tmp) / "count").read_text())
        self.assertEqual(reads, 3, stderr)
        self.assertEqual(code, 1, stderr)
        self.assertIn("release-package: could not read cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD for its "
                      "Released line\n", stderr)
        self.assertNotIn("unavailable or crashed", stderr)

    def test_a_value_that_is_not_a_day_is_not_used(self):
        # Row 89: an exit 0 whose output is not a bare day (which the client
        # never gives) fails as an unexpected answer, never as a Released date.
        code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", released_block="Released: 2026-11-15  ",
                                    client=STAND_IN_CLIENT.format(out="2026-11-15\nnoise\n", code=0))
        self.assertEqual(code, 1, stderr)
        self.assertIn("tools/skill-release-date.py gave an unexpected answer (2026-11-15\nnoise) for the Released "
                      "line of cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD", stderr)

    def test_a_broken_client_is_unavailable(self):
        # Row 89: a client that does not compile (exit 1) or is missing (exit
        # 2) fails the probe, never a content verdict.
        for label, body in (("missing", "missing"), ("broken", "def broken(:\n")):
            with self.subTest(label):
                code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", release_date="2026-11-15",
                                            released_block="Released: 2026-11-15  ", client=body)
                self.assertEqual(code, 1, stderr)
                self.assertIn("tools/skill-release-date.py is unavailable or broken (probe exit "
                              + ("2" if label == "missing" else "1") + ")", stderr)
                self.assertNotIn("malformed", stderr)

    def test_malformed_line_fails_without_release_date(self):
        for label, block in (
            ("not_a_date", "Released: soon"),
            ("impossible_date", "Released: 2026-02-30"),
            ("misspelt_key", "released: 2026-11-15"),
        ):
            with self.subTest(label):
                code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", released_block=block)
                self.assertEqual(code, 1, stderr)
                self.assertIn("Released line in cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD is malformed: "
                              "skill-release-date: ", stderr)

    def test_line_away_from_version_fails(self):
        code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", release_date="2026-11-15",
                                    extra_tail="\nReleased: 2026-11-15\n")
        self.assertEqual(code, 1, stderr)
        self.assertIn("is malformed", stderr)

    def test_invalid_release_date_argument_fails(self):
        for value in ("2026-02-30", "", "15 November 2026"):
            with self.subTest(value):
                code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", release_date=value,
                                            released_block="Released: 2026-11-15  ")
                self.assertEqual(code, 1, stderr)
                self.assertIn("--release-date must be a real YYYY-MM-DD date", stderr)


def dry_run_probe(extractor: str, bash_options: tuple = ()):
    """Run the probe of release-dry-run.sh, extracted from the real script
    (from ``probe_rc=0`` to its ``esac``), in a throwaway tree holding
    ``extractor`` and the real client. Returns (exit code, stdout, stderr)."""
    lines = DRY_RUN.read_text(encoding="utf-8").split("\n")
    start = lines.index("probe_rc=0")
    block = "\n".join(lines[start: lines.index("esac", start) + 1])
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "tools").mkdir()
        (root / "tools" / "skill-release-date.py").write_text(extractor, encoding="utf-8")
        (root / "tools" / "skill-release-date-client.py").write_text(CLIENT.read_text(encoding="utf-8"),
                                                                     encoding="utf-8")
        script = (
            "set -euo pipefail\n"
            "fail() { printf 'release-dry-run: %s\\n' \"$1\" >&2; exit 1; }\n"
            + block + "\nprintf %s \"${probe}\"\n"
        )
        proc = subprocess.run(["bash", *bash_options, "-c", script], cwd=root, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def dry_run_stamped_read(extractor: str, skill_readable: bool = True, client: str | None = None,
                         skill_text: str = "Version: 1.0.15  \nReleased: 2026-11-15  \n", bash_options: tuple = ()):
    """Run the stamped Released read of release-dry-run.sh, extracted from the
    real script (from ``stamped_rc=0`` to its ``esac``), in a throwaway tree
    holding ``extractor`` and ``client`` (the real client by default).
    Returns (exit code, stdout, stderr)."""
    lines = DRY_RUN.read_text(encoding="utf-8").split("\n")
    start = lines.index("stamped_rc=0")
    block = "\n".join(lines[start: lines.index("esac", start) + 1])
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "tools").mkdir()
        skill = root / "cleanlanguage" / "skills" / "cleanlanguage" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        if skill_readable:
            skill.write_text(skill_text, encoding="utf-8")
        else:
            skill.mkdir()
        (root / "tools" / "skill-release-date.py").write_text(extractor, encoding="utf-8")
        (root / "tools" / "skill-release-date-client.py").write_text(
            CLIENT.read_text(encoding="utf-8") if client is None else client, encoding="utf-8")
        script = (
            "set -euo pipefail\n"
            "fail() { printf 'release-dry-run: %s\\n' \"$1\" >&2; exit 1; }\n"
            + block + "\nprintf %s \"${stamped}\"\n"
        )
        proc = subprocess.run(["bash", *bash_options, "-c", script], cwd=root, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


class DryRunReleasedReadTest(unittest.TestCase):
    """T4: the dry run tells unreadable input (client exit 14) apart from an
    extractor that failed inside or broke its contract (client exit 16)."""

    def test_stamped_line_is_read(self):
        code, out, err = dry_run_stamped_read(RELEASE_DATE_TOOL.read_text(encoding="utf-8"))
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "2026-11-15")

    def test_unreadable_stamped_file_is_named_as_unreadable(self):
        code, _out, err = dry_run_stamped_read(RELEASE_DATE_TOOL.read_text(encoding="utf-8"), skill_readable=False)
        self.assertEqual(code, 1, err)
        self.assertIn("could not read the stamped cleanlanguage/skills/cleanlanguage/SKILL.md for its Released line (client exit 14)", err)
        self.assertNotIn("unavailable or crashed", err)

    def test_internal_error_is_reported_as_a_crash(self):
        code, _out, err = dry_run_stamped_read(extractor_with(CRASH_HOOK))
        self.assertEqual(code, 1, err)
        self.assertIn("unavailable or crashed (exit 16) reading the stamped SKILL.md", err)
        self.assertNotIn("could not read the stamped", err)

    def test_a_broken_extractor_reply_is_unavailable(self):
        # Row 89: an extractor that breaks the contract for the read is the
        # tool failing, never a stamp that did not take.
        for mode in MODES:
            with self.subTest(mode):
                code, _out, err = dry_run_stamped_read(broken_extractor("extract", mode))
                self.assertEqual(code, 1, err)
                self.assertIn("tools/skill-release-date.py is unavailable or crashed (exit 16) reading the stamped "
                              "SKILL.md", err)
                self.assertNotIn("could not set the dry-run Released date", err)

    def test_the_probe_passes_and_relays_the_client_reason(self):
        code, out, err = dry_run_probe(RELEASE_DATE_TOOL.read_text(encoding="utf-8"))
        self.assertEqual((code, out, err), (0, "1.0.14", ""))
        code, _out, err = dry_run_probe(broken_extractor("baseline", "exit1"))
        self.assertEqual(code, 1, err)
        self.assertEqual(err.splitlines(), [
            "skill-release-date-client: skill-release-date.py exited 1 in baseline, so the extractor is unavailable",
            "release-dry-run: tools/skill-release-date.py is unavailable or broken (probe exit 16)",
        ])

    def test_a_malformed_stamp_names_the_client_exit(self):
        code, _out, err = dry_run_stamped_read(RELEASE_DATE_TOOL.read_text(encoding="utf-8"),
                                               skill_text="Version: 1.0.15  \nReleased: soon\n")
        self.assertEqual(code, 1, err)
        self.assertIn("could not set the dry-run Released date in SKILL.md (client exit 11)", err)


class CallerLaunchTest(unittest.TestCase):
    """Row 89: the packager and the dry run reach the extractor only through
    the client, each launch isolated."""

    def test_every_launch_goes_through_the_client(self):
        self.assertNotIn(EXTRACTOR_NAME, "tools/skill-release-date-client.py")
        for path, mentions, client, launches in ((PACKAGER, PACKAGER_MENTIONS, PACKAGER_CLIENT_MENTIONS, 5),
                                                 (DRY_RUN, DRY_RUN_MENTIONS, DRY_RUN_CLIENT_MENTIONS, 2)):
            with self.subTest(path.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(extractor_mentions(text), list(mentions))
                self.assertEqual(client_mentions(text), list(client))
                self.assertEqual(text.count("python3 -I tools/skill-release-date-client.py"), launches)

    def test_every_direct_launch_form_fails_the_check(self):
        for path, mentions in ((PACKAGER, PACKAGER_MENTIONS), (DRY_RUN, DRY_RUN_MENTIONS)):
            text = path.read_text(encoding="utf-8")
            for probe in LAUNCH_PROBES:
                with self.subTest(path.name, probe=probe):
                    self.assertNotEqual(extractor_mentions(text + probe + "\n"), list(mentions))

    def test_every_other_client_launch_fails_the_check(self):
        for path, client in ((PACKAGER, PACKAGER_CLIENT_MENTIONS), (DRY_RUN, DRY_RUN_CLIENT_MENTIONS)):
            text = path.read_text(encoding="utf-8")
            for probe in CLIENT_LAUNCH_PROBES:
                with self.subTest(path.name, probe=probe):
                    self.assertNotEqual(client_mentions(text + probe + "\n"), list(client))


# Row 89: the two ways errexit can be inherited by a command substitution.
INHERITED_ERREXIT = (("inherit_errexit", ("-O", "inherit_errexit")), ("posix", ("-o", "posix")))


class InheritedErrexitTest(unittest.TestCase):
    """Row 89: the packager and the dry run keep every result of the client
    when errexit is inherited by command substitutions, by shopt -s
    inherit_errexit or in POSIX mode: a non-zero client exit never ends a
    substitution before its statuses are read, so no run ends without its
    message."""

    def test_the_packager_builds_and_reports_as_without_the_option(self):
        for label, options in INHERITED_ERREXIT:
            with self.subTest(label, case="the version at HEAD builds"):
                code, stderr = run_packager(None, HEAD_VERSION, bash_options=options)
                self.assertEqual(code, 0, stderr)
            with self.subTest(label, case="an undated baseline builds"):
                code, stderr = run_packager("Version: 1.0.14  ", "1.0.14", bash_options=options)
                self.assertEqual(code, 0, stderr)
            with self.subTest(label, case="a dated release builds"):
                code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", release_date="2026-11-15",
                                            released_block="Released: 2026-11-15  ", bash_options=options)
                self.assertEqual(code, 0, stderr)
            with self.subTest(label, case="a client exit 125 is reported"):
                code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", release_date="2026-11-15",
                                            released_block="Released: 2026-11-15  ",
                                            client=STAND_IN_CLIENT.format(out="", code=125), bash_options=options)
                self.assertEqual(code, 1, stderr)
                self.assertIn("tools/skill-release-date.py is unavailable or crashed (exit 125) reading the Released "
                              "line", stderr)
            with self.subTest(label, case="a broken extractor is reported with its reason"):
                code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", release_date="2026-11-15",
                                            released_block="Released: 2026-11-15  ",
                                            extractor=broken_extractor("extract", "exit1"), bash_options=options)
                self.assertEqual(code, 1, stderr)
                self.assertEqual(stderr.splitlines(), [
                    "skill-release-date-client: skill-release-date.py exited 1 in extract, so the extractor is "
                    "unavailable",
                    "release-package: tools/skill-release-date.py is unavailable or crashed (exit 16) reading the "
                    "Released line of cleanlanguage/skills/cleanlanguage/SKILL.md at HEAD",
                ])
            with self.subTest(label, case="a malformed line is named as such"):
                code, stderr = run_packager("Version: 1.2.3  ", "1.2.3", released_block="Released: soon",
                                            bash_options=options)
                self.assertEqual(code, 1, stderr)
                self.assertIn("at HEAD is malformed: skill-release-date: ", stderr)

    def test_the_dry_run_reads_as_without_the_option(self):
        extractor = RELEASE_DATE_TOOL.read_text(encoding="utf-8")
        for label, options in INHERITED_ERREXIT:
            with self.subTest(label):
                self.assertEqual(dry_run_probe(extractor, bash_options=options), (0, "1.0.14", ""))
                code, _out, err = dry_run_probe(broken_extractor("baseline", "exit1"), bash_options=options)
                self.assertEqual(code, 1, err)
                self.assertIn("release-dry-run: tools/skill-release-date.py is unavailable or broken (probe exit 16)",
                              err)
                code, out, err = dry_run_stamped_read(extractor, bash_options=options)
                self.assertEqual((code, out), (0, "2026-11-15"), err)
                code, _out, err = dry_run_stamped_read(extractor, skill_text="Version: 1.0.15  \nReleased: soon\n",
                                                       bash_options=options)
                self.assertEqual(code, 1, err)
                self.assertIn("could not set the dry-run Released date in SKILL.md (client exit 11)", err)


def _locale_available(name: str) -> bool:
    try:
        return subprocess.run(["locale", "-a"], capture_output=True, text=True).stdout \
            .lower().find(name.lower().replace("-", "")) >= 0 or name in \
            subprocess.run(["locale", "-a"], capture_output=True, text=True).stdout
    except OSError:
        return False


class UnicodeAndStressTest(unittest.TestCase):
    """A bash regex class is locale sensitive; the packager must still agree with
    the gates' ASCII rule on non-ASCII blanks and digits, and must not crash on a
    large but valid SKILL.md."""

    def _gates_reject(self, version_block):
        for gate in (LINKS, CHECKSUM):
            matched, _ = gate_verdict(gate, skill_with(version_block))
            self.assertFalse(matched, version_block)

    def test_unicode_blank_is_rejected(self):
        # U+2000 (EN QUAD) is matched by [[:blank:]] under C.UTF-8 but not by the
        # gates' [ \t]; the literal class must reject it, matching the gates.
        block = "Version: 1.2.3\u2000"
        code, stderr = run_packager(block, "1.2.3", locale="C.UTF-8")
        self.assertEqual(code, 1, stderr)
        self.assertIn("not a bare X.Y.Z", stderr)
        self._gates_reject(block)

    def test_unicode_digit_is_rejected(self):
        # A fullwidth digit is matched by [0-9] under a full UTF-8 locale but not
        # by the gates' ASCII [0-9]; the ASCII digit list must reject it.
        if not _locale_available("en_US.utf8"):
            self.skipTest("en_US.UTF-8 locale not installed")
        block = "Version: \uff11.2.3"
        code, stderr = run_packager(block, "\uff11.2.3", locale="en_US.UTF-8")
        self.assertEqual(code, 1, stderr)
        self._gates_reject(block)

    def test_crlf_line_ending_agrees(self):
        # A CRLF line ending: the gate reads with universal newlines (drops the
        # CR) and accepts 1.2.3; the packager strips a trailing CR too, so both
        # accept. The pre-change packager rejected it (the CR survived).
        block = "Version: 1.2.3\r"
        # 1.2.3 is above the undated baseline, so it carries a Released line.
        code, stderr = run_packager(block, "1.2.3", released_block="Released: 2026-11-15\r")
        self.assertEqual(code, 0, stderr)
        for gate in (LINKS, CHECKSUM):
            matched, version = gate_verdict(gate, skill_with(block))
            self.assertTrue(matched)
            self.assertEqual(version, "1.2.3")

    def test_large_valid_skill_builds(self):
        # A large but valid SKILL.md must build, not die with SIGPIPE (exit 141)
        # from an awk pipe that closes early.
        tail = "\n<!-- " + ("x" * 200000) + " -->\n"
        code, stderr = run_packager(None, HEAD_VERSION, extra_tail=tail)
        self.assertEqual(code, 0, stderr)

    def test_nul_in_version_line_is_rejected_by_all_three(self):
        # A NUL in the version line: both the gates and the packager (which now
        # reads the file the same way) reject it, because a NUL is not [ \t] and
        # so breaks the bare-X.Y.Z match. The pre-change packager stripped it.
        block = "Version: 1.2.3\x00"
        code, stderr = run_packager(block, "1.2.3")
        self.assertEqual(code, 1, stderr)
        self.assertIn("not a bare X.Y.Z", stderr)
        self._gates_reject(block)

    def test_nul_outside_version_line_agrees(self):
        # A NUL elsewhere leaves the version line clean, so both accept the
        # version at HEAD.
        code, stderr = run_packager(None, HEAD_VERSION, extra_tail="\n<!-- \x00 -->\n")
        self.assertEqual(code, 0, stderr)

    def test_lone_cr_mid_line_selects_the_same_version(self):
        # A bare CR inside a line: read_text universal newlines split there, so
        # the gate's first Version line is 1.0.0; the packager, reading the file
        # the same way, also selects 1.0.0. A plain bash read loop (split on LF
        # only) would have skipped the hidden token and chosen 2.0.0 instead.
        block = "foo\rVersion: 1.0.0\nVersion: 2.0.0"
        code, _ = run_packager(block, "1.0.0")
        self.assertEqual(code, 0)
        matched, version = gate_verdict(LINKS, skill_with(block))
        self.assertTrue(matched)
        self.assertEqual(version, "1.0.0")

    def test_empty_skill_agrees_with_gates(self):
        # An empty SKILL.md: both the packager and the gates report no Version
        # line (exact message parity). A genuine git-read failure is reported
        # separately by the explicit check on the skill read.
        code, stderr = run_packager(None, HEAD_VERSION, raw_skill=b"")
        self.assertEqual(code, 1, stderr)
        self.assertIn("no Version: line found", stderr)
        for gate in (LINKS, CHECKSUM):
            matched, _ = gate_verdict(gate, "")
            self.assertFalse(matched)

    def test_invalid_utf8_is_rejected(self):
        # An invalid UTF-8 byte anywhere: the gates' read_text raises and the
        # packager's decode raises too, so both reject rather than the packager
        # building malformed text.
        head = subprocess.run(
            ["git", "-C", str(REPO), "show", "HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md"],
            capture_output=True, check=True,
        ).stdout
        raw = head + b"\n<!-- \xff -->\n"
        code, stderr = run_packager(None, HEAD_VERSION, raw_skill=raw)
        self.assertEqual(code, 1, stderr)
        self.assertIn("not valid UTF-8", stderr)


class ZipLayoutTest(unittest.TestCase):
    """The skill source lives under skills/cleanlanguage/ for Agent Plugins
    discovery, but the published zip must still carry SKILL.md and its
    references at the archive root. This fails if the packager's re-root step
    is dropped or the source path regresses to the legacy root."""

    def test_source_is_nested_and_zip_is_rooted(self):
        tree = subprocess.run(
            ["git", "-C", str(REPO), "ls-tree", "-r", "--name-only", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        self.assertIn("cleanlanguage/skills/cleanlanguage/SKILL.md", tree)
        self.assertNotIn("cleanlanguage/SKILL.md", tree)
        with tempfile.TemporaryDirectory() as tmp:
            wt = Path(tmp) / "wt"
            subprocess.run(
                ["git", "-C", str(REPO), "worktree", "add", "--detach", str(wt), "HEAD"],
                capture_output=True, check=True,
            )
            try:
                # Exercise the checkout's packager and extractor, not HEAD's
                # copies, so an uncommitted change is caught locally too.
                shutil.copyfile(PACKAGER, wt / "tools" / "release-package.sh")
                os.chmod(wt / "tools" / "release-package.sh", 0o755)
                shutil.copyfile(RELEASE_DATE_TOOL, wt / "tools" / "skill-release-date.py")
                shutil.copyfile(CLIENT, wt / "tools" / "skill-release-date-client.py")
                proc = subprocess.run(
                    ["bash", str(wt / "tools" / "release-package.sh")],
                    capture_output=True, text=True,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                zip_path = wt / "dist" / "cleanlanguage.zip"
                entries = subprocess.run(
                    ["unzip", "-Z1", str(zip_path)],
                    capture_output=True, text=True, check=True,
                ).stdout.splitlines()
                self.assertIn("SKILL.md", entries)
                self.assertFalse(
                    any(e.startswith("skills/") for e in entries),
                    "the zip must not carry a skills/ subtree: %r" % entries,
                )
                archived = subprocess.run(
                    ["unzip", "-p", str(zip_path), "SKILL.md"],
                    capture_output=True, check=True,
                ).stdout
                blob = subprocess.run(
                    ["git", "-C", str(REPO), "show",
                     "HEAD:cleanlanguage/skills/cleanlanguage/SKILL.md"],
                    capture_output=True, check=True,
                ).stdout
                self.assertEqual(archived, blob)
            finally:
                subprocess.run(
                    ["git", "-C", str(REPO), "worktree", "remove", "--force", str(wt)],
                    capture_output=True, check=True,
                )


if __name__ == "__main__":
    unittest.main()
