---
corpus-id: prtbrn
origin: pack
family: aiqt
tier: 10
facet: INTEG
secondary: [TRUST]
slug: protected-branch-integrity
map-nist-airmf-broad: [MANAGE 4.1]
map-nist-80053-tight: [CM-3, CM-5]
map-nist-ssdf-tight: [PS.1.1]
map-nist-ssdf-broad: [PW.7.1]
map-iso-42001-broad: [A.6.1.3]
map-iso-23894-broad: [A.7, B.7]
---

# Protected-branch integrity

The protected line of development is never rewritten, overwritten, or changed directly; it changes only
through a reviewed, verified integration. On git that means no force-push and no direct commit to the
protected branch, only a merged pull request.
