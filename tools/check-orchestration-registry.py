#!/usr/bin/env python3
"""Validate the structural integrity of `.aiqt/orchestration.json`.

The AIQT orchestration hooks read `.aiqt/orchestration.json` (or the machine-local
`.aiqt/orchestration.local.json`) and classify it `ok` only when it is a JSON object
whose `version` is the integer 1. A malformed, unreadable, or non-version-1 committed
registry classifies `bad`. A `bad` registry does not disarm uniformly: the write-scope
companion exemption empties (cross-repository writes deny, which is fail-safe), but the
scope-gated orchestrator guards diverge on it. `orch_stop_guard` fails OPEN with a warning,
`orch_yield_tool` fails CLOSED (it denies a scheduling call, even with no lease or mode),
and `orch_dispatch_ledger` silently allows without recording. This gate rejects a
structurally invalid committed registry before it lands, so a corrupt registry cannot reach
a session where those outcomes matter.

It validates STRUCTURE only, and mirrors what the hook's `_orch_registry` and
`_wrtscp_companion_stores` accept or reject: a genuinely absent registry passes (the suite
is inert by design), a present-but-unreadable one fails (matching the hook's `lstat` then
read, which classify a permission fault or a dangling symlink as `bad`), and each
`companion_stores` entry must be a non-empty absolute path (OS-agnostic, like the hook's
`_is_absolute`) with no control character (below 0x20 or 0x7f) or lone surrogate code point
(U+D800..U+DFFF). Whether an entry resolves to
a live git top level is a runtime property the hook checks fail-safe; the path need not
exist on the machine running this gate.

Usage: check-orchestration-registry.py [registry-path]
The path defaults to `<repo-root>/.aiqt/orchestration.json`. Exit 0 when the registry is
genuinely absent (it is optional) or valid; exit 1 on a structural defect or an unreadable
present registry.
"""
import json
import os
import pathlib
import re
import stat
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REGISTRY = os.path.join(ROOT, ".aiqt", "orchestration.json")

# Stage-1 top-level allowlist. Any other top-level key is rejected: a new arming key
# (an enumerator, a yield-tool roster, a mode record) lands only together with the gate
# extension that validates it, so an unrecognized key is an ahead-of-gate or malformed
# registry, never silently accepted. This also mechanically keeps a strict-lint omission
# such as `lease.holder_is_session_id` out of the committed registry.
ALLOWED_KEYS = {"version", "companion_stores", "record", "lease", "state_dir", "dispatch_tools"}
# The record surfaces the hook's resume audit and barrier read (aiqt_hooks.py:9355-9391, 9820-9832).
RECORD_KEYS = {"findings", "pending_decisions", "handoff"}
# The lease shape _orch_scope_live and the resume audit read (aiqt_hooks.py:7786-7817, 9392-9409).
LEASE_KEYS = {"path", "max_age_hours"}
# A gate-side sanity bound on `lease.max_age_hours`, STRICTER than the hook. The hook's lease-freshness
# read (aiqt_hooks.py:7793-7798) checks only `max_age_hours > 0` and applies NO upper bound to it (the
# freshness window is `max_age * 3600`). _ORCH_MAX_HORIZON_HOURS = 8760 (aiqt_hooks.py:8265) bounds the
# STALENESS schema's task_hours/external_hours (aiqt_hooks.py:8298-8299), NOT the lease. Capping the
# committed lease at one year here is stricter than the hook, which is fail-safe for a committed artefact.
MAX_AGE_HOURS_MAX = 8760
# POSIX filesystem length limits, applied as a pure commit-time string check to every declared path
# (codex QA HIGH-2). A component longer than NAME_MAX, or a whole path longer than PATH_MAX, is what the
# kernel rejects with ENAMETOOLONG at runtime. An over-long declared state_dir would, through exactly that
# ENAMETOOLONG, drive write_scope_guard to a persistent covered-write denial (see _check_declared_path), so
# it is caught here at author time rather than left to fail closed at every write.
NAME_MAX = 255   # bytes, a single path component
PATH_MAX = 4096  # bytes, a whole path
# Reserve room UNDER state_dir for the machine-state files the hooks WRITE there (codex QA HIGH-1, round 5).
# _check_declared_path already bounds the state_dir STRING at PATH_MAX, but the hooks then join a basename
# onto it, so a DERIVED path `<state_dir>/<basename>` can exceed PATH_MAX even when state_dir itself does
# not. At runtime that overflow raises ENAMETOOLONG in write_scope_guard._load_write_scope's
# `os.lstat(<state_dir>/write-scope.json)` (aiqt_hooks.py:9948-9953 via 10014-10015), the write-scope reader
# classifies it 'bad', and an armed session then denies every covered write persistently
# (aiqt_hooks.py:10388-10392). The longest basename the hooks derive under state_dir is
# "attestations-validated.json" (27 bytes; the longest of every filename joined onto
# _orch_state_dir_for_root in aiqt_hooks.py -- e.g. write-scope.json, resume-barrier.json,
# dispatch-ledger.jsonl, forced-exit-surfaced.json, backlog-checkpoint.json, ESCAPE-ALLOW-YIELD). We reserve
# that PLUS generous headroom, rounded up to 64, so a future recorder filename needs no re-count and one
# path separator is covered. The state_dir-specific check below rejects a state_dir that leaves less than
# this reserve (plus a separator) below PATH_MAX.
STATE_DERIVED_RESERVE = 64  # bytes; >= len("attestations-validated.json") (27) + margin


