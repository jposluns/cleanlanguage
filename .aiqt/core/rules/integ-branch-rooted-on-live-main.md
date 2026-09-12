---
corpus-id: brnrot
origin: pack
family: aiqt
tier: 10
facet: INTEG
secondary: [QUALI]
slug: branch-rooted-on-live-main
map-nist-airmf-broad: [MANAGE 4.1]
map-nist-80053-tight: [CM-3, CM-3(2)]
map-nist-80053-broad: [SA-10]
map-nist-ssdf-broad: [PW.7.1]
map-iso-42001-broad: [A.6.1.3]
---

# Cut branches from the live protected line and re-home after a rewrite

A working branch is cut from the current tip of the protected line of development, so its ancestry
always resolves to the live protected line. A branch whose common ancestor with the protected line no
longer resolves, because a history rewrite, a re-initialization, or a squash-merge retired the root it
was cut from, is orphaned: no work is dispatched onto it and nothing integrates from it until it is
re-homed onto the live line by a recut or a replay of its unique commits. A branch whose ancestry still
resolves but whose fork point has fallen behind the line's configured freshness horizon is stale and is
re-homed on the same terms. On git the signal is the merge base between the protected ref and the
branch: where it resolves to a commit the branch is rooted, and where it resolves to nothing the branch
is orphaned. The check that asserts this derives the protected ref from the repository it runs in and
fails closed when that ref, or the revision under check, cannot be resolved.
