---
corpus-id: vfxcmt
origin: pack
family: aiqt
tier: 10
facet: ACCUR
secondary: [INTEG]
slug: verify-fix-in-commit
---

# Verify a fix is in its commit

Applying a fix on disk is not the same as landing it. Before recording or claiming that a fix shipped, confirm it is actually present in the commit that claims it: inspect the commit's file list (for example git show <ref> --stat) and confirm the changed lines are in the committed content, not only in the working tree or a since-reverted state. A commit message that asserts a fix, with no matching change in the commit, is an inaccurate record; verify the artefact before the claim.
