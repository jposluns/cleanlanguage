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
`companion_stores` entry must be a non-empty POSIX absolute path with no backslash, no
drive-letter prefix, no control character (below 0x20 or 0x7f), and no lone surrogate code
point (U+D800..U+DFFF). Whether an entry resolves to
a live git top level is a runtime property the hook checks fail-safe; the path need not
exist on the machine running this gate.

It also validates the stage-2 arming keys (`enumerator`, `yield_tools`, `mode`,
`attestations`, `mistakes_register`, `staleness`, and `escape`). Where the hook silently
substitutes a default for a malformed value (a timeout outside its window, a staleness
horizon out of range) or silently disables a control (a non-string escape path, a roster
name outside the hook matcher), this gate rejects the value instead. A declared
`yield_tools` roster is checked against the `orch_yield_tool` PreToolUse matcher, and a
declared `dispatch_tools` list against the `orch_dispatch_ledger` PostToolUse matcher, both
read from `plugin/aiqt-guardrails-hooks/hooks/hooks.json` at gate time; an unreadable or
malformed hooks.json is a gate failure, never a skip.

The gate is deliberately NARROWER than the hook. It does not try to admit every registry shape
the hook would handle correctly, which is an open-ended space; it pins the shapes this project
declares and rejects every other shape, even one the hook would act on safely. In particular:
the enumerator script (argv[2]) is a canonical relative path ending in ".py", and every later
operand is absolute, so no verdict depends on where the checkout sits; `escape` is either
undeclared (the hook then uses its default sentinel name) or names a bare file name directly
in the state_dir anchor; `staleness`, when declared, carries both horizons explicitly, and it is
declared whenever `enumerator` or `attestations` is; and a declared `lease` carries its
`max_age_hours` horizon explicitly. The last two close silent defaults: without them the hook
applies 24 hour staleness horizons nobody declared, or treats a present lease as fresh forever.
Every key the gate still accepts as optional is classified, with the hook behaviour its absence
selects, in OPTIONAL_KEY_CLASSIFICATION in tools/test-orchestration-registry.py, which derives the
optional set from this gate and fails on a key the table does not classify. A shape outside these
pins lands only together with the gate change that admits it.

Every file the gate itself opens (the registry and hooks.json) is opened non-blocking and must
be a regular file, so a FIFO, a device, or a directory at either path fails promptly rather
than blocking or reading as empty.

