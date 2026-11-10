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
  3  the check could not run: the config, the site root, or a page could not be
     read, the config is invalid, or tools/web_metadata.py or
     tools/sitemap_engine.py could not be loaded
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
import types
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent


def _refuse(message: str) -> None:
    print(f"generate-sitemap: {message}", file=sys.stderr)
    raise SystemExit(3)


def _load_sibling(name: str, needs: tuple[str, ...]):
    """Load tools/<name>.py by its explicit path, leaving sys.path unchanged.

    The source is always read, compiled and run as a fresh module, so no cached
    bytecode stands in for it. The module is in sys.modules under name while it
    runs, so a later sibling can import it by that name, and is removed from it
    when the load fails. A source that is not a regular file, or that cannot be
    read, compiled or run, or that lacks any name in needs, means that the
    check could not run (exit 3).
    """
    path = TOOLS_DIR / f"{name}.py"
    try:
        info = os.lstat(path)
    except OSError as error:
        _refuse(f"tools/{path.name} could not be read: {error}")
    if not stat.S_ISREG(info.st_mode):
        _refuse(f"tools/{path.name} is not a regular file")
    try:
        source = path.read_bytes()
    except OSError as error:
        _refuse(f"tools/{path.name} could not be read: {error}")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    try:
        exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    except (Exception, SystemExit) as error:
        sys.modules.pop(name, None)
        _refuse(f"tools/{path.name} could not be loaded: {error!r}")
    for attribute in needs:
        if not hasattr(module, attribute):
            sys.modules.pop(name, None)
            _refuse(f"tools/{path.name} defines no {attribute}")
    return module


# The sibling modules load by explicit path, so sys.path never names the tools
# folder and no file planted there can be imported. web_metadata loads first
# under its own name, because sitemap_engine imports it by that name.
_load_sibling("web_metadata",
              ("UrlError", "parse_origin", "meta_tags", "link_tags", "contained"))
engine = _load_sibling("sitemap_engine",
                       ("EngineError", "EngineRunError", "load_config", "write", "verify"))

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
    except engine.EngineRunError as error:
        # The check could not run: a bad or unreadable config, a missing or
        # escaping site root, or an unreadable page.
        print(f"generate-sitemap: {error}", file=sys.stderr)
        return 3
    except engine.EngineError as error:
        # The tree is in an invalid state: drift, a canonical mismatch, a
        # missing or duplicate stamp, or an empty page set.
        print(f"generate-sitemap: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
