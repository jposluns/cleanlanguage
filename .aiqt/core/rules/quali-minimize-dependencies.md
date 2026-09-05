---
corpus-id: mindep
origin: pack
family: aiqt
tier: 10
facet: QUALI
secondary: [SECI]
slug: minimize-dependencies
map-nist-80053-broad: [SA-8]
---

# Minimize external dependencies in favour of standard libraries

A capability is implemented with the language's standard library or the project's existing utilities
where they reasonably serve, and a new external dependency is introduced only when the task cannot
reasonably be achieved without one. This preference never licenses reimplementing what must not be
home-grown, such as cryptography; where a vetted external implementation is the sound choice, it is
used, and it then enters through the project's dependency gates like any other.
