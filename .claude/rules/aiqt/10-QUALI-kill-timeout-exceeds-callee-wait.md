---
corpus-id: kltwat
origin: pack
family: aiqt
tier: 10
facet: QUALI
secondary: [INTEG]
slug: kill-timeout-exceeds-callee-wait
---

# A kill timeout outlives the wait it bounds

When a wrapper is meant to let a command finish its own work, the runtime bound it imposes is set above
the command's intended end-to-end execution budget: its sequential waits, its retries and their backoff,
any queue residence, and the follow-on work that runs once those resolve, plus a margin. A bound set
below that budget can terminate a callee that is still behaving correctly, and the termination can then
be misdiagnosed as a failure of the callee or of whatever it was waiting on. Before wrapping a command
in a timeout meant to let it complete, establish the budget the command grants itself and size the bound above it; and before
concluding that a contended resource is starving a caller, establish that the caller actually outlived
its own configured budget rather than being killed under it. A deliberately shorter deadline is
legitimate where cutting the work short is the explicit intent, such as a latency limit or a fast-fail
probe, provided the termination is attributed to that deadline rather than reported as a failure of the
callee. An environment override meant to grant a longer wait can be silently stripped when it crosses a
privilege boundary, for instance when it is placed on the wrong side of a privilege-elevation command,
so the intended wait never reaches the callee and its default applies unseen; the override is confirmed
to land where the callee reads it rather than assumed to have carried across. This is the companion of
the bounded-consumption rule, which sets a ceiling so a runaway cannot exhaust resources.
