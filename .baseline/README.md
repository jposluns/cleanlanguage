# Baseline 1.7.0: the shared site template

This package is the shared template of Jeff Posluns's 6 project sites (secureconfig.ai, opfiles.ai, auditthis.ai, cleanlanguage.ai, aiqt.ai, grclibrary.ai): 1 stylesheet, 1 palette file, 4 fonts, 6 scripts, the logos, marks and touch icons, 15 reference pages that fix the markup, a palette contrast gate and a template for a site's own palette file, and the 2 documents that govern the sites. A site that copies the runtime files, sets its site class and generates its pages with the reference markup looks and behaves as part of the family and differs only in its colours, logo and content. The normative description is `SPECIFICATION.md` (1.7); `CONTENT-GUIDELINES.md` (1.4) governs the wording, and the Clean Language standard (https://cleanlanguage.ai) governs the prose. `CHANGELOG.md` lists what changed in each version and why.

A published version never changes. Any change is a new version at `https://posluns.ca/baseline/<version>/`, with its archive `https://posluns.ca/baseline/baseline-<version>.tar.gz` and the archives' digests in `https://posluns.ca/baseline/SHA256SUMS`.

## What is in the package

| Path | Content | Copied by a site |
|---|---|---|
| `baseline.css` | The whole shared stylesheet: reset, typography, layout, every component, the footer's container query stages and their fallback. Reads only the tokens in `palettes.css` and the family and layout tokens it declares at the top. | yes |
| `palettes.css` | The 6 site palettes (light, dark, and the `[data-scheme]` forced variants that the light and dark switch sets), the cyclic rainbow and the footer's neutral grey. From 1.6.0 each site's dark mode is a near-black with a tint of its own hue, and dark-mode text is neutral. From 1.7.0 each palette also carries the matrix tokens: row tints, a 5-step heat ramp and 6 column-group accents. | yes |
| `gen_palettes.py`, `contrast-report.txt` | The palette generator and its report; the generator exits non-zero if any text pair misses 4.5:1 (UI pairs 3:1). Edit the script, never the CSS. | no |
| `fonts.css`, `fonts/` | Newsreader, Public Sans, JetBrains Mono and Dancing Script, latin subsets, variable weight, each with its SIL OFL 1.1 licence file. The font paths are relative to `fonts.css`. | yes, with the licence files |
| `copy.js`, `select.js`, `search.js`, `rail.js`, `matrix.js` | Copy to clipboard for prompt and command blocks; the install selector; the client-side list filter, with facets and a results-only mode from 1.5.0, and, from 1.7.0, opt-in chips that show when a choice would give no results; the rail mark that follows the reader (from 1.3.0, on every page whose rail lists in-page sections); the column presets of a matrix table (from 1.5.0), with column toggles and a column highlight (from 1.7.0). Each is opt-in per page and enhances markup that works without it. Load with `defer`. | yes |
| `scheme.js` | The light and dark switch in the top bar (from 1.6.0), on every page. Load it in `<head>`, before the stylesheets, without `defer` or `async`: `<script data-cfasync="false" src=".../scheme.js"></script>`. | yes |
| `site-palette.example.css` | The template of a site's own `site-palette.css` (from 1.6.0; section "Site-owned palette colours"). | no (the site writes its own file only when the owner asks) |
| `tools/check_palette.py` | The palette contrast gate (from 1.6.0), mandatory in every site's build. | yes, to `.baseline/check_palette.py`, not served |
| `logos/` | Per site: `<site>.svg` (full colour: hero, rail, footer), `<site>-mono.svg`, `<site>-favicon.svg`, `<site>-card.svg` (link preview), `<site>-touch.png` (Apple touch icon, 180 by 180, opaque). | yes |
| `marks/` | GitHub, LinkedIn and ORCID marks for the footer, with `marks/NOTICE.md` (sources, dates, terms). | yes, with `marks/NOTICE.md` |
| `reference/` | 15 reference pages, 1 per page type (section "The reference pages" below). | no |
| `tools/measure.js` | Measures the 2 per-site constants (section "Per-site constants"). | no |
| `SPECIFICATION.md`, `CONTENT-GUIDELINES.md` | The specification and the content guidelines at the version published with this package. | no |
| `LICENSE`, `NOTICE.md` | CC0 1.0; the exceptions (fonts, marks). | yes |
| `SHA256SUMS`, `CHANGELOG.md`, `README.md` | Checksums of every file; history; this file. | no |

## Adoption in a repository

1. Obtain the version as its archive, `https://posluns.ca/baseline/baseline-<version>.tar.gz`, and verify its SHA-256 against `https://posluns.ca/baseline/SHA256SUMS` before unpacking. Never verify file by file over the live domain: Cloudflare injects scripts into the HTML it serves, so an HTML file fetched from the site is not the published file. Inside the archive, `SHA256SUMS` covers every file of the version (`sha256sum -c SHA256SUMS` from the version folder).
2. Copy only the runtime and licence files (the "yes" rows above) into the site's own asset folder (proposed `assets/baseline/`): `baseline.css`, `palettes.css`, `fonts.css`, `fonts/` with the 4 licence files, `copy.js`, `select.js`, `search.js`, `rail.js`, `matrix.js`, `scheme.js`, `logos/`, `marks/` with `marks/NOTICE.md`, `LICENSE`, `NOTICE.md`. Copy `tools/check_palette.py` to `.baseline/check_palette.py`, outside the served tree: the build runs it from the repository, so the site copies and pins it, and never serves it. Never copy `reference/`, `tools/measure.js`, `gen_palettes.py`, `contrast-report.txt`, `site-palette.example.css` or the documents.
3. Record the baseline version and each copied file's SHA-256 in `.baseline/pin.toml`:

   ```toml
   version = "1.7.0"

   [files]
   "assets/baseline/baseline.css" = "<sha256>"
   "assets/baseline/palettes.css" = "<sha256>"
   ".baseline/check_palette.py" = "<sha256>"
   ```

   The pin covers 2 locations: `assets/baseline/` (the served runtime and licence files) and `.baseline/` (the build tool `check_palette.py`, never served). A pin gate accepts entries under either location, checks each digest, and fails on an unlisted file in `assets/baseline/`, a listed file that is missing, or an entry outside the 2 locations.

   Add an offline gate that fails if any copied file differs from the pin. Run that gate, the palette gate (mandatory from 1.6.0, below), the security.txt gate and the site's other integrity gates from the Cloudflare Pages build command, so that any failure fails the deploy. No gate reaches the network. The palette gate:

   ```sh
   python3 .baseline/check_palette.py --site <name> --palettes assets/baseline/palettes.css
   # with a site palette file:
   python3 .baseline/check_palette.py --site <name> --palettes assets/baseline/palettes.css --site-palette assets/site-palette.css
   ```

   It prints a contrast table per scheme and exits 0 when every check passes, 1 on any failure or on input it cannot read or evaluate, and 2 on a usage error. The exit code is the contract: a build reads the exit code, never the wording of the printed result line, which may change between releases.
4. Put `class="site-<name>"` on `<html>` (`site-secureconfig`, `site-opfiles`, `site-auditthis`, `site-cleanlanguage`, `site-aiqt`, `site-grclibrary`). That class, the logo files, the content and an optional `site-palette.css` are the only per-site differences. A site must not add CSS that overrides `baseline.css`, with 2 exceptions: an optional `site.css`, loaded after it, may set only the measured per-site constants `--sw` and `--logo-inset` when the site's statement or logo changes (section "Per-site constants"); and, from 1.6.0, an optional `site-palette.css`, loaded immediately after `palettes.css`, may override palette tokens, only at the owner's explicit request (section "Site-owned palette colours"). A need the template cannot meet is a change request to the baseline.
5. Generate every page from the site's own sources with the markup of the reference pages; they are the contract. Every page loads `scheme.js` in `<head>` before the stylesheets (no `defer`), links `fonts.css`, `palettes.css`, the site's `site-palette.css` where it has one, and `baseline.css` in that order, carries the favicon and touch-icon links, the skip link, the top bar with the light and dark switch, 1 `h1`, the footer and the `#copy-status` live region, and contains no inline style, inline script or `on*` attribute. A `<script type="application/ld+json">` block is data and is allowed, on live pages only, never on a noindex draft.
6. Update the site's own gates where they conflict (`SPECIFICATION.md`, section 11).
7. Add this entry to the repository's NOTICE:

   > Site template: the shared site template (baseline <version>, https://posluns.ca/baseline/) is dedicated to the public domain under CC0 1.0 Universal, with 2 exceptions. The fonts Newsreader, Public Sans, JetBrains Mono and Dancing Script are licensed by their authors under the SIL Open Font License 1.1; their licence files are in assets/baseline/fonts/. The GitHub Invertocat, the LinkedIn [in] bug and the ORCID iD icon in assets/baseline/marks/ are trademarks of their owners, used under their owners' published terms as recorded in assets/baseline/marks/NOTICE.md, and are not covered by the CC0 grant.

8. Updates arrive as 1 pull request per site that bumps the pin and the copied files; each site's own checks run as usual.

### Staging at `/draft/` and promotion

1. Base path. Generate every page, asset and internal link with a configurable base path: `/draft/` while staging, `/` after promotion. The draft is self-contained: no draft page links to, or loads anything from, the live pages at the root, except a live file whose path is kept at promotion (for example `/downloads/*`, or opfiles.ai's `/adopt.md`), which a draft page may link rather than copy. The baseline files are copied under the draft (`/draft/assets/baseline/`) and move with it. Every path in this package is relative, so the files work at any base path.
2. Kept out of search and away from the live site. Every draft page carries `<meta name="robots" content="noindex, nofollow">`; `_headers` sends `X-Robots-Tag: noindex` for `/draft/*`; the draft is absent from `sitemap.xml`, `llms.txt` and every other index the live site publishes; the live pages never link to it. Check `_redirects` for a live `/draft` redirect and remove it before staging.
3. Live site unchanged, with 1 exception. Building the draft changes no live page, path, redirect or published file. The exception is the owner-ordered live hardening, in its own pull request ahead of the draft: `/.well-known/security.txt`, `sitemap.xml` and the `Sitemap` line of `robots.txt`, the `apple-touch-icon` links, the removal of a live `/draft` redirect, and the header changes of `SPECIFICATION.md` section 9. Nothing else changes live before promotion. Every existing gate keeps passing on the live tree; gates that scan every HTML file either cover the draft under the template's rules or exclude `/draft/` explicitly, and the exclusion is removed at promotion.
4. Review. The draft is complete when every page of the site's page list exists under `/draft/`, the site's checks and the content guidelines checklist pass, and the implementer has reported to the owner with the draft's URL.
5. Promotion, after the owner's approval only. In 1 pull request: remove the old pages from the published tree (they remain in git history); rebuild the draft with base path `/`; add redirects for every old public path that changes; restore the root's `sitemap.xml`, `llms.txt` and other indexes for the new pages; remove the `/draft/` noindex rules and any gate exclusion; verify every fixed path on the preview deployment before merging.

### Headers

Cloudflare sends only its automatic headers (`X-Content-Type-Options`, `Referrer-Policy`, `Access-Control-Allow-Origin`, HSTS from the zone, `Speculation-Rules` from Speed Brain); no custom Cloudflare rule. The repository's `_headers` sends `Content-Security-Policy`, `X-Frame-Options: DENY`, `Permissions-Policy` and `Cross-Origin-Opener-Policy: same-origin` on `/*`, and on `/draft/*` removes the live CSP, sets the draft CSP and `X-Robots-Tag: noindex`. The shared CSP, the 4 Cloudflare features and their needs, the hash and nonce caveat, the Speed Brain caveat and the proposed Permissions-Policy value are in `SPECIFICATION.md`, section 9.

### Site class, logo and base path

- The site class on `<html>` selects the palette (`palettes.css`) and the per-site constants in `baseline.css` (`--sw`, `--logo-inset`, `--tail-from`).
- The logo appears once per page: in the hero on the landing page (`.hero-art img`), above the rail on every other page (`.rail-logo`); the footer uses all 6 full-colour logos. In the head: `<link rel="icon" href="<base>assets/baseline/logos/<site>-favicon.svg" type="image/svg+xml">` and `<link rel="apple-touch-icon" href="<base>assets/baseline/logos/<site>-touch.png">`; the card logo is for link previews.
- The top bar of every site: the site's own 4 to 6 page links on 1 row, then GitHub as the last, right-most item where the site has a public repository; no Disclosure or Licence item (`SPECIFICATION.md` section 7.1). On a window too narrow for the row, the links scroll sideways and a shadow at the scrolled edge shows that more follow; no script. From 1.6.0 the light and dark switch (`button.scheme`, `scheme.js`, section 7.33) follows the links at the right-hand end, outside the scrolling row; at 1000 px and below it sits at the right of the wordmark. The page follows the device setting until the reader presses it; the choice is stored in `localStorage` (key `scheme`) and applied before the first paint on later pages. Without script the button stays hidden.
- The landing page's "About this project" line, below the value paragraph, links Disclosure, Licence, Privacy (`https://posluns.ca/privacy/`) and Security (`https://posluns.ca/security/`), separated by middle dots, with 1 space after each dot so that the line wraps on phones (from 1.7.0; section 7.24); it is the only place, besides the value paragraph's own licence link, that links the Disclosure and Licence pages. The licence page lives at `/license/` (heading "Licence"), the disclosure page at `/disclosure/`; the disclosure page links the vulnerability disclosure policy and the privacy policy.
- aiqt.ai's rules page keeps the anchors `#rule1` to `#rule5` on its 5 clause sections, so the live redirects from `/rule1` to `/rule5` keep working.

## The reference pages

Each page in `reference/` is built for 1 example site and opens directly from the folder, in light or dark mode as the operating system prefers until the switch in the top bar is pressed; every page, the 404 page included, carries the switch (from 1.6.0). Cross-links between pages that exist in the set go to that page; links to pages of the example site that are not in the set go to `landing.html`, so the set stays self-contained. The pages are markup examples, not a site.

| Page | Example site | What it fixes |
|---|---|---|
| `landing.html` | secureconfig.ai | The hero (kicker, statement, introduction, start link, logo), the "Start here" entry tiles, the "What it gives you" value paragraph, the "About this project" line, the footer |
| `document.html` | aiqt.ai, the standard | The document grid with label column, rail ("On this page"), document control strip, numbered clauses, callout, Next block |
| `reference.html` | aiqt.ai, mappings | Figures, framed registers, a fixed-layout table with `colgroup` widths and wrapping cells, a commit in 7-character form, details blocks |
| `install.html` | cleanlanguage.ai | The selector (`select.js`), download blocks, copy buttons (`copy.js`), steps, the "Last verified" line |
| `license.html` | auditthis.ai | The licence page: scope sentence, parts under another licence, the complete plain-language summary, the owner's note, Next |
| `disclosure.html` | opfiles.ai (entries quoted from the AIQT disclosure as an example of the format) | The disclosure page: opening sentence, entries of claim, limitation and evidence, the security line with the vulnerability disclosure and privacy policy links, Next |
| `404.html` | grclibrary.ai | The 404 page with the logo-only rail |
| `channels.html` | cleanlanguage.ai, by channel | The channel list page: 1 section per channel, each an `h2` and its list of rules, the rail listing the channels, the source callout |
| `checklist.html` | cleanlanguage.ai, checklist | The checklist page: groups of questions as numbered clauses (`N.1`, `N.2`), citable by number |
| `demo.html` | cleanlanguage.ai, try it | The demo page: a before-and-after pair, the prompt in a copy block, the no-script note, the install link |
| `figures.html` | auditthis.ai, references | The 4 components of 1.4.0: the inline accent (`span.accent`), compact figures (`.figures.compact`), a figure beside text (`.fig-aside`) and the brand marker (`mark.marker`) |
| `search.html` | grclibrary.ai, search | `search.js` in results mode (`data-search-mode="results"`): nothing shows until the reader types or picks a filter, title matches rank first, the query and filters in the address (`?q=`, `?domain=`, `?type=`, `?fw=`), facet chips as links; 16 illustrative rows |
| `facets.html` | grclibrary.ai, index | `search.js` facets in the default mode: every row shows, chip groups for domain, type and framework combine with each other and with the query; from 1.7.0 the domain and type chips that would show no documents are marked unavailable (`data-filter-empty="disable"`), and the type chips count the documents each would show (`data-filter-count="live"`); the same 16 illustrative rows |
| `crosswalk.html` | grclibrary.ai, crosswalk | The left-rail page (`.doc.left-rail`, `.lrail`) with 7 views as `matrix.js` presets, the matrix table (`table.matrix`, `data-col`) in the sticky scroll box (`.tablewrap.bounded`, `table.sticky.sticky-col`), `?view=`; 6 domains by 8 instruments, with illustrative identifiers and counts |
| `matrix.html` | grclibrary.ai, large matrix | The large matrix of 1.7.0 (`SPECIFICATION.md` section 7.34): 10 domains by 20 instruments in the combined form (`.tablewrap.bounded` as a named region, `table.matrix.fixed.sticky.sticky-col.pin-cap`), rem column widths (`col.r6` to `col.r24`), wrapping cells (`cells-wrap`, `td.nowrap`), the capped pinned column (`pin-cap`), stripes and row hover (`zebra`, `rowhover`), empty cells (`td.na`), column toggles and `?cols=`, heat shading with its legend (`data-heat`, `.heat-legend`), the column highlight (`data-col-highlight`), rotated headers (`th.rot`) and column groups (`data-grp`, `.grp`); views as `matrix.js` presets; illustrative identifiers, counts and shading |

Sticky tables: from 1.5.0 a table marked `.sticky` sits in a wrapper marked `.tablewrap.bounded`, a box at most 75 % of the viewport height that scrolls in both directions with the header row fixed at its top; add `.sticky-col` to the table to keep the first column at its left (`reference.html`, `crosswalk.html`; `SPECIFICATION.md` section 7.31). From 1.7.0, opt-in, add `.pin-cap` to give the pinned first column a capped width, `clamp(8rem, 30vw, 15rem)`, with wrapping labels; the `pin-r<N>` classes change it. Without `.pin-cap` the column is as in 1.6.1.

Large matrix tables (from 1.7.0, `matrix.html`, `SPECIFICATION.md` section 7.34): each capability is opt-in by a class or an attribute and works without script; the column toggles and the highlight need `matrix.js`. The matrix prints whole, in black on white, with its controls hidden.

Prompt and code blocks come in 2 variants beyond the plain copy block: `pre.prompt-block` (capped at 36rem, scrolls inside, for a prompt the reader copies) and `pre.prompt-flow` (the whole text in the page flow, for a portable text the reader reads in place); both keep the same `pre id`, copy button and status contract.

## Site-owned palette colours

From 1.6.0 a site may override any palette token (`SPECIFICATION.md` section 6.1), light and dark, in its own `site-palette.css`, with no template release. A site does so only at the owner's explicit request.

1. Copy `site-palette.example.css` to the site's asset folder as `site-palette.css` (outside the pinned baseline files) and link it immediately after `palettes.css`.
2. Set each value in both forms of its scheme, with the selectors of `palettes.css`, so that the later file wins whatever the device setting and the switch:

   ```css
   /* light */
   .site-<name> { --link: #...; }
   [data-scheme="light"].site-<name> { --link: #...; }
   /* dark */
   @media (prefers-color-scheme: dark) {
     .site-<name>:not([data-scheme="light"]) { --bg: #...; }
   }
   [data-scheme="dark"].site-<name> { --bg: #...; }
   ```

   The file holds palette tokens only, as `#rgb` or `#rrggbb`, on these selectors; the gate rejects anything else.
3. Run the palette gate with `--site-palette`. It fails if any pairing misses its threshold (text 4.5:1; focus ring, strong rule and rainbow ink 3:1), if the 2 forms of a scheme disagree, or if the file holds anything other than palette tokens.
4. QA, the standard grclibrary.ai set and the owner recorded: a colour change is 1 value in 1 file (in both forms of its scheme); its review is a before and after comparison, of the file and of the rendered pages, showing that only the expected value changed, plus the gate passing.

## Per-site constants

Two values in `baseline.css` depend on a site's content and are measured, not designed. The values shipped in `baseline.css` for the 6 approved statements and logos:

| Site | `--sw` light | `--sw` dark | `--logo-inset` |
|---|---|---|---|
| secureconfig.ai | 13.712 | 14.612 | 0.115 |
| opfiles.ai | 15.070 | 16.070 | 0.1225 |
| auditthis.ai | 12.562 | 13.337 | 0.2075 |
| cleanlanguage.ai | 12.824 | 13.724 | 0.185 |
| aiqt.ai | 19.868 | 21.218 | 0.0975 |
| grclibrary.ai | 13.069 | 13.894 | 0.115 |

- `--sw` (per site, light and dark): the hero statement's width on 1 line in em; dark mode adds 0.01em of tracking, hence the larger dark value. `font-size: clamp(2.6rem, 98cqw / var(--sw), 5rem)` puts the statement on 1 line whenever that fits at 2.6rem or more. The dark value applies in system dark mode and under a forced dark scheme.
- `--logo-inset` (per site): the logo artwork's visible left margin as a fraction of the SVG box, used to indent the rail's text under the artwork's left edge.
- A site re-measures only when its statement's words or its logo change, as a development task on any machine with Node and Playwright, never as a build step: `node tools/measure.js statement <url or file of the landing page>` prints the light and dark `--sw`; `node tools/measure.js logo logos/<site>.svg` prints `--logo-inset`. Set the new values in the site's own `site.css`, loaded after `baseline.css` (`.site-<name> .statement { --sw: ...; }`, the dark value inside `@media (prefers-color-scheme: dark)`, and `.site-<name> .rail { --logo-inset: ...; }`). Never edit the copied `baseline.css`: the pin and its checksum must keep matching. The tool makes no network requests other than loading the page you name (`npx playwright install chromium` once).

## Security contact

Each domain publishes `/.well-known/security.txt` with the W3 fields, pointing at the owner's vulnerability disclosure policy, `https://posluns.ca/security/`; a gate checks the file. The disclosure page's closing line links the same policy and the universal privacy policy, `https://posluns.ca/privacy/`.

## Checking a build

- No en or em dash in any file; no inline style or script (JSON-LD data blocks excepted, live pages only); no `on*` attribute; every external link with `target="_blank" rel="noopener noreferrer"` and a visually hidden "(opens in a new tab)".
- The palette gate passes (`.baseline/check_palette.py`, with the site's `site-palette.css` where it has one).
- Render at 320, 390, 820, 1180, 1512 and 2000 px in light and dark: no horizontal scroll (a bounded table box may scroll inside itself); the light and dark switch visible at the right-hand end of the top bar and toggling the scheme, the choice kept on the next page with no flash of the other scheme, and the button absent without script; the top bar's links on 1 row at every width (scrolling on phones, with the edge shadow), GitHub last where present; exactly 1 GitHub mark displayed in the footer and no blank tile; the footer on 1 line from 600 px of content width and on 2 lines below it; the hero statement on 1 line at 1440 px and above for a 1-sentence statement, in both schemes.
- The landing page within 2 screens at 1180 by 820; body text 20 px on desktop and 18 px on phones.
