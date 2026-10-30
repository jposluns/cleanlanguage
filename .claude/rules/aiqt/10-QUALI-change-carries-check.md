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

A check that asserts an absence, that a finding is not raised, an error is not thrown, or an action is not
taken, is held to a stricter form of that confirmation. Observing such a check run is not evidence that it
guards the change, because an absence assertion passes both when the feature under test suppresses the
outcome and when the input never reaches the path that would produce it. The check discriminates only when
its input is one the feature under test changes, so that removing the feature makes the asserted outcome
appear. Each such check is paired with a deliberate flip that removes or disables the feature, and it is
observed to fail under that flip before its pass is trusted. A flip that yields only a build failure, an
execution error, or an unrelated outcome establishes no discrimination; the flip counts only when the
asserted outcome itself appears. Where the feature can be disabled within the suite, the pairing is kept as a
durable companion case that asserts the outcome does appear without the feature, so a later change that stops
the input reaching that path fails the suite rather than passing silently. This attaches to an absence check
relied on as the check a change carries, not to an incidental negative assertion inside a check whose
discrimination already rests on a positive assertion.
