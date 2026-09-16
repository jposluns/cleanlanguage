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
    # _has_unsafe_char has already rejected above. Split on both separators so a Windows-shaped path's
    # components are measured too.
    if len(value.encode("utf-8", "surrogatepass")) > PATH_MAX:
        _fail("`{}` exceeds {} bytes (PATH_MAX)".format(label, PATH_MAX))
    for comp in re.split(r"[/\\]", value):
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
        if _sd_bytes + 1 + STATE_DERIVED_RESERVE > PATH_MAX:
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
        declared = []
        if isinstance(obj.get("record"), dict):
            for key in sorted(obj["record"]):
                declared.append(("record.{}".format(key), obj["record"][key]))
        if isinstance(obj.get("lease"), dict) and "path" in obj["lease"]:
            declared.append(("lease.path", obj["lease"]["path"]))
        for label, value in declared:
            norm_path = _norm_pathspell(value)
            collides = norm_path == norm_state_dir
            if not collides:
                try:
                    collides = os.path.commonpath([norm_path, norm_state_dir]) == norm_state_dir
                except ValueError:
                    # commonpath raises only on mixing absolute and relative paths, or (on Windows) paths on
                    # different drives. Both inputs here are validated absolute POSIX-shaped paths, so it
                    # should not raise; if it somehow does, treat it as a collision and fail defensively
                    # rather than accept an unproven-safe record path.
                    collides = True
            if collides:
                _fail("`{}` ({!r}) is on or inside `state_dir` ({!r}); a record/lease path on or under "
                      "state_dir collides with the machine-state files the hooks write there (e.g. "
                      "resume-barrier.json), so a hook write would clobber the declared record".format(
                          label, value, obj["state_dir"]))
        # IRREDUCIBLE RESIDUAL (codex QA HIGH-2, disclosed not closed): this gate validates commit-time
        # STRINGS and, best-effort, the state_dir's gate-time TYPE (above). It CANNOT verify runtime
        # directory-usability: a state_dir absent at gate time but unusable at runtime -- created as a file,
        # or living on a read-only or different filesystem -- would drive write_scope_guard._load_write_scope
        # to a persistent covered-write denial. That FAILS SAFE (a denial, never a bypass), is
        # operator-fixable, and is backstopped by the committed registry plus human review. write_scope_guard
        # is defence-in-depth, not a security boundary, so a fail-safe denial there is a degraded-but-safe
        # state, not an exploitable one.
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
