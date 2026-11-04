#!/usr/bin/env python3
"""check_palette.py: the contrast gate for a site's palette (baseline 1.6.0 and later; matrix tokens from 1.7.0).

Reads the package's palettes.css and, optionally, the site's own site-palette.css (loaded after it), works
out the value of every palette token on <html class="site-<name>"> in each of the 6 states a page can be in
(device light or dark, with no data-scheme, data-scheme="light" or data-scheme="dark"), and checks every
pairing that contrast-report.txt checks, with the same thresholds: text pairs 4.5:1, the focus ring and the
strong rule 3:1, rainbow ink on its slice 3:1; from 1.7.0 also the matrix tints (text on the row tints and heat
steps 4.5:1, the focus ring on them 3:1) and the column-group accents as text on every surface and tint (4.5:1),
so a palette from before 1.7.0, which lacks these tokens, fails. It also checks that the 3 light states agree on every token and
the 3 dark states agree, so an override written in only 1 of a scheme's 2 forms fails.

Usage (from the repository root; Python 3 standard library only, no network):
  python3 .baseline/check_palette.py --site grclibrary \
      --palettes assets/baseline/palettes.css --site-palette assets/site-palette.css
--site may be repeated; without it every site in palettes.css is checked. Without --palettes the tool reads
the palettes.css of the package it sits in (../palettes.css).

Exit status: 0 when every check passes; 1 when any pairing misses its threshold, the states of a scheme
disagree, or an input cannot be read or evaluated (the gate fails closed); 2 for a usage error.
site-palette.css may hold only palette tokens (custom properties named in TOKENS or RAINBOW below) in rules
whose selector targets the <html> element; anything else is reported as a failure.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

TOKENS = ["bg", "surface-raised", "surface-sunken", "text", "text-muted", "rule", "rule-strong", "accent",
          "on-accent", "link", "link-hover", "focus", "selection", "code-bg", "callout-bg", "glow", "brand",
          # matrix tables (from 1.7.0)
          "row-tint", "row-hover"] + ["heat-%d" % i for i in range(5)] + ["grp-%d" % i for i in range(1, 7)]
RAINBOW = (["rainbow-%d" % i for i in range(1, 7)] + ["rainbow-join-%d" % i for i in range(1, 7)]
           + ["rainbow-ink-%d" % i for i in range(1, 7)] + ["band-grey"])
SURFACES = ["bg", "surface-raised", "surface-sunken", "code-bg", "callout-bg"]
TEXT_FG = ["text", "text-muted", "link", "link-hover", "accent"]
EXTRA = [  # (label, foreground, background, threshold), as in contrast-report.txt
    ("on-accent on accent", "on-accent", "accent", 4.5),
    ("text on selection", "text", "selection", 4.5),
    ("text on glow", "text", "glow", 4.5),
    ("focus on bg", "focus", "bg", 3.0),
    ("focus on surface-raised", "focus", "surface-raised", 3.0),
    ("focus on surface-sunken", "focus", "surface-sunken", 3.0),
    ("rule-strong on bg", "rule-strong", "bg", 3.0),
    ("rule-strong on surface-raised", "rule-strong", "surface-raised", 3.0),
]
# Matrix tints (from 1.7.0), as in contrast-report.txt: every text token on the 2 row tints; --text, --link and
# --link-hover on the 5 heat steps (baseline.css draws a heat cell's own text in --text, so muted text and the accent
# never sit on a heat step); the focus ring on all 7 at 3:1; each column-group accent as text on the 5 surfaces and
# the 2 row tints.
ROW_TINTS = ["row-tint", "row-hover"]
HEATS = ["heat-%d" % i for i in range(5)]
HEAT_FG = ["text", "link", "link-hover"]
GRPS = ["grp-%d" % i for i in range(1, 7)]
# The 6 states: (device prefers dark, data-scheme attribute or None) and the scheme each shows.
STATES = [(False, None, "light"), (False, "light", "light"), (True, "light", "light"),
          (True, None, "dark"), (False, "dark", "dark"), (True, "dark", "dark")]


class CheckError(Exception):
    pass


# ------------------------------------------------------------------ contrast (WCAG 2.x)
def parse_hex(v):
    m = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", v.strip())
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def rel_lum(rgb):
    def ch(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = rel_lum(a), rel_lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# ------------------------------------------------------------------ a small CSS reader
def strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def blocks(css, path):
    """Yield (prelude, body) for each top-level block, matching braces."""
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            if css[i:].strip():
                raise CheckError("%s: text after the last rule: %r" % (path, css[i:].strip()[:40]))
            return
        depth, k = 1, j + 1
        while k < n and depth:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
            k += 1
        if depth:
            raise CheckError("%s: unbalanced braces" % path)
        yield css[i:j].strip(), css[j + 1:k - 1]
        i = k


def split_top(s, sep=","):
    out, depth, cur = [], 0, ""
    for c in s:
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        if c == sep and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += c
    out.append(cur)
    return [x.strip() for x in out if x.strip()]


SIMPLE = re.compile(r"""\s*(?:
    (?P<root>:root) |
    (?P<html>html)(?![\w-]) |
    \.(?P<cls>[\w-]+) |
    \[\s*data-scheme\s*(?:=\s*(?P<q>["']?)(?P<val>[\w-]+)(?P=q))?\s*\] |
    :(?P<fn>not|is|where)\(
)""", re.X)


def parse_compound(sel):
    """Parse a compound selector that can target <html>. Returns a list of parts, or None when the
    selector has a combinator or any part that cannot match the root element alone."""
    parts, i, s = [], 0, sel.strip()
    if not s:
        return None
    while i < len(s):
        m = SIMPLE.match(s, i)
        if not m or m.end() == i:
            return None
        if m.group("root"):
            parts.append(("root",))
        elif m.group("html"):
            parts.append(("html",))
        elif m.group("cls"):
            parts.append(("cls", m.group("cls")))
        elif m.group("fn"):
            depth, k = 1, m.end()
            while k < len(s) and depth:
                if s[k] == "(":
                    depth += 1
                elif s[k] == ")":
                    depth -= 1
                k += 1
            if depth:
                return None
            inner = [parse_compound(x) for x in split_top(s[m.end():k - 1])]
            if any(x is None for x in inner):
                return None
            parts.append((m.group("fn"), inner))
            i = k
            if i < len(s) and s[i].isspace():
                return None
            continue
        else:
            parts.append(("attr", m.group("val")))
        i = m.end()
        if i < len(s) and s[i].isspace():
            return None  # a combinator: the rule targets a descendant, not <html>
    return parts


def specificity(parts):
    a = b = 0
    for p in parts:
        if p[0] in ("root", "cls", "attr"):
            a += 1
        elif p[0] == "html":
            b += 1
        elif p[0] in ("not", "is"):
            best = max((specificity(x) for x in p[1]), default=(0, 0))
            a, b = a + best[0], b + best[1]
    return (a, b)


def matches(parts, site, attr):
    for p in parts:
        kind = p[0]
        if kind in ("root", "html"):
            continue
        if kind == "cls":
            if p[1] != "site-" + site:
                return False
        elif kind == "attr":
            if attr is None or (p[1] is not None and p[1] != attr):
                return False
        elif kind == "not":
            if any(matches(x, site, attr) for x in p[1]):
                return False
        elif kind in ("is", "where"):
            if not any(matches(x, site, attr) for x in p[1]):
                return False
    return True


def media_true(cond, dark, path):
    c = re.sub(r"\s+", " ", cond.strip().lower())
    if c in ("(prefers-color-scheme: dark)", "screen and (prefers-color-scheme: dark)"):
        return dark
    if c in ("(prefers-color-scheme: light)", "screen and (prefers-color-scheme: light)"):
        return not dark
    raise CheckError("%s: unsupported @media condition %r (only prefers-color-scheme)" % (path, cond))


def read_rules(path, strict):
    """Return a list of rules: (media condition or None, [(parts, specificity)], {name: (value, important)}).
    strict (site-palette.css): every declaration must be a palette token in a rule that targets <html>."""
    try:
        with open(path, encoding="utf-8") as f:
            css = strip_comments(f.read())
    except OSError as e:
        raise CheckError("cannot read %s: %s" % (path, e))
    known = set(TOKENS) | set(RAINBOW)
    rules, problems = [], []

    def add(prelude, body, media):
        decls = {}
        for d in body.split(";"):
            if not d.strip():
                continue
            if ":" not in d:
                problems.append("%s: cannot read the declaration %r" % (path, d.strip()))
                continue
            name, value = d.split(":", 1)
            name, value = name.strip(), value.strip()
            important = bool(re.search(r"!\s*important\s*$", value))
            value = re.sub(r"!\s*important\s*$", "", value).strip()
            if name.startswith("--") and name[2:] in known:
                decls[name[2:]] = (value, important)
            elif strict:
                problems.append("%s: %s { %s } is not a palette token; site-palette.css holds palette tokens only"
                                % (path, prelude, name))
        sels = []
        for s in split_top(prelude):
            parts = parse_compound(s)
            if parts is None:
                if strict and decls:
                    problems.append("%s: the selector %r does not target <html>; palette tokens are set on "
                                    "the site class (see site-palette.example.css)" % (path, s))
                continue
            sels.append((parts, specificity(parts)))
        if decls and sels:
            rules.append((media, sels, decls))

    for prelude, body in blocks(css, path):
        if prelude.startswith("@media"):
            for p2, b2 in blocks(body, path):
                if p2.startswith("@"):
                    problems.append("%s: nested at-rule %r is not supported" % (path, p2))
                    continue
                add(p2, b2, prelude[len("@media"):].strip())
        elif prelude.startswith("@"):
            if strict:
                problems.append("%s: at-rule %r is not allowed in site-palette.css" % (path, prelude.split()[0]))
        else:
            add(prelude, body, None)
    if problems:
        raise CheckError("\n".join(problems))
    return rules


def resolve(sheets, site, dark, attr):
    """The cascaded value of each token on <html class="site-<site>"> in 1 state."""
    best = {}
    order = 0
    for path, rules in sheets:
        for media, sels, decls in rules:
            order += 1
            if media is not None and not media_true(media, dark, path):
                continue
            spec = max((sp for parts, sp in sels if matches(parts, site, attr)), default=None)
            if spec is None:
                continue
            for name, (value, important) in decls.items():
                key = (important, spec, order)
                if name not in best or key >= best[name][0]:
                    best[name] = (key, value, path)
    return {k: (v[1], v[2]) for k, v in best.items()}


def sites_in(rules):
    names = set()
    for _, sels, _ in rules:
        for parts, _ in sels:
            for p in parts:
                if p[0] == "cls" and p[1].startswith("site-"):
                    names.add(p[1][5:])
    return sorted(names)


# ------------------------------------------------------------------ checks
def check_site(sheets, site, out):
    failures = 0
    per_state = {}
    for dark, attr, scheme in STATES:
        per_state[(dark, attr)] = resolve(sheets, site, dark, attr)
    # 1. The 3 states of each scheme agree on every token.
    for scheme in ("light", "dark"):
        states = [(d, a) for d, a, s in STATES if s == scheme]
        ref = per_state[states[0]]
        for st in states[1:]:
            for tok in TOKENS + RAINBOW:
                if tok in ref and per_state[st].get(tok, (None,))[0] != ref[tok][0]:
                    failures += 1
                    out.append("FAIL %s / %s: --%s is %s with no data-scheme on a %s device but %s with data-scheme=%s "
                               "on a %s device; set the override in every form of the scheme"
                               % (site, scheme, tok, ref[tok][0], "dark" if states[0][0] else "light",
                                  per_state[st].get(tok, ("unset",))[0], st[1] or "none", "dark" if st[0] else "light"))
    # 2. Contrast, per scheme (the state that follows the device, which step 1 ties to the others).
    for scheme, state in (("light", (False, None)), ("dark", (True, None))):
        vals = per_state[state]
        rgb = {}
        for tok in TOKENS + RAINBOW:
            if tok == "band-grey":
                continue
            if tok not in vals:
                failures += 1
                out.append("FAIL %s / %s: --%s is not set" % (site, scheme, tok))
                continue
            c = parse_hex(vals[tok][0])
            if c is None:
                failures += 1
                out.append("FAIL %s / %s: --%s is %r; the checker evaluates #rgb or #rrggbb values only"
                           % (site, scheme, tok, vals[tok][0]))
                continue
            rgb[tok] = c
        changed = sorted({t for t, (v, p) in vals.items() if p != sheets[0][0]})
        out.append("== %s / %s%s" % (site, scheme, ("   (from site-palette: %s)" % ", ".join("--" + t for t in changed))
                                     if changed else ""))
        out.append("%-12s %s" % ("fg \\ bg", " ".join("%14s" % s for s in SURFACES)))
        for fg in TEXT_FG:
            row = []
            for s in SURFACES:
                if fg in rgb and s in rgb:
                    r = contrast(rgb[fg], rgb[s])
                    bad = r < 4.5
                    failures += bad
                    row.append("%14s" % ("%.2f:1%s" % (r, " FAIL" if bad else "")))
                else:
                    row.append("%14s" % "n/a")
            out.append("%-12s %s" % (fg, " ".join(row)))
        for label, fg, bg, thr in EXTRA:
            if fg in rgb and bg in rgb:
                r = contrast(rgb[fg], rgb[bg])
                bad = r < thr
                failures += bad
                out.append("  %-34s %6.2f:1  needs %.1f%s" % (label, r, thr, "  FAIL" if bad else ""))
        out.append("  matrix tints (text 4.5:1, focus 3:1)")
        for tint in ROW_TINTS + HEATS:
            for fg in (TEXT_FG if tint in ROW_TINTS else HEAT_FG) + ["focus"]:
                thr = 3.0 if fg == "focus" else 4.5
                if fg in rgb and tint in rgb:
                    r = contrast(rgb[fg], rgb[tint])
                    bad = r < thr
                    failures += bad
                    if bad or fg in ("text-muted", "focus") or (fg == "link" and tint in HEATS):
                        out.append("  %-34s %6.2f:1  needs %.1f%s" % ("%s on %s" % (fg, tint), r, thr, "  FAIL" if bad else ""))
        for g in GRPS:
            grounds = [b for b in SURFACES + ROW_TINTS if b in rgb]
            if g in rgb and grounds:
                r, on = min((contrast(rgb[g], rgb[b]), b) for b in grounds)
                bad = r < 4.5
                failures += bad
                out.append("  %-34s %6.2f:1  needs 4.5%s" % ("%s on %s (lowest)" % (g, on), r, "  FAIL" if bad else ""))
        for i in range(1, 7):
            ink, own = "rainbow-ink-%d" % i, "rainbow-%d" % i
            joins = ["rainbow-join-%d" % i, "rainbow-join-%d" % (6 if i == 1 else i - 1)]
            if all(t in rgb for t in [ink, own] + joins):
                r = min(contrast(rgb[ink], rgb[t]) for t in [own] + joins)
                bad = r < 3.0
                failures += bad
                out.append("  %-34s %6.2f:1  needs 3.0%s" % ("rainbow ink %d on slice %d" % (i, i), r, "  FAIL" if bad else ""))
        out.append("")
    return failures


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check a site's effective palette against the baseline's contrast thresholds.")
    ap.add_argument("--palettes", default=os.path.join(HERE, os.pardir, "palettes.css"),
                    help="the baseline's palettes.css (default: the package's own)")
    ap.add_argument("--site-palette", help="the site's site-palette.css, loaded after palettes.css")
    ap.add_argument("--site", action="append", help="site name without the site- prefix, for example grclibrary; repeatable")
    args = ap.parse_args(argv)
    out = []
    try:
        sheets = [(os.path.normpath(args.palettes), read_rules(args.palettes, strict=False))]
        if args.site_palette:
            sheets.append((os.path.normpath(args.site_palette), read_rules(args.site_palette, strict=True)))
        known = sites_in(sheets[0][1])
        if not known:
            raise CheckError("%s: no .site-<name> palette found" % args.palettes)
        sites = args.site or known
        for s in sites:
            if s not in known:
                raise CheckError("unknown site %r; palettes.css defines: %s" % (s, ", ".join(known)))
        failures = 0
        for s in sites:
            failures += check_site(sheets, s, out)
    except CheckError as e:
        print("\n".join(out))
        print("ERROR: %s" % e)
        print("RESULT: fail (the input could not be checked)")
        return 1
    print("\n".join(out))
    print("RESULT: %s (%d site%s, %d failing check%s)" % ("pass" if not failures else "fail", len(sites),
          "" if len(sites) == 1 else "s", failures, "" if failures == 1 else "s"))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
