#!/usr/bin/env python3
"""Tests for tools/check-baseline-pin.py: each check fails on a deliberate fault.

Each case builds a small pinned tree in a temporary folder (under $TMPDIR),
with the version's README and specification under ``.baseline/`` and a root
``NOTICE.md``, applies 1 fault, runs the gate on that tree as a separate
process and asserts its exit code, and for some cases a line of its output.
The last case runs the gate on this repository. The first 29 cases run
``tools/copy-baseline.py`` on a small version folder and assert that the pin
header it writes, and the committed one, give each key's base; that it copies
and pins the build tools, the palette gate and the card builder with its
fonts, and counts them among the copied files; that it copies the README and
the specification to ``.baseline/`` without pinning them; that a version
without the palette gate, the card builder, the README or the specification,
or whose README names another version, lacks its step 7 NOTICE entry, holds a second
quoted paragraph in step 7 or has CRLF line ends, on every line or on the
entry line only, exits 1 before any served file is replaced; that a link or a
file in place of ``.baseline/card-fonts/``, a link in place of
``.baseline/check_palette.py``, a link above the served copy folder, or a link
in place of ``site-src/`` or ``site-src/site.json`` makes it exit 1 before any
write, leaving what the link leads to unchanged; that it removes a stray file
and folder from ``.baseline/card-fonts/``; that it ends by running the gate on
the tree it wrote, so a clean copy exits 0 and says that the gate passes it,
and a link elsewhere under ``site/`` makes it exit 1 naming the gate's
problem; that a ``--from`` folder that is a link makes it exit 1 before any
write; that a ``--from`` folder inside the served copy folder or inside
``.baseline/card-fonts/``, or one that holds the repository, makes it exit 1
before any write, naming both paths and leaving the served files unchanged;
that on Python older than 3.11, stood in for by a gate whose tomllib import
fails, it exits 3 with its own message before any served file is replaced;
that a hard link from outside the paths it manages to each file it writes in
``.baseline/`` keeps its content through a clean copy; and that a link in
place of ``tools/__pycache__/`` leads to a folder that gains nothing from a
refused copy. When not run as root, a further case makes ``.baseline/``
read-only and asserts that the copy exits 3 with its own 1 line, which says
that the copy and the pin may be incomplete, rather than a traceback. A
further case asserts that no copy-baseline run in these cases, refused or not,
changes, adds or removes a file or link outside the paths the tool manages or
under its ``--from`` folder, comparing each one's path, inode, size and
SHA-256, or a link's target, before and after the run.
Exit 0 when every case passes; 1 otherwise, naming each failing case.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "tools" / "check-baseline-pin.py"
COPY_TOOL = REPO_ROOT / "tools" / "copy-baseline.py"

FILES = {"baseline.css": b"a { color: red; }\n", "fonts/x.woff2": b"\x00\x01font", "marks/NOTICE.md": b"# marks\n"}
# The rest of the files the gate requires in the pin (REQUIRED), from the README's runtime and licence set:
# among them 5 of its 6 scripts (this site leaves out matrix.js, by the owner's decision).
for _name in ("palettes.css", "fonts.css", "copy.js", "select.js", "search.js", "rail.js", "scheme.js", "LICENSE",
              "NOTICE.md"):
    FILES[_name] = f"/* {_name} */\n".encode()
# The pinned build tool, kept at .baseline/check_palette.py and never served.
TOOL = b"# check_palette.py\n"
TOOL_KEY = ".baseline/check_palette.py"
# The card builder and its fonts, pinned at .baseline/ beside the palette gate and never served; each key's name in
# SHA256SUMS is the key with .baseline/ replaced by tools/.
CARD_KEY = ".baseline/build_card.js"
CARD_FONT_KEY = ".baseline/card-fonts/Inter-Bold.otf"
CARD = {CARD_KEY: b"// build_card.js\n", CARD_FONT_KEY: b"OTTO Inter-Bold",
        ".baseline/card-fonts/Inter-ExtraBold.otf": b"OTTO Inter-ExtraBold",
        ".baseline/card-fonts/Inter-Regular.otf": b"OTTO Inter-Regular",
        ".baseline/card-fonts/inter-LICENSE.txt": b"SIL Open Font License 1.1\n"}
# The version's documents, copied to .baseline/ and not pinned: the README's heading names the version, and its
# step 7 prescribes the NOTICE entry; NOTICE_TEXT carries that entry for 1.2.1.
README = (b"# Baseline 1.2.1: x\n\n7. Add this entry to the repository's NOTICE:\n\n"
          b"   > Site template: baseline <version>, with 2 exceptions.\n\n8. Updates.\n")
DOCS = {"README.md": README, "SPECIFICATION.md": b"# specification\n"}
NOTICE_TEXT = ("# Notice\n\n## Site template\n\nSite template: baseline 1.2.1, with 2 exceptions.\n\n"
               "## Other\n\nx\n")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def package_name(key: str) -> str:
    return "tools/" + key[len(".baseline/"):]


def copied(root: Path) -> Path:
    return root / "site" / "draft" / "assets" / "baseline"


def build(root: Path) -> None:
    for name, data in FILES.items():
        (copied(root) / name).parent.mkdir(parents=True, exist_ok=True)
        (copied(root) / name).write_bytes(data)
    sums = "".join(f"{digest(data)}  {name}\n" for name, data in sorted(FILES.items()))
    sums += f"{digest(b'unpinned')}  reference/landing.html\n"
    sums += f"{digest(TOOL)}  tools/check_palette.py\n"
    sums += "".join(f"{digest(data)}  {package_name(key)}\n" for key, data in CARD.items())
    sums += "".join(f"{digest(data)}  {name}\n" for name, data in DOCS.items())
    (root / ".baseline").mkdir()
    (root / ".baseline" / "SHA256SUMS").write_text(sums, encoding="utf-8")
    (root / TOOL_KEY).write_bytes(TOOL)
    for key, data in CARD.items():
        (root / key).parent.mkdir(parents=True, exist_ok=True)
        (root / key).write_bytes(data)
    for name, data in DOCS.items():
        (root / ".baseline" / name).write_bytes(data)
    (root / "NOTICE.md").write_text(NOTICE_TEXT, encoding="utf-8")
    lines = ["# comment", 'version = "1.2.1"', "", "[files]"]
    lines += [f'"assets/baseline/{name}" = "{digest(data)}"' for name, data in sorted(FILES.items())]
    lines += [f'"{TOOL_KEY}" = "{digest(TOOL)}"']
    lines += [f'"{key}" = "{digest(data)}"' for key, data in CARD.items()]
    (root / ".baseline" / "pin.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "site-src").mkdir()
    (root / "site-src" / "site.json").write_text(json.dumps({"base": "/draft/"}), encoding="utf-8")


def run_gate(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(GATE), str(root)], capture_output=True, text=True)


def run(root: Path) -> int:
    return run_gate(root).returncode


def edit_file(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def edit_pin(root: Path, old: str, new: str) -> None:
    edit_file(root / ".baseline" / "pin.toml", old, new)


def edit_readme(root: Path, old: bytes, new: bytes) -> None:
    """Change the copied README and its SHA256SUMS digest together, so only the README's text is at fault."""
    assert old in README, old
    (root / ".baseline" / "README.md").write_bytes(README.replace(old, new, 1))
    edit_file(root / ".baseline" / "SHA256SUMS", digest(README), digest(README.replace(old, new, 1)))