def _fail(msg):
    print("check-orchestration-registry: FAIL: {}".format(msg), file=sys.stderr)
    sys.exit(1)


def _is_absolute(path):
    # OS-agnostic, matching the hook's _is_absolute: a POSIX absolute path OR a Windows path
    # carrying both a drive and a root. This keeps the gate from falsely rejecting an entry the
    # hook would accept when the gate runs on a different OS than the committer.
    #
    # Disclosed residual (codex QA LOW, not fixed): because this is OS-agnostic, a PureWindowsPath value
    # such as `C:\x` reads as absolute here, matching the installed hook and the pack's lab_infra
    # validator. On this POSIX host the POSIX hook would instead resolve such a value RELATIVE to the
    # repo. This is left as a disclosed residual rather than fixed, to preserve cross-OS parity with the
    # pack; the committed store paths are POSIX-absolute, and both human review and the committed-registry
    # change-carries-check guard the committed registry against a stray Windows-shaped path.
    return pathlib.PurePosixPath(path).is_absolute() or pathlib.PureWindowsPath(path).is_absolute()


def _has_unsafe_char(text):
    # A control character (below 0x20 or 0x7f DEL) OR a lone surrogate code point (U+D800..U+DFFF) in a
    # declared path is load-bearing to reject, not cosmetic. Both crash the same PreToolUse path.
    # Control character: a NUL in a record path reaches os.path.realpath inside orch_resume_barrier
    # (aiqt_hooks.py:9828), which raises ValueError. Surrogate: a lone surrogate CANNOT be UTF-8 encoded
    # (it is unpaired), so when the hook resolves the declared path (os.path.realpath / open in
    # orch_resume_barrier, aiqt_hooks.py:9828-9830, a PreToolUse event) the encode to the filesystem
    # encoding raises UnicodeEncodeError. Either crash makes the PreToolUse dispatcher fail closed exit 2
    # (aiqt_hooks.py:10705-10716) -- the one route by which a stage-1 key could reach a blocking outcome.
    # Rejecting surrogates here closes exactly the route the control-char rejection claims to close
    # (closes the codex QA HIGH). The gate closes it for the committed file (matching _wrtscp/companion_stores).
    return any(ord(ch) < 0x20 or ord(ch) == 0x7f or 0xD800 <= ord(ch) <= 0xDFFF for ch in text)


def _norm_pathspell(p):
    # Canonicalize a declared path for a containment comparison: collapse `.`, `..`, and redundant
    # separators with normpath, THEN collapse any leading run of 2+ slashes to a single slash. POSIX
    # normpath PRESERVES a leading exactly-"//" (its value is implementation-defined per POSIX) and already
    # collapses 3+, so the only residual after normpath is a leading "//"; collapsing it makes "/a", "//a",
    # and "///a" all compare equal. Without this, an alias spelling defeats the commonpath containment test
    # below (norm("//opt/x") != norm("/opt/x")), which is codex QA HIGH-1's bypass.
    return re.sub(r"^/{2,}", "/", os.path.normpath(p))


