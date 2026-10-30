---
corpus-id: tmrrst
origin: pack
family: aiqt
tier: 10
facet: QUALI
secondary: [INTEG]
slug: elapsed-aware-timer-restore
---

# A borrowed process timer is restored elapsed-aware

Code that borrows a caller's process-global deadline facility for a bounded window, a signal
handler, an interval timer, or a pending single-shot alarm, restores the caller's state
elapsed-aware, never verbatim. On restore an active caller timer holds exactly the countdown
it would have reached had the borrow not occurred, measured by that timer's own semantics: its
clock domain (wall or monotonic time for a real-time timer, the relevant process or thread CPU
time for a CPU-time timer), its relative or absolute mode, and how it accounts for a clock
adjustment, so a CPU-time timer is charged only the CPU actually consumed during the window and
a relative timer is not disturbed by a wall-clock jump. An inactive caller timer remains inactive
rather than being armed. A pending notification or single-shot alarm is preserved, not consumed
or discarded, and a caller deadline that came due during the window is delivered, not dropped. A
periodic timer's repeat interval, and its phase to the extent the platform can express it, are
preserved. The original handler is reinstalled through exception-safe cleanup. The save and the
elapsed-aware restore live once, in a single shared, nesting-safe helper, so no call site can
hand-roll a variant that reintroduces the verbatim restore, and the helper itself remains subject
to the same inspection as any call site. Where the timer's own semantics cannot be faithfully
reproduced on restore, including a countdown the borrower cannot measure or an already-due
notification the platform cannot make promptly deliverable, the code uses a timeout mechanism
that is not process-global, or refuses the borrow, rather than approximating and corrupting the
caller's deadline, most dangerously a watchdog's. This is the companion of the kill-timeout rule (kltwat).
