#!/usr/bin/env python3
"""Behaviour tests for .claude/hooks/ask_mode_guard.py, the repository AskUserQuestion guard.

Each case writes a mode file under a temporary directory, runs the guard as a subprocess with
python3 -I, passes that file through the test-only --mode-file argument, since CI has no
/opt/orch-operator, and asserts the exit code and the verdict the guard prints. The files a case
creates belong to the uid running the tests, so every case passes that uid through the test-only
--expect-owner-uid argument, except the cases that test the owner check itself. A missing guard
fails every behaviour case rather than skipping it, so an absent file cannot read as a green run.
The last case reads only .claude/settings.json and checks that it registers the guard once, with
neither test-only argument.

Usage: python3 -I tools/test-ask-mode-guard.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
GUARD = REPO_ROOT / ".claude" / "hooks" / "ask_mode_guard.py"
SETTINGS = REPO_ROOT / ".claude" / "settings.json"
REGISTERED_COMMAND = "python3 -I \"$CLAUDE_PROJECT_DIR/.claude/hooks/ask_mode_guard.py\""
MAX_BYTES = 4096

# The shape of the host record: a JSON object whose "mode" decides, with members the guard ignores.
UNATTENDED_LINE = ('{"mode": "unattended", "phase": "dispatch", "set_by": "orch-operator", '
                   '"set_at": "2026-11-07T00:00:00Z"}\n')
ATTENDED_LINE = UNATTENDED_LINE.replace('"unattended"', '"attended"')
ASK = {"tool_name": "AskUserQuestion", "session_id": "s1", "tool_use_id": "tu1",
       "tool_input": {"questions": [{"question": "Which option?"}]}}


class AskModeGuard(unittest.TestCase):
    def setUp(self):
        if not GUARD.exists():
            self.fail("repository guard not found: {}".format(GUARD))
        self._tmp = Path(tempfile.mkdtemp(prefix="ask-mode-guard-"))
        self.host_dir = self._tmp / "orch-operator"
        self.host_dir.mkdir()
        self.mode_file = self.host_dir / "operating-mode"

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    # --- helpers -------------------------------------------------------------------------------------
    def write_mode(self, content, mode=0o644, path=None):
        """Write content (str or bytes) to the mode file with an explicit mode, whatever the umask."""
        path = path or self.mode_file
        data = content.encode("utf-8") if isinstance(content, str) else content
        path.write_bytes(data)
        os.chmod(path, mode)
        return path

    def run_guard(self, payload=ASK, mode_file=None, owner=None, extra=(), stdin=None):
        """Run the guard on payload with --mode-file and, unless owner is False, --expect-owner-uid."""
        args = [sys.executable, "-I", str(GUARD), "--mode-file", str(mode_file or self.mode_file)]
        if owner is not False:
            args += ["--expect-owner-uid", str(os.geteuid() if owner is None else owner)]
        args += list(extra)
        return subprocess.run(args, input=json.dumps(payload) if stdin is None else stdin,
                              capture_output=True, text=True, timeout=30)

    def assert_allows_silently(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "", result.stdout)

    def assert_denies(self, result, cause):
        """A PreToolUse deny on exit 0 whose reason and banner both name cause."""
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(result.stdout.strip(), "", "expected a deny verdict, got no output")
        out = json.loads(result.stdout)
        specific = out["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "PreToolUse")
        self.assertEqual(specific["permissionDecision"], "deny")
        self.assertIn(cause, specific["permissionDecisionReason"])
        self.assertIn(cause, out["systemMessage"])
        return specific["permissionDecisionReason"]

    # --- what a valid record decides: unattended denies, attended allows, other tools pass -----------
    def test_unattended_record_denies(self):
        self.write_mode(UNATTENDED_LINE)
        reason = self.assert_denies(self.run_guard(), "unattended")
        self.assertIn("RECORD the decision as pending", reason)
        # Only the unattended reason tells the maintainer how to take over; the deny for any other
        # mode also contains "unattended", so the substring above cannot tell the two apart.
        self.assertIn("is unattended", reason)
        self.assertIn("the maintainer sets \"mode\" to \"attended\"", reason)

    def test_attended_record_allows_silently(self):
        self.write_mode(ATTENDED_LINE)
        self.assert_allows_silently(self.run_guard())

    def test_other_tool_allows_silently_even_when_unattended(self):
        self.write_mode(UNATTENDED_LINE)
        payload = dict(ASK, tool_name="Bash", tool_input={"command": "true"})
        self.assert_allows_silently(self.run_guard(payload))

    # --- where the file is, and what it is -----------------------------------------------------------
    def test_absent_host_directory_allows_with_a_note(self):
        missing = self._tmp / "no-such-dir" / "operating-mode"
        result = self.run_guard(mode_file=missing)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertNotIn("hookSpecificOutput", out)
        self.assertIn("is absent", out["systemMessage"])
        self.assertEqual(len(out["systemMessage"].splitlines()), 1)

    def test_missing_file_with_directory_present_denies(self):
        self.assert_denies(self.run_guard(), "is missing")

    def test_symlink_to_attended_file_denies(self):
        target = self.write_mode(ATTENDED_LINE, path=self._tmp / "real-mode")
        self.mode_file.symlink_to(target)
        self.assert_denies(self.run_guard(), "symlink")

    def test_fifo_denies_without_hanging(self):
        os.mkfifo(self.mode_file)
        self.assert_denies(self.run_guard(), "not a regular file")

    def test_directory_at_the_path_denies(self):
        self.mode_file.mkdir()
        self.assert_denies(self.run_guard(), "not a regular file")

    def test_unreadable_file_denies(self):
        if os.geteuid() == 0:
            self.skipTest("root reads a mode 000 file, so this case needs a uid other than 0")
        self.write_mode(ATTENDED_LINE, mode=0o000)
        self.assert_denies(self.run_guard(), "unreadable")

    # --- who owns the file and who can write it ------------------------------------------------------
    def test_owner_other_than_expected_denies(self):
        self.write_mode(ATTENDED_LINE)
        other = os.geteuid() + 1
        self.assert_denies(self.run_guard(owner=other), "owned by uid {}".format(os.geteuid()))

    def test_default_expects_root_owner(self):
        # Without the test-only argument the guard expects uid 0, as the production registration does.
        self.write_mode(ATTENDED_LINE)
        result = self.run_guard(owner=False)
        if os.geteuid() == 0:
            self.assert_allows_silently(result)
        else:
            self.assert_denies(result, "owned by uid {}, not uid 0".format(os.geteuid()))

    def test_group_writable_file_denies(self):
        self.write_mode(ATTENDED_LINE, mode=0o664)
        self.assert_denies(self.run_guard(), "writable by group")

    def test_other_writable_file_denies(self):
        self.write_mode(ATTENDED_LINE, mode=0o646)
        self.assert_denies(self.run_guard(), "writable by others")

    # --- what the file holds -------------------------------------------------------------------------
    def test_unparseable_content_denies(self):
        cases = (
            ("not JSON", "Operating-mode: attended\n", "not one JSON document"),
            ("two JSON documents", ATTENDED_LINE + ATTENDED_LINE, "not one JSON document"),
            ("bad UTF-8", b'{"mode": "attended\xff"}\n', "not UTF-8"),
            ("a JSON array", '["attended"]\n', "not a JSON object"),
            ("no mode member", '{"phase": "dispatch"}\n', "no \"mode\" member"),
            ("a numeric mode", '{"mode": 1}\n', "\"mode\" is not a string"),
            ("a duplicate mode key", '{"mode": "attended", "mode": "attended"}\n', "duplicate key"),
        )
        for name, content, cause in cases:
            with self.subTest(case=name):
                self.write_mode(content)
                self.assert_denies(self.run_guard(), cause)

    def test_non_json_constants_deny(self):
        # json.loads accepts NaN, Infinity and -Infinity by default, but JSON has no such values, so
        # an attended record that holds one is not one JSON document.
        for name, member in (("NaN", '"phase": NaN'), ("Infinity", '"set_at": Infinity'),
                             ("nested -Infinity", '"extra": [-Infinity]')):
            with self.subTest(case=name):
                self.write_mode('{"mode": "attended", ' + member + '}\n')
                self.assert_denies(self.run_guard(), "not one JSON document")

    def test_unknown_mode_values_deny(self):
        for value in ("Unattended", "ATTENDED", "attended ", "maintenance", ""):
            with self.subTest(mode=value):
                self.write_mode(json.dumps({"mode": value}) + "\n")
                self.assert_denies(self.run_guard(), "unknown mode")

    def test_content_over_the_size_limit_denies(self):
        padded = ATTENDED_LINE.rstrip("\n") + " " * (MAX_BYTES + 1 - len(ATTENDED_LINE)) + "\n"
        self.assertEqual(len(padded.encode("utf-8")), MAX_BYTES + 1)
        self.write_mode(padded)
        self.assert_denies(self.run_guard(), "over {} bytes".format(MAX_BYTES))

    def test_content_at_the_size_limit_allows(self):
        padded = ATTENDED_LINE.rstrip("\n") + " " * (MAX_BYTES - len(ATTENDED_LINE)) + "\n"
        self.assertEqual(len(padded.encode("utf-8")), MAX_BYTES)
        self.write_mode(padded)
        self.assert_allows_silently(self.run_guard())

    # --- the guard's own failures --------------------------------------------------------------------
    def test_unreadable_payload_denies(self):
        self.write_mode(ATTENDED_LINE)
        self.assert_denies(self.run_guard(stdin="not json"), "guard internal error")

    def test_unknown_argument_denies(self):
        self.write_mode(ATTENDED_LINE)
        self.assert_denies(self.run_guard(extra=["--allow"]), "guard internal error")


class Registration(unittest.TestCase):
    def test_settings_register_the_guard_once_without_test_arguments(self):
        settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        entries = [entry for entry in settings.get("hooks", {}).get("PreToolUse", [])
                   if entry.get("matcher") == "AskUserQuestion"]
        self.assertEqual(len(entries), 1, entries)
        self.assertEqual(entries[0]["hooks"],
                         [{"type": "command", "command": REGISTERED_COMMAND, "timeout": 10}])
        self.assertNotIn("--mode-file", REGISTERED_COMMAND)
        self.assertNotIn("--expect-owner-uid", REGISTERED_COMMAND)


if __name__ == "__main__":
    unittest.main()
