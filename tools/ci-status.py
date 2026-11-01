#!/usr/bin/env python3
"""Report the CI verdict for one commit, exiting non-zero unless every check passed.

Trust boundary. The caller is trusted, together with all of its process state;
environment variables (PATH, BASH_ENV, SHELLOPTS, BASHOPTS, exported functions),
open descriptors, signal state, resource limits, tracers, seccomp filters and the
mount namespace are examples, not a closed list, and a caller with that control
can forge any outcome. ci-status.sh and this tool defend against untrusted files
at the paths they resolve: a planted ci-status.py in the working directory, a
misplaced, symlinked or hard-linked gate, and a decoy reached through a
descriptor path. Within that boundary, property A: through tools/ci-status.sh,
no ci-status.py other than the real one beside the real wrapper runs. Property
B: the tool exits 0 only when this gate ran and every check passed. Under
supported invocations (tools/ci-status.sh executed, run as bash
tools/ci-status.sh, by absolute path or through PATH, from an ordinary shell)
the exit status follows the codes below exactly. Otherwise the status may be any
nonzero code, which still keeps property B: resource exhaustion (a failed fork,
a MemoryError during import), a signal that ends the process, and a syntax error
in this file are outside the exact-code contract. An import failure that raises an exception
exits 3. A gh exit status that cannot be observed is unreadable (exit 3), never
success: the tool reaps gh itself with os.waitpid, because CPython subprocess
reads a lost status (ECHILD from the wait) as 0, and it resets SIGCHLD to its
default disposition before any gh call, because an ignored SIGCHLD, inherited
from the caller, makes the system reap gh and lose its status. Known channels of
the trusted caller state, as examples: a tracer (ptrace) or seccomp filter can
alter any system call result, a bind mount can present the real wrapper beside a
planted gate, and SHELLOPTS with noexec or onecmd makes bash run nothing and exit
0 before ci-status.sh runs.

The verdict comes from the check-runs API, the only endpoint that sees every
required check: the Cloudflare Pages build (the check GitHub requires on this
repository today, per CLAUDE.md) is produced by an external app, not GitHub
Actions, so a gate built on actions/runs alone would pass while the required
check was failing. The legacy commits/<sha>/status endpoint is not used either:
this repository publishes no commit statuses, so it answers "pending" forever.

Reading is FAIL-CLOSED. The whole paginated response is parsed as JSON; a page
that is not an object, a check_runs that is not a list, a check that is not an
object, or any field of the wrong type (a status that is not a non-empty string,
a conclusion/name/slug that is neither a string nor null) makes the entire reading
unreadable. So does a check run whose head_sha is present and is not a non-empty
string naming the requested commit; a run that omits head_sha is accepted on the
strength of the API path, which already names the commit. Absence of checks, an
unreadable read, and a partial reading are never success, so a caller waiting for
green never mistakes silence, a malformed page, or a dropped record for a pass.
This replaces an earlier shell implementation that serialized checks to delimited
text and parsed them in bash, which repeatedly let a crafted or malformed field
forge or hide a check; parsing structured JSON here removes that class of defect.

A pass is never declared on one reading: an external app can report before GitHub
Actions has created its runs, and a read taken in that window sees only the checks
that exist and calls them "every check" (a false green observed on a pull request
whose Actions gates had not started). So a pass is confirmed only when two
consecutive readings have the identical set of checks and conclusions. This costs
one interval on every green result, whether or not --wait was given.

This repository runs, on every pull request and every push to main, 3 GitHub
Actions jobs whose display names are Plugin manifests, Skill discovery and Agent
Plugins manifest, and the external Cloudflare Pages build, which CLAUDE.md names as
the check GitHub requires today. The tool insists on all 4, ahead of the branch
ruleset listing the 3 Actions jobs. Each Actions job is matched by its exact display
name (case-sensitive and untrimmed) together with the github-actions app slug, so a
run of the same name from another app, or an unnamed github-actions job such as the
sitemap check, never satisfies one; the Cloudflare build is matched by its app slug
alone. A passing reading missing any of the 4 means that check has not registered
(a malformed branch, a head whose commit message carries a skip marker, or the
external check still building); such a reading is downgraded from pass to pending,
never to a red. A commit that legitimately ran none of them is a safe false-red,
never a false-green. Residual: a name and an app cannot tell which workflow
produced a run, so a pull request that deletes one of those workflows and adds
another job with the same display name satisfies the check; GitHub's own
app-pinned required check has the same limit. Within the same residual, another job
in one of the 3 workflows can carry one of the 3 display names in a form the check
does not compare, such as a block scalar indented more than 4 spaces (see below).
The tool reads the check runs the API
returns under its default filter, the latest runs, so whether such a job can take
the place of a failed run of the real job in a reading depends on how the API
selects the latest runs, which this tool does not control. Pointing --repo at a repository that
does not run all 4 unconditionally would downgrade a legitimate green to pending.
Residual: a required check that concludes skipped or neutral counts as passed, as
GitHub counts it for a required check, so a job skipped without running its steps
reads green. For the 3 Actions jobs, tools/test-ci-status.sh reads each workflow
with an allow-list that fails closed: the on: block holds only a pull_request
trigger with nothing under it and a push trigger filtered to main alone; the
permissions block is exactly contents: read; a top-level env, if present, holds only
CLAUDE_CODE_VERSION, set to a dotted version number such as 2.1.310; and the job
with a required display name holds only name, runs-on set to ubuntu-latest, and
steps. Each step holds an optional name and either uses: naming an owner/repo action
pinned to a full 40-character commit sha, or run: with shell: bash, and nothing
else. So no if:, needs: or continue-on-error: key, no other runner or shell, no
local or docker action, and no environment variable such as BASH_ENV or SHELLOPTS
set in the workflow can skip the job or its steps, or pass over a failed step, and
still read as passing; any line outside that shape fails the check. What the
commands the steps run and the pinned actions do, including anything they write for
later steps, and what the other jobs of the workflow run, are not checked.

The commit is named only by its full 40-character hexadecimal sha, folded to
lower case and used as given. Every other value, an abbreviation of any length,
a ref name such as HEAD or main, a revision expression, a path-like value, a
non-hexadecimal value, or an empty value, is refused (exit 3) with a message to
pass the full 40-character sha, for example from git rev-parse or gh pr view
--json headRefOid. The tool makes no local git call of its own, so the API path
is built only from a full sha, and a full sha that is not a commit of the
repository fails the API read (exit 3). The sha is printed before any gh call,
and the repository is printed once it is known.

--repo is accepted only as owner/name with exactly one slash: an owner of ASCII
letters, digits and hyphens, and a name of ASCII letters, digits, hyphens,
underscores and dots that does not start with a dot. Any other value is refused
(exit 3), so --repo cannot add a path segment or a query to the API call. A
repository inferred with gh repo view is validated the same way.

Every gh call runs in the directory that holds this file, resolved through
symlinks, so a symlinked copy binds to the clone that holds the real file. Each
gh call runs with GH_REPO, GH_HOST and every GIT_ variable removed from its
environment, so none of them can redirect the repository lookup or the API
call. Residual: gh finds the clone through git, which searches upward from that
directory, so a copy outside any checkout infers the repository of an enclosing
checkout if there is one; pass --repo for such a copy. Git configuration that gh
reaches through HOME, XDG_CONFIG_HOME or the system git configuration, such as a
url.<base>.insteadOf rewrite or a remote.<name>.gh-resolved setting, can still
redirect the repository that gh infers; passing --repo avoids that inference.
The inferred repository comes from gh repo view run in that directory, so it
depends on the local git configuration of that clone and on which of its remotes
gh selects; passing --repo avoids that dependence too. Other gh configuration,
such as GH_CONFIG_DIR and GH_TOKEN, reaches gh unchanged; like the rest of the
caller environment it is trusted: PATH chooses python3 and gh, BASH_ENV runs
code before ci-status.sh, and an exported function such as python3 replaces what
ci-status.sh runs, so a planted ci-status.py can run and exit 0. --timeout,
--interval and --repo may each be given once; a second use is refused (exit 3).

Output is part of the result. A standard output or standard error that is
closed at start or not open for writing (bash, started with a standard stream
closed, can pass that descriptor on open read-only on its own script), a write
or flush that fails (a full device or a closed pipe), and any other unexpected
exception end the tool with exit 3, so a lost report is never read as a verdict
and a crash never reads as a failed check (exit 1). When output works, the exit
status is the verdict of main unchanged.

Usage:
  ci-status.py <sha>                     Report once and exit.
  ci-status.py <sha> --wait              Poll until the checks settle.
  ci-status.py <sha> --wait --timeout 600 --interval 20
  ci-status.py <sha> --repo owner/name   Override the inferred repository.
  ci-status.py [options] -- <sha>        A single -- ends option parsing.

Exit codes:
  0  every check passed, confirmed across two consecutive readings
  1  at least one check failed, was cancelled, or timed out
  2  checks are still running, or --wait hit its timeout
  3  the result could not be read, no checks exist, usage was wrong, or output
     failed
"""

