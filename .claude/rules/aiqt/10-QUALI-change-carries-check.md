---
corpus-id: chgchk
origin: pack
family: aiqt
tier: 10
facet: QUALI
secondary: [INTEG]
slug: change-carries-check
map-nist-80053-broad: [CM-3(2), SA-11]
map-nist-ssdf-broad: [PW.8.2]
map-iso-42001-broad: [A.6.2.4]
---

# A behavioural change carries a check that fails without it

A change that alters behaviour lands together with an automated test or gate that fails when the change is
absent. Verification leaves a durable artefact that keeps guarding the behaviour after the one-time
verification pass has moved on.

The check is confirmed to run, not merely to exist. A test or gate that is present but never reached,
misplaced in its file, wrongly indented, or never registered with the runner, provides no coverage, and a
passing suite is not evidence that it holds: a check that never executed and one that executed and passed are
indistinguishable from the suite's green alone. Before that green is trusted for the new behaviour, confirm
the check executed, by observing it run or by a deliberate flip that shows it failing without the change, and
prefer a runner that reports the count or identity of the checks it actually ran over a hand-maintained
assertion that they are all present.
