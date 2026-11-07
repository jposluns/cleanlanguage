#!/usr/bin/env python3
"""Tests for tools/check-baseline-pin.py and tools/copy-baseline.py.

Each gate case but the last builds a small pinned tree in a temporary folder
(under $TMPDIR), with the version's README and specification under
``.baseline/`` and a root ``NOTICE.md``, applies 1 fault, or none for the
clean tree, runs the gate on that tree as a separate process and asserts its
exit code, and for some cases a line of its output. The last case runs the
gate on this repository. The copy-baseline cases run
``tools/copy-baseline.py`` on a small version folder and assert:

- what it copies and pins: the runtime and licence files to the served copy
  folder, under site/ or, with the base path /draft/, under site/draft/, and
  never matrix.js, reference/ or tools/; the build tools, the palette gate and
  the card builder with its fonts, copied, pinned and counted; the README and
  the specification copied to ``.baseline/`` unpinned; and the pin header;
- what it refuses (exit 1) before any served file is replaced, each case
  asserting the message of the refusal it names, which the other checks that
  can refuse the same file in 1 run do not print, so that a case fails when
  that refusal alone is removed:
  a SHA256SUMS that does not hash to the digest given; a file that does not
  match its digest, that SHA256SUMS does not list, or that it lists and the
  folder lacks; a SHA256SUMS line with text after its file name, or that names
  a file twice, by an absolute path or above the folder, each named with its
  line number; a FIFO, or a link that leads to a FIFO, in place of SHA256SUMS
  or of the gate, each refused by the check made before the open, and a link
  in place of a file in the version folder;
  a version without the palette gate, the card builder, the README or the
  specification; a README that names another version, lacks its step 7 NOTICE
  entry, holds a second quoted paragraph in step 7 or has CRLF line ends, on
  every line or on the entry line only; a link or a file in place of
  ``.baseline/card-fonts/``, a link or a folder in place of
  ``.baseline/check_palette.py``, a link above the served copy folder, a link
  in place of ``site-src/``, and a link or a folder in place of
  ``site-src/site.json``, leaving what a link leads to unchanged; a
  ``--from`` folder that is a link; and a ``--from`` folder inside the
  served copy folder or ``.baseline/card-fonts/``, reached through a link
  into the served copy folder, or holding the repository, naming both paths;
- what else it refuses before its first write, each with the message of its
  own refusal: SHA256SUMS replaced by a FIFO (exit 1) or by a link (exit 3)
  between its check and its open, stood in for by code appended to the gate
  that sends the tool's open to a FIFO or a link outside the version folder;
  a gate that does not compile, a ``site-src/`` without ``site.json``, a
  ``site-src/site.json`` without a base path, and a SHA256SUMS or README that
  is not UTF-8 (each exit 3); and, when not run as root, a ``--from`` folder
  that cannot be listed and a ``.baseline/`` that cannot be searched (each
  exit 3);
- that it removes a stray file and folder from ``.baseline/card-fonts/``;
- that it ends by running the gate on the tree it wrote: a clean copy exits 0
  and says that the gate passes it; a link elsewhere under ``site/``, or a
  ``NOTICE.md`` entry naming the previous version, makes it exit 1 naming the
  gate's problem; and, when not run as root, a folder under ``site/`` that
  cannot be listed makes it exit 3 saying that the gate could not check it;
- how it fails with its own 1 line and never a traceback: on Python older
  than 3.11, stood in for by a gate whose tomllib import fails, it exits 3
  before any served file is replaced; an error that is not an OSError, raised
  by code appended to the gate, exits 3 before any write, or, after the first
  change, exits 3 saying that the copy and the pin may be incomplete; a
  ``--from`` folder whose name is not a version number, and a
  ``--sums-sha256`` that is not 64 lower-case hexadecimal digits, each exit 1;
  a ``--sums-sha256``, an ``--archive-sha256`` and a ``--from`` folder name
  that each end in a newline exit 1, and a base path in
  ``site-src/site.json`` that ends in one exits 3, each before its first
  write, on a version that is otherwise valid; a ``--from`` folder that does
  not exist exits 3; and, when not run as root, a read-only ``.baseline/``
  exits 3 saying that the copy and the pin may be incomplete;
- what argparse handles, with argparse's own output rather than the tool's 1
  line: no options exits 2 with argparse's usage and error lines, and
  ``--help`` exits 0 with its help, each with nothing written;
- that it opens each file in the version folder exactly once in its own
  process, counted by an audit hook on Python's ``open`` event that code
  appended to the gate adds, so a second open through ``builtins.open``,
  ``io.open``, ``os.open`` or anything built on them, such as
  ``shutil.copyfile``, is counted; an ``os.open`` of a path relative to a
  folder's descriptor (``dir_fd``), which the hook resolves against the
  working folder instead, a second read through the same open file, and a
  read by another process are not;
- that a hard link from outside the paths it manages to each file it writes in
  ``.baseline/`` keeps its content through a clean copy, that a link in place
  of ``tools/__pycache__/`` leads to a folder that gains nothing from a
  refused copy, and that an unchecked hash-based cache file for the gate under
  ``tools/__pycache__/``, which the normal loader would run, is never run;
- and that no copy-baseline run in these cases, refused or not, changes, adds
  or removes a file or link outside the paths the tool manages or under its
  ``--from`` folder, comparing each one's path, inode, size and SHA-256, or
  a link's target, before and after the run; and that no run among them that
  ends before its first write, refused or stopped, changes, adds or removes a
  folder, file or link under the test's repository root or its ``--from``
  folder, managed paths included, comparing each folder's and each file's
  mode and modification time as well. Neither comparison covers anything
  else, such as ownership, access time or what is in a folder that the test
  cannot list. A run ends before its first write
  when it does not say that it wrote the copy and the pin or that they may be
  incomplete, as the tool's exit codes give, so the second comparison is made
  after every refused run in these cases, and after ``--help``, without a
  case having to ask for it. Every run goes through
  ``copy_run()``, which makes both comparisons and stops a run still going
  after ``COPY_TIMEOUT`` seconds, so that a run that blocks, such as on a
  FIFO, fails its case instead of hanging the suite, and a further case reads this
  file's source and fails if any other code refers to the tool's path, names
  its file outside a docstring, or starts a process, apart from
  ``run_gate()``, which runs the gate. A run written to avoid that reading,
  such as one that assembles the file name from pieces, is not detected.

The tool compares the ``--from`` folder with the paths it writes by device and
inode. No case here tells that apart from a comparison of resolved names: both
catch a link, and only 2 paths to 1 folder that ``resolve()`` does not merge,
such as a bind mount, would separate them, which needs privileges these tests
do not assume.

Exit 0 when every case passes; 1 otherwise, naming each failing case.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import py_compile
import shutil
import stat
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


def fault_version_newline(root: Path) -> None:
    edit_pin(root, 'version = "1.2.1"', 'version = "1.2.1\\n"')


def fault_digest_newline(root: Path) -> None:
    edit_pin(root, f'"{digest(FILES["baseline.css"])}"', f'"{digest(FILES["baseline.css"])}\\n"')


def fault_path_newline(root: Path) -> None:
    edit_pin(root, '"assets/baseline/baseline.css"', '"assets/baseline/baseline.css\\n"')


def fault_base_newline(root: Path) -> None:
    # The copy moves to where the base path with its newline leads, site/draft/<newline>/, so a gate that matched the
    # base path only up to its newline would find every file in place and pass.
    (root / "site" / "draft" / "\n").mkdir()
    shutil.move(copied(root).parent, root / "site" / "draft" / "\n" / "assets")
    (root / "site-src" / "site.json").write_text(json.dumps({"base": "/draft/\n"}), encoding="utf-8")


def fault_promoted_base(root: Path) -> None:
    (root / "site-src" / "site.json").write_text(json.dumps({"base": "/"}), encoding="utf-8")


def fault_sums_line_malformed(root: Path) -> None:
    with (root / ".baseline" / "SHA256SUMS").open("a", encoding="utf-8") as stream:
        stream.write(f"{digest(b'extra')}  extra.css extra\n")


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
    ("a version that ends in a newline", fault_version_newline, 3),
    ("a pinned digest that ends in a newline", fault_digest_newline, 3),
    ("a pinned path that ends in a newline", fault_path_newline, 3),
    ("a base path that ends in a newline, with the copy where it leads", fault_base_newline, 3),
    ("a path outside assets/baseline/", fault_path_outside, 3),
    ("an unknown .baseline/ key", fault_other_baseline_key, 3),
    ("the card's data file .baseline/site-card.toml pinned", fault_card_data_pinned, 3),
    ("the base path moved to / with the files still under draft/", fault_promoted_base, 3),
    ("the pin is missing", fault_missing_pin, 3),
    ("SHA256SUMS is missing", fault_missing_sums, 3),
    ("a SHA256SUMS line with text after its file name", fault_sums_line_malformed, 3,
        ".baseline/SHA256SUMS line ", " is malformed"),
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


# The paths copy-baseline manages, relative to the repository root: the folders it clears and rebuilds, the served
# copy folder among them under the output root that site-src/site.json gives, and the files it writes in .baseline/.
MANAGED_FILES = {TOOL_KEY, CARD_KEY, ".baseline/SHA256SUMS", ".baseline/pin.toml",
                 *(f".baseline/{name}" for name in DOCS)}


def managed_folders(root: Path) -> tuple[str, ...]:
    """The folders copy-baseline clears in root: the served copy folder under the output root that a readable
    site-src/site.json gives (site/ otherwise, as run_copy sets it), and .baseline/card-fonts/."""
    try:
        base = json.loads((root / "site-src" / "site.json").read_text(encoding="utf-8"))["base"]
    except (OSError, ValueError, KeyError, TypeError):
        base = "/"
    served = "site/" if base == "/" else f"site/{str(base).strip('/')}/"
    return (f"{served}assets/baseline/", ".baseline/card-fonts/")


# Each copy-baseline run in which a file outside managed_folders() and MANAGED_FILES, or under the --from folder,
# changed, appeared or went away.
OUTSIDE_CHANGES: list[str] = []
# Each copy-baseline run that ended before its first write, by the tool's own account, in which anything under the
# test's root or the --from folder changed, appeared or went away, managed paths included.
REFUSED_CHANGES: list[str] = []
# What the tool says when it ends after its first write: on stderr, the gate's check after the copy, or a failure once
# copying has begun; on stdout, a clean copy. Any other run, --help among them, has by the tool's exit-code contract
# ended before it.
AFTER_WRITE = ("wrote the copy and the pin", "the copy and the pin may be incomplete", "wrote .baseline/pin.toml")
# The seconds a copy-baseline run may take: a run that blocks, such as on a FIFO it opens, fails its case instead of
# hanging the suite. A run here takes well under 1 second.
COPY_TIMEOUT = 30
# The exit code that copy_run() reports for a run stopped at COPY_TIMEOUT, which the tool never returns.
TIMED_OUT = -1


def tree_state(root: Path, version: Path | None) -> dict[str, tuple]:
    """root itself and each folder, file and link that os.walk() lists under it, and the same under the --from folder
    wherever it is, when there is one, by path: a folder's mode and modification time, which a name created, renamed
    or removed in it changes; a file's inode, size, SHA-256, mode and modification time; a link's target; and any
    other entry's mode, such as a FIFO's. os.walk() passes over a folder that it cannot list, so nothing in one is
    recorded, as in the case whose --from folder can be searched but not listed. A link under root or the --from
    folder is recorded, never followed."""
    found: dict[str, tuple] = {}
    for top in (root, *((version,) if version is not None else ())):
        for folder, folders, files in os.walk(top):
            paths = [Path(folder)] if Path(folder) == top else []
            for path in paths + [Path(folder) / name for name in folders + files]:
                status = os.lstat(path)
                if stat.S_ISLNK(status.st_mode):
                    found[str(path)] = ("link", os.readlink(path))
                elif stat.S_ISDIR(status.st_mode):
                    found[str(path)] = ("folder", status.st_mode, status.st_mtime_ns)
                elif stat.S_ISREG(status.st_mode):
                    found[str(path)] = ("file", status.st_ino, status.st_size, digest(path.read_bytes()),
                                        status.st_mode, status.st_mtime_ns)
                else:
                    found[str(path)] = ("other", status.st_mode)
    return found


def unmanaged(state: dict[str, tuple], root: Path, version: Path | None) -> dict[str, tuple]:
    """Every entry but a folder in a tree_state() outside the paths copy-baseline manages, and every one under the
    --from folder: a file with its inode, size and SHA-256, a link with its target, and any other entry, such as a
    FIFO, with its mode. This is what a run that changes things must keep."""
    found: dict[str, tuple] = {}
    managed = managed_folders(root)
    inside = str(version) + os.sep if version is not None else None
    for path, value in state.items():
        relative = os.path.relpath(path, root).replace(os.sep, "/")
        if value[0] == "folder" or (not (inside and path.startswith(inside))
                                    and (relative in MANAGED_FILES or relative.startswith(managed))):
            continue
        found[path] = value[:4] if value[0] == "file" else value
    return found


def differences(before: dict[str, tuple], after: dict[str, tuple]) -> list[str]:
    return sorted((before.keys() ^ after.keys()) | {path for path in before.keys() & after.keys()
                                                    if before[path] != after[path]})


def install_copy_tool(root: Path) -> Path:
    """Copy tools/copy-baseline.py into root's tools/, where it takes root as the repository root, and return the
    copy's path. run_copy() installs it before it writes the version folder's SHA256SUMS, since that folder may hold
    root."""
    (root / "tools").mkdir(exist_ok=True)
    shutil.copyfile(COPY_TOOL, root / "tools" / COPY_TOOL.name)
    return root / "tools" / COPY_TOOL.name


def copy_run(root: Path, arguments: list[str], version: Path | None = None) -> subprocess.CompletedProcess:
    """Install tools/copy-baseline.py in root and run it there with arguments. invocation_problems() reads this
    file's source and fails if any other code here refers to the tool's path, names its file outside a docstring or,
    apart from run_gate(), starts a process, so the comparisons here cover every run in this file that does not avoid
    that reading. Whatever the outcome, each difference that unmanaged() keeps between the tree_state() records made
    before and after the run, outside the paths the tool manages or under the version folder when one is given, is
    recorded in OUTSIDE_CHANGES: an entry added or removed, a file's inode, size or SHA-256, a link's target, or
    another entry's mode. A run that does not say that it wrote the copy and the pin or that they may be incomplete
    (AFTER_WRITE) has ended before its first write, as the tool's exit codes give, --help included, so each
    difference between those records under root or the version folder, managed paths included, is recorded in
    REFUSED_CHANGES: an entry added or removed, a folder's mode or modification time, a file's inode, size, SHA-256,
    mode or modification time, a link's target, or another entry's mode. Either kind of change fails the test,
    whichever case makes the run; neither comparison covers anything else, such as ownership, access time or what is
    in a folder that tree_state() cannot list. A run still going after COPY_TIMEOUT seconds is stopped and reported
    with the exit code TIMED_OUT."""
    tool = install_copy_tool(root)
    before = tree_state(root, version)
    command = [sys.executable, "-I", str(tool), *arguments]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=COPY_TIMEOUT)
    except subprocess.TimeoutExpired:
        result = subprocess.CompletedProcess(command, TIMED_OUT, "", f"stopped after {COPY_TIMEOUT} seconds")
    after = tree_state(root, version)
    changed = differences(unmanaged(before, root, version), unmanaged(after, root, version))
    if changed:
        OUTSIDE_CHANGES.append(f"copy-baseline (exit {result.returncode}) changed "
                               f"{[os.path.relpath(path, root) for path in changed]}")
    if not any(marker in result.stdout + result.stderr for marker in AFTER_WRITE):
        changed = differences(before, after)
        if changed:
            REFUSED_CHANGES.append(f"copy-baseline (exit {result.returncode}, before its first write) changed "
                                   f"{[os.path.relpath(path, root) for path in changed]}")
    return result


def installed(root: Path, result: subprocess.CompletedProcess) -> str:
    """The path, relative to root, of the copy of the tool that copy_run() ran."""
    return Path(result.args[2]).relative_to(root).as_posix()


def run_copy(root: Path, package: dict[str, bytes], gate: bytes | None = None,
             source_link: bool = False, version: Path | None = None, notice: str = NOTICE_TEXT,
             sums_edit=None, sums_sha256: str | None = None,
             newline_after: str | None = None, before_run=None) -> subprocess.CompletedProcess:
    """Run tools/copy-baseline.py in root on a version folder 1.2.1 that holds package and its SHA256SUMS, with the
    gate (or the given gate source) beside it, from which it loads notice_entry() and check(), and a NOTICE.md that
    carries the 1.2.1 entry (or the given notice), so that the gate's check at the end passes a clean copy. A
    site-src/ that the caller has already made, as a folder or a link, is kept, and so is a tools/ folder. With
    source_link, 1.2.1 is a link to the version folder. With version, the version folder is made there instead, and
    its SHA256SUMS lists every file in it, so that a version folder that holds the repository still matches its
    sums. sums_edit, when given, changes the SHA256SUMS text before it is written and hashed, and sums_sha256, when
    given, replaces its digest on the command line. newline_after, when given, names the option whose value on the
    command line gains a trailing newline. before_run, when given, is called with root and the version folder once
    the tree and SHA256SUMS are written, just before the run. copy_run() runs the tool and records each change that
    its comparisons find: outside the paths the tool manages or under the version folder after any run, and anywhere
    that tree_state() records after a run that ends before its first write."""
    install_copy_tool(root)
    (root / "tools" / GATE.name).write_bytes(GATE.read_bytes() if gate is None else gate)
    (root / "NOTICE.md").write_text(notice, encoding="utf-8")
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
    if sums_edit is not None:
        sums = sums_edit(sums)
    (version / "SHA256SUMS").write_text(sums, encoding="utf-8")
    if source_link:
        (root / "1.2.1").symlink_to(version)
    arguments = ["--from", str(root / "1.2.1" if source_link else version),
                 "--sums-sha256", sums_sha256 or digest(sums.encode()), "--archive-sha256", "0" * 64]
    if newline_after is not None:
        arguments[arguments.index(newline_after) + 1] += "\n"
    if before_run is not None:
        before_run(root, version)
    return copy_run(root, arguments, version)


# A version also holds files the site never copies: the 6th script, matrix.js, and reference/.
NOT_COPIED = {"matrix.js": b"/* matrix.js */\n", "reference/landing.html": b"<html></html>\n"}
PACKAGE = {**FILES, **DOCS, **NOT_COPIED, "tools/check_palette.py": TOOL,
           **{package_name(key): data for key, data in CARD.items()}}
# Versions copy-baseline refuses (exit 1) before it replaces a served file: each changes PACKAGE in place and gives
# what the tool's 1 line must say.
NO_ENTRY = "README.md holds a carriage return or has no step 7"
COPY_REFUSALS = [
    ("a version without the build tool", lambda package: package.pop("tools/check_palette.py"),
        "SHA256SUMS does not list tools/check_palette.py"),
    ("a version without the card builder", lambda package: package.pop(package_name(CARD_KEY)),
        f"SHA256SUMS does not list {package_name(CARD_KEY)}"),
    ("a version without README.md", lambda package: package.pop("README.md"),
        "SHA256SUMS does not list the document README.md"),
    ("a version without SPECIFICATION.md", lambda package: package.pop("SPECIFICATION.md"),
        "SHA256SUMS does not list the document SPECIFICATION.md"),
    ("a README whose heading names another version",
        lambda package: package.update({"README.md": README.replace(b"Baseline 1.2.1", b"Baseline 1.2.0")}),
        "README.md does not start with the heading '# Baseline 1.2.1: '"),
    ("a README without its step 7 NOTICE entry",
        lambda package: package.update({"README.md": README.replace(b"   > ", b"")}), NO_ENTRY),
    ("a README whose step 7 holds a second, blank-separated quoted paragraph",
        lambda package: package.update({"README.md": README.replace(
            b"exceptions.\n\n", b"exceptions.\n\n   > A 3rd exception: x.\n\n")}), NO_ENTRY),
    # The gate reads the README's bytes without newline translation and refuses this one (exit 3), so copying it
    # would only fail at deploy.
    ("a README with CRLF line ends",
        lambda package: package.update({"README.md": README.replace(b"\n", b"\r\n")}), NO_ENTRY),
    # The gate refuses this one too (exit 3), as it refuses a carriage return anywhere in the README.
    ("a README with CRLF only on its step 7 entry line",
        lambda package: package.update({"README.md": README.replace(b"exceptions.\n", b"exceptions.\r\n")}),
        NO_ENTRY),
]
# SHA256SUMS faults copy-baseline refuses (exit 1) before it replaces a served file: each gives run_copy's arguments
# and what the tool's 1 line must say.
COPY_SUMS_REFUSALS = [
    ("a SHA256SUMS that does not hash to the digest given", {"sums_sha256": "1" * 64},
        "SHA256SUMS does not hash to the published digest"),
    ("a file that does not match its SHA256SUMS digest",
        {"sums_edit": lambda sums: sums.replace(digest(FILES["baseline.css"]), digest(b"other"), 1)},
        "baseline.css does not match its SHA256SUMS digest"),
    ("a file that SHA256SUMS does not list",
        {"sums_edit": lambda sums: sums.replace(f"{digest(FILES['baseline.css'])}  baseline.css\n", "", 1)},
        "the folder does not match SHA256SUMS: missing [], unlisted ['baseline.css']"),
    ("a file that SHA256SUMS lists and the folder lacks",
        {"sums_edit": lambda sums: sums + f"{digest(b'extra')}  extra.css\n"},
        "the folder does not match SHA256SUMS: missing ['extra.css'], unlisted []"),
]
# SHA256SUMS lines copy-baseline refuses (exit 1) before its first write, each added after the version's own lines:
# each gives the line and what the tool's 1 line must say. A name outside the folder would also fail the comparison
# with the folder that follows, with another message, so each case checks the message of its own refusal.
SUMS_LINE_REFUSALS = [
    ("a SHA256SUMS line with text after its file name", f"{digest(b'extra')}  extra.css extra\n", "is malformed"),
    ("a SHA256SUMS line that names a file twice", f"{digest(FILES['baseline.css'])}  baseline.css\n",
        "names 'baseline.css' twice or outside the folder"),
    ("a SHA256SUMS line that names a file by an absolute path", f"{digest(b'extra')}  /extra.css\n",
        "names '/extra.css' twice or outside the folder"),
    ("a SHA256SUMS line that names a file above the folder", f"{digest(b'extra')}  ../extra.css\n",
        "names '../extra.css' twice or outside the folder"),
]


def sums_line_problems() -> list[str]:
    """copy-baseline refuses each line in SUMS_LINE_REFUSALS, naming its line number, with its own 1 line before its
    first write, and copy_run() checks that nothing that tree_state() records under the root changed."""
    problems = []
    for name, line, needle in SUMS_LINE_REFUSALS:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            result = run_copy(root, dict(PACKAGE), sums_edit=lambda sums: sums + line)
            lines = result.stderr.splitlines()
            said = f"SHA256SUMS line {len(PACKAGE) + 1} {needle}"
            if result.returncode != 1 or len(lines) != 1 or said not in lines[0]:
                problems.append(f"copy-baseline: {name} exits {result.returncode}; expected 1 with its own 1 line "
                                f"saying {said!r}: {result.stderr.strip()[-200:]!r}")
    return problems


def fifo_in_place(path: Path) -> None:
    path.unlink()
    os.mkfifo(path)


def link_in_place(path: Path, target: Path) -> None:
    path.unlink()
    path.symlink_to(target)


def fifo_sums(root: Path, version: Path) -> None:
    fifo_in_place(version / "SHA256SUMS")


def link_sums(root: Path, version: Path) -> None:
    os.mkfifo(root / "outside" / "SHA256SUMS")
    link_in_place(version / "SHA256SUMS", root / "outside" / "SHA256SUMS")


def fifo_gate(root: Path, version: Path) -> None:
    fifo_in_place(root / "tools" / GATE.name)


def link_gate(root: Path, version: Path) -> None:
    os.mkfifo(root / "outside" / GATE.name)
    link_in_place(root / "tools" / GATE.name, root / "outside" / GATE.name)


def link_version_file(root: Path, version: Path) -> None:
    shutil.copyfile(version / "baseline.css", root / "outside" / "baseline.css")
    link_in_place(version / "baseline.css", root / "outside" / "baseline.css")


# Files copy-baseline reads that it refuses (exit 1) before its first write, each made a FIFO or a link once the tree
# and SHA256SUMS are written: each gives what the tool's 1 line must say. The tool opens a file with O_NONBLOCK, so
# opening a FIFO does not wait, and checks the opened file again with its own message; each case asserts the message
# of the check made before the open, so a tool without that check fails the case by its message. Each link to the
# gate or to SHA256SUMS leads to a FIFO outside the version folder, so a tool that opens either through the link and
# waits is stopped at COPY_TIMEOUT, failing the case.
READ_REFUSALS = [
    ("a FIFO in place of SHA256SUMS", fifo_sums, "1.2.1/SHA256SUMS is not a regular file; refusing to open it"),
    ("a link in place of SHA256SUMS, leading to a FIFO", link_sums,
        "1.2.1/SHA256SUMS is a link; refusing to read through it"),
    ("a FIFO in place of the gate", fifo_gate, f"tools/{GATE.name} is not a regular file; refusing to open it"),
    ("a link in place of the gate, leading to a FIFO", link_gate,
        f"tools/{GATE.name} is a link; refusing to read through it"),
    ("a link in place of a file in the version folder", link_version_file,
        "1.2.1/baseline.css is not a regular file or folder"),
]


def read_refusal_problems() -> list[str]:
    """copy-baseline refuses each file in READ_REFUSALS with its own 1 line before it opens it, and leaves the served
    files as they were; copy_run() checks that nothing that tree_state() records under the root changed, the FIFO
    and the link's target included."""
    problems = []
    for name, prepare, needle in READ_REFUSALS:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "outside").mkdir()
            served = root / "site" / "assets" / "baseline" / "served-before.css"
            served.parent.mkdir(parents=True)
            served.write_bytes(b"a { color: red; }\n")
            result = run_copy(root, dict(PACKAGE), before_run=prepare)
            lines = result.stderr.splitlines()
            if result.returncode != 1 or len(lines) != 1 or needle not in lines[0] or not served.is_file():
                problems.append(f"copy-baseline: {name} exits {result.returncode}; expected 1 with its own 1 line "
                                f"saying {needle!r}, the served files kept: {result.stderr.strip()[-200:]!r}")
    return problems


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


