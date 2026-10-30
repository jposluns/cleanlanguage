#!/usr/bin/env python3
"""Verify the integrity of the vendored AIQT Guardrails pack.

The repository vendors part of the AIQT Guardrails pack: the rule corpus, the rendered active rules,
the hooks plugin, and provenance metadata. This gate checks that the vendored files on disk agree with
the vendored manifest, and that the manifest agrees with the adopter-written pin. It reads the vendored
file set and every expected hash from `.aiqt/pin.toml` and from the manifest that pin names (normally
`.aiqt/manifest.toml`); it hard-codes no rule name and no hash, so it does not depend on which rules the
project adopts. The one file list it holds is the required set (REQUIRED_FILES, REQUIRED_META,
REQUIRED_WHOLE and REQUIRED_ACTIVE_TREES below): the vendored files and roots this adopter needs, fixed
in the gate rather than read from the pin, so a pin that drops a required file together with every entry
naming it still fails.

The vendored file set is every git-tracked file under the pin `[vendored] paths`, read from the index
with `git ls-files` (GIT_* environment scrubbed, literal pathspecs). Each check names the path it fails on:

  check 1  `[source] source-commit` is 40 lowercase hex characters, `[vendor] source-commit` equals it,
           `[vendored] paths` is a non-empty list of distinct relative paths, each with at least one
           tracked file, and each `[[vendor.relocated]]` entry maps a distinct tracked vendored file to a
           distinct upstream path that is not itself a tracked vendored file. The pin text carries no
           draft marker: the word DRAFT or PLACEHOLDER in capitals, anywhere in the file, comments
           included, fails with its line number, so a draft pin cannot land.
  check 2  every tracked file under the vendored paths, except `.aiqt/release/root.txt` and the manifest
           itself, is a regular file with a manifest `[[sources]]` entry (at its upstream path, for a
           relocated file) whose `bytes` and `sha256` equal the file.
  check 3  every manifest `[[sources]]` entry under a path the pin declares adopted whole
           (`[vendor] whole`) is a tracked regular file on disk; and the required set holds: `[vendor]
           whole` names every REQUIRED_WHOLE root, every REQUIRED_META file is tracked, and every
           REQUIRED_FILES file is a tracked regular file on disk, vendored from its declared upstream
           path (the pin relocation must agree), with a manifest `[[sources]]` entry at that upstream
           path and a `[[vendor.files]]` row.
  check 4  every tracked file under the active rule trees (`[active-rules] trees`) equals its manifest
           `[[artifacts]]` sha256; their count equals `[active-rules] active`; and the corpus rules (the
           `.md` files under `[active-rules] corpus`, identified by their `corpus-id` front matter) absent
           from the active trees are exactly the `[active-rules] excluded-ids` list, which has
           `[active-rules] excluded` members; `[active-rules] trees` names every
           REQUIRED_ACTIVE_TREES tree, and each holds a tracked file.
  check 5  the manifest header `tree-sha256` equals `[integrity] tree-sha256`, and
           `.aiqt/release/root.txt` holds exactly `[integrity] root`.
  check 6  the `[vendor]` block is well formed, each of its `[[vendor.files]]` entries names a tracked
           vendored file whose manifest `[[sources]]` entry carries the same `bytes` and `sha256`, at
           least one vendored file is relocated from the upstream `LICENSE`, and every such file hashes to
           `[vendor] license-sha256`.
  check 7  optional, with `--upstream DIR`: every tracked vendored file is re-derived from
           `git -C DIR cat-file blob SHA:path` (SHA is the pinned source-commit, and path is the upstream
           path for a relocated file) and compared byte for byte, and LICENSE at SHA hashes to
           `[vendor] license-sha256`.

Relocation. The pack keeps some files at its own root, such as `LICENSE` and `NOTICE`, that the adopter
vendors under another path, such as `.aiqt/LICENSE`. A `[[vendor.relocated]]` entry in the pin names the
local `path` and the `upstream` path; the gate then looks the file up in the manifest, and re-derives it in
check 7, at the upstream path. Every other vendored file keeps its upstream path. An absent list means no
file is relocated.

Fails closed. An unreadable, unparseable, missing, or non-regular input, a malformed pin or manifest
field, an empty file list, a manifest without its generated header, or a git enumeration that cannot run
is a failure that names the path; a cannot-evaluate result is never a pass. Every input is opened
O_NONBLOCK and O_NOFOLLOW and judged by fstat on the opened descriptor, so a FIFO, a device, a directory,
or a symlink at an input path fails at once rather than blocking or reading as empty. The script
re-executes itself under `python3 -I` when it was not launched isolated, so a file written beside it
cannot shadow a standard-library import. It needs Python 3.11 or later (tomllib).

Disclosed residual. This gate proves internal consistency only: the files against a manifest that is
itself vendored, and the manifest against a pin that the adopter writes. An actor who rewrites a file, its
manifest entry, and the pin together passes checks 1 to 6. What an adopter-written pin can still hide
from checks 1 to 6, given the required set: a file under a required whole root deleted together with its
manifest `[[sources]]` entry (the edited manifest differs from the pack, which check 7 catches); a
rendered active rule deleted together with a matching `[active-rules] excluded-ids` entry and count; a
vendored file outside the required set added by a later re-vendor and not yet added to it, deleted with
its pin entries; and any change to the required set itself, which is a change to this gate, reviewed as
code. The required set covers every `[vendored] paths` entry of this adopter that is not under a required
whole root or a required active tree. Only check 7 (run locally against the pack
checkout) or an upstream release signature closes that, and CI cannot reach the pack checkout, so check 7
is a QA-worker and pre-merge step until CI egress to the pack repository is granted. Check 7 in turn
trusts the pack checkout it is pointed at, and git there reads its own on-disk configuration. Check 4
counts and hashes the active set but does not re-derive applicability from applies.toml and the profile:
the exclusion list is adopter-declared, and a wrong exclusion is a review finding, not a gate finding.
A relocation is adopter-declared in the same way: one that points a local file at the wrong upstream path
is caught only where the two files differ in content. The gate judges the git index and the working tree at the time it runs: an untracked file under a
vendored path (for example an extra untracked rule a local session would still load) is outside the
tracked set and is not judged, a file changed between its read and the verdict is not re-read, and the
O_NOFOLLOW refusal covers the final path component only, not a symlinked parent directory. Git itself
still reads its on-disk configuration (repository, global, and system) while it enumerates the index.

Usage: check-aiqt-vendor.py [--root DIR] [--upstream DIR]
Exit 0 when every requested check passes; exit 1 on any failure, cannot-evaluate included; exit 2 on a
usage error.
"""
import os
import sys

