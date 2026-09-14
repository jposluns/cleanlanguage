#!/usr/bin/env python3
"""Validate the structural integrity of `.aiqt/orchestration.json`.

The AIQT orchestration hooks read `.aiqt/orchestration.json` (or the machine-local
`.aiqt/orchestration.local.json`) and classify it `ok` only when it is a JSON object
whose `version` is the integer 1. A malformed or non-version-1 committed registry
classifies `bad`: the write-scope companion exemption then empties, so cross-repository
writes deny (which is fail-safe), but the scope-gated stop, yield, and dispatch guards
fail OPEN, with a warning, once a `lease` or `mode` arms them. This gate rejects a
structurally invalid committed registry before it lands, so a corrupt registry cannot
reach a session that arms those guards.

It validates STRUCTURE only. Whether a `companion_stores` entry resolves to a live git
top level is a runtime property the hook checks fail-safe (a non-resolving entry is
dropped, so writes to it deny); the path need not exist on the machine running this gate.

Usage: check-orchestration-registry.py [registry-path]
The path defaults to `<repo-root>/.aiqt/orchestration.json`. Exit 0 when the registry
is absent (it is optional) or valid; exit 1 on a structural defect.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REGISTRY = os.path.join(ROOT, ".aiqt", "orchestration.json")


def _fail(msg):
    print("check-orchestration-registry: FAIL: {}".format(msg), file=sys.stderr)
    sys.exit(1)


def validate(path):
    if not os.path.exists(path):
        print("check-orchestration-registry: no {} (optional); nothing to validate.".format(path))
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        _fail("cannot read {}: {}".format(path, exc))
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        _fail("{} is not valid JSON: {}".format(path, exc))
    if not isinstance(obj, dict):
        _fail("{} top level must be a JSON object, got {}".format(path, type(obj).__name__))
    # `version` must be exactly the integer 1. bool is a subclass of int, so exclude it explicitly;
    # this mirrors the hook's `type(version) is int and version == 1` classification.
    version = obj.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        _fail("`version` must be the integer 1, got {!r}".format(version))
    # `companion_stores`, if present, must be a list of non-empty absolute path strings with no
    # control characters. The hook drops a malformed entry fail-safe at runtime; this catches it at
    # author time so the intended exemption is not silently lost.
    if "companion_stores" in obj:
        stores = obj["companion_stores"]
        if not isinstance(stores, list):
            _fail("`companion_stores` must be a list, got {}".format(type(stores).__name__))
        for i, entry in enumerate(stores):
            if not isinstance(entry, str) or not entry:
                _fail("`companion_stores[{}]` must be a non-empty string, got {!r}".format(i, entry))
            if not os.path.isabs(entry):
                _fail("`companion_stores[{}]` must be an absolute path, got {!r}".format(i, entry))
            if any(ord(ch) < 0x20 for ch in entry):
                _fail("`companion_stores[{}]` contains a control character".format(i))
    summary = "version 1"
    if "companion_stores" in obj:
        summary += ", {} companion store(s)".format(len(obj["companion_stores"]))
    print("check-orchestration-registry: OK ({}: {})".format(path, summary))


def main(argv):
    validate(argv[1] if len(argv) > 1 else DEFAULT_REGISTRY)


if __name__ == "__main__":
    main(sys.argv)
