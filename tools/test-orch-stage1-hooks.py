#!/usr/bin/env python3
"""Behavioural change-carries-check for the item 28.2 stage-1 arming of the recorder/audit hooks.

This suite proves that the stage-1 `.aiqt/orchestration.json` arming keys (`record`, `lease`,
`state_dir`, `dispatch_tools`) actually change the installed hook's behaviour, and that the change
adds no unbounded or fail-closed path beyond the pre-existing bad-registry class. It does so by
driving the REAL installed hook script directly: per case it builds a throwaway git repo and a
temporary stand-in store, writes a fixture registry into the repo, and invokes

    python3 -I <plugin>/hooks/scripts/aiqt_hooks.py <hook-action>

with a JSON stdin payload, then asserts the exit code, any stdout verdict JSON, and the state files
the hook wrote under the temporary store. It NEVER touches the real /opt/cleanlanguage/private store,
so it runs in CI.

Every armed-behaviour proof runs against BOTH the stage-1 fixture (behaviour PRESENT) and today's
two-key registry (behaviour ABSENT), so each arming key is shown load-bearing: a recorder that wrote
unconditionally, or an audit that read an undeclared surface, would flip the two-key assertion. That
dual run is the change-carries-check.

Grounding: every hook-behaviour assertion below is read from
plugin/aiqt-guardrails-hooks/hooks/scripts/aiqt_hooks.py at source; the cited line numbers are in the
per-test comments. Dispatch-action names are the HANDLERS keys (aiqt_hooks.py:10594-10619), passed as
the single argv (main(sys.argv[1:]), aiqt_hooks.py:10724). The repo root is the git top level of
data["cwd"] (_orch_root -> _recovery_toplevel, aiqt_hooks.py:7590-7595, 3859), and scope goes live only
when the declared lease file is present, non-empty and fresh (_orch_scope_live, aiqt_hooks.py:7779-7817).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
HOOK = REPO_ROOT / "plugin" / "aiqt-guardrails-hooks" / "hooks" / "scripts" / "aiqt_hooks.py"


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _git(repo, *args, extra_env=None):
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, env=env, check=True)


class HookHarness(unittest.TestCase):
    """A throwaway git repo plus a temporary stand-in store, torn down after each test."""

    def setUp(self):
        if not HOOK.exists():
            self.skipTest("installed hook not found: {}".format(HOOK))
        self._tmp = Path(tempfile.mkdtemp(prefix="orch-stage1-"))
        self.repo = self._tmp / "repo"
        self.store = self._tmp / "store"
        self.repo.mkdir()
        self.store.mkdir()
        # A hermetic git repo with exactly one commit, so `git rev-parse HEAD` resolves for the resume
        # audit's gate-marker probe and the default branch is a known value ("main").
        subprocess.run(["git", "init", "-b", "main", str(self.repo)],
                       capture_output=True, text=True, check=True)
        _git(self.repo, "-c", "user.email=t@example.invalid", "-c", "user.name=t",
             "commit", "--allow-empty", "-m", "init")

    def tearDown(self):
        # Restore any 0o555 dir written by the unwritable-state-dir case so rmtree can clean up.
        for dirpath, _dirs, _files in os.walk(self._tmp):
            try:
                os.chmod(dirpath, 0o755)
            except OSError:
                pass
        shutil.rmtree(self._tmp, ignore_errors=True)

    # --- registry fixtures ---------------------------------------------------------------------------
    def _p(self, *parts):
        return str(self.store.joinpath(*parts))

    def state_dir(self):
        return self.store / "orch-state"

    def stage1(self, **overrides):
        reg = {
            "version": 1,
            "companion_stores": [str(self.store)],
            "record": {
                "findings": self._p("open-findings.md"),
                "pending_decisions": self._p("pending-decisions.md"),
                "handoff": self._p("session-handoff.md"),
            },
            "lease": {"path": self._p("session-state.md"), "max_age_hours": 24},
            "state_dir": str(self.state_dir()),
            "dispatch_tools": [],
        }
        reg.update(overrides)
        return reg

    def two_key(self):
        return {"version": 1, "companion_stores": [str(self.store)]}

    # --- fixture builders ----------------------------------------------------------------------------
    def write_registry(self, obj):
        aiqt = self.repo / ".aiqt"
        aiqt.mkdir(exist_ok=True)
        path = aiqt / "orchestration.json"
        if isinstance(obj, str):
            path.write_text(obj, encoding="utf-8")
        else:
            path.write_text(json.dumps(obj), encoding="utf-8")

    def arm_lease(self, age_seconds=0):
        """Create a non-empty lease file; age_seconds>0 back-dates its mtime (a stale lease)."""
        lease = Path(self._p("session-state.md"))
        lease.write_text("held by the orchestrator\n", encoding="utf-8")
        if age_seconds:
            t = time.time() - age_seconds
            os.utime(lease, (t, t))
        return lease

    def write_record_files(self, handoff="", findings="", pending=""):
        Path(self._p("session-handoff.md")).write_text(handoff, encoding="utf-8")
        Path(self._p("open-findings.md")).write_text(findings, encoding="utf-8")
        Path(self._p("pending-decisions.md")).write_text(pending, encoding="utf-8")

    def seed_state(self, name, obj):
        sd = self.state_dir()
        sd.mkdir(parents=True, exist_ok=True)
        (sd / name).write_text(json.dumps(obj), encoding="utf-8")

    # --- invocation ----------------------------------------------------------------------------------
    def run_hook(self, action, payload):
        """Invoke `python3 -I aiqt_hooks.py <action>` with the JSON payload on stdin.

        HOME and XDG_STATE_HOME are pinned inside the throwaway tree, so an UNARMED (two-key) run whose
        state_dir falls back to the XDG default writes into the sandbox, never the developer's home; a
        stage-1 run's explicit state_dir (registry wins over XDG) still lands in <store>/orch-state.
        """
        payload = dict(payload)
        payload.setdefault("cwd", str(self.repo))
        env = dict(os.environ)
        env["HOME"] = str(self.store / "home")
        env["XDG_STATE_HOME"] = str(self.store / "xdg")
        result = subprocess.run(
            [sys.executable, "-I", str(HOOK), action],
            input=json.dumps(payload), capture_output=True, text=True, env=env,
        )
        return result

    def stdout_json(self, result):
        out = result.stdout.strip()
        if not out:
            return None
        return json.loads(out.splitlines()[0])

    def read_jsonl(self, name):
        path = self.state_dir() / name
        if not path.exists():
            return None
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def read_json(self, name):
        path = self.state_dir() / name
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def find_anywhere(self, name):
        return [str(p) for p in self.store.rglob(name)]

    def read_json_anywhere(self, name):
        # A bad or two-key registry declares no state_dir, so the hook falls back to the XDG default
        # (pinned inside the sandbox by run_hook); the artefact lands there, not in <store>/orch-state.
        matches = list(self.store.rglob(name))
        if not matches:
            return None
        return json.loads(matches[0].read_text(encoding="utf-8"))


# =====================================================================================================
# 1. orch_dispatch_ledger (PostToolUse recorder; aiqt_hooks.py:9248-9304)
# =====================================================================================================
class DispatchLedger(HookHarness):
    def test_background_bash_synthesized_id_wake_false(self):
        # A background Bash with no observed task id gets a synthesized "disp-" id and wake=False, so it
        # can never be counted as a live task (aiqt_hooks.py:9279-9296).
        self.write_registry(self.stage1())
        self.arm_lease()
        r = self.run_hook("orch_dispatch_ledger", {
            "tool_name": "Bash",
            "tool_input": {"run_in_background": True, "command": "sleep 1"},
            "tool_response": {},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = self.read_jsonl("dispatch-ledger.jsonl")
        self.assertIsNotNone(rows, "stage-1 must record a launch row")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event"], "launch")
        self.assertFalse(rows[0]["wake"])
        self.assertTrue(rows[0]["task_id"].startswith("disp-"))

    def test_background_bash_observed_id_wake_true(self):
        # A REAL observed task id (tool_response.task_id) records wake=True (aiqt_hooks.py:9284-9296).
        self.write_registry(self.stage1())
        self.arm_lease()
        r = self.run_hook("orch_dispatch_ledger", {
            "tool_name": "Bash",
            "tool_input": {"run_in_background": True, "command": "sleep 1"},
            "tool_response": {"task_id": "task-abc"},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = self.read_jsonl("dispatch-ledger.jsonl")
        self.assertEqual(rows[0], {**rows[0], "event": "launch", "task_id": "task-abc", "wake": True})

    def test_taskoutput_with_id_completes(self):
        # TaskOutput carrying a task id appends a complete row, wake=True (aiqt_hooks.py:9264-9267).
        self.write_registry(self.stage1())
        self.arm_lease()
        r = self.run_hook("orch_dispatch_ledger", {
            "tool_name": "TaskOutput", "tool_input": {"task_id": "task-abc"}, "tool_response": {},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = self.read_jsonl("dispatch-ledger.jsonl")
        self.assertEqual(rows[0]["event"], "complete")
        self.assertEqual(rows[0]["task_id"], "task-abc")
        self.assertTrue(rows[0]["wake"])

    def test_two_key_registry_writes_nothing(self):
        # LOAD-BEARING contrast: with the two-key registry scope is never live (no lease, no mode), so
        # the recorder returns _allow() and writes NO ledger anywhere (aiqt_hooks.py:9258-9259).
        self.write_registry(self.two_key())
        self.arm_lease()  # a lease file exists but the registry declares none, so scope stays inert
        r = self.run_hook("orch_dispatch_ledger", {
            "tool_name": "Bash",
            "tool_input": {"run_in_background": True, "command": "sleep 1"},
            "tool_response": {},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.find_anywhere("dispatch-ledger.jsonl"), [],
                         "the two-key registry must record nothing")


# =====================================================================================================
# 2. TaskOutput with no id -> unbound systemMessage, no row (aiqt_hooks.py:9268-9275)
# =====================================================================================================
class TaskOutputNoId(HookHarness):
    def test_unbound_taskoutput(self):
        self.write_registry(self.stage1())
        self.arm_lease()
        r = self.run_hook("orch_dispatch_ledger", {
            "tool_name": "TaskOutput", "tool_input": {}, "tool_response": {},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.stdout_json(r)
        self.assertIn("UNBOUND", out["systemMessage"])
        self.assertIsNone(self.read_jsonl("dispatch-ledger.jsonl"), "an unbound read records no row")


# =====================================================================================================
# 3. orch_prompt_stamp (UserPromptSubmit recorder; aiqt_hooks.py:9307-9348)
# =====================================================================================================
class PromptStamp(HookHarness):
    def test_human_prompt_stamps_and_zeroes_counters(self):
        # A genuine human prompt stamps last_human_input_utc and zeroes both denial counters
        # (aiqt_hooks.py:9327-9333). LOAD-BEARING: the turn-state is SEEDED with NONZERO stop/schedule
        # denial counters first, so a broken implementation that dropped the reset (preserving the seeded
        # values) would fail these assertions instead of passing on a fresh (absent-key => 0) turn-state.
        # The prompt is not a seeded wake digest, so it is genuine human input, not timer-originated.
        self.write_registry(self.stage1())
        self.arm_lease()
        self.seed_state("turn-state.json", {"stop_denials": 5, "schedule_denials": 7})
        r = self.run_hook("orch_prompt_stamp", {"prompt": "please continue the work"})
        self.assertEqual(r.returncode, 0, r.stderr)
        ts = self.read_json("turn-state.json")
        self.assertIsNotNone(ts, "stage-1 must write turn-state.json")
        self.assertIn("last_human_input_utc", ts)
        self.assertEqual(ts["stop_denials"], 0, "a human prompt must zero a seeded nonzero stop counter")
        self.assertEqual(ts["schedule_denials"], 0,
                         "a human prompt must zero a seeded nonzero schedule counter")

    def test_timer_originated_prompt(self):
        # A prompt whose digest is a seeded wake digest is classified TIMER-ORIGINATED, injects the
        # measured gap, and consumes exactly one digest without resetting the counters
        # (aiqt_hooks.py:9325, 9334-9348).
        self.write_registry(self.stage1())
        self.arm_lease()
        prompt = "scheduled wake: recheck ci-7"
        earlier = (_now() - timedelta(minutes=12)).isoformat()
        self.seed_state("turn-state.json", {
            "wake_digests": [_sha256_hex(prompt)],
            "last_human_input_utc": earlier,
            "stop_denials": 1, "schedule_denials": 2,
        })
        r = self.run_hook("orch_prompt_stamp", {"prompt": prompt})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.stdout_json(r)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("TIMER-ORIGINATED", ctx)
        self.assertIn("minutes", ctx)
        ts = self.read_json("turn-state.json")
        self.assertEqual(ts["wake_digests"], [], "the matched wake digest is consumed")
        self.assertEqual(ts["last_human_input_utc"], earlier, "a timer wake never restamps human input")
        self.assertEqual(ts["stop_denials"], 1, "a timer wake never resets the loop counters")

    def test_two_key_registry_writes_nothing(self):
        # LOAD-BEARING contrast: two-key scope is inert, so no turn-state is written anywhere
        # (aiqt_hooks.py:9317-9318).
        self.write_registry(self.two_key())
        self.arm_lease()
        r = self.run_hook("orch_prompt_stamp", {"prompt": "please continue"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.find_anywhere("turn-state.json"), [],
                         "the two-key registry must stamp nothing")


# =====================================================================================================
# 4. orch_resume_audit (SessionStart, warn-only; aiqt_hooks.py:9765-9794)
# =====================================================================================================
class ResumeAudit(HookHarness):
    def test_wrong_branch_handoff_arms_barrier(self):
        # A handoff naming a branch other than HEAD is a divergence finding; the audit warns and arms
        # the resume barrier active:true (aiqt_hooks.py:9365-9370, 9783-9793).
        self.write_registry(self.stage1())
        self.arm_lease()
        self.write_record_files(handoff="Branch: some-other-branch\n")
        r = self.run_hook("orch_resume_audit", {})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.stdout_json(r)
        self.assertIn("resume audit", out["systemMessage"])
        self.assertIn("some-other-branch", out["systemMessage"])
        barrier = self.read_json("resume-barrier.json")
        self.assertTrue(barrier["active"])

    def test_stale_gate_marker_arms_barrier(self):
        # A handoff gate marker citing a commit that is not HEAD is a divergence finding
        # (aiqt_hooks.py:9371-9382).
        self.write_registry(self.stage1())
        self.arm_lease()
        self.write_record_files(handoff="Gate: green @ deadbeef1234\n")
        r = self.run_hook("orch_resume_audit", {})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.stdout_json(r)
        self.assertIn("gate marker", out["systemMessage"])
        self.assertTrue(self.read_json("resume-barrier.json")["active"])

    def test_clean_audit_clears_barrier(self):
        # With readable record surfaces, a fresh lease, and no divergence markers, the audit is clean:
        # a silent allow and resume-barrier.json active:false (aiqt_hooks.py:9784, 9794).
        self.write_registry(self.stage1())
        self.arm_lease()
        self.write_record_files(handoff="Session handoff, no markers here.\n")
        r = self.run_hook("orch_resume_audit", {})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "", "a clean audit is a silent allow")
        self.assertFalse(self.read_json("resume-barrier.json")["active"])

    def test_two_key_registry_finds_no_divergence(self):
        # LOAD-BEARING contrast: the same wrong-branch handoff file is on disk, but the two-key registry
        # declares no record surface, so the audit reads nothing and stays clean (aiqt_hooks.py:9355,
        # 9420) -- proving record.handoff is what makes the finding possible.
        self.write_registry(self.two_key())
        self.arm_lease()
        self.write_record_files(handoff="Branch: some-other-branch\n")
        r = self.run_hook("orch_resume_audit", {})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")
        # The two-key registry declares no state_dir, so the barrier lands at the XDG default.
        self.assertFalse(self.read_json_anywhere("resume-barrier.json")["active"])


# =====================================================================================================
# 5. orch_resume_barrier (PreToolUse, warn-first BAKE posture; aiqt_hooks.py:9797-9845)
# =====================================================================================================
class ResumeBarrier(HookHarness):
    def _arm_barrier(self, warned=False):
        self.seed_state("resume-barrier.json", {
            "active": True, "warned": warned, "findings": ["a divergence"], "ts": _now().isoformat(),
        })

    def test_first_out_of_allowlist_write_warns_once(self):
        # An active barrier surfaces the first mutation outside the allowlist exactly once, flipping
        # warned:true (aiqt_hooks.py:9833-9845).
        self.write_registry(self.stage1())
        self._arm_barrier(warned=False)
        r = self.run_hook("orch_resume_barrier", {
            "tool_name": "Write", "tool_input": {"file_path": self._p("some", "unrelated.py")},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.stdout_json(r)
        self.assertIn("resume barrier", out["systemMessage"])
        self.assertTrue(self.read_json("resume-barrier.json")["warned"])

    def test_second_write_is_silent(self):
        # Once warned, further out-of-allowlist writes are silent: surface once per arming, never a nag
        # wall (aiqt_hooks.py:9833-9834).
        self.write_registry(self.stage1())
        self._arm_barrier(warned=True)
        r = self.run_hook("orch_resume_barrier", {
            "tool_name": "Write", "tool_input": {"file_path": self._p("some", "unrelated.py")},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_write_to_record_surface_is_silent(self):
        # The record surfaces stay writable, so the only exit (correcting the record) is never obstructed
        # (aiqt_hooks.py:9820-9832).
        self.write_registry(self.stage1())
        self._arm_barrier(warned=False)
        self.write_record_files()
        r = self.run_hook("orch_resume_barrier", {
            "tool_name": "Write", "tool_input": {"file_path": self._p("open-findings.md")},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "", "a write to a record surface passes silently")

    def test_write_to_state_dir_is_silent(self):
        self.write_registry(self.stage1())
        self._arm_barrier(warned=False)
        r = self.run_hook("orch_resume_barrier", {
            "tool_name": "Write", "tool_input": {"file_path": str(self.state_dir() / "scratch.json")},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_write_to_registry_file_is_silent(self):
        self.write_registry(self.stage1())
        self._arm_barrier(warned=False)
        r = self.run_hook("orch_resume_barrier", {
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.repo / ".aiqt" / "orchestration.json")},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_record_key_is_load_bearing_for_allowlist(self):
        # LOAD-BEARING contrast: drop only the `record` key (keeping state_dir so the barrier is found).
        # The same write to the former findings surface is now OUTSIDE the allowlist and warns, proving
        # the record key is what keeps the record surfaces writable under the barrier.
        reg = self.stage1()
        findings_path = reg["record"]["findings"]
        del reg["record"]
        self.write_registry(reg)
        self._arm_barrier(warned=False)
        r = self.run_hook("orch_resume_barrier", {
            "tool_name": "Write", "tool_input": {"file_path": findings_path},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.stdout_json(r)
        self.assertIsNotNone(out, "without the record key the findings surface is no longer exempt")
        self.assertIn("resume barrier", out["systemMessage"])


# =====================================================================================================
# 6. Adversarial: a corrupted (truncated-JSON) registry -> the bad-registry class (unchanged by stage 1)
# =====================================================================================================
class CorruptedRegistry(HookHarness):
    TRUNCATED = '{ "version": 1, "record": { "findings":'

    def test_dispatch_ledger_silent_allow(self):
        # status != "ok" -> _allow(); no row (aiqt_hooks.py:9256-9257).
        self.write_registry(self.TRUNCATED)
        self.arm_lease()
        r = self.run_hook("orch_dispatch_ledger", {
            "tool_name": "Bash", "tool_input": {"run_in_background": True}, "tool_response": {},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")
        self.assertEqual(self.find_anywhere("dispatch-ledger.jsonl"), [])

    def test_prompt_stamp_silent_allow(self):
        # status != "ok" -> _allow() (aiqt_hooks.py:9314-9315).
        self.write_registry(self.TRUNCATED)
        self.arm_lease()
        r = self.run_hook("orch_prompt_stamp", {"prompt": "hello"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")
        self.assertEqual(self.find_anywhere("turn-state.json"), [])

    def test_resume_audit_warns_naming_the_registry(self):
        # status == "bad" -> a warn naming the unreadable registry and barrier active:true
        # (aiqt_hooks.py:9776-9793).
        self.write_registry(self.TRUNCATED)
        r = self.run_hook("orch_resume_audit", {})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.stdout_json(r)
        self.assertIn("registry could not be read", out["systemMessage"])
        # A bad registry declares no state_dir, so the barrier lands at the XDG default.
        self.assertTrue(self.read_json_anywhere("resume-barrier.json")["active"])

    def test_resume_barrier_allows(self):
        # status != "ok" -> _allow(), even with a pre-armed barrier (aiqt_hooks.py:9806-9807).
        self.write_registry(self.TRUNCATED)
        self.seed_state("resume-barrier.json", {"active": True, "warned": False, "findings": []})
        r = self.run_hook("orch_resume_barrier", {
            "tool_name": "Write", "tool_input": {"file_path": self._p("x.py")},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "")

    def test_stop_guard_fails_open_warn(self):
        # DURABLE PIN of the fail-OPEN posture at aiqt_hooks.py:8579-8583, refuting the gemini seed's
        # fail-closed claim: a bad registry warns (exit 0) and blocks NOTHING at the Stop boundary.
        self.write_registry(self.TRUNCATED)
        r = self.run_hook("orch_stop_guard", {})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.stdout_json(r)
        self.assertIn("registry could not be read", out["systemMessage"])
        self.assertIn("fails open", out["systemMessage"])

    def test_yield_tool_fails_closed_deny(self):
        # PIN of the PRE-EXISTING fail-closed class (unchanged by stage 1): a bad registry denies a
        # scheduling call. A PreToolUse deny is exit 0 with permissionDecision "deny"
        # (aiqt_hooks.py:8654-8661, _deny at :195-201).
        self.write_registry(self.TRUNCATED)
        r = self.run_hook("orch_yield_tool", {
            "tool_name": "ScheduleWakeup", "tool_input": {},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.stdout_json(r)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")


# =====================================================================================================
# 7. Missing / unwritable state_dir (aiqt_hooks.py:7666, 9301-9303)
# =====================================================================================================
class StateDirIO(HookHarness):
    def test_missing_state_dir_is_created_on_demand(self):
        # The recorders makedirs the state dir on demand and the row lands (aiqt_hooks.py:7666).
        self.write_registry(self.stage1())
        self.arm_lease()
        self.assertFalse(self.state_dir().exists(), "precondition: state_dir does not yet exist")
        r = self.run_hook("orch_dispatch_ledger", {
            "tool_name": "Bash", "tool_input": {"run_in_background": True}, "tool_response": {},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIsNotNone(self.read_jsonl("dispatch-ledger.jsonl"))

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory write permissions")
    def test_unwritable_state_dir_surfaces_failed_write(self):
        # An unwritable state dir makes the ledger append fail; it surfaces a non-blocking systemMessage
        # and never denies (aiqt_hooks.py:9301-9303). The prompt stamp likewise exits 0.
        self.write_registry(self.stage1())
        self.arm_lease()
        sd = self.state_dir()
        sd.mkdir(parents=True)
        os.chmod(sd, 0o555)
        try:
            r = self.run_hook("orch_dispatch_ledger", {
                "tool_name": "Bash", "tool_input": {"run_in_background": True}, "tool_response": {},
            })
            self.assertEqual(r.returncode, 0, r.stderr)
            out = self.stdout_json(r)
            self.assertIn("write failed", out["systemMessage"])
            r2 = self.run_hook("orch_prompt_stamp", {"prompt": "hello"})
            self.assertEqual(r2.returncode, 0, r2.stderr)
        finally:
            os.chmod(sd, 0o755)


# =====================================================================================================
# 8. Stale lease (aiqt_hooks.py:7793-7798, 9400-9401)
# =====================================================================================================
class StaleLease(HookHarness):
    def test_recorders_noop_under_stale_lease(self):
        # A lease older than max_age_hours is not fresh, so scope is not live and the recorders write
        # nothing (aiqt_hooks.py:7798-7799).
        self.write_registry(self.stage1())
        self.arm_lease(age_seconds=2 * 24 * 3600)  # two days old, past the 24h horizon
        r = self.run_hook("orch_dispatch_ledger", {
            "tool_name": "Bash", "tool_input": {"run_in_background": True}, "tool_response": {},
        })
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.find_anywhere("dispatch-ledger.jsonl"), [])

    def test_audit_reports_stale_lease(self):
        # The resume audit surfaces the staleness as a warn-only finding (aiqt_hooks.py:9400-9401).
        self.write_registry(self.stage1())
        self.arm_lease(age_seconds=2 * 24 * 3600)
        self.write_record_files(handoff="no markers\n")
        r = self.run_hook("orch_resume_audit", {})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.stdout_json(r)
        self.assertIn("stale", out["systemMessage"])
        self.assertTrue(self.read_json("resume-barrier.json")["active"])


# =====================================================================================================
# 9. Stop-family surface: stage-1 fixture, live lease, NO operator sentinel (aiqt_hooks.py:8196-8213,
#    8190-8214, 8542-8566)
# =====================================================================================================
class StopFamilySurface(HookHarness):
    def test_stop_denies_with_no_enumerator(self):
        # With scope live and no enumerator declared, a turn-end Stop is DENIED once (exit 2) with the
        # NO_ENUMERATOR reason (aiqt_hooks.py:7966-7968, 8196+8208-8213, 8590-8599).
        self.write_registry(self.stage1())
        self.arm_lease()
        r = self.run_hook("orch_stop_guard", {})
        self.assertEqual(r.returncode, 2, "a live-lease no-enumerator Stop denies (exit 2)")
        self.assertIn("NO_ENUMERATOR", r.stderr)

    def test_followup_stop_releases_with_forced_exit_row(self):
        # The follow-up Stop carrying stop_hook_active:true releases as ALLOW_WITH_FINDINGS (exit 0) and
        # appends a forced-exit row (aiqt_hooks.py:8192-8195, 8601-8607, 8542-8561).
        self.write_registry(self.stage1())
        self.arm_lease()
        r = self.run_hook("orch_stop_guard", {"stop_hook_active": True})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.stdout_json(r)
        self.assertIn("loop bound", out["systemMessage"])
        rows = self.read_jsonl("forced-exit.jsonl")
        self.assertIsNotNone(rows, "a forced release past an unenumerable backlog is recorded")
        self.assertEqual(rows[0]["event"], "Stop")

    def test_self_owned_sentinel_is_ignored_and_spoof_recorded(self):
        # A sentinel owned by the hook's OWN euid is not the operator's; it is ignored (the Stop still
        # denies) and recorded as a spoof (aiqt_hooks.py:7897-7898, 8511-8521).
        #
        # NOTE: the sentinel HONOUR leg (a sentinel owned by a DIFFERENT uid opening the clean-ALLOW
        # channel, aiqt_hooks.py:8190-8191) needs a second uid to create a foreign-owned file and cannot
        # run in single-uid CI; it is verified at arming on the host with the root-owned sentinel.
        self.write_registry(self.stage1())
        self.arm_lease()
        sd = self.state_dir()
        sd.mkdir(parents=True, exist_ok=True)
        sentinel = sd / "ESCAPE-ALLOW-YIELD"
        sentinel.write_text("", encoding="utf-8")
        os.chmod(sentinel, 0o644)
        self.assertEqual(os.stat(sentinel).st_uid, os.geteuid(), "precondition: self-owned sentinel")
        r = self.run_hook("orch_stop_guard", {})
        self.assertEqual(r.returncode, 2, "a self-owned sentinel does not open the escape channel")
        spoof = self.read_json("escape-spoof.json")
        self.assertIsNotNone(spoof, "an ignored sentinel is spoof-recorded")
        self.assertIn("uid", (spoof.get("detail") or ""))


if __name__ == "__main__":
    unittest.main()
