---
corpus-id: tsthrm
origin: pack
family: aiqt
tier: 10
facet: QUALI
secondary: [ACCUR, INTEG]
slug: test-hermeticity
map-nist-80053-tight: [SA-11]
map-nist-80053-broad: [SA-8(29)]
map-nist-ssdf-broad: [PW.8.2]
map-iso-42001-broad: [A.6.2.4]
---

# A test's verdict comes from the code, not its surroundings

A test is built so its pass or fail is caused by the behaviour under test, not by ambient state the test
does not control. State that varies between machines, runs, users, or working directories, the process
umask and inherited filesystem default permissions, the locale, timezone, and clock, environment variables
and the executable search path, and the order in which other tests run, is pinned to a known value,
neutralized, or kept out of what the assertion depends on, so the same code yields the same verdict
everywhere. An assertion narrows to the property the code itself establishes rather than a composite the
environment can perturb; but where a system-created property can carry more than the code sets, the
assertion covers the whole of it rather than only the convenient part, so an unintended widening is caught
rather than concealed. A failure that traces to such uncontrolled state is a defect in the test, fixed at
the test, not a finding against the code; a pass that rests on a convenient local default is not evidence
the code is correct.

A test also leaves the host as it found it. It creates, moves, deletes, or changes the permissions or
ownership of only paths within a temporary location it made for itself and removes afterwards, and it never
mutates state outside that location. Where a test must walk real parent directories, it bounds the walk by
that fixture root, never by a host property such as ownership, which can reach far past the fixture and
disturb unrelated state.