def fault_flip_byte(root: Path) -> None:
    path = copied(root) / "baseline.css"
    data = bytearray(path.read_bytes())
    data[0] ^= 0x01
    path.write_bytes(bytes(data))


def fault_extra_file(root: Path) -> None:
    (copied(root) / "logos").mkdir()
    (copied(root) / "logos" / "extra.svg").write_bytes(b"<svg/>")


def fault_missing_file(root: Path) -> None:
    (copied(root) / "fonts" / "x.woff2").unlink()


def fault_missing_entry(root: Path) -> None:
    edit_pin(root, f'"assets/baseline/marks/NOTICE.md" = "{digest(FILES["marks/NOTICE.md"])}"\n', "")


def fault_symlink(root: Path) -> None:
    target = copied(root) / "baseline.css"
    real = root / "elsewhere.css"
    real.write_bytes(FILES["baseline.css"])
    target.unlink()
    target.symlink_to(real)


def fault_bad_toml(root: Path) -> None:
    edit_pin(root, "[files]", "[files")


def fault_missing_version(root: Path) -> None:
    edit_pin(root, 'version = "1.2.1"\n', "")


def fault_extra_key(root: Path) -> None:
    edit_pin(root, 'version = "1.2.1"\n', 'version = "1.2.1"\nsource = "x"\n')


def fault_bad_version(root: Path) -> None:
    edit_pin(root, 'version = "1.2.1"', 'version = "1.2"')


def fault_malformed_digest(root: Path) -> None:
    edit_pin(root, digest(FILES["baseline.css"]), "abc")


def fault_path_outside(root: Path) -> None:
    edit_pin(root, '"assets/baseline/baseline.css"', '"assets/../baseline.css"')


def fault_digest_not_published(root: Path) -> None:
    new = b"a { color: blue; }\n"
    (copied(root) / "baseline.css").write_bytes(new)
    edit_pin(root, digest(FILES["baseline.css"]), digest(new))


def fault_rail_js_dropped(root: Path) -> None:
    (copied(root) / "rail.js").unlink()
    edit_pin(root, f'"assets/baseline/rail.js" = "{digest(FILES["rail.js"])}"\n', "")


def fault_scheme_js_dropped(root: Path) -> None:
    (copied(root) / "scheme.js").unlink()
    edit_pin(root, f'"assets/baseline/scheme.js" = "{digest(FILES["scheme.js"])}"\n', "")


def fault_tool_edited(root: Path) -> None:
    (root / TOOL_KEY).write_bytes(TOOL + b"# edited\n")


def fault_tool_deleted(root: Path) -> None:
    (root / TOOL_KEY).unlink()


def fault_tool_unpinned(root: Path) -> None:
    edit_pin(root, f'"{TOOL_KEY}" = "{digest(TOOL)}"\n', "")


def fault_tool_digest_not_published(root: Path) -> None:
    new = TOOL + b"# other\n"
    (root / TOOL_KEY).write_bytes(new)
    edit_pin(root, digest(TOOL), digest(new))


def fault_tool_served(root: Path) -> None:
    (root / "site" / "check_palette.py").write_bytes(TOOL)


def fault_other_baseline_key(root: Path) -> None:
    edit_pin(root, f'"{TOOL_KEY}" = "{digest(TOOL)}"\n',
             f'"{TOOL_KEY}" = "{digest(TOOL)}"\n".baseline/other.py" = "{digest(TOOL)}"\n')


def fault_card_builder_edited(root: Path) -> None:
    (root / CARD_KEY).write_bytes(CARD[CARD_KEY] + b"// edited\n")


def fault_card_font_deleted(root: Path) -> None:
    (root / CARD_FONT_KEY).unlink()


def fault_card_builder_unpinned(root: Path) -> None:
    edit_pin(root, f'"{CARD_KEY}" = "{digest(CARD[CARD_KEY])}"\n', "")


def fault_card_builder_digest_not_published(root: Path) -> None:
    new = CARD[CARD_KEY] + b"// other\n"
    (root / CARD_KEY).write_bytes(new)
    edit_pin(root, digest(CARD[CARD_KEY]), digest(new))


def fault_card_font_served(root: Path) -> None:
    (root / "site" / "Inter-Bold.otf").write_bytes(CARD[CARD_FONT_KEY])


def fault_card_font_unpinned(root: Path) -> None:
    (root / ".baseline" / "card-fonts" / "Inter-Thin.otf").write_bytes(b"OTTO Inter-Thin")


def fault_card_fonts_link(root: Path) -> None:
    # The same files in a folder elsewhere, reached through a link, so each pinned font still hashes to its digest.
    fonts = root / ".baseline" / "card-fonts"
    shutil.move(fonts, root / "fonts-elsewhere")
    fonts.symlink_to(root / "fonts-elsewhere")


def fault_card_fonts_file(root: Path) -> None:
    shutil.rmtree(root / ".baseline" / "card-fonts")
    (root / ".baseline" / "card-fonts").write_bytes(b"x")


def fault_card_fonts_inner_link(root: Path) -> None:
    (root / "elsewhere").mkdir()
    (root / ".baseline" / "card-fonts" / "more").symlink_to(root / "elsewhere")