def folder_build_tool(root: Path) -> None:
    (root / TOOL_KEY).mkdir(parents=True)


def folder_site_json(root: Path) -> None:
    (root / "site-src" / "site.json").mkdir(parents=True)


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
# Each gives what the tool's 1 line must say.
COPY_TREE_REFUSALS = [
    ("a link in place of .baseline/card-fonts/", link_card_fonts,
        ".baseline/card-fonts is a link; refusing to write through it"),
    ("a file in place of .baseline/card-fonts/", file_card_fonts, ".baseline/card-fonts is not a folder"),
    ("a link in place of .baseline/check_palette.py", link_build_tool,
        ".baseline/check_palette.py is a link; refusing to write through it"),
    ("a folder in place of .baseline/check_palette.py", folder_build_tool,
        ".baseline/check_palette.py is not a regular file; refusing to write through it"),
    ("a link in place of site/assets/, above the served copy folder", link_served_parent,
        "site/assets is a link; refusing to write through it"),
    ("a link in place of site-src/", link_site_src, "site-src is a link; refusing to read through it"),
    ("a link in place of site-src/site.json", link_site_json,
        "site-src/site.json is a link; refusing to read through it"),
    ("a folder in place of site-src/site.json", folder_site_json,
        "site-src/site.json is not a regular file; refusing to read through it"),
]


