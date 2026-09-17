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
        # max_age_hours is optional: a lease with only a path is valid. state_dir is declared because a
        # declared lease now requires it (claude QA round 7 co-requirement); this test isolates max_age
        # optionality, not the state_dir requirement.
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "lease": {"path": "/opt/x/lease"},
                                             "state_dir": "/opt/x/orch-state"})), 0)

    def test_dispatch_tools_with_strings(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_run(_write(d, {"version": 1, "dispatch_tools": ["Workflow", "Task"]})), 0)

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
        # "a"*150 + "\\" + "a"*150 is ONE 301-byte POSIX component, over NAME_MAX (255). Round 5's
        # `re.split(r"[/\\]", ...)` split it AT the backslash into two <=255-byte fragments and wrongly
        # ACCEPTED it, only to hit ENAMETOOLONG at runtime. Splitting on "/" ONLY measures the true 301-byte
        # component and rejects. RED against the round-5 `[/\\]` split (which returns exit 0 here).
        comp = "a" * 150 + "\\" + "a" * 150  # 301 bytes, ONE POSIX component
        self.assertEqual(len(comp.encode()), 301, "fixture must be a 301-byte single POSIX component")
        self._reject({"version": 1, "record": {"findings": "/opt/x/" + comp}})

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
        self._reject({"version": 1, "dispatch_tools": ["Workflow", "Ta" + chr(0xD800) + "sk"]})


if __name__ == "__main__":
    unittest.main()
