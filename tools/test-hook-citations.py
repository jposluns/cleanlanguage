#!/usr/bin/env python3
"""Check that every hook citation under tools/ names code the vendored hook actually holds.

The tools cite the vendored AIQT hook by symbol, never by line number, so a re-vendor that moves code
does not silently strand a citation. Two citation grammars are recognized anywhere under tools/:

- aiqt_hooks.py, a colon, and SYMBOL, where SYMBOL is a name bound at the top level of
  plugin/aiqt-guardrails-hooks/hooks/scripts/aiqt_hooks.py, namely a def, an async def, a class, or a name an
  Assign or AnnAssign statement binds at module level. A nested function is not a valid anchor. Where a
  clause inside the symbol matters, the anchor is followed by one space and a literal in backticks
  (for example the anchor for orch_dispatch_ledger followed by a backticked is_dispatch clause), and the
  literal must occur inside the source segment of the last top-level binding of SYMBOL.
- hooks.json, a colon, and MODE, where MODE is a mode the vendored hooks.json registers: the argument
  that follows the aiqt_hooks.py script path in the args list of a command hook.

Every other use of either prefix is a finding: a numeric citation (the prefix followed by a digit, also
across a string-literal or comment line wrap), or any other text after the colon. The one exception is
the bare prefix closing a string literal, as an assertion that a reason cites the hook at all does.

A bare hook line number is a finding too. The converted sites wrote hook lines as bare numbers in every
prose position (after at, via, open or return, inside parentheses, in a list after an anchor, after a
symbol name, and as a table column), always inside a comment or a string, and always in a file that
cites the hook. So the rule is: in a Python file under tools/ that cites the hook (the aiqt_hooks.py
prefix and a colon occur in it at least once, as an anchor or not), every
4- or 5-digit number, or a range of them, inside a comment or a string token is a finding, unless the file
and the number are listed in tools/hook-citation-allowlist.json with the reason it is not a hook line. A
number inside the backticked literal of an anchor, a number in code, a digit run attached to letters, a
dot, a colon, a slash, a hyphen or a plus sign (so U+3164, 1.5, 2026-10-30 and T1:639 are not numbers
here) is not a candidate, except that a dot after the number counts as attached only when a letter, a
digit or an underscore follows it, so a number that ends a sentence (the open at 7807.) is a finding. The allowlist fails closed: an unreadable or malformed file, an entry without a
reason, a duplicate entry, or an entry that no longer matches any number in its file is a finding.

The check fails closed. An unreadable, non-UTF-8, unparseable, or empty hook; an unreadable or
malformed hooks.json, or one that registers no mode; a tools tree that cannot be listed or holds no file;
a file that cannot be read or decoded; and a symbolic link or other non-regular entry under tools/ are
each a finding that names the path, never a clean pass.

Residual, disclosed: a bare hook line number of 1 to 3 digits, one in code rather than a comment or a
string, one in a file that never cites the hook or is not a Python file, and any number an allowlist
entry names for its file (the entry covers every occurrence of that number in that file) are not caught.
Nor does the check judge whether an anchor names the symbol a sentence means, only that the symbol and
any quoted literal exist.

Run with python3 -I. Options --hook, --hooks-json, --tools and --allowlist point the real-tree test at
another hook, registration file, tools tree or allowlist (for example an upstream hook extracted for a re-vendor); remaining
arguments go to unittest.
"""
import argparse
import ast
import io
import json
import os
import re
import stat
import sys
import tempfile
import tokenize
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
HOOK = os.path.join(ROOT, "plugin", "aiqt-guardrails-hooks", "hooks", "scripts", "aiqt_hooks.py")
HOOKS_JSON = os.path.join(ROOT, "plugin", "aiqt-guardrails-hooks", "hooks", "hooks.json")
ALLOWLIST = os.path.join(TOOLS, "hook-citation-allowlist.json")
SCRIPT_NAME = "aiqt_hooks.py"

IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
PREFIX = re.compile(r"(aiqt_hooks\.py|hooks\.json):")
HOOK_ANCHOR = re.compile(r"aiqt_hooks\.py:(" + IDENT + r")(?![A-Za-z0-9_])(?: `([^`\n]+)`)?")
JSON_ANCHOR = re.compile(r"hooks\.json:(" + IDENT + r")(?![A-Za-z0-9_])")
BARE_PREFIX = re.compile(r"\"[ \t]*[,)]")
NUMERIC = re.compile(r"(?:\"[ \t]*\n[ \t]*\"|[ \t]*\n[ \t]*#[ \t]*)?[0-9]")
HOOK_PREFIX = re.compile(r"aiqt_hooks\.py:")
BARE_NUMBER = re.compile(r"(?<![0-9A-Za-z_.+:/-])[0-9]{4,5}(?:-[0-9]{1,5})?(?![0-9A-Za-z_-]|\.[0-9A-Za-z_])")
ALLOW_NUMBER = re.compile(r"[0-9]{4,5}(?:-[0-9]{1,5})?")
TEXT_TOKENS = {tokenize.COMMENT, tokenize.STRING}
for _name in ("FSTRING_MIDDLE", "TSTRING_MIDDLE"):
    if hasattr(tokenize, _name):
        TEXT_TOKENS.add(getattr(tokenize, _name))


