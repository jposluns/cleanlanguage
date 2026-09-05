---
corpus-id: artbr1
origin: pack
family: aiqt
tier: 10
facet: INTEG
secondary: [QUALI]
slug: branch-and-merge-on-green
map-nist-airmf-broad: [MANAGE 4.1]
map-nist-80053-tight: [CM-3, CM-3(2)]
map-nist-80053-broad: [SA-10]
map-nist-ssdf-broad: [PS.1.1, PW.7.1]
map-iso-42001-broad: [A.6.1.3]
map-iso-23894-broad: [A.7, B.7]
---

# Branch and merge only on green

Develop a change in isolation from the protected line of development, put it through a review gate, and
integrate it only when its checks pass. What lands on the protected line is the reviewed, verified state,
never a work in progress. On git the usual form is a feature branch and a pull request merged on green;
the mechanism varies, the gate does not.
