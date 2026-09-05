---
corpus-id: dfdpth
origin: pack
family: aiqt
tier: 10
facet: QUALI
secondary: [SECI]
slug: defence-in-depth-default
map-nist-80053-broad: [SA-8]
map-iso-23894-broad: [A.11]
---

# Defence in depth by default

When an overlapping control that guards against the same failure is available at low marginal cost, it is the
default recommendation, and its marginal cost is stated alongside it. The overlap is the value rather than
redundancy to trim: a further layer earns its place by catching what an earlier one misses, so a layer is
not declined on the grounds that a sibling control should already catch the case. This layering applies to a
capability that is kept: an unneeded capability is removed outright before anything is layered on it, and
defence in depth then hardens what remains, never justifying the retention of a capability that could be
removed.

The preference never mandates gold-plating. Where a layer's marginal cost is considerable, it is weighed
rather than assumed, and omitting an expensive layer on a weighed, recorded judgement is sound, not a
violation. A layer that over-fires is not cheap: one that raises false alarms trains its own bypass and
erodes trust in the controls around it, so a noisy layer is not the low-cost overlap this prefers, and adding
one is not warranted by this rule.
