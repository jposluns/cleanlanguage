---
name: aiqt-adopter-supplements
description: Adopter-owned clauses that supplement the AIQT rules where the condensed pack renderings dropped a discipline this project relies on.
---

# AIQT adopter supplements

Adopter-owned, under the reserved `.claude/rules/external/` namespace. These clauses
supplement, and do not override, the vendored AIQT rules. They restore 3 specific disciplines
that the condensed AIQT renderings dropped relative to the detailed originals this repository
previously used. Retire this file once the AIQT pack carries these clauses upstream (tracked
in the durable store; reported to guardrails 2026-09-05).

## Supplement to evidence-grounded completion

Accepting an unverified item requires a durable tracker. Naming an unverified part discharges
the honesty obligation, but when the work then accepts the item rather than resolving it
(proceeding on it, annotating a claim as unverified for now, or relying on a value not
confirmed current), record the acceptance as a durable tracking item in the backlog so it is
revisited and verified. The tracker names what must be verified, where the unverified claim
lives, and what would confirm or refute it. The trigger is acceptance, not mention.

## Supplement to express authorization before execution

A conditional or sequenced authorization authorizes only its first, unconditioned step. "Do X,
then we go" authorizes X; the step after the wait needs its own express go once the maintainer
confirms the condition. Do not read the whole sequence as a standing green light.

## Supplement to clarify before acting

The compute-first gate: before asking the maintainer a question, check whether the answer is a
findable fact you can retrieve yourself (a file location, a citation, a count, a version, where
a term appears, what a document currently says). If it is findable, run the search or read and
surface the answer rather than asking. Asking for a fact you could compute is a discipline
failure, the inverse of silently picking.