def copy_tree_problems() -> list[str]:
    """copy-baseline refuses each tree in COPY_TREE_REFUSALS with its own 1 line before it writes, and rebuilds
    .baseline/card-fonts/ without the stray entries a previous copy or a hand edit left there."""
    problems = []
    for name, prepare, needle in COPY_TREE_REFUSALS:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "outside").mkdir()
            prepare(root)
            served = root / "site" / "assets" / "baseline" / "served-before.css"
            if not served.exists():
                served.parent.mkdir(parents=True)
                served.write_bytes(b"a { color: red; }\n")
            result = run_copy(root, dict(PACKAGE))
            lines = result.stderr.splitlines()
            if result.returncode != 1 or len(lines) != 1 or needle not in lines[0] or not served.is_file():
                problems.append(f"copy-baseline: {name} exits {result.returncode}; expected 1 before any write with "
                                f"its own 1 line saying {needle!r}, the served files kept: "
                                f"{result.stderr.strip()[:200]!r}")
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
        needle = f"{root / '1.2.1'} is a link; give the unpacked version folder itself"
        if (result.returncode != 1 or not served.is_file() or (root / ".baseline").exists()
                or needle not in result.stderr):
            problems.append(f"copy-baseline: a --from folder that is a link exits {result.returncode}; expected 1 "
                            f"before any write, saying {needle!r}: {result.stderr.strip()[:200]!r}")
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


