#!/usr/bin/env python3
"""Report the CI verdict for one commit, exiting non-zero unless every check passed.

The verdict comes from the check-runs API, the only endpoint that sees every
required check: the Cloudflare Pages build (this repository's required check per
CLAUDE.md) is produced by an external app, not GitHub Actions, so a gate built on
actions/runs alone would pass while the required check was failing. The legacy
commits/<sha>/status endpoint is not used either: this repository publishes no
commit statuses, so it answers "pending" forever.

Reading is FAIL-CLOSED. The whole paginated response is parsed as JSON; a page
that is not an object, a check_runs that is not a list, a check that is not an
object, or any field of the wrong type (a status that is not a non-empty string,
a conclusion/name/slug that is neither a string nor null) makes the entire reading
unreadable. Absence of checks, an unreadable read, and a partial reading are never
success, so a caller waiting for green never mistakes silence, a malformed page, or
a dropped record for a pass. This replaces an earlier shell implementation that
serialized checks to delimited text and parsed them in bash, which repeatedly let a
crafted or malformed field forge or hide a check; parsing structured JSON here
removes that class of defect.

A pass is never declared on one reading: an external app can report before GitHub
Actions has created its runs, and a read taken in that window sees only the checks
that exist and calls them "every check" (a false green observed on a pull request
whose Actions gates had not started). So a pass is confirmed only when two
consecutive readings have the identical set of checks and conclusions. This costs
one interval on every green result, whether or not --wait was given.

This repository runs, on every pull request and every push to main, the
github-actions app (plugin-validate, sitemap) and the external Cloudflare Pages
build, which CLAUDE.md names as the required check. A passing reading missing either
of those means that check has not registered (a malformed branch, or the external
check still building); such a reading is downgraded from pass to pending, never to a
red. A commit that legitimately ran neither is a safe false-red, never a
false-green. Pointing --repo at a repository that does not run both unconditionally
would downgrade a legitimate green to pending.

Usage:
  ci-status.py <sha>                     Report once and exit.
  ci-status.py <sha> --wait              Poll until the checks settle.
  ci-status.py <sha> --wait --timeout 600 --interval 20
  ci-status.py <sha> --repo owner/name   Override the inferred repository.

Exit codes:
  0  every check passed, confirmed across two consecutive readings
  1  at least one check failed, was cancelled, or timed out
  2  checks are still running, or --wait hit its timeout
  3  the result could not be read, no checks exist, or usage was wrong
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

PASSING_CONCLUSIONS = {"success", "neutral", "skipped"}
MAX_DIGITS = 9  # keeps a timeout/interval well inside a machine int, rejecting overflow


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
    it = iter(argv)
    for arg in it:
        if arg == "--wait":
            wait = True
        elif arg == "--timeout":
            timeout = _whole("--timeout", next(it, ""))
        elif arg == "--interval":
            interval = _whole("--interval", next(it, ""))
        elif arg == "--repo":
            repo = next(it, "") or die("--repo takes owner/name")
        elif arg.startswith("-"):
            die(f"unknown option {arg}")
        elif sha is None:
            sha = arg
        else:
            die("more than one commit given")
    if not sha:
        die("usage: ci-status.py <sha> [--wait] [--timeout N] [--interval N] [--repo owner/name]")
    if interval <= 0:
        die("--interval must be above zero")
    return sha, repo, wait, timeout, interval


def _whole(flag: str, value: str) -> int:
    # Digit-only, and short enough that it cannot overflow into unrelated
    # semantics. int() itself is unbounded, so the length bound is the real guard.
    if not value or not (value.isascii() and value.isdigit()):
        # str.isdigit() is true for non-ASCII digits (e.g. superscripts) that int()
        # then rejects, so require ASCII digits and never let int() raise.
        die(f"{flag} takes whole seconds")
    if len(value) > MAX_DIGITS:
        die(f"{flag} is out of range")
    return int(value)


def infer_repo(timeout: float) -> str:
    if timeout <= 0:
        return die("could not infer the repository; pass --repo owner/name")
    try:
        proc = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
            capture_output=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return die("could not infer the repository; pass --repo owner/name")
    if proc.returncode != 0:
        return die("could not infer the repository; pass --repo owner/name")
    try:
        out = proc.stdout.decode("utf-8").strip()
    except UnicodeDecodeError:
        return die("could not read the repository name")
    return out or die("could not infer the repository; pass --repo owner/name")


def resolve_sha(sha: str, timeout: float) -> str:
    # Bounded and byte-decoded like read_checks; a hung or non-UTF-8 git must not
    # block or crash, so an unresolvable ref simply falls back to the given sha.
    if timeout <= 0:
        return sha
    try:
        proc = subprocess.run(
            ["git", "rev-parse", sha], capture_output=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return sha
    if proc.returncode != 0:
        return sha
    try:
        return proc.stdout.decode("utf-8").strip() or sha
    except UnicodeDecodeError:
        return sha


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


def _field(value, allow_empty: bool):
    """A field must be a string. null is allowed only for a nullable field (becomes '');
    a bool or number is rejected (a bool is not a valid string even though `x or ''`
    would hide it); an empty string is rejected for a required field. Anything else
    makes the whole reading fail-closed."""
    if value is None:
        if allow_empty:
            return ""
        raise Unreadable("missing required field")
    if isinstance(value, bool) or not isinstance(value, str):
        raise Unreadable("non-string check field")
    if value == "" and not allow_empty:
        raise Unreadable("empty required field")
    try:
        # A lone surrogate is a valid str but cannot be encoded or printed; reject it
        # so it fails closed here rather than crashing the report later.
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise Unreadable("check field is not encodable text") from exc
    return value


def read_checks(repo: str, full_sha: str, deadline: float):
    """One read. Returns the list of checks, or raises Unreadable, fail-closed. The gh
    child is bounded by the time left to the deadline (at least one second), so a hung
    or slow read cannot outlast the wait window."""
    remaining = deadline - time.time()
    if remaining <= 0:
        raise Unreadable("the wait window closed before the read")
    try:
        proc = subprocess.run(
            ["gh", "api", f"repos/{repo}/commits/{full_sha}/check-runs", "--paginate"],
            capture_output=True, timeout=remaining,
        )
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
            checks.append({
                "status": _field(run.get("status"), allow_empty=False),
                "conclusion": _field(run.get("conclusion"), allow_empty=True),
                "name": _field(run.get("name"), allow_empty=True),
                "slug": _field(slug, allow_empty=True),
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


# The checks this repository runs on every pull request and every push to main: the
# github-actions app (plugin-validate, sitemap) and the external Cloudflare Pages
# build, which CLAUDE.md names as the required check. A passing reading that is
# missing either means that check has not registered yet (or the branch is
# malformed), so it is not green until both are present.
# Each required check is matched by its app slug, not its forgeable name. The
# github-actions app slug is exact; the Cloudflare app slug is
# "cloudflare-workers-and-pages" on this repository, so it is matched by the
# "cloudflare" prefix to stay robust to Cloudflare's app naming.
REQUIRED_CHECKS = (
    ("github-actions", lambda slug: slug == "github-actions"),
    ("Cloudflare Pages", lambda slug: slug.startswith("cloudflare")),
)


def missing_required(checks) -> list:
    slugs = {c["slug"] for c in checks}
    return [label for label, matches in REQUIRED_CHECKS if not any(matches(s) for s in slugs)]


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
    sha, repo, wait, timeout, interval = parse_args(sys.argv[1:])
    # Create the deadline before the preflight calls so every child read, including
    # gh repo view and git rev-parse, is bounded by the wait window.
    deadline = time.time() + timeout
    if not repo:
        repo = infer_repo(deadline - time.time())
    full_sha = resolve_sha(sha, deadline - time.time())

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

        # pending (still running, or a downgraded pass awaiting its github-actions check)
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


if __name__ == "__main__":
    sys.exit(main())
