---
corpus-id: bgcwai
origin: pack
family: aiqt
tier: 30
facet: SPEED
secondary: [INTEG, PROGR]
slug: background-work-during-ci-waits
map-nist-80053-broad: [CM-3(2)]
---

# Background work during CI waits

A wait is a resource. While a check or another long operation is in flight, advance independent,
non-conflicting work rather than idling, without ever gating the outcome on an unread or pending result.
Never integrate on a pending or unreadable signal; parallelism speeds the work, it never lowers the bar.