def source_through_link(scratch: Path) -> tuple[Path, Path]:
    # A link above the --from folder leads into the served copy folder, so the path given does not show that the
    # version folder is inside it. The tool resolves the --from folder before it compares, so this case passes
    # whether the folders are compared by device and inode or by resolved name; only 2 paths to 1 folder that resolve()
    # does not merge, such as a bind mount, would separate them.
    (scratch / "via").symlink_to(scratch / "site" / "assets" / "baseline")
    return scratch, scratch / "via" / "1.2.1"


# --from folders copy-baseline refuses (exit 1) before its first write, since the copy would delete or change each
# one: each layout gives the repository root and the version folder, and the message names both.
COPY_SOURCE_REFUSALS = [
    ("a --from folder inside the served copy folder", source_in_served_folder, "is inside site/assets/baseline"),
    ("a --from folder inside .baseline/card-fonts/", source_in_card_fonts, "is inside .baseline/card-fonts"),
    ("a --from folder that holds the repository", source_holding_repository, "holds site/assets/baseline"),
    ("a --from folder reached through a link into the served copy folder", source_through_link,
        "is inside site/assets/baseline"),
]


def copy_source_problems() -> list[str]:
    """copy-baseline refuses each --from folder in COPY_SOURCE_REFUSALS before it writes, naming the folder and the
    path it overlaps, and leaves the served files as they were; copy_run() checks that nothing that tree_state()
    records in the version folder changed."""
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


