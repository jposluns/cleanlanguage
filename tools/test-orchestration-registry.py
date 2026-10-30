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

import ast
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR = HERE / "check-orchestration-registry.py"
REPO_ROOT = HERE.parent
REAL_REGISTRY = REPO_ROOT / ".aiqt" / "orchestration.json"
REAL_HOOKS_JSON = REPO_ROOT / "plugin" / "aiqt-guardrails-hooks" / "hooks" / "hooks.json"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "orchestration-registry.yml"
CONFIG_MD = REPO_ROOT / ".aiqt" / "config.md"
CLAUDE_MD = REPO_ROOT / ".claude" / "CLAUDE.md"
HOOK_PY = REPO_ROOT / "plugin" / "aiqt-guardrails-hooks" / "hooks" / "scripts" / "aiqt_hooks.py"
# The Python interpreter running these tests. It always resolves to a real interpreter, so a fixture whose
# argv[0] is PY is hermetic: it does not depend on /usr/bin/python3 existing on the test host. It is held
# in a plain name so the LaunchIsolation scan below (which looks for sys.executable list displays) judges
# only real gate launches, not enumerator fixtures that deliberately omit "-I".
PY = sys.executable
# The machine-state basenames the hooks write or read inside state_dir, transcribed from the sites in
# plugin/aiqt-guardrails-hooks/hooks/scripts/aiqt_hooks.py (7733, 7756, 8359-8360, 8414, 8424, 8520, 8558,
# 8746-8751, 9300-9301, 9639, 9670, 9715, 9734, 9745-9755, 9775-9777, 9783, 9837, 9864 with 10014-10015),
# plus the "<name>.tmp" sibling that _orch_write_json_atomic writes first (7719-7722). Kept independent of
# the gate constant on purpose, so a name dropped from the gate list fails here; HookStateFileScan below
# also derives the set from the hook source and requires all three to agree.
HOOK_STATE_FILES = (
    "guard-events.jsonl", "turn-state.json", "backlog-checkpoint.json", "checkpoint-init.marker",
    "escape-spoof.json", "escape-spoof.json.surfaced", "forced-exit.jsonl", "pending-asks.jsonl",
    "dispatch-ledger.jsonl", "attestations-validated.json", "forced-exit-surfaced.json",
    "resume-barrier.json", "resume-barrier.json.unused", "write-scope.json",
    "backlog-checkpoint.json.tmp", "checkpoint-init.marker.tmp",
    "attestations-validated.json.tmp", "forced-exit-surfaced.json.tmp",
)

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

# The full stage-2 registry: STAGE1 plus every stage-2 arming key, in the shape the plan proposes. Like
# STAGE1 its paths are illustrative absolutes; the yield_tools roster is checked against the real
# hooks.json of this checkout.
STAGE2 = {
    **STAGE1,
    "enumerator": {
        "argv": [PY, "-I", "tools/orch-enumerate-backlog.py", "/opt/x/private/TODO.md"],
        "timeout": 5,
    },
    "yield_tools": ["ScheduleWakeup", "CronCreate"],
    "mode": {"path": "/opt/x/private/operating-mode.md"},
    "staleness": {"task_hours": 24, "external_hours": 72},
    "escape": {"path": "ESCAPE-ALLOW-YIELD"},
    "attestations": "/opt/x/private/attestations.jsonl",
    "mistakes_register": "/opt/x/private/mistakes-register.jsonl",
}


def _run_full(path) -> subprocess.CompletedProcess:
    """Run the validator against `path`; return the completed process (exit code and stderr)."""
    return subprocess.run(
        [sys.executable, "-I", str(VALIDATOR), str(path)],
        capture_output=True, text=True,
    )


def _run(path) -> int:
    """Run the validator against `path`; return its exit code."""
    return _run_full(path).returncode


def _make_exe(directory, name, target=None) -> str:
    """Create `name` in `directory`: a symlink to `target` when given, else a small executable regular
    file that is not a Python interpreter. Return its absolute path."""
    p = Path(directory) / name
    if target is None:
        p.write_text("#!/bin/false\n", encoding="utf-8")
        p.chmod(0o755)
    else:
        os.symlink(target, str(p))
    return str(p)


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
        # A missing committed registry is a failure, not a skip (round 2 G8): this is the regression guard
        # on the committed file, so its absence must be visible in the test result.
        if not REAL_REGISTRY.exists():
            self.fail("no committed .aiqt/orchestration.json; the regression guard has nothing to check")
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

    def test_full_stage1_fixture(self):
        # A full stage-1 registry with every optional arming key present must validate.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, STAGE1)), 0)

    def test_lease_without_max_age(self):
        # max_age_hours is optional: a lease with only a path is valid. state_dir is declared because a
        # declared lease now requires it (claude QA round 7 co-requirement); this test isolates max_age
        # optionality, not the state_dir requirement.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "lease": {"path": "/opt/x/lease"},
                                             "state_dir": "/opt/x/orch-state"})), 0)

    def test_dispatch_tools_empty_list_accepted(self):
        # The committed shape: an empty list stays valid (it still requires a readable hooks.json).
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "dispatch_tools": []})), 0)

    def test_escape_in_subdirectory_accepted(self):
        # A relative escape path in a subdirectory of the anchor, with no ".." and a non-state basename,
        # stays valid; the hook-state basename rule does not over-reject it.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "state_dir": "/opt/x/orch-state",
                                             "escape": {"path": "operator/ESCAPE-ALLOW-YIELD"}})), 0)

    def test_record_sibling_of_state_dir_accepted(self):
        # A record path that is a SIBLING of state_dir (shares a parent but is NOT inside it) is not a
        # collision and must still validate. The containment check compares component-wise (commonpath),
        # so "/opt/x/orch-state-extra/..." must not be read as inside "/opt/x/orch-state" (their commonpath
        # is /opt/x, not the state_dir). (codex QA HIGH-1)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {
                "version": 1, "state_dir": "/opt/x/orch-state",
                "record": {"handoff": "/opt/x/orch-state-extra/session-handoff.md"},
            })), 0)

    def test_absent_state_dir_path_accepted(self):
        # The best-effort non-directory check (codex QA HIGH-2) must NOT fire when the path does not exist:
        # the gate cannot verify a not-yet-created directory, so an absent state_dir path stays valid.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {
                "version": 1, "state_dir": str(Path(d) / "not-created-yet")})), 0)

    def test_existing_directory_state_dir_accepted(self):
        # A state_dir that EXISTS as a real directory passes the best-effort gate-time type check.
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d) / "orch-state"
            sd.mkdir()
            self.assertEqual(_run(_write(d, {"version": 1, "state_dir": str(sd)})), 0)

    def test_symlink_record_resolving_outside_state_dir_accepted(self):
        # HIGH-1 (codex QA round 6) over-rejection guard: a record path through a symlink that resolves
        # OUTSIDE state_dir must still be ACCEPTED. real dir D is state_dir; a SEPARATE real dir E; sibling
        # symlink L -> E; record.handoff = "<L>/session-handoff.md" resolves to E/session-handoff.md, which
        # is not on or inside D. Both the lexical and the resolved-path checks must accept (exit 0), so the
        # new resolved-path containment does not over-reject a legitimate symlinked record location.
        with tempfile.TemporaryDirectory() as d:
            state_dir = Path(d) / "state"
            state_dir.mkdir()
            elsewhere = Path(d) / "elsewhere"
            elsewhere.mkdir()
            alias = Path(d) / "alias"
            os.symlink(str(elsewhere), str(alias))
            reg = _write(d, {
                "version": 1, "state_dir": str(state_dir),
                "record": {"handoff": str(alias / "session-handoff.md")},
            })
            self.assertEqual(_run(reg), 0)

    def test_absent_state_dir_deep_path_accepted(self):
        # HIGH-2 (codex QA round 5) over-rejection guard: a GENUINELY-ABSENT state_dir (missing leaf AND
        # missing parent) raises FileNotFoundError on lstat, which is absence -> accept (the not-yet-created
        # residual stays disclosed). Only a NON-FileNotFound OSError (ENOTDIR/ENAMETOOLONG/...) is the
        # known-unusable case the round-5 classification rejects, so this genuinely-absent path must stay
        # GREEN after that change. RED would signal the classification over-rejects real absence.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {
                "version": 1, "state_dir": str(Path(d) / "absent-parent" / "state")})), 0)

    # --- stage-2 arming keys ------------------------------------------------------------------------
    def test_full_stage2_fixture(self):
        # The full stage-2 registry validates, including the yield_tools roster against the real
        # orch_yield_tool matcher in hooks.json. Every stage-2 reject fixture is derived from this one.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, STAGE2)), 0)

    def test_escape_relative_accepted(self):
        # A relative escape path joins onto the resolved state_dir, as the hook does (aiqt_hooks.py:7864).
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "state_dir": "/opt/x/orch-state",
                                             "escape": {"path": "ESCAPE-ALLOW-YIELD"}})), 0)

    def test_escape_absolute_under_state_dir_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "state_dir": "/opt/x/orch-state",
                                             "escape": {"path": "/opt/x/orch-state/ESCAPE-ALLOW-YIELD"}})), 0)

    def test_enumerator_and_yield_tools_without_registers_accepted(self):
        # attestations and mistakes_register are optional: the stop and yield guards arm without them.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {
                "version": 1, "state_dir": "/opt/x/orch-state",
                "enumerator": STAGE2["enumerator"], "yield_tools": STAGE2["yield_tools"]})), 0)


