#!/usr/bin/env python3
"""Behaviour tests for .claude/hooks/ask_mode_guard.py, the repository AskUserQuestion guard.

Each behaviour case runs the guard in a subprocess with python3 -I, passes it a mode file path
through the test-only --mode-file argument, since CI has no /opt/orch-operator, and asserts the exit
code and the verdict the guard prints. Every behaviour case but 1 puts that path under a temporary
directory and sets up what it leads to, or its absence, except that in the 2 owner rename cases it
can lead to a file outside that directory, as described below; the device case uses a path below
/dev/null, since only root can create a device node. The directory that holds the mode file is a
real directory with mode 0755 unless a case sets up another state there. Most cases run the guard
as a script; 7 cases load it as a module in that subprocess and inject a fault before they call
its main function: a read that fails after the open, and, for each of the type, owner and write
checks, 1 case where the file opened is not the one the mode file's path led to before the guard
called os.open, and 1 case where it is not the one the path leads to just after the open; renames
inside the wrapped os.open set up both. The owner rename cases rename a symlink above the
directory that holds the mode file, since the guard requires that directory itself to be a real
directory. The files a
case creates belong to the uid running the tests, so every case passes that uid through the
test-only --expect-owner-uid argument, except the 2 cases that pass another uid or none to test the
expected owner. The owner rename cases need a readable file that another uid
owns: run as root, they create one and give it to uid 65534; otherwise they use the first suitable
file among /etc/passwd, /etc/group, /etc/hosts and the Python interpreter, and skip when none is
suitable. A missing guard fails every behaviour case rather than skipping it, so an absent file
cannot read as a green run. Every deny must carry the complete record-and-continue instruction, and
1 case checks that the vendored orch_ask_guard words that instruction the same way. Because the
behaviour cases bypass the guard's production mode file, 1 case loads the guard without running it
and checks the mode file and owner uid it uses when it receives no argument. Another case reads only
.claude/settings.json and checks every hook, under every event and matcher, whose definition names
ask_mode_guard: exactly 1 must, as the AskUserQuestion entry, with neither test-only argument.

Usage: python3 -I tools/test-ask-mode-guard.py
"""
import ast
import errno
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
GUARD = REPO_ROOT / ".claude" / "hooks" / "ask_mode_guard.py"
SETTINGS = REPO_ROOT / ".claude" / "settings.json"
VENDORED_HOOKS = (REPO_ROOT / "plugin" / "aiqt-guardrails-hooks" / "hooks" / "scripts"
                  / "aiqt_hooks.py")
REGISTERED_COMMAND = "python3 -I \"$CLAUDE_PROJECT_DIR/.claude/hooks/ask_mode_guard.py\""
GUARD_NAME = "ask_mode_guard"
MAX_BYTES = 4096

# What the registered guard reads and expects, since the registration passes no argument.
PRODUCTION_MODE_FILE = "/opt/orch-operator/operating-mode"
PRODUCTION_OWNER_UID = 0

# The whole instruction, so a deny that keeps only its opening words fails.
RECORD_AND_CONTINUE = (
    "RECORD the decision as pending (the registry's pending-decisions surface) with your "
    "recommended option and rationale, then CONTINUE with the next authorized independent item. "
    "If the decision sits at the human-oversight threshold (high-consequence, irreversible, or "
    "outward-facing), record it and HOLD that item; the hold never licenses acting without the "
    "answer.")

# The whole warning for a legacy "attended" record, so a change to its wording fails.
LEGACY_WARNING = ('Repository guard: {} holds the legacy mode "attended", read as '
                  'attended-autonomous; AskUserQuestion allowed. The operator runs `orchmod aa` '
                  'to rewrite the record as attended-autonomous.')

# Loads the guard as a module, which does not run main, and prints what parse_args returns for no
# argument together with the two constants behind it. The -B flag keeps the import from writing
# bytecode under .claude/hooks.
DEFAULTS_PROBE = (
    "import importlib.util, json, sys\n"
    "spec = importlib.util.spec_from_file_location('ask_mode_guard', sys.argv[1])\n"
    "guard = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(guard)\n"
    "mode_file, owner = guard.parse_args([])\n"
    "print(json.dumps({'parse_args': [mode_file, owner], 'MODE_FILE': guard.MODE_FILE,\n"
    "                  'EXPECTED_OWNER_UID': guard.EXPECTED_OWNER_UID}))\n")

# The start of each fault probe: load the guard as a module from sys.argv[1], which does not run main.
LOAD_GUARD = (
    "import errno, importlib.util, os, sys\n"
    "spec = importlib.util.spec_from_file_location('ask_mode_guard', sys.argv[1])\n"
    "guard = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(guard)\n")