def hook_symbols(path):
    # Map each top-level name to the source segment of its last top-level binding. Raises on any input
    # that cannot answer the question (unreadable, non-UTF-8, unparseable, no binding at all).
    with open(path, "rb") as fh:
        raw = fh.read()
    src = raw.decode("utf-8")
    tree = ast.parse(src, filename=path)
    table = {}
    for node in tree.body:
        names = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names.extend(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        if not names:
            continue
        segment = ast.get_source_segment(src, node)
        if segment is None:
            raise ValueError("no source segment for a top-level node at line {}".format(node.lineno))
        for name in names:
            table[name] = segment
    if not table:
        raise ValueError("no top-level binding")
    return table


def registered_modes(path):
    # The mode argument after the aiqt_hooks.py script path in every command hook. Raises when the file
    # cannot be read or parsed, has an unexpected shape, or registers no mode.
    with open(path, "rb") as fh:
        data = json.loads(fh.read().decode("utf-8"))
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        raise ValueError("no hooks object")
    modes = set()
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            raise ValueError("event {} is not a list".format(event))
        for group in groups:
            entries = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(entries, list):
                raise ValueError("a group under {} has no hooks list".format(event))
            for entry in entries:
                args = entry.get("args") if isinstance(entry, dict) else None
                if not isinstance(args, list):
                    continue
                for i, arg in enumerate(args[:-1]):
                    if isinstance(arg, str) and os.path.basename(arg) == SCRIPT_NAME \
                            and isinstance(args[i + 1], str):
                        modes.add(args[i + 1])
    if not modes:
        raise ValueError("no registered mode")
    return modes


def load_allowlist(path):
    # {(file, number): reason}. Raises on an unreadable or malformed file, an entry with an unknown or
    # missing key, a malformed number, an empty reason, or a duplicate.
    with open(path, "rb") as fh:
        data = json.loads(fh.read().decode("utf-8"))
    if not isinstance(data, dict) or set(data) != {"entries"} or not isinstance(data["entries"], list):
        raise ValueError("expected an object with exactly the key entries, a list")
    table = {}
    for i, entry in enumerate(data["entries"]):
        if not isinstance(entry, dict) or set(entry) != {"file", "number", "reason"}:
            raise ValueError("entry {} must carry exactly file, number and reason".format(i))
        f, n, r = entry["file"], entry["number"], entry["reason"]
        if not (isinstance(f, str) and f.startswith("tools/") and isinstance(n, str)
                and ALLOW_NUMBER.fullmatch(n) and isinstance(r, str) and r.strip()):
            raise ValueError("entry {} is malformed".format(i))
        if (f, n) in table:
            raise ValueError("entry {} duplicates {} {}".format(i, f, n))
        table[(f, n)] = r
    return table


def bare_numbers(text):
    # Yield (offset, number) for each candidate bare number in a comment or string token, skipping the
    # backticked literal of an anchor. Raises tokenize.TokenError or SyntaxError on untokenizable text.
    skip = [a.span(2) for a in HOOK_ANCHOR.finditer(text) if a.group(2) is not None]
    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type not in TEXT_TOKENS:
            continue
        base = starts[tok.start[0] - 1] + tok.start[1]
        for m in BARE_NUMBER.finditer(tok.string):
            off = base + m.start()
            if not any(lo <= off < hi for lo, hi in skip):
                yield off, m.group(0)


def _tree_files(tools_dir, findings):
    files = []

    def onerror(err):
        findings.append("{}: cannot evaluate: cannot list: {}".format(getattr(err, "filename", tools_dir), err))

    if not os.path.isdir(tools_dir):
        findings.append("{}: cannot evaluate: not a directory".format(tools_dir))
        return files
    for dirpath, dirnames, filenames in os.walk(tools_dir, onerror=onerror):
        kept = []
        for d in sorted(dirnames):
            p = os.path.join(dirpath, d)
            if os.path.islink(p):
                findings.append("{}: a symbolic link under tools/ is not scanned".format(p))
            elif d != "__pycache__":
                kept.append(d)
        dirnames[:] = kept
        for f in sorted(filenames):
            p = os.path.join(dirpath, f)
            try:
                st = os.lstat(p)
            except OSError as err:
                findings.append("{}: cannot evaluate: {}".format(p, err))
                continue
            if not stat.S_ISREG(st.st_mode):
                findings.append("{}: not a regular file, so it is not scanned".format(p))
                continue
            files.append(p)
    if not files and not findings:
        findings.append("{}: cannot evaluate: no file to scan".format(tools_dir))
    return files


def check(tools_dir, hook_path, hooks_json_path, allowlist_path=None):
    # Return (findings, stats). An empty findings list is the only clean result.
    findings = []
    stats = {"files": [], "hook_anchors": 0, "literals": 0, "json_anchors": 0, "bare_checked_files": 0,
             "allowlisted": 0}
    if allowlist_path is None:
        allowlist_path = os.path.join(tools_dir, "hook-citation-allowlist.json")
    try:
        allow = load_allowlist(allowlist_path)
    except (OSError, UnicodeDecodeError, ValueError) as err:
        findings.append("{}: cannot evaluate the allowlist: {}".format(allowlist_path, err))
        allow = None
    used = set()
    try:
        table = hook_symbols(hook_path)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as err:
        findings.append("{}: cannot evaluate the hook: {}".format(hook_path, err))
        table = None
    try:
        modes = registered_modes(hooks_json_path)
    except (OSError, UnicodeDecodeError, ValueError, AttributeError) as err:
        findings.append("{}: cannot evaluate the registrations: {}".format(hooks_json_path, err))
        modes = None
    for path in _tree_files(tools_dir, findings):
        try:
            with open(path, "rb") as fh:
                text = fh.read().decode("utf-8")
        except (OSError, UnicodeDecodeError) as err:
            findings.append("{}: cannot evaluate: {}".format(path, err))
            continue
        stats["files"].append(path)
        for m in PREFIX.finditer(text):
            where = "{}:{}".format(path, text.count("\n", 0, m.start()) + 1)
            if m.group(1) == "aiqt_hooks.py":
                a = HOOK_ANCHOR.match(text, m.start())
                if a:
                    stats["hook_anchors"] += 1
                    if table is None:
                        continue
                    name, literal = a.group(1), a.group(2)
                    if name not in table:
                        findings.append("{}: {} is not a top-level name in the hook".format(where, name))
                    elif literal is not None:
                        stats["literals"] += 1
                        if literal not in table[name]:
                            findings.append("{}: the literal {!r} does not occur in {}".format(
                                where, literal, name))
                    continue
            else:
                a = JSON_ANCHOR.match(text, m.start())
                if a:
                    stats["json_anchors"] += 1
                    if modes is not None and a.group(1) not in modes:
                        findings.append("{}: {} is not a mode hooks.json registers".format(where, a.group(1)))
                    continue
            if BARE_PREFIX.match(text, m.end()):
                continue
            if NUMERIC.match(text, m.end()):
                findings.append("{}: numeric {} citation; cite a symbol instead".format(where, m.group(1)))
            else:
                findings.append("{}: {} citation without a symbol: {!r}".format(
                    where, m.group(1), text[m.start():m.end() + 20]))
        if not path.endswith(".py") or not HOOK_PREFIX.search(text):
            continue
        rel = "tools/" + os.path.relpath(path, tools_dir).replace(os.sep, "/")
        stats["bare_checked_files"] += 1
        try:
            found = list(bare_numbers(text))
        except (tokenize.TokenError, SyntaxError) as err:
            findings.append("{}: cannot evaluate: cannot tokenize: {}".format(path, err))
            continue
        for off, number in found:
            if allow is not None and (rel, number) in allow:
                used.add((rel, number))
                stats["allowlisted"] += 1
                continue
            findings.append("{}:{}: bare hook line number {} in a file that cites the hook; cite a symbol, "
                            "or list it in the allowlist with its reason".format(
                                path, text.count("\n", 0, off) + 1, number))
    if allow is not None:
        for key in sorted(set(allow) - used):
            findings.append("{}: stale allowlist entry {} {}: no such number in that file".format(
                allowlist_path, key[0], key[1]))
    stats["allowlist_entries"] = len(allow) if allow is not None else 0
    return findings, stats


OPTIONS = argparse.Namespace(hook=HOOK, hooks_json=HOOKS_JSON, tools=TOOLS, allowlist=None)


class TreeCitations(unittest.TestCase):
    def test_every_citation_under_tools_resolves(self):
        findings, stats = check(OPTIONS.tools, OPTIONS.hook, OPTIONS.hooks_json, OPTIONS.allowlist)
        sys.stderr.write("test-hook-citations: {} files, {} hook anchors ({} with a literal), {} hooks.json "
                         "anchors, {} files checked for bare numbers, {} allowlisted numbers from {} "
                         "entries, {} findings, against {}\n".format(
                             len(stats["files"]), stats["hook_anchors"], stats["literals"],
                             stats["json_anchors"], stats["bare_checked_files"], stats["allowlisted"],
                             stats["allowlist_entries"], len(findings), OPTIONS.hook))
        self.assertEqual(findings, [], "\n" + "\n".join(findings))
        self.assertGreater(stats["hook_anchors"], 0)

    def test_this_file_is_inside_the_scanned_set(self):
        if os.path.realpath(OPTIONS.tools) != os.path.realpath(TOOLS):
            self.skipTest("--tools points elsewhere")
        _, stats = check(OPTIONS.tools, OPTIONS.hook, OPTIONS.hooks_json, OPTIONS.allowlist)
        self.assertIn(os.path.abspath(__file__), [os.path.abspath(p) for p in stats["files"]])


P = "aiqt_hooks" + ".py:"
J = "hooks" + ".json:"
FIXTURE_HOOK = ("def alpha(data):\n"
                "    def inner():\n"
                "        return 0\n"
                "    return \"beta gamma\"\n"
                "\n"
                "\n"
                "DELTA, EPSILON = 1, 2\n"
                "ZETA: int = 3\n"
                "\n"
                "\n"
                "class Eta:\n"
                "    pass\n")
FIXTURE_JSON = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
    {"type": "command", "command": "python3", "args": ["-I", "/x/hooks/scripts/aiqt_hooks.py", "alpha_mode"]}]}]}}
