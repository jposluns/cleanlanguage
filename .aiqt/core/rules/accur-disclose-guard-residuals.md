---
corpus-id: dscres
origin: pack
family: aiqt
tier: 10
facet: ACCUR
secondary: [QUALI]
slug: disclose-guard-residuals
---

# Disclose a guard's residual coverage

A best-effort guard that cannot cover its whole input space does not present itself as complete. Where
coverage is necessarily incomplete (for example, an open command grammar, a matcher that option-insertion or
wrapping can slip past, or a denylist over an effectively infinite space), the guard states the residual it
does not catch rather than implying it catches everything. A coverage boundary named where the guard is defined is
reviewable; a boundary left implicit reads as a guarantee the guard cannot honour. The disclosure is part of
the guard, not a footnote discovered after it fails.