if not sys.flags.isolated:
    # Isolated mode keeps this script directory and the environment off the import path, so a file
    # written beside the script cannot shadow a standard-library module (SECI config rule).
    try:
        os.execv(sys.executable, [sys.executable, "-I", os.path.abspath(__file__)] + sys.argv[1:])
    except OSError as exc:
        print("check-aiqt-vendor: FAIL: cannot re-execute under python3 -I: {}".format(exc),
              file=sys.stderr)
        sys.exit(1)

import argparse
import hashlib
import re
import stat
import subprocess

try:
    import tomllib
except ImportError:
    print("check-aiqt-vendor: FAIL: tomllib is unavailable; Python 3.11 or later is required",
          file=sys.stderr)
    sys.exit(1)

PROG = "check-aiqt-vendor"
DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIN_REL = ".aiqt/pin.toml"
ROOT_TXT_REL = ".aiqt/release/root.txt"
MANIFEST_HEADER = "# generated by tools/gen_manifest.py; do not hand-edit"
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
CORPUS_ID = re.compile(r"[a-z0-9][a-z0-9_-]*")
GIT_TIMEOUT = 120
OPEN_FLAGS = (os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NOCTTY", 0)
              | getattr(os, "O_CLOEXEC", 0))
# Regular-file index modes. A symlink (120000) or a gitlink (160000) under a vendored path is refused.
REGULAR_MODES = ("100644", "100755")
# The required set: what this adopter vendors outside the whole roots, each file with the upstream path it
# is vendored from (its own path unless the pack keeps it at its root). Fixed here, never read from the pin.
REQUIRED_FILES = {
    ".aiqt/LICENSE": "LICENSE",
    ".aiqt/NOTICE": "NOTICE",
    ".aiqt/core/applies.toml": ".aiqt/core/applies.toml",
    ".aiqt/core/applicability.toml": ".aiqt/core/applicability.toml",
    ".aiqt/core/ownership.toml": ".aiqt/core/ownership.toml",
    ".aiqt/core/order.toml": ".aiqt/core/order.toml",
}
# Provenance files the manifest does not list: the manifest itself and the release root.
REQUIRED_META = (".aiqt/manifest.toml", ROOT_TXT_REL)
# The roots this adopter vendors whole, and the trees of rendered active rules.
REQUIRED_WHOLE = (".aiqt/core/rules", "plugin/aiqt-guardrails-hooks")
REQUIRED_ACTIVE_TREES = (".claude/rules/aiqt", ".claude/rules/security")
# A draft pin: the markers a draft carries until it is finalized (case-sensitive words).
DRAFT_MARKER = re.compile(r"(?<![A-Za-z0-9_])(DRAFT|PLACEHOLDER)(?![A-Za-z0-9_])")