Usage: check-orchestration-registry.py [registry-path]
The path defaults to `<repo-root>/.aiqt/orchestration.json`. Exit 0 when the registry is
genuinely absent (it is optional) or valid; exit 1 on a structural defect or an unreadable
present registry.
"""
import json
import math
import os
import pathlib
import posixpath
import re
import stat
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REGISTRY = os.path.join(ROOT, ".aiqt", "orchestration.json")
# The vendored hook definitions. The orch_yield_tool PreToolUse matcher there bounds what a `yield_tools`
# roster may name, and the orch_dispatch_ledger PostToolUse matcher (hooks.json:276-290, matcher
# "Bash|TaskOutput" at hooks.json:278) bounds what `dispatch_tools` may name: a name outside the matcher
# never reaches the hook, so it would be a silent no-op entry.
HOOKS_JSON = os.path.join(ROOT, "plugin", "aiqt-guardrails-hooks", "hooks", "hooks.json")
# Basenames of the machine-state files the hooks WRITE or READ inside state_dir. An `escape.path` naming
# one of them would make the operator release sentinel share a name with machine state the hooks create,
# overwrite, rename, or interpret, so the gate rejects such a basename. Each entry cites its site in
# aiqt_hooks.py:
#   guard-events.jsonl           7732-7733 (_orch_guard_event via _orch_append_jsonl)
#   turn-state.json              7753-7756 (_orch_save_turn_state, open mode "w")
#   backlog-checkpoint.json      8359, 8414 (_orch_write_json_atomic)
#   checkpoint-init.marker       8360, 8424 (_orch_write_json_atomic)
#   escape-spoof.json            8520 (_orch_write_json)
#   escape-spoof.json.surfaced   9745, 9755 (os.replace of escape-spoof.json once its finding surfaces)
#   forced-exit.jsonl            8558 (_orch_append_jsonl)
#   pending-asks.jsonl           8746, 8751 (_orch_append_jsonl)
#   dispatch-ledger.jsonl        9300-9301 (_orch_append_jsonl)
#   attestations-validated.json  9639, 9670 (_orch_write_json_atomic)
#   forced-exit-surfaced.json    9715, 9734 (_orch_write_json_atomic)
#   resume-barrier.json          9775, 9783, 9809, 9837 (open mode "w")
#   resume-barrier.json.unused   9777 (_orch_append_jsonl probe on a bad registry)
#   write-scope.json             9864, 10014-10015 (_WRTSCP_DECL_REL, READ by _load_write_scope as the
#                                per-slice write-scope declaration; the hook never writes it and writes no
#                                .tmp sibling of it, so only the name itself is listed)
# _orch_write_json_atomic first writes a sibling "<name>.tmp" and then os.replace()s it (aiqt_hooks.py:
# 7719-7722), so the .tmp sibling of every atomically written file is listed too. The test suite derives
# this set independently by scanning the hook source (HookStateFileScan in test-orchestration-registry.py)
# and requires it to equal this constant, so a state file the hook gains is a red test, not a silent gap.
_ATOMIC_STATE_FILES = ("backlog-checkpoint.json", "checkpoint-init.marker", "attestations-validated.json",
                       "forced-exit-surfaced.json")
HOOK_STATE_FILES = frozenset(
    ("guard-events.jsonl", "turn-state.json", "escape-spoof.json", "escape-spoof.json.surfaced",
     "forced-exit.jsonl", "pending-asks.jsonl", "dispatch-ledger.jsonl", "resume-barrier.json",
     "resume-barrier.json.unused", "write-scope.json")
    + _ATOMIC_STATE_FILES + tuple(name + ".tmp" for name in _ATOMIC_STATE_FILES))
# A Windows drive-letter prefix, as in "C:", "C:x", "C:/x", or "C:\x".
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
# The resolved basenames an enumerator argv[0] may carry: a Python interpreter named python, python3, or
# python3.N with an optional one-letter build suffix (python3.13t, for example), matched in full. The gate
# admits only an isolated Python interpreter running a script (see the enumerator check in validate()), so
# this is an allowlist: every other resolved name, a launcher such as env, nice, or timeout, a shell, or a
# renamed script, is rejected rather than listed.
ENUM_PYTHON_NAME = re.compile(r"python(?:3(?:\.[0-9]+[a-z]?)?)?")
# The dispatch_tools names the orch_dispatch_ledger matcher routes to the hook but that the hook cannot use
# as list entries, each with the hook line that makes it so (see the dispatch_tools check in validate()).
DISPATCH_TOOLS_FORBIDDEN = {
    "TaskOutput": "the hook routes a TaskOutput call to its completion branch (aiqt_hooks.py:9264) before it "
                  "reads dispatch_tools (aiqt_hooks.py:9277), so the entry would be inert",
    "Bash": "the hook would then treat EVERY Bash call, foreground included, as a dispatch and record it in "
            "dispatch-ledger.jsonl (aiqt_hooks.py:9279-9280), not only a run_in_background launch",
}

# Stage-2 top-level allowlist. Any other top-level key is rejected: a new arming key lands
# only together with the gate extension that validates it, so an unrecognized key is an
# ahead-of-gate or malformed registry, never silently accepted. `truth` stays rejected: no
# code in the vendored hook reads it. The lease subkey allowlist below also mechanically
# keeps a strict-lint omission such as `lease.holder_is_session_id` out of the committed
# registry.
ALLOWED_KEYS = {"version", "companion_stores", "record", "lease", "state_dir", "dispatch_tools",
                "enumerator", "yield_tools", "mode", "attestations", "mistakes_register",
                "staleness", "escape"}
# The stage-2 keys that drive machine state under state_dir, or name a path that must be
# collision-checked against it, and so require an explicit `state_dir` (the same XDG-default fallback
# hazard as `record`/`lease`; see the cross-field requirement in validate()). `staleness` names no
# path and drives no write, so it is not listed.
STATE_DIR_REQUIRED_BY = ("enumerator", "yield_tools", "mode", "escape", "attestations",
                         "mistakes_register")
# The enumerator shape _orch_enumerate reads (aiqt_hooks.py:7966-7976).
ENUMERATOR_KEYS = {"argv", "timeout"}
# The enumerator timeout bound, in seconds. The hook accepts any number in (0, 600] and silently
# substitutes 60 otherwise (aiqt_hooks.py:7974), but hooks.json gives orch_stop_guard and
# orch_yield_tool a 10 second budget, so an enumerator allowed to run past it overruns the hook that
# runs it. The gate requires an explicit timeout in (0, 8], leaving headroom for the checkpoint work.
ENUMERATOR_TIMEOUT_MAX = 8
# The staleness shape _schema_staleness reads (aiqt_hooks.py:8294-8301). When `staleness` is declared the
# gate requires BOTH keys: the hook silently substitutes 24 hours for a missing or invalid one
# (aiqt_hooks.py:8297-8301, through _v_finite_pos at 8274-8279), so {} or a single field would arm a
# horizon nobody declared.
STALENESS_KEYS = {"task_hours", "external_hours"}
# Mirrors _ORCH_MAX_HORIZON_HOURS (aiqt_hooks.py:8265). The hook turns a value outside (0, 8760] into
# the 24 hour default (aiqt_hooks.py:8274-8279, 8300-8301); the gate rejects it instead.
STALENESS_HOURS_MAX = 8760
# The declared keys whose control reads the staleness horizons, so `staleness` is REQUIRED alongside each
# of these: the enumerated-backlog classification (_orch_build_ctx, aiqt_hooks.py:8439-8452, reached only
# for an enumeration that ran, 8448) and the attestation derivation (aiqt_hooks.py:9595, reached from the
# resume audit at 9657). Without `staleness` the hook applies 24 hours to both horizons (aiqt_hooks.py:
# 8297-8301), a horizon nobody declared. A yield roster or a lease alone never reaches either reader.
STALENESS_REQUIRED_BY = ("enumerator", "attestations")
# The keys a declared `mode` or `escape` object may carry (the readers are aiqt_hooks.py:7766-7767 and
# 7860); `path` is required in each.
MODE_KEYS = {"path"}
ESCAPE_KEYS = {"path"}
# The record surfaces the hook's resume audit and barrier read (aiqt_hooks.py:9355-9391, 9820-9832).
RECORD_KEYS = {"findings", "pending_decisions", "handoff"}
# The lease shape _orch_scope_live and the resume audit read (aiqt_hooks.py:7786-7817, 9392-9409).
# Both keys are REQUIRED. With `max_age_hours` absent, _orch_scope_live keeps `fresh = True`
# (aiqt_hooks.py:7792-7798) and the resume audit raises no stale-lease finding (aiqt_hooks.py:9395-9401),
# so a lease file left behind by a dead orchestrator keeps scope live forever. The committed registry
# declares 24.
LEASE_KEYS = {"path", "max_age_hours"}
# A gate-side sanity bound on `lease.max_age_hours`, STRICTER than the hook. The hook's lease-freshness
# read (aiqt_hooks.py:7793-7798) checks only `max_age_hours > 0` and applies NO upper bound to it (the
# freshness window is `max_age * 3600`). _ORCH_MAX_HORIZON_HOURS = 8760 (aiqt_hooks.py:8265) bounds the
# STALENESS schema's task_hours/external_hours (aiqt_hooks.py:8298-8299), NOT the lease. Capping the
# committed lease at one year here is stricter than the hook, which is fail-safe for a committed artefact.
MAX_AGE_HOURS_MAX = 8760
# POSIX filesystem length limits, applied as a pure commit-time string check to every declared path.
# A component longer than NAME_MAX, or a whole path longer than PATH_MAX, is what the
# kernel rejects with ENAMETOOLONG at runtime. An over-long declared state_dir would, through exactly that
# ENAMETOOLONG, drive write_scope_guard to a persistent covered-write denial (see _check_declared_path), so
# it is caught here at author time rather than left to fail closed at every write.
NAME_MAX = 255   # bytes, a single path component
PATH_MAX = 4096  # bytes, a whole path
# Reserve room UNDER state_dir for the machine-state files the hooks WRITE there.
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
    # OS-agnostic, the same predicate as the hook _is_absolute (aiqt_hooks.py:1935): a POSIX absolute path
    # OR a Windows path carrying both a drive and a root. Every caller first rejects a Windows-shaped value
    # through _is_windows_shaped below, so in practice only the POSIX branch accepts a declared path here.
    return pathlib.PurePosixPath(path).is_absolute() or pathlib.PureWindowsPath(path).is_absolute()


def _is_windows_shaped(text):
    # True for a value carrying a backslash or a leading drive letter ("C:"). The hook resolves a registry
    # path with POSIX os.path.isabs (_orch_path, aiqt_hooks.py:7631-7635; the escape anchor join,
    # aiqt_hooks.py:7863-7864), so on a POSIX host a Windows absolute spelling such as "C:\x" or "C:/x" is
    # NOT absolute there and is silently joined onto the repository root or the state_dir anchor, and a
    # backslash is an ordinary filename character rather than a separator. The gate rejects both shapes in
    # every declared path, every enumerator argv operand, and the escape path, so a value the gate accepts
    # resolves the same way in the gate and in the hook. This closes the parity residual an
    # earlier revision disclosed here, at the cost of refusing every Windows spelling outright; the committed
    # store paths are POSIX.
    return "\\" in text or bool(_DRIVE_PREFIX.match(text))


def _has_unsafe_char(text):
    # A control character (below 0x20 or 0x7f DEL) OR a lone surrogate code point (U+D800..U+DFFF) in a
    # declared path is load-bearing to reject, not cosmetic. Both crash the same PreToolUse path.
    # Control character: a NUL in a record path reaches os.path.realpath inside orch_resume_barrier
    # (aiqt_hooks.py:9828), which raises ValueError. Surrogate: a lone surrogate CANNOT be UTF-8 encoded
    # (it is unpaired), so when the hook resolves the declared path (os.path.realpath / open in
    # orch_resume_barrier, aiqt_hooks.py:9828-9830, a PreToolUse event) the encode to the filesystem
    # encoding raises UnicodeEncodeError. Either crash makes the PreToolUse dispatcher fail closed exit 2
    # (aiqt_hooks.py:10705-10716) -- the one route by which a stage-1 key could reach a blocking outcome.
    # Rejecting surrogates here closes exactly the route the control-char rejection claims to close.
    # The gate closes it for the committed file (matching _wrtscp/companion_stores).
    return any(ord(ch) < 0x20 or ord(ch) == 0x7f or 0xD800 <= ord(ch) <= 0xDFFF for ch in text)


def _norm_pathspell(p):
    # Canonicalize a declared path for a containment comparison: collapse `.`, `..`, and redundant
    # separators with normpath, THEN collapse any leading run of 2+ slashes to a single slash. POSIX
    # normpath PRESERVES a leading exactly-"//" (its value is implementation-defined per POSIX) and already
    # collapses 3+, so the only residual after normpath is a leading "//"; collapsing it makes "/a", "//a",
    # and "///a" all compare equal. Without this, an alias spelling defeats the commonpath containment test
    # below (norm("//opt/x") != norm("/opt/x")).
    return re.sub(r"^/{2,}", "/", os.path.normpath(p))


def _contains_or_equal(child, parent):
    # True when absolute `child` equals `parent` or lies inside it, decided component-wise by commonpath
    # (so a genuine sibling like /opt/x/orch-state-extra is NOT read as inside /opt/x/orch-state, whose
    # commonpath is /opt/x). Both arguments are absolute -- either canonicalized spellings (_norm_pathspell)
    # or realpath'd values. commonpath raises ValueError only on mixing absolute and relative paths, or (on
    # Windows) paths on different drives; neither applies to two validated absolute POSIX-shaped paths, but
    # if it somehow does, treat it as a collision and fail defensively rather than accept an unproven-safe
    # path. Shared by the lexical and the resolved-path containment checks.
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
    if _is_windows_shaped(value):
        _fail("`{}` ({!r}) is Windows-shaped (a backslash or a drive-letter prefix); the hook resolves a "
              "declared path with POSIX os.path.isabs (aiqt_hooks.py:7631-7635), so on a POSIX host it "
              "would not name the path its spelling suggests".format(label, value))
    if not _is_absolute(value):
        _fail("`{}` must be an absolute path, got {!r}".format(label, value))
    if _has_unsafe_char(value):
        _fail("`{}` contains a control or surrogate character".format(label))
    # Reject an over-long path: any single component longer than NAME_MAX bytes, or a whole path longer than
    # PATH_MAX bytes. This is a PURE STRING check (fires in CI, no filesystem access). It closes the
    # ENAMETOOLONG case: an over-long declared state_dir drives write_scope_guard._load_write_scope
    # to a persistent covered-write DENIAL -- lstat(<state_dir>/write-scope.json) raises ENAMETOOLONG, the
    # artifact reader classifies it 'bad', and an armed session then denies every covered write
    # (aiqt_hooks.py:9940-9946, 10015, 10388-10392). Measured in BYTES, not code points, because the kernel
    # limits are on the UTF-8 encoded length; surrogatepass keeps this from crashing on a surrogate that
    # _has_unsafe_char has already rejected above.
    # PATH_MAX (4096) INCLUDES the terminating NUL, so the longest USABLE pathname is PATH_MAX - 1 (4095)
    # bytes; a 4096-byte path passes a `> PATH_MAX` test but the kernel rejects it with ENAMETOOLONG at
    # runtime (os.stat -> errno 36), which for a lease/state path drives the hook's stat to an OSError and,
    # with no mode declared, an inactive scope (aiqt_hooks.py:7791,7813) -- so reject `>= PATH_MAX`.
    # NAME_MAX (255) EXCLUDES the NUL, so the component check below correctly stays `> NAME_MAX`.
    if len(value.encode("utf-8", "surrogatepass")) >= PATH_MAX:
        _fail("`{}` is {} bytes; the longest usable path is {} bytes (PATH_MAX {} counts the NUL)".format(
            label, len(value.encode("utf-8", "surrogatepass")), PATH_MAX - 1, PATH_MAX))
    # Measure each component against NAME_MAX splitting on "/" ONLY, POSIX component semantics.
    # A backslash never reaches this loop: _is_windows_shaped above rejects it first.
    for comp in value.split("/"):
        if len(comp.encode("utf-8", "surrogatepass")) > NAME_MAX:
            _fail("`{}` has a path component longer than {} bytes (NAME_MAX)".format(label, NAME_MAX))


def _read_regular_text(path, label):
    # Read a file the gate itself opens (the registry, hooks.json) as UTF-8 text, failing closed unless it
    # is a regular file. The open is O_NONBLOCK, so a FIFO with no writer opens at once instead
    # of blocking the gate, and fstat then rejects it, as it rejects a character or block device and a
    # directory, before a single byte is read. A plain open() would block forever on such a FIFO, and a
    # device such as /dev/null would read as empty. The fstat runs on the opened descriptor, so the type
    # judged is the type of the file actually read. A symlink is followed, as the hook open follows it
    # (aiqt_hooks.py:7619-7620); a dangling one fails the open.
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        _fail("{} ({}) is present but unreadable: {}".format(label, path, exc))
    chunks = []
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            _fail("{} ({}) is not a regular file (file mode {:o}); a FIFO, a device, or a directory is "
                  "refused rather than read".format(label, path, stat.S_IFMT(st.st_mode)))
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
    except OSError as exc:
        _fail("{} ({}) is present but unreadable: {}".format(label, path, exc))
    finally:
        os.close(fd)
    try:
        return b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError as exc:
        _fail("{} ({}) is not valid UTF-8: {}".format(label, path, exc))


def _hook_matcher_tools(event, hook_name, key):
    # The tool names the hooks.json entry under `event` that runs `hook_name` routes to the hook (its
    # matcher split on "|"): orch_yield_tool under PreToolUse for `yield_tools`, and orch_dispatch_ledger
    # under PostToolUse for `dispatch_tools` (hooks.json:276-290). A name outside this set never reaches the
    # hook, so the hook never judges it. This is a guard input, so it is read from the checkout at gate time
    # and fails closed: an unreadable, non-UTF-8, or non-JSON file, or one with no such entry carrying a
    # usable matcher, is a gate failure (cannot evaluate), never a skip or an empty set.
    raw = _read_regular_text(HOOKS_JSON, "the hook definitions file read to check `{}`".format(key))
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        _fail("cannot parse the hook definitions {} to check `{}`: {}".format(HOOKS_JSON, key, exc))
    hooks = data.get("hooks") if isinstance(data, dict) else None
    entries = hooks.get(event) if isinstance(hooks, dict) else None
    if not isinstance(entries, list):
        _fail("{} has no {} hook list; `{}` cannot be checked".format(HOOKS_JSON, event, key))
    names = set()
    found = False
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
            continue
        for hook in entry["hooks"]:
            args = hook.get("args") if isinstance(hook, dict) else None
            if isinstance(args, list) and hook_name in args:
                matcher = entry.get("matcher")
                if not isinstance(matcher, str) or not matcher:
                    _fail("the {} entry in {} has no usable matcher".format(hook_name, HOOKS_JSON))
                found = True
                names.update(matcher.split("|"))
    if not found:
        _fail("no {} entry in {} runs {}; `{}` cannot be checked against its matcher".format(
            event, HOOKS_JSON, hook_name, key))
    return names


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
    # The registry is read through _read_regular_text: a non-blocking open plus an fstat
    # S_ISREG check, so a FIFO, a device, or a directory at the registry path fails promptly instead of
    # blocking the gate or reading as empty, and a non-UTF-8 registry is a clean FAIL, not a traceback.
    # Disclosed residual: a declared record, lease, or state path pointing at a FIFO would block the read the hook
    # makes at runtime; the gate validates those paths as strings and does not open them.
    raw = _read_regular_text(path, "the registry")
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
            # checks as before, now also covered by the NAME_MAX/PATH_MAX over-long check.
            _check_declared_path("companion_stores[{}]".format(i), entry)
    # Reject any top-level key outside the stage-2 allowlist. A new arming key lands only together with
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
    # declared path; `max_age_hours` is REQUIRED too (its presence is checked at the end of validate(), after
    # every targeted check) and is a non-bool int or float in (0, 8760].
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
        # Reserve room for the DERIVED machine-state paths. _check_declared_path
        # bounded the state_dir STRING at PATH_MAX, but the hooks join a basename onto it, so a near-limit
        # state_dir makes `<state_dir>/<basename>` overflow PATH_MAX even though state_dir itself did not.
        # At runtime that overflow raises ENAMETOOLONG in lstat(<state_dir>/write-scope.json), the
        # write-scope reader classifies it 'bad', and an armed session denies every covered write
        # persistently. Require len(state_dir) + one separator + STATE_DERIVED_RESERVE <= PATH_MAX, measured
        # in BYTES (surrogatepass matches _check_declared_path, though surrogates are already rejected above).
        _sd_bytes = len(obj["state_dir"].encode("utf-8", "surrogatepass"))
        # `>= PATH_MAX`, not `> PATH_MAX`: the derived path <state_dir>/<basename> must itself be <= PATH_MAX-1
        # usable bytes (the same off-by-one class as the whole-path check above).
        if _sd_bytes + 1 + STATE_DERIVED_RESERVE >= PATH_MAX:
            _fail("`state_dir` ({!r}) is {} bytes and leaves no room under PATH_MAX ({}) for the "
                  "machine-state files the hooks derive under it: {} bytes + 1 separator + {} reserved "
                  "for the longest derived filename exceeds PATH_MAX, so a path like "
                  "<state_dir>/write-scope.json would hit ENAMETOOLONG and drive write_scope_guard to a "
                  "persistent covered-write denial".format(
                      obj["state_dir"], _sd_bytes, PATH_MAX, _sd_bytes, STATE_DERIVED_RESERVE))
        # BEST-EFFORT gate-time type check: classify the declared state_dir by what its
        # lstat actually reports. write_scope_guard._load_write_scope reads <state_dir>/write-scope.json;
        # when state_dir is a regular file (e.g. "/etc/passwd") or a path THROUGH a regular file (e.g.
        # "/etc/passwd/" or "/etc/passwd/state") that read's lstat raises ENOTDIR, the artifact reader
        # classifies it 'bad', and an armed session then DENIES every covered write persistently
        # (aiqt_hooks.py:9948-9953, 10015, 10388-10392). Three outcomes, distinguished (an earlier revision
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
    # --- stage-2 arming keys -------------------------------------------------------------------------
    # Each check rejects a value the hook would act on wrongly. Where the hook fails a malformed value
    # closed (an enumerator argv that is not a list of non-empty strings denies every Stop with
    # ENUMERATOR_ERROR, aiqt_hooks.py:7969-7972) or open to a silent default or no-op (a timeout outside
    # (0, 600] becomes 60, aiqt_hooks.py:7974; a staleness horizon out of range becomes 24,
    # aiqt_hooks.py:8300-8301; a non-string or empty escape path disables the release with no record,
    # aiqt_hooks.py:7861-7862; a roster name outside the matcher is never judged, aiqt_hooks.py:8665-8667),
    # the gate rejects the value at author time so neither outcome reaches a session.
    enum_paths = []  # enumerator operands from argv[3] on, each absolute, collision-checked below
    if "enumerator" in obj:
        spec = obj["enumerator"]
        if not isinstance(spec, dict):
            _fail("`enumerator` must be a JSON object, got {}".format(type(spec).__name__))
        extra = set(spec) - ENUMERATOR_KEYS
        if extra:
            _fail("`enumerator` has unknown key(s) {}".format(sorted(extra)))
        if "argv" not in spec:
            _fail("`enumerator.argv` is required")
        argv = spec["argv"]
        if not isinstance(argv, list) or not argv:
            _fail("`enumerator.argv` must be a non-empty list, got {!r}".format(argv))
        for i, arg in enumerate(argv):
            if not isinstance(arg, str) or not arg:
                _fail("`enumerator.argv[{}]` must be a non-empty string, got {!r}".format(i, arg))
            if _has_unsafe_char(arg):
                _fail("`enumerator.argv[{}]` contains a control or surrogate character".format(i))
            # A Windows-shaped operand (a backslash or a drive-letter prefix) is rejected in every argv
            # position: the hook runs argv verbatim with cwd at the repository root (aiqt_hooks.py:7976), so
            # on POSIX such an operand is a relative name, never the Windows path its spelling suggests.
            if _is_windows_shaped(arg):
                _fail("`enumerator.argv[{}]` ({!r}) is Windows-shaped (a backslash or a drive-letter "
                      "prefix); the hook runs it on POSIX, where it is not the path it spells".format(i, arg))
        # argv[0] must be absolute: the hook runs argv with no shell and cwd set to the repository root
        # (aiqt_hooks.py:7976), so a bare interpreter name would resolve through the session PATH, an
        # ambient binding the registry cannot pin.
        _check_declared_path("enumerator.argv[0]", argv[0])
        # The gate admits only an isolated Python interpreter running a script. Without "-I"
        # the interpreter puts the script directory first on sys.path and honours the PYTHON* environment
        # variables, so a file beside the enumerator script could shadow a standard library import and steer
        # the backlog verdict the stop and yield guards act on. Every hook launch in hooks.json carries the
        # same "-I" (for example hooks.json:282-287). The rule is an allowlist, so no launcher outside it
        # (env, nice, timeout, a shell, a renamed script, or any other executable) is admitted:
        #   - argv[0] is resolved with os.path.realpath(strict=True); one that cannot be resolved (absent, a
        #     dangling link, a link loop, or unreadable) is a cannot-evaluate and fails closed;
        #   - the RESOLVED basename must fully match ENUM_PYTHON_NAME (python, python3, or python3.N with an
        #     optional one-letter build suffix); the declared spelling is not consulted, so a symlink alias
        #     is judged by its target;
        #   - argv[1] must be exactly "-I";
        #   - argv[2] must be a script path ending in ".py" that does not start with "-", so neither "-c",
        #     nor "-m", nor any further interpreter option can take the place of the script, and it is
        #     pinned to a canonical RELATIVE path inside the repository (see the operand rule below).
        # Disclosed residual: a Python interpreter installed under a name outside the allowlist (pypy3, for
        # example) is rejected, not admitted; a non-Python executable installed under an allowlisted name is
        # admitted on that name, because the gate judges the resolved name and never executes argv[0]; and a
        # script that itself spawns an unisolated child process is not inspected. Resolution is judged at
        # gate time, on the machine running the gate; the hook resolves argv[0] again when it runs it
        # (aiqt_hooks.py:7976).
        try:
            real_argv0 = os.path.realpath(argv[0], strict=True)
        except (OSError, ValueError) as exc:
            _fail("`enumerator.argv[0]` ({!r}) cannot be resolved at gate time ({}); whether it is a Python "
                  "interpreter that needs \"-I\" cannot be evaluated, so it is rejected".format(argv[0], exc))
        if not ENUM_PYTHON_NAME.fullmatch(os.path.basename(real_argv0)):
            _fail("`enumerator.argv[0]` ({!r}) resolves to {!r}, which is not a Python interpreter (python, "
                  "python3, or python3.N); the gate admits only an isolated Python interpreter running a "
                  "script, so a wrapper, a shell, or any other launcher is rejected".format(
                      argv[0], real_argv0))
        if len(argv) < 2 or argv[1] != "-I":
            _fail("`enumerator.argv[0]` ({!r}, resolving to {!r}) is a Python interpreter, so "
                  "`enumerator.argv[1]` must be exactly \"-I\" (isolated mode), got {!r}".format(
                      argv[0], real_argv0, argv[1] if len(argv) > 1 else None))
        if len(argv) < 3 or not argv[2].endswith(".py") or argv[2].startswith("-"):
            _fail("`enumerator.argv[2]` must be a script path ending in \".py\" (not \"-c\", \"-m\", or "
                  "another interpreter option), got {!r}".format(argv[2] if len(argv) > 2 else None))
        # The script, argv[2], is pinned to a canonical RELATIVE path. The hook runs argv with
        # cwd set to the session repository root (aiqt_hooks.py:7976), the git top level of the session
        # (_orch_root, aiqt_hooks.py:7590-7595), so a relative script names <root>/<script> on whatever host
        # runs the hook. The gate does NOT join the script onto any root for the collision checks: the
        # checkout running the gate (a CI runner, a host clone) can sit at a different depth than the
        # session root, and a verdict that depended on that depth would let CI and the host disagree.
        # Instead the script must be:
        #   - relative, with no ".." component, so it cannot leave the root the hook joins it onto;
        #   - canonical, equal to its own posixpath.normpath, so "./tools/x.py", "tools//x.py",
        #     "tools/./x.py", and a trailing "/" are rejected rather than silently normalized;
        #   - when present in the checkout running the gate (ROOT), reached through no symlinked component
        #     and a regular file at its final name. Absence is accepted (a fixture may name a planned
        #     script). This check reads only the checkout CONTENT, never its location, so the same tree
        #     gives the same verdict at any depth.
        script = argv[2]
        if _is_absolute(script):
            _fail("`enumerator.argv[2]` ({!r}) must be a path relative to the repository root, not an absolute "
                  "path; the gate pins the script to a relative path inside the repository".format(script))
        if ".." in script.split("/"):
            _fail("`enumerator.argv[2]` ({!r}) has a \"..\" component; the script must stay inside the "
                  "repository root the hook runs it from (aiqt_hooks.py:7976)".format(script))
        if posixpath.normpath(script) != script:
            _fail("`enumerator.argv[2]` ({!r}) is not in canonical form (its normalized spelling is {!r}); "
                  "write the script path without \"./\", \".\" components, repeated or trailing "
                  "separators".format(script, posixpath.normpath(script)))
        script_parts = script.split("/")
        for comp in script_parts:
            if len(comp.encode("utf-8", "surrogatepass")) > NAME_MAX:
                _fail("`enumerator.argv[2]` has a path component longer than {} bytes (NAME_MAX)".format(
                    NAME_MAX))
        cur = ROOT
        for idx, comp in enumerate(script_parts):
            cur = os.path.join(cur, comp)
            try:
                st = os.lstat(cur)
            except FileNotFoundError:
                break  # absent in this checkout: accepted, nothing further to inspect
            except OSError as exc:
                _fail("`enumerator.argv[2]` ({!r}) cannot be inspected in the checkout at {!r}: {}".format(
                    script, cur, exc))
            if stat.S_ISLNK(st.st_mode):
                _fail("`enumerator.argv[2]` ({!r}) reaches a symlink at {!r}; the script must be a regular "
                      "file reached through no symlinked component".format(script, cur))
            if idx == len(script_parts) - 1 and not stat.S_ISREG(st.st_mode):
                _fail("`enumerator.argv[2]` ({!r}) is present at {!r} but is not a regular file".format(
                    script, cur))
        # Every operand from argv[3] on (the backlog file) must be ABSOLUTE and then joins the
        # state_dir collision list below, whose declared-path, collision, and containment checks depend only
        # on the absolute strings and the filesystem they name, never on where the checkout sits. A relative
        # operand is rejected rather than joined onto a guessed root. An option-shaped operand such as
        # "--out=<path>" is not absolute either, so it is rejected too, which closes the residual an
        # earlier revision disclosed (a path embedded in an option went unchecked).
        for i in range(3, len(argv)):
            label = "enumerator.argv[{}]".format(i)
            if not _is_absolute(argv[i]):
                _fail("`{}` ({!r}) must be an absolute path: the hook runs the enumerator with cwd at the "
                      "session repository root (aiqt_hooks.py:7976), so a relative operand would name a file "
                      "whose location, and whose collision with state_dir, depends on where the checkout "
                      "sits; the gate pins every operand after the script to an absolute path".format(
                          label, argv[i]))
            _check_declared_path(label, argv[i])
            enum_paths.append((label, argv[i]))
        if "timeout" not in spec:
            _fail("`enumerator.timeout` is required: the hook substitutes 60 seconds for a missing value "
                  "(aiqt_hooks.py:7974), which overruns the 10 second hook budget")
        timeout = spec["timeout"]
        # bool is a subclass of int; reject it. NaN and Infinity fail the range comparison.
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) \
                or not (0 < timeout <= ENUMERATOR_TIMEOUT_MAX):
            _fail("`enumerator.timeout` must be a number of seconds in (0, {}], got {!r}".format(
                ENUMERATOR_TIMEOUT_MAX, timeout))
    # `yield_tools`: a list of unique non-empty control-free names, each one the orch_yield_tool matcher
    # in hooks.json actually routes to the hook. hooks.json is read whenever the key is declared, even for
    # an empty roster, so an unreadable hooks.json always fails rather than skipping.
    if "yield_tools" in obj:
        roster = obj["yield_tools"]
        if not isinstance(roster, list):
            _fail("`yield_tools` must be a list, got {}".format(type(roster).__name__))
        matched = _hook_matcher_tools("PreToolUse", "orch_yield_tool", "yield_tools")
        seen = set()
        for i, entry in enumerate(roster):
            if not isinstance(entry, str) or not entry:
                _fail("`yield_tools[{}]` must be a non-empty string, got {!r}".format(i, entry))
            if _has_unsafe_char(entry):
                _fail("`yield_tools[{}]` contains a control or surrogate character".format(i))
            if entry in seen:
                _fail("`yield_tools[{}]` ({!r}) is a duplicate".format(i, entry))
            seen.add(entry)
            if entry not in matched:
                _fail("`yield_tools[{}]` ({!r}) is not in the orch_yield_tool matcher {} in {}; a name "
                      "outside the matcher never reaches the hook, so the roster entry would be a silent "
                      "no-op".format(i, entry, sorted(matched), HOOKS_JSON))
    # `mode`: an object with exactly the key `path`, a declared path (the reader is _orch_mode,
    # aiqt_hooks.py:7763-7776).
    if "mode" in obj:
        mode = obj["mode"]
        if not isinstance(mode, dict):
            _fail("`mode` must be a JSON object, got {}".format(type(mode).__name__))
        extra = set(mode) - MODE_KEYS
        if extra:
            _fail("`mode` has unknown key(s) {}".format(sorted(extra)))
        if "path" not in mode:
            _fail("`mode.path` is required")
        _check_declared_path("mode.path", mode["path"])
    # `attestations` and `mistakes_register`: each a path STRING, not an object (the readers are
    # aiqt_hooks.py:8068, 9638, and 9677). The attestation anchor the hook opens at <path>.anchor
    # (aiqt_hooks.py:9541) is length-checked too, since it is 7 bytes longer than the declared path.
    for key in ("attestations", "mistakes_register"):
        if key in obj:
            _check_declared_path(key, obj[key])
    if "attestations" in obj:
        _check_declared_path("attestations.anchor", obj["attestations"] + ".anchor")
    # `staleness`: an object with exactly the keys in STALENESS_KEYS, each a non-bool finite number in
    # (0, STALENESS_HOURS_MAX]. This mirrors _v_finite_pos (aiqt_hooks.py:8274-8279) but rejects where the
    # hook would silently default to 24 hours. Only a float is passed to math.isfinite: an int is always
    # finite, and math.isfinite raises OverflowError on an int too large for a float (a JSON integer
    # literal of a few hundred digits), so an int is judged by the exact integer range comparison alone.
    if "staleness" in obj:
        staleness = obj["staleness"]
        if not isinstance(staleness, dict):
            _fail("`staleness` must be a JSON object, got {}".format(type(staleness).__name__))
        extra = set(staleness) - STALENESS_KEYS
        if extra:
            _fail("`staleness` has unknown key(s) {}".format(sorted(extra)))
        missing = STALENESS_KEYS - set(staleness)
        if missing:
            _fail("`staleness` must declare both `task_hours` and `external_hours`, missing {}; the hook "
                  "silently substitutes 24 hours for a missing field (aiqt_hooks.py:8297-8301), so a partial "
                  "or empty object would arm a horizon nobody declared".format(sorted(missing)))
        for key in sorted(staleness):
            v = staleness[key]
            if isinstance(v, bool) or not isinstance(v, (int, float)) \
                    or (isinstance(v, float) and not math.isfinite(v)) \
                    or not (0 < v <= STALENESS_HOURS_MAX):
                _fail("`staleness.{}` must be a finite number of hours in (0, {}], got {!r}".format(
                    key, STALENESS_HOURS_MAX, v))
    # `escape`: undeclared, or an object with exactly the key `path` naming a BARE FILE NAME.
    # The hook formula (_orch_escape_active, aiqt_hooks.py:7859-7882) takes anchor = realpath(state_dir)
    # (7859), uses the default name ESCAPE-ALLOW-YIELD when no path is declared (7865-7866, the name at
    # 7556), joins a relative path onto the anchor (7864), rejects a ".." component (7867-7868), requires
    # normpath containment under the anchor (7869-7871), and walks every intermediate component with lstat,
    # rejecting a symlinked one (7872-7882). The gate pins the one shape this project needs: a bare file
    # name, which the hook joins directly onto the anchor, so there is no intermediate component, the
    # symlinked-component class cannot arise, and containment holds by construction. An absolute or
    # multi-component path is rejected outright, with no attempt to replay the containment rule against
    # the unresolved state_dir spelling. The name must be a non-empty string (an empty or non-string value
    # disables the release with no record, 7861-7862), contain no "/" and no Windows shape, not be "." or
    # "..", not be a hook state file name, and be at most STATE_DERIVED_RESERVE bytes, so the state_dir
    # reserve check above also covers <state_dir>/<name>.
    if "escape" in obj:
        esc = obj["escape"]
        if not isinstance(esc, dict):
            _fail("`escape` must be a JSON object, got {}".format(type(esc).__name__))
        extra = set(esc) - ESCAPE_KEYS
        if extra:
            _fail("`escape` has unknown key(s) {}".format(sorted(extra)))
        if "path" not in esc:
            _fail("`escape.path` is required when `escape` is declared; leave `escape` undeclared to use the "
                  "default sentinel name (aiqt_hooks.py:7865-7866)")
        name = esc["path"]
        if not isinstance(name, str) or not name:
            _fail("`escape.path` must be a non-empty string, got {!r}; the hook disables the operator "
                  "release with no record on such a value (aiqt_hooks.py:7861-7862)".format(name))
        if _has_unsafe_char(name):
            _fail("`escape.path` contains a control or surrogate character")
        if _is_windows_shaped(name):
            _fail("`escape.path` ({!r}) is Windows-shaped (a backslash or a drive-letter prefix); the hook "
                  "joins it onto the state_dir anchor with POSIX semantics (aiqt_hooks.py:7864), so it "
                  "would not name the file its spelling suggests".format(name))
        if "/" in name:
            _fail("`escape.path` ({!r}) must be a bare file name with no \"/\": the gate pins the sentinel "
                  "directly inside the state_dir anchor, so an absolute or multi-component path is "
                  "rejected (the hook would join it onto the anchor and walk its intermediate components, "
                  "aiqt_hooks.py:7864-7882)".format(name))
        if name in (".", ".."):
            _fail("`escape.path` ({!r}) must be a bare file name, not \".\" or \"..\"; it would name the "
                  "anchor directory or leave it, never the regular-file sentinel the hook requires".format(name))
        if len(name.encode("utf-8", "surrogatepass")) > STATE_DERIVED_RESERVE:
            _fail("`escape.path` is longer than {} bytes, the room the state_dir reserve keeps for a file "
                  "name under it".format(STATE_DERIVED_RESERVE))
        # The sentinel must not share a name with a file the hooks themselves write or read in state_dir
        # (HOOK_STATE_FILES above, each cited to its site): the release would collide with machine state
        # rather than name an operator-owned file.
        if name in HOOK_STATE_FILES:
            _fail("`escape.path` ({!r}) is the name of a file the hooks write in state_dir; the operator "
                  "release sentinel must not collide with machine state".format(name))
    # Cross-field REQUIREMENT: a declared `record` or `lease` must be accompanied
    # by an explicit `state_dir`. When `state_dir` is OMITTED the hooks do NOT stop using a state dir --
    # _state_dir_from_registry (aiqt_hooks.py:7638-7651) falls back to
    # ${XDG_STATE_HOME:-~/.local/state}/aiqt-guardrails/orch/<repo-key>/, and orch_resume_audit still opens
    # `<state_dir>/resume-barrier.json` with mode "w" there (aiqt_hooks.py:9783-9785). A record/lease path
    # landing inside that DEFAULT dir is clobbered exactly as in a declared-state_dir collision, but
    # the collision check below runs only `if "state_dir" in obj`, so the default-dir sibling slips through
    # (reproduced: gate exit 0, then the hook clobbers the declared record). Requiring
    # `state_dir` alongside record/lease closes the whole class at gate time: the location is then validated
    # and collision-checked, and a gate-passing armed registry never falls back to the XDG default.
    # `dispatch_tools` carries tool NAMES, not a path, so it cannot collide and does not trigger this.
    if ("record" in obj or "lease" in obj) and "state_dir" not in obj:
        _fail("`record`/`lease` is declared without `state_dir`: the hooks then fall back to an XDG-default "
              "state directory ($XDG_STATE_HOME/aiqt-guardrails/orch/<repo-key>, aiqt_hooks.py:7638-7651) "
              "that this gate never sees, and orch_resume_audit's unconditional `<state_dir>/"
              "resume-barrier.json` write clobbers any record/lease path landing inside it; declare "
              "`state_dir` explicitly so the machine-state location is validated and collision-checked")
    # The same requirement for the stage-2 keys that drive machine state under state_dir or name a path
    # the collision check below must see (STATE_DIR_REQUIRED_BY). Without an explicit state_dir the
    # enumerator checkpoint, the yield denial counter, and the escape anchor would all bind to the unseen
    # XDG-default directory, and a declared mode, attestation, or mistakes-register path would escape the
    # collision check.
    for key in STATE_DIR_REQUIRED_BY:
        if key in obj and "state_dir" not in obj:
            _fail("`{}` is declared without `state_dir`: the machine state it drives, or the collision "
                  "check its path needs, would bind to an XDG-default state directory this gate never "
                  "sees; declare `state_dir` explicitly".format(key))
    # Cross-field collision: a declared record/lease path that lands ON or INSIDE
    # `state_dir` collides with the machine-state files the hooks write there. orch_resume_audit opens
    # `<state_dir>/resume-barrier.json` with mode "w" UNCONDITIONALLY (aiqt_hooks.py:9775, 9783-9785), so
    # a record/lease path pointing into state_dir would be clobbered by that hook write (destructive, no
    # lease needed). The per-key checks above validate each path in isolation and cannot see this; this
    # runs ONLY when `state_dir` is declared and valid (execution reaches here only past its
    # _check_declared_path). `companion_stores` is intentionally NOT checked against state_dir: a state_dir
    # legitimately MAY sit under a companion store; the hazard is a record/lease FILE landing on a
    # machine-state file, not the state directory living under an exempt store.
    if "state_dir" in obj:
        # Robust against path-spelling ALIASES. An earlier normpath+startswith test was
        # bypassed by aliases the two spellings do not share: state_dir "/" + record "/x.json" (norm_state
        # "/" + os.sep = "//", which "/x.json" does not start with), and any leading double-slash spelling
        # (POSIX normpath preserves a leading "//"). _norm_pathspell canonicalizes BOTH sides and collapses
        # that leading "//", and os.path.commonpath then decides containment component-wise, so a genuine
        # SIBLING (e.g. /opt/x/orch-state-extra vs state_dir /opt/x/orch-state -> commonpath /opt/x) is
        # still accepted while ON-or-INSIDE is rejected.
        norm_state_dir = _norm_pathspell(obj["state_dir"])
        # ADDITIONALLY compare RESOLVED paths: an EXISTING symlink alias makes two
        # different spellings resolve to the same file, which the lexical check cannot see. os.path.realpath
        # resolves existing symlink components and leaves a non-existent tail intact, so a record/lease path
        # that resolves onto or into the resolved state_dir is caught even when the spellings differ (for
        # example state_dir "/dev/shm" + record "/run/shm/resume-barrier.json" where /run/shm -> /dev/shm
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
        # Stage 2 adds the declared files the hooks read or write outside state_dir to the same list: the
        # mode record, the attestation register and its <path>.anchor authority (aiqt_hooks.py:9541), the
        # mistakes register, and every enumerator operand from argv[3] on (the backlog file), each one
        # absolute. The script (argv[2]) is relative and pinned inside the repository, so it is not listed.
        # All are validated strings by this point.
        if isinstance(obj.get("mode"), dict) and "path" in obj["mode"]:
            declared.append(("mode.path", obj["mode"]["path"]))
        if "attestations" in obj:
            declared.append(("attestations", obj["attestations"]))
            declared.append(("attestations.anchor", obj["attestations"] + ".anchor"))
        if "mistakes_register" in obj:
            declared.append(("mistakes_register", obj["mistakes_register"]))
        declared.extend(enum_paths)
        for label, value in declared:
            if _contains_or_equal(_norm_pathspell(value), norm_state_dir):
                _fail("`{}` ({!r}) is on or inside `state_dir` ({!r}); a declared path on or under "
                      "state_dir collides with the machine-state files the hooks write there (e.g. "
                      "resume-barrier.json), so a hook write would clobber the declared file".format(
                          label, value, obj["state_dir"]))
            real_value = os.path.realpath(value)
            if _contains_or_equal(real_value, real_state_dir):
                _fail("`{}` ({!r}) RESOLVES onto or inside `state_dir` ({!r}) through an existing symlink "
                      "(the declared path resolves to {!r}, state_dir to {!r}); a hook write to a "
                      "machine-state file there (e.g. resume-barrier.json) would clobber the declared "
                      "file".format(label, value, obj["state_dir"], real_value, real_state_dir))
        # --- THE BOUND: accepted-input soundness is bounded to commit-time validation ---------------------
        # This gate performs COMMIT-TIME validation only. What it establishes is: structural shape + concrete
        # hazards (surrogate/control character, NAME_MAX/PATH_MAX length, derived-path reserve, record/lease-
        # vs-state_dir collision) + BEST-EFFORT resolved-path containment (above) + BEST-EFFORT state_dir
        # gate-time directory-type. Its accepted-input soundness is BOUNDED to what commit-time validation can
        # establish; the maintainer directed this bound. The residuals below are IRREDUCIBLE
        # (no commit-time string or stat check can close them). They do NOT all resolve to a fail-safe denial
        # -- an earlier overstatement held that each was "a denial or a caught
        # collision at runtime, never a bypass". They split by runtime outcome:
        #   FAIL-SAFE DENIALS -- a denial or a caught collision at runtime, never a bypass:
        #   (b) Runtime directory-usability of a NOT-YET-CREATED state_dir: an absent state_dir later created
        #       as a regular file, or living on a read-only or different filesystem. The best-effort lstat
        #       above classifies only what exists at gate time; genuine absence is accepted (it cannot be
        #       verified). At runtime an unusable state_dir drives write_scope_guard._load_write_scope to a
        #       persistent covered-write DENIAL (fail-safe), operator-fixable.
        #   (c) A FIFO or other special file at a declared record/lease/state path: it would block
        #       the HOOK's own read at read time (see the FIFO disclosure at the presence check above, in
        #       validate()). git cannot check out a FIFO, so the only exposure is an exotic hand-crafted local
        #       run, never a checked-out tree. The files the gate itself opens, the registry and hooks.json,
        #       are no longer part of this residual: _read_regular_text refuses a non-regular file.
        #   (e) The enumerator script is inspected in the checkout running the gate (ROOT). The hook runs it
        #       from the session root on the host, a different tree whose content (a symlink planted there
        #       after checkout, for example) the gate cannot see; the pinned relative, canonical, ".."-free
        #       shape is what keeps the script inside that root.
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
        # The Windows-spelling parity residual an earlier revision disclosed here is closed: every declared
        # path, every enumerator argv operand, and the escape path reject a backslash or a drive-letter
        # prefix (_is_windows_shaped), so no Windows-shaped spelling reaches the collision checks above.
        # write_scope_guard and the recorder/audit hooks are DEFENCE IN DEPTH, not a security boundary, so a
        # fail-safe denial there is degraded-but-safe, not exploitable. The COMMITTED registry is verified
        # safe by this gate plus its tests, and human review via change-carries-check is the backstop for
        # future edits.
    # `dispatch_tools`, if present: a list of unique non-empty control-free names, each one the
    # orch_dispatch_ledger PostToolUse matcher in hooks.json ("Bash|TaskOutput", hooks.json:276-290) actually
    # routes to the hook, AND none of them a name in DISPATCH_TOOLS_FORBIDDEN. The hook compares the tool name
    # against this list only after that matcher fired (aiqt_hooks.py:9276-9280), so a name outside the
    # matcher would be a silent no-op entry. Inside the matcher, "TaskOutput" is inert (the hook routes it to
    # its completion branch at aiqt_hooks.py:9264 before reading the list at 9277) and "Bash" is harmful
    # (aiqt_hooks.py:9279-9280 would then record every foreground Bash call as a dispatch), so both are
    # rejected. Under the current matcher, then, no non-empty value is valid: only the empty
    # list passes, until the matcher gains a tool name the hook can use. hooks.json is read whenever the key
    # is declared, even for an empty list, so an unreadable hooks.json always fails rather than skipping.
    if "dispatch_tools" in obj:
        tools = obj["dispatch_tools"]
        if not isinstance(tools, list):
            _fail("`dispatch_tools` must be a list, got {}".format(type(tools).__name__))
        matched = _hook_matcher_tools("PostToolUse", "orch_dispatch_ledger", "dispatch_tools")
        seen = set()
        for i, entry in enumerate(tools):
            if not isinstance(entry, str) or not entry:
                _fail("`dispatch_tools[{}]` must be a non-empty string, got {!r}".format(i, entry))
            if _has_unsafe_char(entry):
                _fail("`dispatch_tools[{}]` contains a control or surrogate character".format(i))
            if entry in seen:
                _fail("`dispatch_tools[{}]` ({!r}) is a duplicate".format(i, entry))
            seen.add(entry)
            if entry in DISPATCH_TOOLS_FORBIDDEN:
                _fail("`dispatch_tools[{}]` ({!r}) is rejected: {}".format(
                    i, entry, DISPATCH_TOOLS_FORBIDDEN[entry]))
            if entry not in matched:
                _fail("`dispatch_tools[{}]` ({!r}) is not in the orch_dispatch_ledger matcher {} in {}; a "
                      "name outside the matcher never reaches the hook, so the entry would be a silent "
                      "no-op".format(i, entry, sorted(matched), HOOKS_JSON))
    # --- required parameters of a declared control ----------------------------------------------------
    # A key that PARAMETERIZES a declared control, rather than arming one, is required whenever that control
    # is declared: its absence leaves the control armed but silently substitutes a hook default. These
    # checks run LAST, after every targeted check, so a fixture that omits a parameter is still rejected by
    # the rule it targets, never only by these.
    #   lease.max_age_hours: see LEASE_KEYS above (aiqt_hooks.py:7792-7798, 9395-9401).
    #   staleness: see STALENESS_REQUIRED_BY above (aiqt_hooks.py:8297-8301).
    # Every key the gate still accepts as optional is classified in OPTIONAL_KEY_CLASSIFICATION in
    # tools/test-orchestration-registry.py, which derives the optional set from this gate.
    if isinstance(obj.get("lease"), dict) and "max_age_hours" not in obj["lease"]:
        _fail("`lease.max_age_hours` is required: without it the hook treats a present, non-empty lease as "
              "fresh forever (aiqt_hooks.py:7792-7798) and the resume audit never reports it stale "
              "(aiqt_hooks.py:9395-9401), so a lease left by a dead orchestrator keeps scope live; the "
              "committed registry declares 24")
    for key in STALENESS_REQUIRED_BY:
        if key in obj and "staleness" not in obj:
            _fail("`{}` is declared without `staleness`: the hook then applies 24 hour task and external "
                  "horizons nobody declared (aiqt_hooks.py:8297-8301); declare both horizons "
                  "explicitly".format(key))
    summary = "version 1"
    if "companion_stores" in obj:
        summary += ", {} companion store(s)".format(len(obj["companion_stores"]))
    arming = [k for k in ("record", "lease", "state_dir", "dispatch_tools", "enumerator", "yield_tools",
                          "mode", "attestations", "mistakes_register", "staleness", "escape") if k in obj]
    summary += ", arming keys: {}".format(", ".join(arming)) if arming else ", no arming keys"
    print("check-orchestration-registry: OK ({}: {})".format(path, summary))


def main(argv):
    validate(argv[1] if len(argv) > 1 else DEFAULT_REGISTRY)


if __name__ == "__main__":
    main(sys.argv)