from __future__ import annotations

try:
    import fcntl
    import json
    import os
    import re
    import signal
    import subprocess
    import sys
    import tempfile
    import time
except Exception:  # an import failure must never read as a verdict (exit 1)
    raise SystemExit(3)

PASSING_CONCLUSIONS = {"success", "neutral", "skipped"}
# The largest --timeout or --interval accepted, in seconds (1 day). Each value
# becomes a subprocess timeout and a sleep; this bound keeps both far inside the
# limits that raise OverflowError (about 2147483 seconds for a millisecond poll).
MAX_SECONDS = 86400
MAX_DIGITS = len(str(MAX_SECONDS))  # rejects a long digit string before int()
FULL_SHA = re.compile(r"[0-9A-Fa-f]{40}")
REPO_NAME = re.compile(r"[A-Za-z0-9-]+/(?!\.)[A-Za-z0-9._-]+")
SHA_HINT = "pass the full 40-character sha (for example from git rev-parse or gh pr view --json headRefOid)"
GH_REDIRECTS = ("GH_REPO", "GH_HOST")  # removed with every GIT_ variable before each gh call
TOOL_DIR = os.path.dirname(os.path.realpath(__file__))  # every gh call runs here


def die(message: str) -> "NoReturn":  # type: ignore[name-defined]
    sys.stderr.write(f"ci-status: {message}\n")
    sys.exit(3)


