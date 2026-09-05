#!/usr/bin/env python3
"""AIQT Guardrails enforcement hooks for Claude Code. Stdlib only, offline.

SOURCE tree copy: this file lives at .aiqt/core/hooks/scripts/aiqt_hooks.py and is copied
byte-identical into the generated plugin surface plugin/aiqt-guardrails-hooks/hooks/scripts/
aiqt_hooks.py by tools/gen_hooks.py; edit the source, never the generated copy. One dispatcher, one
handler function per control declared in .aiqt/core/hooks/manifest.toml:

  diff_wall_stop      Stop        cnsdif  surface (WARN) a unified-diff wall in the final assistant message
  diff_source_pretool PreToolUse  cnsdif  deny a Bash command that dumps a bare console diff
  commit_identity     PreToolUse  cmtidn  deny a git authoring command that names an AI identity
  absolute_paths      PreToolUse  abspth  deny a relative path where a typed-path tool requires absolute
  bash_absolute_paths PreToolUse  abspth  ask on a relative cd/pushd operand or redirect target in Bash
  git_discard         PreToolUse  prsunc  allow/ask/deny a git command that would discard uncommitted work
  branch_root         PreToolUse  brnrot  block branch creation from an orphaned start point
  gate_weakening      PreToolUse  gatdis  deny a git hook bypass; ask a swallowed or truncated checker
  commit_msg_subst    PreToolUse  sectvl  ask on shell substitution in a git commit argument
  secrets_shift_left  PreToolUse  secsec  deny a Write/Edit/MultiEdit/Bash writing an obvious hardcoded secret
  gensrc_guard        PreToolUse  gensrc  a Write/Edit/MultiEdit that hand-edits a registered generated artefact

Contract (doc-confirmed 2026-08-17 against code.claude.com/docs/en/hooks): the hook payload arrives
as JSON on stdin. A PreToolUse handler that decides emits, on exit 0,
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"|"deny",
"permissionDecisionReason": "..."}}; an allow decision is expressed as NO output (exit 0 silent), so
the user's own permission flow is never bypassed, and a deny decision blocks the tool. exit 2 is a
blocking error whose stderr is fed back to Claude. The Stop payload carries the final assistant text
as last_assistant_message (there is NO stop_hook_active field in the current Stop payload).

Error posture at the PreToolUse layer: FAIL CLOSED, for every control EXCEPT git_discard (whose
deliberate boundary posture is stated next), gensrc_guard (a second stated exception, below), and
commit_msg_subst (a third stated exception, below). A
fail-closed control that cannot read the input it is meant
to cover, or is invoked in a context it does not understand, DENIES rather than waving the action
through (per integ-check-fails-closed-on-unreadable): a missing tool_name, an unreadable command
string, or an unreadable required field all deny. A detected violation denies the same way. A clean
pass emits NO decision and exits 0 silently.

gensrc_guard (gensrc) is the SECOND stated exception: it is a registry-driven path ASK whose strongest
outcome on a confirmed violation is itself an ask (the human approving IS the opt-out), so every branch
it cannot clear fails SAFE to ASK rather than deny, because a branch that denied on uncertainty would
punish uncertainty harder than certainty. An unreadable, malformed, or unknown-version registry, an
unresolvable repo root, a target that canonicalizes outside the repo, and an unreadable payload field
all ASK; an absent registry is the inert ALLOW; and only a missing tool_name denies (the shared
fail-closed contract). The ASK still satisfies integ-check-fails-closed-on-unreadable in substance:
the failure surfaces as a gate the human must clear and can never read as clean.

commit_msg_subst (sectvl) is the THIRD stated exception: its strongest normal finding is an ASK, so a
missing or unreadable command string also fails safe to ASK rather than being punished more harshly than
a confirmed substitution. Only a missing tool_name denies under the shared fail-closed contract; a
mis-wired event still hard-blocks because no structured PreToolUse decision can safely be formed.

git_discard (prsunc) is a DELIBERATE, ULTRA-CONSERVATIVE "ask unless PRISTINE and provably clean" exception
to that fail-closed rule (EN-6). It has THREE outcomes: ALLOW (exit 0 silent), DENY, and ASK
(permissionDecision "ask", which prompts the human). UNLIKE the fail-closed controls above, it fails OPEN
(ALLOW) at the TRUE BOUNDARY - a non-Bash or absent tool, a malformed or missing tool_input.command it
cannot read as a discard, a non-git command, or no recognized lossy verb - because none of those is a
discard it can reason about, and it never silently allows a recognized WORKING-TREE-CONTENT discard (a
recognized verb in a genuinely non-destructive FORM - checkout -b, reset --soft, clean -n - preserves the
index and worktree content, though reset --soft still MOVES HEAD, a reflog-recoverable ref move, so it
discards no working-tree content and may ALLOW even on a dirty tree, as detailed below). That no-silent-allow
guarantee is bounded to WORKING-TREE CONTENT and is best-effort, not categorical: some ref-level moves (a
merged-branch delete, reset --soft moving HEAD) are reflog-recoverable, and the obfuscation/config residuals
disclosed below (a fragmented git command word or verb, a git alias, ambient config) can hide a discard the
lexical scan never sees. An UNPARSEABLE command
(unbalanced quote) is not a free pass, it is scanned raw for a lossy verb keyword and ASKS when one is
present. WITHIN scope (a recognized lossy verb: checkout/switch/restore/reset/clean/stash/
rm/branch) the outcome is ASK unless the command is a PRISTINE SINGLE BARE 'git <verb>' invocation AND the
tree is provably clean (or the leading opt-out is set, or the form is genuinely non-destructive). PRISTINE
SINGLE BARE means, PURELY LEXICALLY (the bash grammar is never parsed): after optional leading KEY=value
assignments the command is exactly 'git <args>' as ONE simple command, and the RAW string carries NO shell
metacharacter anywhere EVEN INSIDE QUOTES (none of ; | & < > ( ) { } $ backtick backslash ! newline, which
also rules out &&/||/|&, every redirection form, and every command/process substitution), no shell reserved
word, and a command word that is LITERALLY 'git' (not a path, not a wrapper such as sudo/nice/timeout/nohup/
env/command/exec/builtin/xargs/time/!/sh -c/bash -c). ANY shell metacharacter, wrapper, redirect, reserved
word, or second command makes the command not-pristine - a PURELY LEXICAL determination - and it ASKS
WITHOUT ever consulting the probe (a safe over-ask). An option the form-classifier cannot resolve is a
SEPARATE mechanism and does NOT bear on pristineness: a pristine command carrying an unresolved option still
reaches the probe, where its role routes to a scoped ASK, so it is not silently allowed either. A wrapper is
caught only while the raw scan still sees a contiguous git verb keyword, so 'any wrapper ASKS' is NOT
categorical (a wrapper that ALSO fragments the verb is a disclosed residual, below). Only a
metacharacter-free 'git <verb> <plain args>'
reaches the probe, where PROVABLY CLEAN means the read-only, config-forced porcelain probe (git -c
status.showUntrackedFiles=all status --porcelain --untracked-files=all, so a repo-local
status.showUntrackedFiles=no cannot hide an untracked file) reports NO tracked change AND NO untracked ('??')
entry (only an ignored '!!' entry counts as clean). A pristine bare whole-tree clobber (reset --hard,
checkout -f, switch --force/--discard-changes) on a probed-dirty tree DENIES; everything else in scope ASKS.
No recognized lossy verb that would discard WORKING-TREE CONTENT is silently ALLOWED except a pristine bare
'git <verb>' whose FORM is genuinely non-destructive (checkout -b, reset --soft, clean -n, which ALLOW even
on a dirty tree), or on a provably-clean tree, or a pristine bare form carrying the leading
GUARDRAIL_ALLOW_DISCARD=1 opt-out - worst case it ASKS, at the cost of more asks. This guarantee is bounded to
working-tree content: ref-level moves (reset --soft moving HEAD, a merged-branch delete) are reflog-
recoverable, and the obfuscation/config residuals below are best-effort, not categorical. The HONEST RESIDUAL a lexical hook cannot catch: a git alias or shell
function renaming git; deliberate token fragmentation or obfuscation of the COMMAND WORD 'git' ITSELF or of
the verb (a wrapper whose git command word or verb is SPLIT so neither the token scan nor the raw scan sees
a contiguous git+verb keyword, e.g. env git re'set' --hard, eval git re'set', or command g'it' reset --hard
/ env /usr/bin/g'it' reset --hard, whose raw string carries no contiguous 'git'+'reset', reads as 'no
recognized lossy verb' and is silently ALLOWED - a best-effort residual, not chased); a real discard whose
VERB is outside the recognized set AND the raw scan does NOT flag at all (a 'git worktree remove -f' of a
dirty linked worktree discards that worktree's uncommitted work, yet 'worktree' matches no lossy keyword, so
it is allowed at the true boundary - disclosed, not closed this round). A command the raw scan DOES flag as
in-scope whose resolved subcommand is nonetheless outside the recognized set ('git checkout-index -a -f',
'git read-tree -u --reset HEAD', flagged by their 'checkout'/'reset' substring) is NO LONGER silently
allowed: it ASKS (F-97), since a flagged sub the classifier cannot resolve to a known verb cannot be proven
non-destructive. A discard performed outside the Bash tool; or
persistent shell/config state; the deferred recovery/snapshot layer is the backstop. The one probe kept is
read-only and offline; it never mutates the repo.

Stop layer is a DELIBERATE exception, non-blocking by design (GD-24 tri-family QA, 2026-08-17,
flagged for Architect review): it SURFACES a diff wall with a strong systemMessage and exits 0 (WARN),
it does NOT hard-block. The wall has already rendered by Stop time, so blocking cannot unsend it; and
because there is no stop_hook_active field and no documented built-in loop bound, a hard exit-2 Stop
block could re-fire on the forced continuation and wedge the session. The hard PREVENTION for console
diffs lives in the PreToolUse diff_source layer at the command source; the Stop layer only surfaces.

This is enforced at the DISPATCHER, not left to the handler alone: main() reads each handler's event
class from HANDLER_EVENT (the argv mode, never the payload, which may be unreadable) and, for a
Stop/SubagentStop handler, converts EVERY error path (a bad argv count, unreadable/malformed stdin, a
JSON parse failure, a non-dict payload, or a handler crash) into a non-blocking systemMessage warning
on exit 0. No Stop invocation reaches exit 2 on an ERROR path; a Stop handler may still return exit 2 as a
DELIBERATE decision where the platform documents exit 2 as the block (the orchestration stop guard denies a
manufactured wind-down that way, doc-confirmed 2026-08-29, bounded by its own loop bound so it cannot wedge
the chain). Outside that deliberate deny, only a PreToolUse handler fails closed via exit 2, and only a
genuinely UNKNOWN mode (not in HANDLERS, an unidentifiable broken install) does so on a bad invocation.
"""
import collections
import datetime
import json
import math
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile

PRETOOL = "PreToolUse"
STOP_EVENTS = ("Stop", "SubagentStop")
# Events whose handlers must NEVER exit 2 on an ERROR path (a deliberate handler deny may still
# return 2 where the platform documents exit 2 as the block: Stop and TeammateIdle). SessionStart
# cannot block at all; an errored UserPromptSubmit stamp must never block a human prompt; a
# PostToolUse recorder error must surface as a warning, not a tool failure. Doc-confirmed 2026-08-29.
FAIL_OPEN_EVENTS = STOP_EVENTS + ("SessionStart", "TeammateIdle", "UserPromptSubmit", "PostToolUse")


# --- decision constructors ---------------------------------------------------------------------------
# A handler returns (exit_code, stdout_obj_or_None, stderr_text_or_None). The dispatcher prints the
# stdout object as JSON when present, prints the stderr text when present, and exits with the code.

def _allow():
    """A clean pass: no decision at all (never an explicit allow, which would bypass the user's own
    permission flow), exit 0 silent."""
    return (0, None, None)


def _deny(reason, banner):
    """A PreToolUse block: permissionDecision deny on exit 0, honoured by the platform."""
    return (0, {"hookSpecificOutput": {"hookEventName": PRETOOL,
                                       "permissionDecision": "deny",
                                       "permissionDecisionReason": reason},
                "systemMessage": banner},
            None)


def _ask(reason, banner):
    """A PreToolUse ASK: permissionDecision ask on exit 0, which prompts the human to confirm rather
    than blocking outright. The recoverable middle of the git_discard three-outcome posture (allow /
    ask / deny): used when a recognized lossy verb cannot be PROVEN safe but is not confirmed lossy."""
    return (0, {"hookSpecificOutput": {"hookEventName": PRETOOL,
                                       "permissionDecision": "ask",
                                       "permissionDecisionReason": reason},
                "systemMessage": banner},
            None)


def _stop_warn(banner):
    """A Stop surfacing WARN: exit 0 with a systemMessage banner and NOTHING blocking. Every Stop
    outcome that WARNS (a guard's own I/O error, or a loop-bound-relieved forced exit) uses this, so the
    warn path can never wedge a turn chain; a DELIBERATE Stop deny returns exit 2 directly (see the
    module docstring's design note)."""
    return (0, {"systemMessage": banner}, None)


def _hard_block(message):
    """A fail-closed hard block where no structured decision can be formed (a mis-wired PreToolUse
    event): exit 2 with the diagnostic on stderr, so a broken guard blocks rather than silently
    passing. The Stop handlers do not use this constructor: their ERROR paths warn (exit 0), while a
    DELIBERATE Stop deny returns exit 2 directly (the orchestration stop guard, not warn-only)."""
    return (2, None, message)


def _deny_missing_tool_name(rule):
    """Fail closed on a PreToolUse payload with no tool_name: it cannot be matched against, so it
    cannot be cleared. A present-but-different tool is handled separately (allow, defensive)."""
    return _deny("AIQT rule {} (fail-closed): malformed payload: missing tool_name.".format(rule),
                 "AIQT guardrail: denied a PreToolUse call with no tool_name (rule {}, fail-closed)."
                 .format(rule))


# --- shared raw-command tokenizer (quote/redirect-aware) ---------------------------------------------
# ONE raw-character lexical pass over the Bash command, shared by every lexical Bash hook (diff-source,
# commit-identity, protected-line, gate-weakening, and git-discard's lossy scan). It decides quoting and
# REDIRECTION from RAW character positions and quote provenance BEFORE any token stream exists, so a shell
# redirection ANYWHERE in a command (leading, interspersed, or trailing: 'git >/dev/null commit', '>out
# pytest') is recorded as redirect metadata and REMOVED from the argv the handlers judge, closing the
# post-tokenize redirect-pollution class shared across the hooks. A naive post-tokenize strip was proven
# unsafe (a quoted '>' or a numeric option value was over-stripped into a silent allow, prtbrn round-10
# revert), so the strip happens HERE, from raw positions, where quote provenance and fd adjacency are still
# visible - never reconstructed from already-tokenized words.
#
# It is a LEXER, not a shell parser: it models the recognized redirection and separator grammar and, for
# any construct it does not model - a heredoc ('<<'/'<<-'), a here-string ('<<<'), a process substitution
# ('<('/'>('), a '{fd}>' redirect, a malformed or unterminated redirect, an unbalanced quote or escape,
# or a NUL - it RAISES ValueError so the caller falls back to its conservative raw scan rather than
# returning partial argv (never a partially-cleaned command). An expansion or command substitution ('$',
# '$( )', backtick) or a glob/brace/tilde is not modelled either: it marks the segment OPAQUE (the same
# residual the earlier tokenizer disclosed), so no diff-source ALLOW proof can rest on it.
_SEGMENT_OPERATORS = frozenset((";", "|", "|&", "||", "&&", "&", "(", ")"))
_METACHARS = "<>|&;()"  # unquoted, unescaped: begin an operator (redirect or separator)
# An unquoted expansion/substitution/glob/brace makes a word (and its segment) OPAQUE: no summary/file/pager
# proof may rest on it. A LEADING '~' is tilde expansion; a mid-word '~' is literal (HEAD~1), handled below.
_OPAQUE_WORD_CHARS = frozenset(("$", "`", "*", "?", "[", "{"))
_FD_VAR_RE = re.compile(r"^\{[A-Za-z_][A-Za-z0-9_]*\}$")  # a bash {varname}> fd-var redirect (unsupported)

# A redirect record: op (the operator text), src_fd (the effective source fd, or None for the both-streams
# '&>' forms), target (the decoded target word), target_class (static-real 'file-real', a console/device
# 'file-dev' under /dev or /proc, a numeric/'-' 'descriptor', or a dynamic 'opaque'), stdout_effect
# (what this redirect does to STDOUT: '' none, or 'file-real'/'file-dev'/'descriptor'/'opaque'), and
# target_leading_tilde (True only when the target begins with an UNQUOTED, whole-prefix-unquoted '~' that
# bash tilde-expands AND that expansion is a current-user '~'/'~/x', so the target is absolute like $HOME;
# the abspth Bash floor reads it so a '> ~/x' redirect is ALLOW-consistent with a 'cd ~/x' destination).
_Redirect = collections.namedtuple(
    "_Redirect", ("op", "src_fd", "target", "target_class", "stdout_effect", "target_leading_tilde"))
# A segment record: argv (the quote-decoded words the program receives, REDIRECTION ABSENT), sep_after (the
# operator that ended it, one of _SEGMENT_OPERATORS, or "" at a newline/command end), redirects (the ordered
# redirect records), raw (the raw slice of this segment), opaque_shell (True when the segment carried an
# unquoted expansion/substitution/glob/brace/tilde that no ALLOW proof may rest on), argv_opaque (the
# per-token opacity flags PARALLEL to argv: True where THAT word carried an unquoted expansion/glob/brace or
# a leading tilde, so a consumer can tell an unquoted, shell-expanded '~/x' from a quoted, literal '~/x'),
# and argv_leading_tilde (the per-token flags PARALLEL to argv: True ONLY where THAT word begins with an
# UNQUOTED tilde AND the WHOLE tilde-prefix - '~' up to the first unquoted '/' or end of word - is unquoted
# and unescaped, which is exactly when bash tilde-expansion applies and the word expands to an absolute home.
# This is a STRICTER signal than argv_opaque, which any unquoted expansion/glob/brace ANYWHERE in the token
# also sets; a quoted leading tilde with an unquoted tail, e.g. "~"/x*, and a leading tilde whose PREFIX
# carries a quote or escape, e.g. ~"/x" or ~\/x, are correctly NOT read as an expanded '~').
_Segment = collections.namedtuple(
    "_Segment", ("argv", "sep_after", "redirects", "raw", "opaque_shell", "argv_opaque",
                 "argv_leading_tilde"))


def _read_word(command, i, n):
    """Read exactly ONE shell word starting at index i (which must be at a word character, never a space,
    newline, or metacharacter). Returns (text, opaque, started, all_digits, leading_tilde, new_i): text is
    the quote/escape decoded word, opaque is True if it carried an unquoted
    expansion/substitution/glob/brace/leading-tilde, started is True once any character (even an empty ''
    quote) began the word, all_digits is True only when the whole word is UNQUOTED decimal digits (an
    IO_NUMBER candidate), leading_tilde is True ONLY when the word begins with an UNQUOTED tilde AND the
    WHOLE tilde-prefix (from that '~' up to the first UNQUOTED '/' or end of word) is unquoted and unescaped,
    which is exactly when bash tilde-expansion applies. A quoted, escaped, or non-leading tilde does not set
    it, and neither does a quote or escape ANYWHERE in the tilde-prefix (e.g. ~"/x", ~'', or an escaped '/'
    after the tilde stay relative), while a quote or expansion AFTER the prefix-closing '/' (e.g. ~/$VAR) does
    not block it. Stops at an
    unquoted space, tab, newline, or metacharacter. Raises ValueError on an unbalanced quote or an
    unterminated escape."""
    chars = []
    opaque = False
    started = False
    all_digits = True
    leading_tilde = False
    # tilde_prefix_open: True while we are still INSIDE the tilde-prefix (from a leading unquoted '~' up to
    # the first UNQUOTED '/', or end of word). Bash expands the leading '~' ONLY when the WHOLE tilde-prefix
    # is unquoted and unescaped; any quoted or escaped character in that span disables expansion and the word
    # stays RELATIVE. So while the prefix is open, a single-quote, double-quote, or backslash escape CONTAMINATES
    # it: leading_tilde is cleared. An unquoted '/' CLOSES the prefix cleanly (leading_tilde stays set), so
    # material AFTER it - 'cd ~/$VAR' - never blocks the expansion.
    tilde_prefix_open = False
    while i < n:
        c = command[i]
        if c in " \t\n" or c in _METACHARS:
            break
        if c == "\\" and i + 1 < n and command[i + 1] == "\n":
            # A backslash-newline is a LINE CONTINUATION: it is removed entirely and does NOT start or
            # contribute to a word, so 'git \<newline> commit' is [git, commit], never [git, "", commit]
            # (a synthetic empty argv element that mis-set the subcommand and defeated the sibling guards).
            i += 2
            continue
        if c == "#" and not started:
            # A '#' still at a WORD BOUNDARY (the word has not begun) starts a comment, even when the
            # boundary was EXPOSED by a preceding continuation join ('git diff \<newline># > out.txt'):
            # break so the caller re-applies its end-of-line comment handling rather than reading '#' as a
            # literal word (which would tokenize a commented-out redirect/pipe and earn a false proof).
            # A mid-word '#' (started is True, e.g. ticket#123 or a continuation-joined di\<newline>ff#x)
            # is left literal below.
            break
        was_started = started  # whether the word had begun BEFORE this char (a leading tilde needs it False)
        started = True
        if c == "'":  # single quote: everything literal, no escapes, until the next "'"
            if tilde_prefix_open:  # a quote inside the tilde-prefix disables bash expansion: stays relative
                leading_tilde = False
                tilde_prefix_open = False
            j = command.find("'", i + 1)
            if j < 0:
                raise ValueError("unterminated single quote")
            chars.append(command[i + 1:j])
            all_digits = False
            i = j + 1
            continue
        if c == '"':  # double quote: backslash escapes only "\ $ ` and newline; $ and backtick are opaque
            if tilde_prefix_open:  # a quote inside the tilde-prefix disables bash expansion: stays relative
                leading_tilde = False
                tilde_prefix_open = False
            i += 1
            while True:
                if i >= n:
                    raise ValueError("unterminated double quote")
                d = command[i]
                if d == '"':
                    i += 1
                    break
                if d == "\\":
                    if i + 1 >= n:
                        raise ValueError("unterminated escape")
                    e = command[i + 1]
                    if e in '"\\$`':
                        chars.append(e)
                        i += 2
                        continue
                    if e == "\n":  # line continuation inside a double quote: both characters removed
                        i += 2
                        continue
                    chars.append("\\")  # a backslash before any other char is literal inside "..."
                    i += 1
                    continue
                if d in "$`":
                    opaque = True
                chars.append(d)
                i += 1
            all_digits = False
            continue
        if c == "\\":  # unquoted escape: the next character is literal (a backslash-newline continuation
            # was already consumed above, before the word could start)
            if tilde_prefix_open:  # an escape inside the tilde-prefix disables bash expansion: stays relative
                leading_tilde = False
                tilde_prefix_open = False
            if i + 1 >= n:
                raise ValueError("unterminated escape")
            chars.append(command[i + 1])
            all_digits = False
            i += 2
            continue
        # an ordinary unquoted character
        if c == "~" and not was_started:
            # A LEADING unquoted tilde is bash tilde-expansion (cwd-independent home): record it as such AND
            # mark the word opaque (no diff-source ALLOW proof may rest on the expanded value). Nothing has
            # begun the word before it, so an empty "" quote or any other char ahead of the '~' (""~, x~)
            # leaves was_started True and this branch is not taken - matching bash, which expands only a '~'
            # at the very start of the word.
            opaque = True
            leading_tilde = True
            tilde_prefix_open = True  # begin tracking the tilde-prefix; a later quote/escape voids the tilde
        elif c in _OPAQUE_WORD_CHARS:
            opaque = True
        elif c == "/" and tilde_prefix_open:
            # an UNQUOTED '/' ends the tilde-prefix cleanly: the leading '~' stays an expansion, and anything
            # after this '/' (an opaque '$VAR', a quote) no longer blocks it. 'cd ~/$VAR' remains an ALLOW.
            tilde_prefix_open = False
        if not c.isdigit():
            all_digits = False
        chars.append(c)
        i += 1
    return "".join(chars), opaque, started, all_digits, leading_tilde, i


def _match_operator(command, i, n):
    """Classify the operator at index i (a metacharacter). Returns (op, kind, length): kind is 'sep' for a
    segment separator, 'redirect' for a recognized redirection, or 'cannot' for an unsupported construct
    (a heredoc/here-string '<<', or a process substitution '<('/'>('). Longest-first: '&>>'/'&>' before '&',
    '>>'/'>|'/'>&' before '>', '<>'/'<&' before '<', '||'/'|&' before '|'."""
    c = command[i]
    nx = command[i + 1] if i + 1 < n else ""
    nx2 = command[i + 2] if i + 2 < n else ""
    if c == "&":
        if nx == ">":
            return ("&>>", "redirect", 3) if nx2 == ">" else ("&>", "redirect", 2)
        if nx == "&":
            return "&&", "sep", 2
        return "&", "sep", 1
    if c == ">":
        if nx == ">":
            return ">>", "redirect", 2
        if nx == "|":
            return ">|", "redirect", 2
        if nx == "&":
            return ">&", "redirect", 2
        if nx == "(":
            return ">(", "cannot", 2  # process substitution
        return ">", "redirect", 1
    if c == "<":
        if nx == "<":
            return "<<", "cannot", 2  # heredoc / here-string (<<, <<-, <<<)
        if nx == "(":
            return "<(", "cannot", 2  # process substitution
        if nx == ">":
            return "<>", "redirect", 2
        if nx == "&":
            return "<&", "redirect", 2
        return "<", "redirect", 1
    if c == "|":
        if nx == "|":
            return "||", "sep", 2
        if nx == "&":
            return "|&", "sep", 2
        return "|", "sep", 1
    return c, "sep", 1  # ';', '(', ')'


def _classify_redirect(op, src_fd, target, t_opaque, t_leading_tilde=False):
    """Build a _Redirect from a recognized operator, its explicit source fd (or None), the decoded target,
    and the target's clean-leading-tilde signal. Computes the target class and the effect on STDOUT
    (last-redirect-wins is applied by the caller). '&>'/'&>>' send both streams to the target (stdout
    affected); '>'/'>>'/'>|' affect stdout only when the effective source fd is 1; '>&' is fd
    duplication/close for a numeric or '-' target (descriptor, affecting stdout only from fd 1) or the csh
    both-streams-to-file form for a static word; the input forms '<'/'<>'/'<&' never touch stdout.
    tilde_abs is the ALREADY-GATED clean-tilde flag (an unquoted current-user '~'/'~/x' the shell expands to
    an absolute $HOME): it is stored on the record so the abspth floor allows such a target without
    re-deriving the gate, exactly as the cd/pushd destination path does."""
    tilde_abs = t_leading_tilde and bool(_LITERAL_TILDE_RE.match(target))
    if op in ("&>", "&>>"):
        tclass = _target_class(target, t_opaque)
        return _Redirect(op, None, target, tclass, tclass, tilde_abs)  # both streams -> stdout affected
    if op in (">", ">>", ">|"):
        src = 1 if src_fd is None else src_fd
        tclass = _target_class(target, t_opaque)
        return _Redirect(op, src, target, tclass, tclass if src == 1 else "", tilde_abs)
    if op == ">&":
        src = 1 if src_fd is None else src_fd
        if (not t_opaque) and (target == "-" or target.isdigit()):
            tclass = "descriptor"  # fd duplication or close, never a proven file
        else:
            tclass = _target_class(target, t_opaque)  # csh '>&file' both-streams-to-file form
        return _Redirect(op, src, target, tclass, tclass if src == 1 else "", tilde_abs)
    # input redirects ('<', '<>', '<&'): never a stdout effect
    src = 0 if src_fd is None else src_fd
    tclass = "descriptor" if op == "<&" else _target_class(target, t_opaque)
    return _Redirect(op, src, target, tclass, "", tilde_abs)


def _target_class(target, t_opaque):
    """Classify a redirect target: 'opaque' when it was formed with an unquoted expansion/substitution/
    glob/brace/tilde (dynamic, unresolvable) OR carries a '..' component (it can traverse to a device or
    anywhere and cannot be proven a plain file); 'file-dev' when it is a static path that resolves under
    /dev or /proc (a console/terminal or a stdout/stderr descriptor path, which still reaches the review
    surface); else a static 'file-real' ordinary path. The path is LEXICALLY normalized (os.path.normpath,
    never touching the filesystem) BEFORE classifying, so /tmp/../dev/stdout is recognized as a /dev target
    rather than passing as a plain /tmp file. Two cwd-dependent forms are NOT proven a plain file and route
    to 'opaque' (ASK): a '..' that normpath cannot resolve away (a relative escape such as
    ../../../dev/stdout), and a RELATIVE target whose normalized first component is 'dev' or 'proc'
    (dev/stdout, ./dev/stdout, proc/self/fd/1), which from cwd '/' or via a 'dev'/'proc' symlink IS the
    device the absolute form names but from a working tree is an ordinary relative file. The ABSOLUTE
    /dev,/proc form stays 'file-dev' (DENY, an unambiguous device); the relative form only ASKS, so a
    legitimate write into a repo's own dev/ or proc/ subdirectory is surfaced, not hard-blocked.

    A clean-leading-tilde target ('~'/'~/x') is intentionally left 'opaque' HERE (the tilde marks the word
    opaque): the abspth Bash floor reads the separate _Redirect.target_leading_tilde flag to allow it,
    consistent with the cd/pushd destination, WITHOUT reclassifying the target for the other consumers of
    this shared classifier (the L11 diff-source layer, which keeps its own tilde-target policy)."""
    if t_opaque:
        return "opaque"
    norm = os.path.normpath(target)
    if _DEV_PROC_TARGET_RE.match(norm) or _DEV_PROC_TARGET_RE.match(target):
        return "file-dev"
    if _REL_DEV_PROC_TARGET_RE.match(norm):
        return "opaque"  # a relative dev/proc-leading target is cwd-dependent: could BE the device
    if ".." in norm.replace("\\", "/").split("/") or ".." in target.replace("\\", "/").split("/"):
        return "opaque"  # a '..' component -> could resolve to a device; cannot be proven a plain file
    return "file-real"


def _lex_command(command, partial=False):
    """Lex the raw Bash command into ordered _Segment records. Raises ValueError on an unbalanced quote or
    escape, a NUL, or an unsupported construct (a heredoc/here-string, a process substitution, a '{fd}>'
    redirect, or a malformed redirect), so the caller falls back conservatively rather than acting on a
    partially-cleaned command. Linear, non-recursive, stdlib-only.

    When partial is True the raise-on-error contract is replaced by a best-effort one: instead of raising,
    the lexer returns (segments, complete), where segments are the COMPLETE segments recovered before the
    first unparseable construct and complete is False when such a construct truncated the scan (True when
    the whole command parsed). This lets the Bash abspth floor still inspect a resolvable PREFIX (an
    earlier relative cd/redirect) even when a LATER segment is unparseable, rather than discarding every
    parsed segment on the first heredoc/here-string/process-substitution. The default partial=False keeps
    the list-returning, raise-on-error contract every other caller relies on."""
    n = len(command)
    segments = []
    argv = []
    argv_opaque = []
    argv_leading_tilde = []
    redirects = []
    opaque = [False]
    seg_start = [0]

    def end_segment(sep, op_start, next_start):
        segments.append(_Segment(list(argv), sep, list(redirects),
                                  command[seg_start[0]:op_start], opaque[0], list(argv_opaque),
                                  list(argv_leading_tilde)))
        del argv[:]
        del argv_opaque[:]
        del argv_leading_tilde[:]
        del redirects[:]
        opaque[0] = False
        seg_start[0] = next_start

    def consume_redirect(op, oplen, at, src_fd):
        k = at + oplen
        while k < n and command[k] in " \t":  # inline whitespace before the target (never a newline)
            k += 1
        # A redirect target that begins with an unquoted '#' is a comment where a filename must be (bash
        # treats '#' at a word start as a comment, so the redirect has no target): cannot-evaluate, ASK.
        if k >= n or command[k] == "\n" or command[k] in _METACHARS or command[k] == "#":
            raise ValueError("malformed redirect: no target")
        target, t_opaque, started, _digits, t_ltilde, k2 = _read_word(command, k, n)
        if not started:
            raise ValueError("malformed redirect target")
        redirects.append(_classify_redirect(op, src_fd, target, t_opaque, t_ltilde))
        return k2

    try:
        if "\x00" in command:
            raise ValueError("NUL in command")
        i = 0
        while i < n:
            c = command[i]
            if c in " \t":
                i += 1
                continue
            if c == "\n":
                end_segment("", i, i + 1)
                i += 1
                continue
            if c == "#":
                # An unquoted '#' at a WORD BOUNDARY starts a comment to end of line (bash): the rest of
                # the line is ignored, so a redirect or pipe that is actually commented out (git diff # >
                # /tmp/x) never earns a proof. A mid-word '#' (--rev=abc#1, ticket#123) is read literally
                # inside _read_word and never reaches this word-start position.
                nl = command.find("\n", i)
                i = n if nl == -1 else nl
                continue
            if c in _METACHARS:
                op, kind, oplen = _match_operator(command, i, n)
                if kind == "sep":
                    end_segment(op, i, i + oplen)
                    i += oplen
                    continue
                if kind == "cannot":
                    raise ValueError("unsupported shell construct: {}".format(op))
                i = consume_redirect(op, oplen, i, None)
                continue
            text, w_opaque, started, all_digits, w_leading_tilde, j = _read_word(command, i, n)
            # An IO_NUMBER: an entirely-unquoted-digit word IMMEDIATELY adjacent to a '<'/'>' redirect
            # operator is that redirect's source fd, consumed as fd syntax, never left in argv. '2>file' ->
            # fd 2; but '2 > file' (spaced), "'2'>file"/'\2>file' (quoted/escaped), and 'x2>file' keep it.
            if all_digits and text and j < n and command[j] in "<>":
                op, kind, oplen = _match_operator(command, j, n)
                if kind == "redirect":
                    i = consume_redirect(op, oplen, j, int(text))
                    continue
                if kind == "cannot":
                    raise ValueError("unsupported shell construct: {}".format(op))
            # A '{varname}>' fd-var redirect is not modelled: cannot-evaluate rather than a partial word.
            if text and j < n and command[j] in "<>" and _FD_VAR_RE.match(text):
                raise ValueError("unsupported {fd} redirect")
            if started:
                argv.append(text)
                argv_opaque.append(w_opaque)
                argv_leading_tilde.append(w_leading_tilde)
                if w_opaque:
                    opaque[0] = True
            i = j
        end_segment("", n, n)
    except ValueError:
        # partial mode recovers the COMPLETE segments lexed before the unparseable construct AND the
        # positions of the IN-PROGRESS segment that were fully parsed BEFORE it (an earlier relative
        # cd/redirect in the SAME, still-open segment - e.g. the 'out.txt' of 'cat > out.txt <<EOF' - is
        # thereby still inspected by the Bash abspth floor); a position WITHIN or AFTER the unparseable
        # construct stays uninspected, a disclosed residual. The default contract re-raises for every
        # other caller.
        if partial:
            if argv or redirects:
                segments.append(_Segment(list(argv), "", list(redirects),
                                         command[seg_start[0]:], opaque[0], list(argv_opaque),
                                         list(argv_leading_tilde)))
            return segments, False
        raise
    if partial:
        return segments, True
    return segments


def _segments(command):
    """Compatibility projection over _lex_command: a list of (argv, sep_after) tuples, argv being the
    quote-decoded words with shell REDIRECTION removed (so a leading/interspersed/trailing redirect no
    longer pollutes the token stream) and sep_after the ending operator or "". Raises ValueError on a
    parse error or unsupported construct so callers fall back conservatively. Existing consumers
    (protected_line, gate_weakening, git_discard's lossy scan, find_ai_authorship) read redirect-free
    argv automatically; diff_source_pretool uses the richer _Segment records directly."""
    return [(seg.argv, seg.sep_after) for seg in _lex_command(command)]


# A leading inline shell env-var assignment (FOO=bar or the APPEND form FOO+=bar) that PREFIXES a command,
# e.g. the GIT_PAGER=cat in 'GIT_PAGER=cat git diff'. Such assignments are SKIPPED when resolving a
# segment's command word and its git subcommand, so that form resolves to command word 'git' / subcommand
# 'diff' and is judged like a bare 'git diff' rather than slipping through as a non-git command word. The
# APPEND '+=' form (OLDPWD+=..) is a real bash assignment prefix too, so it is recognized here; missing it
# left the append-assignment mistaken for the command word, so the following cd was never examined. The
# any-segment identity-assignment scan still inspects these same tokens for an AI name
# (GIT_AUTHOR_NAME=Claude ...). Best-effort, per the manifest residue: the 'env VAR=x git ...' command form
# and the 'command git ...' builtin remain out of scope. This matches the DECODED token, so an
# assignment-SHAPED token whose NAME was quoted or escaped ("OLDPWD"=.. -> decoded OLDPWD=..) also matches;
# bash would treat that as a command, not an assignment, so recognizing it is a deliberate conservative
# over-fire (disclosed in the manifest residue), never an under-block.
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")


def _command_word_index(tokens):
    """Index of the segment's command word: the first token that is NOT a leading shell env-var
    assignment (FOO=bar). Returns len(tokens) for an empty segment or one that is all assignments."""
    i = 0
    n = len(tokens)
    while i < n and _ENV_ASSIGN_RE.match(tokens[i]):
        i += 1
    return i


def _command_word(tokens):
    """The command word of a segment: the basename of the first non-assignment token, so an absolute
    path to the tool still resolves (/usr/bin/git -> git) and a leading env-assignment prefix (FOO=bar,
    e.g. GIT_PAGER=cat git diff) is skipped so the command word is still 'git'. '' for an empty segment
    or one that is all assignments."""
    idx = _command_word_index(tokens)
    if idx >= len(tokens):
        return ""
    return tokens[idx].rsplit("/", 1)[-1]


# git global options that CONSUME a following space-separated argument, so the option's value (now its
# own token) is never mistaken for the subcommand: '-C DIR', '-c NAME=VALUE', and the long forms below.
# Their '--opt=value' inline shape carries the value in the same token (an '=' is present), consuming no
# separate arg; that case is handled by the '=' test, so only the space-separated forms skip two tokens.
_GIT_ARG_OPTS = frozenset((
    "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix",
    "--config-env", "--attr-source"))  # --attr-source (git 2.40+) consumes its value in separated form;
    # git does NOT abbreviate top-level options, so exact membership is complete here (F-121)


def _git_subcommand(tokens):
    """The git subcommand of a segment whose command word is git: the first non-option token after the
    command word, skipping any leading env-assignment prefix and the git global options. An
    arg-consuming global option in its space-separated form (-C DIR, --git-dir DIR, ...) skips two tokens
    (its value is now its own token, per the tokenizer) so the value is not read as the subcommand; the
    '--opt=value' form and any other leading '-' token skip one. None when there is no subcommand
    token."""
    i = _command_word_index(tokens) + 1  # skip leading env assignments and the command word itself
    n = len(tokens)
    while i < n:
        token = tokens[i]
        if token.startswith("-"):
            # An '=' inline form carries its value in the same token: skip one. Otherwise a
            # space-separated arg-consuming global option skips two; any other option skips one.
            if "=" not in token and token in _GIT_ARG_OPTS:
                i += 2
            else:
                i += 1
            continue
        return token
    return None


# --- cnsdif (Stop): the diff-wall shape --------------------------------------------------------------
# Thresholds are deliberately permissive toward small illustrative excerpts: the rule forbids burying
# the review surface under a raw dump, not quoting three lines of a patch. Each detector is lexical.
GIT_HEADER_RE = re.compile(r"^diff --git ", re.M)
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@", re.M)
HUNK_MIN = 2        # one quoted hunk header can be illustrative; two is a pasted patch
FENCE_MIN = 10      # a diff/patch fence with this many content lines is a dump, not an excerpt
RUN_MIN = 8         # consecutive lines starting with + or - ...
SIGN_MIN = 3        # ... containing at least this many of EACH sign (a bullet list is all "-")
_FENCE_LANGS = ("diff", "patch", "udiff")
# A leading Markdown blockquote marker: optional indentation, then one or more '>' each optionally
# followed by a single space (a nested '> > ' quote is stripped whole).
_BLOCKQUOTE_RE = re.compile(r"^\s*(?:>\s?)+")


def _strip_quote_indent(line):
    """Strip a leading Markdown blockquote marker ('> ', possibly repeated) and leading indentation from
    a line, so a quoted or indented diff wall is still seen by the WARN-layer detectors. The blockquote
    marker is removed first, then any remaining leading whitespace, so '> ~~~diff' becomes '~~~diff' and
    a four-space-indented '    +added' becomes '+added'. WARN layer only (non-blocking); permissive
    normalization here can only surface more walls, never block."""
    return _BLOCKQUOTE_RE.sub("", line).lstrip()


def _diff_fence_lines(lines):
    """The largest content line count inside a diff/patch/udiff fenced block. Both backtick (```) and
    tilde (~~~) fences are recognized, and the fence info-string is judged by its FIRST token, so a
    fence opened as `diff path/to/file` or `diff title=x` still counts as a diff fence."""
    best = 0
    fence = None    # the marker (``` or ~~~) that opened the current block, or None when outside
    count = 0
    for line in lines:
        stripped = line.strip()
        if fence is not None:
            if stripped.startswith(fence):
                best = max(best, count)
                fence = None
            else:
                count += 1
            continue
        marker = "```" if stripped.startswith("```") else ("~~~" if stripped.startswith("~~~") else None)
        if marker is None:
            continue
        info = stripped[len(marker):].split()
        if info and info[0].lower() in _FENCE_LANGS:
            fence = marker
            count = 0
    if fence is not None:  # an unterminated fence still counts
        best = max(best, count)
    return best


def _plus_minus_run(lines):
    """The longest run of consecutive +/- lines that mixes both signs (>= SIGN_MIN each), which is
    the diff-body shape; an all-minus run is a Markdown bullet list and never trips this. A mixed
    +/- Markdown checklist can rarely trip it; that residual is accepted and noted in the manifest."""
    run = plus = minus = 0
    for line in list(lines) + [""]:  # the sentinel flushes a run that ends the message
        head = line[:1]
        # Explicit tuple test: `head in "+-"` would be True for the EMPTY string (a substring of any
        # string), so a blank line would silently extend a run and the sentinel would never flush.
        if head in ("+", "-"):
            run += 1
            if head == "+":
                plus += 1
            else:
                minus += 1
        else:
            if run >= RUN_MIN and plus >= SIGN_MIN and minus >= SIGN_MIN:
                return run
            run = plus = minus = 0
    return 0


def detect_diff_wall(text):
    """Return a human-readable description of the diff-wall shape found, or None. Each line is first
    normalized (leading blockquote marker and indentation stripped), so a diff wall quoted with '> ' or
    indented four spaces is detected exactly as a bare one; the header/hunk regexes are '^'-anchored and
    would otherwise miss a quoted or indented line."""
    lines = [_strip_quote_indent(line) for line in text.splitlines()]
    normalized = "\n".join(lines)
    if GIT_HEADER_RE.search(normalized):
        return "a 'diff --git' patch header"
    hunks = len(HUNK_RE.findall(normalized))
    if hunks >= HUNK_MIN:
        return "{} unified-diff @@ hunk headers".format(hunks)
    fenced = _diff_fence_lines(lines)
    if fenced >= FENCE_MIN:
        return "a fenced diff block of {} lines".format(fenced)
    run = _plus_minus_run(lines)
    if run:
        return "a run of {} consecutive +/- diff lines".format(run)
    return None


def diff_wall_stop(data):
    """cnsdif (trust/no-console-diff-dumps), Stop: SURFACE (non-blocking WARN) a final response that is
    a raw diff wall. This layer never blocks; see the module docstring's design note (the wall has
    already rendered, and a hard Stop block could wedge the session with no documented loop bound). It
    surfaces via systemMessage on exit 0; the PreToolUse diff_source layer is the hard prevention."""
    if data.get("hook_event_name") not in STOP_EVENTS:
        # Even a mis-wired event only WARNS here: the diff-wall Stop layer is warn-only end to end (the
        # orchestration stop guard, a separate Stop handler, is the one that deliberately denies via exit
        # 2), so nothing here can wedge a turn chain. The generator's event whitelist is the real guard.
        return _stop_warn(
            "AIQT guardrail (rule cnsdif): the Stop diff-wall check was wired to an unexpected event "
            "{!r}; surfacing a warning rather than blocking.".format(data.get("hook_event_name")))
    message = data.get("last_assistant_message")
    if not isinstance(message, str):
        # Unreadable Stop payload: WARN, do not exit 2 (no wedge). The check could not run; surface it.
        return _stop_warn(
            "AIQT guardrail (rule cnsdif): the Stop payload carried no readable last_assistant_message, "
            "so the diff-wall check could not run. Surfacing a warning (non-blocking).")
    found = detect_diff_wall(message)
    if found is None:
        return _allow()
    return _stop_warn(
        "AIQT guardrail WARNING (rule cnsdif, no-console-diff-dumps): the final response contains {}. "
        "A raw diff wall buries the review surface. Report the change as a concise summary and surface "
        "the full detail through a file, an artefact, or the client's own diff view. (This is a "
        "surfacing warning; the PreToolUse layer is the hard prevention at the command source.)"
        .format(found))


# --- cnsdif (PreToolUse): a bare console diff at the source -------------------------------------------
# Layer A of the F-36 catch, redesigned FAIL-SAFE-BY-CONSTRUCTION (GD-112 AIRTIGHT-NARROW philosophy, the
# same one applied to the truncation guard): rather than enumerating every dumping form of git (an
# unbounded shell + git-option grammar, GD-34/F-119), it proves the SAFE form or DENIES/ASKS. It works on
# the shared quote/redirect-aware tokenizer (_lex_command), so a redirection anywhere in the command is
# recorded as metadata and removed from argv, closing the redirect-pollution class. A git diff-PRODUCER is
# ALLOWED only when the WHOLE command matches one of FOUR closed proofs: (A) an exact metacharacter-free
# help invocation (git <producer> --help/-h); (B) an exact summary-only command (a metacharacter-free
# 'git <producer> ... --stat/--name-only/...' whose only other option may be --no-patch); (C) a single
# simple command whose command word is literally 'git', a possible producer, whose LAST stdout redirect is
# proven to land on a static non-/dev,/proc file (last-redirect-wins over the raw redirect metadata); or
# (D) an exact two-stage terminal pager pipeline 'git <producer> | less/more/most/pager'. A producer that
# is confirmed to emit a console patch (a default diff/show/range-diff, or a patch-flagged listing) and
# fits no proof DENIES; any other producer-capable-but-unproven form (a wrapper, a pathed git, quotes, a
# compound, extra summary modifiers, a dynamic redirect target, a pipe to a non-pager) ASKS. The ALLOW path
# deliberately does NOT parse the full git/shell option grammar, so it over-ASKS (a git log carrying any
# extra flag, quoted prose) rather than risk a false ALLOW; the residual is disclosed in the manifest. A
# fifth proof (E) ALLOWs a benign 'git log' commit listing (bare, --oneline, or bare operands, no diff).
_PATCH_FLAGS = frozenset(("-p", "-u"))
_SUMMARY_FLAGS = frozenset(("--stat", "--name-only", "--name-status", "--numstat", "--shortstat"))
_INFO_FLAGS = frozenset(("--help", "-h"))
_PAGERS = frozenset(("less", "more", "most", "pager"))
# The producer-capable git SURFACES (a git word followed later by one of these makes a segment a POSSIBLE
# producer, the fail-safe ASK scope). 'show' covers a plain 'git show' and 'git stash show'.
_PRODUCER_SURFACES = frozenset((
    "diff", "show", "range-diff", "log", "diff-tree", "diff-index", "diff-files", "format-patch"))
# The summary-capable producers for the proof-B and proof-A exact forms (format-patch writes files, never a
# summary listing, so it is excluded here).
_SUMMARY_PRODUCERS = frozenset((
    "diff", "show", "range-diff", "log", "diff-tree", "diff-index", "diff-files"))
# Proof E (benign 'git log' commit-listing): an EXACT, curated allowlist of git log options that are BOTH
# value-free (they never consume a following word: any optional value is inline '=value' only, so a bare
# operand is never a swallowed value) AND provably diff-free (they affect only commit-listing display or
# traversal, never a patch or a file-list). Kept exact, never a fuzzy pattern: 'git log' renders a patch
# ONLY with a patch-generating flag (-p/-u/--patch* and kin), and a summary/file-list form (--stat,
# --numstat, --shortstat, --name-only, --name-status) EMITS output so is NOT here (--stat and kin are proof
# B). Any OTHER option - a patch flag, a summary/file-list flag, a pickaxe (-G/-S) whose diff behaviour
# depends on a co-present -p, a value-taking option (--format, -n <count>, --author=, --since=, --grep=), or
# any unknown flag - is NOT admitted and routes to the unchanged airtight-narrow default (ASK, or DENY when
# a patch flag confirms a console patch).
_BENIGN_LOG_OPTS = frozenset((
    "--oneline", "--graph", "--decorate", "--no-decorate", "--abbrev-commit", "--reverse", "--all"))
# A pipe to one of these known console/truncating sinks is a confirmed console dump (DENY); a pipe to a
# pager is proof D (ALLOW); a pipe to anything else is unprovable (ASK).
_CONSOLE_SINKS = frozenset(("cat", "tee", "head", "tail"))
_DIFF_END_OF_OPTIONS = frozenset(("--", "--end-of-options"))
# Shell reserved words that change execution without a metacharacter (so the plain-command charset alone
# would admit them); an exact token match excludes them from the proof-A/B metacharacter-free forms.
_DIFF_RESERVED_WORDS = frozenset((
    "if", "then", "else", "elif", "fi", "case", "esac", "for", "select", "while", "until",
    "do", "done", "in", "function", "time", "coproc"))
# The conservative metacharacter-free character set for the proof-A/B forms (letters, digits, space, tab,
# and the punctuation '_ - . / = : @ , + %'), so the whole command carries no quote, redirect, separator,
# expansion, substitution, grouping, glob, or comment - matching the GD-112 truncation-guard charset.
_DIFF_PLAIN_RE = re.compile(r"[A-Za-z0-9_ \t./=:@,+%-]+")
# A redirect target UNDER /dev/ or /proc/ is never a real diff-output file: it lands on a console/terminal
# (/dev/tty, /dev/pts/N, /dev/console) or on a stdout/stderr descriptor path (/dev/stdout, /dev/stderr,
# /dev/fd/N, /proc/self/fd/1, /proc/PID/fd/N), so a diff sent there still reaches the review surface.
_DEV_PROC_TARGET_RE = re.compile(r"^/+(?:dev|proc)(?:/|$)")
# A RELATIVE target whose normalized FIRST component is 'dev' or 'proc' (dev/stdout, ./dev/stdout,
# proc/self/fd/1) is CWD-DEPENDENT: from cwd '/', or where a 'dev'/'proc' symlink exists, it resolves to
# the very device the absolute form names, but from an ordinary working tree it is a plain relative file.
# It therefore cannot be proven a plain file lexically, so it is routed OPAQUE (ASK), never a proven
# real-file ALLOW - matching how a '..' escape (equally cwd-dependent) is handled.
_REL_DEV_PROC_TARGET_RE = re.compile(r"^(?:dev|proc)(?:/|$)")
# Fallback-only broad producer probe over the RAW command, used only when _lex_command cannot parse the
# command: an apparent 'git ... <producer>' ASKS (never a silent allow, never a regex-earned allow).
_RAW_DIFF_PRODUCER_RE = re.compile(
    r"(?is)\bgit\b.*?\b(?:diff|show|range-diff|log|diff-tree|diff-index|diff-files|format-patch)\b")


def _has_patch_flag(tokens):
    """True when a segment carries a patch flag (-p, -u, or a --patch* form: --patch, --patch-with-stat,
    --patch-with-raw), the flag that turns a listing/plumbing/stash producer into a console patch and
    that also dumps the full diff alongside a summary flag (git diff --stat -p). Clustered short patch
    flags (-wp), patch-implying options (-U/-c/--cc/-L), and wrapped producers are NOT modelled here: the
    diff-dump guard is best-effort and those forms are a DISCLOSED lexical residual routed to a separate
    cnsdif hardening effort (F-119)."""
    return any(t in _PATCH_FLAGS or t.startswith("--patch") for t in tokens)


def _has_summary_flag(tokens):
    """True when a segment carries a summary/listing flag (--stat, --name-only, --name-status, --numstat,
    --shortstat), in either the bare or the '=value' shape. A summary flag is a listing rather than a raw
    diff, but ONLY when no patch flag is also present (see the handler: --stat -p still dumps the full
    diff), so the summary escape is gated on _has_patch_flag being false. A `--stat`/summary token in a
    NON-flag position - the value of a value-taking option (git diff -S --stat), a post-`--` pathspec
    (git diff -- --stat), or a redirect target (git diff > --stat) - is still counted as a summary flag; a
    role-aware fix would over-deny common commands such as `git diff -M --stat`, so this contrived
    mis-count is a disclosed residual rather than a fix (F-119)."""
    return any(t.split("=", 1)[0] in _SUMMARY_FLAGS for t in tokens)


def _is_diff_producer(tokens):
    """True when a git segment runs a subcommand that renders a diff to the console. The caller has
    already confirmed the segment's command word is git. Judging the SUBCOMMAND (not a bare 'diff'
    token) avoids a false positive on a commit message that mentions the word diff.

    Always a diff dump: diff, show, range-diff (they render a patch by default). Patch-flag gated: log,
    the plumbing producers diff-tree, diff-index, diff-files, and stash 'show' (they emit a listing by
    default and a patch only with -p/-u/--patch). stdout gated: format-patch (writes numbered files by
    default and dumps to the console only with --stdout). Gating the plumbing/format-patch/stash forms
    on their flag keeps the file-writing and name-only forms from a false positive."""
    sub = _git_subcommand(tokens)
    if sub in ("diff", "show", "range-diff"):
        return True
    if sub in ("log", "diff-tree", "diff-index", "diff-files"):
        return _has_patch_flag(tokens)
    if sub == "format-patch":
        return "--stdout" in tokens
    if sub == "stash":
        return "show" in tokens and _has_patch_flag(tokens)
    return False


def _has_info_flag(tokens):
    """True when a segment carries an info flag (--help or -h) as a GENUINE help invocation: git would
    show the subcommand's manual rather than run it, so the segment renders no diff and lands no push or
    commit. It receives the shell-CLEANED argv (the shared _lex_command has already removed shell
    redirection), so a --help/-h that was a redirect TARGET is no longer in the token stream at all; the
    two remaining git-argument-parsing cases (F-117) still apply:
      - END-OF-OPTIONS: after a '--' or '--end-of-options' token every argument is positional (a pathspec or refspec), so a
        --help/-h at or after the first '--' is NOT help (git runs the command); only earlier tokens
        are considered.
      - VALUE / OPTION SLOT: a --help/-h that is the VALUE of a preceding separated option
        (git commit -m --help, git push -o --help --force) is that option's argument, not a help flag,
        so a token whose PREDECESSOR starts with '-' does not count.
    An info flag counts only when its predecessor is a plain word (the subcommand, an operand, or a
    consumed value), exactly where git treats it as help. Fail-safe by construction: every 'git actually
    runs it' shape is excluded, and incompleteness of any value-option list can never cause a silent
    allow. The redirect-target exclusion (a predecessor made only of the characters '<>&|') is retained as
    a harmless belt-and-braces guard, though the tokenizer no longer surfaces a redirect operator here. The
    safe-direction residual is an over-ask/over-deny on ANY complete option placed immediately before help
    (a valueless flag, git commit --amend --help, or an attached-value flag, git commit -mfoo --help / git
    push -ofoo --help --force), where git shows help but the preceding '-' token makes this treat the
    segment as live; recoverable, re-issue as 'git <subcommand> --help'."""
    end = len(tokens)
    for j, tok in enumerate(tokens):
        if tok == "--" or tok == "--end-of-options":  # git's two end-of-options spellings (F-117)
            end = j
            break
    for i in range(1, end):
        prev = tokens[i - 1]
        if (tokens[i] in _INFO_FLAGS and not prev.startswith("-")
                and not (prev and all(c in "<>&|" for c in prev))):
            return True
    return False


def _token_possible_producer(argv):
    """True when the cleaned argv carries a 'git' word (by basename, so /usr/bin/git counts) followed LATER
    by a producer-capable surface (diff/show/range-diff/log/diff-tree/diff-index/diff-files/format-patch;
    'show' also covers 'git stash show'). This is the token half of the possible-producer scope: it catches
    a quote-fragmented producer (g'it' d'iff' -> git diff) that a raw regex over the still-quoted text
    cannot see."""
    seen_git = False
    for word in argv:
        base = word.rsplit("/", 1)[-1]
        if seen_git and base in _PRODUCER_SURFACES:
            return True
        if base == "git":
            seen_git = True
    return False


def _has_producer_surface(argv):
    """True when any argv word (by basename) is a producer surface. Used with an OPAQUE segment to widen
    the possible-producer scope, so a quoting/expansion form that could resolve to a git command word (an
    ANSI-C $'g'it, a $VAR that expands to git) alongside a producer surface is never silently ALLOWED."""
    return any(word.rsplit("/", 1)[-1] in _PRODUCER_SURFACES for word in argv)


def _is_possible_producer(seg):
    """A POSSIBLE producer (the fail-safe ASK scope): a git word followed by a producer surface, seen either
    in the segment's cleaned argv (_token_possible_producer, robust to quote fragmentation) OR by a broad
    raw-text probe over the segment (which over-matches quoted prose such as echo 'git diff' - a deliberate
    over-ASK, never an over-ALLOW), OR an OPAQUE segment (one carrying an unquoted expansion, substitution,
    or ANSI-C/other quoting the lexer cannot resolve to a literal command word) that also carries a producer
    surface, so $'g'it diff (which bash runs as git diff) cannot slip through as no-producer. It never
    establishes an ALLOW; it only widens the ASK/DENY scope."""
    return (_token_possible_producer(seg.argv)
            or bool(_RAW_DIFF_PRODUCER_RE.search(seg.raw))
            or (seg.opaque_shell and _has_producer_surface(seg.argv)))


# git diff/log write the diff to a --output/-o file instead of stdout, so a shell redirect or a pipe is a
# DECOY when --output is present (proofs C and D must not apply). --output/-o takes a file value, inline
# (--output=X / -oX) or separated (--output X / -o X).
def _diff_output_diversion(argv):
    """Return (present, target) for a git --output/-o diff-output diversion before any '--' boundary, or
    (False, None). The target decides console vs file: the diff lands there, not on stdout."""
    end = len(argv)
    for j, word in enumerate(argv):
        if word in _DIFF_END_OF_OPTIONS:
            end = j
            break
    i = 0
    while i < end:
        word = argv[i]
        if word in ("--output", "-o"):
            return True, (argv[i + 1] if i + 1 < len(argv) else None)
        if word.startswith("--output="):
            return True, word[len("--output="):]
        if word.startswith("-o") and not word.startswith("--") and len(word) > 2:
            return True, word[2:]
        i += 1
    return False, None


def _final_stdout_dest(redirects):
    """The classification of the segment's FINAL stdout-affecting redirect (last-redirect-wins), or None
    when no redirect touches stdout: 'file-real' a static non-/dev,/proc path, 'file-dev' a /dev,/proc
    console/descriptor path, 'descriptor' an fd duplication (e.g. 1>&2, unprovable as a file), or 'opaque'
    a dynamic target."""
    dest = None
    for red in redirects:
        if red.stdout_effect:
            dest = red.stdout_effect
    return dest


def _diff_emits_only_summary(argv):
    """Role-aware: True when a producer's OPTION region (before a '--'/'--end-of-options' boundary) carries
    a summary selector (--stat/--name-only/--name-status/--numstat/--shortstat, bare or '=value') and NO
    patch flag (-p/-u/--patch*). Distinguishes a genuine summary listing (git diff -M --stat, which is not a
    console patch dump and so ASKS rather than DENIES) from a summary token in a NON-option position (git
    diff -- --stat, a pathspec: a real dump) and from a summary with a co-present patch flag (git diff
    --stat -p, still a full patch dump)."""
    has_summary = False
    has_patch = False
    for word in argv:
        if word in _DIFF_END_OF_OPTIONS:
            break
        if word.split("=", 1)[0] in _SUMMARY_FLAGS:
            has_summary = True
        if word in _PATCH_FLAGS or word.startswith("--patch"):
            has_patch = True
    return has_summary and not has_patch


def _seg_stdout_reaches_console(seg, segments, index):
    """Where a producer segment's stdout goes: 'file' (a static real file, NOT a console dump), 'console' (a
    /dev,/proc target, or a pipe into a known console/truncating sink cat/tee/head/tail, or a plain producer
    with no diversion), or 'unprovable' (a descriptor or dynamic redirect target, a both-streams '|&' pipe,
    or a pipe into a pager or any other command whose downstream this guard does not follow)."""
    dest = _final_stdout_dest(seg.redirects)
    if dest == "file-real":
        return "file"
    if dest in ("descriptor", "opaque"):
        return "unprovable"
    if seg.sep_after == "|":
        nxt = index + 1
        word = _command_word(segments[nxt].argv) if nxt < len(segments) else ""
        return "console" if word in _CONSOLE_SINKS else "unprovable"
    if seg.sep_after == "|&":
        return "unprovable"
    if dest == "file-dev":
        return "console"
    return "console"  # no stdout redirect and no pipe: straight to the console


def _is_console_dump(seg, segments, index):
    """True when a producer segment is CONFIRMED to emit a console patch: its command word is PROVABLY git
    (a literal 'git' or a path to it, so an opaque/expansion command word this guard cannot resolve is never
    a confirmed dump - it routes to ASK instead), it is a git diff producer, it does not emit only a summary
    listing, and its output is proven to reach a console. When the producer diverts its output with
    --output/-o, THAT target decides (a /dev,/proc console target is a dump; a file or dynamic target is not
    a confirmed dump, so it ASKS) and any shell redirect or pipe is a decoy. Otherwise stdout governs. Used
    only to choose DENY over ASK; its absence never establishes an ALLOW."""
    if _command_word(seg.argv) != "git":
        return False  # an opaque/wrapped command word is not a proven git dump -> ASK, never DENY
    if not _is_diff_producer(seg.argv):
        return False
    if _diff_emits_only_summary(seg.argv):
        return False
    diverted, out_target = _diff_output_diversion(seg.argv)
    if diverted:
        # the diff is written to the --output target, not stdout; the shell redirect/pipe is a decoy
        return out_target is not None and _target_class(out_target, False) == "file-dev"
    return _seg_stdout_reaches_console(seg, segments, index) == "console"


def _diff_proof_help(command):
    """Proof A: an EXACT metacharacter-free help invocation. Allows only 'git <producer> --help/-h' (or the
    exact 'git stash show --help/-h'); any extra option, operand, wrapper, path, quote, or shell syntax
    fails. A --help that reached this command as an option value, a path, or a redirect target cannot form
    this exact shape (the metacharacter-free requirement rules out a redirect, and an option value/path
    changes the exact word list)."""
    if not _DIFF_PLAIN_RE.fullmatch(command):
        return False
    words = command.split()
    if words[:1] != ["git"]:
        return False
    if len(words) == 3 and words[1] in _PRODUCER_SURFACES and words[2] in _INFO_FLAGS:
        return True
    return len(words) == 4 and words[1:3] == ["stash", "show"] and words[3] in _INFO_FLAGS


def _diff_proof_summary(command):
    """Proof B: an EXACT summary-only command. Requires a metacharacter-free single simple command (the
    conservative charset, no shell reserved word), the first resolved words literally 'git' and a
    summary-capable producer ('git stash show' handled explicitly), at least one exact summary selector
    before a '--'/'--end-of-options' boundary, and no other option-like word before the boundary except an
    exact --no-patch (bare operands are allowed). Any extra option (git diff -M --stat, git diff --stat=80),
    a wrapper, a path, an assignment, or a quote fails, routing to ASK rather than another growing option
    table."""
    if not _DIFF_PLAIN_RE.fullmatch(command):
        return False
    words = command.split()
    if _DIFF_RESERVED_WORDS & set(words):
        return False
    if words[:1] != ["git"]:
        return False
    if words[1:2] == ["stash"]:
        if words[2:3] != ["show"]:
            return False
        opts = words[3:]
    elif len(words) >= 2 and words[1] in _SUMMARY_PRODUCERS:
        opts = words[2:]
    else:
        return False
    boundary = len(opts)
    for j, word in enumerate(opts):
        if word in _DIFF_END_OF_OPTIONS:
            boundary = j
            break
    has_selector = False
    for word in opts[:boundary]:
        if word in _SUMMARY_FLAGS:
            has_selector = True
        elif word.startswith("-") and word != "--no-patch":
            return False
    return has_selector


def _diff_proof_log_listing(command):
    """Proof E (Architect-directed refinement): a benign 'git log' COMMIT LISTING that provably emits no diff
    to the console. Requires a metacharacter-free single simple command (the conservative charset, no shell
    reserved word, so no redirect and no pipe), the first resolved words literally 'git' and 'log', and every
    option-like word before a '--'/'--end-of-options' boundary drawn from the exact _BENIGN_LOG_OPTS
    allowlist (bare revision/pathspec operands are allowed, and an option there is valueless so no operand is
    a swallowed value). Any patch flag, pickaxe, value-taking option, or unknown flag fails this proof and
    routes to the unchanged default (ASK, or DENY on a confirmed patch). This is EXACT-form, not a fuzzy
    'anything without -p' allow: an unknown flag is never proven benign."""
    if not _DIFF_PLAIN_RE.fullmatch(command):
        return False
    words = command.split()
    if _DIFF_RESERVED_WORDS & set(words):
        return False
    if words[:2] != ["git", "log"]:
        return False
    opts = words[2:]
    boundary = len(opts)
    for j, word in enumerate(opts):
        if word in _DIFF_END_OF_OPTIONS:
            boundary = j
            break
    for word in opts[:boundary]:
        if word.startswith("-") and word not in _BENIGN_LOG_OPTS:
            return False
    return True


def _diff_proof_realfile(segments):
    """Proof C: a single simple command whose command word is literally 'git', a possible producer, with no
    opaque shell feature, whose FINAL stdout redirect (last-redirect-wins over the raw redirect metadata) is
    proven to land on a static non-/dev,/proc file. Supports leading, interspersed, and trailing redirects
    without token pollution; a dynamic target, a descriptor duplication, or a /dev,/proc target is not a
    proof."""
    if len(segments) != 1:
        return False
    seg = segments[0]
    if seg.opaque_shell:
        return False
    if not seg.argv or seg.argv[0] != "git":  # literal 'git': no assignment prefix, wrapper, or path
        return False
    if not _is_possible_producer(seg):
        return False
    if _diff_output_diversion(seg.argv)[0]:
        return False  # --output/-o governs where the diff lands; the shell redirect is a decoy
    return _final_stdout_dest(seg.redirects) == "file-real"


def _diff_proof_pager(segments):
    """Proof D: an EXACT two-stage terminal pager pipeline. Stage 1 is a plain literal unwrapped 'git'
    possible producer with no redirection or opaque feature; the separator is exactly '|' (not '|&'); stage
    2 is exactly one command word (less/more/most/pager) with no options, operands, redirection, or opaque
    feature, and it is the terminal stage (no later pipe)."""
    if len(segments) != 2:
        return False
    stage1, stage2 = segments
    if stage1.sep_after != "|" or stage2.sep_after != "":
        return False
    if stage1.redirects or stage1.opaque_shell:
        return False
    if not stage1.argv or stage1.argv[0] != "git" or not _is_possible_producer(stage1):
        return False
    if _diff_output_diversion(stage1.argv)[0]:
        return False  # --output/-o diverts the diff off the pipe; the pager is a decoy
    if stage2.redirects or stage2.opaque_shell:
        return False
    return len(stage2.argv) == 1 and stage2.argv[0] in _PAGERS


def _diff_source_fallback(command):
    """FAIL-SAFE conservative check when _lex_command cannot parse the command (an unbalanced quote or an
    unsupported construct such as a heredoc or process substitution): an apparent git diff-producer (the
    broad raw probe) ASKS, everything else ALLOWS. An unparseable command can never earn an ALLOW from a
    summary or redirect regex - the old raw-summary/redirect escapes are removed - so a plausibly-dumping
    unparseable command is surfaced for confirmation rather than proven either way."""
    if _RAW_DIFF_PRODUCER_RE.search(command):
        return _ask(
            "AIQT rule cnsdif (no-console-diff-dumps): the shared tokenizer could not parse this command "
            "(an unbalanced quote, or a heredoc/process-substitution/other construct it does not model) "
            "and it appears to invoke a git diff-producer. This guard deliberately does not parse the "
            "full shell/git grammar, so it cannot prove where the output lands; confirm, or re-issue a "
            "parseable summary form (--stat), a redirect to a real file (> file), or a pager (| less).",
            "AIQT guardrail: asked on an unparseable command that appears to invoke a git diff-producer "
            "(rule cnsdif).")
    return _allow()


def diff_source_pretool(data):
    """cnsdif (trust/no-console-diff-dumps), PreToolUse/Bash. FAIL-SAFE-BY-CONSTRUCTION: a git diff-producer
    is ALLOWED only when the WHOLE command matches one of five closed proofs (exact help, exact summary, a
    benign 'git log' commit listing, a single simple command proven to redirect stdout to a real file, or an
    exact terminal pager pipeline);
    a producer confirmed to emit a console patch and fitting no proof DENIES; any other producer-capable but
    unproven form ASKS. Across a compound or multiple producers, DENY outranks ASK: every possible producer
    must clear a proof, and a multi-command form is never admitted merely because one segment is safe."""
    if data.get("hook_event_name") != PRETOOL:
        return _hard_block("aiqt_hooks: diff_source_pretool wired to unexpected event {!r}; failing "
                           "closed".format(data.get("hook_event_name")))
    tool_name = data.get("tool_name")
    if tool_name is None:
        return _deny_missing_tool_name("cnsdif")
    if tool_name != "Bash":
        return _allow()  # a present-but-different tool is out of scope (defensive; the matcher governs)
    command = (data.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        return _deny(
            "AIQT rule cnsdif (no-console-diff-dumps): the Bash payload carried no readable command "
            "string, so the diff-source check could not run; failing closed.",
            "AIQT guardrail: denied a Bash call with no readable command (rule cnsdif, fail-closed).")
    try:
        segments = _lex_command(command)
    except ValueError:
        return _diff_source_fallback(command)
    possibles = [(index, seg) for index, seg in enumerate(segments) if _is_possible_producer(seg)]
    if not possibles:
        return _allow()  # no producer-capable form anywhere: the bounded true boundary allows
    # AIRTIGHT-NARROW ALLOW: only when the WHOLE command is one of the five closed proofs.
    if (_diff_proof_help(command) or _diff_proof_summary(command)
            or _diff_proof_log_listing(command)
            or _diff_proof_realfile(segments) or _diff_proof_pager(segments)):
        return _allow()
    # Otherwise judge each possible producer: a confirmed console dump DENIES (outranking ASK across a
    # compound), and any remaining producer-capable-but-unproven form ASKS.
    for index, seg in possibles:
        if _is_console_dump(seg, segments, index):
            return _deny(
                "AIQT rule cnsdif (no-console-diff-dumps): this command renders a version-control diff to "
                "the console, burying the review surface under a raw dump. Use a summary form (--stat, "
                "--name-only, --name-status, --numstat), redirect the diff to a real file (> file), or "
                "pipe it into a pager (| less), not the console.",
                "AIQT guardrail: denied a bare console diff dump (rule cnsdif).")
    return _ask(
        "AIQT rule cnsdif (no-console-diff-dumps): this command is producer-capable (it can render a "
        "version-control diff) but is outside the guard's proven-safe forms - a wrapper, a pathed git, "
        "quotes, a compound, an extra option, a dynamic redirect target, or a pipe to a non-pager. This "
        "guard deliberately does not parse the complete shell/git option grammar; confirm it is not a "
        "console dump, or re-issue an exact summary form (--stat), a redirect to a real file (> file), or "
        "an exact pager pipeline (git diff | less).",
        "AIQT guardrail: asked on a producer-capable command outside the guard's proven-safe forms "
        "(rule cnsdif).")


# --- cmtidn: AI identity in a git authoring command --------------------------------------------------
# Quote-aware and token-based. The commit-MESSAGE contexts (a Co-Authored-By trailer, an --author value)
# are judged only on a segment whose command word is git and whose subcommand is a commit-creating verb,
# so a read-side use of the same tokens (git log --author=Claude) never trips. Separately, an identity
# ASSIGNMENT (a git-identity env var, or a user.name/user.email config value) is a violation on ANY
# segment, to harden the common 'set the identity then commit' form. Because the tokens are quote-aware,
# a trailer hiding inside a quoted -m message (e.g. -m "fix; Co-authored-by: Claude", which the old
# whitespace split broke at the ';') now lives intact in the single message token, and a substring scan
# on that token catches it.
AI_IDENTITY_RE = re.compile(
    r"(?i)\b(claude|anthropic|openai|chatgpt|codex|copilot|gemini|gpt-?[0-9o][a-z0-9.-]*)\b"
    r"|@anthropic\.com|@openai\.com")
COMMIT_VERBS = ("commit", "merge", "cherry-pick", "am", "rebase", "revert", "commit-tree")
# A Co-Authored-By trailer inside a single token; its value runs to the token end (the token IS the
# quoted message, so no shell quote can appear within it).
CO_AUTHOR_RE = re.compile(r"(?i)co[- ]?authored[- ]?by\s*:?\s*([^\n]{1,160})")
# Identity-assignment tokens (any segment): a git-identity env var, or a user.name/user.email config
# value in the '-c user.name=VALUE' inline shape.
GIT_ENV_RE = re.compile(r"(?is)^GIT_(?:AUTHOR|COMMITTER)_(?:NAME|EMAIL)=(.*)$")
USER_CONF_EQ_RE = re.compile(r"(?is)^user\.(?:name|email)=(.*)$")
# Fallback-only raw-string contexts, used when the shared tokenizer cannot parse the command (see
# _commit_identity_fallback). A value runs to whitespace or a shell separator/quote.
_VALUE = r"(\"[^\"]*\"|'[^']*'|[^\s\"';|&]+)"
_RAW_IDENTITY_CONTEXTS = (
    (re.compile(r"(?i)co[- ]?authored[- ]?by\s*:?\s*([^\n\"']{1,160})"), "co-author trailer"),
    (re.compile(r"(?i)--author[= ]\s*" + _VALUE), "--author value"),
    (re.compile(r"(?i)\bGIT_(?:AUTHOR|COMMITTER)_(?:NAME|EMAIL)\s*=\s*" + _VALUE), "git identity variable"),
    (re.compile(r"(?i)\buser\.(?:name|email)\s*[= ]\s*" + _VALUE), "user.name/user.email value"),
)


def _commit_message_and_author_ai(tokens):
    """A hit label if this git commit segment names an AI identity in an --author value or in a
    Co-Authored-By trailer (scanned as a substring of any token, so the trailer that lives inside the
    single quoted -m message token is caught), else None. The bare message body is deliberately NOT
    matched against the identity set: a legitimate message that merely mentions an AI product name
    (e.g. -m 'fix claude adapter') is not a recorded AI identity, and denying it would be a false
    positive; only a trailer or an --author value records identity."""
    n = len(tokens)
    for i, tok in enumerate(tokens):
        m = CO_AUTHOR_RE.search(tok)
        if m and AI_IDENTITY_RE.search(m.group(1)):
            return "co-author trailer {!r}".format(m.group(1).strip()[:80])
        if tok.startswith("--author="):
            value = tok[len("--author="):]
            if AI_IDENTITY_RE.search(value):
                return "--author value {!r}".format(value.strip()[:80])
        elif tok == "--author" and i + 1 < n and AI_IDENTITY_RE.search(tokens[i + 1]):
            return "--author value {!r}".format(tokens[i + 1].strip()[:80])
    return None


def _identity_assignment_ai(tokens):
    """A hit label if any token of this segment ASSIGNS an AI identity: a git-identity env var
    (GIT_AUTHOR_NAME=..., ...), a '-c user.name=VALUE' config inline value, or a 'config user.name VALUE'
    /'config user.name=VALUE' pair. Judged on EVERY segment, so setting the identity in a prior segment
    before the commit is caught too."""
    n = len(tokens)
    for i, tok in enumerate(tokens):
        m = GIT_ENV_RE.match(tok)
        if m and AI_IDENTITY_RE.search(m.group(1)):
            return "git identity variable {!r}".format(tok.strip()[:80])
        m = USER_CONF_EQ_RE.match(tok)
        if m and AI_IDENTITY_RE.search(m.group(1)):
            return "user.name/user.email value {!r}".format(tok.strip()[:80])
        if tok in ("user.name", "user.email") and i + 1 < n and AI_IDENTITY_RE.search(tokens[i + 1]):
            return "user.name/user.email value {!r}".format(tokens[i + 1].strip()[:80])
    return None


def find_ai_authorship(command):
    """Return '<context> <value>' when a segment sets an AI identity for a recorded change, else None:
    an identity-assignment (env var / git config) on ANY segment, or a commit-message context (co-author
    trailer, --author value) on a git commit segment. Raises ValueError on a shell parse error (via
    _segments), which the handler turns into the conservative fallback."""
    for tokens, _sep in _segments(command):
        hit = _identity_assignment_ai(tokens)
        if hit is not None:
            return hit
        if _command_word(tokens) == "git" and _git_subcommand(tokens) in COMMIT_VERBS:
            hit = _commit_message_and_author_ai(tokens)
            if hit is not None:
                return hit
    return None


def _commit_identity_fallback(command):
    """FAIL-SAFE conservative scan when the shared tokenizer cannot parse the command (an unbalanced quote or an unsupported construct): scan the RAW
    string for an AI identity in a Co-Authored-By trailer, an --author value, a git-identity env var, or
    a user.name/user.email value; deny on a hit. Never silent-allow a plausibly-violating command on a
    parse failure."""
    for regex, label in _RAW_IDENTITY_CONTEXTS:
        for match in regex.finditer(command):
            if AI_IDENTITY_RE.search(match.group(1)):
                hit = "{} {!r}".format(label, match.group(1).strip()[:80])
                reason = ("AIQT rule cmtidn (commit-identity): the command could not be parsed by the "
                          "shell lexer (likely unbalanced quotes) and it appears to set an AI identity "
                          "({}); failing closed. Remove it and commit as the maintainer.".format(hit))
                return _deny(reason,
                             "AIQT guardrail: denied an unparseable git command that appears to record "
                             "an AI commit identity (rule cmtidn, fail-safe).")
    return _allow()


def commit_identity(data):
    """cmtidn (integ/commit-identity), PreToolUse/Bash: deny a git command that records an AI as
    author, committer, or co-author. No escape hatch: the rule is absolute."""
    if data.get("hook_event_name") != PRETOOL:
        return _hard_block("aiqt_hooks: commit_identity wired to unexpected event {!r}; failing closed"
                           .format(data.get("hook_event_name")))
    tool_name = data.get("tool_name")
    if tool_name is None:
        return _deny_missing_tool_name("cmtidn")
    if tool_name != "Bash":
        return _allow()  # a present-but-different tool is out of scope (defensive; the matcher governs)
    command = (data.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        return _deny(
            "AIQT rule cmtidn (commit-identity): the Bash payload carried no readable command string, "
            "so the commit-identity check could not run; failing closed.",
            "AIQT guardrail: denied a Bash call with no readable command (rule cmtidn, fail-closed).")
    try:
        hit = find_ai_authorship(command)
    except ValueError:
        return _commit_identity_fallback(command)
    if hit is None:
        return _allow()
    reason = ("AIQT rule cmtidn (commit-identity): a recorded change carries the human maintainer's "
              "own identity, with no AI as author, committer, or co-author; this git command sets an "
              "AI identity ({}). Remove it and commit as the maintainer.".format(hit))
    return _deny(reason,
                 "AIQT guardrail: denied a git command recording an AI commit identity (rule cmtidn).")


# --- abspth: relative path where the tool requires absolute ------------------------------------------
# Read, Write, and Edit require an absolute file_path, and NotebookEdit an absolute notebook_path, by the
# tool's own contract, so the rule's relative-to-a-named-root carve-out never applies to them. MultiEdit is
# kept on the same file_path wire for LEGACY COMPATIBILITY only: it is NOT in the current Claude Code
# built-in tool index, so its mapping is retained solely to cover an adopter on an older or re-enabled
# MultiEdit, never as an assertion that MultiEdit is a current/live tool. Glob and Grep are honoured under
# the carve-out: their `pattern` is legitimately relative to a named search root and is never judged, but
# their optional `path` search root should be absolute. Each field name is bound to a Claude Code tool
# schema (Read/Write/Edit -> file_path, NotebookEdit -> notebook_path, Glob/Grep -> optional path), with
# MultiEdit -> file_path the legacy-compat wire above, never assumed.
FILE_PATH_TOOLS = ("Read", "Write", "Edit", "MultiEdit")   # contract-absolute `file_path` (MultiEdit: legacy-compat wire)
NOTEBOOK_PATH_TOOLS = ("NotebookEdit",)                    # contract-absolute `notebook_path`
SEARCH_ROOT_TOOLS = ("Glob", "Grep")                       # optional `path` search root; carve-out


def _is_absolute(path):
    """Absolute under the runtime's own path semantics, not a lexical drive-letter guess: a POSIX
    absolute path (PurePosixPath.is_absolute) OR a Windows path carrying BOTH a drive and a root
    (PureWindowsPath.is_absolute), so a UNC \\\\server\\share and a drive-absolute C:\\ / C:/ count, while
    a drive-RELATIVE 'C:file', a bare 'C:', and a rooted-but-driveless '\\file' are correctly NOT
    absolute (each still resolves against a current directory, or a per-drive current directory, on
    Windows). A '~'-prefixed, empty, or otherwise relative path is likewise not absolute: these tools do
    not expand '~', so it would resolve against a literal '~' directory. Deferring to the stdlib
    predicate closes the drive-relative false positives the old lexical `^[A-Za-z]:` / leading-backslash
    union accepted (C:file, C:, \\file all read as absolute there)."""
    return pathlib.PurePosixPath(path).is_absolute() or pathlib.PureWindowsPath(path).is_absolute()


def _deny_relative(tool, field, value):
    reason = ("AIQT rule abspth (absolute-paths): {} requires an absolute {}; got {!r}. The working "
              "directory can silently differ between tool calls, so re-issue the call with the full "
              "absolute path.".format(tool, field, value))
    return _deny(reason,
                 "AIQT guardrail: denied a relative {} where an absolute one is required "
                 "(rule abspth).".format(field))


def _abspth_check_required(tool, field, value):
    """A field the tool's contract requires to be absolute (Read/Write/Edit/MultiEdit file_path,
    NotebookEdit notebook_path): fail closed when it is absent or not a non-empty string, allow when it
    is absolute, deny when it is relative."""
    if not isinstance(value, str) or not value:
        return _deny(
            "AIQT rule abspth (absolute-paths): the {} payload carried no readable {}, so the "
            "absolute-path check could not run; failing closed.".format(tool, field),
            "AIQT guardrail: denied a {} call with no readable {} (rule abspth, fail-closed)."
            .format(tool, field))
    if _is_absolute(value):
        return _allow()
    return _deny_relative(tool, field, value)


def _abspth_check_search_root(tool, path):
    """The optional `path` search root of Glob/Grep. Carve-out: a rootless call (no path) names the
    current directory as the root against which the relative pattern is legitimately judged, so allow;
    a present search root should be absolute, and a present-but-unreadable one fails closed."""
    if path is None:
        return _allow()  # rootless: the pattern's named root is the current directory (carve-out)
    if not isinstance(path, str) or not path:
        return _deny(
            "AIQT rule abspth (absolute-paths): the {} payload carried an unreadable path search root, "
            "so the absolute-path check could not run; failing closed.".format(tool),
            "AIQT guardrail: denied a {} call with an unreadable path (rule abspth, fail-closed)."
            .format(tool))
    if _is_absolute(path):
        return _allow()
    return _deny_relative(tool, "path search root", path)


def absolute_paths(data):
    """abspth (quali/absolute-paths), PreToolUse on Read|Write|Edit|MultiEdit|NotebookEdit|Glob|Grep:
    deny a relative path where the tool's contract requires absolute, honouring the rule's carve-out for
    the relative search pattern of Glob and Grep."""
    if data.get("hook_event_name") != PRETOOL:
        return _hard_block("aiqt_hooks: absolute_paths wired to unexpected event {!r}; failing closed"
                           .format(data.get("hook_event_name")))
    tool = data.get("tool_name")
    if tool is None:
        return _deny_missing_tool_name("abspth")
    in_scope = tool in FILE_PATH_TOOLS or tool in NOTEBOOK_PATH_TOOLS or tool in SEARCH_ROOT_TOOLS
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        # A falsy or malformed tool_input previously collapsed to {} and let the search-root branch take
        # its allow path (fail-open). Require a mapping first: for any in-scope tool a payload that is not
        # a readable mapping fails closed; an out-of-scope tool (the matcher governs) allows.
        if in_scope:
            return _deny(
                "AIQT rule abspth (absolute-paths): the {} payload was not a readable mapping, so the "
                "absolute-path check could not run; failing closed.".format(tool),
                "AIQT guardrail: denied a {} call with an unreadable tool_input (rule abspth, "
                "fail-closed).".format(tool))
        return _allow()
    if tool in FILE_PATH_TOOLS:
        return _abspth_check_required(tool, "file_path", tool_input.get("file_path"))
    if tool in NOTEBOOK_PATH_TOOLS:
        return _abspth_check_required(tool, "notebook_path", tool_input.get("notebook_path"))
    if tool in SEARCH_ROOT_TOOLS:
        return _abspth_check_search_root(tool, tool_input.get("path"))
    return _allow()  # a present-but-different tool is out of scope (defensive; the matcher governs)


# --- abspth (Bash floor): a relative cd/pushd or redirect target resolved against the cwd ------------
# A SEPARATE PreToolUse linkage of the same rule onto Bash, reusing the shared quote/redirect-aware
# lexer (_lex_command / _command_word). CONSERVATIVE FLOOR, ASK-defaulting: it judges only two positions
# that silently depend on the current directory - a cd/pushd DESTINATION operand, and a redirection
# TARGET - and NEVER an arbitrary command operand (a relative argument to some other command is not
# judged, to avoid over-firing). A relative or unresolvable such position ASKS; an absolute position, and
# a command carrying neither, allow. It never denies: the human confirming is the opt-out.
_CD_BUILTINS = frozenset(("cd", "pushd"))
# cd/pushd option tokens that name NO destination path: the real option flags (cd -L/-P/-e/-@, pushd -n,
# and bundled combos like -LP), which are a limited closed set, NOT any '-'/'+'-prefixed token. A lone '-'
# is cd's $OLDPWD previous-directory shortcut (an absolute prior dir, cwd-independent); '--' ENDS option
# processing so the NEXT token is the destination even when it begins '-'/'+'; and pushd's +N/-N is a
# numeric directory-stack rotation. A '+relative' or '-relative' that is NOT one of these is a real
# relative directory NAME (the destination), matching the comment 'the first token that is not an option'.
_CD_OPT_BUNDLE_RE = re.compile(r"^-[LPe@n]+$")  # cd -L/-P/-e/-@ and pushd -n, singly or bundled (-LP, -nL)
_PUSHD_ROTATION_RE = re.compile(r"^[-+][0-9]+$")  # pushd +N/-N: a stack index, not a filesystem path
# An UNQUOTED CURRENT-USER tilde destination (~ or ~/path) is tilde-EXPANDED by the shell to $HOME, an
# absolute directory, so it is cwd-independent exactly like an absolute path. This is NARROWED to the
# current-user forms only: a '~user'/'~user/path' names another account's home whose EXISTENCE the hook
# cannot verify (an unresolved login name leaves the word RELATIVE), so it is NOT proven absolute here and
# ASKS; and the '~-'/'~+'/'~N' directory-stack forms likewise ASK. A QUOTED '~' (a literal directory named
# '~') is not expanded and stays relative; the LEADING-UNQUOTED-tilde flag (argv_leading_tilde), not the
# broader opacity flag, tells the expanded form from a quoted one whose unquoted tail merely carries opacity.
_LITERAL_TILDE_RE = re.compile(r"^~(/.*)?$")
# CONSERVATIVE CONSOLIDATION (round-4). Any inline env-assignment PREFIXING a cd/pushd command
# ('OLDPWD=.. cd -', 'HOME=.. cd', and the append forms 'OLDPWD+=.. cd -'/'HOME+=.. cd') can redirect where
# the cwd-INDEPENDENT destinations land: an inline OLDPWD= redirects the lone '-' ($OLDPWD) shortcut, and an
# inline HOME= redirects the bare 'cd' (no operand -> $HOME) default, in each case to a value the floor
# cannot prove absolute ('..'). Rather than enumerate OLDPWD/HOME by name (fragile: it misses the '+='
# append form, and the earlier OLDPWD-only check never covered the bare-cd HOME default), the floor takes
# the conservative stance that ANY leading assignment (any name, '=' or '+=', and even an assignment-SHAPED
# token bash would reject because its name was quoted) makes those two otherwise-cwd-independent
# destinations ASK. A plain zero-assignment 'cd -'/'cd -- -'/bare 'cd' keeps its ALLOW. The consequence
# 'FOO=x cd -' -> ASK is a deliberate conservative over-fire, disclosed in the manifest residue.


def _cd_destination_reason(word, argv, argv_leading_tilde):
    """For a cd/pushd segment, return a reason string when its destination operand is relative or
    unresolvable (opaque), else None: an absolute destination, an unquoted current-user tilde one ('~' or
    '~/path', which expands to $HOME), the OLDPWD 'cd -', or no destination at all (cd -> HOME, pushd -> swap
    the stack top), is cwd-independent here. Only the FIRST non-option token is the destination; the real
    cd/pushd option flags and a pushd +N/-N rotation name no relative path and are skipped, while '--' ends
    option processing so the next token is the destination even when it begins '-'/'+'. A lone '-' is the
    $OLDPWD shortcut wherever it lands as the destination, including as the post-'--' destination ('cd -- -',
    which bash still resolves to $OLDPWD), and a NO-operand cd/pushd is the $HOME/stack-swap default; both are
    cwd-independent UNLESS the command carries ANY leading inline env-assignment ('OLDPWD=.. cd -- -',
    'HOME=.. cd', 'OLDPWD+=.. cd -'), which can redirect the destination to a value the floor cannot prove
    absolute, so those two forms then ASK. This is the conservative consolidation (round-4): the trigger is
    the mere PRESENCE of a leading assignment, not its variable name, so the '+=' append form and the bare-cd
    HOME default are covered without name enumeration. An operand carrying an unexpanded expansion never reads
    as absolute unless it is literally rooted (a leading '/'), so an opaque 'cd $DIR' naturally ASKS while an
    absolute '/$X/y' allows. argv_leading_tilde is the per-token LEADING-UNQUOTED-tilde flags parallel to argv
    (True only where the word's leading char is an unquoted tilde, so tilde-expansion applies)."""
    cmd_idx = _command_word_index(argv)  # boundary: argv[:cmd_idx] are the leading env-assignments
    # ANY leading assignment (any name, '=' or '+=') can redirect the cwd-independent destinations ('cd -',
    # bare 'cd'), so it can no longer be trusted; presence, not the variable name, is the trigger.
    has_leading_assignment = cmd_idx > 0
    idx = cmd_idx + 1  # skip leading env-assignments and the command word itself
    end_of_options = False
    for pos in range(idx, len(argv)):
        tok = argv[pos]
        if not end_of_options:
            if tok == "--":
                end_of_options = True  # everything after '--' is an operand, not an option
                continue
            if _CD_OPT_BUNDLE_RE.match(tok):
                continue  # a cd/pushd option flag or bundle (-L/-P/-e/-@/-n): not a destination path
            if word == "pushd" and _PUSHD_ROTATION_RE.match(tok):
                continue  # pushd +N/-N: a directory-stack rotation index, not a filesystem path
        # end-of-options, or the first token that is not an option: this is the destination operand.
        if tok == "-":
            if has_leading_assignment:
                # a leading inline env-assignment can redirect $OLDPWD to a value the floor cannot prove abs
                return ("a {} destination '-' that a leading inline env-assignment can redirect off $OLDPWD"
                        .format(word))
            continue  # cd '-': the $OLDPWD previous-directory shortcut (an absolute prior dir), even
            # after '--' where bash still treats a lone '-' destination as $OLDPWD, not a relative name
        if argv_leading_tilde[pos] and _LITERAL_TILDE_RE.match(tok):
            return None  # an unquoted current-user tilde ('~', '~/x') expands to $HOME: cwd-independent
        if _is_absolute(tok):
            return None
        return "a relative {} destination {!r}".format(word, tok)
    # no destination operand: cd -> HOME, pushd -> stack swap, cwd-independent UNLESS a leading inline
    # env-assignment (e.g. HOME=..) can redirect that default to a value the floor cannot prove absolute.
    if has_leading_assignment:
        return ("a bare {} (no operand) whose $HOME default a leading inline env-assignment can redirect"
                .format(word))
    return None


def bash_absolute_paths(data):
    """abspth (quali/absolute-paths) Bash floor, PreToolUse on Bash: ASK when a Bash command shifts the
    working directory through a relative cd/pushd operand, or names a relative redirection target, since
    either resolves against a working directory that can silently differ between calls. Conservative
    floor: it judges only those two cwd-dependent positions, defaults any relative or unresolvable one to
    ASK (never a silent allow of such a position), does not judge an arbitrary command operand, and does
    not deny."""
    if data.get("hook_event_name") != PRETOOL:
        return _hard_block("aiqt_hooks: bash_absolute_paths wired to unexpected event {!r}; failing "
                           "closed".format(data.get("hook_event_name")))
    tool = data.get("tool_name")
    if tool is None:
        return _deny_missing_tool_name("abspth")
    if tool != "Bash":
        return _allow()  # a present-but-different tool is out of scope (defensive; the matcher governs)
    tool_input = data.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command:
        # Cannot read the command to resolve either position: the floor asks rather than silently allows.
        return _ask(
            "AIQT rule abspth (absolute-paths): the Bash payload carried no readable command string, so "
            "the relative-cwd check could not run; confirm the command uses absolute paths.",
            "AIQT guardrail: asked on a Bash call with no readable command (rule abspth).")
    # Partial lex so an unparseable construct (a heredoc, here-string, process substitution, {fd} redirect,
    # or an unbalanced quote or escape) no longer discards every segment before it: a resolvable relative
    # cd/redirect in the parseable PREFIX still ASKS. Only a cd/redirect position WITHIN or AFTER the
    # unparseable construct is left to the human's own permission flow (a disclosed residual), rather than
    # over-asking on every such command. This is the conservative-floor boundary, not a proof of safety.
    segments = _lex_command(command, partial=True)[0]
    reasons = []
    for seg in segments:
        word = _command_word(seg.argv)
        if word in _CD_BUILTINS:
            reason = _cd_destination_reason(word, seg.argv, seg.argv_leading_tilde)
            if reason is not None:
                reasons.append(reason)
        for redirect in seg.redirects:
            if redirect.target_class == "descriptor":
                continue  # a numeric/'-' fd duplication or close names no filesystem path
            if redirect.target_leading_tilde:
                continue  # an unquoted current-user '~'/'~/x' target expands to $HOME (absolute), as cd's
            if redirect.target_class == "opaque" or not _is_absolute(redirect.target):
                reasons.append("a relative redirection target {!r}".format(redirect.target))
    if reasons:
        seen = []
        for reason in reasons:  # de-duplicate while preserving order so the banner stays bounded
            if reason not in seen:
                seen.append(reason)
        return _ask(
            "AIQT rule abspth (absolute-paths): this command carries {} that resolve(s) against the "
            "current working directory, which can silently differ between calls. Re-issue with absolute "
            "paths, or confirm the working directory is the intended one.".format("; ".join(seen)),
            "AIQT guardrail: asked on a relative cd or redirection target in a Bash command "
            "(rule abspth).")
    return _allow()


# --- prsunc: a git discard that would lose uncommitted work ------------------------------------------
# ULTRA-CONSERVATIVE "ask unless PRISTINE and provably clean" guard (EN-6, EN-6 hardening pass over the
# GD-41 coarse cut). For a command that names any recognized lossy git verb (checkout incl -B force-create,
# switch incl -C/--force-create, restore/reset/clean/stash drop-clear/rm/branch force delete/move/copy/reset)
# the outcome is ASK unless the command is a PRISTINE SINGLE
# BARE 'git <verb>' invocation on a PROVABLY CLEAN tree (or, for that same pristine form, the LEADING opt-out
# is set). Three outcomes:
#   ALLOW  exit 0 silent  - the true boundary (a non-git command, no recognized lossy verb, an
#                           unparseable command with no lossy verb keyword); OR a PRISTINE SINGLE BARE
#                           'git <verb>' whose FORM is genuinely non-destructive (a bare no-op, reset
#                           --soft, an unforced branch-create, clean -n, stash push, branch -d); OR a
#                           PRISTINE SINGLE BARE lossy 'git <verb>' on a PROVABLY CLEAN tree (the config-
#                           forced porcelain probe reports no tracked change AND no untracked entry), so
#                           there is nothing to discard; OR the LEADING opt-out on that same pristine form.
#   DENY   permissionDecision deny - a PRISTINE SINGLE BARE WHOLE-TREE-clobbering verb (reset --hard,
#                           checkout -f with no pathspec, switch --force/--discard-changes) on a tree the
#                           probe confirms is dirty: the loss is certain.
#   ASK    permissionDecision ask  - EVERYTHING else in scope. This is deliberately the common outcome:
#                           ANY command that is not a pristine single bare git invocation - ANY shell
#                           metacharacter anywhere (even quoted), ANY wrapper/redirect/reserved-word/
#                           compound, a first command word that is not literally 'git', or an option the
#                           form-classifier cannot resolve - ASKS without ever consulting the probe; and a
#                           pristine lossy form on a not-provably-clean tree (tracked OR untracked change),
#                           a worktree the guard cannot resolve to the session cwd, a status probe that did
#                           not complete, or a softer/index-only discard (clean of untracked files, stash
#                           drop/clear, branch -D, restore --staged, mixed/path reset, rm --cached) also ASKS.
# The gate is PURELY LEXICAL and never parses the bash grammar: the presence of any shell metacharacter in a
# lossy-verb command is treated as a reason to ASK (a safe over-ask), so ONLY a metacharacter-free
# 'git <verb> <plain args>' ever reaches the probe. This closes the residual silent-allows that survived the
# coarse cut (a shell 'if'/'for', a backtick or '$()' substitution, a '|&' or leading/interspersed redirect,
# and ANY wrapper in front of git - sudo/stdbuf/doas/setsid/eval/sh -c/...: the raw 'git'+work-losing-verb
# scan is trusted UNCONDITIONALLY, not an enumerated wrapper list, so an un-listed wrapper is caught): ASK.
# That "cannot slip" is NOT categorical: a wrapper that ALSO fragments the command word 'git' or the verb so
# neither the token scan nor the raw scan sees a contiguous git+verb keyword reads as "no recognized lossy
# verb" and is silently ALLOWED (a DISCLOSED best-effort residual, see the module docstring; GD-34
# do-not-chase). The raw scan also OVER-ASKS in the SAFE direction: a command that merely CONTAINS a git
# token and a lossy verb as TEXT while running no discard ('echo git branch', 'git log | grep branch') still
# ASKS; narrowing that is the whack-a-mole GD-34 rejected, so the over-ask is disclosed, not chased.
# The status probe (git -c status.showUntrackedFiles=all status --porcelain --untracked-files=all) is
# read-only and offline and FORCES untracked reporting so a repo-local status.showUntrackedFiles=no config
# cannot hide an untracked file. The classifier never mutates working state; BENEATH it, the EN-6 recovery
# layer (see the block comment above _SNAPSHOTTABLE_VERBS) is SIDE-EFFECTING - it writes an inert
# refs/aiqt-recovery/* snapshot ref and an external ledger for a not-provably-clean discard - but writes only
# git objects and one private ref, never the real index, worktree, HEAD, or a branch. HONEST RESIDUAL (not
# caught by a lexical hook): a git alias or shell function that renames git, a discard performed outside the
# Bash tool, or persistent shell/config state set in a prior turn; the recovery/snapshot layer backstops a
# discard it CAN see, but cannot snapshot content the probe itself cannot see (assume-unchanged/skip-worktree
# marks or submodule.<name>.ignore hide work from the probe) nor ignored files (git add --all excludes them).
# An explicit GUARDRAIL_ALLOW_DISCARD truthy assignment LEADING a pristine bare git command opts out to ALLOW.
# The value capture is `(.*)` (matches an EMPTY value, `GUARDRAIL_ALLOW_DISCARD=`), consulted with fullmatch, so
# an exact leading assignment with an empty value updates the last-wins value to '' (bash: effective empty =
# falsy), and `GUARDRAIL_ALLOW_DISCARD=1 GUARDRAIL_ALLOW_DISCARD= git ...` does NOT opt out (the empty final
# assignment wins). A `(.+)` capture would ignore the empty final assignment and wrongly honour the earlier 1.
_DISCARD_OPTOUT_RE = re.compile(r"^GUARDRAIL_ALLOW_DISCARD=(.*)$")
_DISCARD_FALSY = frozenset(("", "0", "false", "no", "off"))  # value (case-insensitive) that is NOT truthy
# Fallback-only raw-string probes, used when the shared tokenizer cannot parse the command (an unbalanced quote or an unsupported construct). We cannot
# segment safely, so scan the RAW string for git AND a recognized work-losing verb: any of the
# always-lossy verbs, or 'branch' in ANY form. On the raw path we do NOT parse branch flags: an unparseable
# 'git branch -d -f topic <heredoc>' / '-df' / '--del --for' cannot be told from a create or a list, so ANY
# raw 'git' + 'branch' is treated as lossy and ASKS regardless of a delete flag. This over-asks a benign
# unparseable 'git branch --list' (rare, safe) and ends the raw-branch silent-allow gap.
# A hit -> ASK (cannot prove safe); no hit -> ALLOW (the true boundary). Mirrors how diff_source/
# commit_identity fall back to a conservative raw scan on a parse failure. The opt-out is NOT consulted on
# this path: the guard cannot parse the command, so it cannot trust an opt-out-looking prefix inside it; an
# unparseable in-scope command ALWAYS ASKS. The opt-out is honoured ONLY on a PARSEABLE pristine bare command.
_RAW_GIT_RE = re.compile(r"(?i)\bgit\b")
_RAW_LOSSY_VERB_RE = re.compile(r"(?i)\b(?:checkout|switch|restore|reset|clean|rm|stash)\b")
_RAW_BRANCH_RE = re.compile(r"(?i)\bbranch\b")
# Shell wrappers/prefixes that stand IN FRONT of the git command so 'git <lossy>' is not the invocation
# actually being classified. The EN-6 ultra-conservative pass widens the GD-41 set (command/exec/builtin/
# env/xargs/time/!) with the privilege/scheduling/interpreter prefixes sudo/nice/timeout/nohup/sh/bash: when
# one of these is the command word and a lossy git verb is present, the guard cannot classify with certainty,
# so it ASKS. (A pristine bare git never has a wrapper as its command word, so this only widens the ask set.)
_WRAPPER_WORDS = frozenset((
    "command", "exec", "builtin", "env", "xargs", "time", "!",
    "sudo", "nice", "timeout", "nohup", "sh", "bash"))
# The ULTRA-CONSERVATIVE pristine gate. A lossy-verb command is a PRISTINE SINGLE BARE 'git <verb>'
# invocation only when the RAW command string carries NONE of this shell structure ANYWHERE, even inside
# quotes (a deliberate over-ask): a metacharacter (; | & < > ( ) { } $ backtick backslash ! newline, which
# also covers &&/||/|&, every redirection form, and command/process substitution) or a shell reserved word.
# The gate NEVER parses the grammar; this lexical scan stands in for it, so only a metacharacter-free
# 'git <verb> <plain args>' ever reaches the clean probe. Everything else in scope ASKS.
_SHELL_META_RE = re.compile(r"[;|&<>(){}$`\\!*?\[\n\r]")  # includes glob chars *?[ (bash filename expansion)
_SHELL_RESERVED_WORDS = frozenset((
    "if", "then", "elif", "else", "fi", "for", "while", "until", "do", "done",
    "case", "esac", "function", "select", "in", "[[", "]]", "{", "}"))
# The safe alternatives named in every DENY/ASK reason, so the actor is never left without a next step.
# The opt-out guidance is PATH-AWARE and appended by the caller. The opt-out is honoured on the command AS
# ISSUED whenever a leading GUARDRAIL_ALLOW_DISCARD=1 prefix short-circuits to ALLOW: on a pristine bare
# command the leading prefix opts THIS command out (_OPTOUT_PRISTINE), and because that short-circuit fires
# BEFORE the repository-view-redirect gate, a pristine repository-view-redirected form (a 'git -C <dir>
# <verb>' or an ambient-GIT_* form that ASKS at that gate) is ALSO opted out by prefixing the command as
# issued, keeping its -C (_OPTOUT_PRISTINE too). Only on a raw/unparseable or non-pristine command, where no
# pristine bare form is present to carry the prefix, is the opt-out NOT honoured on the command as issued, so
# the actor is told to RE-ISSUE the discard as a parseable pristine bare form carrying the prefix
# (_OPTOUT_REISSUE).
_DISCARD_ALTS = (
    "Safe alternatives: commit or 'git stash' your work first; scope the revert with an explicit "
    "'-- <paths>'; unstage without touching the worktree via 'git restore --staged' or 'git rm "
    "--cached'; change branch with 'git switch' (it carries non-conflicting changes and aborts rather than "
    "overwrite them).")
# Opt-out guidance for a PRISTINE bare form, where the leading prefix opts THIS command out.
_OPTOUT_PRISTINE = (
    " Or, for a known-safe discard, prefix this command with GUARDRAIL_ALLOW_DISCARD=1 to override this "
    "guard.")
# Opt-out guidance for a raw/unparseable or non-pristine form, where the opt-out is NOT honoured on the
# command as issued: re-issue it as a parseable pristine bare 'git <verb>' with the leading prefix. A
# repository-view-redirected form does NOT use this: it is pristine-lexically, so its leading prefix opts it
# out on the command as issued (_OPTOUT_PRISTINE, keeping its -C), short-circuiting before the redirect gate.
_OPTOUT_REISSUE = (
    " For a known-safe discard, re-issue it as a parseable pristine bare 'git <verb>' command carrying a "
    "leading GUARDRAIL_ALLOW_DISCARD=1 prefix; the opt-out is honoured only on that pristine bare form, not "
    "on the command as issued here.")


def _segment_has_optout(tokens):
    """True when THIS segment carries a truthy GUARDRAIL_ALLOW_DISCARD as a LEADING env-assignment (the
    documented 'GUARDRAIL_ALLOW_DISCARD=1 git ...' prefix on the git command itself). Only the leading
    assignment region (the tokens before this segment's command word) is inspected, so the same string
    buried in an argument does NOT count. The caller consults this ONLY on a segment whose command word is
    git (GD-41 blocker 4), so an opt-out leading a NON-git command ('GUARDRAIL_ALLOW_DISCARD=1 true; git
    reset --hard') never disables the guard on the later git command. A value in {'', '0', 'false', 'no',
    'off'} (case-insensitive) is NOT truthy. When the leading region repeats the assignment, bash last-wins
    applies: only the LAST GUARDRAIL_ALLOW_DISCARD assignment's value is evaluated (=1 then =0 does NOT opt
    out)."""
    last = None
    for tok in tokens[:_command_word_index(tokens)]:
        m = _DISCARD_OPTOUT_RE.fullmatch(tok)
        if m:
            last = m.group(1)  # bash last-wins: keep the LAST leading assignment's value, evaluate only it
    return last is not None and last.lower() not in _DISCARD_FALSY


def _raw_has_lossy_git(command):
    """True when the RAW command string names git AND a recognized work-losing verb (an always-lossy verb,
    or 'branch' in ANY form: the raw path does not parse branch flags, so any raw 'git' + 'branch' is
    treated as lossy regardless of a delete flag). A coarse fail-safe used both by the unparseable-command
    fallback and by the wrapper-obscured path (GD-41 blocker 8), where a wrapper hides the git verb from the
    token scan; a hit there means the guard cannot classify with certainty and ASKS."""
    if not _RAW_GIT_RE.search(command):
        return False
    return bool(_RAW_LOSSY_VERB_RE.search(command) or _RAW_BRANCH_RE.search(command))


def _git_sub_and_args(tokens):
    """(sub, args): the git subcommand and the token list AFTER it, or (None, []) when there is no
    subcommand. Reuses the _command_word_index skip of leading env assignments and the _GIT_ARG_OPTS skip,
    so a '-C DIR' value is never mistaken for the subcommand."""
    i = _command_word_index(tokens) + 1  # skip leading env assignments and the command word itself
    n = len(tokens)
    while i < n:
        token = tokens[i]
        if token.startswith("-"):
            if "=" not in token and token in _GIT_ARG_OPTS:
                i += 2
            else:
                i += 1
            continue
        return token, tokens[i + 1:]
    return None, []


# The option-parsing boundary tokens: after either, every remaining token is an operand (a pathspec or
# ref), never an option, so a token that merely LOOKS like an option past this point is a literal operand.
_EOO_TOKENS = frozenset(("--", "--end-of-options"))


def _split_pre_post(args):
    """Split a subcommand's arg list at the FIRST option-boundary token ('--' or '--end-of-options').
    Returns (pre, post, had_sep): pre is the option region before it, post is every operand after it (all
    pathspecs, verbatim), had_sep says a boundary token was present."""
    for idx, a in enumerate(args):
        if a in _EOO_TOKENS:
            return args[:idx], args[idx + 1:], True
    return args, [], False


def _has_short(tokens, ch):
    """True when a clustered short-flag token (a single '-' then letters, e.g. '-fd') carries the letter
    ch. Spots '-f' inside a cluster (checkout '-f', clean '-fd'), '-p', '-S'/'-W' (restore)."""
    for t in tokens:
        if t.startswith("-") and not t.startswith("--") and len(t) > 1 and ch in t[1:]:
            return True
    return False


def _has_long_prefix(tokens, full):
    """True when a '--<name>' option token in tokens is a CONSERVATIVE prefix of `full`. The match is
    deliberately broad: it fires whenever `name` is any leading substring of `full`, WITHOUT verifying that
    git itself would accept the abbreviation. Git accepts many UNAMBIGUOUS abbreviations ('--patc' for
    '--patch', '--del' for '--delete', '--dis' for '--discard-changes'), but it REJECTS an AMBIGUOUS one:
    'git branch --for' is ambiguous with '--format' and 'git switch --for' with '--force-create', so git
    errors rather than running '--force'. This guard intentionally treats such an ambiguous force-prefix
    ('--for') as force ANYWAY, routing it to ASK or DENY. The name compared is the part before any '=', so
    '--orphan=x' matches 'orphan'. A bare '--' (empty name) never matches. GD-41 blocker 5: a destructive
    option must be recognized by prefix, not only by its full spelling, or an abbreviated
    force/patch/delete/discard slips through as an inert token and is silently allowed. Erring toward a
    MATCH is safe: over-recognizing a destructive option, even an abbreviation git would reject as
    ambiguous, only routes a form to ASK or DENY, never to a silent allow."""
    for t in tokens:
        if not t.startswith("--"):
            continue
        name = t.split("=", 1)[0][2:]
        if name and full.startswith(name):
            return True
    return False


# --- the one probe kept: the coarse whole-tree clean signal ------------------------------------------

# The ambient git environment could redirect a real-state git call (the clean probe, the recovery
# snapshot) to a DECOY repository, inject config into it, hide content from it, or make a "read-only" call
# WRITE a trace file: an inherited GIT_* var can point git at a different index, object store, work tree,
# ref namespace, or discovery boundary than the one at `-C <repo>` (producing a false "provably clean", a
# false recovery point, or a dirty-tree ALLOW left unchanged), propagate config through the `git -c`
# GIT_CONFIG_PARAMETERS channel (able to hide untracked content via core.excludesFile or inject a
# filter.*.clean that runs during the snapshot `git add --all`), suppress system config via
# GIT_CONFIG_NOSYSTEM, redirect attribute lookup through GIT_ATTR_SOURCE, or (git treats an absolute
# GIT_TRACE value as a FILE PATH and APPENDS trace output to it) make even the read-only status probe and
# the recovery git calls WRITE a file, possibly inside the protected worktree, violating the read-only/inert
# posture. Rather than ENUMERATE this family (rounds 4-5 kept finding new members: GIT_CONFIG_*, then
# GIT_TRACE*, then GIT_ATTR_SOURCE), every real-state call takes an ALLOWLIST posture: _isolate_git_env
# scrubs EVERY ambient GIT_*-prefixed var before the caller applies its own env, so after the scrub a
# real-state call observes the ACTUAL repo at `-C <repo>` rather than an ambient-env decoy and writes no
# trace file; a snapshot call's own GIT_INDEX_FILE (supplied via env_extra) still wins because env_extra is
# applied AFTER the scrub. This is BOUNDED, not categorical: the allowlist scrub closes the whole ambient-env
# class at once, but the residual is NOT limited to on-disk config - it spans the non-GIT_ environment
# (HOME/XDG_CONFIG_HOME/PATH/TMPDIR), on-disk git configuration AND attributes (repo/global/system .gitconfig
# and .gitattributes), index and ignore state, submodules and embedded repos, configured hooks and filters,
# PATH-based git resolution, and partial-clone object availability, all of which git reads by design and none
# neutralized here.


# The FIXED INTERNAL identity the recovery snapshot's `git commit-tree` commits under. The allowlist scrub
# strips every ambient GIT_* (including any GIT_AUTHOR_*/GIT_COMMITTER_*) AND neutralizes on-disk config's
# reach for the call, so with no ambient identity re-applied commit-tree would FALL BACK to user.name/email
# and then FAIL on a host that has none (a CI runner or a fresh install with no global gitconfig), silently
# disabling the recovery backstop there. Re-applying this fixed identity after the scrub makes commit-tree
# depend on NO ambient state; a deterministic identity is also correct on its own terms, since a recovery
# commit is attributed to the guard, not to the user. The address is a fixed non-routable localhost one.
_RECOVERY_IDENTITY_NAME = "aiqt-recovery"
_RECOVERY_IDENTITY_EMAIL = "aiqt-recovery@localhost"


def _isolate_git_env(env):
    """Scrub EVERY ambient GIT_*-prefixed var from env in place, re-assert the PROTECTIVE vars and the fixed
    recovery commit identity, and return it (allowlist posture: no ambient git env is trusted). A real-state
    git call is fully specified by `-C <repo>` plus the few vars the caller re-applies AFTER this scrub
    (GIT_OPTIONAL_LOCKS for the read-only probe; a temp GIT_INDEX_FILE via env_extra for a snapshot), so it
    observes the ACTUAL on-disk repo and writes no trace file. AFTER the scrub this SETS GIT_NO_LAZY_FETCH=1
    and GIT_TERMINAL_PROMPT=0, so the scrub cannot strip an operator's offline/non-interactive posture:
    without them a partial-clone probe/add could LAZY-FETCH (network I/O, writes objects) instead of failing
    offline, and prompting could be re-enabled. It ALSO re-applies GIT_AUTHOR_NAME/EMAIL and
    GIT_COMMITTER_NAME/EMAIL as the fixed _RECOVERY_IDENTITY_* so the snapshot's `git commit-tree` never
    depends on an ambient or on-disk identity the scrub removed (without it commit-tree FAILS where no git
    identity is configured, silently disabling the recovery backstop); the read-only probes simply ignore
    it. A caller's own later env_extra (a temp GIT_INDEX_FILE) still wins because it is applied
    after this returns. Over-scrubbing fails SAFE: any GIT_* the call genuinely needed makes it error, and
    the caller treats that as a probe/snapshot FAILURE (None / SubprocessError) -> fail-to-ASK, never a
    silent allow. This closes the whole ambient-env class at once (GIT_CONFIG_*, GIT_CONFIG_PARAMETERS,
    GIT_TRACE*, GIT_ATTR_SOURCE, GIT_DIR/GIT_WORK_TREE, ...) instead of enumerating it. The residual is NOT
    limited to on-disk config: it spans the non-GIT_ environment (HOME/XDG_CONFIG_HOME/PATH/TMPDIR), on-disk
    git configuration AND attributes (repo/global/system .gitconfig and .gitattributes), index and ignore
    state, submodules and embedded repos, configured hooks and filters, PATH-based git resolution, and
    partial-clone object availability."""
    for _k in [k for k in env if k.startswith("GIT_")]:
        env.pop(_k, None)
    # Re-assert the offline + non-interactive posture the scrub would otherwise strip (Class B): keep a
    # partial-clone operation from lazy-fetching over the network, and keep git from ever prompting.
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    # Re-assert a fixed internal commit identity the scrub removed, so the snapshot's `git commit-tree`
    # never falls back to (now-scrubbed) ambient config and FAILS where no git identity is configured; the
    # read-only probes ignore it. A recovery commit is the guard's, not the user's, so the identity is fixed.
    env["GIT_AUTHOR_NAME"] = _RECOVERY_IDENTITY_NAME
    env["GIT_AUTHOR_EMAIL"] = _RECOVERY_IDENTITY_EMAIL
    env["GIT_COMMITTER_NAME"] = _RECOVERY_IDENTITY_NAME
    env["GIT_COMMITTER_EMAIL"] = _RECOVERY_IDENTITY_EMAIL
    return env


def _tree_is_clean(repo):
    """The clean-tree signal, the ONLY probe this guard keeps, hardened to be CONFIG-PROOF. True when the
    read-only porcelain probe reports NOTHING that a lossy verb could destroy: no uncommitted tracked change
    (any staged or unstaged modification, in EITHER porcelain column) AND no untracked ('??') entry. False
    when it reports either, None when the probe could not run (a subprocess error, a non-zero return, an
    unreadable repo). Untracked files are uncommitted work a force-checkout, a 'git clean', or a 'git reset
    --hard' can destroy, so an untracked-only-dirty tree is NOT provably clean.

    The probe FORCES untracked reporting - 'git -c status.showUntrackedFiles=all status --porcelain
    --untracked-files=all' - so a repo-local 'status.showUntrackedFiles=no' config cannot hide an untracked
    file from the guard and thereby win a silent allow for reset --hard / checkout -f / clean -f. The '-c'
    override and the explicit '--untracked-files=all' both defeat the config; either alone would suffice, and
    carrying both keeps the intent legible. An ignored '!!' entry is treated as clean (porcelain does not emit
    '!!' without --ignored anyway). A forced checkout or 'clean -x' CAN overwrite/remove an ignored file, but
    probing --ignored would ASK on every repo carrying build artifacts, so ignored-file loss on those forms is
    a DISCLOSED residual the recovery layer backstops (every non-dry-run clean already ASKS regardless).
    Deliberately coarse: ANY tracked change or untracked file anywhere makes the tree not-provably-clean.
    Offline, read-only, 5s timeout; the guard never mutates the repo. GIT_OPTIONAL_LOCKS=0 keeps this probe
    from refreshing/writing the real `.git/index`, and EVERY ambient GIT_*-prefixed var is scrubbed via
    _isolate_git_env (the allowlist posture, re-applying only GIT_OPTIONAL_LOCKS after the scrub) so the
    probe reads the REAL repo at `-C <repo>` rather than a foreign preset that could redirect it to a decoy
    clean repo and win a false ALLOW, and writes no ambient GIT_TRACE file."""
    try:
        env = _isolate_git_env(dict(os.environ))
        env["GIT_OPTIONAL_LOCKS"] = "0"
        result = subprocess.run(
            ["git", "-C", repo, "-c", "status.showUntrackedFiles=all",
             "status", "--porcelain", "--untracked-files=all"],
            capture_output=True, text=True, timeout=5, env=env)
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            if not line or line[:2] == "!!":
                continue  # only an ignored entry is treated as clean
            return False  # a tracked change (staged or unstaged) OR an untracked file: not provably clean
        return True
    except Exception:
        return None


# --- verb-form recognition (coarse; erring toward lossy) ---------------------------------------------
# Each _*_role returns (role, kind): role is one of "allow" (this FORM never discards tracked work),
# "ask" (a softer discard that ASKS unconditionally, not gated on the tracked-tree probe - clean of
# untracked files, stash drop/clear, branch -D), "scoped" (an index- or worktree-touching discard: ALLOW on
# a provably-clean tree, else ASK; this now includes the index-only forms restore --staged, mixed/path
# reset, and rm --cached, which can erase staged-only content, GD-41 blocker 6), or "clobber" (a WHOLE-TREE
# overwrite: ALLOW on a clean tree, DENY on a confirmed-dirty tree). kind is a short human label. This
# recognition is purely lexical and never probes to prove an individual dirty-tree form safe; it only
# classifies the FORM, matching destructive options by CONSERVATIVE PREFIX (blocker 5; an ambiguous
# force-prefix like '--for' is treated as force, erring safe) and respecting a '--'
# operand boundary (blocker 3), then the handler gates a scoped/clobber form on the single whole-tree clean
# probe AND on the command being a single simple 'git <verb>' invocation.

# git checkout/switch short options that CONSUME a NEW-BRANCH-NAME argument: '-b'/'-B' (checkout create /
# force-create), '-c'/'-C' (switch create / force-create). The option letter itself is a genuine flag, but
# the REST of its cluster token (attached '-bfoo') or the NEXT token (separated '-b foo') is that branch
# name and must NOT be char-scanned as clustered force flags. Mirrors the branch '-u<upstream>' parser
# (_branch_parse_options, F-82). checkout has no -c/-C and switch has no -b/-B, so one shared set is safe.
_CHECKOUT_SWITCH_NAME_OPTS = frozenset(("b", "B", "c", "C"))


def _checkout_switch_parse_options(pre):
    """Parse a checkout/switch option region (already split before any '--') into (short_flags, operands).
    short_flags is the set of genuine short flag letters; operands is the list of bare operands. A branch-
    name-taking short option ('-b'/'-B' for checkout, '-c'/'-C' for switch) is recorded as a flag, then the
    remainder of its cluster token (attached '-bfoo') or the next token (separated '-b foo') is its NEW-
    BRANCH-NAME value and is NOT char-scanned as force flags. This mirrors _branch_parse_options (F-82) and
    closes the F-85 over-restriction where an attached name like '-bfoo' (the 'f') or '-bBranch' (the 'B')
    was char-scanned as carrying -f/-B and mis-routed to DENY/ASK. Long options are not char-scanned here
    (force/orphan/discard-changes/force-create match by prefix on `pre`)."""
    short_flags = set()
    operands = []
    skip_value = False  # the previous token opened a separated branch-name slot (e.g. '-b <name>')
    for tok in pre:
        if skip_value:
            skip_value = False
            continue  # this token is a prior option's branch-name VALUE, not a flag or an operand
        if tok.startswith("--"):
            continue  # long options match by prefix on `pre`, not char-scanned here
        if tok.startswith("-") and len(tok) > 1:
            body = tok[1:]
            for i, ch in enumerate(body):
                if ch in _CHECKOUT_SWITCH_NAME_OPTS:  # record the option, then its branch name is the
                    short_flags.add(ch)                # rest of this token (or the next token)
                    if i == len(body) - 1:
                        skip_value = True  # a bare '-b': the name is the next token
                    break  # stop the cluster scan; the remainder is the new-branch name, not flags
                short_flags.add(ch)
            continue
        operands.append(tok)  # a bare operand (a branch or a pathspec)
    return short_flags, operands


def _checkout_role(args):
    """git checkout. Force ('-f'/'--force', abbreviations included) is decided FIRST (GD-41 blocker 7). A
    '-B' force branch-create/RESET overwrites an existing branch ref and can orphan committed commits (the
    same reflog-recoverable loss class as 'git branch -f'/'-M'/'-C'), so it ASKS unconditionally, INCLUDING
    when combined with other flags (F-81), before the unforced branch-create allow. A plain branch-create
    ('-b'/'--orphan') only allows when force is ABSENT, because a FORCED branch-create can discard, so
    'checkout -f -b <name>' must fall through to a lossy classification, not the early
    allow. A '-m'/'--merge' or '--conflict[=<style>]' checkout (matched like the switch classifier,
    unambiguous-prefix aware) does a THREE-WAY merge that can overwrite local changes, so even combined
    with a branch-create it is not unconditionally safe -> scoped (ALLOW on a provably-clean tree, ASK on a
    dirty one), decided BEFORE the plain branch-create allow (F-88); a plain '-b'/'--orphan' create with NO
    merge option stays allow. The new-branch NAME of '-b'/'-B' is consumed as that option's ARGUMENT (attached '-bfoo' or
    separated '-b foo') and is NOT char-scanned as force flags, so '-bfoo'/'-bBranch' ALLOW and are never
    mis-read as carrying -f/-B (F-85; see _checkout_switch_parse_options). '-p'/'--patch' (prefix-matched)
    interactively discards worktree hunks -> scoped. A forced
    checkout that carries a BARE OPERAND ('checkout -f <operand>') is lexically ambiguous - the operand may
    be a branch (a whole-tree switch) OR a pathspec (a scoped path-restore), and it is no longer
    disambiguated by a rev-parse probe - so it is treated as -> scoped (which ASKS on a not-provably-clean
    tree; recoverable and human-gated), never a hard DENY that would false-block a legitimate forced
    path-restore. Any '-- <paths>' or other bare-operand form is scoped for the same reason. Only an
    operand-FREE forced checkout ('checkout -f' with no branch and no pathspec) clobbers the whole worktree
    with certainty -> clobber (which DENIES on a confirmed-dirty tree). A bare 'git checkout' with no options
    and no operands has no worktree effect -> allow."""
    pre, post, _had_sep = _split_pre_post(args)
    if _has_long_prefix(pre, "pathspec-from-file"):  # prefix-matched: '--pathspec-from-f' too
        return ("scoped", "git checkout --pathspec-from-file (reverts paths listed in a file)")
    short_flags, operands = _checkout_switch_parse_options(pre)  # '-b'/'-B' consume their branch name (F-85)
    force = "f" in short_flags or _has_long_prefix(pre, "force")
    if "B" in short_flags:  # -B force-creates/RESETS a branch ref, orphaning committed commits (F-81)
        return ("ask", "git checkout -B (a force branch-create/reset that overwrites an existing branch "
                       "ref and may orphan its commits)")
    if not force and ("m" in short_flags or _has_long_prefix(pre, "merge")
                      or _has_long_prefix(pre, "conflict")):  # F-88: a three-way merge, even with a -b
        return ("scoped", "git checkout --merge/--conflict (a three-way merge that can overwrite local "
                          "changes)")  # decided BEFORE the branch-create allow, mirroring the switch classifier
    branch_create = ("b" in short_flags or _has_long_prefix(pre, "orphan"))
    if branch_create and not force:
        return ("allow", None)  # create/switch to a new branch; git carries changes and aborts on conflict
    if "--patch" in pre or "p" in short_flags or _has_long_prefix(pre, "patch"):
        return ("scoped", "git checkout -p/--patch (an interactive worktree-hunk discard)")
    has_paths = bool(post) or bool(operands)
    # A forced branch-create ('checkout -f -b <name>') is lossy but NOT the operand-free whole-tree clobber
    # (blocker 7): its branch name is consumed by -b so it leaves no operand, yet it must stay SCOPED (a
    # recoverable ASK), not clobber. Only a force with NO branch-create and NO operand is the certain
    # whole-tree clobber. (Pre-F-85 the branch name was mis-counted as a bare operand and reached scoped via
    # has_paths; parsing it as -b's argument keeps that outcome without relying on the mis-count.)
    if force and not has_paths and not branch_create:
        return ("clobber", "git checkout -f (a forced branch switch that overwrites the worktree)")
    if has_paths or branch_create:
        return ("scoped", "git checkout (a worktree revert; a forced or branch-create form can discard)")
    if pre:  # options present but none recognized as safe (an abbreviated/exotic option) -> do not trust
        return ("scoped", "git checkout (an option this guard cannot prove non-destructive)")
    return ("allow", None)  # a truly bare 'git checkout': no options, no operand, no worktree effect


def _switch_role(args):
    """git switch. '-f'/'--force'/'--discard-changes' overwrites the worktree (whole-tree) -> clobber; force
    and discard-changes are matched by CONSERVATIVE prefix (blocker 5), so '--dis' is recognized and an
    ambiguous '--for' (which git itself rejects for switch as ambiguous with '--force-create') is treated as
    force anyway, erring safe.
    A '-C'/'--force-create' force branch-create/RESET (matched by prefix too) overwrites an existing branch
    ref and can orphan committed commits (the same reflog-recoverable loss class as 'git branch
    -f'/'-M'/'-C'), so it ASKS (F-81); plain '-c' create keeps the allow. The new-branch NAME of '-c'/'-C'
    is consumed as that option's ARGUMENT (attached '-cfoo' or separated '-c foo') and is NOT char-scanned
    as force flags, so '-cfeature' ALLOWs and is never mis-read as carrying -f/-C (F-85; see
    _checkout_switch_parse_options). '--force' is decided FIRST, so a
    genuine worktree clobber still DENIES rather than being downgraded to the force-create ASK.
    A '-m'/'--merge' or '--conflict[=<style>]' switch performs a THREE-WAY merge into the worktree that can
    overwrite local changes, so it is not unconditionally safe -> scoped (ALLOW on a provably-clean tree, ASK
    on a dirty one), matched by prefix too. A plain switch preserves non-conflicting local changes and aborts
    only when the switch would lose them (git protects), so it is not a silent discard -> allow."""
    pre, _post, _had_sep = _split_pre_post(args)
    short_flags, _operands = _checkout_switch_parse_options(pre)  # '-c'/'-C' consume their branch name (F-85)
    if ("f" in short_flags or _has_long_prefix(pre, "force")
            or _has_long_prefix(pre, "discard-changes")):
        return ("clobber", "git switch --force/--discard-changes (overwrites the worktree)")
    if "C" in short_flags or _has_long_prefix(pre, "force-create"):
        return ("ask", "git switch -C/--force-create (a force branch-create/reset that overwrites an "
                       "existing branch ref and may orphan its commits)")
    if "m" in short_flags or _has_long_prefix(pre, "merge") or _has_long_prefix(pre, "conflict"):
        return ("scoped", "git switch --merge/--conflict (a three-way merge that can overwrite local changes)")
    return ("allow", None)


def _restore_role(args):
    """git restore reverts tracked content, and NO form is unconditionally safe (GD-41 blocker 6): a
    worktree restore drops uncommitted edits, '-p'/'--patch' discards selected hunks, and even a pure
    '--staged' unstage can erase staged-ONLY content (present in the index but not HEAD or the worktree).
    So every restore routes through the whole-tree clean probe -> scoped: it ALLOWS on a provably-clean tree
    (a clean index has no staged-only content to lose) and ASKS on a dirty one. The earlier cut allowed a
    '--staged' unstage unconditionally, which silently discarded staged-only work."""
    return ("scoped", "git restore (reverts tracked content; --staged can erase staged-only changes)")


def _rm_role(args):
    """git rm removes tracked content, and NO form is unconditionally safe (GD-41 blocker 6): plain rm drops
    uncommitted worktree changes, and '--cached' unstages and can erase staged-ONLY content (present in the
    index but not HEAD or the worktree). So both route through the whole-tree clean probe -> scoped: ALLOW on
    a provably-clean tree, ASK on a dirty one. This also means an operand after '--' (git rm -f -- --cached,
    GD-41 blocker 3) can never be misread as the '--cached' option to win an allow: rm is scoped either way.
    The earlier cut allowed '--cached' unconditionally, which silently discarded staged-only work."""
    return ("scoped", "git rm (removes tracked content, dropping uncommitted or staged-only changes)")


def _reset_role(args):
    """git reset. The EFFECTIVE (last-wins) mode from the option region decides: an effective '--hard'
    overwrites the whole worktree -> clobber; only '--soft' is unconditionally safe -> allow (it moves HEAD
    only, leaving the index AND the worktree intact). Every other mode touches the index or worktree and can
    lose work, so it routes through the whole-tree clean probe -> scoped: '--merge' (may abort, may lose),
    '--mixed'/'--keep', a path-scoped reset, or NO mode flag (git defaults to --mixed, which unstages and can
    erase staged-ONLY content, GD-41 blocker 6 - the earlier cut allowed these unconditionally). Mode flags
    are matched by unambiguous PREFIX ('--ha' == '--hard'), and an ambiguous bare '--m' (mixed OR merge) is
    scoped either way; option parsing stops at the first '--'/'--end-of-options' so a mode-looking operand
    past it is a pathspec, not a mode."""
    pre, _post, _had_sep = _split_pre_post(args)
    if any(a == "--pathspec-from-file" or a.startswith("--pathspec-from-file=") for a in pre):
        return ("scoped", "git reset --pathspec-from-file (a path-scoped reset from a file)")
    mode = None  # "clobber" / "soft" / "scoped"
    for a in pre:
        if not (a.startswith("--") and "=" not in a):
            continue
        name = a[2:]
        if not name:
            continue
        if "hard".startswith(name):
            mode = "clobber"
        elif "soft".startswith(name):
            mode = "soft"
        elif ("merge".startswith(name) or "mixed".startswith(name) or "keep".startswith(name)):
            mode = "scoped"  # index/worktree-touching (an ambiguous '--m' also lands here): err toward probe
    if mode == "clobber":
        return ("clobber", "git reset --hard")
    if mode == "soft":
        return ("allow", None)  # HEAD-only: the index and worktree are untouched
    return ("scoped", "git reset (an index or worktree reset that can drop staged or unstaged changes)")


# git clean options that CONSUME the following token (so its value must not be read as a flag): '-e'/
# '--exclude PAT'. The '--exclude=PAT' inline shape carries its value in the same token, consuming none.
_CLEAN_ARG_OPTS = frozenset(("-e", "--exclude"))


def _clean_is_dry_run(pre):
    """True when a git clean option region (already split before any '--') is a genuine DRY RUN
    (-n/--dry-run) that removes nothing. ULTRA-CONSERVATIVE about the arg-consuming '-e'/'--exclude': when
    one is present the guard CANNOT reliably tell a real '-n' flag from an exclude PATTERN token that merely
    looks like '-n' (git clean -f -e '*.keep' -n, or the adversarial git clean -f -e -n where '-n' is the
    pattern), so it does NOT trust '-n' at all and returns False, routing the clean to its unconditional ASK.
    A '-n'/'--dry-run' with no arg-consuming option present still reports a dry run and allows."""
    for t in pre:
        if t in _CLEAN_ARG_OPTS or t.startswith("--exclude="):
            return False  # a separate/inline arg-consuming exclude: do not trust '-n'
        if t.startswith("-") and not t.startswith("--") and "e" in t[1:]:
            return False  # an ATTACHED short exclude ('-en' is '-e' with value 'n'): '-n' not trustworthy
    if _has_long_prefix(pre, "no-dry-run"):
        return False  # the negation (prefix-matched, e.g. '--no-dry-r') turns the dry run back on
    return "--dry-run" in pre or _has_short(pre, "n")


# git branch long options that CONSUME the following token as a REQUIRED separated value, so that value is
# never read as an operand or scanned as clustered force flags. Only required-arg options are listed:
# optional-arg long options (--track/--contains/--merged/--points-at/--color/--abbrev) take a value only in
# the attached '--opt=val' form and never consume a following token.
_BRANCH_LONG_ARG_OPTS = ("set-upstream-to", "sort", "format")
# Long options a '--<name>' abbreviation could ALSO mean; when a name could abbreviate one of these
# destructive options it is NOT treated as arg-consuming, so an ambiguous '--f' errs toward ASK rather than
# swallowing the following operand.
_BRANCH_FORCE_OPTS = ("force", "delete", "move", "copy")


def _branch_long_takes_arg(name):
    """True when the '--<name>' branch option (its '--' and any '=value' already stripped) is an unambiguous
    PREFIX of a git-branch long option that REQUIRES a separated value, so the NEXT token is that value
    rather than a flag or an operand. When `name` could also abbreviate a destructive option (--force/
    --delete/--move/--copy) it is NOT treated as arg-consuming, so an ambiguous '--f' still routes to ASK
    rather than swallowing the following operand and winning a silent allow."""
    if any(full.startswith(name) for full in _BRANCH_FORCE_OPTS):
        return False
    return any(full.startswith(name) for full in _BRANCH_LONG_ARG_OPTS)


def _branch_parse_options(pre):
    """Parse a 'git branch' option region (already split before any '--') into (short_flags, operands).
    short_flags is the set of genuine short flag letters; operands is the list of bare operands. An
    argument-taking option's VALUE is never added to either: the arg-taking short option is '-u <upstream>'
    (attached '-u<val>' or separated '-u <val>'), so a short cluster stops scanning at the first '-u' and the
    remainder of that token (or the next token) is the upstream value, NOT clustered force flags. This closes
    the F-82 over-ASK regression where a blind char-scan read '-ufoo'/'-uMain'/'-uCandidate' as carrying
    -f/-M/-C/-d. Long options are not char-scanned here (the force forms match them by prefix on `pre`); a
    required-arg long option ('--set-upstream-to'/'--sort'/'--format') consumes its separated value so it is
    not mistaken for an operand or a flag."""
    short_flags = set()
    operands = []
    skip_value = False  # the previous token opened a separated-value slot (e.g. '-u <upstream>')
    for tok in pre:
        if skip_value:
            skip_value = False
            continue  # this token is a prior option's VALUE, not a flag or an operand
        if tok.startswith("--"):
            name = tok.split("=", 1)[0][2:]
            if name and "=" not in tok and _branch_long_takes_arg(name):
                skip_value = True  # its value is the next token
            continue
        if tok.startswith("-") and len(tok) > 1:
            body = tok[1:]
            for i, ch in enumerate(body):
                if ch == "u":  # '-u <upstream>': the remainder of this token is the VALUE
                    if i == len(body) - 1:
                        skip_value = True  # a bare '-u': the value is the next token
                    break  # stop the cluster scan; the rest of this token is the upstream value
                short_flags.add(ch)
            continue
        operands.append(tok)  # a bare operand (a branch name)
    return short_flags, operands


def _discard_role(sub, args):
    """Classify a git segment's subcommand into (role, kind); see the block comment above. clean, stash,
    and branch do not use the tracked-tree probe: a real 'git clean' removes UNTRACKED files (a different,
    unrecoverable asset the tracked-change probe does not see), so ANY non-dry-run clean ASKS
    unconditionally (this also closes the clean.requireForce / -q / -i / clustered-flag edges, since the
    guard no longer tries to model whether the clean would fire); stash drop/clear ASK, and a force branch
    delete/move/copy/reset ASKS (an unforced create/list/-d keeps its allow)."""
    if sub == "checkout":
        return _checkout_role(args)
    if sub == "switch":
        return _switch_role(args)
    if sub == "restore":
        return _restore_role(args)
    if sub == "reset":
        return _reset_role(args)
    if sub == "rm":
        return _rm_role(args)
    if sub == "clean":
        # Judge dry-run on the option region BEFORE any '--' (blocker 3): an operand after '--' (git clean
        # -f -- -nasty is a file literally named -nasty) must NOT be read as the '-n' dry-run flag, or a real
        # force-clean is misclassified as a harmless dry run and silently allowed. _clean_is_dry_run also
        # refuses to trust '-n' when an arg-consuming clean option ('-e'/'--exclude') is present, since '-n'
        # may be that option's value rather than the dry-run flag.
        pre, _post, _had_sep = _split_pre_post(args)
        if _clean_is_dry_run(pre):
            return ("allow", None)  # a dry run removes nothing
        return ("ask", "git clean (removes untracked files, which cannot be recovered)")
    if sub == "stash":
        first = next((a for a in args if not a.startswith("-")), None)
        if first in ("drop", "clear"):
            return ("ask", "git stash {} (discards saved stash entries)".format(first))
        # F-95: 'stash export' writes stash state to a ref, and its --to-ref form overwrites an arbitrary ref
        # UNCONDITIONALLY (no fast-forward or merged-ref safeguard), so every 'export' spelling ASKS; ASK for
        # all export forms (including --print) is acceptable per the disclosed over-ask posture.
        if first == "export":
            return ("ask", "git stash export (writes stash state to a ref, and --to-ref overwrites an "
                           "arbitrary ref unconditionally)")
        return ("allow", None)
    if sub == "branch":
        pre, post, _had_sep = _split_pre_post(args)
        short_flags, operands = _branch_parse_options(pre)
        operands = operands + post
        has_big_d = "D" in short_flags
        has_big_m = "M" in short_flags  # -M is 'move --force' (a force rename)
        has_big_c = "C" in short_flags  # -C is 'copy --force' (a force copy)
        # Delete, move, copy, and force are matched by CONSERVATIVE prefix too (GD-41 blocker 5):
        # '--del'/'--mov'/'--cop', and an ambiguous '--for' (which git itself rejects for branch as
        # ambiguous with '--format') is treated as force anyway, erring safe. Short flags are case-
        # sensitive, so -m/-c (unforced move/copy)
        # are distinct from -M/-C (their force forms). _branch_parse_options stops a short cluster at the
        # arg-taking '-u <upstream>' so an attached value ('-ufoo'/'-uMain') is the UPSTREAM, never scanned
        # as a clustered force flag (F-82 over-ASK regression: round-21's blind char-scan mis-read it).
        has_delete = _has_long_prefix(pre, "delete") or "d" in short_flags
        has_move = _has_long_prefix(pre, "move") or "m" in short_flags
        has_copy = _has_long_prefix(pre, "copy") or "c" in short_flags
        has_force = _has_long_prefix(pre, "force") or "f" in short_flags
        has_remotes = _has_long_prefix(pre, "remotes") or "r" in short_flags
        # F-94: a delete (-d/-D/--delete) combined with -r/--remotes deletes remote-tracking refs, which git
        # force-removes UNCONDITIONALLY, bypassing the merged-branch safeguard that protects a plain local
        # '-d'. So a delete+remotes ASKS even without an explicit force flag; a local non-force '-d' keeps its
        # allow below. Decided before the -D/force-delete branch so a delete-of-remotes gets its own reason.
        if has_remotes and (has_big_d or has_delete):
            return ("ask", "git branch -d/-D --remotes (deletes remote-tracking refs, which git "
                           "force-removes past the merged-branch safeguard)")
        # A force DELETE, force MOVE/rename, force COPY, or a bare force branch RESET each reset or overwrite
        # a branch ref and can orphan committed commits (the same reflog-recoverable loss class as -D), so all
        # ASK. A non-force create/list, an unforced -m/-c, and a safe -d delete keep their prior outcome.
        if has_big_d or (has_delete and has_force):
            return ("ask", "git branch -D/--delete --force (a force branch delete that may drop unmerged "
                           "commits)")
        if has_big_m or (has_move and has_force):
            return ("ask", "git branch -M/--move --force (a force rename that overwrites an existing branch "
                           "ref and may orphan its commits)")
        if has_big_c or (has_copy and has_force):
            return ("ask", "git branch -C/--copy --force (a force copy that overwrites an existing branch "
                           "ref and may orphan its commits)")
        if has_force and operands:
            return ("ask", "git branch -f/--force (a force branch reset that overwrites an existing branch "
                           "ref and may orphan its commits)")
        return ("allow", None)
    return ("allow", None)  # not a recognized lossy verb: the true boundary


# --- outcome text ------------------------------------------------------------------------------------

def _discard_ask_reason(kind, detail, optout=None):
    """The (reason, banner) pair for an ASK. Stored by the handler and emitted via _ask if no segment
    DENIES first, so a confirmed loss still wins over a recoverable ask. `optout` selects the PATH-AWARE
    opt-out guidance folded into the reason and the banner: _OPTOUT_PRISTINE (the default) on a pristine
    bare command, INCLUDING a pristine repository-view-redirected form (its leading GUARDRAIL_ALLOW_DISCARD=1
    prefix opts THIS command out, short-circuiting even the redirect gate), or _OPTOUT_REISSUE on a
    raw/unparseable or non-pristine command where no pristine bare form is present, so the opt-out is honoured
    only on a re-issued pristine bare form, never on the command as issued."""
    if optout is None:
        optout = _OPTOUT_PRISTINE
    reason = ("AIQT rule prsunc (preserve-uncommitted-work): {} {}. Confirm before proceeding, or commit "
              "or stash your work first. {}{}".format(kind, detail, _DISCARD_ALTS, optout))
    if optout is _OPTOUT_REISSUE:
        banner = ("AIQT guardrail: {} - confirm this discard, or re-issue it as a parseable pristine bare "
                  "'git <verb>' command carrying a leading GUARDRAIL_ALLOW_DISCARD=1 prefix to skip this "
                  "prompt (the opt-out is not honoured on the command as issued) (rule prsunc)."
                  .format(kind))
    else:
        banner = ("AIQT guardrail: {} - confirm this discard, or prefix GUARDRAIL_ALLOW_DISCARD=1 to skip "
                  "this prompt (rule prsunc).".format(kind))
    return (reason, banner)


def _discard_deny(kind):
    """A DENY: a whole-tree-clobbering verb on a tree the probe confirms is dirty (an uncommitted tracked
    change OR an untracked file the verb could reach), so the loss is certain. The wording covers untracked
    too, because the config-forced probe now counts an untracked-only-dirty tree as dirty."""
    reason = ("AIQT rule prsunc (preserve-uncommitted-work): {} would overwrite the working tree, which "
              "currently holds uncommitted or untracked changes the command could destroy, discarding any "
              "fix you have applied but not yet committed. {}{}"
              .format(kind, _DISCARD_ALTS, _OPTOUT_PRISTINE))
    banner = ("AIQT guardrail: blocked a git command that would discard uncommitted work (rule prsunc). "
              "Prefix GUARDRAIL_ALLOW_DISCARD=1 to override.")
    return _deny(reason, banner)


# --- worktree-certainty (coarse; replaces the removed dir modelling) ---------------------------------

# FAIL-SAFE repository-view check. An ambient GIT_*-prefixed var in the process env can point git at a
# different git dir, work tree, common dir, index, object store, ref namespace, replace/reference view, or
# config/attribute source than the session cwd. The clean probe scrubs EVERY ambient GIT_* before it runs
# (so the PROBE reads the REAL cwd repo), but the guard cannot scrub the operator's shell env from the
# ACTUAL command git will run: with an ambient GIT_DIR at a dirty repo and a clean cwd, the probe reads
# clean and would ALLOW while the real command clobbers the redirected dir; with an ambient GIT_INDEX_FILE
# the probe reads the default (clean) index while the command discards the custom one. Enumerating the
# redirecting vars proved a whack-a-mole (round after round found new members: GIT_NO_REPLACE_OBJECTS,
# GIT_REPLACE_REF_BASE, GIT_REFERENCE_BACKEND, and more will exist), so this FLIPS to fail-safe: ANY
# ambient GIT_* var forces ASK EXCEPT a small COSMETIC allowlist proven not to change the discard target,
# the object/ref view, the index, or dirtiness detection - only UI/editor/pager/prompt/lock/identity
# concerns. A GIT_TRACE* var is NOT cosmetic (an absolute GIT_TRACE value makes the ACTUAL command append
# trace output to that path, which could be a repo file), so it too forces ASK. An unknown or new GIT_* var
# ASKS rather than silently allowing.
_COSMETIC_GIT_VARS = frozenset((
    "GIT_PAGER",             # selects the pager UI; no effect on target/view/index/dirtiness
    "GIT_EDITOR",            # selects the commit-message editor; UI only
    "GIT_SEQUENCE_EDITOR",   # editor for the rebase todo list; UI only
    "GIT_ASKPASS",           # credential-prompt helper; auth UI only
    "GIT_TERMINAL_PROMPT",   # whether git prompts on the terminal; interactivity only
    "GIT_OPTIONAL_LOCKS",    # whether to take optional locks; performance, not target/dirtiness
    "GIT_NO_LAZY_FETCH",     # whether to lazy-fetch missing objects; network posture, not the view
    "GIT_ADVICE",            # whether to print advice hints; output UI only
    "GIT_FLUSH",             # output buffering/flushing; I/O behaviour only
    "GIT_MERGE_AUTOEDIT",    # whether merge auto-opens the editor; UI only
    "GIT_AUTHOR_NAME",       # author identity stamped on new commits; not the working-tree view
    "GIT_AUTHOR_EMAIL",      # author identity; not the view
    "GIT_AUTHOR_DATE",       # author date; not the view
    "GIT_COMMITTER_NAME",    # committer identity; not the view
    "GIT_COMMITTER_EMAIL",   # committer identity; not the view
    "GIT_COMMITTER_DATE",    # committer date; not the view
))


def _ambient_repo_view_override():
    """FAIL-SAFE: True when the ambient process environment carries ANY GIT_*-prefixed variable that is
    NOT in the small cosmetic allowlist. Such a variable can point git at a
    different git dir, work tree, index, object/ref view, replace/reference view, or config/attribute
    source than the session cwd. The clean probe scrubs these before it runs, so IT reads the real cwd
    repo, but the guard cannot scrub them from the ACTUAL command the shell runs: that command still
    inherits them and may act on a DIFFERENT repository view than the one probed. Enumerating the
    redirecting vars was a whack-a-mole (new members kept appearing: GIT_NO_REPLACE_OBJECTS,
    GIT_REPLACE_REF_BASE, GIT_REFERENCE_BACKEND), so this asks whenever it cannot PROVE the scrubbed
    cwd-probe matches the command's actual repository view: an unknown or new GIT_* var ASKS rather than
    silently allowing (clean becomes not-provably-clean -> ASK, never a silent ALLOW). Only clearly
    cosmetic UI/editor/pager/prompt/lock/identity vars, which cannot change the discard target, the
    object/ref view, the index, or dirtiness detection, are allowed through. A GIT_TRACE* var is NOT
    cosmetic and ASKS: an absolute GIT_TRACE value makes the ACTUAL command append trace output to that
    path, which could be a file inside the repo, so it is not provably view-neutral (the recovery/probe git
    calls still scrub the whole GIT_TRACE family, so THEY write no trace, but the command's own ambient
    GIT_TRACE is not neutralized)."""
    for key in os.environ:
        if not key.startswith("GIT_"):
            continue
        if key in _COSMETIC_GIT_VARS:
            continue
        return True
    return False


def _segment_dir_simple(tokens):
    """True when a git segment names its worktree simply enough that the session dir IS the worktree the
    command acts on: no leading env-assignment other than the opt-out (a GIT_DIR/GIT_WORK_TREE could
    redirect it), and no global option before the subcommand (a -C/--git-dir/--work-tree/-c, possibly
    abbreviated or attached, could redirect the worktree or change config). Anything else -> not simple ->
    the handler ASKS rather than trust a clean probe in the session dir. This is the coarse replacement
    for the git-faithful -C/--git-dir/--work-tree/env dir modelling GD-37 removed (that modelling was
    repeatedly fooled into probing a clean dir and silently allowing - F-62/F-64/F-66)."""
    cw_idx = _command_word_index(tokens)
    for tok in tokens[:cw_idx]:
        if _DISCARD_OPTOUT_RE.match(tok):
            continue  # the opt-out assignment is benign and is handled separately
        return False  # some other leading env-assignment: it may redirect the worktree or config
    i = cw_idx + 1  # the token after the 'git' command word
    if i < len(tokens) and tokens[i].startswith("-"):
        return False  # a global option before the subcommand: may be -C/--git-dir/--work-tree/-c
    return True


def _git_discard_fallback(command, cwd=None):
    """FAIL-SAFE conservative scan when the shared tokenizer cannot parse the command (an unbalanced quote or an unsupported construct): we cannot
    segment safely, so scan the RAW string. The opt-out is NOT consulted here: the guard cannot parse the
    command, so it cannot soundly trust an opt-out-looking prefix inside it (a quoted-falsy `="0"`, an
    interspersed `OTHER=x`, an opt-out on a DIFFERENT command `...=1 true; git`, a captured-truthy `0;` all
    read as opt-outs to a raw scan), so an unparseable in-scope command ALWAYS ASKS regardless of any leading
    opt-out-looking prefix. The opt-out is honoured ONLY on a PARSEABLE pristine bare command (see
    _segment_has_optout). If git is present AND a recognized work-losing verb keyword is present (an
    always-lossy verb, or 'branch' in any form) -> ASK (cannot prove safe); otherwise ALLOW (the true
    boundary). Documented best-effort: a genuinely clean but unparseable command that merely mentions a lossy
    verb keyword may ASK.

    Class C: an unparseable command reaching an ASK is a NON-PRISTINE discard, so it gets the SAME
    best-effort SESSION-CWD snapshot the non-pristine path takes (base resolvable + tree not provably
    clean) BEFORE returning the ASK, so a discard that is asked-then-approved is still recoverable. Without
    it, `git reset --hard <<'EOF'\\n'\\nEOF` (Bash-valid, a tokenizer ValueError) reached ASK with NO recovery
    ref. The snapshot is decision-INDEPENDENT and best-effort against the session repo only (the verb is
    unparseable, so the ledger label is a generic 'discard'); on snapshot fail the decision stays ASK with
    the failure surfaced."""
    if not _raw_has_lossy_git(command):
        return _allow()  # no git, or no recognized work-losing verb: the true boundary
    base = cwd if isinstance(cwd, str) and cwd else None
    snap = None
    if base is not None and _tree_is_clean(base) is not True:  # dirty or probe-uncertain: snapshot first
        snap = _record_recovery(base, "discard")
    reason = (
        "AIQT rule prsunc (preserve-uncommitted-work): the command could not be parsed by the shell lexer "
        "(likely an unbalanced quote) and it names a git work-losing verb this guard cannot prove safe; "
        "asking rather than silently allowing. {}{}".format(_DISCARD_ALTS, _OPTOUT_REISSUE))
    banner = (
        "AIQT guardrail: an unparseable git command names a work-losing verb this guard could not prove "
        "safe - confirm this discard. The GUARDRAIL_ALLOW_DISCARD opt-out is NOT honoured on an unparseable "
        "command (the guard cannot parse it); to opt out, re-issue the discard as a parseable bare git "
        "command with the leading prefix (rule prsunc, fail-safe).")
    if snap is not None and snap[0] == "ok":
        reason = reason + " " + _recovery_pointer(snap[1])
    elif snap is not None and snap[0] == "fail":
        reason = reason + (" NOTE: no pre-command recovery snapshot could be created ({}), so this discard "
                           "would not be recoverable by this guard.".format(snap[1]))
    return _ask(reason, banner)


def _pristine_single_bare_git(command, segments):
    """Return the token list of the sole git command when `command` is a PRISTINE SINGLE BARE 'git <verb>'
    invocation, else None (=> the caller ASKS). ULTRA-CONSERVATIVE and PURELY LEXICAL - the bash grammar is
    never parsed. Pristine requires ALL of:
      * the RAW command string carries NO shell metacharacter anywhere, EVEN INSIDE QUOTES (a deliberate
        over-ask): none of ; | & < > ( ) { } $ backtick backslash ! or a newline, which by construction also
        rules out &&/||/|&, every redirection form (>, >>, <, 2>, &>, >&, n>&m, a leading or interspersed
        redirect), and every command/process substitution ($( ), backtick, <( ), >( ));
      * no shell RESERVED-WORD token (if/then/for/while/case/[[/{/... a compound-command keyword);
      * exactly ONE operator-free command segment (guaranteed once no metacharacter is present, asserted);
      * after optional leading KEY=value env/opt-out assignments, the sole command word is LITERALLY 'git'
        (not a path like /usr/bin/git, and not a wrapper such as sudo/env/sh -c/... whose word is not 'git').
    Anything else - a compound, a wrapper/redirect/reserved-word, or a command word that is not literally
    'git' - returns None so the guard ASKS rather than trust the clean probe on a command it cannot read
    with certainty."""
    if _SHELL_META_RE.search(command):
        return None  # any shell metacharacter (even quoted): not pristine -> ASK
    # With no metacharacter there is exactly one operator-free segment; require precisely that.
    populated = [(toks, sep) for toks, sep in segments if toks or sep]
    if len(populated) != 1 or populated[0][1]:
        return None
    tokens = populated[0][0]
    if any(t in _SHELL_RESERVED_WORDS for t in tokens):
        return None  # a shell reserved word: not a bare git invocation -> ASK
    idx = _command_word_index(tokens)  # skip leading KEY=value assignments (incl. the opt-out)
    if idx >= len(tokens) or tokens[idx] != "git":
        return None  # a wrapper, a pathed git, or no command word: not a bare 'git' -> ASK
    return tokens


# --- the recovery/snapshot layer (EN-6): an INERT git-DB sealed-epoch snapshot -----------------------
# BENEATH the ultra-conservative classifier sits a recovery layer that makes a discard RECOVERABLE. Before
# git_discard returns its decision for an in-scope lossy verb whose worktree it can resolve to the session
# cwd AND whose tree is NOT provably clean, it takes an INERT snapshot of the uncommitted work, on the ALLOW
# and the ASK paths alike (the hook fires once at PreToolUse; there is no post-approval callback, so a
# discard that is asked-then-approved, or one wrongly allowed by a classifier mis-parse, must ALREADY have a
# recovery point). The snapshot is decision-INDEPENDENT by design: it does not trust the form-classifier to
# be right about which forms are safe, so it fires for every snapshottable verb on a not-provably-clean tree
# regardless of the allow/ask/deny verdict. It is skipped when the tree is PROVABLY CLEAN (nothing the probe
# can see to lose), when the command is not in scope, and for stash/branch (a worktree snapshot cannot
# capture stash entries or branch commits; ref-pinning for those is a separate, deferred mechanism).
# F-D EXPANSION: a NON-PRISTINE in-scope ASK (a compound/wrapped/redirected snapshottable command) is now
# also snapshot-backed BEST-EFFORT against the SESSION CWD repo, so an asked-then-approved wrapped discard is
# recoverable too. It is best-effort because a non-pristine command's redirected dir is NOT parsed: a command
# that changes into a DIFFERENT repository may be snapshotted at the session repo rather than the target (a
# same-repo cd is still captured by the whole-tree `git add --all`); on snapshot fail the decision stays ASK.
#
# Mechanism (all stdlib/subprocess, offline): the repo TOPLEVEL is resolved once (the anchor for the size
# estimate and the inside-the-repo containment checks, since status paths are toplevel-relative and the cwd
# may be a subdir); a TEMPORARY GIT_INDEX_FILE in a throwaway dir normally OUTSIDE the toplevel (best-effort
# and guarded: the snapshot FAILS rather than write inside the tree when TMPDIR resolves within it), seeded
# by COPYING the real index (so staged content is the baseline); `git add --all` into that temp index
# overlays tracked-modified and UNTRACKED content (ignored excluded); `git write-tree` (temp index) -> a
# tree; `git commit-tree <tree> [-p HEAD]` -> a snapshot commit; then a CREATE-ONLY `git update-ref
# refs/aiqt-recovery/<utc-ts>-<pid> <sha> ""` (empty expected-old value: a name collision FAILS the snapshot
# rather than clobbering a prior recovery ref) protects it from GC.
#
# The BOUND on "inert" (honest framing): the snapshot's OWN git operations write only git objects and one
# private ref (plus a reflog entry for that ref when core.logAllRefUpdates=always, or when a reflog already
# exists for the ref) and do NOT themselves
# modify the real index, worktree, HEAD, or any branch; the ref is invisible to plain `git status`, `git
# branch`, and `git log`, THOUGH reachable via `git log --all` / `git for-each-ref refs/aiqt-recovery` /
# `git show-ref` (a real ref, not hidden). The selftest asserts the real status/index/HEAD, index bytes,
# config, and stash list are unchanged. Every real-state call in this layer scrubs EVERY ambient GIT_*-prefixed
# var (_isolate_git_env, the allowlist posture), so an ambient GIT_CONFIG_PARAMETERS injection, a
# GIT_ATTR_SOURCE redirect, or a GIT_TRACE file-write vector cannot reach these calls; the residual is NOT
# limited to on-disk config - it spans the non-GIT_ environment (HOME/XDG_CONFIG_HOME/PATH/TMPDIR), on-disk
# git configuration AND attributes (repo/global/system), index and ignore state, submodules and embedded
# repos, configured hooks and filters, PATH-based git resolution, and partial-clone object availability, all
# read by git by design. BUT git may ADDITIONALLY run any git-configured (repo, global,
# system, or command-scope) program during the
# snapshot, whose effects are OUTSIDE this guard's control, so the inert guarantee is BOUNDED, not
# categorical: a clean/process filter runs on `git add --all` (the CHECK-IN / clean direction, NOT smudge -
# smudge would run only on a restore/checkout), an fsmonitor hook runs on the `git status` probe, a
# reference-transaction hook AND a post-index-change hook can run on the temp-index write, and a
# reference-transaction hook runs on `git update-ref`. Because a clean filter can TRANSFORM worktree bytes
# before they enter the snapshot, the snapshot is NOT guaranteed byte-exact on a filtered repo. Further, a
# single overlaid tree cannot capture dirty content inside a SUBMODULE or an untracked EMBEDDED git repo (it
# stores only the gitlink), and it flattens staged-vs-unstaged into ONE tree. One JSONL line is appended to a
# per-user ledger normally OUTSIDE the repo (so a `git clean` inside the repo cannot destroy it); the write
# is BEST-EFFORT: normally one line per snapshot, but skipped when no per-user location resolves (absent
# HOME/XDG), when the path would land inside the repo (a misconfigured XDG_STATE_HOME/HOME), or when the
# directory/open/write fails. FAIL POSTURE: when a snapshot is warranted but cannot be made (probe/write
# error, an undecodable non-UTF-8 path, over the size cap, a bare or broken git dir, or a temp dir resolving
# inside the repo) the recovery layer NEVER lets that become a silent allow of a not-provably-clean discard -
# a would-be ALLOW is DOWNGRADED to ASK, and an already-ASK/DENY decision is left as-is with the failure
# surfaced in its reason. HONEST LIMITATION: the snapshot cannot capture what the probe cannot see (content
# hidden by assume-unchanged/skip-worktree marks or submodule.<name>.ignore), nor ignored files (git add
# --all excludes them), so a discard of that content is not recoverable here.
_SNAPSHOTTABLE_VERBS = frozenset(("checkout", "switch", "restore", "reset", "rm", "clean"))
# The lossy git verbs the form-classifier can reason about (the recognized-verb set). A command the raw scan
# flags as in-scope whose resolved subcommand is outside this set (e.g. 'checkout-index', 'read-tree',
# flagged by a 'checkout'/'reset' substring) cannot be classified, so it must not win the catch-all allow
# (F-97): it ASKS instead. This is a SUPERSET of _SNAPSHOTTABLE_VERBS (it also covers stash/branch, whose
# assets a worktree snapshot cannot capture).
_RECOGNIZED_VERBS = frozenset((
    "checkout", "switch", "restore", "reset", "rm", "clean", "stash", "branch"))
_RECOVERY_REF_NS = "refs/aiqt-recovery"
# Skip (and fail to ASK) rather than snapshot an enormous working tree: a changed+untracked estimate over
# this many bytes is treated as a snapshot failure, so the guard never tries to seal a multi-gigabyte tree.
_RECOVERY_SIZE_CAP = 100 * 1024 * 1024  # 100 MiB
# The per-user ledger path components under the XDG state dir. Normally outside any repo; the write is
# guarded (skipped if the resolved path would land inside the repo).
_RECOVERY_LEDGER_PARTS = ("aiqt-guardrails", "recovery.jsonl")


def _recovery_git(repo, args, env_extra=None, timeout=10):
    """Run a git subcommand against repo and return the CompletedProcess. INERT TO WORKING STATE: across all
    of its git calls it never touches the real index (a snapshot call uses a TEMP GIT_INDEX_FILE via
    env_extra), the worktree, HEAD, or a branch, and in a NORMAL repo writes only objects and one private ref
    (see the block comment above _SNAPSHOTTABLE_VERBS for the repo-config residual). EVERY ambient
    GIT_*-prefixed var is ALWAYS scrubbed via _isolate_git_env (the allowlist posture: no ambient git env is
    trusted, so GIT_DIR/GIT_WORK_TREE/GIT_CONFIG_*/GIT_TRACE*/GIT_ATTR_SOURCE and any future GIT_* go at
    once) so a call meant to observe the REAL repo state (the status probe,
    `rev-parse --show-toplevel`/`--git-path index`) and the snapshot itself cannot be redirected to a
    foreign preset repo (a decoy that would win a false clean, a false recovery point, or leak into the
    snapshot) and cannot be made to WRITE a trace file through an ambient GIT_TRACE path; a snapshot call
    overrides GIT_INDEX_FILE with its own temp index through env_extra, applied AFTER the scrub. This scrub
    is BOUNDED to the ambient ENV: the residual is NOT limited to on-disk config - it spans the non-GIT_
    environment (HOME/XDG_CONFIG_HOME/PATH/TMPDIR), on-disk git configuration AND attributes (repo, global,
    and system), index and ignore state, submodules and embedded repos, configured hooks and filters,
    PATH-based git resolution, and partial-clone object availability, all read by git by design and none
    neutralized here.
    Raises subprocess.SubprocessError / OSError on a spawn or timeout failure, which the caller treats as a
    snapshot failure. offline, bounded by `timeout`."""
    cmd = ["git", "-C", repo] + list(args)
    env = _isolate_git_env(dict(os.environ))  # real-state calls must see the REAL repo, not an ambient decoy
    if env_extra:
        env.update(env_extra)  # a snapshot call sets its own GIT_INDEX_FILE here, applied AFTER the scrub
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def _recovery_toplevel(repo):
    """The absolute repo TOPLEVEL for repo, via `git rev-parse --show-toplevel` (run through _recovery_git,
    so it inherits the discovery-env neutralization and targets the REAL repo). Returns the toplevel path, or
    None when git cannot resolve it (a non-zero return or an empty result: a bare repo, a broken git dir, or
    not a work tree) - the caller treats None as a snapshot failure. This matters because `status --porcelain`
    paths are repo-ROOT-relative while the session cwd can be a SUBDIR, so the size-estimate joins and the
    inside-the-repo containment checks must anchor on the TOPLEVEL, not on the (possibly deeper) cwd."""
    try:
        result = _recovery_git(repo, ["rev-parse", "--show-toplevel"], timeout=5)
    except (subprocess.SubprocessError, OSError, ValueError):
        # ValueError covers a UnicodeDecodeError raised by text-mode decoding of a non-UTF-8 toplevel path.
        return None
    if result.returncode != 0:
        return None
    try:
        # Strip git's ONE output terminator (its single trailing newline), NOT arbitrary whitespace and
        # NOT every trailing newline: a repo dir name may legitimately carry a leading or trailing SPACE
        # (which .strip() would corrupt) and may even END in a newline (which rstrip("\n") would eat along
        # with git's terminator), and either corruption makes the registry read (or a containment anchor)
        # silently miss. git prints the path plus EXACTLY one \n, so dropping only that one terminator
        # preserves every path character; a decode or type fault fails safe to None (an unresolved root ->
        # the caller ASKs).
        top = result.stdout[:-1] if result.stdout.endswith("\n") else result.stdout
    except (AttributeError, TypeError):
        return None
    if not top or not os.path.isabs(top):
        return None
    return top


def _recovery_status_entries(repo, top):
    """(classes, total_bytes) from a read-only, config-forced porcelain probe of repo: `classes` is the
    set of covered classes among {'staged','tracked','untracked'} across every changed/untracked entry,
    and `total_bytes` is the summed on-disk size of those paths (a size-cap estimate; a missing path, e.g.
    a deletion, contributes 0). Its paths are repo-ROOT-relative, so a relative one is joined onto `top`
    (the resolved toplevel), NOT the passed repo, which can be a subdir and would under-count the estimate.
    Parses the NUL-delimited `--porcelain -z` form, consuming the extra origin field of a rename/copy record.
    Raises subprocess.SubprocessError / OSError on a probe failure, or UnicodeDecodeError (a ValueError) when
    a non-UTF-8 path cannot be decoded, which the caller turns into a snapshot fail (a graceful ASK)."""
    result = _recovery_git(
        repo, ["-c", "status.showUntrackedFiles=all", "status", "--porcelain",
               "--untracked-files=all", "-z"], env_extra={"GIT_OPTIONAL_LOCKS": "0"}, timeout=5)
    if result.returncode != 0:
        raise subprocess.SubprocessError("status probe returned {}".format(result.returncode))
    classes = set()
    total = 0
    fields = result.stdout.split("\0")
    i, n = 0, len(fields)
    while i < n:
        rec = fields[i]
        i += 1
        if not rec or len(rec) < 3:
            continue
        xy, path = rec[:2], rec[3:]
        # A rename/copy record (X in R/C) carries its ORIGIN path as the next NUL field: consume it.
        if xy and xy[0] in ("R", "C") and i < n:
            i += 1
        if xy == "??":
            classes.add("untracked")
        else:
            if xy[0] not in (" ", "?"):
                classes.add("staged")
            if xy[1] not in (" ", "?"):
                classes.add("tracked")
        try:
            full = path if os.path.isabs(path) else os.path.join(top, path)  # paths are TOPLEVEL-relative
            total += os.path.getsize(full)
        except OSError:
            pass  # a deleted or unreadable path contributes nothing to the size estimate
    return classes, total


def _path_is_within(candidate, parent):
    """True when the realpath of candidate is parent itself or lies under it, tested on whole path
    COMPONENTS (os.path.commonpath) so a sibling like '/repo-x' is not judged inside '/repo', AND a real
    subpath of the filesystem root '/' is correctly judged inside it: the earlier `base + os.sep` test made
    '/' into '//', so every candidate read as OUTSIDE and the guard was silently bypassed (Gemini G1). Used
    to refuse writing recovery data inside the repo it protects (a misconfigured TMPDIR/XDG_STATE_HOME/HOME).
    realpath(strict=False) resolves a not-yet-existing path (the ledger file on its FIRST write) WITHOUT
    raising, so the except fires only on a genuine resolution fault (a symlink loop, or commonpath given
    mixed absolute/relative inputs); on any such error err toward True (unsafe -> refuse) rather than risk
    writing inside the tree."""
    try:
        cand = os.path.realpath(candidate)
        base = os.path.realpath(parent)
        return cand == base or os.path.commonpath([cand, base]) == base
    except (OSError, ValueError):
        return True


def _take_snapshot(repo, top, verb):
    """Take an INERT git-DB snapshot of the working tree (tracked-modified + staged + untracked; ignored
    excluded) via a TEMPORARY GIT_INDEX_FILE normally outside the repo, protected by a private
    refs/aiqt-recovery/<utc-ts>-<pid> ref. `top` is the resolved repo TOPLEVEL (the containment anchor and
    the size-estimate root; the session cwd may be a subdir). In a NORMAL repo writes only git objects and
    that one ref; the real index, worktree, HEAD, and every branch are untouched (see the block comment above
    _SNAPSHOTTABLE_VERBS for the repo-config residual). Returns ('ok', info) with info =
    {ref, sha, classes, restore}, or ('fail', reason)."""
    try:
        classes, total = _recovery_status_entries(repo, top)
    except (subprocess.SubprocessError, OSError) as exc:
        return ("fail", "the working-tree status probe failed ({})".format(exc))
    except UnicodeDecodeError as exc:
        # A non-UTF-8 filename makes `status -z` (text=True) raise a UnicodeDecodeError (a ValueError), which
        # is NOT a SubprocessError/OSError; catch it so it fails the snapshot -> graceful ASK, never an
        # uncaught crash that the dispatcher would turn into an exit-2 HARD BLOCK of a would-ALLOW command.
        return ("fail", "the working-tree status probe returned an undecodable (non-UTF-8) path ({})"
                        .format(exc))
    if total > _RECOVERY_SIZE_CAP:
        return ("fail", "the working tree exceeds the {} MiB recovery snapshot size cap"
                        .format(_RECOVERY_SIZE_CAP // (1024 * 1024)))
    tmpdir = None
    try:
        tmpdir = tempfile.mkdtemp(prefix="aiqt-recovery-")  # normally OUTSIDE the repo, in the system temp dir
        if _path_is_within(tmpdir, top):
            # A TMPDIR misconfigured to resolve inside the repo would seal recovery data where a `git clean`
            # could destroy it; refuse rather than write inside the tree the snapshot protects.
            return ("fail", "the temp snapshot dir resolved inside the repo (TMPDIR misconfigured), so no "
                            "recovery snapshot was written inside the tree it protects")
        tmp_index = os.path.join(tmpdir, "index")
        # Seed the temp index from the REAL index (so staged content is the baseline). git add --all then
        # overlays the worktree (tracked-modified) and untracked files; ignored files are excluded.
        real_index = _recovery_git(
            repo, ["rev-parse", "--path-format=absolute", "--git-path", "index"], timeout=5).stdout.strip()
        if real_index and os.path.exists(real_index):
            shutil.copyfile(real_index, tmp_index)  # else: git creates a fresh temp index on add --all
        env = {"GIT_INDEX_FILE": tmp_index}
        if _recovery_git(repo, ["add", "--all"], env_extra=env, timeout=20).returncode != 0:
            return ("fail", "git add --all into the temp index failed")
        wt = _recovery_git(repo, ["write-tree"], env_extra=env, timeout=10)
        if wt.returncode != 0 or not wt.stdout.strip():
            return ("fail", "git write-tree (temp index) failed")
        tree = wt.stdout.strip()
        head = _recovery_git(repo, ["rev-parse", "--verify", "-q", "HEAD^{commit}"], timeout=5)
        parent = head.stdout.strip() if head.returncode == 0 else ""
        commit_args = ["commit-tree", tree]
        if parent:
            commit_args += ["-p", parent]  # parent HEAD when present; an unborn HEAD makes a rootless snapshot
        commit_args += ["-m", "aiqt-guardrails recovery snapshot before git {}".format(verb)]
        ct = _recovery_git(repo, commit_args, timeout=10)
        if ct.returncode != 0 or not ct.stdout.strip():
            return ("fail", "git commit-tree failed")
        sha = ct.stdout.strip()
        # Microsecond precision plus the pid makes the ref name unique for several snapshots within the same
        # second in the same process; the CREATE-ONLY update-ref below (an empty-string expected-old value)
        # is the backstop, so a name that DID repeat (a clock rollback or a reused pid) FAILS the snapshot
        # rather than silently clobbering a prior recovery point onto the same ref.
        ref = "{}/{}-{}".format(
            _RECOVERY_REF_NS,
            datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"), os.getpid())
        # The trailing "" is the expected OLD value: git makes this a CREATE-ONLY update that fails if the ref
        # already exists, so a colliding name returns non-zero -> ('fail') -> ASK, never an overwrite.
        if _recovery_git(repo, ["update-ref", ref, sha, ""], timeout=5).returncode != 0:
            return ("fail", "git update-ref for the recovery ref failed (a create-only collision or a "
                            "ref-store error), so no recovery point was written over a prior one")
    except (subprocess.SubprocessError, OSError, UnicodeDecodeError) as exc:
        return ("fail", "the snapshot could not be created ({})".format(exc))
    finally:
        if tmpdir is not None:
            shutil.rmtree(tmpdir, ignore_errors=True)
    return ("ok", {"ref": ref, "sha": sha, "classes": sorted(classes),
                   "restore": "git checkout {} -- :/".format(ref)})


def _recovery_ledger_path():
    """The per-user ledger path, normally OUTSIDE any repo: $XDG_STATE_HOME/aiqt-guardrails/recovery.jsonl, or
    ~/.local/state/aiqt-guardrails/recovery.jsonl when XDG_STATE_HOME is unset. None when neither
    XDG_STATE_HOME nor HOME resolves (no per-user location to write to). The write itself is guarded in
    _write_recovery_ledger: it is skipped if this path would resolve inside the repo (a misconfigured
    XDG_STATE_HOME/HOME)."""
    base = os.environ.get("XDG_STATE_HOME")
    if not base:
        home = os.environ.get("HOME")
        if not home:
            return None
        base = os.path.join(home, ".local", "state")
    return os.path.join(base, *_RECOVERY_LEDGER_PARTS)


def _write_recovery_ledger(repo, top, verb, info):
    """Append ONE JSONL record for a snapshot to the per-user ledger. Records ONLY: utc timestamp, repo
    path, the triggering git VERB (never the raw command or file contents, for privacy), the recovery ref,
    the snapshot sha, the covered classes, and the exact restore command. Best-effort: ANY error (not only
    an OSError) is swallowed to False (the ref itself is the recovery point; the ledger is a convenience
    trace read later), so a ledger fault never changes the guard's decision. The containment check anchors on
    `top` (the resolved toplevel), so a per-user path landing inside the worktree ABOVE the session cwd is
    still refused. Returns True on a successful write, else False."""
    path = _recovery_ledger_path()
    if not path:
        return False
    if _path_is_within(path, top):
        return False  # a misconfigured XDG_STATE_HOME/HOME pointing inside the repo: skip (best-effort)
    record = {"ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "repo": repo, "verb": verb, "ref": info["ref"], "sha": info["sha"],
              "classes": info["classes"], "restore": info["restore"]}
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        return True
    except Exception:
        return False


def _record_recovery(repo, verb):
    """Take a recovery snapshot and, on success, append the ledger (best-effort). Returns ('ok', info) or
    ('fail', reason). Called ONLY when the worktree is resolvable to the session cwd and the tree is NOT
    provably clean, so a snapshot is genuinely warranted. Resolves the repo TOPLEVEL ONCE (via _recovery_git,
    so it inherits the discovery-env neutralization) and threads it to both the snapshot and the ledger, so
    the size estimate and the inside-the-repo containment checks anchor on the toplevel, not the (possibly
    deeper) session cwd. An unresolvable toplevel (a bare or broken git dir) is itself a snapshot fail. ANY
    snapshot-path fault (a non-UTF-8 repo/toplevel path, an embedded-NUL cwd, or any future snapshot fault)
    is caught and downgraded to a snapshot failure (a graceful fail-to-ASK), so no snapshot-path exception
    can propagate to the dispatcher and crash the guard. The ledger write is OUTSIDE that boundary and
    separately best-effort: it runs only on a successful snapshot and any fault in it is swallowed, so it can
    NEVER downgrade a successful snapshot's ('ok', info) to a failure."""
    try:
        top = _recovery_toplevel(repo)
        if not top:
            return ("fail", "the repository toplevel could not be resolved (a bare or broken git dir)")
        result = _take_snapshot(repo, top, verb)
    except Exception as exc:  # a snapshot-path fault -> graceful fail-to-ASK
        return ("fail", "the recovery snapshot could not be taken ({}: {})".format(
            type(exc).__name__, exc))
    if result[0] == "ok":
        try:
            _write_recovery_ledger(repo, top, verb, result[1])
        except Exception:  # best-effort ledger: a fault here never affects the snapshot outcome
            pass
    return result


def _recovery_pointer(info):
    """A one-line human pointer to a saved snapshot for an ASK/DENY reason. Says a snapshot was SAVED, not
    that work was discarded (PreToolUse cannot know the command ran). Discloses that the primary restore is
    OVERLAY mode (it brings back modified and new content but does NOT re-apply a recorded file deletion),
    and points to the isolated-branch form for an exact, deletion-inclusive restore."""
    covered = ", ".join(info["classes"]) if info["classes"] else "the working tree"
    return ("A pre-command recovery snapshot was saved ({}) at ref {}; restore it with '{}' (overlay mode: "
            "it brings back modified and new content but does NOT re-apply a file deletion recorded in the "
            "snapshot), or for an exact, deletion-inclusive restore put it on an isolated branch with 'git "
            "switch -c aiqt-recover-<id> {}'.".format(
                covered, info["ref"], info["restore"], info["ref"]))


def _ask_with_recovery(kind, detail, snap, optout=None):
    """An ASK whose reason folds in the recovery outcome: a restore pointer on a successful snapshot, or
    the failure surfaced (decision stays ASK) on a snapshot failure. snap is None (no snapshot warranted),
    ('ok', info), or ('fail', reason). `optout` is passed through to _discard_ask_reason to select the
    path-aware opt-out guidance (default pristine; the non-pristine caller passes _OPTOUT_REISSUE, while the
    ambient/view-redirected caller passes _OPTOUT_PRISTINE because a pristine redirected form is opted out by
    prefixing the command as issued)."""
    reason, banner = _discard_ask_reason(kind, detail, optout)
    if snap is not None and snap[0] == "ok":
        reason = reason + " " + _recovery_pointer(snap[1])
    elif snap is not None and snap[0] == "fail":
        reason = reason + (" NOTE: no pre-command recovery snapshot could be created ({}), so this "
                           "discard would not be recoverable by this guard.".format(snap[1]))
    return _ask(reason, banner)


def _deny_with_recovery(kind, snap):
    """A DENY (a confirmed whole-tree clobber on a dirty tree) whose reason folds in the recovery outcome,
    mirroring _ask_with_recovery."""
    code, obj, err = _discard_deny(kind)
    if snap is not None and snap[0] == "ok":
        obj["hookSpecificOutput"]["permissionDecisionReason"] += " " + _recovery_pointer(snap[1])
    elif snap is not None and snap[0] == "fail":
        obj["hookSpecificOutput"]["permissionDecisionReason"] += (
            " NOTE: no pre-command recovery snapshot could be created ({}).".format(snap[1]))
    return (code, obj, err)


def git_discard(data):
    """prsunc (integ/preserve-uncommitted-work), PreToolUse/Bash. ULTRA-CONSERVATIVE "ask unless PRISTINE
    and provably clean" guard (EN-6). For a command that names any recognized lossy git verb (checkout incl
    -B force-create, switch incl -C/--force-create, restore/reset/clean/stash drop-clear/rm/branch force
    delete/move/copy/reset) the outcome is ASK unless the command
    is a PRISTINE SINGLE BARE 'git <verb>' invocation (see _pristine_single_bare_git: no shell metacharacter
    anywhere even quoted, no reserved word, no wrapper/redirect/compound, and the sole command word literally
    'git') AND either its FORM is genuinely non-destructive, or the working tree is PROVABLY CLEAN (the
    config-forced porcelain probe reports no tracked change AND no untracked entry), or the LEADING opt-out is
    set - in which cases ALLOW. A pristine single bare WHOLE-TREE clobber (reset --hard, checkout -f with no
    pathspec, switch --force/--discard-changes) on a probed-DIRTY tree DENIES. EVERYTHING ELSE in scope ASKS:
    any shell structure at all (a metacharacter, wrapper, redirect, reserved word, or second segment), an
    option the form-classifier cannot resolve, a worktree it cannot resolve to the session cwd, an incomplete
    probe, or a softer/index-only discard. No recognized lossy command that would discard WORKING-TREE CONTENT
    is silently ALLOWED unless it is a pristine
    bare git whose FORM is genuinely non-destructive (checkout -b, reset --soft, clean -n, which ALLOW even on
    a dirty tree), or on a provably-clean tree, or a pristine bare form carrying the leading
    GUARDRAIL_ALLOW_DISCARD=1 opt-out - worst case it ASKS; the guarantee is bounded to working-tree content
    (ref-level moves such as reset --soft moving HEAD or a merged-branch delete are reflog-recoverable) and is
    best-effort against the disclosed obfuscation/config residuals. Fail-open ALLOW is reserved for the TRUE boundary
    (a non-Bash or absent tool, a malformed or missing command it cannot read as a discard, a non-git command,
    or no recognized lossy verb). A wrapper is in scope only while the raw scan still
    sees a contiguous git verb keyword, so 'any wrapper ASKS' is NOT categorical: a wrapper that ALSO
    fragments the COMMAND WORD 'git' itself or the verb (env git re'set' --hard / eval git re'set' / command
    g'it' reset --hard, whose raw string carries no contiguous 'git'+'reset') reads as 'no recognized lossy
    verb' and is silently ALLOWED - a DISCLOSED best-effort residual, not chased. A real discard whose VERB is
    outside the recognized set AND unflagged by the raw scan ('git worktree remove -f' of a dirty linked
    worktree, where 'worktree' matches no lossy keyword) is allowed at the true boundary - disclosed, not
    closed this round. BUT a command the raw scan DOES flag whose resolved subcommand is outside the
    recognized set ('git checkout-index -a -f', 'git read-tree -u --reset HEAD') now ASKS (F-97): a flagged
    sub the classifier cannot resolve to a known verb cannot be proven non-destructive, so it never wins the
    catch-all allow. The status probe (git status --porcelain,
    config-forced to report untracked) is read-only and offline.

    SIDE-EFFECTING (EN-6 recovery layer): this handler is NO LONGER pure-decision. Before returning its
    decision for a snapshottable in-scope verb (checkout/switch/restore/reset/rm/clean) whose worktree it can
    resolve to the session cwd AND whose tree is NOT provably clean, it takes an INERT recovery snapshot of
    the uncommitted work (a private refs/aiqt-recovery/<utc-ts>-<pid> ref over a temp-index tree, git objects
    + one ref only) and BEST-EFFORT appends a line to an EXTERNAL per-user ledger (normally one per snapshot;
    skipped when no per-user location resolves, the path would land inside the repo, or the write fails), on
    the ALLOW and ASK paths alike (the hook fires once, with no post-approval callback). It NEVER mutates the real index, worktree, HEAD, or any
    branch. If a warranted snapshot cannot be made, a would-be ALLOW is downgraded to ASK ('no recovery point
    could be created'); an already-ASK/DENY decision is left as-is with the failure surfaced. F-D EXPANSION: a
    NON-PRISTINE in-scope ASK (a compound/wrapped/redirected snapshottable command) is ALSO snapshot-backed
    BEST-EFFORT against the SESSION CWD repo (the redirected dir of a non-pristine command is not parsed, so a
    command that changes into a DIFFERENT repo may be snapshotted at the session repo rather than the target;
    a same-repo cd is still captured by the whole-tree add --all). See the recovery block comment above
    _SNAPSHOTTABLE_VERBS. The snapshot cannot capture what the probe cannot see (assume-unchanged/skip-worktree
    marks, submodule.<name>.ignore) or ignored files (git add --all excludes them), so a discard of that
    content is not recoverable here."""
    if data.get("hook_event_name") != PRETOOL:
        # A mis-wired event is a broken install: loud (unreachable given the generator's event whitelist).
        return _hard_block("aiqt_hooks: git_discard wired to unexpected event {!r}; failing closed"
                           .format(data.get("hook_event_name")))
    tool_name = data.get("tool_name")
    if tool_name != "Bash":
        return _allow()  # boundary: a missing or other tool is out of scope
    tool_input = data.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return _allow()  # boundary: unreadable/malformed command container
    try:
        segments = _segments(command)
    except ValueError:
        # Conservative raw scan, not a silent allow. Pass cwd so an unparseable in-scope discard still gets
        # a best-effort recovery snapshot before the ASK (Class C), mirroring the non-pristine path.
        return _git_discard_fallback(command, data.get("cwd"))

    # Precisely-identified lossy git segments (the clean-parse signal). A git command-word segment whose
    # verb-form is not "allow" is a real in-scope lossy form. Used for the in-scope decision on a
    # metacharacter-free, unwrapped command, where the segmentation can be trusted.
    lossy = []  # (role, kind, tokens) for each such segment
    for tokens, _sep in segments:
        if _command_word(tokens) != "git":
            continue
        sub, args = _git_sub_and_args(tokens)
        if sub is None:
            continue
        role, kind = _discard_role(sub, args)
        if role != "allow":
            lossy.append((role, kind, tokens))

    # A wrapper or metacharacter can hide a lossy 'git <verb>' from the command-word segment scan, so the
    # in-scope decision below trusts the raw scan rather than any (unbounded) wrapper enumeration.
    # Trust the raw scan UNCONDITIONALLY (round-3 fix): enumerating wrappers is unbounded (stdbuf/doas/
    # setsid/eval defeated the list), so any raw 'git' + work-losing verb is in scope even when the precise
    # `lossy` list is empty (a wrapped or quoted git verb). A non-lossy git command still routes through the
    # pristine path below and allows. Residual: git renamed out of the string (alias/function) -> recovery layer.
    raw_lossy = _raw_has_lossy_git(command)
    if not lossy and not raw_lossy:
        return _allow()  # boundary: no git + work-losing verb anywhere

    # In scope. Apply the ULTRA-CONSERVATIVE pristine gate: anything that is not a pristine single bare
    # 'git <verb>' invocation ASKS, without ever consulting the probe (a safe over-ask).
    pristine = _pristine_single_bare_git(command, segments)
    if pristine is None:
        kind = lossy[0][1] if lossy else "a git work-losing verb"
        # F-D EXPAND (GD-41, Architect-approved): a non-pristine in-scope command still ASKS, but now gets a
        # BEST-EFFORT recovery point first, so an asked-then-approved compound/wrapped discard is recoverable
        # (the hook fires once, with no post-approval callback). This is BEST-EFFORT against the SESSION CWD
        # repo only: we do NOT parse a non-pristine command's redirected dir, so a command that changes into a
        # DIFFERENT repo may be snapshotted at the session repo rather than the target (a same-repo cd is
        # still captured by the whole-tree add --all). The snapshot is decision-INDEPENDENT (same
        # _record_recovery path); on snapshot fail the decision stays ASK with the failure surfaced (never
        # allow).
        np_subs = set()
        for _role, _kind, _toks in lossy:
            _s, _ = _git_sub_and_args(_toks)
            if _s is not None:
                np_subs.add(_s)
        # This command is ALREADY IN SCOPE (a visible lossy token routed it here), so the snapshot is no
        # longer gated on lexical snappable-detection: shell quoting/eval can hide WHICH snappable verb an
        # in-scope command carries (a `re'set'` fragment assembles `reset` at runtime, so np_subs may miss
        # it), so whenever the base resolves and the tree is NOT provably clean we take the inert best-effort
        # snapshot regardless of which verb is (or is not) visible. A verb obfuscated so thoroughly that it
        # evades even the raw scan (a standalone `eval git re'set'`, whose raw string has no contiguous
        # `reset` for _raw_has_lossy_git to catch) never reaches here at all: it is ALLOWED at the in-scope
        # boundary above, a DISCLOSED best-effort residual (the classifier's documented obfuscation residual),
        # not something this snapshot closes. Over-snapshotting a pure stash/branch non-pristine command is an
        # accepted inert cost (a worktree snapshot cannot capture their asset, but it is never an
        # under-protection). The np_verb label is best-effort from any visible snappable sub.
        np_cwd = data.get("cwd")
        np_base = np_cwd if isinstance(np_cwd, str) and np_cwd else None
        np_snap = None
        if np_base is not None and _tree_is_clean(np_base) is not True:
            np_verb = next(iter(sorted(np_subs & _SNAPSHOTTABLE_VERBS)), "discard")
            np_snap = _record_recovery(np_base, np_verb)
        return _ask_with_recovery(
            kind, "is not a pristine single bare 'git <verb>' invocation (it carries a shell "
                  "metacharacter, wrapper, redirect, reserved word, a second command, or a command word "
                  "that is not literally 'git'), so this guard will not trust a clean probe on it", np_snap,
            _OPTOUT_REISSUE)

    # A pristine single bare git command. Honour a truthy LEADING opt-out on it (an explicit override).
    # This short-circuits BEFORE the recovery layer, so an opt-out discard is NOT snapshot-backed: the
    # operator has explicitly taken responsibility for having saved the work.
    if _segment_has_optout(pristine):
        return _allow()

    # Re-derive the verb form from the sole pristine git command.
    sub, args = _git_sub_and_args(pristine)
    role, kind = _discard_role(sub, args) if sub is not None else ("allow", None)

    # FAIL-SAFE (EN-6, structural completion): the command's repository view cannot be proven to be the
    # session cwd when EITHER cause is present. (1) A NON-COSMETIC ambient GIT_* var: the probe scrubs it,
    # but the ACTUAL command still inherits it and may act on a redirected git dir, work tree, index, or
    # object/ref view. (2) A COMMAND-LOCAL redirect that _segment_dir_simple flags: a -C/--git-dir/--work-
    # tree global option or an inline GIT_DIR=/GIT_WORK_TREE= leading assignment ON the command can point it
    # at a different worktree or config. In EITHER case ANY in-scope pristine form ASKS here - a destructive
    # form OR a genuinely non-destructive allow form (reset --soft, plain switch, clean -n, checkout -b) -
    # BEFORE the role/allow logic below that would otherwise let an allow form through and bypass the fail-
    # safe. Only the explicit leading opt-out (short-circuited above) bypasses it. A best-effort snapshot of
    # the SESSION CWD is still taken on a not-provably-clean snappable tree (the cwd is known even when the
    # target is not): it is inert and provides recovery IF the command acts on the cwd (the common benign
    # non-redirecting case), but may NOT capture a redirected tree.
    if _ambient_repo_view_override() or not _segment_dir_simple(pristine):
        ao_cwd = data.get("cwd")
        ao_base = ao_cwd if isinstance(ao_cwd, str) and ao_cwd else None
        ao_snap = None
        if ao_base is not None and sub in _SNAPSHOTTABLE_VERBS and _tree_is_clean(ao_base) is not True:
            ao_snap = _record_recovery(ao_base, sub)
        return _ask_with_recovery(
            kind or "a git work-losing verb",
            "runs under a non-cosmetic ambient GIT_* variable or carries a command-local redirect "
            "(-C/--git-dir/--work-tree or an inline GIT_DIR=/GIT_WORK_TREE= assignment), so this guard "
            "cannot prove the command's repository view is the session directory (the probe scrubs an "
            "ambient var, but the actual command still inherits it, and a command-local redirect points "
            "elsewhere); any recovery snapshot is best-effort against the session cwd and may not capture "
            "a redirected tree", ao_snap, _OPTOUT_PRISTINE)

    if role == "allow" and any(t.lower().startswith(("alias.", "-calias.")) for t in pristine):
        return _ask(*_discard_ask_reason(
            "a git inline alias ('-c alias.<name>=...')",
            "may expand to a work-losing verb this guard cannot resolve"))

    # Resolve the session worktree ONCE: both the recovery layer and the clean probe need it. A non-cosmetic
    # ambient GIT_* override AND a command-local redirect (a -C/--git-dir/--work-tree/-c global option or a
    # GIT_DIR/GIT_WORK_TREE env assignment ON THE COMMAND, both flagged by _segment_dir_simple) were already
    # handled ABOVE (each ASKS with a best-effort cwd snapshot, which may not capture a redirected tree), so
    # neither reaches here. The _segment_dir_simple guard is kept in `resolvable` as a defensive backstop;
    # when the worktree cannot be resolved to the session cwd, no snapshot is possible and a lossy form ASKS.
    cwd = data.get("cwd")
    base = cwd if isinstance(cwd, str) and cwd else None
    resolvable = base is not None and _segment_dir_simple(pristine)
    snapshottable = sub in _SNAPSHOTTABLE_VERBS

    # THE RECOVERY LAYER. For a subcommand a discard could use to destroy worktree or untracked content
    # (checkout/switch/restore/reset/rm/clean), when the worktree is resolvable and the tree is NOT provably
    # clean, snapshot BEFORE returning ANY decision. Decision-INDEPENDENT (it does not trust the
    # form-classifier), so an asked-then-approved OR a wrongly-allowed (mis-parse) discard still has a
    # recovery point; the hook fires once with no post-approval callback. Skipped on a provably-clean tree
    # (nothing to lose) and for stash/branch (a worktree snapshot cannot capture their asset).
    clean = _tree_is_clean(base) if (resolvable and snapshottable) else None
    snap = None
    if resolvable and snapshottable and clean is not True:  # dirty or probe-uncertain: not provably clean
        snap = _record_recovery(base, sub)

    # F-97 (structural class-fix): the command is IN SCOPE (the raw scan flagged a git work-losing keyword)
    # yet its resolved subcommand is NOT one of the recognized lossy verbs - e.g. 'git checkout-index -a -f'
    # or 'git read-tree -u --reset HEAD', whose 'checkout'/'reset' substring trips the raw scan while
    # _discard_role falls to its catch-all allow. Such a command can discard tracked working-tree content
    # (and its sub is not snapshottable, so no recovery point exists), so it must NOT win the catch-all allow:
    # ASK, since a flagged sub the classifier cannot resolve to a known verb cannot be proven non-destructive.
    # A genuine safe FORM of a RECOGNIZED verb (checkout -b, reset --soft, clean -n) is unaffected: its sub IS
    # recognized, so this never fires for it.
    if raw_lossy and sub is not None and sub not in _RECOGNIZED_VERBS:
        return _ask(*_discard_ask_reason(
            kind or "a git command the raw scan flags as work-losing",
            "resolves to the git subcommand {!r}, which is outside the recognized lossy-verb set "
            "(checkout/switch/restore/reset/rm/clean/stash/branch), so this guard cannot prove it "
            "non-destructive".format(sub)))

    if role == "allow":
        # A genuinely non-destructive bare form (bare no-op, reset --soft, unforced -b, plain switch, clean
        # dry-run, stash pop). FAIL POSTURE: if a snapshot was warranted (a not-provably-clean snapshottable
        # tree, a defensive backstop against a mis-parse) and it FAILED, downgrade the allow to ASK - never
        # silent-allow a not-provably-clean discard with no recovery point. Otherwise ALLOW stands.
        if snap is not None and snap[0] == "fail":
            return _ask(*_discard_ask_reason(
                kind or "a git work-losing verb",
                "would run on a working tree that is not provably clean and no recovery point could be "
                "created ({}), so this guard will not silently allow it".format(snap[1])))
        return _allow()

    if role == "ask":
        # A softer discard (a real clean of untracked files, stash drop/clear, a force branch delete/move/
        # copy/reset): ASK regardless of the tracked-tree probe, which does not see the asset these verbs
        # destroy (a branch ref is a separate, reflog-recoverable asset). A clean may have been
        # snapshotted above (git add --all captures untracked); stash/branch are not snapshottable.
        return _ask_with_recovery(kind, "cannot be proven safe offline", snap)

    # A scoped or clobber form (all snapshottable): gate on the clean probe, which must resolve to the
    # session worktree.
    if not resolvable:
        return _ask(*_discard_ask_reason(
            kind, "targets a working tree this guard cannot resolve to the session directory with "
                  "certainty, so it cannot prove the tree clean"))
    if clean is True:
        return _allow()  # pristine bare lossy verb on a PROVABLY CLEAN tree: nothing to lose, no snapshot
    if clean is None:
        # probe-uncertain: a snapshot was attempted above (snap set); fold its outcome into the ASK reason.
        return _ask_with_recovery(
            kind, "targets a repository whose status probe did not complete, so this guard cannot prove "
                  "the working tree clean", snap)
    # clean is False: the tree holds uncommitted tracked changes or untracked files this verb could reach.
    if role == "clobber":
        return _deny_with_recovery(kind, snap)  # a confirmed whole-tree loss, still recoverable if approved
    return _ask_with_recovery(kind, "may discard uncommitted changes in the working tree", snap)


_PROTECTED = frozenset(("main", "master"))  # the protected line(s); default {main, master}, source-level config

# The safe alternative named in every deny/ask reason, so the actor is never left without a next
# step (mirrors _DISCARD_ALTS): the pack's own rule IS the route.
_PROTECTED_ALTS = (
    "Safe route: push to a feature branch instead ('git switch -c <branch>' then push, or 'git push "
    "<remote> HEAD:refs/heads/<feature>') and change the protected branch only through a reviewed, "
    "verified merge on green; never force-push or commit to it directly.")

# git-push options that CONSUME a following token in their SEPARATED form, so the token loop skips
# their value rather than misreading it as the remote or a refspec. Verified against
# git-scm.com/docs/git-push (SYNOPSIS/OPTIONS) and git-scm.com/docs/gitcli, 2026-08-19, and
# empirically against git 2.53.0: a MANDATORY option value may be attached (--opt=value, -ovalue) or
# separated (--opt value, -o value), and each option listed here is documented only WITH a value,
# hence mandatory, hence separable. --recurse-submodules is RESTORED (F-112 round-3, reverting the
# round-2 1A removal): its value is MANDATORY, so git consumes the NEXT token even separated
# ('git push --recurse-submodules check origin main' consumes 'check' as the value; a bare
# '--recurse-submodules origin main' fails with 'fatal: bad recurse-submodules argument: origin' -
# both observed on git 2.53.0; the negated no-value spelling is the DIFFERENT token
# '--no-recurse-submodules', which is not in this set and consumes nothing). Without the skip the
# value token read as an operand and inflated the refspec region, so a truly refspec-less force
# ('git push -f --recurse-submodules on-demand origin') bypassed the HEAD probe - a silent allow.
# The attached shape carries its value in the same token (the '=' / '-o<value>' test in the loop),
# consuming no separate token, so only the exact bare spelling triggers the skip. NOT listed, on the
# same gitcli(7) rule read the other way: --force-with-lease and --signed take an OPTIONAL value,
# legal only in the "stuck" attached form (--force-with-lease=main), and their bare form consumes
# NOTHING (listing them would skip a real operand); --force-if-includes takes NO value in ANY form.
# None of the three ever consumes a following token. Force DETECTION lives in the token loop, not here.
_PUSH_LONG_ARG_OPTS = frozenset((
    "--push-option", "--repo", "--receive-pack", "--exec", "--recurse-submodules"))
_PUSH_SHORT_ARG_OPTS = frozenset(("o",))  # bare letter: the char-scan tests body chars; '-o <val>' skips its value, attached '-o<val>' does not

# Fallback-only raw-string probes, used when the shared tokenizer cannot parse the command (an unbalanced quote or an unsupported construct);
# mirrors the _RAW_DIFF_PRODUCER_RE / _RAW_LOSSY_VERB_RE posture: conservative, over-matching, never
# a silent allow. _RAW_PUSH_RE/_RAW_COMMIT_RE pair git with the verb in one pattern ((?is): case-fold,
# '.' spans newlines). _RAW_PUSH_FORCE_RE spots a force or sweep spelling: '--for[a-z-]*' covers
# --for/--force/--force-with-lease/--force-if-includes; the short cluster scan now admits a digit
# ('-[A-Za-z0-9]*f'), so an ipv4/ipv6 '-4f'/'-6f' clustered with force is caught (F-117), and its
# disclosed false-hit on an attached -o value ending in f ('-of') now also covers '-o4f'; the short
# cluster anchor now also admits a preceding QUOTE character (matching the '+refspec' anchor), so a
# quoted wrapped cluster like env git push '-4f' ... is caught (F-117); and the
# '+<ref>' force-refspec anchor admits a preceding
# QUOTE character as well as start/whitespace, so a quoted '+main:main' under a wrapper is caught
# (F-112 round-3) - all accepted over-asks on this path. _RAW_PUSH_DELETE_RE spots a branch-deletion
# spelling (round-3: a delete rewrites the protected line with no force flag and no '+'): a '--de...'
# long flag ('--de' is git-unambiguous for --delete; '--dry-run' shares no such prefix), a
# '--pru...' long flag (--prune deletes remote refs absent locally with no force flag,
# F-117), or a 'd' carried ANYWHERE in a '-' short cluster that now admits digits
# ('-[A-Za-z0-9]*d'), so a clustered ipv4/ipv6 '-4d'/'-6d' is caught (F-117), and like the force
# anchor it too now admits a preceding QUOTE character (so a quoted wrapped '-4d' is caught),
# mirroring the force '-[A-Za-z0-9]*f' shape (round-4: the old
# cluster-END '-[A-Za-z]*d\b' let a wrapped 'git push -dv origin main' slip while the parsed path
# denies it), both name-independent like the force spellings (the true target may be unreadable or
# shell-expanded); or an empty-source ':<protected>' refspec, judged by its visible name and built
# from _PROTECTED (single source, no drift), so an ordinary colon token (a URL, a src:dst refspec)
# does not ask. _RAW_PROTECTED_RE is built from _PROTECTED and folds case: a raw over-match only
# asks/denies, never allows. An embedded quote or backslash-escape INSIDE a flag in the raw string
# (env git push -'f' origin main, \-f, escaped +main) is not matched, because bash quote/escape removal
# cannot be replicated by a raw-string regex; this is the same inherent lexical boundary as a
# shell-expanded $VAR, disclosed and not chased (F-117/F-119).
_RAW_PUSH_RE = re.compile(r"(?is)\bgit\b.*?\bpush\b")
_RAW_PUSH_FORCE_RE = re.compile(r"(?i)--for[a-z-]*|--mirror\b|--all\b|--branches\b|(?:^|[\s'\"])-[A-Za-z0-9]*f|(?:^|[\s'\"])\+\S")
_RAW_PUSH_DELETE_RE = re.compile(
    r"(?i)--de[a-z-]*|--pru[a-z-]*|(?:^|[\s'\"])-[A-Za-z0-9]*d[A-Za-z0-9]*|(?:^|[\s'\"]):(?:refs/heads/|heads/)?(?:"
    + "|".join(sorted(_PROTECTED)) + r")\b")
_RAW_PROTECTED_RE = re.compile(r"(?i)\b(?:" + "|".join(sorted(_PROTECTED)) + r")\b")
_RAW_COMMIT_RE = re.compile(r"(?is)\bgit\b.*?\bcommit\b")

def _head_branch(repo):
    """The branch HEAD is on at `repo`, or None when it cannot be read: a detached HEAD (symbolic-ref
    exits non-zero), an unborn ref, a broken or absent repo, a timeout, or any subprocess error.
    Read-only, offline, 5s timeout, mirroring _tree_is_clean: EVERY ambient GIT_*-prefixed var is
    scrubbed via _isolate_git_env so the probe reads the REAL repo at `-C <repo>` rather than an
    ambient-env decoy (and writes no ambient GIT_TRACE file), and GIT_OPTIONAL_LOCKS=0 keeps the
    read-only posture explicit. None is the fail-safe answer: the caller treats an unreadable HEAD as
    UNKNOWN, never as 'not protected'."""
    try:
        env = _isolate_git_env(dict(os.environ))
        env["GIT_OPTIONAL_LOCKS"] = "0"
        result = subprocess.run(
            ["git", "-C", repo, "symbolic-ref", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, env=env)
        if result.returncode != 0:
            return None  # detached HEAD, not a repository, or an unreadable one
        return result.stdout.strip() or None
    except Exception:
        return None

def _is_protected_ref(name):
    """True when a ref, or the DESTINATION side of a refspec already split by the caller, names a
    protected branch: bare ('main') or carrying the 'refs/heads/' or 'heads/' prefix a push refspec
    may spell out. Comparison is EXACT and case-sensitive, as git resolves ref names ('Main' is a
    different ref); case-folding lives only in the raw fallback. A name in another namespace
    (refs/tags/..., refs/remotes/...) is not a protected-branch destination."""
    if not name:
        return False
    for prefix in ("refs/heads/", "heads/"):
        if name.startswith(prefix):
            return name[len(prefix):] in _PROTECTED
    return name in _PROTECTED

def _push_parse(args):
    """Parse the token list AFTER a 'git push' subcommand (the args of _git_sub_and_args). Returns
    (force, delete, mirror, sweep_all, prune, operands): force is any force spelling (-f/--force, every
    --force-with-lease spelling - a lease-guarded force still rewrites the remote ref - and
    --force-if-includes, with --mirror implying force as git does); delete is the branch-deletion mode
    (--delete or a clustered -d; the empty-source ':<dst>' delete refspec is judged per-operand by the
    caller); mirror and sweep_all are the ref-sweeping modes (--mirror; --all/--branches pushes EVERY
    branch, protected included, so forced it clobbers the protected one without naming it); prune is
    --prune (round-4: it DELETES every remote branch absent locally, with NO force flag - witnessed
    deleting a remote master through a wildcard refspec - and the caller judges it against the refspec
    shape); operands is the remote/refspec token list in command order. The option region is split from
    the operand region at the first '--'/'--end-of-options' boundary via the shipped _split_pre_post, so
    an operand that merely looks like an option ('git push origin -- --force') is never read as one; post
    tokens extend operands AFTER the loop, preserving command order. Flag detection is VALUE-AWARE (F-112
    round-3): force/delete/mirror/sweep/prune are recognized INSIDE the token loop, only on a token that
    is NOT the value of a preceding value-taking option, so '-o --force' and '--push-option --force' read
    as the option VALUE they are, never as a force flag. Each candidate long option is still matched by
    CONSERVATIVE LONG PREFIX (the shipped _has_long_prefix, applied one token at a time), plus the
    short '-f'/'-d' cluster scan, so an abbreviated '--for' or '--d' - even one git itself would reject
    as ambiguous - routes to ASK/DENY, never a silent allow. A value-taking option is likewise
    recognized by prefix (--rep for --repo, --push-opt for --push-option), so its value token is
    skipped rather than misread as the repository or a refspec (F-121). A value-taking option in its SEPARATED
    form (_PUSH_LONG_ARG_OPTS / _PUSH_SHORT_ARG_OPTS) sets skip_value so its value token is skipped,
    never scanned as a flag or an operand; the attached '--opt=value'/'-o<value>' shape carries its
    value in the same token and needs no skip. --force-with-lease and --signed take an OPTIONAL value
    git accepts only ATTACHED (gitcli(7) stuck form), and --force-if-includes takes no value at all, so
    none of the three ever consumes a following token and none is in the skip sets. Negation and no-op
    flags are NOT modelled (round-4, disclosed): '--no-force'/'--no-delete' cancel nothing here,
    '--force-if-includes' alone (a documented no-op without --force-with-lease) still reads as force,
    and --dry-run is judged like the real thing - all safe-direction over-denies; re-issue without the
    contrived flag combination. Also NOT modelled (disclosed, contrived under-block): a
    `--`/`--end-of-options` that is the VALUE of a preceding value-taking option (git push -o
    --end-of-options --force ...) is split as an end-of-options boundary by _split_pre_post
    before the value-aware loop, so a force after it can read as an operand; re-issue without the
    contrived option-value."""
    pre, post, _had_sep = _split_pre_post(args)
    force = delete = mirror = sweep_all = prune = False
    skip_value = False  # the previous token was a separated value-taking option: skip its value
    operands = []       # remote + refspecs in command order; the loop appends, then post extends
    for tok in pre:
        if skip_value:
            skip_value = False
            continue  # this token is a prior option's VALUE, not a flag or an operand
        if tok.startswith("--"):
            if "=" not in tok and any(_has_long_prefix([tok], _n[2:]) for _n in _PUSH_LONG_ARG_OPTS):
                skip_value = True  # a value-taking push option OR an unambiguous abbreviation git accepts
                                   # (e.g. --rep for --repo, --push-opt for --push-option) consumes the
                                   # next token as its value; erring toward skip is safe (an ambiguous
                                   # prefix git itself rejects is moot), and this closes the abbreviated
                                   # value-option silent-allow (F-121)
            elif _has_long_prefix([tok], "mirror"):  # --mirror: a forced sweep of ALL refs
                mirror = True
            elif _has_long_prefix([tok], "all") or _has_long_prefix([tok], "branches"):
                sweep_all = True  # --all/--branches: every branch, protected included
            elif (_has_long_prefix([tok], "force") or _has_long_prefix([tok], "force-with-lease")
                  or _has_long_prefix([tok], "force-if-includes")):
                force = True
            elif _has_long_prefix([tok], "delete"):  # '--d'/'--de'/... err toward delete; '--dry-run'
                delete = True                        # shares no prefix with 'delete', so it never matches
            elif _has_long_prefix([tok], "prune"):   # --prune deletes remote refs absent locally; the
                prune = True                         # caller judges it against the refspec shape
            continue  # other long options carry no judged meaning
        if tok.startswith("-") and len(tok) > 1:
            body = tok[1:]
            for i, ch in enumerate(body):
                if ch in _PUSH_SHORT_ARG_OPTS:  # '-o': the rest of this token (or the next) is its value
                    if i == len(body) - 1:
                        skip_value = True  # a bare '-o': the value is the next token
                    break  # stop the cluster scan; the remainder is the value, not flags
                if ch == "f":
                    force = True
                elif ch == "d":
                    delete = True
            continue
        operands.append(tok)  # a bare operand: the remote or a refspec
    operands += post  # after '--' every token is a refspec (push has no pathspec position)
    return force or mirror, delete, mirror, sweep_all, prune, operands

def _wildcard_hits_branches(dst):
    """True when a wildcard push destination could expand into refs/heads/ (a protected branch),
    so a sweep the guard cannot enumerate ASKS. The wildcard's literal prefix (before the first
    '*') is compatible with refs/heads/ when it is a prefix of 'refs/heads/' (a wildcard at or
    above the heads namespace: '*', 'refs/*', 'refs/he*'), is itself under refs/heads/ or heads/,
    or carries no refs/ prefix at all (a bare 'name*'). A wildcard provably confined to a non-heads
    namespace (refs/tags/*, refs/remotes/*, refs/notes/*) cannot reach a branch and is excluded.
    GD-145: 'refs/*' (namespace-wide) evaded the old refs/heads/-only test."""
    if "*" not in dst:
        return False
    prefix = dst[:dst.index("*")]
    return ("refs/heads/".startswith(prefix) or prefix.startswith(("refs/heads/", "heads/"))
            or not prefix.startswith("refs/"))


def _push_protected(tokens, args, cwd):
    """Classify one git push segment against the protected set: ('deny', detail, act_noun), where
    act_noun names the denied act for the banner ('force-push' or 'branch deletion'); ('ask', detail,
    None); or None (the push provably misses the protected branches, or is neither forced nor a
    deletion nor a sweep). The refspec-NAMED paths are judged purely lexically and are
    redirect-INDEPENDENT (a 'git -C <dir> push --force origin main' still denies: the protected NAME
    is what is guarded, wherever the remote lives). Operand ROLES follow the grammar git itself uses
    ('git push <repository> <refspec>...'): the FIRST bare operand is the repository and is never
    judged as a destination (a remote literally named 'main' is not a protected refspec - F-112
    round-3), and only the later, refspec-position operands are judged, by their DESTINATION. The
    exemption is safe against a skip-set omission: git itself reads the first operand as the
    repository, and an unskipped option value can only SHIFT operands right (a spurious extra first
    operand), keeping every real refspec in judged positions - the over-inclusive direction, never a
    hidden refspec. A protected DELETION denies like a force (F-112 round-3): '--delete'/'-d' with a
    protected refspec-position operand, or the empty-source ':<dst>' refspec form. A SWEEP this guard
    cannot prove misses the protected names ASKS (round-4 completes the set): a wildcard force or
    delete destination over the branch namespace, --mirror, a forced --all/--branches, the MATCHING
    refspec ':' (every branch existing on both ends; '+:' is its forced form), which is empty on BOTH
    sides so the per-operand loop has no destination to judge (round-3 skipped it - a silent allow),
    and --prune with a wildcard or matching refspec or --all/--branches, which DELETES every remote
    branch absent locally
    with NO force flag (witnessed deleting a remote master). Only the refspec-less force-push and a
    forced or deleted HEAD/@ consult the HEAD probe, and only when the repository view is provable
    (no non-cosmetic ambient GIT_* var, no command-local redirect, a usable session cwd); otherwise
    it ASKS, never a silent allow of an apparent force or deletion. Git resolves a pushed or FORCED
    HEAD/@ to the current branch; a DELETED HEAD or ':@' git itself REJECTS as a nonexistent or
    invalid remote ref, so the probe-backed deny on the delete side is a harmless safe-direction
    over-deny kept for uniformity (round-4 rewording: round-3 wrongly claimed git resolves a deleted
    HEAD to the current branch)."""
    force, delete, mirror, sweep_all, prune, operands = _push_parse(args)
    refspecs = operands[1:]  # operands[0] is the repository (git's own grammar): never a destination
    # Collect every FORCED and every DELETED destination over the REFSPEC-position operands. Forced:
    # the dst of a '+'-prefixed refspec always, and of every refspec when a force flag is present; the
    # src:dst DESTINATION is what the push overwrites ('feature:main' forces main; 'main:feature'
    # forces only feature). Deleted: every refspec dst when --delete/-d is present, and the dst of an
    # empty-source ':<dst>' refspec (git's push-to-delete form) whatever the flags. The MATCHING
    # refspec ':' (and its forced '+:' form) is empty on BOTH sides: it pushes every branch existing
    # on both ends, protected included, yet names no destination for this loop to judge, so it is
    # flagged as a sweep rather than skipped (round-4; the skip was a silent allow). A wildcard
    # destination over the branch namespace is also tracked UNFORCED, for the --prune judgment.
    forced_dsts = []
    deleted_dsts = []
    matching = False     # a ':' or '+:' matching refspec was seen ('+:' is its forced form)
    wild_branch = False  # some refspec dst wildcards the branch namespace, forced or not
    for op in refspecs:
        plus = op.startswith("+")
        spec = op[1:] if plus else op
        if spec == ":":
            matching = True  # the matching refspec: a sweep whether bare (':') or forced ('+:')
            continue
        if ":" in spec:
            src, dst = spec.split(":", 1)
        else:
            src, dst = None, spec  # a bare refspec pushes to a like-named destination
        if not dst:
            continue  # 'main:' names no destination to judge
        if _wildcard_hits_branches(dst):
            wild_branch = True
        if plus or force:
            forced_dsts.append(dst)
        if delete or src == "":
            deleted_dsts.append(dst)
    for dst in forced_dsts:
        if _is_protected_ref(dst):
            return ("deny", "force-pushes the protected branch {!r} (a force flag or a '+'-prefixed "
                            "refspec targeting it)".format(dst), "force-push")
    for dst in deleted_dsts:
        if _is_protected_ref(dst):
            return ("deny", "deletes the protected branch {!r} (a --delete/-d flag or an empty-source "
                            "':<dst>' refspec targeting it); a deletion rewrites the protected line as "
                            "surely as a force-push".format(dst), "branch deletion")
    # A sweep the guard cannot prove misses the protected names ASKS rather than denies: a wildcard
    # force or delete destination that can reach the branch namespace, a --prune sweep (a wildcard
    # or matching refspec, or --all/--branches: it DELETES remote branches absent locally with no
    # force flag), the plain matching refspec, a --mirror push (which force-updates AND deletes every
    # ref), or a forced --all/--branches. The --prune combinations are judged BEFORE the plain
    # matching case so a pruning matching-refspec ('git push --prune origin :') names its deletion
    # effect rather than the non-deleting matching explanation (GD-145).
    for dst in forced_dsts + deleted_dsts:
        if _wildcard_hits_branches(dst):
            return ("ask", "force-pushes or deletes the wildcard refspec {!r}, a sweep this guard "
                           "cannot prove misses the protected branches".format(dst), None)
    if prune and (wild_branch or matching or sweep_all):
        return ("ask", "combines --prune with a sweeping selector (a wildcard or matching refspec, "
                       "or --all/--branches), which DELETES every selected remote ref whose local "
                       "counterpart is absent, without requiring a force flag; the sweep can remove a "
                       "protected "
                       "branch and cause potentially irreversible loss, and this guard cannot prove "
                       "it misses the protected branches", None)
    if matching:
        return ("ask", "pushes the matching refspec ':' ('+:' is its forced form), a matching-refspec "
                       "push of every branch existing on both ends, which this guard cannot prove "
                       "misses the protected branches", None)
    if mirror:
        return ("ask", "is a --mirror push, which force-updates every matching remote ref and DELETES "
                       "every remote ref (branch, tag, note) absent locally; on a shared remote this "
                       "removes branches, protected or not, and can cause potentially irreversible "
                       "loss, and this guard cannot prove it misses the protected branches", None)
    if force and sweep_all:
        return ("ask", "force-pushes --all/--branches, a sweep that includes any protected branch",
                None)
    # HEAD and @ are explicit refspecs. On a push or FORCE git resolves them to the current branch
    # (documented: 'git push <remote> HEAD' pushes the current branch to a like-named remote branch),
    # so a forced HEAD/@ on a protected branch rewrites the protected line even though the literal
    # token is not a protected NAME: treat it like a refspec-less force and resolve via the HEAD
    # probe (F-112 B1). A DELETED HEAD/@ git itself REJECTS ('--delete <remote> HEAD' names a
    # nonexistent remote ref, ':@' an invalid one), so the probe-backed deny on the delete side is a
    # harmless safe-direction over-deny kept for uniformity (round-4 rewording; round-3 wrongly
    # claimed git resolves a deleted HEAD). Computed BEFORE the out-of-scope gate so a '+HEAD' or a
    # deleted HEAD with no global -f is not returned as out-of-scope.
    head_proxy = any(dst in ("HEAD", "@") for dst in forced_dsts + deleted_dsts)
    if not force and not delete and not head_proxy:
        return None  # no force, no delete, no forced/deleted HEAD/@: a plain (or plus-forced
        # non-protected) push is out of scope (a protected NAME was already checked and a '+feature'
        # plus-force to a non-protected branch is allowed)
    if not head_proxy and refspecs:
        return None  # explicit non-HEAD refspecs present, every destination judged above, none protected
    if delete and not force and not head_proxy:
        return None  # a refspec-less --delete: git itself rejects it ("--delete doesn't make sense
        # without any refs"), so there is no implicit current-branch deletion to resolve
    # The forced (or deleted) target is the CURRENT branch (a refspec-less force, or a forced/deleted
    # HEAD/@). Resolve it via the read-only HEAD probe, only when the repository view is provable; the
    # push.default=matching configured-state residual (which could force every matching branch) is
    # disclosed, not modelled; likewise a bare 'git push --prune <remote>' whose deletion is driven
    # by a configured remote.<name>.push refspec, and a configured mirror mode (remote.<name>.mirror
    # =true in git config, or a command-local 'git -c remote.<name>.mirror=true push'), which
    # reproduce the force-and-delete sweep with no bulk flag in the judged push args: the guard reads
    # no git config offline, so these are disclosed residuals, not modelled (GD-145). A '--repo=<remote>'
    # option does not displace the positional repository operand: git gives the command-line positional
    # precedence (git-push(1)), so operands[0] stays the repository and the guard's slice is correct; a
    # '--repo' form carrying a refspec-shaped positional is rejected by git as an unknown repository
    # rather than executed as a push (verified, git 2.53).
    act, act_noun = (("deletes", "branch deletion") if delete and not force
                     else ("force-pushes", "force-push"))
    if _ambient_repo_view_override() or not _segment_dir_simple(tokens):
        return ("ask", "{} the current branch (a refspec-less push, or a HEAD/@ refspec) under a "
                       "non-cosmetic ambient GIT_* variable or a command-local redirect, so this guard "
                       "cannot resolve which branch it would target".format(act), None)
    base = cwd if isinstance(cwd, str) and cwd else None
    head = _head_branch(base) if base is not None else None
    if head is None:
        return ("ask", "{} the current branch (a refspec-less push, or a HEAD/@ refspec) but HEAD "
                       "could not be resolved, so this guard cannot prove the target is off the "
                       "protected line".format(act), None)
    if _is_protected_ref(head):
        return ("deny", "{} the current branch (a refspec-less push, or a HEAD/@ refspec) while HEAD "
                        "is the protected branch {!r}, so the apparent target is the protected line "
                        "itself".format(act, head), act_noun)
    return None  # HEAD provably a non-protected branch: the forced or deleted target is off the protected line

def _commit_on_protected(tokens, cwd):
    """The ASK detail when this git commit segment cannot be proven to land off the protected line, else
    None (HEAD provably a non-protected branch). Fail-to-ASK posture throughout: an unprovable repository
    view (a non-cosmetic ambient GIT_* var, or a command-local -C/--git-dir/--work-tree redirect or
    leading env assignment, both via the shared _segment_dir_simple/_ambient_repo_view_override checks),
    a missing session cwd, and an unresolvable HEAD (detached, a non-repository, a probe error) all ASK;
    only a probe that positively names a non-protected branch allows. A 'cd' in an EARLIER segment of the
    same compound command is NOT modelled (the probe reads the session cwd): the covered accidental case
    is the plain add-and-commit chain in the session repo, and asking on every compound commit would
    defeat the guard's own purpose (this is an ASK-level, fully-recoverable surface, so the lighter
    posture than git_discard's compound handling is proportionate)."""
    if _ambient_repo_view_override() or not _segment_dir_simple(tokens):
        return ("runs under a non-cosmetic ambient GIT_* variable or carries a command-local redirect "
                "(-C/--git-dir/--work-tree or a leading env assignment), so this guard cannot prove "
                "which repository's HEAD it would commit on")
    base = cwd if isinstance(cwd, str) and cwd else None
    head = _head_branch(base) if base is not None else None
    if head is None:
        return ("targets a repository whose HEAD this guard could not resolve (no usable session "
                "directory, a detached HEAD, or a failed probe), so it cannot prove the commit lands "
                "off the protected line")
    if _is_protected_ref(head):
        return "would commit directly on the protected branch {!r}".format(head)
    return None


def _protected_line_fallback(command):
    """FAIL-SAFE conservative raw scan for the two cases the parsed path cannot judge: the tokenizer could not
    parse the command (unbalanced quotes), OR git is hidden under a command-word wrapper (env/sudo/...).
    An apparent git force-push (any -f/--force/--for.../--mirror/--all form, or a '+'-refspec anchored
    to start, whitespace, or either quote character, so a quoted '+main:main' under sudo is caught), or
    an apparent branch DELETION (a '--de...' long flag or a '-d' cluster, protected-named or not - like
    the force spellings, the true target may be unreadable or shell-expanded - or an empty-source
    ':<protected>' refspec, judged by its visible name), protected-named or not, ASKS; an apparent git
    commit ASKS; anything else ALLOWS (the true boundary). It ASKS, NEVER a hard DENY (a recoverable
    prompt, matching _git_discard_fallback) and NEVER a silent allow of an apparent force-push or
    deletion. It OVER-MATCHES by design (a keyword in prose or an unrelated '+' or '-d' token asks),
    the documented posture of the sibling fallbacks (_diff_source_fallback, _git_discard_fallback)."""
    if _RAW_PUSH_RE.search(command) and (_RAW_PUSH_FORCE_RE.search(command)
                                         or _RAW_PUSH_DELETE_RE.search(command)):
        named = " a protected branch" if _RAW_PROTECTED_RE.search(command) else " a target this guard cannot read"
        return _ask(
            "AIQT rule prtbrn (protected-branch-integrity): this command could not be fully parsed by the "
            "shell lexer (unbalanced quotes) or hides git under a command-word wrapper, and it appears to "
            "force-push or delete{}; confirm it cannot rewrite the protected line, or re-issue it as a "
            "plain, parseable git command. {}".format(named, _PROTECTED_ALTS),
            "AIQT guardrail: an apparent force-push or branch deletion this guard cannot fully parse - "
            "confirm before proceeding (rule prtbrn, fail-safe).")
    if _RAW_COMMIT_RE.search(command):
        return _ask(
            "AIQT rule artbr1 (branch-and-merge-on-green): the command could not be parsed by the shell "
            "lexer (likely unbalanced quotes) and it appears to run git commit; this guard cannot prove "
            "the commit lands off the protected line, so confirm, or re-issue it as a parseable "
            "command. {}".format(_PROTECTED_ALTS),
            "AIQT guardrail: an unparseable command appears to commit; this guard cannot prove it lands "
            "off the protected branch - confirm before proceeding (rule artbr1, fail-safe).")
    return _allow()

def protected_line(data):
    """prtbrn + artbr1 (integ/protected-branch-integrity, integ/branch-and-merge-on-green),
    PreToolUse/Bash. DENY a git push segment that force-pushes a protected branch - a force spelling
    (--force, --force-with-lease bare or =value, --force-if-includes, a bare or clustered -f, a
    conservative long prefix) or a '+'-prefixed refspec whose DESTINATION names a protected branch -
    or that DELETES one: a --delete/-d flag with a protected refspec-position operand, or the
    empty-source ':<dst>' delete refspec (F-112 round-3); the deny banner names the actual act,
    force-push vs branch deletion (round-4). Destinations are judged only in REFSPEC position (the
    first bare operand is the repository, so a remote literally named 'main' is not a false deny),
    and flag detection is value-aware (a force or delete spelling in an option-value position,
    '-o --force', is not a flag). A refspec-less force-push and a forced or deleted HEAD/@ resolve
    their target through the read-only HEAD probe (deny on a protected HEAD, fail-to-ASK when
    unprovable; the deleted-HEAD deny is a harmless over-deny, git itself rejecting a HEAD delete as
    a nonexistent ref). A sweep this guard cannot prove misses the protected names ASKS: a wildcard
    force or delete refspec over the branch namespace, --mirror, a forced --all/--branches, the
    matching ':'/'+:' refspec, and --prune with a wildcard or matching refspec or --all/--branches (round-4: prune
    deletes absent remote branches with no force flag). A force-push or delete to a non-protected
    ref and a plain non-force push ALLOW. ASK a git commit segment while HEAD is a protected branch
    (probed read-only under the ambient-GIT_* scrub; fail-to-ASK when HEAD cannot be resolved): the
    protected line changes only through a reviewed merge, and the direct commit is the accidental
    case this client guard catches - only the literal 'commit' subcommand (a merge, cherry-pick, or
    revert that lands commits on the protected line is out of this accidental-case scope by design);
    server-side branch protection is the real gate. A DENY found in any segment wins over a pending
    ASK (a confirmed rewrite outranks the recoverable prompt, mirroring the git_discard posture). No
    escape hatch prefix: the ASK outcomes are themselves the human gate, and the deny mirrors
    commit_identity's absoluteness."""
    if data.get("hook_event_name") != PRETOOL:
        return _hard_block("aiqt_hooks: protected_line wired to unexpected event {!r}; failing closed"
                           .format(data.get("hook_event_name")))
    tool_name = data.get("tool_name")
    if tool_name is None:
        return _deny_missing_tool_name("prtbrn")
    if tool_name != "Bash":
        return _allow()  # a present-but-different tool is out of scope (defensive; the matcher governs)
    command = (data.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        return _deny(
            "AIQT rule prtbrn (protected-branch-integrity): the Bash payload carried no readable command "
            "string, so the protected-line check could not run; failing closed.",
            "AIQT guardrail: denied a Bash call with no readable command (rule prtbrn, fail-closed).")
    try:
        segments = _segments(command)
    except ValueError:
        return _protected_line_fallback(command)
    cwd = data.get("cwd")
    pending_ask = None  # the first ASK found; a DENY anywhere returns immediately and wins over it
    saw_git = False     # did any parsed segment have 'git' as its command word?
    for tokens, _sep in segments:
        if _command_word(tokens) != "git":
            continue
        saw_git = True
        if _has_info_flag(tokens):
            continue  # a --help/-h segment shows help, it pushes and commits nothing (see diff_source)
        sub, args = _git_sub_and_args(tokens)
        if sub == "push":
            outcome = _push_protected(tokens, args, cwd)
            if outcome is None:
                continue
            decision, detail, act_noun = outcome
            if decision == "deny":
                return _deny(
                    "AIQT rule prtbrn (protected-branch-integrity): this git push {}. The protected "
                    "line is never rewritten or overwritten directly; it changes only through a "
                    "reviewed, verified merge (artbr1). {}".format(detail, _PROTECTED_ALTS),
                    "AIQT guardrail: denied a {} targeting a protected branch (rule prtbrn)."
                    .format(act_noun))
            if pending_ask is None:
                pending_ask = _ask(
                    "AIQT rule prtbrn (protected-branch-integrity): this git push {}. Confirm it "
                    "cannot rewrite the protected line before proceeding. {}"
                    .format(detail, _PROTECTED_ALTS),
                    "AIQT guardrail: a git push this guard cannot prove misses the protected branch - "
                    "confirm before proceeding (rule prtbrn).")
        elif sub == "commit":
            detail = _commit_on_protected(tokens, cwd)
            if detail is not None and pending_ask is None:
                pending_ask = _ask(
                    "AIQT rule artbr1 (branch-and-merge-on-green): this git commit {}. A change "
                    "develops on a feature branch and lands on the protected line only through a "
                    "reviewed merge (prtbrn); server-side branch protection remains the real gate, and "
                    "this prompt covers the accidental direct commit. {}"
                    .format(detail, _PROTECTED_ALTS),
                    "AIQT guardrail: a direct commit on (or unprovably off) the protected branch - "
                    "confirm, or move to a feature branch first (rule artbr1).")
    if pending_ask is not None:
        return pending_ask
    # No parsed segment had 'git' as its command word, yet the raw command names git: a
    # command-word wrapper (env/sudo/command/xargs/timeout/nohup/sh -c) or obfuscation hides the
    # git call. Mirror git_discard's raw posture - an apparent wrapped force-push, deletion, or
    # commit ASKS rather than passing silently; a FRAGMENTED command word or verb is the disclosed
    # residual (F-112 1C), and so is a compound in which ANY OTHER segment - earlier OR later -
    # parses with git as its command word ('git status && sudo git push -f ...', and equally
    # 'env git push -f ... && git status'): the benign git segment satisfies saw_git and suppresses
    # this catch - a round-3 disclosure reworded in round-4 (the suppression was never only-earlier),
    # adversarial and best-effort like git_discard's fragmented-verb residual, not chased.
    if not saw_git and _RAW_GIT_RE.search(command):
        return _protected_line_fallback(command)
    return _allow()


# --- brnrot: branch creation must stay rooted on origin/HEAD -----------------------------------------

# ============================================================================
# CONSTANTS (module-level)
# ============================================================================

# Module sentinel and end-of-options boundary already exist in the target module;
# reproduced here so the draft is self-contained and directly runnable.
_ASK_START = object()

# The ONLY options tolerated inside a clean canonical creation: valueless booleans.
# Exact match only -- git resolves an unambiguous long-option PREFIX to the full
# option, so an abbreviated form (e.g. "--qui") is deliberately NOT matched here and
# falls through to the ASK path, never to a clean-allow.
_CLEAN_LONG_BOOLEANS = frozenset(("--quiet", "--force"))
_CLEAN_SHORT_LETTERS = frozenset("qf")
# git branch additionally exposes --verbose/-v as a valueless boolean; checkout/switch/worktree do NOT
# (git rejects -v there and creates nothing), so -v is clean for BRANCH only, not shared.
_BRANCH_CLEAN_LONG = _CLEAN_LONG_BOOLEANS | frozenset(("--verbose",))
_BRANCH_CLEAN_SHORT = _CLEAN_SHORT_LETTERS | frozenset("v")

# git branch: copy (a creation whose start is the SOURCE).
_BRANCH_COPY_SHORT = frozenset("cC")
_BRANCH_COPY_LONG = frozenset(("--copy",))

# git branch: recognized NON-creation actions and listing forms (allow silently).
# delete (d/D), move/rename (m/M), all (a), remotes (r), set-upstream (u).
_BRANCH_NONCREATION_SHORT = frozenset("dDmMaru")
_BRANCH_NONCREATION_LONG = frozenset((
    "--delete", "--move", "--all", "--remotes", "--list",
    "--set-upstream-to", "--unset-upstream", "--show-current", "--edit-description",
))

# git worktree: only `add` can create; the rest are recognized non-creations.
_WORKTREE_NONCREATION_SUBS = frozenset((
    "list", "remove", "move", "prune", "lock", "unlock", "repair",
))
_WORKTREE_CREATE_SHORT = frozenset("bB")


# ============================================================================
# PARSER 1: checkout / switch
# ============================================================================

def _checkout_creation_start(args, switch=False):
    """Maximally-conservative start-point classifier for `git checkout` / `git switch`.

    Returns a start-point string (probe: rooted allows, orphaned DENIES) ONLY for a
    clean canonical creation; `_ASK_START` for any non-clean creation-capable form;
    `None` for a confident non-creation (checkout/switch of an existing ref).
    """
    if switch:
        short_triggers = frozenset("cC")            # -c / -C
        long_triggers = frozenset(("--create", "--force-create"))
    else:
        short_triggers = frozenset("bB")            # -b / -B
        long_triggers = frozenset()                 # checkout has no clean long creation form

    created = False
    branch_name = None      # the trigger's value (new branch name); None => none seen yet
    operands = []           # positional start-point candidates
    saw_eoo = False

    i = 0
    n = len(args)
    while i < n:
        tok = args[i]

        if not saw_eoo and tok in _EOO_TOKENS:
            saw_eoo = True
            i += 1
            continue
        if saw_eoo:
            # checkout: post-boundary tokens are PATHSPECS (ignored, never the start).
            # switch: no pathspecs, so post-boundary tokens are operands.
            if switch:
                operands.append(tok)
            i += 1
            continue

        if tok.startswith("--") and len(tok) > 2:
            name = tok.split("=", 1)[0]
            has_value = "=" in tok
            if name in long_triggers and not created:
                created = True
                if has_value:
                    branch_name = tok.split("=", 1)[1]
                else:
                    i += 1
                    if i < n:
                        branch_name = args[i]
                i += 1
                continue
            if name in _CLEAN_LONG_BOOLEANS and not has_value:
                i += 1
                continue
            # any other long option: unknown, value-taking, negation, abbreviation,
            # a second trigger, --orphan, --detach, --track, --patch, ... -> ASK
            return _ASK_START

        if tok.startswith("-") and len(tok) > 1:
            chars = tok[1:]
            j = 0
            while j < len(chars):
                ch = chars[j]
                if ch in _CLEAN_SHORT_LETTERS:
                    j += 1
                    continue
                if ch in short_triggers and not created:
                    created = True
                    rest = chars[j + 1:]
                    if rest:
                        branch_name = rest              # attached value: -bNAME
                    else:
                        i += 1
                        if i < n:
                            branch_name = args[i]       # separated value: -b NAME
                    break
                # unknown short letter, or a duplicate trigger -> ASK
                return _ASK_START
            i += 1
            continue

        operands.append(tok)
        i += 1

    if created:
        if len(operands) > 1:
            return _ASK_START                           # more operands than a clean creation
        if branch_name is None:
            return None                                 # trigger with no name: git error, no ref
        return operands[0] if operands else "HEAD"

    # no creation trigger: a checkout/switch of an existing ref -> allow silently
    return None


# ============================================================================
# PARSER 2: branch
# ============================================================================

def _branch_command_creation_start(args):
    """Maximally-conservative start-point classifier for `git branch`.

    Clean creation is a bare `<name> [<start>]`, or a copy (`-c`/`-C`/`--copy`) whose
    start is the SOURCE (explicit first operand, else HEAD). Recognized non-creation
    actions and listing forms allow silently; everything else ASKs.
    """
    ask = False
    noncreation = False
    copy = False
    operands = []
    saw_eoo = False

    i = 0
    n = len(args)
    while i < n:
        tok = args[i]

        if not saw_eoo and tok in _EOO_TOKENS:
            saw_eoo = True
            i += 1
            continue
        if saw_eoo:
            operands.append(tok)                        # no pathspecs: operands
            i += 1
            continue

        if tok.startswith("--") and len(tok) > 2:
            name = tok.split("=", 1)[0]
            has_value = "=" in tok
            if tok.startswith("--no-"):
                ask = True                              # any negation flips the classifier -> ASK
            elif name in _BRANCH_COPY_LONG:
                if has_value:
                    ask = True                          # unexpected value on a copy trigger
                else:
                    copy = True
            elif name in _BRANCH_NONCREATION_LONG:
                noncreation = True
            elif name in _BRANCH_CLEAN_LONG and not has_value:
                pass                                    # tolerated valueless boolean (branch: +--verbose)
            else:
                ask = True                              # unknown/value-taking/abbreviated -> ASK
            i += 1
            continue

        if tok.startswith("-") and len(tok) > 1:
            for ch in tok[1:]:
                if ch in _BRANCH_COPY_SHORT:
                    copy = True
                elif ch in _BRANCH_NONCREATION_SHORT:
                    noncreation = True
                elif ch in _BRANCH_CLEAN_SHORT:
                    pass
                else:
                    ask = True                          # any letter outside the known sets -> ASK
            i += 1
            continue

        operands.append(tok)
        i += 1

    if ask:
        return _ASK_START
    if copy and noncreation:
        return _ASK_START                               # contradictory triggers -> ASK
    if noncreation:
        return None
    if copy:
        if len(operands) == 0:
            return None                                 # incomplete copy: git error, no ref
        if len(operands) == 1:
            return "HEAD"                               # copy current HEAD to the new name
        if len(operands) == 2:
            return operands[0]                          # copy the explicit SOURCE
        return _ASK_START                               # unexpected extra operands
    if operands:
        if len(operands) > 2:
            return _ASK_START
        return operands[1] if len(operands) > 1 else "HEAD"
    return None                                         # no operands, no trigger: a listing


# ============================================================================
# PARSER 3: worktree
# ============================================================================

def _worktree_creation_start(args):
    """Maximally-conservative start-point classifier for `git worktree`.

    Only `worktree add -b/-B <name> <path> [<start>]` is a clean creation. A bare
    `worktree add <path> [<commit-ish>]` (no -b) is ambiguous -> ASK. `--detach`/`-d`
    and `--orphan` -> ASK. Recognized non-creation subcommands allow silently.
    """
    if not args:
        return _ASK_START
    subcommand = args[0]
    if subcommand != "add":
        if subcommand in _WORKTREE_NONCREATION_SUBS:
            return None
        return _ASK_START                               # unknown/absent subcommand -> fail-safe

    created = False
    branch_name = None
    operands = []                                       # [<path>, <start>]
    saw_eoo = False

    i = 1
    n = len(args)
    while i < n:
        tok = args[i]

        if not saw_eoo and tok in _EOO_TOKENS:
            saw_eoo = True
            i += 1
            continue
        if saw_eoo:
            operands.append(tok)                        # no pathspecs: operands
            i += 1
            continue

        if tok.startswith("--") and len(tok) > 2:
            name = tok.split("=", 1)[0]
            has_value = "=" in tok
            if name in _CLEAN_LONG_BOOLEANS and not has_value:
                i += 1
                continue
            # --detach, --orphan, --no-*, unknown, value-taking, abbreviated -> ASK
            return _ASK_START

        if tok.startswith("-") and len(tok) > 1:
            chars = tok[1:]
            j = 0
            while j < len(chars):
                ch = chars[j]
                if ch in _CLEAN_SHORT_LETTERS:
                    j += 1
                    continue
                if ch in _WORKTREE_CREATE_SHORT and not created:
                    created = True
                    rest = chars[j + 1:]
                    if rest:
                        branch_name = rest              # attached value: -bNAME
                    else:
                        i += 1
                        if i < n:
                            branch_name = args[i]       # separated value: -b NAME
                    break
                # -d (detach) or any other short letter, or a duplicate trigger -> ASK
                return _ASK_START
            i += 1
            continue

        operands.append(tok)
        i += 1

    if not created:
        return _ASK_START                               # bare `add <path> [<commit-ish>]`: ambiguous
    if branch_name is None:
        return None                                     # -b with no name: git error, no ref
    if len(operands) == 0:
        return None                                     # add -b name  (no path): git error, no ref
    if len(operands) == 1:
        return "HEAD"                                   # add -b name /path  (no start-point)
    if len(operands) == 2:
        return operands[1]                              # operands = [path, start]
    return _ASK_START                                   # unexpected extra operands


# ============================================================================
# SELF-TEST: asserts EVERY required vector
# ============================================================================


def _branch_creation_start(sub, args):
    if sub == "checkout":
        return _checkout_creation_start(args, switch=False)
    if sub == "switch":
        return _checkout_creation_start(args, switch=True)
    if sub == "branch":
        return _branch_command_creation_start(args)
    if sub == "worktree":
        return _worktree_creation_start(args)
    return None


def _branch_root_git(repo, *args):
    env = _isolate_git_env(dict(os.environ))
    env["GIT_OPTIONAL_LOCKS"] = "0"
    # Neutralize replace refs (git replace --graft, refs/replace/*) so a grafted parent cannot make an
    # orphaned start appear rooted through merge-base, which honours replacements by default. The on-disk
    # .git/info/grafts residual is out of scope (an accidental-case guardrail, disclosed in the residue).
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    try:
        return subprocess.run(
            ["git", "-C", repo, *args], capture_output=True, text=True, timeout=5, env=env)
    except Exception:
        return None


def _branch_root_probe(repo, start):
    """Return ('rooted'|'orphaned'|'unknown', detail), based only on unmasked git exit statuses."""
    protected = _branch_root_git(
        repo, "rev-parse", "--verify", "--quiet", "--end-of-options", "origin/HEAD^{commit}")
    if protected is None or protected.returncode != 0 or not protected.stdout.strip():
        return ("unknown", "origin/HEAD cannot be resolved")
    start_probe = _branch_root_git(
        repo, "rev-parse", "--verify", "--quiet", "--end-of-options",
        "{}^{{commit}}".format(start))
    if start_probe is None or start_probe.returncode != 0 or not start_probe.stdout.strip():
        return ("unknown", "the branch start point {!r} cannot be resolved".format(start))
    merge = _branch_root_git(
        repo, "merge-base", protected.stdout.strip(), start_probe.stdout.strip())
    if merge is None:
        return ("unknown", "git merge-base could not be launched")
    if merge.returncode == 0 and merge.stdout.strip():
        return ("rooted", merge.stdout.strip())
    if merge.returncode == 1:
        # A shallow clone truncates history, so a missing merge base can mean the shared root was simply
        # not fetched, not that the branch is orphaned. In a shallow repo, treat exit 1 as unknown (ASK),
        # never a false orphaned deny.
        shallow = _branch_root_git(repo, "rev-parse", "--is-shallow-repository")
        if shallow is None or shallow.returncode != 0:
            return ("unknown", "the shallow-repository status could not be determined, so a missing "
                               "merge base cannot be told from an orphaned start")
        value = shallow.stdout.strip()
        if value == "true":
            return ("unknown", "the repository is shallow, so a missing merge base cannot be told from "
                               "an orphaned start; run `git fetch --unshallow` and retry")
        if value != "false":
            return ("unknown", "unexpected shallow-repository status {!r}".format(value))
        return ("orphaned", "git merge-base reported no common ancestor")
    return ("unknown", "git merge-base returned status {}".format(merge.returncode))


def branch_root(data):
    """brnrot PreToolUse/Bash guard over recognized branch-creation forms."""
    if data.get("hook_event_name") != PRETOOL:
        return _hard_block(
            "aiqt_hooks: branch_root wired to unexpected event {!r}; failing closed"
            .format(data.get("hook_event_name")))
    tool_name = data.get("tool_name")
    if tool_name is None:
        return _deny_missing_tool_name("brnrot")
    if tool_name != "Bash":
        return _allow()
    tool_input = data.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return _deny(
            "AIQT rule brnrot (branch-rooted-on-live-main): the Bash payload carried no readable "
            "command string, so branch creation could not be checked; failing closed.",
            "AIQT guardrail: denied a Bash call with no readable command (rule brnrot, fail-closed).")
    try:
        segments = _segments(command)
    except ValueError:
        # An unsupported LATER construct (a heredoc, a process substitution) must not discard a
        # proven-complete creation already recovered in the prefix: partial-lex and judge the recovered
        # segments, so a canonical orphan creation still DENIES (DENY outranks the parse error). A command
        # with no recovered creation falls back to the open-grammar allow (best-effort, disclosed).
        try:
            segments = [(seg.argv, seg.sep_after) for seg in _lex_command(command, partial=True)[0]]
        except ValueError:
            return _allow()  # even partial recovery failed: open grammar, best-effort

    pending_ask = None
    saw_dir_change = False
    for tokens, _sep in segments:
        word = _command_word(tokens)
        if word in _CD_BUILTINS or word == "popd":
            # a cd/pushd/popd BEFORE the git segment moves the target out of the session cwd; popd lands on
            # an unknowable stack-top directory, so it too routes the following creation to a fail-safe ASK.
            saw_dir_change = True
            continue
        if word != "git" or _has_info_flag(tokens):
            continue
        sub, args = _git_sub_and_args(tokens)
        start = _branch_creation_start(sub, args)
        if start is None:
            continue
        if start is _ASK_START:
            if pending_ask is None:
                pending_ask = _ask(
                    "AIQT rule brnrot: this command uses a branch/worktree form this guard cannot classify "
                    "with confidence (a --track/-t tracking form, an --orphan, an abbreviated or negated "
                    "option, or an option of unknown arity); it may create a branch from an unverified "
                    "start, so its ancestry cannot be checked here. Re-issue it "
                    "with an explicit start point, or confirm to proceed; the CI branch-root gate remains "
                    "the authoritative backstop.",
                    "AIQT guardrail: confirm this branch-creation form; its start point is ambiguous "
                    "(rule brnrot).")
            continue
        if saw_dir_change or _ambient_repo_view_override() or not _segment_dir_simple(tokens):
            if pending_ask is None:
                pending_ask = _ask(
                    "AIQT rule brnrot: this branch-creation command runs under a directory change or a "
                    "repository-view override this guard cannot reconcile with the session repository (a "
                    "cd/pushd in an earlier segment, a non-cosmetic ambient GIT_* variable, or a "
                    "command-local -C/--git-dir/--work-tree redirect). Re-issue it as a plain git command "
                    "from the target repository after confirming the target.",
                    "AIQT guardrail: confirm the branch-creation repository before proceeding "
                    "(rule brnrot).")
            continue
        cwd = data.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            outcome, detail = ("unknown", "the session repository directory is unavailable")
        else:
            outcome, detail = _branch_root_probe(cwd, start)
        if outcome == "orphaned":
            return _deny(
                "AIQT rule brnrot (branch-rooted-on-live-main): start point {!r} has no merge base "
                "with origin/HEAD. Do not dispatch work onto the retired root; recut from origin/HEAD "
                "or replay the branch's unique commits onto it first.".format(start),
                "AIQT guardrail: denied branch creation from an orphaned start point (rule brnrot).")
        if outcome == "unknown" and pending_ask is None:
            pending_ask = _ask(
                "AIQT rule brnrot: branch-root ancestry could not be evaluated ({}). Confirm the "
                "repository and start point; if origin/HEAD is missing, run "
                "`git remote set-head origin --auto`, then retry.".format(detail),
                "AIQT guardrail: branch-root ancestry is unresolved; confirm before proceeding "
                "(rule brnrot).")
    return pending_ask if pending_ask is not None else _allow()


# --- gatdis (EN-5 PR-B): a Bash command that weakens a verification gate -------------------------------

# The git subcommands that accept --no-verify, and the two where the SHORT -n IS --no-verify. Verified
# against the git 2.53.0 man pages (git-commit(1), git-merge(1), git-push(1), git-pull(1), git-rebase(1),
# git-am(1)), 2026-08-19: commit and am bind -n to --no-verify; on push -n is --dry-run and on merge and
# pull it is --no-stat, so the short scan runs ONLY where -n is the bypass, never where it is a harmless
# dry-run or diffstat flag (flagging -n there would block safe commands, the opposite of this control's
# purpose). cherry-pick and revert accept no --no-verify at all and are out of the roster.
_NOVERIFY_VERBS = frozenset(("commit", "merge", "push", "pull", "rebase", "am"))
_NOVERIFY_SHORT_N_VERBS = frozenset(("commit", "am"))

# Value-taking options of the short-n verbs, so an option VALUE is never char-scanned as a clustered
# flag (the '-o' lesson of _push_parse applied to commit -m). Verified against git-commit(1) and
# git-am(1), git 2.53.0, 2026-08-19, on the gitcli(7) rule the push tables use (aiqt_hooks.py, the
# _PUSH_LONG_ARG_OPTS note): a MANDATORY value may be attached or separated, so the cluster scan stops
# at the letter and a bare trailing letter consumes the next token; an OPTIONAL value is legal only in
# the attached "stuck" form, so the scan stops at the letter but a bare one consumes NOTHING; the LONG
# sets are the mandatory-value long options in their SEPARATED form (--message <msg>), whose value
# token could itself begin with '-n' and must be skipped (their '--opt=value' shape carries the value
# in the same token and consumes nothing). These sets cover the COMMON value-taking options rather
# than claiming an exhaustive enumeration: an OMITTED value-taking option is safe-direction (on a
# contrived input whose value itself spells -n or --no-verify it can only cause an over-ask/over-deny,
# never a silent allow), so an option is added only once confirmed value-taking (adding a NON-value-
# taking option would wrongly skip a real operand and could cause a silent allow, so it is never done).
_GATE_SHORT_VALUE_OPTS = {
    "commit": frozenset(("m", "F", "C", "c", "t")),
    "am": frozenset(()),
}
_GATE_SHORT_STUCK_OPTS = {
    "commit": frozenset(("S", "u")),
    "am": frozenset(("S",)),
}
_GATE_LONG_ARG_OPTS = {
    "commit": frozenset((
        "--message", "--file", "--author", "--date", "--template", "--trailer", "--cleanup",
        "--reuse-message", "--reedit-message", "--fixup", "--squash", "--pathspec-from-file")),
    "am": frozenset(("--whitespace", "--exclude", "--include", "--directory", "--quoted-cr",
                     "--resolvemsg")),
}

# The checker lexicon for the ASK heuristics. Three shapes qualify a segment as checker-shaped: a
# known checker COMMAND WORD; a command whose NAME PARTS (basename split on non-alphanumerics, exact
# part match so 'latest' never trips a 'test' substring) contain a checker part; or a known RUNNER
# whose non-option, non-assignment operand qualifies by either test ('make test', 'python -m pytest',
# 'bash tools/run_all_checks.sh'). The lexicon is deliberately a heuristic: it routes to ASK only,
# never a deny, so an over-match costs a prompt and an under-match is the disclosed residue.
_CHECKER_WORDS = frozenset((
    "pytest", "tox", "nox", "unittest", "mypy", "pyright", "ruff", "flake8", "pylint", "bandit",
    "eslint", "tsc", "jest", "vitest", "mocha", "rspec", "rubocop", "phpunit", "phpstan",
    "golangci-lint", "staticcheck", "shellcheck", "hadolint", "yamllint", "markdownlint",
    "gitleaks", "pre-commit", "ctest", "cppcheck", "clang-tidy"))
_CHECKER_RUNNERS = frozenset((
    "make", "npm", "pnpm", "yarn", "npx", "node", "go", "cargo", "mvn", "mvnw", "gradle", "gradlew",
    "python", "python3", "py", "rake", "bundle", "poetry", "pipenv", "uv", "uvx",
    "sh", "bash", "zsh", "dash"))
_CHECKER_NAME_PARTS = frozenset((
    "test", "tests", "selftest", "selftests", "check", "checks", "checker", "lint", "linter",
    "verify", "validate", "audit", "conformance", "vet", "clippy", "gate", "gates"))
_NAME_SPLIT_RE = re.compile(r"[^a-z0-9]+")

# The failure-discarding right-hand sides: an exit-status swallow after '||' (true or the ':' builtin),
# and a truncating stdout sink after '|' that, under default pipeline semantics, replaces the checker
# exit status with its own and can cut the failing tail of the output. tee/cat/less are NOT truncating
# and never qualify.
_EXIT_SWALLOWS = frozenset(("true", ":"))
_TRUNCATING_SINKS = frozenset(("head", "tail"))

# The safe alternative named in every deny/ask reason (mirrors _PROTECTED_ALTS): the rule IS the route.
_GATE_ALTS = (
    "Safe route: run the gate as-is and let its exit status stand; a failing gate is signal, so fix "
    "the artefact it guards. A genuinely broken hook or check is repaired or retired at its source "
    "through a reviewed change, never bypassed for one run.")

# Fallback-only raw-string probes, used when the shared tokenizer cannot parse the command (an unbalanced quote or an unsupported construct);
# mirrors the _RAW_PUSH_RE posture: conservative, over-matching, never a silent allow. '--no-ver'
# deliberately also hits '--no-verbose' (an over-deny on the unparseable path only); the short cluster
# probe requires a whitespace-preceded single-dash token so a long option ('--amend') never matches.
_RAW_NOVERIFY_VERB_RE = re.compile(r"(?is)\bgit\b.*?\b(?:commit|merge|push|pull|rebase|am)\b")
_RAW_NOVERIFY_RE = re.compile(r"(?i)--no-ver")
_RAW_SHORT_NOVERIFY_VERB_RE = re.compile(r"(?is)\bgit\b.*?\b(?:commit|am)\b")
_RAW_SHORT_N_RE = re.compile(r"(?:^|\s)-[A-Za-z]*n\b")
_RAW_CHECKER_RE = re.compile(
    r"(?i)\b(?:pytest|tox|nox|unittest|mypy|pyright|ruff|flake8|pylint|bandit|eslint|tsc|jest|"
    r"vitest|mocha|rspec|rubocop|phpunit|phpstan|golangci-lint|staticcheck|shellcheck|hadolint|"
    r"yamllint|markdownlint|gitleaks|pre-commit|ctest|cppcheck|clang-tidy|"
    r"tests?|selftests?|checks?|checker|lint\w*|verify|validate|audit|conformance)\b")
_RAW_SWALLOW_RE = re.compile(r"\|\|\s*(?:true|:)(?=\s|$)")
_RAW_TRUNCATE_RE = re.compile(r"\|\s*(?:head|tail)\b")
_RAW_COMMIT_MSG_GIT_RE = re.compile(r"(?is)\bgit\b.*?\bcommit\b")
_RAW_COMMIT_MSG_MARKER_RE = re.compile(r"`|\$\(")


def _no_verify_spelling(sub, args):
    """The matched hook-bypass spelling on this git segment, or None. The long form: a --no-verify
    token in the option region (before '--'/'--end-of-options', via the shipped _split_pre_post),
    matched exact or by CONSERVATIVE LONG PREFIX (_has_long_prefix, exactly as protected_line matches
    'force'): an ambiguous abbreviation git itself would reject ('--no-ver') matches ANYWAY, and a
    separated option VALUE in pre is scanned too - both err toward a deny, never an allow, while a
    LONGER distinct option (--no-verify-signatures, --no-verbose) never matches because its full name
    is not a prefix of 'no-verify'. The short form: a bare or clustered -n, ONLY on the verbs where -n
    IS --no-verify (commit, am), with the value-taking short and long options skipped (mirroring
    _push_parse) so an attached value ('-m-n ...'), a separated value ('--message -n'), or a stuck
    optional value ('-Skeyid') is never char-scanned as the flag."""
    pre, _post, _had_sep = _split_pre_post(args)
    if _has_long_prefix(pre, "no-verify"):
        return "a --no-verify spelling"
    if sub not in _NOVERIFY_SHORT_N_VERBS:
        return None
    value_opts = _GATE_SHORT_VALUE_OPTS[sub]
    stuck_opts = _GATE_SHORT_STUCK_OPTS[sub]
    long_arg_opts = _GATE_LONG_ARG_OPTS[sub]
    skip_value = False  # the previous token was a separated value-taking option: skip its value
    for tok in pre:
        if skip_value:
            skip_value = False
            continue  # this token is a prior option's VALUE, not a flag
        if tok.startswith("--"):
            if "=" not in tok and tok in long_arg_opts:
                skip_value = True  # its value is the next token
            continue  # long options were judged by _has_long_prefix above, never char-scanned
        if tok.startswith("-") and len(tok) > 1:
            body = tok[1:]
            for i, ch in enumerate(body):
                if ch in value_opts:  # mandatory value: attached remainder, or the next token if bare
                    if i == len(body) - 1:
                        skip_value = True
                    break  # the remainder of this token is the value, not flags
                if ch in stuck_opts:  # optional value is attached-only: bare form consumes NOTHING
                    break
                if ch == "n":
                    return "the short -n (--no-verify) in {!r}".format(tok[:40])
    return None


def _name_parts_hit(name):
    """True when a name, split on non-alphanumerics and lowercased, carries a checker-shaped PART
    (exact part match: 'run_all_checks.sh' hits on 'checks', while 'latest' never hits on a 'test'
    substring)."""
    return any(p in _CHECKER_NAME_PARTS for p in _NAME_SPLIT_RE.split(name.lower()) if p)


def _is_checker_segment(tokens):
    """True when a segment is CHECKER-SHAPED: its command word is a known checker, its command word's
    name parts hit the checker parts, or it is a known runner one of whose non-option, non-assignment
    operands qualifies by either test ('make test', 'go vet', 'python -m pytest', 'npx jest',
    'bash tools/run_all_checks.sh'). Heuristic by design (routes to ASK only): a runner's separated
    option value is scanned as an operand (an accepted over-ask), and a checker hidden inside an
    'sh -c' quoted script body is one opaque token and is missed (the disclosed residue)."""
    word = _command_word(tokens)
    if not word:
        return False
    lw = word.lower()
    if lw in _CHECKER_WORDS or _name_parts_hit(lw):
        return True
    if lw not in _CHECKER_RUNNERS:
        return False
    for tok in tokens[_command_word_index(tokens) + 1:]:
        if tok.startswith("-") or _ENV_ASSIGN_RE.match(tok):
            continue
        if tok.lower() in _CHECKER_WORDS or _name_parts_hit(tok):
            return True
    return False


def _gate_weakening_fallback(command):
    """FAIL-SAFE conservative scan when the shared tokenizer cannot parse the command (an unbalanced quote or an unsupported construct): an apparent
    git hook bypass (a no-verify verb plus a --no-ver spelling) DENIES; an apparent git commit/am with
    a short -n cluster ASKS (the raw string cannot bind the cluster to its subcommand, so it cannot
    prove the -n is the bypass rather than an unrelated flag); a checker keyword next to a raw swallow
    or truncating-pipe spelling ASKS; anything else ALLOWS (the true boundary). Over-matching by
    design, the documented posture of the sibling fallbacks (_diff_source_fallback,
    _commit_identity_fallback, _protected_line_fallback): re-issue the command parseable."""
    if _RAW_NOVERIFY_VERB_RE.search(command) and _RAW_NOVERIFY_RE.search(command):
        return _deny(
            "AIQT rule gatdis (gate-discipline): the command could not be parsed by the shell lexer "
            "(likely unbalanced quotes) and it appears to bypass verification hooks with a --no-verify "
            "spelling; failing closed. {}".format(_GATE_ALTS),
            "AIQT guardrail: denied an unparseable command that appears to bypass git verification "
            "hooks (rule gatdis, fail-safe).")
    if _RAW_SHORT_NOVERIFY_VERB_RE.search(command) and _RAW_SHORT_N_RE.search(command):
        return _ask(
            "AIQT rule gatdis (gate-discipline): the command could not be parsed by the shell lexer "
            "(likely unbalanced quotes) and it appears to run git commit or git am with a short -n, "
            "which on those verbs bypasses the verification hooks; confirm it does not, or re-issue "
            "it as a parseable command. {}".format(_GATE_ALTS),
            "AIQT guardrail: an unparseable git commit/am appears to carry -n (--no-verify) - confirm "
            "before proceeding (rule gatdis, fail-safe).")
    if _RAW_CHECKER_RE.search(command) and (
            _RAW_SWALLOW_RE.search(command) or _RAW_TRUNCATE_RE.search(command)):
        return _ask(
            "AIQT rule gatdis (gate-discipline): the command could not be parsed by the shell lexer "
            "(likely unbalanced quotes) and it appears to swallow or truncate a checker's failure "
            "signal ('|| true', '|| :', '| head', '| tail'); confirm the checker's exit status still "
            "gates, or re-issue it as a parseable command. {}".format(_GATE_ALTS),
            "AIQT guardrail: an unparseable command appears to discard a checker's failure signal - "
            "confirm before proceeding (rule gatdis, fail-safe).")
    return _allow()


def gate_weakening(data):
    """gatdis (integ/gate-discipline), PreToolUse/Bash. DENY a git segment that bypasses its
    verification hooks: a --no-verify spelling (exact or conservative long prefix) on a subcommand
    that accepts it (commit, merge, push, pull, rebase, am), or the short -n on the two verbs where
    -n IS --no-verify (commit, am; on push -n is --dry-run and on merge/pull it is --no-stat, so it
    is deliberately not flagged there). ASK a checker-shaped segment whose failure signal is
    discarded: swallowed by an immediately following '|| true' or '|| :', or piped into a truncating
    sink (head, tail) whose exit status replaces the checker's under default pipeline semantics. The
    split posture is deliberate: the hook bypass is lexical and zero-intent, so it DENIES with no
    escape-hatch prefix (mirroring commit_identity's absoluteness); 'what is a gate' is not lexically
    certain, so the heuristics only ASK and a mis-shaped name costs a prompt, never a block. A DENY
    found in any segment wins over a pending ASK (mirrors protected_line)."""
    if data.get("hook_event_name") != PRETOOL:
        return _hard_block("aiqt_hooks: gate_weakening wired to unexpected event {!r}; failing closed"
                           .format(data.get("hook_event_name")))
    tool_name = data.get("tool_name")
    if tool_name is None:
        return _deny_missing_tool_name("gatdis")
    if tool_name != "Bash":
        return _allow()  # a present-but-different tool is out of scope (defensive; the matcher governs)
    command = (data.get("tool_input") or {}).get("command")
    if not isinstance(command, str):
        return _deny(
            "AIQT rule gatdis (gate-discipline): the Bash payload carried no readable command string, "
            "so the gate-weakening check could not run; failing closed.",
            "AIQT guardrail: denied a Bash call with no readable command (rule gatdis, fail-closed).")
    try:
        segments = _segments(command)
    except ValueError:
        return _gate_weakening_fallback(command)
    pending_ask = None  # the first ASK found; a DENY anywhere returns immediately and wins over it
    for index, (tokens, sep_after) in enumerate(segments):
        if _command_word(tokens) == "git" and not _has_info_flag(tokens):
            sub, args = _git_sub_and_args(tokens)
            if sub in _NOVERIFY_VERBS:
                spelling = _no_verify_spelling(sub, args)
                if spelling is not None:
                    return _deny(
                        "AIQT rule gatdis (gate-discipline): this git {} carries {}, a deliberate "
                        "bypass of the verification hooks that gate it. Never weaken a gate to obtain "
                        "a pass; fix the artefact instead. {}".format(sub, spelling, _GATE_ALTS),
                        "AIQT guardrail: denied a git verification-hook bypass (--no-verify family) "
                        "(rule gatdis).")
        if not _is_checker_segment(tokens):
            continue
        # The "immediately following" segment, advancing PAST any EMPTY segments (a bare
        # line-continuation/newline inserts a segment with no tokens, so 'pytest ||\n true' and
        # 'pytest |\n head' would otherwise read as having no following swallow/sink and miss the
        # ASK). Only genuinely empty segments are skipped; a real intervening command (a non-empty
        # segment) still breaks adjacency and is NOT skipped.
        nxt_index = index + 1
        while nxt_index < len(segments) and not segments[nxt_index][0]:
            nxt_index += 1
        nxt = segments[nxt_index][0] if nxt_index < len(segments) else []
        if sep_after == "||" and _command_word(nxt) in _EXIT_SWALLOWS:
            if pending_ask is None:
                pending_ask = _ask(
                    "AIQT rule gatdis (gate-discipline): {!r} looks like a verification gate and its "
                    "failure is swallowed by the following '|| {}', so a failing check would read as "
                    "a pass. If it gates this work, run it bare and let the exit status stand; "
                    "confirm only when this command is genuinely not a gate. {}"
                    .format(_command_word(tokens), _command_word(nxt), _GATE_ALTS),
                    "AIQT guardrail: a checker-shaped command has its failure swallowed ('|| true') - "
                    "confirm before proceeding (rule gatdis).")
        elif sep_after == "|" and _command_word(nxt) in _TRUNCATING_SINKS:
            if pending_ask is None:
                pending_ask = _ask(
                    "AIQT rule gatdis (gate-discipline): {!r} looks like a verification gate and is "
                    "piped into '{}', a truncating sink: under default pipeline semantics the "
                    "pipeline reports the sink's exit status, not the checker's, and the truncation "
                    "can also cut the failing output, so the gate's failure signal is discarded. Run "
                    "it bare, or redirect the output to a file and read that. {}"
                    .format(_command_word(tokens), _command_word(nxt), _GATE_ALTS),
                    "AIQT guardrail: a checker-shaped command is piped into a truncating sink "
                    "(| head/tail) - confirm before proceeding (rule gatdis).")
    if pending_ask is not None:
        return pending_ask
    return _allow()


# --- sectvl: shell substitution in a git commit argument --------------------------------------------
def _commit_msg_subst_marker(value, opaque, value_index, seg):
    """The executable marker in a candidate git commit argument, or None. The per-token opacity signal
    distinguishes a substituting double-quoted/unquoted marker from a single-quoted or escaped literal;
    the final-token supplement covers the narrow unquoted '$(' split produced by _lex_command."""
    if not opaque:
        return None
    if "`" in value:
        return "a backtick"
    if "$(" in value:
        return "a $( command substitution"
    if value.endswith("$") and value_index == len(seg.argv) - 1 and seg.sep_after == "(":
        return "a $( command substitution"
    return None


_COMMIT_MSG_COMMAND_MODIFIERS = frozenset((
    "command", "exec", "builtin", "nohup", "time", "!"))
_COMMIT_MSG_ENV_VALUE_OPTS = frozenset((
    "-u", "--unset", "-C", "--chdir", "-S", "--split-string", "--argv0"))


def _commit_msg_command_index(tokens):
    """Index of this hook's effective command word after recognized leading command modifiers.

    This is deliberately local to commit_msg_subst: other guards rely on the shared _command_word's
    narrower contract. Leading shell assignments are skipped first. The command/exec/builtin/nohup/time/!
    modifiers advance one word; env additionally skips its leading option tokens, the separated values of
    its common value-taking options, and NAME=VALUE assignments. Returns len(tokens) when no command remains.
    """
    i = _command_word_index(tokens)
    n = len(tokens)
    while i < n:
        word = tokens[i].rsplit("/", 1)[-1]
        if word in _COMMIT_MSG_COMMAND_MODIFIERS:
            i += 1
            continue
        if word != "env":
            return i
        i += 1
        options = True
        while i < n:
            token = tokens[i]
            if _ENV_ASSIGN_RE.match(token):
                i += 1
                continue
            if options and token == "--":
                options = False
                i += 1
                continue
            if options and token.startswith("-") and token != "-":
                if "=" not in token and token in _COMMIT_MSG_ENV_VALUE_OPTS:
                    i += 2
                else:
                    i += 1
                continue
            break
    return i


def _commit_msg_subst_hit(seg):
    """Return (argument, marker) for the first post-subcommand hit in a recognized git commit segment.

    Every token after commit is inspected without Git option binding: Bash performs substitution before Git
    parses options or an end-of-options token, so neither an option value nor `--` makes a marker safe.
    """
    tokens = seg.argv
    command_index = _commit_msg_command_index(tokens)
    if (command_index >= len(tokens)
            or tokens[command_index].rsplit("/", 1)[-1] != "git"):
        return None
    sub, args = _git_sub_and_args(tokens[command_index:])
    if sub != "commit":
        return None
    offset = len(tokens) - len(args)
    for index, token in enumerate(args, offset):
        marker = _commit_msg_subst_marker(token, seg.argv_opaque[index], index, seg)
        if marker is not None:
            return token, marker
    return None


def _commit_msg_subst_fallback(command):
    """Conservative raw fallback for an unparseable command: apparent git commit + substitution marker
    ASKS; anything else ALLOWS at the true boundary. The probes intentionally over-match and can never
    earn an allow proof for an apparent in-scope hit."""
    if (_RAW_COMMIT_MSG_GIT_RE.search(command)
            and _RAW_COMMIT_MSG_MARKER_RE.search(command)):
        return _ask(
            "AIQT rule sectvl (tool-argument-validation): the command could not be parsed by the shell "
            "lexer and appears to carry a backtick or $( command substitution in a git commit argument. "
            "The shell may execute it BEFORE git processes the argument. Confirm it is deliberate, or "
            "re-issue with single quotes, escape the marker as \\` or \\$(, or write the message to a "
            "file and use git commit -F <file>. The shared lexer conservatively prompts on marker-bearing "
            "$'...' values even though Bash does not substitute inside them.",
            "AIQT guardrail: an unparseable git commit argument appears to carry an executable command "
            "substitution; confirm it is deliberate or re-issue in a safe form (rule sectvl).")
    return _allow()


def commit_msg_subst(data):
    """sectvl (security/tool-argument-validation), PreToolUse/Bash. ASK when a token after a recognized
    git commit subcommand is double-quoted or unquoted and carries a shell-executed backtick or $( command
    substitution. It never denies a detected substitution: legitimate uses exist, so the human confirms
    intent or re-issues the command in a safe form."""
    if data.get("hook_event_name") != PRETOOL:
        return _hard_block("aiqt_hooks: commit_msg_subst wired to unexpected event {!r}; failing closed"
                           .format(data.get("hook_event_name")))
    tool_name = data.get("tool_name")
    if tool_name is None:
        return _deny_missing_tool_name("sectvl")
    if tool_name != "Bash":
        return _allow()  # a present-but-different tool is out of scope (defensive; the matcher governs)
    tool_input = data.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return _ask(
            "AIQT rule sectvl (tool-argument-validation): the Bash payload carried no readable command "
            "string, so the git-commit argument substitution check could not run; confirm the call "
            "before proceeding.",
            "AIQT guardrail: a Bash call has no readable command; confirm before proceeding "
            "(rule sectvl, fail-safe).")
    try:
        segments = _lex_command(command)
    except ValueError:
        return _commit_msg_subst_fallback(command)
    for seg in segments:
        hit = _commit_msg_subst_hit(seg)
        if hit is None:
            continue
        argument, marker = hit
        return _ask(
            "AIQT rule sectvl (tool-argument-validation): this git commit argument {!r} carries {} in a "
            "lexical context that may substitute. Bash executes the marker BEFORE git processes the "
            "argument when it is double-quoted or unquoted. If that is not deliberate, re-issue with "
            "single quotes, escape the marker as \\` or \\$(, or write the message to a file and use "
            "git commit -F <file>. The shared lexer conservatively prompts on marker-bearing $'...' values "
            "even though Bash does not substitute inside them."
            .format(argument[:80], marker),
            "AIQT guardrail: a git commit argument appears to carry an executable command substitution; "
            "confirm it is deliberate or re-issue in a safe form (rule sectvl).")
    return _allow()


# --- secsec: an obvious hardcoded secret in a Write/Edit/MultiEdit/Bash write-form -------------------
# A COMPENSATING, shift-left control: it does NOT replace the CI secret-scan and gitleaks gates (they
# remain the real backstop), it moves the same high-signal detection to the moment a secret would be
# written, so an accidental paste is caught before it ever lands on disk. The patterns are SINGLE-SOURCED
# from tools/check_secrets.py, the pack's source of truth: the PREFIX provider-token shapes, the
# credential-named ASSIGN shape, and the PLACEHOLDER non-secret shape are rendered into the GENERATED
# REGION below by tools/gen_secret_patterns.py (drift-gated), so the hook can never fork from the scanner
# and the standalone plugin needs no runtime import of check_secrets (it stays stdlib-only). The decision
# mirrors check_secrets.py EXACTLY, scanning line by line: a provider-prefix match is a hit; a
# credential-named assignment is a hit only when its value is real (an unquoted value must carry both a
# letter and a digit) AND is not a PLACEHOLDER. The secret value is NEVER echoed into a reason; only the
# pattern label is named. Best-effort, targeting the accidental paste/commit, not an adversary: it does
# NOT catch an entropy-only secret with no recognizable shape, a secret written by a tool other than
# Write/Edit/MultiEdit/Bash, or a secret split across tokens/lines or built by concatenation; on the
# Bash path the command string is scanned as RAW TEXT (not tokenized by the shared lexer, not executed), so a secret
# assembled by concatenation or supplied through a shell variable or expansion is missed, but a redirect
# or an embedded '#' does NOT cause a Bash-path miss; and it does not catch a base64/obfuscated form.
#
# The pattern SOURCE STRINGS below are GENERATED from tools/check_secrets.py by
# tools/gen_secret_patterns.py and are drift-gated; NEVER hand-edit them, and NEVER runtime-import
# check_secrets. Edit tools/check_secrets.py and regenerate (gen_secret_patterns.py, then gen_hooks.py).
# BEGIN generated secret patterns (source: tools/check_secrets.py; regenerate with tools/gen_secret_patterns.py)
_SECSEC_PREFIX_SOURCES = [
    ('\\bgh[pousr]_[A-Za-z0-9]{16,}', 'GitHub token'),
    ('\\bgithub_pat_[A-Za-z0-9_]{20,}', 'GitHub fine-grained PAT'),
    ('\\bsk-[A-Za-z0-9]{20,}', 'OpenAI-style secret key'),
    ('\\bsk-proj-[A-Za-z0-9_-]{20,}', 'OpenAI project key'),
    ('\\bsk-ant-[A-Za-z0-9\\-_]{20,}', 'Anthropic key'),
    ('\\bAKIA[0-9A-Z]{16}\\b', 'AWS access key id'),
    ('\\bxox[baprs]-[A-Za-z0-9-]{10,}', 'Slack token'),
    ('\\bxapp-[A-Za-z0-9-]{10,}', 'Slack app-level token'),
    ('-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----', 'private key block'),
    ('\\beyJ[A-Za-z0-9_-]{8,}\\.[A-Za-z0-9_-]{8,}\\.[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])', 'JWT (JSON Web Token)'),
    ('\\bAIza[0-9A-Za-z_-]{35}(?![0-9A-Za-z_-])', 'Google API key'),
    ('\\b[sr]k_(?:live|test)_[0-9a-zA-Z]{20,}\\b', 'Stripe API key'),
    ('\\bglpat-[0-9A-Za-z_-]{20,}', 'GitLab personal access token'),
    ('\\bSG\\.[A-Za-z0-9_-]{22}\\.[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])', 'SendGrid API key'),
    ('\\bnpm_[A-Za-z0-9]{36}\\b', 'npm access token'),
    ('\\bpypi-AgEIcHlwaS[A-Za-z0-9_-]{50,}', 'PyPI upload token'),
    ('https://hooks\\.slack\\.com/services/T[A-Z0-9]{8,}/B[A-Z0-9]{8,}/[A-Za-z0-9]{24,}', 'Slack webhook URL'),
]
_SECSEC_ASSIGN_SOURCE = '(?ix)\n    (?:^|[^A-Za-z0-9])                       # start, or a non-alphanumeric\n    [A-Za-z0-9]*[_-]?                        # optional prefix such as aws_ or my-\n    (passwd|password|secret|token|api[_-]?key|access[_-]?key|\n       client[_-]?secret|auth[_-]?token|private[_-]?key|credential)\n    \\s*[:=]\\s*\n    (?:\n        (?P<q>[\'"])(?P<qvalue>(?:(?!(?P=q))[^\\n]){12,})(?P=q)  # quoted; qvalue excludes only the OPENING\n                                                     # delimiter (not both quotes), so a value that embeds\n                                                     # the other quote, e.g. "ab\'cd...", is not truncated\n      | (?P<value>[A-Za-z0-9+/=_.\\-]{16,})              # or unquoted; charset excludes {$<( so\n                                                     # templates and f-string holes cannot match\n    )\n    '
_SECSEC_PLACEHOLDER_SOURCE = '(?i)^(x{3,}|\\.{3,}|\\*{3,}|<[^>]+>|\\$\\{[^}]+\\}|\\$[A-Z_]+|(your|my|the)[_-]?\\w*|change[_-]?me|placeholder|example|sample|dummy|redacted|fake|test|todo|none|null|n/?a|actual_password_here)$'
_SECSEC_ENTROPY_ASSIGN_SOURCE = '(?x)\n    (?:^|[^A-Za-z0-9])\n    (?P<name>[A-Za-z][A-Za-z0-9_.\\-]*)\n    \\s*[:=]\\s*\n    (?:\n        # QUOTED: the WHOLE inter-quote value must be alphabet (closing quote required), so a value that\n        # embeds a non-alphabet char (an email\'s @, a URL\'s :) does NOT partially match on its prefix; no\n        # upper cap here because the closing quote bounds it, so a >150-char quoted secret still fires.\n        (?P<q>[\'"])(?P<qvalue>[A-Za-z0-9_./+=\\-]{40,})(?P=q)\n        # UNQUOTED: a possessive run (no backtracking) of 40 OR MORE alphabet chars that is NOT followed by @ or\n        # : (which would make it a prefix of a larger structured value such as an email or a URL); a longer\n        # all-alphabet unquoted value still fires on its 150-char prefix (char 151 is alphabet, not @/:).\n      | (?P<value>[A-Za-z0-9_./+=\\-]{40,}+)(?![@:])\n    )\n    '
_SECSEC_ENTROPY_MIN_LEN = 40
_SECSEC_ENTROPY_MAX_LEN = 150
_SECSEC_ENTROPY_THRESHOLD = 3.5
_SECSEC_CREDENTIAL_COMPONENTS = ('access', 'api', 'apikey', 'auth', 'client', 'credential', 'credentials', 'creds', 'key', 'pass', 'passphrase', 'passwd', 'password', 'pwd', 'secret', 'token')
_SECSEC_METADATA_COMPONENTS = ('alias', 'checksum', 'count', 'digest', 'dir', 'endpoint', 'file', 'fingerprint', 'id', 'length', 'name', 'path', 'public', 'size', 'type', 'uri', 'url', 'version')
# END generated secret patterns
# Compiled at module load from the generated source strings (stdlib re only; no runtime import of
# check_secrets). Recompiling from a pattern's .pattern string preserves its inline flags ((?ix)/(?i)),
# so these behave identically to check_secrets.py's own compiled objects.
_SECSEC_PREFIXES = [(re.compile(_pattern), _label) for _pattern, _label in _SECSEC_PREFIX_SOURCES]
_SECSEC_ASSIGN = re.compile(_SECSEC_ASSIGN_SOURCE)
_SECSEC_PLACEHOLDER = re.compile(_SECSEC_PLACEHOLDER_SOURCE)
# A JavaScript-style environment lookup (process.env.X, import.meta.env.X): a pure dotted-identifier
# path that BEGINS with a recognized env-access root is a CODE REFERENCE, not a literal secret, so it is
# excluded from the unquoted credential match (F-127). The root anchor is required, not a mere `env`
# segment anywhere, so a dotted token that only looks identifier-shaped (a Vault hvs.<random>, a PASETO
# v2.local.<payload>, or myorg.env.prod.<value> with env not at the root) stays caught. Mirrors
# check_secrets.py's DOTTED_PATH / _ENV_REF EXACTLY; hand-mirrored loop logic, not part of the generated
# region above (which carries only the single-sourced pattern strings).
_SECSEC_DOTTED_PATH = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
_SECSEC_ENV_REF = re.compile(r"(?i)\A(?:process\.env|import\.meta\.env|env)\.")


# GD-121: the entropy-gated generic-assignment detector, hand-mirrored from check_secrets.py EXACTLY as
# the ASSIGN/env-ref logic above is. The regex source, the credential/metadata component sets, and the
# threshold are single-sourced through the generated region; the DECISION logic below is the hand mirror
# (not part of the generated region, so the parity battery in tools/selftest_aiqt_hooks.py guards it).
_SECSEC_ENTROPY_ASSIGN = re.compile(_SECSEC_ENTROPY_ASSIGN_SOURCE)
_SECSEC_CREDENTIAL_COMPONENT_SET = frozenset(_SECSEC_CREDENTIAL_COMPONENTS)
_SECSEC_METADATA_COMPONENT_SET = frozenset(_SECSEC_METADATA_COMPONENTS)
_SECSEC_COMPONENT_SPLIT = re.compile(r"[_.\-]+")
_SECSEC_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")


def _secsec_shannon_entropy(value):
    """Shannon entropy (bits/char) of value; mirrors check_secrets._shannon_entropy EXACTLY."""
    if not value:
        return 0.0
    counts = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _secsec_split_components(name):
    """Lower-cased exact identifier components (split on _ - . and camelCase); mirrors
    check_secrets._split_components EXACTLY."""
    components = []
    for part in _SECSEC_COMPONENT_SPLIT.split(name):
        if not part:
            continue
        for token in _SECSEC_CAMEL.findall(part):
            components.append(token.lower())
    return components


# The target field per SINGLE-FIELD tool: the text a Write/Edit would write, or the command a Bash call
# would emit. MultiEdit is in scope too but carries a LIST of edits rather than one field, so it is
# extracted separately (see _secsec_multiedit_text); its name is added to the in-scope tool set here.
_SECSEC_FIELD = {"Write": "content", "Edit": "new_string", "Bash": "command"}
_SECSEC_TOOLS = frozenset(_SECSEC_FIELD) | {"MultiEdit"}


def _scan_secret(text):
    """Return the pattern label of the first real (non-placeholder) secret in text, or None. Mirrors
    tools/check_secrets.py's own decision EXACTLY, line by line: a provider-prefix match on a line is a
    hit (check_secrets does not placeholder-exclude a prefixed token); a credential-named ASSIGN match is
    a hit only when its value is real - an UNQUOTED value must contain both a letter and a digit (else it
    is likelier ordinary prose or code), and the value must not be a PLACEHOLDER. The matched value is
    never returned, only the label, so a reason can name the shape without echoing the secret."""
    for line in text.splitlines():
        for pattern, label in _SECSEC_PREFIXES:
            if pattern.search(line):
                return label
        # Scan EVERY credential-named assignment on the line, not just the first, exactly as
        # check_secrets.py does: a placeholder assignment earlier on the line must not mask a real
        # one after it. The first real (non-placeholder) match on any line is the hit.
        for match in _SECSEC_ASSIGN.finditer(line):
            value = match.group("qvalue") or match.group("value") or ""
            value = value.strip()
            # An UNQUOTED value must additionally look like a credential (letters AND digits), the same
            # extra bar check_secrets.py applies, because an unquoted match is far likelier to be prose.
            if value and match.group("qvalue") is None:
                if not (any(c.isalpha() for c in value) and any(c.isdigit() for c in value)):
                    value = ""
                elif _SECSEC_DOTTED_PATH.fullmatch(value) and _SECSEC_ENV_REF.match(value):
                    value = ""
            if value and not _SECSEC_PLACEHOLDER.match(value):
                return "credential-named variable assigned a literal"
        # GD-121: only when neither a provider prefix nor a credential-named ASSIGN matched this line, try
        # the entropy-gated generic detector, mirroring check_secrets._entropy_assign_is_secret EXACTLY:
        # metadata component on the LHS wins, require a credential component, exclude PLACEHOLDER before
        # entropy, exclude an UNQUOTED env-lookup, require a letter and a digit, then the entropy floor.
        # Reaching here means neither loop above returned, so the "nothing else flagged the line" gate the
        # CI scanner applies holds here too. The matched value is never returned, only the label.
        for match in _SECSEC_ENTROPY_ASSIGN.finditer(line):
            value = (match.group("qvalue") or match.group("value") or "").strip()
            if not value:
                continue
            components = _secsec_split_components(match.group("name"))
            if any(c in _SECSEC_METADATA_COMPONENT_SET for c in components):
                continue
            if not any(c in _SECSEC_CREDENTIAL_COMPONENT_SET for c in components):
                continue
            if _SECSEC_PLACEHOLDER.match(value):
                continue
            if match.group("qvalue") is None:
                if _SECSEC_DOTTED_PATH.fullmatch(value) and _SECSEC_ENV_REF.match(value):
                    continue
            # entropy + letter/digit on the first _SECSEC_ENTROPY_MAX_LEN chars (capture cap), mirroring
            # check_secrets: full value seen by the env-ref exclusion above, prefix judged for entropy.
            candidate = value[:_SECSEC_ENTROPY_MAX_LEN]
            if not (any(c.isalpha() for c in candidate) and any(c.isdigit() for c in candidate)):
                continue
            if _secsec_shannon_entropy(candidate) >= _SECSEC_ENTROPY_THRESHOLD:
                return "high-entropy literal assigned to a credential-like name"
    return None


def _secsec_multiedit_text(tool_input):
    """Return the text a MultiEdit would introduce: the newline-joined concatenation of the new_string
    value of each edit in tool_input["edits"] (a LIST of dicts, each carrying the "new_string" that edit
    would add). Return None to signal FAIL-CLOSED - the edits field absent or not a list, or ANY element
    not a dict or carrying no string new_string - so the caller denies, consistent with the handler's
    posture that a payload the scan cannot read is blocked. Edits are joined on a newline so each edit's
    text stays on its own line for the per-line scan and no secret is split or fused across the boundary."""
    edits = tool_input.get("edits")
    if not isinstance(edits, list):
        return None
    parts = []
    for edit in edits:
        if not isinstance(edit, dict):
            return None
        new_string = edit.get("new_string")
        if not isinstance(new_string, str):
            return None
        parts.append(new_string)
    return "\n".join(parts)


def secrets_shift_left(data):
    """secsec (security/keep-secrets-out), PreToolUse on Write|Edit|MultiEdit|Bash: DENY a call that would
    write an obvious hardcoded secret. Fail-closed like the other PreToolUse controls: a missing tool_name
    denies, a non-dict tool_input denies (the payload cannot be read), and a present tool in scope whose
    target payload is absent or malformed denies (the check cannot read what would be written). A present
    tool NOT in {Write, Edit, MultiEdit, Bash} is out of scope and allows. The target text is the Write
    content, the Edit new_string, the newline-joined new_string values of a MultiEdit's edits (the text
    being introduced), or the Bash command string (the write-form path, best-effort). A DENY names the
    pattern label only, never the secret."""
    if data.get("hook_event_name") != PRETOOL:
        return _hard_block("aiqt_hooks: secrets_shift_left wired to unexpected event {!r}; failing closed"
                           .format(data.get("hook_event_name")))
    tool_name = data.get("tool_name")
    if tool_name is None:
        return _deny_missing_tool_name("secsec")
    if tool_name not in _SECSEC_TOOLS:
        return _allow()  # out of scope (defensive; the matcher governs Write/Edit/MultiEdit/Bash)
    # A non-dict tool_input cannot answer the scan; fail CLOSED cleanly in-handler (mirrors git_discard's
    # isinstance-dict guard) rather than raising an AttributeError only the dispatcher would catch.
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return _deny(
            "AIQT rule secsec (keep-secrets-out): the {} payload carried no readable tool_input, so the "
            "secret scan could not run over what would be written; failing closed.".format(tool_name),
            "AIQT guardrail: denied a {} call with no readable payload (rule secsec, fail-closed)."
            .format(tool_name))
    if tool_name == "MultiEdit":
        target = _secsec_multiedit_text(tool_input)
        if target is None:
            return _deny(
                "AIQT rule secsec (keep-secrets-out): the MultiEdit payload carried no readable edits "
                "list, so the secret scan could not run over what would be written; failing closed.",
                "AIQT guardrail: denied a MultiEdit call with no readable edits (rule secsec, "
                "fail-closed).")
    else:
        field = _SECSEC_FIELD[tool_name]
        target = tool_input.get(field)
        if not isinstance(target, str):
            return _deny(
                "AIQT rule secsec (keep-secrets-out): the {} payload carried no readable {}, so the "
                "secret scan could not run over what would be written; failing closed.".format(tool_name, field),
                "AIQT guardrail: denied a {} call with no readable {} (rule secsec, fail-closed)."
                .format(tool_name, field))
    label = _scan_secret(target)
    if label is None:
        return _allow()
    reason = ("AIQT rule secsec (keep-secrets-out): the text this {} would write contains what looks like "
              "a hardcoded secret ({}). No credential, token, or key is written to a repository or any "
              "persisted location; supply it through the platform's secret store, environment, or auth "
              "flow instead. If it reached a remote, treat it as compromised and rotate it. (This is a "
              "compensating shift-left control; the CI secret-scan and gitleaks gates remain the backstop. "
              "The value is redacted from this message.)".format(tool_name, label))
    return _deny(reason,
                 "AIQT guardrail: denied a {} that would write an apparent hardcoded secret ({}) "
                 "(rule secsec).".format(tool_name, label))


# --- gensrc generated-artefact edit guard ------------------------------------------------------------
# A NEW constant set, deliberately NOT reusing FILE_PATH_TOOLS, which is ("Read", "Write", "Edit"): it
# omits MultiEdit and includes Read, so it does not describe this control's matcher. Mirrors the
# _SECSEC_TOOLS idiom.
_GENSRC_TOOLS = ("Write", "Edit", "MultiEdit")   # MultiEdit carries ONE top-level file_path
_GENSRC_REGISTRY_REL = os.path.join(".aiqt", "gensrc.json")
_GENSRC_VERSION = 1
_GENSRC_MAX_BYTES = 1_000_000  # the real registry is ~5 KB; a larger one is malformed (SECA bound)


def _gensrc_fail_ask(detail):
    """A fail-SAFE ASK shared by every gensrc_guard branch that cannot PROVE no-match. UNLIKE the
    fail-CLOSED PreToolUse controls above (which deny an unreadable input), gensrc_guard fails to ASK,
    like git_discard's boundary posture: this control's strongest outcome on a CONFIRMED violation is
    itself an ask (the human approving IS the opt-out), so a branch that DENIED on uncertainty would
    punish uncertainty harder than certainty. The ask still satisfies integ-check-fails-closed-on-
    unreadable in substance: the failure surfaces as a gate the human must clear and can never read as
    clean. Only a missing tool_name denies (the shared _deny_missing_tool_name contract)."""
    return _ask(
        "AIQT rule gensrc (generated-artefact-source-only): {}; failing safe to ask.".format(detail),
        "AIQT guardrail: asked because the generated-artefact edit guard could not clear this call "
        "({}) (rule gensrc, fail-safe).".format(detail))


def _load_gensrc_registry(root):
    """Read <root>/.aiqt/gensrc.json AT DECISION TIME and return one of ("absent", None),
    ("ok", entries), or ("bad", detail). `entries` is the list of (kind, target, sources, regenerate)
    tuples in registry order with kind=block entries dropped (a path guard cannot see which lines an
    edit touches; the block drift gates backstop those).

    ABSENT (FileNotFoundError from the lstat probe: ENOENT on the file or a missing .aiqt/ component) is
    the inert boundary: a repo with no registry gets no coverage (adopters author their own). Every OTHER
    read fault is BAD, never absent, so an unreadable input can never read as clean (integ-check-fails-
    closed-on-unreadable): a registry that is not a regular file (a symlink dangling or redirecting, a
    FIFO, a directory, a socket, a device; not a trusted regular file), a
    PermissionError/NotADirectoryError/IsADirectoryError, a non-UTF-8 decode, an oversize file (the bound
    is on BYTES via a binary read), malformed JSON, a non-int/unknown version, a non-list `generated`, a
    malformed entry, or a control character (NUL included) in an entry target (rejected BEFORE the
    block-skip). We do NOT use os.path.exists, which swallows EACCES (the trap gen_hooks documents at
    gen_hooks.py:79).
    Per-entry validation mirrors _canonical_target (tools/gen_gensrc.py:193-213), because gen_gensrc's
    validation only guarantees THIS repo's registry; an adopter-authored or hand-tampered registry the
    guard cannot fully read is BAD (it cannot prove no-match). Unknown extra keys within version 1 are
    tolerated: the version field pins the schema, and strictness on additions would break a
    forward-compatibly authored registry. This loader is BEST-EFFORT against the ACCIDENTAL case, not a
    hardened TOCTOU check: it rejects a STATIONARY non-regular registry and fails a delete race safe to
    BAD, but a registry concurrently SWAPPED to a different file type in the lstat-to-open window is a
    disclosed residual (see the comment below and the control residue), a sibling of the hard-link,
    case-insensitive-filesystem, and NFC/NFD aliases."""
    path = os.path.join(root, _GENSRC_REGISTRY_REL)
    # A generated-artefact registry must be a trusted REGULAR file. Anything that is NOT a regular file (a
    # symlink dangling or redirecting, a FIFO, a directory, a socket, a device) is BAD: a symlink could
    # make a foreign or nonexistent target read as this repo's registry, and a FIFO at the path would block
    # the open until the hook timeout. os.lstat is probed BEFORE the open: it does NOT follow a symlink and
    # does NOT block on a FIFO, so a STATIONARY non-regular registry (a symlink, FIFO, directory, ...) is
    # rejected as non-regular. A FileNotFoundError from lstat is genuine absence (a non-symlink ENOENT) ->
    # inert absent (the ONLY inert-absent path); any other lstat OSError is BAD; a path that resolves to
    # something other than a regular file is BAD; and an open-time disappearance (a delete race in the
    # lstat->open window) fails safe to BAD, handled at the open below. This read is BEST-EFFORT against
    # the ACCIDENTAL case, not a hardened check: a registry concurrently SWAPPED to a different type in the
    # lstat->open window (the lstat sees a regular file, the open then binds a substituted symlink/FIFO) is
    # a DISCLOSED residual OUTSIDE the accidental-case scope - a sibling of the hard-link, case-insensitive
    # -filesystem, and NFC/NFD normalization residuals. It requires a concurrent writer inside the repo,
    # who could equally just author the registry, so O_NOFOLLOW/fstat is deliberately NOT added; the
    # disclosure is the honest resolution.
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return ("absent", None)
    except OSError as exc:
        return ("bad", "the registry could not be stat'd ({})".format(exc))
    if not stat.S_ISREG(st.st_mode):
        return ("bad", "the registry is not a regular file (a symlink, FIFO, directory, ...); "
                       "a generated-artefact registry must be a regular file")
    try:
        # BINARY read so the size bound is on BYTES, not characters: read one byte past the cap, and if the
        # file exceeds the cap treat it as malformed (a SECA resource bound a multibyte-oversize file must
        # not slip through a char-count read). Decode is done explicitly below so a decode fault is BAD.
        with open(path, "rb") as handle:
            raw_bytes = handle.read(_GENSRC_MAX_BYTES + 1)
    except FileNotFoundError:
        # The lstat above saw a regular file, but it is gone at open: a concurrent DELETE race in the
        # lstat->open window. This is BAD (fail-safe ASK), never absent: absence is ONLY the lstat-probe
        # FileNotFoundError, so a benign delete race can never read as the inert no-coverage ALLOW.
        return ("bad", "the registry disappeared during the read (a concurrent change); failing safe")
    except OSError as exc:
        return ("bad", "the registry could not be read ({})".format(exc))
    if len(raw_bytes) > _GENSRC_MAX_BYTES:
        return ("bad", "the registry exceeds the {}-byte bound".format(_GENSRC_MAX_BYTES))
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return ("bad", "the registry is not valid UTF-8")
    try:
        obj = json.loads(raw)
    except ValueError:
        return ("bad", "the registry is malformed JSON")
    if not isinstance(obj, dict):
        return ("bad", "the registry is not a JSON object")
    version = obj.get("version")
    # type(version) is int, not `== _GENSRC_VERSION` alone: `True == 1` in Python, so a JSON bool version
    # (true) would else read as version 1. type(True) is bool, not int, so a bool (or a string "1", a
    # float) is rejected. A future version 2 also degrades to a fail-safe ask, never a misread of an
    # unknown shape.
    if type(version) is not int or version != _GENSRC_VERSION:
        return ("bad", "unknown registry version (expected {})".format(_GENSRC_VERSION))
    generated = obj.get("generated")
    if not isinstance(generated, list):
        return ("bad", "the registry carries no generated list")
    entries = []
    for item in generated:
        if not isinstance(item, dict):
            return ("bad", "a registry entry is not an object")
        kind = item.get("kind")
        target = item.get("target")
        sources = item.get("sources")
        regenerate = item.get("regenerate")
        if kind not in ("file", "tree", "block"):
            return ("bad", "a registry entry has an unknown kind")
        # target: a clean POSIX-relative path (no backslash, not absolute, no empty/'.'/'..' segment),
        # trailing '/' ONLY on a tree target (the tree marker); mirrors _canonical_target.
        if not isinstance(target, str) or not target or "\\" in target or _is_absolute(target):
            return ("bad", "a registry entry has a malformed target")
        # Reject a control character (any codepoint < 0x20, NUL included, or DEL 0x7f) in ANY target,
        # BEFORE the kind==block skip below, so a NUL-bearing block entry is BAD (ASK), never silently
        # dropped to zero entries and read as the inert no-coverage ALLOW.
        if any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in target):
            return ("bad", "a registry entry target contains a control character")
        has_trailing = target.endswith("/")
        body = target[:-1] if has_trailing else target
        if any(segment in ("", ".", "..") for segment in body.split("/")):
            return ("bad", "a registry entry has a malformed target")
        if has_trailing and kind != "tree":
            return ("bad", "a non-tree entry target must not end with '/'")
        if kind == "tree" and not has_trailing:
            return ("bad", "a tree entry target must end with '/'")
        if not isinstance(sources, list) or not sources or not all(
                isinstance(source, str) and source for source in sources):
            return ("bad", "a registry entry has malformed sources")
        if not isinstance(regenerate, str) or not regenerate:
            return ("bad", "a registry entry has a malformed regenerate command")
        if kind == "block":
            continue  # blocks are excluded from matching by design; the block drift gates backstop them
        entries.append((kind, target, sources, regenerate))
    return ("ok", entries)


_GENSRC_MATCH_FAULT = object()  # sentinel: a resolution/containment fault so no-match cannot be PROVEN


def _gensrc_within(candidate, parent):
    """A D2-LOCAL, ERROR-AWARE containment tri-state: "in" when the realpath of `candidate` is `parent`
    itself or lies under it (whole-component os.path.commonpath), "out" when it is proven outside, and
    "err" when the check FAULTS (a symlink loop, or commonpath given mixed or foreign inputs such as two
    Windows drive roots). DELIBERATELY NOT the shared _path_is_within, which errs to True (matched) so
    git_discard REFUSES to write recovery data inside a tree it cannot clear; here an unresolved
    containment must not read as a match NOR as a no-match ALLOW, so the fault surfaces as "err" and the
    caller fails safe to ask."""
    try:
        cand = os.path.realpath(candidate)
        base = os.path.realpath(parent)
        if cand == base or os.path.commonpath([cand, base]) == base:
            return "in"
        return "out"
    except (OSError, ValueError):
        return "err"


def _gensrc_match(entries, target, root_c):
    """The first registry entry that `target` (an already-realpath'd absolute path) matches, as
    (entry_target, sources, regenerate); None on a PROVEN no-match; or the _GENSRC_MATCH_FAULT sentinel
    when a resolution or containment fault means no-match cannot be proven (the handler turns the
    sentinel into a fail-safe ask, never a match and never a silent allow). A FILE entry matches on
    realpath EQUALITY; a TREE entry matches when `target` is the tree root or lies under it, by
    component-boundary containment (_gensrc_within), never a raw string prefix, so gen-extra/ never
    matches gen/ and GEN.md.bak never matches GEN.md. Each entry target is repo-root-relative, so it is
    joined onto root_c and canonicalized under try/except: an unresolvable entry is a fault, not a
    no-match. Block entries were dropped at load."""
    for kind, entry_target, sources, regenerate in entries:
        try:
            entry_c = os.path.realpath(os.path.join(root_c, entry_target))
        except (OSError, ValueError):
            return _GENSRC_MATCH_FAULT
        if kind == "file":
            if entry_c == target:
                return (entry_target, sources, regenerate)
        else:  # tree
            verdict = _gensrc_within(target, entry_c)
            if verdict == "err":
                return _GENSRC_MATCH_FAULT
            if verdict == "in":
                return (entry_target, sources, regenerate)
    return None


def gensrc_guard(data):
    """gensrc (integ/generated-artefact-source-only), PreToolUse on Write|Edit|MultiEdit: ASK before a
    Write/Edit/MultiEdit that hand-edits a generated artefact registered in the per-repo
    .aiqt/gensrc.json, read AT DECISION TIME. A REGISTRY-DRIVEN PATH guard, not a content judge: it
    fires only when the file_path resolves onto a kind=file or kind=tree registry entry. Coverage is
    exactly the registry, so an ABSENT registry is the inert ALLOW by design; kind=block entries are
    EXCLUDED (a path guard cannot see which lines an edit touches); Bash is EXCLUDED by design
    (regeneration itself runs through Bash), so the matcher is Write|Edit|MultiEdit only. The decision
    is an ASK, never a deny: the human approving the ask IS the opt-out, and where the drift gate is
    configured an approved hand-edit fails it until source and derivative reconcile. Every fail branch
    fails SAFE to ASK (see _gensrc_fail_ask); only a missing tool_name denies (the shared fail-closed
    contract). A malformed (empty/list/bool) tool_name, a control-char payload field, an unresolvable
    target, and a containment fault all ASK; only a None tool_name denies. The repo root
    is the git toplevel of the SESSION cwd via the scrubbed _recovery_toplevel primitive (NOT
    _gen_common.repo_root, which falls back to cwd and would fabricate a root)."""
    if data.get("hook_event_name") != PRETOOL:
        return _hard_block("aiqt_hooks: gensrc_guard wired to unexpected event {!r}; failing closed"
                           .format(data.get("hook_event_name")))
    tool_name = data.get("tool_name")
    if tool_name is None:
        return _deny_missing_tool_name("gensrc")  # the ONLY deny: a missing field cannot be matched
    if not isinstance(tool_name, str) or not tool_name:
        # A present-but-unreadable tool_name (an empty string, a list, a bool) cannot be matched against
        # the scope set; fail SAFE to ask rather than silently allow (only a MISSING tool_name denies).
        return _gensrc_fail_ask("the tool_name was unreadable")
    if tool_name not in _GENSRC_TOOLS:
        return _allow()  # out of scope (defensive; the matcher governs Write/Edit/MultiEdit)
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return _gensrc_fail_ask("the {} payload carried no readable tool_input".format(tool_name))
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return _gensrc_fail_ask("the {} payload carried no readable file_path".format(tool_name))
    # A control character (NUL included) in file_path is malformed input that would also raise inside
    # os.path.realpath ("embedded null byte"); reject it here so it fails SAFE to ask, never crashes.
    if any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in file_path):
        return _gensrc_fail_ask("the {} payload file_path contains a control character".format(tool_name))
    cwd = data.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return _gensrc_fail_ask("the payload carried no session cwd, so the repo root cannot be resolved")
    # The scrubbed rev-parse primitive (every ambient GIT_* removed), so an ambient decoy repo cannot
    # redirect the registry read; None means the cwd is outside any git work tree (a non-git session).
    root = _recovery_toplevel(cwd)
    if root is None:
        return _gensrc_fail_ask("the session cwd is outside any resolvable git work tree")
    status, payload = _load_gensrc_registry(root)
    if status == "absent":
        return _allow()  # the inert boundary: no registry, no coverage (adopters author their own)
    if status == "bad":
        return _gensrc_fail_ask("the .aiqt/gensrc.json registry could not be cleared ({})".format(payload))
    entries = payload
    if not entries:
        return _allow()  # a registry of only block entries has nothing this path guard can match
    # A relative file_path can only arrive via MultiEdit (abs-paths does not cover it); joining it onto
    # cwd matches the platform's own resolution. Canonicalize both to realpaths for the match; a
    # resolution fault (a symlink loop, an unresolvable path) is an unresolvable target -> fail SAFE to
    # ask, NOT an uncaught crash the dispatcher would turn into an exit-2 hard DENY.
    try:
        target = os.path.realpath(file_path if _is_absolute(file_path) else os.path.join(cwd, file_path))
        root_c = os.path.realpath(root)
    except (OSError, ValueError):
        return _gensrc_fail_ask("the target or repo root could not be resolved (an unresolvable path)")
    within = _gensrc_within(target, root_c)
    if within != "in":
        # "out" (proven outside) OR "err" (a containment fault) both fail safe: an uncleared target
        # cannot be judged against the registry of THIS repo, so it must never read as a silent allow.
        return _gensrc_fail_ask("the target canonicalizes outside the resolved repo, or the containment "
                                "check could not be cleared, so it cannot be judged against the registry "
                                "of this repo")
    match = _gensrc_match(entries, target, root_c)
    if match is _GENSRC_MATCH_FAULT:
        return _gensrc_fail_ask("a registry entry could not be resolved for containment, so a no-match "
                                "cannot be proven")
    if match is None:
        return _allow()  # not a registered generated artefact
    entry_target, sources, regenerate = match
    reason = ("AIQT rule gensrc (generated-artefact-source-only): {} is a generated artefact ({} in "
              ".aiqt/gensrc.json); it is changed only through its source. Edit {} and regenerate with "
              "'{}' instead. Approve only to deliberately hand-edit a generated artefact; where the drift "
              "gate is configured, it will fail until source and derivative are reconciled."
              .format(file_path, entry_target, ", ".join(sources), regenerate))
    banner = ("AIQT guardrail: asked before a {} to the generated artefact {} (rule gensrc): edit the "
              "source and regenerate ({}).".format(tool_name, entry_target, regenerate))
    return _ask(reason, banner)


# --- the orchestrator-integrity suite ----------------------------------------------------------
# One registry, one state directory, one PURE decision core (decide_yield), one delivery substrate; the
# six components are thin bindings over them. The whole suite is REGISTRY-SCOPED: with no
# .aiqt/orchestration.local.json or .aiqt/orchestration.json at the session repo root it is inert (the
# gensrc.json precedent), and the backlog guards additionally require a live orchestrator lease or a
# declared mode record, so bounded workers and plain sessions never inherit the global backlog. The
# stop path fails OPEN on a guard's own error (which can never wedge a session) but DENIES on a backlog
# cannot-evaluate (ignorance refuses the wind-down); the schedule path fails CLOSED on
# cannot-evaluate (a denied tool call cannot wedge anything), bounded by a denial cap. See
# .aiqt/core/hooks/ORCHESTRATION.md for the registry schema and the AEI v1 protocol.

_ORCH_REGISTRY_FILES = (".aiqt/orchestration.local.json", ".aiqt/orchestration.json")
_ORCH_BLOCKER_KINDS = frozenset(
    ("tracked-task", "human-decision", "external", "foreign-lease", "not-before"))
_ORCH_STATES = frozenset(("open", "closed", "proposed"))
_ORCH_LOOP_BOUND = 2          # stop-path denies per epoch before ALLOW_WITH_FINDINGS
_ORCH_SCHEDULE_CAP = 3        # schedule-path denies on an unchanged basis before findings
_ORCH_MAX_NAMED = 10          # actionable items named in a deny message
_ORCH_MODE_RE = re.compile(r"^Operating-mode:\s*(.+?)\s*$", re.MULTILINE)
_ORCH_ESCAPE_NAME = "ESCAPE-ALLOW-YIELD"
_ORCH_QUIET_CLAIM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*min(?:ute)?s?\b")  # minutes number; the "quiet" gate is applied separately
# A human-decision blocker ref must look like a decision id (uppercase-prefixed, for example XY-12),
# never a bare lowercase word or a session-id substring, so a common word present in the pending
# surface cannot forge a human-decision block. Mirrors the record-drift typed-ref discipline.
_ORCH_DECISION_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-[A-Z0-9][A-Za-z0-9-]*$")
_ORCH_CLOCK_SKEW = 300  # seconds of tolerance for a proof timestamp slightly ahead of the guard clock
_ORCH_ATTEST_APPROVED = frozenset(("accepted", "landed"))  # FIX 3: a ref counts only from an approved row


def _orch_now():
    """The clock-read UTC now (tstamp: a recorded timestamp is read from the clock, never recalled)."""
    return datetime.datetime.now(datetime.timezone.utc)


def _orch_parse_utc(text):
    """Parse an ISO-8601 UTC string tolerantly ('Z' accepted); None on anything unparseable, so an
    unreadable timestamp can never satisfy a freshness check."""
    if not isinstance(text, str) or not text:
        return None
    try:
        value = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value


def _orch_sha256_hex(text):
    """The sha256 hex of a single register line's bytes (the tip identity a chained register anchors)."""
    return __import__("hashlib").sha256(text.encode("utf-8")).hexdigest()


def _orch_root(data):
    """The session repo root via the scrubbed rev-parse primitive, or None (out of scope)."""
    cwd = data.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    return _recovery_toplevel(cwd)


def _orch_registry(root):
    """Load the orchestration registry: ('absent', None) only when a registry file is genuinely NOT PRESENT
    (a clean lstat FileNotFoundError; the suite is inert by design), ('ok', dict) on a schema-valid
    registry, ('bad', detail) otherwise. A present-but-unreadable registry is a cannot-evaluate returned as
    bad, never absent: an lstat FAULT (a permission or I/O error), a read/parse error, or a non-version-1
    object all fail closed rather than silently disarming a caller that locates confinement through it. The
    machine-local .aiqt/orchestration.local.json takes WHOLE-FILE precedence over the committed
    .aiqt/orchestration.json; there is no merge, so precedence is never ambiguous."""
    for rel in _ORCH_REGISTRY_FILES:
        path = os.path.join(root, *rel.split("/"))
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue                     # genuinely not present: try the next registry file
        except OSError as exc:
            # An lstat FAULT (e.g. a permission error) is a cannot-evaluate, NOT absence: os.path.lexists
            # would have swallowed it to False and read a present-but-unreadable registry as absent, falling
            # back to XDG and disarming confinement. Surface it as bad so it denies instead.
            return ("bad", "{}: cannot stat registry path ({}); a cannot-evaluate denies rather than "
                           "disarming confinement".format(rel, exc))
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            return ("bad", "{}: {}".format(rel, exc))
        if not isinstance(data, dict) or type(data.get("version")) is not int \
                or data.get("version") != 1:
            return ("bad", "{}: not a version-1 registry object".format(rel))
        return ("ok", data)
    return ("absent", None)


def _orch_path(root, value):
    """Resolve a registry-declared path: absolute kept, relative joined onto the repo root; None for
    a non-string or empty value."""
    if not isinstance(value, str) or not value:
        return None
    return value if os.path.isabs(value) else os.path.join(root, value)


def _state_dir_from_registry(root, reg_data):
    """Resolve the machine-written state directory for root from an ALREADY-READ registry dict (or None for
    an absent registry, or an ok registry that declares no usable state_dir): the registry's state_dir when
    it declares a usable one, else ${XDG_STATE_HOME:-$HOME/.local/state}/aiqt-guardrails/orch/<repo-key>/.
    PURE: it performs NO registry read of its own, so a caller that has already validated the registry passes
    that result here and never triggers a second, independently-faulting read (the TOCTOU fail-open where a
    second EACCES silently downgrades a confined session to the XDG default)."""
    declared = _orch_path(root, (reg_data or {}).get("state_dir"))
    if declared:
        return declared
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"),
                                                            ".local", "state")
    key = __import__("hashlib").sha256(root.encode("utf-8", "replace")).hexdigest()[:16]
    return os.path.join(base, "aiqt-guardrails", "orch", key)


def _orch_state_dir_for_root(root):
    """The machine-written state directory for a repo root: the registry's state_dir when declared, else
    ${XDG_STATE_HOME:-$HOME/.local/state}/aiqt-guardrails/orch/<repo-key>/. Reads the registry ONCE and
    delegates the resolution to the pure _state_dir_from_registry helper (a single read per call)."""
    status, reg = _orch_registry(root)
    return _state_dir_from_registry(root, reg if status == "ok" else None)


def _orch_append_jsonl(path, obj):
    """Best-effort JSONL append (parents created). Returns True on success; the CALLER decides what a
    failed write means (a recorder surfaces it; a guard never changes its decision over it)."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, sort_keys=True) + "\n")
        return True
    except (OSError, ValueError):
        return False


def _orch_read_jsonl(path):
    """Read a JSONL file: (rows, bad_line_count), or (None, 0) when the file is absent or unreadable,
    so a caller can distinguish nothing-recorded from cannot-read (chkfcl)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        return ([], 0)
    except (OSError, ValueError):
        return (None, 0)
    rows, bad = [], 0
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            bad += 1  # valid JSON but not an object (null/list/number): malformed, never coerced to {}
    return (rows, bad)


def _orch_write_json(path, obj):
    """Best-effort JSON overwrite (parents created). Returns True on success; the CALLER decides what
    a failed write means (a recorder surfaces it; a guard never changes its decision over it)."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, sort_keys=True)
        return True
    except (OSError, ValueError):
        return False


def _orch_write_json_atomic(path, obj):
    """Crash-safe JSON overwrite: write a sibling temp then os.replace (an atomic rename on the same
    filesystem), so a crash mid-write never leaves a truncated file a reader would treat as malformed.
    Same best-effort contract as _orch_write_json (returns True on success; the caller decides what a
    failure means)."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, sort_keys=True)
        os.replace(tmp, path)
        return True
    except (OSError, ValueError):
        return False


def _orch_guard_event(root, kind, decision, detail):
    """Best-effort append of one guard-events row (the over-fire metric and the mistakes-register feed).
    Returns whether the append succeeded (False on an I/O failure); the caller decides what a failure means
    and a guard never changes its decision over it."""
    sd = _orch_state_dir_for_root(root)
    return _orch_append_jsonl(os.path.join(sd, "guard-events.jsonl"),
                              {"ts": _orch_now().isoformat(), "kind": kind,
                               "decision": decision, "detail": detail})


def _orch_turn_state(root):
    """The turn-state dict, or None on an unreadable/malformed file (the loop guard treats None as
    bound-reached, the fail-open direction: an unreadable counter can never license unbounded denies)."""
    path = os.path.join(_orch_state_dir_for_root(root), "turn-state.json")
    try:
        if not os.path.lexists(path):
            return {}
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _orch_save_turn_state(root, state):
    sd = _orch_state_dir_for_root(root)
    try:
        os.makedirs(sd, exist_ok=True)
        with open(os.path.join(sd, "turn-state.json"), "w", encoding="utf-8") as fh:
            json.dump(state, fh, sort_keys=True)
        return True
    except (OSError, ValueError):
        return False


def _orch_mode(reg, root):
    """The lowercased Operating-mode value from the declared mode record, or None (undeclared,
    unreadable, or no mode line): the fail-open answer for the ask blocker."""
    path = _orch_path(root, (reg.get("mode") or {}).get("path") if isinstance(
        reg.get("mode"), dict) else None)
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    m = _ORCH_MODE_RE.search(text)
    return m.group(1).lower() if m else None


def _orch_scope_live(reg, root, session_id=None):
    """The D11 scope check: True when a declared orchestrator lease file is live (present, non-empty,
    within max_age_hours when declared) OR a declared mode record carries a mode line. When the lease
    declares holder_is_session_id AND the caller's session_id is known, a LIVE lease must additionally
    NAME that session_id, so a co-located NON-holder session (a bounded worker) does not inherit the
    global backlog (CX-M3). Where the lease records no comparable session identity, scope is repo-coarse
    (a co-located session may inherit the backlog): a disclosed residual, not a strict boundary."""
    lease = reg.get("lease") if isinstance(reg.get("lease"), dict) else None
    if lease:
        path = _orch_path(root, lease.get("path"))
        if path:
            try:
                st = os.stat(path)
                fresh = True
                max_age = lease.get("max_age_hours")
                if isinstance(max_age, (int, float)) and max_age > 0:
                    age = _orch_now().timestamp() - st.st_mtime
                    # a future mtime (age below -skew) is anomalous (clock skew or tamper) and never reads
                    # as fresh forever; a small future skew is tolerated (CX future-mtime finding).
                    fresh = -_ORCH_CLOCK_SKEW <= age <= max_age * 3600
                if st.st_size > 0 and fresh:
                    if lease.get("holder_is_session_id"):
                        # STRICT opt-in holder scoping: the caller must carry a session id AND the lease
                        # must be readable AND name that id as a whole token; anything else is a NON-holder
                        # (a co-located worker or an id-less session never inherits the global backlog).
                        if not (isinstance(session_id, str) and session_id):
                            return False
                        try:
                            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                                held = fh.read()
                        except OSError:
                            return False
                        return _orch_token_present(session_id, held)
                    return True
            except OSError:
                if lease.get("holder_is_session_id"):
                    return False  # holder mode: an unreadable lease -> caller cannot be confirmed holder
                # otherwise an absent/unreadable lease is not live; fall through to the mode check
    return _orch_mode(reg, root) is not None


def _orch_escape_stat(path):
    """The C.1 stat seam: bind the final-component stat to an O_NOFOLLOW-opened descriptor
    (os.open O_RDONLY|O_NOFOLLOW|O_NONBLOCK then os.fstat), or None on any OSError. FIX B: O_NONBLOCK
    keeps a FIFO sentinel with no writer from blocking the open (which would hang the guard); the
    S_ISREG check below then rejects the FIFO. Binding the stat to the opened
    inode rather than a pathname lstat means a name swap AFTER a pathname check cannot redirect the
    validation onto a different inode (a best-effort race narrowing; see _orch_escape_active for the
    disclosed residual). A one-line helper so the self-test can exercise the different-uid honour,
    hardlink, and writable legs hermetically on a single-uid host, where a real file owned by another
    uid (or with a fabricated link count) cannot be created."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW
                     | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
    except OSError:
        return None
    try:
        return os.fstat(fd)
    finally:
        os.close(fd)


def _orch_escape_active(reg, root):
    """C.1: the escape sentinel opens the clean-ALLOW channel only when it is demonstrably an
    operator-created artefact in a trusted place, NOT the assistant's own: a REGULAR file with a single
    hard link (st_nlink == 1), reached without following any symlinked path component, resolved under
    the operator-trusted anchor (the machine-written state dir), owned by a uid other than this guard's
    effective uid, and not group- or other-writable. Returns (active, spoof_detail): a present sentinel
    failing any condition reads INACTIVE with the failed condition as the detail, so the decision
    proceeds exactly as with no sentinel (no new deny anywhere) and the bindings can record the spoof.
    An absent or unstattable path is (False, None).

    FIX 2 raises the bar against the naming/link vectors: an absolute FOREIGN path (e.g. /etc/passwd or
    /proc/self/root/...), a '..' traversal, a symlinked path component, or a hard link no longer opens
    the channel. Residuals (disclosed in ORCHESTRATION.md): the trusted anchor is the machine-written
    state dir, which is itself actor-writable, so an actor with raw filesystem write access remains the
    CATEGORICAL residual (closed only by an operator-owned, assistant-non-writable state dir at the OS
    layer); component resolution is a best-effort lstat walk under the anchor rather than a fully
    race-free openat-under-anchor (a narrow TOCTOU window between the walk and the O_NOFOLLOW open); and
    uid inequality proves not-self, never operator identity."""
    anchor = os.path.realpath(_orch_state_dir_for_root(root))
    declared = (reg.get("escape") or {}).get("path") if isinstance(reg.get("escape"), dict) else None
    if declared is not None and (not isinstance(declared, str) or not declared):
        return (False, None)
    if declared:
        raw = declared if os.path.isabs(declared) else os.path.join(anchor, declared)
    else:
        raw = os.path.join(anchor, _ORCH_ESCAPE_NAME)
    if os.pardir in raw.split(os.sep):
        return (False, "escape sentinel path contains '..' (rejected)")
    norm = os.path.normpath(raw)
    if not (norm == anchor or norm.startswith(anchor.rstrip(os.sep) + os.sep)):
        return (False, "escape sentinel path is outside the operator-trusted anchor (rejected)")
    # refuse to follow a symlinked component from the anchor down to (not including) the final name
    rel = os.path.relpath(norm, anchor)
    parts = [] if rel in ("", os.curdir) else rel.split(os.sep)
    cur = anchor
    for comp in parts[:-1]:
        cur = os.path.join(cur, comp)
        try:
            if stat.S_ISLNK(os.lstat(cur).st_mode):
                return (False, "escape sentinel has a symlinked path component (rejected)")
        except OSError:
            return (False, None)  # a missing intermediate directory is simply no sentinel
    # a symlink AT the final name is a spoof: classify via lstat so it surfaces a detail (the seam's
    # O_NOFOLLOW open would otherwise report it only as an unopenable None)
    try:
        if stat.S_ISLNK(os.lstat(norm).st_mode):
            return (False, "escape sentinel is a symlink (not followed; ignored)")
    except OSError:
        pass  # absent on disk here: the seam is authoritative (and may be injected under test)
    st = _orch_escape_stat(norm)
    if st is None:
        return (False, None)
    if not stat.S_ISREG(st.st_mode):
        return (False, "escape sentinel is not a regular file (symlink or special file; ignored)")
    if st.st_nlink != 1:
        return (False, "escape sentinel has more than one hard link (ignored)")
    if st.st_uid == os.geteuid():
        return (False, "escape sentinel is owned by the assistant's own effective uid (ignored)")
    if st.st_mode & 0o022:
        return (False, "escape sentinel is group- or other-writable (ignored)")
    return (True, None)


def validate_enumeration(obj):
    """AEI v1 strict validation: (items, None) on a valid enumeration, (None, detail) otherwise. A
    duplicate id, a malformed item or field, an unknown version, a missing envelope, or a non-dict
    payload is an error, never an empty backlog (grdinp: a parse failure is a distinct cannot-evaluate,
    not a clean pass)."""
    if not isinstance(obj, dict):
        return (None, "payload is not a JSON object")
    version = obj.get("version")
    if type(version) is not int or version != 1:
        return (None, "unknown AEI version {!r} (an exact integer 1 is required)".format(version))
    gen = obj.get("generated_at_utc")
    gen_ts = _orch_parse_utc(gen) if isinstance(gen, str) else None
    if gen_ts is None:
        return (None, "missing or unparseable generated_at_utc")
    if (gen_ts - _orch_now()).total_seconds() > _ORCH_CLOCK_SKEW:
        return (None, "generated_at_utc is in the future")
    source = obj.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("locator"), str) \
            or not source.get("locator").strip():
        return (None, "missing or malformed source (a non-blank locator is required)")
    items = obj.get("items")
    if not isinstance(items, list):
        return (None, "items is not a list")
    seen, out = set(), []
    for raw in items:
        if not isinstance(raw, dict):
            return (None, "an item is not an object")
        iid = raw.get("id")
        if not isinstance(iid, str) or not iid:
            return (None, "an item has no string id")
        if iid in seen:
            return (None, "duplicate item id {!r}".format(iid))
        seen.add(iid)
        title = raw.get("title")
        if title is not None and not isinstance(title, str):
            return (None, "item {} has a non-string title".format(iid))
        state = raw.get("state")
        if state not in _ORCH_STATES:
            return (None, "item {} has invalid state {!r}".format(iid, state))
        granted = raw.get("granted")
        if not isinstance(granted, bool):
            return (None, "item {} has a non-boolean granted".format(iid))
        blocker = raw.get("blocker")
        if blocker is not None:
            if not isinstance(blocker, dict) or blocker.get("kind") not in _ORCH_BLOCKER_KINDS \
                    or not isinstance(blocker.get("ref"), str) or not blocker.get("ref").strip():
                return (None, "item {} has a malformed blocker".format(iid))
            ev = blocker.get("evidence")
            obs = blocker.get("observed_at_utc")
            if (ev is not None and not isinstance(ev, str)) \
                    or (obs is not None and not isinstance(obs, str)):
                return (None, "item {} has a malformed blocker field (evidence/observed_at_utc)"
                        .format(iid))
        out.append({"id": iid, "title": title if isinstance(title, str) and title else iid,
                    "state": state, "granted": granted, "blocker": blocker})
    return (out, None)


def _orch_enumerate(reg, root):
    """Run the registry enumerator: ('ok', items) or (status, detail) where status is NO_ENUMERATOR or
    ENUMERATOR_ERROR. The enumeration is always FRESH (never a list or a 'drained' claim from the
    agent's context), via the fixed argv array the registry declares (no shell string)."""
    spec = reg.get("enumerator")
    if not isinstance(spec, dict):
        return ("NO_ENUMERATOR", "the registry declares no enumerator")
    argv = spec.get("argv")
    if not isinstance(argv, list) or not argv or not all(
            isinstance(a, str) and a for a in argv):
        return ("ENUMERATOR_ERROR", "enumerator argv is not a list of non-empty strings")
    timeout = spec.get("timeout")
    timeout = timeout if isinstance(timeout, (int, float)) and 0 < timeout <= 600 else 60
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=root)
    except (OSError, subprocess.SubprocessError) as exc:
        return ("ENUMERATOR_ERROR", "enumerator failed to run: {}".format(exc))
    if result.returncode != 0:
        return ("ENUMERATOR_ERROR",
                "enumerator exit {}: {}".format(result.returncode, (result.stderr or "")[:200]))
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        return ("ENUMERATOR_ERROR", "enumerator output is not JSON: {}".format(exc))
    items, err = validate_enumeration(payload)
    if err:
        return ("ENUMERATOR_ERROR", err)
    return ("ok", items)


def _orch_live_ledger_ids(root, task_hours):
    """Task ids that are LIVE: the LAST ledger event for the id is a launch (relaunch after a completion
    counts as live again), the wake route is EXACTLY True (a non-bool truthy like "false" does not count),
    and the launch age is within the staleness horizon and not in the future beyond a small skew tolerance.
    Returns (live_set, readable, detail): readable is False when the ledger is unreadable OR carries any
    malformed line (a cannot-evaluate the caller must NOT treat as 'no live task')."""
    rows, bad = _orch_read_jsonl(os.path.join(_orch_state_dir_for_root(root),
                                              "dispatch-ledger.jsonl"))
    if rows is None:
        return (set(), False, "dispatch ledger unreadable")
    now = _orch_now()
    last = {}
    schema_bad = 0
    for row in rows:
        event = row.get("event")
        if event not in ("launch", "complete"):
            continue  # a row for neither event is not a ledger record: ignored, not counted malformed
        # a launch/complete row MUST carry a str task_id and a str ts; a launch MUST carry a bool wake.
        # A schema-invalid dict row (e.g. a launch missing ts) is MALFORMED, not a silently-ignored row,
        # so a tracked item cannot be demoted to actionable by a half-written record (CX-R4-1).
        if not isinstance(row.get("task_id"), str) or _orch_parse_utc(row.get("ts")) is None \
                or (event == "launch" and not isinstance(row.get("wake"), bool)):
            schema_bad += 1  # ts must PARSE, not merely be a string (a 'banana' ts is malformed, CX-R5-2)
            continue
        last[row["task_id"]] = row  # file order: the LAST valid event per tid wins (relaunch = live)
    live = set()
    for tid, row in last.items():
        if row.get("event") != "launch" or row.get("wake") is not True:
            continue
        ts = _orch_parse_utc(row.get("ts"))
        if ts is not None and -_ORCH_CLOCK_SKEW <= (now - ts).total_seconds() <= task_hours * 3600:
            live.add(tid)
    # an unparseable OR schema-invalid line means some rows could not be trusted: report readable=False so
    # the caller HOLDS the item as cannot-evaluate (never read as 'no live task'); FIX 1 then DENIES the
    # stop on it below the loop bound (ignorance refuses the wind-down), the operator escape releasing it.
    readable = bad == 0 and schema_bad == 0
    detail = "{} malformed ledger line(s) skipped".format(bad) if bad else ""
    return (live, readable, detail)


def _orch_pending_haystack(reg, root):
    """The human-decision proof surface: the DECLARED pending-decisions record ONLY. The machine-written
    pending-asks keys are NOT decision rows and are excluded (an ask key session::tool_use could otherwise
    forge a row via the id-colon match, CX-R4-2). Returns None when no surface is declared or it is
    unreadable, so an undeclared/unreadable surface HOLDS a human-decision item (cannot-evaluate) rather
    than demoting it to a definite actionable; FIX 1 DENIES the stop on that cannot-evaluate below the loop
    bound (ignorance refuses the wind-down), the operator escape releasing a genuine block."""
    rec = reg.get("record") if isinstance(reg.get("record"), dict) else {}
    declared = _orch_path(root, rec.get("pending_decisions"))
    if not declared:
        return None
    try:
        with open(declared, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _orch_attestation_refs(reg, root, staleness):
    """The C.2 attestation proof surface. Three-valued, matching the proof-source idiom: None when the
    registry declares no attestations register; "unreadable" when one is declared but the validated
    snapshot is absent, malformed, not a status-ok run, stale, its binding to the register on disk no
    longer verifies, or (FIX A1) the bound register no longer reads as a clean chain (held, never
    blocked or actionable); else the frozenset of blocker refs RE-DERIVED from the register content.
    The re-anchor (FIX 3) defends the register-SWAP and snapshot-STALENESS classes only: the reader
    re-reads the register, recomputes its append-only authority (git merge-base or <path>.anchor), and
    confirms the snapshot is bound to that same register path + anchored seq + tip digest, so a
    register swapped or a snapshot gone stale between audit and yield HOLDS. FIX A1: the snapshot's
    stored 'refs' field is non-authoritative; the reader re-derives the substantiated refs from the
    re-anchored register content itself (the shared _orch_attestation_derive), so a snapshot forged
    with fabricated refs substantiates none of them. This RAISES THE BAR over free-text evidence but
    is NOT categorically forgery-proof: an actor with filesystem write to the state-dir can still
    forge an attestation by APPENDING a valid approved row (uncommitted; A2 residual), which this
    derivation substantiates. The categorical closure is an operator-owned, assistant-non-writable
    register at the OS layer (SYSTEM-HARDENING.md entry 2). A pre-binding (v1) snapshot lacks the
    binding fields and so fails closed to HOLD (safe migration)."""
    at_path = _orch_path(root, reg.get("attestations"))
    if not at_path:
        return None
    path = os.path.join(_orch_state_dir_for_root(root), "attestations-validated.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            snap = json.load(fh)
    except (OSError, ValueError):
        return "unreadable"
    if not isinstance(snap, dict) or snap.get("status") != "ok" \
            or not isinstance(snap.get("refs"), list):
        return "unreadable"
    generated = _orch_parse_utc(snap.get("ts"))
    age = (_orch_now() - generated).total_seconds() if generated is not None else None
    ext_hours = _orch_validate("staleness", staleness)[1]["external_hours"]
    if age is None or not (-_ORCH_CLOCK_SKEW <= age <= ext_hours * 3600):
        return "unreadable"
    # FIX 3: re-bind the snapshot to the register on disk (re-read + re-anchor).
    astatus, aseq, adigest = _orch_register_authority(root, at_path)
    if astatus != "ok" or snap.get("register") != os.path.realpath(at_path) \
            or snap.get("seq") != aseq or snap.get("digest") != adigest:
        return "unreadable"
    # FIX A1: the snapshot's own 'refs' field is NOT authoritative. Re-derive the substantiated refs
    # from the re-anchored register content itself (the same audit derivation), so a snapshot forged
    # with fabricated refs but bound to the real tip substantiates none of them.
    rows, _detail = _orch_chained_rows(at_path, "AT-")
    if rows is None:
        return "unreadable"
    refs, _unsub, _findings = _orch_attestation_derive(reg, root,
                                                       _orch_state_dir_for_root(root), rows)
    return frozenset(refs)


def classify_backlog(items, live_ids, ledger_readable, pending_haystack, staleness,
                     attestations=None):
    """Pure classification of a VALID enumeration (step 5). Returns actionable/waiting/blocked/
    cannot_evaluate/proposed. A proof SOURCE that cannot be read (ledger unreadable-or-malformed, or
    pending_haystack is None) puts the item in cannot_evaluate: FIX 1 DENIES the stop on it (ignorance
    refuses the wind-down) and the schedule path DENIES on it too (missing evidence never licenses an idle).
    attestations is the C.2 tri-state from _orch_attestation_refs: None (no register declared) keeps
    the free-text external/foreign-lease evidence path byte-identical; "unreadable" (declared but the
    validated snapshot is absent, stale, or malformed) HOLDS such an item (cannot-evaluate), never
    blocked or actionable; a validated ref-set classifies blocked only when the blocker's ref is
    covered by a fresh validated row, the existing observed_at_utc freshness check still applying."""
    now = _orch_now()
    ext_hours = _orch_validate("staleness", staleness)[1]["external_hours"]
    out = {"actionable": [], "waiting": [], "blocked": [], "cannot_evaluate": [], "proposed": []}
    for it in items:
        if it["state"] == "closed":
            continue
        if it["state"] == "proposed" or not it["granted"]:
            out["proposed"].append(it["id"])
            continue
        blocker = it["blocker"]
        if not blocker:
            out["actionable"].append((it["id"], it["title"], "no blocker recorded"))
            continue
        kind, ref = blocker["kind"], blocker["ref"]
        if kind == "tracked-task":
            if not ledger_readable:
                # readable checked FIRST: a partially-malformed ledger cannot be trusted even for an id
                # that happens to appear live in a good row (CX-R5-1), so the item is HELD.
                out["cannot_evaluate"].append((it["id"], "cannot-evaluate",
                                               "ledger unreadable/malformed; held"))
            elif ref in live_ids:
                out["waiting"].append((it["id"], "tracked-task", ref))
            else:
                out["actionable"].append((it["id"], it["title"],
                                          "tracked-task ref {} resolves to no live ledger row"
                                          .format(ref)))
        elif kind == "human-decision":
            if pending_haystack is None:
                out["cannot_evaluate"].append((it["id"], "cannot-evaluate",
                                               "pending surface unreadable; held"))
            elif not _ORCH_DECISION_ID_RE.match(ref):
                out["actionable"].append((it["id"], it["title"],
                                          "human-decision ref {!r} is not a decision id".format(ref)))
            elif re.search(r"(?m)^[ \t]*(?:\|[ \t]*{0}[ \t]*\||{0}[ \t]*:)".format(re.escape(ref)),
                           pending_haystack):
                out["blocked"].append((it["id"], "human-decision", ref))
            else:
                out["actionable"].append((it["id"], it["title"],
                                          "ref {} is not at a pending-decision row-id position".format(ref)))
        elif kind in ("external", "foreign-lease"):
            observed = _orch_parse_utc(blocker.get("observed_at_utc"))
            age = (now - observed).total_seconds() if observed is not None else None
            fresh = age is not None and -_ORCH_CLOCK_SKEW <= age <= ext_hours * 3600
            if attestations == "unreadable":
                # C.2: a DECLARED attestation surface that cannot be read HOLDS the item, a distinct
                # cannot-evaluate: never blocked (a forgeable block) and never actionable (a false
                # deny). FIX 1 DENIES the stop and the schedule path denies bounded by the cap.
                out["cannot_evaluate"].append((it["id"], "cannot-evaluate",
                                               "attestation surface unreadable; held"))
            elif attestations is not None and ref not in attestations:
                out["actionable"].append((it["id"], it["title"],
                                          "{} blocker ref {} is covered by no fresh validated "
                                          "attestation".format(kind, ref)))
            elif (blocker.get("evidence") or "").strip() and fresh:
                out["blocked"].append((it["id"], kind, ref))
            else:
                out["actionable"].append((it["id"], it["title"],
                                          "{} blocker has no fresh (non-future) evidence".format(kind)))
        elif kind == "not-before":
            when = _orch_parse_utc(ref)
            if when is not None and now < when:
                out["blocked"].append((it["id"], "not-before", ref))
            else:
                out["actionable"].append((it["id"], it["title"],
                                          "not-before constraint unparseable or already met"))
    return out


def decide_yield(ctx):
    """The PURE decision core. ctx keys: kind, escape, loop_signal, counter, enum_status, enum_detail,
    actionable, waiting, blocked, cannot_evaluate, proposed, wake_named, schedule_denials, basis_unchanged.
    Returns (verdict, reason, disposition) with verdict ALLOW | ALLOW_WITH_FINDINGS | DENY."""
    kind = ctx["kind"]
    disposition = ([("blocked", i, c, p) for i, c, p in ctx["blocked"]]
                   + [("cannot_evaluate", i, c, p) for i, c, p in ctx.get("cannot_evaluate", [])]
                   + [("waiting", i, c, p) for i, c, p in ctx["waiting"]]
                   + [("actionable", i, t, w) for i, t, w in ctx["actionable"]]
                   + [("proposed", i, "", "") for i in ctx["proposed"]])
    if ctx["escape"]:
        return ("ALLOW", "operator escape artefact present (logged)", disposition)
    if kind != "schedule_idle" and (ctx["counter"] >= _ORCH_LOOP_BOUND or ctx["loop_signal"]):
        return ("ALLOW_WITH_FINDINGS",
                "loop bound reached after {} denial(s); yielding with the unresolved items as "
                "findings rather than re-firing".format(ctx["counter"]), disposition)
    if ctx["enum_status"] != "ok":
        if kind == "schedule_idle":
            if ctx["schedule_denials"] >= _ORCH_SCHEDULE_CAP and ctx["basis_unchanged"]:
                return ("ALLOW_WITH_FINDINGS",
                        "{} schedule denials on an unchanged basis; a guard that can be farmed "
                        "trains its own bypass, so this yield proceeds with findings"
                        .format(ctx["schedule_denials"]), disposition)
            return ("DENY",
                    "the backlog is not enumerable ({}: {}); missing evidence never licenses a new "
                    "idle or wake. Fix the enumerator or the registry, or release through the "
                    "operator-owned escape sentinel".format(ctx["enum_status"],
                                                            ctx["enum_detail"]), disposition)
        return ("DENY",
                "cntdef: the backlog is not enumerable ({}: {}); an unconfirmable enumeration cannot "
                "confirm whole-set exhaustion, so it cannot license a stop (ignorance refuses the "
                "wind-down). Fix the enumerator or the registry; the operator-owned escape sentinel is "
                "the release for a genuine block".format(
                    ctx["enum_status"], ctx["enum_detail"]), disposition)
    # ITEM-LEVEL cannot-evaluate (an unreadable proof source for a specific item) is missing evidence: the
    # schedule path DENIES (never licenses an idle), and (FIX 1) the stop path DENIES too, because an
    # unconfirmable blocker cannot confirm exhaustion (ignorance refuses the wind-down); the operator
    # escape is the release.
    if ctx.get("cannot_evaluate", []) and kind == "schedule_idle":
        if ctx["schedule_denials"] >= _ORCH_SCHEDULE_CAP and ctx["basis_unchanged"]:
            return ("ALLOW_WITH_FINDINGS",
                    "{} schedule denials on an unchanged basis; yielding with findings"
                    .format(ctx["schedule_denials"]), disposition)
        return ("DENY",
                "a proof source for {} open item(s) is unreadable (cannot-evaluate); missing evidence "
                "never licenses a new idle or wake. Fix the source, or release through the "
                "operator-owned escape sentinel.".format(len(ctx.get("cannot_evaluate", []))), disposition)
    if not ctx["actionable"]:
        rechecked = ctx["waiting"] + ctx["blocked"]
        if kind == "schedule_idle" and rechecked and ctx["wake_named"] is False:
            if ctx["schedule_denials"] >= _ORCH_SCHEDULE_CAP and ctx["basis_unchanged"]:
                # anti-farming: wake-hygiene denials are cap-relieved like every other schedule DENY, so
                # a repeated unnamed idle on an unchanged basis yields with findings rather than forever.
                return ("ALLOW_WITH_FINDINGS",
                        "{} schedule denials on an unchanged basis; yielding with findings"
                        .format(ctx["schedule_denials"]), disposition)
            return ("DENY",
                    "wake hygiene: a permitted idle must name the item or blocker it will recheck; "
                    "pending: {}".format(
                        ", ".join(i for i, _c, _p in rechecked[:_ORCH_MAX_NAMED])), disposition)
        if ctx.get("cannot_evaluate", []):
            return ("DENY",
                    "cntdef: {} open item(s) have an unreadable proof source (cannot-evaluate); an "
                    "unconfirmable blocker cannot license a stop (ignorance refuses the wind-down). "
                    "Fix the source; the operator-owned escape sentinel is the release for a genuine "
                    "block.".format(len(ctx.get("cannot_evaluate", []))), disposition)
        return ("ALLOW", "no actionable item remains; the disposition table is the enumeration",
                disposition)
    if kind == "schedule_idle" and ctx["schedule_denials"] >= _ORCH_SCHEDULE_CAP \
            and ctx["basis_unchanged"]:
        return ("ALLOW_WITH_FINDINGS",
                "{} schedule denials on an unchanged basis; yielding with findings"
                .format(ctx["schedule_denials"]), disposition)
    named = ctx["actionable"][:_ORCH_MAX_NAMED]
    more = len(ctx["actionable"]) - len(named)
    listing = "; ".join("{} ({}: {})".format(i, t, w) for i, t, w in named)
    if more > 0:
        listing += "; and {} more".format(more)
    return ("DENY",
            "AIQT rules setcmp/cntdef: {} granted open item(s) are actionable: {}. Two legal exits: "
            "do one of them, or record a proven blocker on each (a live tracked-task ref, a matching "
            "pending-decision row, fresh external evidence, or a not-before time). A fired timer or "
            "an existing cron is neither.".format(len(ctx["actionable"]), listing), disposition)


_ORCH_MAX_HORIZON_HOURS = 8760   # a staleness horizon beyond one year is out of range
_ORCH_COUNTER_MAX = 9999         # a denial counter beyond this is out of range (domain sanity)


def _v_exact_int(value, lo, hi):
    """An exact int in [lo, hi], else None (bool is rejected: True/False are not counts)."""
    return value if type(value) is int and lo <= value <= hi else None


def _v_finite_pos(value, hi):
    """A finite number in (0, hi], else None (bool, NaN, and Infinity are rejected)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or value <= 0 or value > hi:
        return None
    return value


def _orch_validate(boundary, raw):
    """The single validation membrane for a decision-input trust boundary. Returns ('ok', typed) with
    the boundary's fields validated (an invalid field is None where the caller applies the fail-safe
    direction, or already defaulted where the safe value is a default), or ('cannot-evaluate', detail)
    for an unregistered boundary. Every decision input is registered in _ORCH_SCHEMAS, so a new field
    cannot be read without a schema, and the validation-coverage gate holds the readers to this entry."""
    schema = _ORCH_SCHEMAS.get(boundary)
    if schema is None:
        return ("cannot-evaluate", "no schema for boundary {!r}".format(boundary))
    return schema(raw)


def _schema_staleness(raw):
    """A staleness horizon fails OPEN to the 24h default: a malformed horizon can neither age out valid
    evidence (a negative or NaN value) nor never age it out (Infinity), and never raises in arithmetic."""
    d = raw if isinstance(raw, dict) else {}
    th = _v_finite_pos(d.get("task_hours"), _ORCH_MAX_HORIZON_HOURS)
    eh = _v_finite_pos(d.get("external_hours"), _ORCH_MAX_HORIZON_HOURS)
    return ("ok", {"task_hours": th if th is not None else 24,
                   "external_hours": eh if eh is not None else 24})


def _schema_turn_state(raw):
    """A counter is 0 when its key is ABSENT on a readable turn-state (a fresh count), the value when
    present and valid, and None when present-but-malformed OR the whole turn-state is unreadable (raw is
    not a dict). The CALLER maps None to the fail-safe direction (stop -> the loop bound, so a malformed
    or unreadable counter never licenses unbounded denies; schedule -> 0, so it never buys cap relief).
    schedule_basis is a string or None."""
    if not isinstance(raw, dict):
        return ("ok", {"stop_denials": None, "schedule_denials": None, "schedule_basis": None})

    def _count(key):
        return 0 if key not in raw else _v_exact_int(raw[key], 0, _ORCH_COUNTER_MAX)
    basis = raw.get("schedule_basis")
    return ("ok", {"stop_denials": _count("stop_denials"),
                   "schedule_denials": _count("schedule_denials"),
                   "schedule_basis": basis if isinstance(basis, str) else None})


_ORCH_SCHEMAS = {"staleness": _schema_staleness, "turn_state": _schema_turn_state}


def _orch_token_present(needle, hay):
    """Whole-token (word-boundaried) presence test, so 'ci-7' does not match 'xci-70' and 's1' does not
    match 's10' (CX-M5/M8): the guard's id/ref matching is never a bare substring."""
    if not needle or not hay:
        return False
    return re.search(r"(?<![A-Za-z0-9_-]){}(?![A-Za-z0-9_-])".format(re.escape(needle)), hay) is not None


_ORCH_CHECKPOINT_MAX = 4096  # ids the C.3 checkpoint retains; a bound-forced drop is logged, never silent


def _orch_checkpoint_union(root, payload, record=True):
    """C.3 anti-shrinkage checkpoint union, run only after a status-ok enumeration. Compares the
    persisted checkpoint (<state_dir>/backlog-checkpoint.json) against the FULL validated payload
    (closed rows included: a closed row is the receipt that lets an id leave the checkpoint) and
    returns the cannot-evaluate rows to inject: an id recorded eligible or proposed that is absent from
    the payload entirely with no closed receipt (vanished), OR (FIX 2) an id recorded eligible now
    DEMOTED to proposed/ungranted with no closed receipt, is HELD rather than silently shrunk or
    demoted away. An unreadable or malformed checkpoint injects ONE marker row and is
    rewritten fresh. The rewritten checkpoint is the union of prior unreceipted eligible/proposed ids and
    this payload's, bounded at _ORCH_CHECKPOINT_MAX with a bound-forced drop logged to guard-events.
    Verdict effects are entirely existing branches (FIX 1: the stop path DENIES on an injected
    cannot-evaluate, the schedule path denies bounded by the cap); this helper adds no new deny logic, and a failed rewrite
    changes no verdict.

    record=False is the PREVIEW posture (tools/orch_preflight.py): the vanished-id injections are still
    COMPUTED for display, but NO checkpoint rewrite, init-marker write, or guard-event is emitted, so a
    preview makes no state change.

    FIX 4: an absent checkpoint is a legitimate FIRST window only when no prior window was ever
    initialised. When the durable init marker shows a prior window but the checkpoint is now gone, that
    is a possible reset (naive deletion or a crash) and is HELD (cannot-evaluate), never silently
    restarted. RESIDUAL (disclosed): the marker lives in the same actor-writable state dir, so this
    raises the bar (catches naive deletion) without being categorical. The checkpoint's eligibility memory (the FIX 2 demotion catch) lives in the same actor-writable state dir, so it raises the bar without being categorical."""
    sd = _orch_state_dir_for_root(root)
    path = os.path.join(sd, "backlog-checkpoint.json")
    marker = os.path.join(sd, "checkpoint-init.marker")
    injected, prior = [], {}
    present = os.path.lexists(path)
    try:
        if present:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            ids = data.get("ids") if isinstance(data, dict) else None
            if isinstance(ids, dict) and all(isinstance(v, str) for v in ids.values()):
                prior = ids
            else:
                injected.append(("backlog-checkpoint", "cannot-evaluate",
                                 "checkpoint malformed; rewritten fresh, one window uncompared"))
    except (OSError, ValueError):
        injected.append(("backlog-checkpoint", "cannot-evaluate",
                         "checkpoint unreadable; rewritten fresh, one window uncompared"))
    if not present and os.path.lexists(marker):
        # FIX 4: a prior init marker with the checkpoint now gone is a possible reset, held rather than
        # silently starting anti-shrinkage over.
        injected.append(("backlog-checkpoint", "cannot-evaluate",
                         "checkpoint missing though a prior window was initialised; possible reset"))
    # FIX 2: the per-id memory is an ELIGIBILITY label, not the raw state, so a demotion that keeps the
    # id present (state open->proposed, or granted true->false) is caught, not just an outright vanish.
    # "eligible" == granted and open (the id will classify actionable/waiting/blocked/cannot-evaluate);
    # "proposed" == state proposed or ungranted; "closed" is the receipt that lets an id leave. A legacy
    # checkpoint's "open" value reads as "eligible" (a back-compatible migration, no memory lost).
    def _label(it):
        if it["state"] == "closed":
            return "closed"
        return "eligible" if (it["granted"] and it["state"] == "open") else "proposed"
    current = {it["id"]: _label(it) for it in payload}
    for iid in sorted(prior):
        was = "eligible" if prior[iid] == "open" else prior[iid]
        if was in ("eligible", "proposed") and iid not in current:
            injected.append((iid, "cannot-evaluate",
                             "vanished from the enumeration without a close receipt"))
        elif was == "eligible" and current.get(iid) == "proposed":
            # the demotion variant: a previously-actionable id relabelled to proposed/ungranted routes
            # to the harmless proposed bucket and evades both the deny and the vanish check; held.
            injected.append((iid, "cannot-evaluate",
                             "demoted from actionable to proposed/ungranted without a close receipt; held"))
    union = {iid: ("eligible" if st == "open" else st) for iid, st in prior.items()
             if (st in ("open", "eligible", "proposed")) and current.get(iid) != "closed"}
    for it in payload:
        if it["state"] != "closed":
            union[it["id"]] = current[it["id"]]
    if len(union) > _ORCH_CHECKPOINT_MAX:
        dropped = sorted(union)[_ORCH_CHECKPOINT_MAX:]
        union = {iid: union[iid] for iid in sorted(union)[:_ORCH_CHECKPOINT_MAX]}
        if record:
            _orch_guard_event(root, "checkpoint-bound", "dropped",
                              "{} id(s) past the {} bound: {}".format(
                                  len(dropped), _ORCH_CHECKPOINT_MAX, ", ".join(dropped[:10])))
    if record:
        if not _orch_write_json_atomic(path, {"version": 1, "ts": _orch_now().isoformat(),
                                              "ids": union}):
            _orch_guard_event(root, "checkpoint-unwritable", "recorded",
                              "the checkpoint could not be rewritten; the next window compares "
                              "against the prior state")
        elif not os.path.lexists(marker):
            # FIX 4: record that a window has now been initialised, so a later deletion is detectable.
            # FIX C: a failed marker write leaves no init marker, so a later checkpoint deletion would
            # go undetected; record it as a fact (fail-loud) and HOLD this window (cannot-evaluate),
            # never a silent gap, consistent with the other recorders.
            if not _orch_write_json_atomic(marker, {"version": 1, "ts": _orch_now().isoformat()}):
                _orch_guard_event(root, "checkpoint-marker-unwritable", "recorded",
                                  "the checkpoint-init marker could not be written; a later "
                                  "checkpoint deletion would be undetectable this window")
                injected.append(("backlog-checkpoint", "cannot-evaluate",
                                 "checkpoint-init marker unwritable; a later deletion would go "
                                 "undetected"))
    return injected


def _orch_build_ctx(reg, root, kind, data, wake_text=None, record_checkpoint=True):
    """Assemble the decide_yield context from live state (the bindings' I/O half). Returns
    (ctx, turn_state_or_None, basis). The C.1 escape unpack, the C.2 attestation threading, and the
    C.3 checkpoint injection all land HERE, never in decide_yield: the decision core's verdict
    lattice is untouched, and ctx["escape_spoof"] is a recorder-only key decide_yield never reads."""
    staleness = _orch_validate("staleness", reg.get("staleness"))[1]
    task_hours = staleness["task_hours"]
    ts = _orch_turn_state(root)
    tstate = _orch_validate("turn_state", ts)[1]
    # stop counter fails OPEN to the loop bound (an unreadable counter never licenses unbounded denies);
    # schedule counter fails CLOSED to 0 (a malformed value never manufactures cap relief, CX-R4-3).
    counter = tstate["stop_denials"] if tstate["stop_denials"] is not None else _ORCH_LOOP_BOUND
    schedule_denials = tstate["schedule_denials"] if tstate["schedule_denials"] is not None else 0
    status, payload = _orch_enumerate(reg, root)
    if status == "ok":
        live_ids, ledger_readable, _detail = _orch_live_ledger_ids(root, task_hours)
        classes = classify_backlog(payload, live_ids, ledger_readable,
                                   _orch_pending_haystack(reg, root), staleness,
                                   attestations=_orch_attestation_refs(reg, root, staleness))
        # C.3: an id recorded open/proposed at the checkpoint that vanished from this enumeration
        # with no closed receipt is held (cannot-evaluate); the injected ids enter the class-tagged
        # basis below, so under D12 a shrink is a CHANGED basis, never premature cap relief.
        classes["cannot_evaluate"].extend(
            _orch_checkpoint_union(root, payload, record=record_checkpoint))
        enum_detail = ""
        # D12: tag each id with its class so an item flipping between classes reads as a CHANGED basis (an
        # untagged merge let such a flip collide to the same basis and skip fresh handling). CONV4-CX2 +
        # CONV6-C: waiting/blocked carry their blocker KIND:REF (a changed recheck obligation, e.g. a
        # blocker ref vendor-A->vendor-B, is a changed basis) and proposed (p:) its membership, so any
        # genuine backlog change resets the denial count rather than inheriting premature cap relief.
        basis = json.dumps(sorted(
            ["a:" + i for i, _t, _w in classes["actionable"]]
            + ["c:" + i for i, _c, _p in classes["cannot_evaluate"]]
            + ["w:{}:{}:{}".format(i, k, r) for i, k, r in classes["waiting"]]
            + ["b:{}:{}:{}".format(i, k, r) for i, k, r in classes["blocked"]]
            + ["p:" + i for i in classes["proposed"]]))
    else:
        classes = {"actionable": [], "waiting": [], "blocked": [], "cannot_evaluate": [], "proposed": []}
        enum_detail = payload
        basis = status
    wake_named = None
    rechecked = classes["waiting"] + classes["blocked"]
    if kind == "schedule_idle" and rechecked:
        wake_named = any(_orch_token_present(i, wake_text) or _orch_token_present(p, wake_text)
                         for i, _c, p in rechecked)
    basis_unchanged = tstate["schedule_basis"] == basis
    escape_active, escape_spoof = _orch_escape_active(reg, root)
    ctx = {"kind": kind, "escape": escape_active, "escape_spoof": escape_spoof,
           "loop_signal": data.get("stop_hook_active") is True,  # strict bool; a "false" string is not a signal
           "counter": counter, "enum_status": status, "enum_detail": enum_detail,
           "actionable": classes["actionable"], "waiting": classes["waiting"],
           "blocked": classes["blocked"], "cannot_evaluate": classes["cannot_evaluate"],
           "proposed": classes["proposed"],
           "wake_named": wake_named, "schedule_denials": schedule_denials,
           "basis_unchanged": basis_unchanged}
    return ctx, (ts if isinstance(ts, dict) else None), basis


def _orch_record_denial(root, ts, kind, basis):
    """Persist the deny counters (the guard-owned loop bound; platform-independent). Returns True on a
    successful persist. The increment base is sanitized so a tampered non-int counter cannot raise here;
    a STOP-path caller that gets False must fail OPEN, since an un-persistable counter never reaches the
    loop bound and would otherwise re-deny forever."""
    state = dict(ts or {})
    if kind == "schedule_idle":
        prior = _v_exact_int(state.get("schedule_denials"), 0, _ORCH_COUNTER_MAX)
        prior = prior if prior is not None else 0
        # D12: a CHANGED basis starts a fresh count (1), so denials accrued on a different basis can
        # never buy premature cap relief on this one.
        state["schedule_denials"] = prior + 1 if state.get("schedule_basis") == basis else 1
        state["schedule_basis"] = basis
    else:
        prior = _v_exact_int(state.get("stop_denials"), 0, _ORCH_COUNTER_MAX)
        state["stop_denials"] = (prior if prior is not None else 0) + 1
    return _orch_save_turn_state(root, state)


def _orch_record_escape_spoof(root, detail):
    """C.1 recorder: an ignored (foreign, symlinked, hardlinked, actor-owned, or writable) escape
    sentinel is a recorded fact, never a verdict input: the decision already proceeded exactly as with
    no sentinel. Appends a guard-events row and writes <state_dir>/escape-spoof.json so the next resume
    audit surfaces it once. FIX 6: the recording is FAIL-LOUD: returns '' on success, else the warning
    text the caller MUST append to its banner, so an ignored sentinel that could not be recorded is
    never silently dropped (which would contradict the always-recorded-and-surfaced claim, and leave
    the resume audit nothing to surface when both writes failed)."""
    ok_event = _orch_guard_event(root, "escape-spoof", "recorded", detail)
    ok_file = _orch_write_json(os.path.join(_orch_state_dir_for_root(root), "escape-spoof.json"),
                               {"ts": _orch_now().isoformat(), "detail": detail})
    if ok_event and ok_file:
        return ""
    return ("Additionally, an ignored escape sentinel could not be fully recorded (guard-events {}, "
            "escape-spoof.json {}); record the spoof manually before resuming (nocncl)."
            .format("ok" if ok_event else "FAILED", "ok" if ok_file else "FAILED"))


def _orch_open_dispositions(ctx):
    """Every NON-CLOSED disposition id a forced exit would leave behind: actionable, cannot-evaluate,
    waiting, blocked, and proposed. FIX 5: a forced (cap/bound) exit past ANY of these is recorded; the
    old gate recorded only over actionable or cannot-evaluate, so a cap/bound exit over a granted-open
    waiting or blocked row went unrecorded. When the enumeration itself failed the open set cannot even
    be established (enum_status != 'ok'); the caller records regardless in that case."""
    return ([i for i, _t, _w in ctx["actionable"]]
            + [i for i, _c, _p in ctx["cannot_evaluate"]]
            + [i for i, _k, _r in ctx["waiting"]]
            + [i for i, _k, _r in ctx["blocked"]]
            + list(ctx["proposed"]))


def _orch_record_forced_exit(root, event_name, ctx, reason):
    """C.4 recorder: a bound- or cap-released ALLOW_WITH_FINDINGS past any non-closed disposition is
    marked forced_unresolved so the next resume audit surfaces it for triage. FIX 5: the record is
    APPEND-ONLY and uniquely keyed (<state_dir>/forced-exit.jsonl, one row per forced exit with a
    unique key), so two forced exits before a resume are BOTH kept and each surfaced exactly once,
    never clobbered into a single fixed file. No register row, attestation, or escape-adjacent artefact
    ever suppresses this record. Returns '' on success, else the failure text the caller MUST append to
    its banner (the one record this design leans on can never fail silently). The verdict is never
    changed here."""
    open_ids = _orch_open_dispositions(ctx)
    enum_ok = ctx.get("enum_status") == "ok"
    key = _orch_now().isoformat() + "-" + os.urandom(6).hex()
    named = (", ".join(open_ids[:_ORCH_MAX_NAMED])
             or ("open set unestablished" if not enum_ok else "none"))
    ok_event = _orch_guard_event(root, "forced_unresolved", "allow_with_findings",
                                 "{}: open ids {}".format(event_name, named))
    ok_file = _orch_append_jsonl(os.path.join(_orch_state_dir_for_root(root), "forced-exit.jsonl"),
                                 {"ts": _orch_now().isoformat(), "event": event_name, "key": key,
                                  "open_ids": open_ids, "reason": reason,
                                  "enum_status": ctx.get("enum_status")})
    if ok_event and ok_file:
        return ""
    return ("Additionally, the forced-exit record could not be fully persisted (guard-events {}, "
            "forced-exit.jsonl {}); record the forced exit manually before resuming (nocncl)."
            .format("ok" if ok_event else "FAILED", "ok" if ok_file else "FAILED"))


def _orch_stop_family(data, event_name, kind):
    """The shared Stop/TeammateIdle binding: scope, decide, map the verdict to the event's block
    mechanism (exit 2, doc-confirmed for both events 2026-08-29). Fail-OPEN on its own I/O errors;
    a cannot-evaluate DENIES (FIX 1)."""
    root = _orch_root(data)
    if root is None:
        return _allow()
    status, reg = _orch_registry(root)
    if status == "absent":
        return _allow()
    if status == "bad":
        return _stop_warn("AIQT guardrail: the orchestration registry could not be read "
                          "({}); the {} fails open on its own read error and, because the registry is "
                          "unreadable, writes NO guard-event (no record).".format(reg,
                                                                                  event_name))
    if not _orch_scope_live(reg, root, data.get("session_id")):
        return _allow()
    ctx, ts, basis = _orch_build_ctx(reg, root, kind, data)
    spoof_warn = (_orch_record_escape_spoof(root, ctx["escape_spoof"])
                  if ctx.get("escape_spoof") else "")
    verdict, reason, disposition = decide_yield(ctx)
    if verdict == "DENY":
        if not _orch_record_denial(root, ts, kind, basis):
            warn = ("the denial counter could not be persisted, so the loop bound cannot advance; "
                    "failing OPEN with findings rather than re-denying. Underlying: " + reason)
            _orch_guard_event(root, event_name, "allow_unpersistable", warn)
            return _stop_warn("AIQT guardrail ({}): {}{}".format(
                event_name, warn, " " + spoof_warn if spoof_warn else ""))
        _orch_guard_event(root, event_name, "deny", reason)
        # a DENY blocks (exit 2); if the spoof record itself failed, surface it on the block reason too
        return (2, None, reason + (" " + spoof_warn if spoof_warn else ""))
    _orch_guard_event(root, event_name, verdict.lower(), reason)
    if verdict == "ALLOW_WITH_FINDINGS":
        extra = ""
        if (ctx["counter"] >= _ORCH_LOOP_BOUND or ctx["loop_signal"]) \
                and (_orch_open_dispositions(ctx) or ctx["enum_status"] != "ok"):
            # C.4: the bound released this exit past open work; mark it forced_unresolved for the
            # next resume audit's triage. The fail-open verdict itself is unchanged.
            extra = _orch_record_forced_exit(root, event_name, ctx, reason)
        tail = " ".join(x for x in (extra, spoof_warn) if x)
        return _stop_warn("AIQT guardrail ({}): {}{}".format(
            event_name, reason, " " + tail if tail else ""))
    if spoof_warn:
        # a clean ALLOW whose spoof record FAILED still surfaces the failure (never a silent None)
        return _stop_warn("AIQT guardrail ({}): {}".format(event_name, spoof_warn))
    return _allow()


def orch_stop_guard(data):
    """setcmp/cntdef/trkasy/cnclse, Stop: deny a stop past enumerated actionable work
    OR any cannot-evaluate (FIX 1: ignorance refuses the wind-down; the operator escape releases);
    bounded by the guard-owned counter."""
    return _orch_stop_family(data, "Stop", "stop")


def orch_teammate_idle(data):
    """The same decision core at the TeammateIdle boundary. Cannot-evaluate DENIES the idle
    (FIX 1: ignorance refuses the wind-down), the same as the Stop boundary."""
    return _orch_stop_family(data, "TeammateIdle", "stop_idle" if False else "stop")


def _orch_register_wake(root, ts, prompt):
    """Record the sha256 of an ALLOWED wake's prompt into turn-state wake_digests (bounded), so the
    returning UserPromptSubmit is recognised as timer-originated by orch_prompt_stamp and does not reset
    the loop-guard counters or stamp a false genuine-human-input time (G1: the classifier was dead
    because nothing ever wrote wake_digests)."""
    if not isinstance(prompt, str) or not prompt:
        return
    digest = __import__("hashlib").sha256(prompt.encode("utf-8", "replace")).hexdigest()
    state = dict(ts or {})
    wd = state.get("wake_digests")
    wd = [d for d in wd if isinstance(d, str)] if isinstance(wd, list) else []
    wd.append(digest)  # a multiset: two identical wakes register two tokens, each consumed once (CX-M6)
    state["wake_digests"] = wd[-64:]  # bounded so the list cannot grow without limit
    _orch_save_turn_state(root, state)


def orch_yield_tool(data):
    """setcmp/cntdef/tstamp/estsep, PreToolUse over the scheduling tools: judge a call that parks the
    run (schedule_idle) or ends the loop (stop=true) against a fresh enumeration. The schedule path
    fails CLOSED on cannot-evaluate, bounded by the denial cap."""
    root = _orch_root(data)
    if root is None:
        return _allow()
    status, reg = _orch_registry(root)
    if status != "ok":
        return _allow() if status == "absent" else _ask(
            "AIQT guardrail: the orchestration registry could not be read ({}); a "
            "scheduling call cannot be judged, so it asks rather than silently proceeding."
            .format(reg),
            "AIQT guardrail: asked on a scheduling call under an unreadable orchestration registry.")
    if not _orch_scope_live(reg, root, data.get("session_id")):
        return _allow()
    tool = data.get("tool_name")
    declared = reg.get("yield_tools")
    if not isinstance(declared, list) or tool not in declared:
        return _allow()  # inside the matcher but outside the registry roster: out of scope
    tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    kind = "stop" if tool_input.get("stop") is True else "schedule_idle"
    wake_text = " ".join(str(v) for v in tool_input.values() if isinstance(v, str))
    ctx, ts, basis = _orch_build_ctx(reg, root, kind, data, wake_text=wake_text)
    spoof_warn = (_orch_record_escape_spoof(root, ctx["escape_spoof"])
                  if ctx.get("escape_spoof") else "")
    # Measured quiet beats a claimed quiet duration (estsep: the two grades never blend silently).
    claim = _ORCH_QUIET_CLAIM_RE.search(wake_text or "")
    measured_min = None
    if isinstance(ts, dict):
        stamp = _orch_parse_utc(ts.get("last_human_input_utc"))
        if stamp:
            measured_min = (_orch_now() - stamp).total_seconds() / 60.0
    if kind == "schedule_idle" and claim and "quiet" in (wake_text or "").lower() \
            and measured_min is not None and float(claim.group(1)) > measured_min + 1.0:
        reason = ("AIQT rule estsep/tstamp: the call claims {} quiet minutes but the measured gap "
                  "since the last genuine human input is {:.1f} minutes; the measured figure wins. "
                  "Re-issue without the unmeasured claim.".format(claim.group(1), measured_min))
        # The quiet-claim DENY has a trivial legit exit (re-issue without the claim), so it does NOT
        # consume the schedule cap (CX-M2: repeated quiet-claim denials could otherwise farm the cap
        # into an ALLOW_WITH_FINDINGS that parks genuinely actionable work).
        _orch_guard_event(root, "yield-tool", "deny", reason)
        return _deny(reason + (" " + spoof_warn if spoof_warn else ""),
                     "AIQT guardrail: denied a scheduling call whose quiet-duration claim "
                     "contradicts the measured figure.")
    verdict, reason, _disposition = decide_yield(ctx)
    if verdict == "DENY":
        _orch_record_denial(root, ts, kind, basis)
        _orch_guard_event(root, "yield-tool", "deny", reason)
        return _deny(reason + (" " + spoof_warn if spoof_warn else ""),
                     "AIQT guardrail: denied a {} call past the enumerated backlog.".format(tool))
    if kind == "schedule_idle":
        # G1: register the ALLOWED wake's prompt digest so its returning UserPromptSubmit is classified
        # timer-originated (not genuine human input), preserving the loop-guard counters across the wake.
        _orch_register_wake(root, ts, tool_input.get("prompt"))
    _orch_guard_event(root, "yield-tool", verdict.lower(), reason)
    if verdict == "ALLOW_WITH_FINDINGS":
        msg = "AIQT guardrail: {}".format(reason)
        forced = ((kind == "stop" and (ctx["counter"] >= _ORCH_LOOP_BOUND or ctx["loop_signal"]))
                  or (kind == "schedule_idle" and ctx["schedule_denials"] >= _ORCH_SCHEDULE_CAP
                      and ctx["basis_unchanged"]))
        if forced and (_orch_open_dispositions(ctx) or ctx["enum_status"] != "ok"):
            # C.4/FIX 5: cap or bound relief past ANY non-closed disposition (or during a whole-
            # enumerator failure) is marked forced_unresolved; a failed record surfaces in the
            # returned systemMessage rather than silently vanishing.
            extra = _orch_record_forced_exit(root, "yield-tool", ctx, reason)
            if extra:
                msg += " " + extra
        if spoof_warn:
            msg += " " + spoof_warn
        return (0, {"systemMessage": msg}, None)
    if spoof_warn:
        return (0, {"systemMessage": "AIQT guardrail: {}".format(spoof_warn)}, None)
    return _allow()


def orch_ask_guard(data):
    """cntdef/recfst bounded by humovs, PreToolUse AskUserQuestion: deny a blocking question in
    unattended mode with the record-and-continue instruction; fail OPEN on an absent or unreadable
    mode (this guards one mistake shape, not a security boundary). Its regression vectors are held by the behaviour self-test."""
    if data.get("tool_name") != "AskUserQuestion":
        return _allow()
    root = _orch_root(data)
    if root is None:
        return _allow()
    status, reg = _orch_registry(root)
    if status != "ok":
        return _allow()  # absent OR unreadable registry: fail open, this control is advisory-shaped
    mode = _orch_mode(reg, root)
    if mode is None or "unattended" not in mode:
        if mode is None:
            _orch_guard_event(root, "ask-guard", "fail-open", "mode record absent or unreadable")
        return _allow()
    tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    questions = tool_input.get("questions") if isinstance(tool_input.get("questions"), list) else []
    text = json.dumps(tool_input, sort_keys=True)
    digest = __import__("hashlib").sha256(text.encode("utf-8", "replace")).hexdigest()
    key = "{}::{}".format(data.get("session_id", ""), data.get("tool_use_id", digest[:12]))
    pending_path = os.path.join(_orch_state_dir_for_root(root), "pending-asks.jsonl")
    rows, _bad = _orch_read_jsonl(pending_path)
    recorded = rows is not None and any(r.get("key") == key for r in rows)
    if rows is not None and not recorded:
        # A bounded REDACTED summary plus digest, never the question text (log-redaction discipline).
        recorded = _orch_append_jsonl(pending_path, {"ts": _orch_now().isoformat(), "key": key,
                                                     "questions": len(questions), "len": len(text),
                                                     "digest": digest})
    reason = ("AskUserQuestion BLOCKED: the session operating-mode is unattended. RECORD the decision "
              "as pending (the registry's pending-decisions surface) with your recommended option and "
              "rationale, then CONTINUE with the next authorized independent item. If the decision "
              "sits at the human-oversight threshold (high-consequence, irreversible, or "
              "outward-facing), record it and HOLD that item; the hold never licenses acting without "
              "the answer. If the maintainer is in fact present, set an attended operating-mode in "
              "the mode record first, then re-issue.")
    _orch_guard_event(root, "ask-guard", "deny",
                      "pending key {}{}".format(key, "" if recorded else " (NOT persisted)"))
    banner = ("AIQT guardrail: denied a blocking question in unattended mode; recorded pending."
              if recorded else "AIQT guardrail: denied a blocking question in unattended mode, but the "
              "pending row could NOT be persisted; record the decision manually (nocncl).")
    return _deny(reason, banner)


_ORCH_PLAIN_COMMAND_RE = re.compile(r"[A-Za-z0-9_ \t./=:@,+%-]+")
# Shell reserved words that change execution without a metacharacter: `coproc` backgrounds a coprocess whose
# output the harness does not capture, and the compound/prefix keywords start a construct that is not a plain
# producer. They carry only letters, so the plain-command charset alone would admit them; an exact token
# match excludes them. A quoted or otherwise obscured spelling already carries a metacharacter and is caught.
_ORCH_SHELL_KEYWORDS = frozenset((
    "if", "then", "else", "elif", "fi", "case", "esac", "for", "select", "while", "until",
    "do", "done", "in", "function", "time", "coproc"))


def _orch_foreground_detach(command):
    """True when a foreground command carries an executable, unquoted, unescaped bare `&` control operator
    that detaches a child, launching asynchronous work the foreground tool call does not track. The bare
    detach `&` is distinguished from the shell forms that also carry an ampersand but do NOT detach: the
    `&&` logical-AND, the `&>` and `&>>` redirects, the `<&`, `>&`, and `|&` descriptor-duplication and
    pipe-stderr operators, any single-quoted, double-quoted, or backslash-escaped ampersand, and an `&`
    inside an unquoted, word-start `#` comment (comment text, not an operator). A dedicated quote- and
    escape-tracking scan is used, NOT _segments: that helper strips quote and escape provenance and
    classifies both `echo "&"` and `echo \\&` as an `&` separator, which would over-fire. It also drops a
    word-start `#` comment so a commented-out `&` does not prompt, but only to the END OF THAT LINE: a
    comment never suppresses a later line, so a real bare `&` on a subsequent line of a multi-line command
    is still caught rather than smuggled past.

    AMBIGUOUS QUOTING FAILS TOWARD ASK, never toward a silent allow: a scan that ends still inside an
    unbalanced single or double quote cannot prove that a later `&` is quoted rather than an operator (an
    unbalanced quote, or a construct this scan does not model such as ANSI-C `$'...'` or locale `$"..."`
    quoting, can leave the scan `inside quotes` and skip a real trailing `&`), so it reports a detach
    (True -> ASK) rather than allowing. A genuinely balanced, quoted `&` is literal and correctly ignored.

    NARROW BY CONSTRUCTION: this scans for the accidental bare-operator case only. Grammar it does not
    model (a here-document body, a nested shell string, an alias or function that renames a detacher, and
    runtime detachers such as nohup/setsid/disown/coproc) is a disclosed residual; where such a construct
    still leaves an unquoted bare `&`, or leaves the scan inside an unbalanced quote, it errs toward the
    ASK, but a detacher that carries no bare `&` (setsid worker, a nested `bash -c '... &'`) is NOT caught
    here and is a silent-allow residual disclosed in the manifest."""
    in_single = in_double = escaped = False
    prev_dup = False  # the previous char was an unquoted, unescaped >, <, or | (a dup/pipe operator lead)
    word_start = True  # the next unquoted char begins a word (start of string, or after unquoted whitespace)
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if escaped:
            escaped, prev_dup, word_start = False, False, False
            i += 1
            continue
        if in_single:
            if ch == "'":
                in_single = False
            prev_dup, word_start = False, False
            i += 1
            continue
        if in_double:
            if ch == "\\":
                escaped = True
            elif ch == '"':
                in_double = False
            prev_dup, word_start = False, False
            i += 1
            continue
        if ch == "#" and word_start:  # an unquoted, word-start comment: the rest of THIS line is not code
            # A `#` comment runs only to the end of ITS line, not to the end of a multi-line command. Skip
            # to the next newline and resume the scan, so a real bare `&` on a LATER line is not smuggled
            # past by a comment on an earlier one. Breaking the whole scan here silently allowed exactly that
            # (L-GS1: `echo hi  # note\nsleep 100 &`); this fails closed on the comment-obscured detach.
            nl = command.find("\n", i)
            if nl == -1:
                break  # no later line: the comment runs to the end of the string, nothing more to scan
            i = nl  # resume at the newline; the whitespace branch consumes it and begins a new line/word
            continue
        if ch.isspace():
            prev_dup, word_start = False, True
            i += 1
            continue
        if ch == "\\":
            escaped, prev_dup, word_start = True, False, False
            i += 1
            continue
        if ch == "'":
            in_single, prev_dup, word_start = True, False, False
            i += 1
            continue
        if ch == '"':
            in_double, prev_dup, word_start = True, False, False
            i += 1
            continue
        if ch == "&":
            nxt = command[i + 1] if i + 1 < n else ""
            if nxt == "&":  # `&&` logical AND: not a detach
                prev_dup, word_start = False, False
                i += 2
                continue
            if nxt == ">":  # `&>` / `&>>` redirect: not a detach
                prev_dup, word_start = False, False
                i += 1
                continue
            if prev_dup:  # `>&` / `<&` / `|&` descriptor-dup or pipe-stderr: not a detach
                prev_dup, word_start = False, False
                i += 1
                continue
            return True  # an executable bare `&` control operator: a foreground detach
        prev_dup, word_start = ch in (">", "<", "|"), False
        i += 1
    # A scan that ended still inside an unbalanced quote could not prove a later `&` was quoted; fail
    # toward ASK rather than silently allow a possibly-real detach it could not see.
    return in_single or in_double


def orch_truncation_guard(data):
    """trkasy/vrfdlv/nocncl, PreToolUse Bash, scoped to run_in_background dispatches. AIRTIGHT-NARROW: it
    performs NO shell parsing, so no lexical or quoting edge can fabricate a capture. A background dispatch
    is ALLOWED only when its command is a PLAIN command carrying no shell metacharacter and no shell reserved
    word (whose full stdout the harness binds to the TaskOutput completion signal); ANY shell metacharacter -
    a pipe, redirect, separator, quote, expansion, substitution, grouping, glob, comment, or newline - or a
    reserved word such as `coproc` (which backgrounds a coprocess) makes the capture unprovable by this
    guard, and it ASKS the operator to confirm. It never proves capture through
    shell syntax and never DENIES a parsed command; the cost is that a non-trivial background dispatch asks
    for confirmation rather than being proven, a deliberate trade of coverage for a guarantee of no
    shell-syntax false-allow; whether the output actually reaches durable capture is a run-time property
    (the invoked program's own behaviour, or a platform limit such as the harness output ceiling) that is
    out of view here and is confirmed by the post-execution delivery-marker discipline, a disclosed
    residual. A foreground call is in scope only for one NARROW case (L-GS1 / trkasy): shell syntax that
    DETACHES a child with a bare `&` still launches asynchronous work the foreground tool call does not
    track, so a readable foreground command carrying such an operator ASKS the operator to use the tracked
    background dispatch instead; every other foreground call remains out of scope (the harness returns its
    output directly)."""
    if data.get("tool_name") != "Bash":
        return _allow()
    root = _orch_root(data)
    if root is None:
        return _allow()
    status, _reg = _orch_registry(root)
    if status == "absent":
        return _allow()
    tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    command = tool_input.get("command")
    rib = tool_input.get("run_in_background") is True
    if not rib:
        # Foreground scope is narrow: a plain foreground call returns its output directly and is out of
        # scope, but a bare `&` detaches a child into untracked asynchronous work whose result and failure
        # are then lost. On a readable foreground command carrying such an operator, ASK the operator to use
        # the platform's tracked background dispatch (run_in_background) and collect its completion, keep the
        # command foreground and wait, or confirm the detached result is genuinely irrelevant. An unreadable
        # or non-detaching foreground command stays out of scope (ALLOW): approving this ASK does not itself
        # create tracking, and converting to run_in_background=true is what lets the dispatch ledger record it.
        if isinstance(command, str) and _orch_foreground_detach(command):
            return _ask(
                "AIQT rule trkasy: this foreground command detaches a child with a bare '&', launching "
                "asynchronous work this tool call does not track, so its result and failure are lost. Use "
                "the platform's tracked background dispatch (run_in_background) and collect its completion, "
                "keep the command in the foreground and wait for it, or confirm the detached result and "
                "completion are genuinely not needed.",
                "AIQT guardrail: asked on a foreground bare-& detach (untracked asynchronous work).")
        return _allow()  # foreground without a bare-& detach operator is out of scope by design
    if not isinstance(command, str) or not command:
        return _deny(
            "AIQT rule trkasy: a background dispatch carried no readable command string; failing closed.",
            "AIQT guardrail: denied an unreadable background dispatch (fail-closed).")
    if _ORCH_PLAIN_COMMAND_RE.fullmatch(command) and not (_ORCH_SHELL_KEYWORDS & set(command.split())):
        return _allow()  # no metacharacter and no reserved word: the full stdout reaches the harness capture
    return _ask(
        "AIQT rules trkasy/vrfdlv: this background dispatch uses shell syntax (a pipe, redirect, "
        "separator, quote, expansion, or grouping), so this guard does not parse it to prove the full "
        "output is captured. Confirm the full output lands in a durable capture - redirect the producer's "
        "own stdout to a real file, or make a real-file tee the final stage - or run it in the foreground.",
        "AIQT guardrail: asked on a background dispatch whose full-output capture it does not parse.")


def orch_dispatch_ledger(data):
    """trkasy/recfst, PostToolUse (recorder, never blocks): append launch rows for background Bash and
    registry-declared dispatch tools, completion rows for TaskOutput reads. A failed write SURFACES
    as a non-blocking systemMessage (nocncl), never a swallowed error."""
    root = _orch_root(data)
    if root is None:
        return _allow()
    status, reg = _orch_registry(root)
    if status != "ok":
        return _allow()
    if not _orch_scope_live(reg, root, data.get("session_id")):
        return _allow()  # only the holder session writes the shared dispatch ledger (CX-M4b)
    tool = data.get("tool_name")
    tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    response = data.get("tool_response")
    row = None
    if tool == "TaskOutput":
        tid = tool_input.get("task_id") or tool_input.get("taskId")
        if isinstance(tid, str) and tid:
            row = {"event": "complete", "task_id": tid, "tool": tool, "wake": True}
    else:
        dispatch_tools = reg.get("dispatch_tools") if isinstance(
            reg.get("dispatch_tools"), list) else []
        is_dispatch = (tool == "Bash" and tool_input.get("run_in_background") is True) \
            or tool in dispatch_tools
        if is_dispatch:
            tid = None
            observed = False
            if isinstance(response, dict):
                for k in ("task_id", "taskId", "id"):
                    if isinstance(response.get(k), str) and response.get(k):
                        tid = response[k]
                        observed = True
                        break
            if tid is None:
                basis = json.dumps(tool_input, sort_keys=True)
                tid = "disp-" + __import__("hashlib").sha256(
                    (basis + _orch_now().isoformat()).encode("utf-8", "replace")).hexdigest()[:12]
            # CX-M7: only a REAL observed task id has a provable wake route; a synthesized id gets
            # wake=false so it can never be counted as a live task that excuses an idle.
            row = {"event": "launch", "task_id": tid, "tool": tool or "", "wake": observed}
    if row is None:
        return _allow()
    row["ts"] = _orch_now().isoformat()
    path = os.path.join(_orch_state_dir_for_root(root), "dispatch-ledger.jsonl")
    if not _orch_append_jsonl(path, row):
        return (0, {"systemMessage": "AIQT guardrail: the dispatch-ledger write failed; "
                                     "the launched work may be invisible to the stop guard."}, None)
    return _allow()


def orch_prompt_stamp(data):
    """tstamp/estsep, UserPromptSubmit (recorder, never blocks): stamp genuine human input from the
    clock, classify a prompt matching a registered wake as timer-originated, and inject the measured
    gap as context so quiet-duration reasoning uses a measured figure."""
    root = _orch_root(data)
    if root is None:
        return _allow()
    status, reg = _orch_registry(root)
    if status != "ok":
        return _allow()
    if not _orch_scope_live(reg, root, data.get("session_id")):
        return _allow()  # only the holder session stamps/resets the shared turn-state (CX-M4b)
    prompt = data.get("prompt")
    ts = _orch_turn_state(root) or {}
    digest = __import__("hashlib").sha256(
        (prompt or "").encode("utf-8", "replace")).hexdigest() if isinstance(prompt, str) else ""
    _wds = ts.get("wake_digests")
    _wds = _wds if isinstance(_wds, list) else []  # a non-list wake_digests never enables substring match
    timer_originated = digest and digest in _wds
    prev = _orch_parse_utc(ts.get("last_human_input_utc"))
    if not timer_originated:
        ts["last_human_input_utc"] = _orch_now().isoformat()
        ts["stop_denials"] = 0
        ts["schedule_denials"] = 0
        ts.pop("schedule_basis", None)
        _orch_save_turn_state(root, ts)
        return _allow()
    # one-shot: consume the matched wake digest so a later prompt with identical text (including genuine
    # human input) is not perpetually misclassified as timer-originated (R2-CM4/CX-M7).
    wd = list(ts.get("wake_digests") or [])
    if digest in wd:
        wd.remove(digest)  # consume exactly ONE token, so a second identical wake is still recognized
    ts["wake_digests"] = wd
    _orch_save_turn_state(root, ts)
    gap = "unknown (no prior stamp; an unknown duration authorizes nothing)"
    if prev is not None:
        gap = "{:.1f} minutes".format((_orch_now() - prev).total_seconds() / 60.0)
    return (0, {"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": "[aiqt-orch] This prompt is TIMER-ORIGINATED (a registered wake), not "
                             "human input. Measured gap since the last genuine human input: {}."
                             .format(gap)}}, None)


def _orch_resume_probes(reg, root):
    """The resume-audit probes (shared with tools/orch_doctor.py --resume-audit). Returns a list of
    finding strings; empty means the recorded state matches observed reality."""
    findings = []
    rec = reg.get("record") if isinstance(reg.get("record"), dict) else {}
    handoff_path = _orch_path(root, rec.get("handoff"))
    if handoff_path:
        try:
            with open(handoff_path, "r", encoding="utf-8", errors="replace") as fh:
                handoff = fh.read()
        except OSError as exc:
            findings.append("declared handoff unreadable ({}): cannot-evaluate, the barrier holds"
                            .format(exc))
            handoff = ""
        m = re.search(r"^Branch:\s*(\S+)\s*$", handoff, re.MULTILINE)
        if m:
            actual = _head_branch(root)
            if actual is not None and actual != m.group(1):
                findings.append("handoff names branch {} but HEAD is on {}".format(
                    m.group(1), actual))
        m = re.search(r"^Gate:\s*green\s*@\s*([0-9a-f]{7,40})\s*$", handoff, re.MULTILINE)
        if m:
            try:
                env = _isolate_git_env(dict(os.environ))
                head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                                      capture_output=True, text=True, timeout=5, env=env)
                sha = head.stdout.strip() if head.returncode == 0 else ""
            except Exception:
                sha = ""
            if not sha or not sha.startswith(m.group(1)):
                findings.append("handoff gate marker cites commit {} but HEAD is {}".format(
                    m.group(1), sha[:12] or "unreadable"))
    for key in ("findings", "pending_decisions"):
        path = _orch_path(root, rec.get(key))
        if path:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    fh.read()
            except OSError as exc:
                findings.append("declared record surface {} unreadable ({}): cannot-evaluate"
                                .format(key, exc))
    lease = reg.get("lease") if isinstance(reg.get("lease"), dict) else None
    if lease:
        path = _orch_path(root, lease.get("path"))
        max_age = lease.get("max_age_hours")
        if path:
            try:
                st = os.stat(path)
                age = _orch_now().timestamp() - st.st_mtime
                if isinstance(max_age, (int, float)) and max_age > 0 and age > max_age * 3600:
                    findings.append("the orchestrator lease is stale (older than {}h)".format(max_age))
                if age < -_ORCH_CLOCK_SKEW:
                    # CONV4-G2 + CONV6-F: a FUTURE lease mtime (clock skew or tamper) is checked whenever
                    # the lease is stattable, NOT only when a max_age horizon happens to be configured.
                    findings.append("the orchestrator lease mtime is in the future (clock skew or tamper)")
            except FileNotFoundError:
                pass  # no lease yet is a legitimate resume state
            except OSError as exc:
                findings.append("declared lease unreadable ({}): cannot-evaluate".format(exc))
    findings.extend(_orch_merge_pending_findings(reg, root))
    findings.extend(_orch_validate_attestations(reg, root))
    findings.extend(_orch_pending_artefact_findings(root))
    return findings


def _orch_merge_pending_findings(reg, root):
    """The cheap in-hook layer of the record-drift check: an OPEN merge_pending row whose pr:N ref
    already has first-parent merge evidence is a divergence finding. tools/check_record_drift.py is
    the authoritative gate; this probe only feeds the resume audit."""
    rec = reg.get("record") if isinstance(reg.get("record"), dict) else {}
    path = _orch_path(root, rec.get("findings"))
    if not path:
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        return ["declared findings register unreadable ({}): cannot-evaluate".format(exc)]
    prs = set()
    for line in text.splitlines():
        if "merge_pending" in line:
            for m in re.finditer(r"\bpr:(\d+)\b", line):
                prs.add(m.group(1))
    if not prs:
        return []
    try:
        env = _isolate_git_env(dict(os.environ))
        log = subprocess.run(["git", "-C", root, "log", "--first-parent", "-n", "500",
                              "--format=%s"], capture_output=True, text=True, timeout=10, env=env)
        subjects = log.stdout if log.returncode == 0 else None
    except Exception:
        subjects = None
    if subjects is None:
        return ["merge evidence unreadable (git log failed): cannot-evaluate"]
    findings = []
    for n in sorted(prs):
        if re.search(r"\(#{}\)".format(re.escape(n)), subjects):
            findings.append("findings row still merge_pending on pr:{} but first-parent "
                            "history already carries its merge".format(n))
    return findings


def _orch_chained_rows(path, prefix):
    """Read a chained register (one JSON object per line; prev is the sha256 of the prior raw line,
    64*'0' for the first; seq is the line number; ids carry the family prefix) and return
    (rows, detail): rows is None when the file is unreadable or ANY line breaks the chain, shape,
    sequence, or id-prefix discipline, so a tampered or malformed register can never read as a
    smaller clean one. A compact inline mirror of the authoritative gate
    (tools/check_mistakes_register.py): the hooks script is standalone in adopter repos and cannot
    import tools/, so the CI gate remains the authoritative checker and this feeds only the audit."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        return (None, "unreadable ({})".format(exc))
    sha = __import__("hashlib").sha256
    rows, prev = [], None
    for n, line in enumerate(lines, 1):
        try:
            row = json.loads(line)
        except ValueError:
            return (None, "line {} is not JSON".format(n))
        want = "0" * 64 if prev is None else sha(prev.encode("utf-8")).hexdigest()
        if not isinstance(row, dict) or row.get("prev") != want or row.get("seq") != n:
            return (None, "line {} breaks the chain or sequence".format(n))
        rid = row.get("id")
        if not isinstance(rid, str) or not rid.startswith(prefix):
            return (None, "line {} id {!r} lacks the {} prefix".format(n, rid, prefix))
        rows.append(row)
        prev = line
    return (rows, "")


def _orch_register_tip(lines):
    """('ok', seq, digest) for a register's current tip: seq is the line count and digest is the
    sha256 of the last line (the same tip identity tools/check_mistakes_register.py anchors), so a
    yield-time re-anchor can rebind a validated snapshot to the register on disk."""
    if not lines:
        return ("ok", 0, "0" * 64)
    return ("ok", len(lines), _orch_sha256_hex(lines[-1]))


def _orch_register_authority(root, path):
    """FIX 3: the append-only AUTHORITY for a chained register (a compact inline mirror of
    tools/check_mistakes_register.py's verify_append_only; the standalone hooks script cannot import
    tools/). Returns ('ok', seq, digest) when the register on disk is a verified append-only extension
    of an authority the actor cannot trivially forge, its git merge-base state with origin/HEAD when
    the register is tracked, else its <path>.anchor file, with seq/digest identifying the current tip;
    otherwise ('hold', detail, None), a cannot-evaluate the caller routes to a fail-closed HOLD, never
    a clean pass. RESIDUAL (disclosed): the register is itself actor-writable, and this authority only
    checks that the on-disk register is an append-only EXTENSION of its committed (merge-base) or
    anchored prefix. An actor with filesystem write ALONE can therefore APPEND rows past that prefix
    (uncommitted; git status M) and have them counted as the tip, so the git/anchor authority defends
    the register-SWAP and prefix-REWRITE classes but not an appended approved row (A2); the categorical
    residual is closed only by an operator-owned, assistant-non-writable register at the OS layer."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        return ("hold", "register unreadable ({})".format(exc), None)
    env = _isolate_git_env(dict(os.environ))
    rel = None
    try:
        rel = os.path.relpath(os.path.realpath(path), os.path.realpath(root))
    except (OSError, ValueError):
        rel = None
    if rel and not rel.startswith(os.pardir + os.sep) and rel != os.pardir:
        try:
            tracked = subprocess.run(["git", "-C", root, "ls-files", "--error-unmatch", rel],
                                     capture_output=True, timeout=10, env=env).returncode == 0
        except (OSError, subprocess.SubprocessError) as exc:
            return ("hold", "cannot determine register tracking ({})".format(exc), None)
        if tracked:
            try:
                base = subprocess.run(["git", "-C", root, "merge-base", "HEAD", "origin/HEAD"],
                                      capture_output=True, text=True, timeout=10, env=env)
                if base.returncode != 0 or not base.stdout.strip():
                    return ("hold", "no computable merge-base with origin/HEAD", None)
                ref = base.stdout.strip()
                old = subprocess.run(["git", "-C", root, "show", "{}:{}".format(ref, rel)],
                                     capture_output=True, text=True, timeout=10, env=env)
            except (OSError, subprocess.SubprocessError) as exc:
                return ("hold", "cannot read the register authority ({})".format(exc), None)
            if old.returncode != 0:
                return ("hold", "cannot read the register at its merge-base authority", None)
            old_lines = old.stdout.splitlines()
            if lines[:len(old_lines)] != old_lines:
                return ("hold",
                        "register is not an append-only extension of its merge-base state", None)
            return _orch_register_tip(lines)
    anchor = path + ".anchor"
    try:
        with open(anchor, "r", encoding="utf-8") as fh:
            a = json.load(fh)
        n, digest = int(a["seq"]), str(a["digest"])
    except (OSError, ValueError, KeyError, TypeError):
        return ("hold", "declared register has no readable anchor authority", None)
    if len(lines) < n:
        return ("hold", "register is shorter than its verified anchor (rows removed)", None)
    if n > 0 and _orch_sha256_hex(lines[n - 1]) != digest:
        return ("hold", "the anchored row was rewritten (tamper or reorder)", None)
    return _orch_register_tip(lines)


def _orch_pointer_resolves(root, sd, pointer):
    """True when a register row's check_ref/evidence pointer resolves to something real: an existing
    relative path contained under the repo root or the state dir, or a guard-events row (the
    "guard-events:<token>" form, matched as a whole token against recorded kind/detail). An absolute
    pointer is rejected (it would let any host file satisfy the check, grdinp). Relevance is NOT
    machine-judgable and is not judged here: a real but misappropriated integrity signal passes
    resolution, a disclosed residual that triage refutes."""
    if not isinstance(pointer, str) or not pointer.strip():
        return False
    if pointer.startswith("guard-events:"):
        token = pointer[len("guard-events:"):].strip()
        rows, _bad = _orch_read_jsonl(os.path.join(sd, "guard-events.jsonl"))
        if not token or rows is None:
            return False
        return any(_orch_token_present(token, "{} {}".format(r.get("kind", ""), r.get("detail", "")))
                   for r in rows)
    if os.path.isabs(pointer):
        return False
    for base in (root, sd):
        rb = os.path.realpath(base)
        cand = os.path.realpath(os.path.join(base, pointer))
        if (cand == rb or cand.startswith(rb.rstrip(os.sep) + os.sep)) and os.path.exists(cand):
            return True
    return False


def _orch_attestation_derive(reg, root, sd, rows):
    """Shared C.2 derivation over a chained attestation register's rows: return (refs, unsub,
    findings), where refs is the sorted set of blocker refs each covered by a fresh, APPROVED row
    whose integrity pointer resolves. The AUDIT (_orch_validate_attestations) and the yield-time
    reader (_orch_attestation_refs, FIX A1) run this SAME logic, so a validated snapshot's stored
    'refs' field is never authoritative: the yield reader recomputes refs from the re-anchored
    register content itself, and a snapshot forged with fabricated refs substantiates none of them.
    RESIDUAL (disclosed, A2): an actor with filesystem write to the register can still APPEND a valid
    approved row (uncommitted; git status M, past the committed or anchored prefix the authority
    checks) whose ref this derivation then substantiates; only an operator-owned, assistant-non-
    writable register closes that categorically."""
    latest = {}
    for row in rows:
        latest[row["id"]] = row
    ext_hours = _orch_validate("staleness", reg.get("staleness"))[1]["external_hours"]
    now = _orch_now()
    refs, unsub, findings = [], [], []
    for rid in sorted(latest):
        row = latest[rid]
        status = row.get("status")
        if status in ("declined", "superseded"):
            continue
        ref = row.get("ref")
        pointer = row.get("check_ref") or row.get("evidence")
        observed = _orch_parse_utc(row.get("ts"))
        age = (now - observed).total_seconds() if observed is not None else None
        fresh = age is not None and -_ORCH_CLOCK_SKEW <= age <= ext_hours * 3600
        if not isinstance(ref, str) or not ref.strip():
            unsub.append(rid)
            findings.append("attestation {} names no blocker ref; it attests nothing".format(rid))
        elif status not in _ORCH_ATTEST_APPROVED:
            unsub.append(rid)
            findings.append("attestation {} status {!r} is not approved ({}); it attests "
                            "nothing".format(rid, status,
                                             "/".join(sorted(_ORCH_ATTEST_APPROVED))))
        elif not _orch_pointer_resolves(root, sd, pointer):
            unsub.append(rid)
            findings.append("attestation {} pointer {!r} resolves to nothing; it attests "
                            "nothing and blocks nothing".format(rid, pointer))
        elif fresh:
            refs.append(ref)
    return (sorted(set(refs)), unsub, findings)


def _orch_validate_attestations(reg, root):
    """The C.2 validation pass, run at AUDIT CADENCE (the resume audit and tools/orch_doctor.py
    --resume-audit both reach it through _orch_resume_probes), never synchronously at yield time:
    verify the declared attestation register's chain and shape inline, verify each candidate row's
    pointer resolves, and write <state_dir>/attestations-validated.json for the yield-time reader
    (_orch_attestation_refs). A row whose pointer resolves to nothing is recorded unsubstantiated: it
    attests nothing and blocks nothing. Also verifies the pointer of every class systemic-lapse row
    in the declared mistakes register (the GD-127 lapse lifecycle: a lapse is a recorded fact whose
    machine-written integrity signal must resolve; it never converts into a self-authorization).
    Returns finding strings; a failed snapshot write is itself a finding, and the yield-time reader
    then holds (the fail-safe direction), never a clean pass."""
    findings = []
    sd = _orch_state_dir_for_root(root)
    at_path = _orch_path(root, reg.get("attestations"))
    snap_path = os.path.join(sd, "attestations-validated.json")
    if at_path:
        canonical = os.path.realpath(at_path)
        rows, detail = _orch_chained_rows(at_path, "AT-")
        astatus, aseq, adigest = _orch_register_authority(root, at_path)
        hold_snap = {"version": 2, "ts": _orch_now().isoformat(), "status": "unreadable",
                     "refs": [], "unsubstantiated": [], "register": canonical,
                     "seq": None, "digest": None}
        if rows is None:
            findings.append("declared attestation register fails its inline chain/shape check ({}); "
                            "the yield-time reader holds affected items (cannot-evaluate)"
                            .format(detail))
            snap = hold_snap
        elif astatus != "ok":
            findings.append("declared attestation register fails its append-only authority ({}); the "
                            "yield-time reader holds affected items (cannot-evaluate)".format(aseq))
            snap = hold_snap
        else:
            refs, unsub, dfindings = _orch_attestation_derive(reg, root, sd, rows)
            findings.extend(dfindings)
            snap = {"version": 2, "ts": _orch_now().isoformat(), "status": "ok",
                    "refs": refs, "unsubstantiated": unsub, "register": canonical,
                    "seq": aseq, "digest": adigest}
        ok_snap = snap.get("status") == "ok"
        if not ok_snap:
            # delete-then-hold: invalidate any prior fresh 'ok' snapshot BEFORE writing the hold, so a
            # failed write cannot leave a stale clean pass usable.
            try:
                os.remove(snap_path)
            except OSError:
                pass
        if not _orch_write_json_atomic(snap_path, snap):
            findings.append("the attestation snapshot could not be written; invalidating any prior "
                            "snapshot so the yield-time reader holds (never a stale clean pass)")
            try:
                os.remove(snap_path)  # a failed OK write must not leave a prior snapshot usable either
            except OSError:
                pass
    mr_path = _orch_path(root, reg.get("mistakes_register"))
    if mr_path:
        rows, detail = _orch_chained_rows(mr_path, "MR-")
        if rows is None:
            findings.append("declared mistakes register fails its inline chain/shape check ({}); "
                            "tools/check_mistakes_register.py is the authoritative gate"
                            .format(detail))
        else:
            for row in rows:
                if row.get("class") != "systemic-lapse":
                    continue
                pointer = row.get("check_ref") or row.get("evidence")
                if not _orch_pointer_resolves(root, sd, pointer):
                    findings.append("systemic-lapse row {} is unsubstantiated: its pointer {!r} "
                                    "resolves to no machine-written integrity signal; it blocks "
                                    "nothing and never converts into a clean close"
                                    .format(row.get("id"), pointer))
    return findings


def _orch_forced_exit_findings(sd):
    """C.4/FIX 5: surface EACH append-only forced-exit.jsonl row exactly once. A companion
    forced-exit-surfaced.json records the keys already raised; a row whose key is not yet recorded
    becomes a finding, and the surfaced set advances only on a successful write. An unreadable log, a
    malformed line, or an unreadable/unwritable surfaced set re-fires next resume rather than losing
    the record (chkfcl: unreadable is a finding, never a silent skip; the advance is at-least-once)."""
    findings = []
    log = os.path.join(sd, "forced-exit.jsonl")
    rows, bad = _orch_read_jsonl(log)
    if rows is None:
        findings.append("pending forced-exit.jsonl present but unreadable: cannot-evaluate, held for "
                        "manual triage")
        return findings
    if bad:
        findings.append("{} malformed forced-exit.jsonl line(s): cannot-evaluate, held for manual "
                        "triage".format(bad))
    if not rows:
        return findings
    surfaced_path = os.path.join(sd, "forced-exit-surfaced.json")
    try:
        with open(surfaced_path, "r", encoding="utf-8") as fh:
            surfaced = set(json.load(fh).get("keys", []))
    except FileNotFoundError:
        surfaced = set()
    except (OSError, ValueError):
        findings.append("the forced-exit surfaced-set is unreadable: cannot-evaluate, held for manual "
                        "triage")
        return findings  # never re-surface blindly against an unreadable set
    fresh = [r for r in rows if r.get("key") not in surfaced]
    for r in fresh:
        ids = r.get("open_ids") if isinstance(r.get("open_ids"), list) else []
        findings.append("a prior exit was forced past open work (forced_unresolved at {}: {} open "
                        "id(s) {}); triage before continuing".format(
                            r.get("ts", "unknown"), len(ids),
                            ", ".join(str(i) for i in ids[:10]) or "unrecorded"))
    if fresh:
        all_keys = sorted({r.get("key") for r in rows if isinstance(r.get("key"), str)})
        _orch_write_json_atomic(surfaced_path, {"keys": all_keys})  # at-least-once: a failed advance re-fires
    return findings


def _orch_pending_artefact_findings(root):
    """C.1/C.4 resume probes. escape-spoof.json is a single-shot artefact: raised once and renamed with
    a .surfaced suffix, staying in the record; an unreadable one re-fires (chkfcl). Forced exits are an
    append-only log surfaced via _orch_forced_exit_findings so multiple exits are each raised exactly
    once and never clobbered."""
    findings = []
    sd = _orch_state_dir_for_root(root)
    path = os.path.join(sd, "escape-spoof.json")
    try:
        if os.path.lexists(path):
            with open(path, "r", encoding="utf-8") as fh:
                rec = json.load(fh)
            rec = rec if isinstance(rec, dict) else {}
            findings.append("an actor-owned or malformed escape sentinel was ignored at {} ({})"
                            .format(rec.get("ts", "unknown"),
                                    rec.get("detail") or "no detail recorded"))
            try:
                os.replace(path, path + ".surfaced")
            except OSError:
                pass  # it will surface again next resume; never wedge SessionStart
    except (OSError, ValueError):
        findings.append("pending escape-spoof.json record present but unreadable: cannot-evaluate, "
                        "held for manual triage")
    findings.extend(_orch_forced_exit_findings(sd))
    return findings


def orch_resume_audit(data):
    """sesres/recncl/cnclse, SessionStart (warn: the platform cannot block this event): reconcile the
    durable record against observed reality and ARM the resume barrier on divergence; a clean audit
    clears it. Registry-scoped; silent with no registry."""
    root = _orch_root(data)
    if root is None:
        return _allow()
    status, reg = _orch_registry(root)
    if status == "absent":
        return _allow()
    barrier_path = os.path.join(_orch_state_dir_for_root(root), "resume-barrier.json")
    if status == "bad":
        _orch_append_jsonl(barrier_path + ".unused", {})  # no-op path probe; keep posture simple
        findings = ["the orchestration registry could not be read ({})".format(reg)]
    else:
        findings = _orch_resume_probes(reg, root)
    try:
        os.makedirs(os.path.dirname(barrier_path), exist_ok=True)
        with open(barrier_path, "w", encoding="utf-8") as fh:
            json.dump({"active": bool(findings), "findings": findings,
                       "ts": _orch_now().isoformat(), "warned": False}, fh)
    except OSError:
        pass  # a barrier that cannot arm still surfaces below; never wedge SessionStart
    if findings:
        _orch_guard_event(root, "resume-audit", "findings", "; ".join(findings)[:1000])
        return _stop_warn("AIQT guardrail (resume audit): the recorded state diverges from "
                          "observed reality: {}. Correct the record, then re-run "
                          "'python3 tools/orch_doctor.py --resume-audit' to clear the barrier; "
                          "acknowledgement alone does not clear it.".format("; ".join(findings)))
    return _allow()


def orch_resume_barrier(data):
    """sesres/recncl, PreToolUse (stage BAKE: warn-first, blocks nothing yet): while the barrier is
    armed, surface the first mutation outside the allowlist. The record surfaces, the registry files,
    and the suite's own state directory stay writable, so the only exit, correcting the record, is
    never obstructed."""
    root = _orch_root(data)
    if root is None:
        return _allow()
    status, reg = _orch_registry(root)
    if status != "ok":
        return _allow()
    sd = _orch_state_dir_for_root(root)
    barrier_path = os.path.join(sd, "resume-barrier.json")
    try:
        with open(barrier_path, "r", encoding="utf-8") as fh:
            barrier = json.load(fh)
    except (OSError, ValueError):
        return _allow()
    if not isinstance(barrier, dict) or not barrier.get("active"):
        return _allow()
    tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    file_path = tool_input.get("file_path")
    if isinstance(file_path, str) and file_path:
        allow_prefixes = [sd]
        rec = reg.get("record") if isinstance(reg.get("record"), dict) else {}
        for key in ("findings", "pending_decisions", "handoff"):
            p = _orch_path(root, rec.get(key))
            if p:
                allow_prefixes.append(p)
        for rel in _ORCH_REGISTRY_FILES:
            allow_prefixes.append(os.path.join(root, *rel.split("/")))
        target = os.path.realpath(file_path)
        for p in allow_prefixes:
            rp = os.path.realpath(p)
            if target == rp or target.startswith(rp.rstrip(os.sep) + os.sep):
                return _allow()  # the exit path (fixing the record) is always writable
    if barrier.get("warned"):
        return _allow()  # surface once per arming, never a nag wall
    barrier["warned"] = True
    try:
        with open(barrier_path, "w", encoding="utf-8") as fh:
            json.dump(barrier, fh)
    except OSError:
        pass
    return (0, {"systemMessage": (
        "AIQT guardrail (resume barrier, BAKE posture: surfacing, not blocking): the resume "
        "audit found divergence ({}) and this mutation is outside the record surfaces. Correct the "
        "record first, then clear the barrier with 'python3 tools/orch_doctor.py --resume-audit'."
        .format("; ".join(barrier.get("findings") or [])[:500]))}, None)


# --- write-scope guard (EN-8, wrtscp) ----------------------------------------------------------------
# Confine the sole orchestrator's guarded-tool writes to a harness-set per-slice scope declaration, and
# hard-deny writes to frozen paths and to other repositories as a floor the declaration cannot lower.
# It reuses the orchestration substrate (_state_dir_from_registry for the registry-declared state_dir the
# declaration lives at, resolved from a single validated registry read, _orch_guard_event for the over-fire
# metric), the scrubbed git primitive
# (_recovery_toplevel), and the
# gensrc containment/loader idiom (_gensrc_within, the lstat->S_ISREG->byte-bound->UTF-8->JSON taxonomy).
# TWO arming inputs, each fail-open on ABSENCE only: the per-slice declaration (slice confinement) and the
# committed frozen floor (frozen denial). The structural other-repo/nested-repo denial applies to every
# covered write whose repository root resolves (a covered write whose root cannot be resolved is DENIED, not
# allowed); the frozen-floor denial fires whenever a floor is present, and an armed session additionally
# requires one, so an un-armed session with a genuinely-absent floor is inert there. Only slice confinement
# is fail-open on a missing declaration. Once armed, every cannot-evaluate resolves to DENY. See the
# write-scope residue in .aiqt/core/hooks/manifest.toml.
_WRTSCP_TOOLS = ("Write", "Edit", "MultiEdit")   # same matcher as gensrc_guard; MultiEdit carries one file_path
_WRTSCP_DECL_REL = "write-scope.json"            # under the registry-declared <state_dir> (harness-set, per
                                                 # slice; out of the slice tree by default, possibly in-tree)
_WRTSCP_FLOOR_REL = os.path.join(".aiqt", "frozen.json")  # in-tree committed floor (gen_manifest-generated)
_WRTSCP_VERSION = 1
_WRTSCP_MAX_BYTES = 64 * 1024                    # 64 KB: both artifacts are small; a larger one is malformed


def _wrtscp_parse_entry(raw):
    """Validate one path/tree entry in the shared floor/declaration grammar and return (kind, body) with
    kind 'file'|'tree' and body the entry minus any trailing '/', or None if malformed. The grammar mirrors
    the gensrc target grammar so the same containment reasoning applies: a repo-root-relative POSIX string;
    a trailing '/' marks a tree, otherwise an exact file; NO absolute path, backslash, empty/'.'/'..'
    component, control character, or wildcard (fnmatch ambiguity is rejected, per the EN-8 plan). Because
    an entry can carry no '..' component and is never absolute, it can never point outside the repo root it
    is joined onto (the 'pointing outside the repo' half of row 19 is enforced here, by construction)."""
    if not isinstance(raw, str) or not raw:
        return None
    if "\\" in raw or _is_absolute(raw):
        return None
    if any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in raw):
        return None
    if any(ch in raw for ch in ("*", "?", "[")):
        return None
    is_tree = raw.endswith("/")
    body = raw[:-1] if is_tree else raw
    if not body or any(seg in ("", ".", "..") for seg in body.split("/")):
        return None
    return ("tree" if is_tree else "file", body)


def _wrtscp_read_json_artifact(path, max_bytes):
    """The shared lstat-before-open / S_ISREG / byte-bounded / strict-UTF-8 / strict-JSON reader for BOTH
    the out-of-tree declaration and the in-tree floor, in the _load_gensrc_registry idiom. Returns
    ('absent', None), ('bad', detail), or ('ok', obj). ABSENT is ONLY a clean lstat FileNotFoundError;
    EVERY other fault is BAD, never absent, so an unreadable input can never read as no-coverage
    (integ-check-fails-closed-on-unreadable): a non-regular file (symlink/FIFO/directory/device), a
    stat/read error, an oversize file (byte-bounded), a non-UTF-8 decode, malformed JSON, or a non-object.
    A delete race in the lstat->open window fails safe to BAD. Read AT DECISION TIME, never cached."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return ("absent", None)
    except OSError as exc:
        return ("bad", "could not be stat'd ({})".format(exc))
    if not stat.S_ISREG(st.st_mode):
        return ("bad", "is not a regular file (a symlink, FIFO, directory, ...)")
    try:
        with open(path, "rb") as handle:
            raw_bytes = handle.read(max_bytes + 1)
    except FileNotFoundError:
        return ("bad", "disappeared during the read (a concurrent change); failing safe")
    except OSError as exc:
        return ("bad", "could not be read ({})".format(exc))
    if len(raw_bytes) > max_bytes:
        return ("bad", "exceeds the {}-byte bound".format(max_bytes))
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return ("bad", "is not valid UTF-8")
    try:
        obj = json.loads(raw)
    except ValueError:
        return ("bad", "is malformed JSON")
    if not isinstance(obj, dict):
        return ("bad", "is not a JSON object")
    return ("ok", obj)


def _load_write_scope(root):
    """Read <state_dir>/write-scope.json AT DECISION TIME (the harness-set per-slice declaration; it lives
    at the orchestration registry's declared state_dir, out of the slice tree BY DEFAULT but MAY be in-tree
    when the registry declares an in-tree state_dir, so the out-of-tree placement is a harness convention,
    not a guarantee) and return ('absent', None), ('bad', detail), or ('ok', {slice, worktree_root, allow}).
    `allow` is the parsed list of (kind, body) entries (possibly empty; an empty allow list is valid and
    means every covered in-repo write is out of scope). The version pin excludes JSON `true` (type(v) is
    int, not `== 1`, because True == 1 in Python). worktree_root is validated as a non-empty string here; its
    equality with the hook's own canonicalized root is checked in the handler (a stale/copied declaration is
    BAD there). ABSENT is the fail-open state (no slice confinement); every present-but-unreadable outcome is
    BAD. The registry that LOCATES the declaration is itself part of this read: a 'bad' (unreadable or
    malformed) registry is a cannot-evaluate returned as BAD here (fail-closed), never a silent XDG-default
    fallback that would report the declaration absent and DISARM confinement; likewise a registry that is
    'ok' but declares a PRESENT-but-malformed state_dir (a non-string or empty value, which _orch_path
    resolves to None) is BAD, while an ABSENT state_dir key legitimately selects the XDG default and stays
    allowed. The declaration directory is resolved from THIS validated registry result via the pure
    _state_dir_from_registry helper, so _load_write_scope performs exactly ONE registry read and never a
    second, independently-faulting one that could disarm the session; _orch_state_dir_for_root reads once and
    delegates to the same helper for its own other callers."""
    reg_status, reg = _orch_registry(root)
    if reg_status == "bad":
        return ("bad", "{}: the orchestration registry that locates the write-scope declaration is "
                       "unreadable or malformed, a cannot-evaluate that denies rather than silently "
                       "disarming confinement".format(reg))
    if reg_status == "ok" and isinstance(reg, dict) and "state_dir" in reg \
            and _orch_path(root, reg.get("state_dir")) is None:
        # A PRESENT state_dir key whose value is non-string or empty is a cannot-evaluate: the old code
        # returned None from _orch_path and silently fell back to the XDG default, disarming an armed
        # session. (An ABSENT state_dir key legitimately means "use the XDG default" and is not this case.)
        return ("bad", "the orchestration registry declares a malformed state_dir; a cannot-evaluate "
                       "denies rather than disarming confinement")
    # Resolve the declaration directory from the registry result WE ALREADY VALIDATED above, via the pure
    # helper: never re-read the registry here. A second read can fault independently (e.g. EACCES between the
    # two reads) and silently fall back to XDG, disarming the session (the TOCTOU fail-open). This keeps the
    # _orch_registry call above the ONE and only registry read performed by _load_write_scope.
    state_dir = _state_dir_from_registry(root, reg if reg_status == "ok" else None)
    path = os.path.join(state_dir, _WRTSCP_DECL_REL)
    status, obj = _wrtscp_read_json_artifact(path, _WRTSCP_MAX_BYTES)
    if status == "absent":
        return ("absent", None)
    if status == "bad":
        return ("bad", "the write-scope declaration {}".format(obj))
    version = obj.get("version")
    if type(version) is not int or version != _WRTSCP_VERSION:
        return ("bad", "the write-scope declaration has an unknown version (expected {})"
                       .format(_WRTSCP_VERSION))
    slice_name = obj.get("slice")
    if not isinstance(slice_name, str) or not slice_name:
        return ("bad", "the write-scope declaration carries no readable slice")
    worktree_root = obj.get("worktree_root")
    if not isinstance(worktree_root, str) or not worktree_root:
        return ("bad", "the write-scope declaration carries no readable worktree_root")
    allow_raw = obj.get("allow")
    if not isinstance(allow_raw, list):
        return ("bad", "the write-scope declaration carries no allow list")
    allow = []
    for item in allow_raw:
        entry = _wrtscp_parse_entry(item)
        if entry is None:
            return ("bad", "the write-scope declaration has a malformed allow entry")
        allow.append(entry)
    return ("ok", {"slice": slice_name, "worktree_root": worktree_root, "allow": allow})


def _load_frozen_floor(root):
    """Read <root>/.aiqt/frozen.json AT DECISION TIME (the committed, drift-gated floor generated by
    tools/gen_manifest.py from the ownership classification: the frozen class set {derived, manifest-self,
    archive}) and return ('absent', None), ('bad', detail), or ('ok', entries) where entries is the parsed
    list of (kind, body). An EMPTY frozen list is valid (an adopter with nothing frozen). ABSENT means no
    floor is declared (the frozen layer is inert un-armed; an armed session denies, so a Bash-deleted floor
    cannot silently downgrade an armed session); every present-but-unreadable outcome is BAD."""
    path = os.path.join(root, _WRTSCP_FLOOR_REL)
    status, obj = _wrtscp_read_json_artifact(path, _WRTSCP_MAX_BYTES)
    if status == "absent":
        return ("absent", None)
    if status == "bad":
        return ("bad", "the frozen floor {}".format(obj))
    version = obj.get("version")
    if type(version) is not int or version != _WRTSCP_VERSION:
        return ("bad", "the frozen floor has an unknown version (expected {})".format(_WRTSCP_VERSION))
    frozen_raw = obj.get("frozen")
    if not isinstance(frozen_raw, list):
        return ("bad", "the frozen floor carries no frozen list")
    frozen = []
    for item in frozen_raw:
        entry = _wrtscp_parse_entry(item)
        if entry is None:
            return ("bad", "the frozen floor has a malformed entry")
        frozen.append(entry)
    return ("ok", frozen)


def _wrtscp_target_matches(entries, target, root_c):
    """Whether the already-realpath'd absolute `target` matches any (kind, body) entry, joining each entry
    onto root_c and canonicalizing (the gensrc_match idiom). Returns True (matched), False (proven
    no-match), or None (a resolution/containment fault, so no-match cannot be proven; the caller fails
    closed when armed). A file entry matches on realpath equality; a tree entry matches when target is the
    tree root or lies under it by component-boundary containment (_gensrc_within), never a string prefix."""
    for kind, body in entries:
        try:
            entry_c = os.path.realpath(os.path.join(root_c, body))
        except (OSError, ValueError):
            return None
        if kind == "file":
            if entry_c == target:
                return True
        else:
            verdict = _gensrc_within(target, entry_c)
            if verdict == "err":
                return None
            if verdict == "in":
                return True
    return False


def _wrtscp_entry_wholly_frozen(kind, body, floor):
    """Whether a declaration allow entry (kind, body) is EQUAL TO or WHOLLY INSIDE some floor entry, judged
    by component-boundary containment on the DECLARED repo-relative bodies (a declaration-vs-declaration
    consistency check, no filesystem). Such an allow entry can never grant anything (everything it covers is
    frozen), so it makes the declaration malformed (row 19). A floor FILE wholly contains only an identical
    file; a floor TREE T wholly contains any entry whose body equals T or lies under it. An allow tree that
    merely CONTAINS a frozen subtree (allow '.aiqt/' over frozen '.aiqt/core/') is NOT wholly frozen and is
    legal; row 18 still denies the frozen targets inside it at write time."""
    for f_kind, f_body in floor:
        if f_kind == "file":
            if kind == "file" and body == f_body:
                return True
        else:
            if body == f_body or body.startswith(f_body + "/"):
                return True
    return False


def _wrtscp_nearest_existing_dir(target):
    """The nearest EXISTING ancestor directory of an absolute target path (target itself may be a new file
    in a not-yet-existing directory), or None if none resolves. Walks up to the filesystem root."""
    d = os.path.dirname(target)
    while True:
        try:
            if os.path.isdir(d):
                return d
        except OSError:
            return None
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _wrtscp_nested_repo(target, root_c):
    """True when the target sits in a NESTED or FOREIGN git repository under or beside the session root,
    False when it is the same repo, None on a resolution fault. Resolves the SCRUBBED git toplevel of the
    target's nearest existing ancestor directory (_recovery_toplevel, every ambient GIT_* removed) and
    compares it to root_c: a different toplevel is a nested/foreign repo (denied). This carries the
    grc_library_ref case and any absolute path escaping into a sibling checkout, generically."""
    anchor = _wrtscp_nearest_existing_dir(target)
    if anchor is None:
        return None
    top = _recovery_toplevel(anchor)
    if top is None:
        return None
    try:
        return os.path.realpath(top) != root_c
    except (OSError, ValueError):
        return None


def _wrtscp_deny(root, detail, reason, banner):
    """A write-scope DENY that also makes a BEST-EFFORT guard-events append (the over-fire metric) when root
    is resolvable. The append is best-effort: _orch_guard_event may return False and this ignores it, so a
    failed append neither blocks nor alters the denial and the over-fire metric may be lost for that event."""
    if root is not None:
        _orch_guard_event(root, "wrtscp", "deny", detail)
    return _deny("AIQT rule wrtscp (write-scope): {}".format(reason),
                 "AIQT guardrail: {} (rule wrtscp).".format(banner))


def write_scope_guard(data):
    """wrtscp (write-scope), PreToolUse on Write|Edit|MultiEdit (EN-8): confine the sole orchestrator's
    guarded-tool writes to a harness-set per-slice scope declaration, and hard-deny writes to frozen paths
    and to other repositories as a floor the declaration cannot lower. It enforces septsk
    (separate-task-changes) as the pre-write realization of keeping unrelated work out of the slice change
    set, wowo01 (workers-produce-inert-data) as the apply-stage discipline over the sole writer, and exetgt
    (confirm-execution-target): the other-repo denial is its mechanical form for writes.

    TWO arming inputs, each fail-open on ABSENCE only. The per-slice declaration
    <state_dir>/write-scope.json (at the registry-declared state_dir, out of the slice tree by default) arms
    SLICE CONFINEMENT (absent -> un-armed, inert confinement; present -> armed, every uncertainty denies).
    The in-tree committed frozen floor .aiqt/frozen.json arms the FROZEN layer (absent -> the frozen layer is
    inert un-armed; present -> the floor is enforced). The structural other-repo/nested-repo denial applies
    to every covered write whose repository root resolves, and a covered write whose root CANNOT be resolved
    is denied (fail-closed), not allowed. The root is resolved FIRST, so this unresolvable-root denial
    precedes any relative-path handling (a non-git relative-path write denies, it does not defer); only once
    the root resolves does an un-armed relative path defer to the sibling absolute_paths hook. The
    frozen-floor denial fires whenever a floor is PRESENT, and an
    armed session additionally REQUIRES a floor (an armed session with a genuinely-absent floor denies); only
    an un-armed session with a genuinely-absent floor leaves the frozen layer inert, so the frozen denial is
    not unconditionally always-on. Slice confinement is fail-open on a missing declaration; the principled
    fail-open is genuine ABSENCE (of a declaration or floor: no confinement in effect, the same inert
    boundary gensrc and the orchestration suite use). A cannot-evaluate FAULT is not absence: a resolution
    or probe ERROR (an unresolvable session root, a root or target canonicalization fault, a containment
    fault, or a nested-repo probe fault) on a covered write DENIES whether or not the session is armed, and
    never allows an unverified write; and once armed every cannot-evaluate resolves to DENY. Out-of-scope is a DENY, never an ASK:
    an ASK would hand the confined actor the click-through on its own confinement and would wedge an
    unattended run; the remedy is the harness re-declaring the slice. The declaration is machine-set inert
    data, never authored by the assistant through a guarded tool; the residual Bash-write path to the state
    dir is defence in depth, not categorical (disclosed below).

    RESIDUAL (disclose-guard-residuals): a PATH guard, not a content judge; it decides where a write lands,
    never what it writes. Covers only PreToolUse Write/Edit/MultiEdit carrying a readable file_path.
    Bash-mediated writes (redirects, sed -i, cp, mv, tee, an editor launched in Bash), NotebookEdit,
    filesystem MCP tools, and any write outside the platform's hook path are NOT caught; the committed frozen
    floor .aiqt/frozen.json is a generated, drift-gated output backstopped at merge by the manifest-gen-drift
    gate (tools/gen_manifest.py --check), the gensrc-registry-drift gate (tools/gen_gensrc.py --check), and
    the independent manifest-integrity verifier (tools/check_manifest.py), but nothing backstops an
    uncommitted, out-of-scope-mutable, or cross-repository write through those channels. The declaration is
    machine-local and session-scoped (CI cannot observe it). Realpath closes symlink escapes present at check
    time but not a post-check swap, hard-link alias, or bind-mount change (TOCTOU); an OS-level write sandbox
    is the stronger overlapping control. The floor is enforced against the manifest CLASS set {derived,
    manifest-self, archive}. That floor's RUNTIME value is un-lowerable by the constrained actor through the
    guarded tools (a guarded Write/Edit/MultiEdit to .aiqt/frozen.json is itself on the floor and denied);
    but its DEFINITION (FROZEN_CLASSES in tools/gen_manifest.py) is generator source that lands through
    pull-request review PLUS the drift gate, which detects an INCONSISTENT floor (a committed frozen.json
    that does not match a fresh regeneration), NOT an unauthorized-but-internally-consistent redefinition of
    the class set followed by regeneration. An independent floor-authorization mechanism is out of this
    hook's scope. The floor proves membership in its declared selector set only, not that the generation-time
    class mapping is semantically complete."""
    if data.get("hook_event_name") != PRETOOL:
        return _hard_block("aiqt_hooks: write_scope_guard wired to unexpected event {!r}; failing closed"
                           .format(data.get("hook_event_name")))
    tool_name = data.get("tool_name")
    if tool_name is None:
        return _deny_missing_tool_name("wrtscp")             # row 3: the only deny with no root context
    if not isinstance(tool_name, str) or not tool_name:
        # A malformed tool_name is a malformed call; it cannot be matched, and it is not a legitimate write
        # in either regime. DENY (fail-closed), never a silent allow. (No root yet: no guard-events row.)
        return _wrtscp_deny(None, "malformed tool_name",
                            "the PreToolUse payload carried no readable tool_name, so the call cannot be "
                            "matched; a malformed guarded-tool call is not a legitimate write",
                            "denied a guarded-tool call with an unreadable tool_name")
    if tool_name not in _WRTSCP_TOOLS:
        return _allow()                                      # row 1: out of matcher (defensive)
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return _wrtscp_deny(None, "unreadable tool_input",
                            "the {} payload carried no readable tool_input, so the write target cannot be "
                            "determined; a malformed write is not legitimate in either regime"
                            .format(tool_name),
                            "denied a {} with an unreadable tool_input".format(tool_name))  # row 4
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return _wrtscp_deny(None, "missing file_path",
                            "the {} payload carried no readable file_path, so the write target cannot be "
                            "determined; a malformed write is not legitimate in either regime"
                            .format(tool_name),
                            "denied a {} with no readable file_path".format(tool_name))     # row 4
    if any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in file_path):
        return _wrtscp_deny(None, "control-char file_path",
                            "the {} payload file_path contains a control character (malformed input)"
                            .format(tool_name),
                            "denied a {} whose file_path carried a control character".format(tool_name))
    cwd = data.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        # A covered write whose session cwd is missing or unreadable has no resolvable repository root, so
        # containment cannot be evaluated at all; a covered write that cannot be cleared is DENIED
        # (fail-closed), never the old inert allow that let an unlocatable-root write through (row 5).
        return _wrtscp_deny(None, "unresolvable session root (no cwd)",
                            "the {} payload carried no readable cwd, so the session repository root cannot "
                            "be resolved and the write cannot be cleared for containment; a covered write "
                            "whose scope cannot be evaluated is denied".format(tool_name),
                            "denied a {} (session root unresolvable, no cwd)".format(tool_name))  # row 5
    # The scrubbed rev-parse primitive (every ambient GIT_* removed), so an ambient decoy repo cannot
    # redirect the reads; None means a non-git session, whose repository root is unresolvable, so a covered
    # write cannot be cleared for containment and is DENIED (fail-closed) rather than allowed.
    root = _recovery_toplevel(cwd)
    if root is None:
        return _wrtscp_deny(None, "unresolvable session root (non-git)",
                            "the {} session is not in a resolvable git repository, so the session repository "
                            "root cannot be resolved and the write cannot be cleared for containment; a "
                            "covered write whose scope cannot be evaluated is denied".format(tool_name),
                            "denied a {} (session root unresolvable, non-git)".format(tool_name))  # row 5
    decl_status, decl = _load_write_scope(root)
    armed = decl_status != "absent"
    try:
        root_c = os.path.realpath(root)
    except (OSError, ValueError):
        if armed:
            return _wrtscp_deny(root, "root canonicalization fault",
                                "the session repo root could not be canonicalized, so the write cannot be "
                                "cleared against the armed slice", "denied a {} (unresolvable repo root, "
                                "armed)".format(tool_name))                                  # row 15
        return _wrtscp_deny(root, "root canonicalization fault (cannot-evaluate)",
                            "the session repo root could not be canonicalized, so the write target's "
                            "containment could not be proven; a cannot-evaluate denies rather than allowing "
                            "an unverified write",
                            "denied a {} (repo root canonicalization fault)".format(tool_name))  # row 11 (fault -> deny)
    if not _is_absolute(file_path):
        # A relative file_path can only arrive via MultiEdit (abs-paths covers the rest). Un-armed EN-8
        # makes no cwd-trusting determination (the sibling absolute_paths hook owns the relative case);
        # armed, a target that cannot be pinned absolutely is a cannot-evaluate.
        if armed:
            return _wrtscp_deny(root, "relative file_path (armed)",
                                "the {} file_path is relative, so the write target cannot be pinned against "
                                "the armed slice; supply an absolute path".format(tool_name),
                                "denied a {} with a relative file_path (armed)".format(tool_name))  # row 14
        return _allow()                                                                     # row 6
    try:
        target = os.path.realpath(file_path)
    except (OSError, ValueError):
        if armed:
            return _wrtscp_deny(root, "target canonicalization fault",
                                "the {} target path could not be canonicalized, so it cannot be cleared "
                                "against the armed slice".format(tool_name),
                                "denied a {} (unresolvable target, armed)".format(tool_name))  # row 15
        return _wrtscp_deny(root, "target canonicalization fault (cannot-evaluate)",
                            "the {} target path could not be canonicalized, so its containment could not be "
                            "proven; a cannot-evaluate denies rather than allowing an unverified write"
                            .format(tool_name),
                            "denied a {} (target canonicalization fault)".format(tool_name))  # row 11 (fault -> deny)
    if armed and decl_status == "bad":
        return _wrtscp_deny(root, "declaration bad",
                            "{}; an armed session cannot clear a write against an unreadable declaration "
                            "(distinct from an absent one, which is inert)".format(decl),
                            "denied a {} because the write-scope declaration could not be read"
                            .format(tool_name))                                              # row 13
    if armed:  # decl_status == "ok": bind the declaration to THIS tree (a stale/copied/moved decl is BAD)
        try:
            decl_root_c = os.path.realpath(decl["worktree_root"])
        except (OSError, ValueError):
            decl_root_c = None
        if decl_root_c != root_c:
            return _wrtscp_deny(root, "worktree_root mismatch",
                                "the write-scope declaration's worktree_root does not resolve to this repo "
                                "(a stale, copied, or moved declaration), so it cannot confine this tree",
                                "denied a {} (declaration worktree_root mismatch)".format(tool_name))  # row 13
    # --- Structural other-repo / nested-repo denial, in BOTH regimes once the root resolves (rows 7, 16) ---
    within = _gensrc_within(target, root_c)
    if within == "err":
        if armed:
            return _wrtscp_deny(root, "containment fault",
                                "the write target's containment against this repo could not be resolved, so "
                                "it cannot be cleared against the armed slice",
                                "denied a {} (containment fault, armed)".format(tool_name))  # row 15
        return _wrtscp_deny(root, "containment fault (cannot-evaluate)",
                            "the write target's containment against this repo could not be resolved, so a "
                            "no-match could not be proven; a cannot-evaluate denies rather than allowing an "
                            "unverified write",
                            "denied a {} (containment fault)".format(tool_name))  # row 11 (fault -> deny)
    slice_name = decl["slice"] if armed else None
    if within == "out":
        return _wrtscp_deny(root, "outside toplevel",
                            "the write target resolves OUTSIDE this repository ({}); a guarded-tool write "
                            "landing outside the session repo is an aiming error and is denied as a floor "
                            "the scope declaration cannot lower. Run the write from a session rooted in the "
                            "target repo.".format(target),
                            "denied a {} to a target outside this repository".format(tool_name))  # rows 7/16
    nested = _wrtscp_nested_repo(target, root_c)
    if nested is None:
        if armed:
            return _wrtscp_deny(root, "nested-repo probe fault",
                                "the write target's repository could not be resolved, so it cannot be "
                                "cleared against the armed slice",
                                "denied a {} (nested-repo probe fault, armed)".format(tool_name))  # row 15
        return _wrtscp_deny(root, "nested-repo probe fault (cannot-evaluate)",
                            "the write target's repository could not be resolved, so it could not be proven "
                            "the target is not in a nested or foreign repository; a cannot-evaluate denies "
                            "rather than allowing an unverified write",
                            "denied a {} (nested-repo probe fault)".format(tool_name))  # row 11 (fault -> deny)
    if nested:
        return _wrtscp_deny(root, "nested/foreign repo",
                            "the write target sits in a NESTED or FOREIGN git repository under or beside "
                            "this repo ({}); it is denied as a floor the scope declaration cannot lower. "
                            "Run the write from a session rooted in that repo.".format(target),
                            "denied a {} to a nested or foreign repository".format(tool_name))  # rows 7/16
    # --- Frozen-floor denial (rows 8, 9, 10, 17, 18): fires whenever a floor is PRESENT, and an armed
    # session additionally requires one; only an un-armed session with a genuinely-absent floor is inert ---
    floor_status, floor = _load_frozen_floor(root)
    if floor_status == "bad":
        return _wrtscp_deny(root, "floor bad",
                            "{}; a present-but-unreadable floor is a cannot-evaluate and denies (an absent "
                            "floor is inert un-armed)".format(floor),
                            "denied a {} because the frozen floor could not be read".format(tool_name))  # rows 9/17
    if floor_status == "absent":
        if armed:
            return _wrtscp_deny(root, "floor absent (armed)",
                                "an armed session requires a committed frozen floor (.aiqt/frozen.json; an "
                                "explicit empty list is valid), so a deleted floor cannot silently downgrade "
                                "an armed session",
                                "denied a {} because an armed session has no frozen floor".format(tool_name))  # row 17
        # Un-armed with no floor: the frozen layer is inert; the structural denial already applied.
        # (Fall through to the un-armed ALLOW below, row 10 -> row 12.)
        floor = []
    else:
        on_floor = _wrtscp_target_matches(floor, target, root_c)
        if on_floor is None:
            return _wrtscp_deny(root, "floor containment fault",
                                "a frozen-floor entry could not be resolved for containment, so a "
                                "no-match cannot be proven",
                                "denied a {} (floor containment fault)".format(tool_name))   # rows 9/17 (fault)
        if on_floor:
            return _wrtscp_deny(root, "frozen target",
                                "the write target is on the frozen floor ({}): a generated output or frozen "
                                "rotation data, never hand-written through a guarded tool. The floor outranks "
                                "the scope declaration (deny over allow); edit the source and regenerate."
                                .format(target),
                                "denied a {} to a frozen path".format(tool_name))            # rows 8/18
    if not armed:
        return _allow()  # row 12: un-armed, structural cleared, not frozen -> no slice confinement in effect
    # --- ARMED slice confinement (rows 19, 20, 21) ---
    allow = decl["allow"]
    for kind, body in allow:
        if _wrtscp_entry_wholly_frozen(kind, body, floor):
            return _wrtscp_deny(root, "allow entry declares past the floor",
                                "the write-scope declaration for slice {!r} carries an allow entry that is "
                                "wholly on the frozen floor; a declaration cannot declare past the floor and "
                                "is surfaced as malformed rather than partially honoured".format(slice_name),
                                "denied a {} (declaration for slice {!r} declares past the frozen floor)"
                                .format(tool_name, slice_name))                              # row 19
    in_scope = _wrtscp_target_matches(allow, target, root_c)
    if in_scope is None:
        return _wrtscp_deny(root, "allow containment fault",
                            "an allow entry could not be resolved for containment, so in-scope cannot be "
                            "proven for slice {!r}".format(slice_name),
                            "denied a {} (allow containment fault, slice {!r})".format(tool_name, slice_name))  # row 15
    if in_scope:
        return _allow()  # row 20: in repo, not frozen, in the declared slice scope -> silent allow
    return _wrtscp_deny(root, "out of scope",
                        "the write target {} is not in the declared scope for slice {!r}. This slice's "
                        "writes are confined to its declaration; re-declare the slice through the harness to "
                        "widen scope (widening stays on the harness side, never a guarded-tool call)."
                        .format(target, slice_name),
                        "denied a {} outside the declared scope for slice {!r}"
                        .format(tool_name, slice_name))                                      # row 21


# --- dispatcher ---------------------------------------------------------------------------------------
HANDLERS = {
    "diff_wall_stop": diff_wall_stop,
    "diff_source_pretool": diff_source_pretool,
    "commit_identity": commit_identity,
    "absolute_paths": absolute_paths,
    "bash_absolute_paths": bash_absolute_paths,
    "git_discard": git_discard,
    "protected_line": protected_line,
    "branch_root": branch_root,
    "gate_weakening": gate_weakening,
    "commit_msg_subst": commit_msg_subst,
    "secrets_shift_left": secrets_shift_left,
    "gensrc_guard": gensrc_guard,
    "write_scope_guard": write_scope_guard,
    "orch_stop_guard": orch_stop_guard,
    "orch_teammate_idle": orch_teammate_idle,
    "orch_yield_tool": orch_yield_tool,
    "orch_ask_guard": orch_ask_guard,
    "orch_truncation_guard": orch_truncation_guard,
    "orch_dispatch_ledger": orch_dispatch_ledger,
    "orch_prompt_stamp": orch_prompt_stamp,
    "orch_resume_audit": orch_resume_audit,
    "orch_resume_barrier": orch_resume_barrier,
}

# Handler -> event class, so the dispatcher can decide its ERROR posture from the argv MODE alone,
# without reading the (possibly unreadable) payload. This is the load-bearing half of the fail-closed
# design: a Stop/SubagentStop handler must NEVER exit 2 ON AN ERROR PATH, because a hard Stop block could
# re-fire on the forced continuation and wedge the session (no stop_hook_active field, no documented loop
# bound), so on ANY error (unreadable stdin, JSON parse failure, non-dict payload, or a handler crash) it
# emits a non-blocking systemMessage warning and exits 0. A DELIBERATE backlog-deny is the intended
# exception (the documented Stop block mechanism, bounded by the loop cap); only a PreToolUse handler
# fails closed via exit 2 on error.
HANDLER_EVENT = {
    "diff_wall_stop": "Stop",
    "diff_source_pretool": PRETOOL,
    "commit_identity": PRETOOL,
    "absolute_paths": PRETOOL,
    "bash_absolute_paths": PRETOOL,
    "git_discard": PRETOOL,
    "protected_line": PRETOOL,
    "branch_root": PRETOOL,
    "gate_weakening": PRETOOL,
    "commit_msg_subst": PRETOOL,
    "secrets_shift_left": PRETOOL,
    "gensrc_guard": PRETOOL,
    "write_scope_guard": PRETOOL,
    "orch_stop_guard": "Stop",
    "orch_teammate_idle": "TeammateIdle",
    "orch_yield_tool": PRETOOL,
    "orch_ask_guard": PRETOOL,
    "orch_truncation_guard": PRETOOL,
    "orch_dispatch_ledger": "PostToolUse",
    "orch_prompt_stamp": "UserPromptSubmit",
    "orch_resume_audit": "SessionStart",
    "orch_resume_barrier": PRETOOL,
}


def _dispatcher_fail_open_warn(handler_name, detail):
    """A fail-open dispatcher-level error for a Stop/SubagentStop/SessionStart/TeammateIdle/
    UserPromptSubmit/PostToolUse handler: a non-blocking systemMessage on exit 0, so no error on
    these paths can wedge a session, trap a teammate, or block a human prompt."""
    return {"systemMessage": (
        "AIQT guardrail: the {} check could not run ({}); surfacing a warning rather than blocking "
        "(non-blocking by design on this event).".format(handler_name, detail))}


def main(argv):
    # The MODE (argv[0]) alone decides the error posture, never the payload (which may be unreadable).
    # A genuinely unknown mode is not identifiable as Stop and is a broken install, so it fails closed
    # via exit 2. But a KNOWN handler invoked with the wrong argv count must NOT reach exit 2 when it is
    # a Stop/SubagentStop handler: a hard exit-2 Stop path could re-fire on the forced continuation and
    # wedge the session (no stop_hook_active field, no documented loop bound), so a bad-argv Stop
    # invocation WARNS on exit 0 like every other Stop error path (FIX 2). A bad-argv PreToolUse handler
    # still fails closed (exit 2).
    mode = argv[0] if argv else None
    if mode not in HANDLERS:
        print("aiqt_hooks: usage: aiqt_hooks.py <{}>".format("|".join(sorted(HANDLERS))),
              file=sys.stderr)
        return 2
    handler_name = mode
    is_fail_open = HANDLER_EVENT[handler_name] in FAIL_OPEN_EVENTS
    if len(argv) != 1:
        detail = "expected exactly one mode argument, got {}".format(len(argv))
        if is_fail_open:
            # A Stop handler's ERROR path never exits 2 (a deliberate deny does, via the orchestration
            # stop guard), not even on a malformed invocation: WARN and exit 0.
            print(json.dumps(_dispatcher_fail_open_warn(handler_name,"bad invocation: {}".format(detail))))
            return 0
        print("aiqt_hooks: {} ({}); failing closed".format(handler_name, detail), file=sys.stderr)
        return 2
    try:
        data = json.loads(sys.stdin.read())
        if not isinstance(data, dict):
            raise ValueError("payload is not a JSON object")
    except (ValueError, UnicodeDecodeError, OSError) as exc:
        # Unreadable/malformed stdin, JSON parse error, UnicodeDecodeError, or a non-dict payload.
        if is_fail_open:
            # A Stop handler's ERROR path never exits 2: surface a non-blocking warning and exit 0, so no Stop
            # payload (including a bare '{' or any garbage) can ever wedge the session.
            print(json.dumps(_dispatcher_fail_open_warn(handler_name,"unreadable payload: {}".format(exc))))
            return 0
        # A PreToolUse hook that cannot read its payload cannot clear the action, so it fails CLOSED.
        # exit 2 is the platform's blocking path; the diagnostic reaches Claude on stderr.
        print("aiqt_hooks: unreadable hook payload ({}); failing closed".format(exc), file=sys.stderr)
        return 2
    try:
        code, stdout_obj, stderr_text = HANDLERS[handler_name](data)
    except Exception as exc:  # a handler crash is an unreadable result
        if is_fail_open:
            # Same event-aware posture for a crash inside the Stop handler (e.g. the detector throws on a
            # pathological message): WARN and exit 0, never exit 2.
            print(json.dumps(_dispatcher_fail_open_warn(handler_name,"handler crash: {}".format(exc))))
            return 0
        # A PreToolUse handler crash fails closed (block), not pass.
        print("aiqt_hooks: handler {} failed ({}); failing closed".format(handler_name, exc),
              file=sys.stderr)
        return 2
    if stdout_obj is not None:
        print(json.dumps(stdout_obj))
    if stderr_text:
        print(stderr_text, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
