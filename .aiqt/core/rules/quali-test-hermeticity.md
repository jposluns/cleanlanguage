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

Where verification substitutes for an external executable that the code under test reaches by command lookup
or process launch, the substitute is an executable fixture, never a shell function or alias; an in-process
double of the launch interface, which launches nothing, is outside this requirement. The verification declares
the shells, if any, and the invocation routes it exercises, including child processes, has each fixture record
the invocations it receives, and checks that invocation evidence against the invocations each test case
expects. The harness initializes executable lookup and configuration from controlled inputs. The routes,
including absolute paths, a replaced search path, and clients implemented without that executable, by which
the substituted executable is launched or its service reached are all routes that the code under test, or
the verification itself (its test cases, inputs, fixtures, harness, and mutations), can take when run as
the verification runs it, including routes taken in turn, at any depth, by anything loaded, launched, or
contacted along such a route; a route counts whether or not review finds it, and a route reachable only
under inputs the verification neither supplies nor passes through does not count. Where any such route
could, in that run, reach live credentials, among them credentials inherited through the passed
environment, reach remote services, or write outside the fixture, the harness enforces isolation
over every such route: it removes access to live credentials and remote services and confines writes
to its fixture.
Only where every such route to that executable or its service, not only the declared invocation routes,
reaches no live credentials or remote services and writes only fixture state do executable fixtures and checked
invocation evidence suffice without enforced isolation. Placing a fixture first on the executable
search path does not intercept absolute-path calls, calls using a replaced search path, or clients
implemented without that executable, so executable fixtures supplement required isolation and never replace
it. If the required isolation cannot be established, or the verification cannot determine whether it is
required, execution is refused and verification reports that it cannot be evaluated. Missing, malformed,
or unexpected invocation evidence fails verification. Shell functions may
themselves be the subject of a test; where that test also substitutes for an external executable, the
requirements above apply to the substitution.
