---
corpus-id: prsunc
origin: pack
family: aiqt
tier: 10
facet: INTEG
secondary: [ACCUR]
slug: preserve-uncommitted-work
---

# Preserve uncommitted work

A command that reverts a file drops uncommitted changes in it. git checkout -- <path> and git restore <path> overwrite the working tree from the index or a commit, discarding your unstaged edits; git reset --hard drops both staged and unstaged changes. Any of them can throw away a real fix you have applied but not yet committed. When undoing a temporary or experimental change, revert only those specific lines, or commit the genuine change first; never blind-revert a whole file whose uncommitted work you still need. A discard is safe only once the work you intend to keep is committed, or otherwise saved somewhere the discard will not reach.
