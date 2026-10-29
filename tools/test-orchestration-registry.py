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
# The basenames the hooks write inside state_dir, transcribed from the write sites in
# plugin/aiqt-guardrails-hooks/hooks/scripts/aiqt_hooks.py (7733, 7756, 8359-8360, 8414, 8424, 8520, 8558,
# 8746-8751, 9300-9301, 9639, 9670, 9715, 9734, 9775-9777, 9783, 9837), plus the "<name>.tmp" sibling that
# _orch_write_json_atomic writes first (7719-7722). Kept independent of the gate constant on purpose, so a
# name dropped from the gate list fails here.
HOOK_STATE_FILES = (
    "guard-events.jsonl", "turn-state.json", "backlog-checkpoint.json", "checkpoint-init.marker",
    "escape-spoof.json", "forced-exit.jsonl", "pending-asks.jsonl", "dispatch-ledger.jsonl",
    "attestations-validated.json", "forced-exit-surfaced.json", "resume-barrier.json",
    "resume-barrier.json.unused", "backlog-checkpoint.json.tmp", "checkpoint-init.marker.tmp",
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
        "argv": ["/usr/bin/python3", "-I", "tools/orch-enumerate-backlog.py", "/opt/x/private/TODO.md"],
        "timeout": 5,
    },
    "yield_tools": ["ScheduleWakeup", "CronCreate"],
    "mode": {"path": "/opt/x/private/operating-mode.md"},
    "staleness": {"task_hours": 24, "external_hours": 72},
    "escape": {"path": "ESCAPE-ALLOW-YIELD"},
    "attestations": "/opt/x/private/attestations.jsonl",
    "mistakes_register": "/opt/x/private/mistakes-register.jsonl",
}


def _run(path) -> int:
    """Run the validator against `path`; return its exit code."""
    return subprocess.run(
        [sys.executable, "-I", str(VALIDATOR), str(path)],
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

    def test_dispatch_tools_with_strings(self):
        # Both names are inside the orch_dispatch_ledger PostToolUse matcher ("Bash|TaskOutput",
        # hooks.json:278), so the matcher check accepts them.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "dispatch_tools": ["Bash", "TaskOutput"]})), 0)

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

    def test_enumerator_non_python_interpreter_accepted(self):
        # The "-I" requirement applies only when the basename of argv[0] starts with "python".
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {
                "version": 1, "state_dir": "/opt/x/orch-state",
                "enumerator": {"argv": ["/bin/sh", "tools/enumerate.sh", "/opt/x/private/TODO.md"],
                               "timeout": 5}})), 0)

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
        self._reject({"version": 1, "dispatch_tools": ["Bash", 123]})

    def test_dispatch_tools_outside_matcher(self):
        # codex QA F3: Workflow is not in the orch_dispatch_ledger PostToolUse matcher ("Bash|TaskOutput",
        # hooks.json:278), so the hook never sees that tool and the entry would be a silent no-op.
        self._reject({"version": 1, "dispatch_tools": ["Workflow"]})

    def test_dispatch_tools_duplicate(self):
        self._reject({"version": 1, "dispatch_tools": ["Bash", "Bash"]})

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
        self._reject({"version": 1, "dispatch_tools": ["Bash", "Ba" + chr(0xD800) + "sh"]})

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

    def test_enumerator_python_without_isolation(self):
        # codex QA F7: a Python argv[0] must be followed by exactly "-I"; a missing flag, a different flag,
        # or no argv[1] at all is rejected. Each fixture is otherwise valid.
        for argv in (["/usr/bin/python3", "tools/x.py", "/opt/x/private/TODO.md"],
                     ["/usr/bin/python3.12", "-E", "tools/x.py"],
                     ["/usr/local/bin/python", "-P", "-I", "tools/x.py"],
                     ["/usr/bin/python3"]):
            with self.subTest(argv=argv):
                self._reject_stage2({"enumerator": self._enum(argv=argv)})

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
        payload = {"version": 1, "dispatch_tools": ["Bash"]}
        with tempfile.TemporaryDirectory() as d:
            r = self._run_gate_copy(d, payload, json.dumps({"hooks": {"PreToolUse": [], "PostToolUse": []}}))
            self.assertEqual(r.returncode, 1)
            self.assertIn("orch_dispatch_ledger", r.stderr)
            self.assertNotIn("Traceback", r.stderr)


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


if __name__ == "__main__":
    unittest.main()