class InputError(Exception):
    """An input the gate needs cannot be read or parsed; the run cannot be evaluated."""


class Report:
    def __init__(self):
        self.failures = []

    def fail(self, check, path, message):
        self.failures.append((check, path, message))


def _valid_rel(value):
    # A repository-relative POSIX path: non-empty, not absolute, no backslash, no control character, and
    # no empty, "." or ".." component, so it cannot name a file outside the root or alias another entry.
    if not isinstance(value, str) or not value:
        return False
    if value.startswith("/") or "\\" in value:
        return False
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        return False
    return all(comp not in ("", ".", "..") for comp in value.split("/"))


def _under(path, prefix):
    return path == prefix or path.startswith(prefix + "/")


def read_regular(abspath):
    """Return the bytes of a regular file, or raise InputError naming the path."""
    try:
        fd = os.open(abspath, OPEN_FLAGS)
    except OSError as exc:
        raise InputError("{}: cannot open: {}".format(abspath, exc))
    chunks = []
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise InputError("{}: not a regular file (file mode {:o}); refused rather than read".format(
                abspath, stat.S_IFMT(st.st_mode)))
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
    except OSError as exc:
        raise InputError("{}: cannot read: {}".format(abspath, exc))
    finally:
        os.close(fd)
    return b"".join(chunks)


def read_toml(abspath, label):
    raw = read_regular(abspath)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputError("{} ({}): not valid UTF-8: {}".format(label, abspath, exc))
    try:
        return text, tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise InputError("{} ({}): not valid TOML: {}".format(label, abspath, exc))


def _git_env():
    # Scrub every ambient GIT_* variable so an inherited environment cannot redirect git to another
    # repository, index, or work tree.
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def run_git(repo, args, what):
    cmd = ["git", "--literal-pathspecs", "-C", repo] + args
    try:
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, env=_git_env(),
                              timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        raise InputError("{}: cannot run git: {}".format(what, exc))
    if proc.returncode != 0:
        raise InputError("{}: git {} exited {}: {}".format(
            what, " ".join(args[:2]), proc.returncode,
            proc.stderr.decode("utf-8", "replace").strip()))
    return proc.stdout


def tracked_files(root, prefix):
    """Map each tracked path under prefix to its index mode."""
    out = run_git(root, ["ls-files", "-s", "-z", "--", prefix], "enumerate tracked files under " + prefix)
    entries = {}
    for record in out.split(b"\0"):
        if not record:
            continue
        try:
            meta, path_b = record.split(b"\t", 1)
            mode, _obj, stage = meta.decode("ascii").split(" ")
            path = path_b.decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            raise InputError("git ls-files under {}: unparseable index record {!r}".format(prefix, record))
        if stage != "0":
            raise InputError("{}: unmerged index entry (stage {})".format(path, stage))
        entries[path] = mode
    return entries


def _get(table, key, kind):
    value = table.get(key) if isinstance(table, dict) else None
    if kind == "str":
        return value if isinstance(value, str) and value else None
    if kind == "int":
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    if kind == "relpaths":
        if not isinstance(value, list) or not value:
            return None
        if not all(_valid_rel(v) for v in value) or len(set(value)) != len(value):
            return None
        return value
    raise ValueError(kind)