GOOD = ("# see " + P + "alpha `beta gamma` and " + P + "DELTA, " + P + "EPSILON, " + P + "ZETA, "
        + P + "Eta, and " + J + "alpha_mode\n"
        "assert_in(\"" + P + "\", reason)\n")


class FixtureBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.tools = os.path.join(self.root, "tools")
        os.mkdir(self.tools)
        self.hook = os.path.join(self.root, "aiqt_hooks.py")
        self.json = os.path.join(self.root, "hooks.json")
        with open(self.hook, "w", encoding="utf-8") as fh:
            fh.write(FIXTURE_HOOK)
        with open(self.json, "w", encoding="utf-8") as fh:
            json.dump(FIXTURE_JSON, fh)
        self.allow = os.path.join(self.root, "allow.json")
        self._allow([])

    def _allow(self, entries):
        with open(self.allow, "w", encoding="utf-8") as fh:
            json.dump({"entries": entries}, fh)

    def _check(self, hook=None, hooks_json=None):
        return check(self.tools, hook or self.hook, hooks_json or self.json, self.allow)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, text, name="t.py"):
        mode = "wb" if isinstance(text, bytes) else "w"
        with open(os.path.join(self.tools, name), mode) as fh:
            fh.write(text)
        return self._check()

    def _red(self, text, needle):
        findings, _ = self._run(GOOD + text)
        self.assertEqual(len(findings), 1, findings)
        self.assertIn(needle, findings[0])