def fault_served_link_to_fonts(root: Path) -> None:
    # A served folder that is a link to the pinned font folder, so the fonts are served under other paths.
    (root / "site" / "card-assets").symlink_to(root / ".baseline" / "card-fonts")


def fault_copy_folder_link(root: Path) -> None:
    # The same files in a folder elsewhere, reached through a link in place of the copy folder.
    shutil.move(copied(root), root / "copy-elsewhere")
    copied(root).symlink_to(root / "copy-elsewhere")


def fault_site_link(root: Path) -> None:
    shutil.move(root / "site", root / "site-elsewhere")
    (root / "site").symlink_to(root / "site-elsewhere")


def fault_pin_folder_link(root: Path) -> None:
    shutil.move(root / ".baseline", root / "baseline-elsewhere")
    (root / ".baseline").symlink_to(root / "baseline-elsewhere")


def fault_card_data_pinned(root: Path) -> None:
    edit_pin(root, f'"{CARD_KEY}" = "{digest(CARD[CARD_KEY])}"\n',
             f'"{CARD_KEY}" = "{digest(CARD[CARD_KEY])}"\n".baseline/site-card.toml" = "{digest(TOOL)}"\n')


def fault_promoted_base(root: Path) -> None:
    (root / "site-src" / "site.json").write_text(json.dumps({"base": "/"}), encoding="utf-8")


def fault_missing_pin(root: Path) -> None:
    (root / ".baseline" / "pin.toml").unlink()


def fault_missing_sums(root: Path) -> None:
    (root / ".baseline" / "SHA256SUMS").unlink()


def fault_unlistable(root: Path) -> None:
    os.chmod(copied(root) / "fonts", 0)


def fault_other_version(root: Path) -> None:
    # NOTICE.md moves with the pin, so only the README's heading can tell that SHA256SUMS belongs to 1.2.1.
    edit_pin(root, 'version = "1.2.1"', 'version = "1.2.0"')
    edit_file(root / "NOTICE.md", "baseline 1.2.1", "baseline 1.2.0")


def fault_readme_unlisted(root: Path) -> None:
    edit_file(root / ".baseline" / "SHA256SUMS", f"{digest(README)}  README.md\n", "")


def fault_readme_edited(root: Path) -> None:
    (root / ".baseline" / "README.md").write_bytes(README + b"x\n")


def fault_readme_missing(root: Path) -> None:
    (root / ".baseline" / "README.md").unlink()


def fault_readme_no_heading(root: Path) -> None:
    edit_readme(root, b"# Baseline 1.2.1: x", b"# The template 1.2.1: x")


def fault_readme_no_entry(root: Path) -> None:
    edit_readme(root, b"Add this entry to", b"Add an entry to")


def fault_readme_crlf(root: Path) -> None:
    edit_readme(root, README, README.replace(b"\n", b"\r\n"))


def fault_readme_second_quote(root: Path) -> None:
    edit_readme(root, b"exceptions.\n\n8.", b"exceptions.\n\n   > A 3rd exception: x.\n\n8.")


def readme_quote_in_step_8(root: Path) -> None:
    edit_readme(root, b"8. Updates.\n", b"8. Updates.\n\n   > A quote: x.\n")


def fault_spec_edited(root: Path) -> None:
    (root / ".baseline" / "SPECIFICATION.md").write_bytes(DOCS["SPECIFICATION.md"] + b"x\n")


def fault_spec_missing(root: Path) -> None:
    (root / ".baseline" / "SPECIFICATION.md").unlink()


def fault_notice_three_exceptions(root: Path) -> None:
    edit_file(root / "NOTICE.md", "with 2 exceptions", "with 3 exceptions")


def fault_notice_other_version(root: Path) -> None:
    edit_file(root / "NOTICE.md", "baseline 1.2.1", "baseline 1.2.0")


def fault_notice_no_section(root: Path) -> None:
    edit_file(root / "NOTICE.md", "## Site template\n", "## Template\n")


def fault_notice_second_paragraph(root: Path) -> None:
    edit_file(root / "NOTICE.md", "with 2 exceptions.\n", "with 2 exceptions.\n\nAnd more.\n")


def fault_notice_nested_subsection(root: Path) -> None:
    edit_file(root / "NOTICE.md", "with 2 exceptions.\n",
              "with 2 exceptions.\n\n### Exceptions\n\nA 3rd exception: x.\n")


def fault_notice_missing(root: Path) -> None:
    (root / "NOTICE.md").unlink()


def fault_readme_entry_crlf(root: Path) -> None:
    edit_readme(root, b"with 2 exceptions.\n", b"with 2 exceptions.\r\n")


def fault_notice_nested_tab_subsection(root: Path) -> None:
    edit_file(root / "NOTICE.md", "with 2 exceptions.\n",
              "with 2 exceptions.\n\n###\tExceptions\n\nA 3rd exception: x.\n")


def fault_notice_lookalike_heading(root: Path) -> None:
    # The exact heading and the prescribed entry sit in an HTML comment that a heading line ends; the rendered file
    # shows the "## Site template " heading, with a trailing space, and its other entry.
    edit_file(root / "NOTICE.md", "## Site template\n", "<!--\n## Site template\n")
    edit_file(root / "NOTICE.md", "## Other\n",
              "## Other -->\n\n## Site template \n\nSite template: baseline 1.2.1, with 3 exceptions.\n\n"
              "## Other\n")


def fault_notice_comment(root: Path) -> None:
    edit_file(root / "NOTICE.md", "with 2 exceptions.\n", "with 2 exceptions.\n\n<!--\nA 3rd exception: x.\n-->\n")


def fault_notice_backtick_fence(root: Path) -> None:
    edit_file(root / "NOTICE.md", "with 2 exceptions.\n", "with 2 exceptions.\n\n```\nA 3rd exception: x.\n```\n")


def fault_notice_tilde_fence(root: Path) -> None:
    edit_file(root / "NOTICE.md", "with 2 exceptions.\n", "with 2 exceptions.\n\n~~~\nA 3rd exception: x.\n~~~\n")


