#!/usr/bin/env python3
"""Tests for tools/check-orchestration-registry.py.

Pins the structural gate on `.aiqt/orchestration.json`: the committed registry must
stay valid, and every malformation class the hook would classify `bad` (a corrupt
registry has divergent, partly fail-open orchestrator outcomes once armed, and its
`orch_yield_tool` denies scheduling fail-closed even unarmed) must be rejected before
it lands. Runs offline with the standard library; the CI workflow invokes it after the
check itself.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR = HERE / "check-orchestration-registry.py"
REPO_ROOT = HERE.parent
REAL_REGISTRY = REPO_ROOT / ".aiqt" / "orchestration.json"

# A full stage-1 registry with every optional arming key present, used as the accept fixture. The
# paths are illustrative absolutes (the gate validates STRUCTURE, not existence), so this stays
# independent of any one machine's store layout.
STAGE1 = {
    "version": 1,
    "companion_stores": ["/opt/x/private"],
    "record": {
        "findings": "/opt/x/private/open-findings.md",
        "pending_decisions": "/opt/x/private/pending-decisions.md",
        "handoff": "/opt/x/private/session-handoff.md",
    },
    "lease": {"path": "/opt/x/private/session-state.md", "max_age_hours": 24},
    "state_dir": "/opt/x/private/orch-state",
    "dispatch_tools": [],
}


def _run(path) -> int:
    """Run the validator against `path`; return its exit code."""
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        capture_output=True, text=True,
    ).returncode


def _write(tmpdir, payload) -> Path:
    """Write `payload` (a str written verbatim, or any object dumped as JSON) to a temp file."""
    p = Path(tmpdir) / "orchestration.json"
    if isinstance(payload, str):
        p.write_text(payload, encoding="utf-8")
    else:
        p.write_text(json.dumps(payload), encoding="utf-8")
    return p


class RealRegistry(unittest.TestCase):
    def test_committed_registry_is_valid(self):
        # The actual committed registry must always pass; this is the regression guard.
        if not REAL_REGISTRY.exists():
            self.skipTest("no committed .aiqt/orchestration.json")
        self.assertEqual(_run(REAL_REGISTRY), 0)

    def test_committed_registry_is_stage1_armed(self):
        # The change-carries-check on the REAL file: the committed stage-1 registry must carry the
        # recorder/audit arming keys AND validate. This assertion is RED on a tree that still ships the
        # two-key registry (record/lease/state_dir absent) and green only once the arming change lands,
        # so the gate's own test suite fails without the flip it guards.
        if not REAL_REGISTRY.exists():
            self.fail("committed .aiqt/orchestration.json is missing; the stage-1 arming registry "
                      "must be present and armed")
        obj = json.loads(REAL_REGISTRY.read_text(encoding="utf-8"))
        for key in ("record", "lease", "state_dir", "dispatch_tools"):
            self.assertIn(key, obj, "committed registry is missing the stage-1 arming key {!r}".format(key))
        self.assertIn("path", obj["lease"])
        self.assertEqual(_run(REAL_REGISTRY), 0)


class Accepts(unittest.TestCase):
    def test_absent_is_ok(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(Path(d) / "does-not-exist.json"), 0)

    def test_minimal_companion_store(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "companion_stores": ["/opt/x/private"]})), 0)

    def test_version_only(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1})), 0)

    def test_empty_companion_list(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "companion_stores": []})), 0)

    def test_windows_absolute_path_accepted(self):
        # The hook's _is_absolute is OS-agnostic; a drive-and-root Windows path is structurally
        # absolute, so the gate must accept it even running on POSIX, to match what the hook accepts.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "companion_stores": ["C:\\repo"]})), 0)

    def test_full_stage1_fixture(self):
        # A full stage-1 registry with every optional arming key present must validate.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, STAGE1)), 0)

    def test_lease_without_max_age(self):
        # max_age_hours is optional: a lease with only a path is valid.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "lease": {"path": "/opt/x/lease"}})), 0)

    def test_dispatch_tools_with_strings(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "dispatch_tools": ["Workflow", "Task"]})), 0)

    def test_record_sibling_of_state_dir_accepted(self):
        # A record path that is a SIBLING of state_dir (shares a parent but is NOT inside it) is not a
        # collision and must still validate. The prefix check must compare against `state_dir + os.sep`,
        # so "/opt/x/orch-state-extra/..." must not be read as inside "/opt/x/orch-state". (codex QA HIGH)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {
                "version": 1, "state_dir": "/opt/x/orch-state",
                "record": {"handoff": "/opt/x/orch-state-extra/session-handoff.md"},
            })), 0)


class Rejects(unittest.TestCase):
    def _reject(self, payload):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, payload)), 1)

    def test_invalid_json(self):
        self._reject("{ not json")

    def test_top_level_not_object(self):
        self._reject([1, 2, 3])

    def test_version_missing(self):
        self._reject({"companion_stores": ["/opt/x"]})

    def test_version_two(self):
        self._reject({"version": 2})

    def test_version_bool(self):
        # bool is a subclass of int; it must be rejected, mirroring the hook's `type(v) is int`.
        self._reject({"version": True})

    def test_version_string(self):
        self._reject({"version": "1"})

    def test_companion_not_a_list(self):
        self._reject({"version": 1, "companion_stores": "/opt/x"})

    def test_companion_relative_path(self):
        self._reject({"version": 1, "companion_stores": ["relative/path"]})

    def test_companion_empty_string(self):
        self._reject({"version": 1, "companion_stores": [""]})

    def test_companion_non_string(self):
        self._reject({"version": 1, "companion_stores": [123]})

    def test_companion_control_char_low(self):
        self._reject({"version": 1, "companion_stores": ["/opt/x\nevil"]})

    def test_companion_control_char_del(self):
        # 0x7f (DEL) is >= 0x20 but the hook rejects it too; the gate must match.
        self._reject({"version": 1, "companion_stores": ["/opt/x\u007f"]})

    def test_present_but_unreadable_dangling_symlink(self):
        # A dangling registry symlink is present (lstat succeeds) but unreadable (open follows to a
        # missing target); the hook classifies this bad, so the gate must fail, not treat it as absent.
        with tempfile.TemporaryDirectory() as d:
            link = Path(d) / "orchestration.json"
            os.symlink(str(Path(d) / "missing-target.json"), str(link))
            self.assertEqual(_run(link), 1)

    def test_invalid_utf8(self):
        # A non-UTF-8 registry must fail CLEANLY: a FAIL diagnostic on stderr, no traceback. Asserting
        # only exit 1 would pass even without the decode handler (an uncaught traceback also exits 1),
        # so this checks stderr and therefore fails without the handler that catches the read-time
        # UnicodeError.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "orchestration.json"
            p.write_bytes(b"\xff\xfe\x00")
            r = subprocess.run(
                [sys.executable, str(VALIDATOR), str(p)], capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 1)
            self.assertIn("FAIL", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_deeply_nested_json_is_clean_fail(self):
        # Deeply-nested JSON overflows json's recursive scanner with RecursionError, which is NOT a
        # ValueError. Without RecursionError in the parse except it would escape as an uncaught traceback
        # (still exit 1, but an ugly diagnostic); with it the gate emits a clean FAIL. Assert exit 1, a
        # FAIL diagnostic, and NO traceback. The payload is written as raw bytes, not via the dict-based
        # _write helper (which would round-trip through json.dumps).
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "orchestration.json"
            p.write_bytes(b"[" * 100000 + b"]" * 100000)
            r = subprocess.run(
                [sys.executable, str(VALIDATOR), str(p)], capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 1)
            self.assertIn("FAIL", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    # --- stage-1 arming keys ------------------------------------------------------------------------
    def test_unknown_top_level_key(self):
        # `enumerator` is a real stage-2 key deliberately used here: it documents the stage-2 seam.
        # A key outside the stage-1 allowlist lands only with its own gate extension, so it is rejected
        # now rather than shipping an ahead-of-gate registry an installed reader would act on.
        self._reject({"version": 1, "enumerator": {"argv": ["true"]}})

    def test_record_not_a_dict(self):
        self._reject({"version": 1, "record": "/opt/x/findings.md"})

    def test_record_empty(self):
        self._reject({"version": 1, "record": {}})

    def test_record_unknown_subkey(self):
        self._reject({"version": 1, "record": {"bogus": "/opt/x/findings.md"}})

    def test_record_empty_path(self):
        self._reject({"version": 1, "record": {"findings": ""}})

    def test_record_relative_path(self):
        self._reject({"version": 1, "record": {"findings": "relative/findings.md"}})

    def test_record_control_char_path(self):
        self._reject({"version": 1, "record": {"findings": "/opt/x/find\nings.md"}})

    def test_record_nul_in_path(self):
        # A NUL in a declared record path is the load-bearing case: it would raise inside the hook's
        # orch_resume_barrier realpath walk (aiqt_hooks.py:9828) on a PreToolUse event, and that
        # dispatcher fails closed exit 2 on a handler crash. The gate rejects it here.
        self._reject({"version": 1, "record": {"findings": "/opt/x/find" + chr(0) + "ings.md"}})

    def test_lease_missing_path(self):
        self._reject({"version": 1, "lease": {"max_age_hours": 24}})

    def test_lease_max_age_bool(self):
        # bool is a subclass of int; True/False are not durations.
        self._reject({"version": 1, "lease": {"path": "/opt/x/lease", "max_age_hours": True}})

    def test_lease_max_age_zero(self):
        self._reject({"version": 1, "lease": {"path": "/opt/x/lease", "max_age_hours": 0}})

    def test_lease_max_age_negative(self):
        self._reject({"version": 1, "lease": {"path": "/opt/x/lease", "max_age_hours": -1}})

    def test_lease_max_age_string(self):
        self._reject({"version": 1, "lease": {"path": "/opt/x/lease", "max_age_hours": "24"}})

    def test_lease_max_age_over_horizon(self):
        self._reject({"version": 1, "lease": {"path": "/opt/x/lease", "max_age_hours": 9999}})

    def test_lease_unknown_subkey(self):
        # holder_is_session_id is the settled omission: an unknown lease key is rejected, mechanically
        # keeping it out of the committed registry.
        self._reject({"version": 1, "lease": {"path": "/opt/x/lease", "holder_is_session_id": True}})

    def test_state_dir_control_char(self):
        self._reject({"version": 1, "state_dir": "/opt/x/orch\tstate"})

    def test_state_dir_relative(self):
        self._reject({"version": 1, "state_dir": "orch-state"})

    def test_dispatch_tools_not_a_list(self):
        self._reject({"version": 1, "dispatch_tools": "Workflow"})

    def test_dispatch_tools_non_string_entry(self):
        self._reject({"version": 1, "dispatch_tools": ["Workflow", 123]})

    # --- record/lease path colliding with state_dir (codex QA HIGH) ---------------------------------
    # A declared record/lease path ON or INSIDE state_dir collides with the machine-state files the hooks
    # write there: orch_resume_audit opens <state_dir>/resume-barrier.json with mode "w" unconditionally
    # (aiqt_hooks.py:9775, 9783-9785), so such a path would be clobbered by that hook write. The gate
    # rejects the dangerous config. These are RED without the cross-field collision check (the per-key
    # validation accepts each path in isolation).
    def test_record_path_inside_state_dir_rejected(self):
        self._reject({"version": 1, "state_dir": "/opt/x/orch-state",
                      "record": {"handoff": "/opt/x/orch-state/resume-barrier.json"}})

    def test_lease_path_inside_state_dir_rejected(self):
        self._reject({"version": 1, "state_dir": "/opt/x/orch-state",
                      "lease": {"path": "/opt/x/orch-state/session-state.md"}})

    def test_record_path_equal_to_state_dir_rejected(self):
        self._reject({"version": 1, "state_dir": "/opt/x/orch-state",
                      "record": {"handoff": "/opt/x/orch-state"}})

    # --- lone surrogate code points (unencodable to UTF-8) ------------------------------------------
    # A lone surrogate (U+D800..U+DFFF) passes an ord()<0x20-or-0x7f control-char test but CANNOT be
    # UTF-8 encoded, so when the hook resolves such a declared path (os.path.realpath in
    # orch_resume_barrier, aiqt_hooks.py:9828-9830, a PreToolUse event) the encode raises
    # UnicodeEncodeError and the PreToolUse dispatcher fails closed exit 2 (aiqt_hooks.py:10705-10716) --
    # the very route the control-char rejection claims to close. The gate must reject surrogates in every
    # declared-path surface. (codex QA HIGH)
    def test_record_surrogate_path(self):
        self._reject({"version": 1, "record": {"findings": "/opt/x/find" + chr(0xD800) + "ings.md"}})

    def test_companion_surrogate(self):
        self._reject({"version": 1, "companion_stores": ["/opt/x/" + chr(0xD800) + "store"]})

    def test_state_dir_surrogate(self):
        self._reject({"version": 1, "state_dir": "/opt/x/" + chr(0xD800) + "state"})

    def test_lease_path_surrogate(self):
        self._reject({"version": 1, "lease": {"path": "/opt/x/" + chr(0xD800) + "lease"}})

    def test_dispatch_tools_surrogate(self):
        self._reject({"version": 1, "dispatch_tools": ["Workflow", "Ta" + chr(0xD800) + "sk"]})


if __name__ == "__main__":
    unittest.main()