class Unreadable(Exception):
    """A reading that cannot be trusted: a transport error or a malformed payload."""


def parse_args(argv):
    sha = repo = None
    wait = False
    timeout = 900
    interval = 15
    options_ended = False
    given = set()  # --timeout, --interval and --repo seen so far
    it = iter(argv)
    for arg in it:
        if options_ended or not arg.startswith("-"):
            if sha is not None:
                die("more than one commit given")
            sha = arg
        elif arg == "--":
            # A single -- ends option parsing; any later value, a second -- included,
            # is taken as the commit.
            options_ended = True
        elif arg == "--wait":
            wait = True
        elif arg in ("--timeout", "--interval", "--repo"):
            # A repeated option would silently replace the earlier value.
            if arg in given:
                die(f"more than one {arg} given")
            given.add(arg)
            if arg == "--timeout":
                timeout = _whole("--timeout", next(it, ""))
            elif arg == "--interval":
                interval = _whole("--interval", next(it, ""))
            else:
                repo = _repo_name(next(it, ""), "--repo")
        else:
            die(f"unknown option {arg}")
    if sha is None:
        die("usage: ci-status.py [--wait] [--timeout N] [--interval N] [--repo owner/name] [--] <sha>")
    if interval <= 0:
        die("--interval must be above zero")
    return _commit_name(sha), repo, wait, timeout, interval


