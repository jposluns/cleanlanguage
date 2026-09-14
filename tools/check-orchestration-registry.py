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
`_is_absolute`) with no control character (below 0x20 or 0x7f). Whether an entry resolves to
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
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REGISTRY = os.path.join(ROOT, ".aiqt", "orchestration.json")


def _fail(msg):
    print("check-orchestration-registry: FAIL: {}".format(msg), file=sys.stderr)
    sys.exit(1)


def _is_absolute(path):
    # OS-agnostic, matching the hook's _is_absolute: a POSIX absolute path OR a Windows path
    # carrying both a drive and a root. This keeps the gate from falsely rejecting an entry the
    # hook would accept when the gate runs on a different OS than the committer.
    return pathlib.PurePosixPath(path).is_absolute() or pathlib.PureWindowsPath(path).is_absolute()


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
    except ValueError as exc:
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
            if not isinstance(entry, str) or not entry:
                _fail("`companion_stores[{}]` must be a non-empty string, got {!r}".format(i, entry))
            if not _is_absolute(entry):
                _fail("`companion_stores[{}]` must be an absolute path, got {!r}".format(i, entry))
            if any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in entry):
                _fail("`companion_stores[{}]` contains a control character".format(i))
    summary = "version 1"
    if "companion_stores" in obj:
        summary += ", {} companion store(s)".format(len(obj["companion_stores"]))
    print("check-orchestration-registry: OK ({}: {})".format(path, summary))


def main(argv):
    validate(argv[1] if len(argv) > 1 else DEFAULT_REGISTRY)


if __name__ == "__main__":
    main(sys.argv)