# Code appended to the gate's source, which copy-baseline runs in its own process when it loads the gate, before it
# reads the version. FAIL_ON_MKDIR makes every later Path.mkdir() raise an error that is not an OSError, as a deeply
# nested path does; copy-baseline's first mkdir() comes after it has cleared the served copy folder.
FAIL_ON_MKDIR = b"""
import pathlib as _pathlib


def _fail(self, *args, **kwargs):
    raise RecursionError("maximum recursion depth exceeded (injected)")


_pathlib.Path.mkdir = _fail
"""
# FAIL_ON_LOAD raises such an error while the gate loads, before any write.
FAIL_ON_LOAD = b"\nraise LookupError('injected')\n"
# COUNT_OPENS counts each open of a path under the --from folder and prints the counts when the run ends. It counts
# through an audit hook on Python's "open" event, which builtins.open, io.open and os.open raise, and so everything
# built on them, such as pathlib and shutil.copyfile, so a second open by any of those routes in the tool's process is
# counted, whichever module makes it. The hook resolves a relative path against the working folder, so an os.open of a
# path relative to a folder's descriptor (dir_fd) is not counted.
COUNT_OPENS = b"""
import atexit as _atexit
import os as _os
import sys as _sys

_version = _os.path.realpath(_sys.argv[_sys.argv.index("--from") + 1])
_opened = {}


def _count_open(event, args):
    if event == "open" and isinstance(args[0], (str, bytes, _os.PathLike)):
        path = _os.path.realpath(_os.fsdecode(args[0]))
        if path.startswith(_version + _os.sep):
            _opened[path] = _opened.get(path, 0) + 1


_sys.addaudithook(_count_open)
_atexit.register(lambda: [print(f"opened {count} {path}", file=_sys.__stderr__) for path, count in _opened.items()])
"""


def failure_problems() -> list[str]:
    """Each failure below ends copy-baseline with its documented code and its own 1 line, never a traceback: an error
    that is not an OSError, after the first change, exits 3 saying that the copy and the pin may be incomplete; one
    before any write exits 3 without saying so; a --from folder whose name is not a version number, or a
    --sums-sha256 that is not 64 lower-case hexadecimal digits, exits 1; a --from folder that does not exist exits 3.
    The 2 runs with an injected error also check that the served files are cleared or kept to match. A command line
    that argparse refuses, and --help, end with argparse's own output instead: no options exits 2 with its usage and
    error lines, and --help exits 0 with its help, each with nothing written."""
    problems = []
    for name, injected, incomplete in (("an error that is not an OSError after the first change", FAIL_ON_MKDIR, True),
                                       ("an error that is not an OSError before any write", FAIL_ON_LOAD, False)):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            served = root / "site" / "assets" / "baseline" / "served-before.css"
            served.parent.mkdir(parents=True)
            served.write_bytes(b"a { color: red; }\n")
            result = run_copy(root, dict(PACKAGE), GATE.read_bytes() + injected)
            lines = result.stderr.splitlines()
            if (result.returncode != 3 or len(lines) != 1 or not lines[0].startswith("copy-baseline: stopped by")
                    or lines[0].endswith("; the copy and the pin may be incomplete") != incomplete
                    or served.is_file() == incomplete):
                problems.append(f"copy-baseline: {name} exits {result.returncode} with "
                                f"{result.stderr.strip()[-300:]!r}; expected 3 with its own 1 line, "
                                + ("saying that the copy and the pin may be incomplete" if incomplete
                                   else "the served files kept"))
    # Command lines that argparse handles: each gives the arguments, the expected exit code, whether argparse writes to
    # stderr (an error) or stdout (the help), and a line argparse's output must hold.
    for name, arguments, expected, to_stderr, needle in (
            ("no options", [], 2, True, "error: the following arguments are required: --from"),
            ("--help", ["--help"], 0, False, "  --from SOURCE")):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "tools").mkdir()
            shutil.copyfile(GATE, root / "tools" / GATE.name)
            result = copy_run(root, arguments)
            left = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))
            output = result.stderr if to_stderr else result.stdout
            if (result.returncode != expected or not output.startswith("usage: ") or needle not in output
                    or left != sorted(["tools", f"tools/{GATE.name}", installed(root, result)])):
                problems.append(f"copy-baseline: {name} exits {result.returncode}, leaving {left}; expected "
                                f"{expected}, argparse's usage and {needle!r}, and nothing written: "
                                f"{output.strip()[-200:]!r}")
    # Failures the tool reports in its own 1 line: each gives the --from folder's name, the --sums-sha256 value, the
    # expected exit code, and what the line must say.
    for name, folder, sums_sha256, expected, needle in (
            ("a --from folder that does not exist", "1.2.1", "0" * 64, 3, "1.2.1 could not be read"),
            ("a --from folder whose name is not a version number", "latest", "0" * 64, 1,
             "the folder name 'latest' is not a version number"),
            ("a --sums-sha256 that is not 64 lower-case hexadecimal digits", "1.2.1", "0" * 63, 1,
             "--sums-sha256 is not a 64 character lower-case SHA-256")):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "tools").mkdir()
            shutil.copyfile(GATE, root / "tools" / GATE.name)
            arguments = ["--from", str(root / folder), "--sums-sha256", sums_sha256, "--archive-sha256", "0" * 64]
            result = copy_run(root, arguments, root / folder)
            lines = result.stderr.splitlines()
            if result.returncode != expected or len(lines) != 1 or needle not in lines[0]:
                problems.append(f"copy-baseline: {name} exits {result.returncode}; expected {expected} with its own "
                                f"1 line saying {needle!r}: {result.stderr.strip()[-200:]!r}")
    return problems


