# Session hand-off, 2026-08-18

State for a fresh session. Everything below is merged to main unless marked open.

## Shipped this session

- v1.0.9: version bump so the released zip carries the renamed repository URL (PR #69).
- AIQT refresh in `.claude/CLAUDE.md`: Progress tier, revised facets, halt clause; the five rules of AIQT deliberately omitted, with https://aiqt.ai as the pointer (PR #70, provenance record updated).
- v1.0.10: new core-style rule marking clauses with `that` when the words after a verb could read as a direct object; 31 adversarially verified QA corrections across the skill, portable text, and site; six themed website passes for non-technical users (landing rewrite, install journey, verify page, `/instructions/` page with copy buttons and a hardened `js/copy.js`, accessibility, navigation); conjunction-opener cadence rule (PRs #71, #72 restored the hero GitHub button).
- v1.0.11: skill renamed `clean-language` to `cleanlanguage` (frontmatter name, package directory, artefacts `cleanlanguage.zip` and `cleanlanguage-<version>.zip`, portable text `cleanlanguage-instructions.txt` with a 301 from the old path); site download buttons serve the version-named zip via `/download`, `/claude/download`, and `/download/checksum` redirects (PRs #73, #74). Verified end to end: live redirects serve the v1.0.11 assets and the bytes match the published checksum.
- Release workflow: the redirect flip now ships as a PR the workflow opens and merges after checks, because main only accepts changes through a pull request; its first direct-push design was rejected with GH013 during the v1.0.11 release, and PR #74 applied that flip by hand.

## Design decisions and why

- Skill name `cleanlanguage` matches the domain and repository; the old name installs beside the new on every platform, so the install page, README, and INSTALL.md carry a remove-the-old-skill upgrade note.
- The stable `cleanlanguage.zip` asset remains published beside the versioned copy so INSTALL.md's `releases/latest/download` links stay valid.
- Versioned download filenames exist so repeat downloads stay distinguishable; the site prose is version-tolerant rather than auto-updated.
- The maintainer accepted the name collision with the coaching technique "Clean Language": no "AI writing" disambiguation in titles or meta descriptions, except the checklist page title "Clean Language, AI Writing Quality Assurance". The `/checklist/` URL and visible checklist naming stay, since the page is a list.
- Dash characters appear once on the landing page as quoted specimens; this is mention, not use, and does not breach the house dash ban.
- Removal reassurance is platform-generic by choice ("from the same place you added it"), so it cannot go stale with platform menus.
- Condensed site renderings of the skill are intentional; only semantic drift is a defect. `.claude/rules/clean-language-authoring.md` keeps its filename by choice.
- Repository conventions: Clean Language standard for all prose, Oxford English, -ize endings, no em or en dashes. Gates: `tools/check-portable-text-sync.sh` (run `--update` after any skill-source edit) and `tools/check-links.py`. Releases: set the `Version:` line in `cleanlanguage/SKILL.md`, dispatch `release-skill.yml` with the matching `v` tag. Merges to main are allowed on a green Cloudflare Pages check per `CLAUDE.md`.

## Open items and next actions

1. **`RELEASE_PR_TOKEN` secret (unverified).** The workflow's redirect step authenticates with `secrets.RELEASE_PR_TOKEN`, falling back to the built-in token. The maintainer reports a new token with pull-requests write access exists for hand-off; confirm it is stored under exactly that secret name, or change the name in `.github/workflows/release-skill.yml`.
2. **The PR-based redirect step is untested end to end.** It first runs at the next release. Watch the release run's final step; if the automated PR stalls, merge it by hand and investigate. With the fallback token, `pull_request`-triggered check workflows do not run on the automated PR; the required Cloudflare Pages check runs regardless.
3. **ChatGPT team "skill not found" (undiagnosed).** The 1.0.10 package was verified clean and structurally identical to the last working build, so the package is exonerated; workspace sharing or permissions is the suspect. Next: test the 1.0.11 zip on a personal ChatGPT account; check whether the skill was shared to the workspace and whether members may use uploaded skills; only if the personal test also fails, bisect against the archived 1.0.8 zip. If sharing scope is confirmed, add one sharing sentence to the install page's ChatGPT section.
4. **Maintainer's claude.ai skill copy.** It was the 1.0.8 build at last check. Remove the old Clean Language skill there, then upload the current zip, or both will appear.
5. **Site review residue.** The full verified findings report (58 confirmed, 16 refuted) was delivered to the maintainer as a file during the session and is not in the repository; all confirmed findings were either fixed or explicitly declined (meta descriptions and the channels title stay as they are). No queued site work remains.