def fault_notice_lookalike_other_case(root: Path) -> None:
    # The heading in another letter case, after the section, with its other entry.
    edit_file(root / "NOTICE.md", "## Other\n\nx\n",
              "## Other\n\nx\n\n## Site Template\n\nSite template: baseline 1.2.1, with 3 exceptions.\n")


def fault_notice_comment_before_section(root: Path) -> None:
    edit_file(root / "NOTICE.md", "# Notice\n", "# Notice\n\n<!-- x\n")


def fault_notice_fence_after_section(root: Path) -> None:
    edit_file(root / "NOTICE.md", "## Other\n\nx\n", "## Other\n\n   ~~~~\nx\n   ~~~~\n")


def fault_readme_list_item_quote(root: Path) -> None:
    edit_readme(root, b"exceptions.\n\n8.", b"exceptions.\n\n   - > A 3rd exception: x.\n\n8.")


def fault_readme_numbered_item_quote(root: Path) -> None:
    edit_readme(root, b"exceptions.\n\n8.", b"exceptions.\n\n   1. > A 3rd exception: x.\n\n8.")


def fault_readme_blockquote(root: Path) -> None:
    edit_readme(root, b"exceptions.\n\n8.", b"exceptions.\n\n   <BLOCKQUOTE>A 3rd exception.</BLOCKQUOTE>\n\n8.")


def fault_readme_lazy_continuation(root: Path) -> None:
    # The line continues the entry's quoted paragraph, so the rendered entry is longer than its line.
    edit_readme(root, b"exceptions.\n\n8.", b"exceptions.\nA 3rd exception: x.\n\n8.")


def fault_readme_text_before_entry(root: Path) -> None:
    edit_readme(root, b"NOTICE:\n\n   > ", b"NOTICE:\n\n   First, a line of text.\n\n   > ")


# Valid level 1 or 2 headings that end the Site template section, so the lines after them are not compared: the
# clean NOTICE.md's "## Other" in another form.
def end_tab(root: Path) -> None:
    edit_file(root / "NOTICE.md", "## Other\n", "##\tOther\n")


def end_bare_level_2(root: Path) -> None:
    edit_file(root / "NOTICE.md", "## Other\n", "##\n")


def end_bare_level_1(root: Path) -> None:
    edit_file(root / "NOTICE.md", "## Other\n", "#\n")


def end_indented(root: Path) -> None:
    edit_file(root / "NOTICE.md", "## Other\n", "   # Other\n")


CASES = [
    ("clean tree passes", None, 0),
    ("1 flipped byte", fault_flip_byte, 1),
    ("1 extra file", fault_extra_file, 1),
    ("1 missing file", fault_missing_file, 1),
    ("1 missing pin entry", fault_missing_entry, 1),
    ("a symlink in place of a file", fault_symlink, 1),
    ("a digest the published sums do not list", fault_digest_not_published, 1),
    ("rail.js dropped from the copy and the pin", fault_rail_js_dropped, 1),
    ("scheme.js dropped from the copy and the pin", fault_scheme_js_dropped, 1),
    ("the pinned build tool edited", fault_tool_edited, 1),
    ("the pinned build tool deleted", fault_tool_deleted, 1),
    ("the build tool's pin entry removed", fault_tool_unpinned, 1),
    ("the build tool pinned with a digest the published sums do not list", fault_tool_digest_not_published, 1),
    ("a check_palette.py under the served site/ tree", fault_tool_served, 1),
    ("the pinned card builder edited", fault_card_builder_edited, 1, "differs from its pinned digest"),
    ("a pinned card font deleted", fault_card_font_deleted, 1, f"{CARD_FONT_KEY} is pinned but missing"),
    ("the card builder's pin entry removed", fault_card_builder_unpinned, 1, f"{CARD_KEY} is part of"),
    ("the card builder pinned with a digest the published sums do not list", fault_card_builder_digest_not_published,
        1, f"{CARD_KEY} is pinned with a digest"),
    ("an Inter-Bold.otf under the served site/ tree", fault_card_font_served, 1, "site/Inter-Bold.otf is a pinned"),
    ("an unpinned file in .baseline/card-fonts/", fault_card_font_unpinned, 1,
        ".baseline/card-fonts/Inter-Thin.otf is not in the pin"),
    ("a link in place of the .baseline/card-fonts/ folder", fault_card_fonts_link, 1,
        ".baseline/card-fonts is a link, not a folder"),
    ("a file in place of the .baseline/card-fonts/ folder", fault_card_fonts_file, 1,
        ".baseline/card-fonts is not a folder"),
    ("a link to a folder inside .baseline/card-fonts/", fault_card_fonts_inner_link, 1,
        ".baseline/card-fonts/more is a link"),
    ("a site/card-assets link to .baseline/card-fonts/", fault_served_link_to_fonts, 1, "site/card-assets is a link"),
    ("a link in place of the copy folder", fault_copy_folder_link, 1, "site/draft/assets/baseline is a link"),
    ("a link in place of the site/ folder", fault_site_link, 1, "site is a link, not a folder"),
    ("a link in place of the .baseline/ folder", fault_pin_folder_link, 1, ".baseline is a link, not a folder"),
    ("the pin moved to another version, NOTICE.md with it", fault_other_version, 1, "different versions"),
    ("the README not listed in SHA256SUMS", fault_readme_unlisted, 1, "SHA256SUMS does not list README.md"),
    ("the copied README edited", fault_readme_edited, 1),
    ("the copied specification edited", fault_spec_edited, 1),
    ("a NOTICE entry with 3 exceptions", fault_notice_three_exceptions, 1, "NOTICE.md's '## Site template'"),
    ("a NOTICE entry naming another version", fault_notice_other_version, 1),
    ("no Site template section in NOTICE.md", fault_notice_no_section, 1),
    ("a second paragraph in the Site template section", fault_notice_second_paragraph, 1),
    ("a ### subsection under the Site template section", fault_notice_nested_subsection, 1,
        "NOTICE.md's '## Site template'"),
    ("a ### subsection with a tab under the Site template section", fault_notice_nested_tab_subsection, 1,
        "NOTICE.md's '## Site template'"),
    ("a '## Site template ' heading beside the exact one in an HTML comment", fault_notice_lookalike_heading, 1,
        "reads as that heading"),
    ("an HTML comment in the Site template section", fault_notice_comment, 1,
        "an HTML comment opener or a code fence"),
    ("a ``` fence in the Site template section", fault_notice_backtick_fence, 1,
        "an HTML comment opener or a code fence"),
    ("a ~~~ fence in the Site template section", fault_notice_tilde_fence, 1,
        "an HTML comment opener or a code fence"),
    ("a '## Site Template' heading in another letter case after the section", fault_notice_lookalike_other_case, 1,
        "reads as that heading"),
    ("an HTML comment opener before the Site template section", fault_notice_comment_before_section, 1,
        "an HTML comment opener or a code fence"),
    ("a ~~~~ fence indented 3 spaces after the Site template section", fault_notice_fence_after_section, 1,
        "an HTML comment opener or a code fence"),
    ("a README with a quoted line in step 8, outside step 7", readme_quote_in_step_8, 0),
    ("the Site template section ended by a level 2 heading with a tab", end_tab, 0),
    ("the Site template section ended by a bare ##", end_bare_level_2, 0),
    ("the Site template section ended by a bare #", end_bare_level_1, 0),
    ("the Site template section ended by a level 1 heading indented 3 spaces", end_indented, 0),
    ("malformed TOML", fault_bad_toml, 3),
    ("no version", fault_missing_version, 3),
    ("a key outside the README format", fault_extra_key, 3),
    ("a version that is not X.Y.Z", fault_bad_version, 3),
    ("a malformed digest", fault_malformed_digest, 3),
    ("a path outside assets/baseline/", fault_path_outside, 3),
    ("an unknown .baseline/ key", fault_other_baseline_key, 3),
    ("the card's data file .baseline/site-card.toml pinned", fault_card_data_pinned, 3),
    ("the base path moved to / with the files still under draft/", fault_promoted_base, 3),
    ("the pin is missing", fault_missing_pin, 3),
    ("SHA256SUMS is missing", fault_missing_sums, 3),
    ("the copied README is missing", fault_readme_missing, 3),
    ("a README without its version heading", fault_readme_no_heading, 3),
    ("a README without its step 7 NOTICE entry", fault_readme_no_entry, 3),
    ("a README with CRLF line ends", fault_readme_crlf, 3),
    ("a README whose step 7 holds a second, blank-separated quoted paragraph", fault_readme_second_quote, 3),
    ("a README with CRLF only on its step 7 entry line", fault_readme_entry_crlf, 3),
    ("a README whose step 7 holds a list item that is a quote", fault_readme_list_item_quote, 3),
    ("a README whose step 7 holds a numbered list item that is a quote", fault_readme_numbered_item_quote, 3),
    ("a README whose step 7 holds a <BLOCKQUOTE>", fault_readme_blockquote, 3),
    ("a README whose step 7 entry has a line directly after it", fault_readme_lazy_continuation, 3),
    ("a README whose step 7 holds a line of text before the entry", fault_readme_text_before_entry, 3),
    ("the copied specification is missing", fault_spec_missing, 3),
    ("NOTICE.md is missing", fault_notice_missing, 3),
]