# Makes every os.read raise EIO, then runs main on the remaining arguments. The suite has no way to
# make a read of a regular temporary file fail once its open has succeeded, so the probe injects the
# error. main reads the payload through sys.stdin.buffer, not os.read, so only the guard's read of
# the mode file meets the fault.
READ_ERROR_PROBE = LOAD_GUARD + (
    "def failing_read(fd, length):\n"
    "    raise OSError(errno.EIO, os.strerror(errno.EIO))\n"
    "os.read = failing_read\n"
    "sys.exit(guard.main(sys.argv[2:]))\n")

# Wraps os.open so that the entry at sys.argv[3] is renamed over the path sys.argv[4] just before the
# open, when sys.argv[2] is "before", or just after it, when it is "after"; when it is "around",
# sys.argv[3] is renamed over sys.argv[4] just before the open and sys.argv[5] over sys.argv[6] just
# after it. It then runs main on the remaining arguments. The guard opens only the mode file, so the
# renames happen once. A check that looks at the path instead of the open descriptor, on the side of
# the open where the renames leave a file that passes it, then judges a file other than the one the
# guard reads.
SWAP_PROBE = LOAD_GUARD + (
    "when = sys.argv[2]\n"
    "count = 4 if when == 'around' else 2\n"
    "paths = sys.argv[3:3 + count]\n"
    "real_open = os.open\n"
    "def open_with_swap(path, flags, *rest):\n"
    "    if when in ('before', 'around'):\n"
    "        os.rename(paths[0], paths[1])\n"
    "    fd = real_open(path, flags, *rest)\n"
    "    if when == 'after':\n"
    "        os.rename(paths[0], paths[1])\n"
    "    if when == 'around':\n"
    "        os.rename(paths[2], paths[3])\n"
    "    return fd\n"
    "os.open = open_with_swap\n"
    "sys.exit(guard.main(sys.argv[3 + count:]))\n")

# The shape of the host record: a JSON object whose "mode" decides, with members whose values do not.
# The host's only writer, orch-set-mode, run through orchmod, writes exactly 2 values:
# "attended-autonomous" (orchmod aa) and "unattended" (orchmod ua). "attended" is not one of them:
# it is the legacy value, which the guard reads as attended-autonomous with 1 warning.
UNATTENDED_LINE = ('{"mode": "unattended", "phase": "dispatch", "set_by": "orch-operator", '
                   '"set_at": "2026-11-07T00:00:00Z"}\n')
ATTENDED_AUTONOMOUS_LINE = UNATTENDED_LINE.replace('"unattended"', '"attended-autonomous"')
ATTENDED_LINE = UNATTENDED_LINE.replace('"unattended"', '"attended"')
ASK = {"tool_name": "AskUserQuestion", "session_id": "s1", "tool_use_id": "tu1",
       "tool_input": {"questions": [{"question": "Which option?"}]}}

# The open fails with ELOOP both for a symlink at the mode file and for a loop in a directory above
# it, so every case that reaches that error requires the cause that is true of both.
SYMLINK_CAUSE = "is a symlink, or its path holds a symlink loop or too many symlinks"