def _contains_or_equal(child, parent):
    # True when absolute `child` equals `parent` or lies inside it, decided component-wise by commonpath
    # (so a genuine sibling like /opt/x/orch-state-extra is NOT read as inside /opt/x/orch-state, whose
    # commonpath is /opt/x). Both arguments are absolute -- either canonicalized spellings (_norm_pathspell)
    # or realpath'd values. commonpath raises ValueError only on mixing absolute and relative paths, or (on
    # Windows) paths on different drives; neither applies to two validated absolute POSIX-shaped paths, but
    # if it somehow does, treat it as a collision and fail defensively rather than accept an unproven-safe
    # path. Shared by the lexical and the resolved-path containment checks (codex QA HIGH-1).
    if child == parent:
        return True
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:
        return True


def _check_declared_path(label, value):
    # A registry-declared path (a record surface, the lease, the state dir, a companion store) must be a
    # non-empty absolute string with no control or surrogate character, the same shape the hook's _orch_path
    # plus its realpath walk need.
    if not isinstance(value, str) or not value:
        _fail("`{}` must be a non-empty string, got {!r}".format(label, value))
    if not _is_absolute(value):
        _fail("`{}` must be an absolute path, got {!r}".format(label, value))
    if _has_unsafe_char(value):
        _fail("`{}` contains a control or surrogate character".format(label))
    # Reject an over-long path: any single component longer than NAME_MAX bytes, or a whole path longer than
    # PATH_MAX bytes. This is a PURE STRING check (fires in CI, no filesystem access). It closes codex QA
    # HIGH-2's ENAMETOOLONG case: an over-long declared state_dir drives write_scope_guard._load_write_scope
    # to a persistent covered-write DENIAL -- lstat(<state_dir>/write-scope.json) raises ENAMETOOLONG, the
    # artifact reader classifies it 'bad', and an armed session then denies every covered write
    # (aiqt_hooks.py:9940-9946, 10015, 10388-10392). Measured in BYTES, not code points, because the kernel
    # limits are on the UTF-8 encoded length; surrogatepass keeps this from crashing on a surrogate that
    # _has_unsafe_char has already rejected above.
    # PATH_MAX (4096) INCLUDES the terminating NUL, so the longest USABLE pathname is PATH_MAX - 1 (4095)
    # bytes; a 4096-byte path passes a `> PATH_MAX` test but the kernel rejects it with ENAMETOOLONG at
    # runtime (os.stat -> errno 36), which for a lease/state path drives the hook's stat to an OSError and,
    # with no mode declared, an inactive scope (aiqt_hooks.py:7791,7813) -- so reject `>= PATH_MAX` (codex QA
    # round 8). NAME_MAX (255) EXCLUDES the NUL, so the component check below correctly stays `> NAME_MAX`.
    if len(value.encode("utf-8", "surrogatepass")) >= PATH_MAX:
        _fail("`{}` is {} bytes; the longest usable path is {} bytes (PATH_MAX {} counts the NUL)".format(
            label, len(value.encode("utf-8", "surrogatepass")), PATH_MAX - 1, PATH_MAX))
    # Measure each component against NAME_MAX splitting on "/" ONLY -- POSIX component semantics. On POSIX a
    # backslash is a VALID filename character, so an intrinsically over-long single component like
    # ("a"*150 + "\\" + "a"*150) (301 bytes, ONE POSIX component) must NOT be broken at the backslash into
    # two <=255-byte sub-components and wrongly accepted, only to hit ENAMETOOLONG at runtime (codex QA
    # HIGH-2, round 6; this corrects the `[/\\]` split introduced in round 5, which under-counted such a
    # component). A Windows-shaped path's backslash-separated segments are therefore measured as one run,
    # which OVER-counts rather than under-counts: it can only make an over-long Windows path reject, never
    # wrongly accept, so it stays fail-safe. The committed store paths are POSIX.
    for comp in value.split("/"):
        if len(comp.encode("utf-8", "surrogatepass")) > NAME_MAX:
            _fail("`{}` has a path component longer than {} bytes (NAME_MAX)".format(label, NAME_MAX))


