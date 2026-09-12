---
corpus-id: slfgrd
origin: pack
family: aiqt
tier: 10
facet: QUALI
secondary: [INTEG]
slug: self-guardrail-from-error
map-iso-42001-tight: [10.2]
map-nist-airmf-tight: [MANAGE 2.3]
---

# Propose a guardrail when an error reveals a gap

When an error or near-miss traces back to no rule existing that would have prevented it, propose a new
guardrail as a follow-on once the immediate defect is fixed, drafted in the same taxonomy and frontmatter
shape as the rest of the corpus. The proposal is a candidate like any other, landing only through the
normal apply gate.