class AskModeGuard(unittest.TestCase):
    def setUp(self):
        if not GUARD.exists():
            self.fail("repository guard not found: {}".format(GUARD))
        self._tmp = Path(tempfile.mkdtemp(prefix="ask-mode-guard-"))
        self.host_dir = self._tmp / "orch-operator"
        self.host_dir.mkdir()
        # Set explicitly, whatever the umask, since the guard denies a group- or other-writable
        # host directory.
        os.chmod(self.host_dir, 0o755)
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

    def run_probe(self, probe, probe_args=(), mode_file=None):
        """Run a fault probe on the guard for the AskUserQuestion payload, with probe_args, then
        --mode-file and --expect-owner-uid; -B keeps the import from writing bytecode."""
        args = [sys.executable, "-I", "-B", "-c", probe, str(GUARD)] + list(probe_args)
        args += ["--mode-file", str(mode_file or self.mode_file),
                 "--expect-owner-uid", str(os.geteuid())]
        return subprocess.run(args, input=json.dumps(ASK), capture_output=True, text=True, timeout=30)

    def run_swap(self, when, renames, mode_file=None):
        """Run the swap probe with renames, a sequence of (source, target) pairs: 1 pair for
        "before" or "after", 2 for "around"; fail unless every rename took place."""
        args = [when] + [str(path) for pair in renames for path in pair]
        result = self.run_probe(SWAP_PROBE, args, mode_file)
        for source, _target in renames:
            self.assertFalse(os.path.lexists(source), "the probe did not rename {}".format(source))
        return result

    def foreign_file(self):
        """A readable regular file that a uid other than the test's owns and that neither its group
        nor others can write, so that it passes the type and write checks and fails the owner check;
        skips the case without one. Run as root, it is an attended-autonomous record, so only the
        owner check refuses it. Run as another uid, it is a system file such as /etc/passwd or the
        Python interpreter, not a mode record, so a check on its content can refuse it too; the
        owner cases therefore require the owner cause."""
        if os.geteuid() == 0:
            foreign_dir = self._tmp / "foreign"
            foreign_dir.mkdir()
            path = self.write_mode(ATTENDED_AUTONOMOUS_LINE, path=foreign_dir / "operating-mode")
            os.chown(path, 65534, -1)
            return path
        for candidate in ("/etc/passwd", "/etc/group", "/etc/hosts", sys.executable):
            path = Path(os.path.realpath(candidate))
            try:
                info = path.lstat()
            except OSError:
                continue
            if (stat.S_ISREG(info.st_mode) and info.st_uid != os.geteuid()
                    and not info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
                    and os.access(path, os.R_OK)):
                return path
        self.skipTest("no readable file that another uid owns, for the owner check")

    def assert_allows_silently(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "", result.stdout)

    def assert_allows_with_legacy_warning(self, result):
        """An allow with no permissionDecision whose only output is 1 line: the legacy warning."""
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout)
        self.assertEqual(json.loads(result.stdout),
                         {"systemMessage": LEGACY_WARNING.format(self.mode_file)})

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
        # Every deny carries the vendored instruction, so an agent meets one instruction whichever
        # guard denies first.
        self.assertIn(RECORD_AND_CONTINUE, specific["permissionDecisionReason"])
        return specific["permissionDecisionReason"]

    # --- what a valid record decides: the writer's 2 values, the legacy "attended", and other tools
    def test_unattended_record_denies(self):
        self.write_mode(UNATTENDED_LINE)
        reason = self.assert_denies(self.run_guard(), "unattended")
        self.assertIn(RECORD_AND_CONTINUE, reason)
        # Of the denies for a "mode" value, only the unattended reason tells the operator how to
        # take over; the deny for any other value also contains "unattended", so the substring
        # above cannot tell the 2 apart. The file is root-owned and orch-set-mode is its only
        # writer, so the remedy is orchmod.
        self.assertIn("is unattended", reason)
        self.assertIn("the operator runs `orchmod aa`", reason)
        self.assertNotIn("sets \"mode\"", reason)

    def test_attended_autonomous_record_allows_silently(self):
        self.write_mode(ATTENDED_AUTONOMOUS_LINE)
        self.assert_allows_silently(self.run_guard())

    def test_legacy_attended_record_allows_with_one_warning(self):
        # The writer does not write "attended", the legacy value; the guard reads it as
        # attended-autonomous, never as unattended, and prints the whole warning.
        self.write_mode(ATTENDED_LINE)
        self.assert_allows_with_legacy_warning(self.run_guard())

    def test_other_tool_allows_silently_even_when_unattended(self):
        self.write_mode(UNATTENDED_LINE)
        payload = dict(ASK, tool_name="Bash", tool_input={"command": "true"})
        self.assert_allows_silently(self.run_guard(payload))

    def test_members_other_than_mode_do_not_decide(self):
        # With content that passes the whole-content checks, other members, their values, or their
        # absence leave an attended-autonomous record allowed, an unattended record denied, and a
        # legacy attended record allowed with the warning.
        for name, members in (("mode alone", {}),
                              ("other values", {"phase": "maintenance", "set_by": None, "set_at": 0}),
                              ("a nested mode", {"extra": {"mode": "unattended"}})):
            with self.subTest(record=name, mode="attended-autonomous"):
                self.write_mode(json.dumps(dict({"mode": "attended-autonomous"}, **members)) + "\n")
                self.assert_allows_silently(self.run_guard())
            with self.subTest(record=name, mode="unattended"):
                self.write_mode(json.dumps(dict({"mode": "unattended"}, **members)) + "\n")
                self.assert_denies(self.run_guard(), "is unattended")
            with self.subTest(record=name, mode="attended"):
                self.write_mode(json.dumps(dict({"mode": "attended"}, **members)) + "\n")
                self.assert_allows_with_legacy_warning(self.run_guard())

    # --- where the file is, and what it is -----------------------------------------------------------
    def test_absent_host_directory_denies(self):
        # Removing the root-owned host directory must not disarm the guard, so its absence denies.
        host_dir = self._tmp / "no-such-dir"
        cause = "{} is absent, so this host declares no operating-mode".format(host_dir)
        reason = self.assert_denies(self.run_guard(mode_file=host_dir / "operating-mode"), cause)
        self.assertIn("the operator creates {}, owned by root, writable by neither its group nor "
                      "others, and searchable by the session's user, for example with mode 0755, "
                      "runs `orchmod aa`, which sets the host operating-mode to attended-autonomous, "
                      "and lets the session's user read the mode file in it; then "
                      "re-issue.".format(host_dir), reason)

    def test_host_directory_that_cannot_be_checked_denies(self):
        # lstat failing for a reason other than absence, here a parent directory without search
        # permission, must deny naming that failure rather than an absent directory.
        if os.geteuid() == 0:
            self.skipTest("root searches a mode 600 directory, so this case needs a uid other than 0")
        self.write_mode(ATTENDED_AUTONOMOUS_LINE)
        os.chmod(self._tmp, 0o600)
        try:
            result = self.run_guard()
        finally:
            os.chmod(self._tmp, 0o700)
        self.assert_denies(result, "cannot be checked")

    def test_path_component_that_is_a_file_denies(self):
        # A regular file above the host directory makes lstat fail with ENOTDIR, which is not
        # absence, so it must deny naming that error rather than an absent directory.
        blocker = self.write_mode(ATTENDED_AUTONOMOUS_LINE, path=self._tmp / "blocker")
        result = self.run_guard(mode_file=blocker / "orch-operator" / "operating-mode")
        self.assert_denies(result, "cannot be checked: {}".format(os.strerror(errno.ENOTDIR)))

    def test_regular_file_at_the_host_directory_denies(self):
        # lstat finds the file, so the host directory is present but not a directory.
        self.host_dir.rmdir()
        self.write_mode(ATTENDED_AUTONOMOUS_LINE, path=self.host_dir)
        self.assert_denies(self.run_guard(), "{} is not a directory".format(self.host_dir))

    def test_dangling_symlink_at_the_host_directory_denies(self):
        # lstat does not follow the link, so the host directory is present and is a symlink; a
        # check that followed it would read the directory as absent and name that cause.
        self.host_dir.rmdir()
        self.host_dir.symlink_to(self._tmp / "no-such-dir")
        self.assert_denies(self.run_guard(), "{} is a symlink".format(self.host_dir))

    def test_symlink_loop_at_the_host_directory_denies(self):
        # lstat does not follow the loop, so the host directory is present and is a symlink.
        self.host_dir.rmdir()
        self.host_dir.symlink_to(self.host_dir)
        self.assert_denies(self.run_guard(), "{} is a symlink".format(self.host_dir))

    def test_symlink_to_a_directory_at_the_host_directory_denies(self):
        # Whoever controls a symlink at the host directory chooses the record the guard reads, so
        # the guard denies it even when it leads to a real directory with an attended-autonomous
        # or legacy record that passes every check on the file.
        real_dir = self._tmp / "real-dir"
        real_dir.mkdir()
        os.chmod(real_dir, 0o755)
        self.host_dir.rmdir()
        self.host_dir.symlink_to(real_dir)
        for mode, line in (("attended-autonomous", ATTENDED_AUTONOMOUS_LINE),
                           ("attended", ATTENDED_LINE)):
            with self.subTest(mode=mode):
                self.write_mode(line, path=real_dir / "operating-mode")
                self.assert_denies(self.run_guard(), "{} is a symlink".format(self.host_dir))

    def test_host_directory_owned_by_another_uid_denies(self):
        # The test cannot give a directory to another uid without root, so it expects another
        # owner instead. The cause must name the host directory: the mode file, owned by the same
        # uid, would fail the file's owner check too, so only a cause that names the directory
        # shows that the directory's owner check ran. The owner rename cases below test the file's
        # owner check.
        self.write_mode(ATTENDED_AUTONOMOUS_LINE)
        other = os.geteuid() + 1
        self.assert_denies(self.run_guard(owner=other), "{} is owned by uid {}, not uid {}".format(
            self.host_dir, os.geteuid(), other))

    def test_group_writable_host_directory_denies(self):
        # Someone who can write the host directory can replace the mode file in it.
        self.write_mode(ATTENDED_AUTONOMOUS_LINE)
        os.chmod(self.host_dir, 0o775)
        self.assert_denies(self.run_guard(), "{} is writable by group".format(self.host_dir))

    def test_other_writable_host_directory_denies(self):
        self.write_mode(ATTENDED_AUTONOMOUS_LINE)
        os.chmod(self.host_dir, 0o757)
        self.assert_denies(self.run_guard(), "{} is writable by others".format(self.host_dir))

    def test_fifo_at_the_host_directory_denies(self):
        # lstat finds the FIFO, so the host directory is present but not a directory; a check that
        # read a host directory that is not a directory as absent would name the wrong cause.
        self.host_dir.rmdir()
        os.mkfifo(self.host_dir)
        self.assert_denies(self.run_guard(), "{} is not a directory".format(self.host_dir))

    def test_socket_at_the_host_directory_denies(self):
        # As for the FIFO: lstat finds the socket, which is not a directory. The
        # bind fails where the environment refuses Unix sockets, or where the path is longer than a
        # socket address holds, as under a long TMPDIR; the case then cannot set up the state it
        # tests, so it skips, naming the error, and it runs wherever the bind succeeds.
        self.host_dir.rmdir()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            try:
                listener.bind(str(self.host_dir))
            except OSError as error:
                self.skipTest("cannot bind a Unix socket at the host directory: {}".format(error))
            result = self.run_guard()
        finally:
            listener.close()
        self.assert_denies(result, "{} is not a directory".format(self.host_dir))

    def test_device_at_the_host_directory_denies(self):
        # Only root can create a device node, so the case puts the mode file below /dev/null, a
        # character device every Linux host has: lstat finds it, and it is not a directory.
        # Where lstat cannot examine /dev/null, as where the environment does not provide it, the
        # case cannot set up the state it tests, so it skips, naming the error; it also skips where
        # /dev/null is not a character device, and it runs wherever /dev/null is one.
        device = Path("/dev/null")
        try:
            device_mode = device.lstat().st_mode
        except OSError as error:
            self.skipTest("cannot examine /dev/null: {}".format(error))
        if not stat.S_ISCHR(device_mode):
            self.skipTest("/dev/null is not a character device on this host")
        self.assert_denies(self.run_guard(mode_file=device / "operating-mode"),
                           "{} is not a directory".format(device))

    def test_symlink_to_a_file_at_the_host_directory_denies(self):
        # lstat does not follow the link, so the host directory is present and is a symlink, and
        # the attended-autonomous file it leads to never decides.
        target = self.write_mode(ATTENDED_AUTONOMOUS_LINE, path=self._tmp / "real-file")
        self.host_dir.rmdir()
        self.host_dir.symlink_to(target)
        self.assert_denies(self.run_guard(), "{} is a symlink".format(self.host_dir))

    def test_symlink_loop_above_the_host_directory_denies(self):
        # Here lstat itself meets the loop and fails with ELOOP, which is not absence, so it must
        # deny naming that error rather than an absent directory.
        loop = self._tmp / "loop"
        loop.symlink_to(loop)
        result = self.run_guard(mode_file=loop / "orch-operator" / "operating-mode")
        self.assert_denies(result, "cannot be checked: {}".format(os.strerror(errno.ELOOP)))

    def test_host_directory_that_cannot_be_searched_denies(self):
        # lstat of the directory succeeds, since its parent can be searched, and the open of the
        # mode file inside it fails with EACCES, which must deny even over an attended-autonomous
        # record.
        if os.geteuid() == 0:
            self.skipTest("root searches a mode 600 directory, so this case needs a uid other than 0")
        self.write_mode(ATTENDED_AUTONOMOUS_LINE)
        os.chmod(self.host_dir, 0o600)
        try:
            result = self.run_guard()
        finally:
            os.chmod(self.host_dir, 0o700)
        self.assert_denies(result, "is unreadable: {}".format(os.strerror(errno.EACCES)))

    def test_missing_file_with_directory_present_denies(self):
        self.assert_denies(self.run_guard(), "is missing")

    def test_symlink_to_attended_autonomous_file_denies(self):
        target = self.write_mode(ATTENDED_AUTONOMOUS_LINE, path=self._tmp / "real-mode")
        self.mode_file.symlink_to(target)
        self.assert_denies(self.run_guard(), SYMLINK_CAUSE)

    def test_dangling_symlink_at_the_mode_file_denies(self):
        # O_NOFOLLOW refuses the link itself, so a link to nothing is a symlink, not a missing file.
        self.mode_file.symlink_to(self._tmp / "no-such-file")
        self.assert_denies(self.run_guard(), SYMLINK_CAUSE)

    def test_fifo_denies_without_hanging(self):
        os.mkfifo(self.mode_file)
        self.assert_denies(self.run_guard(), "not a regular file")

    def test_directory_at_the_path_denies(self):
        self.mode_file.mkdir()
        self.assert_denies(self.run_guard(), "not a regular file")

    def test_unreadable_file_denies(self):
        if os.geteuid() == 0:
            self.skipTest("root reads a mode 000 file, so this case needs a uid other than 0")
        self.write_mode(ATTENDED_AUTONOMOUS_LINE, mode=0o000)
        self.assert_denies(self.run_guard(), "unreadable")

    def test_read_error_after_open_denies(self):
        # The file opens and passes its checks, then the read fails: that must deny, naming the
        # error, rather than read as an attended-autonomous record.
        self.write_mode(ATTENDED_AUTONOMOUS_LINE)
        self.assert_denies(self.run_probe(READ_ERROR_PROBE),
                           "is unreadable: {}".format(os.strerror(errno.EIO)))

    # --- who owns the file and who can write it ------------------------------------------------------
    def test_default_expects_root_owner(self):
        # Without the test-only argument the guard expects uid 0, as the production registration
        # does; run as another uid, it denies, and the host directory's owner check, which runs
        # first, names the test's uid as the owner.
        self.write_mode(ATTENDED_AUTONOMOUS_LINE)
        result = self.run_guard(owner=False)
        if os.geteuid() == 0:
            self.assert_allows_silently(result)
        else:
            self.assert_denies(result, "owned by uid {}, not uid 0".format(os.geteuid()))

    def test_group_writable_file_denies(self):
        self.write_mode(ATTENDED_AUTONOMOUS_LINE, mode=0o664)
        self.assert_denies(self.run_guard(), "writable by group")

    def test_other_writable_file_denies(self):
        self.write_mode(ATTENDED_AUTONOMOUS_LINE, mode=0o646)
        self.assert_denies(self.run_guard(), "writable by others")

    def test_checks_judge_the_opened_file_not_its_path(self):
        # The opened file is group-writable; the file renamed over its path just after the open is
        # not. The guard denies on group write only if its write check does not look at the path
        # after the open; the cases below cover a look before the open and the other checks.
        self.write_mode(ATTENDED_AUTONOMOUS_LINE, mode=0o664)
        replacement = self.write_mode(ATTENDED_AUTONOMOUS_LINE, path=self.host_dir / "replacement")
        self.assert_denies(self.run_swap("after", [(replacement, self.mode_file)]),
                           "writable by group")

    def test_write_check_judges_the_opened_file_not_an_earlier_look(self):
        # The file at the path before the open passes every check; the group-writable file renamed
        # over it just before the open is the one opened. The guard denies on group write only if
        # its write check does not rely on a look at the path before the open.
        self.write_mode(ATTENDED_AUTONOMOUS_LINE)
        replacement = self.write_mode(ATTENDED_AUTONOMOUS_LINE, mode=0o664,
                                      path=self.host_dir / "replacement")
        self.assert_denies(self.run_swap("before", [(replacement, self.mode_file)]),
                           "writable by group")

    def test_type_check_judges_the_opened_file_not_an_earlier_look(self):
        # A regular attended-autonomous file before the open; a FIFO renamed over it just before the
        # open is the one opened, so only a type check that does not rely on the earlier look denies
        # on type.
        self.write_mode(ATTENDED_AUTONOMOUS_LINE)
        fifo = self.host_dir / "replacement"
        os.mkfifo(fifo)
        os.chmod(fifo, 0o644)
        self.assert_denies(self.run_swap("before", [(fifo, self.mode_file)]), "not a regular file")

    def test_type_check_judges_the_opened_file_not_a_later_look(self):
        # A FIFO is opened; a regular attended-autonomous file renamed over it just after the open
        # passes every check, so only a type check that does not look at the path after the open
        # denies on type.
        os.mkfifo(self.mode_file)
        os.chmod(self.mode_file, 0o644)
        replacement = self.write_mode(ATTENDED_AUTONOMOUS_LINE, path=self.host_dir / "replacement")
        self.assert_denies(self.run_swap("after", [(replacement, self.mode_file)]),
                           "not a regular file")

    def owner_rename_layout(self, foreign):
        """The paths for the owner rename cases, as (link, own_parent, mode_file). The test cannot
        give a file it creates to another uid without root, and the guard requires the host
        directory itself to be a real directory, so the renames move a symlink above it: the mode
        file is link/D/N, where D and N are the names of the foreign file's directory and of the
        file. own_parent holds a real directory D, mode 0755, whose attended-autonomous file N the
        test's uid owns, and link starts as a symlink to own_parent, so the host directory passes
        its checks."""
        own_parent = self._tmp / "own-parent"
        own_dir = own_parent / foreign.parent.name
        own_dir.mkdir(parents=True)
        os.chmod(own_dir, 0o755)
        self.write_mode(ATTENDED_AUTONOMOUS_LINE, path=own_dir / foreign.name)
        link = self._tmp / "link"
        link.symlink_to(own_parent)
        return link, own_parent, link / foreign.parent.name / foreign.name

    def test_owner_check_judges_the_opened_file_not_an_earlier_look(self):
        # When the guard checks the host directory, the mode file's path leads to the file the
        # expected uid owns; just before the open, link is repointed at the parent of the foreign
        # file's directory, so the path leads to the foreign file and the file opened is another
        # uid's. Only an owner check that does not rely on the earlier look denies on owner.
        foreign = self.foreign_file()
        link, _own_parent, mode_file = self.owner_rename_layout(foreign)
        to_foreign = self._tmp / "to-foreign"
        to_foreign.symlink_to(foreign.parent.parent)
        result = self.run_swap("before", [(to_foreign, link)], mode_file)
        self.assert_denies(result, "owned by uid {}, not uid {}".format(
            foreign.stat().st_uid, os.geteuid()))

    def test_owner_check_judges_the_opened_file_not_a_later_look(self):
        # The reverse: link is repointed just before the open, so the file opened is another uid's,
        # and back just after it, so the path leads again to the file the expected uid owns. Only an
        # owner check that does not look at the path after the open denies on owner.
        foreign = self.foreign_file()
        link, own_parent, mode_file = self.owner_rename_layout(foreign)
        to_foreign = self._tmp / "to-foreign"
        to_foreign.symlink_to(foreign.parent.parent)
        to_own = self._tmp / "to-own"
        to_own.symlink_to(own_parent)
        result = self.run_swap("around", [(to_foreign, link), (to_own, link)], mode_file)
        self.assert_denies(result, "owned by uid {}, not uid {}".format(
            foreign.stat().st_uid, os.geteuid()))

    # --- what the file holds -------------------------------------------------------------------------
    def test_unparseable_content_denies(self):
        cases = (
            ("not JSON", "Operating-mode: attended-autonomous\n", "not one JSON document"),
            ("two JSON documents", ATTENDED_AUTONOMOUS_LINE + ATTENDED_AUTONOMOUS_LINE,
             "not one JSON document"),
            ("bad UTF-8", b'{"mode": "attended-autonomous\xff"}\n', "not UTF-8"),
            ("a JSON array", '["attended-autonomous"]\n', "not a JSON object"),
            ("no mode member", '{"phase": "dispatch"}\n', "no \"mode\" member"),
            ("a numeric mode", '{"mode": 1}\n', "\"mode\" is not a string"),
            ("a duplicate mode key",
             '{"mode": "attended-autonomous", "mode": "attended-autonomous"}\n',
             "duplicate key 'mode'"),
            # A repeated key other than "mode", and one inside a nested object, are refused too.
            ("a duplicate key other than mode",
             '{"mode": "attended-autonomous", "phase": "a", "phase": "b"}\n',
             "duplicate key 'phase'"),
            ("a duplicate key in a nested object",
             '{"mode": "attended-autonomous", "extra": {"set_by": "a", "set_by": "a"}}\n',
             "duplicate key 'set_by'"),
        )
        for name, content, cause in cases:
            with self.subTest(case=name):
                self.write_mode(content)
                self.assert_denies(self.run_guard(), cause)

    def test_non_json_constants_deny(self):
        # json.loads accepts NaN, Infinity and -Infinity by default, but JSON has no such values, so
        # an attended-autonomous record that holds one is not one JSON document.
        for name, member in (("NaN", '"phase": NaN'), ("Infinity", '"set_at": Infinity'),
                             ("nested -Infinity", '"extra": [-Infinity]')):
            with self.subTest(case=name):
                self.write_mode('{"mode": "attended-autonomous", ' + member + '}\n')
                self.assert_denies(self.run_guard(), "not one JSON document")

    def test_unknown_mode_values_deny(self):
        # Case and spacing variants of the writer's 2 values and the legacy value, a near miss, and
        # other strings.
        for value in ("Unattended", "ATTENDED-AUTONOMOUS", "attended-autonomous ",
                      "attended_autonomous", "Attended", "ATTENDED", " attended", "attended ",
                      "maintenance", ""):
            with self.subTest(mode=value):
                self.write_mode(json.dumps({"mode": value}) + "\n")
                self.assert_denies(self.run_guard(), "unknown mode")

    def test_content_over_the_size_limit_denies(self):
        padded = (ATTENDED_AUTONOMOUS_LINE.rstrip("\n")
                  + " " * (MAX_BYTES + 1 - len(ATTENDED_AUTONOMOUS_LINE)) + "\n")
        self.assertEqual(len(padded.encode("utf-8")), MAX_BYTES + 1)
        self.write_mode(padded)
        self.assert_denies(self.run_guard(), "over {} bytes".format(MAX_BYTES))

    def test_content_at_the_size_limit_allows(self):
        padded = (ATTENDED_AUTONOMOUS_LINE.rstrip("\n")
                  + " " * (MAX_BYTES - len(ATTENDED_AUTONOMOUS_LINE)) + "\n")
        self.assertEqual(len(padded.encode("utf-8")), MAX_BYTES)
        self.write_mode(padded)
        self.assert_allows_silently(self.run_guard())

    # --- the guard's own failures --------------------------------------------------------------------
    def test_unreadable_payload_denies(self):
        self.write_mode(ATTENDED_AUTONOMOUS_LINE)
        self.assert_denies(self.run_guard(stdin="not json"), "guard internal error")

    def test_unknown_argument_denies(self):
        self.write_mode(ATTENDED_AUTONOMOUS_LINE)
        self.assert_denies(self.run_guard(extra=["--allow"]), "guard internal error")

    def test_payload_that_is_not_an_object_denies_any_tool(self):
        # The guard reads the payload before it looks at the tool, so a payload it cannot read as an
        # object denies even where it names another tool.
        self.write_mode(ATTENDED_AUTONOMOUS_LINE)
        for name, stdin in (("an array", '["tool_name", "Bash"]'), ("a string", '"Bash"'),
                            ("a number", "1"), ("null", "null")):
            with self.subTest(payload=name):
                self.assert_denies(self.run_guard(stdin=stdin), "guard internal error")

    def test_payload_without_a_string_tool_name_denies(self):
        # An object payload that names no tool is as malformed as one that is not an object, so it
        # denies, even while the record says attended-autonomous, rather than passing as some other
        # tool.
        self.write_mode(ATTENDED_AUTONOMOUS_LINE)
        base = {key: value for key, value in ASK.items() if key != "tool_name"}
        for name, payload in (("missing", base), ("null", dict(base, tool_name=None)),
                              ("a number", dict(base, tool_name=1)),
                              ("true", dict(base, tool_name=True)),
                              ("a list", dict(base, tool_name=["AskUserQuestion"])),
                              ("an object", dict(base, tool_name={"name": "AskUserQuestion"}))):
            with self.subTest(tool_name=name):
                self.assert_denies(self.run_guard(payload), "malformed hook payload")

    def test_bad_argument_denies_any_tool(self):
        # The guard reads its arguments before it looks at the tool, so a bad argument denies a Bash
        # call too.
        self.write_mode(ATTENDED_AUTONOMOUS_LINE)
        payload = dict(ASK, tool_name="Bash", tool_input={"command": "true"})
        for name, extra in (("unknown", ["--allow"]), ("unparseable uid", ["--expect-owner-uid", "x"]),
                            ("missing value", ["--mode-file"])):
            with self.subTest(argument=name):
                self.assert_denies(self.run_guard(payload, extra=extra), "guard internal error")