def base_newline(root: Path) -> dict:
    (root / "site-src").mkdir()
    (root / "site-src" / "site.json").write_text(json.dumps({"base": "/draft/\n"}), encoding="utf-8")
    return {}


# Values that copy-baseline matches whole, each with a trailing newline: each gives run_copy's arguments for root, the
# exit code, and what the tool's 1 line must say. Every other input is valid, so a tool that accepted the newline
# would go on to copy.
WHOLE_VALUE_REFUSALS = [
    ("a --sums-sha256 that ends in a newline", lambda root: {"newline_after": "--sums-sha256"}, 1,
        "--sums-sha256 is not a 64 character lower-case SHA-256"),
    ("an --archive-sha256 that ends in a newline", lambda root: {"newline_after": "--archive-sha256"}, 1,
        "--archive-sha256 is not a 64 character lower-case SHA-256"),
    ("a --from folder whose name ends in a newline", lambda root: {"version": root / "1.2.1\n"}, 1,
        "the folder name '1.2.1\\n' is not a version number"),
    ("a site-src/site.json base path that ends in a newline", base_newline, 3,
        "site-src/site.json base '/draft/\\n' must be / or a single folder"),
]


def whole_value_problems() -> list[str]:
    """copy-baseline refuses each value in WHOLE_VALUE_REFUSALS with its own 1 line before its first write, and
    copy_run() checks that nothing that tree_state() records under the root changed. The line must start with the
    refusal's message: the gate refuses the same base path in the same words after a copy, so a tool that copied and
    let the gate refuse it would otherwise pass."""
    problems = []
    for name, arguments, expected, needle in WHOLE_VALUE_REFUSALS:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            served = root / "site" / "assets" / "baseline" / "served-before.css"
            served.parent.mkdir(parents=True)
            served.write_bytes(b"a { color: red; }\n")
            result = run_copy(root, dict(PACKAGE), **arguments(root))
            lines = result.stderr.splitlines()
            if (result.returncode != expected or len(lines) != 1
                    or not lines[0].startswith(f"copy-baseline: {needle}")):
                problems.append(f"copy-baseline: {name} exits {result.returncode}; expected {expected} with its own "
                                f"1 line saying {needle!r}: {result.stderr.strip()[-200:]!r}")
    return problems


# SWAP_OPEN, appended to the gate's source, sends the tool's os.open() of the version's SHA256SUMS to the path given,
# after the tool's lstat has found a regular file there: it stands in for an entry replaced between that check and the
# open, a race no case here can time, and changes nothing in the tree.
SWAP_OPEN = """
import os as _os

_real_open = _os.open


def _swap_open(path, flags, *args, **kwargs):
    if _os.fspath(path).endswith(_os.sep + "SHA256SUMS"):
        path = {replacement!r}
    return _real_open(path, flags, *args, **kwargs)


_os.open = _swap_open
"""


def swapped_gate(replacement: Path) -> bytes:
    return GATE.read_bytes() + SWAP_OPEN.format(replacement=str(replacement)).encode()


def fifo_swap(root: Path) -> dict:
    os.mkfifo(root / "outside" / "fifo")
    return {"gate": swapped_gate(root / "outside" / "fifo")}


def link_swap(root: Path) -> dict:
    (root / "outside" / "target").write_bytes(b"x\n")
    (root / "outside" / "link").symlink_to(root / "outside" / "target")
    return {"gate": swapped_gate(root / "outside" / "link")}


def gate_syntax_error(root: Path) -> dict:
    return {"gate": GATE.read_bytes() + b"\ndef (\n"}


def site_json_missing(root: Path) -> dict:
    (root / "site-src").mkdir()
    return {}


def site_json_no_base(root: Path) -> dict:
    (root / "site-src").mkdir()
    (root / "site-src" / "site.json").write_text("{}", encoding="utf-8")
    return {}


def bytes_in_place(name: str, data: bytes):
    def before_run(root: Path, version: Path) -> None:
        (version / name).write_bytes(data)
    return before_run


def sums_not_utf8(root: Path) -> dict:
    return {"sums_sha256": digest(b"\xff\n"), "before_run": bytes_in_place("SHA256SUMS", b"\xff\n")}


def readme_not_utf8(root: Path) -> dict:
    return {"sums_edit": lambda sums: sums.replace(digest(README), digest(b"\xff\n")),
            "before_run": bytes_in_place("README.md", b"\xff\n")}


# Inputs copy-baseline refuses before its first write that no case above reaches, each with its own message: each
# gives run_copy's arguments for root, the exit code, and what the tool's 1 line must say. The first 2 make the
# version's SHA256SUMS a FIFO and a link as the tool opens it, which only the checks made after lstat can refuse.
INPUT_REFUSALS = [
    ("SHA256SUMS replaced by a FIFO between its check and its open", fifo_swap, 1,
        "1.2.1/SHA256SUMS was not a regular file once opened; refusing to read it"),
    ("SHA256SUMS replaced by a link between its check and its open", link_swap, 3,
        "1.2.1/SHA256SUMS could not be opened or read"),
    ("a gate that does not compile", gate_syntax_error, 3, f"tools/{GATE.name} could not be loaded"),
    ("a site-src/ without site.json", site_json_missing, 3,
        "site-src/site.json could not be checked before it is opened"),
    ("a site-src/site.json without a base path", site_json_no_base, 3, "site-src/site.json has no readable base"),
    ("a SHA256SUMS that is not UTF-8", sums_not_utf8, 3, "SHA256SUMS could not be read"),
    ("a README that is not UTF-8", readme_not_utf8, 3, "README.md could not be read"),
]


