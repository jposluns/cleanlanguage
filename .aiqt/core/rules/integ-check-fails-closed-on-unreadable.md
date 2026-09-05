---
corpus-id: chkfcl
origin: pack
family: aiqt
tier: 10
facet: INTEG
secondary: [QUALI]
slug: check-fails-closed-on-unreadable
map-nist-80053-tight: [SI-17]
map-owasp-cheatsheet-broad: [error-handling]
---

# A check fails closed on input it cannot read

A gate, validator, scan, or traversal that cannot access, read, or list an input it is meant to cover
reports that as a failure, never as an absent, empty, or clean input. An operation that silently yields
nothing on a permission or I/O error, a glob or a listing that returns empty, or an existence check that
returns false, is made to surface the error, so an unreadable input can never read as nothing to check
and pass. A resource the work declares, or that its specification or contract requires it to cover, is held to the
same standard: when it is absent or unusable, that is a failure, not a silent skip. The presence-test-then-run-or-succeed shape, which
lets a missing declared input read as nothing to do, is exactly this failure; absence reads as a clean
result only for an input outside what the work declares or its specification or contract requires.

Unreadable includes present but unparseable. When a candidate record consumed by a gate or parser is
malformed or fails validation against its schema or grammar, the result is a refusing failure that names the
record, never silent absence.