# The paths copy-baseline manages, relative to the repository root, with the output root at site/ as run_copy's
# site-src/site.json sets it: the folders it clears and rebuilds, and the files it writes in .baseline/.
MANAGED_FOLDERS = ("site/assets/baseline/", ".baseline/card-fonts/")
MANAGED_FILES = {TOOL_KEY, CARD_KEY, ".baseline/SHA256SUMS", ".baseline/pin.toml",
                 *(f".baseline/{name}" for name in DOCS)}
# Each copy-baseline run in which a file outside MANAGED_FOLDERS and MANAGED_FILES, or under the --from folder,
# changed, appeared or went away.
OUTSIDE_CHANGES: list[str] = []


def unmanaged(root: Path, version: Path) -> dict[str, tuple]:
    """Every file and link under root outside the paths copy-baseline manages, and every one under the --from folder
    wherever it is, by path, with its inode, size and SHA-256, or a link's target. Links are recorded, never
    followed."""
    found: dict[str, tuple] = {}
    for top, everything in ((root, False), (version, True)):
        for folder, folders, files in os.walk(top):
            for name in folders + files:
                path = Path(folder) / name
                relative = os.path.relpath(path, root).replace(os.sep, "/")
                if not everything and (relative in MANAGED_FILES or relative.startswith(MANAGED_FOLDERS)):
                    continue
                if os.path.islink(path):
                    found[str(path)] = ("link", os.readlink(path))
                elif path.is_file():
                    status = path.stat()
                    found[str(path)] = (status.st_ino, status.st_size, digest(path.read_bytes()))
    return found


def run_copy(root: Path, package: dict[str, bytes], gate: bytes | None = None,
             source_link: bool = False, version: Path | None = None) -> subprocess.CompletedProcess:
    """Run tools/copy-baseline.py in root on a version folder 1.2.1 that holds package and its SHA256SUMS, with the
    gate (or the given gate source) beside it, from which it loads notice_entry() and check(), and a NOTICE.md that
    carries the 1.2.1 entry, so that the gate's check at the end passes a clean copy. A site-src/ that the caller
    has already made, as a folder or a link, is kept, and so is a tools/ folder. With source_link, 1.2.1 is a link
    to the version folder. With version, the version folder is made there instead, and its SHA256SUMS lists every
    file in it, so that a version folder that holds the repository still matches its sums. Whatever the outcome,
    any file outside the paths the tool manages, or under the version folder, that differs after the run from
    before it is recorded in OUTSIDE_CHANGES."""
    (root / "tools").mkdir(exist_ok=True)
    shutil.copyfile(COPY_TOOL, root / "tools" / COPY_TOOL.name)
    (root / "tools" / GATE.name).write_bytes(GATE.read_bytes() if gate is None else gate)
    (root / "NOTICE.md").write_text(NOTICE_TEXT, encoding="utf-8")
    if not os.path.lexists(root / "site-src"):
        (root / "site-src").mkdir()
        (root / "site-src" / "site.json").write_text(json.dumps({"base": "/"}), encoding="utf-8")
    if version is None:
        version = root / "version-elsewhere" / "1.2.1" if source_link else root / "1.2.1"
    for name, data in package.items():
        (version / name).parent.mkdir(parents=True, exist_ok=True)
        (version / name).write_bytes(data)
    names = sorted(path.relative_to(version).as_posix() for path in version.rglob("*") if path.is_file())
    sums = "".join(f"{digest((version / name).read_bytes())}  {name}\n" for name in names if name != "SHA256SUMS")
    (version / "SHA256SUMS").write_text(sums, encoding="utf-8")
    if source_link:
        (root / "1.2.1").symlink_to(version)
    command = [sys.executable, "-I", str(root / "tools" / COPY_TOOL.name), "--from",
               str(root / "1.2.1" if source_link else version),
               "--sums-sha256", digest(sums.encode()), "--archive-sha256", "0" * 64]
    before = unmanaged(root, version)
    result = subprocess.run(command, capture_output=True, text=True)
    after = unmanaged(root, version)
    changed = sorted((before.keys() ^ after.keys()) | {path for path in before.keys() & after.keys()
                                                      if before[path] != after[path]})
    if changed:
        OUTSIDE_CHANGES.append(f"copy-baseline (exit {result.returncode}) changed "
                               f"{[os.path.relpath(path, root) for path in changed]}")
    return result