class Flips(FixtureBase):
    def test_good_fixture_is_clean(self):
        findings, stats = self._run(GOOD)
        self.assertEqual(findings, [])
        self.assertEqual((stats["hook_anchors"], stats["literals"], stats["json_anchors"]), (5, 1, 1))

    def test_missing_symbol_is_red(self):
        self._red("# " + P + "no_such_symbol here\n", "no_such_symbol is not a top-level name")

    def test_nested_function_is_not_an_anchor(self):
        self._red("# " + P + "inner\n", "inner is not a top-level name")

    def test_numeric_citation_is_red(self):
        self._red("# " + P + "12-14\n", "numeric aiqt_hooks.py citation")

    def test_numeric_citation_wrapped_in_a_comment_is_red(self):
        self._red("# see (" + P + "\n#   12-14)\n", "numeric aiqt_hooks.py citation")

    def test_numeric_citation_wrapped_in_a_string_is_red(self):
        self._red("x = (\"see " + P + "\"\n     \"12-14)\")\n", "numeric aiqt_hooks.py citation")

    def test_numeric_hooks_json_citation_is_red(self):
        self._red("# " + J + "278\n", "numeric hooks.json citation")

    def test_literal_absent_from_the_symbol_is_red(self):
        self._red("# " + P + "alpha `not in alpha`\n", "does not occur in alpha")

    def test_literal_from_another_symbol_is_red(self):
        self._red("# " + P + "DELTA `beta gamma`\n", "does not occur in DELTA")

    def test_unregistered_mode_is_red(self):
        self._red("# " + J + "beta_mode\n", "beta_mode is not a mode")

    def test_prefix_without_symbol_is_red(self):
        self._red("# " + P + " alpha\n", "citation without a symbol")

    def test_non_utf8_file_is_red(self):
        self._run(GOOD)
        findings, _ = self._run(b"\xff\xfe" + P.encode() + b"alpha\n", name="bad.py")
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("bad.py: cannot evaluate", findings[0])

    def test_symlink_under_tools_is_red(self):
        self._run(GOOD)
        os.symlink(os.path.join(self.tools, "t.py"), os.path.join(self.tools, "link.py"))
        findings, _ = self._check()
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("link.py: not a regular file", findings[0])

    def test_missing_hook_fails_closed(self):
        self._run(GOOD)
        findings, _ = self._check(hook=os.path.join(self.root, "absent.py"))
        self.assertTrue(findings and "cannot evaluate the hook" in findings[0], findings)

    def test_unparseable_hook_fails_closed(self):
        self._run(GOOD)
        with open(self.hook, "w", encoding="utf-8") as fh:
            fh.write("def (:\n")
        findings, _ = self._check()
        self.assertTrue(findings and "cannot evaluate the hook" in findings[0], findings)

    def test_hooks_json_without_modes_fails_closed(self):
        self._run(GOOD)
        with open(self.json, "w", encoding="utf-8") as fh:
            json.dump({"hooks": {}}, fh)
        findings, _ = self._check()
        self.assertTrue(any("cannot evaluate the registrations" in f for f in findings), findings)

    def test_empty_tools_tree_fails_closed(self):
        findings, _ = self._check()
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("no file to scan", findings[0])

    def test_pycache_is_skipped(self):
        self._run(GOOD)
        os.mkdir(os.path.join(self.tools, "__pycache__"))
        with open(os.path.join(self.tools, "__pycache__", "x.pyc"), "wb") as fh:
            fh.write(b"\xff" + P.encode() + b"9")
        findings, _ = self._check()
        self.assertEqual(findings, [])