def input_refusal_problems() -> list[str]:
    """copy-baseline refuses each input in INPUT_REFUSALS with its own 1 line before its first write, and copy_run()
    checks that nothing that tree_state() records under the root changed."""
    problems = []
    for name, arguments, expected, needle in INPUT_REFUSALS:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "outside").mkdir()
            served = root / "site" / "assets" / "baseline" / "served-before.css"
            served.parent.mkdir(parents=True)
            served.write_bytes(b"a { color: red; }\n")
            result = run_copy(root, dict(PACKAGE), **arguments(root))
            lines = result.stderr.splitlines()
            if (result.returncode != expected or len(lines) != 1 or needle not in lines[0]
                    or not served.is_file()):
                problems.append(f"copy-baseline: {name} exits {result.returncode}; expected {expected} with its own "
                                f"1 line saying {needle!r}, the served files kept: {result.stderr.strip()[-200:]!r}")
    return problems


def permission_refusal_problems() -> list[str]:
    """Inputs that only file permissions make unreadable, so not run as root: a --from folder that can be searched
    but not listed makes copy-baseline exit 3 saying that it could not be listed, and a .baseline/ that cannot be
    searched makes it exit 3 saying that .baseline/card-fonts could not be read, each with its own 1 line before its
    first write."""
    problems = []
    for name, expected_line in (("a --from folder that cannot be listed", "1.2.1 could not be listed"),
                                ("a .baseline/ that cannot be searched", ".baseline/card-fonts could not be read")):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / ".baseline").mkdir()
            locked = root / "1.2.1" if name.startswith("a --from") else root / ".baseline"

            def lock(root: Path, version: Path) -> None:
                os.chmod(locked, 0o100 if locked.name == "1.2.1" else 0)

            try:
                result = run_copy(root, dict(PACKAGE), before_run=lock)
            finally:
                os.chmod(locked, 0o755)
            lines = result.stderr.splitlines()
            if result.returncode != 3 or len(lines) != 1 or expected_line not in lines[0]:
                problems.append(f"copy-baseline: {name} exits {result.returncode}; expected 3 with its own 1 line "
                                f"saying {expected_line!r}: {result.stderr.strip()[-200:]!r}")
    return problems


def read_once_problems() -> list[str]:
    """copy-baseline opens each file in the version folder exactly once in its own process, SHA256SUMS and the README
    included, counted by COUNT_OPENS's audit hook, so a second open by builtins.open, io.open, os.open or anything
    built on them fails this case. An os.open of a path relative to a folder's descriptor (dir_fd), which the hook
    resolves against the working folder instead, a second read through the same open file, and a read by another
    process are not counted."""
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        result = run_copy(root, dict(PACKAGE), GATE.read_bytes() + COUNT_OPENS)
        counts = {}
        for line in result.stderr.splitlines():
            if line.startswith("opened "):
                count, path = line[len("opened "):].split(" ", 1)
                counts[os.path.relpath(path, os.path.realpath(root / "1.2.1"))] = int(count)
        expected = {name: 1 for name in (*PACKAGE, "SHA256SUMS")}
        if result.returncode != 0 or counts != expected:
            wrong = {name: counts.get(name, 0) for name in sorted(expected.keys() | counts.keys())
                     if counts.get(name, 0) != expected.get(name, 0)}
            return [f"copy-baseline: exit {result.returncode}, files in the version folder not opened exactly once: "
                    f"{wrong}"]
    return []