def load_manifest(root, rel):
    abspath = os.path.join(root, rel)
    text, data = read_toml(abspath, "the manifest")
    first = text.split("\n", 1)[0]
    if not first.startswith(MANIFEST_HEADER):
        raise InputError("{}: first line is not the generated header {!r}; a manifest without it is "
                         "refused".format(rel, MANIFEST_HEADER))
    if data.get("format-version") != 1 or isinstance(data.get("format-version"), bool):
        raise InputError("{}: format-version is not the integer 1".format(rel))
    tree = data.get("tree-sha256")
    if not isinstance(tree, str) or not HEX64.fullmatch(tree):
        raise InputError("{}: header tree-sha256 is not 64 lowercase hex characters".format(rel))
    sources = {}
    raw_sources = data.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise InputError("{}: no [[sources]] entries".format(rel))
    for i, ent in enumerate(raw_sources):
        path = ent.get("path") if isinstance(ent, dict) else None
        size = _get(ent, "bytes", "int")
        digest = ent.get("sha256") if isinstance(ent, dict) else None
        if not _valid_rel(path) or size is None or not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise InputError("{}: [[sources]] entry {} is malformed (path, bytes, sha256)".format(rel, i + 1))
        if path in sources:
            raise InputError("{}: duplicate [[sources]] entry for {}".format(rel, path))
        sources[path] = (size, digest)
    artifacts = {}
    raw_artifacts = data.get("artifacts", [])
    if not isinstance(raw_artifacts, list):
        raise InputError("{}: [[artifacts]] is not an array of tables".format(rel))
    for i, ent in enumerate(raw_artifacts):
        path = ent.get("path") if isinstance(ent, dict) else None
        digest = ent.get("sha256") if isinstance(ent, dict) else None
        if not _valid_rel(path) or not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise InputError("{}: [[artifacts]] entry {} is malformed (path, sha256)".format(rel, i + 1))
        if path in artifacts:
            raise InputError("{}: duplicate [[artifacts]] entry for {}".format(rel, path))
        artifacts[path] = digest
    return tree, sources, artifacts


