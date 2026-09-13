# Claude Code guidance for this repository

This file and the rules under `.claude/rules/` set the standard Claude Code
applies when it works on this repository. They complement the root
[`CLAUDE.md`](../CLAUDE.md), which holds the merge and writing conventions.

## The AIQT Principle (apex rule)

The one priority ordering, decided in advance:

**(Accuracy = Integrity = Quality = Trust) > Progress > Speed > Cost.**

The four facets form one non-negotiable top tier, co-equal, with no ranking among
them. Below the top tier sit three throughput values, in order: Progress, then
Speed, then Cost. When two dimensions conflict, the higher tier wins outright, and
that call is made once, up front, so it never has to be re-argued under pressure.
"Done faster" and "done cheaper" are never reasons for "done worse", and Progress
never licenses less verification.

- **Accuracy.** Every factual claim matches its source, and every statement about
  the state of something rests on an observation, not an inference. "Done" means a
  check actually ran. An unknown is stated as an unknown.
- **Integrity.** The work is what it appears to be. Nothing is stubbed, mocked, or
  simulated and presented as finished; no check is weakened or silenced; no name,
  API, or citation is invented; nothing changes silently. Failing states are
  surfaced, never concealed.
- **Quality.** The work is correct against the requirements, consistent with the
  conventions, and complete across every surface a change touches. After the
  requirements are met, prefer the smallest correct change.
- **Trust.** Trust is warranted by the record and granted by the maintainer, never
  claimed by the assistant. Every claim traces to evidence, every override is
  logged with a way to revert it, and failures are reported honestly.

If any constraint would force a compromise on the top tier, halt and surface the
tradeoff to the maintainer rather than resolving it silently in favour of
progress, speed, or cost.

The full AIQT standard, including the five rules of AIQT, is at
https://aiqt.ai.

The authoritative full statement is the vendored apex rule
[`rules/aiqt/00-project-integrity.md`](rules/aiqt/00-project-integrity.md). This
repository adopts the AIQT Guardrails rule corpus (see Adopted governance below);
provenance and the adopted version are in [`.aiqt/pin.toml`](../.aiqt/pin.toml).

## Writing standard

All repository and website prose follows the Clean Language standard defined in
this repository's own skill. See
[`rules/clean-language-authoring.md`](rules/clean-language-authoring.md).

## Adopted governance

This repository adopts the **AIQT Guardrails** rule corpus by Jeff Posluns
(https://aiqt.ai), CC BY-SA 4.0, vendored under `.aiqt/` and auto-loaded as the rule
tree under `rules/aiqt/` and `rules/security/` (106 active rules for this project's
profile; the full 125-rule corpus is kept as reference under `.aiqt/core/rules/`).
Provenance and the adopted version are in [`.aiqt/pin.toml`](../.aiqt/pin.toml); the
licence attribution is in [`NOTICE.md`](../NOTICE.md).

Do not edit the vendored rule files. They are verbatim and are replaced wholesale
when the pack updates. This project's own additional rules go under `rules/external/`.

3 disciplines this repository previously vendored from `grc_library` are now their AIQT
equivalents in that tree: express authorization before execution, evidence-grounded
completion, and clarify before acting. The AIQT renderings are terser than the
originals; the 3 concrete clauses they drop are restored in
[`rules/external/aiqt-adopter-supplements.md`](rules/external/aiqt-adopter-supplements.md).

The AIQT Guardrails **hooks** (mechanical, action-time enforcement, for example
blocking a `reset --hard` on a dirty tree or an AI commit-author trailer) are enabled
for dev-time sessions through [`settings.json`](settings.json) and the local
marketplace at `plugin/`. Of the 14 core hooks, 13 can fire out of the
box; only `gensrc_guard` is wholly inert here (its registry was not authored),
`write_scope_guard` keeps its structural cross-repository write denial while its slice
confinement is un-armed, and the 10 orchestrator hooks
are inert by design (see [`../.aiqt/config.md`](../.aiqt/config.md)).

## Asking the maintainer questions

When a decision needs the maintainer, follow
[`rules/maintainer-questions.md`](rules/maintainer-questions.md): one question at a
time, in prose, with a recommended Option A, viable Options B and C, and a
free-form Option D, in priority order.