def validate(path):
    # Presence, matching the hook: a genuine FileNotFoundError on lstat is absence (pass); any other
    # stat fault (a permission error, a symlink loop) or a read failure (a dangling symlink follows to a
    # missing target) is a present-but-unreadable registry, which the hook classifies `bad`, so fail
    # rather than pass. os.path.exists would swallow both to False and read them as absent.
    try:
        os.lstat(path)
    except FileNotFoundError:
        print("check-orchestration-registry: no {} (optional); nothing to validate.".format(path))
        return
    except OSError as exc:
        _fail("cannot stat {}: {}".format(path, exc))
    # Disclosed residual (codex/claude QA LOW, not fixed here): the presence check is an lstat followed by
    # a plain blocking open() below, so a FIFO/named-pipe left at the registry path with no writer would
    # block this open indefinitely. The same special-file hazard applies to a declared record/lease/state
    # path: were one to point at a FIFO, it would block the HOOK's own read at read time, not this gate.
    # That is out of the gate's scope: the gate validates the registry STRING (non-empty, absolute,
    # control/surrogate-free), not the file type of the target, which may not exist at gate time. This is
    # CI-SAFE: git cannot check out a FIFO, so the only exposure is an exotic hand-crafted local run, never
    # a checked-out tree; the declared paths are store paths. lab_infra's validator opens
    # O_RDONLY|O_NONBLOCK and fstat-checks S_ISREG, and is the consolidation point at the stage-2 lift;
    # this gate is left as a disclosed residual rather than duplicating that hardening now.
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        _fail("{} is present but unreadable: {}".format(path, exc))
    except (UnicodeError, ValueError) as exc:
        # A non-UTF-8 registry raises UnicodeDecodeError (a ValueError) here at read/decode time,
        # not at json.loads; catch it so the gate reports a clean diagnostic, not a traceback.
        _fail("{} is not valid UTF-8: {}".format(path, exc))
    try:
        obj = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        # ValueError covers ordinary malformed JSON; RecursionError (NOT a ValueError) covers deeply
        # nested JSON (e.g. many thousands of open brackets) that overflows json's recursive scanner.
        # Catching it keeps the gate a clean FAIL rather than an uncaught traceback (still fail-closed).
        _fail("{} is not valid JSON: {}".format(path, exc))
    if not isinstance(obj, dict):
        _fail("{} top level must be a JSON object, got {}".format(path, type(obj).__name__))
    # `version` must be exactly the integer 1. bool is a subclass of int, so exclude it explicitly;
    # this mirrors the hook's `type(version) is int and version == 1` classification.
    version = obj.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        _fail("`version` must be the integer 1, got {!r}".format(version))
    # `companion_stores`, if present, must be a list of non-empty absolute path strings with no control
    # character (below 0x20 or 0x7f), matching _wrtscp_companion_stores. The hook drops a malformed entry
    # fail-safe at runtime; this catches it at author time so the intended exemption is not silently lost.
    if "companion_stores" in obj:
        stores = obj["companion_stores"]
        if not isinstance(stores, list):
            _fail("`companion_stores` must be a list, got {}".format(type(stores).__name__))
        for i, entry in enumerate(stores):
            # Route through the shared declared-path helper: same non-empty/absolute/control-and-surrogate
            # checks as before, now also covered by the NAME_MAX/PATH_MAX over-long check (codex QA HIGH-2).
            _check_declared_path("companion_stores[{}]".format(i), entry)
    # Reject any top-level key outside the stage-1 allowlist. A new arming key lands only together with
    # its gate extension, so an unrecognized key is an ahead-of-gate or malformed registry.
    for key in obj:
        if key not in ALLOWED_KEYS:
            _fail("unknown top-level key {!r}; a new arming key lands only together with its gate "
                  "extension".format(key))
    # `record`, if present: a non-empty object whose keys are a subset of RECORD_KEYS, each value a
    # declared (non-empty absolute control-free) path.
    if "record" in obj:
        record = obj["record"]
        if not isinstance(record, dict):
            _fail("`record` must be a JSON object, got {}".format(type(record).__name__))
        if not record:
            _fail("`record` must not be empty")
        extra = set(record) - RECORD_KEYS
        if extra:
            _fail("`record` has unknown key(s) {}".format(sorted(extra)))
        for key in sorted(record):
            _check_declared_path("record.{}".format(key), record[key])
    # `lease`, if present: an object whose keys are a subset of LEASE_KEYS; `path` is REQUIRED and a
    # declared path; `max_age_hours` is optional but, when present, a non-bool int or float in (0, 8760].
    if "lease" in obj:
        lease = obj["lease"]
        if not isinstance(lease, dict):
            _fail("`lease` must be a JSON object, got {}".format(type(lease).__name__))
        extra = set(lease) - LEASE_KEYS
        if extra:
            _fail("`lease` has unknown key(s) {}".format(sorted(extra)))
        if "path" not in lease:
            _fail("`lease.path` is required")
        _check_declared_path("lease.path", lease["path"])
        if "max_age_hours" in lease:
            v = lease["max_age_hours"]
            # bool is a subclass of int; reject it. NaN/Infinity fail the range comparison and are
            # rejected too. The (0, 8760] window is a gate-side sanity cap, STRICTER than the hook, which
            # applies no upper lease bound (see MAX_AGE_HOURS_MAX above); stricter is fail-safe here.
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not (0 < v <= MAX_AGE_HOURS_MAX):
                _fail("`lease.max_age_hours` must be a number in (0, {}], got {!r}".format(
                    MAX_AGE_HOURS_MAX, v))
    # `state_dir`, if present: a declared path.
    if "state_dir" in obj:
        _check_declared_path("state_dir", obj["state_dir"])
        # Reserve room for the DERIVED machine-state paths (codex QA HIGH-1, round 5). _check_declared_path
        # bounded the state_dir STRING at PATH_MAX, but the hooks join a basename onto it, so a near-limit
        # state_dir makes `<state_dir>/<basename>` overflow PATH_MAX even though state_dir itself did not.
        # At runtime that overflow raises ENAMETOOLONG in lstat(<state_dir>/write-scope.json), the
        # write-scope reader classifies it 'bad', and an armed session denies every covered write
        # persistently. Require len(state_dir) + one separator + STATE_DERIVED_RESERVE <= PATH_MAX, measured
        # in BYTES (surrogatepass matches _check_declared_path, though surrogates are already rejected above).
        _sd_bytes = len(obj["state_dir"].encode("utf-8", "surrogatepass"))
        # `>= PATH_MAX`, not `> PATH_MAX`: the derived path <state_dir>/<basename> must itself be <= PATH_MAX-1
        # usable bytes (codex QA round 8, same off-by-one class as the whole-path check above).
        if _sd_bytes + 1 + STATE_DERIVED_RESERVE >= PATH_MAX:
            _fail("`state_dir` ({!r}) is {} bytes and leaves no room under PATH_MAX ({}) for the "
                  "machine-state files the hooks derive under it: {} bytes + 1 separator + {} reserved "
                  "for the longest derived filename exceeds PATH_MAX, so a path like "
                  "<state_dir>/write-scope.json would hit ENAMETOOLONG and drive write_scope_guard to a "
                  "persistent covered-write denial".format(
                      obj["state_dir"], _sd_bytes, PATH_MAX, _sd_bytes, STATE_DERIVED_RESERVE))
        # BEST-EFFORT gate-time type check (codex QA HIGH-2): classify the declared state_dir by what its
        # lstat actually reports. write_scope_guard._load_write_scope reads <state_dir>/write-scope.json;
        # when state_dir is a regular file (e.g. "/etc/passwd") or a path THROUGH a regular file (e.g.
        # "/etc/passwd/" or "/etc/passwd/state") that read's lstat raises ENOTDIR, the artifact reader
        # classifies it 'bad', and an armed session then DENIES every covered write persistently
        # (aiqt_hooks.py:9948-9953, 10015, 10388-10392). Three outcomes, distinguished (round-5 fix; round-4
        # collapsed every OSError to absence and ACCEPTED a known-unusable path):
        #   - FileNotFoundError: GENUINE ABSENCE -> do NOT fail (the not-yet-created residual stays
        #     disclosed; the gate cannot verify a not-yet-created directory).
        #   - a successful lstat that is NOT a directory -> _fail (an existing non-dir, e.g. a regular file
        #     or a dangling symlink whose lstat succeeds).
        #   - ANY OTHER OSError (ENOTDIR, ENAMETOOLONG, ELOOP, EACCES, ...): the path is KNOWN-UNUSABLE at
        #     gate time -> _fail naming it, since the hook hits the same fault at runtime. Do NOT swallow it
        #     as absence.
        # This is BEST-EFFORT, NOT a soundness guarantee: a state_dir absent at gate time but created as a
        # FILE, or unusable at runtime (a read-only or different filesystem), is NOT caught here. os.lstat
        # (not os.stat/os.path.exists) so a symlink is judged by the link itself.
        try:
            _sd_st = os.lstat(obj["state_dir"])
        except FileNotFoundError:
            _sd_st = None  # genuine absence: do NOT fail
        except OSError as exc:
            _fail("`state_dir` ({!r}) cannot be used as a directory at gate time ({}); the hooks write "
                  "machine-state files inside it, so a known-unusable state_dir drives write_scope_guard "
                  "to a persistent covered-write denial".format(obj["state_dir"], exc))
        if _sd_st is not None and not stat.S_ISDIR(_sd_st.st_mode):
            _fail("`state_dir` ({!r}) exists at gate time but is not a directory; the hooks write "
                  "machine-state files inside it, and a non-directory state_dir drives write_scope_guard "
                  "to a persistent covered-write denial".format(obj["state_dir"]))
    # Cross-field REQUIREMENT (claude QA HIGH, round 7): a declared `record` or `lease` must be accompanied
    # by an explicit `state_dir`. When `state_dir` is OMITTED the hooks do NOT stop using a state dir --
    # _state_dir_from_registry (aiqt_hooks.py:7638-7651) falls back to
    # ${XDG_STATE_HOME:-~/.local/state}/aiqt-guardrails/orch/<repo-key>/, and orch_resume_audit still opens
    # `<state_dir>/resume-barrier.json` with mode "w" there (aiqt_hooks.py:9783-9785). A record/lease path
    # landing inside that DEFAULT dir is clobbered exactly as the round-3 declared-state_dir collision, but
    # the collision check below runs only `if "state_dir" in obj`, so the default-dir sibling slips through
    # (claude QA round 7, reproduced gate-exit-0 -> hook clobber of the declared record). Requiring
    # `state_dir` alongside record/lease closes the whole class at gate time: the location is then validated
    # and collision-checked, and a gate-passing armed registry never falls back to the XDG default.
    # `dispatch_tools` carries tool NAMES, not a path, so it cannot collide and does not trigger this.
    if ("record" in obj or "lease" in obj) and "state_dir" not in obj:
        _fail("`record`/`lease` is declared without `state_dir`: the hooks then fall back to an XDG-default "
              "state directory ($XDG_STATE_HOME/aiqt-guardrails/orch/<repo-key>, aiqt_hooks.py:7638-7651) "
              "that this gate never sees, and orch_resume_audit's unconditional `<state_dir>/"
              "resume-barrier.json` write clobbers any record/lease path landing inside it; declare "
              "`state_dir` explicitly so the machine-state location is validated and collision-checked")
    # Cross-field collision (codex QA HIGH): a declared record/lease path that lands ON or INSIDE
    # `state_dir` collides with the machine-state files the hooks write there. orch_resume_audit opens
    # `<state_dir>/resume-barrier.json` with mode "w" UNCONDITIONALLY (aiqt_hooks.py:9775, 9783-9785), so
    # a record/lease path pointing into state_dir would be clobbered by that hook write (destructive, no
    # lease needed). The per-key checks above validate each path in isolation and cannot see this; this
    # runs ONLY when `state_dir` is declared and valid (execution reaches here only past its
    # _check_declared_path). `companion_stores` is intentionally NOT checked against state_dir: a state_dir
    # legitimately MAY sit under a companion store; the hazard is a record/lease FILE landing on a
    # machine-state file, not the state directory living under an exempt store.
    if "state_dir" in obj:
        # Robust against path-spelling ALIASES (codex QA HIGH-1). The round-3 normpath+startswith test was
        # bypassed by aliases the two spellings do not share: state_dir "/" + record "/x.json" (norm_state
        # "/" + os.sep = "//", which "/x.json" does not start with), and any leading double-slash spelling
        # (POSIX normpath preserves a leading "//"). _norm_pathspell canonicalizes BOTH sides and collapses
        # that leading "//", and os.path.commonpath then decides containment component-wise, so a genuine
        # SIBLING (e.g. /opt/x/orch-state-extra vs state_dir /opt/x/orch-state -> commonpath /opt/x) is
        # still accepted while ON-or-INSIDE is rejected.
        norm_state_dir = _norm_pathspell(obj["state_dir"])
        # ADDITIONALLY compare RESOLVED paths (codex QA HIGH-1, round 6): an EXISTING symlink alias makes two
        # different spellings resolve to the same file, which the lexical check cannot see. os.path.realpath
        # resolves existing symlink components and leaves a non-existent tail intact, so a record/lease path
        # that resolves onto or into the resolved state_dir is caught even when the spellings differ (codex
        # reproduced: state_dir "/dev/shm" + record "/run/shm/resume-barrier.json" where /run/shm -> /dev/shm
        # resolve to the same barrier file). BOTH the lexical and the resolved check run -- defence in depth.
        # realpath is computed on the same state_dir as on each declared path, so a symlink anywhere in a
        # shared prefix resolves identically on both sides and cannot manufacture a false collision for a
        # genuine sibling.
        real_state_dir = os.path.realpath(obj["state_dir"])
        declared = []
        if isinstance(obj.get("record"), dict):
            for key in sorted(obj["record"]):
                declared.append(("record.{}".format(key), obj["record"][key]))
        if isinstance(obj.get("lease"), dict) and "path" in obj["lease"]:
            declared.append(("lease.path", obj["lease"]["path"]))
        for label, value in declared:
            if _contains_or_equal(_norm_pathspell(value), norm_state_dir):
                _fail("`{}` ({!r}) is on or inside `state_dir` ({!r}); a record/lease path on or under "
                      "state_dir collides with the machine-state files the hooks write there (e.g. "
                      "resume-barrier.json), so a hook write would clobber the declared record".format(
                          label, value, obj["state_dir"]))
            real_value = os.path.realpath(value)
            if _contains_or_equal(real_value, real_state_dir):
                _fail("`{}` ({!r}) RESOLVES onto or inside `state_dir` ({!r}) through an existing symlink "
                      "(record/lease resolves to {!r}, state_dir to {!r}); a hook write to a machine-state "
                      "file there (e.g. resume-barrier.json) would clobber the declared record".format(
                          label, value, obj["state_dir"], real_value, real_state_dir))
        # --- THE BOUND: accepted-input soundness is bounded to commit-time validation ---------------------
        # This gate performs COMMIT-TIME validation only. What it establishes is: structural shape + concrete
        # hazards (surrogate/control character, NAME_MAX/PATH_MAX length, derived-path reserve, record/lease-
        # vs-state_dir collision) + BEST-EFFORT resolved-path containment (above) + BEST-EFFORT state_dir
        # gate-time directory-type. Its accepted-input soundness is BOUNDED to what commit-time validation can
        # establish; the maintainer directed this bound after round 6. The residuals below are IRREDUCIBLE
        # (no commit-time string or stat check can close them). They do NOT all resolve to a fail-safe denial
        # -- claude QA round 10 corrected an earlier overstatement that each was "a denial or a caught
        # collision at runtime, never a bypass". They split by runtime outcome:
        #   FAIL-SAFE DENIALS -- a denial or a caught collision at runtime, never a bypass:
        #   (b) Runtime directory-usability of a NOT-YET-CREATED state_dir: an absent state_dir later created
        #       as a regular file, or living on a read-only or different filesystem. The best-effort lstat
        #       above classifies only what exists at gate time; genuine absence is accepted (it cannot be
        #       verified). At runtime an unusable state_dir drives write_scope_guard._load_write_scope to a
        #       persistent covered-write DENIAL (fail-safe), operator-fixable.
        #   (c) A FIFO or other special file at a declared registry/record/lease/state path: it would block
        #       the HOOK's own read at read time (see the FIFO disclosure at the presence check above, in
        #       validate()). git cannot check out a FIFO, so the only exposure is an exotic hand-crafted local
        #       run, never a checked-out tree.
        #   POST-GATE FILESYSTEM ALIASING -- a SILENT CLOBBER, not a denial; reachable ONLY with out-of-band
        #   write access to the store or state_dir that ALREADY lets the actor clobber the record directly
        #   (the recorder/audit hooks are DEFENCE IN DEPTH, not a security boundary), so it adds no exposure:
        #   (a) FUTURE symlink swap: a symlink created or retargeted AFTER this gate runs. The resolved-path
        #       check above resolves symlinks at COMMIT time only; a later swap is not observable here, and a
        #       record/lease path later aliased onto a machine-state file is clobbered by the hook write.
        #   (d) HARD LINK (or a symlink planted at a derived state path, e.g. the barrier name) between a
        #       record/lease file and a machine-state file the hooks write. os.path.realpath resolves symlinks
        #       but NOT hard links, the JSON cannot express a link, and the colliding derived file (e.g.
        #       <state_dir>/resume-barrier.json) does not exist at gate time, so no commit-time comparison can
        #       see it. orch_resume_audit's barrier write is a direct truncating open(barrier, "w") with NO
        #       S_ISREG guard (aiqt_hooks.py:9783, unlike the shared _wrtscp_read_json_artifact reader), so an
        #       aliased record file is SILENTLY CLOBBERED, not denied. Precondition: write+search access to
        #       state_dir (and, under fs.protected_hardlinks, to the record file) -- already store-defeating.
        # Also disclosed and left as a parity residual, not closed here: the OS-agnostic _is_absolute Windows
        # spelling (see its LOW disclosure in _is_absolute above). A consequence of accepting that spelling:
        # on a POSIX host the record/lease-vs-state_dir collision check does NOT catch a BACKSLASH-spelled
        # Windows collision (e.g. state_dir "C:\\s" + record "C:\\s\\resume-barrier.json"), because
        # os.path.commonpath treats each backslash string as one POSIX component and finds them disjoint; the
        # FORWARD-slash Windows spelling IS caught, and a mixed POSIX/Windows pair fails closed. Unreachable
        # for the committed POSIX artefact and guarded by the committed-registry test plus human review.
        # write_scope_guard and the recorder/audit hooks are DEFENCE IN DEPTH, not a security boundary, so a
        # fail-safe denial there is degraded-but-safe, not exploitable. The COMMITTED registry is verified
        # safe by this gate plus its tests, and human review via change-carries-check is the backstop for
        # future edits.
    # `dispatch_tools`, if present: a list of non-empty control-free strings.
    if "dispatch_tools" in obj:
        tools = obj["dispatch_tools"]
        if not isinstance(tools, list):
            _fail("`dispatch_tools` must be a list, got {}".format(type(tools).__name__))
        for i, entry in enumerate(tools):
            if not isinstance(entry, str) or not entry:
                _fail("`dispatch_tools[{}]` must be a non-empty string, got {!r}".format(i, entry))
            if _has_unsafe_char(entry):
                _fail("`dispatch_tools[{}]` contains a control or surrogate character".format(i))
    summary = "version 1"
    if "companion_stores" in obj:
        summary += ", {} companion store(s)".format(len(obj["companion_stores"]))
    arming = [k for k in ("record", "lease", "state_dir", "dispatch_tools") if k in obj]
    summary += ", arming keys: {}".format(", ".join(arming)) if arming else ", no arming keys"
    print("check-orchestration-registry: OK ({}: {})".format(path, summary))


def main(argv):
    validate(argv[1] if len(argv) > 1 else DEFAULT_REGISTRY)


if __name__ == "__main__":
    main(sys.argv)
