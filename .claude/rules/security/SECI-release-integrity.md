---
corpus-id: secpub
origin: pack
family: security
facet: SECI
slug: release-integrity
map-cwe-tight: [CWE-353]
map-cwe-broad: [CWE-345]
map-nist-80053-broad: [SI-7, SR-4]
map-nist-ssdf-tight: [PS.2.1]
map-nist-ssdf-broad: [PS.3.2]
map-owasp-web-broad: [A08]
map-owasp-cheatsheet-broad: [software-supply-chain-security]
map-csa-aicm-broad: [MDS-09]
---

# Publish artefacts with verifiable integrity

A released or published artefact ships with a signature verifiable against an authenticated maintainer key,
or a digest published through an authenticated channel independent of artefact delivery. An adopter can then
verify that what they installed matches that authenticated reference.
