# Clean Language website

The `site/` directory contains the static website published at [cleanlanguage.ai](https://cleanlanguage.ai).

## Cloudflare Pages deployment

Connect the GitHub repository to Cloudflare Pages using these settings:

- Production branch: `main`
- Framework preset: `None`
- Build command: `bash tools/pages-build.sh`
- Build output directory: `site`
- Root directory: leave blank
- Environment variable `PYTHON_VERSION`: leave unset; the `.python-version` file at the repository root names the Python version (see below)

Add `cleanlanguage.ai` as the custom domain after the first deployment.

Cloudflare Pages publishes `site/` exactly as it is committed; the build changes no file. The template specification asks the build command to run the site's offline integrity gates (section 4, step 3). On the checked-out tree, [`tools/pages-build.sh`](../tools/pages-build.sh) runs the 5 offline gates that the owner named, `check-baseline-pin`, `check-security-txt`, `check-headers`, `check-inline-code` and `build-site --check`, and no others. Each of these gates reads only the repository, with no network and no git history, except that `check-security-txt` also reads the clock: it fails once the `Expires` date in `site/.well-known/security.txt` has passed, so before then the owner chooses a new date and changes it in every file that holds it: that file, `tools/check-security-txt.py` and `tools/test-security-txt.py`. They need Python 3.11 or later; `check-inline-code` needs 3.14.

If any gate fails, or a gate file is missing, the build fails, that commit is not deployed, and the build log names the gate and the problem. Once the build command is set, a branch that does not yet contain `tools/pages-build.sh` also fails its build (bash exits 127 and no gate runs); merging `main` into that branch fixes it. Fix the cause in a pull request; never remove a gate to make a deploy pass. The same 5 gates also run in GitHub Actions on pull requests and on pushes to `main`. The site's other checks run in GitHub Actions, not in the build, on the triggers that each workflow sets: these are the other offline gates, such as `generate-sitemap.py` and `check-release-links.py`, and the checks that need git history or the network. [`tools/test-pages-build.py`](../tools/test-pages-build.py) fails if the build script stops running a listed gate or stops failing when a gate exits 1 or 3.

Cloudflare's [build image page](https://developers.cloudflare.com/pages/configuration/build-image/) (read on 3 November 2026) gives 3.13.3 as the default Python of its v3 build image, and the first Pages build of this site ran Python 3.13.3. The same page says that a project chooses another version with the `PYTHON_VERSION` environment variable or with a `.python-version` or `runtime.txt` file at its root directory, so the `.python-version` file at the repository root names a 3.14 release, 3.14.4. [`tools/test-pages-build.py`](../tools/test-pages-build.py) fails if `.python-version` is missing or names a version outside the versions that `check-inline-code` supports.

In GitHub Actions, each workflow that runs `check-inline-code`, directly or through a page check, first runs [`tools/check-python-version.py`](../tools/check-python-version.py), which, on Python 3.7 or later, exits 3 unless the runner's `python3` is exactly the release that `.python-version` names, so a runner image that moves to another release fails those workflows until `.python-version` is updated in a pull request. `tools/test-pages-build.py` reads the workflows in `.github/workflows` whose name ends in `.yml` and fails if a job whose steps name the gate, a page check, `tools/pages-build.sh` or `tools/release-dry-run.sh` has an `if:` or `continue-on-error`, or does not run that check exactly, with no other key, as its first step after checkout, or if no job names one. The check confirms only that the runner's interpreter matches the file; it says nothing about the Pages build image.

The same file names the Python of the Pages build, so an edit to `.python-version` also moves the Pages build to that release: merge it only once the pull request's Cloudflare Pages preview build passes.

Nothing in this repository verifies that Pages honours the file: the first line that the build script writes to the build log names the Python version, and so does the pass or fail line of `check-inline-code`; those lines show the version a build ran. If that version is older than 3.11, the script stops before any gate; if it is any version other than 3.14, `check-inline-code` exits 3 and fails the build. In either case, correct `.python-version` in a pull request; if the log shows that Pages ignores the file, set the `PYTHON_VERSION` environment variable in the Cloudflare Pages settings to the release that the file names.

To roll back, clear the build command in the Cloudflare Pages settings; Pages then publishes `site/` without running the gates.

## How the pages are made

The pages are generated on the shared site template (baseline) by [`tools/build-site.py`](../tools/build-site.py), from the sources in [`site-src/`](../site-src/) and the skill's own files. The generated pages are committed, so never edit one by hand: change its source, run `python3 -I tools/build-site.py`, and commit the source and the regenerated page together. `python3 -I tools/build-site.py --check` verifies that the committed `site/` is exactly what the sources produce, beside the hand-maintained files that `site-src/site.json` lists as `static_files`, and CI fails if it drifts.

## Site contents

Generated by `tools/build-site.py`:

- `index.html`: the home page
- `standard/index.html`: overview of the standard
- `examples/index.html`: before-and-after examples, generated from the skill's examples
- `patterns/index.html`: common AI-writing patterns and anti-patterns
- `install/index.html`: the downloads and the setup information for every AI system, with a button to each AI system's own setup page
- `install/claude/index.html`, `install/chatgpt/index.html`, `install/gemini/index.html`, `install/copilot/index.html`, `install/other-ai/index.html`: click-by-click setup for each AI system
- `verify/index.html`: plain-language download verification guide
- `instructions/index.html`: the full instructions as copyable plain text, embedding `downloads/cleanlanguage.md` exactly
- `channels/index.html`: context rules by channel and document type
- `checklist/index.html`: the quality checklist
- `demo/index.html`: a before-and-after example and a prompt to try
- `disclosure/index.html`: what the project claims, the limit of each claim, and the evidence, with the privacy policy and vulnerability disclosure links
- `license/index.html`: the licence, summarized in plain language
- `404.html`: not-found page
- `draft/index.html`: the holding page for drafts under review; it is `noindex`, no page links to it, and it is absent from the sitemap

Copied and pinned:

- `assets/baseline/`: the template's stylesheets, scripts, fonts, logos and marks, copied byte for byte by [`tools/copy-baseline.py`](../tools/copy-baseline.py), pinned in [`.baseline/pin.toml`](../.baseline/pin.toml) and checked by [`tools/check-baseline-pin.py`](../tools/check-baseline-pin.py)

Hand-maintained or generated by other tools:

- `images/cleanlanguage-card.png`: social sharing preview image, committed byte
  for byte; its sources and provenance notes live in [`scripts/card/`](../scripts/card/)
- `downloads/`: the size-labelled portable Clean Language files. `cleanlanguage.md` is the canonical file and mirrors the largest rendering byte-for-byte; `cleanlanguage-29k.md` is that largest rendering, generated by `tools/build-portable-text.py`; `cleanlanguage-11k.md` and `cleanlanguage-8k.md` are hand-maintained condensations (at most 11000 and 8000 characters)
- `robots.txt`: crawler directives
- `.well-known/security.txt`: the security contact file (RFC 9116), checked by
  [`tools/check-security-txt.py`](../tools/check-security-txt.py)
- `sitemap.xml`: search-engine sitemap, generated from the pages by [`tools/generate-sitemap.py`](../tools/generate-sitemap.py) and verified byte for byte by a gate
- `_headers`: Cloudflare Pages security and caching headers, checked by
  [`tools/check-headers.py`](../tools/check-headers.py)
- `_redirects`: download shortcuts to the latest release assets, the old download names, and the retired paths: `/privacy/` to [posluns.ca/privacy](https://posluns.ca/privacy/), and the old icon paths to the pinned logos. [`tools/set-release-links.py`](../tools/set-release-links.py) rewrites it on each release.

When you add, remove, or restamp a page, regenerate the sitemap and commit it alongside the page: run `python3 tools/generate-sitemap.py --write`, then review the resulting change to `site/sitemap.xml`. The bare `python3 tools/generate-sitemap.py` verifies the committed file matches the pages, and CI fails if it drifts.
