# Asking the maintainer questions

**Superseded in part.** On 2026-10-29 the maintainer decided that these questions
are asked in the AskUserQuestion dialog in the four-role shape: predicted, best on
the merits, maximal, and free-form. The description of PR #172 in this repository
quotes the maintainer's instruction. The options are presented in the order
predicted, best on the merits, maximal, and free-form. These four roles replace
the Option A to D lettering in the Format section. That section still requires a
clear recommendation, and the best-on-the-merits option carries it. Where the text
below differs, that dialog governs; in particular, "in prose" and the ban on a
multiple-choice chip interface in the first bullet under Format no longer apply.
The rule awaits the fleet-wide decision SOP owned by lab_infra, the
infrastructure orchestrator for the fleet.

When work reaches a point that needs a decision only the maintainer can make, ask
for it directly. Follow this format so the maintainer can decide quickly and in
order.

## Format

- Ask one question at a time, in prose. Do not batch several questions into one
  message, and do not use a multiple-choice chip interface for these.
- Give each question a clear recommendation and viable alternatives:
  - **Option A**: the recommended answer, marked as recommended.
  - **Option B** and **Option C**: two other viable options.
  - **Option D**: a free-form answer, so the maintainer can give a different
    direction in their own words.
- State briefly why Option A is recommended and what each option changes.
- Ask the next question only after the current one is answered. Continue in
  priority order until every open decision is resolved.

## When to ask

Ask only about genuine decisions: choices where more than one answer is
reasonable and the maintainer's preference, taste, or authority settles it. Apply
clear defect fixes and well-established defaults without asking, and report them.

This rule composes with the express-authorization and clarify-before-acting
disciplines: it is the standard shape for the clarifying question those rules call
for.
