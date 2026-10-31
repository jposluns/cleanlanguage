# Asking the maintainer questions

**Superseded in part.** On 2026-10-29 the maintainer decided that these questions
are asked in the AskUserQuestion dialog in the four-role shape. The maintainer
wrote "the SOP is askuser." The four roles, in this order, are: predicted,
the choice the asker predicts the maintainer will make, drawn from the record of
past maintainer decisions and naming the pattern it rests on; best on the merits,
what the asker judges best for the project; maximal, the go-wild optimum, the
most thorough or over-engineered option, shown to teach what is possible and
never the default; and free-form, where the maintainer answers in their own
words. These four roles replace the Option A to D lettering in the Format
section. Wherever that section says Option A, read the best-on-the-merits option,
whatever its position; it carries the clear recommendation and the brief
statement of why it is recommended. If the maintainer chooses against it, the
asker asks once, explains plainly why it is better, and lets the maintainer
confirm or change their mind; after that, the choice stands. Option B is the
predicted option unless it is the same as the best-on-the-merits option; then
one option carries both roles, the asker says so and why, and there is no
separate Option B. Option C is the maximal option, and Option D is the
free-form answer, given through the dialog's own free-text field rather than a
listed option. One AskUserQuestion round may carry up to 4 questions,
whatever their weight. Where the text below differs, this note governs. In the
last bullet under Format, read "question" as "round": the next round follows
only after the current one is answered. A timeout never authorizes an
irreversible or outward action; a decision left unanswered is recorded, and the
step it gates is held while other work continues; the mode rules in `/flow`
set whether that step then falls under the unattended vote rule, which is in
the machine-local orchestrator instructions, as `/flow` states. A
fleet-wide decision SOP owned by lab_infra, the infrastructure orchestrator for
the fleet, will later replace this rule.

When work reaches a point that needs a decision only the maintainer can make, ask
for it directly. Follow this format so the maintainer can decide quickly and in
order.

## Format

- Ask one round at a time: give brief prose context, then the AskUser four-role
  dialog (the AskUserQuestion tool). Keep one decision per question.
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
