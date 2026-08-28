#!/usr/bin/env python3
"""Generate or verify site/sitemap.xml from the page tree.

Default (no flag) is the gate: it re-derives the sitemap from the pages and
their stamps and compares byte for byte against the committed file, so a
hand edit, a stale entry, or a forgotten regeneration fails loudly. `--write`
regenerates the file. All the work lives in the portable `sitemap_engine`
module; this is the thin project entry point.

Exit codes:
  0  the committed sitemap matches (verify), or it was written (--write)
  1  the committed sitemap drifted, or an input was invalid
  2  the command line was wrong
  3  the check could not run: the config or site root could not be read
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sitemap_engine as engine  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "tools" / "sitemap-config.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or verify the sitemap.")
    parser.add_argument("--write", action="store_true", help="regenerate the sitemap file")
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="path to the sitemap config"
    )
    args = parser.parse_args()

    try:
        config = engine.load_config(args.config)
        if args.write:
            count = engine.write(config, REPO_ROOT)
            print(f"generate-sitemap: wrote {config['output']} with {count} pages.")
            return 0
        ok, message = engine.verify(config, REPO_ROOT)
        print(f"generate-sitemap: {message}")
        return 0 if ok else 1
    except engine.EngineError as error:
        # A drift is a 1; an unreadable config or site root is a 3. The message
        # already names which; distinguish on the two "cannot run" phrasings.
        text = str(error)
        if text.startswith("cannot read config") or "site root" in text or "config" in text:
            print(f"generate-sitemap: {text}", file=sys.stderr)
            return 3
        print(f"generate-sitemap: {text}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