class BareNumberFlips(FixtureBase):
    def test_bare_number_in_a_comment_is_red(self):
        self._red("# the clause at 7817 decides it\n", "bare hook line number 7817")

    def test_bare_range_in_a_string_is_red(self):
        self._red("x = \"returns at 9713-9714\"\n", "bare hook line number 9713-9714")

    def test_sentence_final_number_is_red(self):
        self._red("# before the open at 7807.\n", "bare hook line number 7807")

    def test_sentence_final_range_is_red(self):
        self._red("# the reader returns at 8075-8076.\n", "bare hook line number 8075-8076")

    def test_table_column_is_red(self):
        self._red("#   turn-state.json   7753-7756 (the writer)\n", "bare hook line number 7753-7756")

    def test_number_in_code_is_not_a_candidate(self):
        findings, _ = self._run(GOOD + "x = 12345\n")
        self.assertEqual(findings, [])

    def test_attached_numbers_are_not_candidates(self):
        findings, _ = self._run(GOOD + "# U+3164, 1.5, 2026-10-30, T1:639, v12345, 12345.6, 2026.x\n")
        self.assertEqual(findings, [])

    def test_file_that_never_cites_the_hook_is_out_of_scope(self):
        findings, _ = self._run("# a year, 2026\n")
        self.assertEqual(findings, [])

    def test_number_inside_an_anchor_literal_is_skipped(self):
        with open(self.hook, "a", encoding="utf-8") as fh:
            fh.write("\n\ndef theta():\n    return 12345\n")
        findings, _ = self._run(GOOD + "# " + P + "theta `return 12345`\n")
        self.assertEqual(findings, [])

    def test_allowlisted_number_is_clean(self):
        self._allow([{"file": "tools/t.py", "number": "4096", "reason": "PATH_MAX in bytes"}])
        findings, stats = self._run(GOOD + "# PATH_MAX (4096)\n")
        self.assertEqual(findings, [])
        self.assertEqual(stats["allowlisted"], 1)

    def test_allowlist_is_per_file(self):
        self._allow([{"file": "tools/other.py", "number": "4096", "reason": "PATH_MAX in bytes"}])
        findings, _ = self._run(GOOD + "# PATH_MAX (4096)\n")
        self.assertEqual(len(findings), 2, findings)
        self.assertTrue(any("bare hook line number 4096" in f for f in findings), findings)
        self.assertTrue(any("stale allowlist entry" in f for f in findings), findings)

    def test_stale_allowlist_entry_is_red(self):
        self._allow([{"file": "tools/t.py", "number": "4096", "reason": "PATH_MAX in bytes"}])
        self._red("", "stale allowlist entry tools/t.py 4096")

    def test_allowlist_entry_without_reason_fails_closed(self):
        self._allow([{"file": "tools/t.py", "number": "4096", "reason": " "}])
        findings, _ = self._run(GOOD)
        self.assertTrue(any("cannot evaluate the allowlist" in f for f in findings), findings)

    def test_duplicate_allowlist_entry_fails_closed(self):
        e = {"file": "tools/t.py", "number": "4096", "reason": "PATH_MAX in bytes"}
        self._allow([e, dict(e)])
        findings, _ = self._run(GOOD)
        self.assertTrue(any("cannot evaluate the allowlist" in f for f in findings), findings)

    def test_missing_allowlist_fails_closed(self):
        os.remove(self.allow)
        findings, _ = self._run(GOOD)
        self.assertTrue(any("cannot evaluate the allowlist" in f for f in findings), findings)


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--hook", default=HOOK)
    parser.add_argument("--hooks-json", default=HOOKS_JSON)
    parser.add_argument("--tools", default=TOOLS)
    parser.add_argument("--allowlist", default=None)
    known, rest = parser.parse_known_args()
    OPTIONS.hook, OPTIONS.hooks_json, OPTIONS.tools = known.hook, known.hooks_json, known.tools
    OPTIONS.allowlist = known.allowlist
    unittest.main(argv=[sys.argv[0]] + rest, verbosity=2)


if __name__ == "__main__":
    main()