def corpus_id(data, path):
    """Return the corpus-id in the front matter of a rule file, or raise InputError."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise InputError("{}: not valid UTF-8".format(path))
    if not text.startswith("---\n"):
        raise InputError("{}: no front matter".format(path))
    end = text.find("\n---\n", 3)
    if end < 0:
        raise InputError("{}: unterminated front matter".format(path))
    ids = [line[len("corpus-id:"):].strip() for line in text[4:end].split("\n")
           if line.startswith("corpus-id:")]
    if len(ids) != 1 or not CORPUS_ID.fullmatch(ids[0]):
        raise InputError("{}: front matter does not carry exactly one well-formed corpus-id".format(path))
    return ids[0]


class Gate:
    def __init__(self, root, upstream):
        self.root = root
        self.upstream = upstream
        self.report = Report()
        self.cache = {}
        self.relocated = {}

    def upstream_path(self, rel):
        # The path the pack and its manifest use for a vendored file: its own path unless relocated.
        return self.relocated.get(rel, rel)

    def fail(self, check, path, message):
        self.report.fail(check, path, message)

    def file_bytes(self, rel):
        if rel not in self.cache:
            self.cache[rel] = read_regular(os.path.join(self.root, rel))
        return self.cache[rel]

    # Check 1.
    def check_source_and_paths(self, pin):
        ok = True
        source = pin.get("source")
        commit = _get(source, "source-commit", "str")
        if commit is None or not HEX40.fullmatch(commit):
            self.fail(1, PIN_REL, "[source] source-commit is missing or not 40 lowercase hex characters")
            ok = False
        vendor_commit = _get(pin.get("vendor"), "source-commit", "str")
        if vendor_commit is None or vendor_commit != commit:
            self.fail(1, PIN_REL, "[vendor] source-commit is missing or differs from [source] source-commit")
            ok = False
        paths = _get(pin.get("vendored"), "paths", "relpaths")
        if paths is None:
            self.fail(1, PIN_REL, "[vendored] paths is missing, empty, or holds an invalid or duplicate path")
            return None, None
        tracked = {}
        for prefix in paths:
            entries = tracked_files(self.root, prefix)
            if not entries:
                self.fail(1, prefix, "declared vendored path has no tracked file")
                ok = False
            tracked.update(entries)
        return (commit if ok else None), tracked

    # Check 1, the pin is final.
    def check_pin_final(self, text):
        for lineno, line in enumerate(text.split("\n"), 1):
            for m in DRAFT_MARKER.finditer(line):
                self.fail(1, "{}:{}".format(PIN_REL, lineno), "the pin carries the draft marker {}; a pin with "
                          "a DRAFT marker or a PLACEHOLDER value is not final and cannot land".format(m.group(1)))

    # Check 1, the relocation map.
    def check_relocations(self, pin, tracked):
        """Return {local path: upstream path} from [[vendor.relocated]], failing check 1 on an entry that is
        malformed, duplicated, untracked, or ambiguous. An entry that fails is left out of the map, so its file
        then also fails check 2 for want of a manifest entry at its local path."""
        vendor = pin.get("vendor")
        rows = vendor.get("relocated", []) if isinstance(vendor, dict) else []
        mapping = {}
        if not isinstance(rows, list):
            self.fail(1, PIN_REL, "[vendor] relocated is not an array of tables")
            return mapping
        targets = set()
        for i, ent in enumerate(rows):
            path = ent.get("path") if isinstance(ent, dict) else None
            up = ent.get("upstream") if isinstance(ent, dict) else None
            if not _valid_rel(path) or not _valid_rel(up) or path == up:
                self.fail(1, PIN_REL, "[[vendor.relocated]] entry {} is malformed (path, upstream, distinct "
                          "relative paths)".format(i + 1))
                continue
            if path in mapping:
                self.fail(1, path, "listed twice in [[vendor.relocated]]")
                continue
            if up in targets:
                self.fail(1, up, "named as the upstream path of two [[vendor.relocated]] entries")
                continue
            if path not in tracked:
                self.fail(1, path, "[[vendor.relocated]] names a path that is not a tracked vendored file")
                continue
            if up in tracked:
                self.fail(1, up, "[[vendor.relocated]] upstream path is itself a tracked vendored file, so two "
                          "files would verify against one manifest entry")
                continue
            mapping[path] = up
            targets.add(up)
        return mapping

    # Check 2.
    def check_files_match_manifest(self, tracked, sources, manifest_rel):
        for path in sorted(tracked):
            if path in (ROOT_TXT_REL, manifest_rel):
                continue
            if tracked[path] not in REGULAR_MODES:
                self.fail(2, path, "tracked with index mode {}, not a regular file".format(tracked[path]))
                continue
            try:
                data = self.file_bytes(path)
            except InputError as exc:
                self.fail(2, path, str(exc))
                continue
            up = self.upstream_path(path)
            entry = sources.get(up)
            if entry is None:
                self.fail(2, path, "no manifest [[sources]] entry" + (
                    " at its upstream path {}".format(up) if up != path else ""))
                continue
            size, digest = entry
            if len(data) != size:
                self.fail(2, path, "is {} bytes; the manifest records {}".format(len(data), size))
            actual = hashlib.sha256(data).hexdigest()
            if actual != digest:
                self.fail(2, path, "sha256 {} differs from the manifest {}".format(actual, digest))

    # Check 3.
    def check_whole_paths_present(self, pin, tracked, sources, vendored):
        whole = _get(pin.get("vendor"), "whole", "relpaths")
        if whole is None:
            self.fail(3, PIN_REL, "[vendor] whole is missing, empty, or holds an invalid or duplicate path")
            return
        for prefix in whole:
            if not any(_under(prefix, v) for v in vendored):
                self.fail(3, prefix, "[vendor] whole names a path outside [vendored] paths")
                continue
            listed = sorted(p for p in sources if _under(p, prefix))
            if not listed:
                self.fail(3, prefix, "no manifest [[sources]] entry lies under this adopted-whole path")
            for path in listed:
                if path not in tracked:
                    self.fail(3, path, "manifest [[sources]] entry is not a tracked file")
                    continue
                try:
                    st = os.lstat(os.path.join(self.root, path))
                except OSError as exc:
                    self.fail(3, path, "manifest [[sources]] entry is absent on disk: {}".format(exc))
                    continue
                if not stat.S_ISREG(st.st_mode):
                    self.fail(3, path, "manifest [[sources]] entry is not a regular file on disk")

    # Check 3, the required set.
    def check_required_set(self, pin, tracked, sources):
        vendor = pin.get("vendor") if isinstance(pin.get("vendor"), dict) else {}
        whole = _get(vendor, "whole", "relpaths") or []
        for prefix in REQUIRED_WHOLE:
            if prefix not in whole:
                self.fail(3, prefix, "a required adopted-whole root (REQUIRED_WHOLE) that [vendor] whole does "
                          "not name")
        for path in REQUIRED_META:
            if path not in tracked:
                self.fail(3, path, "a required vendored file (REQUIRED_META) that is not tracked under "
                          "[vendored] paths")
        rows = vendor.get("files")
        listed = {e.get("path") for e in rows if isinstance(e, dict)} if isinstance(rows, list) else set()
        for path, upstream in sorted(REQUIRED_FILES.items()):
            if path not in tracked:
                self.fail(3, path, "a required vendored file (REQUIRED_FILES) that is not tracked under "
                          "[vendored] paths")
                continue
            try:
                st = os.lstat(os.path.join(self.root, path))
            except OSError as exc:
                self.fail(3, path, "a required vendored file absent on disk: {}".format(exc))
                continue
            if not stat.S_ISREG(st.st_mode):
                self.fail(3, path, "a required vendored file that is not a regular file on disk")
            if self.upstream_path(path) != upstream:
                self.fail(3, path, "required to be vendored from the upstream {}, but the pin maps it to {}"
                          .format(upstream, self.upstream_path(path)))
            if upstream not in sources:
                self.fail(3, path, "a required vendored file with no manifest [[sources]] entry at {}"
                          .format(upstream))
            if path not in listed:
                self.fail(3, path, "a required vendored file with no [[vendor.files]] row")

    # Check 4.
    def check_active_rules(self, pin, tracked, artifacts, vendored):
        table = pin.get("active-rules")
        active = _get(table, "active", "int")
        excluded = _get(table, "excluded", "int")
        corpus = _get(table, "corpus", "str")
        trees = _get(table, "trees", "relpaths")
        ids = table.get("excluded-ids") if isinstance(table, dict) else None
        bad = []
        if active is None:
            bad.append("active")
        if excluded is None:
            bad.append("excluded")
        if corpus is None or not _valid_rel(corpus):
            bad.append("corpus")
        if trees is None:
            bad.append("trees")
        if (not isinstance(ids, list) or not all(isinstance(i, str) and CORPUS_ID.fullmatch(i) for i in ids)
                or len(set(ids)) != len(ids)):
            bad.append("excluded-ids")
        if bad:
            self.fail(4, PIN_REL, "[active-rules] field(s) missing or malformed: " + ", ".join(bad))
            return
        for prefix in [corpus] + trees:
            if not any(_under(prefix, v) for v in vendored):
                self.fail(4, prefix, "[active-rules] names a path outside [vendored] paths")
                return
        for tree in REQUIRED_ACTIVE_TREES:
            if tree not in trees:
                self.fail(4, tree, "a required active rule tree (REQUIRED_ACTIVE_TREES) that [active-rules] "
                          "trees does not name")
            elif not any(_under(p, tree) for p in tracked):
                self.fail(4, tree, "a required active rule tree with no tracked file")
        corpus_ids = {}
        corpus_files = sorted(p for p in tracked if _under(p, corpus) and p.endswith(".md"))
        if not corpus_files:
            self.fail(4, corpus, "the rule corpus holds no tracked .md file")
            return
        for path in corpus_files:
            try:
                cid = corpus_id(self.file_bytes(path), path)
            except InputError as exc:
                self.fail(4, path, str(exc))
                continue
            if cid in corpus_ids:
                self.fail(4, path, "corpus-id {} duplicates {}".format(cid, corpus_ids[cid]))
                continue
            corpus_ids[cid] = path
        active_files = sorted(p for p in tracked if any(_under(p, t) for t in trees))
        active_ids = {}
        for path in active_files:
            if not path.endswith(".md"):
                self.fail(4, path, "a non-.md file in an active rule tree")
                continue
            try:
                data = self.file_bytes(path)
            except InputError as exc:
                self.fail(4, path, str(exc))
                continue
            digest = artifacts.get(path)
            actual = hashlib.sha256(data).hexdigest()
            if digest is None:
                self.fail(4, path, "no manifest [[artifacts]] entry")
            elif digest != actual:
                self.fail(4, path, "sha256 {} differs from the manifest artifact {}".format(actual, digest))
            try:
                cid = corpus_id(data, path)
            except InputError as exc:
                self.fail(4, path, str(exc))
                continue
            if cid not in corpus_ids:
                self.fail(4, path, "corpus-id {} names no rule in the corpus".format(cid))
            elif cid in active_ids:
                self.fail(4, path, "corpus-id {} is also rendered at {}".format(cid, active_ids[cid]))
            else:
                active_ids[cid] = path
        if len(active_files) != active:
            self.fail(4, PIN_REL, "{} active rule files are tracked; [active-rules] active is {}".format(
                len(active_files), active))
        absent = set(corpus_ids) - set(active_ids)
        declared = set(ids)
        for cid in sorted(absent - declared):
            self.fail(4, corpus_ids[cid], "corpus rule {} is absent from the active trees but not in "
                      "[active-rules] excluded-ids".format(cid))
        for cid in sorted(declared - absent):
            self.fail(4, PIN_REL, "[active-rules] excluded-ids names {}, which is {}".format(
                cid, "active" if cid in active_ids else "not a corpus rule"))
        if len(ids) != excluded or len(absent) != excluded:
            self.fail(4, PIN_REL, "[active-rules] excluded is {}; excluded-ids has {} members and {} corpus "
                      "rules are absent from the active trees".format(excluded, len(ids), len(absent)))

    # Check 5.
    def check_integrity(self, pin, manifest_tree):
        integ = pin.get("integrity")
        tree = _get(integ, "tree-sha256", "str")
        root = _get(integ, "root", "str")
        if tree is None or not HEX64.fullmatch(tree):
            self.fail(5, PIN_REL, "[integrity] tree-sha256 is missing or not 64 lowercase hex characters")
        elif tree != manifest_tree:
            self.fail(5, PIN_REL, "[integrity] tree-sha256 {} differs from the manifest header {}".format(
                tree, manifest_tree))
        if root is None or not root.startswith("sha256:") or not HEX64.fullmatch(root[len("sha256:"):]):
            self.fail(5, PIN_REL, "[integrity] root is missing or not sha256: and 64 lowercase hex characters")
            return
        try:
            data = self.file_bytes(ROOT_TXT_REL)
        except InputError as exc:
            self.fail(5, ROOT_TXT_REL, str(exc))
            return
        text = data.decode("ascii", "replace")
        if text.endswith("\n"):
            text = text[:-1]
        if text != root:
            self.fail(5, ROOT_TXT_REL, "holds {!r}; [integrity] root is {!r}".format(text, root))

    # Check 6.
    def check_vendor_block(self, pin, tracked, sources):
        vendor = pin.get("vendor")
        if not isinstance(vendor, dict):
            self.fail(6, PIN_REL, "no [vendor] table")
            return
        for key in ("source-date", "verified"):
            if _get(vendor, key, "str") is None:
                self.fail(6, PIN_REL, "[vendor] {} is missing or empty".format(key))
        lic = vendor.get("license-sha256")
        if not isinstance(lic, str) or not HEX64.fullmatch(lic):
            self.fail(6, PIN_REL, "[vendor] license-sha256 is missing or not 64 lowercase hex characters")
        files = vendor.get("files")
        if not isinstance(files, list) or not files:
            self.fail(6, PIN_REL, "[vendor] files is missing or empty")
            return
        seen = set()
        for i, ent in enumerate(files):
            path = ent.get("path") if isinstance(ent, dict) else None
            size = _get(ent, "bytes", "int")
            digest = ent.get("sha256") if isinstance(ent, dict) else None
            if not _valid_rel(path) or size is None or not isinstance(digest, str) or not HEX64.fullmatch(digest):
                self.fail(6, PIN_REL, "[[vendor.files]] entry {} is malformed (path, bytes, sha256)".format(i + 1))
                continue
            if path in seen:
                self.fail(6, path, "listed twice in [[vendor.files]]")
                continue
            seen.add(path)
            if path not in tracked:
                self.fail(6, path, "[[vendor.files]] names a path that is not a tracked vendored file")
                continue
            entry = sources.get(self.upstream_path(path))
            if entry is None:
                self.fail(6, path, "[[vendor.files]] entry has no manifest [[sources]] entry")
            elif entry != (size, digest):
                self.fail(6, path, "[[vendor.files]] records {} bytes, sha256 {}; the manifest records {} "
                          "bytes, sha256 {}".format(size, digest, entry[0], entry[1]))
        if not any(up == "LICENSE" for up in self.relocated.values()):
            self.fail(6, PIN_REL, "no vendored file is relocated from the upstream LICENSE, so [vendor] "
                      "license-sha256 is compared with no vendored file")
        for path in sorted(p for p, up in self.relocated.items() if up == "LICENSE"):
            if not isinstance(lic, str) or not HEX64.fullmatch(lic):
                continue  # already a check 6 failure above
            try:
                actual = hashlib.sha256(self.file_bytes(path)).hexdigest()
            except InputError as exc:
                self.fail(6, path, str(exc))
                continue
            if actual != lic:
                self.fail(6, path, "relocated from the upstream LICENSE, but its sha256 {} differs from "
                          "[vendor] license-sha256 {}".format(actual, lic))

    # Check 7.
    def check_upstream(self, pin, commit, tracked):
        up = self.upstream
        if commit is None:
            self.fail(7, PIN_REL, "cannot evaluate: the pinned source-commit is invalid (see check 1)")
            return
        try:
            run_git(up, ["cat-file", "-e", commit + "^{commit}"], "resolve the pinned commit in " + up)
        except InputError as exc:
            self.fail(7, up, str(exc))
            return
        for path in sorted(tracked):
            try:
                where = self.upstream_path(path)
                theirs = run_git(up, ["cat-file", "blob", commit + ":" + where], "read " + where + " at the pin")
                ours = self.file_bytes(path)
            except InputError as exc:
                self.fail(7, path, str(exc))
                continue
            if theirs != ours:
                self.fail(7, path, "differs from the pack at {} ({} bytes there, {} here)".format(
                    commit, len(theirs), len(ours)))
        lic = _get(pin.get("vendor"), "license-sha256", "str")
        try:
            data = run_git(up, ["cat-file", "blob", commit + ":LICENSE"], "read LICENSE at the pin")
        except InputError as exc:
            self.fail(7, "LICENSE", str(exc))
            return
        actual = hashlib.sha256(data).hexdigest()
        if actual != lic:
            self.fail(7, "LICENSE", "sha256 {} at {} differs from [vendor] license-sha256 {}".format(
                actual, commit, lic))

    def run(self):
        top = run_git(self.root, ["rev-parse", "--show-toplevel"], "locate the repository root")
        top = top.decode("utf-8", "replace").strip()
        if os.path.realpath(top) != os.path.realpath(self.root):
            raise InputError("{}: not the top level of its git work tree ({})".format(self.root, top))
        pin_text, pin = read_toml(os.path.join(self.root, PIN_REL), "the pin")
        self.check_pin_final(pin_text)
        commit, tracked = self.check_source_and_paths(pin)
        if tracked is None:
            self.fail(1, PIN_REL, "checks 2 to 7 cannot be evaluated without a valid [vendored] paths list")
            return 0
        self.relocated = self.check_relocations(pin, tracked)
        manifest_rel = _get(pin.get("integrity"), "manifest", "str")
        if manifest_rel is None or not _valid_rel(manifest_rel):
            raise InputError("{}: [integrity] manifest is missing or not a relative path".format(PIN_REL))
        if manifest_rel not in tracked:
            raise InputError("{}: the manifest is not a tracked vendored file".format(manifest_rel))
        manifest_tree, sources, artifacts = load_manifest(self.root, manifest_rel)
        vendored = pin["vendored"]["paths"]
        self.check_files_match_manifest(tracked, sources, manifest_rel)
        self.check_whole_paths_present(pin, tracked, sources, vendored)
        self.check_required_set(pin, tracked, sources)
        self.check_active_rules(pin, tracked, artifacts, vendored)
        self.check_integrity(pin, manifest_tree)
        self.check_vendor_block(pin, tracked, sources)
        if self.upstream is not None:
            self.check_upstream(pin, commit, tracked)
        return len(tracked)


def main(argv):
    parser = argparse.ArgumentParser(prog="check-aiqt-vendor.py", description=__doc__.split("\n", 1)[0])
    parser.add_argument("--root", default=DEFAULT_ROOT, help="repository root (default: this checkout)")
    parser.add_argument("--upstream", default=None, help="pack checkout for check 7")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    upstream = os.path.abspath(args.upstream) if args.upstream is not None else None
    gate = Gate(root, upstream)
    try:
        count = gate.run()
    except InputError as exc:
        print("{}: FAIL: cannot evaluate: {}".format(PROG, exc), file=sys.stderr)
        return 1
    for check, path, message in gate.report.failures:
        print("{}: FAIL check {}: {}: {}".format(PROG, check, path, message), file=sys.stderr)
    if gate.report.failures:
        print("{}: {} failure(s)".format(PROG, len(gate.report.failures)), file=sys.stderr)
        return 1
    scope = "checks 1 to 7" if upstream is not None else "checks 1 to 6; check 7 not requested"
    print("{}: OK: {} tracked vendored files ({})".format(PROG, count, scope))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