def _commit_name(value: str) -> str:
    """Accept only a full 40-character hexadecimal sha, folded to lower case. Every
    other value is refused, so an abbreviation is never resolved, a moving ref is
    never read as a fixed commit, and the API path is built only from hex digits."""
    if not (value.isascii() and FULL_SHA.fullmatch(value)):
        die(f"{ascii(value)} is not a full 40-character commit sha; {SHA_HINT}")
    return value.lower()


def _repo_name(value: str, source: str) -> str:
    """Accept only owner/name with GitHub-safe characters, so the value cannot add a
    path segment or a query to the API call."""
    if not (value.isascii() and REPO_NAME.fullmatch(value)):
        die(f"{source} {ascii(value)} is not owner/name; pass --repo owner/name")
    return value


def _whole(flag: str, value: str) -> int:
    # Digit-only and at most MAX_SECONDS, so the value can never overflow a sleep
    # or a subprocess timeout. The length check runs first, so int() never sees a
    # long string.
    if not value or not (value.isascii() and value.isdigit()):
        # str.isdigit() is true for non-ASCII digits (e.g. superscripts) that int()
        # then rejects, so require ASCII digits and never let int() raise.
        die(f"{flag} takes whole seconds")
    if len(value) > MAX_DIGITS or int(value) > MAX_SECONDS:
        die(f"{flag} is out of range (at most {MAX_SECONDS} seconds)")
    return int(value)


def _gh(args, timeout: float):
    """Run gh in the directory that holds this file, resolved through symlinks, with
    GH_REPO, GH_HOST and every GIT_ variable removed from its environment, so an
    ambient value cannot point the repository lookup or the API call elsewhere.

    The child is reaped here with os.waitpid rather than through subprocess,
    because CPython subprocess reads a lost exit status (ECHILD from the wait) as
    exit 0. A status that cannot be observed raises ChildProcessError, an OSError,
    and an end other than a normal exit gives returncode -1, so neither can read
    as success. Output goes to unnamed temporary files, so gh never blocks on a
    full pipe while it is polled. OSError and TimeoutExpired reach the caller."""
    env = {
        k: v for k, v in os.environ.items()
        if not (k.startswith("GIT_") or k in GH_REDIRECTS)
    }
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(["gh", *args], cwd=TOOL_DIR, env=env, stdout=out, stderr=err)
        end = time.monotonic() + timeout
        while True:
            try:
                pid, status = os.waitpid(proc.pid, os.WNOHANG)
            except ChildProcessError as exc:
                proc.returncode = -1  # the child is gone; Popen must not wait for it
                raise ChildProcessError("the exit status of gh was lost") from exc
            if pid == proc.pid:
                break
            if time.monotonic() >= end:
                os.kill(proc.pid, signal.SIGKILL)
                try:
                    os.waitpid(proc.pid, 0)
                except ChildProcessError:
                    pass
                proc.returncode = -1
                raise subprocess.TimeoutExpired(proc.args, timeout)
            time.sleep(0.02)
        code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
        proc.returncode = code
        out.seek(0)
        err.seek(0)
        return subprocess.CompletedProcess(proc.args, code, out.read(), err.read())


def infer_repo(timeout: float) -> str:
    if timeout <= 0:
        return die("could not infer the repository; pass --repo owner/name")
    try:
        proc = _gh(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], timeout)
    except (OSError, subprocess.TimeoutExpired):
        return die("could not infer the repository; pass --repo owner/name")
    if proc.returncode != 0:
        return die("could not infer the repository; pass --repo owner/name")
    try:
        out = proc.stdout.decode("utf-8").strip()
    except UnicodeDecodeError:
        return die("could not read the repository name")
    if not out:
        die("could not infer the repository; pass --repo owner/name")
    return _repo_name(out, "the inferred repository")