PACKAGE = {**FILES, **DOCS, "tools/check_palette.py": TOOL, **{package_name(key): data for key, data in CARD.items()}}
# Versions copy-baseline refuses (exit 1) before it replaces a served file: each changes PACKAGE in place.
COPY_REFUSALS = [
    ("a version without the build tool", lambda package: package.pop("tools/check_palette.py")),
    ("a version without the card builder", lambda package: package.pop(package_name(CARD_KEY))),
    ("a version without README.md", lambda package: package.pop("README.md")),
    ("a version without SPECIFICATION.md", lambda package: package.pop("SPECIFICATION.md")),
    ("a README whose heading names another version",
        lambda package: package.update({"README.md": README.replace(b"Baseline 1.2.1", b"Baseline 1.2.0")})),
    ("a README without its step 7 NOTICE entry",
        lambda package: package.update({"README.md": README.replace(b"   > ", b"")})),
    ("a README whose step 7 holds a second, blank-separated quoted paragraph",
        lambda package: package.update({"README.md": README.replace(
            b"exceptions.\n\n", b"exceptions.\n\n   > A 3rd exception: x.\n\n")})),
    # The gate reads the README's bytes without newline translation and refuses this one (exit 3), so copying it
    # would only fail at deploy.
    ("a README with CRLF line ends",
        lambda package: package.update({"README.md": README.replace(b"\n", b"\r\n")})),
    # The gate refuses this one too (exit 3), as it refuses a carriage return anywhere in the README.
    ("a README with CRLF only on its step 7 entry line",
        lambda package: package.update({"README.md": README.replace(b"exceptions.\n", b"exceptions.\r\n")})),
]


def link_card_fonts(root: Path) -> None:
    (root / ".baseline").mkdir()
    (root / ".baseline" / "card-fonts").symlink_to(root / "outside")


def file_card_fonts(root: Path) -> None:
    (root / ".baseline").mkdir()
    (root / ".baseline" / "card-fonts").write_bytes(b"x")


def link_build_tool(root: Path) -> None:
    (root / "outside" / "check_palette.py").write_bytes(b"# outside\n")
    (root / ".baseline").mkdir()
    (root / TOOL_KEY).symlink_to(root / "outside" / "check_palette.py")


def link_served_parent(root: Path) -> None:
    # site/assets/ is a link, so the served copy folder below it is reached through the link.
    (root / "outside" / "baseline").mkdir()
    (root / "outside" / "baseline" / "served-before.css").write_bytes(b"a { color: red; }\n")
    (root / "site").mkdir()
    (root / "site" / "assets").symlink_to(root / "outside")


def link_site_src(root: Path) -> None:
    # site-src/ is a link, so the output root would come from a site.json outside the tree; the gate follows it.
    (root / "outside" / "site.json").write_text(json.dumps({"base": "/"}), encoding="utf-8")
    (root / "site-src").symlink_to(root / "outside")


def link_site_json(root: Path) -> None:
    # site-src/site.json is a link, which the gate refuses (exit 3).
    (root / "outside" / "site.json").write_text(json.dumps({"base": "/"}), encoding="utf-8")
    (root / "site-src").mkdir()
    (root / "site-src" / "site.json").symlink_to(root / "outside" / "site.json")


# Trees copy-baseline refuses (exit 1) before its first write: each makes a folder it writes into, a file it writes,
# or the site-src/site.json it reads the output root from, a link or of the wrong kind. What the link leads to, in
# outside/, lies outside the paths the tool manages, so run_copy checks that it is unchanged.
COPY_TREE_REFUSALS = [
    ("a link in place of .baseline/card-fonts/", link_card_fonts),
    ("a file in place of .baseline/card-fonts/", file_card_fonts),
    ("a link in place of .baseline/check_palette.py", link_build_tool),
    ("a link in place of site/assets/, above the served copy folder", link_served_parent),
    ("a link in place of site-src/", link_site_src),
    ("a link in place of site-src/site.json", link_site_json),
]


def copy_tree_problems() -> list[str]:
    """copy-baseline refuses each tree in COPY_TREE_REFUSALS before it writes, and rebuilds .baseline/card-fonts/
    without the stray entries a previous copy or a hand edit left there."""
    problems = []
    for name, prepare in COPY_TREE_REFUSALS:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "outside").mkdir()
            prepare(root)
            served = root / "site" / "assets" / "baseline" / "served-before.css"
            if not served.exists():
                served.parent.mkdir(parents=True)
                served.write_bytes(b"a { color: red; }\n")
            result = run_copy(root, dict(PACKAGE))
            if result.returncode != 1 or not served.is_file():
                problems.append(f"copy-baseline: {name} exits {result.returncode}; expected 1 before any write, the "
                                f"served files kept: {result.stderr.strip()[:200]!r}")
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        fonts = root / ".baseline" / "card-fonts"
        (fonts / "old").mkdir(parents=True)
        (fonts / "Inter-Thin.otf").write_bytes(b"OTTO Inter-Thin")
        result = run_copy(root, dict(PACKAGE))
        left = sorted(path.relative_to(root).as_posix() for path in fonts.rglob("*"))
        if result.returncode != 0 or left != sorted(key for key in CARD if key.startswith(".baseline/card-fonts/")):
            problems.append(f"copy-baseline: a stray file and folder in .baseline/card-fonts/: exit "
                            f"{result.returncode}, the folder holds {left}; expected 0 and only the pinned fonts")
    return problems


