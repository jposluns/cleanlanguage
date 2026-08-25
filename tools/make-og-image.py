#!/usr/bin/env python3
"""Redraw the headline and URL lines of the Open Graph card.

``site/cleanlanguage-card.png`` is the social sharing card that every page references as
``og:image``. It entered the repository as a bare PNG with no source file and no
generator, so changing a single word of it once meant recovering its typography
from the raster. This script holds that recovered typography, so the next change
is an edit rather than an excavation.

What it does, and does not do
-----------------------------

This is a band editor, not a card generator. It takes the existing card as its
base and redraws two regions: the two headline lines and the URL line. The logo
lockup and the subtitle keep their original pixels untouched, because their
parameters were never recovered. It therefore cannot build the card from
nothing; it needs the committed PNG to start from.

The recovered typography
------------------------

Every value below was measured by fitting rendered glyph bitmaps against the
committed PNG, not assumed:

* Headline: DejaVu Sans Bold, 72px, tracking -2.5px, pure white. Mean per-glyph
  overlap against the original is 0.971, and four of six test words reproduce
  the original ink width exactly.
* URL: DejaVu Sans Bold, 25px, tracking -0.5px, RGB(169, 198, 182). Reproduces
  the original 230 by 24 ink box exactly.
* Background: ``#145C3B``, the site's ``theme-color``.

The card was never set in Inter, despite the site's stylesheet naming Inter
first. It was rendered on a host where Inter was not installed, so the stack
``Inter, ui-sans-serif, system-ui, ..., sans-serif`` fell through to the default
sans. The giveaway is the full stop: a sharp-cornered rectangle in the original,
where Inter's is round.

Requirements
------------

Pillow, and DejaVu Sans Bold installed. Neither is declared as a repository
dependency, because this script is a maintenance tool rather than part of the
site build. Both are checked at startup and reported plainly if missing.

Usage
-----

    tools/make-og-image.py --check
        Redraw with the committed text and confirm the result matches the
        committed PNG byte for byte. Exits non-zero on any drift.

    tools/make-og-image.py --line1 "..." --line2 "..." --url "..."
        Rewrite the card in place.

    tools/make-og-image.py --out /tmp/candidate.png
        Write a candidate elsewhere, leaving the committed card alone.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - environment problem, not a code path
    print(
        "make-og-image: Pillow is not installed. Install it with: "
        "python3 -m pip install Pillow",
        file=sys.stderr,
    )
    raise SystemExit(3)

REPO_ROOT = Path(__file__).resolve().parent.parent
CARD = REPO_ROOT / "site" / "cleanlanguage-card.png"

CANVAS = (1200, 630)
BACKGROUND = (20, 92, 59)

# Candidate locations for DejaVu Sans Bold, tried in order before asking
# fontconfig. A specific file is used rather than a family name so the output
# does not change when the host's font set changes.
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/local/share/fonts/DejaVuSans-Bold.ttf",
)
FONT_PATTERN = "DejaVu Sans:style=Bold"

# Headline: two lines sharing one pen origin, with the band that is cleared
# before redrawing. Ink occupies rows 241..310 and 317..387 once drawn.
HEADLINE = dict(size=72, tracking=-2.5, colour=(255, 255, 255), pen_x=88)
HEADLINE_BASELINES = (294, 372)
HEADLINE_BAND = (232, 396)

# URL line. Aligned by its first ink pixel rather than by pen origin, so it sits
# flush with the logo lockup and subtitle at x=88 whatever the leading glyph is.
URL = dict(size=25, tracking=-0.5, colour=(169, 198, 182))
URL_BASELINE = 536
URL_BAND = (510, 547)
URL_INK_LEFT = 88

# The text the committed card carries. --check compares against these.
DEFAULT_LINE_1 = "Make AI writing sound"
DEFAULT_LINE_2 = "precise, direct, and natural."
DEFAULT_URL = "https://cleanlanguage.ai"

# Keep the rightmost ink this far inside the canvas. The design's own right
# margin is 192px on the longest original line; anything under this reads as
# crowded and is more likely a mistake than a choice.
MIN_RIGHT_MARGIN = 40


def fail(message: str) -> None:
    print(f"make-og-image: {message}", file=sys.stderr)
    raise SystemExit(3)


def resolve_font() -> str:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    if shutil.which("fc-match"):
        found = subprocess.run(
            ["fc-match", "--format=%{file}", FONT_PATTERN],
            capture_output=True,
            text=True,
        ).stdout.strip()
        if found and Path(found).is_file() and "DejaVuSans-Bold" in found:
            return found
    fail(
        "DejaVu Sans Bold was not found. Install it (Debian and Ubuntu: "
        "fonts-dejavu-core) and try again. Substituting another face would "
        "change the card's typography silently."
    )
    raise AssertionError("unreachable")


def draw_tracked(draw, text: str, spec: dict, pen_x: float, baseline: int, font) -> None:
    """Draw one line, advancing per character so tracking can be applied.

    Pillow has no letter-spacing control, and the original card carries negative
    tracking, so each glyph is placed individually at the accumulated pen
    position. ``anchor="ls"`` puts the baseline where the original's is.
    """
    x = float(pen_x)
    for character in text:
        draw.text((x, baseline), character, font=font, fill=spec["colour"], anchor="ls")
        x += font.getlength(character) + spec["tracking"]


def ink_extent(text: str, spec: dict, pen_x: float, baseline: int, font) -> tuple[int, int]:
    """Return the leftmost and rightmost ink columns a line would occupy.

    Rendered on an oversized scratch canvas so a line that would overflow the
    real one is still measured rather than clipped.
    """
    probe = Image.new("L", (CANVAS[0] * 2, CANVAS[1]), 0)
    scratch = ImageDraw.Draw(probe)
    x = float(pen_x)
    for character in text:
        scratch.text((x, baseline), character, font=font, fill=255, anchor="ls")
        x += font.getlength(character) + spec["tracking"]
    bbox = probe.getbbox()
    if bbox is None:
        fail(f"the line {text!r} rendered no ink")
    return bbox[0], bbox[2] - 1


def pen_for_ink_left(text: str, spec: dict, baseline: int, target_left: int, font) -> float:
    """Pen origin that puts the first ink pixel of ``text`` at ``target_left``."""
    left, _ = ink_extent(text, spec, 0, baseline, font)
    return target_left - left


def build(base: Path, out: Path, line1: str, line2: str, url: str) -> None:
    if not base.is_file():
        fail(f"the base card {base} does not exist; this tool edits it, it cannot create it")

    font_path = resolve_font()
    headline_font = ImageFont.truetype(font_path, HEADLINE["size"])
    url_font = ImageFont.truetype(font_path, URL["size"])

    image = Image.open(base).convert("RGB")
    if image.size != CANVAS:
        fail(
            f"the base card is {image.size[0]} by {image.size[1]}, expected "
            f"{CANVAS[0]} by {CANVAS[1]}; the og:image dimension tags assume the latter"
        )

    # Refuse to ship a line that runs off the canvas. This is the failure the
    # original two-line headline hit, and it is silent in the output.
    for text, baseline in zip((line1, line2), HEADLINE_BASELINES):
        _, right = ink_extent(text, HEADLINE, HEADLINE["pen_x"], baseline, headline_font)
        margin = CANVAS[0] - 1 - right
        if margin < MIN_RIGHT_MARGIN:
            fail(
                f"the line {text!r} ends at x={right}, leaving {margin}px of right "
                f"margin; at least {MIN_RIGHT_MARGIN}px is required. Shorten it, "
                f"move the line break, or lower MIN_RIGHT_MARGIN deliberately."
            )

    draw = ImageDraw.Draw(image)
    draw.rectangle([0, HEADLINE_BAND[0], CANVAS[0] - 1, HEADLINE_BAND[1] - 1], fill=BACKGROUND)
    draw.rectangle([0, URL_BAND[0], CANVAS[0] - 1, URL_BAND[1] - 1], fill=BACKGROUND)

    for text, baseline in zip((line1, line2), HEADLINE_BASELINES):
        draw_tracked(draw, text, HEADLINE, HEADLINE["pen_x"], baseline, headline_font)

    url_pen = pen_for_ink_left(url, URL, URL_BASELINE, URL_INK_LEFT, url_font)
    draw_tracked(draw, url, URL, url_pen, URL_BASELINE, url_font)

    image.save(out)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Redraw the headline and URL lines of site/cleanlanguage-card.png.",
    )
    parser.add_argument("--line1", default=DEFAULT_LINE_1, help="first headline line")
    parser.add_argument("--line2", default=DEFAULT_LINE_2, help="second headline line")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL line text")
    parser.add_argument("--base", type=Path, default=CARD, help="card to draw on top of")
    parser.add_argument("--out", type=Path, default=None, help="where to write; defaults to --base")
    parser.add_argument(
        "--check",
        action="store_true",
        help="redraw the committed text and confirm the output matches the committed card",
    )
    args = parser.parse_args()

    if args.check:
        import tempfile

        with tempfile.TemporaryDirectory() as workdir:
            candidate = Path(workdir) / "cleanlanguage-card.png"
            build(args.base, candidate, DEFAULT_LINE_1, DEFAULT_LINE_2, DEFAULT_URL)
            expected, actual = sha256_of(args.base), sha256_of(candidate)
            if expected == actual:
                print(f"The committed card is reproducible. sha256 {expected}")
                return 0
            print("The committed card does not match what this script produces.")
            print(f"  committed: {expected}")
            print(f"  redrawn:   {actual}")
            print(
                "Either the card was edited by another route, or the recovered "
                "typography in this script has drifted from it."
            )
            return 1

    out = args.out or args.base
    build(args.base, out, args.line1, args.line2, args.url)
    print(f"Wrote {out}")
    print(f"  headline: {args.line1} / {args.line2}")
    print(f"  url:      {args.url}")
    print(f"  sha256:   {sha256_of(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