def _no_duplicate_keys(pairs):
    """A JSON object hook that rejects duplicate keys rather than silently keeping the
    last, so a crafted response cannot hide a member (a failing run behind a second
    check_runs, an external slug behind a second slug) from the reading."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON key {key!r}")
        obj[key] = value
    return obj


def _iter_json_values(text: str):
    """Yield each top-level JSON value in text; gh --paginate concatenates one per page."""
    decoder = json.JSONDecoder(object_pairs_hook=_no_duplicate_keys)
    idx, n = 0, len(text)
    while idx < n:
        while idx < n and text[idx].isspace():
            idx += 1
        if idx >= n:
            break
        obj, idx = decoder.raw_decode(text, idx)
        yield obj


def _field(value, allow_empty: bool, field: str):
    """A field must be a string. null is allowed only for a nullable field (becomes '');
    a bool or number is rejected (a bool is not a valid string even though `x or ''`
    would hide it); an empty string is rejected for a required field. Anything else
    makes the whole reading fail-closed. Each message names FIELD."""
    if value is None:
        if allow_empty:
            return ""
        raise Unreadable(f"missing required field {field}")
    if isinstance(value, bool) or not isinstance(value, str):
        raise Unreadable(f"non-string check field {field}")
    if value == "" and not allow_empty:
        raise Unreadable(f"empty required field {field}")
    try:
        # A lone surrogate is a valid str but cannot be encoded or printed; reject it
        # so it fails closed here rather than crashing the report later.
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise Unreadable(f"check field {field} is not encodable text") from exc
    return value


def read_checks(repo: str, full_sha: str, deadline: float):
    """One read. Returns the list of checks, or raises Unreadable, fail-closed. The gh
    child is bounded by the time left to the deadline, so a hung or slow read cannot
    outlast the wait window."""
    remaining = deadline - time.time()
    if remaining <= 0:
        raise Unreadable("the wait window closed before the read")
    try:
        proc = _gh(["api", f"repos/{repo}/commits/{full_sha}/check-runs", "--paginate"], remaining)
    except subprocess.TimeoutExpired as exc:
        raise Unreadable(f"gh api did not return within {int(remaining)} seconds") from exc
    except OSError as exc:
        raise Unreadable(f"could not run gh: {exc}") from exc
    if proc.returncode != 0:
        sys.stderr.write(f"ci-status: could not read checks for {full_sha} in {repo}\n")
        sys.stderr.buffer.write(proc.stderr)
        raise Unreadable("gh api failed")
    try:
        stdout = proc.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        # Malformed transport output is unreadable, not a verdict; exit 1 is reserved
        # for an actual failed check.
        raise Unreadable(f"check-runs payload is not valid UTF-8: {exc}") from exc

    checks = []
    try:
        pages = list(_iter_json_values(stdout))
    except (ValueError, RecursionError) as exc:
        # JSONDecodeError and a duplicate-key ValueError are both ValueError;
        # RecursionError comes from a deeply nested payload. All are a malformed
        # reading, not a verdict, so fail closed.
        raise Unreadable(f"unparseable check-runs payload: {exc!r}") from exc

    # Disclosed residual (per rules/aiqt/10-ACCUR-disclose-guard-residuals): the
    # completeness guards below (total_count agreement, and unique integer check-run
    # ids) assume an HONEST gh transport and are best-effort against a fabricated one.
    # A fully forged or MITM'd response can omit total_count entirely and give every
    # run no id, in which case a padded or truncated body is not caught here. This is
    # accepted, not fixed: a dishonest transport can return a clean green for any
    # commit regardless, so it lies outside this gate's trust boundary (an authentic
    # gh talking to the real API, which always supplies total_count and unique ids).
    # A run that omits head_sha is likewise accepted on the strength of the API path
    # alone.
    declared_total = None
    total_present = None
    seen_ids = set()
    for page in pages:
        if not isinstance(page, dict):
            raise Unreadable("check-runs page is not an object")
        # The API reports the same total on every page. Its presence must be
        # consistent across pages, an explicit null is malformed, and when present it
        # must equal the runs actually received, so a truncated page cannot pass.
        has_total = "total_count" in page
        if total_present is None:
            total_present = has_total
        elif total_present != has_total:
            raise Unreadable("check-runs pages are inconsistent on total_count")
        if has_total:
            total = page["total_count"]
            if not isinstance(total, int) or isinstance(total, bool) or total < 0:
                raise Unreadable("check-runs total_count is not a whole number")
            if declared_total is None:
                declared_total = total
            elif declared_total != total:
                raise Unreadable("check-runs pages disagree on total_count")
        runs = page.get("check_runs")
        if not isinstance(runs, list):
            raise Unreadable("check_runs is not an array")
        for run in runs:
            if not isinstance(run, dict):
                raise Unreadable("a check run is not an object")
            # Each check run has a unique id; a duplicate would let a padded response
            # match total_count while hiding a distinct run.
            run_id = run.get("id")
            if run_id is not None:
                if not isinstance(run_id, int) or isinstance(run_id, bool):
                    raise Unreadable("check run id is not an integer")
                if run_id in seen_ids:
                    raise Unreadable("duplicate check run id")
                seen_ids.add(run_id)
            app = run.get("app")
            if app is None:
                slug = None
            elif isinstance(app, dict):
                slug = app.get("slug")
            else:
                raise Unreadable("check run app is not an object")
            # A run of another commit cannot come from an honest read of this
            # commit's check-runs path, so it is a transport anomaly, never a
            # verdict. A present head_sha must be a non-empty string that names the
            # requested commit; absence is tolerated (see the residual above).
            if "head_sha" in run:
                head = _field(run["head_sha"], allow_empty=False, field="head_sha")
                if head.lower() != full_sha:
                    raise Unreadable(f"check run head_sha {head!r} is not the requested commit {full_sha}")
            checks.append({
                "status": _field(run.get("status"), allow_empty=False, field="status"),
                "conclusion": _field(run.get("conclusion"), allow_empty=True, field="conclusion"),
                "name": _field(run.get("name"), allow_empty=True, field="name"),
                "slug": _field(slug, allow_empty=True, field="app.slug"),
            })
    if declared_total is not None and declared_total != len(checks):
        raise Unreadable(
            f"check-runs declared {declared_total} runs but the reading received {len(checks)}"
        )
    return checks


def verdict_of(checks) -> str:
    if not checks:
        return "none"
    failed = pending = 0
    for c in checks:
        if c["status"] != "completed":
            pending += 1
        elif c["conclusion"] not in PASSING_CONCLUSIONS:
            failed += 1
    if failed:
        return "fail"
    if pending:
        return "pending"
    return "pass"


# The checks this repository runs on every pull request and every push to main,
# and on which this tool insists: the 3 github-actions jobs Plugin manifests, Skill
# discovery and Agent Plugins manifest, and the external Cloudflare Pages build,
# which CLAUDE.md names as the check GitHub requires today. The tool insists on the
# 3 Actions jobs ahead of the branch ruleset listing them. A passing reading missing
# any of them means that check has not registered yet (or the head carries a skip
# marker, or the branch is malformed), so it is not green until all are present.
# Each Actions job is matched by its exact display name together with the
# github-actions app slug, so a run of the same name from another app, or an
# unnamed github-actions job, never satisfies one. The Cloudflare app slug is
# "cloudflare-workers-and-pages" on this repository, so it is matched by the
# "cloudflare" prefix to stay robust to Cloudflare's app naming; its name is not
# consulted.
# Residual: a name and an app cannot tell which workflow produced a run, so a pull
# request that deletes one of those workflows and adds another job with the same
# display name satisfies the check. GitHub's own app-pinned required check has the
# same limit.
# Deferred follow-up (after backlog row 68): this list is declared here and is not
# cross-checked against the branch ruleset for main. That cross-check would also
# require every context the ruleset lists, report a listed context missing from
# this list, and fail closed (exit 3) when the ruleset cannot be read.
def _actions_job(name: str):
    return lambda c: c["slug"] == "github-actions" and c["name"] == name


REQUIRED_CHECKS = (
    ("Plugin manifests", _actions_job("Plugin manifests")),
    ("Skill discovery", _actions_job("Skill discovery")),
    ("Agent Plugins manifest", _actions_job("Agent Plugins manifest")),
    ("Cloudflare Pages", lambda c: c["slug"].startswith("cloudflare")),
)


def missing_required(checks) -> list:
    return [label for label, matches in REQUIRED_CHECKS if not any(matches(c) for c in checks)]


def snapshot(checks) -> str:
    """A canonical, order-independent identity for a set of checks."""
    return json.dumps(
        sorted((c["status"], c["conclusion"], c["name"], c["slug"]) for c in checks)
    )


def report(checks, stream=sys.stdout) -> None:
    for c in checks:
        state = c["conclusion"] if c["status"] == "completed" else c["status"]
        stream.write(f"  {c['name']:<28} {state}\n")


def main() -> int:
    full_sha, repo, wait, timeout, interval = parse_args(sys.argv[1:])
    # Create the deadline before the preflight call so every child read, including
    # gh repo view, is bounded by the wait window.
    deadline = time.time() + timeout
    # The sha is printed before any gh call, so the caller sees which commit is read
    # even when the repository lookup fails.
    sys.stdout.write(f"ci-status: reading checks for commit {full_sha}\n")
    sys.stdout.flush()
    if not repo:
        repo = infer_repo(deadline - time.time())
    sys.stdout.write(f"ci-status: repository {repo}\n")
    sys.stdout.flush()

    confirming = False
    confirmed_snapshot = None
    confirm_rounds = 0

    def nap() -> bool:
        """Sleep up to one interval, never past the deadline. False if the window closed."""
        left = deadline - time.time()
        if left <= 0:
            return False
        time.sleep(min(interval, left))
        return True

    last_checks = None
    last_read_ok = False
    while True:
        # In wait mode, once the deadline has passed, do not start another read: if
        # the last read SUCCEEDED and the checks were still unsettled, that is a
        # timeout (exit 2), not a fresh unreadable read. If the last read was failing,
        # fall through so the read-failure path reports it (exit 3). The first
        # iteration always reads (last_read_ok is False).
        if wait and last_read_ok and time.time() >= deadline:
            sys.stderr.write(f"ci-status: still unsettled after {timeout} seconds; giving up\n")
            report(last_checks, sys.stderr)
            return 2
        try:
            checks = read_checks(repo, full_sha, deadline)
        except Unreadable as exc:
            last_read_ok = False
            # A failed or malformed read breaks any confirmation in progress and is
            # never a verdict; it is also not a changing check set, so it does not
            # count toward the changing-set cap. In wait mode keep waiting to the
            # deadline (a release step calls this after publishing, so a false abort
            # strands it).
            confirming = False
            confirm_rounds = 0
            if wait and time.time() < deadline:
                sys.stderr.write(
                    f"ci-status: check read failed ({exc}); retrying, "
                    f"{int(deadline - time.time())} seconds left\n"
                )
                if nap():
                    continue
            sys.stderr.write(f"ci-status: check read failed for {full_sha}: {exc}\n")
            return 3

        last_checks = checks
        last_read_ok = True
        verdict = verdict_of(checks)
        missing = missing_required(checks)
        if verdict == "pass" and missing:
            verdict = "pending"
            sys.stderr.write(
                f"ci-status: required check(s) {', '.join(missing)} not registered for "
                f"{full_sha} though they run on every PR and push here; not green\n"
            )
        if verdict != "pass":
            confirming = False
            confirmed_snapshot = None
            confirm_rounds = 0

        if verdict == "pass":
            snap = snapshot(checks)
            if confirmed_snapshot is not None and snap == confirmed_snapshot:
                if confirming:
                    if wait and time.time() >= deadline:
                        sys.stderr.write(
                            f"ci-status: checks passed but only after the {timeout} "
                            "second wait window closed\n"
                        )
                        report(checks, sys.stderr)
                        return 2
                    sys.stdout.write(
                        f"ci-status: every check passed for {full_sha}, confirmed on two readings\n"
                    )
                    report(checks)
                    return 0
                confirming = True
            else:
                confirm_rounds += 1
                # In wait mode the deadline bounds a never-settling set, so the
                # changing-set cap only applies to the bounded non-wait reads.
                if not wait and confirm_rounds > 5:
                    sys.stderr.write(
                        f"ci-status: the set of checks kept changing across {confirm_rounds} "
                        "readings; not calling this green\n"
                    )
                    report(checks, sys.stderr)
                    return 2
                confirmed_snapshot = snap
                confirming = True
            sys.stdout.write(
                "ci-status: all checks pass; re-reading to confirm none is still registering\n"
            )
            report(checks)
            if wait and not nap():
                sys.stderr.write(
                    f"ci-status: the {timeout} second wait window closed before the "
                    "confirmation reading\n"
                )
                report(checks, sys.stderr)
                return 2
            if not wait:
                time.sleep(interval)
            continue

        if verdict == "fail":
            sys.stdout.write(f"ci-status: a check did not pass for {full_sha}\n")
            report(checks)
            return 1

        if verdict == "none":
            if wait and time.time() < deadline:
                sys.stderr.write(
                    f"ci-status: no checks recorded yet for {full_sha}; waiting, "
                    f"{int(deadline - time.time())} seconds left\n"
                )
                if nap():
                    continue
                sys.stderr.write(
                    f"ci-status: no checks ever registered for {full_sha} within {timeout} seconds\n"
                )
            else:
                sys.stderr.write(f"ci-status: no checks are recorded for {full_sha} in {repo}\n")
                sys.stderr.write("ci-status: treating absent checks as unreadable, not as a pass\n")
            return 3

        # pending (still running, or a downgraded pass awaiting a required check)
        if not wait:
            sys.stdout.write(f"ci-status: checks are still running for {full_sha}\n")
            report(checks)
            return 2
        if time.time() >= deadline:
            sys.stderr.write(f"ci-status: still unsettled after {timeout} seconds; giving up\n")
            report(checks, sys.stderr)
            return 2
        sys.stdout.write(f"ci-status: waiting, {int(deadline - time.time())} seconds left\n")
        report(checks)
        nap()


def _note(message: str) -> None:
    """Write a message to standard error, ignoring any failure to do so."""
    try:
        sys.stderr.write(message)
        sys.stderr.flush()
    except Exception:  # the stream itself may be the failure being reported
        pass


def _writable(stream) -> bool:
    """True when the stream exists and its descriptor is open for writing."""
    if stream is None:
        return False
    try:
        mode = fcntl.fcntl(stream.fileno(), fcntl.F_GETFL) & os.O_ACCMODE
    except (OSError, ValueError, AttributeError):
        return False
    return mode in (os.O_WRONLY, os.O_RDWR)


def run() -> int:
    """Run main and return its exit status, or 3 when output fails or an
    unexpected exception escapes, so neither can become a verdict."""
    # An inherited ignored SIGCHLD makes the kernel reap each gh child, so its
    # exit status reads as 0. Restore the default before any subprocess runs.
    try:
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    except (OSError, ValueError):
        _note("ci-status: cannot reset SIGCHLD, so a gh exit status could be lost\n")
        return 3
    if not (_writable(sys.stdout) and _writable(sys.stderr)):
        _note("ci-status: standard output or standard error cannot be written\n")
        return 3
    try:
        code = main()
    except SystemExit as exc:
        code = exc.code
    except Exception as exc:
        _note(f"ci-status: unexpected error ({type(exc).__name__}: {exc}); treating the result as unreadable\n")
        return 3
    if not isinstance(code, int) or isinstance(code, bool):
        return 3
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            return 3
    return code


if __name__ == "__main__":
    # os._exit skips the interpreter shutdown flush, whose failure would otherwise
    # replace the status with 120; run has already flushed both streams.
    os._exit(run())