def copy_gate_problems() -> list[str]:
    """copy-baseline reports success only on a tree the gate passes: a clean copy exits 0 and says that the gate
    passes it, a link elsewhere under site/, which no check before the first write covers, makes it exit 1 naming
    the gate's problem, and a --from folder that is a link is refused before any write."""
    problems = []
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        result = run_copy(root, dict(PACKAGE))
        if (result.returncode != 0 or "check-baseline-pin.py passes the tree" not in result.stdout
                or run(root) != 0):
            problems.append(f"copy-baseline: a clean copy exits {result.returncode} with {result.stdout.strip()!r}; "
                            "expected 0, saying that the gate passes the tree, and the gate passing it")
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        (root / "outside").mkdir()
        (root / "site").mkdir()
        (root / "site" / "elsewhere").symlink_to(root / "outside")
        result = run_copy(root, dict(PACKAGE))
        if result.returncode != 1 or "site/elsewhere is a link" not in result.stderr:
            problems.append(f"copy-baseline: a link elsewhere under site/ exits {result.returncode}; expected 1, "
                            f"naming the gate's problem: {result.stderr.strip()[:200]!r}")
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        served = root / "site" / "assets" / "baseline" / "served-before.css"
        served.parent.mkdir(parents=True)
        served.write_bytes(b"a { color: red; }\n")
        result = run_copy(root, dict(PACKAGE), source_link=True)
        if result.returncode != 1 or not served.is_file() or (root / ".baseline").exists():
            problems.append(f"copy-baseline: a --from folder that is a link exits {result.returncode}; expected 1 "
                            f"before any write: {result.stderr.strip()[:200]!r}")
    return problems


def python_floor_problems() -> list[str]:
    """On Python older than 3.11 the gate's tomllib guard exits 3; copy-baseline catches that and reports it in its
    own words before it replaces a served file. A gate whose tomllib import fails stands in for the old Python."""
    source = GATE.read_bytes()
    if source.count(b"\n    import tomllib\n") != 1:
        return ["the Python floor: the gate's 'import tomllib' is not once in tools/check-baseline-pin.py"]
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        served = root / "site" / "assets" / "baseline" / "served-before.css"
        served.parent.mkdir(parents=True)
        served.write_bytes(b"a { color: red; }\n")
        gate = source.replace(b"\n    import tomllib\n", b"\n    import tomllib_absent_here\n", 1)
        result = run_copy(root, dict(PACKAGE), gate)
        lines = result.stderr.splitlines()
        if (result.returncode != 3 or not served.is_file() or len(lines) != 1
                or not lines[0].startswith("copy-baseline: Python 3.11 or later is required")):
            return [f"the Python floor: copy-baseline exits {result.returncode} with "
                    f"{result.stderr.strip()[:200]!r}; expected 3 with its own 1 line naming Python 3.11, "
                    "the served files kept"]
    return []


def source_in_served_folder(scratch: Path) -> tuple[Path, Path]:
    return scratch, scratch / "site" / "assets" / "baseline" / "1.2.1"


def source_in_card_fonts(scratch: Path) -> tuple[Path, Path]:
    return scratch, scratch / ".baseline" / "card-fonts" / "1.2.1"


def source_holding_repository(scratch: Path) -> tuple[Path, Path]:
    return scratch / "1.2.1" / "repo", scratch / "1.2.1"


# --from folders copy-baseline refuses (exit 1) before its first write, since the copy would delete or change each
# one: each layout gives the repository root and the version folder, and the message names both.
COPY_SOURCE_REFUSALS = [
    ("a --from folder inside the served copy folder", source_in_served_folder, "is inside site/assets/baseline"),
    ("a --from folder inside .baseline/card-fonts/", source_in_card_fonts, "is inside .baseline/card-fonts"),
    ("a --from folder that holds the repository", source_holding_repository, "holds site/assets/baseline"),
]


def copy_source_problems() -> list[str]:
    """copy-baseline refuses each --from folder in COPY_SOURCE_REFUSALS before it writes, naming the folder and the
    path it overlaps, and leaves the served files as they were; run_copy checks every file in the version folder."""
    problems = []
    for name, layout, needle in COPY_SOURCE_REFUSALS:
        with tempfile.TemporaryDirectory() as scratch:
            root, version = layout(Path(scratch))
            served = root / "site" / "assets" / "baseline" / "served-before.css"
            served.parent.mkdir(parents=True)
            served.write_bytes(b"a { color: red; }\n")
            result = run_copy(root, dict(PACKAGE), version=version)
            if (result.returncode != 1 or not served.is_file()
                    or (root / ".baseline" / "pin.toml").exists()
                    or f"{version} {needle}" not in result.stderr or "Traceback" in result.stderr):
                problems.append(f"copy-baseline: {name} exits {result.returncode}; expected 1 before any write, "
                                f"naming {str(version)!r} and saying {needle!r}, the served files kept: "
                                f"{result.stderr.strip()[-200:]!r}")
    return problems


def write_failure_problems() -> list[str]:
    """A file that cannot be written once copying has begun makes copy-baseline exit 3 with its own 1 line, not a
    traceback. A .baseline/ that the user cannot write to stands in for the failure."""
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        (root / ".baseline").mkdir()
        os.chmod(root / ".baseline", 0o555)
        try:
            result = run_copy(root, dict(PACKAGE))
        finally:
            os.chmod(root / ".baseline", 0o755)
        lines = result.stderr.splitlines()
        if (result.returncode != 3 or len(lines) != 1
                or not lines[0].startswith("copy-baseline: a file could not be read or written")
                or not lines[0].endswith("; the copy and the pin may be incomplete")):
            return [f"copy-baseline: a file it cannot write exits {result.returncode} with "
                    f"{result.stderr.strip()[-200:]!r}; expected 3 with its own 1 line, saying that the copy and "
                    "the pin may be incomplete"]
    return []


