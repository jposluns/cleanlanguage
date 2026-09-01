# Clean Language

Clean Language is a cross-platform editorial standard for AI writing. It supports drafting, rewriting, proofreading, adapting, and reviewing precise, direct, natural prose.

It removes common AI-writing patterns such as robotic tone, filler, contrast framing, em dashes and en dashes, fake enthusiasm, repeated conclusions, business jargon, and vague claims while preserving factual, technical, legal, policy, contractual, and standards meaning.

<p align="center">
  <a href="https://cleanlanguage.ai/install/?ai=claude"><img alt="Set up in Claude" src="https://img.shields.io/badge/Set_up_in_Claude-C15F3C?style=for-the-badge&logo=anthropic&logoColor=white"></a>
  <a href="https://cleanlanguage.ai/install/?ai=chatgpt"><img alt="Set up in ChatGPT" src="https://img.shields.io/badge/Set_up_in_ChatGPT-111111?style=for-the-badge&logo=openai&logoColor=white"></a>
  <a href="https://cleanlanguage.ai/install/?ai=gemini"><img alt="Set up in Gemini" src="https://img.shields.io/badge/Set_up_in_Gemini-3154D9?style=for-the-badge&logo=googlegemini&logoColor=white"></a>
  <a href="https://cleanlanguage.ai/install/?ai=copilot"><img alt="Set up in Copilot" src="https://img.shields.io/badge/Set_up_in_Copilot-0A6ED1?style=for-the-badge"></a>
</p>

<p align="center">
  <a href="https://cleanlanguage.ai/install/">Detailed installation instructions</a> ·
  <a href="https://cleanlanguage.ai">Project website</a> ·
  <a href="INSTALL.md">Repository installation guide</a>
</p>

## What it does

- Leads with the answer, decision, request, finding, or required action.
- Produces concise, information-dense Oxford English.
- Removes generic AI language without imposing arbitrary grammatical bans.
- Preserves names, dates, figures, commitments, qualifications, quotations, and domain terminology.
- Protects legal, technical, contractual, policy, and standards meaning.
- Supports executive communication, email, Teams, Slack, LinkedIn, reports, policies, incident updates, technical documentation, governance material, and general prose.
- Distinguishes verified facts, reasonable inferences, estimates, and speculation.
- Avoids fake enthusiasm, unrequested reassurance, ceremonial praise, and generic engagement prompts.

## Supported platforms

Clean Language uses one canonical skill definition for Claude, ChatGPT, Gemini, Copilot, and other compatible AI systems. The core skill lives in [`cleanlanguage/`](cleanlanguage/).

- **Claude:** download the packaged Skill, upload it through Claude's Skills interface, and enable it.
- **ChatGPT:** create or upload a Skill using the Clean Language instructions.
- **Gemini:** create a reusable Gem or install the Agent Skill through Gemini CLI.
- **Copilot Studio:** create an agent and upload the full skill zip (recommended). **Microsoft 365 Copilot agent:** create the agent, paste the 8k instructions, and add the full standard as reference.
- **Other AI systems:** use the portable instructions as custom instructions, project knowledge, or a system prompt.

See [INSTALL.md](INSTALL.md) for complete setup instructions.

## Usage examples

- "Rewrite this email using Clean Language."
- "Audit this report for generic AI language without changing the technical meaning."
- "Draft a CIO-level Teams message from these notes."
- "Proofread this policy clause with minimal intervention."
- "Adapt this email into a LinkedIn-compatible response."

## Distribution and assurance

Latest release: [![Latest release](https://img.shields.io/github/v/release/jposluns/cleanlanguage?label=release)](https://github.com/jposluns/cleanlanguage/releases/latest). The full changelog is on the [releases page](https://github.com/jposluns/cleanlanguage/releases).

Tagged releases provide:

- `cleanlanguage.zip`, containing the upload-ready Skill under a stable name;
- `cleanlanguage-<version>.zip`, the same bytes under a version-named copy, which the site's download buttons serve;
- a `.sha256` checksum for each.

Upgrading from a version before 1.0.11? The skill's internal name changed from `clean-language` to `cleanlanguage`, so uploading the new file adds a second skill beside the old one. Remove the old Clean Language skill first, then install the new file.

The package contains prose instructions, metadata, reference material, PNG and SVG icons, and the licence and notice files. It contains no executable scripts, software dependencies, or instructions that require external network access.

## Licence

Except where otherwise noted, all material in this repository, including the Clean Language skill and the cleanlanguage.ai website content, markup, and styles, is licensed under [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/) (SPDX: `CC-BY-SA-4.0`).

Suggested attribution:

> Clean Language by Jeff Posluns, https://cleanlanguage.ai, licensed under CC BY-SA 4.0.

(Add "Changes were made." if you modified it.)

Third-party material retains its original licence. See [NOTICE.md](NOTICE.md).