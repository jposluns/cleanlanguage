# Anti-patterns

Use this catalogue to detect generic AI prose. Diagnose the function of the wording before changing it. Each list names common instances, not the complete set; treat unlisted wording with the same function as if it were listed.

## Throat-clearing

Remove openings that delay the point:

- "Here is the thing"
- "Here is what matters"
- "Let me be clear"
- "The reality is"
- "The truth is"
- "It is worth noting"
- "At its core"
- "When it comes to"
- "In today's environment"
- "I want to explore"
- "Let me walk you through"

Replace the announcement with the substantive statement.

## Empty emphasis

Remove wording that asserts significance without demonstrating it:

- "This is critical"
- "The implications are significant"
- "The stakes are high"
- "This matters because"
- "Make no mistake"
- "Full stop"
- "Let that sink in"
- "game-changing"
- "deeply important"

Name the consequence, exposure, decision, cost, or required action.

## Formulaic contrast

Avoid repeated constructions such as:

- "It is not X. It is Y."
- "Not because X, but because Y."
- "The problem is not X. The problem is Y."
- "This is not merely X; it is Y."
- "It does not just X. It also Y."

Use contrast only when the distinction is materially useful. Otherwise state the actual conclusion directly.

## Manufactured cadence

Watch for:

- repeated 1-sentence paragraphs;
- stacked fragments;
- sentences opened with a conjunction (And, But, So, Yet, Because) as a rhythm device;
- multiple paragraphs ending with a punch line;
- repetitive 3-item rhetorical lists;
- question-and-answer setups that imitate a speech;
- identical sentence lengths;
- concluding slogans that restate the preceding paragraph.

Vary cadence naturally. Use complete sentences unless a fragment serves a clear channel-specific purpose. Open a sentence with a conjunction only when the connection it names is real; rewrite a reflexive And, But, So, or Because opener into the sentence it belongs to.

## Meta-commentary

Delete unnecessary narration about the writing itself:

- "This section explains"
- "The rest of this document will"
- "As discussed below"
- "We will now examine"
- "The following points are worth considering"

Retain navigational language only when it helps readers use a long or complex document.

## Business filler

Replace vague corporate language with the actual action:

| Avoid | Prefer |
|---|---|
| leverage | use, apply, rely on |
| utilize | use |
| navigate challenges | address the specific constraint |
| moving forward | next, from now, by a stated date |
| circle back | return to, respond, review |
| deep dive | analysis, review, investigation |
| align on | agree, approve, decide |
| action this | complete, assign, approve, investigate |
| optimize | state what improves and how it is measured |
| transformation journey | programme, migration, operating change |

Retain established technical terms such as latency, resilience, threat surface, control plane, data plane, zero trust, or least privilege when used precisely.

## AI vocabulary fingerprints

No single word proves that a model wrote a passage; clusters of predictable vocabulary still make prose sound generic. Treat each word below as a diagnostic signal, not a ban. Clean Language challenges words such as:

- delve, tapestry, realm, landscape, journey, testament;
- leverage, unlock, elevate, empower, foster, navigate;
- robust, holistic, seamless, pivotal, crucial, transformative;
- meticulous, nuanced, multifaceted, dynamic, comprehensive;
- underscore, illuminate, resonate, reimagine, revolutionize.

Each stays valid when it carries specific meaning: keep `robust` in "a robust statistical method"; cut scene-setting such as "today's threat landscape". The problem is automatic selection, repetition, and use as a substitute for evidence.

## Empty modifiers

Question intensifiers and softeners such as:

- really
- very
- clearly
- simply
- actually
- fundamentally
- inherently
- genuinely
- obviously
- undoubtedly
- extremely

Delete them when they add no information. Preserve them when they express a defensible degree, legal threshold, technical property, or deliberate tone.

## False agency and hidden ownership

Replace abstractions that conceal responsibility:

- "the decision emerged"
- "the issue was addressed"
- "the process failed"
- "mistakes were made"
- "the data tells us"

Name the actor when known and relevant. Technical objects may remain subjects when they genuinely act: "The firewall blocked the connection" is precise.

## Excessive reassurance

Remove unrequested validation and emotional cushioning:

- "You are absolutely right"
- "That makes complete sense"
- "Great question"
- "I completely understand"
- "You have done an excellent job"

Acknowledge facts or constraints directly instead.

## Artificial balance

Do not force a positive counterpoint after every criticism. State the finding, evidence, consequence, and recommendation. Add mitigating factors only when they affect the conclusion.

## Executive template phrasing

Flag polished professional phrasing that is grammatically sound but overrepresented in generated messages, where it serves as default connection or emphasis rather than precise meaning. Treat it as a diagnostic signal, not a banned list: each of these is legitimate in precise legal, audit, standards, or technical use.

| Avoid as default | Prefer |
|---|---|
| highly relevant | relevant to my work; directly related to what I am doing |
| particularly, specifically, especially | cut the qualifier where the sentence reads as well without it; otherwise name the item plainly (`the API`, not `particularly the API`) |
| aligns closely with | relates directly to; matches; covers |
| my main areas of interest are | I am interested in; I would like to discuss |
| I would value discussions with | I would like to meet with |
| I would welcome your perspective | I would appreciate your view; I would like your feedback |
| possible application to | how this could apply to; whether this fits |

Rewrite an abstract-noun frame as a direct statement: "My main areas of interest are X and Y" becomes "I am interested in X and Y."

Watch for catalogue sentences: noun lists after "including", "across", "spanning", "focused on", or "areas such as" that reproduce a source list without prioritization or intent. Ask whether each item needs to appear, whether related items can be grouped, and whether the list connects to a decision, question, or request. Tie the list to what the writer wants, or trim it.

When the user rejects a phrase as generated or unlike their voice, identify its function and rewrite the sentence structure. Do not substitute a synonym with the same cadence, such as replacing "highly relevant" with "particularly" or "aligns closely with".