def alias_problems() -> list[str]:
    """copy-baseline writes each file as a new file and renames it into place, so a hard link to a file it writes in
    .baseline/, from outside the paths it manages, keeps its content; and it loads the gate without writing byte
    code, so a tools/__pycache__/ link gains nothing, even on a refused copy."""
    problems = []
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        (root / "outside").mkdir()
        (root / ".baseline").mkdir()
        aliases = {}
        for relative in sorted(MANAGED_FILES):
            alias = root / "outside" / Path(relative).name
            alias.write_bytes(f"not managed: {relative}\n".encode())
            os.link(alias, root / relative)
            aliases[alias] = alias.read_bytes()
        result = run_copy(root, dict(PACKAGE))
        changed = [alias.name for alias, data in aliases.items() if alias.read_bytes() != data]
        if result.returncode != 0 or changed or (root / CARD_KEY).read_bytes() != CARD[CARD_KEY]:
            problems.append(f"copy-baseline: a hard link from outside to each file it writes in .baseline/: exit "
                            f"{result.returncode}, the outside files changed {changed}; expected 0, each kept, and "
                            f"the copy written: {result.stderr.strip()[-200:]!r}")
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        (root / "outside").mkdir()
        (root / "tools").mkdir()
        (root / "tools" / "__pycache__").symlink_to(root / "outside")
        package = dict(PACKAGE)
        package.pop(package_name(CARD_KEY))
        result = run_copy(root, package)
        left = sorted(path.name for path in (root / "outside").iterdir())
        if result.returncode != 1 or left:
            problems.append(f"copy-baseline: a link in place of tools/__pycache__/ with a refused copy: exit "
                            f"{result.returncode}, the folder it leads to holds {left}; expected 1 and nothing there")
    return problems


def copy_problems() -> list[str]:
    """copy-baseline pins and copies the build tools, counts them, copies the documents unpinned, and checks for each
    and for the README's version and NOTICE entry before replacing a file."""
    problems = []
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        result = run_copy(root, dict(PACKAGE))
        pin = (root / ".baseline" / "pin.toml").read_text(encoding="utf-8") if result.returncode == 0 else ""
        if f'"{TOOL_KEY}" = "{digest(TOOL)}"\n' not in pin or (root / TOOL_KEY).read_bytes() != TOOL:
            problems.append(f"copy-baseline: the build tool is not copied to {TOOL_KEY} and pinned "
                            f"(exit {result.returncode})")
        for key, data in CARD.items():
            if f'"{key}" = "{digest(data)}"\n' not in pin or (root / key).read_bytes() != data:
                problems.append(f"copy-baseline: {package_name(key)} is not copied to {key} and pinned "
                                f"(exit {result.returncode})")
        if f"copied {len(FILES) + 1 + len(CARD)} files " not in result.stdout:
            problems.append(f"copy-baseline: the count of copied files leaves out a build tool: "
                            f"{result.stdout.strip()!r}")
        documents = root / ".baseline"
        if (not pin or any(not (documents / name).is_file() or (documents / name).read_bytes() != data
                           or name in pin for name, data in DOCS.items())):
            problems.append(f"copy-baseline: the documents are not copied to .baseline/ unpinned "
                            f"(exit {result.returncode})")
    for name, change in COPY_REFUSALS:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            served = root / "site" / "assets" / "baseline" / "served-before.css"
            served.parent.mkdir(parents=True)
            served.write_bytes(b"a { color: red; }\n")
            package = dict(PACKAGE)
            change(package)
            result = run_copy(root, package)
            if result.returncode != 1 or not served.is_file():
                kept = "keeps" if served.is_file() else "replaces"
                problems.append(f"copy-baseline: {name} exits {result.returncode} "
                                f"and {kept} the served files; expected 1 and keeps")
    return problems


def pin_header_problems() -> list[str]:
    """The pin's header, as tools/copy-baseline.py writes it and as committed, gives each key's base."""
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        result = run_copy(root, dict(PACKAGE))
        if result.returncode != 0:
            return [f"the pin header: copy-baseline exit {result.returncode}: {result.stderr.strip()[:200]}"]
        written = (root / ".baseline" / "pin.toml").read_text(encoding="utf-8")
    committed = (REPO_ROOT / ".baseline" / "pin.toml").read_text(encoding="utf-8")

    def header(text: str) -> str:
        lines = text.splitlines()
        return " ".join(lines[:next(i for i, line in enumerate(lines) if line.startswith("# Source:"))])

    problems = []
    if header(written) != header(committed):
        problems.append("the pin header: the committed .baseline/pin.toml header is not copy-baseline's")
    for statement in ("assets/baseline/ are relative to the site's output root",
                      "each build tool's key under .baseline/ is relative to the repository root"):
        if statement not in header(written).replace("# ", ""):
            problems.append(f"the pin header does not say {statement!r}")
    return problems


def main() -> int:
    failures: list[str] = (pin_header_problems() + copy_problems() + copy_tree_problems() + copy_gate_problems()
                           + python_floor_problems() + copy_source_problems() + alias_problems())
    ran = 11 + len(COPY_REFUSALS) + len(COPY_TREE_REFUSALS) + len(COPY_SOURCE_REFUSALS)
    # As root, file permissions do not stop a write, so the write failure cannot be stood in for.
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        failures += write_failure_problems()
        ran += 1
    # Every copy-baseline run above, refused or not, leaves each file outside the paths it manages as it was.
    failures += [f"{change}, outside the paths it manages" for change in OUTSIDE_CHANGES]
    ran += 1
    for name, fault, expected, *needles in CASES:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            build(root)
            if fault:
                fault(root)
            result = run_gate(root)
            ran += 1
            if result.returncode != expected:
                failures.append(f"{name}: exit {result.returncode}, expected {expected}")
            elif any(needle not in result.stdout for needle in needles):
                failures.append(f"{name}: the output does not say {needles}: {result.stdout.strip()[:200]!r}")
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            build(root)
            fault_unlistable(root)
            try:
                code = run(root)
            finally:
                os.chmod(copied(root) / "fonts", 0o755)
            ran += 1
            if code != 3:
                failures.append(f"an unlistable folder: exit {code}, expected 3")
    code = run(REPO_ROOT)
    ran += 1
    if code != 0:
        failures.append(f"this repository: exit {code}, expected 0")
    if failures:
        print("test-baseline-pin: failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"test-baseline-pin: all {ran} cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