class ProductionDefaults(unittest.TestCase):
    def test_defaults_name_the_host_file_and_root(self):
        # Every behaviour case passes --mode-file, so only this case fails when the mode file the
        # registered guard uses with no argument changes. A change to the owner uid it expects with
        # no argument fails this case and test_default_expects_root_owner.
        result = subprocess.run([sys.executable, "-I", "-B", "-c", DEFAULTS_PROBE, str(GUARD)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout),
                         {"parse_args": [PRODUCTION_MODE_FILE, PRODUCTION_OWNER_UID],
                          "MODE_FILE": PRODUCTION_MODE_FILE,
                          "EXPECTED_OWNER_UID": PRODUCTION_OWNER_UID})


class VendoredWording(unittest.TestCase):
    def test_vendored_ask_guard_gives_the_same_instruction(self):
        # The guard words its instruction as the vendored orch_ask_guard does, so an agent meets
        # one instruction whichever guard denies first. The parser joins adjacent string literals,
        # so the vendored reason reads as one constant however its source lines are split.
        tree = ast.parse(VENDORED_HOOKS.read_text(encoding="utf-8"))
        reasons = [node.value for node in ast.walk(tree)
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)
                   and node.value.startswith("AskUserQuestion BLOCKED:")]
        self.assertEqual(len(reasons), 1, reasons)
        self.assertIn(RECORD_AND_CONTINUE, reasons[0])


class Registration(unittest.TestCase):
    def test_settings_register_the_guard_once_without_test_arguments(self):
        settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        # Every hook under every event and matcher whose definition names the guard, so a second
        # registration of it under another matcher or event, or with a test-only argument, is
        # counted too.
        found = [(event, entry.get("matcher"), hook)
                 for event, entries in settings.get("hooks", {}).items()
                 for entry in entries
                 for hook in entry.get("hooks", [])
                 if GUARD_NAME in json.dumps(hook)]
        self.assertEqual(found, [("PreToolUse", "AskUserQuestion",
                                  {"type": "command", "command": REGISTERED_COMMAND,
                                   "timeout": 10})])
        entries = [entry for entry in settings.get("hooks", {}).get("PreToolUse", [])
                   if entry.get("matcher") == "AskUserQuestion"]
        self.assertEqual(len(entries), 1, entries)
        self.assertEqual(entries[0]["hooks"],
                         [{"type": "command", "command": REGISTERED_COMMAND, "timeout": 10}])
        self.assertNotIn("--mode-file", REGISTERED_COMMAND)
        self.assertNotIn("--expect-owner-uid", REGISTERED_COMMAND)


if __name__ == "__main__":
    unittest.main()