def planted_cache_problems() -> list[str]:
    """copy-baseline never runs byte code cached for the gate: an unchecked hash-based cache file under
    tools/__pycache__/, which the normal loader runs without comparing it with the source, makes a gate whose check()
    refuses every tree, and the copy still passes the real gate."""
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        planted = root / "planted" / GATE.name
        planted.parent.mkdir()
        planted.write_bytes(GATE.read_bytes() + b"\n\ndef check(root):\n    return ['planted byte code ran']\n")
        cache = Path(importlib.util.cache_from_source(str(root / "tools" / GATE.name)))
        cache.parent.mkdir(parents=True)
        py_compile.compile(str(planted), cfile=str(cache), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        result = run_copy(root, dict(PACKAGE))
        if result.returncode != 0 or "planted" in result.stderr:
            return [f"copy-baseline: a planted cache file for the gate: exit {result.returncode}; expected 0, the "
                    f"cache file not run: {result.stderr.strip()[-200:]!r}"]
    return []


def gate_unreadable_problems() -> list[str]:
    """A tree that the gate's check cannot read after the copy makes copy-baseline exit 3, naming the gate. A folder
    under site/ that the user cannot list stands in for it."""
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        locked = root / "site" / "locked"
        locked.mkdir(parents=True)
        os.chmod(locked, 0)
        try:
            result = run_copy(root, dict(PACKAGE))
        finally:
            os.chmod(locked, 0o755)
        if result.returncode != 3 or "could not check the tree" not in result.stderr:
            return [f"copy-baseline: a tree the gate cannot read exits {result.returncode}; expected 3, saying that "
                    f"the gate could not check the tree: {result.stderr.strip()[-200:]!r}"]
    return []


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
        served = sorted(path.relative_to(root / "site" / "assets" / "baseline").as_posix()
                        for path in (root / "site" / "assets" / "baseline").rglob("*") if path.is_file())
        if served != sorted(FILES):
            problems.append(f"copy-baseline: the served copy folder holds {served}; expected the runtime and "
                            f"licence files only, without {sorted(NOT_COPIED)} or tools/")
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        (root / "site-src").mkdir()
        (root / "site-src" / "site.json").write_text(json.dumps({"base": "/draft/"}), encoding="utf-8")
        result = run_copy(root, dict(PACKAGE))
        if result.returncode != 0 or (copied(root) / "baseline.css").read_bytes() != FILES["baseline.css"]:
            problems.append(f"copy-baseline: with the base path /draft/, exit {result.returncode}; expected 0 and the "
                            f"copy under site/draft/assets/baseline/: {result.stderr.strip()[-200:]!r}")
    for name, arguments, needle in [*COPY_SUMS_REFUSALS,
                                    ("a NOTICE.md entry naming the previous version",
                                     {"notice": NOTICE_TEXT.replace("baseline 1.2.1", "baseline 1.2.0")},
                                     "NOTICE.md")]:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            served = root / "site" / "assets" / "baseline" / "served-before.css"
            served.parent.mkdir(parents=True)
            served.write_bytes(b"a { color: red; }\n")
            result = run_copy(root, dict(PACKAGE), **arguments)
            # The NOTICE.md entry is compared by the gate's check after the copy; the others are refused before it.
            before_write = "notice" not in arguments
            lines = result.stderr.splitlines()
            if (result.returncode != 1 or served.is_file() != before_write or needle not in result.stderr
                    or (before_write and len(lines) != 1)):
                problems.append(f"copy-baseline: {name} exits {result.returncode}; expected 1, saying {needle!r}, "
                                + ("in its own 1 line, the served files kept" if before_write else "")
                                + f": {result.stderr.strip()[-200:]!r}")
    for name, change, needle in COPY_REFUSALS:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            served = root / "site" / "assets" / "baseline" / "served-before.css"
            served.parent.mkdir(parents=True)
            served.write_bytes(b"a { color: red; }\n")
            package = dict(PACKAGE)
            change(package)
            result = run_copy(root, package)
            lines = result.stderr.splitlines()
            if result.returncode != 1 or len(lines) != 1 or needle not in lines[0] or not served.is_file():
                kept = "keeps" if served.is_file() else "replaces"
                problems.append(f"copy-baseline: {name} exits {result.returncode} "
                                f"and {kept} the served files; expected 1 with its own 1 line saying {needle!r}, "
                                f"and keeps: {result.stderr.strip()[-200:]!r}")
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


# The functions in this file that may start a process: run_gate() runs the gate, and copy_run() runs copy-baseline.
PROCESS_RUNNERS = {"run_gate", "copy_run"}
# The names that lead to the tool's path, each with the only functions that may use it.
TOOL_PATH_USERS = {"COPY_TOOL": {"install_copy_tool"}, "install_copy_tool": {"run_copy", "copy_run"}}
# The name prefixes of the os functions that start a process or replace this one, and the modules that start one.
OS_LAUNCHERS = ("system", "popen", "exec", "spawn", "posix_spawn", "fork")
LAUNCHER_MODULES = {"subprocess", "os", "runpy", "multiprocessing", "pty", "asyncio", "concurrent"}


def invocation_problems() -> list[str]:
    """The problems found by reading this file's own source for code other than copy_run() that could run
    copy-baseline; with none, copy_run()'s comparisons before and after each run cover every run in this file that
    does not avoid this reading. It checks that each name in TOOL_PATH_USERS is used only in the functions it lists;
    that no string outside a docstring and COPY_TOOL's own assignment holds the tool's file name; that only
    copy_run() and run_gate() use a name from subprocess other than CompletedProcess and TimeoutExpired, and
    copy_run() uses one once; and that no code uses an os function whose name starts with one of OS_LAUNCHERS,
    imports one of LAUNCHER_MODULES other than subprocess and os, imports either of those under another name, or
    imports from any of them. A run written to avoid this reading, such as one that assembles the file name from
    pieces, is not detected."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    assignment = next(statement for statement in tree.body if isinstance(statement, ast.Assign)
                      and [getattr(target, "id", None) for target in statement.targets] == ["COPY_TOOL"])
    file_name = next(node.value for node in ast.walk(assignment)
                     if isinstance(node, ast.Constant) and str(node.value).endswith(".py"))
    problems = []
    runs_in_copy_run = 0
    for statement in tree.body:
        function = statement.name if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)) else None
        for node in ast.walk(statement):
            where = f"line {getattr(node, 'lineno', '?')}"
            if (isinstance(node, ast.Name) and node.id in TOOL_PATH_USERS and isinstance(node.ctx, ast.Load)
                    and function not in TOOL_PATH_USERS[node.id]):
                problems.append(f"{where} uses {node.id} outside {sorted(TOOL_PATH_USERS[node.id])}")
            elif (isinstance(node, ast.Constant) and isinstance(node.value, str) and file_name in node.value
                    and id(node) not in docstrings and statement is not assignment):
                problems.append(f"{where} names {file_name} outside a docstring")
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                # A result type and an exception class, neither of which starts a process.
                if node.value.id == "subprocess" and node.attr not in {"CompletedProcess", "TimeoutExpired"}:
                    if function not in PROCESS_RUNNERS:
                        problems.append(f"{where} uses subprocess.{node.attr} outside {sorted(PROCESS_RUNNERS)}")
                    elif function == "copy_run":
                        runs_in_copy_run += 1
                elif node.value.id == "os" and node.attr.startswith(OS_LAUNCHERS):
                    problems.append(f"{where} uses os.{node.attr}, which starts a process")
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in LAUNCHER_MODULES:
                problems.append(f"{where} imports from {node.module}")
            elif isinstance(node, ast.Import):
                # subprocess and os are imported by name only, so that each use reads as subprocess.x or os.x above.
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in LAUNCHER_MODULES and (alias.asname or top not in {"subprocess", "os"}):
                        problems.append(f"{where} imports {alias.name}" + (f" as {alias.asname}" if alias.asname
                                                                           else ""))
    if runs_in_copy_run != 1:
        problems.append(f"copy_run() uses subprocess {runs_in_copy_run} times; expected once")
    return [f"the copy-baseline runs: {problem}, so a run could bypass copy_run()'s comparison"
            for problem in problems]


def main() -> int:
    failures: list[str] = (pin_header_problems() + copy_problems() + copy_tree_problems() + copy_gate_problems()
                           + python_floor_problems() + copy_source_problems() + alias_problems()
                           + failure_problems() + whole_value_problems() + read_once_problems()
                           + planted_cache_problems() + sums_line_problems() + read_refusal_problems()
                           + input_refusal_problems())
    # The 7 cases of failure_problems(), read_once_problems(), planted_cache_problems(), and in copy_problems() the
    # base path /draft/ and the NOTICE.md entry naming the previous version.
    ran = 11 + 7 + 1 + 1 + 2
    ran += (len(COPY_REFUSALS) + len(COPY_SUMS_REFUSALS) + len(COPY_TREE_REFUSALS) + len(COPY_SOURCE_REFUSALS)
            + len(WHOLE_VALUE_REFUSALS) + len(SUMS_LINE_REFUSALS) + len(READ_REFUSALS) + len(INPUT_REFUSALS))
    # As root, file permissions neither stop a write, a listing nor a search, so they cannot stand in for these
    # failures.
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        failures += write_failure_problems() + gate_unreadable_problems() + permission_refusal_problems()
        ran += 2 + 2
    # Every copy-baseline run above, refused or not, must leave each file and link outside the paths it manages as
    # tree_state() records it, and every run that ends before its first write must leave everything that tree_state()
    # records as it was, managed paths included. Each run goes through copy_run(), which records each such change, and
    # invocation_problems() fails if any other code refers to the tool's path, names its file outside a docstring or,
    # apart from run_gate(), starts a process, so the first 2 checks cover every run that does not avoid that reading.
    failures += [f"{change}, outside the paths it manages" for change in OUTSIDE_CHANGES]
    failures += [f"{change}; a run that ends before its first write must not add, remove or change anything that "
                 "tree_state() records" for change in REFUSED_CHANGES]
    failures += invocation_problems()
    ran += 3
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
            elif any(needle not in result.stdout + result.stderr for needle in needles):
                failures.append(f"{name}: the output does not say {needles}: "
                                f"{(result.stdout + result.stderr).strip()[:200]!r}")
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