class Rejects(unittest.TestCase):
    # claude QA round 8 (MEDIUM, test-isolation): the round-7 gate rule "a declared record/lease requires
    # state_dir" rejects ANY record/lease fixture that omits state_dir, regardless of whether the fixture's
    # OWN targeted check fires -- so a regression of that targeted check would go undetected (proven by
    # mutation). For a reject fixture that declares record/lease but no state_dir, inject a DISJOINT (no
    # collision with the fixture's paths) and ABSENT (the gate's lstat type check stays inert) state_dir, so
    # the round-7 rule is inert here and ONLY the fixture's targeted check can reject it. The two
    # test_*_without_state_dir_rejected tests, whose target IS the rule, opt out with add_state_dir=False.
    _ISO_STATE_DIR = "/opt/orch-isolate-sd"

    def _reject(self, payload, add_state_dir=True):
        if (add_state_dir and isinstance(payload, dict)
                and ("record" in payload or "lease" in payload) and "state_dir" not in payload):
            payload = {**payload, "state_dir": self._ISO_STATE_DIR}
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
                [sys.executable, "-I", str(VALIDATOR), str(p)], capture_output=True, text=True,
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
                [sys.executable, "-I", str(VALIDATOR), str(p)], capture_output=True, text=True,
            )
            self.assertEqual(r.returncode, 1)
            self.assertIn("FAIL", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    # --- stage-1 arming keys ------------------------------------------------------------------------
    def test_unknown_top_level_key(self):
        # A key outside the allowlist lands only with its own gate extension, so it is rejected rather than
        # shipping an ahead-of-gate registry an installed reader would act on. Before stage 2 this case
        # used `enumerator`, which is now allowlisted and covered by its own reject tests below.
        self._reject({"version": 1, "bogus_arming_key": {"argv": ["true"]}})

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
        self._reject({"version": 1, "dispatch_tools": [123]})

    def test_dispatch_tools_outside_matcher(self):
        # codex QA F3: Workflow is not in the orch_dispatch_ledger PostToolUse matcher ("Bash|TaskOutput",
        # hooks.json:278), so the hook never sees that tool and the entry would be a silent no-op.
        self._reject({"version": 1, "dispatch_tools": ["Workflow"]})

    def test_dispatch_tools_bash_rejected(self):
        # Round 2 G5: "Bash" is inside the matcher, but listing it makes the hook treat every Bash call,
        # foreground included, as a dispatch and record it (aiqt_hooks.py:9279-9280). The rejection names
        # that hook line, so this cannot pass on some other rule.
        with tempfile.TemporaryDirectory() as d:
            r = _run_full(_write(d, {"version": 1, "dispatch_tools": ["Bash"]}))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("aiqt_hooks.py:9279-9280", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_dispatch_tools_taskoutput_rejected(self):
        # Round 2 G5: "TaskOutput" is inside the matcher, but the hook routes it to its completion branch
        # (aiqt_hooks.py:9264) before it reads the list (aiqt_hooks.py:9277), so the entry is inert.
        with tempfile.TemporaryDirectory() as d:
            r = _run_full(_write(d, {"version": 1, "dispatch_tools": ["TaskOutput"]}))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("aiqt_hooks.py:9264", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

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

    def test_record_without_state_dir_rejected(self):
        # claude QA round 7 HIGH: a declared `record` with NO `state_dir` must be rejected. Without state_dir
        # the hooks fall back to the XDG-default orch state dir (aiqt_hooks.py:7638-7651) that this gate never
        # sees, and orch_resume_audit clobbers a record path landing inside it. RED before the co-requirement
        # (the gate exited 0 accepting record-without-state_dir).
        self._reject({"version": 1, "record": {
            "handoff": "/home/x/.local/state/aiqt-guardrails/orch/deadbeef/resume-barrier.json"}},
            add_state_dir=False)

    def test_lease_without_state_dir_rejected(self):
        # claude QA round 7 HIGH (sibling): a declared `lease` with NO `state_dir` must be rejected for the
        # same reason -- lease.path can land in the same unseen XDG-default state dir. RED before the fix.
        self._reject({"version": 1, "lease": {"path": "/opt/x/lease.md", "max_age_hours": 24}},
                     add_state_dir=False)

    # --- codex QA round 4: path-spelling ALIASES, over-long paths, non-dir state_dir ----------------
    # These are RED against the round-3 normpath+startswith collision check (which accepted the aliases)
    # and against the round-3 path validation (which had no length or state_dir-type check).
    def test_state_dir_root_alias_collision_rejected(self):
        # HIGH-1: state_dir "/" + a record path directly under it. The round-3 check accepted this because
        # norm_state_dir "/" + os.sep = "//", which "/resume-barrier.json" does not start with. The
        # commonpath check rejects it (commonpath(["/resume-barrier.json","/"]) == "/" == state_dir).
        self._reject({"version": 1, "state_dir": "/",
                      "record": {"handoff": "/resume-barrier.json"}})

    def test_double_slash_collision_in_record_rejected(self):
        # HIGH-1: a leading-double-slash spelling of an inside-state_dir record path. POSIX normpath
        # PRESERVES a leading "//", so the round-3 startswith missed it; _norm_pathspell collapses it.
        self._reject({"version": 1, "state_dir": "/opt/x/orch-state",
                      "record": {"handoff": "//opt/x/orch-state/resume-barrier.json"}})

    def test_double_slash_collision_in_state_dir_rejected(self):
        # HIGH-1: the double-slash on the state_dir side instead; both spellings must reject.
        self._reject({"version": 1, "state_dir": "//opt/x/orch-state",
                      "lease": {"path": "/opt/x/orch-state/session-state.md"}})

    def test_lexical_collision_branch_symlink_out_of_state_dir(self):
        # change-carries-check for the LEXICAL containment branch (claude QA round 10, mutation survivor).
        # Disabling the lexical branch while keeping the realpath branch leaves the other collision fixtures
        # green, because os.path.realpath already normalizes their "//"/".." aliases, so the resolved branch
        # subsumes them. THIS fixture rejects ONLY via the lexical branch: a record path lexically INSIDE
        # state_dir but whose symlink component RESOLVES OUTSIDE it. The lexical check (no symlink resolution)
        # sees it inside and rejects; the realpath check resolves the symlink out and would accept. So the
        # gate exits 1 here only while the lexical branch is present -- reverting that branch flips this RED.
        with tempfile.TemporaryDirectory() as sd, \
                tempfile.TemporaryDirectory() as outside, \
                tempfile.TemporaryDirectory() as reg:
            os.symlink(outside, os.path.join(sd, "link-out"))
            payload = {"version": 1, "state_dir": sd,
                       "record": {"handoff": os.path.join(sd, "link-out", "f")}}
            self.assertEqual(_run(_write(reg, payload)), 1)

    def test_overlong_state_dir_component_rejected(self):
        # HIGH-2: a path component over NAME_MAX (255) bytes. At runtime, lstat(<state_dir>/write-scope.json)
        # would raise ENAMETOOLONG, the write-scope reader would classify it 'bad', and an armed session
        # would deny every covered write persistently; the gate rejects the over-long string at author time.
        self._reject({"version": 1, "state_dir": "/opt/" + "a" * 256})

    def test_overlong_record_component_rejected(self):
        # HIGH-2: the same over-long component in a record path.
        self._reject({"version": 1, "record": {"findings": "/opt/" + "a" * 256}})

    def test_overlong_component_with_backslash_rejected(self):
        # HIGH-2 (codex QA round 6): on POSIX a backslash is a VALID filename character, so
        # "a"*150 + "\\" + "a"*150 is ONE 301-byte POSIX component, over NAME_MAX (255). Round 5 split it AT
        # the backslash and wrongly accepted it. Since codex QA F6 the Windows-shape rule rejects any
        # backslash before the length checks run, so this fixture now pins that an over-long backslash
        # component can never be accepted by either route.
        comp = "a" * 150 + "\\" + "a" * 150  # 301 bytes, ONE POSIX component
        self.assertEqual(len(comp.encode()), 301, "fixture must be a 301-byte single POSIX component")
        self._reject({"version": 1, "record": {"findings": "/opt/x/" + comp}})

    def test_lease_path_at_path_max_rejected(self):
        # codex QA round 8: PATH_MAX (4096) INCLUDES the NUL, so a path of exactly 4096 bytes is UNUSABLE
        # (os.stat -> ENAMETOOLONG at runtime). The whole-path check must reject >= PATH_MAX, not just
        # > PATH_MAX. Every component is <= NAME_MAX and state_dir is explicit+disjoint, so ONLY the
        # whole-path length check can reject. RED against the `> PATH_MAX` check (exit 0).
        base = "/" + "".join("a" * 255 + "/" for _ in range(15))  # 3841 bytes, ends with "/"
        p4096 = base + "a" * (4096 - len(base.encode()))
        self.assertEqual(len(p4096.encode()), 4096, "fixture must be exactly PATH_MAX bytes")
        self._reject({"version": 1, "state_dir": "/opt/orch-isolate-sd",
                      "lease": {"path": p4096}})

    def test_lease_path_one_below_path_max_accepted(self):
        # The true maximum usable path is PATH_MAX - 1 (4095) bytes; it must still be ACCEPTED (not
        # over-rejected by the >= change). Same shape, one byte shorter.
        base = "/" + "".join("a" * 255 + "/" for _ in range(15))
        p4095 = base + "a" * (4095 - len(base.encode()))
        self.assertEqual(len(p4095.encode()), 4095)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "state_dir": "/opt/orch-isolate-sd",
                                             "lease": {"path": p4095}})), 0)

    def test_state_dir_existing_non_directory_rejected(self):
        # HIGH-2 best-effort: a state_dir that EXISTS at gate time as a regular file (the "/etc/passwd"
        # shape) is rejected. A real temp regular file is created and state_dir points at it. At runtime
        # write_scope_guard._load_write_scope would read <file>/write-scope.json -> ENOTDIR -> 'bad' -> a
        # persistent covered-write denial; the gate catches the gate-time type. RED without the fix.
        with tempfile.TemporaryDirectory() as d:
            real_file = Path(d) / "state-is-a-file"
            real_file.write_text("not a directory\n", encoding="utf-8")
            self.assertEqual(_run(_write(d, {"version": 1, "state_dir": str(real_file)})), 1)

    # --- codex QA round 5: derived-path reserve (HIGH-1) and known-unusable state_dir (HIGH-2) -------
    def test_state_dir_derived_path_reserve_rejected(self):
        # HIGH-1: a state_dir WITHIN PATH_MAX whose length leaves no room for the machine-state files the
        # hooks WRITE under it. Every component is <= NAME_MAX and the whole path <= PATH_MAX, so the
        # per-component and whole-path checks BOTH pass; only the state_dir-specific reserve check rejects.
        # At runtime lstat(<state_dir>/write-scope.json) would raise ENAMETOOLONG, classify the write-scope
        # declaration 'bad', and drive a persistent covered-write denial. RED without STATE_DERIVED_RESERVE.
        seg = "a" * 255  # NAME_MAX
        sd = "/" + "/".join([seg] * 15) + "/" + "a" * 244  # 4085 bytes
        self.assertLessEqual(len(sd.encode()), 4096, "fixture must stay within PATH_MAX")
        self.assertGreater(len(sd.encode()) + 1 + 64, 4096, "fixture must overflow the derived reserve")
        self._reject({"version": 1, "state_dir": sd})

    def test_state_dir_path_through_regular_file_rejected(self):
        # HIGH-2: a state_dir whose path runs THROUGH a regular file (the "/etc/passwd/state" shape). lstat
        # raises ENOTDIR (a NON-FileNotFound OSError), which round-4 SWALLOWED as absence and accepted. The
        # round-5 classification treats any non-FileNotFound stat fault as known-unusable and rejects, since
        # the hook would hit the same ENOTDIR at runtime reading <state_dir>/write-scope.json -> 'bad' -> a
        # persistent covered-write denial. RED without the fix. Hermetic: a real temp regular file stands in
        # for /etc/passwd (verified at source: os.lstat("/etc/passwd/state") raises ENOTDIR).
        with tempfile.TemporaryDirectory() as d:
            real_file = Path(d) / "passwd"
            real_file.write_text("root:x:0:0:root:/root:/bin/sh\n", encoding="utf-8")
            self.assertEqual(_run(_write(d, {
                "version": 1, "state_dir": str(real_file / "state")})), 1)

    def test_state_dir_trailing_slash_on_regular_file_rejected(self):
        # HIGH-2: the "/etc/passwd/" shape -- a trailing separator on a path that IS a regular file also
        # makes lstat raise ENOTDIR, not FileNotFoundError, so round-4 swallowed it as absence too. Round-5
        # rejects it. RED without the fix. (verified at source: os.lstat("/etc/passwd/") raises ENOTDIR.)
        with tempfile.TemporaryDirectory() as d:
            real_file = Path(d) / "passwd"
            real_file.write_text("root:x:0:0:root:/root:/bin/sh\n", encoding="utf-8")
            self.assertEqual(_run(_write(d, {
                "version": 1, "state_dir": str(real_file) + "/"})), 1)

    # --- codex QA round 6: existing symlink alias defeats the LEXICAL containment check --------------
    def test_symlink_alias_record_into_state_dir_rejected(self):
        # HIGH-1 (codex QA round 6): an EXISTING symlink makes two DIFFERENT spellings resolve to the same
        # file, so a record path that LEXICALLY looks like a sibling of state_dir actually resolves ONTO a
        # machine-state file inside it. Hermetic reproduction: real dir D is state_dir; sibling symlink
        # L -> D; record.handoff = "<L>/resume-barrier.json". Lexically norm(L/...) and norm(D) share only
        # their parent tmp dir (commonpath != state_dir), so the lexical check ACCEPTS. The resolved-path
        # check realpath's both -- realpath(L/resume-barrier.json) == realpath(D)/resume-barrier.json,
        # inside realpath(D) -- and REJECTS. RED without the resolved-path check (gate would exit 0).
        with tempfile.TemporaryDirectory() as d:
            real_dir = Path(d) / "state"
            real_dir.mkdir()
            alias = Path(d) / "alias"
            os.symlink(str(real_dir), str(alias))
            reg = _write(d, {
                "version": 1, "state_dir": str(real_dir),
                "record": {"handoff": str(alias / "resume-barrier.json")},
            })
            self.assertEqual(_run(reg), 1)

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
        self._reject({"version": 1, "dispatch_tools": ["Ba" + chr(0xD800) + "sh"]})

    # --- stage-2 arming keys ------------------------------------------------------------------------
    # Each fixture is the full STAGE2 registry (which the gate accepts, see Accepts.test_full_stage2_fixture)
    # with exactly one key replaced or dropped, so only the targeted stage-2 rule can reject it. On the
    # stage-1 gate every one of these exits 1 for the wrong reason (unknown top-level key); with the key
    # allowlisted but its rule absent, each exits 0 or crashes, so each is RED without its own rule. These
    # use the stricter _reject_clean, so a traceback from later code can never stand in for the rule.
    _DROP = object()

    def _reject_clean(self, payload, add_state_dir=True):
        # Stricter than _reject: exit 1 with a clean FAIL diagnostic and no traceback.
        if (add_state_dir and isinstance(payload, dict)
                and ("record" in payload or "lease" in payload) and "state_dir" not in payload):
            payload = {**payload, "state_dir": self._ISO_STATE_DIR}
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, "-I", str(VALIDATOR), str(_write(d, payload))],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("FAIL", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def _reject_stage2(self, changes):
        payload = copy.deepcopy(STAGE2)
        for key, value in changes.items():
            if value is self._DROP:
                payload.pop(key, None)
            else:
                payload[key] = value
        self._reject_clean(payload)

    def _enum(self, argv=None, **extra):
        spec = {"argv": list(STAGE2["enumerator"]["argv"]) if argv is None else argv, "timeout": 5}
        spec.update(extra)
        return spec

    def test_enumerator_not_an_object(self):
        # A list holding the key names passes the subkey and argv-presence checks, so only the object
        # type check rejects it cleanly.
        self._reject_stage2({"enumerator": ["argv", "timeout"]})

    def test_enumerator_argv_empty(self):
        self._reject_stage2({"enumerator": self._enum(argv=[])})

    def test_enumerator_argv_not_a_list(self):
        self._reject_stage2({"enumerator": self._enum(argv="/usr/bin/python3 tools/x.py")})

    def test_enumerator_argv_contains_empty_string(self):
        self._reject_stage2({"enumerator": self._enum(argv=["/usr/bin/python3", "-I", "", "tools/x.py"])})

    def test_enumerator_argv0_relative(self):
        # The hook runs argv with no shell (aiqt_hooks.py:7976); a bare interpreter name resolves through
        # the session PATH, an ambient binding the registry cannot pin.
        self._reject_stage2({"enumerator": self._enum(argv=["python3", "-I", "tools/x.py"])})

    def test_enumerator_argv_control_char(self):
        self._reject_stage2({"enumerator": self._enum(argv=["/usr/bin/python3", "-I", "tools/x\n.py"])})

    def _run_stage2_enum(self, argv):
        # Run the gate on STAGE2 with only the enumerator argv replaced; return the completed process, so a
        # test can assert which rule rejected the fixture, not only that something did.
        payload = copy.deepcopy(STAGE2)
        payload["enumerator"] = self._enum(argv=argv)
        with tempfile.TemporaryDirectory() as d:
            return _run_full(_write(d, payload))

    def _assert_enum_rejected_by(self, argv, needle):
        r = self._run_stage2_enum(argv)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn(needle, r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_enumerator_python_without_isolation(self):
        # codex QA F7: a Python argv[0] must be followed by exactly "-I"; a missing flag, a different flag,
        # or no argv[1] at all is rejected. Each fixture is otherwise valid. The interpreters are the test
        # interpreter itself and temporary symlinks to it named python3.12 and python, so every argv[0]
        # resolves on any host and only the isolation rule can reject it.
        with tempfile.TemporaryDirectory() as d:
            py312 = _make_exe(d, "python3.12", os.path.realpath(PY))
            pybare = _make_exe(d, "python", os.path.realpath(PY))
            for argv in ([PY, "tools/x.py", "/opt/x/private/TODO.md"],
                         [py312, "-E", "tools/x.py"],
                         [pybare, "-P", "-I", "tools/x.py"],
                         [PY]):
                with self.subTest(argv=argv):
                    self._assert_enum_rejected_by(argv, "is a Python interpreter")

    def test_enumerator_symlink_alias_requires_isolation(self):
        # Round 2 G2, kept under the round 3 R4 allowlist: a symlink alias of the Python interpreter whose
        # own name is not an interpreter name is judged by what it resolves to. Without "-I" it is
        # rejected; with "-I" it is accepted.
        with tempfile.TemporaryDirectory() as d:
            alias = _make_exe(d, "enumerate-runner", os.path.realpath(PY))
            self.assertFalse(os.path.basename(alias).startswith("python"))
            self._assert_enum_rejected_by([alias, "tools/x.py", "/opt/x/private/TODO.md"],
                                          "is a Python interpreter")
            r = self._run_stage2_enum([alias, "-I", "tools/x.py", "/opt/x/private/TODO.md"])
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_enumerator_launchers_rejected(self):
        # Round 3 R4: the gate admits only an isolated Python interpreter as argv[0], so a launcher that
        # would run Python for it (env, nice, timeout) is rejected by its resolved name, however the Python
        # launch behind it is spelled, including one with no *.py operand, which the withdrawn wrapper-name
        # blocklist admitted. Each launcher is a temporary regular file and a temporary symlink to it under
        # a neutral name; the real host binaries are checked too where the host has them.
        with tempfile.TemporaryDirectory() as d:
            cases = []
            for name in ("env", "nice", "timeout"):
                exe = _make_exe(d, name)
                alias = _make_exe(d, "runner-" + name, exe)
                cases.append([exe, PY, "-I", "tools/x.py"])
                cases.append([alias, PY, "tools/enumerate"])
                host = os.path.join("/usr/bin", name)
                if os.path.exists(host):
                    cases.append([host, PY, "tools/enumerate"])
            cases.append([os.path.join(d, "timeout"), "5", PY, "tools/enumerate"])
            for argv in cases:
                with self.subTest(argv=argv):
                    self._assert_enum_rejected_by(argv, "is not a Python interpreter")

    def test_enumerator_shells_rejected(self):
        # Round 3 R4: a shell argv[0] runs a script whose own interpreter launch the gate cannot see.
        with tempfile.TemporaryDirectory() as d:
            for name in ("sh", "bash", "dash", "zsh", "ksh"):
                shell = _make_exe(d, name)
                with self.subTest(shell=name):
                    self._assert_enum_rejected_by([shell, "tools/enumerate.sh", "/opt/x/private/TODO.md"],
                                                  "is not a Python interpreter")

    def test_enumerator_renamed_shell_script_rejected(self):
        # Round 3 R4: a shell script under a neutral name, which could itself start Python unisolated, is
        # rejected whatever follows it, and so is a script named *.py run directly through its shebang.
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / "enumerate-backlog"
            script.write_text("#!/bin/sh\nexec python3 tools/orch-enumerate-backlog.py\n", encoding="utf-8")
            script.chmod(0o755)
            shebang_py = _make_exe(d, "enumerate.py")
            for argv in ([str(script)],
                         [str(script), "-I", "tools/x.py"],
                         [str(script), "/opt/x/private/TODO.md"],
                         [shebang_py, "/opt/x/private/TODO.md"]):
                with self.subTest(argv=argv):
                    self._assert_enum_rejected_by(argv, "is not a Python interpreter")

    def test_enumerator_script_operand_required(self):
        # Round 3 R4: after "-I", argv[2] must be a script path ending in ".py" that is not an option, so
        # "-c", "-m", a further option, a script not named *.py, or no script at all is rejected. The
        # control, the same interpreter running a *.py script, is accepted, so only this rule rejects them.
        cases = ([PY, "-I"],
                 [PY, "-I", "-c", "print(1)"],
                 [PY, "-I", "-m", "json.tool"],
                 [PY, "-I", "-mtools.py"],
                 [PY, "-I", "-E", "tools/x.py"],
                 [PY, "-I", "tools/enumerate"],
                 [PY, "-I", "tools/enumerate.pyc"])
        for argv in cases:
            with self.subTest(argv=argv):
                self._assert_enum_rejected_by(argv, "must be a script path ending in")
        r = self._run_stage2_enum([PY, "-I", "tools/x.py", "/opt/x/private/TODO.md"])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_enumerator_interpreter_name_allowlist(self):
        # Round 3 R4: the resolved basename of argv[0] must fully match python, python3, or python3.N with
        # an optional one-letter build suffix. The fixtures are regular files the gate never executes, which
        # also pins the disclosed residual: a file under an allowlisted name is admitted on that name.
        with tempfile.TemporaryDirectory() as d:
            for name in ("python", "python3", "python3.12", "python3.13t"):
                exe = _make_exe(d, name)
                with self.subTest(accepted=name):
                    r = self._run_stage2_enum([exe, "-I", "tools/x.py", "/opt/x/private/TODO.md"])
                    self.assertEqual(r.returncode, 0, r.stderr)
            for name in ("pypy3", "python2.7", "python3-config", "ipython3", "python3.12.sh", "pythonw"):
                exe = _make_exe(d, name)
                with self.subTest(rejected=name):
                    self._assert_enum_rejected_by([exe, "-I", "tools/x.py"], "is not a Python interpreter")

    def test_enumerator_unresolvable_argv0_rejected(self):
        # Round 2 G2: an argv[0] that cannot be resolved (absent, or a dangling symlink) is a
        # cannot-evaluate, so the gate rejects it rather than guess whether it is a Python interpreter.
        with tempfile.TemporaryDirectory() as d:
            dangling = _make_exe(d, "enumerate-runner", os.path.join(d, "missing-target"))
            for argv in (["/opt/x/does-not-exist/python3", "-I", "tools/x.py"],
                         [dangling, "-I", "tools/x.py"]):
                with self.subTest(argv=argv):
                    self._assert_enum_rejected_by(argv, "cannot be resolved")

    def test_enumerator_windows_shaped_operands(self):
        # codex QA F6: the hook runs argv verbatim on POSIX with cwd at the repository root
        # (aiqt_hooks.py:7976), so a Windows-shaped operand is a relative POSIX name, not the path it
        # spells. A drive-relative "C:TODO.md" and a backslash relative path are not absolute, so only the
        # Windows-shape rule can reject them. (A drive-absolute operand such as "C:/backlog/TODO.md" was
        # already rejected before F6: it joins the state_dir collision list, where mixing it with the POSIX
        # state_dir makes commonpath raise, which the gate treats as a collision.)
        for argv in (["/usr/bin/python3", "-I", "tools/x.py", "C:TODO.md"],
                     ["/usr/bin/python3", "-I", "tools/x.py", "backlog\\TODO.md"],
                     ["/usr/bin/python3", "-I", "tools\\x.py"],
                     ["C:\\Python\\python.exe", "-I", "tools/x.py"]):
            with self.subTest(argv=argv):
                self._reject_stage2({"enumerator": self._enum(argv=argv)})

    def test_enumerator_timeout_absent(self):
        spec = self._enum()
        del spec["timeout"]
        self._reject_stage2({"enumerator": spec})

    def test_enumerator_timeout_60(self):
        # 60 is inside the hook window (0, 600] but overruns the 10 second hook budget in hooks.json.
        self._reject_stage2({"enumerator": self._enum(timeout=60)})

    def test_enumerator_timeout_bool(self):
        self._reject_stage2({"enumerator": self._enum(timeout=True)})

    def test_enumerator_timeout_zero(self):
        self._reject_stage2({"enumerator": self._enum(timeout=0)})

    def test_enumerator_unknown_subkey(self):
        self._reject_stage2({"enumerator": self._enum(shell=True)})

    def test_enumerator_backlog_operand_inside_state_dir(self):
        # An absolute operand (the backlog file) joins the state_dir collision list.
        self._reject_stage2({"enumerator": self._enum(argv=[
            "/usr/bin/python3", "-I", "tools/x.py", "/opt/x/private/orch-state/TODO.md"])})

    def test_enumerator_without_state_dir(self):
        # Opts out of the injected isolation state_dir: the target here IS the state_dir requirement. The
        # enumerator is otherwise valid, so only that requirement can reject it.
        self._reject_clean({"version": 1, "enumerator": self._enum()}, add_state_dir=False)

    def test_other_stage2_keys_without_state_dir(self):
        # The same requirement for every other STATE_DIR_REQUIRED_BY key, each otherwise valid.
        for key in ("yield_tools", "mode", "escape", "attestations", "mistakes_register"):
            with self.subTest(key=key):
                self._reject_clean({"version": 1, key: STAGE2[key]}, add_state_dir=False)

    def test_yield_tools_not_a_list(self):
        # The string case is also caught by the matcher check (each character is no tool name); the
        # integer case is caught only by the list type check.
        for value in ("ScheduleWakeup", 5):
            with self.subTest(value=value):
                self._reject_stage2({"yield_tools": value})

    def test_yield_tools_outside_matcher(self):
        # Bash is not in the orch_yield_tool matcher, so the hook would never judge it as a yield.
        self._reject_stage2({"yield_tools": ["ScheduleWakeup", "Bash"]})

    def test_yield_tools_duplicate(self):
        self._reject_stage2({"yield_tools": ["ScheduleWakeup", "ScheduleWakeup"]})

    def test_mode_not_an_object(self):
        # The string case is also caught by the subkey check; the list holding "path" only by the object
        # type check.
        for value in ("/opt/x/private/operating-mode.md", ["path"]):
            with self.subTest(value=value):
                self._reject_stage2({"mode": value})

    def test_mode_without_path(self):
        self._reject_stage2({"mode": {}})

    def test_mode_extra_key(self):
        self._reject_stage2({"mode": {"path": "/opt/x/private/operating-mode.md", "default": "attended"}})

    def test_mode_path_relative(self):
        self._reject_stage2({"mode": {"path": "private/operating-mode.md"}})

    def test_mode_path_inside_state_dir(self):
        self._reject_stage2({"mode": {"path": "/opt/x/private/orch-state/operating-mode.md"}})

    def test_attestations_not_a_string(self):
        self._reject_stage2({"attestations": {"path": "/opt/x/private/attestations.jsonl"}})

    def test_attestations_relative(self):
        self._reject_stage2({"attestations": "private/attestations.jsonl"})

    def test_attestations_inside_state_dir(self):
        self._reject_stage2({"attestations": "/opt/x/private/orch-state/attestations.jsonl"})

    def test_attestations_anchor_component_overlong(self):
        # A 250-byte final component is within NAME_MAX, but the <path>.anchor file the hook opens adds 7
        # bytes and exceeds it; only the anchor length check rejects this.
        self._reject_stage2({"attestations": "/opt/x/private/" + "a" * 250})

    def test_attestations_anchor_on_state_dir(self):
        # The register itself sits outside state_dir, but its <path>.anchor authority (aiqt_hooks.py:9541)
        # lands exactly on it; only the anchor entry in the collision list can reject this.
        self._reject_stage2({"state_dir": "/opt/x/private/at.anchor",
                             "attestations": "/opt/x/private/at"})

    def test_mistakes_register_not_a_string(self):
        self._reject_stage2({"mistakes_register": 5})

    def test_mistakes_register_inside_state_dir(self):
        self._reject_stage2({"mistakes_register": "/opt/x/private/orch-state/mistakes-register.jsonl"})

    def test_staleness_not_an_object(self):
        # The string "24" is also caught by the subkey check; the list holding "task_hours" only by the
        # object type check.
        for value in ("24", ["task_hours"]):
            with self.subTest(value=value):
                self._reject_stage2({"staleness": value})

    def test_staleness_task_hours_negative(self):
        self._reject_stage2({"staleness": {"task_hours": -1, "external_hours": 72}})

    def test_staleness_external_hours_9000(self):
        self._reject_stage2({"staleness": {"task_hours": 24, "external_hours": 9000}})

    def test_staleness_bool(self):
        # bool is a subclass of int; True would read as one hour.
        self._reject_stage2({"staleness": {"task_hours": True, "external_hours": 72}})

    def test_staleness_unknown_subkey(self):
        self._reject_stage2({"staleness": {"task_hours": 24, "lease_hours": 24}})

    def test_escape_not_an_object(self):
        # The string case is also caught by the subkey check; the list holding "path" only by the object
        # type check.
        for value in ("ESCAPE-ALLOW-YIELD", ["path"]):
            with self.subTest(value=value):
                self._reject_stage2({"escape": value})

    def test_escape_without_path(self):
        self._reject_stage2({"escape": {}})

    def test_escape_empty_string(self):
        # The hook disables the release with no record on an empty path (aiqt_hooks.py:7861-7862).
        self._reject_stage2({"escape": {"path": ""}})

    def test_escape_non_string(self):
        self._reject_stage2({"escape": {"path": 5}})

    def test_escape_dotdot(self):
        self._reject_stage2({"escape": {"path": "../ESCAPE-ALLOW-YIELD"}})

    def test_escape_dotdot_inside_anchor(self):
        # The case above is also caught by containment. Here the ".." stays inside the anchor
        # (normpath gives <state_dir>/ESCAPE-ALLOW-YIELD), so only the ".." rule rejects it, as the hook
        # does on the raw path (aiqt_hooks.py:7867-7868).
        self._reject_stage2({"escape": {"path": "sub/../ESCAPE-ALLOW-YIELD"}})

    def test_escape_hook_state_basename(self):
        # The escape sentinel must not share a basename with a file the hooks write in state_dir.
        for name in HOOK_STATE_FILES:
            for path in (name, "operator/" + name, "/opt/x/private/orch-state/" + name):
                with self.subTest(path=path):
                    self._reject_stage2({"escape": {"path": path}})

    def test_escape_windows_shaped(self):
        # codex QA F6: the hook joins the escape path onto the anchor with POSIX semantics
        # (aiqt_hooks.py:7863-7864). "C:ESCAPE" joined there is a valid POSIX path under the anchor, so only
        # the Windows-shape rule rejects it.
        for path in ("operator\\ESCAPE-ALLOW-YIELD", "C:ESCAPE-ALLOW-YIELD"):
            with self.subTest(path=path):
                self._reject_stage2({"escape": {"path": path}})

    def test_escape_absolute_outside_state_dir(self):
        self._reject_stage2({"escape": {"path": "/opt/x/private/ESCAPE-ALLOW-YIELD"}})

    def test_escape_onto_state_dir(self):
        # "." resolves onto the anchor directory itself, which can never be the regular-file sentinel.
        self._reject_stage2({"escape": {"path": "."}})

    def test_truth_present(self):
        # `truth` has no reader in the vendored hook, so it stays outside the allowlist.
        self._reject_stage2({"truth": {"changelog": "changelog.toml", "merged_pr_history": True}})

    def test_windows_shaped_declared_paths(self):
        # codex QA F6: the hook resolves a declared path with POSIX os.path.isabs (aiqt_hooks.py:7631-7635),
        # so a Windows spelling on a POSIX host is joined onto the repository root and a backslash is an
        # ordinary filename character. Each STAGE2 fixture replaces one declared path with a value that is
        # absolute to the gate predicate ("C:\\x" and "C:/x" through its Windows branch, a backslash POSIX
        # path through its POSIX branch) and collides with nothing, so only the Windows-shape rule rejects
        # it. (A drive-letter record, lease, mode, or register path was already rejected before F6 whenever
        # a POSIX state_dir is declared, because commonpath raises on the mixed pair and the gate treats
        # that as a collision; the backslash POSIX forms below are the ones that previously passed.)
        cases = [
            ("companion_stores", ["C:\\repo"]),
            ("companion_stores", ["C:/repo"]),
            ("companion_stores", ["/opt/x\\private"]),
            ("record", {"findings": "/opt/x/private\\open-findings.md"}),
            ("lease", {"path": "/opt/x/private\\session-state.md", "max_age_hours": 24}),
            ("mode", {"path": "/opt/x/private\\operating-mode.md"}),
            ("attestations", "/opt/x/private\\attestations.jsonl"),
            ("mistakes_register", "/opt/x/private\\mistakes-register.jsonl"),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self._reject_stage2({key: value})
        # A Windows-shaped state_dir with no other declared path to mix with is accepted without the rule.
        for state_dir in ("C:/x/orch-state", "C:\\x\\orch-state", "/opt/x\\orch-state"):
            with self.subTest(state_dir=state_dir):
                self._reject_clean({"version": 1, "state_dir": state_dir})

    # --- hooks.json as a guard input: unreadable or malformed fails, never skips ------------------------
    def _run_gate_copy(self, tree, payload, hooks_json=None):
        # Run a copy of the gate from <tree>/tools, so its ROOT (and so its HOOKS_JSON) is <tree>. When
        # `hooks_json` is given it is written at the plugin path under <tree>; otherwise none exists.
        tools_dir = Path(tree) / "tools"
        tools_dir.mkdir(exist_ok=True)
        gate = tools_dir / "check-orchestration-registry.py"
        shutil.copyfile(VALIDATOR, gate)
        if hooks_json is not None:
            hp = Path(tree) / "plugin" / "aiqt-guardrails-hooks" / "hooks" / "hooks.json"
            hp.parent.mkdir(parents=True, exist_ok=True)
            hp.write_text(hooks_json, encoding="utf-8")
        reg = _write(tree, payload)
        return subprocess.run([sys.executable, "-I", str(gate), str(reg)], capture_output=True, text=True)

    def test_yield_tools_with_absent_hooks_json_rejected(self):
        payload = {"version": 1, "state_dir": "/opt/x/orch-state", "yield_tools": ["ScheduleWakeup"]}
        with tempfile.TemporaryDirectory() as d:
            r = self._run_gate_copy(d, payload)
            self.assertEqual(r.returncode, 1)
            self.assertIn("hooks.json", r.stderr)
            self.assertNotIn("Traceback", r.stderr)
        # Control: the same gate copy with the real hooks.json in place accepts the same registry, so the
        # rejection above is caused by the missing hooks.json and nothing else.
        with tempfile.TemporaryDirectory() as d:
            r = self._run_gate_copy(d, payload, REAL_HOOKS_JSON.read_text(encoding="utf-8"))
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_yield_tools_with_hooks_json_lacking_the_entry_rejected(self):
        payload = {"version": 1, "state_dir": "/opt/x/orch-state", "yield_tools": ["ScheduleWakeup"]}
        with tempfile.TemporaryDirectory() as d:
            r = self._run_gate_copy(d, payload, json.dumps({"hooks": {"PreToolUse": []}}))
            self.assertEqual(r.returncode, 1)
            self.assertIn("orch_yield_tool", r.stderr)

    def test_yield_tools_with_non_json_hooks_json_rejected(self):
        payload = {"version": 1, "state_dir": "/opt/x/orch-state", "yield_tools": []}
        with tempfile.TemporaryDirectory() as d:
            r = self._run_gate_copy(d, payload, "{ not json")
            self.assertEqual(r.returncode, 1)
            self.assertNotIn("Traceback", r.stderr)

    def test_dispatch_tools_with_absent_hooks_json_rejected(self):
        # codex QA F3: dispatch_tools, even the empty list, is checked against hooks.json, so a missing
        # hooks.json is a cannot-evaluate gate failure, never a skip.
        payload = {"version": 1, "dispatch_tools": []}
        with tempfile.TemporaryDirectory() as d:
            r = self._run_gate_copy(d, payload)
            self.assertEqual(r.returncode, 1)
            self.assertIn("hooks.json", r.stderr)
            self.assertNotIn("Traceback", r.stderr)
        # Control: with the real hooks.json in place the same registry is accepted.
        with tempfile.TemporaryDirectory() as d:
            r = self._run_gate_copy(d, payload, REAL_HOOKS_JSON.read_text(encoding="utf-8"))
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_dispatch_tools_with_hooks_json_lacking_the_entry_rejected(self):
        payload = {"version": 1, "dispatch_tools": []}
        with tempfile.TemporaryDirectory() as d:
            r = self._run_gate_copy(d, payload, json.dumps({"hooks": {"PreToolUse": [], "PostToolUse": []}}))
            self.assertEqual(r.returncode, 1)
            self.assertIn("orch_dispatch_ledger", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_dispatch_tools_under_a_widened_matcher(self):
        # Under the real matcher ("Bash|TaskOutput") no non-empty dispatch_tools value is valid, so the
        # matcher-accept and duplicate paths are exercised against a hooks.json whose orch_dispatch_ledger
        # matcher also routes "Workflow": that name is accepted, its duplicate is rejected, and "Bash" stays
        # rejected however the matcher reads.
        hooks = json.loads(REAL_HOOKS_JSON.read_text(encoding="utf-8"))
        widened = 0
        for entry in hooks["hooks"]["PostToolUse"]:
            if any("orch_dispatch_ledger" in h.get("args", []) for h in entry.get("hooks", [])):
                entry["matcher"] += "|Workflow"
                widened += 1
        self.assertEqual(widened, 1, "expected exactly one orch_dispatch_ledger entry in hooks.json")
        cases = ((["Workflow"], 0, None), (["Workflow", "Workflow"], 1, "duplicate"),
                 (["Workflow", "Bash"], 1, "aiqt_hooks.py:9279-9280"))
        for tools, code, needle in cases:
            with self.subTest(tools=tools), tempfile.TemporaryDirectory() as d:
                r = self._run_gate_copy(d, {"version": 1, "dispatch_tools": tools}, json.dumps(hooks))
                self.assertEqual(r.returncode, code, r.stderr)
                if needle:
                    self.assertIn(needle, r.stderr)


# --- the hook state-file set, derived from the hook source (round 2 G3) ------------------------------------
_STATE_EXTS = (".json", ".jsonl", ".marker", ".unused")
_STATE_DIR_CALLS = frozenset(("_orch_state_dir_for_root", "_state_dir_from_registry"))
_STATE_DIR_NAMES = frozenset(("sd", "state_dir"))
_ATOMIC_WRITERS = frozenset(("_orch_write_json_atomic",))


def _call_name(node):
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name):
            return f.id
        if isinstance(f, ast.Attribute):
            return f.attr
    return None


def _is_path_join(node):
    f = node.func if isinstance(node, ast.Call) else None
    return (isinstance(f, ast.Attribute) and f.attr == "join" and isinstance(f.value, ast.Attribute)
            and f.value.attr == "path" and isinstance(f.value.value, ast.Name) and f.value.value.id == "os")


def scan_hook_state_files(source):
    """Derive, from hook source text, every machine-state basename joined onto state_dir.

    A state-dir join is os.path.join(<base>, <name>) where <name> is a string literal or a module-level
    string constant (such as _WRTSCP_DECL_REL) ending in one of _STATE_EXTS, and <base> is sd or state_dir,
    a call to _orch_state_dir_for_root or _state_dir_from_registry, or a local assigned from such a call.
    Within the same function, a variable holding a state-dir join that is extended with a "." suffix
    literal (barrier_path + ".unused", path + ".surfaced") adds that derived name, and one passed to
    _orch_write_json_atomic adds its "<name>.tmp" sibling. Returns (names, unclassified), where
    unclassified lists every join of such a name onto a base the scan cannot classify as either the state
    dir or the repository root, so a new join form fails the test rather than slipping past the scan."""
    tree = ast.parse(source)
    consts = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            consts[node.targets[0].id] = node.value.value
    names, unclassified = set(), []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        nodes = list(ast.walk(fn))
        sd_vars = set(_STATE_DIR_NAMES)
        for node in nodes:
            if isinstance(node, ast.Assign) and _call_name(node.value) in _STATE_DIR_CALLS:
                sd_vars.update(t.id for t in node.targets if isinstance(t, ast.Name))

        def state_join(expr):
            # The state basename `expr` joins onto state_dir, or None when it is no such join.
            if not _is_path_join(expr) or len(expr.args) != 2:
                return None
            base, leaf = expr.args
            if isinstance(leaf, ast.Constant) and isinstance(leaf.value, str):
                name = leaf.value
            elif isinstance(leaf, ast.Name) and leaf.id in consts:
                name = consts[leaf.id]
            else:
                return None
            if not name.endswith(_STATE_EXTS):
                return None
            if (isinstance(base, ast.Name) and base.id in sd_vars) or _call_name(base) in _STATE_DIR_CALLS:
                return name
            if isinstance(base, ast.Name) and base.id == "root":
                return None  # an in-tree file under the repository root, not state_dir
            unclassified.append("line {}: os.path.join({}, {!r})".format(
                expr.lineno, ast.unparse(base), name))
            return None

        held = {}
        for node in nodes:
            if isinstance(node, ast.Call):
                name = state_join(node)
                if name:
                    names.add(name)
            if isinstance(node, ast.Assign):
                name = state_join(node.value)
                if name:
                    held.update((t.id, name) for t in node.targets if isinstance(t, ast.Name))

        def held_name(expr):
            if isinstance(expr, ast.Name) and expr.id in held:
                return held[expr.id]
            return state_join(expr)

        for node in nodes:
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) \
                    and isinstance(node.right, ast.Constant) and isinstance(node.right.value, str) \
                    and node.right.value.startswith("."):
                name = held_name(node.left)
                if name:
                    names.add(name + node.right.value)
            if _call_name(node) in _ATOMIC_WRITERS and node.args:
                name = held_name(node.args[0])
                if name:
                    names.add(name + ".tmp")
    return names, sorted(set(unclassified))


def _load_gate_module():
    spec = importlib.util.spec_from_file_location("check_orchestration_registry_under_test", str(VALIDATOR))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EnumeratorRelativeOperands(unittest.TestCase):
    # Round 3 R1: the hook runs the enumerator argv with cwd at the repository root (aiqt_hooks.py:7976),
    # the parent of the .aiqt directory holding the registry (aiqt_hooks.py:7548, 7590-7594, 7606-7607), so
    # a relative operand names a path under that root and faces the same state_dir collision checks as an
    # absolute one. Each fixture writes the registry at <repo>/.aiqt/orchestration.json in a temporary
    # tree, so the gate derives <repo> as the root.

    def _run_in_repo(self, tree, payload):
        repo = Path(tree) / "repo"
        (repo / ".aiqt").mkdir(parents=True, exist_ok=True)
        reg = repo / ".aiqt" / "orchestration.json"
        reg.write_text(json.dumps(payload), encoding="utf-8")
        return _run_full(reg)

    @staticmethod
    def _payload(state_dir, operands):
        return {"version": 1, "state_dir": str(state_dir),
                "enumerator": {"argv": [PY, "-I", "tools/orch-enumerate-backlog.py"] + list(operands),
                               "timeout": 5}}

    def test_relative_operand_reaching_state_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "repo"
            outside = Path(d) / "orch-state"
            outside.mkdir()
            repo.mkdir()
            os.symlink(str(outside), str(repo / "state-link"))
            cases = [
                (repo / "state", ["state/resume-barrier.json"]),
                (repo / "state", ["./state/../state/turn-state.json"]),
                (outside, ["../orch-state/resume-barrier.json"]),
                (outside, ["state-link/resume-barrier.json"]),
            ]
            for state_dir, operands in cases:
                with self.subTest(state_dir=str(state_dir), operands=operands):
                    r = self._run_in_repo(d, self._payload(state_dir, operands))
                    self.assertEqual(r.returncode, 1, r.stdout)
                    self.assertIn("joined onto the repository root", r.stderr)
                    self.assertIn("state_dir", r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
                # Control: the same operands with state_dir elsewhere are accepted, so only the collision
                # of the root-joined operand with state_dir rejects the fixture above.
                with self.subTest(control=operands):
                    r = self._run_in_repo(d, self._payload(Path(d) / "elsewhere", operands))
                    self.assertEqual(r.returncode, 0, r.stderr)

    def test_registry_outside_aiqt_uses_gate_root(self):
        # A registry checked from a path outside any .aiqt directory joins a relative operand onto the
        # checkout the gate runs from. The state_dir is an absent path under that checkout, so nothing is
        # written there; the operand reaching it is rejected.
        name = "orch-state-r1-fixture-absent"
        state_dir = REPO_ROOT / name
        self.assertFalse(os.path.lexists(str(state_dir)))
        with tempfile.TemporaryDirectory() as d:
            r = _run_full(_write(d, self._payload(state_dir, [name + "/resume-barrier.json"])))
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("joined onto the repository root", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_planned_stage2_argv_accepted(self):
        # The planned stage-2 enumerator argv, with the test interpreter standing in for the python3 of the
        # host, added to the committed registry, is accepted.
        planned = [PY, "-I", "tools/orch-enumerate-backlog.py", "/opt/cleanlanguage/private/TODO.md"]
        payload = json.loads(REAL_REGISTRY.read_text(encoding="utf-8"))
        payload["enumerator"] = {"argv": planned, "timeout": 5}
        with tempfile.TemporaryDirectory() as d:
            r = self._run_in_repo(d, payload)
            self.assertEqual(r.returncode, 0, r.stderr)
        # The temporary-directory equivalent: the same shape with every store path under a temporary tree.
        with tempfile.TemporaryDirectory() as d:
            payload = self._payload(Path(d) / "orch-state", [str(Path(d) / "private" / "TODO.md")])
            r = self._run_in_repo(d, payload)
            self.assertEqual(r.returncode, 0, r.stderr)


class HookStateFileScan(unittest.TestCase):
    # Round 2 G3: the escape.path basename rule is only as complete as the gate HOOK_STATE_FILES set, so
    # the set is derived here from the hook source and must equal both the gate constant and the
    # transcribed list at the top of this file. A state file the hook gains, or one the gate drops, is red.
    def test_scanner_finds_a_new_state_file(self):
        # The scanner itself is exercised on a small synthetic source, so a scan that silently found
        # nothing could not pass the equality test below by accident of an empty gate set.
        source = ("def f(root):\n"
                  "    sd = _orch_state_dir_for_root(root)\n"
                  "    p = os.path.join(sd, \"new-state.json\")\n"
                  "    _orch_write_json_atomic(p, {})\n"
                  "    os.replace(p, p + \".done\")\n"
                  "    q = os.path.join(root, \".aiqt\", \"x.json\")\n"
                  "    r = os.path.join(elsewhere, \"other.json\")\n")
        names, unclassified = scan_hook_state_files(source)
        self.assertEqual(names, {"new-state.json", "new-state.json.tmp", "new-state.json.done"})
        self.assertEqual(len(unclassified), 1, unclassified)

    def test_gate_set_matches_the_hook_source(self):
        names, unclassified = scan_hook_state_files(HOOK_PY.read_text(encoding="utf-8"))
        self.assertEqual(unclassified, [], "joins the scan cannot classify; extend the scan")
        self.assertGreaterEqual(len(names), 18, sorted(names))
        gate = _load_gate_module()
        self.assertEqual(sorted(names), sorted(gate.HOOK_STATE_FILES),
                         "the gate HOOK_STATE_FILES set differs from the state files the hook source joins "
                         "onto state_dir")
        self.assertEqual(sorted(names), sorted(HOOK_STATE_FILES))


class LaunchIsolation(unittest.TestCase):
    # codex QA F7: every Python launch of the gate runs isolated (-I), so a file beside a script cannot
    # shadow a standard library import and an ambient PYTHON* variable cannot steer it. These read the
    # sources statically and fail if any launch drops the flag.
    def test_workflow_python_launches_are_isolated(self):
        runs = [line.strip() for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith("run:") and "python" in line]
        self.assertGreaterEqual(len(runs), 7, "expected every workflow step to launch Python")
        for run in runs:
            with self.subTest(run=run):
                self.assertTrue(run.startswith("run: python3 -I "), run)

    def test_gate_subprocess_launches_are_isolated(self):
        # Every list display in this file whose first element is sys.executable must have "-I" second.
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        launches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.List) and node.elts:
                head = node.elts[0]
                if isinstance(head, ast.Attribute) and head.attr == "executable" \
                        and isinstance(head.value, ast.Name) and head.value.id == "sys":
                    launches.append(node)
        self.assertGreaterEqual(len(launches), 5, "expected at least five gate launches")
        for node in launches:
            with self.subTest(line=node.lineno):
                second = node.elts[1] if len(node.elts) > 1 else None
                self.assertTrue(isinstance(second, ast.Constant) and second.value == "-I",
                                "line {} launches Python without -I".format(node.lineno))


class ConfigDisclosure(unittest.TestCase):
    # codex QA F8: the adoption config states every exit of the stop decision, including the loop bound
    # (aiqt_hooks.py:8192-8195) and the fail-open on an unsaved denial counter (aiqt_hooks.py:8590-8595).
    def test_stop_decision_exits_are_disclosed(self):
        text = " ".join(CONFIG_MD.read_text(encoding="utf-8").split())
        for phrase in ("the loop bound", "denial counter cannot be saved", "guard fails open instead"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_lease_liveness_states_the_non_empty_condition(self):
        # Round 2 G10: the lease makes scope live only when its file is non-empty as well as present and
        # fresh (aiqt_hooks.py:7799, st.st_size > 0).
        text = " ".join(CONFIG_MD.read_text(encoding="utf-8").split())
        self.assertIn("while the lease file is present, non-empty, and fresh", text)

    def test_claude_md_defers_the_orchestrator_hook_account_to_config(self):
        # Round 2 G6: .claude/CLAUDE.md must not claim that only two orchestrator hooks are armed, since
        # the stop guard also denies on NO_ENUMERATOR while the lease is live (config.md); it points there.
        text = " ".join(CLAUDE_MD.read_text(encoding="utf-8").split())
        self.assertNotIn("arms two of the 10 orchestrator hooks", text)
        self.assertIn("A minimal orchestration registry is declared; what each of the 10 orchestrator hooks "
                      "does under it today, including the stop guard denial and the operator escape that "
                      "releases it, is described in [`../.aiqt/config.md`](../.aiqt/config.md).", text)


if __name__ == "__main__":
    unittest.main()
